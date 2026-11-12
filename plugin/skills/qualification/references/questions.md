# Guide d'entretien : qualification

L'entretien sert à recueillir des faits sur l'usage et sur l'impact. Il ne s'agit pas de négocier un niveau de contrôle. Tu poses des questions concrètes, tu reformules, et tu déduis le niveau d'après l'échelle.

Vocabulaire à employer : « l'application », « les personnes qui l'utilisent », « les informations ». Évite « DICP », « palier » et « exposition » tant que le métier ne les emploie pas lui-même.

## Identité (`application`)

- Quel est le nom de l'application ? À quoi sert-elle, en deux ou trois phrases ?
- Qui en est responsable côté métier (nom, direction ou service) ?
- Où se trouve son code (adresse du dépôt) ? Si le métier ne le sait pas, laisse le champ vide.
- `code` : propose-le à partir du nom, en minuscules avec des tirets (`notes-de-frais`), et fais-le confirmer. Il ne change plus ensuite.

## Utilisateurs et exposition (`utilisateurs`, `exposition`)

- Qui utilise l'application ? Seulement des salariés (`interne`) ? Des personnes extérieures qui ont un compte : clients, fournisseurs, partenaires (`externe`) ? N'importe qui, sans compte (`public`) ?
- Combien de personnes environ ?
- Faut-il pouvoir s'en servir depuis l'extérieur du réseau de l'entreprise : depuis Internet, chez soi sans VPN, sur un téléphone, ou depuis le réseau d'un partenaire ou d'un client, même par une interconnexion dédiée ? Si oui, `externe`. Un réseau que l'entreprise ne maîtrise pas est peu fiable, quel que soit le lien avec le partenaire. Un public sans compte implique toujours `externe`.

## Interconnexions (`interconnexions`)

Une application qui peut parler à beaucoup d'outils a beaucoup de capacités : c'est ce thème qui les recense. Passe la liste en revue, explicitement :

- outils de l'entreprise : annuaire, messagerie, ERP, comptabilité, paie, CRM, GED, partages de fichiers ;
- autres applications de l'entreprise, et leurs bases lues ou modifiées directement ;
- services en ligne : IA, envoi d'e-mails ou de SMS, stockage, paiement, cartographie, statistiques, suivi des erreurs ;
- partenaires, clients ou prestataires, y compris par un réseau d'interconnexion dédié.

Pour chaque système :

- `systeme`, `usage` : lequel, et qu'est-ce que l'application en fait ? Note la réponse dans ses mots.
- `zone` : est-il hors de l'entreprise, ou joint par le réseau d'un partenaire ? Si oui, `externe`.
- `acces` : l'application se contente-t-elle de consulter (`lecture`) ? Crée-t-elle, modifie-t-elle ou supprime-t-elle des informations, ou déclenche-t-elle des actions comme un envoi ou un paiement (`ecriture`) ? Gère-t-elle le système lui-même : comptes, droits, configuration (`administration`) ? S'il ne sait pas : `a_verifier`.
- `nature` : par une API, en lisant directement la base, par des fichiers, par courriel ? S'il ne sait pas, ce qui est courant : `a_verifier`.
- `sensible` : `a_verifier`, sauf si un référentiel des applications le donne. Faute de référentiel, c'est à l'équipe infra de le dire.

Ne compte pas les stockages propres de l'application, ni les services communs à toutes les applications : authentification par le compte de l'entreprise, gestionnaire de secrets, journalisation, supervision.

## Données personnelles (`donnees_personnelles`)

- L'application garde-t-elle ou manipule-t-elle des informations sur des personnes : noms, coordonnées, situation, dossiers ? L'identité des personnes qui se connectent ne compte pas : toute application la connaît.
- Sur qui portent-elles : salariés, clients, candidats, patients… ? Combien de personnes environ ?
- Y a-t-il des informations sensibles : santé, opinions politiques, convictions religieuses, appartenance syndicale, origine, vie sexuelle, données biométriques ou génétiques, infractions ou condamnations ? Si oui, `sensibles`.

## Besoins de sécurité (`dicp`)

Pose la question de chaque axe, laisse le métier répondre, puis propose le niveau et fais-le confirmer. Le motif reprend sa réponse, en 200 caractères au plus.

### Disponibilité

« Si l'application s'arrête, au bout de combien de temps est-ce un vrai problème ? Que fait-on en attendant ? »

| Niveau | Un arrêt est supportable… |
|---|---|
| 1 | plusieurs jours |
| 2 | une journée au plus |
| 3 | quelques heures au plus |
| 4 | moins d'une heure |

### Intégrité

« Si l'application enregistre ou calcule une information fausse, ou si quelqu'un la modifie sans en avoir le droit, que se passe-t-il ? »

| Niveau | Conséquences |
|---|---|
| 1 | négligeables : l'erreur se voit et se corrige sans dommage |
| 2 | limitées : gêne, reprise manuelle |
| 3 | importantes : perte financière, non-conformité, décision erronée sur une personne |
| 4 | graves : sécurité des personnes, perte majeure, mise en cause pénale |

### Confidentialité

« Si toutes les informations de l'application devenaient visibles de tous les salariés, ou publiées sur Internet, quelles conséquences ? »

| Niveau | Les informations sont… |
|---|---|
| 1 | publiques : aucune conséquence |
| 2 | à usage interne : leur diffusion hors de l'entreprise gênerait |
| 3 | confidentielles : réservées à certaines personnes, avec un préjudice si elles circulent |
| 4 | secrètes : leur divulgation causerait un préjudice grave |

### Preuve

« Faut-il pouvoir dire, après coup, qui a fait quoi et quand ? Pour qui : vous, un auditeur, un juge ? »

| Niveau | Savoir qui a fait quoi est… |
|---|---|
| 1 | inutile |
| 2 | utile au diagnostic |
| 3 | exigé pour un contrôle : audit interne, commissaire aux comptes, contrôle fiscal |
| 4 | exigé avec valeur probante : opposable en justice |

## Signes de sous-évaluation

À vérifier pendant l'entretien, puis par l'équipe infra pendant la validation :

- des données personnelles « non » alors que l'application gère des dossiers, des demandes ou des comptes de personnes autres que ses utilisateurs ;
- une confidentialité de niveau 1 ou 2 pour des informations sur des personnes, des montants, des contrats ou des documents internes ;
- une intégrité de niveau 1 ou 2 pour une application qui calcule des montants, déclenche des paiements ou prend des décisions sur des personnes ;
- des utilisateurs « salariés seulement » alors que l'objet parle de clients, de fournisseurs ou de candidats ;
- une exposition « interne » alors que l'usage décrit se fait en déplacement, chez des tiers ou depuis le réseau d'un partenaire ;
- une interconnexion en lecture alors que l'usage décrit une modification, un envoi ou une action ;
- une interconnexion interne alors que le système appartient à un partenaire ou à un prestataire ;
- aucune interconnexion pour une application dont l'objet parle d'export, de synchronisation ou de notifications ;
- un motif qui décrit un impact plus fort que le niveau choisi.

## Squelette

```yaml
format: raton/qualification/v0
application:
  code: …
  nom: …
  objet: >
    …
  porteur: { nom: …, entite: … }
  depot: …                     # si connu
exposition: interne            # interne | externe
utilisateurs:
  populations: [interne]       # interne | externe | public
  effectif: …
interconnexions:               # liste vide s'il n'y en a aucune
  - id: I01
    systeme: …
    usage: …
    zone: interne              # interne | externe | a_verifier
    nature: a_verifier         # api | base_de_donnees | fichiers | courriel | autre | a_verifier
    acces: lecture             # lecture | ecriture | administration | a_verifier
    sensible: a_verifier       # oui | non | a_verifier : l'équipe infra tranche
donnees_personnelles:
  niveau: oui                  # non | oui | sensibles ; si non, rien d'autre
  personnes: [salariés]
  volume: …
dicp:
  disponibilite: { niveau: …, motif: … }
  integrite: { niveau: …, motif: … }
  confidentialite: { niveau: …, motif: … }
  preuve: { niveau: …, motif: … }
# exigences : recopiées depuis « qualification.py calculer »
# validation : ajoutée par l'équipe infra seulement
```
