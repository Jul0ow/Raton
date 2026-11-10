# Raton

Bibliothèque de skills Claude Code pour relire du code non fiable avant sa mise en production : vérifier qu'une application est inoffensive, qu'elle fait ce que déclare sa documentation et qu'elle est déployable dans le SI (Kubernetes), puis produire un avis argumenté que l'entreprise peut signer.

Projet en démarrage : voir la [feuille de route](docs/feuille-de-route.md) et l'[architecture](docs/architecture.md), qui schématise l'enchaînement des skills, les données qu'ils produisent et le rôle de chaque partie prenante.

## Contenu

| Chemin | Rôle |
|---|---|
| `plugin/` | le plugin Claude Code `raton` : skills, schémas, scripts |
| `plugin/skills/dat/` | skill de co-rédaction du DAT |
| `plugin/schemas/` | schémas communs : intention, technique, rapport de contrôle, constat, corrigé du corpus |
| `plugin/scripts/dossier.py` | validation, rendu lisible et écarts du dossier `.raton/` |
| `plugin/scripts/constats.py` | validation des rapports, vérification des preuves dans le dépôt, comparaison avec un corrigé |
| `plugin/references/` | guides partagés par les skills, dont la rédaction des constats |
| `corpus/` | applications piégées et constats attendus, pour mesurer la détection |
| `docs/` | feuille de route, [architecture](docs/architecture.md) et formats ([DAT](docs/formats/dat.md), [constats](docs/formats/constats.md)) |
| `tests/` | tests des schémas, du script et du corpus |

## Utiliser le plugin en local

Dans Claude Code :

```
/plugin marketplace add /chemin/vers/Raton
/plugin install raton@raton
```

Le skill se lance avec `/raton:dat` (ou `/raton:dat intention`, `/raton:dat technique`) depuis le dépôt de l'application à décrire.

## Tests

Ils demandent `pyyaml` et `jsonschema` :

```bash
python3 -m unittest discover -s tests
```
