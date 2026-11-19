"""Abnahme B17: Läufer startet Agenten und Prüfungen ohne Produktivpfade (AK6-AK8).

Der echte ``bin/vibe-run.sh`` läuft in einer Fake-Toolchain
(Muster ``tests/unit/test_b16_runner_wiring.py``). Die Startumgebung enthält
absichtlich Fake-Produktivpfade (``VIBE``, ``VIBE_PROFILE``, ``VIBE_INSTALL``,
``VIBE_STATE``, ``VIBE_RUNTIME``, ``VIBE_CONFIG_FILE``, ``VIBE_AGENTS_DIR``).

Geprüft wird:

* AK6: Die Agenten-Prozessumgebung enthält keine dieser ``VIBE_*``-Variablen.
* AK7: Der erzeugte Prompt nennt ``vibe ask --runtime <Laufzeit>`` und
  ``vibe ask --wait <id> --runtime``.
* AK8: Bei ``SANDBOX=on`` laufen Agent, Paketprüfung und Abschlussprüfung über
  die bubblewrap-Attrappe. Der Agent erhält das Konfigurationsprojekt und die
  Paket-Arbeitskopie als zusätzliches Schreibverzeichnis sowie ``--chdir`` auf
  die Arbeitskopie — auch wenn die Arbeitskopie selbst keine ``.vibe`` enthält.
  Die Prüfbefehle laufen mit bereinigter Umgebung. Das gilt auch für den
  Android-Direktzweig ohne ``VERIFY_FULL`` (Review 1, Finding 1).

Es werden keine Modelle aufgerufen und keine echten Produktivpfade berührt;
alle Pfade liegen unter ``tempfile``.

Run:

    env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
        -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
        python3 -m unittest tests.unit.test_b17_runner_isolation -v
"""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

PRODUCTIVE_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
)

FEEDBACK_ONE = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

GIT_IDENTITY = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

RECORDING_OPENCODE = r'''#!/usr/bin/env python3
"""Zeichnet Argumente und Prozessumgebung je Aufruf auf."""
import json
import os
import sys

record = os.environ.get("B17_RECORD")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(
            {"argv": sys.argv[1:], "env": dict(os.environ)},
            ensure_ascii=False,
        ) + "\n")
os.execvp("package-agent", ["package-agent"] + sys.argv[1:])
'''

FAKE_BWRAP = r'''#!/usr/bin/env python3
"""Zeichnet die bubblewrap-Argumente auf und führt den Befehl aus."""
import json
import os
import sys

args = sys.argv[1:]
record = os.environ.get("B17_BWRAP_RECORD")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args, ensure_ascii=False) + "\n")
if "--" not in args:
    raise SystemExit(0)
command = args[args.index("--") + 1:]
if not command:
    raise SystemExit(0)
os.execvp(command[0], command)
'''


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def read_env_file(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")

        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        (self.tool_bin / "vibe_sandbox.py").write_text(
            SANDBOX.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()

        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.opencode = self.fakebin / "opencode"
        self.opencode.write_text(RECORDING_OPENCODE, encoding="utf-8")
        self.opencode.chmod(0o755)
        self.package_agent = self.fakebin / "package-agent"
        self.package_agent.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        self.package_agent.chmod(0o755)
        (self.fakebin / "curl").write_text(support.FAKE_CURL, encoding="utf-8")
        (self.fakebin / "curl").chmod(0o755)
        self.bwrap = self.fakebin / "bwrap"
        self.bwrap.write_text(FAKE_BWRAP, encoding="utf-8")
        self.bwrap.chmod(0o755)

        self.record_path = self.root / "record.jsonl"
        self.bwrap_record = self.root / "bwrap.jsonl"

    def make_project(self, env_text, name="proj", hide_vibe=False):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=FEEDBACK_ONE)
        if hide_vibe:
            # Reproduziert den Vorfall: Die Arbeitskopie enthält keine .vibe,
            # das Konfigurationsprojekt aber schon.
            exclude = project / ".git" / "info" / "exclude"
            exclude.write_text(".vibe/\n", encoding="utf-8")
        support.commit_all(project, "Ausgangsstand")
        return project

    def verification_project(self, sandbox="off", name="proj"):
        package_env = self.root / (name + "-package.env")
        package_marker = self.root / (name + "-package.marker")
        full_env = self.root / (name + "-full.env")
        full_marker = self.root / (name + "-full.marker")
        env_text = (
            "TYPE=generic\n"
            "AGENT=test-agent\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            "MAX_RETRIES=1\n"
            "VERIFY_PACKAGE='env > \"%s\"; echo paket > \"%s\"'\n"
            "VERIFY_FULL='env > \"%s\"; echo final > \"%s\"'\n"
            "SANDBOX=%s\n"
            'SANDBOX_TOOLS="git"\n'
        ) % (package_env, package_marker, full_env, full_marker, sandbox)
        project = self.make_project(
            env_text, name=name, hide_vibe=(sandbox == "on")
        )
        return project, {
            "package_env": package_env,
            "package_marker": package_marker,
            "full_env": full_env,
            "full_marker": full_marker,
        }

    def android_project(self, name="android"):
        """Projekt mit ``TYPE=android`` und leerem ``VERIFY_FULL``.

        Der Läufer wählt dann den Android-Direktzweig
        ``bash "$V/verify.sh" "$P" full``. Das Prüfskript schreibt seine
        Prozessumgebung und einen Marker; die Hash-Datei lässt ``check_hash``
        den Lauf starten.
        """
        self.android_env = self.root / (name + "-verify.env")
        self.android_marker = self.root / (name + "-verify.marker")
        verify_dir = self.install / "verify"
        verify_dir.mkdir(parents=True)
        script = verify_dir / "verify.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "env > " + shlex.quote(str(self.android_env)) + "\n"
            "echo android > " + shlex.quote(str(self.android_marker)) + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        hash_file = self.home / ".config" / "schreibfuchs-verify.sha"
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(digest + "  verify.sh\n", encoding="utf-8")
        env_text = (
            "TYPE=android\n"
            "AGENT=test-agent\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            "MAX_RETRIES=1\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL=""\n'
            "SANDBOX=on\n"
            'SANDBOX_TOOLS="git"\n'
        )
        return self.make_project(env_text, name=name, hide_vibe=True)

    def env(self, project, sandbox=False, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("VIBE", "FAKE_", "B17_")):
                env.pop(key, None)
        for key in ("AGENT", "MAX_PACKAGES", "MAX_RETRIES", "SANDBOX",
                    "SANDBOX_TOOLS", "VERIFY_FULL", "VERIFY_PACKAGE"):
            env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_PROFILE": "prod",
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": project.name,
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_COUNTER": str(self.root / "counter"),
            "FAKE_CALLS": str(self.root / "calls.jsonl"),
            "B17_RECORD": str(self.record_path),
            "B17_BWRAP_RECORD": str(self.bwrap_record),
        })
        if sandbox:
            env["VIBE_BWRAP"] = str(self.bwrap)
        env.update(GIT_IDENTITY)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, sandbox=False, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, sandbox=sandbox, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def agent_record(self):
        for record in read_jsonl(self.record_path):
            argv = record.get("argv") or []
            if argv and argv[0] == "run":
                return record
        return None

    def bwrap_records(self):
        return read_jsonl(self.bwrap_record)

    def bwrap_invocation(self, needle):
        for argv in self.bwrap_records():
            if needle in " ".join(argv):
                return argv
        return None


class AgentEnvironmentTest(RunnerFixture):
    """AK6: keine Produktivpfade im Agentenprozess."""

    def test_agent_process_has_no_vibe_paths(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record, "Kein Agentenaufruf aufgezeichnet")
        present = [key for key in PRODUCTIVE_KEYS if key in record["env"]]
        self.assertEqual(
            [], present,
            "Der Agentenprozess erbt Produktivpfade: " + ", ".join(present),
        )

    def test_agent_process_keeps_its_run_control_variables(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record)
        self.assertEqual(record["env"].get("VIBE_LOGNAME"), project.name,
                         "Laufsteuer-Variablen dürfen erhalten bleiben")


class QuestionHintTest(RunnerFixture):
    """AK7: Der Prompt nennt die Laufzeit für Rückfragen ausdrücklich."""

    def test_prompt_contains_runtime_for_ask_and_wait(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record, "Kein Agentenaufruf aufgezeichnet")
        prompt = record["argv"][-1]
        self.assertIn("vibe ask --runtime", prompt)
        self.assertIn("vibe ask --wait", prompt)
        self.assertIn(
            str(self.runtime.resolve()), prompt,
            "Der Prompt nennt den Laufzeitordner des Laufs nicht",
        )
        self.assertIn("--runtime", prompt.split("vibe ask --wait", 1)[1])


class SandboxWiringTest(RunnerFixture):
    """AK8: Sandbox gilt für Agent und Prüfungen, auch ohne .vibe in der Kopie."""

    def test_agent_runs_in_the_sandbox_with_config_project_and_worktree(self):
        project, _paths = self.verification_project(sandbox="on")

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        invocation = self.bwrap_invocation("opencode")
        self.assertIsNotNone(
            invocation,
            "Der Agent lief nicht über bubblewrap:\n" + result.stdout,
        )
        argv = invocation
        separator = argv.index("--")
        command = argv[separator + 1:]
        self.assertEqual(command[0], "opencode")
        self.assertIn("run", command)

        pairs = [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]
        real_project = os.path.realpath(project)
        chdir = argv[argv.index("--chdir") + 1]
        self.assertTrue(
            chdir.startswith(str(self.runtime.resolve()) + os.sep + "worktrees"),
            "Der Agent läuft nicht in der Paket-Arbeitskopie: " + chdir,
        )
        self.assertIn(("--bind", real_project, real_project), pairs,
                      "Das Konfigurationsprojekt ist nicht schreibbar gebunden")
        self.assertIn(("--bind", chdir, chdir), pairs,
                      "Die Paket-Arbeitskopie ist nicht schreibbar gebunden")
        self.assertIn(
            ("--ro-bind", os.path.join(real_project, ".vibe"),
             os.path.join(real_project, ".vibe")),
            pairs,
            "Die Sandbox liest die Konfiguration nicht aus dem Projekt",
        )

    def test_package_and_final_verification_run_in_the_sandbox(self):
        project, paths = self.verification_project(sandbox="on")

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(paths["package_marker"].is_file(),
                        "Paketprüfung lief nicht:\n" + result.stdout)
        self.assertTrue(paths["full_marker"].is_file(),
                        "Abschlussprüfung lief nicht:\n" + result.stdout)
        self.assertIsNotNone(
            self.bwrap_invocation(str(paths["package_marker"])),
            "Paketprüfung lief außerhalb der Sandbox",
        )
        self.assertIsNotNone(
            self.bwrap_invocation(str(paths["full_marker"])),
            "Abschlussprüfung lief außerhalb der Sandbox",
        )
        for key in ("package_env", "full_env"):
            values = read_env_file(paths[key])
            leaked = [name for name in PRODUCTIVE_KEYS if name in values]
            self.assertEqual(
                [], leaked,
                "Die Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )

    def test_android_final_verification_runs_in_the_sandbox_with_clean_environment(self):
        """Review 1/High: Auch der Android-Direktzweig läuft isoliert.

        ``final_verify`` ruft bei leerem ``VERIFY_FULL`` das Abnahmeskript
        direkt auf. Es muss über denselben Sandbox-/Clean-Env-Adapter laufen
        wie die generische Abschlussprüfung und ``VIBE_VERIFY_RUNTIME``
        erhalten.
        """
        project = self.android_project()

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            self.android_marker.is_file(),
            "Die Android-Abschlussprüfung lief nicht:\n" + result.stdout,
        )
        values = read_env_file(self.android_env)
        with self.subTest(check="sandbox"):
            self.assertIsNotNone(
                self.bwrap_invocation("verify.sh"),
                "Die Android-Abschlussprüfung lief außerhalb der Sandbox:\n"
                + result.stdout,
            )
        with self.subTest(check="cleaned-environment"):
            leaked = [key for key in PRODUCTIVE_KEYS if key in values]
            self.assertEqual(
                [], leaked,
                "Die Android-Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )
        with self.subTest(check="verify-runtime"):
            self.assertTrue(
                "VIBE_VERIFY_RUNTIME" in values,
                "Die Android-Prüfung erhält kein VIBE_VERIFY_RUNTIME",
            )
            self.assertEqual(
                os.path.realpath(self.runtime),
                os.path.realpath(values.get("VIBE_VERIFY_RUNTIME", "")),
                "VIBE_VERIFY_RUNTIME nennt nicht den Laufzeitordner des Laufs",
            )

    def test_verification_without_sandbox_is_unwrapped_but_cleaned(self):
        project, paths = self.verification_project(sandbox="off")

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(paths["package_marker"].is_file())
        self.assertTrue(paths["full_marker"].is_file())
        self.assertIsNone(
            self.bwrap_invocation(str(paths["package_marker"])),
            "Bei SANDBOX=off darf die Paketprüfung nicht gewrappt laufen",
        )
        self.assertIsNone(
            self.bwrap_invocation(str(paths["full_marker"])),
            "Bei SANDBOX=off darf die Abschlussprüfung nicht gewrappt laufen",
        )
        for key in ("package_env", "full_env"):
            values = read_env_file(paths[key])
            leaked = [name for name in PRODUCTIVE_KEYS if name in values]
            self.assertEqual(
                [], leaked,
                "Die Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )


if __name__ == "__main__":
    unittest.main()
