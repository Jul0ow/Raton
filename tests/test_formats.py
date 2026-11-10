"""Tests communs à tous les formats : schémas et chargeur."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "plugin" / "scripts"))

import raton_formats  # noqa: E402


class TestSchemas(unittest.TestCase):
    def test_schemas_valides(self):
        for chemin in raton_formats.SCHEMAS.glob("*.schema.json"):
            with self.subTest(schema=chemin.name):
                Draft202012Validator.check_schema(json.loads(chemin.read_text(encoding="utf-8")))

    def test_chaque_format_a_son_schema(self):
        for format_, fichier in raton_formats.FORMATS.items():
            with self.subTest(format=format_):
                schema = raton_formats.schema(format_)
                self.assertEqual(schema["properties"]["format"]["const"], format_)

    def test_identifiants_uniques(self):
        ids = [json.loads(p.read_text(encoding="utf-8"))["$id"] for p in raton_formats.SCHEMAS.glob("*.schema.json")]
        self.assertEqual(len(ids), len(set(ids)))


class TestChargeur(unittest.TestCase):
    def charger_texte(self, texte):
        with tempfile.TemporaryDirectory() as rep:
            chemin = Path(rep) / "f.yaml"
            chemin.write_bytes(texte.encode("utf-8") if isinstance(texte, str) else texte)
            return raton_formats.charger(chemin)

    def test_json_accepte(self):
        self.assertEqual(self.charger_texte('{"a": [1, 2]}'), {"a": [1, 2]})

    def test_cle_en_double_refusee(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "clé en double"):
            self.charger_texte("a: 1\nb: 2\na: 3\n")

    def test_cle_en_double_imbriquee_refusee(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "clé en double"):
            self.charger_texte("a:\n  b: 1\n  b: 2\n")

    def test_dates_en_texte(self):
        self.assertEqual(
            self.charger_texte("d: 2026-11-10\nh: 2026-11-10T10:00:00Z\n"),
            {"d": "2026-11-10", "h": "2026-11-10T10:00:00+00:00"},
        )

    def test_balise_python_refusee(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "YAML invalide"):
            self.charger_texte("a: !!python/object/apply:os.system ['true']\n")

    def test_binaire_refuse(self):
        with self.assertRaisesRegex(raton_formats.ErreurFormat, "UTF-8"):
            self.charger_texte(b"\xff\xfe\x00a")


if __name__ == "__main__":
    unittest.main()
