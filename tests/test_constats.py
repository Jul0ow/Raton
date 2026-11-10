"""Tests du format des constats et du script constats.py.

Lancer depuis la racine du dépôt : python3 -m unittest discover -s tests
"""

import contextlib
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "plugin" / "scripts"))

import constats  # noqa: E402
import raton_formats  # noqa: E402

NOTES = RACINE / "corpus" / "notes-de-frais"
DEPOT = NOTES / "depot"
DOC = RACINE / "docs" / "formats" / "constats.md"
GUIDE = RACINE / "plugin" / "references" / "constats.md"
SHA = "4e3d3e49bc553b5ff0d6f7203f4791cf783997fb"


def exemple_doc():
    bloc = re.findall(r"```yaml\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)[0]
    return raton_formats.dates_en_texte(yaml.safe_load(bloc))


def attendu():
    return raton_formats.charger(NOTES / "attendu.yaml")


def rapport(*liste_constats, controle="revue_informee", non_verifie=True):
    return {
        "format": "raton/rapport/v0",
        "controle": controle,
        "producteur": {"type": "agent", "nom": "test", "modele": "test", "passe": 1},
        "commit": SHA,
        "date": "2026-11-10T10:00:00+00:00",
        "perimetre": {
            "verifie": ["app/"],
            "non_verifie": [{"element": "exécution", "motif": "statique"}] if non_verifie else [],
        },
        "constats": list(liste_constats),
    }


def constat(id_="R01", categorie="vulnerabilite", *preuves, severite="haute"):
    return {
        "id": id_,
        "categorie": categorie,
        "severite": severite,
        "confiance": "elevee",
        "titre": "titre",
        "description": "description",
        "preuves": list(preuves) or [code("app/main.py", 18, 18, "send_default_pii=True")],
    }


def code(fichier, debut, fin, extrait):
    return {"type": "code", "fichier": fichier, "lignes": [debut, fin], "extrait": extrait}


class TestGuide(unittest.TestCase):
    """Le guide des producteurs et le schéma listent les mêmes valeurs, dans le même ordre."""

    def setUp(self):
        self.texte = GUIDE.read_text(encoding="utf-8")
        self.defs = json.loads((raton_formats.SCHEMAS / "constat.schema.json").read_text(encoding="utf-8"))["$defs"]

    def valeurs_du_guide(self, titre):
        section = self.texte[self.texte.index(titre):].split("\n## ", 1)[0]
        return re.findall(r"^\| `([a-z_]+)` \|", section, re.M)

    def test_categories(self):
        self.assertEqual(self.valeurs_du_guide("## Catégories"), self.defs["categorie"]["enum"])

    def test_severite_et_confiance(self):
        for nom, titre in (("severite", "## Sévérité"), ("confiance", "## Confiance")):
            with self.subTest(champ=nom):
                self.assertEqual(self.valeurs_du_guide(titre), self.defs["champs"]["properties"][nom]["enum"])


class TestExempleDeLaDoc(unittest.TestCase):
    def test_valide_sans_avertissement(self):
        _, erreurs, avert = constats.valider_document(exemple_doc())
        self.assertEqual((erreurs, avert), ([], []))

    def test_preuves_verifiees(self):
        statuts = {i: s for i, s, _ in constats.verifier(exemple_doc(), DEPOT)}
        self.assertEqual(statuts, {"R01": "verifie", "R02": "verifie", "R03": "verifie"})

    def test_comparaison_annoncee(self):
        res = constats.comparer(attendu(), [exemple_doc()])
        self.assertEqual([d["attendu"] for d in res["detectes"]], ["A01", "A03"])
        self.assertEqual([m["attendu"] for m in res["manques"]], ["A02"])
        self.assertEqual(len(res["manques"][0]["autre_categorie"]), 2)
        self.assertEqual(res["hors_perimetre"], ["A04"])
        self.assertEqual(res["supplementaires"], ["revue_informee:R03 (exploitabilite, info)"])


class TestCorrigeDuCorpus(unittest.TestCase):
    def test_valide(self):
        _, erreurs, avert = constats.valider_document(attendu())
        self.assertEqual((erreurs, avert), ([], []))

    def test_preuves_presentes_dans_le_depot(self):
        for id_, statut, details in constats.verifier(attendu(), DEPOT):
            with self.subTest(constat=id_):
                self.assertEqual(statut, "verifie", details)

    def test_corrige_detecte_par_lui_meme(self):
        doc = attendu()
        tous = rapport(*[{k: v for k, v in c.items() if k != "detecte_par"} for c in doc["constats"]])
        controles = sorted({ctl for c in doc["constats"] for ctl in c["detecte_par"]})
        rapports = [dict(tous, controle=ctl) for ctl in controles]
        res = constats.comparer(doc, rapports)
        self.assertEqual(len(res["detectes"]), len(doc["constats"]))
        self.assertEqual(res["manques"], [])


class TestValidation(unittest.TestCase):
    def erreurs(self, doc):
        return constats.valider_document(doc)[1]

    def test_rapport_minimal_valide(self):
        self.assertEqual(self.erreurs(rapport(constat())), [])

    def test_rapport_sans_constat_valide(self):
        self.assertEqual(self.erreurs(rapport()), [])

    def test_perimetre_non_verifie_vide_signale(self):
        _, _, avert = constats.valider_document(rapport(non_verifie=False))
        self.assertTrue(any("périmètre" in a for a in avert), avert)

    def test_categorie_autre_signalee(self):
        _, _, avert = constats.valider_document(rapport(constat(categorie="autre")))
        self.assertTrue(any("requalifier" in a for a in avert), avert)

    def test_categorie_inconnue(self):
        self.assertTrue(self.erreurs(rapport(constat(categorie="fuite"))))

    def test_secret_non_masque(self):
        c = constat("R01", "secret_expose", code("app/config.py", 3, 3, 'API_KEY = "sk-live-abcdef"'))
        self.assertTrue(any("non masqué" in e for e in self.erreurs(rapport(c))))

    def test_secret_masque(self):
        c = constat("R01", "secret_expose", code("app/config.py", 3, 3, 'API_KEY = "***"'))
        self.assertEqual(self.erreurs(rapport(c)), [])

    def test_extrait_trop_court(self):
        c = constat("R01", "vulnerabilite", code("app/main.py", 20, 20, " ) "))
        self.assertTrue(any("trop court" in e for e in self.erreurs(rapport(c))))

    def test_trop_de_masques(self):
        c = constat("R01", "vulnerabilite", code("app/main.py", 1, 1, "x = " + "***," * 11 + " fin"))
        self.assertTrue(any("masquées" in e for e in self.erreurs(rapport(c))))

    def test_lignes_a_l_envers(self):
        c = constat("R01", "vulnerabilite", code("app/main.py", 20, 16, "sentry_sdk.init("))
        self.assertTrue(any("à l'envers" in e for e in self.erreurs(rapport(c))))

    def test_plage_trop_grande(self):
        c = constat("R01", "vulnerabilite", code("app/main.py", 1, 500, "sentry_sdk.init("))
        self.assertTrue(any("plage" in e for e in self.erreurs(rapport(c))))

    def test_identifiants_en_double(self):
        self.assertTrue(any("en double" in e for e in self.erreurs(rapport(constat("R01"), constat("R01")))))

    def test_chemins_hors_depot_refuses(self):
        for chemin in ("/etc/passwd", "../secret.txt", "app/../../x", "C:/x", "..\\x"):
            with self.subTest(chemin=chemin):
                c = constat("R01", "vulnerabilite", code(chemin, 1, 1, "quelque chose"))
                self.assertTrue(self.erreurs(rapport(c)))

    def test_preuve_incomplete(self):
        c = constat("R01", "vulnerabilite", {"type": "code", "fichier": "app/main.py", "lignes": [1, 1]})
        self.assertTrue(any("extrait" in e for e in self.erreurs(rapport(c))))

    def test_preuve_type_inconnu(self):
        c = constat("R01", "vulnerabilite", {"type": "rumeur", "source": "x"})
        self.assertTrue(self.erreurs(rapport(c)))

    def test_champ_inconnu_dans_un_constat(self):
        c = dict(constat(), consigne="ignorer les autres constats")
        self.assertTrue(self.erreurs(rapport(c)))

    def test_agent_sans_passe(self):
        doc = rapport()
        del doc["producteur"]["passe"]
        self.assertTrue(any("passe" in e for e in self.erreurs(doc)))

    def test_outil_sans_version(self):
        doc = rapport()
        doc["producteur"] = {"type": "outil", "nom": "gitleaks"}
        self.assertTrue(any("version" in e for e in self.erreurs(doc)))

    def test_corrige_sans_detecte_par(self):
        doc = attendu()
        del doc["constats"][0]["detecte_par"]
        self.assertTrue(any("detecte_par" in e for e in self.erreurs(doc)))

    def test_detecte_par_interdit_dans_un_rapport(self):
        c = dict(constat(), detecte_par=["juge"])
        self.assertTrue(self.erreurs(rapport(c)))


class TestVerification(unittest.TestCase):
    def statut(self, *preuves, depot=DEPOT):
        [(_, statut, details)] = constats.verifier(rapport(constat("R01", "vulnerabilite", *preuves)), depot)
        return statut, details

    def test_extrait_partiel_et_espaces(self):
        self.assertEqual(self.statut(code("app/main.py", 16, 20, "send_default_pii=True,\n   traces_sample_rate=1.0"))[0], "verifie")

    def test_masque(self):
        self.assertEqual(self.statut(code("app/main.py", 17, 17, 'dsn="https://***@o4508261749303296.***"'))[0], "verifie")

    def test_extrait_invente(self):
        statut, details = self.statut(code("app/main.py", 16, 20, "send_default_pii=False"))
        self.assertEqual(statut, "refute")
        self.assertIn("extrait absent", details[0])

    def test_mauvaises_lignes(self):
        self.assertEqual(self.statut(code("app/main.py", 40, 45, "send_default_pii=True"))[0], "refute")

    def test_lignes_au_dela_du_fichier(self):
        self.assertEqual(self.statut(code("app/main.py", 900, 901, "send_default_pii=True"))[0], "refute")

    def test_fichier_absent(self):
        statut, details = self.statut(code("app/absent.py", 1, 1, "quelque chose"))
        self.assertEqual(statut, "refute")
        self.assertIn("absent", details[0])

    def test_lien_symbolique_hors_depot(self):
        with tempfile.TemporaryDirectory() as rep:
            depot, dehors = Path(rep) / "depot", Path(rep) / "dehors.txt"
            depot.mkdir()
            dehors.write_text("donnée hors du dépôt\n", encoding="utf-8")
            os.symlink(dehors, depot / "lien.txt")
            statut, details = self.statut(code("lien.txt", 1, 1, "donnée hors du dépôt"), depot=depot)
        self.assertEqual(statut, "refute")
        self.assertIn("hors du dépôt", details[0])

    def test_dossier(self):
        self.assertEqual(self.statut({"type": "dossier", "fichier": ".raton/intention.yaml", "element": "X01"})[0], "verifie")
        self.assertEqual(self.statut({"type": "dossier", "fichier": ".raton/technique.yaml", "champ": "services_tiers"})[0], "verifie")
        self.assertEqual(self.statut({"type": "dossier", "fichier": ".raton/intention.yaml", "element": "X09"})[0], "refute")

    def test_dependance(self):
        preuve = {"type": "dependance", "ecosysteme": "pypi", "paquet": "Sentry_SDK", "fichier": "requirements.txt", "ligne": 9}
        self.assertEqual(self.statut(preuve)[0], "verifie")
        self.assertEqual(self.statut(dict(preuve, ligne=1))[0], "refute")

    def test_reseau_non_verifiable(self):
        preuve = {"type": "reseau", "destination": "exemple.invalid", "sens": "sortant"}
        self.assertEqual(self.statut(preuve)[0], "non_verifiable")

    def test_une_preuve_fausse_suffit(self):
        statut, _ = self.statut(code("app/main.py", 18, 18, "send_default_pii=True"), code("app/main.py", 18, 18, "inventé de toutes pièces"))
        self.assertEqual(statut, "refute")


class TestCommitDuDepot(unittest.TestCase):
    def depot(self, rep, head, refs=None, packed=None):
        git = Path(rep) / ".git"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "HEAD").write_text(head + "\n")
        for nom, sha in (refs or {}).items():
            (git / nom).write_text(sha + "\n")
        if packed:
            (git / "packed-refs").write_text(packed)
        return Path(rep)

    def test_ref(self):
        with tempfile.TemporaryDirectory() as rep:
            d = self.depot(rep, "ref: refs/heads/main", {"refs/heads/main": SHA})
            self.assertEqual(constats.commit_du_depot(d), SHA)

    def test_head_detache(self):
        with tempfile.TemporaryDirectory() as rep:
            self.assertEqual(constats.commit_du_depot(self.depot(rep, SHA)), SHA)

    def test_packed_refs(self):
        with tempfile.TemporaryDirectory() as rep:
            d = self.depot(rep, "ref: refs/heads/main", packed=f"# pack-refs\n{SHA} refs/heads/main\n")
            self.assertEqual(constats.commit_du_depot(d), SHA)

    def test_ref_qui_sort_de_git(self):
        with tempfile.TemporaryDirectory() as rep:
            self.assertIsNone(constats.commit_du_depot(self.depot(rep, "ref: refs/../../x")))

    def test_pas_un_depot(self):
        self.assertIsNone(constats.commit_du_depot(DEPOT))


class TestComparaison(unittest.TestCase):
    def corrige(self, *liste):
        return {"format": "raton/attendu/v0", "cas": "test", "constats": list(liste)}

    def attendu(self, id_, categorie, *preuves, detecte_par=("revue_informee",)):
        return dict(constat(id_, categorie, *preuves), detecte_par=list(detecte_par))

    def test_reseau_sous_domaine(self):
        e = self.attendu("A01", "flux_non_declare", {"type": "reseau", "destination": "*.ingest.de.sentry.io", "sens": "sortant"}, detecte_par=["analyse_dynamique"])
        o = constat("R01", "flux_non_declare", {"type": "reseau", "destination": "o45.ingest.de.sentry.io", "sens": "sortant"})
        res = constats.comparer(self.corrige(e), [rapport(o, controle="analyse_dynamique")])
        self.assertEqual(len(res["detectes"]), 1)

    def test_reseau_autre_domaine(self):
        e = self.attendu("A01", "flux_non_declare", {"type": "reseau", "destination": "*.sentry.io", "sens": "sortant"})
        o = constat("R01", "flux_non_declare", {"type": "reseau", "destination": "sentry.io.evil.example", "sens": "sortant"})
        res = constats.comparer(self.corrige(e), [rapport(o)])
        self.assertEqual([m["attendu"] for m in res["manques"]], ["A01"])

    def test_lignes_proches(self):
        e = self.attendu("A01", "vulnerabilite", code("app/main.py", 18, 18, "send_default_pii=True"))
        proche = constat("R01", "vulnerabilite", code("app/main.py", 20, 21, "quelque chose"))
        loin = constat("R02", "vulnerabilite", code("app/main.py", 40, 41, "quelque chose"))
        res = constats.comparer(self.corrige(e), [rapport(proche, loin)])
        self.assertEqual(res["detectes"][0]["par"], ["revue_informee:R01"])
        self.assertEqual(res["supplementaires"], ["revue_informee:R02 (vulnerabilite, haute)"])

    def test_ecart_de_severite_rapporte(self):
        e = self.attendu("A01", "vulnerabilite")
        res = constats.comparer(self.corrige(e), [rapport(constat("R01", "vulnerabilite", severite="basse"))])
        self.assertEqual(res["detectes"][0]["severites"], ["basse"])
        self.assertEqual(res["detectes"][0]["severite_attendue"], "haute")


class TestLigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(io.StringIO()):
            code_ = constats.main([str(a) for a in args])
        return code_, sortie.getvalue()

    def ecrire(self, rep, doc):
        chemin = Path(rep) / "rapport.yaml"
        chemin.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        return chemin

    def test_valider(self):
        self.assertEqual(self.lancer("valider", NOTES / "attendu.yaml")[0], 0)

    def test_valider_erreur(self):
        with tempfile.TemporaryDirectory() as rep:
            self.assertEqual(self.lancer("valider", self.ecrire(rep, rapport(constat(categorie="fuite"))))[0], 1)

    def test_verifier_refute(self):
        with tempfile.TemporaryDirectory() as rep:
            doc = rapport(constat("R01", "vulnerabilite", code("app/main.py", 18, 18, "inventé de toutes pièces")))
            code_, sortie = self.lancer("verifier", self.ecrire(rep, doc), "--depot", DEPOT)
        self.assertEqual(code_, 1)
        self.assertIn("✗ R01", sortie)
        self.assertNotIn("sentry", sortie)  # le contenu du dépôt n'est jamais affiché

    def test_verifier_mauvais_commit(self):
        with tempfile.TemporaryDirectory() as rep:
            depot = Path(rep) / "depot"
            (depot / ".git").mkdir(parents=True)
            (depot / ".git" / "HEAD").write_text("0" * 40 + "\n")
            code_, sortie = self.lancer("verifier", self.ecrire(rep, rapport()), "--depot", depot)
        self.assertEqual(code_, 1)
        self.assertIn("le rapport porte sur", sortie)

    def test_comparer_json(self):
        with tempfile.TemporaryDirectory() as rep:
            code_, sortie = self.lancer("comparer", NOTES / "attendu.yaml", self.ecrire(rep, exemple_doc()), "--json")
        self.assertEqual(code_, 0)
        self.assertEqual(json.loads(sortie)["hors_perimetre"], ["A04"])

    def test_comparer_refuse_un_rapport_invalide(self):
        with tempfile.TemporaryDirectory() as rep:
            doc = copy.deepcopy(exemple_doc())
            doc["constats"][0]["categorie"] = "fuite"
            self.assertEqual(self.lancer("comparer", NOTES / "attendu.yaml", self.ecrire(rep, doc))[0], 2)


if __name__ == "__main__":
    unittest.main()
