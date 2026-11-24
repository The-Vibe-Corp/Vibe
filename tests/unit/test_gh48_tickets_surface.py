"""GH-48: Vertragstests für die Ticket-/Feedback-Oberflächen in ``bin/vibe``.

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` und der verbindliche
Implementierungsvertrag GH-48 (§3 Oberflächen, §6 GitHub-Ebene). Geprüft wird
die nach außen sichtbare Semantik der bisherigen Markdown-Funktionen auf dem
neuen Ticketspeicher ``.vibe/tickets.json``:

* Zeilenformen von ``ticket_items``/``feedback_items``/``open_items``
  (status, kind, completed, Anzeigezustand),
* Anlegen mit Auto-IDs und Typen, Bearbeiten/Löschen mit done-Schutz und
  Fehlermeldungen, die den Ticketspeicher statt TICKETS.md nennen,
* GitHub-Import, -Sync und Zustandsaktion auf dem Speicher,
* ``package_close`` übernimmt den Abschluss mit ``require_commit=False``.

Kein echtes GitHub und kein Netz: GitHub-REST ausschließlich gegen einen
``ThreadingHTTPServer`` auf ``127.0.0.1`` (Muster
``test_ap3_korbat_issues_backend``). Keine Modellaufrufe, keine produktiven
Pfade; ``bin/vibe`` wird mit temporärem ``VIBE``/``HOME`` geladen.

Run:

    python3 -m unittest tests.unit.test_gh48_tickets_surface -v
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
FAKE_TOKEN = "gh48-fake-token-4711"
STAMP = "2026-01-01T00:00:00+00:00"

# Variablen, die der GitHub-REST-Fake braucht bzw. die keine echten
# Zugangsdaten oder Proxys in den Test lassen dürfen.
GITHUB_ENV_KEYS = (
    "GITHUB_TOKEN", "GH_TOKEN", "http_proxy", "https_proxy", "all_proxy",
    "VIBE_GITHUB_CREDENTIAL", "GIT_TERMINAL_PROMPT", "NO_PROXY",
)


def load_cli(vibe_root):
    """Lädt ``bin/vibe`` als Modul mit vollständig temporären Pfaden."""
    with env_support.isolated_process_environment(
        VIBE=str(vibe_root),
        VIBE_NO_CONTAINER="1",
        HOME=str(Path(vibe_root) / "home"),
        VIBE_RUNTIME=str(Path(vibe_root) / "_logs"),
        VIBE_STATE=str(Path(vibe_root) / "_toolchain"),
        VIBE_STORAGE_LOCK_DIR=str(Path(vibe_root) / "locks"),
        VIBE_CONFIG_FILE=str(Path(vibe_root) / "home" / ".config" / "vibe"
                             / "config.json"),
        GITHUB_TOKEN=FAKE_TOKEN,
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_gh48_surface_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def ticket(tid, title, type="task", state="open", **extra):
    """Ticketdatensatz mit allen Vertragsfeldern."""
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


def issue(number, title, labels=(), state="open", body="", assignees=(),
          pull_request=None):
    item = {
        "number": number, "title": title, "body": body, "state": state,
        "labels": [{"name": name} for name in labels],
        "assignees": [{"login": name} for name in assignees],
    }
    if pull_request is not None:
        item["pull_request"] = pull_request
    return item


class _IssuesHandler(BaseHTTPRequestHandler):
    """Loopback-REST-Fake für Issues und Pull-Requests."""

    def log_message(self, *args):
        return

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
                items = [item for item in items
                         if item.get("state") != "closed"]
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
            self.server.next_number += 1
            number = self.server.next_number
            item = {
                "number": number,
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "state": "open",
                "labels": [{"name": name}
                           for name in payload.get("labels") or []],
                "assignees": [{"login": name}
                              for name in payload.get("assignees") or []],
            }
            self.server.issues.append(item)
            self._respond(201, item)
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
                self._respond(200, item)
                return
        self._respond(404, {"message": "Not Found"})


class FakeIssuesServer:
    def __init__(self, issues, next_number=200):
        self.requests = []
        self.issues = [dict(item) for item in issues]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _IssuesHandler)
        self.httpd.requests = self.requests
        self.httpd.issues = self.issues
        self.httpd.next_number = next_number
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

    def by_path(self, method, suffix):
        return [item for item in self.requests if item["method"] == method
                and urllib.parse.urlparse(item["path"]).path.rstrip("/")
                .endswith(suffix)]


class SurfaceCase(unittest.TestCase):
    """Temporäres Projekt mit Ticketspeicher; ``bin/vibe`` isoliert geladen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved_env = {key: os.environ.get(key) for key in GITHUB_ENV_KEYS}
        self.addCleanup(self.restore_env)
        for key in GITHUB_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update({
            "GITHUB_TOKEN": FAKE_TOKEN,
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.root = Path(self.tmp.name)
        (self.root / "home").mkdir()
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env = self.project / ".vibe" / "project.env"
        self.env.write_text("TYPE=generic\n", encoding="utf-8")
        self.store = self.project / ".vibe" / "tickets.json"
        self.cli = load_cli(self.root)

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_env(self, text):
        self.env.write_text(text, encoding="utf-8")

    def issues_env(self, server):
        self.write_env(
            "TYPE=generic\n"
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % server.base)

    def write_store(self, tickets):
        self.store.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return json.loads(self.store.read_text(encoding="utf-8"))

    def tickets(self):
        return {item["id"]: item for item in self.read_store()["tickets"]}

    def rows(self, function, name="proj"):
        return {row["id"]: row for row in function(name)}


class RowShapeTest(SurfaceCase):
    """Zeilenformen der drei Leseflächen auf dem Speicher."""

    def setUp(self):
        super().setUp()
        self.write_store([
            ticket("AP1", "Offen", priority="P1"),
            ticket("FEAT-2", "Feature", type="feature", state="in-progress"),
            ticket("AP3", "Entwurf", state="draft"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
            ticket("B1", "Bug", type="bug", github=12),
            ticket("F1", "Rückmeldung", type="feedback", state="blocked",
                   blocked_reason="wartet"),
        ])

    def test_ticket_items_read_task_and_feature_rows_from_the_store(self):
        """Vor: task/feature/done/bug/feedback im Speicher. Aktion:
        ticket_items. Erwartet: nur task/feature; Zeilenform mit id, title,
        description, state (Anzeigezustand), completed, status, github."""
        rows = self.rows(self.cli.ticket_items)

        self.assertEqual({"AP1", "FEAT-2", "AP3", "AP4"}, set(rows))
        row = rows["FEAT-2"]
        for key in ("id", "title", "description", "state", "completed",
                    "status", "github"):
            self.assertIn(key, row)
        self.assertEqual("In Progress", row["state"])
        self.assertEqual("in-progress", row["status"])
        self.assertFalse(row["completed"])
        self.assertEqual("offen", rows["AP1"]["state"])
        self.assertEqual("Draft", rows["AP3"]["state"])
        self.assertEqual("erledigt", rows["AP4"]["state"])
        self.assertTrue(rows["AP4"]["completed"])

    def test_feedback_items_read_bug_and_feedback_rows_with_kind(self):
        """Vor: Bug B1 und Feedback F1 im Speicher. Aktion: feedback_items.
        Erwartet: beide Zeilen mit kind=bug bzw. feedback; der blockierte
        Zustand erscheint als BLOCKIERT, github bleibt sichtbar."""
        rows = self.rows(self.cli.feedback_items)

        self.assertEqual({"B1", "F1"}, set(rows))
        self.assertEqual("bug", rows["B1"]["kind"])
        self.assertEqual("feedback", rows["F1"]["kind"])
        self.assertEqual(12, rows["B1"]["github"])
        self.assertEqual("BLOCKIERT", rows["F1"]["state"])
        self.assertFalse(rows["F1"]["completed"])

    def test_open_items_list_all_unfinished_tickets_in_store_order(self):
        """Vor: offen/in-progress/draft/blockiert/erledigt. Aktion: open_items.
        Erwartet: alle außer done, in Speicherreihenfolge, je (id, Titel[:60],
        Anzeigezustand)."""
        items = self.cli.open_items("proj")

        self.assertEqual(["AP1", "FEAT-2", "AP3", "B1", "F1"],
                         [item[0] for item in items])
        self.assertEqual(("AP1", "Offen", "offen"), items[0])
        self.assertEqual(("FEAT-2", "Feature", "In Progress"), items[1])
        self.assertEqual(("B1", "Bug", "offen"), items[3])
        self.assertEqual(("F1", "Rückmeldung", "BLOCKIERT"), items[4])



class MissingStoreTest(SurfaceCase):
    """Ohne Ticketspeicher liefern die Leseflächen leere Listen."""

    def test_missing_store_yields_empty_rows(self):
        """Vor: kein Ticketspeicher (kein setUp-Store). Aktion: alle
        Leseflächen. Erwartet: leere Listen statt Fehler (keine
        TICKETS.md-Pflicht)."""
        self.assertFalse(self.store.exists())

        self.assertEqual([], self.cli.ticket_items("proj"))
        self.assertEqual([], self.cli.feedback_items("proj"))
        self.assertEqual([], self.cli.open_items("proj"))


class AddTest(SurfaceCase):
    """Anlegen mit Auto-IDs, Typen und fehlendem Speicher."""

    def test_add_ticket_creates_a_missing_store_with_ap_id(self):
        """Vor: kein Speicher, kein TICKETS.md. Aktion: add_ticket ohne ID.
        Erwartet: AP1, .vibe/tickets.json wird angelegt, Ticket ist task/open."""
        tid = self.cli.add_ticket("proj", "", "Erstes Paket", "Beschreibung")

        self.assertEqual("AP1", tid)
        self.assertTrue(self.store.is_file())
        record = self.tickets()["AP1"]
        self.assertEqual("task", record["type"])
        self.assertEqual("open", record["state"])
        self.assertEqual("Erstes Paket", record["title"])
        self.assertEqual("Beschreibung", record["description"])

    def test_add_ticket_accepts_an_explicit_id_and_continues_auto_ids(self):
        """Vor: AP7 angelegt. Aktion: add_ticket ohne ID.
        Erwartet: eigene ID bleibt, die Auto-ID zählt danach weiter (AP8)."""
        self.assertEqual("AP7", self.cli.add_ticket("proj", "AP7", "Eigen"))
        self.assertEqual("AP8", self.cli.add_ticket("proj", "", "Auto"))

    def test_add_ticket_rejects_duplicate_and_invalid_ids(self):
        """Vor: AP1 existiert. Aktion: AP1 erneut bzw. ungültige ID.
        Erwartet: ValueError jeweils; der Speicher bleibt bei einem Ticket."""
        self.cli.add_ticket("proj", "AP1", "Erstes")
        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "AP1", "Doppelt")
        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "keine id", "Ungültig")
        self.assertEqual(["AP1"], list(self.tickets()))

    def test_add_feedback_and_add_bug_store_the_distinct_types(self):
        """Vor: leerer Speicher. Aktion: add_feedback, add_bug, add_feedback.
        Erwartet: F1 (feedback), B1 (bug), F2 (feedback)."""
        self.assertEqual("F1", self.cli.add_feedback("proj", "Idee", "Text"))
        self.assertEqual("B1", self.cli.add_bug("proj", "Fehler", "Text"))
        self.assertEqual("F2", self.cli.add_feedback("proj", "Noch eine"))

        records = self.tickets()
        self.assertEqual("feedback", records["F1"]["type"])
        self.assertEqual("bug", records["B1"]["type"])
        self.assertEqual("feedback", records["F2"]["type"])


class EditDeleteTest(SurfaceCase):
    """Bearbeiten/Löschen mit Nachweisschutz und Speicher-Fehlermeldungen."""

    def setUp(self):
        super().setUp()
        self.write_store([
            ticket("AP1", "Offen", description="alt"),
            ticket("AP2", "Fertig", state="done", commit="abcdef1",
                   test="test_ap2"),
            ticket("F1", "Feedback", type="feedback", description="alt"),
            ticket("B1", "Bug", type="bug"),
        ])

    def test_ticket_update_changes_only_title_and_description(self):
        """Vor: offenes AP1. Aktion: ticket_update. Erwartet: Titel und
        Beschreibung neu, Typ/Zustand unverändert."""
        self.cli.ticket_update("proj", "AP1", "Neu", "neu")

        record = self.tickets()["AP1"]
        self.assertEqual("Neu", record["title"])
        self.assertEqual("neu", record["description"])
        self.assertEqual("open", record["state"])
        self.assertEqual("task", record["type"])

    def test_done_tickets_stay_protected_against_edit_and_delete(self):
        """Vor: erledigtes AP2. Aktion: ticket_update und ticket_delete.
        Erwartet: ValueError jeweils, der Speicher bleibt unverändert."""
        before = self.store.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.ticket_update("proj", "AP2", "Neu")
        with self.assertRaises(ValueError):
            self.cli.ticket_delete("proj", "AP2")

        self.assertEqual(before, self.store.read_bytes())

    def test_feedback_update_and_delete_follow_the_same_rules(self):
        """Vor: offenes F1 und offener Bug B1. Aktion: update F1, delete B1.
        Erwartet: F1 neu, B1 entfernt, AP1/AP2 unberührt."""
        self.cli.feedback_update("proj", "F1", "Neu", "neu")
        self.cli.feedback_delete("proj", "B1")

        records = self.tickets()
        self.assertEqual("Neu", records["F1"]["title"])
        self.assertNotIn("B1", records)
        self.assertIn("AP1", records)

    def test_unknown_ticket_reports_the_ticket_store_not_the_legacy_files(self):
        """Vor: kein Ticket X9. Aktion: ticket_update/delete/feedback_update.
        Erwartet: ValueError, dessen Meldung den Ticketspeicher nennt und
        TICKETS.md/FEEDBACK.md nicht mehr adressiert."""
        for action in (
            lambda: self.cli.ticket_update("proj", "X9", "Titel"),
            lambda: self.cli.ticket_delete("proj", "X9"),
            lambda: self.cli.feedback_update("proj", "X9", "Titel"),
        ):
            with self.assertRaises(ValueError) as caught:
                action()
            message = str(caught.exception)
            self.assertIn("Ticketspeicher", message)
            self.assertNotIn("TICKETS.md", message)
            self.assertNotIn("FEEDBACK.md", message)


class GithubSurfaceTest(SurfaceCase):
    """GitHub-Import, -Sync und -Zustand schreiben in den Ticketspeicher."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer([
            issue(101, "Remote Bug", labels=["bug"], body="Body 101"),
            issue(102, "Remote Aufgabe", labels=["ready"], body="Body 102"),
            issue(104, "Nur PR", pull_request={"url": "x"}),
        ]).start()
        self.addCleanup(self.server.close)
        self.issues_env(self.server)

    def test_import_creates_gh_tickets_in_the_store(self):
        """Vor: Remote-Issues 101 (bug) und 102, ein PR. Aktion:
        github_issues_import. Erwartet: GH-101 als bug, GH-102 als task;
        der PR wird nicht zum Ticket; kein Markdown-Ledger entsteht."""
        added, seen = self.cli.github_issues_import("proj")

        self.assertEqual(2, added)
        self.assertEqual(2, seen)
        records = self.tickets()
        self.assertEqual({"GH-101", "GH-102"}, set(records))
        self.assertEqual("bug", records["GH-101"]["type"])
        self.assertEqual(101, records["GH-101"]["github"])
        self.assertEqual("task", records["GH-102"]["type"])
        self.assertFalse((self.project / "TICKETS.md").exists())

    def test_sync_pulls_states_and_pushes_open_local_tickets(self):
        """Vor: lokale Tickets AP1 (offen, ohne GitHub), GH-101 (veralteter
        Titel, offen) und GH-103 (offen, Issue geschlossen). Aktion:
        github_issues_sync. Erwartet: GH-101 Zustand aus Labels, GH-103 done,
        AP1 erhält eine Issuenummer; nichts wird als Markdown geschrieben."""
        self.server.issues[:] = [
            issue(101, "Remote neu", labels=["in-progress"]),
            issue(103, "Remote zu", state="closed"),
        ]
        self.write_store([
            ticket("AP1", "Lokal offen"),
            ticket("GH-101", "Alt", github=101),
            ticket("GH-103", "Alt zu", github=103),
        ])

        ok, message = self.cli.github_issues_sync("proj")

        self.assertTrue(ok, message)
        records = self.tickets()
        self.assertEqual("Remote neu", records["GH-101"]["title"])
        self.assertEqual("in-progress", records["GH-101"]["state"])
        self.assertEqual("done", records["GH-103"]["state"])
        self.assertIsNotNone(records["AP1"]["github"])
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(["Lokal offen"], [post["body"].get("title")
                                           for post in posts])

    def test_state_action_maps_ready_to_open_and_keeps_draft(self):
        """Vor: GH-101 offen. Aktion: github_issues_state draft, ready,
        in-progress. Erwartet: draft -> draft, ready -> open, in-progress ->
        in-progress; das Issue wird per PATCH aktualisiert."""
        self.write_store([ticket("GH-101", "Titel", github=101)])

        self.cli.github_issues_state("proj", "GH-101", "draft")
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        self.cli.github_issues_state("proj", "GH-101", "ready")
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        self.cli.github_issues_state("proj", "GH-101", "in-progress")
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])
        self.assertGreaterEqual(len(self.server.by_path("PATCH", "/issues/101")), 3)
        with self.assertRaises(ValueError):
            self.cli.github_issues_state("proj", "GH-101", "erledigt")


class PackageCloseTest(SurfaceCase):
    """``package_close`` übernimmt den Abschluss ohne Commit-Prüfung."""

    def test_package_close_uses_sync_ticket_without_require_commit(self):
        """Vor: registrierter Worktree, aktive GitHub-Verknüpfung, gemergter
        PR. Aktion: package_close. Erwartet: sync_ticket(..., 
        require_commit=False) wird aufgerufen; der alte sync_proof-Pfad nicht."""
        self.write_env(
            'TYPE=generic\nGITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n')
        worktree = self.root / "wt"
        worktree.mkdir()
        if not hasattr(self.cli.vibe_packages, "sync_ticket"):
            raise AssertionError(
                "vibe_packages.sync_ticket fehlt (GH-48: sync-ticket).")

        class Registry:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, project, pid):
                return {"branch": "feature/test/x1",
                        "path": str(worktree)}

            def unregister(self, project, pid):
                return None

        class Sessions:
            def __init__(self, *args, **kwargs):
                pass

            def forget_worktree(self, path):
                return None

        sync_calls = []

        def fake_sync(project, path, pid, require_commit=True):
            sync_calls.append({"project": project, "path": path, "pid": pid,
                               "require_commit": require_commit})
            return True, pid + " übernommen."

        with mock.patch.object(self.cli.vibe_runs, "WorktreeRegistry", Registry), \
                mock.patch.object(self.cli.vibe_runs, "SessionRegistry", Sessions), \
                mock.patch.object(self.cli.vibe_github, "remotes",
                                  return_value=[{"name": "origin"}]), \
                mock.patch.object(
                    self.cli.vibe_github, "merged_pull_request",
                    return_value={"found": True, "merged": True,
                                  "url": "http://example.invalid/pr/1"}), \
                mock.patch.object(self.cli.vibe_github, "pull_integration",
                                  return_value=(True, True, "ok")), \
                mock.patch.object(self.cli.vibe_github, "git",
                                  return_value=(0, "")), \
                mock.patch.object(self.cli.vibe_packages, "sync_ticket",
                                  side_effect=fake_sync) as sync_spy:
            ok, message = self.cli.package_close("proj", "X1")

        self.assertTrue(ok, message)
        self.assertEqual(1, sync_spy.call_count, sync_calls)
        self.assertEqual(1, len(sync_calls), sync_calls)
        self.assertIs(False, sync_calls[0]["require_commit"])
        self.assertEqual("X1", sync_calls[0]["pid"])
        # Der alte Markdown-Nachweispfad ist vertragsgemäß entfernt; es gibt
        # keinen zweiten Abschlussweg neben sync_ticket.
        self.assertFalse(hasattr(self.cli.vibe_packages, "sync_proof"))


if __name__ == "__main__":
    unittest.main()
