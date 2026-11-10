"""Chargement et validation des formats Raton, communs aux scripts.

Les fichiers chargés peuvent venir de l'auteur ou d'un agent : ce sont des données
non fiables. Ce module ne fait que les analyser.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import sys
from pathlib import Path

try:
    import yaml
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
except ImportError:  # pragma: no cover
    sys.exit(
        "Dépendances manquantes (pyyaml, jsonschema). "
        "Lancer avec « uv run <script> … » ou installer : pip install pyyaml jsonschema"
    )

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
FORMATS = {
    "raton/intention/v0": "intention.schema.json",
    "raton/technique/v0": "technique.schema.json",
    "raton/rapport/v0": "rapport.schema.json",
    "raton/attendu/v0": "attendu.schema.json",
    "raton/qualification/v0": "qualification.schema.json",
}
TAILLE_MAX = 5_000_000  # octets


class ErreurFormat(Exception):
    pass


# --- Chargement --------------------------------------------------------------


class _Chargeur(yaml.SafeLoader):
    """SafeLoader qui refuse les clés en double : YAML garde silencieusement la
    dernière, ce qui permettrait de montrer une valeur à l'humain et d'en faire
    lire une autre à un outil."""


def _mapping_sans_doublon(chargeur, noeud, deep=False):
    vues = set()
    for cle, _ in noeud.value:
        valeur = chargeur.construct_object(cle, deep=deep)
        try:
            doublon = valeur in vues
        except TypeError:  # clé non hachable : construct_mapping la refusera
            continue
        if doublon:
            raise ErreurFormat(f"ligne {cle.start_mark.line + 1} : clé en double « {valeur} »")
        vues.add(valeur)
    return chargeur.construct_mapping(noeud, deep=deep)


_Chargeur.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_sans_doublon)


def dates_en_texte(valeur):
    """YAML convertit 2026-11-08 en date ; les schémas attendent du texte."""
    if isinstance(valeur, (dt.date, dt.datetime)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {k: dates_en_texte(v) for k, v in valeur.items()}
    if isinstance(valeur, list):
        return [dates_en_texte(v) for v in valeur]
    return valeur


def charger(chemin: Path):
    """Charge un fichier YAML ou JSON (JSON est un sous-ensemble de YAML)."""
    chemin = Path(chemin)
    if chemin.stat().st_size > TAILLE_MAX:
        raise ErreurFormat(f"{chemin} : fichier trop gros")
    try:
        with chemin.open(encoding="utf-8") as f:
            contenu = yaml.load(f, Loader=_Chargeur)
    except yaml.YAMLError as e:
        raise ErreurFormat(f"{chemin} : YAML invalide : {e}") from None
    except UnicodeDecodeError:
        raise ErreurFormat(f"{chemin} : n'est pas du texte UTF-8") from None
    return dates_en_texte(contenu)


# --- Schémas -----------------------------------------------------------------


@functools.cache
def _registre():
    ressources = []
    for chemin in sorted(SCHEMAS.glob("*.schema.json")):
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        ressources.append((contenu["$id"], Resource.from_contents(contenu)))
    return Registry().with_resources(ressources)


@functools.cache
def schema(format_):
    return json.loads((SCHEMAS / FORMATS[format_]).read_text(encoding="utf-8"))


@functools.cache
def _validateur(format_):
    return Draft202012Validator(schema(format_), registry=_registre())


def _chemin_json(erreur):
    return "/".join(str(p) for p in erreur.absolute_path) or "(racine)"


def erreurs_schema(doc, formats):
    """Valide doc contre le schéma de son champ format, parmi les formats acceptés.
    Renvoie (format, erreurs)."""
    if not isinstance(doc, dict) or doc.get("format") not in formats:
        return None, [f"champ « format » absent ou inconnu (attendu : {', '.join(formats)})"]
    format_ = doc["format"]
    erreurs = [
        f"{_chemin_json(e)} : {e.message}"
        for e in sorted(_validateur(format_).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    ]
    return format_, erreurs


# --- Rendu -------------------------------------------------------------------


_MD_SPECIAUX = str.maketrans({c: "\\" + c for c in "\\`*_[]<>|#"})


def md_inerte(texte):
    """Texte de l'auteur rendu inerte en Markdown : pas de lien, d'image, de balise
    ni de mise en forme qui changerait ce que le valideur croit lire."""
    return " ".join(str(texte).split()).translate(_MD_SPECIAUX)


# --- Identifiants -------------------------------------------------------------


def ids(liste):
    return [e.get("id") for e in liste or [] if isinstance(e, dict)]


def doublons(section, liste):
    vus, res = set(), []
    for i in ids(liste):
        if i in vus:
            res.append(f"{section} : identifiant en double {i}")
        vus.add(i)
    return res
