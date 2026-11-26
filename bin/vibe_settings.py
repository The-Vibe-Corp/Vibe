#!/usr/bin/env python3
"""Persistente Nutzereinstellungen der Anwendung (GH-117).

``<state>/settings.json`` hält die persönlichen Einstellungen, die nicht an
ein Projekt gebunden sind:

* ``theme`` — Hell/Dunkel/Automatisch
* ``accent`` — Akzentfarbe
* ``features`` — ein-/ausgeschaltete Funktionsmerkmale
* ``favorite_projects`` — bevorzugte Projekte
* ``favorite_agents`` — bevorzugte Agenten je Geltungsbereich

Die Datei ist versionsverträglich: Ein fehlender oder unbekannter Wert wird
nie zum Absturz, sondern fällt je Schlüssel auf einen sicheren Standard
zurück. Beim Schreiben werden unbekannte Schlüssel und eine höhere Version
erhalten, damit eine neuere Anwendung ihre Daten nicht verliert und eine
ältere sie nicht unbemerkt herabstuft.

Dieses Modul liest und schreibt ausschließlich ``settings.json`` im
übergebenen Zustandsordner; beim Import wird keine Datei berührt.
"""
import json
import os

try:
    import vibe_storage
except ImportError:
    # Tests laden dieses Modul per SourceFileLoader direkt aus bin/, ohne
    # bin/ im sys.path. Dann wird das Schwestermodul über seinen Pfad geladen
    # und unter dem Namen registriert, den der normale Import ebenfalls nutzt.
    import importlib.machinery
    import importlib.util
    import sys

    _loader = importlib.machinery.SourceFileLoader(
        "vibe_storage",
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "vibe_storage.py"),
    )
    _spec = importlib.util.spec_from_loader(_loader.name, _loader)
    vibe_storage = importlib.util.module_from_spec(_spec)
    sys.modules["vibe_storage"] = vibe_storage
    _loader.exec_module(vibe_storage)

FILENAME = "settings.json"
SCHEMA_VERSION = 1

THEMES = ("light", "dark", "auto")
ACCENTS = (
    "blue", "teal", "cyan", "green", "lime", "yellow", "amber", "orange",
    "red", "pink", "violet", "indigo",
)
FEATURE_IDS = (
    "github", "agentsfile", "writeaccess", "models", "profiles", "mcp",
    "harness", "gates", "sandbox", "priority",
)

DEFAULTS = {
    "theme": "light",
    "accent": "blue",
    "features": {},
    "favorite_projects": [],
    "favorite_agents": [],
}

# Grenzen für die beiden Listen. Längere Eingaben werden nach dem Entdoppeln
# auf die ersten Einträge gekürzt; leere oder zu lange Texte sind ungültig.
MAX_TEXT = 200
MAX_LIST = 200
# Begrenzte Wiederholungen bei einem Schreibkonflikt: Jeder Versuch liest den
# aktuellen Stand neu und wendet denselben Patch erneut an, damit parallele
# Teil-Updates einander nicht still überschreiben.
MAX_WRITE_ATTEMPTS = 8


def path(state_dir):
    """Vollständiger Pfad der Einstellungsdatei im Zustandsordner."""
    return os.path.join(state_dir, FILENAME)


def _parse_document(text):
    """JSON-Objekt aus dem Dateitext; alles andere gilt als leer."""
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError, RecursionError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _read_document(state_dir):
    """Liest die Datei als JSON-Objekt; defekte Inhalte gelten als leer.

    Liefert ``(daten, vorhanden)``. ``vorhanden`` beschreibt nur, ob die Datei
    existiert — auch eine defekte Datei wird nicht stillschweigend gelöscht.
    """
    target = path(state_dir)
    exists = os.path.exists(target)
    try:
        with open(target, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return {}, exists
    return _parse_document(text), exists


def _file_version(data):
    """Version aus der Datei; fehlend oder unbrauchbar bedeutet Schema 1.

    Eine höhere Version bleibt erhalten (keine Herabstufung), eine Version
    unter 1 wird als aktuelle Version behandelt.
    """
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        return SCHEMA_VERSION
    if version < 1:
        return SCHEMA_VERSION
    return version


def _raw_settings(data):
    """Rohes Einstellungsobjekt; alles außer einem Objekt gilt als leer."""
    settings = data.get("settings")
    return settings if isinstance(settings, dict) else {}


def _valid_text(value):
    return isinstance(value, str) and 0 < len(value) <= MAX_TEXT


def _normalize_projects(value):
    """Liste nichtleerer Texte, entdoppelt und gekürzt.

    Liefert ``(liste, verworfen)``; ``liste`` ist ``None``, wenn der Wert kein
    Array ist. Ungültige Einträge werden einzeln verworfen, nicht die Liste.
    """
    if not isinstance(value, list):
        return None, False
    result = []
    seen = set()
    dropped = False
    for item in value:
        if not _valid_text(item):
            dropped = True
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= MAX_LIST:
            break
    return result, dropped


def _normalize_agents(value):
    """Liste von ``{"scope", "name"}``, entdoppelt und gekürzt.

    Liefert ``(liste, verworfen)``; ``liste`` ist ``None``, wenn der Wert kein
    Array ist. Ungültige Einträge werden einzeln verworfen, nicht die Liste.
    """
    if not isinstance(value, list):
        return None, False
    result = []
    seen = set()
    dropped = False
    for item in value:
        if not isinstance(item, dict):
            dropped = True
            continue
        scope = item.get("scope")
        name = item.get("name")
        if not _valid_text(scope) or not _valid_text(name):
            dropped = True
            continue
        key = (scope, name)
        if key in seen:
            continue
        seen.add(key)
        result.append({"scope": scope, "name": name})
        if len(result) >= MAX_LIST:
            break
    return result, dropped


def _effective_features(raw):
    """Alle bekannten Merkmale als Bool; unbekannte und falsche Typen: False."""
    source = raw if isinstance(raw, dict) else {}
    return {
        feature_id: (source.get(feature_id)
                     if isinstance(source.get(feature_id), bool) else False)
        for feature_id in FEATURE_IDS
    }


def _effective(raw):
    """Effektive Einstellungen mit allen fünf Schlüsseln, je Wert geprüft."""
    return {
        "theme": (raw.get("theme") if raw.get("theme") in THEMES
                  else DEFAULTS["theme"]),
        "accent": (raw.get("accent") if raw.get("accent") in ACCENTS
                   else DEFAULTS["accent"]),
        "features": _effective_features(raw.get("features")),
        "favorite_projects": (_normalize_projects(raw.get("favorite_projects"))[0]
                              or []),
        "favorite_agents": (_normalize_agents(raw.get("favorite_agents"))[0]
                            or []),
    }


def load(state_dir):
    """Effektive Einstellungen; wirft bei fehlender oder defekter Datei nie."""
    return view(state_dir)["settings"]


def view(state_dir):
    """Ansicht für API und HTML-Meta: Version, Speicherstatus und Werte."""
    data, exists = _read_document(state_dir)
    return {
        "ok": True,
        "version": _file_version(data),
        "stored": exists,
        "settings": _effective(_raw_settings(data)),
    }


def _merge_features(raw, value):
    """Mischt ein Merkmals-Patch; liefert ``(merged, angewandt, ungültig)``.

    Unbekannte Merkmals-IDs mit booleschem Wert bleiben erhalten (eine neuere
    Anwendung könnte sie kennen); die Ansicht ignoriert sie trotzdem.
    """
    if not isinstance(value, dict):
        return None, 0, True
    current = raw.get("features")
    merged = dict(current) if isinstance(current, dict) else {}
    applied = 0
    invalid = False
    for feature_id, flag in value.items():
        if isinstance(feature_id, str) and isinstance(flag, bool):
            merged[feature_id] = flag
            applied += 1
        else:
            invalid = True
    if applied == 0:
        return None, 0, True
    return merged, applied, invalid


def _merge_patch(data, patch):
    """Wendet einen Patch auf einen Dokumentstand an (ohne zu schreiben).

    Liefert ``(version, rohe_einstellungen, ignoriert, geändert)``. Die
    Berechnung ist rein und wird bei jedem Konflikt-Retry auf den frisch
    gelesenen Stand erneut ausgeführt.
    """
    version = _file_version(data)
    raw = dict(_raw_settings(data))
    ignored = []
    changed = False

    for key, value in patch.items():
        if key == "theme":
            if isinstance(value, str) and value in THEMES:
                raw["theme"] = value
                changed = True
            else:
                ignored.append(key)
        elif key == "accent":
            if isinstance(value, str) and value in ACCENTS:
                raw["accent"] = value
                changed = True
            else:
                ignored.append(key)
        elif key == "features":
            merged, applied, invalid = _merge_features(raw, value)
            if applied:
                raw["features"] = merged
                changed = True
            if invalid:
                ignored.append(key)
        elif key == "favorite_projects":
            normalized, dropped = _normalize_projects(value)
            if normalized is None:
                ignored.append(key)
            else:
                raw[key] = normalized
                changed = True
                if dropped:
                    ignored.append(key)
        elif key == "favorite_agents":
            normalized, dropped = _normalize_agents(value)
            if normalized is None:
                ignored.append(key)
            else:
                raw[key] = normalized
                changed = True
                if dropped:
                    ignored.append(key)
        else:
            # Unbekannte Patch-Schlüssel gehören nicht in diese Datei.
            ignored.append(key)

    return version, raw, ignored, changed


def update(state_dir, patch):
    """Validiert ein Patch-Objekt und mischt gültige Schlüssel in die Datei.

    Ungültige Werte werden je Schlüssel gemeldet und nicht geschrieben; ein
    Patch ohne gültigen Schlüssel schreibt gar nicht. Unbekannte Schlüssel der
    Datei und eine höhere Version bleiben bei jedem Schreiben erhalten.

    Gelesen wird über ``vibe_storage.read_snapshot``; die erwartete Prüfsumme
    geht an ``write_text``. Ändert sich die Datei zwischen Lesen und Schreiben,
    wird der Patch auf dem frischen Stand erneut angewendet (begrenzte Zahl an
    Versuchen), statt die konkurrierende Änderung zu überschreiben.
    """
    if not isinstance(patch, dict):
        patch = {}
    target = path(state_dir)

    for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
        snapshot = vibe_storage.read_snapshot(target)
        data = _parse_document(snapshot.text)
        version, raw, ignored, changed = _merge_patch(data, patch)

        if not changed:
            return {
                "ok": True,
                "version": version,
                "stored": snapshot.exists,
                "settings": _effective(raw),
                "ignored": ignored,
            }

        document = dict(data)
        document["version"] = version
        document["settings"] = raw
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        expected = snapshot if snapshot.exists else vibe_storage.MISSING
        try:
            vibe_storage.write_text(target, text, expected=expected)
        except vibe_storage.ConcurrentChangeError:
            if attempt >= MAX_WRITE_ATTEMPTS:
                raise vibe_storage.ConcurrentChangeError(
                    f"{FILENAME} konnte nach {MAX_WRITE_ATTEMPTS} Versuchen "
                    "nicht konfliktfrei geschrieben werden: " + target
                ) from None
            continue

        return {
            "ok": True,
            "version": version,
            "stored": True,
            "settings": _effective(raw),
            "ignored": ignored,
        }

    # Unerreichbar: Der letzte Versuch kehrt zurück oder löst oben aus.
    raise vibe_storage.ConcurrentChangeError(
        f"{FILENAME} konnte nicht konfliktfrei geschrieben werden: " + target
    )
