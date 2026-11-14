"""Browserabnahme für die neu strukturierte Projektdetail-Oberfläche (F13).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft wird, dass das Projektdetail nicht mehr
alle Informationen gleichzeitig zeigt, sondern in klar benannte Bereiche
gliedert:

* Die Bereiche sind als Register (role=tablist) umgesetzt, genau ein Bereich
  ist sichtbar.
* Die Register lassen sich per Maus und per Tastatur bedienen (Pfeiltasten,
  Home/End) und sind für Screenreader korrekt verknüpft.
* Die wichtigsten Aktionen und der Laufzustand bleiben in jedem Bereich
  sichtbar (feste Kopfleiste).
* Einstellungen und Assistent sind nicht im Standardbild sichtbar und werden
  erst über ihr Register geöffnet.
* Die Prüfaktion wechselt in die Ausgabe und zeigt dort die Prüfungsausgabe.
* Das Detail bleibt im schmalen Fenster ohne horizontalen Seitenlauf bedienbar.

Die Screenshots ``F13-uebersicht.png`` und ``F13-einstellungen.png`` entstehen
in diesem Test und zeigen die tatsächliche Oberfläche.
"""
import os
import shutil
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
OVERVIEW_SHOT = SHOTS / "F13-uebersicht.png"
SETTINGS_SHOT = SHOTS / "F13-einstellungen.png"

# Ambient VIBE_* values would point vibe-web at the productive
# installation; the test must own all runtime paths.
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

FEEDBACK = (
    "# FEEDBACK — Test\n\n"
    "- [ ] F1 Erster Punkt\n"
    "  Beschreibung: Erste Beschreibung\n\n"
    "- [ ] F2 Zweiter Punkt\n"
    "  Beschreibung: Zweite Beschreibung\n"
)

TABS = ["Arbeit", "Ausgabe", "Assistent", "Einstellungen"]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProjectDetailUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="echo F13-Pruefung"\n', encoding="utf-8"
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        # Für „Anlegen und Assistent öffnen“ braucht vibe die Projektvorlagen.
        shutil.copytree(REPO / "templates", cls.root / "_toolchain" / "templates")
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR":
                    str(cls.root / "home" / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE":
                    str(cls.root / "home" / ".config" / "vibe" / "config.json"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
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
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Abschnitt auf, falls er als <details>
        umgesetzt ist. Auf der Bestandsstruktur bleibt der Aufruf ein No-op."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                self.wait_until(
                    lambda: section.evaluate("el => !!el.open"),
                    message="%s ließ sich nicht aufklappen" % selector,
                )

    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.tab("Arbeit").wait_for()

    def tab(self, name):
        return self.page.get_by_role("tab", name=name, exact=True)

    def panel(self, name):
        return self.page.locator(
            '[role="tabpanel"][data-panel="%s"]' % name.lower()
        )

    def selected_tab(self):
        return self.page.locator('[role="tab"][aria-selected="true"]').inner_text()

    def test_detail_groups_content_into_tabs_and_shows_only_the_active_area(self):
        self.open_detail()

        tablist = self.page.locator('[role="tablist"]')
        self.assertEqual(tablist.count(), 1, "Registerleiste fehlt")
        self.assertEqual(
            [self.tab(name).inner_text().strip() for name in TABS],
            TABS,
            "Register sind nicht vollständig oder falsch benannt",
        )
        self.assertEqual(self.selected_tab().strip(), "Arbeit")

        self.assertTrue(self.panel("arbeit").is_visible(), "Standardbereich ist nicht sichtbar")
        for other in ("ausgabe", "assistent", "einstellungen"):
            self.assertFalse(
                self.panel(other).is_visible(),
                "Bereich %s ist im Standardbild sichtbar" % other,
            )

        # Weniger wichtige Bereiche sind nicht gleichzeitig zu sehen.
        self.assertFalse(self.page.locator("#log").is_visible(), "Live-Ausgabe ist sofort sichtbar")
        self.assertFalse(self.page.locator("#guide").is_visible(), "Assistent ist sofort sichtbar")
        self.assertFalse(self.page.locator("#sandbox").is_visible(), "Sandbox ist sofort sichtbar")
        self.assertFalse(
            self.page.get_by_text("Schreibrechte (Agenten)").is_visible(),
            "Schreibrechte sind sofort sichtbar",
        )

        # Die wichtigen Inhalte der täglichen Arbeit sind im Standardbild da.
        self.assertIn("Feedback (", self.panel("arbeit").inner_text())
        self.assertTrue(self.page.get_by_text("Feedback eintragen").is_visible())

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(OVERVIEW_SHOT))
        self.assertTrue(OVERVIEW_SHOT.exists() and OVERVIEW_SHOT.stat().st_size > 0)

    def test_tabs_can_be_switched_by_mouse_and_keyboard(self):
        self.open_detail()

        self.tab("Einstellungen").click()
        self.wait_until(
            lambda: self.panel("einstellungen").is_visible(),
            message="Einstellungen wurden nicht geöffnet",
        )
        self.assertEqual(self.selected_tab().strip(), "Einstellungen")
        self.assertFalse(self.panel("arbeit").is_visible())
        self.assertTrue(self.page.locator("#sandbox").is_visible())
        self.assertTrue(
            self.page.get_by_text("Schreibrechte (Agenten)").is_visible()
        )

        # Der Einstellungen-Screenshot ist der Standardzustands-Nachweis des
        # AP7-Layouts; er darf nicht die Ladezeile der Agententabelle zeigen.
        # Die Suite ohne Agentendateien kennt keine Projekt-Agentenzeile,
        # deshalb ist das Ladeende-Signal die Toggle-Checkbox (erscheint erst
        # nach Abschluss von /api/project-agents) und zusätzlich der Nachweis,
        # dass die Ladezeile weg ist.
        toggle = self.page.locator('input[data-toggle="unconfigured"]')
        toggle.wait_for()
        self.assertNotIn(
            "Lade Agenten",
            self.panel("einstellungen").inner_text(),
            "Agententabelle lädt: Screenshot würde die Ladezeile zeigen",
        )

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SETTINGS_SHOT))
        self.assertTrue(SETTINGS_SHOT.exists() and SETTINGS_SHOT.stat().st_size > 0)

        self.tab("Einstellungen").focus()
        self.page.keyboard.press("Home")
        self.wait_until(
            lambda: self.selected_tab().strip() == "Arbeit",
            message="Home führte nicht zum ersten Register",
        )
        self.assertTrue(self.panel("arbeit").is_visible())

        self.page.keyboard.press("ArrowRight")
        self.wait_until(
            lambda: self.selected_tab().strip() == "Ausgabe",
            message="Pfeil rechts wechselte nicht zum nächsten Register",
        )
        self.assertTrue(self.panel("ausgabe").is_visible())
        self.assertTrue(self.page.locator("#log").is_visible())

        self.page.keyboard.press("End")
        self.wait_until(
            lambda: self.selected_tab().strip() == "Einstellungen",
            message="End führte nicht zum letzten Register",
        )

    def test_chosen_tab_survives_an_action_and_resets_when_leaving_the_detail(self):
        self.open_detail()
        self.tab("Einstellungen").click()
        self.wait_until(
            lambda: self.panel("einstellungen").is_visible(),
            message="Einstellungen wurden nicht geöffnet",
        )

        old_tablist = self.page.locator('[role="tablist"]').element_handle()
        self.expand_optional("#sandbox")
        tools = self.panel("einstellungen").get_by_label("Build-Werkzeuge")
        tools.fill("git npm")
        self.panel("einstellungen").get_by_role(
            "button", name="Werkzeuge speichern"
        ).click()
        self.wait_until(
            lambda: old_tablist.evaluate("el => !el.isConnected"),
            message="Die Aktion lud das Detail nicht neu",
        )
        self.assertEqual(
            self.selected_tab().strip(),
            "Einstellungen",
            "Die Aktion setzte das gewählte Register zurück",
        )
        self.expand_optional("#sandbox")
        self.assertEqual(
            self.panel("einstellungen").get_by_label("Build-Werkzeuge").input_value(),
            "git npm",
            "Die gespeicherten Werkzeuge stehen nach dem Neuladen nicht im Feld",
        )

        self.page.get_by_role("button", name="← zurück").click()
        row = self.page.locator("tr.row").first
        row.wait_for()
        row.click()
        self.wait_until(
            lambda: self.selected_tab().strip() == "Arbeit",
            message="Der Rückweg zur Projektliste setzte das Register nicht zurück",
        )
        self.assertTrue(self.panel("arbeit").is_visible())

    def test_verify_action_opens_the_output_area_and_streams_the_check_log(self):
        self.open_detail()

        self.panel("arbeit").get_by_role("button", name="Prüfung quick").click()
        self.wait_until(
            lambda: self.selected_tab().strip() == "Ausgabe",
            message="Prüfung wechselte nicht zur Ausgabe",
        )
        self.assertTrue(self.panel("ausgabe").is_visible())
        self.wait_until(
            lambda: "F13-Pruefung" in self.page.locator("#log").inner_text(),
            message="Ausgabe der Prüfung erschien nicht im Ausgabebereich",
        )

        # Die frühere Funktion „Lauf-Log“ bleibt erhalten: Sie hängt die
        # Ausgabe wieder an den Agentenlauf statt an die Prüfung.
        self.panel("ausgabe").get_by_role("button", name="Lauf-Log").click()
        self.wait_until(
            lambda: "Startzeile" in self.page.locator("#log").inner_text(),
            message="Lauf-Log verband die Ausgabe nicht wieder mit dem Agentenlauf",
        )

    def test_narrow_viewport_keeps_the_detail_usable_without_page_scroll(self):
        self.open_detail()
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.wait_for_timeout(200)

        self.assertTrue(self.tab("Arbeit").is_visible())
        self.tab("Einstellungen").click()
        self.wait_until(
            lambda: self.panel("einstellungen").is_visible(),
            message="Einstellungen wurden im schmalen Fenster nicht geöffnet",
        )
        self.assertTrue(self.page.locator("#sandbox").is_visible())
        overflow = self.page.evaluate(
            "document.documentElement.scrollWidth - window.innerWidth"
        )
        self.assertLessEqual(
            overflow, 1, "Projektdetail erzeugt horizontalen Seitenlauf im schmalen Fenster"
        )

    def test_each_tab_is_linked_to_its_panel_for_assistive_technology(self):
        self.open_detail()
        for name in TABS:
            tab = self.tab(name)
            panel_id = tab.get_attribute("aria-controls")
            self.assertTrue(panel_id, "Register %s hat kein aria-controls" % name)
            panel = self.page.locator("#" + panel_id)
            self.assertEqual(panel.count(), 1, "Panel für %s fehlt" % name)
            self.assertEqual(panel.get_attribute("role"), "tabpanel")
            self.assertEqual(panel.get_attribute("aria-labelledby"), tab.get_attribute("id"))

    def test_new_project_opens_the_assistant_area(self):
        self.page.goto(self.base + "/#t=" + self.token)
        form = self.page.locator("#nf")
        form.wait_for()
        form.locator("input").first.fill("neu")
        form.locator("select").select_option("generic")
        form.get_by_role("button", name="Anlegen und Assistent öffnen").click()
        self.wait_until(
            lambda: self.page.locator('[role="tab"][aria-selected="true"]').count() == 1
            and self.selected_tab().strip() == "Assistent",
            timeout=20,
            message="„Anlegen und Assistent öffnen“ öffnete nicht den Assistenten",
        )
        self.assertTrue(self.panel("assistent").is_visible())
        self.assertTrue(self.page.locator("#guide").is_visible())

    def test_primary_actions_and_run_state_stay_visible_in_every_area(self):
        self.open_detail()

        header = self.page.locator("main > div.bar").first
        self.assertTrue(
            header.get_by_role("button", name="Agentenlauf starten").is_visible()
        )
        self.assertTrue(header.locator("span.pill").first.is_visible())

        for name in TABS[1:]:
            self.tab(name).click()
            self.wait_until(
                lambda: self.panel(name.lower()).is_visible(),
                message="Bereich %s wurde nicht geöffnet" % name,
            )
            self.assertTrue(
                header.get_by_role("button", name="Agentenlauf starten").is_visible(),
                "Hauptaktion verschwand im Bereich %s" % name,
            )
            self.assertEqual(
                header.locator("span.pill").first.inner_text().strip()
                in ("läuft", "gestoppt"),
                True,
                "Laufzustand ist im Bereich %s nicht sichtbar" % name,
            )


if __name__ == "__main__":
    unittest.main()
