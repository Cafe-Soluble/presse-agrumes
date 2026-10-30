# syntax=docker/dockerfile:1.7
# =============================================================================
# Presse-Agrumes — image Docker
# =============================================================================
# Multi-stage : Node compile l'interface React, Python exécute le backend.
# L'image finale ne contient ni Node ni les sources frontend inutiles.
#
# Build local :
#   docker build -t presse-agrumes:local .
#   docker run --rm -p 8080:8080 \
#     -v "$PWD/config.toml:/app/config.toml:ro" \
#     -v "$PWD/data:/app/data" \
#     -v /mnt/media:/mnt/media \
#     presse-agrumes:local
#
# La configuration est exclusivement lue dans /app/config.toml.
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

ARG APP_VERSION=0.5.0
LABEL org.opencontainers.image.title="Presse-Agrumes" \
      org.opencontainers.image.description="Analyse et compression AV1 de bibliothèques vidéo" \
      org.opencontainers.image.source="https://github.com/Cafe-Soluble/presse-agrumes" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.licenses="MIT"

# ffmpeg/ffprobe pour l'analyse et l'encodage AV1 ; tini pour les signaux
# (indispensable pour que la pause/reprise et l'arrêt propre fonctionnent).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -Eq "libsvtav1|libaom-av1" \
    || (echo "ffmpeg sans encodeur AV1 dans l'image" >&2; exit 1)

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY presse_agrumes ./presse_agrumes
COPY --from=frontend /build/frontend/dist ./frontend/dist
COPY config.toml ./config.toml

# Utilisateur non-root. L'UID 1000 est le plus courant sur les NAS ; il peut
# être surchargé dans docker-compose (`user: "1026:100"` par exemple).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/data \
    && chown -R app:app /app \
    && chmod 600 /app/config.toml

USER app

# Le port réel vient de [server] port dans config.toml (8080 par défaut).
EXPOSE 8080
VOLUME ["/app/data"]
STOPSIGNAL SIGTERM

# /healthz est volontairement accessible sans authentification.
# Le healthcheck lit le port réel dans le fichier TOML monté.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import tomllib,urllib.request; c=tomllib.load(open('/app/config.toml','rb')); urllib.request.urlopen('http://127.0.0.1:%d/healthz' % int(c['server']['port']), timeout=3).read()"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "-m", "presse_agrumes", "--config", "/app/config.toml", "--strict-port"]
