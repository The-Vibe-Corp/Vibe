"""Limits: CLI- und Läufer-Grenzen.

Aufruf: python3 -m unittest tests.unit.test_limits -v
"""


# ===========================================================================
# Unabhängige Abnahme: Globales Limitverhalten ausdrücklich einstellen
# ===========================================================================

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
# Erlaubt einen Lauf gegen eine Kopie des Läufers (z. B. für die belegte
# Rotphase), ohne die Produktionsdatei zu verändern. Ohne die Variable gilt
# unverändert der Läufer des Repositories.
RUNNER = Path(os.environ.get("VIBE_TEST_RUNNER") or (BIN / "vibe-run.sh"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

INVALID_MARKERS = (
    "ungültig",
    "unlesbar",
    "defekt",
    "beschädigt",
    "kein gültiges",
    "invalid",
)

# Ausgaben, die nur bei einem ausgeführten Reconnect-Pfad entstehen. Die
# Attrappe selbst meldet „Fritzbox-Automatik ist aus“; auch dieser Text darf
# nicht erscheinen, weil er einen Aufruf von 'vibe fritz auto' verrät.
RECONNECT_OUTPUT_MARKERS = (
    "zentraler reconnect",
    "neue ip manuell anfordern",
    "keine neue ip angefordert",
    "fritzbox-automatik",
)


def assert_continue_hint(test, text):
    """Der Hinweis auf ``continue`` ist mehr als die allgemeine GitHub-Meldung."""
    hints = [line for line in text.splitlines() if "hinweis" in line]
    test.assertTrue(hints, text)
    test.assertTrue(
        any("limit" in line or "continue" in line for line in hints), hints
    )


def isolated_env(root, home, state, install, runtime):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIBE_") or key.startswith("SANDBOX") or key in (
            "VIBE",
            "AGENT",
            "TYPE",
            "VERIFY_QUICK",
            "VERIFY_FULL",
        ):
            env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "VIBE_CONFIG_FILE": str(root / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(root / "locks"),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "VIBE_STATE": str(state),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def status_line(result):
    """Die Zeile mit dem wirksamen Wert, ohne die allgemeine Aufrufhilfe.

    Eine reine Hilfeausgabe enthält keinen wirksamen Wert. Eine echte
    Statuszeile darf jedes Format haben, solange sie ``stop`` oder
    ``continue`` nennt.
    """
    output = result.stdout
    lowered_output = output.lower()
    if "aufruf:" in lowered_output or "usage:" in lowered_output:
        return ""
    for line in output.splitlines():
        lowered = line.strip().lower()
        if re.search(r"\b(stop|continue)\b", lowered):
            return lowered
    return ""


class LimitsCliTest(unittest.TestCase):
    """``vibe limits`` liest und schreibt die globale Einstellung."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=isolated_env(
                self.root, self.home, self.state, self.install, self.runtime
            ),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_status_without_a_file_reports_stop(self):
        result = self.run_cli("limits", "status")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stop", status_line(result), result.stdout)
        self.assertNotIn("continue", status_line(result), result.stdout)

    def test_limits_without_argument_shows_status(self):
        result = self.run_cli("limits")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stop", status_line(result), result.stdout)

    def test_stop_is_persisted_and_reported(self):
        result = self.run_cli("limits", "stop")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            (self.state / "limits.json").is_file(),
            "Die globale Einstellung gehört nach <Zustand>/limits.json",
        )

        status = self.run_cli("limits", "status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("stop", status_line(status), status.stdout)

    def test_continue_is_persisted_and_reported(self):
        result = self.run_cli("limits", "continue")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            (self.state / "limits.json").is_file(),
            "Die globale Einstellung gehört nach <Zustand>/limits.json",
        )

        status = self.run_cli("limits", "status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("continue", status_line(status), status.stdout)

    def test_unknown_argument_is_rejected(self):
        result = self.run_cli("limits", "kaputt")

        self.assertNotEqual(
            result.returncode, 0, result.stdout + result.stderr
        )
        self.assertIn(
            "limit", (result.stdout + result.stderr).lower(), result.stdout
        )

    def test_invalid_file_is_reported_and_not_continue(self):
        (self.state / "limits.json").write_text("{ kein json\n", encoding="utf-8")

        result = self.run_cli("limits", "status")

        combined = (result.stdout + result.stderr).lower()
        self.assertTrue(
            any(marker in combined for marker in INVALID_MARKERS), combined
        )
        self.assertIn("limit", combined, combined)
        if result.returncode == 0:
            self.assertNotIn("continue", status_line(result), result.stdout)


class RunnerLimitsTest(unittest.TestCase):
    """Der Läufer wendet ``stop`` und ``continue`` auf Quota/Auth an."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"

    def tearDown(self):
        self.tmp.cleanup()

    def write_project(self, max_retries):
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            f"MAX_RETRIES={max_retries}\n",
            feedback=[support.ticket_record(
                "F1", "Erstes Paket", type="feedback", description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")

    def base_env(self):
        return isolated_env(
            self.root, self.home, self.state, self.install, self.runtime
        )

    def limits(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), "limits", *args],
            cwd=str(self.root),
            env=self.base_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def runner_env(self, fake_mode):
        env = self.base_env()
        fakebin = support.install_fake_tools(self.root)
        env.update(
            {
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": fake_mode,
                "FAKE_ARGS_PATH": str(self.root / "opencode.args"),
                "PATH": str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
            }
        )
        return env

    def run_runner(self, fake_mode, max_retries):
        self.write_project(max_retries)
        return subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(fake_mode),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def call_lines(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_blocked_immediately(self, mode):
        result = self.run_runner(mode, max_retries=2)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())
        combined = self.log_text().lower()
        self.assertIn("blockiert", combined, combined)
        if mode == "quota":
            self.assertTrue(
                "quota" in combined or "kontingent" in combined, combined
            )
        else:
            self.assertTrue(
                "anmeld" in combined
                or "auth" in combined
                or "401" in combined,
                combined,
            )

    def use_stop(self):
        saved = self.limits("stop")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        status = self.limits("status")
        self.assertIn("stop", status_line(status), status.stdout)

    def test_default_stop_blocks_quota_immediately(self):
        self.assertFalse((self.state / "limits.json").exists())

        self.assert_blocked_immediately("quota")

    def test_default_stop_blocks_auth_immediately(self):
        self.assertFalse((self.state / "limits.json").exists())

        self.assert_blocked_immediately("auth")

    def test_stop_setting_blocks_quota_immediately(self):
        self.use_stop()

        self.assert_blocked_immediately("quota")

    def test_stop_setting_blocks_auth_immediately(self):
        self.use_stop()

        self.assert_blocked_immediately("auth")

    def test_continue_retries_quota_within_the_limit_and_logs_a_hint(self):
        saved = self.limits("continue")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        status = self.limits("status")
        self.assertIn("continue", status_line(status), status.stdout)

        result = self.run_runner("quota", max_retries=1)

        self.assertEqual(len(self.call_lines()), 2, self.call_lines())
        combined = self.log_text().lower()
        assert_continue_hint(self, combined)
        self.assertTrue(
            "quota" in combined or "kontingent" in combined, combined
        )
        self.assertNotIn("blockiert: quota", combined, combined)

    def test_continue_retries_auth_within_the_limit_and_logs_a_hint(self):
        saved = self.limits("continue")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        status = self.limits("status")
        self.assertIn("continue", status_line(status), status.stdout)

        result = self.run_runner("auth", max_retries=1)

        self.assertEqual(len(self.call_lines()), 2, self.call_lines())
        combined = self.log_text().lower()
        assert_continue_hint(self, combined)

    def install_vibe_probe(self):
        """Ersetzt die ``vibe``-Attrappe durch eine beobachtende Variante.

        Der Läufer ruft ``$INSTALL/bin/vibe`` ausschließlich für
        ``fritz auto`` auf. Jeder Aufruf wird mit seinen Argumenten in einer
        Markierungsdatei festgehalten; eine echte FRITZ!Box wird nie
        angesprochen. Der Exit-Code 3 entspricht der Attrappe aus
        ``runner_support`` und löst keinen Wartevorgang aus.
        """
        marks = self.root / "vibe.calls"
        (self.tool_bin / "vibe").write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"with open({str(marks)!r}, 'a', encoding='utf-8') as handle:\n"
            "    handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "print('Fritzbox-Automatik ist aus')\n"
            "raise SystemExit(3)\n",
            encoding="utf-8",
        )
        (self.tool_bin / "vibe").chmod(0o755)
        return marks

    def assert_no_router_reconnect(self, result, marks):
        """Weder Reconnect-Ausgabe noch ein Aufruf von ``fritz auto``."""
        combined = (result.stdout + result.stderr + self.log_text()).lower()
        for marker in RECONNECT_OUTPUT_MARKERS:
            self.assertNotIn(
                marker,
                combined,
                "Quota-/Anmeldefehler dürfen keinen Reconnect auslösen, "
                f"gefunden: {marker!r}\n{combined}",
            )
        lines = (
            marks.read_text(encoding="utf-8").splitlines()
            if marks.exists()
            else []
        )
        self.assertFalse(
            [line for line in lines if "fritz auto" in line],
            "Der Läufer hat 'vibe fritz auto' aufgerufen: " + repr(lines),
        )

    def assert_continue_without_reconnect(self, mode):
        saved = self.limits("continue")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        status = self.limits("status")
        self.assertIn("continue", status_line(status), status.stdout)

        marks = self.install_vibe_probe()
        result = self.run_runner(mode, max_retries=1)

        # 1. Der Fehler wird wie bisher im Rahmen des Limits wiederholt.
        self.assertEqual(
            len(self.call_lines()),
            2,
            "MAX_RETRIES=1 erlaubt genau zwei Versuche: "
            + repr(self.call_lines()),
        )
        combined = self.log_text().lower()
        assert_continue_hint(self, combined)
        # 2./3. Kein Reconnect und kein Aufruf von 'vibe fritz auto'.
        self.assert_no_router_reconnect(result, marks)

    def test_continue_quota_does_not_trigger_a_router_reconnect(self):
        self.assert_continue_without_reconnect("quota")

    def test_continue_auth_does_not_trigger_a_router_reconnect(self):
        self.assert_continue_without_reconnect("auth")

    def test_continue_never_repeats_beyond_max_retries(self):
        saved = self.limits("continue")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        status = self.limits("status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("continue", status_line(status), status.stdout)

        result = self.run_runner("quota", max_retries=1)

        self.assertEqual(
            len(self.call_lines()),
            2,
            "MAX_RETRIES=1 erlaubt genau zwei Versuche: "
            + repr(self.call_lines()),
        )
        self.assertLessEqual(len(self.call_lines()), 2, result.stdout)

    def test_invalid_file_is_reported_and_blocks_instead_of_continuing(self):
        (self.state / "limits.json").write_text(
            "{ kaputt\n", encoding="utf-8"
        )

        result = self.run_runner("quota", max_retries=2)

        self.assertLessEqual(
            len(self.call_lines()),
            1,
            "Eine defekte Einstellung darf nicht still als continue gelten: "
            + repr(self.call_lines()),
        )
        combined = (result.stdout + result.stderr + self.log_text()).lower()
        self.assertTrue(
            any(marker in combined for marker in INVALID_MARKERS), combined
        )
        self.assertIn("limit", combined, combined)


if __name__ == "__main__":
    unittest.main()
