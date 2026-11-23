#!/usr/bin/env python3
"""Paralleler Testläufer für die vibe-Suite (F31).

Zweck: Die Unit-Suite (>1800 Tests) läuft als ``unittest discover`` über
17 Minuten, obwohl nur ein Viertel davon CPU ist — der Rest ist Warten auf
Subprozesse und Ports. Der Läufer führt jedes Testmodul in einem eigenen
Prozess aus, mehrere davon gleichzeitig, und fasst die Ergebnisse zu einem
deterministischen Bericht zusammen. Nur Python-Standardbibliothek.

Aufrufbeispiele:
    python3 scripts/run-tests-parallel.py --dir tests/unit
    python3 scripts/run-tests-parallel.py --dir tests/unit --dir tests/browser
    python3 scripts/run-tests-parallel.py --dir tests/unit --jobs 4
    python3 scripts/run-tests-parallel.py --dir tests/unit --timeout 600

Berichtsformat (Vertrag von verify_engine.py und der Oberfläche):
* Je Modul ein Block mit Kopfzeile ``--- <modul> ---``; die Modulausgabe
  wird unverändert durchgereicht, insbesondere alle ``Ran N tests``-Zeilen
  bleiben im Gesamtausdruck erhalten.
* Abschlusszeile: ``Gesamt: <n> Tests, <b>/<m> Module bestanden,
  <f> fehlgeschlagen`` (n = Summe aller Ran-Zahlen; ein Modul ohne
  Ran-Zeile zählt 0). Ein Modul mit Importfehler erzeugt nur den
  unittest-Platzhalter ``_FailedTest`` mit ``Ran 1 test``; diese eine
  nicht ausgeführte Prüfung zählt nicht zur Summe.
* Exit 0 nur, wenn alle Module bestanden. Ein fehlgeschlagenes Modul oder
  ein Importfehler ergibt Exit 1; die fehlgeschlagenen Module werden
  namentlich genannt und ihre Ausgabe bleibt sichtbar. Kein stiller
  Testverlust: Ein Modul ohne Prozessende oder ohne ``Ran``-Zeile zählt
  als fehlgeschlagen.

Zeitlimit: ``--timeout`` (Sekunden, Standard 900, 0 = kein Limit) begrenzt
jeden Modulprozess. Ein überschrittenes Limit beendet den Prozess, das Modul
gilt als fehlgeschlagen (Exit 1, namentlich genannt), und sein Block nennt
den Timeout mit der bis dahin gesammelten Ausgabe — keine stille Auslassung.
Die Modulausgabe wird als UTF-8 mit Ersatzzeichen gelesen (``encoding``,
``errors``), damit fremd kodierte Zeichen den Lauf nicht abbrechen.

Grenzen: Browser-Tests starten echte Browser und belegen Ports; dafür ist
``--jobs 2`` oder niedriger zu wählen. Die Berichtsblöcke erscheinen erst
nach Ende aller Läufe (gesammelte Ausgabe, damit die Blöcke nicht
ineinanderlaufen und sortiert bleiben).
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from functools import partial
from pathlib import Path

SUMMARY = "Gesamt: {tests} Tests, {passed}/{modules} Module bestanden, {failed} fehlgeschlagen"
RAN_RE = re.compile(r"Ran (\d+) tests?")
# unittest ersetzt ein Modul mit Importfehler durch eine einzelne
# _FailedTest; deren "Ran 1 test" ist kein ausgeführtes Test.
LOADER_FAILURE_RE = re.compile(
    r"unittest\.loader\._FailedTest|Failed to import test module"
)
# Erste Fehlerzeile des Tracebacks: Fehlerklasse + Meldung. Sie liefert dem
# Bericht (AP7-Korbat, ``--report``) ``error_class``/``error_message``.
EXCEPTION_RE = re.compile(
    r"^(?P<class>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Failure)):\s*(?P<message>.*)$",
    re.MULTILINE,
)
EXIT_USAGE = 2
EXIT_FAILURE = 1


def discover_modules(directories):
    """Testmodule (test*.py) je Verzeichnis rekursiv als dotted path zum cwd.

    Verschachtelte Module werden erfasst (z. B. ``tests.verschachtelt.
    test_nested``); doppelte Treffer aus überlappenden ``--dir``-Angaben
    zählen nur einmal.
    """
    modules = []
    seen = set()
    for directory in directories:
        base = Path(directory)
        if not base.is_dir():
            print(f"FEHLT: Verzeichnis fehlt: {directory}", file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
        for path in sorted(base.rglob("test*.py")):
            if not path.is_file():
                continue
            rel = os.path.relpath(path, os.getcwd())
            module = str(Path(rel).with_suffix("")).replace(os.sep, ".")
            if module not in seen:
                seen.add(module)
                modules.append(module)
    return modules


def run_module(module, timeout=None):
    """Führt ``python3 -m unittest <module>`` aus und sammelt die Ausgabe.

    ``timeout`` begrenzt den Modulprozess in Sekunden; ``None`` bedeutet kein
    Limit. Bei Überschreiten wird der Prozess beendet, das Modul zählt als
    fehlgeschlagen, und die bisherige Ausgabe bleibt im Bericht sichtbar.
    """
    timed_out = False
    returncode = None
    output = ""
    try:
        process = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=os.getcwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        output = process.stdout
        returncode = process.returncode
    except subprocess.TimeoutExpired as error:
        # POSIX liefert die bisher gesammelte Ausgabe als Bytes im Fehler;
        # sie bleibt sichtbar, damit ein Timeout niemals still ausfällt.
        timed_out = True
        partial_output = error.stdout
        if isinstance(partial_output, bytes):
            partial_output = partial_output.decode("utf-8", errors="replace")
        output = (partial_output or "") + (
            f"\nTIMEOUT: Zeitlimit von {timeout} s überschritten; "
            "Prozess beendet, Modul zählt als fehlgeschlagen.\n"
        )
    ran = RAN_RE.findall(output)
    tests = sum(int(count) for count in ran)
    loader_failure = LOADER_FAILURE_RE.search(output) is not None
    if loader_failure:
        # Der Platzhalter _FailedTest wird als "Ran 1 test" gezählt, ohne
        # dass ein echtes Test gelaufen ist; die Summe zählt reale Tests.
        tests = 0
    # Kein stiller Testverlust: Bestanden zählt nur mit Prozessende 0 und
    # nachweislich ausgeführten Tests (Ran-Zeile). Ein Modul ohne Ran-Zeile
    # (Absturz, Importfehler) ist fehlgeschlagen, auch wenn es 0 meldet;
    # unittest meldet für leere Module selbst "Ran 0 tests". Ein
    # überschrittenes Zeitlimit ist immer fehlgeschlagen.
    passed = (
        not timed_out
        and returncode == 0
        and not loader_failure
        and RAN_RE.search(output) is not None
    )
    return {
        "module": module,
        "output": output,
        "returncode": returncode,
        "tests": tests,
        "passed": passed,
    }


def error_details(output):
    """Fehlerklasse und Meldung der ersten Traceback-Ausnahme, sonst ``(None, None)``."""
    match = EXCEPTION_RE.search(output)
    if match:
        return match.group("class"), match.group("message").strip()
    return None, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Testmodule parallel ausführen (F31); Bericht wie unittest."
    )
    parser.add_argument(
        "--dir", action="append", required=True, metavar="VERZEICHNIS",
        help="Verzeichnis mit Testmodulen (mehrfach angebbar)",
    )
    parser.add_argument(
        "--jobs", type=int, default=max(os.cpu_count() or 1, 2), metavar="N",
        help="gleichzeitige Modulprozesse (Standard: Anzahl Kerne, mindestens 2)",
    )
    parser.add_argument(
        "--timeout", type=int, default=900, metavar="SEK",
        help="Zeitlimit je Modul in Sekunden (Standard: 900; 0 = kein Limit)",
    )
    parser.add_argument(
        "--report", metavar="PFAD",
        help="JSON-Bericht nach Abschluss schreiben (AP7-Korbat); ohne die "
        "Option wird nichts geschrieben",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs benötigt mindestens 1.")
    if args.timeout < 0:
        parser.error("--timeout erfordert Sekunden >= 0 (0 = kein Limit).")

    modules = discover_modules(args.dir)
    if not modules:
        print("FEHLT: Keine Testmodule (test*.py) gefunden.")
        return EXIT_FAILURE

    limit = args.timeout or None
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(partial(run_module, timeout=limit), modules))

    results.sort(key=lambda result: result["module"])
    for result in results:
        print(f"--- {result['module']} ---")
        print(result["output"], end="" if result["output"].endswith("\n") else "\n")

    total = sum(result["tests"] for result in results)
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    if args.report:
        write_report(args.report, results, total)
    print(SUMMARY.format(tests=total, passed=passed, modules=len(results), failed=failed))
    if failed:
        names = ", ".join(result["module"] for result in results if not result["passed"])
        print(f"Fehlgeschlagene Module: {names}")
        return EXIT_FAILURE
    return 0


def write_report(path, results, total):
    """Schreibt den strukturierten Bericht (``--report``), ohne die Textausgabe
    oder die Exitcodes zu verändern."""
    modules = []
    for result in results:
        error_class, error_message = (None, None)
        if not result["passed"]:
            error_class, error_message = error_details(result["output"])
        modules.append(
            {
                "module": result["module"],
                "tests": result["tests"],
                "passed": result["passed"],
                "returncode": result["returncode"],
                "error_class": error_class,
                "error_message": error_message,
            }
        )
    report = {"modules": modules, "total_tests": total}
    Path(path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
