"""GH-48: Browserabnahme für Tickets im Dashboard ohne Markdown-Ledger.

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` und der verbindliche
Implementierungsvertrag GH-48 (§7 Web-API/Oberflächen). Das echte Dashboard
läuft auf einem eigenen Port mit temporären Pfaden; bedient wird es mit
Chromium über Playwright. Der Projektordner enthält ausschließlich
``.vibe/tickets.json`` — kein TICKETS.md/FEEDBACK.md.

Geprüft wird:
* das Zustandsauswahlfeld in Ticket- und Feedback-Formular mit den
  Vertragswerten draft/open/in-progress und Voreinstellung open,
* Anlegen eines Entwurfs offline: gespeicherter Zustand draft und sichtbarer
  Pill „Draft",
* Anzeige bestehender Zustände (In Progress, BLOCKIERT, erledigt) aus dem
  Speicher; der frühere Pill „ohne Nachweis" erscheint nicht,
* ein offline angelegtes Ticket erzeugt keine TICKETS.md.

Ist Playwright oder Chromium in der Umgebung nicht verfügbar, wird der Fall
mit Begründung übersprungen (kein erfundenes Grün). Kein Netz außer Loopback,
keine Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.browser.test_gh48_tickets_ui -v
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

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Umgebung ohne Playwright
    sync_playwright = None

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
STAMP = "2026-01-01T00:00:00+00:00"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER",
)


def isolated_env(root, home, port):
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "VIBE_UI_PORT": str(port),
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_toolchain"),
        "VIBE_INSTALL": str(Path(root) / "_toolchain"),
        "VIBE_RUNTIME": str(Path(root) / "_logs"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    return env


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


@unittest.skipIf(sync_playwright is None, "Playwright ist nicht installiert.")
class TicketDashboardBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        cls.store_path = cls.project / ".vibe" / "tickets.json"
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        cls.port = free_port()

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # noqa: BLE001 - Chromium kann fehlen
            cls.playwright.stop()
            cls.tmp.cleanup()
            raise unittest.SkipTest(
                "Chromium ist für Playwright nicht verfügbar: " + str(error))

        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=isolated_env(cls.root, cls.home, cls.port),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                cls.browser.close()
                cls.playwright.stop()
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            cls.browser.close()
            cls.playwright.stop()
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = "http://127.0.0.1:%d" % cls.port

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
        self.write_store([
            ticket("AP1", "Bestehendes Paket"),
            ticket("B1", "Bestehender Bug", type="bug"),
        ])
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400,
                                                    "height": 1000})
        self.page.set_default_timeout(8000)

    def tearDown(self):
        self.page.close()

    # -------------------------------------------------------------- Helfer
    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item for item in json.loads(
            self.store_path.read_text(encoding="utf-8"))["tickets"]}

    def wait_until(self, predicate, timeout=10, message="Bedingung fehlt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.locator("#tickets").wait_for()

    def state_select(self, form_id):
        select = self.page.locator("#" + form_id + " select").first
        select.wait_for()
        return select

    # -------------------------------------------------------------- Fälle
    def test_ticket_and_feedback_forms_offer_the_contract_states(self):
        """Vor: bestehender Speicher. Aktion: Detailansicht öffnen.
        Erwartet: Ticket- und Feedback-Formular haben ein Zustandsfeld mit
        draft/open/in-progress; Voreinstellung ist open.
        Fehlerfall: kein Zustandsfeld (offline keine Zustände) oder andere
        Werte."""
        self.open_detail()

        for form_id in ("ticket-new", "feedback-new"):
            with self.subTest(form=form_id):
                select = self.state_select(form_id)
                values = select.locator("option").evaluate_all(
                    "els => els.map(e => e.value)")
                self.assertEqual(["draft", "open", "in-progress"], values)
                self.assertEqual("open", select.input_value())

    def test_create_a_draft_ticket_offline_and_show_its_state(self):
        """Vor: kein TICKETS.md, Speicher mit AP1. Aktion: Ticket mit
        Beschreibung und Zustand draft anlegen.
        Erwartet: Speicher enthält den neuen Entwurf (state=draft), die
        Karte zeigt „Draft", TICKETS.md entsteht nicht.
        Fehlerfall: Entwurf wird offen gespeichert, nicht angezeigt oder in
        Markdown geschrieben."""
        self.open_detail()
        form = self.page.locator("#ticket-new")
        form.locator("input").nth(1).fill("Entwurf Paket")
        form.locator("textarea").fill("Noch nicht bereit")
        self.state_select("ticket-new").select_option("draft")
        form.locator("button").first.click()

        self.wait_until(
            lambda: any(record["title"] == "Entwurf Paket"
                        for record in self.read_store().values()),
            message="Entwurf wurde nicht im Ticketspeicher angelegt",
        )
        fresh = [record for record in self.read_store().values()
                 if record["title"] == "Entwurf Paket"][0]
        self.assertEqual("draft", fresh["state"])
        self.assertFalse((self.project / "TICKETS.md").exists())

        entry = self.page.locator(
            '#tickets .fbentry[data-id="%s"]' % fresh["id"])
        entry.wait_for()
        self.assertIn("Draft", entry.inner_text())
        self.assertNotIn("ohne Nachweis", entry.inner_text())

    def test_existing_states_from_the_store_are_displayed(self):
        """Vor: Speicher mit in-progress, blockiertem und erledigtem Ticket.
        Aktion: Detailansicht öffnen.
        Erwartet: die Karten zeigen „In Progress", „BLOCKIERT" und
        „erledigt"; der entfallene Pill „ohne Nachweis" erscheint nirgends.
        Fehlerfall: Zustände stammen weiter aus Markdown oder der alte
        Pill bleibt sichtbar."""
        self.write_store([
            ticket("AP2", "Läuft gerade", state="in-progress"),
            ticket("B1", "Blockierter Bug", type="bug", state="blocked",
                   blocked_reason="Grund"),
            ticket("AP3", "Fertig", state="done", commit="abcdef1",
                   test="test_ap3"),
        ])
        self.open_detail()

        open_entry = self.page.locator('#tickets .fbentry[data-id="AP2"]')
        open_entry.wait_for()
        self.assertIn("In Progress", open_entry.inner_text())
        feedback = self.page.locator('#feedback .fbentry[data-id="B1"]')
        feedback.wait_for()
        self.assertIn("BLOCKIERT", feedback.inner_text())

        # Langjähriges Classic-Verhalten: abgeschlossene Punkte sind
        # standardmäßig ausgeblendet. Die Karte bietet dafür einen
        # Umschalter; erst dann ist der erledigt-Pill sichtbar.
        self.assertFalse(
            self.page.locator('#tickets .fbentry[data-id="AP3"]').count())
        toggle = self.page.locator("#tickets button", has_text="Show completed")
        if not toggle.count():
            toggle = self.page.locator("#tickets button",
                                       has_text="Abgeschlossene anzeigen")
        toggle.first.click()
        done_entry = self.page.locator('#tickets .fbentry[data-id="AP3"]')
        done_entry.wait_for()
        self.assertIn("erledigt", done_entry.inner_text())

        body = self.page.locator("body").inner_text()
        self.assertNotIn("ohne Nachweis", body)


if __name__ == "__main__":
    unittest.main()
