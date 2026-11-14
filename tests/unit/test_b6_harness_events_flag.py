"""Unit-Abnahme B6 (Teil 2): Harness-Schnittstelle für Pi-JSON-Ereignisse.

Arbeitspaket B6 verlangt, dass F24 (aktiver Agent, Subagenten-Tabs)
harness-übergreifend funktioniert. Damit die Pi-Läufe erfasste Ereignisse
liefern, baut die verbindliche geplante Schnittstelle ein ``--mode json``
in die Argumentliste für Pi ein; opencode bleibt unverändert:

* ``vibe_harness.run_argv(..., events=True)`` fügt für Pi die Argumente
  ``["--mode", "json"]`` ein (vor der Optionsgrenze ``--``; Reihenfolge
  sonst unverändert).
* ``run_argv(..., events=False)`` oder der Parameter weggelassen:Argumentlisten
  byte-identisch zum bisherigen Verhalten (Regressionsschutz der
  AP04-Tests).
* Für opencode ändert sich mit ``events=True`` nichts: nie eine Pi-
  spezifische Einstellung (``--mode json``/``--json``).
* CLI beim Unterbefehl ``run``: neuer Flag ``--json``; ohne Flag bleiben
  die Argumente wie bisher.

Geprüft wird die CLI mit einer Pi-Attrappe, die ihre Aufrufargumente in
einer Datei protokolliert; es entstehen keine Modellkosten.
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))

import vibe_harness  # noqa: E402


def write_script(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# Erwartete Argumentlisten der Baseline (Reg tests ohne den Befund):
# exakt die Aufrufe aus tests/unit/test_ap04_harness.py (HarnessRunTest).
PI_BASELINE_ARGV = ["pi-fake", "--print", "--no-session", "--",
                    "Du bist der Coder.\n\n---\n\nAufgabe"]
OPENCODE_BASELINE_ARGV = [
    "opencode-fake", "run", "--standalone", "--auto", "--thinking",
    "--agent", "coder", "--model", "opencode/model-a",
    "--title", "proj F1", "Aufgabe",
]


class HarnessArgvFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        agent_dir = self.project / ".opencode" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "coder.md").write_text(
            "---\ndescription: Coder\nmode: primary\n---\nDu bist der Coder.\n",
            encoding="utf-8",
        )
        self.addCleanup(self.tmp.cleanup)


class PiRunArgvEventsTest(HarnessArgvFixture):
    """AK4: run_argv events-Flag für Pi."""

    # 1. Name: test_pi_events_true_inserts_json_mode_before_the_option_end
    #    [AK4] Vorbedingung: Pi-Agentendatei vorhanden. Aktion:
    #    run_argv("pi", ..., events=True). Erwartung: die Argumente
    #    ["--mode","json"] erscheinen genau einmal, zusammenhängend, vor
    #    der Optionsgrenze "--"; die letzte Aufgabe bleibt das
    #    letzte Argument; "--print"/"--no-session" bleiben.
    #    Fehlerfall: Argumente fehlen, stehen hinter "--" oder das
    #    Baseline-Verhalten ändert sich.
    def test_pi_events_true_inserts_json_mode_before_the_option_end(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder",
            binary="pi-fake", events=True,
        )

        self.assertIn(["--mode", "json"],
                      [argv[i:i + 2] for i in range(len(argv) - 1)],
                      f"--mode json muss zusammenhängend erscheinen: {argv}")
        self.assertEqual(1, argv.count("--mode"), f"Genau einmal: {argv}")
        self.assertEqual(1, argv.count("json"), f"Genau einmal: {argv}")
        self.assertLess(
            argv.index("--mode"), argv.index("--"),
            "--mode muss vor der Optionsgrenze -- stehen: " + repr(argv),
        )
        stripped = argv.copy()
        del stripped[argv.index("--mode"):argv.index("--mode") + 2]
        self.assertEqual(
            PI_BASELINE_ARGV, stripped,
            "Die restliche Reihenfolge darf sich nicht ändern: " + repr(argv),
        )

    # 2. Name: test_pi_events_false_is_byte_identical_to_ap04_tests [AK4]
    #    Vorbedingung: Pi-Agentendatei vorhanden. Aktion:
    #    run_argv("pi", ..., events=False). Erwartung: exakt die bisher
    #    geprüfte Argumentliste der AP04-Tests (kein --mode, kein json).
    def test_pi_events_false_is_byte_identical_to_ap04_tests(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder",
            binary="pi-fake", events=False,
        )

        self.assertEqual(PI_BASELINE_ARGV, argv)

    # 3. Name: test_pi_default_without_events_flag_is_unchanged [AK4]
    #    Vorbedingung: wie 2. Aktion: run_argv ohne events-Parameter.
    #    Erwartung: wie bei dem Aufruf der AP04-Tests (default False).
    def test_pi_default_without_events_flag_is_unchanged(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder", binary="pi-fake",
        )

        self.assertEqual(PI_BASELINE_ARGV, argv)


class OpencodeRunArgvEventsTest(HarnessArgvFixture):
    """AK4: Für opencode ändert sich mit events=True nichts (Regression)."""

    # 1. Name: test_opencode_events_true_changes_nothing [AK4]
    #    Vorbedingung: wie bisher (Agent, Modell, Titel). Aktion:
    #    run_argv("opencode", ..., events=True) und events=False.
    #    Erwartung: beide Aufrufe liefern exakt die bisher geprüfte
    #    Argumentliste; keine Pi-spezifische Einstellung (--mode, --json)
    #    erscheint.
    def test_opencode_events_true_changes_nothing(self):
        plain = vibe_harness.run_argv(
            "opencode", "Aufgabe", self.project, agent="coder",
            model="opencode/model-a", title="proj F1",
            binary="opencode-fake", server_url="",
        )
        events = vibe_harness.run_argv(
            "opencode", "Aufgabe", self.project, agent="coder",
            model="opencode/model-a", title="proj F1",
            binary="opencode-fake", server_url="", events=True,
        )

        self.assertEqual(OPENCODE_BASELINE_ARGV, plain)
        self.assertEqual(plain, events)


FAKE_PI_CLI = """\
#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
for argument in "$@"; do
  printf '%s\\0' "$argument"
done >> "$FAKE_PI_ARGS_PATH"
printf 'PI_ARGS_RECORD_END\\0' >> "$FAKE_PI_ARGS_PATH"
exit 0
"""


class HarnessCliJsonFlagTest(HarnessArgvFixture):
    """AK4: CLI-Flag --json beim Unterbefehl run ist da und bleibt ohne
    Flag beim bisherigen Verhalten (kein --mode json)."""

    def fakebin(self):
        fake = self.root / "fakebin"
        write_script(fake, "pi", FAKE_PI_CLI)
        return fake

    def env(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX"):
                env.pop(key, None)
        env.update({
            "PATH": str(self.fakebin()) + os.pathsep + env.get("PATH", ""),
            "FAKE_PI_ARGS_PATH": str(self.root / "pi.args"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    def pi_arg_lists(self):
        path = self.root / "pi.args"
        self.assertTrue(path.exists(), "pi wurde nicht aufgerufen")
        raw = path.read_bytes()
        tokens = raw.decode("utf-8", "surrogateescape").split("\0")
        records, current = [], []
        for token in tokens:
            if token == "PI_ARGS_RECORD_END":
                records.append(current)
                current = []
            elif token:
                current.append(token)
        return records

    def cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(BIN / "vibe_harness.py"), "run",
             "--harness", "pi", "--project", str(self.project),
             "--agent", "coder", "--title", "proj B6",
             "--prompt", "Aufgabe von CLI", *extra],
            env=self.env(), capture_output=True, text=True, timeout=60,
        )

    # 1. Name: test_cli_run_json_flag_invokes_pi_with_json_mode [AK4]
    #    Vorbedingung: Pi-Agentendatei im Projekt, Pi-Attrappe im PATH.
    #    Aktion: vibe_harness.py run ... --json. Erwartung: Exit-Code wie
    #    der Agentenprozess (0) und in der protokollierten Argumentliste
    #    stehen --mode und json vor der Optionsgrenze --.
    #    Fehlerfall: --json wird abgewiesen, ignoriert oder falsch
    #    positioniert.
    def test_cli_run_json_flag_invokes_pi_with_json_mode(self):
        result = self.cli("--json")

        self.assertEqual(
            0, result.returncode,
            f"--json muss vorhanden sein: {result.returncode}\n"
            + result.stdout + result.stderr,
        )
        records = self.pi_arg_lists()
        self.assertTrue(records, "pi wurde ohne Argumente aufgerufen")
        argv = records[-1]
        self.assertIn("--mode", argv)
        self.assertIn("json", argv)
        self.assertLess(
            argv.index("--mode"), argv.index("--"),
            "--mode muss vor der Optionsgrenze -- erscheinen",
        )
        self.assertIn("--print", argv)
        self.assertIn("--no-session", argv)

    # 2. Name: test_cli_run_without_json_flag_keeps_previous_behavior [AK4]
    #    Vorbedingung: wie 1. Aktion: vibe_harness.py run ohne --json.
    #    Erwartung: Exit-Code 0 und keine Pi-Ereignisargumente (--mode,
    #    json) in der Argumentliste (bisheriges Verhalten unberührt).
    def test_cli_run_without_json_flag_keeps_previous_behavior(self):
        result = self.cli()

        self.assertEqual(
            0, result.returncode,
            "Ohne --json bleibt das bisherige Verhalten: "
            + result.stdout + result.stderr,
        )
        for argv in self.pi_arg_lists():
            self.assertNotIn("--mode", argv, "Kein --mode ohne --json")
            self.assertNotIn("json", argv, "Kein json ohne --json")


if __name__ == "__main__":
    unittest.main()
