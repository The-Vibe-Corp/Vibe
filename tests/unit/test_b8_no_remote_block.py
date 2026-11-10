"""B8 — Projektansicht blockiert nicht bei nicht erreichbarem Git-Remote.

Akzeptanzkriterien aus dem Arbeitspaket B8 (FEEDBACK.md), unabhängig vom
Implementierungsdiff abgeleitet:

* AC1: Die Projektansicht (``/api/project`` bzw.
  ``vibe_services.project_detail``) fragt das Git-Remote nie an:
  ``status()``/``branches()`` laufen mit ``remote=False`` und Ahead/Behind
  kommt ausschließlich aus der lokalen ``origin/<branch>``-Referenz.
* AC2: Ohne aktivierte GitHub-Verknüpfung (kein ``GITHUB_ENABLED``) wird
  generell kein Remote kontaktiert — auch im Normalmodus (remote=True).
* AC3: Reine Fern-Leseabfragen (ls-remote sowie der Fetch zur
  Objektnachziehung im Fern-Lesepfad) sind mit 10 Sekunden begrenzt
  (``TIMEOUT_REMOTE_READ``); bewusste Aktionen ``fetch``/``pull``/``push``
  behalten 120 Sekunden (``TIMEOUT_GIT``).
* AC4: Git läuft ohne Terminal-Prompt (``GIT_TERMINAL_PROMPT=0``,
  ``GCM_INTERACTIVE=never``) — unabhängig vom Token-Vorhandensein.

Kein echtes Netz: Alle Fernadressen lauschen ausschließlich auf 127.0.0.1
(hängender Git-Dienst, 401-Abforderung) oder sind lokale ``file://``-Repos.
Git läuft mit deaktivierter System-/Global-Konfiguration und fester
Test-Identität; produktive Pfade werden nie berührt. Der
``subprocess.run``-Spy ersetzt nichts: echte Prozesse laufen weiter, es
werden nur argv, timeout und env protokolliert.

Ausführen mit:

    python3 -m unittest tests.unit.test_b8_no_remote_block -v
"""
import contextlib
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
BIN = REPO / "bin"
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
SERVICES_MODULE = REPO / "bin" / "vibe_services.py"
WEB = REPO / "bin" / "vibe-web.py"

FAKE_TOKEN_ENV = "b8-short-env-token"
FAKE_TOKEN_STORED = "b8-short-stored-t"

NETWORK_VERBS = ("ls-remote", "fetch", "pull", "push")
REMOTE_BOUND = 40.0  # Die Projektansicht darf nie das 120-s-Git-Limit ausreizen.


ISOLATED_ENV_KEYS = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STATE",
    "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_PROFILE", "VIBE_UI_PORT", "VIBE_UI_BIND", "VIBE_OPENCODE_PORT",
    "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "NO_PROXY",
)

_GH_CACHE = {}


def github_module():
    """Lädt ``bin/vibe_github.py`` als eigenständiges Modul."""
    if _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_b8_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def services_module():
    """Lädt ``bin/vibe_services.py`` mit bin/ im Modulpfad."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    loader = importlib.machinery.SourceFileLoader(
        "vibe_services_b8_under_test", str(SERVICES_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME (V-008-Muster)."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader("vibe_b8_cli_under_test", str(CLI))
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
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität; nie produktive Konfiguration."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )


def commit_file(project, name, content, message):
    (Path(project) / name).write_text(content, encoding="utf-8")
    git(project, "add", name)
    git(project, "commit", "-q", "-m", message)


def git_verb(argv):
    """Erster fachlicher Git-Unterbefehl nach dem festen Präfix."""
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


def subprocess_spy(calls):
    """Protokolliert subprocess.run und führt es unverändert aus."""
    real_run = subprocess.run

    def wrapper(argv, *rest, **kwargs):
        calls.append({
            "argv": [str(a) for a in argv],
            "timeout": kwargs.get("timeout"),
            "env": dict(kwargs.get("env") or {}),
        })
        return real_run(argv, *rest, **kwargs)

    return wrapper


def network_calls(calls):
    return [c for c in calls if git_verb(c["argv"]) in NETWORK_VERBS]


class HangingGitServer:
    """Lokaler Dienst, der Verbindungen annimmt und schweigt.

    ``git ls-remote`` gegen diese Adresse wartet bis zum Zeitlimit — genau
    das Fehlerbild des Bugs (nachfragendes/nicht erreichbares Remote).
    """

    def __init__(self):
        self.connections = []
        self.stopped = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.url = "git://127.0.0.1:%d/blocked/proj.git" % self.port
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.sock.settimeout(0.3)
        while not self.stopped.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            self.connections.append(conn)
            # Bewusst keine Antwort: git wartet so auf Daten.

    @property
    def hit_count(self):
        return len(self.connections)

    def close(self):
        self.stopped.set()
        with contextlib.suppress(OSError):
            self.sock.close()
        self.thread.join(timeout=5)
        for conn in self.connections:
            with contextlib.suppress(OSError):
                conn.close()


class _DenyingAuthHandler(BaseHTTPRequestHandler):
    """Git-HTTP-Gegenstelle, die auf jeden Abruf Authentifizierung verlangt."""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.server.requests.append(self.path)
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="b8-probe"')
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "0")
        self.end_headers()


class DenyingAuthServer:
    """401-Fake für git über http; nur auf 127.0.0.1 erreichbar."""

    def __init__(self):
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _DenyingAuthHandler)
        self.httpd.requests = self.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d/proj.git" % self.httpd.server_address[1]

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class B8Case(unittest.TestCase):
    """Isolierte Umgebung: eigener VIBE-Wurzelordner, keine Zugangsdaten im ENV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ws = self.base / "ws"
        self.ws.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.base / "state"
        self.state.mkdir()
        self.runtime = self.ws / "_logs"
        self.runtime.mkdir()
        self.install = self.base / "install"
        self.install.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_KEYS}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy",
                    "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        os.environ.pop("VIBE_CONFIG_FILE", None)
        os.environ.pop("VIBE_PROFILE", None)
        (self.home / ".config" / "opencode" / "agents").mkdir(parents=True,
                                                              exist_ok=True)
        os.environ.update({
            "VIBE": str(self.ws),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.install),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module()

    def restore_env(self):
        """Stellt die ursprüngliche Umgebung wieder her (keine Reste an Tests)."""
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_project(self, name="proj", github_enabled=False):
        project = self.ws / name
        project.mkdir(parents=True, exist_ok=True)
        git(project, "init", "-q", "-b", "main")
        git(project, "commit", "--allow-empty", "-q", "-m", "init")
        (project / ".vibe").mkdir(exist_ok=True)
        lines = ['TYPE=generic', 'TESTER=test-agent', 'SANDBOX="off"']
        if github_enabled:
            lines.append('GITHUB_ENABLED="1"')
            lines.append('GITHUB_REPO="blocked/proj"')
        (project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        return project

    def set_remote(self, project, url):
        git(project, "remote", "add", "origin", url)

    def make_bare(self, name):
        bare = self.base / name
        bare.mkdir()
        git(bare, "init", "-q", "--bare", "-b", "main")
        return bare


# ---------------------------------------------------------------- AC1: Lokalmodus
class StatusLocalRefsTest(B8Case):
    """AC1: status(remote=False) liest Ahead/Behind nur aus lokalen Referenzen."""

    def test_status_liesst_ahead_behind_nur_aus_lokalen_referenzen(self):
        bare = self.make_bare("upstream.git")
        project = self.make_project(github_enabled=True)
        self.set_remote(project, "file://" + str(bare))
        git(project, "push", "-q", "-u", "origin", "main")
        self.assertTrue(self.gh.status(str(project), remote=False)["unpushed"] is False)

        commit_file(project, "arbeit.txt", "lokal", "B8: lokale Arbeit")
        info = self.gh.status(str(project), remote=False)

        self.assertEqual(info["branch"], "main")
        self.assertEqual((info["ahead"], info["behind"]), (1, 0),
                         "Der unveröffentlichte Commit muss aus der lokalen "
                         "origin/<branch>-Referenz als ahead=1 erkennbar sein")
        self.assertTrue(info["unpushed"])

        # Ein Zweitarbeiter schiebt ferne Arbeit ins Bare-Repo, ohne dass das
        # Projekt sie abruft. Die lokale Referenz kennt ihn nicht: behind
        # bleibt 0 (kein heimlicher Netzabruf in der Ansicht).
        zweit = self.base / "zweit"
        git(self.base, "clone", "-q", "file://" + str(bare), str(zweit))
        commit_file(zweit, "partner.txt", "draußen", "B8: ferne Arbeit")
        git(zweit, "push", "-q", "origin", "main")

        info_after = self.gh.status(str(project), remote=False)

        self.assertEqual((info_after["ahead"], info_after["behind"]), (1, 0),
                         "Es wurde ausschließlich die lokale Referenz gelesen")

    def test_status_remote_false_wartet_nicht_auf_haengendes_remote(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        start = time.monotonic()
        info = self.gh.status(str(project), remote=False)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5.0,
                        "status(remote=False) wartete auf das blockierende "
                        "Remote (%.1fs)" % elapsed)
        self.assertEqual((info["ahead"], info["behind"]), (0, 0),
                         "Ohne lokale Fern-Referenz bleibt der Stand neutral")
        self.assertEqual(0, hanging.hit_count,
                         "Der Fake-Dienst wurde kontaktiert — Netzverbot im "
                         "Lokalmodus verletzt")

    def test_branches_remote_false_bleibt_fernfrei_und_vollstaendig(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            start = time.monotonic()
            rows = self.gh.branches(str(project), remote=False)
            elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5.0, "branches(remote=False) wartete: %.1fs" % elapsed)
        names = [row["name"] for row in rows]
        self.assertIn("main", names)
        self.assertTrue(any(row.get("current") for row in rows))
        for row in rows:
            self.assertIsInstance(row["ahead"], int)
            self.assertIsInstance(row["behind"], int)
        self.assertEqual([], network_calls(calls),
                         "remote=False darf keinen Fernaufruf auslösen: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)


# ------------------------------------------------------ AC1: Projektansicht
class ProjectDetailLocalModeTest(B8Case):
    """AC1: ``vibe_services.project_detail`` fragt das Git-Remote nie an.

    Schlüssel der Aussage: GITHUB_ENABLED ist gesetzt; den Lokalmodus
    bezeugt somit der Aufrufort (remote=False), nicht die Konfiguration.
    """

    def setUp(self):
        super().setUp()
        self.cli = load_cli(self.ws, self.home)
        self.services = services_module()
        self.paths = self.cli.PATHS

    def test_project_detail_fragt_origin_trotz_github_enabled_nicht_an(self):
        bare = self.make_bare("upstream.git")
        project = self.make_project(github_enabled=True)
        self.set_remote(project, "file://" + str(bare))
        git(project, "push", "-q", "-u", "origin", "main")
        commit_file(project, "arbeit.txt", "lokal", "B8: ungesehene Arbeit")

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            data = self.services.project_detail(self.cli, self.paths, "proj")

        self.assertEqual([], network_calls(calls),
                         "Die Projektansicht darf das Git-Remote nie "
                         "ansprechen (ls-remote/fetch/pull/push verboten): %r"
                         % [c["argv"] for c in network_calls(calls)])
        github = data["github"]
        self.assertIn("branches", github)
        branch_names = [row["name"] for row in github["branches"]]
        self.assertIn("main", branch_names)
        for row in github["branches"]:
            self.assertIsInstance(row["ahead"], int)
            self.assertIsInstance(row["behind"], int)
        self.assertTrue(github["unpushed"],
                        "Ahead/Behind muss aus der lokalen Referenz stammen")
        self.assertTrue(github["enabled"])

    def test_project_detail_ohne_git_remote_bewahrt_die_karte(self):
        project = self.make_project(github_enabled=False)
        data = self.services.project_detail(self.cli, self.paths, "proj")

        github = data["github"]
        branch_names = [row["name"] for row in github["branches"]]
        self.assertIn("main", branch_names)
        self.assertFalse(github["enabled"])
        self.assertEqual((github["ahead"], github["behind"]), (0, 0))


# --------------------------------------------- AC1 Ende-an-Ende über das Dashboard
class ApiProjectBlockingTest(unittest.TestCase):
    """AC1 Ende-an-Ende: GET /api/project bleibt bei hängendem origin
    antwortend und beweist an der echten Oberfläche, dass vor dem Fix
    geleerte 120 Sekunden Wartezeit nur mehr Geschichte wären."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.ws = cls.root / "ws"
        cls.ws.mkdir()
        cls.hanging = HangingGitServer()
        project = cls.ws / "proj"
        project.mkdir()
        git(project, "init", "-q", "-b", "main")
        git(project, "commit", "--allow-empty", "-q", "-m", "init")
        git(project, "remote", "add", "origin", cls.hanging.url)
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nTESTER=test-agent\nSANDBOX="off"\n'
            'GITHUB_ENABLED="1"\nGITHUB_REPO="blocked/proj"\n', encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "state").mkdir()
        (cls.root / "install").mkdir()
        (cls.ws / "_logs").mkdir()
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        cls.port = probe.getsockname()[1]
        probe.close()
        env = {k: v for k, v in os.environ.items() if k not in
               ("GITHUB_TOKEN", "GH_TOKEN", "http_proxy", "https_proxy",
                "all_proxy", "VIBE_RUNTIME", "VIBE_AGENTS_DIR", "VIBE_INSTALL",
                "VIBE_CONFIG_FILE", "VIBE_PROFILE")}
        env.update({
            "VIBE": str(cls.ws),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(cls.root / "state"),
            "VIBE_RUNTIME": str(cls.ws / "_logs"),
            "VIBE_AGENTS_DIR": str(cls.root / "home" / ".config" / "opencode"
                                   / "agents"),
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.root / "home"),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.ws / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.hanging.close()
        cls.tmp.cleanup()

    def get(self, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method="GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_api_project_antwortet_ohne_fernkontakt_bei_haengendem_remote(self):
        started = time.monotonic()
        status, body = self.get("/api/project?name=proj")
        elapsed = time.monotonic() - started

        self.assertEqual(200, status, body)
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Projektansicht wartete %.1fs auf das Remote — "
                        "Vor-Fix-Verhalten" % elapsed)
        github = body["github"]
        self.assertIn("branches", github)
        self.assertIsInstance(github["branches"], list)
        self.assertEqual(github["branch"], "main")
        self.assertEqual(0, self.hanging.hit_count,
                         "Das Dashboard versuchte den Ferndienst zu "
                         "erreichen (%d Verbindungen)" % self.hanging.hit_count)


# ---------------------------------------------- AC2: kein Remote ohne GitHub
class NoRemoteWithoutGithubTest(B8Case):
    """AC2: Ohne GITHUB_ENABLED wird generell kein Remote kontaktiert."""

    def test_status_ohne_github_enabled_kontaktiert_nicht_den_ferndienst(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=False)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project))  # remote=True: Normalmodus!

        self.assertEqual([], network_calls(calls),
                         "Auch mit remote=True darf die Status-Ebene ohne "
                         "aktivierte Verknüpfung keinen Fernaufruf machen: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)
        self.assertFalse(info["enabled"])
        self.assertEqual((info["ahead"], info["behind"]), (0, 0))

    def test_branches_ohne_github_enabled_bleibt_fernfrei(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=False)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project))  # remote=True: Normalmodus!

        self.assertEqual([], network_calls(calls),
                         "branches() ohne GITHUB_ENABLED darf nicht "
                         "ls-remote: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)
        self.assertIn("main", [row["name"] for row in rows])


# ------------------------------------------------------------------ AC3: Zeitlimits
class RemoteReadTimeoutTest(B8Case):
    """AC3: Fernleseabfragen laufen beim hängenden Remote auf Timeout."""

    def test_reine_fernleseabfrage_grenzt_auf_10_sekunden(self):
        """Vorbedingung: GitHub aktiviert, origin hängt schweigend;
        Aktion: status(remote=True);
        Erwartung: ls-remote wird unternommen, bricht nach ~10 s ab
        (nicht 120 s), Ahead/Behind fällt auf 0/0 zurück."""
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            started = time.monotonic()
            info = self.gh.status(str(project), remote=True)
            elapsed = time.monotonic() - started

        verbs = [git_verb(c["argv"]) for c in network_calls(calls)]
        self.assertIn("ls-remote", verbs,
                      "Ohne den Fernkontaktversuch trägt der Test nichts bei")
        self.assertGreaterEqual(elapsed, 9.0,
                                "Ein Zeitlimit unter 10 s wäre eine "
                                "unangekündigte Verschärfung (%.1fs)" % elapsed)
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Fernlese wartete auf das 120-s-Git-Limit "
                        "(%.1fs) — Vor-Fix-Verhalten" % elapsed)
        self.assertEqual((info["ahead"], info["behind"]), (0, 0),
                         "Bei Fernausfall bleibt der Stand neutral (keine "
                         "veralteten Referenzen)")

    def test_fetch_pull_push_behalten_120_sekunden_zeitlimit(self):
        project = self.make_project(github_enabled=False)
        self.set_remote(project, "file:///nicht/angelegt/b8-missing")

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            ok_fetch, _ = self.gh.fetch(str(project))
            ok_pull, _ = self.gh.pull(str(project))
            ok_push, _ = self.gh.push(str(project), "main")

        self.assertFalse(ok_fetch)
        self.assertFalse(ok_pull)
        self.assertFalse(ok_push)
        timeouts = {git_verb(c["argv"]): c["timeout"]
                    for c in network_calls(calls)}
        for verb in ("fetch", "pull", "push"):
            self.assertIn(verb, timeouts, "Aktion %s lief gar nicht" % verb)
            self.assertEqual(120, timeouts[verb],
                             "Bewusste Aktion %s muss 120 s behalten, hat %s"
                             % (verb, timeouts[verb]))
        self.assertEqual(10, self.gh.TIMEOUT_REMOTE_READ)
        self.assertEqual(120, self.gh.TIMEOUT_GIT)


# ----------------------------------------------------------------- AC4: Prompt-Freiheit
class PromptFreeGitTest(B8Case):
    """AC4: Git läuft ohne Terminal-Prompt, unabhängig vom Token."""

    def record_status(self, project):
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            started = time.monotonic()
            info = self.gh.status(str(project), remote=True)
            elapsed = time.monotonic() - started
        return calls, info, elapsed

    def assert_prompt_free(self, calls):
        for call in calls:
            env = call["env"]
            self.assertEqual("0", env.get("GIT_TERMINAL_PROMPT"),
                             "GIT_TERMINAL_PROMPT=0 fehlt: argv=%r"
                             % (call["argv"],))
            self.assertEqual("never", env.get("GCM_INTERACTIVE"),
                             "GCM_INTERACTIVE=never fehlt: argv=%r"
                             % (call["argv"],))

    def test_git_aufrufe_sind_stets_ohne_terminal_prompt(self):
        project = self.make_project(github_enabled=True)

        calls, _info, _elapsed = self.record_status(project)

        self.assertTrue(calls)
        self.assert_prompt_free(calls)

    def test_git_aufrufe_bleiben_promptfrei_auch_mit_token(self):
        project = self.make_project(github_enabled=True)
        self.gh.save_token(FAKE_TOKEN_STORED)
        self.addCleanup(lambda: self.gh.delete_token())
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN_ENV

        calls, _info, _elapsed = self.record_status(project)

        self.assertTrue(calls)
        self.assert_prompt_free(calls)
        for call in calls:
            joined = "\n".join(call["argv"])
            self.assertNotIn(FAKE_TOKEN_STORED, joined)
            self.assertNotIn(FAKE_TOKEN_ENV, joined,
                             "Der Tokeninhalt darf nie im argv stehen")

    def test_http_remote_mit_auth_forderung_blockiert_nicht(self):
        """Authentifizierungs-Forderung (401) stoppt die Ansicht nicht."""
        denying = DenyingAuthServer().start()
        self.addCleanup(denying.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, denying.url)

        calls, info, elapsed = self.record_status(project)

        self.assertGreater(len(list(denying.requests)), 0,
                           "Ein Kontaktversuch war für diesen Nachweis nötig")
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Auth-Forderung blockierte die Ansicht (%.1fs)" % elapsed)
        self.assert_prompt_free(network_calls(calls))
        self.assertEqual((info["ahead"], info["behind"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
