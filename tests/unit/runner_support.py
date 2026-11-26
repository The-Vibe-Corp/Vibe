"""Gemeinsame Helfer für Tests des Paket-Läufers.

Die Datei ist kein Testmodul (der Name beginnt nicht mit ``test_``). Sie
liefert ein echtes, kleines Git-Repository, eine Installation mit den
Läufermodulen und einen nachgebildeten Agenten, der ein Arbeitspaket
vollständig abschließt (Commit, Nachweis, Feature-Dokumentation, Review).
Es werden keine Modellaufrufe ausgeführt.
"""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"


def git(project, *args, env=None):
    """Führt git im Projektordner aus, ohne eine Ausnahme zu werfen."""
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def init_repo(project):
    """Legt ein leeres Repository mit reproduzierbarer Identität an."""
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    git(project, "config", "user.name", "Test")
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "commit.gpgsign", "false")
    return project


def commit_all(project, message="Ausgangsstand"):
    """Commitet den aktuellen Stand; ein Fehler ist ein Testfehler."""
    git(project, "add", "-A")
    result = git(project, "commit", "-q", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def install_runner(install):
    """Kopiert Läufer und benötigte Module in eine Testinstallation.

    GH-76: ``vibe-run.sh`` ruft das Subkommando ``platform-instructions``
    über ``bin/vibe_harness.py`` auf (nicht über ``bin/vibe``, weil viele
    Läufertests den CLI-Einstieg als Attrappe ersetzen). Die Testinstallation
    braucht deshalb genau die bisherigen Läufermodule plus ``vibe_harness.py``
    und dessen Import ``vibe_opencode.py``. ``vibe_keys.py`` bleibt bewusst
    draußen: Sein Vorhandensein aktiviert im Läufer den Key-Sync, der für den
    Pi-Harness nicht unterstützt ist; die ältere Installation ohne dieses
    Modul ist der dokumentierte, getestete Zustand. ``vibe_usage.py`` wird
    kopiert, damit die Läuferprüfung von ``sessions finish-package`` den
    Kostenleser in der Testinstallation findet; ``vibe_gates*.py`` bleibt wie
    bei HEAD eine Glob-Kopie, damit ältere Stände ohne sie lauffähig bleiben.
    """
    bin_dir = install / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "vibe-run.sh",
        "vibe_runs.py",
        "vibe_packages.py",
        "vibe_questions.py",
        "vibe_autonomous.py",
        "vibe_storage.py",
        # B16: github-complete ist eine echte Abschlussschranke. Ohne dieses
        # Modul würde das Subkommando in jeder Fake-Toolchain mit
        # SystemExit(1) fehlschlagen und alle Läufer-Tests blockieren.
        "vibe_github.py",
        # GH-76: Der Läufer erzeugt die Plattformanweisungen über dieses
        # Modul; es importiert vibe_opencode.
        "vibe_harness.py",
        "vibe_opencode.py",
    ):
        shutil.copy(BIN / name, bin_dir / name)
    # GH-48: Der Läufer transportiert und synchronisiert Tickets über den
    # projektlokalen Speicher. Vor der GH-48-Implementierung fehlt das Modul
    # noch; die Kopie bleibt dann aus, damit ältere Stände lauffähig sind.
    tickets = BIN / "vibe_tickets.py"
    if tickets.is_file():
        shutil.copy(tickets, bin_dir / tickets.name)
    # GH-99: Der Kostenleser für ``sessions finish-package`` liegt als eigenes
    # Modul vor und muss in der Testinstallation verfügbar sein.
    usage = BIN / "vibe_usage.py"
    if usage.is_file():
        shutil.copy(usage, bin_dir / usage.name)
    # AP10: Die Schrankeneinstellungen liegen als eigenes Modul vor. Auch
    # hier bleiben ältere Stände ohne dieses Modul unverändert lauffähig.
    for source in sorted(BIN.glob("vibe_gates*.py")):
        shutil.copy(source, bin_dir / source.name)
    return bin_dir


def write_agents(agents_dir, *names):
    """Legt minimale Agentendateien an; der Läufer prüft nur die Existenz."""
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (agents_dir / (name + ".md")).write_text(
            "---\ndescription: Testagent\nmode: subagent\n---\n",
            encoding="utf-8",
        )


STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="task", state="open", **extra):
    """Ticketdatensatz mit allen GH-48-Vertragsfeldern."""
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


def write_project(project, env_text, feedback=None, tickets=None):
    """Schreibt Projektkonfiguration und optional den GH-48-Ticketspeicher.

    ``feedback``/``tickets`` sind Listen von Ticketdatensätzen
    (``ticket_record``). Die früheren Markdown-Ledger TICKETS.md/FEEDBACK.md
    entstehen bewusst nicht mehr; Markdown-Zeichenketten werden abgelehnt,
    damit alte Fixtures nicht stillschweigend wirkungslos weiterlaufen.
    """
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    # GH-48: .vibe ist Laufzeitstand und wird nie versioniert; sonst würde
    # jede Zustandsänderung (z. B. mark_blocked) den Integrationsstand
    # beschmutzen.
    gitignore = project / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".vibe/\n", encoding="utf-8")
    records = []
    for source in (tickets, feedback):
        if source is None:
            continue
        if isinstance(source, str):
            raise ValueError(
                "write_project erwartet Ticketdatensätze, keine "
                "Markdown-Ledger (GH-48).")
        records.extend(source)
    if records:
        write_ticket_store(project, records)


def write_ticket_store(project, tickets):
    """Schreibt den GH-48-Ticketspeicher ``.vibe/tickets.json`` roh.

    Bewusst ohne ``bin/vibe_tickets.py``: Tests, die den Speicher nur als
    Eingabe brauchen, bleiben unabhängig vom Speichermodul.
    """
    import json

    path = Path(project) / ".vibe" / "tickets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "tickets": tickets},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return path


# F25: Markierung des Datensatzendes je opencode-Aufruf in FAKE_ARGS_PATH.
# Ein Prompt kann kein NUL-Byte enthalten, deshalb ist die Grenze eindeutig.
ARGS_RECORD_END = "ARGS_RECORD_END"

FAKE_OPENCODE = r'''#!/usr/bin/env python3
"""Schließt ein Arbeitspaket so ab, wie es die Abschlussschranke verlangt."""
import json
import os
import pathlib
import re
import subprocess
import sys

def _b13_serve(argv):
    """B13: Attrappe eines privaten opencode-Servers des Paket-Läufers.

    Sie beantwortet GET /api/info mit 200, wenn die Basic-Auth-Anmeldung
    ``opencode:<OPENCODE_SERVER_PASSWORD>`` stimmt, sonst mit 401; POST auf
    ``/prompt`` wird ebenso geschützt entgegengenommen. Jede Beobachtung
    landet als JSON-Zeile in ``FAKE_SERVE_RECORD``. Mit FAKE_SERVE_NEVER=1
    lauscht die Attrappe nie (der Läufer darf den Agenten dann nicht
    starten); mit FAKE_SERVE_DELAY startet sie verzögert.
    """
    import base64
    import signal
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    port = 0
    if "--port" in argv:
        try:
            port = int(argv[argv.index("--port") + 1])
        except (ValueError, IndexError):
            port = 0
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    record = os.environ.get("FAKE_SERVE_RECORD")
    delay = float(os.environ.get("FAKE_SERVE_DELAY", "0") or 0)
    never = os.environ.get("FAKE_SERVE_NEVER", "") == "1"

    def note(entry):
        if not record:
            return
        with open(record, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print("SERVE_FAKE_START", flush=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _auth_ok(self):
            expected = base64.b64encode(
                ("opencode:" + password).encode("utf-8")).decode("ascii")
            return self.headers.get("Authorization", "") == "Basic " + expected

        def _reply(self, ok):
            body = json.dumps({"ok": ok}, ensure_ascii=False).encode("utf-8")
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            ok = self._auth_ok()
            note({"method": "GET", "path": self.path, "auth_ok": ok})
            self._reply(ok)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            ok = self._auth_ok()
            note({
                "method": "POST",
                "path": self.path,
                "auth_ok": ok,
                "body": raw.decode("utf-8", "replace"),
                "tmpdir": os.environ.get("TMPDIR", ""),
            })
            self._reply(ok)

    if never:
        note({"event": "never-listen", "tmpdir": os.environ.get("TMPDIR", "")})
        time.sleep(120)
        return
    if delay:
        time.sleep(delay)

    def password_shape(name):
        """F31: Nur Anwesenheit und Laenge notieren, nie den Kennwortwert."""
        value = os.environ.get(name)
        return bool(value), (len(value) if value is not None else 0)

    op_present, op_len = password_shape("OPENCODE_PASSWORD")
    server_present, server_len = password_shape("OPENCODE_SERVER_PASSWORD")
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    bound = httpd.server_address[1]
    note({"event": "listening", "port_bound": bound, "pid": os.getpid(),
          "cwd": os.getcwd(),
          "tmpdir": os.environ.get("TMPDIR", ""),
          "opencode_password_present": op_present,
          "opencode_password_len": op_len,
          "server_password_present": server_present,
          "server_password_len": server_len})
    print("SERVE_FAKE_PORT=" + str(bound), flush=True)

    def terminate(signum, frame):
        note({"event": "term", "signal": signum})
        print("SERVE_FAKE_TERM", flush=True)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        httpd.serve_forever()
    finally:
        note({"event": "exit"})

args = sys.argv[1:]
prompt = args[-1] if args else ""
match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", prompt)
pid = match.group(1) if match else "F1"
cwd = pathlib.Path.cwd()

args_path = os.environ.get("FAKE_ARGS_PATH")
if args_path:
    # F25: Je Aufruf wird die Argumentliste angehängt, nicht überschrieben.
    # Datensatzende markiert ein Token, NUL-getrennt; ein Prompt kann kein
    # NUL-Byte enthalten, deshalb ist die Grenze eindeutig erkennbar.
    with open(args_path, "ab") as handle:
        for argument in args:
            handle.write(argument.encode("utf-8") + b"\0")
        handle.write("ARGS_RECORD_END".encode("utf-8") + b"\0")

# B13: Der private Server-Aufruf (``opencode serve``) wird vor der
# Agentenlogik behandelt; die Argumentliste ist bereits protokolliert.
if args and args[0] == "serve":
    _b13_serve(args)
    sys.exit(0)

output = os.environ.get("FAKE_OUTPUT")
if output:
    sys.stdout.write(output)
    sys.stdout.flush()

# Ein Preflight-Auftrag enthält die Befunde („Preflight ...“) und die
# Anweisung des Nutzers. Er darf nicht als Arbeitspaket F1 gelten.
is_preflight = (
    "preflight" in prompt.lower()
    or "anweisung des nutzers" in prompt.lower()
)
calls = os.environ.get("FAKE_CALLS")
if calls:
    with open(calls, "a", encoding="utf-8") as handle:
        if is_preflight:
            handle.write(
                "preflight\t" + str(cwd) + "\t"
                + json.dumps(prompt, ensure_ascii=False) + "\n"
            )
        else:
            handle.write(pid + "\t" + str(cwd) + "\n")

if is_preflight:
    mode = os.environ.get("FAKE_PREFLIGHT_MODE", "noop")
    if mode == "fail":
        sys.stderr.write(
            "Preflight-Agent fehlgeschlagen: Befunde nicht behoben\n"
        )
        sys.exit(1)
    if mode == "fix":
        target = cwd / "unfertig.txt"
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        subprocess.run(
            ["git", "-C", str(cwd), "add", "-A"],
            check=False, capture_output=True, text=True,
        )
        staged = subprocess.run(
            ["git", "-C", str(cwd), "diff", "--cached", "--quiet"],
            check=False,
        )
        if staged.returncode != 0:
            subprocess.run(
                ["git", "-C", str(cwd), "commit", "-q", "-m",
                 "Preflight: Befund behoben"],
                check=False, capture_output=True, text=True,
            )
    sys.exit(0)

counter_path = pathlib.Path(os.environ.get("FAKE_COUNTER", os.devnull))
try:
    counter = int(counter_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    counter = 0
counter_path.write_text(str(counter + 1), encoding="utf-8")

# F25: Ohne vorbereitete Ausgabe liefert das Fake je Aufruf eine
# Hauptsession als JSON-Ereignis, wie es opencode mit --format json tut;
# der Versuchszähler erzeugt eine eindeutige Kennung je Versuch. Mit
# FAKE_OUTPUT bleibt die Ausgabe unverändert, weil die Ausgabe die
# Session selbst vorgibt.
if not output:
    session = "ses_attempt" + str(counter + 1)
    event = json.dumps({
        "type": "text",
        "sessionID": session,
        "part": {"type": "text", "text": "Antwort " + session},
    }, ensure_ascii=False)
    sys.stdout.write(event + "\n")
    sys.stdout.flush()

sequence = os.environ.get("FAKE_MODE_SEQUENCE", "")
if sequence:
    modes = [item.strip() for item in sequence.split(",") if item.strip()]
    mode = modes[min(counter, len(modes) - 1)]
else:
    mode = os.environ.get("FAKE_MODE", "complete")

if mode == "quota":
    sys.stderr.write("429 rate limit exceeded\n")
    sys.exit(1)
if mode == "auth":
    sys.stderr.write("401 unauthorized\n")
    sys.exit(1)
if mode == "hang":
    # V-026: Der Läufer wird während eines laufenden Versuchs signalisiert.
    import time
    time.sleep(30)
    sys.exit(0)
if mode == "network":
    sys.stderr.write("ECONNRESET connection reset by peer\n")
    sys.exit(1)
if mode == "network-first" and counter == 0:
    sys.stderr.write("ECONNRESET connection reset by peer\n")
    sys.exit(1)
if mode == "fail":
    sys.stderr.write("beliebiger Agentenfehler\n")
    sys.exit(1)
if mode == "no-artifacts":
    sys.exit(0)

# AP7 (T-V21): Tamper-Varianten für den Hash-Wächter. Der nachgebildete Agent
# verändert transportierte .vibe-Dateien im eigenen Arbeitsbaum, schließt das
# Paket aber weiterhin vollständig ab. So stammt ein Block eindeutig vom
# Wächter und nicht von einer fehlenden Abschlussschranke. ``FAKE_TAMPER`` ist
# eine Liste ``aktion:dateiname`` (Komma-getrennt): ``append`` hängt eine
# Zeile an, ``rewrite`` schreibt identisch neu, ``create`` legt die Datei an,
# ``delete`` entfernt eine beim Start vorhandene Datei. Eine bereits fehlende
# Datei bleibt bei ``delete`` folgenlos (``rm -f``-Semantik), damit derselbe
# Modus auch die Best-effort-Regel prüfen kann.
def _ap7_tamper():
    spec = os.environ.get("FAKE_TAMPER", "").strip()
    if not spec:
        return
    for entry in spec.split(","):
        entry = entry.strip()
        if not entry:
            continue
        action, _, name = entry.partition(":")
        path = cwd / ".vibe" / name
        if action == "create":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '{"version": 1, "min_tests": 1, "envs": {}}\n',
                encoding="utf-8",
            )
            continue
        if action == "delete":
            # Löschen braucht Schreibrecht auf dem Verzeichnis, nicht auf der
            # Datei. Falls ein restriktives Setup den Unlink verwehrt, hilft
            # der Schreibschutz des Transports (best effort 0444) zuvor.
            try:
                path.unlink()
            except OSError:
                try:
                    path.chmod(0o644)
                    path.unlink()
                except OSError:
                    pass
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            # Der Transport setzt best effort 0444; für die Manipulation
            # braucht die Attrappe Schreibrechte.
            path.chmod(0o644)
        except OSError:
            pass
        if action == "append":
            path.write_text(
                original + "AGENT_HAT_VERAENDERT=1\n", encoding="utf-8"
            )
        elif action == "rewrite":
            path.write_text(original, encoding="utf-8")


_ap7_tamper()


def run(*command, check=True):
    return subprocess.run(
        list(command), cwd=cwd, check=check, capture_output=True, text=True
    )


def complete_ticket(commit):
    """Schließt das aktuelle Ticket als sichtbare Laufzeitdatei ab (GH-48)."""
    path = cwd / ("TICKET-" + pid + ".json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {"id": pid, "title": pid, "type": "task",
                  "description": ""}
    record.setdefault("type", "task")
    record.update({
        "id": pid,
        "state": "done",
        "commit": commit,
        "test": "test_" + pid.lower().replace("-", "_"),
    })
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


(cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Umsetzung")
short = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

complete_ticket(short)

(cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "features" / (pid + ".md")).write_text(
    "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
)
(cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
    "# Review\n\nVerdict: PASS\n", encoding="utf-8"
)
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Nachweis")
dirty = os.environ.get("FAKE_DIRTY_INTEGRATION")
if dirty and counter == 0:
    pathlib.Path(dirty, "dirty.txt").write_text("x\n", encoding="utf-8")
if os.environ.get("FAKE_PAUSE_AFTER_FIRST") and counter == 0:
    # B17: Der Agent erhält bewusst keinen Produktivpfad VIBE_RUNTIME.
    # FAKE_RUNTIME ist eine reine Fixture-Variable des Tests im Prüfkontext
    # und wird unverändert an den nachgebildeten Agenten vererbt.
    runtime = pathlib.Path(os.environ["FAKE_RUNTIME"])
    name = os.environ.get("VIBE_LOGNAME", "proj")
    (runtime / (name + ".pause-after")).touch()
sys.exit(0)
'''

FAKE_VIBE = '''#!/usr/bin/env python3
raise SystemExit(3)
'''

FAKE_CURL = '''#!/usr/bin/env bash
exit 7
'''

# B13: Echte HTTP-Attrappe für curl. Der Läufer prüft die Servergesundheit
# mit curl; diese Attrappe führt die Anfrage wirklich aus (Basic-Auth über
# -u) und meldet Erfolg nur bei einer 2xx-Antwort. Ist niemand am Port,
# schlägt sie genau wie curl fehl (Exit 7). Für Tests, deren Lauf über den
# privaten opencode-Server gehen soll (B13), statt der toten FAKE_CURL
# über ``install_real_curl`` einsetzen.
REAL_CURL = r'''#!/usr/bin/env python3
import base64
import http.client
import sys
from urllib.parse import urlparse

args = sys.argv[1:]
url = ""
userpass = ""
index = 0
while index < len(args):
    item = args[index]
    if item == "-u" and index + 1 < len(args):
        userpass = args[index + 1]
        index += 2
        continue
    if item.startswith("http"):
        url = item
    index += 1
if not url:
    sys.exit(7)
target = urlparse(url)
headers = {}
if userpass:
    headers["Authorization"] = "Basic " + base64.b64encode(
        userpass.encode("utf-8")).decode("ascii")
try:
    connection = http.client.HTTPConnection(
        target.hostname, target.port or 80, timeout=3)
    connection.request("GET", target.path or "/", headers=headers)
    response = connection.getresponse()
    response.read()
    healthy = 200 <= response.status < 300
    connection.close()
except OSError:
    healthy = False
sys.exit(0 if healthy else 7)
'''


def opencode_arg_records(args_path):
    """Zerlegt die per Aufruf angehängten Argumentlisten des opencode-Fakes.

    Rückgabe: Liste von Argumentlisten, in Aufrufreihenfolge. Fehlt die Datei,
    ist die Liste leer.
    """
    try:
        raw = Path(args_path).read_bytes()
    except OSError:
        return []
    tokens = raw.decode("utf-8", "surrogateescape").split("\0")
    records = []
    current = []
    for token in tokens:
        if token == ARGS_RECORD_END:
            records.append(current)
            current = []
        elif token:
            current.append(token)
    return records


def install_real_curl(fakebin):
    """Ersetzt die curl-Attrappe durch die echte HTTP-Attrappe (B13).

    Für Läufer-Tests, die den privaten opencode-Server verwenden: Die
    Gesundheitsprüfung des Läufers muss ein lauschendes Server-Fake wirklich
    erreichen können; die toten ``FAKE_CURL``-Attrappe würde jede Prüfung
    scheitern lassen und den Lauf abbrechen.
    """
    curl = fakebin / "curl"
    curl.write_text(REAL_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return curl


def install_fake_tools(root):
    """Legt opencode-, curl- und vibe-Attrappen in einem eigenen PATH ab."""
    fakebin = root / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    for name in ("opencode", "package-agent"):
        path = fakebin / name
        path.write_text(FAKE_OPENCODE, encoding="utf-8")
        path.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return fakebin
