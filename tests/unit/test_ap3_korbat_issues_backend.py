"""AP3-Korbat (Backbone): GitHub-Issues-Sync unabhaengig vom Implementierungsdiff.

Quellen der Ableitung: Arbeitspaket AP3-Korbat (TICKETS.md), ``SPEC.md``
(Arbeitspakete und Feedback, Sicherheit und Datenintegritaet, Qualitaet und
Abnahme) und die verbindlichen Design-Entscheidungen des Koordinators (1-14).

Abgedeckt sind:

* **Opt-in je Projekt** (Design 1, 2): ``GITHUB_ISSUES_ENABLED`` ist nur bei
  exakt ``"1"`` aktiv; ``read_config``/``status`` liefern ``issues_enabled``,
  ``issues_in_progress_label`` (Standard ``in-progress``) und
  ``issues_assignee`` (Leerwert = alle).
* **Backbone-Modul** (Design 3): ``bin/vibe_issues.py`` existiert, exportiert
  ``sync_issues(project_path, config)`` und greift fuer REST nur ueber
  ``vibe_github`` zu (kein eigenes ``urllib.request``/``http.client``).
* **Pull** (Design 4, 5): offene Issues werden zu ``- [ ] GH-<n> ...`` (PRs
  ignoriert, ``bug`` -> ``Art: Bug``, In-Progress-Label -> ``Status:``);
  bestehende Bloecke werden nicht dupliziert und vom Remote-Stand
  aktualisiert; geschlossene Issues setzen den lokalen Block auf ``[x]`` mit
  Nachweiszeile.
* **Push** (Design 6): offene lokale Pakete ohne GitHub-Bezug werden als
  Issue angelegt, behalten ihre lokale ID und erhalten ``GitHub: #<n>``;
  erledigte Pakete und Feedback werden nicht gepusht; ``Art: Bug`` -> Label
  ``bug``.
* **Assignee-Filter** (Design 1, 4): gesetzt = nur zugewiesene Issues werden
  gepullt und neue Issues diesem Nutzer zugewiesen.
* **Parser** (Design 5): ``ticket_items`` traegt ``status``/``github``
  additiv; die Zustands-Praezedenz bleibt erledigt > BLOCKIERT >
  WARTET AUF MERGE > In-Progress > offen; FEEDBACK-Parsing bleibt intakt.
* **Runner-Abschluss** (Design 8): ``vibe_github.complete_package`` haengt
  ``Closes #<n>`` an den PR-Body, wenn der Ticketblock einen Issue-Bezug hat;
  ohne Bezug bleibt der Body unveraendert.
* **Speicherweg** (Design 13): der Sync benutzt die atomare
  ``vibe_storage``-Schicht und meldet einen Konflikt, statt still zu
  ueberschreiben.

Kein echtes Netz und kein echtes GitHub: REST ausschliesslich gegen einen
``ThreadingHTTPServer`` auf ``127.0.0.1``; Git nur in temporaeren
Verzeichnissen mit fester Test-Identitaet. Keine Modellaufrufe, keine
produktiven Pfade oder Geheimnisse (Token ist ein Fake-String).

Run:

    python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v
"""
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
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
GITHUB_MODULE = BIN / "vibe_github.py"
ISSUES_MODULE = BIN / "vibe_issues.py"
PACKAGES_MODULE = BIN / "vibe_packages.py"
CLI = BIN / "vibe"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

FAKE_TOKEN = "ap3-korbat-fake-token-4711"

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

ENTRY_RE = re.compile(r"^- \[[^\]]*\] ")


# --------------------------------------------------------------- test helpers
def load_module(path, name):
    """Laedt eine Skriptdatei als eigenes Modul (Muster AP4/AP5)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def github_module():
    if "gh" not in _CACHE:
        _CACHE["gh"] = load_module(GITHUB_MODULE, "vibe_github_ap3_backend_under_test")
    return _CACHE["gh"]


def issues_module():
    if not ISSUES_MODULE.exists():
        raise AssertionError(
            "bin/vibe_issues.py fehlt (Backbone-Modul fuer den Issues-Sync)")
    if "issues" not in _CACHE:
        _CACHE["issues"] = load_module(
            ISSUES_MODULE, "vibe_issues_ap3_backend_under_test")
    return _CACHE["issues"]


def packages_module():
    if "packages" not in _CACHE:
        _CACHE["packages"] = load_module(
            PACKAGES_MODULE, "vibe_packages_ap3_backend_under_test")
    return _CACHE["packages"]


def cli_parser_module():
    """Laedt ``bin/vibe`` isoliert fuer Parserpruefungen (Review-Runde 1)."""
    if "cli_parser" not in _CACHE:
        tmp = tempfile.TemporaryDirectory(prefix="ap3-cli-parser-")
        root = Path(tmp.name)
        (root / "vibe").mkdir()
        (root / "home").mkdir()
        saved = {key: os.environ.get(key)
                 for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
        os.environ.update({
            "VIBE": str(root / "vibe"),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(root / "home"),
        })
        try:
            _CACHE["cli_parser_tmp"] = tmp
            _CACHE["cli_parser"] = load_module(
                CLI, "vibe_ap3_injection_parser_under_test")
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    return _CACHE["cli_parser"]


_CACHE = {}


def issue(number, title, labels=(), assignees=(), state="open", body=""):
    """GitHub-Issue im REST-Format des Fakes."""
    return {
        "number": number, "title": title, "body": body, "state": state,
        "labels": [{"name": name} for name in labels],
        "assignees": [{"login": name} for name in assignees],
    }


def entry_block(text, ident):
    """Textblock eines TICKETS.md-Eintrags (``- [ ] <id> ...`` bis zum naechsten)."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if ENTRY_RE.match(line) and line[6:].split(" ", 1)[0] == ident:
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if ENTRY_RE.match(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


def stats_dict(result):
    """Findet die Statistik ``created/updated/closed/pushed`` im Ergebnis."""
    keys = ("created", "updated", "closed", "pushed")
    if isinstance(result, dict):
        if all(key in result for key in keys):
            return result
        for value in result.values():
            if isinstance(value, dict):
                try:
                    return stats_dict(value)
                except AssertionError:
                    continue
    if isinstance(result, (tuple, list)):
        for value in result:
            if isinstance(value, dict):
                try:
                    return stats_dict(value)
                except AssertionError:
                    continue
    raise AssertionError(
        "Sync-Ergebnis enthaelt keine Statistik created/updated/closed/pushed: "
        + repr(result))


def stat_count(value):
    if isinstance(value, int):
        return value
    try:
        return len(value)
    except TypeError:
        return value


def real_git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60)


def seed_bare(root, name):
    """Bare-Origin mit einem Ausgangscommit; liefert (url, seed-pfad)."""
    work = Path(root) / "seed" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "shared.txt").write_text("base\n", encoding="utf-8")
    real_git(work, "init", "-q", "-b", "main")
    real_git(work, "add", "-A")
    real_git(work, "commit", "-q", "-m", "seed")
    bare = Path(root) / "origin" / (name + ".git")
    bare.mkdir(parents=True, exist_ok=True)
    real_git(bare, "init", "-q", "--bare")
    real_git(work, "remote", "add", "origin", str(bare))
    real_git(work, "push", "-q", "origin", "main")
    real_git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare), work


def clone_project(root, name, url):
    project = Path(root) / name
    real_git(root, "clone", "-q", url, str(project))
    return project


# ------------------------------------------------------------- loopback fake
DEFAULT_ISSUES = [
    {
        "number": 101, "title": "Remote open", "body": "Open body",
        "state": "open", "labels": [{"name": "bug"}],
        "assignees": [{"login": "alice"}],
    },
    {
        "number": 102, "title": "Remote progress", "body": "Progress body",
        "state": "open", "labels": [{"name": "in-progress"}],
        "assignees": [{"login": "bob"}],
    },
    {
        "number": 103, "title": "Remote closed", "body": "Closed body",
        "state": "closed", "labels": [],
        "assignees": [{"login": "alice"}],
    },
    {
        "number": 104, "title": "Remote pull request", "body": "PR only",
        "state": "open", "labels": [],
        "assignees": [],
        "pull_request": {"url": "https://example.invalid/pull/104"},
    },
]


class _IssuesHandler(BaseHTTPRequestHandler):
    """REST-Fake: Issue-Liste, Anlegen, PATCH und Merge-Request-Anlage."""

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

    def _number(self):
        return int(urllib.parse.urlparse(self.path).path.rsplit("/", 1)[1])

    def do_GET(self):
        self._record()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)
        if path.endswith("/issues"):
            items = list(self.server.issues)
            if query.get("state", [""])[0] == "open":
                items = [item for item in items if item.get("state") != "closed"]
            assignee = query.get("assignee", [""])[0]
            if assignee:
                items = [item for item in items if any(
                    entry.get("login") == assignee
                    for entry in item.get("assignees", []))]
            self._respond(200, items)
            return
        if "/issues/" in path:
            number = self._number()
            for item in self.server.issues:
                if item.get("number") == number:
                    self._respond(200, item)
                    return
            self._respond(404, {"message": "Not Found"})
            return
        if path.endswith("/pulls"):
            self._respond(200, [])
            return
        self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if path.endswith("/issues"):
            if self.server.fail_create:
                self._respond(500, {"message": "simulierter GitHub-Fehler"})
                return
            self.server.next_number += 1
            number = self.server.next_number
            item = {
                "number": number,
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "state": "open",
                "labels": [{"name": name} for name in payload.get("labels") or []],
                "assignees": [{"login": name} for name in payload.get("assignees") or []],
            }
            self.server.issues.append(item)
            self._respond(201, item)
            return
        if path.endswith("/pulls"):
            self._respond(201, {"number": 42, "state": "open",
                                "html_url": self.server.base + "/pull/42"})
            return
        self._respond(404, {"message": "Not Found"})

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if "/issues/" in path:
            number = self._number()
            for item in self.server.issues:
                if item.get("number") != number:
                    continue
                if "state" in payload:
                    item["state"] = payload["state"]
                if "labels" in payload:
                    item["labels"] = [{"name": name}
                                      for name in payload.get("labels") or []]
                if "assignees" in payload:
                    item["assignees"] = [{"login": name}
                                         for name in payload.get("assignees") or []]
                self._respond(200, item)
                return
        self._respond(404, {"message": "Not Found"})


class FakeIssuesServer:
    """Loopback-REST-Fake fuer GitHub-Issues und Merge-Requests."""

    def __init__(self, issues=None, next_number=200, fail_create=False):
        self.requests = []
        self.issues = [dict(item) for item in (issues if issues is not None
                                              else DEFAULT_ISSUES)]
        self.next_number = next_number
        self.fail_create = fail_create
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _IssuesHandler)
        self.httpd.requests = self.requests
        self.httpd.issues = self.issues
        self.httpd.next_number = self.next_number
        self.httpd.fail_create = self.fail_create
        self.httpd.base = self.base
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
        return [item for item in self.requests if item["method"] == method]

    def by_path(self, method, suffix):
        return [item for item in self.calls(method)
                if urllib.parse.urlparse(item["path"]).path.rstrip("/")
                .endswith(suffix)]


class GithubCase(unittest.TestCase):
    """Isolierte Umgebung; kein echtes Netz, kein produktives HOME/VIBE."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy", "https_proxy",
                    "all_proxy", "VIBE_GITHUB_CREDENTIAL"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE": str(self.base / "vibe"),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_STATE": str(self.state),
            "GITHUB_TOKEN": FAKE_TOKEN,
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

    def make_project(self, name="proj", tickets="", feedback="", env_text=None,
                     git=False):
        project = self.base / name
        (project / ".vibe").mkdir(parents=True, exist_ok=True)
        if env_text is None:
            env_text = 'TYPE=generic\nGITHUB_ENABLED="1"\n'
        (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n\n" + tickets,
                                            encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n\n" + feedback,
                                             encoding="utf-8")
        if git:
            real_git(project, "init", "-q", "-b", "main")
            real_git(project, "commit", "--allow-empty", "-q", "-m", "init")
        return project

    def issues_env(self, server, **overrides):
        values = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": server.base,
            "GITHUB_ISSUES_ENABLED": "1",
        }
        values.update(overrides)
        return "".join('%s="%s"\n' % (key, value)
                       for key, value in values.items())

    def tickets(self, project):
        return (project / "TICKETS.md").read_text(encoding="utf-8")


# ------------------------------------------------------ Design 1/2: opt-in
class IssuesConfigTest(GithubCase):
    """AK Design 1/2: Issues-Sync ist ein binaeres Opt-in mit Defaults."""

    def write_env(self, text):
        path = self.base / "project.env"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_issues_keys_default_off_and_in_progress(self):
        """Vorbedingung: project.env ohne Issues-Schluessel.
        Aktion: ``vibe_github.read_config`` lesen.
        Erwartung: ``issues_enabled`` False, Label ``in-progress``,
        ``issues_assignee`` leer, Ready-Label ``ready``.
        Fehlerfall: fehlende Schluessel, Wahrwert oder abweichender Default.
        """
        path = self.write_env('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n')

        config = self.gh.read_config(str(path))

        self.assertIn("issues_enabled", config, config)
        self.assertIs(config["issues_enabled"], False, config)
        self.assertEqual("in-progress", config.get("issues_in_progress_label"),
                         config)
        self.assertEqual("", config.get("issues_assignee"), config)
        self.assertEqual("ready", config.get("issues_ready_label"), config)

    def test_ready_label_default_and_override(self):
        """Vorbedingung: ``GITHUB_ISSUES_READY`` fehlt bzw. ist gesetzt.
        Aktion: ``read_config`` je Variante lesen.
        Erwartung: fehlend -> ``ready``; gesetzt -> eigener Wert.
        Fehlerfall: Default fehlt oder der Wert wird ignoriert.
        """
        for line, expected in (("", "ready"),
                               ('GITHUB_ISSUES_READY="freigegeben"',
                                "freigegeben")):
            with self.subTest(expected=expected):
                path = self.write_env(
                    'GITHUB_ENABLED="1"\nGITHUB_ISSUES_ENABLED="1"\n'
                    + line + "\n")
                config = self.gh.read_config(str(path))
                self.assertEqual(expected, config.get("issues_ready_label"),
                                 config)

    def test_only_exact_one_enables_the_issue_sync(self):
        """Vorbedingung: ``GITHUB_ISSUES_ENABLED`` leer, ``true``, ``on``, ``1``.
        Aktion: je Wert ``read_config`` lesen.
        Erwartung: nur exakt ``"1"`` aktiviert; alles andere bleibt aus.
        Fehlerfall: ``true``/``on`` aktivieren den Sync oder ``1`` nicht.
        """
        for value, expected in (("", False), ("true", False), ("on", False),
                                ("yes", False), ("1", True)):
            with self.subTest(value=value):
                path = self.write_env(
                    'GITHUB_ENABLED="1"\nGITHUB_ISSUES_ENABLED="%s"\n' % value)
                config = self.gh.read_config(str(path))
                self.assertIs(config["issues_enabled"], expected, config)

    def test_status_exposes_the_issues_settings(self):
        """Vorbedingung: Projekt mit aktivem Issues-Sync, eigenem Label und
        Assignee.
        Aktion: ``vibe_github.status(project, remote=False)`` lesen.
        Erwartung: ``issues_enabled``/``issues_in_progress_label``/
        ``issues_assignee`` entsprechen der Konfiguration.
        Fehlerfall: Status verschweigt die Werte oder liefert Strings.
        """
        project = self.make_project(
            env_text=('TYPE=generic\nGITHUB_ENABLED="1"\n'
                      'GITHUB_ISSUES_ENABLED="1"\n'
                      'GITHUB_ISSUES_IN_PROGRESS="triaged"\n'
                      'GITHUB_ISSUES_READY="freigegeben"\n'
                      'GITHUB_ISSUES_ASSIGNEE="alice"\n'))

        view = self.gh.status(project, remote=False)

        self.assertIn("issues_enabled", view, view)
        self.assertIs(view["issues_enabled"], True, view)
        self.assertEqual("triaged", view.get("issues_in_progress_label"), view)
        self.assertEqual("freigegeben", view.get("issues_ready_label"), view)
        self.assertEqual("alice", view.get("issues_assignee"), view)


# -------------------------------------------------- Design 3/4/5/6/13: sync
class IssuesSyncTest(GithubCase):
    """AK Design 3-6/13: Pull, Push, Close und Konfliktschutz."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    def test_backbone_module_uses_vibe_github_for_rest(self):
        """Vorbedingung: ``bin/vibe_issues.py`` ist das neue Backbone-Modul.
        Aktion: Modul laden, Quelltext pruefen.
        Erwartung: ``sync_issues`` ist aufrufbar; REST laeuft ueber
        ``vibe_github`` (kein eigenes ``urllib.request``/``http.client``).
        Fehlerfall: Modul fehlt, Funktion fehlt oder REST wird dupliziert.
        """
        module = issues_module()

        self.assertTrue(callable(getattr(module, "sync_issues", None)),
                        "sync_issues fehlt")
        source = ISSUES_MODULE.read_text(encoding="utf-8")
        self.assertIn("vibe_github", source)
        self.assertNotIn("urllib.request.urlopen", source)
        self.assertNotIn("http.client", source)

    def test_sync_ignores_the_legacy_github_label_filter(self):
        """Vorbedingung: ``GITHUB_LABEL="vibe"``, aber die Remote-Issues
        tragen dieses Label nicht.
        Aktion: ``sync_issues``.
        Erwartung: Der Sync fuehrt trotzdem alle Issues (GH-101/GH-102); nur
        die bestehenden Aktionen ``issues``/``issues-import`` bleiben am
        Label.
        Fehlerfall: Der Sync wendet den Legacy-Label-Filter an und verliert
        Issues.
        """
        project = self.make_project(
            env_text=self.issues_env(self.server, GITHUB_LABEL="vibe"),
            tickets="")

        issues_module().sync_issues(str(project), self.config_for(project))

        text = self.tickets(project)
        self.assertIn("GH-101", text)
        self.assertIn("GH-102", text)

    def test_pull_creates_blocks_and_skips_pull_requests(self):
        """Vorbedingung: TICKETS.md ohne Bloecke; Remote hat drei Issues
        (offen, offen mit In-Progress-Label, geschlossen) und einen PR.
        Aktion: ``sync_issues(project, config)``.
        Erwartung: GH-101 offen mit Beschreibung, ``GitHub: #101`` und
        ``Art: Bug``; GH-102 mit ``Status: in-progress``; der PR (GH-104)
        erscheint nicht; die Liste wird mit ``state=all`` gelesen.
        Fehlerfall: PR wird Ticket, Label/Status fehlt, falscher Issue-Zustand.
        """
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets="")
        # Geschlossene Issues werden nur ueber vorhandene Bloecke uebernommen;
        # fuer die Anlage-Statistik bleibt hier der Remote-Stand offen.
        self.server.httpd.issues[:] = [
            item for item in self.server.httpd.issues
            if item.get("state") != "closed"]

        stats = stats_dict(issues_module().sync_issues(
            str(project), self.config_for(project)))

        text = self.tickets(project)
        first = entry_block(text, "GH-101")
        self.assertTrue(first.startswith("- [ ] GH-101 Remote open"), text)
        self.assertIn("Open body", first)
        self.assertIn("GitHub: #101", first)
        self.assertIn("Art: Bug", first)
        second = entry_block(text, "GH-102")
        self.assertTrue(second.startswith("- [ ] GH-102 Remote progress"), text)
        self.assertIn("Status: in-progress", second)
        self.assertNotIn("GH-104", text)
        gets = self.server.calls("GET")
        self.assertTrue(any("state=all" in call["path"] for call in gets),
                        gets)
        self.assertEqual(2, stat_count(stats["created"]), stats)

    def test_pull_does_not_duplicate_and_updates_open_blocks(self):
        """Vorbedingung: lokale Bloecke fuer GH-101 (veralteter Titel) und ein
        lokales Paket AP7 mit ``GitHub: #102``; Remote liefert neue Titel und
        fuer #102 das In-Progress-Label.
        Aktion: ``sync_issues`` zweimal.
        Erwartung: genau ein GH-101/GitHub-#101-Block, Titel wird vom Remote
        aktualisiert; AP7 bleibt als ID erhalten, wird nicht durch GH-102
        dupliziert und erhaelt ``Status: in-progress``. Ein zweiter Lauf
        erzeugt keine weiteren Bloecke.
        Fehlerfall: Duplikate, Umbenennung lokaler IDs oder fehlende
        Zustandsuebernahme.
        """
        tickets = (
            "- [ ] GH-101 Old title\n"
            "  Beschreibung: old\n"
            "  GitHub: #101\n\n"
            "- [ ] AP7 Local title\n"
            "  Beschreibung: local\n"
            "  GitHub: #102\n"
        )
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets=tickets)
        module = issues_module()

        module.sync_issues(str(project), self.config_for(project))
        text = self.tickets(project)

        self.assertEqual(1, text.count("GH-101"), text)
        self.assertIn("Remote open", text)
        self.assertNotIn("Old title", text)
        self.assertEqual(1, text.count("GitHub: #101"), text)
        self.assertRegex(entry_block(text, "AP7"), r"^- \[ \] AP7 \S")
        self.assertNotIn("GH-102", text)
        self.assertEqual(1, text.count("GitHub: #102"), text)
        self.assertIn("Status: in-progress", entry_block(text, "AP7"))

        module.sync_issues(str(project), self.config_for(project))
        again = self.tickets(project)
        self.assertEqual(1, again.count("GH-101"), again)
        self.assertEqual(1, again.count("GitHub: #102"), again)

    def test_closed_issue_marks_the_local_block_done(self):
        """Vorbedingung: lokaler offener Block GH-103; das Issue ist auf
        GitHub geschlossen.
        Aktion: ``sync_issues``.
        Erwartung: Block wird ``[x]`` und traegt eine Nachweiszeile, die
        Issue #103 und „geschlossen“ nennt; Statistik zaehlt ``closed``.
        Fehlerfall: Block bleibt offen, Nachweis fehlt oder falsche Nummer.
        """
        tickets = ("- [ ] GH-103 Remote closed\n"
                   "  Beschreibung: alt\n"
                   "  GitHub: #103\n")
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets=tickets)

        stats = stats_dict(issues_module().sync_issues(
            str(project), self.config_for(project)))

        block = entry_block(self.tickets(project), "GH-103")
        self.assertTrue(block.startswith("- [x] GH-103"), block)
        self.assertIn("#103", block)
        self.assertIn("geschlossen", block.lower())
        self.assertEqual(1, stat_count(stats["closed"]), stats)

    def test_pull_state_is_authoritative_and_descriptions_stay_local(self):
        """Vorbedingung: lokale Bloecke fuer GH-101 (draft), GH-102
        (in-progress), GH-105 (ready), GH-103 (offen) mit lokalen
        Beschreibungen; Remote traegt abweichende Zustaende und Titel, dazu
        ein neues Ready-Issue GH-106.
        Aktion: ``sync_issues``.
        Erwartung: GitHub ist zustandsautoritativ: GH-101 ``Status: draft``,
        GH-102 ``Status: in-progress``, GH-105 ohne Statuszeile, GH-103
        ``[x]``; Titel werden aktualisiert, lokale Beschreibungen bleiben
        erhalten; GH-106 wird mit Remote-Body neu angelegt.
        Fehlerfall: alter lokaler Zustand bleibt, Titel veraltet oder lokale
        Beschreibung wird ueberschrieben.
        """
        self.server.httpd.issues[:] = [
            issue(101, "Remote draft", labels=["bug"], body="Remote body 101"),
            issue(102, "Remote progress", labels=["ready", "in-progress"],
                  body="Remote body 102"),
            issue(105, "Remote ready", labels=["ready"],
                  body="Remote body 105"),
            issue(103, "Remote closed", state="closed", body="Remote body 103"),
            issue(106, "Fresh ready", labels=["ready"], body="Fresh body 106"),
        ]
        tickets = (
            "- [ ] GH-101 Alt draft\n"
            "  Beschreibung: lokal 101\n"
            "  GitHub: #101\n\n"
            "- [ ] GH-102 Alt progress\n"
            "  Beschreibung: lokal 102\n"
            "  Status: draft\n"
            "  GitHub: #102\n\n"
            "- [ ] GH-105 Alt ready\n"
            "  Beschreibung: lokal 105\n"
            "  Status: in-progress\n"
            "  GitHub: #105\n\n"
            "- [ ] GH-103 Alt closed\n"
            "  Beschreibung: lokal 103\n"
            "  GitHub: #103\n"
        )
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets=tickets)

        issues_module().sync_issues(str(project), self.config_for(project))

        text = self.tickets(project)
        self.assertIn("Remote draft", entry_block(text, "GH-101"))
        self.assertIn("lokal 101", entry_block(text, "GH-101"))
        self.assertIn("Status: draft", entry_block(text, "GH-101"))
        self.assertIn("Remote progress", entry_block(text, "GH-102"))
        self.assertIn("Status: in-progress", entry_block(text, "GH-102"))
        self.assertIn("Remote ready", entry_block(text, "GH-105"))
        self.assertIn("lokal 105", entry_block(text, "GH-105"))
        self.assertNotRegex(entry_block(text, "GH-105"),
                            r"(?m)^\s+Status:")
        self.assertTrue(entry_block(text, "GH-103").startswith(
            "- [x] GH-103"), text)
        self.assertIn("geschlossen", entry_block(text, "GH-103").lower())
        self.assertIn("Fresh body 106", entry_block(text, "GH-106"))

    def test_previously_open_issue_without_ready_label_becomes_draft(self):
        """Vorbedingung: lokal offener Block GH-101 ohne Statuszeile; Remote
        offen ohne Ready-Label (bisheriges Verhalten).
        Aktion: ``sync_issues``.
        Erwartung: Der Block wird als Draft markiert (``Status: draft``);
        Freigabe erfordert danach eine ausdrueckliche Handlung.
        Fehlerfall: Der Block bleibt still arbeitbar.
        """
        project = self.make_project(
            env_text=self.issues_env(self.server),
            tickets=("- [ ] GH-101 Alt\n  Beschreibung: lokal\n"
                     "  GitHub: #101\n"))

        issues_module().sync_issues(str(project), self.config_for(project))

        self.assertIn("Status: draft", entry_block(self.tickets(project),
                                                   "GH-101"))

    def test_push_creates_issues_for_open_local_packages_only(self):
        """Vorbedingung: offenes AP1, offener Bug AP2 (``Art: Bug``),
        erledigtes AP3.
        Aktion: ``sync_issues``.
        Erwartung: Zwei POSTs (AP1, AP2), AP2 mit Label ``bug``; AP3 wird
        nicht gepusht; AP1/AP2 behalten ihre lokale ID und erhalten
        ``GitHub: #<n>``; Feedback wird nicht gepusht.
        Fehlerfall: erledigte Pakete/Feedback werden gepusht, IDs umbenannt
        oder die Verweiszeile fehlt.
        """
        tickets = (
            "- [ ] AP1 Local task\n"
            "  Beschreibung: Do it\n\n"
            "- [ ] AP2 Local bug\n"
            "  Art: Bug\n"
            "  Beschreibung: Broken\n\n"
            "- [x] AP3 Done\n"
            "  Beschreibung: done\n"
            "  Commit: abc1234; Test: test_ap3\n"
        )
        feedback = "- [ ] F1 Feedback\n  Beschreibung: nur lokal\n"
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets=tickets,
            feedback=feedback)

        stats = stats_dict(issues_module().sync_issues(
            str(project), self.config_for(project)))

        posts = self.server.by_path("POST", "/issues")
        titles = {post["body"].get("title") for post in posts}
        self.assertEqual({"Local task", "Local bug"}, titles, posts)
        bug_post = next(post for post in posts
                        if post["body"].get("title") == "Local bug")
        self.assertIn("bug", bug_post["body"].get("labels") or [], bug_post)
        text = self.tickets(project)
        self.assertIn("- [ ] AP1 Local task", text)
        self.assertIn("- [ ] AP2 Local bug", text)
        self.assertRegex(entry_block(text, "AP1"), r"GitHub: #\d+")
        self.assertRegex(entry_block(text, "AP2"), r"GitHub: #\d+")
        self.assertNotRegex(entry_block(text, "AP3"), r"GitHub: #\d+")
        self.assertEqual(2, stat_count(stats["pushed"]), stats)

    def test_push_preserves_draft_and_ready_state(self):
        """Vorbedingung: offenes AP1 ohne Statuszeile, offenes AP2 mit
        ``Status: draft``.
        Aktion: ``sync_issues``.
        Erwartung: AP1 wird als Issue MIT Ready-Label angelegt, AP2 OHNE
        Ready-Label (Entwurf); die lokalen IDs bleiben.
        Fehlerfall: Entwuerfe werden arbeitbar gepusht oder Arbeitstickets als
        Entwurf angelegt.
        """
        tickets = (
            "- [ ] AP1 Ready lokal\n"
            "  Beschreibung: arbeitbar\n\n"
            "- [ ] AP2 Draft lokal\n"
            "  Status: draft\n"
            "  Beschreibung: entwurf\n"
        )
        project = self.make_project(
            env_text=self.issues_env(self.server), tickets=tickets)

        issues_module().sync_issues(str(project), self.config_for(project))

        posts = self.server.by_path("POST", "/issues")
        by_title = {post["body"].get("title"): post["body"] for post in posts}
        self.assertIn("ready", by_title["Ready lokal"].get("labels") or [],
                      by_title)
        self.assertNotIn("ready", by_title["Draft lokal"].get("labels") or [],
                         by_title)
        text = self.tickets(project)
        self.assertIn("- [ ] AP1 Ready lokal", text)
        self.assertIn("- [ ] AP2 Draft lokal", text)
        self.assertIn("Status: draft", entry_block(text, "AP2"))

    def test_assignee_filter_limits_pull_and_assigns_new_issues(self):
        """Vorbedingung: ``GITHUB_ISSUES_ASSIGNEE="alice"``; Remote-Issue 101
        ist Alice zugewiesen, 102 Bob; lokal wartet ein offenes AP1.
        Aktion: ``sync_issues``.
        Erwartung: Nur GH-101 wird gepullt; das neue Issue fuer AP1 wird Alice
        zugewiesen.
        Fehlerfall: fremde Issues landen lokal oder neue Issues ohne Assignee.
        """
        project = self.make_project(
            env_text=self.issues_env(self.server, GITHUB_ISSUES_ASSIGNEE="alice"),
            tickets="- [ ] AP1 Local task\n  Beschreibung: Do it\n")

        issues_module().sync_issues(str(project), self.config_for(project))

        text = self.tickets(project)
        self.assertIn("GH-101", text)
        self.assertNotIn("GH-102", text)
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(1, len(posts), posts)
        self.assertEqual(["alice"], posts[0]["body"].get("assignees"), posts)

    def test_assignee_and_draft_compose_for_work_selection(self):
        """Vorbedingung: Assignee ``alice``; Remote: GH-101 ready/bob,
        GH-102 ready/alice, GH-103 draft/alice, GH-104 draft/bob;
        ``PACKAGE_ORDER="GH-103 GH-102"``.
        Aktion: ``sync_issues``, danach ``select_package``.
        Erwartung: Nur zugewiesene Issues landen lokal; GH-102 ist ohne
        Statuszeile arbeitbar, GH-103 traegt ``Status: draft``. Trotz
        Prioritaetsordnung wird GH-103 uebersprungen und GH-102 gewaehlt.
        Fehlerfall: fremde Issues werden gefuehrt oder Entwuerfe gestartet.
        """
        self.server.httpd.issues[:] = [
            issue(101, "Bob ready", labels=["ready"], assignees=["bob"]),
            issue(102, "Alice ready", labels=["ready"], assignees=["alice"]),
            issue(103, "Alice draft", labels=[], assignees=["alice"]),
            issue(104, "Bob draft", labels=[], assignees=["bob"]),
        ]
        project = self.make_project(
            env_text=self.issues_env(
                self.server, GITHUB_ISSUES_ASSIGNEE="alice",
                PACKAGE_ORDER="GH-103 GH-102"),
            tickets="")

        issues_module().sync_issues(str(project), self.config_for(project))

        text = self.tickets(project)
        self.assertIn("GH-102", text)
        self.assertIn("GH-103", text)
        self.assertNotIn("GH-101", text)
        self.assertNotIn("GH-104", text)
        self.assertNotRegex(entry_block(text, "GH-102"),
                            r"(?m)^\s+Status:")
        self.assertIn("Status: draft", entry_block(text, "GH-103"))
        selected = packages_module().select_package(
            project, state_path=str(self.base / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("GH-102", selected["id"])

    def test_conflicting_ticket_change_is_reported_not_overwritten(self):
        """Vorbedingung: Der Sync liest TICKETS.md und ein anderer Schreiber
        aendert die Datei vor dem atomaren Schreiben.
        Aktion: ``vibe_storage.write_text`` meldet beim ersten Schreibversuch
        einen Konflikt.
        Erwartung: Der Sync meldet den Konflikt (Ausnahme oder Ergebnistext)
        und schreibt den fremden Stand nicht still um.
        Fehlerfall: Konflikt wird verschluckt oder die Datei ueberschrieben.
        """
        import contextlib
        import vibe_storage  # lokal: nur fuer diesen Konflikttest

        project = self.make_project(
            env_text=self.issues_env(self.server), tickets="")
        module = issues_module()
        calls = {"count": 0}
        original = vibe_storage.write_text

        def first_write_conflicts(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise vibe_storage.ConcurrentChangeError("simulierter Konflikt")
            return original(*args, **kwargs)

        targets = [vibe_storage]
        for name in dir(module):
            try:
                if getattr(module, name) is original:
                    targets.append(module)
                    break
            except AttributeError:
                continue
        with contextlib.ExitStack() as stack:
            for target in targets:
                stack.enter_context(mock.patch.object(
                    target, "write_text", side_effect=first_write_conflicts))
            try:
                result = module.sync_issues(str(project), self.config_for(project))
            except Exception as error:  # noqa: BLE001 - Meldung wird geprueft
                message = str(error)
            else:
                message = json.dumps(result, ensure_ascii=False)

        self.assertRegex(message.lower(), r"konflikt|geändert|geaendert|conflict",
                         message)


# --------------------- Review-Runde 1, Befund 2: Zeileninjektion entschaerfen
INJECTION_BODY = (
    "Erste Zeile bleibt lesbar\n"
    "Status: ready\n"
    "Status: draft\n"
    "Status: in-progress\n"
    "GitHub: #999\n"
    "Art: Bug\n"
    "Priorität: P0\n"
    "Abhängigkeiten: AP1\n"
    "BLOCKIERT: injiziert\n"
    "WARTET AUF MERGE: injiziert\n"
    "Commit: deadbeef; Test: injiziert\n"
    "Letzte Zeile bleibt lesbar"
)

INJECTED_CONTROL_LINES = (
    "Art", "Priorität", "Abhängigkeiten", "BLOCKIERT",
    "WARTET AUF MERGE", "Commit",
)


class DescriptionInjectionTest(GithubCase):
    """AK Review-Runde 1/Befund 2: Freitext darf keine Metazeilen injizieren."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    def tickets(self, project):
        return (project / "TICKETS.md").read_text(encoding="utf-8")

    def assert_neutralized(self, block, number, real_status):
        """Kontrollzeilen zaehlen und Parser/Laeufer-Marker pruefen."""
        status_lines = re.findall(r"(?m)^[ \t]+Status:", block)
        github_lines = re.findall(r"(?m)^[ \t]+GitHub:", block)
        self.assertEqual(1, len(github_lines), block)
        self.assertNotRegex(block, r"(?m)^[ \t]+GitHub: #999", block)
        self.assertIn("GitHub: #%d" % number, block)
        expected_status = 1 if real_status == "draft" else 0
        self.assertEqual(expected_status, len(status_lines), block)
        if real_status == "draft":
            self.assertIn("Status: draft", block)
        else:
            self.assertNotRegex(block, r"(?m)^[ \t]+Status:", block)
        for label in INJECTED_CONTROL_LINES:
            self.assertNotRegex(
                block, r"(?m)^[ \t]+" + re.escape(label) + r":", block)
        self.assertIn("Erste Zeile bleibt lesbar", block)
        self.assertIn("Letzte Zeile bleibt lesbar", block)
        self.assertIn("#999", block)
        self.assertIn("deadbeef", block)

        # bin/vibe-Parser: echte Nummer, kein erfundenes Art/Status.
        cli = cli_parser_module()
        entries = cli._scan_blocks(block)
        self.assertEqual(1, len(entries), block)
        item = cli._parse_entry(entries[0], None, need_proof=False)
        self.assertIsNotNone(item, block)
        self.assertEqual("GH-%d" % number, item["id"], item)
        self.assertEqual(number, item["github"], item)
        self.assertEqual("", item["art"], item)
        self.assertNotIn(item["state"], ("BLOCKIERT", "WARTET AUF MERGE"),
                         item)
        if real_status == "draft":
            self.assertEqual("draft", item["status"], item)
            self.assertEqual("Draft", item["state"], item)
        else:
            self.assertIn(item["status"], ("", None), item)
            self.assertNotIn(item["state"], ("Draft", "In Progress"), item)

        # bin/vibe_issues._parse_block: echte Nummer, echter Status.
        module = issues_module()
        lines = block.splitlines()
        parsed = None
        for span in module._scan_blocks(lines):
            candidate = module._parse_block(lines, *span)
            if candidate["id"] == "GH-%d" % number:
                parsed = candidate
                break
        self.assertIsNotNone(parsed, block)
        self.assertEqual(number, parsed["github"], parsed)
        self.assertEqual("", parsed["art"], parsed)
        self.assertEqual(
            "draft" if real_status == "draft" else None, parsed["status"],
            parsed)

        # Laeufer-Marker und Nachweis duerfen nicht auf Freitext anspringen.
        packages = packages_module()
        self.assertFalse(packages.is_blocked(block), block)
        self.assertFalse(packages.is_waiting_merge(block), block)
        self.assertEqual(9, packages.priority(block), block)
        self.assertEqual([], packages.dependencies(block), block)
        self.assertEqual([], packages.proof_commits(block), block)
        self.assertEqual(real_status == "draft", packages.is_draft(block),
                         block)

    def test_sync_pull_neutralizes_metadata_lines_from_issue_body(self):
        """Vorbedingung: Remote-Issues 201 (ready) und 202 (draft) mit einem
        Body, der Status-/GitHub-/Art-/Prioritaets-/Abhaengigkeits-/Marker-/
        Commit-Zeilen enthaelt.
        Aktion: ``sync_issues``.
        Erwartung: Die Zeilen bleiben lesbar, wirken aber nicht als
        Steuerfelder: GH-201 ohne Statuszeile, GH-202 genau ``Status: draft``,
        ``github`` = echte Nummer, kein BLOCKIERT/WARTET/Art/Prioritaet/
        Abhaengigkeit/Commit-Nachweis.
        Fehlerfall: Freitext manipuliert Draft-Schutz, Issuenummer, Schranken
        oder Nachweis.
        """
        self.server.httpd.issues[:] = [
            issue(201, "Injected ready", labels=["ready"],
                  body=INJECTION_BODY),
            issue(202, "Injected draft", labels=[], body=INJECTION_BODY),
        ]
        project = self.make_project(
            env_text=(
                'TYPE=generic\nGITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                'GITHUB_API="%s"\nGITHUB_ISSUES_ENABLED="1"\n'
                % self.server.base),
            tickets="")

        issues_module().sync_issues(str(project), self.config_for(project))

        text = self.tickets(project)
        self.assert_neutralized(entry_block(text, "GH-201"), 201, "ready")
        self.assert_neutralized(entry_block(text, "GH-202"), 202, "draft")

    def test_add_ticket_connected_neutralizes_metadata_lines(self):
        """Vorbedingung: ``add_ticket_connected`` mit einer Beschreibung, die
        Status-/GitHub-/Art-/Marker-/Commit-Zeilen enthaelt; einmal ready,
        einmal draft.
        Aktion: zwei Aufrufe mit ``draft=False``/``draft=True``.
        Erwartung: identische Entschaerfung wie beim Pull; der jeweilige
        lokale Block traegt den echten Zustand.
        Fehlerfall: Die lokale Ticket-Anlage laesst Metazeilen aus dem
        Beschreibungstext wirken.
        """
        project = self.make_project(
            env_text=(
                'TYPE=generic\nGITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                'GITHUB_API="%s"\nGITHUB_ISSUES_ENABLED="1"\n'
                % self.server.base),
            tickets="")
        module = issues_module()
        config = self.config_for(project)

        ready_id = module.add_ticket_connected(
            str(project), config, "Injected ready", INJECTION_BODY, "", False)
        draft_id = module.add_ticket_connected(
            str(project), config, "Injected draft", INJECTION_BODY, "", True)

        text = self.tickets(project)
        self.assert_neutralized(entry_block(text, ready_id), 201, "ready")
        self.assert_neutralized(entry_block(text, draft_id), 202, "draft")


# ------------------------------- Design 15/17: Entwuerfe werden nicht gestartet
class DraftSelectionTest(GithubCase):
    """AK Design 15/17: ``is_draft`` und Auswahl in allen drei Wegen."""

    def project(self, tickets="", feedback="", order=""):
        env = 'TYPE=generic\nGITHUB_ENABLED="1"\n'
        if order:
            env += 'PACKAGE_ORDER="%s"\n' % order
        return self.make_project(name="selection", tickets=tickets,
                                 feedback=feedback, env_text=env)

    def select(self, project, **kwargs):
        return packages_module().select_package(
            project, state_path=str(self.base / "next.json"), **kwargs)

    def test_is_draft_requires_the_exact_status_line(self):
        """Vorbedingung: Bloecke mit ``Status: draft``, nur dem Wort „draft“
        in der Beschreibung sowie ohne Statuszeile.
        Aktion: ``is_draft`` je Block.
        Erwartung: nur die exakte Statuszeile gilt als Entwurf; „draft“ im
        Beschreibungstext nicht.
        Fehlerfall: Freitext markiert ein Paket als Entwurf.
        """
        module = packages_module()

        self.assertTrue(module.is_draft("- [ ] T1 Echt\n  Status: draft\n"))
        self.assertFalse(module.is_draft(
            "- [ ] T2 Text\n  Beschreibung: draft\n"))
        self.assertFalse(module.is_draft("- [ ] T3 Offen\n"))

    def test_package_order_skips_a_draft(self):
        """Vorbedingung: ``PACKAGE_ORDER="T1 T2"``; T1 ist Entwurf, T2 offen.
        Aktion: ``select_package``.
        Erwartung: T2 wird gewaehlt; T1 wird trotz erster Prioritaet
        uebersprungen.
        Fehlerfall: Entwurf startet ueber die Priorisierungsliste.
        """
        project = self.project(
            tickets=("- [ ] T1 Entwurf\n  Status: draft\n"
                     "- [ ] T2 Offen\n"),
            order="T1 T2")

        selected = self.select(project)

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_ticket_priority_order_skips_a_draft(self):
        """Vorbedingung: T1 ist P0-Entwurf, T2 offen ohne Prioritaet.
        Aktion: ``select_package`` ohne PACKAGE_ORDER.
        Erwartung: T2 wird gewaehlt; die Ticket-Prioritaet darf den Entwurf
        nicht vorziehen.
        Fehlerfall: Entwurf startet ueber die P0-Ordnung.
        """
        project = self.project(
            tickets=("- [ ] T1 Entwurf\n  Priorität: P0\n  Status: draft\n"
                     "- [ ] T2 Offen\n"))

        selected = self.select(project)

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_default_and_feedback_order_skip_a_draft(self):
        """Vorbedingung: einziger TICKETS-Block T1 ist Entwurf; F1 ist
        normales Feedback.
        Aktion: ``select_package``.
        Erwartung: F1 aus FEEDBACK.md wird gewaehlt; ohne F1 bleibt das
        Ergebnis ``None``.
        Fehlerfall: Entwurf startet ueber die Standard-/Feedback-Ordnung.
        """
        project = self.project(
            tickets="- [ ] T1 Entwurf\n  Status: draft\n",
            feedback="- [ ] F1 Feedback\n  Beschreibung: frei\n")

        selected = self.select(project)

        self.assertIsNotNone(selected)
        self.assertEqual("F1", selected["id"])

        only_draft = self.project(tickets="- [ ] T1 Entwurf\n  Status: draft\n")
        self.assertIsNone(self.select(only_draft))

    def test_prefer_reattaches_a_draft_package(self):
        """Vorbedingung: T1 ist Entwurf, T2 offen.
        Aktion: ``select_package(project, prefer="T1")``.
        Erwartung: T1 wird ausdruecklich erneut gewaehlt (Reattach gewinnt wie
        bei BLOCKIERT).
        Fehlerfall: ``prefer`` wird durch den Entwurfszustand wirkungslos.
        """
        project = self.project(
            tickets=("- [ ] T1 Entwurf\n  Status: draft\n"
                     "- [ ] T2 Offen\n"))

        selected = self.select(project, prefer="T1")

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])


# ------------------------------------------- Design 5: Parser und Praezedenz
class TicketParserTest(unittest.TestCase):
    """AK Design 5: ``Status:``/``GitHub:`` additiv, Praezedenz erhalten."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "vibe"
        cls.home = Path(cls._tmp.name) / "home"
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        cls.home.mkdir()
        cls.saved = {key: os.environ.get(key)
                     for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
        os.environ["VIBE"] = str(cls.root)
        os.environ["VIBE_NO_CONTAINER"] = "1"
        os.environ["HOME"] = str(cls.home)
        try:
            cls.cli = load_module(CLI, "vibe_ap3_parser_under_test")
        finally:
            for key, value in cls.saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def write(self, tickets="", feedback=""):
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n" + tickets, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + feedback, encoding="utf-8")

    def rows(self):
        return {row["id"]: row for row in self.cli.ticket_items("proj")}

    def test_status_and_github_reference_are_exposed_additively(self):
        """Vorbedingung: offener Block mit ``Status: in-progress`` und
        ``GitHub: #103``.
        Aktion: ``ticket_items`` lesen.
        Erwartung: ``status`` == ``in-progress``, ``github`` == 103,
        ``completed`` False; Titel/Beschreibung unveraendert.
        Fehlerfall: Felder fehlen oder das Paket gilt als erledigt.
        """
        self.write(tickets=(
            "- [ ] AP1 Verbundene Aufgabe\n"
            "  Beschreibung: Text\n"
            "  Status: in-progress\n"
            "  GitHub: #103\n"))

        row = self.rows()["AP1"]

        self.assertEqual("in-progress", row.get("status"), row)
        self.assertEqual(103, int(row.get("github")), row)
        self.assertIs(row["completed"], False, row)
        self.assertEqual("Verbundene Aufgabe", row["title"])
        self.assertEqual("Text", row["description"])

    def test_legacy_open_block_keeps_its_fields(self):
        """Vorbedingung: klassischer offener Block ohne neue Zeilen.
        Aktion: ``ticket_items`` lesen.
        Erwartung: Zustand ``offen``; ``status`` leer/None, ``github`` None.
        Fehlerfall: Bestandsfelder aendern sich oder ein Fantasiewert
        erscheint.
        """
        self.write(tickets=(
            "- [ ] AP2 Klassisch\n"
            "  Beschreibung: Alt\n"))

        row = self.rows()["AP2"]

        self.assertEqual("offen", row["state"])
        self.assertIn(row.get("status"), ("", None), row)
        self.assertIsNone(row.get("github"), row)

    def test_gh_id_without_reference_keeps_github_none(self):
        """Vorbedingung: Legacy-Block mit ID ``GH-77``, aber ohne
        ``GitHub: #77``-Zeile.
        Aktion: ``ticket_items`` lesen.
        Erwartung: ``id`` bleibt GH-77, ``github`` ist None; die UI darf den
        Bezug spaeter ueber die ID erkennen, der Parser erfindet keine Nummer.
        Fehlerfall: Der Parser leitet github aus der ID ab und verletzt den
        Vertrag fuer Legacy-Bloecke.
        """
        self.write(tickets=(
            "- [ ] GH-77 Legacy-Import\n"
            "  Beschreibung: ohne Verweiszeile\n"))

        row = self.rows()["GH-77"]

        self.assertEqual("GH-77", row["id"])
        self.assertIsNone(row.get("github"), row)
        self.assertIn(row.get("status"), ("", None), row)

    def test_state_precedence_keeps_runner_states_above_in_progress(self):
        """Vorbedingung: vier Bloecke mit ``Status: in-progress``, zusaetzlich
        BLOCKIERT, WARTET AUF MERGE bzw. erledigt.
        Aktion: ``ticket_items`` lesen.
        Erwartung: BLOCKIERT > WARTET AUF MERGE > In-Progress > offen;
        erledigt bleibt erledigt. Der reine In-Progress-Block wird nicht als
        ``offen`` gemeldet.
        Fehlerfall: In-Progress maskiert eine Runner-Schranke.
        """
        self.write(tickets=(
            "- [ ] AP1 Blockiert\n"
            "  Status: in-progress\n"
            "  BLOCKIERT: extern\n\n"
            "- [ ] AP2 Wartet\n"
            "  Status: in-progress\n"
            "  WARTET AUF MERGE: PR offen\n\n"
            "- [x] AP3 Fertig\n"
            "  Status: in-progress\n"
            "  Commit: abc1234; Test: test_ap3\n\n"
            "- [ ] AP4 Fortschritt\n"
            "  Status: in-progress\n"))

        rows = self.rows()

        self.assertEqual("BLOCKIERT", rows["AP1"]["state"], rows["AP1"])
        self.assertEqual("WARTET AUF MERGE", rows["AP2"]["state"], rows["AP2"])
        self.assertEqual("erledigt", rows["AP3"]["state"], rows["AP3"])
        self.assertIs(rows["AP3"]["completed"], True, rows["AP3"])
        self.assertNotEqual("offen", rows["AP4"]["state"], rows["AP4"])
        self.assertIn("progress", rows["AP4"]["state"].lower().replace("-", " "),
                      rows["AP4"])

    def test_draft_status_is_exposed_with_precedence(self):
        """Vorbedingung: Bloecke mit ``Status: draft`` allein sowie zusammen
        mit In-Progress, BLOCKIERT, WARTET AUF MERGE und erledigt.
        Aktion: ``ticket_items`` lesen.
        Erwartung: draft wird als ``status``/Zustand sichtbar (nicht
        ``offen``); Praezedenz erledigt > BLOCKIERT > WARTET > In-Progress >
        Draft.
        Fehlerfall: Entwurf gilt als arbeitsoffen oder maskiert eine Schranke.
        """
        self.write(tickets=(
            "- [ ] AP1 Entwurf\n"
            "  Status: draft\n\n"
            "- [ ] AP2 Beides\n"
            "  Status: draft\n"
            "  Status: in-progress\n\n"
            "- [ ] AP3 Blockiert\n"
            "  Status: draft\n"
            "  BLOCKIERT: extern\n\n"
            "- [ ] AP4 Wartet\n"
            "  Status: draft\n"
            "  WARTET AUF MERGE: PR\n\n"
            "- [x] AP5 Fertig\n"
            "  Status: draft\n"
            "  Commit: abc1234; Test: test_ap3\n"))

        rows = self.rows()

        self.assertEqual("draft", rows["AP1"].get("status"), rows["AP1"])
        self.assertNotEqual("offen", rows["AP1"]["state"], rows["AP1"])
        self.assertRegex(rows["AP1"]["state"].lower(), r"draft|entwurf")
        self.assertEqual("BLOCKIERT", rows["AP3"]["state"], rows["AP3"])
        self.assertEqual("WARTET AUF MERGE", rows["AP4"]["state"], rows["AP4"])
        self.assertEqual("erledigt", rows["AP5"]["state"], rows["AP5"])
        self.assertIn("progress",
                      rows["AP2"]["state"].lower().replace("-", " "),
                      rows["AP2"])

    def test_feedback_parsing_remains_functional(self):
        """Vorbedingung: normales Bug-Feedback ohne neue Zeilen.
        Aktion: ``feedback_items`` lesen.
        Erwartung: ``kind`` == bug, Zustand offen, keine Ausnahme.
        Fehlerfall: Die additive Parser-Aenderung bricht FEEDBACK.md.
        """
        self.write(feedback=(
            "- [ ] F1 Fehler\n"
            "  Art: Bug\n"
            "  Beschreibung: kaputt\n"))

        items = self.cli.feedback_items("proj")

        self.assertEqual(1, len(items), items)
        self.assertEqual("bug", items[0]["kind"], items[0])
        self.assertEqual("offen", items[0]["state"], items[0])


# --------------------------------------- Design 8: Closes #123 im PR-Body
class CompletePackageClosesIssueTest(GithubCase):
    """AK Design 8: Der Runner-Abschluss verknuepft den PR mit dem Issue."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def feature_project(self, name, tickets):
        url, _seed = seed_bare(self.base, name)
        project = clone_project(self.base, name, url)
        real_git(project, "checkout", "-q", "-b", "feature/x")
        (project / "feature.txt").write_text("feature\n", encoding="utf-8")
        real_git(project, "add", "-A")
        real_git(project, "commit", "-q", "-m", "feature: change")
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nGITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\nGITHUB_BASE="main"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % self.server.base,
            encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n\n" + tickets,
                                            encoding="utf-8")
        return project

    def pr_payload(self):
        posts = self.server.by_path("POST", "/pulls")
        self.assertEqual(1, len(posts), posts)
        return posts[0]["body"]

    def test_issue_id_in_the_block_appends_closes_to_the_pr_body(self):
        """Vorbedingung: Paket GH-77 im Ticketblock, Featurebranch bereit.
        Aktion: ``vibe_github.complete_package(..., package_id="GH-77")``.
        Erwartung: Der PR-Body enthaelt ``Closes #77``.
        Fehlerfall: PR ohne Close-Verweis.
        """
        project = self.feature_project(
            "close-id", "- [ ] GH-77 Paket\n  Beschreibung: Text\n")

        performed, ok, message, _result = self.gh.complete_package(
            project, "feature/x", package_id="GH-77")

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertIn("Closes #77", self.pr_payload().get("body", ""))

    def test_github_reference_line_appends_closes_to_the_pr_body(self):
        """Vorbedingung: lokales Paket AP9 mit ``GitHub: #551``.
        Aktion: ``complete_package(..., package_id="AP9")``.
        Erwartung: Der PR-Body enthaelt ``Closes #551``.
        Fehlerfall: Verweiszeile wird nicht ausgewertet.
        """
        project = self.feature_project(
            "close-ref",
            "- [ ] AP9 Paket\n  Beschreibung: Text\n  GitHub: #551\n")

        performed, ok, message, _result = self.gh.complete_package(
            project, "feature/x", package_id="AP9")

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertIn("Closes #551", self.pr_payload().get("body", ""))

    def test_package_without_issue_reference_keeps_the_pr_body(self):
        """Vorbedingung: lokales Paket AP10 ohne GitHub-Bezug.
        Aktion: ``complete_package(..., package_id="AP10")``.
        Erwartung: Der PR-Body enthaelt keinen ``Closes``-Zusatz.
        Fehlerfall: Erfundener Close-Verweis.
        """
        project = self.feature_project(
            "close-none",
            "- [ ] AP10 Paket\n  Beschreibung: Text\n")

        performed, ok, message, _result = self.gh.complete_package(
            project, "feature/x", package_id="AP10")

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertNotIn("Closes", self.pr_payload().get("body", ""))


if __name__ == "__main__":
    unittest.main()
