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
  CURRENT_UID=$(id -u)
  CURRENT_GID=$(id -g)
  echo "ERREUR : $DATA_ROOT n'est pas inscriptible par l'utilisateur du conteneur (UID $CURRENT_UID)." >&2
  echo "Sur l'hôte, corrigez le propriétaire du dossier monté, par exemple :" >&2
  echo "  sudo chown -R $CURRENT_UID:$CURRENT_GID ./data" >&2
  echo "ou adaptez 'user:' dans docker-compose.yml à l'UID/GID qui possède ./data." >&2
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
  echo "  Racines autorisées : /media  /mnt  /srv  /volume1  /volume2"
  echo "  Montez votre partage média sur l'une de ces racines, puis"
  echo "  choisissez le dossier exact dans l'interface (assistant)."
  echo "  Utilisateur   : agrumes"
  echo "  Mot de passe  : $PASSWORD"
  echo ""
  echo "  Accès web     : http://<IP-du-NAS>:8473"
  echo "                  (remplacez <IP-du-NAS> par l'adresse du NAS,"
  echo "                   par exemple http://192.168.1.20:8473)"
  echo ""
  echo "  Notez ce mot de passe. Pour le modifier :"
  echo "    éditez /data/config.toml sur l'hôte, puis redémarrez."
  echo "=============================================================="
fi

exec python3 -u -m presse_agrumes \
  --config "$CONFIG_FILE" --strict-port
