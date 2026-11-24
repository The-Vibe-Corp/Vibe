"""Browserabnahme für Arbeitspakete und Bugmeldungen (F15, GH-48).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden Anlegen, Bearbeiten und Löschen
von Arbeitspaketen sowie das Melden eines Bugs — auf dem JSON-Ticketspeicher
``.vibe/tickets.json``. Markdown-Ledger existieren nicht mehr.

Ist Playwright oder Chromium in der Umgebung nicht verfügbar, wird das Modul
mit Begründung übersprungen (kein erfundenes Grün).
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
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Umgebung ohne Playwright
    sync_playwright = None

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SHOTS = Path(
    os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")
)
SHOT = SHOTS / "F15-arbeitspakete.png"
STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


BASELINE = [
    ticket_record("F15", "Arbeitspakete", description="Bestehendes Paket",
                  priority="P1"),
    ticket_record("V-001", "Erledigtes Paket", state="done",
                  description="Fertig", commit="abcdef1", test="test_x"),
    ticket_record("F1", "Bestehender Punkt", type="feedback",
                  description="Bestehende Beschreibung"),
]

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
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    return env


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipIf(sync_playwright is None, "Playwright ist nicht installiert.")
class WorkPackageBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        cls.store = cls.project / ".vibe" / "tickets.json"
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # noqa: BLE001 - Chromium kann fehlen
            cls.playwright.stop()
            cls.tmp.cleanup()
            raise unittest.SkipTest(
                "Chromium ist für Playwright nicht verfügbar: " + str(error))

        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
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
        cls.base = f"http://127.0.0.1:{cls.port}"

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
        self.store.write_text(
            json.dumps({"version": 1, "tickets": BASELINE},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400,
                                                    "height": 1000})
        self.page.set_default_timeout(10000)

    def tearDown(self):
        self.page.close()

    # -------------------------------------------------------------- Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung fehlt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def records(self):
        return {item["id"]: item for item in json.loads(
            self.store.read_text(encoding="utf-8"))["tickets"]}

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.locator("#tickets").wait_for()
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()

    def create_ticket(self, title, description, tid="", state=""):
        form = self.page.locator("#ticket-new")
        if tid:
            form.locator("input").first.fill(tid)
        form.locator("input").nth(1).fill(title)
        form.locator("textarea").fill(description)
        if state:
            form.locator("select").first.select_option(state)
        form.locator("button").first.click()

    # -------------------------------------------------------------- Fälle
    def test_add_edit_and_delete_a_work_package(self):
        """Vor: Speicher mit F15 und done V-001. Aktion: F18 über das Formular
        anlegen, bearbeiten, löschen. Erwartet: Datensatz mit Titel,
        Beschreibung und Zustand entsteht, ändert sich und verschwindet;
        F15 und der erledigte Nachweis bleiben erhalten."""
        self.open_detail()

        self.create_ticket("Neues Paket", "Zeile eins\nZeile zwei", tid="F18")

        self.wait_until(
            lambda: "F18" in self.records(),
            message="Neues Arbeitspaket wurde nicht gespeichert",
        )
        record = self.records()["F18"]
        self.assertEqual("Neues Paket", record["title"])
        self.assertEqual("Zeile eins\nZeile zwei", record["description"])
        self.assertEqual("task", record["type"])
        self.assertEqual("open", record["state"])
        self.assertEqual("P1", self.records()["F15"]["priority"])

        entry = self.page.locator('#tickets .fbentry[data-id="F18"]')
        entry.get_by_role("button", name="Edit").click()
        entry.locator("input").fill("Geändertes Paket")
        entry.locator("textarea").fill("Geänderte Beschreibung")
        entry.get_by_role("button", name="Save").click()

        self.wait_until(
            lambda: self.records()["F18"]["title"] == "Geändertes Paket",
            message="Bearbeitetes Arbeitspaket wurde nicht gespeichert",
        )
        self.assertEqual("Geänderte Beschreibung",
                         self.records()["F18"]["description"])
        self.assertEqual("P1", self.records()["F15"]["priority"])

        entry = self.page.locator('#tickets .fbentry[data-id="F18"]')
        entry.get_by_role("button", name="Delete").click()
        entry.locator(".confirm").get_by_role(
            "button", name="Yes, delete").click()
        self.wait_until(
            lambda: "F18" not in self.records(),
            message="Arbeitspaket wurde nicht gelöscht",
        )
        records = self.records()
        self.assertIn("F15", records)
        self.assertEqual("done", records["V-001"]["state"])

    def test_add_work_package_without_an_id_and_use_the_assigned_id(self):
        """F23/AK8: Das ID-Feld bleibt leer; die Oberfläche zeigt die
        automatisch vergebene ID und meldet sie. Anschließend bearbeiten und
        löschen."""
        self.open_detail()

        self.create_ticket("Auto Paket", "Zeile eins\nZeile zwei")

        def assigned_id():
            identifiers = self.page.eval_on_selector_all(
                "#tickets .fbentry", "els => els.map(e => e.dataset.id)")
            fresh = [ident for ident in identifiers
                     if ident not in ("F15", "V-001")]
            return fresh[0] if len(fresh) == 1 else None

        self.wait_until(assigned_id, message="Arbeitspaket ohne ID fehlt")
        assigned = assigned_id()
        self.assertTrue(assigned)
        self.assertRegex(assigned, r"[A-Za-z0-9][A-Za-z0-9_.:-]*")
        self.assertIn(assigned, self.records())
        self.assertEqual("Auto Paket", self.records()[assigned]["title"])

        self.wait_until(
            lambda: f"{assigned} angelegt"
            in "\n".join(self.page.locator(".toasttext").all_inner_texts()),
            message="Meldung nennt nicht die vergebene ID",
        )

        entry = self.page.locator('#tickets .fbentry[data-id="%s"]' % assigned)
        entry.get_by_role("button", name="Edit").click()
        entry.locator("textarea").fill("Geänderte Beschreibung")
        entry.get_by_role("button", name="Save").click()

        self.wait_until(
            lambda: self.records()[assigned]["description"]
            == "Geänderte Beschreibung",
            message="Bearbeitetes Auto-Arbeitspaket wurde nicht gespeichert",
        )
        self.assertEqual("Auto Paket", self.records()[assigned]["title"])

        entry = self.page.locator('#tickets .fbentry[data-id="%s"]' % assigned)
        entry.get_by_role("button", name="Delete").click()
        entry.locator(".confirm").get_by_role(
            "button", name="Yes, delete").click()
        self.wait_until(
            lambda: assigned not in self.records(),
            message="Auto-Arbeitspaket wurde nicht gelöscht",
        )
        self.assertIn("F15", self.records())

    def test_report_a_bug_from_the_ui(self):
        """Vor: F1 als Feedback im Speicher. Aktion: Bug über das Formular
        melden. Erwartet: B1 mit type bug und Beschreibung, F1 bleibt."""
        self.open_detail()

        form = self.page.locator("#bug-new")
        form.locator("input").fill("Absturz beim Start")
        form.locator("textarea").fill("Fenster bleibt leer")
        form.get_by_role("button", name="Report bug").click()

        self.wait_until(
            lambda: any(record["type"] == "bug"
                        for record in self.records().values()),
            message="Bugmeldung wurde nicht gespeichert",
        )
        bug = next(record for record in self.records().values()
                   if record["type"] == "bug")
        self.assertEqual("B1", bug["id"])
        self.assertEqual("Absturz beim Start", bug["title"])
        self.assertEqual("Fenster bleibt leer", bug["description"])
        self.assertIn("F1", self.records())

        entry = self.page.locator('#feedback .fbentry[data-id="B1"]')
        entry.wait_for()
        self.assertIn("Bug", entry.inner_text())
        self.assertIn("Absturz beim Start", entry.inner_text())

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.is_file())
        self.assertGreater(SHOT.stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
