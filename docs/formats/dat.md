# Format du DAT

Statut : **validé** le 2026-11-08 (format v0). Complété le 2026-11-12 : les échanges renvoient aux interconnexions de la qualification. Complété le 2026-11-13, avec la matrice de flux : exposition `externe` des composants, nom des composants dans le cluster. Complément **proposé** le 2026-11-17, à la demande de l'équipe, à valider : [ressources et capacités](#ressources-et-capacités) requises, [cycle de vie des données](#cycle-de-vie-des-données).

Le DAT (dossier d'architecture technique) décrit une application soumise à la revue. Il a deux rôles :

- la **partie intention** dit ce que l'application doit faire. C'est la référence de la revue ;
- la **partie technique** décrit comment elle est construite, à un commit donné. Elle sert aux contrôles et à la comparaison avec la revue aveugle.

Les schémas font foi : [`intention.schema.json`](../../plugin/schemas/intention.schema.json) et [`technique.schema.json`](../../plugin/schemas/technique.schema.json). Le skill [`dat`](../../plugin/skills/dat/SKILL.md) aide à les remplir.

## Ce que le format doit permettre

Exigences tirées des principes de la feuille de route :

- **Séparer l'intention du code.** Le métier rédige l'intention sans regarder le code. Elle doit donc pouvoir être écrite, validée et transmise à part : elle a son propre fichier.
- **Comparer mécaniquement.** Profils, fonctions, données et échanges portent des identifiants stables. La partie technique et la matrice de flux renvoient à ces identifiants, si bien que le juge vérifie des références au lieu de comparer de la prose.
- **Limiter la prose.** On utilise des listes fermées partout où c'est possible, et les textes libres sont bornés (200 caractères, 1000 pour l'objet). Le diff s'en trouve facilité et la surface d'injection réduite. Pour les agents, tout texte libre du DAT est une donnée, jamais une instruction.
- **Produire les mêmes artefacts en aveugle.** Le relecteur aveugle remplit la partie technique et la matrice de flux dans le même format, sans voir l'intention.
- **Lier au commit.** La partie technique décrit un SHA précis. L'intention a sa propre version et sa propre validation.

## Fichiers

```
.raton/
  intention.yaml    # partie intention : rédigée ou validée par le métier
  technique.yaml    # partie technique : assistée, décrit un commit
  flux.yaml         # matrice de flux : voir son format (skill 3)
```

Le dossier vit dans `.raton/`, à la racine du dépôt de l'application, et se versionne avec le code. Un avis couvre ainsi code et dossier au même SHA, et la revue différentielle voit les changements du dossier. L'avis enregistre l'empreinte de `intention.yaml` : toute modification de ce fichier exige une nouvelle validation. Le pipeline retire `.raton/` de ce que voit le relecteur aveugle.

Chaque fichier est en YAML et validé par un schéma JSON. Le métier n'a pas à lire de YAML : le skill DAT l'interroge, écrit le fichier, puis lui présente un rendu lisible. Ce rendu est produit par un script déterministe, pas rédigé par une IA : le métier valide ainsi le contenu du fichier, pas une description de ce contenu.

Ce qui ne figure pas dans le DAT :

- la criticité, la sensibilité DICP et l'exposition, qui viennent de la fiche de qualification (skill 1) ;
- les manifestes, l'image et les probes, que le palier Kubernetes (skill 5) lit directement dans le dépôt. Les ressources, elles, sont déclarées dans la partie technique, et le palier Kubernetes les confronte aux manifestes ;
- les logs, la sauvegarde et le responsable de la maintenance, qui relèvent du dossier d'exploitation (skill 4).

## Partie intention

Elle est écrite en langage métier, sans vocabulaire technique. Le porteur métier la rédige ou la valide **sans partir du code** : générée depuis le code, elle concorderait forcément avec lui et ne prouverait rien. Pendant la phase intention, le skill DAT n'a donc pas accès au dépôt.

| Section | Contenu | À quoi elle sert |
|---|---|---|
| `application` | nom, objet (le besoin couvert, en quelques phrases), porteur métier | identifier l'application et son responsable |
| `profils` | qui utilise l'application : population interne ou externe, effectif approximatif | contrôle d'accès attendu (skill 8) |
| `donnees` | catégories de données manipulées : origine, caractère personnel, durée de conservation | proportionnalité, RGPD, détection des données inattendues |
| `fonctions` | ce que l'application permet de faire, pour quels profils ou sur quel déclencheur, sur quelles données, avec quels échanges | détection des fonctions non décrites |
| `echanges` | systèmes et services avec lesquels l'application échange des données, dans quel sens, lesquelles, pourquoi, et par quelles interconnexions de la fiche de qualification | référence de la matrice de flux, recoupement avec la qualification |
| `exclusions` | ce que l'application ne fait pas, dit explicitement | affirmations vérifiables, par exemple « aucune donnée ne sort de l'entreprise » |
| `validation` | rédacteur, valideur, date, version, attestation de rédaction sans le code | traçabilité de la référence |

Le champ `sens` d'un échange donne le sens des **données** (`recoit`, `envoie`, `les_deux`), comme le métier le pense. Le sens des **connexions** (qui initie) est porté par la matrice de flux.

Le champ `interconnexions` d'un échange cite les [interconnexions de la fiche de qualification](qualification.md#interconnexions) par lesquelles il passe. La fiche n'est pas du code : le métier peut l'avoir sous les yeux pendant la phase intention. Le skill DAT exige d'ailleurs la fiche validée avant de commencer, quelle que soit la phase. Un échange qui ne correspond à aucune interconnexion révèle une qualification incomplète. On l'écrit alors sans ce champ, et on fait requalifier l'application. Le champ est facultatif pour le schéma, qui reste compatible avec les intentions déjà écrites ; c'est `qualification.py valider --intention` qui exige un renvoi pour chaque échange.

Tant que la section `validation` est absente, l'intention est un brouillon : on peut la valider contre le schéma et la rendre lisible, mais la revue ne peut pas s'appuyer dessus.

Exemple, repris de l'application [`notes-de-frais`](../../corpus/notes-de-frais/) du corpus de test :

```yaml
format: raton/intention/v0

application:
  nom: Notes de frais
  objet: >
    Les salariés déposent leurs notes de frais et leurs justificatifs,
    leur manager les valide, puis la comptabilité exporte les notes validées.
  porteur: { nom: Marie Durand, entite: Direction financière }

profils:
  - { id: P01, libelle: Salarié, population: interne, effectif: 2000 }
  - { id: P02, libelle: Manager, population: interne, effectif: 200 }
  - { id: P03, libelle: Comptable, population: interne, effectif: 5 }

donnees:
  - id: D01
    libelle: Notes de frais (salarié, montant, date, motif, décision)
    origine: saisies par P01, décision par P02
    personnelles: oui            # non | oui | sensibles (art. 9 RGPD)
    conservation: 10 ans
  - id: D02
    libelle: Justificatifs scannés
    origine: déposés par P01
    personnelles: oui
    conservation: 10 ans
  - id: D03
    libelle: Rattachement des salariés à leur manager
    origine: annuaire de l'entreprise
    personnelles: oui
    conservation: non stockées

fonctions:
  - id: F01
    libelle: Déposer ses notes de frais et suivre leur traitement
    profils: [P01]
    donnees: { lit: [D01, D02], ecrit: [D01, D02] }
  - id: F02
    libelle: Lire automatiquement le montant et la date d'un justificatif
    declencheur: dépôt d'un justificatif sans montant ou sans date saisis
    donnees: { lit: [D02], ecrit: [D01] }
    echanges: [E02]
  - id: F03
    libelle: Valider ou refuser les notes de son équipe
    profils: [P02]
    donnees: { lit: [D01, D02, D03], ecrit: [D01] }
    echanges: [E01]
  - id: F04
    libelle: Exporter les notes validées vers la comptabilité
    profils: [P03]
    donnees: { lit: [D01] }
    echanges: [E03]

echanges:
  - id: E01
    partenaire: Annuaire de l'entreprise
    interconnexions: [I01]
    sens: recoit
    donnees: [D03]
    motif: savoir quels salariés dépendent d'un manager
  - id: E02
    partenaire: Service d'IA externe (fournisseur à préciser)
    interconnexions: [I02]
    sens: les_deux
    donnees: [D02, D01]
    motif: lire le montant et la date sur les justificatifs
  - id: E03
    partenaire: Logiciel de comptabilité
    interconnexions: [I03]
    sens: envoie
    donnees: [D01]
    motif: export des notes validées

exclusions:
  - { id: X01, libelle: "Aucune donnée ne sort de l'entreprise, sauf les justificatifs envoyés au service d'IA (E02)" }
  - { id: X02, libelle: Aucun accès depuis Internet }
  - { id: X03, libelle: "L'application ne valide jamais une note sans action d'un manager" }

validation:
  version: 1
  redige_par: Marie Durand
  valide_par: Marie Durand
  date: 2026-11-08
  redige_sans_le_code: true
```

## Partie technique

Elle décrit l'application telle qu'elle est construite, au commit indiqué. Elle est assistée : l'auteur peut la remplir avec une IA à partir du code. Elle ne prouve donc rien à elle seule. Sa valeur vient de deux comparaisons : avec l'intention (revue informée) et avec la reconstruction aveugle.

| Section | Contenu |
|---|---|
| `source` | dépôt, commit (SHA complet), langages, frameworks |
| `composants` | unités déployées : nom dans le cluster, rôle (`web`, `api`, `worker`, `tache_planifiee`), technologie, exposition, fonctions réalisées |
| `stockages` | bases, fichiers, caches : type (liste fermée), technologie, données stockées ; nom dans le cluster s'il est déployé avec l'application |
| `composants[].ressources`, `stockages[].ressources` | processeur et mémoire requis : nombre d'instances, demande et plafond d'une instance ; pour un stockage, seulement s'il est déployé dans le namespace de l'application |
| `stockages[].capacite` | volume de stockage requis : à la mise en production, puis par an |
| `cycle_de_vie` | pour chaque donnée conservée : durée de conservation appliquée, ce qu'elle devient ensuite, ce qui l'applique |
| `services_tiers` | tout ce que le code appelle hors de l'application, systèmes de l'entreprise compris, sauf les stockages et le SSO. **Y compris télémétrie, analytics et remontée d'erreurs.** Pour chacun : données transmises, échanges réalisés |
| `authentification` | mécanisme (`sso_entreprise`, `maison`, `aucune`), protocole, correspondance entre rôles techniques et profils |
| `configuration` | variables attendues, secrets attendus (noms seulement, jamais de valeur) et leur provenance |

Suite de l'exemple, telle qu'une partie technique **exacte** décrirait l'application :

```yaml
format: raton/technique/v0

source:
  depot: https://git.example.com/finance/notes-de-frais
  commit: 4e3d3e49bc553b5ff0d6f7203f4791cf783997fb
  langages: [python]
  frameworks: [fastapi, sqlalchemy]

composants:
  - id: C01
    nom: api
    libelle: API notes de frais
    role: api
    technologie: python / fastapi
    expose: interne
    fonctions: [F01, F02, F03, F04]
    ressources: { instances: 2, cpu: 250m, cpu_max: "1", memoire: 256Mi, memoire_max: 512Mi }

stockages:
  - { id: S01, type: base_relationnelle, technologie: postgresql, donnees: [D01], capacite: { initiale: 1Gi, par_an: 100Mi } }
  - { id: S02, type: stockage_objet, technologie: s3, donnees: [D02], capacite: { initiale: 1Gi, par_an: 25Gi } }

services_tiers:
  - { id: T01, libelle: Annuaire de l'entreprise, usage: liste des salariés d'un manager, echanges: [E01] }
  - { id: T02, libelle: API du fournisseur d'IA, usage: lecture des justificatifs, donnees_transmises: [D02], echanges: [E02] }
  - { id: T03, libelle: API du logiciel de comptabilité, usage: import des notes validées, donnees_transmises: [D01], echanges: [E03] }
  - id: T04
    libelle: SDK Sentry (remontée d'erreurs)
    usage: suivi des erreurs et des performances
    donnees_transmises: [D01]    # contenu des requêtes et identité des utilisateurs
    echanges: []                 # aucun échange dans l'intention : flux non déclaré

authentification:
  mecanisme: sso_entreprise
  protocole: oidc
  roles:
    - { role: employee, profils: [P01] }
    - { role: manager, profils: [P02] }
    - { role: accounting, profils: [P03] }

cycle_de_vie:
  - { donnee: D01, fin: aucune, precision: rien dans le code ne supprime les notes de la base }
  - { donnee: D02, fin: aucune, precision: rien dans le code ne supprime les justificatifs du stockage objet }

configuration:
  variables: [OIDC_ISSUER, OIDC_AUDIENCE, AI_ENDPOINT, DIRECTORY_URL, COMPTA_URL, S3_ENDPOINT, S3_BUCKET]
  secrets:
    - { nom: DATABASE_URL, provenance: gestionnaire_secrets }
    - { nom: AI_API_KEY, provenance: gestionnaire_secrets }
    - { nom: DIRECTORY_TOKEN, provenance: gestionnaire_secrets }
    - { nom: COMPTA_TOKEN, provenance: gestionnaire_secrets }
    - { nom: AWS_ACCESS_KEY_ID, provenance: gestionnaire_secrets }
    - { nom: AWS_SECRET_ACCESS_KEY, provenance: gestionnaire_secrets }
```

Le service `T04` illustre le cas visé par le modèle de menace : un SDK ajouté par l'IA, que le métier ignore. Il ne renvoie à aucun échange de l'intention, ce qui en fait un constat même quand la partie technique est honnête. Dans le corpus, la partie technique soumise par l'auteur l'omet : c'est à la revue de le trouver dans le code.

Le cycle de vie montre l'autre intérêt d'une description exacte : l'intention prévoit de conserver notes et justificatifs 10 ans, mais rien dans le code ne les supprime ensuite. Décrire le cycle de vie fait apparaître cet écart dès la rédaction du DAT, avant toute revue.

### Ressources et capacités

L'équipe DevOps dimensionne le namespace, les bases et les stockages de l'application avant de la déployer. La partie technique lui dit ce qu'il faut :

- **par composant**, `ressources` : nombre d'`instances` en fonctionnement normal (pour une tâche planifiée, les pods lancés à chaque exécution) ; `cpu` et `memoire` d'une instance en fonctionnement normal ; `cpu_max` et `memoire_max`, son plafond. Sans plafond déclaré, le plafond vaut la demande ;
- **par stockage**, `capacite` : volume `initiale`, à la mise en production, marge comprise, et croissance estimée `par_an` (`0Gi` pour un cache). Avec la durée de conservation du cycle de vie, elle dit jusqu'où le stockage grossira ;
- **par stockage déployé dans le namespace** (il a un `nom`, comme une base PostgreSQL lancée avec l'application), aussi des `ressources`, puisque ses pods en consomment. Un stockage géré hors du cluster n'en a pas.

Les quantités s'écrivent en unités Kubernetes : `250m` ou `0.5` pour le processeur, `512Mi`, `2Gi`, `1Ti` pour la mémoire et le stockage. Ce sont les valeurs que l'équipe DevOps reportera dans les manifestes, sans conversion. Les suffixes décimaux (`M`, `G`) sont refusés : en Kubernetes, `512m` vaut 0,512 octet, une erreur facile à commettre et difficile à voir.

Ce sont des ordres de grandeur estimés par l'auteur, pas des mesures. Ils servent trois fois :

- l'équipe DevOps dimensionne et réserve ;
- le palier Kubernetes (skill 5) vérifie que les `requests` et `limits` des manifestes reprennent ces valeurs : `requests` pour la demande, `limits` pour le plafond ;
- l'analyse dynamique (skill 10), en bac à sable, pourra comparer la consommation observée aux valeurs déclarées.

`dossier.py rendre .raton/technique.yaml` additionne les besoins : processeur et mémoire demandés et au plus, stockage à la mise en production et par an.

### Cycle de vie des données

L'intention dit combien de temps le métier veut garder chaque donnée (`conservation`), dans ses mots. La partie technique dit ce que l'application en fait réellement, pour chaque donnée conservée dans un stockage :

| Champ | Contenu |
|---|---|
| `donnee` | la donnée de l'intention (`D01`) |
| `duree` | la durée appliquée et son point de départ, par exemple « 10 ans après l'export » |
| `fin` | ce qu'elle devient ensuite : `suppression`, `anonymisation`, `archivage`, ou `aucune` si elle est conservée sans limite |
| `mecanisme` | ce qui l'applique : `composant` (le code de l'application, par le composant cité dans `composant`, souvent une tâche planifiée), `regle_stockage` (l'expiration native du stockage : règle de cycle de vie d'un stockage objet, durée de vie d'un cache), `manuel` (une procédure humaine, que le dossier d'exploitation devra décrire) |
| `precision` | facultatif : où va une donnée archivée, ce qui déclenche la fin, une limite connue |

Le reste du cycle de vie est déjà dans le dossier, et le rendu le rassemble dans un seul tableau par donnée :

- **collecte et usage** : l'origine de la donnée et les fonctions qui la lisent ou l'écrivent, dans l'intention ;
- **conservation** : les stockages qui la contiennent, dans la partie technique ;
- **transmission** : les services tiers qui la reçoivent, dans la partie technique, et les flux qui la transportent, dans la matrice de flux ;
- **fin** : la nouvelle section.

`duree` et `mecanisme` sont obligatoires sauf si `fin` vaut `aucune`, et `composant` l'est quand le mécanisme est un composant. Une donnée qu'aucun stockage ne conserve, comme le rattachement des salariés à leur manager, lu dans l'annuaire à chaque demande, n'a pas d'entrée : le rendu la liste à part.

La conservation des sauvegardes relève du dossier d'exploitation (skill 4) : une donnée supprimée de la base reste dans les sauvegardes jusqu'à leur expiration.

### Déclarations propres à l'auteur

Ressources, capacités et cycle de vie sont facultatifs pour le schéma : le relecteur aveugle, qui produit une partie technique au même format, ne peut pas deviner le dimensionnement voulu par l'auteur. Dans le dossier de l'auteur, en revanche, ils sont obligatoires : `dossier.py valider .raton` les exige dès que la partie technique est validée avec l'intention. C'est le même principe que pour les renvois aux interconnexions, facultatifs pour le schéma et exigés par `qualification.py`.

## Traçabilité et comparaison

Ce que le juge vérifie, par simple jeu de références. La commande `dossier.py ecarts` fait déjà les vérifications marquées ⚙ entre intention et technique déclarée.

Intention et technique (revue informée) :

- ⚙ chaque fonction `F` est réalisée par au moins un composant ;
- une fonction trouvée dans le code sans `F` correspondante est une **fonction non décrite** ;
- ⚙ chaque service tiers renvoie à un échange `E`, sinon c'est un **flux non déclaré** ; à l'inverse, chaque échange est réalisé par un service ;
- ⚙ chaque donnée transmise à un service est prévue par l'échange correspondant ;
- ⚙ chaque rôle technique correspond à un profil `P`, et un rôle sans profil (un `admin` par exemple) est un constat ; chaque profil a un rôle ;
- chaque exclusion `X` reçoit un verdict du relecteur informé : respectée, violée ou non vérifiable ;
- ⚙ chaque composant déclare ses ressources, chaque stockage sa capacité, chaque stockage déployé dans le namespace ses ressources, et chaque donnée conservée dans un stockage son cycle de vie ; un cycle de vie ne décrit qu'une donnée conservée ;
- chaque cycle de vie est confronté au code et à la conservation de l'intention : une suppression déclarée que le code ne fait pas est un **dossier inexact** ; une conservation prévue par l'intention que rien ne fait respecter, comme dans l'exemple, est un constat que le métier tranche, en faisant ajouter la suppression ou en faisant évoluer son intention.

Intention et qualification (`qualification.py valider --intention`, voir les [recoupements](qualification.md#recoupements-avec-lintention)) :

- ⚙ chaque échange renvoie à au moins une interconnexion de la fiche, et un échange où l'application envoie des données ne passe pas seulement par des interconnexions en lecture ;
- ⚙ la fiche n'est pas en deçà de l'intention : profils externes, données personnelles.

Intention, technique et matrice de flux (`flux.py ecarts`, voir le [format de la matrice](flux.md#confrontation-avec-le-dossier)) :

- ⚙ chaque flux vers un service tiers ou un autre système renvoie à un échange `E` et à une interconnexion `I` ; les flux vers les stockages de l'application et vers les services de la plateforme (SSO, gestionnaire de secrets, journalisation, supervision) n'en ont pas besoin ;
- ⚙ chaque échange est réalisé par au moins un flux, et chaque service tiers et chaque stockage sont atteints par un flux : sinon, les politiques réseau générées les bloqueraient.

Technique déclarée et reconstruction aveugle :

- l'aveugle produit `technique.yaml` et `flux.yaml` sans identifiants `P`, `F`, `D`, `E` ni `I`, puisqu'il ne voit ni l'intention ni la fiche de qualification : ces références sont facultatives dans les schémas. Il omet aussi ressources, capacités et cycle de vie, qui sont des déclarations de l'auteur ;
- le juge apparie composants, stockages, services tiers et flux, et tout élément présent d'un seul côté est une divergence escaladée à un humain ;
- pour détecter les fonctions non décrites, l'aveugle devra aussi décrire les fonctions et les données qu'il observe. Le format sera fixé avec le skill 9 ; la piste est de reprendre celui de l'intention, pour un diff direct. La même description dira quelles suppressions il trouve dans le code, pour confronter le cycle de vie déclaré.

## Proportionnalité

Toutes les sections sont obligatoires dès le premier palier. Elles sont courtes, et ce sont elles qui rendent la revue possible : une petite application interne peut fuiter des données comme une grosse. Le palier issu de la qualification joue sur le niveau de détail attendu et sur les contrôles, pas sur la présence des sections.

## Décisions

Validées le 2026-11-08 :

1. Deux fichiers (intention, technique) plutôt qu'un document unique.
2. YAML et schéma JSON, avec un rendu lisible généré pour la validation humaine.
3. Dossier dans `.raton/`, versionné avec le code ; empreinte de l'intention enregistrée dans l'avis.
4. Identifiants courts à préfixe (`P01`, `F01`…).

Complété le 2026-11-12 : chaque échange peut citer les interconnexions de la fiche de qualification par lesquelles il passe.

Complété le 2026-11-13, à la relecture de la matrice de flux :

- l'exposition d'un composant vaut `externe`, et non plus `internet`, avec le sens qu'elle a dans la qualification : joignable depuis un réseau que l'entreprise ne maîtrise pas, Internet ou réseau d'un partenaire ;
- chaque composant, et chaque stockage déployé avec l'application, a un `nom` court et lisible (`api`, `worker`, `postgres`), unique dans l'application. Ses pods le portent en étiquette et les politiques réseau le reprennent : l'équipe DevOps lit `api` dans le cluster plutôt que `C01`.

Proposé le 2026-11-17, à la demande de l'équipe, à valider :

- la partie technique documente les ressources requises : processeur et mémoire par composant (instances, demande, plafond), en unités Kubernetes, et volume par stockage (initial et par an) ;
- elle décrit le cycle de vie de chaque donnée conservée : durée appliquée, fin, mécanisme ;
- ces déclarations sont facultatives pour le schéma, pour le relecteur aveugle, et exigées par `dossier.py` dans le dossier de l'auteur ;
- le palier Kubernetes vérifiera que les `requests` et `limits` des manifestes reprennent les ressources déclarées.

Questions pour la validation :

- faut-il déclarer aussi la conservation chez les services tiers (un fournisseur d'IA qui garde les justificatifs 30 jours, par exemple) ? Elle dépend du contrat plus que du code ; elle pourrait entrer dans `services_tiers` ;
- l'équipe DevOps veut-elle un nombre d'instances minimal selon la disponibilité de la fiche de qualification, par exemple deux instances dès le niveau 3 ? Le palier Kubernetes pourrait le vérifier.

Écarté pour l'instant : exiger un second valideur de l'intention quand l'auteur du code et le porteur métier sont la même personne.

## Outillage

[`plugin/scripts/dossier.py`](../../plugin/scripts/dossier.py), déterministe et en lecture seule :

```bash
python3 plugin/scripts/dossier.py valider <fichier ou répertoire .raton>
python3 plugin/scripts/dossier.py rendre .raton/intention.yaml
python3 plugin/scripts/dossier.py rendre .raton/technique.yaml   # ressources totales, cycle de vie
python3 plugin/scripts/dossier.py ecarts .raton
```

`valider` contrôle le schéma, l'unicité des identifiants et les références : internes à l'intention, de la technique vers l'intention, puis de la [matrice de flux](flux.md) vers les deux. Validée avec l'intention, la partie technique doit aussi porter les [déclarations propres à l'auteur](#déclarations-propres-à-lauteur). Le chargeur YAML refuse les clés en double, que YAML écraserait sans rien dire : un même fichier pourrait sinon montrer une valeur à l'humain et en faire lire une autre à un outil.
