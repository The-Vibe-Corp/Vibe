"""GitHub-Oberfläche: Karte, Verknüpfung, Checkout und Anmeldung.

Aufruf: python3 -m unittest tests.browser.test_github_ui -v
"""


# ===========================================================================
# Browser acceptance tests for the Git & GitHub card in the dashboard
# ===========================================================================

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

# Installed developer dependency: Chromium is read-only from the user cache
# (same pattern as scripts/verify.py); never downloaded inside a test.
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

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeGitHubHandler(BaseHTTPRequestHandler):
    """Local GitHub REST stand-in, shared by all browser tests."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method, body):
        self.server.requests.append({"method": method, "path": self.path, "body": body})

    def do_GET(self):
        self._record("GET", None)
        if self.path.startswith("/repos/owner/name/issues"):
            self._respond(200, self.server.issues)
        else:
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._record("POST", body.decode("utf-8") if body else None)
        if self.path.startswith("/repos/owner/name/pulls"):
            self.server.pr_posts.append(self.server.requests[-1])
            self._respond(self.server.pr_status, self.server.pr_payload)
        else:
            self._respond(404, {"message": "Not Found"})


class FakeGitHubServer:
    """Fake API bound to 127.0.0.1; tests inspect every recorded request."""

    def __init__(self):
        self.requests = []
        self.pr_posts = []
        self.issues = [
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
        self.pr_status = 201
        self.pr_payload = {
            "number": 42,
            "html_url": "http://127.0.0.1/owner/name/pull/42",
        }
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHubHandler)
        self.httpd.requests = self.requests
        self.httpd.pr_posts = self.pr_posts
        self.httpd.issues = self.issues
        self.httpd.pr_status = self.pr_status
        self.httpd.pr_payload = self.pr_payload
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


def git_out(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_project(root, name, extra_env=""):
    """Creates a minimal vibe project with git repo and project.env."""
    project = root / name
    project.mkdir(parents=True)
    git(project, "init", "-q", "-b", "main")
    git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        'TYPE=generic\nTESTER=test-agent\n' + extra_env, encoding="utf-8"
    )
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
    """Wartet, bis ein Toast-Text das Muster enthält.

    Toasts verschwinden automatisch nach ca. 8 s; die Fehlermeldung zeigt
    deshalb die letzten gesehenen nicht-leeren Meldungen.
    """
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        texts = []
        for toast in page.locator(".toast").all():
            try:
                texts.append(toast.inner_text())
            except Exception:  # noqa: BLE001 - Toast kann zwischenzeitlich verschwinden
                pass
        if texts:
            last = texts
        for value in texts:
            if re.search(pattern, value, re.IGNORECASE):
                return value
        time.sleep(0.1)
    raise AssertionError("kein Toast passend zu %r; zuletzt gesehen: %r" % (pattern, last))


class GitHubCardUiTest(unittest.TestCase):
    """The project detail page must expose the Git & GitHub card (AP6)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1", "installed_at": "2026-11-07"}),
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

        # Fake GitHub API has to exist before the dashboard reads its config.
        cls.github = FakeGitHubServer().start()
        cls.fg_port = free_port()

        # Enabled project with a real local git origin (file://).
        cls.project_env = make_project(
            cls.root, "gh-demo",
            extra_env=(
                'GITHUB_ENABLED="1"\n'
                'GITHUB_REPO="owner/name"\n'
                f'GITHUB_API="{cls.github.base}"\n'
                'GITHUB_LABEL="vibe"\n'
            ),
        )
        cls.env_file = cls.project_env / ".vibe" / "project.env"
        cls.tickets_file = cls.project_env / "TICKETS.md"
        bare = cls.root / "_origin-bare"
        bare.mkdir()
        git(bare, "init", "-q", "--bare")
        git(cls.project_env, "remote", "add", "origin", "file://" + str(bare))
        git(cls.project_env, "push", "-q", "-u", "origin", "main")

        # Second project without any GitHub configuration (optional feature).
        cls.project_off = make_project(cls.root, "gh-off")
        cls.off_env = cls.project_off / ".vibe" / "project.env"

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
    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Abschnitt auf, falls er als <details>
        umgesetzt ist. Auf der Bestandsstruktur bleibt der Aufruf ein No-op."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                assert section.evaluate("el => !!el.open"), \
                    "%s ließ sich nicht aufklappen" % selector

    def open_project_settings(self, name):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector(".row")
        self.page.locator(".row").filter(has_text=name).first.click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        card = self.git_card()
        self.expand_optional("#github")
        return card

    def git_card(self):
        card = self.page.locator(".card").filter(has_text="Git & GitHub").first
        card.wait_for(state="visible", timeout=15000)
        return card

    def input_with_value(self, card, value):
        inputs = card.locator("input")
        for index in range(inputs.count()):
            field = inputs.nth(index)
            if field.input_value() == value:
                return field
        self.fail(
            f"kein Eingabefeld mit Wert {value!r} in der Git & GitHub-Karte gefunden"
        )

    # ------------------------------------------------------------ tests
    def test_git_card_shows_settings_fields_and_saved_state(self):
        card = self.open_project_settings("gh-demo")

        checkbox = card.locator("input[type='checkbox']")
        self.assertEqual(checkbox.count(), 1)
        self.assertTrue(checkbox.is_checked())
        self.input_with_value(card, "owner/name")   # repository field (owner/name)
        self.input_with_value(card, "vibe")          # label field

    def test_github_link_button_keeps_dot_in_the_repository_name(self):
        """R2-1/Medium über die UI: Verknüpfen mit owner/my.repo überträgt den
        vollen Slug in project.env (eigenes Projekt, gh-demo bleibt unberührt)."""
        project = make_project(self.root, "gh-dot")
        env_file = project / ".vibe" / "project.env"
        card = self.open_project_settings("gh-dot")
        repo = card.locator("input[placeholder='owner/name']").first

        repo.fill("owner/my.repo")
        card.get_by_role("button", name=re.compile(r"Link with GitHub", re.I)).click()
        wait_for_toast(self.page, r"Verknüpfung (gespeichert|saved)")

        self.assertTrue(
            wait_for_file_content(env_file, 'GITHUB_REPO="owner/my.repo"'),
            "Der Punkte-Slug wurde nicht ohne manuelles Nachladen gespeichert",
        )
        self.assertIn('GITHUB_ENABLED="1"', env_file.read_text(encoding="utf-8"))
        self.assertTrue(
            self.page.locator(".card").filter(has_text="Git & GitHub").first.is_visible()
        )

    def test_settings_changed_in_the_card_are_persisted_without_manual_reload(self):
        card = self.open_project_settings("gh-demo")
        repo = self.input_with_value(card, "owner/name")

        repo.fill("owner/renamed")
        card.get_by_role("button", name=re.compile(r"^Save$", re.I)).click()
        self.assertTrue(
            wait_for_file_content(self.env_file, 'GITHUB_REPO="owner/renamed"'),
            "Einstellung wurde nicht ohne manuelles Nachladen gespeichert",
        )
        # The card stays in place; no full page Replacement.

        card = self.page.locator(".card").filter(has_text="Git & GitHub").first
        self.assertTrue(card.is_visible())
        text = self.env_file.read_text(encoding="utf-8")
        self.assertIn('TESTER=test-agent', text)
        self.assertIn('GITHUB_ENABLED="1"', text)

    def test_import_adds_vibe_issues_to_tickets_and_keeps_bugs_out(self):
        self.open_project_settings("gh-demo")

        self.tickets_file.write_text("# TICKETS\n", encoding="utf-8")
        card = self.git_card()
        card.locator("text=Issues").first.wait_for(state="visible", timeout=10000)
        card.get_by_role("button", name=re.compile("Import", re.I)).click()
        self.assertTrue(
            wait_for_file_content(self.tickets_file, "- [ ] GH-7"),
            "Der Import hat GH-7 nicht in TICKETS.md eingetragen",
        )
        text = self.tickets_file.read_text(encoding="utf-8")
        self.assertNotIn("GH-8", text)
        self.assertIn("Sandbox für Import einschränken", text)

    def test_merge_request_asks_confirm_and_only_then_sends_action(self):
        card = self.open_project_settings("gh-demo")
        pr_button = card.get_by_role(
            "button", name=re.compile(r"Merge-Request|Merge Request", re.I)
        )
        self.assertEqual(pr_button.count(), 1)

        # First click asks for confirmation; no API action happens, no error yet.
        pr_button.click()
        group = card.locator(".confirm, [role='group']").first
        group.wait_for(state="visible", timeout=5000)
        self.assertEqual(self.github.pr_posts, [])
        texts = group.get_by_role("button").all_inner_texts()
        self.assertTrue(any(re.search(r"^Yes", t, re.I) for t in texts), texts)
        self.assertTrue(any(re.search(r"Cancel", t, re.I) for t in texts), texts)
        self.assertEqual(self.page.locator(".toast").count(), 0)

        # Cancel sends nothing at all.
        group.get_by_role("button", name=re.compile(r"Cancel", re.I)).click()
        self.assertEqual(card.locator(".confirm, [role='group']").count(), 0)
        self.assertEqual(self.github.pr_posts, [])
        self.assertEqual(self.page.locator(".toast").count(), 0)

        # Confirming is what actually throws the error message (no token here).
        pr_button.click()
        group = card.locator(".confirm, [role='group']").first
        group.wait_for(state="visible", timeout=5000)
        group.get_by_role("button", name=re.compile(r"^Yes", re.I)).first.click()
        toast = self.page.locator(".toast").first
        toast.wait_for(state="visible", timeout=15000)
        self.assertRegex(toast.inner_text(), re.compile(r"Kein GitHub|Fehler|Error", re.I))
        self.assertEqual(self.github.pr_posts, [])
        self.assertTrue(self.git_card().is_visible())

    def test_disabled_project_shows_the_card_without_merge_request(self):
        card = self.open_project_settings("gh-off")

        checkbox = card.locator("input[type='checkbox']")
        self.assertEqual(checkbox.count(), 1)
        self.assertFalse(checkbox.is_checked())
        self.assertEqual(
            card.get_by_role("button", name=re.compile(r"Merge-Request|Merge Request", re.I)).count(),
            0,
        )

    def test_branch_overview_and_fetch_pull_actions_are_visible(self):
        card = self.open_project_settings("gh-demo")

        self.assertIn("main", card.inner_text())
        buttons = card.get_by_role("button").all_inner_texts()
        joined = " | ".join(buttons)
        self.assertRegex(joined, re.compile(r"Fetch|Abrufen", re.I), joined)
        self.assertRegex(joined, re.compile(r"Pull", re.I), joined)

        fetch = card.get_by_role("button", name=re.compile(r"Fetch|Abrufen", re.I)).first
        before = len(self.github.requests)
        fetch.click()
        toast = self.page.locator(".toast").first
        toast.wait_for(state="visible", timeout=15000)
        self.assertTrue(toast.inner_text().strip())
        self.assertEqual(len(self.github.requests), before,
                         "Der lokale Abruf darf keine API-Anfrage erzeugen")


    def test_push_transfers_the_current_branch_to_origin(self):
        card = self.open_project_settings("gh-demo")

        # One local commit that origin does not know yet.
        probe = self.project_env / "push-probe.txt"
        probe.write_text("Browser-Push-Probe", encoding="utf-8")
        git(self.project_env, "add", "push-probe.txt")
        git(self.project_env, "commit", "-q", "-m", "AP6: Browser-Push-Probe")
        local_head = git_out(self.project_env, "rev-parse", "HEAD")

        push = card.get_by_role("button", name=re.compile(r"Push", re.I))
        self.assertEqual(push.count(), 1)

        push.click()
        toast = self.page.locator(".toast").first
        toast.wait_for(state="visible", timeout=15000)
        message = toast.inner_text()
        self.assertRegex(message, re.compile(r"übertragen|pushed|transferred", re.I), message)
        self.assertRegex(message, re.compile(r"origin", re.I), message)

        # The transfer is real: origin references the local head now.
        remote_tip = git_out(self.project_env, "ls-remote", "origin", "refs/heads/main").split()[0]
        self.assertEqual(remote_tip, local_head)

        # The card and its push button survive the successful action.
        self.assertTrue(self.git_card().is_visible())
        deadline = time.time() + 15
        while (time.time() < deadline and
               card.get_by_role(
                   "button", name=re.compile(r"Push", re.I)).count() != 1):
            time.sleep(0.1)
        self.assertEqual(
            card.get_by_role("button", name=re.compile(r"Push", re.I)).count(), 1,
            "Der Push-Knopf fehlt nach dem erfolgreichen Push",
        )


def wait_for_toast_scan(page):
    """Sammelt aktuelle Toast-Texte ohne Fehler bei zwischenzeitlichem Verschwinden."""
    texts = []
    for toast in page.locator(".toast").all():
        try:
            texts.append({"texts": [toast.inner_text()]})
        except Exception:  # noqa: BLE001 - Toast kann verschwinden
            pass
    return texts


class LinkOnlyMergeRequestUiTest(unittest.TestCase):
    """R2-2/Medium: Der UI-Klick-Fluss darf NACH purem ``link`` nicht in der
    Sackgasse "Basis-Branch (base) unbekannt" enden. Eigenes Dashboard mit
    kurzen Fake-Token in der Prozessumgebung; der Vorher-Zustand wird exakt
    wie von der CLI ``vibe github link`` mit origin via ``remote add`` (kein
    Klon, kein origin/HEAD) erzeugt."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1", "installed_at": "2026-11-07"}),
            encoding="utf-8",
        )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, script in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fakebin / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)

        cls.github = FakeGitHubServer().start()
        cls.fg_port = free_port()

        # Projekt NUR über die reine link-Vorgeschichte: Bare-Repo (-b main),
        # origin via remote add (kein Klon, kein origin/HEAD), main gepusht.
        cls.project = make_project(cls.root, "gh-linkonly")
        cls.env_file = cls.project / ".vibe" / "project.env"
        bare = cls.root / "_loonly-bare"
        bare.mkdir()
        git(bare, "init", "-q", "--bare", "-b", "main")
        cls.loonly_bare = bare
        git(cls.project, "remote", "add", "origin", "file://" + str(bare))
        git(cls.project, "push", "-q", "-u", "origin", "main")

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
            # Kurzes Fake-Literal (< 16 Zeichen): Der Dashboard-Prozess soll
            # die Merge-Request-Basis-Verarbeitung real erreichen.
            "GITHUB_TOKEN": "t-nur-test",
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
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector(".row")
        self.page.locator(".row").filter(has_text=name).first.click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        card = self.page.locator(".card").filter(has_text="Git & GitHub").first
        card.wait_for(state="visible", timeout=15000)
        self.expand_optional("#github")
        return card

    def test_merge_request_after_link_only_sends_default_base(self):
        # Ausdrücklich kein Redirect der origin auf github.com im Test
        # (der Karten-Link-Knopf erzeugt https://github.com/...-URLs und der
        # Merge-Request-Push würde echten Netzkontakt versuchen). Die reine
        # link-Aktion läuft daher über den produktgleichen Web-API-Pfad
        # (/api/github action=link -> vibe.github_link) mit file://-origin —
        # genau die im Review geforderte Vorgeschichte: origin via remote add,
        # kein Klon, kein origin/HEAD. Der Merge-Request danach ist echter
        # UI-Klick-Fluss der Karte (inkl. Inline-Bestätigung).
        card = self.open_project_settings("gh-linkonly")

        # settings: Repo, API-Basis (lokaler Fake-Server).
        card.locator("input[placeholder='owner/name']").first.fill("owner/name")
        card.locator("input[aria-label*='API-Basis']").first.fill(self.github.base)
        card.get_by_role("button", name=re.compile(r"^Save$", re.I)).click()
        self.assertTrue(
            wait_for_file_content(self.env_file, 'GITHUB_API="' + self.github.base + '"'),
            "Einstellungen wurden nicht gespeichert",
        )

        # pures link über die Web-API (gleiche Naht wie der Karten-Knopf).
        response = self.page.evaluate(
            """async ([token, url]) => {
                const r = await fetch('/api/github', {
                    method: 'POST',
                    headers: {'X-Token': token, 'Content-Type': 'application/json'},
                    body: JSON.stringify({name: 'gh-linkonly', action: 'link', url})
                });
                return await r.json();
            }""",
            [self.token, "file://" + str(self.loonly_bare)],
        )
        self.assertTrue(response.get("ok"), response)
        self.assertTrue(
            wait_for_file_content(self.env_file, 'GITHUB_ENABLED="1"'),
            "Die reine Verknüpfung hat GitHub nicht aktiviert",
        )
        # Die Karte rendert den Merge-Request-Knopf im aktivierten Zustand;
        # die Ansicht wird wie nach einer erfolgreichen Kartenaktion neu aufgebaut.
        self.page.reload()
        card = self.open_project_settings("gh-linkonly")
        self.assertEqual(
            card.get_by_role(
                "button", name=re.compile(r"Merge-Request|Merge Request", re.I)
            ).count(),
            1,
            "Merge-Request-Knopf nach Verknüpfung nicht sichtbar",
        )

        # Merge-Request-Klick-Fluss: inline bestätigen.
        card.get_by_role(
            "button", name=re.compile(r"Merge-Request|Merge Request", re.I)
        ).click()
        group = card.locator(".confirm, [role='group']").first
        group.wait_for(state="visible", timeout=5000)
        self.assertEqual(self.github.pr_posts, [])
        group.get_by_role("button", name=re.compile(r"^Yes", re.I)).first.click()

        seen = []
        deadline = time.time() + 15
        while time.time() < deadline and not self.github.pr_posts:
            for scan in wait_for_toast_scan(self.page):
                seen.extend(scan["texts"])
            time.sleep(0.1)
        for scan in wait_for_toast_scan(self.page):
            seen.extend(scan["texts"])
        self.assertTrue(
            self.github.pr_posts,
            "Merge-Request endete ohne API-Anfrage; Meldungen: %r" % (seen,),
        )
        body = json.loads(self.github.pr_posts[-1]["body"])
        self.assertEqual(body["base"], "main")
        self.assertNotRegex(body["base"], r"^[0-9a-f]{7,40}$")
        toasts = " | ".join(seen)
        self.assertNotIn("Basis-Branch", toasts,
                         "Der UI-Fluss endete in der Basis-Sackgasse")
        self.assertNotRegex(toasts, re.compile(r"base\) unbekannt", re.I), toasts)
        self.assertRegex(toasts, re.compile(r"Merge-Request", re.I), toasts)
        self.assertTrue(
            self.page.locator(".card").filter(has_text="Git & GitHub").first.is_visible()
        )


# ===========================================================================
# Browser acceptance tests for the „Aus GitHub auschecken“ flow
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

from playwright.sync_api import sync_playwright

if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))


FAKE_PI_ap8 = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE_ap8 = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
exit 2
"""


def git_ap8(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True, timeout=60)


def git_out_ap8(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60).stdout.strip()


def make_project_ap8(root, name):
    """Erzeugt ein minimales bestehendes Projekt mit git und project.env."""
    project = root / name
    project.mkdir(parents=True)
    git_ap8(project, "init", "-q", "-b", "main")
    git_ap8(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8"
    )
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


def seed_bare(root, name, files):
    """Lokale Bare-Quelle ohne Netz; liefert die file://-Adresse."""
    work = root / "seed" / name
    work.mkdir(parents=True)
    for relative, content in files.items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git_ap8(work, "init", "-q", "-b", "main")
    git_ap8(work, "add", "-A")
    git_ap8(work, "commit", "-q", "-m", "seed")
    bare = root / "origin" / (name + ".git")
    bare.mkdir(parents=True)
    git_ap8(bare, "init", "-q", "--bare")
    git_ap8(work, "push", "-q", str(bare), "main")
    git_ap8(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare)


def write_template(templates, typ, files):
    for relative, content in files.items():
        target = templates / typ / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def build_templates(templates):
    """Lokale Vorlage: Nach dem Clone gelten GENAU diese Einstellungen."""
    write_template(templates, "common", {
        "FEEDBACK.md": "# FEEDBACK A8-LOK-VORLAGE\n",
        "TICKETS.md": "# TICKETS A8-LOK-VORLAGE\n",
        "opencode.json": '{\n  "$schema": "a8-lokale-vorlage"\n}\n',
        ".opencode/agents/test-agent.md": "# Lokale Test-Agent-Vorlage\n",
    })
    write_template(templates, "generic", {
        "AGENTS.md": "# AGENTS fuer {{NAME}}\n",
        ".vibe/project.env": (
            "TYPE=generic\n"
            "REVIEWER=lokal-reviewer\n"
            "TESTER=test-agent\n"
            "SANDBOX=aus\n"
            'VERIFY_QUICK="echo lokal-quick"\n'
            'VERIFY_PACKAGE="echo lokal-paket"\n'
            'VERIFY_FULL="echo lokal-full"\n'
        ),
    })


def wait_for_file_content_ap8(path, needle, timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if needle in Path(path).read_text(encoding="utf-8"):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def wait_for_toast_ap8(page, pattern, timeout=25.0):
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
        "kein Toast passend zu %r; zuletzt gesehen: %r" % (pattern, last)
    )


class CheckoutUiTest(unittest.TestCase):
    """Die Projektliste bietet das Auschecken an (AK5)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        build_templates(cls.toolchain / "templates")
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1",
                        "installed_at": "2026-11-10"}),
            encoding="utf-8",
        )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.workspace = cls.root  # VIBE ist die Wurzel des Prüfstands
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        for name, script in (("opencode", FAKE_OPENCODE_ap8), ("pi", FAKE_PI_ap8)):
            path = cls.fakebin / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)

        # Bestehendes Projekt, damit die Projektliste nicht leer startet.
        make_project_ap8(cls.workspace, "bestand")

        # Lokale Bare-Quellen für den Auschecklauf ohne Netz.
        cls.aushang_url = seed_bare(cls.workspace, "aushang", {
            "README.md": "Aushang-Inhalt\n",
        })
        cls.karte_url = seed_bare(cls.workspace, "karte", {
            "README.md": "Karte-Inhalt\n",
        })

        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.workspace),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.toolchain),
            "VIBE_INSTALL": str(cls.toolchain),
            "VIBE_RUNTIME": str(cls.logs),
            "HOME": str(cls.home),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        cls.token_file = cls.logs / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if cls.token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = cls.token_file.read_text(encoding="utf-8").strip()
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

    # ------------------------------------------------------- helpers
    def open_project_list(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector(".row", timeout=20000)
        return self.new_project_card()

    def new_project_card(self):
        card = self.page.locator(".card").filter(
            has_text=re.compile("New project", re.I)
        ).first
        card.wait_for(state="visible", timeout=20000)
        return card

    def url_input(self, card):
        """Das URL-Feld der Auscheck-Karte (per Bezeichnung oder Stellvertreter)."""
        inputs = card.locator("input:not([type='checkbox'])")
        pattern = re.compile(r"(URL|Adresse|GitHub|auschecken|Remote)", re.I)
        for index in range(inputs.count()):
            field = inputs.nth(index)
            label = " ".join(filter(None, (
                field.get_attribute("aria-label") or "",
                field.get_attribute("placeholder") or "",
            )))
            if field.is_editable() and pattern.search(label):
                return field
        self.fail(
            "kein URL-Feld gefunden; Felder: %r" %
            [inputs.nth(i).get_attribute("placeholder") or
             inputs.nth(i).get_attribute("aria-label")
             for i in range(inputs.count())]
        )

    def checkout_button(self, card):
        button = card.get_by_role(
            "button", name=re.compile(r"Check out from GitHub", re.I)
        )
        self.assertEqual(button.count(), 1,
                         "Genau ein Auschecken-Knopf wird erwartet")
        return button

    # ------------------------------------------------------- tests
    def test_the_project_list_offers_the_github_checkout_card(self):
        """AK5: Karte „Neues Projekt“ mit URL-Feld und Auschecken-Knopf."""
        card = self.open_project_list()

        self.url_input(card)
        self.checkout_button(card)
        # Bestehende Kartenfunktionen bleiben (kein blockierender Umstand):
        self.assertTrue(card.get_by_role("button").count() >= 1)

    def test_checkout_from_a_local_file_url_creates_and_opens_the_project(self):
        """AK1+AK2+AK5: Auschecken legt das Projekt an, übernimmt lokale
        Einstellungen und öffnet das Projekt."""
        card = self.open_project_list()
        field = self.url_input(card)
        field.fill(self.aushang_url)
        self.checkout_button(card).click()

        # Das neue Projekt entsteht mit lokal übernommenen Einstellungen.
        env_file = self.workspace / "aushang" / ".vibe" / "project.env"
        self.assertTrue(
            wait_for_file_content_ap8(env_file, "TESTER=test-agent"),
            "Die lokale Projektvorlage wurde nicht auf das neue Projekt übernommen",
        )
        env_value = env_file.read_text(encoding="utf-8")
        self.assertIn("TYPE=", env_value)
        self.assertNotIn("GITHUB_REPO=", env_value)

        agents_file = self.workspace / "aushang" / "AGENTS.md"
        self.assertTrue(
            wait_for_file_content_ap8(agents_file, "# AGENTS fuer"),
            "AGENTS.md ohne die Vorlage",
        )

        # In der Liste auffindbar und geöffnet (Projektansicht im Schaubereich).
        row = self.page.locator(".row").filter(has_text="aushang").first
        row.wait_for(state="visible", timeout=25000)
        heading = self.page.get_by_role("heading", name=re.compile("aushang", re.I))
        heading.wait_for(state="visible", timeout=25000)

        # Remote origin zeigt auf die ausgecheckte Adresse.
        origin = git_out_ap8(self.workspace / "aushang",
                         "remote", "get-url", "origin")
        self.assertEqual(origin, self.aushang_url)

        # Der bestehende Projektbestand bleibt in der Liste sichtbar.
        if self.page.url.endswith("#t=" + self.token):
            self.page.locator(".row").filter(has_text="bestand").first \
                .wait_for(state="visible", timeout=10000)

    def test_the_clone_api_creates_the_project_and_requires_the_token(self):
        """AK5: POST /api/clone {url, name} -> {ok, message, project}; nur
        mit gültiger Anmeldung (Token oder Session); Fehler strukturiert."""
        # Die API läuft über die geöffnete Oberfläche (Standardursprung);
        # die Seite muss dafür tatsächlich geladen sein.
        self.open_project_list()
        # Mit Token: Erfolg.
        payload = self.page.evaluate(
            """async ([token, url]) => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    headers: {'X-Token': token, 'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, name: 'karte'})
                });
                return [r.status, await r.json()];
            }""",
            [self.token, self.karte_url],
        )
        status, data = payload
        self.assertEqual(status, 200, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("message", data)
        self.assertIn("project", data)
        self.assertTrue((self.workspace / "karte" / ".vibe" / "project.env").exists())

        # Ohne Token: nichts angelegt, strukturierte Fehler. Die geladene
        # Seite hat über boot() bereits ein Session-Cookie erhalten; das ist
        # laut SPEC eine gültige Anmeldung. Die Tokenpflicht wird deshalb mit
        # einer Anfrage ohne jegliche Credentials geprüft.
        without = self.page.evaluate(
            """async () => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    credentials: 'omit',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: '%s', name: 'untersignal'})
                });
                return [r.status, await r.json().catch(() => ({}))];
            }""" % (self.aushang_url,)
        )
        status, data = without
        self.assertTrue(status >= 400 or not data.get("ok"), data)
        self.assertFalse((self.workspace / "untersignal").exists())

        # Mit Token, aber ungültiger Adresse: strukturierte Fehler.
        invalid = self.page.evaluate(
            """async ([token]) => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    headers: {'X-Token': token, 'Content-Type': 'application/json'},
                    body: JSON.stringify({url: '://kaputt'})
                });
                return [r.status, await r.json().catch(() => ({}))];
            }""",
            [self.token],
        )
        status, data = invalid
        self.assertTrue(status >= 400 or not data.get("ok"), data)
        self.assertTrue(
            data.get("message") or data.get("error") or not data,
            "keine gemeldete Fehlbegründung",
        )
        self.assertFalse((self.workspace / "kaputt").exists())

    def test_an_invalid_url_reports_an_error_and_keeps_the_form_usable(self):
        """AK4+AK5: Klar gemeldeter Fehler, kein halb angelegtes Projekt, die
        Karte bleibt ohne blockierenden Dialog nutzbar."""
        card = self.open_project_list()
        field = self.url_input(card)
        field.fill("://kaputt")
        self.checkout_button(card).click()

        toast = wait_for_toast_ap8(self.page, r".", timeout=25.0)
        self.assertTrue(toast.strip(), "Fehlermeldung fehlt")
        self.assertFalse((self.workspace / "kaputt").exists())
        self.assertFalse(
            self.page.locator(".row").filter(has_text="kaputt").count()
        )
        # Keine blockierende Sackgasse: Feld und Knopf sind erneut nutzbar.
        self.assertTrue(field.is_editable())
        self.assertTrue(self.checkout_button(card).is_visible())


# ===========================================================================
# Browser acceptance tests for the „Bereit für Github Teil 3“ UI
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))


FAKE_PI_ap9 = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE_ap9 = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
exit 2
"""


PROJECT_TOKEN = "ap9-ui-projekt-token-555"


class AP9FakeGitHubHandler(BaseHTTPRequestHandler):
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


class AP9FakeGitHubServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), AP9FakeGitHubHandler)
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


def git_ap9(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60)


def git_out_ap9(cwd, *argv):
    return git_ap9(cwd, *argv).stdout.strip()


def make_project_ap9(root, name, extra_env=""):
    """Minimales vibe-Projekt mit Git-Repository und project.env."""
    project = root / name
    project.mkdir(parents=True)
    git_ap9(project, "init", "-q", "-b", "main")
    git_ap9(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n" + extra_env, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


def wait_for_toast_ap9(page, pattern, timeout=15.0):
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
        for name, text in (("opencode", FAKE_OPENCODE_ap9), ("pi", FAKE_PI_ap9)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)

        cls.github = AP9FakeGitHubServer().start()

        # Projekt mit funktionierender Verknüpfung: origin (file://),
        # GitHub-Fake und einem zweiten lokalen Branch für „Wechseln“.
        cls.project_env = make_project_ap9(
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
        git_ap9(bare, "init", "-q", "--bare")
        git_ap9(cls.project_env, "remote", "add", "origin", "file://" + str(bare))
        git_ap9(cls.project_env, "push", "-q", "-u", "origin", "main")
        git_ap9(cls.project_env, "branch", "feature/arbeit")
        cls.bare_path = bare

        # Projekt mit absichtlich kaputter API-Adresse (Loopback, kein Dienst):
        cls.bad_env = make_project_ap9(
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
        git_ap9(bad_bare, "init", "-q", "--bare")
        git_ap9(cls.bad_env, "remote", "add", "origin", "file://" + str(bad_bare))
        git_ap9(cls.bad_env, "push", "-q", "-u", "origin", "main")

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
        self.page.goto(self.base + "/classic#t=" + self.token)
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
        wait_for_toast_ap9(self.page, r"wechsel|Branch", timeout=15000)
        deadline = time.time() + 10
        while time.time() < deadline:
            if git_out_ap9(self.project_env, "rev-parse", "--abbrev-ref",
                       "HEAD") == "feature/arbeit":
                break
            time.sleep(0.2)
        self.assertEqual("feature/arbeit",
                         git_out_ap9(self.project_env, "rev-parse",
                                 "--abbrev-ref", "HEAD"),
                         "„Wechseln“ hat den Arbeitsbaum nicht gewechselt")

        # Der Wechsel rendert die Karte neu: den Branches-Abschnitt erneut
        # aufklappen (kurz warten, bis die Karte wieder gerendert ist).
        branches = self.reopen_branches()

        # „Push“ auf der Feature-Zeile überträgt den Zweig zur origin:
        tip = git_out_ap9(self.project_env, "rev-parse", "feature/arbeit")
        self.button_in_row(branches, "feature/arbeit",
                           re.compile(r"^\s*Push\s*$", re.I)).click()
        wait_for_toast_ap9(self.page, r"übertragen|Push|origin", timeout=15000)
        remote_tip = git_out_ap9(self.project_env, "ls-remote", "origin",
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


# ===========================================================================
# Browser-Acceptanztests für die GitHub-Authentifizierung in der Karte
# ===========================================================================

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

if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))


# Test-Token; das Dashboard erhält ihn nie über die Umgebung.
UI_TOKEN = "b7-browser-token-9999xyz"

ISOLATED_ENV_b7 = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "VIBE_PROFIL", "VIBE_PROFILE",
)

SAVE_TOKEN = re.compile(
    r"(?:.*(?:zugangs)?token.*(?:speichern|hinterlegen|save|store).*"
    r"|.*(?:speichern|save|store).*(?:zugangs)?token.*)", re.I)
CLEAR_TOKEN = re.compile(
    r"(?:.*(?:zugangs)?token.*(?:entfernen|l[oö]schen|remove|clear).*"
    r"|.*(?:entfernen|remove|clear|delete).*(?:zugangs)?token.*)", re.I)
SETTINGS_SAVE = re.compile(r"^\s*(Speichern|Save)\s*$")
AUTH_STATUS = re.compile(r"gespeichert|hinterlegt|umgebung|saved|stored|environment", re.I)


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


class AuthFakeGitHubHandler(BaseHTTPRequestHandler):
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


class AuthFakeGitHubServer:
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
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), AuthFakeGitHubHandler)
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


def make_project_b7(root, name, extra_env=""):
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

        cls.github = AuthFakeGitHubServer().start()

        # Projekt mit funktionierendem file://-Origin und konfigurierbarer
        # Fake-API: alle auth-Aktionen der Karte laufen hier.
        cls.demo = make_project_b7(
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
        bare_env = make_project_b7(cls.root, "_bare-helper")
        git(bare, "init", "-q", "--bare", "-b", "main")
        git(cls.demo, "remote", "add", "origin", "file://" + str(bare))
        git(cls.demo, "push", "-q", "-u", "origin", "main")

        # Projekt mit offizieller API (https://api.github.com): Der pr-Fluss
        # scheitert offline verständlich am fehlenden Token, ohne Netzkontakt.
        cls.official = make_project_b7(
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
        cls.broken = make_project_b7(
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
        for key in ISOLATED_ENV_b7:
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
        self.page.goto(self.base + "/classic#t=" + self.web_token)
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
        group.get_by_role("button", name=re.compile(r"Ja|Bestätigen|Yes|Confirm", re.I)).first.click()

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
        for key in ISOLATED_ENV_b7:
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
            page.goto(base_url + "/classic#t=" + login_token)
            page.wait_for_selector(".row")
            page.locator(".row").filter(has_text="gh-b7-demo").first.click()
            page.get_by_role("tab", name="Settings").click()
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
            self.assertNotRegex(
                initial_text, r"Kein Token hinterlegt|No token stored",
                "Der Server meldet Umgebungszugriff; die Startzeile zeigt ihn "
                "nicht: %r" % initial_text)
            self.assertTrue(
                re.search(r"umgebung|environment", initial_text, re.IGNORECASE),
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
                self.assertNotRegex(
                    text, r"gespeichert|saved",
                    "token.save zeigt die Quelle hartkodiert statt der "
                    "Serverquelle 'umgebung': %r" % text)
                self.assertNotRegex(
                    text, r"Kein Token hinterlegt|No token stored",
                    "token.save hat die Anzeige geleert: %r" % text)
            self.assertTrue(
                all(re.search(r"umgebung|environment", t, re.IGNORECASE)
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
                self.assertNotRegex(
                    text, r"Kein Token hinterlegt|No token stored",
                    "token.clear setzt die Anzeige auf '' statt der "
                    "Serverquelle 'umgebung': %r" % text)
                self.assertNotRegex(
                    text, r"gespeichert|saved",
                    "Nach token.clear bleibt eine falsche Quelle stehen: %r"
                    % text)
            self.assertTrue(
                all(re.search(r"umgebung|environment", t, re.IGNORECASE)
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
