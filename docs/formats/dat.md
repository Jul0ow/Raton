# Format du DAT

Statut : **validé** le 2026-11-08 (format v0). Complété le 2026-11-12 : les échanges renvoient aux interconnexions de la qualification.

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
  flux.yaml         # matrice de flux (skill 3, format défini séparément)
```

Le dossier vit dans `.raton/`, à la racine du dépôt de l'application, et se versionne avec le code. Un avis couvre ainsi code et dossier au même SHA, et la revue différentielle voit les changements du dossier. L'avis enregistre l'empreinte de `intention.yaml` : toute modification de ce fichier exige une nouvelle validation. Le pipeline retire `.raton/` de ce que voit le relecteur aveugle.

Chaque fichier est en YAML et validé par un schéma JSON. Le métier n'a pas à lire de YAML : le skill DAT l'interroge, écrit le fichier, puis lui présente un rendu lisible. Ce rendu est produit par un script déterministe, pas rédigé par une IA : le métier valide ainsi le contenu du fichier, pas une description de ce contenu.

Ce qui ne figure pas dans le DAT :

- la criticité, la sensibilité DICP et l'exposition, qui viennent de la fiche de qualification (skill 1) ;
- les manifestes, l'image, les probes et les ressources, que le palier Kubernetes (skill 5) lit directement dans le dépôt ;
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

Le champ `interconnexions` d'un échange cite les [interconnexions de la fiche de qualification](qualification.md#interconnexions) par lesquelles il passe. La fiche n'est pas du code : le métier peut l'avoir sous les yeux pendant la phase intention. Un échange qui ne correspond à aucune interconnexion révèle une qualification incomplète. On l'écrit alors sans ce champ, et on fait requalifier l'application. Le champ est facultatif pour le schéma, qui reste compatible avec les intentions déjà écrites ; c'est `qualification.py valider --intention` qui exige un renvoi pour chaque échange.

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
| `composants` | unités déployées : rôle (`web`, `api`, `worker`, `tache_planifiee`), technologie, exposition, fonctions réalisées |
| `stockages` | bases, fichiers, caches : type (liste fermée), technologie, données stockées |
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
  - { id: C01, libelle: API notes de frais, role: api, technologie: python / fastapi, expose: interne, fonctions: [F01, F02, F03, F04] }

stockages:
  - { id: S01, type: base_relationnelle, technologie: postgresql, donnees: [D01] }
  - { id: S02, type: stockage_objet, technologie: s3, donnees: [D02] }

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

## Traçabilité et comparaison

Ce que le juge vérifie, par simple jeu de références. La commande `dossier.py ecarts` fait déjà les vérifications marquées ⚙ entre intention et technique déclarée.

Intention et technique (revue informée) :

- ⚙ chaque fonction `F` est réalisée par au moins un composant ;
- une fonction trouvée dans le code sans `F` correspondante est une **fonction non décrite** ;
- ⚙ chaque service tiers renvoie à un échange `E`, sinon c'est un **flux non déclaré** ; à l'inverse, chaque échange est réalisé par un service ;
- ⚙ chaque donnée transmise à un service est prévue par l'échange correspondant ;
- ⚙ chaque rôle technique correspond à un profil `P`, et un rôle sans profil (un `admin` par exemple) est un constat ; chaque profil a un rôle ;
- chaque exclusion `X` reçoit un verdict du relecteur informé : respectée, violée ou non vérifiable.

Intention et qualification (`qualification.py valider --intention`, voir les [recoupements](qualification.md#recoupements-avec-lintention)) :

- ⚙ chaque échange renvoie à au moins une interconnexion de la fiche, et un échange où l'application envoie des données ne passe pas seulement par des interconnexions en lecture ;
- ⚙ la fiche n'est pas en deçà de l'intention : profils externes, données personnelles.

Intention et matrice de flux :

- chaque flux sortant de l'application renvoie à un échange `E` ou à un service d'infrastructure du SI (SSO, gestionnaire de secrets, journalisation), et un échange sans flux est une incohérence. La forme exacte sera fixée avec le format de la matrice (skill 3) ; les flux renverront aussi aux interconnexions de la qualification.

Technique déclarée et reconstruction aveugle :

- l'aveugle produit `technique.yaml` et `flux.yaml` sans identifiants `P`, `F`, `D` ni `E`, puisqu'il ne voit pas l'intention : ces références sont facultatives dans le schéma ;
- le juge apparie composants, stockages, services tiers et flux, et tout élément présent d'un seul côté est une divergence escaladée à un humain ;
- pour détecter les fonctions non décrites, l'aveugle devra aussi décrire les fonctions et les données qu'il observe. Le format sera fixé avec le skill 9 ; la piste est de reprendre celui de l'intention, pour un diff direct.

## Proportionnalité

Toutes les sections sont obligatoires dès le premier palier. Elles sont courtes, et ce sont elles qui rendent la revue possible : une petite application interne peut fuiter des données comme une grosse. Le palier issu de la qualification joue sur le niveau de détail attendu et sur les contrôles, pas sur la présence des sections.

## Décisions

Validées le 2026-11-08 :

1. Deux fichiers (intention, technique) plutôt qu'un document unique.
2. YAML et schéma JSON, avec un rendu lisible généré pour la validation humaine.
3. Dossier dans `.raton/`, versionné avec le code ; empreinte de l'intention enregistrée dans l'avis.
4. Identifiants courts à préfixe (`P01`, `F01`…).

Complété le 2026-11-12 : chaque échange peut citer les interconnexions de la fiche de qualification par lesquelles il passe.

Écarté pour l'instant : exiger un second valideur de l'intention quand l'auteur du code et le porteur métier sont la même personne.

## Outillage

[`plugin/scripts/dossier.py`](../../plugin/scripts/dossier.py), déterministe et en lecture seule :

```bash
python3 plugin/scripts/dossier.py valider <fichier ou répertoire .raton>
python3 plugin/scripts/dossier.py rendre .raton/intention.yaml
python3 plugin/scripts/dossier.py ecarts .raton
```

`valider` contrôle le schéma, l'unicité des identifiants et les références, internes à l'intention puis de la technique vers l'intention. Le chargeur YAML refuse les clés en double, que YAML écraserait sans rien dire : un même fichier pourrait sinon montrer une valeur à l'humain et en faire lire une autre à un outil.
