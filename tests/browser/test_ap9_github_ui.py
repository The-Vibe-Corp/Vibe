"""Browser acceptance tests for the AP9 „Bereit für Github Teil 3“ UI.

Geprüfte Anforderungen (AP9, TICKETS.md; abgeleitet unabhängig von der
Implementierung):

* Die Token-Zeile nennt „für dieses Projekt gespeichert (verschlüsselt)“,
  wenn der Token als Projekt-Token hinterlegt ist (source „projekt“).
* Ein Knopf „Verbindung testen“ zeigt eine Ergebniszeile mit ok/fehler-
  Kennzeichnung — ohne echten Netzkontakt zu github.com.
* Jede Branch-Zeile bietet „Wechseln“ und „Push“; beide Aktionen wirken
  wirklich (Arbeitsbaum wechselt; Fern-Ref wird aktualisiert).
* Ein Einstellungsfeld „Basis-Branch für Merge-Requests“ persistiert
  GITHUB_BASE in der project.env.

Das Dashboard läuft als echter Prozess gegen eine Fake-Toolchain in einem
temporären Verzeichnis (Muster tests/browser/test_ap06_github_ui.py).
GitHub-REST geht nur an einen lokalen Fake auf 127.0.0.1; Git läuft gegen
lokale Bare-Repositories (file://). Keine produktiven Pfade, keine
Geheimnisse, keine Modellaufrufe.

Run:

    python3 -m unittest tests.browser.test_ap9_github_ui -v
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
exit 2
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
exit 2
"""

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
)

PROJECT_TOKEN = "ap9-ui-projekt-token-555"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeGitHubHandler(BaseHTTPRequestHandler):
    """Lokaler REST-Stand-in; github.com wird nie kontaktiert."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/repos/owner/name"):
            self._respond(200, {"full_name": "owner/name"})
        else:
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._respond(201, {"number": 42,
                            "html_url": "http://127.0.0.1/pull/42"})


class FakeGitHubServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHubHandler)
        self.thread = __import__("threading").Thread(
            target=self.httpd.serve_forever, daemon=True)

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
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60)


def git_out(cwd, *argv):
    return git(cwd, *argv).stdout.strip()


def make_project(root, name, extra_env=""):
    """Minimales vibe-Projekt mit Git-Repository und project.env."""
    project = root / name
    project.mkdir(parents=True)
    git(project, "init", "-q", "-b", "main")
    git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n" + extra_env, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


def wait_for_file_content(path, needle, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if needle in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            pass
        time.sleep(0.1)
    return False


def wait_for_toast(page, pattern, timeout=15.0):
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        texts = []
        for toast in page.locator(".toast").all():
            try:
                texts.append(toast.inner_text())
            except Exception:  # noqa: BLE001 - Toast kann verschwinden
                pass
        if texts:
            last = texts
        for value in texts:
            if re.search(pattern, value, re.IGNORECASE):
                return value
        time.sleep(0.1)
    raise AssertionError(
        "kein Toast passend zu %r; zuletzt gesehen: %r" % (pattern, last))


def http_request(port, method, path, body=None, token=None):
    import http.client
    headers = {}
    if token:
        headers["X-Token"] = token
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


class GitHubCardAP9UiTest(unittest.TestCase):
    """Die Git & GitHub-Karte trägt die AP9-Steuerung und das Feedback."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1",
                        "installed_at": "2026-11-07"}),
            encoding="utf-8",
        )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)

        cls.github = FakeGitHubServer().start()

        # Projekt mit funktionierender Verknüpfung: origin (file://),
        # GitHub-Fake und einem zweiten lokalen Branch für „Wechseln“.
        cls.project_env = make_project(
            cls.root, "gh-ok",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
                f'GITHUB_API="{cls.github.base}"\n'
                'GITHUB_LABEL="vibe"\n'
            ),
        )
        cls.env_file = cls.project_env / ".vibe" / "project.env"
        bare = cls.root / "_origin-bare"
        bare.mkdir()
        git(bare, "init", "-q", "--bare")
        git(cls.project_env, "remote", "add", "origin", "file://" + str(bare))
        git(cls.project_env, "push", "-q", "-u", "origin", "main")
        git(cls.project_env, "branch", "feature/arbeit")
        cls.bare_path = bare

        # Projekt mit absichtlich kaputter API-Adresse (Loopback, kein Dienst):
        cls.bad_env = make_project(
            cls.root, "gh-bad",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
                'GITHUB_API="http://127.0.0.1:9"\n'
                'GITHUB_LABEL="vibe"\n'
            ),
        )
        bad_bare = cls.root / "_origin-bare-bad"
        bad_bare.mkdir()
        git(bad_bare, "init", "-q", "--bare")
        git(cls.bad_env, "remote", "add", "origin", "file://" + str(bad_bare))
        git(cls.bad_env, "push", "-q", "-u", "origin", "main")

        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.toolchain),
            "VIBE_INSTALL": str(cls.toolchain),
            "VIBE_RUNTIME": str(cls.logs),
            "HOME": str(cls.home),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
        })
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
                raise AssertionError("vibe-web exited early: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web is not reachable")
        cls.token = token_file.read_text(encoding="utf-8").strip()
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
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------ helpers
    def save_project_token_via_api(self, name, token=PROJECT_TOKEN):
        status, text = http_request(
            self.port, "POST", "/api/github",
            body={"name": name, "action": "token.save", "token": token},
            token=self.token)
        self.assertEqual(200, status, text)
        self.assertNotIn(token, text, "Die Antwort darf den Token nie echoen")

    def expand_optional(self, selector):
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                assert section.evaluate("el => !!el.open"), \
                    "%s ließ sich nicht aufklappen" % selector

    def open_project_settings(self, name):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.wait_for_selector(".row")
        self.page.locator(".row").filter(has_text=name).first.click()
        self.page.get_by_role("tab", name="Settings").click()
        card = self.git_card()
        self.expand_optional("#github")
        return card

    def git_card(self):
        card = self.page.locator(".card").filter(has_text="Git & GitHub").first
        card.wait_for(state="visible", timeout=15000)
        return card

    def expand_details(self, card, label):
        """Klappt den Abschnitt mit dem Label auf (B7-Vererbung: Branch-
        Zeilen können in einem zugeklappten <details> liegen) und liefert
        den geöffneten Abschnitt."""
        for section in card.locator("details").all():
            try:
                summary = section.locator("summary").first
                # textContent (statt inner_text): auch bei versteckten
                # Elementen lesbar, z. B. innerhalb eines zugeklappten
                # Eltern-<details>.
                if label.lower() not in (
                        summary.evaluate("el => el.textContent || ''")
                        or "").lower():
                    continue
            except Exception:  # noqa: BLE001 - Abschnitt kann verschwinden
                continue
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
            assert section.evaluate("el => !!el.open"), (
                "Abschnitt %r ließ sich nicht aufklappen" % label)
            return section
        self.fail("Kein aufklappbarer Abschnitt %r in der Karte" % label)

    def reopen_branches(self, label="Branches", timeout=15.0):
        """Öffnet den Branches-Abschnitt erneut; nach Aktionen rendert die
        Karte neu, das <details> ist dann weg oder zugeklappt."""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                # Nach Aktionen rendert die Karte neu und klappt dabei auch
                # den übergeordneten GitHub-Abschnitt zu: erst den wieder
                # aufklappen, dann den Branches-Abschnitt suchen.
                self.expand_optional("#github")
                return self.expand_details(self.git_card(), label)
            except AssertionError as error:
                last = error
                time.sleep(0.3)
        raise last

    def button_in_row(self, section, row_text, button_name):
        """Liefert den Knopf ``button_name`` in der Zeile, die ``row_text``
        enthält (Zeile = nächster Vorfahre mit passendem Text)."""
        buttons = section.get_by_role("button", name=button_name)
        needle = row_text.replace("'", "\\'")
        for index in range(buttons.count()):
            hit = buttons.nth(index).evaluate(
                "el => { let e = el.parentElement;"
                " while (e) { if ((e.innerText || '').includes('"
                + needle + "')) return true; e = e.parentElement; }"
                " return false; }")
            if hit:
                return buttons.nth(index)
        self.fail("Kein Knopf %r in einer Zeile mit %r" % (button_name, row_text))

    def marking_of(self, line):
        """CSS-Kennung der Ergebniszeile (am Element oder am nächsten
        Vorfahren mit class-Attribut)."""
        element = line.first
        classes = element.get_attribute("class") or ""
        if classes.strip():
            return classes
        return element.evaluate(
            "el => { const e = el.closest('[class]');"
            " return e ? (e.getAttribute('class') || '') : ''; }")

    def connection_result_line(self, card):
        """Ergebniszeile des Verbindungstests („Verbindung: …“) — der
        Doppelpunkt unterscheidet sie vom Knopf „Verbindung testen“."""
        line = card.locator("text=/Verbindung:|Connection:/").last
        line.wait_for(state="visible", timeout=20000)
        return line

    # ------------------------------------------------------------ tests
    def test_connection_test_button_shows_an_ok_result_line(self):
        """AK UI-Feedback: „Verbindung testen“ meldet das Ergebnis in der Karte."""
        self.save_project_token_via_api("gh-ok")
        card = self.open_project_settings("gh-ok")

        button = card.get_by_role(
            "button", name=re.compile(r"Verbindung testen|Test connection", re.I))
        self.assertEqual(button.count(), 1, "Knopf „Verbindung testen“ fehlt")
        button.click()

        line = self.connection_result_line(card)
        text = line.inner_text()
        self.assertTrue(text.strip(), "Ergebniszeile braucht einen Text")
        self.assertRegex(text, re.compile(r"OK|erreichbar|funktioniert|Erfolg",
                                          re.I), text)
        classes = self.marking_of(line)
        self.assertRegex(classes, re.compile(r"ok|good|success", re.I),
                         "Erfolgszeile ohne ok-Kennung: %r" % classes)

    def test_connection_test_shows_a_distinct_error_marking(self):
        """AK UI-Feedback: Fehler werden als Fehler gekennzeichnet (Klasse)."""
        self.save_project_token_via_api("gh-bad")
        card = self.open_project_settings("gh-bad")

        button = card.get_by_role(
            "button", name=re.compile(r"Verbindung testen|Test connection", re.I))
        self.assertEqual(button.count(), 1)
        button.click()

        line = self.connection_result_line(card)
        text = line.inner_text()
        self.assertTrue(text.strip(), "Ergebniszeile braucht einen Text")
        self.assertRegex(
            text, re.compile(r"Fehler|nicht|scheitert|fehl|ERROR|not|fail", re.I), text)
        # Farb-/Zustandskennung: die Fehlerkennung unterscheidet sich von der
        # Erfolgsdarstellung (eigene CSS-Klasse erwartet).
        classes = self.marking_of(line)
        self.assertNotEqual("", classes.strip(),
                            "Die Ergebniszeile braucht eine ok/fehler-Kennung")
        self.assertTrue(
            re.search(r"err|fail|bad|fehler", classes, re.I),
            "Ergebniszeile ohne erkennbare Fehlerkennung: %r" % classes)

    def test_token_line_names_the_encrypted_project_storage(self):
        """AK Token je Projekt: die Token-Zeile nennt die verschlüsselte
        projektbezogene Ablage."""
        self.save_project_token_via_api("gh-ok")
        card = self.open_project_settings("gh-ok")

        text = card.inner_text()

        self.assertRegex(
            text,
            re.compile(r"(für dieses Projekt gespeichert \(verschlüsselt\)"
                       r"|saved for this project \(encrypted\))"),
            "Token-Zeile muss die projektspezifische verschlüsselte "
            "Ablage benennen; Karte: %r" % text[:400])
        self.assertNotIn(PROJECT_TOKEN, text)

    def test_branch_rows_offer_wechseln_and_push_and_they_work(self):
        """AK Branch-Kontrolle: jede Branch-Zeile bietet Wechseln und Push."""
        card = self.open_project_settings("gh-ok")
        branches = self.expand_details(card, "Branches")

        wechseln = branches.get_by_role(
            "button", name=re.compile(r"^\s*(Wechseln|Switch)\s*$", re.I))
        push = branches.get_by_role("button", name=re.compile(r"^\s*Push\s*$", re.I))
        self.assertGreaterEqual(wechseln.count(), 1,
                                "Kein „Wechseln“-Knopf je Branch-Zeile")
        self.assertGreaterEqual(push.count(), 1, "Kein „Push“-Knopf je Zeile")

        # „Wechseln“ auf feature/arbeit wechselt den Arbeitsbaum wirklich:
        self.button_in_row(branches, "feature/arbeit",
                           re.compile(r"^\s*(Wechseln|Switch)\s*$", re.I)).click()
        wait_for_toast(self.page, r"wechsel|Branch", timeout=15000)
        deadline = time.time() + 10
        while time.time() < deadline:
            if git_out(self.project_env, "rev-parse", "--abbrev-ref",
                       "HEAD") == "feature/arbeit":
                break
            time.sleep(0.2)
        self.assertEqual("feature/arbeit",
                         git_out(self.project_env, "rev-parse",
                                 "--abbrev-ref", "HEAD"),
                         "„Wechseln“ hat den Arbeitsbaum nicht gewechselt")

        # Der Wechsel rendert die Karte neu: den Branches-Abschnitt erneut
        # aufklappen (kurz warten, bis die Karte wieder gerendert ist).
        branches = self.reopen_branches()

        # „Push“ auf der Feature-Zeile überträgt den Zweig zur origin:
        tip = git_out(self.project_env, "rev-parse", "feature/arbeit")
        self.button_in_row(branches, "feature/arbeit",
                           re.compile(r"^\s*Push\s*$", re.I)).click()
        wait_for_toast(self.page, r"übertragen|Push|origin", timeout=15000)
        remote_tip = git_out(self.project_env, "ls-remote", "origin",
                             "refs/heads/feature/arbeit").split()[0]
        self.assertEqual(tip, remote_tip, "„Push“ hat den Zweig nicht gesendet")

    def test_base_branch_setting_is_persisted_in_the_project_env(self):
        """AK Merge-Request-Ziel: Feld „Basis-Branch für Merge-Requests“."""
        card = self.open_project_settings("gh-ok")

        field = card.locator(
            "input[aria-label*='Basis-Branch'], "
            "input[aria-label*='Base branch'], "
            "input[placeholder*='Basis-Branch']")
        self.assertEqual(field.count(), 1,
                         "Einstellungsfeld „Basis-Branch für Merge-Requests“ fehlt")
        field.fill("main")

        card.get_by_role("button", name="Save", exact=True).click()
        self.assertTrue(
            wait_for_file_content(self.env_file, 'GITHUB_BASE="main"'),
            "GITHUB_BASE wurde nicht in die project.env gespeichert")


if __name__ == "__main__":
    unittest.main()
