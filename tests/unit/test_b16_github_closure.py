"""Abnahme B16 „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
(Bug): GitHub-Abschluss ist eine echte Schranke.

Die Testfälle leiten sich aus Arbeitspaket B16 (FEEDBACK.md) und SPEC.md ab,
unabhängig von einer Implementierung. Geprüft wird ``bin/vibe_github.py``:

* ``integration_state(project_path) -> dict``: prüft vor dem Abschluss, ob
  der lokale Integrationsbranch zum Fernstand passt. Liefert immer ein Dict
  ``{"ok", "message", "ahead", "behind"}`` und wirft niemals. Detached HEAD,
  fehlgeschlagener ``git fetch origin`` und ein zurückliegender Stand
  (``behind > 0``) sind nicht ok; bei Divergenz enthält die Meldung
  ``divergiert``, bei reinem Rückstand ``veraltet`` und stets den Schluss
  ``kein Abschluss auf veraltetem Stand.``.
* ``complete_package(project_path, branch, package_id=None, title=None)``:
  liefert ein 4-Tupel ``(performed, ok, message, result)``. ``result`` ist
  ein Dict mit ``branch`` und ``pr_url``. Bei nicht ok geblockter
  Integrationslage wird weder gepusht noch ein Merge-Request gestellt.
  Push- und Merge-Request-Fehler liefern ``(True, False, Meldung, result)``.
  Die Funktion wirft niemals.
* CLI ``github-complete`` druckt zusätzlich immer eine letzte Zeile
  ``ABGABE: Branch <branch>, Merge-Request <pr-url>`` bzw. ``... keine``.

Kein echtes Netz: github.com wird nie berührt. Git läuft in temporären
Verzeichnissen mit fester Test-Identität gegen lokale Bare-Repositories
(``file://``); REST geht nur an einen Fake auf 127.0.0.1. Keine produktiven
Pfade, keine Geheimnisse, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_b16_github_closure -v
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

REPO = Path(__file__).resolve().parents[2]
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
PACKAGES = REPO / "bin" / "vibe_packages.py"

FAKE_TOKEN = "b16-closure-env-token-4711"

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
        "vibe_github_b16_closure_under_test", str(GITHUB_MODULE))
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


def project_env(api="", base="main", enabled=True):
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
    real_git(work, "add", "-A")
    real_git(work, "commit", "-q", "-m", "fremd")
    real_git(work, "push", "-q", "origin", "main")


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
        self.gh = github_module()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def not_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN, text)

    def configured_project(self, name, server=None, base="main"):
        api = server.base if server else ""
        bare_url = seed_bare(self.base, name + "-origin")
        project = make_project(
            self.base, name,
            env_extra=project_env(api=api, base=base, enabled=True),
            with_origin=bare_url)
        bare = self.base / "origin" / (name + "-origin.git")
        return project, bare

    def local_commit(self, project, name="lokal.txt"):
        (project / name).write_text(name + "\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "lokal")


# ------------------------------------------------------------ integration_state
class IntegrationStateTest(B16Case):
    """AK: Bei divergiertem oder veraltetem dev vor Abschluss abbrechen."""

    def test_detached_head_is_not_ok(self):
        bare_url = seed_bare(self.base, "detached-origin")
        project = make_project(self.base, "detached",
                               env_extra=project_env(), with_origin=bare_url)
        real_git(project, "checkout", "-q", "--detach", "HEAD")

        state = self.gh.integration_state(project)

        self.assertFalse(state["ok"])
        self.assertTrue(str(state["message"]).strip())

    def test_failed_fetch_is_not_ok_and_mentions_credentials(self):
        project = make_project(self.base, "fetch-fehlt",
                               env_extra=project_env())
        real_git(project, "remote", "add", "origin",
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
        real_git(bare, "init", "-q", "--bare", "-b", "main")
        project = make_project(self.base, "erstveroeffentlichung",
                               env_extra=project_env())
        real_git(project, "remote", "add", "origin", "file://" + str(bare))
        real_git(project, "fetch", "-q", "origin", check=False)

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
        real_git(project, "checkout", "-q", "--detach", "HEAD")
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
        real_git(project, "branch", "feature/x")

        result = self.gh.complete_package(project, "feature/x", package_id="B16")

        self.assertEqual(4, len(tuple(result)), "4-Tupel erwartet")
        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok, "Divergenz darf nicht als Erfolg gelten")
        self.assertIn("divergiert", str(message))
        self.assertEqual("", extra["pr_url"])
        remote = real_git(bare, "ls-remote", "--heads", "origin",
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
        real_git(project, "branch", "feature/x")

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
        remote = real_git(bare, "ls-remote", "--heads", "origin",
                          "refs/heads/feature/x", check=False)
        self.assertEqual("", remote.stdout.strip())
        self.assertEqual([], server.posts)

    def test_ahead_only_pushes_and_opens_the_merge_request(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project, bare = self.configured_project("cp-voraus", server=server)
        self.local_commit(project)
        real_git(project, "branch", "feature/x")
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
        real_git(project, "branch", "feature/x")

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
        real_git(project, "branch", "feature/x")
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN

        result = self.gh.complete_package(project, "feature/x")

        performed, ok, message, extra = result
        self.assertTrue(performed)
        self.assertFalse(ok)
        self.assertIn("Merge-Request fehlgeschlagen", str(message))
        self.assertEqual("", extra["pr_url"])
        self.not_disclosed(message)

    def test_never_raises_and_returns_four_elements_with_result_keys(self):
        project = make_project(self.base, "cp-robust")
        real_git(project, "checkout", "-q", "-b", "feature/robust")
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
        real_git(project, "checkout", "-q", "-b", "feature/skip")

        performed, ok, message, extra = self.gh.complete_package(
            project, "feature/skip", package_id="B16")

        self.assertFalse(performed)
        self.assertTrue(ok)
        self.assertTrue(str(message).strip())
        self.assertEqual("", extra["pr_url"])

    def test_missing_origin_skips(self):
        project = make_project(self.base, "cp-ohne-origin",
                               env_extra=project_env())
        real_git(project, "checkout", "-q", "-b", "feature/ohne")

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
            env_extra=project_env(api=api, enabled=enabled),
            with_origin=bare_url)
        real_git(project, "checkout", "-q", "-b", "feature/cli")
        self.local_commit(project, "arbeit.txt")
        return project

    def test_success_prints_the_delivery_line(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        project = self.checked_out_project("cli-ok", server=server)

        result = self.run_packages(
            "github-complete", "--project", str(project),
            "--branch", "feature/cli", "--id", "B16",
            github_token=FAKE_TOKEN)

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


if __name__ == "__main__":
    unittest.main()
