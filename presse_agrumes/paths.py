"""Gestion sûre des chemins et navigation dans le système de fichiers.

L'application écrit et supprime des fichiers : chaque chemin fourni par
l'utilisateur passe par `guard_path()` qui vérifie qu'il est bien dans une
racine autorisée (`PA_ALLOWED_ROOTS`) et qu'il ne contient pas d'octet NUL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from . import config
from .media import VIDEO_EXTENSIONS


class PathError(ValueError):
    pass


def resolve_path(raw: str | Path, *, must_exist: bool = False) -> Path:
    if raw is None or str(raw).strip() == "":
        raise PathError("Chemin vide.")
    if "\x00" in str(raw):
        raise PathError("Chemin invalide.")
    path = Path(raw).expanduser()
    try:
        path = path.resolve(strict=must_exist)
    except OSError as exc:
        raise PathError(f"Chemin inaccessible : {exc}") from exc
    return path


def _is_allowed(path: Path) -> bool:
    for root in config.ALLOWED_ROOTS:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def guard_path(raw: str | Path, *, must_exist: bool = False) -> Path:
    path = resolve_path(raw, must_exist=must_exist)
    if not _is_allowed(path):
        allowed = ", ".join(str(r) for r in config.ALLOWED_ROOTS)
        raise PathError(
            f"Accès refusé à {path} : hors des racines autorisées ({allowed})."
        )
    return path


def is_readable(path: Path) -> bool:
    try:
        return path.exists() and os.access(path, os.R_OK)
    except OSError:
        return False


def is_writable_dir(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK | os.X_OK)
    except OSError:
        return False


def ensure_writable_dir(path: Path) -> None:
    """Crée le dossier si nécessaire puis vérifie qu'on peut y écrire."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathError(f"Impossible de créer {path} : {exc}") from exc
    if not is_writable_dir(path):
        raise PathError(f"Dossier non accessible en écriture : {path}")


def describe_permissions(path: Path) -> dict:
    """Retourne un état lisible par l'interface, sans lever d'exception."""
    result = {
        "path": str(path),
        "exists": False,
        "is_dir": False,
        "readable": False,
        "writable": False,
        "executable": False,
    }
    try:
        stat = path.stat()
        result.update(
            exists=True,
            is_dir=path.is_dir(),
            readable=os.access(path, os.R_OK),
            writable=os.access(path, os.W_OK),
            executable=os.access(path, os.X_OK),
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
        )
        if path.is_dir():
            result["writable"] = os.access(path, os.W_OK | os.X_OK)
    except OSError as exc:
        result["error"] = str(exc)
    return result


def _entry(path: Path) -> dict:
    info = describe_permissions(path)
    info["name"] = path.name or str(path)
    try:
        info["is_symlink"] = path.is_symlink()
    except OSError:
        info["is_symlink"] = False
    return info


def browse(raw: str, *, show_files: bool = False) -> dict:
    """Liste les sous-dossiers (et éventuellement vidéos) d'un répertoire."""
    path = guard_path(raw, must_exist=True)
    if not path.is_dir():
        raise PathError(f"{path} n'est pas un dossier.")
    if not is_readable(path):
        raise PathError(f"Dossier non lisible (permissions) : {path}")

    directories: list[dict] = []
    videos: list[dict] = []
    errors: list[str] = []
    try:
        with os.scandir(path) as iterator:
            for item in iterator:
                try:
                    is_dir = item.is_dir(follow_symlinks=False)
                    is_file = item.is_file(follow_symlinks=False)
                    if item.is_symlink():
                        # On affiche les liens mais on ne suit pas les dossiers
                        # pour éviter les boucles infinies lors du scan.
                        try:
                            target_is_dir = Path(item.path).is_dir()
                        except OSError:
                            target_is_dir = False
                        if target_is_dir:
                            directories.append(_entry(Path(item.path)))
                        continue
                    if is_dir:
                        directories.append(_entry(Path(item.path)))
                    elif is_file and show_files:
                        entry_path = Path(item.path)
                        if entry_path.suffix.lower() in VIDEO_EXTENSIONS:
                            videos.append(_entry(entry_path))
                except OSError as exc:
                    errors.append(f"{item.name}: {exc}")
    except PermissionError as exc:
        raise PathError(f"Dossier non lisible (permissions) : {exc}") from exc
    except OSError as exc:
        raise PathError(f"Impossible de lire {path} : {exc}") from exc

    directories.sort(key=lambda e: e["name"].lower())
    videos.sort(key=lambda e: e["name"].lower())
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "name": path.name or str(path),
        "directories": directories,
        "videos": videos,
        "errors": errors,
        "permissions": describe_permissions(path),
        "breadcrumbs": _breadcrumbs(path),
    }


def _breadcrumbs(path: Path) -> list[dict]:
    crumbs = []
    current = path
    while True:
        crumbs.append({"name": current.name or str(current), "path": str(current)})
        if current.parent == current:
            break
        current = current.parent
    return list(reversed(crumbs))


def common_roots() -> list[dict]:
    """Racines pratiques proposées dans l'interface (montages NAS, home...)."""
    candidates: list[Path] = [Path.home()]
    for name in ("/mnt", "/media", "/srv", "/volume1", "/volume2", "/data", "/"):
        candidates.append(Path(name))
    # Montages détectés dans /proc/mounts (utile sur OMV/Unraid/Synology).
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                mount = parts[1].replace("\\040", " ")
                if any(mount.startswith(prefix) for prefix in ("/mnt", "/media", "/srv", "/volume")):
                    candidates.append(Path(mount))
    except OSError:
        pass

    seen = set()
    roots = []
    for path in candidates:
        try:
            resolved = path.resolve()
            key = str(resolved)
            if key in seen or not resolved.exists():
                continue
            seen.add(key)
            if not _is_allowed(resolved):
                continue
            roots.append(
                {
                    "path": key,
                    "name": resolved.name or key,
                    "readable": is_readable(resolved),
                    "writable": is_writable_dir(resolved),
                }
            )
        except OSError:
            continue
    return roots


def is_under(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False
