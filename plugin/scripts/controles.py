#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.18"]
# ///
"""Contrôles déterministes : lancer les outils sur le dépôt, convertir leurs sorties en rapports.

  controles.py analyser DEPOT --commit SHA --fiche FICHE --sortie REP     phase d'analyse du pipeline
                        [--bases REP] [--image IMAGE] [--application CODE]
  controles.py convertir gitleaks --depot DEPOT --commit SHA --version V  sortie JSON de gitleaks → rapport
                        [--arbre JSON] [--historique JSON]
  controles.py suppressions DEPOT [--outil OUTIL]                         ce que le dépôt demande aux outils d'ignorer
  controles.py inventorier REP                                            empreintes des bases préparées
  controles.py valider EXECUTION                                          manifeste d'exécution

Le dépôt vient de l'auteur : c'est une donnée non fiable. Le script n'exécute rien qui en
vienne. Les outils reçoivent la configuration de Raton, jamais celle du dépôt, un
environnement sans jeton, et une copie de l'arbre sans les fichiers qui leur demanderaient
d'ignorer des résultats. Les valeurs secrètes trouvées ne sortent jamais du job : les
rapports et les sorties conservées les masquent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import constats
import qualification
from raton_formats import ErreurFormat, charger, erreurs_schema

FORMAT = "raton/execution/v0"
REGLES = Path(__file__).resolve().parent.parent / "regles"
MASQUE = constats.MASQUE

# Contrôles déterministes, dans l'ordre du pipeline, et les outils qui les réalisent.
CONTROLES_DETERMINISTES = ("secrets", "chaine_approvisionnement", "sast", "identite_acces", "palier_kubernetes")

TAILLE_DEPOT_MAX = 500_000_000  # octets copiés pour l'analyse de l'arbre
TAILLE_TEXTE_MAX = 1_000_000  # fichiers lus pour chercher les demandes d'ignorer
TAILLE_SORTIE_MAX = 50_000_000  # sortie JSON d'un outil
FICHIERS_MAX = 50_000
DELAI_OUTIL = 1800  # secondes
PREUVES_MAX = 20  # par constat, comme le schéma
EXTRAIT_LONG = 600  # au-delà, on ne cite que la ligne du secret, ou un morceau
BASES_MAX = 1000


# --- Masquage ----------------------------------------------------------------

PEM = re.compile(r"-----(BEGIN|END)[A-Z0-9 _-]{0,100}-----")
JETON_LONG = re.compile(r"[A-Za-z0-9+/=_\-]{16,}")
CHAINE = re.compile(r"('''|\"\"\"|'|\")(.+?)\1")


def _significatif(texte):
    return len("".join(texte.replace(MASQUE, "").split()))


def _masque_pour(secret):
    """Ce qui remplace un secret : *** ; pour une clé PEM, les lignes BEGIN et END restent
    lisibles, elles ne sont pas secrètes et rendent l'extrait probant."""
    lignes = [l.strip() for l in secret.splitlines() if l.strip()]
    if len(lignes) >= 2 and PEM.fullmatch(lignes[0]) and PEM.fullmatch(lignes[-1]):
        return f"{lignes[0]}\n{MASQUE}\n{lignes[-1]}"
    return MASQUE


def masquer(texte, secrets):
    """Remplace chaque secret connu, du plus long au plus court."""
    for s in sorted({s for s in secrets if s}, key=len, reverse=True):
        texte = texte.replace(s, _masque_pour(s))
    return texte


def masquer_jetons(texte):
    """Masquage générique, quand on ne connaît pas la valeur : contenu des chaînes et
    longues suites de caractères (clés, empreintes, base64)."""
    texte = CHAINE.sub(lambda m: f"{m.group(1)}{MASQUE}{m.group(1)}", texte)
    return JETON_LONG.sub(MASQUE, texte)


def _couper(texte, longueur):
    """Coupe sans laisser un masque à moitié : ** n'est pas un masque."""
    texte = texte[:longueur]
    return re.sub(r"\*{1,2}$", "", texte) if not texte.endswith(MASQUE) else texte


def _fenetre(ligne, rayon=150):
    """Morceau d'une très longue ligne (code minifié) autour du premier masque."""
    i = ligne.find(MASQUE)
    if i < 0 or len(ligne) <= 2 * rayon:
        return _couper(ligne, 2 * rayon)
    morceau = ligne[max(0, i - rayon) : i + len(MASQUE) + rayon]
    return re.sub(r"^\*{1,2}(?!\*)", "", _couper(morceau, len(morceau)))


# --- Lecture du dépôt ----------------------------------------------------------


def fichiers_texte(depot: Path):
    """(chemin relatif, lignes) de chaque fichier texte du dépôt, hors .git. Les liens
    symboliques ne sont jamais suivis : ils pourraient désigner un fichier du job."""
    depot = Path(depot)
    vus = 0
    for racine, reps, fichiers in os.walk(depot, followlinks=False):
        rel = Path(racine).relative_to(depot)
        reps[:] = sorted(r for r in reps if not (rel == Path(".") and r == ".git") and not os.path.islink(os.path.join(racine, r)))
        for nom in sorted(fichiers):
            chemin = Path(racine) / nom
            try:
                st = os.lstat(chemin)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode) or st.st_size > TAILLE_TEXTE_MAX:
                continue
            vus += 1
            if vus > FICHIERS_MAX:
                return
            contenu = chemin.read_bytes()
            if b"\0" in contenu[:8192]:
                continue
            yield (rel / nom).as_posix(), contenu.decode("utf-8", errors="replace").splitlines()


def _lignes_du_depot(depot, relatif):
    chemin, err = constats._fichier_du_depot(Path(depot), relatif)
    return None if err else constats._lignes(chemin)


def copier_arbre(depot: Path, dest: Path, exclus_racine=()):
    """Copie l'arbre de travail sans .git, sans liens symboliques ni fichiers spéciaux, et
    sans les fichiers de la racine qui configureraient l'outil à la place de Raton."""
    depot, total = Path(depot), 0
    for racine, reps, fichiers in os.walk(depot, followlinks=False):
        rel = Path(racine).relative_to(depot)
        reps[:] = [r for r in reps if not (rel == Path(".") and r == ".git") and not os.path.islink(os.path.join(racine, r))]
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for nom in fichiers:
            if rel == Path(".") and nom in exclus_racine:
                continue
            src = Path(racine) / nom
            st = os.lstat(src)
            if not stat.S_ISREG(st.st_mode):
                continue
            total += st.st_size
            if total > TAILLE_DEPOT_MAX:
                raise ErreurFormat(f"dépôt de plus de {TAILLE_DEPOT_MAX // 1_000_000} Mo")
            shutil.copyfile(src, dest / rel / nom)


# --- Demandes d'ignorer adressées aux outils -----------------------------------

# Fichiers lus par l'outil à la racine du dépôt analysé, et marqueurs de ligne. Raton les
# neutralise ; leur présence est un constat. Les autres outils s'ajouteront avec eux.
FICHIERS_SUPPRESSION = {
    "gitleaks": {
        ".gitleaksignore": "une liste de résultats à ignorer",
        ".gitleaks.toml": "une configuration qui remplacerait celle de Raton",
    },
}
MARQUEURS_SUPPRESSION = {
    "gitleaks": re.compile(r"gitleaks:allow"),
}


def _ligne_citable(ligne):
    l = " ".join(masquer_jetons(ligne).split())
    if len(l) > 160:
        l = _couper(l, 160)
    return l if _significatif(l) >= constats.EXTRAIT_MIN else None


def suppressions(depot: Path, outil: str):
    """Constats sur les demandes d'ignorer faites à l'outil par le dépôt (sans identifiant)."""
    depot, res = Path(depot), []
    for nom, effet in FICHIERS_SUPPRESSION.get(outil, {}).items():
        lignes = _lignes_du_depot(depot, nom)
        if lignes is None or (depot / nom).is_symlink():
            continue
        utiles = [(i, l) for i, l in enumerate(lignes, 1) if l.strip() and not l.lstrip().startswith("#")]
        citable = next(((i, c) for i, l in utiles if (c := _ligne_citable(l))), None)
        if not citable:
            continue  # fichier vide ou sans entrée : sans effet
        i, extrait = citable
        res.append({
            "categorie": "injection_relecteurs",
            "severite": "basse",
            "confiance": "elevee",
            "titre": f"Le dépôt contient {nom}, qui demanderait à {outil} d'ignorer des résultats",
            "description": (
                f"{nom} ({len(utiles)} entrée(s)) donnerait à {outil} {effet}. Raton ne l'applique pas : "
                f"il passe sa propre configuration et analyse une copie du dépôt sans ce fichier. "
                "Ce qu'il aurait caché figure donc dans ce rapport."
            ),
            "regle": f"raton:suppression:{outil}",
            "preuves": [{"type": "code", "fichier": nom, "lignes": [i, i], "extrait": extrait}],
        })
    marqueur = MARQUEURS_SUPPRESSION.get(outil)
    if marqueur:
        trouves = []
        for rel, lignes in fichiers_texte(depot):
            for i, l in enumerate(lignes, 1):
                if m := marqueur.search(l):
                    trouves.append((rel, i, m.group(0)))
        if trouves:
            res.append({
                "categorie": "injection_relecteurs",
                "severite": "basse",
                "confiance": "elevee",
                "titre": f"Le code demande à {outil} d'ignorer {len(trouves)} ligne(s)",
                "description": (
                    f"Le marqueur « {trouves[0][2]} » demande à {outil} de ne pas signaler une ligne. Raton passe "
                    "outre : ces lignes ont été analysées comme les autres. Une IA qui fait taire un outil au lieu "
                    "de corriger le problème laisse ce genre de marque."
                    + (f" {len(trouves)} lignes, les {PREUVES_MAX} premières citées." if len(trouves) > PREUVES_MAX else "")
                ),
                "regle": f"raton:suppression:{outil}",
                "preuves": [
                    {"type": "code", "fichier": rel, "lignes": [i, i], "extrait": texte}
                    for rel, i, texte in trouves[:PREUVES_MAX]
                ],
            })
    return res


# --- gitleaks : conversion -----------------------------------------------------

REGLES_GENERIQUES = {"generic-api-key"}  # motif et entropie, sans format de fournisseur
CONFIANCE_REGLES = {"raton-identifiants-url": "moyenne"}
_RANG_CONFIANCE = {"faible": 0, "moyenne": 1, "elevee": 2}


def confiance_regle(regle):
    return "faible" if regle in REGLES_GENERIQUES else CONFIANCE_REGLES.get(regle, "elevee")


class ErreurConversion(Exception):
    pass


def _chemin_relatif(fichier, racines):
    f = str(fichier or "").replace("\\", "/")
    for r in racines:
        r = r.replace("\\", "/").rstrip("/") + "/"
        if f.startswith(r):
            f = f[len(r) :]
            break
    while f.startswith("./"):
        f = f[2:]
    parties = f.split("/")
    if not f or f.startswith("/") or re.match(r"^[A-Za-z]:", f) or ".." in parties or len(f) > 500 or "\0" in f:
        return None
    return f


def _entier(v, defaut=1):
    return v if isinstance(v, int) and v >= 1 else defaut


@dataclass
class _Resultat:
    regle: str
    fichier: str
    debut: int
    fin: int
    secret: str
    match: str
    commit: str | None  # None pour l'arbre du commit relu


def _resultats(brut, racines, historique):
    res, ignores = [], 0
    for r in brut or []:
        if not isinstance(r, dict):
            ignores += 1
            continue
        fichier = _chemin_relatif(r.get("File"), racines)
        commit = str(r.get("Commit") or "")
        if fichier is None or (historique and not re.fullmatch(r"[0-9a-f]{40}", commit)) or r.get("SymlinkFile"):
            ignores += 1
            continue
        secret = str(r.get("Secret") or "").replace("\r\n", "\n")
        if secret == "REDACTED" or secret.endswith("..."):
            raise ErreurConversion("sortie masquée par --redact : relancer gitleaks sans, la conversion masque elle-même")
        debut = _entier(r.get("StartLine"))
        res.append(_Resultat(
            regle=str(r.get("RuleID") or "inconnue")[:100],
            fichier=fichier,
            debut=debut,
            fin=max(debut, _entier(r.get("EndLine"), debut)),
            secret=secret,
            match=str(r.get("Match") or "").replace("\r\n", "\n"),
            commit=commit if historique else None,
        ))
    return res, ignores


def _localiser(lignes, debut, fin, secret):
    """Lignes où le secret figure vraiment, près de celles que donne l'outil."""
    tete = secret.split("\n")[0]
    if not tete:
        return None
    for i in range(max(1, debut - 2), min(len(lignes), fin + 2) + 1):
        if tete in lignes[i - 1]:
            return i, min(len(lignes), i + secret.count("\n"))
    return None


def _extrait_controle(extrait, lignes, debut, fin, tous_secrets):
    """L'extrait est-il probant, retrouvable dans les lignes, et sans secret ?"""
    if not extrait or _significatif(extrait) < constats.EXTRAIT_MIN or extrait.count(MASQUE) > constats.MASQUES_MAX:
        return False
    if any(len(s) >= 4 and s in extrait for s in tous_secrets):
        return False
    return constats.extrait_present(extrait, "\n".join(lignes[debut - 1 : fin]))


def _preuve_arbre(depot, commit, r, secrets_du_fichier, tous_secrets):
    """Preuve de code pour un secret du commit relu ; à défaut d'extrait sûr et probant,
    preuve d'historique au commit relu, sans extrait."""
    repli = {"type": "historique", "commit": commit, "fichier": r.fichier, "lignes": [r.debut, r.fin]}
    lignes = _lignes_du_depot(depot, r.fichier)
    if not lignes:
        return repli
    trouve = _localiser(lignes, r.debut, r.fin, r.secret) if r.secret else None
    debut, fin = trouve or (min(r.debut, len(lignes)), min(r.fin, len(lignes)))
    for d, f in ((debut, fin), (max(1, debut - 1), min(len(lignes), fin + 1))):
        texte = "\n".join(lignes[d - 1 : f])
        texte = masquer(texte, secrets_du_fichier) if trouve else masquer_jetons(masquer(texte, secrets_du_fichier))
        candidats = [texte]
        if len(texte) > EXTRAIT_LONG:  # code minifié, longue clé : la ligne du secret, ou un morceau
            ligne = next((l for l in texte.split("\n") if MASQUE in l), texte.split("\n")[0])
            candidats.insert(0, _fenetre(ligne))
        for extrait in candidats:
            if _extrait_controle(extrait, lignes, d, f, tous_secrets):
                return {"type": "code", "fichier": r.fichier, "lignes": [d, f], "extrait": extrait}
    return repli


def _preuve_historique(r, tous_secrets):
    p = {"type": "historique", "commit": r.commit, "fichier": r.fichier, "lignes": [r.debut, r.fin]}
    if r.secret and r.secret in r.match:
        extrait = masquer(r.match, tous_secrets)
        if len(extrait) > EXTRAIT_LONG:
            extrait = _fenetre(next((l for l in extrait.split("\n") if MASQUE in l), extrait))
        if _significatif(extrait) >= constats.EXTRAIT_MIN and not any(len(s) >= 4 and s in extrait for s in tous_secrets):
            p["extrait"] = extrait
    return p


def _perimetre_gitleaks(arbre, historique, contexte, ignores):
    verifie, non_verifie = [], []
    if arbre is not None:
        verifie.append("fichiers du dépôt au commit relu, hors liens symboliques, règles gitleaks par défaut et règles de Raton")
    else:
        non_verifie.append({"element": "fichiers du dépôt au commit relu", "motif": "analyse de l'arbre non lancée"})
    if historique is not None:
        n = contexte.get("commits")
        verifie.append(f"historique git jusqu'au commit relu ({n} commits)" if n else "historique git jusqu'au commit relu")
        if contexte.get("historique_complet") is False:
            non_verifie.append({"element": "historique antérieur au clone", "motif": "clone superficiel"})
        non_verifie.append({"element": "branches qui ne mènent pas au commit relu", "motif": "seul l'historique du commit relu est parcouru"})
    else:
        non_verifie.append({"element": "historique git", "motif": "analyse de l'historique non lancée"})
    non_verifie += [
        {"element": "secrets sans motif reconnaissable : mot de passe court, valeur sans préfixe", "motif": "détection par motifs et entropie"},
        {"element": "fichiers de plus de 10 Mo, contenu des archives", "motif": "ignorés par la configuration de Raton"},
        {"element": "validité des secrets trouvés", "motif": "aucun appel réseau : la revue ne les essaie pas"},
        {"element": "secrets des dépendances et de l'image construite", "motif": "seul le dépôt est analysé"},
    ]
    if ignores:
        non_verifie.append({"element": f"{ignores} résultat(s) de gitleaks inexploitables", "motif": "chemin hors du dépôt, lien symbolique ou commit illisible"})
    return {"verifie": verifie, "non_verifie": non_verifie}


def rapport_gitleaks(depot, commit, version, arbre=None, historique=None, date=None, contexte=None, racines=()):
    """Rapport « secrets » depuis les sorties JSON de gitleaks (non masquées) sur l'arbre du
    commit relu et sur son historique. Un secret, quel que soit le nombre d'endroits où il
    figure, fait un constat. Les demandes d'ignorer faites à gitleaks s'y ajoutent."""
    if arbre is None and historique is None:
        raise ErreurConversion("ni l'arbre ni l'historique : rien à convertir")
    depot, contexte = Path(depot), contexte or {}
    racines = [str(Path(r).resolve()) for r in racines] + [str(r) for r in racines] + [str(depot.resolve()), str(depot)]
    r_arbre, ign_a = _resultats(arbre, racines, historique=False)
    r_hist, ign_h = _resultats(historique, racines, historique=True)
    tous = r_arbre + r_hist
    tous_secrets = {r.secret for r in tous if r.secret}
    par_fichier = {}
    for r in r_arbre:
        par_fichier.setdefault(r.fichier, set()).add(r.secret)

    groupes = {}
    for r in tous:
        cle = ("s", r.secret) if r.secret else ("l", r.regle, r.fichier, r.debut, r.commit)
        groupes.setdefault(cle, []).append(r)

    liste = []
    for membres in groupes.values():
        present = [r for r in membres if r.commit is None]
        passe = [r for r in membres if r.commit is not None]
        regles = sorted({r.regle for r in membres}, key=lambda x: (x in REGLES_GENERIQUES, x))
        confiance = max((confiance_regle(x) for x in regles), key=_RANG_CONFIANCE.get)
        preuves, vues = [], set()
        for r in present:
            p = _preuve_arbre(depot, commit, r, par_fichier.get(r.fichier, set()), tous_secrets)
            cle_p = (p["fichier"], tuple(p["lignes"]))
            if cle_p not in vues:
                vues.add(cle_p)
                preuves.append(p)
        for r in sorted(passe, key=lambda r: (r.fichier, r.commit, r.debut)):
            cle_p = (r.commit, r.fichier)
            if cle_p not in vues:
                vues.add(cle_p)
                preuves.append(_preuve_historique(r, tous_secrets))
        total = len(preuves)
        preuves = preuves[:PREUVES_MAX]
        fichiers = sorted({r.fichier for r in (present or passe)})
        endroits = ", ".join(fichiers[:5]) + (" …" if len(fichiers) > 5 else "")
        if present:
            titre = f"Secret dans le code (règle gitleaks {regles[0]})"
            description = (
                f"gitleaks a trouvé un secret dans {endroits}. Il figure au commit relu : il partirait en production "
                "avec l'application, et toute personne qui a accès au dépôt peut le lire. Le changer, le retirer du "
                "code, puis le fournir par une variable d'environnement ou un fichier monté."
            )
            if passe:
                description += " Il figure aussi dans l'historique git."
        else:
            premier = min(passe, key=lambda r: (r.fichier, r.commit))
            titre = f"Secret encore lisible dans l'historique git (règle gitleaks {regles[0]})"
            description = (
                f"gitleaks a trouvé un secret dans l'historique git ({endroits}, commit {premier.commit[:12]}). Il n'est "
                "plus dans le code au commit relu, mais toute personne qui a accès au dépôt peut encore le lire. Le "
                "considérer comme compromis et le changer : le retirer de l'historique ne suffit pas."
            )
        if total > PREUVES_MAX:
            description += f" {total} emplacements, les {PREUVES_MAX} premiers cités."
        if confiance == "faible":
            description += " La règle est générique (motif et entropie) : à confirmer par un humain."
        liste.append((0 if present else 1, fichiers[0], {
            "categorie": "secret_expose",
            "severite": "haute",
            "confiance": confiance,
            "titre": titre[:200],
            "description": description[:2000],
            "regle": f"gitleaks:{regles[0]}"[:200],
            "cwe": "CWE-798",
            "preuves": preuves,
        }))
    trouves = [c for _, _, c in sorted(liste, key=lambda t: (t[0], t[1]))] + suppressions(depot, "gitleaks")
    for i, c in enumerate(trouves, 1):
        c["id"] = f"R{i:02d}"
    rapport = {
        "format": "raton/rapport/v0",
        "controle": "secrets",
        "producteur": {"type": "outil", "nom": "gitleaks", "version": str(version)[:100]},
        "commit": commit,
        "date": date or maintenant(),
        "perimetre": _perimetre_gitleaks(arbre, historique, contexte, ign_a + ign_h),
        "constats": [{"id": c.pop("id"), **c} for c in trouves],
    }
    _sans_secret(rapport, tous_secrets)
    return rapport


def _sans_secret(doc, secrets):
    """Dernier filet : aucun secret de 8 caractères ou plus ne doit figurer dans le texte."""
    texte = json.dumps(doc, ensure_ascii=False)
    longs = [s for s in secrets if len(s) >= 8]
    if any(s in texte or json.dumps(s, ensure_ascii=False)[1:-1] in texte for s in longs):
        raise ErreurConversion("un secret apparaîtrait dans la sortie : conversion refusée")


CHAMPS_BRUTS = ("RuleID", "Description", "File", "StartLine", "EndLine", "StartColumn", "EndColumn",
                "Match", "Secret", "Commit", "Entropy", "Date", "Tags", "Fingerprint")


def brut_masque(brut, secrets):
    """Sortie de gitleaks à conserver : valeurs masquées, sans l'identité des auteurs de
    commits ni leurs messages (minimisation : le commit suffit à les retrouver)."""
    res = []
    for r in brut or []:
        if not isinstance(r, dict):
            continue
        e = {k: r[k] for k in CHAMPS_BRUTS if k in r}
        secret = str(r.get("Secret") or "")
        e["Secret"] = MASQUE
        match = str(r.get("Match") or "")
        e["Match"] = masquer(match, secrets) if secret and secret in match else MASQUE
        res.append(e)
    _sans_secret(res, secrets)
    return res


# --- Exécution des outils -------------------------------------------------------


def maintenant():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _environnement(travail):
    """Environnement des outils : rien de celui du job, donc aucun jeton (CI_JOB_TOKEN…),
    et aucune configuration git ou d'outil venue d'ailleurs."""
    return {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(travail),
        "TMPDIR": str(travail),
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }


def _executer(argv, travail, delai=DELAI_OUTIL):
    return subprocess.run(
        [str(a) for a in argv], cwd=travail, env=_environnement(travail), stdin=subprocess.DEVNULL,
        capture_output=True, timeout=delai, check=False,
    )


def _erreur_outil(res):
    texte = (res.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()[-3:]
    return masquer_jetons(" / ".join(texte))[:300] or f"code de sortie {res.returncode}"


def _version(exe, travail):
    try:
        res = _executer([exe, "version"], travail, delai=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"v?(\d+\.\d+\.\d+[0-9A-Za-z.+-]*)", (res.stdout or b"").decode("utf-8", errors="replace"))
    return m.group(1) if m else None


def _charger_json(chemin):
    if not chemin.exists() or chemin.stat().st_size == 0:
        return []
    if chemin.stat().st_size > TAILLE_SORTIE_MAX:
        raise ErreurConversion(f"sortie de plus de {TAILLE_SORTIE_MAX // 1_000_000} Mo")
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(contenu, list):
        raise ErreurConversion("sortie JSON inattendue : une liste de résultats était attendue")
    return contenu


@dataclass
class Resultat:
    controle: str
    statut: str
    motif: str | None = None
    outil: dict | None = None
    rapport: dict | None = None
    bruts: dict = field(default_factory=dict)  # nom de fichier → contenu


def secrets_gitleaks(depot, commit, travail, contexte):
    """Contrôle des secrets : gitleaks sur une copie de l'arbre, puis sur un miroir de
    l'historique. Ni l'une ni l'autre ne porte de .gitleaksignore ou de .gitleaks.toml."""
    exe = shutil.which("gitleaks")
    if not exe:
        return Resultat("secrets", "echec", "gitleaks introuvable dans l'image")
    if not shutil.which("git"):
        return Resultat("secrets", "echec", "git introuvable dans l'image")
    version = _version(exe, travail) or "inconnue"
    outil = {"nom": "gitleaks", "version": version}
    copie, miroir, vide = travail / "arbre", travail / "historique.git", travail / "vide"
    vide.mkdir()
    try:
        copier_arbre(depot, copie, exclus_racine=FICHIERS_SUPPRESSION["gitleaks"])
    except ErreurFormat as e:
        return Resultat("secrets", "echec", str(e), outil)
    clone = _executer(["git", "clone", "--mirror", "--quiet", Path(depot).resolve(), miroir], travail, delai=600)
    if clone.returncode != 0:
        return Resultat("secrets", "echec", f"copie de l'historique impossible : {_erreur_outil(clone)}", outil)
    commun = [
        "--config", REGLES / "gitleaks.toml", "--gitleaks-ignore-path", vide, "--ignore-gitleaks-allow",
        "--report-format", "json", "--exit-code", "0", "--no-banner", "--no-color", "--log-level", "warn",
        "--max-target-megabytes", "10", "--max-decode-depth", "2",
    ]
    sorties = {"arbre": travail / "gitleaks-arbre.json", "historique": travail / "gitleaks-historique.json"}
    for nom, argv in (
        ("arbre", [exe, "dir", copie, *commun, "--report-path", sorties["arbre"]]),
        ("historique", [exe, "git", miroir, f"--log-opts={commit}", *commun, "--report-path", sorties["historique"]]),
    ):
        try:
            res = _executer(argv, vide)
        except subprocess.TimeoutExpired:
            return Resultat("secrets", "echec", f"gitleaks ({nom}) : délai de {DELAI_OUTIL} s dépassé", outil)
        if res.returncode != 0:
            return Resultat("secrets", "echec", f"gitleaks ({nom}) : {_erreur_outil(res)}", outil)
    try:
        arbre, historique = _charger_json(sorties["arbre"]), _charger_json(sorties["historique"])
        rapport = rapport_gitleaks(depot, commit, version, arbre, historique, contexte=contexte, racines=[copie])
        secrets_vus = {str(r.get("Secret") or "") for r in arbre + historique if isinstance(r, dict)} - {""}
        bruts = {
            "gitleaks-arbre.json": brut_masque(arbre, secrets_vus),
            "gitleaks-historique.json": brut_masque(historique, secrets_vus),
        }
    except (ErreurConversion, ValueError) as e:
        return Resultat("secrets", "echec", f"conversion : {e}", outil)
    return Resultat("secrets", "fait", None, outil, rapport, bruts)


OUTILS = {"secrets": secrets_gitleaks}


# --- Bases préparées --------------------------------------------------------------


def _empreinte(chemin):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return f"sha256:{h.hexdigest()}"


DATE_HEURE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})?)?")


def inventaire(rep: Path):
    """Fichiers préparés et leur empreinte. Pour une base Trivy, la date de mise à jour
    que donne son metadata.json."""
    rep, res = Path(rep), []
    for chemin in sorted(p for p in rep.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = chemin.relative_to(rep).as_posix()
        if rel == "inventaire.yaml":
            continue
        e = {"fichier": rel, "empreinte": _empreinte(chemin)}
        if chemin.name == "metadata.json" and chemin.stat().st_size < 10_000:
            try:
                date = str(json.loads(chemin.read_text(encoding="utf-8")).get("UpdatedAt", ""))
            except (ValueError, AttributeError):
                date = ""
            if DATE_HEURE.fullmatch(date):
                e["date"] = date
        res.append(e)
        if len(res) >= BASES_MAX:
            break
    return res


# --- Orchestration -------------------------------------------------------------


def _nombre_de_commits(depot, commit):
    """Commits jusqu'au commit relu, pour le périmètre. git tourne sur notre propre clone,
    avec un environnement et une configuration vides."""
    if not shutil.which("git"):
        return None
    with tempfile.TemporaryDirectory(prefix="raton-git-") as travail:
        try:
            res = _executer(["git", "-C", Path(depot).resolve(), "rev-list", "--count", commit], Path(travail), delai=600)
        except (OSError, subprocess.TimeoutExpired):
            return None
    sortie = (res.stdout or b"").strip()
    return int(sortie) if res.returncode == 0 and sortie.isdigit() and int(sortie) > 0 else None


def _fiche_validee(chemin):
    fiche = charger(chemin)
    erreurs, _ = qualification.valider_document(fiche)
    if erreurs:
        raise ErreurFormat(f"{chemin} : fiche non valide, lancer « qualification.py valider »")
    if "validation" not in fiche:
        raise ErreurFormat(f"{chemin} : fiche sans validation, c'est un brouillon")
    exigences = fiche.get("exigences")
    if not exigences:
        palier = qualification.calculer(fiche).palier
        exigences = {"palier": palier, "controles": qualification.controles_obligatoires(palier)}
    return fiche, exigences


def _ecrire_yaml(chemin, doc):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")


def analyser(depot, commit, fiche_chemin, sortie, bases=None, image=None, application=None):
    """Lance les contrôles déterministes exigés par la fiche et écrit, dans SORTIE, les
    rapports, les sorties masquées des outils et execution.yaml. Renvoie le manifeste."""
    depot, sortie = Path(depot), Path(sortie)
    lu = constats.commit_du_depot(depot)
    if lu != commit:
        raise ErreurFormat(f"{depot} n'est pas au commit {commit} (HEAD : {lu or 'introuvable'})")
    fiche, exigences = _fiche_validee(Path(fiche_chemin))
    code = fiche["application"]["code"]
    if application and application != code:
        raise ErreurFormat(f"la fiche est celle de {code}, pas de {application}")
    contexte = {"historique_complet": not (depot / ".git" / "shallow").exists()}
    if n := _nombre_de_commits(depot, commit):
        contexte["commits"] = n
    manifeste = {
        "format": FORMAT,
        "application": code,
        "commit": commit,
        "date": maintenant(),
        "fiche": {"empreinte": _empreinte(fiche_chemin), "palier": exigences["palier"]},
    }
    if image:
        manifeste["image"] = image[:300]
    manifeste["historique"] = {"complet": contexte["historique_complet"]}
    if "commits" in contexte:
        manifeste["historique"]["commits"] = contexte["commits"]
    if bases:
        manifeste["bases"] = inventaire(Path(bases))
    manifeste["controles"] = []
    for controle in CONTROLES_DETERMINISTES:
        if controle not in exigences["controles"]:
            continue
        if controle not in OUTILS:
            manifeste["controles"].append({"controle": controle, "statut": "non_outille", "motif": "aucun outil ne réalise encore ce contrôle"})
            continue
        with tempfile.TemporaryDirectory(prefix=f"raton-{controle}-") as travail:
            res = OUTILS[controle](depot, commit, Path(travail).resolve(), contexte)
        entree = {"controle": controle}
        if res.outil:
            entree["outil"] = res.outil
        if res.statut == "fait":
            _, erreurs, _ = constats.valider_document(res.rapport)
            if erreurs:
                res.statut, res.motif = "echec", "rapport invalide : " + " ; ".join(erreurs[:3])
        entree["statut"] = res.statut
        if res.statut == "fait":
            nom = f"rapports/{controle}-{res.outil['nom']}.yaml"
            _ecrire_yaml(sortie / nom, res.rapport)
            entree["rapport"] = nom
            if res.bruts:
                entree["brut"] = []
                for fichier, contenu in res.bruts.items():
                    (sortie / "brut").mkdir(parents=True, exist_ok=True)
                    (sortie / "brut" / fichier).write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")
                    entree["brut"].append(f"brut/{fichier}")
            statuts = [s for _, s, _ in constats.verifier(res.rapport, depot)]
            entree["constats"] = len(res.rapport["constats"])
            entree["verification"] = {k: statuts.count(s) for k, s in (("verifies", "verifie"), ("refutes", "refute"), ("non_verifiables", "non_verifiable"))}
        else:
            entree["motif"] = res.motif
        manifeste["controles"].append(entree)
    erreurs = valider_execution(manifeste)
    if erreurs:
        raise ErreurFormat("manifeste invalide : " + " ; ".join(erreurs))
    _ecrire_yaml(sortie / "execution.yaml", manifeste)
    return manifeste


def valider_execution(doc):
    _, erreurs = erreurs_schema(doc, (FORMAT,))
    if erreurs:
        return erreurs
    vus = set()
    for c in doc["controles"]:
        cle = (c["controle"], c.get("outil", {}).get("nom"))
        if cle in vus:
            erreurs.append(f"contrôle {c['controle']} : outil {cle[1]} en double")
        vus.add(cle)
        if c["statut"] == "fait" and sum(c["verification"].values()) != c["constats"]:
            erreurs.append(f"contrôle {c['controle']} : la vérification ne compte pas autant de constats que le rapport")
    return erreurs


# --- Ligne de commande ------------------------------------------------------------


def _dump(doc):
    sys.stdout.write(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False))


def _cmd_analyser(args):
    manifeste = analyser(args.depot, args.commit, args.fiche, args.sortie, args.bases, args.image, args.application)
    code = 0
    for c in manifeste["controles"]:
        detail = c.get("motif") or f"{c['constats']} constat(s), {c['verification']['refutes']} réfuté(s)"
        print(f"{c['controle']} : {c['statut']} ({detail})")
        if c["statut"] == "echec" or (c["statut"] == "fait" and c["verification"]["refutes"]):
            code = 1
    print(f"Écrit dans {args.sortie} ; le pipeline conserve ce répertoire comme artefact.")
    return code


def _cmd_convertir(args):
    arbre = _charger_json(Path(args.arbre)) if args.arbre else None
    historique = _charger_json(Path(args.historique)) if args.historique else None
    _dump(rapport_gitleaks(Path(args.depot), args.commit, args.version, arbre, historique))
    return 0


def _cmd_suppressions(args):
    outils = [args.outil] if args.outil else sorted(FICHIERS_SUPPRESSION.keys() | MARQUEURS_SUPPRESSION.keys())
    trouves = [c for o in outils for c in suppressions(Path(args.depot), o)]
    _dump(trouves)
    return 1 if trouves else 0


def _cmd_inventorier(args):
    _dump(inventaire(Path(args.rep)))
    return 0


def _cmd_valider(args):
    erreurs = valider_execution(charger(Path(args.execution)))
    for e in erreurs:
        print(f"erreur : {e}", file=sys.stderr)
    if not erreurs:
        print("manifeste valide")
    return 1 if erreurs else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="controles.py", description=__doc__.split("\n\n")[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("analyser", help="lancer les contrôles déterministes exigés par la fiche")
    p.add_argument("depot", help="clone du dépôt de l'application, au commit relu, historique compris")
    p.add_argument("--commit", required=True, help="SHA complet du commit relu")
    p.add_argument("--fiche", required=True, help="fiche de qualification validée")
    p.add_argument("--sortie", required=True, help="répertoire des rapports, conservé comme artefact")
    p.add_argument("--bases", help="répertoire préparé par la phase de préparation")
    p.add_argument("--image", help="image d'outillage, nom et digest, pour le manifeste")
    p.add_argument("--application", help="code attendu de l'application, vérifié contre la fiche")
    p.set_defaults(func=_cmd_analyser)
    p = sous.add_parser("convertir", help="convertir une sortie d'outil en rapport")
    p.add_argument("outil", choices=["gitleaks"])
    p.add_argument("--depot", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--version", required=True, help="version de l'outil")
    p.add_argument("--arbre", help="sortie JSON de « gitleaks dir », sans --redact")
    p.add_argument("--historique", help="sortie JSON de « gitleaks git », sans --redact")
    p.set_defaults(func=_cmd_convertir)
    p = sous.add_parser("suppressions", help="demandes d'ignorer faites aux outils par le dépôt")
    p.add_argument("depot")
    p.add_argument("--outil", choices=sorted(FICHIERS_SUPPRESSION.keys() | MARQUEURS_SUPPRESSION.keys()))
    p.set_defaults(func=_cmd_suppressions)
    p = sous.add_parser("inventorier", help="empreintes des bases préparées")
    p.add_argument("rep")
    p.set_defaults(func=_cmd_inventorier)
    p = sous.add_parser("valider", help="valider un manifeste d'exécution")
    p.add_argument("execution")
    p.set_defaults(func=_cmd_valider)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ErreurFormat, ErreurConversion, OSError, ValueError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
