# Raton

Bibliothèque de skills Claude Code pour relire du code non fiable avant sa mise en production : vérifier qu'une application est inoffensive, qu'elle fait ce que déclare sa documentation et qu'elle est déployable dans le SI (Kubernetes), puis produire un avis argumenté que l'entreprise peut signer.

Projet en démarrage : voir la [feuille de route](docs/feuille-de-route.md) et l'[architecture](docs/architecture.md), qui schématise l'enchaînement des skills, les données qu'ils produisent et le rôle de chaque partie prenante.

## Contenu

| Chemin | Rôle |
|---|---|
| `plugin/` | le plugin Claude Code `raton` : skills, schémas, scripts |
| `plugin/skills/qualification/` | skill de qualification : entretien avec le métier, validation par l'équipe infra |
| `plugin/skills/dat/` | skill de co-rédaction du DAT |
| `plugin/skills/matrice-flux/` | skill de rédaction de la matrice de flux |
| `plugin/schemas/` | schémas communs : qualification, intention, technique, matrice de flux, plateforme, rapport de contrôle, constat, corrigé du corpus |
| `plugin/scripts/qualification.py` | validation de la fiche de qualification, calcul du palier et des contrôles obligatoires, rendu lisible |
| `plugin/scripts/dossier.py` | validation, rendu lisible et écarts du dossier `.raton/` |
| `plugin/scripts/flux.py` | validation et rendu de la matrice de flux, écarts avec le dossier et la fiche, génération des politiques réseau |
| `plugin/scripts/constats.py` | validation des rapports, vérification des preuves dans le dépôt ; mesure de Raton sur le corpus (comparaison avec un corrigé) |
| `plugin/references/` | guides partagés par les skills, dont la rédaction des constats |
| `corpus/` | applications piégées et leurs corrigés, pour mesurer ce que Raton détecte ; jamais utilisé pour relire une vraie application. `corpus/plateforme.yaml` sert d'exemple de fichier de plateforme |
| `docs/` | feuille de route, [architecture](docs/architecture.md) et formats ([qualification](docs/formats/qualification.md), [DAT](docs/formats/dat.md), [matrice de flux](docs/formats/flux.md), [constats](docs/formats/constats.md)) |
| `tests/` | tests des schémas, du script et du corpus |

## Utiliser le plugin en local

Dans Claude Code :

```
/plugin marketplace add /chemin/vers/Raton
/plugin install raton@raton
```

Les skills se lancent ainsi :

- `/raton:qualification` (ou `/raton:qualification renseigner`, `/raton:qualification valider <fiche>`), hors du dépôt de l'application : la fiche appartient à l'équipe infra ;
- `/raton:dat <fiche de qualification>` (ou `/raton:dat intention <fiche>`, `/raton:dat technique <fiche>`), depuis le dépôt de l'application à décrire ;
- `/raton:matrice-flux <fiche de qualification>`, depuis le dépôt de l'application, une fois l'intention validée et la partie technique écrite.

Les skills DAT et matrice de flux ne démarrent pas sans la fiche de qualification validée : le métier en a reçu une copie de l'équipe infra.

## Tests

Ils demandent `pyyaml` et `jsonschema` :

```bash
python3 -m unittest discover -s tests
```
