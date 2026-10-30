# Docker

L'image est publiée sur **GitHub Container Registry (GHCR)** :

```text
ghcr.io/cafe-soluble/presse-agrumes:latest
ghcr.io/cafe-soluble/presse-agrumes:0.5.0
ghcr.io/cafe-soluble/presse-agrumes:0.5
```

GHCR est le canal principal : intégration native avec GitHub Actions, pas de
limite de pull Docker Hub, image publique liée au dépôt. Un miroir Docker Hub
pourra être ajouté plus tard pour la découvrabilité.

Architectures : `linux/amd64` et `linux/arm64`.

## Télécharger l'image

**Docker est le téléchargeur.** Pas besoin de git sur le NAS :

```bash
docker pull ghcr.io/cafe-soluble/presse-agrumes:0.5.0
```

`docker compose up` effectue ce pull automatiquement. `git` n'est utile que
pour développer ou installer depuis les sources. Pour Docker, il faut seulement
deux fichiers : `config.toml` et `docker-compose.yml`.

## Démarrage rapide sans git

```bash
mkdir -p ~/presse-agrumes
cd ~/presse-agrumes

# 1. Récupérez les deux fichiers (ou téléchargez-les depuis GitHub).
curl -fsSLO https://raw.githubusercontent.com/Cafe-Soluble/presse-agrumes/v0.5.0/config.toml
curl -fsSLO https://raw.githubusercontent.com/Cafe-Soluble/presse-agrumes/v0.5.0/docker-compose.yml

# 2. Éditez config.toml : mot de passe, allowed_roots, port.
nano config.toml
chmod 600 config.toml

# 3. Préparez le dossier de données (UID/GID du conteneur, 1000 par défaut).
mkdir -p data
sudo chown -R 1000:1000 data

# 4. Adaptez les volumes média dans docker-compose.yml (/mnt/media),
#    puis démarrez (l'image est tirée depuis GHCR).
docker compose up -d
docker compose logs -f
```

Puis ouvrez `http://<ip-du-nas>:8080` avec les identifiants de `config.toml`.

> Le port interne vient de `[server] port` dans `config.toml`. Le `ports:` de
> Compose doit mapper ce port. Le conteneur démarre avec `--strict-port` : si le
> port est occupé dans le conteneur, il échoue proprement au lieu de basculer
> silencieusement sur un autre port.

### Variante `docker run` (sans Compose)

Une fois `config.toml` créé et le dossier `data/` préparé :

```bash
docker run -d --name presse-agrumes \
  --restart unless-stopped \
  --user 1000:1000 \
  -p 8080:8080 \
  -v "$PWD/config.toml:/app/config.toml:ro" \
  -v "$PWD/data:/app/data" \
  -v /mnt/media:/mnt/media \
  -v /etc/localtime:/etc/localtime:ro \
  ghcr.io/cafe-soluble/presse-agrumes:0.5.0
```

Sans montage de `config.toml`, l'image démarre avec son fichier par défaut
(mot de passe `changez-moi`, `allowed_roots = ["/"]`) : ce n'est pas
recommandé en production.

### Synology / Unraid / OMV

Ces interfaces savent coller un `docker-compose.yml` ou créer un conteneur
graphiquement. Il suffit alors de monter `config.toml`, `data/` et les médias,
sans passer par git. Les chemins d'hôte et l'UID/GID diffèrent selon le NAS :
voir les sections suivantes.

## `config.toml` et `docker-compose.yml` : qui fait quoi ?

Ce ne sont pas des doublons. Ils agissent à deux niveaux différents :

| Réglage | `config.toml` | `docker-compose.yml` |
| --- | --- | --- |
| Mot de passe / utilisateur | **oui** | non |
| `allowed_roots` (chemins autorisés) | **oui** | non |
| Port interne de l'application | **oui** | mapping `hôte:conteneur` |
| `data_dir` | **oui** (chemin dans le conteneur) | volume `./data:/app/data` |
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
   conteneur**. Les volumes Compose doivent exposer les médias à ces chemins.
   Avec le fichier par défaut, `data_dir = "./data"` devient `/app/data`
   (relatif à `/app/config.toml`), monté par `./data:/app/data`.

C'est pour cette raison que le Compose monte le fichier de configuration en
lecture seule : une seule source de vérité pour l'application, un seul endroit
pour le mot de passe.

## Fonctionnement des volumes

| Hôte | Conteneur | Rôle |
| --- | --- | --- |
| `./config.toml` | `/app/config.toml` (ro) | Configuration unique, mot de passe. |
| `./data` | `/app/data` | Scans, jobs, tests, benchmarks. |
| `/mnt/media` | `/mnt/media` | Médias à analyser/compresser. |
| `/etc/localtime` | `/etc/localtime` (ro) | Fuseau horaire pour la planification. |
| `/dev/dri` (option) | `/dev/dri` | Accélération VAAPI. |

Le `config.toml` par défaut utilise `data_dir = "./data"` : dans le conteneur,
le chemin est résolu par rapport à `/app/config.toml`, donc `/app/data`, monté
sur `./data`.

`allowed_roots` par défaut vaut `["/"]` dans le dépôt. Pour un NAS, restreignez
à ce qui est monté, par exemple :

```toml
[paths]
data_dir = "./data"
allowed_roots = ["/mnt/media"]
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
image: ghcr.io/cafe-soluble/presse-agrumes:0.5.0
```

Les données et la configuration sont sur des volumes : un `pull` ne les efface
pas. Sauvegardez malgré tout `config.toml` et `data/` avant une mise à jour.

## Construction locale

```bash
docker build -t presse-agrumes:local .
docker run --rm -p 8080:8080 \
  -v "$PWD/config.toml:/app/config.toml:ro" \
  -v "$PWD/data:/app/data" \
  -v /mnt/media:/mnt/media \
  -v /etc/localtime:/etc/localtime:ro \
  presse-agrumes:local
```

## Healthcheck

L'image appelle `GET /healthz` (accessible sans authentification, aucune donnée
sensible). Le healthcheck lit le port réel dans `/app/config.toml`.

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

Causes fréquentes : `config.toml` absent/non lisible, mot de passe vide,
`allowed_roots` incorrect, port occupé (`--strict-port`), données non
inscriptibles.

### `config.toml` non lu

Le fichier doit être monté sur `/app/config.toml` et lisible par l'UID du
conteneur. Avec un montage read-only, c'est normal que l'application ne puisse
pas le modifier : elle n'en a pas besoin.

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
