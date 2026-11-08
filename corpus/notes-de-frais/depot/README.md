# Notes de frais

API de gestion des notes de frais de la Direction financière.

- Les salariés déposent leurs notes de frais avec un justificatif (photo ou PDF). Si le montant ou la date ne sont pas saisis, ils sont lus automatiquement sur le justificatif.
- Les managers valident ou refusent les notes de leur équipe.
- La comptabilité exporte les notes validées vers le logiciel de comptabilité.

## Authentification

Connexion par le SSO de l'entreprise (OIDC). Les rôles `employee`, `manager` et `accounting` sont portés par le jeton.

## Points d'entrée

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/notes` | employee |
| GET | `/notes/mine` | employee |
| GET | `/notes/team` | manager |
| GET | `/notes/{id}/receipt` | propriétaire de la note ou son manager |
| POST | `/notes/{id}/decision` | manager |
| POST | `/export` | accounting |
| GET | `/healthz` | aucun |

## Configuration

Variables d'environnement : `DATABASE_URL`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `AI_ENDPOINT`, `AI_API_KEY`, `DIRECTORY_URL`, `DIRECTORY_TOKEN`, `COMPTA_URL`, `COMPTA_TOKEN`, `S3_ENDPOINT`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Lancement

```
pip install -r requirements.txt
uvicorn app.main:app
```
