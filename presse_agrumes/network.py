"""Détection de ports libres et d'adresses IP locales.

Utilisé au démarrage pour éviter un conflit si le port préféré (8473 par
défaut) est déjà occupé par une autre application du NAS.
"""

from __future__ import annotations

import socket


def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    if not 0 < port < 65536:
        return False
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    bind_host = host or "0.0.0.0"
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
            return True
        except OSError:
            return False


def find_available_port(
    preferred: int,
    host: str = "0.0.0.0",
    max_tries: int = 100,
) -> int:
    """Renvoie le premier port libre à partir de `preferred`.

    Le scan est séquentiel (8473, 8474, …) pour rester prévisible.
    """
    for offset in range(max_tries):
        port = preferred + offset
        if port > 65535:
            break
        if is_port_available(port, host):
            return port
    raise RuntimeError(
        f"Aucun port libre trouvé entre {preferred} et {preferred + max_tries - 1}."
    )


def local_ip_addresses() -> list[str]:
    """Adresses IPv4 non-loopback de la machine, la plus probable d'abord."""
    addresses: list[str] = []

    def add(value: str | None) -> None:
        if not value:
            return
        value = value.split("%", 1)[0]
        if value.startswith("127.") or value == "0.0.0.0":
            return
        if value not in addresses:
            addresses.append(value)

    # Méthode UDP : ne contacte rien, mais demande à l'OS quelle interface
    # serait utilisée pour sortir. C'est l'adresse la plus utile à afficher.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass

    # Énumération des interfaces (Linux) : permet notamment de voir l'adresse
    # Tailscale/WireGuard, que getaddrinfo ne renvoie pas toujours.
    try:
        import fcntl
        import struct

        for _index, name in socket.if_nameindex():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    packed = fcntl.ioctl(
                        sock.fileno(),
                        0x8915,  # SIOCGIFADDR
                        struct.pack("256s", name[:15].encode("utf-8")),
                    )
                    add(socket.inet_ntoa(packed[20:24]))
            except OSError:
                continue
    except (ImportError, OSError):
        pass

    return addresses


def primary_local_ip() -> str:
    addresses = local_ip_addresses()
    return addresses[0] if addresses else "127.0.0.1"
