#!/usr/bin/env bash
# Crée un tag de release après vérifications. Usage : scripts/release.sh 0.3.0
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1#v}"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?$ ]]; then
  echo "Usage : scripts/release.sh X.Y.Z (reçu : ${1:-vide})" >&2
  exit 2
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Le dépôt n'est pas propre. Committez ou nettoyez avant de taguer." >&2
  git status --short >&2
  exit 1
fi

if git rev-parse "v$VERSION" >/dev/null 2>&1; then
  echo "Le tag v$VERSION existe déjà." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Environnement .venv absent. Lancez ./run.sh ou créez le venv." >&2
  exit 1
fi

PY_VERSION=$(.venv/bin/python -c "from presse_agrumes import __version__; print(__version__)")
CFG_VERSION=$(.venv/bin/python -c "from presse_agrumes import config; print(config.VERSION)")
PYPROJECT_VERSION=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
FRONTEND_VERSION=$(cd frontend && node -p "require('./package.json').version")
DOCKER_VERSION=$(grep -m1 '^ARG APP_VERSION=' Dockerfile | cut -d= -f2)

if [ "$VERSION" != "$PY_VERSION" ] || [ "$VERSION" != "$CFG_VERSION" ] \
   || [ "$VERSION" != "$PYPROJECT_VERSION" ] || [ "$VERSION" != "$FRONTEND_VERSION" ] \
   || [ "$VERSION" != "$DOCKER_VERSION" ]; then
  echo "Versions incohérentes :" >&2
  echo "  demandée   : $VERSION" >&2
  echo "  __version__: $PY_VERSION" >&2
  echo "  config     : $CFG_VERSION" >&2
  echo "  pyproject  : $PYPROJECT_VERSION" >&2
  echo "  frontend   : $FRONTEND_VERSION" >&2
  echo "  Dockerfile : $DOCKER_VERSION" >&2
  exit 1
fi

if ! grep -q "## \[$VERSION\]" CHANGELOG.md; then
  echo "CHANGELOG.md ne contient pas de section ## [$VERSION]." >&2
  exit 1
fi

echo "→ Tests backend"
.venv/bin/python -m pytest

echo "→ Vérification et build frontend"
(
  cd frontend
  npm run typecheck
  npm run build
)

if [ -n "$(git status --porcelain)" ]; then
  echo "Le build ou les tests ont modifié des fichiers. Committez-les puis relancez." >&2
  git status --short >&2
  exit 1
fi

git tag -a "v$VERSION" -m "Presse-Agrumes v$VERSION"
echo "✓ Tag v$VERSION créé."
echo "Poussez avec : git push origin main && git push origin v$VERSION"
