# AGENTS.md — guide pour les agents de développement

> **À lire avant toute modification.** Ce fichier décrit l'architecture réelle,
> les conventions et les pièges du projet Presse-Agrumes. Après chaque
> intervention notable, ajoutez une entrée datée dans
> [`docs/JOURNAL.md`](docs/JOURNAL.md).

## Mission

Presse-Agrumes analyse une bibliothèque vidéo sur un NAS, propose les fichiers
intéressants à compresser en AV1, regroupe les séries par saison, estime le
temps selon le matériel, permet un test qualité côte à côte, puis lance la
compression avec gestion des originaux et des permissions.

## Stack imposée

- Backend : **Python 3.10+ / FastAPI / Uvicorn**.
- Frontend : **Vite + React 19 + TypeScript**.
- UI : **Tailwind CSS + shadcn/ui** (Radix UI), icônes Lucide.
- Routage : **React Router** (`/`, `/history`, `/hardware`).
- Données serveur : **TanStack Query** + SSE pour les jobs.
- Média : ffmpeg / ffprobe. Encodeur privilégié : **SVT-AV1**.

Ne pas revenir à une interface vanilla ou à un autre framework sans demande
explicite de l'utilisateur.

## Commandes utiles

```bash
# Démarrage complet (venv + build frontend si absent)
./run.sh

# Backend seul
.venv/bin/python -m presse_agrumes --port 8080

# Développement (backend reload + Vite proxy sur 5173)
scripts/dev.sh

# Tests backend
.venv/bin/python -m pytest

# Frontend
cd frontend
npm run typecheck
npm run build
npm run test:e2e        # Playwright, nécessite un serveur
```

Le venv local contient `pytest`, `httpx`, `fastapi`, `uvicorn`. Sur la VM de
test, ffmpeg est un build statique dans `~/.local/bin` (SVT-AV1 + libaom).

## Carte du code

### Backend `presse_agrumes/`

| Fichier | Rôle |
| --- | --- |
| `app.py` | Création FastAPI, auth Basic, headers, routes, SSE, service du build React et fallback SPA. |
| `jobs.py` | Orchestration des jobs scan/compression/test, progression, annulation, préflight, commandes ffmpeg. |
| `media.py` | Extensions, `find_video_files`, ffprobe, analyse, estimation de gain, construction des commandes ffmpeg. |
| `series.py` | IDs stables, regroupement des packs de séries, résolution des items sélectionnés en fichiers. |
| `schedule.py` | Plages horaires, calcul de la prochaine reprise (jours, heures, minuit). |
| `network.py` | Scan de ports libres et énumération des IP locales. |
| `hardware.py` | Détection CPU/RAM/GPU/encodeurs, benchmark ffmpeg, cache, calcul d'ETA. |
| `paths.py` | `guard_path`, racines autorisées, navigation, permissions, `ensure_writable_dir`. |
| `models.py` | Schémas Pydantic des requêtes (dont `CompressionSchedule`). |
| `storage.py` | Écriture JSON atomique (scans, jobs, tests, cache matériel). |
| `config.py` | Variables `PA_*`, détection de ffmpeg/ffprobe, dossiers, auth générée. |
| `__main__.py` | CLI Uvicorn, scan de port, affichage URL/IP/mot de passe. |

### Frontend `frontend/src/`

| Chemin | Rôle |
| --- | --- |
| `pages/workspace-page.tsx` | Orchestrateur principal : scan, sélection, préflight, compression, dialogues. |
| `components/folder-step.tsx` | Étape 1 : dossier, options, dossiers de séries, progression du scan. |
| `components/results-panel.tsx` | Étape 2 : résumé, filtres, tri, lignes, packs, erreurs. |
| `components/compression-panel.tsx` | Étape 3 : réglages AV1, ressources, originaux, destination, ETA, préflight. |
| `components/job-panel.tsx` | Suivi d'un job de compression, journal, pause/reprise, résultat. |
| `components/active-jobs-banner.tsx` | Bannière globale des jobs actifs (polling `/api/jobs/active`). |
| `components/schedule-editor.tsx` | Plages horaires (jours, début, fin, traversée de minuit). |
| `components/test-dialog.tsx` | Test qualité et comparaison vidéo côte à côte. |
| `components/browse-dialog.tsx` | Navigateur de dossiers (racine, séries, sortie, corbeille). |
| `components/page.tsx`, `layout/app-shell.tsx` | Mise en page, header, navigation. |
| `components/ui/*` | Composants shadcn/ui (Button, Card, Dialog, Select, Slider…). |
| `lib/api.ts` | Client API typé. Toute nouvelle route doit y être ajoutée. |
| `lib/types.ts` | Types des objets backend. Garder synchronisé avec Pydantic. |
| `lib/estimate.ts` | Miroir client de l'estimation ETA/benchmark. |
| `hooks/use-api.ts` | Queries TanStack + `useJob` (SSE + polling). |

### Données `data/` (ignoré par git)

```
data/scans/{id}.json + index.json
data/jobs/{id}.json
data/tests/{id}/meta.json + original.mp4 + original-raw.mkv + compressed.mp4
data/cache/hardware.json
```

## Flux principaux

### Scan

1. `POST /api/scans` valide le chemin via `paths.guard_path`.
2. `jobs._run_scan` parcourt l'arborescence (progression SSE), lance ffprobe en
   parallèle, construit les fiches, puis `series.build_items`.
3. Le scan complet est sauvegardé ; le job renvoie `scan_id`.
4. Le frontend ouvre `/?scan={id}` et charge `GET /api/scans/{id}`.

### Préflight

`POST /api/preflight` appelle `JobManager.plan_compression` :
- résout les items (packs → épisodes) ;
- ignore les fichiers déjà AV1 et les erreurs ;
- calcule les destinations (suffixe, même nom, dossier miroir) ;
- vérifie permissions, conflits, espace disque par fichier **et cumulé par
  dossier** ;
- estime l'ETA.

Le frontend l'appelle automatiquement avec un debounce (~700 ms) à chaque
changement de sélection/réglages. Il ne crée que des dossiers de sortie.

### Compression

1. `POST /api/compressions` démarre un job threadé.
2. Chaque fichier : ffmpeg écrit `.nom.pa-tmp-XXXX.ext`, progression parsée sur
   `pipe:1`, validation ffprobe, `os.replace` atomique.
3. Ensuite seulement : original conservé / supprimé / déplacé vers la corbeille.
4. Le job est persisté après chaque fichier.

### Pause, reprise et planification

- `Job.pause(reason)` ajoute une raison (`manual`, `schedule`), passe le statut
  à `paused` et envoie `SIGSTOP` aux ffmpeg en cours.
- `Job.resume(reason)` retire la raison ; si plus aucune raison, `SIGCONT` et
  statut `running`.
- `wait_if_paused()` bloque les workers avant de démarrer un fichier.
- La planification est évaluée toutes les 15 s par un thread dédié. Hors plage :
  pause `schedule` + `next_resume_at`.
- Les jobs `paused` ne sont **pas** terminaux : ils restent dans
  `/api/jobs/active` et le frontend les réaffiche après rechargement.

### Test qualité

1. `POST /api/tests` prend un extrait (pourcentage ou seconde).
2. Trois fichiers : aperçu H.264 MP4 (navigateur), brut MKV (copie), AV1 MP4
   (aperçu). Le MP4/AAC est forcé pour la lecture navigateur.
3. Le gain est calculé sur le **débit** (taille/durée), pas sur la taille brute
   (l'extrait brut peut être plus long à cause du calage image-clé).

## Invariants à ne pas casser

1. **Jamais de `shell=True`** pour ffmpeg. Toujours des listes d'arguments.
2. **Jamais de recompression AV1** : `resolve_item_files` et le préflight
   ignorent les fichiers `already_av1`.
3. **Original supprimé uniquement après** `media.file_is_valid_video` sur la
   sortie temporaire et `os.replace`.
4. **Tous les chemins utilisateur** passent par `paths.guard_path` et
   `PA_ALLOWED_ROOTS`.
5. **Les liens symboliques ne sont pas suivis** dans le scan.
6. **La sortie est atomique** (fichier temporaire dans le même dossier).
7. **Les fichiers illisibles ne tuent pas le scan** : `os.walk(onerror=…)`,
   erreurs par fichier, `ThreadPoolExecutor` avec `future.result()` protégé.
8. **Le build React est servi par FastAPI** : si `frontend/dist` est absent, la
   page 503 explique la commande de build. Le fallback SPA renvoie `index.html`
   pour `/history`, `/hardware`, etc., mais jamais pour `/api/*` ou `/assets/*`.
9. **SSE** : ne pas mettre de middleware qui bufferise `text/event-stream`.
   Le client a un repli polling TanStack Query.
10. **Le dossier `frontend/dist` est versionné** pour un déploiement sans Node.
    Rebuild après toute modification frontend et committer le nouveau build.
11. **Authentification par défaut** : un mot de passe temporaire est généré au
    démarrage et affiché en console. Ne jamais logger le mot de passe côté
    requête, ne pas l'exposer dans `/api/config`. `PA_AUTH_DISABLED=1` est
    réservé au développement/tests.
12. **Port** : le port préféré est scanné ; ne pas coder 8080 en dur dans les
    URLs du frontend (utiliser des chemins relatifs).
13. **Pause** : les ffmpeg sont suspendus par `SIGSTOP` ; ne jamais supprimer un
    fichier temporaire pendant une pause (le job doit pouvoir reprendre).

## Ajouter une fonctionnalité

### Backend

1. Ajoutez le schéma dans `models.py`.
2. Implémentez la logique dans `media.py` / `jobs.py` / `hardware.py`.
3. Exposez la route dans `app.py` (avant le fallback SPA).
4. Persistez via `storage.py` si l'état doit survivre au redémarrage.
5. Ajoutez un test dans `tests/`.
6. Documentez dans `docs/API.md` et `docs/ARCHITECTURE.md`.

### Frontend

1. Ajoutez le type dans `lib/types.ts` et la méthode dans `lib/api.ts`.
2. Utilisez TanStack Query (pas de `fetch` direct dans les composants).
3. Pour un job, utilisez `useJob` (SSE + polling).
4. Réutilisez les composants `components/ui/*` (shadcn/ui), pas de CSS ad hoc
   hors Tailwind.
5. Vérifiez `npm run typecheck && npm run build`, puis testez en headless.
6. Rebuild `frontend/dist` et committer.

## Tests

- `tests/conftest.py` crée un environnement isolé (`PA_DATA_DIR`,
  `PA_ALLOWED_ROOTS` dans un tmp), génère de vraies vidéos H.264 avec ffmpeg,
  et fournit `TestClient`.
- `tests/test_core.py` : formats, estimation, permissions, fichiers vides/corrompus, planification, pause de job, scan de ports, regroupement séries.
- `tests/test_api.py` : health, SPA, scan, préflight, test qualité, compression
  avec suppression/déplacement/remplacement, dossier miroir, dossier en lecture
  seule, fichiers AV1, auth Basic, jobs actifs, pause/reprise, planification.
- Les tests nécessitent ffmpeg/ffprobe ; ils sont ignorés (`skip`) sinon.
- `frontend/e2e/smoke.spec.ts` : navigation SPA et absence d'erreurs console.

Sur une VM Debian sans GUI, Playwright headless a besoin de Chromium et de
bibliothèques (glib, nss, gbm…). Voir `docs/DEVELOPMENT.md` pour l'installation
locale sans root.

## Pièges connus

- **`series.build_items`** : un pack = le dossier parent immédiat des vidéos
  sous un marqueur de séries. Ne pas revenir à une comparaison épisode par
  épisode dans la liste principale.
- **Nom de série** : `Adolescence.S01.MULTI…` → `Adolescence — S01`. La logique
  `_series_base` retire le marqueur de saison et les séparateurs.
- **ETA** : le benchmark est mesuré sur tous les threads. Le pourcentage alloué
  et la concurrence réduisent linéairement les fps ; c'est une approximation
  volontairement simple.
- **`resource_percent`** : contrôle `lp` (SVT) / `-threads` (libaom) + `nice 10`,
  pas un cgroup. Ne pas promettre une isolation stricte.
- **MP4 + sous-titres** : non supporté en v1 (les sous-titres ne sont copiés que
  vers MKV). WebM + audio copié est converti en Opus.
- **`same_dir_same_name` + « garder »** : le préflight refuse (sinon la sortie
  écraserait l'original). Avec « supprimer », le remplacement est assumé.
- **Les noms de fichiers avec espaces/Unicode** doivent rester dans des listes
  d'arguments, jamais dans une commande shell.
- **Le frontend dépend de l'API** : les types `lib/types.ts` doivent suivre
  `models.py` et les dictionnaires de `jobs.py`.
- **Build Vite** : les noms d'assets sont hashés ; après rebuild, le serveur
  FastAPI continue de servir le dossier `assets/` (pas de cache d'index).
- **Mot de passe généré** : il est créé à l'import de `config.py`, affiché par
  `__main__.py`, puis copié dans l'environnement pour que le sous-processus
  `--reload` utilise le même. Ne pas déplacer cette logique dans `app.py`.
- **Deux instances** : le scan de port peut lancer une deuxième instance si 8080
  est occupé par un autre Presse-Agrumes. Elles partagent `data/` ; éviter ce cas
  sur un NAS (utiliser `--strict-port` ou arrêter l'ancienne).
- **Planification** : heures locales du serveur, précision de 15 s ; une plage
  `22:00→07:00` traverse minuit et appartient au jour de début.
- **Pause** : `SIGSTOP`/`SIGCONT` ne fonctionnent que sur POSIX (cible Linux).
  Ne pas remplacer par une suppression/relance de ffmpeg.
- **Jobs actifs** : `/api/jobs/active` ne lit que la mémoire ; après redémarrage
  du service, les jobs sont `interrupted` (pas de reprise automatique).

## Journal

Chaque intervention doit ajouter une entrée dans `docs/JOURNAL.md` :

```markdown
## 2026-10-30 — Titre court
- Fichiers modifiés : …
- Décision / raison : …
- Tests : …
- Reste à faire : …
```

C'est la mémoire du projet pour les agents suivants.
