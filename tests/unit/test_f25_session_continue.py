"""Unit-Abnahme F25: Sessionfortsetzung bei Wiederholung.

Arbeitspaket F25 „einfaches Continue" verlangt, dass eine unterbrochene
Agentensession bei jeder Wiederholung des Paket-Läufers mit
``opencode run --session <Session-ID>`` fortgesetzt wird. Die Hauptsession
kommt aus dem JSON-Ereignisstrom (``opencode --format json``) und liegt
bereits in ``<log>.state.json``; bisher galt dort die erste Session je
Zustandsdatei (Sperre), künftig die zuletzt erfasste. Es werden keine
Modellaufrufe ausgeführt.

Akzeptanzkriterien und Testfälle:

Übersetzungsstufe (vibe_runs.translate_event / stream_events):

* ``test_first_main_session_writes_one_session_line`` —
  Vorbedingung: leerer Zustand. Aktion: ein JSON-Ereignis mit
  ``sessionID`` übersetzen. Erwartung: genau eine Zeile
  ``[Session] <Session-ID>``; die Zustandsdatei hält die Session.
* ``test_same_session_writes_no_second_session_line`` —
  Vorbedingung: Session bereits erfasst. Aktion: erneutes Ereignis mit
  derselben ``sessionID``. Erwartung: keine weitere ``[Session]``-Zeile,
  Zustand unverändert.
* ``test_second_attempt_session_updates_state_last_wins`` —
  Vorbedingung: Zustand hält ``ses_attempt1``. Aktion: Ereignis mit
  abweichender ``sessionID`` (Zweitversuch). Erwartung: neue
  ``[Session]``-Zeile und Zustand = zuletzt erfasste Session („zuletzt
  gewinnt", semantische Änderung gegen die bisherige Erst-Sperre).
* ``test_event_without_main_session_changes_nothing`` —
  Vorbedingung: Zustand mit Session. Aktion: Ereignis ohne/leerer
  ``sessionID``. Erwartung: keine Zeile, keine Änderung.
* ``test_subagent_capture_survives_session_sequence`` —
  Vorbedingung: Ereignisstrom mit Hauptsession und Subagenten.
  Aktion: übersetzen. Erwartung: Subagentenerfassung (F19) bleibt
  vollständig, keine Roh-JSON-Zeilen.
* ``test_stream_last_attempt_session_wins_in_state_file`` —
  Vorbedingung: Zustandsdatei nach erstem Versuch. Aktion: zweiter
  ``stream_events``-Durchlauf mit abweichender ``sessionID`` in dieselbe
  Zustandsdatei. Erwartung: zweite ``[Session]``-Zeile im Ausgaben und
  Zustandsdatei = ``ses_attempt2``.
* ``test_stream_output_stays_free_of_raw_json`` —
  Vorbedingung: leerer Zustand. Aktion: JSON-Ereignis durch den
  Protokollierungsfilter leiten. Erwartung: Ereignistext Klartext,
  ``[Session]``-Zeile, keine Zeile, die mit ``{`` beginnt (F19-Garantie).

Läuferintegration (vibe-run.sh mit opencode-Attrappe):

* ``test_retry_continues_the_captured_session`` —
  Vorbedingung: Projekt mit einem offenen Paket F25, ``MAX_RETRIES=1``,
  Versuchsfolge ``fail`` (Fehlerklasse „other", wiederholbar) und dann
  ``complete``. Aktion: Läufer starten. Erwartung: erster Aufruf ohne
  ``--session``; zweiter Aufruf enthält ``--session ses_attempt1``; der
  Prompt enthält in beiden Versuchen „Arbeitspaket F25"; der Lauf endet
  mit „FERTIG".
* ``test_retry_writes_exactly_one_session_line_per_attempt`` —
  Vorbedingung: wie zuvor. Erwartung: genau je eine Zeile
  ``[Session] ses_attempt1`` und ``[Session] ses_attempt2`` im
  Laufprotokoll.
* ``test_state_file_holds_the_latest_attempt_session`` —
  Vorbedingung: wie zuvor. Erwartung: ``<log>.state.json`` hält nach dem
  Zweitversuch ``ses_attempt2``.
* ``test_retry_without_stream_module_repeats_without_session`` —
  Vorbedingung: Installation ohne ``vibe_runs.py`` (kein
  Protokollierungsfilter). Erwartung: Wiederholung wie bisher — zweiter
  Aufruf ohne ``--session``, vollständiger Prompt, Lauf endet mit
  „FERTIG"; Abbruch nicht zulässig.
* ``test_retry_without_captured_session_repeats_full_prompt`` —
  Vorbedingung: Attrappe liefert keine Session-Ereignisse (FAKE_OUTPUT).
  Erwartung: wie zuvor; ``--session`` wird nie übergeben (auch nicht mit
  leerem Wert).
* ``test_quota_failure_makes_no_second_call_and_no_continuation`` —
  Vorbedingung: Attrappe mit ``FAKE_MODE=quota`` und ``MAX_RETRIES=3``.
  Erwartung: genau ein Agentenaufruf, kein zweiter Versuch, keine
  Wiederholungsmeldung, der Lauf endet blockiert (Exit 1).


Review-Abnahme F25 (Nachbarkriterien des Reviewers):

* ``test_plain_text_session_line_cannot_hijack_the_session`` —
  Vorbedingung: Attrappe liefert je Versuch zuerst das JSON-Ereignis der
  echten Hauptsession ``ses_attempt1`` und darunter eine Agenten-
  Klartextzeile, die selbst mit ``[Session] ses.bogus/versuch-ohne-
  ereignis`` beginnt (Punkt/Schrägstrich, keine Ereignis-Session).
  Erwartung: nur die JSON-erfasste Kennung gewinnt — der zweite Aufruf
  enthält genau ``--session ses_attempt1``, die Klartextzeile bleibt
  unberücksichtigt (steht als Klartext im Protokoll, landet nicht im
  Zustand), Lauf endet mit „FERTIG".
* ``test_third_retry_continues_with_the_latest_captured_session`` —
  Vorbedingung: ``MAX_RETRIES=2`` (drei Versuche), Versuchsfolge
  ``fail,fail,complete``. Erwartung: erster Aufruf ohne ``--session``;
  zweiter Aufruf mit ``--session ses_attempt1``; dritter Aufruf mit der
  im Zweitversuch erfassten Kennung ``ses_attempt2``. Das Fake bildet
  echte Sitzungsdauern nicht nach und erzeugt je Aufruf eine neue
  Kennung, deshalb gilt hier konsequent „zuletzt gewinnt". Alle drei
  Prompts enthalten „Arbeitspaket F25"; je Versuch steht genau eine
  ``[Session]``-Zeile (drei verschiedene Kennungen, keine Duplikate),
  der Lauf endet mit „FERTIG" und die Zustandsdatei hält
  ``ses_attempt3``.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
RUNS = REPO / "bin" / "vibe_runs.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support


def load_module(path, name):
    """Lädt ein bin-Modul als Testunterlage (ohne Installation)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


RUNS_MODULE = load_module(RUNS, "vibe_runs_f25_under_test")

# Review-Abnahme: Agentenklartext, der wie eine [Session]-Zeile beginnt.
DECOY_SESSION_LINE = "[Session] ses.bogus/versuch-ohne-ereignis"


def text_event(session, text="Antwort"):
    """Ereignis wie opencode --format json je Versuch ausgeben."""
    return {
        "type": "text",
        "sessionID": session,
        "part": {"type": "text", "text": text},
    }


def subagent_event(session):
    """Subagentenergebnis, wie es das F19-Testnachahmungen vorgibt."""
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "tool": "subagent",
            "state": {
                "status": "completed",
                "input": {
                    "agent": "general",
                    "description": "Testzusammenfassung",
                    "prompt": "Sammle Infos",
                },
                "output": "PONG",
            },
            "metadata": {"metadata": {"sessionID": "ses_child"}},
        },
    }


class TranslateSessionTest(unittest.TestCase):
    """[Session]-Zeile je erfasster Hauptsession; zuletzt gewinnt."""

    def test_first_main_session_writes_one_session_line(self):
        state = {"session": "", "subagents": []}

        lines, changed = RUNS_MODULE.translate_event(
            text_event("ses_attempt1", "Antwort 1"), state
        )

        self.assertTrue(changed, "Session nicht erfasst")
        self.assertEqual("ses_attempt1", state["session"], state)
        self.assertIn(
            "[Session] ses_attempt1",
            lines,
            f"[Session]-Zeile fehlt: {lines}",
        )

    def test_same_session_writes_no_second_session_line(self):
        state = {"session": "ses_attempt1", "subagents": []}

        lines, changed = RUNS_MODULE.translate_event(
            text_event("ses_attempt1", "Antwort 1"), state
        )

        self.assertFalse(changed, "Same-Session-Ereignis ändert den Zustand")
        self.assertEqual("ses_attempt1", state["session"], state)
        self.assertNotIn(
            "[Session] ses_attempt1", lines, "Doppelte [Session]-Zeile"
        )

    def test_second_attempt_session_updates_state_last_wins(self):
        state = {"session": "ses_attempt1", "subagents": []}

        lines, changed = RUNS_MODULE.translate_event(
            text_event("ses_attempt2", "Antwort 2"), state
        )

        self.assertTrue(changed, "Neue Session nicht übernommen")
        self.assertEqual(
            "ses_attempt2",
            state["session"],
            "Zustand hält nicht die zuletzt erfasste Session (Zweitversuch): "
            + state["session"],
        )
        self.assertIn("[Session] ses_attempt2", lines, lines)

    def test_event_without_main_session_changes_nothing(self):
        state = {"session": "ses_attempt1", "subagents": []}
        for event in ({"type": "text", "part": {"type": "text", "text": "x"}},
                      {"type": "text", "sessionID": "",
                       "part": {"type": "text", "text": "x"}}):
            lines, changed = RUNS_MODULE.translate_event(event, state)

            self.assertFalse(changed, f"Ereignis änderte Zustand: {event}")
            self.assertEqual("ses_attempt1", state["session"], state)
            self.assertTrue(
                all(not line.startswith("[Session]") for line in lines),
                f"[Session]-Zeile ohne Hauptsession: {lines}",
            )

    def test_subagent_capture_survives_session_sequence(self):
        state = {"session": "", "subagents": []}

        lines, changed = RUNS_MODULE.translate_event(
            text_event("ses_attempt1", "Antwort 1"), state
        )
        RUNS_MODULE.translate_event(subagent_event("ses_attempt1"), state)

        self.assertEqual("ses_attempt1", state["session"], state)
        entries = state["subagents"]
        self.assertEqual(1, len(entries), f"Subagenten unvollständig: {state}")
        self.assertEqual("ses_child", entries[0].get("session"), entries)
        self.assertEqual("completed", entries[0].get("status"), entries)
        bad = [line for line in lines if line.lstrip().startswith("{")]
        self.assertEqual(
            [], bad, "Roh-JSON geduldet: " + repr(bad)
        )


class StreamSessionStateTest(unittest.TestCase):
    """Zustandsdatei und Ausgabeprotokoll über zwei Versuchsdurchläufe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state_path = self.root / "proj.log.state.json"
        self.addCleanup(self.tmp.cleanup)

    def feed(self, events):
        """einen Durchlauf durch stream_events geben; Ausgaben sammeln."""
        collected = []
        RUNS_MODULE.stream_events(events, collected.append, str(self.state_path))
        return collected

    def test_stream_last_attempt_session_wins_in_state_file(self):
        first = self.feed([
            json.dumps(text_event("ses_attempt1", "Antwort 1")) + "\n",
        ])

        self.assertIn(
            "[Session] ses_attempt1", first, f"Erste Zeile fehlt: {first}"
        )
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("ses_attempt1", state.get("session"), state)

        second = self.feed([
            json.dumps(text_event("ses_attempt2", "Antwort 2")) + "\n",
        ])

        self.assertIn(
            "[Session] ses_attempt2",
            second,
            f"[Session]-Zeile des Zweitversuchs fehlt: {second}",
        )
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "ses_attempt2",
            state.get("session"),
            "Zustandsdatei hält die Erst-Sperre statt der letzten Session: "
            + repr(state),
        )

    def test_agent_plain_session_lines_pass_through_but_do_not_capture(self):
        """Review-Abnahme: Klartext geht weiter, erfasst wird nur das Ereignis."""

        lines = self.feed([
            json.dumps(text_event("ses_attempt1", "Antwort 1")) + "\n",
            DECOY_SESSION_LINE + "\n",
        ])

        self.assertIn(
            DECOY_SESSION_LINE,
            lines,
            "Agentenklartextzeile muss unverändert ins Protokoll: " + repr(lines),
        )
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "ses_attempt1",
            state.get("session"),
            "Klartextzeile darf die Zustandsdatei nicht bestimmen: "
            + repr(state),
        )

    def test_stream_output_stays_free_of_raw_json(self):
        lines = self.feed([
            json.dumps(text_event("ses_attempt1", "Hallo")) + "\n",
        ])

        self.assertIn("Hallo", lines, f"Ereignistext fehlt: {lines}")
        self.assertIn("[Session] ses_attempt1", lines, lines)
        bad = [line for line in lines if line.lstrip().startswith("{")]
        self.assertEqual(
            [], bad, "Roh-JSON-Zeilen dürfen nicht ins Protokoll: " + repr(bad)
        )


class RunnerSessionContinueFixture(unittest.TestCase):
    """Läufer, opencode-Attrappe und isoliertes Projekt je Testfall."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.write_project(
            feedback="- [ ] F25 Sessionfortsetzung\n  Beschreibung: Test\n"
        )
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.args = self.root / "opencode.args"
        self.fakebin = support.install_fake_tools(self.root)
        self.addCleanup(self.tmp.cleanup)

    def write_project(self, env_text=None, feedback=None):
        env_text = env_text or (
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=1\n"
        )
        support.write_project(
            self.project, env_text,
            feedback=feedback if feedback is not None else (
                "- [ ] F25 Sessionfortsetzung\n  Beschreibung: Test\n"
            ),
        )
        support.commit_all(self.project, "Ausgangsstand")

    def env(self, **extra):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key in (
                    "AGENT", "TESTER", "REVIEWER", "MAX_RETRIES",
                    "VERIFY_QUICK", "VERIFY_FULL", "VERIFY_PACKAGE",
                )
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": "proj",
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_ARGS_PATH": str(self.args),
            }
        )
        env.update(extra)
        return env

    def run_runner(self, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def call_lines(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def arg_records(self):
        records = support.opencode_arg_records(self.args)
        self.assertTrue(records, "opencode wurde nicht aufgerufen")
        return records


class SessionContinueTest(RunnerSessionContinueFixture):
    """Wiederholung nimmt die am ersten Versuch erfasste Session mit."""

    def test_retry_continues_the_captured_session(self):
        result = self.run_runner(FAKE_MODE_SEQUENCE="fail,complete")

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn(
            "FERTIG", log, "Lauf ohne Abnahme:\n" + log + result.stderr
        )
        records = self.arg_records()
        self.assertEqual(
            2, len(records), f"Erwartet zwei Versuche: {self.call_lines()}"
        )
        first, second = records
        self.assertNotIn(
            "--session", first,
            "Erster Versuch startet nicht fortgesetzt: " + repr(first),
        )
        self.assertIn(
            "--session", second,
            "Zweitversuch ohne Fortsetzung: " + repr(second),
        )
        position = second.index("--session")
        self.assertLess(position + 1, len(second), "Wert fehlt")
        self.assertEqual(
            "ses_attempt1",
            second[position + 1],
            "Zweitversuch nimmt nicht die erfasste Session mit: "
            + repr(second),
        )
        self.assertIn(
            "Arbeitspaket F25", first[-1],
            "Erster Prompt unvollständig: " + repr(first[-1]),
        )
        self.assertIn(
            "Arbeitspaket F25", second[-1],
            "Zweitversuch-Prompt unvollständig: " + repr(second[-1]),
        )

    def test_retry_writes_exactly_one_session_line_per_attempt(self):
        result = self.run_runner(FAKE_MODE_SEQUENCE="fail,complete")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        log = self.log_text()
        session_lines = [
            line for line in log.splitlines() if line.startswith("[Session]")
        ]
        self.assertEqual(
            ["[Session] ses_attempt1", "[Session] ses_attempt2"],
            session_lines,
            "Je Versuch genau eine [Session]-Zeile erwartet:\n" + log,
        )
        raw = [
            line for line in log.splitlines() if line.lstrip().startswith("{")
        ]
        self.assertEqual(
            [], raw, "Roh-JSON geduldet:\n" + log
        )

    def test_state_file_holds_the_latest_attempt_session(self):
        result = self.run_runner(FAKE_MODE_SEQUENCE="fail,complete")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        path = self.runtime / "proj.log.state.json"
        self.assertTrue(path.is_file(), "Zustandsdatei fehlt")
        state = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            "ses_attempt2",
            state.get("session"),
            "Zustandsdatei hält nicht die zuletzt erfasste Session: "
            + repr(state),
        )


class PlainRepeatTest(RunnerSessionContinueFixture):
    """Ohne erfasste Session verhält sich die Wiederholung wie bisher."""

    def test_retry_without_stream_module_repeats_without_session(self):
        (self.tool_bin / "vibe_runs.py").unlink()

        result = self.run_runner(FAKE_MODE_SEQUENCE="fail,complete")

        self.assertEqual(
            0, result.returncode,
            "Wiederholung ohne Session darf nicht abbrechen:\n"
            + result.stdout + result.stderr,
        )
        self.assertIn(
            "FERTIG", self.log_text(),
            "Lauf ohne Abnahme:\n" + self.log_text() + result.stderr,
        )
        records = self.arg_records()
        self.assertEqual(2, len(records), self.call_lines())
        for record in records:
            self.assertNotIn(
                "--session", record,
                "Kein --session ohne erfasste Session: " + repr(record),
            )
        self.assertIn(
            "Arbeitspaket F25", records[1][-1],
            "Zweitversuch-Prompt unvollständig: " + repr(records[1][-1]),
        )

    def test_retry_without_captured_session_repeats_full_prompt(self):
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="fail,complete",
            FAKE_OUTPUT="Agentenantwort ohne Session\n",
        )

        self.assertEqual(
            0, result.returncode,
            "Wiederholung ohne Session darf nicht abbrechen:\n"
            + result.stdout + result.stderr,
        )
        self.assertIn("FERTIG", self.log_text())
        records = self.arg_records()
        self.assertEqual(2, len(records), self.call_lines())
        for record in records:
            self.assertNotIn(
                "--session", record,
                "--session wird nie mit fehlender/leerer Session übergeben: "
                + repr(record),
            )
        self.assertIn(
            "Arbeitspaket F25", records[1][-1],
            "Zweitversuch-Prompt unvollständig: " + repr(records[1][-1]),
        )


class NoRetryOnQuotaTest(RunnerSessionContinueFixture):
    """Quota/Kontingent hält an, ohne Zweitversuch und ohne Fortsetzung."""

    def test_quota_failure_makes_no_second_call_and_no_continuation(self):
        result = self.run_runner(FAKE_MODE="quota")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("Quota/Kontingent bei F25", result.stdout)
        records = self.arg_records()
        self.assertEqual(
            1, len(records),
            "Kein zweiter Agentenaufruf bei Quota: " + repr(records),
        )
        self.assertNotIn("--session", records[0])
        log = self.log_text()
        self.assertNotIn(
            "Wiederhole", log, "Fortsetzungsmeldung bei Quota:\n" + log
        )


class DecoySessionLineTest(RunnerSessionContinueFixture):
    """Agentenklartext entführt keine Session; nur Ereignisse zählen."""

    def test_plain_text_session_line_cannot_hijack_the_session(self):
        fake_output = (
            '{"type":"text","sessionID":"ses_attempt1",'
            '"part":{"type":"text","text":"Antwort 1"}}\n'
            + DECOY_SESSION_LINE + "\n"
        )
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="fail,complete", FAKE_OUTPUT=fake_output
        )

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)
        records = self.arg_records()
        self.assertEqual(2, len(records), self.call_lines())
        self.assertNotIn(
            "--session", records[0],
            "Erster Versuch startet nicht fortgesetzt: " + repr(records[0]),
        )
        session_values = [
            record[position + 1]
            for record in records
            for position in range(len(record))
            if record[position] == "--session"
        ]
        self.assertEqual(
            ["ses_attempt1"],
            session_values,
            "Nur die JSON-erfasste Kennung gewinnt (Klartext entführt "
            "nichts): " + repr(records),
        )
        state = json.loads(
            (self.runtime / "proj.log.state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "ses_attempt1",
            state.get("session"),
            "Zustandsdatei hält die Klartext-Attrappe nicht: " + repr(state),
        )
        self.assertIn(
            DECOY_SESSION_LINE,
            log.splitlines(),
            "Die Agentenklartextzeile muss weiterhin ins Protokoll:\n" + log,
        )
        self.assertIn(
            "Arbeitspaket F25", records[1][-1],
            "Zweitversuch-Prompt unvollständig: " + repr(records[1][-1]),
        )


class ThirdAttemptChainTest(RunnerSessionContinueFixture):
    """Dreiversuchskette: „zuletzt gewinnt" über zwei Wiederholungen.

    Das Fake erzeugt je Aufruf eine neue Kennung und bildet echte
    Sitzungsdauern nicht nach; deshalb wird die Erwartung tranchiert
    festgelegt: Der zweite Versuch nimmt ``ses_attempt1`` mit, der
    dritte die im Zweitversuch erfasste Kennung ``ses_attempt2``.
    """

    def test_third_retry_continues_with_the_latest_captured_session(self):
        self.write_project(
            env_text=(
                "TYPE=generic\n"
                "AGENT=tester\n"
                "TESTER=test-agent\n"
                "REVIEWER=code-reviewer\n"
                'VERIFY_PACKAGE="true"\n'
                'VERIFY_FULL="true"\n'
                "MAX_RETRIES=2\n"
            )
        )
        result = self.run_runner(FAKE_MODE_SEQUENCE="fail,fail,complete")

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)
        records = self.arg_records()
        self.assertEqual(
            3, len(records),
            "Erwartet drei Versuche je MAX_RETRIES=2: " + repr(self.call_lines()),
        )

        def session_values(record):
            return [
                record[position + 1]
                for position in range(len(record) - 1)
                if record[position] == "--session"
            ]

        self.assertNotIn(
            "--session", records[0],
            "Erster Versuch startet nicht fortgesetzt: " + repr(records[0]),
        )
        self.assertEqual(
            ["ses_attempt1"], session_values(records[1]),
            "Zweitversuch nimmt nicht die Erst-Kennung mit: " + repr(records[1]),
        )
        self.assertEqual(
            ["ses_attempt2"], session_values(records[2]),
            "Drittversuch nimmt nicht die zuletzt erfasste Kennung mit: "
            + repr(records[2]),
        )
        for record in records:
            self.assertIn(
                "Arbeitspaket F25", record[-1],
                "Prompt unvollständig: " + repr(record[-1]),
            )
        session_lines = sorted(
            line for line in log.splitlines() if line.startswith("[Session]")
        )
        self.assertEqual(
            [
                "[Session] ses_attempt1",
                "[Session] ses_attempt2",
                "[Session] ses_attempt3",
            ],
            session_lines,
            "Je Versuch genau eine [Session]-Zeile ohne Duplikate:\n" + log,
        )
        for identifier in ("ses_attempt1", "ses_attempt2", "ses_attempt3"):
            self.assertEqual(
                1, log.count("[Session] " + identifier),
                "Kennung mehrfach protokolliert: " + log,
            )
        state = json.loads(
            (self.runtime / "proj.log.state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "ses_attempt3",
            state.get("session"),
            "Zustandsdatei hält nicht die zuletzt erfasste Session: "
            + repr(state),
        )


if __name__ == "__main__":
    unittest.main()
