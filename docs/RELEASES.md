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
| `v0.8.0` | 2026-10-31 | Changement de mot de passe dans l'interface, annulation des analyses depuis la bannière, assistant/explorateur sans racine `/`, guide d'installation Compose pas-à-pas. |
| `v0.8.1` | 2026-10-31 | Gain potentiel ajusté au CRF choisi (résultats, résumé, préflight, sortie estimée) au lieu d'une valeur fixe. |
| `v0.8.2` | 2026-10-31 | L'analyse active reste affichée après navigation vers Matériel/Historique ; bouton Fermer si elle n'existe plus. |
| `v0.9.0` | 2026-10-31 | Création de dossiers, espace disque et faisabilité avant compression, historique des compressions, nettoyage des codecs dans les noms, téléchargements de test clarifiés. |
| `v0.10.0` | 2026-10-31 | Codec H.265 (libx265, VAAPI, QSV), benchmark sur fichier réel avec fourchette, diagnostic matériel VAAPI par codec. |
| `v0.10.1` | 2026-10-31 | Image Docker avec vainfo et pilotes VAAPI (Mesa, Intel non-free amd64, repli i965), documentation VAAPI détaillée. |
| `v0.10.2` | 2026-10-31 | VAAPI : GID numériques dans le Compose et la doc (les noms video/render peuvent manquer dans l'image), messages vainfo headless documentés. |
| `v0.11.0` | 2026-10-31 | Onglet Système (CPU, mémoire, température, GPU), suffixe synchronisé avec le codec, aperçu du nom final, tailles/gain estimés, suivi de compression en haut de page. |
| `v0.11.1` | 2026-10-31 | ETA initiale calibrée sur un extrait du fichier réel, bouton Calibrer dans l'estimation, remplacement du codec dans le nom (h264 -> av1, x265 -> h265). |
| `v0.11.2` | 2026-10-31 | ETA non calibrée affichée « à calibrer » au lieu d'une valeur de mire trompeuse ; benchmark synthétique marqué « mire ». |
