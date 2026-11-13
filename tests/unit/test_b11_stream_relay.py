"""Unit-Abnahme B11 (Teil 2): Live-Erfassung von Subagenten im Stream-Filter.

Arbeitspaket B11, Punkt 7: Sandbox-Läufe verwenden ``--standalone``; der
gemeinsame Dashboard-Server läuft dann oft gar nicht. Der Stream-Filter
(``bin/vibe_runs.py stream``) muss Subagenten deshalb **zusätzlich live aus
dem Ereignisstrom** erfassen:

* Ereignisse mit einer sessionID, die nicht die Hauptsession ist, legen einen
  laufenden Subagenten an und akkumulieren dessen Teilausgabe aus
  ``text``-, ``reasoning``- und ``tool_use``-Ereignissen.
* Der Abschluss kommt weiterhin über das bestehende ``task``/``completed``-
  Ereignis (Werkzeug ``task`` oder ``subagent``, Status ``completed`` mit
  der Kind-Session in ``state.metadata``).
* Ereignisse, die der Harness nicht liefert, erzeugen keine Subagenten
  („keine erfundenen Subagenten“). Defekte JSON-Zeilen beschädigen weder den
  Stream noch den Zustand.
* Die Zustandsdatei wächst nicht unbegrenzt: Die Zahl der Einträge bleibt
  auch nach vielen abgeschlossenen Subagenten begrenzt, laufende Einträge
  bleiben erhalten. Als praktische Obergrenze legt dieser Test 50 Einträge
  und 256 KiB Dateigröße fest.

Testfälle:

1. test_child_session_events_create_a_running_subagent_with_output   [AK7]
   Vorbedingung: leerer Zustand; zuerst ein Hauptsession-Ereignis.
   Aktion: text-, reasoning- und tool_use-Ereignis einer fremden Session.
   Erwartung: Hauptsession bleibt unverändert; genau ein laufender Eintrag
   mit dieser Session, ``started`` gesetzt, ``ended`` 0; Teilausgabe enthält
   Text, ``[Denken]`` und ``[Werkzeug]`` samt Detail.
   Fehlerfall: Kein Eintrag, Hauptsession wird überschrieben oder Ausgabe
   geht verloren.
2. test_two_child_sessions_are_tracked_in_parallel                     [AK7]
   Vorbedingung: Hauptsession erfasst.
   Aktion: verschachtelte Ereignisse zweier fremder Sessions.
   Erwartung: Zwei laufende Einträge mit getrennten, vollständigen Ausgaben;
   keine Ausgabe des einen beim anderen.
   Fehlerfall: Ein Eintrag fehlt, Ausgaben vermischt oder ein Eintrag für die
   Hauptsession erfunden.
3. test_task_completion_ends_the_matching_child_only                 [AK7]
   Vorbedingung: zwei laufende Kinder aus dem Ereignisstrom.
   Aktion: bestehendes task/completed-Ereignis der Hauptsession mit der
   Kind-Session A.
   Erwartung: A ist ``completed`` mit ``ended`` ungleich 0; B bleibt
   ``running`` mit ``ended`` 0.
   Fehlerfall: Abschluss wird ignoriert, falsches Kind beendet oder beide.
4. test_events_without_child_sessions_invent_no_subagents             [AK7]
   Vorbedingung: leerer Zustand.
   Aktion: ausschließlich Ereignisse der Hauptsession (Text, Denken,
   gewöhnliches Werkzeug).
   Erwartung: Kein Subagenteneintrag; Hauptsession bleibt erfasst.
   Fehlerfall: Der Filter erfindet Subagenten.
5. test_broken_lines_do_not_break_capture                             [AK7]
   Vorbedingung: Hauptsession erfasst.
   Aktion: defekte JSON-Zeile, danach ein Kind-Ereignis.
   Erwartung: Kein Absturz; das Kind wird erfasst, die defekte Zeile bleibt
   im Klartext sichtbar, die Zustandsdatei ist gültiges JSON.
   Fehlerfall: Abbruch, verlorene Erfassung oder beschädigter Zustand.
6. test_state_file_stays_bounded_with_many_finished_subagents        [AK6/7]
   Vorbedingung: Hauptsession erfasst.
   Aktion: 60 abgeschlossene Kind-Subagenten mit je 3 000 Zeichen Ausgabe,
   danach ein weiterer laufender Subagent.
   Erwartung: Höchstens 50 Einträge, Datei unter 256 KiB, der laufende
   Eintrag ist vorhanden.
   Fehlerfall: Unbegrenztes Wachstum oder Verlust des laufenden Eintrags.

7. test_attempt_pins_the_first_session_and_takes_others_as_children
   [AK7, Review Minor 2]
   Vorbedingung: leerer Zustand; Filter wird mit ``attempt=True``
   aufgerufen (wie der Produktionspfad).
   Aktion: Strom 1 pinnt ses_versuch_eins und erfasst ses_kind_a als Kind;
   Strom 2 (neuer Aufruf) mit ses_versuch_zwei.
   Erwartung: Erstes Ereignis pinnt die Hauptsession des Versuchs; das
   Kind wird laufend erfasst; der zweite Versuch ersetzt die Hauptsession,
   ohne ein Kind zu erzeugen.
   Fehlerfall: Kind als Hauptsession oder zweiter Versuch als Kind.
8. test_huge_child_output_is_kept_only_as_a_tail      [AK7, Review Medium 3]
   Vorbedingung: Hauptsession erfasst; ein Kind läuft.
   Aktion: Kind-Ausgabe deutlich über 64 KiB (ANFANG … ENDE), dann Abschluss.
   Erwartung: gespeicherte Ausgabe ist ein Tail von höchstens 64 KiB
   (Anfang verworfen, Ende erhalten); Zustandsdatei unter 256 KiB.
   Fehlerfall: Unbegrenztes Wachstum oder Verlust des Endes.

Der Filter wird direkt über ``vibe_runs.stream_events`` mit einem
synthetischen JSONL-Strom (``io.StringIO``) aufgerufen. Keine Modellaufrufe,
keine externen Dienste.
"""
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))

import vibe_runs  # noqa: E402

MAIN_SESSION = "ses_main_b11"
CHILD_A = "ses_kind_a"
CHILD_B = "ses_kind_b"
RUNNING_C = "ses_kind_laufend"


def text_event(session, text):
    return {"type": "text", "sessionID": session,
            "part": {"type": "text", "text": text}}


def reasoning_event(session, text):
    return {"type": "reasoning", "sessionID": session,
            "part": {"type": "text", "text": text}}


def tool_event(session, tool, command):
    return {"type": "tool_use", "sessionID": session,
            "part": {"tool": tool,
                     "state": {"status": "running",
                               "input": {"command": command}}}}


def completed_task_event(session, child, output):
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "tool": "task",
            "state": {
                "status": "completed",
                "input": {"agent": "general", "description": "Kind " + child},
                "metadata": {"metadata": {"sessionID": child}},
                "output": output,
            },
        },
    }


class StreamRelayFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "proj.log.state.json"

    def feed(self, events, raw_lines=()):
        payload = "\n".join([json.dumps(event, ensure_ascii=False)
                             for event in events] + list(raw_lines)) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(self.state_path))
        return emitted

    def state(self):
        return vibe_runs.load_subagent_state(str(self.state_path))

    def entry(self, session):
        return next((item for item in self.state()["subagents"]
                     if item.get("session") == session), None)

    def establish_main(self):
        self.feed([text_event(MAIN_SESSION, "Hauptagent arbeitet")])


class LiveChildCaptureTest(StreamRelayFixture):
    """AK7: fremde sessionID -> laufender Subagent mit Teilausgabe."""

    def test_child_session_events_create_a_running_subagent_with_output(self):
        """AK7: Kind-Ereignisse erzeugen einen laufenden Subagenten.

        Vorbedingung: leerer Zustand, Hauptsession-Ereignis zuerst.
        Aktion: Text, Denken und Werkzeug des Kindes ses_kind_a.
        Erwartung: Hauptsession bleibt ses_main_b11; ein Eintrag ses_kind_a,
        Status running, ended 0; Ausgabe enthält Text, "[Denken] " und
        "[Werkzeug] bash" samt "ls -la".
        Fehlerfall: Kein Eintrag, überschriebene Hauptsession oder fehlende
        Teilausgabe.
        """
        self.establish_main()

        self.feed([
            text_event(CHILD_A, "Teilausgabe A"),
            reasoning_event(CHILD_A, "Kind denkt nach"),
            tool_event(CHILD_A, "bash", "ls -la"),
        ])

        state = self.state()
        self.assertEqual(
            MAIN_SESSION, state["session"],
            "Die Hauptsession wurde durch Kind-Ereignisse überschrieben: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(
            entry, "Für die Kind-Session wurde kein laufender Subagent "
                   "angelegt: " + json.dumps(state, ensure_ascii=False))
        self.assertEqual("running", entry.get("status"), entry)
        self.assertEqual(0, entry.get("ended"), entry)
        self.assertIsInstance(entry.get("started"), int, entry)
        output = str(entry.get("output") or "")
        for expected in ("Teilausgabe A", "[Denken] Kind denkt nach",
                         "[Werkzeug] bash", "ls -la"):
            self.assertIn(expected, output,
                          f"Teilausgabe {expected!r} fehlt in {output!r}")

    def test_two_child_sessions_are_tracked_in_parallel(self):
        """AK7: zwei parallele Kinder werden getrennt erfasst.

        Vorbedingung: Hauptsession erfasst.
        Aktion: verschachtelte Text-/Werkzeugereignisse von ses_kind_a und
        ses_kind_b.
        Erwartung: zwei laufende Einträge; A-Ausgabe nur in A, B-Ausgabe nur
        in B; kein Eintrag für die Hauptsession.
        Fehlerfall: Eintrag fehlt, Ausgaben vermischt oder Hauptsession als
        Subagent erfunden.
        """
        self.establish_main()

        self.feed([
            text_event(CHILD_A, "A-ERSTE-4711"),
            text_event(CHILD_B, "B-ERSTE-4711"),
            reasoning_event(CHILD_A, "A-DENKEN-4711"),
            tool_event(CHILD_B, "bash", "b-command-4711"),
            text_event(CHILD_A, "A-ZWEITE-4711"),
        ])

        entries = {item.get("session"): item
                   for item in self.state()["subagents"]}
        self.assertEqual(
            {CHILD_A, CHILD_B}, set(entries),
            "Nicht genau die beiden laufenden Kinder wurden erfasst: "
            + json.dumps(list(entries), ensure_ascii=False))
        output_a = str(entries[CHILD_A].get("output") or "")
        output_b = str(entries[CHILD_B].get("output") or "")
        self.assertIn("A-ERSTE-4711", output_a, output_a)
        self.assertIn("A-ZWEITE-4711", output_a, output_a)
        self.assertIn("[Denken] A-DENKEN-4711", output_a, output_a)
        self.assertNotIn("B-ERSTE-4711", output_a,
                         "Ausgabe von B landete bei A: " + output_a)
        self.assertIn("B-ERSTE-4711", output_b, output_b)
        self.assertIn("b-command-4711", output_b, output_b)
        self.assertNotIn("A-ERSTE-4711", output_b,
                         "Ausgabe von A landete bei B: " + output_b)
        self.assertEqual("running", entries[CHILD_A].get("status"), entries)
        self.assertEqual("running", entries[CHILD_B].get("status"), entries)

    def test_task_completion_ends_the_matching_child_only(self):
        """AK7: task/completed beendet genau das zugehörige Kind.

        Vorbedingung: ses_kind_a und ses_kind_b laufen aus dem Ereignisstrom.
        Aktion: task/completed-Ereignis der Hauptsession mit Kind A.
        Erwartung: A completed mit ended ungleich 0, B weiter running mit
        ended 0; Hauptsession unverändert.
        Fehlerfall: Abschluss ignoriert, falsches Kind oder beide beendet.
        """
        self.establish_main()
        self.feed([text_event(CHILD_A, "A-läuft"),
                   text_event(CHILD_B, "B-läuft")])

        self.feed([completed_task_event(MAIN_SESSION, CHILD_A, "FERTIG-A")])

        entry_a = self.entry(CHILD_A)
        entry_b = self.entry(CHILD_B)
        self.assertIsNotNone(entry_a, "Kind A fehlt")
        self.assertIsNotNone(entry_b, "Kind B fehlt")
        self.assertEqual("completed", entry_a.get("status"),
                         f"Kind A wurde nicht abgeschlossen: {entry_a}")
        self.assertNotEqual(0, entry_a.get("ended"), entry_a)
        self.assertEqual("running", entry_b.get("status"),
                         f"Kind B wurde fälschlich beendet: {entry_b}")
        self.assertEqual(0, entry_b.get("ended"), entry_b)
        self.assertIn("B-läuft", str(entry_b.get("output") or ""), entry_b)
        self.assertEqual(MAIN_SESSION, self.state()["session"])


class NoInventionTest(StreamRelayFixture):
    """AK7: ohne Kind-Ereignisse entstehen keine Subagenten."""

    def test_events_without_child_sessions_invent_no_subagents(self):
        """AK7: nur Hauptsession-Ereignisse erzeugen keine Subagenten.

        Vorbedingung: leerer Zustand.
        Aktion: Text, Denken und gewöhnliches Werkzeug der Hauptsession.
        Erwartung: Kein Subagenteneintrag; Hauptsession bleibt erfasst.
        Fehlerfall: Erfundene Subagenten.
        """
        self.feed([
            text_event(MAIN_SESSION, "Haupttext"),
            reasoning_event(MAIN_SESSION, "Hauptdenken"),
            tool_event(MAIN_SESSION, "bash", "git status"),
        ])

        state = self.state()
        self.assertEqual(MAIN_SESSION, state["session"], state)
        self.assertEqual([], state["subagents"],
                         "Der Filter hat Subagenten erfunden: "
                         + json.dumps(state, ensure_ascii=False))


class RobustnessTest(StreamRelayFixture):
    """AK7: defekte Zeilen schaden der Erfassung nicht."""

    def test_broken_lines_do_not_break_capture(self):
        """AK7: defekte JSON-Zeile, danach Kind-Ereignis.

        Vorbedingung: Hauptsession erfasst.
        Aktion: Zeile "{kaputt" und anschließend ein Kind-Text.
        Erwartung: Kein Absturz; Kind wird laufend erfasst; die defekte Zeile
        bleibt im Klartext sichtbar; Zustandsdatei ist gültiges JSON.
        Fehlerfall: Ausnahme, verlorene Erfassung oder beschädigter Zustand.
        """
        self.establish_main()

        emitted = self.feed(
            [text_event(CHILD_A, "TROTZ-FEHLER-4711")], raw_lines=["{kaputt"])

        self.assertTrue(any("kaputt" in line for line in emitted),
                        "Die defekte Zeile verschwand aus dem Klartext: "
                        + repr(emitted))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kind nach defekter Zeile nicht erfasst")
        self.assertIn("TROTZ-FEHLER-4711", str(entry.get("output") or ""))
        json.loads(self.state_path.read_text(encoding="utf-8"))


class BoundedStateTest(StreamRelayFixture):
    """AK6/7: Zustandsdatei wächst nicht unbegrenzt."""

    def test_state_file_stays_bounded_with_many_finished_subagents(self):
        """AK6/7: viele abgeschlossene Kinder bleiben begrenzt.

        Vorbedingung: Hauptsession erfasst.
        Aktion: 60 Kinder mit je 3 000 Zeichen Ausgabe abschließen, danach
        ein laufendes Kind.
        Erwartung: höchstens 50 Einträge, Datei unter 256 KiB, laufendes
        Kind vorhanden.
        Fehlerfall: unbegrenztes Wachstum oder Verlust des laufenden
        Eintrags.
        """
        self.establish_main()
        payload = "K" * 3000
        for index in range(60):
            child = f"ses_kind_{index:02d}"
            self.feed([
                text_event(child, payload),
                completed_task_event(MAIN_SESSION, child, payload),
            ])
        self.feed([text_event(RUNNING_C, "LAUFEND-4711")])

        state = self.state()
        entries = state["subagents"]
        self.assertLessEqual(
            len(entries), 50,
            f"Die Zustandsdatei hält {len(entries)} Einträge und wächst "
            f"unbegrenzt: {sorted(item.get('session') for item in entries)[:5]} …")
        size = self.state_path.stat().st_size
        self.assertLess(
            size, 256 * 1024,
            f"Die Zustandsdatei ist mit {size} Bytes unbegrenzt gewachsen")
        running = self.entry(RUNNING_C)
        self.assertIsNotNone(
            running, "Der laufende Subagent wurde beim Begrenzen entfernt")
        self.assertEqual("running", running.get("status"), running)


class AttemptContextTest(StreamRelayFixture):
    """Review Minor 2: Erfassung mit gesetztem ``attempt``-Kontext.

    Der Produktionspfad (``vibe-run.sh``) ruft den Filter immer mit
    ``--attempt`` auf. Diese Fälle prüfen die Pinning- und Kind-Erfassung
    des Versuchsmodus direkt statt nur über die F25-Suite:

    * Das erste Ereignis des Stroms pinnt die Hauptsession des Versuchs.
    * Abweichende Sessions werden als laufende Kinder erfasst.
    * Innerhalb eines Stroms bleibt die Hauptsession bestehen (erstes
      Ereignis gewinnt); ein zweiter Versuch (neuer ``stream_events``-Aufruf)
      ersetzt die Hauptsession („zuletzt gewinnt“), ohne ein Kind zu
      erzeugen.
    """

    VERSUCH_1 = "ses_versuch_eins"
    VERSUCH_2 = "ses_versuch_zwei"

    def feed_attempt(self, events):
        payload = "\n".join(
            json.dumps(event, ensure_ascii=False) for event in events) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(self.state_path),
            attempt=True)
        return emitted

    def test_attempt_pins_the_first_session_and_takes_others_as_children(self):
        """Mit attempt: erstes Ereignis pinnt, Kinder werden erfasst.

        Vorbedingung: leerer Zustand.
        Aktion: Strom 1 (``attempt=True``) mit erstem Ereignis
        ses_versuch_eins, danach Kind ses_kind_a; Strom 2 (neuer Aufruf,
        ``attempt=True``) mit ses_versuch_zwei.
        Erwartung: Nach Strom 1 ist ses_versuch_eins die Hauptsession und
        ses_kind_a ein laufender Eintrag mit Ausgabe; nach Strom 2 ist
        ses_versuch_zwei die Hauptsession, ohne dass dafür ein Kind-Eintrag
        entsteht; das erfasste Kind bleibt erhalten.
        Fehlerfall: Das Kind wird als Hauptsession übernommen, das Kind
        fehlt, oder der zweite Versuch wird als Kind erfasst.
        """
        self.feed_attempt([
            text_event(self.VERSUCH_1, "Versuch eins"),
            text_event(CHILD_A, "Kind arbeitet"),
        ])

        state = self.state()
        self.assertEqual(
            self.VERSUCH_1, state["session"],
            "Das erste Ereignis pinnte nicht die Hauptsession des Versuchs: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(
            entry, "Die abweichende Session wurde nicht als Kind erfasst: "
            + json.dumps(state, ensure_ascii=False))
        self.assertEqual("running", entry.get("status"), entry)
        self.assertIn("Kind arbeitet", str(entry.get("output") or ""), entry)

        self.feed_attempt([text_event(self.VERSUCH_2, "Versuch zwei")])

        state = self.state()
        self.assertEqual(
            self.VERSUCH_2, state["session"],
            "Der zweite Versuch hat die Hauptsession nicht ersetzt: "
            + json.dumps(state, ensure_ascii=False))
        sessions = [item.get("session") for item in state["subagents"]]
        self.assertNotIn(
            self.VERSUCH_2, sessions,
            "Die neue Hauptsession wurde fälschlich als Kind erfasst: "
            + json.dumps(sessions, ensure_ascii=False))
        self.assertIn(
            CHILD_A, sessions,
            "Das zuvor erfasste Kind ging beim Versuchswechsel verloren: "
            + json.dumps(sessions, ensure_ascii=False))


class OutputBudgetTest(StreamRelayFixture):
    """Review Medium 3: Ausgabebudget je Subagent-Eintrag.

    Vereinbarte Semantik: Der gespeicherte ``output`` eines Eintrags bleibt
    auf einen Tail von höchstens 64 KiB begrenzt (Anfang verworfen, Ende
    erhalten). Die Begrenzung betrifft abgelaufene Inhalte; laufende
    Einträge behalten den jeweils letzten Stand. Die Gesamtdatei bleibt
    dadurch begrenzt. ``/api/subagents`` liefert ``output`` höchstens als
    Tail von 4 KiB (eigener Fall in ``test_b11_output_view_api.py``);
    ``/api/subagent-output`` bleibt das vollwertige Live-Pfadangebot.
    """

    TAIL_BUDGET = 64 * 1024

    def test_huge_child_output_is_kept_only_as_a_tail(self):
        """Große Kind-Ausgabe wird nur als 64-KiB-Tail gespeichert.

        Vorbedingung: Hauptsession erfasst; ein Kind läuft.
        Aktion: mehrere Kind-Ereignisse mit zusammen deutlich über 64 KiB
        Ausgabe; das erste enthält ANFANG-4711, das letzte ENDE-4711;
        danach Abschluss mit leerer Ergebnis-Ausgabe.
        Erwartung: Die gespeicherte Ausgabe bleibt auf 64 KiB begrenzt,
        der Anfang ist verworfen, das Ende erhalten; die Zustandsdatei
        bleibt unter 256 KiB; nach dem Abschluss gilt die Begrenzung
        weiterhin und der Eintrag ist ``completed``.
        Fehlerfall: Unbegrenztes Wachstum des ``output``-Felds oder
        Verlust des Endes.
        """
        self.establish_main()

        # Ein Strom wie der Produktionspfad: Hauptsession- und Kind-Ereignisse
        # durchmischt. (Ein Strom mit ausschließlich Text einer einzigen
        # fremden Session wäre laut F25-Kompatibilität ein neuer Versuch und
        # würde die Hauptsession ersetzen.)
        events = [text_event(CHILD_A, "ANFANG-4711 " + "a" * 8000)]
        for index in range(24):
            events.append(text_event(MAIN_SESSION, "Haupt weiter %d" % index))
            events.append(
                text_event(CHILD_A, "BLOCK-%02d-4711 %s" % (index, "b" * 10000)))
        events.append(text_event(MAIN_SESSION, "Haupt fertig"))
        events.append(text_event(CHILD_A, "ENDE-4711"))
        events.append(completed_task_event(MAIN_SESSION, CHILD_A, ""))
        self.feed(events)

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Das Kind wurde nicht erfasst")
        self.assertEqual("completed", entry.get("status"), entry)
        output = str(entry.get("output") or "")
        size = len(output.encode("utf-8"))
        self.assertLessEqual(
            size, self.TAIL_BUDGET,
            "Die gespeicherte Ausgabe ist mit %d Bytes unbegrenzt gewachsen"
            % size)
        self.assertNotIn(
            "ANFANG-4711", output,
            "Der Anfang wurde nicht verworfen (Tail-Semantik)")
        self.assertIn(
            "ENDE-4711", output,
            "Das Ende der Ausgabe ging verloren:\n" + output[-200:])
        state_size = self.state_path.stat().st_size
        self.assertLess(
            state_size, 256 * 1024,
            "Die Zustandsdatei ist mit %d Bytes unbegrenzt gewachsen"
            % state_size)


if __name__ == "__main__":
    unittest.main()
