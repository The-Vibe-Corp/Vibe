"""Unit-Abnahme F19 (Teil 1): Protokollprozess des Paket-Läufers.

Arbeitspaket F19 „Ausgabe ansicht, im Projekte" verlangt als Grundbaustein,
dass der Paket-Läufer opencode mit ``--format json`` aufruft und daraus
weiterhin ein menschenlesbares Laufprotokoll in ``vibe.logpath(name)`` schreibt
sowie erfasste Subagenten in ``<log>.state.json`` hinterlegt. Geprüft wird der
Läufer direkt mit einem nachgebildeten opencode (Fake-Binary); es entstehen
keine Modellkosten und keine echten externen Dienste.

Akzeptanzkriterien:
* Das Laufprotokoll enthält den Ereignistext („Hallo") und keine Zeile, die mit
  ``{`` beginnt (kein Roh-JSON im Protokoll).
* opencode wird mit ``--format json`` aufgerufen.
* Ohne Subagenten entsteht kein erfasster Eintrag (keine Attrappe).
* Mit Subagenten-Ereignissen enthält die Zustandsdatei Hauptsession,
  Agent, Beschreibung, Prompt, Status, Start/Ende und Ausgabe.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

MAIN_SESSION = "ses_main"
CHILD_SESSION = "ses_child"
FAKE_COMPLETED_TEXT = "PONG"


def fake_output(subagents=False):
    """Ereignisse im opencode-JSON-Format, wie sie der Läufer filtert."""
    lines = [
        '{"type":"text","sessionID":"%s","part":{"type":"text","text":"Hallo"}}'
        % MAIN_SESSION
    ]
    if subagents:
        lines.append(
            '{"type":"tool_use","sessionID":"%s","part":{"tool":"subagent",'
            '"state":{"status":"completed","input":{"agent":"general",'
            '"description":"Testzusammenfassung","prompt":"Sammle Infos"},'
            '"output":"%s"},"metadata":{"metadata":{"sessionID":"%s"}}}}'
            % (MAIN_SESSION, FAKE_COMPLETED_TEXT, CHILD_SESSION)
        )
        lines.append(
            '{"type":"tool_use","sessionID":"%s","part":{"tool":"subagent",'
            '"state":{"status":"running","input":{"agent":"general",'
            '"description":"Sammlung laeuft","prompt":"War auch läuft"},'
            '"output":""}}}' % MAIN_SESSION
        )
    return "\n".join(lines) + "\n"


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.project = self.root / "proj"
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback="- [ ] F19 Testpaket\n  Beschreibung: Test\n",
        )
        self.tool_bin = support.install_runner(self.root / "_toolchain")
        self.fakebin = support.install_fake_tools(self.root)
        support.init_repo(self.project)
        support.commit_all(self.project)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"
        self.addCleanup(self.tmp.cleanup)

    def env(self, subagents=False):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key
                in (
                    "AGENT",
                    "TESTER",
                    "REVIEWER",
                    "MAX_RETRIES",
                    "VERIFY_QUICK",
                    "VERIFY_FULL",
                    "VERIFY_PACKAGE",
                    "TMUX",
                    "TMUX_PANE",
                )
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.root / "_toolchain"),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_AGENTS_DIR": str(self.agents),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.root / "_logs" / "opencode.args"),
                "FAKE_OUTPUT": fake_output(subagents),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
            }
        )
        return env

    def command(self):
        return ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)]

    def run_runner(self, subagents=False):
        result = subprocess.run(
            self.command(),
            env=self.env(subagents=subagents),
            cwd=str(self.project),
            capture_output=True,
            text=True,
            timeout=90,
        )
        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout + result.stderr
        )
        self.assertIn(
            "FERTIG",
            log,
            "Läufer hat die Abnahme nicht gemeldet:\n" + log + "\n" + result.stderr,
        )
        return result

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_state(self):
        path = self.root / "_logs" / "proj.log.state.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            self.fail("Zustandsdatei ist kein gültiges JSON: " + path.read_text(encoding="utf-8"))

    def opencode_args(self):
        path = self.root / "_logs" / "opencode.args"
        self.assertTrue(path.exists(), "opencode wurde nicht aufgerufen")
        return [word for word in path.read_text(encoding="utf-8").split("\0") if word]


class RunnerLogTest(RunnerFixture):
    """Menschenlesbares Protokoll statt Roh-JSON (Grundlage der Ausgabeansicht)."""

    def test_runner_logs_only_human_readable_lines(self):
        self.run_runner()

        log = self.log_text()
        self.assertIn("Hallo", log, "Ereignistext fehlt im Laufprotokoll")
        bad = [line for line in log.splitlines() if line.startswith("{")]
        self.assertEqual(
            bad, [], "Roh-JSON-Zeilen dürfen nicht ins menschliche Protokoll:\n" + log
        )

    def test_runner_calls_opencode_with_format_json(self):
        self.run_runner()

        args = self.opencode_args()
        self.assertEqual(
            "run", args[0], "Fake wurde nicht als 'opencode run' aufgerufen: " + repr(args)
        )
        for token in ("--format", "json"):
            self.assertIn(token, args, f"Argument {token} fehlt: {args}")

    def test_runner_without_subagents_writes_no_fake_entries(self):
        """Fehlende Erfassung: keine Attrappen, keine falsche Hauptsession."""
        self.run_runner()

        state = self.read_state()
        if state is not None:
            self.assertEqual(
                state.get("session"),
                MAIN_SESSION,
                f"Hauptsession falsch oder nicht erfasst: {state}",
            )
            self.assertEqual(
                [], state.get("subagents") or [], f"Subagenten erfunden: {state}"
            )

    def test_runner_still_runs_packages_and_verification(self):
        self.run_runner()
        self.assertIn(
            "Arbeitspaket F19",
            self.log_text(),
            "Der Paketlauf selbst wurde durch die Protokollierung beschädigt",
        )


class RunnerSubagentStateTest(RunnerFixture):
    """Erfasste Subagenten in der Zustandsdatei (Grundlage der Subagentenansicht)."""

    def test_state_file_records_completed_and_running_subagents(self):
        self.run_runner(subagents=True)

        state = self.read_state()
        self.assertIsNotNone(state, "Zustandsdatei fehlt nach Subagenten-Ereignissen")
        self.assertEqual(
            state.get("session"), MAIN_SESSION, f"Hauptsession falsch erfasst: {state}"
        )
        entries = state.get("subagents")
        self.assertIsInstance(entries, list, f"subagents keine Liste: {state}")
        self.assertEqual(2, len(entries), f"Falsche Anzahl erfasster Subagenten: {state}")

        completed, running = entries

        self.assertEqual(
            completed.get("session"),
            CHILD_SESSION,
            f"Sub-Session fehlt oder falsch: {completed}",
        )
        self.assertEqual("general", completed.get("agent"), f"Agent fehlt: {completed}")
        self.assertEqual(
            "Testzusammenfassung",
            completed.get("description"),
            f"Beschreibung fehlt: {completed}",
        )
        self.assertEqual(
            "completed", completed.get("status"), f"Status falsch erfasst: {completed}"
        )
        self.assertIn(
            FAKE_COMPLETED_TEXT,
            str(completed.get("output") or ""),
            f"Ausgabe fehlt: {completed}",
        )
        self.assertIsInstance(
            completed.get("prompt"), str, f"Prompt fehlt (auch leer erlaubt): {completed}"
        )
        self.assertIsInstance(
            completed.get("started"), int, f"Started muss numerisch sein: {completed}"
        )
        self.assertIsInstance(
            completed.get("ended"), int, f"Ended muss numerisch sein: {completed}"
        )

        self.assertEqual(
            "running", running.get("status"), f"Status bei laufendem Subagenten: {running}"
        )
        self.assertEqual("general", running.get("agent"), f"Agent fehlt: {running}")
        self.assertIsInstance(
            running.get("ended", 0), int, f"Ended muss numerisch sein (0 erlaubt): {running}"
        )


if __name__ == "__main__":
    unittest.main()
