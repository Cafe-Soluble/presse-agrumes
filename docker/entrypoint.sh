#!/bin/sh
# =============================================================================
# Entrypoint Docker de Presse-Agrumes
# =============================================================================
# Au premier démarrage, crée /data/config.toml dans le volume persistant avec :
#   - un mot de passe aléatoire affiché dans les logs ;
#   - data_dir = /data ;
#   - allowed_roots = montages courants (/media, /mnt, /srv, /volume1...) ;
#     l'assistant de premier démarrage permet de choisir le dossier exact
#     dans l'interface.
#
# Aux démarrages suivants, réutilise le fichier existant. Pour changer le mot
# de passe ou les dossiers autorisés : éditez /data/config.toml sur l'hôte
# (volume ./data ou volume nommé) puis redémarrez le conteneur.
#
# Aucune variable d'environnement n'est utilisée.
# =============================================================================
set -eu

DATA_ROOT=/data
CONFIG_FILE="$DATA_ROOT/config.toml"

mkdir -p "$DATA_ROOT"
if [ ! -w "$DATA_ROOT" ]; then
  echo "ERREUR : $DATA_ROOT n'est pas inscriptible par l'utilisateur du conteneur." >&2
  echo "Vérifiez le propriétaire du volume (UID/GID via 'user:' dans Compose)." >&2
  exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
  PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
  umask 077
  cat > "$CONFIG_FILE" <<EOF
# Généré automatiquement au premier démarrage.
# Modifiez ce fichier puis redémarrez le conteneur.
# Il est stocké dans le volume /data (persistant).

[server]
host = "0.0.0.0"
port = 8473

[paths]
data_dir = "/data"
# Montages courants : l'assistant de premier démarrage permet de choisir le
# dossier exact dans l'interface. Montez votre partage sur /media, /mnt,
# /volume1... (voir la documentation).
allowed_roots = ["/media", "/mnt", "/srv", "/volume1", "/volume2"]

[auth]
user = "agrumes"
password = "$PASSWORD"
disabled = false

[ffmpeg]
# Détection automatique de ffmpeg/ffprobe dans l'image.
EOF
  chmod 600 "$CONFIG_FILE"
  echo "=============================================================="
  echo "  🍊 Presse-Agrumes — première configuration"
  echo "=============================================================="
  echo "  Configuration : $CONFIG_FILE  (volume /data)"
  echo "  Médias        : /media (montez votre partage ici)"
  echo "  Utilisateur   : agrumes"
  echo "  Mot de passe  : $PASSWORD"
  echo ""
  echo "  Notez ce mot de passe. Pour le modifier :"
  echo "    éditez /data/config.toml sur l'hôte, puis redémarrez."
  echo "=============================================================="
fi

exec python3 -u -m presse_agrumes \
  --config "$CONFIG_FILE" --strict-port
