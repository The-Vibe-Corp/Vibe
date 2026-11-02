#!/usr/bin/env python3
"""Host-Starter für das vibe-Dashboard (V-017).

Der Starter ist für den Start aus dem Bazzite-Startmenü gedacht:

* Läuft vibe auf dem konfigurierten Port, wird nur der Browser geöffnet.
* Läuft vibe nicht, wird der nötige Distrobox-Container über
  ``distrobox enter`` gestartet, das Dashboard gestartet, die Bereitschaft
  über ``/api/health`` abgewartet und danach der Browser geöffnet.
* Ein fremder Dienst auf dem Port wird nicht als vibe behandelt.
* Ein Dateischloss verhindert, dass Mehrfachklicks mehrere Dashboards starten.
* Fehler werden im bereinigten Laufzeitlog und über den Desktop-Notifier
  sichtbar gemacht. Das Zugangstoken wird nie protokolliert.

Wie der Rest von vibe verwendet der Starter nur die Python-Standardbibliothek.
Er führt Programme ausschließlich als Argumentliste aus (keine Shell) und
startet ohne ``start``/``stop`` keine Prozesse. Die eigentliche Dashboard-
und Containerlogik bleibt in ``bin/vibe``; der Starter ist die dünne
Host-Hülle für das Startmenü.
"""
import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Bazzite ist Linux
    fcntl = None

HERE = os.path.dirname(os.path.realpath(__file__))
# Der Starter wird entweder direkt aus scripts/ (Quellbaum) oder zusammen mit
# einer Kopie von vibe_paths.py im Benutzerdatenverzeichnis ausgeführt. In
# beiden Fällen muss dasselbe Pfadmodul importierbar sein.
for _candidate in (HERE, os.path.join(os.path.dirname(HERE), "bin")):
    if os.path.isfile(os.path.join(_candidate, "vibe_paths.py")):
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break

import vibe_paths

HEALTH_TIMEOUT = 2.0
START_TIMEOUT = 30.0
MAX_HEALTH_BYTES = 64 * 1024
TOKEN_URL_RE = re.compile(r"#t=[^\s\"'&]+")
TRUTHY = {"1", "true", "yes", "on"}
LOG_NAME = "desktop-starter.log"
LOCK_NAME = "desktop-starter.lock"


class StarterError(RuntimeError):
    """Verständlicher Fehler; der Starter endet mit Exitcode 1."""


class Outcome:
    """Ergebnis eines Starter-Laufs."""

    def __init__(self, state, url, detail=""):
        self.state = state
        self.url = url
        self.detail = detail

    def __repr__(self):
        return f"Outcome(state={self.state!r}, url={self.url!r})"


def health_url(paths):
    return f"http://{paths.ui_bind}:{paths.ui_port}/api/health"


def base_url(paths):
    return f"http://{paths.ui_bind}:{paths.ui_port}/"


def dashboard_url(paths, token):
    return f"{base_url(paths)}#t={token}"


def runtime_file(paths, name):
    return os.path.join(paths.runtime, name)


def read_instance(paths):
    try:
        with open(runtime_file(paths, "web.instance"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def read_token(paths):
    try:
        with open(runtime_file(paths, "web.token"), encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def _truthy(value):
    return str(value or "").strip().lower() in TRUTHY


def in_container(environ=None):
    """Erkennt, ob der Starter bereits im Steuerungscontainer läuft."""
    environ = dict(os.environ if environ is None else environ)
    if _truthy(environ.get("VIBE_NO_CONTAINER")):
        return True
    if environ.get("container") or environ.get("DISTROBOX_ENTER_PATH"):
        return True
    return os.path.exists("/run/.containerenv") or os.path.exists("/.dockerenv")


def probe(url, opener=None, timeout=HEALTH_TIMEOUT):
    """Fragt einen Health-Endpunkt ab.

    Liefert ``("vibe"|"foreign"|"absent", daten)``. ``absent`` heißt: auf dem
    Port antwortet niemand. Alles, was antwortet, aber keine gültige
    vibe-Health-Antwort ist, gilt als ``foreign``.
    """
    opener = opener or urllib.request.urlopen
    try:
        with opener(url, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                try:
                    status = response.getcode()
                except AttributeError:
                    status = 200
            body = response.read(MAX_HEALTH_BYTES)
    except urllib.error.HTTPError as error:
        return "foreign", {"status": error.code}
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return "absent", None
    if status != 200:
        return "foreign", {"status": status}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "foreign", None
    if not isinstance(data, dict):
        return "foreign", data
    return "vibe", data


def resolve_state(paths, opener=None, url=None, timeout=HEALTH_TIMEOUT):
    """Klassifiziert den Dienst auf dem Dashboard-Port.

    Eine vibe-Health-Antwort zählt nur, wenn App-Kennung und Instanzkennung zur
    aktuellen Laufzeit passen. Eine fremde Anwendung oder eine andere
    vibe-Instanz auf demselben Port wird nicht übernommen.
    """
    state, data = probe(url or health_url(paths), opener=opener, timeout=timeout)
    if state != "vibe":
        return state, data
    if data.get("ok") is not True or data.get("app") != "vibe":
        return "foreign", data
    expected = read_instance(paths)
    # Ohne eine eigene Instanzkennung ist die Antwort nicht überprüfbar. Sie
    # wird deshalb nie als das eigene Dashboard übernommen.
    if not expected or data.get("instance") != expected:
        return "foreign", data
    return "vibe", data


def redact(text, token=None):
    """Entfernt Tokens aus Meldungen und Logzeilen."""
    cleaned = TOKEN_URL_RE.sub("#t=[entfernt]", str(text))
    if token:
        cleaned = cleaned.replace(str(token), "[entfernt]")
    return cleaned


def _call(runner, argv, timeout, environ):
    """Führt eine Argumentliste aus und übersetzt fehlende Programme/Timeouts."""
    try:
        return runner(argv, timeout=timeout, env=dict(environ))
    except FileNotFoundError as error:
        return subprocess.CompletedProcess(
            argv, 127, "", f"Programm nicht gefunden: {argv[0]} ({error})"
        )
    except PermissionError as error:
        return subprocess.CompletedProcess(
            argv, 126, "", f"Programm nicht ausführbar: {argv[0]} ({error})"
        )
    except OSError as error:
        return subprocess.CompletedProcess(
            argv, 126, "", f"Programm konnte nicht gestartet werden: {argv[0]} ({error})"
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv, 124, "", f"Zeitüberschreitung nach {timeout} s"
        )


def _output(completed):
    parts = []
    for name in ("stdout", "stderr"):
        value = getattr(completed, name, "") or ""
        if value.strip():
            parts.append(value.strip())
    return " | ".join(parts)


def run(argv, timeout=60, env=None):
    """Standardausführung ohne Shell; Argumente bleiben getrennt."""
    return subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def container_prefix(paths, environ, inside=None, which=None):
    """Argumente zum Betreten des konfigurierten Containers."""
    if inside is None:
        inside = in_container(environ)
    if inside:
        return []
    if which is not None and which("distrobox") is None:
        raise StarterError(
            "distrobox wurde nicht gefunden; der Container "
            f"{paths.container} kann nicht gestartet werden."
        )
    # --no-tty: Der Startmenüeintrag besitzt kein Terminal. Ohne diese Option
    # kann distrobox beim Start aus dem Desktop scheitern.
    return ["distrobox", "enter", "--no-tty", paths.container, "--", "env"]


def vibe_cli(paths):
    """Findet die vibe-CLI in der Installation oder im Quellbaum."""
    candidates = (
        os.path.join(paths.install, "bin", "vibe"),
        os.path.join(paths.code_bin, "vibe"),
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise StarterError(
        "vibe-Programm nicht gefunden; geprüft wurden "
        + ", ".join(candidates)
        + ". Zuerst vibe installieren oder die Pfade konfigurieren."
    )


def vibe_command(paths, arguments, environ, inside=None, which=None):
    """Baut den Aufruf der vibe-CLI für Host oder Container.

    Die aufgelösten Pfade und Ports werden als einzelne ``KEY=WERT``-Argumente
    an ``env`` übergeben. Leerzeichen und Sonderzeichen bleiben dadurch
    unverändert; keine Shell wertet den Befehl aus.
    """
    prefix = container_prefix(paths, environ, inside=inside, which=which)
    command = ["python3", vibe_cli(paths)] + list(arguments)
    if not prefix:
        return command
    exports = [f"{key}={value}" for key, value in paths.child_env().items()]
    return prefix + exports + command


def split_command(value):
    """Trennt eine konfigurierte Befehlszeile, ohne Pfade mit Leerzeichen zu zerlegen.

    Ein vorhandener ausführbarer Pfad gilt als ein Argument; andernfalls wird
    die Zeile wie eine Befehlszeile mit Optionen getrennt.
    """
    text = (value or "").strip()
    if not text:
        return []
    if os.path.isfile(text) and os.access(text, os.X_OK):
        return [text]
    return shlex.split(text)


def browser_command(environ):
    custom = (environ.get("VIBE_BROWSER") or "").strip()
    if custom:
        argv = split_command(custom)
        if not argv:
            raise StarterError("VIBE_BROWSER ist leer.")
        return argv
    browser = shutil.which("xdg-open")
    if browser is None:
        raise StarterError(
            "xdg-open wurde nicht gefunden; die Weboberfläche kann nicht "
            "geöffnet werden."
        )
    return [browser]


def open_browser(url, environ, runner):
    argv = browser_command(environ) + [url]
    completed = _call(runner, argv, 30, environ)
    if completed.returncode != 0:
        detail = _output(completed) or f"Exit-Code {completed.returncode}"
        raise StarterError(
            "Dashboard läuft, aber der Browser konnte nicht geöffnet werden: " + detail
        )


def notify_error(message, environ, runner, which=None):
    """Zeigt einen Fehler ohne Terminalfenster sichtbar an, soweit möglich."""
    custom = (environ.get("VIBE_NOTIFY") or "").strip()
    if custom:
        argv = split_command(custom) + [message]
    else:
        which = which or shutil.which
        if which("notify-send") is None:
            return False
        argv = ["notify-send", "vibe", message]
    _call(runner, argv, 10, environ)
    return True


def log_error(paths, message):
    """Schreibt eine bereinigte Fehlerzeile in das Laufzeitlog."""
    try:
        vibe_paths.ensure(paths, "runtime")
        target = runtime_file(paths, LOG_NAME)
        line = time.strftime("%Y-%m-%dT%H:%M:%S") + " FEHLER: "
        line += " | ".join(str(message).splitlines()) + "\n"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return target
    except (OSError, vibe_paths.ConfigError):
        return None


def log_line(paths, message):
    """Schreibt eine bereinigte Zustandszeile; Tokens werden entfernt."""
    try:
        vibe_paths.ensure(paths, "runtime")
        target = runtime_file(paths, LOG_NAME)
        line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + redact(message) + "\n"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return target
    except (OSError, vibe_paths.ConfigError):
        return None


@contextlib.contextmanager
def starter_lock(paths):
    """Serialisiert gleichzeitige Starter-Aufrufe je Laufzeitordner."""
    vibe_paths.ensure(paths, "runtime")
    path = runtime_file(paths, LOCK_NAME)
    with open(path, "a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)


def start(paths, environ=None, runner=None, opener=None, inside=None,
          sleeper=time.sleep, timeout=None, which=None):
    """Startet das Dashboard bei Bedarf und öffnet die Weboberfläche."""
    environ = dict(os.environ if environ is None else environ)
    runner = runner or run
    if timeout is None:
        raw = environ.get("VIBE_START_TIMEOUT", "")
        try:
            timeout = float(raw) if str(raw).strip() else START_TIMEOUT
        except ValueError:
            raise StarterError(f"VIBE_START_TIMEOUT ist keine Zahl: {raw!r}")
    if timeout <= 0:
        raise StarterError("VIBE_START_TIMEOUT muss größer als 0 sein.")

    with starter_lock(paths):
        state, _ = resolve_state(paths, opener=opener)
        if state == "vibe":
            token = read_token(paths)
            if not token:
                raise StarterError(
                    "Dashboard läuft, aber das Zugangstoken (Token) fehlt in "
                    + runtime_file(paths, "web.token")
                )
            url = dashboard_url(paths, token)
            log_line(paths, "Dashboard läuft bereits; Browser wird geöffnet.")
            open_browser(url, environ, runner)
            return Outcome("running", url)

        if state == "foreign":
            raise StarterError(
                f"Auf Port {paths.ui_port} antwortet ein fremder Dienst; "
                "es wurde nichts gestartet."
            )

        command = vibe_command(paths, ["ui", "start"], environ, inside=inside, which=which)
        completed = _call(runner, command, 60, environ)
        if completed.returncode != 0:
            detail = _output(completed) or f"Exit-Code {completed.returncode}"
            detail = redact(detail, read_token(paths))
            raise StarterError("Dashboard konnte nicht gestartet werden: " + detail)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state, _ = resolve_state(paths, opener=opener)
            if state == "vibe":
                break
            if state == "foreign":
                raise StarterError(
                    f"Auf Port {paths.ui_port} antwortet nach dem Start ein "
                    "fremder Dienst; es wurde nichts geöffnet."
                )
            sleeper(0.25)
        else:
            raise StarterError(
                f"Das Dashboard antwortet nach {timeout:.0f} Sekunden nicht. "
                "Log: " + runtime_file(paths, LOG_NAME)
            )

        token = read_token(paths)
        if not token:
            raise StarterError(
                "Das Dashboard läuft, aber das Zugangstoken fehlt in "
                + runtime_file(paths, "web.token") + "."
            )
        url = dashboard_url(paths, token)
        log_line(paths, "Dashboard gestartet; Browser wird geöffnet.")
        open_browser(url, environ, runner)
        return Outcome("started", url)


def stop(paths, environ=None, runner=None, inside=None, which=None, opener=None):
    """Beendet ausschließlich das vibe-Dashboard.

    Läuft kein Dashboard, wird nichts gestartet und kein Container betreten.
    Ein fremder Dienst auf dem Port wird nicht beendet.
    """
    environ = dict(os.environ if environ is None else environ)
    runner = runner or run
    state, _ = resolve_state(paths, opener=opener)
    if state == "absent":
        return Outcome("absent", base_url(paths), "Dashboard läuft nicht.")
    if state == "foreign":
        raise StarterError(
            f"Auf Port {paths.ui_port} antwortet ein fremder Dienst; "
            "es wurde nichts beendet."
        )
    command = vibe_command(paths, ["ui", "stop"], environ, inside=inside, which=which)
    completed = _call(runner, command, 60, environ)
    if completed.returncode != 0:
        detail = _output(completed) or f"Exit-Code {completed.returncode}"
        raise StarterError("Dashboard konnte nicht beendet werden: " + detail)
    log_line(paths, "Dashboard beendet.")
    return Outcome("stopped", base_url(paths), _output(completed))


def status(paths, opener=None):
    state, _ = resolve_state(paths, opener=opener)
    if state == "vibe":
        return Outcome("running", base_url(paths))
    if state == "foreign":
        return Outcome("foreign", base_url(paths))
    return Outcome("absent", base_url(paths))


def report_error(paths, message, environ=None, runner=None, which=None):
    """Macht einen Starterfehler sichtbar und liefert den bereinigten Text.

    Der Fehler wird bereinigt protokolliert, möglichst über den
    Desktop-Notifier angezeigt und auf stderr ausgegeben. Das Token gelangt
    weder in das Log noch in die Meldung.
    """
    environ = dict(os.environ if environ is None else environ)
    cleaned = redact(message, read_token(paths))
    log_error(paths, cleaned)
    try:
        notify_error(cleaned, environ, runner or run, which=which)
    except Exception:
        # Die Anzeige ist eine Zusatzhilfe; der Fehler wird auf jeden Fall auf
        # stderr ausgegeben und protokolliert.
        pass
    print("vibe: " + cleaned, file=sys.stderr)
    return cleaned


def _fail(paths, message):
    report_error(paths, message, which=shutil.which)
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="vibe-Dashboard starten oder beenden (Bazzite-Startmenü)"
    )
    parser.add_argument(
        "action", nargs="?", default="start", choices=("start", "stop", "status"),
        help="start (Standard), stop oder status",
    )
    args = parser.parse_args(argv)
    try:
        paths = vibe_paths.resolve()
    except vibe_paths.ConfigError as error:
        print("vibe: Pfadkonfiguration: " + str(error), file=sys.stderr)
        return 1

    try:
        if args.action == "start":
            outcome = start(paths, which=shutil.which)
            print(("vibe läuft: " if outcome.state == "running" else "vibe gestartet: ")
                  + base_url(paths))
        elif args.action == "stop":
            outcome = stop(paths, which=shutil.which)
            if outcome.state == "absent":
                print("vibe läuft nicht; nichts beendet.")
            else:
                print("vibe-Dashboard beendet.")
        else:
            outcome = status(paths)
            if outcome.state == "running":
                print("vibe läuft: " + base_url(paths))
            elif outcome.state == "foreign":
                print("Auf Port " + str(paths.ui_port) + " antwortet ein fremder Dienst.")
            else:
                print("vibe läuft nicht.")
    except (StarterError, vibe_paths.ConfigError) as error:
        return _fail(paths, str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
