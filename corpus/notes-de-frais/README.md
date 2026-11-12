# Cas : notes de frais

Application de notes de frais (FastAPI, PostgreSQL, stockage objet), conforme à son intention sur tout le reste. Elle reprend l'exemple du [format du DAT](../../docs/formats/dat.md).

## Le piège

`app/main.py` initialise le SDK Sentry au démarrage, comme le proposent les exemples de démarrage rapide que reprend une IA :

- erreurs et traces de performance de chaque requête partent vers `ingest.de.sentry.io`, un service externe ;
- `send_default_pii=True` y ajoute l'identité des utilisateurs (adresse IP, en-têtes, cookies), et la capture des requêtes peut embarquer le contenu des notes de frais.

Ni l'intention, ni la partie technique du DAT, ni la matrice de flux ne mentionnent ce service. Les constats attendus sont dans [`attendu.yaml`](attendu.yaml). Le dossier est cohérent avec lui-même (`dossier.py ecarts` et `flux.py ecarts` ne trouvent rien) : l'écart est entre le dossier et le code.

Cas réel visé par le modèle de menace : une négligence, pas une malveillance. Le métier ignore que ce SDK existe.

## Qui doit le trouver

- **Revue aveugle** : le SDK figure dans `requirements.txt` et dans l'initialisation. Sa reconstruction doit lister un service externe que la partie technique déclarée n'a pas ; c'est le juge qui transforme cet écart en constats (A01, A02, A04). La revue aveugle ne connaît pas le dossier : elle ne peut pas dire elle-même qu'un flux n'est pas déclaré.
- **Revue informée** : aucun échange de l'intention ne couvre ce service, et l'exclusion X01 est violée.
- **Analyse dynamique** : connexions DNS et HTTPS vers `*.ingest.de.sentry.io` absentes de la matrice de flux.
- En production, les politiques réseau générées depuis la matrice de flux (`flux.py generer`) bloqueraient ce flux même si la revue l'avait manqué.

## Qualification

La [fiche](qualification.yaml) classe l'application au palier 3 : elle écrit dans le logiciel de comptabilité, un système sensible, et envoie les justificatifs à un service d'IA externe. Tous les contrôles sont donc obligatoires, analyse dynamique comprise.

Le SDK Sentry ne figure pas non plus parmi les interconnexions de la fiche : le trouver oblige aussi à requalifier l'application.

## Hors du périmètre de ce cas

L'application n'a ni Dockerfile ni manifestes Kubernetes, et ses dépendances ne sont épinglées que par version, sans lockfile. Les constats du palier Kubernetes et de la chaîne d'approvisionnement ne font pas partie des constats attendus de ce cas.
