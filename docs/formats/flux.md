# Format de la matrice de flux

Statut : **validé en partie** le 2026-11-13 (format v0). Deux points restent à trancher, listés à la fin dans [Décisions](#décisions) : les renvois, reformulés, et le nom des pods, revu pour l'administration.

La matrice de flux déclare toutes les connexions réseau de l'application : celles qu'elle reçoit, celles qu'elle ouvre, et celles qu'échangent ses composants. Elle sert deux fois :

- **pendant la revue**, elle décrit les flux que le juge compare à la reconstruction aveugle, et que l'analyse dynamique compare aux connexions observées ;
- **au déploiement**, l'équipe infra en génère les politiques réseau. Elles refusent tout par défaut : un flux absent de la matrice est bloqué en production, même si la revue l'a manqué.

Les schémas font foi : [`flux.schema.json`](../../plugin/schemas/flux.schema.json) pour la matrice, [`plateforme.schema.json`](../../plugin/schemas/plateforme.schema.json) pour le fichier de plateforme. Le skill [`matrice-flux`](../../plugin/skills/matrice-flux/SKILL.md) aide l'auteur à remplir la matrice. Le script [`flux.py`](../../plugin/scripts/flux.py) la valide, la confronte au dossier et génère les politiques.

## Vocabulaire

### La plateforme

La **plateforme** est l'ensemble des services communs que l'équipe infra fournit à toutes les applications qu'elle héberge. Aucune application ne les possède ni ne les gère elle-même :

- les **points d'entrée** par lesquels arrivent les utilisateurs : l'entrée interne pour ceux du réseau de l'entreprise, l'entrée externe pour ceux qui viennent d'un réseau que l'entreprise ne maîtrise pas (Internet, réseau d'un partenaire, extranet) ;
- le **SSO** de l'entreprise, le **gestionnaire de secrets**, la **journalisation** et la **supervision** ;
- le **DNS** du cluster.

Ce sont, avec les points d'entrée et le DNS, les « services d'infrastructure communs » que la [fiche de qualification](qualification.md#interconnexions) exclut de ses interconnexions. La matrice les nomme (`plateforme: sso`) sans dire où ils se trouvent : c'est le [fichier de plateforme](#le-fichier-de-plateforme), tenu par l'équipe infra, qui donne leur emplacement et la façon dont le cluster filtre le réseau.

### Interconnexion, échange, flux

Trois notions voisines, tenues dans trois documents différents, répondent à trois questions :

| | Interconnexion | Échange | Flux |
|---|---|---|---|
| Document | fiche de qualification | intention | matrice de flux |
| Question | avec quel système l'application communique-t-elle, et avec quels droits ? | quelles données passent, dans quel sens, et pourquoi ? | quelle connexion réseau, ouverte par qui, vers quelle adresse et quel port ? |
| Écrit par | le métier, précisé et validé par l'équipe infra | le métier, sans le code | l'auteur, d'après le code |
| Sert à | calculer le palier, borner les comptes de service | servir de référence à la revue | générer les politiques réseau |

Pour le service d'IA de l'application `notes-de-frais` :

- l'interconnexion `I02` dit que l'application écrit dans un service d'IA externe, qui n'est pas un système sensible ;
- l'échange `E02` dit qu'elle lui envoie les justificatifs et en reçoit le montant et la date : les données vont dans les deux sens ;
- le flux `R06` dit que le composant `C01` ouvre une connexion HTTPS vers `api.fournisseur-ia.example`, port 443 : c'est toujours l'application qui ouvre la connexion, même si les données vont dans les deux sens.

Un échange se réalise par un ou plusieurs flux : un appel d'API, plus un rappel du partenaire, font deux flux pour un échange. Certains flux, à l'inverse, ne réalisent aucun échange : ceux vers la base de données de l'application, vers le SSO, ou entre ses composants. Un flux vers un autre système qui ne réalise aucun échange est un **flux non déclaré**.

## Ce que le format doit permettre

- **Devenir un contrôle.** Les politiques réseau sont générées depuis la matrice, et depuis elle seule. Déclarer un flux revient à en demander l'ouverture ; l'omettre revient à le bloquer.
- **Porter le sens des connexions.** Une politique réseau filtre selon qui ouvre la connexion. Chaque flux dit donc qui l'ouvre (`de`) et qui la reçoit (`vers`). Le sens des données reste dans l'intention : l'application envoie un justificatif au service d'IA, qui renvoie un montant. Cela fait un seul flux sortant pour un échange `les_deux`.
- **Justifier chaque flux.** Un flux vers un système que l'application ne possède pas renvoie à l'échange de l'intention qu'il réalise, et à l'interconnexion de la fiche de qualification par laquelle il passe. Le juge vérifie des références au lieu de comparer de la prose, et l'équipe infra voit pourquoi elle ouvre chaque flux.
- **Être produite en aveugle.** Le relecteur aveugle remplit une matrice dans le même format. Il ne connaît ni les échanges ni les interconnexions, donc ces renvois sont facultatifs dans le schéma.
- **Se comparer aux flux observés.** Les destinations sont désignées comme l'analyse dynamique les voit : nom DNS ou bloc d'adresses, et port.
- **Rester indépendante du CNI.** La matrice nomme les destinations. C'est le fichier de plateforme qui dit comment le cluster les filtre.

## Fichier

```
.raton/
  intention.yaml
  technique.yaml
  flux.yaml        # matrice de flux : décrit le même commit que technique.yaml
```

Comme la partie technique, la matrice décrit le code à un commit précis, et l'auteur la remplit avec une IA. Elle ne prouve donc rien à elle seule. Sa valeur vient de deux choses : les comparaisons (avec l'intention, la fiche de qualification, la reconstruction aveugle et l'analyse dynamique), et les politiques générées, qui bloquent ce qu'elle omet.

Ce qui n'y figure pas :

- la résolution de noms, toujours permise vers le DNS du cluster ;
- les sondes de Kubernetes (liveness, readiness), que les politiques réseau laissent passer ;
- les adresses des services de la plateforme : c'est le fichier de plateforme qui les donne.

## Contenu

| Champ | Contenu |
|---|---|
| `application` | code de l'application dans la fiche de qualification ; il nomme aussi son namespace |
| `commit` | SHA complet du commit décrit |
| `flux` | la liste des flux |

Chaque flux :

| Champ | Contenu |
|---|---|
| `id` | `R01`, `R02`… |
| `de`, `vers` | les deux extrémités : `de` ouvre la connexion, `vers` la reçoit |
| `port` | port de destination |
| `protocole` | protocole applicatif, dans une liste fermée : `https`, `http`, `grpc`, `postgresql`, `mysql`, `redis`, `mongodb`, `amqp`, `kafka`, `smtp`, `ldaps`, `ldap`, `sftp`, `ssh`, `tcp`, `udp`. Seul `udp` passe par UDP ; tous les autres passent par TCP |
| `motif` | pourquoi ce flux existe, en 200 caractères au plus |
| `echanges` | échanges de l'intention que le flux réalise |
| `interconnexions` | interconnexions de la fiche de qualification par lesquelles il passe |

Une extrémité a une seule nature :

| Nature | Ce que c'est | Adresse |
|---|---|---|
| `composant: C01` | un composant de la partie technique | aucune : c'est un pod du namespace de l'application |
| `stockage: S01` | un stockage de la partie technique | aucune s'il est déployé dans le namespace ; sinon son adresse (base gérée, stockage objet de l'entreprise) |
| `service: T01` | un service tiers de la partie technique | obligatoire |
| `systeme: <libellé>` | un autre système, qui n'est pas un service tiers ; typiquement, un partenaire qui appelle l'application | obligatoire |
| `plateforme: <service>` | un service de la [plateforme](#la-plateforme) : `entree_interne` et `entree_externe` (points d'entrée des utilisateurs, depuis le réseau de l'entreprise ou depuis un réseau qu'elle ne maîtrise pas), `sso`, `secrets`, `journalisation`, `supervision` | aucune : le fichier de plateforme la donne |

L'adresse s'écrit de l'une de ces façons :

- `hote` : un nom DNS. Un joker `*.` en tête couvre exactement un niveau : `*.ingest.de.sentry.io` couvre `o4508261749303296.ingest.de.sentry.io`, mais ni `ingest.de.sentry.io`, ni `a.b.ingest.de.sentry.io`. C'est la règle de Cilium, que la génération reprend telle quelle.
- `cidr` : un bloc d'adresses, comme `10.20.30.0/28`, ou `/32` pour une seule adresse.
- `variable` : la variable de configuration par laquelle le code reçoit l'adresse.
  - À côté de `hote` ou de `cidr`, elle documente le lien avec le code.
  - Seule, elle signale que l'adresse n'est pas encore connue. C'est souvent le cas pour le relecteur aveugle, ou pour un système interne dont seule l'équipe infra connaît l'adresse. La matrice est alors incomplète, et la génération refuse de produire des politiques tant que l'adresse n'est pas fixée.

On écrit le nom d'hôte, jamais l'URL entière : une URL peut contenir une clé, comme le DSN de Sentry.

**Renvois.** Seuls les flux vers un système que l'application ne possède pas, un `service` tiers ou un autre `systeme`, renvoient à un échange de l'intention et à une interconnexion de la fiche. Les autres flux n'ont rien à citer, puisque ni l'intention ni la fiche ne les décrivent :

- les flux vers les stockages de l'application, sa base de données ou son stockage objet : elle les possède ;
- les flux entre ses composants ;
- les flux vers la plateforme ou depuis elle : entrées des utilisateurs, SSO, secrets, journalisation, supervision.

Dans l'exemple ci-dessous, `R03`, vers la base PostgreSQL de l'application, ne cite rien ; `R05`, vers l'annuaire, cite l'échange `E01` et l'interconnexion `I01`. Ce sont les exclusions des [interconnexions de la fiche](qualification.md#interconnexions).

**Règles.** En plus du schéma, `flux.py valider` vérifie que :

- une extrémité au moins est un composant de l'application ;
- les entrées de la plateforme sont toujours à l'origine, et le SSO, le gestionnaire de secrets et les stockages toujours à la destination ;
- les blocs d'adresses sont valides ;
- les renvois désignent des éléments qui existent : composants, stockages et services de la partie technique, échanges de l'intention, interconnexions de la fiche ;
- la matrice décrit le même commit que la partie technique ;
- le code de l'application est celui de la fiche.

Il avertit aussi dans trois cas :

- une adresse reste à fixer ;
- un joker est employé ;
- une origine est désignée par un nom, qu'une politique réseau ne sait pas filtrer : il faut le bloc d'adresses.

## Exemple

La matrice de l'application [`notes-de-frais`](../../corpus/notes-de-frais/) du corpus, telle que l'auteur la soumet :

```yaml
format: raton/flux/v0
application: notes-de-frais
commit: 4e3d3e49bc553b5ff0d6f7203f4791cf783997fb

flux:
  - id: R01
    de: { plateforme: entree_interne }
    vers: { composant: C01 }
    port: 8000
    protocole: http
    motif: accès des salariés, des managers et des comptables

  - id: R02
    de: { composant: C01 }
    vers: { plateforme: sso }
    port: 443
    protocole: https
    motif: configuration OIDC et clés de vérification des jetons

  - id: R03
    de: { composant: C01 }
    vers: { stockage: S01, hote: notes-de-frais.postgres.example.com, variable: DATABASE_URL }
    port: 5432
    protocole: postgresql
    motif: notes de frais

  - id: R04
    de: { composant: C01 }
    vers: { stockage: S02, hote: s3.example.com, variable: S3_ENDPOINT }
    port: 443
    protocole: https
    motif: justificatifs

  - id: R05
    de: { composant: C01 }
    vers: { service: T01, hote: annuaire.example.com, variable: DIRECTORY_URL }
    port: 443
    protocole: https
    motif: salariés rattachés à un manager
    echanges: [E01]
    interconnexions: [I01]

  - id: R06
    de: { composant: C01 }
    vers: { service: T02, hote: api.fournisseur-ia.example, variable: AI_ENDPOINT }
    port: 443
    protocole: https
    motif: lecture du montant et de la date des justificatifs
    echanges: [E02]
    interconnexions: [I02]

  - id: R07
    de: { composant: C01 }
    vers: { service: T03, hote: compta.example.com, variable: COMPTA_URL }
    port: 443
    protocole: https
    motif: export des notes validées
    echanges: [E03]
    interconnexions: [I03]
```

À lire :

- R01 : les utilisateurs arrivent par l'entrée interne, sur le port de l'application. Ce flux n'a aucun renvoi.
- R02 : le SSO est un service de la plateforme.
- R03 et R04 : les deux stockages sont hors du namespace. L'un est une base gérée, l'autre le stockage objet de l'entreprise.
- R05 à R07 : un flux par échange, chacun avec son interconnexion. Le flux R06 vers le service d'IA réalise à lui seul l'échange E02, qui va dans les deux sens.

Comme la partie technique soumise, cette matrice omet le SDK Sentry. Une matrice exacte, comme la reconstruction aveugle, contiendrait ce flux :

```yaml
- id: R08
  de: { composant: C01 }
  vers: { service: T04, hote: "*.ingest.de.sentry.io" }
  port: 443
  protocole: https
```

Il ne renvoie à aucun échange ni à aucune interconnexion, et `flux.py ecarts` le signale deux fois. Tel qu'il est omis ici, il serait bloqué en production par les politiques générées.

## Confrontation avec le dossier

`flux.py ecarts` confronte la matrice à la partie technique et à l'intention (le répertoire `.raton`), et à la fiche de qualification :

| Écart | Ce qu'il signale | Demande |
|---|---|---|
| `flux_sans_echange` | un flux vers un service ou un système qu'aucun échange de l'intention ne couvre : un flux non déclaré | l'intention |
| `echange_sans_flux` | un échange qu'aucun flux ne réalise : les politiques le bloqueraient | l'intention |
| `flux_sans_interconnexion` | un flux vers un service ou un système qui ne passe par aucune interconnexion de la fiche | la fiche |
| `interconnexion_sans_flux` | une interconnexion par laquelle aucun flux ne passe : si elle ne sert pas, elle ne doit pas recevoir de droits | la fiche |
| `interconnexion_hors_echange` | un flux qui passe par une interconnexion que ses échanges ne citent pas | l'intention et la fiche |
| `exposition_sous_evaluee` | un flux depuis l'entrée externe, alors que la fiche déclare une exposition interne | la fiche |
| `service_sans_flux`, `stockage_sans_flux` | un service ou un stockage de la partie technique qu'aucun flux n'atteint : il serait bloqué | la technique |
| `exposition_incoherente` | l'exposition d'un composant dans la partie technique ne correspond pas aux flux qui lui arrivent des entrées | la technique |
| `flux_en_clair` | du `http` ou du `ldap` hors du namespace | — |
| `bloc_large` | un bloc de plus de 65 536 adresses en IPv4 (préfixe plus court que /16), ou de préfixe plus court que /48 en IPv6 | — |

Comme pour `dossier.py ecarts`, ce sont des points à examiner, pas des erreurs de format. L'auteur les règle avant de soumettre : il corrige le code ou la matrice, ou fait évoluer l'intention, ce qui demande une nouvelle validation. Un flux sans interconnexion ou une exposition sous-évaluée demandent en plus de faire requalifier l'application par l'équipe infra.

Sur le corpus, la matrice soumise ne donne aucun écart : elle est cohérente avec le dossier, et l'écart se trouve entre le dossier et le code. Avec la partie technique exacte du [format du DAT](dat.md#partie-technique), qui liste le SDK Sentry, l'écart `service_sans_flux` apparaît pour `T04`.

## Génération des politiques réseau

`flux.py generer` traduit la matrice en politiques Kubernetes, d'après le fichier de plateforme. L'équipe infra lance la génération au déploiement, depuis la matrice du commit approuvé, et applique le résultat. Les politiques ne vivent pas dans le dépôt de l'application : l'auteur ne peut pas les retoucher.

Hypothèses de déploiement :

- un namespace par application, nommé d'après son code ;
- chaque pod porte le nom de son composant ou de son stockage, tel que le donne la partie technique (`api`, `worker`, `postgres`), dans une étiquette que fixe la plateforme. Un nom lisible évite à l'équipe infra de tenir une grille de correspondance : elle lit `api` dans le cluster, là où `C01` l'obligerait à ouvrir le dossier. Le palier Kubernetes (skill 5) vérifiera que les manifestes posent cette étiquette ;
- tout est refusé par défaut, en entrée comme en sortie.

### Le fichier de plateforme

L'équipe infra le tient à la racine de son dépôt. Il est commun à toutes les applications. Exemple, celui du corpus ([`corpus/plateforme.yaml`](../../corpus/plateforme.yaml)) :

```yaml
format: raton/plateforme/v0
cni: cilium                                        # cilium | standard
etiquette_composant: app.kubernetes.io/component  # porte le nom du composant (api, worker…)

dns:
  namespace: kube-system
  pods: { k8s-app: kube-dns }

services:
  entree_interne:
    namespace: entree-interne
    pods: { app.kubernetes.io/name: entree-interne }
  entree_externe:
    namespace: entree-externe
    pods: { app.kubernetes.io/name: entree-externe }
  sso: { hotes: [sso.example.com] }
  secrets: { hotes: [coffre.example.com] }
  journalisation: { cidrs: [10.10.20.0/24] }
  supervision:
    namespace: supervision
    pods: { app.kubernetes.io/name: prometheus }
```

Chaque service est décrit de l'une de ces façons :

- dans le cluster, par son namespace et les étiquettes de ses pods ;
- hors du cluster, par des noms DNS ou par des blocs d'adresses.

Avec un CNI `standard`, la plateforme peut ajouter un `proxy_sortant` (namespace, étiquettes, port). Un flux vers un service que la plateforme ne décrit pas empêche la génération.

### Ce qui est généré

1. `raton-refus-par-defaut` refuse toute entrée et toute sortie aux pods du namespace.
2. `raton-dns` permet la résolution de noms auprès du DNS du cluster.
3. `raton-<nom>` est une NetworkPolicy par composant ou stockage du namespace, nommée d'après lui (`raton-api`). Elle porte une règle par flux désigné par un sélecteur ou par un bloc d'adresses : les entrées depuis la plateforme, les flux entre composants, les blocs d'adresses.
4. Les flux vers un nom DNS dépendent du CNI :
   - avec Cilium, `raton-noms-<nom>` est une CiliumNetworkPolicy, avec une règle `toFQDNs` par flux ;
   - avec un CNI standard, la NetworkPolicy du composant l'autorise à joindre le proxy sortant, et `flux.py egress` donne la liste des destinations à autoriser dans le proxy. Seuls `http`, `https` et `grpc` passent par le proxy ; un autre protocole doit désigner sa destination par un bloc d'adresses. Sans proxy, ces flux restent bloqués, et le script le signale.

Chaque politique porte en annotation le commit, le composant avec son libellé (`raton/composant`) et les flux dont elle découle (`raton/flux`), pour remonter d'une règle à la ligne de la matrice. Le rendu (`flux.py rendre --dossier`) donne la grille complète des composants, de leurs noms et de leurs libellés. Les noms `dns` et `refus-par-defaut` sont réservés aux politiques communes.

Pour le corpus, avec Cilium, l'entrée des utilisateurs donne cette politique :

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: raton-api
  namespace: notes-de-frais
  labels:
    app.kubernetes.io/part-of: notes-de-frais
    app.kubernetes.io/managed-by: raton
  annotations:
    raton/commit: 4e3d3e49bc553b5ff0d6f7203f4791cf783997fb
    raton/composant: C01 — API notes de frais
    raton/flux: R01
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/component: api
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: entree-interne
      podSelector:
        matchLabels:
          app.kubernetes.io/name: entree-interne
    ports:
    - protocol: TCP
      port: 8000
```

Les six flux sortants, tous désignés par un nom, donnent une CiliumNetworkPolicy `raton-noms-api` à six règles, comme celle de l'annuaire :

```yaml
- toFQDNs:
  - matchName: annuaire.example.com
  toPorts:
  - ports:
    - port: '443'
      protocol: TCP
```

Le SDK Sentry n'y figure pas : sa connexion vers `*.ingest.de.sentry.io` est refusée.

### Le choix du CNI

Une NetworkPolicy standard ne connaît que des sélecteurs de pods et des blocs d'adresses. Or les destinations qui comptent le plus pour le modèle de menace sont des services en ligne, désignés par un nom (`*.ingest.de.sentry.io`) et dont les adresses changent. Il y a deux façons de les filtrer :

| | Cilium | NetworkPolicy standard et proxy sortant |
|---|---|---|
| Filtrage par nom | dans le cluster : Cilium apprend les adresses en observant les réponses DNS | par le proxy, qui voit le nom demandé |
| Protocoles | tous | `http`, `https` et `grpc` ; une base de données hors du cluster doit être désignée par un bloc d'adresses |
| Ce qu'il faut | Cilium comme CNI | un proxy sortant, que l'application doit utiliser (`HTTPS_PROXY`) |
| Ce que génère Raton | NetworkPolicies et CiliumNetworkPolicies | NetworkPolicies, et la liste à charger dans le proxy (`flux.py egress`) |

Cilium filtre tous les protocoles sans que l'application ait à coopérer. **Décidé le 2026-11-13 : Cilium par défaut.** Le mode standard avec un proxy sortant reste disponible pour un cluster qui ne pourrait pas l'adopter : le format ne dépend pas de ce choix, et le générateur sait produire les deux.

## Comparaisons à venir

Le format est prévu pour trois comparaisons, qui viendront avec leurs skills :

- **Juge (skill 9).** Il apparie les flux de l'auteur et ceux de l'aveugle :
  - un flux hors du namespace par son adresse et son port, un joker couvrant le nom observé ;
  - un flux de la plateforme par son service ;
  - un flux interne par l'appariement des composants.

  Un flux présent d'un seul côté est une divergence.
- **Analyse dynamique (skill 10).** Chaque connexion observée (nom DNS ou adresse, et port) doit correspondre à un flux de la matrice. Sinon, c'est un constat `flux_non_declare`.
- **Revue différentielle (skill 11).** La différence de `flux.yaml` entre deux commits montre les ouvertures nouvelles.

## Outillage

[`plugin/scripts/flux.py`](../../plugin/scripts/flux.py), déterministe ; il ne fait que lire ses entrées et écrit sur la sortie standard :

```bash
python3 plugin/scripts/flux.py valider .raton/flux.yaml [--dossier .raton] [--qualification qualification.yaml]
python3 plugin/scripts/flux.py ecarts .raton/flux.yaml --dossier .raton --qualification qualification.yaml
python3 plugin/scripts/flux.py rendre .raton/flux.yaml [--dossier .raton]
python3 plugin/scripts/flux.py egress .raton/flux.yaml
python3 plugin/scripts/flux.py generer .raton/flux.yaml --dossier .raton --plateforme plateforme.yaml [--namespace notes-de-frais]
```

- `valider` contrôle le schéma, les règles et, avec les options, les renvois vers le dossier et la fiche.
- `ecarts` liste les écarts du tableau ci-dessus.
- `rendre` produit le rendu lisible que relisent l'auteur et l'équipe infra.
- `egress` liste les connexions que l'application ouvre hors de son namespace, pour un proxy sortant ou un pare-feu.
- `generer` produit les politiques réseau ; la partie technique lui donne le nom des composants. Ses avertissements vont sur la sortie d'erreur.

`dossier.py valider .raton` valide aussi `flux.yaml`, avec ses renvois vers l'intention et la partie technique.

## Décisions

Validées le 2026-11-13 :

1. Un fichier `.raton/flux.yaml`, qui décrit le même commit que la partie technique, rempli par l'auteur avec le skill.
2. Une seule liste de flux, chacun dans le sens de la connexion (`de` ouvre, `vers` reçoit), plutôt que des listes séparées d'entrées et de sorties : un flux entre deux composants s'écrit une seule fois.
3. Cinq natures d'extrémités : composant, stockage, service tiers, autre système, service de la plateforme.
4. Des destinations désignées par un nom DNS (joker d'un seul niveau, comme Cilium) ou par un bloc d'adresses. Une variable seule marque une adresse à fixer, et bloque la génération.
5. Une couverture (flux non déclaré, échange sans flux…) signalée par des écarts à examiner, comme `dossier.py ecarts`, plutôt que par des erreurs de format.
6. Un fichier de plateforme, tenu par l'équipe infra, qui sépare la matrice du cluster.
7. Cilium comme CNI par défaut ; le mode standard, avec un proxy sortant, reste disponible.

Demandés à la même relecture :

- définir la plateforme, et distinguer interconnexion, échange et flux : voir [Vocabulaire](#vocabulaire) ;
- l'entrée externe ne se limite pas à Internet : la partie technique emploie désormais l'exposition `externe` de la qualification, au lieu de `internet` ;
- le skill demande la fiche de qualification avant de commencer, et ne va pas plus loin sans elle.

À valider :

1. **Les renvois**, reformulés. Seuls les flux vers un service tiers ou un autre système citent un échange et une interconnexion. Les flux vers les stockages de l'application, entre ses composants, et vers ou depuis la plateforme n'en citent pas, parce que ni l'intention ni la fiche ne les décrivent : voir le paragraphe « Renvois » de [Contenu](#contenu).
2. **Le nom des pods**, revu pour l'administration. Toujours un namespace par application et un refus par défaut. Mais les pods portent un nom lisible, déclaré dans la partie technique (`api`), plutôt que l'identifiant `C01`. Les politiques reprennent ce nom (`raton-api`) et rappellent l'identifiant et le libellé en annotation ; le rendu donne la grille complète.

## Reporté

- **Restreindre les noms résolus.** Limiter les requêtes DNS de l'application aux noms qu'elle déclare fermerait l'exfiltration par requêtes DNS. Il faut toutefois tenir compte des domaines de recherche de Kubernetes, qui multiplient les requêtes. À étudier avec Cilium.
- **Plages de ports.** Pour l'instant, on écrit un flux par port.
- **Comparaisons automatiques**, entre deux matrices et avec les flux observés : avec les skills 9 et 10.
