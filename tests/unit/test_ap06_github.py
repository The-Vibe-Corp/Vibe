"""Acceptance tests for the Git/GitHub integration (AP6).

The tests are derived from the work package AP6 (TICKETS.md) and SPEC.md,
independent of any implementation diff. Covered interface contract:

* Module ``bin/vibe_github.py`` (standard library only):
  - read_config(env_path) -> {"enabled": bool, "repo": str, "label": str, "api": str}
  - status(project_path)  -> offline view with remotes, branch, ahead/behind
  - branches(project_path) -> list of dicts (name, current, ahead, behind)
  - fetch pull push        -> (ok, message), argument lists only, no shell
  - list_issues(repo, label, api, token) -> list with number/title/html_url
  - import_issues_into_tickets(project_path, issues) -> idempotent, atomic,
    writes "- [ ] GH-<num> <title>" blocks compatible with the ticket parser
  - create_pull_request(...) -> dict with "url"; token only from
    GITHUB_TOKEN|GH_TOKEN; without a token a clear German error message and
    no request at all; API base is configurable (default https://api.github.com)
* CLI ``vibe github <project> status|link|unlink|fetch|pull|issues|pr`` where
  ``pr`` without --confirm must not push and must not call the API.
* Rules: GENERAL_RULES and all templates/*/AGENTS.md state that commit
  messages stay human readable (für Menschen) and essential (Wesentliche).

No real network calls (github.com is never contacted), no productive
$VIBE/_toolchain paths, no secrets; git runs only inside temporary
directories with a fixed test identity. Run with:

    python3 -m unittest tests.unit.test_ap06_github -v
"""
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
    """Project with .vibe/project.env, TICKETS.md, FEEDBACK.md and real git."""

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
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")

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


class IssuesImportTest(ProjectFixture):
    """import_issues_into_tickets: atomic, idempotent, label filtered."""

    def setUp(self):
        super().setUp()
        self.server = FakeGitHubServer().start()
        self.addCleanup(self.server.close)
        self.cli.set_env_values(
            "proj",
            {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name", "GITHUB_API": self.server.base},
        )
        self.vibe_issues = [dict(item) for item in ISSUES if item["number"] == 7]

    def test_import_appends_vibe_issues_in_ticket_format_and_is_idempotent(self):
        tickets = self.project / "TICKETS.md"

        self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        text = tickets.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^- \[ \] GH-7 \S")
        self.assertNotIn("GH-8", text)  # label filter keeps bugs out
        self.assertIn("Sandbox für Import einschränken", text)

        self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        self.assertEqual(tickets.read_text(encoding="utf-8"), text)

    def test_import_keeps_existing_ticket_entries_unchanged(self):
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n- [ ] AP1 Erstes Paket\n  Beschreibung: vorhanden\n",
            encoding="utf-8",
        )

        self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        text = tickets.read_text(encoding="utf-8")
        self.assertIn("AP1 Erstes Paket", text)
        self.assertIn("GH-7", text)

    def test_imported_items_are_parseable_as_open_tickets(self):
        self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        items = self.cli.ticket_items("proj")
        gh_items = [i for i in items if i["id"] == "GH-7"]
        self.assertEqual(len(gh_items), 1)
        self.assertEqual(gh_items[0]["state"], "offen")


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


# -------------------------------------------------------------- Commit message rule
class CommitMessageRuleTest(ProjectFixture):
    """AP6: commits stay human readable and reduced to the essentials."""

    PHRASES = ("Commit-Meldungen", "für Menschen", "Wesentliche")

    @staticmethod
    def git_section(text):
        return text.split("## Ordnung im Git halten", 1)[1].split("\n## ", 1)[0]

    def test_general_rules_demand_human_readable_essential_commit_messages(self):
        section = self.git_section(self.cli.GENERAL_RULES)
        for phrase in ("Commit-Meldungen", "für Menschen", "Wesentliche"):
            self.assertIn(phrase, section, f"fehlende Regel: {phrase}")

    def test_all_shipped_templates_contain_the_same_commit_rule(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn(self.cli.GENERAL_RULES, text, path)
                section = self.git_section(text)
                for phrase in ("Commit-Meldungen", "für Menschen", "Wesentliche"):
                    self.assertIn(phrase, section, path)


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


class ImportCollisionTest(ProjectFixture):
    """TICKETS import detects concurrent edits (atomic write, review R1)."""

    def setUp(self):
        super().setUp()
        self.server = FakeGitHubServer().start()
        self.addCleanup(self.server.close)
        self.cli.set_env_values(
            "proj",
            {"GITHUB_ENABLED": "1", "GITHUB_REPO": "owner/name", "GITHUB_API": self.server.base},
        )
        self.vibe_issues = [dict(item) for item in ISSUES if item["number"] == 7]
        self.tickets = self.project / "TICKETS.md"

    def collision(self, touch_after_read):
        """Rewires the storage seam the product module actually binds to.

        ``bin/vibe_github.py`` imports ``vibe_storage`` through sys.modules,
        not through the loader alias; therefore the attribute of the loaded
        product module is the object the patch has to target.
        """
        storage = getattr(self.gh, "vibe_storage", None) or storage_module()
        real_snapshot = storage.read_snapshot
        calls = []

        def snapshot_seq(path, *rest, **kw):
            snapshot = real_snapshot(path, *rest, **kw)
            calls.append(path)
            if touch_after_read and len(calls) == 1:
                # Side writer between the module's read and its write step.
                with open(self.tickets, "a", encoding="utf-8") as fh:
                    fh.write("\n- [ ] AP9 Eingriff\n  Beschreibung: seitlich\n")
            return snapshot

        return storage, snapshot_seq

    def test_concurrent_ticket_change_is_reported_and_file_stays_intact(self):
        storage, snapshot_seq = self.collision(touch_after_read=True)

        with mock.patch.object(storage, "read_snapshot", side_effect=snapshot_seq):
            with self.assertRaises(ValueError) as ctx:
                self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        message = str(ctx.exception)
        self.assertIn("zwischenzeitlich", message)
        self.assertIn("Import", message)
        text = self.tickets.read_text(encoding="utf-8")
        self.assertIn("AP9 Eingriff", text)   # the outside write survived
        self.assertNotIn("GH-7", text)        # the import wrote nothing

    def test_import_without_interference_keeps_working(self):
        storage, snapshot_seq = self.collision(touch_after_read=False)

        with mock.patch.object(storage, "read_snapshot", side_effect=snapshot_seq):
            self.gh.import_issues_into_tickets(str(self.project), self.vibe_issues)

        self.assertIn("- [ ] GH-7", self.tickets.read_text(encoding="utf-8"))


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


if __name__ == "__main__":
    unittest.main()


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
