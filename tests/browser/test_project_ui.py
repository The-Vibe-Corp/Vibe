"""Projektansicht: Übersicht, Tabs, Arbeit, Einstellungen, Sitzungen, Keep-Changes, AGENTS.md und Paketprüfung.

Aufruf: python3 -m unittest tests.browser.test_project_ui -v
"""


# ===========================================================================
# Browserabnahme, Meilenstein B: Projektansicht und Projekteinstellungen
# ===========================================================================

import http.client
import json
import os
import re
import shutil
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

STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


# GH-48: Ticketzustände kommen aus dem Speicher. Zwei offene Pakete, ein
# blockiertes, ein erledigtes sowie zwei Feedback-Einträge.
TICKETS = [
    ticket_record("AP-1", "Offenes Paket", description="Noch offen."),
    ticket_record("AP-2", "Zweites offenes Paket",
                  description="Ebenfalls offen."),
    ticket_record("AP-3", "Blockiertes Paket", state="blocked",
                  description="Wartet auf Freigabe.",
                  blocked_reason="externe Freigabe fehlt"),
    ticket_record("AP-4", "Erledigtes Paket", state="done",
                  description="Fertig.", commit="1234567",
                  test="test_done"),
    ticket_record("BUG-7", "Absturz beim Start", type="bug",
                  description="Fenster bleibt leer."),
    ticket_record("FB-1", "Wunsch für die Oberfläche", type="feedback",
                  description="Bitte größere Schaltflächen."),
]


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
    "done": 1,
}
# F34: Kacheln „Feedback“ und „Ohne Nachweis“ entfallen; der Zustand „ohne
# Nachweis“ erscheint als Badge ``[data-nv-proof]`` an den Einträgen.
REMOVED_TILES = ("proof", "feedback")

HIDDEN_SECTIONS = ("github", "writeaccess", "sandbox", "agentsfile")
# F33 WP3/2r: die eigene Pause-Sektion ist entfallen (Status als Pille im
# Überblick), daher nicht mehr in den erwarteten Sektionen.
# F34: „Prüfungen“ (checks) und die Sessions-Liste entfallen; das
# Session-Limit ist projektspezifisch und ohne Feature-Schalter sichtbar.
VISIBLE_SECTIONS = ("team", "basics", "session-limit")
REMOVED_SECTIONS = ("checks", "sessions")

# Review-Fix AP22: lokaler GitHub-REST-Ersatz und lokales Git-Remote.
# Es gibt keinen Netzzugriff außerhalb von Loopback; die API-Basis steht in
# der project.env und wird ausschließlich von bewussten Aktionen kontaktiert.
GITHUB_TOKEN = "ap22-review-token-4711"
GITHUB_ISSUES = [
    {
        "number": 7,
        "title": "Sandbox für Import einschränken",
        "state": "open",
        "html_url": "http://127.0.0.1/owner/name/issues/7",
        "labels": [{"name": "vibe"}],
    },
    {
        "number": 8,
        "title": "Bug im Label-Filter",
        "state": "open",
        "html_url": "http://127.0.0.1/owner/name/issues/8",
        "labels": [{"name": "bug"}],
    },
]

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env, check=check,
        capture_output=True, text=True, timeout=60)


def git_out(cwd, *argv):
    return git(cwd, *argv).stdout.strip()


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


class _FakeGithubHandler(BaseHTTPRequestHandler):
    """GitHub-REST-Attrappe: nur Loopback, keine echten GitHub-Aufrufe."""

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
        self.server.requests.append({"method": "GET", "path": self.path})
        if self.path.startswith("/repos/owner/name/issues"):
            self._send_json(200, self.server.issues)
        elif self.path.startswith("/repos/owner/name"):
            self._send_json(200, {"full_name": "owner/name"})
        else:
            self._send_json(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append({"method": "POST", "path": self.path})
        if self.path.startswith("/repos/owner/name/pulls"):
            self.server.pr_posts.append({
                "path": self.path,
                "body": body.decode("utf-8") if body else "",
            })
            self._send_json(201, {
                "number": 42,
                "html_url": "http://127.0.0.1/owner/name/pull/42",
            })
        else:
            self._send_json(404, {"message": "Not Found"})


class FakeGithubServer:
    """Lokaler GitHub-REST-Ersatz mit Aufzeichnung aller Anfragen."""

    def __init__(self):
        self.requests = []
        self.pr_posts = []
        self.issues = list(GITHUB_ISSUES)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _FakeGithubHandler)
        self.httpd.daemon_threads = True
        self.httpd.requests = self.requests
        self.httpd.pr_posts = self.pr_posts
        self.httpd.issues = self.issues
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


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

        # Review-Fix AP22: lokales Git-Remote und GitHub-REST-Attrappe.
        # Beides entsteht vor dem Serverstart; alle Aufrufe bleiben auf
        # Loopback beziehungsweise file:// beschränkt.
        cls.github = FakeGithubServer().start()
        bare = cls.root / "_origin.git"
        bare.mkdir()
        git(bare, "init", "-q", "--bare", "-b", "main")
        git(cls.project, "init", "-q", "-b", "main")
        git(cls.project, "commit", "--allow-empty", "-q", "-m", "init")
        git(cls.project, "remote", "add", "origin", "file://" + str(bare))
        git(cls.project, "push", "-q", "-u", "origin", "main")
        git(cls.project, "branch", "feature/arbeit")
        cls.bare = bare
        cls.write_project_env()

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
    def write_project_env(cls, enabled=False, api=None, base="main"):
        """Schreibt die Projektkonfiguration inklusive Git-&-GitHub-Schlüssel."""
        keys = [
            "TYPE=generic",
            "AGENT=tester",
            'VERIFY_QUICK="true"',
            'GITHUB_ENABLED="%s"' % ("1" if enabled else ""),
            'GITHUB_REPO="owner/name"',
            'GITHUB_LABEL="vibe"',
            'GITHUB_API="%s"' % (api or cls.github.base),
            'GITHUB_BASE="%s"' % base,
        ]
        (cls.project / ".vibe" / "project.env").write_text(
            "\n".join(keys) + "\n", encoding="utf-8")

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
            try:
                cls.github.stop()
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
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": TICKETS},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        for path in (
            self.project / ".vibe" / "agents.json",
            self.log_dir / f"{PROJECT}.pause-after",
            self.log_dir / "autonomous.json",
            self.log_dir / "runs.json",
            self.log_dir / f"{PROJECT}.verify.log",
        ):
            path.unlink(missing_ok=True)
        self.write_project_env()
        shutil.rmtree(self.state_dir / "github-tokens", ignore_errors=True)
        for token_file in (self.state_dir / "github-token.key",
                           self.state_dir / "github-token"):
            Path(token_file).unlink(missing_ok=True)
        try:
            git(self.project, "checkout", "-q", "-f", "main")
        except subprocess.CalledProcessError:
            pass
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


class OverviewTilesTest(AP22ProjectBrowserTest):
    def test_overview_tiles_show_fixture_counts(self):
        """Vorbedingung: Board mit zwei offenen, einem blockierten und einem
        erledigten Paket sowie zwei Feedback-Einträgen ohne Nachweis.

        Erwartung: Die Kacheln zeigen ``open=2``, ``blocked=1`` und ``done=1``.
        F34: Die Kacheln „Feedback“ und „Ohne Nachweis“ entfallen; der Zustand
        „ohne Nachweis“ erscheint als Badge ``[data-nv-proof]`` an den
        betroffenen Einträgen der Arbeitsliste. Beides wird geprüft: die
        Kacheln per Abwesenheitsprüfung, das Badge an ``BUG-7`` und ``FB-1``.
        """
        self.open_project()
        self.open_tab("overview")
        for name, expected in TILE_EXPECTED.items():
            with self.subTest(tile=name):
                self.assertEqual(
                    expected, self.tile_value(name),
                    f"Kachel {name!r} zeigt nicht die erwartete Anzahl")
        for tile in REMOVED_TILES:
            with self.subTest(tile=tile):
                self.assertEqual(
                    0, self.page.locator(f"[data-nv-tile='{tile}']").count(),
                    f"Die entfallene Kachel {tile!r} existiert entgegen dem F34-Vertrag")
        # GH-48: Der Zustand „ohne Nachweis" existiert nicht mehr. Die
        # Arbeitsliste zeigt die Speicherzustände: das erledigte Paket mit
        # „erledigt", die beiden Feedback-Einträge offen.
        self.open_tab("work")
        done = self.page.locator("article[data-nv-ticket='AP-4']")
        done.wait_for(state="attached", timeout=20000)
        self.assertFalse(done.is_visible(),
                         "erledigtes Paket ist im Standard sichtbar")
        self.page.locator("[data-nv-work-hide-done]").click()
        done.wait_for(state="visible", timeout=20000)
        self.assertRegex(done.inner_text(), r"(?i)erledigt|done")
        for entry in ("BUG-7", "FB-1"):
            card = self.page.locator(f"article[data-nv-feedback-item='{entry}']")
            card.wait_for(state="visible", timeout=20000)
            self.assertRegex(card.inner_text(), r"(?i)offen|open")
        self.assert_clean_page()


class ChecksTest(AP22ProjectBrowserTest):
    def test_checks_buttons_and_quick_verify_started(self):
        """Vorbedingung: ``VERIFY_QUICK="true"`` in ``.vibe/project.env``.

        GH-108: Prüfen und Vollprüfung liegen im „Weitere Aktionen“-Dropdown
        des Headers und sind dort erst nach dem Aufklappen erreichbar.
        Aktion: Dropdown öffnen und Quick-Prüfung starten. Erwartung: Beide
        Knöpfe sind im Dropdown vorhanden, eine sichtbare Startmeldung
        erscheint und das Prüfprotokoll wird angelegt.
        """
        self.open_project()
        more = self.page.locator("details[data-nv-more-actions]")
        self.assertEqual(1, more.count(), "Das Aktions-Dropdown fehlt im Header")
        quick = more.locator("[data-nv-action='verify']")
        full = more.locator("[data-nv-verify='full']")
        self.assertEqual(1, quick.count(), "Der Quick-Prüfknopf fehlt im Dropdown")
        self.assertEqual(
            1, full.count(), "Der Voll-Prüfknopf fehlt im Dropdown")
        self.assertFalse(quick.is_visible(),
                         "Die Prüfknöpfe sind ohne Dropdown sichtbar")
        more.locator("summary").click()
        self.assertTrue(quick.is_visible(),
                        "Die Prüfknöpfe bleiben nach dem Öffnen verborgen")

        quick.click()
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

        self.page.locator("nav[data-nv-navs] [data-nv-nav='home']").click()
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
        Erwartung: ``team/basics/session-limit`` existieren; die Pause-Sektion,
        „Prüfungen“ (``checks``) und die Sessions-Liste sind entfallen (F34);
        die Feature-Bereiche ``github/writeaccess/sandbox/agentsfile`` fehlen
        vollständig im DOM (nicht nur versteckt).
        """
        self.open_project()
        self.open_tab("settings")
        for section in VISIBLE_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    1, self.page.locator(f"[data-nv-psection='{section}']").count(),
                    f"Projekteinstellung {section!r} fehlt")
        # F34: „Prüfungen“ (checks) und die Sessions-Liste entfallen.
        for section in REMOVED_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    0, self.page.locator(f"[data-nv-psection='{section}']").count(),
                    f"Entfernter Bereich {section!r} existiert entgegen dem F34-Vertrag")
        # F33 WP3/2r: die Pause-Sektion darf nicht mehr existieren.
        self.assertEqual(
            0, self.page.locator("[data-nv-psection='pause']").count(),
            "Die eigene Pause-Sektion existiert entgegen dem F33-Vertrag")
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
        # F33 WP3: die Modellwahl ist eine Combobox (kein select); Bedienung
        # über Eingabefeld und Optionsliste, Wert steht in data-nv-value.
        model = row.locator(
            "div[data-nv-combobox][data-nv-agent-model]").first
        self.assertEqual(1, model.count(), "Die Modellwahl des Agenten fehlt")
        model.locator("input[data-nv-combobox-input]").click()
        option = model.locator("li[data-nv-combobox-option]",
                               has_text="opencode/helper-modell")
        self.wait_until(
            lambda: option.count() == 1,
            timeout=20,
            message="Der Modellkatalog enthält das Ersatzmodell nicht")
        option.first.click()
        self.assertEqual(
            "opencode/helper-modell", model.get_attribute("data-nv-value"),
            "Die Modellauswahl wurde nicht übernommen")
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
        # F33 WP3: der gespeicherte Wert steht am Combobox-Container.
        self.assertEqual(
            "opencode/helper-modell",
            row.locator(
                "div[data-nv-combobox][data-nv-agent-model]"
            ).get_attribute("data-nv-value"),
            "Die Modellüberschreibung ging beim Reload verloren")
        self.assert_clean_page()


class OpencodeTeamTest(AP22ProjectBrowserTest):
    def test_opencode_team_agents_are_marked_toggleable_and_persisted(self):
        """AK B5: general/explore sind als OpenCode markiert und bleiben wählbar.

        Vorbedingung: globale Agenten; Projekt ``proj`` geöffnet.
        Aktion: Team-Bereich öffnen, general abwählen, explore ein Modell
        geben, Seite neu laden.
        Erwartung: OpenCode-Kennzeichnung, gespeicherter Schalter und Modell
        sind nach dem Reload unverändert sichtbar.
        """
        self.open_project()
        self.open_tab("settings")

        general = self.page.locator("[data-nv-team-agent='general']").first
        general.wait_for(state="visible", timeout=20000)
        explore = self.page.locator("[data-nv-team-agent='explore']").first
        explore.wait_for(state="visible", timeout=20000)
        for row in (general, explore):
            self.assertIn(
                "opencode", row.inner_text().lower(),
                "Der opencode-Agent ist im Team-Bereich nicht als OpenCode markiert")
        self.assertIn(
            "opencode",
            self.page.locator("[data-nv-psection='team']").inner_text().lower(),
            "Die OpenCode-Kennzeichnung fehlt im Team-Bereich")

        toggle = general.locator("input[data-nv-agent-toggle]")
        self.assertTrue(toggle.is_checked(),
                        "Der opencode-Agent general ist nicht standardmäßig erlaubt")
        toggle.click()
        self.wait_api(
            f"/api/project-agents?name={PROJECT}",
            lambda data: any(
                agent.get("name") == "general" and agent.get("configured") is False
                for agent in data.get("agents", [])),
            message="Der OpenCode-Toggle wurde nicht gespeichert")

        # F33 WP3: die Modellwahl ist eine Combobox (kein select); Bedienung
        # über Eingabefeld und Optionsliste, Wert steht in data-nv-value.
        model = explore.locator(
            "div[data-nv-combobox][data-nv-agent-model]").first
        model.locator("input[data-nv-combobox-input]").click()
        option = model.locator("li[data-nv-combobox-option]",
                               has_text="opencode/helper-modell")
        self.wait_until(
            lambda: option.count() == 1,
            timeout=20,
            message="Der Modellkatalog enthält das Ersatzmodell nicht")
        option.first.click()
        self.assertEqual(
            "opencode/helper-modell", model.get_attribute("data-nv-value"),
            "Die Modellauswahl wurde nicht übernommen")
        self.wait_api(
            f"/api/project-agents?name={PROJECT}",
            lambda data: any(
                agent.get("name") == "explore"
                and agent.get("override") == "opencode/helper-modell"
                for agent in data.get("agents", [])),
            message="Das OpenCode-Modell wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        general = self.page.locator("[data-nv-team-agent='general']").first
        general.wait_for(state="visible", timeout=20000)
        self.assertFalse(
            general.locator("input[data-nv-agent-toggle]").is_checked(),
            "Der OpenCode-Schalter ging beim Reload verloren")
        explore = self.page.locator("[data-nv-team-agent='explore']").first
        # F33 WP3: der gespeicherte Wert steht am Combobox-Container.
        self.assertEqual(
            "opencode/helper-modell",
            explore.locator(
                "div[data-nv-combobox][data-nv-agent-model]"
            ).get_attribute("data-nv-value"),
            "Das OpenCode-Modell ging beim Reload verloren")
        self.assert_clean_page()


class BasicsTest(AP22ProjectBrowserTest):
    def test_basics_has_init_button(self):
        """Vorbedingung: unvorbereitetes Projekt (keine ``.vibe/project.env``).

        Aktion: Einstellungen, Bereich ``basics`` öffnen (ohne Klick).
        Erwartung: ``[data-nv-action="init"]`` ist vorhanden — F34: der Knopf
        „Projekt vorbereiten“ erscheint nur bei unvorbereitetem Projekt; nach
        dem Anlegen der ``project.env`` entfällt er wieder.
        """
        (self.project / ".vibe" / "project.env").unlink(missing_ok=True)
        self.open_project()
        self.open_tab("settings")
        self.assertEqual(
            1, self.page.locator("[data-nv-action='init']").count(),
            "Der Knopf „Projekt vorbereiten“ fehlt")
        self.write_project_env()
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.open_tab("settings")
        self.assertEqual(
            0, self.page.locator("[data-nv-action='init']").count(),
            "Der Knopf „Projekt vorbereiten“ darf bei vorbereitetem Projekt "
            "nicht angezeigt werden")
        self.assert_clean_page()


class AssistantGuideTest(AP22ProjectBrowserTest):
    def test_assistant_guide_and_autonomous_toggle(self):
        """Vorbedingung: Projekt ohne ``SPEC.md``.

        Aktion: Assistent öffnen, Autonom-Schalter klicken, Seite neu laden.
        Erwartung: ``[data-nv-assistant]`` zeigt die Leitfaden-Schritte aus
        ``/api/guide``; ``/api/autonomous`` meldet ``enabled=true`` und der
        Schalter bleibt nach dem Reload an. Die Autonom-Zeile liegt dabei
        vertragsgemäß im Überblick (``div[data-nv-autonomous-row]``), nicht
        mehr im Beschreibungs-Tab. F34: Die Leitfadenüberschrift ist die über
        ``tr()`` vollständig übersetzte Form (Backend-„Produktziel“ erscheint als
        „Projektziel“/„Project goal“).
        """
        # Erst booten: Relativer API-Zugriff aus ``about:blank`` wäre sonst
        # ein Harness-Fehler, kein Aussagesatz über die Oberfläche.
        self.boot()
        guide = self.api_json(f"/api/guide?name={PROJECT}")
        self.assertTrue(guide.get("steps"), "Der Leitfaden liefert keine Schritte")
        first_title = str(guide["steps"][0].get("title") or "")
        # F34: Schrittüberschriften sind vollständig über ``tr()`` übersetzt;
        # der Backend-Titel „Produktziel“ erscheint als „Projektziel“ (de) bzw.
        # „Project goal“ (en) — die UI zeigt die übersetzte Form.
        first_heading = "Project goal" if first_title == "Produktziel" else first_title

        self.page.locator("[data-nv-action='open-project']").first.click()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.open_tab("assistant")
        assistant = self.page.locator("[data-nv-assistant]")
        assistant.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: first_heading in assistant.inner_text(),
            timeout=20,
            message="Der Assistent zeigt den ersten Leitfaden-Schritt nicht: "
                    + repr(first_heading))

        # F33 WP3/2q: die Autonom-Zeile steht im Überblick; die Leitfragen
        # bleiben im Tab und wurden oben geprüft (keine Abschwächung).
        self.open_tab("overview")
        row = self.page.locator(
            "section[data-nv-ppanel='overview'] div[data-nv-autonomous-row]")
        row.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            row.inner_text() or "",
            re.compile(r"automatisch|automatic|rückfragen|questions", re.I),
            "Die Autonom-Zeile erklärt das automatische Beantworten nicht: "
            + repr(row.inner_text()))
        toggle = row.locator("input[data-nv-autonomous]")
        self.assertEqual(
            1, toggle.count(),
            "Die Autonom-Zeile enthält keinen Schalter [data-nv-autonomous]")
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
        # F33 WP3: nach dem Reload erneut den Überblick öffnen.
        self.open_tab("overview")
        row = self.page.locator(
            "section[data-nv-ppanel='overview'] div[data-nv-autonomous-row]")
        row.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, row.locator("input[data-nv-autonomous]").count(),
            "Der Autonom-Schalter fehlt nach dem Reload")
        self.assertTrue(
            self.toggle_state("[data-nv-autonomous]"),
            "Der autonome Modus ging beim Reload verloren")
        self.assert_clean_page()


class GithubParityTest(AP22ProjectBrowserTest):
    """Review-Fix AP22: Git & GitHub deckt die zugesagte CLI-Parität ab.

    Verbindliche DOM-Hooks dieser Runde (der Vertrag nennt die Aktionen, aber
    keine Elementnamen; die Fix-Runde setzt genau diese Namen um)::

        input[data-nv-field="github-enabled"]        Aktivierung (Checkbox)
        [data-nv-action="github-settings-save"]      Einstellungen speichern
        input[data-nv-field="github-token"]          Token-Eingabe
        [data-nv-action="github-token-save"]         Token speichern
        [data-nv-action="github-token-clear"]        Token löschen
        [data-nv-github-auth]                        maskierte Token-Zeile
        [data-nv-action="github-connection"]         Verbindung prüfen
        [data-nv-github-connection][data-nv-ok]      strukturiertes Ergebnis
        [data-nv-github-branch="<branch>"]           Branch-Zeile
        [data-nv-action="github-checkout"]           Branch auschecken
        select[data-nv-github-push-branch]           Push: Quelle
        select[data-nv-github-push-target]           Push: Ziel
        [data-nv-action="github-push"]               Push ausführen
        [data-nv-action="github-pull"]               Pull (--ff-only)
        [data-nv-action="issues-sync"]               einen Issues-Sync
                                                    (GH-47: kein
                                                    github-issues/import)
        [data-nv-action="github-pr"]                 Merge-Request anfragen
        [data-nv-github-pr-confirm]                  Bestätigungsbereich
        [data-nv-action="github-pr-confirm"]         Merge-Request bestätigen
        [data-nv-github-pr-result]                   Ergebnis des Versuchs

    Alle Git-Aufrufe laufen gegen ein lokales Bare-Repository (``file://``),
    die GitHub-REST-Ebene gegen eine Attrappe auf 127.0.0.1. Ein echter
    github.com-Kontakt ist ausgeschlossen.
    """

    def enable_github_feature(self):
        """Schaltet den Feature-Schalter ``github`` über #/settings ein."""
        self.boot()
        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        box = self.page.locator("input[data-nv-feature='github']")
        box.wait_for(state="visible", timeout=20000)
        if not box.is_checked():
            box.check()
        self.wait_until(lambda: box.is_checked(), timeout=20,
                        message="Der Feature-Schalter github blieb aus")

    def reload_github_section(self):
        self.page.goto(self.base + "/#/project/proj/settings")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        section = self.page.locator("[data-nv-psection='github']")
        section.wait_for(state="visible", timeout=25000)
        return section

    def open_github_section(self):
        self.enable_github_feature()
        return self.reload_github_section()

    def activate_github(self):
        """Aktiviert die Projektverknüpfung über die Oberfläche."""
        self.write_project_env(enabled=False)
        section = self.open_github_section()
        box = section.locator("input[data-nv-field='github-enabled']")
        box.wait_for(state="visible", timeout=20000)
        if not box.is_checked():
            box.check()
        section.locator("[data-nv-action='github-settings-save']").first.click()
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: data.get("github", {}).get("enabled") is True,
            message="Die GitHub-Aktivierung wurde nicht gespeichert")
        return self.reload_github_section()

    def save_token(self):
        section = self.reload_github_section()
        field = section.locator("input[data-nv-field='github-token']")
        field.wait_for(state="visible", timeout=20000)
        field.fill(GITHUB_TOKEN)
        section.locator("[data-nv-action='github-token-save']").first.click()
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: data.get("github", {}).get("auth", {}).get("set") is True,
            message="Der GitHub-Token wurde nicht gespeichert")
        return self.reload_github_section()

    def remote_tip(self, branch):
        out = git_out(self.project, "ls-remote", "origin",
                      f"refs/heads/{branch}")
        return out.split()[0] if out else ""

    def enable_issue_sync_env(self, api=None):
        """GH-47: Issues-Sync zusätzlich zur GitHub-Verknüpfung aktivieren."""
        self.write_project_env(enabled=True, api=api)
        path = self.project / ".vibe" / "project.env"
        path.write_text(
            path.read_text(encoding="utf-8")
            + 'GITHUB_ISSUES_ENABLED="1"\n',
            encoding="utf-8")
        # Derselbe Hash lädt die Seite nicht neu; ohne Reload bliebe der
        # Issues-Schalter aus dem vorherigen Projektstand stehen.
        self.page.reload()

    def test_github_section_offers_every_parity_action(self):
        """Vorbedingung: Feature ``github`` ist über #/settings eingeschaltet,
        Issues-Sync ist aktiv.

        Erwartung (GH-47/q6cbba05d8ca9): Der Projektbereich
        ``[data-nv-psection="github"]`` bietet Aktivierung, Token
        speichern/löschen, Verbindungstest, Branch-Zeilen mit Auschecken,
        Pull, Push mit Quelle/Ziel, genau einen Issues-Sync und den
        Merge-Request samt Bestätigung; die getrennten Aktionen
        ``github-issues``/``github-import`` fehlen.
        """
        self.activate_github()
        self.enable_issue_sync_env()
        section = self.reload_github_section()
        controls = [
            "input[data-nv-field='github-enabled']",
            "[data-nv-action='github-settings-save']",
            "input[data-nv-field='github-token']",
            "[data-nv-action='github-token-save']",
            "[data-nv-action='github-token-clear']",
            "[data-nv-action='github-connection']",
            "select[data-nv-github-push-branch]",
            "select[data-nv-github-push-target]",
            "[data-nv-action='github-push']",
            "[data-nv-action='github-pull']",
            "[data-nv-action='issues-sync']",
            "[data-nv-action='github-pr']",
        ]
        for selector in controls:
            with self.subTest(control=selector):
                self.assertEqual(
                    1, section.locator(selector).count(),
                    f"GitHub-Bedienelement {selector!r} fehlt")
        for selector in ("[data-nv-action='github-issues']",
                         "[data-nv-action='github-import']",
                         "[data-nv-field='github-issue-label']"):
            with self.subTest(removed=selector):
                self.assertEqual(
                    0, section.locator(selector).count(),
                    f"Entfallenes Bedienelement {selector!r} ist noch da")
        main_row = section.locator("[data-nv-github-branch='main']")
        self.assertEqual(
            1, main_row.count(),
            "Die Branch-Zeile [data-nv-github-branch='main'] fehlt")
        self.assertEqual(
            1, main_row.locator("[data-nv-action='github-checkout']").count(),
            "Der Auschecken-Knopf der Branch-Zeile fehlt")
        self.assert_clean_page()

    def test_github_activation_toggle_persists_enable_and_disable(self):
        """Vorbedingung: Projekt mit ``GITHUB_ENABLED=""``.

        Aktion: Schalter ``github-enabled`` einschalten und speichern, danach
        ausschalten und speichern.
        Erwartung: ``/api/project`` meldet ``github.enabled`` wahr bzw. falsch;
        die project.env enthält nach dem Einschalten ``GITHUB_ENABLED="1"``.
        """
        self.write_project_env(enabled=False)
        section = self.open_github_section()
        toggle = section.locator("input[data-nv-field='github-enabled']")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertFalse(toggle.is_checked(),
                         "Die Verknüpfung ist ohne Zutun bereits aktiv")
        toggle.check()
        section.locator("[data-nv-action='github-settings-save']").first.click()
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: data.get("github", {}).get("enabled") is True,
            message="Das Einschalten der GitHub-Verknüpfung wurde nicht "
                    "gespeichert")
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn('GITHUB_ENABLED="1"', env_text,
                      "Die project.env wurde nicht aktiviert")

        section = self.reload_github_section()
        toggle = section.locator("input[data-nv-field='github-enabled']")
        self.assertTrue(toggle.is_checked(),
                        "Der Aktiv-Schalter zeigt den gespeicherten Zustand "
                        "nicht")
        toggle.uncheck()
        section.locator("[data-nv-action='github-settings-save']").first.click()
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: data.get("github", {}).get("enabled") is False,
            message="Das Ausschalten der GitHub-Verknüpfung wurde nicht "
                    "gespeichert")
        self.assert_clean_page()

    def test_github_token_save_masks_status_and_clear_removes_it(self):
        """Vorbedingung: Feature github aktiv, kein Token hinterlegt.

        Aktion: Token über die Oberfläche speichern, danach löschen.
        Erwartung: Die Projekt-API meldet ``auth.set=true`` mit Quelle
        ``projekt``; die Statuspille ``[data-nv-github-token-state]`` enthält
        den Token nicht und meldet nach dem Speichern den gesetzten Zustand
        („Token hinterlegt“); nach dem Löschen ist ``auth.set=false`` und die
        Pille meldet den leeren Zustand.
        """
        self.activate_github()
        section = self.save_token()
        token_state = section.locator("span[data-nv-github-token-state]")
        token_state.wait_for(state="visible", timeout=20000)
        self.assertNotIn(GITHUB_TOKEN, section.inner_text(),
                         "Der Token steht unmaskiert im DOM")
        self.wait_until(
            lambda: re.search(r"(?i)token (hinterlegt|stored)",
                              token_state.inner_text() or ""),
            timeout=20,
            message="Die Token-Statuspille meldet nicht den gesetzten Zustand: "
                    + repr(token_state.inner_text()))
        self.assertTrue(
            self.api_json(f"/api/project?name={PROJECT}")["github"]["auth"]["set"],
            "Der Token ist serverseitig nicht gesetzt")
        self.assertEqual(
            "projekt",
            self.api_json(f"/api/project?name={PROJECT}")["github"]["auth"]["source"],
            "Der Token wurde nicht als Projekt-Token abgelegt")

        section.locator("[data-nv-action='github-token-clear']").first.click()
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: data.get("github", {}).get("auth", {}).get("set") is False,
            message="Der Token wurde nicht entfernt")
        token_state = section.locator("span[data-nv-github-token-state]")
        self.wait_until(
            lambda: re.search(r"(?i)(kein token|no token)",
                              token_state.inner_text() or ""),
            timeout=20,
            message="Die Token-Statuspille zeigt nach dem Löschen nicht den "
                    "leeren Zustand: " + repr(token_state.inner_text()))
        self.assertNotIn(GITHUB_TOKEN, section.inner_text(),
                         "Der gelöschte Token steht weiterhin im DOM")
        self.assert_clean_page()

    def test_github_connection_check_shows_a_structured_result(self):
        """Vorbedingung: aktive Verknüpfung, gespeicherter Projekt-Token,
        lokale GitHub-Attrappe und lokales Bare-Remote.

        Aktion: ``[data-nv-action="github-connection"]`` klicken.
        Erwartung: ``[data-nv-github-connection][data-nv-ok="true"]`` ist
        sichtbar und nennt ein Ergebnis; es wird kein externes Netz berührt.
        """
        self.activate_github()
        section = self.save_token()
        section.locator("[data-nv-action='github-connection']").first.click()
        result = section.locator("[data-nv-github-connection]")
        result.wait_for(state="visible", timeout=20000)
        self.assertEqual("true", result.get_attribute("data-nv-ok"),
                         "Die Verbindungsprüfung meldet keinen Erfolg: "
                         + repr(result.inner_text()))
        self.assertTrue((result.inner_text() or "").strip(),
                        "Die Verbindungsprüfung zeigt keinen Text")
        self.assert_clean_page()

    def test_github_branch_list_and_checkout_switches_the_worktree(self):
        """Vorbedingung: lokales Repository mit den Branches main und
        feature/arbeit; Verknüpfung aktiv.

        Aktion: Branch-Zeile ``feature/arbeit`` prüfen und auschecken.
        Erwartung: Beide Branch-Zeilen existieren; der Arbeitsbaum steht
        danach auf ``feature/arbeit``.
        """
        self.activate_github()
        section = self.reload_github_section()
        self.assertEqual(
            1, section.locator("[data-nv-github-branch='main']").count(),
            "Die Branch-Zeile main fehlt")
        row = section.locator("[data-nv-github-branch='feature/arbeit']")
        row.wait_for(state="visible", timeout=20000)
        row.locator("[data-nv-action='github-checkout']").first.click()
        self.wait_until(
            lambda: git_out(self.project, "rev-parse", "--abbrev-ref", "HEAD")
            == "feature/arbeit",
            timeout=25,
            message="Der Branch wurde nicht ausgecheckt")
        self.assert_clean_page()

    def test_github_pull_fast_forwards_the_current_branch(self):
        """Vorbedingung: lokaler Branch ``review-pull`` ist hinter origin.

        Aktion: ``[data-nv-action="github-pull"]`` klicken.
        Erwartung: Der Branch wird per ff-only auf den Fernstand gebracht;
        die lokale Spitze entspricht danach der Fernspitze.
        """
        self.activate_github()
        git(self.project, "push", "origin", "--delete", "review-pull",
            check=False)
        git(self.project, "checkout", "-q", "-B", "review-pull", "main")
        probe = self.project / "pull-probe.txt"
        probe.write_text("Fernänderung\n", encoding="utf-8")
        git(self.project, "add", "pull-probe.txt")
        git(self.project, "commit", "-q", "-m", "Review-Fix Pull-Probe")
        git(self.project, "push", "-q", "-u", "origin", "review-pull")
        remote = git_out(self.project, "rev-parse", "HEAD")
        git(self.project, "reset", "--hard", "-q", "HEAD~1")
        self.assertNotEqual(
            remote, git_out(self.project, "rev-parse", "HEAD"),
            "Die Vorbedingung 'hinter origin' wurde nicht hergestellt")

        section = self.reload_github_section()
        section.locator("[data-nv-action='github-pull']").first.click()
        self.wait_until(
            lambda: git_out(self.project, "rev-parse", "HEAD") == remote,
            timeout=25,
            message="Der Pull hat den Branch nicht aufgeholt")
        self.assert_clean_page()

    def test_github_push_uses_source_and_target(self):
        """Vorbedingung: lokaler Branch ``feature/arbeit`` mit einem Commit,
        der auf origin noch fehlt.

        Aktion: Quelle ``feature/arbeit`` und Ziel ``review-target`` über die
        Selects ``select[data-nv-github-push-branch]`` bzw.
        ``select[data-nv-github-push-target]`` eintragen, danach
        ``[data-nv-action="github-push"]`` klicken.
        Erwartung: ``origin/review-target`` zeigt auf die lokale Spitze.
        """
        self.activate_github()
        git(self.project, "push", "origin", "--delete", "review-target",
            check=False)
        git(self.project, "checkout", "-q", "-B", "feature/arbeit", "main")
        probe = self.project / "push-probe.txt"
        probe.write_text("Browser-Push-Probe\n", encoding="utf-8")
        git(self.project, "add", "push-probe.txt")
        git(self.project, "commit", "-q", "-m", "Review-Fix Push-Probe")
        head = git_out(self.project, "rev-parse", "HEAD")
        # F34: Die Ziel-Auswahl bietet die lokalen Branches als Vorschläge an.
        # Der Branch wird hier außerhalb der Oberfläche angelegt; ein ``goto``
        # auf dieselbe Adresse mit anderem Fragment lädt die Seite nicht neu,
        # deshalb wird vor dem Prüfen wirklich neu geladen.
        git(self.project, "branch", "review-target", "main")
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        section = self.page.locator("[data-nv-psection='github']")
        section.wait_for(state="visible", timeout=25000)
        # F34: Quelle und Ziel sind Selects mit Vorschlägen, nicht Freitextfelder.
        section.locator("select[data-nv-github-push-branch]").select_option("feature/arbeit")
        section.locator("select[data-nv-github-push-target]").select_option("review-target")
        section.locator("[data-nv-action='github-push']").first.click()
        self.wait_until(
            lambda: self.remote_tip("review-target") == head,
            timeout=25,
            message="Der Push hat origin/review-target nicht auf die lokale "
                    "Spitze gebracht")
        self.assert_clean_page()

    def test_github_issues_section_offers_only_the_unified_sync(self):
        """Vorbedingung: aktive Verknüpfung, Issues-Sync aktiv.

        Erwartung (GH-47/q6cbba05d8ca9): Die Issues-Sektion bietet genau
        einen Sync-Button; die früheren Aktionen „Issues laden“,
        „Issues importieren“ und der Label-Filter fehlen. Es findet kein
        REST-Aufruf statt, weil nichts geklickt wird.
        """
        self.activate_github()
        self.enable_issue_sync_env()
        section = self.reload_github_section()

        self.assertEqual(
            1, section.locator("[data-nv-action='issues-sync']").count(),
            "Der eine Sync-Button fehlt")
        for selector in ("[data-nv-action='github-issues']",
                         "[data-nv-action='github-import']",
                         "[data-nv-field='github-issue-label']"):
            with self.subTest(removed=selector):
                self.assertEqual(
                    0, section.locator(selector).count(),
                    f"Entfallenes Bedienelement {selector!r} ist noch da")
        self.assert_clean_page()

    def test_issues_sync_pulls_open_issues_into_the_store(self):
        """Vorbedingung: lokale GitHub-Attrappe liefert GH-7 (Label vibe) und
        GH-8 (Label bug); der Ticketspeicher ist leer.

        Aktion: ``[data-nv-action="issues-sync"]`` klicken.
        Erwartung (GH-47/q6cbba05d8ca9): Beide offenen Issues werden als
        GH-Tickets in den Speicher übernommen; GH-8 erhält type=bug.
        """
        self.activate_github()
        self.enable_issue_sync_env()
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": []}) + "\n",
            encoding="utf-8")
        section = self.reload_github_section()
        section.locator("[data-nv-action='issues-sync']").first.click()
        store = self.project / ".vibe" / "tickets.json"

        def records():
            return {item["id"]: item for item in json.loads(
                store.read_text(encoding="utf-8"))["tickets"]}

        self.wait_until(
            lambda: {"GH-7", "GH-8"} <= set(records()),
            timeout=25,
            message="Offene Issues wurden nicht synchronisiert")
        self.assertEqual("task", records()["GH-7"]["type"])
        self.assertEqual("bug", records()["GH-8"]["type"])
        self.assertEqual("Sandbox für Import einschränken",
                         records()["GH-7"]["title"])
        self.assert_clean_page()

    def test_github_merge_request_requires_confirmation_then_attempts(self):
        """Vorbedingung: aktive Verknüpfung, kein Token (der Projekt-Token
        wird bewusst nie an eine fremde API-Basis gesendet).

        Aktion: Merge-Request anfordern, dann im Bestätigungsbereich
        bestätigen.
        Erwartung: Vor der Bestätigung erscheint nur der Bestätigungsbereich
        und es wird kein Pull-Request gesendet. Nach der Bestätigung wird die
        Aktion ausgeführt und ihr Ergebnis in ``[data-nv-github-pr-result]``
        angezeigt (hier die ehrliche Token-Ablehnung); es gibt keinen
        externen Netzaufruf.
        """
        self.activate_github()
        section = self.reload_github_section()
        before = len(self.github.pr_posts)
        section.locator("[data-nv-action='github-pr']").first.click()
        confirm = section.locator("[data-nv-github-pr-confirm]")
        confirm.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            confirm.inner_text(),
            r"(?i)bestät|bestaetig|fortfahren|wirklich|confirm",
            "Der Bestätigungsbereich erklärt die Aktion nicht")
        self.assertEqual(
            before, len(self.github.pr_posts),
            "Ohne Bestätigung wurde bereits ein Pull-Request gesendet")

        section.locator("[data-nv-action='github-pr-confirm']").first.click()
        result = section.locator("[data-nv-github-pr-result]")
        result.wait_for(state="visible", timeout=25000)
        self.assertTrue(
            (result.inner_text() or "").strip(),
            "Der bestätigte Merge-Request zeigt kein Ergebnis")
        self.assertRegex(
            result.inner_text(),
            r"(?i)token|zugang|fehler|nicht|bestät|bestaetig",
            "Das Ergebnis des Merge-Request-Versuchs ist nicht verständlich: "
            + repr(result.inner_text()))
        self.assertEqual(
            before, len(self.github.pr_posts),
            "Der Projekt-Token wurde an eine fremde API-Basis gesendet")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme, Projektdetail (Overview, Arbeit, Beschreibung
# ===========================================================================

import http.client
import json
import os
import re
import shutil
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


LONG_DESCRIPTION = (
    "Diese Beschreibung ist absichtlich sehr lang und besteht aus vielen "
    "Wörtern, damit sie in der schmalen Board-Spalte über die vereinbarten "
    "fünf Zeilen hinausläuft und ohne Aufklappen abgeschnitten werden muss. "
    "Sie wiederholt sich bewusst, damit die Höhe zuverlässig größer ist als "
    "der begrenzte Kasten und der Aufklapp-Knopf einen sichtbaren Unterschied "
    "macht. Noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, "
    "noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, noch ein "
    "Satz, noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, "
    "noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz."
)


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


# GH-48/GH-56: der Ticketspeicher ist .vibe/tickets.json.
TICKETS_f33 = [
    ticket("F1", "Erstes Paket", description=LONG_DESCRIPTION),
    ticket("F2", "Zweites Paket", description="Kurz und knapp."),
    ticket("F3", "Blockiertes Paket", state="blocked",
           description="Wartet auf Freigabe.",
           blocked_reason="externe Freigabe fehlt"),
    ticket("F4", "Erledigtes Paket", state="done", description="Fertig.",
           commit="1234567", test="test_erledigt"),
]

FEEDBACK = [
    ticket("B7", "Absturz beim Start", type="bug",
           description="Fenster bleibt leer."),
    ticket("FB-1", "Wunsch für die Oberfläche", type="feedback",
           description="Bitte größere Schaltflächen."),
]

SPEC = """# SPEC — F33 Test

## Product goal

Ein gefüllter Absatz, der den Zweck beschreibt.

## Audience and use

Noch offen – im Projektassistenten ergänzen.

## Functional scope

Noch offen – im Projektassistenten ergänzen.

## Out of scope

Noch offen – im Projektassistenten ergänzen.

## Target environment

Noch offen – im Projektassistenten ergänzen.

## Quality and acceptance

Noch offen – im Projektassistenten ergänzen.
"""

PROJECT_AGENTS = """Projektregel davor.

<!-- vibe:general-rules -->
Verwaltete Regel 4711.
<!-- /vibe:general-rules -->

Projektregel danach.
"""

GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"


FAKE_OPENCODE_f33 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/tester-modell\\nopencode/helper-modell\\n'
    exit 0
    ;;
esac
exit 2
"""


class F33ProjectBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fixtures für Projektdetail (WP3)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        (cls.agents_dir / "tester.md").write_text(TESTER_AGENT, encoding="utf-8")
        (cls.agents_dir / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        cls.global_agents = cls.home / ".config" / "opencode" / "AGENTS.md"
        cls.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
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
        fake.write_text(FAKE_OPENCODE_f33, encoding="utf-8")
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
        self.write_fixtures()
        for path in (
            self.log_dir / f"{PROJECT}.pause-after",
            self.log_dir / "autonomous.json",
            self.project / ".vibe" / "agents.json",
        ):
            path.unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1000})
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{priority: true, github: true, agentsfile: true})); } "
            "catch (error) {}")
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

    def write_fixtures(self):
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": TICKETS_f33 + FEEDBACK},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (self.project / "SPEC.md").write_text(SPEC, encoding="utf-8")
        (self.project / "AGENTS.md").write_text(PROJECT_AGENTS, encoding="utf-8")
        (self.global_agents).write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n"
            'GITHUB_ENABLED=""\nGITHUB_REPO="owner/name"\n',
            encoding="utf-8")

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
            conn.getresponse().read()
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (url) => {
              const response = await fetch(url, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", self.base + path)

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

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

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def boot(self):
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
        panel = self.page.locator(f"section[data-nv-ppanel='{tab}']")
        panel.wait_for(state="visible", timeout=20000)
        return panel

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def classes(self, locator):
        return (locator.get_attribute("class") or "").split()

    def assert_follows(self, selectors, message):
        """Prüft die DOM-Reihenfolge der Selektoren (jeder folgt dem vorigen)."""
        missing = [selector for selector in selectors
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        ordered = self.page.evaluate(
            """(selectors) => {
              const nodes = selectors.map(s => document.querySelector(s));
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""", selectors)
        self.assertTrue(ordered, message)

    def assert_before(self, first, second, message):
        missing = [selector for selector in (first, second)
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        result = self.page.evaluate(
            """([a, b]) => {
              const A = document.querySelector(a);
              const B = document.querySelector(b);
              if (!A || !B) return null;
              return (A.compareDocumentPosition(B)
                      & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
            }""", [first, second])
        self.assertTrue(result, message)

    def open_work(self):
        self.open_project()
        return self.open_tab("work")

    def records(self):
        doc = json.loads((self.project / ".vibe" / "tickets.json").read_text(
            encoding="utf-8"))
        return {row["id"]: row for row in doc["tickets"]}

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Projektansicht erzeugte JavaScript-Fehler")


class OverviewCardsTest(F33ProjectBrowserTest):
    def test_sessions_card_has_no_guide_link(self):
        """Vorbedingung: Projekt geöffnet, Überblick aktiv.

        Erwartung: Die Sitzungskarte ``[data-nv-sessions]`` enthält keinen
        Link mit der Beschriftung „Leitfaden“ (deutsch/englisch); der
        Leitfaden bleibt über den Tab erreichbar.
        """
        self.open_project()
        sessions = self.page.locator("[data-nv-sessions]")
        sessions.wait_for(state="visible", timeout=20000)
        # Der Vertrag meint den Link *unter* den Sitzungen; er ist ein
        # Geschwister der Sitzungskarte. Deshalb wird der gesamte Überblick
        # geprüft, nicht nur der Inhalt von [data-nv-sessions].
        overview = self.page.locator("section[data-nv-ppanel='overview']")
        links = overview.locator("a")
        texts = [text.strip() for text in links.all_inner_texts()]
        self.assertFalse(
            any(re.search(r"leitfaden|guide", text, re.I) for text in texts),
            "Der Überblick enthält weiterhin einen Leitfaden-Link unter den "
            "Sitzungen: " + repr(texts))
        self.assertEqual(
            1, self.page.locator("[data-nv-ptab='assistant']").count(),
            "Der Leitfaden-Tab fehlt")
        self.assert_clean_page()

    def test_autonomous_row_lives_in_the_overview(self):
        """Vorbedingung: Überblick aktiv, autonomer Modus aus.

        Erwartung: ``div[data-nv-autonomous-row]`` ist im Überblick sichtbar,
        enthält ``input[data-nv-autonomous]`` und eine Erklärung, die das
        automatische Beantworten offener Rückfragen beschreibt.
        """
        self.open_project()
        overview = self.page.locator("section[data-nv-ppanel='overview']")
        row = overview.locator("div[data-nv-autonomous-row]")
        row.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, row.locator("input[data-nv-autonomous]").count(),
            "Die Autonom-Zeile enthält keinen Schalter [data-nv-autonomous]")
        text = row.inner_text() or ""
        self.assertTrue(
            re.search(r"automatisch|automatically|rückfragen|questions", text,
                      re.I),
            "Die Autonom-Zeile erklärt das automatische Beantworten nicht: "
            + repr(text))
        self.assert_clean_page()

    def test_pause_badge_only_shows_for_an_active_pause(self):
        """Vorbedingung: keine Pause angefordert.

        Aktion: ``[data-nv-action="pause"]`` im Held klicken.
        Erwartung: Vorher existiert keine ``span[data-nv-pause-badge]``;
        danach erscheint die Pille mit Klasse ``nv-warn`` und dem Hinweis auf
        die aktive Pause nach dem Paket.
        """
        self.open_project()
        badge = self.page.locator("span[data-nv-pause-badge]")
        self.assertEqual(
            0, badge.count(),
            "Die Pause-Pille ist ohne aktive Pause bereits vorhanden")
        self.page.locator("[data-nv-action='pause']").first.click()
        pause_file = self.log_dir / f"{PROJECT}.pause-after"
        self.wait_until(lambda: pause_file.is_file(), timeout=20,
                        message="Die Pause-Anforderung wurde nicht gespeichert")
        self.wait_until(lambda: badge.count() == 1, timeout=20,
                        message="Die Pause-Pille erscheint nicht")
        self.assertTrue(badge.first.is_visible(),
                        "Die Pause-Pille ist nicht sichtbar")
        self.assertIn(
            "nv-warn", self.classes(badge.first),
            "Die Pause-Pille trägt nicht die Klasse nv-warn")
        self.assertTrue(
            re.search(r"pause", badge.first.inner_text() or "", re.I),
            "Die Pause-Pille nennt die Pause nicht: "
            + repr(badge.first.inner_text()))
        self.assert_clean_page()


class WorkOrderTest(F33ProjectBrowserTest):
    def test_work_tab_follows_the_contract_order(self):
        """Vorbedingung: Feature ``priority`` an, Arbeit geöffnet.

        GH-108: Die Aktionen liegen im Header (``nv-hero``), nicht mehr in
        einer Aktionsleiste der Work-Ansicht. Erwartung: Header-Aktion →
        Filterleiste → Priorisierung → Kanban-Board in genau dieser
        DOM-Reihenfolge.
        """
        panel = self.open_work()
        self.assert_follows(
            [
                "[data-nv-hero] [data-nv-action='new-package']",
                "section[data-nv-ppanel='work'] div[data-nv-filter-bar]",
                "section[data-nv-ppanel='work'] div[data-nv-priority-strip]",
                "section[data-nv-ppanel='work'] div[data-nv-board]",
            ],
            "Die Arbeitsbereiche stehen nicht in der Reihenfolge "
            "Header-Aktion → Filterleiste → Priorisierung → Board")
        self.assertEqual(
            3, panel.locator("[data-nv-col]").count(),
            "GH-56: Das Board muss genau drei Spalten haben")
        self.assertTrue(panel.is_visible(), "Das Arbeits-Panel ist nicht sichtbar")
        self.assert_clean_page()

    def test_work_search_filters_ticket_and_feedback_cards_live(self):
        """Vorbedingung: Pakete F1/F2/F3/F4, Feedback B7/FB-1.

        Aktion: ``input[data-nv-work-search]`` mit „F2“ füllen, dann leeren.
        Erwartung: Nur die Karte F2 bleibt sichtbar, F1 wird ausgeblendet;
        nach dem Leeren sind beide wieder sichtbar.
        """
        self.open_work()
        search = self.page.locator("input[data-nv-work-search]")
        search.wait_for(state="visible", timeout=20000)
        card_f1 = self.page.locator("[data-nv-ticket='F1']")
        card_f2 = self.page.locator("[data-nv-ticket='F2']")
        search.fill("F2")
        self.wait_until(
            lambda: card_f2.is_visible() and not card_f1.is_visible(),
            timeout=15,
            message="Die Live-Suche blendet die nicht passende Karte F1 nicht "
                    "aus oder versteckt F2")
        search.fill("")
        self.wait_until(
            lambda: card_f1.is_visible(), timeout=15,
            message="Nach dem Leeren der Suche erscheint F1 nicht wieder")
        self.assert_clean_page()

    def test_hide_done_toggle_hides_and_shows_done_cards(self):
        """Vorbedingung: F4 ist erledigt.

        Aktion: ``button[data-nv-work-hide-done]`` prüfen, dann klicken.
        Erwartung: Standard ``aria-pressed="true"``, F4 unsichtbar; der Knopf
        nennt „Erledigte anzeigen (1)“. Nach dem Klick ist F4 sichtbar,
        ``aria-pressed="false"`` und der Knopf bietet das Ausblenden an.
        """
        self.open_work()
        toggle = self.page.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte ausblenden“ ist nicht standardmäßig aktiv")
        done = self.page.locator("[data-nv-ticket='F4']")
        self.assertFalse(done.is_visible(),
                         "Die erledigte Karte F4 ist trotz Standardfilter sichtbar")
        label = toggle.inner_text() or ""
        self.assertTrue(
            re.search(r"anzeigen|show", label, re.I) and "1" in label,
            "Der Knopf bietet nicht „Erledigte anzeigen (1)“ an: " + repr(label))
        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "false",
            timeout=15,
            message="Der Klick setzt aria-pressed nicht auf false")
        self.wait_until(lambda: done.is_visible(), timeout=15,
                        message="Die erledigte Karte F4 erscheint nicht")
        self.assertTrue(
            re.search(r"ausblend|hide", toggle.inner_text() or "", re.I),
            "Der Knopf bietet nach dem Einblenden kein Ausblenden an: "
            + repr(toggle.inner_text()))
        self.assert_clean_page()

    def test_long_ticket_description_is_clamped_and_expandable(self):
        """Vorbedingung: F1 hat eine sehr lange Beschreibung.

        GH-56 verlagert sekundäre Informationen in die Detailansicht: Die
        fachliche Absicht (lange Beschreibung überlastet die Kachel nicht,
        bleibt aber vollständig lesbar) wird über Details geprüft. Der alte
        Aufklapp-Knopf auf der Karte ist überholt.
        """
        self.open_work()
        card = self.page.locator("[data-nv-ticket='F1']")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, card.locator("div.nv-ticket-desc").count(),
            "GH-56: Die Kachel zeigt keine Beschreibung mehr")
        self.assertEqual(
            0, card.locator("button[data-nv-ticket-more]").count(),
            "GH-56: Die Kachel hat keinen Aufklapp-Knopf mehr")
        card.locator("button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='F1']").first
        detail.wait_for(state="visible", timeout=20000)
        self.assertIn(LONG_DESCRIPTION, detail.inner_text(),
                      "Die vollständige lange Beschreibung fehlt in der Detailansicht")
        self.assert_clean_page()

    def test_ticket_actions_are_visible_secondary_and_danger_buttons(self):
        """Vorbedingung: Karte F1 in der integrierten Liste.

        Erwartung: Kartenklick öffnet das Kontext-Panel; dort sind
        ``data-nv-action="ticket-edit"`` (nv-secondary) und
        ``data-nv-action="ticket-delete"`` (nv-danger) sichtbare Buttons.
        """
        self.open_work()
        card = self.page.locator("article[data-nv-ticket='F1']")
        card.wait_for(state="visible", timeout=20000)
        card.click()
        detail = self.page.locator(
            "aside[data-nv-context] [data-nv-ticket-detail='F1']")
        detail.wait_for(state="visible", timeout=20000)
        edit = detail.locator("button[data-nv-action='ticket-edit']")
        delete = detail.locator("button[data-nv-action='ticket-delete']")
        self.assertEqual(1, edit.count(), "Der Bearbeiten-Knopf fehlt")
        self.assertEqual(1, delete.count(), "Der Löschen-Knopf fehlt")
        self.assertTrue(edit.is_visible(), "Der Bearbeiten-Knopf ist unsichtbar")
        self.assertTrue(delete.is_visible(), "Der Löschen-Knopf ist unsichtbar")
        self.assertIn("nv-secondary", self.classes(edit),
                      "Der Bearbeiten-Knopf trägt nicht nv-secondary")
        self.assertIn("nv-danger", self.classes(delete),
                      "Der Löschen-Knopf trägt nicht nv-danger")
        self.assert_clean_page()

    def test_feedback_box_starts_collapsed_with_edit_and_delete(self):
        """Vorbedingung: zwei offene Feedback-Einträge.

        Erwartung: Die Feedback-Box (``details[data-nv-feedback-box]``) ist
        nicht mehr vorhanden; die offenen Einträge sind Karten der gemeinsamen
        Liste (``article[data-nv-feedback-item]``) mit ``data-nv-kind`` und
        Badge ``span.nv-kind-badge``; der Kartenklick öffnet das Kontext-Panel
        mit den Aktionen „Bearbeiten“/„Löschen“.
        """
        self.open_work()
        self.assertEqual(
            0, self.page.locator("details[data-nv-feedback-box]").count(),
            "F34: Die Feedback-Box (details[data-nv-feedback-box]) gehört "
            "nicht mehr zum Arbeits-Tab")
        b7 = self.page.locator("article[data-nv-feedback-item='B7']")
        fb1 = self.page.locator("article[data-nv-feedback-item='FB-1']")
        b7.wait_for(state="visible", timeout=20000)
        fb1.wait_for(state="visible", timeout=20000)
        self.assertEqual("bug", b7.get_attribute("data-nv-kind") or "",
                         "Das Feedback B7 trägt nicht data-nv-kind")
        self.assertEqual("feedback", fb1.get_attribute("data-nv-kind") or "",
                         "Das Feedback FB-1 trägt nicht data-nv-kind")
        self.assertEqual(1, b7.locator("span.nv-kind-badge").count(),
                         "Das Feedback B7 trägt kein nv-kind-Badge")
        self.assertEqual(1, fb1.locator("span.nv-kind-badge").count(),
                         "Das Feedback FB-1 trägt kein nv-kind-Badge")
        b7.click()
        detail = self.page.locator(
            "aside[data-nv-context] [data-nv-ticket-detail='B7']")
        detail.wait_for(state="visible", timeout=20000)
        edit = detail.locator("button[data-nv-action='ticket-edit']")
        delete = detail.locator("button[data-nv-action='ticket-delete']")
        self.assertEqual(1, edit.count(), "Der Bearbeiten-Knopf fehlt")
        self.assertEqual(1, delete.count(), "Der Löschen-Knopf fehlt")
        self.assertTrue(edit.is_visible(), "Der Bearbeiten-Knopf ist unsichtbar")
        self.assertTrue(delete.is_visible(), "Der Löschen-Knopf ist unsichtbar")
        self.assertIn("nv-secondary", self.classes(edit),
                      "Der Bearbeiten-Knopf trägt nicht nv-secondary")
        self.assertIn("nv-danger", self.classes(delete),
                      "Der Löschen-Knopf trägt nicht nv-danger")
        self.assert_clean_page()

    def test_feedback_edit_posts_update(self):
        """Vorbedingung: Feedback B7 offen.

        Aktion: Bearbeiten öffnen, Titel ändern, speichern.
        Erwartung: Die Kennung ist schreibgeschützt; der POST geht an
        ``/api/feedback`` mit ``action:"update"`` und ``id:"B7"``; die
        geänderte Beschreibung erscheint anschließend in ``/api/project``.
        """
        self.open_work()
        card = self.page.locator("article[data-nv-feedback-item='B7']")
        card.wait_for(state="visible", timeout=20000)
        card.click()
        detail = self.page.locator(
            "aside[data-nv-context] [data-nv-ticket-detail='B7']")
        detail.wait_for(state="visible", timeout=20000)
        detail.locator("button[data-nv-action='ticket-edit']").click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        self.assertFalse(ident.is_editable(),
                         "Die Kennung ist beim Bearbeiten nicht schreibgeschützt")
        self.assertEqual("B7", ident.input_value(),
                         "Das Bearbeiten-Formular trägt nicht die Kennung B7")
        form.locator("input[data-nv-field='title']").fill(
            "Absturz beim Start (neu)")
        form.locator("button[data-nv-action='ticket-save']").click()
        self.wait_until(
            lambda: any(payload.get("action") == "update"
                        and payload.get("id") == "B7"
                        for payload in self.posts_to("/api/feedback")),
            timeout=20,
            message="Es wurde kein /api/feedback-POST mit action=update "
                    "gesendet: " + repr(self.posts_to("/api/feedback")))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: any(
                entry.get("id") == "B7"
                and "Absturz beim Start (neu)" in str(entry.get("title") or "")
                for entry in data.get("feedback", [])),
            message="Der geänderte Feedback-Titel ist nicht gespeichert")
        self.assert_clean_page()

    def test_feedback_delete_posts_delete(self):
        """Vorbedingung: Feedback B7 offen.

        Aktion: Karte B7 öffnen, Kontext-Panel öffnen, Löschen bestätigen.

        Erwartung: POST ``/api/feedback`` mit ``action:"delete"`` und
        ``id:"B7"``; der Eintrag verschwindet aus ``/api/project``. Zusätzlich
        haben erledigte Einträge ``[data-nv-done-notice]`` und keine
        Bearbeiten-/Löschen-Knöpfe.
        """
        self.open_work()
        card = self.page.locator("article[data-nv-feedback-item='B7']")
        card.wait_for(state="visible", timeout=20000)
        card.click()
        detail = self.page.locator(
            "aside[data-nv-context] [data-nv-ticket-detail='B7']")
        detail.wait_for(state="visible", timeout=20000)
        self.page.on("dialog", lambda dialog: dialog.accept())
        detail.locator("button[data-nv-action='ticket-delete']").click()
        self.wait_until(
            lambda: any(payload.get("action") == "delete"
                        and payload.get("id") == "B7"
                        for payload in self.posts_to("/api/feedback")),
            timeout=20,
            message="Es wurde kein /api/feedback-POST mit action=delete "
                    "gesendet: " + repr(self.posts_to("/api/feedback")))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: all(entry.get("id") != "B7"
                             for entry in data.get("feedback", [])),
            message="Der gelöschte Feedback-Eintrag B7 ist weiterhin vorhanden")
        # F34: Erledigte Einträge behalten den Nachweis und erlauben keine
        # Bearbeiten-/Löschen-Aktionen.
        toggle = self.page.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        toggle.click()
        done_card = self.page.locator("article[data-nv-ticket='F4']")
        done_card.wait_for(state="visible", timeout=20000)
        done_card.click()
        done_detail = self.page.locator(
            "aside[data-nv-context] [data-nv-ticket-detail='F4']")
        done_detail.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, done_detail.locator("[data-nv-done-notice]").count(),
                         "Ein erledigter Eintrag zeigt kein [data-nv-done-notice]")
        self.assertEqual(
            0, done_detail.locator("button[data-nv-action='ticket-edit']").count(),
            "Ein erledigter Eintrag darf nicht bearbeitet werden")
        self.assertEqual(
            0, done_detail.locator("button[data-nv-action='ticket-delete']").count(),
            "Ein erledigter Eintrag darf nicht gelöscht werden")
        self.assert_clean_page()

    def test_form_opens_directly_under_the_action_bar(self):
        """Vorbedingung: Arbeit geöffnet, kein Formular im Ruhezustand.

        GH-56: Das Formular öffnet im Editor (NV.editView) statt inline unter
        der Aktionsleiste. Die frühere DOM-Position relativ zur Ticketliste
        ist ein reines Layout-Detail ohne Fachwert und entfällt. Erhalten
        bleibt die fachliche Absicht: sofort sichtbar, im Viewport, mit den
        wesentlichen Feldern und Aktionen.
        """
        self.open_work()
        self.assertEqual(
            0, self.page.locator("[data-nv-ticket-form]").count(),
            "Im Ruhezustand steht bereits ein Formular im DOM")
        self.page.locator("[data-nv-action='new-package']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        editor = self.page.locator("aside[data-nv-ticket-editor]").first
        editor.wait_for(state="visible", timeout=15000)
        self.assertEqual(1, editor.locator("[data-nv-ticket-form]").count(),
                         "Das Formular liegt nicht im GH-56-Ticket-Editor")
        box = form.bounding_box()
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box["y"], 0,
                                "Das Formular liegt oberhalb des Viewports")
        self.assertLess(
            box["y"], 0.75 * 1000,
            "Das Formular öffnet erst weit unten (Riesenscroll): y="
            + repr(box["y"]))
        for hook in ("input[data-nv-field='title']",
                     "textarea[data-nv-field='description']",
                     "button[data-nv-action='ticket-save']"):
            self.assertGreaterEqual(form.locator(hook).count(), 1,
                                    "Dem Formular fehlt " + hook)
        self.assert_clean_page()

    def test_id_field_has_placeholder_hint_and_suggestion(self):
        """Vorbedingung: Pakete F1–F4 und Bug B7 vorhanden.

        Aktion: „Paket anlegen“ und danach „Bug melden“ öffnen.
        Erwartung: ``input[data-nv-field="id"]`` trägt den Platzhalter
        „leer lassen = automatisch vergeben“, einen Hinweis
        ``small[data-nv-id-hint]`` und ist mit einem noch nicht vergebenen
        Vorschlag vorbelegt; das Feld ist löschbar. Die konkrete Kennung
        hängt vom Speicher ab (alte Markdown-IDs F5/B8 sind überholt).
        """
        self.open_work()
        self.page.locator("[data-nv-action='new-package']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        placeholder = ident.get_attribute("placeholder") or ""
        self.assertTrue(
            re.search(r"leer|empty|automatisch|automatic", placeholder, re.I),
            "Der Platzhalter der Kennung erklärt das Leerlassen nicht: "
            + repr(placeholder))
        hint = form.locator("small[data-nv-id-hint]")
        self.assertEqual(1, hint.count(),
                         "Der Kennungs-Hinweis small[data-nv-id-hint] fehlt")
        self.assertTrue(
            re.search(r"automatisch|automatic|vergeben|assign",
                      hint.inner_text() or "", re.I),
            "Der Kennungs-Hinweis erklärt die automatische Vergabe nicht: "
            + repr(hint.inner_text()))
        suggestion = ident.input_value()
        self.assertTrue(suggestion and suggestion not in self.records(),
                        "Das Paket-Formular ist nicht mit einer unvergebenen "
                        "Kennung vorbelegt: " + repr(suggestion))
        ident.fill("")
        self.assertEqual("", ident.input_value(),
                         "Das Kennungsfeld lässt sich nicht leeren")

        # GH-56: Der Editor muss geschlossen werden, bevor der nächste
        # Aktionsknopf angeklickt wird – sein Scrim fängt sonst den Klick ab.
        self.page.locator("[data-nv-editview-close]").first.click()
        self.page.locator("aside[data-nv-editview]").first.wait_for(
            state="hidden", timeout=15000)
        self.page.locator("[data-nv-action='new-bug']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        bug_suggestion = ident.input_value()
        self.assertTrue(bug_suggestion and bug_suggestion not in self.records(),
                        "Das Bug-Formular ist nicht mit einer unvergebenen "
                        "Kennung vorbelegt: " + repr(bug_suggestion))
        self.assert_clean_page()


class PriorityTest(F33ProjectBrowserTest):
    def prepare_order(self, order):
        status, data = self.post_json(
            "/api/priority", {"name": PROJECT, "action": "set", "order": order})
        self.assertEqual(200, status, repr(data))

    def test_strip_sits_above_the_board_with_badges_and_count(self):
        """Vorbedingung: gespeicherte Reihenfolge F2 vor F1.

        Erwartung: ``div[data-nv-priority-strip]`` steht oberhalb des
        Kanban-Boards; die Karte F2 trägt ``span[data-nv-prio-badge]`` „P1“,
        F1 „P2“; die Leiste meldet „2 priorisiert“.
        """
        self.prepare_order("F2 F1")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.assert_before(
            "section[data-nv-ppanel='work'] div[data-nv-priority-strip]",
            "section[data-nv-ppanel='work'] div[data-nv-board]",
            "Die Priorisierungsleiste steht nicht oberhalb des Boards")
        first = self.page.locator(
            "[data-nv-ticket='F2'] span[data-nv-prio-badge]")
        second = self.page.locator(
            "[data-nv-ticket='F1'] span[data-nv-prio-badge]")
        self.assertEqual(1, first.count(),
                         "Die priorisierte Karte F2 trägt kein P1-Badge")
        self.assertEqual(1, second.count(),
                         "Die priorisierte Karte F1 trägt kein P2-Badge")
        self.assertRegex(first.inner_text() or "", r"P1",
                         "Das erste Badge ist nicht P1")
        self.assertRegex(second.inner_text() or "", r"P2",
                         "Das zweite Badge ist nicht P2")
        text = strip.inner_text() or ""
        self.assertTrue(
            re.search(r"2", text) and re.search(
                r"priorisiert|prioriti[sz]ed|priorit", text, re.I),
            "Die Leiste meldet nicht „2 priorisiert“: " + repr(text))
        self.assert_clean_page()

    def test_drag_and_drop_saves_the_order(self):
        """Vorbedingung: keine gespeicherte Reihenfolge, offene Pakete.

        Aktion: Drag-Griff von F2 auf die Zeile von F1 ziehen.
        Erwartung: ``POST /api/priority`` mit ``action:"set"`` und einer von
        der Ausgangsfolge abweichenden Permutation; die neue Folge ist über
        ``GET /api/priority`` persistiert.
        """
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        handles = strip.locator("button[data-nv-drag-handle]")
        self.assertGreaterEqual(handles.count(), 2,
                                "Die Priorisierungszeilen haben keine "
                                "Drag-Griffe")
        rows = handles.evaluate_all(
            "nodes => nodes.map(n => (n.parentElement.textContent || '').trim())")
        index_f2 = next((i for i, text in enumerate(rows) if "F2" in text), None)
        index_f1 = next((i for i, text in enumerate(rows) if "F1" in text), None)
        self.assertIsNotNone(index_f2, "Keine Zeile für F2: " + repr(rows))
        self.assertIsNotNone(index_f1, "Keine Zeile für F1: " + repr(rows))
        before = [row.split()[0] for row in rows]
        handles.nth(index_f2).drag_to(handles.nth(index_f1))
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        payload = [p for p in self.posts_to("/api/priority")
                   if p.get("action") == "set"][-1]
        order = [part for part in str(payload.get("order") or "").split()
                 if part]
        self.assertIn("F1", order, "Die gespeicherte Folge enthält F1 nicht: "
                                   + repr(order))
        self.assertIn("F2", order, "Die gespeicherte Folge enthält F2 nicht: "
                                   + repr(order))
        self.assertNotEqual(
            before[:len(order)], order,
            "Der Drop hat die Reihenfolge nicht verändert: " + repr(order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht "
                    "persistiert: " + repr(order))
        self.assert_clean_page()

    def test_arrow_buttons_reorder_and_save(self):
        """Vorbedingung: keine gespeicherte Reihenfolge, F1 vor F2.

        Aktion: ↓ am Paket F1 klicken.
        Erwartung: F1 rückt hinter F2; die Änderung wird als
        ``POST /api/priority {action:"set"}`` gespeichert.
        """
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        down = strip.locator("button[data-nv-action='priority-down']")
        self.assertGreaterEqual(down.count(), 1,
                                "Die Priorisierungszeilen haben keine "
                                "↓-Knöpfe")
        target = None
        for index in range(down.count()):
            row_text = down.nth(index).evaluate(
                "node => (node.parentElement.textContent || '')")
            if "F1" in row_text:
                target = down.nth(index)
                break
        self.assertIsNotNone(target, "Keine ↓-Knopf-Zeile für F1 gefunden")
        target.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        and [part for part in str(payload.get("order") or "")
                             .split()][:2] == ["F2", "F1"]
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert die neue Reihenfolge F2 vor F1 "
                    "nicht: " + repr(self.posts_to("/api/priority")))
        self.assert_clean_page()

    def test_reset_clears_the_order(self):
        """Vorbedingung: gespeicherte Reihenfolge F2 vor F1.

        Aktion: ``button[data-nv-priority-reset]`` klicken.
        Erwartung: ``POST /api/priority`` mit ``action:"set"`` und
        ``order:""``; danach tragen die Karten keine Prioritäts-Badges mehr.
        """
        self.prepare_order("F2 F1")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            self.page.locator("span[data-nv-prio-badge]").count(), 1,
            "Vorbedingung: Die priorisierte Reihenfolge zeigt keine Badges")
        reset = strip.locator("button[data-nv-priority-reset]")
        self.assertEqual(1, reset.count(),
                         "Der Zurücksetzen-Knopf fehlt")
        reset.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        and str(payload.get("order") or "") == ""
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Das Zurücksetzen sendet nicht order:\"\": "
                    + repr(self.posts_to("/api/priority")))
        self.wait_until(
            lambda: self.page.locator("span[data-nv-prio-badge]").count() == 0,
            timeout=15,
            message="Die Prioritäts-Badges bleiben nach dem Zurücksetzen stehen")
        self.assert_clean_page()


class DescriptionTest(F33ProjectBrowserTest):
    def open_description(self):
        self.open_project()
        return self.open_tab("assistant")

    def test_tab_is_labelled_description_without_note_field(self):
        """Vorbedingung: Projekt geöffnet.

        Erwartung: Der Tab ``data-nv-ptab="assistant"`` heißt „Beschreibung“
        (englisch „Description“); im Panel gibt es kein ``[data-nv-note]``
        mehr, die Leitfragen bleiben sichtbar.
        """
        panel = self.open_description()
        tab = self.page.locator("[data-nv-ptab='assistant']")
        # F33 WP3: Vertrag/Nutzerentscheidung 3 verlangt sichtbar
        # „Beschreibung“ (en „Description“) — die Prüfung ist case-insensitiv.
        self.assertRegex(
            tab.inner_text() or "",
            re.compile(r"beschreibung|description", re.I),
            "Der Tab heißt nicht „Beschreibung“: " + repr(tab.inner_text()))
        self.assertEqual(
            0, panel.locator("[data-nv-note]").count(),
            "Das Notizfeld [data-nv-note] existiert weiterhin")
        self.assertGreaterEqual(
            panel.locator("textarea[data-nv-answer-field]").count(), 1,
            "Die Leitfragen-Antworten fehlen")
        self.assert_clean_page()

    def test_step_status_reports_filled_and_open_steps(self):
        """Vorbedingung: ``ziel`` ist gefüllt, ``nutzer`` ist offen.

        Erwartung: ``div[data-nv-guide-progress]`` nennt „1 von 8 ausgefüllt“;
        ``nav[data-nv-guide-nav]`` mit je Schritt ``button[data-nv-guide-step]``
        und übersetztem Namen; es existiert keine Status-Pille
        (``span[data-nv-step-status]``) mehr; der Klick auf den Schritt-Knopf
        springt zum Schritt in den Viewport.
        """
        panel = self.open_description()
        progress = panel.locator("div[data-nv-guide-progress]")
        progress.wait_for(state="visible", timeout=20000)
        progress_text = progress.inner_text() or ""
        self.assertRegex(
            progress_text, re.compile(r"^1 of 8 filled"),
            "Die Fortschrittsanzeige nennt nicht „1 von 8 ausgefüllt“: "
            + repr(progress_text))
        nav = panel.locator("nav[data-nv-guide-nav]")
        nav.wait_for(state="visible", timeout=20000)
        steps = nav.locator("button[data-nv-guide-step]")
        self.assertGreaterEqual(
            steps.count(), 2, "Es fehlen Schritt-Knöpfe in nav[data-nv-guide-nav]")
        first = steps.first
        self.assertTrue(
            (first.inner_text() or "").strip(),
            "Der erste Schritt-Knopf hat keinen Namen")
        self.assertRegex(
            first.inner_text() or "", re.compile(r"project goal", re.I),
            "Der erste Schritt-Knopf trägt nicht den übersetzten Namen: "
            + repr(first.inner_text()))
        self.assertEqual(
            0, panel.locator("span[data-nv-step-status]").count(),
            "Es existiert weiterhin die F33-Status-Pille span[data-nv-step-status]")
        first.click()
        self.wait_until(
            lambda: self.page.evaluate(
                """id => {
                  const el = document.querySelector(
                    'section[data-nv-guide-step-id="' + id + '"]');
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.bottom > 0 && rect.top < window.innerHeight;
                }""", "ziel"),
            timeout=20,
            message="Der Klick auf den Schritt-Knopf springt nicht zum Schritt")
        self.assert_clean_page()

    def test_draft_button_is_secondary(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: „Mit Agent entwerfen“ ist ein Knopf der Klasse
        ``nv-secondary`` (klar sichtbar, nicht Ghost).
        """
        panel = self.open_description()
        buttons = panel.locator("button").filter(
            has_text=re.compile(r"entwerfen|draft", re.I))
        self.assertGreaterEqual(buttons.count(), 1,
                                "Der Knopf „Mit Agent entwerfen“ fehlt")
        self.assertIn(
            "nv-secondary", self.classes(buttons.first),
            "„Mit Agent entwerfen“ trägt nicht die Klasse nv-secondary: "
            + repr(buttons.first.get_attribute("class")))
        self.assert_clean_page()

    def test_answer_save_updates_status_without_rerender(self):
        """Vorbedingung: Schritt ``nutzer`` ist offen.

        Aktion: Antwort eintragen, ``button[data-nv-answer-save]`` klicken.
        Erwartung: Kein Voll-Neurender (dieselbe Schritt-DOM bleibt bestehen,
        kein Skelett), Toast, Fortschritt wechselt auf „2 of 8 filled“, die
        Antwort bleibt im Feld, ``/api/guide`` meldet den Schritt als gefüllt.
        """
        panel = self.open_description()
        field = panel.locator("textarea[data-nv-answer-field='nutzer']")
        field.wait_for(state="visible", timeout=20000)
        step = field.locator("xpath=ancestor::section[@data-nv-guide-step-id='nutzer'][1]")
        step.evaluate("node => node.setAttribute('data-test-sentinel', '1')")
        progress = panel.locator("div[data-nv-guide-progress]")
        progress_text_before = progress.inner_text() or ""
        self.assertRegex(
            progress_text_before, re.compile(r"^1 of 8 filled"),
            "Vorbedingung: Der Fortschritt nennt nicht „1 of 8 ausgefüllt“: "
            + repr(progress_text_before))
        field.fill("Antwort-4711: Die Zielgruppe sind Tester.")
        step.locator("button[data-nv-answer-save]").click()
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None,
            timeout=20,
            message="Das Speichern der Antwort bestätigt nicht: "
                    + repr(self.toast_text()))
        self.wait_until(
            lambda: re.search(r"^2 of 8 filled", progress.inner_text() or "",
                              re.I) is not None,
            timeout=20,
            message="Der Fortschritt wechselt nach dem Speichern nicht auf "
                    "„2 of 8 ausgefüllt“: " + repr(progress.inner_text()))
        self.assertEqual(
            "1", step.get_attribute("data-test-sentinel"),
            "Die Ansicht wurde vollständig neu gerendert (Schritt-DOM ersetzt)")
        self.assertEqual(
            "Antwort-4711: Die Zielgruppe sind Tester.", field.input_value(),
            "Die Antwort ging beim Speichern verloren")
        self.assertFalse(
            panel.locator(".nv-skeleton:visible").count() > 0,
            "Beim Speichern erscheint ein Skelett-Platzhalter")
        self.wait_api(
            f"/api/guide?name={PROJECT}",
            lambda data: any(
                entry.get("id") == "nutzer"
                and entry.get("status") == "gefüllt"
                for entry in data.get("steps", [])),
            message="Der Leitfaden-Schritt nutzer ist nicht als gefüllt "
                    "gespeichert")
        self.assert_clean_page()


class SettingsTabTest(F33ProjectBrowserTest):
    def open_settings(self):
        self.open_project()
        return self.open_tab("settings")

    def section(self, name):
        locator = self.page.locator(f"[data-nv-psection='{name}']")
        locator.wait_for(state="visible", timeout=20000)
        return locator

    def test_agents_file_section_has_no_managed_block_editor(self):
        """GH-101: Der verwaltete Block ist aus der UI entfernt. Der
        Bestandsblock bleibt als gewöhnlicher Dateiinhalt sichtbar und wird
        nicht mehr in einem schreibgeschützten Block-Feld ausgewiesen.
        """
        panel = self.open_settings()
        order = panel.evaluate(
            """node => Array.from(node.querySelectorAll(
                 'section[data-nv-psection]'))
                 .map(section => section.getAttribute('data-nv-psection'))""")
        self.assertTrue(order, "Es wurden keine Projekt-Sektionen gefunden")
        self.assertEqual(
            "agentsfile", order[0],
            "AGENTS.md ist nicht die erste Sektion der Einstellungen: "
            + repr(order))
        section = self.section("agentsfile")
        self.assertEqual(
            0, section.locator("pre[data-nv-agents-managed]").count(),
            "Die Sektion zeigt weiterhin den verwalteten Block")
        self.assertNotRegex(
            (section.inner_text() or ""), r"verwalteten block|managed block",
            "Die Sektion nennt weiterhin den verwalteten Block")
        fields = section.locator(
            "textarea[data-nv-agents-text], textarea[data-nv-agents-before],"
            " textarea[data-nv-agents-after]")
        self.assertGreaterEqual(
            fields.count(), 1, "Die AGENTS.md-Sektion hat kein Textfeld")
        combined = "".join(fields.nth(i).input_value() or ""
                           for i in range(fields.count()))
        for needle in ("Projektregel davor", "Verwaltete Regel 4711",
                       "Projektregel danach"):
            with self.subTest(inhalt=needle):
                self.assertIn(needle, combined,
                              "Der Dateiinhalt fehlt im Editor: " + needle)
        self.assertEqual(
            0, section.locator("[data-nv-action='agents-file-create']").count(),
            "Der Anlegen-Knopf agents-file-create existiert bei vorhandener "
            "Datei")
        self.assert_clean_page()

    def test_agents_file_save_posts_text_and_preserves_legacy_block(self):
        """Vorbedingung: AGENTS.md mit Legacy-Block vorhanden.

        Aktion: Dateiinhalt ändern und speichern.
        Erwartung: POST ``/api/agents_file`` mit ``action:"save"``, dem
        geänderten Text und nichtleerem ``digest``; Toast; der vorhandene
        (nicht-kanonische) Bestandsblock bleibt byte-identisch — keine
        Normalisierung und kein Neuschreiben (GH-101/GH-76).
        """
        self.open_settings()
        section = self.section("agentsfile")
        fields = section.locator(
            "textarea[data-nv-agents-text], textarea[data-nv-agents-before]")
        self.assertGreaterEqual(fields.count(), 1, "Kein editbares Textfeld")
        new_text = (
            "Neue Regel davor 4711.\n\n"
            "<!-- vibe:general-rules -->\n"
            "Verwaltete Regel 4711.\n"
            "<!-- /vibe:general-rules -->\n\n"
            "Projektregel danach.\n")
        fields.first.fill(new_text)
        save = section.locator("button[data-nv-action='agents-file-save']")
        self.assertEqual(1, save.count(),
                         "Der Speichern-Knopf agents-file-save fehlt")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "save"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Es wurde kein /api/agents_file-POST mit action=save "
                    "gesendet: " + repr(self.posts_to("/api/agents_file")))
        payload = [p for p in self.posts_to("/api/agents_file")
                   if p.get("action") == "save"][-1]
        posted = str(payload.get("text") or "") + str(payload.get("before") or "")
        self.assertIn("Neue Regel davor 4711", posted,
                      "Der POST enthält den geänderten Text nicht")
        self.assertTrue(str(payload.get("digest") or ""),
                        "Der POST enthält keine Prüfsumme")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None,
            timeout=20,
            message="Das Speichern der AGENTS.md bestätigt nicht")
        self.wait_api(
            f"/api/agents_file?name={PROJECT}",
            lambda data: "Neue Regel davor 4711"
            in str(data.get("text") or data.get("before") or ""),
            message="Der geänderte Text ist nicht gespeichert")
        text = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        # GH-101/GH-76: Der vorhandene Bestandsblock bleibt byte-identisch;
        # der frühere deutsche Regeltext wird nicht mehr eingesetzt.
        self.assertIn("<!-- vibe:general-rules -->", text,
                      "Der Bestandsblock-Marker fehlt nach dem Speichern")
        self.assertIn("Verwaltete Regel 4711", text,
                      "Der Bestandsblock wurde verändert")
        self.assertNotIn("## Projektordner sauber halten", text,
                         "Der frühere deutsche Regeltext wurde eingesetzt")
        self.assert_clean_page()

    def test_global_agents_hint_is_readonly(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: Im Projekteinstellungen-Tab gibt es die globale AGENTS.md
        nicht doppelt. Die globale AGENTS.md ist über
        ``nav[data-nv-navs] [data-nv-nav='settings']`` →
        ``section[data-nv-ssection='global-agents']`` erreichbar. Das alte
        ``details[data-nv-global-agents]`` mit eingebettetem Textarea wurde
        durch den Bearbeiten-Knopf ``[data-nv-action='global-agents-edit']``
        und einen Editor (``textarea[data-nv-agents-text]``) ersetzt; die
        fachliche Absicht — Hinweis, Erreichbarkeit und Fixture-Inhalt —
        bleibt erhalten.
        """
        panel = self.open_settings()
        self.assertEqual(
            0, panel.locator("details[data-nv-global-agents-hint]").count(),
            "Die globale AGENTS.md-Hinweis-Box existiert im "
            "Projekteinstellungen-Tab nicht mehr")
        self.assertEqual(
            0, panel.locator("details[data-nv-global-agents]").count(),
            "Die globale AGENTS.md-Details existieren nicht im "
            "Projekteinstellungen-Tab")
        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        main = self.page.locator("main#nv-main[data-nv-view='settings']")
        main.wait_for(state="visible", timeout=20000)
        section = self.page.locator("section[data-nv-ssection='global-agents']")
        section.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, section.locator("small[data-nv-global-agents-hint]").count(),
            "Der Hinweis small[data-nv-global-agents-hint] fehlt")
        edit = section.locator("button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        editor = self.page.locator("aside[data-nv-editview]").first
        editor.wait_for(state="visible", timeout=20000)
        textarea = editor.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        rows = textarea.evaluate(
            "node => parseInt(node.getAttribute('rows') || '0', 10) || node.rows")
        self.assertGreaterEqual(
            rows, 16, "textarea[data-nv-agents-text] hat weniger als 16 rows")
        self.assertIn("GLOBALE-REGEL-4711", textarea.input_value(),
                      "Der Inhalt der globalen AGENTS.md wird nicht angezeigt")
        self.assert_clean_page()

    def test_agents_file_backup_and_restore_controls(self):
        """Vorbedingung: AGENTS.md-Sektion sichtbar.

        Erwartung: ``agents-file-backup`` und ``agents-file-restore``
        existieren; ein Klick auf Wiederherstellen zeigt zuerst die
        Inline-Bestätigung ``div[data-nv-agents-restore-confirm]``, ohne
        sofort zu schreiben.
        """
        self.open_settings()
        section = self.section("agentsfile")
        backup = section.locator("button[data-nv-action='agents-file-backup']")
        restore = section.locator("button[data-nv-action='agents-file-restore']")
        self.assertEqual(1, backup.count(), "Der Sicherungs-Knopf fehlt")
        self.assertEqual(1, restore.count(), "Der Wiederherstellen-Knopf fehlt")
        confirm = section.locator("div[data-nv-agents-restore-confirm]")
        self.assertEqual(1, confirm.count(),
                         "Die Inline-Bestätigung der Wiederherstellung fehlt")
        self.assertFalse(confirm.is_visible(),
                         "Die Bestätigung ist ohne Klick bereits sichtbar")
        restore.click()
        confirm.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            0, len([payload for payload in self.posts_to("/api/agents_file")
                    if payload.get("action") == "restore"]),
            "Die Wiederherstellung wurde ohne Bestätigung ausgeführt")
        self.assert_clean_page()

    def test_github_explains_branches_and_puts_mr_above_issues(self):
        """Vorbedingung: Feature ``github`` an, Issues-Sync aktiv.

        Erwartung: ``small[data-nv-github-help-source]`` und
        ``small[data-nv-github-help-target]`` erklären Quell-/Ziel-Branch;
        der Merge-Request-Block steht über dem einen Issue-Sync-Block
        (GH-47/q6cbba05d8ca9: ``github-issues`` ist entfallen).
        """
        env_path = self.project / ".vibe" / "project.env"
        env_path.write_text(
            env_path.read_text(encoding="utf-8")
            + 'GITHUB_ISSUES_ENABLED="1"\n',
            encoding="utf-8")
        self.open_settings()
        section = self.section("github")
        source = section.locator("small[data-nv-github-help-source]")
        target = section.locator("small[data-nv-github-help-target]")
        self.assertEqual(1, source.count(),
                         "Die Erklärung des Quell-Branches fehlt")
        self.assertEqual(1, target.count(),
                         "Die Erklärung des Ziel-Branches fehlt")
        self.assertTrue((source.inner_text() or "").strip(),
                        "Die Erklärung des Quell-Branches ist leer")
        self.assertTrue((target.inner_text() or "").strip(),
                        "Die Erklärung des Ziel-Branches ist leer")
        self.assert_before(
            "[data-nv-psection='github'] [data-nv-action='github-pr']",
            "[data-nv-psection='github'] [data-nv-action='issues-sync']",
            "Der Merge-Request-Block steht nicht über dem Issue-Block")
        self.assert_clean_page()

    def test_auto_merge_is_a_switch_row(self):
        """Vorbedingung: Feature ``github`` an.

        Erwartung: ``label.nv-switch-row[data-nv-automerge-switch]`` enthält
        ``input[data-nv-field="github-auto-merge"]`` und einen beschreibenden
        Text zum automatischen Mergen.
        """
        self.open_settings()
        section = self.section("github")
        label = section.locator("label.nv-switch-row[data-nv-automerge-switch]")
        label.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, label.locator("input[data-nv-field='github-auto-merge']").count(),
            "Der Auto-Merge-Schalter liegt nicht in der Schalterzeile")
        self.assertRegex(
            label.inner_text() or "", r"merge",
            "Die Schalterzeile erklärt das automatische Mergen nicht: "
            + repr(label.inner_text()))
        self.assert_clean_page()

    def test_team_model_is_a_combobox(self):
        """Vorbedingung: Team-Sektion mit Agent ``tester``.

        Erwartung: Die Modellwahl ist keine ``select``-Liste mehr, sondern
        eine Combobox; der Wert-Hook ``data-nv-agent-model`` liegt am
        Combobox-Container.
        """
        self.open_settings()
        self.section("team")
        row = self.page.locator("[data-nv-team-agent='tester']")
        row.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, row.locator("select[data-nv-agent-model]").count(),
            "Die Modellwahl ist weiterhin eine select-Liste")
        container = row.locator("[data-nv-agent-model]")
        self.assertEqual(1, container.count(),
                         "Der Wert-Hook data-nv-agent-model fehlt am "
                         "Combobox-Container")
        is_combobox = container.evaluate(
            """node => node.hasAttribute('data-nv-combobox')
                 || !!node.querySelector("input[data-nv-combobox-input]")""")
        self.assertTrue(is_combobox,
                        "data-nv-agent-model liegt nicht an einer Combobox")
        self.assert_clean_page()

    def test_there_is_no_own_pause_section(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: Die eigene Einstellungssektion „Pause nach Paket“ entfällt
        vollständig (``[data-nv-psection="pause"]`` existiert nicht); der
        Status steht im Überblick.
        """
        panel = self.open_settings()
        self.assertEqual(
            0, panel.locator("[data-nv-psection='pause']").count(),
            "Die eigene Pause-Sektion existiert weiterhin")
        self.assertNotRegex(
            panel.inner_text() or "", r"Pause nach Paket",
            "Die Einstellungen nennen weiterhin die Pause-Sektion")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme, Projektdetail (Überblick, Arbeit, Beschreibung
# ===========================================================================

import http.client
import json
import os
import re
import shutil
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


# --- F34-Fixture: TICKETS.md ------------------------------------------------
# Zustände gemäß Backend/Vertrag: offen, erledigt, BLOCKIERT, WARTET AUF
# MERGE, Draft, In Progress. FB-1 ist erledigt (echter Nachweis auf einem
# echten Git-Commit); B7 ist offen (Art: Bug).


# GH-48/GH-56: der Ticketspeicher ist .vibe/tickets.json.
TICKETS_f34 = [
    ticket("F1", "Erstes Paket",
           description="Erstes Paket eingegeben, wartet auf Umsetzung."),
    ticket("F2", "Zweites Paket", state="done",
           description="Projekt als erledigt markiert."),
    ticket("F3", "Blockiertes Paket", state="blocked",
           blocked_reason="externe Freigabe fehlt"),
    ticket("F4", "Wartet auf Merge", state="waiting-merge",
           waiting_note="Wartet auf Merge-Freigabe."),
    ticket("F5", "Entwurf erstellt", state="draft"),
    ticket("F6", "In Arbeit", state="in-progress"),
    ticket("F7", "Dritte Überprüfung",
           description="Noch ein offenes Paket, um die Listenhöhe zu erhöhen."),
    ticket("F8", "Vierte Überprüfung",
           description="Ein weiteres offenes Paket, um die Listenhöhe zu erhöhen."),
]


def feedback_fixture(proof_hash):
    return [
        ticket("B7", "Wunsch für die Oberfläche", type="bug",
               description="Bitte größere Schaltflächen."),
        ticket("FB-1", "Absturz beim Start", type="feedback", state="done",
               description="Fenster bleibt leer.", commit=proof_hash,
               test="test_f34"),
    ]


SPEC_f34 = """# SPEC — F34 Test

## Product goal

Das Projekttest-Projekt der F34-Vertragsprüfung.

## Audience and use

Entwicklerinnen und Entwickler im Dashboard.

## Functional scope

Überblick, Arbeit, Beschreibung, Einstellungen.

## Out of scope

Keine Auswertungen im Projektdetail.

## Target environment

Dashboard auf Loopback.

## Quality and acceptance

Browser-Tests gegen das echte Dashboard.
"""


PROJECT_ENV = (
    "TYPE=generic\n"
    "GITHUB_ENABLED=1\n"
    'GITHUB_REPO="owner/name"\n'
    "GITHUB_BRANCH=main\n"
)


FAKE_OPENCODE_f34 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/tester-modell\\nopencode/helper-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

# --- F34-Fixture: sessions.json (drei Session-Zeilen) -----------------------
# package_catalog (Paketkennung -> Kurztitel aus FEEDBACK.md / TICKETS.md):
# F1 -> "Erstes Paket", F7 -> "Dritte Überprüfung" — die Werte werden per
# Fixture aus TICKETS.md/FEEDBACK.md abgeleitet.
# Reihenfolge: session_overview liefert jüngste zuerst — erste Zeile also
# den jüngsten Eintrag.
EXPECTED_TITLES = {"F1": "Erstes Paket", "F7": "Dritte Überprüfung"}
SESSION_ROWS = [
    # (session, agent, package_id, relativ-Zeit-Sekunden, state)
    ("ses_f34cc1b2c3d4e5f6c3", "tester", "F7", 5, "stopped"),
    ("ses_f34bb1b2c3d4e5f6b2", "helper", "F1", 60, "running"),
    ("ses_f34aa1b2c3d4e5f6a1", "tester", "F1", 120, "running"),
]


def git_f34(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=True, timeout=60, env=env)


class F34ProjectBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fixtures für Projektdetail (F34 WP5)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        (cls.agents_dir / "tester.md").write_text(TESTER_AGENT, encoding="utf-8")
        (cls.agents_dir / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        cls.global_agents = cls.home / ".config" / "opencode" / "AGENTS.md"
        cls.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
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
        fake.write_text(FAKE_OPENCODE_f34, encoding="utf-8")
        fake.chmod(0o755)

        # Echtes Git-Repository mit einem Commit: Beweis für das erledigte
        # Feedback FB-1 (Commit-Hash + ``Test:``-Zeile im Block).
        git_f34(cls.project, "init", "-q", "-b", "main")
        git_f34(cls.project, "commit", "--allow-empty", "-q", "-m", "F34 Test Commit")
        cls.proof_hash = git_f34(cls.project, "rev-parse", "HEAD").stdout.strip()

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
        self.write_fixtures()
        (self.log_dir / "autonomous.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1000})
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{priority: true, sandbox: true, writeaccess: true, "
            "agentsfile: true, github: true})); } catch (error) {}")
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

    def write_fixtures(self):
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1,
                        "tickets": TICKETS_f34 + feedback_fixture(self.proof_hash)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (self.project / "SPEC.md").write_text(SPEC_f34, encoding="utf-8")
        (self.project / "AGENTS.md").write_text(PROJECT_AGENTS, encoding="utf-8")
        (self.global_agents).write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8")
        now = int(time.time())
        sessions = {
            "limit": 5,
            "sessions": [{
                "session": session,
                "project": os.path.realpath(str(self.project)),
                "name": PROJECT,
                "run_id": "",
                "agent": agent,
                "harness": "",
                "worktree_path": "",
                "package_id": package_id,
                "branch": "main",
                "first_seen": now - age - 10,
                "last_seen": now - age,
                "state": state,
            } for session, agent, package_id, age, state in SESSION_ROWS],
            "project_limits": {},
        }
        (self.log_dir / "sessions.json").write_text(
            json.dumps(sessions, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

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
            conn.getresponse().read()
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (url) => {
              const response = await fetch(url, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", self.base + path)

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

    def wait_api(self, path, predicate, timeout=20, message=None):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = self.api_json(path)
            except Exception:  # noqa: BLE001 - Poll darf kurze Fehler sehen
                last = None
            if last is not None and predicate(last):
                return last
            self.page.wait_for_timeout(150)
        self.fail((message or "API-Bedingung nicht erfüllt") + " — zuletzt: "
                  + repr(last))

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def boot(self):
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
        panel = self.page.locator(f"section[data-nv-ppanel='{tab}']")
        panel.wait_for(state="visible", timeout=20000)
        return panel

    def open_overview(self):
        return self.open_project()

    def open_work(self):
        self.open_project()
        panel = self.open_tab("work")
        self.page.locator("div[data-nv-board]").first.wait_for(
            state="visible", timeout=20000)
        self.page.locator("input[data-nv-work-search]").wait_for(
            state="visible", timeout=20000)
        # GH-67: die separate Priorisierungsansicht gibt es nur mobil;
        # auf diesem Desktop-Viewport liegt kein div[data-nv-priority-strip]
        # im DOM. Strip-Tests nutzen open_work_mobile().
        self.install_render_counter()
        return panel

    def open_work_mobile(self):
        """GH-67: Priorisierung ist an den Breakpoint <=768px gebunden.

        Der Desktop-Helfer wartet auf das Board; mobil gibt es stattdessen
        die Liste plus Priorisierungsstrip. Dieser Helfer bildet genau diesen
        Pfad ab und wartet bewusst nicht auf div[data-nv-board].
        """
        self.page.set_viewport_size({"width": 600, "height": 800})
        self.open_project()
        panel = self.open_tab("work")
        self.page.locator("input[data-nv-work-search]").wait_for(
            state="visible", timeout=20000)
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        self.install_render_counter()
        return panel

    def records(self):
        doc = json.loads((self.project / ".vibe" / "tickets.json").read_text(
            encoding="utf-8"))
        return {row["id"]: row for row in doc["tickets"]}

    def install_render_counter(self):
        """Umhüllt ``NV.render`` mit einem Zähler des TESTGERÜSTS.

        Das Produkt hat keinen eigenen Render-Zähler; dieser Helfer legt sich
        nach dem Laden vor ``NV.render`` (``bin/web/nova-core.js``) und erhöht
        ``window.__nvRenderCount`` bei jedem Aufruf. Ein unveränderter Zähler
        belegt damit, dass eine Prioritätsaktion keinen Voll-Neurender
        ausgelöst hat. Der Helfer ist idempotent; nach einem ``page.goto``
        muss er erneut laufen.
        """
        state = self.page.evaluate(
            """() => {
              if (window.__nvRenderCounterInstalled === true) {
                return {ok: true, already: true};
              }
              if (typeof NV === 'undefined'
                  || typeof NV.render !== 'function') {
                return {ok: false, reason: 'NV.render fehlt'};
              }
              var original = NV.render;
              window.__nvRenderCount = 0;
              window.__nvRenderCountOriginal = original;
              NV.render = function () {
                window.__nvRenderCount += 1;
                return original.apply(this, arguments);
              };
              window.__nvRenderCounterInstalled = true;
              return {
                ok: true,
                already: false,
                wrapped: NV.render !== window.__nvRenderCountOriginal,
                countsInBody: String(NV.render)
                  .indexOf('__nvRenderCount') !== -1
              };
            }""")
        self.assertTrue(
            state.get("ok"),
            "Der Render-Zähler konnte nicht installiert werden: %r"
            % (state.get("reason"),))
        if not state.get("already"):
            self.assertTrue(
                state.get("wrapped") and state.get("countsInBody"),
                "Die Umhüllung von NV.render zählt nicht wirklich: %r"
                % (state,))

    def nv_render_count(self):
        """Zählerstand des testseitig umhüllten ``NV.render``.

        Scheitert, wenn der Zähler fehlt — ein stiller Rückfall auf 0 würde
        eine Zusicherung vortäuschen, die nichts prüft.
        """
        state = self.page.evaluate(
            """() => ({
              installed: window.__nvRenderCounterInstalled === true,
              count: typeof window.__nvRenderCount === 'number'
                ? window.__nvRenderCount : null
            })""")
        self.assertTrue(
            state.get("installed"),
            "Der Render-Zähler ist nicht installiert; nv_render_count() "
            "kann keinen Voll-Neurender ausschließen")
        self.assertIsNotNone(
            state.get("count"),
            "Der Render-Zähler hat keinen numerischen Stand")
        return state["count"]

    def open_assistant(self):
        self.open_project()
        return self.open_tab("assistant")

    def open_settings(self):
        self.open_project()
        return self.open_tab("settings")

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def classes(self, locator):
        return (locator.get_attribute("class") or "").split()

    def assert_follows(self, selectors, message):
        """Prüft die DOM-Reihenfolge der Selektoren (jeder folgt dem vorigen)."""
        missing = [selector for selector in selectors
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        ordered = self.page.evaluate(
            """(selectors) => {
              const nodes = selectors.map(s => document.querySelector(s));
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""", selectors)
        self.assertTrue(ordered, message)

    def assert_before(self, first, second, message):
        missing = [selector for selector in (first, second)
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        result = self.page.evaluate(
            """([a, b]) => {
              const A = document.querySelector(a);
              const B = document.querySelector(b);
              if (!A || !B) return null;
              return (A.compareDocumentPosition(B)
                      & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
            }""", [first, second])
        self.assertTrue(result, message)

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Projektansicht erzeugte JavaScript-Fehler")

    # ---------- F34-Vertrags-Hilfen ----------

    def card_selector(self, ident):
        return (f"div[data-nv-board] [data-nv-ticket='{ident}'], "
                f"div[data-nv-board] [data-nv-feedback-item='{ident}']")

    def visible_card_ids(self):
        ids = []
        for card in self.page.locator(
                "div[data-nv-board] [data-nv-ticket], "
                "div[data-nv-board] [data-nv-feedback-item]").all():
            if card.is_visible():
                ident = (card.get_attribute("data-nv-ticket")
                         or card.get_attribute("data-nv-feedback-item") or "")
                ids.append(ident)
        return ids

    def strip_ids(self):
        return self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id]").evaluate_all(
                "nodes => nodes.map("
                "node => node.getAttribute('data-nv-priority-id'))")

    def expected_effective_ids(self):
        """Effektive Prioritätsreihenfolge aus ``GET /api/priority``.

        GH-56: ``nvpPriorityStrip`` zeigt ausschließlich Ready-Tickets
        (Rohzustand ``open``, Anzeige ``offen``). Draft, Running, Blocked,
        Waiting-Merge und Done gehören nicht in die Priorisierung.
        """
        data = self.api_json(f"/api/priority?name={PROJECT}")
        tickets, feedback = self.project_entries()
        open_ids = {str(entry.get("id") or "") for entry in tickets + feedback
                    if str(entry.get("state") or "") in ("offen", "open")}
        ids, seen = [], set()
        for entry in list(data.get("order") or []) + \
                list(data.get("standard") or []):
            entry_id = str(entry.get("id") or "")
            if not entry_id or entry_id in seen or entry_id not in open_ids:
                continue
            if str(entry.get("status") or "") == "erledigt":
                continue
            ids.append(entry_id)
            seen.add(entry_id)
        return ids

    def set_priority(self, order):
        status, data = self.post_json(
            "/api/priority", {"name": PROJECT, "action": "set", "order": order})
        self.assertEqual(200, status, repr(data))
        self.assertTrue(bool(data.get("ok")), repr(data))

    def project_entries(self):
        data = self.api_json(f"/api/project?name={PROJECT}")
        return data.get("tickets") or [], data.get("feedback") or []

    def sessions_rows(self):
        data = self.api_json(f"/api/sessions?name={PROJECT}")
        return data.get("sessions") or []

    def state_label(self, state):
        """Zustands-Pille der Oberfläche (englischer Modus, siehe i18n.js).

        GH-67: ``offen``/``open`` heißt in der Oberfläche nun ``Ready``
        (deutsch ``Bereit``); interne Kennungen bleiben unverändert.
        """
        return {
            "offen": "Ready",
            "WARTET AUF MERGE": "Waiting for merge",
            "BLOCKIERT": "Blocked",
            "In Progress": "In Progress",
            "Draft": "Draft",
            "ohne Nachweis": "Ohne Nachweis",
            "erledigt": "Done",
        }.get(state, "Open")


class OverviewTest(F34ProjectBrowserTest):
    def test_autonomous_card_is_first_in_overview(self):
        """Vorbedingung: Überblick geöffnet, kein Status gesetzt.

        Erwartung: ``section[data-nv-autonomous-card]`` ist das erste Element
        der Übersicht (y-Position vor den Kacheln), enthält
        ``input[data-nv-autonomous]``, eine Überschrift, die Erklärung
        („Im autonomen Modus sind Rückfragen nicht möglich; der Agent
        entscheidet offene Punkte selbst“) und eine Zustands-Pille
        ``span[data-nv-autonomous-state]`` mit einem Wert.
        """
        self.open_overview()
        panel = self.page.locator("section[data-nv-ppanel='overview']")
        card = panel.locator("section[data-nv-autonomous-card]")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, card.count(), "Die autonome Karte fehlt")
        tiles = panel.locator("div[data-nv-tile]")
        tiles.first.wait_for(state="visible", timeout=20000)
        card_box = card.bounding_box()
        tile_box = tiles.first.bounding_box()
        self.assertIsNotNone(card_box)
        self.assertIsNotNone(tile_box)
        self.assertLess(card_box["y"], tile_box["y"],
                        "Die autonome Karte steht nicht oben (vor den Kacheln)")
        self.assertEqual(1, card.locator("input[data-nv-autonomous]").count(),
                         "Der Schalter [data-nv-autonomous] fehlt")
        self.assertGreaterEqual(card.locator("h3").count(), 1,
                                "Der Kachel trägt keine Überschrift")
        text = card.inner_text() or ""
        self.assertRegex(
            text, re.compile(r"beantwortet|automatisch|rückfragen|questions",
                             re.I),
            "Die Karte trägt keine Erklärung (Beantwortung offener Rückfragen): "
            + repr(text))
        state = card.locator("span[data-nv-autonomous-state]")
        self.assertEqual(1, state.count(), "Die Zustands-Pille fehlt")
        self.assertTrue((state.inner_text() or "").strip(),
                        "Die Zustands-Pille ist leer")
        self.assert_clean_page()

    def test_tiles_match_the_contract_set(self):
        """Vorbedingung: Pakete in den Zuständen offen, erledigt, BLOCKIERT,
        WARTET AUF MERGE, Draft, In Progress.

        Erwartung: genau die sechs Kacheln ``div[data-nv-tile]`` mit
        ``data-nv-tile`` ∈ {open, progress, blocked, waiting, done, draft};
        die Entwurf-Kachel trägt eine ``title``-Erklärung; keine Kachel
        nennt „Feedback“ oder „ohne Nachweis“.
        """
        panel = self.open_overview()
        tiles = panel.locator("div[data-nv-tile]")
        tiles.first.wait_for(state="visible", timeout=20000)
        values = sorted(tiles.evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-nv-tile'))"))
        self.assertEqual(
            ["blocked", "done", "draft", "open", "progress", "waiting"],
            values, "Die Kacheln (data-nv-tile) sind nicht genau die sechs "
            "offenen/erledigten/Draft-Kacheln: " + repr(values))
        draft = panel.locator("div[data-nv-tile][data-nv-tile='draft']")
        self.assertTrue(
            (draft.first.get_attribute("title") or "").strip(),
            "Die Entwurf-Kachel trägt keine title-Erklärung")
        for index in range(tiles.count()):
            text = (tiles.nth(index).inner_text() or "").lower()
            self.assertNotRegex(
                text, r"feedback|ohne nachweis",
                "Eine Kachel nennt Feedback oder „ohne Nachweis“: " + repr(text))
        self.assert_clean_page()

    def test_state_card_names_the_last_package(self):
        """Vorbedingung: Pakete vorhanden; B7 ist das letzte Paket der
        effektiven Reihenfolge (ohne manuelle Priorisierung).

        Erwartung: ``section[data-nv-state-card]`` nennt Kennung + Titel +
        Zustand des letzten Arbeitspakets („B7“, „Wunsch für die Oberfläche“,
        GH-67: „Ready“ statt „Offen“); danach „Letzter Commit“ und „Prüfung“.
        """
        panel = self.open_overview()
        tickets, feedback = self.project_entries()
        expected_last = self.expected_effective_ids()[-1]
        self.assertEqual("B7", expected_last,
                         "Vorbedingung: das letzte Paket der effektiven "
                         "Reihenfolge ist B7, erhalten: " + repr(expected_last))
        match = next(
            (entry for entry in tickets + feedback
             if str(entry.get("id") or "") == expected_last), None)
        self.assertIsNotNone(match, "Vorbedingung: B7 existiert")
        state_card = panel.locator("section[data-nv-state-card]")
        state_card.wait_for(state="visible", timeout=20000)
        card_text = state_card.inner_text() or ""
        self.assertIn(expected_last, card_text,
                      "Der Kennung des letzten Pakets fehlt in der „Zustand“-Karte: "
                      + repr(card_text))
        self.assertIn(str(match.get("title") or ""), card_text,
                      "Der Titel des letzten Pakets fehlt in der „Zustand“-Karte")
        self.assertIn(self.state_label(str(match.get("state") or "")), card_text,
                      "Der Zustand des letzten Pakets fehlt in der „Zustand“-Karte")
        # Vertragsbegriffe (englischer Modus): Überschrift, letzter Commit,
        # Prüfstatus — alle in der „Zustand“-Karte.
        for fragment in ("State", "Last work package", "Last commit",
                         "Verification"):
            self.assertIn(fragment, card_text,
                          f"Der Fragment {fragment!r} fehlt in der „Zustand“-Karte")
        self.assert_clean_page()

    def test_sessions_rows_and_resume_column(self):
        """Vorbedingung: ``sessions.json`` mit drei Session-Zeilen
        (package_id F1/F1/F7, Agent tester/helper/tester).

        Erwartung: ``div[data-nv-sessions]`` nennt die Paketkennungen und
        Titel (GH-99: als Gruppenüberschriften, nicht zwingend pro Zeile).
        Jede Sitzung hat eine Zeile mit Agent, Zustand und relativer Zeit;
        die technische ID steht nur in ``code.nv-session-id`` (gekürzt,
        ``title`` voll); ``button[data-nv-action="session-resume"]`` rechts
        in einer Spalte mit gleicher x-Position. Die Zeilen werden über die
        volle Session-ID zugeordnet, damit die Gruppier-Reihenfolge irrelevant
        ist.
        """
        self.open_overview()
        rows = self.page.locator("div[data-nv-sessions] div.nv-session-row")
        rows.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(rows.count(), 3,
                                "Vorbedingung: drei Session-Zeilen, "
                                "erhalten: " + repr(rows.count()))
        container_text = self.page.locator(
            "div[data-nv-sessions]").inner_text() or ""
        for package_id, title in EXPECTED_TITLES.items():
            self.assertIn(
                package_id, container_text,
                f"Paketkennung {package_id} fehlt in der Sitzungskarte: "
                + repr(container_text))
            self.assertIn(
                title, container_text,
                f"Pakettitel {title} fehlt in der Sitzungskarte: "
                + repr(container_text))
        api_rows = {
            str(row.get("session") or ""): row
            for row in self.sessions_rows()}
        by_session = {}
        for row in rows.all():
            code = row.locator("code.nv-session-id")
            if code.count():
                by_session[code.first.get_attribute("title")] = row
        for session, agent, package_id, age, state in SESSION_ROWS:
            row = by_session.get(session)
            self.assertIsNotNone(row, f"Zeile für {session} fehlt")
            text = row.inner_text() or ""
            self.assertIn(agent, text,
                          f"Agent {agent} fehlt für {session}: " + repr(text))
            self.assertRegex(
                text, re.compile(r"(\d+\s*(min|stunde)|gerade eben|just now)",
                                 re.I),
                f"Session {session}: keine relative Zeit angezeigt: "
                + repr(text))
            state_label = api_rows.get(session, {}).get("state_label") or ""
            if state_label:
                self.assertIn(state_label, text,
                              f"Zustand {state_label} fehlt für {session}: "
                              + repr(text))
            self.assertNotIn(
                session, text,
                f"Session {session}: die technische Session-ID steht im "
                "Zeilentext: " + repr(text))
            code = row.locator("code.nv-session-id")
            self.assertEqual(1, code.count(),
                             f"Session {session}: code.nv-session-id fehlt")
            self.assertEqual(
                session, code.first.get_attribute("title"),
                f"Session {session}: der title der Session-ID ist nicht voll")
            self.assertLess(
                len(code.first.inner_text() or ""), len(session),
                f"Session {session}: die technische ID ist nicht gekürzt")
            resume = row.locator("button[data-nv-action='session-resume']")
            self.assertEqual(
                1, resume.count(),
                f"Session {session}: button[data-nv-action=session-resume] fehlt")
            self.assertRegex(
                resume.first.inner_text() or "",
                re.compile(r"forsetz|resume|continue", re.I),
                f"Session {session}: Der Fortsetzen-Knopf hat kein Label")
        resumes = self.page.locator("button[data-nv-action='session-resume']")
        xs = [resume.bounding_box()["x"] for resume in resumes.all()]
        self.assertTrue(
            xs and max(xs) - min(xs) < 1,
            "Die Fortsetzen-Knöpfe sind nicht in einer Spalte mit gleicher "
            "x-Position: " + repr(xs))
        self.assert_clean_page()

    def test_session_limit_is_only_in_settings(self):
        """Vorbedingung: Überblick geöffnet.

        Erwartung: kein ``[data-nv-session-limit]`` im Überblick; in den
        Einstellungen ``input[data-nv-session-limit]`` +
        ``button[data-nv-action="session-limit-save"]`` (SettingsTest).
        """
        self.open_overview()
        self.assertEqual(
            0, self.page.locator("section[data-nv-ppanel='overview'] "
                                 "[data-nv-session-limit]").count(),
            "Das Session-Limit ist im Überblick sichtbar (wurde WP3 eingeführt)")
        self.assert_clean_page()


class SessionGroupingUiTest(F34ProjectBrowserTest):
    """GH-99: Sitzungen stehen im Kontext ihres Arbeitspakets.

    Die Gruppierung kommt aus dem ``packages``-Feld von
    ``GET /api/sessions?name=`` (dauerhafte Zuordnung), nicht aus der
    flachen ``sessions``-Liste. Der Test stubt die API bewusst mit einer
    flachen Liste in *ungruppierter* Reihenfolge: die alte Oberfläche zeigt
    genau diese Reihenfolge und besteht den Test nicht; die neue Oberfläche
    muss nach Paket gruppieren.
    """

    ALPHA = "ses_group_alpha_0123456789abcdef"
    ALPHA2 = "ses_group_alpha2_0123456789abcdef"
    BETA = "ses_group_beta_0123456789abcdef"

    def _grouped_payload(self):
        now = int(time.time())

        def row(session, agent, package_id, state, age):
            return {
                "session": session,
                "project": os.path.realpath(str(self.project)),
                "name": PROJECT,
                "run_id": "",
                "agent": agent,
                "harness": "opencode",
                "worktree_path": "",
                "package_id": package_id,
                "branch": "main",
                "first_seen": now - age - 10,
                "last_seen": now - age,
                "state": state,
                "state_label": state,
            }

        alpha = row(self.ALPHA, "alpha-agent", "F1", "running", 60)
        alpha2 = row(self.ALPHA2, "alpha-agent", "F1", "stopped", 120)
        beta = row(self.BETA, "beta-agent", "F7", "running", 30)
        return {
            "ok": True,
            "running": False,
            "resume_supported": True,
            "limit": 5,
            # Bewusst ungruppiert: F7 zuerst, obwohl F1 in ``packages``
            # zuerst kommt. Nur die neue Oberfläche nutzt ``packages``.
            "sessions": [beta, alpha, alpha2],
            "packages": [
                {"id": "F1", "title": "Erstes Paket",
                 "sessions": [alpha, alpha2]},
                {"id": "F7", "title": "Dritte Überprüfung",
                 "sessions": [beta]},
            ],
        }

    def test_sessions_grouped_by_package_with_full_id_tooltip(self):
        """Vorbedingung: /api/sessions liefert zwei Pakete mit drei Sitzungen.

        Erwartung: Die Sitzungskarte zeigt die Pakettitel in der
        ``packages``-Reihenfolge (F1 vor F7); die Sitzungen eines Pakets
        stehen hinter dessen Titel und vor dem nächsten Pakettitel. Jede
        Session-ID erscheint als gekürztes ``code.nv-session-id`` mit
        vollständiger ID im ``title``; der Fortsetzen-Knopf bleibt je
        Sitzung erhalten und sendet die volle ID.
        """
        payload = self._grouped_payload()
        self.page.route(
            "**/api/sessions*",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(payload, ensure_ascii=False)))

        self.open_overview()
        container = self.page.locator("div[data-nv-sessions]")
        container.first.wait_for(state="visible", timeout=20000)
        text = container.inner_text() or ""

        # Pakete in der Reihenfolge des ``packages``-Feldes, nicht der
        # flachen (hier umgekehrten) sessions-Liste.
        pos_f1 = text.index("Erstes Paket")
        pos_f7 = text.index("Dritte Überprüfung")
        self.assertLess(pos_f1, pos_f7,
                        "Die Pakete sind nicht nach ``packages`` gruppiert: "
                        + repr(text))
        self.assertLess(pos_f1, text.index("alpha-agent"),
                        "alpha-agent steht nicht unter F1: " + repr(text))
        self.assertLess(text.index("alpha-agent"), pos_f7,
                        "F1-Sitzungen stehen nicht vor F7: " + repr(text))
        self.assertLess(pos_f7, text.index("beta-agent"),
                        "beta-agent steht nicht unter F7: " + repr(text))

        codes = container.locator("code.nv-session-id")
        self.assertEqual(3, codes.count(),
                         "Nicht alle Sitzungen zeigen eine code.nv-session-id")
        by_full = {}
        for code in codes.all():
            by_full[code.get_attribute("title")] = code
        for full in (self.ALPHA, self.ALPHA2, self.BETA):
            self.assertIn(full, by_full,
                          f"Der Tooltip für {full} fehlt: "
                          + repr(list(by_full)))
            code = by_full[full]
            self.assertLess(len(code.inner_text() or ""), len(full),
                            f"Die Session-ID {full} ist nicht gekürzt")
            self.assertEqual(
                full, code.get_attribute("title"),
                "Der Tooltip zeigt nicht den vollständigen Session-Namen")

        resumes = container.locator("button[data-nv-action='session-resume']")
        self.assertEqual(3, resumes.count(),
                         "Der Fortsetzen-Knopf fehlt für mindestens eine "
                         "Sitzung")
        # Fortsetzen sendet weiterhin die *volle* ID, nicht die Kurzform.
        first_resume = resumes.first
        row = first_resume.locator(
            "xpath=ancestor::*[contains(@class, 'nv-session-row')][1]")
        expected_session = row.locator("code.nv-session-id").first.get_attribute(
            "title")
        first_resume.click()
        self.wait_until(
            lambda: any(
                p.get("session") == expected_session
                for p in self.posts_to("/api/sessions")),
            message="Fortsetzen sendet nicht die vollständige Session-ID: "
                    + repr(self.posts_to("/api/sessions")))
        self.assert_clean_page()


class WorkTest(F34ProjectBrowserTest):
    def test_work_order_and_no_board(self):
        """Vorbedingung: Arbeit geöffnet.

        GH-108: „Paket anlegen“, „Bug melden“ und „Feedback geben“ stehen im
        Header und sind in jedem Tab verfügbar; in der Work-Ansicht gibt es
        keine eigene Aktionsleiste mehr. Erwartung: Header-Aktionen vor der
        Filterleiste, danach das Kanban-Board. GH-67: die Priorisierung liegt
        auf Desktop nicht im DOM (siehe open_work_mobile).
        """
        panel = self.open_work()
        hero = self.page.locator("[data-nv-hero]")
        for action in ("new-package", "new-bug", "new-feedback"):
            with self.subTest(action=action):
                self.assertEqual(
                    1, hero.locator(f"[data-nv-action='{action}']").count(),
                    f"{action} fehlt im Header")
                self.assertEqual(
                    0, panel.locator(f"[data-nv-action='{action}']").count(),
                    f"{action} ist noch in der Work-Ansicht")
        self.assert_before(
            "[data-nv-hero] [data-nv-action='new-package']",
            "section[data-nv-ppanel='work'] div.nv-filter-bar[data-nv-filter-bar]",
            "Die Header-Aktionen stehen nicht vor der Filterleiste")
        self.assert_follows(
            [
                "section[data-nv-ppanel='work'] div.nv-filter-bar[data-nv-filter-bar]",
                "section[data-nv-ppanel='work'] div[data-nv-board]",
            ],
            "Filterleiste und Board stehen nicht in der Reihenfolge "
            "Filterleiste → Board")
        self.assertEqual(
            3, panel.locator("[data-nv-col]").count(),
            "GH-56: Das Board muss genau drei Spalten haben")
        self.assert_clean_page()

    def test_filterbar_hooks_exist(self):
        """Vorbedingung: Arbeit geöffnet.

        Erwartung: ``input[data-nv-work-search]``, Chips
        ``button[data-nv-work-kind]`` in {all, package, bug, feedback},
        ``button[data-nv-work-hide-done]`` mit ``aria-pressed="true"``.
        """
        panel = self.open_work()
        search = panel.locator("input[data-nv-work-search]")
        search.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, search.count(),
                         "input[data-nv-work-search] fehlt")
        chips = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind]")
        self.assertEqual(
            ["all", "package", "bug", "feedback"],
            chips.evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-nv-work-kind'))"),
            "Die Typ-Chips haben nicht die Werte all|package|bug|feedback")
        toggle = panel.locator("button[data-nv-work-hide-done]")
        self.assertEqual(1, toggle.count(),
                         "button[data-nv-work-hide-done] fehlt")
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte anzeigen“ ist nicht standardmäßig aktiv")
        self.assert_clean_page()

    def test_integrated_list_and_kinds(self):
        """Vorbedingung: Arbeit geöffnet, „Erledigte anzeigen“ aus
        (F2 erledigtes Paket, FB-1 erledigtes Feedback).

        Erwartung: ``div.nv-ticket-list[data-nv-ticket-list]`` mit sichtbaren
        Karten ``article[data-nv-ticket]``/``article[data-nv-feedback-item]``
        mit ``data-nv-kind`` ∈ {package, bug, feedback}; erledigtes F2 als
        Karte gelistet, unsichtbar; keine separate Feedback-Sektion
        (``details[data-nv-feedback-box]``).
        """
        panel = self.open_work()
        # Die Reihenfolge ist hier nicht Fachgegenstand (Priorisierung wird
        # in den PriorityTest-Fällen geprüft); entscheidend ist die vollständige
        # Menge der nicht erledigten Einträge beider Arten.
        self.assertCountEqual(
            ["F1", "F3", "F4", "F5", "F6", "F7", "F8", "B7"],
            self.visible_card_ids(),
            "Alle offenen Einträge (Pakete, Bugs) erscheinen im Board "
            "(erledigte sind ausgeblendet)")
        f2 = self.page.locator("div[data-nv-board] [data-nv-ticket='F2']")
        self.assertEqual(1, f2.count(),
                         "Das erledigte Paket F2 ist nicht als Karte gelistet")
        self.assertFalse(f2.is_visible(),
                         "F2 ist ohne „Erledigte anzeigen“ sichtbar")
        fb1 = self.page.locator("div[data-nv-board] [data-nv-feedback-item='FB-1']")
        self.assertEqual(1, fb1.count(),
                         "Das erledigte Feedback FB-1 ist nicht als Karte gelistet")
        kinds = {ident: self.page.locator(self.card_selector(ident))
                 .first.get_attribute("data-nv-kind") or ""
                 for ident in ["F1", "F3", "F4", "F5", "F6", "F7", "F8",
                               "B7", "FB-1"]}
        self.assertEqual(
            {"F1": "package", "F3": "package", "F4": "package", "F5": "package",
             "F6": "package", "F7": "package", "F8": "package", "B7": "bug",
             "FB-1": "feedback"},
            kinds, "Die Karten nennen data-nv-kind package|bug|feedback")
        self.assertEqual(
            0, self.page.locator("details[data-nv-feedback-box]").count(),
            "Es gibt eine separate Feedback-Sektion (details[data-nv-feedback-box])")
        self.assert_clean_page()

    def test_work_search_finds_done_and_filters(self):
        """Vorbedingung: F2 ist erledigt und ausgeblendet.

        GH-56/GH-67: Erledigte bleiben unabhängig von der Suche verborgen und
        werden ausschließlich über den Show-done-Schalter sichtbar. Der frühere
        Done-Schnellfilter gibt es nicht mehr. Die Fachlichkeit bleibt: Suche
        filtert Treffer, der Schalter blendet erledigte Treffer gezielt ein,
        Reset stellt den Ausgangszustand wieder her.
        """
        panel = self.open_work()
        search = panel.locator("input[data-nv-work-search]")
        f2 = self.page.locator("div[data-nv-board] [data-nv-ticket='F2']")
        f1 = self.page.locator("div[data-nv-board] [data-nv-ticket='F1']")
        done_chip = panel.locator("button[data-nv-work-hide-done]")
        self.assertFalse(f2.is_visible(), "Vorbedingung: F2 ist ausgeblendet")
        search.fill("F2")
        self.wait_until(
            lambda: not f1.is_visible(), timeout=15,
            message="Die Suche „F2“ lässt das nicht passende Paket F1 sichtbar")
        self.assertFalse(f2.is_visible(),
                         "GH-56: ein Suchtreffer darf Done nicht einblenden")
        done_chip.click()
        self.wait_until(
            lambda: f2.is_visible(), timeout=15,
            message="Der Show-done-Schalter blendet den erledigten "
                    "Suchtreffer nicht ein")
        search.fill("")
        done_chip.click()
        self.wait_until(
            lambda: f1.is_visible() and not f2.is_visible(), timeout=15,
            message="Nach Reset der Suche und des Show-done-Schalters stimmt "
                    "die Sichtbarkeit nicht")
        self.assert_clean_page()

    def test_hide_done_toggle(self):
        """Vorbedingung: F2 (Paket) und FB-1 (Feedback) sind erledigt.

        Erwartung: Standard ``aria-pressed="true"``, beide erledigten Karten
        unsichtbar, Label „Erledigte anzeigen (2)“ — ein erledigtes Paket
        plus ein erledigtes Feedback, nicht die Anzahl der Pakete allein.
        Nach Klick ``aria-pressed="false"``, beide Karten sichtbar, Label
        „Erledigte ausblenden“.
        """
        panel = self.open_work()
        toggle = panel.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte anzeigen“ ist nicht standardmäßig aktiv")
        # GH-82: erledigte Karten liegen im Erledigt-Raster, nicht im Board.
        f2 = self.page.locator(
            "[data-nv-work-done-grid] [data-nv-ticket='F2']")
        fb1 = self.page.locator(
            "[data-nv-work-done-grid] [data-nv-feedback-item='FB-1']")
        self.assertEqual(1, f2.count(), "Das erledigte Paket F2 fehlt")
        self.assertEqual(1, fb1.count(), "Das erledigte Feedback FB-1 fehlt")
        self.assertFalse(f2.is_visible(),
                         "Die erledigte Karte F2 ist trotz Standardfilter sichtbar")
        self.assertFalse(fb1.is_visible(),
                         "Das erledigte Feedback FB-1 ist trotz Standardfilter sichtbar")
        label = toggle.inner_text() or ""
        self.assertRegex(
            label, re.compile(r"(?i)show done|erledigte anzeigen"),
            "Der Knopf bietet nicht „Erledigte anzeigen“ an: " + repr(label))
        # GH-121: die gemischte Zahl aus Paket UND Feedback muss stimmen.
        self.assertRegex(
            label,
            re.compile(r"(?i)\b(?:show done|erledigte anzeigen)\s*\(2\)"),
            "Der Knopf meldet nicht die gemischte Anzahl 2 (F2 + FB-1): "
            + repr(label))
        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "false",
            timeout=15,
            message="Der Klick setzt aria-pressed nicht auf false")
        self.wait_until(
            lambda: f2.is_visible() and fb1.is_visible(), timeout=15,
            message="Die erledigten Karten F2 und FB-1 erscheinen nicht")
        label = toggle.inner_text() or ""
        self.assertRegex(
            label, re.compile(r"(?i)hide done|erledigte ausblenden"),
            "Der Knopf bietet nach dem Einblenden kein „Erledigte ausblenden“ "
            "an: " + repr(label))
        self.assert_clean_page()

    def test_show_done_count_covers_packages_and_feedback(self):
        """GH-121: „Show done“ zählt erledigte Pakete UND Feedback.

        Vorbedingung: F34-Fixture mit erledigtem Paket F2, erledigtem
        Feedback FB-1 und acht nicht erledigten Einträgen.
        Aktion: Work öffnen, Label lesen, Umschalter hin und zurück klicken,
        dazwischen nach dem erledigten Feedback suchen.
        Erwartung: Die Labelzahl entspricht genau der Zahl erledigter Karten
        beider Arten, bleibt nach dem Zurückschalten erhalten und schließt
        die nicht erledigten Einträge nicht ein. Beide erledigten Karten
        werden gemeinsam ein-/ausgeblendet; aria-pressed, Hooks und die
        Verknüpfung mit der Suche bleiben dabei erhalten.
        """
        panel = self.open_work()
        toggle = panel.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        done_f2 = self.page.locator(
            "[data-nv-work-done-grid] [data-nv-ticket='F2']")
        done_fb1 = self.page.locator(
            "[data-nv-work-done-grid] [data-nv-feedback-item='FB-1']")
        open_cards = self.page.locator(
            "div[data-nv-board] [data-nv-ticket], "
            "div[data-nv-board] [data-nv-feedback-item]")
        self.assertEqual(1, done_f2.count(), "Vorbedingung: F2 ist erledigt")
        self.assertEqual(1, done_fb1.count(), "Vorbedingung: FB-1 ist erledigt")
        self.assertEqual(8, open_cards.count(),
                         "Vorbedingung: acht Einträge sind nicht erledigt")

        def label_count():
            label = toggle.inner_text() or ""
            match = re.search(r"\((\d+)\)", label)
            self.assertIsNotNone(
                match, "Das Show-done-Label nennt keine Zahl: " + repr(label))
            return int(match.group(1))

        self.assertEqual(2, label_count(),
                         "Die Startzahl zählt F2 und FB-1 nicht gemeinsam")
        self.assertLess(label_count(), open_cards.count(),
                        "Die Startzahl zählt auch nicht erledigte Einträge")
        self.assertFalse(done_f2.is_visible(), "F2 ist anfangs nicht verborgen")
        self.assertFalse(done_fb1.is_visible(),
                         "FB-1 ist anfangs nicht verborgen")
        self.assertTrue(
            all(card.is_visible() for card in open_cards.all()),
            "Nicht erledigte Karten sind anfangs nicht sichtbar")

        # Die Suche allein darf erledigte Treffer nicht einblenden.
        search = panel.locator("input[data-nv-work-search]")
        search.fill("FB-1")
        self.wait_until(
            lambda: not done_fb1.is_visible(), timeout=15,
            message="Die Suche blendet erledigtes Feedback ohne Show-done ein")
        search.fill("")
        self.wait_until(
            lambda: all(card.is_visible() for card in open_cards.all()),
            timeout=15, message="Nach Reset der Suche fehlen offene Karten")

        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "false"
            and done_f2.is_visible() and done_fb1.is_visible(),
            timeout=15,
            message="Show done blendet nicht beide erledigten Karten ein")
        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "true"
            and not done_f2.is_visible() and not done_fb1.is_visible(),
            timeout=15,
            message="Zurückschalten verbirgt die erledigten Karten nicht wieder")
        self.assertEqual(2, label_count(),
                         "Die Zahl nach dem Zurückschalten ist nicht mehr 2")
        self.assert_clean_page()

    def test_show_done_count_includes_done_bug(self):
        """GH-121: Ein erledigter Bug zählt wie Paket und Feedback.

        Vorbedingung: F34-Fixture plus zusätzlicher erledigter Bug BUG-9.
        Aktion: Ticketspeicher ergänzen, Work öffnen, Umschalter klicken.
        Erwartung: „Show done (3)“ für F2 (Paket), FB-1 (Feedback) und BUG-9
        (Bug); der Bug liegt im Erledigt-Raster und wird mit ein-/ausgeblendet.
        """
        rows = TICKETS_f34 + feedback_fixture(self.proof_hash)
        rows.append(ticket("BUG-9", "Erledigter Bug", type="bug", state="done",
                           description="Behoben.", commit=self.proof_hash,
                           test="test_done_bug"))
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": rows},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

        panel = self.open_work()
        toggle = panel.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        label = toggle.inner_text() or ""
        self.assertRegex(
            label,
            re.compile(r"(?i)\b(?:show done|erledigte anzeigen)\s*\(3\)"),
            "Der erledigte Bug fehlt in der Show-done-Zahl: " + repr(label))
        bug = self.page.locator(
            "[data-nv-work-done-grid] [data-nv-feedback-item='BUG-9']")
        self.assertEqual(1, bug.count(), "Der erledigte Bug fehlt im Raster")
        self.assertFalse(bug.is_visible(), "Der erledigte Bug ist anfangs sichtbar")
        toggle.click()
        self.wait_until(lambda: bug.is_visible(), timeout=15,
                        message="Show done blendet den erledigten Bug nicht ein")
        self.assert_clean_page()

    def test_work_chips_filter_by_kind(self):
        """Vorbedingung: Arbeit geöffnet.

        Aktion: Chip ``button[data-nv-work-kind="bug"]`` drücken.

        Erwartung: nur ``article[data-nv-kind="bug"]`` (B7) sichtbar,
        Paket-/Feedback-Karten ausgeblendet; Chip „all“ stellt alle offenen
        wieder her.
        """
        panel = self.open_work()
        bug_chip = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind='bug']")
        bug_chip.click()
        b7 = self.page.locator("div[data-nv-board] [data-nv-feedback-item='B7']")
        f1 = self.page.locator("div[data-nv-board] [data-nv-ticket='F1']")
        self.wait_until(
            lambda: b7.is_visible() and not f1.is_visible(), timeout=15,
            message="Chip „bug“: B7 ist nicht sichtbar oder F1 bleibt sichtbar "
                    "(Karten tragen data-nv-kind nicht auf article-Ebene?)")
        self.assertEqual([card.get_attribute("data-nv-ticket")
                          or card.get_attribute("data-nv-feedback-item")
                          for card in self.page.locator(
                              "div[data-nv-board] [data-nv-ticket], "
                              "div[data-nv-board] [data-nv-feedback-item]").all()
                          if card.is_visible()], ["B7"],
                         "Nach Chip „bug“ sind nicht nur die Bugs sichtbar")
        all_chip = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind='all']")
        all_chip.click()
        self.wait_until(
            lambda: f1.is_visible() and b7.is_visible(), timeout=15,
            message="Chip „all“ stellt die offenen Einträge nicht wieder her")
        self.assert_clean_page()

    def test_done_cards_have_no_delete_and_api_rejects_delete(self):
        """Vorbedingung: Arbeit geöffnet (F2 erledigt, FB-1 erledigt).

        Aktion: API-Löschversuch auf das erledigte Paket F2 und das erledigte
        Feedback FB-1.

        Erwartung: Die F2-Karte hat keinen Löschen-Knopf (Edit gesperrt);
        ``POST /api/ticket`` {action:delete,id:F2} und ``POST /api/feedback``
        {action:delete,id:FB-1} liefern ``ok:false``; beide Einträge bleiben
        in ``/api/project`` vorhanden.
        """
        panel = self.open_work()
        f2 = self.page.locator("div[data-nv-board] [data-nv-ticket='F2']")
        self.assertEqual(1, f2.count(), "Das erledigte Paket F2 ist nicht als Karte gelistet")
        self.assertEqual(
            0, f2.locator("button[data-nv-action='ticket-delete']").count(),
            "Die erledigte Karte hat einen Löschen-Knopf (Backend-Schutz fehlt)")
        self.assertEqual(
            0, f2.locator("button[data-nv-action='ticket-edit']").count(),
            "Die erledigte Karte hat einen Bearbeiten-Knopf")
        status, data = self.post_json(
            "/api/ticket", {"name": PROJECT, "action": "delete", "id": "F2"})
        # Vertrag (WP7): ``ok:false`` + Meldung (HTTP-Status kann 400 sein,
        # die Anwendungs-Antwort ist ``ok:false``).
        self.assertFalse(data.get("ok"),
                         "Der API-Löschversuch auf das erledigte Paket F2 "
                         "liefert ok:true: " + repr(data))
        self.assertRegex(
            str(data.get("message") or ""), r"(?i)abgeschlossen|erledigt|nachweis",
            "Der API-Löschversuch auf F2 liefert keine Nachweis-Meldung: "
            + repr(data))
        status, data = self.post_json(
            "/api/feedback",
            {"name": PROJECT, "action": "delete", "id": "FB-1"})
        self.assertFalse(data.get("ok"),
                         "Der API-Löschversuch auf das erledigte Feedback FB-1 "
                         "liefert ok:true: " + repr(data))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: any(entry.get("id") == "F2" for entry in data.get("tickets") or [])
            and any(entry.get("id") == "FB-1" for entry in data.get("feedback") or []),
            message="F2/FB-1 wurden durch den Löschversuch gelöscht")
        self.assert_clean_page()

    def test_priority_strip_is_first_two_prioritized(self):
        """Vorbedingung: ``POST /api/priority`` order „F7 F8“ (beide Ready).

        GH-56: Der Strip enthält ausschließlich Ready-Tickets; Draft F5
        darf nicht erscheinen. GH-67: der Strip existiert nur mobil, daher
        läuft dieser Fall mit 600x800 statt auf dem Desktop-Board.
        Erwartung: Strip-Reihenfolge == effektive Ordnung, erste beide F7, F8.
        """
        self.set_priority("F7 F8")
        self.open_work_mobile()
        expected = self.expected_effective_ids()
        self.assertEqual(
            ["F7", "F8"], expected[:2],
            "Vorbedingung: F7/F8 leiten sich als erste, priorisierte Einträge "
            "ab: " + repr(expected))
        self.assertNotIn("F5", expected,
                         "GH-56: ein Draft-Ticket darf nicht priorisiert werden")
        self.wait_until(
            lambda: self.strip_ids() == expected, timeout=20,
            message="Die Strip-Reihenfolge passt nicht zur effektiven Ordnung: "
                    + repr(self.strip_ids()) + " erwartet: " + repr(expected))
        self.assertIn("F1", expected, "Vorbedingung: F1 in der Ordnung")
        f7_card = self.page.locator(
            "section[data-nv-ppanel='work'] [data-nv-ticket='F7']")
        f7_card.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "P1", f7_card.locator("span[data-nv-prio-badge]").first
            .inner_text(),
            "Die priorisierte Karte F7 trägt kein P1-Badge")
        self.assert_clean_page()

    def test_drag_and_drop_shows_marker_and_persists(self):
        """Vorbedingung: order „F7 F8“ (beide Ready).

        Aktion: Drag-Griff von F7 auf die Zeile von B7 ziehen.

        Erwartung: während des Ziehens sichtbare Einfügemarke
        (``div[data-nv-drop-marker]``); nach Drop POST ``/api/priority``
        {action:"set"} mit abweichender Permutation; Strip zeichnet die neue
        Reihenfolge sofort; ``GET /api/priority`` liefert sie persistiert.
        """
        self.set_priority("F7 F8")
        self.open_work_mobile()
        before = self.strip_ids()
        handle = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F7'] "
            "button[data-nv-drag-handle]")
        target = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='B7'] "
            "button[data-nv-drag-handle]")
        handle.wait_for(state="visible", timeout=20000)
        handle_box = handle.bounding_box()
        target_box = target.bounding_box()
        self.assertIsNotNone(handle_box)
        self.assertIsNotNone(target_box)
        # 1) Echter Drag-Start auf dem Drag-Griff (dragstart → Geister-Zeile).
        #    Chromium startet den Drag erst beim ersten Move nach mouse.down.
        self.page.mouse.move(handle_box["x"] + handle_box["width"] / 2,
                             handle_box["y"] + handle_box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(target_box["x"] + target_box["width"] / 2,
                             target_box["y"] + target_box["height"] / 2)
        ghost = self.page.locator("[data-nv-drag-ghost]")
        self.wait_until(
            lambda: ghost.count() == 1 and ghost.is_visible(), timeout=15,
            message="Der Drag-Griff bricht ab: keine sichtbare Geisterzeile "
                    "(div[data-nv-drag-ghost]) beim Ziehen")
        # 2) Einfügemarke während des Ziehens. Headless-Chromium feuert
        #    während manuellen Ziehen kein dragover; wir fahren es auf dem
        #    Strip nach, um den Produkt-Pfad (Live-Einfügemarke) zu üben —
        #    browserseitig wird dragover während eines Drags gefeuert.
        self.page.evaluate(
            """(y) => {
              const strip = document.querySelector(
                'div[data-nv-priority-strip]');
              const dataTransfer = new DataTransfer();
              strip.dispatchEvent(new DragEvent('dragover', {
                bubbles: true, cancelable: true, clientY: y,
                dataTransfer: dataTransfer}));
            }""", target_box["y"] + target_box["height"] / 2)
        marker = self.page.locator(
            "div[data-nv-priority-strip] div[data-nv-drop-marker]")
        self.wait_until(
            lambda: marker.count() == 1 and marker.is_visible(), timeout=15,
            message="Während des Ziehens ist keine sichtbare Einfügemarke "
                    "(div[data-nv-drop-marker]) vorhanden")
        # 3) Drop durch einen echten Playwright-Drag (Chromium feuert
        #    dragover + drop während des Drag-Vorgangs).
        self.page.mouse.up()
        handle.drag_to(target, force=True)
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertNotEqual(
            before, posted_order,
            "Der Drop hat die Strip-Reihenfolge nicht verändert: " + repr(posted_order))
        self.assertIn("F7", posted_order, "Die neue Reihenfolge enthält F7 nicht: "
                                         + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht "
                    "persistiert: " + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die neue Reihenfolge nicht sofort: "
                    + repr(self.strip_ids()))
        self.assert_clean_page()

    def test_drag_and_drop_moves_card_to_exact_target_position(self):
        """Vorbedingung: explizite Priorität „F7 B7 F8 F1“ über die Ready-
        Einträge (GH-56: nur ``open`` erscheint im Strip).
        Aktion: Drag-Griff von F1 auf die Zeile von F8 ziehen.
        Erwartung: F1 steht direkt vor F8; die exakte neue Reihenfolge wird
        per POST und ``GET /api/priority`` persistiert.
        """
        self.set_priority("F7 B7 F8 F1")
        self.open_work_mobile()
        expected_before = ["F7", "B7", "F8", "F1"]
        self.wait_until(
            lambda: self.strip_ids() == expected_before, timeout=20,
            message="Die definierte Startreihenfolge der Strip-Liste fehlt: "
                    + repr(self.strip_ids()))
        # Kein-Voll-Neurender-Messung: DOM-Sentinel am Strip (überlebt nur,
        # wenn das Element nicht ersetzt wird) plus echter Render-Zähler
        # (testseitig umhülltes NV.render, siehe install_render_counter).
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.evaluate(
            "node => node.setAttribute('data-nv-f34-no-rerender', '1')")
        render_before = self.nv_render_count()
        source = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F1'] "
            "button[data-nv-drag-handle]")
        target = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F8'] "
            "button[data-nv-drag-handle]")
        source.wait_for(state="visible", timeout=20000)
        target.wait_for(state="visible", timeout=20000)
        source_box = source.bounding_box()
        target_box = target.bounding_box()
        self.assertIsNotNone(source_box)
        self.assertIsNotNone(target_box)
        self.page.mouse.move(source_box["x"] + source_box["width"] / 2,
                             source_box["y"] + source_box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(target_box["x"] + target_box["width"] / 2,
                             target_box["y"] + target_box["height"] / 2)
        ghost = self.page.locator("[data-nv-drag-ghost]")
        self.wait_until(
            lambda: ghost.count() == 1 and ghost.is_visible(), timeout=15,
            message="Der Drag-Start bricht ab: keine sichtbare Geisterzeile "
                    "(div[data-nv-drag-ghost]) beim Ziehen")
        # 2) Einfügemarke während des Ziehens. Headless-Chromium feuert
        #    während manuellen Ziehen kein dragover; wir fahren es auf dem
        #    Strip nach, um den Produkt-Pfad (Live-Einfügemarke) zu üben —
        #    browserseitig wird dragover während eines Drags gefeuert.
        self.page.evaluate(
            """(y) => {
              const strip = document.querySelector(
                'div[data-nv-priority-strip]');
              const dataTransfer = new DataTransfer();
              strip.dispatchEvent(new DragEvent('dragover', {
                bubbles: true, cancelable: true, clientY: y,
                dataTransfer: dataTransfer}));
            }""", target_box["y"] + target_box["height"] / 2)
        marker = self.page.locator(
            "div[data-nv-priority-strip] div[data-nv-drop-marker]")
        self.wait_until(
            lambda: marker.count() == 1 and marker.is_visible(), timeout=15,
            message="Während des Ziehens ist keine sichtbare Einfügemarke "
                    "(div[data-nv-drop-marker]) vorhanden")
        self.page.mouse.up()
        source.drag_to(target, force=True)
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        expected_after = ["F7", "B7", "F1", "F8"]
        self.assertEqual(
            expected_after, posted_order,
            "Der Drop hat die exakte Zielposition nicht respektiert: "
            "erwartet " + repr(expected_after) + ", erhalten: " + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die exakte neue Reihenfolge nicht: "
                    + repr(self.strip_ids()))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der Drop bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            "1", strip.get_attribute("data-nv-f34-no-rerender"),
            "Der Drop hat den Priorisierungs-Strip ersetzt "
            "(Voll-Neurender statt lokalem Neuzeichnen)")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der Drop vollneu-rendered (NV.render wurde während des "
            "Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_arrows_reorder_and_save(self):
        """Vorbedingung: order „F7 F8“ (beide Ready).

        Aktion: ↓-Knopf der ersten Zeile (F7) klicken.

        Erwartung: ``POST /api/priority`` mit neuer Reihenfolge (F8 vor F7);
        ``GET /api/priority`` bestätigt die neue Reihenfolge.
        """
        self.set_priority("F7 F8")
        self.open_work_mobile()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.evaluate(
            "node => node.setAttribute('data-nv-f34-no-rerender', '1')")
        render_before = self.nv_render_count()
        down = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F7'] "
            "button[data-nv-action='priority-down']")
        self.assertEqual(1, down.count(), "↓-Knopf für F7 fehlt")
        down.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertEqual(
            ["F8", "F7"], posted_order[:2],
            "Der ↓-Knopf speichert F8 vor F7 nicht: " + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per ↓ gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids()[:2] == ["F8", "F7"], timeout=15,
            message="Der Strip zeigt nach ↓ nicht sichtbar F8 vor F7: "
                    + repr(self.strip_ids()))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der ↓-Knopf bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            "1", strip.get_attribute("data-nv-f34-no-rerender"),
            "Der ↓-Knopf hat den Priorisierungs-Strip ersetzt "
            "(Voll-Neurender statt lokalem Neuzeichnen)")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der ↓-Knopf vollneu-rendered (NV.render wurde während des "
            "Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_card_rank_badges_follow_priority_action_without_rerender(self):
        """Vorbedingung: order „F7 F8 B7“: nur diese Ready-Karten tragen
        ``P1``–``P3``, F1 trägt zunächst kein Badge.

        Aktion: ↓-Knopf der Zeile F7 klicken (Speicherweg wie nach Drag & Drop).

        Erwartung: die Karten-Badges ``span[data-nv-prio-badge]`` der
        Arbeitskarten in ``div[data-nv-ticket-list]`` tragen die NEUE
        Reihenfolge (``P<index+1>`` gemäß Strip-Reihenfolge und persistierter
        ``/api/priority``-Order); Karten ohne Rang tragen kein Badge; der Strip
        zeigt dieselben Ränge; Toast bestätigt das Speichern; KEIN
        Voll-Neurender (echter Render-Zähler unverändert).
        """
        self.set_priority("F7 F8 B7")
        self.open_work_mobile()
        strip = self.page.locator("div[data-nv-priority-strip]")
        self.wait_until(
            lambda: self.strip_ids()[:3] == ["F7", "F8", "B7"], timeout=20,
            message="Vorbedingung: der Strip beginnt nicht mit F7, F8, B7: "
                    + repr(self.strip_ids()))

        def card_badges():
            """Rang-Badge je Arbeitskarte (Kennung -> ``P<n>`` oder ``None``)."""
            return self.page.evaluate(
                """() => {
                  const out = {};
                  document.querySelectorAll(
                    'section[data-nv-ppanel="work"] [data-nv-ticket], '
                    + 'section[data-nv-ppanel="work"] [data-nv-feedback-item]'
                  ).forEach(card => {
                    const id = card.getAttribute('data-nv-ticket')
                      || card.getAttribute('data-nv-feedback-item');
                    const badge = card.querySelector(
                      'span[data-nv-prio-badge]');
                    out[id] = badge ? badge.textContent.trim() : null;
                  });
                  return out;
                }""")

        def strip_ranks():
            """Rang-Präfix je Strip-Zeile (Kennung -> Text der Zeile)."""
            return self.page.evaluate(
                """() => {
                  const out = {};
                  document.querySelectorAll(
                    'div[data-nv-priority-strip] [data-nv-priority-id]'
                  ).forEach(row => {
                    const id = row.getAttribute('data-nv-priority-id');
                    const label = row.querySelector('.nv-priority-label');
                    out[id] = label ? label.textContent.trim() : '';
                  });
                  return out;
                }""")

        before = card_badges()
        self.assertEqual(
            {"F7": "P1", "F8": "P2", "B7": "P3"},
            {ident: before.get(ident) for ident in ("F7", "F8", "B7")},
            "Vorbedingung: die priorisierten Karten tragen nicht P1–P3: "
            + repr(before))
        self.assertIsNone(
            before.get("F1"),
            "Vorbedingung: F1 hat ohne Rang ein Badge: " + repr(before))

        render_before = self.nv_render_count()
        down = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F7'] "
            "button[data-nv-action='priority-down']")
        self.assertEqual(1, down.count(), "↓-Knopf für F7 fehlt")
        down.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertEqual(
            ["F8", "F7", "B7"], posted_order[:3],
            "Der ↓-Knopf speichert die neue Reihenfolge nicht: "
            + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per ↓ gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die neue Reihenfolge nicht sofort: "
                    + repr(self.strip_ids()))

        expected_badges = {ident: "P" + str(index + 1)
                           for index, ident in enumerate(posted_order)}
        observed = card_badges()
        deadline = time.time() + 15
        while time.time() < deadline:
            observed = card_badges()
            if all(observed.get(ident) == badge
                   for ident, badge in expected_badges.items()):
                break
            self.page.wait_for_timeout(100)
        self.assertEqual(
            expected_badges,
            {ident: observed.get(ident) for ident in expected_badges},
            "Die Karten-Badges folgen der neuen Reihenfolge nicht "
            "(erwartet ``P<index+1>`` gemäß Strip und persistierter Order): "
            + repr(observed))
        unbewertet = {ident: badge for ident, badge in observed.items()
                      if ident not in expected_badges and badge}
        self.assertEqual(
            {}, unbewertet,
            "Karten ohne Rang tragen ein Badge: " + repr(unbewertet))
        ranks = strip_ranks()
        for index, ident in enumerate(posted_order):
            self.assertTrue(
                str(ranks.get(ident) or "").startswith("P" + str(index + 1) + " "),
                "Der Strip zeigt für " + ident + " nicht P" + str(index + 1)
                + ": " + repr(ranks.get(ident)))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der ↓-Knopf bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Die Rang-Aktualisierung vollneu-rendered (NV.render wurde "
            "während des Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_priority_reset(self):
        """Vorbedingung: order „F5 F8“ (Badges vorhanden).

        Aktion: ``button[data-nv-priority-reset]`` klicken.

        Erwartung: POST ``/api/priority`` mit ``order:""``; Badges
        (``span[data-nv-prio-badge]``) verschwinden.
        """
        self.set_priority("F7 F8")
        self.open_work_mobile()
        strip = self.page.locator("div[data-nv-priority-strip]")
        self.assertGreaterEqual(
            self.page.locator("span[data-nv-prio-badge]").count(), 2,
            "Vorbedingung: die priorisierten Einträge zeigen keine Badges")
        reset = strip.locator("button[data-nv-priority-reset]")
        self.assertEqual(1, reset.count(), "Der Zurücksetzen-Knopf fehlt")
        reset.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        and str(payload.get("order") or "") == ""
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Das Zurücksetzen sendet nicht order:\"\": "
                    + repr(self.posts_to("/api/priority")))
        self.wait_until(
            lambda: self.page.locator("span[data-nv-prio-badge]").count() == 0,
            timeout=15,
            message="Die Prioritäts-Badges bleiben nach dem Zurücksetzen stehen")
        self.assert_clean_page()

    def test_back_to_top(self):
        """Vorbedingung: Arbeit geöffnet, Seite mindestens 600px scrollbar.

        GH-67: Der Desktop-Strip entfällt und verkürzt die Seite. Damit die
        600px-Schwelle des Nach-oben-Knopfs überhaupt erreichbar bleibt,
        ergänzt dieser Fall zusätzliche Tickets im Fixture. Die fachliche
        Erwartung wird dadurch nicht abgeschwächt.

        Aktion: bis zu 600 px Scrolltiefe scrollen.

        Erwartung: ``button[data-nv-back-to-top]`` erscheint; Klick scrollt
        zum Listenanfang (scrollY sinkt deutlich).
        """
        store = self.project / ".vibe" / "tickets.json"
        data = json.loads(store.read_text(encoding="utf-8"))
        data["tickets"].extend(
            ticket("BT%d" % index, "Zusätzliche Karte %d" % index)
            for index in range(8))
        store.write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        panel = self.open_work()
        button = panel.locator("button[data-nv-back-to-top]")
        self.assertEqual(1, button.count(),
                         "Der Nach-oben-Knopf [data-nv-back-to-top] fehlt")
        self.assertFalse(button.is_visible(),
                         "Der Nach-oben-Knopf ist ohne Scrolltiefe sichtbar")
        self.page.evaluate(
            "() => window.scrollTo(0, Math.max(document.body.scrollHeight, "
            "1200))")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => Math.max(window.scrollY || 0, "
                "document.documentElement.scrollTop || 0) >= 600"),
            timeout=20,
            message="Die Seite ist nicht in die benötigte Tiefe scrollbar")
        self.wait_until(
            lambda: button.is_visible(), timeout=15,
            message="Der Nach-oben-Knopf erscheint nicht ab 600px Scrolltiefe")
        before = self.page.evaluate(
            "() => Math.max(window.scrollY || 0, "
            "document.documentElement.scrollTop || 0)")
        button.click()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => Math.max(window.scrollY || 0, "
                "document.documentElement.scrollTop || 0) < %s" % (before - 100,)),
            timeout=20,
            message="Das Scrollen zum Listenanfang ging nicht zurück (scrollY "
                    "hat nicht um mindestens 100px abgesunken)")
        self.assert_clean_page()


class AssistantTest(F34ProjectBrowserTest):
    def test_assistant_tab_and_headings(self):
        """Vorbedingung: Projekt geöffnet.

        Erwartung: Tab „Beschreibung“ (label ~/beschreibung|description/i),
        ``nav[data-nv-guide-nav]`` mit mindestens einem
        ``[data-nv-guide-step]``; Überschrift „1. Project goal“ im englischen
        Modus (keine deutsche „Projektziel“-Überschrift).
        """
        panel = self.open_assistant()
        tab = self.page.locator("[data-nv-ptab='assistant']")
        self.assertRegex(tab.inner_text() or "",
                         re.compile(r"beschreibung|description", re.I),
                         "Der Tab heißt nicht „Beschreibung“: "
                         + repr(tab.inner_text()))
        nav = panel.locator("nav[data-nv-guide-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            panel.locator("nav[data-nv-guide-nav] [data-nv-guide-step]").count(),
            1, "Es fehlen Schritt-Knöpfe in nav[data-nv-guide-nav]")
        headings = panel.locator("h4").all_inner_texts()
        self.assertTrue(
            any(re.search(r"^1\.\s*Project goal$", text.strip())
                for text in headings),
            "Der erste Schritt heißt im englischen Modus „1. Project goal“: "
            + repr(headings))
        self.assertNotIn("Projektziel", panel.inner_text() or "",
                         "Eine deutsche „Projektziel“-Überschrift bleibt im "
                         "englischen Modus")
        self.assert_clean_page()

    def test_answer_fields_have_rows_ge_6(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: alle ``textarea[data-nv-answer-field]`` haben ``rows >= 6``.
        """
        panel = self.open_assistant()
        fields = panel.locator("textarea[data-nv-answer-field]")
        fields.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(fields.count(), 1, "Es fehlen Antwortfelder")
        for index in range(fields.count()):
            rows = fields.nth(index).evaluate(
                "node => parseInt(node.getAttribute('rows') || '0', 10) || "
                "node.rows")
            self.assertGreaterEqual(
                rows, 6, f"Antwortfeld {index} hat weniger als 6 rows")
        self.assert_clean_page()

    def test_no_status_pills_ausgefuellt_or_open(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: keine ``span.nv-pill`` mit Text „ausgefüllt“/„open“;
        keine ``[data-nv-step-status]``.
        """
        panel = self.open_assistant()
        pills = panel.locator("span.nv-pill").all()
        for pill in pills:
            text = (pill.inner_text() or "").strip()
            self.assertFalse(
                re.search(r"(?i)ausgefüllt|open", text),
                "Unerlaubte Status-Pille: " + repr(text))
        self.assertEqual(
            0, panel.locator("[data-nv-step-status]").count(),
            "Es gibt noch die F33-Status-Pillen [data-nv-step-status]")
        self.assert_clean_page()

    def test_guide_nav_jumps_to_step(self):
        """Vorbedingung: Beschreibung geöffnet.

        Aktion: ``button[data-nv-guide-step="ziel"]`` klicken.

        Erwartung: der Schritt ``section[data-nv-guide-step-id="ziel"]`` wird
        sichtbar (in den Viewport gescrollt).
        """
        panel = self.open_assistant()
        nav = panel.locator("nav[data-nv-guide-nav]")
        first = nav.locator("[data-nv-guide-step]").first
        first.wait_for(state="visible", timeout=20000)
        first.click()
        self.wait_until(
            lambda: self.page.evaluate(
                """id => {
                  const el = document.querySelector(
                    'section[data-nv-guide-step-id="' + id + '"]');
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.bottom > 0 && rect.top < window.innerHeight;
                }""", "ziel"),
            timeout=20,
            message="Der Klick auf den Schritt-Knopf springt nicht zum Schritt")
        self.assert_clean_page()


class SettingsTest(F34ProjectBrowserTest):
    def test_settings_section_order(self):
        """Vorbedingung: Einstellungen geöffnet (generisches Projekt).

        Erwartung: Sektionen in der Reihenfolge agentsfile, basics, sandbox,
        team, github, writeaccess, session-limit (Fehlerbehebung nur Android).
        """
        panel = self.open_settings()
        order = panel.evaluate(
            """node => Array.from(node.querySelectorAll(
                'section[data-nv-psection]'))
                 .map(section => section.getAttribute('data-nv-psection'))""")
        self.assertEqual(
            ["agentsfile", "basics", "sandbox", "team", "github",
             "writeaccess", "session-limit"], order,
            "Die Einstellungen sind nicht in der vertraglichen Reihenfolge: "
            + repr(order))
        self.assert_clean_page()

    def test_agents_section_has_editable_content_without_managed_block(self):
        """GH-101: Die AGENTS.md-Sektion ist offen, zeigt den vollständigen
        Dateiinhalt in einem editablen Feld und keinen verwalteten Block mehr.
        Die Backup-Auswahl bleibt vorhanden.
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        details.wait_for(state="visible", timeout=20000)
        self.assertTrue(details.evaluate("node => node.open"),
                        "Die AGENTS.md-Sektion ist nicht offen (Standard offen)")
        fields = details.locator(
            "textarea[data-nv-agents-text], textarea[data-nv-agents-before],"
            " textarea[data-nv-agents-after]")
        self.assertGreaterEqual(fields.count(), 1, "Kein editbares Textfeld")
        for index in range(fields.count()):
            rows = fields.nth(index).evaluate(
                "node => parseInt(node.getAttribute('rows') || '0', 10) || node.rows")
            self.assertGreaterEqual(
                rows, 14, "textarea[data-nv-agents-*] hat weniger als 14 rows")
        combined = "".join(fields.nth(i).input_value() or ""
                           for i in range(fields.count()))
        for needle in ("Projektregel davor", "Verwaltete Regel 4711",
                       "Projektregel danach"):
            with self.subTest(inhalt=needle):
                self.assertIn(needle, combined,
                              "Der Dateiinhalt fehlt im Editor: " + needle)
        self.assertEqual(
            0, details.locator("pre[data-nv-agents-managed]").count(),
            "Der verwaltete Block wird weiterhin angezeigt")
        self.assertNotRegex(
            (details.inner_text() or ""), r"verwalteten block|managed block",
            "Die Sektion nennt weiterhin den verwalteten Block")
        backup = details.locator("select[data-nv-agents-backup]")
        self.assertEqual(1, backup.count(), "select[data-nv-agents-backup] fehlt")
        self.assert_clean_page()

    def test_agents_backup_select_lists_backups(self):
        """Vorbedingung: AGENTS.md-Sektion offen.

        Aktion: „Sicherung anlegen“ klicken (POST ``/api/agents_file``
        action=backup).

        Erwartung: ``select[data-nv-agents-backup]`` listet die angelegte
        Sicherung (Zeitstempel).
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        backup = details.locator("select[data-nv-agents-backup]")
        backup.wait_for(state="visible", timeout=20000)
        backup_button = details.locator(
            "button[data-nv-action='agents-file-backup']")
        self.assertEqual(1, backup_button.count(), "Der Sicherungs-Knopf fehlt")
        backup_button.click()
        self.wait_until(
            lambda: any(payload.get("action") == "backup"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Der Klick speichert nicht über POST /api/agents_file "
                    "{action: backup}: " + repr(self.posts_to("/api/agents_file")))
        options = backup.locator("option").all_inner_texts()
        timestamps = [text for text in options
                      if re.search(r"\d{8}-\d{6}-\d{6}", text)]
        self.assertTrue(
            timestamps,
            "Der select[data-nv-agents-backup] listet keine Sicherungen mit "
            "Zeitstempel: " + repr(options))
        self.assert_clean_page()

    def test_agents_restore_confirmation_and_post(self):
        """Vorbedingung: AGENTS.md-Sektion offen.

        Aktion: „Wiederherstellen“ klicken; bestätigen.

        Erwartung: ``div[data-nv-agents-restore-confirm]`` sichtbar mit
        sichtbarem Sicherungsnamen; „Ja, wiederherstellen“ schickt POST
        ``/api/agents_file`` {action:restore}.
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        restore = details.locator(
            "button[data-nv-action='agents-file-restore']")
        self.assertEqual(1, restore.count(), "Der Wiederherstellen-Knopf fehlt")
        confirm = details.locator("div[data-nv-agents-restore-confirm]")
        self.assertEqual(1, confirm.count(),
                         "Die Inline-Bestätigung der Wiederherstellung fehlt")
        self.assertFalse(confirm.is_visible(),
                         "Die Bestätigung ist ohne Klick sichtbar")
        restore.click()
        confirm.wait_for(state="visible", timeout=15000)
        self.assertIn("wiederherstellen", (confirm.inner_text() or "").lower(),
                      "Der Bestätigungstext nennt das Wiederherstellen nicht: "
                      + repr(confirm.inner_text()))
        self.assertEqual(
            0, len([payload for payload in self.posts_to("/api/agents_file")
                    if payload.get("action") == "restore"]),
            "Die Wiederherstellung wurde ohne Bestätigung ausgeführt")
        self.page.locator("details[data-nv-agents-section] "
                          "button[data-nv-action='agents-file-restore-confirm']") \
            .click()
        self.wait_until(
            lambda: any(payload.get("action") == "restore"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Die Bestätigung sendet keinen /api/agents_file-POST "
                    "action=restore: " + repr(self.posts_to("/api/agents_file")))
        self.assert_clean_page()

    def test_basics_type_help_and_confirm(self):
        """Vorbedingung: Basics geöffnet, Projekt initialisiert (``.vibe/project.env``).

        Erwartung: ``small[data-nv-type-help]`` nicht leer; „Projekt
        vorbereiten“ fehlt; Typwechsel zeigt ``div[data-nv-type-confirm]``;
        „Ja, Typ ändern“ POSTet ``/api/init``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='basics']")
        section.wait_for(state="visible", timeout=20000)
        type_help = section.locator("small[data-nv-type-help]")
        self.assertEqual(1, type_help.count(), "small[data-nv-type-help] fehlt")
        self.assertTrue((type_help.inner_text() or "").strip(),
                        "Die Typ-Erklärung ist leer")
        self.assertEqual(
            0, section.locator("[data-nv-action='init']").count(),
            "Der Knopf „Projekt vorbereiten“ ist für ein vorhandenes Projekt "
            "unexpected sichtbar")
        type_select = section.locator("select[data-nv-field='type']")
        type_select.wait_for(state="visible", timeout=20000)
        type_select.select_option("python")
        confirm = section.locator("div[data-nv-type-confirm]")
        self.wait_until(
            lambda: confirm.is_visible(), timeout=15000,
            message="Das Typwechsel-Bestätigungs-Div ist ohne Änderung nicht sichtbar")
        self.assertRegex(type_help.inner_text() or "", re.compile(r"python", re.I),
                         "Die Typ-Erklärung ändert sich nicht mit dem Typ")
        section.locator("button[data-nv-action='type-confirm-yes']").click()
        self.wait_until(
            lambda: any(payload.get("type") == "python"
                        for payload in self.posts_to("/api/init")),
            timeout=20,
            message="Der Bestätigung sendet keinen /api/init-POST mit type=python: "
                    + repr(self.posts_to("/api/init")))
        self.assert_clean_page()

    def test_sandbox_section_early_with_explanation(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``section[data-nv-psection='sandbox']`` nach Basics und
        vor Team; Erklärung („Sandbox“ + erlaubte/verbotene Punkte);
        ``[data-nv-field='sandbox-toggle']`` und ``[data-nv-field='sandbox-check']``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='sandbox']")
        section.wait_for(state="visible", timeout=20000)
        self.assertRegex(section.inner_text() or "", re.compile(r"sandbox"),
                         "Die Sandbox-Erklärung fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='sandbox-toggle']").count(),
            "Der Sandbox-Schalter [data-nv-action=sandbox-toggle] fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='sandbox-check']").count(),
            "Der Prüfen-Knopf [data-nv-action=sandbox-check] fehlt")
        self.assert_clean_page()

    def test_team_section_rows(self):
        """Vorbedingung: Einstellungen geöffnet (Agents tester/helper in HOME).

        Erwartung: ``section[data-nv-psection='team']`` mit
        ``[data-nv-team-agent]``-Zeilen für tester und helper.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='team']")
        section.wait_for(state="visible", timeout=20000)
        agents = section.evaluate(
            """node => Array.from(node.querySelectorAll('[data-nv-team-agent]'))
                 .map(row => row.getAttribute('data-nv-team-agent'))""")
        self.assertIn("tester", agents, "Vorbedingung: Agent tester fehlt")
        self.assertIn("helper", agents, "Vorbedingung: Agent helper fehlt")
        self.assert_clean_page()

    def test_github_structure(self):
        """Vorbedingung: Einstellungen geöffnet, GitHub-Verbindung
        (``owner/name``) konfiguriert.

        Erwartung: ``span[data-nv-github-token-state]`` (Token-Status-Pille,
        „Kein Token“ ohne Token); ``select[data-nv-github-push-branch]`` und
        ``select[data-nv-github-push-target]`` als selects; „Fetch“ im
        Synchronisieren-Block (``[data-nv-action='github-fetch']``);
        Issues-Sync erklärt (``[data-nv-field='github-issues-enabled']``).
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='github']")
        section.wait_for(state="visible", timeout=20000)
        token_state = section.locator("span[data-nv-github-token-state]")
        self.assertEqual(1, token_state.count(),
                         "Die Token-Status-Pille [data-nv-github-token-state] fehlt")
        self.assertTrue((token_state.inner_text() or "").strip(),
                        "Der Token-Status ist leer")
        for hook in ("select[data-nv-github-push-branch]",
                     "select[data-nv-github-push-target]"):
            select = section.locator(hook)
            self.assertEqual(1, select.count(),
                             f"{hook} fehlt")
            self.assertEqual("SELECT", select.first.evaluate(
                "node => node.tagName"), f"{hook} ist kein select")
        for hook in ("[data-nv-action='github-pull']",
                     "[data-nv-action='github-fetch']",
                     "[data-nv-action='github-push']"):
            self.assertEqual(1, section.locator(hook).count(),
                             f"Der Synchronisieren-Block hat keinen {hook}")
        issues = section.locator("[data-nv-field='github-issues-enabled']")
        self.assertEqual(1, issues.count(),
                         "Der Issues-Sync-Schalter fehlt")
        self.assertRegex(section.inner_text() or "", re.compile(r"issues"),
                         "Die GitHub-Issues werden nicht erklärt")
        self.assert_clean_page()

    def test_write_access_section(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``section[data-nv-psection='writeaccess']`` mit
        ``[data-nv-field='path']`` und ``[data-nv-action='rights-add']``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='writeaccess']")
        section.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, section.locator("[data-nv-field='path']").count(),
                         "[data-nv-field=path] fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='rights-add']").count(),
            "[data-nv-action=rights-add] fehlt")
        self.assert_clean_page()

    def test_session_limit_section_and_save(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``input[data-nv-session-limit]`` +
        ``button[data-nv-action="session-limit-save"]``; Erklärung „gilt nur
        für dieses Projekt“; Save POSTet ``/api/sessions {action:"limit"}``;
        ``GET /api/sessions?name=`` liefert ``limit``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='session-limit']")
        section.wait_for(state="visible", timeout=20000)
        limit_input = section.locator("input[data-nv-session-limit]")
        save = section.locator("button[data-nv-action='session-limit-save']")
        self.assertEqual(1, limit_input.count(),
                         "input[data-nv-session-limit] fehlt")
        self.assertEqual(1, save.count(),
                         "button[data-nv-action=session-limit-save] fehlt")
        self.assertRegex(
            section.inner_text() or "",
            re.compile(r"(?i)applies to this project only|gilt nur für dieses Projekt"),
            "Die Erklärung „gilt nur für dieses Projekt“ fehlt")
        limit_input.fill("5")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "limit" and payload.get("limit") == 5
                        for payload in self.posts_to("/api/sessions")),
            timeout=20,
            message="Der Speichern-Knopf POSTet nicht über /api/sessions "
                    "action=limit limit=5: " + repr(self.posts_to("/api/sessions")))
        self.wait_api(
            f"/api/sessions?name={PROJECT}",
            lambda data: int(data.get("limit") or 0) == 5,
            message="Das Projektlimit ist nicht gespeichert")
        self.assert_clean_page()

    def test_no_checks_or_opencode_server_hooks(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: keine ``[data-nv-doctor-row]`` (Prüfungen), keine
        ``[data-nv-sessions-limit]``/``[data-nv-limit-hint]`` (WP3-Hooks).
        """
        panel = self.open_settings()
        self.assertEqual(0, panel.locator("[data-nv-doctor-row]").count(),
                         "Die Prüfungen (data-nv-doctor-row) sind vorhanden")
        self.assertEqual(0, panel.locator("[data-nv-sessions-limit]").count(),
                         "Die WP3-Hook [data-nv-sessions-limit] ist vorhanden")
        self.assertEqual(0, panel.locator("[data-nv-limit-hint]").count(),
                         "Der WP3-Hook [data-nv-limit-hint] ist vorhanden")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme: neue Zugänglichkeitsstruktur der Einstellungen
# ===========================================================================

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Installed developer dependency: Chromium is read-only from the user
# cache (same pattern as tests/browser/test_ap06_github_ui.py); never
# downloaded inside a test.
_BROWSERS_ap7 = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS_ap7.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS_ap7))

from playwright.sync_api import sync_playwright


# Ambient VIBE_* values (sandbox/container) would point vibe-web at the
# productive installation; the test must own all runtime paths.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_HARNESS",
)


class Ap7SettingsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_settings(self):
        # Vorbedingung einstellen: Projekt öffnen, Register „Einstellungen“.
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        panel = self.page.locator("#panel-einstellungen")
        panel.wait_for()
        self.assertTrue(panel.is_visible(), "Einstellungen-Panel ist nicht sichtbar")

    def nav(self):
        return self.page.locator(".settings-nav")

    def chip(self, goto):
        return self.nav().locator('[data-goto="%s"]' % goto)

    def chip_gotos(self):
        return self.nav().locator("[data-goto]").evaluate_all(
            "els => els.map(el => el.getAttribute('data-goto'))"
        )

    def chip_texts(self):
        return self.nav().locator("[data-goto]").all_inner_texts()

    def expand(self, section_selector):
        """Klappt einen optionalen Abschnitt auf, falls er als <details> liegt.

        Für Tests, die gegen die aktuelle Bestandsstruktur neutral
        bleiben sollen, ist der Klick ein No-op, solange der Abschnitt
        noch kein <summary> enthält (Bestandsstruktur zeigt alles
        ohne Aufklappen).
        """
        section = self.page.locator(section_selector).first
        summary = section.locator("summary")
        if not summary.count():
            return
        section.evaluate("el => el.scrollIntoView({block: 'center'})")
        if not section.evaluate("el => !!el.open"):
            summary.click()
        self.wait_until(
            lambda: section.evaluate("el => !!el.open"),
            message="Abschnitt %s ließ sich nicht aufklappen" % section_selector,
        )

    def section_visible_without_scroll(self, selector):
        box = self.page.evaluate(
            """(sel) => {
              const el = document.querySelector(sel);
              if (!el) return null;
              const b = el.getBoundingClientRect();
              return {top: b.top, bottom: b.bottom,
                      viewport: window.innerHeight};
            }""",
            selector,
        )
        self.assertIsNotNone(box, "Abschnitt %s fehlt" % selector)
        self.assertLessEqual(
            box["bottom"], box["viewport"],
            "%s liegt unter dem sichtbaren Bereich" % selector,
        )
        self.assertGreaterEqual(
            box["top"], 0, "%s liegt über dem sichtbaren Bereich" % selector,
        )

    def order_by_document_position(self, *selectors):
        # AK-Hilfsnachweis: DOM-Reihenfolge (vorbereitet für Tab-Reihenfolge).
        return self.page.evaluate(
            """(sels) => {
              const picked = sels.map(s => document.querySelector(s));
              if (picked.some(el => el == null)) return false;
              for (let i = 1; i < picked.length; i += 1) {
                const rel = picked[i - 1].compareDocumentPosition(picked[i]);
                if (!(rel & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
              }
              return true;
            }""",
            list(selectors),
        )

    # ------------------------------------------------------------ Testfälle
    def test_settings_tab_shows_section_nav_and_open_agents_first(self):
        """AK 2a/2b/2c/2d/3.

        Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“
        frisch aktiviert, nichts aufgeklappt.
        Aktion: Abschnittsleiste, Agentenabschnitt und die drei optionalen
        Abschnitte inspizieren.
        Erwartet: .settings-nav mit den vier Sprungknöpfen (Bedienknöpfe,
        Status-Pills: Agenten „…“ oder Zahl, Schreibrechte „Standardliste“,
        Sandbox „aus“, GitHub „aus“); #project-agents offen und bedienbar;
        #settings-rechte/#sandbox/#github vorhanden als eingeklappte
        <details>; ihr Steuerelemente unsichtbar; DOM-Reihenfolge nav →
        Agenten → Schreibrechte → Sandbox → GitHub; Abschnittsleiste und
        Agentensteuerung ohne Scrollen im sichtbaren Bereich.
        """
        self.open_settings()

        gotos = self.chip_gotos()
        self.assertEqual(
            set(gotos), {"agenten", "rechte", "sandbox", "github"},
            "Sprungknöpfe der Abschnittsleiste unvollständig: %r" % (gotos,),
        )
        for goto in ("agenten", "rechte", "sandbox", "github"):
            chip = self.chip(goto)
            self.assertGreater(chip.count(), 0, "Chip %s fehlt" % goto)
            self.assertTrue(
                chip.evaluate(
                    "el => el.matches('button, [role=button]')", timeout=2000),
                "Chip %s ist kein Bedienknopf" % goto,
            )

        # Status-Pills: Agenten zeigt nach dem Laden „…“ oder eine Zahl.
        self.wait_until(
            lambda: any(
                "…" in text or any(c.isdigit() for c in text)
                for text in self.chip_texts()
            ),
            timeout=15,
            message="Der Agenten-Chip zeigt weder … noch eine Zahl",
        )
        self.assertRegex(" ".join(self.chip_texts()), r"Standardliste|Default list",
                         "Der Schreibrechte-Chip nennt weder „Standardliste“ noch „Default list“")
        self.assertIn("off", self.chip("sandbox").inner_text(),
                      "Der Sandbox-Chip zeigt nicht „off“")
        self.assertIn("off", self.chip("github").inner_text(),
                      "Der GitHub-Chip zeigt nicht „off“")

        agents = self.page.locator("#project-agents")
        agents.wait_for()
        self.assertTrue(agents.is_visible(), "Agenten-Abschnitt ist nicht offen")
        toggle = agents.locator('input[data-toggle="unconfigured"]')
        toggle.wait_for()
        self.assertTrue(
            toggle.is_visible() and toggle.is_enabled(),
            "Agenten-Auswahl ist im Standardzustand nicht bedienbar",
        )

        for section_selector, probe in (
            ("#settings-rechte", "Restore defaults"),
            ("#sandbox", None),
            ("#github", "Link with GitHub"),
        ):
            section = self.page.locator(section_selector)
            section.wait_for()
            self.assertFalse(
                section.evaluate("el => !!el.open"),
                "%s ist im Standardzustand nicht eingeklappt" % section_selector,
            )
            if probe:
                button = section.get_by_role("button", name=probe)
                self.assertFalse(
                    button.first.is_visible() if button.count() else False,
                    "Inhalt von %s ist sichtbar, obwohl eingeklappt"
                    % section_selector,
                )
        sandbox_input = self.page.get_by_label("Build tools")
        self.assertFalse(
            sandbox_input.first.is_visible() if sandbox_input.count() else False,
            "Build-Werkzeuge-Eingabe ist im eingeklappten Zustand sichtbar",
        )

        self.assertTrue(
            self.order_by_document_position(
                ".settings-nav", "#project-agents",
                "#settings-rechte", "#sandbox", "#github",
            ),
            "DOM-Reihenfolge ist nicht Leiste, Agenten, Schreibrechte, "
            "Sandbox, GitHub",
        )

        self.section_visible_without_scroll(".settings-nav")
        toggle_box = toggle.evaluate(
            "el => {const b = el.getBoundingClientRect();"
            "return {bottom: b.bottom, viewport: window.innerHeight}}"
        )
        self.assertLessEqual(
            toggle_box["bottom"], toggle_box["viewport"],
            "Agenten-Steuerung ist ohne Scrollen nicht vollständig sichtbar",
        )

    def test_chips_open_optional_sections_without_full_reload(self):
        """AK 2a (Chips öffnen die Abschnitte), AK 3/4 (kein Neuladen).

        Vorbedingung: Register „Einstellungen“ geöffnet; ein Marker „__ap7“
        ist in window gesetzt.
        Aktion: Chips für Sandbox, Schreibrechte und Git & GitHub nacheinander
        klicken.
        Erwartet: jeder Abschnitt klappt sich auf und sein Steuerinhalt wird
        sichtbar und in den sichtbaren Bereich gescrollt; der Marker überlebt
        den Klick (kein Neuladen); der Agenten-Abschnitt bleibt
        dabei sichtbar (nicht geschlossen).
        """
        self.open_settings()
        self.page.evaluate("window.__ap7_marker = 1")
        agents_toggle = self.page.locator('#project-agents input[data-toggle="unconfigured"]')
        # Die Agententabelle lädt asynchron (/api/project-agents); der
        # Abschlussvergleich läuft erst gegen den geladenen Zustand.
        agents_toggle.wait_for()

        self.chip("sandbox").click(timeout=2000)
        self.wait_until(
            lambda: self.page.locator("#sandbox").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Turn on sandbox").is_visible(),
            message="Sandbox-Chip klappte den Sandbox-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#sandbox")
        self.assertEqual(self.page.evaluate("window.__ap7_marker"), 1,
                         "Der Chipklick lud die Seite neu statt nur aufzuklappen")

        self.chip("rechte").click(timeout=2000)
        self.wait_until(
            lambda: self.page.get_by_role("button", name="Restore defaults").is_visible(),
            message="Rechte-Chip klappte den Schreibrechte-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#settings-rechte")

        self.chip("github").click(timeout=2000)
        self.wait_until(
            lambda: self.page.locator("#github").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Link with GitHub").is_visible(),
            message="GitHub-Chip klappte den Git-und-GitHub-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#github")

        # Der wcześniej offene Agenten-Abschnitt bleibt offen und sichtbar.
        self.assertTrue(
            self.page.locator("#project-agents").is_visible(),
            "Agenten-Abschnitt wurde beim Chip-Klick geschlossen",
        )
        self.assertTrue(
            agents_toggle.is_visible(),
            "Agenten-Checkbox ist nach den Chip-Klicks nicht mehr sichtbar",
        )
        self.assertEqual(self.page.evaluate("window.__ap7_marker"), 1,
                         "Chips verursachten einen kompletten Seitenaufbau")

    def test_github_optional_blocks_hidden_when_disabled_collapse_and_after_enable(self):
        """AK 2e.

        Vorbedingung: Projekt „proj“ ohne GitHub-Verknüpfung; Einstellungen
        geöffnet, GitHub-Abschnitt aufgeklappt.
        Aktion 1: die Aktionsknöpfe und den Issues-Block im aus-Zustand
        prüfen.
        Aktion 2: Verknüpfungs-Checkbox aktivieren, „Speichern“ klicken, das
        Register einmal﻿﻿﻿﻿ verlassen und neu öffnen, den Abschnitt aufklappen.
        Erwartet: aus = Aktionsknöpfe und „Issues als Arbeitspakete“ unsicht-
        bar; nach Aktivieren + erneutem Öffnen sind „Abrufen (fetch, kein
        Merge)“, „Push (Branch nach origin)“, „Pull (aufholen, --ff-only)“,
        „Merge-Request stellen“ und der Issues-Block sichtbar; project.env
        erhalten GITHUB_ENABLED="1", ohne andere Zeilen zu verlieren.
        """
        self.open_settings()
        self.expand("#github")
        github = self.page.locator("#github")

        action_names = (
            "Fetch (no merge)",
            "Push (current branch)",
            "Pull (fast-forward, --ff-only)",
            "Create merge request",
        )
        for name in action_names:
            button = github.get_by_role("button", name=name)
            self.assertFalse(
                button.first.is_visible() if button.count() else False,
                "„%s“ ist ohne Verknüpfung sichtbar" % name,
            )
        issues_block = github.get_by_text("Issues as work packages")
        self.assertFalse(
            issues_block.first.is_visible() if issues_block.count() else False,
            "Der Issues-Block ist ohne Verknüpfung sichtbar",
        )

        checkbox = github.locator('input[type="checkbox"]').first
        checkbox.wait_for()
        self.assertFalse(checkbox.is_checked(), "Verknüpfung startete aktiv")
        checkbox.check()
        github.get_by_role("button", name="Save", exact=True).click()

        env_file = self.project / ".vibe" / "project.env"
        self.wait_until(
            lambda: 'GITHUB_ENABLED="1"' in env_file.read_text(encoding="utf-8"),
            message="Aktivieren schrieb kein GITHUB_ENABLED=1 nach project.env",
        )

        # Das Einstellungsregister wurde nach dem Speichern neu gebaut;
        # der Test verlässt das Register und öffnet es erneut.
        self.page.locator("[role='tab'][aria-controls='panel-arbeit']").click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        self.page.locator("#panel-einstellungen").wait_for()
        self.expand("#github")
        github = self.page.locator("#github")
        for name in action_names:
            self.wait_until(
                lambda: github.get_by_role("button", name=name).first.is_visible(),
                message="„%s“ nach Verknüpfungsaufbau nicht sichtbar" % name,
            )
        self.assertTrue(
            github.get_by_text("Issues as work packages").first.is_visible(),
            "Der Issues-Block nach Verknüpfungsaufbau nicht sichtbar",
        )

        new_text = env_file.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", new_text, "Speichern beschädigte project.env")

        # Aufräumen über dieselbe UI: Verknüpfung wieder deaktivieren, damit
        # spätere Fälle (GitHub-Chip „aus“) reihenfolgeunabhängig laufen. Der
        # Server liest das Projekt beim Neuaufbau neu ein; deshalb das
        # Register einmal betreten/verlassen statt die Datei im Hintergrund
        # zu editieren.
        self.page.locator("[role='tab'][aria-controls='panel-arbeit']").click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        self.page.locator("#panel-einstellungen").wait_for()
        self.expand("#github")
        github = self.page.locator("#github")
        checkbox = github.locator('input[type="checkbox"]').first
        self.assertTrue(checkbox.is_checked(),
                        "Die Verknüpfung ist beim Aufräumen nicht mehr aktiv")
        checkbox.uncheck()
        github.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(
            lambda: 'GITHUB_ENABLED="1"'
                    not in env_file.read_text(encoding="utf-8"),
            message="Abschalten schrieb GITHUB_ENABLED=1 nicht zurück",
        )
        self.assertIn(
            "TYPE=generic", env_file.read_text(encoding="utf-8"),
            "Abschalten beschädigte project.env",
        )

    def test_settings_default_state_needs_no_hidden_content(self):
        """AK 3.

        Vorbedingung: frisches „Einstellungen“-Register, nichts aufgeklappt.
        Aktion: nur den Standardzustand inspizieren und die wichtigen
        Agenten-Steuerelemente bedienen.
        Erwartet: Agentenfilter und Agententabelle sofort sichtbar und
        schaltbar; Build-Werkzeuge-, Verzeichnis- und Repository-Eingabe
        der optionalen Abschnitte sind ohne Aufklappen unsichtbar.
        """
        self.open_settings()

        toggle = self.page.locator('input[data-toggle="unconfigured"]')
        toggle.wait_for()
        self.assertTrue(
            toggle.is_visible() and toggle.is_enabled(),
            "Agentenfilter ist im Standardzustand nicht bedienbar",
        )
        toggle.click()
        self.wait_until(
            lambda: toggle.is_checked(),
            message="Agentenfilter ließ sich nicht umschalten",
        )

        probe_specs = (
            ("Build tools", lambda: self.page.get_by_label("Build tools")),
            ("Verzeichnis-Eingabe der Schreibrechte",
             lambda: self.page.get_by_placeholder("/absoluter/pfad")),
            ("GitHub-Repository-Eingabe",
             lambda: self.page.locator("input[placeholder='owner/name']")),
        )
        for label, probe_factory in probe_specs:
            probe = probe_factory()
            self.assertFalse(
                probe.first.is_visible() if probe.count() else False,
                "%s ist im Standardzustand sichtbar" % label,
            )

    def test_keyboard(self):
        """AK 4.

        Vorbedingung: Register „Einstellungen“ geöffnet.
        Aktion: mit der Tastatur die Abschnittsleiste durchtabben und mit
        Enter das Sandbox-summary bedienen.
        Erwartet: der erste fokussierbare Knoten des Panels ist der
        Agenten-Chip der Abschnittsleiste; Tab-Reihenfolge ist
        agenten → rechte → sandbox → github; Enter auf „summary“ von #sandbox
        macht den Abschnitt samt „Sandbox einschalten“ sichtbar.
        """
        self.open_settings()

        # Native Bedienelemente ohne tabindex: DOM-Reihenfolge = Tab-Reihen-
        # folge. Prüfung 1: der erste fokussierbare Knoten ist ein Chip.
        first_focusable = self.page.evaluate(
            """() => {
              const panel = document.querySelector('#panel-einstellungen');
              const candidates = panel.querySelectorAll(
                'button, input, select, textarea, summary');
              return candidates.length ? candidates[0].outerHTML : null;
            }"""
        )
        self.assertIsNotNone(first_focusable, "Kein fokussierbares Element im Panel")
        chip = self.chip("agenten")
        self.assertEqual(
            chip.evaluate("el => el.outerHTML", timeout=2000), first_focusable,
            "Das erste fokussierbare Element des Panels ist nicht der "
            "Agenten-Chip: %s" % first_focusable[:120],
        )

        # Prüfung 2: Tab-Reihenfolge über die Chips referenzieren.
        self.chip("agenten").focus(timeout=2000)
        expected_after_tab = {"agenten": "rechte", "rechte": "sandbox",
                              "sandbox": "github"}
        for goto, expected in sorted(expected_after_tab.items()):
            current = self.page.evaluate(
                "document.activeElement &&"
                " document.activeElement.getAttribute('data-goto') || ''"
            )
            self.assertEqual(current, goto,
                             "Fokus lag vor Tab nicht auf Chip %s" % goto)
            self.page.keyboard.press("Tab")
            next_goto = self.page.evaluate(
                "document.activeElement &&"
                " document.activeElement.getAttribute('data-goto') || ''"
            )
            self.assertEqual(next_goto, expected,
                             "Tab von %s landete nicht auf %s" % (goto, expected))

        # Prüfung 3: Enter auf dem summary macht den Abschnitt sichtbar.
        summary = self.page.locator("#sandbox summary")
        summary.wait_for()
        summary.focus()
        self.assertEqual(
            self.page.evaluate(
                "document.activeElement === document.querySelector('#sandbox summary')"
            ),
            True,
            "Das Sandbox-summary ist nicht oder nicht allein fokussierbar",
        )
        self.page.keyboard.press("Enter")
        self.wait_until(
            lambda: self.page.locator("#sandbox").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Turn on sandbox").is_visible(),
            message="Enter auf dem Sandbox-summary klappte den Abschnitt nicht auf",
        )

    def test_chip_jump_leaves_section_summary_below_fixed_header(self):
        """Review-Runde 1, Medium-Befund; verschärft in Review-Runde 2 (M1):
        der Test muss das Alignment-Regime erreichen, sonst gilt die
        Geometrie-Invariante auch ohne Gegenmaßnahme.

        Vorbedingung: Register „Einstellungen“ offen; danach wird der
        Viewport auf 400 px Höhe verengt, damit der Inhalt die Fensterhöhe
        übersteigt und scrollIntoView({block:'start'}) das Sprungziel
        tatsächlich an die Kopfleiste schieben kann (Kontrast zur
        Standardfixture, in der alles in den Viewport passt und der Sprung
        ein No-op bleibt).
        Aktion: je Chip (Schreibrechte, Sandbox, Git & GitHub) Klick, dann
        prüfen, dass wirklich gescrollt wurde, und die gerenderte Geometrie
        von .detailbar (position:sticky) und Ziel-summary lesen.
        Erwartet (Invariante): summary.top >= detailbar.bottom - 2 —
        der summary-Anfang muss unter der Unterkante der fixen Kopfleiste
        liegen. Ergänzend: nach dem Sprung window.scrollY > 0 (Alignment
        wurde erreicht — der Test fällt nicht auf einen No-op-Sprung zurück),
        summary.height > 0 und summary.top >= 0. Die Invariante ist bindend:
        im Alignment-Regime gilt gerundet summary.top ≈ scroll-margin-top; mit margin 0
        gilt die Invariante nachweisbar nicht mehr.
        Gegenmaßnahme: scroll-margin-top auf .seccard/#project-agents
        (bin/web/styles.css, AP7-Abschnitt).
        """
        self.open_settings()
        self.page.set_viewport_size({"width": 1280, "height": 400})

        for goto, selector in (
            ("rechte", "#settings-rechte"),
            ("sandbox", "#sandbox"),
            ("github", "#github"),
        ):
            self.chip(goto).click(timeout=2000)
            self.wait_until(
                lambda: self.page.locator(selector).evaluate("el => !!el.open"),
                message="Chip %s klappte den Abschnitt nicht auf" % goto,
            )
            # Vorbedingung der Invariante: der Sprung hat wirklich gescrollt.
            self.wait_until(
                lambda: self.page.evaluate("window.scrollY") > 0,
                message="Chip %s scrollte nicht: Alignment-Regime "
                "nicht erreicht" % goto,
            )
            geom = self.page.evaluate(
                """(sel) => {
                  const bar = document.querySelector('.detailbar');
                  const section = document.querySelector(sel);
                  if (!bar || !section) return null;
                  const summary = section.querySelector(':scope > summary');
                  if (!summary) return null;
                  const barBox = bar.getBoundingClientRect();
                  const sumBox = summary.getBoundingClientRect();
                  return {barBottom: barBox.bottom, barHeight: barBox.height,
                          sumTop: sumBox.top, sumHeight: sumBox.height};
                }""",
                selector,
            )
            self.assertIsNotNone(
                geom, "Kopfzeile oder Sprungziel %s nicht im DOM" % selector)
            self.assertGreater(
                geom["sumHeight"], 0,
                "summary von %s hat keine Höhe: %r" % (selector, geom),
            )
            self.assertGreaterEqual(
                geom["sumTop"], 0,
                "summary von %s liegt über dem Fensteranfang: %r"
                % (selector, geom),
            )
            self.assertGreaterEqual(
                geom["sumTop"], geom["barBottom"] - 2,
                "Sprungziel %s wird von der fixen Kopfleiste verdeckt "
                "(summary.top=%.2f < detailbar.bottom=%.2f; "
                "detailbar Höhe %.2f): %r"
                % (selector, geom["sumTop"], geom["barBottom"],
                   geom["barHeight"], geom),
            )

    def test_agents_chip_shows_error_when_agents_api_fails(self):
        """Agenten-Chip im Fehlerfall (Robustheit der Status-Pills).

        Vorbedingung: das Register startet mit blockierter Agenten-API
        (/api/project-agents wird per page.route abgebrochen (abort) —
        deterministisch, kein echtes Backend).
        Aktion: Einstellungsregister öffnen und den Agenten-Chip lesen.
        Erwartet: Der Agentenabschnitt zeigt die Fehlermeldung
        „Agentenauswahl nicht verfügbar …", und der Agenten-Chip zeigt die
        Status-Pill „Fehler" statt „…" (Ton bad, kein Stillstand bei
        „Lade …").
        """
        self.page.route(
            re.compile(r"/api/project-agents.*"),
            lambda route: route.abort(),
        )
        self.open_settings()

        error_box = self.page.locator("#project-agents .bad")
        self.wait_until(
            lambda: error_box.count() > 0
            and "Agent selection unavailable" in error_box.first.inner_text(),
            timeout=15,
            message="Der Agentenabschnitt meldete die blockierte API nicht",
        )
        chip = self.chip("agenten")
        self.wait_until(
            lambda: "Error" in chip.inner_text(),
            message="Agenten-Chip zeigt bei API-Fehler nicht „Error“",
        )
        pill_class = chip.locator(".pill").evaluate(
            "el => el.className", timeout=2000
        )
        self.assertIn("bad", pill_class,
                      "Fehler-Pill des Agenten-Chips trägt nicht den bad-Ton")


# ===========================================================================
# Browserabnahme (Teil 5): Sessions-Karte im Projektpanel
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


AGENT = "vibe-agent"
ABORTED = "ses_ab_4711"
FINISHED = "ses_ok_4711"
FAILED = "ses_bad_4711"
UNKNOWN = "ses_mut_4711"
NOW = 1_700_000_000

FAKE_TMUX = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def entry(session, state, label, agent=AGENT, last=NOW, harness="opencode",
          run_id="lauf-1"):
    return {
        "session": session,
        "project": "/tmp/proj",
        "name": "proj",
        "run_id": run_id,
        "agent": agent,
        "harness": harness,
        "first_seen": last - 600,
        "last_seen": last,
        "state": state,
        "state_label": label,
    }


def payload(sessions, running=False, resume_supported=True, limit=5):
    return {
        "ok": True,
        "running": running,
        "resume_supported": resume_supported,
        "limit": limit,
        "sessions": sessions,
    }


class Ap19SessionsUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP19 Session Management\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key.startswith(
                "SANDBOX"
            ) or key in ("TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "HOME": str(cls.root / "home"),
            "XDG_CONFIG_HOME": str(cls.root / "home" / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(cls.root / "tmux.log"),
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

    # ---------- Fixture ----------

    def setUp(self):
        self.page_errors = []
        self.dialogs = []
        self.get_payload = payload([
            entry(FAILED, "failed", "failed", last=NOW - 30),
            entry(ABORTED, "aborted", "aborted", last=NOW - 20),
            entry(FINISHED, "finished", "completed", last=NOW - 10),
            entry(UNKNOWN, "unknown", "unknown", last=NOW),
        ])
        self.posts = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 900})
        self.page.on(
            "pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)
        self.page.route("**/api/sessions*", self._handle_sessions)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def _handle_sessions(self, route):
        request = route.request
        if request.method == "POST":
            raw = request.post_data or ""
            try:
                self.posts.append(json.loads(raw))
            except ValueError:
                self.posts.append({"raw": raw})
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(
                    {"ok": True, "message": "Fortsetzen gestartet."}))
            return
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(self.get_payload, ensure_ascii=False))

    def tearDown(self):
        self.page.close()

    # ---------- Helfer ----------

    def open_project(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        self.card().wait_for(state="visible", timeout=20000)

    def card(self):
        return self.page.locator("[data-panel='arbeit'] div.card").filter(
            has=self.page.locator("b", has_text=re.compile(r"^Sessions$"))
        ).first

    def row(self, session):
        return self.card().locator(f"[data-session='{session}']").first

    def resume_button(self, session):
        return self.row(session).locator("button").filter(
            has_text=re.compile(r"^Resume$"))

    def visible_resume_buttons(self):
        buttons = self.card().locator("button").filter(
            has_text=re.compile(r"^Resume$"))
        result = []
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if button.is_visible() and button.is_enabled():
                result.append(button)
        return result

    def pill_classes(self, session):
        pill = self.row(session).locator("span.pill").first
        return set((pill.get_attribute("class") or "").split())

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Sessions-Karte erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Sessions-Karte öffnete einen Browserdialog")

    def active_element(self):
        """Text und Session-Zeile des aktuell fokussierten Elements."""
        return self.page.evaluate(
            "() => { const a = document.activeElement; "
            "if (!a) return {text: '', session: null}; "
            "const row = a.closest ? a.closest('[data-session]') : null; "
            "return {text: (a.textContent || '').trim(), "
            "session: row ? row.getAttribute('data-session') : null}; }")

    def tab_to_resume(self, session, max_steps=300):
        """Setzt den Fokus auf den Dokumentanfang und wandert per Tab bis zum
        Fortsetzen-Knopf genau dieser Session."""
        self.page.locator("body").click(position={"x": 2, "y": 2})
        for _ in range(max_steps):
            self.page.keyboard.press("Tab")
            active = self.active_element()
            if active["text"] == "Resume" and active["session"] == session:
                return
        self.fail(
            f"Der Fortsetzen-Knopf für {session} war per Tab nicht erreichbar")


class SessionsCardTest(Ap19SessionsUiTest):
    """AK1/AK2: Übersicht mit Kennung, Zustandslabel, Pille und Zeit."""

    def test_card_lists_sessions_with_state_labels_and_pill_tones(self):
        """Vier Sessions erscheinen mit Kennung, Label und passender Tonklasse."""
        self.open_project()

        for session, label in (
            (FAILED, "failed"),
            (ABORTED, "aborted"),
            (FINISHED, "completed"),
            (UNKNOWN, "unknown"),
        ):
            row = self.row(session)
            self.assertTrue(row.is_visible(),
                            f"Zeile für {session} fehlt")
            text = row.inner_text()
            self.assertIn(session, text, text)
            self.assertIn(label, text,
                          f"Zustandslabel {label!r} fehlt für {session}: {text}")

        self.assertIn("ok", self.pill_classes(FINISHED),
                      "Abgeschlossen muss die Tonklasse ok tragen")
        self.assertIn("warn", self.pill_classes(ABORTED),
                      "Abgebrochen muss die Tonklasse warn tragen")
        self.assertIn("bad", self.pill_classes(FAILED),
                      "Fehlgeschlagen muss die Tonklasse bad tragen")
        self.assertIn("mut", self.pill_classes(UNKNOWN),
                      "Unbekannt muss die Tonklasse mut tragen")
        self.assert_clean_page()

    def test_row_shows_a_human_readable_last_seen_time(self):
        """Die Zeile zeigt die Zeit nicht als rohen Epochenwert."""
        self.open_project()

        text = self.row(ABORTED).inner_text()

        self.assertFalse(
            str(NOW - 20) in text,
            f"Roher last_seen-Wert statt lesbarer Zeit: {text!r}")
        self.assertTrue(
            re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}", text)
            or re.search(r"\d{1,2}:\d{2}", text),
            f"Keine lesbare Zeit in der Zeile: {text!r}")
        self.assert_clean_page()

    def test_empty_state_when_no_sessions_were_captured(self):
        """Ohne Sessions erscheint der vereinbarte Leertext."""
        self.get_payload = payload([], limit=5)

        self.open_project()

        card_text = self.card().inner_text()
        self.assertIn("No recorded sessions yet.", card_text, card_text)
        self.assert_clean_page()


class SessionsContinueUiTest(Ap19SessionsUiTest):
    """AK3: Fortsetzen über die Karte – Payload, Sperren, Pi, Tastatur."""

    def test_resume_posts_exactly_name_session_and_action(self):
        """Ein Klick sendet den vereinbarten Payload für genau diese Session."""
        self.open_project()

        button = self.resume_button(ABORTED)
        self.assertGreater(button.count(), 0,
                           "Kein Fortsetzen-Knopf für die abgebrochene Session")
        button.first.click()

        self.wait_until(lambda: bool(self.posts),
                        message="Es wurde kein POST /api/sessions gesendet")
        self.assertEqual(
            {"name": "proj", "session": ABORTED, "action": "continue"},
            self.posts[0],
            f"Der Fortsetzen-POST hat nicht exakt den vereinbarten Payload: "
            f"{self.posts[0]!r}")
        self.assert_clean_page()

    def test_resume_is_not_offered_while_the_run_is_active(self):
        """Bei aktivem Lauf gibt es keinen betätigbaren Fortsetzen-Knopf."""
        self.get_payload = payload(
            [entry(ABORTED, "aborted", "aborted")], running=True)

        self.open_project()

        self.assertEqual(
            [], self.visible_resume_buttons(),
            "Während eines aktiven Laufs darf Fortsetzen nicht angeboten werden")
        self.assert_clean_page()

    def test_pi_shows_no_resume_button_and_explains_no_session(self):
        """Ohne Fortsetzen-Fähigkeit (Pi) erscheint kein Knopf, aber der Grund."""
        self.get_payload = payload(
            [entry(ABORTED, "aborted", "aborted", harness="pi")],
            resume_supported=False)

        self.open_project()

        card_text = self.card().inner_text()
        self.assertIn("Pi", card_text,
                      f"Der Pi-Hinweis fehlt: {card_text!r}")
        self.assertIn("--no-session", card_text,
                      f"Die --no-session-Begründung fehlt: {card_text!r}")
        self.assertEqual(
            [], self.visible_resume_buttons(),
            "Bei Pi darf kein Fortsetzen angeboten werden")
        self.assert_clean_page()

    def test_resume_can_be_operated_by_keyboard(self):
        """Der Knopf ist per Tab erreichbar und sendet mit Enter denselben POST."""
        self.open_project()

        self.tab_to_resume(ABORTED)
        self.page.keyboard.press("Enter")

        self.wait_until(lambda: bool(self.posts),
                        message="Enter auf dem Fortsetzen-Knopf sendete nichts")
        self.assertEqual(
            {"name": "proj", "session": ABORTED, "action": "continue"},
            self.posts[0],
            f"Der per Tastatur ausgelöste POST ist falsch: {self.posts[0]!r}")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme: „Trotz Änderungen starten“ im Projektdetail
# ===========================================================================

import json
import re
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT = SHOTS / "F27-trotz-aenderungen.png"

PROJECT_ENV_f27 = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK_f27 = "# FEEDBACK\n\n- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

FAKE_TMUX_f27 = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
# Lauf-Sockets kommen als "-L <socket>" vor dem Unterkommando; für die
# Erkennung zählt das Unterkommando, nicht die Socket-Auswahl.
if args[:1] == ["-L"]:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def git_f27(project, *args):
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def init_repo(project):
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    git_f27(project, "config", "user.name", "Test")
    git_f27(project, "config", "user.email", "test@example.invalid")
    git_f27(project, "config", "commit.gpgsign", "false")


def commit_all(project, message):
    git_f27(project, "add", "-A")
    result = git_f27(project, "commit", "-q", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def write_project(root, name, agents):
    project = root / name
    init_repo(project)
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(
        PROJECT_ENV_f27, encoding="utf-8"
    )
    (project / "FEEDBACK.md").write_text(FEEDBACK_f27, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    project_agent = project / ".opencode" / "agents" / "test-agent.md"
    project_agent.parent.mkdir(parents=True)
    project_agent.write_text(
        "---\ndescription: Testagent\nmode: subagent\n---\n",
        encoding="utf-8",
    )
    commit_all(project, "Ausgangsstand")
    return project


class KeepChangesUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n",
                encoding="utf-8",
            )
        cls.dirty = write_project(cls.root, "dirtyproj", cls.agents)
        (cls.dirty / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        cls.clean = write_project(cls.root, "cleanproj", cls.agents)

        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX_f27, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"

        cls.runtime = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_STATE": str(cls.root / "_state"),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_TMUX_LOG": str(cls.tmux_log),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.runtime / "web.token"
        deadline = time.time() + 20
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
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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

    def setUp(self):
        if self.tmux_log.exists():
            self.tmux_log.unlink()
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 1000}
        )
        # Ein nativer Bestätigungsdialog würde den Lauf sonst still abbrechen.
        self.dialog_seen = False

        def on_dialog(dialog):
            self.dialog_seen = True
            dialog.accept()

        self.page.on("dialog", on_dialog)

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self, name):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text=name).first
        row.wait_for()
        row.click()
        self.page.get_by_role("button", name="← Back").wait_for()

    def new_sessions(self):
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def test_dirty_project_offers_keep_changes_with_confirmation_and_files(self):
        self.open_detail("dirtyproj")
        button = self.page.get_by_role(
            "button", name=re.compile(r"Trotz Änderungen starten|Start anyway")
        )
        button.wait_for()
        self.assertTrue(button.is_visible())

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        button.click()
        group = self.page.locator(".confirm")
        try:
            group.wait_for(timeout=5000)
        except Exception:
            # Ein nativer Dialog wurde bereits automatisch bestätigt.
            group = None
        confirmed = bool(group is not None and group.count())
        if confirmed:
            yes = group.get_by_role("button").filter(has_not_text="Cancel")
            self.assertGreater(
                yes.count(), 0, "Bestätigung bot keine Zustimmung an"
            )
            yes.first.click()
        else:
            confirmed = self.dialog_seen
        self.assertTrue(
            confirmed,
            "„Trotz Änderungen starten“ startete ohne Bestätigung.",
        )

        toasts = self.page.locator("#toasts .toast").filter(
            has_text="unfertig.txt"
        )
        observed = []
        def toast_named_file():
            texts = []
            for toast in self.page.locator("#toasts .toast").all():
                try:
                    texts.append(toast.inner_text())
                except Exception:  # noqa: BLE001 - Toast kann verschwinden
                    pass
            observed[:] = texts
            return any("unfertig.txt" in text for text in texts)
        try:
            self.wait_until(
                toast_named_file,
                message="Die Rückmeldung nannte die zurückbehaltene Datei nicht",
            )
        except AssertionError as error:
            raise AssertionError(str(error) + "; Toasts: " + repr(observed)) from None
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, sessions)
        self.assertIn("VIBE_KEEP_CHANGES=1", sessions[0])
        self.assertEqual(
            (self.dirty / "unfertig.txt").read_text(encoding="utf-8"),
            "unfertig\n",
        )

    def test_clean_project_does_not_offer_an_enabled_keep_changes_action(self):
        self.open_detail("cleanproj")
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()

        button = self.page.get_by_role(
            "button", name=re.compile(r"Trotz Änderungen starten|Start anyway")
        )
        if button.count():
            self.assertFalse(
                button.first.is_visible() and button.first.is_enabled(),
                "Sauberes Projekt bot die Aktion „Trotz Änderungen starten“ an",
            )


# ===========================================================================
# Browserabnahme: AGENTS.md in der Assistent-Ansicht ansehen und bearbeiten
# ===========================================================================

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap11_priority_ui.py).
_BROWSERS_f31 = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS_f31.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS_f31))

from playwright.sync_api import sync_playwright

SHOT_f31 = Path(
    os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")
) / "F31-agents-file.png"


def general_rules():
    """Ein nicht-kanonischer Bestandsblock (GH-76: wird nicht mehr erzeugt).

    Der Block darf nicht aus einer Produktionskonstante stammen; so fällt
    jede Normalisierung auf den früheren deutschen Text auf.
    """
    return (
        "<!-- vibe:general-rules -->\n"
        "## Bestandsregel F31\n\n"
        "- alter, nicht mehr erzeugter Block\n"
        "<!-- /vibe:general-rules -->"
    )


BLOCK = general_rules()
EXPLANATION = re.compile(
    r"bleibt byte-identisch erhalten|preserved byte-identically")
BEFORE = "Kopfteil-F31\n"
AFTER = "\nFußteil-F31\n"

PROJECT_ENV_f31 = "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\nREVIEWER=code-reviewer\n"


def git_f31(project, *argv):
    return subprocess.run(
        ["git", "-C", str(project), *argv], capture_output=True, text=True, check=False
    )


class AgentsFileUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n", encoding="utf-8"
            )
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(PROJECT_ENV_f31, encoding="utf-8")
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(cls.project)], check=True,
            capture_output=True,
        )
        git_f31(cls.project, "config", "user.name", "Test")
        git_f31(cls.project, "config", "user.email", "test@example.invalid")
        git_f31(cls.project, "config", "commit.gpgsign", "false")

        toolchain = cls.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
        cls.runtime = cls.root / "_logs"
        cls.runtime.mkdir()
        cls.port = free_port()

        # Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
        # produktive Installation zeigen lassen; der Test besitzt alle
        # Laufzeitpfade selbst.
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(toolchain),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_STATE": str(toolchain),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.runtime / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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

    def setUp(self):
        # Frische AGENTS.md je Test: keine Querschieße zwischen den Fällen.
        path = self.project / "AGENTS.md"
        if path.exists():
            path.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_guide(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Assistant", exact=True).click()
        self.page.locator("#guide").wait_for()

    def agents_card(self):
        """Die AGENTS.md-Karte: innerster Karten-Container mit Speichern-Button.

        Die Karte ist ein Bestandteil der Assistent-Ansicht; sie trägt den
        Titel „AGENTS.md — Regeln für Agenten“ und enthält entweder den
        Speichern-Button oder den Button „Aus Vorlage anlegen“.
        """
        guide = self.page.locator("#guide")
        # has=-Filter verankern den eingebetteten Selektor am Kandidaten-Div,
        # nicht am Vorfahren. Ein an #guide verankerter get_by_role-Locator
        # trafe nie (der Karten-Div liegt INNERHALB von #guide und kann keinen
        # weiteren #guide-Nachfahren enthalten). Deshalb hier page-relativ.
        buttons = self.page.get_by_role(
            "button", name=re.compile(r"^(Speichern|Save)$|^(Aus Vorlage anlegen|Create from template)$")
        )
        return (
            guide.locator("div")
            .filter(has_text=re.compile(r"Regeln für Agenten|rules for agents", re.I))
            .filter(has=buttons)
            .last
        )

    def agents_path(self):
        return self.project / "AGENTS.md"

    def write_agents(self):
        self.agents_path().write_text(BEFORE + BLOCK + AFTER, encoding="utf-8")

    # ---------- AK1 + AK2: Ansicht und Kennzeichnung ----------

    def test_card_shows_full_text_without_a_separate_managed_block(self):
        """GH-101: Die Karte zeigt den vollständigen Dateiinhalt — including
        des Legacy-Markerblocks — byte-identisch in einem Feld. Ein verwalteter
        Block wird nicht mehr als eigenes, schreibgeschütztes Element
        ausgewiesen; die eingefrorene klassische UI behält nur ihre
        Kompatibilitätsfelder (vorher = Gesamttext, nachher = leer).
        """
        full = BEFORE + BLOCK + AFTER
        self.write_agents()
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        text = card.inner_text()
        self.assertIn("AGENTS.md", text)
        self.assertRegex(text, r"Regeln für Agenten|rules for agents")
        # Der Hinweis der eingefrorenen klassischen UI bleibt zulässig.
        self.assertRegex(text, EXPLANATION)
        boxes = card.get_by_role("textbox")
        self.assertEqual(boxes.count(), 2, "vor/after-Textareas fehlen in der Karte")
        self.assertEqual(
            boxes.nth(0).input_value(), full,
            "Der vollständige Dateiinhalt fehlt oder ist verändert")
        self.assertEqual(boxes.nth(1).input_value(), "")
        # Kein gesonderter verwalteter Block mehr: kein <pre> und kein
        # Element außerhalb der Textareas trägt den Legacy-Blocktext.
        self.assertEqual(
            0, card.locator("pre").count(),
            "Die Karte stellt weiterhin einen verwalteten Block dar")
        stray = card.evaluate(
            """node => {
                 const hits = [];
                 node.querySelectorAll('*').forEach(el => {
                   if (el.tagName === 'TEXTAREA') return;
                   if ((el.textContent || '').includes('Bestandsregel F31')) {
                     hits.push(el.tagName);
                   }
                 });
                 return hits;
               }""")
        self.assertEqual(
            [], stray, "Der Legacy-Block wird als eigenes Element angezeigt")
        SHOT_f31.parent.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(SHOT_f31))
        self.assertTrue(SHOT_f31.exists() and SHOT_f31.stat().st_size > 0)

    # ---------- AK3: Bearbeiten und Speichern ----------

    def test_editing_full_text_saves_file_and_keeps_legacy_markers_identical(self):
        """GH-101: Bearbeitet wird der vollständige Text. Der Legacy-Block
        bleibt beim Speichern byte-identisch; Marker werden weder eingefügt
        noch entfernt. Die eingefrorene klassische UI nutzt weiterhin die
        Kompatibilitätsfelder, die API speichert ``text`` mit Digest-Schutz.
        """
        full = BEFORE + BLOCK + AFTER
        self.write_agents()
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        boxes = card.get_by_role("textbox")
        # Der Gesamttext steht im Kompatibilitätsfeld „vorher“; geändert wird
        # nur der Teil nach dem Block, der Block selbst bleibt unberührt.
        source = boxes.nth(0)
        self.assertEqual(source.input_value(), full)
        changed = BEFORE + BLOCK + "\nFußteil-F31 geändert\n"
        source.fill(changed)
        card.get_by_role("button", name="Save").click()
        self.wait_until(
            lambda: "Fußteil-F31 geändert" in self.agents_path().read_text(encoding="utf-8"),
            message="Speichern hat AGENTS.md nicht aktualisiert",
        )
        text = self.agents_path().read_text(encoding="utf-8")
        self.assertEqual(text, changed)
        self.assertEqual(text.count("<!-- vibe:general-rules -->"), 1)
        self.assertEqual(text.count("<!-- /vibe:general-rules -->"), 1)

        # API: vollständiger Text + Digest ohne Block-Sonderbehandlung.
        def get_view():
            request = urllib.request.Request(
                self.base + "/api/agents_file?name=proj",
                headers={"X-Token": self.token})
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))

        def post_save(payload):
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                self.base + "/api/agents_file", data=body, method="POST",
                headers={"X-Token": self.token,
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                try:
                    return json.loads(error.read().decode("utf-8"))
                finally:
                    error.close()

        digest = get_view()["digest"]
        self.assertTrue(digest)
        api_text = BEFORE + BLOCK + "\nAPI-Änderung F31\n"
        answer = post_save({"name": "proj", "action": "save",
                            "text": api_text, "digest": digest})
        self.assertTrue(answer.get("ok"), answer)
        result = self.agents_path().read_text(encoding="utf-8")
        self.assertEqual(result, api_text)
        self.assertEqual(result.count("<!-- vibe:general-rules -->"), 1)
        self.assertEqual(result.count("<!-- /vibe:general-rules -->"), 1)

        # Digest-Schutz: eine fremde Änderung nach dem Lesen wird nicht
        # überschrieben; die Datei bleibt byte-identisch.
        stale = get_view()["digest"]
        foreign = api_text + "Fremde Änderung\n"
        self.agents_path().write_text(foreign, encoding="utf-8")
        answer = post_save({"name": "proj", "action": "save",
                            "text": api_text, "digest": stale})
        self.assertFalse(answer.get("ok"), answer)
        self.assertEqual(self.agents_path().read_text(encoding="utf-8"), foreign)

    # ---------- AK3b: Blockfreie Datei (GH-76) ----------

    def test_blockless_file_allows_editing_both_parts_and_saves_them(self):
        """GH-76: Ohne verwalteten Block müssen beide Textareas editierbar sein.

        Vorbedingung: AGENTS.md ohne Marker. Aktion: beide Teile ändern und
        speichern. Erwartung: ``before`` ist NICHT deaktiviert; die Datei
        enthält danach ``before + after``. Fehlerfall: die UI deaktiviert den
        oberen Teil, obwohl blockfreie Dateien der Normalfall sind.
        """
        self.agents_path().write_text("Oben-F31\nUnten-F31\n", encoding="utf-8")
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        boxes = card.get_by_role("textbox")
        self.assertEqual(2, boxes.count(), "vor/after-Textareas fehlen")
        self.assertTrue(boxes.nth(0).is_enabled(),
                        "Der obere Teil ist bei blockfreier Datei deaktiviert")
        self.assertTrue(boxes.nth(1).is_enabled(),
                        "Der untere Teil ist deaktiviert")
        boxes.nth(0).fill("Neuer oberer Teil F31\n")
        boxes.nth(1).fill("Neuer unterer Teil F31\n")
        card.get_by_role("button", name="Save").click()
        self.wait_until(
            lambda: "Neuer unterer Teil F31" in self.agents_path().read_text(
                encoding="utf-8"),
            message="Speichern hat die blockfreie AGENTS.md nicht aktualisiert",
        )
        self.assertEqual(
            "Neuer oberer Teil F31\nNeuer unterer Teil F31\n",
            self.agents_path().read_text(encoding="utf-8"))

    # ---------- AK6: Aus Vorlage anlegen ----------

    def test_missing_file_can_be_created_from_template(self):
        self.assertFalse(self.agents_path().exists())
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        card.get_by_role("button", name="Create from template").click()
        self.wait_until(
            lambda: self.agents_path().exists(),
            message="AGENTS.md wurde nicht aus der Vorlage angelegt",
        )
        text = self.agents_path().read_text(encoding="utf-8")
        self.assertIn("# Projekt: proj", text)
        template = (REPO / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text, template.replace("{{NAME}}", "proj"))
        # Die Karte zeigt danach den Inhalt.
        card = self.agents_card()
        self.wait_until(
            lambda: any(
                "# Projekt: proj" in card.get_by_role("textbox").nth(i).input_value()
                for i in range(max(card.get_by_role("textbox").count(), 1))
            ),
            message="Karte zeigt den neu angelegten Inhalt nicht",
        )

    # ---------- AK8: Web-API ----------

    def test_get_view_and_unknown_post_action_are_rejected(self):
        self.write_agents()
        # GET liefert die Ansicht (AK8, Voraussetzung für die Karte).
        url = self.base + "/api/agents_file?name=proj"
        request = urllib.request.Request(url, headers={"X-Token": self.token})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            view = json.loads(response.read().decode("utf-8"))
        full = BEFORE + BLOCK + AFTER
        self.assertTrue(view["exists"])
        # GH-101: die Ansicht liefert den vollständigen Text; die Felder
        # before/after und managed existieren nur noch für die klassische UI.
        self.assertEqual(view["text"], full)
        self.assertEqual(view["before"], full)
        self.assertEqual(view["after"], "")
        self.assertIsNone(view["managed"])
        self.assertTrue(view["digest"])

        # Unbekannte Aktion wird abgewiesen und ändert die Datei nicht.
        body = json.dumps({"name": "proj", "action": "f31-fremd"}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/agents_file", data=body, method="POST",
            headers={"X-Token": self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertTrue(400 <= status < 500, "unbekannte Aktion wurde nicht abgewiesen")
        self.assertEqual(
            self.agents_path().read_text(encoding="utf-8"), BEFORE + BLOCK + AFTER
        )


# ===========================================================================
# Browserabnahme für den Prüfbutton ``Prüfung package``
# ===========================================================================

import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOT_f312 = SHOTS / "F31-paketpruefung.png"

PACKAGE_MARKER = "paket-pruefung-marker"

# Ambient VIBE_* values would point vibe-web at the productive installation;
# the test must own all runtime paths.

FEEDBACK_f31 = "# FEEDBACK — Test\n\n- [ ] F1 Erster Punkt\n"


class VerifyPackageUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        # Dokumentierte Nutzer-Verdrahtung (AP7-Design, T-V20): Das Dashboard
        # führt VERIFY_PACKAGE unverändert aus. Der autoritative Wert ruft
        # deshalb den verify.sh-Wrapper auf; die Engine führt dann VERIFY_QUICK
        # aus (einzige Prüfschnittstelle).
        wrapper = "bash %s package --project %s" % (
            REPO / "scripts" / "verify.sh", cls.project)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            f'VERIFY_QUICK="echo {PACKAGE_MARKER}"\n'
            'VERIFY_FULL="echo full-pruefung-marker"\n'
            f'VERIFY_PACKAGE="{wrapper}"\n',
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "VIBE_RUNTIME": str(cls.log_dir),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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

    def setUp(self):
        (self.project / "FEEDBACK.md").write_text(FEEDBACK_f31, encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()

    def test_package_button_runs_the_package_check_and_streams_its_output(self):
        self.open_detail()
        arbeit = self.page.locator('[role="tabpanel"][data-panel="arbeit"]')

        # Alle drei Prüfstufen bleiben nebeneinander erreichbar.
        for label in ("Check quick", "Check package", "Check full"):
            self.assertTrue(
                arbeit.get_by_role("button", name=label).is_visible(),
                f"Button {label!r} fehlt in der Projektansicht",
            )

        arbeit.get_by_role("button", name="Check package").click()
        self.wait_until(
            lambda: self.page.locator('[role="tab"][aria-selected="true"]')
            .inner_text()
            .strip()
            == "Output",
            message="Prüfung package wechselte nicht zur Ausgabe",
        )
        self.assertTrue(
            self.page.locator('[role="tabpanel"][data-panel="ausgabe"]').is_visible()
        )
        self.wait_until(
            lambda: PACKAGE_MARKER in self.page.locator("#log").inner_text(),
            message="Ausgabe von VERIFY_QUICK erschien nicht im Ausgabebereich",
        )
        log = self.page.locator("#log").inner_text()
        self.assertIn("verify.sh", log,
                      "Der Paketknopf lief nicht über den verify.sh-Wrapper")
        self.assertNotIn("full-pruefung-marker", log)

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT_f312))
        self.assertTrue(SHOT_f312.exists() and SHOT_f312.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
