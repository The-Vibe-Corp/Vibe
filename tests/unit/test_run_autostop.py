"""Abnahme für F10: Der Agentenlauf endet, wenn alle Arbeitspakete erledigt sind.

Der Paket-Läufer beendet sich nach dem letzten Paket und der Abschlussprüfung.
Die tmux-Sitzung darf danach nicht offen bleiben, sonst meldet vibe den Lauf
weiterhin als aktiv. Geprüft wird das mit einer echten, isolierten
tmux-Sitzung (eigener ``TMUX_TMPDIR``) und einer nachgebildeten
opencode-/verify-Ablage; es werden keine Modellaufrufe ausgeführt.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

NEXT_ITEM = '''import os, sys
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
open("/tmp/next_id", "w", encoding="utf-8").write("F1")
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F1 Testpaket\\n  Beschreibung: Test\\n"
)
'''

FAKE_OPENCODE = '''#!/usr/bin/env bash
printf 'x\\n' >> "$VIBE/_logs/opencode.invocations"
exit 0
'''

FAKE_CURL = '''#!/usr/bin/env bash
exit 7
'''


class RunnerSessionEndTest(unittest.TestCase):
    """Prüft, dass die tmux-Sitzung mit dem Ende des Läufers verschwindet."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.name = "f10proj%d" % os.getpid()
        self.project = self.root / self.name
        (self.project / ".vibe").mkdir(parents=True)
        # V-010: Der Läufer fällt nicht mehr auf einen fest eingebauten
        # Kernagentennamen zurück. Ein Projektlauf braucht deshalb einen
        # konfigurierten Agenten; die Rolle des Agenten ist hier unerheblich.
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nAGENT=tester\nVERIFY_FULL="true"\n', encoding="utf-8"
        )
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        self.verify = self.root / "_toolchain" / "verify"
        self.verify.mkdir(parents=True)
        # bin/vibe startet den Läufer aus der Installation ($VIBE/_toolchain).
        self.tool_bin = self.root / "_toolchain" / "bin"
        self.tool_bin.mkdir(parents=True)
        shutil.copy(REPO / "bin" / "vibe-run.sh", self.tool_bin / "vibe-run.sh")
        (self.verify / "next_item.py").write_text(NEXT_ITEM, encoding="utf-8")
        marker = self.verify / "verify-marker.txt"
        marker.write_text("ok\n", encoding="utf-8")
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        home_config = self.root / "home" / ".config"
        home_config.mkdir(parents=True)
        (home_config / "schreibfuchs-verify.sha").write_text(
            f"{digest}  verify-marker.txt\n", encoding="utf-8"
        )
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("curl", FAKE_CURL)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte; sonst
        # fiele der Test in den gemeinsamen Server des Nutzers zurück.
        self.tmux_dir.chmod(0o700)
        self.session = "vibe-" + self.name
        self.log = self.root / "_logs" / (self.name + ".log")

    def tearDown(self):
        self.tmux("kill-server")
        self.tmp.cleanup()

    def env(self):
        env = os.environ.copy()
        # Ein geerbtes TMUX zeigt sonst auf den Server der Sitzung, in der der
        # Test gestartet wurde; kill-server würde fremde Läufe beenden.
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "HOME": str(self.root / "home"),
                "PATH": str(self.root / "fakebin") + os.pathsep + env.get("PATH", ""),
                "TMUX_TMPDIR": str(self.tmux_dir),
                "TERM": env.get("TERM", "xterm"),
            }
        )
        return env

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def session_alive(self):
        return self.tmux("has-session", "-t", self.session).returncode == 0

    def shared_sessions(self):
        """Sitzungen des gemeinsamen tmux-Servers des Nutzers (ohne TMUX_TMPDIR)."""
        env = self.env()
        env.pop("TMUX_TMPDIR", None)
        result = subprocess.run(
            ["tmux", "ls", "-F", "#{session_name}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return [] if result.returncode != 0 else result.stdout.split()

    def start_run(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "run", self.name],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(
            self.session,
            self.shared_sessions(),
            "Test-Sitzung landete im gemeinsamen tmux-Server: TMUX_TMPDIR wird nicht beachtet.",
        )
        return result

    def log_text(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_session_ends_when_the_runner_has_finished(self):
        self.start_run()

        # Erst den Abschluss der Prüfung abwarten: Danach darf die Sitzung
        # nicht mehr auf eine Eingabe warten.
        deadline = time.time() + 15
        while time.time() < deadline and "=== Abschlussprüfung ===" not in self.log_text():
            time.sleep(0.1)
        log = self.log_text()
        self.assertIn("=== Abschlussprüfung ===", log, "Läufer hat nicht abgeschlossen:\n" + log)

        deadline = time.time() + 10
        while time.time() < deadline and self.session_alive():
            time.sleep(0.1)
        self.assertFalse(
            self.session_alive(),
            "tmux-Sitzung " + self.session + " blieb nach dem Lauf offen:\n" + log,
        )
        # Mit dem Schließen der Sitzung darf das Ergebnis nicht verloren gehen.
        self.assertIn("FERTIG", self.log_text())

    def test_session_ends_even_when_the_run_pauses(self):
        self.start_run()  # erst normal beenden, dann Pause vor dem Start setzen
        deadline = time.time() + 10
        while time.time() < deadline and self.session_alive():
            time.sleep(0.1)
        self.assertFalse(self.session_alive())

        flag = self.root / "_logs" / (self.name + ".pause-after")
        flag.write_text("", encoding="utf-8")
        self.start_run()

        deadline = time.time() + 10
        while time.time() < deadline and self.session_alive():
            time.sleep(0.1)

        log = self.log.read_text(encoding="utf-8")
        self.assertIn("Angehalten auf Wunsch", log)
        self.assertFalse(
            self.session_alive(),
            "tmux-Sitzung blieb nach der Pause offen:\n" + log,
        )
        self.assertFalse(flag.exists())


if __name__ == "__main__":
    unittest.main()
