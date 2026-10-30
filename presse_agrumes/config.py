"""Configuration centrale de Presse-Agrumes.

Un fichier TOML est lu au démarrage (par défaut `<projet>/config.toml`, ou le
chemin indiqué par `PA_CONFIG_FILE`). Les variables d'environnement restent
supportées et ont priorité sur le fichier, ce qui permet de surcharger un
déploiement sans modifier la configuration.

Exemple de fichier : `config.example.toml`.

Variables d'environnement prioritaires :
    PA_CONFIG_FILE       chemin du fichier TOML
    PA_HOST              adresse d'écoute
    PA_PORT              port préféré
    PA_DATA_DIR          dossier de données
    PA_ALLOWED_ROOTS     racines autorisées, séparées par ':'
    PA_AUTH_USER         utilisateur HTTP Basic
    PA_AUTH_PASSWORD     mot de passe HTTP Basic
    PA_AUTH_DISABLED     "1" pour désactiver l'authentification
    FFMPEG_BIN           chemin explicite vers ffmpeg
    FFPROBE_BIN          chemin explicite vers ffprobe
"""

from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

APP_NAME = "Presse-Agrumes"
VERSION = "0.3.0"

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(
    os.environ.get("PA_CONFIG_FILE", str(BASE_DIR / "config.toml"))
).expanduser().resolve()


def read_config_file(path: Path) -> dict[str, Any]:
    """Lit un fichier TOML et renvoie son contenu (ou {} s'il est absent)."""
    if not path.is_file():
        return {}
    if tomllib is None:
        raise RuntimeError(
            "Le fichier de configuration nécessite TOML. "
            "Installez 'tomli' (Python < 3.11) ou utilisez Python 3.11+."
        )
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Configuration invalide dans {path} : {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Configuration invalide dans {path} : objet TOML attendu.")
    return data


FILE_CONFIG = read_config_file(CONFIG_FILE)
CONFIG_FILE_EXISTS = CONFIG_FILE.is_file()


def _cfg(section: str, key: str, default: Any = None) -> Any:
    value = FILE_CONFIG.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _env_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _config_path(value: Any) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = CONFIG_FILE.parent / path
    return path.resolve()


def _resolve_data_path(env_name: str, config_value: Any, default: Path) -> Path:
    env = _env_value(env_name)
    if env:
        return Path(env).expanduser().resolve()
    if config_value:
        return _config_path(config_value)
    return default


HOST = _env_value("PA_HOST") or str(_cfg("server", "host", "0.0.0.0"))
try:
    PORT = int(_env_value("PA_PORT") or _cfg("server", "port", 8080))
except (TypeError, ValueError) as exc:
    raise RuntimeError(f"Port invalide dans la configuration : {exc}") from exc
if not 0 < PORT < 65536:
    raise RuntimeError(f"Port invalide dans la configuration : {PORT}")

DATA_DIR = _resolve_data_path(
    "PA_DATA_DIR", _cfg("paths", "data_dir"), BASE_DIR / "data"
)
SCANS_DIR = DATA_DIR / "scans"
JOBS_DIR = DATA_DIR / "jobs"
TESTS_DIR = DATA_DIR / "tests"
CACHE_DIR = DATA_DIR / "cache"

# Racines auxquelles l'interface est autorisée à accéder. Sur un NAS on peut
# restreindre à /srv, /mnt, /media, /volume1... La valeur par défaut laisse
# tout le système accessible : l'outil est prévu pour un réseau local de
# confiance, jamais pour être exposé sur Internet.
_env_roots = _env_value("PA_ALLOWED_ROOTS")
if _env_roots:
    _allowed_values: list[Any] = _env_roots.split(os.pathsep)
else:
    _configured_roots = _cfg("paths", "allowed_roots", ["/"])
    if isinstance(_configured_roots, str):
        _allowed_values = [part for part in _configured_roots.split(os.pathsep)]
    elif isinstance(_configured_roots, (list, tuple)):
        _allowed_values = list(_configured_roots)
    else:
        _allowed_values = ["/"]
ALLOWED_ROOTS = [
    _config_path(value)
    for value in _allowed_values
    if str(value).strip()
]
if not ALLOWED_ROOTS:
    ALLOWED_ROOTS = [Path("/")]


def _find_binary(name: str, env_var: str, config_key: str) -> str | None:
    """Cherche un binaire dans l'env, le fichier, le PATH puis les emplacements usuels.

    On privilégie shutil.which() pour respecter le PATH, mais on ajoute des
    emplacements classiques (dont ~/.local/bin utilisé par le build statique
    de développement) car un service systemd démarre avec un PATH minimal.
    """
    explicit = _env_value(env_var)
    if not explicit:
        configured = _cfg("ffmpeg", config_key)
        if configured:
            explicit = str(_config_path(configured))
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
    return _find_binary("ffmpeg", "FFMPEG_BIN", "ffmpeg")


def ffprobe_bin() -> str | None:
    return _find_binary("ffprobe", "FFPROBE_BIN", "ffprobe")


def ensure_dirs() -> None:
    for directory in (DATA_DIR, SCANS_DIR, JOBS_DIR, TESTS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

_env_disabled = _env_value("PA_AUTH_DISABLED")
if _env_disabled is not None:
    AUTH_DISABLED = _as_bool(_env_disabled)
else:
    AUTH_DISABLED = _as_bool(_cfg("auth", "disabled", False))

AUTH_USER = (
    _env_value("PA_AUTH_USER")
    or str(_cfg("auth", "user", "agrumes"))
).strip() or "agrumes"

_env_password = _env_value("PA_AUTH_PASSWORD")
_config_password = _cfg("auth", "password")
if _config_password is not None:
    _config_password = str(_config_password).strip() or None

AUTH_PASSWORD_GENERATED = False
if AUTH_DISABLED:
    AUTH_PASSWORD = ""
    AUTH_PASSWORD_SOURCE = "disabled"
elif _env_password:
    AUTH_PASSWORD = _env_password
    AUTH_PASSWORD_SOURCE = "environment"
elif _config_password:
    AUTH_PASSWORD = _config_password
    AUTH_PASSWORD_SOURCE = "config"
else:
    # Mot de passe temporaire propre à chaque lancement. Il est affiché dans
    # la console par __main__ et transmis aux sous-processus uvicorn --reload.
    AUTH_PASSWORD = secrets.token_hex(8)  # 16 caractères hexadécimaux
    AUTH_PASSWORD_GENERATED = True
    AUTH_PASSWORD_SOURCE = "generated"

AUTH_ENABLED = not AUTH_DISABLED and bool(AUTH_USER and AUTH_PASSWORD)
