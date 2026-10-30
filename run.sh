#!/usr/bin/env bash
# Démarrage de Presse-Agrumes (backend FastAPI + frontend compilé).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "→ Création de l'environnement Python .venv"
  "$PYTHON" -m venv .venv
fi

if ! .venv/bin/python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "→ Installation des dépendances Python"
  .venv/bin/pip install --upgrade pip >/dev/null
  .venv/bin/pip install -r requirements.txt
fi

if [ ! -f "frontend/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "→ Build du frontend React"
    (cd frontend && npm install --no-audit --no-fund && npm run build)
  else
    cat >&2 <<'MSG'
Le frontend compilé est absent (frontend/dist/index.html) et npm est introuvable.
Sur une machine avec Node 20+ :
    cd frontend && npm install && npm run build
Puis relancez ./run.sh. Le dossier frontend/dist peut aussi être copié depuis
une autre machine.
MSG
    exit 1
  fi
fi

if [ ! -f "config.toml" ]; then
  echo "⚠ config.toml introuvable. Il est normalement fourni avec le projet." >&2
  echo "  Restaurez-le depuis git ou lancez avec --config /chemin/vers/config.toml." >&2
fi

if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/ffmpeg" ]; then
  echo "⚠ ffmpeg introuvable. Installez-le ou renseignez [ffmpeg] dans config.toml." >&2
fi

exec .venv/bin/python -m presse_agrumes "$@"
