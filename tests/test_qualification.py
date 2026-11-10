"""Tests de la fiche de qualification et du script qualification.py."""

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

import qualification as q  # noqa: E402
import raton_formats  # noqa: E402

NOTES = RACINE / "corpus" / "notes-de-frais"
FICHE = NOTES / "qualification.yaml"
INTENTION = NOTES / "depot" / ".raton" / "intention.yaml"
DOC = RACINE / "docs" / "formats" / "qualification.md"


def fiche():
    return raton_formats.charger(FICHE)


def intention():
    return raton_formats.charger(INTENTION)


def minimale(**kw):
    """Fiche validée la plus basse possible : palier 1, sans donnée personnelle."""
    f = fiche()
    f["donnees_personnelles"] = {"niveau": "non"}
    for axe, _ in q.AXES:
        f["dicp"][axe] = {"niveau": 1, "motif": "sans enjeu"}
    f["exigences"] = {"palier": 1, "controles": q.controles_obligatoires(1)}
    for cle, valeur in kw.items():
        f[cle] = valeur
    return f


def avec_exigences_calculees(f):
    calc = q.calculer(f)
    f["exigences"] = {"palier": calc.palier, "controles": q.controles_obligatoires(calc.palier)}
    return f


class TestCorpusEtDoc(unittest.TestCase):
    def test_fiche_du_corpus_valide(self):
        erreurs, avert = q.valider_document(fiche(), intention())
        self.assertEqual(erreurs, [])
        self.assertEqual(avert, [])

    def test_palier_du_corpus(self):
        calc = q.calculer(fiche())
        self.assertEqual((calc.palier, calc.base, calc.internet), (2, 2, False))
        self.assertEqual(fiche()["exigences"]["controles"], q.controles_obligatoires(2))

    def test_exemple_de_la_doc_identique_au_corpus(self):
        blocs = re.findall(r"```yaml\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)
        exemples = [raton_formats.dates_en_texte(yaml.safe_load(b)) for b in blocs]
        self.assertEqual([e for e in exemples if e.get("format") == q.FORMAT], [fiche()])

    def test_fiche_hors_du_depot_de_l_auteur(self):
        self.assertFalse(list((NOTES / "depot").rglob("qualification.yaml")))


class TestPolitique(unittest.TestCase):
    def test_controles_connus_des_rapports(self):
        constat = json.loads((raton_formats.SCHEMAS / "constat.schema.json").read_text(encoding="utf-8"))
        self.assertLessEqual({c for c, _, _ in q.CONTROLES}, set(constat["$defs"]["controle"]["enum"]))

    def test_controles_du_schema_et_de_la_politique(self):
        enum = raton_formats.schema(q.FORMAT)["$defs"]["controle"]["enum"]
        self.assertEqual(enum, [c for c, _, _ in q.CONTROLES])

    def test_paliers_emboites(self):
        for p in (1, 2):
            self.assertLess(set(q.controles_obligatoires(p)), set(q.controles_obligatoires(p + 1)))

    def test_echelle_complete(self):
        for axe, _ in q.AXES:
            self.assertEqual(sorted(q.ECHELLE[axe]), [1, 2, 3, 4])


class TestCalcul(unittest.TestCase):
    def palier(self, f):
        return q.calculer(f).palier

    def test_palier_1(self):
        self.assertEqual(self.palier(minimale()), 1)

    def test_internet_ajoute_un_palier(self):
        self.assertEqual(self.palier(minimale(exposition="internet")), 2)
        f = fiche()
        f["exposition"] = "internet"
        self.assertEqual(self.palier(f), 3)

    def test_internet_plafonne(self):
        f = minimale(exposition="internet")
        f["utilisateurs"]["populations"] = ["public"]
        self.assertEqual(self.palier(f), 3)

    def test_utilisateurs(self):
        for population, attendu in (("interne", 1), ("externe", 2), ("public", 3)):
            f = minimale()
            f["utilisateurs"]["populations"] = ["interne", population]
            self.assertEqual(self.palier(f), attendu, population)

    def test_donnees_sensibles(self):
        f = fiche()
        f["donnees_personnelles"]["niveau"] = "sensibles"
        self.assertEqual(self.palier(f), 3)

    def test_axes_dicp(self):
        for niveau, attendu in ((1, 1), (2, 1), (3, 2), (4, 3)):
            for axe, _ in q.AXES:
                f = minimale()
                f["dicp"][axe]["niveau"] = niveau
                self.assertEqual(self.palier(f), attendu, (axe, niveau))


class TestValidation(unittest.TestCase):
    def erreurs(self, f, intention=None):
        return q.valider_document(f, intention)[0]

    def avertissements(self, f):
        return q.valider_document(f)[1]

    def test_fiche_minimale_valide(self):
        self.assertEqual(q.valider_document(minimale()), ([], []))

    def test_brouillon_sans_exigences(self):
        f = fiche()
        del f["exigences"], f["validation"]
        erreurs, avert = q.valider_document(f)
        self.assertEqual(erreurs, [])
        self.assertTrue(any("brouillon" in a for a in avert))
        self.assertTrue(any("exigences absentes" in a for a in avert))

    def test_validation_exige_les_exigences(self):
        f = fiche()
        del f["exigences"]
        self.assertTrue(any("exigences" in e for e in self.erreurs(f)))

    def test_palier_sous_le_minimum(self):
        f = fiche()
        f["exigences"] = {"palier": 1, "controles": q.controles_obligatoires(1)}
        erreurs = self.erreurs(f)
        self.assertTrue(any("inférieur au palier calculé 2" in e for e in erreurs), erreurs)
        self.assertTrue(any("revue_aveugle" in e for e in erreurs), erreurs)

    def test_controle_obligatoire_manquant(self):
        f = fiche()
        f["exigences"]["controles"].remove("secrets")
        self.assertTrue(any("absents : secrets" in e for e in self.erreurs(f)))

    def test_palier_releve_exige_justification_et_controles(self):
        f = fiche()
        f["exigences"]["palier"] = 3
        erreurs = self.erreurs(f)
        self.assertTrue(any("analyse_dynamique" in e for e in erreurs), erreurs)
        self.assertTrue(any("justification" in e for e in erreurs), erreurs)
        f["exigences"]["controles"].append("analyse_dynamique")
        f["exigences"]["justification"] = "SDK inconnu embarqué"
        self.assertEqual(self.erreurs(f), [])

    def test_controle_ajoute_exige_justification(self):
        f = fiche()
        f["exigences"]["controles"].append("analyse_dynamique")
        self.assertTrue(any("justification" in e for e in self.erreurs(f)))

    def test_public_suppose_internet(self):
        f = minimale()
        f["utilisateurs"]["populations"] = ["public"]
        f = avec_exigences_calculees(f)
        self.assertTrue(any("Internet" in e for e in self.erreurs(f)))

    def test_validee_par_le_metier_refusee(self):
        for nom in ("Marie Durand", "  marie   DURAND "):
            f = fiche()
            f["validation"]["valide_par"]["nom"] = nom
            self.assertTrue(any("équipe infra" in e for e in self.erreurs(f)), nom)

    def test_validee_par_le_porteur_refusee(self):
        f = fiche()
        f["validation"]["renseigne_par"]["nom"] = "Jean Martin"
        f["validation"]["valide_par"]["nom"] = "Marie Durand"
        self.assertTrue(any("équipe infra" in e for e in self.erreurs(f)))

    def test_registre_obligatoire_avec_donnees(self):
        f = fiche()
        del f["donnees_personnelles"]["registre"]
        self.assertTrue(self.erreurs(f))

    def test_registre_interdit_sans_donnees(self):
        f = minimale()
        f["donnees_personnelles"]["registre"] = {"statut": "a_inscrire"}
        self.assertTrue(self.erreurs(f))

    def test_reference_selon_statut(self):
        f = fiche()
        del f["donnees_personnelles"]["registre"]["reference"]
        self.assertTrue(self.erreurs(f))
        f["donnees_personnelles"]["registre"] = {"statut": "a_inscrire", "reference": "TRT-1"}
        self.assertTrue(self.erreurs(f))

    def test_registre_a_verifier(self):
        f = fiche()
        f["donnees_personnelles"]["registre"] = {"statut": "a_verifier"}
        self.assertTrue(any("registre" in e for e in self.erreurs(f)))
        del f["validation"]
        erreurs, avert = q.valider_document(f)
        self.assertEqual(erreurs, [])
        self.assertTrue(any("registre" in a for a in avert))

    def test_registre_a_inscrire_signale(self):
        f = fiche()
        f["donnees_personnelles"]["registre"] = {"statut": "a_inscrire"}
        self.assertEqual(self.erreurs(f), [])
        self.assertTrue(any("à inscrire" in a for a in self.avertissements(f)))

    def test_signes_de_sous_evaluation(self):
        f = fiche()
        f["dicp"]["confidentialite"]["niveau"] = 1
        self.assertTrue(any("confidentialité 1" in a for a in self.avertissements(f)))
        f = fiche()
        f["donnees_personnelles"]["niveau"] = "sensibles"
        f["dicp"]["confidentialite"]["niveau"] = 2
        f = avec_exigences_calculees(f)
        avert = self.avertissements(f)
        self.assertTrue(any("AIPD" in a for a in avert), avert)
        self.assertTrue(any("inférieure à 3" in a for a in avert), avert)

    def test_niveau_dicp_hors_echelle(self):
        f = fiche()
        f["dicp"]["preuve"]["niveau"] = 5
        self.assertTrue(self.erreurs(f))

    def test_code_invalide(self):
        f = fiche()
        f["application"]["code"] = "Notes de frais"
        self.assertTrue(self.erreurs(f))

    def test_controle_inconnu(self):
        f = fiche()
        f["exigences"]["controles"].append("revue_differentielle")
        self.assertTrue(self.erreurs(f))


class TestRecoupements(unittest.TestCase):
    def test_profil_externe_non_qualifie(self):
        i = intention()
        i["profils"][0]["population"] = "externe"
        erreurs = q.recoupements(fiche(), i)
        self.assertEqual(len(erreurs), 1)
        self.assertIn("P01", erreurs[0])

    def test_profil_externe_couvert(self):
        i = intention()
        i["profils"][0]["population"] = "externe"
        f = fiche()
        f["utilisateurs"]["populations"] = ["interne", "externe"]
        self.assertEqual(q.recoupements(f, i), [])

    def test_donnees_plus_sensibles_dans_l_intention(self):
        i = intention()
        i["donnees"][1]["personnelles"] = "sensibles"
        erreurs = q.recoupements(fiche(), i)
        self.assertEqual(len(erreurs), 1)
        self.assertIn("D02", erreurs[0])

    def test_donnees_personnelles_niees(self):
        f = minimale()
        erreurs = q.valider_document(f, intention())[0]
        self.assertTrue(any("« oui »" in e and "« non »" in e for e in erreurs), erreurs)

    def test_surevaluation_acceptee(self):
        f = copy.deepcopy(fiche())
        f["donnees_personnelles"]["niveau"] = "sensibles"
        self.assertEqual(q.recoupements(f, intention()), [])


class TestRendu(unittest.TestCase):
    def test_rendu_du_corpus(self):
        rendu = q.rendre(fiche())
        self.assertIn("Palier calculé : 2 (renforcé)", rendu)
        self.assertIn("Palier retenu : 2 (renforcé)", rendu)
        self.assertIn("- Revue aveugle par agents", rendu)
        self.assertNotIn("Analyse dynamique", rendu)
        self.assertNotIn("Brouillon", rendu)
        self.assertIn("validée par Paul Lefèvre (Équipe infra)", rendu)

    def test_rendu_brouillon(self):
        f = fiche()
        del f["exigences"], f["validation"]
        rendu = q.rendre(f)
        self.assertIn("Brouillon", rendu)
        self.assertIn("Palier retenu : pas encore fixé", rendu)
        self.assertIn("- Revue aveugle par agents", rendu)

    def test_rendu_signale_les_ajouts(self):
        f = fiche()
        f["exigences"]["controles"].append("analyse_dynamique")
        f["exigences"]["justification"] = "SDK inconnu"
        self.assertIn("Analyse dynamique en bac à sable (au-delà du minimum)", q.rendre(f))

    def test_rendu_internet(self):
        f = fiche()
        f["exposition"] = "internet"
        self.assertIn("plus un pour l'exposition à Internet", q.rendre(f))

    def test_rendu_neutralise_le_texte(self):
        f = fiche()
        f["dicp"]["preuve"]["motif"] = "voir [ici](https://evil.example) | <img src=x>"
        rendu = q.rendre(f)
        for brut in (r"\[ici\]\(", r"<img", r" \| <"):
            self.assertIsNone(re.search(r"(?<!\\)" + brut, rendu), brut)
        self.assertIn("voir \\[ici\\](https://evil.example) \\| \\<img src=x\\>", rendu)


class TestLigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(io.StringIO()):
            code = q.main(list(args))
        return code, sortie.getvalue()

    def test_valider_corpus_avec_intention(self):
        code, sortie = self.lancer("valider", str(FICHE), "--intention", str(INTENTION))
        self.assertEqual(code, 0, sortie)
        self.assertIn("✓", sortie)

    def test_valider_erreur(self):
        f = fiche()
        f["exigences"]["palier"] = 1
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "q.yaml"
            chemin.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
            code, sortie = self.lancer("valider", str(chemin))
        self.assertEqual(code, 1)
        self.assertIn("erreur :", sortie)

    def test_calculer_donne_un_bloc_valide(self):
        f = fiche()
        del f["exigences"], f["validation"]
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "q.yaml"
            chemin.write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf-8")
            code, sortie = self.lancer("calculer", str(chemin))
        self.assertEqual(code, 0)
        bloc = yaml.safe_load(sortie[sortie.index("exigences:") :])
        f.update(bloc)
        self.assertEqual(q.valider_document(f)[0], [])
        self.assertEqual(bloc["exigences"], fiche()["exigences"])

    def test_rendre_refuse_une_fiche_non_conforme(self):
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "q.yaml"
            chemin.write_text("format: raton/qualification/v0\n", encoding="utf-8")
            code, _ = self.lancer("rendre", str(chemin))
        self.assertEqual(code, 2)

    def test_intention_invalide_refusee(self):
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "i.yaml"
            chemin.write_text("format: raton/intention/v0\n", encoding="utf-8")
            code, _ = self.lancer("valider", str(FICHE), "--intention", str(chemin))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
