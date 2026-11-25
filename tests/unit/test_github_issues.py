"""GitHub-Issues: Synchronisierung, Oberflächen, Ticket-API und CLI.

Aufruf: python3 -m unittest tests.unit.test_github_issues -v
"""


# ===========================================================================
# (Backbone): GitHub-Issues-Sync unabhaengig vom Implementierungsdiff
# ===========================================================================

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
        Aktion: zwei Aufrufe mit dem einen Typ-Parameter (B1-Signatur).
        Erwartet: GH-Tickets mit echtem Zustand und dem übergebenen Typ; der
        Text bleibt in description."""
        project = self.make_project(env_text=self.issues_env(self.server))
        module = issues_module()
        config = self.config_for(project)

        ready_id = module.add_ticket_connected(
            str(project), config, "Injected ready", INJECTION_BODY,
            "feature", False)
        draft_id = module.add_ticket_connected(
            str(project), config, "Injected draft", INJECTION_BODY,
            "feature", True)

        records = self.records(project)
        self.assertEqual("open", records[ready_id]["state"])
        self.assertEqual("draft", records[draft_id]["state"])
        self.assertEqual("feature", records[ready_id]["type"])
        self.assertEqual("feature", records[draft_id]["type"])
        self.assertIn("BLOCKIERT: injiziert",
                      records[ready_id]["description"])
        self.assertNotEqual("blocked", records[ready_id]["state"])

    def test_add_ticket_connected_uses_one_type_for_label_and_store(self):
        """Vor: Issues-Sync aktiv, Loopback-Fake. Aktion: verbundene Anlage je
        Typ (bug/feature/feedback/task), draft und ein offenes Feature.

        Erwartung (B1/B+E): Typ-Label nur für bug/feature/feedback
        (``task`` ohne Typ-Label); bei draft fehlt das Ready-Label, bei open
        ist es gesetzt; der Speichertyp entspricht genau dem Typ-Parameter.
        """
        project = self.make_project(env_text=self.issues_env(self.server))
        module = issues_module()
        config = self.config_for(project)

        cases = (("bug", True), ("feature", True), ("feedback", True),
                 ("task", True), ("feature", False))
        for index, (ttype, draft) in enumerate(cases):
            with self.subTest(ttype=ttype, draft=draft):
                self.server.requests.clear()
                self.server.httpd.next_number = 300 + index
                ticket_id = module.add_ticket_connected(
                    str(project), config, "Ticket %s %s" % (ttype, index),
                    "Text", ttype, draft)
                posts = [call for call in self.server.calls("POST")
                         if call["path"].rstrip("/").endswith("/issues")]
                self.assertEqual(1, len(posts), posts)
                labels = posts[0]["body"].get("labels") or []
                if ttype == "task":
                    self.assertNotIn("bug", labels, posts[0])
                    self.assertNotIn("feature", labels, posts[0])
                    self.assertNotIn("feedback", labels, posts[0])
                else:
                    self.assertIn(ttype, labels, posts[0])
                ready = config["issues_ready_label"]
                if draft:
                    self.assertNotIn(ready, labels, posts[0])
                else:
                    self.assertIn(ready, labels, posts[0])
                record = self.records(project)[ticket_id]
                self.assertEqual(ttype, record["type"])
                self.assertEqual("draft" if draft else "open", record["state"])


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


# ===========================================================================
# (Web-API, CLI, Nova-Oberflaeche): unabhaengige Abnahmetests
# ===========================================================================

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_web_routes import DashboardFixture

CLI_ap3 = REPO / "bin" / "vibe"
NOVA = REPO / "bin" / "web" / "nova-project.js"
WAITING_AP3 = "WARTET AUF MERGE"


def js_region(text, marker, fallback=8000):
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


def ticket_store(project, records):
    """Schreibt den GH-48-Ticketspeicher ``.vibe/tickets.json``.

    Alte Markdown-Ledger werden entfernt: Sie duerfen als Eingabe nicht mehr
    wirken (kein Dual-Read-Fallback), und ein liegengebliebener Altbestand
    soll die Speicherfaelle nicht verdecken.
    """
    path = Path(project) / ".vibe" / "tickets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "tickets": list(records)},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    for name in ("TICKETS.md", "FEEDBACK.md"):
        (Path(project) / name).unlink(missing_ok=True)
    return path


def ticket_records(project):
    """Ticketspeicher als ``{id: Datensatz}`` lesen."""
    document = json.loads(
        (Path(project) / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in document["tickets"]}


# ----------------------------------------------------------- Web-API-Fixture
class IssuesWebFixture(DashboardFixture):
    """Dashboard-Fixture mit Fake-GitHub und GitHub-Token in der Umgebung."""

    @classmethod
    def setUpClass(cls):
        previous = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN
        try:
            cls.start_server()
        finally:
            if previous is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)
        # GH-48: Der Speicher ist die einzige Ticketquelle; jeder Fall startet
        # mit einem leeren Speicher, damit kein Testzustand ueberlaeuft.
        self.write_tickets([])

    def write_env(self, **values):
        base = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": self.server.base,
        }
        base.update(values)
        text = "".join('%s="%s"\n' % (key, value)
                       for key, value in base.items())
        (self.project / ".vibe" / "project.env").write_text(text,
                                                           encoding="utf-8")

    def write_tickets(self, records):
        ticket_store(self.project, records)

    def tickets(self):
        return ticket_records(self.project)

    def github(self, body):
        status, text, _headers = self.post(
            "/api/github", dict({"name": "proj"}, **body))
        return status, json.loads(text)

    def ticket(self, body):
        status, text, _headers = self.post(
            "/api/ticket", dict({"name": "proj"}, **body))
        return status, json.loads(text)


# ------------------------------------------------------------- Web-API-Faelle
class IssuesSettingsApiTest(IssuesWebFixture):
    """AK Design 1/2/11: Einstellungen der neuen Issues-Karte."""

    def test_settings_persist_issues_options_and_status(self):
        """Vorbedingung: verbundenes Projekt mit aktivem Issues-Sync.
        Aktion: ``/api/github action=settings`` mit ``issues_enabled``,
        ``issues_in_progress`` und ``issues_assignee``.
        Erwartung: 200; ``project.env`` traegt
        ``GITHUB_ISSUES_ENABLED="1"``, ``GITHUB_ISSUES_IN_PROGRESS``,
        ``GITHUB_ISSUES_ASSIGNEE``; der Status liefert die Werte.
        Fehlerfall: Schluessel werden verworfen oder nicht gespeichert.
        """
        self.write_env()

        status, data = self.github({
            "action": "settings",
            "issues_enabled": True,
            "issues_in_progress": "triaged",
            "issues_ready": "freigegeben",
            "issues_assignee": "alice",
        })

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn('GITHUB_ISSUES_ENABLED="1"', env_text)
        self.assertIn('GITHUB_ISSUES_IN_PROGRESS="triaged"', env_text)
        self.assertIn('GITHUB_ISSUES_READY="freigegeben"', env_text)
        self.assertIn('GITHUB_ISSUES_ASSIGNEE="alice"', env_text)
        view = data.get("github") or {}
        self.assertIs(view.get("issues_enabled"), True, data)
        self.assertEqual("triaged", view.get("issues_in_progress_label"), data)
        self.assertEqual("freigegeben", view.get("issues_ready_label"), data)
        self.assertEqual("alice", view.get("issues_assignee"), data)

    def test_settings_can_turn_the_issue_sync_off_again(self):
        """Vorbedingung: Issues-Sync ist aktiv.
        Aktion: ``settings`` mit ``issues_enabled: false``.
        Erwartung: ``GITHUB_ISSUES_ENABLED=""``; Status meldet aus.
        Fehlerfall: Der Schalter laesst sich nicht zuruecksetzen.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.github({"action": "settings",
                                    "issues_enabled": False})

        self.assertEqual(200, status, data)
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn('GITHUB_ISSUES_ENABLED=""', env_text)
        self.assertIs((data.get("github") or {}).get("issues_enabled"), False,
                      data)


class IssuesSyncApiTest(IssuesWebFixture):
    """AK Design 4/6/10: Sync ueber die Web-API."""

    def test_sync_without_opt_in_is_refused_without_network(self):
        """Vorbedingung: GitHub verknuepft, aber ``GITHUB_ISSUES_ENABLED``
        fehlt.
        Aktion: ``/api/github action=issues.sync``.
        Erwartung: ``ok:false`` mit verstaendlicher Meldung; der Fake erhaelt
        keinen einzigen Aufruf; der Ticketspeicher bleibt unveraendert.
        Fehlerfall: Netzaufruf oder stilles Anlegen lokaler Eintraege.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")
        before = self.tickets()

        status, data = self.github({"action": "issues.sync"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        message = str(data.get("message") or "").lower()
        self.assertTrue(any(word in message for word in
                            ("issue", "sync", "nicht aktiv", "deaktiviert")),
                        data)
        self.assertEqual([], self.server.requests)
        self.assertEqual(before, self.tickets())

    def test_sync_returns_statistics_and_updates_tickets(self):
        """Vorbedingung: Issues-Sync aktiv; Remote hat Issue 101, lokal wartet
        AP1.
        Aktion: ``issues.sync``.
        Erwartung: 200; Statistik ``created``/``updated``/``closed``/
        ``pushed``; der Ticketspeicher enthaelt GH-101 und AP1 traegt den
        GitHub-Bezug ``github=<n>``.
        Fehlerfall: keine Statistik, kein Pull oder kein Push.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("AP1", "Local task", description="Do it")])

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        stats = stats_dict(data)
        contract = ("created", "updated", "closed", "pushed",
                    "text_pushed", "text_pulled", "conflicts",
                    "closed_remote")
        for key in contract:
            self.assertIn(key, stats, data)
        self.assertEqual(set(contract), set(stats), data)
        self.assertTrue(all(isinstance(stats[key], int) for key in contract),
                        data)
        records = self.tickets()
        self.assertEqual("Remote open", records["GH-101"]["title"])
        self.assertEqual(101, records["GH-101"]["github"])
        self.assertIsInstance(records["AP1"]["github"], int,
                              records["AP1"])

    def test_state_action_sets_and_removes_the_in_progress_label(self):
        """Vorbedingung: lokales Ticket GH-101, Issues-Sync aktiv.
        Aktion: ``issues.state`` mit ``in-progress`` und danach ``open``.
        Erwartung: PATCH setzt/entfernt das In-Progress-Label; ``open`` setzt
        das Ready-Label (GH-47: sonst würde der nächste Sync auf draft
        zurücksetzen); der lokale Speicherzustand wechselt auf ``in-progress``
        und zurueck auf ``open``.
        Fehlerfall: Label und lokaler Zustand laufen auseinander oder Ready
        fehlt nach ``open``.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Remote open", github=101)])

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "in-progress"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])
        patches = self.server.calls("PATCH")
        self.assertEqual(1, len(patches), patches)
        self.assertIn("in-progress",
                      patches[0]["body"].get("labels") or [], patches)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "open"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        patches = self.server.calls("PATCH")
        self.assertEqual(2, len(patches), patches)
        self.assertNotIn("in-progress",
                         patches[1]["body"].get("labels") or [], patches)
        self.assertIn("ready",
                      patches[1]["body"].get("labels") or [], patches)

    def test_state_action_supports_draft_and_ready(self):
        """Vorbedingung: Remote-Issue 101 traegt ``ready`` und
        ``in-progress``; lokal steht ``state=in-progress``.
        Aktion: ``issues.state`` nacheinander mit ``draft``, ``ready`` und
        ``in-progress``.
        Erwartung: draft entfernt Ready- und In-Progress-Label, ready setzt
        Ready und entfernt In-Progress, in-progress setzt In-Progress und
        laesst Ready stehen; der lokale Speicherzustand folgt sofort
        (draft -> open -> in-progress).
        Fehlerfall: Labels/Speicherzustand laufen auseinander oder Ready geht
        verloren.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"},
                                                 {"name": "in-progress"}]
        self.write_tickets([
            ticket_record("GH-101", "Remote open", github=101,
                          state="in-progress")])

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "draft"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "ready"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "in-progress"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("in-progress", labels)
        self.assertIn("ready", labels)


class TicketAddApiTest(IssuesWebFixture):
    """AK Design 9: Ticket-Anlage im verbundenen und lokalen Projekt."""

    def test_bug_type_creates_issue_and_github_block(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``type="bug"`` (B1).
        Erwartung: Issue wird mit Label ``bug`` angelegt; der Ticketspeicher
        enthaelt ``GH-<n>`` mit ``type=bug`` und ``github=<n>``.
        Fehlerfall: lokale AP-ID statt GH-Ticket oder fehlendes Label.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web bug", "description": "kaputt",
            "type": "bug"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        records = self.tickets()
        self.assertEqual(1, len(records), records)
        ident, record = next(iter(records.items()))
        self.assertRegex(ident, r"^GH-\d+$")
        self.assertEqual("Web bug", record["title"])
        self.assertEqual("kaputt", record["description"])
        self.assertEqual("bug", record["type"])
        self.assertIsInstance(record["github"], int)
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(1, len(posts), posts)
        self.assertIn("bug", posts[0]["body"].get("labels") or [], posts)

    def test_feature_type_uses_the_feature_label(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``type="feature"`` (B1).
        Erwartung: Issue mit Label ``feature``; das Speicher-Ticket hat
        ``type=feature`` (nicht ``bug``).
        Fehlerfall: Feature wird als Bug markiert oder ohne Label angelegt.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web feature", "description": "neu",
            "type": "feature"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        records = self.tickets()
        self.assertEqual(1, len(records), records)
        ident, record = next(iter(records.items()))
        self.assertRegex(ident, r"^GH-\d+$")
        self.assertEqual("Web feature", record["title"])
        self.assertEqual("feature", record["type"])
        post = self.server.by_path("POST", "/issues")[0]
        self.assertIn("feature", post["body"].get("labels") or [], post)

    def test_ticket_add_with_state_draft_creates_a_draft_ticket(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``type="bug"`` und
        ``state="draft"``.
        Erwartung: Das Issue wird OHNE Ready-Label angelegt; das Speicher-
        Ticket traegt ``state=draft``.
        Fehlerfall: Ein ausdruecklicher Entwurf wird sofort arbeitbar.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web draft", "description": "entwurf",
            "type": "bug", "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        records = self.tickets()
        ident, record = next(iter(records.items()))
        self.assertRegex(ident, r"^GH-\d+$")
        self.assertEqual("draft", record["state"])
        post = self.server.by_path("POST", "/issues")[0]
        self.assertNotIn("ready", post["body"].get("labels") or [], post)

    def test_ticket_add_defaults_to_open_and_creates_a_ready_issue(self):
        """Vorbedingung: Issues-Sync aktiv, kein ``state``-Feld im Request.
        Aktion: ``/api/ticket action=add`` ohne Typ und Zustand.
        Erwartung (GH-48/B1): Vorgabe ``state=open`` und Typ ``feature``; das
        Issue traegt das Typ- und das Ready-Label.
        Fehlerfall: Die Vorgabe ist Entwurf oder das Ready-Label fehlt.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web ready", "description": "frei"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        records = self.tickets()
        ident, record = next(iter(records.items()))
        self.assertRegex(ident, r"^GH-\d+$")
        self.assertEqual("open", record["state"])
        self.assertEqual("feature", record["type"])
        post = self.server.by_path("POST", "/issues")[0]
        labels = post["body"].get("labels") or []
        self.assertIn("ready", labels, post)
        self.assertIn("feature", labels, post)

    def test_failed_issue_creation_leaves_no_local_entry(self):
        """Vorbedingung: Issues-Sync aktiv, der Fake lehnt die Anlage ab.
        Aktion: ``/api/ticket action=add`` mit ``type="bug"``.
        Erwartung: ``ok:false``; der Ticketspeicher bleibt leer (kein GH- und
        kein AP-Ticket).
        Fehlerfall: halbfertiger lokaler Eintrag trotz GitHub-Fehler.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.fail_create = True
        before = self.tickets()

        status, data = self.ticket({
            "action": "add", "title": "Web bug", "description": "kaputt",
            "type": "bug"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertTrue(str(data.get("message") or "").strip(), data)
        self.assertEqual(before, self.tickets())

    def test_without_issue_sync_the_local_auto_id_is_kept(self):
        """Vorbedingung: GitHub verknuepft, Issues-Sync aus.
        Aktion: ``/api/ticket action=add`` mit ``draft:true``.
        Erwartung: lokales ``AP1``-Ticket im Zustand ``open``; kein REST-
        Aufruf; das Draft-Feld bleibt wirkungslos.
        Fehlerfall: Opt-out erzwingt GitHub-Issues oder eine Draft-Markierung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")

        status, data = self.ticket({
            "action": "add", "title": "Nur lokal", "description": "Text",
            "draft": True})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        records = self.tickets()
        self.assertEqual(["AP1"], list(records))
        self.assertEqual("Nur lokal", records["AP1"]["title"])
        self.assertEqual("open", records["AP1"]["state"])
        self.assertIsNone(records["AP1"]["github"])
        self.assertEqual([], self.server.calls("POST"))


# --------------------------------------------------------------- CLI-Faelle
class IssuesCliTest(unittest.TestCase):
    """AK Design 10: CLI-Aktionen mit isolierter Umgebung und Fake-REST."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "vibe"
        self.home = self.base / "home"
        self.state = self.base / "state"
        self.project = self.root / "proj"
        for path in (self.home, self.state, self.project / ".vibe"):
            path.mkdir(parents=True, exist_ok=True)
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)

    def write_env(self, **values):
        base = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": self.server.base,
        }
        base.update(values)
        (self.project / ".vibe" / "project.env").write_text(
            "".join('%s="%s"\n' % (key, value)
                    for key, value in base.items()),
            encoding="utf-8")

    def write_tickets(self, records):
        ticket_store(self.project, records)

    def tickets(self):
        return ticket_records(self.project)

    def run_cli(self, *argv):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV and not key.startswith("GIT_")}
        env.update({
            "VIBE": str(self.root),
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
        return subprocess.run(
            [sys.executable, str(CLI_ap3), "github", "proj", *argv],
            cwd=str(self.base), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=False)

    def test_issues_sync_without_opt_in_makes_no_request(self):
        """Vorbedingung: GitHub verknuepft, Issues-Sync aus.
        Aktion: ``vibe github proj issues-sync``.
        Erwartung: Exit ungleich 0 mit klarer Meldung; kein REST-Aufruf;
        der Ticketspeicher bleibt unveraendert.
        Fehlerfall: stiller Netzaufruf oder Erfolgsmeldung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets([])
        before = self.tickets()

        result = self.run_cli("issues-sync")

        output = (result.stdout + result.stderr).lower()
        self.assertNotEqual(0, result.returncode, output)
        self.assertTrue(any(word in output for word in
                            ("issue", "sync", "nicht aktiv", "deaktiviert")),
                        output)
        self.assertEqual([], self.server.requests)
        self.assertEqual(before, self.tickets())

    def test_issues_sync_pulls_a_remote_issue(self):
        """Vorbedingung: Issues-Sync aktiv, Remote hat Issue 101.
        Aktion: ``vibe github proj issues-sync``.
        Erwartung: Exit 0; der Ticketspeicher enthaelt GH-101.
        Fehlerfall: Befehl unbekannt oder ohne Wirkung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        result = self.run_cli("issues-sync")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("GH-101", self.tickets())

    def test_issues_state_sets_and_removes_the_local_status_line(self):
        """Vorbedingung: lokales Ticket GH-101, Issues-Sync aktiv.
        Aktion: ``issues-state GH-101 in-progress`` und danach ``open``.
        Erwartung: Der Speicherzustand wechselt auf ``in-progress`` und
        zurueck auf ``open``; PATCH-Aufrufe tragen bzw. entfernen das Label.
        Fehlerfall: CLI-Aktion fehlt oder der lokale Zustand bleibt stehen.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Remote open", github=101)])

        first = self.run_cli("issues-state", "GH-101", "in-progress")
        first_out = first.stdout + first.stderr
        self.assertEqual(0, first.returncode, first_out)
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])

        second = self.run_cli("issues-state", "GH-101", "open")
        second_out = second.stdout + second.stderr
        self.assertEqual(0, second.returncode, second_out)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        self.assertGreaterEqual(len(self.server.calls("PATCH")), 2)

    def test_issues_state_supports_draft_and_ready(self):
        """Vorbedingung: Remote-Issue 101 traegt ``ready`` und
        ``in-progress``; lokales Ticket GH-101.
        Aktion: ``issues-state GH-101 draft``, ``... ready`` und
        ``... in-progress``.
        Erwartung: Exit 0 je Aktion; lokaler Speicherzustand draft -> open ->
        in-progress; PATCH-Labels wie in Design 19.
        Fehlerfall: CLI kennt die neuen Zustaende nicht oder synchronisiert
        den Speicherzustand nicht.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"},
                                                 {"name": "in-progress"}]
        self.write_tickets([
            ticket_record("GH-101", "Remote open", github=101)])

        draft = self.run_cli("issues-state", "GH-101", "draft")
        self.assertEqual(0, draft.returncode, draft.stdout + draft.stderr)
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        ready = self.run_cli("issues-state", "GH-101", "ready")
        self.assertEqual(0, ready.returncode, ready.stdout + ready.stderr)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        progress = self.run_cli("issues-state", "GH-101", "in-progress")
        self.assertEqual(0, progress.returncode,
                         progress.stdout + progress.stderr)
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("in-progress", labels)
        self.assertIn("ready", labels)


# --------------------------------------------------------- Nova-Oberflaeche
class NovaIssuesSurfaceTest(unittest.TestCase):
    """AK Design 11: Struktur der Nova-Oberflaeche (kein Browser noetig)."""

    @classmethod
    def setUpClass(cls):
        cls.text = NOVA.read_text(encoding="utf-8")

    def test_state_helpers_know_in_progress(self):
        """Vorbedingung: ``nova-project.js`` mit Zustandshelfer und Karte.
        Aktion: ``nvpStateLabel`` und die Zustands-Pille der Karte pruefen.
        Erwartung (F34): Ein In-Progress-Zustand wird mit „In Progress“
        beschriftet und als gelbe Pille (``nv-warn``) an der Karte dargestellt;
        die fruehere Board-Spaltenabbildung existiert nicht mehr.
        Fehlerfall: In Progress faellt auf „offen“ zurueck.
        """
        label = js_region(self.text, "function nvpStateLabel(")
        card = js_region(self.text, "function nvpTicketCard(")
        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertRegex(label, r"(?i)in[ _-]?progress")
        self.assertIn("data-nv-state", card)
        self.assertRegex(card, r"(?i)in[ _-]?progress")
        self.assertRegex(card, r"nv-warn")
        self.assertNotIn("nvpStateColumn", self.text,
                         "Die entfernte Board-Spaltenabbildung existiert noch")

    def test_work_list_and_tiles_include_progress_without_board(self):
        """Vorbedingung: Uebersichtskacheln und Arbeit-Reiter.
        Aktion: Kacheldefinitionen, integrierte Liste und Board-Abwesenheit
        pruefen.
        Erwartung (F34): Die Uebersicht zaehlt In-Progress-Pakete; die Arbeit
        ist eine Liste ``div.nv-ticket-list[data-nv-ticket-list]`` mit
        ``nvpTicketCard``-Karten; ein Board (``.nv-board``/``nvpBoardColumn``)
        existiert nicht.
        Fehlerfall: Zustand ist nur im Parser, nicht in der Oberflaeche, oder
        das entfernte Board ist noch vorhanden.
        """
        overview = js_region(self.text, "var tiles = el('div'")
        work = js_region(self.text, "var ticketList = el('div'")
        self.assertTrue(overview, "Uebersichts-Kacheln nicht gefunden")
        self.assertIn("nvpCount(tickets", overview)
        self.assertRegex(overview, r"(?i)progress")
        self.assertTrue(work, "Integrierte Arbeitsliste nicht gefunden")
        self.assertIn("data-nv-ticket-list", work)
        self.assertIn("nvpTicketCard", work)
        self.assertIn("allItems.forEach", work)
        self.assertNotIn(".nv-board", self.text,
                         "Das entfernte Board existiert noch")
        self.assertNotIn("nvpBoardColumn", self.text,
                         "Die entfernte Board-Spalte existiert noch")

    def test_github_card_has_sync_button_and_issues_fields(self):
        """Vorbedingung: ``nvpGithubSection``.
        Aktion: Aktionen und Formularfelder pruefen.
        Erwartung (GH-47): genau ein Sync-Button ``issues-sync`` und die
        entfallenen Aktionen ``github-issues``/``github-import`` sowie der
        Label-Filter der Issues-Sektion fehlen; Schalter
        ``github-issues-enabled``; Felder fuer In-Progress-Label und Assignee,
        die ueber ``settings`` mit ``issues_enabled``/``issues_in_progress``/
        ``issues_assignee`` gespeichert werden.
        Fehlerfall: Sync nicht ausloesbar, Altabktionen bleiben oder
        Einstellungen nicht speicherbar.
        """
        region = js_region(self.text, "function nvpGithubSection(")
        self.assertTrue(region, "nvpGithubSection nicht gefunden")
        self.assertIn("issues-sync", region)
        self.assertNotIn("'github-issues'", region)
        self.assertNotIn("'github-import'", region)
        self.assertNotIn("github-issue-label", region)
        self.assertIn("github-issues-enabled", region)
        self.assertRegex(region, r"(?i)in[ _-]?progress")
        self.assertRegex(region, r"(?i)assignee")
        self.assertIn("issues_enabled", region)
        self.assertIn("issues_in_progress", region)
        self.assertIn("issues_ready", region)
        self.assertIn("issues_assignee", region)

    def test_cards_show_draft_state_with_gray_pill_and_explanation(self):
        """Vorbedingung: ``nova-project.js``.
        Aktion: Zustandshelfer, Karten-Pille und Entwurf-Kachel pruefen.
        Erwartung (F34): Draft/Entwurf wird mit „Entwurf“ beschriftet, an der
        Karte als graue Pille ``nv-muted`` dargestellt und in der Uebersicht
        als Kachel mit ``title``-Erklaerung gefuehrt; ein Board gibt es nicht.
        Fehlerfall: Entwurf erscheint als offen oder ohne Kennzeichnung.
        """
        label = js_region(self.text, "function nvpStateLabel(")
        card = js_region(self.text, "function nvpTicketCard(")
        overview = js_region(self.text, "var tiles = el('div'")
        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertTrue(overview, "Uebersichts-Kacheln nicht gefunden")
        self.assertRegex(label, r"(?i)draft|entwurf")
        self.assertRegex(card, r"(?i)draft|entwurf")
        self.assertRegex(card, r"nv-muted")
        self.assertIn("data-nv-state", card)
        self.assertRegex(
            overview,
            r"\[\s*'draft'\s*,\s*nvpCount\(tickets\s*,\s*'Draft'\)")
        self.assertIn("Noch nicht freigegebene Pakete", overview)
        self.assertIn("title: tile[3]", overview,
                      "Die Entwurf-Kachel traegt keine title-Erklaerung")
        self.assertNotIn(".nv-board", self.text,
                         "Das entfernte Board existiert noch")

    def test_ticket_cards_are_generic_and_actions_live_in_the_detail_panel(self):
        """Vorbedingung: ``nvpTicketCard``/``nvpOpenTicketDetail``.
        Aktion: Karten-Hooks und Aktionen im Kontext-Panel pruefen.
        Erwartung (F34, GH-82): Eine Karte bedient alle Typen
        (``data-nv-kind``, ``data-nv-state``, Paket- oder Feedback-Hook)
        und oeffnet das Kontext-Panel; dort liegen Bearbeiten/Loeschen,
        aber kein manueller Abschluss. Die frueheren Board-Issueaktionen
        (``issues-state``) sind mit dem Board entfallen; die
        Issue-Zustands-API bleibt in den Backend-Faellen geprueft.
        Fehlerfall: Kartenaktionen sind nicht erreichbar oder das Detail
        bietet weiterhin einen Abschluss-Knopf an.
        """
        card = js_region(self.text, "function nvpTicketCard(")
        detail = js_region(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertTrue(detail, "nvpOpenTicketDetail nicht gefunden")
        self.assertIn("data-nv-kind", card)
        self.assertIn("data-nv-state", card)
        self.assertIn("data-nv-ticket", card)
        self.assertIn("data-nv-feedback-item", card)
        self.assertIn("nvpOpenTicketDetail", card)
        self.assertIn("ticket-edit", detail)
        self.assertIn("ticket-delete", detail)
        self.assertNotIn("ticket-close", detail)
        self.assertNotIn("package-close", detail)
        self.assertNotIn("nvpConfirmClose", detail)
        self.assertNotIn("issues-state", self.text,
                         "Board-Issueaktionen gehoeren nicht mehr zur "
                         "integrierten Liste")

    def test_ticket_form_has_draft_checkbox(self):
        """Vorbedingung: ``nvpOpenTicketForm``.
        Aktion: Formularfelder und Save-Payload pruefen.
        Erwartung: Checkbox ``data-nv-field="draft"`` mit Vorgabe gesetzt und
        ``draft`` im Request-Body.
        Fehlerfall: Entwurf ist beim Anlegen nicht waehlbar.
        """
        form = js_region(self.text, "function nvpOpenTicketForm(")
        self.assertTrue(form, "nvpOpenTicketForm nicht gefunden")
        self.assertIn("draft", form)
        self.assertRegex(form, r"(?i)checked")
        self.assertRegex(form, r"data-nv-field[^\n]*draft|draft[^\n]*data-nv-field")

    def test_in_progress_pill_uses_warn_class_and_draft_stays_muted(self):
        """Vorbedingung: ``nvpTicketCard`` mit Zustands-Pille.
        Aktion: Klassenzuweisung der Pille pruefen.
        Erwartung: ``In Progress`` erhaelt ``nv-warn`` (gelb) wie
        ``WARTET AUF MERGE``; ``Draft`` erhaelt weiterhin ``nv-muted``.
        Fehlerfall: In Progress faellt auf das neutrale Pillen-Grau zurueck.
        """
        card = js_region(self.text, "function nvpTicketCard(")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        warn_lines = [line for line in card.splitlines() if "nv-warn" in line]
        self.assertTrue(warn_lines, card)
        self.assertTrue(any("In Progress" in line for line in warn_lines),
                        "In Progress erhaelt kein nv-warn: " + repr(warn_lines))
        muted_lines = [line for line in card.splitlines()
                       if "nv-muted" in line]
        self.assertTrue(any("Draft" in line for line in muted_lines),
                        "Draft erhaelt kein nv-muted: " + repr(muted_lines))

    def test_legacy_gh_package_cards_have_no_manual_close_action(self):
        """Vorbedingung: Paketkarte mit ID ``GH-<n>`` ohne
        ``GitHub: #n``-Zeile (Legacy-Import) im Zustand BLOCKIERT/WARTET.
        Aktion: Detailregion auf Abschluss-Steuerelemente pruefen.
        Erwartung (GH-82): Unabhaengig von GitHub-Referenz und Zustand gibt
        es im Detail keinen „Paket abschliessen“-Knopf; Abschlüsse laufen
        ausschließlich über den Läufer. Board-Issueaktionen entfallen mit
        dem Board.
        Fehlerfall: Legacy-GH-Bloecke bieten weiterhin einen manuellen
        Abschluss an.
        """
        detail = js_region(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(detail, "nvpOpenTicketDetail nicht gefunden")
        self.assertNotIn("package-close", detail)
        self.assertNotIn("ticket-close", detail)
        self.assertNotIn("issues-state", self.text,
                         "Board-Issueaktionen gehoeren nicht mehr zur "
                         "integrierten Liste")

    def test_ticket_form_offers_one_type_field_for_bug_and_feature(self):
        """Vorbedingung: ``nvpOpenTicketForm``.
        Aktion: Typauswahl im Anlageformular pruefen.
        Erwartung (B1): genau ein Feld ``data-nv-field`` ``ticket-type`` mit
        Bug, Feature und Feedback; die fruehere Kategorieauswahl entfaellt.
        Fehlerfall: Typ und Kategorie werden weiterhin doppelt angeboten.

        Die frueheren ``issues_enabled``-Assertions aus AP3/F33 (Marker
        ``var issuesEnabled = !!(data.github...`` im Arbeitsbereich) waren am
        Branchpunkt nie erfuellt: Der Marker existierte im Ist-Code nicht, es
        gab nur die Settings-Checkbox. Sie sind ein vorbestehend roter,
        funktionsloser Vertrag und entfallen mit B1.
        """
        form = js_region(self.text, "function nvpOpenTicketForm(")
        self.assertTrue(form, "nvpOpenTicketForm nicht gefunden")
        self.assertIn("ticket-type", form)
        self.assertNotIn("category", form,
                         "Die ueberlappende Kategorieauswahl existiert weiterhin")
        self.assertRegex(form, r"(?i)bug")
        self.assertRegex(form, r"(?i)feature")
        self.assertRegex(form, r"(?i)feedback")


# ===========================================================================
# Vertragstests für Issue-Löschen/Sync und Text-Sync (Backend)
# ===========================================================================

import json
import sys
import unittest
from pathlib import Path

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_packages  # noqa: E402
import vibe_tickets  # noqa: E402


STAT_KEYS = {
    "created", "updated", "closed", "pushed",
    "text_pushed", "text_pulled", "conflicts", "closed_remote",
}


class Gh47Case(GithubCase):
    """Isolierte Umgebung mit Fake-REST und Ticketspeicher-Helfern."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer(issues=[]).start()
        self.addCleanup(self.server.close)

    # ---------------------------------------------------------- Speicher
    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    def write_document(self, project, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        path = project / ".vibe" / "tickets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
        return path

    def read_document(self, project):
        return json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))

    def records(self, project):
        return {item["id"]: item for item in self.read_document(project)["tickets"]}

    def deletions(self, project):
        return list(self.read_document(project).get("github_deletions") or [])

    def sync(self, project):
        return vibe_packages_issues_module().sync_issues(
            str(project), self.config_for(project))

    def project(self, name="proj"):
        return self.make_project(name=name, env_text=self.issues_env(self.server))


def vibe_packages_issues_module():
    if "gh47_issues" not in _CACHE:
        _CACHE["gh47_issues"] = load_module(
            REPO / "bin" / "vibe_issues.py", "vibe_issues_gh47_under_test")
    return _CACHE["gh47_issues"]


class StatsContractTest(Gh47Case):
    """Statistikvertrag: vier bestehende plus vier neue Zähler."""

    def test_sync_statistics_use_the_contract_keys(self):
        """Vor: Remote-Ready-Issue. Aktion: sync.
        Erwartet: genau die acht Vertragsschlüssel, alle ganzzahlig."""
        self.server.httpd.issues[:] = [
            issue(201, "Titel", labels=["ready"], body="Beschreibung")]
        project = self.project()

        stats = self.sync(project)

        self.assertEqual(STAT_KEYS, set(stats), stats)
        for key in STAT_KEYS:
            self.assertIsInstance(stats[key], int, (key, stats))


class TombstoneSyncTest(Gh47Case):
    """q8907138c500b: Tombstones verhindern Wiederbelegung und werden
    nachgearbeitet, ohne den Gesamtsync abzubrechen."""

    def test_failed_close_keeps_tombstone_and_does_not_recreate_the_issue(self):
        """Vor: Remote 101 offen (PATCH scheitert), 102 ready; Tombstone 101.
        Aktion: sync. Erwartet: kein GH-101, GH-102 entsteht, Tombstone bleibt,
        closed_remote 0; der übrige Pull läuft weiter."""
        self.server.httpd.issues[:] = [
            issue(101, "Gelöscht lokal", labels=["ready"], body="x"),
            issue(102, "Neu", labels=["ready"], body="y"),
        ]
        self.server.httpd.fail_patch_numbers.add(101)
        project = self.project()
        self.write_document(project, [], deletions=[101])

        stats = self.sync(project)

        self.assertNotIn("GH-101", self.records(project))
        self.assertIn("GH-102", self.records(project))
        self.assertEqual([101], self.deletions(project))
        self.assertEqual(0, stats["closed_remote"], stats)
        self.assertTrue(self.server.by_path("PATCH", "/issues/101"),
                        self.server.requests)

    def test_successful_retry_closes_the_issue_and_drops_the_tombstone(self):
        """Vor: Remote 101 offen, Tombstone 101. Aktion: sync.
        Erwartet: Issue 101 geschlossen, Tombstone entfernt, kein GH-101,
        closed_remote 1."""
        self.server.httpd.issues[:] = [
            issue(101, "Gelöscht lokal", labels=["ready"], body="x")]
        project = self.project()
        self.write_document(project, [], deletions=[101])

        stats = self.sync(project)

        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        self.assertEqual([], self.deletions(project))
        self.assertNotIn("GH-101", self.records(project))
        self.assertEqual(1, stats["closed_remote"], stats)

    def test_tombstone_drops_for_already_closed_or_missing_issues(self):
        """Vor: Tombstones 103 (remote geschlossen) und 999 (fehlt).
        Aktion: sync. Erwartet: beide Einträge entfernt, kein Ticket, kein
        Abbruch."""
        self.server.httpd.issues[:] = [
            issue(103, "Bereits zu", state="closed", body="z")]
        project = self.project()
        self.write_document(project, [], deletions=[103, 999])

        self.sync(project)

        self.assertEqual([], self.deletions(project))
        self.assertNotIn("GH-103", self.records(project))


class TextSyncTest(Gh47Case):
    """q9a10d0cf6e7f: bidirektionaler Text-Sync mit lokalem Vorrang."""

    def seed_ready(self, number=201, title="Titel", body="Beschreibung"):
        self.server.httpd.issues[:] = [
            issue(number, title, labels=["ready"], body=body)]

    def test_pull_creation_sets_a_gh_text_baseline(self):
        """Vor: Remote-Ready-Issue 201. Aktion: sync.
        Erwartet: GH-201 trägt ein nichtleeres ``gh_text``."""
        self.seed_ready()
        project = self.project()

        self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertIsInstance(record.get("gh_text"), str, record)
        self.assertTrue(record["gh_text"], record)

    def test_local_text_change_is_pushed_only_once(self):
        """Vor: Baseline nach Pull; danach lokaler Titel/Beschreibung neu.
        Aktion: sync zweimal. Erwartet: PATCH mit lokalem Titel/Body,
        text_pushed 1, gh_text aktualisiert; zweiter Lauf ohne PATCH."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        before_hash = self.records(project)["GH-201"]["gh_text"]
        vibe_tickets.update(str(project), "GH-201",
                            title="Lokal neu", description="Lokaler Body")
        patches_before = len(self.server.by_path("PATCH", "/issues/201"))

        stats = self.sync(project)

        patches = self.server.by_path("PATCH", "/issues/201")
        self.assertEqual(patches_before + 1, len(patches), patches)
        self.assertEqual("Lokal neu", patches[-1]["body"].get("title"))
        self.assertEqual("Lokaler Body", patches[-1]["body"].get("body"))
        self.assertEqual("Lokal neu", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["text_pushed"], stats)
        self.assertEqual(0, stats["conflicts"], stats)
        self.assertNotEqual(before_hash,
                            self.records(project)["GH-201"]["gh_text"])

        again = self.sync(project)
        self.assertEqual(len(patches), len(self.server.by_path("PATCH",
                                                               "/issues/201")))
        self.assertEqual(0, again["text_pushed"], again)

    def test_remote_text_change_is_pulled_including_the_description(self):
        """Vor: Baseline; danach Remote-Titel/-Beschreibung neu, lokal unverändert.
        Aktion: sync. Erwartet: lokaler Titel UND Beschreibung übernommen,
        text_pulled 1, kein PATCH."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        self.server.httpd.issues[0]["title"] = "Remote neu"
        self.server.httpd.issues[0]["body"] = "Remote Body"

        stats = self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertEqual("Remote neu", record["title"])
        self.assertEqual("Remote Body", record["description"])
        self.assertEqual(1, stats["text_pulled"], stats)
        self.assertFalse(self.server.by_path("PATCH", "/issues/201"))

    def test_conflict_keeps_local_text_counts_it_and_continues(self):
        """Vor: Baseline; danach beide Seiten geändert, dazu neues Remote-Issue.
        Aktion: sync. Erwartet: lokale Fassung bleibt und wird gepusht,
        conflicts 1, GH-202 entsteht (Sync bricht nicht ab)."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        vibe_tickets.update(str(project), "GH-201",
                            title="Lokal gewinnt", description="Lokal Body")
        self.server.httpd.issues[0]["title"] = "Remote anders"
        self.server.httpd.issues[0]["body"] = "Remote anders Body"
        self.server.httpd.issues.append(
            issue(202, "Zweites", labels=["ready"], body="zwei"))

        stats = self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertEqual("Lokal gewinnt", record["title"])
        self.assertEqual("Lokal Body", record["description"])
        self.assertEqual("Lokal gewinnt", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["conflicts"], stats)
        self.assertIn("GH-202", self.records(project))

    def test_missing_baseline_with_different_texts_is_a_conflict(self):
        """Vor: lokales Ticket mit github=203 und abweichendem Text, kein
        gh_text; Remote anders. Aktion: sync.
        Erwartet: lokale Fassung gewinnt und wird gepusht, conflicts 1."""
        self.server.httpd.issues[:] = [
            issue(203, "Remote", labels=["ready"], body="Remote Body")]
        project = self.project()
        self.write_document(project, [
            ticket_record("AP1", "Lokal", github=203,
                          description="Lokaler Body")])

        stats = self.sync(project)

        record = self.records(project)["AP1"]
        self.assertEqual("Lokal", record["title"])
        self.assertEqual("Lokaler Body", record["description"])
        self.assertEqual("Lokal", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["conflicts"], stats)

    def test_missing_baseline_with_equal_texts_adopts_without_push(self):
        """Vor: gleicher Text beidseitig, aber kein gh_text. Aktion: sync.
        Erwartet: gh_text wird gesetzt, kein PATCH/Text-Push, conflicts 0."""
        self.seed_ready()
        project = self.project()
        self.write_document(project, [
            ticket_record("AP1", "Titel", github=201,
                          description="Beschreibung")])

        stats = self.sync(project)

        self.assertFalse(self.server.by_path("PATCH", "/issues/201"))
        self.assertEqual(0, stats["text_pushed"], stats)
        self.assertEqual(0, stats["conflicts"], stats)
        self.assertTrue(self.records(project)["AP1"]["gh_text"])

    def test_done_ticket_text_is_not_synced_in_either_direction(self):
        """Vor: erledigtes GH-202 mit altem Text, Remote geändert; neues
        Ready-Issue. Aktion: sync. Erwartet: GH-202 bleibt textstabil, kein
        PATCH an 202; GH-201 entsteht."""
        self.server.httpd.issues[:] = [
            issue(201, "Neu", labels=["ready"], body="neu"),
            issue(202, "Remote neu", labels=["ready"], body="Remote Body"),
        ]
        project = self.project()
        self.write_document(project, [
            ticket_record("GH-202", "Fertig", state="done", github=202,
                          commit="abcdef1", test="test_gh47",
                          description="Alt")])

        self.sync(project)

        record = self.records(project)["GH-202"]
        self.assertEqual("Fertig", record["title"])
        self.assertEqual("Alt", record["description"])
        self.assertFalse(self.server.by_path("PATCH", "/issues/202"))
        self.assertIn("GH-201", self.records(project))


class StorePreservationTest(Gh47Case):
    """Speicherhaltung für gh_text und Tombstones."""

    def test_gh_text_survives_a_ticket_update(self):
        """Vor: Ticket mit gh_text. Aktion: Titel ändern.
        Erwartet: gh_text bleibt erhalten (normalize bewahrt unbekannte
        Felder)."""
        project = self.make_project()
        vibe_tickets.add(str(project), "Titel", tid="AP1",
                         extra={"gh_text": "abc123"})

        vibe_tickets.update(str(project), "AP1", title="Neuer Titel")

        self.assertEqual("abc123", self.records(project)["AP1"]["gh_text"])

    def test_github_deletions_survives_ticket_writes(self):
        """Vor: Dokument mit github_deletions [7]. Aktion: Ticket ändern und
        neues anlegen. Erwartet: der Dokumentschlüssel bleibt erhalten."""
        project = self.make_project()
        self.write_document(project, [ticket_record("AP1", "Alt")],
                            deletions=[7])

        vibe_tickets.update(str(project), "AP1", title="Neu")
        vibe_tickets.add(str(project), "Zusatz", tid="AP2")

        self.assertEqual([7], self.deletions(project))
        self.assertEqual({"AP1", "AP2"}, set(self.records(project)))


class IssueStateFixTest(Gh47Case):
    """D: open setzt das Ready-Label statt beide Labels zu entfernen."""

    def test_open_state_sets_ready_label_and_survives_the_next_sync(self):
        """Vor: GH-101, Remote trägt in-progress. Aktion: set_issue_state open,
        dann sync. Erwartet: PATCH setzt ready/entfernt in-progress; der Sync
        setzt das Ticket nicht auf draft zurück."""
        self.server.httpd.issues[:] = [
            issue(101, "Offen", labels=["in-progress"], body="x")]
        project = self.project()
        self.write_document(project, [
            ticket_record("GH-101", "Offen", github=101, state="in-progress")])

        issue_module = vibe_packages_issues_module()
        issue_module.set_issue_state(str(project), self.config_for(project),
                                     "GH-101", "open")

        labels = self.server.by_path("PATCH", "/issues/101")[-1]["body"].get(
            "labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)
        self.assertEqual("open", self.records(project)["GH-101"]["state"])

        self.sync(project)
        self.assertEqual("open", self.records(project)["GH-101"]["state"])


class DraftRunDisciplineTest(Gh47Case):
    """D: nur lauffähige Tickets werden gewählt; Drafts sind sichtbar, aber
    nicht startbar."""

    def select(self, project, **kwargs):
        return vibe_packages.select_package(
            project, state_path=str(self.base / "next.json"), **kwargs)

    def test_only_open_and_in_progress_are_eligible(self):
        """Vor: Draft, blocked, waiting-merge, open und in-progress.
        Aktion: select zweimal. Erwartet: erst open, dann in-progress; nie
        draft/blocked/waiting."""
        project = self.make_project()
        self.write_document(project, [
            ticket_record("D1", "Entwurf", state="draft"),
            ticket_record("B1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("W1", "Wartet", state="waiting-merge"),
            ticket_record("T1", "Offen"),
            ticket_record("P1", "Läuft", state="in-progress"),
        ])

        first = self.select(project)
        second = self.select(project, skip={first["id"]})

        self.assertEqual("T1", first["id"])
        self.assertEqual("P1", second["id"])

    def test_order_and_priority_fallbacks_skip_drafts(self):
        """Vor: Draft D1 in PACKAGE_ORDER und mit P0; offenes T2.
        Aktion: select. Erwartet: T2 (beide Ordnungen überspringen den
        Entwurf)."""
        project = self.make_project(
            env_text='TYPE=generic\nPACKAGE_ORDER="D1 T2"\n')
        self.write_document(project, [
            ticket_record("D1", "Entwurf", state="draft", priority="P0"),
            ticket_record("T2", "Offen"),
        ])

        self.assertEqual("T2", self.select(project)["id"])

    def test_connected_pull_maps_missing_ready_label_to_draft(self):
        """Vor: Remote 101 ohne Ready-Label, 102 mit Ready.
        Aktion: sync, dann select. Erwartet: 101 draft, 102 open; nur GH-102
        ist wählbar."""
        self.server.httpd.issues[:] = [
            issue(101, "Ohne Ready", labels=[], body="a"),
            issue(102, "Mit Ready", labels=["ready"], body="b"),
        ]
        project = self.project()

        self.sync(project)

        records = self.records(project)
        self.assertEqual("draft", records["GH-101"]["state"])
        self.assertEqual("open", records["GH-102"]["state"])
        self.assertEqual("GH-102", self.select(project)["id"])


# ===========================================================================
# Vertragstests für Web-API, CLI und Oberflächenstruktur
# ===========================================================================

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_gh47 = REPO / "bin" / "vibe"
CLASSIC = REPO / "bin" / "web" / "app.js"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


class Gh47WebCase(IssuesWebFixture):
    """Dashboard-Fixture mit Dokumentzugriff und Feedback-POST."""

    def write_document(self, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        path = self.project / ".vibe" / "tickets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
        return path

    def read_document(self):
        return json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))

    def deletions(self):
        return list(self.read_document().get("github_deletions") or [])

    def feedback(self, body):
        status, text, _headers = self.post(
            "/api/feedback", dict({"name": "proj"}, **body))
        return status, json.loads(text)

    def patches(self, suffix=None):
        calls = self.server.calls("PATCH")
        if suffix is None:
            return calls
        return [call for call in calls
                if call["path"].rstrip("/").endswith(suffix)]


class LegacyGithubActionsRemovedTest(Gh47WebCase):
    """q6cbba05d8ca9: die getrennten Aktionen sind aus der Web-API entfernt."""

    def test_action_issues_is_unknown_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``/api/github action=issues``.
        Erwartet: ok false, Meldung „Unbekannte Aktion“, kein REST-Aufruf."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "issues"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertRegex(str(data.get("message") or ""), r"(?i)unbekannt")
        self.assertEqual([], self.server.requests)

    def test_action_import_is_unknown_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``/api/github action=import``.
        Erwartet: ok false, Meldung „Unbekannte Aktion“, kein REST-Aufruf."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "import"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertRegex(str(data.get("message") or ""), r"(?i)unbekannt")
        self.assertEqual([], self.server.requests)

    def test_issues_sync_and_state_remain_available(self):
        """Vor: Issues-Sync aktiv, Remote 101. Aktion: ``issues.sync``.
        Erwartet: ok, GH-101 entsteht; die Sync-Aktion bleibt erreichbar."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("GH-101", self.tickets())


class ConnectedDeleteApiTest(Gh47WebCase):
    """q8907138c500b: verbundenes Löschen über /api/ticket und /api/feedback."""

    def test_delete_without_github_reference_is_local_only(self):
        """Vor: Issues-Sync aktiv, AP1 ohne GitHub-Bezug.
        Aktion: ``/api/ticket delete``. Erwartet: ok, Ticket weg, kein PATCH,
        keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("AP1", "Nur lokal")])

        status, data = self.ticket({"action": "delete", "id": "AP1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("AP1", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertEqual([], self.deletions())

    def test_successful_close_deletes_locally_and_names_the_issue(self):
        """Vor: GH-101 mit github=101. Aktion: ``/api/ticket delete``.
        Erwartet: ok, Ticket weg, PATCH state=closed, Meldung nennt #101 und
        „geschlossen“, keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("GH-101", "Verknüpft", github=101)])

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("GH-101", self.tickets())
        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        patches = self.patches("/issues/101")
        self.assertEqual(1, len(patches), patches)
        self.assertEqual("closed", patches[0]["body"].get("state"))
        message = str(data.get("message") or "")
        self.assertIn("101", message, data)
        self.assertRegex(message, r"(?i)geschlossen")
        self.assertEqual([], self.deletions())

    def test_failed_close_deletes_locally_and_records_a_tombstone(self):
        """Vor: GH-101, PATCH scheitert mit 403. Aktion: delete.
        Erwartet: ok nicht false, Ticket weg, 101 in ``github_deletions``,
        Meldung nennt Fehlschlag + erneuten Sync-Versuch, kein Token."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("GH-101", "Verknüpft", github=101)])
        self.server.httpd.fail_patch_numbers.add(101)

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertIsNot(data.get("ok"), False, data)
        self.assertNotIn("GH-101", self.tickets())
        self.assertEqual([101], self.deletions())
        message = str(data.get("message") or "")
        self.assertRegex(message, r"(?i)fehl|konnte nicht|nicht geschlossen",
                         data)
        self.assertIn("erneut", message.lower(), data)
        self.assertNotIn(FAKE_TOKEN, message, data)

    def test_failed_close_tombstones_are_deduplicated(self):
        """Vor: GH-101 und AP1 zeigen auf Issue 101; PATCH scheitert.
        Aktion: beide löschen. Erwartet: ``github_deletions`` enthält 101
        genau einmal."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Verknüpft", github=101),
            ticket_record("AP1", "Zweiter Bezug", github=101),
        ])
        self.server.httpd.fail_patch_numbers.add(101)

        self.ticket({"action": "delete", "id": "GH-101"})
        self.ticket({"action": "delete", "id": "AP1"})

        self.assertEqual([101], self.deletions())
        self.assertNotIn("GH-101", self.tickets())
        self.assertNotIn("AP1", self.tickets())

    def test_done_ticket_is_refused_before_any_rest_call(self):
        """Vor: erledigtes GH-101 mit GitHub-Bezug. Aktion: delete.
        Erwartet: ok false, Nachweis-Meldung, Ticket bleibt, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Fertig", state="done", github=101,
                          commit="abcdef1", test="test_gh47")])

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertIn("GH-101", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertRegex(str(data.get("message") or ""), r"(?i)erledigt|nachweis")

    def test_feedback_delete_uses_the_connected_path(self):
        """Vor: Bug B1 mit github=101. Aktion: ``/api/feedback delete``.
        Erwartet: Issue geschlossen, B1 lokal weg, PATCH state=closed."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "delete", "id": "B1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("B1", self.tickets())
        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        self.assertEqual(1, len(self.patches("/issues/101")))

    def test_feedback_delete_without_issue_sync_stays_local(self):
        """Vor: Issues-Sync aus, B1 mit github=101. Aktion: feedback delete.
        Erwartet: lokal gelöscht, kein PATCH, keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "delete", "id": "B1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("B1", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertEqual([], self.deletions())


class TicketStateApiTest(Gh47WebCase):
    """D: Zustandssteuerung über /api/ticket und /api/feedback."""

    def test_state_without_issue_sync_is_local_only(self):
        """Vor: Issues-Sync aus, AP1 offen. Aktion: state=draft.
        Erwartet: lokal draft, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets([ticket_record("AP1", "Offen")])

        status, data = self.ticket({"action": "state", "id": "AP1",
                                    "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["AP1"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))

    def test_state_with_github_reference_patches_labels_and_local_state(self):
        """Vor: Issues-Sync aktiv, GH-101. Aktion: state draft, dann open.
        Erwartet: draft entfernt Ready/In-Progress lokal+remote; open setzt
        Ready (GH-47-Fix) und lokal offen."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [
            {"name": "ready"}, {"name": "in-progress"}]
        self.write_tickets([
            ticket_record("GH-101", "Offen", github=101,
                          state="in-progress")])

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "draft"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Ticket")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "open"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Ticket")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

    def test_state_with_issue_sync_but_no_github_reference_stays_local(self):
        """Vor: Issues-Sync aktiv, AP1 offen ohne GitHub-Bezug. Aktion:
        state=draft (GH-82: in-progress ist dem Läufer vorbehalten).
        Erwartet: ok, lokal draft, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("AP1", "Offen")])

        status, data = self.ticket({"action": "state", "id": "AP1",
                                    "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["AP1"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))

    def test_feedback_state_with_github_reference_patches_labels(self):
        """Vor: Issues-Sync aktiv, B1 mit github=101. Aktion: feedback state
        draft. Erwartet: PATCH entfernt Ready/In-Progress, B1 lokal draft."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"}]
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "state", "id": "B1",
                                      "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["B1"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Feedback")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)

    def test_done_ticket_state_is_refused_without_rest(self):
        """Vor: erledigtes GH-101. Aktion: state=open.
        Erwartet: ok false, Zustand bleibt done, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Fertig", state="done", github=101,
                          commit="abcdef1", test="test_gh47")])

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "open"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertEqual("done", self.tickets()["GH-101"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))


class SyncMessageTest(Gh47WebCase):
    """q9a10d0cf6e7f: Statistik und Web-Meldung nennen die neuen Anteile."""

    def test_conflict_is_reported_in_message_and_statistics(self):
        """Vor: Baseline für GH-201, danach beide Seiten geändert.
        Aktion: issues.sync. Erwartet: Meldung nennt Konflikt; Statistik hat
        die acht Vertragsschlüssel mit conflicts=1; lokale Fassung bleibt."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[:] = [
            issue(201, "Titel", labels=["ready"], body="Beschreibung")]
        self.write_tickets([])
        first = self.github({"action": "issues.sync"})
        self.assertTrue(first[1].get("ok"), first)

        import vibe_tickets
        vibe_tickets.update(str(self.project), "GH-201",
                            title="Lokal gewinnt", description="Lokal Body")
        self.server.httpd.issues[0]["title"] = "Remote anders"
        self.server.httpd.issues[0]["body"] = "Remote anders Body"

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("GH-201", self.tickets())
        self.assertEqual("Lokal gewinnt", self.tickets()["GH-201"]["title"])
        message = str(data.get("message") or "")
        self.assertRegex(message, r"(?i)konflikt", data)
        stats = data.get("stats") or {}
        self.assertEqual(STAT_KEYS, set(stats), data)
        self.assertEqual(1, stats.get("conflicts"), data)


class IssuesCliCase(unittest.TestCase):
    """CLI mit isolierten Pfaden und Loopback-REST-Fake."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "vibe"
        self.home = self.base / "home"
        self.state = self.base / "state"
        self.project = self.root / "proj"
        for path in (self.home, self.state, self.project / ".vibe"):
            path.mkdir(parents=True, exist_ok=True)
        self.server = FakeIssuesServer(issues=[]).start()
        self.addCleanup(self.server.close)

    def write_env(self, **values):
        base = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": self.server.base,
        }
        base.update(values)
        (self.project / ".vibe" / "project.env").write_text(
            "".join('%s="%s"\n' % (key, value)
                    for key, value in base.items()),
            encoding="utf-8")

    def write_document(self, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_document(self):
        return json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))

    def tickets(self):
        return {item["id"]: item
                for item in self.read_document()["tickets"]}

    def run_cli(self, *argv):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV and not key.startswith("GIT_")}
        env.update({
            "VIBE": str(self.root),
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
        return subprocess.run(
            [sys.executable, str(CLI_gh47), "github", "proj", *argv],
            cwd=str(self.base), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=False)


class CliLegacyActionsTest(IssuesCliCase):
    """q6cbba05d8ca9: ``issues``/``issues-import`` sind aus der CLI entfernt."""

    def test_cli_issues_is_removed_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``vibe github proj issues``.
        Erwartet: Exit != 0, verständliche „unbekannt“-Meldung, kein REST."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_document([])

        result = self.run_cli("issues")

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output, r"(?i)unbekannt|aktion")
        self.assertEqual([], self.server.requests)

    def test_cli_issues_import_is_removed_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``issues-import``.
        Erwartet: Exit != 0, „unbekannt“-Meldung, kein REST."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_document([])

        result = self.run_cli("issues-import")

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output, r"(?i)unbekannt|aktion")
        self.assertEqual([], self.server.requests)

    def test_usage_no_longer_offers_issues_or_import(self):
        """Vor: ``bin/vibe``. Aktion: Quelltext/Docstring prüfen.
        Erwartet: ``issues-import`` kommt nicht mehr vor; ``issues-sync`` und
        ``issues-state`` bleiben dokumentiert."""
        source = CLI_gh47.read_text(encoding="utf-8")

        self.assertNotIn("issues-import", source)
        self.assertIn("issues-sync", source)
        self.assertIn("issues-state", source)


class CliSyncMessageTest(IssuesCliCase):
    """q9a10d0cf6e7f: CLI-Meldung nennt Text- und Konfliktanteile."""

    def test_sync_output_mentions_text_upload_and_conflicts(self):
        """Vor: zwei Baseline-Tickets; danach lokale Textänderung (201) und
        beidseitige Änderung (202). Aktion: issues-sync.
        Erwartet: Exit 0; Ausgabe nennt Text/hochgeladen und Konflikt."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[:] = [
            issue(201, "Titel A", labels=["ready"], body="Body A"),
            issue(202, "Titel B", labels=["ready"], body="Body B"),
        ]
        self.write_document([])
        first = self.run_cli("issues-sync")
        self.assertEqual(0, first.returncode,
                         first.stdout + first.stderr)
        self.assertEqual({"GH-201", "GH-202"}, set(self.tickets()))

        import vibe_tickets
        vibe_tickets.update(str(self.project), "GH-201",
                            title="Lokal A", description="Lokal A Body")
        vibe_tickets.update(str(self.project), "GH-202",
                            title="Lokal B", description="Lokal B Body")
        self.server.httpd.issues[1]["title"] = "Remote B"
        self.server.httpd.issues[1]["body"] = "Remote B Body"

        second = self.run_cli("issues-sync")

        output = (second.stdout + second.stderr).lower()
        self.assertEqual(0, second.returncode, output)
        self.assertIn("text", output)
        self.assertIn("hochgeladen", output)
        self.assertIn("konflikt", output)


class SurfaceStructureTest(unittest.TestCase):
    """q6cbba05d8ca9: genau ein Sync, keine Laden/Import/Filtreste."""

    @classmethod
    def setUpClass(cls):
        cls.nova = NOVA.read_text(encoding="utf-8")
        cls.classic = CLASSIC.read_text(encoding="utf-8")

    def test_nova_issues_section_has_exactly_one_sync_and_no_legacy(self):
        """Vor: ``nvpGithubSection``. Aktion: Aktionen/Felder prüfen.
        Erwartet: genau ein ``issues-sync``, kein ``github-issues``/
        ``github-import``, kein ``github-issue-label``; Erklärung nennt
        Synchronisieren, Ready/Entwurf und Schließen."""
        region = js_region(self.nova, "function nvpGithubSection(")
        self.assertTrue(region, "nvpGithubSection nicht gefunden")
        self.assertEqual(1, region.count("issues-sync"), region)
        self.assertNotIn("'github-issues'", region)
        self.assertNotIn("'github-import'", region)
        self.assertNotIn("github-issue-label", region)
        self.assertRegex(region, r"(?i)synchronisier")
        self.assertRegex(region, r"(?i)ready")
        self.assertRegex(region, r"(?i)entwurf|draft")
        self.assertRegex(region, r"(?i)schließ|schliess|close")

    def test_classic_issues_section_drops_load_import_and_filter(self):
        """Vor: ``app.js``. Aktion: Issues-Bedienung prüfen.
        Erwartet: kein ``action:'issues'``/``action:'import'``, keine Buttons
        „Issues laden“/„Issues importieren“, kein ``issueFilter``; ein
        Sync-Button mit ``issues.sync``."""
        self.assertNotIn("Issues laden", self.classic)
        self.assertNotIn("Issues importieren", self.classic)
        self.assertNotIn("issueFilter", self.classic)
        self.assertNotRegex(self.classic, r"action\s*:\s*'issues'")
        self.assertNotRegex(self.classic, r"action\s*:\s*'import'")
        self.assertIn("Issues synchronisieren", self.classic)
        self.assertRegex(self.classic, r"action\s*:\s*['\"]issues\.sync['\"]")

    def test_product_import_helpers_are_removed(self):
        """Vor: Produktmodule. Aktion: Attribute prüfen.
        Erwartet: ``vibe_github.import_issues_into_tickets`` fehlt,
        ``list_issues`` bleibt; ``bin/vibe`` hat keine Legacy-Liste/Import."""
        import vibe_github

        self.assertFalse(hasattr(vibe_github, "import_issues_into_tickets"))
        self.assertTrue(callable(getattr(vibe_github, "list_issues", None)))
        source = CLI_gh47.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^def github_issues\(")
        self.assertNotRegex(source, r"(?m)^def github_issues_import\(")


if __name__ == "__main__":
    unittest.main()
