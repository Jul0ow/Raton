#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Fiche de qualification : validation, calcul du palier d'exigence, rendu lisible.

  qualification.py valider FICHE [--intention INTENTION]   schéma, règles et recoupements avec l'intention
  qualification.py calculer FICHE                          palier calculé et contrôles obligatoires
  qualification.py rendre FICHE                            rendu Markdown, pour le métier et l'équipe infra

Le palier ne se décide pas : il se calcule par la règle ci-dessous, publique et
déterministe. L'équipe infra peut le relever, jamais l'abaisser. La fiche est une
donnée non fiable : le script ne fait que l'analyser.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from raton_formats import ErreurFormat, charger, doublons, erreurs_schema, md_inerte

FORMAT = "raton/qualification/v0"

# --- Politique ---------------------------------------------------------------
# Règle par défaut, à aligner sur la PSSI de l'entreprise : voir
# docs/formats/qualification.md. Toute modification change le palier exigé.

PALIER_UTILISATEURS = {"interne": 1, "externe": 2, "public": 3}
PALIER_DONNEES = {"non": 1, "oui": 2, "sensibles": 3}
PALIER_DICP = {1: 1, 2: 1, 3: 2, 4: 3}
# Interconnexions : seuls comptent les droits, la sensibilité du système cible et la
# zone ; le nombre de systèmes n'intervient pas. Une zone externe compte comme une
# exposition externe. Ce qui reste à vérifier compte au plus haut.
PALIER_ACCES = {  # (accès, système sensible) → palier
    ("lecture", False): 1,
    ("lecture", True): 2,
    ("ecriture", False): 2,
    ("ecriture", True): 3,
    ("administration", False): 3,
    ("administration", True): 3,
}
PALIER_MAX = 3
NOMS_PALIERS = {1: "socle", 2: "renforcé", 3: "élevé"}

# (contrôle, palier à partir duquel il est obligatoire, libellé), dans l'ordre du pipeline
CONTROLES = (
    ("dat", 1, "Cohérence du DAT, intention et technique"),
    ("matrice_flux", 1, "Matrice de flux"),
    ("exploitation", 1, "Dossier d'exploitation"),
    ("palier_kubernetes", 1, "Palier de déployabilité Kubernetes"),
    ("chaine_approvisionnement", 1, "Chaîne d'approvisionnement"),
    ("secrets", 1, "Secrets et configuration"),
    ("identite_acces", 1, "Identité et accès"),
    ("sast", 1, "Analyse statique du code (SAST)"),
    ("revue_informee", 1, "Revue informée par agents, en plusieurs passes"),
    ("juge", 1, "Juge : comparaison des passes et des relecteurs"),
    ("revue_aveugle", 2, "Revue aveugle par agents"),
    ("analyse_dynamique", 3, "Analyse dynamique en bac à sable"),
)

AXES = (
    ("disponibilite", "Disponibilité"),
    ("integrite", "Intégrité"),
    ("confidentialite", "Confidentialité"),
    ("preuve", "Preuve"),
)
ECHELLE = {
    "disponibilite": {
        1: "plusieurs jours d'arrêt supportables",
        2: "une journée d'arrêt au plus",
        3: "quelques heures d'arrêt au plus",
        4: "moins d'une heure d'arrêt",
    },
    "integrite": {
        1: "erreur sans conséquence",
        2: "erreur gênante, vite corrigée",
        3: "erreur aux conséquences importantes",
        4: "erreur aux conséquences graves",
    },
    "confidentialite": {
        1: "informations publiques",
        2: "usage interne",
        3: "confidentiel, accès restreint",
        4: "secret",
    },
    "preuve": {
        1: "aucun besoin de traces",
        2: "traces utiles au diagnostic",
        3: "traces exigées pour un contrôle",
        4: "traces à valeur probante",
    },
}


def controles_obligatoires(palier):
    return [c for c, p, _ in CONTROLES if p <= palier]


def palier_interconnexion(i):
    acces = "administration" if i["acces"] == "a_verifier" else i["acces"]
    return PALIER_ACCES[(acces, i["sensible"] != "non")]


def zone_externe(i):
    return i["zone"] != "interne"


def a_verifier(i):
    return [c for c in ("zone", "nature", "acces", "sensible") if i[c] == "a_verifier"]


@dataclass
class Calcul:
    palier: int
    base: int  # avant l'exposition externe
    criteres: list  # (critère, réponse, palier)
    causes_externes: list  # « exposition » et identifiants des interconnexions externes

    @property
    def externe(self):
        return bool(self.causes_externes)


def calculer(fiche):
    """Palier calculé : le plus élevé des critères, plus un en cas d'exposition externe
    (accès depuis un réseau extérieur ou interconnexion avec un tel réseau), sans
    dépasser le palier maximal."""
    pop = fiche["utilisateurs"]["populations"]
    niveau = fiche["donnees_personnelles"]["niveau"]
    criteres = [
        ("Utilisateurs", ", ".join(pop), max(PALIER_UTILISATEURS[p] for p in pop)),
        ("Données personnelles", niveau, PALIER_DONNEES[niveau]),
    ]
    inter = fiche["interconnexions"]
    p_inter = max((palier_interconnexion(i) for i in inter), default=1)
    determinantes = [i["id"] for i in inter if palier_interconnexion(i) == p_inter]
    criteres.append(("Interconnexions", ", ".join(determinantes) or "aucune", p_inter))
    for axe, libelle in AXES:
        n = fiche["dicp"][axe]["niveau"]
        criteres.append((libelle, n, PALIER_DICP[n]))
    base = max(p for *_, p in criteres)
    causes = (["exposition"] if fiche["exposition"] == "externe" else []) + [i["id"] for i in inter if zone_externe(i)]
    return Calcul(min(PALIER_MAX, base + 1) if causes else base, base, criteres, causes)


# --- Validation --------------------------------------------------------------


def _meme_nom(a, b):
    def norm(s):
        return " ".join(s.split()).casefold()

    return norm(a) == norm(b)


def coherence(fiche):
    """Règles que le schéma ne peut pas porter. Renvoie (erreurs, avertissements)."""
    erreurs, avert = [], []
    validee = "validation" in fiche

    if "public" in fiche["utilisateurs"]["populations"] and fiche["exposition"] != "externe":
        erreurs.append("utilisateurs : un public sans compte suppose une exposition externe")

    erreurs += doublons("interconnexions", fiche["interconnexions"])
    for i in fiche["interconnexions"]:
        champs = a_verifier(i)
        if champs and validee:
            erreurs.append(f"interconnexion {i['id']} : {', '.join(champs)} à vérifier ; une fiche validée ne peut pas laisser ce point ouvert")
        elif champs:
            avert.append(f"interconnexion {i['id']} : {', '.join(champs)} à vérifier par l'équipe infra ; compté au plus haut en attendant")

    dp = fiche["donnees_personnelles"]
    conf = fiche["dicp"]["confidentialite"]["niveau"]
    if dp["niveau"] == "oui" and conf < 2:
        avert.append("confidentialité 1 (informations publiques) alors que l'application traite des données personnelles : à confirmer")
    if dp["niveau"] == "sensibles":
        if conf < 3:
            avert.append("confidentialité inférieure à 3 alors que l'application traite des données sensibles : à confirmer")
        avert.append("données sensibles : vérifier avec le DPO si une analyse d'impact (AIPD) est requise")

    calc = calculer(fiche)
    ex = fiche.get("exigences")
    if ex is None:
        avert.append("exigences absentes : « calculer » donne le palier et les contrôles obligatoires")
    else:
        if ex["palier"] < calc.palier:
            erreurs.append(f"exigences : palier {ex['palier']} inférieur au palier calculé {calc.palier}")
        requis = controles_obligatoires(max(ex["palier"], calc.palier))
        manquants = [c for c in requis if c not in ex["controles"]]
        if manquants:
            erreurs.append(f"exigences : contrôles obligatoires absents : {', '.join(manquants)}")
        au_dela = ex["palier"] > calc.palier or set(ex["controles"]) - set(requis)
        if au_dela and "justification" not in ex:
            erreurs.append("exigences : au-delà du minimum calculé, une justification est obligatoire")

    if validee:
        v = fiche["validation"]
        noms_metier = (v["renseigne_par"]["nom"], fiche["application"]["porteur"]["nom"])
        if any(_meme_nom(v["valide_par"]["nom"], n) for n in noms_metier):
            erreurs.append("validation : la fiche est validée par l'équipe infra, pas par le métier qui l'a renseignée")
    else:
        avert.append("brouillon : pas de section validation, le pipeline ne peut pas s'appuyer sur cette fiche")
    return erreurs, avert


_ORDRE_DONNEES = {"non": 0, "oui": 1, "sensibles": 2}


def recoupements(fiche, intention):
    """Ce que l'intention atteste et que la fiche sous-évalue : chaque écart est une
    erreur, car la qualification choisit les contrôles et borne les droits. Renvoie
    (erreurs, avertissements)."""
    res, avert = [], []
    externes = [p["id"] for p in intention["profils"] if p["population"] == "externe"]
    if externes and not set(fiche["utilisateurs"]["populations"]) & {"externe", "public"}:
        res.append(
            f"utilisateurs : l'intention déclare des profils externes ({', '.join(externes)}), "
            "la fiche seulement des utilisateurs internes"
        )
    niveau_q = fiche["donnees_personnelles"]["niveau"]
    niveau_i = max((d["personnelles"] for d in intention["donnees"]), key=_ORDRE_DONNEES.get, default="non")
    if _ORDRE_DONNEES[niveau_i] > _ORDRE_DONNEES[niveau_q]:
        ids = [d["id"] for d in intention["donnees"] if d["personnelles"] == niveau_i]
        res.append(
            f"données personnelles : l'intention en déclare de niveau « {niveau_i} » ({', '.join(ids)}), "
            f"la fiche « {niveau_q} »"
        )

    inter = {i["id"]: i for i in fiche["interconnexions"]}
    citees = set()
    for e in intention["echanges"]:
        nom = f"échange {e['id']} ({e['partenaire']})"
        refs = e.get("interconnexions", [])
        citees.update(refs)
        if not refs:
            res.append(f"{nom} : ne renvoie à aucune interconnexion de la fiche")
        for r in refs:
            if r not in inter:
                res.append(f"{nom} : renvoie à {r}, absente de la fiche")
        connues = [inter[r] for r in refs if r in inter]
        if e["sens"] != "recoit" and connues and all(i["acces"] == "lecture" for i in connues):
            res.append(f"{nom} : l'application envoie des données par {', '.join(i['id'] for i in connues)}, que la fiche déclare en lecture seule")
    for i in fiche["interconnexions"]:
        if i["id"] not in citees:
            avert.append(
                f"interconnexion {i['id']} ({i['systeme']}) : aucun échange de l'intention ne la cite ; "
                "si elle ne sert pas, elle ne doit pas recevoir de droits"
            )
    return res, avert


def valider_document(fiche, intention=None):
    """Renvoie (erreurs, avertissements)."""
    _, erreurs = erreurs_schema(fiche, (FORMAT,))
    if erreurs:  # les règles supposent une fiche conforme au schéma
        return erreurs, []
    erreurs, avert = coherence(fiche)
    if intention is not None:
        err_r, av_r = recoupements(fiche, intention)
        erreurs, avert = erreurs + err_r, avert + av_r
    return erreurs, avert


def charger_intention(chemin):
    intention = charger(chemin)
    _, erreurs = erreurs_schema(intention, ("raton/intention/v0",))
    if erreurs:
        raise ErreurFormat(f"{chemin} : intention non valide, lancer d'abord « dossier.py valider »")
    return intention


# --- Rendu lisible -----------------------------------------------------------


_EXPOSITION = {"interne": "réseau de l'entreprise seulement", "externe": "réseau extérieur à l'entreprise"}
_POPULATIONS = {"interne": "salariés", "externe": "personnes extérieures identifiées", "public": "public sans compte"}
_DONNEES = {"non": "aucune, hors identité des utilisateurs", "oui": "oui", "sensibles": "oui, dont des données sensibles"}
_VALEURS = {  # libellés des valeurs des interconnexions
    "a_verifier": "à vérifier",
    "ecriture": "écriture",
    "api": "API",
    "base_de_donnees": "base de données",
}


def _valeur(v):
    return _VALEURS.get(v, v)


def _causes_externes(calc):
    causes = ["accès depuis l'extérieur" if c == "exposition" else f"interconnexion {c}" for c in calc.causes_externes]
    return ", ".join(causes)


def _palier(p):
    return f"{p} ({NOMS_PALIERS[p]})"


def rendre(fiche):
    app, val, ex = fiche["application"], fiche.get("validation"), fiche.get("exigences")
    calc = calculer(fiche)
    paliers = {critere: p for critere, _, p in calc.criteres}

    lignes = [f"# {md_inerte(app['nom'])} — qualification", ""]
    if val is None:
        lignes += ["> **Brouillon, non validé par l'équipe infra.**", ""]
    lignes += [
        md_inerte(app["objet"]),
        "",
        f"- Code : {app['code']}",
        f"- Porteur métier : {md_inerte(app['porteur']['nom'])} ({md_inerte(app['porteur']['entite'])})",
    ]
    if "depot" in app:
        lignes.append(f"- Dépôt : {md_inerte(app['depot'])}")

    u, dp = fiche["utilisateurs"], fiche["donnees_personnelles"]
    donnees = _DONNEES[dp["niveau"]]
    if dp["niveau"] != "non":
        personnes = ", ".join(md_inerte(p) for p in dp["personnes"])
        donnees += f" ; {personnes} ; environ {dp['volume']} personnes"
    lignes += [
        "",
        "## Exposition, utilisateurs et données",
        "",
        "| Critère | Réponse | Palier |",
        "|---|---|---|",
        f"| Exposition | {_EXPOSITION[fiche['exposition']]} | {'un palier de plus' if fiche['exposition'] == 'externe' else '—'} |",
        f"| Utilisateurs | {', '.join(_POPULATIONS[p] for p in u['populations'])} ; environ {u['effectif']} | {paliers['Utilisateurs']} |",
        f"| Données personnelles | {donnees} | {paliers['Données personnelles']} |",
    ]

    lignes += ["", "## Interconnexions", ""]
    inter = fiche["interconnexions"]
    if inter:
        lignes += [
            "| Système | Usage | Zone | Nature | Accès | Système sensible | Palier |",
            "|---|---|---|---|---|---|---|",
        ]
        for i in inter:
            zone = _valeur(i["zone"]) + (" : un palier de plus" if zone_externe(i) else "")
            lignes.append(
                f"| {md_inerte(i['systeme'])} ({i['id']}) | {md_inerte(i['usage'])} | {zone} | {_valeur(i['nature'])} "
                f"| {_valeur(i['acces'])} | {_valeur(i['sensible'])} | {palier_interconnexion(i)} |"
            )
        if any(a_verifier(i) for i in inter):
            lignes += ["", "Ce qui reste à vérifier compte au plus haut : zone externe, administration, système sensible."]
    else:
        lignes.append("Aucune interconnexion avec un autre système.")

    lignes += ["", "## Besoins de sécurité (DICP)", "", "| Axe | Niveau | Motif | Palier |", "|---|---|---|---|"]
    for axe, libelle in AXES:
        b = fiche["dicp"][axe]
        lignes.append(f"| {libelle} | {b['niveau']} : {ECHELLE[axe][b['niveau']]} | {md_inerte(b['motif'])} | {paliers[libelle]} |")

    regle = "le plus élevé des critères"
    if calc.externe:
        regle += f", plus un pour l'exposition externe ({_causes_externes(calc)})"
    lignes += ["", "## Palier d'exigence", "", f"- Palier calculé : {_palier(calc.palier)}, {regle}."]
    if ex is None:
        lignes.append("- Palier retenu : pas encore fixé.")
        controles = controles_obligatoires(calc.palier)
    else:
        lignes.append(f"- Palier retenu : {_palier(ex['palier'])}.")
        if "justification" in ex:
            lignes.append(f"- Justification : {md_inerte(ex['justification'])}")
        controles = ex["controles"]

    minimum = set(controles_obligatoires(calc.palier))
    lignes += ["", "## Contrôles obligatoires", ""]
    for c, _, libelle in CONTROLES:
        if c in controles:
            lignes.append(f"- {libelle}" + ("" if c in minimum else " (au-delà du minimum)"))

    lignes += ["", "## Validation", ""]
    if val is None:
        lignes.append("Pas encore validée par l'équipe infra.")
    else:
        lignes.append(
            f"Version {val['version']}, renseignée par {md_inerte(val['renseigne_par']['nom'])} "
            f"({md_inerte(val['renseigne_par']['entite'])}), validée par {md_inerte(val['valide_par']['nom'])} "
            f"({md_inerte(val['valide_par']['entite'])}) le {val['date']}."
        )
    return "\n".join(lignes) + "\n"


# --- Ligne de commande -------------------------------------------------------


def _charger_conforme(chemin):
    fiche = charger(chemin)
    _, erreurs = erreurs_schema(fiche, (FORMAT,))
    if erreurs:
        raise ErreurFormat(f"{chemin} : non conforme au schéma, lancer d'abord « qualification.py valider »")
    return fiche


def _cmd_valider(args):
    intention = charger_intention(Path(args.intention)) if args.intention else None
    erreurs, avert = valider_document(charger(Path(args.fiche)), intention)
    print(f"{'✗' if erreurs else '✓'} {args.fiche}")
    for e in erreurs:
        print(f"  erreur : {e}")
    for a in avert:
        print(f"  avertissement : {a}")
    return 1 if erreurs else 0


def _cmd_calculer(args):
    calc = calculer(_charger_conforme(Path(args.fiche)))
    for critere, reponse, palier in calc.criteres:
        print(f"{critere} : {reponse} → palier {palier}")
    if calc.externe:
        print(f"Exposition externe : {_causes_externes(calc)} → un palier de plus")
    else:
        print("Exposition interne, aucune interconnexion externe → aucun palier de plus")
    print(f"Palier calculé : {_palier(calc.palier)}")
    print()
    print("exigences:")
    print(f"  palier: {calc.palier}")
    print(f"  controles: [{', '.join(controles_obligatoires(calc.palier))}]")
    return 0


def _cmd_rendre(args):
    sys.stdout.write(rendre(_charger_conforme(Path(args.fiche))))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="qualification.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("valider", help="valider une fiche, éventuellement contre l'intention")
    p.add_argument("fiche")
    p.add_argument("--intention", help="intention.yaml de l'application, pour les recoupements")
    p.set_defaults(func=_cmd_valider)
    p = sous.add_parser("calculer", help="palier calculé et contrôles obligatoires")
    p.add_argument("fiche")
    p.set_defaults(func=_cmd_calculer)
    p = sous.add_parser("rendre", help="rendre la fiche en Markdown")
    p.add_argument("fiche")
    p.set_defaults(func=_cmd_rendre)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
