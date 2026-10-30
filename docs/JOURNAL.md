# Journal de développement

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
- Reste à faire à la clôture de cette séance : commit(s) git, vérification
  finale `pytest` + `npm run build` + `test:e2e`, éventuel push `origin`.
