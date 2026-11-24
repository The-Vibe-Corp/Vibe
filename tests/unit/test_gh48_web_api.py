"""GH-48: Vertragstests für die Web-API ``/api/ticket`` und ``/api/feedback``.

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` (Arbeitspakete und
Feedback, Sicherheit und Datenintegrität) und der verbindliche
Implementierungsvertrag GH-48 (§7 Web-API). Das echte Dashboard
(``bin/vibe-web.py``) läuft als eigener Prozess auf einem freien Port mit
vollständig temporären ``VIBE``-/``HOME``-Pfaden (Muster
``tests/unit/test_f29_priority_api.py``). Geprüft werden:

* ``add`` offline mit und ohne Zustand (draft/open) in den Ticketspeicher,
* die neue Aktion ``state`` (draft/open/in-progress erlaubt; done/blocked/
  waiting-merge und unbekannte Tickets abgelehnt),
* ``update``/``delete`` inklusive done-Schutz,
* verbundene Anlage über ``add_ticket_connected`` (Loopback-GitHub-Fake),
* ``project_detail``: tickets = task/feature, feedback = bug/feedback + kind,
* die bestehende Token-Pflicht bleibt für die neuen Aktionen bestehen.

Kein echtes GitHub, keine Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_gh48_web_api -v
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
FAKE_TOKEN = "gh48-web-fake-token"
GITHUB_TOKEN = "gh48-web-github-token"
STAMP = "2026-01-01T00:00:00+00:00"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class _IssuesHandler(BaseHTTPRequestHandler):
    """Minimaler Loopback-Fake für die verbundene Ticket-Anlage."""

    def log_message(self, *args):
        return

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._respond(200, [])

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        self.server.requests.append(payload)
        self.server.number += 1
        self._respond(201, {
            "number": self.server.number,
            "title": payload.get("title", ""),
            "body": payload.get("body", ""),
            "state": "open",
            "labels": [{"name": name}
                       for name in payload.get("labels") or []],
            "assignees": [],
        })


class TicketApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit",
                        "--allow-empty", "-q", "-m", "init"],
                       check=True, capture_output=True)
        (cls.project / ".vibe").mkdir()
        cls.env_path = cls.project / ".vibe" / "project.env"
        cls.store_path = cls.project / ".vibe" / "tickets.json"

        cls.github = ThreadingHTTPServer(("127.0.0.1", 0), _IssuesHandler)
        cls.github.requests = []
        cls.github.number = 200
        cls.github_thread = threading.Thread(target=cls.github.serve_forever,
                                             daemon=True)
        cls.github_thread.start()
        cls.github_base = "http://127.0.0.1:%d" % cls.github.server_address[1]

        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        cls.port = free_port()
        env = env_support.isolated_environ()
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.home),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode"
                                   / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe"
                                    / "config.json"),
            "GITHUB_TOKEN": GITHUB_TOKEN,
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
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
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = "http://127.0.0.1:%d" % cls.port

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
        cls.github.shutdown()
        cls.github.server_close()
        cls.github_thread.join(timeout=5)
        cls.tmp.cleanup()

    def setUp(self):
        self.write_env("TYPE=generic\n")
        self.write_store([])
        self.github.requests.clear()
        self.github.number = 200

    # -------------------------------------------------------------- Helfer
    def write_env(self, text):
        self.env_path.write_text(text, encoding="utf-8")

    def issues_env(self):
        self.write_env(
            "TYPE=generic\n"
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % self.github_base)

    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item
                for item in json.loads(self.store_path.read_text(
                    encoding="utf-8"))["tickets"]}

    def request(self, path, body=None, token=True):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=data,
            method="POST" if body is not None else "GET")
        if token:
            request.add_header("X-Token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw}

    def post(self, path, body):
        return self.request(path, body)

    # ------------------------------------------------------------- add
    def test_add_offline_defaults_to_open(self):
        """Vor: kein Speicher, keine GitHub-Verknüpfung. Aktion: POST
        /api/ticket add. Erwartet: ok, AP1 im Speicher, state open."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Erstes Paket",
            "description": "Text"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        records = self.read_store()
        self.assertIn("AP1", records)
        self.assertEqual("open", records["AP1"]["state"])
        self.assertEqual("Erstes Paket", records["AP1"]["title"])

    def test_add_accepts_an_optional_state(self):
        """Vor: kein Speicher. Aktion: POST /api/ticket add mit
        state=draft. Erwartet: AP1 ist draft (offline nutzbar)."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Entwurf",
            "state": "draft"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("draft", self.read_store()["AP1"]["state"])

    def test_feedback_add_creates_bug_and_feedback_types(self):
        """Vor: kein Speicher. Aktion: POST /api/feedback add zweimal
        (kind=bug, ohne kind). Erwartet: B1 type bug, F1 type feedback."""
        first = self.post("/api/feedback", {
            "name": "proj", "action": "add", "title": "Kaputt",
            "kind": "bug"})
        second = self.post("/api/feedback", {
            "name": "proj", "action": "add", "title": "Idee"})

        self.assertTrue(first[1].get("ok"), first)
        self.assertTrue(second[1].get("ok"), second)
        records = self.read_store()
        self.assertEqual("bug", records["B1"]["type"])
        self.assertEqual("feedback", records["F1"]["type"])

    # ------------------------------------------------------------ state
    def test_state_action_allows_draft_open_and_in_progress(self):
        """Vor: AP1 offen. Aktion: state draft -> open -> in-progress.
        Erwartet: jeweils ok und der Speicherzustand folgt."""
        self.write_store([ticket("AP1", "Titel")])

        for value in ("draft", "open", "in-progress"):
            status, payload = self.post("/api/ticket", {
                "name": "proj", "action": "state", "id": "AP1",
                "state": value})
            self.assertEqual(200, status, payload)
            self.assertTrue(payload.get("ok"), payload)
            self.assertEqual(value, self.read_store()["AP1"]["state"])

    def test_state_action_rejects_runner_and_github_states(self):
        """Vor: AP1 offen. Aktion: state done/blocked/waiting-merge.
        Erwartet: ok falsch mit Klartext; der Speicher bleibt offen."""
        self.write_store([ticket("AP1", "Titel")])

        for value in ("done", "blocked", "waiting-merge"):
            status, payload = self.post("/api/ticket", {
                "name": "proj", "action": "state", "id": "AP1",
                "state": value})
            self.assertIn(status, (200, 400), payload)
            self.assertFalse(payload.get("ok"), payload)
            message = str(payload.get("message") or "")
            self.assertTrue(message.strip())
            self.assertTrue(value in message.lower()
                            or "state" in message.lower()
                            or "zustand" in message.lower(), payload)
            self.assertEqual("open", self.read_store()["AP1"]["state"])

    def test_state_action_rejects_unknown_ticket(self):
        """Vor: leerer Speicher. Aktion: state für X9.
        Erwartet: ok falsch, kein Ticket entsteht."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "state", "id": "X9",
            "state": "open"})

        self.assertIn(status, (200, 400), payload)
        self.assertFalse(payload.get("ok"), payload)
        message = str(payload.get("message") or "").lower()
        self.assertTrue("x9" in message or "nicht gefunden" in message
                        or "unbekannt" in message, payload)
        self.assertEqual({}, self.read_store())

    # --------------------------------------------------- update/delete
    def test_update_and_delete_open_ticket(self):
        """Vor: AP1 offen. Aktion: update, danach delete.
        Erwartet: Titel geändert, danach ist AP1 entfernt."""
        self.write_store([ticket("AP1", "Alt")])

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "update", "id": "AP1",
            "title": "Neu", "description": "Text"})
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("Neu", self.read_store()["AP1"]["title"])

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "delete", "id": "AP1"})
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual({}, self.read_store())

    def test_done_ticket_cannot_be_deleted_or_edited_via_the_api(self):
        """Vor: AP2 done mit Nachweis. Aktion: update und delete.
        Erwartet: ok falsch jeweils; das Ticket bleibt unverändert."""
        self.write_store([ticket("AP2", "Fertig", state="done",
                                 commit="abcdef1", test="test_ap2")])
        before = self.store_path.read_bytes()

        for body in (
            {"name": "proj", "action": "update", "id": "AP2",
             "title": "Neu"},
            {"name": "proj", "action": "delete", "id": "AP2"},
        ):
            status, payload = self.post("/api/ticket", body)
            self.assertIn(status, (200, 400), payload)
            self.assertFalse(payload.get("ok"), payload)
        self.assertEqual(before, self.store_path.read_bytes())

    # -------------------------------------------------------- verbunden
    def test_connected_add_creates_the_issue_first_and_the_gh_ticket(self):
        """Vor: Issues-Sync aktiv, Loopback-GitHub. Aktion: POST /api/ticket
        add mit category=bug. Erwartet: genau ein Issue-POST; lokales Ticket
        GH-201 mit type bug."""
        self.issues_env()

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Verbunden",
            "description": "Text", "category": "bug"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(1, len(self.github.requests), self.github.requests)
        records = self.read_store()
        self.assertIn("GH-201", records)
        self.assertEqual("bug", records["GH-201"]["type"])

    # --------------------------------------------------- project_detail
    def test_project_detail_assigns_tickets_and_feedback(self):
        """Vor: task/feature/bug/feedback im Speicher. Aktion: GET
        /api/project?name=proj. Erwartet: data["tickets"] = task/feature,
        data["feedback"] = bug/feedback mit kind."""
        self.write_store([
            ticket("AP1", "Aufgabe"),
            ticket("FEAT-2", "Feature", type="feature"),
            ticket("B1", "Bug", type="bug"),
            ticket("F1", "Feedback", type="feedback"),
        ])

        status, payload = self.request("/api/project?name=proj")

        self.assertEqual(200, status, payload)
        ticket_ids = {row["id"] for row in payload["tickets"]}
        feedback_ids = {row["id"] for row in payload["feedback"]}
        self.assertEqual({"AP1", "FEAT-2"}, ticket_ids)
        self.assertEqual({"B1", "F1"}, feedback_ids)
        kinds = {row["id"]: row.get("kind") for row in payload["feedback"]}
        self.assertEqual("bug", kinds["B1"])
        self.assertEqual("feedback", kinds["F1"])

    # -------------------------------------------------------------- Auth
    def test_new_actions_still_require_the_token(self):
        """Vor: gültiger Speicher. Aktion: POST /api/ticket ohne Token.
        Erwartet: 403; der Speicher bleibt unverändert."""
        self.write_store([ticket("AP1", "Titel")])
        before = self.store_path.read_bytes()

        status, _ = self.request("/api/ticket", {
            "name": "proj", "action": "delete", "id": "AP1"}, token=False)

        self.assertEqual(403, status)
        self.assertEqual(before, self.store_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
