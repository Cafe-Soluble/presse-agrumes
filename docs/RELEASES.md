# Versionning et releases

## Convention

Presse-Agrumes suit **SemVer** :

- `MAJOR` : changement incompatible (format de données, API) ;
- `MINOR` : nouvelle fonctionnalité compatible ;
- `PATCH` : correction compatible.

Les tags git sont annotés et préfixés par `v` : `v0.1.0`, `v0.2.0`, `v0.2.1`…
Les pré-releases peuvent utiliser `v0.7.0-rc.1`.

## Fichiers de version à synchroniser

| Fichier | Champ |
| --- | --- |
| `presse_agrumes/__init__.py` | `__version__` |
| `presse_agrumes/config.py` | `VERSION` |
| `pyproject.toml` | `version` |
| `frontend/package.json` | `version` |
| `frontend/package-lock.json` | `version` (via `npm version`) |
| `Dockerfile` | `ARG APP_VERSION` |
| `CHANGELOG.md` | section `## [X.Y.Z]` |
| tag git | `vX.Y.Z` |

## Procédure de release

1. **Mettre à jour le CHANGELOG** avec une section datée.
2. **Bumper les versions** :
   ```bash
   cd frontend
   npm version X.Y.Z --no-git-tag-version
   cd ..
   sed -i 's/__version__ = ".*"/__version__ = "X.Y.Z"/' presse_agrumes/__init__.py
   sed -i 's/VERSION = ".*"/VERSION = "X.Y.Z"/' presse_agrumes/config.py
   sed -i 's/^version = ".*"/version = "X.Y.Z"/' pyproject.toml
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
   git commit -m "chore(release): vX.Y.Z"
   ```
7. **Créer le tag** avec le script :
   ```bash
   scripts/release.sh X.Y.Z
   ```
   Le script vérifie la propreté du dépôt, la cohérence des versions, relance
   les tests et le build, puis crée le tag annoté.
8. **Pousser** :
   ```bash
   git push origin main
   git push origin vX.Y.Z
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
| `v0.4.0` | 2026-10-30 | Configuration uniquement par `config.toml`, suppression des variables d'environnement, fichier versionné, systemd sans `Environment=`. |
| `v0.4.1` | 2026-10-30 | Nettoyage du lancement (`run.sh`), plus aucune variable de shell pour la configuration. |
| `v0.5.0` | 2026-10-30 | Image Docker multi-arch GHCR, docker-compose, CI, endpoint `/healthz`, documentation Docker. |
| `v0.6.0` | 2026-10-30 | Installation Docker en une commande, config auto-générée dans `/data`, mot de passe aléatoire dans les logs, smoke test CI. |
| `v0.7.0` | 2026-10-31 | Assistant de premier démarrage (choix du dossier média), `/api/setup`, racines Docker élargies, miroir Docker Hub optionnel. |
| `v0.7.1` | 2026-10-31 | Port par défaut 8473 au lieu de 8080 (native, Docker, Compose), scan vers 8474/8475, documentation et smoke CI mis à jour. |
| `v0.7.2` | 2026-10-31 | Installation Docker Compose simplifiée : `docker-compose.yml` publié avec la release, 3 valeurs à adapter, chemins hôte/conteneur explicités, config toujours auto-générée. |
| `v0.7.3` | 2026-10-31 | Message d'erreur explicite si `/data` n'est pas inscriptible (UID + `chown`), montage média documenté (dossier exact ou racine `/srv`, `/volume1`, `/mnt`), dépannage « première configuration absente ». |
