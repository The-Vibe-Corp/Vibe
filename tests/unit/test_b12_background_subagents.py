"""Unit-Abnahme B12: Hintergrund-Subagenten bleiben sichtbar.

Arbeitspaket B12 (Bug „Subagenten in Ausgabe nicht sichtbar"): opencode ≥ 2.3
kehrt beim ``task``/``subagent``-Werkzeug SOFORT zurück; die Hauptsession
meldet ``state.status="completed"`` mit ``state.metadata = {"sessionID": …,
"status": "running"}``, während die Kind-Session im Hintergrund weiterläuft.
Die Ausgabeansicht listet nur Einträge mit Status ``running`` — der
Hintergrund-Subagent war damit nie sichtbar.

Vereinbartes Verhalten (Akzeptanzkriterien):

* AK1 — Werkzeug-Metadaten sind Authorität: ``state.status="completed"`` +
  flache Metadaten ``{"sessionID": <kind>, "status": "running"}`` → Eintrag
  ``running``, ``ended`` 0; Agent/Beschreibung/Prompt aus ``state.input``;
  Ausgabe als 64-KiB-Tail; Hauptsession unverändert.
* AK2 — Keine Regression: Metadaten ohne ``status``-Feld (Alt-Form,
  verschachtelt ``metadata.metadata``) und Metadaten mit bekanntem/belegtem
  Abschlussstatus ergeben weiterhin ``completed`` mit ``ended`` > 0.
* AK3 — Wiederbelebung: Ein bereits abgeschlossener Eintrag, dessen Session
  danach Kind-Ereignisse (Text/Denken/Werkzeug) liefert, wird wieder
  ``running`` mit ``ended`` 0; die Ausgabe akkumuliert weiter.
* AK4 — Dashboard-Herabstufung (``/api/subagents``): Kennt der opencode-Server
  die Kind-Session (``parentID`` = Hauptsession) und ist sie NICHT aktiv, wird
  ein Eintrag mit ``running`` auf ``completed`` herabgestuft; ist sie aktiv,
  bleibt ``running``; ohne Kennwort oder ohne brauchbaren Server bleibt
  ``running`` (kein erfundener Abschluss).
* AK5 — Die Protokollzeile ``[Subagent] <agent>: <beschreibung> — <status>``
  spiegelt den wirksamen Eintrag-Status (für AK1 also ``running``).

Testfälle (Zuordnung in den Docstrings):

1. test_flat_running_metadata_keeps_background_subagent_running    [AK1, AK5]
2. test_stream_filter_publishes_running_subagent_line             [AK1, AK5]
3. test_background_subagent_output_is_tail_capped                        [AK1]
4. test_alt_metadata_without_status_stays_completed                      [AK2]
5. test_flat_metadata_with_explicit_status_follows_it                    [AK2]
6. test_metadata_without_known_status_falls_back_to_tool_state           [AK2]
7. test_finished_entry_is_revived_by_later_child_events                  [AK3]
8. test_dashboard_downgrades_running_entry_when_child_is_known_and_inactive
                                                                          [AK4a]
9. test_dashboard_keeps_running_entry_when_child_is_active               [AK4b]
10. test_dashboard_keeps_running_entry_without_password                  [AK4c]
11. test_dashboard_keeps_running_entry_when_server_fails                 [AK4c]

Keine Netzverbindung in die Welt, keine Modellaufrufe: Der opencode-Server ist
eine lokale HTTP-Attrappe (Muster wie in ``test_b11_output_view_api.py``), der
Dashboardserver läuft in einem isolierten VIBE-Root auf einem freien Port.
"""
import base64
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))

import vibe_runs  # noqa: E402

MAIN_SESSION = "ses_main_b12"
CHILD_A = "ses_kind_a"
CHILD_B = "ses_kind_b"
AGENT = "code-reviewer"
DESCRIPTION = "Reviewer-Verfügbarkeit prüfen"
PROMPT = "Prüfe die Reviewer-Verfügbarkeit."
BACKGROUND_OUTPUT = (
    "The subagent is working in the background "
    "(sessionID: ses_kind_a). You will receive a <subagent> message "
    "when it goes idle."
)
TAIL_BUDGET = 64 * 1024
SERVER_CREDENTIAL = "geheim-B12-4711"


# ---------------------------------------------------------------------------
# Teil 1: Ereignisübersetzung (vibe_runs.translate_event / stream_events)
# ---------------------------------------------------------------------------

def text_event(session, text):
    return {"type": "text", "sessionID": session,
            "part": {"type": "text", "text": text}}


def reasoning_event(session, text):
    return {"type": "reasoning", "sessionID": session,
            "part": {"type": "text", "text": text}}


def subagent_task_event(session, child, metadata, status="completed",
                        agent=AGENT, description=DESCRIPTION, output=""):
    """Ein task/subagent-Werkzeugereignis der Hauptsession.

    ``metadata`` ist der Wert von ``part.state.metadata``; ``status`` der Wert
    von ``part.state.status``. opencode ≥ 2.3 liefert die flache Form
    ``{"sessionID": <kind>, "status": "running"}`` mit ``status="completed"``
    am Zustand; ältere Stände verschachteln ``metadata.metadata`` ohne
    Statusfeld.
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
                    "description": description,
                    "prompt": PROMPT,
                },
                "metadata": metadata,
                "output": output,
            },
        },
    }


class TranslateFixture(unittest.TestCase):
    """Direkter Aufruf der Übersetzung mit einem Zustand im Speicher."""

    def setUp(self):
        self.state = {"session": "", "subagents": []}

    def feed(self, events):
        """Wendet Ereignisse nacheinander an und sammelt die Zeilen."""
        lines = []
        for event in events:
            event_lines, _changed = vibe_runs.translate_event(event, self.state)
            lines.extend(event_lines)
        return lines

    def entry(self, session):
        return next((item for item in self.state["subagents"]
                     if item.get("session") == session), None)

    def establish_main(self):
        self.feed([text_event(MAIN_SESSION, "Hauptagent arbeitet")])


class BackgroundSubagentTest(TranslateFixture):
    """AK1: Metadaten-Status macht den Hintergrund-Subagenten sichtbar."""

    def test_flat_running_metadata_keeps_background_subagent_running(self):
        """AK1/AK5: Hintergrund-Subagent läuft, Zeile zeigt running.

        Vorbedingung: Hauptsession erfasst; opencode ≥ 2.3-Form.
        Aktion: tool_use der Hauptsession, Werkzeug ``task``,
        ``state.status="completed"``, ``state.metadata={"sessionID":
        ses_kind_a, "status": "running"}``, Tool-Output als Text.
        Erwartung: Genau ein Eintrag mit session=ses_kind_a, status
        "running", ended 0, gestartet gesetzt, Agent/Beschreibung/Prompt aus
        state.input; Ausgabe enthält den Tool-Output; Hauptsession
        unverändert; Zeile "[Subagent] code-reviewer: … — running", keine
        Subagentenzeile mit "— completed".
        Fehlerfall: Eintrag erscheint als "completed" (Aktueller Fehler) oder
        die Hauptsession wird verändert.
        """
        self.establish_main()

        lines = self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_A,
            {"sessionID": CHILD_A, "status": "running"},
            status="completed", output=BACKGROUND_OUTPUT)])

        state = self.state
        self.assertEqual(MAIN_SESSION, state["session"], state)
        self.assertEqual(
            1, len(state["subagents"]),
            "Es muss genau einen Subagenteneintrag geben: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session: "
                             + json.dumps(state, ensure_ascii=False))
        self.assertEqual(
            "running", entry.get("status"),
            "Der Hintergrund-Subagent gilt fälschlich als abgeschlossen: "
            + json.dumps(entry, ensure_ascii=False))
        self.assertEqual(0, entry.get("ended"),
                         "Ein laufender Eintrag darf kein ended haben: "
                         + json.dumps(entry, ensure_ascii=False))
        self.assertIsInstance(entry.get("started"), int, entry)
        self.assertEqual(AGENT, entry.get("agent"), entry)
        self.assertEqual(DESCRIPTION, entry.get("description"), entry)
        self.assertEqual(PROMPT, entry.get("prompt"), entry)
        self.assertIn("The subagent is working in the background",
                      str(entry.get("output") or ""), entry)
        self.assertIn(
            f"[Subagent] {AGENT}: {DESCRIPTION} — running", lines, lines)
        completed_lines = [line for line in lines
                           if line.startswith("[Subagent]")
                           and line.rstrip().endswith("— completed")]
        self.assertEqual([], completed_lines,
                         "Die Subagentenzeile meldet einen Abschluss: "
                         + repr(completed_lines))

    def test_stream_filter_publishes_running_subagent_line(self):
        """AK1/AK5: Der Stream-Filter gibt die laufende Zeile aus.

        Vorbedingung: leerer Zustand; Aufruf über ``stream_events`` wie in der
        Produktion.
        Aktion: Hauptsession-Text, danach das opencode-2.3-task-Ereignis mit
        Metadaten-Status "running".
        Erwartung: Der Ausgabestrom enthält genau eine Subagentenzeile und sie
        endet auf "— running"; die Zustandsdatei hält einen laufenden Eintrag.
        Fehlerfall: Die Zeile meldet "— completed" (Aktueller Fehler) oder der
        Eintrag wird als abgeschlossen gespeichert.
        """
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "proj.log.state.json"
            payload = "\n".join(json.dumps(event, ensure_ascii=False)
                                for event in [
                                    text_event(MAIN_SESSION, "Hauptagent"),
                                    subagent_task_event(
                                        MAIN_SESSION, CHILD_A,
                                        {"sessionID": CHILD_A,
                                         "status": "running"},
                                        status="completed",
                                        output=BACKGROUND_OUTPUT),
                                ]) + "\n"
            emitted = []
            vibe_runs.stream_events(
                io.StringIO(payload), emitted.append, str(state_path))

            # Strukturkorrektur (Coding-Agent-Rückmeldung): Die Zustandsdatei
            # wird noch innerhalb des TemporaryDirectory gelesen und geprüft;
            # nach dem Verlassen wäre sie bereits gelöscht. Die fachlichen
            # Assertionen bleiben unverändert.
            self.assertIn(
                f"[Subagent] {AGENT}: {DESCRIPTION} — running", emitted,
                emitted)
            subagent_lines = [line for line in emitted
                              if line.startswith("[Subagent]")]
            self.assertEqual(
                1, len(subagent_lines),
                "Es soll genau eine Subagentenzeile geben: " + repr(emitted))
            state = vibe_runs.load_subagent_state(str(state_path))
            entry = next(
                (item for item in state["subagents"]
                 if item.get("session") == CHILD_A), None)
            self.assertIsNotNone(entry, "Kein Eintrag in der Zustandsdatei: "
                                 + json.dumps(state, ensure_ascii=False))
            self.assertEqual("running", entry.get("status"), entry)
            self.assertEqual(0, entry.get("ended"), entry)

    def test_background_subagent_output_is_tail_capped(self):
        """AK1: Auch die Hintergrund-Ausgabe bleibt ein 64-KiB-Tail.

        Vorbedingung: Hauptsession erfasst.
        Aktion: task-Ereignis mit rund 70 KiB Ausgabe (ANFANG-4711 am Anfang,
        ENDE-4711 am Ende) und Metadaten-Status "running".
        Erwartung: gespeicherte Ausgabe höchstens 64 KiB, Anfang verworfen,
        Ende erhalten; Status bleibt "running".
        Fehlerfall: Unbegrenztes Wachstum oder Verlust des Endes.
        """
        self.establish_main()
        huge = ("ANFANG-4711\n" + "m" * 70_000 + "\nENDE-4711")

        self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_A, {"sessionID": CHILD_A, "status": "running"},
            status="completed", output=huge)])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        output = str(entry.get("output") or "")
        self.assertLessEqual(
            len(output.encode("utf-8")), TAIL_BUDGET,
            "Die gespeicherte Ausgabe ist mit %d Bytes unbegrenzt" % len(output))
        self.assertNotIn("ANFANG-4711", output,
                         "Der Anfang wurde nicht verworfen (Tail-Semantik)")
        self.assertIn("ENDE-4711", output,
                      "Das Ende der Ausgabe ging verloren:\n" + output[-200:])
        self.assertEqual("running", entry.get("status"), entry)


class SyncLegacyBehaviorTest(TranslateFixture):
    """AK2: Synchrones und Alt-Verhalten ändert sich nicht."""

    def test_alt_metadata_without_status_stays_completed(self):
        """AK2: Alt-Form ohne Statusfeld bleibt completed.

        Vorbedingung: Hauptsession erfasst; opencode ≤ 2.2.6-Form.
        Aktion: task-Ereignis, ``state.status="completed"``, Metadaten
        ``{"metadata": {"sessionID": ses_kind_a}}`` ohne Statusfeld.
        Erwartung: Eintrag status "completed" mit ended > 0; Zeile meldet
        "— completed".
        Fehlerfall: Der Eintrag wird laufend gehalten oder endet nie.
        """
        self.establish_main()

        lines = self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_A, {"metadata": {"sessionID": CHILD_A}},
            status="completed", output="FERTIG-A")])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"),
                            "Ein abgeschlossener Eintrag braucht ended: "
                            + json.dumps(entry, ensure_ascii=False))
        self.assertIn(
            f"[Subagent] {AGENT}: {DESCRIPTION} — completed", lines, lines)

    def test_flat_metadata_with_explicit_status_follows_it(self):
        """AK2: Flache Metadaten mit bekanntem Status gelten weiter.

        Vorbedingung: Hauptsession erfasst.
        Aktion: task-Ereignis mit flachen Metadaten
        ``{"sessionID": ses_kind_a, "status": "completed"}`` und
        ``state.status="completed"``.
        Erwartung: Eintrag status "completed" mit ended > 0.
        Fehlerfall: Die Metadaten werden ignoriert oder der Eintrag bleibt
        fälschlich laufend.
        """
        self.establish_main()

        self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_A,
            {"sessionID": CHILD_A, "status": "completed"},
            status="completed", output="FERTIG-A")])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"), entry)

    def test_metadata_without_known_status_falls_back_to_tool_state(self):
        """AK2/Fehlerfall: Unbekannter oder fehlender Status → state.status.

        Vorbedingung: Hauptsession erfasst.
        Aktion: Erst flache Metadaten ohne Statusfeld, dann mit unbekanntem
        Statuswert "wartet-auf-freigabe"; beide mit
        ``state.status="completed"``.
        Erwartung: Beide Male Eintrag status "completed" mit ended > 0; kein
        laufender Eintrag.
        Fehlerfall: Ein unbekannter Statuswert hält den Eintrag künstlich
        am Laufen.
        """
        self.establish_main()

        self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_A, {"sessionID": CHILD_A},
            status="completed", output="FERTIG-A")])
        entry = self.entry(CHILD_A)
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"), entry)

        self.feed([subagent_task_event(
            MAIN_SESSION, CHILD_B,
            {"sessionID": CHILD_B, "status": "wartet-auf-freigabe"},
            status="completed", output="FERTIG-B")])
        entry_b = self.entry(CHILD_B)
        self.assertIsNotNone(entry_b, "Kein Eintrag für ses_kind_b")
        self.assertEqual("completed", entry_b.get("status"), entry_b)
        self.assertNotEqual(0, entry_b.get("ended"), entry_b)
        self.assertEqual("completed", self.entry(CHILD_A).get("status"),
                         "Der erste Eintrag wurde verändert")


class RevivalTest(TranslateFixture):
    """AK3: Kind-Ereignisse nach Abschluss beleben den Eintrag wieder."""

    def test_finished_entry_is_revived_by_later_child_events(self):
        """AK3: Abschluss + nachfolgende Kind-Ereignisse → wieder running.

        Vorbedingung: Hauptsession erfasst; ses_kind_a über das Alt-Form-
        task-Ereignis abgeschlossen, ses_kind_b (anderes Kind) ebenfalls
        abgeschlossen.
        Aktion: Danach text-, reasoning- und tool_use-Ereignisse von
        ses_kind_a.
        Erwartung: ses_kind_a ist wieder status "running" mit ended 0; die
        Ausgabe enthält den alten Abschluss-Text und die neuen Teilausgaben;
        ses_kind_b bleibt unverändert "completed".
        Fehlerfall: Der Eintrag bleibt abgeschlossen (Aktueller Fehler), die
        Ausgabe geht verloren oder ses_kind_b wird mitbelebt.
        """
        self.establish_main()
        self.feed([
            subagent_task_event(
                MAIN_SESSION, CHILD_A, {"metadata": {"sessionID": CHILD_A}},
                status="completed", output="ABSCHLUSS-A-4711"),
            subagent_task_event(
                MAIN_SESSION, CHILD_B, {"metadata": {"sessionID": CHILD_B}},
                status="completed", output="ABSCHLUSS-B-4711"),
        ])
        self.assertEqual("completed", self.entry(CHILD_A).get("status"))
        self.assertEqual("completed", self.entry(CHILD_B).get("status"))

        self.feed([
            text_event(CHILD_A, "NACHLESE-4711"),
            reasoning_event(CHILD_A, "Kind denkt erneut nach"),
            {"type": "tool_use", "sessionID": CHILD_A,
             "part": {"tool": "bash",
                      "state": {"status": "running",
                                "input": {"command": "git status"}}}},
        ])

        entry_a = self.entry(CHILD_A)
        self.assertEqual(
            "running", entry_a.get("status"),
            "Der abgeschlossene Eintrag wurde durch Kind-Ereignisse nicht "
            "wiederbelebt: " + json.dumps(entry_a, ensure_ascii=False))
        self.assertEqual(0, entry_a.get("ended"),
                         "Der wiederbelebte Eintrag darf kein ended haben: "
                         + json.dumps(entry_a, ensure_ascii=False))
        output = str(entry_a.get("output") or "")
        for expected in ("ABSCHLUSS-A-4711", "NACHLESE-4711",
                         "[Denken] Kind denkt erneut nach",
                         "[Werkzeug] bash", "git status"):
            self.assertIn(expected, output,
                          f"Ausgabeteil {expected!r} fehlt:\n{output[-300:]}")
        entry_b = self.entry(CHILD_B)
        self.assertEqual(
            "completed", entry_b.get("status"),
            "Das unbelebte Kind wurde fälschlich verändert: "
            + json.dumps(entry_b, ensure_ascii=False))
        self.assertNotEqual(0, entry_b.get("ended"), entry_b)


# ---------------------------------------------------------------------------
# Teil 2: Dashboard-Herabstufung (/api/subagents, AK4)
# ---------------------------------------------------------------------------

WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Lokaler opencode-Testserver ohne Modellaufrufe.

    ``GET /api/session?limit=100`` liefert die Session-Liste aus
    ``sessions_path``; ``GET /api/session/active`` die Aktivkarte aus
    ``active_path``. Mit ``fail`` wird jede Anfrage mit 500 beantwortet
    („Server unbrauchbar“). Jede Anfrage wird protokolliert.
    """

    context = None

    def log_message(self, *args):
        return

    def _record(self):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "auth_ok": self._auth_ok(),
            }, ensure_ascii=False) + "\n")

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8").strip()
        except OSError:
            return False
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return self.headers.get("Authorization", "") == "Basic " + encoded

    def _read_json(self, key, fallback):
        try:
            return json.loads(Path(self.context[key]).read_text(
                encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return fallback

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        if not self._auth_ok():
            self._send_json(401, {"ok": False})
            return
        if self.context.get("fail"):
            self._send_json(500, {"ok": False})
            return
        if "/api/session/active" in self.path:
            payload = self._read_json("active_path", {"data": {}})
        elif "/api/session" in self.path:
            payload = self._read_json("sessions_path", {"data": []})
        else:
            payload = {"ok": True}
        self._send_json(200, payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record()
        if self._auth_ok():
            self._send_json(200, {"ok": True})
        else:
            self._send_json(401, {"ok": False})


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf; verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")
if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


class DashboardFixture(unittest.TestCase):
    """Dashboard, isoliertes Projekt, tmux- und opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir()
        (cls.project / ".vibe").mkdir()
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n',
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] B12 Hintergrund-Subagenten\n"
            "  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "commit", "-q", "-m",
                        "Ausgangsstand"], check=True, capture_output=True)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8")
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "sessions_path": str(cls.root / "sessions.json"),
            "active_path": str(cls.root / "active.json"),
            "fail": False,
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context))
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
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
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        (cls.root / "tmp").mkdir(exist_ok=True)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_AGENTS_DIR": str(cls.agents),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
            "HOME": str(cls.home),
            "XDG_CONFIG_HOME": str(cls.home / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(cls.tmux_log),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

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
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     self.log_dir / "opencode.password",
                     Path(self.context["record_path"]),
                     Path(self.context["sessions_path"]),
                     Path(self.context["active_path"])):
            if path.exists():
                path.unlink()
        self.context["fail"] = False

    def tearDown(self):
        self.context["fail"] = False

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", "test-agent",
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def password_private(self, value=SERVER_CREDENTIAL):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def write_state(self, entry):
        """Legt Zustandsdatei mit Hauptsession und einem Eintrag an."""
        now = int(time.time())
        entry = dict(entry)
        entry.setdefault("session", CHILD_A)
        entry.setdefault("agent", AGENT)
        entry.setdefault("description", DESCRIPTION)
        entry.setdefault("prompt", PROMPT)
        entry.setdefault("status", "running")
        entry.setdefault("started", now + 2)
        entry.setdefault("ended", 0)
        entry.setdefault("output", "B12-LIVE-AUSGABE")
        path = self.log_dir / "proj.log.state.json"
        path.write_text(json.dumps(
            {"session": MAIN_SESSION, "subagents": [entry]},
            ensure_ascii=False), encoding="utf-8")
        return path

    def write_server_view(self, child_known=True, child_active=False):
        """Bestimmt, was die opencode-Attrappe über die Kind-Session meldet."""
        sessions = []
        if child_known:
            sessions.append({
                "id": CHILD_A,
                "parentID": MAIN_SESSION,
                "agent": AGENT,
                "title": DESCRIPTION,
                "time": {"created": 1700000000000, "updated": 1700000005000},
            })
        Path(self.context["sessions_path"]).write_text(
            json.dumps({"data": sessions}, ensure_ascii=False),
            encoding="utf-8")
        active = {CHILD_A: {"type": "running"}} if child_active else {}
        Path(self.context["active_path"]).write_text(
            json.dumps({"data": active}, ensure_ascii=False),
            encoding="utf-8")

    def request(self, method, path, body=None):
        encoded = (json.dumps(body, ensure_ascii=False).encode("utf-8")
                   if body is not None else None)
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Token": self.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            return response.status, payload, text
        finally:
            connection.close()

    def get_subagents(self):
        return self.request("GET", "/api/subagents?name=proj")

    def list_entries(self):
        status, data, raw = self.get_subagents()
        self.assertEqual(200, status, raw)
        self.assertTrue(
            bool(data) and data.get("ok") is True,
            "Die Subagentenliste sollte geliefert werden: " + raw)
        return [entry for entry in (data or {}).get("subagents") or []]

    def requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DashboardDowngradeTest(DashboardFixture):
    """AK4: Herabstufung am geteilten Server, Grenzen ohne Server."""

    def test_dashboard_downgrades_running_entry_when_child_is_known_and_inactive(
            self):
        """AK4a: Bekannte, inaktive Kind-Session → completed.

        Vorbedingung: laufender Registereintrag; Zustandsdatei mit
        Hauptsession und laufendem Eintrag ses_kind_a; opencode-Attrappe
        meldet ses_kind_a in /api/session (parentID = Hauptsession) und NICHT
        in /api/session/active.
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "completed".
        Fehlerfall: Der Eintrag bleibt "running" (Aktueller Fehler).
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(
            1, len(matching),
            "Der Eintrag der Kind-Session fehlt in der Liste: "
            + json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "completed", matching[0].get("status"),
            "Der Hintergrund-Subagent wurde nach Serverlage nicht "
            "herabgestuft: " + json.dumps(matching[0], ensure_ascii=False))

    def test_dashboard_keeps_running_entry_when_child_is_active(self):
        """AK4b: Aktive Kind-Session bleibt running.

        Vorbedingung: wie AK4a, aber die Attrappe meldet ses_kind_a in
        /api/session/active mit type "running".
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running".
        Fehlerfall: Fälschliche Herabstufung trotz Aktivität.
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=True)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Der aktive Subagent wurde fälschlich beendet: "
            + json.dumps(matching[0], ensure_ascii=False))

    def test_dashboard_keeps_running_entry_without_password(self):
        """AK4c: Ohne Kennwort bleibt running, kein Serveraufruf.

        Vorbedingung: laufender Registereintrag und Zustandsdatei wie AK4a;
        keine Kennwortdatei; Attrappe meldet die Kind-Session als bekannt und
        inaktiv.
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running"; es gab keinen
        HTTP-Aufruf an die opencode-Attrappe.
        Fehlerfall: Erfundener Abschluss oder Serverabfrage ohne Kennwort.
        """
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Ohne Kennwort darf kein Abschluss erfunden werden: "
            + json.dumps(matching[0], ensure_ascii=False))
        self.assertEqual(
            [], self.requests(),
            "Ohne Kennwort wurde trotzdem der Server gefragt: "
            + json.dumps(self.requests(), ensure_ascii=False))

    def test_dashboard_keeps_running_entry_when_server_fails(self):
        """AK4c/Fehlerfall: Unbrauchbarer Server erfundet keinen Abschluss.

        Vorbedingung: wie AK4a, aber die Attrappe beantwortet jede Anfrage
        mit 500 (Server unbrauchbar).
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running".
        Fehlerfall: Ein Fehler wird still als Abschluss interpretiert.
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)
        self.context["fail"] = True

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Ein Serverfehler darf nicht als Abschluss gelten: "
            + json.dumps(matching[0], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
