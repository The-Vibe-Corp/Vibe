"""Browser-Acceptanztests für die GitHub-Authentifizierung in der Karte
„Git & GitHub" (B7, Nutzer-Feedback).

Das Dashboard läuft wie in den etablierten Browser-Tests (Muster
tests/browser/test_ap06_github_ui.py) als echter Prozess gegen eine temporäre
Werkbank: eigenes VIBE/HOME/VIBE_STATE, freie Ports, Fake-Werkzeuge und eine
GitHub-REST-Fake, die ausschließlich auf 127.0.0.1 lauscht. Kein echter
Netzkontakt: die Projekte tragen file://-Origins bzw. ein sofort scheiterndes
Nicht-GitHub-Remote; github.com wird nie berührt.

Abgedeckte Akzeptanzkriterien (B7 / SPEC „Sicherheit und Datenintegrität"):

* Auth-Block in der Karte sichtbar: Status, Token-Eingabe als Passwortfeld,
  Aktionen „Token speichern" und „Token entfernen".
* token.save/token.clear wirken über die UI (Datei im VIBE_STATE, Antwort
  enthält niemals den Tokeninhalt).
* Fehlgeschlagene Git-Aktionen (fetch/pull/push, pr, import) hinterlegen ihre
  Meldung in der dauerhaften Karten-Fehlerbox (errBox) statt nur als kurz-
  lebiger Toast; sie steht bleibt, bis die nächste Aktion oder ein Erfolg
  sie verdrängt.
* Der Tokeninhalt taucht in keinem UI-Text und in keiner HTTP-Antwort auf.

Ausführen mit:

    python3 -m unittest discover -s tests/browser -p test_b7_github_auth_ui.py -v
"""
import hashlib
import importlib.machinery
import importlib.util
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

from playwright.sync_api import sync_playwright

_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

FAKE_PI = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
if [ "$1" = "--list-models" ]; then
  printf 'anthropic/claude-sonnet\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/model-a\\n'
  exit 0
fi
exit 2
"""

# Test-Token; das Dashboard erhält ihn nie über die Umgebung.
UI_TOKEN = "b7-browser-token-9999xyz"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "VIBE_PROFIL", "VIBE_PROFILE",
)

SAVE_TOKEN = re.compile(r".*(zugangs)?token.*(speichern|hinterlegen).*", re.I)
CLEAR_TOKEN = re.compile(r".*(zugangs)?token.*(entfernen|l[oö]schen).*", re.I)
SETTINGS_SAVE = re.compile(r"^\s*Speichern\s*$")
AUTH_STATUS = re.compile(r"gespeichert|hinterlegt|umgebung", re.I)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def github_module_for_paths():
    """Lädt bin/vibe_github.py im Testprozess (nur für token_state_path())."""
    global _PATHS_MODULE
    if _PATHS_MODULE is None:
        bin_dir = str(REPO / "bin")
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        loader = importlib.machinery.SourceFileLoader(
            "vibe_github_b7_paths", str(REPO / "bin" / "vibe_github.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        loader.exec_module(module)
        _PATHS_MODULE = module
    return _PATHS_MODULE


_PATHS_MODULE = None


def expected_token_path(state, project_dir):
    """Projekt-Token-Ablage (AP9-Vertrag, ersetzt die frühere globale
    Datei): <VIBE_STATE>/github-tokens/<sha256(realpath)[:16]>.json."""
    project = os.path.realpath(str(project_dir))
    digest = hashlib.sha256(project.encode("utf-8")).hexdigest()[:16]
    return Path(state) / "github-tokens" / (digest + ".json")


class FakeGitHubHandler(BaseHTTPRequestHandler):
    """Lokaler GitHub-REST-Vertreter; protokolliert jede Anfrage."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method, body=None):
        self.server.requests.append({
            "method": method,
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
            "body": body,
        })

    def do_GET(self):
        self._record("GET")
        if self.path.startswith("/repos/owner/name/issues"):
            self._respond(200, self.server.issues)
        else:
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else None
        self._record("POST", body)
        self._respond(404, {"message": "Not Found"})


class FakeGitHubServer:
    def __init__(self):
        self.requests = []
        self.issues = [
            {
                "number": 7,
                "title": "Sandbox für Import einschränken",
                "state": "open",
                "html_url": "http://127.0.0.1/owner/name/issues/7",
                "labels": [{"name": "vibe"}],
            },
        ]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHubHandler)
        self.httpd.requests = self.requests
        self.httpd.issues = self.issues
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

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


def git(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True)


def make_project(root, name, extra_env=""):
    """Minimales vibe-Projekt mit Git-Repository und project.env."""
    project = Path(root) / name
    project.mkdir(parents=True)
    git(project, "init", "-q", "-b", "main")
    git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        'TYPE=generic\nTESTER=test-agent\n' + extra_env, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


class GitHubAuthUiTest(unittest.TestCase):
    """B7: Authentifizierung muss über die Github-Karte möglich sein."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, script in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fakebin / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)

        cls.github = FakeGitHubServer().start()

        # Projekt mit funktionierendem file://-Origin und konfigurierbarer
        # Fake-API: alle auth-Aktionen der Karte laufen hier.
        cls.demo = make_project(
            cls.root, "gh-b7-demo",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
                f'GITHUB_API="{cls.github.base}"\n'
                'GITHUB_LABEL="vibe"\n'
            ),
        )
        bare = cls.root / "_bare-demo"
        bare.mkdir()
        bare_env = make_project(cls.root, "_bare-helper")
        git(bare, "init", "-q", "--bare", "-b", "main")
        git(cls.demo, "remote", "add", "origin", "file://" + str(bare))
        git(cls.demo, "push", "-q", "-u", "origin", "main")

        # Projekt mit offizieller API (https://api.github.com): Der pr-Fluss
        # scheitert offline verständlich am fehlenden Token, ohne Netzkontakt.
        cls.official = make_project(
            cls.root, "gh-b7-official",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
            ),
        )
        bare_official = cls.root / "_bare-official"
        bare_official.mkdir()
        git(bare_official, "init", "-q", "--bare", "-b", "main")
        git(cls.official, "remote", "add", "origin", "file://" + str(bare_official))
        git(cls.official, "push", "-q", "-u", "origin", "main")

        # Projekt, dessen einziges Remote sofort scheitert (Verbindung
        # abgewiesen): fetch/pull/push enden mit verständlicher Fehlermeldung.
        cls.broken = make_project(
            cls.root, "gh-b7-broken",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
                f'GITHUB_API="{cls.github.base}"\n'
            ),
        )
        git(cls.broken, "remote", "add", "aux", "http://127.0.0.1:1/x.git")

        cls.token_file = expected_token_path(cls.state, cls.demo)

        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.logs),
            "HOME": str(cls.home),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.fakebin = fakebin
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.logs / "web.token"
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
        cls.web_token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.github.stop()
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
        if self.token_file is not None and self.token_file.exists():
            self.token_file.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()
        if self.token_file is not None and self.token_file.exists():
            self.token_file.unlink()

    # ------------------------------------------------------------ helpers
    def expand_optional(self, selector):
        """AP7-neutral: klapp `<details>`-Abschnitte optional auf."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                assert section.evaluate("el => !!el.open"), \
                    "%s ließ sich nicht aufklappen" % selector

    def open_project_settings(self, name):
        self.page.goto(self.base + "/#t=" + self.web_token)
        self.page.wait_for_selector(".row")
        self.page.locator(".row").filter(has_text=name).first.click()
        self.page.get_by_role("tab", name="Einstellungen").click()
        card = self.git_card()
        self.expand_optional("#github")
        return card

    def git_card(self):
        card = self.page.locator(".card").filter(has_text="Git & GitHub").first
        card.wait_for(state="visible", timeout=15000)
        return card

    def token_exists(self):
        return self.token_file is not None and self.token_file.exists()

    def record(self):
        """Sammelt Response-Objekte für spätere Geheimnisprüfung."""
        collected = []

        def on_response(response):
            collected.append(response)

        self.page.on("response", on_response)
        return collected

    def response_texts(self, collected):
        texts = []
        for response in collected:
            try:
                texts.append({"url": response.url, "body": response.text()})
            except Exception:  # noqa: BLE001 - Binär-/abgebrochene Antworten
                continue
        return texts

    # ------------------------------------------------------------ tests
    def test_auth_block_is_visible_with_password_input_and_both_actions(self):
        card = self.open_project_settings("gh-b7-demo")

        self.assertTrue(
            re.search(r"(zugangs)?token", card.inner_text(), re.IGNORECASE),
            "Die Karte muss einen auth-Block mit Status anzeigen")
        self.assertEqual(
            1, card.locator("input[type='password']").count(),
            "Die Token-Eingabe muss ein Passwortfeld sein")
        names = card.get_by_role("button").all_inner_texts()
        self.assertTrue(
            any(SAVE_TOKEN.match(value) for value in names),
            "Meldung 'Token speichern' fehlt: %s" % (names,))
        self.assertTrue(
            any(CLEAR_TOKEN.match(value) for value in names),
            "Meldung 'Token entfernen' fehlt: %s" % (names,))

    def test_save_then_clear_token_via_ui_persists_without_leaking_secrets(self):
        card = self.open_project_settings("gh-b7-demo")
        collected = self.record()
        self.assertIsNotNone(
            self.token_file,
            "token_state_path() liefert keinen Pfad (Schnittstelle fehlt)")

        card.locator("input[type='password']").first.fill(UI_TOKEN)
        save_button = card.get_by_role("button", name=SAVE_TOKEN).first
        save_button.click()

        deadline = time.time() + 15
        while time.time() < deadline:
            if self.token_file.exists():
                break
            time.sleep(0.2)
        self.assertTrue(self.token_file.exists(),
                        "Der gespeicherte Projekt-Token fehlt im VIBE_STATE "
                        "(github-tokens/<hash>.json)")
        with open(self.token_file, encoding="utf-8") as handle:
            stored = handle.read()
        self.assertNotIn(UI_TOKEN, stored,
                         "Die Ablage ist verschlüsselt: kein Klartext-Token")

        self.page.wait_for_timeout(500)
        card = self.git_card()
        self.assertTrue(AUTH_STATUS.search(card.inner_text()),
                        "Die Karte muss den gespeicherten Zustand anzeigen: %s"
                        % (card.inner_text()[:400],))

        card.get_by_role("button", name=CLEAR_TOKEN).first.click()
        deadline = time.time() + 15
        while time.time() < deadline and self.token_exists():
            time.sleep(0.2)
        self.assertFalse(self.token_exists(),
                         "token.clear über die UI löscht die Datei")

        self.page.wait_for_timeout(500)
        texts = [entry["body"] for entry in self.response_texts(collected)]
        for body in texts:
            self.assertNotIn(UI_TOKEN, body,
                             "Eine Antwort enthielt den Tokeninhalt: %r" % body[:200])
        self.assertNotIn(UI_TOKEN, self.page.inner_text("body"))

    def test_failed_git_actions_leave_persistent_message_in_card_error_box(self):
        card = self.open_project_settings("gh-b7-broken")

        for action in (r".*(fetch|abrufen).*", r".*pull.*", r".*push.*"):
            with self.subTest(action=action):
                button = card.get_by_role("button", name=re.compile(action, re.I)).first
                button.click()
                box = card.locator(".bad").first
                box.wait_for(state="visible", timeout=15000)
                self.assertTrue(box.inner_text().strip(),
                                "Die Karten-Fehlerbox zeigt die Meldung nicht")
                self.page.wait_for_timeout(2200)
                self.assertTrue(box.is_visible(),
                                "Die Meldung muss in der bleiben, nicht nur "
                                "als kurzer Toast")
                self.assertTrue(box.inner_text().strip(),
                                "Die Fehlerbox-Meldung verschwand zu früh")

    def test_merge_request_failure_shows_token_guidance_and_clears_after_success(self):
        card = self.open_project_settings("gh-b7-official")

        pr_button = card.get_by_role(
            "button", name=re.compile(r"Merge-Request|Merge Request", re.I)).first
        pr_button.click()
        group = card.locator(".confirm, [role='group']").first
        group.wait_for(state="visible", timeout=5000)
        group.get_by_role("button", name=re.compile(r"Ja|Bestätigen", re.I)).first.click()

        box = card.locator(".bad").first
        box.wait_for(state="visible", timeout=15000)
        self.assertTrue(
            re.search(r"token|zugangs", box.inner_text(), re.IGNORECASE),
            "Die Fehlermeldung muss zur Token-Hinterlegung führen: %s"
            % (box.inner_text(),))
        self.page.wait_for_timeout(2200)
        self.assertTrue(box.is_visible() and box.inner_text().strip(),
                        "Die Fehlerbox-Meldung muss stehen bleiben")

        card = self.git_card()
        card.get_by_role("button", name=SETTINGS_SAVE).first.click()
        self.page.wait_for_timeout(1000)
        card = self.git_card()
        boxes = card.locator(".bad")
        for index in range(boxes.count()):
            self.assertFalse(boxes.nth(index).inner_text().strip(),
                             "Die nächste erfolgreiche Aktion muss die "
                             "Fehlerbox leeren")

    def test_no_token_content_in_any_api_response(self):
        card = self.open_project_settings("gh-b7-demo")
        collected = self.record()

        self.assertIsNotNone(
            self.token_file,
            "token_state_path() liefert keinen Pfad (Schnittstelle fehlt)")
        card.locator("input[type='password']").first.fill(UI_TOKEN)
        card.get_by_role("button", name=SAVE_TOKEN).first.click()
        deadline = time.time() + 15
        while time.time() < deadline and not self.token_file.exists():
            time.sleep(0.2)
        card = self.git_card()
        card.get_by_role("button", name=CLEAR_TOKEN).first.click()
        deadline = time.time() + 15
        while time.time() < deadline and self.token_exists():
            time.sleep(0.2)
        self.assertFalse(self.token_exists())
        self.page.wait_for_timeout(500)

        github_payloads = 0
        for entry in self.response_texts(collected):
            self.assertNotIn(UI_TOKEN, entry["body"],
                             "Antwort %s enthielt den Tokeninhalt" % entry["url"])
            if "/api/github" in entry["url"]:
                github_payloads += 1
        self.assertGreaterEqual(
            github_payloads, 2,
            "Die token-save/clear-Aktionen müssen über /api/github laufen "
            "und in keinen Antworten das Geheimnis tragen")

    def test_fetch_failure_message_never_contains_a_stored_token(self):
        self.assertIsNotNone(
            self.token_file,
            "token_state_path() liefert keinen Pfad (Schnittstelle fehlt)")
        self.token_file.parent.mkdir(exist_ok=True)
        self.token_file.write_text(UI_TOKEN, encoding="utf-8")
        card = self.open_project_settings("gh-b7-broken")

        card.get_by_role("button", name=re.compile(r".*(fetch|abrufen).*", re.I)).first.click()
        box = card.locator(".bad").first
        box.wait_for(state="visible", timeout=15000)

        self.assertNotIn(UI_TOKEN, self.page.inner_text("body"),
                         "Der gespeicherte Tokeninhalt taucht in der "
                         "Oberfläche auf")


    # -------------------------------------------- Review-Befund: Serverquelle
    def start_token_dashboard(self, extra_env):
        """Startet ein zweites Dashboard mit eigener Prozessumgebung.

        Vor allem für die Umwelt-Token-Prüfung nötig: token_status() gewinnt
        'umgebung' im laufenden Serverprozess; ein SharedPreferences-Shim oder
        Fakt-Token-Anfrage ist dafür kein Ersatz (die Liste der Umgebung
        entscheidet, nicht die UI).
        """
        cls = type(self)
        state = cls.root / "_state-envtoken"
        state.mkdir(exist_ok=True)
        runtime = cls.root / "_logs-envtoken"
        runtime.mkdir(exist_ok=True)
        port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(port),
            "VIBE_STATE": str(state),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(runtime),
            "HOME": str(cls.home),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        env.update(extra_env)
        if cls.token_file is not None and cls.token_file.exists():
            cls.token_file.unlink()
        proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = runtime / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        break
                except OSError:
                    pass
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise AssertionError(
                    "vibe-web (Umgebungstoken) wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            proc.terminate()
            raise AssertionError("Dashboard mit Umgebungstoken nicht erreichbar")
        return port, token_file.read_text(encoding="utf-8").strip(), proc, state

    def test_auth_line_follows_the_server_source_after_save_and_clear(self):
        """Review-Befund 'statische Auth-Quelle': Die Statuszeile (authLine)
        muss nach token.save/token.clear die Serverinformation extra["auth"]
        {set, source} übernehmen (bin/vibe-web.py /api/github, token.save/
        token.clear), nicht hartkodiert 'gespeichert'/''. Das Dashboard dieses
        Falls trägt GITHUB_TOKEN im Prozess-ENV: der Server meldet
        auth.set=True mit source="umgebung" — nach beiden Aktionen muss die
        Zeile 'Zugang über die Umgebung' zeigen.
        Determinismus: Der Server-Erfolg jeder Aktion wird über den
        Zustandsnachweis belegt (Token-Datei erscheint/verschwindet im
        zuständigen VIBE_STATE), bevor die Zeile in einem Beobachtungsfenster
        ausgelesen wird — so kann die hartkodierte Anzeige dem Auslesen
        nicht durch ein Zeitrennen entgehen."""
        port, login_token, proc, state = self.start_token_dashboard(
            {"GITHUB_TOKEN": "b7-fake-env"})
        token_path = expected_token_path(state, type(self).demo)
        self.assertIsNotNone(
            token_path, "token_state_path() liefert keinen Pfad")
        page = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            base_url = f"http://127.0.0.1:{port}"
            page.goto(base_url + "/#t=" + login_token)
            page.wait_for_selector(".row")
            page.locator(".row").filter(has_text="gh-b7-demo").first.click()
            page.get_by_role("tab", name="Einstellungen").click()
            card = page.locator(".card").filter(has_text="Git & GitHub").first
            card.wait_for(state="visible", timeout=15000)
            summary = page.locator("#github > summary")
            if summary.count():
                page.locator("#github").first.evaluate(
                    "el => el.scrollIntoView({block: 'center'})")
                summary.click()

            auth_line = card.locator("[data-auth]").first
            auth_line.wait_for(state="visible", timeout=10000)
            initial_text = auth_line.inner_text()
            self.assertNotIn(
                "Kein Token hinterlegt", initial_text,
                "Der Server meldet Umgebungszugriff; die Startzeile zeigt ihn "
                "nicht: %r" % initial_text)
            self.assertTrue(
                re.search(r"umgebung", initial_text, re.IGNORECASE),
                "Initialzeile muss 'Zugang über die Umgebung' zeigen: %r"
                % initial_text)

            def wait_token_state(present, description):
                deadline = time.time() + 15.0
                while time.time() < deadline:
                    if token_path.exists() == present:
                        return
                    time.sleep(0.1)
                raise AssertionError(
                    "Server-Erfolg unbelegt: %s (Token-Datei %s nach 15 s)"
                    % (description, "erscheint nicht" if present
                       else "verschwindet nicht"))

            def observe_line(seconds, description):
                """Zeile für ein Fenster auslesen und alle Texte zurückgeben."""
                collected = []
                deadline = time.time() + seconds
                while time.time() < deadline:
                    try:
                        text = card.locator("[data-auth]").first.inner_text()
                    except Exception:  # noqa: BLE001 — Zeile kann umbauen
                        text = ""
                    collected.append(text)
                    time.sleep(0.1)
                self.assertTrue(
                    collected, "Beobachtungsfenster leer (%s)" % description)
                return collected

            # --- token.save: Server bestätigt (Datei erscheint), Zeile muss
            #     die Serverquelle 'umgebung' tragen, nie 'gespeichert'.
            card.locator("input[type='password']").first.fill(UI_TOKEN)
            card.get_by_role("button", name=SAVE_TOKEN).first.click()
            wait_token_state(True, "token.save hat den Token gespeichert")
            texts_after_save = observe_line(
                2.5, "nach token.save")
            for text in texts_after_save:
                self.assertNotIn(
                    "gespeichert", text,
                    "token.save zeigt die Quelle hartkodiert statt der "
                    "Serverquelle 'umgebung': %r" % text)
                self.assertNotIn(
                    "Kein Token hinterlegt", text,
                    "token.save hat die Anzeige geleert: %r" % text)
            self.assertTrue(
                all(re.search(r"umgebung", t, re.IGNORECASE)
                    for t in texts_after_save),
                "Die Auth-Zeile muss nach token.save durchgehend die "
                "Serverquelle 'umgebung' zeigen (setAuth(r.auth && "
                "r.auth.set ? r.auth.source : '')): %r" % texts_after_save)

            # --- token.clear: Server bestätigt (Datei verschwindet), Zeile
            #     muss die Serverquelle 'umgebung' tragen, nie ''.
            card = page.locator(".card").filter(has_text="Git & GitHub").first
            card.get_by_role("button", name=CLEAR_TOKEN).first.click()
            wait_token_state(False, "token.clear hat den Token entfernt")
            texts_after_clear = observe_line(
                2.5, "nach token.clear")
            for text in texts_after_clear:
                self.assertNotIn(
                    "Kein Token hinterlegt", text,
                    "token.clear setzt die Anzeige auf '' statt der "
                    "Serverquelle 'umgebung': %r" % text)
                self.assertNotIn(
                    "gespeichert", text,
                    "Nach token.clear bleibt eine falsche Quelle stehen: %r"
                    % text)
            self.assertTrue(
                all(re.search(r"umgebung", t, re.IGNORECASE)
                    for t in texts_after_clear),
                "Die Auth-Zeile muss nach token.clear durchgehend die "
                "Serverquelle 'umgebung' zeigen (setAuth(r.auth && "
                "r.auth.set ? r.auth.source : '')): %r" % texts_after_clear)
        finally:
            page.close()
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if proc.stdout:
                proc.stdout.close()
            token_path_final = expected_token_path(state, type(self).demo)
            if token_path_final is not None and token_path_final.exists():
                token_path_final.unlink()




if __name__ == "__main__":
    unittest.main()
