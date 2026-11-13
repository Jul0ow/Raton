#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Matrice de flux : validation, écarts avec le dossier, rendu lisible, politiques réseau.

  flux.py valider FLUX [--dossier REP] [--qualification FICHE]   schéma, règles et références
  flux.py ecarts FLUX [--dossier REP] [--qualification FICHE]    flux non déclarés, échanges sans flux…
  flux.py rendre FLUX [--dossier REP]                            rendu Markdown, pour l'auteur et l'équipe infra
  flux.py egress FLUX                                            destinations hors du namespace, pour un proxy ou un pare-feu
  flux.py generer FLUX --dossier REP --plateforme PLATEFORME     politiques réseau à appliquer au déploiement
                     [--namespace NS]

REP est le répertoire .raton (intention.yaml, technique.yaml). La plateforme est l'ensemble
des services communs que l'équipe infra fournit à toutes les applications : entrées des
utilisateurs, SSO, secrets, journalisation, supervision, DNS. La matrice vient de l'auteur :
c'est une donnée non fiable, que le script ne fait qu'analyser. Les politiques générées
refusent tout par défaut : un flux absent de la matrice est bloqué.
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from pathlib import Path

import yaml

from raton_formats import ErreurFormat, charger, doublons, erreurs_schema, ids, md_inerte

FORMAT = "raton/flux/v0"
FORMAT_PLATEFORME = "raton/plateforme/v0"

NATURES = ("composant", "stockage", "service", "systeme", "plateforme")
PLATEFORME = {
    "entree_interne": "entrée des utilisateurs, réseau de l'entreprise",
    "entree_externe": "entrée des utilisateurs, hors du réseau de l'entreprise",
    "sso": "SSO de l'entreprise",
    "secrets": "gestionnaire de secrets",
    "journalisation": "journalisation",
    "supervision": "supervision",
}
SEULEMENT_ORIGINE = {"entree_interne", "entree_externe"}
SEULEMENT_DESTINATION = {"sso", "secrets"}
# Exposition d'un composant dans la partie technique → entrées de la plateforme qui
# peuvent lui envoyer des connexions. externe : réseau que l'entreprise ne maîtrise pas,
# Internet ou réseau d'un partenaire, comme dans la fiche de qualification.
ENTREE_REQUISE = {"externe": "entree_externe", "interne": "entree_interne"}
ENTREES_PERMISES = {"externe": {"entree_externe", "entree_interne"}, "interne": {"entree_interne"}, "aucune": set()}
EN_CLAIR = {"http", "ldap"}
PAR_PROXY = {"http", "https", "grpc"}  # protocoles qu'un proxy sortant HTTP sait relayer
PREFIXE_MIN = {4: 16, 6: 48}  # en deçà, un bloc d'adresses est signalé comme large

ETIQUETTES = {"app.kubernetes.io/managed-by": "raton"}
NOMS_RESERVES = {"dns", "refus-par-defaut"}  # politiques communes à tout le namespace


def transport(protocole):
    return "UDP" if protocole == "udp" else "TCP"


# --- Extrémités ----------------------------------------------------------------


def nature(ext):
    return next(n for n in NATURES if n in ext)


def adresse(ext):
    return ext.get("hote") or ext.get("cidr")


def dans_le_namespace(ext):
    """Pod du namespace de l'application : un composant, ou un stockage déployé avec
    elle, reconnaissable à ce qu'il n'a ni adresse ni variable."""
    if "composant" in ext:
        return True
    return "stockage" in ext and not adresse(ext) and "variable" not in ext


def hors_namespace(ext):
    """Désigné par une adresse, ou par la variable qui la porte."""
    return not dans_le_namespace(ext) and "plateforme" not in ext


def tiers(ext):
    """Système que l'application ne possède pas, hors services de la plateforme : un
    tel flux doit renvoyer à un échange et à une interconnexion."""
    return "service" in ext or "systeme" in ext


def ident(ext):
    return ext.get("composant") or ext.get("stockage")


def court(ext):
    """Désignation courte, pour les messages."""
    if "plateforme" in ext:
        return ext["plateforme"]
    if dans_le_namespace(ext):
        return ident(ext)
    return adresse(ext) or f"${ext['variable']}"


def resume(f):
    return f"{f['id']} ({court(f['de'])} → {court(f['vers'])}:{f['port']})"


# --- Validation --------------------------------------------------------------


def coherence(doc):
    """Règles que le schéma ne peut pas porter. Renvoie (erreurs, avertissements)."""
    erreurs, avert = doublons("flux", doc["flux"]), []
    for f in doc["flux"]:
        nom = f"flux {f['id']}"
        de, vers = f["de"], f["vers"]
        if "composant" not in de and "composant" not in vers:
            erreurs.append(f"{nom} : ni l'origine ni la destination n'est un composant de l'application")
        if de.get("plateforme") in SEULEMENT_DESTINATION:
            erreurs.append(f"{nom} : le service {de['plateforme']} ne peut être qu'une destination")
        if vers.get("plateforme") in SEULEMENT_ORIGINE:
            erreurs.append(f"{nom} : {vers['plateforme']} ne peut être qu'une origine")
        if "stockage" in de:
            erreurs.append(f"{nom} : un stockage reçoit des connexions, il n'en ouvre pas")
        for cote, ext in (("origine", de), ("destination", vers)):
            if "cidr" in ext:
                try:
                    ipaddress.ip_network(ext["cidr"])
                except ValueError:
                    erreurs.append(f"{nom} : {cote} : bloc d'adresses invalide « {ext['cidr']} »")
            if hors_namespace(ext) and not adresse(ext):
                avert.append(
                    f"{nom} : {cote} : adresse à fixer avant de générer les politiques réseau "
                    f"(seule la variable {ext['variable']} est connue)"
                )
            if ext.get("hote", "").startswith("*."):
                avert.append(f"{nom} : {cote} : le joker {ext['hote']} couvre tous les noms de ce niveau ; un nom exact est préférable s'il est connu")
        if "hote" in de:
            avert.append(f"{nom} : une origine désignée par un nom ne peut pas être filtrée ; donner son bloc d'adresses (cidr)")
    return erreurs, avert


def references(doc, technique=None, intention=None, qualification=None):
    """Références vers la partie technique (C, S, T), l'intention (E) et la fiche de
    qualification (I). Renvoie la liste des erreurs."""
    erreurs = []
    connus = {}
    if technique is not None:
        connus = {
            "composant": set(ids(technique["composants"])),
            "stockage": set(ids(technique["stockages"])),
            "service": set(ids(technique["services_tiers"])),
        }
    echanges = set(ids(intention["echanges"])) if intention is not None else None
    inter = set(ids(qualification["interconnexions"])) if qualification is not None else None
    sans_nom = {s["id"] for s in technique["stockages"] if "nom" not in s} if technique is not None else set()
    for f in doc["flux"]:
        nom = f"flux {f['id']}"
        for ext in (f["de"], f["vers"]):
            for n, connus_n in connus.items():
                if n in ext and ext[n] not in connus_n:
                    erreurs.append(f"{nom} : {ext[n]} absent de la partie technique")
            if dans_le_namespace(ext) and ident(ext) in sans_nom:
                erreurs.append(f"{nom} : {ident(ext)} est déployé dans le namespace, il lui faut un nom dans la partie technique")
        if echanges is not None:
            erreurs += [f"{nom} : échange {e} absent de l'intention" for e in f.get("echanges", []) if e not in echanges]
        if inter is not None:
            erreurs += [f"{nom} : interconnexion {i} absente de la fiche de qualification" for i in f.get("interconnexions", []) if i not in inter]
    if technique is not None and doc["commit"] != technique["source"]["commit"]:
        erreurs.append(f"commit : {doc['commit']}, alors que la partie technique décrit {technique['source']['commit']}")
    if qualification is not None and doc["application"] != qualification["application"]["code"]:
        erreurs.append(f"application : « {doc['application']} » au lieu de « {qualification['application']['code']} », le code de la fiche de qualification")
    return erreurs


def valider_document(doc, technique=None, intention=None, qualification=None):
    """Renvoie (erreurs, avertissements)."""
    _, erreurs = erreurs_schema(doc, (FORMAT,))
    if erreurs:  # les règles supposent un document conforme au schéma
        return erreurs, []
    erreurs, avert = coherence(doc)
    return erreurs + references(doc, technique, intention, qualification), avert


# --- Écarts ------------------------------------------------------------------


def ecarts(doc, technique=None, intention=None, qualification=None):
    """Points à examiner, constatés par jeu de références : ce ne sont pas des erreurs
    de format. Chaque écart est un couple (code, message)."""
    res = []
    flux = sorted(doc["flux"], key=lambda f: f["id"])
    prevues = {e["id"]: set(e.get("interconnexions", [])) for e in intention["echanges"]} if intention else {}

    for f in flux:
        extremites = (f["de"], f["vers"])
        if f["protocole"] in EN_CLAIR and any(hors_namespace(e) for e in extremites):
            res.append(("flux_en_clair", f"{resume(f)} : {f['protocole']} n'est pas chiffré, hors du namespace de l'application"))
        for e in extremites:
            if "cidr" in e:
                reseau = ipaddress.ip_network(e["cidr"])
                if reseau.prefixlen < PREFIXE_MIN[reseau.version]:
                    res.append(("bloc_large", f"{resume(f)} : le bloc {e['cidr']} couvre {reseau.num_addresses} adresses"))
        if any(tiers(e) for e in extremites):
            if intention is not None and not f.get("echanges"):
                res.append(("flux_sans_echange", f"{resume(f)} : ne renvoie à aucun échange de l'intention"))
            if qualification is not None and not f.get("interconnexions"):
                res.append(("flux_sans_interconnexion", f"{resume(f)} : ne renvoie à aucune interconnexion de la fiche de qualification"))
        if intention is not None and qualification is not None and f.get("echanges"):
            attendues = set().union(*(prevues.get(e, set()) for e in f["echanges"]))
            hors = [i for i in f.get("interconnexions", []) if i not in attendues]
            if attendues and hors:
                res.append((
                    "interconnexion_hors_echange",
                    f"{resume(f)} : passe par {', '.join(hors)}, que ses échanges ({', '.join(f['echanges'])}) ne citent pas",
                ))
        if qualification is not None and f["de"].get("plateforme") == "entree_externe" and qualification["exposition"] != "externe":
            res.append(("exposition_sous_evaluee", f"{resume(f)} : connexions depuis l'extérieur, alors que la fiche de qualification déclare une exposition interne"))

    if intention is not None:
        cites = {e for f in flux for e in f.get("echanges", [])}
        for e in intention["echanges"]:
            if e["id"] not in cites:
                res.append(("echange_sans_flux", f"{e['id']} ({e['partenaire']}) : aucun flux ne le réalise ; les politiques générées le bloqueraient"))
    if qualification is not None:
        cites = {i for f in flux for i in f.get("interconnexions", [])}
        for i in qualification["interconnexions"]:
            if i["id"] not in cites:
                res.append(("interconnexion_sans_flux", f"{i['id']} ({i['systeme']}) : aucun flux n'y passe ; si elle ne sert pas, elle ne doit pas recevoir de droits"))
    if technique is not None:
        utilises = {(n, ext[n]) for f in flux for ext in (f["de"], f["vers"]) for n in ("stockage", "service") if n in ext}
        for s in technique["stockages"]:
            if ("stockage", s["id"]) not in utilises:
                res.append(("stockage_sans_flux", f"{s['id']} ({s['technologie']}) : aucun flux n'y mène"))
        for t in technique["services_tiers"]:
            if ("service", t["id"]) not in utilises:
                res.append(("service_sans_flux", f"{t['id']} ({t['libelle']}) : appelé par le code, absent de la matrice ; les politiques générées le bloqueraient"))
        entrees = {}
        for f in flux:
            p = f["de"].get("plateforme")
            if p in SEULEMENT_ORIGINE and "composant" in f["vers"]:
                entrees.setdefault(f["vers"]["composant"], set()).add(p)
        for c in technique["composants"]:
            recues, expose = entrees.get(c["id"], set()), c["expose"]
            requise = ENTREE_REQUISE.get(expose)
            if requise and requise not in recues:
                res.append(("exposition_incoherente", f"{c['id']} ({c['libelle']}) : exposé « {expose} » d'après la partie technique, sans flux depuis {requise}"))
            for p in sorted(recues - ENTREES_PERMISES[expose]):
                res.append(("exposition_incoherente", f"{c['id']} ({c['libelle']}) : reçoit des connexions depuis {p}, alors que la partie technique le dit exposé « {expose} »"))
    return res


# --- Rendu lisible -----------------------------------------------------------


def rendre(doc, technique=None):
    noms = {}
    if technique is not None:
        for c in technique["composants"]:
            noms[c["id"]] = c["libelle"]
        for s in technique["stockages"]:
            noms[s["id"]] = s["technologie"]
        for t in technique["services_tiers"]:
            noms[t["id"]] = t["libelle"]

    def decrire(ext):
        n = nature(ext)
        if n == "plateforme":
            return PLATEFORME[ext["plateforme"]]
        if n == "systeme":
            texte = md_inerte(ext["systeme"])
        else:
            i = ext[n]
            texte = f"{md_inerte(noms[i])} ({i})" if i in noms else i
        if adresse(ext):
            return f"{texte} — {md_inerte(adresse(ext))}"
        if hors_namespace(ext):
            return f"{texte} — adresse à fixer (variable {ext['variable']})"
        if n == "stockage":
            return f"{texte} — dans le namespace"
        return texte

    def renvois(f):
        r = []
        if f.get("echanges"):
            r.append("échange " + ", ".join(f["echanges"]))
        if f.get("interconnexions"):
            r.append("interconnexion " + ", ".join(f["interconnexions"]))
        return " ; ".join(r) or "—"

    grille = []
    if technique is not None:
        grille = [(c["id"], c["nom"], c["libelle"]) for c in technique["composants"]]
        grille += [(s["id"], s["nom"], s["technologie"]) for s in technique["stockages"] if "nom" in s]

    groupes = {"recus": [], "ouverts": [], "internes": []}
    for f in sorted(doc["flux"], key=lambda f: f["id"]):
        de, vers = dans_le_namespace(f["de"]), dans_le_namespace(f["vers"])
        groupes["internes" if de and vers else "ouverts" if de else "recus"].append(f)

    lignes = [
        f"# {doc['application']} — matrice de flux",
        "",
        f"Commit décrit : {doc['commit']}",
        "",
        "Les politiques réseau générées depuis cette matrice refusent tout par défaut : un flux qui n'y figure pas est bloqué. "
        "Seule la résolution de noms par le DNS du cluster est toujours permise.",
    ]
    if grille:
        lignes += [
            "",
            "## Composants dans le cluster",
            "",
            "Les pods portent le nom de leur composant ; les politiques réseau en reprennent le nom.",
            "",
            "| Identifiant | Nom des pods | Libellé |",
            "|---|---|---|",
        ]
        lignes += [f"| {i} | {n} | {md_inerte(lib)} |" for i, n, lib in grille]
    titres = (
        ("recus", "Connexions reçues par l'application"),
        ("ouverts", "Connexions ouvertes par l'application"),
        ("internes", "Connexions entre ses composants"),
    )
    for cle, titre in titres:
        lignes += ["", f"## {titre}", ""]
        if not groupes[cle]:
            lignes.append("Aucune.")
            continue
        lignes += ["| Flux | De | Vers | Port | Motif | Renvois |", "|---|---|---|---|---|---|"]
        for f in groupes[cle]:
            motif = md_inerte(f["motif"]) if "motif" in f else "—"
            lignes.append(
                f"| {f['id']} | {decrire(f['de'])} | {decrire(f['vers'])} | {f['port']} ({f['protocole']}) | {motif} | {renvois(f)} |"
            )
    return "\n".join(lignes) + "\n"


# --- Destinations hors du namespace ------------------------------------------------


def destinations(doc):
    """Connexions que l'application ouvre hors de son namespace : la liste à autoriser
    dans un proxy sortant ou un pare-feu. Les services de la plateforme y figurent par
    leur nom : c'est le fichier de plateforme qui donne leur adresse."""
    res = []
    for f in sorted(doc["flux"], key=lambda f: f["id"]):
        vers = f["vers"]
        if dans_le_namespace(f["de"]) and not dans_le_namespace(vers):
            d = {"flux": f["id"], "composant": ident(f["de"])}
            for cle in ("plateforme", "hote", "cidr", "variable"):
                if cle in vers and (cle != "variable" or not adresse(vers)):
                    d[cle] = vers[cle]
            d.update(port=f["port"], protocole=f["protocole"])
            res.append(d)
    return {"application": doc["application"], "commit": doc["commit"], "destinations": res}


# --- Politiques réseau -------------------------------------------------------


def valider_plateforme(plateforme):
    _, erreurs = erreurs_schema(plateforme, (FORMAT_PLATEFORME,))
    if erreurs:
        return erreurs
    for nom, lieu in plateforme["services"].items():
        for c in lieu.get("cidrs", []):
            try:
                ipaddress.ip_network(c)
            except ValueError:
                erreurs.append(f"services/{nom} : bloc d'adresses invalide « {c} »")
    return erreurs


def _dans_le_cluster(lieu):
    return {
        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": lieu["namespace"]}},
        "podSelector": {"matchLabels": dict(lieu["pods"])},
    }


def _pairs(ext, plateforme, noms):
    """Ce que désigne une extrémité : ("np", pairs d'une NetworkPolicy) ou ("noms", noms DNS)."""
    if dans_le_namespace(ext):
        return "np", [{"podSelector": {"matchLabels": {plateforme["etiquette_composant"]: noms[ident(ext)]}}}]
    if "plateforme" in ext:
        lieu = plateforme["services"][ext["plateforme"]]
    elif "hote" in ext:
        lieu = {"hotes": [ext["hote"]]}
    else:
        lieu = {"cidrs": [ext["cidr"]]}
    if "namespace" in lieu:
        return "np", [_dans_le_cluster(lieu)]
    if "cidrs" in lieu:
        return "np", [{"ipBlock": {"cidr": c}} for c in lieu["cidrs"]]
    return "noms", list(lieu["hotes"])


def _fqdn(nom):
    return {"matchPattern": nom} if nom.startswith("*.") else {"matchName": nom}


def generer(doc, plateforme, technique, namespace=None):
    """Politiques réseau d'après la matrice. La partie technique donne le nom des
    composants, que portent leurs pods. Renvoie (objets Kubernetes, avertissements).
    Lève ErreurFormat si une adresse, un nom ou un service de la plateforme manque."""
    ns = namespace or doc["application"]
    cle = plateforme["etiquette_composant"]
    cilium = plateforme["cni"] == "cilium"
    proxy = plateforme.get("proxy_sortant")
    noms = {c["id"]: c["nom"] for c in technique["composants"]}
    noms.update({s["id"]: s["nom"] for s in technique["stockages"] if "nom" in s})
    libelles = {c["id"]: c["libelle"] for c in technique["composants"]}
    libelles.update({s["id"]: s["technologie"] for s in technique["stockages"]})

    manques = []
    for f in doc["flux"]:
        for ext in (f["de"], f["vers"]):
            p = ext.get("plateforme")
            if dans_le_namespace(ext) and ident(ext) not in noms:
                manques.append(f"{f['id']} : {ident(ext)} n'a pas de nom dans la partie technique")
            elif dans_le_namespace(ext) and noms[ident(ext)] in NOMS_RESERVES:
                manques.append(f"{f['id']} : le nom « {noms[ident(ext)]} » de {ident(ext)} est réservé aux politiques communes")
            elif p and p not in plateforme["services"]:
                manques.append(f"{f['id']} : la plateforme ne décrit pas le service {p}")
            elif hors_namespace(ext) and not adresse(ext):
                manques.append(f"{f['id']} : adresse inconnue, seule la variable {ext['variable']} est donnée")
    if manques:
        raise ErreurFormat("génération impossible : " + " ; ".join(manques))

    avert = []
    pods = {}

    def pod(i):
        return pods.setdefault(i, {"ingress": [], "egress": [], "noms": []})

    for f in sorted(doc["flux"], key=lambda f: f["id"]):
        ports = [{"protocol": transport(f["protocole"]), "port": f["port"]}]
        de, vers = f["de"], f["vers"]
        if dans_le_namespace(de):
            genre, cibles = _pairs(vers, plateforme, noms)
            if genre == "np":
                pod(ident(de))["egress"].append((f["id"], {"to": cibles, "ports": ports}))
            else:
                pod(ident(de))["noms"].append((f["id"], cibles, f))
        if dans_le_namespace(vers):
            genre, cibles = _pairs(de, plateforme, noms)
            if genre == "np":
                pod(ident(vers))["ingress"].append((f["id"], {"from": cibles, "ports": ports}))
            else:
                avert.append(f"{f['id']} : origine désignée par un nom ({', '.join(cibles)}), impossible à filtrer : flux non autorisé")

    def meta(nom, flux_ids, composant=None):
        m = {"name": nom, "namespace": ns, "labels": {"app.kubernetes.io/part-of": doc["application"], **ETIQUETTES}}
        m["annotations"] = {"raton/commit": doc["commit"]}
        if composant:
            m["annotations"]["raton/composant"] = f"{composant} — {libelles[composant]}"
        if flux_ids:
            m["annotations"]["raton/flux"] = " ".join(flux_ids)
        return m

    objets = [
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": meta("raton-refus-par-defaut", []),
            "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        }
    ]
    dns = plateforme["dns"]
    if cilium:
        objets.append({
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": meta("raton-dns", []),
            "spec": {
                "endpointSelector": {},
                "egress": [{
                    "toEndpoints": [{"matchLabels": {
                        "k8s:io.kubernetes.pod.namespace": dns["namespace"],
                        **{f"k8s:{k}": v for k, v in dns["pods"].items()},
                    }}],
                    "toPorts": [{"ports": [{"port": "53", "protocol": "ANY"}], "rules": {"dns": [{"matchPattern": "*"}]}}],
                }],
            },
        })
    else:
        objets.append({
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": meta("raton-dns", []),
            "spec": {
                "podSelector": {},
                "policyTypes": ["Egress"],
                "egress": [{"to": [_dans_le_cluster(dns)], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}],
            },
        })

    noms_cilium = []
    for i in sorted(pods):
        p = pods[i]
        ingress = [r for _, r in p["ingress"]]
        egress = [r for _, r in p["egress"]]
        flux_ids = [fid for fid, _ in p["ingress"]] + [fid for fid, _ in p["egress"]]
        if p["noms"] and cilium:
            noms_cilium.append((i, p["noms"]))
        else:
            relayes = []
            for fid, hotes, f in p["noms"]:
                if not proxy:
                    avert.append(f"{fid} : {', '.join(hotes)} : non généré, le CNI ne filtre pas par nom et la plateforme n'a pas de proxy sortant ; flux bloqué")
                elif f["protocole"] not in PAR_PROXY:
                    avert.append(f"{fid} : {', '.join(hotes)} : non généré, {f['protocole']} ne passe pas par un proxy HTTP ; désigner la destination par un bloc d'adresses")
                else:
                    relayes.append(fid)
                    avert.append(f"{fid} : {', '.join(hotes)}, port {f['port']} : passe par le proxy sortant, où il faut l'autoriser (flux.py egress)")
            if relayes:
                egress.append({"to": [_dans_le_cluster(proxy)], "ports": [{"protocol": "TCP", "port": proxy["port"]}]})
                flux_ids += relayes
        spec = {"podSelector": {"matchLabels": {cle: noms[i]}}, "policyTypes": []}
        if ingress:
            spec["policyTypes"].append("Ingress")
            spec["ingress"] = ingress
        if egress:
            spec["policyTypes"].append("Egress")
            spec["egress"] = egress
        if spec["policyTypes"]:
            objets.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": meta(f"raton-{noms[i]}", flux_ids, i), "spec": spec})

    for i, hotes_par_flux in noms_cilium:
        objets.append({
            "apiVersion": "cilium.io/v2",
            "kind": "CiliumNetworkPolicy",
            "metadata": meta(f"raton-noms-{noms[i]}", [fid for fid, _, _ in hotes_par_flux], i),
            "spec": {
                "endpointSelector": {"matchLabels": {cle: noms[i]}},
                "egress": [
                    {
                        "toFQDNs": [_fqdn(h) for h in hotes],
                        "toPorts": [{"ports": [{"port": str(f["port"]), "protocol": transport(f["protocole"])}]}],
                    }
                    for _, hotes, f in hotes_par_flux
                ],
            },
        })
    return objets, avert


# --- Ligne de commande -------------------------------------------------------


def _conforme(chemin, format_):
    doc = charger(chemin)
    _, erreurs = erreurs_schema(doc, (format_,))
    if erreurs:
        raise ErreurFormat(f"{chemin} : non conforme au schéma {format_}")
    return doc


def _dossier(rep):
    """(technique, intention) du répertoire .raton, chacune None si absente."""
    if rep is None:
        return None, None
    rep = Path(rep)
    technique = _conforme(rep / "technique.yaml", "raton/technique/v0") if (rep / "technique.yaml").exists() else None
    intention = _conforme(rep / "intention.yaml", "raton/intention/v0") if (rep / "intention.yaml").exists() else None
    return technique, intention


def _qualification(chemin):
    return _conforme(Path(chemin), "raton/qualification/v0") if chemin else None


def _flux_valide(chemin):
    doc = charger(chemin)
    erreurs, _ = valider_document(doc)
    if erreurs:
        raise ErreurFormat(f"{chemin} : non valide, lancer d'abord « flux.py valider »")
    return doc


def _cmd_valider(args):
    technique, intention = _dossier(args.dossier)
    erreurs, avert = valider_document(charger(Path(args.flux)), technique, intention, _qualification(args.qualification))
    print(f"{'✗' if erreurs else '✓'} {args.flux}")
    for e in erreurs:
        print(f"  erreur : {e}")
    for a in avert:
        print(f"  avertissement : {a}")
    return 1 if erreurs else 0


def _cmd_ecarts(args):
    doc = _flux_valide(Path(args.flux))
    technique, intention = _dossier(args.dossier)
    qualification = _qualification(args.qualification)
    erreurs = references(doc, technique, intention, qualification)
    if erreurs:
        raise ErreurFormat("références invalides, lancer d'abord « flux.py valider » avec les mêmes options")
    liste = ecarts(doc, technique, intention, qualification)
    for code, message in liste:
        print(f"[{code}] {message}")
    print(f"{len(liste)} écart(s)")
    return 0


def _cmd_rendre(args):
    technique, _ = _dossier(args.dossier)
    sys.stdout.write(rendre(_flux_valide(Path(args.flux)), technique))
    return 0


def _yaml(objets, entete):
    texte = yaml.safe_dump_all(objets, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return "".join(f"# {ligne}\n" for ligne in entete) + texte


def _cmd_egress(args):
    doc = _flux_valide(Path(args.flux))
    sys.stdout.write(_yaml([destinations(doc)], ["Destinations hors du namespace, déclarées par la matrice de flux"]))
    return 0


def _cmd_generer(args):
    doc = _flux_valide(Path(args.flux))
    technique, _ = _dossier(args.dossier)
    if technique is None:
        raise ErreurFormat(f"{args.dossier} : technique.yaml absent ; il donne le nom des composants")
    if erreurs := references(doc, technique):
        raise ErreurFormat("références invalides : " + " ; ".join(erreurs))
    plateforme = charger(Path(args.plateforme))
    erreurs = valider_plateforme(plateforme)
    if erreurs:
        raise ErreurFormat(f"{args.plateforme} : " + " ; ".join(erreurs))
    objets, avert = generer(doc, plateforme, technique, args.namespace)
    for a in avert:
        print(f"avertissement : {a}", file=sys.stderr)
    entete = [
        f"Généré par flux.py depuis la matrice de flux de {doc['application']}, commit {doc['commit']}.",
        "Ne pas modifier à la main : modifier la matrice, la faire relire, puis regénérer.",
    ]
    sys.stdout.write(_yaml(objets, entete))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="flux.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    for nom, func, aide in (
        ("valider", _cmd_valider, "valider la matrice, et ses références avec --dossier et --qualification"),
        ("ecarts", _cmd_ecarts, "écarts entre la matrice, le dossier et la fiche de qualification"),
    ):
        p = sous.add_parser(nom, help=aide)
        p.add_argument("flux")
        p.add_argument("--dossier", help="répertoire .raton : intention.yaml et technique.yaml")
        p.add_argument("--qualification", help="fiche de qualification validée")
        p.set_defaults(func=func)
    p = sous.add_parser("rendre", help="rendre la matrice en Markdown")
    p.add_argument("flux")
    p.add_argument("--dossier", help="répertoire .raton, pour nommer composants, stockages et services")
    p.set_defaults(func=_cmd_rendre)
    p = sous.add_parser("egress", help="destinations hors du namespace")
    p.add_argument("flux")
    p.set_defaults(func=_cmd_egress)
    p = sous.add_parser("generer", help="politiques réseau Kubernetes")
    p.add_argument("flux")
    p.add_argument("--dossier", required=True, help="répertoire .raton : technique.yaml donne le nom des composants")
    p.add_argument("--plateforme", required=True, help="fichier de plateforme de l'équipe infra")
    p.add_argument("--namespace", help="namespace de l'application ; par défaut, son code")
    p.set_defaults(func=_cmd_generer)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
