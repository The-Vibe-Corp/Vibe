#!/usr/bin/env python3
"""Globales Limitverhalten für Agentenläufe (V-027).

Quota- und Anmeldefehler halten einen Lauf standardmäßig sofort an
(``stop``). Auf ausdrückliche Entscheidung kann das Verhalten global auf
``continue`` gestellt werden: Der Fehler wird dann wie ein wiederholbarer
Fehler im Rahmen der vorhandenen Wiederholungslimits behandelt.

Eigenschaften:

* **Global** — genau eine Einstellung für alle Projekte, keine
  Projektüberschreibung.
* **Ausdrücklich** — ohne Datei und bei defekter Datei gilt ``stop``. Eine
  ungültige Einstellung wird gemeldet und nie still als ``continue``
  ausgelegt.
* **Kein Netzwerk, keine Modelle** — das Modul liest und schreibt nur eine
  JSON-Datei ``<Zustand>/limits.json``.

Aufruf:

  vibe_limits.py status|stop|continue|mode [--state ORDNER]

``mode`` gibt ausschließlich den wirksamen Wert auf der Standardausgabe aus;
das nutzt ``bin/vibe-run.sh``. Meldungen zu einer defekten Datei gehen in
diesem Fall auf die Standardfehlerausgabe.
"""
import argparse
import json
import os
import sys

import vibe_storage

FILE_NAME = "limits.json"
MODE_STOP = "stop"
MODE_CONTINUE = "continue"
MODES = (MODE_STOP, MODE_CONTINUE)
DEFAULT_MODE = MODE_STOP


def state_dir(value=None):
    """Zustandsordner: Argument, ``VIBE_STATE``, ``VIBE_INSTALL``, sonst ``.``."""
    return os.path.abspath(
        str(value or os.environ.get("VIBE_STATE")
            or os.environ.get("VIBE_INSTALL") or ".")
    )


def path(state=None):
    """Pfad der globalen Einstellungsdatei."""
    return os.path.join(state_dir(state), FILE_NAME)


def load(state=None):
    """Wirksamer Wert und Meldung: ``(mode, problem)``.

    ``problem`` ist leer, wenn die Einstellung gültig oder nicht vorhanden
    ist. Bei einer defekten Datei gilt konservativ ``stop``.
    """
    target = path(state)
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return DEFAULT_MODE, ""
    except (OSError, ValueError) as error:
        return DEFAULT_MODE, f"Limit-Einstellung {target} ist ungültig: {error}"
    mode = data.get("mode") if isinstance(data, dict) else None
    if mode not in MODES:
        return DEFAULT_MODE, (
            f"Limit-Einstellung {target} ist ungültig: erwartet wird "
            + " oder ".join(MODES) + f", gefunden {mode!r}."
        )
    return mode, ""


def save(state, mode):
    """Schreibt den Wert atomar und gibt ihn zurück."""
    if mode not in MODES:
        raise ValueError(f"Unbekanntes Limitverhalten: {mode!r}")
    target = path(state)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    text = json.dumps({"mode": mode}, indent=1, ensure_ascii=False) + "\n"
    vibe_storage.write_text(target, text)
    return mode


def describe(state=None):
    """Statuszeile für ``vibe limits status`` (ohne Fehlerausgabe)."""
    mode, _problem = load(state)
    if mode == MODE_CONTINUE:
        return ("Limitverhalten: continue — Quota- und Anmeldefehler werden im "
                "Rahmen der Wiederholungslimits erneut versucht.")
    return ("Limitverhalten: stop — Quota- und Anmeldefehler halten den Lauf "
            "sofort an.")


def main(argv=None):
    """Kommandozeile: ``status``, ``stop``, ``continue`` und ``mode``."""
    parser = argparse.ArgumentParser(
        prog="vibe_limits.py",
        description="Globales Limitverhalten für Agentenläufe (V-027)",
    )
    parser.add_argument("action", nargs="?", default=MODE_STOP,
                        choices=("status", "stop", "continue", "mode"))
    parser.add_argument("--state", default=None)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.action == "mode":
        mode, problem = load(args.state)
        if problem:
            print(problem, file=sys.stderr)
        print(mode)
        return 0
    if args.action in MODES:
        try:
            save(args.state, args.action)
        except OSError as error:
            print(f"Limitverhalten nicht gespeichert: {error}", file=sys.stderr)
            return 1
    _mode, problem = load(args.state)
    if problem:
        print(problem, file=sys.stderr)
    print(describe(args.state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
