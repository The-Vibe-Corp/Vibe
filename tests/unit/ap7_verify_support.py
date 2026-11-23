"""Gemeinsame Fixturen für die AP7-Korbat-Tests (verify.sh/Engine/Baseline).

Die Datei ist kein Testmodul (der Name beginnt nicht mit ``test_``). Sie
liefert kleine Fixture-Projekte, Aufrufhelfer für das echte
``scripts/verify.sh`` und das heute noch gültige ``scripts/verify.py`` sowie
Hilfen für Baseline-Dateien.

Alle Pfade liegen in temporären Verzeichnissen; ``HOME`` und ``VIBE`` werden
auf Fixture-Ordner gezeigt. Es werden keine Modell-, MCP- oder
Produktivpfade verwendet.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "scripts" / "verify.sh"
VERIFY_PY = REPO / "scripts" / "verify.py"
ENGINE = REPO / "scripts" / "verify_engine.py"
TEST_RUNNER = REPO / "scripts" / "run-tests-parallel.py"

# Fixture-Module. Ein grünes Modul meldet über eine eindeutige Zeile, dass es
# tatsächlich gelaufen ist; nur so lässt sich „Befehl ausgeführt“ von
# „Befehl nur konfiguriert“ unterscheiden.
GREEN_TEST = (
    "import unittest\n\n"
    "class GruenTest(unittest.TestCase):\n"
    "    def test_gruen(self):\n"
    "        print('AP7-GRUEN-GELAUFEN')\n"
    "        self.assertTrue(True)\n"
)

RED_TEST = (
    "import unittest\n\n"
    "class RotTest(unittest.TestCase):\n"
    "    def test_rot(self):\n"
    "        self.fail('AP7-BEKANNT-ROT')\n"
)

# Gleiches Modul, anderer Fehler (andere Klasse/Meldung): Die Signatur muss
# sich ändern, sonst würde eine geänderte Regression als „bekannt“ gelten.
RED_TEST_OTHER = (
    "import unittest\n\n"
    "class RotTest(unittest.TestCase):\n"
    "    def test_rot(self):\n"
    "        raise ValueError('AP7-NEU-ROT')\n"
)

RAN_RE = re.compile(r"Ran (\d+) tests?")


def clean_environment(extra=None):
    """Umgebung ohne geerbte VIBE_*/VERIFY_*- und tmux-Werte.

    Die Prüfung darf nie von der Konfiguration des Aufrufers abhängen; nur die
    im Test ausdrücklich gesetzten Werte bleiben erhalten.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VIBE_") and not key.startswith("VERIFY_")
    }
    for key in ("TMUX", "TMUX_PANE"):
        environment.pop(key, None)
    environment.update({key: str(value) for key, value in (extra or {}).items()})
    return environment


def run_verify(*args, project=None, env=None, cwd=None, timeout=180):
    """Startet das echte ``scripts/verify.sh`` (Frontend)."""
    command = ["bash", str(VERIFY), *args]
    if project is not None:
        command.extend(["--project", str(project)])
    return subprocess.run(
        command,
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=clean_environment(env),
    )


def run_verify_py(*args, project=None, env=None, cwd=None, timeout=180):
    """Startet den bisherigen Aufrufer ``scripts/verify.py``."""
    command = [sys.executable, str(VERIFY_PY), *args]
    if project is not None:
        command.extend(["--project", str(project)])
    return subprocess.run(
        command,
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=clean_environment(env),
    )


def output(result):
    return result.stdout + result.stderr


def ran_tests(text):
    """Summe der ``Ran N tests``-Zeilen eines Ausdrucks."""
    return sum(int(count) for count in RAN_RE.findall(text))


class VerifyFixture(unittest.TestCase):
    """Basis-Fixture: temporäres Projekt, eigenes HOME/VIBE."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.vibe = self.base / "vibe"
        self.vibe.mkdir()

    def env(self, **extra):
        values = {
            "HOME": str(self.home),
            "VIBE": str(self.vibe),
            "VIBE_NO_CONTAINER": "1",
        }
        values.update({key: str(value) for key, value in extra.items()})
        return values

    def make_project(self, lines, name="projekt"):
        project = self.base / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        return project

    def write_module(self, project, relative, source):
        path = Path(project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def verify(self, *args, project=None, timeout=180, **extra):
        return run_verify(
            *args,
            project=project,
            env=self.env(**extra),
            timeout=timeout,
        )


def write_baseline(path, envs=None, min_tests=1, version=1):
    """Schreibt eine Baseline im Schema v1 und liefert ihre Daten."""
    data = {"version": version, "min_tests": min_tests, "envs": envs or {}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def read_baseline(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def local_baseline(project):
    return Path(project) / ".vibe" / "verify-baseline"


def committed_baseline(project):
    return Path(project) / "tests" / "verify-baseline.json"
