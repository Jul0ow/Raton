"""Tests des contrôles déterministes : script controles.py, manifeste d'exécution, image et pipeline.

Lancer depuis la racine du dépôt : python3 -m unittest discover -s tests

gitleaks n'est pas installé dans l'environnement de développement : les conversions sont
testées sur des sorties construites selon le format JSON documenté de gitleaks, et
l'orchestration avec un faux gitleaks qui note ce qu'il reçoit.
"""

import base64
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "plugin" / "scripts"))

import constats  # noqa: E402
import controles  # noqa: E402
import raton_formats  # noqa: E402

FICHE = RACINE / "corpus" / "notes-de-frais" / "qualification.yaml"
DOC = RACINE / "docs" / "controles.md"
DOCKERFILE = RACINE / "ci" / "Dockerfile"
PIPELINE = RACINE / "ci" / "raton.gitlab-ci.yml"
EXIGENCES_PIP = RACINE / "ci" / "requirements-image.txt"

# Valeurs factices, construites pour ressembler à des secrets.
MOT_DE_PASSE = "Sup3rS3cretPassw0rd"
CLE_API = "ak_live_51H8sdfJKL2398sdfkjh23498sdfkjh"
JETON_ANCIEN = "tok_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
JETON_ENCODE = "sk_test_FAKE0123456789abcdefABCDEF"
CORPS_PEM = ["MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9v"]
PEM = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(CORPS_PEM) + "\n-----END PRIVATE KEY-----"
SECRETS = [MOT_DE_PASSE, CLE_API, JETON_ANCIEN, JETON_ENCODE, *CORPS_PEM]

CONFIG_V1 = 'import os\n\nDEBUG = False\n'
CONFIG_V2 = textwrap.dedent(f'''\
    import os

    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://notes:{MOT_DE_PASSE}@db:5432/notes")
    API_KEY = "{CLE_API}"  # gitleaks:allow
    DEBUG = False
''')
ENCODE = f'TOKEN_B64 = "{base64.b64encode(JETON_ENCODE.encode()).decode()}"\n'


def _git(rep, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Auteur", "GIT_AUTHOR_EMAIL": "auteur@example.com",
           "GIT_COMMITTER_NAME": "Auteur", "GIT_COMMITTER_EMAIL": "auteur@example.com",
           "GIT_AUTHOR_DATE": "2026-11-01T10:00:00Z", "GIT_COMMITTER_DATE": "2026-11-01T10:00:00Z",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(rep), *args], env=env, check=True, capture_output=True, text=True).stdout.strip()


def construire_depot(rep: Path):
    """Deux commits : le premier ajoute un .env avec un jeton, le second le retire et met
    un mot de passe, une clé d'API, une clé PEM et un jeton encodé dans le code."""
    rep.mkdir(parents=True, exist_ok=True)
    _git(rep, "init", "-q", "-b", "main")
    (rep / "app").mkdir()
    (rep / "app" / "config.py").write_text(CONFIG_V1, encoding="utf-8")
    (rep / ".env").write_text(f"COMPTA_TOKEN={JETON_ANCIEN}\n", encoding="utf-8")
    _git(rep, "add", "-A")
    _git(rep, "commit", "-q", "-m", "premier")
    premier = _git(rep, "rev-parse", "HEAD")
    (rep / ".env").unlink()
    (rep / "app" / "config.py").write_text(CONFIG_V2, encoding="utf-8")
    (rep / "app" / "encode.py").write_text(ENCODE, encoding="utf-8")
    (rep / "cle.pem").write_text(PEM + "\n", encoding="utf-8")
    (rep / ".gitleaksignore").write_text(f"# ignorés\n{premier}:.env:generic-api-key:1\n", encoding="utf-8")
    (rep / "lien").symlink_to("/etc/hostname")
    _git(rep, "add", "-A")
    _git(rep, "commit", "-q", "-m", "second")
    return premier, _git(rep, "rev-parse", "HEAD")


def sortie_arbre(prefixe=""):
    return [
        {"RuleID": "raton-identifiants-url", "Description": "Identifiants dans une URL", "File": f"{prefixe}app/config.py",
         "StartLine": 3, "EndLine": 3, "StartColumn": 48, "EndColumn": 95, "Secret": MOT_DE_PASSE,
         "Match": f"postgresql://notes:{MOT_DE_PASSE}@db:5432/notes", "Commit": "", "Entropy": 3.9,
         "Author": "", "Email": "", "Date": "", "Message": "", "Tags": [], "Fingerprint": "app/config.py:raton-identifiants-url:3"},
        {"RuleID": "generic-api-key", "Description": "Generic API Key", "File": f"{prefixe}app/config.py",
         "StartLine": 4, "EndLine": 4, "StartColumn": 1, "EndColumn": 50, "Secret": CLE_API,
         "Match": f'API_KEY = "{CLE_API}"', "Commit": "", "Entropy": 4.2, "Tags": [], "Fingerprint": "app/config.py:generic-api-key:4"},
        {"RuleID": "private-key", "Description": "Private Key", "File": f"{prefixe}cle.pem",
         "StartLine": 1, "EndLine": 4, "Secret": PEM, "Match": PEM, "Commit": "", "Entropy": 5.1, "Tags": [],
         "Fingerprint": "cle.pem:private-key:1"},
        {"RuleID": "generic-api-key", "Description": "Generic API Key", "File": f"{prefixe}app/encode.py",
         "StartLine": 1, "EndLine": 1, "Secret": JETON_ENCODE, "Match": f"token {JETON_ENCODE}", "Commit": "",
         "Entropy": 4.0, "Tags": ["decoded:base64", "decode-depth:1"], "Fingerprint": "app/encode.py:generic-api-key:1"},
    ]


def sortie_historique(premier, second):
    return [
        {"RuleID": "generic-api-key", "Description": "Generic API Key", "File": ".env", "StartLine": 1, "EndLine": 1,
         "Secret": JETON_ANCIEN, "Match": f"COMPTA_TOKEN={JETON_ANCIEN}", "Commit": premier, "Entropy": 4.1,
         "Author": "Auteur", "Email": "auteur@example.com", "Date": "2026-11-01T10:00:00Z", "Message": "premier",
         "Tags": [], "Fingerprint": f"{premier}:.env:generic-api-key:1"},
        {"RuleID": "raton-identifiants-url", "Description": "Identifiants dans une URL", "File": "app/config.py",
         "StartLine": 3, "EndLine": 3, "Secret": MOT_DE_PASSE, "Match": f"postgresql://notes:{MOT_DE_PASSE}@db:5432/notes",
         "Commit": second, "Entropy": 3.9, "Author": "Auteur", "Email": "auteur@example.com",
         "Date": "2026-11-01T10:00:00Z", "Message": "second", "Tags": [], "Fingerprint": f"{second}:app/config.py:raton-identifiants-url:3"},
    ]


class DepotTemporaire(unittest.TestCase):
    def setUp(self):
        self._rep = tempfile.TemporaryDirectory()
        self.rep = Path(self._rep.name)
        self.depot = self.rep / "depot"
        self.premier, self.second = construire_depot(self.depot)

    def tearDown(self):
        self._rep.cleanup()

    def rapport(self, arbre=None, historique=None, **kw):
        arbre = sortie_arbre() if arbre is None else arbre
        historique = sortie_historique(self.premier, self.second) if historique is None else historique
        return controles.rapport_gitleaks(self.depot, self.second, "8.30.1", arbre, historique, date="2026-11-13T10:00:00Z", **kw)


class TestConversionGitleaks(DepotTemporaire):
    def test_rapport_valide(self):
        _, erreurs, _ = constats.valider_document(self.rapport())
        self.assertEqual(erreurs, [])

    def test_aucun_secret_dans_le_rapport(self):
        texte = yaml.safe_dump(self.rapport(), allow_unicode=True)
        for s in SECRETS + [base64.b64encode(JETON_ENCODE.encode()).decode()]:
            self.assertNotIn(s, texte)

    def test_un_constat_par_secret(self):
        r = self.rapport()
        secrets = [c for c in r["constats"] if c["categorie"] == "secret_expose"]
        self.assertEqual(len(secrets), 5)  # mot de passe, clé d'API, PEM, jeton encodé, jeton de l'historique
        url = next(c for c in secrets if c["regle"] == "gitleaks:raton-identifiants-url")
        self.assertEqual([p["type"] for p in url["preuves"]], ["code", "historique"])
        self.assertIn("aussi dans l'historique", url["description"])

    def test_preuves_verifiees_contre_le_depot(self):
        r = self.rapport()
        statuts = {cid: s for cid, s, _ in constats.verifier(r, self.depot)}
        par_regle = {c["regle"] + ":" + c["preuves"][0]["fichier"]: statuts[c["id"]] for c in r["constats"]}
        self.assertEqual(par_regle["gitleaks:raton-identifiants-url:app/config.py"], "verifie")
        self.assertEqual(par_regle["gitleaks:generic-api-key:app/config.py"], "verifie")
        self.assertEqual(par_regle["gitleaks:private-key:cle.pem"], "verifie")
        self.assertEqual(par_regle["gitleaks:generic-api-key:app/encode.py"], "verifie")
        self.assertEqual(par_regle["gitleaks:generic-api-key:.env"], "non_verifiable")
        self.assertNotIn("refute", statuts.values())

    def test_secret_de_l_historique(self):
        c = next(c for c in self.rapport()["constats"] if c["preuves"][0]["fichier"] == ".env")
        self.assertIn("historique", c["titre"])
        self.assertEqual(c["preuves"][0]["commit"], self.premier)
        self.assertEqual(c["preuves"][0]["extrait"], "COMPTA_TOKEN=***")
        self.assertEqual(c["severite"], "haute")

    def test_pem_garde_ses_bornes(self):
        c = next(c for c in self.rapport()["constats"] if c["regle"] == "gitleaks:private-key")
        extrait = c["preuves"][0]["extrait"]
        self.assertIn("-----BEGIN PRIVATE KEY-----", extrait)
        self.assertIn("***", extrait)
        self.assertEqual(c["confiance"], "elevee")

    def test_secret_encode_masque_generiquement(self):
        c = next(c for c in self.rapport()["constats"] if c["preuves"][0]["fichier"] == "app/encode.py")
        self.assertEqual(c["preuves"][0]["extrait"], 'TOKEN_B64 = "***"')

    def test_autres_secrets_de_la_ligne_masques(self):
        lignes = (self.depot / "app" / "config.py").read_text().splitlines()
        lignes[2] += f"  # {CLE_API}"
        (self.depot / "app" / "config.py").write_text("\n".join(lignes) + "\n")
        texte = yaml.safe_dump(self.rapport())
        self.assertNotIn(CLE_API, texte)

    def test_confiance_selon_la_regle(self):
        par_regle = {c["regle"]: c["confiance"] for c in self.rapport()["constats"] if c["categorie"] == "secret_expose"}
        self.assertEqual(par_regle["gitleaks:raton-identifiants-url"], "moyenne")
        self.assertEqual(par_regle["gitleaks:generic-api-key"], "faible")
        self.assertEqual(par_regle["gitleaks:private-key"], "elevee")

    def test_regle_specifique_preferee(self):
        arbre = sortie_arbre()
        arbre.append({**arbre[1], "RuleID": "stripe-access-token"})
        c = next(c for c in self.rapport(arbre=arbre)["constats"] if "app/config.py" in c["preuves"][0]["fichier"] and c["preuves"][0]["lignes"] == [4, 4])
        self.assertEqual(c["regle"], "gitleaks:stripe-access-token")
        self.assertEqual(c["confiance"], "elevee")

    def test_chemins_absolus_ramenes_au_depot(self):
        copie = self.rep / "copie"
        r = self.rapport(arbre=sortie_arbre(f"{copie}/"), racines=[copie])
        fichiers = {p["fichier"] for c in r["constats"] for p in c["preuves"]}
        self.assertIn("app/config.py", fichiers)

    def test_chemin_hors_du_depot_ignore(self):
        arbre = sortie_arbre() + [{**sortie_arbre()[0], "File": "/etc/passwd"}, {**sortie_arbre()[0], "File": "../x"}]
        r = self.rapport(arbre=arbre)
        self.assertTrue(any("2 résultat(s)" in e["element"] for e in r["perimetre"]["non_verifie"]))

    def test_sortie_masquee_refusee(self):
        arbre = [{**sortie_arbre()[0], "Secret": "REDACTED", "Match": "postgresql://notes:REDACTED@db"}]
        with self.assertRaisesRegex(controles.ErreurConversion, "--redact"):
            self.rapport(arbre=arbre)

    def test_repli_sans_extrait(self):
        (self.depot / "seul.txt").write_text(f"{CLE_API}\n")
        arbre = [{"RuleID": "generic-api-key", "File": "seul.txt", "StartLine": 1, "EndLine": 1, "Secret": CLE_API, "Match": CLE_API}]
        c = self.rapport(arbre=arbre, historique=[])["constats"][0]
        self.assertEqual(c["preuves"][0], {"type": "historique", "commit": self.second, "fichier": "seul.txt", "lignes": [1, 1]})

    def test_lignes_decalees_retrouvees(self):
        arbre = [{**sortie_arbre()[0], "StartLine": 2, "EndLine": 2}]
        c = self.rapport(arbre=arbre, historique=[])["constats"][0]
        self.assertEqual(c["preuves"][0]["lignes"], [3, 3])

    def test_ligne_minifiee_coupee(self):
        longue = "x=1;" * 400 + f'k="{CLE_API}";' + "y=2;" * 400
        (self.depot / "app.min.js").write_text(longue + "\n")
        arbre = [{"RuleID": "generic-api-key", "File": "app.min.js", "StartLine": 1, "EndLine": 1, "Secret": CLE_API, "Match": f'k="{CLE_API}"'}]
        p = self.rapport(arbre=arbre, historique=[])["constats"][0]["preuves"][0]
        self.assertEqual(p["type"], "code")
        self.assertLessEqual(len(p["extrait"]), 400)
        self.assertTrue(constats.extrait_present(p["extrait"], longue))

    def test_perimetre(self):
        r = self.rapport(contexte={"historique_complet": False, "commits": 2})
        self.assertIn("historique git jusqu'au commit relu (2 commits)", r["perimetre"]["verifie"])
        self.assertTrue(any(e["motif"] == "clone superficiel" for e in r["perimetre"]["non_verifie"]))

    def test_rien_a_convertir(self):
        with self.assertRaises(controles.ErreurConversion):
            controles.rapport_gitleaks(self.depot, self.second, "8.30.1")

    def test_brut_masque(self):
        brut = controles.brut_masque(sortie_historique(self.premier, self.second), set(SECRETS))
        texte = json.dumps(brut)
        for s in SECRETS:
            self.assertNotIn(s, texte)
        self.assertNotIn("auteur@example.com", texte)
        self.assertEqual(brut[0]["Match"], "COMPTA_TOKEN=***")

    def test_cli_convertir(self):
        arbre, hist = self.rep / "a.json", self.rep / "h.json"
        arbre.write_text(json.dumps(sortie_arbre()))
        hist.write_text(json.dumps(sortie_historique(self.premier, self.second)))
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = controles.main(["convertir", "gitleaks", "--depot", str(self.depot), "--commit", self.second,
                                   "--version", "8.30.1", "--arbre", str(arbre), "--historique", str(hist)])
        self.assertEqual(code, 0)
        doc = yaml.safe_load(sortie.getvalue())
        self.assertEqual(doc["producteur"], {"type": "outil", "nom": "gitleaks", "version": "8.30.1"})


class TestSuppressions(DepotTemporaire):
    def test_fichier_et_marqueur(self):
        trouves = controles.suppressions(self.depot, "gitleaks")
        self.assertEqual(len(trouves), 2)
        fichier, marqueur = trouves
        self.assertEqual(fichier["preuves"][0]["fichier"], ".gitleaksignore")
        self.assertEqual(fichier["preuves"][0]["extrait"], "***:.env:generic-api-key:1")
        self.assertEqual(marqueur["preuves"], [{"type": "code", "fichier": "app/config.py", "lignes": [4, 4], "extrait": "gitleaks:allow"}])
        for c in trouves:
            self.assertEqual((c["categorie"], c["severite"]), ("injection_relecteurs", "basse"))

    def test_dans_le_rapport_et_verifiees(self):
        r = self.rapport()
        supp = [c for c in r["constats"] if c["categorie"] == "injection_relecteurs"]
        self.assertEqual(len(supp), 2)
        statuts = {cid: s for cid, s, _ in constats.verifier(r, self.depot)}
        self.assertEqual({statuts[c["id"]] for c in supp}, {"verifie"})

    def test_config_masquee(self):
        (self.depot / ".gitleaks.toml").write_text(f"[[allowlists]]\nregexes = ['''{CLE_API}''']\n")
        trouves = controles.suppressions(self.depot, "gitleaks")
        config = next(c for c in trouves if c["preuves"][0]["fichier"] == ".gitleaks.toml")
        self.assertNotIn(CLE_API, json.dumps(config))

    def test_fichier_vide_sans_effet(self):
        (self.depot / ".gitleaksignore").write_text("# rien\n\n")
        trouves = controles.suppressions(self.depot, "gitleaks")
        self.assertEqual([c["preuves"][0]["fichier"] for c in trouves], ["app/config.py"])

    def test_liens_non_suivis(self):
        (self.depot / "ext").symlink_to(self.rep)
        (self.rep / "dehors.py").write_text("x = 1  # gitleaks:allow\n")
        fichiers = [rel for rel, _ in controles.fichiers_texte(self.depot)]
        self.assertNotIn("lien", fichiers)
        self.assertFalse(any(f.startswith("ext/") for f in fichiers))
        self.assertNotIn(".git/HEAD", fichiers)

    def test_cli(self):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = controles.main(["suppressions", str(self.depot)])
        self.assertEqual(code, 1)
        self.assertEqual(len(yaml.safe_load(sortie.getvalue())), 2)


class TestCopie(DepotTemporaire):
    def test_copie_sans_git_ni_liens_ni_exclus(self):
        dest = self.rep / "copie"
        controles.copier_arbre(self.depot, dest, exclus_racine={".gitleaksignore"})
        noms = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*"))
        self.assertEqual(noms, ["app", "app/config.py", "app/encode.py", "cle.pem"])


FAUX_GITLEAKS = r'''#!/usr/bin/env python3
import json, os, sys
JOURNAL = {journal!r}
ARBRE = {arbre!r}
HISTORIQUE = {historique!r}
ECHEC = {echec!r}
args = sys.argv[1:]
if args and args[0] == "version":
    print("v8.30.1")
    sys.exit(0)
mode, source = args[0], args[1]
rapport = args[args.index("--report-path") + 1]
with open(JOURNAL, "a") as f:
    f.write(json.dumps({{"mode": mode, "source": source, "args": args, "cwd": os.getcwd(), "env": dict(os.environ),
                        "racine": sorted(os.listdir(source))}}) + "\n")
if ECHEC:
    print("panique : configuration illisible", file=sys.stderr)
    sys.exit(3)
resultats = ARBRE if mode == "dir" else HISTORIQUE
for r in resultats:
    if mode == "dir":
        r["File"] = source.rstrip("/") + "/" + r["File"]
with open(rapport, "w") as f:
    json.dump(resultats, f)
'''


class TestAnalyser(DepotTemporaire):
    def setUp(self):
        super().setUp()
        self.bin = self.rep / "bin"
        self.bin.mkdir()
        self.journal = self.rep / "journal.jsonl"
        self.sortie = self.rep / "revue"
        self._env = dict(os.environ)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{os.environ['PATH']}"
        os.environ["CI_JOB_TOKEN"] = "jeton-du-job-a-ne-pas-transmettre"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        super().tearDown()

    def installer_faux(self, echec=False):
        exe = self.bin / "gitleaks"
        exe.write_text(FAUX_GITLEAKS.format(journal=str(self.journal), arbre=sortie_arbre(),
                                            historique=sortie_historique(self.premier, self.second), echec=echec))
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    def appels(self):
        return [json.loads(l) for l in self.journal.read_text().splitlines()]

    def analyser(self, **kw):
        return controles.analyser(self.depot, self.second, FICHE, self.sortie, **kw)

    def test_bout_en_bout(self):
        self.installer_faux()
        m = self.analyser(image="jfrog.example.com/raton/outillage@sha256:" + "0" * 64)
        self.assertEqual(controles.valider_execution(m), [])
        secrets = m["controles"][0]
        self.assertEqual(secrets["controle"], "secrets")
        self.assertEqual(secrets["statut"], "fait")
        self.assertEqual(secrets["outil"], {"nom": "gitleaks", "version": "8.30.1"})
        self.assertEqual(secrets["verification"]["refutes"], 0)
        self.assertEqual(secrets["constats"], 7)
        self.assertEqual(m["historique"], {"complet": True, "commits": 2})
        self.assertEqual(
            [(c["controle"], c["statut"]) for c in m["controles"][1:]],
            [("chaine_approvisionnement", "non_outille"), ("sast", "non_outille"),
             ("identite_acces", "non_outille"), ("palier_kubernetes", "non_outille")],
        )
        self.assertEqual(m["fiche"]["palier"], 3)
        rapport = raton_formats.charger(self.sortie / secrets["rapport"])
        self.assertEqual(constats.valider_document(rapport)[1], [])
        self.assertEqual(raton_formats.charger(self.sortie / "execution.yaml"), m)

    def test_rien_de_secret_dans_la_sortie(self):
        self.installer_faux()
        self.analyser()
        for chemin in self.sortie.rglob("*"):
            if chemin.is_file():
                texte = chemin.read_text()
                for s in SECRETS:
                    self.assertNotIn(s, texte, chemin.name)

    def test_outil_isole_du_depot_et_du_job(self):
        self.installer_faux()
        self.analyser()
        dir_, git = self.appels()
        for appel in (dir_, git):
            self.assertNotIn("CI_JOB_TOKEN", appel["env"])
            self.assertIn("--ignore-gitleaks-allow", appel["args"])
            config = appel["args"][appel["args"].index("--config") + 1]
            self.assertEqual(Path(config), RACINE / "plugin" / "regles" / "gitleaks.toml")
            ignore = Path(appel["args"][appel["args"].index("--gitleaks-ignore-path") + 1])
            self.assertEqual(appel["cwd"], str(ignore))
            self.assertFalse(str(Path(appel["source"])).startswith(str(self.depot)))
        self.assertEqual(dir_["racine"], ["app", "cle.pem"])
        self.assertIn("HEAD", git["racine"])
        self.assertNotIn(".gitleaksignore", git["racine"])
        self.assertIn(f"--log-opts={self.second}", git["args"])

    def test_outil_absent(self):
        m = self.analyser()
        self.assertEqual((m["controles"][0]["statut"], m["controles"][0]["motif"]), ("echec", "gitleaks introuvable dans l'image"))
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            code = controles.main(["analyser", str(self.depot), "--commit", self.second, "--fiche", str(FICHE), "--sortie", str(self.sortie)])
        self.assertEqual(code, 1)

    def test_outil_en_erreur(self):
        self.installer_faux(echec=True)
        c = self.analyser()["controles"][0]
        self.assertEqual(c["statut"], "echec")
        self.assertIn("configuration illisible", c["motif"])
        self.assertFalse((self.sortie / "rapports").exists())

    def test_mauvais_commit(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "n'est pas au commit"):
            controles.analyser(self.depot, self.premier, FICHE, self.sortie)

    def test_mauvaise_application(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "pas de compta"):
            self.analyser(application="compta")

    def test_fiche_brouillon(self):
        brouillon = self.rep / "fiche.yaml"
        fiche = raton_formats.charger(FICHE)
        del fiche["validation"]
        brouillon.write_text(yaml.safe_dump(fiche, allow_unicode=True))
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "brouillon"):
            controles.analyser(self.depot, self.second, brouillon, self.sortie)

    def test_clone_superficiel(self):
        (self.depot / ".git" / "shallow").write_text(self.premier + "\n")
        self.installer_faux()
        m = self.analyser()
        self.assertFalse(m["historique"]["complet"])

    def test_bases(self):
        bases = self.rep / "bases" / "trivy" / "db"
        bases.mkdir(parents=True)
        (bases / "trivy.db").write_bytes(b"base")
        (bases / "metadata.json").write_text('{"Version": 2, "UpdatedAt": "2026-11-13T06:12:34.5Z"}')
        self.installer_faux()
        m = self.analyser(bases=self.rep / "bases")
        par_fichier = {b["fichier"]: b for b in m["bases"]}
        self.assertEqual(par_fichier["trivy/db/metadata.json"]["date"], "2026-11-13T06:12:34.5Z")
        self.assertRegex(par_fichier["trivy/db/trivy.db"]["empreinte"], r"^sha256:[0-9a-f]{64}$")


class TestManifeste(unittest.TestCase):
    def manifeste(self):
        return {
            "format": "raton/execution/v0", "application": "notes-de-frais", "commit": "a" * 40,
            "date": "2026-11-13T10:00:00Z", "fiche": {"empreinte": "sha256:" + "b" * 64, "palier": 3},
            "controles": [{"controle": "secrets", "outil": {"nom": "gitleaks", "version": "8.30.1"}, "statut": "fait",
                           "rapport": "rapports/secrets-gitleaks.yaml", "constats": 1,
                           "verification": {"verifies": 1, "refutes": 0, "non_verifiables": 0}}],
        }

    def test_valide(self):
        self.assertEqual(controles.valider_execution(self.manifeste()), [])

    def test_echec_sans_motif_refuse(self):
        m = self.manifeste()
        m["controles"] = [{"controle": "secrets", "statut": "echec"}]
        self.assertTrue(controles.valider_execution(m))

    def test_fait_sans_rapport_refuse(self):
        m = self.manifeste()
        del m["controles"][0]["rapport"]
        self.assertTrue(controles.valider_execution(m))

    def test_comptes_incoherents(self):
        m = self.manifeste()
        m["controles"][0]["constats"] = 2
        self.assertIn("vérification", controles.valider_execution(m)[0])

    def test_doublon(self):
        m = self.manifeste()
        m["controles"].append(dict(m["controles"][0]))
        self.assertIn("en double", controles.valider_execution(m)[0])

    def test_exemple_de_la_doc(self):
        blocs = re.findall(r"```yaml\n(format: raton/execution/v0\n.*?)```", DOC.read_text(encoding="utf-8"), re.S)
        self.assertEqual(len(blocs), 1)
        exemple = raton_formats.dates_en_texte(yaml.safe_load(blocs[0]))
        self.assertEqual(controles.valider_execution(exemple), [])
        self.assertEqual(exemple["fiche"]["empreinte"], controles._empreinte(FICHE))


class TestInventaire(unittest.TestCase):
    def test_inventaire(self):
        with tempfile.TemporaryDirectory() as rep:
            rep = Path(rep)
            (rep / "a").write_bytes(b"x")
            (rep / "inventaire.yaml").write_text("ignoré")
            (rep / "lien").symlink_to(rep / "a")
            inv = controles.inventaire(rep)
        self.assertEqual(inv, [{"fichier": "a", "empreinte": "sha256:2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"}])


class TestRegles(unittest.TestCase):
    def setUp(self):
        self.config = tomllib.loads((RACINE / "plugin" / "regles" / "gitleaks.toml").read_text(encoding="utf-8"))
        self.regle = next(r for r in self.config["rules"] if r["id"] == "raton-identifiants-url")

    def test_regles_par_defaut_gardees(self):
        self.assertTrue(self.config["extend"]["useDefault"])
        self.assertNotIn("allowlists", self.config)  # aucune exception globale

    def test_identifiants_url(self):
        motif = re.compile(self.regle["regex"])
        m = motif.search(f'DATABASE_URL = "postgresql://notes:{MOT_DE_PASSE}@db:5432/notes"')
        self.assertEqual(m.group(self.regle["secretGroup"]), MOT_DE_PASSE)
        self.assertIsNone(motif.search("https://example.com/chemin:avec@rien"))

    def test_variable_interpolee_exclue(self):
        exceptions = [re.compile(r) for a in self.regle["allowlists"] for r in a["regexes"]]
        for valeur in ("${DB_PASSWORD}", "$PASS", "{password}", "%(password)s"):
            self.assertTrue(any(e.search(valeur) for e in exceptions), valeur)
        self.assertFalse(any(e.search(MOT_DE_PASSE) for e in exceptions))

    def test_syntaxe_re2(self):
        """gitleaks est écrit en Go : ni lookaround ni référence arrière."""
        for r in self.config["rules"]:
            self.assertNotRegex(r["regex"], r"\(\?[=!<]|\\[1-9]")


class TestImageEtPipeline(unittest.TestCase):
    def test_outils_epingles(self):
        texte = DOCKERFILE.read_text(encoding="utf-8")
        self.assertRegex(texte, r"ARG IMAGE_PYTHON=\S+@sha256:[0-9a-f]{64}")
        for outil in ("GITLEAKS", "TRIVY"):
            self.assertRegex(texte, rf"ARG {outil}_VERSION=\d+\.\d+\.\d+")
            for arch in ("AMD64", "ARM64"):
                self.assertRegex(texte, rf"ARG {outil}_SHA256_{arch}=[0-9a-f]{{64}}")
        self.assertRegex(texte, r"USER 10001")
        self.assertIn("--require-hashes", texte)

    def test_dependances_python_epinglees(self):
        texte = EXIGENCES_PIP.read_text(encoding="utf-8")
        paquets = re.findall(r"^([a-z0-9-]+)==\S+ \\$", texte, re.M)
        self.assertEqual(sorted(paquets), ["attrs", "jsonschema", "jsonschema-specifications", "pyyaml", "referencing", "rpds-py"])
        for bloc in re.split(r"\n(?=[a-z])", texte.split("\n\n", 1)[1].strip()):
            self.assertRegex(bloc, r"--hash=sha256:[0-9a-f]{64}")

    def test_pipeline(self):
        doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
        prep, analyse = doc["raton:preparation"], doc["raton:analyse"]
        self.assertEqual(prep["tags"], ["raton-preparation"])
        self.assertEqual(prep["variables"]["GIT_STRATEGY"], "none")
        self.assertEqual(analyse["tags"], ["raton-analyse"])
        self.assertEqual(analyse["needs"], ["raton:preparation"])
        script = "\n".join(analyse["script"])
        self.assertIn("controles.py analyser", script)
        self.assertIn("remote set-url", script)  # le jeton du job ne reste pas dans la configuration du clone
        self.assertEqual(analyse["artifacts"]["when"], "always")


if __name__ == "__main__":
    unittest.main()
