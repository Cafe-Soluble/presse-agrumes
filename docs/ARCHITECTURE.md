# Architecture

## Vue d'ensemble

```text
┌────────────────────────────────────────────────────────────────────┐
│ Navigateur (LAN)                                                   │
│ React 19 + TypeScript + Tailwind + shadcn/ui                      │
│ React Router · TanStack Query · EventSource (SSE)                 │
└───────────────┬────────────────────────────────────────────────────┘
                │ HTTP /api (JSON)            │ text/event-stream
                ▼                             ▼
┌────────────────────────────────────────────────────────────────────┐
│ FastAPI (presse_agrumes/app.py)                                    │
│ auth Basic optionnelle · validation Pydantic · fallback SPA        │
└───────────────┬────────────────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────────────────────────────────────────┐
│ JobManager (jobs.py) — threads daemon                              │
│  scan ──────────────► media.find_video_files + ffprobe             │
│  préflight ─────────► series.resolve_item_files + paths.permissions│
│  compression ───────► ffmpeg (SVT-AV1/libaom/VAAPI) + ffprobe      │
│  test qualité ──────► ffmpeg (H.264 proxy + brut + AV1)            │
│  benchmark ─────────► ffmpeg testsrc2 1080p                        │
└───────┬───────────────────────────────┬────────────────────────────┘
        │ JSON atomique                 │ subprocess (listes d'args)
        ▼                               ▼
┌───────────────────────┐      ┌────────────────────────────────────┐
│ data/                 │      │ ffmpeg / ffprobe                   │
│ scans/ jobs/ tests/   │      │ fichiers médias du NAS             │
│ cache/hardware.json   │      └────────────────────────────────────┘
└───────────────────────┘
```

## Choix structurants

- **SPA servie par le backend** : pas de serveur Node en production. FastAPI
  sert `frontend/dist` (build versionné) et renvoie `index.html` pour les routes
  React (`/history`, `/hardware`). Vite est utilisé uniquement en développement,
  avec un proxy `/api` vers `127.0.0.1:8080`.
- **Aucune base de données** : les scans et jobs sont des JSON atomiques. Un
  NAS peut facilement inspecter/sauvegarder `data/`, et le volume reste faible
  (métadonnées, pas de vidéos).
- **Jobs en threads** : les opérations sont bloquantes (ffprobe/ffmpeg) et
  FastAPI reste réactif. Chaque job expose un snapshot thread-safe et un flux
  SSE. TanStack Query interroge aussi `/api/jobs/{id}` en repli.
- **Regroupement des séries explicite** : l'IA ne devine pas si un dossier est
  une série. L'utilisateur marque une racine de séries. Sous cette racine, le
  dossier parent immédiat d'une vidéo devient un pack (saison ou série).
- **Sécurité locale** : `PA_ALLOWED_ROOTS` + `guard_path`, pas de shell,
  authentification Basic optionnelle, liens symboliques non suivis.

## Backend

### `config.py`

Résout `PA_*`, les dossiers de données, et cherche ffmpeg/ffprobe dans l'ordre :
variable d'environnement explicite, `PATH`, `~/.local/bin`, `/usr/local/bin`,
`/usr/bin`, `/opt/ffmpeg/bin`. Le fallback `~/.local/bin` sert au build statique
de développement.

### `paths.py`

- `guard_path(raw, must_exist=…)` : expansion `~`, résolution, refus des octets
  NUL, vérification d'appartenance à `ALLOWED_ROOTS`.
- `browse(raw)` : liste les dossiers avec indicateurs lecture/écriture, gère
  `PermissionError`, ne suit pas les liens pour éviter les boucles.
- `common_roots()` : home + montages usuels (`/mnt`, `/media`, `/srv`,
  `/volume*`) lus dans `/proc/mounts`.
- `ensure_writable_dir()` : crée le dossier puis vérifie `W_OK|X_OK`.

### `media.py`

- `find_video_files()` : `os.walk(topdown=True)`, filtre les extensions,
  exclut les motifs glob et les pseudo-fs (`/proc`, `/sys`, `/dev`, `/run`),
  signale les dossiers illisibles via `onerror`, callback de progression.
- `analyze_file()` : ne lève jamais ; renvoie une fiche même en erreur.
  Champs : codec vidéo/audio, résolution, fps, durée, bitrate, bpp, HDR,
  10 bits, taille, permissions, gain estimé, recommandation.
- `estimate_gain()` : facteur par codec, ajusté par bpp, plafonné à 90 %.
  AV1 → 0. La taille de sortie estimée est `taille - gain`.
- `build_compress_command()` : liste d'arguments, mapping des presets, `lp`
  pour SVT-AV1, `-cpu-used` pour libaom, VAAPI si demandé, audio, conteneur,
  sous-titres (MKV uniquement), progression `pipe:1`.
- `build_preview_original_command()` / `build_raw_clip_command()` /
  `build_compress_test_command()` : pipeline du test qualité.
- `file_is_valid_video()` : vérifie existence, taille et durée via ffprobe.

### `series.py`

- IDs stables : `file:<sha1(path)[:16]>`, `pack:<sha1(dir)[:16]>`.
- `build_items(files, root, series_roots)` : pour chaque fichier sous un
  marqueur, le pack est le dossier parent immédiat. Les fichiers hors marqueur
  restent des items individuels. Les packs agrègent taille, durée, gain,
  codecs, résolutions, épisodes et déjà-AV1.
- `_series_base()` : `Adolescence.S01.MULTI.1080p…` → `Adolescence`, saison
  `S01` ; si le dossier s'appelle seulement `S01`, le parent fournit le nom.
- `resolve_item_files(scan, item_ids)` : packs → épisodes, ignore les AV1 et
  les erreurs avec avertissements.

### `jobs.py`

`Job` contient : statut, progression, items, logs (deque), estimate, résultat,
`sse.Event` d'annulation, processus ffmpeg en cours, verrou.

- **Scan** : walk → ffprobe en pool (`workers`) → `build_items` → sauvegarde.
  L'ETA est calculé sur le débit de fichiers analysés.
- **Préflight** (`plan_compression`) : résolution des items, chemins de sortie,
  conflits, permissions, espace disque par fichier et cumulé par dossier,
  estimation matérielle. Utilisé par `/api/preflight` et par la compression.
- **Compression** : pool de `concurrency` workers, threads répartis. Sortie
  temporaire `.pa-tmp-<token>.ext`, progression parsée (`out_time_us`, `speed`,
  `fps`), validation ffprobe, `os.replace`, puis traitement de l'original.
  Annulation : `terminate()` des processus, arrêt du pool, statut `cancelled`.
- **Test** : trois étapes (proxy original 0→35 %, brut 35→45 %, AV1 45→100 %),
  méta et comparaison de débit.
- **Benchmark** : délégué à `hardware.benchmark`, exécuté en threadpool via
  `asyncio.to_thread` pour ne pas bloquer l'event loop.

### `hardware.py`

- Lit `/proc/cpuinfo`, `/proc/meminfo`, `/dev/dri`, `ffmpeg -encoders`.
- Benchmark : mire `testsrc2` 1920×1080 30 fps 4 s, encodeur/preset demandés,
  parsing de `fps=` et repli sur `speed × 30` (SVT renvoie parfois `fps=0`).
- Cache : `data/cache/hardware.json`, clé `encodeur:preset:threads`, invalidé
  par une empreinte CPU + version ffmpeg.
- ETA : `durée / fps_effectif × 1.12 + 1.5 s/fichier`, fps effectif réduit par
  `threads_alloués / threads_benchmark` et la concurrence.

### `storage.py`

Écriture `tmp-<pid>` + `os.replace` ; index des scans pour la page historique.
Les jobs sont persistés à chaque étape de compression (pas à chaque tick SSE).

## Frontend

### État et données

- **TanStack Query** : `config`, `hardware`, `mounts`, `scans`, `scan`, `job`,
  `preflight`, `browse`, `test`.
- **`useJob`** : EventSource sur `/api/jobs/{id}/events` met à jour le cache
  TanStack ; `refetchInterval` de 1,2 s tant que le job n'est pas terminal,
  ce qui couvre les coupures SSE.
- **localStorage** : racine, options de scan, dossiers de série, réglages AV1,
  destination, originaux, pourcentage de ressources, concurrence.
- **Sélection** : `Set<string>` d'IDs d'items. Un pack sélectionné sélectionne
  tous ses épisodes côté serveur.

### Pages

- `/` : workspace en trois étapes + job + derniers scans.
- `/history` : liste des scans, ouverture (`/?scan=…`), suppression de l'index.
- `/hardware` : profil, benchmark, cache, explication de l'ETA.

### Préflight automatique

Le workspace construit un payload (`scan_id`, `item_ids`, réglages, sorties,
originaux, ressources), le debounce à 700 ms, puis appelle `POST /api/preflight`.
Les avertissements (conflits, permissions, espace disque, AV1 ignorés) sont
affichés dans l'étape 3. Un changement de sélection/réglage relance la
vérification.

## Formats de données

### Fiche fichier (extrait)

```json
{
  "path": "/mnt/media/film.mkv",
  "relative_path": "film.mkv",
  "video_codec": "h264",
  "resolution": "1920x1080",
  "duration_sec": 5400.2,
  "bit_rate_bps": 8000000,
  "bits_per_pixel": 0.15,
  "size_bytes": 5400000000,
  "already_av1": false,
  "estimated_gain_bytes": 1800000000,
  "estimated_output_bytes": 3600000000,
  "recommendation": "bon",
  "error": null
}
```

### Pack série

```json
{
  "id": "pack:…",
  "kind": "series",
  "name": "Breaking Bad — S01 (8 épisodes)",
  "series_name": "Breaking Bad",
  "season_label": "S01",
  "episode_count": 8,
  "episodes": [{ "path": "…", "episode": "E01", "size_human": "1.2 Go" }],
  "size_bytes": 10000000000,
  "estimated_gain_bytes": 4000000000,
  "estimated_gain_percent": 40.0
}
```

### Job (snapshot)

```json
{
  "id": "…",
  "kind": "compress",
  "status": "running",
  "progress": {
    "phase": "compressing",
    "percent": 42.5,
    "done": 1,
    "total": 3,
    "eta_seconds": 320,
    "speed": "1.8x",
    "fps": 54.2
  },
  "items": [{ "filename": "E01.mkv", "status": "running", "percent": 37 }],
  "warnings": [],
  "logs": ["…"]
}
```

## Performances

- ffprobe : 2 threads par défaut (disques mécaniques), configurable.
- Compression : 1 fichier par défaut ; `concurrency` > 1 divise les threads.
- SVT-AV1 est le facteur limitant : un preset 8 en 1080p peut être 5 à 20 fois
  plus rapide que libaom sur le même CPU.
- L'interface ne charge jamais les vidéos complètes : seuls les extraits de
  test sont servis, avec support HTTP Range.

## Limites connues

- Pas de pause/reprise d'un job de compression (annulation uniquement).
- Sous-titres non supportés vers MP4/WebM.
- Pas de copie des métadonnées complexes (chapitres, pièces jointes) au-delà de
  `-map_metadata 0`.
- L'ETA ne connaît pas la complexité réelle de la vidéo ; le benchmark sur mire
  est une approximation.
- Mono-utilisateur : pas de comptes ni de quotas.
