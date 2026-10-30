# Versionning et releases

## Convention

Presse-Agrumes suit **SemVer** :

- `MAJOR` : changement incompatible (format de données, API) ;
- `MINOR` : nouvelle fonctionnalité compatible ;
- `PATCH` : correction compatible.

Les tags git sont annotés et préfixés par `v` : `v0.1.0`, `v0.2.0`, `v0.2.1`…
Les pré-releases peuvent utiliser `v0.3.0-rc.1`.

## Fichiers de version à synchroniser

| Fichier | Champ |
| --- | --- |
| `presse_agrumes/__init__.py` | `__version__` |
| `presse_agrumes/config.py` | `VERSION` |
| `pyproject.toml` | `version` |
| `frontend/package.json` | `version` |
| `frontend/package-lock.json` | `version` (via `npm version`) |
| `CHANGELOG.md` | section `## [X.Y.Z]` |
| tag git | `vX.Y.Z` |

## Procédure de release

1. **Mettre à jour le CHANGELOG** avec une section datée.
2. **Bumper les versions** :
   ```bash
   cd frontend
   npm version 0.3.0 --no-git-tag-version
   cd ..
   sed -i 's/__version__ = ".*"/__version__ = "0.3.0"/' presse_agrumes/__init__.py
   sed -i 's/VERSION = ".*"/VERSION = "0.3.0"/' presse_agrumes/config.py
   sed -i 's/^version = ".*"/version = "0.3.0"/' pyproject.toml
   ```
3. **Mettre à jour la documentation** si nécessaire (README, roadmap).
4. **Rebuild le frontend** :
   ```bash
   cd frontend && npm run build
   ```
5. **Lancer les vérifications** :
   ```bash
   .venv/bin/python -m pytest
   cd frontend && npm run typecheck && npm run test:e2e
   ```
6. **Committer** :
   ```bash
   git add -A
   git commit -m "chore(release): v0.3.0"
   ```
7. **Créer le tag** avec le script :
   ```bash
   scripts/release.sh 0.3.0
   ```
   Le script vérifie la propreté du dépôt, la cohérence des versions, relance
   les tests et le build, puis crée le tag annoté.
8. **Pousser** :
   ```bash
   git push origin main
   git push origin v0.3.0
   ```

## Vérifier une release

```bash
git tag -n
git describe --tags
curl -u agrumes:motdepasse http://127.0.0.1:8080/api/health
```

`/api/health` renvoie la version chargée par le processus. Si elle ne correspond
pas au tag, le service n'a pas été redémarré après le déploiement.

## Historique

| Tag | Date | Contenu |
| --- | --- | --- |
| `v0.1.0` | 2026-10-30 | Analyse, compression, test qualité, interface React, documentation. |
| `v0.2.0` | 2026-10-30 | Mot de passe généré, scan de ports, pause/reprise, planification, bannière des tâches actives, sélection par ligne, erreurs enrichies. |
| `v0.3.0` | 2026-10-30 | Fichier `config.toml`, suppression directe, limites 10/20/30/50/Tout, calibration ETA automatique. |
