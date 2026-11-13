"""Tests de la matrice de flux, du fichier de plateforme et du script flux.py."""

import contextlib
import copy
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "plugin" / "scripts"))

import dossier  # noqa: E402
import flux  # noqa: E402
import raton_formats  # noqa: E402

CORPUS = RACINE / "corpus"
NOTES = CORPUS / "notes-de-frais"
RATON = NOTES / "depot" / ".raton"
FLUX = RATON / "flux.yaml"
PLATEFORME = CORPUS / "plateforme.yaml"
FICHE = NOTES / "qualification.yaml"
DOC = RACINE / "docs" / "formats" / "flux.md"
DOC_DAT = RACINE / "docs" / "formats" / "dat.md"

SENTRY = {
    "id": "R08",
    "de": {"composant": "C01"},
    "vers": {"service": "T04", "hote": "*.ingest.de.sentry.io"},
    "port": 443,
    "protocole": "https",
}


def matrice():
    return raton_formats.charger(FLUX)


def technique():
    return raton_formats.charger(RATON / "technique.yaml")


def intention():
    return raton_formats.charger(RATON / "intention.yaml")


def fiche():
    return raton_formats.charger(FICHE)


def plateforme(**kw):
    p = raton_formats.charger(PLATEFORME)
    p.update(kw)
    return p


def blocs(chemin):
    return [raton_formats.dates_en_texte(yaml.safe_load(b)) for b in re.findall(r"```yaml\n(.*?)```", chemin.read_text(encoding="utf-8"), re.S)]


def technique_etendue():
    """Partie technique du corpus, plus un worker (C02) et une base déployée dans le namespace (S01)."""
    t = technique()
    t["composants"].append({"id": "C02", "nom": "worker", "libelle": "Traitements", "role": "worker", "technologie": "python", "expose": "aucune"})
    t["stockages"][0]["nom"] = "postgres"
    return t


def technique_exacte():
    """Partie technique exacte du format du DAT, qui liste le SDK Sentry (T04)."""
    return next(b for b in blocs(DOC_DAT) if isinstance(b, dict) and b.get("format") == "raton/technique/v0")


def avec_flux(doc, *nouveaux):
    doc = copy.deepcopy(doc)
    doc["flux"].extend(copy.deepcopy(list(nouveaux)))
    return doc


def un_flux(id_="R09", de=None, vers=None, port=443, protocole="https", **kw):
    f = {"id": id_, "de": de or {"composant": "C01"}, "vers": vers or {"service": "T01", "hote": "autre.example.com"}, "port": port, "protocole": protocole}
    f.update(kw)
    return f


def codes(liste):
    return sorted(code for code, _ in liste)


class TestCorpusEtDoc(unittest.TestCase):
    def test_matrice_du_corpus_valide(self):
        erreurs, avert = flux.valider_document(matrice(), technique(), intention(), fiche())
        self.assertEqual(erreurs, [])
        self.assertEqual(avert, [])

    def test_matrice_du_corpus_sans_ecart(self):
        # Le piège est entre le dossier et le code, pas dans le dossier.
        self.assertEqual(flux.ecarts(matrice(), technique(), intention(), fiche()), [])

    def test_technique_exacte_revele_le_sdk(self):
        res = flux.ecarts(matrice(), technique_exacte(), intention(), fiche())
        self.assertEqual(codes(res), ["service_sans_flux"])
        self.assertTrue(res[0][1].startswith("T04"))

    def test_flux_sentry_non_declare(self):
        doc = avec_flux(matrice(), SENTRY)
        erreurs, avert = flux.valider_document(doc, technique_exacte(), intention(), fiche())
        self.assertEqual(erreurs, [])
        self.assertEqual(len(avert), 1)
        self.assertIn("joker", avert[0])
        res = flux.ecarts(doc, technique_exacte(), intention(), fiche())
        self.assertEqual(codes(res), ["flux_sans_echange", "flux_sans_interconnexion"])
        self.assertTrue(all("*.ingest.de.sentry.io:443" in m for _, m in res))

    def test_exemples_de_la_doc_identiques_au_corpus(self):
        exemples = [b for b in blocs(DOC) if isinstance(b, dict) and "format" in b]
        self.assertEqual([e for e in exemples if e["format"] == flux.FORMAT], [matrice()])
        self.assertEqual([e for e in exemples if e["format"] == flux.FORMAT_PLATEFORME], [plateforme()])

    def test_fragment_sentry_de_la_doc(self):
        fragment = next(b for b in blocs(DOC) if isinstance(b, list) and b[0].get("id") == "R08")
        self.assertEqual(fragment, [SENTRY])

    def test_extraits_generes_de_la_doc(self):
        objets, _ = flux.generer(matrice(), plateforme(), technique())
        par_nom = {o["metadata"]["name"]: o for o in objets}
        np_doc = next(b for b in blocs(DOC) if isinstance(b, dict) and b.get("kind") == "NetworkPolicy")
        self.assertEqual(np_doc, par_nom[np_doc["metadata"]["name"]])
        regle = next(b for b in blocs(DOC) if isinstance(b, list) and "toFQDNs" in b[0])
        self.assertIn(regle[0], par_nom["raton-noms-api"]["spec"]["egress"])
        self.assertEqual(len(par_nom["raton-noms-api"]["spec"]["egress"]), 6)

    def test_meme_commit_que_la_technique(self):
        self.assertEqual(matrice()["commit"], technique()["source"]["commit"])

    def test_dossier_valide_la_matrice(self):
        resultats = dossier.valider_chemin(RATON)
        par_nom = {f.name: (e, a) for f, e, a in resultats}
        self.assertEqual(par_nom["flux.yaml"], ([], []))

    def test_dossier_signale_une_reference_inconnue(self):
        with tempfile.TemporaryDirectory() as rep:
            for nom in ("intention.yaml", "technique.yaml"):
                (Path(rep) / nom).write_text((RATON / nom).read_text(encoding="utf-8"), encoding="utf-8")
            doc = avec_flux(matrice(), un_flux(vers={"service": "T09", "hote": "x.example.com"}))
            (Path(rep) / "flux.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
            resultats = dossier.valider_chemin(Path(rep))
        erreurs = {f.name: e for f, e, _ in resultats}["flux.yaml"]
        self.assertEqual(erreurs, ["flux R09 : T09 absent de la partie technique"])


class TestSchema(unittest.TestCase):
    def erreurs_extremite(self, ext):
        doc = avec_flux(matrice(), un_flux(vers=ext))
        _, erreurs = raton_formats.erreurs_schema(doc, (flux.FORMAT,))
        return erreurs

    def test_extremites_valides(self):
        for ext in (
            {"composant": "C02"},
            {"stockage": "S01"},
            {"stockage": "S01", "cidr": "10.0.0.0/28"},
            {"service": "T01", "variable": "API_URL"},
            {"systeme": "Partenaire", "cidr": "203.0.113.0/24"},
            {"plateforme": "sso"},
            {"service": "T01", "hote": "*.exemple.com"},
        ):
            with self.subTest(ext=ext):
                self.assertEqual(self.erreurs_extremite(ext), [])

    def test_extremites_refusees(self):
        for ext in (
            {"composant": "C01", "hote": "a.example.com"},
            {"plateforme": "sso", "hote": "sso.example.com"},
            {"service": "T01"},
            {"systeme": "Partenaire"},
            {"service": "T01", "hote": "a.example.com", "cidr": "10.0.0.0/8"},
            {"service": "T01", "composant": "C01", "hote": "a.example.com"},
            {"hote": "a.example.com"},
            {"service": "T01", "hote": "**.example.com"},
            {"service": "T01", "hote": "a.*.example.com"},
            {"service": "T01", "hote": "10.0.0.1"},
            {"service": "T01", "hote": "https://a.example.com/chemin"},
            {"service": "T01", "hote": "A.example.com"},
            {"plateforme": "dns"},
        ):
            with self.subTest(ext=ext):
                self.assertNotEqual(self.erreurs_extremite(ext), [])

    def test_identifiant_et_port(self):
        for champ, valeur in (("id", "F01"), ("port", 0), ("port", 70000), ("protocole", "ftp")):
            with self.subTest(champ=champ):
                doc = avec_flux(matrice(), un_flux(**{champ: valeur}) if champ != "id" else un_flux(id_=valeur))
                _, erreurs = raton_formats.erreurs_schema(doc, (flux.FORMAT,))
                self.assertNotEqual(erreurs, [])

    def test_renvois_facultatifs_pour_l_aveugle(self):
        doc = matrice()
        for f in doc["flux"]:
            f.pop("echanges", None)
            f.pop("interconnexions", None)
        self.assertEqual(flux.valider_document(doc, technique()), ([], []))

    def test_plateforme_du_corpus_valide(self):
        self.assertEqual(flux.valider_plateforme(plateforme()), [])

    def test_plateforme_refusee(self):
        for cle, valeur in (
            ("cni", "calico"),
            ("services", {"sso": {"hotes": ["sso.example.com"], "cidrs": ["10.0.0.0/8"]}}),
            ("services", {"dns": {"hotes": ["x.example.com"]}}),
            ("services", {"journalisation": {"cidrs": ["10.0.0.1/24"]}}),
            ("dns", {"namespace": "Kube_System", "pods": {"a": "b"}}),
        ):
            with self.subTest(cle=cle, valeur=valeur):
                self.assertNotEqual(flux.valider_plateforme(plateforme(**{cle: valeur})), [])


class TestRegles(unittest.TestCase):
    def valider(self, *nouveaux, **refs):
        return flux.valider_document(avec_flux(matrice(), *nouveaux), **refs)

    def test_un_composant_au_moins(self):
        erreurs, _ = self.valider(un_flux(de={"plateforme": "entree_interne"}, vers={"stockage": "S01"}))
        self.assertIn("flux R09 : ni l'origine ni la destination n'est un composant de l'application", erreurs)

    def test_sens_des_services_de_plateforme(self):
        erreurs, _ = self.valider(
            un_flux("R09", de={"plateforme": "sso"}, vers={"composant": "C01"}),
            un_flux("R10", vers={"plateforme": "entree_externe"}),
        )
        self.assertEqual(len(erreurs), 2)
        self.assertIn("ne peut être qu'une destination", erreurs[0])
        self.assertIn("ne peut être qu'une origine", erreurs[1])

    def test_stockage_jamais_a_l_origine(self):
        erreurs, _ = self.valider(un_flux(de={"stockage": "S01"}, vers={"composant": "C01"}))
        self.assertIn("flux R09 : un stockage reçoit des connexions, il n'en ouvre pas", erreurs)

    def test_bloc_invalide(self):
        erreurs, _ = self.valider(un_flux(vers={"service": "T01", "cidr": "10.0.0.1/24"}))
        self.assertIn("flux R09 : destination : bloc d'adresses invalide « 10.0.0.1/24 »", erreurs)

    def test_identifiant_en_double(self):
        erreurs, _ = self.valider(un_flux("R01"))
        self.assertIn("flux : identifiant en double R01", erreurs)

    def test_avertissements(self):
        _, avert = self.valider(
            un_flux("R09", vers={"service": "T01", "variable": "API_URL"}),
            un_flux("R10", de={"systeme": "Partenaire", "hote": "partenaire.example.com"}, vers={"composant": "C01"}),
        )
        self.assertEqual(len(avert), 2)
        self.assertIn("adresse à fixer", avert[0])
        self.assertIn("API_URL", avert[0])
        self.assertIn("ne peut pas être filtrée", avert[1])

    def test_references(self):
        doc = avec_flux(
            matrice(),
            un_flux("R09", de={"composant": "C07"}, vers={"stockage": "S09"}, protocole="postgresql", port=5432),
            un_flux("R10", echanges=["E09"], interconnexions=["I09"]),
        )
        doc["application"] = "autre"
        doc["commit"] = "0" * 40
        erreurs, _ = flux.valider_document(doc, technique(), intention(), fiche())
        self.assertEqual(
            erreurs,
            [
                "flux R09 : C07 absent de la partie technique",
                "flux R09 : S09 absent de la partie technique",
                "flux R10 : échange E09 absent de l'intention",
                "flux R10 : interconnexion I09 absente de la fiche de qualification",
                f"commit : {'0' * 40}, alors que la partie technique décrit {technique()['source']['commit']}",
                "application : « autre » au lieu de « notes-de-frais », le code de la fiche de qualification",
            ],
        )


class TestEcarts(unittest.TestCase):
    def ecarts(self, doc, **kw):
        refs = {"technique": technique(), "intention": intention(), "qualification": fiche()}
        refs.update(kw)
        return flux.ecarts(doc, **refs)

    def sans(self, *ids):
        doc = matrice()
        doc["flux"] = [f for f in doc["flux"] if f["id"] not in ids]
        return doc

    def test_echange_et_interconnexion_sans_flux(self):
        res = self.ecarts(self.sans("R05"))
        self.assertEqual(codes(res), ["echange_sans_flux", "interconnexion_sans_flux", "service_sans_flux"])

    def test_stockage_sans_flux(self):
        self.assertEqual(codes(self.ecarts(self.sans("R03"))), ["stockage_sans_flux"])

    def test_interconnexion_hors_echange(self):
        doc = matrice()
        doc["flux"][4]["interconnexions"] = ["I01", "I03"]
        res = self.ecarts(doc)
        self.assertEqual(codes(res), ["interconnexion_hors_echange"])
        self.assertIn("passe par I03, que ses échanges (E01) ne citent pas", res[0][1])

    def test_exposition_sous_evaluee(self):
        doc = matrice()
        doc["flux"][0]["de"] = {"plateforme": "entree_externe"}
        self.assertEqual(codes(self.ecarts(doc)), ["exposition_incoherente", "exposition_incoherente", "exposition_sous_evaluee"])
        f = fiche()
        f["exposition"] = "externe"
        t = technique()
        t["composants"][0]["expose"] = "externe"
        self.assertEqual(self.ecarts(doc, technique=t, qualification=f), [])

    def test_composant_expose_sans_entree(self):
        self.assertEqual(codes(self.ecarts(self.sans("R01"))), ["exposition_incoherente"])

    def test_entree_interne_permise_pour_un_composant_expose_a_l_exterieur(self):
        doc = avec_flux(matrice(), un_flux("R09", de={"plateforme": "entree_externe"}, vers={"composant": "C01"}, port=8000, protocole="http"))
        f, t = fiche(), technique()
        f["exposition"] = "externe"
        t["composants"][0]["expose"] = "externe"
        self.assertEqual(self.ecarts(doc, technique=t, qualification=f), [])

    def test_composant_non_expose(self):
        t = technique()
        t["composants"][0]["expose"] = "aucune"
        res = self.ecarts(matrice(), technique=t)
        self.assertEqual(codes(res), ["exposition_incoherente"])
        self.assertIn("depuis entree_interne", res[0][1])

    def test_en_clair_et_bloc_large(self):
        doc = avec_flux(
            matrice(),
            un_flux("R09", vers={"stockage": "S02", "hote": "s3.example.com"}, protocole="http", port=80),
            un_flux("R10", vers={"stockage": "S01", "cidr": "10.0.0.0/8"}, protocole="postgresql", port=5432),
            un_flux("R11", vers={"composant": "C02"}, protocole="http", port=8080),
        )
        res = self.ecarts(doc, technique=None, intention=None, qualification=None)
        self.assertEqual(codes(res), ["bloc_large", "flux_en_clair"])
        self.assertIn("16777216 adresses", dict(res)["bloc_large"])

    def test_sans_dossier_rien_a_couvrir(self):
        self.assertEqual(flux.ecarts(avec_flux(matrice(), SENTRY)), [])


class TestRendu(unittest.TestCase):
    def test_sections_et_renvois(self):
        md = flux.rendre(matrice(), technique())
        self.assertIn("## Connexions reçues par l'application", md)
        self.assertIn("| R01 | entrée des utilisateurs, réseau de l'entreprise | API notes de frais (C01) | 8000 (http) |", md)
        self.assertIn("échange E02 ; interconnexion I02", md)
        self.assertIn("## Connexions entre ses composants\n\nAucune.", md)

    def test_grille_des_composants(self):
        md = flux.rendre(matrice(), technique_etendue())
        self.assertIn("| Identifiant | Nom des pods | Libellé |", md)
        self.assertIn("| C01 | api | API notes de frais |", md)
        self.assertIn("| C02 | worker | Traitements |", md)
        self.assertIn("| S01 | postgres | postgresql |", md)
        self.assertNotIn("Nom des pods", flux.rendre(matrice()))

    def test_textes_inertes(self):
        doc = avec_flux(
            matrice(),
            un_flux("R09", de={"systeme": "[clic](https://exemple.invalid) <b>", "cidr": "203.0.113.0/24"}, vers={"composant": "C01"}, motif="# titre"),
            SENTRY,
        )
        md = flux.rendre(doc)
        self.assertIn("\\[clic\\](https://exemple.invalid) \\<b\\>", md)
        self.assertIn("\\# titre", md)
        self.assertIn("\\*.ingest.de.sentry.io", md)
        self.assertNotIn("](https", md.replace("\\](https", ""))

    def test_adresse_a_fixer_et_stockage_interne(self):
        doc = avec_flux(
            matrice(),
            un_flux("R09", vers={"service": "T01", "variable": "API_URL"}),
            un_flux("R10", vers={"stockage": "S01"}, protocole="postgresql", port=5432),
        )
        md = flux.rendre(doc)
        self.assertIn("| T01 — adresse à fixer (variable API_URL) |", md)
        self.assertIn("| R10 | C01 | S01 — dans le namespace |", md)


class TestGeneration(unittest.TestCase):
    def generer(self, doc=None, technique_=None, **kw):
        return flux.generer(doc or matrice(), plateforme(**kw), technique_ or technique_etendue())

    def test_corpus_avec_cilium(self):
        objets, avert = self.generer()
        self.assertEqual(avert, [])
        self.assertEqual(
            [(o["kind"], o["metadata"]["name"]) for o in objets],
            [
                ("NetworkPolicy", "raton-refus-par-defaut"),
                ("CiliumNetworkPolicy", "raton-dns"),
                ("NetworkPolicy", "raton-api"),
                ("CiliumNetworkPolicy", "raton-noms-api"),
            ],
        )
        self.assertEqual(objets[0]["spec"], {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]})
        self.assertTrue(all(o["metadata"]["namespace"] == "notes-de-frais" for o in objets))
        dns = objets[1]["spec"]["egress"][0]
        self.assertEqual(dns["toPorts"][0]["rules"], {"dns": [{"matchPattern": "*"}]})
        noms = [r["toFQDNs"] for r in objets[3]["spec"]["egress"]]
        self.assertIn([{"matchName": "sso.example.com"}], noms)
        self.assertIn([{"matchName": "compta.example.com"}], noms)

    def test_chaque_flux_est_trace(self):
        objets, _ = self.generer()
        traces = {fid for o in objets for fid in o["metadata"]["annotations"].get("raton/flux", "").split()}
        self.assertEqual(traces, {f["id"] for f in matrice()["flux"]})

    def test_le_sdk_omis_n_est_pas_autorise(self):
        objets, _ = self.generer()
        self.assertNotIn("sentry", yaml.safe_dump_all(objets))

    def test_joker_en_motif(self):
        objets, _ = self.generer(avec_flux(matrice(), SENTRY))
        regles = objets[-1]["spec"]["egress"]
        self.assertIn([{"matchPattern": "*.ingest.de.sentry.io"}], [r["toFQDNs"] for r in regles])

    def test_standard_sans_proxy(self):
        objets, avert = self.generer(cni="standard")
        self.assertEqual([o["kind"] for o in objets], ["NetworkPolicy"] * 3)
        self.assertEqual(objets[1]["spec"]["egress"][0]["ports"], [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}])
        self.assertEqual(len(avert), 6)
        self.assertTrue(all("flux bloqué" in a for a in avert))
        self.assertNotIn("egress", objets[2]["spec"])

    def test_standard_avec_proxy(self):
        proxy = {"namespace": "proxy-sortant", "pods": {"app": "proxy"}, "port": 3128}
        objets, avert = self.generer(cni="standard", proxy_sortant=proxy)
        np_api = objets[2]
        self.assertEqual(np_api["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(np_api["spec"]["egress"][0]["ports"], [{"protocol": "TCP", "port": 3128}])
        self.assertEqual(np_api["metadata"]["annotations"]["raton/flux"], "R01 R02 R04 R05 R06 R07")
        self.assertEqual(len([a for a in avert if "proxy sortant" in a]), 5)
        self.assertIn("R03 : notes-de-frais.postgres.example.com : non généré, postgresql ne passe pas par un proxy HTTP", avert[1])

    def test_bloc_d_adresses_et_flux_interne(self):
        doc = matrice()
        doc["flux"][2]["vers"] = {"stockage": "S01", "cidr": "10.20.30.0/28"}
        doc = avec_flux(doc, un_flux("R09", vers={"composant": "C02"}, port=9000, protocole="grpc"))
        objets, _ = self.generer(doc)
        par_nom = {o["metadata"]["name"]: o for o in objets}
        egress = par_nom["raton-api"]["spec"]["egress"]
        self.assertIn({"to": [{"ipBlock": {"cidr": "10.20.30.0/28"}}], "ports": [{"protocol": "TCP", "port": 5432}]}, egress)
        self.assertIn({"to": [{"podSelector": {"matchLabels": {"app.kubernetes.io/component": "worker"}}}], "ports": [{"protocol": "TCP", "port": 9000}]}, egress)
        self.assertEqual(
            par_nom["raton-worker"]["spec"],
            {
                "podSelector": {"matchLabels": {"app.kubernetes.io/component": "worker"}},
                "policyTypes": ["Ingress"],
                "ingress": [{"from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/component": "api"}}}], "ports": [{"protocol": "TCP", "port": 9000}]}],
            },
        )
        self.assertEqual(par_nom["raton-worker"]["metadata"]["annotations"]["raton/composant"], "C02 — Traitements")

    def test_stockage_dans_le_namespace_et_journalisation(self):
        doc = matrice()
        doc["flux"][2]["vers"] = {"stockage": "S01"}
        doc = avec_flux(doc, un_flux("R09", vers={"plateforme": "journalisation"}, port=514, protocole="udp"))
        par_nom = {o["metadata"]["name"]: o for o in self.generer(doc)[0]}
        self.assertIn("raton-postgres", par_nom)
        self.assertEqual(par_nom["raton-postgres"]["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 5432}])
        self.assertEqual(par_nom["raton-postgres"]["metadata"]["annotations"]["raton/composant"], "S01 — postgresql")
        self.assertIn({"to": [{"ipBlock": {"cidr": "10.10.20.0/24"}}], "ports": [{"protocol": "UDP", "port": 514}]}, par_nom["raton-api"]["spec"]["egress"])

    def test_origine_par_nom_non_autorisee(self):
        doc = avec_flux(matrice(), un_flux("R09", de={"systeme": "Partenaire", "hote": "p.example.com"}, vers={"composant": "C01"}))
        objets, avert = self.generer(doc)
        self.assertEqual(len(avert), 1)
        self.assertIn("R09 : origine désignée par un nom", avert[0])
        self.assertNotIn("R09", " ".join(o["metadata"]["annotations"].get("raton/flux", "") for o in objets))

    def test_adresse_inconnue(self):
        doc = avec_flux(matrice(), un_flux(vers={"service": "T01", "variable": "API_URL"}))
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "R09 : adresse inconnue"):
            self.generer(doc)

    def test_service_absent_de_la_plateforme(self):
        doc = avec_flux(matrice(), un_flux(vers={"plateforme": "secrets"}))
        p = plateforme()
        del p["services"]["secrets"]
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "ne décrit pas le service secrets"):
            flux.generer(doc, p, technique())

    def test_stockage_du_namespace_sans_nom(self):
        doc = matrice()
        doc["flux"][2]["vers"] = {"stockage": "S01"}
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "R03 : S01 n'a pas de nom dans la partie technique"):
            self.generer(doc, technique())
        erreurs, _ = flux.valider_document(doc, technique())
        self.assertEqual(erreurs, ["flux R03 : S01 est déployé dans le namespace, il lui faut un nom dans la partie technique"])

    def test_nom_reserve(self):
        t = technique()
        t["composants"][0]["nom"] = "dns"
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "« dns » de C01 est réservé"):
            self.generer(None, t)

    def test_namespace_impose(self):
        objets, _ = flux.generer(matrice(), plateforme(), technique(), "finance-ndf")
        self.assertTrue(all(o["metadata"]["namespace"] == "finance-ndf" for o in objets))


class TestDestinations(unittest.TestCase):
    def test_corpus(self):
        d = flux.destinations(matrice())
        self.assertEqual(d["application"], "notes-de-frais")
        self.assertEqual([x["flux"] for x in d["destinations"]], ["R02", "R03", "R04", "R05", "R06", "R07"])
        self.assertEqual(d["destinations"][0], {"flux": "R02", "composant": "C01", "plateforme": "sso", "port": 443, "protocole": "https"})
        self.assertEqual(d["destinations"][3]["hote"], "annuaire.example.com")
        self.assertNotIn("variable", d["destinations"][3])

    def test_variable_seule(self):
        d = flux.destinations(avec_flux(matrice(), un_flux(vers={"service": "T01", "variable": "API_URL"})))
        self.assertEqual(d["destinations"][-1]["variable"], "API_URL")


class TestLigneDeCommande(unittest.TestCase):
    def lancer(self, *args):
        sortie, erreur = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreur):
            code = flux.main([str(a) for a in args])
        return code, sortie.getvalue(), erreur.getvalue()

    def ecrire(self, rep, doc):
        chemin = Path(rep) / "flux.yaml"
        chemin.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        return chemin

    def test_valider_corpus(self):
        code, sortie, _ = self.lancer("valider", FLUX, "--dossier", RATON, "--qualification", FICHE)
        self.assertEqual(code, 0)
        self.assertTrue(sortie.startswith("✓"))

    def test_valider_erreur(self):
        with tempfile.TemporaryDirectory() as rep:
            code, sortie, _ = self.lancer("valider", self.ecrire(rep, avec_flux(matrice(), un_flux("R01"))))
        self.assertEqual(code, 1)
        self.assertIn("identifiant en double R01", sortie)

    def test_ecarts(self):
        code, sortie, _ = self.lancer("ecarts", FLUX, "--dossier", RATON, "--qualification", FICHE)
        self.assertEqual((code, sortie), (0, "0 écart(s)\n"))
        with tempfile.TemporaryDirectory() as rep:
            code, sortie, _ = self.lancer("ecarts", self.ecrire(rep, avec_flux(matrice(), SENTRY)), "--dossier", RATON, "--qualification", FICHE)
        self.assertEqual(code, 2)  # T04 est inconnu de la partie technique soumise
        with tempfile.TemporaryDirectory() as rep:
            sentry = copy.deepcopy(SENTRY)
            sentry["vers"] = {"systeme": "Sentry", "hote": "*.ingest.de.sentry.io"}
            code, sortie, _ = self.lancer("ecarts", self.ecrire(rep, avec_flux(matrice(), sentry)), "--dossier", RATON, "--qualification", FICHE)
        self.assertEqual(code, 0)
        self.assertIn("[flux_sans_echange] R08", sortie)
        self.assertIn("2 écart(s)", sortie)

    def test_rendre(self):
        code, sortie, _ = self.lancer("rendre", FLUX, "--dossier", RATON)
        self.assertEqual(code, 0)
        self.assertTrue(sortie.startswith("# notes-de-frais — matrice de flux"))

    def test_egress(self):
        code, sortie, _ = self.lancer("egress", FLUX)
        self.assertEqual(code, 0)
        self.assertEqual(yaml.safe_load(sortie), flux.destinations(matrice()))

    def test_generer(self):
        code, sortie, erreur = self.lancer("generer", FLUX, "--dossier", RATON, "--plateforme", PLATEFORME)
        self.assertEqual((code, erreur), (0, ""))
        self.assertTrue(sortie.startswith("# Généré par flux.py"))
        self.assertEqual(list(yaml.safe_load_all(sortie)), self.generer_objets())

    def generer_objets(self):
        return flux.generer(matrice(), plateforme(), technique())[0]

    def test_generer_refuse_une_matrice_invalide(self):
        with tempfile.TemporaryDirectory() as rep:
            code, _, erreur = self.lancer("generer", self.ecrire(rep, avec_flux(matrice(), un_flux("R01"))), "--dossier", RATON, "--plateforme", PLATEFORME)
        self.assertEqual(code, 2)
        self.assertIn("non valide", erreur)

    def test_generer_refuse_une_plateforme_invalide(self):
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "plateforme.yaml"
            chemin.write_text(yaml.safe_dump(plateforme(cni="calico")), encoding="utf-8")
            code, _, erreur = self.lancer("generer", FLUX, "--dossier", RATON, "--plateforme", chemin)
        self.assertEqual(code, 2)
        self.assertIn("cni", erreur)


if __name__ == "__main__":
    unittest.main()
