"""Abnahme AP9 „Bereit für Github Teil 3“: Projekt-Token, Branch-Kontrolle,
Verbindungsprüfung und CLI.

Die Testfälle leiten sich aus Arbeitspaket AP9 (TICKETS.md) und SPEC.md ab,
unabhängig von einer Implementierung. Geprüfte fachliche Schnittstellen:

* ``save_project_token/read_project_token/delete_project_token``: Token je
  Projekt, verschlüsselt unter ``<VIBE_STATE>/github-tokens/<hash>.json``
  (Datei 0600 best effort, Ordner 0700 best effort, Masterschlüssel
  ``<VIBE_STATE>/github-token.key`` mit 32 zufälligen Bytes). Der Klartext-
  Token steht nie im Dateiinhalt; defekte Einträge liefern ``""`` statt
  Ausnahmen; Löschen ist tolerant.
* ``token_status(project_path)`` und ``token_for_rest(api, project_path)``:
  Umgebung gewinnt, dann Projekt-Token, dann legacy globaler Token; der
  gespeicherte Token geht ausdrücklich nur an die offizielle GitHub-API.
* ``git(project_path, *args)``: Credential-Injection über die Prozessum-
  gebung (GIT_CONFIG_*), niemals Tokeninhalt in argv.
* ``read_config`` meldet zusätzlich ``base`` (GITHUB_BASE, Standard "").
* ``checkout_branch`` und ``push``: Branch-Wechsel mit Validierung und
  Schutzzweigen; Push mit Ziel-Branch (Refspec) und Upstream.
* ``connection(project_path)``: Fern-/REST-Zustand ohne Ausnahme-Durchreich
  und ohne Tokeninhalt in Meldungen.
* CLI ``vibe github <p> checkout|test|push|token|pr`` und
  ``vibe clone <url> [name] --branch``.

Kein echtes Netz: github.com wird nie berührt; alle Git-Vorgänge laufen in
temporären Verzeichnissen gegen lokale Bare-Repositories (``file://``); REST
geht nur an einen Fake auf 127.0.0.1. Keine produktiven Pfade, keine
Geheimnisse, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_ap9_github -v
"""
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

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"

OFFICIAL_API = "https://api.github.com"
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
    env.update(GIT_IDENTITY)
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
        self.gh = github_module()

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
        env.update(GIT_IDENTITY)
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
        gh = github_module()
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
        gh = github_module()
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
        gh = github_module()
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


if __name__ == "__main__":
    unittest.main()
