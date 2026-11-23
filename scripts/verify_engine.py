#!/usr/bin/env python3
"""Isolierte Projektprüfung für vibe — Kern (AP7-Korbat, T-V13/T-V16–T-V19).

Aufruf über das Frontend: bash scripts/verify.sh quick|package|full [Optionen].
Die Engine liest die Konfiguration aus <projekt>/.vibe/project.env und führt die
Prüfung in einer temporären Umgebung aus. Sie ist die einzige Prüfschnittstelle
(Single Source of Truth): ``VERIFY_QUICK`` ist der einzige ausgeführte
Konfigurationsbefehl, ``VERIFY_PACKAGE``/``VERIFY_FULL`` sind keine
Befehlsvariablen der Engine mehr (der Läufer führt sie verbatim als
verify.sh-Wrapper aus). ``full`` baut den Testlauf selbst über
``scripts/run-tests-parallel.py`` aus ``VERIFY_TESTS``/``--tests`` und wertet
die Baseline (drei Zustände) aus.

Isolation (unverändert aus der früheren verify.py):
* HOME, VIBE, TMPDIR und die XDG-Verzeichnisse liegen unter einem eigenen
  temporären Prüfverzeichnis. Die Konfiguration des Aufrufers wird nur gelesen.
* Ein geerbtes TMUX wird entfernt; TMUX_TMPDIR zeigt auf ein eigenes
  Verzeichnis. So kann kein Test den tmux-Server der aufrufenden Sitzung
  beenden.
* Für Dashboard, opencode, Tests und Prüfung werden eigene freie Ports
  bereitgestellt (VIBE_UI_PORT, VIBE_OPENCODE_PORT, VIBE_TEST_PORT,
  VIBE_VERIFY_PORT).

Guards (T-V13):
* Selbstpfad-Wächter: ``VERIFY_QUICK`` darf kein Token enthalten, dessen
  Basisname ``verify.sh``/``verify.py``/``verify_engine.py`` ist (Rekursions-
  falle B1). Ein solcher Lauf endet mit Exit 3, ohne Rekursion.
* Tiefenwächter: ``VIBE_VERIFY_DEPTH`` ≥ 2 endet mit Exit 3; Wert 1 ist ein
  legitimer geschachtelter Lauf. Die ausgeführte Prüfung erhält Tiefe + 1.

Exitcodes:
  0  Erfolg (grün oder Baseline-OK)
  1  unerwarteter interner Fehler
  2  Aufruf- oder Modusfehler
  3  Konfiguration (Selbstreferenz/Rekursion, ungültige Baseline, gesenkte
     min_tests, fehlende Prüfkonfiguration)
  4  benötigtes Werkzeug fehlt
  5  Prüfbefehl fehlgeschlagen (ohne auswertbares Ergebnis)
  6  Testnachweis fehlt oder ist unvollständig
  7  neue Regression gegenüber der Baseline
"""
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import site
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_TOOL = 4
EXIT_CHECK = 5
EXIT_TESTS = 6
EXIT_REGRESSION = 7

MODES = ("quick", "package", "full")
TEMP_PREFIX = "vv-"
SELF_BASENAMES = ("verify.sh", "verify.py", "verify_engine.py")

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_RUNNER = SCRIPT_DIR / "run-tests-parallel.py"

USAGE = (
    "Aufruf: bash scripts/verify.sh quick|package|full [--project DIR] "
    "[--tests DIR ...]\n"
    "        [--jobs N] [--timeout SEK] [--baseline PATH] [--env LABEL]\n"
    "        [--min-tests N] [--write-baseline] [--keep]\n"
    "\n"
    "  quick    schnelle statische Prüfung (VERIFY_QUICK)\n"
    "  package  Paketprüfung (VERIFY_QUICK); Testnachweis nur bei gesetztem\n"
    "           VERIFY_PACKAGE_TESTS\n"
    "  full     vollständige Prüfung inklusive Testnachweis (VERIFY_TESTS) und\n"
    "           Baseline-Vergleich\n"
    "  --project DIR      Projekt mit .vibe/project.env (Standard: dieses "
    "Repository)\n"
    "  --tests DIR        Testverzeichnis (mehrfach; überschreibt VERIFY_TESTS\n"
    "                     bzw. VERIFY_PACKAGE_TESTS)\n"
    "  --jobs N           gleichzeitige Testmodulprozesse\n"
    "  --timeout SEK      Zeitlimit je Testmodul in Sekunden\n"
    "  --baseline PATH    Baseline-Manifest (ersetzt committed + lokale Datei)\n"
    "  --env LABEL        Umgebungs-Label für den Baseline-Vergleich "
    "(oder VERIFY_ENV)\n"
    "  --min-tests N      Mindestzahl ausgeführter Tests (überschreibt "
    "VERIFY_MIN_TESTS)\n"
    "  --write-baseline   schreibt die lokale .vibe/verify-baseline (nur full)\n"
    "  --keep             temporäres Prüfverzeichnis auch bei Erfolg behalten\n"
    "\n"
    "Exitcodes: 0 Erfolg (grün oder Baseline-OK), 1 interner Fehler, 2 Aufruf,\n"
    "           3 Konfiguration, 4 Werkzeug, 5 Prüfbefehl, 6 Testnachweis "
    "fehlt,\n"
    "           7 neue Regression gegenüber Baseline."
)


class VerifyError(Exception):
    """Abbruch mit definiertem Exitcode und verständlicher Meldung."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code, message):
    raise VerifyError(code, message)


def print_usage():
    print(USAGE)


def parse_int(value, name, code):
    """Wandelt einen Zahlenwert; bei Fehler ein verständlicher Abbruch."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        fail(code, f"{name} ist keine Zahl: {value}")
    return number


def parse_args(argv):
    """Parst den CLI-Vertrag (Frontend/Engine, T-V16)."""
    mode = None
    project = None
    keep = False
    tests = []
    jobs = None
    timeout = None
    baseline = None
    env = None
    min_tests = None
    write_baseline = False

    def store(attr, value):
        nonlocal project, jobs, timeout, baseline, env, min_tests
        if attr == "tests":
            tests.append(value)
        elif attr == "project":
            project = value
        elif attr == "jobs":
            jobs = value
        elif attr == "timeout":
            timeout = value
        elif attr == "baseline":
            baseline = value
        elif attr == "env":
            env = value
        elif attr == "min_tests":
            min_tests = value

    value_options = {
        "--project": "project",
        "--tests": "tests",
        "--jobs": "jobs",
        "--timeout": "timeout",
        "--baseline": "baseline",
        "--env": "env",
        "--min-tests": "min_tests",
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            print_usage()
            raise SystemExit(EXIT_OK)
        if arg == "--keep":
            keep = True
        elif arg == "--write-baseline":
            write_baseline = True
        elif arg in value_options:
            index += 1
            if index >= len(argv):
                fail(EXIT_USAGE, f"{arg} benötigt einen Wert.")
            store(value_options[arg], argv[index])
        elif arg.startswith("--") and "=" in arg:
            name, _, value = arg.partition("=")
            if name not in value_options:
                fail(EXIT_USAGE, f"Unbekannte Option: {name}")
            store(value_options[name], value)
        elif arg.startswith("-"):
            fail(EXIT_USAGE, f"Unbekannte Option: {arg}")
        elif mode is None:
            if arg not in MODES:
                fail(
                    EXIT_USAGE,
                    f"Unbekannter Modus '{arg}'. Erlaubt: {', '.join(MODES)}.",
                )
            mode = arg
        else:
            fail(EXIT_USAGE, f"Überzähliges Argument: {arg}")
        index += 1
    if mode is None:
        fail(EXIT_USAGE, "Modus fehlt.")
    return {
        "mode": mode,
        "project": project,
        "keep": keep,
        "tests": tests,
        "jobs": jobs,
        "timeout": timeout,
        "baseline": baseline,
        "env": env,
        "min_tests": min_tests,
        "write_baseline": write_baseline,
    }


def read_project_env(path):
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(EXIT_CONFIG, f"Prüfkonfiguration {path} ist nicht lesbar: {error}")
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not match:
            fail(
                EXIT_CONFIG,
                f"{path}:{number}: erwartet KEY=WERT, gefunden: {stripped}",
            )
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[match.group(1)] = value
    return values


def project_root(argument):
    root = argument if argument is not None else Path(__file__).resolve().parent.parent
    root = Path(root).expanduser().resolve()
    if not (root / ".vibe" / "project.env").is_file():
        fail(
            EXIT_CONFIG,
            f"{root}/.vibe/project.env fehlt. Prüfbefehle müssen dort stehen.",
        )
    return root


def check_tools(values):
    declared = shlex.split(values.get("VERIFY_TOOLS", ""))
    missing = [tool for tool in declared if shutil.which(tool) is None]
    if missing:
        fail(
            EXIT_TOOL,
            "Benötigte Werkzeuge fehlen: "
            + ", ".join(missing)
            + " (VERIFY_TOOLS in .vibe/project.env).",
        )
    return declared


def allocate_ports(count):
    ports = []
    while len(ports) < count:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port in (8787, 4096) or port in ports:
            continue
        ports.append(port)
    return ports


def prepare_environment(base):
    home = base / "home"
    vibe = base / "vibe"
    tmp = base / "tmp"
    screenshots = base / "screenshots"
    opencode_config = base / "opencode-config"
    opencode_state = base / "state"
    tmux = base / "tmux"
    for folder in (
        home / ".config",
        home / ".cache" / "opencode",
        home / ".local" / "share",
        home / ".local" / "state",
        vibe / "_toolchain",
        vibe / "_logs",
        tmp,
        screenshots,
        opencode_config,
        opencode_state,
        tmux,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte.
    tmux.chmod(0o700)
    # opencode startet ohne vorhandenen Modellcache einen Hintergrunddienst und
    # wartet auf dessen Port. Eine leere Cache-Markierung lässt 'opencode models'
    # den mitgelieferten Katalog verwenden; es werden keine echten Anbieter-
    # oder Modellaufrufe ausgeführt.
    (home / ".cache" / "opencode" / "models.json").write_text(
        "{}\n", encoding="utf-8"
    )
    gitconfig = base / "gitconfig"
    gitconfig.write_text("", encoding="utf-8")
    # Entwicklungsabhängigkeiten (z. B. Playwright) liegen häufig im
    # Benutzer-Site-Paket. Der Pfad wird gelesen, geschrieben wird nur im
    # temporären HOME.
    python_userbase = site.getuserbase()
    playwright_browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(
        Path.home() / ".cache" / "ms-playwright"
    )

    ui_port, opencode_port, test_port, verify_port = allocate_ports(4)
    (opencode_config / "service.json").write_text(
        json.dumps({"port": opencode_port}) + "\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith("VIBE_") or key == "PYTHONPATH" or key.startswith("XDG_"):
            environment.pop(key, None)
    # Ein geerbtes TMUX gewinnt in tmux gegen TMUX_TMPDIR. Ohne Entfernen
    # erreicht ein Test, der seinen tmux-Server aufräumt, den Server der
    # aufrufenden Sitzung und beendet Dashboard, opencode und laufende Läufe.
    for key in ("TMUX", "TMUX_PANE"):
        environment.pop(key, None)
    environment.update(
        {
            "HOME": str(home),
            "VIBE": str(vibe),
            "PYTHONUSERBASE": python_userbase,
            "TMPDIR": str(tmp),
            "TMUX_TMPDIR": str(tmux),
            "XDG_STATE_HOME": str(opencode_state),
            "VIBE_VERIFY_ROOT": str(base),
            "VIBE_VERIFY_SCREENSHOT_DIR": str(screenshots),
            "VIBE_UI_PORT": str(ui_port),
            "VIBE_OPENCODE_PORT": str(opencode_port),
            "VIBE_TEST_PORT": str(test_port),
            "VIBE_VERIFY_PORT": str(verify_port),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "OPENCODE_CONFIG_DIR": str(opencode_config),
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
        }
    )
    # Chromium ist eine installierte Entwicklungsabhängigkeit und wird nur
    # gelesen. Ohne diesen Pfad würde Playwright ihn im temporären HOME suchen.
    if Path(playwright_browsers).is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers
    return environment


def start_opencode_service(environment):
    """Startet den isolierten opencode-Dienst für schnelle Modellabfragen.

    Der Dienst läuft mit temporärem HOME, Konfigurations- und Statusverzeichnis.
    Er listet nur Modelle; es werden keine Modell- oder MCP-Werkzeuge aufgerufen.
    Fehlt opencode oder startet der Dienst nicht, läuft die Prüfung ohne ihn
    weiter (die Modellwarnungen entfallen dann).
    """
    if shutil.which("opencode") is None:
        return False
    try:
        subprocess.run(
            ["opencode", "service", "start"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    port = int(environment["VIBE_OPENCODE_PORT"])
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def stop_opencode_service(environment):
    if shutil.which("opencode") is None:
        return
    try:
        subprocess.run(
            ["opencode", "service", "stop"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def required_test_files(root, specs):
    missing = []
    for spec in specs:
        candidate = root / spec
        if any(char in spec for char in "*?["):
            paths = [Path(item) for item in glob.glob(str(candidate), recursive=True)]
        elif candidate.is_dir():
            paths = [path for path in candidate.rglob("*") if path.is_file()]
        elif candidate.is_file():
            paths = [candidate]
        else:
            paths = []
        matches = [path for path in paths if "test" in path.name.lower()]
        if not matches:
            missing.append(spec)
    return missing


def stream_process(argv, root, environment, log):
    """Führt eine Argumentliste ohne Shell aus und reicht die Ausgabe durch."""
    rendered = " ".join(shlex.quote(str(arg)) for arg in argv)
    log.write("$ " + rendered + "\n")
    sys.stdout.write("$ " + rendered + "\n")
    sys.stdout.flush()
    process = subprocess.Popen(
        argv,
        cwd=str(root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    chunks = []
    if process.stdout is None:
        return process.wait(), ""
    for line in process.stdout:
        chunks.append(line)
        log.write(line)
        sys.stdout.write(line)
        if not line.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    return process.wait(), "".join(chunks)


def run_command(command, root, environment, log):
    """Führt einen konfigurierten Shell-Befehl (VERIFY_QUICK) aus."""
    log.write(f"$ {command}\n")
    sys.stdout.write(f"$ {command}\n")
    sys.stdout.flush()
    process = subprocess.Popen(
        ["bash", "-c", command],
        cwd=str(root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    chunks = []
    if process.stdout is None:
        return process.wait(), ""
    for line in process.stdout:
        chunks.append(line)
        log.write(line)
        sys.stdout.write(line)
        if not line.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    return process.wait(), "".join(chunks)


def guard_self_reference(command, variable):
    """Verweigert Prüfbefehle, die auf die eigenen Skripte zeigen (B1)."""
    for token in shlex.split(command):
        base = os.path.basename(token)
        if base in SELF_BASENAMES:
            fail(
                EXIT_CONFIG,
                f"{variable} enthält einen Selbstaufruf der Prüfung "
                f"(Token '{token}'). Rekursionsschutz: Prüfbefehle dürfen nicht "
                "auf verify.sh, verify.py oder verify_engine.py zeigen "
                "(Rekursionsfalle B1). "
                f"Richtige Einrichtung: {variable} auf den statischen "
                "Prüfbefehl des Projekts setzen.",
            )


def parse_depth(raw):
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------- Baseline


def normalize_message(message):
    """Entfernt absolute Pfade, Zeilennummern und Zeitangaben aus einer Meldung."""
    text = message or ""
    text = re.sub(r"(?:^|[\s\"'])/[A-Za-z0-9_./\-]+", " <pfad>", text)
    text = re.sub(r"[A-Za-z]:\\[^\s]+", "<pfad>", text)
    text = re.sub(r"\bline\s+\d+\b", "line <n>", text)
    text = re.sub(r"\b\d+:\d+\b", "<zeile>", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<datum>", text)
    text = re.sub(r"\b\d+\.\d+s\b", "<zeit>", text)
    return text.strip()


def failure_signature(module, error_class, error_message):
    normalized = normalize_message(error_message)
    payload = module + "\n" + (error_class or "") + "\n" + normalized
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_baseline(path, required=False):
    """Lädt und validiert eine Baseline (Schema v1); fehlend → ``None``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        if required:
            fail(EXIT_CONFIG, f"Baseline-Datei {path} fehlt.")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        fail(EXIT_CONFIG, f"Baseline-Datei {path} ist kein gültiges JSON: {error}")
    if not isinstance(data, dict) or data.get("version") != 1:
        fail(
            EXIT_CONFIG,
            f"Baseline-Datei {path} entspricht nicht Schema v1 "
            "(Feld 'version' muss 1 sein).",
        )
    min_tests = data.get("min_tests")
    if not isinstance(min_tests, int) or isinstance(min_tests, bool) or min_tests < 1:
        fail(
            EXIT_CONFIG,
            f"Baseline-Datei {path}: 'min_tests' muss eine positive ganze "
            "Zahl sein.",
        )
    envs = data.get("envs")
    if not isinstance(envs, dict):
        fail(EXIT_CONFIG, f"Baseline-Datei {path}: 'envs' muss eine Map sein.")
    return {"min_tests": min_tests, "envs": envs}


def select_failures(ordered_sources, label):
    """Erste Quelle mit Sektion für das Label gilt exklusiv (D1)."""
    if label is not None:
        for name, data in ordered_sources:
            if label in data["envs"]:
                section = data["envs"][label]
                failures = section.get("failures", []) if isinstance(section, dict) else []
                return name, failures
    return None, []


def known_signature(failures, module, signature):
    for entry in failures:
        if not isinstance(entry, dict):
            continue
        if entry.get("module") == module and entry.get("signature") == signature:
            return True
    return False


def write_local_baseline(root, label, failures, new_min, existing):
    """Schreibt/aktualisiert die lokale ``.vibe/verify-baseline``."""
    data = existing if existing is not None else {"version": 1, "min_tests": 1, "envs": {}}
    data["version"] = 1
    data["min_tests"] = new_min
    envs = data.setdefault("envs", {})
    if label is not None:
        envs[label] = {"failures": failures}
    path = root / ".vibe" / "verify-baseline"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def configured_min_tests(values, args):
    if args["min_tests"] is not None:
        return parse_int(args["min_tests"], "--min-tests", EXIT_USAGE)
    raw = values.get("VERIFY_MIN_TESTS", "1").strip() or "1"
    return parse_int(raw, "VERIFY_MIN_TESTS", EXIT_CONFIG)


def resolve_jobs(values, args):
    raw = args["jobs"] if args["jobs"] is not None else values.get("VERIFY_JOBS", "").strip() or None
    if raw is None:
        return None
    return parse_int(raw, "--jobs/VERIFY_JOBS", EXIT_USAGE)


def resolve_timeout(args):
    if args["timeout"] is None:
        return None
    return parse_int(args["timeout"], "--timeout", EXIT_USAGE)


def make_temp_base():
    # T-V2: kurzer Präfix; VIBE_VERIFY_TMP legt den Elternordner fest.
    tmp_parent = os.environ.get("VIBE_VERIFY_TMP")
    if tmp_parent:
        parent = Path(tmp_parent)
        try:
            parent.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=str(parent)))
        except OSError as error:
            fail(EXIT_CONFIG, "VIBE_VERIFY_TMP ist nicht nutzbar: " + str(error))
    return Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))


# ------------------------------------------------------------- Modi


def runner_command(specs, jobs, timeout, report_path):
    argv = [sys.executable, str(TEST_RUNNER)]
    for spec in specs:
        argv += ["--dir", spec]
    if jobs is not None:
        argv += ["--jobs", str(jobs)]
    if timeout is not None:
        argv += ["--timeout", str(timeout)]
    argv += ["--report", str(report_path)]
    return argv


def read_report(base):
    path = base / "report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    modules = data.get("modules") if isinstance(data, dict) else None
    if not isinstance(modules, list):
        return None
    failed = [entry for entry in modules if isinstance(entry, dict) and not entry.get("passed")]
    total = data.get("total_tests", 0)
    return total, failed


def real_failures(failed_modules):
    """Nur Module mit tatsächlich ausgeführten, fehlgeschlagenen Tests.

    Ein Modul ohne ausgeführte Tests (``Ran 0 tests``/Importfehler) ist kein
    Fehlschlag im Sinne der Baseline, sondern ein fehlender Testnachweis.
    """
    return [entry for entry in failed_modules if (entry.get("tests") or 0) > 0]


def run_quick(args, root, env_file, values, tools, environment, log):
    command = values.get("VERIFY_QUICK", "").strip()
    if not command:
        fail(EXIT_CONFIG, f"VERIFY_QUICK fehlt in {env_file}.")
    if "TODO" in command:
        fail(
            EXIT_CONFIG,
            f"VERIFY_QUICK ist in {env_file} noch ein Platzhalter (TODO) und "
            "kein Prüfbefehl.",
        )
    guard_self_reference(command, "VERIFY_QUICK")
    status, _output = run_command(command, root, environment, log)
    if status != 0:
        fail(
            EXIT_CHECK,
            f"Prüfbefehl ist fehlgeschlagen (Befehl-Exit {status}, "
            f"Prüf-Exit {EXIT_CHECK}).",
        )


def proof_specs(args, values, key):
    return args["tests"] if args["tests"] else shlex.split(values.get(key, "").strip())


def require_test_structure(root, specs, key, env_file):
    if not specs:
        fail(
            EXIT_TESTS,
            f"{key} fehlt in {env_file}. Ohne Teststruktur ist der "
            "Testnachweis unvollständig.",
        )
    missing = required_test_files(root, specs)
    if missing:
        fail(
            EXIT_TESTS,
            "Keine Testdateien gefunden für: " + ", ".join(missing) + f" ({key}).",
        )


def run_test_runner(specs, jobs, timeout, root, environment, log, base):
    argv = runner_command(specs, jobs, timeout, base / "report.json")
    status, _output = stream_process(argv, root, environment, log)
    return status


def run_package(args, root, env_file, values, tools, environment, log, base):
    run_quick(args, root, env_file, values, tools, environment, log)
    package_specs = proof_specs(args, values, "VERIFY_PACKAGE_TESTS")
    if not package_specs:
        return
    require_test_structure(root, package_specs, "VERIFY_PACKAGE_TESTS", env_file)
    jobs = resolve_jobs(values, args)
    timeout = resolve_timeout(args)
    run_test_runner(package_specs, jobs, timeout, root, environment, log, base)
    report = read_report(base)
    if report is None:
        fail(EXIT_CHECK, "Prüfbefehl lieferte kein auswertbares Ergebnis.")
    total, failed_modules = report
    failures = real_failures(failed_modules)
    if failures:
        names = ", ".join(str(entry.get("module")) for entry in failures)
        fail(
            EXIT_CHECK,
            f"Testlauf ist fehlgeschlagen: {names} (Prüf-Exit {EXIT_CHECK}).",
        )
    minimum = configured_min_tests(values, args)
    if total < minimum:
        fail(
            EXIT_TESTS,
            f"Nur {total} ausgeführte Tests erkannt, Minimum {minimum}. "
            "Fehlende Tests sind kein bestandener Nachweis.",
        )
    print(f"OK: Tests erkannt: {total} (Minimum {minimum}).")


def run_full(args, root, env_file, values, tools, environment, log, base):
    # VERIFY_FULL wird von der Engine nicht gelesen; Hinweis statt Fehler.
    verify_full = values.get("VERIFY_FULL", "").strip()
    if verify_full:
        print(
            "HINWEIS: VERIFY_FULL wird von der Prüfung nicht gelesen und nur "
            "vom Läufer verbatim als verify.sh-Wrapper ausgeführt."
        )
    specs = proof_specs(args, values, "VERIFY_TESTS")
    require_test_structure(root, specs, "VERIFY_TESTS", env_file)

    label = args["env"] if args["env"] is not None else values.get("VERIFY_ENV", "").strip() or None

    # Baselines laden (Fehlvergleich: Präzedenz --baseline > lokal > committed).
    ordered_sources = []
    if args["baseline"]:
        ordered_sources.append(("baseline", load_baseline(Path(args["baseline"]).expanduser(), required=True)))
    local_path = root / ".vibe" / "verify-baseline"
    local_data = load_baseline(local_path)
    if local_data is not None:
        ordered_sources.append(("local", local_data))
    committed_path = root / "tests" / "verify-baseline.json"
    committed_data = load_baseline(committed_path)
    if committed_data is not None:
        ordered_sources.append(("committed", committed_data))

    # min_tests-Ratchet: Maximum über alle Quellen (D1, unabhängig vom Vergleich).
    minimum = configured_min_tests(values, args)
    for _name, data in ordered_sources:
        minimum = max(minimum, data["min_tests"])

    jobs = resolve_jobs(values, args)
    timeout = resolve_timeout(args)
    run_test_runner(specs, jobs, timeout, root, environment, log, base)
    report = read_report(base)
    if report is None:
        fail(EXIT_CHECK, "Prüfbefehl lieferte kein auswertbares Ergebnis.")
    total, failed_modules = report

    source_name, baseline_failures = select_failures(ordered_sources, label)

    failures = []
    for entry in real_failures(failed_modules):
        failures.append(
            {
                "module": entry.get("module"),
                "class": entry.get("error_class"),
                "signature": failure_signature(
                    entry.get("module"), entry.get("error_class"), entry.get("error_message")
                ),
            }
        )

    regressions = []
    for failure in failures:
        if not known_signature(baseline_failures, failure["module"], failure["signature"]):
            regressions.append(failure)

    baseline_ok = bool(failures) and not regressions

    if failures:
        if regressions:
            if source_name is None:
                print(
                    "FEHLT: Umgebungs-Label passt zu keiner Baseline-Sektion "
                    "(Mismatch); jeder Fehlschlag zählt als Regression. "
                    "Neuaufbau: --write-baseline."
                )
            for failure in regressions:
                print(
                    f"Neue Regression: {failure['module']} "
                    f"({failure['class'] or 'unbekannt'}, {failure['signature']})."
                )
            if len(regressions) < len(failures):
                for failure in failures:
                    if failure not in regressions:
                        print(f"Bekannt rot: {failure['module']}.")
        else:
            print("BASELINE-OK: bekannte fehlgeschlagene Module:")
            for failure in failures:
                print(f"  {failure['module']}")

    parts = [f"mode=full", f"tests={total}", f"failed_modules={len(failures)}"]
    if baseline_ok:
        parts.append("baseline_ok=1")
        if label is not None:
            parts.append(f"env={label}")
    print("VERIFY_RESULT: " + " ".join(parts))

    if args["write_baseline"]:
        # D2: --write-baseline ändert das Laufurteil nicht; nur der lokale,
        # unversionierte Vorschlag wird geschrieben.
        requested = configured_min_tests(values, args)
        existing_min = local_data["min_tests"] if local_data is not None else 1
        if requested < existing_min:
            fail(
                EXIT_CONFIG,
                "Senkung von min_tests abgelehnt: "
                f"{requested} ist kleiner als die bestehende Schwelle "
                f"{existing_min}. Die Baseline ist monoton (Ratchet).",
            )
        committed_warn = committed_data["envs"] if committed_data is not None else {}
        if label is not None and label in committed_warn:
            current_modules = {failure["module"] for failure in failures}
            for entry in committed_warn[label].get("failures", []):
                if isinstance(entry, dict) and entry.get("module") not in current_modules:
                    print(
                        f"HINWEIS: Modul {entry.get('module')} steht in der "
                        "committed Baseline und ist jetzt grün; der Eintrag ist "
                        "per Review aus der kanonischen Baseline zu entfernen."
                    )
        write_local_baseline(root, label, failures, minimum, local_data)
        print(
            "HINWEIS: .vibe/verify-baseline wurde als lokaler, unversionierter "
            "Vorschlag geschrieben. Kanonisch wird die Baseline ausschließlich "
            "über einen geprüften Merge-Request."
        )

    if regressions:
        return EXIT_REGRESSION
    if total < minimum:
        fail(
            EXIT_TESTS,
            f"Nur {total} ausgeführte Tests erkannt, Minimum {minimum}. "
            "Fehlende Tests sind kein bestandener Vollnachweis.",
        )
    return EXIT_OK


# ------------------------------------------------------------- Hauptablauf


def main(argv=None):
    base = None
    mode = None
    args = None
    try:
        args = parse_args(list(sys.argv[1:] if argv is None else argv))
        mode = args["mode"]
        depth = parse_depth(os.environ.get("VIBE_VERIFY_DEPTH", "0"))
        if depth >= 2:
            fail(
                EXIT_CONFIG,
                f"Rekursion erkannt: VIBE_VERIFY_DEPTH={depth} ist zu tief "
                "(≥ 2). Die Prüfung ruft sich selbst auf; der Lauf wird "
                "abgebrochen.",
            )
        root = project_root(args["project"])
        env_file = root / ".vibe" / "project.env"
        values = read_project_env(env_file)
        tools = check_tools(values)

        base = make_temp_base()
        environment = prepare_environment(base)
        environment["VIBE_VERIFY_DEPTH"] = str(depth + 1)
        service_started = (
            start_opencode_service(environment) if mode == "full" else False
        )
        try:
            print(f"=== vibe-Prüfung: {mode} ===")
            print(f"Projekt: {root}")
            print(f"Prüfverzeichnis: {base}")
            if tools:
                print("Werkzeuge: " + " ".join(tools))
            sys.stdout.flush()

            with (base / "verify.log").open("w", encoding="utf-8") as log:
                log.write(f"Modus: {mode}\nProjekt: {root}\n")
                if mode == "quick":
                    run_quick(args, root, env_file, values, tools, environment, log)
                elif mode == "package":
                    run_package(args, root, env_file, values, tools, environment, log, base)
                elif mode == "full":
                    full_result = run_full(args, root, env_file, values, tools, environment, log, base)
        finally:
            if service_started:
                stop_opencode_service(environment)
    except VerifyError as error:
        print(f"FEHLT: {error.message}", file=sys.stderr)
        if error.code == EXIT_USAGE:
            print(USAGE, file=sys.stderr)
        if base is not None:
            print(f"Prüfverzeichnis behalten: {base}", file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        message = "FEHLT: Prüfung abgebrochen."
        if base is not None:
            message += f" Prüfverzeichnis behalten: {base}"
        print(message, file=sys.stderr)
        return EXIT_INTERNAL

    result = full_result if mode == "full" else EXIT_OK
    if args["keep"]:
        print(f"Prüfverzeichnis behalten: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
        print(f"Prüfverzeichnis entfernt: {base}")
    if result == EXIT_OK:
        print(f"OK: Prüfung '{mode}' erfolgreich. (Exit {result})")
    else:
        print(
            f"FEHLT: Prüfung '{mode}' ergab neue Regressionen gegenüber der "
            f"Baseline. (Exit {result})",
            file=sys.stderr,
        )
    return result


if __name__ == "__main__":
    sys.exit(main())
