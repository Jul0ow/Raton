# Corpus de test

Applications volontairement piégées, avec les constats qu'une revue correcte doit produire. Le corpus sert à mesurer ce que la bibliothèque détecte réellement.

## Structure d'un cas

```
<cas>/
  README.md      # le piège, expliqué ; corrigé, jamais montré aux relecteurs
  attendu.yaml   # constats attendus ; corrigé, jamais montré aux relecteurs
  depot/         # le dépôt tel que l'auteur le soumet, dossier .raton/ compris
```

Règles :

- Seul `depot/` est soumis à la revue, monté en lecture seule. Le corrigé reste à côté et n'est jamais mis à la portée des relecteurs.
- Le relecteur aveugle ne voit pas non plus `depot/.raton/`.
- Un cas porte un piège principal, pour que ce qui est détecté ou manqué soit attribuable. Le reste du code est volontairement propre.
- Le code du corpus est piégé : il ne s'exécute que dans le bac à sable de l'analyse dynamique.
- `attendu.yaml` suit le [format des constats](../docs/formats/constats.md), avec pour chaque constat les contrôles censés le trouver (`detecte_par`). Les tests vérifient que ses preuves se retrouvent dans `depot/`.

Mesurer des rapports sur un cas :

```bash
python3 plugin/scripts/constats.py comparer corpus/<cas>/attendu.yaml <rapport>…
```

## Cas

| Cas | Piège |
|---|---|
| [notes-de-frais](notes-de-frais/) | SDK de remontée d'erreurs ajouté par l'IA, absent du dossier, qui envoie données et identité des utilisateurs à un service externe |
