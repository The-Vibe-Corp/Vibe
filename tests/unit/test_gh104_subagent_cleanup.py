"""Active subagent cleanup in the project output view (lifecycle regression).

The output view renders from the active ``subagents[]`` list of
``<log>.state.json``. These tests drive the production chain
``vibe_runs.stream_events`` -> state file -> ``/api/subagents`` with real
opencode-shaped events and assert that:

* a subagent leaves the active list at its own terminal event, while a
  concurrently running one stays active;
* completion, error, failure and cancellation all clean up immediately;
* consecutive tickets in one run/session do not inherit stale entries;
* finished output remains available as history (log/preserved record).

No model calls, no production paths: temporary HOME/runtime/state, dedicated
loopback ports, local opencode/run-server substitutes only where needed.

Run: python3 -m unittest tests.unit.test_gh104_subagent_cleanup -v
"""

import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
RUNS_PY = BIN / "vibe_runs.py"
WEB = BIN / "vibe-web.py"

sys.path.insert(0, str(BIN))
import vibe_runs  # noqa: E402

MAIN = "ses_main_gh104"
TICKET_1 = "ses_ticket_eins_gh104"
TICKET_2 = "ses_ticket_zwei_gh104"
CHILD_A = "ses_kind_a_gh104"
CHILD_B = "ses_kind_b_gh104"
HISTORY_A = "AUSGABE-A-4711"
HISTORY_B = "AUSGABE-B-4711"
FINAL_A = "ERGEBNIS-A-4711"


def text_event(session, text):
    """opencode text event of ``session`` (main or child)."""
    return {"type": "text", "sessionID": session,
            "part": {"type": "text", "text": text}}


def task_event(session, child, status, output="", metadata=None,
               agent="general", description=None):
    """task/subagent tool event of the main session.

    ``metadata=None`` uses the legacy nested form without a status field, so
    the tool status is authoritative. A dict is stored in ``state.metadata``;
    that is the shape opencode >= 2.3 uses for background subagents.
    """
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "tool": "task",
            "state": {
                "status": status,
                "input": {
                    "agent": agent,
                    "description": description or ("Kind " + child),
                    "prompt": "Auftrag " + child,
                },
                "metadata": metadata if metadata is not None else {
                    "metadata": {"sessionID": child}},
                "output": output,
            },
        },
    }


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SubagentLifecycleFixture(unittest.TestCase):
    """Feeds events through the real stream filter into a temporary state file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_path = self.root / "proj.log.state.json"
        self.emitted = []

    def feed(self, events, attempt=False, state_path=None):
        path = state_path or self.state_path
        payload = "\n".join(
            json.dumps(event, ensure_ascii=False) for event in events) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(path), attempt=attempt)
        self.emitted.extend(emitted)
        return emitted

    def state(self, state_path=None):
        return vibe_runs.load_subagent_state(str(state_path or self.state_path))

    def active_sessions(self, state_path=None):
        return [item.get("session")
                for item in self.state(state_path)["subagents"]]

    def active_entry(self, session, state_path=None):
        return next(
            (item for item in self.state(state_path)["subagents"]
             if item.get("session") == session), None)

    def history_has(self, text):
        """Finished output must survive in the log or a preserved record."""
        if text in "\n".join(self.emitted):
            return True
        try:
            return text in self.state_path.read_text(encoding="utf-8")
        except OSError:
            return False


class TerminalCleanupTest(SubagentLifecycleFixture):
    """A subagent leaves the active list at its own terminal event."""

    def test_finished_subagent_leaves_active_list_and_other_stays_running(self):
        """Two concurrent children; finishing A removes only A from active.

        Precondition: main session plus two running children with their own
        output. Action: a terminal task event for child A. Expectation: A is
        gone from the active list, B is still active with ``running`` and its
        own output, and A's historical output is still available. Failure: A
        remains in the active list (only hidden by the UI) or B is removed.
        """
        self.feed([
            text_event(MAIN, "Hauptagent arbeitet"),
            text_event(CHILD_A, HISTORY_A),
            text_event(CHILD_B, HISTORY_B),
        ])
        self.assertEqual(
            {CHILD_A, CHILD_B}, set(self.active_sessions()),
            "Vorbedingung: beide Kinder müssen laufen")

        self.feed([task_event(MAIN, CHILD_A, "completed", FINAL_A)])

        active = self.active_sessions()
        self.assertNotIn(
            CHILD_A, active,
            "Der beendete Subagent steht noch in der aktiven Liste: "
            + json.dumps(self.state(), ensure_ascii=False))
        self.assertIn(
            CHILD_B, active,
            "Der mitlaufende Subagent wurde mit entfernt: "
            + json.dumps(self.state(), ensure_ascii=False))
        entry_b = self.active_entry(CHILD_B)
        self.assertEqual("running", entry_b.get("status"), entry_b)
        self.assertIn(HISTORY_B, str(entry_b.get("output") or ""), entry_b)
        for historical in (HISTORY_A, FINAL_A):
            self.assertTrue(
                self.history_has(historical),
                f"Historische Ausgabe {historical!r} ging verloren: "
                + json.dumps(self.state(), ensure_ascii=False))

    def test_every_terminal_status_removes_the_active_entry(self):
        """completed, error, failed, cancelled and canceled all clean up."""
        statuses = ("completed", "error", "failed", "cancelled", "canceled")
        for status in statuses:
            with self.subTest(status=status):
                path = self.root / (status + ".state.json")
                before = len(self.emitted)
                emitted = self.feed([
                    text_event(MAIN, "Haupt " + status),
                    text_event(CHILD_A, "LAUF-A-" + status),
                    task_event(MAIN, CHILD_A, status, "ENDE-A-" + status),
                ], state_path=path)
                self.assertNotIn(
                    CHILD_A, self.active_sessions(path),
                    f"Terminalstatus {status!r} entfernte den Eintrag nicht: "
                    + json.dumps(self.state(path), ensure_ascii=False))
                for historical in ("LAUF-A-" + status, "ENDE-A-" + status):
                    self.assertIn(
                        historical, "\n".join(emitted),
                        f"Historische Ausgabe fehlt bei {status!r}: "
                        + repr(emitted))
                self.assertEqual(before + len(emitted), len(self.emitted))

    def test_background_subagent_is_removed_at_its_own_terminal_event(self):
        """opencode >= 2.3 background child: metadata status ends it, too."""
        self.feed([
            text_event(MAIN, "Hauptagent"),
            task_event(MAIN, CHILD_A, "completed", "BACKGROUND-4711",
                       metadata={"sessionID": CHILD_A, "status": "running"}),
        ])
        self.assertIn(CHILD_A, self.active_sessions())
        self.assertEqual(
            "running", self.active_entry(CHILD_A).get("status"),
            "Vorbedingung: Hintergrund-Subagent muss laufen")

        self.feed([task_event(
            MAIN, CHILD_A, "completed", FINAL_A,
            metadata={"sessionID": CHILD_A, "status": "completed"})])

        self.assertNotIn(
            CHILD_A, self.active_sessions(),
            "Der Hintergrund-Subagent blieb nach seinem Abschluss aktiv: "
            + json.dumps(self.state(), ensure_ascii=False))
        self.assertTrue(
            self.history_has(FINAL_A),
            "Die Ausgabe des abgeschlossenen Hintergrund-Subagenten fehlt")


class ConsecutiveTicketsTest(SubagentLifecycleFixture):
    """Several tickets in one run/session do not inherit stale subagents."""

    def test_second_ticket_does_not_inherit_the_first_tickets_running_child(self):
        """Same state file, two attempt streams: only ticket 2 stays active."""
        emitted_1 = self.feed([
            text_event(TICKET_1, "TICKET1-START-4711"),
            text_event(CHILD_A, HISTORY_A),
        ], attempt=True)
        self.assertIn(
            CHILD_A, self.active_sessions(),
            "Vorbedingung: Kind des ersten Tickets muss laufen")

        emitted_2 = self.feed([
            text_event(TICKET_2, "TICKET2-START-4711"),
            text_event(CHILD_B, HISTORY_B),
        ], attempt=True)

        state = self.state()
        self.assertEqual(
            TICKET_2, state["session"],
            "Die Hauptsession des zweiten Tickets wurde nicht übernommen")
        active = self.active_sessions()
        self.assertNotIn(
            CHILD_A, active,
            "Das Kind des ersten Tickets lief in den zweiten Ticket hinein: "
            + json.dumps(state, ensure_ascii=False))
        self.assertIn(
            CHILD_B, active,
            "Das Kind des zweiten Tickets fehlt: "
            + json.dumps(state, ensure_ascii=False))
        self.assertEqual("running", self.active_entry(CHILD_B).get("status"))
        self.assertIn(HISTORY_A, "\n".join(emitted_1 + emitted_2))
        self.assertTrue(self.history_has(HISTORY_A))
        self.assertIn(HISTORY_B, "\n".join(emitted_2))

    def test_finished_child_from_earlier_ticket_stays_inactive_on_next_ticket(self):
        """A finished child cannot reappear when the next ticket starts."""
        self.feed([
            text_event(TICKET_1, "TICKET1-START-4711"),
            text_event(CHILD_A, HISTORY_A),
            task_event(TICKET_1, CHILD_A, "completed", FINAL_A),
        ], attempt=True)
        self.assertNotIn(
            CHILD_A, self.active_sessions(),
            "Vorbedingung: der beendete Subagent muss schon inactive sein")

        self.feed([
            text_event(TICKET_2, "TICKET2-START-4711"),
            text_event(CHILD_B, HISTORY_B),
        ], attempt=True)

        self.assertEqual(TICKET_2, self.state()["session"])
        self.assertNotIn(
            CHILD_A, self.active_sessions(),
            "Der beendete Subagent kam im nächsten Ticket wieder zurück: "
            + json.dumps(self.state(), ensure_ascii=False))
        self.assertIn(CHILD_B, self.active_sessions())
        self.assertTrue(
            self.history_has(FINAL_A),
            "Die historische Ausgabe des früheren Tickets fehlt")


class OutputApiFixture(unittest.TestCase):
    """Isolated dashboard with a real run registry and state-file path."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        cls.runtime = cls.root / "_logs"
        cls.runtime.mkdir()
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmux").mkdir()
        (cls.root / "tmp").mkdir()
        cls.port = free_port()

        env = os.environ.copy()
        for key in list(env):
            if (key.startswith("VIBE") or key.startswith("SANDBOX")
                    or key in ("TMUX", "TMUX_PANE")):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.runtime),
            "VIBE_STATE": str(cls.state_dir),
            "HOME": str(cls.home),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.root / "tmux"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.runtime / "web.token"
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
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
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
        cls.server_log.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.state_path = self.runtime / "proj.log.state.json"
        self.log_path = self.runtime / "proj.log"
        for path in (self.state_path, self.log_path,
                     self.runtime / "runs.json"):
            path.unlink(missing_ok=True)
        self.emitted = []

    def register_run(self):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.runtime),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", "tester",
            "--state", "running",
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(
            0, result.returncode,
            "Laufregister nicht angelegt: " + result.stdout + result.stderr)

    def feed(self, events, attempt=False):
        payload = "\n".join(
            json.dumps(event, ensure_ascii=False) for event in events) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(self.state_path),
            attempt=attempt)
        self.emitted.extend(emitted)
        # Der Läufer schreibt die emit-Zeilen in das Laufprotokoll; dieses
        # Protokoll ist die historische Ausgabe, die nicht gelöscht wird.
        if emitted:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write("\n".join(emitted) + "\n")

    def request(self, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=15)
        try:
            connection.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token})
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(text), text
            except ValueError:
                return response.status, None, text
        finally:
            connection.close()


class ActiveListApiTest(OutputApiFixture):
    """The API used by the output view must not expose stale active cards."""

    def test_api_never_lists_a_finished_or_carried_over_subagent_as_active(self):
        """Finished/carried-over child absent; concurrent child still active."""
        self.register_run()
        self.feed([
            text_event(TICKET_1, "TICKET1-START-4711"),
            text_event(CHILD_A, HISTORY_A),
            task_event(TICKET_1, CHILD_A, "completed", FINAL_A),
        ], attempt=True)
        self.feed([
            text_event(TICKET_2, "TICKET2-START-4711"),
            text_event(CHILD_B, HISTORY_B),
        ], attempt=True)

        status, data, raw = self.request("/api/subagents?name=proj")
        self.assertEqual(200, status, raw)
        self.assertTrue(data and data.get("ok"), raw)
        by_session = {entry.get("session"): entry
                      for entry in data.get("subagents") or []}
        self.assertNotIn(
            CHILD_A, by_session,
            "Ein beendeter Subagent aus dem vorherigen Ticket steht noch "
            "in der aktiven API-Liste: " + raw)
        self.assertIn(
            CHILD_B, by_session,
            "Der laufende Subagent des aktuellen Tickets fehlt: " + raw)
        self.assertEqual("running", by_session[CHILD_B].get("status"), raw)
        self.assertIn(
            FINAL_A, self.log_path.read_text(encoding="utf-8"),
            "Die historische Ausgabe des beendeten Subagenten fehlt im Protokoll")


if __name__ == "__main__":
    unittest.main()
