"""Tests de la notation de l'application (note.py).

Lancer depuis la racine du dépôt : python3 -m unittest discover -s tests
"""

import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "plugin" / "scripts"))

import note  # noqa: E402
import raton_formats  # noqa: E402

NOTES = RACINE / "corpus" / "notes-de-frais"
DOC_NOTE = RACINE / "docs" / "formats" / "note.md"
DOC_CONSTATS = RACINE / "docs" / "formats" / "constats.md"
SHA = "4e3d3e49bc553b5ff0d6f7203f4791cf783997fb"


def fiche():
    return raton_formats.charger(NOTES / "qualification.yaml")


def rapport_de_la_doc():
    """Le rapport de revue informée donné en exemple dans le format des constats."""
    blocs = re.findall(r"```yaml\n(.*?)```", DOC_CONSTATS.read_text(encoding="utf-8"), re.S)
    return raton_formats.dates_en_texte(yaml.safe_load(next(b for b in blocs if "raton/rapport/v0" in b)))


def rapport(controle, constats, passe=None, commit=SHA):
    producteur = {"type": "agent", "nom": controle, "modele": "exemple", "passe": passe or 1}
    return {
        "format": "raton/rapport/v0",
        "controle": controle,
        "producteur": producteur,
        "commit": commit,
        "date": "2026-11-17T10:00:00Z",
        "perimetre": {"verifie": ["code"], "non_verifie": [{"element": "exécution", "motif": "statique"}]},
        "constats": constats,
    }


def constat(id_, categorie="vulnerabilite", severite="haute", confiance="elevee", fichier="app/main.py", lignes=(10, 12)):
    return {
        "id": id_,
        "categorie": categorie,
        "severite": severite,
        "confiance": confiance,
        "titre": f"Constat {id_}",
        "description": "description",
        "preuves": [{"type": "code", "fichier": fichier, "lignes": list(lignes), "extrait": "extrait probant"}],
    }


def rapports_du_corrige():
    """Ce que produiraient les contrôles s'ils trouvaient tout le corrigé du cas."""
    attendu = raton_formats.charger(NOTES / "attendu.yaml")
    par_controle = {}
    for c in attendu["constats"]:
        for ctl in c["detecte_par"]:
            c2 = {k: v for k, v in c.items() if k != "detecte_par"}
            par_controle.setdefault(ctl, []).append(c2)
    return [rapport(ctl, cs) for ctl, cs in par_controle.items()]


class TestBareme(unittest.TestCase):
    def test_sans_constat(self):
        points, total, lettre, plafond = note.bareme([])
        self.assertEqual((total, lettre, plafond), (100, "A", None))
        self.assertEqual(set(points.values()), {20})

    def test_chaque_categorie_a_un_axe(self):
        enum = json.loads((raton_formats.SCHEMAS / "constat.schema.json").read_text(encoding="utf-8"))["$defs"]["categorie"]["enum"]
        self.assertEqual(sorted(note.AXE_DE), sorted(enum))

    def test_cout_par_severite_et_plancher(self):
        comptes = [{"categorie": "licence", "severite": s} for s in ("moyenne", "basse")]
        points, total, lettre, _ = note.bareme(comptes)
        self.assertEqual(points["dependances"], 13)
        self.assertEqual((total, lettre), (93, "A"))
        comptes = [{"categorie": "licence", "severite": "moyenne"}] * 6
        points, total, _, _ = note.bareme(comptes)
        self.assertEqual(points["dependances"], 0)
        self.assertEqual(total, 80)

    def test_seuils(self):
        for total, lettre in ((100, "A"), (90, "A"), (89, "B"), (75, "B"), (74, "C"), (60, "C"), (59, "D"), (40, "D"), (39, "E"), (0, "E")):
            with self.subTest(total=total):
                self.assertEqual(note.lettre_du_total(total), lettre)

    def test_plafonds(self):
        _, total, lettre, plafond = note.bareme([{"categorie": "licence", "severite": "haute"}])
        self.assertEqual((total, lettre, plafond), (90, "C", {"lettre": "C", "severite": "haute"}))
        _, total, lettre, plafond = note.bareme([{"categorie": "secret_expose", "severite": "critique"}])
        self.assertEqual((total, lettre, plafond), (80, "E", {"lettre": "E", "severite": "critique"}))

    def test_plafond_sans_effet_si_la_note_est_deja_basse(self):
        comptes = [{"categorie": c, "severite": "critique"} for c in ("licence", "deploiement", "dossier_inexact", "vulnerabilite")]
        comptes.append({"categorie": "flux_non_declare", "severite": "haute"})
        _, total, lettre, _ = note.bareme(comptes)
        self.assertEqual((total, lettre), (10, "E"))


class TestRegroupement(unittest.TestCase):
    def test_meme_probleme_dans_deux_rapports(self):
        rapports = [
            rapport("revue_informee", [constat("R01", severite="moyenne")]),
            rapport("juge", [constat("J07", severite="haute", lignes=(11, 11))]),
        ]
        groupes = note.regrouper(rapports)
        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]["ref"], "juge#1:J07")
        self.assertEqual(groupes[0]["severite"], "haute")
        self.assertEqual(groupes[0]["aussi"], ["revue_informee#1:R01"])

    def test_deux_constats_d_un_meme_rapport_restent_distincts(self):
        groupes = note.regrouper([rapport("secrets", [constat("S1", "secret_expose"), constat("S2", "secret_expose", lignes=(11, 11))])])
        self.assertEqual([g["ref"] for g in groupes], ["secrets#1:S1", "secrets#1:S2"])

    def test_autre_categorie_ou_autre_endroit_distincts(self):
        rapports = [
            rapport("revue_informee", [constat("R01")], passe=1),
            rapport("revue_informee", [constat("R01", "controle_acces"), constat("R02", fichier="app/auth.py")], passe=2),
        ]
        self.assertEqual([g["ref"] for g in note.regrouper(rapports)], ["revue_informee#1:R01", "revue_informee#2:R01", "revue_informee#2:R02"])

    def test_rapports_homonymes(self):
        r = rapport("sast", [constat("X1")])
        r["producteur"] = {"type": "outil", "nom": "opengrep", "version": "1"}
        self.assertEqual(note.prefixes([r, copy.deepcopy(r)]), ["sast", "sast~2"])

    def test_confiance_la_plus_haute_du_groupe(self):
        rapports = [rapport("revue_informee", [constat("R01", confiance="faible")]), rapport("juge", [constat("J01", confiance="moyenne")])]
        self.assertEqual(note.regrouper(rapports)[0]["confiance"], "moyenne")


class TestNoter(unittest.TestCase):
    def test_exemple_de_la_doc(self):
        n = note.noter(fiche(), [rapport_de_la_doc()])
        self.assertEqual((n["total"], n["lettre"], n["provisoire"]), (80, "C", True))
        self.assertEqual(len(n["controles_manquants"]), 11)
        self.assertEqual(n["prochaine_lettre"], {"lettre": "A", "total": 100, "corriger": ["revue_informee#1:R01", "revue_informee#1:R02"]})
        self.assertEqual([c["ref"] for c in n["non_comptes"]], ["revue_informee#1:R03"])

    def test_corrige_complet(self):
        n = note.noter(fiche(), rapports_du_corrige())
        self.assertEqual([c["ref"] for c in n["constats"]], ["revue_informee#1:A01", "revue_informee#1:A02", "revue_informee#1:A03", "juge#1:A04"])
        self.assertEqual(n["constats"][0]["aussi"], ["juge#1:A01", "analyse_dynamique#1:A01"])
        points = {a["axe"]: a["points"] for a in n["axes"]}
        self.assertEqual((points["intention"], points["dossier"]), (0, 15))
        self.assertEqual((n["total"], n["lettre"]), (75, "C"))
        self.assertEqual(n["prochaine_lettre"]["lettre"], "A")
        self.assertEqual(len(n["prochaine_lettre"]["corriger"]), 3)

    def test_soupcon_non_compte(self):
        n = note.noter(fiche(), [rapport("revue_informee", [constat("R01", confiance="faible")])])
        self.assertEqual((n["total"], n["lettre"], n["constats"]), (100, "A", []))
        self.assertIn("confiance faible", n["non_comptes"][0]["motif"])
        self.assertIsNone(n["prochaine_lettre"])

    def test_note_complete_quand_tous_les_controles_ont_tourne(self):
        rapports = [rapport(c, []) for c in fiche()["exigences"]["controles"]]
        n = note.noter(fiche(), rapports)
        self.assertEqual((n["provisoire"], n["controles_manquants"]), (False, []))

    def test_un_seul_commit(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "plusieurs commits"):
            note.noter(fiche(), [rapport("sast", []), rapport("secrets", [], commit="0" * 40)])
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "aucun rapport"):
            note.noter(fiche(), [])

    def test_conforme_au_schema(self):
        for rapports in ([rapport_de_la_doc()], rapports_du_corrige(), [rapport("sast", [])]):
            n = note.noter(fiche(), rapports)
            self.assertEqual(raton_formats.erreurs_schema(n, (note.FORMAT,)), (note.FORMAT, []))


class TestRendu(unittest.TestCase):
    def test_rendu_dans_la_doc(self):
        """Le rendu montré dans docs/formats/note.md est celui du script."""
        md = note.rendre(note.noter(fiche(), [rapport_de_la_doc()]), "Notes de frais")
        doc = DOC_NOTE.read_text(encoding="utf-8")
        bloc = re.search(r"```markdown\n(.*?)```", doc, re.S).group(1)
        self.assertEqual(bloc, md)

    def test_rendu_neutralise_les_titres(self):
        r = rapport("revue_informee", [dict(constat("R01"), titre="[cliquer](https://exemple.invalid) <b>")])
        md = note.rendre(note.noter(fiche(), [r]))
        self.assertIn("\\[cliquer\\](https://exemple.invalid) \\<b\\>", md)

    def test_rendu_note_maximale(self):
        md = note.rendre(note.noter(fiche(), [rapport(c, []) for c in fiche()["exigences"]["controles"]]))
        self.assertIn("# Note A\n", md)
        self.assertIn("La note est au maximum", md)
        self.assertNotIn("Provisoire", md)


class TestLigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = note.main(list(args))
        return code, sortie.getvalue(), erreur.getvalue()

    def ecrire(self, rep, nom, doc):
        chemin = Path(rep) / nom
        chemin.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        return str(chemin)

    def test_noter(self):
        with tempfile.TemporaryDirectory() as rep:
            r = self.ecrire(rep, "r.yaml", rapport_de_la_doc())
            code, sortie, _ = self.lancer("noter", str(NOTES / "qualification.yaml"), r)
            self.assertEqual(code, 0)
            self.assertIn("note C (provisoire)", sortie)
            code, sortie, _ = self.lancer("noter", str(NOTES / "qualification.yaml"), r, "--json")
            self.assertEqual(json.loads(sortie)["lettre"], "C")

    def test_fiche_brouillon_refusee(self):
        brouillon = fiche()
        del brouillon["validation"]
        with tempfile.TemporaryDirectory() as rep:
            code, _, erreur = self.lancer("noter", self.ecrire(rep, "f.yaml", brouillon), self.ecrire(rep, "r.yaml", rapport_de_la_doc()))
        self.assertEqual(code, 2)
        self.assertIn("non validée", erreur)

    def test_rapport_invalide_refuse(self):
        r = rapport_de_la_doc()
        r["constats"][0]["severite"] = "enorme"
        with tempfile.TemporaryDirectory() as rep:
            code, _, _ = self.lancer("noter", str(NOTES / "qualification.yaml"), self.ecrire(rep, "r.yaml", r))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
