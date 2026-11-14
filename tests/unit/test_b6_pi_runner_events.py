"""Unit-Abnahme B6 (Teil 3): Läuferverbindung für Pi über den echten
``bin/vibe-run.sh``.

Arbeitspaket B6 verlangt, dass F24 (aktiver Agent, Subagenten-Tabs) auch
mit dem Pi-Harness funktioniert. Nach dem Befund ruft der Läufer den Pi
bisher mit reiner Klartextausgabe auf (keine Erfassung, keine Subagenten-
Tabs); die verbindliche geplante Schnittstelle sieht Folgendes vor:

* ``<VIBE_STATE>/harness.json = {"harness":"pi"}`` wählt den Pi-Harness.
* Der Pi-Zweig von ``run_agent_in`` fügt ``--json`` hinzu (die Harness-CLI
  liefert ``--mode json``) und leitet die Ausgabe durch denselben
  ``STREAM_FILTER`` wie der opencode-Zweig (
  ``vibe_runs.py stream --state <log>.state.json``).
* Der Exit-Code des Agentenprozesses bleibt maßgeblich.
* Ergebnis: menschenlesbares Protokoll (kein Roh-JSON), Zustandsdatei mit
  erfasstem Subagenteneintrag und ohne ephemere Pi-Hauptsession.

Der Agent wird durch eine Pi-Attrappe im isolierten PATH ersetzt, die
Pi-JSONL-Ereignisse ausgibt, ihre Argumente protokolliert und das
Arbeitspaket wie das F19-Muster vollständig abschließt. Keine echten
Modellaufrufe, keine externen Dienste; NTFS/FUSE wird beachtet (Skripte
werden mit ``bash <datei>`` ausgeführt, Rechte der Attrappe werden gesetzt).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

PI_SESSION = "ses-pi-4711"
TOOL_CALL = "call_abc123"

# Attrappe: protokolliert die Argumente, gibt Pi-JSONL gemäß der
# Pi-Dokumentation 1.5.0 (docs/json.md) aus und schließt das Arbeitspaket
# so ab, wie die echten Abschlussschranken es verlangen (Muster: die
# opencode-Attrappe in runner_support.py — hier als eigenständiger Text
# des Test-Agenten geschrieben).
FAKE_PI = r'''#!/usr/bin/env python3
"""Pi-Attrappe für die B6-Abnahme (kein echter pi, keine Modellkosten)."""
import json
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
message = args[-1] if args else ""
match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", message)
pid = match.group(1) if match else "B6"
cwd = pathlib.Path.cwd()

args_path = os.environ.get("FAKE_PI_ARGS_PATH")
if args_path:
    # Je Aufruf wird die Argumentliste NUL-getrennt mit Datensatzende
    # angehängt; der Prompt enthält kein NUL-Byte, die Grenze ist eindeutig.
    with open(args_path, "ab") as handle:
        for argument in args:
            handle.write(argument.encode("utf-8") + b"\0")
        handle.write(b"PI_ARGS_RECORD_END\0")

session = os.environ.get("FAKE_PI_SESSION", "ses-pi-4711")
events = [
    {"type": "session", "version": 3, "id": session,
     "timestamp": "2026-01-01T00:00:00.000Z", "cwd": str(cwd)},
    {"type": "agent_start"},
    {"type": "message_end", "message": {"role": "user", "content": message,
                                        "timestamp": 1735689600000}},
    {"type": "message_end", "message": {"role": "assistant", "content": [
        {"type": "thinking", "text": "nachdenkliche Zeile"},
        {"type": "text", "text": "Hallo\nWelt"},
    ]}},
    {"type": "tool_execution_start", "toolCallId": "call_abc123", "toolName": "task",
     "args": {"agent": "general", "description": "Testzusammenfassung",
              "prompt": "Sammle Infos"}},
    {"type": "tool_execution_update", "toolCallId": "call_abc123",
     "toolName": "task",
     "args": {"agent": "general", "description": "Testzusammenfassung"},
     "partialResult": {"content": [{"type": "text", "text": "Teilausgabe"}]}},
    {"type": "tool_execution_end", "toolCallId": "call_abc123", "toolName": "task",
     "result": {"content": [{"type": "text", "text": "PONG"},
                            {"type": "text", "text": "Zweitzeile"}]},
     "isError": False, "durationMs": 7},
    {"type": "turn_end", "message": {"role": "assistant", "content": []},
     "toolResults": []},
    {"type": "agent_end", "messages": [], "willRetry": False},
    {"type": "agent_settled", "aborted": False},
]
for event in events:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
sys.stdout.flush()

if os.environ.get("FAKE_PI_MODE", "complete") == "fail":
    sys.stderr.write("beliebiger Agentenfehler\n")
    sys.exit(1)

counter_path = pathlib.Path(os.environ.get("FAKE_PI_COUNTER", os.devnull))
try:
    counter = int(counter_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    counter = 0
counter_path.write_text(str(counter + 1), encoding="utf-8")


def run(*command, check=True):
    return subprocess.run(list(command), cwd=cwd, check=check,
                          capture_output=True, text=True)


def mark_done(path, commit):
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    index = 0
    pattern = re.compile(r"^- \[ \] " + re.escape(pid) + r"\b")
    while index < len(lines):
        line = lines[index]
        if not pattern.match(line):
            out.append(line)
            index += 1
            continue
        out.append(line.replace("- [ ]", "- [x]", 1))
        index += 1
        continuation = []
        while index < len(lines):
            candidate = lines[index]
            if candidate.startswith((" ", "\t")):
                continuation.append(candidate)
                index += 1
            elif not candidate.strip():
                index += 1
            else:
                break
        continuation = [
            item
            for item in continuation
            if not re.match(r"\s*(Commit|Test|Datei):", item)
        ]
        out.extend(continuation)
        out.append("  Commit: " + commit + "; Test: test_" + pid.lower().replace("-", "_"))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


(cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Umsetzung")
short = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

for name in ("TICKETS.md", "FEEDBACK.md"):
    mark_done(cwd / name, short)

(cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "features" / (pid + ".md")).write_text(
    "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8")
(cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
    "# Review\n\nVerdict: PASS\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Nachweis")
sys.exit(0)
'''

FAKE_CURL_LOCAL = """#!/usr/bin/env bash
exit 7
"""


class PiRunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        # Pi liest den Prompt-Text der Agentendatei; die Dateien brauchen
        # deshalb einen echten Prompt-Text (Frontmatter wird nicht mitgesendet).
        self.agents.mkdir(parents=True)
        for name in ("tester", "test-agent", "code-reviewer", "reviewer"):
            (self.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Test-Agent der Arbeitspakete.\n",
                encoding="utf-8",
            )
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
            feedback="- [ ] B6 Testpaket\n  Beschreibung: Test\n",
        )
        self.tool_bin = support.install_runner(self.root / "_toolchain")
        self.install = self.root / "_toolchain"
        # Harness-Schicht für den Pi-Zweig des Läufers:
        for name in ("vibe_harness.py", "vibe_opencode.py"):
            (self.tool_bin / name).write_text(
                (BIN / name).read_text(encoding="utf-8"), encoding="utf-8")
        # Harness-Auswahl: Pi gewählt (echter Auswahlstand des Läufers).
        (self.install / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.fakebin = support.install_fake_tools(self.root)
        (self.fakebin / "pi").write_text(FAKE_PI, encoding="utf-8")
        self.fakebin_chmod(self.fakebin / "pi")
        support.init_repo(self.project)
        support.commit_all(self.project)
        self.addCleanup(self.tmp.cleanup)

    def fakebin_chmod(self, path):
        mode = path.stat().st_mode | 0o111
        path.chmod(mode)

    def env(self):
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
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_AGENTS_DIR": str(self.agents),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_PI_ARGS_PATH": str(self.root / "_logs" / "pi.args"),
                "FAKE_PI_SESSION": PI_SESSION,
                "FAKE_PI_COUNTER": str(self.root / "counter"),
                "FAKE_PI_MODE": os.environ.get("B6_FAKE_PI_MODE", "complete"),
            }
        )
        return env

    def command(self):
        # Hausregel NTFS/FUSE: Skripte mit bash <datei> ausführen.
        return ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)]

    def run_runner(self):
        result = subprocess.run(
            self.command(),
            env=self.env(),
            cwd=str(self.project),
            capture_output=True,
            text=True,
            timeout=180,
        )
        log = self.log_text()
        return result, log

    def log_lines(self):
        text = self.log_text()
        try:
            return text.splitlines()
        except AttributeError:
            return []

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
            self.fail(
                "Zustandsdatei ist kein gültiges JSON: "
                + path.read_text(encoding="utf-8"))

    def pi_calls(self):
        path = self.root / "_logs" / "pi.args"
        self.assertTrue(path.exists(), "pi wurde nicht aufgerufen")
        tokens = path.read_bytes().decode(
            "utf-8", "surrogateescape").split("\0")
        records, current = [], []
        for token in tokens:
            if token == "PI_ARGS_RECORD_END":
                records.append(current)
                current = []
            elif token:
                current.append(token)
        return records


class PiRunnerSuccessfulRunTest(PiRunnerFixture):
    """AK5 (+ AK1/AK3/AK4): Erfolgreicher Pi-Lauf über den echten Läufer."""

    def run_and_expect_finished(self):
        result, log = self.run_runner()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout + result.stderr)
        self.assertIn(
            "FERTIG", log,
            "Läufer hat die Abnahme nicht gemeldet:\n" + log + "\n" + result.stderr)
        return log

    # 1. Name: test_pi_runner_logs_translated_protocol_without_raw_json
    #    [AK5/AK1] Vorbedingung: harness.json wählt Pi; Pi-Attrappe liefert
    #    die Pi-JSONL-Ereignisse; Arbeitspaket lauffähig. Aktion: echten
    #    vibe-run.sh ausführen. Erwartung: Das Protokoll enthält die
    #    übersetzten Zeilen ("Hallo", "[Session] ses-pi-4711",
    #    "[Denken] nachdenkliche Zeile", "[Werkzeug] task — läuft") als
    #    eigene Zeilen und keine Zeile, die mit "{" beginnt (kein Roh-JSON).
    #    Fehlerfall: Roh-JSON im Protokoll oder fehlende übersetzte Zeilen.
    def test_pi_runner_logs_translated_protocol_without_raw_json(self):
        log = self.run_and_expect_finished()

        lines = self.log_lines()
        raw = [line for line in lines if line.startswith("{")]
        self.assertEqual(
            raw, [], f"Roh-JSON-Zeilen dürfen nicht ins Protokoll:\n{log}")
        for expected in (
            "Hallo",
            "Welt",
            "[Session] " + PI_SESSION,
            "[Denken] nachdenkliche Zeile",
        ):
            self.assertIn(
                expected, lines,
                f"Übersetzte Zeile {expected!r} fehlt im Protokoll:\n" + log)
        self.assertTrue(
            any(line.startswith("[Werkzeug] task — läuft") for line in lines),
            f"Werkzeugstart fehlt im Protokoll: {[line for line in lines if 'Werkzeug' in line]}",
        )

    # 2. Name: test_pi_runner_state_file_captures_subagent_and_no_session
    #    [AK5/AK3] Vorbedingung: wie 1. Aktion: Läufer ausführen und
    #    Zustandsdatei lesen. Erwartung: Der task-Eintrag ist erfasst
    #    (session == toolCallId als Tab-Schlüssel, agent, description,
    #    prompt, status "completed", Ausgabe "PONG\nZweitzeile", started/
    #    ended numerisch); die Hauptsession im Zustand bleibt leer (die
    #    ephemere Pi-Kennung darf F25-Ketten nicht fälschen).
    #    Fehlerfall: Zustandsdatei fehlt oder Eintrag falsch.
    def test_pi_runner_state_file_captures_subagent_and_no_session(self):
        self.run_and_expect_finished()

        state = self.read_state()
        self.assertIsNotNone(
            state, "Zustandsdatei fehlt nach dem Pi-Lauf")
        self.assertEqual(
            "", state.get("session", ""),
            "Die ephemere Pi-Session darf nicht als Hauptsession "
            "erfasst werden: " + json.dumps(state, ensure_ascii=False),
        )
        entries = state.get("subagents") or []
        self.assertEqual(1, len(entries), f"Genau der task-Eintrag: {state}")
        entry = entries[0]
        self.assertEqual(TOOL_CALL, entry.get("session"), entry)
        self.assertEqual("general", entry.get("agent"), entry)
        self.assertEqual("Testzusammenfassung", entry.get("description"), entry)
        self.assertEqual("Sammle Infos", entry.get("prompt"), entry)
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertIn("PONG\nZweitzeile", str(entry.get("output") or ""), entry)
        self.assertIsInstance(entry.get("started"), int, entry)
        self.assertIsInstance(entry.get("ended"), int, entry)

    # 3. Name: test_pi_runner_calls_pi_agent_with_json_mode [AK5/AK4]
    #    Vorbedingung: wie 1. Aktion: Läufer ausführen und die von der
    #    Pi-Attrappe protokollierten Argumente lesen. Erwartung: Jeder
    #    Aufruf enthält --print und --no-session; mindestens ein Aufruf
    #    enthält --mode und json, und zwar vor der Optionsgrenze --.
    #    Fehlerfall: Ohne --mode json würde Pi keine Ereignisse liefern
    #    (genau der gemeldete Defekt).
    def test_pi_runner_calls_pi_agent_with_json_mode(self):
        self.run_and_expect_finished()

        records = self.pi_calls()
        self.assertTrue(records, "pi wurde nicht aufgerufen")
        for argv in records:
            self.assertIn(
                "--print", argv, f"Print-Modus fehlt: {argv}")
            self.assertIn(
                "--no-session", argv, f"--no-session fehlt: {argv}")
        self.assertTrue(
            any("--mode" in argv and "json" in argv for argv in records),
            f"kein --mode json-Aufruf: {records}")
        package_calls = [argv for argv in records if "--mode" in argv]
        for argv in package_calls:
            self.assertLess(
                argv.index("--mode"), argv.index("--"),
                f"--mode muss vor der Optionsgrenze -- stehen: {argv}")


class PiRunnerExitCodeTest(PiRunnerFixture):
    """AK5: Der Exit-Code des Agentenprozesses bleibt maßgeblich."""

    def run_in_fail_mode(self):
        env = self.env()
        env["FAKE_PI_MODE"] = "fail"
        result = subprocess.run(
            self.command(), env=env, cwd=str(self.project),
            capture_output=True, text=True, timeout=180,
        )
        return result, self.log_text()

    # 1. Name: test_pi_xrun_agent_exit_code_one_does_not_close_package
    #    [AK5] Vorbedingung: wie oben; Pi-Attrappe endet mit definiertem
    #    Exit-Code 1. Aktion: echten vibe-run.sh ausführen. Erwartung: Das
    #    Protokoll meldet "Agent beendet, Exit-Code 1" und der
    #    Abschlussbericht schließt das Paket nicht ("Geschlossen: keine");
    #    die Abnahme läuft trotzdem regulär zu Ende (bisherige Läufer-
    #    semantik: übersprungenes Paket blockiert den Abschluss nicht).
    #    Fehlerfall: Der Läufer bricht ab oder schließt das Paket fälschlich.
    def test_pi_run_agent_exit_code_one_does_not_close_package(self):
        result, log = self.run_in_fail_mode()

        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + log + result.stderr)
        self.assertIn(
            "Agent beendet, Exit-Code 1", log,
            "Der Exit-Code des Pi-Prozesses muss maßgeblich sein:\n" + log)
        self.assertIn(
            "Geschlossen: keine", log,
            "Das Paket darf bei Agentenfehlern nicht geschlossen werden:\n" + log)


if __name__ == "__main__":
    unittest.main()
