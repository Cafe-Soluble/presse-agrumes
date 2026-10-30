# Décisions d'architecture (ADR synthétiques)

## ADR-001 — FastAPI + jobs en threads

**Contexte** : opérations ffprobe/ffmpeg bloquantes, besoin de progression temps
réel, déploiement simple sur NAS.

**Décision** : FastAPI/Uvicorn, jobs dans des threads daemon, snapshots
thread-safe, SSE + polling de secours.

**Conséquences** : pas de file de tâches distribuée ; un seul processus
applicatif. L'interface reste réactive, mais un redémarrage interrompt les jobs
(marqués `interrupted`).

## ADR-002 — JSON atomique plutôt qu'une base de données

**Contexte** : volumes de métadonnées faibles, environnement NAS, besoin
d'inspection manuelle et de sauvegarde simple.

**Décision** : un fichier JSON par scan/job/test, écriture via fichier
temporaire + `os.replace`, index `data/scans/index.json`.

**Conséquences** : pas de requêtes complexes ; l'index doit rester cohérent.
Les vidéos ne sont jamais stockées dans `data/`.

## ADR-003 — Séries regroupées par dossier parent explicite

**Contexte** : impossible de deviner de façon fiable si un dossier est une
série, une saison, un film ou des extras.

**Décision** : l'utilisateur marque une ou plusieurs racines de séries. Sous
ces racines, le dossier parent immédiat d'une vidéo devient un pack. Les
épisodes restent consultables en détail, mais ne sont pas comparés un par un
dans la liste principale.

**Conséquences** : prévisible et sans faux positifs. Un rangement exotique
(épisodes imbriqués dans des sous-dossiers par épisode) produit un pack par
épisode.

## ADR-004 — Estimation pessimiste + benchmark réel

**Contexte** : le gain et le temps dépendent énormément du contenu, du codec
source et du matériel.

**Décision** : facteur de gain prudent par codec/bpp, plafonné à 90 % ; ETA
basée sur un benchmark ffmpeg 1080p mis en cache, avec table indicative en
repli ; pourcentage de threads + concurrence + marge 12 %.

**Conséquences** : les chiffres servent au tri, pas de garantie. Le test
qualité reste la source de vérité.

## ADR-005 — Sécurité locale et confirmation des destructions

**Contexte** : l'outil supprime et déplace des vidéos.

**Décision** : pas de shell, chemins confinés par `PA_ALLOWED_ROOTS`, HTTP
Basic optionnel, sortie temporaire validée avant remplacement, original traité
seulement après succès, confirmation UI pour la suppression, jamais de
recompression AV1.

**Conséquences** : l'outil reste simple mais doit être réservé au LAN. La
suppression reste irréversible après validation.

## ADR-006 — SPA React servie par FastAPI, build versionné

**Contexte** : contrainte utilisateur (Vite + React + TypeScript + Tailwind +
shadcn/ui + Router + TanStack Query) et cible NAS pouvant ne pas avoir Node.

**Décision** : frontend dans `frontend/`, build Vite dans `frontend/dist`,
versionné ; FastAPI sert les assets et l'index avec fallback SPA ; Vite proxy
`/api` en développement.

**Conséquences** : clone-and-run sans Node. Il faut rebuild et committer
`dist` après chaque modification frontend ; ne jamais mettre un middleware qui
bufferise le SSE.

## ADR-007 — Test qualité en MP4/AAC

**Contexte** : les conteneurs finaux (MKV/WebM) et certains codecs audio ne
sont pas lisibles dans tous les navigateurs.

**Décision** : produire systématiquement un aperçu original H.264 MP4, un
extrait brut MKV téléchargeable et un extrait AV1 MP4/AAC pour la comparaison
côte à côte. Comparer les débits, pas les tailles brutes.

**Conséquences** : l'aperçu original est un proxy (CRF 18), pas le fichier
strictement bit-à-bit ; c'est indiqué dans l'interface et la documentation.
