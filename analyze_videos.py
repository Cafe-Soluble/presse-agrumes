#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_videos.py
==================

Scanne récursivement un dossier (par défaut le dossier courant) à la recherche
de fichiers vidéo, extrait leurs métadonnées via `ffprobe` (format, codec,
bitrate, résolution, durée, taille, date...), estime de façon PESSIMISTE le
gain d'espace disque potentiel si le fichier était ré-encodé en AV1, puis
trie et exporte le résultat dans un fichier JSON réutilisable par un futur
script de compression.

Prérequis :
    - ffmpeg / ffprobe installés et disponibles dans le PATH
      (sur un NAS type OMV/Synology/Unraid : `apt install ffmpeg` ou paquet
      communautaire équivalent)
    - Python 3.7+

Utilisation :
    python3 analyze_videos.py
    python3 analyze_videos.py /srv/dev-disk-by-label5/Partage
    python3 analyze_videos.py /srv/dev-disk-by-label5/Partage -o resultats.json -w 8

Sortie :
    - Affichage en console de chaque fichier analysé au fur et à mesure
    - Un fichier JSON contenant la liste complète des fichiers, triée par
      gain potentiel décroissant (les meilleurs candidats à la compression
      AV1 en premier)
    - Un récapitulatif final (nombre de fichiers, taille totale, gain total
      estimé)
"""

import argparse
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Extensions vidéo "génériques" prises en compte (insensible à la casse)
VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".m2v", ".m2ts", ".mts", ".ts", ".vob", ".3gp",
    ".3g2", ".ogv", ".divx", ".asf", ".rm", ".rmvb", ".f4v", ".mxf",
    ".y4m", ".yuv",
}

# Facteur de gain "de base" (pessimiste) par codec vidéo si ré-encodé en AV1.
# 0.35 = on estime récupérer 35% de la taille du fichier, dans le pire des cas.
# Ce sont des ordres de grandeur volontairement prudents.
CODEC_GAIN_FACTORS = {
    "av1": 0.00,          # déjà en AV1, rien à gagner
    "vp9": 0.15,
    "hevc": 0.15,         # H.265
    "h265": 0.15,
    "h264": 0.35,
    "avc": 0.35,
    "avc1": 0.35,
    "mpeg4": 0.45,
    "msmpeg4": 0.45,
    "mpeg4v2": 0.45,
    "vp8": 0.40,
    "vc1": 0.50,
    "wmv3": 0.50,
    "wmv2": 0.55,
    "wmv1": 0.55,
    "mpeg2video": 0.55,
    "mpeg1video": 0.55,
    "theora": 0.50,
    "cinepak": 0.60,
    "ffv1": 0.55,         # lossless déjà compressé, marge plus faible
    "prores": 0.75,
    "dnxhd": 0.75,
    "huffyuv": 0.85,
    "utvideo": 0.85,
    "rawvideo": 0.85,     # brut / sans compression
}
DEFAULT_GAIN_FACTOR = 0.30  # codec inconnu -> hypothèse prudente
MAX_GAIN_FACTOR = 0.90      # on ne promet jamais plus de 90% de gain

# Seuils de "bits par pixel" (bit_rate / (largeur*hauteur*fps)) pour ajuster
# l'estimation : un fichier déjà très peu bitrate-gourmand pour sa résolution
# est probablement déjà bien compressé -> on réduit le gain espéré.
BPP_LOW = 0.04
BPP_MID = 0.08
BPP_HIGH = 0.15


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def human_size(num_bytes):
    """Convertit un nombre d'octets en chaîne lisible (Ko/Mo/Go/To)."""
    if num_bytes is None:
        return "N/A"
    step = 1024.0
    for unit in ["o", "Ko", "Mo", "Go", "To", "Po"]:
        if abs(num_bytes) < step:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.2f} Eo"


def parse_frame_rate(rate_str):
    """Parse une chaîne du type '25/1' ou '30000/1001' renvoyée par ffprobe."""
    if not rate_str:
        return None
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            num, den = float(num), float(den)
            if den == 0:
                return None
            return num / den
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return None


def find_video_files(root):
    """Parcourt récursivement `root` et renvoie la liste des chemins vidéo.

    Affiche une progression pendant le parcours (dossiers visités, fichiers
    vidéo trouvés) car sur un gros volume (RAID de plusieurs To) le simple
    listage de l'arborescence peut prendre plusieurs minutes sans que
    l'analyse ffprobe n'ait même commencé.
    """
    files = []
    dirs_scanned = 0
    start = time.time()
    last_print = start

    print("Parcours de l'arborescence en cours (cela peut prendre du temps "
          "sur un gros volume)...", flush=True)

    for dirpath, _dirnames, filenames in os.walk(root):
        dirs_scanned += 1
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                files.append(os.path.join(dirpath, name))

        now = time.time()
        if now - last_print >= 2:  # affichage toutes les ~2 secondes
            elapsed = now - start
            print(
                f"  ... {dirs_scanned} dossier(s) parcourus, "
                f"{len(files)} vidéo(s) trouvée(s) jusqu'à présent "
                f"({elapsed:.0f}s écoulées) - en cours : {dirpath}",
                flush=True,
            )
            last_print = now

    elapsed = time.time() - start
    print(
        f"Parcours terminé en {elapsed:.0f}s : {dirs_scanned} dossier(s) "
        f"visités, {len(files)} fichier(s) vidéo trouvés.\n",
        flush=True,
    )
    return files


def run_ffprobe(path):
    """Appelle ffprobe et renvoie le JSON parsé, ou None en cas d'échec."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def estimate_gain(codec_name, size_bytes, bit_rate, width, height, fps):
    """Calcule le facteur de gain pessimiste et l'estime en octets."""
    codec_key = (codec_name or "").lower()
    base_factor = CODEC_GAIN_FACTORS.get(codec_key, DEFAULT_GAIN_FACTOR)

    bpp = None
    if bit_rate and width and height and fps:
        try:
            bpp = bit_rate / (width * height * fps)
        except ZeroDivisionError:
            bpp = None

    if bpp is None:
        adjustment = 1.0
    elif bpp < BPP_LOW:
        adjustment = 0.5   # déjà très compressé pour sa résolution
    elif bpp < BPP_MID:
        adjustment = 0.8
    elif bpp < BPP_HIGH:
        adjustment = 1.0
    else:
        adjustment = 1.3   # bitrate généreux -> plus de marge probable

    final_factor = min(base_factor * adjustment, MAX_GAIN_FACTOR)
    gain_bytes = int(size_bytes * final_factor) if size_bytes else 0
    return final_factor, gain_bytes, bpp


def analyze_file(path):
    """Construit le dictionnaire de métadonnées pour un fichier vidéo."""
    try:
        stat = os.stat(path)
        size_bytes = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except OSError as exc:
        return {"path": path, "error": f"stat impossible: {exc}"}

    probe = run_ffprobe(path)
    if probe is None:
        return {
            "path": path,
            "filename": os.path.basename(path),
            "extension": os.path.splitext(path)[1].lower(),
            "size_bytes": size_bytes,
            "size_human": human_size(size_bytes),
            "date_modified": mtime.isoformat(),
            "error": "ffprobe a échoué (fichier corrompu, illisible, ou ffmpeg absent)",
        }

    fmt = probe.get("format", {}) or {}
    streams = probe.get("streams", []) or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    container_format = fmt.get("format_name", "inconnu")
    duration_sec = float(fmt.get("duration", 0) or 0)

    # bit_rate : priorité au format global, sinon au flux vidéo, sinon calcul manuel
    bit_rate = fmt.get("bit_rate") or video_stream.get("bit_rate")
    bit_rate = int(bit_rate) if bit_rate else None
    if not bit_rate and duration_sec > 0:
        bit_rate = int((size_bytes * 8) / duration_sec)

    width = video_stream.get("width")
    height = video_stream.get("height")
    fps = parse_frame_rate(video_stream.get("r_frame_rate"))
    video_codec = video_stream.get("codec_name", "inconnu")
    audio_codec = audio_stream.get("codec_name", "aucun/inconnu")

    gain_factor, gain_bytes, bpp = estimate_gain(
        video_codec, size_bytes, bit_rate, width, height, fps
    )

    entry = {
        "path": os.path.abspath(path),
        "filename": os.path.basename(path),
        "extension": os.path.splitext(path)[1].lower(),
        "container_format": container_format,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else "inconnue",
        "fps": round(fps, 3) if fps else None,
        "duration_sec": round(duration_sec, 2),
        "bit_rate_bps": bit_rate,
        "bit_rate_human": f"{bit_rate / 1000:.0f} kbps" if bit_rate else "N/A",
        "bits_per_pixel": round(bpp, 4) if bpp else None,
        "size_bytes": size_bytes,
        "size_human": human_size(size_bytes),
        "date_modified": mtime.isoformat(),
        "already_av1": video_codec.lower() == "av1",
        "estimated_gain_factor": round(gain_factor, 3),
        "estimated_gain_percent": round(gain_factor * 100, 1),
        "estimated_gain_bytes": gain_bytes,
        "estimated_gain_human": human_size(gain_bytes),
        "error": None,
    }
    return entry


def save_output(output_path, root, results, errors, total_found, partial=False):
    """Écrit le JSON de sortie de façon atomique (fichier temporaire + rename)
    pour ne jamais laisser un JSON corrompu/tronqué si le script est coupé
    en pleine écriture."""
    sorted_results = sorted(results, key=lambda e: e["estimated_gain_bytes"], reverse=True)
    output_data = {
        "scan_root": root,
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "partial": partial,
        "total_files_found": total_found,
        "total_files_analyzed": len(sorted_results),
        "total_files_errors": len(errors),
        "files": sorted_results,
        "errors": errors,
    }
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)  # remplacement atomique
    return sorted_results


def print_summary(results, errors, total_found, output_path):
    total_size = sum(e["size_bytes"] for e in results)
    total_gain = sum(e["estimated_gain_bytes"] for e in results)
    already_av1_count = sum(1 for e in results if e["already_av1"])
    pct_gain = (total_gain / total_size * 100) if total_size else 0

    print("\n" + "=" * 60)
    print("RÉCAPITULATIF")
    print("=" * 60)
    print(f"Fichiers vidéo trouvés           : {total_found}")
    print(f"Fichiers analysés avec succès     : {len(results)}")
    print(f"Fichiers en erreur                : {len(errors)}")
    print(f"Déjà en AV1                       : {already_av1_count}")
    print(f"Taille totale actuelle            : {human_size(total_size)}")
    print(f"Gain potentiel total estimé       : {human_size(total_gain)} "
          f"({pct_gain:.1f}% de la taille totale)")
    print(f"Taille estimée après compression  : {human_size(total_size - total_gain)}")
    print("-" * 60)
    print("Top 10 des meilleurs candidats à la compression AV1 :")
    for e in results[:10]:
        print(f"  - {e['filename']} ({e['video_codec']}, {e['size_human']}) "
              f"-> gain estimé {e['estimated_gain_human']} "
              f"({e['estimated_gain_percent']}%)")
    print("-" * 60)
    print(f"Résultat détaillé exporté dans : {output_path}")
    print("=" * 60)


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Analyse les vidéos d'un dossier pour préparer une compression AV1."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Dossier racine à scanner (par défaut : dossier courant).",
    )
    parser.add_argument(
        "-o", "--output",
        default="video_compression_candidates.json",
        help="Chemin du fichier JSON de sortie.",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int, default=2,
        help="Nombre de threads ffprobe en parallèle (défaut : 2). "
             "Sur un RAID en disques mécaniques, trop de threads en "
             "parallèle sature les I/O et RALENTIT le scan au lieu de "
             "l'accélérer. Monte à 4-6 seulement si c'est du SSD/NVMe.",
    )
    parser.add_argument(
        "--min-size-mb",
        type=float, default=0,
        help="Ignore les fichiers plus petits que ce seuil (en Mo).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reprend une analyse interrompue : relit le fichier de sortie "
             "existant et ne ré-analyse pas les fichiers déjà présents.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int, default=50,
        help="Sauvegarde le JSON de sortie tous les N fichiers analysés "
             "(défaut : 50), pour ne rien perdre en cas d'interruption.",
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"Erreur : '{root}' n'est pas un dossier valide.", file=sys.stderr)
        sys.exit(1)

    output_path = os.path.abspath(args.output)

    print(f"Recherche des fichiers vidéo dans : {root}", flush=True)
    all_files = find_video_files(root)

    if args.min_size_mb > 0:
        min_bytes = args.min_size_mb * 1024 * 1024
        all_files = [f for f in all_files if os.path.getsize(f) >= min_bytes]

    total_found = len(all_files)

    # --- Reprise d'une analyse précédente -------------------------------
    results = []
    errors = []
    already_done_paths = set()
    if args.resume and os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                previous = json.load(f)
            results = previous.get("files", [])
            errors = previous.get("errors", [])
            already_done_paths = {e["path"] for e in results} | {
                e["path"] for e in errors if e.get("path")
            }
            print(f"Reprise : {len(already_done_paths)} fichier(s) déjà "
                  f"analysés seront ignorés.", flush=True)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Impossible de lire le fichier de reprise ({exc}), "
                  f"on repart de zéro.", flush=True)

    to_process = [
        f for f in all_files if os.path.abspath(f) not in already_done_paths
    ]
    print(f"{total_found} fichier(s) vidéo trouvé(s), "
          f"{len(to_process)} à analyser. Analyse en cours "
          f"(workers={args.workers})...\n", flush=True)

    # --- Analyse avec checkpoints réguliers et arrêt propre sur Ctrl+C --
    interrupted = {"flag": False}

    def handle_sigint(_signum, _frame):
        interrupted["flag"] = True
        print("\nInterruption demandée (Ctrl+C) - sauvegarde des résultats "
              "en cours, merci de patienter...", flush=True)

    signal.signal(signal.SIGINT, handle_sigint)

    start_time = time.time()
    done = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
    future_to_path = {executor.submit(analyze_file, f): f for f in to_process}

    try:
        for future in concurrent.futures.as_completed(future_to_path):
            done += 1
            entry = future.result()
            if entry.get("error"):
                errors.append(entry)
                print(f"[{done}/{len(to_process)}] ⚠ {entry['path']} -> {entry['error']}",
                      flush=True)
            else:
                results.append(entry)
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = len(to_process) - done
                eta_s = remaining / rate if rate > 0 else 0
                print(
                    f"[{done}/{len(to_process)}] {entry['filename']} | "
                    f"{entry['video_codec']} | {entry['resolution']} | "
                    f"{entry['bit_rate_human']} | {entry['size_human']} | "
                    f"gain estimé: {entry['estimated_gain_percent']}% "
                    f"({entry['estimated_gain_human']}) | "
                    f"ETA ~{eta_s/60:.0f} min",
                    flush=True,
                )

            if done % args.checkpoint_every == 0:
                save_output(output_path, root, results, errors, total_found, partial=True)

            if interrupted["flag"]:
                for f in future_to_path:
                    f.cancel()
                break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # ---------------- Sauvegarde finale + récapitulatif ----------------
    final_results = save_output(
        output_path, root, results, errors, total_found,
        partial=interrupted["flag"],
    )
    print_summary(final_results, errors, total_found, output_path)
    if interrupted["flag"]:
        print("\n⚠ Analyse interrompue par l'utilisateur : le JSON contient "
              "les résultats partiels. Relance avec --resume pour continuer.")


if __name__ == "__main__":
    main()
