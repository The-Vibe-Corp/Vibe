"""Browserabnahme AP19 (Teil 5): Sessions-Karte im Projektpanel.

Arbeitspaket AP19 „Session Management“ verlangt, dass der Nutzer die letzten
Sessions im Dashboard sieht, ihren Zustand erkennt und eine Session – auch
nach einem unerwarteten Abbruch – exakt fortsetzen kann (AK1–AK3). Die
Sessions-Karte liegt im Projektbereich ``[data-panel='arbeit']``.

Verbindlicher UI-Vertrag dieser Abnahme (bewusst schlank):

* Eine Karte mit der Überschrift „Sessions“ zeigt die Sessions aus
  ``GET /api/sessions?name=<projekt>``. Jede Zeile ist ein Element mit
  ``data-session="<kennung>"`` und nennt Kennung, deutsches Zustandslabel,
  Agent und eine für Menschen lesbare Zeit (``last_seen``).
* Der Zustand erscheint als Pille ``span.pill`` mit genau einer Tonklasse:
  ``run`` (läuft), ``ok`` (abgeschlossen), ``warn`` (abgebrochen),
  ``bad`` (fehlgeschlagen), ``mut`` (sonst/unbekannt).
* Je fortsetzbarer Zeile gibt es einen Knopf „Fortsetzen“. Sein Klick sendet
  ``POST /api/sessions`` mit exakt ``{"name", "session", "action":
  "continue"}``.
* Ist ein Lauf des Projekts aktiv (``running: true``), wird kein Fortsetzen
  angeboten (Knopf fehlt oder ist deaktiviert).
* Ohne erfasste Sessions erscheint der Leertext „Noch keine erfassten
  Sessions.“
* Kann der gewählte Harness nicht fortsetzen (``resume_supported: false``,
  z. B. Pi), erscheint kein Fortsetzen-Knopf und die Karte erklärt den Grund
  mit „Pi“ und „--no-session“.
* Die Karte ist per Tastatur bedienbar: Der Fortsetzen-Knopf ist per Tab
  erreichbar und löst mit Enter denselben POST aus.
* Die Karte erzeugt keine JavaScript-Fehler und öffnet keine Dialoge.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port und
isoliertem VIBE-Root. Die API-Antworten werden im Browser abgefangen, damit
die UI unabhängig von der Serverimplementierung geprüft wird; POSTs werden
aufgezeichnet und niemals an den echten Server weitergereicht. Keine echten
Modellaufrufe, keine produktive Installation.
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

AGENT = "vibe-agent"
ABORTED = "ses_ab_4711"
FINISHED = "ses_ok_4711"
FAILED = "ses_bad_4711"
UNKNOWN = "ses_mut_4711"
NOW = 1_700_000_000

FAKE_TMUX = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def entry(session, state, label, agent=AGENT, last=NOW, harness="opencode",
          run_id="lauf-1"):
    return {
        "session": session,
        "project": "/tmp/proj",
        "name": "proj",
        "run_id": run_id,
        "agent": agent,
        "harness": harness,
        "first_seen": last - 600,
        "last_seen": last,
        "state": state,
        "state_label": label,
    }


def payload(sessions, running=False, resume_supported=True, limit=5):
    return {
        "ok": True,
        "running": running,
        "resume_supported": resume_supported,
        "limit": limit,
        "sessions": sessions,
    }


class Ap19SessionsUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP19 Session Management\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key.startswith(
                "SANDBOX"
            ) or key in ("TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "HOME": str(cls.root / "home"),
            "XDG_CONFIG_HOME": str(cls.root / "home" / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(cls.root / "tmux.log"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Fixture ----------

    def setUp(self):
        self.page_errors = []
        self.dialogs = []
        self.get_payload = payload([
            entry(FAILED, "failed", "failed", last=NOW - 30),
            entry(ABORTED, "aborted", "aborted", last=NOW - 20),
            entry(FINISHED, "finished", "completed", last=NOW - 10),
            entry(UNKNOWN, "unknown", "unknown", last=NOW),
        ])
        self.posts = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 900})
        self.page.on(
            "pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)
        self.page.route("**/api/sessions*", self._handle_sessions)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def _handle_sessions(self, route):
        request = route.request
        if request.method == "POST":
            raw = request.post_data or ""
            try:
                self.posts.append(json.loads(raw))
            except ValueError:
                self.posts.append({"raw": raw})
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(
                    {"ok": True, "message": "Fortsetzen gestartet."}))
            return
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(self.get_payload, ensure_ascii=False))

    def tearDown(self):
        self.page.close()

    # ---------- Helfer ----------

    def open_project(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        self.card().wait_for(state="visible", timeout=20000)

    def card(self):
        return self.page.locator("[data-panel='arbeit'] div.card").filter(
            has=self.page.locator("b", has_text=re.compile(r"^Sessions$"))
        ).first

    def row(self, session):
        return self.card().locator(f"[data-session='{session}']").first

    def resume_button(self, session):
        return self.row(session).locator("button").filter(
            has_text=re.compile(r"^Resume$"))

    def visible_resume_buttons(self):
        buttons = self.card().locator("button").filter(
            has_text=re.compile(r"^Resume$"))
        result = []
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if button.is_visible() and button.is_enabled():
                result.append(button)
        return result

    def pill_classes(self, session):
        pill = self.row(session).locator("span.pill").first
        return set((pill.get_attribute("class") or "").split())

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Sessions-Karte erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Sessions-Karte öffnete einen Browserdialog")

    def active_element(self):
        """Text und Session-Zeile des aktuell fokussierten Elements."""
        return self.page.evaluate(
            "() => { const a = document.activeElement; "
            "if (!a) return {text: '', session: null}; "
            "const row = a.closest ? a.closest('[data-session]') : null; "
            "return {text: (a.textContent || '').trim(), "
            "session: row ? row.getAttribute('data-session') : null}; }")

    def tab_to_resume(self, session, max_steps=300):
        """Setzt den Fokus auf den Dokumentanfang und wandert per Tab bis zum
        Fortsetzen-Knopf genau dieser Session."""
        self.page.locator("body").click(position={"x": 2, "y": 2})
        for _ in range(max_steps):
            self.page.keyboard.press("Tab")
            active = self.active_element()
            if active["text"] == "Resume" and active["session"] == session:
                return
        self.fail(
            f"Der Fortsetzen-Knopf für {session} war per Tab nicht erreichbar")


class SessionsCardTest(Ap19SessionsUiTest):
    """AK1/AK2: Übersicht mit Kennung, Zustandslabel, Pille und Zeit."""

    def test_card_lists_sessions_with_state_labels_and_pill_tones(self):
        """Vier Sessions erscheinen mit Kennung, Label und passender Tonklasse."""
        self.open_project()

        for session, label in (
            (FAILED, "failed"),
            (ABORTED, "aborted"),
            (FINISHED, "completed"),
            (UNKNOWN, "unknown"),
        ):
            row = self.row(session)
            self.assertTrue(row.is_visible(),
                            f"Zeile für {session} fehlt")
            text = row.inner_text()
            self.assertIn(session, text, text)
            self.assertIn(label, text,
                          f"Zustandslabel {label!r} fehlt für {session}: {text}")

        self.assertIn("ok", self.pill_classes(FINISHED),
                      "Abgeschlossen muss die Tonklasse ok tragen")
        self.assertIn("warn", self.pill_classes(ABORTED),
                      "Abgebrochen muss die Tonklasse warn tragen")
        self.assertIn("bad", self.pill_classes(FAILED),
                      "Fehlgeschlagen muss die Tonklasse bad tragen")
        self.assertIn("mut", self.pill_classes(UNKNOWN),
                      "Unbekannt muss die Tonklasse mut tragen")
        self.assert_clean_page()

    def test_row_shows_a_human_readable_last_seen_time(self):
        """Die Zeile zeigt die Zeit nicht als rohen Epochenwert."""
        self.open_project()

        text = self.row(ABORTED).inner_text()

        self.assertFalse(
            str(NOW - 20) in text,
            f"Roher last_seen-Wert statt lesbarer Zeit: {text!r}")
        self.assertTrue(
            re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", text)
            or re.search(r"\d{1,2}:\d{2}", text),
            f"Keine lesbare Zeit in der Zeile: {text!r}")
        self.assert_clean_page()

    def test_empty_state_when_no_sessions_were_captured(self):
        """Ohne Sessions erscheint der vereinbarte Leertext."""
        self.get_payload = payload([], limit=5)

        self.open_project()

        card_text = self.card().inner_text()
        self.assertIn("No recorded sessions yet.", card_text, card_text)
        self.assert_clean_page()


class SessionsContinueUiTest(Ap19SessionsUiTest):
    """AK3: Fortsetzen über die Karte – Payload, Sperren, Pi, Tastatur."""

    def test_resume_posts_exactly_name_session_and_action(self):
        """Ein Klick sendet den vereinbarten Payload für genau diese Session."""
        self.open_project()

        button = self.resume_button(ABORTED)
        self.assertGreater(button.count(), 0,
                           "Kein Fortsetzen-Knopf für die abgebrochene Session")
        button.first.click()

        self.wait_until(lambda: bool(self.posts),
                        message="Es wurde kein POST /api/sessions gesendet")
        self.assertEqual(
            {"name": "proj", "session": ABORTED, "action": "continue"},
            self.posts[0],
            f"Der Fortsetzen-POST hat nicht exakt den vereinbarten Payload: "
            f"{self.posts[0]!r}")
        self.assert_clean_page()

    def test_resume_is_not_offered_while_the_run_is_active(self):
        """Bei aktivem Lauf gibt es keinen betätigbaren Fortsetzen-Knopf."""
        self.get_payload = payload(
            [entry(ABORTED, "aborted", "aborted")], running=True)

        self.open_project()

        self.assertEqual(
            [], self.visible_resume_buttons(),
            "Während eines aktiven Laufs darf Fortsetzen nicht angeboten werden")
        self.assert_clean_page()

    def test_pi_shows_no_resume_button_and_explains_no_session(self):
        """Ohne Fortsetzen-Fähigkeit (Pi) erscheint kein Knopf, aber der Grund."""
        self.get_payload = payload(
            [entry(ABORTED, "aborted", "aborted", harness="pi")],
            resume_supported=False)

        self.open_project()

        card_text = self.card().inner_text()
        self.assertIn("Pi", card_text,
                      f"Der Pi-Hinweis fehlt: {card_text!r}")
        self.assertIn("--no-session", card_text,
                      f"Die --no-session-Begründung fehlt: {card_text!r}")
        self.assertEqual(
            [], self.visible_resume_buttons(),
            "Bei Pi darf kein Fortsetzen angeboten werden")
        self.assert_clean_page()

    def test_resume_can_be_operated_by_keyboard(self):
        """Der Knopf ist per Tab erreichbar und sendet mit Enter denselben POST."""
        self.open_project()

        self.tab_to_resume(ABORTED)
        self.page.keyboard.press("Enter")

        self.wait_until(lambda: bool(self.posts),
                        message="Enter auf dem Fortsetzen-Knopf sendete nichts")
        self.assertEqual(
            {"name": "proj", "session": ABORTED, "action": "continue"},
            self.posts[0],
            f"Der per Tastatur ausgelöste POST ist falsch: {self.posts[0]!r}")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
