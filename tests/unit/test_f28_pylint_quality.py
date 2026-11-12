"""Akzeptanztests für Arbeitspaket F28: Code-Verbesserungen gemäß pylint-Bericht.

Grundlage: TICKETS.md „F28 Code Verbesserungen“; der pylint-Lauf des Nutzers
vor der Umsetzung von B9 liegt als Kopie in
docs/reviews/F28-nutzer-pylint-report_2026_11_10.txt, ein identischer Lauf am
aktuellen Paketstand in docs/reviews/F28-pylint-baseline_2026_11_10.txt
(pylint 4.0.5, Rating 8.65/10, 747 Ausgabezeilen).

Akzeptanzkriterien (siehe Arbeitspaket F28):
  AK1 Lint-Qualität: Derselbe pylint-Lauf (gleiche 16 Module in ./bin, gleiche
      Arbeitsumgebung, gleiche pylint-Installation) meldet nach der
      Implementierung keine Befunde mehr außerhalb der unten offen
      dokumentierten Ausnahmeliste. Der Haupt-Test schlägt am aktuellen
      Ausgangsstand bewusst ROT an (z. B. C0116 missing-function-docstring,
      C0321 multiple-statements, W0718 broad-exception-caught, E1101
      no-member, R0801 duplicate-code, W1514 unspecified-encoding).
  AK2 Verhaltenserhaltung: keine neuen Fehler in tests/unit und tests/browser;
      das wird nicht als verschachtelter Unittest geprüft, sondern durch
      getrennte Läufe der bestehenden Suiten dokumentiert:
        python3 -m unittest discover -s tests/unit
        python3 -m unittest discover -s tests/browser

Offen dokumentierte Ausnahmeliste (Symbolnamen exakt wie pylint 4.0.5 sie
meldet; nichts ist versteckt):
  Struktur-/Design-Befunde der im Arbeitspaket genannten Klassen:
    too-many-branches             (R0912)
    too-many-locals               (R0914)
    too-many-arguments            (R0913)
    too-many-positional-arguments (R0917)
    too-many-statements           (R0915)
    too-many-return-statements    (R0911)
    too-many-nested-blocks        (R0101)
    too-many-boolean-expressions  (R0916; AK-Kürzel „boolean-expressions“)
    too-many-lines                (C0302; AK-Kürzel „lines“)
    line-too-long                 (C0301; ergänzend unter der „lines“-Klasse
        dokumentiert: Zeilenumbrüche in HTML-/URL-Template-Strings ändern
        sonst die Bytefolge der ausgelieferten Oberfläche und kollidieren
        mit AK2. Als einzige Zusatzausnahme offen benannt.)
  Modul-Namens-Befunde: invalid-name (C0103) NUR für den Modulnamen der
    beiden Einstiegsdateien mit Bindestrich (fritz-reconnect.py, vibe-web.py).
    Variablen- und Methodennamen-Befunde (z. B. SRV, do_GET) sindNICHT
    ausgenommen.
  Alles Weitere muss behoben werden.

Testbefehl:  python3 -m unittest tests.unit.test_f28_pylint_quality -v
"""

import json
import os
import pathlib
import shutil
import subprocess
import unittest

WERKZEUGWURZEL = pathlib.Path(__file__).resolve().parents[2]
BIN = WERKZEUGWURZEL / "bin"

# Baselisten aus docs/reviews/F28-pylint-baseline_2026_11_10.txt, ergänzt um
# das AP13-Modul vibe_ui_config.py, damit auch es in der Baseline gelintet
# wird (die Ausnahmeliste wird dafür nicht erweitert).
MODULE = [
    "fritz-reconnect.py",
    "vibe-web.py",
    "vibe_autonomous.py",
    "vibe_github.py",
    "vibe_guide.py",
    "vibe_harness.py",
    "vibe_mcp.py",
    "vibe_models.py",
    "vibe_opencode.py",
    "vibe_packages.py",
    "vibe_paths.py",
    "vibe_ui_config.py",
    "vibe_questions.py",
    "vibe_runs.py",
    "vibe_sandbox.py",
    "vibe_services.py",
    "vibe_storage.py",
]

# Offene Ausnahmeliste (siehe Moduldokumentation):
AUSNAHMEN_SYMBOLE = {
    "too-many-branches",
    "too-many-locals",
    "too-many-arguments",
    "too-many-positional-arguments",
    "too-many-statements",
    "too-many-return-statements",
    "too-many-nested-blocks",
    "too-many-boolean-expressions",
    "too-many-lines",
    "line-too-long",
}
BINDESTRICH_MODUL = {"fritz-reconnect.py", "vibe-web.py"}

PYLINT_PRIMAER = "/usr/bin/pylint"
PRUEF_TIMEOUT_S = 600
ARTIFAKTORDNER = "/tmp/opencode/f28-test-agent"


class F28PylintQualitaet(unittest.TestCase):
    """AK1: pylint-Qualität der Module in bin/ im Rahmen des F28-Berichts."""

    @classmethod
    def setUpClass(cls):
        pylintpfad = PYLINT_PRIMAER if os.path.isfile(PYLINT_PRIMAER) else shutil.which("pylint")
        if pylintpfad is None:
            raise unittest.SkipTest(
                "pylint nicht verfügbar (/usr/bin/pylint fehlt und kein 'pylint' "
                "im PATH). Prüfung laut Vorgabe mit skipTest übersprungen."
            )
        cls.pylint = pylintpfad
        fehlende = [n for n in MODULE if not (BIN / n).is_file()]
        if fehlende:
            raise unittest.SkipTest(
                "Prüfungstemplates nicht vorhanden: fehlende Module in bin/: "
                f"{fehlende}"
            )
        pathlib.Path(ARTIFAKTORDNER).mkdir(parents=True, exist_ok=True)
        # Keine produktive HOME-Pylint-Konfiguration in die Prüfung ziehen:
        umgebung = dict(os.environ)
        umgebung["PYLINTHOME"] = os.path.join(ARTIFAKTORDNER, ".pylint-home")
        cls.umgebung = umgebung
        cls.befehl = [cls.pylint, "--output-format=json", "-j", "1", *MODULE]
        cls.lauf = subprocess.run(
            cls.befehl,
            cwd=str(BIN),
            capture_output=True,
            text=True,
            timeout=PRUEF_TIMEOUT_S,
            env=umgebung,
        )
        try:
            cls.befunde = json.loads(cls.lauf.stdout)
        except ValueError as fehler:
            raise AssertionError(
                f"pylint lief, aber lieferte keine gültige JSON-Ausgabe "
                f"(rc={cls.lauf.returncode}, stderr={cls.lauf.stderr[:200]!r}): {fehler}"
            ) from fehler

    def test_ak1_pylint_ausfuehrung_gesichert(self):
        """AK1/Schutzgitter: Der Lauf ist wirklich gesichert worden.

        Vorbedingung: pylint vorhanden, 16 Module existieren in bin/, Lauf mit
        derselben Modulliste und Arbeitsverzeichnis wie die Baseline.
        Aktion: Exit-Code, Befundmenge und Nachweis prüfen, dass beide
        Bindestrich-Einstiegsdateien (modulbezogener invalid-name) gelintet
        wurden.
        Erwartet: rc im Befundberbereich (1,2,3,4,8,16,31,32), >= 1 Befund,
        für beide Einstiegsdateien je ein Modulnamen-invalid-name-Befund.
        Fehlerfall: rc=0 (ergebnisloser Lauf) oder übersprungene
        Einstiegsdateibenachricht → AssertionError.
        """
        rc = self.lauf.returncode
        # pylint-Exitcodes sind eine Bitmaske (fatal=1, error=2, warning=4,
        # refactor=8, convention=16, usagesfehler=32): jeder Nicht-null-Wert
        # unter 32 ist ein normaler Lauf mit Befunden; 32 wäre ein
        # Befehlsbenutzungsfehler und damit keine gültige Messung.
        self.assertTrue(0 < rc < 32,
                        f"ungewöhnlicher pylint-Exitcode {rc}; "
                        f"stderr={self.lauf.stderr[:200]!r}")
        self.assertTrue(self.befunde,
                        "ergebnisloser pylint-Lauf (0 Befundzeilen) — Messung unbrauchbar")
        for pfad in ("fritz-reconnect.py", "vibe-web.py"):
            treffer = [
                b for b in self.befunde
                if b.get("path") == pfad
                and b.get("symbol") == "invalid-name"
                and str(b.get("message", "")).startswith("Module name")
            ]
            self.assertTrue(
                treffer,
                f"Einstiegsdatei {pfad} wurde nicht erwartbar gelintet "
                "(kein Modulnamen-invalid-name-Befund); Auswertung unzuverlässig,"
            )

    def test_ak1_keine_befunde_ausser_ausnahmen(self):
        """AK1/Haupttest: kein pylint-Befund außerhalb der Ausnahmeliste.

        Vorbedingung: Lauf in setUpClass gesichert (siehe Test oben).
        Aktion: alle Befunde gegen AUSNAHMEN_SYMBOLE und den eingeschränkten
        invalid-name-Filter (nur Modulnamen der Bindestrich-Einstiegsdateien)
        prüfen.
        Erwartet: Liste der Verletzungen ist leer.
        Fehlerfall: AssertionError mit Kategoriauszählung und bis zu 10
        Beispielen (pfad:zeile [symbol]: meldung).
        """
        verletzte = []
        for befund in self.befunde:
            symbol = befund.get("symbol", "")
            pfad = befund.get("path", "")
            meldung = str(befund.get("message", ""))
            if symbol in AUSNAHMEN_SYMBOLE:
                continue
            if (symbol == "invalid-name" and meldung.startswith("Module name")
                    and pfad in BINDESTRICH_MODUL):
                continue
            verletzte.append((symbol, pfad, befund.get("line"), meldung))
        if verletzte:
            kategorien = {}
            for symbol, _pfad, _zeile, _meldung in verletzte:
                kategorien[symbol] = kategorien.get(symbol, 0) + 1
            zeilen = [f"{pfad}:{zeile} [{symbol}]: {meldung}"
                      for symbol, pfad, zeile, meldung in verletzte[:10]]
            beispiele = "\n".join(zeilen)
            self.fail(
                f"AK1 verletzt: {len(verletzte)} pylint-Befunde außerhalb der "
                f"Ausnahmeliste. Kategorien: {kategorien}. Beispiele:\n{beispiele}"
            )
