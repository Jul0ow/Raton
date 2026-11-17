#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Note de l'application : calculée à la fin de la revue, à partir des rapports de contrôle.

  note.py noter FICHE RAPPORT… [--json]   note sur 100 et lettre de A à E, points à gagner

La note dit au métier ce qu'il lui reste à améliorer, et ce que chaque correction lui
rapporte. Elle se calcule par la règle ci-dessous, publique et déterministe : personne ne
la choisit. Elle ne décide pas de la mise en production, qui relève de l'avis signé.

Les rapports peuvent venir d'un agent : ce sont des données non fiables, que le script
ne fait qu'analyser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import constats
import qualification
from raton_formats import ErreurFormat, charger, md_inerte

FORMAT = "raton/note/v0"

# --- Règle ---------------------------------------------------------------------
# Validée le 2026-11-17 : voir docs/formats/note.md. Toute
# modification change la note de toutes les applications.

POINTS_PAR_AXE = 20

# (axe, libellé pour le métier, catégories de constats qui lui retirent des points)
AXES = (
    ("dossier", "Dossier fidèle", ("dossier_inexact", "dossier_incomplet", "declaration_non_realisee")),
    ("intention", "Conforme à l'intention", ("flux_non_declare", "donnees_non_declarees", "fonction_non_decrite", "exclusion_violee")),
    ("code", "Code sûr", (
        "vulnerabilite", "controle_acces", "secret_expose", "code_malveillant", "obfuscation",
        "declencheur_conditionnel", "injection_relecteurs", "autre",
    )),
    ("dependances", "Dépendances saines", ("dependance_vulnerable", "dependance_suspecte", "script_installation", "version_non_epinglee", "licence")),
    ("production", "Prête pour la production", ("deploiement", "exploitabilite", "non_conformite_si")),
)
AXE_DE = {cat: axe for axe, _, cats in AXES for cat in cats}
LIBELLE_AXE = {axe: lib for axe, lib, _ in AXES}

COUT = {"critique": 20, "haute": 10, "moyenne": 5, "basse": 2, "info": 0}
ORDRE_SEVERITE = ("critique", "haute", "moyenne", "basse", "info")

# Lettre selon le total, puis plafond selon le constat le plus grave.
SEUILS = ((90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "E"))
PLAFOND = {"critique": "E", "haute": "C"}
LETTRES = "ABCDE"

# Un soupçon à confirmer ne coûte rien tant qu'un humain ne l'a pas confirmé.
CONFIANCES_COMPTEES = ("elevee", "moyenne")

# Pour le rendu : « 1 constat haut », « 3 constats hauts ».
_SEV_ADJ = {"critique": ("critique", "critiques"), "haute": ("haut", "hauts"), "moyenne": ("moyen", "moyens"),
            "basse": ("bas", "bas"), "info": ("info", "info")}


def lettre_du_total(total):
    return next(lettre for seuil, lettre in SEUILS if total >= seuil)


def lettre_et_plafond(total, severites):
    """Lettre du total, abaissée au plafond du constat le plus grave."""
    lettre = lettre_du_total(total)
    for sev in ORDRE_SEVERITE:
        if sev in severites and sev in PLAFOND:
            return max(lettre, PLAFOND[sev], key=LETTRES.index), {"lettre": PLAFOND[sev], "severite": sev}
    return lettre, None


# --- Calcul --------------------------------------------------------------------


def prefixes(rapports):
    """Désignation unique de chaque rapport : son contrôle, suivi du numéro de passe pour
    un agent (revue_informee#2), et d'un rang si deux rapports se confondent encore."""
    res, vus = [], {}
    for r in rapports:
        base = r["controle"] + (f"#{r['producteur']['passe']}" if "passe" in r["producteur"] else "")
        vus[base] = vus.get(base, 0) + 1
        res.append(base if vus[base] == 1 else f"{base}~{vus[base]}")
    return res


def regrouper(rapports):
    """Constats des rapports, un même problème trouvé par plusieurs rapports (contrôles
    ou passes) ne comptant qu'une fois : même catégorie et au moins une preuve qui
    correspond, la règle de la mesure sur le corpus. Deux constats d'un même rapport ne
    sont jamais fusionnés : son producteur les a distingués. Le groupe prend la sévérité
    la plus haute et la confiance la plus haute de ses membres."""
    items = [(i, f"{p}:{c['id']}", c) for i, (p, r) in enumerate(zip(prefixes(rapports), rapports)) for c in r["constats"]]
    parent = list(range(len(items)))

    def racine(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a in range(len(items)):
        for b in range(a):
            (ra, _, ca), (rb, _, cb) = items[a], items[b]
            if ra != rb and ca["categorie"] == cb["categorie"] and constats.meme_emplacement(ca, cb):
                parent[racine(a)] = racine(b)
    groupes = {}
    for k in range(len(items)):
        groupes.setdefault(racine(k), []).append(k)
    res = []
    for membres in sorted(groupes.values(), key=min):
        tete = min(membres, key=lambda k: (ORDRE_SEVERITE.index(items[k][2]["severite"]), k))
        c = items[tete][2]
        res.append({
            "ref": items[tete][1],
            "aussi": [items[k][1] for k in membres if k != tete],
            "categorie": c["categorie"],
            "severite": c["severite"],
            "confiance": min((items[k][2]["confiance"] for k in membres), key=("elevee", "moyenne", "faible").index),
            "titre": c["titre"],
        })
    return res


def bareme(comptes):
    """Points par axe et total, pour une liste de constats comptés."""
    points = {axe: POINTS_PAR_AXE for axe, _, _ in AXES}
    for c in comptes:
        points[AXE_DE[c["categorie"]]] -= COUT[c["severite"]]
    points = {axe: max(0, p) for axe, p in points.items()}
    total = round(100 * sum(points.values()) / (POINTS_PAR_AXE * len(AXES)))
    lettre, plafond = lettre_et_plafond(total, {c["severite"] for c in comptes})
    return points, total, lettre, plafond


def prochaine_lettre(comptes, lettre):
    """Les constats à corriger pour gagner au moins une lettre : on retire les plus
    graves d'abord, jusqu'à ce que la lettre monte."""
    if lettre == "A":
        return None
    restants = sorted(comptes, key=lambda c: ORDRE_SEVERITE.index(c["severite"]))
    corriges = []
    while restants:
        corriges.append(restants.pop(0))
        _, total, nouvelle, _ = bareme(restants)
        if LETTRES.index(nouvelle) < LETTRES.index(lettre):
            return {"lettre": nouvelle, "total": total, "corriger": [c["ref"] for c in corriges]}
    return None


def noter(fiche, rapports):
    """Note de l'application au commit des rapports. Renvoie un document raton/note/v0."""
    if not rapports:
        raise ErreurFormat("aucun rapport : la note se calcule sur les rapports de contrôle")
    commits = sorted({r["commit"] for r in rapports})
    if len(commits) > 1:
        raise ErreurFormat(f"rapports sur plusieurs commits ({', '.join(c[:7] for c in commits)}) : une note porte sur un seul")
    groupes = regrouper(rapports)
    comptes, non_comptes = [], []
    for c in groupes:
        if c["confiance"] not in CONFIANCES_COMPTEES:
            non_comptes.append(dict(c, motif="confiance faible : soupçon à confirmer"))
        elif COUT[c["severite"]] == 0:
            non_comptes.append(dict(c, motif="information, sans coût"))
        else:
            comptes.append(dict(c, axe=AXE_DE[c["categorie"]], cout=COUT[c["severite"]]))
    points, total, lettre, plafond = bareme(comptes)
    exigences = fiche["exigences"]
    faits = {r["controle"] for r in rapports}
    manquants = [c for c in exigences["controles"] if c not in faits]
    return {
        "format": FORMAT,
        "application": fiche["application"]["code"],
        "commit": commits[0],
        "palier": exigences["palier"],
        "total": total,
        "lettre": lettre,
        "plafond": plafond,
        "provisoire": bool(manquants),
        "controles_manquants": manquants,
        "axes": [
            {"axe": axe, "points": points[axe], "constats": [c["ref"] for c in comptes if c["axe"] == axe]}
            for axe, _, _ in AXES
        ],
        "constats": comptes,
        "non_comptes": non_comptes,
        "prochaine_lettre": prochaine_lettre(comptes, lettre),
    }


# --- Rendu ---------------------------------------------------------------------


def _compte(severites):
    parts = [f"{n} {_SEV_ADJ[sev][n > 1]}" for sev in ORDRE_SEVERITE if (n := severites.count(sev))]
    return ", ".join(parts) or "aucun"


def rendre(note, nom=None):
    """Rendu Markdown pour le métier : la note, d'où elle vient, comment la monter."""
    par_ref = {c["ref"]: c for c in note["constats"]}
    titre = f"{md_inerte(nom)} : note {note['lettre']}" if nom else f"Note {note['lettre']}"
    lignes = [
        f"# {titre}{' (provisoire)' if note['provisoire'] else ''}",
        "",
        f"**{note['total']}/100** · palier {note['palier']} · commit `{note['commit'][:12]}`",
        "",
        "> La note mesure ce qu'il reste à améliorer d'après les contrôles. Elle ne décide pas "
        "de la mise en production : c'est l'avis, signé par le change manager.",
    ]
    if note["provisoire"]:
        lignes += [
            ">",
            f"> **Provisoire** : {len(note['controles_manquants'])} contrôle(s) obligatoire(s) sans rapport "
            f"({', '.join(note['controles_manquants'])}). Ce qu'ils trouveront peut faire baisser la note.",
        ]
    lignes += ["", "| Axe | Points | Constats comptés |", "|---|---|---|"]
    for a in note["axes"]:
        sev = [par_ref[r]["severite"] for r in a["constats"]]
        lignes.append(f"| {LIBELLE_AXE[a['axe']]} | {a['points']}/{POINTS_PAR_AXE} | {_compte(sev)} |")
    if note["plafond"] and note["lettre"] != lettre_du_total(note["total"]):
        p = note["plafond"]
        lignes += ["", f"Au moins un constat {_SEV_ADJ[p['severite']][0]} : la note ne peut pas dépasser {p['lettre']}, quel que soit le total."]

    lignes += ["", "## Pour gagner des points", ""]
    prochaine = note["prochaine_lettre"]
    if note["lettre"] == "A":
        lignes.append("La note est au maximum. Chaque nouvelle version repasse la revue : il s'agit de la garder.")
    elif prochaine is None:
        lignes.append("Aucun constat compté : la note ne peut monter qu'avec les contrôles qui manquent.")
    else:
        n = len(prochaine["corriger"])
        lignes.append(
            f"Corriger {'ce constat' if n == 1 else f'ces {n} constats'} fait passer la note de "
            f"{note['lettre']} à {prochaine['lettre']} ({prochaine['total']}/100) :"
        )
        lignes.append("")
        for ref in prochaine["corriger"]:
            c = par_ref[ref]
            lignes.append(f"- **{ref}** ({_SEV_ADJ[c['severite']][0]}, {LIBELLE_AXE[c['axe']]}) : {md_inerte(c['titre'])}")
    if note["constats"]:
        lignes += [
            "",
            "## Constats comptés",
            "",
            "Un constat corrigé rend ses points à la version suivante. Un même problème trouvé par plusieurs contrôles ne compte qu'une fois.",
            "",
            "| Constat | Axe | Sévérité | Coût | Trouvé aussi par |",
            "|---|---|---|---|---|",
        ]
        for c in sorted(note["constats"], key=lambda c: (-c["cout"], c["ref"])):
            lignes.append(
                f"| {c['ref']} : {md_inerte(c['titre'])} | {LIBELLE_AXE[c['axe']]} | {c['severite']} | −{c['cout']} | {', '.join(c['aussi']) or '—'} |"
            )
    if note["non_comptes"]:
        lignes += ["", "## Non comptés", ""]
        for c in note["non_comptes"]:
            lignes.append(f"- {c['ref']} : {md_inerte(c['titre'])} ({c['motif']})")
    return "\n".join(lignes) + "\n"


# --- Ligne de commande ---------------------------------------------------------


def charger_fiche(chemin):
    fiche = charger(chemin)
    erreurs, _ = qualification.valider_document(fiche)
    if erreurs:
        raise ErreurFormat(f"{chemin} : fiche non valide, lancer d'abord « qualification.py valider »")
    if "validation" not in fiche:
        raise ErreurFormat(f"{chemin} : fiche non validée par l'équipe DevOps ; la note s'appuie sur ses contrôles obligatoires")
    return fiche


def _cmd_noter(args):
    fiche = charger_fiche(Path(args.fiche))
    rapports = [constats._charger_valide(r, ("raton/rapport/v0",)) for r in args.rapports]
    note = noter(fiche, rapports)
    if args.json:
        print(json.dumps(note, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(rendre(note, fiche["application"]["nom"]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="note.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("noter", help="noter l'application à partir de sa fiche et des rapports d'un commit")
    p.add_argument("fiche", help="fiche de qualification validée")
    p.add_argument("rapports", nargs="+", help="rapports de contrôle, tous sur le même commit")
    p.add_argument("--json", action="store_true", help="document raton/note/v0, à conserver avec l'avis")
    p.set_defaults(func=_cmd_noter)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
