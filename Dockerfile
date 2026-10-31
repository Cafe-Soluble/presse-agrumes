# syntax=docker/dockerfile:1.7
# =============================================================================
# Presse-Agrumes - image Docker
# =============================================================================
# Multi-stage : Node compile l'interface React, Python exécute le backend.
# L'image finale ne contient ni Node ni les sources frontend inutiles.
#
# Build local :
#   docker build -t presse-agrumes:local .
#   docker run --rm -p 8473:8473 \
#     -v /mnt/media:/media \
#     -v presse-agrumes:/data \
#     presse-agrumes:local
#
# Au premier démarrage, /data/config.toml est créé automatiquement dans le
# volume persistant avec un mot de passe aléatoire affiché dans les logs.
# =============================================================================

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13

FROM node:${NODE_VERSION}-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ARG APP_VERSION=0.11.2
LABEL org.opencontainers.image.title="Presse-Agrumes" \
      org.opencontainers.image.description="Analyse et compression AV1 de bibliothèques vidéo" \
      org.opencontainers.image.source="https://github.com/Cafe-Soluble/presse-agrumes" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="MIT"

# ffmpeg/ffprobe pour l'analyse et l'encodage AV1 ; tini pour les signaux
# (indispensable pour que la pause/reprise et l'arrêt propre fonctionnent).
# ffmpeg/ffprobe, tini, et le support VAAPI : vainfo pour le diagnostic et les
# pilotes userspace pour que /dev/dri soit réellement exploitable dans le
# conteneur. Le pilote Intel non-free est amd64 uniquement.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg tini ca-certificates vainfo libva2 libva-drm2 mesa-va-drivers \
    && if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
         sed -i 's/^Components: main$/Components: main contrib non-free non-free-firmware/' \
           /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
         apt-get update; \
         apt-get install -y --no-install-recommends intel-media-va-driver-non-free \
           || apt-get install -y --no-install-recommends i965-va-driver || true; \
       fi \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -Eq "libsvtav1|libaom-av1" \
    || (echo "ffmpeg sans encodeur AV1 dans l'image" >&2; exit 1)

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY presse_agrumes ./presse_agrumes
COPY --from=frontend /build/frontend/dist ./frontend/dist
COPY config.toml ./config.toml
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Utilisateur non-root. L'UID 1000 est le plus courant sur les NAS ; il peut
# être surchargé dans docker-compose (`user: "1026:100"` par exemple).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app /data \
    && chmod 600 /app/config.toml \
    && chmod 755 /usr/local/bin/entrypoint.sh

USER app

# Le port réel vient de [server] port dans /data/config.toml (8473 par défaut).
EXPOSE 8473
VOLUME ["/data"]
STOPSIGNAL SIGTERM

# /healthz est volontairement accessible sans authentification.
# Le healthcheck lit le port réel dans la configuration persistante.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import tomllib,urllib.request; c=tomllib.load(open('/data/config.toml','rb')); urllib.request.urlopen('http://127.0.0.1:%d/healthz' % int(c['server']['port']), timeout=3).read()"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
