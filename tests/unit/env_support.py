"""Isolation von Testprozessen gegen die Umgebung des aufrufenden Läufers.

Warum diese Datei existiert: Die Tests laufen über den vibe-Paket-Läufer,
dessen Umgebung eine *laufende* Instanz beschreibt — ``VIBE_UI_BIND``,
``VIBE_UI_PORT``, ``VIBE_RUNTIME``, ``GITHUB_AUTO_MERGE`` und ein ``HOME``
mit persönlicher ``config.json``. Erbt ein Test diese Werte, bindet sein
Test-Dashboard an eine fremde Adresse (der Test fragt aber ``127.0.0.1``),
schreibt Laufzeitkennungen in produktive Pfade (EROFS im Runner) oder liest
eine persönliche Konfiguration, die ``runtime``/``state`` auf den
Produktivort legt. Ergebnis waren umgebungsabhängig rote Module.

Die Konvention ist bewusst dieselbe wie in ``test_agent_management.py``:
eine Liste der Instanzvariablen, die vor dem Start eigener Prozesse entfernt
und anschließend mit ausschließlich temporären Pfaden belegt werden. Kein
Test darf produktive ``VIBE``-/``HOME``-Konfiguration verwenden.
"""
import os
from contextlib import contextmanager

# Variablen, die die laufende Instanz beschreiben und niemals an einen
# Testprozess vererbt werden dürfen. ``PATH``, Locale und vergleichbare
# Prozessumgebung bleiben erhalten.
INHERITED_INSTANCE_KEYS = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "VIBE_UI_BIND",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_RUNTIME",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_PROFILE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_CONTAINER",
    "VIBE_MODEL",
    "VIBE_MANAGED",
    "VIBE_RUN_ID",
    "VIBE_SESSION",
    "VIBE_LOGNAME",
    "VIBE_PREFLIGHT_ASSIST",
    "VIBE_KEEP_CHANGES",
    "GITHUB_AUTO_MERGE",
    "HOME",
)

# Aktive Werte für ``VIBE_SANDBOX_ACTIVE``. ``bin/vibe_sandbox.py`` setzt die
# Variable künftig für alle in der Sandbox gestarteten Kinder.
_SANDBOX_ACTIVE_VALUES = ("1", "on", "true")


def isolated_environ(environ=None, **overrides):
    """Kopie der Prozessumgebung ohne Instanzvariablen, plus Übergaben.

    ``overrides`` werden als Zeichenketten gesetzt; ``None`` lässt den
    Schlüssel entfernt. So kann jeder Test ausschließlich temporäre Pfade
    verwenden.
    """
    source = os.environ if environ is None else environ
    env = dict(source)
    for key in INHERITED_INSTANCE_KEYS:
        env.pop(key, None)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


@contextmanager
def isolated_process_environment(**overrides):
    """Setzt ``os.environ`` für einen Import-/Aufrufblock isoliert.

    Wird für Tests verwendet, die ``bin/vibe`` als Modul laden: Die Modul-
    globals (Pfade, Ports) entstehen beim Import und dürfen nicht aus der
    Läuferumgebung stammen. Nach dem Block wird die vorherige Umgebung
    vollständig wiederhergestellt.
    """
    saved = {key: os.environ.get(key) for key in INHERITED_INSTANCE_KEYS}
    for key in INHERITED_INSTANCE_KEYS:
        os.environ.pop(key, None)
    os.environ.update(
        {key: str(value) for key, value in overrides.items() if value is not None}
    )
    try:
        yield os.environ
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def sandbox_nested(environ=None):
    """True, wenn der Testprozess in der vibe-Sandbox verschachtelt läuft.

    ``VIBE_SANDBOX_ACTIVE`` wird von ``bin/vibe_sandbox.py`` über
    ``--setenv`` an alle gestarteten Kinder weitergegeben und damit auch an
    Testprozesse, die der Läufer in der Sandbox startet. Ein verschachteltes
    bubblewrap kann keinen weiteren Benutzernamensraum anlegen (Befund:
    „No permissions to create a new namespace“); echte bwrap-Läufe sind dort
    nicht prüfbar.

    Das ist ausdrücklich eine Aussage über die *Verschachtelung*, nicht über
    die Verfügbarkeit von bwrap. Außerhalb der Sandbox dürfen bwrap-Fälle
    weiterhin scheitern, wenn bubblewrap fehlt — ein pauschales
    ``skipUnless(bwrap verfügbar)`` würde echte Defekte verdecken.
    """
    source = os.environ if environ is None else environ
    value = str(source.get("VIBE_SANDBOX_ACTIVE", "")).strip().lower()
    return value in _SANDBOX_ACTIVE_VALUES


def skip_if_sandbox_nested(test):
    """Dekoriert einen bwrap-abhängigen Testfall mit der Verschachtelungsregel."""
    import unittest

    return unittest.skipIf(
        sandbox_nested(),
        "Innerhalb der vibe-Sandbox (VIBE_SANDBOX_ACTIVE=1) kann bwrap "
        "keinen weiteren Benutzernamensraum anlegen; der echte Sandbox-Lauf "
        "ist dort nicht prüfbar (Skip betrifft nur die Verschachtelung).",
    )(test)
