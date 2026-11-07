"""Tests für den versionierten Modellkatalog (V-011).

Der Katalog ``data/models.json`` ist die einzige Quelle für Modell-Fakten,
Preise und Einschätzungen im Dashboard und in der CLI. Diese Tests sichern:

* jede nicht triviale Angabe braucht Quelle und Datum,
* unbekannte Werte sind ausdrücklich erlaubt und brauchen keine Quelle,
* Fakten und Einschätzungen sind getrennt,
* unbestätigte Modell-IDs und veraltete Preise werden gemeldet,
* Währung, Einheit, Tarife und Gültigkeitsdatum sind Pflicht,
* der ausgelieferte Katalog ist selbst fehlerfrei und übernimmt keine
  ungeprüften Altpreise,
* der alte lokale Katalog (Schema 1) wird lesbar, aber als Altbestand markiert,
* entfernte und unbekannte Modelle werden gegen die aktuelle Modellliste
  abgeglichen,
* die CLI zeigt Quelle und Datum.

Alle Tests arbeiten ohne Netzwerk und ohne Modellaufrufe.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
MODULE = BIN / "vibe_models.py"
CLI = BIN / "vibe"
SHIPPED = REPO / "data" / "models.json"
HEUTE = date(2026, 10, 30)


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def assertion(value, art="fakt", quelle="models.dev", datum="2026-10-30"):
    node = {"wert": value, "art": art}
    if quelle is not None:
        node["quelle"] = quelle
    if datum is not None:
        node["datum"] = datum
    return node


def entry(model_id="opencode/test-free"):
    return {
        "id": model_id,
        "name": "Test Free",
        "anbieter": "OpenCode Zen",
        "id_status": "bestaetigt",
        "id_beleg": {"quelle": "opencode models --standalone, opencode 2.2.2",
                     "datum": "2026-10-30"},
        "preis": {
            "status": "kostenlos",
            "waehrung": "USD",
            "einheit": "1 Mio. Tokens",
            "stand": "2026-10-30",
            "quelle": "models.dev, Anbieter opencode",
            "tarife": {"eingabe": 0, "ausgabe": 0, "cache_lesen": 0},
        },
        "fakten": {
            "kontext": assertion("200000 Token"),
            "bild": assertion("nein"),
            "daten": assertion("unbekannt"),
        },
        "einschaetzungen": {
            "tempo": assertion("schnell", art="einschaetzung",
                               quelle="Altkatalog 2026-10-25", datum="2026-10-25"),
            "staerken": [{"text": "Schnell im Test", "art": "messung",
                          "quelle": "bigiron.cc-Test 2026-10-19", "datum": "2026-10-19"}],
            "schwaechen": [],
        },
    }


def catalog(*models):
    return {
        "schema": 2,
        "version": "1.0",
        "stand": "2026-10-30",
        "waehrung": "USD",
        "einheit": "1 Mio. Tokens",
        "hinweis": "Testkatalog",
        "modelle": list(models) or [entry()],
        "nicht_uebernommen": [],
    }


def codes(findings):
    return {finding["code"] for finding in findings}


class ModelCatalogValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = load_module(MODULE, "vibe_models")

    def validate(self, data, **kwargs):
        kwargs.setdefault("heute", HEUTE)
        return self.models.validate(data, **kwargs)

    def test_valid_catalog_has_no_findings(self):
        self.assertEqual(self.validate(catalog()), [])

    def test_missing_source_is_reported(self):
        data = catalog()
        data["modelle"][0]["fakten"]["kontext"] = assertion(
            "200000 Token", quelle=None)
        self.assertIn("quelle_fehlt", codes(self.validate(data)))

    def test_missing_date_is_reported(self):
        data = catalog()
        data["modelle"][0]["einschaetzungen"]["tempo"] = assertion(
            "schnell", art="einschaetzung", datum=None)
        self.assertIn("datum_fehlt", codes(self.validate(data)))

    def test_invalid_date_is_reported(self):
        data = catalog()
        data["modelle"][0]["fakten"]["kontext"]["datum"] = "gestern"
        self.assertIn("datum_ungueltig", codes(self.validate(data)))

    def test_unknown_values_are_allowed_without_source(self):
        data = catalog()
        data["modelle"][0]["fakten"]["kontext"] = {"wert": "unbekannt"}
        data["modelle"][0]["fakten"]["bild"] = {"wert": "unklar"}
        data["modelle"][0]["einschaetzungen"]["tempo"] = {"wert": "keine Daten"}
        self.assertEqual(self.validate(data), [])

    def test_facts_and_assessments_must_stay_separated(self):
        data = catalog()
        data["modelle"][0]["fakten"]["kontext"]["art"] = "einschaetzung"
        data["modelle"][0]["einschaetzungen"]["tempo"]["art"] = "fakt"
        found = codes(self.validate(data))
        self.assertIn("art_falsch", found)

    def test_unknown_art_is_reported(self):
        data = catalog()
        data["modelle"][0]["fakten"]["kontext"]["art"] = "gefuehl"
        self.assertIn("art_ungueltig", codes(self.validate(data)))

    def test_outdated_price_is_reported(self):
        data = catalog()
        data["modelle"][0]["preis"]["stand"] = "2025-01-01"
        self.assertIn("preis_veraltet", codes(self.validate(data)))

    def test_price_without_currency_or_unit_is_reported(self):
        data = catalog()
        data["modelle"][0]["preis"].pop("waehrung")
        data["modelle"][0]["preis"].pop("einheit")
        found = codes(self.validate(data))
        self.assertIn("waehrung_fehlt", found)
        self.assertIn("einheit_fehlt", found)

    def test_known_price_requires_validity_date_and_source(self):
        data = catalog()
        data["modelle"][0]["preis"].update({
            "status": "bekannt", "stand": None, "quelle": "",
            "tarife": {"eingabe": 0.15, "ausgabe": 0.5}})
        found = codes(self.validate(data))
        self.assertIn("preis_beleg_fehlt", found)

    def test_free_price_requires_separate_tariffs(self):
        # "kostenlos" ist ein Preisstatus, keine Erlaubnis, die Tarife
        # wegzulassen: Eingabe und Ausgabe muessen getrennt belegt sein.
        data = catalog()
        data["modelle"][0]["preis"] = {
            "status": "kostenlos", "waehrung": "USD",
            "einheit": "1 Mio. Tokens", "stand": "2026-10-30",
            "quelle": "models.dev, Anbieter opencode",
        }
        found = codes(self.validate(data))
        self.assertIn("tarif_ungueltig", found)
        data["modelle"][0]["preis"]["tarife"] = {"eingabe": 0, "ausgabe": 0}
        self.assertEqual(self.validate(data), [])

    def test_cache_write_tariff_is_checked_even_when_cache_read_exists(self):
        # Getrennte Cachepreise: ein ungueltiger Schreibtarif darf nicht
        # deshalb durchrutschen, weil ein Lesetarif vorhanden ist.
        data = catalog()
        data["modelle"][0]["preis"]["status"] = "bekannt"
        data["modelle"][0]["preis"]["tarife"] = {
            "eingabe": 0.15, "ausgabe": 0.5,
            "cache_lesen": 0.03, "cache_schreiben": "n/a",
        }
        found = codes(self.validate(data))
        self.assertIn("tarif_ungueltig", found)
        data["modelle"][0]["preis"]["tarife"]["cache_schreiben"] = 0.05
        self.assertEqual(self.validate(data), [])

    def test_price_tiers_are_checked_individually(self):
        data = catalog()
        data["modelle"][0]["preis"]["status"] = "bekannt"
        data["modelle"][0]["preis"]["tarife"] = {
            "eingabe": 2.0, "ausgabe": 10.0,
            "staffeln": [{"ab_kontext": 272000, "eingabe": 5.0, "ausgabe": 22.5}],
            "cache_lesen": 0.5,
        }
        self.assertEqual(self.validate(data), [])
        data["modelle"][0]["preis"]["tarife"]["staffeln"][0].pop("ab_kontext")
        self.assertIn("tarif_ungueltig", codes(self.validate(data)))

    def test_unverified_model_id_is_reported(self):
        data = catalog()
        data["modelle"][0]["id_status"] = "unbestaetigt"
        self.assertIn("unbestaetigte_id", codes(self.validate(data)))

    def test_id_evidence_is_required(self):
        data = catalog()
        data["modelle"][0].pop("id_beleg")
        self.assertIn("id_beleg_fehlt", codes(self.validate(data)))

    def test_removed_model_requires_own_date_and_source(self):
        data = catalog()
        data["modelle"][0]["id_status"] = "entfernt"
        data["modelle"][0].pop("id_beleg")
        self.assertIn("entfernt_beleg_fehlt", codes(self.validate(data)))
        data["modelle"][0]["entfernt_am"] = "2026-10-30"
        data["modelle"][0]["entfernt_quelle"] = "opencode models --standalone"
        self.assertEqual(self.validate(data), [])

    def test_removed_model_is_reported_against_current_list(self):
        data = catalog(entry("opencode/weg"))
        found = codes(self.validate(data, aktuell=["opencode/da"]))
        self.assertIn("modell_entfernt", found)
        self.assertIn("modell_unbekannt", found)

    def test_duplicate_ids_are_reported(self):
        data = catalog(entry("opencode/doppelt"), entry("opencode/doppelt"))
        self.assertIn("doppelte_id", codes(self.validate(data)))

    def test_legacy_catalog_is_readable_but_marked(self):
        legacy = {
            "stand": "2026-10-25",
            "hinweis": "Altbestand",
            "models": [{
                "id": "opencode/alt-free", "name": "Alt", "lab": "Test",
                "preis": "kostenlos", "ctx": "1 Mio.", "tempo": "schnell",
                "aufwand": "gering", "daten": "gut", "daten_text": "kein Training",
                "vision": "ja", "coder": "geeignet", "reviewer": "bedingt",
                "staerken": ["schnell"], "schwaechen": ["keine Messung"],
                "quellen": "Altkatalog",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            view = self.models.load(str(path))
        self.assertTrue(view["legacy"])
        self.assertIn("altkatalog", codes(view["findings"]))
        model = view["models"][0]
        self.assertEqual(model["id"], "opencode/alt-free")
        self.assertEqual(model["id_status"], "unbestaetigt")
        # Der kostenlose Status bleibt aus Kompatibilitätsgründen erhalten;
        # alle nicht-trivialen Altangaben tragen Quelle und Datum.
        self.assertEqual(model["preis"]["status"], "kostenlos")
        self.assertEqual(model["fakten"]["kontext"]["datum"], "2026-10-25")
        self.assertEqual(model["einschaetzungen"]["tempo"]["art"], "altbestand")

    def test_legacy_paid_price_is_not_adopted(self):
        legacy = {"stand": "2026-10-25", "models": [{
            "id": "opencode/alt-paid", "preis": "$1,40 / $4,40"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            view = self.models.load(str(path))
        price = view["models"][0]["preis"]
        self.assertEqual(price["status"], "unbekannt")
        self.assertNotIn("1,40", json.dumps(price, ensure_ascii=False))

    def test_price_text_contains_currency_and_unit(self):
        preis = dict(entry()["preis"])
        preis["status"] = "bekannt"
        preis["tarife"] = {"eingabe": 0.15, "ausgabe": 0.5}
        text = self.models.price_text(preis)
        self.assertIn("USD", text)
        self.assertIn("1 Mio. Tokens", text)
        self.assertIn("0,15", text)
        self.assertIn("0,50", text)

    def test_unknown_price_text_is_explicit(self):
        self.assertEqual(
            self.models.price_text({"status": "unbekannt"}), "unbekannt")

    def test_assertion_text_marks_unknown(self):
        self.assertEqual(
            self.models.assertion_text({"wert": "unbekannt"}), "unbekannt")
        self.assertEqual(
            self.models.assertion_text({"wert": "schnell"}), "schnell")


class ShippedCatalogTest(unittest.TestCase):
    """Der ausgelieferte Katalog muss selbst alle Regeln erfüllen."""

    @classmethod
    def setUpClass(cls):
        cls.models = load_module(MODULE, "vibe_models")
        cls.raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
        cls.view = cls.models.load(str(SHIPPED))

    def test_catalog_uses_versioned_schema(self):
        self.assertEqual(self.raw["schema"], 2)
        self.assertTrue(self.raw.get("version"))
        self.assertRegex(self.raw.get("stand", ""), r"^\d{4}-\d{2}-\d{2}$")

    def test_catalog_matches_its_own_rules(self):
        self.assertEqual(self.models.validate(self.raw, heute=HEUTE), [])

    def test_every_model_has_evidence_for_id_and_price(self):
        for model in self.raw["modelle"]:
            self.assertIn(model["id_status"], ("bestaetigt", "entfernt"))
            self.assertTrue(model["id_beleg"]["quelle"])
            self.assertTrue(model["id_beleg"]["datum"])
            price = model["preis"]
            self.assertIn(price["status"], ("kostenlos", "bekannt", "unbekannt"))
            if price["status"] == "unbekannt":
                self.assertTrue(price.get("grund"))
            else:
                self.assertEqual(price["waehrung"], "USD")
                self.assertEqual(price["einheit"], "1 Mio. Tokens")
                self.assertTrue(price["quelle"])
                self.assertTrue(price["stand"])

    def test_legacy_paid_ids_are_not_adopted(self):
        ids = {model["id"] for model in self.raw["modelle"]}
        # Diese IDs standen im Altkatalog, sind aber am Prüftag nicht in
        # ``opencode models --standalone`` erschienen.
        for legacy_id in ("opencode/glm-5.3", "opencode/deepseek-v4-pro",
                          "opencode/claude-sonnet-5-5",
                          "opencode/nemotron-3-ultra-free"):
            self.assertNotIn(legacy_id, ids)
            self.assertIn(legacy_id, json.dumps(
                self.raw["nicht_uebernommen"], ensure_ascii=False))

    def test_no_legacy_price_strings_are_used_as_facts(self):
        text = json.dumps(self.raw["modelle"], ensure_ascii=False)
        for legacy_price in ("$1,40", "$4,40", "$0,30", "$1,20", "$2,00"):
            self.assertNotIn(legacy_price, text)

    def test_catalog_contains_only_confirmed_models(self):
        for model in self.raw["modelle"]:
            self.assertEqual(model["id_status"], "bestaetigt")
            self.assertTrue(model["id"].startswith("opencode/"))

    def test_catalog_names_unknown_data_terms_explicitly(self):
        # Datenschutzbedingungen stammen aus dem Altbestand und sind als
        # solche mit Quelle und Datum markiert.
        model = self.raw["modelle"][0]
        daten = model["fakten"]["daten"]
        self.assertEqual(daten["art"], "altbestand")
        self.assertTrue(daten["quelle"])
        self.assertTrue(daten["datum"])


class CatalogCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = load_module(MODULE, "vibe_models")

    def run_cli(self, root, *args):
        env = os.environ.copy()
        for key in ("VIBE", "VIBE_STATE", "VIBE_INSTALL", "VIBE_RUNTIME",
                    "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE", "SANDBOX",
                    "SANDBOX_TOOLS", "VIBE_UI_PORT"):
            env.pop(key, None)
        env.update({
            "VIBE": str(root),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(Path(root) / "home"),
            "PATH": "/usr/bin:/bin",
        })
        return subprocess.run(
            [sys.executable, str(CLI), "models", *args],
            env=env, text=True, capture_output=True, timeout=60)

    def test_cli_lists_sources_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_toolchain").mkdir()
            (root / "_toolchain" / "models.json").write_text(
                json.dumps(catalog(), ensure_ascii=False), encoding="utf-8")
            result = self.run_cli(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("opencode/test-free", result.stdout)
        self.assertIn("2026-10-30", result.stdout)
        self.assertIn("models.dev", result.stdout)

    def test_cli_detail_shows_facts_and_assessments_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_toolchain").mkdir()
            (root / "_toolchain" / "models.json").write_text(
                json.dumps(catalog(), ensure_ascii=False), encoding="utf-8")
            result = self.run_cli(root, "opencode/test-free")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fakten", result.stdout)
        self.assertIn("Einschätzungen", result.stdout)
        self.assertIn("Altkatalog 2026-10-25", result.stdout)
        self.assertIn("bigiron.cc-Test 2026-10-19", result.stdout)

    def test_cli_marks_missing_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(Path(tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("kein modellkatalog", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
