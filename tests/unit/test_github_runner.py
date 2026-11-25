"""GitHub im Läufer: Pull, Paketabschluss, Verdrahtung und Merge-Verhalten.

Aufruf: python3 -m unittest tests.unit.test_github_runner -v
"""


# ===========================================================================
# Abnahme „Bereit für Github Teil 3“: Läufer-Unterstützung für Pull und
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
PACKAGES = REPO / "bin" / "vibe_packages.py"

FAKE_TOKEN = "ap9-runner-env-token-777"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
)

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

_GH_CACHE = {}


def github_module():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_ap9_runner_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def real_git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def real_git_out(cwd, *argv):
    return real_git(cwd, *argv).stdout.strip()


def seed_bare(root, name):
    work = Path(root) / "seed" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "README.md").write_text("Inhalt\n", encoding="utf-8")
    real_git(work, "init", "-q", "-b", "main")
    real_git(work, "add", "-A")
    real_git(work, "commit", "-q", "-m", "seed")
    bare = Path(root) / "origin" / (name + ".git")
    bare.mkdir(parents=True, exist_ok=True)
    real_git(bare, "init", "-q", "--bare")
    real_git(work, "remote", "add", "origin", str(bare))
    real_git(work, "push", "-q", "origin", "main")
    real_git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare)


def make_project(root, name, env_extra="", with_origin=None):
    """Git-Projekt mit project.env; origin optional direkt verknüpft."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    real_git(project, "init", "-q", "-b", "main")
    real_git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir(exist_ok=True)
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n" + env_extra, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    if with_origin:
        real_git(project, "remote", "add", "origin", with_origin)
        real_git(project, "fetch", "-q", "origin")
        real_git(project, "reset", "-q", "--hard", "origin/main")
    return project


def project_env(name, api="", base="main", enabled=True):
    text = ""
    if enabled:
        text += 'GITHUB_ENABLED="1"\n'
    text += 'GITHUB_REPO="owner/name"\n'
    text += 'GITHUB_BASE="%s"\n' % base
    if api:
        text += 'GITHUB_API="%s"\n' % api
    return text


class _RestHandler(BaseHTTPRequestHandler):
    """REST-Fake auf 127.0.0.1; zeichnet Merge-Request-POSTs auf."""

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
        self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) if length else b""
        self._record()
        self.server.posts.append({
            "path": self.path,
            "body": json.loads(raw_body.decode("utf-8")) if raw_body else None,
            "authorization": self.headers.get("Authorization") or "",
        })
        self._respond(self.server.post_status, {
            "number": 42, "html_url": "http://127.0.0.1/pull/42"})


class RestFakeServer:
    def __init__(self, post_status=201):
        self.requests = []
        self.posts = []
        self.post_status = post_status
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            self._port = sock.getsockname()[1]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self._port), _RestHandler)
        self.httpd.requests = self.requests
        self.httpd.posts = self.posts
        self.httpd.post_status = post_status
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self._port

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class AP9RunnerCase(unittest.TestCase):
    """Isolierte Umgebung: temporäres VIBE_STATE, klare Prozessumgebung."""

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
        self.gh = github_module()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def not_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN, text)


# --------------------------------------------------------- pull_integration
class PullIntegrationTest(AP9RunnerCase):
    """AK „Vor jedem neuen AP den Haupt-Branch aktualisieren (pull)“."""

    def test_pull_integration_skips_when_github_is_disabled(self):
        bare_url = seed_bare(self.base, "skip-origin")
        project = make_project(self.base, "skip", env_extra="", with_origin=bare_url)

        performed, ok, message = self.gh.pull_integration(project)

        self.assertFalse(performed, "Ohne GITHUB_ENABLED wird bewusst übersprungen")
        self.assertTrue(ok)
        self.assertTrue(str(message).strip(), "Skip-Meldung erwartet")

    def test_pull_integration_skips_without_an_origin_remote(self):
        project = make_project(self.base, "ohne-fremd",
                               env_extra=project_env("ohne-fremd", enabled=True))

        performed, ok, message = self.gh.pull_integration(project)

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip())

    def test_pull_integration_updates_the_integration_branch(self):
        bare_url = seed_bare(self.base, "aktuell-origin")
        project = make_project(
            self.base, "aktuell",
            env_extra=project_env("aktuell", enabled=True), with_origin=bare_url)
        # Fernstand zieht um einen Commit voraus:
        seed_work = self.base / "seed" / "aktuell-origin"
        (seed_work / "neu.txt").write_text("neu\n", encoding="utf-8")
        real_git(seed_work, "add", "-A")
        real_git(seed_work, "commit", "-q", "-m", "fernauftrag")
        real_git(seed_work, "push", "-q", "origin", "main")
        # Sollwert unabhängig von der Implementierung direkt aus der
        # Bare-Quelle lesen (der Remote-Tracking-Ref im Projekt wird erst
        # durch den Fetch im Aufruf aktualisiert).
        remote_tip = real_git_out(self.base / "origin" / "aktuell-origin.git",
                                  "rev-parse", "main")

        performed, ok, message = self.gh.pull_integration(project)

        self.assertTrue(performed)
        self.assertTrue(ok, message)
        self.assertEqual(remote_tip, real_git_out(project, "rev-parse", "HEAD"),
                         "Der Integrationsbranch muss den Fernstand annehmen")
        self.not_disclosed(message)

    def test_pull_integration_fails_on_divergence_without_merge_commit(self):
        bare_url = seed_bare(self.base, "abfall-origin")
        project = make_project(
            self.base, "abfall",
            env_extra=project_env("abfall", enabled=True), with_origin=bare_url)
        # Lokal auseinanderlaufender Commit (noch nicht gesendet):
        (project / "lokal.txt").write_text("lokal\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "lokal")
        local_tip = real_git_out(project, "rev-parse", "HEAD")
        # Fernstand zieht unabhängig voraus:
        seed_work = self.base / "seed" / "abfall-origin"
        (seed_work / "fremd.txt").write_text("fremd\n", encoding="utf-8")
        real_git(seed_work, "add", "-A")
        real_git(seed_work, "commit", "-q", "-m", "fremd")
        real_git(seed_work, "push", "-q", "origin", "main")

        performed, ok, message = self.gh.pull_integration(project)

        self.assertTrue(performed)
        self.assertFalse(ok, "Divergenz ohne ff-only darf nicht Erfolg melden")
        self.assertTrue(str(message).strip(), "Meldung erwartet")
        self.assertEqual(local_tip, real_git_out(project, "rev-parse", "HEAD"),
                         "Der fehlgeschlagene Pull darf keinen Merge-Commit "
                         "erzeugen (ff-only)")
        self.not_disclosed(message)

    def test_pull_integration_never_raises(self):
        project = make_project(self.base, "nie-ausnahme")
        try:
            result = self.gh.pull_integration(project)
        except Exception as error:  # noqa: BLE001 - genau das ist der Befund
            self.fail("pull_integration darf niemals werfen: %r" % (error,))
        self.assertEqual(3, len(tuple(result)),
                         "(performed, ok, message) erwartet")


# -------------------------------------------------------- complete_package
class CompletePackageTest(AP9RunnerCase):
    """AK „Nach AP-Abschluss automatisch einen Merge-Request stellen“."""

    def configured_project(self, name, server=None, base="main"):
        api = server.base if server else ""
        bare_url = seed_bare(self.base, name + "-origin")
        return make_project(
            self.base, name,
            env_extra=project_env(name, api=api, base=base, enabled=True),
            with_origin=bare_url)

    def work_on_branch(self, project, branch):
        real_git(project, "checkout", "-q", "-b", branch)
        (project / "arbeit.txt").write_text(branch + "\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "AP-Arbeit")

    def test_complete_package_skips_when_github_is_disabled(self):
        bare_url = seed_bare(self.base, "skip-paket-origin")
        project = make_project(self.base, "skip-paket", env_extra="",
                               with_origin=bare_url)
        self.work_on_branch(project, "feature/skip")

        performed, ok, message, result = self.gh.complete_package(
            project, "feature/skip", package_id="AP9")

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip(), "Skip-Meldung erwartet")
        self.assertEqual("", result["pr_url"])

    def test_complete_package_skips_without_an_origin_remote(self):
        project = make_project(self.base, "paket-ohne-fremd",
                               env_extra=project_env("paket-ohne-fremd"))
        self.work_on_branch(project, "feature/ohne")

        performed, ok, message, result = self.gh.complete_package(
            project, "feature/ohne")

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip())
        self.assertEqual("", result["pr_url"])

    def test_complete_package_pushes_and_opens_the_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.configured_project("paket-ok", server=server)
        self.work_on_branch(project, "feature/ap9")
        tip = real_git_out(project, "rev-parse", "HEAD")

        performed, ok, message, result = self.gh.complete_package(
            project, "feature/ap9", package_id="AP9")

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertEqual("feature/ap9", result["branch"])
        self.assertTrue(result["pr_url"], "PR-URL im Ergebnis erwartet")
        remote_tip = real_git_out(project, "ls-remote", "origin",
                                  "refs/heads/feature/ap9").split()[0]
        self.assertEqual(tip, remote_tip, "Der Zweig muss gepusht werden")
        upstream = real_git_out(project, "rev-parse", "--abbrev-ref",
                                "feature/ap9@{u}")
        self.assertEqual("origin/feature/ap9", upstream, "Upstream erwartet")
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts, "Es muss ein Merge-Request beantragt werden")
        self.assertEqual("feature/ap9", posts[-1]["body"].get("head"))
        self.assertEqual("main", posts[-1]["body"].get("base"),
                         "GITHUB_BASE ist der Haupt-Branch für den Request")
        self.not_disclosed(message)

    def test_complete_package_falls_back_to_the_origin_default_branch(self):
        """Ohne GITHUB_BASE liefert origin/HEAD den Basis-Branch."""
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        api = server.base
        bare_url = seed_bare(self.base, "paket-head-origin")
        project = make_project(
            self.base, "paket-head",
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_API="%s"\n' % api),
            with_origin=bare_url)
        real_git(project, "remote", "set-head", "origin", "--auto", check=False)
        self.work_on_branch(project, "feature/kopf")

        performed, ok, message, result = self.gh.complete_package(
            project, "feature/kopf")

        self.assertTrue(ok, message)
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts)
        self.assertEqual("main", posts[-1]["body"].get("base"),
                         "Ohne GITHUB_BASE gilt der Standard-Branch der origin")

    def test_complete_package_reports_a_failed_merge_request(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        project = self.configured_project("paket-fehler", server=server)
        self.work_on_branch(project, "feature/fehler")
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN

        performed, ok, message, result = self.gh.complete_package(
            project, "feature/fehler")

        self.assertTrue(performed)
        self.assertFalse(ok, "Ein abgelehnter Merge-Request ist kein Erfolg")
        self.assertTrue(str(message).strip(), "Meldung erwartet")
        self.assertEqual("", result["pr_url"])
        self.not_disclosed(message)

    def test_complete_package_never_raises(self):
        project = make_project(self.base, "paket-nie-ausnahme",
                               env_extra=project_env("paket-nie-ausnahme"))
        self.work_on_branch(project, "feature/nie")
        try:
            result = self.gh.complete_package(project, "feature/nie")
        except Exception as error:  # noqa: BLE001 - genau das ist der Befund
            self.fail("complete_package darf niemals werfen: %r" % (error,))
        self.assertEqual(4, len(tuple(result)),
                         "(performed, ok, message, result) erwartet")
        self.assertIn("branch", tuple(result)[3])
        self.assertIn("pr_url", tuple(result)[3])


# ----------------------------------------------- Subkommandos des Läufers
class SubcommandExitCodesTest(AP9RunnerCase):
    """AK Läufer-Integration: Exitcodes der vibe_packages-Unter­befehle."""

    def run_packages(self, *argv, github_token=None):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        if github_token is not None:
            env["GITHUB_TOKEN"] = github_token
        env.update(GIT_IDENTITY)
        return subprocess.run(
            [sys.executable, str(PACKAGES), *argv],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=120, check=False,
        )

    def test_github_pull_subcommand_skips_with_exit_zero(self):
        bare_url = seed_bare(self.base, "sub-skip-origin")
        project = make_project(self.base, "sub-skip", env_extra="",
                               with_origin=bare_url)

        result = self.run_packages("github-pull", "--project", str(project))

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertTrue((result.stdout + result.stderr).strip())

    def test_github_pull_subcommand_succeeds_with_exit_zero(self):
        bare_url = seed_bare(self.base, "sub-ok-origin")
        project = make_project(
            self.base, "sub-ok",
            env_extra=project_env("sub-ok"), with_origin=bare_url)
        seed_work = self.base / "seed" / "sub-ok-origin"
        (seed_work / "vorlauf.txt").write_text("vor\n", encoding="utf-8")
        real_git(seed_work, "add", "-A")
        real_git(seed_work, "commit", "-q", "-m", "voraus")
        real_git(seed_work, "push", "-q", "origin", "main")

        result = self.run_packages("github-pull", "--project", str(project))

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        remote_tip = real_git_out(project, "rev-parse", "origin/main")
        self.assertEqual(remote_tip, real_git_out(project, "rev-parse", "HEAD"))

    def test_github_pull_subcommand_fails_with_exit_one(self):
        bare_url = seed_bare(self.base, "sub-fehler-origin")
        project = make_project(
            self.base, "sub-fehler",
            env_extra=project_env("sub-fehler"), with_origin=bare_url)
        (project / "lokal.txt").write_text("lokal\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "lokal")
        seed_work = self.base / "seed" / "sub-fehler-origin"
        (seed_work / "fremd.txt").write_text("fremd\n", encoding="utf-8")
        real_git(seed_work, "add", "-A")
        real_git(seed_work, "commit", "-q", "-m", "fremd")
        real_git(seed_work, "push", "-q", "origin", "main")

        result = self.run_packages("github-pull", "--project", str(project))

        self.assertEqual(1, result.returncode,
                         "Ein Fehlschlag beendet den Unterbefehl mit 1: "
                         + result.stdout + result.stderr)
        self.assertTrue((result.stdout + result.stderr).strip())

    def test_github_complete_subcommand_skips_with_exit_zero(self):
        bare_url = seed_bare(self.base, "sub-cskip-origin")
        project = make_project(self.base, "sub-cskip", env_extra="",
                               with_origin=bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/läufer")

        result = self.run_packages("github-complete", "--project", str(project),
                                   "--branch", "feature/läufer")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_github_complete_subcommand_succeeds_with_exit_zero(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare_url = seed_bare(self.base, "sub-cok-origin")
        project = make_project(
            self.base, "sub-cok",
            env_extra=project_env("sub-cok", api=server.base),
            with_origin=bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/erfolgreich")
        (project / "arbeit.txt").write_text("arbeit\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "arbeit")
        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/erfolgreich", "--id", "AP9",
            github_token=FAKE_TOKEN)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts, "Merge-Request muss beantragt sein")

    def test_github_complete_subcommand_fails_with_exit_one(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        bare_url = seed_bare(self.base, "sub-cfail-origin")
        project = make_project(
            self.base, "sub-cfail",
            env_extra=project_env("sub-cfail", api=server.base),
            with_origin=bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/gescheitert")
        (project / "arbeit.txt").write_text("arbeit\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "arbeit")

        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/gescheitert")

        self.assertEqual(1, result.returncode,
                         "Fehlschlag endet mit 1: " + result.stdout + result.stderr)
        self.assertTrue((result.stdout + result.stderr).strip())
        self.not_disclosed(result.stdout + result.stderr)


# ===========================================================================
# Abnahme /: Verkabelung der GitHub-Subkommandos im Paketläufer
# ===========================================================================

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

# B16: Ein erreichbarer Merge-Request-Endpunkt ist für erfolgreiche
# Abschlüsse nötig; die harte Schranke blockiert sonst zu Recht.

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=1
"""

FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]

DEAD_API = "http://127.0.0.1:9"  # Loopback ohne Dienst: schnelle Verweigerung

GIT_IDENTITY_ap9 = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *args):
    return support.git(cwd, *args)


class AP9WiringFixture(unittest.TestCase):
    """Isolierter ``bin/vibe-run.sh`` mit nachgebildeten Agenten."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        # B16: ``install_runner`` kopiert ``vibe_github.py`` inzwischen mit;
        # ohne dieses Modul würde die harte GitHub-Abschlussschranke jede
        # Fake-Toolchain blockieren.
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()
        self.fakebin = support.install_fake_tools(self.root)

    # ------------------------------------------------------------ Projekt
    def make_project(self, env_extra="", feedback=FEEDBACK_ONE, name="proj"):
        project = self.root / name
        support.init_repo(project)
        support.write_project(
            project, PROJECT_ENV + env_extra, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        return project

    def link_origin(self, project, bare):
        """Verknüpft das Projekt mit einer lokalen Bare-Quelle (file://)."""
        result = git(project, "remote", "add", "origin", "file://" + str(bare))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def empty_bare(self, name):
        """Leere lokale Bare-Quelle mit main als Anfangsbranch.

        Kein Seed-Commit: Jede Fernhistorie entsteht aus dem Projektstand
        selbst, damit der Pull des Läufers fast-forward-fähig ist.
        """
        bare = self.root / "origin" / (name + ".git")
        bare.mkdir(parents=True, exist_ok=True)
        self.assertEqual(
            0, git(bare, "init", "-q", "--bare", "-b", "main").returncode)
        return bare

    def publish(self, project, bare, ahead_commits=0):
        """Setzt den Projektstand auf die Bare-Quelle und schiebt ihn
        optional um ``ahead_commits`` leere Fern-Commits voraus, die lokal
        wieder verworfen werden. Liefert den Fernstand (Rev-Parse)."""
        self.assertEqual(
            0, git(project, "push", "-q", "-u", "origin", "main").returncode)
        for step in range(ahead_commits):
            self.assertEqual(
                0, git(project, "commit", "--allow-empty", "-q", "-m",
                       "fernauftrag-%d" % step).returncode)
            self.assertEqual(
                0, git(project, "push", "-q", "origin", "main").returncode)
        remote_tip = git(bare, "rev-parse", "main").stdout.strip()
        if ahead_commits:
            self.assertEqual(
                0, git(project, "reset", "-q", "--hard",
                       "HEAD~%d" % ahead_commits).returncode)
            self.assertNotEqual(
                remote_tip, git(project, "rev-parse", "HEAD").stdout.strip(),
                "Vorbedingung: der Fernstand ist um Commits voraus")
        return remote_tip

    # -------------------------------------------------------------- Läufer
    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in ("AGENT", "MAX_PACKAGES", "MAX_RETRIES", "SANDBOX",
                    "SANDBOX_TOOLS", "VERIFY_FULL", "VERIFY_PACKAGE",
                    "GITHUB_TOKEN", "GH_TOKEN"):
            env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": project.name,
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "15",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_COUNTER": str(self.root / "counter"),
            "FAKE_CALLS": str(self.root / "calls.jsonl"),
        })
        env.update(GIT_IDENTITY_ap9)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=180, check=False,
        )

    def log(self, project=None):
        project = project or self.root / "proj"
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ---------------------------------------------------------- Assertions
    def worktrees(self):
        """Arbeitskopien des Laufs (leer, wenn noch keine angelegt wurden)."""
        root = self.runtime / "worktrees"
        return [entry for entry in root.iterdir()] if root.exists() else []

    def log_index(self, log, needle):
        for index, line in enumerate(log.splitlines()):
            if needle in line:
                return index
        return -1


class PullWiringTest(AP9WiringFixture):
    """github-pull: Reihenfolge nach Auswahl, vor der Arbeitskopie."""

    def test_a_failing_github_pull_is_a_hint_but_completion_blocks(self):
        """B16 ersetzt die AP9-Abschlusssemantik.

        Der fehlgeschlagene ``github-pull`` bleibt ein HINWEIS (AP9). Der
        anschließende GitHub-Abschluss ist dagegen eine echte Schranke: Weil
        origin nicht erreichbar ist, darf das Paket nicht lokal gemergt
        werden. B1/Anforderung 4: Der Läufer markiert den Bearbeitungsbeginn
        bereits mit ``mark-start``, das Ticket steht daher auf ``in-progress``
        und bleibt ungeschlossen; die Arbeitskopie bleibt liegen.
        """
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\n'))
        # origin zeigt ins Leere: fetch scheitert, push scheitert später —
        # beide Subkommandos enden mit Exit 1.
        self.link_origin(project, self.root / "origin" / "fehlt.git")

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            "Die fehlgeschlagene GitHub-Schranke muss den "
                            "Lauf blockieren:\n" + result.stdout + result.stderr)
        log = self.log(project)
        hint_pull = self.log_index(
            log, "HINWEIS: GitHub-Pull des Haupt-Branchs vor F1 fehlgeschlagen")
        header = self.log_index(log, "Arbeitspaket F1, Durchgang")
        blocked = self.log_index(
            log, "BLOCKIERT: GitHub-Abschluss für F1 fehlgeschlagen "
                 "(Push/Merge-Request):")
        fertig = self.log_index(log, "FERTIG")

        self.assertGreaterEqual(hint_pull, 0,
                                "Fehlender Pull erzeugt keinen HINWEIS:\n" + log)
        # Reihenfolge: HINWEIS vor dem Paketkopf — der Pull läuft nach der
        # Auswahl (er kennt F1) und vor dem Erfassen des Paketbases.
        self.assertLess(hint_pull, header, log)
        self.assertGreaterEqual(blocked, 0,
                                "Der GitHub-Abschluss blockiert nicht:\n" + log)
        self.assertEqual(-1, fertig,
                         "Ein blockiertes Paket darf nicht FERTIG melden:\n"
                         + log)
        # Das Paket ist NICHT lokal gemergt:
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            "Das Paket wurde trotz fehlgeschlagener GitHub-Schranke "
            "gemergt:\n" + log)
        # Das Ticket bleibt in Bearbeitung und ungeschlossen (B1: der Läufer
        # markiert den Start mit mark-start → in-progress):
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        record = {item["id"]: item for item in document["tickets"]}["F1"]
        self.assertEqual("in-progress", record["state"], record)
        report = (self.runtime / (project.name + ".report.txt")).read_text(
            encoding="utf-8")
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        # Die blockierte Arbeitskopie bleibt zur Diagnose liegen.
        worktree_root = self.runtime / "worktrees"
        self.assertTrue(
            worktree_root.exists() and any(worktree_root.iterdir()),
            "Die blockierte Arbeitskopie wurde entfernt")

    def test_a_successful_pull_updates_the_base_before_the_worktree(self):
        # B16: Die harte GitHub-Schranke verlangt einen erreichbaren
        # Merge-Request-Endpunkt; der REST-Fake liefert ihn für den Abschluss.
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % server.base))
        bare = self.empty_bare("aktuell")
        self.link_origin(project, bare)
        # Projektstand auf origin bringen; der Fernstand ist danach um einen
        # Commit voraus, der lokal wieder verworfen wurde.
        remote_tip = self.publish(project, bare, ahead_commits=1)

        result = self.run_runner(project)

        # AP4-Korbat: PR-only ist der Standard; der Lauf endet nach dem
        # Merge-Request, ohne lokal zu mergen. Der Paketbranch bleibt in der
        # Arbeitskopie und trägt den Nachweis der Reihenfolge.
        log = self.log(project)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Pull"),
            "Ein erfolgreicher Pull läuft unsichtbar weiter:\n" + log)
        branch = git(project, "rev-parse", "--verify",
                     "refs/heads/feature/test/f1")
        self.assertEqual(0, branch.returncode,
                         "Der Paketbranch fehlt:\n" + log)
        # Der erste Paketcommit baut unmittelbar auf dem gezogenen
        # Fernstand auf: der Pull ist vor Arbeitskopie/Paketbase gelaufen.
        history = git(project, "log", "--format=%H %P %s",
                      "feature/test/f1").stdout.splitlines()
        parent = None
        for line in reversed(history):
            fields = line.split(" ", 2)
            if len(fields) >= 3 and fields[2].startswith("F1:"):
                # Ältester Paketcommit: sein Elternteil ist der Paketbase.
                parent = fields[1].split(" ")[0]
                break
        self.assertIsNotNone(parent, "Kein Paketcommit F1 gefunden:\n" + log)
        self.assertEqual(remote_tip, parent,
                         "Der Paketbase ist nicht der gezogene Fernstand:\n"
                         + log)


class CompleteWiringTest(AP9WiringFixture):
    """github-complete: erst nach grüner Schranke, vor dem Merge."""

    def test_complete_is_not_called_when_the_gate_is_red(self):
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % DEAD_API))
        bare = self.empty_bare("schranke")
        self.link_origin(project, bare)
        self.publish(project, bare)
        # Der Agent beendet sich sauber, liefert aber keine Nachweise:
        # die Paketprüfung ist grün, die Abschlussschranke rot.

        result = self.run_runner(project, FAKE_MODE="no-artifacts")

        self.assertNotEqual(0, result.returncode,
                            "Eine rote Schranke darf nicht FERTIG melden")
        log = self.log(project)
        self.assertIn("Abschlussschranke für F1 nicht erfüllt", log, log)
        self.assertIn("BLOCKIERT", log, log)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Abschluss"),
            "github-complete darf erst nach grüner Schranke laufen:\n" + log)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Pull"),
            "Der Pull läuft auch hier (unsichtbar) vor dem Paket:\n" + log)
        listing = git(project, "ls-tree", "--name-only", "HEAD",
                      "impl-F1.txt")
        self.assertEqual(0, listing.returncode, listing.stderr)
        self.assertEqual(
            "", listing.stdout.strip(),
            "Ohne grüne Schranke darf nichts in den Integrationsstand "
            "gemergt sein:\n" + log)


# ===========================================================================
# (GitHub-Teil): T-G0, T-G7, T-G1, T-G2, T-G3, T-G4
# ===========================================================================

import importlib.machinery
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BIN = REPO / "bin"
GITHUB_MODULE_ap4 = BIN / "vibe_github.py"
PACKAGES_ap4 = BIN / "vibe_packages.py"
RUNS_PY = BIN / "vibe_runs.py"
CLI = BIN / "vibe"

FAKE_TOKEN_ap4 = "ap4-korbat-env-token-0815"
WORKTREE_TOKEN = "ap5-korbat-worktree-token-4711"

ISOLATED_ENV_ap4 = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    # Die Läuferumgebung setzt GITHUB_AUTO_MERGE=1 (autonomer Lauf); die
    # Prüfungen hier erwarten PR-only (Standard aus), solange project.env
    # den Schalter nicht ausdrücklich setzt.
    "GITHUB_AUTO_MERGE",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
)


_CACHE = {}


def github_module_ap4():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _CACHE:
        return _CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_ap4_under_test", str(GITHUB_MODULE_ap4))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _CACHE["gh"] = module
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap4_github_cli_under_test", str(CLI))
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


def real_git_ap4(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def fresh_env(**extra):
    env = {key: value for key, value in os.environ.items()
           if key not in ISOLATED_ENV_ap4 and not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    env.update(GIT_IDENTITY)
    env.update({key: str(value) for key, value in extra.items()})
    return env


def seed_bare_ap4(root, name):
    """Bare-Origin mit einem Ausgangscommit; liefert (url, seed-pfad)."""
    work = Path(root) / "seed" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "shared.txt").write_text("base\n", encoding="utf-8")
    real_git_ap4(work, "init", "-q", "-b", "main")
    real_git_ap4(work, "add", "-A")
    real_git_ap4(work, "commit", "-q", "-m", "seed")
    bare = Path(root) / "origin" / (name + ".git")
    bare.mkdir(parents=True, exist_ok=True)
    real_git_ap4(bare, "init", "-q", "--bare")
    real_git_ap4(work, "remote", "add", "origin", str(bare))
    real_git_ap4(work, "push", "-q", "origin", "main")
    real_git_ap4(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare), work


def clone_project(root, name, url):
    project = Path(root) / name
    real_git_ap4(root, "clone", "-q", url, str(project))
    return project


def push_remote_change(seed, name, content, message="remote"):
    (seed / name).write_text(content, encoding="utf-8")
    real_git_ap4(seed, "add", "-A")
    real_git_ap4(seed, "commit", "-q", "-m", message)
    real_git_ap4(seed, "push", "-q", "origin", "main")


class GithubCase(unittest.TestCase):
    """Isolierte Prozessumgebung; GitHub/REST nie echt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_ap4}
        self.addCleanup(self.restore_env)
        for key in ISOLATED_ENV_ap4:
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module_ap4()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------- T-G0 config
class AutoMergeConfigTest(GithubCase):
    """AK T-G0: Binärer Schalter ``auto_merge`` mit Standard aus."""

    def write_env(self, text):
        env_path = self.base / "project.env"
        env_path.write_text(text, encoding="utf-8")
        return env_path

    def test_missing_key_defaults_auto_merge_off(self):
        """Vorbedingung: project.env ohne GITHUB_AUTO_MERGE.
        Aktion: ``read_config`` lesen.
        Erwartung: ``auto_merge`` ist ``False`` (PR-only ist der Standard).
        Fehlerfall: fehlender Schlüssel, Wahrwert oder Ausnahme.
        """
        env_path = self.write_env('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n')

        config = self.gh.read_config(str(env_path))

        self.assertIn("auto_merge", config, config)
        self.assertIs(config["auto_merge"], False, config)

    def test_empty_and_one_values_are_read_binary(self):
        """Vorbedingung: project.env mit GITHUB_AUTO_MERGE leer bzw. "1".
        Aktion: ``read_config`` je Wert lesen.
        Erwartung: "" → False, "1" → True; ein Enum gibt es nicht.
        Fehlerfall: leerer Wert gilt als an oder "1" wird nicht erkannt.
        """
        for value, expected in (("", False), ("1", True)):
            with self.subTest(value=value):
                env_path = self.write_env(
                    'GITHUB_ENABLED="1"\nGITHUB_AUTO_MERGE="%s"\n' % value)
                config = self.gh.read_config(str(env_path))
                self.assertIs(config["auto_merge"], expected, config)

    def test_status_exposes_auto_merge(self):
        """Vorbedingung: Projekt ohne/mit aktiviertem Auto-Merge.
        Aktion: ``status(project)`` lesen.
        Erwartung: ``status["auto_merge"]`` entspricht der Konfiguration.
        Fehlerfall: Status verschweigt den Schalter oder liefert einen String.
        """
        for value, expected in (("", False), ("1", True)):
            with self.subTest(value=value):
                project = self.base / ("status-%s" % (value or "aus"))
                project.mkdir()
                real_git_ap4(project, "init", "-q", "-b", "main")
                real_git_ap4(project, "commit", "--allow-empty", "-q", "-m", "init")
                (project / ".vibe").mkdir()
                (project / ".vibe" / "project.env").write_text(
                    'GITHUB_ENABLED="1"\nGITHUB_AUTO_MERGE="%s"\n' % value,
                    encoding="utf-8")
                view = self.gh.status(project, remote=False)
                self.assertIn("auto_merge", view, view)
                self.assertIs(view["auto_merge"], expected, view)


# ------------------------------------------------------------ T-G7 mergeability
class EnsureMergeableTest(GithubCase):
    """AK T-G7: Basis in den Paketbranch mergen, Konflikte stehen lassen."""

    def run_ensure(self, project, base="origin/main"):
        return subprocess.run(
            [sys.executable, str(PACKAGES_ap4), "ensure-mergeable",
             "--project", str(project), "--base", base],
            cwd=str(REPO), env=fresh_env(), capture_output=True,
            text=True, timeout=120, check=False,
        )

    def feature_project(self, name, conflicting=False):
        url, seed = seed_bare_ap4(self.base, name)
        project = clone_project(self.base, name, url)
        real_git_ap4(project, "checkout", "-q", "-b", "feature/x")
        if conflicting:
            (project / "shared.txt").write_text("feature\n", encoding="utf-8")
        else:
            (project / "feature.txt").write_text("feature\n", encoding="utf-8")
        real_git_ap4(project, "add", "-A")
        real_git_ap4(project, "commit", "-q", "-m", "feature: change")
        if conflicting:
            push_remote_change(seed, "shared.txt", "remote\n")
        else:
            push_remote_change(seed, "remote.txt", "remote\n")
        return project, seed

    def test_base_already_ancestor_is_ok_without_a_new_commit(self):
        """Vorbedingung: Featurebranch zweigt vom aktuellen origin/main ab.
        Aktion: ``ensure-mergeable --base origin/main``.
        Erwartung: Exit 0, HEAD unverändert, kein Merge-Commit.
        Fehlerfall: unnötiger Merge oder Fehlschlag.
        """
        url, _seed = seed_bare_ap4(self.base, "ancestor")
        project = clone_project(self.base, "ancestor", url)
        real_git_ap4(project, "checkout", "-q", "-b", "feature/x")
        (project / "feature.txt").write_text("x\n", encoding="utf-8")
        real_git_ap4(project, "add", "-A")
        real_git_ap4(project, "commit", "-q", "-m", "feature: x")
        before = real_git_out(project, "rev-parse", "HEAD")

        result = self.run_ensure(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, real_git_out(project, "rev-parse", "HEAD"),
                         "Die Basis war bereits Vorfahr; kein Commit erwartet")

    def test_advanced_base_is_merged_with_a_merge_commit_and_not_pushed(self):
        """Vorbedingung: origin/main ist um einen Commit voraus.
        Aktion: ``ensure-mergeable`` im Featurebranch ausführen.
        Erwartung: Exit 0; HEAD ist ein Merge-Commit mit origin/main als
        zweitem Elternteil; beide Änderungen sind vorhanden; der Branch wird
        NICHT gepusht (kein origin/feature/x).
        Fehlerfall: kein Merge, Fast-Forward, Push oder fehlende Änderung.
        """
        project, _seed = self.feature_project("advanced")
        bare = self.base / "origin" / "advanced.git"

        result = self.run_ensure(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        parents = real_git_out(
            project, "rev-list", "--parents", "-n", "1", "HEAD").split()
        self.assertEqual(3, len(parents),
                         "HEAD ist kein Merge-Commit: " + " ".join(parents))
        self.assertEqual("remote\n",
                         (project / "remote.txt").read_text(encoding="utf-8"),
                         "Die Fernänderung fehlt nach dem Merge")
        self.assertEqual("base\n",
                         (project / "shared.txt").read_text(encoding="utf-8"),
                         "Unveränderte Datei darf durch den Merge nicht "
                         "verändert werden")
        self.assertTrue((project / "feature.txt").is_file())
        remote_branch = real_git_ap4(
            bare, "rev-parse", "--verify", "refs/heads/feature/x", check=False)
        self.assertNotEqual(
            0, remote_branch.returncode,
            "ensure-mergeable darf den Branch nicht pushen")

    def test_conflict_is_left_in_the_worktree_and_paths_are_reported(self):
        """Vorbedingung: basis und Feature ändern dieselbe Datei.
        Aktion: ``ensure-mergeable`` ausführen.
        Erwartung: Exit ≠ 0; ``.git/MERGE_HEAD`` zeigt einen laufenden Merge
        (kein Abbruch); ``shared.txt`` ist als konfliktbehaftet gemeldet und
        im Index als unmerged geführt.
        Fehlerfall: Merge wird abgebrochen, Pfad fehlt in der Ausgabe oder es
        wird fälschlich Erfolg gemeldet.
        """
        project, _seed = self.feature_project("konflikt", conflicting=True)

        result = self.run_ensure(project)

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertTrue((project / ".git" / "MERGE_HEAD").exists(),
                        "Der Merge wurde abgebrochen statt stehen gelassen")
        unmerged = real_git_out(project, "ls-files", "-u")
        self.assertIn("shared.txt", unmerged)
        self.assertIn("shared.txt", output,
                      "Der konfliktbehaftete Pfad wurde nicht gemeldet:\n"
                      + output)

    def test_after_a_repair_the_second_run_is_clean(self):
        """Vorbedingung: Konfliktfall aus dem vorigen Fall.
        Aktion: Konflikt im Arbeitsbaum lösen, ``git add`` und committen,
        danach ``ensure-mergeable`` erneut ausführen.
        Erwartung: zweiter Aufruf Exit 0, sauberer Baum, kein MERGE_HEAD.
        Fehlerfall: Reparatur wird nicht erkannt oder es bleibt ein Konflikt.
        """
        project, _seed = self.feature_project("reparatur", conflicting=True)
        first = self.run_ensure(project)
        self.assertNotEqual(0, first.returncode)

        (project / "shared.txt").write_text("feature\nremote\n", encoding="utf-8")
        real_git_ap4(project, "add", "shared.txt")
        real_git_ap4(project, "commit", "-q", "-m", "Konflikt gelöst")
        second = self.run_ensure(project)

        self.assertEqual(0, second.returncode,
                         second.stdout + second.stderr)
        self.assertFalse((project / ".git" / "MERGE_HEAD").exists())
        self.assertEqual("", real_git_out(project, "status", "--porcelain"))


class EnsureMergeableCredentialTest(GithubCase):
    """AP5-Korbat 4c: Credential einmal aus dem Projektordner für den Worktree.

    ``ensure_mergeable(project, worktree)`` führt Git im Worktree aus, muss
    den verschlüsselten Projekt-Token aber über den Projektpfad auflösen und
    an alle Git-Aufrufe weiterreichen. Sonst scheitert ``git fetch origin`` im
    Worktree mit „could not read Username“, obwohl der Projektpfad einen Token
    besitzt.
    """

    def setUp(self):
        super().setUp()
        self.project = self.base / "projekt"
        self.project.mkdir()
        (self.project / ".vibe").mkdir()
        (self.project / ".vibe" / "project.env").write_text(
            'GITHUB_ENABLED="1"\nGITHUB_BASE="main"\n', encoding="utf-8")
        self.worktree = self.base / "worktree"
        self.worktree.mkdir()

    def stub_git(self, calls, fetch=(0, "")):
        """Ersetzt subprocess.run und protokolliert argv/cwd/ENV."""

        def stub(argv, **kwargs):
            record = {
                "argv": [str(item) for item in argv],
                "cwd": kwargs.get("cwd"),
                "env": dict(kwargs.get("env") or {}),
            }
            calls.append(record)
            if "remote" in record["argv"]:
                return types.SimpleNamespace(
                    returncode=0,
                    stdout="origin\tfile:///tmp/origin (fetch)\n",
                    stderr="")
            if "fetch" in record["argv"]:
                return types.SimpleNamespace(
                    returncode=fetch[0], stdout=fetch[1], stderr="")
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        return stub

    def test_fetch_in_the_worktree_uses_the_project_token(self):
        """Vorbedingung: Projekt hat einen Projekt-Token, der Worktree einen
        anderen; Base ``origin/main`` ist bereits Vorfahr.
        Aktion: ``ensure_mergeable(project, worktree, base="origin/main")`` mit
        protokolliertem Git-Stub ausführen.
        Erwartung: ``git fetch`` im Worktree erhält den Token des
        PROJEKTordners über die Prozessumgebung; der Token steht nie in argv
        oder der Meldung; das Ergebnis ist erfolgreich.
        Fehlerfall: Worktree-Pfad löst die Credential-Kette aus (falscher oder
        kein Token) → scheinbarer Token-Fehler.
        """
        self.gh.save_project_token(self.project, FAKE_TOKEN_ap4)
        self.gh.save_project_token(self.worktree, WORKTREE_TOKEN)
        calls = []

        with mock.patch("subprocess.run", self.stub_git(calls)):
            ok, message, result = self.gh.ensure_mergeable(
                self.project, self.worktree, base="origin/main")

        self.assertTrue(ok, message)
        fetch_calls = [record for record in calls
                       if "fetch" in record["argv"]]
        self.assertTrue(fetch_calls, "git fetch wurde nicht ausgeführt")
        credential_key = self.gh.CREDENTIAL_ENV_NAME
        for record in calls:
            self.assertEqual(
                FAKE_TOKEN_ap4, record["env"].get(credential_key),
                "Git im Worktree nutzt nicht den Projekt-Token: %r"
                % (record["argv"],))
            self.assertNotIn(FAKE_TOKEN_ap4, "\n".join(record["argv"]),
                             "Der Token darf nie in argv stehen")
        self.assertNotIn(FAKE_TOKEN_ap4, message)
        self.assertNotIn(WORKTREE_TOKEN, message)

    def test_without_any_token_the_fetch_fails_with_guidance(self):
        """Vorbedingung: Weder Projekt- noch Umgebungstoken vorhanden.
        Aktion: ``ensure_mergeable``; der Stub lässt ``git fetch`` mit der
        üblichen Git-Auth-Meldung scheitern.
        Erwartung: ``ok`` ist False; die Meldung enthält die verständliche
        Token-Guidance; ein Credential wird nicht injiziert.
        Fehlerfall: stiller Erfolg oder rohe Git-Meldung ohne Hilfe.
        """
        calls = []
        failure = (128, "fatal: could not read Username for "
                        "'https://github.com': terminal prompts disabled")

        with mock.patch("subprocess.run",
                        self.stub_git(calls, fetch=failure)):
            ok, message, _result = self.gh.ensure_mergeable(
                self.project, self.worktree, base="origin/main")

        self.assertFalse(ok)
        self.assertIn("Zugangsdaten", message, message)
        fetch_call = [record for record in calls
                      if "fetch" in record["argv"]][-1]
        self.assertNotIn(
            self.gh.CREDENTIAL_ENV_NAME, fetch_call["env"],
            "Ohne Token darf kein Credential weitergegeben werden")


# ----------------------------------------------------------------- T-G2 prune
class PruneFetchTest(GithubCase):
    """AK T-G2: Jeder Fetch entfernt veraltete Fern-Referenzen."""

    def project_with_origin(self, name):
        url, seed = seed_bare_ap4(self.base, name)
        project = clone_project(self.base, name, url)
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            'GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
            'GITHUB_BASE="main"\n', encoding="utf-8")
        # Eine temporäre Fern-Referenz anlegen und wieder löschen.
        real_git_ap4(project, "push", "-q", "origin", "main:temp")
        real_git_ap4(project, "fetch", "-q", "origin")
        real_git_ap4(seed, "push", "-q", "origin", "--delete", "temp")
        return project

    def stale_ref_exists(self, project):
        return real_git_ap4(
            project, "rev-parse", "--verify", "--quiet",
            "refs/remotes/origin/temp", check=False).returncode == 0

    def test_fetch_prunes_deleted_remote_branches(self):
        """Vorbedingung: origin/temp ist lokal bekannt, auf dem Fern gelöscht.
        Aktion: ``vibe_github.fetch(project)``.
        Erwartung: ``origin/temp`` ist danach entfernt.
        Fehlerfall: veraltete Fern-Referenz bleibt stehen.
        """
        project = self.project_with_origin("prune-fetch")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        ok, message = self.gh.fetch(project)

        self.assertTrue(ok, message)
        self.assertFalse(self.stale_ref_exists(project),
                         "fetch hat veraltete Fern-Referenzen nicht entfernt: "
                         + message)

    def test_pull_integration_prunes_deleted_remote_branches(self):
        """Vorbedingung: wie oben; GitHub ist aktiviert.
        Aktion: ``pull_integration(project)``.
        Erwartung: ``origin/temp`` ist entfernt, der Branch bleibt aktuell.
        Fehlerfall: Pull lässt veraltete Fern-Referenzen zurück.
        """
        project = self.project_with_origin("prune-pull")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        performed, ok, message = self.gh.pull_integration(project)

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertFalse(self.stale_ref_exists(project),
                         "pull_integration hat nicht gepruned: " + message)

    def test_integration_state_prunes_deleted_remote_branches(self):
        """Vorbedingung: wie oben; GitHub ist aktiviert.
        Aktion: ``integration_state(project)``.
        Erwartung: ``origin/temp`` ist entfernt und der Zustand bleibt ok.
        Fehlerfall: Prüfung lässt veraltete Fern-Referenzen zurück.
        """
        project = self.project_with_origin("prune-state")
        self.assertTrue(self.stale_ref_exists(project), "Vorbedingung fehlt")

        state = self.gh.integration_state(project)

        self.assertTrue(state["ok"], state["message"])
        self.assertFalse(self.stale_ref_exists(project),
                         "integration_state hat nicht gepruned: "
                         + state["message"])

    def test_ensure_mergeable_source_fetches_with_prune(self):
        """Vorbedingung: Quelltext der Läufermodule.
        Aktion: Umgebung des neuen Subkommandos lesen.
        Erwartung: Der ensure-mergeable-Fetch ist mit ``--prune`` verdrahtet
        (der enge Refspec lässt sich nicht verhaltensbasiert prüfen).
        Fehlerfall: Fetch ohne ``--prune``.
        """
        source = (PACKAGES_ap4.read_text(encoding="utf-8")
                  + GITHUB_MODULE_ap4.read_text(encoding="utf-8"))
        self.assertRegex(
            source,
            r"ensure[-_]mergeable[\s\S]{0,2000}?--prune",
            "ensure-mergeable nutzt keinen prune-Fetch")


# --------------------------------------------------------------- T-G3 upstream
class GithubLinkUpstreamTest(unittest.TestCase):
    """AK T-G3: ``github_link`` setzt best-effort den Upstream."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.saved = {key: os.environ.get(key)
                      for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME",
                                  "GITHUB_TOKEN", "GH_TOKEN")}
        self.addCleanup(self.restore)
        for key in ("GITHUB_TOKEN", "GH_TOKEN"):
            os.environ.pop(key, None)
        self.project = self.workspace / "proj"
        self.url, self.seed = seed_bare_ap4(self.base, "link-origin")
        self.bare = self.base / "origin" / "link-origin.git"
        real_git_ap4(self.workspace, "clone", "-q", self.url, "proj")
        (self.project / ".vibe").mkdir()
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        real_git_ap4(self.project, "add", "-A")
        real_git_ap4(self.project, "commit", "-q", "-m", "projekt")
        self.cli = load_cli(self.workspace, self.home)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_link_sets_upstream_for_branches_with_a_remote_counterpart(self):
        """Vorbedingung: lokale Branches ``main`` und ``feature/up`` haben
        beide ``origin/<branch>``; ``feature/up`` hat noch keinen Upstream.
        Aktion: ``github_link(proj, file://…)`` aufrufen.
        Erwartung: beide Branches zeigen auf ``origin/<branch>``.
        Fehlerfall: Upstream fehlt weiterhin.
        """
        real_git_ap4(self.project, "checkout", "-q", "-b", "feature/up")
        (self.project / "up.txt").write_text("up\n", encoding="utf-8")
        real_git_ap4(self.project, "add", "-A")
        real_git_ap4(self.project, "commit", "-q", "-m", "up")
        real_git_ap4(self.project, "push", "-q", "origin", "feature/up")
        real_git_ap4(self.project, "checkout", "-q", "main")

        self.cli.github_link("proj", "file://" + str(self.bare))

        for branch in ("main", "feature/up"):
            with self.subTest(branch=branch):
                upstream = real_git_ap4(
                    self.project, "rev-parse", "--abbrev-ref",
                    branch + "@{upstream}", check=False)
                self.assertEqual(
                    0, upstream.returncode,
                    "Kein Upstream für %s: %s" % (branch, upstream.stderr))
                self.assertEqual("origin/" + branch, upstream.stdout.strip())

    def test_link_is_not_fatal_when_a_local_branch_has_no_counterpart(self):
        """Vorbedingung: lokaler Branch ``nur-lokal`` ohne ``origin/``-Pendant.
        Aktion: ``github_link`` aufrufen.
        Erwartung: Aufruf gelingt; der Branch bleibt ohne Upstream.
        Fehlerfall: Link bricht wegen des fehlenden Gegenstücks ab.
        """
        real_git_ap4(self.project, "branch", "nur-lokal")

        view = self.cli.github_link("proj", "file://" + str(self.bare))

        self.assertTrue(view.get("enabled"), view)
        upstream = real_git_ap4(
            self.project, "rev-parse", "--abbrev-ref",
            "nur-lokal@{upstream}", check=False)
        self.assertNotEqual(0, upstream.returncode,
                            "Für einen Branch ohne Fern-Pendant darf kein "
                            "Upstream gesetzt werden")


class GithubCliStatusTest(unittest.TestCase):
    """AK Review-Befund 3: ``vibe github <projekt> status`` nennt Auto-Merge."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.saved = {key: os.environ.get(key)
                      for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
        self.addCleanup(self.restore)
        self.project = self.workspace / "proj"
        real_git_ap4(self.workspace, "init", "-q", "-b", "main", "proj")
        real_git_ap4(self.project, "config", "user.name", "Test")
        real_git_ap4(self.project, "commit", "--allow-empty", "-q", "-m", "init")
        (self.project / ".vibe").mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def status_output(self, auto_merge):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nGITHUB_ENABLED=""\nGITHUB_AUTO_MERGE="%s"\n'
            % auto_merge, encoding="utf-8")
        out = io.StringIO()
        self.cli.cmd_github("proj", "status", out=out)
        return out.getvalue()

    def auto_merge_line(self, output):
        for line in output.splitlines():
            if "Auto-Merge:" in line:
                return line
        return ""

    def test_status_names_auto_merge_ja_when_enabled(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE="1"``.
        Aktion: ``vibe github proj status`` über ``cmd_github(..., out=…)``.
        Erwartung: Eine Zeile „Auto-Merge:“ meldet „ja“.
        Fehlerfall: Der Status verschweigt den Schalter.
        """
        output = self.status_output("1")

        line = self.auto_merge_line(output)
        self.assertTrue(line, "Keine Auto-Merge-Zeile im Status:\n" + output)
        self.assertIn("ja", line.lower(), line)

    def test_status_names_auto_merge_nein_when_disabled(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE=""`` (Standard aus).
        Aktion: ``vibe github proj status``.
        Erwartung: Eine Zeile „Auto-Merge:“ meldet „nein“.
        Fehlerfall: Aus wird als an dargestellt.
        """
        output = self.status_output("")

        line = self.auto_merge_line(output)
        self.assertTrue(line, "Keine Auto-Merge-Zeile im Status:\n" + output)
        self.assertIn("nein", line.lower(), line)


# ------------------------------------------------------- T-G4 worktree checkout
class WorktreeCheckoutTest(GithubCase):
    """AK T-G4: Ein in einer Arbeitskopie ausgecheckter Branch bleibt tabu."""

    def test_checkout_branch_refuses_a_branch_held_by_another_worktree(self):
        """Vorbedingung: ``feature/held`` ist in einer zweiten Arbeitskopie
        ausgecheckt, das Projekt steht auf ``main``.
        Aktion: ``checkout_branch(project, "feature/held")``.
        Erwartung: Die Funktion verweigert mit einer Meldung, die die
        Arbeitskopie nennt; das Projekt bleibt auf ``main``.
        Fehlerfall: Der Branch wird gewaltsam ausgecheckt oder eine
        unverständliche Git-Fehlermeldung durchgereicht.
        """
        url, _seed = seed_bare_ap4(self.base, "worktree-held")
        project = clone_project(self.base, "worktree-held", url)
        real_git_ap4(project, "branch", "feature/held")
        second = self.base / "second-worktree"
        real_git_ap4(project, "worktree", "add", "-q", str(second), "feature/held")

        try:
            ok, message = self.gh.checkout_branch(project, "feature/held")
        except ValueError as error:
            ok, message = False, str(error)

        self.assertFalse(ok, "Branch in fremder Arbeitskopie wurde ausgecheckt")
        self.assertIn("Arbeitskopie", str(message), str(message))
        self.assertEqual("main", real_git_out(project, "rev-parse",
                                              "--abbrev-ref", "HEAD"))


# -------------------------------------------- T-G0/T-G1 runner ownership paths
class _MergeHandler(BaseHTTPRequestHandler):
    """REST-Fake: PR-Erstellung, Zustandsabfrage und Squash-Merge."""

    def log_message(self, fmt, *args):
        pass

    def _record(self, body=b""):
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")) if body else None,
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
        merged = bool(self.server.merged)
        self._respond(200, {
            "number": 42, "state": "closed" if merged else "open",
            "merged": merged,
            "mergeable": True, "mergeable_state": "clean",
            "merged_at": "2026-01-01T00:00:00Z" if merged else None,
            "html_url": self.server.pr_url,
        })

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        if self.path.rstrip("/").endswith("/pulls"):
            self._respond(201, {"number": 42, "html_url": self.server.pr_url,
                                "state": "open", "merged": False})
            return
        self._respond(404, {"message": "Not Found"})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        if self.path.rstrip("/").endswith("/merge"):
            try:
                self.server.on_merge()
            except Exception as error:  # noqa: BLE001 - im Fake sichtbar machen
                self.server.merge_error = repr(error)
                self._respond(500, {"message": "fake merge failed"})
                return
            self.server.merged = True
            self._respond(200, {"merged": True, "sha": "squash",
                                "message": "Pull Request successfully merged"})
            return
        self._respond(404, {"message": "Not Found"})


class MergeRestFakeServer:
    """Loopback-REST-Fake mit optionalem Squash-Merge-Callback."""

    def __init__(self, on_merge=None, port=None):
        self.requests = []
        self.on_merge = on_merge or (lambda: None)
        self.merge_error = ""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if port is None:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _MergeHandler)
        self.httpd.requests = self.requests
        self.httpd.on_merge = self.on_merge
        self.httpd.merge_error = ""
        self.httpd.merged = False
        self.httpd.pr_url = "http://127.0.0.1:%d/pull/42" % port
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def calls(self, method):
        return [item for item in self.requests
                if item["method"] == method]

    def puts(self):
        return self.calls("PUT")

    def posts(self):
        return self.calls("POST")


class RunnerFixtureMixin:
    """AP9-Läuferfixture: echtes Git, Fake-Agent, lokale Bare-Quelle."""

    def _fixture(self):
        # Import hier, damit das Modul auch ohne die Fixture ladbar bleibt.
        return AP9WiringFixture

    def setUp(self):
        fixture = self._fixture()
        self.fixture = fixture
        fixture.setUp(self)

    def tearDown(self):
        self.fixture.tearDown(self)

    def run_runner(self, project, **extra):
        return self.fixture.run_runner(self, project, **extra)

    def env(self, project, **extra):
        env = self.fixture.env(self, project, **extra)
        # Die Läuferumgebung setzt GITHUB_AUTO_MERGE=1 (autonomer Lauf). Der
        # Läufer liest den Schalter aus seiner Prozessumgebung; ohne diese
        # Bereinigung würde ein Projekt ohne project.env-Eintrag trotzdem
        # automatisch mergen. Gesetzt wird er nur noch über project.env.
        env.pop("GITHUB_AUTO_MERGE", None)
        return env

    def log(self, project=None):
        return self.fixture.log(self, project)

    def worktrees(self):
        return self.fixture.worktrees(self)

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def make_github_project(self, api, auto_merge=None, name="proj"):
        extra = ('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                 'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % api)
        if auto_merge is not None:
            extra += 'GITHUB_AUTO_MERGE="%s"\n' % auto_merge
        return self.fixture.make_project(
            self, env_extra=extra, feedback=FEEDBACK_ONE, name=name)

    def prepare_origin(self, project, name="proj"):
        bare = self.fixture.empty_bare(self, name)
        self.fixture.link_origin(self, project, bare)
        self.fixture.publish(self, project, bare)
        return bare

    def squash_merge_to_bare(self, bare, branch="feature/test/f1"):
        """Simuliert den GitHub-Squash-Merge auf dem Fern-Integrationsstand."""
        seed = self.root / "squash-seed"
        if not seed.exists():
            real_git_ap4(self.root, "clone", "-q", "file://" + str(bare), str(seed))
        real_git_ap4(seed, "fetch", "-q", "origin")
        real_git_ap4(seed, "checkout", "-q", "-B", "main", "origin/main")
        real_git_ap4(seed, "merge", "--squash", "-q", "origin/" + branch)
        real_git_ap4(seed, "-c", "user.name=Test", "-c",
                 "user.email=test@example.invalid", "commit", "-q", "-m",
                 "F1: squash")
        real_git_ap4(seed, "push", "-q", "origin", "main")
        return real_git_out(bare, "rev-parse", "main")

    def worktree_registry(self):
        sys.path.insert(0, str(BIN))
        try:
            from vibe_runs import WorktreeRegistry  # noqa: PLC0415
        finally:
            sys.path.remove(str(BIN))
        return WorktreeRegistry(str(self.runtime))


class PrOnlyRunnerTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-G0/T-G1: Ohne Schalter bleibt der PR-only-Standard stehen."""

    def test_pr_only_stops_without_local_merge_and_keeps_the_worktree(self):
        """Vorbedingung: GitHub aktiv, ``GITHUB_AUTO_MERGE`` nicht gesetzt;
        Paket und REST-Fake bereit.
        Aktion: Läufer ausführen.
        Erwartung: Branch wird gepusht und der MR gestellt; KEIN lokaler
        Merge, Arbeitskopie bleibt, Registry-Eintrag mit MR-URL existiert,
        Ticket bleibt offen mit Wartevermerk (AP5-Korbat 4a: „WARTET AUF
        MERGE“ statt BLOCKIERT); Protokoll nennt „wartet auf Merge“ und
        ``vibe package close``; kein REST-Merge.
        Fehlerfall: lokaler Merge, Cleanup, stilles Verschlucken oder
        fehlender Wartehinweis.
        """
        server = MergeRestFakeServer().start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base)
        bare = self.prepare_origin(project)

        result = self.run_runner(project)
        log = self.log(project)

        self.assertIn("wartet auf merge", log.lower(),
                      "Kein Wartehinweis im Protokoll:\n" + log)
        self.assertIn("vibe package close", log,
                      "Der nächste Schritt fehlt im Protokoll:\n" + log)
        self.assertNotEqual(
            0, real_git_ap4(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode,
            "PR-only darf nicht lokal mergen:\n" + log)
        self.assertEqual(
            0, real_git_ap4(bare, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Der Paketbranch muss gepusht sein")
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        record = {item["id"]: item for item in document["tickets"]}["F1"]
        self.assertEqual("waiting-merge", record["state"], record)
        self.assertTrue(record.get("waiting_note"), record)
        self.assertNotEqual("blocked", record["state"], record)
        self.assertTrue(self.fixture.worktrees(self), "Arbeitskopie fehlt")
        entries = self.worktree_registry().all()
        self.assertTrue(
            any(entry.get("id") == "F1"
                and entry.get("pr_url", "").endswith("/pull/42")
                for entry in entries),
            "Registry-Eintrag mit MR-URL fehlt: " + repr(entries))
        self.assertEqual([], server.puts(),
                         "PR-only darf keinen REST-Merge auslösen")


class AutoMergeRunnerTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-G0: ``GITHUB_AUTO_MERGE="1"`` mergt den PR und räumt auf."""

    def test_auto_merge_squashes_the_pr_and_cleans_up(self):
        """Vorbedingung: ``GITHUB_AUTO_MERGE="1"``; REST-Fake kann PR
        anlegen, abfragen und squash-mergen; der Merge-Callback schreibt den
        Squash-Commit auf den Fern-Integrationsstand.
        Aktion: Läufer ausführen.
        Erwartung: Exit 0; genau ein REST-Merge mit ``merge_method=squash``;
        der Integrationsstand ist auf der Fernspitze, enthält die
        Paketänderung und den abgehakten Nachweis; Arbeitskopie, Branch und
        Registry-Eintrag sind entfernt.
        Fehlerfall: kein Merge, falsche Merge-Art, lokaler Altstand oder
        zurückbleibende Arbeitskopie.
        """
        bare = None
        server = None

        def merge():
            self.squash_merge_to_bare(bare)

        server = MergeRestFakeServer(on_merge=merge).start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base, auto_merge="1")
        bare = self.prepare_origin(project)

        result = self.run_runner(project)
        log = self.log(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", server.merge_error)
        puts = server.puts()
        self.assertTrue(puts, "Kein REST-Merge ausgelöst:\n" + log)
        self.assertEqual("squash", (puts[-1]["body"] or {}).get("merge_method"),
                         puts[-1])
        remote_tip = real_git_out(bare, "rev-parse", "main")
        self.assertEqual(remote_tip, real_git_out(project, "rev-parse", "HEAD"),
                         "Der Integrationsstand ist nicht auf der Fernspitze")
        self.assertEqual(
            0, real_git_ap4(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode,
            "Die Paketänderung fehlt im Integrationsstand")
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "done",
            {item["id"]: item for item in document["tickets"]}["F1"]["state"])
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn("Merge-Request http://127.0.0.1:", report)
        self.assertNotEqual(
            0, real_git_ap4(project, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Der lokale Paketbranch muss entfernt sein")
        self.assertFalse(
            any((self.runtime / "worktrees").glob("*"))
            if (self.runtime / "worktrees").exists() else False,
            "Die Arbeitskopie muss entfernt sein")
        self.assertEqual([], self.worktree_registry().all(),
                         "Der Registry-Eintrag muss entfernt sein")

    def test_auto_merge_does_not_merge_when_the_gate_is_red(self):
        """Vorbedingung: Auto-Merge an, aber der Agent liefert keine
        Nachweise (Abschlussschranke rot).
        Aktion: Läufer ausführen.
        Erwartung: kein REST-Merge, kein lokaler Merge, Blockievermerk.
        Fehlerfall: Auto-Merge übergeht die Schranke.
        """
        server = MergeRestFakeServer().start()
        self.addCleanup(server.close)
        project = self.make_github_project(server.base, auto_merge="1")
        self.prepare_origin(project)

        result = self.run_runner(project, FAKE_MODE="no-artifacts")

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        self.assertEqual([], server.puts(),
                         "Auto-Merge darf eine rote Schranke nicht übergehen")
        self.assertNotEqual(
            0, real_git_ap4(project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode)


# ===========================================================================
# Abnahme „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FAKE_TOKEN_b16 = "b16-closure-env-token-4711"


def github_module_b16():
    """Lädt ``bin/vibe_github.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "gh" in _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_b16_closure_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def real_git_b16(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def project_env_b16(api="", base="main", enabled=True):
    text = ""
    if enabled:
        text += 'GITHUB_ENABLED="1"\n'
    text += 'GITHUB_REPO="owner/name"\n'
    text += 'GITHUB_BASE="%s"\n' % base
    if api:
        text += 'GITHUB_API="%s"\n' % api
    return text


def push_foreign_commit(root, seed_name):
    """Legt einen unabhängigen Commit auf dem Fernstand ab."""
    work = Path(root) / "seed" / seed_name
    (work / "fremd.txt").write_text("fremd\n", encoding="utf-8")
    real_git_b16(work, "add", "-A")
    real_git_b16(work, "commit", "-q", "-m", "fremd")
    real_git_b16(work, "push", "-q", "origin", "main")


def install_rejecting_hook(bare):
    """pre-receive-Hook, der jede Ref-Erstellung wie GH013 ablehnt."""
    hooks = Path(bare) / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "echo 'GH013: Cannot create ref due to creations being restricted' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)


class B16Case(unittest.TestCase):
    """Isolierte Umgebung: temporäres VIBE_STATE, klare Prozessumgebung."""

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
        self.gh = github_module_b16()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def not_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN_b16, text)

    def configured_project(self, name, server=None, base="main"):
        api = server.base if server else ""
        bare_url = seed_bare(self.base, name + "-origin")
        project = make_project(
            self.base, name,
            env_extra=project_env_b16(api=api, base=base, enabled=True),
            with_origin=bare_url)
        bare = self.base / "origin" / (name + "-origin.git")
        return project, bare

    def local_commit(self, project, name="lokal.txt"):
        (project / name).write_text(name + "\n", encoding="utf-8")
        real_git_b16(project, "add", "-A")
        real_git_b16(project, "commit", "-q", "-m", "lokal")


# ------------------------------------------------------------ integration_state
class IntegrationStateTest(B16Case):
    """AK: Bei divergiertem oder veraltetem dev vor Abschluss abbrechen."""

    def test_detached_head_is_not_ok(self):
        bare_url = seed_bare(self.base, "detached-origin")
        project = make_project(self.base, "detached",
                               env_extra=project_env_b16(), with_origin=bare_url)
        real_git_b16(project, "checkout", "-q", "--detach", "HEAD")

        state = self.gh.integration_state(project)

        self.assertFalse(state["ok"])
        self.assertTrue(str(state["message"]).strip())

    def test_failed_fetch_is_not_ok_and_mentions_credentials(self):
        project = make_project(self.base, "fetch-fehlt",
                               env_extra=project_env_b16())
        real_git_b16(project, "remote", "add", "origin",
                 "file://" + str(self.base / "gibt-es-nicht.git"))

        state = self.gh.integration_state(project)

        self.assertFalse(state["ok"])
        message = str(state["message"])
        self.assertTrue(message.strip())
        self.assertTrue(
            "Token" in message or "Zugangsdaten" in message,
            "Auth-Hinweis erwartet: " + message)
        self.not_disclosed(message)

    def test_first_publication_without_a_remote_branch_is_ok(self):
        bare = self.base / "origin" / "leer.git"
        bare.mkdir(parents=True, exist_ok=True)
        real_git_b16(bare, "init", "-q", "--bare", "-b", "main")
        project = make_project(self.base, "erstveroeffentlichung",
                               env_extra=project_env_b16())
        real_git_b16(project, "remote", "add", "origin", "file://" + str(bare))
        real_git_b16(project, "fetch", "-q", "origin", check=False)

        state = self.gh.integration_state(project)

        self.assertTrue(state["ok"], state["message"])
        self.assertEqual(0, state["ahead"])
        self.assertEqual(0, state["behind"])

    def test_diverged_state_names_the_numbers_and_blocks(self):
        project, _bare = self.configured_project("divergiert")
        self.local_commit(project)
        push_foreign_commit(self.base, "divergiert-origin")

        state = self.gh.integration_state(project)

        self.assertFalse(state["ok"])
        self.assertGreaterEqual(state["ahead"], 1)
        self.assertGreaterEqual(state["behind"], 1)
        message = str(state["message"])
        self.assertIn("divergiert", message)
        self.assertIn(str(state["ahead"]), message)
        self.assertIn(str(state["behind"]), message)
        self.assertTrue(
            message.strip().endswith("kein Abschluss auf veraltetem Stand."),
            message)

    def test_outdated_state_uses_the_word_veraltet_and_blocks(self):
        project, _bare = self.configured_project("veraltet")
        push_foreign_commit(self.base, "veraltet-origin")

        state = self.gh.integration_state(project)

        self.assertFalse(state["ok"])
        self.assertEqual(0, state["ahead"])
        self.assertGreaterEqual(state["behind"], 1)
        message = str(state["message"])
        self.assertIn("veraltet", message)
        self.assertTrue(
            message.strip().endswith("kein Abschluss auf veraltetem Stand."),
            message)

    def test_ahead_only_is_ok(self):
        project, _bare = self.configured_project("voraus")
        self.local_commit(project)

        state = self.gh.integration_state(project)

        self.assertTrue(state["ok"], state["message"])
        self.assertGreaterEqual(state["ahead"], 1)
        self.assertEqual(0, state["behind"])

    def test_never_raises_and_always_returns_the_dict_shape(self):
        project, _bare = self.configured_project("robust")
        real_git_b16(project, "checkout", "-q", "--detach", "HEAD")
        cases = [
            project,
            self.base / "gibt-es-nicht",
            make_project(self.base, "ohne-origin"),
        ]
        for case in cases:
            with self.subTest(path=str(case)):
                try:
                    state = self.gh.integration_state(case)
                except Exception as error:  # noqa: BLE001 - genau das ist der Befund
                    self.fail("integration_state darf niemals werfen: %r"
                              % (error,))
                self.assertEqual(
                    {"ok", "message", "ahead", "behind"}, set(state),
                    "Ergebnisdict-Schlüssel erwartet")
                self.assertIsInstance(state["ok"], bool)
                self.assertIsInstance(state["message"], str)
                self.assertIsInstance(state["ahead"], int)
                self.assertIsInstance(state["behind"], int)


# ------------------------------------------------------------ complete_package
class CompletePackageClosureTest(B16Case):
    """AK: Push-/PR-Fehler und Divergenz blockieren den Abschluss."""

    def test_diverged_state_blocks_before_push_and_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project, bare = self.configured_project("cp-divergiert", server=server)
        self.local_commit(project)
        push_foreign_commit(self.base, "cp-divergiert-origin")
        real_git_b16(project, "branch", "feature/x")

        result = self.gh.complete_package(project, "feature/x", package_id="B16")

        self.assertEqual(4, len(tuple(result)), "4-Tupel erwartet")
        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok, "Divergenz darf nicht als Erfolg gelten")
        self.assertIn("divergiert", str(message))
        self.assertEqual("", extra["pr_url"])
        remote = real_git_b16(bare, "ls-remote", "--heads", "origin",
                          "refs/heads/feature/x", check=False)
        self.assertEqual("", remote.stdout.strip(),
                         "Bei Divergenz darf nicht gepusht werden")
        self.assertEqual([], server.posts,
                         "Bei Divergenz darf kein Merge-Request gestellt werden")
        self.not_disclosed(message)

    def test_outdated_state_blocks_before_push_and_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project, bare = self.configured_project("cp-veraltet", server=server)
        push_foreign_commit(self.base, "cp-veraltet-origin")
        real_git_b16(project, "branch", "feature/x")

        result = self.gh.complete_package(project, "feature/x")

        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok)
        self.assertIn("veraltet", str(message))
        self.assertTrue(
            str(message).strip().endswith(
                "kein Abschluss auf veraltetem Stand."),
            message)
        self.assertEqual("", extra["pr_url"])
        remote = real_git_b16(bare, "ls-remote", "--heads", "origin",
                          "refs/heads/feature/x", check=False)
        self.assertEqual("", remote.stdout.strip())
        self.assertEqual([], server.posts)

    def test_ahead_only_pushes_and_opens_the_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project, bare = self.configured_project("cp-voraus", server=server)
        self.local_commit(project)
        real_git_b16(project, "branch", "feature/x")
        tip = real_git_out(project, "rev-parse", "feature/x")

        result = self.gh.complete_package(project, "feature/x", package_id="B16")

        self.assertEqual(4, len(tuple(result)), "4-Tupel erwartet")
        performed, ok, message, extra = result
        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertEqual("feature/x", extra["branch"])
        self.assertEqual("http://127.0.0.1/pull/42", extra["pr_url"])
        remote_tip = real_git_out(bare, "rev-parse", "refs/heads/feature/x")
        self.assertEqual(tip, remote_tip, "Der Branch muss gepusht werden")
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts, "Es muss ein Merge-Request gestellt werden")
        self.not_disclosed(message)

    def test_rejected_push_blocks_without_a_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project, bare = self.configured_project("cp-gh013", server=server)
        install_rejecting_hook(bare)
        real_git_b16(project, "branch", "feature/x")

        result = self.gh.complete_package(project, "feature/x")

        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok, "Ein abgelehnter Push ist kein Erfolg")
        self.assertIn("GH013", str(message))
        self.assertEqual("", extra["pr_url"])
        self.assertEqual([], server.posts,
                         "Nach abgelehntem Push kein Merge-Request")
        self.not_disclosed(message)

    def test_failed_merge_request_blocks_and_reports_no_pr_url(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        project, _bare = self.configured_project("cp-prfehler", server=server)
        real_git_b16(project, "branch", "feature/x")
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN_b16

        result = self.gh.complete_package(project, "feature/x")

        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok)
        self.assertIn("Merge-Request fehlgeschlagen", str(message))
        self.assertEqual("", extra["pr_url"])
        self.not_disclosed(message)

    def test_never_raises_and_returns_four_elements_with_result_keys(self):
        project = make_project(self.base, "cp-robust")
        real_git_b16(project, "checkout", "-q", "-b", "feature/robust")
        try:
            result = self.gh.complete_package(project, "feature/robust")
        except Exception as error:  # noqa: BLE001 - genau das ist der Befund
            self.fail("complete_package darf niemals werfen: %r" % (error,))
        self.assertEqual(4, len(tuple(result)),
                         "(performed, ok, message, result) erwartet")
        extra = tuple(result)[3]
        self.assertIsInstance(extra, dict)
        self.assertIn("branch", extra)
        self.assertIn("pr_url", extra)


# ------------------------------------------------------------- Skip-Pfade
class CompletePackageSkipTest(B16Case):
    """AK: Ohne GitHub-Verknüpfung bleibt der Abschluss ein bewusster Skip.

    Nutzerbestätigung 19.11.2026: Die Prüfung ist nur verpflichtend, wenn
    GitHub für das Projekt aktiviert ist. Ein rein lokales Projekt ohne
    GitHub braucht nur Commit und lokales Merge.
    """

    def test_disabled_configuration_skips_with_an_empty_pr_url(self):
        bare_url = seed_bare(self.base, "cp-skip-origin")
        project = make_project(self.base, "cp-skip", env_extra="",
                               with_origin=bare_url)
        real_git_b16(project, "checkout", "-q", "-b", "feature/skip")

        performed, ok, message, extra = self.gh.complete_package(
            project, "feature/skip", package_id="B16")

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip())
        self.assertEqual("", extra["pr_url"])

    def test_missing_origin_skips(self):
        project = make_project(self.base, "cp-ohne-origin",
                               env_extra=project_env_b16())
        real_git_b16(project, "checkout", "-q", "-b", "feature/ohne")

        performed, ok, message, extra = self.gh.complete_package(
            project, "feature/ohne")

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip())
        self.assertEqual("", extra["pr_url"])


# ---------------------------------------------------- Subkommando github-complete
class GithubCompleteCliTest(B16Case):
    """AK: Der Abschlussbericht nennt Branch und Merge-Request-URL."""

    def run_packages(self, *argv, github_token=None):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        if github_token is not None:
            env["GITHUB_TOKEN"] = github_token
        env.update(GIT_IDENTITY)
        return subprocess.run(
            [sys.executable, str(PACKAGES), *argv],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=120, check=False,
        )

    def checked_out_project(self, name, server=None, enabled=True):
        api = server.base if server else ""
        bare_url = seed_bare(self.base, name + "-origin")
        project = make_project(
            self.base, name,
            env_extra=project_env_b16(api=api, enabled=enabled),
            with_origin=bare_url)
        real_git_b16(project, "checkout", "-q", "-b", "feature/cli")
        self.local_commit(project, "arbeit.txt")
        return project

    def test_success_prints_the_delivery_line(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.checked_out_project("cli-ok", server=server)

        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/cli", "--id", "B16",
            github_token=FAKE_TOKEN_b16)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "ABGABE: Branch feature/cli, Merge-Request http://127.0.0.1/pull/42",
            result.stdout)
        self.not_disclosed(result.stdout + result.stderr)

    def test_skip_prints_merge_request_keine(self):
        project = self.checked_out_project("cli-skip", enabled=False)

        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/cli")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("ABGABE: Branch feature/cli, Merge-Request keine",
                      result.stdout)

    def test_failure_exits_one_and_still_prints_the_delivery_line(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        project = self.checked_out_project("cli-fehler", server=server)

        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/cli")

        self.assertEqual(1, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("ABGABE: Branch feature/cli, Merge-Request keine",
                      result.stdout)
        self.not_disclosed(result.stdout + result.stderr)


# ===========================================================================
# Abnahme „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
# ===========================================================================

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402


# GH-48: Tickets liegen im Projekt-Speicher; der frühere FEEDBACK.md-Ledger
# existiert nicht mehr.

GITHUB_ENV = (
    'GITHUB_ENABLED="1"\n'
    'GITHUB_REPO="owner/name"\n'
    'GITHUB_BASE="main"\n'
)


class B16WiringFixture(AP9WiringFixture):
    """AP9-Fixture plus GitHub-Verknüpfung und Prüfhelfer für B16."""

    def github_env(self, api=""):
        text = GITHUB_ENV
        if api:
            text += 'GITHUB_API="%s"\n' % api
        return text

    def make_github_project(self, name="proj", api=""):
        return self.make_project(
            env_extra=self.github_env(api), feedback=FEEDBACK_ONE, name=name)

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def blocked_line(self, log):
        """Erste Protokollzeile der GitHub-Abschlussschranke."""
        for line in log.splitlines():
            if line.startswith(
                    "BLOCKIERT: GitHub-Abschluss für F1 fehlgeschlagen "
                    "(Push/Merge-Request):"):
                return line
        return ""

    def assert_not_merged(self, project, pid="F1"):
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-" + pid + ".txt"
                   ).returncode,
            "Das Paket darf nicht lokal gemergt sein")

    def ticket(self, project, pid="F1"):
        """Liest das Ticket aus dem GH-48-Projektspeicher."""
        path = project / ".vibe" / "tickets.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data["tickets"]:
            if record["id"] == pid:
                return record
        self.fail("Ticket %s fehlt im Speicher %s" % (pid, path))

    def assert_ticket_open(self, project, pid="F1"):
        record = self.ticket(project, pid)
        self.assertNotEqual(
            "done", record["state"],
            "Das Ticket muss offen bleiben: %r" % (record,))


# --------------------------------------------------------------- PR-only-Fall
class PrOnlyClosureTest(B16WiringFixture):
    """AK AP4/T-G1: Ohne GITHUB_AUTO_MERGE bleibt es beim PR-only-Abschluss.

    Die frühere B16-Erwartung (sofortiger lokaler Merge, Cleanup und
    „Geschlossen“) gilt nur noch im Auto-Merge-Modus. AP4-Korbat macht
    PR-only zum Standard: Push und Merge-Request sind weiterhin eine harte
    Schranke, aber der Lauf hält nach dem Öffnen des PRs an, die Arbeitskopie
    bleibt registriert und das Ticket bleibt offen.

    Vorbedingung: Projekt mit aktivierter GitHub-Verknüpfung, ein offenes
    Paket F1, ``GITHUB_AUTO_MERGE`` nicht gesetzt.
    Aktion: Läufer einmal ausführen (Repo wird gepusht, Merge-Request
    gestellt).
    Erwartung: ``FEEDBACK.md`` trägt den Wartezustand ``WARTET AUF MERGE``
    und keinen ``BLOCKIERT``-Vermerk mehr. Grund: AP5-Korbat 4b ersetzt den
    bisherigen PR-only-BLOCKIERT-Vermerk ausdrücklich durch den neuen
    Wartezustand (analog zu ``test_ap4_korbat_github.PrOnlyRunnerTest``).
    Fehlerfall: Der Lauf vermerkt weiterhin BLOCKIERT oder gar keinen
    Wartezustand; dann wäre die geforderte Zustandsänderung nicht umgesetzt.
    """

    def test_successful_run_pushes_and_opens_the_pr_then_waits_for_merge(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-ok")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)

        result = self.run_runner(project)

        log = self.log(project)
        # Branch-Regel: feature/<owner>/<id>, nicht vibe/...
        self.assertEqual(
            0, git(bare, "rev-parse", "--verify",
                   "refs/heads/feature/test/f1").returncode,
            "Der Branch wurde nicht unter dem Repository-Namensschema "
            "gepusht:\n" + log)
        posts = [post for post in server.posts
                 if post["path"].startswith("/repos/owner/name/pulls")]
        self.assertTrue(posts, "Der Merge-Request wurde nicht gestellt")
        self.assertEqual("feature/test/f1", posts[-1]["body"].get("head"))
        # PR-only: kein lokaler Merge, kein Cleanup, Ticket bleibt offen.
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        record = self.ticket(project)
        self.assertEqual("waiting-merge", record["state"],
                         "AP5-Korbat 4b: PR-only muss als Wartezustand "
                         "vermerkt sein: %r" % (record,))
        self.assertTrue(record["waiting_note"],
                        "Der Wartezustand braucht eine Notiz: %r" % (record,))
        self.assertFalse(record["blocked_reason"],
                         "PR-only darf nicht als blockiert vermerkt "
                         "werden: %r" % (record,))
        self.assertTrue(self.worktrees(),
                        "Die Arbeitskopie muss bis zum Merge registriert "
                        "bleiben:\n" + log)
        self.assertIn("wartet auf merge", log.lower(),
                      "Der Lauf muss auf den Merge warten:\n" + log)
        self.assertIn("vibe package close", log,
                      "Der nächste Schritt muss genannt sein:\n" + log)


# --------------------------------------------------------------- Fehlerpfade
class BlockedClosureTest(B16WiringFixture):
    """AK: Push-/PR-Fehler blockieren ohne Merge und ohne [x]."""

    def test_rejected_push_blocks_without_merge_or_ticket_update(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-gh013")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)
        install_rejecting_hook(bare)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("GH013", blocked,
                      "Die Push-Ablehnung muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")
        self.assertEqual([], server.posts,
                         "Nach abgelehntem Push kein Merge-Request")

    def test_failed_merge_request_blocks_but_the_push_happened(self):
        server = RestFakeServer(post_status=422).start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-prfehler")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        self.publish(project, bare)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("Merge-Request fehlgeschlagen", blocked,
                      "Der PR-Fehler muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        # Beabsichtigtes Teilergebnis: Der Push ist erfolgt, nur der
        # Merge-Request scheiterte.
        self.assertEqual(
            0, git(bare, "rev-parse", "--verify",
                   "refs/heads/feature/test/f1").returncode,
            "Der Push muss trotz PR-Fehler erfolgt sein")
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")


# ------------------------------------------------------------- Divergenz dev
class DivergenceTest(B16WiringFixture):
    """AK: Bei divergiertem dev vor Abschluss abbrechen und informieren."""

    def test_diverged_integration_branch_blocks_with_divergiert(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        bare = self.empty_bare("b16-divergiert")
        project = self.make_github_project(api=server.base)
        self.link_origin(project, bare)
        # Fernstand zieht um einen Commit voraus; der lokale Stand wird
        # danach um einen eigenen, ungepushten Commit ergänzt → divergiert.
        self.publish(project, bare, ahead_commits=1)
        self.assertEqual(
            0, git(project, "commit", "--allow-empty", "-q", "-m",
                   "lokal").returncode)

        result = self.run_runner(project)

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        # Der Pull bleibt ein HINWEIS (AP9-Semantik für den Pull).
        self.assertIn(
            "HINWEIS: GitHub-Pull des Haupt-Branchs vor F1 fehlgeschlagen",
            log, log)
        blocked = self.blocked_line(log)
        self.assertTrue(blocked, log)
        self.assertIn("divergiert", blocked,
                      "Die Divergenz muss in der BLOCKIERT-Zeile stehen:\n"
                      + log)
        self.assert_not_merged(project)
        self.assert_ticket_open(project)
        report = self.report(project)
        self.assertIn("Blockiert: F1", report)
        self.assertNotIn("Geschlossen: F1", report)
        self.assertTrue(self.worktrees(),
                        "Die blockierte Arbeitskopie muss liegen bleiben")


# ------------------------------------------------- Bericht ohne GitHub-Verknüpfung
class ReportWithoutGithubTest(B16WiringFixture):
    """AK: Rein lokale Projekte schließen mit Commit und Merge.

    Nutzerbestätigung 19.11.2026: Die GitHub-Prüfung ist nur verpflichtend,
    wenn GitHub für das Projekt aktiviert ist. Ein rein lokales Projekt ohne
    GitHub braucht nur einen erfolgreichen Commit und ggf. das lokale Merge
    des Feature-Branchs. Der Skip-Pfad ist damit Soll-Semantik, kein
    Kompromiss.
    """

    def test_report_without_github_names_branch_commit_and_keine(self):
        project = self.make_project(feedback=FEEDBACK_ONE)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn(
            "Merge-Request: keine (GitHub nicht aktiv oder kein origin)",
            report)
        # Der Commit-Anteil der Berichtszeile muss den Projekt-HEAD nennen.
        head_sha = git(project, "rev-parse", "--short", "HEAD").stdout.strip()
        self.assertTrue(head_sha, "Projekt-HEAD nicht ermittelbar")
        self.assertIn(", Commit " + head_sha + ",", report)
        self.assertIn(", Commit " + head_sha + ",", self.log(project))
        self.assertEqual(0, git(project, "cat-file", "-e",
                                "HEAD:impl-F1.txt").returncode)

    def test_github_enabled_but_without_origin_still_closes_locally(self):
        """Ohne origin gibt es nichts zu pushen: bewusster Skip, lokales Merge."""
        project = self.make_project(
            env_extra=self.github_env(), feedback=FEEDBACK_ONE)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = self.report(project)
        self.assertIn("Geschlossen: F1 — Branch feature/test/f1", report)
        self.assertIn(
            "Merge-Request: keine (GitHub nicht aktiv oder kein origin)",
            report)
        self.assertEqual(0, git(project, "cat-file", "-e",
                                "HEAD:impl-F1.txt").returncode)


if __name__ == "__main__":
    unittest.main()
