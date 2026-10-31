"""Configuration centrale de Presse-Agrumes.

**Toute la configuration est dans `config.toml`.** Aucune variable
d'environnement n'est utilisée par l'application. Le fichier est versionné avec
le projet ; en production, l'utilisateur doit y changer le mot de passe, les
racines autorisées et, si besoin, le port.

Le chemin du fichier peut être changé au lancement avec `--config` (utile pour
Docker ou un déploiement système) :

    python -m presse_agrumes --config /etc/presse-agrumes/config.toml

Structure du fichier (voir `config.toml` commenté à la racine) :

    [server]  host, port
    [paths]   data_dir, allowed_roots
    [auth]    user, password, disabled
    [ffmpeg]  ffmpeg, ffprobe (facultatif)
"""

from __future__ import annotations

import json
import os
import re
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
VERSION = "0.11.3"

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_FILE = BASE_DIR / "config.toml"
CONFIG_FILE = DEFAULT_CONFIG_FILE
CONFIG_FILE_EXISTS = False
FILE_CONFIG: dict[str, Any] = {}

DEFAULT_PASSWORD_VALUES = {"changez-moi", "change-me", "password", "motdepasse"}

# Valeurs par défaut (remplacées par _apply_config_file).
HOST = "0.0.0.0"
PORT = 8473
DATA_DIR = BASE_DIR / "data"
SCANS_DIR = DATA_DIR / "scans"
JOBS_DIR = DATA_DIR / "jobs"
TESTS_DIR = DATA_DIR / "tests"
CACHE_DIR = DATA_DIR / "cache"
ALLOWED_ROOTS: list[Path] = [Path("/")]
AUTH_DISABLED = False
AUTH_USER = "agrumes"
AUTH_PASSWORD = ""
AUTH_PASSWORD_SOURCE = "config"
AUTH_PASSWORD_IS_DEFAULT = False
AUTH_ENABLED = True


def read_config_file(path: Path) -> dict[str, Any]:
    """Lit un fichier TOML et renvoie son contenu (ou {} s'il est absent)."""
    if not path.is_file():
        return {}
    if tomllib is None:
        raise RuntimeError(
            "La lecture de config.toml nécessite TOML. "
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


def _cfg(section: str, key: str, default: Any = None) -> Any:
    value = FILE_CONFIG.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(key, default)


def _config_path(value: Any) -> Path:
    """Résout un chemin relatif au dossier qui contient config.toml."""
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = CONFIG_FILE.parent / path
    return path.resolve()


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _apply_config_file() -> None:
    """(Re)charge les valeurs globales depuis CONFIG_FILE."""
    global CONFIG_FILE_EXISTS, FILE_CONFIG
    global HOST, PORT, DATA_DIR, SCANS_DIR, JOBS_DIR, TESTS_DIR, CACHE_DIR
    global ALLOWED_ROOTS
    global AUTH_DISABLED, AUTH_USER, AUTH_PASSWORD, AUTH_PASSWORD_SOURCE
    global AUTH_PASSWORD_IS_DEFAULT, AUTH_ENABLED

    CONFIG_FILE_EXISTS = CONFIG_FILE.is_file()
    FILE_CONFIG = read_config_file(CONFIG_FILE)

    if not CONFIG_FILE_EXISTS:
        raise RuntimeError(
            f"Fichier de configuration introuvable : {CONFIG_FILE}\n"
            "Le fichier config.toml est fourni avec le projet. "
            "Créez-le ou lancez avec --config /chemin/vers/config.toml."
        )

    HOST = str(_cfg("server", "host", "0.0.0.0"))
    try:
        PORT = int(_cfg("server", "port", 8473))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Port invalide dans {CONFIG_FILE} : {exc}") from exc
    if not 0 < PORT < 65536:
        raise RuntimeError(f"Port invalide dans {CONFIG_FILE} : {PORT}")

    data_dir_value = _cfg("paths", "data_dir", "./data")
    DATA_DIR = _config_path(data_dir_value)
    SCANS_DIR = DATA_DIR / "scans"
    JOBS_DIR = DATA_DIR / "jobs"
    TESTS_DIR = DATA_DIR / "tests"
    CACHE_DIR = DATA_DIR / "cache"

    configured_roots = _cfg("paths", "allowed_roots", ["/"])
    if isinstance(configured_roots, str):
        root_values = configured_roots.split(os.pathsep)
    elif isinstance(configured_roots, (list, tuple)):
        root_values = list(configured_roots)
    else:
        root_values = ["/"]
    ALLOWED_ROOTS = [
        _config_path(value) for value in root_values if str(value).strip()
    ] or [Path("/")]

    AUTH_DISABLED = _as_bool(_cfg("auth", "disabled", False))
    AUTH_USER = str(_cfg("auth", "user", "agrumes")).strip() or "agrumes"
    password = _cfg("auth", "password")
    password = str(password).strip() if password is not None else ""

    if AUTH_DISABLED:
        AUTH_PASSWORD = ""
        AUTH_PASSWORD_SOURCE = "disabled"
        AUTH_PASSWORD_IS_DEFAULT = False
        AUTH_ENABLED = False
    elif password:
        AUTH_PASSWORD = password
        AUTH_PASSWORD_SOURCE = "config"
        AUTH_PASSWORD_IS_DEFAULT = password.lower() in DEFAULT_PASSWORD_VALUES
        AUTH_ENABLED = True
    else:
        raise RuntimeError(
            f"Aucun mot de passe défini dans {CONFIG_FILE}.\n"
            "Renseignez [auth] password, ou mettez disabled = true pour le "
            "développement local."
        )


def apply_config_file(path: str | Path) -> None:
    """Charge un autre fichier de configuration (option --config, tests)."""
    global CONFIG_FILE
    CONFIG_FILE = Path(path).expanduser().resolve()
    _apply_config_file()


def update_password(new_password: str) -> None:
    """Met à jour ``[auth] password`` dans CONFIG_FILE.

    Réécrit uniquement la ligne du mot de passe pour conserver les commentaires
    et les autres réglages. Les permissions d'origine sont conservées (600 par
    défaut). Met aussi à jour l'état en mémoire, sans redémarrage.
    """
    global AUTH_PASSWORD, AUTH_PASSWORD_SOURCE, AUTH_PASSWORD_IS_DEFAULT

    if not new_password or "\n" in new_password or "\r" in new_password:
        raise ValueError("Mot de passe invalide.")

    path = CONFIG_FILE
    try:
        text = path.read_text(encoding="utf-8")
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise RuntimeError(f"Impossible de lire {path} : {exc}") from exc

    lines = text.splitlines(keepends=True)
    in_auth = False
    auth_header_index: int | None = None
    replaced = False
    output: list[str] = []

    password_re = re.compile(r"^(\s*)password\s*=\s*(?:\"[^\"]*\"|'[^']*')\s*$")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_auth = stripped == "[auth]"
            if in_auth and auth_header_index is None:
                auth_header_index = len(output)
        if in_auth and not replaced and password_re.match(line.rstrip("\n")):
            indent = password_re.match(line.rstrip("\n")).group(1)  # type: ignore[union-attr]
            output.append(f"{indent}password = {json.dumps(new_password, ensure_ascii=False)}\n")
            replaced = True
        else:
            output.append(line)

    if not replaced:
        value = f'password = {json.dumps(new_password, ensure_ascii=False)}\n'
        if auth_header_index is None:
            output.append(f'\n[auth]\nuser = "{AUTH_USER}"\n{value}')
        else:
            output.insert(auth_header_index + 1, value)

    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text("".join(output), encoding="utf-8")
        os.chmod(tmp, mode or 0o600)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Impossible d'écrire {path} : {exc}") from exc

    AUTH_PASSWORD = new_password
    AUTH_PASSWORD_SOURCE = "config"
    AUTH_PASSWORD_IS_DEFAULT = new_password.lower() in DEFAULT_PASSWORD_VALUES


def ensure_dirs() -> None:
    for directory in (DATA_DIR, SCANS_DIR, JOBS_DIR, TESTS_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _find_binary(name: str, config_key: str) -> str | None:
    """Cherche un binaire dans config.toml, le PATH puis les emplacements usuels."""
    configured = _cfg("ffmpeg", config_key)
    if configured:
        explicit = _config_path(configured)
        return str(explicit) if explicit.is_file() else None
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
    return _find_binary("ffmpeg", "ffmpeg")


def ffprobe_bin() -> str | None:
    return _find_binary("ffprobe", "ffprobe")


# Chargement initial (le fichier versionné existe normalement déjà).
_apply_config_file()
