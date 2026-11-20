"""Browserabnahme AP22, Meilenstein B: Projektansicht und Projekteinstellungen.

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Projektansicht“,
„Frontend-Vertrag“) ab. Das echte Dashboard läuft als eigener Prozess auf
freiem Port mit isoliertem VIBE-Root; die opencode-Gegenstelle ist eine
lokale HTTP-Attrappe, und ein Ersatzprogramm ``opencode`` auf dem PATH
liefert den Modellkatalog (Muster ``tests/browser/test_ap03_agents_ui.py``).
Chromium kommt aus dem Nur-Lese-Cache, es gibt keine Modellaufrufe und keinen
Netzzugriff außerhalb von Loopback.

Getestet wird ausschließlich über die ``data-nv-*``-Hooks des Vertrags.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``ProjectHeroTest.test_open_project_from_home_shows_hero``
    Vorbedingung: Projekt ``proj`` mit ``.vibe/project.env``. Aktion:
    ``[data-nv-action="open-project"]`` auf der Startseite klicken.
    Erwartung: ``main[data-nv-view="project"]``, Titel ``proj``,
    Lauf-Pille ``running|stopped``, ``[data-nv-branch]`` vorhanden.
``ProjectTabsTest.test_tabs_switch_panels_and_expose_aria``
    Aktion: alle fünf ``data-nv-ptab`` prüfen, ``work`` und ``overview``
    anklicken. Erwartung: fünf ``role="tab"``, genau eine Auswahl,
    ``section[data-nv-ppanel]`` mit ``role="tabpanel"``; Sichtbarkeit folgt.
``OverviewTest.test_overview_tiles_show_fixture_counts``
    Vorbedingung: zwei offene Pakete, ein blockiertes, ein erledigtes, zwei
    Feedback-Einträge ohne Nachweis. Erwartung: Kacheln ``open=2``,
    ``blocked=1``, ``proof=2``, ``done=1``, ``feedback=2``.
``ChecksTest.test_checks_buttons_and_quick_verify_started``
    Vorbedingung: ``VERIFY_QUICK="true"``. Aktion: Quick-Knopf klicken.
    Erwartung: ``[data-nv-action="verify"]`` und ``[data-nv-verify="full"]``
    vorhanden; eine Startmeldung erscheint und das Prüfprotokoll entsteht.
``PauseTest.test_pause_toggle_and_home_badge``
    Aktion: ``[data-nv-action="pause"]`` klicken, zur Startseite wechseln.
    Erwartung: Pause-Datei angelegt, Projektkarte zeigt
    ``[data-nv-pause-badge]``.
``SettingsSectionsTest.test_project_settings_sections_and_hidden_features``
    Erwartung: ``team/basics/checks/pause/sessions`` vorhanden; die
    Feature-Bereiche ``github/writeaccess/sandbox/agentsfile`` fehlen ohne
    eingeschaltete Schalter vollständig im DOM.
``TeamTest.test_team_toggles_agent_and_saves_model_override``
    Vorbedingung: globale Agenten ``vibe-agent``, ``tester``, ``helper``.
    Aktion: Tester aktivieren, Modellüberschreibung wählen, neu laden.
    Erwartung: ``/api/project-agents`` führt ``selected=true`` und
    ``override=opencode/helper-modell``; nach Reload sind Schalter und
    Auswahl unverändert.
``BasicsTest.test_basics_has_init_button``
    Erwartung: ``[data-nv-action="init"]`` ist vorhanden (ohne Klick).
``AssistantTest.test_assistant_guide_and_autonomous_toggle``
    Vorbedingung: Projekt ohne ``SPEC.md``. Aktion: Autonom-Schalter klicken,
    neu laden. Erwartung: ``[data-nv-assistant]`` zeigt die Leitfaden-Schritte
    aus ``/api/guide``; ``/api/autonomous`` meldet ``enabled=true``, der
    Schalter bleibt nach dem Reload an.

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
----------------------------------------------------------
1. **Kachel-Zählung.** Der Vertrag nennt die Kacheln, aber nicht, ob
   ``open`` alle offenen Einträge (inklusive Feedback) oder nur die
   Board-Karten zählt. Hier zählen die Kacheln die Board-Karten; die
   Fixtures sind so gewählt, dass keine Feedback-Einträge offen sind und
   ``open`` deshalb in beiden Lesarten 2 ist. ``feedback`` wird als Zahl der
   Einträge in ``FEEDBACK.md`` gelesen (2).
2. **Feedback in der Nachweis-Spalte.** ``ohne Nachweis`` entsteht laut
   Backend ausschließlich bei ``FEEDBACK.md``-Einträgen; die Fixtures legen
   deshalb zwei Feedback-Einträge mit ungültigem Nachweis an, die als
   Board-Karten in der Nachweis-Spalte erwartet werden.
3. **Lauf-Pille.** Der Vertrag nennt keinen Wert-Hook. Geprüft wird
   ``data-state`` (wie auf der Startseite) mit Rückfall auf den sichtbaren
   Text; erlaubt sind ausschließlich ``running``/``stopped``.
4. **Fokus/Modellwahl.** Der Vertrag nennt keinen Speichern-Knopf für den
   Modell-Override; der Test erwartet die unmittelbare Wirkung des
   ``change``-Ereignisses über ``/api/project-agents``.
5. **Autonom-Schalter.** Der Vertrag nennt kein Elementtyp; der Test liest
   ``checked``, ``aria-checked`` oder ein ``data-on``-Merkmal.
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

TICKETS = """# TICKETS — AP22 Test

- [ ] AP-OPEN Offenes Paket
  Beschreibung: Noch offen.

- [ ] AP-OPEN2 Zweites offenes Paket
  Beschreibung: Ebenfalls offen.

- [ ] AP-BLOCK Blockiertes Paket
  Beschreibung: Wartet auf Freigabe.
  BLOCKIERT: externe Freigabe fehlt

- [x] AP-DONE Erledigtes Paket
  Beschreibung: Fertig.
"""

# Beide Feedback-Einträge sind abgehakt, der Commit existiert nicht: Damit
# klassifiziert das Backend sie als "ohne Nachweis" (Nachweis-Spalte).
FEEDBACK = """# FEEDBACK — AP22 Test

- [x] BUG-7 Absturz beim Start
  Beschreibung: Fenster bleibt leer.
  Art: Bug
  Commit: 1234567; Test: test_start

- [x] FB-1 Wunsch für die Oberfläche
  Beschreibung: Bitte größere Schaltflächen.
  Commit: 7654321; Test: test_ui
"""

VIBE_AGENT = """---
description: Vibe-Standardagent
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer.
"""

TESTER_AGENT = """---
description: Testet die Anwendung
mode: subagent
model: opencode/tester-modell
permission:
  read: allow
  edit: deny
---

Teste die Anwendung.
"""

HELPER_AGENT = """---
description: Hilft beim Testen
mode: subagent
model: opencode/helper-modell
permission:
  read: allow
  edit: deny
---

Hilf beim Testen.
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/tester-modell\\nopencode/helper-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

TILE_EXPECTED = {
    "open": 2,
    "blocked": 1,
    "proof": 2,
    "done": 1,
    "feedback": 2,
}

HIDDEN_SECTIONS = ("github", "writeaccess", "sandbox", "agentsfile")
VISIBLE_SECTIONS = ("team", "basics", "checks", "pause", "sessions")


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: leere Antworten, kein Modellaufruf."""

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


class AP22ProjectBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Attrappen und Fixtures für die Projektansicht."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\nVERIFY_QUICK=\"true\"\n",
            encoding="utf-8")
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        (cls.agents_dir / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (cls.agents_dir / "tester.md").write_text(TESTER_AGENT, encoding="utf-8")
        (cls.agents_dir / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
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
        cls.fake_bin = fake_bin

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
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
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
        # Alle veränderlichen Fixtures zurücksetzen, damit die Fälle
        # unabhängig von der Reihenfolge bleiben.
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        for path in (
            self.project / ".vibe" / "agents.json",
            self.log_dir / f"{PROJECT}.pause-after",
            self.log_dir / "autonomous.json",
            self.log_dir / "runs.json",
            self.log_dir / f"{PROJECT}.verify.log",
        ):
            path.unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

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

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        # Absolute URL: Der Helfer funktioniert auch, bevor die Seite geladen
        # ist, und hängt nicht von der aktuellen Origin ab.
        return self.page.evaluate(
            """async (url) => {
              const response = await fetch(url, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", self.base + path)

    def wait_api(self, path, predicate, timeout=20, message=None):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = self.api_json(path)
            except Exception:  # noqa: BLE001 - Polling darf kurze Fehler sehen
                last = None
            if last is not None and predicate(last):
                return last
            self.page.wait_for_timeout(150)
        self.fail((message or "API-Bedingung nicht erfüllt") + " — zuletzt: "
                  + repr(last))

    def boot(self):
        """Öffnet die neue UI mit Token-Tausch und wartet auf die Startseite."""
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_project(self):
        self.boot()
        self.page.locator("[data-nv-action='open-project']").first.click()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        return self.page.locator("main#nv-main[data-nv-view='project']")

    def open_tab(self, tab):
        self.page.locator(f"[data-nv-ptab='{tab}']").click()
        self.page.locator(f"section[data-nv-ppanel='{tab}']").wait_for(
            state="visible", timeout=20000)
        return self.page.locator(f"section[data-nv-ppanel='{tab}']")

    def open_route(self, route, view):
        self.page.goto(self.base + "/" + route)
        self.page.locator(f"main#nv-main[data-nv-view='{view}']").wait_for(
            state="visible", timeout=25000)

    def run_state(self):
        """Liest die Lauf-Pille als ``running``/``stopped``.

        Bevorzugt wird ``data-state`` (wie auf der Startseite); fehlt das
        Merkmal, wird der sichtbare Text abgebildet. Andere Werte sind laut
        Vertrag unzulässig und lassen den Test scheitern.
        """
        pill = self.page.locator("[data-nv-run-state]").first
        pill.wait_for(state="visible", timeout=20000)
        state = (pill.get_attribute("data-state") or "").strip().lower()
        text = (pill.inner_text() or "").strip().lower()
        mapping = {"läuft": "running", "gestoppt": "stopped",
                   "running": "running", "stopped": "stopped"}
        return state or mapping.get(text, text)

    def tile_value(self, name):
        tile = self.page.locator(f"[data-nv-tile='{name}']").first
        tile.wait_for(state="visible", timeout=20000)
        text = tile.inner_text() or ""
        match = re.search(r"\d+", text)
        self.assertIsNotNone(
            match, f"Kachel {name!r} zeigt keine Zahl: {text!r}")
        return int(match.group(0))

    def toggle_state(self, selector):
        return self.page.evaluate(
            """(selector) => {
              const node = document.querySelector(selector);
              if (!node) return null;
              if (typeof node.checked === 'boolean') return node.checked;
              const aria = node.getAttribute('aria-checked');
              if (aria !== null) return aria === 'true';
              const dataOn = node.getAttribute('data-on');
              if (dataOn !== null) return dataOn === 'true';
              return node.classList.contains('on') || node.classList.contains('active');
            }""", selector)

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Projektansicht erzeugte JavaScript-Fehler")


class ProjectHeroTest(AP22ProjectBrowserTest):
    def test_open_project_from_home_shows_hero(self):
        """Vorbedingung: Projekt ``proj`` ist auf der Startseite gelistet.

        Aktion: ``[data-nv-action="open-project"]`` klicken.
        Erwartung: ``main[data-nv-view="project"]``, der Titel lautet
        ``proj``, eine Lauf-Pille meldet ``running`` oder ``stopped`` und
        ``[data-nv-branch]`` ist vorhanden.
        """
        main = self.open_project()
        self.assertTrue(main.is_visible(), "Die Projektansicht ist nicht sichtbar")
        self.assertEqual(
            PROJECT, self.page.locator("[data-nv-project-title]").inner_text().strip(),
            "Der Projekttitel stimmt nicht mit dem Projektnamen überein")
        self.assertIn(
            self.run_state(), {"running", "stopped"},
            "Die Lauf-Pille zeigt keinen der Vertragswerte")
        self.assertEqual(
            1, self.page.locator("[data-nv-branch]").count(),
            "Der Branch-Hook [data-nv-branch] fehlt")
        self.assert_clean_page()


class ProjectTabsTest(AP22ProjectBrowserTest):
    def test_tabs_switch_panels_and_expose_aria(self):
        """Vorbedingung: Projektansicht geöffnet.

        Aktion: alle Tab-Hooks prüfen, ``work`` und ``overview`` anklicken.
        Erwartung: fünf ``role="tab"``-Knöpfe, genau eine Auswahl,
        ``section[data-nv-ppanel]`` mit ``role="tabpanel"``; nur das aktive
        Panel ist sichtbar.
        """
        self.open_project()
        tabs = ["overview", "work", "output", "assistant", "settings"]
        for tab in tabs:
            locator = self.page.locator(f"[data-nv-ptab='{tab}']")
            self.assertEqual(1, locator.count(), f"Tab {tab!r} fehlt")
            self.assertEqual(
                "tab", locator.get_attribute("role"),
                f"Tab {tab!r} hat keine ARIA-Rolle tab")
        self.assertEqual(
            1, self.page.locator("[data-nv-ptab][aria-selected='true']").count(),
            "Es ist nicht genau ein Tab als ausgewählt markiert")

        self.open_tab("work")
        self.assertFalse(
            self.page.locator("section[data-nv-ppanel='overview']").is_visible(),
            "Das Überblick-Panel bleibt trotz Wechsel auf Arbeit sichtbar")
        self.assertEqual(
            "true",
            self.page.locator("[data-nv-ptab='work']").get_attribute("aria-selected"),
            "Der Arbeits-Tab ist nach dem Wechsel nicht ausgewählt")
        for panel in tabs:
            self.assertEqual(
                1, self.page.locator(f"section[data-nv-ppanel='{panel}']").count(),
                f"Panel {panel!r} fehlt")
            self.assertEqual(
                "tabpanel",
                self.page.locator(
                    f"section[data-nv-ppanel='{panel}']").get_attribute("role"),
                f"Panel {panel!r} hat keine ARIA-Rolle tabpanel")

        self.open_tab("overview")
        self.assertTrue(
            self.page.locator("section[data-nv-ppanel='overview']").is_visible(),
            "Das Überblick-Panel ist nach dem Zurückwechseln nicht sichtbar")
        self.assert_clean_page()


class OverviewTest(AP22ProjectBrowserTest):
    def test_overview_tiles_show_fixture_counts(self):
        """Vorbedingung: Board mit zwei offenen, einem blockierten und einem
        erledigten Paket sowie zwei Feedback-Einträgen ohne Nachweis.

        Erwartung: Die Kacheln zeigen ``open=2``, ``blocked=1``, ``proof=2``,
        ``done=1`` und ``feedback=2``.
        """
        self.open_project()
        self.open_tab("overview")
        for name, expected in TILE_EXPECTED.items():
            with self.subTest(tile=name):
                self.assertEqual(
                    expected, self.tile_value(name),
                    f"Kachel {name!r} zeigt nicht die erwartete Anzahl")
        self.assert_clean_page()


class ChecksTest(AP22ProjectBrowserTest):
    def test_checks_buttons_and_quick_verify_started(self):
        """Vorbedingung: ``VERIFY_QUICK="true"`` in ``.vibe/project.env``.

        Aktion: Quick-Prüfung über ``[data-nv-action="verify"]`` starten.
        Erwartung: ``[data-nv-verify="full"]`` existiert; eine sichtbare
        Startmeldung erscheint und das Prüfprotokoll wird angelegt.
        """
        self.open_project()
        self.assertEqual(
            1, self.page.locator("[data-nv-action='verify']").count(),
            "Der Quick-Prüfknopf fehlt")
        self.assertEqual(
            1, self.page.locator("[data-nv-verify='full']").count(),
            "Der Voll-Prüfknopf [data-nv-verify='full'] fehlt")

        self.page.locator("[data-nv-action='verify']").first.click()
        verify_log = self.log_dir / f"{PROJECT}.verify.log"
        self.wait_until(
            lambda: verify_log.is_file() and verify_log.stat().st_size > 0,
            timeout=20,
            message="Die Schnellprüfung hat kein Protokoll geschrieben")
        self.wait_until(
            lambda: re.search(r"prüfung|pruefung|verify|gestartet|started",
                              self.page.locator("#nv-toasts").inner_text(),
                              re.I) is not None,
            timeout=20,
            message="Es erscheint keine Startmeldung zur Prüfung")
        self.assert_clean_page()


class PauseTest(AP22ProjectBrowserTest):
    def test_pause_toggle_and_home_badge(self):
        """Vorbedingung: keine Pause angefordert.

        Aktion: ``[data-nv-action="pause"]`` klicken, zur Startseite gehen.
        Erwartung: Die Pause-Datei existiert und die Projektkarte zeigt
        ``[data-nv-pause-badge]``.
        """
        self.open_project()
        button = self.page.locator("[data-nv-action='pause']").first
        button.wait_for(state="visible", timeout=20000)
        button.click()
        pause_file = self.log_dir / f"{PROJECT}.pause-after"
        self.wait_until(
            lambda: pause_file.is_file(),
            timeout=20,
            message="Die Pause-Anforderung wurde nicht gespeichert")

        self.page.locator("[data-nv-nav='home']").click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=20000)
        card = self.page.locator(f"[data-nv-project='{PROJECT}']")
        self.wait_until(
            lambda: card.locator("[data-nv-pause-badge]").count() == 1,
            timeout=20,
            message="Die Projektkarte zeigt nach der Pause kein Pause-Badge")
        self.assert_clean_page()


class SettingsSectionsTest(AP22ProjectBrowserTest):
    def test_project_settings_sections_and_hidden_features(self):
        """Vorbedingung: frischer Browserkontext, alle Feature-Schalter aus.

        Aktion: Projekt-Einstellungen öffnen.
        Erwartung: ``team/basics/checks/pause/sessions`` existieren; die
        Bereiche ``github/writeaccess/sandbox/agentsfile`` fehlen vollständig
        im DOM (nicht nur versteckt).
        """
        self.open_project()
        self.open_tab("settings")
        for section in VISIBLE_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    1, self.page.locator(f"[data-nv-psection='{section}']").count(),
                    f"Projekteinstellung {section!r} fehlt")
        for section in HIDDEN_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    0, self.page.locator(f"[data-nv-psection='{section}']").count(),
                    f"Technischer Bereich {section!r} ist ohne Feature sichtbar")
        self.assert_clean_page()


class TeamTest(AP22ProjectBrowserTest):
    def test_team_toggles_agent_and_saves_model_override(self):
        """Vorbedingung: globale Agenten ``vibe-agent``, ``tester``, ``helper``.

        Aktion: Tester aktivieren, ``opencode/helper-modell`` als
        Überschreibung wählen, Seite neu laden.
        Erwartung: ``/api/project-agents`` meldet ``selected=true`` und
        ``override=opencode/helper-modell``; nach Reload sind Schalter und
        Auswahl unverändert.
        """
        self.open_project()
        self.open_tab("settings")
        row = self.page.locator("[data-nv-team-agent='tester']").first
        row.wait_for(state="visible", timeout=20000)
        toggle = row.locator("input[data-nv-agent-toggle]")
        self.assertEqual(1, toggle.count(),
                         "Der Aktiv-Schalter des Agenten fehlt")
        self.assertFalse(toggle.is_checked(),
                         "Der Tester ist ohne Zutun bereits aktiv")
        toggle.click()
        self.wait_api(
            f"/api/project-agents?name={PROJECT}",
            lambda data: any(
                agent.get("name") == "tester" and agent.get("selected")
                for agent in data.get("agents", [])),
            message="Der Aktiv-Schalter wurde nicht gespeichert")

        row = self.page.locator("[data-nv-team-agent='tester']").first
        model = row.locator("select[data-nv-agent-model]").first
        self.assertEqual(1, model.count(), "Die Modellwahl des Agenten fehlt")
        self.wait_until(
            lambda: model.locator(
                "option[value='opencode/helper-modell']").count() == 1,
            timeout=20,
            message="Der Modellkatalog enthält das Ersatzmodell nicht")
        model.select_option("opencode/helper-modell")
        self.wait_api(
            f"/api/project-agents?name={PROJECT}",
            lambda data: any(
                agent.get("name") == "tester"
                and agent.get("override") == "opencode/helper-modell"
                for agent in data.get("agents", [])),
            message="Die Modellüberschreibung wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        row = self.page.locator("[data-nv-team-agent='tester']").first
        row.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            row.locator("input[data-nv-agent-toggle]").is_checked(),
            "Der Aktiv-Schalter ging beim Reload verloren")
        self.assertEqual(
            "opencode/helper-modell",
            row.locator("select[data-nv-agent-model]").input_value(),
            "Die Modellüberschreibung ging beim Reload verloren")
        self.assert_clean_page()


class BasicsTest(AP22ProjectBrowserTest):
    def test_basics_has_init_button(self):
        """Vorbedingung: Projekt geöffnet. Aktion: Einstellungen, Bereich
        ``basics`` prüfen (ohne Klick).
        Erwartung: ``[data-nv-action="init"]`` ist vorhanden.
        """
        self.open_project()
        self.open_tab("settings")
        self.assertEqual(
            1, self.page.locator("[data-nv-action='init']").count(),
            "Der Knopf „Projekt vorbereiten“ fehlt")
        self.assert_clean_page()


class AssistantTest(AP22ProjectBrowserTest):
    def test_assistant_guide_and_autonomous_toggle(self):
        """Vorbedingung: Projekt ohne ``SPEC.md``.

        Aktion: Assistent öffnen, Autonom-Schalter klicken, Seite neu laden.
        Erwartung: ``[data-nv-assistant]`` zeigt die Leitfaden-Schritte aus
        ``/api/guide``; ``/api/autonomous`` meldet ``enabled=true`` und der
        Schalter bleibt nach dem Reload an.
        """
        # Erst booten: Relativer API-Zugriff aus ``about:blank`` wäre sonst
        # ein Harness-Fehler, kein Aussagesatz über die Oberfläche.
        self.boot()
        guide = self.api_json(f"/api/guide?name={PROJECT}")
        self.assertTrue(guide.get("steps"), "Der Leitfaden liefert keine Schritte")
        first_title = str(guide["steps"][0].get("title") or "")

        self.page.locator("[data-nv-action='open-project']").first.click()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.open_tab("assistant")
        assistant = self.page.locator("[data-nv-assistant]")
        assistant.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: first_title in assistant.inner_text(),
            timeout=20,
            message="Der Assistent zeigt den ersten Leitfaden-Schritt nicht: "
                    + repr(first_title))

        toggle = self.page.locator("[data-nv-autonomous]").first
        toggle.wait_for(state="visible", timeout=20000)
        self.assertFalse(self.toggle_state("[data-nv-autonomous]"),
                         "Der autonome Modus ist ohne Zutun bereits aktiv")
        toggle.click()
        self.wait_api(
            f"/api/autonomous?name={PROJECT}",
            lambda data: data.get("enabled") is True,
            message="Der autonome Modus wurde nicht aktiviert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.wait_until(
            lambda: self.page.locator("[data-nv-autonomous]").count() == 1,
            timeout=20,
            message="Der Autonom-Schalter fehlt nach dem Reload")
        self.assertTrue(
            self.toggle_state("[data-nv-autonomous]"),
            "Der autonome Modus ging beim Reload verloren")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
