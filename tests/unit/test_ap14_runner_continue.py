"""Unit-Abnahme AP14 (Teil 3): Fortsetzung eines Laufs in derselben Session.

Arbeitspaket AP14 verlangt „Continue-Fortsetzung eines Laufs in derselben
Session“. Zwei Ebenen tragen das:

* ``vibe.cmd_run(name, agent=None, out=None, keep_changes=False,
  continue_session=None)``: ``continue_session`` wird gegen
  ``[A-Za-z0-9_-]`` geprüft; ein ungültiger Wert bricht den Start mit
  ``sys.exit`` und Meldung ab. Ein gültiger Wert wird dem Läufer als
  Umgebungsvariable ``VIBE_CONTINUE_SESSION=<id>`` mitgegeben (analog zum
  bestehenden ``VIBE_KEEP_CHANGES``-Export).
* ``bin/vibe-run.sh``: Mit ``VIBE_CONTINUE_SESSION=<id>`` startet der
  opencode-Zweig bereits den ersten Paketversuch mit
  ``opencode run --session <id>``, und auch folgende Pakete desselben Laufs
  starten mit ``--session`` (Fortsetzungskette). Im Laufprotokoll erscheint
  eine Zeile mit „Fortsetzung in Session“ und der Kennung. Ohne die
  Variable bleibt das F25-Verhalten unverändert (kein ``--session`` beim
  ersten Versuch). Ein Wert mit ungültigen Zeichen wird ignoriert. Der
  Pi-Zweig erhält niemals ``--session``.

Der Agent wird durch Attrappen im isolierten PATH ersetzt (Muster
tests/unit/test_f25_session_continue.py); ``cmd_run`` wird als Modul mit
einer tmux-Attrappe geladen (Muster tests/unit/test_f27_keep_changes.py).
Es werden keine Modellaufrufe ausgeführt.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = REPO / "bin" / "vibe"
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support  # noqa: E402

CONTINUE_SESSION = "ses_continue"
BAD_SESSION = "ses;x"

PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)


def load_module(path, name):
    """Lädt ein bin-Modul als Testunterlage (ohne Installation)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
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


def session_values(record):
    """Werte aller ``--session``-Argumente einer aufgezeichneten Argumentliste."""
    return [
        record[position + 1]
        for position in range(len(record) - 1)
        if record[position] == "--session"
    ]


class CliContinueExportTest(unittest.TestCase):
    """``vibe.cmd_run``: Validierung von ``continue_session`` und Export."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        support.write_agents(cls.agents, "test-agent", "code-reviewer")
        cls.install = cls.root / "_toolchain"
        cls.runtime = cls.root / "_logs"
        cls.project = cls.root / "proj"
        support.init_repo(cls.project)
        support.write_project(
            cls.project, PROJECT_ENV,
            feedback="- [ ] AP14 Continue\n  Beschreibung: Test\n",
        )
        project_agent = cls.project / ".opencode" / "agents" / "test-agent.md"
        project_agent.parent.mkdir(parents=True)
        project_agent.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n",
            encoding="utf-8",
        )
        support.commit_all(cls.project, "Ausgangsstand")
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.addClassCleanup(cls.tmp.cleanup)
        cls._old_env = os.environ.copy()
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("FAKE_")
                or key.startswith("SANDBOX")
                or key in (
                    "AGENT", "TESTER", "REVIEWER", "MAX_RETRIES",
                    "VERIFY_QUICK", "VERIFY_FULL", "VERIFY_PACKAGE",
                )
            ):
                env.pop(key, None)
        (cls.root / "tmp").mkdir(exist_ok=True)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_INSTALL": str(cls.install),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "TMPDIR": str(cls.root / "tmp"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_TMUX_LOG": str(cls.tmux_log),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        os.environ.clear()
        os.environ.update(env)
        cls.module = load_module(CLI, "vibe_ap14_cli_under_test")
        cls.addClassCleanup(cls._restore_env)

    @classmethod
    def _restore_env(cls):
        os.environ.clear()
        os.environ.update(cls._old_env)

    def setUp(self):
        if self.tmux_log.exists():
            self.tmux_log.unlink()

    def new_session_commands(self):
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def test_invalid_continue_session_aborts_with_message_and_without_start(self):
        """Ungültige Kennung: Abbruch über sys.exit mit Meldung; es darf kein
        Lauf gestartet werden."""
        for value in ("ses;x", "ses/../x", "ses x", "ses;x;rm"):
            with self.subTest(value=value):
                if self.tmux_log.exists():
                    self.tmux_log.unlink()
                with self.assertRaises(SystemExit) as caught:
                    self.module.cmd_run("proj", continue_session=value)
                self.assertTrue(
                    str(caught.exception).strip(),
                    f"Abbruch ohne Meldung für {value!r}",
                )
                self.assertEqual(
                    [], self.new_session_commands(),
                    f"Ungültige Kennung {value!r} startete dennoch einen Lauf",
                )

    def test_valid_continue_session_is_exported_to_the_runner(self):
        self.module.cmd_run("proj", continue_session=CONTINUE_SESSION)

        commands = self.new_session_commands()
        self.assertTrue(
            commands, "Der Start hat keinen Läufer-Befehl erzeugt (tmux-Attrappe)"
        )
        joined = "\n".join(commands)
        self.assertIn(
            f"VIBE_CONTINUE_SESSION={CONTINUE_SESSION}",
            joined,
            "Der Startbefehl exportiert die Session nicht an den Läufer: "
            + joined,
        )

    def test_without_continue_session_nothing_is_exported(self):
        """Regression F27: Ohne continue_session bleibt der Startbefehl frei
        von VIBE_CONTINUE_SESSION."""
        self.module.cmd_run("proj")

        commands = self.new_session_commands()
        self.assertTrue(commands, "Startbefehl fehlt")
        self.assertNotIn(
            "VIBE_CONTINUE_SESSION", "\n".join(commands),
            "Ohne continue_session wird nichts exportiert",
        )


class RunnerContinueChainFixture(unittest.TestCase):
    """Läufer, opencode-Attrappe und isoliertes Projekt mit zwei Paketen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        # AP14: Die Fixture liefert die echte Harness-Schicht, damit der
        # Läufer den Produktionspfad ($BIN/vibe_harness.py, Auswahl und
        # Pi-Start über run_argv/os.execvp) benutzt und keine doppelte
        # Auswahl-/Prompt-Nachbildung im Shell-Skript nötig ist. Python fügt
        # das Skriptverzeichnis automatisch zum sys.path; die drei Module
        # liegen deshalb nebeneinander in $INSTALL/bin.
        for name in ("vibe_harness.py", "vibe_opencode.py", "vibe_storage.py"):
            (self.tool_bin / name).write_text(
                (BIN / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.write_project()
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.args = self.root / "opencode.args"
        self.fakebin = support.install_fake_tools(self.root)
        self.addCleanup(self.tmp.cleanup)

    def write_project(self, env_text=None, feedback=None):
        env_text = env_text or PROJECT_ENV
        support.write_project(
            self.project, env_text,
            feedback=feedback if feedback is not None else (
                "- [ ] AP14A Erster Schritt\n  Beschreibung: Test\n"
                "- [ ] AP14B Zweiter Schritt\n  Beschreibung: Test\n"
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
            timeout=180,
        )

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def arg_records(self):
        records = support.opencode_arg_records(self.args)
        self.assertTrue(records, "opencode wurde nicht aufgerufen")
        return records


class RunnerContinueChainTest(RunnerContinueChainFixture):
    """Mit VIBE_CONTINUE_SESSION startet der erste Versuch — und die Kette."""

    def test_first_package_and_the_chain_start_with_the_given_session(self):
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="complete,complete",
            VIBE_CONTINUE_SESSION=CONTINUE_SESSION,
        )

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)
        records = self.arg_records()
        self.assertEqual(
            2, len(records),
            f"Erwartet ein Aufruf je Paket: {records}",
        )
        self.assertEqual(
            [CONTINUE_SESSION], session_values(records[0]),
            "Der erste Paketversuch startet nicht mit --session "
            + CONTINUE_SESSION + ": " + repr(records[0]),
        )
        self.assertIn(
            "Arbeitspaket AP14A", records[0][-1],
            "Erster Prompt unvollständig: " + repr(records[0][-1]),
        )
        chain = session_values(records[1])
        self.assertEqual(
            1, len(chain),
            "Das folgende Paket startet ohne genau eine Fortsetzungskennung: "
            + repr(records[1]),
        )
        self.assertTrue(
            chain and re.fullmatch(r"[A-Za-z0-9_-]+", chain[0] or ""),
            "Die Fortsetzungskennung des Folgepakets ist leer oder ungültig: "
            + repr(chain),
        )
        self.assertIn(
            "Arbeitspaket AP14B", records[1][-1],
            "Zweiter Prompt unvollständig: " + repr(records[1][-1]),
        )
        continuation_lines = [
            line for line in log.splitlines()
            if "Fortsetzung in Session" in line
        ]
        self.assertTrue(
            continuation_lines,
            "Im Log fehlt eine Zeile mit 'Fortsetzung in Session':\n" + log,
        )
        self.assertTrue(
            any(CONTINUE_SESSION in line for line in continuation_lines),
            "Die Fortsetzungszeile nennt nicht die Kennung "
            + CONTINUE_SESSION + ":\n" + repr(continuation_lines),
        )


class RunnerPlainRepeatTest(RunnerContinueChainFixture):
    """Ohne VIBE_CONTINUE_SESSION bleibt das F25-Verhalten unverändert."""

    def test_without_continue_session_the_first_attempt_starts_fresh(self):
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="fail,complete,complete",
        )

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)
        records = self.arg_records()
        self.assertEqual(
            3, len(records),
            f"Erwartet zwei Versuche für AP14A und einen für AP14B: "
            f"{records}",
        )
        self.assertNotIn(
            "--session", records[0],
            "Der erste Versuch startet nicht fortgesetzt: " + repr(records[0]),
        )
        self.assertEqual(
            ["ses_attempt1"],
            session_values(records[1]),
            "Die F25-Wiederholung nimmt nicht die erfasste Session auf: "
            + repr(records[1]),
        )

    def test_invalid_continue_session_is_ignored(self):
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="complete,complete",
            VIBE_CONTINUE_SESSION=BAD_SESSION,
        )

        self.assertEqual(
            0, result.returncode,
            "Ein ungültiger VIBE_CONTINUE_SESSION-Wert darf den Lauf nicht "
            "abbrechen:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)
        for record in self.arg_records():
            self.assertNotIn(
                "--session", record,
                "Ungültige Kennung wurde übergeben: " + repr(record),
            )
        self.assertNotIn(
            "Fortsetzung in Session", log,
            "Ungültige Kennung erzeugte eine Fortsetzungsmeldung:\n" + log,
        )


class RunnerPiNeverContinuesTest(RunnerContinueChainFixture):
    """Der Pi-Zweig erhält niemals --session (Pi läuft mit --no-session)."""

    def test_pi_branch_never_receives_a_session(self):
        # Pi-Auswahl (echter Auswahlstand des Läufers) und Pi-Attrappe; der
        # Pi-Zweig liest den Prompt-Text der Agentendatei, die Dateien brauchen
        # deshalb einen echten Text.
        (self.install / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for name in ("tester", "test-agent", "code-reviewer", "reviewer"):
            (self.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8",
            )
        pi_args = self.root / "pi.args"
        shutil = __import__("shutil")
        shutil.copyfile(self.fakebin / "opencode", self.fakebin / "pi")
        self.fakebin.joinpath("pi").chmod(0o755)

        result = self.run_runner(
            FAKE_MODE_SEQUENCE="complete",
            FAKE_ARGS_PATH=str(pi_args),
            VIBE_CONTINUE_SESSION=CONTINUE_SESSION,
        )

        self.assertEqual(
            0, result.returncode,
            "Pi-Lauf bricht ab:\n" + result.stdout + result.stderr,
        )
        self.assertIn(
            "FERTIG", self.log_text(),
            "Pi-Lauf ohne Abnahme:\n" + self.log_text(),
        )
        records = support.opencode_arg_records(pi_args)
        self.assertTrue(
            records, "Die Pi-Attrappe wurde nicht aufgerufen"
        )
        for record in records:
            self.assertIn(
                "--no-session", record,
                "Der Aufruf ist kein Pi-Print-Modus-Aufruf: " + repr(record),
            )
            self.assertNotIn(
                "--session", record,
                "Der Pi-Zweig erhielt --session: " + repr(record),
            )


if __name__ == "__main__":
    unittest.main()
