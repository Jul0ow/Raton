#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Outils déterministes sur le dossier Raton (.raton/).

  dossier.py valider CHEMIN     valide un fichier du dossier, ou le répertoire .raton entier
                                (intention, technique et matrice de flux, références croisées comprises)
  dossier.py rendre FICHIER     rend intention.yaml en Markdown lisible, pour validation humaine ;
                                rend aussi technique.yaml : ressources, capacités, cycle de vie des données
  dossier.py ecarts REPERTOIRE  compare intention.yaml et technique.yaml par références

Les fichiers lus viennent de l'auteur : ce sont des données non fiables. Le script ne fait
que les analyser ; il n'exécute rien de ce qu'ils contiennent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import flux
from raton_formats import ErreurFormat, charger, doublons, erreurs_schema
from raton_formats import md_inerte as _cell
from raton_formats import ids as _ids

FORMATS = ("raton/intention/v0", "raton/technique/v0", flux.FORMAT)


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


def millicoeurs(quantite):
    """Quantité de processeur Kubernetes (250m, 0.5, 2) en millièmes de cœur."""
    if quantite.endswith("m"):
        return int(quantite[:-1])
    entier, _, decimales = quantite.partition(".")
    return int(entier) * 1000 + int((decimales + "000")[:3])


_MIO = {"Mi": 1, "Gi": 1024, "Ti": 1024 * 1024}


def mio(quantite):
    """Quantité de mémoire ou de stockage Kubernetes (512Mi, 2Gi, 1Ti) en Mio."""
    return int(quantite[:-2]) * _MIO[quantite[-2:]]


def _coherence_ressources(qui, r, erreurs):
    if millicoeurs(r["cpu"]) == 0 or mio(r["memoire"]) == 0:
        erreurs.append(f"{qui} : processeur et mémoire ne peuvent pas être nuls")
    if "cpu_max" in r and millicoeurs(r["cpu_max"]) < millicoeurs(r["cpu"]):
        erreurs.append(f"{qui} : cpu_max {r['cpu_max']} inférieur à cpu {r['cpu']}")
    if "memoire_max" in r and mio(r["memoire_max"]) < mio(r["memoire"]):
        erreurs.append(f"{qui} : memoire_max {r['memoire_max']} inférieure à memoire {r['memoire']}")


def coherence_technique(doc, intention=None):
    """Sans l'intention, le document peut venir du relecteur aveugle : seules comptent ses
    règles internes. Avec l'intention, c'est le dossier de l'auteur : ses références sont
    vérifiées, et ses déclarations propres (ressources, capacités, cycle de vie) exigées."""
    erreurs = []
    for section in ("composants", "stockages", "services_tiers"):
        erreurs += doublons(section, doc.get(section))
    vus = {}
    for e in doc["composants"] + doc["stockages"]:
        if "nom" in e and e["nom"] in vus:
            erreurs.append(f"{e['id']} : nom « {e['nom']} » déjà porté par {vus[e['nom']]} ; il étiquette les pods, il doit être unique")
        vus.setdefault(e.get("nom"), e["id"])
    for e in doc["composants"] + doc["stockages"]:
        if "ressources" in e:
            _coherence_ressources(e["id"], e["ressources"], erreurs)
    for s in doc["stockages"]:
        if "ressources" in s and "nom" not in s:
            erreurs.append(f"{s['id']} : des ressources sans nom ; elles ne concernent qu'un stockage déployé dans le namespace de l'application")
    cycle = doc.get("cycle_de_vie", [])
    vues = set()
    composants = set(_ids(doc["composants"]))
    for c in cycle:
        if c["donnee"] in vues:
            erreurs.append(f"cycle_de_vie : donnée {c['donnee']} décrite deux fois")
        vues.add(c["donnee"])
        _refs(f"cycle de vie de {c['donnee']}", [c["composant"]] if "composant" in c else [], composants, erreurs)
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
    _refs("cycle_de_vie", [c["donnee"] for c in cycle], donnees, erreurs)
    erreurs += manques_auteur(doc)
    return erreurs, []


def manques_auteur(doc):
    """Déclarations que seul l'auteur peut faire, et que son dossier doit porter."""
    manques = []
    for c in doc["composants"]:
        if "ressources" not in c:
            manques.append(f"composant {c['id']} : ressources non déclarées (instances, cpu, memoire)")
    for s in doc["stockages"]:
        if "capacite" not in s:
            manques.append(f"stockage {s['id']} : capacité non déclarée (initiale, par_an)")
        if "nom" in s and "ressources" not in s:
            manques.append(f"stockage {s['id']} : déployé dans le namespace, ressources non déclarées")
    conservees = {d for s in doc["stockages"] for d in s.get("donnees", [])}
    decrites = {c["donnee"] for c in doc.get("cycle_de_vie", [])}
    for d in sorted(conservees - decrites):
        manques.append(f"cycle_de_vie : donnée {d} conservée dans un stockage, cycle de vie non décrit")
    for d in sorted(decrites - conservees):
        manques.append(f"cycle_de_vie : donnée {d} conservée par aucun stockage ; ajouter le stockage ou retirer l'entrée")
    return manques


def valider_document(doc, intention=None, technique=None):
    """Renvoie (format, erreurs, avertissements). La technique ne sert qu'à vérifier les
    références de la matrice de flux."""
    format_, erreurs = erreurs_schema(doc, FORMATS)
    if erreurs:  # la cohérence suppose un document conforme au schéma
        return format_, erreurs, []
    if format_ == "raton/intention/v0":
        return (format_, *coherence_intention(doc))
    if format_ == flux.FORMAT:
        return (format_, *flux.valider_document(doc, technique, intention))
    return (format_, *coherence_technique(doc, intention))


def valider_chemin(chemin: Path):
    """Valide un fichier, ou un répertoire .raton : intention, puis technique, puis
    matrice de flux, avec contrôle des références de chacune vers les précédentes."""
    resultats = []
    if chemin.is_dir():
        valides = {}
        for nom, format_ in (
            ("intention.yaml", "raton/intention/v0"),
            ("technique.yaml", "raton/technique/v0"),
            ("flux.yaml", flux.FORMAT),
        ):
            fichier = chemin / nom
            if not fichier.exists():
                continue
            doc = charger(fichier)
            fmt, err, av = valider_document(doc, valides.get("raton/intention/v0"), valides.get("raton/technique/v0"))
            if fmt != format_ and not err:
                err = [f"format {fmt} inattendu dans {nom}, qui doit contenir {format_}"]
            resultats.append((fichier, err, av))
            if not err:
                valides[format_] = doc
        if not resultats:
            raise ErreurFormat(f"{chemin} : ni intention.yaml, ni technique.yaml, ni flux.yaml")
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
            refs = f" ; interconnexion {', '.join(e['interconnexions'])}" if e.get("interconnexions") else ""
            lignes.append(
                f"| {_cell(e['partenaire'])} ({e['id']}{refs}) | l'application {sens[e['sens']]} "
                f"| {noms(e['donnees'])} | {_cell(e['motif'])} |"
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


def _cpu(m):
    return str(m // 1000) if m % 1000 == 0 else f"{m}m"


def _octets(n):
    """Mio en texte lisible : 512Mi, 2Gi, 25.1Gi."""
    for suffixe, facteur in (("Ti", 1024 * 1024), ("Gi", 1024)):
        if n >= facteur:
            return f"{n / facteur:.1f}".removesuffix(".0") + suffixe
    return f"{n}Mi" if n else "0"


def _valeur_et_plafond(valeur, plafond):
    return valeur if plafond in (None, valeur) else f"{valeur} (max {plafond})"


_FIN = {
    "suppression": "suppression",
    "anonymisation": "anonymisation",
    "archivage": "archivage",
    "aucune": "aucune",
}


def rendre_technique(doc, intention=None):
    """Rendu lisible de la partie technique, pour l'équipe DevOps, le change manager et le
    RSSI. Les libellés de l'intention, si elle est fournie, nomment les références."""
    lib = {}
    if intention:
        lib = {e["id"]: e.get("libelle") or e.get("partenaire") for s in ("profils", "donnees", "fonctions", "echanges") for e in intention[s]}
    noms_c = {c["id"]: c["nom"] for c in doc["composants"]}

    def noms(ids):
        return ", ".join(f"{_cell(lib[i])} ({i})" if i in lib else i for i in ids) or "—"

    src = doc["source"]
    titre = f"{_cell(intention['application']['nom'])} — partie technique" if intention else "Partie technique"
    lignes = [
        f"# {titre}",
        "",
        f"Commit `{src['commit']}` du dépôt {_cell(src['depot'])}.",
        f"Langages : {', '.join(src['langages'])}" + (f" ; frameworks : {', '.join(src['frameworks'])}." if src.get("frameworks") else "."),
        "",
        "## Composants",
        "",
        "| Composant | Rôle | Exposition | Instances | Processeur | Mémoire | Fonctions |",
        "|---|---|---|---|---|---|---|",
    ]
    total_cpu = total_cpu_max = total_mem = total_mem_max = 0
    total_initial = total_an = 0
    incomplet = False

    def ressources(r):
        nonlocal total_cpu, total_cpu_max, total_mem, total_mem_max, incomplet
        if r is None:
            incomplet = True
            return ["non déclaré"] * 3
        n = r["instances"]
        total_cpu += n * millicoeurs(r["cpu"])
        total_cpu_max += n * millicoeurs(r.get("cpu_max", r["cpu"]))
        total_mem += n * mio(r["memoire"])
        total_mem_max += n * mio(r.get("memoire_max", r["memoire"]))
        return [str(n), _valeur_et_plafond(r["cpu"], r.get("cpu_max")), _valeur_et_plafond(r["memoire"], r.get("memoire_max"))]

    for c in doc["composants"]:
        cols = ressources(c.get("ressources"))
        lignes.append(
            f"| {c['nom']} ({c['id']}) : {_cell(c['libelle'])} | {c['role']} | {c['expose']} | "
            + " | ".join(cols) + f" | {noms(c.get('fonctions', []))} |"
        )
    lignes += [
        "",
        "## Stockages",
        "",
        "| Stockage | Type | Technologie | Données | Capacité initiale | Croissance par an | Pods dans le namespace |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in doc["stockages"]:
        cap = s.get("capacite")
        if cap:
            total_initial += mio(cap["initiale"])
            total_an += mio(cap["par_an"])
        else:
            incomplet = True
        pods = "non, géré hors du cluster"
        if "nom" in s:
            pods = "{} : {} instance(s), processeur {}, mémoire {}".format(s["nom"], *ressources(s.get("ressources")))
        lignes.append(
            f"| {s['id']} | {s['type'].replace('_', ' ')} | {_cell(s['technologie'])} | {noms(s.get('donnees', []))} | "
            f"{cap['initiale'] if cap else 'non déclarée'} | {cap['par_an'] if cap else 'non déclarée'} | {pods} |"
        )
    lignes += [
        "",
        "## Ressources à prévoir",
        "",
        f"- Processeur : {_cpu(total_cpu)} demandés, {_cpu(total_cpu_max)} au plus",
        f"- Mémoire : {_octets(total_mem)} demandés, {_octets(total_mem_max)} au plus",
        f"- Stockage : {_octets(total_initial)} à la mise en production, puis {_octets(total_an)} de plus par an",
    ]
    if incomplet:
        lignes += ["", "> **Incomplet** : des ressources ou des capacités ne sont pas déclarées ; ces totaux ne les comptent pas."]

    lignes += ["", "## Cycle de vie des données", ""]
    origine = {d["id"]: d for d in intention["donnees"]} if intention else {}
    lieux = {}
    for s in doc["stockages"]:
        for d in s.get("donnees", []):
            lieux.setdefault(d, []).append(f"{s['id']} ({_cell(s['technologie'])})")
    tiers = {}
    for t in doc["services_tiers"]:
        for d in t.get("donnees_transmises", []):
            tiers.setdefault(d, []).append(f"{t['id']} ({_cell(t['libelle'])})")
    cycle = doc.get("cycle_de_vie", [])
    if cycle:
        lignes += [
            "| Donnée | Origine | Conservée dans | Transmise à | Conservation prévue par l'intention | Conservation appliquée | Fin |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in cycle:
            d = c["donnee"]
            fin = _FIN[c["fin"]]
            if c.get("mecanisme") == "composant":
                fin += f", par le composant {noms_c.get(c['composant'], c['composant'])} ({c['composant']})"
            elif c.get("mecanisme") == "regle_stockage":
                fin += ", par une règle du stockage"
            elif c.get("mecanisme") == "manuel":
                fin += ", à la main (dossier d'exploitation)"
            if c.get("precision"):
                fin += f" ; {_cell(c['precision'])}"
            lignes.append(
                f"| {noms([d])} | {_cell(origine[d]['origine']) if d in origine else '—'} | {', '.join(lieux.get(d, [])) or '—'} | "
                f"{', '.join(tiers.get(d, [])) or '—'} | {_cell(origine[d]['conservation']) if d in origine else '—'} | "
                f"{_cell(c.get('duree', 'sans limite'))} | {fin} |"
            )
    else:
        lignes.append("Non décrit.")
    non_conservees = [d for d in origine if d not in lieux]
    if non_conservees:
        lignes += ["", f"Données de l'intention qu'aucun stockage ne conserve : {noms(non_conservees)}."]

    lignes += ["", "## Services tiers", ""]
    if doc["services_tiers"]:
        lignes += ["| Service | Usage | Données transmises | Échanges |", "|---|---|---|---|"]
        for t in doc["services_tiers"]:
            echanges = noms(t["echanges"]) if t.get("echanges") else ("**aucun échange déclaré**" if "echanges" in t else "—")
            lignes.append(f"| {_cell(t['libelle'])} ({t['id']}) | {_cell(t['usage'])} | {noms(t.get('donnees_transmises', []))} | {echanges} |")
    else:
        lignes.append("Aucun.")
    auth = doc["authentification"]
    lignes += ["", "## Authentification", "", f"Mécanisme : {auth['mecanisme']}" + (f" ({auth['protocole']})." if auth.get("protocole") else ".")]
    for r in auth.get("roles", []):
        lignes.append(f"- rôle « {_cell(r['role'])} » : {noms(r.get('profils', [])) if r.get('profils') else '**aucun profil**'}")
    conf = doc["configuration"]
    lignes += [
        "",
        "## Configuration",
        "",
        f"Variables : {', '.join(conf['variables']) or '—'}.",
        "Secrets (noms seulement) : " + (", ".join(f"{s['nom']} ({s['provenance'].replace('_', ' ')})" for s in conf["secrets"]) or "—") + ".",
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
    chemin = Path(args.fichier)
    doc = charger(chemin)
    if isinstance(doc, dict) and doc.get("format") == "raton/technique/v0":
        voisine = chemin.parent / "intention.yaml"
        intention = _charger_valide(voisine, "raton/intention/v0") if voisine.exists() else None
        sys.stdout.write(rendre_technique(_charger_valide(chemin, "raton/technique/v0", intention), intention))
    else:
        sys.stdout.write(rendre_intention(_charger_valide(chemin, "raton/intention/v0")))
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
    p = sous.add_parser("rendre", help="rendre intention.yaml ou technique.yaml en Markdown")
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
