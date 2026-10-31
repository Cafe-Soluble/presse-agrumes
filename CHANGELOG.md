# Changelog

## [0.10.2] - 2026-10-31

### Modifié

- **VAAPI** : le Compose et la documentation utilisent des **GID numériques**
  pour `group_add`. Les noms `video` et `render` ne sont pas toujours présents
  dans `/etc/group` de l'image, ce qui provoque
  `Unable to find group render` au démarrage.
- Documentation : commandes `getent group video` et
  `stat -c '%g' /dev/dri/renderD128`, et explication des messages `XDG_RUNTIME_DIR`
  et `can't connect to X server` de vainfo en headless.

## [0.10.1] - 2026-10-31

### Corrigé

- **VAAPI dans Docker** : l'image ne contenait ni `vainfo` ni pilote userspace,
  donc `/dev/dri` seul ne suffisait pas. L'image installe maintenant `vainfo`,
  `libva2`, `libva-drm2`, les pilotes Mesa et, en amd64, le pilote Intel
  non-free avec repli sur i965.
- **Documentation VAAPI** : montage de `/dev/dri`, groupes `video`/`render`,
  recréation du conteneur, vérification avec `vainfo`, lecture du tableau de
  diagnostic et causes d'échec.

## [0.10.0] - 2026-10-31

### Ajouté

- **Codec H.265 / HEVC** : choix AV1 ou H.265, avec libx265 (logiciel),
  hevc_vaapi et hevc_qsv (matériel si réellement utilisable). Les libellés et
  plages s'adaptent (CRF logiciel, QP matériel), et un avertissement rappelle
  que l'encodage matériel produit des fichiers plus gros.
- **Benchmark sur fichier réel** : le bouton « Calibrer » encode 3 extraits
  répartis sur la durée du fichier (20 %, 50 %, 80 %), avec les réglages réels,
  puis retient la vitesse médiane, le minimum et le maximum. La taille finale
  estimée est calculée à partir du débit des extraits. Le résultat est mis en
  cache.
- **Diagnostic matériel VAAPI** : tableau par codec (H.264, H.265 8/10 bits,
  AV1, VP9, MPEG-2, VC-1) avec décodage/encodage réels selon vainfo, présence de
  l'encodeur ffmpeg, test réel d'encodage, et cause explicite en cas d'échec
  (/dev/dri absent, permissions, driver, profil non supporté).

### Modifié

- L'ETA initiale utilise le benchmark réel quand il existe, au lieu d'une mire
  synthétique de 4 secondes.
- Le cache benchmark distingue encodeur, preset, CRF, threads et fichier réel.

## [0.9.0] - 2026-10-31

### Ajouté

- **Création de dossier** dans l'explorateur (corbeille, dossier de sortie,
  séries, racine), avec validation du nom et des permissions.
- **Espace disque** : espace libre et taux d'utilisation visibles, contrôle
  avant lancement, blocage si la sortie estimée dépasse l'espace libre, et
  avertissement lorsqu'une partie seulement des fichiers peut être compressée.
- **Historique des compressions** : jobs terminés, annulés ou en erreur, avec
  nombre de fichiers, gain réel, encodeur et échecs.
- **Nettoyage des noms** : option pour retirer x264, x265, H264, H265, HEVC,
  AV1 et variantes du nom de sortie.
- **Téléchargement des extraits de test** : bouton de téléchargement sur chaque
  aperçu, tailles explicites pour l'aperçu et la copie brute, explication de la
  différence de taille et d'audio.

### Modifié

- **Ordre de la page** : Réglages de compression (étape 2) avant Résultats de
  l'analyse (étape 3).
- **Typographie** : suppression de tous les tirets cadratins du projet et règle
  ajoutée dans `AGENTS.md`.

### Corrigé

- Confusion sur l'extrait original de test : l'aperçu H.264/AAC (9,2 Mo dans
  l'exemple) et la copie brute MKV (27,3 Mo) sont deux fichiers différents,
  désormais clairement étiquetés et téléchargeables séparément.

## [0.8.2] - 2026-10-31

### Corrigé

- **Analyse active perdue en changeant de page** : les liens « Matériel » et
  « Historique » perdent le paramètre `?scan=`, donc l'analyse affichée
  disparaissait et il fallait la rouvrir. L'identifiant est maintenant mémorisé
  (`localStorage`) et restauré au retour sur la page Compression.
- Si l'analyse mémorisée n'existe plus, l'alerte propose un bouton **Fermer**
  qui efface la référence au lieu de bloquer la page.

## [0.8.1] - 2026-10-31

### Corrigé

- **Gain potentiel figé quel que soit le preset** : le scan calcule un gain de
  référence (CRF 32) et l'interface l'affichait tel quel. Le gain est maintenant
  ajusté au CRF choisi :
  - « Archivage » (CRF 24) → gain plus faible, sortie plus grosse ;
  - « Rapide » (CRF 34) → gain plus élevé, sortie plus petite.
- L'ajustement s'applique au résumé « Gain potentiel / Après compression », aux
  lignes et aux épisodes, au tri par gain, à la sortie estimée et au préflight
  (donc à la vérification d'espace disque).

### Technique

- `media.adjusted_gain_for_crf` (serveur) et `adjustedGain` (miroir frontend)
  utilisent la même formule : ±16 CRF ≈ ×2 sur le débit, avec bornes.
- Tests : le préflight à CRF 24 doit estimer une sortie plus grosse qu'à CRF 34.

## [0.8.0] - 2026-10-31

### Ajouté

- **Changement de mot de passe depuis l'interface** : bouton clé dans l'en-tête,
  route `POST /api/auth/password`, écriture dans `config.toml` sans redémarrage.
  L'ancien mot de passe est exigé, le nouveau doit faire 8 caractères minimum.
- **Annulation des analyses** : bouton « Annuler » dans la bannière des jobs
  actifs pour les scans et les tests qualité (l'API `cancel` existait déjà, elle
  est maintenant accessible sans ouvrir le panneau de progression).

### Corrigé

- **Explorateur de dossiers** : plus de requête sur `/` avant le chargement des
  racines (message « Accès refusé à / : hors des racines autorisées »). Un ancien
  chemin `/` mémorisé est ignoré si `/` n'est pas autorisé.
- **Assistant de premier démarrage** : les racines vides (`/mnt`, `/srv`…)
  ne sont plus proposées quand un média est déjà monté ; elles restent visibles
  uniquement si aucun média n'est trouvé, avec l'explication.

### Modifié

- **README** : guide Docker Compose pas-à-pas (téléchargement, 3 valeurs,
  chemins hôte/conteneur, démarrage, mise à jour, dépannage), inspiré des guides
  d'auto-hébergement grand public.
- Documentation API et compose mise à jour (version `0.8.0`).

## [0.7.3] - 2026-10-31

### Modifié

- **Démarrage Docker** : si `/data` n'est pas inscriptible, l'entrypoint affiche
  l'UID du conteneur et la commande `chown` exacte à exécuter sur l'hôte. C'est
  la cause la plus fréquente d'un conteneur qui s'arrête avant d'afficher le mot
  de passe.
- **Message de première configuration** : il liste les racines autorisées
  (`/media`, `/mnt`, `/srv`, `/volume1`, `/volume2`) au lieu d'indiquer
  uniquement `/media`, ce qui était trompeur quand le partage était monté
  ailleurs, et affiche l'URL d'accès (`http://<IP-du-NAS>:8473`).
- **`docker-compose.yml`** : étapes explicites `chown` + vérification des logs,
  et deux stratégies de montage média (dossier exact ou racine du partage :
  `/srv` sur OMV, `/volume1` sur Synology, `/mnt` sur Unraid).

### Documentation

- Dépannage « aucune ligne première configuration » (`Exited (1)`,
  « /data n'est pas inscriptible », correction `chown`).
- Rappel que l'assistant ne peut choisir que dans les chemins **déjà montés**,
  et qu'il ne faut jamais monter `/`.

## [0.7.2] - 2026-10-31

### Modifié

- **Installation Docker réorganisée autour de Compose** : le
  `docker-compose.yml` est joint à chaque release GitHub
  (`releases/latest/download/docker-compose.yml`). Un seul fichier à
  télécharger, 3 valeurs à adapter (UID/GID, port, dossier média).
- **`docker-compose.yml`** : valeurs directement dans le fichier (plus de
  `.env`), commentaires « À ADAPTER » et rappel explicite du format
  `hôte:conteneur` pour chaque volume.
- **Documentation** : chemin recommandé unique (Compose), `docker run` en
  annexe, tableau hôte/conteneur, configuration toujours auto-générée dans
  `./data/config.toml` au premier démarrage.
- **CI** : job `release` qui publie le Compose en asset de release pour les
  tags `v*`.

## [0.7.1] - 2026-10-31

### Modifié

- **Port par défaut 8473** au lieu de 8080, en natif comme en Docker/Compose.
  8080 est très souvent occupé (proxys, autres applications), ce qui provoquait
  des conflits ou des bascules de port. Le scan automatique continue vers 8474,
  8475… en cas de conflit.
- `Dockerfile` : `EXPOSE 8473`, healthcheck inchangé (lit le port réel dans
  `/data/config.toml`).
- Documentation, exemples `curl`/`docker run`, proxy Vite et smoke test CI
  alignés sur 8473.

> Les installations existantes conservent le port de leur `config.toml` ; seule
> une configuration générée ou le fichier du dépôt change.

## [0.7.0] - 2026-10-31

### Ajouté

- **Assistant de premier démarrage** : au premier lancement, l'interface propose
  de choisir le dossier média parmi les racines autorisées (ou « Plus tard »).
  Le choix est mémorisé dans `data/settings.json` et préremplit l'étape 1.
- Routes `GET /api/setup` et `POST /api/setup` (validation par `guard_path`,
  refus des chemins hors `allowed_roots`).
- L'explorateur de dossiers s'ouvre sur une racine autorisée non vide : en
  Docker, `/` n'est plus proposé par erreur.

### Modifié

- **Racines Docker par défaut élargies** : `/media`, `/mnt`, `/srv`,
  `/volume1`, `/volume2`, pour pouvoir monter le partage média sur l'un de ces
  chemins puis le choisir dans l'assistant.
- Workflow Docker : miroir **Docker Hub optionnel**
  (`cafesoluble/presse-agrumes`), activé par les secrets
  `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`.

### Corrigé

- Test e2e : fermeture de l'assistant sur une installation neuve ; « Plus
  tard » reste mémorisé (localStorage) et ne réapparaît plus à chaque visite.

## [0.6.0] - 2026-10-30

### Modifié

- **Installation Docker en une commande** : plus besoin de git, curl, Compose ni
  fichier de configuration préexistant.
  `docker run ... -v /mnt/media:/media -v presse-agrumes:/data <image>`.
- **Configuration générée au premier démarrage** dans `/data/config.toml`
  (volume persistant), avec mot de passe aléatoire affiché dans les logs,
  `data_dir = "/data"` et `allowed_roots = ["/media"]`.
- Entrypoint Docker dédié (`docker/entrypoint.sh`), healthcheck sur
  `/data/config.toml`.
- Smoke test CI : construction de l'image, démarrage, vérification de
  `/healthz` et de la création de `/data/config.toml`.
- Documentation Docker simplifiée (une commande + `docker logs`).

## [0.5.0] - 2026-10-30

### Ajouté

- **Image Docker multi-arch** (`linux/amd64`, `linux/arm64`) avec ffmpeg,
  tini, utilisateur non-root, healthcheck, volume `/app/data` et configuration
  montée en lecture seule.
- **`docker-compose.yml`** prêt à adapter (UID/GID, médias, VAAPI, fuseau
  horaire).
- **Workflow GitHub Actions** de tests + build/push de l'image sur
  **GHCR** (`ghcr.io/cafe-soluble/presse-agrumes`) avec tags de version.
- **Endpoint `/healthz`** non authentifié, sans données sensibles, pour les
  healthchecks Docker/Kubernetes.
- Documentation Docker complète : [`docs/DOCKER.md`](docs/DOCKER.md).

### Notes

- La configuration reste exclusivement `config.toml` ; aucun `Environment=`.
- Le `.deb` et un dépôt APT restent prévus dans une prochaine version.

## [0.4.1] - 2026-10-30

- Suppression du dernier recours à une variable de shell (`PYTHON`) dans
  `run.sh` : le lancement utilise `python3`, conformément à la configuration
  uniquement par fichier.

## [0.4.0] - 2026-10-30

### Modifié - rupture de configuration

- **Suppression totale des variables d'environnement** pour la configuration.
  Seul `config.toml` est lu (ou le fichier passé à `--config`).
- **`config.toml` est désormais versionné** avec le projet ; il contient un
  modèle commenté. En production, l'utilisateur doit changer le mot de passe
  par défaut `changez-moi` et restreindre `allowed_roots`.
- Les options `--host` et `--port` sont supprimées : hôte et port viennent du
  fichier de configuration. `--config`, `--strict-port` et `--reload` restent.
- L'unité systemd ne contient plus aucune ligne `Environment=`.
- `config.example.toml` et `deploy/presse-agrumes.env.example` sont supprimés.
- Un avertissement console est affiché si le mot de passe par défaut est encore
  utilisé, ou si `config.toml` est lisible par d'autres utilisateurs.
- Tests : configuration temporaire appliquée via `config.apply_config_file`,
  Playwright sur un backend dédié (port 8099, auth désactivée).

## [0.3.0] - 2026-10-30

### Ajouté

- **Fichier de configuration `config.toml`** : mot de passe, utilisateur, port,
  racines autorisées, dossier de données et chemins ffmpeg. (Les variables
  d'environnement ont été supprimées en v0.4.0.)
- **Suppression directe** d'un fichier, pack ou fichier en erreur depuis les
  résultats, avec confirmation et mise à jour du scan. Route
  `POST /api/scans/{id}/delete`.
- **Limite d'affichage et de sélection** : 10, 20, 30, 50, 100 ou tout ;
  « Sélectionner affichés » sélectionne uniquement la page visible.
- **ETA fiabilisée** : calibration automatique du preset au lancement si aucune
  mesure n'existe, bouton « Calibrer (~5 s) », recalcul de l'ETA globale à partir
  de la vitesse réelle ffmpeg.
- Le bouton **Suivi** de la bannière ouvre et scrolle maintenant vers le panneau
  détaillé de la compression.

### Modifié

- Le mot de passe n'est plus affiché en clair quand il vient de `config.toml` ;
  la console indique le fichier utilisé (et un avertissement si ses permissions
  sont trop larges).
- Version 0.3.0.

## [0.2.0] - 2026-10-30

### Ajouté

- **Authentification par défaut** : mot de passe temporaire généré à chaque
  démarrage, affiché en console avec l'utilisateur `agrumes`.
- **Scan automatique des ports** : si le port préféré est occupé, l'application
  bascule sur le suivant et affiche l'URL réelle (IPv4, dont Tailscale).
- **Pause / reprise** d'une compression : `SIGSTOP`/`SIGCONT` sur ffmpeg, sans
  perte de progression.
- **Planification horaire** : fenêtres par jour et par heure, traversée de
  minuit, pause automatique hors plage et reprise programmée.
- **Bannière des tâches actives** en haut de toutes les pages, avec progression,
  ETA, vitesse, pause/reprise et accès au suivi.
- **Réouverture automatique** du suivi après fermeture du navigateur, via
  `GET /api/jobs/active`.
- **Sélection par ligne entière** dans les résultats, la case à cocher restant
  utilisable.
- **Erreurs enrichies** : fichier vide, corrompu, permissions, timeout, absence
  de flux vidéo, avec libellé et conseil ; ces fichiers sont ignorés sans
  interrompre le scan.
- **Versionning** : SemVer synchronisé (backend, frontend, pyproject,
  CHANGELOG), tags git `v0.1.0` et `v0.2.0`, script `scripts/release.sh`,
  documentation `docs/RELEASES.md`.

### Modifié

- `/api/health` et `/api/config` exposent le fuseau horaire du serveur.
- Les jobs peuvent avoir le statut `paused` ; `/api/jobs/active` liste les
  tâches en cours.
- Nouvelles routes `POST /api/jobs/{id}/pause` et `/resume`.

## [0.1.0] - 2026-10-30

Première version fonctionnelle.

### Ajouté

- Analyse récursive des vidéos avec ffprobe, progression SSE, ETA et annulation.
- Estimation du gain AV1 (codec, bitrate, résolution, bpp), détection HDR/10 bits.
- Regroupement explicite des séries par saison/pack, avec détail des épisodes.
- Interface React/Vite/TypeScript/Tailwind/shadcn/ui, React Router, TanStack Query.
- Sélection par fichier ou pack, tri, recherche et filtres.
- Réglages AV1 : SVT-AV1, libaom, VAAPI, preset, CRF, 8/10 bits, audio,
  conteneur, sous-titres.
- Préflight complet : permissions, conflits, espace disque, estimation.
- Compression avec sortie atomique, vérification ffprobe, annulation.
- Gestion des originaux : conserver, supprimer, déplacer en corbeille.
- Destinations : même dossier (suffixe ou remplacement), dossier miroir.
- Détection matérielle, benchmark ffmpeg, cache par machine, ETA selon les
  ressources allouées.
- Test qualité avec extrait configurable, comparaison côte à côte, téléchargements.
- Historique des analyses (index JSON).
- Documentation complète, tests pytest et test de fumée Playwright.
- Scripts de démarrage, service systemd, exemple d'environnement.

### Sécurité

- Aucune commande shell, chemins confinés, auth Basic optionnelle.
- Original supprimé uniquement après validation de la sortie.
- Fichiers déjà AV1 jamais recompressés.
