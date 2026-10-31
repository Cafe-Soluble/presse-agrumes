# Docker

L'image est publiée sur **GitHub Container Registry (GHCR)** :

```text
ghcr.io/cafe-soluble/presse-agrumes:latest
ghcr.io/cafe-soluble/presse-agrumes:0.11.1
ghcr.io/cafe-soluble/presse-agrumes:0.7
```

GHCR est le canal principal : intégration native avec GitHub Actions, pas de
limite de pull Docker Hub, image publique liée au dépôt. Un miroir Docker Hub
peut être activé pour obtenir un nom plus court.

Architectures : `linux/amd64` et `linux/arm64`.

## Installation recommandée : Docker Compose

C'est le chemin principal. **Un seul fichier à télécharger** (`docker-compose.yml`)
et **aucun `config.toml` à créer** : l'application génère sa configuration au
premier démarrage.

### 1. Télécharger le Compose

```bash
mkdir -p presse-agrumes/data
cd presse-agrumes

# Le conteneur tourne avec l'UID/GID de « user: » (1000 par défaut).
sudo chown -R 1000:1000 data

curl -fsSLO https://github.com/Cafe-Soluble/presse-agrumes/releases/latest/download/docker-compose.yml
```

Le fichier est joint à chaque release : il correspond exactement à la version
de l'image publiée.

### 2. Adapter les 3 valeurs

Ouvre `docker-compose.yml` et repère les lignes marquées **« À ADAPTER »** :

| Ligne | Format | Ce qui est attendu |
| --- | --- | --- |
| `user: "1000:1000"` | `UID:GID` | L'utilisateur qui possède `./data` et les médias. `id -u` et `id -g`. |
| `- "8473:8473"` | `port navigateur:port interne` | À gauche, le port sur le NAS. À droite, 8473 : le port interne, ne pas changer. |
| `- /volume1/media:/media` | `hôte:conteneur` | À gauche, le dossier média **réel sur le NAS** (il doit exister). À droite, `/media` : le chemin vu par l'application, ne pas changer. |

Deux façons de monter les médias :

- **dossier exact** : `- /volume1/media:/media`, ou `- /srv/media:/media` sur OMV ;
- **racine du partage** : `- /srv:/srv` (OMV), `- /volume1:/volume1` (Synology),
  `- /mnt:/mnt` (Unraid). L'assistant permet ensuite de choisir le sous-dossier,
  sans retoucher le Compose.

Vérifie le chemin hôte avant de démarrer : `ls -ld /srv`. Ne monte jamais `/`.

### 3. Démarrer

```bash
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

Le mot de passe est généré et affiché une seule fois. Si la ligne
« première configuration » n'apparaît pas, le conteneur s'est arrêté avant :
voir la section Dépannage. Ouvre ensuite `http://<ip-du-nas>:8473` avec
l'utilisateur `agrumes`.

- La configuration est créée dans `./data/config.toml` (à côté du Compose).
- Au premier lancement, un assistant propose de choisir le dossier média
  (ou « Plus tard »).
- Le dossier `./data` doit exister et être inscriptible par l'UID de `user:`.
  Crée-le avec le bon utilisateur, ou :
  ```bash
  sudo chown -R 1000:1000 data
  ```

## Comprendre les chemins : hôte vs conteneur

Tous les volumes Docker suivent le format **`hôte:conteneur`** :

| Dans le Compose | Côté | Exemple | Rôle |
| --- | --- | --- | --- |
| `- /volume1/media:/media` | **hôte** | `/volume1/media` | Le dossier réel sur le NAS. Il doit exister et être lisible. |
| | **conteneur** | `/media` | Le chemin vu par l'application. Fixe. |
| `- ./data:/data` | **hôte** | `./data` | Dossier du projet : config générée, scans, jobs, tests. |
| | **conteneur** | `/data` | Chemin vu par l'application. Fixe. |

Conséquences :

- `config.toml` ne contient que des chemins **conteneur** : `/data` et
  `allowed_roots = ["/media"]`. Il ne connaît pas `/volume1`.
- Pour ajouter un second partage, monte-le sur un autre chemin conteneur, puis
  ajoute ce chemin dans `allowed_roots` :
  ```yaml
  - /volume2/films:/media2
  ```
  ```toml
  allowed_roots = ["/media", "/media2"]
  ```
- Si tu utilises la suppression/déplacement des originaux, le montage média
  doit être en écriture (pas de `:ro`).

## Variante : `docker run` (annexe)

Sans Compose, avec un volume nommé pour la configuration :

```bash
docker run -d --name presse-agrumes \
  --restart unless-stopped \
  -p 8473:8473 \
  -v /volume1/media:/media \
  -v presse-agrumes:/data \
  ghcr.io/cafe-soluble/presse-agrumes:0.11.1

docker logs presse-agrumes | grep -A6 "première configuration"
```

Même règle : `/volume1/media` est le chemin **hôte**, `/media` le chemin
**conteneur**. La configuration vit dans le volume nommé `presse-agrumes` ;
pour l'éditer, utilise `docker cp` ou préfère Compose avec `./data`.

## Nom court via Docker Hub (optionnel)

L'image peut aussi être publiée en miroir sur Docker Hub pour obtenir la
commande la plus courte possible :

```text
cafesoluble/presse-agrumes:0.11.1
```

Docker Hub n'accepte que des lettres minuscules et des chiffres dans un
identifiant : `cafe-soluble` (avec tiret) n'est pas un namespace valide. Le
namespace naturel du projet est donc `cafesoluble`.

Le workflow `.github/workflows/docker.yml` publie ce miroir automatiquement si
les secrets suivants sont définis (Settings → Secrets and variables → Actions) :

| Secret | Valeur |
| --- | --- |
| `DOCKERHUB_USERNAME` | `cafesoluble` |
| `DOCKERHUB_TOKEN` | token d'accès Docker Hub (Read & Write) |

Sans ces secrets, les étapes Docker Hub sont ignorées : GHCR reste seul canal.
Après leur ajout, pousse un nouveau tag (`v0.7.2`, `v0.8.0`…) pour publier les
tags de version, puis :

```bash
docker pull cafesoluble/presse-agrumes:0.11.1
```

Les tags publiés sont `<version>`, `<major>.<minor>`, la branche, le SHA court
et `latest`.

## Modifier la configuration

Après le premier démarrage, éditez `./data/config.toml` (ou le volume `/data`) :

```toml
[server]
host = "0.0.0.0"
port = 8473

[paths]
data_dir = "/data"
allowed_roots = ["/media", "/media2"]

[auth]
user = "agrumes"
password = "mon-nouveau-mot-de-passe"
disabled = false
```

Le mot de passe peut aussi être changé depuis l'interface : bouton **clé** en
haut à droite. Il est réécrit dans `config.toml` et prend effet immédiatement,
sans redémarrage.

Puis, pour les autres réglages :

```bash
docker compose restart
# ou, sans Compose : docker restart presse-agrumes
```

Le port interne doit correspondre au mapping Docker (côté conteneur). Le
conteneur démarre avec `--strict-port` : si le port est occupé, il échoue
proprement.

## Synology / Unraid / OMV

Ces interfaces savent importer le `docker-compose.yml` de la release ou créer
un conteneur graphiquement. Dans les deux cas, montez au minimum :

- un volume persistant sur `/data` (configuration + données) ;
- vos médias sur `/media` ;
- éventuellement `/etc/localtime` en lecture seule et `/dev/dri`.

Aucune configuration préalable n'est nécessaire : le mot de passe est généré et
affiché dans les logs du conteneur.

## `config.toml` et `docker-compose.yml` : qui fait quoi ?

Ce ne sont pas des doublons. Ils agissent à deux niveaux différents :

| Réglage | `config.toml` | `docker-compose.yml` |
| --- | --- | --- |
| Mot de passe / utilisateur | **oui** | non |
| `allowed_roots` (chemins autorisés) | **oui** | non |
| Port interne de l'application | **oui** | mapping `hôte:conteneur` |
| `data_dir` | **oui** (chemin dans le conteneur) | volume `./data:/data` |
| Médias | chemins vus dans le conteneur | volumes hôte → conteneur |
| UID/GID | non | **oui** (`user:`) |
| VAAPI / `/dev/dri` | non | **oui** (`devices:`) |
| Restart, healthcheck | non | **oui** |
| ffmpeg/ffprobe | **oui** (`[ffmpeg]`) | non |

En résumé :

- **l'application** lit uniquement `config.toml` ;
- **Docker** lit uniquement `docker-compose.yml` ;
- Compose ne connaît pas ton mot de passe ni tes règles de sécurité ;
- l'application ne sait pas comment Docker monte les volumes.

Deux points de cohérence sont à surveiller :

1. **Port** : si `[server] port = 8473`, le mapping doit être `"8473:8473"` (ou
   `"9000:8473"` pour exposer 9000 sur l'hôte). Si tu changes le port dans
   `config.toml`, change aussi le côté conteneur du mapping.
2. **Chemins** : `allowed_roots` et `data_dir` sont des chemins **dans le
   conteneur**. L'entrypoint génère des chemins absolus :
   `data_dir = "/data"` (volume `./data:/data`) et `allowed_roots` couvrant
   `/media`, `/mnt`, `/srv`, `/volume1`, `/volume2`. Montez le partage média
   sur l'un de ces chemins, puis choisis le dossier exact dans l'assistant.

Le mot de passe est donc uniquement dans `/data/config.toml` (volume), jamais
dans Compose ni dans l'image finale. Un seul endroit à sauvegarder/protéger.

## Fonctionnement des volumes

| Hôte | Conteneur | Rôle |
| --- | --- | --- |
| `./data` | `/data` | Configuration générée, scans, jobs, tests, benchmarks. |
| `/mnt/media` | `/media` | Médias à analyser/compresser. |
| `/etc/localtime` | `/etc/localtime` (ro) | Fuseau horaire pour la planification. |
| `/dev/dri` (option) | `/dev/dri` | Accélération VAAPI. |

Le fichier généré utilise `data_dir = "/data"` : il est monté sur `./data`.
Il est créé automatiquement au premier démarrage, avec `allowed_roots`
couvrant les montages courants (`/media`, `/mnt`, `/srv`, `/volume1`,
`/volume2`).

Le `config.toml` du dépôt (installation native) contient encore
`allowed_roots = ["/"]` comme valeur de démonstration. En Docker, la
configuration générée est déjà restreinte à ces montages. Si tu montes d'autres
partages, ajoute-les dans `/data/config.toml` :

```toml
[paths]
data_dir = "/data"
allowed_roots = ["/media", "/media2"]
```

## UID/GID et permissions

Le conteneur tourne avec l'utilisateur `app`, UID/GID **1000** par défaut. C'est
le cas le plus courant, mais pas universel (Synology utilise souvent 1026,
certains Unraid 99).

```bash
id -u          # UID de votre utilisateur média
id -g          # GID
```

Puis dans `docker-compose.yml` :

```yaml
user: "1026:100"   # exemple Synology
```

Le dossier `./data` doit appartenir à cet UID/GID. Les médias doivent être
**lisibles**, et les dossiers de sortie/origineux **inscriptibles** si vous
utilisez la suppression, le déplacement ou une sortie dans le même dossier.

```bash
sudo chown -R 1026:100 data
```

## VAAPI / GPU

Par défaut, le conteneur ne voit pas le GPU : `/dev/dri` doit être monté
explicitement. C'est pour cela que le diagnostic peut afficher
« Aucun périphérique /dev/dri/renderD128 ».

### 1. Vérifier le NAS

```bash
ls -l /dev/dri
# attendu : card0 et renderD128
id
getent group video
stat -c '%g %n' /dev/dri/renderD128
```

### 2. Autoriser le conteneur

Utilise des **GID numériques**. Les noms `video` et `render` ne sont pas
forcément présents dans `/etc/group` de l'image, et Docker échoue alors avec
`Unable to find group render`.

```bash
getent group video          # exemple : video:x:44:
stat -c '%g' /dev/dri/renderD128   # exemple : 105
```

Dans `docker-compose.yml`, remplace les valeurs par les tiennes :

```yaml
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "44"     # GID de video
      - "105"    # GID de renderD128
```

Puis recrée le conteneur (un simple restart ne suffit pas) :

```bash
docker compose up -d --force-recreate
```

### 3. Vérifier dans le conteneur

```bash
docker exec presse-agrumes ls -l /dev/dri
docker exec presse-agrumes vainfo
```

Depuis la version 0.10.1, l'image contient `vainfo`, les pilotes Mesa et, en
amd64, le pilote Intel non-free (avec repli sur i965). Sans pilote userspace,
`/dev/dri` seul ne suffit pas.

Les messages `XDG_RUNTIME_DIR is invalid` et `can't connect to X server` sont
normaux en headless : `vainfo` bascule sur DRM et affiche ensuite le driver et
les profils.

### 4. Lire le diagnostic

La page Matériel affiche un tableau par codec. Une croix signifie que le
matériel ou le pilote ne sait pas faire cette opération, même si ffmpeg
contient l'encodeur. Causes fréquentes :

- pas de `/dev/dri` dans le conteneur : ajouter `devices` ;
- permissions : ajouter les groupes `video` et `render` ;
- `vainfo` absent ou driver manquant : mettre à jour l'image ou installer le
  pilote sur le NAS ;
- profil non supporté par le GPU : aucun contournement logiciel.

Sur un Pentium G5400 (UHD 610), l'encodage AV1 matériel n'existe pas et l'AV1
reste en CPU. Le H.265 matériel peut être disponible. Sans VAAPI, l'application
utilise SVT-AV1 ou libx265 en CPU.

## Fuseau horaire

La planification utilise l'heure locale du serveur. Dans Docker, le montage
suivant évite un décalage UTC :

```yaml
    volumes:
      - /etc/localtime:/etc/localtime:ro
```

## Mises à jour

Le Compose de la release épingle une version précise :

```yaml
image: ghcr.io/cafe-soluble/presse-agrumes:0.11.1
```

Pour monter de version, remplace ce numéro par celui de la nouvelle release
(ou reprends le `docker-compose.yml` de cette release), puis :

```bash
docker compose pull
docker compose up -d
```

Pour des mises à jour automatiques, utilise `:latest` à la place du numéro.

Les données et la configuration sont dans `./data` : un `pull` ne les efface
pas. Sauvegarde `./data` avant une mise à jour.

## Construction locale

```bash
docker build -t presse-agrumes:local .
docker run --rm -p 8473:8473 \
  -v "$PWD/data:/data" \
  -v /mnt/media:/media \
  -v /etc/localtime:/etc/localtime:ro \
  presse-agrumes:local
```

## Healthcheck

L'image appelle `GET /healthz` (accessible sans authentification, aucune donnée
sensible). Le healthcheck lit le port réel dans `/data/config.toml`.

```bash
docker inspect --format '{{json .State.Health}}' presse-agrumes
```

## Dépannage

### Aucune ligne « première configuration »

Le conteneur n'a pas pu créer `/data/config.toml` : il a quitté avant.

```bash
docker compose ps -a          # doit montrer Exited (1)
docker compose logs --tail=50
```

Message typique :

```text
ERREUR : /data n'est pas inscriptible par l'utilisateur du conteneur (UID 1000).
```

Cause : `./data` appartient à root (ou à un autre UID) alors que le conteneur
tourne avec `user: "1000:1000"`. Correction :

```bash
sudo chown -R 1000:1000 data
docker compose up -d --force-recreate
docker compose logs | sed -n '/première configuration/,+8p'
```

Adapte `1000:1000` aux valeurs de `user:` si tu les as changées.

### « Permission denied » sur `data/` ou les médias

L'UID/GID du conteneur ne correspond pas au propriétaire. Adapte `user:` et
fais `chown` sur `./data` (et éventuellement les médias), ou vérifie les ACL du
partage. Le conteneur doit pouvoir **lire** les médias et **écrire** dans les
dossiers de sortie pour la suppression/déplacement.

### Le conteneur redémarre en boucle

```bash
docker compose logs presse-agrumes
```

Causes fréquentes : volume `/data` non inscriptible (UID/GID), port occupé
(`--strict-port`), `allowed_roots` incorrect, configuration invalide après
édition.

### `config.toml` non lu

Le fichier généré est `/data/config.toml`. Il doit être lisible par l'UID du
conteneur. Après le premier démarrage, il est modifiable sur l'hôte (volume
`./data`) ou via `docker cp` avec un volume nommé.

### Le port change

Le port interne est celui de `config.toml`. Mettez à jour `ports:` en
conséquence, ou gardez 8473.

### ARM64 et ffmpeg

L'image est construite pour `arm64`. Si le ffmpeg Debian de l'image n'a pas
SVT-AV1, l'application utilise libaom (plus lent). Vérifiez :

```bash
docker compose exec presse-agrumes ffmpeg -hide_banner -encoders | grep -E 'libsvtav1|libaom-av1'
```

## Publier l'image

Le workflow `.github/workflows/docker.yml` construit et pousse l'image sur tag
`v*` (et sur `main`) avec les plateformes amd64/arm64. Après le premier push,
rendez le package **public** dans GitHub → Packages → Presse-Agrumes → Package
settings → Change visibility.

Tags générés :

- `vX.Y.Z` → `X.Y.Z`, `X.Y`, `latest` (release stable) ;
- branche `main` → `main` ;
- commit → `sha-…`.
