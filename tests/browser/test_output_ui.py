"""Ausgabe-Oberfläche: Panel, Fokus, Steuerung, Fortsetzen, Syntaxhervorhebung und Subagenten.

Aufruf: python3 -m unittest tests.browser.test_output_ui -v
"""


# ===========================================================================
# Browserabnahme: Syntaxhervorhebung in der Agentenausgabe
# ===========================================================================

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
MAIN_SESSION = "ses_ap16_main"
CHILD_A = "ses_ap16_sub_a"

# Marker ohne Ziffern, Hexwörter, Anführungszeichen oder Dateiendungen,
# damit die schlichte Zeile nach keinem bekannten Hervorhebungsmerkmal
# anspringt und als Vergleichsbasis farbrein bleibt.
MAIN_PLAIN = "SCHLICHTE_ZEILE_OHNE_HERVORHEBUNG bleibt normal"
MAIN_HEAD = "=== PROTOKOLLKOPF_APX ==="
MAIN_ERR = "[Fehler] FEHLERZEILE_ROT: Hier ist etwas schiefgegangen"
MAIN_PATH = "Pfadangabe bin/web/app.js im Protokoll"
MAIN_MARKUP = "<script>window.__ap16pwn=1</script> und <b>nicht wirklich fett</b>"
LIVE_ERR = "[Fehler] LIVEFEHLER_ROT: frisch angehaengte Fehlerzeile"
SUB_PLAIN = "SCHLICHTE_SUBZEILE bleibt normal"
SUB_ERR = "[Fehler] SUBFEHLER_ROT: Ausgabe des Subagenten ist markiert"
SUB_MARKUP = "<script>window.__ap16pwn=99</script>"
STEER_TEXT = "AP16 Hinweis: bitte weiter mit der Rotphase"

COLORS_JS = """(selector) => {
  const area = document.querySelector(selector);
  if (!area) return null;
  const walker = document.createTreeWalker(area, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const text = node.textContent || '';
    if (!text.trim()) continue;
    nodes.push({text: text, color: getComputedStyle(node.parentElement).color});
  }
  return nodes;
}"""

MARKUP_PROBE_JS = """(selector) => {
  const area = document.querySelector(selector);
  if (!area) return {scripts: 0, bold: 0};
  return {
    scripts: area.querySelectorAll('script').length,
    bold: Array.from(area.querySelectorAll('b, strong'))
      .filter(node => (node.textContent || '').includes('nicht wirklich fett'))
      .length,
  };
}"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AP16OutputBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP16 Ausgabe hervorheben\n"
            "  Beschreibung: Test\n", encoding="utf-8")
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

    def write_log(self, *lines):
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(lines) + "\n",
            encoding="utf-8")

    def append_log(self, line):
        with open(self.log_dir / "proj.log", "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

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
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        tabs = self.page.locator(
            "[aria-label='Project sections'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Project sections'] button[role=tab]")
        out_tab = tabs.filter(has_text="Output").first
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

    def main_log_area(self):
        return "[data-panel='ausgabe'] [data-agent-view][data-role='main'] .bv-log"

    def sub_log_area(self, session):
        return ("[data-panel='ausgabe'] "
                f"[data-agent-view][data-role='subagent'][data-session='{session}'] "
                ".bv-log")

    def legacy_log_area(self):
        return "[data-panel='ausgabe'] pre#log"

    def text_colors(self, selector):
        nodes = self.page.evaluate(COLORS_JS, selector)
        self.assertIsNotNone(
            nodes, f"Ausgabefläche {selector} wurde nicht gefunden")
        return nodes

    def wait_for_text(self, selector, marker, timeout=20):
        self.wait_until(
            lambda: any(marker in node["text"] for node in self.text_colors(selector)),
            timeout=timeout,
            message=f"{marker!r} erschien nicht in {selector}")

    def colors_of(self, nodes, marker):
        return {node["color"] for node in nodes if marker in node["text"]}

    def assert_line_highlighted(self, nodes, marker, plain_marker):
        plain = self.colors_of(nodes, plain_marker)
        self.assertEqual(
            len(plain), 1,
            f"Die schlichte Zeile trägt mehrere Farben: {plain!r}")
        marked = self.colors_of(nodes, marker)
        self.assertTrue(
            marked, f"Hervorhebungszeichenkette {marker!r} wurde nicht gefunden")
        different = marked - plain
        self.assertTrue(
            different,
            f"{marker!r} unterscheidet sich farblich nicht von der "
            f"schlichten Zeile (Farben {sorted(marked)!r} gegen "
            f"{sorted(plain)!r})")

    def assert_text_preserved(self, selector, *lines):
        text = self.page.eval_on_selector(selector, "area => area.textContent")
        for line in lines:
            self.assertIn(
                line, text,
                f"Protokollzeile fehlt oder ist verändert in {selector}")
            self.assertEqual(
                1, text.count(line),
                f"Protokollzeile erscheint mehrfach: {line!r}")
        visible = self.page.eval_on_selector(selector, "area => area.innerText")
        for line in lines:
            self.assertIn(
                line, visible,
                f"Protokollzeile ist nicht sichtbar dargestellt: {line!r}")

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")

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

    def steer_textarea(self):
        area = self.panel().locator("textarea[aria-label*='Zusatzanweisung'], textarea[aria-label*='Additional instruction']")
        self.assertGreater(
            area.count(), 0,
            "Keine Anweisungseingabe (textarea mit aria-label "
            "'Zusatzanweisung') gefunden")
        return area.first

    def steer_send_button(self):
        button = self.panel().locator("button").filter(
            has_text=re.compile("senden|Send", re.I)).first
        self.assertGreater(
            button.count(), 0, "Kein Senden-Knopf gefunden")
        return button

    def continue_button(self):
        return self.panel().locator("button").filter(
            has_text=re.compile(r"^Resume$")).first


class MainAgentHighlightTest(AP16OutputBrowserTest):
    def test_main_agent_log_lines_are_visually_distinguished(self):
        """AK1/AK3: Hauptausgabe hebt Zeilen hervor und bleibt textgleich.

        Vorbedingung: aktiver Lauf; Hauptlog mit Kopf-, Fehler-, Pfad-,
        schlichter und Markup-Zeile.
        Aktion: Ausgabeansicht öffnen; berechnete Farben und Textinhalt der
        Hauptausgabe messen.
        Erwartung: Kopf-, Fehler- und Pfadtoken tragen andere Farben als die
        schlichte Zeile; alle Zeilen stehen exakt einmal sichtbar im Text.
        Fehlerfall: Keine Farbdifferenz oder veränderter/doppelter Text.
        """
        self.register_run("running")
        self.write_log(MAIN_PLAIN, MAIN_HEAD, MAIN_ERR, MAIN_PATH, MAIN_MARKUP)
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_ERR)

        selector = self.main_log_area()
        self.wait_for_text(selector, MAIN_PLAIN)
        nodes = self.text_colors(selector)
        self.assert_line_highlighted(nodes, "FEHLERZEILE_ROT", MAIN_PLAIN)
        self.assert_line_highlighted(nodes, "PROTOKOLLKOPF_APX", MAIN_PLAIN)
        self.assert_line_highlighted(nodes, "bin/web/app.js", MAIN_PLAIN)
        self.assert_text_preserved(
            selector, MAIN_PLAIN, MAIN_HEAD, MAIN_ERR, MAIN_PATH, MAIN_MARKUP)
        self.assert_clean_page()

    def test_subagent_log_is_highlighted_like_the_main_log(self):
        """AK2: Subagentenansicht erhält dieselbe Hervorhebung.

        Vorbedingung: aktiver Lauf; Subagent A mit Fehler- und schlichter
        Zeile in seiner Ausgabe.
        Aktion: Farben in der Subagentenansicht messen.
        Erwartung: Die Fehlerzeile unterscheidet sich farblich von der
        schlichten Zeile in derselben Ansicht.
        Fehlerfall: Die Subagentenausgabe bleibt ohne Hervorhebung.
        """
        self.register_run("running")
        self.write_log(MAIN_PLAIN, MAIN_ERR)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A",
                     SUB_PLAIN + "\n" + SUB_ERR),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_ERR)
        self.wait_for_view("subagent", CHILD_A, SUB_ERR)

        selector = self.sub_log_area(CHILD_A)
        self.wait_for_text(selector, SUB_PLAIN)
        nodes = self.text_colors(selector)
        self.assert_line_highlighted(nodes, "SUBFEHLER_ROT", SUB_PLAIN)
        self.assert_text_preserved(selector, SUB_PLAIN, SUB_ERR)
        self.assert_clean_page()

    def test_log_markup_is_never_interpreted_as_html(self):
        """AK4: Protokollmarkup bleibt Text und wird nie als HTML gelesen.

        Vorbedingung: aktiver Lauf; Haupt- und Subagentenprotokoll enthalten
        ``<script>``- und ``<b>``-Markup.
        Aktion: Ausgabeansicht öffnen; DOM-Zählung und ``window.__ap16pwn``
        prüfen.
        Erwartung: Kein Skript ausgeführt, keine Markup-Elemente in den
        Ansichten, Markup wörtlich sichtbar; Seite fehlerfrei.
        Fehlerfall: Markup wird als HTML interpretiert oder erzeugt Fehler.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKUP, MAIN_PLAIN)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", SUB_MARKUP),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKUP)
        self.wait_for_view("subagent", CHILD_A, SUB_MARKUP)

        main_selector = self.main_log_area()
        sub_selector = self.sub_log_area(CHILD_A)
        self.wait_for_text(main_selector, MAIN_MARKUP)
        self.wait_for_text(sub_selector, SUB_MARKUP)
        self.assertIsNone(
            self.page.evaluate("() => window.__ap16pwn"),
            "Protokollinhalt wurde als Skript ausgeführt")
        for name, selector in (("Hauptansicht", main_selector),
                               ("Subagentenansicht", sub_selector)):
            probe = self.page.evaluate(MARKUP_PROBE_JS, selector)
            self.assertEqual(
                0, probe["scripts"],
                f"{name} interpretierte ein Skript-Tag als HTML")
            self.assertEqual(
                0, probe["bold"],
                f"{name} interpretierte ein <b>-Tag als HTML")
            self.assertIn(
                "<script>", self.page.eval_on_selector(
                    selector, "area => area.textContent"),
                f"{name} zeigt das Markup nicht wörtlich an")
        self.assert_clean_page()


class LiveHighlightTest(AP16OutputBrowserTest):
    def test_live_appended_error_line_is_highlighted(self):
        """AK5: Neue Protokollzeilen erscheinen hervorgehoben und fehlerfrei.

        Vorbedingung: aktiver Lauf, Ausgabeansicht geöffnet.
        Aktion: Fehlerzeile an das Laufprotokoll anhängen.
        Erwartung: Die neue Zeile erscheint farblich von schlichten Zeilen
        unterschieden, genau einmal, ohne JavaScript-Fehler oder
        Browserdialoge.
        Fehlerfall: Neue Zeile ohne Hervorhebung, doppelt oder mit
        JavaScript-Fehlern im Live-Pfad.
        """
        self.register_run("running")
        self.write_log(MAIN_PLAIN, MAIN_ERR)
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_ERR)

        selector = self.main_log_area()
        self.wait_for_text(selector, MAIN_PLAIN)
        self.append_log(LIVE_ERR)
        self.wait_for_text(selector, "LIVEFEHLER_ROT")
        nodes = self.text_colors(selector)
        self.assert_line_highlighted(nodes, "LIVEFEHLER_ROT", MAIN_PLAIN)
        self.assert_text_preserved(selector, LIVE_ERR)
        self.assert_clean_page()


class LegacyRunLogTest(AP16OutputBrowserTest):
    def test_f19_run_log_keeps_its_highlighting(self):
        """AK6: Die „Live-Ausgabe“-Karte behält ihre F19-Hervorhebung.

        Vorbedingung: beendeter Lauf ohne Sitzungsangabe; die Ausgabeansicht
        zeigt den Rückfallmodus mit ``pre#log``.
        Aktion: Farben in der „Live-Ausgabe“-Karte messen.
        Erwartung: Kopf- und Fehlerzeilen unterscheiden sich farblich von der
        schlichten Zeile.
        Fehlerfall: Die bestehende F19-Hervorhebung ging verloren.
        """
        self.register_run("finished")
        self.write_log(MAIN_PLAIN, MAIN_HEAD, MAIN_ERR)
        self.open_detail()
        self.open_output()

        selector = self.legacy_log_area()
        self.wait_for_text(selector, MAIN_PLAIN)
        self.assertTrue(
            self.panel().locator("pre#log").count() == 1,
            "Die Live-Ausgabe-Karte mit pre#log fehlt im Rückfallmodus")
        nodes = self.text_colors(selector)
        self.assert_line_highlighted(nodes, "FEHLERZEILE_ROT", MAIN_PLAIN)
        self.assert_line_highlighted(nodes, "PROTOKOLLKOPF_APX", MAIN_PLAIN)
        self.assert_clean_page()

    def test_send_and_continue_controls_still_work(self):
        """AK6: Anweisung senden bleibt unberührt; kein Fortsetzen im Lauf.

        Vorbedingung: aktiver Lauf; /api/steer abgefangen.
        Aktion: Anweisung eingeben und über den Senden-Knopf absetzen.
        Erwartung: Eingabe und Knopf sind freigegeben, der POST nennt
        Projektname und Hauptsession; kein sichtbarer Fortsetzen-Knopf.
        Fehlerfall: Steuerung wurde durch die Hervorhebung beschädigt.
        """
        self.register_run("running")
        self.write_log(MAIN_PLAIN, MAIN_ERR)
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_ERR)

        textarea = self.steer_textarea()
        send = self.steer_send_button()
        self.assertFalse(textarea.is_disabled(),
                         "Anweisungseingabe ist gesperrt, obwohl der Lauf aktiv ist")
        self.assertFalse(send.is_disabled(),
                         "Senden-Knopf ist gesperrt, obwohl der Lauf aktiv ist")
        self.wait_until(
            lambda: self.continue_button().count() == 0
            or not self.continue_button().first.is_visible(),
            message="Während eines aktiven Laufs wird Fortsetzen angeboten")

        self.intercept("/api/steer")
        textarea.fill(STEER_TEXT)
        request = self.post_request("/api/steer", send.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual("proj", payload.get("name"), payload)
        self.assertEqual(MAIN_SESSION, payload.get("session"), payload)
        self.assertEqual(STEER_TEXT, payload.get("text"), payload)
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme: übersichtliche Ausgabeansicht ohne verschachtelte Scrollbars
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


MAIN_SESSION_ap20 = "ses_main_ap20"
SESSIONS = [
    "ses_ap20_a", "ses_ap20_b", "ses_ap20_c",
    "ses_ap20_d", "ses_ap20_e", "ses_ap20_f",
]
AGENT_NAMES = {
    "ses_ap20_a": "testerA", "ses_ap20_b": "testerB", "ses_ap20_c": "testerC",
    "ses_ap20_d": "testerD", "ses_ap20_e": "testerE", "ses_ap20_f": "testerF",
}
TAGS = {session: session[-1].upper() for session in SESSIONS}
DESCRIPTION_MARKERS = {
    session: f"PRUEF-{TAGS[session]}-4711" for session in SESSIONS
}
# Bewusst lange Beschreibungen: Die Übersichtszeile muss sie kürzen.
DESCRIPTIONS = {
    session: (f"{DESCRIPTION_MARKERS[session]} prüft die Ausgabe des "
              f"Hauptagenten, dokumentiert jeden Zwischenschritt und "
              f"hängt am Ende einen sehr ausführlichen Bericht an, der in "
              f"einer kompakten Zeile niemals vollständig Platz findet "
              f"ENDE-{TAGS[session]}-4711")
    for session in SESSIONS
}
MAIN_MARKER = "HAUPT-AP20-4711: Hauptagent schreibt sein Protokoll."
NEW_MAIN_SESSION = "ses_main_ap20_next"

MIN_CARD_HEIGHT = 300
ENLARGE_RATIO_HEIGHT = 0.70
ENLARGE_RATIO_WIDTH = 0.60


def output_marker(session):
    return f"AUSGABE-{TAGS[session]}-4711"


def live_marker(session):
    return f"LIVE-{TAGS[session]}-4711"


def long_output(session, marker):
    """Umfangreiche Ausgabe mit Highlighter-Zeilen (``hl-*``).

    Deutlich mehr Zeilen als in eine 300-px-Karte oder in den Hauptbereich
    passen: Nur so ist die Abnahme „das Vorschaufenster ist selbst scrollbar
    und zeigt seine letzten Zeilen“ aussagekräftig.
    """
    tag = TAGS[session]
    lines = [
        f"=== Ausgabe {tag} ===",
        f"[Werkzeug] bash — ok: {tag}",
        f"{marker}: Subagent {AGENT_NAMES[session]} arbeitet.",
        f"$ ./scripts/check-{tag.lower()}.sh --verbose",
        "+neue Zeile im Protokoll",
        "-alte Zeile im Protokoll",
        '`code` und "text" bleiben erhalten',
    ]
    for index in range(1, 61):
        lines.append(
            f"Zeile {index:02d} für {tag}: Der Agent protokolliert seinen "
            f"Fortschritt und die geprüften Dateien.")
    return "\n".join(lines)


class AP20FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: liefert keine Agentennachrichten.

    Damit greift im Dashboard der dokumentierte State-Fallback: Die Ausgabe
    der Subagenten kommt aus ``proj.log.state.json`` und lässt sich durch
    Überschreiben dieser Datei live verlängern, ohne einen echten Server.
    """

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/message" in self.path:
            self._send_json(200, {"data": []})
            return
        # Leere Lage für /api/session und /api/session/active: Die
        # Zustandsdatei bleibt maßgeblich für die Subagentenliste.
        self._send_json(200, {"ok": True})


# ---------- JS-Messhelfer (robust gegen Umbauten des DOM) ----------

OVERVIEW_JS = """() => {
  const panel = document.querySelector("[data-panel='ausgabe']");
  if (!panel) return {panel: false};
  const overview = panel.querySelector(".bv-overview[data-active-agents]");
  if (!overview) return {panel: true, present: false};
  const box = overview.getBoundingClientRect();
  const rows = Array.from(overview.querySelectorAll(".bv-overview-row")).map(row => {
    const focus = row.querySelector("button[data-focus-session]");
    const pill = row.querySelector("[class*='pill'], [data-status], [role='status']");
    const rowBox = row.getBoundingClientRect();
    return {
      session: row.getAttribute("data-overview-session"),
      text: row.innerText || "",
      height: rowBox.height,
      width: rowBox.width,
      visible: rowBox.width > 0 && rowBox.height > 0,
      hasPill: !!pill,
      focusSession: focus ? focus.getAttribute("data-focus-session") : null,
      focusLabel: focus ? (focus.getAttribute("aria-label") || "") : null,
    };
  });
  return {
    panel: true, present: true,
    visible: box.width > 0 && box.height > 0,
    active: overview.getAttribute("data-active-agents"),
    text: overview.innerText || "",
    rows,
  };
}"""

LAYOUT_JS = """() => {
  const panel = document.querySelector("[data-panel='ausgabe']");
  if (!panel) return null;
  const rect = panel.getBoundingClientRect();
  const views = Array.from(panel.querySelectorAll("[data-agent-view]"));
  const describe = node => {
    const cls = typeof node.className === "string"
      ? node.className.trim().split(/\\s+/).filter(Boolean).join(".")
      : "";
    return node.tagName.toLowerCase() + (cls ? "." + cls : "");
  };
  const scrollable = [];
  const horizontal = [];
  for (const node of panel.querySelectorAll("*")) {
    const style = getComputedStyle(node);
    const overflowY = style.overflowY;
    const overflowX = style.overflowX;
    if ((overflowY === "auto" || overflowY === "scroll")
        && node.scrollHeight > node.clientHeight + 1) {
      const owner = node.closest("[data-agent-view]");
      scrollable.push({
        node: describe(node),
        overflowY,
        scrollHeight: node.scrollHeight,
        clientHeight: node.clientHeight,
        session: owner ? owner.getAttribute("data-session") : null,
        role: owner ? owner.getAttribute("data-role") : null,
        panelWide: views.length > 0 && views.every(view => node.contains(view)),
      });
    }
    if ((overflowX === "auto" || overflowX === "scroll")
        && node.scrollWidth > node.clientWidth + 2) {
      horizontal.push({
        node: describe(node),
        overflowX,
        scrollWidth: node.scrollWidth,
        clientWidth: node.clientWidth,
      });
    }
  }
  const subs = panel.querySelector(".bv-subs");
  const logs = Array.from(panel.querySelectorAll("[data-agent-view] .bv-log")).map(node => {
    const owner = node.closest("[data-agent-view]");
    return {
      session: owner.getAttribute("data-session"),
      role: owner.getAttribute("data-role"),
      overflowY: getComputedStyle(node).overflowY,
      scrollHeight: node.scrollHeight,
      clientHeight: node.clientHeight,
    };
  });
  return {
    panel: {left: rect.left, right: rect.right, width: rect.width, height: rect.height},
    subs: subs ? {
      scrollWidth: subs.scrollWidth,
      clientWidth: subs.clientWidth,
      overflowX: getComputedStyle(subs).overflowX,
      overflowY: getComputedStyle(subs).overflowY,
    } : null,
    scrollable, horizontal, logs,
  };
}"""

DESCRIPTION_TRUNCATION_JS = """(arg) => {
  const panel = document.querySelector("[data-panel='ausgabe']");
  const row = panel && panel.querySelector(
    ".bv-overview-row[data-overview-session='" + arg.session + "']");
  if (!row) return {found: false};
  const text = row.innerText || "";
  if (!text.includes(arg.description)) {
    return {found: true, truncated: true, reason: "text"};
  }
  const rowStyle = getComputedStyle(row);
  if (rowStyle.overflow !== "visible"
      && (row.scrollWidth > row.clientWidth + 2
          || row.scrollHeight > row.clientHeight + 2)) {
    return {found: true, truncated: true, reason: "row-clip"};
  }
  for (const node of row.querySelectorAll("*")) {
    const style = getComputedStyle(node);
    if (style.textOverflow === "ellipsis") {
      return {found: true, truncated: true, reason: "ellipsis"};
    }
    if ((style.overflow === "hidden" || style.overflowX === "hidden"
         || style.overflowY === "hidden")
        && (node.scrollWidth > node.clientWidth + 2
            || node.scrollHeight > node.clientHeight + 2)) {
      return {found: true, truncated: true, reason: "node-clip"};
    }
  }
  return {found: true, truncated: false, reason: "full"};
}"""


class AP20BrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP20 UI Verbesserungen Ausgabe\n"
            "  Beschreibung: Test\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True, exist_ok=True)
        # Kennwort vorhanden, damit die Attrappe tatsächlich angefragt wird:
        # Sie liefert keine Nachrichten, der State-Fallback ist maßgeblich.
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-AP20-4711", encoding="utf-8")
        password.chmod(0o600)
        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), AP20FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
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
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
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
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
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

    def sub(self, session, status="running", output=None):
        return {
            "session": session,
            "agent": AGENT_NAMES[session],
            "description": DESCRIPTIONS[session],
            "prompt": "Auftrag für " + AGENT_NAMES[session],
            "status": status,
            "started": int(time.time()) + 5,
            "ended": int(time.time()) + 180 if status != "running" else 0,
            "output": (output if output is not None
                       else long_output(session, output_marker(session))),
        }

    def write_state(self, subs=None, main_session=MAIN_SESSION_ap20):
        if subs is None:
            subs = [self.sub(session) for session in SESSIONS]
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": main_session, "subagents": subs},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def panel(self):
        return self.page.locator("[data-panel='ausgabe']")

    def agent_view(self, role=None, session=None):
        selector = "[data-agent-view]"
        if role:
            selector += f"[data-role='{role}']"
        if session:
            selector += f"[data-session='{session}']"
        return self.panel().locator(selector)

    def sub_view(self, session):
        return self.agent_view(role="subagent", session=session)

    def overview(self):
        return self.page.evaluate(OVERVIEW_JS)

    def layout(self):
        return self.page.evaluate(LAYOUT_JS)

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        tabs = self.page.locator(
            "[role='tablist'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[role='tablist'] button[role=tab]")
        out_tab = self.page.locator(
            "[role='tab'][aria-controls='panel-ausgabe']").first
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

    def open_six_running(self, main_lines=None):
        """Standardvorbedingung: Hauptagent + sechs laufende Subagenten."""
        self.register_run("running")
        self.write_log(*(main_lines if main_lines is not None
                         else [MAIN_MARKER]))
        self.write_state()
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_ap20, MAIN_MARKER)
        for session in SESSIONS:
            self.wait_for_view("subagent", session, output_marker(session))
        return self.panel()

    def wait_for_overview(self, active=6, timeout=20):
        def ready():
            data = self.overview()
            return bool(
                data.get("present") and data.get("visible")
                and data.get("active") == str(active)
                and len(data.get("rows") or []) == active + 1)
        self.wait_until(
            ready, timeout=timeout,
            message="Kompakte Übersicht "
                    f"(data-active-agents='{active}') fehlt oder ist "
                    "unvollständig: " + repr(self.overview()))
        return self.overview()

    def focus_button(self, session):
        return self.panel().locator(
            f".bv-overview-row[data-overview-session='{session}'] "
            f"button[data-focus-session='{session}']")

    def card_enlarge_button(self, session):
        """Karten-Umschalter (Fokus) im Kopf der Subagenten-Karte.

        B20: Der Knopf heißt einheitlich „Fokus“/„Fokus beenden“ und wird
        über den Kartenkopf ``.bv-head button`` sowie sein ``aria-label``
        („… fokussieren“) gefunden. Der alte Name „Vergrößern/Verkleinern“
        ist nicht mehr Teil des Vertrags.
        """
        buttons = self.sub_view(session).locator(".bv-head button")
        for index in range(buttons.count()):
            candidate = buttons.nth(index)
            label = (candidate.get_attribute("aria-label") or "").lower()
            if re.search(r"fokus|focus", label):
                return candidate
        self.fail(f"Kein Fokus-Knopf in der Karte {session} gefunden "
                  f"({buttons.count()} Knöpfe im Kartenkopf)")

    def scroll_sessions(self, layout):
        """Sessions der tatsächlich scrollbaren Ausgabeflächen."""
        return {entry["session"] for entry in layout["scrollable"]
                if "bv-log" in entry["node"]}

    def assert_only_logs_scroll(self, layout, message="Scrollbereiche"):
        """B20: Scrollen dürfen nur Ausgabeflächen und der panelweite Container."""
        for entry in layout["scrollable"]:
            self.assertTrue(
                "bv-log" in entry["node"] or entry["panelWide"],
                f"{message}: Unerwarteter scrollbarer Bereich (weder "
                f"Ausgabefläche noch panelweit): {entry!r}")

    def sizes(self, locator):
        return locator.bounding_box() or {
            "width": 0, "height": 0, "x": 0, "y": 0}

    def card_sizes(self):
        boxes = {}
        for session in SESSIONS:
            boxes[session] = self.sizes(self.sub_view(session).first)
        return boxes

    def is_enlarged(self, session):
        classes = self.sub_view(session).first.get_attribute("class") or ""
        return "enlarged" in classes.split()

    def wait_enlarged(self, session, timeout=10):
        def check():
            box = self.sizes(self.sub_view(session).first)
            return (self.is_enlarged(session)
                    and box["height"] >= ENLARGE_RATIO_HEIGHT * 900
                    and box["width"] >= ENLARGE_RATIO_WIDTH * 1400)
        self.wait_until(
            check, timeout=timeout,
            message=f"Karte {session} wurde nicht ansichtsfüllend vergrößert: "
                    f"class={self.sub_view(session).first.get_attribute('class')!r} "
                    f"box={self.sizes(self.sub_view(session).first)!r}")

    def wait_normal(self, session, timeout=10):
        def check():
            return (not self.is_enlarged(session)
                    and self.sizes(self.sub_view(session).first)["height"]
                    < MIN_CARD_HEIGHT + 100)
        self.wait_until(
            check, timeout=timeout,
            message=f"Karte {session} wurde nicht auf Normalgröße "
                    f"zurückgestellt: "
                    f"class={self.sub_view(session).first.get_attribute('class')!r} "
                    f"box={self.sizes(self.sub_view(session).first)!r}")

    def main_focus_button(self):
        """Fokus-Knopf im Kopf der Hauptagentenansicht."""
        return self.panel().locator(
            "[data-agent-view][data-role='main'] "
            "button[data-focus-session]")

    def main_overview_focus_button(self, session=MAIN_SESSION_ap20):
        """Fokus-Knopf der Übersichtszeile des Hauptagenten."""
        return self.panel().locator(
            f".bv-overview-row[data-overview-session='{session}'] "
            "button[data-focus-session]")

    def is_main_enlarged(self):
        classes = (self.agent_view(role="main").first.get_attribute("class")
                   or "")
        return "enlarged" in classes.split()

    def wait_main_enlarged(self, timeout=10):
        def check():
            box = self.sizes(self.agent_view(role="main").first)
            return (self.is_main_enlarged()
                    and box["height"] >= ENLARGE_RATIO_HEIGHT * 900
                    and box["width"] >= ENLARGE_RATIO_WIDTH * 1400)
        self.wait_until(
            check, timeout=timeout,
            message="Die Hauptagentenansicht wurde nicht ansichtsfüllend "
                    "vergrößert: "
                    f"class={self.agent_view(role='main').first.get_attribute('class')!r} "
                    f"box={self.sizes(self.agent_view(role='main').first)!r}")

    def wait_main_normal(self, timeout=10):
        def check():
            return (not self.is_main_enlarged()
                    and self.sizes(self.agent_view(role="main").first)["height"]
                    < ENLARGE_RATIO_HEIGHT * 900)
        self.wait_until(
            check, timeout=timeout,
            message="Die Hauptagentenansicht wurde nicht auf Normalgröße "
                    "zurückgestellt: "
                    f"class={self.agent_view(role='main').first.get_attribute('class')!r} "
                    f"box={self.sizes(self.agent_view(role='main').first)!r}")

    def long_main_log(self):
        """Hauptlog mit genug Zeilen, damit die vergrößerte Ansicht scrollt."""
        lines = [MAIN_MARKER]
        for index in range(1, 71):
            lines.append(
                f"Zeile {index:02d} des Hauptagenten: Er protokolliert "
                "Fortschritt, geprüfte Dateien und offene Punkte.")
        return lines

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")


class ContractTest(AP20BrowserTest):
    def test_b11_f30_contract_remains_with_six_subagents(self):
        """AK1: Der B11/F30-Vertrag gilt auch mit sechs Subagenten.

        Vorbedingung: aktiver Lauf, Hauptlog, sechs laufende Subagenten mit
        umfangreicher Ausgabe; Viewport 1400×900.
        Aktion: Ausgabe öffnen, Struktur prüfen; am Ende Lauf auf
        ``finished`` setzen.
        Erwartung: Panel; Hauptagent + 6 Subagenten gleichzeitig im DOM und
        sichtbar mit ``role='log'``; Zielauswahl mit 7 Optionen;
        Anweisungseingabe, Senden-Knopf, ``.bv-log`` mit ``hl-*``-Spans,
        ``.bv-subs``, Karten ≥ 300 px, Fokus-Knopf in jeder Karte, kein
        Modal, keine Tabliste; bei gestopptem Lauf erscheint „Fortsetzen“.
        Fehlerfall: Der Neuaufbau bricht den bestehenden Vertrag.
        """
        self.open_six_running()

        self.assertTrue(self.panel().first.is_visible(),
                        "Das Ausgabepanel ist nicht sichtbar")
        main_view = self.agent_view(role="main")
        self.assertEqual(1, main_view.count(),
                         "Genau eine Hauptagentenansicht erwartet")
        self.assertTrue(main_view.first.is_visible(),
                        "Der Hauptagent ist nicht sichtbar")
        self.assertEqual("log", main_view.first.get_attribute("role"),
                         "Der Hauptagent ist keine Live-Region (role=log)")

        for session in SESSIONS:
            view = self.sub_view(session)
            self.assertEqual(1, view.count(),
                             f"Subagent {session} fehlt in der Ansicht")
            self.assertTrue(view.first.is_visible(),
                            f"Subagent {session} ist nicht sichtbar")
            self.assertEqual("log", view.first.get_attribute("role"),
                             f"Subagent {session} ist keine Live-Region")
        sessions_in_dom = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] [data-agent-view]",
            "nodes => nodes.map(node => node.getAttribute('data-session'))")
        self.assertEqual(
            {MAIN_SESSION_ap20, *SESSIONS}, set(sessions_in_dom),
            "Nicht alle Agenten sind gleichzeitig im DOM: "
            + repr(sessions_in_dom))

        select = self.panel().locator("select[aria-label='Target']")
        self.assertEqual(1, select.count(),
                         "Keine Zielauswahl (select[aria-label='Ziel'])")
        options = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] select[aria-label='Target'] option",
            "nodes => nodes.map(node => node.value)")
        self.assertEqual(
            {MAIN_SESSION_ap20, *SESSIONS}, set(options),
            "Zielauswahl enthält nicht alle Agenten: " + repr(options))

        self.assertEqual(
            1, self.panel().locator(
                "textarea[aria-label*='Additional instruction']").count(),
            "Keine Anweisungseingabe (aria-label „Zusatzanweisung“)")
        self.assertGreater(
            self.panel().locator("button").filter(
                has_text="Send instruction").count(),
            0, "Kein Senden-Knopf vorhanden")

        highlighted = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] [data-agent-view] .bv-log "
            "span[class^='hl-']",
            "nodes => nodes.length")
        self.assertGreater(
            highlighted, 0,
            "Die Ausgabeflächen enthalten keine Highlighter-Spans (hl-*)")
        preserved = self.page.eval_on_selector(
            f"[data-panel='ausgabe'] [data-agent-view]"
            f"[data-session='{SESSIONS[0]}'] .bv-log",
            "node => node.textContent")
        self.assertIn(output_marker(SESSIONS[0]), preserved,
                      "Der Ausgabetext der Karte ist nicht wörtlich erhalten")

        self.assertEqual(
            1, self.panel().locator(".bv-subs").count(),
            "Der Container .bv-subs fehlt")

        for session in SESSIONS:
            box = self.sizes(self.sub_view(session).first)
            self.assertGreaterEqual(
                box["height"], MIN_CARD_HEIGHT,
                f"Karte {session} ist mit {box['height']} px zu klein "
                f"(Ziel ≥ {MIN_CARD_HEIGHT} px)")
            button = self.card_enlarge_button(session)
            self.assertIsNotNone(button, f"Kein Knopf in Karte {session}")

        tabs = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] [role='tablist']",
            "nodes => nodes.length")
        self.assertEqual(0, tabs,
                         "Im Ausgabebereich existiert eine Tabliste")
        dialogs = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] [role='dialog'], "
            "[data-panel='ausgabe'] dialog[open]",
            "nodes => nodes.length")
        self.assertEqual(0, dialogs,
                         "Die Ausgabeansicht öffnete ein Modal")

        self.register_run("finished")
        continue_button = self.panel().locator("button").filter(
            has_text="Resume").first
        self.wait_until(
            lambda: continue_button.count() > 0
            and continue_button.is_visible(),
            message="Bei gestopptem Lauf fehlt der Fortsetzen-Knopf")
        self.assert_clean_page()


class OverviewTest(AP20BrowserTest):
    def test_overview_lists_all_agents_with_compact_rows(self):
        """AK2: Kompakte Statusübersicht über alle aktiven Agenten.

        Vorbedingung: sechs laufende Subagenten, Viewport 1400×900.
        Aktion: Übersicht auslesen.
        Erwartung: ``.bv-overview[aria-label='Aktive Agenten']`` mit
        ``data-active-agents='6'``, sichtbarem Zählertext mit „6“; je Agent
        (Hauptsession + 6 Subagenten) eine kompakte Zeile
        ``.bv-overview-row[data-overview-session=…]`` mit Name, gekürzter
        Beschreibung, Status-Pille und Fokus-Knopf je Subagent.
        Fehlerfall: Übersicht fehlt, ist unvollständig, nicht kompakt oder
        ohne Fokus-Knöpfe.
        """
        self.open_six_running()
        data = self.wait_for_overview(active=6)

        self.assertTrue(data["visible"], "Die Übersicht ist nicht sichtbar")
        self.assertIn(
            "6", data["text"],
            "Der Zählertext der Übersicht nennt nicht sechs Agenten: "
            + repr(data["text"]))
        rows = {row["session"]: row for row in data["rows"]}
        expected = {MAIN_SESSION_ap20, *SESSIONS}
        self.assertEqual(
            expected, set(rows),
            "Die Übersichtszeilen nennen nicht alle Agenten: "
            + repr([row["session"] for row in data["rows"]]))
        self.assertEqual(
            len(expected), len(data["rows"]),
            "Die Übersicht rendert Duplikate statt genau einer Zeile je "
            "Agent: " + repr([row["session"] for row in data["rows"]]))

        main_row = rows[MAIN_SESSION_ap20]
        self.assertIn("Main agent", main_row["text"],
                      "Die Übersichtszeile der Hauptsession nennt den "
                      "Hauptagenten nicht: " + repr(main_row["text"]))
        self.assertTrue(main_row["hasPill"],
                        "Die Hauptzeile hat keine Status-Pille: "
                        + repr(main_row))
        self.assertTrue(main_row["visible"], "Die Hauptzeile ist nicht sichtbar")

        for session in SESSIONS:
            row = rows[session]
            self.assertTrue(row["visible"],
                            f"Übersichtszeile {session} ist nicht sichtbar")
            self.assertIn(
                AGENT_NAMES[session], row["text"],
                f"Übersichtszeile {session} nennt den Agentennamen nicht: "
                + repr(row["text"]))
            self.assertIn(
                DESCRIPTION_MARKERS[session], row["text"],
                f"Übersichtszeile {session} zeigt die Beschreibung nicht: "
                + repr(row["text"]))
            self.assertTrue(
                row["hasPill"],
                f"Übersichtszeile {session} hat keine Status-Pille: "
                + repr(row))
            self.assertEqual(
                session, row["focusSession"],
                f"Der Fokus-Knopf der Zeile {session} trägt nicht "
                f"data-focus-session='{session}': {row!r}")
            self.assertRegex(
                (row["focusLabel"] or ""), re.compile(r"fokussieren|focus", re.I),
                f"Der Fokus-Knopf der Zeile {session} ist nicht als "
                f"„fokussieren“ beschriftet: {row!r}")
            self.assertLessEqual(
                row["height"], 90,
                f"Übersichtszeile {session} ist mit {row['height']:.0f} px "
                "nicht kompakt")
            truncation = self.page.evaluate(
                DESCRIPTION_TRUNCATION_JS,
                {"session": session,
                 "description": DESCRIPTIONS[session]})
            self.assertTrue(
                truncation.get("found"),
                f"Übersichtszeile {session} wurde nicht gefunden")
            self.assertTrue(
                truncation.get("truncated"),
                f"Die lange Beschreibung der Zeile {session} wird nicht "
                f"gekürzt dargestellt: {truncation!r}")

        positions = self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                 "[data-panel='ausgabe'] .bv-overview-row"))
                 .map(row => row.getBoundingClientRect().top)""")
        self.assertEqual(len(expected), len(positions),
                         "Die Übersicht rendert nicht genau eine Zeile je "
                         "Agent")
        self.assert_clean_page()

    def test_finished_subagent_leaves_overview_and_view(self):
        """AK2: Beendete Subagenten verschwinden aus Ansicht und Übersicht.

        Vorbedingung: sechs laufende Subagenten sichtbar.
        Aktion: Subagent A in der Zustandsdatei auf ``completed`` setzen.
        Erwartung: Ansicht und Übersichtszeile von A verschwinden;
        ``data-active-agents`` wird „5“; Hauptagent und die übrigen fünf
        bleiben sichtbar.
        Fehlerfall: Beendete Agenten bleiben in der Übersicht stehen oder
        reißen andere Agenten mit.
        """
        self.open_six_running()
        self.wait_for_overview(active=6)

        subs = [self.sub(session) for session in SESSIONS]
        subs[0] = self.sub(SESSIONS[0], status="completed")
        self.write_state(subs)

        self.wait_until(
            lambda: self.sub_view(SESSIONS[0]).count() == 0
            or not self.sub_view(SESSIONS[0]).first.is_visible(),
            message="Der abgeschlossene Subagent A blieb in der Ansicht")
        data = self.wait_for_overview(active=5)
        sessions = [row["session"] for row in data["rows"]]
        self.assertNotIn(SESSIONS[0], sessions,
                         "Der abgeschlossene Subagent A blieb in der "
                         "Übersicht: " + repr(sessions))
        self.assertEqual(
            {MAIN_SESSION_ap20, *SESSIONS[1:]}, set(sessions),
            "Nach dem Abschluss fehlen weitere Agenten in der Übersicht: "
            + repr(sessions))
        self.assertTrue(
            self.agent_view(role="main").first.is_visible(),
            "Der Hauptagent verschwand mit dem abgeschlossenen Subagenten")
        self.assert_clean_page()


class ScrollbarTest(AP20BrowserTest):
    def test_normal_mode_has_no_nested_scrollbars_at_1400(self):
        """AK3: Im Normalmodus scrollen nur die Ausgabeflächen selbst.

        Vorbedingung: sechs laufende Subagenten, Viewport 1400×900.
        Aktion: Panel, ``.bv-subs`` und jede Agenten-Ausgabefläche messen.
        Erwartung: ``.bv-subs`` ohne horizontalen Overflow
        (``scrollWidth <= clientWidth + 2``); jedes ``[data-agent-view]
        .bv-log`` mit berechnetem ``overflow-y: auto`` und mit überlangem
        Inhalt tatsächlich scrollbar (``scrollHeight > clientHeight``);
        scrollbar sind nur Ausgabeflächen und der panelweite Container, also
        kein weiterer verschachtelter Scrollbereich; kein horizontal
        scrollbarer Bereich.
        Fehlerfall (Ticket-Screenshot): mehrere verschachtelte Scrollbars und
        eine seitlich scrollende Kartenleiste.
        """
        self.open_six_running()
        layout = self.layout()
        self.assertIsNotNone(layout, "Das Ausgabepanel wurde nicht gefunden")

        self.assertIsNotNone(layout["subs"],
                             "Der Container .bv-subs fehlt")
        subs = layout["subs"]
        self.assertLessEqual(
            subs["scrollWidth"], subs["clientWidth"] + 2,
            f".bv-subs hat horizontalen Overflow: scrollWidth="
            f"{subs['scrollWidth']} px, clientWidth={subs['clientWidth']} px")

        for log in layout["logs"]:
            self.assertEqual(
                "auto", log["overflowY"],
                f"Die Ausgabefläche von {log['role']}/{log['session']} hat "
                f"im Normalmodus overflow-y={log['overflowY']!r} "
                "(erwartet: auto)")

        self.assert_only_logs_scroll(layout)
        scrolling = self.scroll_sessions(layout)
        for session in SESSIONS:
            self.assertIn(
                session, scrolling,
                f"Die Ausgabefläche von {session} ist mit überlangem Inhalt "
                "nicht scrollbar; die letzten Zeilen wären abgeschnitten: "
                + repr(layout["logs"]))

        self.assertEqual(
            [], layout["horizontal"],
            "Elemente mit horizontalem scrollbaren Overflow: "
            + repr(layout["horizontal"]))
        self.assert_clean_page()

    def test_narrow_viewport_has_no_horizontal_overflow_at_900(self):
        """AK3: Auch bei 900 px Viewport keine horizontale Kartenleiste.

        Vorbedingung: sechs laufende Subagenten; Viewport 900×900.
        Aktion: Viewport verkleinern und messen.
        Erwartung: ``.bv-subs`` ohne horizontalen Overflow; jedes ``.bv-log``
        ``overflow-y: auto``; kein horizontal scrollbarer Bereich.
        Fehlerfall: Die Kartenleiste wird seitlich abgeschnitten und muss
        horizontal gescrollt werden.
        """
        self.open_six_running()
        self.page.set_viewport_size({"width": 900, "height": 900})
        self.wait_until(
            lambda: (self.layout() or {}).get("subs") is not None,
            message="Der Container .bv-subs fehlt nach dem Verkleinern")
        self.page.wait_for_timeout(400)
        layout = self.layout()

        subs = layout["subs"]
        self.assertLessEqual(
            subs["scrollWidth"], subs["clientWidth"] + 2,
            f".bv-subs hat bei 900 px horizontalen Overflow: scrollWidth="
            f"{subs['scrollWidth']} px, clientWidth={subs['clientWidth']} px")
        self.assertEqual(
            [], layout["horizontal"],
            "Bei 900 px existieren horizontal scrollbare Bereiche: "
            + repr(layout["horizontal"]))
        for log in layout["logs"]:
            self.assertEqual(
                "auto", log["overflowY"],
                f"Die Ausgabefläche von {log['role']}/{log['session']} hat "
                f"bei 900 px overflow-y={log['overflowY']!r} "
                "(erwartet: auto)")
        self.assert_only_logs_scroll(layout, "Bei 900 px")
        self.assert_clean_page()


class GridTest(AP20BrowserTest):
    def test_subagent_cards_wrap_into_rows_within_the_panel(self):
        """AK4: Das Kartenraster bricht um und bleibt in der Panelbreite.

        Vorbedingung: sechs laufende Subagenten, Viewport 1400×900.
        Aktion: Karten und Panel ausmessen.
        Erwartung: Die sechs Karten liegen in mindestens zwei Zeilen
        (unterschiedliche ``y``-Werte) und ihre rechte Kante bleibt innerhalb
        der Panelbreite (≤ Panel rechts + 2).
        Fehlerfall: Einseitig abgeschnittene horizontale Kartenleiste.
        """
        self.open_six_running()
        layout = self.layout()
        panel_right = layout["panel"]["right"]
        boxes = self.card_sizes()

        for session, box in boxes.items():
            self.assertGreater(box["width"], 0,
                               f"Karte {session} hat keine Ausdehnung")
            self.assertLessEqual(
                box["x"] + box["width"], panel_right + 2,
                f"Karte {session} ragt über den Panelrand hinaus: rechte "
                f"Kante {box['x'] + box['width']:.1f} px, Panel rechts "
                f"{panel_right:.1f} px")

        rows = sorted({round(box["y"]) for box in boxes.values()})
        distinct_rows = []
        for value in rows:
            if not distinct_rows or value - distinct_rows[-1] > 20:
                distinct_rows.append(value)
        self.assertGreaterEqual(
            len(distinct_rows), 2,
            "Die sechs Subagent-Karten liegen in nur einer Zeile "
            f"(y-Werte: {rows!r})")
        self.assertGreaterEqual(
            len({round(box["x"]) for box in boxes.values()}), 2,
            "Die Karten sind nicht nebeneinander angeordnet: "
            + repr({session: box["x"] for session, box in boxes.items()}))
        self.assert_clean_page()


class FocusModeTest(AP20BrowserTest):
    def test_overview_focus_enlarges_one_card_and_unlocks_scroll(self):
        """AK5: Fokus-Modus zeigt genau eine Karte mit scrollbarer Ausgabe.

        Vorbedingung: sechs laufende Subagenten, Viewport 1400×900.
        Aktion: Fokus-Knopf der Übersicht für Session A klicken; danach die
        Zustandsdatei von A mit einem neuen Marker überschreiben; Fokus
        ausschließlich per Escape beenden.
        Erwartung: Genau Karte A trägt ``enlarged`` und ist ≥ 70 % vh /
        ≥ 60 % vw; ihr ``.bv-log`` bleibt scrollbar (``overflow-y: auto``,
        Inhalt überläuft) und gehört zu den scrollbaren Ausgabeflächen; der
        neue Marker erscheint ohne Neuladen; ``aria-expanded`` an Karten- und
        Übersichts-Knopf ist ``true`` und nach Escape wieder ``false``;
        danach ist die Karte normal groß und die Ausgabefläche weiterhin
        ``overflow-y: auto``.
        Fehlerfall: Kein Fokus, falsche Karte, eingefrorene Ausgabe, ein
        fehlender Escape-Handler oder abgeschnittene Ausgabe.
        """
        self.open_six_running()
        self.wait_for_overview(active=6)
        target = SESSIONS[0]
        overview_button = self.focus_button(target).first
        card_button = self.card_enlarge_button(target)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf meldet vor dem Fokus nicht "
            "aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Der Karten-Fokus-Knopf meldet vor dem Fokus nicht "
            "aria-expanded='false'")
        overview_button.click()
        self.wait_enlarged(target)
        self.assertEqual(
            "true", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf meldet im Fokus nicht "
            "aria-expanded='true'")
        self.assertEqual(
            "true", card_button.get_attribute("aria-expanded"),
            "Der Karten-Fokus-Knopf meldet im Fokus nicht "
            "aria-expanded='true'")

        for session in SESSIONS:
            if session == target:
                continue
            self.assertFalse(
                self.is_enlarged(session),
                f"Der Fokus vergrößerte zusätzlich Karte {session}")

        layout = self.layout()
        target_log = next(
            (log for log in layout["logs"] if log["session"] == target), None)
        self.assertIsNotNone(target_log,
                             f"Keine Ausgabefläche für Karte {target}")
        self.assertEqual(
            "auto", target_log["overflowY"],
            "Die Ausgabefläche der fokussierten Karte hat overflow-y="
            f"{target_log['overflowY']!r} (erwartet: auto)")
        self.assertGreater(
            target_log["scrollHeight"], target_log["clientHeight"] + 4,
            "Die Ausgabefläche der fokussierten Karte ist nicht scrollbar: "
            + repr(target_log))
        self.assertIn(
            target, self.scroll_sessions(layout),
            "Die Ausgabefläche der fokussierten Karte gehört nicht zu den "
            "scrollbaren Bereichen: " + repr(layout["scrollable"]))
        self.assert_only_logs_scroll(layout, "Im Fokus-Modus")

        new_marker = live_marker(target)
        subs = [self.sub(session) for session in SESSIONS]
        subs[0] = self.sub(
            target,
            output=long_output(target, output_marker(target))
            + "\n" + new_marker + ": Die fokussierte Karte schreibt weiter.")
        self.write_state(subs)
        self.wait_until(
            lambda: new_marker in self.sub_view(target).first.inner_text(),
            timeout=20,
            message="Die fokussierte Karte aktualisiert ihre Live-Ausgabe "
                    "nicht")

        # Escape ist hier der verbindliche Pfad. Kein Ersatzweg, damit ein
        # fehlender Handler (Regression) den Test zwingend rot macht.
        self.page.keyboard.press("Escape")
        self.wait_normal(target, timeout=8)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Nach Escape meldet der Übersichts-Fokus-Knopf nicht "
            "aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Nach Escape meldet der Karten-Fokus-Knopf nicht "
            "aria-expanded='false'")
        layout = self.layout()
        target_log = next(
            (log for log in layout["logs"] if log["session"] == target), None)
        self.assertEqual(
            "auto", target_log["overflowY"],
            "Nach dem Beenden des Fokus ist die Ausgabefläche nicht mehr "
            "scrollbar: " + repr(target_log))
        self.assert_only_logs_scroll(layout, "Nach dem Beenden des Fokus")
        self.assert_clean_page()

    def test_card_button_and_overview_focus_share_the_same_state(self):
        """AK5: Karten-Knopf und Übersichts-Fokus teilen denselben Zustand.

        Vorbedingung: sechs laufende Subagenten; Karte A normal groß.
        Aktion: Karten-Fokus-Knopf von A klicken; dann den
        Übersichts-Fokus-Knopf von A (programmatischer Klick, weil die
        vergrößerte Karte die Übersicht überdeckt); dann Fokus erneut über
        die Übersicht; schließlich den Karten-Knopf „Fokus beenden“.
        Erwartung: Jeder Weg hebt den Zustand des anderen auf; nach dem
        Karten-Knopf ist A vergrößert und ein Klick auf den Fokus-Knopf
        stellt die Normalgröße her; umgekehrt hebt der Karten-Knopf den
        Übersichts-Fokus auf. Der Karten-Knopf heißt im Fokus einheitlich
        „Fokus beenden“ (nicht „Verkleinern“).
        Fehlerfall: Zwei getrennte Zustände, sodass der eine Knopf den
        anderen nicht aufhebt.
        """
        self.open_six_running()
        self.wait_for_overview(active=6)
        target = SESSIONS[0]
        overview_button = self.focus_button(target).first
        card_button = self.card_enlarge_button(target)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf startet nicht mit "
            "aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Der Karten-Fokus-Knopf startet nicht mit "
            "aria-expanded='false'")

        card_button.click()
        self.wait_enlarged(target)
        self.assertEqual(
            "true", overview_button.get_attribute("aria-expanded"),
            "Der Karten-Knopf vergrößert die Karte, aber der "
            "Übersichts-Fokus-Knopf meldet nicht aria-expanded='true'")
        self.assertEqual(
            "true", card_button.get_attribute("aria-expanded"),
            "Der Karten-Knopf meldet nach dem Vergrößern nicht "
            "aria-expanded='true'")

        overview_button.evaluate("node => node.click()")
        self.wait_normal(target)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf hebt den Kartenzustand auf, meldet "
            "aber nicht aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Der Karten-Knopf meldet nach dem Aufheben per Übersicht nicht "
            "aria-expanded='false'")

        overview_button.click()
        self.wait_enlarged(target)
        self.assertEqual(
            "true", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf meldet im Fokus nicht "
            "aria-expanded='true'")
        self.assertEqual(
            "true", card_button.get_attribute("aria-expanded"),
            "Der Karten-Knopf spiegelt den Übersichts-Fokus nicht in "
            "aria-expanded='true'")

        shrink = self.card_enlarge_button(target)
        self.assertIn(
            shrink.inner_text().strip(), ("Fokus beenden", "End focus"),
            "Der Karten-Knopf heißt im Fokus nicht „Fokus beenden“ "
            "(B20: „Verkleinern“ entfällt): "
            + repr(shrink.inner_text()))
        shrink.click()
        self.wait_normal(target)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf meldet nach dem Aufheben per "
            "Karten-Knopf nicht aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Der Karten-Knopf meldet nach dem Verkleinern nicht "
            "aria-expanded='false'")

        for session in SESSIONS[1:]:
            self.assertFalse(
                self.is_enlarged(session),
                f"Karte {session} wurde unerwartet vergrößert")
        self.assert_clean_page()

    def test_second_focus_click_restores_normal_mode(self):
        """AK5: Ein zweiter Klick auf denselben Fokus-Knopf hebt den Fokus auf.

        Vorbedingung: Fokus auf Karte A ist aktiv (über den Übersichts-Knopf).
        Aktion: Derselbe Übersichts-Fokus-Knopf wird ein zweites Mal
        ausgelöst; Escape wird bewusst nicht verwendet.
        Erwartung: Karte A ist wieder normal groß, ihr ``.bv-log`` bleibt
        scrollbar (``overflow-y: auto``), ``aria-expanded`` an Übersichts- und
        Karten-Knopf ist wieder ``false`` und es existiert kein unerwarteter
        Scrollbereich.
        Fehlerfall: Der zweite Klick hebt den Fokus nicht auf.
        """
        self.open_six_running()
        self.wait_for_overview(active=6)
        target = SESSIONS[0]
        overview_button = self.focus_button(target).first
        card_button = self.card_enlarge_button(target)

        overview_button.click()
        self.wait_enlarged(target)
        self.assertEqual(
            "true", overview_button.get_attribute("aria-expanded"),
            "Der Übersichts-Fokus-Knopf meldet im Fokus nicht "
            "aria-expanded='true'")

        # Die vergrößerte Karte überdeckt die Übersicht; der zweite Klick
        # auf denselben Knopf löst denselben Handler aus.
        overview_button.evaluate("node => node.click()")
        self.wait_normal(target)
        self.assertEqual(
            "false", overview_button.get_attribute("aria-expanded"),
            "Nach dem zweiten Klick meldet der Übersichts-Fokus-Knopf nicht "
            "aria-expanded='false'")
        self.assertEqual(
            "false", card_button.get_attribute("aria-expanded"),
            "Nach dem zweiten Klick meldet der Karten-Fokus-Knopf nicht "
            "aria-expanded='false'")

        layout = self.layout()
        target_log = next(
            (log for log in layout["logs"] if log["session"] == target), None)
        self.assertIsNotNone(target_log,
                             f"Keine Ausgabefläche für Karte {target}")
        self.assertEqual(
            "auto", target_log["overflowY"],
            "Nach dem zweiten Klick ist die Ausgabefläche nicht mehr "
            "scrollbar: " + repr(target_log))
        self.assert_only_logs_scroll(layout, "Nach dem zweiten Klick")
        self.assert_clean_page()

    def test_main_agent_header_focus_button_enlarges_main_view(self):
        """AK5: Der Fokus-Knopf im Hauptkopf vergrößert die Hauptansicht.

        Vorbedingung: sechs laufende Subagenten, lange Hauptausgabe
        (scrollbar), Viewport 1400×900.
        Aktion: ``button[data-focus-session][aria-label*='fokussieren']``
        innerhalb von ``[data-agent-view][data-role='main']`` klicken;
        Fokus per Escape beenden; erneut fokussieren und per zweitem Klick
        beenden.
        Erwartung: Hauptansicht ``enlarged`` und ≥ 70 % vh / ≥ 60 % vw; ihr
        ``.bv-log`` bleibt scrollbar (``overflow-y: auto``); danach normale
        Größe und weiterhin ``overflow-y: auto``.
        ``aria-expanded`` an diesem Knopf und an der Übersichtszeile des
        Hauptagenten ist ``true`` bzw. ``false``.
        Fehlerfall: Der Knopf im Hauptkopf ist ohne Funktion (belegter Bug im
        aktuellen Arbeitsbaum), der Fokus gilt der falschen Ansicht oder die
        Ausgabe wird abgeschnitten.
        """
        self.open_six_running(main_lines=self.long_main_log())
        self.wait_for_overview(active=6)
        header_button = self.main_focus_button()
        row_button = self.main_overview_focus_button(MAIN_SESSION_ap20)
        self.assertEqual(
            1, header_button.count(),
            "Im Kopf der Hauptagentenansicht fehlt der Fokus-Knopf "
            "button[data-focus-session]")
        self.assertEqual(
            1, row_button.count(),
            "Die Übersichtszeile des Hauptagenten hat keinen Fokus-Knopf")
        self.assertEqual(
            "false", header_button.first.get_attribute("aria-expanded"),
            "Der Haupt-Fokus-Knopf startet nicht mit aria-expanded='false'")
        self.assertEqual(
            "false", row_button.first.get_attribute("aria-expanded"),
            "Die Übersichtszeile des Hauptagenten startet nicht mit "
            "aria-expanded='false'")

        header_button.first.click()
        self.wait_main_enlarged()
        self.assertEqual(
            "true", header_button.first.get_attribute("aria-expanded"),
            "Der Haupt-Fokus-Knopf meldet im Fokus nicht "
            "aria-expanded='true'")
        self.assertEqual(
            "true", row_button.first.get_attribute("aria-expanded"),
            "Die Übersichtszeile des Hauptagenten meldet im Fokus nicht "
            "aria-expanded='true'")

        for session in SESSIONS:
            self.assertFalse(
                self.is_enlarged(session),
                f"Der Haupt-Fokus vergrößerte zusätzlich Karte {session}")

        layout = self.layout()
        main_log = next(
            (log for log in layout["logs"] if log["role"] == "main"), None)
        self.assertIsNotNone(main_log,
                             "Keine Ausgabefläche für den Hauptagenten")
        self.assertEqual(
            "auto", main_log["overflowY"],
            "Die Ausgabefläche des fokussierten Hauptagenten hat overflow-y="
            f"{main_log['overflowY']!r} (erwartet: auto)")
        self.assertGreater(
            main_log["scrollHeight"], main_log["clientHeight"] + 4,
            "Die Ausgabefläche des fokussierten Hauptagenten ist nicht "
            "scrollbar: " + repr(main_log))
        self.assertIn(
            MAIN_SESSION_ap20, self.scroll_sessions(layout),
            "Die Ausgabefläche des Hauptagenten gehört nicht zu den "
            "scrollbaren Bereichen: " + repr(layout["scrollable"]))
        self.assert_only_logs_scroll(layout, "Im Haupt-Fokus")

        self.page.keyboard.press("Escape")
        self.wait_main_normal(timeout=8)
        self.assertEqual(
            "false", header_button.first.get_attribute("aria-expanded"),
            "Nach Escape meldet der Haupt-Fokus-Knopf nicht "
            "aria-expanded='false'")
        self.assertEqual(
            "false", row_button.first.get_attribute("aria-expanded"),
            "Nach Escape meldet die Übersichtszeile des Hauptagenten nicht "
            "aria-expanded='false'")
        layout = self.layout()
        main_log = next(
            (log for log in layout["logs"] if log["role"] == "main"), None)
        self.assertEqual(
            "auto", main_log["overflowY"],
            "Nach dem Beenden des Haupt-Fokus ist die Ausgabefläche nicht "
            "mehr scrollbar: " + repr(main_log))
        self.assert_only_logs_scroll(layout, "Nach dem Beenden des "
                                            "Haupt-Fokus")

        # Zweiter Klick auf denselben Haupt-Fokus-Knopf beendet den Fokus
        # ebenfalls, ohne Escape.
        header_button.first.click()
        self.wait_main_enlarged()
        self.assertEqual(
            "true", row_button.first.get_attribute("aria-expanded"),
            "Die Übersichtszeile des Hauptagenten meldet nach erneutem Fokus "
            "nicht aria-expanded='true'")
        header_button.first.click()
        self.wait_main_normal()
        self.assertEqual(
            "false", header_button.first.get_attribute("aria-expanded"),
            "Nach dem zweiten Klick meldet der Haupt-Fokus-Knopf nicht "
            "aria-expanded='false'")
        self.assertEqual(
            "false", row_button.first.get_attribute("aria-expanded"),
            "Nach dem zweiten Klick meldet die Übersichtszeile des "
            "Hauptagenten nicht aria-expanded='false'")
        self.assert_clean_page()

    def test_session_switch_with_active_focus_keeps_no_orphan_state(self):
        """AK6: Hauptsession-Wechsel bei aktivem Subagenten-Fokus bleibt sauber.

        Vorbedingung: sechs laufende Subagenten; Fokus auf Subagent A ist über
        den Übersichts-Knopf aktiv.
        Aktion: Hauptsession in der Zustandsdatei auf ``NEW_MAIN_SESSION``
        setzen und den Zustand neu laden lassen.
        Erwartung: Kein verwaister Fokus und keine ``enlarged``-Hauptansicht
        der alten Session; die Karte A bleibt die fokussierte scrollbare
        Ausgabefläche; die Übersichtszeile der Hauptsession folgt der neuen
        Kennung und die alte Zeile verschwindet; ``aria-expanded`` bleibt
        konsistent.
        Fehlerfall: Der alte Fokus oder die alte Hauptsession bleibt hängen,
        oder die Ausgabeflächen sind nicht mehr scrollbar.
        """
        self.open_six_running()
        self.wait_for_overview(active=6)
        target = SESSIONS[0]
        self.focus_button(target).first.click()
        self.wait_enlarged(target)

        subs = [self.sub(session) for session in SESSIONS]
        self.write_state(subs, main_session=NEW_MAIN_SESSION)
        self.wait_until(
            lambda: self.agent_view(role="main").first.get_attribute(
                "data-session") == NEW_MAIN_SESSION,
            message="Die Hauptansicht übernahm die neue Session-Kennung nicht")
        self.wait_until(
            lambda: any(row["session"] == NEW_MAIN_SESSION
                        for row in (self.overview().get("rows") or [])),
            message="Die Übersichtszeile der Hauptsession folgt der neuen "
                    "Kennung nicht")
        data = self.wait_for_overview(active=6)
        rows = {row["session"]: row for row in data["rows"]}
        self.assertIn(
            NEW_MAIN_SESSION, rows,
            "Die neue Hauptsession fehlt in der Übersicht: " + repr(rows))
        self.assertNotIn(
            MAIN_SESSION_ap20, rows,
            "Die alte Hauptsession bleibt als verwaiste Zeile in der "
            "Übersicht: " + repr(rows))
        self.assertIn(
            "Main agent", rows[NEW_MAIN_SESSION]["text"],
            "Die neue Hauptzeile nennt den Hauptagenten nicht: "
            + repr(rows[NEW_MAIN_SESSION]["text"]))

        self.assertFalse(
            self.is_main_enlarged(),
            "Die Hauptansicht der alten Session blieb vergrößert")
        self.assertTrue(
            self.is_enlarged(target),
            "Der gültige Fokus auf Subagent A ging beim Hauptsession-Wechsel "
            "verloren")
        layout = self.layout()
        self.assertIn(
            target, self.scroll_sessions(layout),
            "Beim Hauptsession-Wechsel ist die fokussierte Ausgabefläche "
            "nicht mehr scrollbar: " + repr(layout["scrollable"]))
        self.assert_only_logs_scroll(layout, "Beim Hauptsession-Wechsel")
        self.assertEqual(
            "true", self.focus_button(target).first.get_attribute(
                "aria-expanded"),
            "Der Fokus-Knopf von Subagent A meldet nach dem Session-Wechsel "
            "nicht aria-expanded='true'")
        self.assertEqual(
            "false", self.main_overview_focus_button(
                NEW_MAIN_SESSION).first.get_attribute("aria-expanded"),
            "Die neue Hauptzeile meldet fälschlich einen aktiven Fokus")
        self.assert_clean_page()

    def test_zero_running_subagents_shows_empty_overview(self):
        """AK2/AK3: Ohne laufende Subagenten bleibt die Übersicht leer und ruhig.

        Vorbedingung: aktiver Lauf, Hauptlog, Zustandsdatei ohne Subagenten,
        Viewport 1400×900.
        Aktion: Ausgabe öffnen und Übersicht auslesen.
        Erwartung: ``.bv-overview[data-active-agents='0']`` mit sichtbarem
        Leerzustandstext; ``.bv-subs`` ist ausgeblendet; genau eine
        Agentenansicht (Hauptagent); kein unerwarteter Scrollbereich; keine
        JS-Fehler.
        Fehlerfall: Der Leerzustand fehlt, der Subagentenbereich bleibt
        sichtbar oder die Ansicht erzeugt JavaScript-Fehler.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state(subs=[])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_ap20, MAIN_MARKER)
        data = self.wait_for_overview(active=0)

        self.assertEqual(
            "0", data["active"],
            "Die Übersicht meldet ohne Subagenten nicht "
            f"data-active-agents='0': {data!r}")
        self.assertEqual(
            [MAIN_SESSION_ap20], [row["session"] for row in data["rows"]],
            "Ohne Subagenten darf nur die Hauptzeile übrig bleiben: "
            + repr([row["session"] for row in data["rows"]]))
        self.wait_until(
            lambda: self.panel().locator(
                "[data-agent-view][data-role='subagent']").count() == 0,
            message="Ohne laufende Subagenten blieb eine Subagentenansicht "
                    "im DOM")

        subs_box = self.panel().locator(".bv-subs")
        self.assertEqual(
            1, subs_box.count(), "Der Container .bv-subs fehlt")
        self.assertTrue(
            subs_box.first.is_hidden()
            or subs_box.first.get_attribute("hidden") is not None,
            "Der Subagentenbereich .bv-subs ist ohne Subagenten sichtbar")

        empty = self.panel().locator(".bv-overview-empty")
        self.assertEqual(
            1, empty.count(),
            "Die Übersicht hat keinen Leerzustand (.bv-overview-empty)")
        self.assertTrue(
            empty.first.is_visible(),
            "Der Leerzustand der Übersicht ist ohne Subagenten nicht "
            "sichtbar")
        self.assertTrue(
            empty.first.inner_text().strip(),
            "Der Leerzustand der Übersicht enthält keinen Text")

        layout = self.layout()
        self.assert_only_logs_scroll(layout, "Ohne Subagenten")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme, Meilenstein B: Live-Ausgabe mit Attrappe
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

PROJECT = "proj"
MAIN_SESSION_ap22 = "ses_ap22_main"
CHILD_A_ap22 = "ses_ap22_a"
CHILD_B = "ses_ap22_b"
MAIN_MARKER_ap22 = "HAUPT-AP22-4711: Hauptagent schreibt sein Protokoll."
RAW_MARKUP = "<b>not markup</b>"
OUTPUT_A = "AUSGABE-A-AP22-4711: Subagent A arbeitet."
OUTPUT_B = "AUSGABE-B-AP22-4711: Subagent B arbeitet."
STEER_TEXT_ap22 = "Bitte die vollständige Ausgabe zeigen"
TMUX_SESSION = "vibe-" + PROJECT


class AP22FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: liefert keine Agentennachrichten."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/message" in self.path:
            self._send_json(200, {"data": []})
            return
        self._send_json(200, {"ok": True})


class AP22OutputBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Laufregister, Zustandsdatei und tmux-Nachbildung."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — AP22 Test\n\n- [ ] AP22 Ausgabe\n"
            "  Beschreibung: Test\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), AP22FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

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
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            cls.kill_tmux()
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    @classmethod
    def kill_tmux(cls):
        subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "kill-server"],
            env=cls.env, capture_output=True, text=True, timeout=10,
            check=False)

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self.kill_tmux()
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log.state.json").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    def tearDown(self):
        self.page.close()
        self.context.close()
        self.kill_tmux()

    # ---------- Seeds und Helfer ----------

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            request = (
                "POST /api/language HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Token: {self.token}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            conn.sendall(request)
            conn.recv(4096)
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", path)

    def start_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", AGENT,
            "--session", TMUX_SESSION, "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)
        if state == "running":
            self.start_tmux()

    def start_tmux(self):
        result = subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "new-session", "-d",
             "-s", TMUX_SESSION, "sleep", "300"],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                         "tmux-Sitzung konnte nicht angelegt werden: "
                         + result.stdout + result.stderr)
        result = subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "set-environment",
             "-t", TMUX_SESSION, "VIBE_MANAGED", "run"],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                         "tmux-Markierung konnte nicht gesetzt werden: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        (self.log_dir / f"{PROJECT}.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(markers) + "\n",
            encoding="utf-8")

    def sub(self, session, agent, description, output, status="running"):
        return {
            "session": session,
            "agent": agent,
            "description": description,
            "prompt": "Auftrag für " + agent,
            "status": status,
            "started": int(time.time()) + 5,
            "ended": int(time.time()) + 180 if status != "running" else 0,
            "output": output,
        }

    def write_state(self, subs):
        (self.log_dir / f"{PROJECT}.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION_ap22, "subagents": subs},
                       ensure_ascii=False),
            encoding="utf-8")

    def seed_live(self):
        self.start_run("running")
        self.write_log(MAIN_MARKER_ap22, RAW_MARKUP)
        self.write_state([
            self.sub(CHILD_A_ap22, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_output(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/output")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.page.locator("section[data-nv-ppanel='output']")
        panel.wait_for(state="visible", timeout=20000)
        return panel

    def run_state(self):
        pill = self.page.locator("[data-nv-out-main-state]").first
        pill.wait_for(state="visible", timeout=20000)
        state = (pill.get_attribute("data-state") or "").strip().lower()
        text = (pill.inner_text() or "").strip().lower()
        mapping = {"läuft": "running", "gestoppt": "stopped",
                   "running": "running", "stopped": "stopped"}
        return state or mapping.get(text, text)

    def confirm_if_visible(self):
        confirm = self.page.locator(
            "[role='dialog'] button, [data-nv-confirm] button").filter(
                has_text=re.compile(r"stopp|stop|ja|yes", re.I)).first
        if confirm.count() and confirm.is_visible():
            confirm.click()

    def sub_card(self, session):
        return self.page.locator(f"[data-nv-out-sub='{session}']").first

    def focus_marker(self, session):
        return self.page.evaluate(
            """(session) => {
              const card = document.querySelector(
                "[data-nv-out-sub='" + session + "']");
              if (!card) return null;
              const classes = (typeof card.className === 'string'
                ? card.className : '').split(/\\s+/)
                .filter(name => /focus/i.test(name));
              const attrs = Array.from(card.attributes).filter(attribute =>
                /focus/i.test(attribute.name)
                && !['false', '0', ''].includes(attribute.value));
              const expanded = Array.from(card.querySelectorAll('button'))
                .some(button => button.getAttribute('aria-expanded') === 'true'
                  && /fokus|focus/i.test(
                    (button.getAttribute('aria-label') || '')
                    + ' ' + (button.textContent || '')));
              return {classes, attrs: attrs.map(a => a.name), expanded,
                      focused: classes.length > 0 || attrs.length > 0 || expanded};
            }""", session)

    def click_focus(self, session):
        return self.page.evaluate(
            """(session) => {
              const card = document.querySelector(
                "[data-nv-out-sub='" + session + "']");
              if (!card) return false;
              const buttons = Array.from(card.querySelectorAll('button'));
              const target = buttons.find(button => /fokus|focus|zoom|vergröß|enlarge/i
                .test((button.getAttribute('aria-label') || '')
                  + ' ' + (button.textContent || '')));
              if (!target) return false;
              target.click();
              return true;
            }""", session)

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Ausgabeansicht erzeugte JavaScript-Fehler")


class OutputPanelTest(AP22OutputBrowserTest):
    def test_main_and_two_subagent_cards_show_log_text(self):
        """Vorbedingung: laufender Lauf, zwei laufende Subagenten und ein
        Hauptlog mit Markern inklusive ``<b>not markup</b>``.

        Erwartung: Zwei sichtbare Subagenten-Karten, der Hauptbereich ist
        eine Log-Region und zeigt die Zeilen als Text (kein ``<b>``-Element),
        beide Subagenten-Karten existieren mit ihrer Ausgabe.
        """
        self.seed_live()
        self.open_output()

        cards = self.page.locator("div[data-nv-out-subs] [data-nv-out-sub]")
        self.wait_until(
            lambda: cards.count() == 2, timeout=20,
            message="Es sind nicht zwei Subagenten-Karten vorhanden: "
                    + str(cards.count()))
        for index in range(cards.count()):
            self.assertTrue(cards.nth(index).is_visible(),
                            f"Subagenten-Karte {index} ist nicht sichtbar")

        main = self.page.locator("[data-nv-out-main][role='log']")
        main.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: MAIN_MARKER_ap22 in main.evaluate("node => node.textContent"),
            timeout=25,
            message="Der Hauptbereich zeigt das Protokoll nicht")
        content = main.evaluate("node => node.textContent")
        self.assertIn(
            RAW_MARKUP, content,
            "Markup-artiger Protokolltext erscheint nicht als Text")
        self.assertEqual(
            0, main.locator("b").count(),
            "Protokollinhalt wurde als HTML-Markup gerendert")

        for session, marker in ((CHILD_A_ap22, OUTPUT_A), (CHILD_B, OUTPUT_B)):
            with self.subTest(session=session):
                card = self.sub_card(session)
                card.wait_for(state="visible", timeout=20000)
                self.wait_until(
                    lambda card=card, marker=marker: marker in card.inner_text(),
                    timeout=20,
                    message=f"Subagentenkarte {session} zeigt ihre Ausgabe nicht")
        self.assert_clean_page()


class FocusMarkerTest(AP22OutputBrowserTest):
    def test_focus_control_marks_exactly_one_subagent(self):
        """Vorbedingung: zwei laufende Subagenten.

        Aktion: Fokus-Knopf in Karte A klicken.
        Erwartung: Genau eine Karte trägt ein Fokus-Merkmal, und zwar A.
        """
        self.seed_live()
        self.open_output()
        self.sub_card(CHILD_A_ap22).wait_for(state="visible", timeout=20000)
        self.sub_card(CHILD_B).wait_for(state="visible", timeout=20000)

        self.assertTrue(
            self.click_focus(CHILD_A_ap22),
            "In der Subagentenkarte fehlt ein Fokus-Knopf")
        self.wait_until(
            lambda: (self.focus_marker(CHILD_A_ap22) or {}).get("focused") is True,
            timeout=20,
            message="Der Fokus-Knopf setzte kein Fokus-Merkmal an Karte A")
        self.assertFalse(
            (self.focus_marker(CHILD_B) or {}).get("focused"),
            "Karte B trägt gleichzeitig ein Fokus-Merkmal")
        self.assert_clean_page()


class SteerTest(AP22OutputBrowserTest):
    def test_steer_sends_the_instruction_and_reports_the_result(self):
        """Vorbedingung: laufender Lauf.

        Aktion: Anweisung eingeben, ``[data-nv-action="steer"]`` klicken.
        Erwartung: POST ``/api/steer`` mit Projekt und Text; die
        Antwortmeldung erscheint sichtbar.
        """
        self.seed_live()
        self.open_output()
        records = []

        def handler(route):
            records.append(route.request.post_data or "")
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "message": "ANWEISUNG-OK-4711"}))

        self.page.route("**/api/steer", handler)
        steer = self.page.locator("[data-nv-steer]")
        steer.wait_for(state="visible", timeout=20000)
        steer.fill(STEER_TEXT_ap22)
        with self.page.expect_request("**/api/steer", timeout=20000):
            self.page.locator("[data-nv-action='steer']").first.click()
        self.assertEqual(1, len(records), "Es wurde kein /api/steer-POST gesendet")
        payload = json.loads(records[0] or "{}")
        self.assertEqual(PROJECT, payload.get("name"), payload)
        self.assertEqual(STEER_TEXT_ap22, payload.get("text"), payload)
        self.wait_until(
            lambda: "ANWEISUNG-OK-4711" in self.page.locator("#nv-toasts").inner_text(),
            timeout=20,
            message="Die Antwort auf die Anweisung erscheint nicht als Meldung")
        self.assert_clean_page()


class ContinueAvailabilityTest(AP22OutputBrowserTest):
    def test_continue_exists_with_active_run_and_shows_api_message(self):
        """Vorbedingung: laufender Lauf.

        Erwartung: ``[data-nv-action="continue"]`` ist sichtbar; ein Klick
        zeigt die API-Meldung, ohne die Seite zu brechen.
        """
        self.seed_live()
        self.open_output()
        button = self.page.locator("[data-nv-action='continue']")
        button.wait_for(state="visible", timeout=20000)

        self.page.route(
            "**/api/continue",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": False,
                                 "message": "WEITER-AP22-GRENZE"})))
        button.first.click()
        self.wait_until(
            lambda: "WEITER-AP22-GRENZE" in self.page.locator("#nv-toasts").inner_text(),
            timeout=20,
            message="Die API-Meldung zum Fortsetzen erscheint nicht")
        self.assert_clean_page()


class StopTest(AP22OutputBrowserTest):
    def test_stop_is_visible_and_run_state_becomes_stopped(self):
        """Vorbedingung: laufender Lauf mit echter tmux-Sitzung.

        Aktion: ``[data-nv-action="stop"]`` klicken, neu laden.
        Erwartung: ``/api/run-state`` meldet keinen laufenden Lauf mehr und
        die Lauf-Pille zeigt ``stopped``.
        """
        self.seed_live()
        self.open_output()
        stop = self.page.locator("[data-nv-action='stop']")
        stop.wait_for(state="visible", timeout=20000)
        stop.first.click()
        self.confirm_if_visible()
        self.wait_until(
            lambda: self.api_json(
                f"/api/run-state?name={PROJECT}").get("running") is False,
            timeout=30,
            message="Der Lauf wurde durch Stop nicht beendet")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "stopped", self.run_state(),
            "Die Lauf-Pille meldet nach dem Stop nicht stopped")
        self.assertFalse(
            self.page.locator("[data-nv-action='stop']").is_visible(),
            "Der Stop-Knopf bleibt bei gestopptem Lauf sichtbar")
        self.assert_clean_page()


class LegacyLogTest(AP22OutputBrowserTest):
    def test_output_without_live_run_shows_log_tail(self):
        """Vorbedingung: kein Lauf im Register, aber ein Protokoll.

        Erwartung: Die Ausgabe zeigt die letzten Protokollzeilen und erzeugt
        keine JavaScript-Fehler.
        """
        marker = "NACHLESE-AP22-4711: letzte Zeile ohne Lauf."
        self.write_log(MAIN_MARKER_ap22, marker)
        self.open_output()
        panel = self.page.locator("section[data-nv-ppanel='output']")
        self.wait_until(
            lambda: marker in panel.inner_text(),
            timeout=25,
            message="Die Ausgabe ohne laufenden Lauf zeigt die Protokollzeilen nicht")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme (Teil 2): vollständig neu gebaute Ausgabeansicht
# ===========================================================================

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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


MAIN_SESSION_b11 = "ses_main_b11"
CHILD_A_b11 = "ses_kind_a"
CHILD_B_b11 = "ses_kind_b"
MAIN_MARKER_b11 = "HAUPT-B11-4711: Hauptagent schreibt sein Protokoll."
MAIN_LIVE = "HAUPT-LIVE-4711: neue Hauptzeile."
OUTPUT_A_b11 = "AUSGABE-A-4711: Subagent A arbeitet."
OUTPUT_A_LIVE = "A-LIVE-4711: A hat weitergeschrieben."
OUTPUT_B_b11 = "AUSGABE-B-4711: Subagent B arbeitet."
STEER_TEXT_b11 = "Bitte die vollständige Ausgabe zeigen"

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

    def write_state(self, subs, main_session=MAIN_SESSION_b11):
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
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        tabs = self.page.locator(
            "[aria-label='Project sections'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Project sections'] button[role=tab]")
        out_tab = tabs.filter(has_text="Output").first
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
        select = self.panel().locator("select[aria-label='Target']")
        self.assertGreater(
            select.count(), 0,
            "Keine Zielauswahl (select[aria-label='Target']) gefunden")
        return select.first

    def target_sessions(self):
        return self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] select[aria-label='Target'] option",
            "options => options.map(option => option.value)")

    def steer_textarea(self):
        area = self.panel().locator("textarea[aria-label*='Zusatzanweisung'], textarea[aria-label*='Additional instruction']")
        self.assertGreater(
            area.count(), 0,
            "Keine Anweisungseingabe (textarea mit aria-label "
            "'Zusatzanweisung') gefunden")
        return area.first

    def steer_send_button(self):
        button = self.panel().locator("button").filter(
            has_text=re.compile("senden|Send", re.I)).first
        self.assertGreater(
            button.count(), 0, "Kein Senden-Knopf gefunden")
        return button

    def continue_button(self):
        return self.panel().locator("button").filter(
            has_text=re.compile(r"^Resume$")).first

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
        self.write_log(MAIN_MARKER_b11)
        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
        ])
        self.open_detail()
        self.open_output()

        main_view = self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)
        view_a = self.wait_for_view("subagent", CHILD_A_b11, OUTPUT_A_b11)
        view_b = self.wait_for_view("subagent", CHILD_B_b11, OUTPUT_B_b11)

        self.assertTrue(main_view.is_visible(), "Hauptagent ist nicht sichtbar")
        self.assertTrue(view_a.is_visible(), "Subagent A ist nicht sichtbar")
        self.assertTrue(view_b.is_visible(), "Subagent B ist nicht sichtbar")

        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11 + "\n" + OUTPUT_A_LIVE),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
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
        self.write_log(MAIN_MARKER_b11)
        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)
        self.wait_for_view("subagent", CHILD_A_b11, OUTPUT_A_b11)
        self.wait_for_view("subagent", CHILD_B_b11, OUTPUT_B_b11)

        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11,
                     status="completed"),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
        ])

        self.wait_until(
            lambda: self.agent_view(session=CHILD_A_b11).count() == 0
            or not self.agent_view(session=CHILD_A_b11).first.is_visible(),
            timeout=20,
            message="Der abgeschlossene Subagent A blieb in der Ansicht")
        self.assertTrue(self.agent_view(session=CHILD_B_b11).first.is_visible(),
                        "Subagent B verschwand mit A")
        self.assertTrue(
            self.agent_view(role="main").first.is_visible(),
            "Der Hauptagent verschwand mit dem Subagenten")
        self.assert_clean_page()


class SteerTargetTest(B11OutputBrowserTest):
    def seed(self):
        self.register_run("running")
        self.write_log(MAIN_MARKER_b11)
        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)
        self.wait_for_view("subagent", CHILD_A_b11, OUTPUT_A_b11)
        self.wait_for_view("subagent", CHILD_B_b11, OUTPUT_B_b11)
        self.wait_until(
            lambda: {MAIN_SESSION_b11, CHILD_A_b11, CHILD_B_b11}
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

        select.select_option(MAIN_SESSION_b11)
        textarea.fill(STEER_TEXT_b11)
        request = self.post_request("/api/steer", send.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual("proj", payload.get("name"), payload)
        self.assertEqual(MAIN_SESSION_b11, payload.get("session"), payload)
        self.assertEqual(STEER_TEXT_b11, payload.get("text"), payload)

        select.select_option(CHILD_A_b11)
        textarea.fill(STEER_TEXT_b11)
        request = self.post_request("/api/steer", send.click)
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(CHILD_A_b11, payload.get("session"),
                         "Anweisung ging nicht an den gewählten Subagenten: "
                         + repr(payload))
        self.assertEqual(STEER_TEXT_b11, payload.get("text"), payload)
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
        self.assertIn(after, {MAIN_SESSION_b11, CHILD_A_b11, CHILD_B_b11},
                      "Unerwartetes Tastaturziel: " + after)

        textarea = self.steer_textarea()
        textarea.focus()
        self.page.keyboard.type(STEER_TEXT_b11)
        send = self.steer_send_button()
        request = self.post_request(
            "/api/steer",
            lambda: (send.focus(), self.page.keyboard.press("Enter")))
        payload = json.loads(request.post_data or "{}")
        self.assertEqual(after, payload.get("session"),
                         "Enter sendete nicht an das gewählte Ziel: " + repr(payload))
        self.assertEqual(STEER_TEXT_b11, payload.get("text"), payload)

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
        self.write_log(MAIN_MARKER_b11)
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
        self.write_log(MAIN_MARKER_b11)
        self.write_state([])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)

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
        self.write_log(MAIN_MARKER_b11)
        self.write_state([
            self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11),
            self.sub(CHILD_B_b11, "testerB", "Auftrag B", OUTPUT_B_b11),
        ])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)
        self.wait_for_view("subagent", CHILD_A_b11, OUTPUT_A_b11)
        self.wait_for_view("subagent", CHILD_B_b11, OUTPUT_B_b11)

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
        self.write_log(MAIN_MARKER_b11)
        self.write_state([self.sub(CHILD_A_b11, "testerA", "Auftrag A", OUTPUT_A_b11)])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION_b11, MAIN_MARKER_b11)

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


# ===========================================================================
# Browserabnahme, Ausgabe (2p, korrigiert)
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


MAIN_SESSION_f33 = "ses_f33_main"
CHILD_SESSION = "ses_f33_child"
MAIN_MARKER_f33 = "HAUPT-F33-4711: Hauptagent schreibt sein Protokoll."
SUB_MARKER = "SUB-F33-4711: Der Subagent schreibt seine Ausgabe."
LONG_TOKEN = "X" * 400
STEER_TEXT_f33 = "Bitte die vollständige Ausgabe zeigen"
SUB_STEER_TEXT = "Bitte nur die Tests ausführen"

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/tester-modell\\n'
    exit 0
    ;;
esac
exit 2
"""


class F33FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: keine Agentennachrichten."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"data": []})


class F33OutputBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Laufregister und Zustandsdatei für die Ausgabe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] F1 Ausgabe\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), F33FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

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
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
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
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Umgebung je Test ----------

    def setUp(self):
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log.state.json").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self.post_requests.append(request)
            if request.method == "POST" else None)

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Seeds und Helfer ----------

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            request = (
                "POST /api/language HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Token: {self.token}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            conn.sendall(request)
            conn.recv(4096)
        finally:
            conn.close()

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", AGENT,
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        lines = ["=== Agentenlauf proj ==="] + list(markers)
        # Genug Zeilen, damit der Steuerblock am Seitenende ohne Scrollen
        # nicht mehr erreichbar wäre. Bewusst unter dem SSE-Tail von 80
        # Zeilen, damit die Marker im gerenderten Protokoll ankommen.
        lines += ["Protokollzeile %03d mit etwas Text." % index
                  for index in range(60)]
        (self.log_dir / f"{PROJECT}.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def write_state(self):
        entry = {
            "session": CHILD_SESSION,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Auftrag für tester",
            "status": "running",
            "started": int(time.time()) + 5,
            "ended": 0,
            "output": SUB_MARKER + " " + LONG_TOKEN,
        }
        (self.log_dir / f"{PROJECT}.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION_f33, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")

    def seed_live(self):
        self.register_run("running")
        self.write_log(MAIN_MARKER_f33 + " " + LONG_TOKEN)
        self.write_state()

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_output(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/output")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.page.locator("section[data-nv-ppanel='output']")
        panel.wait_for(state="visible", timeout=20000)
        self.page.locator("section[data-nv-out-main-wrap]").wait_for(
            state="visible", timeout=20000)
        return panel

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def enlarged_state(self):
        return self.page.evaluate(
            """() => {
              const nodes = Array.from(
                document.querySelectorAll('.nv-out-enlarged'));
              const main = document.querySelector('[data-nv-out-main]');
              return {
                count: nodes.length,
                holdsMain: nodes.some(node =>
                  node === main || (main && node.contains(main))),
                fixed: nodes.length
                  ? getComputedStyle(nodes[0]).position : '',
                rect: nodes.length
                  ? nodes[0].getBoundingClientRect().toJSON() : null,
                bodyOverflow: getComputedStyle(document.body).overflow,
                htmlOverflow: getComputedStyle(document.documentElement).overflow,
              };
            }""")

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Ausgabeansicht erzeugte JavaScript-Fehler")


class FocusTest(F33OutputBrowserTest):
    def test_main_output_focus_enlarges_and_escape_restores(self):
        """Vorbedingung: laufender Lauf mit Hauptausgabe.

        Aktion: ``button[data-nv-action="out-focus"]`` klicken, danach Escape.
        Erwartung: ``aria-expanded`` false → true; genau ein Element trägt
        ``.nv-out-enlarged``, enthält die Hauptausgabe, ist ``fixed`` und
        mindestens Viewport − 32 px groß; Escape entfernt den Zustand und
        setzt ``aria-expanded`` zurück.
        """
        self.seed_live()
        self.open_output()
        button = self.page.locator("button[data-nv-action='out-focus']")
        button.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", button.get_attribute("aria-expanded"),
                         "Der Fokus-Knopf meldet nicht aria-expanded=false")
        button.click()
        self.wait_until(
            lambda: self.enlarged_state()["count"] == 1, timeout=20,
            message="Der Fokus-Knopf vergrößert die Hauptausgabe nicht "
                    "(.nv-out-enlarged fehlt)")
        state = self.enlarged_state()
        self.assertTrue(state["holdsMain"],
                        "Die vergrößerte Fläche enthält nicht die Hauptausgabe")
        self.assertEqual("fixed", state["fixed"],
                         "Die vergrößerte Ausgabe ist nicht fixiert")
        self.assertGreaterEqual(state["rect"]["width"], 1400 - 32,
                                "Die vergrößerte Ausgabe füllt die Breite nicht")
        self.assertGreaterEqual(state["rect"]["height"], 1000 - 32,
                                "Die vergrößerte Ausgabe füllt die Höhe nicht")
        self.assertIn(state["bodyOverflow"], ("hidden", "clip"),
                      "Der Body scrollt im vergrößerten Zustand weiter mit")
        self.assertEqual("true", button.get_attribute("aria-expanded"),
                         "Der Fokus-Knopf meldet den Zustand nicht")
        self.page.keyboard.press("Escape")
        self.wait_until(
            lambda: self.enlarged_state()["count"] == 0, timeout=15,
            message="Escape beendet die Vergrößerung nicht")
        self.assertEqual("false", button.get_attribute("aria-expanded"),
                         "Escape setzt aria-expanded nicht zurück")
        self.assert_clean_page()

    def test_second_click_leaves_the_focus_state(self):
        """Vorbedingung: Hauptausgabe sichtbar.

        Aktion: Fokus-Knopf zweimal klicken.
        Erwartung: Der erste Klick vergrößert, der zweite Klick stellt den
        Normalzustand wieder her (kein ``.nv-out-enlarged``).
        """
        self.seed_live()
        self.open_output()
        button = self.page.locator("button[data-nv-action='out-focus']")
        button.wait_for(state="visible", timeout=20000)
        button.click()
        self.wait_until(
            lambda: self.enlarged_state()["count"] == 1, timeout=20,
            message="Der erste Klick vergrößert die Ausgabe nicht")
        button.click()
        self.wait_until(
            lambda: self.enlarged_state()["count"] == 0, timeout=15,
            message="Der erneute Klick beendet die Vergrößerung nicht")
        self.assert_clean_page()


class ControlsPlacementTest(F33OutputBrowserTest):
    def test_steer_block_sits_directly_under_the_status_line(self):
        """Vorbedingung: laufender Lauf, langes Hauptprotokoll.

        Erwartung: Statuszeile → Steuerblock → Protokoll in dieser
        Reihenfolge; ``input[data-nv-steer]`` sowie die Aktionen
        ``steer``/``continue``/``stop`` sind sichtbar und liegen beim Öffnen
        ohne Scrollen im Viewport (``position: sticky``).
        """
        self.seed_live()
        self.open_output()
        controls = self.page.locator(".nv-out-controls, [data-nv-steer]")
        controls.first.wait_for(state="visible", timeout=20000)
        order = self.page.evaluate(
            """() => {
              const statusLine = document.querySelector('[data-nv-out-summary]');
              const main = document.querySelector('[data-nv-out-main]');
              const steer = document.querySelector('[data-nv-steer]');
              if (!statusLine || !main || !steer) return null;
              let block = steer;
              while (block && block !== document.body
                     && !block.querySelector('[data-nv-action="continue"]')) {
                block = block.parentElement;
              }
              if (!block || block === document.body) return null;
              return {
                followsStatusLine: (statusLine.compareDocumentPosition(block)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
                beforeLog: (block.compareDocumentPosition(main)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
                rect: block.getBoundingClientRect().toJSON(),
                position: getComputedStyle(block).position,
              };
            }""")
        self.assertIsNotNone(
            order, "Der Steuerblock (Steer/Fortsetzen/Stoppen) wurde nicht "
                   "gefunden")
        self.assertTrue(order["followsStatusLine"],
                        "Der Steuerblock steht nicht unter der Statuszeile")
        self.assertTrue(order["beforeLog"],
                        "Der Steuerblock steht unter dem Protokoll statt "
                        "darüber")
        self.assertEqual("sticky", order["position"],
                         "Der Steuerblock ist nicht sticky")
        self.assertGreaterEqual(order["rect"]["y"], 0,
                                "Der Steuerblock liegt oberhalb des Viewports")
        self.assertLess(
            order["rect"]["y"] + order["rect"]["height"], 1000,
            "Der Steuerblock ist beim Öffnen nicht ohne Scrollen erreichbar")
        for selector in ("input[data-nv-steer]",
                         "[data-nv-action='steer']",
                         "[data-nv-action='continue']",
                         "[data-nv-action='stop']"):
            with self.subTest(control=selector):
                node = self.page.locator(selector)
                self.assertEqual(1, node.count(), f"{selector} fehlt")
                self.assertTrue(node.first.is_visible(),
                                f"{selector} ist nicht sichtbar")
        self.assert_clean_page()


class SubagentSteerTest(F33OutputBrowserTest):
    def test_running_card_sends_session_with_the_instruction(self):
        """Vorbedingung: laufender Subagent ``ses_f33_child``.

        Aktion: ``input[data-nv-sub-steer]`` füllen,
        ``button[data-nv-sub-steer-send]`` klicken.
        Erwartung: POST ``/api/steer`` mit ``name``, ``text`` und
        ``session="ses_f33_child"``; die Karte ist die laufende Karte.
        """
        self.seed_live()
        self.open_output()
        card = self.page.locator(
            f"[data-nv-out-sub='{CHILD_SESSION}']")
        card.wait_for(state="visible", timeout=20000)
        field = card.locator("input[data-nv-sub-steer]")
        field.wait_for(state="visible", timeout=20000)
        send = card.locator("button[data-nv-sub-steer-send]")
        self.assertEqual(1, send.count(),
                         "Der Senden-Knopf der Subagenten-Anweisung fehlt")
        self.assertTrue(send.is_visible(),
                        "Der Senden-Knopf ist nicht sichtbar")
        field.fill(SUB_STEER_TEXT)
        records = []

        def handler(route):
            records.append(route.request.post_data or "")
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "message": "SUB-STEER-OK-4711"}))

        self.page.route("**/api/steer", handler)
        send.click()
        self.wait_until(
            lambda: len(records) >= 1, timeout=20,
            message="Die Subagenten-Anweisung sendet kein /api/steer")
        payload = json.loads(records[0] or "{}")
        self.assertEqual(PROJECT, payload.get("name"), payload)
        self.assertEqual(SUB_STEER_TEXT, payload.get("text"), payload)
        self.assertEqual(CHILD_SESSION, payload.get("session"), payload)
        self.assert_clean_page()


class LogOverflowTest(F33OutputBrowserTest):
    def test_logs_wrap_without_horizontal_overflow(self):
        """Vorbedingung: Haupt- und Subagenten-Protokoll mit langem Token.

        Erwartung: ``.nv-log`` bricht Zeilen um (``white-space: pre-wrap``);
        weder Haupt- noch Subagenten-Protokoll laufen horizontal über
        (``scrollWidth <= clientWidth``).
        """
        self.seed_live()
        self.open_output()
        main = self.page.locator("[data-nv-out-main]")
        main.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: LONG_TOKEN[:40] in (main.inner_text() or ""),
            timeout=25, message="Das Hauptprotokoll zeigt den langen Text nicht")
        sub = self.page.locator(
            f"[data-nv-out-sub='{CHILD_SESSION}'] .nv-log")
        sub.wait_for(state="visible", timeout=20000)
        for name, node in (("Hauptprotokoll", main), ("Subagentenprotokoll", sub)):
            with self.subTest(log=name):
                metrics = node.evaluate(
                    """node => ({
                      whiteSpace: getComputedStyle(node).whiteSpace,
                      clientWidth: node.clientWidth,
                      scrollWidth: node.scrollWidth,
                    })""")
                self.assertIn(
                    metrics["whiteSpace"], ("pre-wrap", "break-spaces"),
                    f"{name} bricht Zeilen nicht um: {metrics}")
                self.assertLessEqual(
                    metrics["scrollWidth"], metrics["clientWidth"] + 1,
                    f"{name} läuft horizontal über: {metrics}")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme, Ausgabe
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


MAIN_AGENT = "tester-main"
MAIN_SESSION_f34 = "ses_f34_main"
SUB_A = "ses_f34_a"
SUB_B = "ses_f34_b"
SUB_C = "ses_f34_c"
SUB_D = "ses_f34_d"
SUB_E = "ses_f34_e"
SUB_F = "ses_f34_f"
PKG_ID = "F34-Ticket-4711"
SES_RESUME = "ses_f34_resume"
MAIN_MARKER_f34 = "HAUPT-F34: Hauptagent schreibt sein Protokoll."


class F34FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: liefert keine Agentennachrichten."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"data": []})


class F34OutputBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Laufregister und Zustandsdatei für die Ausgabe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] F1 Ausgabe\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), F34FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

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
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
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
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Umgebung je Test ----------

    def setUp(self):
        for name in ("runs.json", f"{PROJECT}.log",
                     f"{PROJECT}.log.state.json", "sessions.json"):
            (self.log_dir / name).unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.post_language("de")
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Seeds und Helfer ----------

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            request = (
                "POST /api/language HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Token: {self.token}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            conn.sendall(request)
            conn.recv(4096)
        finally:
            conn.close()

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", MAIN_AGENT,
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        lines = ["=== Agentenlauf proj ==="] + list(markers)
        lines += ["Protokollzeile %03d mit etwas Text." % index
                  for index in range(60)]
        (self.log_dir / f"{PROJECT}.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def seed_subs(self, subs):
        """subs: Liste von (session, agent, description, output)."""
        entries = []
        for session, agent, description, output in subs:
            entries.append({
                "session": session,
                "agent": agent,
                "description": description,
                "prompt": "Auftrag für " + agent,
                "status": "running",
                "started": int(time.time()) + 5,
                "ended": 0,
                "output": output,
            })
        (self.log_dir / f"{PROJECT}.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION_f34, "subagents": entries},
                       ensure_ascii=False),
            encoding="utf-8")

    def seed_subs_ab(self):
        self.seed_subs([
            (SUB_A, "testerA", "Auftrag A",
             "AUSGABE-A-F34: Subagent testerA arbeitet."),
            (SUB_B, "testerB", "Auftrag B",
             "AUSGABE-B-F34: Subagent testerB arbeitet."),
        ])

    def seed_live(self):
        self.register_run("running")
        self.write_log(MAIN_MARKER_f34)
        self.seed_subs_ab()

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_output(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/output")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.page.locator("section[data-nv-ppanel='output']")
        panel.wait_for(state="visible", timeout=20000)
        self.page.locator("section[data-nv-out-main-wrap]").wait_for(
            state="visible", timeout=20000)
        return panel

    def card(self, session):
        return self.page.locator(f"[data-nv-out-sub='{session}']").first

    def set_viewport(self, width, height):
        """Ersetzt Kontext und Seite durch ein Kontext-Setup mit anderem
        Viewport (Playwright 1.65 hat ``BrowserContext.set_viewport_size``
        nicht)."""
        self.page.close()
        self.context.close()
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def summary_row(self, target):
        return self.page.locator(
            f"[data-nv-out-summary-row][data-nv-summary-target='{target}']").first

    def visible_in_viewport(self, node):
        box = node.bounding_box()
        if box is None:
            return False
        height = self.page.evaluate("() => window.innerHeight")
        return box["y"] >= -1 and box["y"] + box["height"] <= height + 1

    def parse_limit(self, node, viewport, factor, label):
        """Inline-``max-height`` (px/vh) gegen ``factor * viewport`` prüfen."""
        metrics = node.evaluate(
            "node => ({inline: node.style.maxHeight || '',"
            " overflow: getComputedStyle(node).overflowX})")
        match = re.match(r"^(-?[\d.]+)(px|vh)$", metrics["inline"] or "")
        self.assertIsNotNone(
            match, f"Inline-Max-Height fehlt ({label}): {metrics!r}")
        value = float(match.group(1))
        if match.group(2) == "vh":
            self.assertLessEqual(value / 100 * viewport,
                                 viewport * factor + 1,
                                 f"{label}: max-height {metrics['inline']} "
                                 f"überschreitet {factor * 100:.0f}vh")
        else:
            self.assertLessEqual(value, viewport * factor + 1,
                                 f"{label}: max-height {metrics['inline']} "
                                 f"überschreitet {factor * 100:.0f}vh")
        self.assertIn(metrics["overflow"], ("auto", "scroll"),
                      f"{label}: kein eigenes Scroll (overflow: "
                      f"{metrics['overflow']})")

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Ausgabeansicht erzeugte JavaScript-Fehler")


class SummaryTest(F34OutputBrowserTest):
    def test_summary_rows_show_main_and_subagent_meta(self):
        """Vorbedingung: laufender Lauf mit Hauptlog, Subagenten A/B.

        Aktion: ``div[data-nv-out-summary]`` zeit die Hauptzeile und die
        Zeile je Subagenten.
        Erwartung: Hauptzeile: Name ``tester-main``, Rolle/Agent
        ``Hauptagent``, Zustand ``läuft``, Modell-Element (Title ``Modell``),
        Sitzung ``ses_f34_main``; Subagentenzeile A: Name ``testerA``, Rolle
        ``Auftrag A``, Zustand ``läuft``, Sitzung ``ses_f34_a`` (Title =
        voller Session-Name).
        """
        self.seed_live()
        self.open_output()
        summary = self.page.locator("div[data-nv-out-summary]").first
        summary.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: summary.locator("[data-nv-out-summary-row]").count() >= 3,
            timeout=20,
            message="Die Kopfzusammenfassung hat die Zeilen nicht geladen")

        main_row = self.summary_row("main")
        main_row.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: main_row.locator("b.nv-out-sum-name").count() == 1
            and main_row.locator("b.nv-out-sum-name").first.inner_text()
            == MAIN_AGENT,
            timeout=20,
            message="Hauptzeile meldet anderen Agenten: "
                    + repr(main_row.inner_text() or ""))
        self.assertEqual(
            MAIN_AGENT, main_row.locator("b.nv-out-sum-name").first.inner_text())
        self.assertEqual("Hauptagent",
                         main_row.locator("span.nv-out-sum-role").first
                         .inner_text())
        state = main_row.locator("span[data-state]").first
        self.wait_until(
            lambda: state.get_attribute("data-state") == "running"
            and state.inner_text() == "läuft",
            timeout=20, message="Hauptzeile meldet nicht Zustand läuft")
        model = main_row.locator("span[title='Modell']")
        self.assertEqual(1, model.count(), "Hauptzeile fehlt das Modell-Element")
        self.assertTrue(model.first.is_visible())
        session = main_row.locator("code.nv-out-sum-session").first
        self.assertEqual(MAIN_SESSION_f34, session.inner_text())
        self.assertEqual(MAIN_SESSION_f34, session.get_attribute("title"))

        sub_row = self.summary_row(SUB_A)
        sub_row.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: sub_row.locator("b.nv-out-sum-name").first.inner_text()
            == "testerA",
            timeout=20, message="Subagentenzeile meldet anderen Agenten")
        self.assertEqual("Auftrag A",
                         sub_row.locator("span.nv-out-sum-role").first
                         .inner_text())
        sub_state = sub_row.locator("span[data-state]").first
        self.assertEqual("running", sub_state.get_attribute("data-state"))
        self.assertEqual("läuft", sub_state.inner_text())
        sub_model = sub_row.locator("span[title='Modell']")
        self.assertEqual(1, sub_model.count())
        self.assertTrue(sub_model.first.is_visible())
        sub_session = sub_row.locator("code.nv-out-sum-session").first
        self.assertEqual(SUB_A, sub_session.inner_text())
        self.assertEqual(SUB_A, sub_session.get_attribute("title"))
        self.assert_clean_page()

    def test_summary_click_focuses_and_scrolls_to_card(self):
        """Vorbedingung: laufender Lauf, Subagenten A/B (2 Zeilen in Summen).

        Aktion: Klick auf die Zeile für ``ses_f34_a``.
        Erwartung: Karte A trägt Fokus (``data-focus="true"``), Karte B
        ``data-focus="false"``; Karte A ist im Viewport (fokussiert/
        gescrollt).
        """
        self.seed_live()
        self.open_output()
        card_a = self.card(SUB_A)
        card_a.wait_for(state="visible", timeout=20000)
        summary = self.page.locator("div[data-nv-out-summary]").first
        summary.wait_for(state="visible", timeout=20000)
        self.summary_row(SUB_A).click()
        self.wait_until(
            lambda: card_a.get_attribute("data-focus") == "true",
            timeout=20,
            message="Die Zusammenfassungszeile setzt keinen Fokus an Karte A")
        card_b = self.card(SUB_B)
        card_b.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", card_b.get_attribute("data-focus"),
                         "Karte B trägt gleichzeitig den Fokus")
        self.wait_until(
            lambda: self.visible_in_viewport(card_a),
            timeout=20,
            message="Die fokussierte Karte ist nach dem Klick nicht im "
                    "Viewport sichtbar")
        self.assert_clean_page()


class SummaryOverflowTest(F34OutputBrowserTest):
    def test_summary_scrolls_horizontally_not_the_page(self):
        """Vorbedingung: 6 laufende Subagenten (a..f).

        Erwartung: ``div[data-nv-out-summary]`` scrollt horizontal
        (``overflow-x`` auto/scroll); die Seite läuft nicht horizontal über
        (``documentElement.scrollWidth <= clientWidth + 2``).
        """
        subs = [
            (session, f"tester{name.upper()}", f"Auftrag {name}",
             f"AUSGABE-{name}-F34: Subagent arbeitet.")
            for name, session in (
                ("a", SUB_A), ("b", SUB_B), ("c", SUB_C),
                ("d", SUB_D), ("e", SUB_E), ("f", SUB_F))
        ]
        self.seed_subs(subs)
        self.register_run("running")
        self.write_log(MAIN_MARKER_f34)
        self.open_output()
        summary = self.page.locator("div[data-nv-out-summary]").first
        summary.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: summary.locator("[data-nv-out-summary-row]").count() >= 7,
            timeout=20, message="Nicht alle Zusammenfassungszeilen geladen")
        metrics = self.page.evaluate(
            """() => ({
              overflowX: getComputedStyle(
                document.querySelector('[data-nv-out-summary]')).overflowX,
              docScrollWidth: document.documentElement.scrollWidth,
              docClientWidth: document.documentElement.clientWidth,
            })""")
        self.assertIn(metrics["overflowX"], ("auto", "scroll"),
                      f"Die Summen scrollt nicht horizontal: {metrics}")
        self.assertLessEqual(
            metrics["docScrollWidth"], metrics["docClientWidth"] + 2,
            f"Die Seite läuft horizontal über: {metrics}")
        self.assert_clean_page()


class MainCardTest(F34OutputBrowserTest):
    def test_main_card_structure(self):
        """Vorbedingung: laufender Lauf mit Hauptlog.

        Erwartung: ``section[data-nv-out-main-wrap]`` hat Titel ``Hauptagent``,
        Zustand ``läuft``, Sitzung ``ses_f34_main``; Fokus-Knopf
        ``button[data-nv-action="out-focus"]`` mit Icon (``.nv-out-icon``)
        UND sichtbarem Text (``Fokus``), ``aria-expanded="false"``; Log
        ``pre[data-nv-out-main]`` mit ``max-height <= 60vh`` und eigenem
        Scroll (``overflowX`` auto/scroll); ``button[data-nv-log-expand][data-nv-log-target=
        "main"]`` sichtbar, ``aria-expanded="false"``, Text ``Alles anzeigen``.
        """
        self.seed_live()
        self.open_output()
        main_wrap = self.page.locator("section[data-nv-out-main-wrap]").first
        main_wrap.wait_for(state="visible", timeout=20000)
        head = main_wrap.locator("div.nv-out-main-head").first
        head.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: head.locator("b").count() == 1
            and head.locator("b").first.inner_text() == "Hauptagent",
            timeout=20, message="Head-Titel meldet: "
                                + repr(head.inner_text() or ""))
        state = main_wrap.locator("[data-nv-out-main-state]").first
        state.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: state.get_attribute("data-state") == "running"
            and state.inner_text() == "läuft",
            timeout=20, message="Hauptzustand meldet nicht läuft")
        session = main_wrap.locator("code[data-nv-out-session]").first
        self.assertEqual(MAIN_SESSION_f34, session.inner_text())
        self.assertEqual(MAIN_SESSION_f34, session.get_attribute("title"))

        focus = main_wrap.locator("button[data-nv-action='out-focus']").first
        focus.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", focus.get_attribute("aria-expanded"),
                         "Der Fokus-Knopf meldet nicht aria-expanded=false")
        self.assertEqual(1, focus.locator(".nv-out-icon").count(),
                         "Der Fokus-Knopf hat kein Icon")
        self.assertTrue(focus.locator(".nv-out-icon").first.is_visible())
        self.assertIn("Fokus", focus.inner_text(),
                      "Der Fokus-Knopf hat keinen sichtbaren Text")

        log = main_wrap.locator("pre[data-nv-out-main]").first
        log.wait_for(state="visible", timeout=20000)
        self.parse_limit(log, self.page.evaluate("() => window.innerHeight"),
                         0.6, "Hauptprotokoll")

        expand = main_wrap.locator(
            "button[data-nv-log-expand][data-nv-log-target='main']").first
        expand.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", expand.get_attribute("aria-expanded"))
        self.assertIn("Alles anzeigen", expand.inner_text())
        self.assert_clean_page()

    def test_main_focus_and_expand_toggle(self):
        """Vorbedingung: laufender Lauf mit Hauptlog.

        Aktion: ``button[data-nv-action="out-focus"]`` klicken, erneut; dann
        ``button[data-nv-log-expand][data-nv-log-target="main"]`` klicken,
        erneut.
        Erwartung: Fokus-Knopf wechselt ``aria-expanded`` false → true →
        false, zwischen „Fokus" und „Fokus aufheben"; Expand-Knopf wechselt
        ``aria-expanded`` false → true → false, zwischen „Alles anzeigen"
        und „Weniger anzeigen".
        """
        self.seed_live()
        self.open_output()
        main_wrap = self.page.locator("section[data-nv-out-main-wrap]").first
        main_wrap.wait_for(state="visible", timeout=20000)
        focus = main_wrap.locator("button[data-nv-action='out-focus']").first
        focus.wait_for(state="visible", timeout=20000)
        focus.click()
        self.wait_until(
            lambda: focus.get_attribute("aria-expanded") == "true",
            timeout=20,
            message="Der Fokus-Knopf meldet nicht aria-expanded=true")
        self.assertIn("Fokus aufheben", focus.inner_text())
        focus.click()
        self.wait_until(
            lambda: focus.get_attribute("aria-expanded") == "false",
            timeout=20,
            message="Der Fokus-Knopf meldet nicht zurück auf aria-expanded=false")
        self.assertIn("Fokus", focus.inner_text())

        expand = main_wrap.locator(
            "button[data-nv-log-expand][data-nv-log-target='main']").first
        expand.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", expand.get_attribute("aria-expanded"))
        expand.click()
        self.wait_until(
            lambda: expand.get_attribute("aria-expanded") == "true",
            timeout=20,
            message="Der Expand-Knopf meldet nicht aria-expanded=true")
        self.assertIn("Weniger anzeigen", expand.inner_text())
        expand.click()
        self.wait_until(
            lambda: expand.get_attribute("aria-expanded") == "false",
            timeout=20,
            message="Der Expand-Knopf meldet nicht auf aria-expanded=false zurück")
        self.assertIn("Alles anzeigen", expand.inner_text())
        self.assert_clean_page()


class SubGridTest(F34OutputBrowserTest):
    def test_cards_form_two_column_grid_at_1200px(self):
        """Vorbedingung: Viewport ≥ 1200 px, laufende Subagenten A/B.

        Erwartung: Hauptkarte und beide Subagenten-Karten liegen im selben
        Grid; ``gridTemplateColumns`` meldet zwei Spalten. Eine Subkarte
        teilt die erste Zeile mit der Hauptkarte, die zweite bricht innerhalb
        der Panelbreite in eine weitere Zeile um.
        """
        self.seed_live()
        self.set_viewport(1200, 1000)
        self.open_output()
        subs = self.page.locator("div[data-nv-out-subs]").first
        subs.wait_for(state="attached", timeout=20000)
        self.wait_until(
            lambda: subs.locator("[data-nv-out-sub]").count() == 2,
            timeout=20,
            message="Nicht beide Subagenten-Karten im Raster")
        metrics = self.page.evaluate(
            """() => {
              const panel = document.querySelector(
                "section[data-nv-ppanel='output']");
              const main = document.querySelector(
                "section[data-nv-out-main-wrap]");
              const cards = Array.from(
                document.querySelectorAll('[data-nv-out-sub]'));
              const gridAncestor = node => {
                let current = node ? node.parentElement : null;
                while (current && current !== panel) {
                  if (getComputedStyle(current).display === 'grid') return current;
                  current = current.parentElement;
                }
                return null;
              };
              const grid = gridAncestor(main);
              const box = node => {
                const rect = node.getBoundingClientRect();
                return {x: rect.x, y: rect.y, width: rect.width,
                        height: rect.height, right: rect.right};
              };
              return {
                columns: grid ? getComputedStyle(grid).gridTemplateColumns
                  .trim().split(/\\s+/).filter(Boolean) : [],
                shared: !!grid && cards.every(node => gridAncestor(node) === grid),
                main: box(main),
                boxes: cards.map(box),
                panel: box(panel),
              };
            }""")
        self.assertTrue(
            metrics["shared"],
            "Haupt- und Subagenten-Karten teilen kein Raster: "
            + repr(metrics))
        self.assertGreaterEqual(
            len(metrics["columns"]), 2,
            f"Das Grid-Template hat keine zwei Spalten: {metrics}")
        self.assertEqual(2, len(metrics["boxes"]),
                         "Karten konnten nicht gemessen werden")
        first_row = [box for box in metrics["boxes"]
                     if abs(box["y"] - metrics["main"]["y"]) <= 8]
        self.assertGreaterEqual(
            len(first_row), 1,
            "Keine Subagenten-Karte teilt die Zeile der Hauptkarte: "
            + repr(metrics))
        other_row = [box for box in metrics["boxes"] if box not in first_row]
        self.assertEqual(1, len(other_row),
                         "Die zweite Subagenten-Karte bricht nicht um: "
                         + repr(metrics))
        self.assertGreater(
            other_row[0]["y"], metrics["main"]["y"] + 20,
            "Die zweite Subagenten-Karte liegt nicht in einer weiteren "
            "Zeile: " + repr(metrics))
        for label, box in [("Hauptkarte", metrics["main"])] + [
                (f"Subagentenkarte {index + 1}", box)
                for index, box in enumerate(metrics["boxes"])]:
            self.assertLessEqual(
                box["right"], metrics["panel"]["right"] + 2,
                f"{label} ragt über den Panelrand hinaus: " + repr(box))
        self.assert_clean_page()

    def test_card_structure_and_padding(self):
        """Vorbedingung: laufende Subagenten A/B.

        Erwartung pro Karte: Name (``b.nv-out-sub-name`` = Agent), Rolle/
        Agent/Beschreibung (``span.nv-out-sub-role``), Zustand
        (``data-state="running"``, Text ``läuft``), Sitzung (``code.nv-out-
        sub-session``), Fokus-Knopf (``button[data-nv-sub-focus]``
        sichtbar), Log (``pre`` in der Karte: ``max-height <= 40vh`` mit
        eigenem Scroll), eigener Aufklappen-Knopf (``button[data-nv-log-
        expand][data-nv-log-target=...]``), einheitliche Innenabstände
        (alle vier Seiten gleich, > 0).
        """
        self.seed_live()
        self.open_output()
        viewport = self.page.evaluate("() => window.innerHeight")
        for session, agent, description in (
                (SUB_A, "testerA", "Auftrag A"),
                (SUB_B, "testerB", "Auftrag B")):
            with self.subTest(card=session):
                card = self.card(session)
                card.wait_for(state="visible", timeout=20000)
                self.assertEqual(
                    agent, card.locator("b.nv-out-sub-name").first.inner_text())
                self.assertEqual(
                    description,
                    card.locator("span.nv-out-sub-role").first.inner_text())
                status = card.locator("span[data-nv-sub-state]").first
                self.assertEqual("running", status.get_attribute("data-state"))
                self.assertEqual("läuft", status.inner_text())
                session_code = card.locator("code.nv-out-sub-session").first
                self.assertEqual(session, session_code.inner_text())
                self.assertEqual(session, session_code.get_attribute("title"))
                self.assertEqual(
                    1, card.locator("button[data-nv-sub-focus]").count())
                focus = card.locator("button[data-nv-sub-focus]").first
                self.assertTrue(focus.is_visible())
                self.parse_limit(
                    card.locator("pre").first, viewport, 0.4,
                    f"Subagentenprotokoll {session}")
                self.assertEqual(
                    1,
                    card.locator("button[data-nv-log-expand]"
                                 f"[data-nv-log-target='{session}']").count())
                padding = card.evaluate(
                    """node => [getComputedStyle(node).paddingTop,
                                getComputedStyle(node).paddingRight,
                                getComputedStyle(node).paddingBottom,
                                getComputedStyle(node).paddingLeft]""")
                values = [float(item.rstrip("px") or 0) for item in padding]
                self.assertTrue(
                    all(value > 0 for value in values),
                    f"Karte {session} hat leere Innenabstände: {padding}")
                self.assertEqual(
                    len(set(values)), 1,
                    f"Karte {session}: Innenabstände ungleich: {padding}")
        self.assert_clean_page()


class SubCardTest(F34OutputBrowserTest):
    def test_sub_card_expand_toggles(self):
        """Vorbedingung: laufender Subagent A.

        Aktion: ``button[data-nv-log-expand][data-nv-log-target="ses_f34_a"]``
        klicken, erneut.
        Erwartung: Aufklappen-Knopf wechselt ``aria-expanded`` false → true →
        false und zwischen „Alles anzeigen" und „Weniger anzeigen".
        """
        self.seed_live()
        self.open_output()
        card = self.card(SUB_A)
        card.wait_for(state="visible", timeout=20000)
        expand = card.locator(
            f"button[data-nv-log-expand][data-nv-log-target='{SUB_A}']").first
        expand.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", expand.get_attribute("aria-expanded"))
        self.assertIn("Alles anzeigen", expand.inner_text())
        expand.click()
        self.wait_until(
            lambda: expand.get_attribute("aria-expanded") == "true",
            timeout=20,
            message="Der Aufklappen-Knopf meldet nicht aria-expanded=true")
        self.assertIn("Weniger anzeigen", expand.inner_text())
        expand.click()
        self.wait_until(
            lambda: expand.get_attribute("aria-expanded") == "false",
            timeout=20,
            message="Der Aufklappen-Knopf meldet nicht zurück auf "
                    "aria-expanded=false")
        self.assertIn("Alles anzeigen", expand.inner_text())
        self.assert_clean_page()


class ControlsTest(F34OutputBrowserTest):
    def test_control_block_visibility_and_continue_context(self):
        """Vorbedingung: laufender Lauf mit Hauptsession ``ses_f34_main``.

        Erwartung: Steuerblock oben: ``input[data-nv-steer]``,
        ``button[data-nv-action="steer"]`` („Anweisung senden"),
        ``button[data-nv-action="continue"]`` („Fortsetzen") und
        ``button[data-nv-action="stop"]`` („Stoppen") alle sichtbar;
        DOM-Reihenfolge Statuszeile → Steuerblock → Protokoll;
        ``title`` von Fortsetzen meldet die Sitzungs-ID;
        ``small[data-nv-continue-hint]`` erklärt „Sendet ‚weiter‘ an die
        laufende Sitzung"; Continue ist enabled.
        """
        self.seed_live()
        self.open_output()
        order = self.page.evaluate(
            """() => {
              const statusLine = document.querySelector(
                '[data-nv-out-summary]');
              const controls = document.querySelector('.nv-out-controls');
              const main = document.querySelector('[data-nv-out-main]');
              if (!statusLine || !controls || !main) return null;
              return {
                afterStatusLine: (statusLine.compareDocumentPosition(controls)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
                beforeLog: (controls.compareDocumentPosition(main)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
              };
            }""")
        self.assertIsNotNone(order, "Der Steuerblock wurde nicht gefunden")
        self.assertTrue(order["afterStatusLine"],
                        "Der Steuerblock steht nicht unter der Statuszeile")
        self.assertTrue(order["beforeLog"],
                        "Der Steuerblock steht unter dem Protokoll")
        for selector in ("input[data-nv-steer]",
                         "button[data-nv-action='steer']",
                         "button[data-nv-action='continue']",
                         "button[data-nv-action='stop']"):
            with self.subTest(control=selector):
                node = self.page.locator(selector).first
                self.assertEqual(1, node.count(), f"{selector} fehlt")
                node.wait_for(state="visible", timeout=20000)
                self.assertTrue(node.is_visible(), f"{selector} nicht sichtbar")
        self.assertEqual(
            "Anweisung senden",
            self.page.locator("button[data-nv-action='steer']").first
            .inner_text())
        continue_button = self.page.locator(
            "button[data-nv-action='continue']").first
        continue_button.wait_for(state="visible", timeout=20000)
        self.assertEqual("Fortsetzen", continue_button.inner_text())
        self.assertTrue(continue_button.is_enabled(),
                        "Fortsetzen ist bei laufendem Lauf deaktiviert")
        title = continue_button.get_attribute("title") or ""
        self.assertIn(MAIN_SESSION_f34, title,
                      f"Der title nennt die Sitzung nicht: {title!r}")
        hint = self.page.locator("small[data-nv-continue-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertEqual("Sendet ‚weiter‘ an die laufende Sitzung",
                         hint.inner_text())
        self.assert_clean_page()

    def test_continue_disabled_without_session(self):
        """Vorbedingung: laufender Lauf, Zustandsdatei ``{"session": ""}``.

        Erwartung: ``button[data-nv-action="continue"]`` ist disabled; der
        ``title`` meldet „Keine Sitzung – Fortsetzen nicht möglich.";
        ``small[data-nv-continue-hint]`` erklärt die fehlende Sitzung.
        """
        (self.log_dir / f"{PROJECT}.log.state.json").write_text(
            json.dumps({"session": "", "subagents": []}, ensure_ascii=False),
            encoding="utf-8")
        self.register_run("running")
        self.open_output()
        continue_button = self.page.locator(
            "button[data-nv-action='continue']").first
        continue_button.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: continue_button.is_disabled(),
            timeout=20,
            message="Der Fortsetzen-Knopf ist ohne Sitzung nicht disabled")
        self.assertIn(
            "Keine Sitzung – Fortsetzen nicht möglich.",
            continue_button.get_attribute("title") or "")
        hint = self.page.locator("small[data-nv-continue-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "Ohne Sitzung kann der Lauf nicht fortgesetzt werden.",
            hint.inner_text())
        self.assert_clean_page()


class ResumeTest(F34OutputBrowserTest):
    def test_resume_button_with_context(self):
        """Vorbedingung: beendeter Lauf (``--state stopped``);
        ``sessions.json`` mit Eintrag Paket ``F34-Ticket-4711``, Sitzung
        ``ses_f34_resume``.

        Erwartung: ``section[data-nv-out-resume]`` sichtbar;
        ``button[data-nv-action="session-resume"]`` sichtbar im
        ``div.nv-out-resume-row``: der Zeilenkontext meldet Paket und
        Sitzung (``<b>``), die Erklärung „Setzt diese Sitzung fort." liegt
        im ``<small>``; der ``title`` des Knopfes meldet Paket und Sitzung.
        """
        self.register_run(state="stopped")
        now = int(time.time())
        entry = {
            "session": SES_RESUME,
            "first_seen": now - 120,
            "last_seen": now - 60,
            "project": str(self.project.resolve()),
            "name": PROJECT,
            "run_id": "",
            "agent": MAIN_AGENT,
            "harness": "opencode",
            "package_id": PKG_ID,
        }
        (self.log_dir / "sessions.json").write_text(
            json.dumps({"limit": 5, "sessions": [entry]},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        self.open_output()
        resume = self.page.locator("section[data-nv-out-resume]").first
        resume.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, resume.locator("button[data-nv-action='session-resume']").count())
        button = resume.locator(
            "button[data-nv-action='session-resume']").first
        button.wait_for(state="visible", timeout=20000)
        self.assertTrue(button.is_visible())
        row = resume.locator("div.nv-out-resume-row").first
        row.wait_for(state="visible", timeout=20000)
        row_text = row.inner_text()
        self.assertIn(PKG_ID, row_text)
        self.assertIn(SES_RESUME, row_text)
        self.assertIn("Setzt diese Sitzung fort.", row_text)
        context_b = row.locator("b").first.inner_text()
        self.assertIn(PKG_ID, context_b,
                      f"Kontext {context_b!r} meldet kein Paket")
        self.assertIn(SES_RESUME, context_b,
                      f"Kontext {context_b!r} meldet keine Sitzung")
        self.assertEqual(1, row.locator("small").count())
        self.assertIn("Setzt diese Sitzung fort.",
                      row.locator("small").first.inner_text())
        title = button.get_attribute("title") or ""
        self.assertIn(PKG_ID, title, f"Title {title!r} meldet kein Paket")
        self.assertIn(SES_RESUME, title,
                      f"Title {title!r} meldet keine Sitzung")
        self.assert_clean_page()


class PageOverflowTest(F34OutputBrowserTest):
    def test_no_horizontal_overflow_at_1280(self):
        """Vorbedingung: Viewport 1280 px × 1000, laufender Lauf, Subagenten
        A/B.

        Erwartung: ``documentElement.scrollWidth <=
        documentElement.clientWidth + 1`` — die Seite läuft nicht
        horizontal über (wahrend beabsichtigte Überläufe in
        ``overflow-x: auto``-Containern der Zusammenfassung abgefangen werden).
        """
        self.set_viewport(1280, 1000)
        self.seed_live()
        self.open_output()
        main = self.page.locator("[data-nv-out-main]").first
        main.wait_for(state="visible", timeout=20000)
        summary = self.page.locator("div[data-nv-out-summary]").first
        summary.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: summary.locator("[data-nv-out-summary-row]").count() >= 3,
            timeout=20, message="Nicht alle Zusammenfassungszeilen geladen")
        metrics = self.page.evaluate(
            """() => ({
              docScrollWidth: document.documentElement.scrollWidth,
              docClientWidth: document.documentElement.clientWidth,
            })""")
        self.assertLessEqual(
            metrics["docScrollWidth"], metrics["docClientWidth"] + 1,
            f"Die Seite läuft horizontal über: {metrics}")
        self.assert_clean_page()



class OutputCardBehaviorTest(F34OutputBrowserTest):
    """Nova-Ausgabe: Nachführverhalten, Kartenraster, Kartenstil und Statuszeile."""

    MAIN_STAY = "NACHFUEHREN-OBEN-PROTOKOLL"
    MAIN_LATER = "NACHFUEHREN-SPAETER-PROTOKOLL"
    MAIN_FOLLOW = "NACHFUEHREN-NACH-BOTTOM-PROTOKOLL"
    SUB_STAY = "NACHFUEHREN-OBEN-SUBAGENT"
    SUB_LATER = "NACHFUEHREN-SPAETER-SUBAGENT"
    SUB_FOLLOW = "NACHFUEHREN-NACH-BOTTOM-SUBAGENT"

    LOG_METRICS_JS = """node => ({
      scrollTop: node.scrollTop,
      scrollHeight: node.scrollHeight,
      clientHeight: node.clientHeight,
      text: node.textContent || '',
    })"""

    CARD_LAYOUT_JS = """() => {
      const panel = document.querySelector("section[data-nv-ppanel='output']");
      const main = document.querySelector("section[data-nv-out-main-wrap]");
      const subs = Array.from(document.querySelectorAll("[data-nv-out-sub]"));
      const box = node => {
        const rect = node.getBoundingClientRect();
        return {
          x: rect.x, y: rect.y, width: rect.width, height: rect.height,
          right: rect.right, bottom: rect.bottom,
        };
      };
      const container = document.querySelector("[data-nv-out-subs]");
      const gridAncestor = node => {
        let current = node ? node.parentElement : null;
        while (current && current !== panel) {
          if (getComputedStyle(current).display === 'grid') return current;
          current = current.parentElement;
        }
        return null;
      };
      const mainGrid = gridAncestor(main);
      const subGrids = subs.map(gridAncestor);
      const grid = {
        shared: !!mainGrid && subGrids.length > 0
          && subGrids.every(node => node === mainGrid),
        columns: mainGrid ? getComputedStyle(mainGrid).gridTemplateColumns
          .trim().split(/\\s+/).filter(Boolean).length : 0,
      };
      return {
        panel: panel ? box(panel) : null,
        main: main ? box(main) : null,
        subs: subs.map(box),
        container: container ? {
          box: box(container),
          scrollWidth: container.scrollWidth,
          clientWidth: container.clientWidth,
        } : null,
        grid: grid,
        docScrollWidth: document.documentElement.scrollWidth,
        docClientWidth: document.documentElement.clientWidth,
      };
    }"""

    CARD_STYLE_JS = """() => {
      const inline = node => node ? node.getAttribute('style') || '' : null;
      const cards = Array.from(document.querySelectorAll("[data-nv-out-sub]"));
      const probe = document.createElement('div');
      probe.style.display = 'flex';
      document.body.append(probe);
      const tokenGaps = ['--nv-space-1', '--nv-space-2', '--nv-space-3',
        '--nv-space-4', '--nv-space-5', '--nv-space-6'].map(name => {
          probe.style.gap = 'var(' + name + ')';
          return getComputedStyle(probe).gap;
        });
      probe.remove();
      const styleOf = node => {
        const style = getComputedStyle(node);
        return {
          display: style.display,
          flexWrap: style.flexWrap,
          alignItems: style.alignItems,
          gap: style.gap,
          padding: style.paddingTop,
          radius: style.borderTopLeftRadius,
          background: style.backgroundColor,
          border: style.borderTopColor,
          overflowY: style.overflowY,
          whiteSpace: style.whiteSpace,
        };
      };
      const first = cards[0];
      const firstHead = first ? first.querySelector('.nv-out-sub-head') : null;
      const firstLog = first ? first.querySelector('pre') : null;
      return {
        mainInline: inline(document.querySelector(
          'section[data-nv-out-main-wrap]')),
        mainHeadInline: inline(document.querySelector('.nv-out-main-head')),
        mainLogInline: inline(document.querySelector('pre[data-nv-out-main]')),
        subsInline: inline(document.querySelector('[data-nv-out-subs]')),
        cards: cards.map(card => ({
          card: inline(card),
          head: inline(card.querySelector('.nv-out-sub-head')),
          log: inline(card.querySelector('pre')),
        })),
        tokenGaps: tokenGaps,
        mainStyle: styleOf(document.querySelector(
          'section[data-nv-out-main-wrap]')),
        mainHeadStyle: styleOf(document.querySelector('.nv-out-main-head')),
        mainLogStyle: styleOf(document.querySelector('pre[data-nv-out-main]')),
        cardStyle: first ? styleOf(first) : null,
        cardHeadStyle: firstHead ? styleOf(firstHead) : null,
        cardLogStyle: firstLog ? styleOf(firstLog) : null,
      };
    }"""

    STATUS_LABEL_JS = """() => {
      const panel = document.querySelector("section[data-nv-ppanel='output']");
      if (!panel) return ['Ausgabe-Panel fehlt'];
      const ownText = node => Array.from(node.childNodes)
        .filter(child => child.nodeType === Node.TEXT_NODE)
        .map(child => (child.textContent || '').trim()).join(' ').trim();
      return Array.from(panel.querySelectorAll('*')).map(ownText).filter(text =>
        /^Hauptagent:\\s*\\S/.test(text)
        || /^\\d+\\s*Subagenten$/.test(text)
        || /^Keine laufenden Subagenten\\.$/.test(text));
    }"""

    def append_main_line(self, marker):
        with (self.log_dir / f"{PROJECT}.log").open(
                "a", encoding="utf-8") as handle:
            handle.write(marker + "\n")

    def long_output(self, marker):
        return "\n".join([marker] + [
            f"Zeile {index:03d} des Subagenten mit fortlaufendem Text."
            for index in range(60)])

    def log_metrics(self, selector):
        return self.page.eval_on_selector(selector, self.LOG_METRICS_JS)

    def set_log_scroll(self, selector, offset):
        self.page.eval_on_selector(
            selector, "node => { node.scrollTop = %d; }" % offset)

    def log_at_bottom(self, metrics):
        return metrics["scrollHeight"] - metrics["scrollTop"] \
            - metrics["clientHeight"] <= 2

    def wait_for_log_marker(self, selector, marker, timeout=25):
        self.wait_until(
            lambda: marker in self.log_metrics(selector)["text"],
            timeout=timeout,
            message=f"Die neue Protokollzeile {marker!r} kam nicht an")

    def test_main_log_holds_reader_position_until_bottom_is_reached(self):
        """Vorbedingung: laufender Lauf mit überlangem Hauptprotokoll.

        Aktion: Das Protokoll wird auf eine Position oberhalb des Fußes
        gescrollt; dann kommt eine neue Zeile per Livestream hinzu. Danach
        wird ans Ende gescrollt und erneut eine Zeile angehängt.

        Erwartung: Die erste Zeile erscheint, die Scrollposition bleibt
        unverändert; nach dem Rückkehr zum Fuß folgt das Protokoll der
        zweiten Zeile automatisch nach unten.
        """
        self.seed_live()
        self.open_output()
        selector = "pre[data-nv-out-main]"
        log = self.page.locator(selector).first
        log.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: self.log_metrics(selector)["scrollHeight"]
            > self.log_metrics(selector)["clientHeight"] + 200,
            timeout=20, message="Das Hauptprotokoll ist nicht scrollbar")

        self.set_log_scroll(selector, 120)
        before = self.log_metrics(selector)
        self.assertGreaterEqual(
            before["scrollTop"], 100,
            "Die Testscrollposition im Hauptprotokoll konnte nicht gesetzt "
            "werden: " + repr(before))

        self.append_main_line(self.MAIN_STAY)
        self.wait_for_log_marker(selector, self.MAIN_STAY)
        held = self.log_metrics(selector)
        self.assertGreater(
            held["scrollHeight"], before["scrollHeight"],
            "Das Hauptprotokoll ist nicht gewachsen")
        self.assertLessEqual(
            abs(held["scrollTop"] - before["scrollTop"]), 6,
            "Das Hauptprotokoll hat die Leseposition verlassen: von "
            f"{before['scrollTop']} auf {held['scrollTop']} px")

        self.set_log_scroll(selector, self.log_metrics(selector)["scrollHeight"])
        bottom = self.log_metrics(selector)
        self.assertTrue(self.log_at_bottom(bottom),
                        "Das Hauptprotokoll steht nicht am Fuß: " + repr(bottom))
        self.append_main_line(self.MAIN_FOLLOW)
        self.wait_for_log_marker(selector, self.MAIN_FOLLOW)
        after = self.log_metrics(selector)
        self.assertTrue(
            self.log_at_bottom(after),
            "Das Hauptprotokoll folgt am Fuß nicht nach: " + repr(after))
        self.assert_clean_page()

    def test_subagent_log_holds_reader_position_until_bottom_is_reached(self):
        """Vorbedingung: laufender Subagent A mit überlanger Ausgabe.

        Aktion: Die Karte wird oberhalb des Fußes gescrollt; die
        Zustandsdatei liefert eine längere Ausgabe. Danach wird ans Ende
        gescrollt und erneut eine längere Ausgabe geladen.

        Erwartung: Die neue Ausgabe erscheint, die Scrollposition bleibt
        unverändert; vom Fuß aus folgt die Karte der nächsten Ausgabe.
        """
        first = self.long_output(self.SUB_STAY)
        self.seed_subs([
            (SUB_A, "testerA", "Auftrag A", first),
            (SUB_B, "testerB", "Auftrag B", "AUSGABE-B-F34: Subagent B."),
        ])
        self.register_run("running")
        self.write_log(MAIN_MARKER_f34)
        self.open_output()
        selector = "[data-nv-out-sub='%s'] pre" % SUB_A
        log = self.page.locator(selector).first
        log.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: self.log_metrics(selector)["scrollHeight"]
            > self.log_metrics(selector)["clientHeight"] + 200,
            timeout=20, message="Das Subagentenprotokoll ist nicht scrollbar")

        self.set_log_scroll(selector, 120)
        before = self.log_metrics(selector)
        self.assertGreaterEqual(
            before["scrollTop"], 100,
            "Die Testscrollposition im Subagentenprotokoll konnte nicht "
            "gesetzt werden: " + repr(before))

        longer = self.long_output(self.SUB_STAY) + "\n" + self.SUB_LATER
        self.seed_subs([
            (SUB_A, "testerA", "Auftrag A", longer),
            (SUB_B, "testerB", "Auftrag B", "AUSGABE-B-F34: Subagent B."),
        ])
        self.wait_for_log_marker(selector, self.SUB_LATER, timeout=30)
        held = self.log_metrics(selector)
        self.assertGreater(
            held["scrollHeight"], before["scrollHeight"],
            "Die Subagentenausgabe ist nicht gewachsen")
        self.assertLessEqual(
            abs(held["scrollTop"] - before["scrollTop"]), 6,
            "Das Subagentenprotokoll hat die Leseposition verlassen: von "
            f"{before['scrollTop']} auf {held['scrollTop']} px")

        self.set_log_scroll(selector, self.log_metrics(selector)["scrollHeight"])
        bottom = self.log_metrics(selector)
        self.assertTrue(self.log_at_bottom(bottom),
                        "Das Subagentenprotokoll steht nicht am Fuß: "
                        + repr(bottom))
        longest = longer + "\n" + self.SUB_FOLLOW
        self.seed_subs([
            (SUB_A, "testerA", "Auftrag A", longest),
            (SUB_B, "testerB", "Auftrag B", "AUSGABE-B-F34: Subagent B."),
        ])
        self.wait_for_log_marker(selector, self.SUB_FOLLOW, timeout=30)
        after = self.log_metrics(selector)
        self.assertTrue(
            self.log_at_bottom(after),
            "Das Subagentenprotokoll folgt am Fuß nicht nach: " + repr(after))
        self.assert_clean_page()

    def test_agent_cards_use_viewport_width_without_horizontal_overflow(self):
        """Vorbedingung: laufender Lauf mit zwei Subagenten.

        Aktion: Bei 1400, 900 und 400 px Viewport werden Hauptkarte,
        Subagenten-Karten, Panel und Dokument ausgemessen.

        Erwartung: Haupt- und Subagenten-Karten teilen sich einen gemeinsamen
        Rastercontainer; alle Karten liegen innerhalb der Panelbreite, das
        Dokument und der Kartencontainer laufen nicht horizontal über. Auf
        breiten Viewports teilt die Hauptkarte zusätzlich eine Zeile mit einer
        Subagenten-Karte und ist schmaler als das gesamte Panel; auf 400 px
        bleibt alles ohne Überlauf umgebrochen.
        """
        self.seed_live()
        self.open_output()
        for width in (1400, 900, 400):
            with self.subTest(viewport=width):
                self.set_viewport(width, 900)
                self.open_output()
                self.wait_until(
                    lambda: self.card(SUB_A).count() == 1
                    and self.card(SUB_B).count() == 1,
                    timeout=20, message="Die Subagenten-Karten fehlen bei "
                                       f"{width} px")
                metrics = self.page.evaluate(self.CARD_LAYOUT_JS)
                self.assertIsNotNone(metrics["panel"])
                self.assertIsNotNone(metrics["main"])
                self.assertEqual(2, len(metrics["subs"]))
                self.assertIsNotNone(metrics["container"])
                self.assertTrue(
                    metrics["grid"]["shared"],
                    f"Haupt- und Subagenten-Karten teilen bei {width} px "
                    "kein gemeinsames Raster: " + repr(metrics["grid"]))
                self.assertGreaterEqual(
                    metrics["grid"]["columns"], 1,
                    f"Das Raster hat bei {width} px keine Spalte: "
                    + repr(metrics["grid"]))
                self.assertLessEqual(
                    metrics["docScrollWidth"], metrics["docClientWidth"] + 2,
                    f"Die Seite läuft bei {width} px horizontal über: "
                    + repr(metrics))
                self.assertLessEqual(
                    metrics["container"]["scrollWidth"],
                    metrics["container"]["clientWidth"] + 2,
                    f"Der Kartencontainer läuft bei {width} px über: "
                    + repr(metrics["container"]))
                for label, box in [("Hauptkarte", metrics["main"])] + [
                        (f"Subagentenkarte {index + 1}", box)
                        for index, box in enumerate(metrics["subs"])]:
                    self.assertGreater(box["width"], 0,
                                       f"{label} hat keine Breite bei "
                                       f"{width} px")
                    self.assertLessEqual(
                        box["right"], metrics["panel"]["right"] + 2,
                        f"{label} ragt bei {width} px über den Panelrand "
                        "hinaus: " + repr(box))
                if width == 1400:
                    self.assertLess(
                        metrics["main"]["width"],
                        metrics["panel"]["width"] * 0.75,
                        "Die Hauptkarte belegt bei 1400 px die volle "
                        "Panelbreite statt eines Rasterplatzes: "
                        + repr(metrics["main"]))
                    self.assertTrue(
                        any(abs(metrics["main"]["y"] - sub["y"]) <= 8
                            for sub in metrics["subs"]),
                        "Die Hauptkarte teilt bei 1400 px keine Zeile "
                        "mit einer Subagenten-Karte: " + repr(metrics))
        self.assert_clean_page()

    def test_preview_cards_take_their_styling_from_css_classes(self):
        """Vorbedingung: laufender Lauf mit zwei Subagenten-Karten.

        Aktion: Inline-Styles und berechnete Styles von Hauptkarte,
        Unterkarten, Köpfen, Logs und Kartencontainer auslesen.

        Erwartung: Karten, Köpfe und Container tragen keine Inline-Styles;
        Logs haben höchstens das dynamische ``max-height`` inline, während
        Überlauf und Zeilenumbruch aus CSS kommen. Abstände und Rahmen
        entsprechen den Design-Tokens und denen der Hauptkarte.
        """
        self.seed_live()
        self.open_output()
        self.wait_until(
            lambda: self.card(SUB_A).count() == 1
            and self.card(SUB_B).count() == 1,
            timeout=20, message="Die Subagenten-Karten fehlen")
        styles = self.page.evaluate(self.CARD_STYLE_JS)
        self.assertEqual(2, len(styles["cards"]))
        for label in ("mainInline", "mainHeadInline", "subsInline"):
            self.assertEqual(
                "", styles[label],
                f"{label} enthält Inline-Styles: {styles[label]!r}")
        for index, card in enumerate(styles["cards"]):
            with self.subTest(card=index):
                self.assertEqual("", card["card"],
                                 "Die Karte hat Inline-Styles: " + repr(card))
                self.assertEqual("", card["head"],
                                 "Der Kartenkopf hat Inline-Styles: "
                                 + repr(card))
                declarations = [
                    item.strip() for item in card["log"].split(";")
                    if item.strip()]
                properties = {item.split(":", 1)[0].strip().lower()
                              for item in declarations}
                self.assertLessEqual(
                    properties, {"max-height"},
                    "Das Subagentenlog hat statische Inline-Styles: "
                    + repr(card["log"]))
        declarations = [
            item.strip() for item in styles["mainLogInline"].split(";")
            if item.strip()]
        properties = {item.split(":", 1)[0].strip().lower()
                      for item in declarations}
        self.assertLessEqual(
            properties, {"max-height"},
            "Das Hauptprotokoll hat statische Inline-Styles: "
            + repr(styles["mainLogInline"]))

        self.assertEqual("flex", styles["mainHeadStyle"]["display"])
        self.assertEqual("wrap", styles["mainHeadStyle"]["flexWrap"])
        self.assertEqual("center", styles["mainHeadStyle"]["alignItems"])
        self.assertEqual("flex", styles["cardHeadStyle"]["display"])
        self.assertEqual("wrap", styles["cardHeadStyle"]["flexWrap"])
        self.assertEqual("center", styles["cardHeadStyle"]["alignItems"])
        for label in ("mainHeadStyle", "cardHeadStyle"):
            self.assertIn(styles[label]["gap"], styles["tokenGaps"],
                          f"{label} nutzt keinen Abstands-Token: "
                          + repr(styles[label]))
        self.assertIn(styles["cardStyle"]["padding"], styles["tokenGaps"],
                      "Die Karte nutzt keinen Abstands-Token: "
                      + repr(styles["cardStyle"]))
        for key in ("radius", "background", "border"):
            self.assertEqual(
                styles["mainStyle"][key], styles["cardStyle"][key],
                f"Die Subagentenkarte weicht bei {key} von .nv-card ab: "
                + repr(styles))
        for label in ("mainLogStyle", "cardLogStyle"):
            self.assertIn(styles[label]["overflowY"], ("auto", "scroll"),
                          f"{label} scrollt nicht: " + repr(styles[label]))
            self.assertEqual("pre-wrap", styles[label]["whiteSpace"],
                             f"{label} bricht Zeilen nicht um: "
                             + repr(styles[label]))
        self.assert_clean_page()

    def test_status_line_is_gone_and_run_state_stays_on_cards(self):
        """Vorbedingung: laufender Lauf mit zwei laufenden Subagenten.

        Aktion: Beschriftungen der alten Zeile unter den Karten suchen;
        Laufzustand in Hauptkarte und Zusammenfassung lesen.

        Erwartung: Keine Zeile „läuftHauptagent: … Subagenten“ mehr; zwei
        sichtbare Subagenten-Karten; ``läuft`` in der Hauptkarte und in der
        Zusammenfassungszeile des Hauptagenten.
        """
        self.seed_live()
        self.open_output()
        self.wait_until(
            lambda: self.card(SUB_A).count() == 1
            and self.card(SUB_B).count() == 1,
            timeout=20, message="Die Subagenten-Karten fehlen")
        leftovers = self.page.evaluate(self.STATUS_LABEL_JS)
        self.assertEqual(
            [], leftovers,
            "Die Statuszeile unter den Karten ist noch vorhanden: "
            + repr(leftovers))
        for session in (SUB_A, SUB_B):
            self.assertTrue(self.card(session).is_visible(),
                            f"Subagenten-Karte {session} ist nicht sichtbar")

        main_state = self.page.locator("[data-nv-out-main-state]").first
        main_state.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: main_state.get_attribute("data-state") == "running"
            and main_state.inner_text() == "läuft",
            timeout=20, message="Die Hauptkarte meldet nicht läuft: "
                                + repr(main_state.inner_text()))
        summary_state = self.page.locator(
            "[data-nv-out-summary-row][data-nv-summary-target='main'] "
            ".nv-pill").first
        summary_state.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "running", summary_state.get_attribute("data-state"),
            "Die Zusammenfassung zeigt den Laufzustand nicht")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
