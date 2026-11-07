"""Browserabnahme für den belegbaren Modellkatalog (V-011).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden:

* die Modelltabelle ist eingeklappt und lässt sich aufklappen,
* jede Zeile öffnet Detailzeilen mit Fakten und Einschätzungen,
* Fakten und Einschätzungen nennen Quelle und Datum,
* Preise nennen Währung, Einheit und getrennte Tarife,
* entfernte Modelle werden markiert,
* unbekannte, verbundene Modelle erscheinen ohne Einschätzung,
* Katalogbefunde und nicht übernommene Altbestände sind sichtbar.

Der Screenshot ``V-011-modellkatalog.png`` entsteht in diesem Test und zeigt
die tatsächliche Oberfläche.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT = SHOTS / "V-011-modellkatalog.png"

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/test-free\\nopencode/luecke\\nopencode/fremd\\n'
  exit 0
fi
echo 'unerwarteter Aufruf' >&2
exit 2
"""


def assertion(value, art="fakt", quelle="models.dev API, Anbieter opencode", datum="2026-10-30"):
    node = {"wert": value, "art": art}
    if quelle is not None:
        node["quelle"] = quelle
    if datum is not None:
        node["datum"] = datum
    return node


def catalog():
    return {
        "schema": 2,
        "version": "2026-10-30.1",
        "stand": "2026-10-30",
        "waehrung": "USD",
        "einheit": "1 Mio. Tokens",
        "hinweis": "Testkatalog für die Browserabnahme.",
        "quellen": [
            {"name": "opencode models --standalone", "datum": "2026-10-30",
             "zweck": "Modell-IDs"},
            {"name": "models.dev API", "datum": "2026-10-30", "zweck": "Fakten und Preise"},
        ],
        "modelle": [
            {
                "id": "opencode/test-free",
                "name": "Test Free",
                "anbieter": "OpenCode Zen",
                "id_status": "bestaetigt",
                "id_beleg": {"quelle": "opencode models --standalone", "datum": "2026-10-30"},
                "preis": {
                    "status": "bekannt", "waehrung": "USD", "einheit": "1 Mio. Tokens",
                    "stand": "2026-10-30", "quelle": "models.dev API",
                    "tarife": {"eingabe": 0.15, "ausgabe": 0.5,
                               "cache_lesen": 0.03,
                               "staffeln": [{"ab_kontext": 272000,
                                             "eingabe": 0.3, "ausgabe": 1.0}]},
                },
                "fakten": {
                    "kontext": assertion("200.000 Token"),
                    "bild": assertion("ja"),
                    "daten": assertion("unbekannt"),
                },
                "einschaetzungen": {
                    "tempo": assertion("schnell", art="einschaetzung",
                                       quelle="Altkatalog 2026-10-25", datum="2026-10-25"),
                    "aufwand": assertion("gering", art="einschaetzung",
                                         quelle="Altkatalog 2026-10-25", datum="2026-10-25"),
                    "coder": assertion("geeignet", art="einschaetzung",
                                       quelle="Altkatalog 2026-10-25", datum="2026-10-25"),
                    "reviewer": assertion("geeignet", art="einschaetzung",
                                          quelle="Altkatalog 2026-10-25", datum="2026-10-25"),
                    "staerken": [{"text": "Schnell im Test", "art": "messung",
                                  "quelle": "bigiron.cc-Test 2026-10-19", "datum": "2026-10-19"}],
                    "schwaechen": [{"text": "Nur begrenzt frei", "art": "einschaetzung",
                                    "quelle": "Altkatalog 2026-10-25", "datum": "2026-10-25"}],
                },
            },
            {
                "id": "opencode/luecke",
                "name": "Lücke",
                "anbieter": "OpenCode Zen",
                "id_status": "bestaetigt",
                "id_beleg": {"quelle": "opencode models --standalone", "datum": "2026-10-30"},
                "preis": {"status": "unbekannt", "grund": "kein belegter Preis"},
                "fakten": {"kontext": assertion("100.000 Token", quelle=None)},
                "einschaetzungen": {},
            },
            {
                "id": "opencode/weg",
                "name": "Entferntes Modell",
                "anbieter": "OpenCode Zen",
                "id_status": "entfernt",
                "entfernt_am": "2026-10-30",
                "entfernt_quelle": "opencode models --standalone",
                "preis": {"status": "unbekannt", "grund": "Modell nicht mehr gelistet"},
                "fakten": {"kontext": assertion("unbekannt")},
                "einschaetzungen": {},
            },
        ],
        "nicht_uebernommen": [
            {"id": "opencode/alt-paid", "name": "Alt bezahlt",
             "grund": "Altpreis ohne Gültigkeitsdatum",
             "quelle": "opencode models --standalone", "datum": "2026-10-30"},
        ],
    }


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER",
)


class ModelsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        (cls.root / "_logs").mkdir()
        (cls.root / "_toolchain").mkdir()
        (cls.root / "_toolchain" / "models.json").write_text(
            json.dumps(catalog(), ensure_ascii=False), encoding="utf-8")
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
        cls.fake_bin = fake_bin
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port, fake_bin)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1500, "height": 1100})
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.get_by_role("button", name="Agenten & Modelle").click()
        self.page.get_by_role("button", name="Neuer Agent").wait_for()
        self.page.locator("#models > details > summary").wait_for()

    def tearDown(self):
        self.page.close()

    def open_models(self):
        details = self.page.locator("#models details").first
        if not details.get_attribute("open"):
            details.locator(":scope > summary").click()
        self.page.locator('tr[data-model-row="opencode/test-free"]').wait_for()

    def row(self, model_id):
        return self.page.locator(f'tr[data-model-row="{model_id}"]')

    def detail(self, model_id):
        return self.page.locator(f'tr[data-model-detail="{model_id}"]')

    def test_table_is_collapsed_and_expands(self):
        details = self.page.locator("#models details").first
        self.assertIsNone(details.get_attribute("open"))
        self.assertFalse(self.row("opencode/test-free").is_visible())
        self.open_models()
        self.assertTrue(self.row("opencode/test-free").is_visible())
        self.assertIn("Fakten", self.page.locator("#models > details > summary").inner_text())

    def test_price_shows_currency_unit_and_tariff_tiers(self):
        self.open_models()
        cell = self.row("opencode/test-free").locator('[data-price-status="bekannt"]')
        self.assertIn("0,15 / 0,50 USD je 1 Mio. Tokens", cell.inner_text())
        self.row("opencode/test-free").click()
        detail = self.detail("opencode/test-free")
        self.assertTrue(detail.is_visible())
        text = detail.inner_text()
        self.assertIn("Währung: USD", text)
        self.assertIn("Einheit: 1 Mio. Tokens", text)
        self.assertIn("Stand: 2026-10-30", text)
        self.assertIn("Tarife je Einheit", text)
        self.assertIn("Staffel ab 272000 Kontext", text)

    def test_detail_separates_facts_and_assessments_with_sources(self):
        self.open_models()
        self.row("opencode/test-free").click()
        detail = self.detail("opencode/test-free")
        facts = detail.locator(".mfacts")
        opinions = detail.locator(".mopinion")
        self.assertIn("200.000 Token", facts.inner_text())
        self.assertIn("models.dev API, Anbieter opencode (2026-10-30)", facts.inner_text())
        self.assertIn("[fakt]", facts.inner_text())
        self.assertIn("schnell", opinions.inner_text())
        self.assertIn("Altkatalog 2026-10-25 (2026-10-25)", opinions.inner_text())
        self.assertIn("[einschaetzung]", opinions.inner_text())
        self.assertIn("Schnell im Test", opinions.inner_text())
        self.assertIn("bigiron.cc-Test 2026-10-19", opinions.inner_text())
        self.assertEqual(facts.locator("[data-assertion]").count(), 3)
        self.assertEqual(opinions.locator("[data-assertion]").count(), 4)

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT), full_page=True)
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

    def test_removed_model_is_marked(self):
        self.open_models()
        row = self.row("opencode/weg")
        self.assertIn("nicht mehr gelistet", row.inner_text())
        row.click()
        text = self.detail("opencode/weg").inner_text()
        self.assertIn("Nicht in „opencode models“", text)
        self.assertIn("Als entfernt geführt seit 2026-10-30", text)

    def test_unknown_model_has_no_assessment(self):
        self.open_models()
        row = self.row("opencode/fremd")
        self.assertIn("unbekannt", row.inner_text())
        # Auch ohne Katalogeintrag ist die Detailzeile erst nach dem Klick offen.
        self.assertFalse(self.detail("opencode/fremd").is_visible())
        row.click()
        self.assertTrue(self.detail("opencode/fremd").is_visible())
        self.assertIn("Kein Katalogeintrag", self.detail("opencode/fremd").inner_text())

    def test_catalog_findings_and_not_adopted_entries_are_visible(self):
        self.open_models()
        findings = self.page.locator("[data-catalog-findings]")
        self.assertEqual(findings.count(), 1)
        self.assertIn("Katalogbefunde (1)", findings.inner_text())
        self.assertIn("Quelle fehlt", findings.inner_text())
        notice = self.page.locator("[data-not-adopted]")
        notice.locator("summary").click()
        self.assertIn("Nicht übernommene Altbestände (1)", notice.inner_text())
        self.assertIn("opencode/alt-paid", notice.inner_text())
        self.assertIn("Altpreis ohne Gültigkeitsdatum", notice.inner_text())


def isolated_env(root, home, port, fake_bin):
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "VIBE_UI_PORT": str(port),
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_toolchain"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
    })
    return env


if __name__ == "__main__":
    unittest.main()
