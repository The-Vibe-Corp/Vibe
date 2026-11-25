"""Ticket-Oberfläche: Issues-Karte und Ticket-Dashboard.

Aufruf: python3 -m unittest tests.browser.test_tickets_ui -v
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


# ===========================================================================
# Browserabnahme für Issues-Sync-Button und Zustandssteuerung
# ===========================================================================

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Umgebung ohne Playwright
    sync_playwright = None

PROJECT = "proj"


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
class Gh47IssuesBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.port = free_port()
        cls.closed_api_port = free_port()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.store_path = cls.project / ".vibe" / "tickets.json"

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # noqa: BLE001 - Chromium kann fehlen
            cls.playwright.stop()
            if cls.proc.poll() is None:
                cls.proc.terminate()
                cls.proc.wait(timeout=5)
            cls.server_log.close()
            cls.tmp.cleanup()
            raise unittest.SkipTest(
                "Chromium ist für Playwright nicht verfügbar: " + str(error))

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
        cls.server_log.close()
        cls.tmp.cleanup()

    # -------------------------------------------------------------- Helfer
    def setUp(self):
        self.write_env()
        self.write_store([
            ticket("AP1", "Offenes Paket"),
            ticket("AP2", "Entwurf Paket", state="draft"),
            ticket("B1", "Blockierter Bug", type="bug", state="blocked",
                   blocked_reason="extern"),
            ticket("AP3", "Fertiges Paket", state="done", commit="abcdef1",
                   test="test_gh47"),
        ])
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 1000})
        self.page.set_default_timeout(15000)
        self.page_errors = []
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()

    def write_env(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\n'
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="http://127.0.0.1:%d"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % self.closed_api_port,
            encoding="utf-8")

    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item for item in json.loads(
            self.store_path.read_text(encoding="utf-8"))["tickets"]}

    def wait_until(self, predicate, timeout=20, message="Bedingung fehlt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def enable_github_feature(self):
        self.boot()
        self.page.locator(
            "nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        box = self.page.locator("input[data-nv-feature='github']")
        box.wait_for(state="visible", timeout=20000)
        if not box.is_checked():
            box.check()
        self.wait_until(lambda: box.is_checked(), timeout=20,
                        message="Der Feature-Schalter github blieb aus")

    def open_github_settings(self):
        self.enable_github_feature()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/settings")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        section = self.page.locator("[data-nv-psection='github']")
        section.wait_for(state="visible", timeout=25000)
        return section

    def open_work(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/work")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("section[data-nv-ppanel='work']").wait_for(
            state="visible", timeout=20000)

    # -------------------------------------------------------------- Fälle
    def test_issues_section_offers_one_sync_and_no_legacy_actions(self):
        """Vor: Issues-Sync aktiv, GitHub-Feature an.
        Aktion: GitHub-Sektion öffnen.
        Erwartet: genau ein ``[data-nv-action='issues-sync']``; keine
        ``github-issues``/``github-import`` und kein
        ``[data-nv-field='github-issue-label']``; Erklärung nennt
        Synchronisieren, Ready, Entwurf und Schließen."""
        section = self.open_github_settings()

        self.assertEqual(
            1, section.locator("[data-nv-action='issues-sync']").count(),
            "Genau ein Sync-Button erwartet")
        self.assertEqual(
            0, section.locator("[data-nv-action='github-issues']").count(),
            "„Issues laden“ ist noch vorhanden")
        self.assertEqual(
            0, section.locator("[data-nv-action='github-import']").count(),
            "„Issues importieren“ ist noch vorhanden")
        self.assertEqual(
            0, section.locator("[data-nv-field='github-issue-label']").count(),
            "Der Label-Filter der Issues-Sektion ist noch vorhanden")
        text = section.inner_text()
        self.assertRegex(text, r"(?i)synchroni[sz]",
                         "Der einheitliche Sync wird nicht erklärt")
        self.assertRegex(text, r"(?i)ready", "Das Ready-Label fehlt im Text")
        self.assertRegex(text, r"(?i)entwurf|draft",
                         "Die Ready-/Entwurf-Abbildung fehlt im Text")
        self.assertRegex(text, r"(?i)schließ|schliess|close",
                         "Das Best-effort-Schließen wird nicht erklärt")
        self.assertEqual([], self.page_errors, self.page_errors)

    def test_ticket_detail_state_control_changes_draft_to_open(self):
        """Vor: AP2 ist Entwurf. Aktion: Arbeit öffnen, Karte AP2 anklicken,
        ``select[data-nv-ticket-state-select]`` auf open setzen und
        ``ticket-state-save`` klicken.
        Erwartet: Karte zeigt den Entwurf (data-nv-state=draft); das Select
        bietet nur draft|open (in-progress gehört dem Läufer) und ist mit
        draft vorbelegt; nach dem Speichern steht AP2 im Speicher auf open
        und die Karte auf „open“."""
        self.open_work()
        card = self.page.locator("article[data-nv-ticket='AP2']")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual("draft", card.get_attribute("data-nv-state"), card.inner_text())
        self.assertRegex(card.inner_text(), r"(?i)draft|entwurf")

        card.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP2']")
        detail.wait_for(state="visible", timeout=20000)
        select = detail.locator("select[data-nv-ticket-state-select]")
        self.assertEqual(1, select.count(), "Zustands-Select fehlt im Detail")
        values = select.locator("option").evaluate_all(
            "els => els.map(e => e.value)")
        self.assertEqual(["draft", "open"], values)
        self.assertEqual("draft", select.input_value())

        select.select_option("open")
        detail.locator(
            "button[data-nv-action='ticket-state-save']").click()

        self.wait_until(
            lambda: self.read_store()["AP2"]["state"] == "open",
            message="Der Zustandswechsel wurde nicht gespeichert")
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        card = self.page.locator("article[data-nv-ticket='AP2']")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual("open", card.get_attribute("data-nv-state"))
        self.assertEqual([], self.page_errors, self.page_errors)

    def test_done_and_blocked_tickets_follow_the_state_contract(self):
        """Vor: B1 blockiert, AP3 erledigt.
        Aktion: B1-Detail öffnen; danach erledigte anzeigen und AP3 öffnen.
        Erwartet: B1 hat weder Zustands-Select noch Speichern-Knopf, sondern
        den Läufer-Hinweis (blocked gehört dem Läufer); AP3 hat kein
        Select/Speichern, sondern den Nachweis-Hinweis."""
        self.open_work()
        blocked = self.page.locator("article[data-nv-feedback-item='B1']")
        blocked.wait_for(state="visible", timeout=20000)
        blocked.click()
        detail = self.page.locator("[data-nv-ticket-detail='B1']")
        detail.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, detail.locator("select[data-nv-ticket-state-select]").count(),
            "Blockierte Tickets dürfen keine Zustandsauswahl anbieten")
        self.assertEqual(
            0, detail.locator(
                "button[data-nv-action='ticket-state-save']").count(),
            "Blockierte Tickets dürfen keinen Zustand speichern")
        notice = detail.locator("[data-nv-runner-state-notice]")
        self.assertEqual(
            1, notice.count(),
            "Blockierte Tickets zeigen keinen Läufer-Zustandshinweis")
        self.assertTrue(notice.first.is_visible(),
                        "Der Läufer-Zustandshinweis ist nicht sichtbar")
        self.assertRegex(notice.first.inner_text(), r"(?i)läufer|runner",
                         "Der Hinweis nennt nicht den Läufer")

        # Das Kontext-Panel (nv-context-scrim) liegt über der Arbeitsebene;
        # erst schließen, sonst ist der Erledigt-Umschalter nicht klickbar.
        self.page.keyboard.press("Escape")
        detail.wait_for(state="hidden", timeout=10000)

        toggle = self.page.locator("[data-nv-work-hide-done]")
        if toggle.count():
            toggle.first.click()
        done = self.page.locator("article[data-nv-ticket='AP3']")
        done.wait_for(state="visible", timeout=20000)
        done.click()
        done_detail = self.page.locator("[data-nv-ticket-detail='AP3']")
        done_detail.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, done_detail.locator(
                "select[data-nv-ticket-state-select]").count(),
            "Erledigte Tickets dürfen keine Zustandswahl zeigen")
        self.assertEqual(
            0, done_detail.locator(
                "button[data-nv-action='ticket-state-save']").count())
        self.assertRegex(done_detail.inner_text(),
                         r"(?i)nachweis|erledigt|abgeschlossen|evidence|completed|done")
        self.assertEqual([], self.page_errors, self.page_errors)


# ===========================================================================
# Browserabnahme für Tickets im Dashboard ohne Markdown-Ledger
# ===========================================================================

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


def isolated_env_gh48(root, home, port):
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
            env=isolated_env_gh48(cls.root, cls.home, cls.port),
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
        nur draft/open (in-progress gehört dem Läufer); Voreinstellung
        ist open.
        Fehlerfall: kein Zustandsfeld (offline keine Zustände), ein
        Läufer-Zustand oder andere Werte."""
        self.open_detail()

        for form_id in ("ticket-new", "feedback-new"):
            with self.subTest(form=form_id):
                select = self.state_select(form_id)
                values = select.locator("option").evaluate_all(
                    "els => els.map(e => e.value)")
                self.assertEqual(["draft", "open"], values)
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
