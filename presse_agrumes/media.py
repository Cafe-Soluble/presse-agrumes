"""Moteur média : scan, ffprobe, estimation de gain et commandes ffmpeg.

C'est le cœur historique du projet (adapté de `analyze_videos.py`). Les
fonctions de ce module ne font aucune I/O réseau et ne connaissent pas
FastAPI : elles sont testables isolément.

Règles importantes :
- Toutes les commandes ffmpeg sont construites sous forme de listes (jamais
  de `shell=True`) pour éviter toute injection.
- L'estimation de gain reste volontairement pessimiste.
- Les fichiers déjà en AV1 ont un gain nul et ne sont jamais recompressés.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from . import config

VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".m2v", ".m2ts", ".mts", ".ts", ".vob", ".3gp",
    ".3g2", ".ogv", ".divx", ".asf", ".rm", ".rmvb", ".f4v", ".mxf",
    ".y4m", ".yuv",
}

# Répertoires virtuels à ne jamais parcourir, même si l'utilisateur choisit /.
SKIP_DIRS = {
    "/proc", "/sys", "/dev", "/run", "/var/lib/docker", "/snap",
}

CODEC_GAIN_FACTORS = {
    "av1": 0.00,
    "vp9": 0.15,
    "hevc": 0.15,
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
    "ffv1": 0.55,
    "prores": 0.75,
    "dnxhd": 0.75,
    "huffyuv": 0.85,
    "utvideo": 0.85,
    "rawvideo": 0.85,
}
DEFAULT_GAIN_FACTOR = 0.30
MAX_GAIN_FACTOR = 0.90

BPP_LOW = 0.04
BPP_MID = 0.08
BPP_HIGH = 0.15

CONTAINER_EXT = {"mkv": ".mkv", "mp4": ".mp4", "webm": ".webm"}


# ---------------------------------------------------------------------------
# Formatage / utilitaires
# ---------------------------------------------------------------------------

def human_size(num_bytes: float | None) -> str:
    if num_bytes is None:
        return "N/A"
    value = float(num_bytes)
    for unit in ["o", "Ko", "Mo", "Go", "To", "Po"]:
        if abs(value) < 1024.0:
            if unit == "o":
                return f"{int(value)} o"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} Eo"


def human_duration(seconds: float | None) -> str:
    if not seconds or seconds < 0:
        return "-"
    seconds = int(round(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days} j {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def parse_frame_rate(rate_str: str | None) -> float | None:
    if not rate_str:
        return None
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/", 1)
            num_f, den_f = float(num), float(den)
            if den_f == 0:
                return None
            return num_f / den_f
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return None


def _safe_float(value) -> float | None:
    try:
        result = float(value)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Parcours du système de fichiers
# ---------------------------------------------------------------------------

def _matches_any(relative: str, name: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def find_video_files(
    root: Path,
    *,
    exclude_globs: list[str] | None = None,
    follow_symlinks: bool = False,
    min_size_bytes: int = 0,
    progress: Callable[[dict], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[list[Path], list[dict], dict]:
    """Parcourt récursivement `root` et renvoie (fichiers, erreurs, stats).

    Gère les dossiers illisibles via `onerror` : un dossier en erreur ne doit
    jamais interrompre tout le scan d'un NAS.
    """
    patterns = exclude_globs or []
    files: list[Path] = []
    errors: list[dict] = []
    dirs_scanned = 0
    start = time.time()
    last_report = 0.0

    def on_error(exc: OSError) -> None:
        errors.append({
            "path": getattr(exc, "filename", None) or str(root),
            "error": f"dossier illisible : {exc}",
        })

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, onerror=on_error, followlinks=follow_symlinks
    ):
        dirnames[:] = [
            name
            for name in dirnames
            if not _is_skipped_dir(Path(dirpath) / name)
            and not _matches_any(
                str((Path(dirpath) / name).relative_to(root)), name, patterns
            )
        ]
        dirs_scanned += 1
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                relative = str(path)
            if _matches_any(relative, name, patterns):
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                errors.append({"path": str(path), "error": f"stat impossible : {exc}"})
                continue
            if size < min_size_bytes:
                continue
            files.append(path)

        now = time.time()
        if progress and now - last_report >= 0.5:
            last_report = now
            progress({
                "dirs_scanned": dirs_scanned,
                "files_found": len(files),
                "current_dir": dirpath,
                "elapsed": round(now - start, 1),
            })
        if cancel and cancel():
            break

    stats = {
        "dirs_scanned": dirs_scanned,
        "files_found": len(files),
        "elapsed": round(time.time() - start, 2),
    }
    return files, errors, stats


def _is_skipped_dir(path: Path) -> bool:
    try:
        resolved = str(path.resolve())
    except OSError:
        return False
    return any(
        resolved == skipped or resolved.startswith(skipped + "/")
        for skipped in SKIP_DIRS
    )


# ---------------------------------------------------------------------------
# ffprobe / analyse
# ---------------------------------------------------------------------------

def run_ffprobe(path: str | Path) -> tuple[dict | None, str | None]:
    binary = config.ffprobe_bin()
    if not binary:
        return None, "ffprobe introuvable (installez ffmpeg ou renseignez [ffmpeg] dans config.toml)."
    command = [
        binary, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=120,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return None, "ffprobe a dépassé le délai de 120 s."
    except OSError as exc:
        return None, f"ffprobe n'a pas pu démarrer : {exc}"
    if result.returncode != 0 or not result.stdout.strip():
        message = (result.stderr or "").strip().splitlines()
        return None, message[-1] if message else "ffprobe a échoué."
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"sortie ffprobe illisible : {exc}"


def estimate_gain(
    codec_name: str | None,
    size_bytes: int,
    bit_rate: int | None,
    width: int | None,
    height: int | None,
    fps: float | None,
) -> tuple[float, int, float | None, int]:
    """Renvoie (facteur, gain octets, bpp, taille estimée après compression)."""
    codec_key = (codec_name or "").lower()
    base_factor = CODEC_GAIN_FACTORS.get(codec_key, DEFAULT_GAIN_FACTOR)
    if codec_key == "av1":
        return 0.0, 0, None, size_bytes

    bpp = None
    if bit_rate and width and height and fps:
        try:
            bpp = bit_rate / (width * height * fps)
        except ZeroDivisionError:
            bpp = None

    if bpp is None:
        adjustment = 1.0
    elif bpp < BPP_LOW:
        adjustment = 0.5
    elif bpp < BPP_MID:
        adjustment = 0.8
    elif bpp < BPP_HIGH:
        adjustment = 1.0
    else:
        adjustment = 1.3

    final_factor = min(base_factor * adjustment, MAX_GAIN_FACTOR)
    gain_bytes = int(size_bytes * final_factor) if size_bytes else 0
    estimated_output = max(0, size_bytes - gain_bytes)
    return final_factor, gain_bytes, bpp, estimated_output


REFERENCE_CRF = 32


def adjusted_gain_for_crf(
    base_factor: float,
    size_bytes: int,
    crf: int,
) -> tuple[float, int, int]:
    """Ajuste le gain selon le CRF choisi (référence : CRF 32).

    Chaque +16 CRF divise approximativement le débit par deux : monter le CRF
    augmente le gain, le baisser (qualité supérieure) réduit le gain et
    augmente la taille estimée.
    """
    output_ratio = min(0.98, max(0.02, 1.0 - float(base_factor)))
    scale = 2 ** ((REFERENCE_CRF - int(crf)) / 16.0)
    adjusted_output = min(0.98, max(0.02, output_ratio * scale))
    factor = min(0.95, 1.0 - adjusted_output)
    gain_bytes = int(size_bytes * factor) if size_bytes else 0
    return round(factor, 3), gain_bytes, max(0, size_bytes - gain_bytes)


def _pick_duration(fmt: dict, video_stream: dict) -> float:
    duration = _safe_float(fmt.get("duration"))
    if duration is None:
        duration = _safe_float(video_stream.get("duration"))
    if duration is None:
        duration = 0.0
    return duration


def friendly_probe_error(path: Path, message: str | None) -> tuple[str, str, str]:
    """Traduit les erreurs ffprobe en message actionnable.

    Retourne (message, code, conseil). On retire le chemin répété en préfixe
    pour que l'interface n'affiche pas deux fois le même fichier.
    """
    clean = (message or "").strip()
    path_prefix = str(path)
    if clean.startswith(path_prefix + ":"):
        clean = clean[len(path_prefix) + 1:].strip()
    lower = clean.lower()

    if "invalid data found" in lower or "moov atom not found" in lower:
        return (
            "Fichier illisible ou corrompu : ffprobe ne reconnaît pas le format.",
            "invalid_data",
            "Le fichier est probablement tronqué, incomplet ou dans un format exotique. "
            "Il est ignoré par l'analyse et la compression.",
        )
    if "permission denied" in lower:
        return (
            "Permission refusée lors de la lecture du fichier.",
            "permission_denied",
            "Vérifiez les droits de l'utilisateur qui exécute Presse-Agrumes.",
        )
    if "no such file" in lower:
        return (
            "Fichier introuvable (supprimé ou déplacé pendant l'analyse).",
            "not_found",
            "Relancez l'analyse si le fichier est revenu.",
        )
    if "dépassé" in lower or "timeout" in lower:
        return (
            "ffprobe a dépassé le temps imparti.",
            "timeout",
            "Le fichier est peut-être sur un support lent ou endommagé. Il est ignoré.",
        )
    return (
        f"ffprobe n'a pas pu analyser le fichier : {clean or 'erreur inconnue'}",
        "probe_error",
        "Le fichier est ignoré par l'analyse et la compression.",
    )


def analyze_file(path: str | Path, root: str | Path) -> dict:
    """Construit la fiche complète d'un fichier vidéo (jamais d'exception)."""
    path = Path(path)
    root = Path(root)
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = str(path)

    entry: dict = {
        "path": str(path),
        "relative_path": relative,
        "filename": path.name,
        "parent": str(path.parent),
        "extension": path.suffix.lower(),
        "error": None,
        "error_code": None,
        "error_hint": None,
        "readable": False,
        "parent_writable": False,
    }
    try:
        stat = path.stat()
        size_bytes = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except OSError as exc:
        entry["error"] = f"stat impossible : {exc}"
        entry["error_code"] = "stat_error"
        entry["error_hint"] = "Le fichier est ignoré par l'analyse et la compression."
        return entry

    entry.update({
        "size_bytes": size_bytes,
        "size_human": human_size(size_bytes),
        "date_modified": mtime.isoformat(),
        "readable": os.access(path, os.R_OK),
        "parent_writable": os.access(path.parent, os.W_OK | os.X_OK),
    })
    if not entry["readable"]:
        entry["error"] = "Fichier non lisible (permissions)."
        entry["error_code"] = "permission_denied"
        entry["error_hint"] = "Vérifiez les droits de l'utilisateur qui exécute Presse-Agrumes."
        return entry
    if size_bytes == 0:
        entry["error"] = "Fichier vide (0 octet) : téléchargement incomplet ou fichier de travail."
        entry["error_code"] = "empty_file"
        entry["error_hint"] = (
            "Presse-Agrumes l'ignore : aucun fichier n'est modifié. "
            "Supprimez-le ou remplacez-le si nécessaire."
        )
        return entry

    probe, probe_error = run_ffprobe(path)
    if probe is None:
        message, code, hint = friendly_probe_error(path, probe_error)
        entry["error"] = message
        entry["error_code"] = code
        entry["error_hint"] = hint
        return entry

    fmt = probe.get("format", {}) or {}
    streams = probe.get("streams", []) or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    audio_stream = audio_streams[0] if audio_streams else {}

    width = video_stream.get("width")
    height = video_stream.get("height")
    fps = parse_frame_rate(video_stream.get("r_frame_rate"))
    duration_sec = _pick_duration(fmt, video_stream)
    bit_rate = fmt.get("bit_rate") or video_stream.get("bit_rate")
    try:
        bit_rate = int(float(bit_rate)) if bit_rate else None
    except (TypeError, ValueError):
        bit_rate = None
    if not bit_rate and duration_sec > 0:
        bit_rate = int((size_bytes * 8) / duration_sec)

    video_codec = (video_stream.get("codec_name") or "inconnu").lower()
    audio_codec = (audio_stream.get("codec_name") or "aucun").lower()
    pix_fmt = video_stream.get("pix_fmt") or ""
    color_transfer = (video_stream.get("color_transfer") or "").lower()
    is_hdr = color_transfer in {"smpte2084", "arib-std-b67", "smpte428"}
    is_10bit = any(token in pix_fmt for token in ("10le", "10be", "12le", "12be"))
    if video_codec not in {"inconnu", "av1"} and not width:
        entry["error"] = "Aucun flux vidéo exploitable détecté."
        entry["error_code"] = "no_video"
        entry["error_hint"] = "Le fichier est ignoré par l'analyse et la compression."
        return entry

    gain_factor, gain_bytes, bpp, estimated_output = estimate_gain(
        video_codec, size_bytes, bit_rate, width, height, fps
    )
    if video_codec == "av1":
        recommendation = "already_av1"
    elif gain_factor >= 0.45:
        recommendation = "excellent"
    elif gain_factor >= 0.30:
        recommendation = "bon"
    elif gain_factor >= 0.15:
        recommendation = "faible"
    else:
        recommendation = "tres_faible"

    entry.update({
        "container_format": fmt.get("format_name", "inconnu"),
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "audio_streams": len(audio_streams),
        "subtitle_streams": len(subtitle_streams),
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else "inconnue",
        "fps": round(fps, 3) if fps else None,
        "duration_sec": round(duration_sec, 2),
        "duration_human": human_duration(duration_sec),
        "bit_rate_bps": bit_rate,
        "bit_rate_human": f"{bit_rate / 1000:.0f} kbps" if bit_rate else "N/A",
        "bits_per_pixel": round(bpp, 4) if bpp else None,
        "pix_fmt": pix_fmt,
        "is_10bit": is_10bit,
        "is_hdr": is_hdr,
        "already_av1": video_codec == "av1",
        "estimated_gain_factor": round(gain_factor, 3),
        "estimated_gain_percent": round(gain_factor * 100, 1),
        "estimated_gain_bytes": gain_bytes,
        "estimated_gain_human": human_size(gain_bytes),
        "estimated_output_bytes": estimated_output,
        "estimated_output_human": human_size(estimated_output),
        "recommendation": recommendation,
    })
    return entry


# ---------------------------------------------------------------------------
# Détection / commandes ffmpeg
# ---------------------------------------------------------------------------

_ENCODER_CACHE: dict[str, object] = {}


def ffmpeg_version() -> str | None:
    binary = config.ffmpeg_bin()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, timeout=15
        )
        return result.stdout.splitlines()[0] if result.stdout else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def available_encoders(force: bool = False) -> dict[str, bool]:
    """Détecte les encodeurs AV1 disponibles, avec cache mémoire."""
    cache_key = config.ffmpeg_bin() or ""
    if not force and _ENCODER_CACHE.get("key") == cache_key:
        return _ENCODER_CACHE["value"]  # type: ignore[return-value]
    result = {
        "libsvtav1": False,
        "libaom-av1": False,
        "av1_vaapi": False,
        "av1_nvenc": False,
        "av1_qsv": False,
        "libx265": False,
        "hevc_vaapi": False,
        "hevc_qsv": False,
        "hevc_nvenc": False,
        "h264_vaapi": False,
        "libx264": False,
    }
    binary = config.ffmpeg_bin()
    if binary:
        try:
            proc = subprocess.run(
                [binary, "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=30,
            )
            text = proc.stdout + proc.stderr
            for encoder in list(result):
                if encoder in text:
                    result[encoder] = True
        except (OSError, subprocess.TimeoutExpired):
            pass
    _ENCODER_CACHE.clear()
    _ENCODER_CACHE.update({"key": cache_key, "value": result})
    return result


def choose_encoder(
    requested: str, available: dict[str, bool], codec: str = "av1"
) -> str | None:
    if requested != "auto":
        return requested if available.get(requested) else None
    candidates = (
        ("libsvtav1", "libaom-av1", "av1_vaapi")
        if codec != "hevc"
        else ("libx265", "hevc_vaapi", "hevc_qsv")
    )
    for candidate in candidates:
        if available.get(candidate):
            return candidate
    return None


def encoder_display_name(encoder: str | None) -> str:
    return {
        "libsvtav1": "SVT-AV1 (CPU)",
        "libaom-av1": "libaom AV1 (CPU, lent)",
        "av1_vaapi": "VAAPI (GPU)",
        "av1_nvenc": "NVENC (GPU)",
        "av1_qsv": "Quick Sync (GPU)",
        "libx265": "H.265 / libx265 (CPU)",
        "hevc_vaapi": "H.265 VAAPI (GPU)",
        "hevc_qsv": "H.265 Quick Sync (GPU)",
        "hevc_nvenc": "H.265 NVENC (GPU)",
    }.get(encoder or "", encoder or "inconnu")


def container_extension(container: str) -> str:
    return CONTAINER_EXT.get(container, ".mkv")


_CODEC_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:x264|x265|h\.?264|h\.?265|hevc|avc|av1|vp9|xvid|divx|10bit|8bit|hdr10)(?![a-z0-9])"
)


def _collapse_separators(match: re.Match[str]) -> str:
    separators = match.group(0)
    for separator in ("-", "_", " "):
        if separator in separators:
            return separator
    return "."


def strip_codec_tokens(stem: str) -> str:
    """Retire les marqueurs de codec du nom (x265, H264, HEVC, AV1...)."""
    cleaned = _CODEC_TOKEN_RE.sub("", stem)
    cleaned = re.sub(r"[._\-\s]{2,}", _collapse_separators, cleaned).strip(" ._-")
    return cleaned or stem


def output_filename(
    source: Path,
    settings,
    output_mode: str,
    suffix: str,
    clean_codec: bool = False,
) -> str:
    if output_mode == "same_dir_same_name":
        return source.stem + container_extension(settings.container)
    stem = strip_codec_tokens(source.stem) if clean_codec else source.stem
    cleaned = suffix.strip() or "av1"
    return f"{stem}.{cleaned}{container_extension(settings.container)}"



X265_PRESETS = [
    "placebo", "veryslow", "slower", "slow", "medium", "medium",
    "fast", "faster", "veryfast", "superfast", "ultrafast", "ultrafast",
    "ultrafast", "ultrafast",
]
QSV_PRESETS = [
    "veryslow", "veryslow", "slower", "slow", "medium", "medium",
    "fast", "faster", "veryfast", "veryfast", "veryfast", "veryfast",
    "veryfast", "veryfast",
]


def x265_preset_name(preset: int) -> str:
    return X265_PRESETS[min(13, max(0, int(preset)))]


def qsv_preset_name(preset: int) -> str:
    return QSV_PRESETS[min(13, max(0, int(preset)))]


def video_encode_args(settings, encoder: str, threads: int) -> list[str]:
    """Arguments vidéo communs à la compression, au test et au benchmark."""
    if encoder == "libsvtav1":
        return ["-c:v", "libsvtav1", "-preset", str(settings.preset),
                "-crf", str(settings.crf), "-pix_fmt", settings.pixel_format,
                "-svtav1-params", f"lp={max(1, threads)}"]
    if encoder == "libaom-av1":
        aom_cpu = min(8, max(0, round(settings.preset * 8 / 13)))
        return ["-c:v", "libaom-av1", "-cpu-used", str(aom_cpu),
                "-crf", str(settings.crf), "-b:v", "0",
                "-pix_fmt", settings.pixel_format, "-threads", str(max(1, threads))]
    if encoder == "av1_vaapi":
        return ["-vaapi_device", "/dev/dri/renderD128",
                "-vf", "format=nv12,hwupload", "-c:v", "av1_vaapi",
                "-qp", str(min(255, max(0, round(settings.crf * 255 / 63))))]
    if encoder == "libx265":
        crf = min(51, max(0, int(settings.crf)))
        return ["-c:v", "libx265", "-preset", x265_preset_name(settings.preset),
                "-crf", str(crf), "-pix_fmt", settings.pixel_format]
    if encoder == "hevc_vaapi":
        qp = min(51, max(0, int(settings.crf)))
        pixel = "p010" if settings.pixel_format == "yuv420p10le" else "nv12"
        return ["-vaapi_device", "/dev/dri/renderD128",
                "-vf", f"format={pixel},hwupload", "-c:v", "hevc_vaapi",
                "-qp", str(qp)]
    if encoder == "hevc_qsv":
        q = min(51, max(1, int(settings.crf)))
        return ["-c:v", "hevc_qsv", "-global_quality", str(q),
                "-preset", qsv_preset_name(settings.preset)]
    raise RuntimeError(f"Encodeur non pris en charge : {encoder}")


def build_compress_command(
    input_path: Path,
    output_path: Path,
    settings,
    *,
    encoder: str,
    threads: int,
    duration_sec: float | None = None,
    preview: bool = False,
) -> list[str]:
    """Construit la commande ffmpeg de compression AV1.

    `preview=True` force un MP4 H.264-compatible pour la lecture navigateur
    (utilisé par les tests qualité), avec audio AAC.
    """
    binary = config.ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg introuvable.")
    container = "mp4" if preview else settings.container
    cmd = [
        binary, "-hide_banner", "-nostdin", "-y",
        "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "0",
    ]

    cmd += video_encode_args(settings, encoder, threads)
    if settings.codec == "hevc" and container == "mp4":
        cmd += ["-tag:v", "hvc1"]

    # Sous-titres : copiés uniquement vers MKV (le MP4/WebM demanderait une
    # conversion supplémentaire, hors périmètre de la v1).
    if settings.subtitles == "copy" and container == "mkv" and not preview:
        cmd += ["-map", "0:s?", "-c:s", "copy"]

    if preview:
        if settings.audio_mode == "none":
            cmd += ["-an"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "160k"]
    elif settings.audio_mode == "copy":
        if container == "webm":
            # WebM n'accepte pas l'audio AAC/AC3 copié : on convertit en Opus.
            cmd += ["-c:a", "libopus", "-b:a", f"{settings.audio_bitrate_kbps}k"]
        else:
            cmd += ["-c:a", "copy"]
    elif settings.audio_mode == "opus":
        cmd += ["-c:a", "libopus", "-b:a", f"{settings.audio_bitrate_kbps}k"]
    elif settings.audio_mode == "aac":
        cmd += ["-c:a", "aac", "-b:a", f"{settings.audio_bitrate_kbps}k"]
    else:
        cmd += ["-an"]

    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", str(output_path)]
    return cmd


def build_preview_original_command(
    input_path: Path, output_path: Path, start: float, duration: float
) -> list[str]:
    binary = config.ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg introuvable.")
    return [
        binary, "-hide_banner", "-nostdin", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
        "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(output_path),
    ]


def build_raw_clip_command(
    input_path: Path, output_path: Path, start: float, duration: float
) -> list[str]:
    binary = config.ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg introuvable.")
    return [
        binary, "-hide_banner", "-nostdin", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
        "-i", str(input_path),
        "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero",
        "-progress", "pipe:1", "-nostats", str(output_path),
    ]


def build_compress_test_command(
    input_path: Path, output_path: Path, settings, *, encoder: str,
    threads: int, start: float, duration: float,
) -> list[str]:
    """Compression d'un extrait, dans un MP4 lisible par le navigateur."""
    binary = config.ffmpeg_bin()
    if not binary:
        raise RuntimeError("ffmpeg introuvable.")
    cmd = [
        binary, "-hide_banner", "-nostdin", "-y",
        "-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}",
        "-i", str(input_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-map_metadata", "0",
    ]
    cmd += video_encode_args(settings, encoder, threads)
    if settings.codec == "hevc":
        cmd += ["-tag:v", "hvc1"]

    if settings.audio_mode == "none":
        cmd += ["-an"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", str(output_path)]
    return cmd


def probe_duration(path: Path) -> tuple[float, dict | None, str | None]:
    probe, error = run_ffprobe(path)
    if probe is None:
        return 0.0, None, error
    fmt = probe.get("format", {}) or {}
    video = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        {},
    )
    return _pick_duration(fmt, video), probe, None


def file_is_valid_video(path: Path, min_duration: float = 0.05) -> tuple[bool, str | None]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "fichier de sortie absent ou vide"
    duration, probe, error = probe_duration(path)
    if probe is None:
        return False, error or "sortie non lisible par ffprobe"
    if duration < min_duration:
        return False, "durée de sortie nulle"
    return True, None
