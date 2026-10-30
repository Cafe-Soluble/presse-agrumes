# 🍊 Presse-Agrumes

**Analysez votre bibliothèque vidéo, testez la qualité, puis compressez en AV1 — sans quitter votre navigateur.**

Presse-Agrumes est un outil web auto-hébergé pensé pour les NAS et les serveurs domestiques. Il parcourt un dossier, détecte les vidéos qui valent le coup d'être réencodées en AV1, regroupe les séries par saison, estime le temps sur votre matériel et permet de vérifier le résultat sur un extrait avant de toucher au moindre fichier.

> [!WARNING]
> Cet outil lit, déplace et supprime des fichiers vidéo. Il est conçu pour un **réseau local de confiance**. Ne l'exposez pas directement sur Internet : utilisez un VPN ou, au minimum, l'authentification HTTP Basic intégrée (`PA_AUTH_USER` / `PA_AUTH_PASSWORD`) derrière un reverse proxy TLS.

![Interface principale](docs/screenshots/workspace.png)

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Démarrage rapide](#démarrage-rapide)
- [Installation sur un NAS](#installation-sur-un-nas)
- [Configuration](#configuration)
- [Guide d'utilisation](#guide-dutilisation)
- [Sécurité et permissions](#sécurité-et-permissions)
- [Structure du dépôt](#structure-du-dépôt)
- [API](#api)
- [Développement et tests](#développement-et-tests)
- [Dépannage](#dépannage)
- [Feuille de route](#feuille-de-route)
- [Licence](#licence)

## Fonctionnalités

- **Analyse récursive** d'un dossier avec progression SSE en temps réel, ETA, annulation et reprise après erreur.
- **Détection des bons candidats** : codec, bitrate, résolution, durée, HDR, 10 bits, bits par pixel, gain estimé de façon volontairement pessimiste.
- **Séries regroupées** : un dossier marqué « séries » devient une seule ligne par saison (ou par série), avec le détail des épisodes à la demande. Aucune heuristique imposée : c'est vous qui indiquez les dossiers de séries.
- **Tri, recherche, filtres et sélection** par fichier ou par pack complet.
- **Réglages AV1** : SVT-AV1 / libaom / VAAPI, preset, CRF, 8 ou 10 bits, audio copié ou réencodé, MKV/MP4/WebM, sous-titres.
- **Gestion des originaux** : conserver, supprimer après vérification ffprobe, ou déplacer vers une corbeille en conservant l'arborescence.
- **Destination des fichiers compressés** : même dossier avec suffixe, remplacement sur place, ou dossier personnalisé avec miroir de l'arborescence.
- **Estimation matérielle** : détection CPU/RAM/GPU, benchmark ffmpeg réel, ETA selon le pourcentage de ressources alloué et le nombre d'encodages simultanés.
- **Test qualité** : extrait de 20 s (configurable), encodage AV1 et comparaison côte à côte dans le navigateur, avec téléchargement de l'original brut.
- **Gestion des permissions** : dossiers illisibles, fichiers en erreur, sorties non inscriptibles, espace disque insuffisant et conflits de noms sont signalés avant lancement.
- **Garde-fous** : jamais de recompression d'un fichier déjà AV1, sortie écrite dans un fichier temporaire puis renommée atomiquement, original supprimé seulement après validation de la sortie.
- **Interface React** responsive, thème sombre, navigation entre compression, historique et matériel.

| Test qualité | Matériel & ETA |
| --- | --- |
| ![Test qualité](docs/screenshots/test-quality.png) | ![Matériel](docs/screenshots/hardware.png) |

| Historique |
| --- |
| ![Historique](docs/screenshots/history.png) |

## Stack technique

| Couche | Technologie |
| --- | --- |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Vite, React 19, TypeScript |
| UI | Tailwind CSS, composants shadcn/ui (Radix UI), icônes Lucide |
| Routage | React Router |
| Données client | TanStack Query + SSE (progression), repli polling |
| Média | ffmpeg / ffprobe, encodeur SVT-AV1 (recommandé) |
| Persistance | JSON atomique dans `data/` (scans, jobs, tests, benchmark) |

Le backend ne fait confiance à aucun chemin : chaque accès passe par `presse_agrumes/paths.py` et les racines autorisées. Les commandes ffmpeg sont toujours construites sous forme de listes, jamais via un shell.

## Démarrage rapide

### Prérequis

- Linux (Debian/Ubuntu, OMV, Unraid, Synology avec conteneur, etc.) ;
- Python **3.10+** et `python3-venv` ;
- **ffmpeg / ffprobe** avec au moins un encodeur AV1 :
  ```bash
  ffmpeg -hide_banner -encoders | grep -E 'libsvtav1|libaom-av1|av1_vaapi'
  ```
  `libsvtav1` est fortement recommandé (rapide). `libaom-av1` fonctionne mais est beaucoup plus lent.
- Node.js 20+ **uniquement** pour reconstruire l'interface. Le build `frontend/dist` est versionné, donc un NAS sans Node peut lancer l'application telle quelle.

### Installation

```bash
git clone git@github.com:Cafe-Soluble/presse-agrumes.git
cd presse-agrumes
./run.sh
```

`run.sh` crée le venv, installe les dépendances, compile le frontend s'il manque, puis démarre le serveur.

Ouvrez ensuite :

```text
http://<IP-du-serveur>:8080
```

Exemple : `http://192.168.1.50:8080`.

### Premier usage

1. Choisissez le dossier à analyser (navigateur de dossiers intégré ou chemin direct).
2. Si le dossier contient des séries, ajoutez-le dans **Dossiers de séries**.
3. Lancez l'analyse, triez par gain potentiel, sélectionnez des fichiers ou des packs.
4. Cliquez sur **Test** pour vérifier la qualité sur un extrait.
5. Ajustez les réglages, choisissez le devenir des originaux et la destination.
6. Lancez la compression, suivez la progression et le journal.

## Installation sur un NAS

### Debian / Ubuntu / OMV

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv git
# Node n'est nécessaire que pour rebuild le frontend :
sudo apt install -y nodejs npm
```

Clonez le dépôt dans `/opt/presse-agrumes`, puis :

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# (facultatif si frontend/dist est présent)
(cd frontend && npm install && npm run build)
```

### Service systemd

Un modèle est fourni dans [`deploy/presse-agrumes.service`](deploy/presse-agrumes.service) :

```bash
sudo cp deploy/presse-agrumes.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now presse-agrumes
sudo journalctl -u presse-agrumes -f
```

Adaptez `User`, `Group`, `WorkingDirectory`, `PA_ALLOWED_ROOTS` et les chemins ffmpeg. L'utilisateur du service doit pouvoir **lire** les médias et **écrire** dans les dossiers de sortie / corbeille.

### Reverse proxy / HTTPS

Placez Nginx, Caddy ou Traefik devant l'application si vous voulez TLS. Exemple Caddy :

```caddyfile
agrumes.mondomaine.local {
  reverse_proxy 127.0.0.1:8080
  basic_auth {
    agrumes $2a$14$...
  }
}
```

Si vous utilisez SSE derrière un proxy, désactivez le buffering pour `/api/jobs/*/events` (`proxy_buffering off;` côté Nginx). L'application envoie déjà `X-Accel-Buffering: no`.

## Configuration

Toutes les options sont des variables d'environnement. Un exemple complet est fourni dans [`deploy/presse-agrumes.env.example`](deploy/presse-agrumes.env.example).

| Variable | Défaut | Description |
| --- | --- | --- |
| `PA_HOST` | `0.0.0.0` | Adresse d'écoute. |
| `PA_PORT` | `8080` | Port HTTP. |
| `PA_DATA_DIR` | `<projet>/data` | Scans, jobs, tests, benchmarks. |
| `PA_ALLOWED_ROOTS` | `/` | Racines accessibles, séparées par `:`. **À restreindre** (`/mnt/media:/srv/media`). |
| `PA_AUTH_USER` | vide | Active HTTP Basic si un utilisateur est défini. |
| `PA_AUTH_PASSWORD` | vide | Mot de passe HTTP Basic. |
| `FFMPEG_BIN` | auto | Chemin absolu vers ffmpeg (utile en systemd). |
| `FFPROBE_BIN` | auto | Chemin absolu vers ffprobe. |

Exemple :

```bash
PA_ALLOWED_ROOTS=/mnt/media:/srv/media \
PA_AUTH_USER=agrumes PA_AUTH_PASSWORD='un-mot-de-passe-solide' \
./run.sh
```

## Guide d'utilisation

### 1. Dossier et séries

- **Dossier à analyser** : racine du scan. Tous les sous-dossiers sont parcourus, sauf `proc`, `sys`, `dev`, `run` et les motifs exclus.
- **Options d'analyse** : taille minimale, threads ffprobe (2 sur disque mécanique, 4–6 sur SSD), motifs d'exclusion (`@eaDir`, `#recycle`, `*.tmp`…), affichage des fichiers déjà AV1.
- **Dossiers de séries** : marquez les dossiers qui *contiennent* des séries. Chaque dossier de saison devient une ligne unique :
  - `Breaking Bad/S01/E01.mkv` → pack « Breaking Bad — S01 » ;
  - `Breaking Bad/E01.mkv` → pack du dossier « Breaking Bad » ;
  - les épisodes ne sont **pas** comparés individuellement dans la liste, mais leur détail est accessible via « Détail des … fichiers ».
- L'analyse est en lecture seule. Le bouton **Annuler** interrompt proprement le scan.

### 2. Résultats et sélection

- Résumé : nombre d'éléments, taille totale, gain potentiel, taille estimée après compression, durée.
- Tri par gain, gain %, taille, durée ou nom ; recherche plein texte ; filtres séries / fichiers / meilleurs gains / déjà AV1.
- Cochez des fichiers ou des packs entiers. Les fichiers déjà AV1 sont désactivés : ils ne sont jamais recompressés.
- Les erreurs (fichier illisible, ffprobe en échec) sont listées à part et ne bloquent pas le scan.

### 3. Réglages AV1

Presets rapides : **Rapide** (preset 10, CRF 34), **Équilibré** (8/32), **Qualité** (6/28), **Archivage** (4/24). Les valeurs restent modifiables.

| Réglage | Valeurs | Conseils |
| --- | --- | --- |
| Encodeur | `auto`, SVT-AV1, libaom, VAAPI | SVT-AV1 pour le CPU ; VAAPI seulement si `/dev/dri/renderD128` est disponible. |
| Preset | 0–13 | Plus bas = meilleure qualité mais plus lent. 8–10 pour un NAS. |
| CRF | 0–63 | Plus bas = meilleure qualité et fichier plus gros. 28–34 en 1080p. |
| Profondeur | 8 ou 10 bits | 10 bits conseillé pour le HDR et les dégradés. |
| Audio | copier / Opus / AAC / supprimer | « Copier » évite toute perte supplémentaire. |
| Conteneur | MKV / MP4 / WebM | MKV recommandé (sous-titres, compatibilité). |
| Sous-titres | copier / ignorer | Copie uniquement vers MKV. |

### 4. Originaux et destination

| Originaux | Comportement |
| --- | --- |
| **Garder** | L'original reste en place, la version AV1 est ajoutée à côté. |
| **Supprimer après vérification** | L'original n'est supprimé qu'après un ffprobe réussi sur la sortie. Action irréversible, confirmation explicite. |
| **Déplacer vers une corbeille** | Déplacement vers un dossier choisi, en conservant l'arborescence relative. |

| Sortie | Comportement |
| --- | --- |
| **Même dossier, nouveau nom** | `film.mp4` → `film.av1.mkv` (suffixe configurable). |
| **Même dossier, même nom** | Remplace le fichier source. Compatible uniquement avec « supprimer » (ou le remplacement assumé). |
| **Autre dossier** | Recrée l'arborescence relative du scan sous le dossier choisi. |

### 5. ETA et ressources

- Le benchmark encode 4 s de mire 1080p avec l'encodeur/preset choisi et mesure les images/seconde réelles.
- L'ETA combine la durée vidéo, le benchmark, le pourcentage de threads alloué, le nombre d'encodages simultanés et une marge de 12 %.
- Sans benchmark, une table indicative par CPU est utilisée : le badge **indicatif** le signale.
- Les processus sont lancés avec `nice 10` pour laisser le NAS réactif. Le pourcentage agit sur le nombre de threads (`lp` pour SVT-AV1), pas sur une isolation stricte du CPU.
- Le benchmark est accessible depuis **Matériel** et mis en cache par machine.

### 6. Test qualité

Depuis une ligne de résultat (fichier ou pack) :

1. Choisissez l'épisode à tester s'il s'agit d'un pack.
2. Réglez la durée (20 s par défaut) et la position (pourcentage ou seconde exacte).
3. Générez : Presse-Agrumes produit un aperçu original H.264 (lecture navigateur), un extrait brut MKV (téléchargement) et un extrait AV1 MP4.
4. Comparez côte à côte, téléchargez, puis ajustez les réglages si nécessaire.

Le gain affiché est calculé sur le **débit** (taille/durée) entre l'extrait brut et l'extrait AV1. La découpe sans réencodage peut inclure quelques secondes supplémentaires (calage sur image-clé) ; le texte de comparaison le précise.

### 7. Compression

- Le préflight vérifie les chemins, les permissions, les conflits de noms et l'espace disque **avant** de lancer ffmpeg.
- La sortie est écrite dans un fichier temporaire `.pa-tmp-*`, validée par ffprobe, puis renommée atomiquement.
- La progression affiche le fichier courant, le pourcentage, la vitesse, les fps, l'ETA, le journal ffmpeg et le résultat par fichier.
- L'historique des analyses permet de reprendre un scan sans rescanner le NAS.

## Comment fonctionne l'estimation du gain

Le facteur de gain dépend du codec source (H.264, HEVC, MPEG-2, etc.), du bits par pixel (bitrate / (largeur × hauteur × fps)) et d'un plafond de 90 %. Les fichiers déjà AV1 ont un gain nul. L'estimation est **pessimiste** : elle sert à trier les candidats, pas à garantir un résultat. Le test qualité reste la référence.

## Sécurité et permissions

- **Réseau local uniquement** : l'application peut lire, déplacer et supprimer des fichiers. N'exposez jamais le port directement sur Internet.
- `PA_ALLOWED_ROOTS` limite les chemins accessibles. Le navigateur de dossiers ne peut pas sortir de ces racines.
- `PA_AUTH_USER` / `PA_AUTH_PASSWORD` activent HTTP Basic. Pour du TLS, utilisez un reverse proxy.
- Les commandes ffmpeg sont construites sans shell, avec des listes d'arguments. Aucun nom de fichier n'est interprété par un shell.
- Les liens symboliques ne sont pas suivis pendant le scan (évite les boucles et les sorties de racine).
- L'original n'est jamais supprimé avant la validation ffprobe de la sortie.
- Si un fichier/dossier est illisible, il est signalé sans interrompre le scan. Si un dossier de sortie n'est pas inscriptible, le préflight renvoie une erreur explicite.
- L'application ne tourne pas en root : utilisez un utilisateur dédié avec les droits sur les médias.

## Structure du dépôt

```text
presse-agrumes/
├── presse_agrumes/          # backend FastAPI
│   ├── app.py               # routes HTTP, auth, SSE, SPA fallback
│   ├── jobs.py              # scan / compression / test, progression, annulation
│   ├── media.py             # ffprobe, estimation, commandes ffmpeg
│   ├── series.py            # regroupement des saisons/séries
│   ├── hardware.py          # détection matériel + benchmark + ETA
│   ├── paths.py             # garde-fous chemins, navigation, permissions
│   ├── models.py            # schémas Pydantic
│   ├── storage.py           # JSON atomique
│   └── config.py            # variables d'environnement, binaires
├── frontend/                # SPA React + TypeScript
│   ├── src/components/ui/   # composants shadcn/ui
│   ├── src/pages/           # workspace, historique, matériel
│   ├── src/lib/             # API typée, formats, estimation
│   ├── e2e/                 # test de fumée Playwright
│   └── dist/                # build versionné (démarrage sans Node)
├── tests/                   # pytest (unitaires + API + encodages réels)
├── docs/                    # architecture, API, développement, journal
├── deploy/                  # unité systemd + exemple d'environnement
├── scripts/dev.sh           # backend reload + Vite
├── analyze_videos.py        # script CLI historique (référence)
├── run.sh                   # démarrage clé en main
└── data/                    # généré, ignoré par git
```

## API

L'API REST est documentée automatiquement sur [`/docs`](http://localhost:8080/docs) (Swagger UI) et dans [`docs/API.md`](docs/API.md). Les routes principales :

- `POST /api/scans` puis `GET /api/jobs/{id}/events` (SSE) ;
- `GET /api/scans/{id}` ;
- `POST /api/preflight` ;
- `POST /api/compressions` ;
- `POST /api/tests` puis `GET /api/tests/{id}/meta` ;
- `GET /api/hardware`, `POST /api/hardware/benchmark` ;
- `GET /api/browse?path=…`.

Exemple de scan :

```bash
curl -X POST http://127.0.0.1:8080/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"root":"/mnt/media","options":{"series_roots":["/mnt/media/Series"]}}'
```

## Développement et tests

Voir [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) et [`AGENTS.md`](AGENTS.md).

```bash
# Backend
.venv/bin/python -m pytest

# Frontend
cd frontend
npm run typecheck
npm run build
npm run test:e2e   # nécessite un serveur lancé (ou Playwright le démarre)
```

Le test de fumée Playwright vérifie le chargement de la SPA, la navigation et l'absence d'erreurs console. Sur une VM Debian sans interface graphique, il faut installer Chromium et ses bibliothèques système ; c'est possible en headless (voir `docs/DEVELOPMENT.md`).

## Dépannage

### « ffmpeg est introuvable » / « Aucun encodeur AV1 »

```bash
which ffmpeg ffprobe
ffmpeg -hide_banner -encoders | grep -E 'libsvtav1|libaom-av1'
```

Sous systemd, le `PATH` est minimal : définissez `FFMPEG_BIN` et `FFPROBE_BIN` en chemins absolus.

### Le service ne voit pas les fichiers

Vérifiez que l'utilisateur du service a les droits :

```bash
sudo -u media test -r /mnt/media/film.mkv && echo lisible
sudo -u media test -w /mnt/media && echo inscriptible
```

Puis adaptez `User`, `Group`, les ACL ou `PA_ALLOWED_ROOTS`.

### Le frontend affiche « interface non compilée »

`frontend/dist/index.html` est absent. Lancez :

```bash
cd frontend && npm install && npm run build
```

ou copiez `frontend/dist` depuis une machine où il a été compilé.

### L'ETA est très approximative

Lancez un benchmark depuis la page **Matériel**. Sans benchmark, la table est générique et ne tient pas compte de la charge réelle du NAS.

### La vidéo compressée ne se lit pas dans le navigateur

Le test qualité produit un MP4/AAC exprès pour le navigateur. Le fichier final peut être en MKV/WebM/AV1 ; utilisez VLC, mpv ou un navigateur récent (Chrome/Firefox/Edge). Safari peut nécessiter des réglages supplémentaires.

### Un fichier est marqué « déjà AV1 » alors qu'il ne devrait pas

Vérifiez le codec avec :

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1 fichier
```

## Feuille de route

- Pause/reprise d'un job de compression, reprise après redémarrage.
- Notifications (webhook, Apprise, e-mail) en fin de job.
- Profils de compression par bibliothèque.
- Support des encodeurs matériels NVENC/QSV/AMF selon les builds ffmpeg.
- Comparateur de captures avant/après avec slider.
- Import de listes de lecture, détection de doublons.
- Dockerfile multi-arch et paquets de release.

## Licence

MIT — voir [`LICENSE`](LICENSE).

Le script historique [`analyze_videos.py`](analyze_videos.py) est conservé comme référence de la première version CLI ; l'application utilise désormais le moteur `presse_agrumes/media.py`.
