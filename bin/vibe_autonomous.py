#!/usr/bin/env python3
"""Autonomer Modus für Agentenläufe (F16).

Ist der autonome Modus für ein Projekt eingeschaltet, darf der Agent ohne
Antwort des Nutzers selbst entscheiden. Die Einstellung gehört dem Nutzer:
Sie liegt als ``autonomous.json`` im Laufzeitordner und damit **außerhalb**
des Ordners ``questions``, den ein sandboxed Agent beschreiben darf. Ein
Agent kann den Modus deshalb weder für sich einschalten noch die Entscheidung
des Nutzers überschreiben.

Aufbau der Datei::

    {"version": 1, "projects": {"projektname": {"enabled": true, "changed": "..."}}}

Ein leerer Projektname steht für die globale Voreinstellung; er gilt nur für
Rückfragen ohne Projektzuordnung. Fehlt die Datei oder ist sie unlesbar, ist
der Modus aus. Ein Lesefehler darf nie dazu führen, dass ein Agent ohne
ausdrückliche Freigabe allein entscheidet.
"""
import json
import os
import time

import vibe_storage

STATE_NAME = "autonomous.json"
MAX_PROJECT = 120


def _clean_project(project):
    """Projektname prüfen; der leere Name ist die globale Voreinstellung."""
    if not isinstance(project, str):
        raise ValueError("Projekt muss Text sein")
    if any(char in project for char in ("\x00", "\n", "\r")):
        raise ValueError("Projekt enthält ein Steuerzeichen")
    text = project.strip()
    if len(text) > MAX_PROJECT:
        raise ValueError("Projekt ist länger als " + str(MAX_PROJECT) + " Zeichen")
    return text


def _runtime(runtime):
    if runtime is None or not os.fspath(runtime):
        raise ValueError("Laufzeitordner fehlt")
    return os.fspath(runtime)


def state_path(runtime):
    """Pfad der Zustandsdatei im Laufzeitordner."""
    return os.path.join(_runtime(runtime), STATE_NAME)


def _stamp(now=None):
    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now)
    )


def _empty():
    return {"version": 1, "projects": {}}


def _parse(text):
    """Liest den Zustand streng; unbekannte Einträge werden ignoriert."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("Autonomer Modus ist nicht lesbar") from error
    if not isinstance(data, dict):
        raise ValueError("Autonomer Modus ist nicht lesbar")
    raw = data.get("projects", {})
    if not isinstance(raw, dict):
        raise ValueError("Autonomer Modus ist nicht lesbar")
    projects = {}
    for name, entry in raw.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        if entry.get("enabled") is True:
            projects[name] = {
                "enabled": True,
                "changed": str(entry.get("changed") or ""),
            }
    return {"version": 1, "projects": projects}


def load(runtime):
    """Liest den gespeicherten Zustand; eine fehlende Datei heißt „aus“."""
    try:
        with open(state_path(runtime), encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return _empty()
    except OSError as error:
        raise ValueError("Autonomer Modus ist nicht lesbar") from error
    return _parse(text)


def is_enabled(runtime, project=""):
    """Ist der autonome Modus für das Projekt eingeschaltet?

    Ein unlesbarer Zustand gilt bewusst als „aus“: Ohne ausdrückliche,
    lesbare Freigabe entscheidet kein Agent allein.
    """
    try:
        state = load(runtime)
        name = _clean_project(project)
    except ValueError:
        return False
    return bool(state["projects"].get(name))


def status(runtime, project=""):
    """Zustand eines Projekts mit Zeitpunkt der letzten Änderung."""
    state = load(runtime)
    name = _clean_project(project)
    entry = state["projects"].get(name)
    return {
        "project": name,
        "enabled": bool(entry),
        "changed": entry.get("changed", "") if entry else "",
    }


def set_enabled(runtime, project, enabled, now=None):
    """Schaltet den Modus für ein Projekt ein oder aus.

    Die Datei wird unter derselben Prüfsummenkontrolle wie die übrige
    Konfiguration geschrieben; ein gleichzeitiger Schreibvorgang wird erneut
    versucht statt still überschrieben.
    """
    project = _clean_project(project)
    path = state_path(runtime)
    for _attempt in range(8):
        snapshot = vibe_storage.read_snapshot(path)
        if snapshot.exists:
            state = _parse(snapshot.text)
        else:
            state = _empty()
        projects = dict(state["projects"])
        changed = _stamp(now)
        if enabled:
            projects[project] = {"enabled": True, "changed": changed}
        else:
            projects.pop(project, None)
        payload = json.dumps(
            {"version": 1, "projects": projects}, ensure_ascii=False, indent=1
        ) + "\n"
        try:
            vibe_storage.write_text(
                path, payload, expected=snapshot, mode=0o600
            )
        except vibe_storage.ConcurrentChangeError:
            continue
        return {"project": project, "enabled": bool(enabled), "changed": changed}
    raise RuntimeError("Autonomer Modus konnte nicht gespeichert werden")
