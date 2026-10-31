# Développement

## Environnement de référence

Le projet a été développé et validé sur :

- Debian 13 (trixie), Python 3.13 ;
- Node 26 / npm 11 (Node 20+ suffit) ;
- ffmpeg 7 avec `libsvtav1`, `libaom-av1`, `libx264` ;
- VM sans interface graphique, tests UI via Chromium headless Playwright.

L'application cible aussi les NAS x86_64 (OMV, Unraid, Synology via conteneur)
et les petites distributions avec Python 3.10+.

## Installation de développement

```bash
git clone git@github.com:Cafe-Soluble/presse-agrumes.git
cd presse-agrumes
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest httpx   # tests
(cd frontend && npm install)
```

### ffmpeg

Debian :

```bash
sudo apt install ffmpeg
ffmpeg -hide_banner -encoders | grep -E 'libsvtav1|libaom-av1|libx264'
```

Sans root (VM de test), on peut utiliser un build statique :

```bash
mkdir -p ~/.local/opt ~/.local/bin
cd ~/.local/opt
curl -L -o ffmpeg.tar.xz \
  https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
tar -xf ffmpeg.tar.xz
ln -sf ~/.local/opt/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg ~/.local/bin/ffmpeg
ln -sf ~/.local/opt/ffmpeg-master-latest-linux64-gpl/bin/ffprobe ~/.local/bin/ffprobe
```

`config.py` cherche aussi `~/.local/bin`, ce qui couvre le cas d'un service
systemd avec un `PATH` minimal. Pour être explicite, renseignez les chemins
dans `[ffmpeg]` de `config.toml`.

## Configuration de développement

Toute la configuration vient de `config.toml` (versionné). Pour développer :

```bash
chmod 600 config.toml
# éditez le mot de passe, le port, allowed_roots...
```

Pour éviter la boîte de dialogue HTTP Basic en local, mettez temporairement
`disabled = true` dans `[auth]` (ne committez pas ce changement). Les tests
utilisent leur propre fichier `tests/playwright.config.toml`, sans toucher à
la configuration de production.

## Lancer en développement

```bash
# Terminal 1 - backend avec reload (port/host lus dans config.toml)
.venv/bin/python -m presse_agrumes --reload

# Terminal 2 - Vite (proxy /api vers 8473)
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Ouvrir `http://127.0.0.1:5173`. Le proxy Vite évite tout problème de CORS.

Ou en une commande :

```bash
scripts/dev.sh
```

## Docker

La construction de l'image est décrite dans [`DOCKER.md`](DOCKER.md). En local :

```bash
docker build -t presse-agrumes:local .
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

L'image est multi-arch (amd64/arm64) via le workflow
`.github/workflows/docker.yml`, qui publie sur GHCR. Elle n'utilise aucune
variable d'environnement : l'entrypoint génère `/data/config.toml` dans le volume
persistant au premier démarrage, avec un mot de passe aléatoire affiché dans les
logs. Le volume `/data` contient aussi les scans/jobs.

```bash
docker run -d --name presse-agrumes -p 8473:8473 \
  -v /mnt/media:/media -v presse-agrumes:/data \
  ghcr.io/cafe-soluble/presse-agrumes:0.11.0
docker logs presse-agrumes
```

## Build de production

```bash
cd frontend
npm run typecheck
npm run build        # génère frontend/dist
```

FastAPI sert `frontend/dist` :

- `/` et toutes les routes clientes (`/history`, `/hardware`) renvoient
  `index.html` ;
- `/assets/*` sert les fichiers hashés ;
- `/api/*` ne tombe jamais dans le fallback SPA ;
- si `frontend/dist/index.html` est absent, `/` renvoie une page 503 avec la
  commande de build.

Le dossier `frontend/dist` est **versionné** pour qu'un NAS sans Node puisse
démarrer directement. Après toute modification frontend :

```bash
npm run build
git add frontend/dist
```

## Tests backend

```bash
.venv/bin/python -m pytest
```

Les tests :

- écrivent un `config.toml` temporaire (auth désactivée, chemins tmp) et
  l'appliquent avec `config.apply_config_file` ;
- génèrent de vraies vidéos H.264 avec ffmpeg (mire + sinus) ;
- testent le scan, le préflight, la compression, le test qualité, les
  permissions, le déplacement/suppression des originaux, les sorties miroir et
  le refus de recompression AV1 ;
- sont ignorés si ffmpeg/ffprobe sont absents.

Pour un test ciblé :

```bash
.venv/bin/python -m pytest tests/test_api.py -k compression -vv
```

### Ajouter un test

- Unitaire : `tests/test_core.py`.
- Configuration : `tests/test_config_file.py` (TOML, priorité, validation).
- API / intégration : `tests/test_api.py` + helpers `scan_root`, `wait_job`.
- Ne jamais utiliser le `data/` réel : passer par les fixtures.

## Tests frontend

### TypeScript

```bash
cd frontend
npm run typecheck
```

### Playwright headless

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

Le test démarre automatiquement un backend dédié sur le port **8099** avec
`tests/playwright.config.toml` (auth désactivée, données dans `data/e2e`) :

```bash
cd frontend
npm run test:e2e
```

Le test vérifie le chargement de la SPA, la navigation et l'absence d'erreurs
console. Les parcours avancés (bannière active, pause, planification, erreurs)
sont couverts par les tests backend et ont été validés manuellement en headless
avec captures dans `docs/screenshots/`.

### VM Debian sans GUI

Playwright headless fonctionne sans X11, mais Chromium a besoin de
bibliothèques système et de polices. Sans `sudo`, on peut les extraire
localement :

```bash
mkdir -p /tmp/debs ~/.local/chrome-libs
cd /tmp/debs
for pkg in libasound2t64 libatk1.0-0t64 libatk-bridge2.0-0t64 \
           libatspi2.0-0t64 libgbm1 libglib2.0-0t64 libnspr4 libnss3 \
           libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 \
           libxrender1 libdrm2 libxi6 fonts-dejavu-core; do
  apt-get download "$pkg"
  dpkg-deb -x "$pkg"*.deb ~/.local/chrome-libs
done

export LD_LIBRARY_PATH="$HOME/.local/chrome-libs/usr/lib/x86_64-linux-gnu"
export FONTCONFIG_PATH="$HOME/.local/chrome-libs/etc/fonts"
npx playwright test
```

Les polices DejaVu extraites sous `~/.local/share/fonts` sont aussi détectées.
Sur une installation de bureau classique, ces manipulations sont inutiles.
Pour des captures d'écran de documentation, utiliser `page.screenshot({fullPage:
true})`.

## Conventions de code

- Python : 4 espaces, type hints, docstrings en français, pas de dépendance
  lourde supplémentaire sans justification.
- Les fonctions média ne doivent pas lever pour un fichier isolé : renvoyer une
  fiche avec `error`.
- Les chemins utilisateur passent par `paths.guard_path`.
- Les commandes ffmpeg sont des listes, jamais des chaînes shell.
- Frontend : composants fonctionnels, hooks, TanStack Query, classes Tailwind.
  Réutiliser `components/ui/*` plutôt que réinventer les contrôles.
- Les textes visibles sont en français ; les identifiants techniques en anglais.
- Éviter les `any` TypeScript. Mettre à jour `lib/types.ts` avec le backend.
- Pas de `console.log` permanent dans le frontend.

## Ajouter une route API

1. Modèle Pydantic dans `models.py` si nécessaire.
2. Logique dans le module métier (`media`, `hardware`, `jobs`).
3. Route dans `app.py` **avant** le fallback SPA.
4. Méthode typée dans `frontend/src/lib/api.ts`.
5. Query/mutation TanStack dans le composant.
6. Test API + documentation `docs/API.md`.

## Données et nettoyage

```bash
# Supprimer les scans/jobs/tests/benchmarks locaux
rm -rf data

# Les clips de test peuvent être volumineux :
du -sh data/tests/*
```

`data/` est ignoré par git ; `MEDIAS/` aussi.

## Déploiement systemd

Voir `deploy/presse-agrumes.service` et `README.md`. Points d'attention :

- `User`/`Group` doivent pouvoir lire les médias et écrire les sorties ;
- `[paths] allowed_roots` doit lister les chemins autorisés ;
- `[ffmpeg]` peut contenir des chemins absolus si le PATH du service est minimal ;
- `[paths] data_dir` doit être accessible en écriture ;
- redémarrer après un rebuild du frontend n'est pas nécessaire : le serveur lit
  `frontend/dist/index.html` à chaque requête ; en revanche, si `assets/`
  n'existait pas au démarrage, redémarrer.

## Releases

Le versionning et la création des tags sont décrits dans
[`RELEASES.md`](RELEASES.md). En résumé : bumper les versions, mettre à jour le
CHANGELOG, committer, puis exécuter `scripts/release.sh X.Y.Z` et pousser le tag.

## Checklist de release

- [ ] `pytest` vert.
- [ ] `npm run typecheck` et `npm run build` verts.
- [ ] `npm run test:e2e` vert (ou test manuel headless documenté).
- [ ] `frontend/dist` rebuild et ajouté.
- [ ] Captures dans `docs/screenshots/` à jour.
- [ ] `docs/JOURNAL.md` complété.
- [ ] `README.md` / `CHANGELOG.md` à jour.
- [ ] Versions synchronisées (`__init__.py`, `config.py`, `pyproject.toml`,
      `frontend/package.json`, `CHANGELOG.md`).
- [ ] `scripts/release.sh X.Y.Z` exécuté et tag poussé.
- [ ] Image Docker construite par la CI sur le tag, package GHCR public.
- [ ] `git status` ne contient ni `data/`, ni `MEDIAS/`, ni `node_modules/`.
