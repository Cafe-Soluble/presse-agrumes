"""Regroupement des séries en « packs » (saison ou série).

Un pack est simplement l'ensemble des vidéos situées dans un même dossier
marqué comme appartenant à une arborescence de séries. Ce choix est robuste :
- `Breaking Bad/S01/E01.mkv` -> pack du dossier `S01`
- `Breaking Bad/E01.mkv`     -> pack du dossier `Breaking Bad`
- un dossier `Extras/` à côté -> pack `Extras`

L'utilisateur doit explicitement marquer les dossiers de séries lors du scan :
aucune heuristique ne devine le contenu, ce qui évite de regrouper par erreur
des films ou des vidéos personnelles.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .media import human_duration, human_size

SEASON_RE = re.compile(r"(?i)(?:^|[ ._-])(s\d{1,2}|season[ ._-]?\d{1,2}|saison[ ._-]?\d{1,2})(?:$|[ ._-])")
EPISODE_RE = re.compile(r"(?i)(?:^|[ ._-])(e\d{1,3}|episode[ ._-]?\d{1,3})(?:$|[ ._-])")


def _hash(prefix: str, value: str) -> str:
    return prefix + hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:16]


def file_item_id(path: str) -> str:
    return _hash("file:", path)


def pack_item_id(directory: str) -> str:
    return _hash("pack:", directory)


def natural_key(value: str) -> list:
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", value)]


def normalize_roots(raw_roots: Iterable[str]) -> list[Path]:
    roots = []
    for raw in raw_roots:
        try:
            path = Path(raw).expanduser().resolve()
        except OSError:
            continue
        if path.is_dir() and path not in roots:
            roots.append(path)
    # Les racines les plus spécifiques d'abord (si des marqueurs sont imbriqués).
    return sorted(roots, key=lambda p: len(p.parts), reverse=True)


def _marker_for(path: Path, roots: list[Path]) -> Path | None:
    for root in roots:
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def _detect_season(folder_name: str) -> str | None:
    match = SEASON_RE.search(folder_name)
    if match:
        return match.group(1).upper().replace("_", " ").replace(".", " ")
    match = re.search(r"(?i)\b(S\d{1,2})\b", folder_name)
    return match.group(1).upper() if match else None


def _series_base(folder_name: str) -> tuple[str | None, str | None]:
    """Sépare « Adolescence.S01.MULTI… » en (« Adolescence », « S01 »).

    Le nom de série est tout ce qui précède le marqueur de saison, débarrassé
    des séparateurs. Si le dossier s'appelle uniquement « S01 », le nom de
    série est inconnu et sera déduit du dossier parent.
    """
    match = SEASON_RE.search(folder_name)
    if not match:
        return folder_name, None
    season = match.group(1).upper().replace("_", " ").replace(".", " ")
    base = folder_name[:match.start()].strip(" ._-")
    return (base or None), season


def _episode_info(entry: dict) -> dict:
    name = entry["filename"]
    episode = None
    match = EPISODE_RE.search(name)
    if match:
        episode = match.group(1).upper()
    return {
        "id": file_item_id(entry["path"]),
        "path": entry["path"],
        "relative_path": entry.get("relative_path"),
        "filename": name,
        "episode": episode,
        "size_bytes": entry.get("size_bytes", 0),
        "size_human": entry.get("size_human", human_size(entry.get("size_bytes"))),
        "duration_sec": entry.get("duration_sec", 0),
        "duration_human": entry.get("duration_human", "-"),
        "video_codec": entry.get("video_codec"),
        "resolution": entry.get("resolution"),
        "estimated_gain_bytes": entry.get("estimated_gain_bytes", 0),
        "estimated_gain_human": entry.get("estimated_gain_human"),
        "estimated_gain_percent": entry.get("estimated_gain_percent", 0),
        "already_av1": entry.get("already_av1", False),
        "error": entry.get("error"),
    }


def _make_pack(directory: Path, marker: Path, entries: list[dict], root: Path) -> dict:
    entries = sorted(entries, key=lambda e: natural_key(e["filename"]))
    total_size = sum(e.get("size_bytes", 0) for e in entries)
    total_gain = sum(e.get("estimated_gain_bytes", 0) for e in entries)
    total_duration = sum(e.get("duration_sec", 0) for e in entries)
    total_output = sum(e.get("estimated_output_bytes", 0) for e in entries)
    already = sum(1 for e in entries if e.get("already_av1"))
    errors = [e for e in entries if e.get("error")]

    codecs: dict[str, int] = {}
    resolutions: dict[str, int] = {}
    for entry in entries:
        codec = entry.get("video_codec") or "inconnu"
        codecs[codec] = codecs.get(codec, 0) + 1
        resolution = entry.get("resolution") or "inconnue"
        resolutions[resolution] = resolutions.get(resolution, 0) + 1

    try:
        rel_from_marker = directory.relative_to(marker)
        marker_parts = rel_from_marker.parts
    except ValueError:
        marker_parts = (directory.name,)
    try:
        relative = str(directory.relative_to(root))
    except ValueError:
        relative = str(directory)

    folder_name = directory.name
    base_name, season = _series_base(folder_name)
    if season is None and len(marker_parts) >= 2:
        season = _detect_season(marker_parts[-2])
    if marker_parts:
        marker_series = marker_parts[0]
    else:
        marker_series = folder_name

    # Trois cas :
    # 1. le dossier du pack contient la saison dans son nom
    #    (« Adolescence.S01.MULTI… » ou « Breaking Bad S01 ») ;
    # 2. c'est un sous-dossier de saison (« S01 ») dont le parent est la série ;
    # 3. c'est un dossier de série sans saison.
    if base_name and season:
        series_name = base_name
    elif season and len(marker_parts) >= 1 and marker_parts[0] != folder_name:
        series_name = marker_parts[0]
    elif season and directory.parent.name:
        series_name = directory.parent.name
    else:
        series_name = marker_series

    if season:
        display_name = f"{series_name} - {season}"
    elif series_name == folder_name:
        display_name = folder_name
    else:
        display_name = f"{series_name} - {folder_name}"
    if len(entries) > 1:
        display_name += f" ({len(entries)} épisodes)"
    else:
        display_name += " (1 épisode)"

    gain_percent = (total_gain / total_size * 100) if total_size else 0
    if already == len(entries):
        recommendation = "already_av1"
    elif gain_percent >= 45:
        recommendation = "excellent"
    elif gain_percent >= 30:
        recommendation = "bon"
    elif gain_percent >= 15:
        recommendation = "faible"
    else:
        recommendation = "tres_faible"

    return {
        "id": pack_item_id(str(directory)),
        "kind": "series",
        "name": display_name,
        "folder_name": folder_name,
        "series_name": series_name,
        "season_label": season,
        "path": str(directory),
        "relative_path": relative,
        "marker_root": str(marker),
        "episode_count": len(entries),
        "episodes": [_episode_info(e) for e in entries],
        "codec_summary": codecs,
        "resolution_summary": resolutions,
        "size_bytes": total_size,
        "size_human": human_size(total_size),
        "duration_sec": round(total_duration, 2),
        "duration_human": human_duration(total_duration),
        "estimated_gain_bytes": total_gain,
        "estimated_gain_human": human_size(total_gain),
        "estimated_gain_percent": round(gain_percent, 1),
        "estimated_output_bytes": total_output,
        "estimated_output_human": human_size(total_output),
        "already_av1_count": already,
        "error_count": len(errors),
        "recommendation": recommendation,
        "parent_writable": all(e.get("parent_writable") for e in entries),
    }


def build_items(files: list[dict], root: Path, series_roots: Iterable[str]) -> dict:
    """Construit la liste d'items affichables (packs de séries + fichiers).

    Retourne un dict {items, summary, packs}. Les fichiers en erreur restent
    visibles séparément pour que l'utilisateur comprenne ce qui a échoué.
    """
    markers = normalize_roots(series_roots)
    buckets: dict[str, tuple[Path, Path, list[dict]]] = {}
    loose: list[dict] = []
    errors: list[dict] = []

    for entry in files:
        if entry.get("error") or not entry.get("path"):
            errors.append(entry)
            continue
        path = Path(entry["path"])
        marker = _marker_for(path.parent, markers)
        if marker is None:
            loose.append(entry)
            continue
        pack_dir = path.parent
        key = str(pack_dir)
        if key not in buckets:
            buckets[key] = (pack_dir, marker, [])
        buckets[key][2].append(entry)

    packs = [
        _make_pack(directory, marker, entries, root)
        for directory, marker, entries in buckets.values()
    ]

    items = list(packs)
    for entry in loose:
        item = dict(entry)
        item["id"] = file_item_id(entry["path"])
        item["kind"] = "file"
        item["name"] = entry["filename"]
        items.append(item)

    # Les erreurs pures (fichier illisible, ffprobe en échec) sont exposées à
    # part et ne sont pas sélectionnables.
    items.sort(
        key=lambda item: (
            item.get("already_av1", False),
            -item.get("estimated_gain_bytes", 0),
        )
    )

    total_size = sum(i.get("size_bytes", 0) for i in items)
    total_gain = sum(i.get("estimated_gain_bytes", 0) for i in items)
    total_duration = sum(i.get("duration_sec", 0) for i in items)
    total_output = sum(i.get("estimated_output_bytes", 0) for i in items)
    already_count = 0
    for item in items:
        if item["kind"] == "series":
            if item.get("episode_count") and item.get("already_av1_count") == item.get("episode_count"):
                already_count += item["episode_count"]
        elif item.get("already_av1"):
            already_count += 1

    summary = {
        "items_count": len(items),
        "pack_count": len(packs),
        "file_count": len(loose),
        "error_count": len(errors),
        "video_file_count": len(files),
        "total_size_bytes": total_size,
        "total_size_human": human_size(total_size),
        "total_gain_bytes": total_gain,
        "total_gain_human": human_size(total_gain),
        "total_gain_percent": round((total_gain / total_size * 100) if total_size else 0, 1),
        "total_output_bytes": total_output,
        "total_output_human": human_size(total_output),
        "total_duration_sec": round(total_duration, 2),
        "total_duration_human": human_duration(total_duration),
        "already_av1_count": already_count,
    }
    return {"items": items, "packs": packs, "errors": errors, "summary": summary}


def resolve_item_files(scan: dict, item_ids: Iterable[str]) -> tuple[list[dict], list[dict]]:
    """Traduit les IDs d'items (fichiers/packs) en fiches de fichiers à encoder.

    Retourne (fichiers, avertissements). Les fichiers déjà AV1 ou en erreur
    sont ignorés avec un avertissement explicite.
    """
    by_id = {item["id"]: item for item in scan.get("items", [])}
    by_path = {entry["path"]: entry for entry in scan.get("files", [])}
    selected_files: dict[str, dict] = {}
    warnings: list[dict] = []

    for item_id in item_ids:
        item = by_id.get(item_id)
        if item is None:
            warnings.append({"item_id": item_id, "warning": "item inconnu dans ce scan"})
            continue
        paths = []
        if item["kind"] == "series":
            paths = [episode["path"] for episode in item.get("episodes", [])]
        else:
            paths = [item["path"]]
        for path in paths:
            entry = by_path.get(path)
            if entry is None:
                warnings.append({"path": path, "warning": "fichier absent du scan"})
                continue
            if entry.get("error"):
                warnings.append({"path": path, "warning": entry["error"]})
                continue
            if entry.get("already_av1"):
                warnings.append({"path": path, "warning": "déjà en AV1, ignoré"})
                continue
            selected_files[path] = entry
    return list(selected_files.values()), warnings


def resolve_item_paths(scan: dict, item_ids: Iterable[str]) -> tuple[list[str], list[dict]]:
    """Comme `resolve_item_files`, mais SANS filtrer AV1/erreurs.

    Utilisé par la suppression directe : on doit pouvoir supprimer un pack
    complet, un fichier déjà AV1 ou un fichier en erreur.
    """
    by_id = {item["id"]: item for item in scan.get("items", [])}
    by_path = {entry["path"]: entry for entry in scan.get("files", [])}
    paths: list[str] = []
    warnings: list[dict] = []
    for item_id in item_ids:
        item = by_id.get(item_id)
        if item is None:
            warnings.append({"item_id": item_id, "warning": "item inconnu dans ce scan"})
            continue
        if item["kind"] == "series":
            candidates = [episode["path"] for episode in item.get("episodes", [])]
        else:
            candidates = [item["path"]]
        for path in candidates:
            if path in by_path and path not in paths:
                paths.append(path)
            elif path not in by_path:
                warnings.append({"path": path, "warning": "fichier absent du scan"})
    return paths, warnings
