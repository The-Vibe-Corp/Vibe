#!/usr/bin/env python3
"""Compat-Shim für die isolierte Projektprüfung (AP7-Korbat, T-V16).

Die eigentliche Logik liegt seit AP7 in ``scripts/verify_engine.py``. Dieser
Shim erhält den bisherigen Aufruf ``python3 scripts/verify.py …`` am Leben,
indem er mit denselben argv an die Engine delegiert (``os.execv``). Er trägt
keine eigene Prüflogik und liest keine Konfiguration.
"""
import os
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().with_name("verify_engine.py")

# Delegation per os.execv: der Python-Interpreter ersetzt diesen Prozess; die
# Engine erhält dieselben argv. So bleibt der alte Aufrufer gültig, ohne dass
# verify_engine.py als ausführbare Datei vorliegen muss (FUSE/NTFS-sicher).
os.execv(sys.executable, [sys.executable, str(ENGINE)] + sys.argv[1:])
