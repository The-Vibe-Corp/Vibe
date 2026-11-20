"""Browserabnahme B20: scrollbare, mitlaufende Vorschaufenster und einheitlicher Fokus.

FEEDBACK.md B20 „AP20 ist fehlerhaft“ meldet drei Beobachtungen an der
Ausgabeansicht:

* Die Vorschaufenster der laufenden Agenten sind ohne Scrollbar.
* Sie zeigen nicht immer die letzten Zeilen; sie wirken eingefroren.
* Die Subagenten-Knöpfe heißen „Vergrößern/Verkleinern“ statt wie der
  Hauptagenten-Knopf „Fokus“.

Fachliche Entscheidung A (beantwortete ``vibe ask``-Rückfrage): Die
Beschriftung der Subagenten-Umschalter wird vereinheitlicht. Karten-Knopf und
Übersichts-Fokus-Knopf lesen „Fokus“; im aktiven Zustand „Fokus beenden“.
Der Name „Vergrößern/Verkleinern“ für Subagenten entfällt.

UI-Vertrag dieser Abnahme (Grundlage für die Implementierung):

* Jedes Vorschaufenster (``pre.bv-log``) der Subagenten-Karten und der
  Hauptagentenansicht ist **in der Standardansicht** scrollbar
  (``overflow-y: auto``). Bei überlangem Inhalt gilt
  ``scrollHeight > clientHeight``; es gibt keinen horizontalen Overflow.
* Trifft neuer Inhalt ein, während das Fenster am Fuße steht, bleibt es am
  Fuße (Autoscroll). Die zuletzt geschriebene Zeile ist sichtbar, nicht
  abgeschnitten. Die Aktualisierung erfolgt weiterhin über das bestehende
  2-Sekunden-Polling.
* Der Karten-Umschalter eines Subagenten und die Fokus-Knöpfe der Übersicht
  sind einheitlich benannt: „Fokus“ bzw. im aktiven Zustand „Fokus beenden“.
  Der Karten-Knopf trägt ``aria-label="Subagent fokussieren"`` und schaltet
  beim Klick die Karte in den ``enlarged``-Zustand (``aria-expanded="true"``);
  ein zweiter Klick hebt beides auf.
* Der Hauptagenten-Knopf liest ebenfalls „Fokus“ (einheitliche Benennung).

Testfälle:

1. test_subagent_preview_is_scrollable_in_normal_mode          [AK1]
   Vorbedingung: aktiver Lauf mit einem laufenden Subagenten und
   überlanger Live-Ausgabe; Ausgabeansicht geöffnet; Viewport 1400×900.
   Aktion: Das Vorschaufenster ``.bv-sub pre.bv-log`` ausmessen.
   Erwartung: Die Karte ist nicht vergrößert; ``overflow-y`` ist ``auto``;
   ``scrollHeight > clientHeight``; kein horizontaler Overflow.
   Fehlerfall (aktueller Zustand): ``overflow-y: hidden`` – das Fenster ist
   nicht scrollbar, lange Ausgabe ist nur abgeschnitten.
2. test_new_content_autoscrolls_preview_to_foot                [AK1]
   Vorbedingung: wie 1; das Fenster steht am Fuße (letzte Zeile sichtbar).
   Aktion: Die opencode-Attrappe liefert eine längere Ausgabe mit neuem
   Endmarker; ohne Neuladen das Polling abwarten.
   Erwartung: Der neue Text erscheint; das Fenster bleibt am Fuße
   (``scrollTop + clientHeight == scrollHeight``), ``scrollTop > 0`` und die
   letzte Zeile liegt vollständig im sichtbaren Fenster.
   Fehlerfall (aktueller Zustand): Das Fenster ist nicht scrollbar, der Fuß
   wird nicht gehalten und neue Zeilen bleiben unsichtbar.
3. test_subagent_toggle_uses_uniform_focus_label               [AK2]
   Vorbedingung: wie 1; Oberflächensprache Deutsch.
   Aktion: Karten-Knopf und Hauptagenten-Knopf auslesen; Karten-Knopf
   anklicken und erneut anklicken.
   Erwartung: Karten-Knopf-Text „Fokus“, ``aria-label="Subagent
   fokussieren"``; Hauptagenten-Knopf ebenfalls „Fokus“; Übersichts-Knopf
   „Fokus“; nach dem Klick „Fokus beenden“, ``aria-expanded="true"`` und
   Karte mit Klasse ``enlarged``; nach dem zweiten Klick wieder „Fokus“,
   ``aria-expanded="false"`` und keine ``enlarged``-Klasse.
   Fehlerfall (aktueller Zustand): „Vergrößern/Verkleinern“ statt „Fokus“.
4. test_main_preview_is_scrollable_in_normal_mode              [AK3]
   Vorbedingung: aktiver Lauf mit überlangem Hauptlog; Ausgabe geöffnet;
   Viewport 1400×900.
   Aktion: Das Hauptfenster ``.bv-main pre.bv-log`` ausmessen.
   Erwartung: ``overflow-y`` ist ``auto``; ``scrollHeight > clientHeight``;
   kein horizontaler Overflow.
   Fehlerfall (aktueller Zustand): ``overflow-y: hidden`` – der Hauptagent
   kann seine letzten Zeilen nicht zeigen.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port und
isolierter VIBE-Umgebung; der opencode-Server ist eine lokale Attrappe, die
die Live-Ausgabe aus einer Datei liefert. Die Oberflächensprache wird vor dem
Seitenaufruf über ``POST /api/language`` auf Deutsch gesetzt, damit die
Umschalter „Fokus“/„Fokus beenden“ heißen (Standard wäre Englisch:
„Focus“/„End focus“). Keine echten Modellaufrufe, keine produktive
Installation.
"""
import http.client
import json
import os
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

AGENT = "vibe-agent"
MAIN_SESSION = "ses_main_b20"
CHILD_SESSION = "ses_kind_b20"
STATIC_OUTPUT = ("Der Subagent arbeitet (sessionID: ses_kind_b20). "
                 "STATISCH-B20-4711")
END_A = "ENDE-A-B20-4711: Der Subagent schließt seine erste Fassung ab."
END_B = "ENDE-B-B20-4711: Der Subagent schreibt die neuen letzten Zeilen."
MAIN_MARKER = "HAUPT-B20-4711: Hauptagent schreibt sein Protokoll."

CARD_LABEL = "Subagent fokussieren"
FOCUS_TEXT = "Fokus"
FOCUS_END_TEXT = "Fokus beenden"

VIEWPORT = {"width": 1400, "height": 900}


def long_text(tag, lines=70):
    """Überlange Ausgabe: deutlich mehr Zeilen als in ein Fenster passen."""
    rows = [f"=== Ausgabe {tag} ==="]
    for index in range(1, lines + 1):
        rows.append(
            f"Zeile {index:02d} ({tag}): Der Agent protokolliert Fortschritt, "
            "geprüfte Dateien und offene Punkte.")
    return "\n".join(rows)


def messages(text):
    return {"data": [
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": text}]},
    ]}


LIVE_A = messages(long_text("B20-A") + "\n" + END_A)
LIVE_B = messages(long_text("B20-B", lines=110) + "\n" + END_B)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: /api/session/<id>/message liefert die Live-Ausgabe."""

    context = None

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
            try:
                payload = json.loads(
                    Path(self.context["messages_path"]).read_text(
                        encoding="utf-8"))
            except (OSError, ValueError):
                payload = {"data": []}
            if "order=asc" not in self.path:
                entries = payload.get("data") if isinstance(payload, dict) else []
                payload = {"data": list(reversed(entries or []))}
            self._send_json(200, payload)
            return
        # Leere Lage für /api/session und /api/session/active: Die
        # Zustandsdatei bleibt maßgeblich für die Subagentenliste.
        self._send_json(200, {"ok": True})


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


# ---------- JS-Messhelfer (robust gegen Umbauten des DOM) ----------

PREVIEW_JS = """(selector) => {
  const pre = document.querySelector(selector);
  if (!pre) return {found: false};
  const style = getComputedStyle(pre);
  const rect = pre.getBoundingClientRect();
  const last = pre.lastElementChild;
  const lastRect = last ? last.getBoundingClientRect() : null;
  return {
    found: true,
    overflowY: style.overflowY,
    overflowX: style.overflowX,
    scrollTop: pre.scrollTop,
    scrollHeight: pre.scrollHeight,
    clientHeight: pre.clientHeight,
    scrollWidth: pre.scrollWidth,
    clientWidth: pre.clientWidth,
    atBottom: pre.scrollHeight - pre.scrollTop - pre.clientHeight <= 2,
    lastVisible: !!lastRect && lastRect.height > 0
      && lastRect.top >= rect.top - 1 && lastRect.bottom <= rect.bottom + 1,
    height: rect.height,
    text: pre.textContent || "",
  };
}"""

CARD_JS = """(session) => {
  const view = document.querySelector(
    "[data-panel='ausgabe'] [data-agent-view][data-role='subagent']"
    + "[data-session='" + session + "']");
  if (!view) return {found: false};
  const head = view.querySelector(".bv-head");
  const toggle = head ? head.querySelector("button") : null;
  return {
    found: true,
    classes: (view.getAttribute("class") || "").split(/\\s+/),
    toggle: toggle ? {
      text: (toggle.innerText || "").trim(),
      label: toggle.getAttribute("aria-label"),
      expanded: toggle.getAttribute("aria-expanded"),
    } : null,
  };
}"""

MAIN_TOGGLE_JS = """() => {
  const view = document.querySelector(
    "[data-panel='ausgabe'] [data-agent-view][data-role='main']");
  if (!view) return {found: false};
  const head = view.querySelector(".bv-head");
  const toggle = head ? head.querySelector("button") : null;
  return {
    found: true,
    toggle: toggle ? {
      text: (toggle.innerText || "").trim(),
      label: toggle.getAttribute("aria-label"),
      expanded: toggle.getAttribute("aria-expanded"),
    } : null,
  };
}"""

OVERVIEW_FOCUS_JS = """() => {
  const button = document.querySelector(
    "[data-panel='ausgabe'] .bv-overview-row button[data-focus-session]");
  return button ? {
    text: (button.innerText || "").trim(),
    label: button.getAttribute("aria-label"),
  } : null;
}"""


class B20BrowserTest(unittest.TestCase):
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
            "# FEEDBACK\n\n- [ ] B20 AP20 ist fehlerhaft\n"
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
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {"messages_path": str(cls.root / "messages.json")}
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context))
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
        self.write_messages(LIVE_A)
        password = self.log_dir / "opencode.password"
        password.write_text("geheim-B20-4711", encoding="utf-8")
        password.chmod(0o600)
        # Deutsch ist für die einheitliche Beschriftung „Fokus“ verbindlich;
        # der Dashboard-Standard wäre Englisch („Focus“/„End focus“).
        status, body = self.post_language("de")
        self.assertEqual(200, status,
                         "Vorbedingung Sprache fehlgeschlagen: "
                         f"{status} {body}")
        self.page_errors = []
        self.dialogs = []
        self.page = self.browser.new_page(viewport=dict(VIEWPORT))
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def tearDown(self):
        self.page.close()

    def post_language(self, lang):
        """Setzt die globale Sprache direkt über die API (Test-Vorbedingung)."""
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def write_messages(self, payload):
        Path(self.context["messages_path"]).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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

    def write_state(self):
        entry = {
            "session": CHILD_SESSION,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Auftrag für tester",
            "status": "running",
            "started": int(time.time()) + 5,
            "ended": 0,
            "output": STATIC_OUTPUT,
        }
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(200)
        self.fail(message)

    def panel(self):
        return self.page.locator("[data-panel='ausgabe']")

    def sub_view(self):
        return self.panel().locator(
            "[data-agent-view][data-role='subagent']"
            f"[data-session='{CHILD_SESSION}']")

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        # Sprachunabhängig: der Projekt-Tablist existiert in jeder Sprache.
        tabs = self.page.locator("[role='tablist'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        # Sprachunabhängig: der Reiter trägt aria-controls='panel-ausgabe'.
        tab = self.page.locator(
            "[role='tab'][aria-controls='panel-ausgabe']").first
        tab.click()
        self.panel().wait_for(state="visible", timeout=15000)

    def open_output_with_running_subagent(self, main_lines=None):
        """Standardvorbedingung: laufender Subagent in geöffneter Ansicht."""
        self.register_run("running")
        self.write_log(*(main_lines if main_lines is not None else [MAIN_MARKER]))
        self.write_state()
        self.open_detail()
        self.open_output()
        view = self.sub_view()
        self.wait_until(
            lambda: view.count() == 1 and view.first.is_visible()
            and view.first.inner_text().strip() != "",
            message="Laufende Subagent-Karte mit Ausgabe fehlt")
        return view.first

    def preview(self, selector):
        return self.page.evaluate(PREVIEW_JS, selector)

    def sub_preview(self):
        return self.preview(
            "[data-panel='ausgabe'] [data-agent-view][data-role='subagent']"
            f"[data-session='{CHILD_SESSION}'] pre.bv-log")

    def main_preview(self):
        return self.preview(
            "[data-panel='ausgabe'] [data-agent-view][data-role='main'] "
            "pre.bv-log")

    def card_state(self):
        return self.page.evaluate(CARD_JS, CHILD_SESSION)

    def main_toggle(self):
        return self.page.evaluate(MAIN_TOGGLE_JS)

    def overview_focus(self):
        return self.page.evaluate(OVERVIEW_FOCUS_JS)

    def assert_scrollable(self, data, what):
        """Gemeinsamer Vertrag: scrollbares Fenster ohne horizontalen Overflow."""
        self.assertTrue(data.get("found"), f"{what} wurde nicht gefunden")
        self.assertEqual(
            "auto", data["overflowY"],
            f"{what} ist in der Standardansicht nicht scrollbar "
            f"(overflow-y={data['overflowY']!r}, erwartet: auto)")
        self.assertGreater(
            data["scrollHeight"], data["clientHeight"] + 4,
            f"{what} hat keinen überlaufenden Inhalt: scrollHeight="
            f"{data['scrollHeight']} px, clientHeight={data['clientHeight']} px")
        self.assertLessEqual(
            data["scrollWidth"], data["clientWidth"] + 2,
            f"{what} hat horizontalen Overflow: scrollWidth="
            f"{data['scrollWidth']} px, clientWidth={data['clientWidth']} px")

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")


class PreviewScrollTest(B20BrowserTest):
    def test_subagent_preview_is_scrollable_in_normal_mode(self):
        """AK1: Das Subagenten-Vorschaufenster ist standardmäßig scrollbar.

        Vorbedingung: aktiver Lauf, ein laufender Subagent mit überlanger
        Live-Ausgabe (70 Zeilen); Ausgabeansicht geöffnet; 1400×900.
        Aktion: ``.bv-sub pre.bv-log`` ausmessen.
        Erwartung: Karte nicht vergrößert; ``overflow-y: auto``;
        ``scrollHeight > clientHeight``; kein horizontaler Overflow.
        Fehlerfall (aktueller Zustand): ``overflow-y: hidden``; die lange
        Ausgabe ist nur abgeschnitten und nicht scrollbar.
        """
        card = self.open_output_with_running_subagent()
        state = self.card_state()
        self.assertTrue(state["found"], "Die Subagent-Karte fehlt")
        self.assertNotIn(
            "enlarged", state["classes"],
            "Die Standardansicht darf nicht vergrößert sein: "
            + repr(state["classes"]))
        data = self.sub_preview()
        self.assert_scrollable(data, "Das Subagenten-Vorschaufenster")
        self.assertIn(
            END_A, data["text"],
            "Die Live-Ausgabe des Subagenten fehlt im Vorschaufenster")
        self.assertNotIn(
            "STATISCH-B20-4711", data["text"],
            "Das Vorschaufenster zeigt den statischen Ersttext statt der "
            "Live-Ausgabe")
        self.assert_clean_page()

    def test_new_content_autoscrolls_preview_to_foot(self):
        """AK1: Neuer Inhalt hält das Vorschaufenster am Fuße.

        Vorbedingung: wie 1; das Fenster steht am Fuße (letzte Zeile
        sichtbar), die Live-Ausgabe endet mit ENDE-A-B20-4711.
        Aktion: Die opencode-Attrappe liefert eine längere Ausgabe mit dem
        neuen Endmarker ENDE-B-B20-4711; ohne Neuladen das 2-Sekunden-Polling
        abwarten.
        Erwartung: Der neue Marker erscheint; das Fenster bleibt am Fuße
        (``scrollTop + clientHeight == scrollHeight``), ``scrollTop > 0`` und
        die letzte Zeile liegt vollständig im sichtbaren Fenster.
        Fehlerfall (aktueller Zustand): Das Fenster ist nicht scrollbar, der
        Fuß wird nicht gehalten, neue Zeilen bleiben unsichtbar.
        """
        self.open_output_with_running_subagent()
        self.wait_until(
            lambda: END_A in self.sub_preview().get("text", ""),
            message="Die erste Live-Ausgabe (ENDE-A-B20-4711) fehlt")
        before = self.sub_preview()
        self.assert_scrollable(before, "Das Subagenten-Vorschaufenster")
        self.assertTrue(
            before["atBottom"],
            "Das Fenster steht nach dem ersten Befüllen nicht am Fuße: "
            f"scrollTop={before['scrollTop']}, scrollHeight="
            f"{before['scrollHeight']}, clientHeight={before['clientHeight']}")
        self.assertTrue(
            before["lastVisible"],
            "Die letzte Zeile der ersten Fassung ist nicht sichtbar")

        self.write_messages(LIVE_B)
        self.wait_until(
            lambda: END_B in self.sub_preview().get("text", ""),
            message="Die neue Live-Ausgabe (ENDE-B-B20-4711) erscheint beim "
                    "Polling nicht")
        after = self.sub_preview()
        self.assert_scrollable(after, "Das Subagenten-Vorschaufenster")
        self.assertGreater(
            after["scrollHeight"], before["scrollHeight"],
            "Die Live-Ausgabe ist nicht gewachsen: scrollHeight blieb bei "
            f"{after['scrollHeight']} px")
        self.assertGreater(
            after["scrollTop"], 0,
            "Das Fenster ist nicht gescrollt (scrollTop=0); der Fuß der "
            "Ausgabe ist nicht erreichbar")
        self.assertTrue(
            after["atBottom"],
            "Das Fenster folgt dem neuen Inhalt nicht bis zum Fuß: "
            f"scrollTop={after['scrollTop']}, scrollHeight="
            f"{after['scrollHeight']}, clientHeight={after['clientHeight']}")
        self.assertTrue(
            after["lastVisible"],
            "Die neue letzte Zeile (ENDE-B-B20-4711) liegt außerhalb des "
            "sichtbaren Fensters")
        self.assert_clean_page()


class FocusNamingTest(B20BrowserTest):
    def test_subagent_toggle_uses_uniform_focus_label(self):
        """AK2: Subagenten-Umschalter heißen einheitlich „Fokus“.

        Vorbedingung: laufende Subagent-Karte; Oberflächensprache Deutsch.
        Aktion: Karten-Knopf und Hauptagenten-Knopf auslesen; den
        Karten-Knopf anklicken und ein zweites Mal anklicken.
        Erwartung: Karten-Knopf „Fokus“ mit ``aria-label="Subagent
        fokussieren"``; Hauptagenten-Knopf „Fokus“; Übersichts-Knopf
        „Fokus“; nach dem Klick „Fokus beenden“, ``aria-expanded="true"``
        und Karte ``enlarged``; nach dem zweiten Klick wieder „Fokus“,
        ``aria-expanded="false"`` ohne ``enlarged``.
        Fehlerfall (aktueller Zustand): „Vergrößern/Verkleinern“ statt
        „Fokus“.
        """
        self.open_output_with_running_subagent()
        self.assertEqual(
            "de", self.page.evaluate("() => document.documentElement.lang"),
            "Die Oberfläche wurde nicht auf Deutsch gestellt; die "
            "Beschriftung „Fokus“ ist so nicht prüfbar")

        state = self.card_state()
        self.assertTrue(state["found"], "Die Subagent-Karte fehlt")
        toggle = state["toggle"]
        self.assertIsNotNone(toggle, "Die Subagent-Karte hat keinen "
                                     "Karten-Knopf im Kopf (.bv-head button)")
        self.assertEqual(
            FOCUS_TEXT, toggle["text"],
            f"Der Karten-Knopf heißt {toggle['text']!r} statt 'Fokus'")
        self.assertEqual(
            CARD_LABEL, toggle["label"],
            f"Der Karten-Knopf trägt aria-label={toggle['label']!r} statt "
            f"{CARD_LABEL!r}")
        self.assertEqual(
            "false", toggle["expanded"],
            "Der Karten-Knopf startet nicht mit aria-expanded='false'")

        main = self.main_toggle()
        self.assertTrue(main["found"], "Die Hauptagentenansicht fehlt")
        self.assertIsNotNone(main["toggle"],
                             "Der Hauptagent hat keinen Fokus-Knopf")
        self.assertEqual(
            FOCUS_TEXT, main["toggle"]["text"],
            "Der Hauptagenten-Knopf heißt "
            f"{main['toggle']['text']!r} statt 'Fokus'; die Benennung ist "
            "nicht einheitlich")

        overview = self.overview_focus()
        self.assertIsNotNone(
            overview, "Die Übersicht hat keinen Fokus-Knopf")
        self.assertEqual(
            FOCUS_TEXT, overview["text"],
            f"Der Übersichts-Knopf heißt {overview['text']!r} statt 'Fokus'")

        self.sub_view().locator(".bv-head button").first.click()
        self.wait_until(
            lambda: self.card_state()["toggle"]["text"] == FOCUS_END_TEXT,
            message="Nach dem Fokus heißt der Karten-Knopf nicht "
                    f"{FOCUS_END_TEXT!r}")
        state = self.card_state()
        self.assertEqual(
            "true", state["toggle"]["expanded"],
            "Der Karten-Knopf meldet im Fokus nicht aria-expanded='true'")
        self.assertIn(
            "enlarged", state["classes"],
            "Der Karten-Knopf vergrößert die Karte nicht "
            f"(class={state['classes']!r})")

        self.sub_view().locator(".bv-head button").first.click()
        self.wait_until(
            lambda: self.card_state()["toggle"]["text"] == FOCUS_TEXT,
            message="Nach dem zweiten Klick heißt der Karten-Knopf nicht "
                    f"wieder {FOCUS_TEXT!r}")
        state = self.card_state()
        self.assertEqual(
            "false", state["toggle"]["expanded"],
            "Nach dem zweiten Klick meldet der Karten-Knopf nicht "
            "aria-expanded='false'")
        self.assertNotIn(
            "enlarged", state["classes"],
            "Nach dem zweiten Klick bleibt die Karte vergrößert: "
            + repr(state["classes"]))
        self.assert_clean_page()


class MainPreviewTest(B20BrowserTest):
    def test_main_preview_is_scrollable_in_normal_mode(self):
        """AK3: Auch das Hauptagenten-Fenster ist standardmäßig scrollbar.

        Vorbedingung: aktiver Lauf mit überlangem Hauptlog (70 Zeilen);
        Ausgabeansicht geöffnet; 1400×900.
        Aktion: ``.bv-main pre.bv-log`` ausmessen.
        Erwartung: ``overflow-y: auto``; ``scrollHeight > clientHeight``;
        kein horizontaler Overflow; der Hauptmarker steht im Text.
        Fehlerfall (aktueller Zustand): ``overflow-y: hidden``; der
        Hauptagent kann seine letzten Zeilen nicht anzeigen.
        """
        lines = [MAIN_MARKER]
        for index in range(1, 71):
            lines.append(
                f"Zeile {index:02d} des Hauptagenten: Er protokolliert "
                "Fortschritt, geprüfte Dateien und offene Punkte.")
        self.open_output_with_running_subagent(main_lines=lines)
        self.wait_until(
            lambda: MAIN_MARKER in self.main_preview().get("text", ""),
            message="Der Hauptmarker erscheint nicht im "
                    "Hauptagenten-Vorschaufenster")
        data = self.main_preview()
        self.assert_scrollable(data, "Das Hauptagenten-Vorschaufenster")
        self.assertIn(
            MAIN_MARKER, data["text"],
            "Der Hauptmarker fehlt im Hauptagenten-Vorschaufenster")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
