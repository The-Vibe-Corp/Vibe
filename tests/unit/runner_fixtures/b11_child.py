#!/usr/bin/env python3
"""Unterprozess des B11-Harness-Doubles (z. B. ein Sandbox-Wrapper).

Ignoriert dieselben Signale wie der Harness, schreibt seine PID und Ticks und
startet einen Enkelprozess, der die eigentliche Arbeit nachbildet.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_SIGNALS = {"HUP": signal.SIGHUP, "TERM": signal.SIGTERM, "INT": signal.SIGINT}


def main():
    raw = os.environ.get("B11_IGNORE", "HUP,TERM")
    for name in {item.strip().upper() for item in raw.split(",") if item.strip()}:
        signal.signal(_SIGNALS[name], signal.SIG_IGN)
    base = Path(os.environ["B11_FIXTURE_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "child.pid").write_text(str(os.getpid()), encoding="utf-8")
    script = Path(__file__).resolve().with_name("b11_grandchild.py")
    grandchild = subprocess.Popen([sys.executable, str(script)])
    tick = base / "child.tick"
    while True:
        with tick.open("a", encoding="utf-8") as handle:
            handle.write("c\n")
        if grandchild.poll() is not None:
            sys.exit(grandchild.returncode)
        time.sleep(0.05)


if __name__ == "__main__":
    main()
