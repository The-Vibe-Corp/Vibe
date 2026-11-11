#!/usr/bin/env python3
"""Schrankeneinstellungen für den Paket-Läufer (AP10).

Die Schranken begrenzen, wie weit der Läufer pro Arbeitspaket und Durchgang
arbeitet. Sie sind global in ``<Zustand>/gates.json`` abgelegt (Zustand ist
``VIBE_STATE``, sonst der Installationsordner) und können je Projekt optional
abweichend gesetzt werden: ``.vibe/project.env`` mit ``REPAIR_ROUNDS``,
``ASSIST_ROUNDS``, ``MAX_RETRIES``, ``MAX_PACKAGES`` und ``GATE_OVERRIDE``.

Schranken und Voreinstellungen:

* ``repair_rounds`` — 2, Reparaturrunden je Arbeitspaket.
* ``assist_rounds`` — 10, Rückfrage-Assistenzrunden (Preflight).
* ``retries`` — 2, Wiederholungen je Arbeitspaket.
* ``packages`` — 80, Durchgangslimit.
* ``override`` — ``ask``; erlaubt sind ``ask`` (bei blockiertem Paket
  nachfragen) und ``off`` (bisheriges Verhalten: sofort blockieren).

Wirksame Priorität: Projekt > global > Voreinstellung; für ``packages``
behält die Umgebungsvariable ``VIBE_MAX_PACKAGES`` den höchsten Vorrang
(bestehendes Verhalten des Läufers). Defekte Werte (nicht-ganzzahlig,
unbekannter override-Wert, defekte Datei) werden als Probleme gemeldet und
konservativ als Voreinstellung interpretiert; es wird nie still ein anderer
Wert angenommen.

Das Modul liest und schreibt nur lokale Dateien: keine Modelle, keine
Netzverbindung. Schreibzugriffe laufen atomar über ``vibe_storage``.

Aufruf:

  vibe_gates.py [status|json] [--state ORDNER] [--project PROJEKT]

``json`` gibt die wirksamen Schranken als JSON auf der Standardausgabe aus
(das nutzt ``bin/vibe-run.sh``); Meldungen zu defekten Werten gehen auf die
Standardfehlerausgabe.
"""
import argparse
import json
import os
import re
import sys

# Das Modul liegt neben ``vibe_storage``; beim direkten Laden (z. B. in Tests
# über SourceFileLoader) muss dieser Ordner zunächst im Modulpfad stehen.
_BIN_DIR = os.path.dirname(os.path.realpath(__file__))
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

import vibe_storage

FILE_NAME = "gates.json"
DEFAULTS = {
    "repair_rounds": 2,
    "assist_rounds": 10,
    "retries": 2,
    "packages": 80,
    "override": "ask",
}
NUMERIC_GATES = ("repair_rounds", "assist_rounds", "retries", "packages")
OVERRIDE_ASK = "ask"
OVERRIDE_OFF = "off"
OVERRIDES = (OVERRIDE_ASK, OVERRIDE_OFF)
# Projektschlüssel in .vibe/project.env, je Schranke.
PROJECT_ENV_KEYS = {
    "repair_rounds": "REPAIR_ROUNDS",
    "assist_rounds": "ASSIST_ROUNDS",
    "retries": "MAX_RETRIES",
    "packages": "MAX_PACKAGES",
    "override": "GATE_OVERRIDE",
}
ORIGIN_STANDARD = "Standard"
ORIGIN_GLOBAL = "global"
ORIGIN_PROJECT = "projekt"
ORIGIN_ENV = "Umgebung"
ENV_PACKAGES = "VIBE_MAX_PACKAGES"


def state_dir(value=None):
    """Zustandsordner: Argument, ``VIBE_STATE``, ``VIBE_INSTALL``, sonst ``.``."""
    return os.path.abspath(
        str(value or os.environ.get("VIBE_STATE")
            or os.environ.get("VIBE_INSTALL") or ".")
    )


def path(state=None):
    """Pfad der globalen Schrankeneinstellungsdatei."""
    return os.path.join(state_dir(state), FILE_NAME)


def load(state=None):
    """Inhalt der globalen Datei: ``(daten, problem)``.

    ``problem`` ist leer, wenn die Datei gültig oder nicht vorhanden ist.
    Bei einer defekten Datei werden keine Werte geliefert; die Aufrufer
    interpretieren defekte Schranken konservativ als Voreinstellung.
    """
    target = path(state)
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError) as error:
        return {}, "Schrankeneinstellung %s ist ungültig: %s" % (target, error)
    if not isinstance(data, dict):
        return {}, (
            "Schrankeneinstellung %s ist ungültig: erwartet wird ein "
            "JSON-Objekt." % target
        )
    return data, ""


def read_env(path):
    """Liest ``SCHLUESSEL=WERT``-Zeilen aus einer Env-Datei.

    Wie in ``vibe_packages.read_env``: Anführungszeichen werden entfernt,
    Kommentare und leere Zeilen übersprungen. Eine nicht lesbare Datei ist
    kein Absturz, sondern ergibt ein leeres Ergebnis.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return {}
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_numeric(key, raw):
    """Wert einer Zählschranke: ``(wert, problem)``; ``None`` bei Defekt."""
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        return None, (
            "Schranke '%s' erwartet eine positive Zahl, gefunden %r."
            % (key, raw)
        )
    text = str(raw).strip()
    if not re.fullmatch(r"[0-9]+", text):
        return None, (
            "Schranke '%s' erwartet eine positive Zahl, gefunden %r."
            % (key, raw)
        )
    value = int(text)
    if value < 1:
        return None, (
            "Schranke '%s' erwartet eine Zahl ab 1, gefunden %r."
            % (key, raw)
        )
    return value, None


def parse_override(key, raw):
    """Wert der override-Schranke: ``(wert, problem)``; ``None`` bei Defekt."""
    if not isinstance(raw, str):
        return None, (
            "Schranke '%s' erwartet 'ask' oder 'off', gefunden %r."
            % (key, raw)
        )
    text = raw.strip().lower()
    if text not in OVERRIDES:
        return None, (
            "Schranke '%s' erwartet 'ask' oder 'off', gefunden %r."
            % (key, raw)
        )
    return text, None


def _parse_gate(key, raw):
    """Delegiert an den passenden Parser der Schranke."""
    if key in NUMERIC_GATES:
        return parse_numeric(key, raw)
    return parse_override(key, raw)


def validate(key, value):
    """Prüft eine Schranke und liefert ihren normierten Wert.

    Zählschranken werden zu ``int`` normiert, ``override`` zu ``"ask"`` oder
    ``"off"``. Bei unbekannter Schranke oder ungültigem Wert wird
    ``ValueError`` geworfen, ohne etwas zu schreiben.
    """
    if key not in DEFAULTS:
        raise ValueError(
            "Unbekannte Schranke: %r (erlaubt: %s)"
            % (key, ", ".join(DEFAULTS))
        )
    parsed, problem = _parse_gate(key, value)
    if problem:
        raise ValueError(problem)
    return parsed


def effective(state=None, project=None):
    """Wirksame Schranken samt Herkunft und Problemliste.

    Rückgabeform (dokumentiert und stabil):

    ``{"gates": {schranke: {"value": wert, "origin": herkunft}},
    "problems": [meldung, ...]}``

    ``origin`` ist ``"Standard"``, ``"global"``, ``"projekt"`` oder
    ``"Umgebung"`` (nur ``packages`` über ``VIBE_MAX_PACKAGES``). Der
    Zustandsordner ist ``state``; der Projektordner ``project`` (optional).
    """
    problems = []
    data, problem = load(state)
    if problem:
        problems.append(problem)
        data = {}
    project_values = {}
    if project:
        project_values = read_env(
            os.path.join(str(project), ".vibe", "project.env")
        )
    values, origins = {}, {}
    for key, default in DEFAULTS.items():
        value, origin = default, ORIGIN_STANDARD
        if key in data:
            parsed, defect = _parse_gate(key, data[key])
            if defect:
                problems.append("Globale Schrankeneinstellung: " + defect)
            else:
                value, origin = parsed, ORIGIN_GLOBAL
        project_raw = project_values.get(PROJECT_ENV_KEYS[key])
        if project_raw is not None and str(project_raw).strip() != "":
            parsed, defect = _parse_gate(key, project_raw)
            if defect:
                problems.append(
                    "Projekteinstellung (%s): %s"
                    % (os.path.join(str(project), ".vibe", "project.env"),
                       defect)
                )
            else:
                value, origin = parsed, ORIGIN_PROJECT
        values[key], origins[key] = value, origin
    env_raw = os.environ.get(ENV_PACKAGES)
    if env_raw is not None and env_raw.strip() != "":
        parsed, defect = parse_numeric("packages", env_raw)
        if defect:
            problems.append(ENV_PACKAGES + ": " + defect)
        else:
            values["packages"], origins["packages"] = parsed, ORIGIN_ENV
    return {
        "gates": {
            key: {"value": values[key], "origin": origins[key]}
            for key in DEFAULTS
        },
        "problems": problems,
    }


def save(state, key, value):
    """Schreibt eine globale Schranke atomar und liefert den normierten Wert.

    ``value`` darf ``int`` oder ``str`` sein und wird zuerst über
    :func:`validate` geprüft; ein Fehler bricht ab, bevor die Datei gelesen
    oder geschrieben wird. Vorhandene andere Einträge bleiben erhalten; eine
    defekte Datei wird durch die neue Einstellung ersetzt.
    """
    parsed = validate(key, value)
    target = path(state)
    data, _problem = load(state)
    data[key] = parsed
    os.makedirs(os.path.dirname(target), exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    vibe_storage.write_text(target, text)
    return parsed


def describe(state=None, project=None):
    """Lesbare Statuszeilen für ``vibe gates status`` (ohne Problemmeldungen)."""
    result = effective(state, project)
    return [
        "  %s=%s (%s)" % (key, entry["value"], entry["origin"])
        for key, entry in result["gates"].items()
    ]


def main(argv=None):
    """Kommandozeile: ``status`` (Tabelle) und ``json`` (Maschinenausgabe)."""
    parser = argparse.ArgumentParser(
        prog="vibe_gates.py",
        description="Schrankeneinstellungen für Agentenläufe (AP10)",
    )
    parser.add_argument("action", nargs="?", default="status",
                        choices=("status", "json"))
    parser.add_argument("--state", default=None)
    parser.add_argument("--project", default=None)
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    result = effective(args.state, args.project)
    if args.action == "json":
        for message in result["problems"]:
            print(message, file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    for message in result["problems"]:
        print(message)
    print("Wirksame Schranken:")
    for line in describe(args.state, args.project):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
