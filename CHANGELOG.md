# Changelog

## [0.4.1] — 2026-10-30

- Suppression du dernier recours à une variable de shell (`PYTHON`) dans
  `run.sh` : le lancement utilise `python3`, conformément à la configuration
  uniquement par fichier.

## [0.4.0] — 2026-10-30

### Modifié — rupture de configuration

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

## [0.3.0] — 2026-10-30

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

## [0.2.0] — 2026-10-30

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

## [0.1.0] — 2026-10-30

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
