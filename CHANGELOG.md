# Changelog

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
