"""Browserabnahme F33, WP4: Ausgabe (2p, korrigiert).

Ableitung ausschließlich aus ``docs/features/F33.md`` — Abschnitt
„Dom-Hook-Vertrag → WP4 — Ausgabe (2p, korrigiert)“ sowie der Korrektur zu
2p. Geprüft werden die verbindlichen ``data-nv-*``-Hooks und das
beobachtbare Verhalten: Fokus/Vergrößern der Hauptausgabe, der Steuerblock
direkt unter der Statuszeile, Subagenten-Anweisungen mit ``session`` und
der Zeilenumbruch der Protokolle.

Das echte Dashboard läuft als eigener Prozess auf einem freien
Loopback-Port mit isoliertem ``VIBE``/``HOME``. Lauf und Subagent werden
über das echte Laufregister und die Zustandsdatei ``proj.log.state.json``
nachgebildet (Muster ``tests/browser/test_ap22_output_ui.py`` und
``tests/browser/test_b14_subagent_output_ui.py``); die opencode-Attrappe
liefert keine Agentennachrichten, sodass die Ausgabe aus der Zustandsdatei
kommt. Es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von
Loopback.

Fachlicher Rahmen
-----------------
* **Fokus/Vergrößern:** ``button[data-nv-action="out-focus"]`` mit
  ``aria-expanded`` vergrößert die Hauptausgabe über die Klasse
  ``.nv-out-enlarged`` (fixed, nahezu flächig); Escape oder ein erneuter
  Klick beendet den Zustand.
* **Steuerblock oben:** ``input[data-nv-steer]`` sowie die Aktionen
  ``steer``/``continue``/``stop`` stehen direkt unter der Statuszeile
  (``position: sticky``) und sind ohne Scrollen erreichbar.
* **Subagenten-Anweisungen:** ``input[data-nv-sub-steer]`` +
  ``button[data-nv-sub-steer-send]`` je laufender Karte senden
  ``POST /api/steer {name, text, session}``.
* **Rahmen-Overflow:** ``.nv-log`` bricht Zeilen um (``pre-wrap``) — kein
  horizontaler Überlauf bei Haupt- und Subagenten-Protokollen.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``FocusTest.test_main_output_focus_enlarges_and_escape_restores``
``FocusTest.test_second_click_leaves_the_focus_state``
``ControlsTest.test_steer_block_sits_directly_under_the_status_line``
``SubagentSteerTest.test_running_card_sends_session_with_the_instruction``
``OverflowTest.test_logs_wrap_without_horizontal_overflow``

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
---------------------------------------------------------
1. **Träger der Vergrößerung.** Der Vertrag nennt die Klasse
   ``.nv-out-enlarged``, aber nicht, welches Element sie trägt. Akzeptiert
   wird genau ein Element mit dieser Klasse, das die Hauptausgabe
   (``[data-nv-out-main]``) enthält oder selbst ist.
2. **„Nahezu flächig“.** Geprüft wird ``position: fixed`` und eine Fläche
   von mindestens Viewport − 32 px in beiden Richtungen (``inset: 8px``).
3. **„Body scrollt nicht mit“.** Geprüft wird ``overflow`` ``hidden`` oder
   ``clip`` an ``body`` oder ``html`` im vergrößerten Zustand; eine
   Scrollsperre über eine andere Mechanik ist damit bewusst nicht erzwungen.
4. **Subagenten-Anweisung nur bei laufendem Lauf.** Ohne laufenden Lauf
   existieren laut Backend keine Subagenten-Karten; der Negativfall ist
   strukturell nicht darstellbar. Geprüft wird die laufende Karte samt
   ``session`` in der Nutzlast.
5. **Steuerblock-Erreichbarkeit.** Geprüft wird die DOM-Reihenfolge
   Statuszeile → Steuerblock → Protokoll und dass der Block beim Öffnen
   ohne Scrollen im Viewport liegt (bei einem langen Protokoll).

ROT-PHASE (2026-11-21, vor der Implementierung von WP4)
------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f33_output_ui.py' -v

Gelaufen gegen einen sauberen ``git archive HEAD``-Baum (temporär entpackt),
weil im Arbeitsbaum der WP4-CSS-Block bereits von einem parallelen Agenten
angelegt war. Der Baseline-Baum enthält den committeten WP6-Backendstand,
aber weder ``.nv-out-enlarged`` noch die F33-Ausgabestile — das ist der
Stand „vor der Implementierung“. Die Testdatei ist unverändert die finale
Fassung.

Ergebnis: **5 Fälle, 5 rot, 0 grün.** Kein Fall scheiterte aus
Umgebungsgründen.

* ``test_main_output_focus_enlarges_and_escape_restores`` — TimeoutError:
  ``button[data-nv-action="out-focus"]`` fehlt.
* ``test_second_click_leaves_the_focus_state`` — TimeoutError: derselbe
  fehlende Fokus-Knopf.
* ``test_steer_block_sits_directly_under_the_status_line`` —
  AssertionError: Der Steuerblock steht unter dem Protokoll statt darüber.
* ``test_running_card_sends_session_with_the_instruction`` — TimeoutError:
  ``input[data-nv-sub-steer]``/``button[data-nv-sub-steer-send]`` fehlen.
* ``test_logs_wrap_without_horizontal_overflow`` — AssertionError (zwei
  Subfälle): ``white-space`` ist ``pre``; Hauptprotokoll
  ``scrollWidth 4068 > clientWidth 1086``, Subagentenprotokoll
  ``4059 > 1020`` — beide laufen horizontal über.
"""
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

PROJECT = "proj"
AGENT = "vibe-agent"
MAIN_SESSION = "ses_f33_main"
CHILD_SESSION = "ses_f33_child"
MAIN_MARKER = "HAUPT-F33-4711: Hauptagent schreibt sein Protokoll."
SUB_MARKER = "SUB-F33-4711: Der Subagent schreibt seine Ausgabe."
LONG_TOKEN = "X" * 400
STEER_TEXT = "Bitte die vollständige Ausgabe zeigen"
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
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
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
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
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")

    def seed_live(self):
        self.register_run("running")
        self.write_log(MAIN_MARKER + " " + LONG_TOKEN)
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
        self.page.locator("[data-nv-out-overview]").wait_for(
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


class ControlsTest(F33OutputBrowserTest):
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
              const overview = document.querySelector('[data-nv-out-overview]');
              const main = document.querySelector('[data-nv-out-main]');
              const steer = document.querySelector('[data-nv-steer]');
              if (!overview || !main || !steer) return null;
              let block = steer;
              while (block && block !== document.body
                     && !block.querySelector('[data-nv-action="continue"]')) {
                block = block.parentElement;
              }
              if (!block || block === document.body) return null;
              return {
                followsOverview: (overview.compareDocumentPosition(block)
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
        self.assertTrue(order["followsOverview"],
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


class OverflowTest(F33OutputBrowserTest):
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


if __name__ == "__main__":
    unittest.main()
