# Format de la note de l'application

Statut : **validé** le 2026-11-17 (format v0), à la demande de l'équipe : voir les [décisions](#décisions).

À la fin de la revue, l'application reçoit une **note** : un total sur 100 et une lettre de A à E. Elle dit au porteur métier ce qu'il lui reste à améliorer et ce que chaque correction lui rapporte, pour lui donner envie de la faire monter d'une version à l'autre.

Le schéma fait foi : [`note.schema.json`](../../plugin/schemas/note.schema.json). Le script [`note.py`](../../plugin/scripts/note.py) calcule la note à partir de la fiche de qualification et des rapports de contrôle d'un commit.

## Ce que la note doit permettre

- **Motiver sans négocier.** Comme le palier, la note se calcule par une règle publique et déterministe. Personne ne la choisit : ni le métier, ni une IA, ni l'équipe DevOps. Une note discutée au cas par cas ne motiverait personne.
- **Dire comment monter.** Chaque constat a un coût connu d'avance, et la note liste les corrections qui font gagner une lettre. Le métier sait par où commencer.
- **Récompenser l'honnêteté.** Déclarer coûte moins cher que cacher. Un service tiers déclaré dans l'intention, la fiche et la matrice de flux ne coûte rien à la note : son risque est traité par la qualification et par l'avis. Le même service, trouvé par la revue, coûte un constat haut, qui plafonne la note à C.
- **Ne pas décider à la place de l'avis.** Une bonne note n'autorise rien. La mise en production dépend de l'avis, signé par le change manager.
- **Dire ses limites.** La note est provisoire tant qu'un contrôle obligatoire n'a pas tourné, et elle le dit.

## Quand et par qui

La note se calcule à la synthèse (skill 12), à chaque revue, revue différentielle comprise : chaque commit soumis reçoit sa note, à côté de son avis.

- L'équipe DevOps la calcule après avoir tranché les divergences entre passes et entre relecteurs, et la transmet au métier avec les constats à corriger.
- Elle est rangée avec l'avis dans le dépôt de l'équipe DevOps. Le change manager et le RSSI y ont accès, comme au reste du dossier.
- Un refus du change manager ne change pas la note, qui se calcule sur les rapports. Le métier reçoit les motifs du refus avec les constats à corriger ; la version corrigée repasse la revue différentielle, qui vérifie que chaque motif est traité, et reçoit une nouvelle note. Un motif resté sans réponse devient un constat de cette revue, et compte.
- Les constats que l'équipe DevOps écarte (faux positifs) ne comptent pas. Tant que le registre des décisions n'existe pas (voir le [format des constats](constats.md#reporté)), le script compte tous les constats des rapports qu'on lui donne : l'équipe DevOps ne lui passe que les rapports retenus.

## Calcul

### Cinq axes de 20 points

Chaque catégorie de constat retire des points à un axe, et un seul :

| Axe | Ce qu'il dit au métier | Catégories |
|---|---|---|
| Dossier fidèle | le DAT, la matrice de flux et le dossier d'exploitation décrivent l'application telle qu'elle est | `dossier_inexact`, `dossier_incomplet`, `declaration_non_realisee` |
| Conforme à l'intention | l'application ne fait que ce que le métier a déclaré | `flux_non_declare`, `donnees_non_declarees`, `fonction_non_decrite`, `exclusion_violee` |
| Code sûr | ni faille, ni secret, ni code suspect | `vulnerabilite`, `controle_acces`, `secret_expose`, `code_malveillant`, `obfuscation`, `declencheur_conditionnel`, `injection_relecteurs`, `autre` |
| Dépendances saines | des dépendances connues, à jour, épinglées | `dependance_vulnerable`, `dependance_suspecte`, `script_installation`, `version_non_epinglee`, `licence` |
| Prête pour la production | déployable, exploitable, conforme aux standards du SI | `deploiement`, `exploitabilite`, `non_conformite_si` |

Les axes pèsent autant les uns que les autres. Ils regroupent les 23 catégories en cinq questions que le métier comprend, et lui montrent où se trouvent ses points perdus.

### Coût d'un constat

| Sévérité | Coût |
|---|---|
| critique | 20 points : l'axe entier |
| haute | 10 points |
| moyenne | 5 points |
| basse | 2 points |
| info | rien |

Un axe ne descend pas sous zéro : vingt dépendances vulnérables ne font pas perdre de points aux autres axes. Le total est la somme des cinq axes.

Ne comptent pas :

- les constats `info`, qui ne sont pas des défauts ;
- les constats de confiance `faible` : ce sont des soupçons à confirmer. Un humain qui confirme le soupçon relève sa confiance, et le constat compte alors.

Un même problème trouvé par plusieurs rapports (plusieurs contrôles ou plusieurs passes) ne compte qu'une fois, à sa sévérité la plus haute. La règle est celle de la [mesure sur le corpus](constats.md#corrigés-du-corpus--mesurer-raton) : même catégorie et au moins une preuve qui correspond. Deux constats d'un même rapport ne sont jamais fusionnés, puisque leur producteur les a distingués. Sans cette règle, le métier paierait plusieurs fois le même défaut, simplement parce que plusieurs contrôles l'ont vu.

### Lettre

| Lettre | Total | Plafond |
|---|---|---|
| A | 90 et plus | |
| B | de 75 à 89 | |
| C | de 60 à 74 | au mieux C avec un constat haut |
| D | de 40 à 59 | |
| E | moins de 40 | toujours E avec un constat critique |

Les plafonds empêchent un bon total de masquer un défaut grave. Une application qui envoie des données à un service non déclaré ne peut pas avoir A, même si tout le reste est parfait : le [guide des constats](../../plugin/references/constats.md#sévérité) dit d'un constat haut qu'il est « à corriger avant la mise en production ».

### Note provisoire

La fiche de qualification dit quels contrôles sont obligatoires. Tant que l'un d'eux n'a pas de rapport, la note est **provisoire** et le rendu les nomme : ce qu'ils trouveront peut la faire baisser. La note ne les compte pas comme des échecs, car le métier n'y peut rien : c'est l'équipe DevOps qui lance les contrôles.

### Points à gagner

Le rendu liste les constats à corriger pour gagner au moins une lettre : on retire les plus graves d'abord, jusqu'à ce que la lettre monte. Corriger un constat, c'est corriger le code, ou faire évoluer le dossier en connaissance de cause : déclarer un service dans l'intention, ce qui repasse par la validation de l'intention et, si besoin, par une requalification. Dans les deux cas, le constat disparaît de la revue suivante et ses points reviennent.

## Exemple

Le rapport de revue informée donné en exemple dans le [format des constats](constats.md#exemple), sur le cas [`notes-de-frais`](../../corpus/notes-de-frais/), avec sa fiche de qualification :

```bash
python3 plugin/scripts/note.py noter corpus/notes-de-frais/qualification.yaml rapport.yaml
```

```markdown
# Notes de frais : note C (provisoire)

**80/100** · palier 3 · commit `4e3d3e49bc55`

> La note mesure ce qu'il reste à améliorer d'après les contrôles. Elle ne décide pas de la mise en production : c'est l'avis, signé par le change manager.
>
> **Provisoire** : 11 contrôle(s) obligatoire(s) sans rapport (dat, matrice_flux, exploitation, palier_kubernetes, chaine_approvisionnement, secrets, identite_acces, sast, juge, revue_aveugle, analyse_dynamique). Ce qu'ils trouveront peut faire baisser la note.

| Axe | Points | Constats comptés |
|---|---|---|
| Dossier fidèle | 20/20 | aucun |
| Conforme à l'intention | 0/20 | 2 hauts |
| Code sûr | 20/20 | aucun |
| Dépendances saines | 20/20 | aucun |
| Prête pour la production | 20/20 | aucun |

Au moins un constat haut : la note ne peut pas dépasser C, quel que soit le total.

## Pour gagner des points

Corriger ces 2 constats fait passer la note de C à A (100/100) :

- **revue_informee#1:R01** (haut, Conforme à l'intention) : Envoi des erreurs et des traces à Sentry, service non déclaré
- **revue_informee#1:R02** (haut, Conforme à l'intention) : L'envoi vers Sentry contredit l'exclusion X01

## Constats comptés

Un constat corrigé rend ses points à la version suivante. Un même problème trouvé par plusieurs contrôles ne compte qu'une fois.

| Constat | Axe | Sévérité | Coût | Trouvé aussi par |
|---|---|---|---|---|
| revue_informee#1:R01 : Envoi des erreurs et des traces à Sentry, service non déclaré | Conforme à l'intention | haute | −10 | — |
| revue_informee#1:R02 : L'envoi vers Sentry contredit l'exclusion X01 | Conforme à l'intention | haute | −10 | — |

## Non comptés

- revue_informee#1:R03 : Schéma de base créé au démarrage, sans migrations (information, sans coût)
```

Les deux constats hauts vident l'axe « Conforme à l'intention » : 80 points sur 100, ce qui vaudrait B, mais le plafond ramène la note à C. Le constat `info` ne coûte rien. Retirer le SDK Sentry, ou le déclarer en connaissance de cause, rend les 20 points et lève le plafond.

Si tous les contrôles avaient tourné et trouvé tout le [corrigé du cas](../../corpus/notes-de-frais/attendu.yaml), la note serait de 75, donc C : trois constats hauts sur l'intention, le même SDK vu par la revue informée, le juge et l'analyse dynamique ne comptant qu'une fois, et un constat moyen sur le dossier, la partie technique qui omet le SDK. Les mêmes corrections la feraient passer à A.

## Ce que la note n'est pas

- **Pas l'avis.** L'avis tient compte de ce que la note ignore : le contexte, les réserves, les contrôles qui n'ont pas tourné. Le change manager peut refuser une application bien notée, et en accepter une moins bien notée avec des réserves.
- **Pas une mesure du risque de l'application.** Une application qui écrit dans la paie a plus d'enjeux qu'une autre ; cela relève de la qualification, qui fixe le palier. La note mesure ce qu'il reste à corriger, à palier donné.
- **Pas un classement entre applications.** Deux applications de paliers différents ne passent pas les mêmes contrôles : celle du palier 3 a plus de chances de recevoir des constats. La note compare une application à elle-même, d'une version à l'autre ; le rendu affiche le palier à côté de la note pour le rappeler.

## Contournements

Une note que l'on veut faire monter, on peut aussi chercher à la tromper. Les parades :

- **Le métier ne retire pas un constat.** Il corrige, ou l'équipe DevOps écarte le constat comme faux positif. Contester ne rapporte rien.
- **Cacher coûte plus cher que déclarer.** Un flux omis du dossier et trouvé par la revue coûte un constat haut et un dossier inexact ; déclaré, il ne coûte rien. Et la matrice de flux le bloque en production de toute façon.
- **Sous-qualifier pour subir moins de contrôles** ne marche pas mieux qu'avant : la fiche est validée par l'équipe DevOps, et le palier s'affiche à côté de la note.

## Reporté

- **Progression d'une version à l'autre.** Montrer « C → B » est sans doute ce qui motive le plus. Il faut pour cela conserver les notes successives : à faire avec le format de l'avis et la revue différentielle. Le document produit par `note.py noter --json` est prévu pour être rangé avec l'avis.
- **Écarts du dossier.** Les écarts de `dossier.py ecarts` et de `flux.py ecarts` entreront dans la note quand les contrôles `dat` et `matrice_flux` produiront des rapports.
- **Constats écartés.** Avec le registre des décisions.

## Décisions

Validées le 2026-11-17 :

1. Une lettre de A à E, en plus du total sur 100.
2. Cinq axes de poids égaux, et des coûts par sévérité de 20, 10, 5, 2 et 0 points.
3. Les plafonds : C au mieux avec un constat haut, E avec un constat critique.
4. Les soupçons (confiance faible) ne comptent pas tant qu'un humain ne les a pas confirmés.
5. La note est vue par le métier, l'équipe DevOps, le change manager et le RSSI. Un catalogue des applications, qui les décrirait et afficherait leur note, serait utile, mais c'est un projet à part (voir la [feuille de route](../feuille-de-route.md#hors-du-périmètre)). Le document `raton/note/v0` est prévu pour l'alimenter ; le catalogue devra afficher le palier à côté de la note, pour ne pas comparer des applications qui ne passent pas les mêmes contrôles.

## Outillage

[`plugin/scripts/note.py`](../../plugin/scripts/note.py), déterministe et en lecture seule :

```bash
python3 plugin/scripts/note.py noter <fiche validée> <rapport>…          # rendu Markdown pour le métier
python3 plugin/scripts/note.py noter <fiche validée> <rapport>… --json   # document raton/note/v0
```

Le script refuse une fiche non validée et des rapports portant sur des commits différents : une note porte sur un commit.
