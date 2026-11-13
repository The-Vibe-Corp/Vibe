#!/usr/bin/env python3
"""Enkelprozess des B11-Harness-Doubles: schreibt dauerhaft Lebenszeichen."""
import os
import signal
import time
from pathlib import Path

_SIGNALS = {"HUP": signal.SIGHUP, "TERM": signal.SIGTERM, "INT": signal.SIGINT}


def main():
    raw = os.environ.get("B11_IGNORE", "HUP,TERM")
    for name in {item.strip().upper() for item in raw.split(",") if item.strip()}:
        signal.signal(_SIGNALS[name], signal.SIG_IGN)
    base = Path(os.environ["B11_FIXTURE_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    (base / "grandchild.pid").write_text(str(os.getpid()), encoding="utf-8")
    tick = base / "grandchild.tick"
    while True:
        with tick.open("a", encoding="utf-8") as handle:
            handle.write("g\n")
        time.sleep(0.05)


if __name__ == "__main__":
    main()
