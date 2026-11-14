"""Browserabnahme F20: die Oberfläche stellt sich bei Pi auf Pi um.

Der Test startet das echte Dashboard mit Attrappen für opencode und Pi
(leere /-Programmsignaturen wie in tests/browser/test_ap04_harness_ui.py).
Die Auswahl steht vorbefüllt in ``<VIBE_STATE>/harness.json``.

Geprüft (Akzeptanzkriterien B aus dem Arbeitspaket F20):
* B1 Kopfleiste (Serverbox): bei Pi erscheinen „opencode-Server:“ sowie die
  Knöpfe „opencode stoppen“/„opencode starten“ nicht; erkennbar ist, dass
  Pi-Läufe ohne opencode-Server laufen; „Dashboard beenden“ bleibt.
* B2 Projekt-Detail: kein Link „opencode-Weboberfläche“.
* B3 Steuerkarte: Hinweis nennt nicht mehr die „opencode-Session“, sondern
  den Print-Modus-Grenzwert von Pi.
* B4 Subagenten-Karte: Hinweis auf das Pi-Limit.
* B5 Agenten-/Modellansicht: Detailaufklapper referenziert
  „pi --list-models“, Profil-/Anmelde-Hinweis nennt Pi, Agentenordner-Hinweis
  erklärt die Dateien als Prompt-Quelle.
* B6 Sandbox-/Schreibrechte-Karte: Beschreibung nennt die Pi-Laufart statt
  „mit eigenem opencode-Server in bubblewrap“.
* B7 MCP-Tab: Hinweis verweist nicht auf „opencode mcp auth“.
* Regression opencode: alle bisherigen Texte und Knöpfe bleiben unverändert.

Keine echten Modellaufrufe; isoliertes VIBE/HOME, eigener Port.
Provenienz: Von der unabhängigen Test-Agenten-Sitzung geprüft, formal
übernommen und als verbindliche Testfälle des Test-Agenten erklärt.
"""
import json
import os
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

FAKE_PI = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '1.5.0\\n'
  exit 0
fi
if [ "$1" = "--list-models" ]; then
  printf 'anthropic/claude-sonnet\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/model-a\\n'
  exit 0
fi
exit 2
"""

CATALOG = {
    "schema": 2,
    "version": "2026-10-30.1",
    "stand": "2026-10-30",
    "waehrung": "USD",
    "einheit": "1 Mio. Tokens",
    "hinweis": "Testkatalog für die F20-Browserabnahme.",
    "quellen": [],
    "modelle": [
        {
            "id": "opencode/test-free",
            "name": "Test Free",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models --standalone", "datum": "2026-10-30"},
        },
    ],
}

ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_HARNESS",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def mentions_serverless_run(text):
    """Erkennung „Pi läuft ohne opencode-Server“ trotz freier Formulierung."""
    patterns = (
        r"(?i)(?:ohne|kein\w*|nicht|frei von)\s+[^<]{0,60}\bopencode",
        r"(?i)(?:ohne|kein\w*|nicht)\s+[^<]{0,40}\bserver\b",
        r"(?i)\bpi\b[^<]{0,80}(?:ohne|kein\w*|nicht)[^<]{0,40}\bserver\b",
    )
    import re as _re
    return any(_re.search(p, text) for p in patterns)


def mentions_pi_limit(text, subject):
    """„Pi-Grenzwert bei <subject>“ in freier Formulierung erkennen."""
    import re as _re
    patterns = (
        r"(?i)(?:kein[eonsr]?|nicht|ohne|nur|limit|grenz\w*)[^<]{0,90}" + subject,
        subject + r"[^<]{0,60}(?:kein[eonsr]?|nicht|ohne|nur)",
    )
    return any(_re.search(p, text) for p in patterns)


class HarnessUiBase(unittest.TestCase):
    """Gemeinsames Nachbildchen: echtes Dashboard, Attrappen, ein Projekt."""

    selection = None  # None = keine Datei (Default opencode), sonst "pi"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1",
                        "installed_at": "2026-11-07"}),
            encoding="utf-8",
        )
        (cls.toolchain / "models.json").write_text(
            json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8"
        )
        if cls.selection is not None:
            (cls.toolchain / "harness.json").write_text(
                json.dumps({"harness": cls.selection}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F20 PI integration\n"
            "  Beschreibung: Umstellung auf Pi\n",
            encoding="utf-8",
        )
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.logs),
                "HOME": str(cls.home),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.logs / "web.token"
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
        cls.tmp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def open_dashboard(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.wait_for_selector("nav button")

    def open_detail(self):
        self.open_dashboard()
        self.page.locator("tr.row").first.click()
        self.page.wait_for_selector("#runstate")

    def open_detail_tab(self, label):
        self.page.get_by_role("tab", name=label).click()

    def open_nav(self, label, tab=None):
        # Nav-Tests müssen die Vorbedingung selbst herstellen (frische Seite
        # startet auf about:blank): Dashboard öffnen, dann den Nav-Knopf
        # anklicken (Muster der übrigen Browser-Suiten). Danach abwarten, bis
        # der Klick das Register gewechselt hat (Klasse „on“ am Zielknopf) –
        # das Registerrendern selbst folgt asynchron.
        self.open_dashboard()
        self.page.get_by_role("button", name=label).click()
        marker = "b.dataset.t" if tab else "b.textContent"
        target = json.dumps(tab if tab else label)
        self.page.wait_for_function(
            "[...document.querySelectorAll('nav button')].some((b) => "
            "b.classList.contains('on') && " + marker + " === " + target + ")"
        )

    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Einstellungsabschnitt auf, falls er als
        <details> umgesetzt ist. Auf der Bestandsstruktur bleibt der Aufruf
        ein No-op."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                assert section.evaluate("el => !!el.open"), \
                    "%s ließ sich nicht aufklappen" % selector

    def open_models_table(self):
        """Klappt die Modell-Liste auf (Muster tests/browser/test_models_ui.py)."""
        details = self.page.locator("#models details").first
        if not details.get_attribute("open"):
            details.locator(":scope > summary").click()


class PiHarnessUiTest(HarnessUiBase):
    """Fallgruppe B: Pi gewählt (harness.json = {"harness":"pi"})."""

    selection = "pi"

    def test_server_box_runs_pi_without_opencode_server_controls(self):
        # AK B1. Vorbedingung: Pi gewählt, Dashboard geöffnet; Aktion: Kopf-
        # leiste lesen; Erwartung: kein „opencode-Server:“-Text, keine Knöpfe
        # „opencode stoppen“/„opencode starten“, Pi-Freiheits-Merkmal sichtbar,
        # „Dashboard beenden“ bleibt.
        self.open_dashboard()
        box = self.page.locator("#srv")
        box.wait_for()
        self.page.wait_for_function(
            "document.querySelector('#srv') && document.querySelector('#srv').innerText.length > 0"
        )
        text = box.inner_text()
        self.assertNotIn("opencode-Server:", text,
                         "Bei Pi bleibt der opencode-Server-Text in der Kopfleiste?")
        self.assertEqual(
            self.page.get_by_role("button", name="opencode stoppen").count(), 0)
        self.assertEqual(
            self.page.get_by_role("button", name="opencode starten").count(), 0)
        self.assertNotIn("opencode stoppen", text)
        self.assertNotIn("opencode starten", text)
        self.assertIn("Dashboard beenden", text,
                      "Der Knopf „Dashboard beenden“ darf nicht verschwinden")
        import re
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Kopfleiste nennt die Pi-Laufart nicht: " + text)
        self.assertTrue(
            mentions_serverless_run(text),
            "Kopfleiste ist nicht erkennbar, dass Pi ohne opencode-Server läuft: "
            + text,
        )

    def test_project_detail_has_no_opencode_weblink(self):
        # AK B2. Vorbedingung: Pi gewählt, Projekt geöffnet; Aktion: Detail
        # betrachten; Erwartung: kein Linktext „opencode-Weboberfläche“.
        self.open_detail()
        self.assertEqual(
            self.page.locator('a:has-text("opencode-Weboberfläche")').count(), 0)
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode-Weboberfläche", body)

    def test_models_detail_points_to_pi_list_models(self):
        # AK B5a. Vorbedingung: Pi gewählt, Modellkatalog vorhanden, Katalog-
        # modell fehlt in der Pi-Modellliste; Aktion: Register „Agenten &
        # Modelle“, Modellzeile aufklappen; Erwartung: „pi --list-models“ statt
        # „Nicht in „opencode models““.
        self.open_nav("Agenten & Modelle")
        self.open_models_table()
        row = self.page.locator('tr[data-model-row="opencode/test-free"]')
        row.wait_for()
        row.click()
        detail = self.page.locator('tr[data-model-detail="opencode/test-free"]')
        text = detail.inner_text()
        self.assertNotIn("Nicht in „opencode models“", text)
        self.assertIn("pi --list-models", text,
                      "Aufklapper verweist nicht auf „pi --list-models“: " + text)

    def test_profiles_hint_names_pi_instead_of_opencode_login(self):
        # AK B5b. Vorbedingung: Pi gewählt; Aktion: Register „Agenten &
        # Modelle“, Profilhinweis lesen; Erwartung: Anmelde-Hinweis nennt Pi,
        # „opencode auth login“ erscheint nicht.
        self.open_nav("Agenten & Modelle")
        self.page.wait_for_selector("#agents")
        import re
        self.assertTrue(
            re.search(r"(?i)\bpi\b", self.page.locator("main").inner_text()),
            "Agenten-/Modellansicht erwähnt Pi nicht")
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode auth login", body)

    def test_agents_dir_hint_explains_prompt_source(self):
        # AK B5c. Vorbedingung: Pi gewählt; Aktion: Agenten-Karte lesen;
        # Erwartung: Hinweis erklärt Agentendateien als Prompt-Quelle für Pi.
        self.open_nav("Agenten & Modelle")
        card = self.page.locator("#agents")
        card.wait_for()
        import re
        text = card.inner_text()
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Agenten-Hinweis nennt Pi nicht: " + text)
        self.assertTrue(re.search(r"(?i)prompt", text),
                        "Agenten-Hinweis erklärt die Prompt-Quelle nicht: " + text)

    def test_sandbox_card_describes_pi_runtime(self):
        # AK B6. Vorbedingung: Pi gewählt; Aktion: Projekt → Register
        # „Einstellungen“, Sandbox-Karte lesen; Erwartung: keine „mit eigenem
        # opencode-Server in bubblewrap“-Formulierung, Pi-Laufart erkennbar.
        self.open_detail()
        self.open_detail_tab("Einstellungen")
        card = self.page.locator("#sandbox")
        card.wait_for()
        self.expand_optional("#sandbox")
        import re
        text = card.inner_text()
        self.assertNotIn("opencode-Server in bubblewrap", text)
        self.assertNotIn("mit eigenem opencode-Server", text)
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Sandbox-Karte nennt die Pi-Laufart nicht: " + text)

    def test_mcp_hint_points_to_pi_limit(self):
        # AK B7. Vorbedingung: Pi gewählt; Aktion: Register „MCP-Tools“ öffnen;
        # Erwartung: kein „opencode mcp auth“-Hinweis, Pi-spezifischer Grenzwert
        # erkennbar.
        self.open_nav("MCP-Tools", tab="mcp")
        # #mcpres ist eine leere Ergebnisbox (DOM vorhanden, ohne Inhalt
        # unsichtbar): auf DOM-Präsenz warten, nicht auf Sichtbarkeit.
        self.page.wait_for_selector("#mcpres", state="attached")
        import re
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode mcp auth", body)
        self.assertTrue(re.search(r"(?i)\bpi\b", body),
                        "MCP-Hinweis nennt den Pi-Grenzwert nicht: " + body)


class OpencodeRegressionUiTest(HarnessUiBase):
    """Regression: ohne Auswahl (Default opencode) bleiben Texte/Knöpfe wie
    bisher."""

    selection = None

    def test_server_box_keeps_opencode_controls(self):
        # AK Regression B1. Vorbedingung: keine Auswahl; Aktion: Kopfleiste;
        # Erwartung: „opencode-Server:“ und Knopf „opencode starten“ (Server
        # aus) vorhanden, „Dashboard beenden“ bleibt.
        self.open_dashboard()
        box = self.page.locator("#srv")
        self.page.wait_for_function(
            "document.querySelector('#srv') && document.querySelector('#srv').innerText.includes('opencode-Server:')"
        )
        text = box.inner_text()
        self.assertIn("opencode-Server:", text)
        self.assertIn("opencode starten", text)
        self.assertEqual(
            self.page.get_by_role("button", name="opencode starten").count(), 1)
        self.assertIn("Dashboard beenden", text)

    def test_detail_link_and_cards_keep_opencode_wording(self):
        # AK Regression B2/B6 (B11: Ausgabe-Karten entfallen aus der Prüfung).
        # Vorbedingung: keine Auswahl; Aktion: Projekt öffnen, Register
        # lesen; Erwartung: Link „opencode-Weboberfläche“ und Sandbox-Text
        # „mit eigenem opencode-Server in bubblewrap“.
        # B11: Der Ausgabebereich wird komplett neu gebaut (Vertrag
        # tests/browser/test_b11_output_ui.py); die alten Karten #steer-card
        # und #subagents-card sind dort nicht mehr Teil der Oberfläche. Die
        # opencode-Wortwahl dieser Karten wird deshalb nicht mehr geprüft;
        # die fachliche Pi-Sperre bleibt an der API geprüft
        # (tests/unit/test_ap14_output_view_api.py). Weblink- und Sandbox-
        # Regression bleiben unverändert.
        self.open_detail()
        self.assertEqual(
            self.page.locator('a:has-text("opencode-Weboberfläche")').count(), 1)
        self.open_detail_tab("Einstellungen")
        sandbox = self.page.locator("#sandbox")
        sandbox.wait_for()
        self.expand_optional("#sandbox")
        self.assertIn("opencode-Server in bubblewrap", sandbox.inner_text())
        # „Voreingestellt sind …“ steht in der Karte „Schreibrechte (Agenten)“,
        # nicht in der Sandbox-Karte (Bestandsstruktur bin/web/app.js).
        self.expand_optional("#settings-rechte")
        self.assertIn(
            "Voreingestellt sind /tmp/opencode",
            self.page.locator(
                ".card", has_text="Schreibrechte (Agenten)").inner_text())

    def test_agents_models_and_mcp_keep_opencode_wording(self):
        # AK Regression B5/B7. Vorbedingung: keine Auswahl; Aktion: Agenten->
        # Modellzeile aufklappen und MCP-Tab öffnen; Erwartung: „Nicht in
        # „opencode models““, „opencode auth login“,	     ~/.config/opencode/agents
        # und „opencode mcp auth“ bleiben.
        self.open_nav("Agenten & Modelle")
        self.open_models_table()
        row = self.page.locator('tr[data-model-row="opencode/test-free"]')
        row.wait_for()
        row.click()
        detail = self.page.locator('tr[data-model-detail="opencode/test-free"]')
        text = detail.inner_text()
        self.assertIn("Nicht in „opencode models“", text)
        agents_card = self.page.locator("#agents")
        agents_card.wait_for()
        agents_text = agents_card.inner_text()
        self.assertIn("Systemweite Agenten liegen unter ~/.config/opencode/agents",
                      agents_text)
        self.assertNotIn("Pi", agents_text)
        self.page.locator("main").inner_text()
        self.assertIn("opencode auth login", self.page.locator("main").inner_text())
        self.open_nav("MCP-Tools", tab="mcp")
        # #mcpres ist eine leere Ergebnisbox (DOM vorhanden, ohne Inhalt
        # unsichtbar): auf DOM-Präsenz warten, nicht auf Sichtbarkeit.
        self.page.wait_for_selector("#mcpres", state="attached")
        self.assertIn("opencode mcp auth", self.page.locator("main").inner_text())


if __name__ == "__main__":
    unittest.main()
