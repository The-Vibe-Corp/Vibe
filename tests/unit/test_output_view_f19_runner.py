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
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "bin" / "vibe-run.sh"

MAIN_SESSION = "ses_main"
CHILD_SESSION = "ses_child"
FAKE_COMPLETED_TEXT = "PONG"

NEXT_ITEM = """import os, sys
here = os.path.dirname(os.path.abspath(__file__))
count_path = os.path.join(here, "next-calls")
try:
    calls = int(open(count_path, encoding="utf-8").read())
except OSError:
    calls = 0
calls += 1
open(count_path, "w", encoding="utf-8").write(str(calls))
if calls > 1:
    sys.exit(1)
open("/tmp/next_id", "w", encoding="utf-8").write("F19")
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F19 Testpaket\\n  Beschreibung: Test\\n"
)
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
printf '%s\\0' "$@" > "$FAKE_ARGS_PATH"
printf '%s\\n' '{"type":"text","sessionID":"%(main)s","part":{"type":"text","text":"Hallo"}}'
if [ -n "${FAKE_SUBAGENTS:-}" ]; then
  printf '%s\\n' '{"type":"tool_use","sessionID":"%(main)s","part":{"tool":"subagent","state":{"status":"completed","input":{"agent":"general","description":"Testzusammenfassung","prompt":"Sammle Infos"},"output":"%(pong)s"},"metadata":{"metadata":{"sessionID":"%(child)s"}}}}'
  printf '%s\\n' '{"type":"tool_use","sessionID":"%(main)s","part":{"tool":"subagent","state":{"status":"running","input":{"agent":"general","description":"Sammlung laeuft","prompt":"War auch läuft"},"output":""}}}'
fi
"""

FAKE_CURL = """#!/usr/bin/env bash
exit 7
"""


def make_fake_opencode(pairs):
    text = FAKE_OPENCODE
    for key, value in pairs.items():
        text = text.replace("%(" + key + ")s", value)
    return text


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        (self.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nAGENT=tester\nVERIFY_FULL="true"\n', encoding="utf-8"
        )
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F19 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        self.tool_bin = self.root / "_toolchain" / "bin"
        self.tool_bin.mkdir(parents=True)
        shutil.copy(RUNNER, self.tool_bin / "vibe-run.sh")
        shutil.copy(REPO / "bin" / "vibe_runs.py", self.tool_bin / "vibe_runs.py")
        verify = self.root / "_toolchain" / "verify"
        verify.mkdir(parents=True)
        (verify / "next_item.py").write_text(NEXT_ITEM, encoding="utf-8")
        marker = verify / "verify-marker.txt"
        marker.write_text("ok\n", encoding="utf-8")
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        (self.home / ".config" / "schreibfuchs-verify.sha").write_text(
            f"{digest}  verify-marker.txt\n", encoding="utf-8"
        )
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        (fakebin / "opencode").write_text(
            make_fake_opencode(
                {
                    "main": MAIN_SESSION,
                    "child": CHILD_SESSION,
                    "pong": FAKE_COMPLETED_TEXT,
                }
            ),
            encoding="utf-8",
        )
        (fakebin / "opencode").chmod(0o755)
        (fakebin / "curl").write_text(FAKE_CURL, encoding="utf-8")
        (fakebin / "curl").chmod(0o755)
        self.addCleanup(self.tmp.cleanup)

    def env(self, subagents=False):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "AGENT",
                "VERIFY_QUICK",
                "VERIFY_FULL",
                "TMUX",
                "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.root / "fakebin") + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.root / "_logs" / "opencode.args"),
            }
        )
        if subagents:
            env["FAKE_SUBAGENTS"] = "1"
        return env

    def command(self):
        """Startet den Läufer in einer bwrap-Instanz mit eigenem beschreibbarem
        /tmp: vibe-run.sh legt Laufsperrdateien und next_item-Zwischenstände in
        festen /tmp-Pfaden ab. Das Testtmp dieses Agenten ist readonly; die
        Sandbox (vibe_sandbox) nutzt bwrap ohnehin als Projektwerkzeug. Der
        Wrapper ändert nichts am Verhalten des Läufers.
        """
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--tmpfs", "/tmp",
            "--bind", str(self.root), str(self.root),
            "--proc", "/proc",
            "--dev", "/dev",
            "--setenv", "TMPDIR", "/tmp",
            "--setenv", "HOME", str(self.home),
            "bash", str(self.tool_bin / "vibe-run.sh"), str(self.project),
        ]

    def run_runner(self, subagents=False):
        result = subprocess.run(
            self.command(),
            env=self.env(subagents=subagents),
            cwd=str(self.root),
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
