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

**Décision** : pas de shell, chemins confinés par `[paths] allowed_roots`, HTTP
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

## ADR-008 — Authentification par mot de passe généré

**Contexte** : l'outil donne accès à des opérations destructrices et sera souvent
lancé sur un NAS sans reverse proxy.

**Décision** : HTTP Basic actif par défaut, utilisateur `agrumes`, mot de passe
dans `config.toml`. `[auth] disabled = true` est réservé au développement.

**Conséquences** : protection immédiate sans configuration, mais mot de passe à
récupérer dans les logs systemd. Pour un accès hors LAN, un reverse proxy TLS
reste nécessaire.

## ADR-009 — Scan de ports au démarrage

**Contexte** : 8080 est fréquemment occupé sur un NAS (autres applications).

**Décision** : scanner les ports suivants (8080 → 8081 → …) avec un bind TCP et
afficher l'URL réelle. `--strict-port` permet d'échouer volontairement si le port
demandé est occupé.

**Conséquences** : démarrage sans conflit et URL imprimée en console. Le
frontend utilise uniquement des chemins relatifs, donc fonctionne sur n'importe
quel port.

## ADR-010 — Pause par SIGSTOP plutôt qu'annulation

**Contexte** : certains encodages durent plusieurs heures ; annuler perdrait le
travail et les fichiers temporaires.

**Décision** : la pause suspend les processus ffmpeg (`SIGSTOP`) et la reprise
les relance (`SIGCONT`). Les workers attendent avant de démarrer un nouveau
fichier. L'annulation reste distincte.

**Conséquences** : reprise exacte au même point, mais les processus suspendus
occupent toujours leur mémoire. Sur un NAS, la planification horaire utilise ce
même mécanisme.

## ADR-011 — Planification par plages autorisées

**Contexte** : l'utilisateur veut limiter les compressions à certaines heures ou
jours, avec reprise automatique.

**Décision** : fenêtres `days/start/end` évaluées toutes les 15 s ; hors plage,
pause `schedule`, `next_resume_at` affiché. Les heures sont celles du serveur.

**Conséquences** : simple et prévisible, précision de 15 s. Les changements de
fuseau/horloge pendant un job sont pris en compte à la prochaine évaluation.

## ADR-012 — Bannière des jobs actifs et reprise après navigation

**Contexte** : fermer le navigateur ne doit pas faire perdre la vision du travail
en cours.

**Décision** : endpoint `/api/jobs/active` (mémoire), polling 2,5 s par le
frontend, bannière globale sous le header et réouverture automatique du panneau
de suivi via `context.scan_id` au retour sur le workspace.

**Conséquences** : les jobs restent visibles tant que le serveur tourne. Après un
redémarrage du service, les jobs sont marqués `interrupted` et ne sont plus
actifs (l'historique les conserve).

## ADR-013 — SemVer + tags git annotés

**Contexte** : besoin de savoir quelle version tourne sur le NAS et de revenir à
une release stable.

**Décision** : SemVer, versions synchronisées dans les fichiers Python/Node/
pyproject/CHANGELOG, tags `vX.Y.Z`, script `scripts/release.sh` qui vérifie la
cohérence, les tests et le build avant de taguer.

**Conséquences** : releases traçables et vérifiables via `/api/health`. Le build
frontend reste versionné pour un déploiement sans Node.

## ADR-014 — Mot de passe dans config.toml

**Contexte** : l'utilisateur ne veut pas mettre le mot de passe dans
l'environnement ; les variables sont peu lisibles sur un NAS.

**Décision** : fichier TOML `config.toml` (ignoré par git) avec `[auth] user` et
`[auth] password`, chargé à l'import. Aucune variable d'environnement n'est
lue (changement v0.4.0).

**Conséquences** : configuration lisible et versionnable via
`config.toml` versionné, permissions `chmod 600` recommandées, redémarrage requis
après modification.

## ADR-015 — Suppression directe depuis les résultats

**Contexte** : l'utilisateur veut supprimer immédiatement des fichiers inutiles
ou corrompus, sans passer par une compression.

**Décision** : route dédiée `POST /api/scans/{id}/delete` avec `item_ids` ou
`paths` limités aux fichiers déjà présents dans le scan ; refus des symlinks et
des chemins hors racine ; confirmation UI ; reconstruction du scan après
suppression.

**Conséquences** : action rapide mais irréversible (pas de corbeille). La
gestion « supprimer après compression » reste séparée et vérifiée par ffprobe.

## ADR-016 — Sélection et affichage limités

**Contexte** : les bibliothèques peuvent contenir des milliers de fichiers et
l'utilisateur veut traiter seulement 10, 20, 30 ou 50 médias.

**Décision** : sélecteur d'affichage 10/20/30/50/100/tout + bouton
« Sélectionner affichés » ; « Tout sélectionner » conserve le comportement
global.

**Conséquences** : maîtrise du DOM et des lots de compression, sans limiter la
recherche ni les filtres.

## ADR-017 — ETA calibrée et recalculée

**Contexte** : l'ETA initiale (table générique) peut être très différente de la
vitesse réelle, surtout si le benchmark a été fait pour un autre preset.

**Décision** : calibration automatique courte (1 s) au lancement si le preset
n'a pas de cache ; bouton « Calibrer (~5 s) » dans les résultats ; ETA globale
recalculée en continu à partir de `speed` ffmpeg. L'ETA des résultats est
explicitement présentée comme initiale.

**Conséquences** : démarrage légèrement plus long lors de la première
compression d'un preset, mais ETA du panneau de suivi beaucoup plus fiable.
