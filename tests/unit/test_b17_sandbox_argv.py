"""Abnahme B17: Sandbox-Schnittstelle für Zusatzverzeichnisse und chdir (AK8/AK9).

Neu muss die Sandbox zusätzliche Schreibverzeichnisse binden (die Paket-
Arbeitskopie), das Arbeitsverzeichnis ausdrücklich setzen und den
Autonomiezustand nur lesend einbinden. Ohne die neuen Angaben bleibt das
bisherige Verhalten unverändert (AK9).

Die Tests prüfen die Argumentliste direkt an :func:`vibe_sandbox.bwrap_argv`.
Die Sandbox wird nicht gestartet; ``VIBE_BWRAP`` zeigt auf eine ausführbare
Attrappe, damit die Argumentkomposition ohne bubblewrap prüfbar ist.

Run:

    env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
        -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
        python3 -m unittest tests.unit.test_b17_sandbox_argv -v
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

MODULE_KEYS = ("VIBE_RUNTIME", "VIBE_SANDBOX_ROOT", "VIBE_BWRAP")


def load_sandbox():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_sandbox_b17", str(SANDBOX)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SandboxArgvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nSANDBOX=on\nSANDBOX_TOOLS=\"git\"\n", encoding="utf-8"
        )
        self.copy = self.root / "paket-arbeitskopie"
        self.copy.mkdir()
        self.runtime = self.root / "runtime"
        self.sandbox = load_sandbox()

        self.old = {key: os.environ.get(key) for key in MODULE_KEYS}
        self.addCleanup(self._restore_env)
        for key in MODULE_KEYS:
            os.environ.pop(key, None)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.root / "home")
        (self.root / "home").mkdir()
        fake_bwrap = self.root / "fake-bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_bwrap.chmod(0o755)
        os.environ["VIBE_BWRAP"] = str(fake_bwrap)

    def _restore_env(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def bind_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]

    def setenv_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] == "--setenv"
        ]

    def test_nested_sandbox_marker_is_set_once_before_the_command(self):
        """T-BR2: Der Sandbox-Start trägt den Verschachtelungsmarker.

        Vorbedingung: ``SANDBOX=on`` im Projekt und eine ausführbare
        ``VIBE_BWRAP``-Attrappe (es wird kein bubblewrap gestartet).

        Aktion: ``bwrap_argv`` für einen Sandbox-Start erzeugen.

        Erwartetes Ergebnis: Genau ein Paar
        ``('--setenv', 'VIBE_SANDBOX_ACTIVE', '1')`` steht in der
        Argumentliste, und zwar vor dem ``--``-Trenner. Nur so erbt der
        gestartete Prozess den Marker; die Endprüfung erkennt daran eine
        verschachtelte Sandbox und überspringt bwrap-abhängige Fälle mit
        Begründung, ohne pauschal auf bwrap-Verfügbarkeit zu prüfen.

        Fehlerfall: Marker fehlt, ist doppelt oder steht hinter ``--`` —
        dann erhält der Prozess ihn nicht und ein echter Defekt würde
        durch ein pauschales ``skipUnless`` verdeckt.
        """
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"], runtime=self.runtime
        )

        marker = ("--setenv", "VIBE_SANDBOX_ACTIVE", "1")
        self.assertEqual(self.setenv_pairs(argv).count(marker), 1, argv)
        separator = argv.index("--")
        self.assertLess(
            argv.index("VIBE_SANDBOX_ACTIVE"), separator,
            "Marker steht hinter dem Kommandotrenner und erreicht den "
            "gestarteten Prozess nicht",
        )
        self.assertNotIn("VIBE_SANDBOX_ACTIVE", argv[separator + 1:])

    def test_extra_write_dirs_are_bound_writable(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"],
            runtime=self.runtime,
            extra_write_dirs=[str(self.copy)],
            chdir=str(self.copy),
        )

        self.assertIn(
            ("--bind", str(self.copy), str(self.copy)), self.bind_pairs(argv),
            "Die Paket-Arbeitskopie ist nicht beschreibbar gebunden",
        )

    def test_chdir_overrides_the_working_directory(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"],
            runtime=self.runtime,
            extra_write_dirs=[str(self.copy)],
            chdir=str(self.copy),
        )

        self.assertIn("--chdir", argv)
        self.assertEqual(argv[argv.index("--chdir") + 1], str(self.copy))
        self.assertNotEqual(
            argv[argv.index("--chdir") + 1], os.path.realpath(self.project)
        )

    def test_question_folder_is_writable_and_autonomous_state_read_only(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"], runtime=self.runtime
        )
        questions = str(self.runtime / "questions")
        autonomous = str(self.runtime / "autonomous.json")

        pairs = self.bind_pairs(argv)
        self.assertIn(("--bind", questions, questions), pairs)
        self.assertIn(("--ro-bind-try", autonomous, autonomous), pairs)
        for flag, source, _target in pairs:
            if source == autonomous:
                self.assertEqual(
                    "--ro-bind-try", flag,
                    "autonomous.json darf nicht beschreibbar gebunden werden",
                )

    def test_without_new_arguments_the_previous_behaviour_stays(self):
        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertEqual(argv[argv.index("--chdir") + 1],
                         os.path.realpath(self.project))
        text = " ".join(argv)
        self.assertNotIn("questions", text)
        self.assertNotIn("autonomous.json", text)


if __name__ == "__main__":
    unittest.main()
