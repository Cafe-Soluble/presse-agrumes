"""Point d'entrée CLI : `python -m presse_agrumes`.

Toute la configuration vient de `config.toml` (ou du fichier passé à
`--config`). Au démarrage :
- charge le fichier de configuration ;
- cherche un port libre à partir du port configuré ;
- affiche l'URL, le port, les IP locales et la source du mot de passe.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from . import config
from .network import (
    find_available_port,
    is_port_available,
    local_ip_addresses,
    primary_local_ip,
)


def _print_banner(port: int, requested_port: int, host: str) -> None:
    line = "=" * 66
    print(line)
    print(f"  🍊 Presse-Agrumes v{config.VERSION}")
    print(line)
    print(f"  Configuration      : {config.CONFIG_FILE}")
    print(f"  Données            : {config.DATA_DIR}")
    print(f"  ffmpeg             : {config.ffmpeg_bin() or 'INTROUVABLE (installez ffmpeg)'}")
    print(f"  ffprobe            : {config.ffprobe_bin() or 'INTROUVABLE'}")
    if requested_port != port:
        print(f"  Port               : {port}  (le port {requested_port} était occupé)")
    else:
        print(f"  Port               : {port}")

    if host in {"0.0.0.0", "::", ""}:
        addresses = local_ip_addresses()
        if not addresses:
            addresses = [primary_local_ip()]
        print("  Adresse(s) locale(s) :")
        for address in addresses:
            print(f"    http://{address}:{port}")
        print(f"    http://127.0.0.1:{port}  (local uniquement)")
    else:
        print(f"  Adresse            : http://{host}:{port}")

    if config.AUTH_ENABLED:
        print("  Authentification   : HTTP Basic")
        print(f"  Utilisateur        : {config.AUTH_USER}")
        print(f"  Mot de passe       : défini dans {config.CONFIG_FILE}")
        if config.AUTH_PASSWORD_IS_DEFAULT:
            print(
                "                       ⚠ MOT DE PASSE PAR DÉFAUT : "
                "modifiez [auth] password dans config.toml."
            )
        try:
            mode = config.CONFIG_FILE.stat().st_mode & 0o777
            if mode & 0o077:
                print(
                    "                       ⚠ fichier lisible par d'autres : "
                    f"chmod 600 {config.CONFIG_FILE}"
                )
        except OSError:
            pass
    else:
        print("  Authentification   : DÉSACTIVÉE ([auth] disabled = true)")
        print("                       ⚠ Interface accessible sans mot de passe.")
    print(line)
    print("  Ouvrez l'adresse ci-dessus dans votre navigateur.")
    print("  Ctrl+C pour arrêter le serveur.")
    print(line, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Presse-Agrumes - serveur web")
    parser.add_argument(
        "--config",
        default=None,
        help="Chemin du fichier TOML (défaut : config.toml à la racine du projet).",
    )
    parser.add_argument("--reload", action="store_true", help="rechargement dev")
    parser.add_argument(
        "--strict-port", action="store_true",
        help="échouer si le port configuré est occupé au lieu d'en chercher un autre",
    )
    args = parser.parse_args()

    if args.config:
        if args.reload:
            parser.error("--config n'est pas compatible avec --reload.")
        try:
            config.apply_config_file(args.config)
        except RuntimeError as exc:
            print(f"Erreur de configuration : {exc}", file=sys.stderr)
            sys.exit(1)

    config.ensure_dirs()
    requested_port = config.PORT
    host = config.HOST

    try:
        if args.strict_port:
            if not is_port_available(requested_port, host):
                print(
                    f"Erreur : le port {requested_port} est déjà occupé "
                    "(--strict-port).",
                    file=sys.stderr,
                )
                sys.exit(1)
            port = requested_port
        else:
            port = find_available_port(requested_port, host)
    except RuntimeError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)

    _print_banner(port, requested_port, host)
    uvicorn.run(
        "presse_agrumes.app:app",
        host=host,
        port=port,
        reload=args.reload,
        reload_dirs=["presse_agrumes"] if args.reload else None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
