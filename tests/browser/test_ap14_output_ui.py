"""Browserabnahme AP14: Überarbeitete Ausgabeansicht — Hauptagent immer
sichtbar, laufende Subagenten als eigene Panels, zielgenaue Anweisungen und
Continue.

Startpunkt ist das echte Dashboard (bin/vibe-web.py) auf einem eigenen Port
mit eigenem HOME und isoliertem VIBE-Root, analog
tests/browser/test_f24_output_tabs_ui.py. Der aktive Lauf wird ohne tmux
nachgebildet: Der Laufregistereintrag (``_logs/runs.json``) ist Autorität für
die Laufaktivität; Subagentenzustand und deren erfasste Ausgabe stehen in
``_logs/proj.log.state.json``; ein kleines ``_logs/proj.log`` füttert den
SSE-Stream der Hauptausgabe. Keine produktive Installation, keine echten
Läufe, keine Modellkosten.

Zusätzlich zum Server werden die steuernden POST-Anfragen der Oberfläche
(/api/steer, /api/continue) im Browser abgefangen (Playwright-Route) und mit
einem Erfolg protokolliert — so wird bewiesen, welche Session und welcher
Endpunkt tatsächlich angesprochen wird, ohne einen echten Agentenlauf
zu brauchen.

Testfälle (Vertrag aus dem Arbeitspaket AP14):

a) test_main_agent_panel_is_always_present_even_without_subagents   [AK Hauptpanel]
   Vorbedingung: aktiver Lauf ohne Subagenten; Ausgabe-Tab geöffnet.
   Aktion: Ausgabebereich betrachten.
   Erwartung: Ein „Hauptagent“-Panel ist vorhanden und zeigt die
   Hauptausgabe — auch ohne Subagenten.
   Fehlerfall: Ohne Subagenten fehlt die Hauptagent-Kennzeichnung oder die
   Hauptausgabe.

b) test_running_subagent_appears_and_disappears_after_completion    [AK Subpanels]
   Vorbedingung: aktiver Lauf + erfasster Subagent ses_subA (tester,
   „Untersuche X“, status running) mit erfasster Ausgabe.
   Aktion: Ausgabebereich öffnen; danach Zustandsdatei auf status
   „completed“ (ended gesetzt) ändern und den Poll-Zyklus abwarten.
   Erwartung: Der laufende Subagent erscheint als zusätzliches Panel/Tab
   neben dem Hauptagenten; nach dem Abschluss verschwindet sein Panel aus
   der Agentenauswahl, das Hauptagent-Panel bleibt sichtbar.
   Fehlerfall: Panel fehlt trotz Laufzeit oder bleibt nach dem Abschluss
   in der Agentenauswahl stehen.

c) test_steer_label_names_the_selected_target                       [AK Steuern]
   Vorbedingung: aktiver Lauf + laufender Subagent (tester).
   Aktion: Hauptagent-Panel wählen, dann das Subagent-Panel.
   Erwartung: Die Beschriftung der Anweisungseingabe nennt das Ziel —
   „Anweisung an Hauptagent“ bzw. „Anweisung an tester“ (Agentname).
   Fehlerfall: Die Beschriftung bleibt generisch oder wechselt nicht mit.

d) test_steer_send_posts_the_session_of_the_selected_panel          [AK Steuern]
   Vorbedingung: wie c); /api/steer wird im Browser abgefangen.
   Aktion: Text eingeben und senden, erst mit gewähltem Hauptagent-Panel,
   dann mit gewähltem Subagent-Panel.
   Erwartung: POST /api/steer enthält die Session des gewählten Panels
   (ses_main bzw. ses_subA) und den Text.
   Fehlerfall: Falsche oder fehlende Session im POST.

e) test_continue_button_is_available_when_stopped_and_posts_continue [AK Continue]
   Vorbedingung: gestoppter Lauf (Register finished) + Zustandsdatei mit
   Hauptsession ses_main; /api/continue wird im Browser abgefangen.
   Aktion: Ausgabebereich öffnen, Continue-Knopf anklicken.
   Erwartung: Ein Fortsetzen-Knopf (außerhalb der Protokollkarte, dort gibt
   es den Protokoll-Pause-Knopf) ist sichtbar; der Klick ruft
   POST /api/continue mit dem Projektnamen auf.
   Fehlerfall: Knopf fehlt trotz gestopptem Lauf mit bekannter Session oder
   der Klick sendet nichts.

f) test_continue_button_is_hidden_while_a_run_is_active             [AK Continue]
   Vorbedingung: aktiver Lauf (Register running) mit bekannter Session.
   Aktion: Ausgabebereich öffnen und über mehrere Poll-Zyklen beobachten.
   Erwartung: Es erscheint kein Fortsetzen-Knopf.
   Fehlerfall: Der Knopf wird während des Laufs angeboten.

g) test_pi_steer_is_unavailable_and_never_sends                     [AK Harness]
   Vorbedingung: Harness-Auswahl pi; aktiver Lauf mit Subagent.
   Aktion: Ausgabebereich öffnen, Text eingeben, Senden anklicken;
   /api/steer wird abgefangen.
   Erwartung: Ein Hinweis nennt die --no-session-Begründung; es wird kein
   POST /api/steer gesendet.
   Fehlerfall: Die Oberfläche sendet trotzdem.

h) test_pi_continue_is_unavailable_when_stopped                     [AK Harness]
   Vorbedingung: Harness-Auswahl pi; gestoppter Lauf mit bekannter Session.
   Aktion: Ausgabebereich öffnen; falls ein Fortsetzen-Knopf erreichbar und
   betätigbar ist, anklicken; /api/continue wird abgefangen.
   Erwartung: Der Knopf fehlt oder ist ausgegraut; kein POST /api/continue.
   Fehlerfall: Die Oberfläche bietet Fortsetzen funktionsfähig an.
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

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"
# Der Marker enthält das Wort "Hauptagent" bewusst nicht, damit der Test
# nicht am Ausgabetext vorbeigrünscht; die Hauptagent-Kennzeichnung muss
# als eigenes Panel/Tab der Ansicht erscheinen.
MAIN_MARKER = "HAUPT-4711: Der primäre Agent schreibt sein Protokoll."
MAIN_SESSION = "ses_main"
SUB_SESSION = "ses_subA"
SUB_OUTPUT = "Ausgabe A"
STEER_TEXT = "Bitte zuerst die Borderstellung prüfen"

CONTINUE_BUTTONS_JS = """() => Array.from(document.querySelectorAll('button'))
  .filter(b => /Fortsetzen/.test(b.textContent || '') && !b.closest('.logcard'))
  .map(b => ({text: (b.textContent || '').trim(), disabled: !!b.disabled,
              visible: !!(b.offsetParent || b.getClientRects().length)}))"""

STEER_LABELS_JS = """() => {
  const found = new Set();
  const scope = document.querySelector("[data-panel='ausgabe']") || document;
  for (const node of scope.querySelectorAll('*')) {
    const values = [node.textContent || ''];
    const label = node.getAttribute ? node.getAttribute('aria-label') : null;
    if (label) values.push(label);
    for (const value of values) {
      const match = value.match(/Anweisung an [^\\n]{0,60}/);
      if (match) found.add(match[0].trim());
    }
  }
  return Array.from(found);
}"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Ap14OutputBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Chromium erzeugt beim Herunterfahren noch Dateien im TMPDIR;
        # die Bereinigung toleriert diesen Wettlauf (ignore_errors).
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP14 Ausgabeüberarbeitung\n"
            "  Beschreibung: Test\n",
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True, exist_ok=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_STATE": str(cls.state_dir),
                "HOME": str(cls.root / "home"),
                "TMPDIR": str(cls.root / "tmp"),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
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
            if cls.proc.stdout:
                cls.proc.stdout.close()
            cls.tmp.cleanup()

    # ---------- Seeds und Helfer ----------

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        (self.log_dir / "proj.log.state.json").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.page_errors = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 1000}
        )
        self.page.on("pageerror", lambda e: self.page_errors.append(str(e)))

    def tearDown(self):
        self.page.close()

    def select_pi(self):
        (self.state_dir / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def register_run(self, state="running", agent=AGENT):
        """Aktiver/gestoppter Lauf ohne tmux: Laufregistereintrag mit dem
        echten Werkzeug."""
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.log_dir),
                "--project", str(self.project),
                "--name", "proj", "--key", "proj", "--agent", agent,
                "--state", state,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def write_log(self):
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + MAIN_MARKER + "\n",
            encoding="utf-8",
        )

    def write_state(self, session=MAIN_SESSION, subs=None):
        payload = {"session": session, "subagents": subs or []}
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def running_sub(self, session=SUB_SESSION, agent="tester",
                    description="Untersuche X", output=SUB_OUTPUT):
        return {
            "session": session,
            "agent": agent,
            "description": description,
            "prompt": description + " gründlich",
            "status": "running",
            "started": int(time.time()),
            "ended": 0,
            "output": output,
        }

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def wait_absent(self, probe, timeout=8, message="Bedingung bleibt erfüllt"):
        """True, solange ``probe`` über den Zeitraum hinweg falsch bleibt."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if probe():
                self.fail(message)
            # wait_for_timeout verarbeitet while wartend die Seitenereignisse;
            # reine Python-Sleeps würden abgefangene POSTs unbeobachtet lassen.
            self.page.wait_for_timeout(250)
        return True

    def panel(self):
        return self.page.locator("[data-panel='ausgabe']")

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=15000)
        row.click()
        self.wait_until(
            lambda: self.page.locator("#runstate").inner_text().strip()
            in ("läuft", "gestoppt"),
            message="Projektdetail zeigte keinen Laufstatus",
        )

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Projektbereiche'] button[role=tab]"
        )
        out_tab = tabs.filter(has_text="Ausgabe").first
        out_tab.click()
        self.panel().wait_for(state="visible", timeout=10000)

    def output_tablist(self):
        return self.panel().locator("[role='tablist']")

    def output_tabs(self):
        return self.output_tablist().locator("[role='tab']")

    def log_card(self):
        return self.panel().locator(".logcard")

    def select_tab(self, label):
        tab = self.output_tabs().filter(has_text=label).first
        self.assertGreater(
            tab.count(), 0, f"Tab/Panel {label!r} nicht gefunden"
        )
        tab.click()
        self.wait_until(
            lambda: tab.get_attribute("aria-selected") == "true",
            message=f"Tab {label!r} wurde nicht ausgewählt",
            timeout=10,
        )

    def continue_buttons(self):
        """Fortsetzen-Knöpfe außerhalb der Protokollkarte (dort liegt der
        Protokoll-Pause-Knopf mit wechselnder Beschriftung)."""
        return self.page.evaluate(CONTINUE_BUTTONS_JS)

    def steer_labels(self):
        return self.page.evaluate(STEER_LABELS_JS)

    def steer_textarea(self):
        return self.panel().locator("textarea").first

    def steer_send_button(self):
        button = self.panel().locator("button").filter(
            has_text=re.compile(r"send", re.I)
        ).first
        self.assertGreater(
            button.count(), 0,
            "Kein Senden-Knopf für die Anweisungseingabe gefunden",
        )
        return button

    def intercept(self, endpoint):
        """Fängt POST-Anfragen an ``endpoint`` ab und protokolliert sie."""
        records = []

        def handler(route):
            request = route.request
            records.append(
                {"url": request.url, "post": request.post_data or ""}
            )
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "message": "ok"}),
            )

        self.page.route("**" + endpoint, handler)
        return records

    def post_request(self, endpoint, action):
        """Löst ``action`` aus und wartet synchron auf den POST an ``endpoint``.

        ``expect_request`` verarbeitet dabei die Seitenereignisse; die Abfang-
        Route (``intercept``) sorgt weiterhin dafür, dass die Anfrage den
        Server nicht erreicht, sondern mit einem Erfolg beantwortet wird.
        """
        with self.page.expect_request("**" + endpoint, timeout=15000) as ri:
            action()
        return ri.value

    def click_continue_button(self):
        clicked = self.page.evaluate(
            """() => {
              const button = Array.from(document.querySelectorAll('button'))
                .find(b => /Fortsetzen/.test(b.textContent || '')
                     && !b.closest('.logcard'));
              if (!button) return false;
              button.click();
              return true;
            }"""
        )
        self.assertTrue(clicked, "Kein Fortsetzen-Knopf zum Anklicken gefunden")


class MainPanelTest(Ap14OutputBrowserTest):
    def test_main_agent_panel_is_always_present_even_without_subagents(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state([])
        self.open_detail()
        self.open_output()

        self.wait_until(
            lambda: "Hauptagent" in self.panel().inner_text(timeout=2000)
            and MAIN_MARKER in self.panel().inner_text(timeout=2000),
            message="Ohne Subagenten fehlt das immer vorhandene "
                    "Hauptagent-Panel samt Hauptausgabe",
            timeout=15,
        )
        self.assertEqual(
            [str(e) for e in self.page_errors], [],
            "Die Ausgabeansicht erzeugte JavaScript-Fehler",
        )


class SubagentPanelsTest(Ap14OutputBrowserTest):
    def test_running_subagent_appears_and_disappears_after_completion(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state(subs=[self.running_sub()])
        self.open_detail()
        self.open_output()
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() >= 2,
            message="Laufender Subagent erscheint nicht als zusätzliches "
                    "Panel/Tab (Anzahl: " + str(tabs.count()) + ")",
        )
        labels = [tabs.nth(i).inner_text() for i in range(tabs.count())]
        self.assertTrue(
            any("Hauptagent" in label for label in labels),
            "Hauptagent-Panel fehlt neben dem Subagenten: " + repr(labels),
        )
        self.assertTrue(
            any("Untersuche X" in label or "tester" in label
                for label in labels),
            "Subagent-Panel fehlt: " + repr(labels),
        )

        done = self.running_sub()
        done["status"] = "completed"
        done["ended"] = int(time.time()) + 1
        self.write_state(subs=[done])
        self.wait_until(
            lambda: not tabs.filter(has_text="Untersuche X").count()
            or not self.output_tablist().first.is_visible(),
            message="Das Panel des beendeten Subagenten blieb in der "
                    "Agentenauswahl stehen",
            timeout=15,
        )
        self.assertTrue(
            "Hauptagent" in self.panel().inner_text(timeout=2000)
            and MAIN_MARKER in self.panel().inner_text(timeout=2000),
            "Nach dem Subagenten-Ende fehlt das Hauptagent-Panel",
        )
        card_text = self.log_card().inner_text()
        self.assertNotIn(
            "Untersuche X", card_text,
            "Der beendete Subagent bleibt in der Ausgabekarte sichtbar",
        )


class SteerTargetTest(Ap14OutputBrowserTest):
    def seed(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state(subs=[self.running_sub()])
        self.open_detail()
        self.open_output()
        tabs = self.output_tabs()
        self.wait_until(
            lambda: tabs.count() >= 2,
            message="Vorbedingung: Subagent-Panel fehlt",
        )

    def test_steer_label_names_the_selected_target(self):
        self.seed()
        self.select_tab("Hauptagent")
        self.wait_until(
            lambda: any(
                label.startswith("Anweisung an Hauptagent")
                for label in self.steer_labels()
            ),
            message="Beschriftung nennt bei gewähltem Hauptagent nicht "
                    "'Anweisung an Hauptagent': "
                    + repr(self.steer_labels()),
        )
        self.select_tab("Untersuche X")
        self.wait_until(
            lambda: any(
                "Anweisung an tester" in label
                for label in self.steer_labels()
            ),
            message="Beschriftung nennt bei gewähltem Subagent nicht "
                    "'Anweisung an tester': " + repr(self.steer_labels()),
        )

    def test_steer_send_posts_the_session_of_the_selected_panel(self):
        self.seed()
        self.intercept("/api/steer")
        self.select_tab("Hauptagent")
        self.steer_textarea().fill(STEER_TEXT)
        request = self.post_request("/api/steer", self.steer_send_button().click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(
            "proj", payload.get("name"),
            "POST /api/steer nennt das Projekt nicht: " + repr(payload),
        )
        self.assertEqual(
            MAIN_SESSION, payload.get("session"),
            "Bei gewähltem Hauptagent-Panel wird nicht dessen Session "
            "gesendet: " + repr(payload),
        )
        self.assertEqual(
            STEER_TEXT, payload.get("text"),
            "Der Text fehlt im POST: " + repr(payload),
        )

        self.select_tab("Untersuche X")
        self.steer_textarea().fill(STEER_TEXT)
        request = self.post_request("/api/steer", self.steer_send_button().click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(
            SUB_SESSION, payload.get("session"),
            "Bei gewähltem Subagent-Panel wird nicht dessen Session "
            "gesendet: " + repr(payload),
        )
        self.assertEqual(
            [str(e) for e in self.page_errors], [],
            "Das Senden erzeugte JavaScript-Fehler",
        )


class ContinueButtonTest(Ap14OutputBrowserTest):
    def test_continue_button_is_available_when_stopped_and_posts_continue(self):
        self.register_run(state="finished", agent=AGENT)
        self.write_log()
        self.write_state(session=MAIN_SESSION, subs=[])
        self.open_detail()
        self.open_output()
        records = self.intercept("/api/continue")

        self.wait_until(
            lambda: any(
                button["visible"] and not button["disabled"]
                for button in self.continue_buttons()
            ),
            message="Bei gestopptem Lauf mit bekannter Session fehlt ein "
                    "betätigbarer Fortsetzen-Knopf: "
                    + repr(self.continue_buttons()),
            timeout=15,
        )
        request = self.post_request("/api/continue", self.click_continue_button)
        self.assertTrue(
            request.url.endswith("/api/continue"),
            "Es wurde nicht /api/continue aufgerufen: " + request.url,
        )
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(
            "proj", payload.get("name"),
            "POST /api/continue nennt das Projekt nicht: " + repr(payload),
        )

    def test_continue_button_is_hidden_while_a_run_is_active(self):
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state(session=MAIN_SESSION, subs=[])
        self.open_detail()
        self.open_output()
        self.wait_absent(
            lambda: any(button["visible"] for button in self.continue_buttons()),
            timeout=8,
            message="Während eines aktiven Laufs wird ein Fortsetzen-Knopf "
                    "angeboten",
        )


class PiAvailabilityTest(Ap14OutputBrowserTest):
    def test_pi_steer_is_unavailable_and_never_sends(self):
        self.select_pi()
        self.register_run(state="running", agent=AGENT)
        self.write_log()
        self.write_state(subs=[self.running_sub()])
        self.open_detail()
        self.open_output()
        records = self.intercept("/api/steer")
        self.wait_until(
            lambda: "--no-session" in self.panel().inner_text(timeout=2000),
            message="Bei Pi fehlt der Hinweis auf die --no-session-Begründung",
            timeout=15,
        )
        self.steer_textarea().fill(STEER_TEXT)
        self.steer_send_button().click()
        self.wait_absent(
            lambda: len(records) > 0,
            timeout=6,
            message="Bei Pi wurde trotzdem POST /api/steer gesendet: "
                    + repr(records),
        )
        self.assertEqual(
            [str(e) for e in self.page_errors], [],
            "Die Pi-Ansicht erzeugte JavaScript-Fehler",
        )

    def test_pi_continue_is_unavailable_when_stopped(self):
        self.select_pi()
        self.register_run(state="finished", agent=AGENT)
        self.write_log()
        self.write_state(session=MAIN_SESSION, subs=[])
        self.open_detail()
        self.open_output()
        records = self.intercept("/api/continue")

        def clickable_continue():
            return any(
                button["visible"] and not button["disabled"]
                for button in self.continue_buttons()
            )

        if clickable_continue():
            self.click_continue_button()
        self.wait_absent(
            lambda: len(records) > 0,
            timeout=6,
            message="Bei Pi wurde trotzdem POST /api/continue gesendet: "
                    + repr(records),
        )


if __name__ == "__main__":
    unittest.main()
