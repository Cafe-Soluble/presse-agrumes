"""Configuration centrale de Presse-Agrumes.

Tout est surchargeable par variables d'environnement, ce qui permet de
déployer l'application sur un NAS sans modifier le code.

Variables utiles :
    PA_HOST              adresse d'écoute (défaut 0.0.0.0)
    PA_PORT              port (défaut 8080)
    PA_DATA_DIR          dossier de données (défaut <projet>/data)
    PA_ALLOWED_ROOTS     racines autorisées, séparées par ':' (défaut '/')
    PA_AUTH_USER         active l'authentification HTTP Basic si défini
    PA_AUTH_PASSWORD     mot de passe HTTP Basic
    FFMPEG_BIN           chemin explicite vers ffmpeg
    FFPROBE_BIN          chemin explicite vers ffprobe
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "Presse-Agrumes"
VERSION = "0.1.0"

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = _env_path("PA_DATA_DIR", BASE_DIR / "data")
SCANS_DIR = DATA_DIR / "scans"
JOBS_DIR = DATA_DIR / "jobs"
TESTS_DIR = DATA_DIR / "tests"
CACHE_DIR = DATA_DIR / "cache"

HOST = os.environ.get("PA_HOST", "0.0.0.0")
PORT = int(os.environ.get("PA_PORT", "8080"))

# Racines auxquelles l'interface est autorisée à accéder. Sur un NAS on peut
# restreindre à /srv, /mnt, /media, /volume1... La valeur par défaut laisse
# tout le système accessible : l'outil est prévu pour un réseau local de
# confiance, jamais pour être exposé sur Internet.
_allowed_raw = os.environ.get("PA_ALLOWED_ROOTS", "/")
ALLOWED_ROOTS = [
    Path(p).expanduser().resolve()
    for p in _allowed_raw.split(os.pathsep)
    if p.strip()
]


def _find_binary(name: str, env_var: str) -> str | None:
    """Cherche un binaire dans l'env, le PATH puis les emplacements usuels.

    On privilégie shutil.which() pour respecter le PATH, mais on ajoute des
    emplacements classiques (dont ~/.local/bin utilisé par le build statique
    de développement) car un service systemd démarre avec un PATH minimal.
    """
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit if Path(explicit).is_file() else None
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path.home() / ".local/bin" / name,
        Path("/usr/local/bin") / name,
        Path("/usr/bin") / name,
        Path("/opt/ffmpeg/bin") / name,
        Path("/opt/homebrew/bin") / name,
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def ffmpeg_bin() -> str | None:
    return _find_binary("ffmpeg", "FFMPEG_BIN")


def ffprobe_bin() -> str | None:
    return _find_binary("ffprobe", "FFPROBE_BIN")


def ensure_dirs() -> None:
    for directory in (DATA_DIR, SCANS_DIR, JOBS_DIR, TESTS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


AUTH_USER = os.environ.get("PA_AUTH_USER", "").strip()
AUTH_PASSWORD = os.environ.get("PA_AUTH_PASSWORD", "").strip()
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASSWORD)
