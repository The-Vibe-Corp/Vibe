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


SUBAGENT_FINISHED = ("completed", "error", "failed", "cancelled", "canceled")
# opencode nennt das Werkzeug intern "task"; ältere Stände und die Anzeige
# verwenden "subagent". Beide Formen werden erkannt.
SUBAGENT_TOOLS = ("task", "subagent")


def subagent_state_path(log_path):
    """Zustandsdatei mit Hauptsession und erfassten Subagenten je Laufprotokoll."""
    return str(log_path) + ".state.json"


def load_subagent_state(path):
    """Liest die Zustandsdatei; fehlende oder defekte Daten sind ein leerer Zustand."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"session": "", "subagents": []}
    if not isinstance(data, dict):
        return {"session": "", "subagents": []}
    session = data.get("session") if isinstance(data.get("session"), str) else ""
    entries = [
        dict(item) for item in data.get("subagents") or []
        if isinstance(item, dict)
    ]
    return {"session": session, "subagents": entries}


def save_subagent_state(path, state):
    """Schreibt den Subagenten-Zustand atomar; nur der Läufer schreibt hier."""
    text = json.dumps(state, ensure_ascii=False, indent=1) + "\n"
    _atomic_write(path, text)


def _subagent_session(part, tool_state=None):
    """Liest die Sub-Session aus den Metadaten einer Werkzeugausführung.

    opencode legt das Ergebnis einer Werkzeugausführung unter
    ``part.state.metadata`` ab; dort steht bei ``task`` ein verschachteltes
    ``metadata`` mit ``sessionID``. Ältere Stände und Testnachbildungen führen
    ``metadata`` direkt am Teil. Beide Formen sind gültig.
    """
    candidates = []
    if isinstance(tool_state, dict):
        candidates.append(tool_state.get("metadata"))
    candidates.append(part.get("metadata"))
    for metadata in candidates:
        if not isinstance(metadata, dict):
            continue
        inner = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else metadata
        value = inner.get("sessionID") or inner.get("session_id") or ""
        if isinstance(value, str) and value:
            return value
    return ""


def _subagent_entry(state, session, agent, description):
    """Findet den bestehenden Eintrag; ohne Session über Agent und Beschreibung."""
    if session:
        for entry in state["subagents"]:
            if entry.get("session") == session:
                return entry
        return None
    for entry in state["subagents"]:
        if (not entry.get("session") and entry.get("agent") == agent
                and entry.get("description") == description
                and entry.get("status") == "running"):
            return entry
    return None


def translate_event(event, state):
    """Übersetzt ein opencode-JSON-Ereignis in Protokollzeilen und Zustand.

    Rückgabe: (Zeilen, Zustand geändert). Roh-JSON wird nie zurückgegeben.
    """
    if not isinstance(event, dict):
        return [], False
    changed = False
    session = event.get("sessionID")
    if isinstance(session, str) and session and not state.get("session"):
        state["session"] = session
        changed = True

    kind = event.get("type")
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    if kind == "text":
        text = part.get("text")
        if isinstance(text, str) and text:
            return text.splitlines(), changed
        return [], changed
    if kind == "reasoning":
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            return ["[Denken] " + line for line in text.splitlines()], changed
        return [], changed
    if kind == "error":
        error = event.get("error")
        if isinstance(error, dict):
            data = error.get("data") if isinstance(error.get("data"), dict) else {}
            message = data.get("message") or error.get("message") or error.get("name") or ""
        else:
            message = error
        message = " ".join(str(message or "").split())
        return (["[Fehler] " + message] if message else []), changed
    if kind != "tool_use":
        return [], changed

    tool = part.get("tool") or part.get("name") or "?"
    tool_state = part.get("state") if isinstance(part.get("state"), dict) else {}
    status = str(tool_state.get("status") or "unbekannt")
    inputs = tool_state.get("input") if isinstance(tool_state.get("input"), dict) else {}
    if tool not in SUBAGENT_TOOLS:
        detail = inputs.get("description") or inputs.get("command") or inputs.get("filePath") or ""
        detail = " ".join(str(detail).split())
        line = f"[Werkzeug] {tool} — {status}"
        return ([line + (": " + detail if detail else "")]), changed

    agent = str(inputs.get("agent") or inputs.get("subagent_type") or "")
    description = str(inputs.get("description") or "")
    prompt = inputs.get("prompt") if isinstance(inputs.get("prompt"), str) else ""
    output = tool_state.get("output") if isinstance(tool_state.get("output"), str) else ""
    child_session = _subagent_session(part, tool_state)
    now = int(time.time())
    entry = _subagent_entry(state, child_session, agent, description)
    if entry is None:
        entry = {
            "session": child_session,
            "agent": agent,
            "description": description,
            "prompt": prompt,
            "status": status,
            "started": now,
            "ended": 0,
            "output": "",
        }
        state["subagents"].append(entry)
        changed = True
    for key, value in (
        ("session", child_session), ("agent", agent),
        ("description", description), ("prompt", prompt),
    ):
        if value and entry.get(key) != value:
            entry[key] = value
            changed = True
    if entry.get("status") != status:
        entry["status"] = status
        changed = True
    if output and entry.get("output") != output:
        entry["output"] = output
        changed = True
    ended = now if status in SUBAGENT_FINISHED else 0
    if entry.get("ended") != ended:
        entry["ended"] = ended
        changed = True
    if not isinstance(entry.get("started"), int):
        entry["started"] = now
        changed = True

    lines = [f"[Subagent] {agent or '?'}: {description or '(ohne Beschreibung)'} — {status}"]
    if output:
        lines.extend(output.splitlines())
    return lines, changed


def stream_events(stdin, emit, state_path):
    """Liest JSON-Zeilen von stdin, schreibt Klartext und pflegt den Zustand.

    Nicht-JSON-Zeilen (z. B. stderr des Agenten) werden unverändert
    durchgereicht. Jede Zustandsänderung wird atomar gespeichert, damit das
    Dashboard nie eine halbe Datei liest.
    """
    state = load_subagent_state(state_path)
    for raw in stdin:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if not line.lstrip().startswith("{"):
            emit(line)
            continue
        try:
            event = json.loads(line)
        except ValueError:
            emit("opencode: " + line)
            continue
        lines, changed = translate_event(event, state)
        for output_line in lines:
            emit(output_line)
        if changed:
            save_subagent_state(state_path, state)


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

    stream = sub.add_parser(
        "stream",
        help="opencode-JSON-Ereignisse in Klartext und Subagenten-Zustand übersetzen",
    )
    stream.add_argument("--state", required=True, help="Zustandsdatei <log>.state.json")
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
    if args.command == "stream":
        def emit(line):
            sys.stdout.write(str(line) + "\n")
            sys.stdout.flush()
        stream_events(sys.stdin, emit, args.state)
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
