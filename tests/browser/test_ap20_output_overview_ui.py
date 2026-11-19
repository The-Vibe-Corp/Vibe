"""Browserabnahme AP20: übersichtliche Ausgabeansicht ohne verschachtelte Scrollbars.

Ticket AP20 (``TICKETS.md``) zeigt im Screenshot ``vibe_ui.png`` das
Ausgabe-Panel mit mehrfach verschachtelten Scrollbars und einer
unübersichtlichen horizontalen Reihe von Subagent-Karten. Ziel ist ein
Neuaufbau der Ansicht:

* höchstens **ein** Scrollbereich je Modus,
* eine kompakte Statusübersicht über alle aktiven Agenten,
* ein umbrechendes Kartenraster statt einer einseitig herausgeschnittenen
  Leiste,
* ein Fokus-Modus, der genau eine Karte ansichtsfüllend zeigt und deren
  Ausgabe scrollbar macht.

Der bestehende B11/F30-Vertrag bleibt unverändert gültig (Panel, Agenten-
ansichten, Zielauswahl, Karten, Vergrößerung, Highlighter).

Verbindlicher UI-Vertrag dieser Abnahme:

1. **Bestand (B11/F30):** Panel ``[data-panel='ausgabe']``; Hauptagent und
   jeder laufende Subagent als
   ``[data-agent-view][data-role='main'|'subagent'][data-session=…]`` mit
   ``role='log'``; sechs laufende Subagenten sind gleichzeitig im DOM und
   sichtbar; ``select[aria-label='Ziel']``, ``textarea`` mit
   ``aria-label*='Zusatzanweisung'``, Senden-Knopf, Fortsetzen-Knopf,
   ``.bv-log`` mit Highlighter-Spans (``hl-*``), ``.bv-subs``,
   ``.bv-sub``-Karten ≥ 300 px, Vergrößern-Knopf (``aria-label`` enthält
   „vergrö“), Vergrößerung ≥ 70 % Viewporthöhe und ≥ 60 % Viewportbreite,
   kein Modal und keine ``role='tablist'`` im Ausgabebereich.
2. **Übersicht:** ``[data-panel='ausgabe'] .bv-overview[aria-label='Aktive
   Agenten'][data-active-agents='6']`` mit sichtbarem Zählertext, der „6“
   enthält, und je laufendem Agenten (inklusive Hauptsession) einer Zeile
   ``.bv-overview-row[data-overview-session='<session>']`` mit Agentenname,
   gekürzter Beschreibung, Status-Pille und Fokus-Knopf
   ``button[data-focus-session='<session>'][aria-label*='fokussieren']``.
3. **Scrollbar-Abnahme (Kern des Tickets):** ``.bv-subs`` hat keinen
   horizontalen Overflow (``scrollWidth <= clientWidth + 2``) bei sechs
   Karten und 1400 px sowie 900 px Viewport. Jedes
   ``[data-agent-view] .bv-log`` hat im Normalmodus berechnetes
   ``overflow-y: hidden``. Im Panel existiert höchstens ein tatsächlich
   scrollbarer Bereich (``overflow-y`` ``auto``/``scroll`` **und**
   ``scrollHeight > clientHeight``) – der panelweite Container. Kein Element
   hat horizontalen scrollbaren Overflow.
4. **Raster:** Die sechs Subagent-Karten liegen in mindestens zwei Zeilen
   (unterschiedliche ``y``-Werte) und vollständig innerhalb der Panelbreite
   (rechte Kante ≤ Panel rechts + 2).
5. **Fokus-Modus:** Der Fokus-Knopf der Übersicht, der Vergrößern-Knopf
   jeder Karte und der Fokus-Knopf im Kopf des Hauptagenten schalten
   denselben Zustand: genau eine Ansicht (``enlarged``, ≥ 70 % vh /
   ≥ 60 % vw), deren ``.bv-log`` berechnetes ``overflow-y: auto`` und der
   einzige Scrollbereich ist; die Live-Ausgabe aktualisiert sich weiter;
   Escape und ein zweiter Klick stellen die Normalgröße wieder her. Der
   Zustand steht an allen Fokus-Knöpfen und an der zugehörigen
   Übersichtszeile in ``aria-expanded``.
6. **Regression:** Die bestehenden Suiten bleiben unverändert gültig.

Testfälle (12):

1. test_b11_f30_contract_remains_with_six_subagents          [AK1]
   Vorbedingung: aktiver Lauf, Hauptlog, sechs laufende Subagenten mit
   umfangreicher Ausgabe.
   Aktion: Ausgabebereich öffnen; am Ende den Lauf auf ``finished`` setzen.
   Erwartung: Panel, sieben Agentenansichten (Haupt + 6) gleichzeitig sichtbar
   und Live-Regionen, Zielauswahl mit sieben Optionen, Anweisungseingabe,
   Senden-Knopf, Highlighter-Spans, ``.bv-subs``, Kartenhöhe ≥ 300 px,
   Vergrößern-Knopf in jeder Karte, kein Modal, keine Tabliste; bei
   gestopptem Lauf erscheint „Fortsetzen“.
   Fehlerfall: Der Neuaufbau bricht den bestehenden Vertrag.
2. test_overview_lists_all_agents_with_compact_rows          [AK2]
   Vorbedingung: wie 1.
   Aktion: Übersicht auslesen.
   Erwartung: ``.bv-overview`` mit ``data-active-agents='6'``, Zählertext
   enthält „6“, sieben kompakte Zeilen (Hauptsession + 6 Subagenten) mit
   Name, gekürzter Beschreibung, Status-Pille und Fokus-Knopf je Subagent.
   Fehlerfall: Übersicht fehlt, ist unvollständig oder nicht kompakt.
3. test_normal_mode_has_no_nested_scrollbars_at_1400         [AK3]
   Vorbedingung: sechs Karten, Viewport 1400×900.
   Aktion: Layout messen.
   Erwartung: ``.bv-subs`` ohne horizontalen Overflow; jedes ``.bv-log``
   ``overflow-y: hidden``; höchstens ein scrollbarer Bereich (panelweit);
   kein horizontaler Scrollbereich.
   Fehlerfall: Innere Scrollleisten (Ticket-Screenshot).
4. test_narrow_viewport_has_no_horizontal_overflow_at_900    [AK3]
   Vorbedingung: wie 3, Viewport 900×900.
   Erwartung: ``.bv-subs`` ohne horizontalen Overflow; höchstens ein
   scrollbarer Bereich; kein horizontaler Scrollbereich.
   Fehlerfall: Kartenleiste wird bei schmalem Viewport seitlich abgeschnitten.
5. test_subagent_cards_wrap_into_rows_within_the_panel       [AK4]
   Vorbedingung: wie 3.
   Erwartung: Karten in ≥ 2 Zeilen; rechte Kante ≤ Panel rechts + 2.
   Fehlerfall: Einseitig herausgeschnittene horizontale Leiste.
6. test_overview_focus_enlarges_one_card_and_unlocks_scroll  [AK5]
   Vorbedingung: wie 3.
   Aktion: Fokus-Knopf der Übersicht für Session A klicken; Zustandsdatei mit
   neuem Marker überschreiben; Fokus ausschließlich per Escape beenden.
   Erwartung: Nur Karte A ``enlarged`` und ≥ 70 % vh / ≥ 60 % vw; ihr
   ``.bv-log`` ``overflow-y: auto`` und einziger Scrollbereich; neuer Marker
   erscheint; ``aria-expanded`` an Karten- und Übersichts-Knopf ist ``true``
   und nach Escape wieder ``false``; nach dem Beenden normale Größe und
   ``overflow-y: hidden``.
   Fehlerfall: Kein Fokus, falsche Karte, eingefrorene Ausgabe, fehlender
   Escape-Handler oder verschachtelte Scrollbereiche.
7. test_second_focus_click_restores_normal_mode              [AK5]
   Vorbedingung: Fokus auf Karte A ist aktiv.
   Aktion: Derselbe Übersichts-Fokus-Knopf ein zweites Mal auslösen (ohne
   Escape).
   Erwartung: Karte A ist wieder normal groß, ``overflow-y: hidden``,
   ``aria-expanded`` wieder ``false``, höchstens ein Scrollbereich.
   Fehlerfall: Der zweite Klick hebt den Fokus nicht auf.
8. test_card_button_and_overview_focus_share_the_same_state  [AK5]
   Vorbedingung: wie 3.
   Aktion: Karten-Vergrößern-Knopf von A; Übersichts-Fokus-Knopf von A
   (programmatischer Klick, da die vergrößerte Karte die Übersicht überdeckt);
   danach Fokus erneut über die Übersicht; dann den Karten-Knopf
   „Verkleinern“.
   Erwartung: Jeder Weg hebt den Zustand des anderen auf; die Karte ist
   jeweils genau einmal vergrößert bzw. normal; ``aria-expanded`` an beiden
   Knöpfen folgt dem Zustand.
   Fehlerfall: Zwei getrennte Zustände – der eine Knopf hebt den anderen
   nicht auf.
9. test_main_agent_header_focus_button_enlarges_main_view    [AK5]
   Vorbedingung: wie 3, zusätzlich lange Hauptausgabe.
   Aktion: Fokus-Knopf im Kopf des Hauptagenten klicken; per Escape beenden;
   erneut fokussieren und per zweitem Klick beenden.
   Erwartung: Hauptansicht ``enlarged`` und ≥ 70 % vh / ≥ 60 % vw; ihr
   ``.bv-log`` ``overflow-y: auto`` und einziger Scrollbereich; danach
   normale Größe und ``overflow-y: hidden``. ``aria-expanded`` an diesem
   Knopf und an der Übersichtszeile des Hauptagenten ist jeweils ``true``
   bzw. ``false``.
   Fehlerfall: Der Knopf im Hauptkopf ist ohne Funktion (belegter Bug im
   aktuellen Arbeitsbaum).
10. test_session_switch_with_active_focus_keeps_no_orphan_state [AK6]
    Vorbedingung: Fokus auf Subagent A; sechs laufende Subagenten.
    Aktion: Hauptsession in der Zustandsdatei auf eine neue Kennung setzen.
    Erwartung: Kein verwaister Fokus und keine ``enlarged``-Hauptansicht der
    alten Session; genau ein Scrollbereich (Karte A); die Übersichtszeile der
    Hauptsession folgt der neuen Kennung, die alte Zeile verschwindet;
    ``aria-expanded`` bleibt konsistent.
    Fehlerfall: Alter Fokus/Zustand bleibt hängen oder die Übersicht führt
    weiter die alte Hauptsession.
11. test_zero_running_subagents_shows_empty_overview         [AK2/AK3]
    Vorbedingung: aktiver Lauf, Zustandsdatei ohne Subagenten.
    Aktion: Ausgabe öffnen und Übersicht auslesen.
    Erwartung: ``.bv-overview[data-active-agents='0']`` mit sichtbarem
    Leerzustandstext; ``.bv-subs`` ausgeblendet; genau eine Agentenansicht
    (Hauptagent); höchstens ein Scrollbereich; keine JS-Fehler.
    Fehlerfall: Leerzustand fehlt, Subagentenbereich bleibt sichtbar oder die
    Ansicht erzeugt Fehler.
12. test_finished_subagent_leaves_overview_and_view           [AK2]
    Vorbedingung: wie 1.
    Aktion: Subagent A in der Zustandsdatei auf ``completed`` setzen.
    Erwartung: Ansicht und Übersichtszeile von A verschwinden;
    ``data-active-agents`` wird „5“; Hauptagent und die übrigen fünf bleiben.
    Fehlerfall: Beendete Agenten bleiben in der Übersicht stehen.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port,
isoliertem VIBE-Root und einer lokalen opencode-Attrappe, die keine
Nachrichten liefert; die Ausgabe kommt damit aus der Zustandsdatei
(State-Fallback) und wird durch Überschreiben derselben live verlängert.
Keine echten Modellaufrufe, keine produktive Installation.
"""
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
MAIN_SESSION = "ses_main_ap20"
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
    passen: Nur so ist im Basisstand tatsächlich eine innere Scrollleiste
    vorhanden und die Abnahme „höchstens ein Scrollbereich“ aussagekräftig.
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
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
  const overview = panel.querySelector(".bv-overview[aria-label='Aktive Agenten']");
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

    def write_state(self, subs=None, main_session=MAIN_SESSION):
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

    def open_six_running(self, main_lines=None):
        """Standardvorbedingung: Hauptagent + sechs laufende Subagenten."""
        self.register_run("running")
        self.write_log(*(main_lines if main_lines is not None
                         else [MAIN_MARKER]))
        self.write_state()
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
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
        buttons = self.sub_view(session).locator("button")
        for index in range(buttons.count()):
            candidate = buttons.nth(index)
            label = (candidate.get_attribute("aria-label") or "").lower()
            if "vergrö" in label or "verklein" in label:
                return candidate
        self.fail(f"Kein Vergrößern-Knopf in der Karte {session} gefunden")

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
            "button[data-focus-session][aria-label*='fokussieren']")

    def main_overview_focus_button(self, session=MAIN_SESSION):
        """Fokus-Knopf der Übersichtszeile des Hauptagenten."""
        return self.panel().locator(
            f".bv-overview-row[data-overview-session='{session}'] "
            "button[data-focus-session][aria-label*='fokussieren']")

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
        ``.bv-subs``, Karten ≥ 300 px, Vergrößern-Knopf in jeder Karte, kein
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
            {MAIN_SESSION, *SESSIONS}, set(sessions_in_dom),
            "Nicht alle Agenten sind gleichzeitig im DOM: "
            + repr(sessions_in_dom))

        select = self.panel().locator("select[aria-label='Ziel']")
        self.assertEqual(1, select.count(),
                         "Keine Zielauswahl (select[aria-label='Ziel'])")
        options = self.page.eval_on_selector_all(
            "[data-panel='ausgabe'] select[aria-label='Ziel'] option",
            "nodes => nodes.map(node => node.value)")
        self.assertEqual(
            {MAIN_SESSION, *SESSIONS}, set(options),
            "Zielauswahl enthält nicht alle Agenten: " + repr(options))

        self.assertEqual(
            1, self.panel().locator(
                "textarea[aria-label*='Zusatzanweisung']").count(),
            "Keine Anweisungseingabe (aria-label „Zusatzanweisung“)")
        self.assertGreater(
            self.panel().locator("button").filter(has_text="senden").count(),
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
            has_text="Fortsetzen").first
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
        expected = {MAIN_SESSION, *SESSIONS}
        self.assertEqual(
            expected, set(rows),
            "Die Übersichtszeilen nennen nicht alle Agenten: "
            + repr([row["session"] for row in data["rows"]]))
        self.assertEqual(
            len(expected), len(data["rows"]),
            "Die Übersicht rendert Duplikate statt genau einer Zeile je "
            "Agent: " + repr([row["session"] for row in data["rows"]]))

        main_row = rows[MAIN_SESSION]
        self.assertIn("Hauptagent", main_row["text"],
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
            self.assertIn(
                "fokussieren", (row["focusLabel"] or "").lower(),
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
            {MAIN_SESSION, *SESSIONS[1:]}, set(sessions),
            "Nach dem Abschluss fehlen weitere Agenten in der Übersicht: "
            + repr(sessions))
        self.assertTrue(
            self.agent_view(role="main").first.is_visible(),
            "Der Hauptagent verschwand mit dem abgeschlossenen Subagenten")
        self.assert_clean_page()


class ScrollbarTest(AP20BrowserTest):
    def test_normal_mode_has_no_nested_scrollbars_at_1400(self):
        """AK3: Im Normalmodus gibt es keine verschachtelten Scrollleisten.

        Vorbedingung: sechs laufende Subagenten, Viewport 1400×900.
        Aktion: Panel, ``.bv-subs`` und jede Agenten-Ausgabefläche messen.
        Erwartung: ``.bv-subs`` ohne horizontalen Overflow
        (``scrollWidth <= clientWidth + 2``); jedes ``[data-agent-view]
        .bv-log`` mit berechnetem ``overflow-y: hidden``; höchstens ein
        tatsächlich scrollbarer Bereich im Panel, und dieser ist panelweit
        (enthält alle Agentenansichten); kein horizontal scrollbarer
        Bereich.
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
                "hidden", log["overflowY"],
                f"Die Ausgabefläche von {log['role']}/{log['session']} hat "
                f"im Normalmodus overflow-y={log['overflowY']!r} "
                "(erwartet: hidden)")

        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Im Ausgabepanel existieren mehrere scrollbare Bereiche: "
            + repr(layout["scrollable"]))
        if layout["scrollable"]:
            self.assertTrue(
                layout["scrollable"][0]["panelWide"],
                "Der einzige scrollbare Bereich ist nicht der panelweite "
                "Container: " + repr(layout["scrollable"][0]))
        self.assertEqual(
            [], layout["horizontal"],
            "Elemente mit horizontalem scrollbaren Overflow: "
            + repr(layout["horizontal"]))
        self.assert_clean_page()

    def test_narrow_viewport_has_no_horizontal_overflow_at_900(self):
        """AK3: Auch bei 900 px Viewport keine horizontale Kartenleiste.

        Vorbedingung: sechs laufende Subagenten; Viewport 900×900.
        Aktion: Viewport verkleinern und messen.
        Erwartung: ``.bv-subs`` ohne horizontalen Overflow; höchstens ein
        scrollbarer Bereich; kein horizontal scrollbarer Bereich.
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
        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Im Ausgabepanel existieren bei 900 px mehrere scrollbare "
            "Bereiche: " + repr(layout["scrollable"]))
        self.assertEqual(
            [], layout["horizontal"],
            "Bei 900 px existieren horizontal scrollbare Bereiche: "
            + repr(layout["horizontal"]))
        for log in layout["logs"]:
            self.assertEqual(
                "hidden", log["overflowY"],
                f"Die Ausgabefläche von {log['role']}/{log['session']} hat "
                f"bei 900 px overflow-y={log['overflowY']!r} "
                "(erwartet: hidden)")
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
        ≥ 60 % vw; ihr ``.bv-log`` hat berechnetes ``overflow-y: auto`` und
        ist der einzige scrollbare Bereich; der neue Marker erscheint ohne
        Neuladen; ``aria-expanded`` an Karten- und Übersichts-Knopf ist
        ``true`` und nach Escape wieder ``false``; danach ist die Karte
        normal groß und die Ausgabefläche wieder ``overflow-y: hidden``.
        Fehlerfall: Kein Fokus, falsche Karte, eingefrorene Ausgabe, ein
        fehlender Escape-Handler oder verschachtelte Scrollbereiche.
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
        self.assertEqual(
            1, len(layout["scrollable"]),
            "Im Fokus-Modus muss genau ein Bereich scrollbar sein: "
            + repr(layout["scrollable"]))
        self.assertEqual(
            target, layout["scrollable"][0]["session"],
            "Der einzige scrollbare Bereich gehört nicht zur fokussierten "
            "Karte: " + repr(layout["scrollable"][0]))

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
            "hidden", target_log["overflowY"],
            "Nach dem Beenden des Fokus bleibt die Ausgabefläche scrollbar: "
            + repr(target_log))
        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Nach dem Beenden des Fokus existieren mehrere scrollbare "
            "Bereiche: " + repr(layout["scrollable"]))
        self.assert_clean_page()

    def test_card_button_and_overview_focus_share_the_same_state(self):
        """AK5: Karten-Knopf und Übersichts-Fokus teilen denselben Zustand.

        Vorbedingung: sechs laufende Subagenten; Karte A normal groß.
        Aktion: Karten-Vergrößern-Knopf von A klicken; dann den
        Übersichts-Fokus-Knopf von A (programmatischer Klick, weil die
        vergrößerte Karte die Übersicht überdeckt); dann Fokus erneut über
        die Übersicht; schließlich den Karten-Knopf „Verkleinern“.
        Erwartung: Jeder Weg hebt den Zustand des anderen auf; nach dem
        Karten-Knopf ist A vergrößert und ein Klick auf den Fokus-Knopf
        stellt die Normalgröße her; umgekehrt hebt der Karten-Knopf den
        Übersichts-Fokus auf.
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

        shrink = self.sub_view(target).locator("button").filter(
            has_text="Verkleinern").first
        if shrink.count() == 0:
            # Alternativ trägt der Knopf weiterhin sein aria-label.
            card_button.click()
        else:
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
        Erwartung: Karte A ist wieder normal groß, ihr ``.bv-log`` hat
        ``overflow-y: hidden``, ``aria-expanded`` an Übersichts- und
        Karten-Knopf ist wieder ``false`` und es existiert höchstens ein
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
            "hidden", target_log["overflowY"],
            "Nach dem zweiten Klick bleibt die Ausgabefläche scrollbar: "
            + repr(target_log))
        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Nach dem zweiten Klick existieren mehrere scrollbare Bereiche: "
            + repr(layout["scrollable"]))
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
        ``.bv-log`` hat ``overflow-y: auto`` und ist der einzige
        Scrollbereich; danach normale Größe und ``overflow-y: hidden``.
        ``aria-expanded`` an diesem Knopf und an der Übersichtszeile des
        Hauptagenten ist ``true`` bzw. ``false``.
        Fehlerfall: Der Knopf im Hauptkopf ist ohne Funktion (belegter Bug im
        aktuellen Arbeitsbaum), der Fokus gilt der falschen Ansicht oder es
        entstehen mehrere Scrollbereiche.
        """
        self.open_six_running(main_lines=self.long_main_log())
        self.wait_for_overview(active=6)
        header_button = self.main_focus_button()
        row_button = self.main_overview_focus_button(MAIN_SESSION)
        self.assertEqual(
            1, header_button.count(),
            "Im Kopf der Hauptagentenansicht fehlt der Fokus-Knopf "
            "button[data-focus-session][aria-label*='fokussieren']")
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
        self.assertEqual(
            1, len(layout["scrollable"]),
            "Im Haupt-Fokus muss genau ein Bereich scrollbar sein: "
            + repr(layout["scrollable"]))
        self.assertEqual(
            "main", layout["scrollable"][0]["role"],
            "Der einzige scrollbare Bereich gehört nicht zur Hauptansicht: "
            + repr(layout["scrollable"][0]))
        self.assertEqual(
            MAIN_SESSION, layout["scrollable"][0]["session"],
            "Der einzige scrollbare Bereich gehört nicht zur Hauptsession: "
            + repr(layout["scrollable"][0]))

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
            "hidden", main_log["overflowY"],
            "Nach dem Beenden des Haupt-Fokus bleibt die Ausgabefläche "
            "scrollbar: " + repr(main_log))
        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Nach dem Beenden des Haupt-Fokus existieren mehrere scrollbare "
            "Bereiche: " + repr(layout["scrollable"]))

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
        der alten Session; weiterhin genau ein Scrollbereich (Karte A); die
        Übersichtszeile der Hauptsession folgt der neuen Kennung und die alte
        Zeile verschwindet; ``aria-expanded`` bleibt konsistent.
        Fehlerfall: Der alte Fokus oder die alte Hauptsession bleibt hängen,
        oder es entstehen zwei Scrollbereiche.
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
            MAIN_SESSION, rows,
            "Die alte Hauptsession bleibt als verwaiste Zeile in der "
            "Übersicht: " + repr(rows))
        self.assertIn(
            "Hauptagent", rows[NEW_MAIN_SESSION]["text"],
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
        self.assertEqual(
            1, len(layout["scrollable"]),
            "Beim Hauptsession-Wechsel entstand ein zweiter Scrollbereich: "
            + repr(layout["scrollable"]))
        self.assertEqual(
            target, layout["scrollable"][0]["session"],
            "Der einzige Scrollbereich gehört nicht zum fokussierten "
            "Subagenten: " + repr(layout["scrollable"][0]))
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
        Agentenansicht (Hauptagent); höchstens ein Scrollbereich; keine
        JS-Fehler.
        Fehlerfall: Der Leerzustand fehlt, der Subagentenbereich bleibt
        sichtbar oder die Ansicht erzeugt JavaScript-Fehler.
        """
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state(subs=[])
        self.open_detail()
        self.open_output()
        self.wait_for_view("main", MAIN_SESSION, MAIN_MARKER)
        data = self.wait_for_overview(active=0)

        self.assertEqual(
            "0", data["active"],
            "Die Übersicht meldet ohne Subagenten nicht "
            f"data-active-agents='0': {data!r}")
        self.assertEqual(
            [MAIN_SESSION], [row["session"] for row in data["rows"]],
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
        self.assertLessEqual(
            len(layout["scrollable"]), 1,
            "Ohne Subagenten existieren mehrere scrollbare Bereiche: "
            + repr(layout["scrollable"]))
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
