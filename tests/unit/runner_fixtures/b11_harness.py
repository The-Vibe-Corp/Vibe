#!/usr/bin/env python3
"""Test-Double für einen Agenten-Harness (B11/1).

Das Läufer-Skript ruft dieses Programm als ``opencode`` auf. Es stellt einen
Harness nach, der Signale nicht beachtet: Die in ``B11_IGNORE`` genannten
Signale werden ignoriert, das Programm schreibt Lebenszeichen (Ticks) und
startet einen Unterprozess samt Enkelprozess.

Umgebung:
  B11_FIXTURE_DIR  Verzeichnis für pid-/tick-Dateien (Pflicht)
  B11_IGNORE       Signale, die ignoriert werden (Vorgabe ``HUP,TERM``)
  B11_CHILD        ``1`` startet Unter- und Enkelprozess (Vorgabe ``1``)
  B11_EXIT_AFTER   Sekunden bis zum regulären Ende (leer = endlos)
  B11_EXIT_CODE    Exit-Code des regulären Endes (Vorgabe ``0``)

Es werden keine Modelle, Netze oder persönlichen Konfigurationen verwendet.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_SIGNALS = {"HUP": signal.SIGHUP, "TERM": signal.SIGTERM, "INT": signal.SIGINT}


def ignored_signals():
    """Liest die zu ignorierenden Signale aus ``B11_IGNORE``."""
    raw = os.environ.get("B11_IGNORE", "HUP,TERM")
    return {item.strip().upper() for item in raw.split(",") if item.strip()}


def main():
    for name in ignored_signals():
        signal.signal(_SIGNALS[name], signal.SIG_IGN)
    base = Path(os.environ["B11_FIXTURE_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "harness.pid").write_text(str(os.getpid()), encoding="utf-8")
    child = None
    if os.environ.get("B11_CHILD", "1") == "1":
        script = Path(__file__).resolve().with_name("b11_child.py")
        child = subprocess.Popen([sys.executable, str(script)])
    exit_after = os.environ.get("B11_EXIT_AFTER", "").strip()
    deadline = time.monotonic() + float(exit_after) if exit_after else None
    tick = base / "harness.tick"
    while True:
        with tick.open("a", encoding="utf-8") as handle:
            handle.write("h\n")
        if deadline is not None and time.monotonic() >= deadline:
            if child is not None:
                child.kill()
                child.wait()
            sys.exit(int(os.environ.get("B11_EXIT_CODE", "0")))
        time.sleep(0.05)


if __name__ == "__main__":
    main()
