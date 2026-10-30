#!/usr/bin/env bash
# Développement : backend avec rechargement + Vite en proxy sur le port 5173.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "Lancez d'abord ./run.sh ou créez le venv (voir docs/DEVELOPMENT.md)." >&2
  exit 1
fi

cleanup() {
  kill 0 2>/dev/null || true
}
trap cleanup EXIT

PA_AUTH_DISABLED=1 .venv/bin/python -m presse_agrumes --host 127.0.0.1 --port 8080 --reload &
BACKEND_PID=$!

(
  cd frontend
  npm run dev -- --host 0.0.0.0 --port 5173
) &
FRONTEND_PID=$!

echo "Backend  : http://127.0.0.1:8080"
echo "Frontend : http://127.0.0.1:5173 (proxy /api vers le backend)"
wait "$BACKEND_PID" "$FRONTEND_PID"
