"""GitHub-Kern: Konfiguration, Verknüpfung, Push/Pull, REST-Zugriff, Token und Branchnamen.

Aufruf: python3 -m unittest tests.unit.test_github -v
"""


# ===========================================================================
# Acceptance tests for the Git/GitHub integration
# ===========================================================================

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"

OFFICIAL_API = "https://api.github.com"
DEFAULT_LABEL = "vibe"
NO_TOKEN_PREFIX = "Kein GitHub-Zugangstoken"

ISSUES = [
    {
        "number": 7,
        "title": "Sandbox für Import einschränken",
        "state": "open",
        "body": "Der Import liest nur das konfigurierte Label.",
        "html_url": "http://127.0.0.1/owner/name/issues/7",
        "labels": [{"name": "vibe"}],
    },
    {
        "number": 8,
        "title": "Bug im Label-Filter",
        "state": "open",
        "body": "Bugs gehören nicht in TICKETS.md.",
        "html_url": "http://127.0.0.1/owner/name/issues/8",
        "labels": [{"name": "bug"}],
    },
]


def is_argument_list(value):
    return isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value)


class FakeGitHubHandler(BaseHTTPRequestHandler):
    """Local REST stand-in for GitHub; records every request for the test."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method, body):
        parsed = urlparse(self.path)
        self.server.requests.append({
            "method": method,
            "path": parsed.path,
            "query": parse_qs(parsed.query),
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": json.loads(body.decode("utf-8")) if body else None,
        })

    def do_GET(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record("GET", b"")
        if urlparse(self.path).path == "/repos/owner/name/issues":
            self._respond(200, self.server.issues)
        else:
            self.server.not_found.append(urlparse(self.path).path)
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record("POST", raw)
        if urlparse(self.path).path == "/repos/owner/name/pulls":
            self.server.pr_posts.append(self.server.requests[-1])
            self._respond(self.server.pr_status, self.server.pr_payload)
        else:
            self._respond(404, {"message": "Not Found"})


class FakeGitHubServer:
    """GitHub fake on 127.0.0.1 only; never reachable from elsewhere."""

    def __init__(self, pr_status=201, pr_payload=None):
        self.requests = []
        self.not_found = []
        self.pr_posts = []
        self.issues = list(ISSUES)
        self.pr_status = pr_status
        self.pr_payload = pr_payload or {
            "number": 42,
            "id": 4207,
            "html_url": "http://127.0.0.1/owner/name/pull/42",
        }
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHubHandler)
        self.httpd.requests = self.requests
        self.httpd.not_found = self.not_found
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

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    @property
    def last_pr(self):
        return self.pr_posts[-1] if self.pr_posts else None


_GITHUB_CACHE = {}


STORAGE_MODULE = REPO / "bin" / "vibe_storage.py"


def storage_module():
    """Loads ``bin/vibe_storage.py`` first; patches target for atomic writes."""
    if "vibe_storage" in _GITHUB_CACHE:
        return _GITHUB_CACHE["storage"]
    loader = importlib.machinery.SourceFileLoader("vibe_storage_under_test", str(STORAGE_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GITHUB_CACHE["storage"] = module
    return module


def github_module():
    """Loads ``bin/vibe_github.py`` as a plain module (red phase: missing file)."""
    if "gh" in _GITHUB_CACHE:
        return _GITHUB_CACHE["gh"]
    # Typical sibling import; preloading keeps the patch seam deterministic.
    storage_module()
    loader = importlib.machinery.SourceFileLoader("vibe_github_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GITHUB_CACHE["gh"] = module
    return module


def load_cli(vibe_root, home):
    """Loads ``bin/vibe`` as a module with isolated VIBE and HOME (V-008 pattern)."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader("vibe_ap06_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    # Ignore any user/global/system git configuration inside the tests.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv, check=True):
    """Runs a real git command with a fixed test identity (never network)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )


def git_out(cwd, *argv):
    return git(cwd, *argv).stdout.strip()


def commit_file(path, name, content, message):
    (Path(path) / name).write_text(content, encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-q", "-m", message)


def init_git_repo(path, branch="main"):
    Path(path).mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", branch)
    git(path, "commit", "--allow-empty", "-q", "-m", "init")


class ProjectFixture(unittest.TestCase):
    """Project with .vibe/project.env, the GH-48 ticket store and real git."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        # Isolated environment: never reuse a caller-provided GitHub token.
        self._saved_tokens = {k: os.environ.pop(k, None) for k in ("GITHUB_TOKEN", "GH_TOKEN")}
        self.addCleanup(self.restore_token_env)
        self.prepare_project()
        self.cli = load_cli(self.workspace, self.home)
        self.gh = github_module()
        self.env_path = self.project / ".vibe" / "project.env"

    def restore_token_env(self):
        for key, value in self._saved_tokens.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def prepare_project(self):
        self.project = self.workspace / "proj"
        init_git_repo(self.project)
        (self.project / ".vibe").mkdir(parents=True)
        self.env_path_tmp = self.project / ".vibe" / "project.env"
        self.env_path_tmp.write_text(
            'TYPE=generic\nTESTER=test-agent\nSANDBOX="off"\n', encoding="utf-8"
        )
        # Der Ticketspeicher ist Laufzeitstand und wird nie versioniert.
        (self.project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
        self.store = self.project / ".vibe" / "tickets.json"

    def store_tickets(self):
        """Ticketliste aus dem GH-48-Speicher; fehlende Datei heißt leer."""
        if not self.store.exists():
            return []
        return json.loads(self.store.read_text(encoding="utf-8"))["tickets"]

    def write_store_tickets(self, tickets):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    def make_bare(self, name):
        bare = self.base / name
        bare.mkdir()
        # -b main: ohne init.defaultBranch wäre der Bare-Default "master".
        git(bare, "init", "-q", "--bare", "-b", "main")
        return bare

    def add_origin(self, bare):
        git(self.project, "remote", "add", "origin", "file://" + str(bare))

    def run_cli(self, *args, **kwargs):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.cli.cmd_github("proj", *args, out=stdout, **kwargs)
        return result, stdout.getvalue(), stderr.getvalue()


# ------------------------------------------------------------ Configuration
class ReadConfigDefaultsTest(unittest.TestCase):
    """read_config: safe defaults; GitHub stays off until configured."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_path = self.project / ".vibe" / "project.env"
        self.gh = github_module()

    def test_missing_keys_mean_disabled_with_vibe_label_and_official_api(self):
        self.env_path.write_text('TYPE=generic\nSANDBOX="on"\n', encoding="utf-8")

        config = self.gh.read_config(str(self.env_path))

        for key in ("enabled", "repo", "label", "api"):
            self.assertIn(key, config)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["repo"], "")
        self.assertEqual(config["label"], DEFAULT_LABEL)
        self.assertEqual(config["api"], OFFICIAL_API)

    def test_missing_project_env_file_reports_disabled_github(self):
        config = self.gh.read_config(str(self.env_path))

        self.assertFalse(config["enabled"])
        self.assertEqual(config["repo"], "")

    def test_enabled_flag_values_are_parsed(self):
        for value, expected in (("1", True), ("0", False), ("true", True)):
            with self.subTest(value=value):
                self.env_path.write_text(f'GITHUB_ENABLED="{value}"\n', encoding="utf-8")
                self.assertTrue(self.gh.read_config(str(self.env_path))["enabled"] is expected)

    def test_quoted_values_keep_their_content(self):
        self.env_path.write_text(
            'GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
            'GITHUB_LABEL="vibe-tasks"\nGITHUB_API="http://127.0.0.1:9/v3"\n',
            encoding="utf-8",
        )

        config = self.gh.read_config(str(self.env_path))

        self.assertTrue(config["enabled"])
        self.assertEqual(config["repo"], "owner/name")
        self.assertEqual(config["label"], "vibe-tasks")
        self.assertEqual(config["api"], "http://127.0.0.1:9/v3")


class ConfigWriteTest(ProjectFixture):
    """GitHub keys are written through the shared set_env_values of the CLI."""

    def test_setting_github_keys_preserves_existing_lines(self):
        before = self.env_path.read_text(encoding="utf-8")

        self.cli.set_env_values("proj", {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name"})

        after = self.env_path.read_text(encoding="utf-8")
        self.assertIn('GITHUB_ENABLED="1"', after)
        self.assertIn('GITHUB_REPO="owner/name"', after)
        for line in before.splitlines():
            self.assertIn(line, after.splitlines())
        self.assertEqual(after.count("TYPE="), 1)
        self.assertEqual(after.count("TESTER="), 1)

    def test_setting_github_keys_in_a_crlf_file_keeps_crlf_style(self):
        self.env_path.write_text(
            'TYPE=generic\r\nTESTER=test-agent\r\nSANDBOX="off"\r\n', encoding="utf-8"
        )

        self.cli.set_env_values("proj", {"GITHUB_LABEL": "vibe-tasks"})

        # Text-Modus normalisiert Zeilenenden; bytes erfassen den CRLF-Stand.
        after = self.env_path.read_bytes().decode("utf-8")
        self.assertIn('GITHUB_LABEL="vibe-tasks"', after)
        self.assertIn("TYPE=generic\r\nTESTER=test-agent\r\n", after)

    def test_saved_github_config_round_trips_through_read_config(self):
        self.cli.set_env_values(
            "proj",
            {
                "GITHUB_ENABLED": "1",
                "GITHUB_REPO": "owner/name",
                "GITHUB_LABEL": "vibe-tasks",
                "GITHUB_API": "http://127.0.0.1:9/v3",
            },
        )

        config = self.gh.read_config(str(self.env_path))

        self.assertTrue(config["enabled"])
        self.assertEqual(config["repo"], "owner/name")
        self.assertEqual(config["label"], "vibe-tasks")
        self.assertEqual(config["api"], "http://127.0.0.1:9/v3")


# --------------------------------------------------------------- Link/Unlink
class LinkUnlinkTest(ProjectFixture):
    """link registers remote origin and the project env without touching others."""

    def setUp(self):
        super().setUp()
        self.bare = self.make_bare("upstream-bare")
        git(self.project, "remote", "add", "upstream", str(self.bare))

    def test_link_sets_origin_url_and_persists_github_keys(self):
        url = "https://github.com/owner/name.git"

        self.run_cli("link", url)

        self.assertEqual(git_out(self.project, "remote", "get-url", "origin"), url)
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn('GITHUB_ENABLED="1"', text)
        self.assertIn('GITHUB_REPO="owner/name"', text)
        self.assertIn('SANDBOX="off"', text)

    def test_link_with_local_file_remote_also_lands_in_the_config(self):
        url = "file://" + str(self.bare)

        self.run_cli("link", url)

        self.assertEqual(git_out(self.project, "remote", "get-url", "origin"), url)
        self.assertIn('GITHUB_ENABLED="1"', self.env_path.read_text(encoding="utf-8"))

    def test_unlink_removes_origin_but_keeps_other_lines_and_remotes(self):
        self.run_cli("link", "https://github.com/owner/name.git")

        self.run_cli("unlink")

        self.assertTrue(git(self.project, "remote", "get-url", "origin", check=False).returncode)
        self.assertEqual(git_out(self.project, "remote", "get-url", "upstream"), str(self.bare))
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn('SANDBOX="off"', text)
        self.assertIn("TESTER=test-agent", text)

    def test_invalid_url_is_refused_without_any_change(self):
        for bad in ("nur-worte", "https://github.com/owneronly"):
            with self.subTest(url=bad):
                before_remotes = git_out(self.project, "remote", "-v")
                before_env = self.env_path.read_text(encoding="utf-8")
                try:
                    self.run_cli("link", bad)
                except (ValueError, SystemExit):
                    pass  # refusing loudly is as acceptable as a failure message
                self.assertEqual(git_out(self.project, "remote", "-v"), before_remotes)
                self.assertEqual(self.env_path.read_text(encoding="utf-8"), before_env)


# --------------------------------------------------------------- Fetch/Pull/Push
class RemoteOpsTest(ProjectFixture):
    """fetch/pull/push against real but strictly local repos (file://)."""

    def setUp(self):
        super().setUp()
        self.origin = self.make_bare("origin-bare")
        self.add_origin(self.origin)
        git(self.project, "push", "-q", "-u", "origin", "main")

    def test_push_publishes_the_local_commit_to_origin(self):
        commit_file(self.project, "arbeit.txt", "lokal", "AP6: lokal")

        ok, message = self.gh.push(str(self.project), "main")

        self.assertTrue(ok)
        self.assertTrue(message)
        second = self.base / "zweitkollaborateur"
        git(self.base, "clone", "-q", "file://" + str(self.origin), str(second))
        self.assertEqual((second / "arbeit.txt").read_text(encoding="utf-8"), "lokal")

    def test_pull_absorbs_remote_updates(self):
        contributor = self.base / "zweitkollaborateur"
        git(self.base, "clone", "-q", "file://" + str(self.origin), str(contributor))
        commit_file(contributor, "partner.txt", "von draußen", "AP6: remote Arbeit")
        git(contributor, "push", "-q", "origin", "main")

        ok, message = self.gh.pull(str(self.project))

        self.assertTrue(ok)
        self.assertTrue(message)
        self.assertEqual((self.project / "partner.txt").read_text(encoding="utf-8"), "von draußen")

    def test_diverged_pull_fails_and_keeps_the_local_state_intact(self):
        contributor = self.base / "zweitkollaborateur"
        git(self.base, "clone", "-q", "file://" + str(self.origin), str(contributor))
        commit_file(contributor, "partner.txt", "draußen", "AP6: anderer Knoten")
        git(contributor, "push", "-q", "origin", "main")
        commit_file(self.project, "lokal.txt", "vor Ort", "AP6: eigene Arbeit")
        head_before = git_out(self.project, "rev-parse", "HEAD")
        tracked = self.project / "lokal.txt"
        content_before = tracked.read_bytes()

        ok, message = self.gh.pull(str(self.project))

        self.assertFalse(ok)
        self.assertTrue(message)
        self.assertEqual(git_out(self.project, "rev-parse", "HEAD"), head_before)
        self.assertEqual(tracked.read_bytes(), content_before)

    def test_git_calls_use_plain_argument_lists_without_shell(self):
        real_run = subprocess.run
        calls = []

        def spy(args=None, *rest, **kwargs):
            calls.append((args, kwargs))
            return real_run(args, *rest, **kwargs)

        holder = getattr(self.gh, "subprocess", None) or self.gh
        with mock.patch.object(holder, "run", spy):
            self.gh.fetch(str(self.project))
            self.gh.pull(str(self.project))

        self.assertTrue(calls)
        for args, kwargs in calls:
            self.assertTrue(is_argument_list(args), args)
            self.assertFalse(kwargs.get("shell"), "shell=True is forbidden")

    def test_fetch_reports_an_unreachable_remote_without_crashing(self):
        git(self.project, "remote", "set-url", "origin", "file:///kein/repo/hier")

        ok, message = self.gh.fetch(str(self.project))

        self.assertFalse(ok)
        self.assertTrue(isinstance(message, str) and message)


# ------------------------------------------------------------------ Status/Branches
class StatusAndBranchesTest(ProjectFixture):
    """status/branches: pure local read view, no network behaviour."""

    def setUp(self):
        super().setUp()
        self.origin = self.make_bare("origin-bare")
        self.add_origin(self.origin)
        git(self.project, "push", "-q", "-u", "origin", "main")
        self.cli.set_env_values(
            "proj", {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name"}
        )

    def test_status_reports_the_essential_github_and_remote_facts(self):
        info = self.gh.status(str(self.project))

        for key in ("enabled", "repo", "label", "api", "remotes", "branch",
                    "ahead", "behind", "unpushed"):
            self.assertIn(key, info)
        self.assertTrue(info["enabled"])
        self.assertEqual(info["repo"], "owner/name")
        self.assertEqual(info["branch"], "main")
        origin = [r for r in info["remotes"] if r.get("name") == "origin"][0]
        url = origin.get("url") or (origin.get("fetch") or [None])[0]
        self.assertIn(str(self.origin), url)

    def test_unpushed_tracks_the_published_history(self):
        self.assertFalse(self.gh.status(str(self.project))["unpushed"])

        commit_file(self.project, "neu.txt", "dies", "AP6: ungesendet")

        self.assertTrue(self.gh.status(str(self.project))["unpushed"])

        self.gh.push(str(self.project), "main")

        self.assertFalse(self.gh.status(str(self.project))["unpushed"])

    def test_branches_list_local_names_mark_current_and_report_ahead_behind(self):
        contributor = self.base / "zweitkollaborateur"
        git(self.base, "clone", "-q", "file://" + str(self.origin), str(contributor))
        git(contributor, "checkout", "-q", "-b", "feature")
        commit_file(contributor, "partner.txt", "draußen", "AP6: remote Zweig")
        git(contributor, "push", "-q", "origin", "feature")
        git(self.project, "fetch", "-q", "origin", "feature")
        git(self.project, "checkout", "-q", "-b", "feature", "origin/feature")
        commit_file(self.project, "mine.txt", "vor Ort", "AP6: eigener Zweig")
        # Remote roars ahead while the local commit stays unpublished.
        git(contributor, "pull", "-q", "origin", "feature")
        commit_file(contributor, "partner2.txt", "draußen 2", "AP6: remote Zweig 2")
        git(contributor, "push", "-q", "origin", "feature")

        branches = self.gh.branches(str(self.project))
        names = [b["name"] for b in branches]

        self.assertIn("main", names)
        self.assertIn("feature", names)
        feature = [b for b in branches if b["name"] == "feature"][0]
        current = [b for b in branches if b.get("current")][0]
        self.assertEqual(current["name"], "feature")
        self.assertEqual(feature.get("ahead"), 1)
        self.assertEqual(feature.get("behind"), 1)


# ------------------------------------------------------------------- Issues/HTTP layer
class GitHubHttpLayerTest(unittest.TestCase):
    """GitHub HTTP layer exclusively against the local fake API server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.server = FakeGitHubServer().start()
        self.addCleanup(self.server.close)
        self.gh = github_module()
        self._saved_tokens = {k: os.environ.pop(k, None) for k in ("GITHUB_TOKEN", "GH_TOKEN")}
        self.addCleanup(self.restore_token_env)

    def restore_token_env(self):
        for key, value in self._saved_tokens.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_list_issues_filters_by_label_and_returns_number_title_url(self):
        issues = self.gh.list_issues("owner/name", "vibe", api=self.server.base)

        self.assertEqual([i["number"] for i in issues], [7])
        self.assertEqual(issues[0]["title"], "Sandbox für Import einschränken")
        self.assertIn("issues/7", issues[0]["html_url"])
        sent = self.server.requests[-1]
        self.assertEqual(sent["method"], "GET")
        self.assertEqual(sent["path"], "/repos/owner/name/issues")

    def test_create_pull_request_posts_bearer_token_and_returns_the_url(self):
        result = self.gh.create_pull_request(
            project_path=str(self.project),
            repo="owner/name",
            head="feature/ap6",
            base="main",
            title="AP6: Zusammenführung",
            body="Kurze Zusammenfassung",
            api=self.server.base,
            token="t-supersecret",
        )

        self.assertIn("url", result)
        self.assertIn("pull/42", str(result["url"]))
        sent = self.server.last_pr
        self.assertEqual(sent["path"], "/repos/owner/name/pulls")
        self.assertEqual(sent["headers"]["authorization"], "Bearer t-supersecret")
        self.assertEqual(sent["body"]["title"], "AP6: Zusammenführung")
        self.assertEqual(sent["body"]["head"], "feature/ap6")
        self.assertEqual(sent["body"]["base"], "main")
        self.assertIn("body", sent["body"])

    def test_create_pull_request_sends_exactly_one_api_request(self):
        self.gh.create_pull_request(
            project_path=str(self.project), repo="owner/name",
            head="feature/ap6", base="main", title="t", body="b",
            api=self.server.base, token="t-supersecret",
        )

        posts = [r for r in self.server.requests if r["method"] == "POST"]
        self.assertEqual(len(posts), 1)

    def test_missing_token_blocks_the_pull_request_without_any_request(self):
        with self.assertRaises(Exception) as ctx:
            self.gh.create_pull_request(
                project_path=str(self.project), repo="owner/name",
                head="feature/ap6", base="main", title="t", body="b",
                api=self.server.base, token=None,
            )

        self.assertTrue(str(ctx.exception).startswith(NO_TOKEN_PREFIX))
        self.assertEqual(self.server.requests, [])

    def test_pull_request_resolves_the_token_from_the_environment(self):
        os.environ["GITHUB_TOKEN"] = "t-from-env"

        self.gh.create_pull_request(
            project_path=str(self.project), repo="owner/name",
            head="feature/ap6", base="main", title="t", body="b",
            api=self.server.base, token=None,
        )

        self.assertEqual(self.server.last_pr["headers"]["authorization"], "Bearer t-from-env")

    def test_error_status_is_mapped_to_a_clear_message(self):
        self.server.httpd.pr_status = 422
        self.server.httpd.pr_payload = {"message": "Validation Failed"}

        with self.assertRaises(Exception) as ctx:
            self.gh.create_pull_request(
                project_path=str(self.project), repo="owner/name",
                head="feature/ap6", base="main", title="t", body="b",
                api=self.server.base, token="t-supersecret",
            )

        self.assertIn("422", str(ctx.exception))
        self.assertIn("Validation Failed", str(ctx.exception))

    def test_error_messages_never_leak_the_token(self):
        secret = "t-absolut"  # kurzes Fake-Literal; check-no-secrets akzeptiert < 16 Zeichen
        self.server.httpd.pr_status = 401
        self.server.httpd.pr_payload = {"message": "Bad credentials"}

        with self.assertRaises(Exception) as ctx:
            self.gh.create_pull_request(
                project_path=str(self.project), repo="owner/name",
                head="feature/ap6", base="main", title="t", body="b",
                api=self.server.base, token=secret,
            )

        message = str(ctx.exception)
        self.assertNotIn(secret, message)
        self.assertIn("401", message)


class IssuesImportRemovalTest(ProjectFixture):
    """GH-47: der getrennte Importpfad ist entfallen.

    ``list_issues`` bleibt als eigenständiger REST-Helper bestehen; die
    Ticketübernahme läuft ausschließlich über den einen Issues-Sync
    (``vibe_issues.sync_issues``).
    """

    def test_import_helper_is_removed_and_list_issues_stays(self):
        self.assertFalse(hasattr(self.gh, "import_issues_into_tickets"),
                         "import_issues_into_tickets existiert noch")
        self.assertTrue(callable(getattr(self.gh, "list_issues", None)),
                        "list_issues muss als REST-Helper erhalten bleiben")


# ------------------------------------------------------------------- CLI actions
class CliGithubTest(ProjectFixture):
    """CLI commands; the interface must not push or call any API implicitly."""

    def test_status_prints_branch_and_remote_facts(self):
        bare = self.make_bare("status-bare")
        git(self.project, "remote", "add", "origin", "file://" + str(bare))

        result, out, _ = self.run_cli("status")

        self.assertIn("main", out)
        self.assertIn("origin", out)

    def test_pr_without_confirm_never_pushes_or_calls_the_api(self):
        server = FakeGitHubServer().start()
        self.addCleanup(server.close)
        self.cli.set_env_values(
            "proj",
            {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name", "GITHUB_API": server.base},
        )
        head_before = git_out(self.project, "rev-parse", "HEAD")

        self.run_cli("pr", title="Merge-Ziehungs-Anfrage")

        self.assertEqual(server.requests, [])
        self.assertEqual(git_out(self.project, "rev-parse", "HEAD"), head_before)


# GH-76: Die früheren deutschen Commit-Regeln (GENERAL_RULES/Vorlagen) sind
# durch die englischen Plattformanweisungen ersetzt. Deren Commit-Vertrag
# (``<ID>:``-Betreff) wird in
# ``tests.unit.test_gh76_platform_instructions`` geprüft; hier bleibt der
# GitHub-spezifische Commit-Pfad unverändert.


# ------------------------------------------------- Review round 1 (new cases)
class DefaultBaseTest(ProjectFixture):
    """PR without base resolves the default branch name of origin (review R1)."""

    def setUp(self):
        super().setUp()
        self.origin = self.make_bare("origin-bare")
        self.add_origin(self.origin)
        git(self.project, "push", "-q", "-u", "origin", "main")
        git(self.project, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.server = FakeGitHubServer().start()
        self.addCleanup(self.server.close)
        self.cli.set_env_values(
            "proj",
            {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name", "GITHUB_API": self.server.base},
        )

    def test_default_base_resolves_the_branch_name_of_origin_head(self):
        self.assertEqual(self.gh.default_base(str(self.project)), "main")

    def test_pr_without_base_names_the_default_branch_not_a_commit_sha(self):
        self.gh.create_pull_request(
            project_path=str(self.project), repo="owner/name",
            head="feature/ap6", base=None, title="t", body="b",
            api=self.server.base, token="t-short",
        )

        sent = self.server.last_pr
        self.assertEqual(sent["body"]["base"], "main")
        self.assertNotRegex(sent["body"]["base"], r"^[0-9a-f]{40}$")

    def test_unknown_default_base_fails_usably_without_any_request(self):
        git(self.project, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/nope")

        with self.assertRaises(Exception) as ctx:
            self.gh.create_pull_request(
                project_path=str(self.project), repo="owner/name",
                head="feature/ap6", base=None, title="t", body="b",
                api=self.server.base, token="t-short",
            )

        self.assertTrue(str(ctx.exception))
        self.assertEqual(self.server.requests, [])


class RemotesMaskingTest(ProjectFixture):
    """remotes()/status() mask embedded credentials in URLs (review R1)."""

    def setUp(self):
        super().setUp()
        self.bare = self.make_bare("masked-bare")
        # Credentials stay inside the test tempdir and are tiny (fake data).
        git(self.project, "remote", "add", "origin", "https://t-kl:pw7@host/netz/pfad.git")
        git(self.project, "remote", "add", "upstream", "file://" + str(self.bare))

    def test_remotes_masks_embedded_credentials_and_keeps_the_rest(self):
        pairs = self.gh.remotes(str(self.project))
        origin = [r for r in pairs if r.get("name") == "origin"][0]
        url = origin.get("url") or (origin.get("fetch") or [None])[0]

        self.assertIn("***", url)
        self.assertTrue(str(url).startswith("https://***"), url)
        self.assertIn("host/netz/pfad.git", url)
        self.assertNotIn("t-kl", str(url))
        self.assertNotIn("pw7", str(url))

    def test_status_never_exposes_the_credentials_either(self):
        info = self.gh.status(str(self.project))

        for entry in info["remotes"]:
            self.assertNotIn("t-kl", str(entry.get("url") or ""))
            self.assertNotIn("pw7", str(entry.get("url") or ""))

    def test_plain_urls_stay_the_same(self):
        pairs = self.gh.remotes(str(self.project))
        upstream = [r for r in pairs if r.get("name") == "upstream"][0]
        url = upstream.get("url") or (upstream.get("fetch") or [None])[0]

        self.assertEqual(url, "file://" + str(self.bare))


# ------------------------------------------------ Standalone push (review R1)
class CliPushTest(ProjectFixture):
    """Own push action: ``vibe github <proj> push`` without a merge request."""

    def run_push(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = 0
        # LC_ALL=C macht die Git-Fehlermeldung deterministisch (keine
        # lokalisierte Übersetzung); der Test prüft den gemeldeten Kern.
        with mock.patch.dict(os.environ, {"LC_ALL": "C", "LANG": "C"}):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    self.cli.cmd_github("proj", "push", out=stdout)
                except SystemExit as exc:
                    exit_code = 0 if exc.code in (None, "") else int(exc.code)
        return exit_code, stdout.getvalue() + stderr.getvalue()

    def test_cli_push_publishes_the_pending_commit_to_origin(self):
        origin = self.make_bare("push-bare")
        self.add_origin(origin)
        git(self.project, "push", "-q", "-u", "origin", "main")
        commit_file(self.project, "neu2.txt", "einmal", "AP6: push sichtbar")

        code, output = self.run_push()

        self.assertEqual(code, 0, output)
        self.assertIn("übertragen", output)
        self.assertIn("origin", output)
        remote_tip = git_out(self.project, "ls-remote", "origin", "refs/heads/main").split()[0]
        self.assertEqual(remote_tip, git_out(self.project, "rev-parse", "HEAD"))

    def test_cli_push_without_any_remote_reports_the_problem(self):
        code, output = self.run_push()

        # Intent: Das Fehlen eines Remotes darf nicht verschluckt werden.
        # Geprüft wird der Exit-Code und eine stabile, mit LC_ALL=C erzeugte
        # Git-Fehlerkernstelle — nicht der frühere deutsche Substring
        # "Remote", den Git selbst nicht ausgibt.
        self.assertEqual(code, 1, output)
        self.assertTrue(output.strip(), "push meldete gar nichts")
        self.assertTrue(
            "does not appear to be a git repository" in output
            or "Could not read from remote repository" in output,
            "Git-Fehlerkern fehlt in der Meldung: " + output,
        )


class CheckApiTest(unittest.TestCase):
    """check_api: scheme and host validated, readable errors (review R1)."""

    def setUp(self):
        self.gh = github_module()

    def test_official_and_local_apis_are_accepted(self):
        for url in ("https://api.github.com", "http://127.0.0.1:8000", "https://vibe.invalid/api"):
            with self.subTest(url=url):
                self.gh.check_api(url)  # valid: does not raise

    def test_bad_schemas_missing_hosts_and_control_chars_are_refused(self):
        for url in ("ftp://host/rest", "not-a-url", "https://", "https://host/x\t"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as ctx:
                    self.gh.check_api(url)
                self.assertTrue(str(ctx.exception))


class LinkMessageMaskingTest(ProjectFixture):
    """R2-3/Minor: Die link-Erfolgsmeldung zeigt Zugangsdaten aus
    eingebetteten URLs nie im Klartext; Schema/Host/Pfad bleiben erkennbar."""

    def test_link_success_message_masks_embedded_credentials(self):
        # Kurze Fake-Kontodaten (< 16 Zeichen) — check-no-secrets-Heuristik.
        url = "https://v-kl:pw7@github.com/owner/repo.git"

        result, out, err = self.run_cli("link", url)
        printed = out + err

        self.assertIn("Verknüpft", printed)
        self.assertNotIn("v-kl", printed)
        self.assertNotIn("pw7", printed)
        for fragment in ("https://", "github.com/owner/repo", "***"):
            self.assertIn(fragment, printed, fragment)


# =============================== Review Runde 2 (Medium/Medium/Minor) ===============================
# Die Testfälle wurden vor der zugehörigen Implementierung geschrieben (Rotphase
# protokolliert unter /tmp/opencode/ap6-r2-*.log). Sie sind aus dem Review-Befund
# und der fachlichen Akzeptanz (TICKETS.md AP6, AGENTS.md) abgeleitet.
class GithubSlugDotNameTest(unittest.TestCase):
    """R2-1/Medium: Repo-Namen mit Punkt sind zulässig, ./..-Segmente bleiben
    verständlich abgelehnt (Schnittstelle: parse_remote_url in bin/vibe_github.py)."""

    def setUp(self):
        self.gh = github_module()

    def test_repo_names_with_dots_are_accepted_in_url_and_scp_form(self):
        cases = (
            ("https://github.com/owner/my.repo.git", "owner/my.repo"),
            ("https://github.com/owner/my.repo", "owner/my.repo"),
            ("git@github.com:owner/my.repo.git", "owner/my.repo"),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(self.gh.parse_remote_url(url), expected)

    def test_dot_and_dotdot_path_segments_stay_refused(self):
        for url in ("https://github.com/owner/../name",
                    "https://github.com/owner/./name",
                    "https://github.com/./name"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError) as ctx:
                    self.gh.parse_remote_url(url)
                self.assertTrue(str(ctx.exception))

    def test_dotless_slugs_still_resolve_as_before(self):
        self.assertEqual(
            self.gh.parse_remote_url("https://github.com/owner/name.git"),
            "owner/name",
        )


class LinkDotSlugTest(ProjectFixture):
    """R2-1/Medium über die CLI-Verknüpfung: link gelingt vollständig für
    Repo-Namen mit Punkt und bleibt ohne Wirkung bei ./..-Pfadabschnitten."""

    def test_link_with_dotted_repo_name_persists_the_full_slug(self):
        url = "https://github.com/owner/my.repo.git"
        before = self.env_path.read_text(encoding="utf-8")

        self.run_cli("link", url)

        self.assertEqual(git_out(self.project, "remote", "get-url", "origin"), url)
        after = self.env_path.read_text(encoding="utf-8")
        self.assertIn('GITHUB_ENABLED="1"', after)
        self.assertIn('GITHUB_REPO="owner/my.repo"', after)
        for line in before.splitlines():
            self.assertIn(line, after.splitlines())
        self.assertEqual(after.count("TESTER="), 1)

    def test_link_refuses_dotdot_path_segments_without_any_change(self):
        for bad in ("https://github.com/owner/../name",
                    "https://github.com/owner/./name"):
            with self.subTest(url=bad):
                before_remotes = git_out(self.project, "remote", "-v")
                before_env = self.env_path.read_text(encoding="utf-8")
                try:
                    self.run_cli("link", bad)
                except (ValueError, SystemExit):
                    pass  # laut verweigern ist genauso zulässig wie eine Meldung
                self.assertEqual(git_out(self.project, "remote", "-v"), before_remotes)
                self.assertEqual(self.env_path.read_text(encoding="utf-8"), before_env)


class DefaultBaseAfterLinkTest(ProjectFixture):
    """R2-2/Medium: Nach link (echter lokaler origin via ``remote add``, kein
    Klon) MUSS origin/HEAD existieren, so dass default_base ohne Vorarbeit
    "main" liefert und der CLI-Merge-Request ohne --base "main" sendet."""

    def setUp(self):
        super().setUp()
        self.bare = self.make_bare("r2-bare")
        # `remote add` statt `clone`: dadurch ist refs/remotes/origin/HEAD
        # vor der link-Verarbeitung garantiert nicht gesetzt (experimentell
        # verifiziert: push -u schreibt nur refs/remotes/origin/main).
        self.add_origin(self.bare)
        git(self.project, "push", "-q", "-u", "origin", "main")
        # Fixture-Invariante als Vorbedingungsnachweis:
        before_head = git(self.project, "symbolic-ref", "refs/remotes/origin/HEAD",
                          check=False)
        self.assertNotEqual(before_head.returncode, 0,
                            "Vorbedingung verletzt: origin/HEAD existierte schon")
        self.assertEqual(self.gh.default_base(str(self.project)), "")

    def link_only(self):
        self.run_cli("link", "file://" + str(self.bare))

    def test_link_establishes_origin_head_and_default_base_is_main(self):
        self.link_only()

        original = git(self.project, "symbolic-ref", "refs/remotes/origin/HEAD",
                       check=False)
        self.assertEqual(original.returncode, 0, original.stdout + original.stderr)
        self.assertEqual(original.stdout.strip(), "refs/remotes/origin/main")
        self.assertEqual(self.gh.default_base(str(self.project)), "main")

    def test_cli_merge_request_without_base_sends_main_and_succeeds(self):
        self.link_only()
        server = FakeGitHubServer().start()
        self.addCleanup(server.close)
        # github_pr liest den Token aus GITHUB_TOKEN|GH_TOKEN; die Fixture
        # entfernt solche Werte, hier gilt ein kurzes Fake-Literal.
        os.environ["GITHUB_TOKEN"] = "t-nur-test"
        self.addCleanup(self.restore_token_env)
        self.cli.set_env_values(
            "proj", {"GITHUB_REPO": "owner/name", "GITHUB_API": server.base}
        )

        result = self.cli.github_pr(
            "proj", title="R2: Merge-Request", base=None, confirm=True
        )

        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("base"), "main")
        self.assertEqual(result.get("number"), 42)
        self.assertIn("pull/42", str(result.get("url")))
        sent = server.last_pr
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["path"], "/repos/owner/name/pulls")
        self.assertEqual(sent["body"]["base"], "main")
        self.assertNotRegex(sent["body"]["base"], r"^[0-9a-f]{7,40}$")

    def test_cli_pr_flow_does_not_end_in_the_base_dead_end(self):
        self.link_only()
        server = FakeGitHubServer().start()
        self.addCleanup(server.close)
        os.environ["GITHUB_TOKEN"] = "t-nur-test"
        self.addCleanup(self.restore_token_env)
        out = err = ""
        self.cli.set_env_values(
            "proj", {"GITHUB_REPO": "owner/name", "GITHUB_API": server.base}
        )
        try:
            result, out, err = self.run_cli("pr", title="R2: per CLI", confirm=True)
        except SystemExit as exc:
            self.fail("PR-Klick-Fluss endet in der Sackgasse: %r (%s) (%s)"
                      % (exc.code, out, err))
        self.assertIn("Merge-Request erstellt", out)
        self.assertIn("pull/42", out)


# ===========================================================================
# Abnahme „Bereit für Github Teil 3“: Projekt-Token, Branch-Kontrolle
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


FAKE_TOKEN = "ap9-unit-projekt-token-111"
ENV_TOKEN = "ap9-unit-env-token-222"
LEGACY_TOKEN = "ap9-unit-legacy-token-333"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
)

GIT_IDENTITY_ap9 = {
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

_GH_CACHE = {}


def github_module_ap9():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_ap9_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def real_git(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität, nie gerichtete Netzaufrufe."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY_ap9)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def real_git_out(cwd, *argv):
    return real_git(cwd, *argv).stdout.strip()


def make_project(root, name="proj", env_extra=""):
    """Minimales eigenes Git-Projekt ohne Remote."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    real_git(project, "init", "-q", "-b", "main")
    real_git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir(exist_ok=True)
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n" + env_extra, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


def seed_bare(root, name, files=None, extra_branch=None):
    """Lokale Bare-Quelle ohne Netz; liefert die file://-Adresse."""
    work = Path(root) / "seed" / name
    work.mkdir(parents=True, exist_ok=True)
    for relative, content in (files or {"README.md": "Inhalt\n"}).items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    real_git(work, "init", "-q", "-b", "main")
    real_git(work, "add", "-A")
    real_git(work, "commit", "-q", "-m", "seed")
    if extra_branch:
        real_git(work, "checkout", "-q", "-b", extra_branch)
        (work / "branch-file.txt").write_text(extra_branch, encoding="utf-8")
        real_git(work, "add", "-A")
        real_git(work, "commit", "-q", "-m", "branch-" + extra_branch)
        real_git(work, "checkout", "-q", "main")
    bare = Path(root) / "origin" / (name + ".git")
    bare.mkdir(parents=True, exist_ok=True)
    real_git(bare, "init", "-q", "--bare")
    real_git(work, "push", "-q", str(bare), "main")
    if extra_branch:
        real_git(work, "push", "-q", str(bare), extra_branch)
    real_git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare)


# ---------------------------------------------------------------- REST-Fake
class _RestHandler(BaseHTTPRequestHandler):
    """REST-Fake auf 127.0.0.1; protokolliert Pfad und Authorization."""

    def log_message(self, fmt, *args):
        pass

    def _record(self):
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
        })

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._record()
        if self.path.startswith("/repos/owner/name"):
            self._respond(self.server.repo_status, {"full_name": "owner/name"})
        else:
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record()
        self.server.posts.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
        })
        self._respond(self.server.post_status, {
            "number": 42, "html_url": "http://127.0.0.1/pull/42"})


class RestFakeServer:
    """Fake-API nur für 127.0.0.1; Tests prüfen jede aufgezeichnete Anfrage."""

    def __init__(self, repo_status=200, post_status=201):
        self.requests = []
        self.posts = []
        self.repo_status = repo_status
        self.post_status = post_status
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            self._port = sock.getsockname()[1]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self._port), _RestHandler)
        self.httpd.requests = self.requests
        self.httpd.posts = self.posts
        self.httpd.repo_status = repo_status
        self.httpd.post_status = post_status
        self.thread = None

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self._port

    def start(self):
        self.thread = __import__("threading").Thread(
            target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


# ------------------------------------------------------------ gemeinsame Basis
class AP9Case(unittest.TestCase):
    """Isolierte Umgebung: temporäres VIBE_STATE, keine Token im ENV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy", "https_proxy",
                    "all_proxy", "VIBE_GITHUB_CREDENTIAL"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module_ap9()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def token_file_for(self, project_path):
        digest = hashlib.sha256(
            os.path.realpath(str(project_path)).encode("utf-8")).hexdigest()[:16]
        return self.state / "github-tokens" / (digest + ".json")

    def master_key_path(self):
        return self.state / "github-token.key"

    def chmod_effective(self):
        probe = self.base / ".chmod-probe"
        probe.write_text("x", encoding="utf-8")
        try:
            os.chmod(probe, 0o600)
            return stat.S_IMODE(os.stat(probe).st_mode) == 0o600
        finally:
            probe.unlink()

    def not_disclosed(self, text):
        for secret in (FAKE_TOKEN, ENV_TOKEN, LEGACY_TOKEN):
            self.assertNotIn(secret, text, secret)


# ============================================================ Token-Speicher
class ProjectTokenStoreTest(AP9Case):
    """AK Token je Projekt, verschlüsselt (AP9 Punkt 1)."""

    def test_save_and_read_roundtrip_keeps_the_exact_token(self):
        project = make_project(self.base, "rundtrip")
        self.assertFalse(self.token_file_for(project).exists())

        self.gh.save_project_token(project, FAKE_TOKEN)

        self.assertEqual(FAKE_TOKEN, self.gh.read_project_token(project))
        self.assertTrue(self.token_file_for(project).is_file(),
                        "Token muss unter <VIBE_STATE>/github-tokens liegen")

    def test_two_projects_get_separate_tokens(self):
        one = make_project(self.base, "eins")
        two = make_project(self.base, "zwei")

        self.gh.save_project_token(one, FAKE_TOKEN)
        self.gh.save_project_token(two, ENV_TOKEN)

        self.assertEqual(FAKE_TOKEN, self.gh.read_project_token(one))
        self.assertEqual(ENV_TOKEN, self.gh.read_project_token(two))
        self.assertNotEqual(self.token_file_for(one), self.token_file_for(two),
                            "Projekte dürfen sich keinen Token-Eintrag teilen")

    def test_token_file_name_is_the_realpath_hash(self):
        project = make_project(self.base, "hashprobe")
        self.gh.save_project_token(project, FAKE_TOKEN)

        expected = self.token_file_for(project)
        self.assertTrue(expected.is_file())
        # Ein symbolischer Link auf dasselbe Projekt zeigt auf denselben
        # Eintrag (realpath, nicht die angegebene Schreibweise).
        link = self.base / "verweis"
        link.symlink_to(project, target_is_directory=True)
        self.assertEqual(FAKE_TOKEN, self.gh.read_project_token(link))

    def test_stored_file_is_encrypted_and_never_carries_the_plaintext(self):
        project = make_project(self.base, "chiffre")
        self.gh.save_project_token(project, FAKE_TOKEN)

        raw = self.token_file_for(project).read_text(encoding="utf-8")
        self.assertNotIn(FAKE_TOKEN, raw,
                         "Der Klartext-Token darf nie in der Ablage stehen")
        data = json.loads(raw)
        strings = [value for value in data.values() if isinstance(value, str)]
        self.assertTrue(strings, "Chiffrat-JSON erwartet")
        self.assertTrue(any(value != FAKE_TOKEN for value in strings),
                        "Die Ablage ist kein Klartext-Spiegel: %r" % (data,))
        self.assertNotEqual(FAKE_TOKEN,
                            json.dumps(data, ensure_ascii=False))

    def test_master_key_is_created_once_with_32_random_bytes(self):
        project = make_project(self.base, "schluessel")

        self.gh.save_project_token(project, FAKE_TOKEN)

        key = self.master_key_path()
        self.assertTrue(key.is_file(), "Masterschlüssel fehlt")
        first = key.read_bytes()
        self.assertEqual(32, len(first),
                         "Der Masterschlüssel braucht 32 zufällige Bytes")
        second_project = make_project(self.base, "schluessel2")
        self.gh.save_project_token(second_project, ENV_TOKEN)
        self.assertEqual(first, key.read_bytes(),
                         "Ein erneuter Save darf den Masterschlüssel nicht "
                         "drehen (sonst sind alte Einträge verloren)")

    def test_file_and_directory_permissions_best_effort(self):
        project = make_project(self.base, "rechte")
        if not self.chmod_effective():
            self.skipTest("Dateisystem ohne wirksame Unix-Rechte (FUSE/NTFS)")

        self.gh.save_project_token(project, FAKE_TOKEN)

        mode = stat.S_IMODE(os.stat(self.token_file_for(project)).st_mode)
        self.assertEqual(0o600, mode, "Token-Datei braucht 0600")
        folder = self.token_file_for(project).parent
        self.assertEqual(0o700, stat.S_IMODE(os.stat(folder).st_mode),
                         "Token-Ordner braucht 0700")

    def test_invalid_tokens_are_rejected_without_side_effects(self):
        project = make_project(self.base, "ablehnung")
        bad_values = ("", "   ", "ab\x00cd", "ab\ncd", "ab\rcd", "\tsecret")

        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_project_token(project, bad)
        self.assertFalse(self.token_file_for(project).exists(),
                         "Ein abgelehnter Save darf keine Reste hinterlassen")

        self.gh.save_project_token(project, FAKE_TOKEN)
        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_project_token(project, bad)
        self.assertEqual(FAKE_TOKEN, self.gh.read_project_token(project),
                         "Ungültige Eingaben dürfen den gespeicherten Token "
                         "nicht beschädigen")

    def test_read_tolerates_missing_entry(self):
        project = make_project(self.base, "fehlt")
        self.assertEqual("", self.gh.read_project_token(project))

    def test_read_tolerates_corrupt_json(self):
        project = make_project(self.base, "kaputt")
        self.gh.save_project_token(project, FAKE_TOKEN)
        self.token_file_for(project).write_text("{kein json", encoding="utf-8")

        self.assertEqual("", self.gh.read_project_token(project),
                         "Ein defekter Eintrag darf keine Ausnahme werfen")

    def test_tampered_ciphertext_returns_empty_string(self):
        project = make_project(self.base, "manipuliert")
        self.gh.save_project_token(project, FAKE_TOKEN)
        path = self.token_file_for(project)
        data = json.loads(path.read_text(encoding="utf-8"))
        longest = max((value for value in data.values() if isinstance(value, str)),
                      key=len)
        flipped = ("X" if longest[0] != "X" else "Y") + longest[1:]
        data["manipuliert"] = flipped
        # Ein Bit im Chiffrat kippen: Feld bewusst verdrehen, ohne Struktur
        # zu zerstören (implementationenneutral: längstes Zeichenkettenfeld).
        fields = {}
        for key, value in data.items():
            fields[key] = flipped if value == longest else value
        path.write_text(json.dumps(fields), encoding="utf-8")

        self.assertEqual("", self.gh.read_project_token(project),
                         "Ein leicht verändertes Chiffrat ist als manipuliert "
                         "zu erkennen und liefert keinen Token")

    def test_delete_removes_token_and_tolerates_missing_file(self):
        project = make_project(self.base, "loeschprobe")
        self.gh.delete_project_token(project)  # fehlende Datei: kein Fehler

        self.gh.save_project_token(project, FAKE_TOKEN)
        self.assertTrue(self.token_file_for(project).exists())

        self.gh.delete_project_token(project)
        self.assertFalse(self.token_file_for(project).exists())
        self.assertEqual("", self.gh.read_project_token(project))

        self.gh.delete_project_token(project)  # tolerant, kein zweiter Fehler


class TokenPrecedenceTest(AP9Case):
    """AK Token-Präzedenz: Umgebung > Projekt > legacy globaler Token."""

    def test_token_status_reports_environment_first_then_project_then_legacy(self):
        project = make_project(self.base, "praezedenz")
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ.pop("GH_TOKEN", None)
        self.assertEqual({"set": False, "source": ""},
                         self.gh.token_status(project))

        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status(project))

        os.environ.pop("GITHUB_TOKEN", None)
        self.gh.save_project_token(project, FAKE_TOKEN)
        self.assertEqual({"set": True, "source": "projekt"},
                         self.gh.token_status(project),
                         "Ohne Umgebungstoken gewinnt der Projekt-Token")

        self.gh.delete_project_token(project)
        self.gh.save_token(LEGACY_TOKEN)  # legacy globaler Token (B7)
        self.assertEqual({"set": True, "source": "gespeichert"},
                         self.gh.token_status(project),
                         "Ohne Projekt-Token bleibt der legacy Token Rückfall")

    def test_token_for_rest_environment_token_wins_everywhere(self):
        project = make_project(self.base, "rest-env")
        self.gh.save_project_token(project, FAKE_TOKEN)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN

        self.assertEqual(ENV_TOKEN, self.gh.token_for_rest(OFFICIAL_API, project))
        self.assertEqual(ENV_TOKEN, self.gh.token_for_rest("http://127.0.0.1:9/v3", project))

    def test_project_token_goes_only_to_the_official_api(self):
        project = make_project(self.base, "rest-projekt")
        self.gh.save_project_token(project, FAKE_TOKEN)

        self.assertEqual(FAKE_TOKEN, self.gh.token_for_rest(OFFICIAL_API, project))
        self.assertEqual(FAKE_TOKEN, self.gh.token_for_rest(None, project))
        self.assertEqual("", self.gh.token_for_rest("http://127.0.0.1:9/v3", project),
                         "Der gespeicherte Projekt-Token gehört nie zu einer "
                         "konfigurierten Fremd-API")

    def test_legacy_saved_token_remains_fallback_for_the_official_api(self):
        project = make_project(self.base, "rest-legacy")
        self.gh.save_token(LEGACY_TOKEN)

        self.assertEqual(LEGACY_TOKEN, self.gh.token_for_rest(OFFICIAL_API, project))
        self.assertEqual("", self.gh.token_for_rest("http://127.0.0.1:9/v3", project))


# ------------------------------------------------------ Git-Credential-Route
def make_git_stub(calls, branch="main"):
    """Ersetzt subprocess.run: protokolliert argv, cwd und ENV vollständig."""

    def stub(argv, **kwargs):
        record = {
            "argv": list(str(a) for a in argv),
            "cwd": kwargs.get("cwd"),
            "env": dict(kwargs.get("env") or {}),
        }
        calls.append(record)
        verb = str(argv[0])
        rest = record["argv"][1:]
        skip = 0
        for value in rest:
            if value.startswith("-"):
                skip += 1
        verb = rest[skip] if skip < len(rest) else ""
        if verb == "symbolic-ref":
            return types.SimpleNamespace(returncode=0, stdout=branch, stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    return stub


class GitCredentialRoutingTest(AP9Case):
    """AK Credential-Injection: Projekt-Token in der Prozessumgebung, nie argv."""

    def setUp(self):
        super().setUp()
        self.project = self.base / "credproj"
        self.project.mkdir()

    def test_git_uses_project_token_without_token_in_argv(self):
        self.gh.save_project_token(self.project, FAKE_TOKEN)
        calls = []
        with mock.patch("subprocess.run", make_git_stub(calls)):
            self.gh.git(self.project, "fetch", "--dry-run")

        self.assertTrue(calls)
        record = calls[-1]
        joined = "\n".join(record["argv"])
        self.assertNotIn(FAKE_TOKEN, joined, "Tokeninhalt darf nie in argv stehen")
        haystack = joined + "\n" + "\n".join(record["env"].keys())
        self.assertIn("credential.https://github.com.helper", haystack,
                      "URL-gültige Credential-Konfiguration erwartet")
        self.assertTrue(any(FAKE_TOKEN in str(value)
                            for value in record["env"].values()),
                        "Der Projekt-Token wird über die Prozessumgebung "
                        "eingespeist (env-Schlüssel=%r)" % sorted(record["env"]))

    def test_git_prefers_the_environment_token_over_the_project_token(self):
        self.gh.save_project_token(self.project, FAKE_TOKEN)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        calls = []
        with mock.patch("subprocess.run", make_git_stub(calls)):
            self.gh.git(self.project, "fetch", "--dry-run")

        record = calls[-1]
        env_values = "\n".join(str(value) for value in record["env"].values())
        self.assertIn(ENV_TOKEN, env_values)
        self.assertNotIn(FAKE_TOKEN, env_values,
                         "Die Umgebung gewinnt über den Projekt-Token")

    def test_git_falls_back_to_the_legacy_saved_token(self):
        self.gh.save_token(LEGACY_TOKEN)
        calls = []
        with mock.patch("subprocess.run", make_git_stub(calls)):
            self.gh.git(self.project, "fetch", "--dry-run")

        record = calls[-1]
        env_values = "\n".join(str(value) for value in record["env"].values())
        self.assertIn(LEGACY_TOKEN, env_values)
        self.assertNotIn(LEGACY_TOKEN, "\n".join(record["argv"]))


# ================================================================== read_config
class ConfigBaseTest(AP9Case):
    """AK Mehr Branch-Kontrolle: Basis-Branch für Merge-Requests."""

    def test_read_config_reports_the_configured_base(self):
        project = make_project(self.base, "basis",
                               env_extra='GITHUB_BASE="develop"\n')

        config = self.gh.read_config(project / ".vibe" / "project.env")

        self.assertIn("base", config, "read_config braucht das Feld base")
        self.assertEqual("develop", config["base"])

    def test_read_config_defaults_to_an_empty_base(self):
        project = make_project(self.base, "basis-leer")

        config = self.gh.read_config(project / ".vibe" / "project.env")

        self.assertIn("base", config, "Das Feld base muss immer vorhanden sein")
        self.assertEqual("", config["base"])
        self.assertIn("enabled", config)
        self.assertIn("repo", config)


# ============================================================ checkout_branch
class CheckoutBranchTest(AP9Case):
    """AK Mehr Branch-Kontrolle: Branch auschecken mit Schutzregeln."""

    def setUp(self):
        super().setUp()
        self.project = make_project(self.base, "zweigwerk")
        self.bare_url = seed_bare(self.base, "zweigwerk-origin",
                                  extra_branch="feature/arbeit")
        real_git(self.project, "remote", "add", "origin", self.bare_url)
        real_git(self.project, "fetch", "-q", "origin")
        real_git(self.project, "branch", "--set-upstream-to",
                 "origin/main", "main", check=False)

    def current(self):
        return real_git_out(self.project, "rev-parse", "--abbrev-ref", "HEAD")

    def test_invalid_branch_names_raise_valueerror(self):
        for bad in ("", "..", "arbeit.lock", "-vornull", "weiß leer", "feat;x"):
            with self.subTest(branch=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.checkout_branch(self.project, bad)

    def test_dirty_worktree_rejects_the_checkout_and_stays_on_branch(self):
        """Tracked, uncommitierte Änderungen blockieren den Wechsel (git-
        Semantik: nur im Wechsel gefährdete Änderungen zählen)."""
        # make_project committet leer: TICKETS.md wird erst zur tracked
        # Basis gemacht, dann bearbeitet (sonst wäre die Änderung untracked).
        readme = self.project / "TICKETS.md"
        real_git(self.project, "add", "TICKETS.md")
        real_git(self.project, "commit", "-q", "-m", "tickets")
        original = readme.read_text(encoding="utf-8")
        readme.write_text(original + "offene Bearbeitung\n", encoding="utf-8")
        before = self.current()

        with self.assertRaises(ValueError):
            self.gh.checkout_branch(self.project, "feature/arbeit")

        self.assertEqual(before, self.current(),
                         "Bei uncommitierten Änderungen darf nichts wechseln")
        self.assertIn("offene Bearbeitung\n", readme.read_text(encoding="utf-8"),
                      "Der Arbeitsbaum bleibt unangetastet")

    def test_already_checked_out_branch_reports_success(self):
        ok, message = self.gh.checkout_branch(self.project, "main")

        self.assertTrue(ok, message)
        self.assertTrue(str(message).strip(), "Meldung erwartet")
        self.assertEqual("main", self.current())

    def test_existing_local_branch_is_checked_out(self):
        real_git(self.project, "branch", "lokal/ebene")

        ok, message = self.gh.checkout_branch(self.project, "lokal/ebene")

        self.assertTrue(ok, message)
        self.assertEqual("lokal/ebene", self.current())

    def test_branch_that_only_exists_on_origin_is_created_locally(self):
        real_git(self.project, "branch", "-D", "feature/arbeit", check=False)
        self.assertNotEqual(
            0, real_git(self.project, "rev-parse", "-q", "--verify",
                        "refs/heads/feature/arbeit", check=False).returncode,
            "Vorbedingung: nur origin/feature/arbeit vorhanden")

        ok, message = self.gh.checkout_branch(self.project, "feature/arbeit")

        self.assertTrue(ok, message)
        self.assertEqual("feature/arbeit", self.current())
        self.assertEqual(
            0,
            real_git(self.project, "rev-parse", "-q", "--verify",
                     "refs/heads/feature/arbeit", check=False).returncode,
            "Es muss ein echter lokaler Branch entstehen")

    def test_unknown_branch_fails_with_a_clear_message(self):
        with self.assertRaises(ValueError) as thrown:
            self.gh.checkout_branch(self.project, "nirgendwo")

        self.assertIn("Branch nicht gefunden", str(thrown.exception))

    def test_checkout_never_runs_a_shell(self):
        """Ein Metazeichen-Name wird vorher abgelehnt; es entsteht keine Datei."""
        with self.assertRaises(ValueError):
            self.gh.checkout_branch(self.project, "feat;touch marker")

        self.assertFalse((self.base / "marker").exists(),
                         "Der Name wurde über eine Shell ausgeführt")


# ==================================================================== push
class PushTargetTest(AP9Case):
    """AK Mehr Branch-Kontrolle: pushen in einen gewählten Ziel-Branch."""

    def setUp(self):
        super().setUp()
        self.project = make_project(self.base, "schieber")
        self.bare_url = seed_bare(self.base, "schieber-origin")
        real_git(self.project, "remote", "add", "origin", self.bare_url)

    def new_branch(self, name):
        real_git(self.project, "checkout", "-q", "-b", name)
        (self.project / ("datei-" + name.replace("/", "-"))).write_text(
            name, encoding="utf-8")
        real_git(self.project, "add", "-A")
        real_git(self.project, "commit", "-q", "-m", name)

    def test_push_without_arguments_pushes_the_current_branch_and_sets_upstream(self):
        self.new_branch("feature/arbeit")
        tip = real_git_out(self.project, "rev-parse", "HEAD")

        ok, message = self.gh.push(self.project)

        self.assertTrue(ok, message)
        remote_tip = real_git_out(self.project, "ls-remote", "origin",
                                  "refs/heads/feature/arbeit").split()[0]
        self.assertEqual(tip, remote_tip,
                         "Der aktuelle Branch wurde nach origin übertragen")
        upstream = real_git_out(self.project, "rev-parse",
                                "--abbrev-ref", "feature/arbeit@{u}")
        self.assertEqual("origin/feature/arbeit", upstream,
                         "Der Upstream muss gesetzt werden")

    def test_push_moves_the_branch_to_the_requested_target(self):
        self.new_branch("feature/quelle")
        tip = real_git_out(self.project, "rev-parse", "HEAD")

        ok, message = self.gh.push(self.project, branch="feature/quelle",
                                   target="feature/ziel")

        self.assertTrue(ok, message)
        remote_tip = real_git_out(self.project, "ls-remote", "origin",
                                  "refs/heads/feature/ziel").split()[0]
        self.assertEqual(tip, remote_tip,
                         "Der Ziel-Branch erhält den Stand der Quelle")
        # origin/feature/quelle bleibt von dem gezielten Push unberührt:
        self.assertEqual(
            "", real_git_out(self.project, "ls-remote", "origin",
                             "refs/heads/feature/quelle"),
            "Ohne Ziel-Angabe soll die Quelle selbst nicht gepusht werden")

    def test_push_rejects_an_invalid_target_name(self):
        self.new_branch("feature/normal")

        with self.assertRaises(ValueError):
            self.gh.push(self.project, branch="feature/normal", target="böser Ziel")

        self.assertEqual(
            "", real_git_out(self.project, "ls-remote", "origin",
                             "refs/heads/feature/normal"),
            "Ein abgelehnter Push darf den Zweig nicht übertragen")

    def test_push_failure_reports_a_clear_message_without_exception(self):
        real_git(self.project, "remote", "set-url", "origin",
                 "file://" + str(self.base / "origin" / "nicht-da.git"))
        real_git(self.project, "commit", "--allow-empty", "-q", "-m", "weiter")

        ok, message = self.gh.push(self.project)

        self.assertFalse(ok)
        self.assertTrue(str(message).strip(), "Fehlermeldung erwartet")


# ============================================================== connection
class ConnectionTest(AP9Case):
    """AK UI-Feedback: Verbindungsprüfung ohne Ausnahme-Durchreich."""

    def test_connection_reports_a_working_remote_and_skips_rest_without_token(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = make_project(
            self.base, "verbunden",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\n' % server.base))
        bare_url = seed_bare(self.base, "verbunden-origin")
        real_git(project, "remote", "add", "origin", bare_url)

        view = self.gh.connection(project)

        self.assertIn("remote", view)
        self.assertIn("api", view)
        self.assertIn("ok", view)
        self.assertIn("message", view)
        self.assertTrue(view["remote"], "file://-origin muss erreichbar sein")
        self.assertIsNone(view["api"],
                          "Ohne Token bleibt die REST-Prüfung aus (Hinweis)")
        self.assertTrue(str(view["message"]).strip())
        self.not_disclosed(json.dumps(view, default=str))

    def test_connection_reports_a_working_rest_with_a_token(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = make_project(
            self.base, "rest-ok",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\n' % server.base))
        bare_url = seed_bare(self.base, "rest-ok-origin")
        real_git(project, "remote", "add", "origin", bare_url)
        self.gh.save_project_token(project, FAKE_TOKEN)

        view = self.gh.connection(project)

        self.assertTrue(view["api"], json.dumps(view, ensure_ascii=False))
        self.assertTrue(server.requests, "Die REST-Prüfung muss einen Abruf tätigen")
        self.assertIn("/repos/owner/name", server.requests[-1]["path"])
        self.not_disclosed(json.dumps(view, default=str))

    def test_connection_reports_a_broken_rest_without_raising(self):
        server = RestFakeServer(repo_status=404).start()
        self.addCleanup(server.close)
        project = make_project(
            self.base, "rest-schlecht",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\n' % server.base))
        bare_url = seed_bare(self.base, "rest-schlecht-origin")
        real_git(project, "remote", "add", "origin", bare_url)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN

        view = self.gh.connection(project)  # GitHubError wird gefangen

        self.assertFalse(view["api"], json.dumps(view, default=str))
        self.assertTrue(str(view["message"]).strip())
        self.not_disclosed(json.dumps(view, default=str))

    def test_connection_without_origin_reports_the_broken_remote(self):
        project = make_project(self.base, "ohne-fremd")

        view = self.gh.connection(project)

        self.assertFalse(view["remote"],
                         "Ohne origin ist die Fernverbindung kaputt")
        self.assertTrue(str(view["message"]).strip())


# ==================================================================== CLI
def write_cli_templates(install):
    """Vorlagen für Subprozessläufe: TPL liegt unter VIBE_INSTALL/templates."""
    templates = Path(install) / "templates"
    for typ, files in (
        ("common", {
            "FEEDBACK.md": "# FEEDBACK\n",
            "TICKETS.md": "# TICKETS\n",
            "opencode.json": '{\n  "$schema": "vorlage"\n}\n',
            ".opencode/agents/test-agent.md": "TEST-AGENT\n",
        }),
        ("generic", {
            "AGENTS.md": "# AGENTS fuer {{NAME}}\n",
            ".vibe/project.env": "TYPE=generic\nTESTER=test-agent\n",
        }),
    ):
        for relative, content in files.items():
            target = templates / typ / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


class CommandLineTest(unittest.TestCase):
    """CLI „vibe github …“ und „vibe clone … --branch“ (AP9-Erweiterungen)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "ws"
        self.workspace.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        write_cli_templates(self.install)

    def isolated_env(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE": str(self.workspace),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.install),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
        })
        env.update(GIT_IDENTITY_ap9)
        env["NO_PROXY"] = "127.0.0.1,localhost"
        return env

    def project(self, name, env_extra=""):
        project = make_project(self.workspace, name, env_extra=env_extra)
        return project

    def run_cli(self, *argv, env=None, input_text=None):
        return subprocess.run(
            [sys.executable, str(CLI), *argv],
            cwd=str(self.workspace), env=env or self.isolated_env(),
            input=input_text, capture_output=True, text=True,
            timeout=120, check=False,
        )

    def test_cli_checkout_switches_the_branch(self):
        project = self.project("zweig-cli")
        real_git(project, "branch", "feature/cli-zweig")

        result = self.run_cli("github", "zweig-cli", "checkout", "feature/cli-zweig")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertEqual("feature/cli-zweig",
                         real_git_out(project, "rev-parse", "--abbrev-ref", "HEAD"))
        self.assertTrue(output.strip())

    def test_cli_checkout_rejects_invalid_names_without_switching(self):
        project = self.project("zweig-cli2")

        result = self.run_cli("github", "zweig-cli2", "checkout", "böser zweig")

        self.assertNotEqual(0, result.returncode)
        self.assertTrue((result.stdout + result.stderr).strip())
        self.assertEqual("main",
                         real_git_out(project, "rev-parse", "--abbrev-ref", "HEAD"))

    def test_cli_test_reports_the_connection_without_a_token_leak(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.project(
            "test-cli",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\n' % server.base))
        bare_url = seed_bare(self.root, "test-cli-origin")
        real_git(project, "remote", "add", "origin", bare_url)
        env = self.isolated_env()
        # Projekt-Token in dem vom CLI genutzten Zustandsordner ablegen:
        gh = github_module_ap9()
        old_state = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = env["VIBE_STATE"]
        try:
            gh.save_project_token(project, FAKE_TOKEN)
        finally:
            if old_state is None:
                os.environ.pop("VIBE_STATE", None)
            else:
                os.environ["VIBE_STATE"] = old_state

        result = self.run_cli("github", "test-cli", "test", env=env)

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertTrue(output.strip(), "Meldung zum Verbindungsergebnis erwartet")
        self.assertNotIn(FAKE_TOKEN, output)

    def test_cli_push_transfers_a_named_branch(self):
        project = self.project("push-cli")
        bare_url = seed_bare(self.root, "push-cli-origin")
        real_git(project, "remote", "add", "origin", bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/cli-push")
        (project / "probe.txt").write_text("probe\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "probe")

        result = self.run_cli("github", "push-cli", "push", "feature/cli-push")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        remote_tip = real_git_out(project, "ls-remote", "origin",
                                  "refs/heads/feature/cli-push").split()[0]
        self.assertEqual(real_git_out(project, "rev-parse", "HEAD"), remote_tip)

    def test_cli_token_clear_removes_the_project_token(self):
        project = self.project("token-cli")
        env = self.isolated_env()
        gh = github_module_ap9()
        old_state = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = env["VIBE_STATE"]
        try:
            gh.save_project_token(project, FAKE_TOKEN)
        finally:
            if old_state is None:
                os.environ.pop("VIBE_STATE", None)
            else:
                os.environ["VIBE_STATE"] = old_state

        result = self.run_cli("github", "token-cli", "token", "clear", env=env)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        old_state = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = env["VIBE_STATE"]
        try:
            self.assertEqual("", gh.read_project_token(project),
                             "token clear entfernt den Projekt-Token")
        finally:
            if old_state is None:
                os.environ.pop("VIBE_STATE", None)
            else:
                os.environ["VIBE_STATE"] = old_state

    def test_cli_token_saves_the_piped_input_for_this_project(self):
        project = self.project("token-cli2")
        env = self.isolated_env()

        result = self.run_cli("github", "token-cli2", "token", env=env,
                              input_text=FAKE_TOKEN + "\n")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertNotIn(FAKE_TOKEN, output, "Der Token darf nicht echoen werden")
        gh = github_module_ap9()
        old_state = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = env["VIBE_STATE"]
        try:
            self.assertEqual(FAKE_TOKEN, gh.read_project_token(project),
                             "token speichert je Projekt")
        finally:
            if old_state is None:
                os.environ.pop("VIBE_STATE", None)
            else:
                os.environ["VIBE_STATE"] = old_state

    def _merge_request_cli(self, branch_argument):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.project(
            "pr-cli",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\nGITHUB_BASE="main"\n' % server.base))
        bare_url = seed_bare(self.root, "pr-cli-origin")
        real_git(project, "remote", "add", "origin", bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/pr-zweig")
        (project / "arbeit.txt").write_text("arbeit\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "arbeit")
        env = self.isolated_env()
        env["GITHUB_TOKEN"] = ENV_TOKEN
        argv = ["github", "pr-cli", "pr", "--confirm"]
        if branch_argument:
            argv += ["--branch", branch_argument]
        result = self.run_cli(*argv, env=env)
        return result, server, project

    def test_cli_pr_uses_the_given_branch_for_the_merge_request(self):
        result, server, _project = self._merge_request_cli("feature/pr-zweig")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        posts = [post for post in server.posts if post["path"].startswith(
            "/repos/owner/name/pulls")]
        self.assertTrue(posts, "Der Merge-Request muss beantragt werden")
        self.assertEqual("Bearer " + ENV_TOKEN, posts[-1]["authorization"])

    def test_cli_pr_defaults_to_the_current_branch(self):
        result, server, project = self._merge_request_cli(None)

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        posts = [post for post in server.posts if post["path"].startswith(
            "/repos/owner/name/pulls")]
        self.assertTrue(posts, "Standard-Zweig ist der ausgecheckte Branch")

    def test_cli_clone_checks_out_the_requested_branch(self):
        bare_url = seed_bare(self.root, "klonziel", extra_branch="feature/start")
        result = self.run_cli("clone", bare_url, "klonziel", "--branch",
                              "feature/start")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        project = self.workspace / "klonziel"
        self.assertTrue((project / ".git").is_dir())
        self.assertEqual("feature/start",
                         real_git_out(project, "rev-parse", "--abbrev-ref", "HEAD"))


# ===========================================================================
# GitHub-Authentifizierung über die Oberfläche (Nutzer-Feedback )
# ===========================================================================

import contextlib
import hashlib
import http.client
import importlib.machinery
import importlib.util
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

WEB = REPO / "bin" / "vibe-web.py"

FAKE_TOKEN_b7 = "b7-unit-fake-token-123"
ENV_TOKEN_b7 = "b7-unit-env-token-456"
OTHER_API = "http://127.0.0.1:9/v3"

GUIDANCE = re.compile(
    r"token|zugangsdaten|zugangstoken|authentifiz|anmelden|hinterlegen",
    re.IGNORECASE,
)

RAW_VARIANTS = {
    "could_not_read_username":
        "fatal: could not read Username for 'https://github.com': "
        "terminal prompts disabled",
    "terminal_prompts_only":
        "Schwerwiegend: could not read Username for 'https://github.com': "
        "terminal prompts disabled",
    "broken_askpass":
        "fatal: cannot exec '/usr/bin/ksshaskpass': "
        "Datei oder Verzeichnis nicht gefunden",
    "german_askpass_and_prompts":
        "Zusammenführen nicht möglich: Schwerwiegend: cannot exec "
        "'/usr/bin/ksshaskpass': Datei oder Verzeichnis nicht gefunden\n"
        "Schwerwiegend: could not read Username for 'https://github.com': "
        "terminal prompts disabled",
    "authentication_failed":
        "fatal: Authentication failed for 'https://github.com/'",
}

_ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy",
)


def github_module_b7():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _GH_CACHE:
        return _GH_CACHE["gh"]
    bin_dir = str(REPO / "bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_b7_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module

def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

GIT_IDENTITY_b7 = {
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

def real_git_b7(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität, nie dirigierte Netzaufrufe."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY_b7)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )

def make_project_b7(root, name="proj"):
    """Minimales eigenes Git-Projekt ohne Remote (Status bleibt offline)."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    real_git_b7(project, "init", "-q", "-b", "main", check=False)
    real_git_b7(project, "commit", "--allow-empty", "-q", "-m", "init", check=False)
    (project / ".vibe").mkdir(exist_ok=True)
    (project / ".vibe" / "project.env").write_text(
        'TYPE=generic\nTESTER=test-agent\n', encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project

def git_verb(argv):
    """Erster fachlicher Git-Unterbefehl nach dem festen Prefix."""
    argv = [str(a) for a in argv]
    if "core.fsmonitor=false" in argv:
        idx = argv.index("core.fsmonitor=false") + 1
    elif argv and argv[0] == "git":
        idx = 1
    else:
        idx = 0
    while idx < len(argv) and argv[idx].startswith("-"):
        idx += 1
    return argv[idx] if idx < len(argv) else ""

NETWORK_VERBS = ("fetch", "pull", "push", "ls-remote")

def make_git_stub_b7(calls, remote="https://github.com/owner/name.git",
                  failures=None, branch="main"):
    """Ersetzt subprocess.run: protokolliert jeden Git-Aufruf vollständig.

    Vorbedingung:Echte Prozesse laufen nicht: argv, cwd und die übergebene
    Prozessumgebung werden protokolliert; fetch/pull/push/ls-remote scheitern
    laut ``failures`` oder werden als Erfolg (0, "") beantwortet.
    """
    failures = failures or {}

    def stub(argv, **kwargs):
        record = {
            "argv": list(str(a) for a in argv),
            "cwd": kwargs.get("cwd"),
            "env": dict(kwargs.get("env") or {}),
        }
        calls.append(record)
        verb = git_verb(argv)
        if verb in failures:
            return types.SimpleNamespace(
                returncode=1, stdout="", stderr=failures[verb])
        if verb == "remote":
            out = ("origin\t%s (fetch)\n" % remote) + ("origin\t%s (push)" % remote)
            return types.SimpleNamespace(returncode=0, stdout=out, stderr="")
        if verb == "symbolic-ref":
            return types.SimpleNamespace(returncode=0, stdout=branch, stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    return stub

def network_records(calls):
    return [r for r in calls if git_verb(r["argv"]) in NETWORK_VERBS]

def credentials_scope_texts(record):
    """argv und ENV eines Aufrufs als Suchtext für Credential-Konfiguration."""
    env = record["env"]
    return "\n".join(record["argv"]) + "\n" + "\n".join(env) + "\n" + "\n".join(
        str(v) for v in env.values())

class B7Case(unittest.TestCase):
    """Isolierte Umgebung: temporäres VIBE_STATE, keine Zugangsdaten im ENV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in _ISOLATED_ENV}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy", "https_proxy",
                    "all_proxy"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module_b7()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def store_token(self, token=FAKE_TOKEN_b7):
        self.gh.save_token(token)

    def token_path(self):
        return Path(self.gh.token_state_path())

# --------------------------------------------------------------- Token-Speicher
class TokenStoreTest(B7Case):
    """AC1: Token-Speicher im Zustandsordner, ohne Geheimnis in Meldungen."""

    def test_token_state_path_lies_inside_vibe_state_and_moves_with_it(self):
        path_one = Path(self.gh.token_state_path())
        second_state = self.base / "state-two"
        os.environ["VIBE_STATE"] = str(second_state)
        try:
            path_two = Path(self.gh.token_state_path())
        finally:
            os.environ["VIBE_STATE"] = str(self.state)

        for path in (path_one, path_two):
            self.assertTrue(os.path.isabs(str(path)),
                            "Token-Pfad muss absolut sein: %s" % path)
        try:
            path_one.relative_to(self.state)
        except ValueError:
            self.fail("Token-Pfad %s liegt außerhalb von VIBE_STATE" % path_one)
        try:
            path_two.relative_to(second_state)
        except ValueError:
            self.fail("Der Token-Pfad folgt nicht dem temp- VIBE_STATE "
                      "(Import-Zeit-Kopplung wäre falsch): %s" % path_two)

    def test_save_and_read_roundtrip_stores_exact_token_without_newline(self):
        self.assertFalse(self.token_path().exists())

        self.gh.save_token(FAKE_TOKEN_b7)

        with open(self.token_path(), encoding="utf-8") as handle:
            self.assertEqual(FAKE_TOKEN_b7, handle.read(),
                             "Der Token muss ohne angefügten Zeilenumbruch "
                             "gespeichert werden")
        self.assertEqual(FAKE_TOKEN_b7, self.gh.read_stored_token())

    def test_save_token_rejects_empty_and_control_characters_without_side_effects(self):
        bad_values = ("", "   ", "ab\x00cd", "ab\ncd", "ab\rcd")

        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_token(bad)
        self.assertFalse(self.token_path().exists(),
                         "Ein abgelehnter Token-Speicherversuch darf keine "
                         "Reste hinterlassen")

        self.gh.save_token(FAKE_TOKEN_b7)
        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_token(bad)
        self.assertEqual(FAKE_TOKEN_b7, self.gh.read_stored_token(),
                         "Ungültige Eingaben dürfen den bereits gespeicherten "
                         "Token nicht verändern")

    def test_file_mode_is_0600_best_effort(self):
        probe = self.state / ".chmod-probe"
        probe.write_text("x", encoding="utf-8")
        os.chmod(probe, 0o600)
        chmod_effective = stat.S_IMODE(os.stat(probe).st_mode) == 0o600
        probe.unlink()

        self.gh.save_token(FAKE_TOKEN_b7)
        mode = stat.S_IMODE(os.stat(self.token_path()).st_mode)

        if chmod_effective:
            self.assertEqual(0o600, mode,
                             "Der gespeicherte Token benötigt 0600 (best "
                             "effort, hier wirksames Dateisystem)")
        else:
            # FUSE/NTFS erlauben laut SPEC keine fälschlich wirksamen
            # Unix-Rechte; die Kerninhalte bleiben trotzdem verpflichtend.
            self.assertTrue(self.token_path().exists())

    def test_read_without_stored_token_returns_empty_string(self):
        self.assertEqual("", self.gh.read_stored_token())

        self.gh.save_token(FAKE_TOKEN_b7)
        self.gh.delete_token()
        self.assertEqual("", self.gh.read_stored_token())

    def test_delete_token_removes_file_and_is_tolerant(self):
        self.gh.save_token(FAKE_TOKEN_b7)
        self.assertTrue(self.token_path().exists())

        self.gh.delete_token()
        self.assertFalse(self.token_path().exists())
        self.assertEqual("", self.gh.read_stored_token())

        self.gh.delete_token()  # tolerant ohne vorhandene Datei

    def test_token_status_precedence_and_clear_state(self):
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ.pop("GH_TOKEN", None)
        self.assertEqual({"set": False, "source": ""},
                         self.gh.token_status())

        os.environ["GITHUB_TOKEN"] = ENV_TOKEN_b7
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status())
        self.gh.save_token(FAKE_TOKEN_b7)
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status(),
                         "Die Umgebung gewinnt über den gespeicherten Token")
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ["GH_TOKEN"] = ENV_TOKEN_b7
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status())
        os.environ.pop("GH_TOKEN", None)
        self.assertEqual({"set": True, "source": "gespeichert"},
                         self.gh.token_status())

        self.gh.delete_token()
        self.assertEqual({"set": False, "source": ""},
                         self.gh.token_status(),
                         "Nach dem Löschen bleiben keine Reste")

    def test_status_view_reports_auth_without_token_content(self):
        project = make_project_b7(self.base)
        self.gh.save_token(FAKE_TOKEN_b7)

        view = self.gh.status(project)

        self.assertIn("auth", view, "Der Karten-Status muss auth-Info melden")
        self.assertEqual({"set": True, "source": "gespeichert"}, view["auth"])
        self.not_token_disclosed(json.dumps(view, default=str))

        self.gh.delete_token()
        view = self.gh.status(project)
        self.assertEqual({"set": False, "source": ""}, view["auth"])
        self.not_token_disclosed(json.dumps(view, default=str))

    def not_token_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN_b7, text)
        self.assertNotIn(ENV_TOKEN_b7, text)

# ------------------------------------------------------- Git-Credential-Mechanik
class GitCredentialTest(B7Case):
    """AC2/AC3: Zugangsdaten nur URL-scoped und niemals über argv."""

    def setUp(self):
        super().setUp()
        self.project = self.base / "ghproj"
        self.project.mkdir()

    def record_fetch(self, remote="https://github.com/owner/name.git"):
        calls = []
        stub = make_git_stub_b7(calls, remote=remote)
        with mock.patch("subprocess.run", stub):
            ok, message = self.gh.fetch(self.project)
        return ok, message, calls

    def assert_url_scoped_credentials(self, record):
        # Kompakte Meldungen: Testausgaben dürfen die Prozessumgebung nicht
        # ausdrucken (AC8); nur argv und ENV-Schlüsselnamen sind unkritisch.
        haystack = credentials_scope_texts(record)
        self.assertIn("credential.https://github.com.helper", haystack,
                      "Der Git-Aufruf braucht den URL-scoped Helper für "
                      "github.com: argv=%r env-schluessel=%r"
                      % (record["argv"], sorted(record["env"])))
        self.assertIn("x-access-token", haystack,
                      "Der Token-Benutzername x-access-token fehlt: argv=%r"
                      % (record["argv"],))
        self.assertNotIn(FAKE_TOKEN_b7, "\n".join(record["argv"]),
                         "Der Tokeninhalt darf nie im argv stehen")

    def test_fetch_with_stored_token_gets_url_scoped_credentials_without_token_in_argv(self):
        self.store_token()

        ok, message, calls = self.record_fetch()

        self.assertTrue(ok, message)
        network = network_records(calls)
        self.assertTrue(network, "Der Abruf muss einen Fernaufruf tätigen")
        for record in network:
            self.assert_url_scoped_credentials(record)
            self.assertTrue(
                any(FAKE_TOKEN_b7 in str(v) for v in record["env"].values()),
                "Der gespeicherte Token wird über die Prozessumgebung "
                "eingespeist (env-schluessel=%r)" % sorted(record["env"]))
            self.assertEqual("0", record["env"].get("GIT_TERMINAL_PROMPT", ""),
                             "Der bewährte Prompt-Schutz bleibt bestehen")

    def test_push_with_stored_token_gets_credentials_the_same_way(self):
        self.store_token()
        calls = []
        stub = make_git_stub_b7(calls)
        with mock.patch("subprocess.run", stub):
            ok, message = self.gh.push(self.project)

        self.assertTrue(ok, message)
        network = network_records(calls)
        self.assertTrue(network)
        for record in network:
            self.assert_url_scoped_credentials(record)

    def test_pull_with_env_token_gets_credentials_without_token_in_argv(self):
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN_b7
        calls = []
        stub = make_git_stub_b7(calls)
        with mock.patch("subprocess.run", stub):
            ok, message = self.gh.pull(self.project)

        self.assertTrue(ok, message)
        network = network_records(calls)
        self.assertTrue(network)
        for record in network:
            haystack = credentials_scope_texts(record)
            self.assertIn(
                "credential.https://github.com.helper", haystack,
                "URL-scoped Helper fehlt: argv=%r" % (record["argv"],))
            self.assertIn("x-access-token", haystack,
                          "x-access-token fehlt: argv=%r" % (record["argv"],))
            self.assertNotIn(ENV_TOKEN_b7, "\n".join(record["argv"]))
            self.assertEqual("0", record["env"].get("GIT_TERMINAL_PROMPT", ""))

    def test_without_token_git_behaviour_is_unchanged(self):
        self.gh.delete_token()

        ok, message, calls = self.record_fetch()

        self.assertTrue(ok, message)
        for record in network_records(calls):
            haystack = credentials_scope_texts(record)
            self.assertNotIn("credential.https://github.com", haystack,
                             "Ohne Token keine Credential-Konfiguration")
            self.assertNotIn("x-access-token", haystack)
            self.assertEqual("0", record["env"].get("GIT_TERMINAL_PROMPT", ""),
                             "GIT_TERMINAL_PROMPT=0 bleibt Pflicht")

    def test_non_github_remote_never_receives_stored_token_mechanism(self):
        self.store_token()
        other = "https://git.example.com/owner/name.git"
        calls = []
        stub = make_git_stub_b7(calls, remote=other)
        with mock.patch("subprocess.run", stub):
            ok, message = self.gh.fetch(self.project)

        self.assertTrue(ok, message)
        for record in network_records(calls):
            haystack = credentials_scope_texts(record)
            for match in re.finditer(r"credential\.[^\s\n=]+", haystack):
                self.assertTrue(
                    match.group().startswith("credential.https://github.com"),
                    "Credential-Konfiguration darf ausschließlich für "
                    "github.com gescort (begrenzt) sein (argv=%r env-schluessel=%r)"
                    % (record["argv"], sorted(record["env"])))
            self.assertNotIn(FAKE_TOKEN_b7, "\n".join(record["argv"]))
            self.assertFalse(record["env"].get("GIT_ASKPASS"),
                             "Kein ungeordnetes askpass für fremde Hosts")
            self.assertFalse(record["env"].get("SSH_ASKPASS"))

# ------------------------------------------------------------- Echter Leck-Test
class _GitAuthProbeHandler(BaseHTTPRequestHandler):
    """401-Server auf 127.0.0.1: protokolliert jede Authentifizierung."""

    def log_message(self, fmt, *args):
        pass

    def _deny(self):
        self.server.requests.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
        })
        raw = json.dumps({"message": "credentials required"}).encode("utf-8")
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="b7-probe"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._deny()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._deny()

class GitAuthProbeServer:
    def __init__(self):
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GitAuthProbeHandler)
        self.httpd.requests = self.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

class GitHostLeakProbeTest(B7Case):
    """AC3: Echtes Git gegen einen fremden http-Host delivers den gespeicherten
    Token nie — auch nicht über einen (ungeordneten) askpass-Umweg."""

    def test_real_git_to_non_github_http_host_never_uploads_stored_token(self):
        server = GitAuthProbeServer().start()
        self.addCleanup(server.close)
        project = make_project_b7(self.base, "leakproj")
        real_git_b7(project, "remote", "add", "aux",
                 server.base + "/x.git")
        self.store_token()

        ok, message = self.gh.fetch(project)

        self.assertFalse(ok, "Der nicht erreichbare Fernabruf muss scheitern")
        self.assertTrue(server.requests,
                        "Der Test-Aufwand ist ohne Fernkontakt wertlos")
        for request in server.requests:
            blob = json.dumps(request)
            self.assertNotIn(FAKE_TOKEN_b7, blob,
                             "Der Fremd-Host hat Zugangsdaten empfangen: %s"
                             % blob)
        self.assertNotIn(FAKE_TOKEN_b7, message)
        self.assertTrue(GUIDANCE.search(message),
                        "Der authentifizierende Fehler muss mit klarem "
                        "Hinweis gereinigt werden: %s" % message)

# ------------------------------------------------------------------ REST-Ebene
class AuthRestHandler(BaseHTTPRequestHandler):
    """REST-Fake auf 127.0.0.1; protokolliert Authorization-Header."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, method):
        self.server.requests.append({
            "method": method,
            "path": self.path,
            "authorization": self.headers.get("Authorization") or "",
        })

    def do_GET(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record("GET")
        if self.path.startswith("/repos/owner/name/issues"):
            self._respond(200, [{"number": 7, "title": "T",
                                 "html_url": "http://127.0.0.1/7",
                                 "labels": [{"name": "vibe"}]}])
        else:
            self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record("POST")
        self._respond(404, {"message": "Not Found"})

class AuthRestFakeServer:
    def __init__(self):
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), AuthRestHandler)
        self.httpd.requests = self.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

class RestAuthTest(B7Case):
    """AC3/AC4: Token-Auflösung für list_issues/create_pull_request."""

    def setUp(self):
        super().setUp()
        self.captured = []

    def record_http_json(self):
        def fake(method, url, *, token=None, payload=None, timeout=30):
            self.captured.append({
                "method": method, "url": url,
                "token": token, "payload": payload})
            if method == "POST":
                return {"number": 42, "html_url": "http://127.0.0.1/pr/42"}
            return []

        return fake

    def test_list_issues_resolves_env_token_by_default(self):
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN_b7

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(ENV_TOKEN_b7, self.captured[-1]["token"],
                         "list_issues muss sich standardmäßig über den "
                         "Umgebungstoken authentifizieren")

    def test_list_issues_resolves_stored_token_for_official_api(self):
        self.store_token()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(FAKE_TOKEN_b7, self.captured[-1]["token"],
                         "Ohne Umgebungstoken wird der gespeicherte Token für "
                         "die offizielle API verwendet")

    def test_env_token_wins_over_stored_token(self):
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN_b7
        self.store_token()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(ENV_TOKEN_b7, self.captured[-1]["token"])

    def test_stored_token_is_never_sent_to_non_official_api(self):
        server = AuthRestFakeServer().start()
        self.addCleanup(server.close)
        self.store_token()

        self.gh.list_issues("owner/name", api=server.base)

        self.assertTrue(server.requests)
        for request in server.requests:
            self.assertNotIn(FAKE_TOKEN_b7, request["authorization"],
                             "Der gespeicherte Token gehört nie zur "
                             "konfigurierbaren API")

    def test_env_token_keeps_rest_delivery_to_configured_api(self):
        server = AuthRestFakeServer().start()
        self.addCleanup(server.close)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN_b7

        self.gh.list_issues("owner/name", api=server.base)

        self.assertTrue(server.requests)
        self.assertEqual("Bearer " + ENV_TOKEN_b7,
                         server.requests[-1]["authorization"],
                         "Der Umgebungstoken behält sein REST-Lieferverhalten")

    def test_create_pull_request_without_any_token_fails_comprehensibly(self):
        project = self.base / "prproj"
        project.mkdir()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            with self.assertRaises(self.gh.GitHubError) as caught:
                self.gh.create_pull_request(
                    project, "owner/name", head="feature", base="main",
                    title="B7 Rotphasennachweis")

        self.assertTrue(str(caught.exception).startswith(
            "Kein GitHub-Zugangstoken"), str(caught.exception))
        self.assertFalse(self.captured, "Ohne Token darf kein Aufruf starten")

    def test_create_pull_request_uses_stored_token_for_official_api(self):
        project = self.base / "prproj2"
        project.mkdir()
        self.store_token()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            result = self.gh.create_pull_request(
                project, "owner/name", head="feature", base="main",
                title="B7 Titel pr")

        self.assertTrue(self.captured)
        self.assertEqual(FAKE_TOKEN_b7, self.captured[-1]["token"])
        self.assertEqual(42, result["number"])

    def test_errors_and_status_never_disclose_token(self):
        self.store_token()

        with self.assertRaises(ValueError) as thrown:
            self.gh.list_issues("owner name!")
        self.assertNotIn(FAKE_TOKEN_b7, str(thrown.exception))

        with self.assertRaises(ValueError) as thrown:
            self.gh.create_pull_request(self.base, "owner/name",
                                        head="feature", base="main")
        # Ohne Projektbasis ein verständlicher Fehler, ohne Tokeninhalt.
        self.assertNotIn(FAKE_TOKEN_b7, str(thrown.exception))

        status = self.gh.token_status()
        self.not_disclosed(json.dumps(status))
        self.assertEqual({"set": True, "source": "gespeichert"}, status)

    def not_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN_b7, text)
        self.assertNotIn(ENV_TOKEN_b7, text)

# ------------------------------------------------------------- Fehlerklassifikation
class ErrorClassificationTest(B7Case):
    """AC5: Git-Fehlerbilder führen mit sauberem Anweisungshinweis zur
    Token-Hinterlegung, ohne Geheimnisse zu enthüllen."""

    def setUp(self):
        super().setUp()
        self.store_token()  # Klassifikation muss auch trotz vorhandener Zugangsdaten greifen
        self.project = self.base / "classproj"
        self.project.mkdir()
    def test_could_not_read_username_is_classified_with_token_guidance(self):
        self._classify_all_actions(RAW_VARIANTS["could_not_read_username"])

    def test_terminal_prompts_only_is_classified_with_token_guidance(self):
        self._classify_all_actions(RAW_VARIANTS["terminal_prompts_only"])

    def test_broken_askpass_is_classified_with_token_guidance(self):
        self._classify_all_actions(RAW_VARIANTS["broken_askpass"])

    def test_german_askpass_variant_is_classified_with_token_guidance(self):
        self._classify_all_actions(RAW_VARIANTS["german_askpass_and_prompts"])

    def test_authentication_failed_is_classified_with_token_guidance(self):
        self._classify_all_actions(RAW_VARIANTS["authentication_failed"])

    def _classify_all_actions(self, variant):
        for action in ("fetch", "pull", "push"):
            with self.subTest(action=action, variant=variant[:40]):
                failures = {action: variant}
                calls = []
                stub = make_git_stub_b7(calls, failures=failures)
                with mock.patch("subprocess.run", stub):
                    ok, message = getattr(self.gh, action)(self.project)
                self.assertFalse(ok, "Der feindliche Fernabruf muss scheitern")
                self.assertNotIn(FAKE_TOKEN_b7, message,
                                 "Fehlermeldungen enthüllen nie den Token")
                self.assertTrue(GUIDANCE.search(message),
                                "Die Meldung muss den Nutzer zur Token-"
                                "Hinterlegung führen: %s" % message)

# ----------------------------------------------------------------------- Web-API
class TokenRoutesWebTest(unittest.TestCase):
    """AC6: /api/github token.save/token.clear über das echte Dashboard.

    Der Webserver läuft als eigener Prozess mit temporärem VIBE/HOME und
    freiem Port; die Authentifizierung folgt den etablierten V-004-Regeln.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        home = cls.root / "home"
        (home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        logs = cls.root / "_logs"
        logs.mkdir()
        project = make_project_b7(cls.root, "pgh")
        cls.port = free_port()
        env = os.environ.copy()
        for key in _ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(logs),
            "HOME": str(home),
            "VIBE_AGENTS_DIR": str(home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(home / ".config" / "vibe" / "config.json"),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = logs / "web.token"
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
        cls.gh = github_module_b7()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.token_file = self.expected_token_path()
        if self.token_file.exists():
            self.token_file.unlink()

    def tearDown(self):
        if self.token_file.exists():
            self.token_file.unlink()

    def expected_token_path(self):
        """Projekt-Token-Ablage (AP9-Vertrag, ersetzt die frühere globale
        Datei): <VIBE_STATE>/github-tokens/<sha256(realpath)[:16]>.json."""
        old = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = str(self.state)
        try:
            project = os.path.realpath(str(self.root / "pgh"))
            digest = hashlib.sha256(project.encode("utf-8")).hexdigest()[:16]
            return Path(self.state) / "github-tokens" / (digest + ".json")
        finally:
            if old is None:
                os.environ.pop("VIBE_STATE", None)
            else:
                os.environ["VIBE_STATE"] = old

    def request(self, method, path, body=None, token=True):
        headers = {}
        if token is True:
            headers["X-Token"] = self.web_token
        elif isinstance(token, str):
            headers["X-Token"] = token
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            connection.close()

    def github_post(self, body, token=True):
        return self.request("POST", "/api/github", body=body, token=token)

    def test_token_save_persists_state_and_hides_secret(self):
        """AP9-Vertrag: token.save legt den Token je Projekt verschlüsselt
        ab (github-tokens/<hash>.json); der Klartext steht nie im Inhalt."""
        status, text = self.github_post(
            {"name": "pgh", "action": "token.save", "token": FAKE_TOKEN_b7})
        data = json.loads(text) if text.startswith("{") else {}

        self.assertEqual(200, status, text)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn(FAKE_TOKEN_b7, text,
                         "Die Antwort darf den Tokeninhalt nie enthalten")
        self.assertTrue(self.token_file.exists(),
                        "Der Token wird je Projekt unter VIBE_STATE/"
                        "github-tokens gespeichert")
        raw = self.token_file.read_text(encoding="utf-8")
        self.assertNotIn(FAKE_TOKEN_b7, raw,
                         "Die Ablage ist verschlüsselt: kein Klartext-Token")
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": True, "source": "projekt"}, auth,
                         "Die Antwort trägt den auth-Status ohne Geheimnis")
        global_file = self.token_file.parent.parent / "github-token"
        self.assertFalse(global_file.exists(),
                         "token.save schreibt je Projekt; die frühere globale "
                         "Datei wird nicht mehr erzeugt")

    def test_token_clear_removes_the_stored_token(self):
        self.github_post({"name": "pgh", "action": "token.save", "token": FAKE_TOKEN_b7})
        self.assertTrue(self.token_file.exists())

        status, text = self.github_post({"name": "pgh", "action": "token.clear"})
        data = json.loads(text) if text.startswith("{") else {}

        self.assertEqual(200, status, text)
        self.assertTrue(data.get("ok"), data)
        self.assertFalse(self.token_file.exists(),
                         "token.clear löscht den Projekt-Token-Eintrag")
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": False, "source": ""}, auth,
                         "Nach dem Entfernen bleiben keine Reste")

        status, _ = self.github_post({"name": "pgh", "action": "token.clear"})
        self.assertEqual(200, status, "Wiederholtes Entfernen bleibt tolerant")

    def test_unauthorized_github_calls_are_rejected(self):
        for token in ("falsches-token", None):
            with self.subTest(token=token):
                status, text = self.github_post(
                    {"name": "pgh", "action": "token.save", "token": FAKE_TOKEN_b7},
                    token=token)
                self.assertGreaterEqual(status, 400, text)
                self.assertNotIn(FAKE_TOKEN_b7, text)
                self.assertFalse(self.token_file.exists())

    def test_detail_view_reports_auth_state_without_secret(self):
        self.github_post({"name": "pgh", "action": "token.save", "token": FAKE_TOKEN_b7})

        status, text = self.request("GET", "/api/project?name=pgh")
        data = json.loads(text)
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": True, "source": "projekt"}, auth, text)
        self.assertNotIn(FAKE_TOKEN_b7, text)

        self.github_post({"name": "pgh", "action": "token.clear"})

        status, text = self.request("GET", "/api/project?name=pgh")
        data = json.loads(text)
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": False, "source": ""}, auth, text)
        self.assertNotIn(FAKE_TOKEN_b7, text)


# ===========================================================================
# Abnahme „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
# ===========================================================================

import importlib.machinery
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGES = REPO / "bin" / "vibe_packages.py"

# Umgebungsvariablen, die für Prozessaufrufe isoliert werden müssen, damit
# weder die produktive Installation noch persönliche Konfigurationen erreicht
# werden (Muster tests/unit/test_ap11_priority.py).
ISOLATED_ENV_b16 = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
)

GIT_IDENTITY_b16 = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def load_packages():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul (Rotphase: Lücken)."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b16_branch_under_test", str(PACKAGES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def real_git_b16(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY_b16)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


class BranchNameCase(unittest.TestCase):
    """Isolierte Umgebung mit temporären Projekten je Test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_b16}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.packages = load_packages()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ------------------------------------------------------------ Projekt
    def make_project(self, name="proj", env_extra="", feedback=None,
                     tickets=None, user_name=None):
        """Projekt mit GH-48-Ticketspeicher statt Markdown-Ledgern."""
        project = self.base / name
        project.mkdir(parents=True, exist_ok=True)
        real_git_b16(project, "init", "-q", "-b", "main")
        real_git_b16(project, "commit", "--allow-empty", "-q", "-m", "init")
        if user_name is not None:
            real_git_b16(project, "config", "user.name", user_name)
        (project / ".vibe").mkdir(exist_ok=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n" + env_extra, encoding="utf-8")
        records = []
        for source in (tickets, feedback):
            if source:
                records.extend(source)
        if records:
            (project / ".vibe" / "tickets.json").write_text(
                json.dumps({"version": 1, "tickets": records},
                           ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
        return project

    def create_branch(self, project, name):
        real_git_b16(project, "branch", name)

    def run_branch_name(self, project, pid):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV_b16}
        env.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        env.update(GIT_IDENTITY_b16)
        return subprocess.run(
            [sys.executable, str(PACKAGES), "branch-name",
             "--project", str(project), "--id", pid],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=120, check=False,
        )


# ------------------------------------------------------------- Standardmuster
class DefaultPatternTest(BranchNameCase):
    """AK: Branch-Namen entsprechen den Repository-Regeln (feature/...)."""

    def test_default_pattern_uses_sanitized_git_user_name(self):
        project = self.make_project(user_name="M0P")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/m0p/b16", name)

    def test_owner_is_kebab_cased_from_a_name_with_spaces_and_uppercase(self):
        project = self.make_project(user_name="Max Mustermann")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/max-mustermann/b16", name)

    def test_missing_user_name_falls_back_to_vibe(self):
        project = self.make_project(user_name=None)

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/vibe/b16", name)

    def test_package_id_is_kebab_cased(self):
        project = self.make_project(user_name="Test")

        name = self.packages.package_branch_name(project, "AP_19")

        self.assertEqual("feature/test/ap-19", name)


# ------------------------------------------------------ Konfigurierbares Muster
class PatternConfigurationTest(BranchNameCase):
    """AK: Muster ist über PACKAGE_BRANCH_PATTERN konfigurierbar."""

    def test_configured_pattern_with_slug_uses_the_ticket_title(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{owner}/{id}-{slug}"\n',
            feedback=[{"id": "F1", "title": "Kurzer Titel"}],
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/test/f1-kurzer-titel", name)

    def test_slug_is_limited_to_24_characters(self):
        title = "Ein sehr langer Pakettitel mit vielen Woertern"
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{id}-{slug}"\n',
            feedback=[{"id": "F1", "title": title}],
            user_name="Test",
        )
        full_slug = "ein-sehr-langer-pakettitel-mit-vielen-woertern"
        expected = full_slug[:24].rstrip("-")

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/f1-" + expected, name)
        self.assertLessEqual(len(expected), 24)

    def test_slug_falls_back_to_paket_without_a_title(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{id}-{slug}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/f1-paket", name)

    def test_pattern_without_owner_works(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("pkg/b16", name)

    def test_explicit_pattern_argument_overrides_the_configuration(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(
            project, "B16", pattern="feature/{owner}/{id}")

        self.assertEqual("feature/test/b16", name)


# ------------------------------------------------------------- Ungültige Fälle
class InvalidPatternTest(BranchNameCase):
    """AK: Ungültiges Muster/Ergebnis wird klar abgelehnt (ValueError)."""

    def test_unknown_placeholder_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError) as raised:
            self.packages.package_branch_name(
                project, "B16", pattern="feature/{foo}/{id}")

        self.assertIn("{foo}", str(raised.exception))

    def test_empty_pattern_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(project, "B16", pattern="")

    def test_empty_segment_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="feature//{id}")

    def test_segment_ending_on_lock_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="feature/{id}.lock")

    def test_uppercase_in_the_result_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="Feature/{id}")

    def test_subcommand_reports_an_invalid_pattern_with_exit_one(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="{foo}/{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(1, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout + result.stderr)
        self.assertNotIn("feature/", result.stdout)

    def test_subcommand_reports_an_invalid_result_with_exit_one(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature//{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(1, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout + result.stderr)


# ---------------------------------------------------------------- Kollisionen
class CollisionTest(BranchNameCase):
    """AK: Lokale Branch-Kollisionen werden mit Suffixen aufgelöst."""

    def test_existing_branch_gets_the_suffix_two(self):
        project = self.make_project(user_name="Test")
        self.create_branch(project, "feature/test/b16")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/test/b16-2", name)

    def test_two_existing_branches_get_the_suffix_three(self):
        project = self.make_project(user_name="Test")
        self.create_branch(project, "feature/test/b16")
        self.create_branch(project, "feature/test/b16-2")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/test/b16-3", name)


# ---------------------------------------------------------------- Subkommando
class BranchNameSubcommandTest(BranchNameCase):
    """AK: Der Läufer erhält den Branch-Namen über ein Subkommando."""

    def test_subcommand_prints_exactly_the_branch_name_and_exits_zero(self):
        project = self.make_project(user_name="M0P")

        result = self.run_branch_name(project, "B16")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("feature/m0p/b16", result.stdout.strip())
        self.assertEqual(1, len(result.stdout.strip().splitlines()),
                         "Genau eine stdout-Zeile erwartet")

    def test_subcommand_uses_the_configured_pattern(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("pkg/b16", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
