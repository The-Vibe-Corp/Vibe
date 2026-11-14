"""Browser acceptance tests for the Git & GitHub card in the dashboard (AP6).

The dashboard runs as a real process against a fake toolchain inside a
temporary directory (pattern of tests/browser/test_ap04_harness_ui.py).
GitHub requests go to a local fake REST server on 127.0.0.1 only; the
dashboard process has no GitHub token, so no real github.com call can
happen. The project on disk carries a .vibe/project.env and a real git
origin (file://), so fetch/pull stay inside the temp directory.

Run with:

    python3 -m unittest tests.browser.test_ap06_github_ui -v
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
        self.page.goto(self.base + "/#t=" + self.token)
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
        repo = card.locator("input[aria-label*='Repository']").first

        repo.fill("owner/my.repo")
        card.get_by_role("button", name=re.compile(r"Mit GitHub verkn", re.I)).click()
        wait_for_toast(self.page, r"Verknüpfung gespeichert")

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
        card.get_by_role("button", name=re.compile("Speichern", re.I)).click()
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
        self.assertTrue(any(re.search(r"Ja|Bestätigen", t, re.I) for t in texts), texts)
        self.assertTrue(any(re.search(r"Abbrechen", t, re.I) for t in texts), texts)
        self.assertEqual(self.page.locator(".toast").count(), 0)

        # Cancel sends nothing at all.
        group.get_by_role("button", name=re.compile(r"Abbrechen", re.I)).click()
        self.assertEqual(card.locator(".confirm, [role='group']").count(), 0)
        self.assertEqual(self.github.pr_posts, [])
        self.assertEqual(self.page.locator(".toast").count(), 0)

        # Confirming is what actually throws the error message (no token here).
        pr_button.click()
        group = card.locator(".confirm, [role='group']").first
        group.wait_for(state="visible", timeout=5000)
        group.get_by_role("button", name=re.compile(r"Ja|Bestätigen", re.I)).first.click()
        toast = self.page.locator(".toast").first
        toast.wait_for(state="visible", timeout=15000)
        self.assertRegex(toast.inner_text(), re.compile(r"Kein GitHub|Fehler", re.I))
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
        self.assertRegex(message, re.compile("übertragen", re.I), message)
        self.assertRegex(message, re.compile(r"origin", re.I), message)

        # The transfer is real: origin references the local head now.
        remote_tip = git_out(self.project_env, "ls-remote", "origin", "refs/heads/main").split()[0]
        self.assertEqual(remote_tip, local_head)

        # The card and its push button survive the successful action.
        self.assertTrue(self.git_card().is_visible())
        self.assertEqual(
            card.get_by_role("button", name=re.compile(r"Push", re.I)).count(), 1
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
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.wait_for_selector(".row")
        self.page.locator(".row").filter(has_text=name).first.click()
        self.page.get_by_role("tab", name="Einstellungen").click()
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
        card.locator("input[aria-label*='Repository']").first.fill("owner/name")
        card.locator("input[aria-label*='API-Basis']").first.fill(self.github.base)
        card.get_by_role("button", name=re.compile("Speichern", re.I)).click()
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
        group.get_by_role("button", name=re.compile(r"Ja|Bestätigen", re.I)).first.click()

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




if __name__ == "__main__":
    unittest.main()
