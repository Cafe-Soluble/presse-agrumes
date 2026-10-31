# Journal de développement

> **Note de lecture (v0.4.0)** : les entrées antérieures à la v0.4.0 mentionnent
> des variables d'environnement (`PA_*`, `FFMPEG_BIN`, `FFPROBE_BIN`). Elles ont
> été **entièrement supprimées** : depuis la v0.4.0, seule la configuration par
> `config.toml` est utilisée. Ces mentions sont conservées comme historique.

> Ce journal est la mémoire du projet. **Ajoutez une entrée datée après chaque
> intervention notable** : fichiers touchés, décisions, tests, points ouverts.

## 2026-10-30 — Audit du script initial et cadrage

- Lu `analyze_videos.py` (script CLI historique, 494 lignes) : scan récursif,
  ffprobe, estimation prudente, reprise, checkpoints. Conservé à la racine
  comme référence.
- Constats : pas d'interface, pas de compression, pas de test qualité, pas de
  détection matérielle réelle, pas de regroupement de séries, gestion des
  permissions limitée, script monolithique difficile à tester.
- Décision : backend FastAPI testable + interface web servie par le même
  processus, stockage JSON atomique, jobs en threads, SSE.
- Environnement de test : Debian 13, sans sudo. ffmpeg absent → build statique
  BtbN dans `~/.local/opt` + liens `~/.local/bin`. Node disponible.
- Plan consigné dans la conversation et repris dans `README.md` / `AGENTS.md`.

## 2026-10-30 — Backend : moteur média, séries, matériel, jobs

- Création `presse_agrumes/` :
  - `config.py` (env `PA_*`, recherche ffmpeg/ffprobe, dossiers data) ;
  - `storage.py` (JSON atomique, index scans, jobs, tests, cache) ;
  - `paths.py` (`guard_path`, `PA_ALLOWED_ROOTS`, navigation, permissions) ;
  - `media.py` (extensions, walk tolérant, ffprobe, analyse, estimation,
    commandes ffmpeg) ;
  - `series.py` (regroupement par dossier parent sous marqueur explicite) ;
  - `hardware.py` (CPU/RAM/GPU, encodeurs, benchmark mire 1080p, ETA) ;
  - `jobs.py` (scan/compression/test, préflight, annulation, SSE snapshots) ;
  - `models.py`, `app.py`, `__main__.py`.
- Choix de sécurité : aucune commande shell, sortie temporaire + `os.replace`,
  original supprimé seulement après ffprobe, AV1 jamais recompressé.
- Test manuel API : scan de `MEDIAS/`, 18 fichiers, pack Adolescence regroupé,
  erreur sur fichier vide correctement signalée.

## 2026-10-30 — Première interface (vanilla) puis décision de migration

- Une première interface HTML/CSS/JS sans dépendance a été construite et
  testée : analyse, résultats, compression, test qualité, benchmark, navigateur
  de dossiers. Elle a servi à valider tous les parcours API.
- **Nouvelle contrainte utilisateur en cours de route** : imposer
  Vite + React + TypeScript + Tailwind + shadcn/ui + React Router + TanStack
  Query. L'interface vanilla a été **remplacée** (dossier `web/` supprimé).
- Le backend n'a pas changé de contrat ; l'API reste la même.

## 2026-10-30 — Migration React/Vite/shadcn

- Création `frontend/` : Vite 6, React 19, TS strict, Tailwind 3.4, Radix UI
  (composants shadcn/ui), React Router 7, TanStack Query 5, Lucide.
- Pages : `/` (workspace 3 étapes + job), `/history`, `/hardware`.
- Composants métier : `folder-step`, `results-panel`, `compression-panel`,
  `job-panel`, `test-dialog`, `browse-dialog`.
- `lib/api.ts` typé, `lib/types.ts`, `lib/estimate.ts` (miroir ETA),
  `hooks/use-api.ts` (`useJob` SSE + polling de secours).
- FastAPI sert `frontend/dist` et renvoie l'index pour les routes clientes.
  `frontend/dist` est versionné pour un démarrage sans Node.
- Build : `tsc --noEmit && vite build`, 1762 modules, ~606 Ko JS minifié.

## 2026-10-30 — Validation headless et corrections

- Installation de Playwright + Chromium headless. La VM n'ayant ni polices ni
  bibliothèques X/glib, installation locale sans root : `.deb` extraits dans
  `~/.local/chrome-libs`, DejaVu dans `~/.local/share/fonts`, `LD_LIBRARY_PATH`.
- Captures générées : `docs/screenshots/workspace.png`, `test-quality.png`,
  `hardware.png`, `history.png`.
- Parcours Playwright validé : ouverture d'un scan, sélection, préflight,
  compression réelle, test qualité avec lecture des deux vidéos (`readyState=4`)
  et absence d'erreurs console.
- Bugs corrigés pendant cette phase :
  - compteur `already_av1_count` faussé par `None == None` ;
  - nom de pack `SERIES — S01` au lieu de `Adolescence — S01` ;
  - benchmark SVT renvoyant `fps=0.00` → repli sur `speed × 30` ;
  - comparaison de test qualité basée sur des durées différentes → comparaison
    de débit ;
  - warning « fichier existant remplacé » ambigu pour un remplacement sur place ;
  - contrôle cumulé de l'espace disque par dossier de sortie ;
  - `nice 10` sur les processus ffmpeg de compression ;
  - fallback SPA et asset hash après rebuild.

## 2026-10-30 — Tests backend et cas limites

- `tests/conftest.py` : environnement temporaire, `PA_ALLOWED_ROOTS`,
  génération de vidéos H.264 réelles, helpers scan/wait/probe.
- `tests/test_core.py` : formats, estimation, permissions, regroupement séries,
  marqueur sur dossier de saison.
- `tests/test_api.py` : health/SPA, config/guard, scan, préflight, test qualité
  (Range HTTP), compression avec suppression, déplacement en corbeille,
  remplacement sur place, dossier miroir, dossier non inscriptible, refus de
  recompression AV1.
- Résultat : **21 tests passés** en ~5 s (preset 12, petits fichiers).
- Tests manuels complémentaires : original déplacé vers `trash/…`, original
  supprimé après succès, AV1 sur place, sortie custom miroir, dossier 555 →
  erreur 400 explicite, fichier 000 → erreur de scan.
- Test Playwright : `1 passed` (`frontend/e2e/smoke.spec.ts`).

## 2026-10-30 — Documentation, scripts et git

- README public complet (fonctionnalités, installation NAS, systemd, config,
  guide, sécurité, API, dépannage, roadmap).
- `AGENTS.md` (carte du code, invariants, procédures, pièges, tests).
- `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEVELOPMENT.md`,
  `docs/DECISIONS.md`, `docs/JOURNAL.md`, `CHANGELOG.md`.
- `requirements.txt`, `pyproject.toml`, `.gitignore`, `LICENSE` MIT.
- `run.sh`, `scripts/dev.sh`, `deploy/presse-agrumes.service`,
  `deploy/presse-agrumes.env.example`.
- Nettoyage des scripts UI ad hoc ; ajout du test Playwright réutilisable.

## 2026-10-30 — Clôture, vérifications et commits

- Vérifications finales :
  - `pytest` : **22 tests passés** (scan, préflight, compression, permissions,
    test qualité, auth Basic, AV1, dossiers miroir/lecture seule).
  - `npm run typecheck` et `npm run build` : OK, `frontend/dist` à jour.
  - `npx playwright test` (headless) : **1 test passé**.
  - `./run.sh --help` : OK ; l'avertissement ffmpeg est évité si le binaire
    est dans `~/.local/bin` (build statique de test).
- Commits locaux :
  - `0bd8cf6` backend ;
  - `eb6d02f` frontend React ;
  - `385d7a3` tests ;
  - `fc37973` documentation.
- Le dossier `data/`, `MEDIAS/` et `frontend/node_modules/` sont ignorés ; le
  build `frontend/dist` est versionné.
- Push `origin/main` effectué (`22eeec9..993515c`), puis validation du
  démarrage autonome du backend par le `webServer` Playwright.
- Reste : validation sur le vrai NAS (droits réels, chemins `/mnt`, encodeur
  matériel).


## 2026-10-30 — v0.2.0 : auth, ports, pause, planification, bannière active

- **Authentification par défaut** : `config.py` génère `secrets.token_hex(8)` si
  `PA_AUTH_PASSWORD` est absent ; `__main__.py` affiche utilisateur, mot de passe,
  port et IP locales. `PA_AUTH_DISABLED=1` pour les tests/dev. Le mot de passe
  généré est copié dans l'environnement pour que `uvicorn --reload` utilise le
  même dans le processus fils.
- **Scan de ports** : `network.py` (bind TCP, IP via UDP/hostname/SIOCGIFADDR).
  Testé : 8080 occupé → 8081, avec affichage de l'URL et de l'IP Tailscale.
  `--strict-port` permet d'échouer volontairement.
- **Pause/reprise** : statut `paused`, raisons `manual`/`schedule`,
  `SIGSTOP`/`SIGCONT`, `wait_if_paused`, `Job.condition`. Test réel de pause au
  milieu d'un encodage + reprise.
- **Planification** : `schedule.py` + `CompressionSchedule` Pydantic + UI
  (`schedule-editor.tsx`). Fenêtres par jour/heure, traversée de minuit,
  évaluation toutes les 15 s, `next_resume_at`. Test d'un job qui démarre en
  pause hors plage, puis annulation.
- **Bannière active** : `GET /api/jobs/active`, `active-jobs-banner.tsx`,
  polling 2,5 s, réouverture auto du panneau après reload via `context.scan_id`.
  Testé headless : job planifié en pause, reload, bannière + panneau toujours
  visibles.
- **Sélection par ligne** : clic sur toute la ligne, exclusion des boutons/
  checkbox/details. Testé Playwright (`checkbox after row click: true`).
- **Erreurs enrichies** : `error_code`/`error_hint` (`empty_file`,
  `invalid_data`, permissions, timeout…). Le fichier vide de `MEDIAS/` affiche
  désormais « Fichier vide (0 octet) » et un conseil. Captures
  `docs/screenshots/error-handling.png`.
- **Versionning** : passage en 0.2.0, tag `v0.1.0` créé sur la release
  précédente, `scripts/release.sh`, `docs/RELEASES.md`, CHANGELOG.
- **Tests** : `pytest` → **30 passés** ; `npm run typecheck` + build OK ;
  Playwright → 1 passé avec auth Basic. Vérifications manuelles : auth 401/200,
  port 8081, `--reload` avec mot de passe partagé.
- **Reste** : commit + tag `v0.2.0` + push (fait après cette entrée).

## 2026-10-30 — v0.3.0 : config.toml, suppression directe, limites, ETA

- **Mot de passe en fichier** : `config.py` charge `config.toml` (TOML via
  `tomllib`/`tomli`), avec sections `[server]`, `[paths]`, `[auth]`, `[ffmpeg]`.
  Priorité env > fichier > défauts. `config.example.toml` fourni, `config.toml`
  ignoré par git. La console indique le fichier utilisé (et ne réaffiche pas le
  secret) ; avertissement si permissions trop larges. Tests TOML + subprocess.
- **Suppression directe** : `POST /api/scans/{id}/delete` (`item_ids` ou `paths`),
  validation stricte (présent dans le scan, sous la racine, pas de symlink),
  reconstruction de `files/items/packs/summary`. Bouton **Suppr.** par ligne et
  sur les fichiers en erreur, confirmation AlertDialog. Tests de suppression
  fichier + erreur + refus de chemin inconnu.
- **Limites 10/20/30/50/100/Tout** : sélecteur d'affichage et bouton
  « Sélectionner affichés » (sans AV1), « Tout sélectionner » conservé.
- **Bouton Suivi** : navigue vers `/?scan=…/#job` et scrolle vers le panneau de
  suivi ; `useLocation` gère l'arrivée sur la page.
- **ETA** : calibration automatique 1 s au lancement si le preset n'a pas de
  benchmark, bouton « Calibrer (~5 s) » dans les résultats, ETA globale recalculée
  avec `speed` ffmpeg. Test manuel : preset 8 calibré à 75 fps, compression OK.
- **Validation** : `pytest` → **35 passés** ; typecheck/build OK ; parcours
  Playwright manuel : limite 17→10, sélection de 10, suppression UI (fichier
  supprimé, ligne retirée), job planifié en pause, bouton Suivi (`#job`), job
  avec calibration ETA. Login avec mot de passe `config.toml` validé.
- **Reste** : commit + tag `v0.3.0` + push (fait après cette entrée).

## 2026-10-30 — v0.4.0 : configuration uniquement par config.toml

- **Suppression de toutes les variables d'environnement** de l'application
  (`PA_*`, `FFMPEG_BIN`, `FFPROBE_BIN`). `config.py` ne lit plus que le fichier
  TOML ; `apply_config_file(path)` permet de charger un fichier alternatif
  (option `--config`, tests, Docker).
- **`config.toml` devient versionné** et commenté section par section. Mot de
  passe par défaut `changez-moi` à changer en production, `allowed_roots = ["/"]`
  à restreindre. `config.example.toml` et `.env.example` supprimés.
- **Systemd** : plus aucune directive `Environment=` ; la configuration est lue
  depuis `/opt/presse-agrumes/config.toml`. `--host`/`--port` retirés, le port
  vient du fichier. `--config`, `--strict-port` et `--reload` restent.
- **Avertissements** : mot de passe par défaut encore présent, ou permissions de
  `config.toml` trop larges.
- **Tests** : `conftest.py` écrit un fichier TOML temporaire et l'applique avant
  d'importer l'app ; Playwright lance un backend dédié sur le port 8099 avec
  `tests/playwright.config.toml`. Plus aucune variable d'environnement dans les
  tests.
- **Validation** : pytest 36 passés, build Vite OK, Playwright OK, auth par
  `config.toml`, suppression directe, limites, Suivi et calibration ETA.
- **Reste** : commit + tag `v0.4.0` + push (fait après cette entrée).

## 2026-10-30 — v0.5.0 : distribution Docker / GHCR

- **Décision de distribution** : GHCR comme canal principal (intégration GitHub,
  pas de limite de pull Docker Hub, packages publics, multi-arch), Docker Hub
  éventuellement en miroir plus tard. `.deb` prévu ensuite.
- **Dockerfile multi-stage** : Node 22 compile le frontend, Python 3.13 slim
  (Debian trixie) exécute le backend avec ffmpeg/tini. Utilisateur non-root UID
  1000, volume `/app/data`, `config.toml` copié par défaut et monté en lecture
  seule en production, `--strict-port`.
- **Healthcheck** : endpoint `/healthz` sans auth, sans secret ; le healthcheck
  Docker lit le port réel dans `/app/config.toml`.
- **docker-compose.yml** : config ro, data, médias, localtime, VAAPI optionnel,
  UID/GID adaptables.
- **GitHub Actions** : job tests (pytest + typecheck/build) puis build/push
  multi-arch `linux/amd64,linux/arm64` vers
  `ghcr.io/cafe-soluble/presse-agrumes`, tags SemVer + latest.
- **Documentation** : `docs/DOCKER.md` (Synology/Unraid/OMV, UID/GID, VAAPI,
  timezone, mises à jour, dépannage), README et AGENTS mis à jour.
- **Limite de l'environnement** : Docker n'est pas installé sur la VM de test,
  donc l'image n'a pas pu être construite localement ; la CI est le premier
  build réel. Vérifier le tag `python:3.13-slim-trixie` et la présence de
  `libsvtav1`/`libaom-av1` dans ffmpeg Debian.
- **Validation locale** : `pytest` 36 passés, typecheck/build Vite OK,
  Playwright OK. `/healthz` testé sans auth.
- **Reste** : commit + tag `v0.5.0`, push ; déclencher la CI et rendre le
  package GHCR public ; valider `docker compose` sur un vrai NAS.

## 2026-10-30 — v0.6.0 : installation Docker en une commande

- **Problème utilisateur** : l'installation Docker demandait git/curl/config/
  Compose. Objectif : une seule commande et un mot de passe affiché.
- **Entrypoint** `docker/entrypoint.sh` : au premier démarrage, crée
  `/data/config.toml` dans le volume persistant avec un mot de passe aléatoire,
  `data_dir="/data"`, `allowed_roots=["/media"]` ; affiche le mot de passe dans
  les logs. Aux démarrages suivants, réutilise le fichier.
- **Dockerfile** : copie de l'entrypoint, volume `/data`, healthcheck sur
  `/data/config.toml`, `--strict-port`.
- **docker-compose.yml** : plus de montage de `config.toml` ; monte `./data:/data`
  et `/mnt/media:/media`. La config est générée dans `./data/config.toml`.
- **CI** : ajout d'un job smoke qui construit l'image, la lance avec un volume,
  vérifie `/healthz` et la création de `/data/config.toml`.
- **Docs** : README/DOCKER réécrits autour de la commande unique et de
  `docker logs`. Le nom court `cafe-soluble/...` nécessite un miroir Docker Hub
  (non configuré faute de compte/token) ; l'image actuelle est GHCR.
- **Validation locale** : tests 36, build frontend. Le smoke Docker sera validé
  par la CI (Docker absent sur la VM).
- **Reste** : commit + tag `v0.6.0` + push, surveiller le job smoke, puis
  éventuel miroir Docker Hub.

## 2026-10-31 — v0.6.0 validé, miroir Docker Hub optionnel

- **CI v0.6.0** : jobs `test`, `docker` (buildx amd64/arm64) et `smoke`
  (build + démarrage + `/healthz` + `/data/config.toml`) tous verts.
- **Image publique** : manifestes `0.6.0`, `0.6`, `latest` accessibles en
  anonyme sur GHCR, index OCI avec `linux/amd64` et `linux/arm64`.
- **Docker Hub** : ajout d'étapes optionnelles dans le workflow (login,
  métadonnées, build/push) conditionnées à `DOCKERHUB_USERNAME` et
  `DOCKERHUB_TOKEN`. Sans secrets, elles sont ignorées et GHCR reste seul canal.
- **Contrainte de nom** : les identifiants Docker Hub n'acceptent que lettres
  minuscules et chiffres ; `cafe-soluble` n'est pas un namespace valide. Le nom
  court visé devient `cafesoluble/presse-agrumes`. Documentation corrigée
  (README + `docs/DOCKER.md`, section « Nom court via Docker Hub »).
- **Reste** : créer le compte Docker Hub `cafesoluble`, ajouter les deux secrets,
  puis pousser un tag (`v0.6.1` ou `v0.7.0`) pour publier les tags de version.

## 2026-10-31 — v0.7.0 : assistant de premier démarrage

- **Contexte** : un chantier non commité ajoutait `/api/setup` et
  `setup-dialog.tsx` mais ne rendait pas le dialogue ; `tsc` et le smoke
  Playwright échouaient.
- **Complété** : rendu de `SetupDialog` dans `workspace-page`, `onComplete`
  (mémorise le dossier + préremplit l'étape 1), « Plus tard » persistant en
  `localStorage`, test e2e adapté.
- **Backend** : `GET/POST /api/setup`, `data/settings.json`, racines autorisées
  d'abord dans `common_roots`, refus des chemins hors périmètre.
- **Docker** : `allowed_roots` par défaut élargi à `/media`, `/mnt`, `/srv`,
  `/volume1`, `/volume2` ; documentation mise à jour.
- **Tests** : 37 pytest, typecheck, build, Playwright OK.
- **Release** : v0.7.0, image multi-arch GHCR (`0.7.0`, `0.7`, `latest`).

## 2026-10-31 — v0.7.1 : port par défaut 8473

- **Demande** : 8080 est trop souvent occupé ; choisir un port par défaut moins
  courant.
- **Décision** : 8473 par défaut (natif, Docker, Compose), scan inchangé vers
  8474/8475 en cas de conflit. Vérifié libre dans `/etc/services`.
- **Fichiers** : `config.py`, `config.toml`, `network.py`, `app.py`,
  `docker/entrypoint.sh`, `Dockerfile` (`EXPOSE`), `docker-compose.yml`,
  `scripts/dev.sh`, `frontend/vite.config.ts`, workflow smoke, docs.
- **Migration** : les installations existantes gardent le port de leur
  `config.toml` ; aucune action pour elles.
- **Tests** : pytest, typecheck, build, Playwright OK.

## 2026-10-31 — v0.7.2 : installation Compose simplifiée

- **Décision** : un seul chemin recommandé (Compose), `docker run` en annexe.
  Le Compose est téléchargé depuis la release et contient 3 valeurs à adapter
  (UID/GID, port, chemin média). Pas de `.env` : tout est inline avec des
  commentaires « À ADAPTER ».
- **Chemins** : documentation explicite du format `hôte:conteneur`
  (`/volume1/media:/media`) et distinction avec les chemins conteneur de
  `config.toml` (`/media`, `/data`).
- **Scénario A conservé** : aucun `config.toml` à créer, génération automatique
  dans `./data` avec mot de passe aléatoire affiché dans les logs.
- **CI** : ajout d'un job `release` (`softprops/action-gh-release`) qui joint
  `docker-compose.yml` aux releases des tags `v*`.
- **Tests** : pytest, typecheck, build, Playwright, YAML Compose/workflow.
