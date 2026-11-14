"""Browserabnahme AP16: Syntaxhervorhebung in der Agentenausgabe.

Arbeitspaket AP16 („Die Agent ausgabe soll syntax highlighting erhalten, um
besser lesbar zu sein“) verlangt, dass die Agentenansichten der Ausgabeansicht
(B11-Neubau) die Protokollzeilen visuell unterscheiden und dadurch lesbarer
werden — für den Hauptagenten und für jeden laufenden Subagenten.

Geprüft wird implementierungsunabhängig über berechnete Stile: Zeilen bzw.
Zeichenketten, die hervorgehenswert sind (Protokollkopf, Fehlerzeilen,
Pfadangaben), müssen sich in der berechneten Textfarbe von schlichten
Protokollzeilen unterscheiden. Konkrete Klassennamen werden nicht gefordert;
für die bestehende „Live-Ausgabe“-Karte gilt der dokumentierte F19-Vertrag
(``pre#log`` mit ``hl-*``-Klassen in ``bin/web/styles.css``), der erhalten
bleiben muss.

Verbindliche Prüfziele dieser Abnahme:

* AK1: Die Hauptagentenansicht hebt Protokollzeilen visuell hervor (Farbe
  unterscheidet sich von schlichten Zeilen).
* AK2: Laufende Subagenten erhalten dieselbe Hervorhebung in ihrer eigenen
  Ansicht.
* AK3: Die Hervorhebung ändert den dargestellten Text nicht; der sichtbare
  Text bleibt exakt der Protokolltext.
* AK4: Protokollinhalt wird niemals als HTML interpretiert; Markup im Text
  bleibt sichtbarer Text (kein innerHTML-Vektor).
* AK5: Live-Verlängerungen erscheinen fehlerfrei und bereits hervorgehoben;
  keine JavaScript-Fehler, keine Browserdialoge.
* AK6: Die F19-Hervorhebung der „Live-Ausgabe“-Karte (``pre#log``) funktioniert
  weiter; Anweisung senden und Fortsetzen bleiben unberührt.

Testfälle:

1. test_main_agent_log_lines_are_visually_distinguished     [AK1, AK3]
   Vorbedingung: aktiver Lauf; Hauptlog mit Kopf-, Fehler-, Pfad- und
   schlichter Zeile sowie einer Markup-Zeile.
   Aktion: Ausgabeansicht öffnen und berechnete Farben aller Textknoten der
   Hauptausgabe messen.
   Erwartung: Kopf-, Fehler- und Pfadtoken tragen eine andere Farbe als die
   schlichte Zeile; die schlichte Zeile selbst trägt genau eine Farbe; alle
   Protokollzeilen stehen exakt einmal und lesbar im Text.
   Fehlerfall: Keine Farbdifferenz (keine Hervorhebung) oder veränderter/
   doppelter Protokolltext.
2. test_subagent_log_is_highlighted_like_the_main_log       [AK2]
   Vorbedingung: aktiver Lauf; Subagent A mit Fehler- und schlichter Zeile.
   Aktion: Farben in der Subagentenansicht messen.
   Erwartung: Fehlerzeile farblich von der schlichten Zeile unterschieden.
   Fehlerfall: Subagentenausgabe bleibt ohne Hervorhebung.
3. test_log_markup_is_never_interpreted_as_html             [AK4]
   Vorbedingung: aktiver Lauf; Haupt- und Subagentenprotokoll enthalten
   ``<script>``- und ``<b>``-Markup.
   Aktion: Ausgabeansicht öffnen, DOM und ``window.__ap16pwn`` prüfen.
   Erwartung: Kein Skript ausgeführt, keine script/b-Elemente in den
   Ansichten, Markup wörtlich sichtbar; Seite fehlerfrei.
   Fehlerfall: Markup wird als HTML interpretiert oder erzeugt Fehler.
4. test_live_appended_error_line_is_highlighted             [AK5]
   Vorbedingung: aktiver Lauf, Ausgabeansicht geöffnet.
   Aktion: Fehlerzeile an das Laufprotokoll anhängen.
   Erwartung: Neue Zeile erscheint hervorgehoben, genau einmal, ohne
   JavaScript-Fehler oder Browserdialoge.
   Fehlerfall: Neue Zeile ohne Hervorhebung oder Fehler im Live-Pfad.
5. test_f19_run_log_keeps_its_highlighting                  [AK6]
   Vorbedingung: beendeter Lauf ohne Sitzungsangabe (Rückfallmodus).
   Aktion: Ausgabeansicht öffnen; Farben in der „Live-Ausgabe“-Karte
   (``pre#log``) messen.
   Erwartung: Kopf- und Fehlerzeilen unterscheiden sich farblich von der
   schlichten Zeile.
   Fehlerfall: Die bestehende F19-Hervorhebung ging verloren.
6. test_send_and_continue_controls_still_work               [AK6]
   Vorbedingung: aktiver Lauf; /api/steer abgefangen.
   Aktion: Anweisung eingeben und senden.
   Erwartung: Eingaben sind freigegeben, POST nennt die Hauptsession; kein
   Fortsetzen-Knopf während des Laufs.
   Fehlerfall: Steuerung wurde durch die Hervorhebung beschädigt.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port und
isoliertem VIBE-Root. Lauf, Hauptsession und Subagenten werden über das echte
Laufregister und die Zustandsdatei nachgebildet; steuernde POSTs fängt
Playwright ab. Keine echten Modellaufrufe, keine produktive Installation,
keine Netzzugriffe.
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


if __name__ == "__main__":
    unittest.main()
