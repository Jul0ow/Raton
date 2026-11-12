# Bibliothèque de skills — relecture de code non fiable avant mise en production

## Contexte

De plus en plus de personnes métier, qui codent peu ou pas, produisent (souvent avec une IA) des applications utiles qu'elles veulent mettre en production. L'entreprise n'a aucune raison de faire confiance à ce code, et le volume produit dépasse ce qu'un humain peut relire.

La bibliothèque doit permettre de vérifier qu'une application :
- est inoffensive : pas de faille, pas de maliciel, pas d'exfiltration de données ;
- fait ce qui est déclaré dans sa documentation ;
- est déployable dans le SI (Kubernetes pour l'instant).

Elle aboutit à un avis argumenté que l'entreprise peut signer.

## Principes directeurs

- **Tout ce qui vient de l'auteur est non fiable.** Le code, mais aussi la documentation, les commentaires et les fichiers destinés aux IA (README, CLAUDE.md, AGENTS.md, .cursorrules). Les agents relecteurs les traitent comme des données, jamais comme des instructions. Une tentative d'injection visant les relecteurs est elle-même un constat.
- **L'intention vient de l'humain.** La partie « intention » du DAT est rédigée ou validée par le métier sans partir du code. C'est la référence de la revue : une doc générée depuis le code concorderait forcément avec lui et ne prouverait rien.
- **Aucune exécution hors bac à sable.** La revue statique est en lecture seule et sans réseau (pas même un `npm install`, qui exécute les scripts postinstall). L'exécution n'a lieu que pendant l'analyse dynamique, en environnement isolé.
- **Le déterministe d'abord, les LLM ensuite.** Des outils reproductibles (SAST, secrets, CVE, IaC) produisent des preuves auditables. Les agents trient leurs résultats et couvrent ce que les outils ne voient pas : logique métier, écart avec l'intention, flux cachés.
- **Formats communs, comparaison mécanique.** Les constats sont structurés (fichier, ligne, catégorie, sévérité, preuve) et la matrice de flux est lisible par machine. La revue aveugle produit les mêmes artefacts que la doc, ce qui permet un diff automatique.
- **Plusieurs passes, et un humain tranche.** Les LLM ne sont pas déterministes : une divergence entre passes, ou entre revue aveugle et revue informée, est escaladée à un humain.
- **Proportionnalité.** Le niveau d'exigence découle de la qualification (criticité, sensibilité DICP, exposition, données personnelles).
- **La doc devient un contrôle.** La matrice de flux génère les NetworkPolicies et les règles d'egress : un flux non déclaré est bloqué en production, même si la revue l'a manqué.
- **Un avis porte sur un commit précis (SHA).** Toute nouvelle version passe par la revue différentielle.
- **Modèle de menace.** Le risque réel vient surtout de la négligence (données métier envoyées à une API tierce, SDK qui renvoie de la télémétrie, dépendance compromise ou inventée par une IA) plutôt que de la malveillance. La revue est pourtant conçue comme si l'auteur était malveillant.
- **Limites explicites.** L'absence de constat ne prouve pas l'absence de faille. Chaque avis dit ce qui a été vérifié et ce qui ne l'a pas été.

## Chaîne de traitement

Qualification → dossier (DAT, matrice de flux, dossier d'exploitation) → contrôles déterministes → revue par agents aveugle / informée → analyse dynamique → synthèse et avis.

## Catalogue des skills

| # | Skill | Objectif | Livrable |
|---|---|---|---|
| 1 | Qualification | Classer l'application : criticité métier, sensibilité DICP, exposition (interne ou Internet), données personnelles (lien avec le registre RGPD), utilisateurs | Fiche d'identité, palier d'exigence et liste des contrôles obligatoires |
| 2 | DAT | Décrire l'application. Format co-rédigé : une partie « intention » remplie par l'humain (fonctions, données, utilisateurs, flux attendus) et une partie technique assistée | DAT au format commun ; la partie intention sert de référence à la revue |
| 3 | Matrice de flux | Déclarer tous les flux entrants et sortants | Fichier YAML validé par un schéma ; génération des NetworkPolicies et règles d'egress |
| 4 | Dossier d'exploitation | Logs, probes, métriques, sauvegarde et restauration, runbook, responsable de la maintenance | Dossier d'exploitation ; constat si personne n'est désigné pour maintenir l'appli |
| 5 | Palier de déployabilité Kubernetes | Dockerfile non-root, image épinglée par digest, securityContext, requests/limits, probes, Pod Security Standards en mode restricted, ni privileged ni hostPath ; présence de tests et de documentation | Palier atteint comparé au palier exigé |
| 6 | Chaîne d'approvisionnement | SBOM, lockfile, versions épinglées, CVE, scripts d'installation, paquets inexistants ou typosquattés, licences, images de base | SBOM et constats |
| 7 | Secrets et configuration | Aucun secret dans le code ni dans l'historique git ; configuration externalisée ; secrets fournis par l'outil de l'entreprise | Constats |
| 8 | Identité et accès | SSO de l'entreprise plutôt qu'une authentification maison, contrôle des rôles, aucun endpoint d'admin ouvert | Constats |
| 9 | Revue par agents aveugle / informée | Agents sans contexte, en lecture seule. L'aveugle reconstruit, depuis le seul code, ce que fait l'appli (résumé d'architecture et matrice de flux) ; l'informé vérifie la conformité au DAT ; un juge compare. Recherche de failles, maliciels, exfiltration, obfuscation, déclencheurs conditionnels et injections visant les relecteurs | Constats structurés et diff doc / code : flux non déclarés, fonctions non décrites, incohérences |
| 10 | Analyse dynamique | Déployer dans un namespace isolé, egress fermé et journalisé, puis comparer les flux observés (DNS, connexions) à la matrice | Flux observés comparés aux flux déclarés |
| 11 | Revue différentielle | Revoir le delta entre le commit approuvé et la nouvelle version, en se concentrant sur ce qui change le risque (flux, dépendances, permissions) | Avis sur le nouveau SHA |
| 12 | Synthèse et avis | Agréger tous les résultats | Avis Go / Go avec réserves / No-Go, périmètre vérifié et non vérifié, prêt à signer |
| 13 | Pré-contrôle côté auteur | Version self-service pour que le métier arrive avec un dossier complet | Liste des manques avant soumission |

## Composants transverses

- **Schémas communs** : format des constats, matrice de flux, fiche de qualification.
- **Outillage de revue** : une image conteneur aux versions épinglées (pistes : Semgrep ou CodeQL, gitleaks, Trivy ou osv-scanner, Syft, kubescape ou Checkov), lancée sur le dépôt monté en lecture seule et sans réseau, pour des résultats reproductibles.
- **Agents** : relecteur aveugle, relecteur informé et juge, avec des outils limités à la lecture.
- **Corpus de test** : des applications volontairement piégées avec les constats attendus, pour mesurer ce que la bibliothèque détecte réellement. Exemples : exfiltration via un SDK d'analytics, secret en dur, script postinstall, injection dans le README, flux non déclaré, authentification maison.

## Ordre de construction

1. **Socle** : dépôt, structure de plugin, schémas communs, premières applis du corpus de test.
2. **Dossier** : qualification, DAT, matrice de flux.
3. **Contrôles** : outillage, chaîne d'approvisionnement, secrets, identité et accès, palier Kubernetes.
4. **Revue par agents** aveugle / informée.
5. **Synthèse et avis** : premier pipeline complet, mesuré sur le corpus de test.
6. **Extensions** : analyse dynamique, revue différentielle, dossier d'exploitation, pré-contrôle côté auteur.

## Questions ouvertes

- Langages et frameworks des applis à relire (règles SAST à prévoir).
- Briques du SI à imposer : SSO (OIDC ?), gestionnaire de secrets, registre d'images, CNI (NetworkPolicy standard ou CiliumNetworkPolicy ?). Pour le CNI, le [format de la matrice de flux](formats/flux.md#le-choix-du-cni) recommande Cilium, qui filtre les destinations par nom ; le générateur sait aussi produire des NetworkPolicy standard, avec un proxy sortant.
- Échelle DICP et règle de calcul du palier : à aligner sur la PSSI de l'entreprise. Une proposition par défaut figure dans le [format de la qualification](formats/qualification.md).
- Qui signe l'avis : RSSI, architecte, comité ? Hypothèse de travail retenue le 2026-11-10 : le RSSI signe ; l'équipe infra mène la revue et exploite l'application.
- Diffusion de la bibliothèque : plugin Claude Code via une marketplace interne ?
- Diversité des relecteurs : même modèle sur plusieurs passes, ou modèles différents ?

## Statut

- 2026-11-08 : catalogue et principes validés. Développement dans un dépôt git avec Claude Code. Prochaine étape : le format du DAT.
- 2026-11-08 : format du DAT validé ([docs/formats/dat.md](formats/dat.md)). Structure de plugin, schémas intention et technique, script `dossier.py`, skill DAT, premier cas du corpus (notes de frais : SDK de remontée d'erreurs non déclaré).
- 2026-11-10 : proposition de format des constats, à valider ([docs/formats/constats.md](formats/constats.md)). Script `constats.py` : validation, vérification des preuves dans le dépôt, comparaison avec un corrigé du corpus.
- 2026-11-10 : [architecture](architecture.md) schématisée : skills, données, parties prenantes. Rôles retenus pour l'instant : l'équipe infra mène la revue et exploite l'application, le RSSI signe l'avis.
- 2026-11-10 : proposition de format de la qualification, à valider ([docs/formats/qualification.md](formats/qualification.md)) : trois paliers calculés par une règle publique, fiche validée et rangée par l'équipe infra hors du dépôt de l'application, recoupée avec l'intention. Script `qualification.py`, skill qualification, fiche du cas `notes-de-frais`.
- 2026-11-10 : format des constats validé ([docs/formats/constats.md](formats/constats.md)).
- 2026-11-12 : décisions de la qualification validées, avec trois demandes : transmission de la fiche par demande de fusion ou par ticket, exposition `externe` (tout réseau que l'entreprise ne maîtrise pas, interconnexions avec les partenaires comprises) plutôt que `internet`, registre RGPD écarté pour l'instant. Ajout des interconnexions de l'application à la fiche : droits, sensibilité du système cible et zone pèsent sur le palier, une interconnexion externe compte comme une exposition externe, et les échanges de l'intention y renvoient.
- 2026-11-12 : interconnexions validées, avec le tableau droits × sensibilité et la règle « ce qui reste à vérifier compte au plus haut ». Prochaine étape : la matrice de flux.
- 2026-11-12 : proposition de format de la matrice de flux, à valider ([docs/formats/flux.md](formats/flux.md)) : flux dans le sens des connexions, renvois aux échanges de l'intention et aux interconnexions de la fiche, destinations par nom ou par bloc d'adresses. Fichier de plateforme tenu par l'équipe infra. Script `flux.py` : validation, écarts avec le dossier, génération des politiques réseau (refus par défaut ; Cilium ou NetworkPolicy standard avec proxy sortant). Skill matrice-flux, matrice du cas `notes-de-frais`, qui omet le SDK Sentry comme sa partie technique.
