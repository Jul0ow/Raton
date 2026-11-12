# Format de la fiche de qualification

Statut : **validé** le 2026-11-12 (format v0). L'échelle DICP pourra être revue avec la PSSI, et une section sur les interconnexions est en discussion.

La qualification est la première étape du parcours. Elle classe l'application selon le tort qu'elle pourrait causer, puis en déduit le **palier d'exigence** et la liste des **contrôles obligatoires**. Le métier répond aux questions ; l'équipe infra valide la fiche.

Le schéma fait foi : [`qualification.schema.json`](../../plugin/schemas/qualification.schema.json). Le skill [`qualification`](../../plugin/skills/qualification/SKILL.md) mène l'entretien et la validation. Le script [`qualification.py`](../../plugin/scripts/qualification.py) calcule le palier.

## Ce que le format doit permettre

- **Proportionner sans négocier.** Le palier se calcule à partir des réponses, par une règle publique et déterministe. Personne ne le choisit, ni le métier, ni une IA, ni l'équipe infra. L'équipe infra peut seulement le relever, en le justifiant.
- **Résister à la sous-évaluation.** L'auteur a intérêt à minimiser la sensibilité de son application pour alléger les contrôles. Trois parades :
  - l'équipe infra valide la fiche et la range hors de portée de l'auteur ;
  - chaque niveau porte son motif, que l'équipe infra peut discuter ;
  - le script recoupe la fiche avec l'intention attestée par le métier.
- **Poser des questions métier.** Le métier ne sait pas dire « confidentialité 3 ». Il sait en revanche dire ce qui se passe si l'application s'arrête une journée ou si ses informations circulent. Le skill pose ces questions et en déduit le niveau d'après une échelle écrite.
- **Tracer.** La fiche est versionnée, et elle dit qui l'a renseignée, qui l'a validée et quand. L'avis enregistre la version et l'empreinte de la fiche appliquée.

## Où vit la fiche

Contrairement au DAT, la fiche ne vit pas dans le dépôt de l'application, et pour deux raisons :

- l'auteur pourrait la modifier après validation, et rien ne le signalerait avant la revue ;
- elle qualifie l'application, pas un commit : elle ne change pas à chaque version.

Elle appartient à l'équipe infra, qui la range dans un dépôt qu'elle tient, avec un répertoire par application :

```
<dépôt de l'équipe infra>/
  notes-de-frais/
    qualification.yaml
```

Ce répertoire pourra aussi recevoir les avis et le registre des décisions, dont les formats restent à définir.

La fiche arrive à l'équipe infra par l'un de deux circuits, selon que le métier connaît GitLab ou non :

| Circuit | Pour qui | Déroulé |
|---|---|---|
| Demande de fusion | un métier qui utilise GitLab | il propose la fiche dans le dépôt de l'équipe infra ; l'équipe infra la relit, la corrige au besoin, la valide et la fusionne |
| Ticket | un métier qui ne connaît pas GitLab | il ouvre un ticket auprès de l'équipe infra, avec la fiche en pièce jointe et son rendu lisible dans le corps du ticket ; l'équipe infra la relit, la valide, la dépose elle-même dans son dépôt et clôt le ticket |

Dans les deux cas, seule l'équipe infra fait entrer la fiche dans son dépôt. Ensuite :

- le pipeline reçoit le chemin de la fiche validée ;
- l'auteur en reçoit une copie pour le pré-contrôle (skill 13).

Dans le corpus, la fiche est rangée à côté de `depot/`, et non dedans, pour la même raison.

## Contenu

| Section | Contenu | Rempli par |
|---|---|---|
| `application` | code (identifiant stable, nom du répertoire), nom, objet, porteur, dépôt | métier |
| `exposition` | `interne` ou `externe` | métier |
| `utilisateurs` | populations (`interne`, `externe`, `public`), effectif | métier |
| `donnees_personnelles` | niveau (`non`, `oui`, `sensibles`), personnes concernées, volume | métier |
| `dicp` | pour chacun des quatre axes : un niveau de 1 à 4 et son motif | métier, sur les questions du skill |
| `exigences` | palier retenu, contrôles obligatoires, justification s'ils dépassent le minimum | script ; l'équipe infra peut relever |
| `validation` | version, personne qui a renseigné la fiche, personne qui l'a validée, date | équipe infra |

Définitions :

- **Exposition `externe`** : l'application est joignable depuis un réseau que l'entreprise ne maîtrise pas. C'est le cas d'Internet, mais aussi du réseau d'interconnexion avec un partenaire ou d'un extranet. Un tel réseau est traité comme peu fiable, même derrière une authentification et quel que soit le lien contractuel avec le partenaire. Une application joignable seulement depuis le réseau de l'entreprise, VPN compris, est `interne`.
- **Utilisateurs** :
  - `interne` : les salariés ;
  - `externe` : des personnes extérieures identifiées, avec un compte nominatif (clients, fournisseurs, partenaires) ;
  - `public` : n'importe qui, sans compte nominatif, ce qui suppose une exposition externe.
- **Données personnelles** :
  - `non` : aucune, en dehors de l'identité des utilisateurs fournie par l'authentification. Toute application sait qui est connecté ; ce cas commun ne pèse pas sur le palier.
  - `oui` : des informations sur des personnes.
  - `sensibles` : des catégories particulières au sens de l'article 9 du RGPD (santé, opinions, appartenance syndicale, origine, convictions religieuses, vie sexuelle, données biométriques ou génétiques), ou des infractions et condamnations (article 10).

  L'échelle est celle du champ `personnelles` de l'intention, ce qui permet le recoupement.

La feuille de route cite la **criticité métier** parmi les critères. Ce n'est pas un critère à part : c'est ce que mesurent la disponibilité et l'intégrité, à travers l'impact d'un arrêt ou d'une erreur sur l'activité. Un critère séparé ferait répondre deux fois à la même question, avec le risque d'obtenir deux réponses différentes.

## Échelle DICP

Chaque axe a quatre niveaux. Le skill pose une question, le métier répond avec ses mots, et le niveau découle de l'échelle. En cas d'hésitation entre deux niveaux, on retient le plus élevé, et l'équipe infra tranche.

| Niveau | Disponibilité : un arrêt est supportable… | Intégrité : une erreur ou une modification indue a des conséquences… | Confidentialité : les informations sont… | Preuve : savoir qui a fait quoi, et quand, est… |
|---|---|---|---|---|
| 1 | plusieurs jours | négligeables : elle se voit et se corrige sans dommage | publiques | inutile |
| 2 | une journée au plus | limitées : gêne, reprise manuelle | à usage interne : leur diffusion hors de l'entreprise gênerait | utile au diagnostic |
| 3 | quelques heures au plus | importantes : perte financière, non-conformité, décision erronée sur une personne | confidentielles : réservées à certaines personnes, avec un préjudice si elles circulent | exigé pour un contrôle : audit interne, commissaire aux comptes, contrôle fiscal |
| 4 | moins d'une heure | graves : sécurité des personnes, perte majeure, mise en cause pénale | secrètes : leur divulgation causerait un préjudice grave | exigé avec valeur probante : opposable en justice |

C'est une échelle par défaut. Elle est à aligner sur celle de la PSSI de l'entreprise : c'est une question ouverte.

## Calcul du palier

On regarde le palier atteint par chaque critère et on retient le plus élevé. Si l'application a une exposition externe, on monte d'un palier, sans dépasser 3.

| Critère | Palier 1 | Palier 2 | Palier 3 |
|---|---|---|---|
| Utilisateurs | salariés seulement | personnes extérieures identifiées | public sans compte |
| Données personnelles | aucune, hors identité des utilisateurs | oui | sensibles |
| Chacun des quatre axes DICP | niveau 1 ou 2 | niveau 3 | niveau 4 |

Contrôles obligatoires selon le palier :

| Contrôles | 1 · socle | 2 · renforcé | 3 · élevé |
|---|:-:|:-:|:-:|
| Dossier : cohérence du DAT, matrice de flux, dossier d'exploitation | ✓ | ✓ | ✓ |
| Contrôles déterministes : palier Kubernetes, chaîne d'approvisionnement, secrets, identité et accès, SAST | ✓ | ✓ | ✓ |
| Revue informée en plusieurs passes, juge | ✓ | ✓ | ✓ |
| Revue aveugle | | ✓ | ✓ |
| Analyse dynamique en bac à sable | | | ✓ |

Pourquoi cette répartition :

- **Le socle couvre déjà le modèle de menace principal** : données envoyées à un tiers, SDK de télémétrie, dépendance compromise. Les outils déterministes coûtent peu, la revue informée confronte le code à l'intention, et la matrice de flux bloque en production tout flux non déclaré.
- **La revue aveugle s'ajoute au palier 2** : dès que l'application traite des données personnelles, sert des utilisateurs extérieurs, a une exposition externe ou a un besoin DICP de niveau 3. Le relecteur informé lit le dossier et risque d'y être ancré ; l'aveugle, qui ne le voit pas, trouve ce que le dossier tait.
- **L'analyse dynamique, la plus coûteuse, est réservée au palier 3.** Elle concerne une application ouverte au public, traitant des données sensibles, ayant un besoin de niveau 4, ou ayant une exposition externe alors qu'elle relève déjà du palier 2.

Le dossier (DAT, matrice de flux, dossier d'exploitation) est exigé à tous les paliers, comme le prévoit le [format du DAT](dat.md#proportionnalité). La revue différentielle ne dépend pas du palier : toute nouvelle version y passe.

Le palier sert aussi à d'autres skills :

- le palier Kubernetes exigé (skill 5) est le palier retenu ;
- le nombre de passes des relecteurs (skill 9) et le niveau de détail du dossier d'exploitation (skill 4) seront fixés avec ces skills.

L'équipe infra peut relever le palier ou ajouter un contrôle, par exemple une analyse dynamique pour une application de palier 2 qui embarque un SDK inconnu. La fiche porte alors une justification.

Elle ne peut pas descendre sous le minimum. Si la règle lui paraît inadaptée, c'est la règle qu'il faut changer, pour toutes les applications.

## Exemple

La fiche de l'application [`notes-de-frais`](../../corpus/notes-de-frais/) du corpus :

```yaml
format: raton/qualification/v0

application:
  code: notes-de-frais
  nom: Notes de frais
  objet: >
    Les salariés déposent leurs notes de frais et leurs justificatifs,
    leur manager les valide, puis la comptabilité exporte les notes validées.
  porteur: { nom: Marie Durand, entite: Direction financière }
  depot: https://git.example.com/finance/notes-de-frais

exposition: interne

utilisateurs:
  populations: [interne]
  effectif: 2000

donnees_personnelles:
  niveau: oui
  personnes: [salariés]
  volume: 2000

dicp:
  disponibilite:
    niveau: 2
    motif: un arrêt d'une journée retarde les remboursements, sans autre conséquence
  integrite:
    niveau: 3
    motif: les montants validés sont remboursés aux salariés et exportés en comptabilité
  confidentialite:
    niveau: 3
    motif: dépenses et justificatifs réservés au salarié, à son manager et à la comptabilité
  preuve:
    niveau: 3
    motif: savoir qui a validé chaque note, pour les contrôles comptables et fiscaux

exigences:
  palier: 2
  controles:
    - dat
    - matrice_flux
    - exploitation
    - palier_kubernetes
    - chaine_approvisionnement
    - secrets
    - identite_acces
    - sast
    - revue_informee
    - juge
    - revue_aveugle

validation:
  version: 1
  renseigne_par: { nom: Marie Durand, entite: Direction financière }
  valide_par: { nom: Paul Lefèvre, entite: Équipe infra }
  date: 2026-11-09
```

Le palier se calcule ainsi :

- aucun critère n'atteint le palier 3 ;
- les données personnelles et trois axes DICP donnent le palier 2 ;
- l'exposition est interne, donc rien ne s'ajoute.

Elle passe donc la revue aveugle mais pas l'analyse dynamique. Son piège, un SDK qui envoie des données à un service externe, reste à portée de la revue informée, de la revue aveugle et du juge, et l'egress généré depuis la matrice de flux le bloquerait en production.

## Recoupements avec l'intention

L'intention est rédigée après la qualification, et elle est attestée par le métier. Le script recoupe les deux documents, car la fiche ne peut pas être en deçà de ce que déclare l'intention :

- un profil `externe` dans l'intention exige des utilisateurs `externe` ou `public` dans la fiche ;
- aucune donnée de l'intention ne peut être plus personnelle que le niveau de la fiche : une donnée `sensibles` exige une fiche `sensibles`.

Chaque écart est une erreur. Pour le résoudre, il faut soit requalifier l'application (nouvelle version de la fiche, validée par l'équipe infra), soit corriger l'intention. Le pré-contrôle et le pipeline refont ce recoupement à chaque soumission : une intention qui s'enrichit d'un profil ou d'une donnée déclenche donc la requalification.

Le script signale aussi, sans bloquer, les points qui méritent une question de l'équipe infra :

- une confidentialité de niveau 1 alors que l'application traite des données personnelles ;
- une confidentialité inférieure à 3 alors qu'elle traite des données sensibles ;
- des données sensibles, pour lesquelles il faut vérifier avec le DPO si une analyse d'impact (AIPD) est requise.

## Validation

Une fiche validée respecte, en plus du schéma, ces règles :

- les exigences ne sont pas en deçà du minimum calculé, et une justification accompagne tout dépassement ;
- la personne qui valide n'est ni celle qui a renseigné la fiche, ni le porteur métier.

Le script ne compare que les noms : il n'écarte que le cas évident. La vraie garantie vient du circuit, puisque seule l'équipe infra fait entrer une fiche dans son dépôt.

Sans section `validation`, la fiche est un brouillon. Le schéma n'accepte de validation que si la fiche contient ses exigences.

## Outillage

[`plugin/scripts/qualification.py`](../../plugin/scripts/qualification.py), déterministe et en lecture seule :

```bash
python3 plugin/scripts/qualification.py valider qualification.yaml [--intention .raton/intention.yaml]
python3 plugin/scripts/qualification.py calculer qualification.yaml
python3 plugin/scripts/qualification.py rendre qualification.yaml
```

- `calculer` affiche le palier atteint par chaque critère, puis le palier calculé et le bloc `exigences` minimal.
- `rendre` produit le rendu lisible que le métier relit et que l'équipe infra valide. Ce rendu montre le palier de chaque critère : la règle se lit sur la fiche.

## Reporté

- **Politique propre à l'entreprise.** La règle de calcul et l'échelle sont pour l'instant écrites dans `qualification.py`. Quand la question de la diffusion sera tranchée, elles passeront dans un fichier que l'entreprise ajustera sans toucher au code, et la fiche indiquera quelle version de la règle l'a calculée.
- **Durée de validité.** Faut-il requalifier périodiquement, en plus des recoupements avec l'intention ? À voir avec l'usage.
- **Registre RGPD.** Écarté pour l'instant : l'entreprise traite très peu de données personnelles. Le niveau de données personnelles reste un critère du palier ; le lien avec le registre pourra revenir si le besoin apparaît.
- **Changement de fiche et avis.** Un avis vaut pour une version de la fiche. Si le palier monte, les contrôles ajoutés n'ont pas été faits et il faut une nouvelle revue. Ce point sera traité avec la synthèse et la revue différentielle.

## Décisions

Validées le 2026-11-12 :

1. La fiche vit hors du dépôt de l'application, dans un dépôt tenu par l'équipe infra.
2. La criticité métier est portée par les axes D et I du DICP, sans critère séparé.
3. Une échelle DICP par défaut à quatre niveaux, qui pourra être revue avec la PSSI.
4. L'identité des utilisateurs fournie par l'authentification ne compte pas comme donnée personnelle pour le palier.
5. Trois paliers : on retient le critère le plus élevé, plus un palier pour une exposition externe. L'équipe infra peut relever le palier, jamais l'abaisser.
6. La répartition des contrôles : un socle, puis la revue aveugle au palier 2, puis l'analyse dynamique au palier 3.
7. Des recoupements avec l'intention qui bloquent quand la fiche sous-évalue.

Demandés à la même relecture :

- deux circuits pour transmettre la fiche, la demande de fusion ou le ticket, pour les métiers qui ne connaissent pas GitLab ;
- une exposition `externe` plutôt que `internet` : tout réseau que l'entreprise ne maîtrise pas est peu fiable, interconnexions avec les partenaires comprises ;
- le registre RGPD écarté pour l'instant.
