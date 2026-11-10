# Corpus de test

Applications volontairement piégées, avec les constats qu'une revue correcte doit produire. Le corpus ne sert pas à relire des applications : il sert à **mesurer Raton lui-même**, comme des tests unitaires pour les relecteurs (voir la [boucle de mesure](../docs/architecture.md#1-un-même-pipeline-deux-usages)).

- Les mainteneurs de Raton construisent chaque cas : ils cachent un piège dans `depot/` et écrivent le corrigé, `attendu.yaml`.
- Le pipeline relit `depot/` comme n'importe quelle application et produit ses rapports.
- `constats.py comparer` confronte ces rapports au corrigé : constats détectés, manqués, et en trop.
- Le résultat sert à mesurer la détection et les faux positifs, à vérifier qu'un changement de prompt, de modèle ou d'outil ne dégrade rien, et à fonder la rubrique « ce qui n'a pas été vérifié » des avis.

Une application réelle n'a pas de corrigé : sa revue s'arrête à l'avis.

## Structure d'un cas

```
<cas>/
  README.md           # le piège, expliqué ; corrigé, jamais montré aux relecteurs
  attendu.yaml        # constats attendus ; corrigé, jamais montré aux relecteurs
  qualification.yaml  # fiche validée par l'équipe infra : entrée du pipeline, hors du dépôt de l'auteur
  depot/              # le dépôt tel que l'auteur le soumet, dossier .raton/ compris
```

Règles :

- Seul `depot/` est soumis à la revue, monté en lecture seule. Le corrigé reste à côté et n'est jamais mis à la portée des relecteurs.
- Le relecteur aveugle ne voit pas non plus `depot/.raton/`.
- La [fiche de qualification](../docs/formats/qualification.md) n'est pas un corrigé : comme pour une vraie application, elle vient de l'équipe infra et choisit les contrôles. Elle reste hors de `depot/`, parce que l'auteur ne doit pas pouvoir la modifier.
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
