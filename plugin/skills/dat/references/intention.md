# Guide d'entretien : partie intention

L'entretien recueille ce que le porteur métier sait et veut. Ce n'est ni un audit ni un atelier de conception : tu ne proposes pas de fonctions et tu ne corriges pas ses choix. Tu poses des questions ouvertes, tu reformules, et tu notes « ne sait pas » quand il ne sait pas.

Vocabulaire à employer : « l'application », « les personnes qui l'utilisent », « les informations », « les autres outils ». Évite « API », « endpoint », « base de données », « flux » et « SDK ».

## Questions par thème

### Objet (`application`)

- À quoi sert l'application, en deux ou trois phrases ? Que faisait-on avant elle ?
- Qui en est responsable côté métier (nom, direction ou service) ?

### Profils (`profils`)

- Qui l'utilise ? Pour chaque groupe : fait-il partie de l'entreprise, combien de personnes environ ?
- Quelqu'un l'administre-t-il (gestion des comptes, paramétrage) ? Si oui, c'est un profil à part entière.
- Des personnes extérieures (clients, fournisseurs, prestataires) y ont-elles accès ?

### Données (`donnees`)

- Quelles informations y entrent ? Qui les saisit, ou d'où viennent-elles ?
- Lesquelles concernent des personnes ? Y en a-t-il de sensibles : santé, opinions, appartenance syndicale, origine, vie sexuelle, données biométriques ? Si oui, `personnelles: sensibles`.
- Combien de temps l'application les garde-t-elle ? Une information seulement consultée, sans être gardée, se note « non stockées ».

Regroupe par catégorie (« notes de frais », « justificatifs ») plutôt que champ par champ.

### Fonctions (`fonctions`)

- Pour chaque profil : que fait-il dans l'application, du début à la fin ? Fais dérouler une journée type.
- L'application fait-elle des choses toute seule : calculs, envois, relances, tâches à heure fixe ? Pour chacune, qu'est-ce qui la déclenche (`declencheur`) ?
- Pour chaque fonction : quelles informations lit-elle, lesquelles crée-t-elle ou modifie-t-elle ?

### Échanges (`echanges`)

C'est le thème le plus important pour la revue : un échange oublié ici devient un flux non déclaré. Passe la liste suivante en revue, explicitement, même si l'utilisateur pense avoir tout dit :

- services d'IA : assistant conversationnel, lecture de documents, transcription, traduction, résumé ;
- envoi d'e-mails, de SMS ou de notifications ;
- stockage ou partage de fichiers en ligne ;
- outils de l'entreprise : annuaire, messagerie, ERP, CRM, paie, comptabilité, GED ;
- paiement, cartographie, signature électronique ;
- mesure d'audience, statistiques de visite, suivi des erreurs ;
- fichiers déposés ou récupérés sur un serveur, exports et imports réguliers.

Pour chaque échange : avec quel partenaire, dans quel sens vont les informations (l'application reçoit, envoie, ou les deux), lesquelles, et pourquoi. Un partenaire dont le nom n'est pas connu se note tel quel : « service d'IA externe (fournisseur à préciser) ».

L'authentification par le compte de l'entreprise n'est pas un échange : la partie technique la décrit.

### Exclusions (`exclusions`)

Propose des affirmations et fais-les confirmer ou infirmer une à une. Ne garde que celles que l'utilisateur confirme sans hésiter.

- Aucune information ne sort de l'entreprise (ou : seulement vers tel échange).
- L'application n'est pas accessible depuis Internet.
- Elle ne traite aucune donnée sensible.
- Elle ne prend aucune décision sans action humaine.
- Elle ne supprime ni ne modifie de données dans les autres outils.
- Elle n'envoie rien aux personnes extérieures.

Une exclusion est une promesse vérifiable : la revue la confrontera au code.

## Identifiants

`P01`, `D01`, `F01`, `E01`, `X01`, numérotés dans l'ordre d'apparition. Un identifiant ne change jamais d'élément, d'une version à l'autre : un élément supprimé libère son numéro sans qu'on le réutilise.

## Squelette

```yaml
format: raton/intention/v0
application:
  nom: …
  objet: >
    …
  porteur: { nom: …, entite: … }
profils:
  - { id: P01, libelle: …, population: interne, effectif: … }
donnees:
  - { id: D01, libelle: …, origine: …, personnelles: oui, conservation: … }
fonctions:
  - id: F01
    libelle: …
    profils: [P01]            # ou declencheur: … pour une fonction automatique
    donnees: { lit: [D01], ecrit: [D01] }
    echanges: [E01]
echanges:
  - { id: E01, partenaire: …, sens: envoie, donnees: [D01], motif: … }
exclusions:
  - { id: X01, libelle: … }
# validation : ajoutée seulement après accord explicite du valideur
```

Les textes libres sont courts (200 caractères, 1000 pour l'objet) : ce sont des données que la revue compare, pas de la prose.
