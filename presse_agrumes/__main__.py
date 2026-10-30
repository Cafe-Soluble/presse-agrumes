"""Point d'entrée CLI : `python -m presse_agrumes`."""

from __future__ import annotations

import argparse
import socket

import uvicorn

from . import config
from .app import app


def _local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Presse-Agrumes — serveur web")
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--reload", action="store_true", help="rechargement dev")
    args = parser.parse_args()

    config.ensure_dirs()
    print("=" * 62)
    print(f"  🍊 Presse-Agrumes {config.VERSION}")
    print("=" * 62)
    print(f"  Interface : http://{_local_ip()}:{args.port}")
    print(f"  Local     : http://127.0.0.1:{args.port}")
    print(f"  Données   : {config.DATA_DIR}")
    print(f"  ffmpeg    : {config.ffmpeg_bin() or 'INTROUVABLE (installez ffmpeg)'}")
    print(f"  ffprobe   : {config.ffprobe_bin() or 'INTROUVABLE'}")
    if config.AUTH_ENABLED:
        print("  Auth      : HTTP Basic activée")
    print("=" * 62)
    uvicorn.run(
        "presse_agrumes.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
