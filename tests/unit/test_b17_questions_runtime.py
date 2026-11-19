"""Abnahme B17: Rückfragen ohne Produktivpfade (AK7).

``vibe ask`` und ``vibe answer`` lasen den Laufzeitordner bisher ausschließlich
aus der Umgebung (``VIBE_RUNTIME``). Im AP-Betrieb ist das ein Produktivpfad.
Neu ist die Option ``--runtime PFAD``: Fragen, Antworten und der autonome Modus
werden aus dem ausdrücklich übergebenen Laufzeitordner gelesen und dorthin
geschrieben.

Die Tests laden ``bin/vibe`` als Modul (Muster ``tests/unit/test_questions.py``)
mit einer isolierten Umgebung und rufen die Kommandofunktionen direkt auf. Es
werden keine Modelle oder Netzdienste benutzt; alle Pfade liegen unter einem
temporären Verzeichnis. Auch die vom Werkzeug ausgegebenen Fortsetzungsbefehle
müssen den Laufzeitordner nennen (Review 1, Finding 2).

Run:

    env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
        -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
        python3 -m unittest tests.unit.test_b17_questions_runtime -v
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
QUESTIONS = REPO / "bin" / "vibe_questions.py"

ISOLATED_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_DIR",
)


def load_module(name, path):
    bin_dir = str(Path(path).parent)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class QuestionRuntimeTest(unittest.TestCase):
    """cmd_ask/cmd_answer folgen dem ausdrücklichen --runtime."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env_runtime = self.root / "env-runtime"
        self.runtime = self.root / "pruef-runtime"
        self.questions = load_module(
            "vibe_questions_b17", QUESTIONS
        )
        self.cli = self._load_cli()

    def _load_cli(self):
        old = {key: os.environ.get(key) for key in ISOLATED_KEYS}
        for key in ISOLATED_KEYS:
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE": str(self.root / "vibe"),
            "VIBE_RUNTIME": str(self.env_runtime),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "HOME": str(self.home),
            "VIBE_NO_CONTAINER": "1",
        })
        try:
            return load_module("vibe_cli_b17", CLI)
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def run_cli(self, function, arguments):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            function(list(arguments))
        return out.getvalue()

    def question_files(self, runtime):
        folder = Path(runtime) / "questions"
        return [path for path in folder.iterdir()] if folder.is_dir() else []

    def test_cmd_ask_writes_into_the_given_runtime(self):
        self.cli.cmd_ask([
            "--runtime", str(self.runtime),
            "--project", "",
            "--no-wait",
            "Welche Farbe?",
            "--option", "Rot",
        ])

        self.assertEqual(len(self.question_files(self.runtime)), 1)
        self.assertEqual(
            self.question_files(self.env_runtime), [],
            "Die Frage wurde in den Laufzeitordner aus der Umgebung geschrieben",
        )

    def test_cmd_answer_uses_the_given_runtime(self):
        qid = self.questions.create(
            self.runtime, project="proj", text="Welche Farbe?", options=["Rot"]
        )

        self.run_cli(self.cli.cmd_answer, [
            "--runtime", str(self.runtime), qid, "--option", "1",
        ])

        record = self.questions.load(self.runtime, qid)
        self.assertIsNotNone(record["answer"])
        self.assertFalse((self.env_runtime / "questions").exists(),
                         "Die Antwort wurde über den Umgebungspfad gesucht")

    def test_wait_reads_the_answer_from_the_given_runtime(self):
        qid = self.questions.create(
            self.runtime, project="proj", text="Welche Farbe?", options=["Rot"]
        )
        self.questions.answer(self.runtime, qid, option=0, text="", by="cli")

        output = self.run_cli(self.cli.cmd_ask, [
            "--runtime", str(self.runtime), "--wait", qid,
        ])

        self.assertIn("Antwort", output)
        self.assertTrue(
            (self.runtime / "questions").is_dir(),
            "Der --runtime-Ordner wurde nicht verwendet",
        )

    def test_autonomous_mode_is_read_from_the_given_runtime(self):
        qid = self.questions.create(
            self.runtime, project="proj", text="Welche Farbe?", options=["Rot"]
        )
        self.cli.vibe_autonomous.set_enabled(self.runtime, "proj", True)

        self.assertTrue(self.cli.vibe_autonomous.is_enabled(self.runtime, "proj"))
        self.assertFalse(
            self.cli.vibe_autonomous.is_enabled(self.env_runtime, "proj"),
            "Der autonome Modus wurde im Umgebungspfad gespeichert",
        )
        # Der Wartepfad endet im autonomen Modus ohne Zeitlimit.
        output = self.run_cli(self.cli.cmd_ask, [
            "--runtime", str(self.runtime), "--wait", qid,
        ])
        self.assertIn("Autonomer Modus", output)

    def test_timeout_and_autonomous_hints_name_the_given_runtime(self):
        """Review 1/Medium: Fortsetzungsbefehle nennen den Laufzeitordner.

        Ohne ``--runtime`` in der Meldung würde ein Agent, der die Zeile
        wörtlich befolgt, den Produktivpfad aus seiner Konfiguration treffen.
        Geprüft werden die Timeout-Meldung und die Autonomie-Meldung.
        """
        qid = self.questions.create(
            self.runtime, project="proj", text="Welche Farbe?", options=["Rot"]
        )

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as raised:
                self.cli.cmd_ask([
                    "--runtime", str(self.runtime),
                    "--wait", qid,
                    "--timeout", "0.01",
                ])
        timeout_output = out.getvalue()
        self.assertEqual(raised.exception.code, 3)
        with self.subTest(hint="timeout"):
            self.assertIn("vibe ask --wait " + qid, timeout_output)
            self.assertIn(
                "--runtime " + str(self.runtime), timeout_output,
                "Die Timeout-Meldung schickt den Agenten ohne Laufzeitordner",
            )

        self.cli.vibe_autonomous.set_enabled(self.runtime, "proj", True)
        autonomous_output = self.run_cli(self.cli.cmd_ask, [
            "--runtime", str(self.runtime), "--wait", qid,
        ])
        with self.subTest(hint="autonomous"):
            self.assertIn("Autonomer Modus", autonomous_output)
            self.assertIn("vibe answer", autonomous_output)
            self.assertIn(
                "--runtime " + str(self.runtime), autonomous_output,
                "Die Autonomie-Meldung schickt den Agenten ohne Laufzeitordner",
            )
            self.assertIn(qid, autonomous_output)
            self.assertIn("--by agent", autonomous_output)


if __name__ == "__main__":
    unittest.main()
