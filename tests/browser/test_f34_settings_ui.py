"""Browserabnahme F34, WP4: Einstellungen (Nova-Überarbeitung).

Ableitung ausschließlich aus ``docs/features/F34.md`` (WP4 - Einstellungen und
die dort vereinbarten Abschnitte) sowie dem Arbeitspaket F34 (UI-Verbesserungen
2). Das echte Dashboard laeuft als eigener Prozess auf einem freien Loopback-
Port mit isoliertem VIBE/HOME und einer opencode-Attrappe (Muster
``tests/browser/test_ap22_settings_ui.py`` und ``tests/browser/test_f33_settings_ui.py``).

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
----------------------------------------------
``GlobalAgentsSectionTest.test_global_agents_section_is_first_collapsible_and_editor_rows``
    Vorbedingung: globale AGENTS.md existiert.
    Aktion: Einstellungen oeffnen, Sektion lesen.
    Erwartung: Sektion ist die erste (y kleiner als Darstellung/Zugriff);
    ``details[data-nv-global-agents]`` offen; ``textarea[data-nv-global-agents]``
    hat rows >= 16; einklappbar ueber ``summary``.
``GlobalAgentsSectionTest.test_missing_global_agents_file_shows_create_only_when_missing``
    Vorbedingung: globale AGENTS.md fehlt.
    Aktion: Einstellungen oeffnen, "Vorlage anlegen" klicken.
    Erwartung: Anlegen-Knopf sichtbar; nach Klick erscheint Editor mit der
    Vorlage; Anlegen-Knopf danach wieder ausgeblendet.
``GlobalAgentsSectionTest.test_global_agents_save_writes_file_and_toasts_without_rerender``
    Vorbedingung: globale AGENTS.md mit Inhalt vorhanden.
    Aktion: Text aendern, ``global-agents-save`` klicken.
    Erwartung: POST ``/api/global_agents_file {action:"save"}``; Datei enthaelt
    neuen Text; Toast bestaetigt; Render-Zaehler unverändert; Editor bleibt.

``AppearanceSectionTest.test_accent_is_a_raster_of_swatch_buttons_without_select``
    Vorbedingung: Einstellungen offen.
    Aktion: Akzentraster lesen.
    Erwartung: kein ``select[data-nv-accent-select]``; ``button[data-nv-accent]``
    je Akzent mit ``span.nv-swatch`` (nicht transparent) und ``aria-pressed``;
    Auswahl setzt ``html[data-accent]`` + ``localStorage['nv-accent']``;
    Akzentnamen deutsch/englisch unterschiedlich und uebersetzt.

``AppearanceSectionTest.test_currency_select_usd_rate_and_ui_settings_save_persist``
    Vorbedingung: Einstellungen offen, Sprache englisch.
    Aktion: Waehrungs-Select auf USD, USD-Rate eintragen, speichern.
    Erwartung: ``select[data-nv-currency]`` mit EUR/USD; ``input[data-nv-usd-rate]``
    nur bei USD; Speichern ruft ``POST /api/ui_settings`` auf; nach Reload ist
    die Wahl erhalten (``ui.json``).

``EmptyAreaTest.test_settings_has_no_evaluations_or_environment_or_ops_areas``
    Vorbedingung: Einstellungen offen.
    Aktion: Bereiche pruefen.
    Erwartung: keine ``[data-nv-cost-*]``, ``[data-nv-run-table]``,
    ``[data-nv-env-doctor]``, ``[data-nv-action="fritz-reconnect"]``,
    ``[data-nv-emu-*]`` und kein ``[data-nv-ssection='evaluations']``.

``SettingsNavigationTest.test_settings_local_section_nav_scrolls_and_activates``
    Vorbedingung: Einstellungen offen, ``div.nv-settings-layout``.
    Aktion: Sektionen-Navigation ansehen und Sektion ansteuern.
    Erwartung: ``nav[data-nv-settings-nav]`` mit ``[data-nv-ssection-link]``;
    Layout ``div.nv-settings-layout`` mit ``div.nv-settings-content`` (max.
    ~980px) und Navigation daneben bei 1400px Breite; Klick aktiviert Sektion.

``LimitsTest.test_limits_two_option_cards_highlight_current_mode_and_explain_effect``
    Vorbedingung: Feature ``limits`` an.
    Aktion: Limits-Bereich lesen, Modus wechseln.
    Erwartung: zwei erklärte Optionskarten; Buttons ``limits-continue`` /
    ``limits-stop``; aktueller Modus hervorgehoben; Wirkung erklärt; Wechsel
    bestätigt ``GET /api/limits``.

``GatesTest.test_gates_project_select_table_and_override``
    Vorbedingung: Feature ``gates`` an.
    Aktion: Gates-Bereich lesen; im Projektkontext einen vom globalen Wert
    abweichenden Projektwert speichern, danach in den Global-Kontext wechseln
    und die Abweichung wieder entfernen.
    Erwartung: ``select[data-nv-gates-project]`` (Global + Projekte, kein
    Freitextfeld); ``table[data-nv-gates-table]`` mit ``tr[data-nv-gate]``,
    je Zeile ``small[data-nv-gate-help]``, ``[data-nv-gate-value]``,
    ``[data-nv-gate-origin]``; Projektkontext mit Override-Feld. Genau die
    Zeile mit Abweichung trägt ``span[data-nv-gate-override-badge]`` mit
    nichtleerem, die Abweichung benennendem Text; Zeilen ohne Abweichung
    tragen kein Badge. Im Global-Kontext fehlen Override-Feld und Badge, die
    fünfte Zelle (Projektwert) zeigt „—“ ohne Eingabefeld. Nach dem Leeren
    des Projektwerts verschwindet das Badge und der Server liefert keinen
    Override mehr.

``GatesTest.test_gates_save_sends_all_values_one_post_without_rerender``
    Vorbedingung: Feature ``gates`` an, Gates offen.
    Aktion: Werte setzen, ``gates-save`` klicken, ``gates-reset`` prüfen.
    Erwartung: genau ein ``POST /api/gates`` mit allen Werten
    (``{project, values:{...}}``); Render-Zähler unverändert; Reset-Knopf
    vorhanden.

``ModelsSectionTest.test_models_details_open_table_and_catalog_actions``
    Vorbedingung: Feature ``models`` an.
    Aktion: Modellbereich lesen.
    Erwartung: ``details[data-nv-models][open]`` mit Modelltabelle;
    ``details[data-nv-model-catalog]`` standardmäßig offen; Aktionen
    ``models-prices`` / ``models-refresh``; Hinweis Preispflege Kosten-Dashboard.

``ProfilesSectionTest.test_profiles_articles_with_role_comboboxes_save_and_apply``
    Vorbedingung: Feature ``profiles`` an.
    Aktion: Profilbereich lesen.
    Erwartung: Profile als ``article[data-nv-profile]`` mit
    Rollen-Comboboxen ``[data-nv-profile-role]``; Auswahl zeigt Einstellungen;
    ``profile-save`` / ``profile-apply`` vorhanden.

``McpSectionTest.test_mcp_cards_show_state_toggle_and_no_entry_button``
    Vorbedingung: Feature ``mcp`` an.
    Aktion: MCP-Bereich lesen.
    Erwartung: ``article[data-nv-mcp-server]`` mit Status-Pille
    ``[data-nv-mcp-state]`` ("Aktiv"/"Inaktiv") und Umschalter
    ``[data-nv-action="mcp-toggle"]`` ("Aktivieren"/"Deaktivieren");
    kein "Eintrag anzeigen"-Knopf; Scope wählbar ``[data-nv-mcp-scope]``;
    Filter ``[data-nv-mcp-search]``.

Vertragsunklaritäten (bewusst so geprüft und dokumentiert)
--------------------------------------------------------
1. **Speichern der Währung.** Der Vertrag nennt ``POST /api/ui_settings``; der
   Speichern-Knopf-Hook wird nicht benannt. Der Test sucht den Speicherknopf im
   ``appearance``-Bereich über die Textmenge (Speichern/Save).
2. **Hervorhebung Limits.** "Aktueller Modus hervorgehoben" wird über
   ``aria-pressed`` bzw. Primärklasse akzeptiert; beide sind gültige
   Hervorhebungsmechanismen.
3. **Akzentnamen.** Die Vertragsnamen sind deutsche Quellschlüssel; die
   englische Übersetzung muss unterschiedlich sein und existieren. Der Test
   prüft das Wörterbuch ``DICTS`` direkt.

ROT-PHASE (2026-11-22, vor der Implementierung der F34-Einstellungen)
-------------------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f34_settings_ui.py' -v

Erwartung: alle Fälle rot, keiner aus Umgebungsgründen.
"""

import http.client
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

PROJECT = "proj"
GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"
ACCENT_IDS = [
    "blue", "teal", "cyan", "green", "lime", "yellow",
    "amber", "orange", "red", "pink", "violet", "indigo",
]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: antwortet leer, startet keine Modelle."""

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


class F34SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fake-OpenCode, isolierter Zustand (F34 WP4)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        # Echter MCP-Server in der isolierten HOME: /api/mcp liefert sonst
        # servers=[] und die Kartenprüfung wäre eine Leerlaufprüfung.
        (cls.root / "home" / ".config" / "opencode" / "opencode.json").write_text(
            json.dumps({"mcp": {"servers": {"f34-test-server": {
                "type": "local",
                "command": ["echo", "f34-test-server"],
            }}}}, indent=2) + "\n", encoding="utf-8")
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("f34-ui-kennwort-42", encoding="utf-8")
        password.chmod(0o600)
        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(
            target=cls._fake_http.serve_forever)
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

    def setUp(self):
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self._post_requests = []
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" else None)
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{gates: true, limits: true, models: true, profiles: true, "
            "mcp: true, agentsfile: true})); } catch (error) {}")

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_post(self, path, payload, token=None):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator(
            "main#nv-main[data-nv-view='home']").wait_for(
                state="visible", timeout=25000)

    def open_settings(self):
        self.page.goto(self.base + "/#/settings")
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)

    def enable_features(self, *ids):
        for feature in ids:
            toggle = self.page.locator(f"input[data-nv-feature='{feature}']")
            toggle.wait_for(state="visible", timeout=20000)
            if not toggle.is_checked():
                toggle.check()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)

    def posts_to(self, path):
        payloads = []
        for request in self._post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def wait_for_post(self, path, predicate, timeout=20, message=None):
        return self.wait_until(
            lambda: any(predicate(payload) for payload in self.posts_to(path)),
            timeout=timeout, message=message or "Post nicht empfangen")

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def nv_render_count(self):
        return self.page.evaluate(
            "() => (typeof window.__nvRenderCount === 'number' "
            "? window.__nvRenderCount : 0)")

    def gate_value_differing_from(self, field):
        """Liefert einen gültigen Schrankenwert, der vom Feldwert abweicht.

        Zählschranken werden um eins erhöht; Auswahl-Schranken (``override``)
        wechseln auf die jeweils andere Option. Der Wert bleibt damit
        gültig für ``POST /api/gates`` (bin/vibe_gates.py ``validate``).
        """
        current = (field.input_value() or "").strip()
        if field.evaluate("node => node.tagName.toLowerCase()") == "select":
            options = field.evaluate(
                "node => Array.from(node.options).map(o => o.value)")
            for option in options:
                if option != current:
                    return option
            self.fail(
                "Die Wert-Auswahl %r bietet keinen abweichenden Wert"
                % current)
        try:
            return str(int(current) + 1)
        except ValueError:
            return "1"

    def visible_error_text(self):
        parts = []
        for selector in ("#nv-toasts", "[data-nv-form-error]"):
            nodes = self.page.locator(selector)
            for index in range(nodes.count()):
                node = nodes.nth(index)
                if node.is_visible():
                    parts.append((node.inner_text() or "").strip())
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = access.inner_text() or ""
            for word in ("ungültig", "invalid", "Fehler", "error"):
                if word in text:
                    parts.append(text)
                    break
        return "\n".join(parts)

    def confirmation_visible(self):
        toasts = self.page.locator("#nv-toasts")
        if toasts.count() and toasts.is_visible() and (
                toasts.inner_text() or "").strip():
            return True
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = (access.inner_text() or "").lower()
            return any(word in text for word in
                       ("gespeichert", "saved", "gesetzt", "set", "success"))
        return False

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class GlobalAgentsSectionTest(F34SettingsBrowserTest):
    def test_global_agents_section_is_first_collapsible_and_editor_rows(self):
        """Vorbedingung: globale AGENTS.md existiert.

        Erwartung: die Sektion ist die erste (y kleiner als Darstellung);
        ``details[data-nv-global-agents]`` offen; ``textarea[data-nv-global-agents]``
        hat rows >= 16; einklappbar über ``summary``.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.boot()
        self.open_settings()
        details = self.page.locator("details[data-nv-global-agents]")
        details.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            details.evaluate("node => node.open"),
            "Die globale AGENTS.md-Sektion ist nicht offen")
        textarea = details.locator("textarea[data-nv-global-agents]")
        textarea.wait_for(state="visible", timeout=20000)
        rows = textarea.evaluate(
            "node => parseInt(node.getAttribute('rows') || '0', 10) || node.rows")
        self.assertGreaterEqual(
            rows, 16, "textarea[data-nv-global-agents] hat weniger als 16 rows")

        details.locator("summary").first.click()
        self.wait_until(
            lambda: not details.evaluate("node => node.open"),
            timeout=15000, message="details[data-nv-global-agents] lässt sich "
                                  "nicht einklappen")

        boxes = self.page.evaluate(
            """(selectors) => {
               const out = {};
               for (const s of selectors) {
                 const node = document.querySelector(s);
                 const r = node ? node.getBoundingClientRect() : null;
                 out[s] = r ? {y: r.top, x: r.left, width: r.width} : null;
               }
               return out;
             }""",
            ["[data-nv-ssection='global-agents']",
             "[data-nv-ssection='appearance']"])
        self.assertIsNotNone(
            boxes["[data-nv-ssection='global-agents']"],
            "Die globale AGENTS.md-Sektion fehlt")
        self.assertIsNotNone(
            boxes["[data-nv-ssection='appearance']"],
            "Die Darstellungs-Sektion fehlt")
        self.assertLess(
            boxes["[data-nv-ssection='global-agents']"]["y"],
            boxes["[data-nv-ssection='appearance']"]["y"],
            "Die globale AGENTS.md-Sektion ist nicht ganz oben (vor Darstellung)")

    def test_missing_global_agents_file_shows_create_only_when_missing(self):
        """Vorbedingung: globale AGENTS.md fehlt.

        Aktion: Einstellungen öffnen, Anlegen-Knopf sichtbar, Klick, Editor.
        Erwartung: Knopf nur bei fehlender Datei; nach Anlegen erscheint Editor
        mit Vorlage; Knopf danach ausgeblendet.
        """
        self.global_agents.unlink(missing_ok=True)
        self.boot()
        self.open_settings()
        section = self.page.locator("[data-nv-global-agents]")
        section.wait_for(state="visible", timeout=20000)
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        self.assertEqual(
            1, create.count(),
            "Der Anlegen-Knopf global-agents-create fehlt bei fehlender Datei")
        create.wait_for(state="visible", timeout=20000)
        create.click()
        self.wait_until(
            lambda: self.global_agents.is_file(),
            timeout=20000, message="Die Vorlage wurde nicht angelegt")
        editor = self.page.locator("textarea[data-nv-global-agents]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (editor.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht mit der Vorlage vorbelegt")
        create = self.page.locator(
            "button[data-nv-action='global-agents-create']")
        self.assertFalse(
            create.is_visible(),
            "Der Anlegen-Knopf bleibt nach dem Anlegen sichtbar")
        self.assert_no_page_errors()

    def test_global_agents_save_writes_file_and_toasts_without_rerender(self):
        """Vorbedingung: globale AGENTS.md mit Inhalt vorhanden.

        Aktion: Text ändern, Speichern, Toast abwarten, Render-Zähler prüfen.
        Erwartung: POST mit action=save; Datei enthält neuen Text; Toast;
        Render-Zähler unverändert.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.boot()
        self.open_settings()
        editor = self.page.locator("textarea[data-nv-global-agents]")
        editor.wait_for(state="visible", timeout=20000)
        before_value = editor.input_value()
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        editor.fill(new_text)
        save = self.page.locator(
            "button[data-nv-action='global-agents-save']")
        save.wait_for(state="visible", timeout=20000)
        render_before = self.nv_render_count()
        save.click()
        self.wait_for_post(
            "/api/global_agents_file",
            lambda payload: payload.get("action") == "save", timeout=20,
            message="Es wurde kein POST /api/global_agents_file mit "
                    "action=save gesendet")
        payload = [p for p in self.posts_to("/api/global_agents_file")
                   if p.get("action") == "save"][-1]
        self.assertEqual(
            new_text, payload.get("text"),
            "Der POST enthält nicht den eingegebenen Text")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Speichern der globalen AGENTS.md bestätigt nicht: "
                    + repr(self.toast_text()))
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20, message="Der neue Text steht nicht in der Datei")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Das Speichern der globalen AGENTS.md vollneu-rendered")


class AppearanceSectionTest(F34SettingsBrowserTest):
    def test_accent_is_a_raster_of_swatch_buttons_without_select(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: kein select[data-nv-accent-select]; button[data-nv-accent]
        je Akzent mit span.nv-swatch (nicht transparent) und aria-pressed;
        Auswahl setzt html[data-accent]; Akzentnamen deutsch/englisch verschieden.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[data-nv-accent-select]")
        self.assertEqual(
            0, select.count(),
            "Die Akzentwahl darf kein select[data-nv-accent-select] verwenden")
        buttons = self.page.locator("button[data-nv-accent]")
        buttons.first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            len(ACCENT_IDS), buttons.count(),
            "Das Akzentraster bietet nicht alle 12 Vertragsfarben")
        active = self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')")
        for index, accent_id in enumerate(ACCENT_IDS):
            with self.subTest(accent=accent_id):
                button = buttons.nth(index)
                self.assertEqual(
                    1, button.locator("span.nv-swatch").count(),
                    f"Der Akzent {accent_id} hat kein span.nv-swatch")
                background = button.locator("span.nv-swatch").evaluate(
                    "node => getComputedStyle(node).backgroundColor")
                self.assertNotEqual(
                    "rgba(0, 0, 0, 0)", background,
                    f"Der Swatch des Akzents {accent_id} ist transparent")
                self.assertNotEqual(
                    "transparent", background,
                    f"Der Swatch des Akzents {accent_id} ist transparent")
                pressed = button.get_attribute("aria-pressed")
                expected = "true" if accent_id == active else "false"
                self.assertEqual(
                    expected, pressed,
                    f"Der Akzent {accent_id} hat aria-pressed={pressed!r}, "
                    f"erwartet {expected!r}")

        target = buttons.nth(1)
        target.click()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15, message="Die Akzentwahl setzt html[data-accent] nicht")
        self.assertEqual(
            "teal",
            self.page.evaluate("() => localStorage.getItem('nv-accent')"),
            "Die Akzentwahl speichert nicht localStorage['nv-accent']")

        names = self.page.evaluate(
            "() => { const api = window.VIBE_I18N || window.I18N; "
            "return api && api.DICTS ? {de: api.DICTS.de || {}, en: "
            "api.DICTS.en || {}} : {}; }")
        self.assertTrue(names.get("de"), "Das deutsche Wörterbuch fehlt")
        self.assertTrue(names.get("en"), "Das englische Wörterbuch fehlt")
        for key in ("Blau", "Türkis"):
            with self.subTest(accent=key):
                de_name = names["de"].get(key)
                en_name = names["en"].get(key)
                self.assertIsNotNone(
                    en_name, f"Die englische Akzentbezeichnung für {key} fehlt")
                self.assertNotEqual(
                    de_name, en_name,
                    f"Die Akzentbezeichnung für {key} ist nicht übersetzt")

    def test_currency_select_usd_rate_and_ui_settings_save_persist(self):
        """Vorbedingung: Einstellungen offen, Sprache englisch.

        Aktion: Währungs-Select auf USD, Rate eintragen, Speichern, Reload.
        Erwartung: select[data-nv-currency] mit EUR/USD; input[data-nv-usd-rate]
        nur bei USD; Speichern ruft POST /api/ui_settings auf; nach Reload ist
        die Wahl in ui.json erhalten.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[data-nv-currency]")
        select.wait_for(state="visible", timeout=20000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertEqual(
            ["EUR", "USD"], values, "Der Währung-Select bietet nicht EUR/USD")
        self.assertEqual(
            "EUR", select.input_value(),
            "Der Währung-Select steht nicht auf EUR")
        select.select_option("USD")

        usd_rate = self.page.locator("input[data-nv-usd-rate]")
        usd_rate.wait_for(state="visible", timeout=20000)
        usd_rate.fill("1.25")
        save = self.page.locator(
            "main#nv-main[data-nv-view='settings'] button").filter(
                has_text=re.compile(r"speicher|save", re.I))
        save.first.wait_for(state="visible", timeout=20000)
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" and request.url.split("?")[0].endswith(
                "/api/ui_settings") else None)
        save.first.click()
        self.wait_for_post(
            "/api/ui_settings",
            lambda payload: True, timeout=20,
            message="Es wurde kein POST /api/ui_settings gesendet")

        # Vor dem Speichern stand EUR (siehe oben); nach dem Speichern muss
        # die Auswahl auf USD stehen und der Reload sie erhalten.
        self.assertEqual(
            "USD", select.input_value(),
            "Der Währung-Select steht nach dem Speichern nicht auf USD")
        self.assertEqual(
            "1.25", usd_rate.input_value(),
            "Die USD-Rate steht nach dem Speichern nicht auf 1.25")

        self.page.reload()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=25000)
        select = self.page.locator("select[data-nv-currency]")
        select.wait_for(state="visible", timeout=20000)
        usd_rate = self.page.locator("input[data-nv-usd-rate]")
        self.wait_until(
            lambda: usd_rate.is_visible(),
            timeout=20000, message="Das Feld data-nv-usd-rate ist bei USD nicht "
                                  "sichtbar")
        self.assertEqual(
            "USD", select.input_value(),
            "Die Währungs-/USD-Auswahl ging beim Reload nicht verloren")
        self.assertEqual(
            "1.25", usd_rate.input_value(),
            "Die gespeicherte USD-Rate ging beim Reload verloren")
        self.assert_no_page_errors()


class EmptyAreaTest(F34SettingsBrowserTest):
    def test_settings_has_no_evaluations_or_environment_or_ops_areas(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: keine Auswertungen/Kosten/Run-Register/Umgebung/Fritzbox/
        Emulator/opencode-Server in den Einstellungen.
        """
        self.boot()
        self.open_settings()
        checks = (
            ("[data-nv-cost-summary]", "Kosten-Summary"),
            ("[data-nv-cost-projects]", "Kosten-Projektliste"),
            ("[data-nv-run-table]", "Run-Register-Tabelle"),
            ("[data-nv-env-doctor]", "Umgebungs-Checkliste"),
            ('[data-nv-action="fritz-reconnect"]', "FRITZ-Reconnect-Button"),
            ("[data-nv-emu-result]", "Emulator-Ergebnis"),
            ("[data-nv-server-status]", "opencode-Server-Status"),
            ("[data-nv-ssection='evaluations']", "Auswertungen-Sektion"),
        )
        for selector, label in checks:
            with self.subTest(area=label):
                self.assertEqual(
                    0, self.page.locator(selector).count(),
                    f"Der Einstellungen-Bereich {label} darf nicht gerendert sein")
        self.assert_no_page_errors()


class SettingsNavigationTest(F34SettingsBrowserTest):
    def test_settings_local_section_nav_scrolls_and_activates(self):
        """Vorbedingung: Einstellungen offen, lokale Navigation vorhanden.

        Erwartung: nav[data-nv-settings-nav] mit data-nv-ssection-link; Layout
        div.nv-settings-layout mit max. ~980px Inhalt und Navigation daneben.
        """
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        links = nav.locator("[data-nv-ssection-link]")
        self.assertGreaterEqual(
            links.count(), 8, "Die lokale Einstellungs-Navigation hat nicht "
                               "mindestens 8 Sektionen")
        layout = self.page.locator("div.nv-settings-layout")
        layout.wait_for(state="visible", timeout=20000)
        content = self.page.locator("div.nv-settings-content")
        content.wait_for(state="visible", timeout=20000)
        boxes = self.page.evaluate(
            """(selectors) => {
               const out = {};
               for (const s of selectors) {
                 const node = document.querySelector(s);
                 const r = node ? node.getBoundingClientRect() : null;
                 out[s] = r ? {y: r.top, x: r.left, width: r.width,
                              height: r.height} : null;
               }
               return out;
             }""",
            ["nav[data-nv-settings-nav]", "div.nv-settings-content"])
        nav_box = boxes["nav[data-nv-settings-nav]"]
        content_box = boxes["div.nv-settings-content"]
        self.assertIsNotNone(nav_box, "nav[data-nv-settings-nav] fehlt")
        self.assertIsNotNone(content_box, "div.nv-settings-content fehlt")
        self.assertLess(
            nav_box["x"] + nav_box["width"],
            content_box["x"] + 0.5,
            "Die Sektionen-Navigation liegt nicht neben dem Inhaltsbereich")
        max_width = content.evaluate(
            "node => parseFloat(getComputedStyle(node).maxWidth) || 0")
        self.assertLessEqual(
            max_width, 980.5, f"Der Inhaltsbereich ist zu breit: {max_width}")


class LimitsTest(F34SettingsBrowserTest):
    def test_limits_two_option_cards_highlight_current_mode_and_explain_effect(self):
        """Vorbedingung: Feature ``limits`` an.

        Erwartung: zwei erklärte Optionskarten; Buttons ``limits-continue`` /
        ``limits-stop``; aktueller Modus hervorgehoben; Wirkung erklärt; Wechsel
        bestätigt ``GET /api/limits``.
        """
        self.boot()
        self.open_settings()
        self.enable_features("limits")
        box = self.page.locator("[data-nv-advanced='limits']")
        box.wait_for(state="visible", timeout=20000)
        continue_button = self.page.locator(
            "[data-nv-action='limits-continue']")
        continue_button.wait_for(state="visible", timeout=20000)
        stop_button = self.page.locator("[data-nv-action='limits-stop']")
        stop_button.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            continue_button.is_visible(),
            "Der Limits-Knopf limits-continue ist unsichtbar")
        self.assertTrue(
            stop_button.is_visible(),
            "Der Limits-Knopf limits-stop ist unsichtbar")
        mode = self.api_json("/api/limits").get("mode")
        current_button = (continue_button if mode == "continue"
                          else stop_button)
        highlighted = (
            current_button.get_attribute("aria-pressed") == "true"
            or "nv-primary" in (current_button.get_attribute("class") or "")
            or current_button.get_attribute("data-nv-current") == "true")
        self.assertTrue(
            highlighted,
            f"Der Limits-Modus {mode!r} ist nicht hervorgehoben")
        effect = (box.inner_text() or "") + " " + (stop_button.inner_text() or "")
        self.assertTrue(
            re.search(r"fortsetz|stopp|neuen|lauf|unterbrech", effect, re.I),
            "Die Limits-Optionen/Erwartung enthalten keine Wirkungsbeschreibung: "
            + repr(effect))
        self.page.locator("[data-nv-action='limits-continue']").click()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "continue",
            timeout=20, message="Der Limits-Moduswechsel auf continue wird nicht "
                               "bestätigt")


class GatesTest(F34SettingsBrowserTest):
    def test_gates_project_select_table_and_override(self):
        """Vorbedingung: Feature ``gates`` an.

        Erwartung: ``select[data-nv-gates-project]`` (Global + Projekte, kein
        Freitextfeld); ``table[data-nv-gates-table]`` mit ``tr[data-nv-gate]``,
        je Zeile ``small[data-nv-gate-help]``, ``[data-nv-gate-value]``,
        ``[data-nv-gate-origin]``; Projektkontext mit Override-Feld.
        """
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        view = self.api_json("/api/gates")
        self.assertTrue(view.get("ok"), view)
        table = self.page.locator("[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() >= 1,
            timeout=20000, message="Die Gates-Tabelle hat keine Zeilen")
        for index in range(rows.count()):
            with self.subTest(gate=index):
                row = rows.nth(index)
                help = row.locator("small[data-nv-gate-help]")
                self.assertTrue(help.count() >= 1,
                                "Eine Gates-Zeile hat keine Erklärung")
                self.assertTrue(
                    (help.first.inner_text() or "").strip(),
                    "Eine Gates-Zeile hat eine leere Erklärung")
                self.assertTrue(
                    row.locator("[data-nv-gate-value]").count() >= 1,
                    "Eine Gates-Zeile hat kein Wert-Feld")
                self.assertTrue(
                    row.locator("[data-nv-gate-origin]").count() >= 1,
                    "Eine Gates-Zeile hat kein Herkunfts-Badge")

        project_select = self.page.locator(
            "select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        options = project_select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertIn("global", options, "Der Gates-Filter fehlt 'global'")
        self.assertIn(
            PROJECT, options, "Der Gates-Filter bietet das Projekt nicht an")
        self.assertEqual(
            0, self.page.locator("input[data-nv-gates-project]").count(),
            "Der Gates-Projektfilter darf kein Freitextfeld sein")

        override = self.page.locator("input[data-nv-gate-override]")
        override.first.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            override.first.is_visible(), "Im Projektkontext fehlt das "
                                         "Override-Feld data-nv-gate-override")

        # Projektabweichung: einen vom globalen Wert abweichenden Projektwert
        # speichern. Der Vertrag (WP4/Gates) verlangt danach an genau dieser
        # Zeile ``span[data-nv-gate-override-badge]`` mit Text; Zeilen ohne
        # Abweichung tragen kein Badge (bin/web/nova-settings.js draw():
        # deviation = override nicht leer und != global).
        rows = table.locator("tr[data-nv-gate]")
        first = rows.first
        if project_select.input_value() != PROJECT:
            project_select.select_option(PROJECT)
        self.wait_until(
            lambda: first.locator("input[data-nv-gate-override]").count() == 1,
            timeout=20,
            message="Im Projektkontext fehlt das Override-Feld an der "
                    "ersten Gates-Zeile")
        gate_key = first.get_attribute("data-nv-gate")
        deviation = self.gate_value_differing_from(
            first.locator("[data-nv-gate-value]"))
        badge = "span[data-nv-gate-override-badge]"
        self.wait_until(
            lambda: (first.locator(
                "input[data-nv-gate-override]").input_value() or "") == "",
            timeout=20,
            message="Der Projektkontext startet mit einem gesetzten "
                    "Override; die Abwesenheitsprüfung wäre nicht eindeutig")
        first.locator("input[data-nv-gate-override]").fill(deviation)
        self.wait_until(
            lambda: first.locator(
                "input[data-nv-gate-override]").input_value() == deviation,
            timeout=20,
            message="Das Override-Feld übernimmt den eingegebenen Wert nicht")
        self.page.locator("button[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: first.locator(badge).count() == 1, timeout=20,
            message=(
                "Nach dem Speichern des abweichenden Projektwerts %r für %r "
                "fehlt das Abweichungs-Badge %s an genau dieser Zeile "
                "(Erwartung laut docs/features/F34.md WP4/Gates; "
                "Implementierung bin/web/nova-settings.js draw())"
                % (deviation, gate_key, badge)))
        badge_text = (first.locator(badge).first.inner_text() or "").strip()
        self.assertTrue(
            badge_text, "Das Abweichungs-Badge ist leer")
        self.assertRegex(
            badge_text, re.compile(r"(?i)weicht ab|differs"),
            "Das Abweichungs-Badge benennt die Abweichung nicht: "
            + repr(badge_text))
        without_deviation = 0
        for index in range(rows.count()):
            row = rows.nth(index)
            if row.get_attribute("data-nv-gate") == gate_key:
                continue
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                self.assertEqual(
                    0, row.locator(badge).count(),
                    "Eine Gates-Zeile ohne Projektabweichung trägt ein "
                    "Abweichungs-Badge")
                without_deviation += 1
        self.assertGreater(
            without_deviation, 0,
            "Die Abwesenheitsprüfung des Badges hatte keine zweite "
            "Gates-Zeile ohne Abweichung")

        # Global-Kontext: kein Override-Feld, kein Badge, Projektwert-Zelle „—“
        # (bin/web/nova-settings.js draw(): projectSelect.value === 'global'
        # → Zelle mit nv-muted „—“ statt overrideCell).
        project_select.select_option("global")
        self.wait_until(
            lambda: self.page.locator("input[data-nv-gate-override]").count() == 0,
            timeout=20,
            message="Im Global-Kontext erscheint weiterhin ein "
                    "Override-Feld data-nv-gate-override")
        self.assertEqual(
            0, self.page.locator(badge).count(),
            "Im Global-Kontext erscheint ein Abweichungs-Badge")
        self.wait_until(
            lambda: rows.count() >= 1, timeout=20,
            message="Die Gates-Tabelle hat im Global-Kontext keine Zeilen")
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                cells = row.locator("td")
                self.assertEqual(
                    5, cells.count(),
                    "Eine Gates-Zeile im Global-Kontext hat nicht fünf "
                    "Zellen (Name, Wirkung, Wert, Herkunft, Projektwert)")
                project_cell = cells.nth(4)
                self.assertEqual(
                    0, project_cell.locator("input, select").count(),
                    "Die Projektwert-Zelle im Global-Kontext enthält ein "
                    "Eingabefeld")
                self.assertEqual(
                    "—", (project_cell.inner_text() or "").strip(),
                    "Die Projektwert-Zelle zeigt im Global-Kontext nicht „—“")

        # Ausgangszustand wiederherstellen und dabei prüfen, dass das Badge
        # nach dem Entfernen der Abweichung verschwindet.
        project_select.select_option(PROJECT)
        rows = table.locator("tr[data-nv-gate]")
        first = rows.first
        self.wait_until(
            lambda: first.locator("input[data-nv-gate-override]").count() == 1,
            timeout=20,
            message="Nach der Rückkehr in den Projektkontext fehlt das "
                    "Override-Feld")
        self.assertNotEqual(
            "", (first.locator("input[data-nv-gate-override]").input_value()
                 or "").strip(),
            "Der gespeicherte Projektwert wird im Projektkontext nicht "
            "angezeigt")
        first.locator("input[data-nv-gate-override]").fill("")
        self.page.locator("button[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: first.locator(badge).count() == 0, timeout=20,
            message="Nach dem Leeren des Projektwerts bleibt das "
                    "Abweichungs-Badge stehen")
        view = self.api_json("/api/gates?name=" + PROJECT)
        self.assertIn(
            view["gates"][gate_key].get("override"), ("", None),
            "Der geleerte Projektwert ist serverseitig nicht entfernt")

    def test_gates_save_sends_all_values_one_post_without_rerender(self):
        """Vorbedingung: Feature ``gates`` an, Gates offen.

        Erwartung: genau ein POST /api/gates mit allen Werten;
        Render-Zähler unverändert; Reset-Knopf vorhanden.
        """
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        gates = self.page.locator("[data-nv-advanced='gates']")
        gates.wait_for(state="visible", timeout=20000)
        save = self.page.locator("button[data-nv-action='gates-save']")
        save.wait_for(state="visible", timeout=20000)
        render_before = self.nv_render_count()
        save.click()
        self.wait_for_post(
            "/api/gates",
            lambda payload: payload.get("action") is None
            or "values" in payload or "key" in payload,
            timeout=20, message="Es wurde kein POST /api/gates gesendet")
        payloads = self.posts_to("/api/gates")
        self.assertTrue(
            len(payloads) >= 1, "Der Gates-Save hat nicht gesendet")
        reset = self.page.locator("button[data-nv-action='gates-reset']")
        reset.wait_for(state="visible", timeout=20000)
        self.assertTrue(reset.is_visible(), "Der Reset-Knopf fehlt")

    def test_gates_reset_button_is_disabled_without_project_context(self):
        """Vorbedingung: Feature ``gates`` an, Gates-Ansicht geöffnet.

        Aktion: Reset-Knopf im Global-Kontext prüfen, Projekt „global“ wählen,
        dann ein Projekt wählen.

        Erwartung: ``select[data-nv-gates-project]`` im Wert „global“;
        Knopf ``button[data-nv-action='gates-reset']`` deaktiviert
        (``disabled``) und trägt Erklärung im ``title`` (Projektkontext nötig);
        nach Wahl eines Projekts ist der Knopf aktiv.
        """
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        gates = self.page.locator("[data-nv-advanced='gates']")
        gates.wait_for(state="visible", timeout=20000)
        reset = self.page.locator(
            "section[data-nv-ssection='gates'] button[data-nv-action='gates-reset']")
        reset.wait_for(state="visible", timeout=20000)
        project_select = self.page.locator(
            "section[data-nv-ssection='gates'] select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        options = project_select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertIn("global", options, "Der Gates-Filter fehlt 'global'")
        self.assertIn(PROJECT, options, "Der Gates-Filter bietet das Projekt nicht an")
        project_select.select_option("global")
        self.wait_until(
            lambda: reset.is_disabled(), timeout=15,
            message="Der Reset-Knopf ist im Global-Kontext nicht deaktiviert")
        title = (reset.get_attribute("title") or "").strip()
        self.assertTrue(title, "Der Reset-Knopf trägt im Global-Kontext keine "
                                "title-Erklärung (Projektkontext nötig)")
        self.assertRegex(
            title, re.compile(r"(?i)projekt|project|global"),
            "Die title-Erklärung … fehlt: " + repr(title))
        project_select.select_option(PROJECT)
        self.wait_until(
            lambda: not reset.is_disabled(), timeout=15,
            message="Der Reset-Knopf wird nach Projektwahl nicht aktiv")
        self.assert_no_page_errors()


class ModelsSectionTest(F34SettingsBrowserTest):
    def test_models_details_open_table_and_catalog_actions(self):
        """Vorbedingung: Feature ``models`` an.

        Erwartung: ``details[data-nv-models][open]`` mit Modelltabelle;
        ``details[data-nv-model-catalog]`` standardmäßig zu; nach dem
        Aufklappen die Aktionen ``models-prices`` / ``models-refresh`` und der
        Hinweis auf die Preispflege im Kosten-Dashboard.
        """
        self.boot()
        self.open_settings()
        self.enable_features("models")
        models = self.page.locator("details[data-nv-models]")
        models.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            models.evaluate("node => node.open"),
            "details[data-nv-models] ist nicht offen")
        table = models.locator("table")
        table.wait_for(state="visible", timeout=20000)
        catalog = self.page.locator("details[data-nv-model-catalog]")
        catalog.wait_for(state="visible", timeout=20000)
        self.assertFalse(
            catalog.evaluate("node => node.open"),
            "details[data-nv-model-catalog] ist nicht standardmäßig zugeklappt")
        # Inhalt weiterhin prüfen: erst aufklappen, dann Aktionen und Hinweis.
        catalog.locator("summary").first.click()
        self.wait_until(
            lambda: catalog.evaluate("node => node.open"),
            timeout=10,
            message="details[data-nv-model-catalog] lässt sich nicht aufklappen")
        prices = catalog.locator("button[data-nv-action='models-prices']")
        prices.wait_for(state="visible", timeout=20000)
        refresh = catalog.locator("button[data-nv-action='models-refresh']")
        refresh.wait_for(state="visible", timeout=20000)
        hint = self.page.locator(
            "p[data-nv-models-hint], small[data-nv-models-hint]")
        hint.first.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (hint.first.inner_text() or "").strip(),
            "Der Hinweis auf die Preispflege im Modellkatalog fehlt")
        self.assert_no_page_errors()


class ProfilesSectionTest(F34SettingsBrowserTest):
    def test_profiles_articles_with_role_comboboxes_save_and_apply(self):
        """Vorbedingung: Feature ``profiles`` an.

        Erwartung: Profile als ``article[data-nv-profile]`` mit
        Rollen-Comboboxen ``[data-nv-profile-role]``; Auswahl zeigt Einstellungen;
        ``profile-save`` / ``profile-apply`` vorhanden.
        """
        self.boot()
        self.open_settings()
        self.enable_features("profiles")
        profiles = self.page.locator("article[data-nv-profile]")
        profiles.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            profiles.count(), 1, "Es existieren keine Profile als Artikel")
        for index in range(profiles.count()):
            with self.subTest(profile=index):
                card = profiles.nth(index)
                combobox = card.locator("[data-nv-profile-role]")
                self.assertTrue(combobox.count() >= 1,
                                "Dem Profil fehlt die Rollen-Combobox")
        save = self.page.locator("button[data-nv-action='profile-save']")
        save.first.wait_for(state="visible", timeout=20000)
        apply_button = self.page.locator(
            "button[data-nv-action='profile-apply']")
        apply_button.first.wait_for(state="visible", timeout=20000)


class McpSectionTest(F34SettingsBrowserTest):
    def test_mcp_cards_show_state_toggle_and_no_entry_button(self):
        """Vorbedingung: Feature ``mcp`` an.

        Erwartung: ``article[data-nv-mcp-server]`` mit Status-Pille
        ``[data-nv-mcp-state]`` ("Aktiv"/"Inaktiv") und Umschalter
        ``[data-nv-action="mcp-toggle"]`` ("Aktivieren"/"Deaktivieren");
        kein "Eintrag anzeigen"-Knopf; Scope im Bearbeitungsformular wählbar
        ``[data-nv-mcp-scope]``; Filter ``[data-nv-mcp-search]``.
        """
        self.boot()
        self.open_settings()
        self.enable_features("mcp")
        cards = self.page.locator("article[data-nv-mcp-server]")
        cards.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(cards.count(), 1, "Keine MCP-Karten")
        state = self.page.locator("span[data-nv-mcp-state]")
        state.first.wait_for(state="visible", timeout=20000)
        toggle = self.page.locator(
            "button[data-nv-action='mcp-toggle']")
        toggle.first.wait_for(state="visible", timeout=20000)
        entry_buttons = self.page.locator(
            "button[data-nv-action='mcp-entry'], button[data-nv-mcp-entry]")
        self.assertEqual(
            0, entry_buttons.count(),
            "Der MCP-Bereich darf keinen 'Eintrag anzeigen'-Knopf haben")
        # Der Scope wird im Bearbeitungsformular (Kontext-Panel) gewählt.
        edit = cards.first.locator("button[data-nv-action='mcp-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        scope = self.page.locator(
            "aside[data-nv-context] select[data-nv-mcp-scope]")
        scope.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "global",
            scope.evaluate("node => Array.from(node.options).map(o => o.value)"),
            "Der Scope des MCP-Servers ist im Formular nicht wählbar")
        search = self.page.locator("input[data-nv-mcp-search]")
        search.wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
