#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Outils déterministes sur les constats (rapports de contrôle et corrigés du corpus).

  constats.py valider FICHIER…                 schéma et règles de cohérence
  constats.py verifier FICHIER --depot DEPOT   les preuves citées existent-elles dans le dépôt ?
  constats.py comparer ATTENDU RAPPORT…        constats détectés, manqués et supplémentaires

Les rapports peuvent venir d'un agent, et les extraits qu'ils citent viennent de l'auteur :
ce sont des données non fiables. Le script les compare au dépôt sans rien exécuter, et
n'affiche jamais le contenu des fichiers du dépôt.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from raton_formats import ErreurFormat, charger, doublons, erreurs_schema

FORMATS = ("raton/rapport/v0", "raton/attendu/v0")
MASQUE = "***"
EXTRAIT_MIN = 5  # caractères significatifs : en deçà, un extrait se retrouve partout
PLAGE_MAX = 200  # lignes
MASQUES_MAX = 10  # borne aussi le coût de la recherche
TOLERANCE_LIGNES = 3  # pour apparier deux preuves de code
TAILLE_FICHIER_MAX = 5_000_000


# --- Validation --------------------------------------------------------------


def coherence(doc):
    """Règles que le schéma ne peut pas exprimer. Renvoie (erreurs, avertissements)."""
    erreurs = doublons("constats", doc["constats"])
    avert = []
    for c in doc["constats"]:
        for i, p in enumerate(c["preuves"]):
            ou = f"constat {c['id']}, preuve {i + 1}"
            if "lignes" in p:
                debut, fin = p["lignes"]
                if fin < debut:
                    erreurs.append(f"{ou} : lignes [{debut}, {fin}] à l'envers")
                elif fin - debut >= PLAGE_MAX:
                    erreurs.append(f"{ou} : plage de plus de {PLAGE_MAX} lignes")
            if "extrait" in p:
                significatif = "".join(p["extrait"].replace(MASQUE, "").split())
                if len(significatif) < EXTRAIT_MIN:
                    erreurs.append(f"{ou} : extrait trop court pour être probant")
                if p["extrait"].count(MASQUE) > MASQUES_MAX:
                    erreurs.append(f"{ou} : plus de {MASQUES_MAX} valeurs masquées")
                if c["categorie"] == "secret_expose" and MASQUE not in p["extrait"]:
                    erreurs.append(f"{ou} : extrait d'un secret non masqué (remplacer la valeur par {MASQUE})")
        if c["categorie"] == "autre":
            avert.append(f"constat {c['id']} : catégorie « autre », à requalifier")
    if doc["format"] == "raton/rapport/v0" and not doc["perimetre"]["non_verifie"]:
        avert.append("périmètre : rien n'est déclaré non vérifié ; aucun contrôle ne couvre tout")
    return erreurs, avert


def valider_document(doc):
    """Renvoie (format, erreurs, avertissements)."""
    format_, erreurs = erreurs_schema(doc, FORMATS)
    if erreurs:
        return format_, erreurs, []
    return (format_, *coherence(doc))


# --- Vérification des preuves ------------------------------------------------


def normaliser(texte):
    return " ".join(texte.split())


def extrait_present(extrait, texte):
    """L'extrait, aux espaces près, figure-t-il dans le texte ? *** y vaut n'importe
    quelle suite non vide de caractères."""
    morceaux = [re.escape(m) for m in normaliser(extrait).split(MASQUE)]
    return re.search(".+?".join(morceaux), normaliser(texte), re.S) is not None


def _fichier_du_depot(depot: Path, relatif: str):
    """Résout un chemin cité sans jamais sortir du dépôt, liens symboliques compris."""
    racine = depot.resolve()
    try:
        chemin = (racine / relatif).resolve()
    except (OSError, RuntimeError):  # boucle de liens symboliques
        return None, "chemin illisible"
    if not chemin.is_relative_to(racine):
        return None, "chemin hors du dépôt"
    if not chemin.is_file():
        return None, "fichier absent"
    if chemin.stat().st_size > TAILLE_FICHIER_MAX:
        return None, "fichier trop gros"
    return chemin, None


def _lignes(chemin):
    return chemin.read_text(encoding="utf-8", errors="replace").splitlines()


def _verifier_code(depot, p):
    chemin, err = _fichier_du_depot(depot, p["fichier"])
    if err:
        return False, err
    lignes = _lignes(chemin)
    debut, fin = p["lignes"]
    if fin > len(lignes):
        return False, f"le fichier n'a que {len(lignes)} lignes"
    if not extrait_present(p["extrait"], "\n".join(lignes[debut - 1 : fin])):
        return False, "extrait absent des lignes citées"
    return True, None


def _ids_du_fichier(valeur):
    if isinstance(valeur, dict):
        if isinstance(valeur.get("id"), str):
            yield valeur["id"]
        for v in valeur.values():
            yield from _ids_du_fichier(v)
    elif isinstance(valeur, list):
        for v in valeur:
            yield from _ids_du_fichier(v)


def _verifier_dossier(depot, p):
    chemin, err = _fichier_du_depot(depot, p["fichier"])
    if err:
        return False, err
    try:
        contenu = charger(chemin)
    except (ErreurFormat, OSError):
        return False, "fichier du dossier illisible"
    if "element" in p and p["element"] not in set(_ids_du_fichier(contenu)):
        return False, f"élément {p['element']} absent"
    if "champ" in p and not (isinstance(contenu, dict) and p["champ"] in contenu):
        return False, f"section {p['champ']} absente"
    return True, None


def _nom_paquet(nom):
    return re.sub(r"[-_.]+", "-", nom.lower())


def _verifier_dependance(depot, p):
    if "fichier" not in p:
        return None, "pas de fichier cité"
    chemin, err = _fichier_du_depot(depot, p["fichier"])
    if err:
        return False, err
    if "ligne" not in p:
        texte = "\n".join(_lignes(chemin))
    else:
        lignes = _lignes(chemin)
        if p["ligne"] > len(lignes):
            return False, f"le fichier n'a que {len(lignes)} lignes"
        texte = lignes[p["ligne"] - 1]
    if _nom_paquet(p["paquet"]) not in _nom_paquet(texte):
        return False, "paquet absent de l'emplacement cité"
    return True, None


VERIFICATEURS = {"code": _verifier_code, "dossier": _verifier_dossier, "dependance": _verifier_dependance}


def verifier(doc, depot: Path):
    """Pour chaque constat : (id, statut, détails). Statut : verifie si toutes les
    preuves vérifiables le sont, refute si l'une est fausse, non_verifiable sinon."""
    resultats = []
    for c in doc["constats"]:
        details, ok, ko = [], 0, 0
        for i, p in enumerate(c["preuves"]):
            fonction = VERIFICATEURS.get(p["type"])
            res, raison = fonction(depot, p) if fonction else (None, f"preuve {p['type']} non vérifiable ici")
            if res is True:
                ok += 1
            elif res is False:
                ko += 1
                details.append(f"preuve {i + 1} ({p['type']}) : {raison}")
            else:
                details.append(f"preuve {i + 1} ({p['type']}) : {raison}")
        statut = "refute" if ko else ("verifie" if ok else "non_verifiable")
        resultats.append((c["id"], statut, details))
    return resultats


def commit_du_depot(depot: Path):
    """SHA de HEAD lu directement dans .git, sans lancer git sur un dépôt non fiable.
    None si DEPOT n'est pas la racine d'un dépôt git ou si HEAD est introuvable."""
    git = depot / ".git"
    if not (git / "HEAD").is_file():
        return None
    head = (git / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    if re.fullmatch(r"[0-9a-f]{40}", head):
        return head
    m = re.fullmatch(r"ref: (refs/[A-Za-z0-9._/-]+)", head)
    if not m or ".." in m.group(1):
        return None
    ref = git / m.group(1)
    if ref.is_file():
        sha = ref.read_text(encoding="utf-8", errors="replace").strip()
        return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    packed = git / "packed-refs"
    if packed.is_file():
        for ligne in packed.read_text(encoding="utf-8", errors="replace").splitlines():
            morceaux = ligne.split()
            if len(morceaux) == 2 and morceaux[1] == m.group(1) and re.fullmatch(r"[0-9a-f]{40}", morceaux[0]):
                return morceaux[0]
    return None


# --- Comparaison avec un corrigé ---------------------------------------------


def _destination(attendue, obtenue):
    attendue, obtenue = attendue.lower().rstrip("."), obtenue.lower().rstrip(".")
    if attendue.startswith("*."):
        return obtenue.endswith(attendue[1:])
    return attendue == obtenue


def preuves_correspondent(a, b):
    if a["type"] != b["type"]:
        return False
    t = a["type"]
    if t in ("code", "historique"):
        if a["fichier"] != b["fichier"]:
            return False
        if "lignes" not in a or "lignes" not in b:
            return True
        return a["lignes"][0] <= b["lignes"][1] + TOLERANCE_LIGNES and b["lignes"][0] <= a["lignes"][1] + TOLERANCE_LIGNES
    if t == "dossier":
        if a["fichier"] != b["fichier"]:
            return False
        return not ("element" in a and "element" in b) or a["element"] == b["element"]
    if t == "dependance":
        return a["ecosysteme"] == b["ecosysteme"] and _nom_paquet(a["paquet"]) == _nom_paquet(b["paquet"])
    if t == "reseau":
        return _destination(a["destination"], b["destination"])
    if t == "absence":
        return normaliser(a["attendu"]).lower() == normaliser(b["attendu"]).lower()
    return False


def meme_emplacement(a, b):
    return any(preuves_correspondent(pa, pb) for pa in a["preuves"] for pb in b["preuves"])


def comparer(attendu, rapports):
    """Mesure des rapports contre un corrigé. Un constat attendu est détecté si un
    constat obtenu a la même catégorie et au moins une preuve correspondante. Il est
    hors périmètre si aucun des contrôles des rapports n'est censé le trouver."""
    controles = {r["controle"] for r in rapports}
    obtenus = [(r["controle"], c) for r in rapports for c in r["constats"]]
    apparies = set()
    res = {"controles": sorted(controles), "detectes": [], "manques": [], "hors_perimetre": [], "supplementaires": []}
    for e in attendu["constats"]:
        trouves = [(i, ctl, c) for i, (ctl, c) in enumerate(obtenus)
                   if c["categorie"] == e["categorie"] and meme_emplacement(e, c)]
        apparies.update(i for i, _, _ in trouves)
        if trouves:
            res["detectes"].append({
                "attendu": e["id"],
                "par": [f"{ctl}:{c['id']}" for _, ctl, c in trouves],
                "severites": sorted({c["severite"] for _, _, c in trouves}),
                "severite_attendue": e["severite"],
            })
        elif not set(e["detecte_par"]) & controles:
            res["hors_perimetre"].append(e["id"])
        else:
            voisins = [f"{ctl}:{c['id']} ({c['categorie']})" for ctl, c in obtenus if meme_emplacement(e, c)]
            res["manques"].append({"attendu": e["id"], "autre_categorie": voisins})
    for i, (ctl, c) in enumerate(obtenus):
        if i not in apparies:
            res["supplementaires"].append(f"{ctl}:{c['id']} ({c['categorie']}, {c['severite']})")
    return res


# --- Ligne de commande -------------------------------------------------------


def _charger_valide(chemin, formats=FORMATS):
    doc = charger(Path(chemin))
    format_, erreurs, _ = valider_document(doc)
    if erreurs or format_ not in formats:
        raise ErreurFormat(f"{chemin} : non valide, lancer d'abord « constats.py valider »")
    return doc


def _cmd_valider(args):
    code = 0
    for fichier in args.fichiers:
        _, erreurs, avert = valider_document(charger(Path(fichier)))
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


def _cmd_verifier(args):
    doc = _charger_valide(args.fichier)
    depot = Path(args.depot)
    if not depot.is_dir():
        raise ErreurFormat(f"{depot} : pas un répertoire")
    if "commit" in doc:
        sha = commit_du_depot(depot)
        if sha is None:
            print(f"commit non contrôlé : {depot} n'est pas la racine d'un dépôt git lisible")
        elif sha != doc["commit"]:
            print(f"✗ le dépôt est à {sha}, le rapport porte sur {doc['commit']}")
            return 1
    code = 0
    symboles = {"verifie": "✓", "refute": "✗", "non_verifiable": "?"}
    for id_, statut, details in verifier(doc, depot):
        if statut == "refute":
            code = 1
        print(f"{symboles[statut]} {id_} : {statut.replace('_', ' ')}")
        for d in details:
            print(f"  {d}")
    return code


def _cmd_comparer(args):
    attendu = _charger_valide(args.attendu, ("raton/attendu/v0",))
    rapports = [_charger_valide(r, ("raton/rapport/v0",)) for r in args.rapports]
    res = comparer(attendu, rapports)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print(f"contrôles : {', '.join(res['controles'])}")
    for d in res["detectes"]:
        ecart = "" if d["severites"] == [d["severite_attendue"]] else f" ; sévérité {'/'.join(d['severites'])}, attendue {d['severite_attendue']}"
        print(f"✓ {d['attendu']} détecté par {', '.join(d['par'])}{ecart}")
    for m in res["manques"]:
        voisins = f" ; même emplacement, autre catégorie : {', '.join(m['autre_categorie'])}" if m["autre_categorie"] else ""
        print(f"✗ {m['attendu']} manqué{voisins}")
    for h in res["hors_perimetre"]:
        print(f"· {h} hors du périmètre de ces contrôles")
    for s in res["supplementaires"]:
        print(f"+ {s} : non attendu (faux positif ou constat réel non prévu)")
    attendus = len(res["detectes"]) + len(res["manques"])
    if attendus:
        print(f"{len(res['detectes'])}/{attendus} constats attendus détectés")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="constats.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("valider", help="valider des rapports ou des corrigés")
    p.add_argument("fichiers", nargs="+")
    p.set_defaults(func=_cmd_valider)
    p = sous.add_parser("verifier", help="vérifier les preuves dans le dépôt")
    p.add_argument("fichier")
    p.add_argument("--depot", required=True, help="racine du dépôt relu, au commit du rapport")
    p.set_defaults(func=_cmd_verifier)
    p = sous.add_parser("comparer", help="comparer des rapports à un corrigé du corpus")
    p.add_argument("attendu")
    p.add_argument("rapports", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_comparer)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
