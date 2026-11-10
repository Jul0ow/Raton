# Format des constats

Statut : **proposition à valider** (2026-11-10).

Chaque contrôle (outil, agent ou humain) produit un **rapport** : sur quel commit il a porté, ce qu'il a vérifié et ce qu'il n'a pas vérifié, et ses **constats**. La synthèse agrège les rapports pour rédiger l'avis ; le juge compare ceux de plusieurs passes ; le corpus de test mesure ce qu'ils détectent.

Les schémas font foi : [`rapport.schema.json`](../../plugin/schemas/rapport.schema.json), [`constat.schema.json`](../../plugin/schemas/constat.schema.json) et [`attendu.schema.json`](../../plugin/schemas/attendu.schema.json). Le guide destiné aux producteurs, avec les définitions des catégories, de la sévérité et de la confiance, est [`plugin/references/constats.md`](../../plugin/references/constats.md).

## Ce que le format doit permettre

- **Prouver plutôt qu'affirmer.** Un LLM peut inventer un constat ou citer une ligne qui n'existe pas. Chaque constat porte donc des preuves typées, et celles qui peuvent l'être sont vérifiées mécaniquement contre le dépôt. Un constat réfuté est traité comme une invention.
- **Comparer mécaniquement.** Une liste fermée de catégories et des preuves localisées permettent d'apparier deux constats sans comparer de prose : entre passes, entre revue aveugle et revue informée, entre un rapport et le corrigé du corpus.
- **Dire les limites.** Chaque rapport déclare son périmètre, vérifié et non vérifié. Un rapport sans constat ne vaut que par ce périmètre, et l'avis en hérite.
- **Ne pas propager les secrets.** Un rapport circule plus largement que le dépôt : la valeur d'un secret y est toujours masquée.
- **Rester une donnée.** Les extraits cités viennent de l'auteur et les descriptions d'un producteur qui a pu être manipulé. Les agents qui lisent un rapport le traitent comme une donnée. En cas de doute, la preuve fait foi, pas la description.

## Rapport

| Champ | Contenu |
|---|---|
| `controle` | le contrôle exécuté : `secrets`, `sast`, `palier_kubernetes`, `revue_aveugle`, `juge`, `analyse_dynamique`… (liste fermée, calquée sur le catalogue) |
| `producteur` | `outil` (nom et version obligatoires), `agent` (modèle et numéro de passe obligatoires) ou `humain` |
| `commit` | SHA complet relu |
| `date` | date et heure d'exécution |
| `perimetre` | `verifie` : ce qui a été couvert ; `non_verifie` : ce qui ne l'a pas été, avec le motif |
| `constats` | la liste, éventuellement vide |

Un rapport par exécution : deux passes d'un même agent font deux rapports, que le juge compare.

## Constat

| Champ | Contenu |
|---|---|
| `id` | unique dans le rapport |
| `categorie` | l'une des 23 catégories du [guide](../../plugin/references/constats.md#catégories) |
| `severite` | `critique`, `haute`, `moyenne`, `basse`, `info` |
| `confiance` | `elevee`, `moyenne`, `faible` |
| `titre`, `description` | les mots du producteur, bornés à 200 et 2000 caractères |
| `regle`, `cwe` | facultatifs : règle de l'outil ou CVE, classe de faiblesse |
| `preuves` | au moins une, de type `code`, `historique`, `dossier`, `dependance`, `reseau` ou `absence` |

La catégorie dit **quoi**, `regle` et `cwe` disent **précisément quoi**. Une liste courte et fermée garde la comparaison possible ; le détail reste disponible sans multiplier les catégories.

La sévérité est celle qu'estime le producteur, dans le contexte de l'application. Le passage de la sévérité à l'avis (Go, Go avec réserves, No-Go) relève de la synthèse.

## Vérification des preuves

`constats.py verifier RAPPORT --depot DEPOT` reprend chaque preuve vérifiable :

- `code` : le fichier existe dans le dépôt, les lignes aussi, et l'extrait figure dans ces lignes, aux espaces près. `***` y vaut n'importe quelle valeur masquée ;
- `dossier` : l'élément (`X01`) ou la section (`services_tiers`) existe dans le fichier du `.raton/` cité ;
- `dependance` : le paquet figure à la ligne citée du manifeste.

Chaque constat en sort `verifie`, `refute` (une preuve est fausse) ou `non_verifiable` (aucune preuve vérifiable, par exemple un flux réseau observé). Le script vérifie aussi que le dépôt est bien au commit du rapport : il lit `.git` directement, sans lancer `git` sur un dépôt non fiable. Il ne sort jamais du dépôt, liens symboliques compris, et n'affiche jamais le contenu des fichiers lus.

`constats.py valider` ajoute au schéma quelques règles : identifiants uniques, plages de lignes cohérentes et bornées, extraits assez longs pour être probants, secret masqué dans tout constat `secret_expose`.

## Corrigés du corpus

Un corrigé (`attendu.yaml`) liste les constats attendus d'un cas, au même format, avec en plus `detecte_par` : les contrôles censés trouver chacun d'eux.

`constats.py comparer ATTENDU RAPPORT…` apparie les constats obtenus aux constats attendus. Un constat attendu est **détecté** si un constat obtenu a la même catégorie et au moins une preuve qui correspond :

- `code` et `historique` : même fichier, plages de lignes qui se chevauchent à 3 lignes près ;
- `dossier` : même fichier et même élément quand les deux en citent un ;
- `dependance` : même écosystème et même paquet ;
- `reseau` : même destination, `*.` en tête acceptant tout sous-domaine ;
- `absence` : même élément manquant.

Un constat attendu que les contrôles des rapports ne sont pas censés trouver est **hors périmètre**, pas manqué. Un constat obtenu sans correspondance est **supplémentaire** : faux positif ou constat réel que le corrigé ne prévoyait pas, à trancher par un humain. Quand un constat manqué a été trouvé au même endroit sous une autre catégorie, la comparaison le signale.

## Exemple

Rapport d'une revue informée sur le cas [`notes-de-frais`](../../corpus/notes-de-frais/) :

```yaml
format: raton/rapport/v0
controle: revue_informee
producteur: { type: agent, nom: relecteur-informe, modele: exemple, passe: 1 }
commit: 4e3d3e49bc553b5ff0d6f7203f4791cf783997fb
date: 2026-11-10T10:00:00Z

perimetre:
  verifie:
    - code Python de app/ confronté à l'intention et à la partie technique
    - dépendances déclarées dans requirements.txt
  non_verifie:
    - { element: comportement à l'exécution, motif: revue statique }
    - { element: code des dépendances, motif: hors du périmètre de la revue par agents }

constats:
  - id: R01
    categorie: flux_non_declare
    severite: haute
    confiance: elevee
    titre: Envoi des erreurs et des traces à Sentry, service non déclaré
    description: >
      Le SDK Sentry est initialisé au démarrage avec un DSN pointant vers
      ingest.de.sentry.io. Aucun échange de l'intention ne couvre ce service.
    preuves:
      - type: code
        fichier: app/main.py
        lignes: [16, 20]
        extrait: |
          sentry_sdk.init(
              dsn="https://***@o4508261749303296.ingest.de.sentry.io/4508261752711248",
      - { type: dependance, ecosysteme: pypi, paquet: sentry-sdk, version: 2.74.0, fichier: requirements.txt, ligne: 9 }

  - id: R02
    categorie: exclusion_violee
    severite: haute
    confiance: elevee
    titre: L'envoi vers Sentry contredit l'exclusion X01
    description: X01 exclut toute sortie de données hors de l'entreprise, sauf vers le service d'IA.
    preuves:
      - { type: dossier, fichier: .raton/intention.yaml, element: X01 }
      - { type: code, fichier: app/main.py, lignes: [16, 16], extrait: "sentry_sdk.init(" }

  - id: R03
    categorie: exploitabilite
    severite: info
    confiance: elevee
    titre: Schéma de base créé au démarrage, sans migrations
    description: Les évolutions du schéma ne seront pas appliquées aux bases existantes.
    preuves:
      - { type: code, fichier: app/main.py, lignes: [28, 28], extrait: Base.metadata.create_all(engine) }
```

La clé publique du DSN est masquée par `***` : ce n'est pas obligatoire hors `secret_expose`, mais ce n'est jamais gênant. Comparé au corrigé, ce rapport détecte A01 et A03. Il manque A02, la transmission de données personnelles : R01 et R02 citent bien le même endroit, mais sous d'autres catégories, ce que la comparaison signale. A04, attendu du juge, est hors de son périmètre. R03 est en plus : un constat réel que le corrigé ne prévoyait pas.

```
✓ A01 détecté par revue_informee:R01
✓ A03 détecté par revue_informee:R02
✗ A02 manqué ; même emplacement, autre catégorie : revue_informee:R01 (flux_non_declare), revue_informee:R02 (exclusion_violee)
· A04 hors du périmètre de ces contrôles
+ revue_informee:R03 (exploitabilite, info) : non attendu (faux positif ou constat réel non prévu)
2/3 constats attendus détectés
```

## Reporté

- **Empreinte stable et décisions humaines.** Pour reporter d'une version à l'autre la décision prise sur un constat (accepté, corrigé, écarté), il faudra une empreinte indépendante des numéros de ligne et un registre des décisions séparé des rapports, qui restent des preuves brutes. À traiter avec la synthèse et la revue différentielle ; le format des rapports n'a pas à changer pour cela.
- **Import SARIF.** Semgrep, CodeQL, gitleaks, Trivy, Checkov et kubescape savent produire du SARIF. Un adaptateur le convertira en rapport Raton lors de la mise en place de l'outillage ; le format Raton reste le pivot, parce que SARIF ne porte ni périmètre, ni preuves de dossier, ni flux observés.
- **Sortie du juge.** Le rapport consolidé du juge (accord entre passes, divergences escaladées) sera défini avec le skill 9.

## Décisions à valider

1. Un format pivot propre à Raton, alimenté par SARIF pour les outils, plutôt que SARIF partout.
2. Un rapport par exécution de contrôle, avec un périmètre vérifié et non vérifié obligatoire.
3. Une liste fermée de 23 catégories, le détail étant porté par `regle` et `cwe`.
4. Cinq niveaux de sévérité et trois niveaux de confiance, définis dans le guide.
5. Des preuves typées, vérifiées mécaniquement quand c'est possible, et la valeur des secrets toujours masquée.
6. La règle d'appariement ci-dessus pour mesurer le corpus.
