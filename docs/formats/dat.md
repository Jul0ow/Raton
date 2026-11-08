# Format du DAT

Statut : **proposition à valider** (2026-11-08).

Le DAT (dossier d'architecture technique) décrit une application soumise à la revue. Il a deux rôles :

- la **partie intention** dit ce que l'application doit faire. C'est la référence de la revue ;
- la **partie technique** décrit comment elle est construite, à un commit donné. Elle sert aux contrôles et à la comparaison avec la revue aveugle.

## Ce que le format doit permettre

Exigences tirées des principes de la feuille de route :

- **Séparer l'intention du code.** Le métier rédige l'intention sans regarder le code. Elle doit donc pouvoir être écrite, validée et transmise à part : elle a son propre fichier.
- **Comparer mécaniquement.** Profils, fonctions, données et échanges portent des identifiants stables. La partie technique et la matrice de flux renvoient à ces identifiants, si bien que le juge vérifie des références au lieu de comparer de la prose.
- **Limiter la prose.** On utilise des listes fermées partout où c'est possible et un texte libre court ailleurs. Le diff s'en trouve facilité et la surface d'injection réduite. Pour les agents, tout texte libre du DAT est une donnée, jamais une instruction.
- **Produire les mêmes artefacts en aveugle.** Le relecteur aveugle remplit la partie technique et la matrice de flux dans le même format, sans voir l'intention.
- **Lier au commit.** La partie technique décrit un SHA précis. L'intention a sa propre version et sa propre validation.

## Fichiers

```
.raton/
  intention.yaml    # partie intention : rédigée ou validée par le métier
  technique.yaml    # partie technique : assistée, décrit un commit
  flux.yaml         # matrice de flux (skill 3, format défini séparément)
```

Chaque fichier est en YAML et validé par un schéma JSON. Le métier n'a pas à lire de YAML : le skill DAT l'interroge, écrit le fichier, puis lui présente une version lisible à valider.

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
| `fonctions` | ce que l'application permet de faire, pour quels profils, sur quelles données, avec quels échanges | détection des fonctions non décrites |
| `echanges` | systèmes et services avec lesquels l'application échange des données, dans quel sens, lesquelles, pourquoi | référence de la matrice de flux |
| `exclusions` | ce que l'application ne fait pas, dit explicitement | affirmations vérifiables, par exemple « aucune donnée ne sort de l'entreprise » |
| `validation` | rédacteur, valideur, date, version, attestation de rédaction sans le code | traçabilité de la référence |

Le champ `sens` d'un échange donne le sens des **données** (`recoit`, `envoie`, `les_deux`), comme le métier le pense. Le sens des **connexions** (qui initie) est porté par la matrice de flux.

Exemple sur une application fictive :

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
    libelle: Notes de frais (montant, date, motif)
    origine: saisies par P01
    personnelles: oui            # non | oui | sensibles (art. 9 RGPD)
    conservation: 10 ans
  - id: D02
    libelle: Justificatifs scannés
    origine: déposés par P01
    personnelles: oui
    conservation: 10 ans
  - id: D03
    libelle: Nom et manager des salariés
    origine: annuaire de l'entreprise
    personnelles: oui
    conservation: non stockées

fonctions:
  - id: F01
    libelle: Déposer une note de frais et ses justificatifs
    profils: [P01]
    donnees: { ecrit: [D01, D02] }
  - id: F02
    libelle: Lire automatiquement les montants d'un justificatif
    declencheur: au dépôt d'un justificatif
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
    sens: recoit
    donnees: [D03]
    motif: retrouver le manager d'un salarié
  - id: E02
    partenaire: Service d'IA externe (fournisseur à préciser)
    sens: les_deux
    donnees: [D02, D01]
    motif: lire les montants sur les justificatifs
  - id: E03
    partenaire: Logiciel de comptabilité
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
| `stockages` | bases, fichiers, caches : type, données stockées |
| `services_tiers` | API, SDK et services externes appelés par le code, **y compris télémétrie, analytics et remontée d'erreurs** : données transmises, échanges couverts |
| `authentification` | mécanisme (`sso_entreprise`, `maison`, `aucune`), protocole, correspondance entre rôles techniques et profils |
| `configuration` | variables attendues, secrets attendus (noms seulement, jamais de valeur) et leur provenance |

Suite de l'exemple :

```yaml
format: raton/technique/v0

source:
  depot: https://git.example.com/finance/notes-de-frais
  commit: 4e3d3e49bc553b5ff0d6f7203f4791cf783997fb
  langages: [python, typescript]
  frameworks: [fastapi, react]

composants:
  - { id: C01, libelle: Interface web, role: web, technologie: react, expose: interne, fonctions: [F01, F03, F04] }
  - { id: C02, libelle: API, role: api, technologie: fastapi, expose: interne, fonctions: [F01, F02, F03, F04] }

stockages:
  - { id: S01, type: postgresql, donnees: [D01] }
  - { id: S02, type: stockage_objet, donnees: [D02] }

services_tiers:
  - id: T01
    libelle: API du fournisseur d'IA
    usage: lecture des justificatifs
    donnees_transmises: [D02]
    echanges: [E02]
  - id: T02
    libelle: SDK de remontée d'erreurs
    usage: suivi des plantages
    donnees_transmises: []       # les traces d'erreur peuvent contenir D01 : à vérifier
    echanges: []                 # aucun échange dans l'intention : flux non déclaré

authentification:
  mecanisme: sso_entreprise
  protocole: oidc
  roles:
    - { role: employee, profils: [P01] }
    - { role: manager, profils: [P02] }
    - { role: accounting, profils: [P03] }

configuration:
  variables: [DATABASE_URL, AI_ENDPOINT, OIDC_ISSUER]
  secrets:
    - { nom: AI_API_KEY, provenance: gestionnaire_secrets }
    - { nom: DATABASE_PASSWORD, provenance: gestionnaire_secrets }
```

Le service `T02` illustre le cas visé par le modèle de menace : un SDK ajouté par l'IA, que le métier ignore. Il ne renvoie à aucun échange de l'intention, ce qui en fait un constat même si la partie technique est honnête.

## Traçabilité et comparaison

Ce que le juge vérifie, par simple jeu de références.

Intention et technique (revue informée) :

- chaque fonction `F` est réalisée par au moins un composant, et une fonction trouvée dans le code sans `F` correspondante est une **fonction non décrite** ;
- chaque donnée stockée ou transmise est déclarée dans l'intention ;
- chaque service tiers renvoie à un échange `E`, sinon c'est un **flux non déclaré** ;
- chaque rôle technique correspond à un profil `P`, et un rôle sans profil (un `admin` par exemple) est un constat ;
- chaque exclusion `X` reçoit un verdict du relecteur informé : respectée, violée ou non vérifiable.

Intention et matrice de flux :

- chaque flux de la matrice renvoie à un échange `E`, et un échange sans flux est une incohérence.

Technique déclarée et reconstruction aveugle :

- l'aveugle produit `technique.yaml` et `flux.yaml` sans identifiants `P`, `F`, `D` ni `E`, puisqu'il ne voit pas l'intention ;
- le juge apparie composants, stockages, services tiers et flux, et tout élément présent d'un seul côté est une divergence escaladée à un humain.

## Proportionnalité

Toutes les sections sont obligatoires dès le premier palier. Elles sont courtes, et ce sont elles qui rendent la revue possible : une petite application interne peut fuiter des données comme une grosse. Le palier issu de la qualification joue sur le niveau de détail attendu et sur les contrôles, pas sur la présence des sections.

## Décisions à valider

1. **Deux fichiers** (intention, technique) plutôt qu'un document unique. Recommandé, pour pouvoir transmettre, valider et figer l'intention à part.
2. **YAML et schéma JSON**, avec un rendu lisible généré pour la validation humaine, plutôt qu'un Markdown structuré.
3. **Emplacement du dossier.** Proposition : `.raton/` dans le dépôt de l'application, versionné avec le code, pour que l'avis couvre code et dossier au même SHA et que la revue différentielle voie les changements du dossier. L'avis enregistre l'empreinte de `intention.yaml`, et toute modification de ce fichier exige une nouvelle validation. Le pipeline retire `.raton/` de ce que voit le relecteur aveugle. L'alternative est un dépôt séparé tenu par l'entreprise.
4. **Identifiants courts à préfixe** (`P01`, `F01`…) plutôt que des noms descriptifs.
5. **Valideur de l'intention.** Quand l'auteur du code et le porteur métier sont la même personne, faut-il un second valideur (manager, architecte) ?

## Suite

Une fois le format validé, il restera à écrire :

1. les schémas JSON (`schemas/intention.schema.json`, `schemas/technique.schema.json`) ;
2. cet exemple complet comme première application du corpus de test, avec le SDK de remontée d'erreurs comme constat attendu ;
3. le skill DAT : un entretien du métier pour l'intention, sans accès au code, puis une assistance pour la partie technique.
