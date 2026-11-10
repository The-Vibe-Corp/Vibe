"""B7 — GitHub-Authentifizierung über die Oberfläche (Nutzer-Feedback B7).

Akzeptanzkriterien aus dem Arbeitspaket B7 und SPEC.md („Sicherheit und
Datenintegrität"), unabhängig vom Implementierungsdiff abgeleitet:

* Token-Speicher im Zustandsordner (VIBE_STATE, außerhalb des Projekt-Git),
  Modus 0600 best effort; Tokeninhalt erscheint nie in Status-/Fehlermeldungen.
* Git-Aktionen (fetch/pull/push) liefern Zugangsdaten URL-scoped über die
  Git-Credential-Mechanik (``credential.https://github.com.helper``,
  Benutzername ``x-access-token``, Tokeninhalt nur über die Prozessumgebung,
  niemals über argv oder Protokolle). Ohne Token bleibt das Git-Verhalten
  unverändert (GIT_TERMINAL_PROMPT=0, keine Prompts).
* Gespeicherte Zugangsdaten werden ausschließlich an api.github.com bzw.
  den Git-Host github.com übergeben; Umgebungstoken behalten ihr bisheriges
  REST-Lieferverhalten.
* list_issues/create_pull_request ermitteln den Token standardmäßig aus der
  Umgebung ODER der gespeicherten Datei; Fehlschlag ohne Token bleibt
  verständlich ("Kein GitHub-Zugangstoken …").
* Git-Fehlerbilder (could not read Username, terminal prompts disabled,
  kaputtes askpass-Programm, Authentication failed) werden mit klarem
  Handlungshinweis zur Token-Hinterlegung gereinigt.
* Web-API: token.save / token.clear; Status ergänzt auth {set, source} ohne
  Geheimnis.

Kein echtes Netz: github.com wird nie berührt. Lokale Fakes lauschen nur auf
127.0.0.1; git läuft mit deaktivierter Systemkonfiguration; die Testumgebung
nutzt ein temporäres VIBE_STATE ohne produktive Pfade.

Ausführen mit:

    python3 -m unittest discover -s tests/unit -p test_b7_github_auth.py -v
"""
import contextlib
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

REPO = Path(__file__).resolve().parents[2]
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
WEB = REPO / "bin" / "vibe-web.py"

OFFICIAL_API = "https://api.github.com"
FAKE_TOKEN = "b7-unit-fake-token-123"
ENV_TOKEN = "b7-unit-env-token-456"
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

_GH_CACHE = {}

def github_module():
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

def real_git(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität, nie dirigierte Netzaufrufe."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )

def make_project(root, name="proj"):
    """Minimales eigenes Git-Projekt ohne Remote (Status bleibt offline)."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    real_git(project, "init", "-q", "-b", "main", check=False)
    real_git(project, "commit", "--allow-empty", "-q", "-m", "init", check=False)
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

def make_git_stub(calls, remote="https://github.com/owner/name.git",
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
        self.gh = github_module()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def store_token(self, token=FAKE_TOKEN):
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

        self.gh.save_token(FAKE_TOKEN)

        with open(self.token_path(), encoding="utf-8") as handle:
            self.assertEqual(FAKE_TOKEN, handle.read(),
                             "Der Token muss ohne angefügten Zeilenumbruch "
                             "gespeichert werden")
        self.assertEqual(FAKE_TOKEN, self.gh.read_stored_token())

    def test_save_token_rejects_empty_and_control_characters_without_side_effects(self):
        bad_values = ("", "   ", "ab\x00cd", "ab\ncd", "ab\rcd")

        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_token(bad)
        self.assertFalse(self.token_path().exists(),
                         "Ein abgelehnter Token-Speicherversuch darf keine "
                         "Reste hinterlassen")

        self.gh.save_token(FAKE_TOKEN)
        for bad in bad_values:
            with self.subTest(value=repr(bad)):
                with self.assertRaises(ValueError):
                    self.gh.save_token(bad)
        self.assertEqual(FAKE_TOKEN, self.gh.read_stored_token(),
                         "Ungültige Eingaben dürfen den bereits gespeicherten "
                         "Token nicht verändern")

    def test_file_mode_is_0600_best_effort(self):
        probe = self.state / ".chmod-probe"
        probe.write_text("x", encoding="utf-8")
        os.chmod(probe, 0o600)
        chmod_effective = stat.S_IMODE(os.stat(probe).st_mode) == 0o600
        probe.unlink()

        self.gh.save_token(FAKE_TOKEN)
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

        self.gh.save_token(FAKE_TOKEN)
        self.gh.delete_token()
        self.assertEqual("", self.gh.read_stored_token())

    def test_delete_token_removes_file_and_is_tolerant(self):
        self.gh.save_token(FAKE_TOKEN)
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

        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status())
        self.gh.save_token(FAKE_TOKEN)
        self.assertEqual({"set": True, "source": "umgebung"},
                         self.gh.token_status(),
                         "Die Umgebung gewinnt über den gespeicherten Token")
        os.environ.pop("GITHUB_TOKEN", None)
        os.environ["GH_TOKEN"] = ENV_TOKEN
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
        project = make_project(self.base)
        self.gh.save_token(FAKE_TOKEN)

        view = self.gh.status(project)

        self.assertIn("auth", view, "Der Karten-Status muss auth-Info melden")
        self.assertEqual({"set": True, "source": "gespeichert"}, view["auth"])
        self.not_token_disclosed(json.dumps(view, default=str))

        self.gh.delete_token()
        view = self.gh.status(project)
        self.assertEqual({"set": False, "source": ""}, view["auth"])
        self.not_token_disclosed(json.dumps(view, default=str))

    def not_token_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(ENV_TOKEN, text)

# ------------------------------------------------------- Git-Credential-Mechanik
class GitCredentialTest(B7Case):
    """AC2/AC3: Zugangsdaten nur URL-scoped und niemals über argv."""

    def setUp(self):
        super().setUp()
        self.project = self.base / "ghproj"
        self.project.mkdir()

    def record_fetch(self, remote="https://github.com/owner/name.git"):
        calls = []
        stub = make_git_stub(calls, remote=remote)
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
        self.assertNotIn(FAKE_TOKEN, "\n".join(record["argv"]),
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
                any(FAKE_TOKEN in str(v) for v in record["env"].values()),
                "Der gespeicherte Token wird über die Prozessumgebung "
                "eingespeist (env-schluessel=%r)" % sorted(record["env"]))
            self.assertEqual("0", record["env"].get("GIT_TERMINAL_PROMPT", ""),
                             "Der bewährte Prompt-Schutz bleibt bestehen")

    def test_push_with_stored_token_gets_credentials_the_same_way(self):
        self.store_token()
        calls = []
        stub = make_git_stub(calls)
        with mock.patch("subprocess.run", stub):
            ok, message = self.gh.push(self.project)

        self.assertTrue(ok, message)
        network = network_records(calls)
        self.assertTrue(network)
        for record in network:
            self.assert_url_scoped_credentials(record)

    def test_pull_with_env_token_gets_credentials_without_token_in_argv(self):
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        calls = []
        stub = make_git_stub(calls)
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
            self.assertNotIn(ENV_TOKEN, "\n".join(record["argv"]))
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
        stub = make_git_stub(calls, remote=other)
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
            self.assertNotIn(FAKE_TOKEN, "\n".join(record["argv"]))
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
        project = make_project(self.base, "leakproj")
        real_git(project, "remote", "add", "aux",
                 server.base + "/x.git")
        self.store_token()

        ok, message = self.gh.fetch(project)

        self.assertFalse(ok, "Der nicht erreichbare Fernabruf muss scheitern")
        self.assertTrue(server.requests,
                        "Der Test-Aufwand ist ohne Fernkontakt wertlos")
        for request in server.requests:
            blob = json.dumps(request)
            self.assertNotIn(FAKE_TOKEN, blob,
                             "Der Fremd-Host hat Zugangsdaten empfangen: %s"
                             % blob)
        self.assertNotIn(FAKE_TOKEN, message)
        self.assertTrue(GUIDANCE.search(message),
                        "Der authentifizierende Fehler muss mit klarem "
                        "Hinweis gereinigt werden: %s" % message)

# ------------------------------------------------------------------ REST-Ebene
class _RestHandler(BaseHTTPRequestHandler):
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

class RestFakeServer:
    def __init__(self):
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RestHandler)
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
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(ENV_TOKEN, self.captured[-1]["token"],
                         "list_issues muss sich standardmäßig über den "
                         "Umgebungstoken authentifizieren")

    def test_list_issues_resolves_stored_token_for_official_api(self):
        self.store_token()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(FAKE_TOKEN, self.captured[-1]["token"],
                         "Ohne Umgebungstoken wird der gespeicherte Token für "
                         "die offizielle API verwendet")

    def test_env_token_wins_over_stored_token(self):
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        self.store_token()

        with mock.patch.object(self.gh, "_http_json", self.record_http_json()):
            self.gh.list_issues("owner/name")

        self.assertTrue(self.captured)
        self.assertEqual(ENV_TOKEN, self.captured[-1]["token"])

    def test_stored_token_is_never_sent_to_non_official_api(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        self.store_token()

        self.gh.list_issues("owner/name", api=server.base)

        self.assertTrue(server.requests)
        for request in server.requests:
            self.assertNotIn(FAKE_TOKEN, request["authorization"],
                             "Der gespeicherte Token gehört nie zur "
                             "konfigurierbaren API")

    def test_env_token_keeps_rest_delivery_to_configured_api(self):
        server = RestFakeServer().start()
        self.addCleanup(server.close)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN

        self.gh.list_issues("owner/name", api=server.base)

        self.assertTrue(server.requests)
        self.assertEqual("Bearer " + ENV_TOKEN,
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
        self.assertEqual(FAKE_TOKEN, self.captured[-1]["token"])
        self.assertEqual(42, result["number"])

    def test_errors_and_status_never_disclose_token(self):
        self.store_token()

        with self.assertRaises(ValueError) as thrown:
            self.gh.list_issues("owner name!")
        self.assertNotIn(FAKE_TOKEN, str(thrown.exception))

        with self.assertRaises(ValueError) as thrown:
            self.gh.create_pull_request(self.base, "owner/name",
                                        head="feature", base="main")
        # Ohne Projektbasis ein verständlicher Fehler, ohne Tokeninhalt.
        self.assertNotIn(FAKE_TOKEN, str(thrown.exception))

        status = self.gh.token_status()
        self.not_disclosed(json.dumps(status))
        self.assertEqual({"set": True, "source": "gespeichert"}, status)

    def not_disclosed(self, text):
        self.assertNotIn(FAKE_TOKEN, text)
        self.assertNotIn(ENV_TOKEN, text)

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
                stub = make_git_stub(calls, failures=failures)
                with mock.patch("subprocess.run", stub):
                    ok, message = getattr(self.gh, action)(self.project)
                self.assertFalse(ok, "Der feindliche Fernabruf muss scheitern")
                self.assertNotIn(FAKE_TOKEN, message,
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
        project = make_project(cls.root, "pgh")
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
        cls.gh = github_module()

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
        """token_state_path() im Testprozess mit dem VIBE_STATE des Servers."""
        old = os.environ.get("VIBE_STATE")
        os.environ["VIBE_STATE"] = str(self.state)
        try:
            return Path(self.gh.token_state_path())
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
        status, text = self.github_post(
            {"name": "pgh", "action": "token.save", "token": FAKE_TOKEN})
        data = json.loads(text) if text.startswith("{") else {}

        self.assertEqual(200, status, text)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn(FAKE_TOKEN, text,
                         "Die Antwort darf den Tokeninhalt nie enthalten")
        self.assertTrue(self.token_file.exists(),
                        "Der Token wird im Zustandsordner von VIBE_STATE "
                        "gespeichert")
        with open(self.token_file, encoding="utf-8") as handle:
            self.assertEqual(FAKE_TOKEN, handle.read())
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": True, "source": "gespeichert"}, auth,
                         "Die Antwort trägt den auth-Status ohne Geheimnis")

    def test_token_clear_removes_the_stored_token(self):
        self.github_post({"name": "pgh", "action": "token.save", "token": FAKE_TOKEN})
        self.assertTrue(self.token_file.exists())

        status, text = self.github_post({"name": "pgh", "action": "token.clear"})
        data = json.loads(text) if text.startswith("{") else {}

        self.assertEqual(200, status, text)
        self.assertTrue(data.get("ok"), data)
        self.assertFalse(self.token_file.exists(),
                         "token.clear löscht die gespeicherte Datei")
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": False, "source": ""}, auth,
                         "Nach dem Entfernen bleiben keine Reste")

        status, _ = self.github_post({"name": "pgh", "action": "token.clear"})
        self.assertEqual(200, status, "Wiederholtes Entfernen bleibt tolerant")

    def test_unauthorized_github_calls_are_rejected(self):
        for token in ("falsches-token", None):
            with self.subTest(token=token):
                status, text = self.github_post(
                    {"name": "pgh", "action": "token.save", "token": FAKE_TOKEN},
                    token=token)
                self.assertGreaterEqual(status, 400, text)
                self.assertNotIn(FAKE_TOKEN, text)
                self.assertFalse(self.token_file.exists())

    def test_detail_view_reports_auth_state_without_secret(self):
        self.github_post({"name": "pgh", "action": "token.save", "token": FAKE_TOKEN})

        status, text = self.request("GET", "/api/project?name=pgh")
        data = json.loads(text)
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": True, "source": "gespeichert"}, auth, text)
        self.assertNotIn(FAKE_TOKEN, text)

        self.github_post({"name": "pgh", "action": "token.clear"})

        status, text = self.request("GET", "/api/project?name=pgh")
        data = json.loads(text)
        auth = (data.get("github") or {}).get("auth")
        self.assertEqual({"set": False, "source": ""}, auth, text)
        self.assertNotIn(FAKE_TOKEN, text)

if __name__ == "__main__":
    unittest.main()
