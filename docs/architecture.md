# Architecture

Ce document montre comment s'enchaînent les skills, ce qu'ils lisent et produisent, et où interviennent les humains. Il suit la [feuille de route](feuille-de-route.md) ; les rôles qu'elle ne fixe pas encore sont rassemblés à la fin, dans [Hypothèses à confirmer](#hypothèses-à-confirmer).

Code couleur des skills et des formats :

- vert : en place ;
- jaune : proposé, à valider ;
- gris pointillé : à faire.

## 1. Un même pipeline, deux usages

Raton sert à relire de vraies applications, mais il faut aussi savoir ce qu'il vaut : une revue qui ne trouve rien ne prouve rien si l'on ignore ce qu'elle sait trouver. Le même pipeline tourne donc dans deux boucles.

```mermaid
flowchart LR
  APP["Application réelle<br/>code + dossier .raton/"] --> PIPE
  CAS["Cas du corpus<br/>dépôt volontairement piégé"] --> PIPE
  PIPE[["Pipeline Raton<br/>contrôles et revue par agents"]] --> RAP[/"Rapports de contrôle<br/>constats + périmètre"/]

  RAP -->|"application réelle"| SYN["Synthèse"] --> AVIS[/"Avis à signer"/]

  RAP -->|"cas du corpus"| CMP{{"constats.py comparer"}}
  ATT[/"attendu.yaml<br/>corrigé du cas"/] --> CMP
  CMP --> MES[/"Mesure : détectés,<br/>manqués, en trop"/]
  MES -.->|"améliorer prompts,<br/>règles, outils"| PIPE

  MAINT(("Mainteneurs<br/>de Raton")) -->|"conçoivent le piège"| CAS
  MAINT -->|"écrivent le corrigé"| ATT

  classDef humain fill:#d0ebff,stroke:#1971c2,color:#000
  classDef corpus fill:#fff4e6,stroke:#e8590c,color:#000
  class MAINT humain
  class CAS,ATT,CMP,MES corpus
```

**Boucle de production** (en haut) : une application réelle passe dans le pipeline, les rapports sont synthétisés en un avis que l'entreprise signe. Il n'y a pas de corrigé : personne ne sait d'avance ce que contient l'application.

**Boucle de mesure** (en bas, en orange) : c'est le contrôle qualité de Raton lui-même, l'équivalent de tests unitaires pour les relecteurs.

- **Qui écrit `attendu.yaml` ?** Les mainteneurs de Raton, c'est-à-dire l'équipe qui développe la bibliothèque, au moment où ils construisent un cas piégé. Ils savent ce qu'ils ont caché ; le corrigé l'écrit dans le format des constats.
- **Le corrigé n'entre jamais dans le pipeline.** Les relecteurs ne voient que `depot/`. Le corrigé n'intervient qu'après, pour noter leurs rapports.
- **À quoi sert la comparaison ?**
  - **Mesurer la détection** : quelle part des pièges est trouvée, et combien de constats sont des faux positifs.
  - **Éviter les régressions** : un changement de prompt, de modèle ou de version d'outil se mesure avant d'être adopté.
  - **Trancher les questions ouvertes** : un même modèle sur plusieurs passes ou des modèles différents, sur des chiffres plutôt qu'à l'intuition.
  - **Rendre l'avis honnête** : la rubrique « ce qui n'a pas été vérifié » s'appuie sur ce que Raton sait, ou ne sait pas, détecter.

## 2. Parcours d'une application

Qui fait quoi, dans l'ordre, du code produit par le métier jusqu'au déploiement.

```mermaid
sequenceDiagram
  autonumber
  actor M as Porteur métier
  participant R as Raton
  actor E as Équipe de revue
  actor S as Signataire
  actor X as Exploitation

  Note over M: Application produite avec une IA
  M->>R: Qualification (1) : répond aux questions
  E->>R: Valide la qualification
  R-->>M: Palier d'exigence et contrôles obligatoires
  M->>R: DAT, phase intention (2), sans le code
  R-->>M: Rendu lisible de l'intention
  M->>R: Valide et atteste
  M->>R: DAT technique (2), matrice de flux (3), dossier d'exploitation (4)
  loop Jusqu'à un dossier complet
    M->>R: Pré-contrôle (13)
    R-->>M: Liste des manques
  end
  M->>E: Soumet le dépôt au commit SHA
  E->>R: Lance la revue
  Note over R: Contrôles déterministes (5 à 8, SAST)<br/>Revue aveugle et informée, juge (9)<br/>Analyse dynamique (10)
  R-->>E: Rapports et divergences entre passes
  E->>R: Tranche les divergences
  R-->>E: Synthèse (12) : projet d'avis, périmètre vérifié et non vérifié
  alt Constats à corriger
    E-->>M: Constats à corriger
    M->>E: Nouvelle version, nouveau SHA
    E->>R: Revue différentielle (11)
    R-->>E: Projet d'avis sur le nouveau SHA
  end
  E->>S: Avis argumenté
  S-->>E: Signe : Go, Go avec réserves ou No-Go
  E->>X: Avis signé, NetworkPolicies, dossier d'exploitation
  Note over X: Déploie. Tout flux non déclaré<br/>dans la matrice est bloqué.
```

Trois moments humains structurent le parcours :

- **le métier atteste son intention** (étape 6) : c'est la référence de toute la revue ;
- **l'équipe de revue tranche** les divergences entre passes et entre relecteurs (étape 13) ;
- **le signataire engage l'entreprise** sur un commit précis (étape 20).

Toute nouvelle version repasse par la revue différentielle et donne un nouvel avis.

## 3. Skills et données

### Constituer le dossier

Le métier et l'auteur (souvent la même personne) préparent le dossier avant de soumettre l'application.

```mermaid
flowchart LR
  M(("Porteur<br/>métier"))
  E(("Équipe<br/>de revue"))
  RGPD[("Registre RGPD")]
  CODE[("Dépôt de l'application<br/>au commit SHA")]

  Q["1 · Qualification"]
  DAT["2 · DAT"]
  EXP["4 · Dossier d'exploitation"]
  MF["3 · Matrice de flux"]
  PC["13 · Pré-contrôle"]

  QF[/"Fiche de qualification<br/>palier, contrôles obligatoires"/]
  INT[/".raton/intention.yaml"/]
  TEC[/".raton/technique.yaml"/]
  EXF[/".raton/ dossier d'exploitation"/]
  FLX[/".raton/flux.yaml"/]
  NP[/"NetworkPolicies<br/>règles d'egress"/]
  MQ[/"Liste des manques"/]

  RGPD --> Q
  E -->|"valide"| Q
  M -->|"répond"| Q
  M -->|"entretien, sans le code"| DAT
  CODE -->|"phase technique"| DAT
  M --> EXP
  Q --> QF
  DAT --> INT
  DAT --> TEC
  EXP --> EXF
  INT --> MF
  CODE --> MF
  MF --> FLX
  FLX -->|"génère"| NP
  QF --> PC
  INT --> PC
  TEC --> PC
  FLX --> PC
  EXF --> PC
  PC --> MQ
  MQ -.->|"compléter"| M

  classDef humain fill:#d0ebff,stroke:#1971c2,color:#000
  classDef fait fill:#d3f9d8,stroke:#2b8a3e,color:#000
  classDef afaire fill:#f8f9fa,stroke:#868e96,color:#000,stroke-dasharray:4 3
  class M,E humain
  class DAT,INT,TEC fait
  class Q,MF,EXP,PC,QF,FLX,EXF,NP,MQ afaire
```

### Contrôler et conclure

L'équipe de revue lance le pipeline sur le commit soumis. La fiche de qualification décide des contrôles à exécuter ; chacun produit un rapport au format commun.

```mermaid
flowchart LR
  QF[/"Fiche de qualification"/]
  CODE[("Code au commit SHA")]
  DOS[/"Dossier .raton/"/]

  subgraph CTRL ["Contrôles retenus par la qualification"]
    direction TB
    DET["Contrôles déterministes<br/>5 · Palier Kubernetes<br/>6 · Chaîne d'approvisionnement<br/>7 · Secrets<br/>8 · Identité et accès<br/>SAST"]
    AG["9 · Revue par agents<br/>aveugle, informée, juge"]
    DYN["10 · Analyse dynamique<br/>bac à sable"]
  end

  SBOM[/"SBOM"/]
  RAP[/"Rapports de contrôle<br/>constats + périmètre"/]
  SYN["12 · Synthèse et avis"]
  AVIS[/"Avis sur le SHA<br/>Go · réserves · No-Go"/]
  DIFF["11 · Revue différentielle"]
  E(("Équipe<br/>de revue"))
  S(("Signataire"))

  QF -.->|"choisit les contrôles"| CTRL
  CODE --> CTRL
  DOS -->|"informé, juge"| AG
  DOS -->|"flux déclarés"| DYN
  DET --> SBOM
  DET --> RAP
  AG --> RAP
  DYN --> RAP
  RAP --> SYN
  E -->|"tranche"| SYN
  SYN --> AVIS
  S -->|"signe"| AVIS
  AVIS -->|"version suivante"| DIFF
  DIFF -->|"rapports sur le delta"| RAP

  classDef humain fill:#d0ebff,stroke:#1971c2,color:#000
  classDef propose fill:#fff3bf,stroke:#e67700,color:#000
  classDef afaire fill:#f8f9fa,stroke:#868e96,color:#000,stroke-dasharray:4 3
  class E,S humain
  class RAP propose
  class DET,AG,DYN,SBOM,SYN,AVIS,DIFF afaire
```

### Qui voit quoi pendant la revue par agents

Le cœur de la revue est la comparaison entre ce que le code fait et ce que le dossier déclare. Pour qu'elle prouve quelque chose, le relecteur aveugle ne doit pas voir le dossier.

```mermaid
flowchart LR
  CODE[/"Code au commit relu<br/>sans .raton/"/]
  INT[/"intention.yaml"/]
  DECL[/"technique.yaml et flux.yaml<br/>déclarés par l'auteur"/]

  AV["Relecteur aveugle<br/>plusieurs passes"]
  INF["Relecteur informé<br/>plusieurs passes"]
  J["Juge"]
  E(("Équipe<br/>de revue"))

  RECON[/"Reconstruction<br/>technique + flux"/]
  RI[/"Rapports : écarts,<br/>exclusions, failles"/]
  RJ[/"Rapport du juge<br/>accords et divergences"/]

  CODE --> AV
  CODE --> INF
  INT --> INF
  DECL --> INF
  AV --> RECON
  INF --> RI
  RECON --> J
  DECL --> J
  INT --> J
  RI --> J
  J --> RJ
  RJ -->|"divergences"| E

  classDef humain fill:#d0ebff,stroke:#1971c2,color:#000
  class E humain
```

- Le **relecteur aveugle** ne lit que le code et décrit ce que fait l'application, dans le format de la partie technique et de la matrice de flux.
- Le **relecteur informé** confronte le code à l'intention : fonctions non décrites, exclusions violées, failles.
- Le **juge** compare la reconstruction aveugle à ce que l'auteur a déclaré, et les passes entre elles. Un flux que l'aveugle a trouvé et que le dossier ne déclare pas devient un constat. Une divergence entre passes va à l'équipe de revue.

## 4. Récapitulatif des skills

| # | Skill | Qui intervient | Lit | Produit | État |
|---|---|---|---|---|---|
| 1 | Qualification | métier (répond), équipe de revue (valide) | réponses, registre RGPD | fiche de qualification : palier, contrôles obligatoires | à faire |
| 2 | DAT | métier (intention), auteur avec une IA (technique) | entretien ; code pour la partie technique | `intention.yaml`, `technique.yaml` | en place |
| 3 | Matrice de flux | auteur | intention, code | `flux.yaml`, d'où sont générées les NetworkPolicies | à faire |
| 4 | Dossier d'exploitation | auteur, exploitation | — | dossier d'exploitation | à faire |
| 5 | Palier Kubernetes | outils | Dockerfile, manifestes, qualification | rapport | à faire |
| 6 | Chaîne d'approvisionnement | outils | manifestes, lockfiles, images | SBOM, rapport | à faire |
| 7 | Secrets | outils | code, historique git | rapport | à faire |
| 8 | Identité et accès | outils, agent | code, partie technique | rapport | à faire |
| 9 | Revue par agents | agents ; l'équipe de revue tranche | code ; dossier pour l'informé et le juge | reconstruction, rapports | à faire |
| 10 | Analyse dynamique | outils, en bac à sable | application déployée, `flux.yaml` | rapport des flux observés | à faire |
| 11 | Revue différentielle | agents ; équipe de revue | avis précédent, delta entre commits | rapports, nouvel avis | à faire |
| 12 | Synthèse et avis | agent ; équipe de revue ; signataire | rapports, qualification | avis Go, Go avec réserves ou No-Go | à faire |
| 13 | Pré-contrôle | métier, seul | dossier, qualification | liste des manques | à faire |

Composants transverses :

| Composant | État |
|---|---|
| Formats intention et technique | en place |
| Format des constats (rapport, constat, corrigé) | proposé, à valider |
| Formats de la qualification, de la matrice de flux, du dossier d'exploitation et de l'avis | à faire |
| Scripts `dossier.py` et `constats.py` | en place |
| Image conteneur d'outillage (Semgrep, gitleaks, Trivy…) | à faire |
| Corpus de test | un cas : `notes-de-frais` |

## Hypothèses à confirmer

La feuille de route ne fixe pas encore ces rôles. Les diagrammes retiennent les hypothèses suivantes :

- **Équipe de revue** : le diagramme suppose qu'une même équipe (sécurité, architecture ?) lance le pipeline, tranche les divergences et présente l'avis au signataire.
- **Validation de la qualification** : faite par l'équipe de revue, pas seulement par le métier, parce que l'auteur a intérêt à sous-évaluer la sensibilité de son application pour alléger les contrôles.
- **Signataire** : RSSI, architecte ou comité, question ouverte de la feuille de route.
- **Exploitation** : reçoit l'avis signé, les NetworkPolicies et le dossier d'exploitation, puis déploie.
- **Mainteneurs de Raton** : l'équipe qui développe la bibliothèque et son corpus.
