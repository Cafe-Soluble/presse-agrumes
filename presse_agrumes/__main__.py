"""Point d'entrée CLI : `python -m presse_agrumes`.

Au démarrage :
- génère un mot de passe temporaire si aucun n'est fourni ;
- cherche un port libre à partir du port demandé (8080 par défaut) ;
- affiche l'URL, le port, les IP locales et le mot de passe en console.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from . import config
from .app import app  # noqa: F401  (importé pour charger l'application)
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
        if config.AUTH_PASSWORD_GENERATED:
            print(f"  Mot de passe       : {config.AUTH_PASSWORD}")
            print("                       (temporaire, régénéré à chaque démarrage)")
        else:
            print("  Mot de passe       : défini via PA_AUTH_PASSWORD")
    else:
        print("  Authentification   : DÉSACTIVÉE (PA_AUTH_DISABLED=1)")
        print("                       ⚠ Interface accessible sans mot de passe.")
    print(line)
    print("  Ouvrez l'adresse ci-dessus dans votre navigateur.")
    print("  Ctrl+C pour arrêter le serveur.")
    print(line, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Presse-Agrumes — serveur web")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument(
        "--port", type=int, default=None,
        help=f"Port préféré (défaut : {config.PORT}). Un port libre est cherché si occupé.",
    )
    parser.add_argument("--reload", action="store_true", help="rechargement dev")
    parser.add_argument(
        "--strict-port", action="store_true",
        help="échouer si le port demandé est occupé au lieu d'en chercher un autre",
    )
    args = parser.parse_args()

    config.ensure_dirs()
    requested_port = args.port if args.port is not None else config.PORT
    if not 0 < requested_port < 65536:
        print(f"Erreur : port invalide ({requested_port}).", file=sys.stderr)
        sys.exit(2)

    try:
        if args.strict_port:
            if not is_port_available(requested_port, args.host):
                print(
                    f"Erreur : le port {requested_port} est déjà occupé "
                    "(--strict-port).",
                    file=sys.stderr,
                )
                sys.exit(1)
            port = requested_port
        else:
            port = find_available_port(requested_port, args.host)
    except RuntimeError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)

    # Le mot de passe généré doit être partagé avec le processus de reload
    # d'uvicorn, sinon le parent afficherait un mot de passe et le fils en
    # utiliserait un autre.
    if config.AUTH_PASSWORD_GENERATED:
        os.environ["PA_AUTH_USER"] = config.AUTH_USER
        os.environ["PA_AUTH_PASSWORD"] = config.AUTH_PASSWORD

    _print_banner(port, requested_port, args.host)
    uvicorn.run(
        "presse_agrumes.app:app",
        host=args.host,
        port=port,
        reload=args.reload,
        reload_dirs=["presse_agrumes"] if args.reload else None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
