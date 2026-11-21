"""Tests der Harness-Installation (B18).

Fachlicher Rahmen
-----------------
B18 ergänzt die Harness-Schicht um ``vibe_harness.install(name, which=None,
runner=None, timeout=300, environ=None)``. Die Oberfläche darf einen Harness
nur dann wirksam wählen, wenn er installiert ist; für nicht installierte
Harnesses gibt es einen Installieren-Knopf. Der Installationsbefehl stammt
ausschließlich aus der Registry (``setup_plan``), niemals aus
Aufruferargumenten. Nach dem Lauf prüft ``install`` erneut („erneute
Prüfung“ auch serverseitig).

Vertrag (``docs/features/B18.md``, verbindlich):

* Unbekannter Harness → ``HarnessError`` (über ``definition``).
* Bereits installiert (``which(binary)`` findet das Programm): nichts
  ausführen; Ergebnis ``{"harness", "code": 0, "output": "", "already": True,
  "probe": …}``.
* Sonst den Registry-Befehl über die bestehende ``_run``-Semantik ausführen
  (Runner injizierbar) und danach erneut ``probe(name)``:
  ``{"harness", "code", "output", "already": False, "probe": <probe>}``.
* Pi-Befehl: ``npm install -g --ignore-scripts
  @earendil-works/pi-coding-agent``.
* Deutsche, verständliche Rückgaben; ``output`` wird wie im Bestand gekappt.

Die Fälle sind unabhängig von der Implementierung formuliert. Externe
Programme werden ausschließlich über die injizierten Parameter ``which`` und
``runner`` ersetzt; es startet kein echter Prozess.

Testfälle (Name — Vorbedingung — Aktion — Erwartung)
---------------------------------------------------
``test_06_missing_npm_reports_exit_127_and_stays_missing``
    Vorbedingung: ``which`` findet Pi nicht, der Runner liefert für npm 127.
    Aktion: ``install("pi", …)``. Erwartung: ``code == 127``,
    ``already is False``, der Registry-Befehl wurde exakt so aufgerufen, die
    erneute Probe bleibt nicht installiert (``status == "missing"``).
``test_07_successful_runner_triggers_a_fresh_ready_probe``
    Vorbedingung: ``which`` findet Pi nicht; der Runner meldet für npm Erfolg
    und für die Pi-Probe Version 0.72.0. Aktion: ``install("pi", …)``.
    Erwartung: ``code == 0``, ``already is False``, ``probe`` ist
    ``ready``/installiert mit Version 0.72.0; der Registry-Befehl wurde
    exakt so aufgerufen.
``test_08_already_installed_runs_no_install_command``
    Vorbedingung: ``which`` findet Pi. Aktion: ``install("pi", …)``.
    Erwartung: ``already is True``, ``code == 0``, ``output == ""``; kein
    npm-Aufruf (die Probe darf lesend laufen).
``test_09_unknown_harness_raises_harness_error``
    Vorbedingung: keiner. Aktion: ``install("unbekannt")``. Erwartung:
    ``HarnessError``.

ROT-PHASE (2026-11-21, vor der Implementierung)
----------------------------------------------
Aufruf::

    python3 -m unittest discover -s tests/unit -p 'test_b18_harness.py' -v

Ergebnis: 4 Tests, 4 ERROR.

* ``test_06``, ``test_07``, ``test_08``, ``test_09`` — ERROR
  (AttributeError): ``module 'vibe_harness' has no attribute 'install'``.
  Die neue Funktion existiert noch nicht; deshalb ist jeder Fall rot, bevor
  eine fachliche Assertion greifen kann. Nach der Implementierung prüfen die
  Fälle Runner-/Which-Injektion, Registry-Befehl, erneute Probe und
  ``HarnessError`` für unbekannte Namen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))

import vibe_harness  # noqa: E402  (bewusster Import nach sys.path-Anpassung)

PI_COMMAND = [
    "npm", "install", "-g", "--ignore-scripts",
    "@earendil-works/pi-coding-agent",
]


class HarnessInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.empty_path = self.root / "leer"
        self.empty_path.mkdir()
        self.environ = {"PATH": str(self.empty_path)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_06_missing_npm_reports_exit_127_and_stays_missing(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            if argv[0] == "npm":
                return 127, "npm: command not found"
            return 127, "pi: command not found"

        result = vibe_harness.install(
            "pi", which=lambda name: None, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(127, result["code"])
        self.assertFalse(result["already"])
        self.assertIn(PI_COMMAND, calls,
                      "Der Registry-Befehl wurde nicht exakt aufgerufen: "
                      + repr(calls))
        self.assertFalse(result["probe"]["installed"],
                         "Die erneute Probe meldet Pi fälschlich als "
                         "installiert: " + repr(result["probe"]))
        self.assertEqual("missing", result["probe"]["status"],
                         "Die erneute Probe meldet nicht 'missing': "
                         + repr(result["probe"]))

    def test_07_successful_runner_triggers_a_fresh_ready_probe(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            if argv[0] == "npm":
                return 0, "added 1 package"
            return 0, "0.72.0"

        result = vibe_harness.install(
            "pi", which=lambda name: None, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(0, result["code"])
        self.assertFalse(result["already"])
        self.assertIn(PI_COMMAND, calls,
                      "Der Registry-Befehl wurde nicht exakt aufgerufen: "
                      + repr(calls))
        probe = result["probe"]
        self.assertTrue(probe["installed"],
                        "Die erneute Probe meldet Pi nicht als installiert: "
                        + repr(probe))
        self.assertEqual("ready", probe["status"],
                         "Die erneute Probe ist nicht 'ready': " + repr(probe))
        self.assertEqual("0.72.0", probe["version"],
                         "Die erneute Probe liest die Version nicht: "
                         + repr(probe))

    def test_08_already_installed_runs_no_install_command(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            return 0, "0.72.0"

        result = vibe_harness.install(
            "pi", which=lambda name: "/usr/bin/" + name, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(0, result["code"])
        self.assertTrue(result["already"],
                        "Ein bereits installierter Harness wird nicht als "
                        "already gemeldet: " + repr(result))
        self.assertEqual("", result["output"],
                         "Ein bereits installierter Harness liefert eine "
                         "Befehlsausgabe: " + repr(result))
        self.assertFalse(
            [argv for argv in calls if argv and argv[0] == "npm"],
            "Für einen bereits installierten Harness wurde der "
            "Installationsbefehl ausgeführt: " + repr(calls))

    def test_09_unknown_harness_raises_harness_error(self):
        with self.assertRaises(vibe_harness.HarnessError):
            vibe_harness.install(
                "unbekannt", which=lambda name: None,
                environ=self.environ)


if __name__ == "__main__":
    unittest.main()
