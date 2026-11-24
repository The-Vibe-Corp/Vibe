"""GH-47: Browserabnahme für Issues-Sync-Button und Zustandssteuerung.

Quelle der Ableitung: Arbeitspaket GH-47, ``SPEC.md`` und die verbindlichen
Nutzerentscheidungen q6cbba05d8ca9 (genau ein Sync) sowie der
Koordinatoren-Vertrag für die Nova-Zustandssteuerung:

* ``nvpOpenTicketDetail`` zeigt für nicht erledigte Tickets ein
  ``select[data-nv-ticket-state-select]`` mit den Werten
  ``draft|open|in-progress`` und den Button
  ``[data-nv-action='ticket-state-save']`` („Zustand setzen“).
* Erledigte Tickets zeigen stattdessen den Nachweis-Hinweis.
* Die Issues-Sektion hat genau einen Sync-Button und keine Reste von
  „Issues laden“, „Issues importieren“ oder dem Label-Filter.

Das echte Dashboard läuft isoliert auf einem freien Loopback-Port; bedient
wird es mit Chromium über Playwright. Es gibt keinen externen Netzaufruf: Die
GitHub-API-Basis zeigt auf eine geschlossene Loopback-Adresse, und der
Sync-Button wird nicht ausgelöst.

Ist Playwright oder Chromium nicht verfügbar, wird bewusst übersprungen (kein
erfundenes Grün). Run:

    python3 -m unittest tests.browser.test_gh47_issues_ui -v
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Umgebung ohne Playwright
    sync_playwright = None

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
PROJECT = "proj"
STAMP = "2026-01-01T00:00:00+00:00"


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
        Erwartet: Karte zeigt den Entwurf (data-nv-state=Draft); das Select
        bietet draft|open|in-progress und ist mit draft vorbelegt; nach dem
        Speichern steht AP2 im Speicher auf open und die Karte auf „offen“."""
        self.open_work()
        card = self.page.locator("article[data-nv-ticket='AP2']")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual("Draft", card.get_attribute("data-nv-state"), card.inner_text())
        self.assertRegex(card.inner_text(), r"(?i)draft|entwurf")

        card.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP2']")
        detail.wait_for(state="visible", timeout=20000)
        select = detail.locator("select[data-nv-ticket-state-select]")
        self.assertEqual(1, select.count(), "Zustands-Select fehlt im Detail")
        values = select.locator("option").evaluate_all(
            "els => els.map(e => e.value)")
        self.assertEqual(["draft", "open", "in-progress"], values)
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
        self.assertEqual("offen", card.get_attribute("data-nv-state"))
        self.assertEqual([], self.page_errors, self.page_errors)

    def test_done_and_blocked_tickets_follow_the_state_contract(self):
        """Vor: B1 blockiert, AP3 erledigt.
        Aktion: B1-Detail öffnen; danach erledigte anzeigen und AP3 öffnen.
        Erwartet: B1 hat ein Zustands-Select ohne Vorbelegung (blocked ist
        kein draft/open/in-progress); AP3 hat kein Select/Speichern, sondern
        den Nachweis-Hinweis."""
        self.open_work()
        blocked = self.page.locator("article[data-nv-feedback-item='B1']")
        blocked.wait_for(state="visible", timeout=20000)
        blocked.click()
        detail = self.page.locator("[data-nv-ticket-detail='B1']")
        detail.wait_for(state="visible", timeout=20000)
        select = detail.locator("select[data-nv-ticket-state-select]")
        self.assertEqual(1, select.count(),
                         "Blockierte Tickets brauchen die Zustandswahl")
        self.assertEqual("", select.input_value(),
                         "Blockierte Tickets dürfen keine Vorbelegung haben")

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


if __name__ == "__main__":
    unittest.main()
