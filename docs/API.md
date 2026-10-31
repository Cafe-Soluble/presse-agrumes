# API HTTP

Base : `http://<serveur>:8473`. Documentation interactive : `/docs` (Swagger UI),
schéma OpenAPI : `/openapi.json`.

Toutes les réponses sont en JSON, sauf les fichiers de test et les flux SSE.
Les erreurs utilisent le format `{"detail": "message"}`.

## Authentification

Active par défaut. Le mot de passe est lu dans `config.toml` (`[auth] password`).
Aucune variable d'environnement n'est utilisée. Toutes les routes (y compris
`/api/health`) exigent HTTP Basic :

```bash
curl -u agrumes:motdepasse http://127.0.0.1:8473/api/health
```


## Santé et configuration

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/health` | Statut, version, chemins ffmpeg/ffprobe, auth, fuseau serveur. |
| GET | `/api/config` | Presets qualité, défauts, racines autorisées, notes, fuseau. |
| GET | `/api/mounts` | Racines pratiques (home, `/mnt`, `/media`, montages). |
| GET | `/api/disk?path=/media` | Espace libre/total et pourcentage utilisé pour un dossier autorisé. |
| GET | `/api/system` | Charge CPU, mémoire, température et GPU (valeurs indisponibles à `null`). |
| POST | `/api/auth/password` | Change le mot de passe (`current_password`, `new_password`) et réécrit `config.toml`. |
| GET | `/api/setup` | État de l'assistant : `needed`, dossier média mémorisé, racines autorisées. |
| POST | `/api/setup` | Enregistre le dossier média choisi (`{"media_root": "/media/Films"}`) dans `data/settings.json`. |

## Fichiers

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/browse?path=/mnt/media` | Liste les sous-dossiers, permissions, breadcrumbs. |
| GET | `/api/browse?path=…&show_files=true` | Ajoute les fichiers vidéo. |
| POST | `/api/browse/mkdir` | Crée un dossier (`{"parent": "/media", "name": "Films"}`). |

Réponse (extrait) :

```json
{
  "path": "/mnt/media",
  "parent": "/mnt",
  "directories": [
    { "name": "Series", "path": "/mnt/media/Series", "readable": true, "writable": true }
  ],
  "videos": [],
  "permissions": { "readable": true, "writable": true },
  "breadcrumbs": [{ "name": "mnt", "path": "/mnt" }]
}
```

Les chemins hors `[paths] allowed_roots` renvoient `400`.

## Matériel

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/hardware?refresh=false` | CPU, RAM, GPU, encodeurs, benchmarks en cache. |
| POST | `/api/hardware/benchmark` | Lance un benchmark ffmpeg. |

Corps du benchmark :

```json
{ "encoder": "libsvtav1", "preset": 8, "threads": null, "force": false }
```

Réponse :

```json
{
  "benchmark": { "fps": 142.8, "speed": 4.76, "elapsed_sec": 0.94, "cached": false },
  "hardware": { "benchmarks": { "libsvtav1:p12:t6": { "fps": 142.8 } } }
}
```

## Analyse

### Démarrer un scan

`POST /api/scans`

```json
{
  "root": "/mnt/media",
  "options": {
    "min_size_mb": 200,
    "workers": 2,
    "include_av1": true,
    "follow_symlinks": false,
    "series_roots": ["/mnt/media/Series"],
    "exclude_globs": ["@eaDir", "#recycle", "*.tmp"]
  }
}
```

Réponse : snapshot de job (`id`, `status`, `progress`…). Suivre avec SSE ou
polling.

### Suivre un job

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/jobs/{job_id}` | Snapshot JSON. |
| GET | `/api/jobs/active` | Jobs en cours (queued/running/paused), tous types. |
| GET | `/api/jobs/{job_id}/events` | Flux SSE (`data: {snapshot}\n\n`). |
| POST | `/api/jobs/{job_id}/pause` | Pause une compression (SIGSTOP). |
| POST | `/api/jobs/{job_id}/resume` | Reprend une compression en pause manuelle. |
| POST | `/api/jobs/{job_id}/cancel` | Annulation. |
| GET | `/api/jobs?limit=30` | Jobs récents (mémoire + persistés). |

Exemple SSE :

```bash
curl -N http://127.0.0.1:8473/api/jobs/<id>/events
```

Le flux se termine quand le statut est `done`, `error`, `cancelled` ou
`interrupted`. Un commentaire `: keepalive` est émis périodiquement.

### Scans sauvegardés

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/scans` | Index des scans (résumés). |
| GET | `/api/scans/{scan_id}` | Scan complet : fichiers, items, packs, erreurs. |
| DELETE | `/api/scans/{scan_id}` | Supprime l'index (pas les vidéos). |
| POST | `/api/scans/{scan_id}/delete` | Supprime des fichiers média ciblés. |

### Suppression directe

```json
{
  "item_ids": ["file:…", "pack:…"],
  "paths": ["/mnt/media/fichier-en-erreur.mp4"]
}
```

Les `item_ids` suppriment un fichier ou tous les épisodes d'un pack ; `paths`
permet de cibler un fichier en erreur. Seuls les chemins déjà présents dans le
scan sont acceptés, les liens symboliques sont refusés et le fichier résolu doit
rester sous la racine du scan. Réponse :

```json
{
  "deleted": ["/mnt/media/fichier.mp4"],
  "deleted_count": 1,
  "errors": [],
  "warnings": [],
  "summary": { "items_count": 12 }
}
```

Cette opération est **irréversible** et distincte de la gestion des originaux
pendant une compression.

### Préflight

`POST /api/preflight`

```json
{
  "scan_id": "…",
  "item_ids": ["file:…", "pack:…"],
  "settings": {
    "encoder": "auto",
    "preset": 8,
    "crf": 32,
    "pixel_format": "yuv420p",
    "audio_mode": "copy",
    "audio_bitrate_kbps": 128,
    "container": "mkv",
    "subtitles": "copy"
  },
  "output": {
    "mode": "same_dir_new_name",
    "suffix": "av1",
    "output_dir": null,
    "overwrite": false
  },
  "originals": { "mode": "keep", "trash_dir": null },
  "resource_percent": 70,
  "concurrency": 1
}
```

Réponse :

```json
{
  "file_count": 8,
  "warnings": [],
  "skipped": [{ "path": "…", "warning": "déjà en AV1, ignoré" }],
  "estimate": { "seconds": 3600, "fps_reference": 142.8, "source": "benchmark" },
  "total_input_human": "10.0 Go",
  "total_estimated_output_human": "6.0 Go",
  "free_space_human": "1.2 To",
  "sample_destinations": [{ "source": "…", "destination": "…" }]
}
```

Les modes de sortie :

- `same_dir_new_name` : `stem.suffix.ext` ;
- `same_dir_same_name` : remplace la source (incompatible avec l'original
  conservé) ;
- `custom_dir` : `output_dir / relative_parent / stem.suffix.ext`.

Les modes d'originaux : `keep`, `delete`, `move` (avec `trash_dir`).

## Compression

`POST /api/compressions` - même corps que le préflight, plus `verify: true` et
`schedule` optionnel. Réponse : snapshot de job. Le job contient les items avec
`status`, `percent`, `output_size`, `saved_bytes`, `error`, `warning`.

Statuts : `queued`, `running`, `paused`, `done`, `error`, `cancelled`,
`interrupted`. Un job `paused` contient `pause_reasons` (`manual`, `schedule`),
`next_resume_at` et reste visible dans `/api/jobs/active`.

Le champ `schedule` optionnel permet de limiter l'encodage à des plages :

```json
{
  "schedule": {
    "enabled": true,
    "windows": [
      { "days": [0, 1, 2, 3, 4], "start": "22:00", "end": "07:00" }
    ]
  }
}
```

`days` : 0 = lundi … 6 = dimanche. Heures locales du serveur. Une plage qui
traverse minuit couvre le jour de début et la matinée suivante ; `start == end`
signifie toute la journée. Hors plage, le job passe en `paused` et reprend
automatiquement.

Exemple :

```bash
curl -X POST http://127.0.0.1:8473/api/compressions \
  -H 'Content-Type: application/json' \
  -d '{"scan_id":"…","item_ids":["pack:…"],"settings":{"preset":8,"crf":32},"output":{"mode":"same_dir_new_name","suffix":"av1"},"originals":{"mode":"keep"},"resource_percent":70,"concurrency":1}'
```

Les valeurs manquantes des sous-objets `settings`, `output` et `originals`
prennent les défauts Pydantic.

### Résultat

```json
{
  "success": 8,
  "failed": 0,
  "total": 8,
  "input_bytes": 10000000000,
  "output_bytes": 6000000000,
  "saved_bytes": 4000000000,
  "saved_percent": 40.0,
  "elapsed_seconds": 3600,
  "encoder": "libsvtav1",
  "items": []
}
```

## Test qualité

`POST /api/tests`

```json
{
  "path": "/mnt/media/Series/Breaking.Bad.S01/E01.mkv",
  "duration": 20,
  "start_mode": "percent",
  "start_percent": 25,
  "start_seconds": 0,
  "settings": { "preset": 8, "crf": 32 }
}
```

Réponse : job. À la fin, `result.test_id` permet de récupérer les fichiers.

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/tests/{test_id}/meta` | Métadonnées, tailles, débits, comparaison. |
| GET | `/api/tests/{test_id}/files/{filename}` | Fichier inline (support Range). |
| GET | `/api/tests/{test_id}/files/{filename}?download=1` | Téléchargement. |

Fichiers générés :

- `original.mp4` : aperçu H.264 CRF 18 (lecture navigateur) ;
- `original-raw.mkv` : extrait brut copié sans réencodage ;
- `compressed.mp4` : extrait AV1 + AAC (lecture navigateur).

Le gain de la comparaison est calculé sur le débit (taille/durée) entre le brut
et l'AV1.

## Codes d'erreur

| Code | Cas |
| --- | --- |
| `400` | Chemin invalide/hors racine, payload incohérent, dossier non inscriptible. |
| `404` | Scan/job/test/fichier inconnu. |
| `409` | Annulation d'un job déjà terminé. |
| `500` | ffmpeg/ffprobe introuvable, échec interne. |

## Exemple complet en Python

```python
import httpx, time

base = "http://127.0.0.1:8473"
client = httpx.Client(timeout=120)

job = client.post(f"{base}/api/scans", json={"root": "/mnt/media"}).json()
while True:
    snapshot = client.get(f"{base}/api/jobs/{job['id']}").json()
    if snapshot["status"] in {"done", "error", "cancelled"}:
        break
    time.sleep(1)

scan_id = snapshot["result"]["scan_id"]
scan = client.get(f"{base}/api/scans/{scan_id}").json()
print(scan["summary"])
```
