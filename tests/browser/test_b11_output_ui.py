"""Browserabnahme B11 (Teil 2): vollständig neu gebaute Ausgabeansicht.

Arbeitspaket B11 („throw away the ui of the ausgabe view. redo ap 14. you are
not allowed to recycle any previous work“) verlangt eine Ansicht, in der die
Arbeit **aller** laufenden Agenten gleichzeitig sichtbar ist. Die bisherigen
Bausteine der F19/F24/AP14-Ansicht (nur-aktiver-Tab-Mechanik, ``steerCard``,
``subagentCard``, alter Syntax-Highlighter des Views) dürfen nicht
weiterverwendet werden.

Verbindlicher UI-Vertrag dieser Abnahme (bewusst schlank, damit die Umsetzung
frei bleibt):

* Der Ausgabebereich liegt weiterhin im Projektdetail-Panel
  ``[data-panel='ausgabe']`` (Projektbereiche-Tab „Ausgabe“).
* Jede sichtbare Agentenansicht ist ein Element mit ``data-agent-view``,
  ``data-role`` (``main`` oder ``subagent``) und ``data-session`` (Session-ID).
  Sie ist eine Live-Region (``role='log'`` oder ``aria-live``) und zeigt ihre
  eigene Ausgabe sichtbar an. Der Hauptagent (``data-role='main'``) ist immer
  vorhanden.
* Laufende Subagenten erscheinen **gleichzeitig** als eigene Ansichten, ohne
  Tabwechsel. Beendete Subagenten verschwinden aus der Ansicht.
* Zielauswahl für Anweisungen: ein natives ``select`` mit
  ``aria-label='Ziel'``; jede Option trägt die Session-ID als ``value``
  (Hauptsession und jeder laufende Subagent). Dazu ein ``textarea`` mit
  ``aria-label``, das „Zusatzanweisung“ enthält, und ein Knopf mit dem
  zugänglichen Namen „…senden“. Der POST an ``/api/steer`` enthält die
  gewählte Session.
* ``POST /api/continue`` wird über einen Knopf „Fortsetzen“ ausgelöst; er
  erscheint nur bei gestopptem Lauf und verschwindet während eines Laufs.
* Die Ansicht nutzt die verfügbare Höhe (kein kleiner Briefkasten), öffnet
  keine Modale und ist per Maus und Tastatur bedienbar.
* Die alten IDs/Klassen der F19/F24/AP14-Ansicht (u. a. ``steer-card``,
  ``subagents-card``, ``agent-active``, ``log``, ``logcard``, ``outtabs``,
  ``output-layout``, ``outpane``) sind im Ausgabebereich nicht mehr vorhanden.

Testfälle:

1. test_main_and_two_running_subagents_are_visible_at_the_same_time [AK1]
   Vorbedingung: aktiver Lauf; Zustandsdatei mit zwei laufenden Subagenten A
   und B samt Ausgabe; Hauptlog mit Marker.
   Aktion: Ausgabebereich öffnen; danach Ausgabe von A und Hauptlog live
   verlängern.
   Erwartung: Hauptagent, A und B sind ohne Klick gleichzeitig sichtbar;
   Live-Verlängerungen erscheinen ohne Panelwechsel.
   Fehlerfall: Nur ein Agent sichtbar, Tabwechsel nötig oder Ausgabe
   aktualisiert sich nicht.
2. test_finished_subagent_leaves_the_view_and_main_stays           [AK2]
   Vorbedingung: wie 1.
   Aktion: Subagent A auf ``completed`` setzen.
   Erwartung: A verschwindet, Hauptagent und B bleiben sichtbar.
   Fehlerfall: A bleibt stehen oder Haupt/B verschwinden mit.
3. test_steer_target_selection_posts_the_chosen_session            [AK3]
   Vorbedingung: wie 1; /api/steer im Browser abgefangen.
   Aktion: Ziel Hauptagent wählen, Text senden; dann Ziel A wählen, senden.
   Erwartung: POST nennt Projekt, Text und exakt die gewählte Session.
   Fehlerfall: Falsche/fehlende Session oder kein POST.
4. test_steer_can_be_operated_by_keyboard                          [AK1/AK5]
   Vorbedingung: wie 1.
   Aktion: Zielauswahl per Pfeiltaste ändern; Text tippen; Senden-Knopf
   fokussieren und mit Enter auslösen.
   Erwartung: POST mit der per Tastatur gewählten Session; jede
   Agentenansicht ist eine Live-Region.
   Fehlerfall: Tastatur ändert nichts, Enter sendet nicht oder Ansichten sind
   keine Live-Region.
5. test_continue_button_is_shown_when_stopped_and_posts_continue   [AK4]
   Vorbedingung: Lauf gestoppt (Register finished), Hauptsession erfasst.
   Aktion: Ausgabe öffnen, „Fortsetzen“ anklicken.
   Erwartung: POST /api/continue mit Projektname.
   Fehlerfall: Knopf fehlt oder sendet nichts.
6. test_continue_button_is_hidden_while_a_run_is_active            [AK4]
   Vorbedingung: aktiver Lauf.
   Aktion: Ausgabe öffnen und mehrere Poll-Zyklen beobachten.
   Erwartung: Kein sichtbarer „Fortsetzen“-Knopf.
   Fehlerfall: Fortsetzen wird während des Laufs angeboten.
7. test_output_view_uses_the_available_height                      [AK5]
   Vorbedingung: aktiver Lauf mit zwei Subagenten; Viewport 1400×900.
   Aktion: Ausgabe öffnen.
   Erwartung: Ausgabepanel mindestens 65 % und Hauptansicht mindestens 40 %
   der Viewporthöhe; Hauptansicht endet sichtbar im Viewport.
   Fehlerfall: Kleine Teilansicht oder Überlauf unterhalb des Viewports.
8. test_old_output_view_building_blocks_are_removed                [AK5]
   Vorbedingung: aktiver Lauf.
   Aktion: Ausgabe öffnen.
   Erwartung: Alte IDs/Klassen und die Agenten-Tabliste fehlen; kein Modal.
   Fehlerfall: Alte Bausteine wurden recycelt.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port und
isoliertem VIBE-Root. Lauf und Subagenten werden über das echte Laufregister
und die Zustandsdatei nachgebildet; steuernde POSTs fängt Playwright ab.
Keine echten Modellaufrufe, keine produktive Installation.
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
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"
MAIN_SESSION = "ses_main_b11"
CHILD_A = "ses_kind_a"
CHILD_B = "ses_kind_b"
MAIN_MARKER = "HAUPT-B11-4711: Hauptagent schreibt sein Protokoll."
MAIN_LIVE = "HAUPT-LIVE-4711: neue Hauptzeile."
OUTPUT_A = "AUSGABE-A-4711: Subagent A arbeitet."
OUTPUT_A_LIVE = "A-LIVE-4711: A hat weitergeschrieben."
OUTPUT_B = "AUSGABE-B-4711: Subagent B arbeitet."
STEER_TEXT = "Bitte die vollständige Ausgabe zeigen"

OLD_IDS = (
    "steer-card", "subagents-card", "agent-active", "log", "continue-bar",
    "continue-btn", "steer-text", "steer-target", "steer-send",
    "f19-controls", "subagent-list", "subagent-count",
)
OLD_CLASSES = (
    "logcard", "outtabs", "agenttabs", "output-layout", "output-side",
    "outpane", "subagents", "subagent",
)

OLD_BLOCKS_JS = """() => {
  const scope = document.querySelector("[data-panel='ausgabe']") || document;
  const ids = %s.filter(id => scope.querySelector('#' + id));
  const classes = %s.filter(name => scope.querySelector('.' + name));
  const agentTabs = scope.querySelectorAll(
    "[role='tablist'][aria-label='Aktive Agenten']").length
    + scope.querySelectorAll("[role='tablist']").length;
  const dialogs = scope.querySelectorAll(
    "[role='dialog'], dialog[open]").length;
  return {ids, classes, agentTabs, dialogs};
}""" % (json.dumps(list(OLD_IDS)), json.dumps(list(OLD_CLASSES)))

LIVE_REGION_JS = """() => Array.from(document.querySelectorAll('[data-agent-view]'))
  .map(node => ({session: node.getAttribute('data-session'),
                 role: node.getAttribute('data-role'),
                 log: node.getAttribute('role'),
                 live: node.getAttribute('aria-live')}))"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class B11OutputBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] B11 Ausgabeansicht\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        cls.oc_port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
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

    # ---------- Seeds und Helfer ----------

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        (self.log_dir / "proj.log.state.json").unlink(missing_ok=True)
        (self.log_dir / "proj.log").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.page_errors = []
        self.dialogs = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 900})
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def tearDown(self):
        self.page.close()

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", AGENT,
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(markers) + "\n",
            encoding="utf-8")

    def append_log(self, marker):
        with open(self.log_dir / "proj.log", "a", encoding="utf-8") as handle:
            handle.write(marker + "\n")

    def sub(self, session, agent, description, output, status="running"):
        started = int(time.time()) + 5
        return {
            "session": session,
            "agent": agent,
            "description": description,
            "prompt": "Auftrag für " + agent,
            "status": status,
            "started": started,
            "ended": int(time.time()) + 180 if status != "running" else 0,
            "output": output,
        }

    def write_state(self, subs, main_session=MAIN_SESSION):
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": main_session, "subagents": subs},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def wait_absent(self, probe, timeout=8, message="Bedingung bleibt erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if probe():
                self.fail(message)
            self.page.wait_for_timeout(250)
        return True

    def panel(self):
        return self.page.locator("[data-panel='ausgabe']")

    def agent_view(self, role=None, session=None):
        selector = "[data-agent-view]"
        if role:
            selector += f"[data-role='{role}']"
        if session:
            selector += f"[data-session='{session}']"
        return self.panel().locator(selector)

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        tabs = self.page.locator(
            "[aria-label='Projektbereiche'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Projektbereiche'] button[role=tab]")
        out_tab = tabs.filter(has_text="Ausgabe").first
        out_tab.click()
        self.panel().wait_for(state="visible", timeout=15000)

    def wait_for_view(self, role, session, marker, timeout=20):
        view = self.agent_view(role=role, session=session)
        self.wait_until(
            lambda: view.count() == 1 and view.first.is_visible()
            and marker in view.first.inner_text(),
            timeout=timeout,
            message=f"Agentenansicht {role}/{session} mit {marker!r} fehlt")
        return view.first

    def target_select(self):
        select = self.panel().locator("select[aria-label='Ziel']")
        self.assertGreater(
            select.count(), 0,
            "Keine Zielauswahl (select[aria-label='Ziel']) gefunden")
        return select.first

    def target_sessions(self):
        return self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] select[aria-label='Ziel'] option",
            "options => options.map(option => option.value)")

    def steer_textarea(self):
        area = self.panel().locator("textarea[aria-label*='Zusatzanweisung']")
        self.assertGreater(
            area.count(), 0,
            "Keine Anweisungseingabe (textarea mit aria-label "
            "'Zusatzanweisung') gefunden")
        return area.first

    def steer_send_button(self):
        button = self.panel().locator("button").filter(
            has_text=re.compile("senden", re.I)).first
        self.assertGreater(
            button.count(), 0, "Kein Senden-Knopf gefunden")
        return button

    def continue_button(self):
        return self.panel().locator("button").filter(
            has_text=re.compile(r"^Fortsetzen$")).first

    def intercept(self, endpoint):
        records = []

        def handler(route):
            request = route.request
            records.append({"url": request.url,
                            "post": request.post_data or ""})
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "message": "ok"}))

        self.page.route("**" + endpoint, handler)
        return records

    def post_request(self, endpoint, action):
        with self.page.expect_request("**" + endpoint, timeout=15000) as info:
            action()
        return info.value

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")


class SimultaneousAgentsTest(B11OutputBrowserTest):
    def test_main_and_two_running_subagents_are_visible_at_the_same_time(self):
        """AK1: Hauptagent und zwei laufende Subagenten gleichzeitig sichtbar.

        Vorbedingung: aktiver Lauf, Hauptlog-Marker, zwei laufende Subagenten
        A und B mit eigener Ausgabe.
        Aktion: Ausgabe öffnen; danach A-Ausgabe und Hauptlog live verlängern.
        Erwartung: Alle drei Ansichten sind gleichzeitig sichtbar; die
        Live-Verlängerungen erscheinen ohne Panelwechsel.
        Fehlerfall: Nur ein Agent sichtbar, Tabwechsel nötig oder keine
        Aktualisierung.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])
        self.open_detail()
        self.open_output()

        main_view = self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
        view_a = self.wait_for_view("subagent", CHILD_A, OUTPUT_A)
        view_b = self.wait_for_view("subagent", CHILD_B, OUTPUT_B)

        self.assertTrue(main_view.is_visible(), "Hauptagent ist nicht sichtbar")
        self.assertTrue(view_a.is_visible(), "Subagent A ist nicht sichtbar")
        self.assertTrue(view_b.is_visible(), "Subagent B ist nicht sichtbar")

        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A + "\n" + OUTPUT_A_LIVE),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])
        self.append_log(MAIN_LIVE)

        self.wait_until(
            lambda: OUTPUT_A_LIVE in view_a.inner_text()
            and MAIN_LIVE in main_view.inner_text(),
            timeout=20,
            message="Live-Verlängerung erschien nicht ohne Panelwechsel")
        self.assertTrue(view_b.is_visible(),
                        "Subagent B verschwand während der Aktualisierung")
        self.assert_clean_page()

    def test_finished_subagent_leaves_the_view_and_main_stays(self):
        """AK2: abgeschlossener Subagent fällt aus der Ansicht.

        Vorbedingung: Hauptagent und laufende Subagenten A und B sichtbar.
        Aktion: A auf completed setzen.
        Erwartung: Ansicht A verschwindet; Hauptagent und B bleiben sichtbar.
        Fehlerfall: A bleibt stehen oder Haupt/B verschwinden mit.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
        self.wait_for_view("subagent", CHILD_A, OUTPUT_A)
        self.wait_for_view("subagent", CHILD_B, OUTPUT_B)

        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A,
                     status="completed"),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])

        self.wait_until(
            lambda: self.agent_view(session=CHILD_A).count() == 0
            or not self.agent_view(session=CHILD_A).first.is_visible(),
            timeout=20,
            message="Der abgeschlossene Subagent A blieb in der Ansicht")
        self.assertTrue(self.agent_view(session=CHILD_B).first.is_visible(),
                        "Subagent B verschwand mit A")
        self.assertTrue(
            self.agent_view(role="main").first.is_visible(),
            "Der Hauptagent verschwand mit dem Subagenten")
        self.assert_clean_page()


class SteerTargetTest(B11OutputBrowserTest):
    def seed(self):
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
        self.wait_for_view("subagent", CHILD_A, OUTPUT_A)
        self.wait_for_view("subagent", CHILD_B, OUTPUT_B)
        self.wait_until(
            lambda: {MAIN_SESSION, CHILD_A, CHILD_B}
            <= set(self.target_sessions()),
            timeout=20,
            message="Zielauswahl enthält nicht alle laufenden Agenten: "
                    + repr(self.target_sessions()))

    def test_steer_target_selection_posts_the_chosen_session(self):
        """AK3: Anweisung geht an die gewählte Session.

        Vorbedingung: Hauptagent und zwei laufende Subagenten sichtbar;
        /api/steer abgefangen.
        Aktion: Ziel Hauptagent + Senden; danach Ziel A + Senden.
        Erwartung: POST nennt Projekt, Text und exakt ses_main_b11 bzw.
        ses_kind_a.
        Fehlerfall: Falsche oder fehlende Session, kein POST.
        """
        self.seed()
        records = self.intercept("/api/steer")
        select = self.target_select()
        textarea = self.steer_textarea()
        send = self.steer_send_button()

        select.select_option(MAIN_SESSION)
        textarea.fill(STEER_TEXT)
        request = self.post_request("/api/steer", send.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual("proj", payload.get("name"), payload)
        self.assertEqual(MAIN_SESSION, payload.get("session"), payload)
        self.assertEqual(STEER_TEXT, payload.get("text"), payload)

        select.select_option(CHILD_A)
        textarea.fill(STEER_TEXT)
        request = self.post_request("/api/steer", send.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(CHILD_A, payload.get("session"),
                         "Anweisung ging nicht an den gewählten Subagenten: "
                         + repr(payload))
        self.assertEqual(STEER_TEXT, payload.get("text"), payload)
        self.assert_clean_page()

    def test_steer_can_be_operated_by_keyboard(self):
        """AK1/AK5: Tastaturbedienung von Zielauswahl und Senden.

        Vorbedingung: wie oben.
        Aktion: Zielauswahl fokussieren und mit Pfeiltaste ändern; Text
        tippen; Senden-Knopf fokussieren und mit Enter auslösen.
        Erwartung: POST mit der per Tastatur gewählten Session; jede
        Agentenansicht ist eine Live-Region.
        Fehlerfall: Pfeiltaste ändert nichts, Enter sendet nicht oder
        Ansichten sind keine Live-Regionen.
        """
        self.seed()
        self.intercept("/api/steer")
        select = self.target_select()
        before = select.input_value()
        select.focus()
        self.page.keyboard.press("ArrowDown")
        after = select.input_value()
        self.assertNotEqual(
            before, after,
            "Die Zielauswahl ließ sich nicht per Pfeiltaste ändern")
        self.assertIn(after, {MAIN_SESSION, CHILD_A, CHILD_B},
                      "Unerwartetes Tastaturziel: " + after)

        textarea = self.steer_textarea()
        textarea.focus()
        self.page.keyboard.type(STEER_TEXT)
        send = self.steer_send_button()
        request = self.post_request(
            "/api/steer",
            lambda: (send.focus(), self.page.keyboard.press("Enter")))
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(after, payload.get("session"),
                         "Enter sendete nicht an das gewählte Ziel: " + repr(payload))
        self.assertEqual(STEER_TEXT, payload.get("text"), payload)

        regions = self.page.evaluate(LIVE_REGION_JS)
        self.assertGreaterEqual(len(regions), 3,
                                "Nicht alle Agentenansichten sind vorhanden: "
                                + repr(regions))
        for region in regions:
            self.assertTrue(
                region.get("log") == "log"
                or region.get("live") in ("polite", "assertive"),
                "Agentenansicht ist keine Live-Region: " + repr(region))
        self.assert_clean_page()


class ContinueTest(B11OutputBrowserTest):
    def test_continue_button_is_shown_when_stopped_and_posts_continue(self):
        """AK4: gestoppter Lauf bietet Fortsetzen und ruft /api/continue.

        Vorbedingung: Register finished, Hauptsession erfasst.
        Aktion: Ausgabe öffnen, „Fortsetzen“ anklicken.
        Erwartung: POST /api/continue mit Projektname.
        Fehlerfall: Knopf fehlt oder der Klick sendet nichts.
        """
        self.register_run("finished")
        self.write_log(MAIN_MARKER)
        self.write_state([])
        self.open_detail()
        self.open_output()

        button = self.continue_button()
        self.wait_until(
            lambda: button.count() > 0 and button.first.is_visible(),
            message="Bei gestopptem Lauf fehlt der Fortsetzen-Knopf")
        records = self.intercept("/api/continue")
        request = self.post_request("/api/continue", button.first.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual("proj", payload.get("name"), payload)
        self.assertEqual(1, len(records), records)
        self.assert_clean_page()

    def test_continue_button_is_hidden_while_a_run_is_active(self):
        """AK4: während eines Laufs kein Fortsetzen-Knopf.

        Vorbedingung: Register running, Hauptsession erfasst.
        Aktion: Ausgabe öffnen und mehrere Poll-Zyklen beobachten.
        Erwartung: Kein sichtbarer Fortsetzen-Knopf.
        Fehlerfall: Fortsetzen wird während des Laufs angeboten.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)

        self.wait_absent(
            lambda: self.continue_button().count() > 0
            and self.continue_button().first.is_visible(),
            timeout=8,
            message="Während eines aktiven Laufs wird Fortsetzen angeboten")
        self.assert_clean_page()


class LayoutAndRebuildTest(B11OutputBrowserTest):
    def test_output_view_uses_the_available_height(self):
        """AK5: Ansicht nutzt die verfügbare Höhe.

        Vorbedingung: aktiver Lauf mit zwei laufenden Subagenten; Viewport
        1400×900.
        Aktion: Ausgabe öffnen.
        Erwartung: Ausgabepanel ≥ 65 % Viewporthöhe, Hauptansicht ≥ 40 %;
        Hauptansicht endet im sichtbaren Bereich.
        Fehlerfall: Kleine Teilansicht oder Überlauf unterhalb des Viewports.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
        self.wait_for_view("subagent", CHILD_A, OUTPUT_A)
        self.wait_for_view("subagent", CHILD_B, OUTPUT_B)

        viewport = self.page.viewport_size
        panel_box = self.panel().bounding_box()
        main_box = self.agent_view(role="main").first.bounding_box()
        self.assertIsNotNone(panel_box, "Ausgabepanel hat keine Ausdehnung")
        self.assertIsNotNone(main_box, "Hauptansicht hat keine Ausdehnung")
        self.assertGreaterEqual(
            panel_box["height"], viewport["height"] * 0.65,
            f"Ausgabepanel ist nur {panel_box['height']:.0f}px hoch")
        self.assertGreaterEqual(
            main_box["height"], viewport["height"] * 0.40,
            f"Hauptansicht ist nur {main_box['height']:.0f}px hoch")
        self.assertLessEqual(
            main_box["y"] + main_box["height"], viewport["height"] + 2,
            "Hauptansicht ragt unterhalb des sichtbaren Bereichs")
        self.assert_clean_page()

    def test_old_output_view_building_blocks_are_removed(self):
        """AK5: alte F19/F24/AP14-Bausteine sind entfernt.

        Vorbedingung: aktiver Lauf.
        Aktion: Ausgabe öffnen.
        Erwartung: Keine alten IDs/Klassen, keine Agenten-Tabliste und kein
        Modal im Ausgabebereich.
        Fehlerfall: Alte Bausteine wurden recycelt.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state([self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A)])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)

        found = self.page.evaluate(OLD_BLOCKS_JS)
        self.assertEqual([], found["ids"],
                         "Alte IDs der Ausgabeansicht sind noch vorhanden: "
                         + repr(found["ids"]))
        self.assertEqual([], found["classes"],
                         "Alte Klassen der Ausgabeansicht sind noch vorhanden: "
                         + repr(found["classes"]))
        self.assertEqual(0, found["agentTabs"],
                         "Im Ausgabebereich existiert noch eine Agenten-Tabliste")
        self.assertEqual(0, found["dialogs"],
                         "Die Ausgabeansicht öffnete ein Modal")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
