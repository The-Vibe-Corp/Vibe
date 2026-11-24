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
            if number in self.server.fail_patch_numbers:
                self._respond(403, {"message": "simulierte fehlende Berechtigung"})
                return
            for item in self.server.issues:
                if item.get("number") != number:
                    continue
                if "state" in payload:
                    item["state"] = payload["state"]
                if "title" in payload:
                    item["title"] = payload["title"]
                if "body" in payload:
                    item["body"] = payload["body"]
                if "labels" in payload:
                    item["labels"] = [{"name": name}
                                      for name in payload.get("labels") or []]
                if "assignees" in payload:
                    item["assignees"] = [{"login": name}
                                         for name in payload.get("assignees") or []]
                self._respond(200, item)
                return
            self._respond(404, {"message": "Not Found"})
            return
        self._respond(404, {"message": "Not Found"})


class FakeIssuesServer:
    """Loopback-REST-Fake fuer GitHub-Issues und Merge-Requests."""

    def __init__(self, issues=None, next_number=200, fail_create=False,
                 fail_patch_numbers=None):
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
        self.httpd.fail_patch_numbers = set(fail_patch_numbers or ())
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
INJECTION_BODY = (
    "Erste Zeile bleibt lesbar\n"
    "Status: ready\n"
    "GitHub: #999\n"
    "Art: Bug\n"
    "BLOCKIERT: injiziert\n"
    "Commit: deadbeef; Test: injiziert\n"
    "Letzte Zeile bleibt lesbar"
)


STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="task", state="open", **extra):
    """Ticketdatensatz des GH-48-Speichers."""
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class IssuesSyncTest(GithubCase):
    """GH-48: Pull, Push, Close und Konfliktschutz auf dem Ticketspeicher."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    # ---------------------------------------------------------- Speicher
    def write_store(self, project, records):
        path = project / ".vibe" / "tickets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "tickets": list(records)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return path

    def records(self, project):
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}

    def sync(self, project):
        stats = stats_dict(issues_module().sync_issues(
            str(project), self.config_for(project)))
        return stats

    # ------------------------------------------------------------ Fälle
    def test_backbone_module_uses_vibe_github_for_rest(self):
        """Vorbedingung: ``bin/vibe_issues.py`` ist das Backbone-Modul.
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
        """Vor: GITHUB_LABEL="vibe", Remote-Issues tragen es nicht.
        Aktion: sync_issues. Erwartet: GH-101 und GH-102 entstehen."""
        project = self.make_project(
            env_text=self.issues_env(self.server, GITHUB_LABEL="vibe"))

        self.sync(project)

        self.assertEqual({"GH-101", "GH-102"}, set(self.records(project)))

    def test_pull_creates_tickets_and_skips_pull_requests(self):
        """Vor: leerer Speicher; Remote 101 (bug), 102 (in-progress), PR 104.
        Aktion: sync_issues. Erwartet: GH-101 bug/open mit Body, GH-102
        in-progress; kein GH-104; state=all gelesen."""
        project = self.make_project(env_text=self.issues_env(self.server))

        stats = self.sync(project)

        records = self.records(project)
        self.assertEqual("bug", records["GH-101"]["type"])
        # Ohne ready-Label gilt ein offenes Issue als Entwurf.
        self.assertEqual("draft", records["GH-101"]["state"])
        self.assertEqual(101, records["GH-101"]["github"])
        self.assertEqual("Open body", records["GH-101"]["description"])
        self.assertEqual("in-progress", records["GH-102"]["state"])
        self.assertNotIn("GH-104", records)
        gets = self.server.calls("GET")
        self.assertTrue(any("state=all" in call["path"] for call in gets),
                        gets)
        self.assertEqual(2, stat_count(stats["created"]), stats)

    def test_pull_does_not_duplicate_and_updates_open_tickets(self):
        """Vor: GH-101 und AP7 mit textgleichem Remote-Stand (Baseline);
        danach ändert sich der Remote-Titel und AP7 wird in-progress.
        Aktion: sync zweimal.
        Erwartet: eine GH-101-Zeile, Titel aktualisiert, AP7 bleibt ID und
        wird in-progress; zweiter Lauf erzeugt nichts Neues."""
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("GH-101", "Remote open", github=101,
                          description="Open body"),
            ticket_record("AP7", "Remote progress", github=102,
                          description="Progress body"),
        ])

        self.sync(project)
        self.server.httpd.issues[0]["title"] = "Remote open neu"
        self.server.httpd.issues[1]["title"] = "Remote progress neu"
        self.server.httpd.issues[1]["labels"] = [
            {"name": "ready"}, {"name": "in-progress"}]
        self.sync(project)
        records = self.records(project)

        self.assertEqual({"GH-101", "AP7"}, set(records))
        self.assertEqual("Remote open neu", records["GH-101"]["title"])
        self.assertEqual("in-progress", records["AP7"]["state"])
        self.assertEqual(102, records["AP7"]["github"])

        self.sync(project)
        self.assertEqual({"GH-101", "AP7"}, set(self.records(project)))

    def test_closed_issue_marks_the_local_ticket_done(self):
        """Vor: GH-103 offen, Issue geschlossen. Aktion: sync_issues.
        Erwartet: state done, test-Feld nennt das geschlossene Issue;
        Statistik zählt closed."""
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("GH-103", "Remote closed", github=103)])

        stats = self.sync(project)

        record = self.records(project)["GH-103"]
        self.assertEqual("done", record["state"])
        self.assertIn("#103", record["test"])
        self.assertEqual(1, stat_count(stats["closed"]), stats)

    def test_pull_state_is_authoritative_and_remote_text_updates_are_taken_over(self):
        """GH-47: Zustand bleibt label-autoritativ, Texte sind bidirektional.
        Vor: textgleicher Ausgangsstand (Baseline) für GH-101/102/105/103;
        danach ändert der Remote-Stand Titel und Beschreibung, dazu ein neues
        Ready-Issue.
        Aktion: sync_issues zweimal.
        Erwartet: Zustände/Titel/Beschreibungen vom Remote für offene Tickets;
        das erledigte GH-103 behält seinen Text (Done-Schutz); GH-106 entsteht.
        Fehlerfall: Beschreibungen bleiben lokal oder Done-Tickets werden
        überschrieben."""
        self.server.httpd.issues[:] = [
            issue(101, "Alt draft", labels=["bug"], body="lokal 101"),
            issue(102, "Alt progress", labels=["ready", "in-progress"],
                  body="lokal 102"),
            issue(105, "Alt ready", labels=["ready"], body="lokal 105"),
            issue(103, "Alt closed", state="closed", body="lokal 103"),
        ]
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("GH-101", "Alt draft", github=101,
                          description="lokal 101"),
            ticket_record("GH-102", "Alt progress", github=102,
                          description="lokal 102"),
            ticket_record("GH-105", "Alt ready", github=105,
                          description="lokal 105"),
            ticket_record("GH-103", "Alt closed", github=103,
                          description="lokal 103"),
        ])
        self.sync(project)  # Baseline für den Textabgleich

        self.server.httpd.issues[:] = [
            issue(101, "Remote draft", labels=["bug"],
                  body="Remote body 101"),
            issue(102, "Remote progress", labels=["ready", "in-progress"],
                  body="Remote body 102"),
            issue(105, "Remote ready", labels=["ready"],
                  body="Remote body 105"),
            issue(103, "Remote closed", state="closed", body="Remote body 103"),
            issue(106, "Fresh ready", labels=["ready"], body="Fresh body 106"),
        ]

        self.sync(project)

        records = self.records(project)
        self.assertEqual("draft", records["GH-101"]["state"])
        self.assertEqual("Remote draft", records["GH-101"]["title"])
        self.assertEqual("Remote body 101", records["GH-101"]["description"])
        self.assertEqual("in-progress", records["GH-102"]["state"])
        self.assertEqual("Remote body 102", records["GH-102"]["description"])
        self.assertEqual("open", records["GH-105"]["state"])
        self.assertEqual("Remote body 105", records["GH-105"]["description"])
        self.assertEqual("done", records["GH-103"]["state"])
        self.assertEqual("Alt closed", records["GH-103"]["title"])
        self.assertEqual("lokal 103", records["GH-103"]["description"])
        self.assertEqual("Fresh body 106", records["GH-106"]["description"])

    def test_previously_open_issue_without_ready_label_becomes_draft(self):
        """Vor: GH-101 offen, Remote offen ohne Ready-Label.
        Aktion: sync_issues. Erwartet: lokaler Zustand draft."""
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("GH-101", "Alt", github=101)])

        self.sync(project)

        self.assertEqual("draft", self.records(project)["GH-101"]["state"])

    def test_push_creates_issues_for_open_local_tickets_only(self):
        """Vor: offenes AP1 (task), AP2 (bug), done AP3, Feedback F1,
        blockiertes B4. Aktion: sync_issues. Erwartet: nur AP1/AP2 werden
        gepusht (AP2 mit bug-Label), erhalten github; AP3/F1/B4 nicht."""
        self.server.httpd.issues[:] = []
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("AP1", "Local task", description="Do it"),
            ticket_record("AP2", "Local bug", type="bug",
                          description="Broken"),
            ticket_record("AP3", "Done", state="done", commit="abcdef1",
                          test="test_ap3"),
            ticket_record("F1", "Feedback", type="feedback"),
            ticket_record("B4", "Blocked", type="bug", state="blocked",
                          blocked_reason="extern"),
        ])

        stats = self.sync(project)

        posts = self.server.by_path("POST", "/issues")
        titles = {post["body"].get("title") for post in posts}
        # GH-48: Alle offenen Tickets ohne GitHub-Bezug werden gepusht,
        # einschließlich Feedback (das frühere Ledger-Verbot entfällt).
        self.assertEqual({"Local task", "Local bug", "Feedback"}, titles, posts)
        bug_post = next(post for post in posts
                        if post["body"].get("title") == "Local bug")
        self.assertIn("bug", bug_post["body"].get("labels") or [], bug_post)
        records = self.records(project)
        self.assertIsNotNone(records["AP1"]["github"])
        self.assertIsNotNone(records["AP2"]["github"])
        self.assertIsNone(records["AP3"]["github"])
        self.assertIsNotNone(records["F1"]["github"])
        self.assertIsNone(records["B4"]["github"])
        self.assertEqual(3, stat_count(stats["pushed"]), stats)

    def test_push_excludes_waiting_tickets(self):
        """Vor: AP1 waiting-merge, AP2 blocked. Aktion: sync_issues.
        Erwartet: keine POSTs; github bleibt leer (GH-48-Änderung)."""
        self.server.httpd.issues[:] = []
        project = self.make_project(env_text=self.issues_env(self.server))
        self.write_store(project, [
            ticket_record("AP1", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
            ticket_record("AP2", "Blockiert", state="blocked",
                          blocked_reason="extern"),
        ])

        self.sync(project)

        self.assertEqual([], self.server.by_path("POST", "/issues"))
        records = self.records(project)
        self.assertIsNone(records["AP1"]["github"])
        self.assertIsNone(records["AP2"]["github"])

    def test_assignee_filter_limits_pull_and_assigns_new_issues(self):
        """Vor: Assignee alice; Issue 101 alice, 102 bob; AP1 wartet lokal.
        Aktion: sync_issues. Erwartet: nur GH-101 gepullt; AP1-Issue alice."""
        project = self.make_project(
            env_text=self.issues_env(self.server, GITHUB_ISSUES_ASSIGNEE="alice"))
        self.write_store(project, [
            ticket_record("AP1", "Local task", description="Do it")])

        self.sync(project)

        records = self.records(project)
        self.assertIn("GH-101", records)
        self.assertNotIn("GH-102", records)
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(1, len(posts), posts)
        self.assertEqual(["alice"], posts[0]["body"].get("assignees"), posts)

    def test_conflicting_ticket_change_is_reported_not_overwritten(self):
        """Vor: Speicherschreiben meldet beim ersten Versuch einen Konflikt.
        Aktion: sync_issues. Erwartet: Konfliktmeldung, kein stilles
        Überschreiben."""
        import contextlib
        import vibe_storage  # lokal: nur für diesen Konflikttest

        project = self.make_project(env_text=self.issues_env(self.server))
        module = issues_module()
        calls = {"count": 0}
        original = vibe_storage.write_text

        def first_write_conflicts(*args, **kwargs):
            calls["count"] += 1
            raise vibe_storage.ConcurrentChangeError("simulierter Konflikt")

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                vibe_storage, "write_text", side_effect=first_write_conflicts))
            try:
                result = module.sync_issues(str(project),
                                            self.config_for(project))
            except Exception as error:  # noqa: BLE001 - Meldung wird geprüft
                message = str(error)
            else:
                message = json.dumps(result, ensure_ascii=False)

        self.assertRegex(message.lower(),
                         r"konflikt|geändert|geaendert|conflict", message)


class DescriptionAndStateTest(GithubCase):
    """GH-48: Freitext ist ein Feld und kann keine Metazeilen injizieren."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    def records(self, project):
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}

    def test_pull_keeps_metadata_lines_in_the_description_field(self):
        """Vor: Issue-Body enthält Status-/GitHub-/Commit-Zeilen. Aktion: sync.
        Erwartet: Der Body bleibt vollständig in description; type/state
        stammen aus Labels, github aus der Nummer."""
        self.server.httpd.issues[:] = [
            issue(201, "Injected ready", labels=["ready"],
                  body=INJECTION_BODY),
            issue(202, "Injected draft", labels=[], body=INJECTION_BODY),
        ]
        project = self.make_project(env_text=self.issues_env(self.server))

        issues_module().sync_issues(str(project), self.config_for(project))

        records = self.records(project)
        self.assertEqual("open", records["GH-201"]["state"])
        self.assertEqual("draft", records["GH-202"]["state"])
        self.assertEqual(201, records["GH-201"]["github"])
        for tid in ("GH-201", "GH-202"):
            self.assertIn("Status: ready", records[tid]["description"])
            self.assertIn("Commit: deadbeef", records[tid]["description"])
            self.assertEqual("task", records[tid]["type"])

    def test_add_ticket_connected_keeps_metadata_text_inert(self):
        """Vor: ``add_ticket_connected`` mit Metazeilen im Text, ready+draft.
        Aktion: zwei Aufrufe. Erwartet: GH-Tickets mit echtem Zustand; der
        Text bleibt in description."""
        project = self.make_project(env_text=self.issues_env(self.server))
        module = issues_module()
        config = self.config_for(project)

        ready_id = module.add_ticket_connected(
            str(project), config, "Injected ready", INJECTION_BODY, "", False)
        draft_id = module.add_ticket_connected(
            str(project), config, "Injected draft", INJECTION_BODY, "", True)

        records = self.records(project)
        self.assertEqual("open", records[ready_id]["state"])
        self.assertEqual("draft", records[draft_id]["state"])
        self.assertIn("BLOCKIERT: injiziert",
                      records[ready_id]["description"])
        self.assertNotEqual("blocked", records[ready_id]["state"])


class DraftSelectionTest(GithubCase):
    """GH-48: draft/blocked/waiting werden nicht gestartet."""

    def project(self, records, order=""):
        env = 'TYPE=generic\nGITHUB_ENABLED="1"\n'
        if order:
            env += 'PACKAGE_ORDER="%s"\n' % order
        project = self.make_project(name="selection", env_text=env)
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": list(records)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return project

    def select(self, project, **kwargs):
        return packages_module().select_package(
            project, state_path=str(self.base / "next.json"), **kwargs)

    def test_a_draft_is_skipped_in_favour_of_an_open_ticket(self):
        project = self.project([
            ticket_record("T1", "Entwurf", state="draft"),
            ticket_record("T2", "Offen"),
        ])

        self.assertEqual("T2", self.select(project)["id"])

    def test_package_order_skips_a_draft(self):
        project = self.project([
            ticket_record("T1", "Entwurf", state="draft"),
            ticket_record("T2", "Offen"),
        ], order="T1 T2")

        self.assertEqual("T2", self.select(project)["id"])

    def test_priority_order_skips_a_draft(self):
        project = self.project([
            ticket_record("T1", "Entwurf", state="draft", priority="P0"),
            ticket_record("T2", "Offen"),
        ])

        self.assertEqual("T2", self.select(project)["id"])

    def test_prefer_reattaches_a_draft_package(self):
        project = self.project([
            ticket_record("T1", "Entwurf", state="draft"),
            ticket_record("T2", "Offen"),
        ])

        self.assertEqual("T1", self.select(project, prefer="T1")["id"])

    def test_assignee_and_draft_compose_for_work_selection(self):
        self.server = FakeIssuesServer(issues=[
            issue(101, "Bob ready", labels=["ready"], assignees=["bob"]),
            issue(102, "Alice ready", labels=["ready"], assignees=["alice"]),
            issue(103, "Alice draft", labels=[], assignees=["alice"]),
            issue(104, "Bob draft", labels=[], assignees=["bob"]),
        ]).start()
        self.addCleanup(self.server.close)
        project = self.make_project(
            env_text=self.issues_env(
                self.server, GITHUB_ISSUES_ASSIGNEE="alice",
                PACKAGE_ORDER="GH-103 GH-102"))

        issues_module().sync_issues(
            str(project), self.gh.read_config(
                str(project / ".vibe" / "project.env")))

        records = self.records(project)
        self.assertIn("GH-102", records)
        self.assertIn("GH-103", records)
        self.assertNotIn("GH-101", records)
        self.assertNotIn("GH-104", records)
        self.assertEqual("open", records["GH-102"]["state"])
        self.assertEqual("draft", records["GH-103"]["state"])
        self.assertEqual("GH-102", self.select(project)["id"])

    def records(self, project):
        document = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}


class TicketStatusTest(GithubCase):
    """GH-48: Zeilenform der Oberflächen aus dem Speicher."""

    def cli_for_base(self):
        """Lädt ``bin/vibe`` mit VIBE=self.base, damit ``proj`` auflösbar ist."""
        old = {key: os.environ.get(key)
               for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
        os.environ.update({"VIBE": str(self.base), "VIBE_NO_CONTAINER": "1",
                           "HOME": str(self.home)})
        try:
            loader = importlib.machinery.SourceFileLoader(
                "vibe_ap3_status_cli_under_test", str(CLI))
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

    def test_ticket_items_expose_state_status_and_github(self):
        project = self.make_project()
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [
                ticket_record("GH-48", "Ticket", github=48),
                ticket_record("AP1", "Läuft", state="in-progress"),
            ]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        cli = self.cli_for_base()

        rows = {row["id"]: row for row in cli.ticket_items(project.name)}

        self.assertEqual(48, rows["GH-48"]["github"])
        self.assertEqual("offen", rows["GH-48"]["state"])
        self.assertEqual("in-progress", rows["AP1"]["status"])
        self.assertEqual("In Progress", rows["AP1"]["state"])

    def test_done_ticket_is_completed_and_not_open(self):
        project = self.make_project()
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [
                ticket_record("AP1", "Fertig", state="done",
                              commit="abcdef1", test="test_ap1"),
            ]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        cli = self.cli_for_base()

        rows = cli.ticket_items(project.name)

        self.assertTrue(rows[0]["completed"])
        self.assertEqual("erledigt", rows[0]["state"])
        self.assertEqual([], cli.open_items(project.name))


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
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": list(tickets)},
                       ensure_ascii=False, indent=1) + "\n",
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
            "close-id", [ticket_record("GH-77", "Paket", github=77)])

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
            "close-ref", [ticket_record("AP9", "Paket", github=551)])

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
            "close-none", [ticket_record("AP10", "Paket")])

        performed, ok, message, _result = self.gh.complete_package(
            project, "feature/x", package_id="AP10")

        self.assertTrue(performed, message)
        self.assertTrue(ok, message)
        self.assertNotIn("Closes", self.pr_payload().get("body", ""))


if __name__ == "__main__":
    unittest.main()
