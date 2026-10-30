# Changelog

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
