"""Unit-Abnahme B6: F24 (aktiver Agent, Subagenten-Tabs) funktioniert für Pi.

Arbeitspaket B6 (FEEDBACK.md): „F24 funktioniert nicht richtig … Diese
Funktion darf außerdem nicht opencode spezifisch sein, z. B. wenn der
pi harness benutzt wird, muss es auch funktionieren."

Die fachliche Quelle ist die Pi-Dokumentation 1.5.0
(/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/docs/json.md):
Pi 1.5.0 liefert im JSON-Modus einen strukturierten JSONL-Ereignisstrom
(``--mode json``) mit den Ereignistypen ``session`` (Header mit ``id``),
``message_start/update/end`` (assistant content = Array von Blöcken type
text/thinking), ``tool_execution_start/update/end`` (toolCallId, toolName,
args, partialResult, result, isError) und Rauschereignissen (turn_*,
agent_*, queue_update, compaction_*).

Geplante, verbindliche Schnittstellen gegen die geprüft wird:
* ``vibe_runs.translate_pi_event(event, state) -> (lines, changed)`` —
  identische Schnittstelle zur bestehenden ``translate_event`` (opencode).
* ``vibe_runs.stream_events(stdin, emit, state_path)`` erkennt die
  Ereignisform automatisch: Pi-Ereignistypen → Pi-Übersetzung, sonst
  unverändertes opencode-Verhalten (Nicht-JSON-Zeilen unverändert,
  defektes JSON mit Präfix ``opencode: ``).
* Zustandsdatei ``<log>.state.json``: Pi-Session-Header wird NICHT als
  Hauptsession übernommen (Pi-Läufe sind ephemer, ``--no-session``; die
  opencode-Live-Abfrage darf mit dieser Kennung nie befragt werden).
* Werkzeugnamen aus SUBAGENT_TOOLS ("task", "subagent") erzeugen einen
  Subagenteneintrag mit ``session`` = toolCallId (Tab-Schlüssel), Status
  start ``running``, Ende ``completed``/``error`` und erfasster Ausgabe
  aus ``partialResult``/``result.content[{type:"text"}]``.
* UI-API: /api/subagents und /api/subagent-output bleiben unverändert und
  arbeiten mit den erfassten Zustandsdaten (Muster test_f20/
  test_f24_output_agent_ui, echter lokaler Webserver, eigener Port,
  keine Modellaufrufe, keine externen Dienste).

Rotphase: Alle Pi-bezogenen Fälle scheitern, weil die geplanten
Schnittstellen (noch) nicht existieren; die opencode-Regressionen sind
vorher bereits grün und beweisen die Unverändertheit (AK2).
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

PI_SESSION = "ses-pi-4711"
TOOL_CALL = "call_abc123"
PI_BROKEN = "{kaputt"
PI_PLAIN = "Zufällige Ausgabe ohne JSON"


def pi_events(session=PI_SESSION):
    """Pi-JSONL-Ereignisse eines vollständigen einfachen Laufs (Pi-Doku 1.5.0).

    Reihenfolge und Form folgen exakt dem Beispielkapitel der offiziellen
    json.md: Session-Header, message_end für user/assistant (assistant
    content = Blockliste), tool_execution_start/update/end und die
    Rausch-Ereignisse turn_end/agent_end/agent_settled.
    """
    events = [
        {"type": "session", "version": 3, "id": session,
         "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "/proj"},
        {"type": "agent_start"},
        {"type": "message_end",
         "message": {"role": "user", "content": "Arbeitspaket B6",
                     "timestamp": 1735689600000}},
        {"type": "message_end",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "text": "nachdenkliche Zeile"},
             {"type": "text", "text": "Hallo\nWelt"},
         ]}},
        {"type": "tool_execution_start", "toolCallId": "call_bash1",
         "toolName": "bash", "args": {"command": "ls -la"}},
        {"type": "tool_execution_update", "toolCallId": "call_bash1",
         "toolName": "bash", "args": {"command": "ls -la"},
         "partialResult": {"content": [{"type": "text", "text": "Datei1"}]}},
        {"type": "tool_execution_end", "toolCallId": "call_bash1",
         "toolName": "bash",
         "result": {"content": [{"type": "text", "text": "Datei1"}]},
         "isError": False, "durationMs": 4},
    ]
    return [json.dumps(event, ensure_ascii=False) for event in events]


def pi_task_events():
    """Pi-Ereignisse für ein erfasstes Subagenten-Werkzeug (task)."""
    events = [
        {"type": "tool_execution_start", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "args": {"agent": "general", "description": "Testzusammenfassung",
                  "prompt": "Sammle Infos"}},
        {"type": "tool_execution_update", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "args": {"agent": "general", "description": "Testzusammenfassung"},
         "partialResult": {"content": [{"type": "text", "text": "Teilausgabe"}]}},
        {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "result": {"content": [{"type": "text", "text": "PONG"},
                                {"type": "text", "text": "Zweitzeile"}]},
         "isError": False, "durationMs": 7},
    ]
    return events


class PiTranslateFixture(unittest.TestCase):
    """Vorbedingung je Fall: frischer leerer Zustand (kein Session, keine
    Subagenten)."""

    def setUp(self):
        self.state = {"session": "", "subagents": []}

    def translate(self, event):
        return vibe_runs.translate_pi_event(event, self.state)


class PiEventTranslationTest(PiTranslateFixture):
    """AK1: Pi-Ereignisse werden vollständig in Klartextzeilen übersetzt;
    nichts geht verloren, nichts wird erfunden."""

    # 1. Name: test_pi_session_header_becomes_session_line_without_state [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: Pi-Session-Header übersetzen.
    #    Erwartung: Zeile "[Session] ses-pi-4711"; die Kennung wird NICHT in
    #    den Zustand übernommen (Pi-Läufe sind ephemer, die opencode-
    #    Live-Abfrage darf mit dieser Kennung nie befragt werden).
    #    Fehlerfall: Keine Zeile oder Kennung im Zustand.
    def test_pi_session_header_becomes_session_line_without_state(self):
        event = {"type": "session", "version": 3, "id": PI_SESSION,
                 "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "/proj"}

        lines, _changed = self.translate(event)

        self.assertIn("[Session] " + PI_SESSION, lines)
        self.assertEqual(
            "", self.state["session"],
            "Die ephemere Pi-Session-Kennung darf nicht als Hauptsession "
            "erfasst werden: " + json.dumps(self.state, ensure_ascii=False),
        )

    # 2. Name: test_pi_assistant_text_and_thinking_blocks_become_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_end (assistant,
    #    Content = [thinking-Block, text-Block mit Zeilenumbruch]).
    #    Erwartung: Textzeilen je Zeile ("Hallo", "Welt") und
    #    "[Denken] nachdenkliche Zeile" in Content-Reihenfolge.
    #    Fehlerfall: Zeilen fehlen, Reihenfolge falsch oder Roh-JSON.
    def test_pi_assistant_text_and_thinking_blocks_become_lines(self):
        event = {"type": "message_end", "message": {"role": "assistant",
                 "content": [{"type": "thinking", "text": "nachdenkliche Zeile"},
                             {"type": "text", "text": "Hallo\nWelt"}]}}

        lines, _changed = self.translate(event)

        self.assertEqual(
            ["[Denken] nachdenkliche Zeile", "Hallo", "Welt"], lines,
            "Text- und Denkblöcke müssen zeilenweise in Content-Reihenfolge "
            "erscheinen: " + repr(lines),
        )
        self.assertFalse(any(
            line.startswith("{") for line in lines), "Roh-JSON im Protokoll")

    # 3. Name: test_pi_user_message_produces_no_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_end (role user).
    #    Erwartung: keine Zeilen (nichts wird erfunden).
    def test_pi_user_message_produces_no_lines(self):
        event = {"type": "message_start",
                 "message": {"role": "user", "content": "Aufgabe"}}

        lines, _changed = self.translate(event)

        self.assertEqual([], lines)

    # 4. Name: test_pi_tool_start_update_end_become_tool_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: bash-Werkzeugereignisse
    #    gemäß Pi-Doku (args.command). Erwartung: Start "[Werkzeug] bash —
    #    läuft: ls -la"; Ende "[Werkzeug] bash — abgeschlossen"; bei
    #    isError dementsprechend "— Fehler". Keine Zustandsänderung.
    def test_pi_tool_start_update_end_become_tool_lines(self):
        start = {"type": "tool_execution_start", "toolCallId": "call_bash1",
                 "toolName": "bash", "args": {"command": "ls -la"}}
        ok = {"type": "tool_execution_end", "toolCallId": "call_bash1",
              "toolName": "bash",
              "result": {"content": [{"type": "text", "text": "Datei1"}]},
              "isError": False, "durationMs": 4}
        bad = {"type": "tool_execution_end", "toolCallId": "call_bash2",
               "toolName": "bash", "result": {"content": []}, "isError": True}

        start_lines, changed = self.translate(start)
        ok_lines, _ = self.translate(ok)
        bad_lines, _ = self.translate(bad)

        self.assertIn("[Werkzeug] bash — läuft: ls -la", start_lines)
        self.assertTrue(any(
            line.startswith("[Werkzeug] bash —") and "abgeschlossen" in line
            for line in ok_lines), f"Ende-Zeile falsch: {ok_lines}")
        self.assertTrue(any(
            line.startswith("[Werkzeug] bash —") and "Fehler" in line
            for line in bad_lines), f"Fehler-Zeile fehlt: {bad_lines}")
        self.assertEqual(
            {"session": "", "subagents": []},
            self.state,
            "Einfache Werkzeugausführung darf keine Subagenten erfinden",
        )

    # 5. Name: test_pi_streaming_and_noise_events_produce_nothing [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_update deltas,
    #    turn_start/turn_end, agent_start/agent_end/agent_settled,
    #    queue_update, compaction_start. Erwartung: keine Zeilen, keine
    #    Zustandsänderung (delta-freie Meldung, „Rauschen" bleibt draußen).
    def test_pi_streaming_and_noise_events_produce_nothing(self):
        noise = [
            {"type": "message_update", "usage": {},
             "assistantMessageEvent": {"type": "text_delta",
                                       "contentIndex": 0, "delta": "Hello "}},
            {"type": "turn_start"},
            {"type": "turn_end", "message": {"role": "assistant", "content": []},
             "toolResults": []},
            {"type": "agent_start"},
            {"type": "agent_end", "messages": [], "willRetry": False},
            {"type": "agent_settled", "aborted": False},
            {"type": "queue_update", "steering": [], "followUp": []},
            {"type": "compaction_start", "reason": "threshold"},
        ]
        for event in noise:
            lines, changed = self.translate(event)
            self.assertEqual([], lines, f"Zeilen bei {event.get('type')}")
            self.assertFalse(changed, f"Zustandsänderung bei {event.get('type')}")

        self.assertEqual(
            {"session": "", "subagents": []}, self.state,
            "Rauschereignisse dürfen den Zustand nicht verändern")

    # 6. Name: test_pi_events_without_lines_have_empty_state [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: unknown Ereignistype.
    #    Erwartung: keine Zeilen, keine Zustandsänderung.
    def test_pi_events_without_lines_have_empty_state(self):
        lines, changed = self.translate({"type": "unbekannt"})

        self.assertEqual([], lines)
        self.assertFalse(changed)
        self.assertEqual({"session": "", "subagents": []}, self.state)


class PiSubagentCaptureTest(PiTranslateFixture):
    """AK3: Pi-Subagentenerfassung — Eintrag mit toolCallId als
    Tab-Schlüssel (session), Statusfortschritt und Ausgabeerfassung."""

    # 1. Name: test_pi_task_start_creates_running_entry_with_toolcall_session
    #    [AK3] Vorbedingung: leerer Zustand. Aktion:
    #    tool_execution_start für "task" mit agent/description/prompt.
    #    Erwartung: genau ein Eintrag: session == toolCallId, agent,
    #    description, prompt, status "running", started numerisch, ended 0,
    #    output "".
    #    Fehlerfall: kein Eintrag, falscher Schlüssel oder erfundene Felder.
    def test_pi_task_start_creates_running_entry_with_toolcall_session(self):
        event = pi_task_events()[0]

        _lines, changed = self.translate(event)

        self.assertTrue(changed, "Der neue Eintrag muss als Änderung gelten")
        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Genau ein Eintrag: {entries}")
        entry = entries[0]
        self.assertEqual(TOOL_CALL, entry.get("session"),
                         "toolCallId ist der Tab-Schlüssel (session)")
        self.assertEqual("general", entry.get("agent"))
        self.assertEqual("Testzusammenfassung", entry.get("description"))
        self.assertEqual("Sammle Infos", entry.get("prompt"))
        self.assertEqual("running", entry.get("status"))
        self.assertIsInstance(entry.get("started"), int, "started numerisch")
        self.assertEqual(0, entry.get("ended"), "ended bleibt bis zum Ende 0")

    # 2. Name: test_pi_task_update_captures_partial_result [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: update mit
    #    partialResult (Text). Erwartung: erfasste Ausgabe enthält den
    #    Teilttext; Status bleibt "running"; genau ein Eintrag.
    def test_pi_task_update_captures_partial_result(self):
        self.translate(pi_task_events()[0])
        update = pi_task_events()[1]

        self.translate(update)

        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Kein Doppeltab: {entries}")
        self.assertIn("Teilausgabe", str(entries[0].get("output")))
        self.assertEqual("running", entries[0].get("status"))

    # 3. Name: test_pi_task_end_records_text_output_and_completed_status [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: end mit result
    #    (zwei Text-Blöcke), isError false. Erwartung: status "completed",
    #    Ausgabe = Blocktexte zeilenweise mit \n verbunden ("PONG\n
    #    Zweitzeile"), ended numerisch und ungleich 0.
    def test_pi_task_end_records_text_output_and_completed_status(self):
        self.translate(pi_task_events()[0])
        end = pi_task_events()[2]

        _lines, changed = self.translate(end)

        self.assertTrue(changed, "Der Abschluss muss als Änderung gelten")
        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Kein Doppeltab: {entries}")
        entry = entries[0]
        self.assertIn("PONG\nZweitzeile", str(entry.get("output")))
        self.assertEqual("completed", entry.get("status"))
        self.assertIsInstance(entry.get("ended"), int)
        self.assertNotEqual(0, entry.get("ended"), "ended beim Abschluss gesetzt")

    # 4. Name: test_pi_failed_task_marks_error_status [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: end mit isError
    #    true. Erwartung: status "error", ended gesetzt.
    def test_pi_failed_task_marks_error_status(self):
        self.translate(pi_task_events()[0])
        end = {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
               "toolName": "task", "result": {"content": [], "details": {}},
               "isError": True}

        self.translate(end)

        entry = self.state["subagents"][0]
        self.assertEqual(
            "error", entry.get("status"),
            f"isError muss den Fehlerstatus setzen: {entry}")
        self.assertNotEqual(0, entry.get("ended"))

    # 5. Name: test_pi_subagent_tool_alias_is_captured_too [AK3]
    #    Vorbedingung: leerer Zustand. Aktion: toolName "subagent".
    #    Erwartung: wie "task"; kein zweiter Eintrag bei Start/Ende.
    def test_pi_subagent_tool_alias_is_captured_too(self):
        start = {"type": "tool_execution_start", "toolCallId": TOOL_CALL,
                 "toolName": "subagent",
                 "args": {"agent": "review", "description": "Prüfung"}}
        end = {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
               "toolName": "subagent", "result": {"content":
               [{"type": "text", "text": "FERTIG"}]}, "isError": False}

        self.translate(start)
        self.translate(end)

        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Alias darf keinen Doppeltab geben: {entries}")
        self.assertEqual("review", entries[0].get("agent"))
        self.assertEqual("completed", entries[0].get("status"))
        self.assertIn("FERTIG", str(entries[0].get("output")))

    # 6. Name: test_pi_plain_tool_execution_invents_no_entries [AK3]
    #    Vorbedingung: leerer Zustand. Aktion: bash falls start/update/end.
    #    Erwartung: kein erfasster Subagent-Eintrag (keine Attrappen).
    def test_pi_plain_tool_execution_invents_no_entries(self):
        for event in pi_events():
            self.translate(json.loads(event))

        self.assertEqual([], self.state["subagents"],
                         "Einfache Werkzeuge dürfen keinen Tab-Eintrag erzeugen")


class PiStreamFormTest(unittest.TestCase):
    """AK1: stream_events erkennt die Ereignisform automatisch und gibt
    alles in Klartext aus; Nicht-JSON-Zeilen passieren unverändert."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = str(Path(self.tmp.name) / "lauf.log.state.json")

    def stream(self, payload, state_path=None):
        collected = []
        vibe_runs.stream_events(
            io.StringIO(payload), collected.append,
            state_path or self.state_path,
        )
        return collected

    # 1. Name: test_stream_passes_non_json_lines_through_unchanged [AK1]
    #    Vorbedingung: keine Zustandsdatei. Aktion: Klartextzeile über
    #    stream_events. Erwartung: unverändert wiedergegeben.
    def test_stream_passes_non_json_lines_through_unchanged(self):
        lines = self.stream(PI_PLAIN + "\n")

        self.assertEqual([PI_PLAIN], lines)

    # 2. Name: test_stream_broken_json_keeps_opencode_prefix [AK1]
    #    Vorbedingung: keine Zustandsdatei. Aktion: defekte JSON-Zeile.
    #    Erwartung: Zeile mit Präfix "opencode: " (bisheriges Rückfall-
    #    verhalten bleibt bestehen, auch wenn die Form nicht erkennbar ist).
    def test_stream_broken_json_keeps_opencode_prefix(self):
        lines = self.stream(PI_BROKEN + "\n")

        self.assertEqual(["opencode: " + PI_BROKEN], lines)

    # 3. Name: test_stream_recognizes_pi_stream_and_translates_all_events
    #    [AK1] Vorbedingung: keine Zustandsdatei. Aktion: vollständiges
    #    Pi-Szenario (Session, Text/Denken, bash, task). Erwartung: alle
    #    Ereignisse als Klartextzeilen, kein Roh-JSON, kein erfundener Text; die
    #    Zustandsdatei enthält den erfassten Eintrag und keinen
    #    ephemere Sessionschlüssel.
    def test_stream_recognizes_pi_stream_and_translates_all_events(self):
        payload = "\n".join(
            pi_events() + "\n".join(map(json.dumps, pi_task_events())).splitlines()
        )
        lines = self.stream(payload + "\n")

        expected_without_tool_content = [
            "[Session] " + PI_SESSION,
            "[Denken] nachdenkliche Zeile",
            "Hallo",
            "Welt",
        ]
        for index, candidate in enumerate(expected_without_tool_content):
            self.assertEqual(
                candidate, lines[index],
                f"Zeile {index} falsch: {lines}",
            )
        self.assertFalse(
            [line for line in lines if line.startswith("{")],
            f"Roh-JSON im Klartextstream: {lines}",
        )
        self.assertTrue(
            any("Werkzeug" in line for line in lines),
            "Werkzeugereignisse müssen im Klartextstream erscheinen",
        )

        state = vibe_runs.load_subagent_state(self.state_path)
        entries = state["subagents"]
        self.assertEqual(
            1, len(entries), f"Genau der task-Eintrag erfasst: {state}")
        self.assertEqual(TOOL_CALL, entries[0].get("session"))
        self.assertEqual("completed", entries[0].get("status"))
        self.assertEqual("PONG\nZweitzeile", entries[0].get("output"))
        self.assertEqual(
            "", state["session"],
            "Die ephemere Pi-Session darf nie als Hauptsession landen")

    # 4. Name: test_stream_mixed_pi_prefix_does_not_clobber_opencode_session
    #    [AK2] Vorbedingung: opencode-Zustand mit erfasster Sitzung.
    #    Aktion: opencode-Ereignisse gefolgt von einem Pi-Session-Header.
    #    Erwartung: die erfasste opencode-Hauptsitzung wird nicht durch die
    #    ephemere Pi-Kennung überschrieben.
    def test_stream_mixed_pi_prefix_does_not_clobber_opencode_session(self):
        opencode = ('{"type":"text","sessionID":"ses_mop",'
                    '"part":{"type":"text","text":"Bis hierher"}}')
        payload = opencode + "\n" + pi_events()[0] + "\n"
        self.stream(payload)

        state = vibe_runs.load_subagent_state(self.state_path)
        self.assertEqual(
            "ses_mop", state["session"],
            "Pi-Session darf die beibehaltene opencode-Hauptsession nicht "
            "überschreiben: " + json.dumps(state, ensure_ascii=False))


class OpencodeRegressionTest(PiStreamFormTest):
    """AK2: opencode-Verhalten unverändert — bestehende opencode-
    Fixturszenarien produzieren byte-gleiche Protokollzeilen und Zustands-
    datei (Fixtur durch Übersetzen des unveränderten Produktcodes bei der
    Baseline ermittelt und als Literale fixiert)."""

    # Fixtur der opencode-Ereignisse, wie die opencode-Lauftests sie
    # prüfen (z. B. tests/unit/test_output_view_f19_runner.py): Text,
    # Reasoning, Werkzeug, Subagent-Abschluss. Erwartete Zeilen = exakt die
    # Ausgabe der unveränderten translate_event an der Baseline.
    OPENCODE_EVENTS = (
        '{"type":"text","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Zunaechst schaue ich ins Verzeichnis"}}\n'
        '{"type":"reasoning","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Gedanke eins\\nGedanke zwei"}}\n'
        '{"type":"tool_use","sessionID":"ses_main","part":{"tool":"bash",'
        '"state":{"status":"running","input":{"command":"ls -la"}}}}\n'
        '{"type":"tool_use","sessionID":"ses_main","part":{"tool":"subagent",'
        '"state":{"status":"completed","input":{"agent":"general",'
        '"description":"Testzusammenfassung","prompt":"Sammle Infos"},'
        '"output":"PONG"},"metadata":{"metadata":{"sessionID":"ses_child"}}}}\n'
        '{"type":"error","sessionID":"ses_main",'
        '"error":{"data":{"message":"Boom"}}}\n'
        '{"type":"text","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Fertig"}}\n'
    )

    OPENCODE_EXPECTED_LINES = [
        "[Session] ses_main",
        "Zunaechst schaue ich ins Verzeichnis",
        "[Denken] Gedanke eins",
        "[Denken] Gedanke zwei",
        "[Werkzeug] bash \u2014 running: ls -la",
        "[Subagent] general: Testzusammenfassung \u2014 completed",
        "PONG",
        "[Fehler] Boom",
        "Fertig",
    ]

    # 1. Name: test_stream_opencode_events_byte_identical [AK2]
    #    Vorbedingung: keine Zustandsdatei. Aktion: das opencode-Fixtur-
    #    Szenario über den automatisch erkennenden Stream. Erwartung:
    #    byte-gleiche Protokollzeilen zur bisherigen Übersetzung (Liste
    #    zeilengleich identisch) und die erfasste Sessionsdatei mit
    #    Hauptsession und Ausbildung.
    def test_stream_opencode_events_byte_identical(self):
        lines = self.stream(self.OPENCODE_EVENTS)

        self.assertEqual(
            self.OPENCODE_EXPECTED_LINES, lines,
            "Die automatische Formerkennung darf das opencode-Verhalten "
            "nicht verändern",
        )
        state = vibe_runs.load_subagent_state(self.state_path)
        self.assertEqual("ses_main", state["session"])
        entries = state["subagents"]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual({
            "session": "ses_child",
            "agent": "general",
            "description": "Testzusammenfassung",
            "prompt": "Sammle Infos",
            "status": "completed",
            "ended": entry.get("ended"),
            "started": entry.get("started"),
            "output": "PONG",
        }, entry)
        self.assertIsInstance(entry.get("started"), int)
        self.assertIsInstance(entry.get("ended"), int)

    # 2. Name: test_stream_mixed_opencode_input_keeps_behavior [AK2]
    #    Vorbedingung: wie 1, plus Nicht-JSON-Zeile und defektes JSON im
    #    selben Stream. Erwartung: Nicht-JSON unverändert, defekt mit
    #    "opencode: "-Präfix, übersetzte Ereignisse unverändert.
    def test_stream_mixed_opencode_input_keeps_behavior(self):
        payload = (
            self.OPENCODE_EVENTS
            + PI_PLAIN + "\n"
            + PI_BROKEN + "\n"
        )

        lines = self.stream(payload)

        self.assertEqual(
            self.OPENCODE_EXPECTED_LINES + [PI_PLAIN, "opencode: " + PI_BROKEN],
            lines,
        )


class PiSubagentApiFixture(unittest.TestCase):
    """Startet das echte Dashboard (bin/vibe-web.py) im isolierten VIBE-Root
    auf einem freien Port (Muster: tests/unit/test_f24_output_agent_ui.py).
    Die Zustandsdatei entsteht ausschließlich über das echte Übersetzungs-
    werkzeug bin/vibe_runs.py stream — dieselbe Quelle wie ein echter Läufer.
    Keine Modellaufrufe, keine externen Dienste (nur localhost)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        cls.log_dir = cls.root / "_logs"
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_STATE": str(cls.root / "_toolchain"),
            "HOME": str(cls.root / "home"),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        (cls.root / "tmp").mkdir(parents=True)
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log.name)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
        finally:
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        state = self.log_dir / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def stream_pi_events(self):
        """Vorbedingung: der echte Übersetzungsfilter verarbeitet das
        Pi-Szenario (denselben Weg wie der echte Läufer)."""
        payload = "\n".join(
            pi_events() + "\n".join(map(json.dumps, pi_task_events())).splitlines()
        ) + "\n"
        result = subprocess.run(
            [sys.executable, str(RUNS_PY), "stream",
             "--state", str(self.state_path())],
            env=self.env,
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung fehlgeschlagen: " + result.stdout + result.stderr)

    def call_pi_run(self):
        """Aktion: das Pi-Fixtur-Szenario durch den echten Läufer-Filter."""
        return self.stream_pi_events()

    def state_path(self):
        return self.log_dir / "proj.log.state.json"

    def get(self, path):
        """Fachliche Abfrage: GET an die UI-API mit Token (Header und
        t=-Parameter, wie die Oberfläche die Route aufrufen darf)."""
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=15)
        headers = {"X-Token": self.token}
        try:
            connection.request("GET", path + ("&t=" if "?" in path else "?t=") + self.token, headers=headers)
            response = connection.getresponse()
            body = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            return response.status, payload, body
        finally:
            connection.close()


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PiSubagentApiTest(PiSubagentApiFixture):
    """AK3: Die unveränderte UI-API arbeitet mit den aus Pi-Ereignissen
    erfassten Zustandsdaten."""

    # 1. Name: test_pi_captured_subagent_appears_in_ui_api [AK3]
    #    Vorbedingung: Pi-Szenario vom echten Übersetzungsfilter in die
    #    Zustandsdatei erfasst. Aktion: GET /api/subagents?name=proj.
    #    Erwartung: 200/ok; der Tab-Eintrag erscheint mit session ==
    #    toolCallId, status "completed", Agent und Beschreibung sowie
    #    erfasster Ausgabe.
    def test_pi_captured_subagent_appears_in_ui_api(self):
        self.call_pi_run()

        status, data, raw = self.get("/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        entries = data.get("subagents") or []
        self.assertEqual(
            1, len(entries), f"Genau der erfasste Eintrag: {raw}")
        entry = entries[0]
        self.assertEqual(TOOL_CALL, entry.get("session"), raw)
        self.assertEqual("completed", entry.get("status"), raw)
        self.assertEqual("general", entry.get("agent"), raw)
        self.assertEqual("Testzusammenfassung", entry.get("description"), raw)
        self.assertIn("PONG", str(entry.get("output") or ""), raw)
        self.assertEqual(
            "", data.get("session", ""),
            "Die ephemere Pi-Session darf der API nicht als erfasste "
            "Hauptsitzung gemeldet werden: " + raw)

    # 2. Name: test_pi_subagent_output_served_by_ui_api [AK3]
    #    Vorbedingung: wie 1. Aktion: GET /api/subagent-output mit der
    #    toolCallId-Session. Erwartung: ok, Text enthält "PONG\nZweitzeile",
    #    Status "completed".
    def test_pi_subagent_output_served_by_ui_api(self):
        self.call_pi_run()

        status, data, raw = self.get(
            "/api/subagent-output?name=proj&session=" + TOOL_CALL)
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertIn("PONG", data.get("text", ""), raw)
        self.assertIn("Zweitzeile", data.get("text", ""), raw)
        self.assertEqual("completed", data.get("status"), raw)


if __name__ == "__main__":
    unittest.main()
