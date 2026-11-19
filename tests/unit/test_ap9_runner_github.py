"""Abnahme AP9 „Bereit für Github Teil 3“: Läufer-Unterstützung für Pull und
Merge-Request je Arbeitspaket.

Die Testfälle leiten sich aus Arbeitspaket AP9 (TICKETS.md) und SPEC.md ab,
unabhängig von einer Implementierung:

* ``pull_integration(project_path) -> (performed, ok, message)``: vor jedem
  neuen Arbeitspaket wird der Haupt-Branch aktualisiert. Ohne GitHub-
  Konfiguration (GITHUB_ENABLED) oder ohne origin-Remote wird bewusst
  übersprungen (performed=False, ok=True). Sonst fetch + ff-only Pull des
  aktuellen Integrationsbranches; Fehler liefern (True, False, Meldung),
  werfen aber niemals.
* ``complete_package(project_path, branch, package_id=None) -> (performed,
  ok, message, result)``: nach AP-Abschluss Push des Branches (mit Upstream)
  und Merge-Request auf den Basis-Branch (explizit > GITHUB_BASE >
  origin/HEAD). Nicht konfiguriert/kein origin → Skip; Fehler liefern
  (True, False, Meldung, result), werfen niemals. Seit B16 enthält
  ``result`` die Schlüssel ``branch`` und ``pr_url``.
* Subkommandos des Läufers: ``vibe_packages.py github-pull --project`` und
  ``github-complete --project --branch [--id]`` beenden mit 0 bei Erfolg
  oder Skip und 1 bei Fehlschlag; Meldungen auf stdout/stderr.

Kein echtes Netz: github.com wird nie berührt. Git läuft in temporären
Verzeichnissen mit fester Test-Identität gegen lokale Bare-Repositories
(``file://``); REST geht nur an einen Fake auf 127.0.0.1. Keine produktiven
Pfade, keine Geheimnisse, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_ap9_runner_github -v
"""
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


if __name__ == "__main__":
    unittest.main()
