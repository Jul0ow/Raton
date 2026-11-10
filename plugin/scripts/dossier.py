#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Outils déterministes sur le dossier Raton (.raton/).

  dossier.py valider CHEMIN     valide un fichier du dossier, ou le répertoire .raton entier
  dossier.py rendre FICHIER     rend intention.yaml en Markdown lisible, pour validation humaine
  dossier.py ecarts REPERTOIRE  compare intention.yaml et technique.yaml par références

Les fichiers lus viennent de l'auteur : ce sont des données non fiables. Le script ne fait
que les analyser ; il n'exécute rien de ce qu'ils contiennent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from raton_formats import ErreurFormat, charger, doublons, erreurs_schema
from raton_formats import ids as _ids

FORMATS = ("raton/intention/v0", "raton/technique/v0")


# --- Validation --------------------------------------------------------------


def _refs(contexte, refs, connus, erreurs):
    for r in refs or []:
        if r not in connus:
            erreurs.append(f"{contexte} : référence inconnue {r}")


def coherence_intention(doc):
    """Références internes à l'intention. Renvoie (erreurs, avertissements)."""
    erreurs, avert = [], []
    for section in ("profils", "donnees", "fonctions", "echanges", "exclusions"):
        erreurs += doublons(section, doc.get(section))
    profils = set(_ids(doc["profils"]))
    donnees = set(_ids(doc["donnees"]))
    echanges = set(_ids(doc["echanges"]))

    utilisees, profils_utiles, echanges_utiles = set(), set(), set()
    for f in doc["fonctions"]:
        _refs(f"fonction {f['id']}", f.get("profils"), profils, erreurs)
        for mode in ("lit", "ecrit"):
            _refs(f"fonction {f['id']}", f["donnees"].get(mode), donnees, erreurs)
            utilisees.update(f["donnees"].get(mode, []))
        _refs(f"fonction {f['id']}", f.get("echanges"), echanges, erreurs)
        profils_utiles.update(f.get("profils", []))
        echanges_utiles.update(f.get("echanges", []))
    for e in doc["echanges"]:
        _refs(f"échange {e['id']}", e["donnees"], donnees, erreurs)
        utilisees.update(e["donnees"])

    for p in sorted(profils - profils_utiles):
        avert.append(f"profil {p} : aucune fonction ne lui est ouverte")
    for d in sorted(donnees - utilisees):
        avert.append(f"donnée {d} : utilisée par aucune fonction ni aucun échange")
    for e in sorted(echanges - echanges_utiles):
        avert.append(f"échange {e} : rattaché à aucune fonction")
    if not doc["exclusions"]:
        avert.append("exclusions : aucune ; dire ce que l'application ne fait pas aide la revue")
    if "validation" not in doc:
        avert.append("brouillon : pas de section validation, la revue ne peut pas s'appuyer sur cette intention")
    return erreurs, avert


def coherence_technique(doc, intention=None):
    erreurs = []
    for section in ("composants", "stockages", "services_tiers"):
        erreurs += doublons(section, doc.get(section))
    if intention is None:
        return erreurs, []
    fonctions = set(_ids(intention["fonctions"]))
    donnees = set(_ids(intention["donnees"]))
    echanges = set(_ids(intention["echanges"]))
    profils = set(_ids(intention["profils"]))
    for c in doc["composants"]:
        _refs(f"composant {c['id']}", c.get("fonctions"), fonctions, erreurs)
    for s in doc["stockages"]:
        _refs(f"stockage {s['id']}", s.get("donnees"), donnees, erreurs)
    for t in doc["services_tiers"]:
        _refs(f"service {t['id']}", t.get("donnees_transmises"), donnees, erreurs)
        _refs(f"service {t['id']}", t.get("echanges"), echanges, erreurs)
    for r in doc["authentification"].get("roles", []):
        _refs(f"rôle {r['role']}", r.get("profils"), profils, erreurs)
    return erreurs, []


def valider_document(doc, intention=None):
    """Renvoie (format, erreurs, avertissements)."""
    format_, erreurs = erreurs_schema(doc, FORMATS)
    if erreurs:  # la cohérence suppose un document conforme au schéma
        return format_, erreurs, []
    if format_ == "raton/intention/v0":
        return (format_, *coherence_intention(doc))
    return (format_, *coherence_technique(doc, intention))


def valider_chemin(chemin: Path):
    """Valide un fichier, ou un répertoire .raton (intention puis technique,
    avec contrôle des références de l'une vers l'autre)."""
    resultats = []
    if chemin.is_dir():
        intention = None
        fichier_i = chemin / "intention.yaml"
        if fichier_i.exists():
            doc_i = charger(fichier_i)
            fmt, err, av = valider_document(doc_i)
            resultats.append((fichier_i, err, av))
            if not err and fmt == "raton/intention/v0":
                intention = doc_i
        fichier_t = chemin / "technique.yaml"
        if fichier_t.exists():
            _, err, av = valider_document(charger(fichier_t), intention)
            resultats.append((fichier_t, err, av))
        if not resultats:
            raise ErreurFormat(f"{chemin} : ni intention.yaml ni technique.yaml")
    else:
        _, err, av = valider_document(charger(chemin))
        resultats.append((chemin, err, av))
    return resultats


# --- Écarts intention / technique --------------------------------------------


def ecarts(intention, technique):
    """Écarts constatés par simple jeu de références. Chaque écart est un couple
    (code, message). Ce sont des points à examiner, pas des erreurs de format."""
    res = []
    libelles = {
        e["id"]: e.get("libelle") or e.get("partenaire")
        for section in ("profils", "donnees", "fonctions", "echanges")
        for e in intention[section]
    }

    def nom(i):
        return f"{i} ({libelles[i]})" if i in libelles else i

    realisees = {f for c in technique["composants"] for f in c.get("fonctions", [])}
    for f in intention["fonctions"]:
        if f["id"] not in realisees:
            res.append(("fonction_non_realisee", f"{nom(f['id'])} : réalisée par aucun composant"))

    echanges = {e["id"]: e for e in intention["echanges"]}
    couverts = set()
    for t in technique["services_tiers"]:
        refs = t.get("echanges", [])
        couverts.update(refs)
        if not refs:
            res.append(("service_sans_echange", f"{t['id']} ({t['libelle']}) : ne renvoie à aucun échange déclaré"))
        prevues = {d for e in refs if e in echanges for d in echanges[e]["donnees"]}
        for d in t.get("donnees_transmises", []):
            if d not in prevues:
                res.append(("donnee_non_prevue", f"{t['id']} ({t['libelle']}) : transmet {nom(d)}, absente des échanges"))
    for e in echanges:
        if e not in couverts:
            res.append(("echange_sans_service", f"{nom(e)} : aucun service ne le réalise"))

    roles = technique["authentification"].get("roles", [])
    for r in roles:
        if not r.get("profils"):
            res.append(("role_sans_profil", f"rôle « {r['role']} » : ne correspond à aucun profil"))
    if technique["authentification"]["mecanisme"] != "aucune":
        avec_role = {p for r in roles for p in r.get("profils", [])}
        for p in intention["profils"]:
            if p["id"] not in avec_role:
                res.append(("profil_sans_role", f"{nom(p['id'])} : aucun rôle technique"))
    return res


# --- Rendu lisible -----------------------------------------------------------


_MD_SPECIAUX = str.maketrans({c: "\\" + c for c in "\\`*_[]<>|#"})


def _cell(texte):
    """Texte de l'auteur rendu inerte : pas de lien, d'image, de balise ni de
    mise en forme qui changerait ce que le valideur croit lire."""
    return " ".join(str(texte).split()).translate(_MD_SPECIAUX)


def rendre_intention(doc):
    lib = {e["id"]: e.get("libelle") or e.get("partenaire") for s in ("profils", "donnees", "echanges") for e in doc[s]}

    def noms(ids):
        return ", ".join(f"{lib.get(i, i)} ({i})" for i in ids) or "—"

    app, val = doc["application"], doc.get("validation")
    lignes = [
        f"# {_cell(app['nom'])} — intention",
        "",
    ]
    if val is None:
        lignes += ["> **Brouillon, non validé.**", ""]
    lignes += [
        _cell(app["objet"]),
        "",
        f"Porteur métier : {_cell(app['porteur']['nom'])} ({_cell(app['porteur']['entite'])})",
        "",
        "## Qui utilise l'application",
        "",
        "| Profil | Population | Effectif |",
        "|---|---|---|",
    ]
    for p in doc["profils"]:
        lignes.append(f"| {_cell(p['libelle'])} ({p['id']}) | {p['population']} | {p.get('effectif', '—')} |")
    lignes += ["", "## Données manipulées", "", "| Donnée | Origine | Personnelles | Conservation |", "|---|---|---|---|"]
    for d in doc["donnees"]:
        lignes.append(
            f"| {_cell(d['libelle'])} ({d['id']}) | {_cell(d['origine'])} | {d['personnelles']} | {_cell(d['conservation'])} |"
        )
    lignes += ["", "## Ce que l'application permet de faire", ""]
    for f in doc["fonctions"]:
        qui = noms(f["profils"]) if f.get("profils") else f"automatique, {_cell(f['declencheur'])}"
        lignes.append(f"- **{_cell(f['libelle'])}** ({f['id']}) — {qui}")
        if f["donnees"].get("lit"):
            lignes.append(f"  - lit : {noms(f['donnees']['lit'])}")
        if f["donnees"].get("ecrit"):
            lignes.append(f"  - écrit : {noms(f['donnees']['ecrit'])}")
        if f.get("echanges"):
            lignes.append(f"  - échanges : {noms(f['echanges'])}")
    sens = {"recoit": "reçoit", "envoie": "envoie", "les_deux": "envoie et reçoit"}
    lignes += ["", "## Avec qui l'application échange des données", ""]
    if doc["echanges"]:
        lignes += ["| Partenaire | Sens | Données | Motif |", "|---|---|---|---|"]
        for e in doc["echanges"]:
            lignes.append(
                f"| {_cell(e['partenaire'])} ({e['id']}) | l'application {sens[e['sens']]} | {noms(e['donnees'])} | {_cell(e['motif'])} |"
            )
    else:
        lignes.append("Aucun échange avec un autre système.")
    lignes += ["", "## Ce que l'application ne fait pas", ""]
    lignes += [f"- {_cell(x['libelle'])} ({x['id']})" for x in doc["exclusions"]] or ["Rien n'est précisé."]
    lignes += ["", "## Validation", ""]
    if val is None:
        lignes.append("Pas encore validée.")
    else:
        lignes += [
            f"Version {val['version']}, rédigée par {_cell(val['redige_par'])}, "
            f"validée par {_cell(val['valide_par'])} le {val['date']}.",
            "Le valideur atteste que cette intention a été rédigée sans partir du code.",
        ]
    return "\n".join(lignes) + "\n"


# --- Ligne de commande -------------------------------------------------------


def _cmd_valider(args):
    code = 0
    for fichier, erreurs, avert in valider_chemin(Path(args.chemin)):
        if erreurs:
            code = 1
            print(f"✗ {fichier}")
            for e in erreurs:
                print(f"  erreur : {e}")
        else:
            print(f"✓ {fichier}")
        for a in avert:
            print(f"  avertissement : {a}")
    return code


def _charger_valide(chemin, format_, intention=None):
    doc = charger(chemin)
    fmt, erreurs, _ = valider_document(doc, intention)
    if erreurs or fmt != format_:
        raise ErreurFormat(f"{chemin} : non valide, lancer d'abord « dossier.py valider »")
    return doc


def _cmd_rendre(args):
    sys.stdout.write(rendre_intention(_charger_valide(Path(args.fichier), "raton/intention/v0")))
    return 0


def _cmd_ecarts(args):
    rep = Path(args.repertoire)
    intention = _charger_valide(rep / "intention.yaml", "raton/intention/v0")
    technique = _charger_valide(rep / "technique.yaml", "raton/technique/v0", intention)
    liste = ecarts(intention, technique)
    for code, message in liste:
        print(f"[{code}] {message}")
    print(f"{len(liste)} écart(s)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dossier.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("valider", help="valider un fichier ou un répertoire .raton")
    p.add_argument("chemin")
    p.set_defaults(func=_cmd_valider)
    p = sous.add_parser("rendre", help="rendre intention.yaml en Markdown")
    p.add_argument("fichier")
    p.set_defaults(func=_cmd_rendre)
    p = sous.add_parser("ecarts", help="écarts entre intention et technique")
    p.add_argument("repertoire")
    p.set_defaults(func=_cmd_ecarts)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
