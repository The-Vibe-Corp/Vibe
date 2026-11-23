"""Browserabnahme F34, WP6: Ausgabe.

Ableitung ausschließlich aus ``docs/features/F34.md`` — Abschnitt
„WP6 — Ausgabe":

* Kopfzusammenfassung ``div[data-nv-out-summary]``: je Zeile Name, Rolle/
  Agent, Zustand, Modell, Sitzung; Klick fokussiert/scrollt zur zugehörigen
  Karte; bei vielen Subagenten scrollt die Zusammenfassung horizontal
  (``overflow-x``), nicht die Seite.
* Hauptkarte: Titel, Zustand, Sitzung; Fokus-Knopf ``button[data-nv-action=
  "out-focus"]`` mit Icon UND sichtbarem Text; ``pre[data-nv-out-main]`` mit
  ``max-height <= 60vh`` und eigenem Scroll; ``button[data-nv-log-expand]``
  wechselt ``aria-expanded`` zwischen „Alles anzeigen" und „Weniger anzeigen".
* Subagenten-Karten im Raster (zwei Spalten ab 1200 px), je Karte Name,
  Agent, Zustand, Fokus-Knopf, Log ``max-height <= 40vh`` und eigener
  Aufklappen-Knopf; einheitliche Innenabstände.
* Steuerblock oben bleibt: Anweisung, Fortsetzen, Stoppen. „Fortsetzen" hat
  sichtbaren Text, ``small[data-nv-continue-hint]`` erklärt „Sendet ‚weiter‘
  an die laufende Sitzung", die Sitzungs-ID steht im ``title``; ohne
  Sitzung ist der Knopf deaktiviert und erklärt.
* Beendete Läufe: ``button[data-nv-action="session-resume"]`` mit
  Paket-/Sitzungskontext und Erklärung, nicht als nackter Knopf.
* Keine horizontalen Überläufe bei 1280 px (``scrollWidth <= clientWidth``
  der Seite).

Das Dashboard läuft als eigener Prozess auf einem freien Loopback-Port mit
isoliertem ``VIBE``/``HOME``. Lauf und Subagenten werden über das echte
Laufregister und die Zustandsdatei ``proj.log.state.json`` nachgebildet;
die opencode-Attrappe liefert keine Agentennachrichten. Beendete Läufe
werden über ``sessions.json`` (SessionRegistry) nachgebildet. Es gibt keine
Modellaufrufe und keinen Netzzugriff außer Loopback. Die Seite bootet in
deutscher Sprache (``post_language("de")`` → ``<meta>``), die contracts in
den Tests sind daher die deutschen Quelltexte.
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
MAIN_AGENT = "tester-main"
MAIN_SESSION = "ses_f34_main"
SUB_A = "ses_f34_a"
SUB_B = "ses_f34_b"
SUB_C = "ses_f34_c"
SUB_D = "ses_f34_d"
SUB_E = "ses_f34_e"
SUB_F = "ses_f34_f"
PKG_ID = "F34-Ticket-4711"
SES_RESUME = "ses_f34_resume"
MAIN_MARKER = "HAUPT-F34: Hauptagent schreibt sein Protokoll."

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
            json.dumps({"session": MAIN_SESSION, "subagents": entries},
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
        self.write_log(MAIN_MARKER)
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
        self.page.locator("[data-nv-out-overview]").wait_for(
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
        self.assertEqual(MAIN_SESSION, session.inner_text())
        self.assertEqual(MAIN_SESSION, session.get_attribute("title"))

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
        self.write_log(MAIN_MARKER)
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
        self.assertEqual(MAIN_SESSION, session.inner_text())
        self.assertEqual(MAIN_SESSION, session.get_attribute("title"))

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
    def test_two_columns_at_1200px(self):
        """Vorbedingung: Viewport ≥ 1200 px, laufende Subagenten A/B.

        Erwartung: ``div[data-nv-out-subs]`` hat ein Grid-Template mit zwei
        Spalten (``minmax(min(100%, 30rem), 1fr)``,
        ``getComputedStyle(...).gridTemplateColumns`` meldet zwei Tracks);
        beide Karten (``[data-nv-out-sub]``) liegen in derselben Zeile
        (gleiche ``y``-Koordinate im selben ``evaluate``).
        """
        self.seed_live()
        self.set_viewport(1200, 1000)
        self.open_output()
        subs = self.page.locator("div[data-nv-out-subs]").first
        subs.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: subs.locator("[data-nv-out-sub]").count() == 2,
            timeout=20,
            message="Nicht beide Subagenten-Karten im Raster")
        metrics = self.page.evaluate(
            """() => {
              const subs = document.querySelector('div[data-nv-out-subs]');
              const cards = Array.from(
                subs.querySelectorAll('[data-nv-out-sub]'));
              return {
                columns: getComputedStyle(subs)
                  .gridTemplateColumns.trim().split(/\\s+/).filter(Boolean),
                boxes: cards.map(node => {
                  const rect = node.getBoundingClientRect();
                  return {
                    y: rect.y, x: rect.x, width: rect.width, height: rect.height,
                  };
                }),
              };
            }""")
        self.assertGreaterEqual(
            len(metrics["columns"]), 2,
            f"Das Grid-Template hat keine zwei Spalten: {metrics}")
        self.assertEqual(2, len(metrics["boxes"]), "Karten konnten nicht gemessen werden")
        self.assertAlmostEqual(
            metrics["boxes"][0]["y"], metrics["boxes"][1]["y"], delta=1.5,
            msg="Die Karten sind nicht in derselben Zeile — das Raster "
                "liefert keine zwei Spalten: " + repr(metrics))
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
              const overview = document.querySelector(
                '[data-nv-out-overview]');
              const controls = document.querySelector('.nv-out-controls');
              const main = document.querySelector('[data-nv-out-main]');
              if (!overview || !controls || !main) return null;
              return {
                afterOverview: (overview.compareDocumentPosition(controls)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
                beforeLog: (controls.compareDocumentPosition(main)
                  & Node.DOCUMENT_POSITION_FOLLOWING) !== 0,
              };
            }""")
        self.assertIsNotNone(order, "Der Steuerblock wurde nicht gefunden")
        self.assertTrue(order["afterOverview"],
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
        self.assertIn(MAIN_SESSION, title,
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


class OverflowTest(F34OutputBrowserTest):
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


if __name__ == "__main__":
    unittest.main()
