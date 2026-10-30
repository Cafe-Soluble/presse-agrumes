# Docker

L'image est publiée sur **GitHub Container Registry (GHCR)** :

```text
ghcr.io/cafe-soluble/presse-agrumes:latest
ghcr.io/cafe-soluble/presse-agrumes:0.6.0
ghcr.io/cafe-soluble/presse-agrumes:0.6
```

GHCR est le canal principal : intégration native avec GitHub Actions, pas de
limite de pull Docker Hub, image publique liée au dépôt. Un miroir Docker Hub
pourra être ajouté plus tard pour la découvrabilité.

Architectures : `linux/amd64` et `linux/arm64`.

## Installation en une commande

**Docker télécharge l'image.** Pas besoin de git, de curl, ni de `config.toml`
préexistant :

```bash
docker run -d --name presse-agrumes \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /mnt/media:/media \
  -v presse-agrumes:/data \
  ghcr.io/cafe-soluble/presse-agrumes:0.6.0
```

Au premier démarrage, l'entrypoint crée automatiquement :

- `/data/config.toml` avec un **mot de passe aléatoire** ;
- `data_dir = "/data"` ;
- `allowed_roots = ["/media"]`.

Récupérez le mot de passe :

```bash
docker logs presse-agrumes | grep -A6 "première configuration"
```

Puis ouvrez `http://<ip-du-nas>:8080`.

> Le mot de passe n'est affiché qu'à la première création. Il reste lisible dans
> le volume `/data` (`config.toml`). Pour le changer, éditez ce fichier puis
> redémarrez le conteneur.

Pour un montage hôte (plus facile à sauvegarder/éditer) :

```bash
mkdir -p /volume1/docker/presse-agrumes
sudo chown -R 1000:1000 /volume1/docker/presse-agrumes

docker run -d --name presse-agrumes \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /mnt/media:/media \
  -v /volume1/docker/presse-agrumes:/data \
  ghcr.io/cafe-soluble/presse-agrumes:0.6.0
```

Le fichier de configuration est alors
`/volume1/docker/presse-agrumes/config.toml`.

## Avec Docker Compose

```bash
mkdir -p data && sudo chown -R 1000:1000 data
docker compose up -d
docker compose logs | grep -A6 "première configuration"
```

Le Compose monte `./data:/data` et `/mnt/media:/media`. Adaptez l'UID/GID et le
chemin média. Le fichier `./data/config.toml` est créé au premier démarrage.

## UID/GID

Le conteneur tourne avec l'utilisateur `app`, UID/GID **1000** par défaut. Si
ton NAS utilise un autre UID (Synology 1026, Unraid 99…), ajoutez `--user` à
`docker run` ou `user:` dans Compose, et donnez-lui le volume `/data` :

```bash
id -u
id -g
sudo chown -R 1026:100 /volume1/docker/presse-agrumes
```

Le serveur doit aussi pouvoir lire les médias et écrire dans les dossiers de
sortie si tu utilises la suppression/déplacement.

## Modifier la configuration

Après le premier démarrage, éditez `config.toml` dans le volume `/data` :

```toml
[server]
host = "0.0.0.0"
port = 8080

[paths]
data_dir = "/data"
allowed_roots = ["/media", "/media2"]

[auth]
user = "agrumes"
password = "mon-nouveau-mot-de-passe"
disabled = false
```

Puis :

```bash
docker restart presse-agrumes
```

Le port interne doit correspondre au mapping Docker (côté conteneur). Le
conteneur démarre avec `--strict-port` : si le port est occupé, il échoue
proprement.

## Synology / Unraid / OMV

Ces interfaces savent coller un `docker-compose.yml` ou créer un conteneur
graphiquement. Montez au minimum :

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

1. **Port** : si `[server] port = 8080`, le mapping doit être `"8080:8080"` (ou
   `"9000:8080"` pour exposer 9000 sur l'hôte). Si tu changes le port dans
   `config.toml`, change aussi le côté conteneur du mapping.
2. **Chemins** : `allowed_roots` et `data_dir` sont des chemins **dans le
   conteneur**. Le wizard d'entrypoint génère des chemins absolus :
   `data_dir = "/data"` (volume `./data:/data`) et `allowed_roots = ["/media"]`
   (volume média monté sur `/media`).

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
Il est créé automatiquement au premier démarrage, avec `allowed_roots = ["/media"]`.

Le `config.toml` du dépôt (installation native) contient encore
`allowed_roots = ["/"]` comme valeur de démonstration. En Docker, la
configuration générée utilise déjà `["/media"]`. Si tu montes d'autres
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

Si `/dev/dri/renderD128` existe sur le NAS :

```yaml
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - video
      - render
```

Vérifiez les groupes de votre utilisateur média (`groups`, ou les GID dans
`/etc/group`). Sans VAAPI, l'application utilise SVT-AV1 en CPU.

## Fuseau horaire

La planification utilise l'heure locale du serveur. Dans Docker, le montage
suivant évite un décalage UTC :

```yaml
    volumes:
      - /etc/localtime:/etc/localtime:ro
```

## Mises à jour

```bash
docker compose pull
docker compose up -d
```

Pour une version stable, épinglez un tag précis plutôt que `latest` :

```yaml
image: ghcr.io/cafe-soluble/presse-agrumes:0.6.0
```

Les données et la configuration sont sur des volumes : un `pull` ne les efface
pas. Sauvegardez malgré tout `config.toml` et `data/` avant une mise à jour.

## Construction locale

```bash
docker build -t presse-agrumes:local .
docker run --rm -p 8080:8080 \
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

### « Permission denied » sur `data/` ou les médias

L'UID/GID du conteneur ne correspond pas au propriétaire. Adaptez `user:` et
`chown`, ou vérifiez les ACL du partage.

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
conséquence, ou gardez 8080.

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
