#!/usr/bin/env python3
"""Laufregister für Agentenläufe (V-015).

Ein Lauf ist genau eine Ausführung des Paket-Läufers für ein Projekt. Jeder
Lauf hat eine eindeutige ID, eine eigene tmux-Sitzung, ein eigenes Lauf- und
Prüfprotokoll und einen eigenen Zustand. Das Register liegt als
``<laufzeit>/runs.json`` neben den Logs.

Eigenschaften:

* **Eindeutige IDs** — Zeitstempel plus Zufallsanteil; auch zwei Läufe
  desselben Projekts kollidieren nicht.
* **Parallele Projekte** — jede Änderung liest und schreibt unter einer
  Sperrdatei und ersetzt die Datei atomar. Ein Lauf kann den Eintrag eines
  anderen Projekts nicht überschreiben. Wo das Dateisystem keine wirksame
  Sperre bietet (z. B. FUSE/NTFS), kann der letzte Schreiber gewinnen; das
  wird hier nicht als garantiert zugesichert.
* **Begrenzte Datei** — nur die letzten Einträge bleiben erhalten.

Dieses Modul startet keine Prozesse, spricht nicht mit dem Netzwerk und ruft
keine Modelle auf. Es schreibt ausschließlich im Laufzeitordner. Es ist bewusst
eigenständig (nur Standardbibliothek): ``bin/vibe-run.sh`` ruft es als Skript
auf, auch wenn die Installation unvollständig ist.

Aufruf aus ``bin/vibe`` und ``bin/vibe-run.sh``:

  vibe_runs.py key <projekt> <laufzeit> [bevorzugt]
  vibe_runs.py start --runtime R --project P --name N --key K --agent A
                     [--session S] [--log L] [--verify-log V] [--id ID]
                     [--state S]
  vibe_runs.py finish --runtime R --id ID [--exit-code N] [--state finished]
  vibe_runs.py rotate <logdatei> [--max-bytes N] [--keep N]
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import time

try:  # Nur unter POSIX verfügbar; ohne Sperre bleibt der letzte Schreibvorgang gewinnen.
    import fcntl
except ImportError:  # pragma: no cover - Windows ohne vibe-Betrieb
    fcntl = None

KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
KEEP_RECORDS = 100
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_KEEP = 3
LIVE_STATES = ("starting", "running")
STATES = ("starting", "running", "finished", "stopped", "paused", "failed", "ended")


def clean_key(text):
    """Bildet aus einem beliebigen Namen einen Datei- und Sitzungsschlüssel."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(text or ""))


def digest(path):
    """Kurzer, stabiler Fingerabdruck eines Projektpfads."""
    real = os.path.realpath(os.path.abspath(str(path or "")))
    return hashlib.sha1(real.encode("utf-8", "surrogateescape")).hexdigest()[:8]


def new_run_id(key, now=None):
    """Eindeutige Lauf-ID: lesbarer Schlüssel, Zeitstempel, Zufallsanteil."""
    base = clean_key(key) or "lauf"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return f"{base}-{stamp}-{secrets.token_hex(3)}"


def rotate_log(path, max_bytes=DEFAULT_MAX_BYTES, keep=DEFAULT_KEEP):
    """Verschiebt eine zu große Logdatei nach ``.1`` und nummeriert ältere um.

    Es bleiben höchstens ``keep`` Archive. Rückgabe: True, wenn rotiert wurde.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if max_bytes is None or int(keep) < 1 or size < int(max_bytes):
        return False
    for index in range(int(keep) - 1, 0, -1):
        source = f"{path}.{index}"
        if os.path.exists(source):
            os.replace(source, f"{path}.{index + 1}")
    os.replace(path, f"{path}.1")
    return True


def _fsync_dir(directory):
    """Sichert den Verzeichniseintrag nach ``os.replace`` (best effort)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".runs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(directory)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class RunRegistry:
    """Zustand aller bekannten Läufe eines Laufzeitordners."""

    def __init__(self, runtime, keep=KEEP_RECORDS):
        self.runtime = os.path.abspath(str(runtime))
        self.path = os.path.join(self.runtime, "runs.json")
        self.lock_path = os.path.join(self.runtime, "runs.lock")
        self.keep = int(keep)

    @contextlib.contextmanager
    def _locked(self):
        os.makedirs(self.runtime, exist_ok=True)
        handle = open(self.lock_path, "a+")
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                with contextlib.suppress(OSError):
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        runs = data.get("runs") if isinstance(data, dict) else None
        if not isinstance(runs, list):
            return []
        return [
            record for record in runs
            if isinstance(record, dict) and isinstance(record.get("id"), str)
        ]

    def _write(self, runs):
        text = json.dumps({"runs": runs[-self.keep:]}, indent=1, ensure_ascii=False) + "\n"
        _atomic_write(self.path, text)

    def all(self):
        return self._read()

    def get(self, run_id):
        for record in reversed(self._read()):
            if record.get("id") == run_id:
                return dict(record)
        return None

    def latest(self, project=None, key=None):
        """Jüngster Eintrag, wahlweise für einen Projektpfad oder einen Schlüssel."""
        real = os.path.realpath(os.path.abspath(project)) if project else None
        for record in reversed(self._read()):
            if real is not None and os.path.realpath(
                os.path.abspath(str(record.get("project", "")))
            ) != real:
                continue
            if key is not None and record.get("key") != key:
                continue
            return dict(record)
        return None

    def start(self, project, name, key, agent, session="", log="", verify_log="",
              run_id=None, state="running"):
        """Legt einen Lauf an oder aktualisiert ihn (gleiche ID = gleicher Lauf)."""
        record = {
            "id": run_id or new_run_id(key),
            "project": str(project),
            "name": str(name),
            "key": str(key),
            "agent": str(agent or ""),
            "session": str(session or ""),
            "log": str(log or ""),
            "verify_log": str(verify_log or ""),
            "state": state if state in STATES else "running",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "pid": os.getpid(),
            "exit_code": None,
        }
        with self._locked():
            runs = [item for item in self._read() if item.get("id") != record["id"]]
            runs.append(record)
            self._write(runs)
        return dict(record)

    def finish(self, run_id, exit_code=None, state="finished"):
        """Beendet einen Lauf; ein unbekannter Lauf bleibt unbekannt (None)."""
        if state not in STATES:
            raise ValueError(f"Unbekannter Laufzustand: {state!r}")
        with self._locked():
            runs = self._read()
            found = None
            for record in runs:
                if record.get("id") != run_id:
                    continue
                record["state"] = state
                record["exit_code"] = exit_code
                record["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                found = dict(record)
            if found is not None:
                self._write(runs)
            return found


def choose_key(project, runtime, preferred=""):
    """Kollisionsfreier Laufschlüssel für einen direkt gestarteten Lauf.

    ``preferred`` (von ``bin/vibe``) gilt unverändert. Ohne Vorgabe wird der
    Verzeichnisname verwendet — außer ein anderes Projekt ist bereits unter
    demselben Schlüssel eingetragen; dann kommt ein Pfad-Fingerabdruck hinzu.
    Auch beendete Läufe zählen mit: Ihr Protokoll liegt weiterhin unter dem
    Schlüssel und darf nicht von einem anderen Projekt überschrieben werden.
    """
    real = os.path.realpath(os.path.abspath(str(project)))
    base = clean_key(preferred or os.path.basename(real.rstrip(os.sep))) or "projekt"
    if preferred:
        return base
    for record in reversed(RunRegistry(runtime).all()):
        if record.get("key") != base:
            continue
        other = record.get("project") or ""
        if os.path.realpath(os.path.abspath(other)) != real:
            return f"{base}-{digest(real)}"
    return base


def _state(value):
    if value not in STATES:
        raise argparse.ArgumentTypeError(
            "Zustand muss einer von " + ", ".join(STATES) + " sein"
        )
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_runs.py", description="Laufregister für Agentenläufe (V-015)"
    )
    sub = parser.add_subparsers(dest="command")

    key = sub.add_parser("key", help="kollisionsfreien Laufschlüssel ausgeben")
    key.add_argument("project")
    key.add_argument("runtime")
    key.add_argument("preferred", nargs="?", default="")

    start = sub.add_parser("start", help="Lauf anlegen oder aktualisieren")
    start.add_argument("--runtime", required=True)
    start.add_argument("--project", required=True)
    start.add_argument("--name", required=True)
    start.add_argument("--key", required=True)
    start.add_argument("--agent", default="")
    start.add_argument("--session", default="")
    start.add_argument("--log", default="")
    start.add_argument("--verify-log", default="")
    start.add_argument("--id", default="")
    start.add_argument("--state", type=_state, default="running")

    finish = sub.add_parser("finish", help="Lauf beenden")
    finish.add_argument("--runtime", required=True)
    finish.add_argument("--id", required=True)
    finish.add_argument("--exit-code", type=int, default=None)
    finish.add_argument("--state", type=_state, default="finished")

    rotate = sub.add_parser("rotate", help="Logdatei bei Bedarf rotieren")
    rotate.add_argument("path")
    rotate.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    rotate.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    if args.command == "key":
        print(choose_key(args.project, args.runtime, args.preferred))
        return 0
    if args.command == "start":
        record = RunRegistry(args.runtime).start(
            project=args.project, name=args.name, key=args.key, agent=args.agent,
            session=args.session, log=args.log, verify_log=args.verify_log,
            run_id=args.id or None, state=args.state,
        )
        print(record["id"])
        return 0
    if args.command == "finish":
        record = RunRegistry(args.runtime).finish(
            args.id, exit_code=args.exit_code, state=args.state
        )
        if record is None:
            print(f"Unbekannter Lauf: {args.id}", file=sys.stderr)
            return 1
        print(record["id"])
        return 0
    if args.command == "rotate":
        rotate_log(args.path, max_bytes=args.max_bytes, keep=args.keep)
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
