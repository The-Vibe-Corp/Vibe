"""Browserabnahme AP11 „Priorisierung der Abarbeitungsreihenfolge“.

Das Dashboard erhält im Projekt-Einstellungs-Tab einen neuen optionalen
Abschnitt „Priorisierung“ (TICKETS.md AP11, AK 9):

* der Abschnitt erscheint in ``#panel-einstellungen`` als ``details``-Abschnitt
  mit ``data-goto``-Sprungknopf in der Abschnittsleiste und lässt sich über
  diesen aufklappen,
* der Abschnitt zeigt die sich aus der Konfiguration ergebende effektive
  Abarbeitungsreihenfolge der offenen Pakete,
* „Speichern“ einer Reihenfolge schreibt ``PACKAGE_ORDER`` in
  ``.vibe/project.env`` des Testprojekts (POST /api/priority, action set,
  wie das /api/rights-Schreibmuster), „Löschen“ leert ihn (action clear);
  andere Zeilen von project.env bleiben erhalten,
* GET /api/priority?name= liefert die konfigurierte Reihenfolge mit Status je
  Eintrag (offen/erledigt/gesperrt/fehlt), die effektive Reihenfolge und eine
  Meldung.

Die Tests starten das echte Dashboard auf einem eigenen Port mit vollständig
isolierten VIBE_*-Pfaden (Muster tests/browser/test_ap7_settings_ui.py) und
bedienen es mit Chromium über Playwright. Chromium wird nur aus dem Nutzer-
Cache gelesen (~/.cache/ms-playwright), nie heruntergeladen. Keine echten
externen Dienste, keine Modellaufrufe.

Run:

    python3 -m unittest tests.browser.test_ap11_priority_ui -v
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap7_settings_ui.py).
_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

# Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
# produktive Installation zeigen lassen; der Test besitzt alle Laufzeitpfade.
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


def git(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60,
        env=env,
    )


class Ap11PriorityBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        git(cls.project, "init", "-q", "-b", "main")
        (cls.project / ".vibe").mkdir(exist_ok=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8")
        # Eine nachweislich erledigte Aufgabe und zwei offene Aufgaben:
        # die Statusanzeige der API (erledigt/offen) wird dadurch prüfbar.
        git(cls.project, "commit", "--allow-empty", "-q", "-m", "init")
        commit = subprocess.run(
            ["git", "-C", str(cls.project), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "- [x] T0 Erledigte Aufgabe\n"
            "  Beschreibung: fertig\n"
            "  Commit: %s; Test: test_ap11\n\n" % commit +
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        git(cls.project, "add", "-A")
        git(cls.project, "commit", "-q", "-m", "Nachweis T0")
        cls.env_path = cls.project / ".vibe" / "project.env"

        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
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
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"),
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
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
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

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_settings(self):
        """Vorbedingung einstellen: Projekt öffnen, Register „Einstellungen“."""
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        panel = self.page.locator("#panel-einstellungen")
        panel.wait_for()
        self.assertTrue(panel.is_visible(),
                        "Einstellungen-Panel ist nicht sichtbar")

    def priority_chip(self):
        """Der data-goto-Sprungknopf des Priorisierungs-Abschnitts."""
        return self.page.locator(
            '#panel-einstellungen [data-goto*="prioris" i]').first

    def priority_section(self):
        """Der details-Abschnitt „Priorisierung“ im Einstellungs-Panel."""
        return self.page.locator(
            '#panel-einstellungen details', has_text="Priorisierung").first

    def open_priority_section(self):
        """Klappt den Priorisierungs-Abschnitt über den Sprungknopf auf."""
        self.open_settings()
        chip = self.priority_chip()
        chip.wait_for(timeout=10000)
        section = self.priority_section()
        section.wait_for(timeout=10000)
        if not section.evaluate("el => !!el.open"):
            chip.click(timeout=2000)
        self.wait_until(
            lambda: section.evaluate("el => !!el.open"),
            message="Priorisierungs-Abschnitt ließ sich nicht aufklappen")
        return section

    def priority_input(self, section):
        """Die Kennungs-Eingabe des Priorisierungs-Abschnitts."""
        field = section.locator("input[type='text'], input:not([type]), "
                                "textarea").first
        field.wait_for(timeout=10000)
        return field

    def save_button(self, section):
        return section.get_by_role("button", name="Speichern").first

    def clear_button(self, section):
        return section.get_by_role(
            "button", name=re.compile(r"Löschen|Leeren|Zurücksetzen|Clear",
                                      re.I)).first

    def reenter_settings(self):
        """Baut das Register neu auf (Server liest Projektdateien neu ein)."""
        self.page.get_by_role("tab", name="Arbeit", exact=True).click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#panel-einstellungen").wait_for()

    # ------------------------------------------------------------ Testfälle
    def test_priority_section_is_details_with_data_goto_chip(self):
        """AK 9 (Struktur).

        Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“.
        Aktion: Abschnittsleiste und Priorisierungs-Abschnitt inspizieren und
        den data-goto-Sprungknopf betätigen.
        Erwartet: ein data-goto-Sprungknopf für die Priorisierung existiert
        in #panel-einstellungen; der Priorisierungs-Abschnitt ist ein
        ``details``-Element; der Knopfklapp klappt den Abschnitt auf.
        """
        self.open_settings()

        chip = self.priority_chip()
        chip.wait_for(timeout=10000)
        section = self.priority_section()
        section.wait_for(timeout=10000)
        self.assertEqual(
            "details",
            section.evaluate("el => el.tagName.toLowerCase()"),
            "Der Priorisierungs-Abschnitt ist kein details-Element",
        )
        chip.click(timeout=2000)
        self.wait_until(
            lambda: section.evaluate("el => !!el.open"),
            message="Der data-goto-Knopf klappte den Priorisierungs-Abschnitt "
                    "nicht auf",
        )

    def test_priority_section_shows_the_effective_order(self):
        """AK 9 (Anzeige).

        Vorbedingung: Projekt mit erledigter T0 und offenen Aufgaben T1, T2;
        kein PACKAGE_ORDER-Eintrag; Priorisierungs-Abschnitt aufgeklappt.
        Aktion: den Abschnittstext lesen.
        Erwartet: der Abschnitt zeigt die effektive Abarbeitungsreihenfolge
        der offenen Pakete — T1 erscheint vor T2; die erledigte T0 steht
        nicht vor den offenen Aufgaben als nächste Wahl.
        """
        section = self.open_priority_section()

        text = section.inner_text()
        self.assertIn("T1", text, "effektive Reihenfolge nennt T1 nicht")
        self.assertIn("T2", text, "effektive Reihenfolge nennt T2 nicht")
        self.assertLess(text.index("T1"), text.index("T2"),
                        "effektive Reihenfolge ist nicht T1 vor T2: " + text)

    def test_save_writes_package_order_and_clear_empties_it(self):
        """AK 9 (Speichern/Löschen).

        Vorbedingung: Priorisierungs-Abschnitt aufgeklappt; project.env ohne
        PACKAGE_ORDER.
        Aktion 1: „T2,T1“ eintragen und „Speichern“ drücken.
        Erwartet 1: project.env enthält PACKAGE_ORDER mit T2 vor T1 und
        behält TYPE=generic sowie TESTER.
        Aktion 2: Register neu betreten, Abschnitt aufklappen, „Löschen“
        drücken.
        Erwartet 2: PACKAGE_ORDER ist geleert (keine Kennung mehr); die
        übrigen Zeilen bleiben.
        """
        section = self.open_priority_section()
        field = self.priority_input(section)
        field.fill("T2,T1")
        self.save_button(section).click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env",
        )
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("T2", text)
        self.assertIn("T1", text)
        self.assertLess(
            text.index("T2"), text.index("T1"),
            "PACKAGE_ORDER wurde nicht in der gewählten Reihenfolge "
            "abgelegt: " + text,
        )
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        self.reenter_settings()
        # goto mit gleichem Hash-Anker lädt nicht neu; der Abschnitt wird
        # deshalb direkt per data-goto-Chip aufgeklappt statt den
        # Übersichts-Zyklus erneut zu durchlaufen.
        section = self.priority_section()
        section.wait_for(timeout=10000)
        chip = self.priority_chip()
        if not section.evaluate("el => !!el.open"):
            chip.click(timeout=2000)
        self.wait_until(
            lambda: section.evaluate("el => !!el.open"),
            message="Priorisierungs-Abschnitt ließ sich beim zweiten Eintritt "
                    "nicht aufklappen")
        self.clear_button(section).click()
        self.wait_until(
            lambda: re.search(
                r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?\s*["\']?\s*$',
                self.env_path.read_text(encoding="utf-8"))
            or "PACKAGE_ORDER" not in self.env_path.read_text(
                encoding="utf-8"),
            message="Löschen leerte PACKAGE_ORDER nicht",
        )
        text = self.env_path.read_text(encoding="utf-8")
        self.assertNotIn("T2,", text.replace("TYPE=generic", ""),
                         "Löschen hinterließ Kennungen in PACKAGE_ORDER")
        self.assertIn("TYPE=generic", text, "Löschen beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Löschen beschädigte project.env")

    def test_priority_api_reports_configured_effective_and_status(self):
        """AK 9 (GET /api/priority).

        Vorbedingung: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt
        (mit Nachweis), T1/T2 offen, X9 unbekannt.
        Aktion: GET /api/priority?name=proj mit Token stellen und die JSON-
        Antwort auswerten.
        Erwartet: HTTP 200; die Antwort nennt die konfigurierten Einträge
        samt Status (erledigt für T0, fehlt für X9), enthält eine
        effektive Reihenfolge, die T2 vor T1 ohne erledigtes T0 zeigt, und
        eine Meldung.
        """
        write_env = self.env_path.read_text(encoding="utf-8")
        write_env = write_env + 'PACKAGE_ORDER="T2,T0,X9,T1"\n'
        self.env_path.write_text(write_env, encoding="utf-8")
        # Die Fixture-Datei ist geteilt: Nach diesem Test gilt wieder die
        # Standardkonfiguration, damit nachfolgende Tests unverändert laufen.
        self.addCleanup(
            lambda: self.env_path.write_text(
                "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8"))

        request = urllib.request.Request(
            f"{self.base}/api/priority?name=proj", method="GET")
        request.add_header("X-Token", self.token)
        with urllib.request.urlopen(request, timeout=20) as response:
            self.assertEqual(200, response.status)
            payload = json.loads(response.read().decode("utf-8"))

        dumped = json.dumps(payload, ensure_ascii=False)
        for identifier in ("T0", "T1", "T2", "X9"):
            self.assertIn(identifier, dumped,
                          "Antwort nennt %s nicht: %s" % (identifier, dumped))
        self.assertIn("erledigt", dumped,
                      "Status erledigt fehlt: " + dumped)
        self.assertIn("fehlt", dumped, "Status fehlt für X9: " + dumped)

        # „order" und „queue" sind Listen von Objekten (id, title, status).
        order = {entry["id"]: entry.get("status", "")
                 for entry in payload.get("order", [])
                 if isinstance(entry, dict) and "id" in entry}
        queue = [entry["id"] for entry in payload.get("queue", [])
                 if isinstance(entry, dict) and "id" in entry]
        self.assertEqual({"T2": "offen", "T0": "erledigt", "X9": "fehlt",
                          "T1": "offen"},
                         order,
                         "Status je konfiguriertem Eintrag falsch: " + dumped)
        self.assertEqual(["T2", "T1"], queue,
                         "effektive Reihenfolge falsch: " + dumped)
        self.assertNotIn("T0", queue,
                         "die erledigte T0 rückt in die effektive "
                         "Reihenfolge: " + dumped)
        self.assertTrue(
            any("meldung" in key.lower() or "message" in key.lower()
                for key in self._keys(payload)),
            "keine Meldung in der Antwort: " + dumped,
        )

    def _keys(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from self._keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._keys(item)


if __name__ == "__main__":
    unittest.main()
