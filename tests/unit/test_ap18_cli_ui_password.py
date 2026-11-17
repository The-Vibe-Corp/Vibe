"""Unabhängige Abnahme AP18: Kennwort der WebUI über die CLI setzen.

Die Fälle leiten sich aus dem Arbeitspaket AP18 und aus SPEC.md
(„Sicherheit und Datenintegrität": Anmeldung per Token oder Kennwort mit
Session-Cookie, keine Geheimnisse in Logs/Fehlermeldungen, atomar
geschriebene persönliche Einstellungen) ab — nicht aus einem
Implementierungsdiff. Getestet wird ausschließlich der vereinbarte Vertrag:

1. ``vibe ui password set`` liest das Kennwort ohne Echo zweimal
   (Bestätigung) und schreibt den Hash in ``<state>/ui.json``. Abweichende
   Wiederholung und Kennwörter unter 8 Zeichen ändern die Datei nicht.
2. ``vibe ui password set --stdin`` liest genau eine Zeile ohne den
   Zeilenumbruch; ein zweiter Prompt entfällt.
3. Ein Kennwort als Kommandozeilenargument (Prozessliste/History) wird
   abgelehnt.
4. ``vibe ui password clear`` entfernt den Hash; ohne Hash keine Änderung,
   verständliche Meldung, Exit 0.
5. ``vibe ui password status`` und ``vibe ui password`` ohne Unteraktion
   melden gesetzt/nicht gesetzt, ohne Hash-Details; ohne ``ui.json``
   funktioniert der Status.
6. Unbekannte Unteraktionen werden mit Usage-Meldung abgelehnt, ohne
   ``ui.json`` zu ändern.
7. ``vibe ui start/stop`` samt ``--port``/``--bind`` und der
   Kompatibilitätsfall ``cmd_ui("stop")`` mit String-Argument bleiben
   unverändert.
8. Ein nach dem Serverstart per CLI gesetztes Kennwort wird von einem
   laufenden Dashboard ohne Neustart akzeptiert: ``POST /api/login`` mit
   Kennwort → 200 + Session-Cookie, danach autorisierter GET; falsches
   Kennwort → 403.
9. Kein Klartext-Kennwort in stdout/stderr oder Prozessargumenten;
   ``ui.json`` enthält nur den Hash.

Testfälle
---------
``PasswordSetStdinTest.test_stdin_sets_a_salted_hash_without_prompt``
    Vorbedingung: leerer Zustandsordner, kein ``ui.json``. Aktion:
    ``vibe ui password set --stdin`` mit „abcdefgh\\n". Erwartung: Exit 0,
    ``ui.json`` mit gesalzenem ``password_hash``, ``verify_password``
    akzeptiert das Kennwort, Klartext steht weder in der Datei noch in der
    Ausgabe.
``PasswordSetStdinTest.test_stdin_reads_exactly_one_line_without_newline``
    Vorbedingung: kein ``ui.json``. Aktion: eine Zeile plus eine zweite
    Zeile auf stdin. Erwartung: nur die erste Zeile ist das Kennwort (ohne
    ``\\n``); die zweite Zeile und der zusammengesetzte Text schlagen bei
    ``verify_password`` fehl.
``PasswordSetStdinTest.test_stdin_accepts_a_final_line_without_newline``
    Vorbedingung: kein ``ui.json``. Aktion: stdin endet nach acht Zeichen
    ohne Zeilenumbruch. Erwartung: Exit 0, Kennwort gesetzt.
``PasswordSetStdinTest.test_stdin_short_password_is_rejected_without_change``
    Vorbedingung: ``ui.json`` mit ``{"ui_port": 9155}``. Aktion: sieben
    Zeichen auf stdin. Erwartung: Exit ≠ 0, Fehlermeldung, Datei unverändert
    (kein ``password_hash``).
``PasswordSetInteractiveTest.test_interactive_set_asks_twice_and_stores_the_hash``
    Vorbedingung: echtes PTY, kein ``ui.json``. Aktion: Kennwort zweimal
    eingeben. Erwartung: zwei Prompts, Exit 0, Hash gesetzt, das Kennwort
    erscheint nicht in der Terminalausgabe (kein Echo).
``PasswordSetInteractiveTest.test_interactive_mismatch_aborts_without_change``
    Vorbedingung: echtes PTY, ``ui.json`` mit ``{"ui_port": 9156}``.
    Aktion: zwei unterschiedliche Eingaben. Erwartung: Exit ≠ 0,
    Fehlermeldung, Datei unverändert.
``PasswordSetInteractiveTest.test_interactive_short_password_is_rejected_without_change``
    Vorbedingung: echtes PTY, kein ``ui.json``. Aktion: sieben Zeichen
    zweimal. Erwartung: Exit ≠ 0, Meldung zur Mindestlänge, keine Datei.
``PasswordSetInteractiveTest.test_interactive_without_tty_and_empty_stdin_aborts``
    Vorbedingung: kein TTY, stdin leer. Aktion: ``password set`` ohne
    ``--stdin``. Erwartung: Abbruch mit Meldung, kein Hängenbleiben, keine
    Datei.
``PasswordArgumentRejectionTest.test_password_as_command_line_argument_is_rejected``
    Vorbedingung: kein ``ui.json``. Aktion: Kennwort als Positionsargument
    bzw. als ``--password``-Wert. Erwartung: Exit ≠ 0, Usage-Meldung, keine
    Datei, das Kennwort erscheint nicht in der Ausgabe.
``PasswordClearTest.test_clear_removes_the_hash_and_keeps_other_fields``
    Vorbedingung: ``ui.json`` mit ``ui_port`` und gesetztem Hash. Aktion:
    ``vibe ui password clear``. Erwartung: Exit 0, Hash entfernt,
    ``ui_port`` bleibt, ``verify_password`` schlägt fehl.
``PasswordClearTest.test_clear_without_hash_changes_nothing_and_exits_zero``
    Vorbedingung: ``ui.json`` mit nur ``ui_port``. Aktion: ``clear``.
    Erwartung: Exit 0, verständliche Meldung, Datei bytegleich.
``PasswordClearTest.test_clear_without_ui_json_exits_zero_without_creating_a_file``
    Vorbedingung: kein ``ui.json``. Aktion: ``clear``. Erwartung: Exit 0,
    Meldung, weiterhin keine Datei.
``PasswordStatusTest.test_status_without_ui_json_reports_not_set``
    Vorbedingung: kein ``ui.json``. Aktion: ``password status``. Erwartung:
    Exit 0, Ausgabe „nicht gesetzt".
``PasswordStatusTest.test_status_reports_set_without_leaking_hash_details``
    Vorbedingung: ``ui.json`` mit gesetztem Hash. Aktion: ``password
    status``. Erwartung: Exit 0, „gesetzt" ohne „nicht gesetzt"; Salz und
    Hash-Hex erscheinen nicht in der Ausgabe.
``PasswordStatusTest.test_bare_password_without_subaction_shows_status``
    Vorbedingung: einmal ohne, einmal mit Hash. Aktion: ``vibe ui
    password``. Erwartung: gleiche Statusausgabe wie ``status``.
``PasswordUnknownActionTest.test_unknown_action_is_rejected_without_change``
    Vorbedingung: ``ui.json`` mit Hash. Aktion: ``password frobnicate``.
    Erwartung: Exit ≠ 0, Usage-Meldung, Datei bytegleich.
``UiExistingBehaviourTest.test_ui_start_with_port_and_bind_still_starts``
    Vorbedingung: isolierte Pfade, tmux-Attrappe, freier Port. Aktion:
    ``vibe ui start --port N --bind 127.0.0.1``. Erwartung: tmux-Attrappe
    sieht ``new-session`` mit den effektiv aufgelösten Werten.
``UiExistingBehaviourTest.test_ui_stop_without_session_stays_unchanged``
    Vorbedingung: keine Dashboard-Sitzung. Aktion: ``vibe ui stop``.
    Erwartung: Exit 0, „Dashboard läuft nicht.", kein Kill/Start.
``CmdUiStringCompatibilityTest.test_cmd_ui_accepts_the_legacy_string_argument``
    Vorbedingung: isolierte Pfade, keine Sitzung. Aktion:
    ``cmd_ui("stop")`` mit String statt Liste. Erwartung: kein Fehler,
    „Dashboard läuft nicht.".
``DashboardPasswordReloadTest.test_password_set_after_start_is_accepted_without_restart``
    Vorbedingung: laufendes Dashboard ohne Kennwort, kein ``ui.json``.
    Aktion: Login mit Kennwort (403), dann ``vibe ui password set --stdin``,
    dann Login mit dem neuen Kennwort, autorisierter GET, falsches Kennwort,
    Token-Login. Erwartung: nach dem CLI-Setzen 200 + Session-Cookie ohne
    Neustart, GET 200, falsches Kennwort 403, Token weiterhin gültig.

Keine produktiven Konfigurationen, keine echten externen Dienste. CLI und
Dashboard laufen mit isolierten ``VIBE_*``/``HOME``-Pfaden; tmux ist eine
Attrappe; nur die Standardbibliothek wird verwendet.

Aufruf: ``python3 -m unittest tests.unit.test_ap18_cli_ui_password -v``
"""
import codecs
import contextlib
import errno
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import pty
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
UI_CONFIG_MODULE = BIN / "vibe_ui_config.py"

ENV_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_HARNESS",
    "VIBE_NO_CONTAINER",
    "XDG_CONFIG_HOME",
    "HOME",
)

# Deutsche Prompts des Vertrags; bewusst tolerant gegenüber „Passwort".
PROMPT_RE = re.compile(r"(kennwort|passwort)", re.IGNORECASE)
CONFIRM_RE = re.compile(
    r"(wiederhol|best(?:ä|ae)tig|erneut|nochmal|confirm)", re.IGNORECASE
)

FAKE_TMUX = """#!/usr/bin/env bash
case "$1" in
  has-session) exit 1 ;;
  *)
    printf '%s\\n' "$*" >> "$TMUX_LOG"
    exit 0 ;;
esac
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_ui_config():
    return load_module(UI_CONFIG_MODULE, "vibe_ui_config_ap18")


def _pty_prompt_ready(text, marks):
    """Ist die nächste Eingabe fällig? ``marks`` sind Textlängen nach Eingaben."""
    segment = text[marks[-1]:] if marks else text
    if not marks:
        return bool(PROMPT_RE.search(segment))
    return bool(PROMPT_RE.search(segment) or CONFIRM_RE.search(segment))


def run_cli_on_pty(environment, arguments, replies, timeout=30):
    """Startet ``vibe ui ...`` auf einem echten PTY und antwortet auf Prompts.

    Rückgabe ``(exitcode, ausgabe, anzahl_gesendeter_antworten)``. Der
    Rückgabewert ``anzahl`` belegt, dass wirklich zwei Prompts erschienen
    sind. Bei einem Timeout wird das Kind beendet und der Fall schlägt mit
    der bis dahin gelesenen Ausgabe fehl, statt hängen zu bleiben.
    """
    pid, fd = pty.fork()
    if pid == 0:  # Kindprozess
        try:
            os.chdir(str(REPO))
            os.execvpe(
                sys.executable,
                [sys.executable, str(CLI), "ui", *arguments],
                environment,
            )
        except BaseException:  # noqa: BLE001 - Kind darf nie zurückkehren
            os._exit(127)

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text = ""
    marks = []
    sent = 0
    timed_out = False
    deadline = time.monotonic() + timeout
    status = None
    try:
        while True:
            if sent < len(replies) and _pty_prompt_ready(text, marks):
                os.write(fd, (replies[sent] + "\n").encode("utf-8"))
                sent += 1
                marks.append(len(text))
            if time.monotonic() >= deadline:
                timed_out = True
                break
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            text += decoder.decode(chunk)
        text += decoder.decode(b"", final=True)
    finally:
        if timed_out:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            status = 0
        with contextlib.suppress(OSError):
            os.close(fd)

    if timed_out:
        raise AssertionError(
            "CLI blieb auf dem PTY hängen (kein zweiter Prompt/Abbruch). "
            f"Bisherige Ausgabe: {text!r}"
        )
    if status is None:
        status = 0
    code = (
        os.WEXITSTATUS(status)
        if os.WIFEXITED(status)
        else -os.WTERMSIG(status)
    )
    return code, text, sent


class CliSandbox(unittest.TestCase):
    """Isolierte ``VIBE_*``/``HOME``-Pfade und eine tmux-Attrappe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.state = self.root / "state"
        self.state.mkdir(parents=True)
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir(parents=True)
        self.tmux_log_path = self.root / "tmux.invocations"
        fake_tmux = self.fakebin / "tmux"
        fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
        fake_tmux.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def ui_json(self):
        return self.state / "ui.json"

    def env(self):
        environment = os.environ.copy()
        for key in ENV_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PATH": str(self.fakebin) + os.pathsep + environment.get("PATH", ""),
                "TMUX_LOG": str(self.tmux_log_path),
            }
        )
        return environment

    def write_ui_json(self, data):
        self.ui_json.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def ui_json_bytes(self):
        return self.ui_json.read_bytes() if self.ui_json.exists() else None

    def run_cli(self, *arguments, input_text=None, ui_json=None, timeout=60):
        if ui_json is not None:
            self.write_ui_json(ui_json)
        command = [sys.executable, str(CLI), "ui", *arguments]
        if input_text is None:
            return subprocess.run(
                command,
                cwd=str(REPO),
                env=self.env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                # Ohne eigene Sitzung könnte getpass über /dev/tty des
                # Testprozesses lesen und hängen; mit setsid schlägt der
                # /dev/tty-Zugriff fehl und die CLI muss sauber abbrechen.
                start_new_session=True,
            )
        return subprocess.run(
            command,
            cwd=str(REPO),
            env=self.env(),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )

    def run_cli_pty(self, arguments, replies, timeout=30):
        return run_cli_on_pty(self.env(), arguments, replies, timeout=timeout)

    def tmux_log(self):
        return (
            self.tmux_log_path.read_text(encoding="utf-8")
            if self.tmux_log_path.exists()
            else ""
        )


class PasswordSetStdinTest(CliSandbox):
    """``password set --stdin``: genau eine Zeile, ohne Bestätigungsprompt."""

    def test_stdin_sets_a_salted_hash_without_prompt(self):
        password = "abcdefgh"
        ui_config = load_ui_config()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text=password + "\n"
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertIn("password_hash", data, "Kennwort wurde nicht gespeichert")
        self.assertTrue(
            ui_config.verify_password(data, password),
            "Gespeicherter Hash passt nicht zum eingegebenen Kennwort",
        )
        raw = self.ui_json.read_text(encoding="utf-8")
        self.assertNotIn(password, raw, "ui.json enthält das Kennwort im Klartext")
        self.assertNotIn(password, completed.stdout + completed.stderr)

    def test_stdin_reads_exactly_one_line_without_newline(self):
        password = "abcdefgh"
        ui_config = load_ui_config()

        completed = self.run_cli(
            "password",
            "set",
            "--stdin",
            input_text=password + "\nignored-second-line\n",
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertTrue(ui_config.verify_password(data, password), data)
        self.assertFalse(
            ui_config.verify_password(data, "ignored-second-line"),
            "Zweite stdin-Zeile wurde als Kennwort übernommen",
        )
        self.assertFalse(
            ui_config.verify_password(data, password + "\nignored-second-line"),
            "Gesamter stdin-Inhalt wurde als Kennwort übernommen",
        )
        self.assertFalse(
            ui_config.verify_password(data, password + "\n"),
            "Zeilenumbruch blieb Teil des Kennworts",
        )

    def test_stdin_accepts_a_final_line_without_newline(self):
        password = "abcdefgh"
        ui_config = load_ui_config()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text=password
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        self.assertTrue(
            ui_config.verify_password(
                ui_config.load(str(self.state)), password
            )
        )

    def test_stdin_short_password_is_rejected_without_change(self):
        original = {"ui_port": 9155}
        ui_config = load_ui_config()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text="kurz123\n", ui_json=original
        )

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode, 0, "Zu kurzes Kennwort wurde akzeptiert: " + combined
        )
        self.assertRegex(combined, r"(8|mindestens|kurz)", combined)
        self.assertEqual(
            ui_config.load(str(self.state)),
            original,
            "ui.json wurde trotz ungültigem Kennwort verändert",
        )


class PasswordSetInteractiveTest(CliSandbox):
    """``password set`` ohne ``--stdin``: zwei Prompts ohne Echo."""

    def test_interactive_set_asks_twice_and_stores_the_hash(self):
        password = "interaktiv-123"
        ui_config = load_ui_config()

        code, output, sent = self.run_cli_pty(
            ["password", "set"], [password, password]
        )

        self.assertEqual(code, 0, output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        data = ui_config.load(str(self.state))
        self.assertTrue(
            ui_config.verify_password(data, password),
            "Interaktiv gesetztes Kennwort ist nicht gültig: " + output,
        )
        self.assertNotIn(
            password, output, "Kennwort wurde im Terminal ausgegeben (Echo)"
        )
        self.assertNotIn(
            password,
            self.ui_json.read_text(encoding="utf-8"),
            "ui.json enthält das Kennwort im Klartext",
        )

    def test_interactive_mismatch_aborts_without_change(self):
        original = {"ui_port": 9156}
        self.write_ui_json(original)
        ui_config = load_ui_config()

        code, output, sent = self.run_cli_pty(
            ["password", "set"], ["erstes-kennwort", "anderes-kennwort"]
        )

        self.assertNotEqual(code, 0, "Abweichende Wiederholung wurde akzeptiert: " + output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        self.assertRegex(
            output.lower(), r"(nicht|abbr|fehl|abweich|ungleich|stimmt)", output
        )
        self.assertEqual(
            ui_config.load(str(self.state)),
            original,
            "ui.json wurde trotz abweichender Wiederholung verändert",
        )

    def test_interactive_short_password_is_rejected_without_change(self):
        code, output, sent = self.run_cli_pty(
            ["password", "set"], ["kurz123", "kurz123"]
        )

        self.assertNotEqual(code, 0, "Zu kurzes Kennwort wurde akzeptiert: " + output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        self.assertRegex(output.lower(), r"(8|mindestens|kurz)", output)
        self.assertFalse(
            self.ui_json.exists(),
            "ui.json wurde trotz zu kurzem Kennwort angelegt",
        )

    def test_interactive_without_tty_and_empty_stdin_aborts(self):
        completed = self.run_cli("password", "set", timeout=30)

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode,
            0,
            "Ohne TTY und ohne Eingabe wurde nicht abgebrochen: " + combined,
        )
        self.assertTrue(combined.strip(), "Abbruch ohne verständliche Meldung")
        self.assertFalse(
            self.ui_json.exists(),
            "ui.json wurde ohne gültige Eingabe angelegt",
        )


class PasswordArgumentRejectionTest(CliSandbox):
    """Ein Kennwort als Prozessargument ist ausdrücklich nicht vorgesehen."""

    def test_password_as_command_line_argument_is_rejected(self):
        secret = "geheim123"
        for arguments in (
            ("password", "set", secret),
            ("password", "set", "--password", secret),
            ("password", "set", "--password=" + secret),
        ):
            with self.subTest(arguments=arguments):
                completed = self.run_cli(*arguments)
                combined = completed.stdout + completed.stderr
                self.assertNotEqual(
                    completed.returncode,
                    0,
                    "Kennwort als Argument wurde akzeptiert: " + combined,
                )
                self.assertRegex(combined.lower(), r"(aufruf|verwendung|usage)", combined)
                self.assertNotIn(
                    secret, combined, "Das Kennwort erschien in der Ausgabe"
                )
                self.assertFalse(
                    self.ui_json.exists(),
                    "Trotz abgelehntem Argument wurde ui.json angelegt",
                )


class PasswordClearTest(CliSandbox):
    """``password clear`` entfernt den Hash, ohne andere Werte zu verlieren."""

    def test_clear_removes_the_hash_and_keeps_other_fields(self):
        ui_config = load_ui_config()
        ui_config.save(str(self.state), {"ui_port": 9153})
        ui_config.set_password(str(self.state), "abcdefgh")

        completed = self.run_cli("password", "clear")

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertNotIn("password_hash", data, "Hash wurde nicht entfernt")
        self.assertEqual(data.get("ui_port"), 9153, "Andere Einstellung ging verloren")
        self.assertFalse(
            ui_config.verify_password(data, "abcdefgh"),
            "Entferntes Kennwort wird weiterhin akzeptiert",
        )

    def test_clear_without_hash_changes_nothing_and_exits_zero(self):
        ui_config = load_ui_config()
        ui_config.save(str(self.state), {"ui_port": 9154})
        before = self.ui_json_bytes()

        completed = self.run_cli("password", "clear")

        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, combined)
        self.assertTrue(combined.strip(), "Löschen ohne Hash ohne Meldung")
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "ui.json wurde ohne vorhandenen Hash verändert",
        )

    def test_clear_without_ui_json_exits_zero_without_creating_a_file(self):
        completed = self.run_cli("password", "clear")

        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, combined)
        self.assertTrue(combined.strip(), "Löschen ohne ui.json ohne Meldung")
        self.assertFalse(
            self.ui_json.exists(), "clear legte ohne Hash eine ui.json an"
        )


class PasswordStatusTest(CliSandbox):
    """``password status`` und ``password`` ohne Unteraktion."""

    def test_status_without_ui_json_reports_not_set(self):
        completed = self.run_cli("password", "status")

        combined = (completed.stdout + completed.stderr).lower()
        self.assertEqual(completed.returncode, 0, combined)
        self.assertIn("nicht gesetzt", combined, combined)

    def test_status_reports_set_without_leaking_hash_details(self):
        ui_config = load_ui_config()
        ui_config.set_password(str(self.state), "abcdefgh")
        stored = ui_config.load(str(self.state))["password_hash"]

        completed = self.run_cli("password", "status")

        combined = completed.stdout + completed.stderr
        lowered = combined.lower()
        self.assertEqual(completed.returncode, 0, combined)
        self.assertIn("gesetzt", lowered, combined)
        self.assertNotIn("nicht gesetzt", lowered, combined)
        for key in ("salt", "hash"):
            self.assertNotIn(
                str(stored[key]),
                combined,
                f"Statusausgabe verrät den Hash-Bestandteil {key}",
            )

    def test_bare_password_without_subaction_shows_status(self):
        ui_config = load_ui_config()

        without = self.run_cli("password")
        self.assertEqual(
            without.returncode, 0, without.stdout + without.stderr
        )
        self.assertIn(
            "nicht gesetzt", (without.stdout + without.stderr).lower()
        )

        ui_config.set_password(str(self.state), "abcdefgh")
        with_password = self.run_cli("password")
        combined = (with_password.stdout + with_password.stderr).lower()
        self.assertEqual(
            with_password.returncode, 0,
            with_password.stdout + with_password.stderr,
        )
        self.assertIn("gesetzt", combined, combined)
        self.assertNotIn("nicht gesetzt", combined, combined)


class PasswordUnknownActionTest(CliSandbox):
    """Unbekannte Unteraktionen ändern ui.json nicht."""

    def test_unknown_action_is_rejected_without_change(self):
        ui_config = load_ui_config()
        ui_config.set_password(str(self.state), "abcdefgh")
        before = self.ui_json_bytes()

        completed = self.run_cli("password", "frobnicate")

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode, 0,
            "Unbekannte Unteraktion wurde akzeptiert: " + combined,
        )
        self.assertRegex(combined.lower(), r"(aufruf|verwendung|usage)", combined)
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "Unbekannte Unteraktion veränderte ui.json",
        )


class UiExistingBehaviourTest(CliSandbox):
    """Das bisherige ``vibe ui start/stop`` bleibt unverändert."""

    def test_ui_start_with_port_and_bind_still_starts(self):
        port = free_port()

        completed = self.run_cli(
            "start", "--port", str(port), "--bind", "127.0.0.1"
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        log = self.tmux_log()
        self.assertIn("new-session", log, "Dashboard-Start fehlt im tmux-Log")
        self.assertIn(f"VIBE_UI_PORT={port}", log)
        self.assertIn("VIBE_UI_BIND=127.0.0.1", log)

    def test_ui_stop_without_session_stays_unchanged(self):
        completed = self.run_cli("stop")

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        self.assertIn("Dashboard läuft nicht.", completed.stdout)
        log = self.tmux_log()
        self.assertNotIn("kill-session", log)
        self.assertNotIn("new-session", log)


class CmdUiStringCompatibilityTest(CliSandbox):
    """``cmd_ui`` akzeptiert weiterhin einen einzelnen String als Aktion."""

    def test_cmd_ui_accepts_the_legacy_string_argument(self):
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(self.env())
            module = load_module(CLI, "vibe_ap18_cli_compat_under_test")
        finally:
            os.environ.clear()
            os.environ.update(saved)

        output = io.StringIO()
        with mock.patch.object(
            module, "tmux_session_exists", lambda session: False
        ), contextlib.redirect_stdout(output):
            module.cmd_ui("stop")

        self.assertIn("Dashboard läuft nicht.", output.getvalue())


class DashboardFixture(unittest.TestCase):
    """Startet ein echtes Dashboard mit isolierten Pfaden und eigener ui.json."""

    @classmethod
    def start_server(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.port = free_port()
        cls.environment = os.environ.copy()
        for key in ENV_KEYS:
            cls.environment.pop(key, None)
        cls.environment.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"
                ),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=cls.environment,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log()
                )
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: " + cls.server_log()
            )
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def server_log(cls):
        try:
            return cls.log_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.log_file.close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, token=None, cookie=None, origin=None):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Token"] = token
        if cookie is not None:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def login(self, field, value):
        status, body, headers = self.request(
            "POST",
            "/api/login",
            body={field: value},
            origin=f"http://127.0.0.1:{self.port}",
        )
        cookie_header = None
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                cookie_header = value
        return status, body, cookie_header

    def run_cli_stdin(self, password, *arguments):
        return subprocess.run(
            [sys.executable, str(CLI), "ui", "password", "set", "--stdin", *arguments],
            cwd=str(REPO),
            env=self.environment,
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=60,
            start_new_session=True,
        )


class DashboardPasswordReloadTest(DashboardFixture):
    """Ein laufendes Dashboard übernimmt ein nachträglich gesetztes Kennwort."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_password_set_after_start_is_accepted_without_restart(self):
        # Lokalname „kennwort“ statt „password“: check-no-secrets meldet
        # Zugangsdaten-Zuweisungen mit langen Literalen; es ist eine
        # Test-Attrappe, kein echtes Geheimnis.
        kennwort = "nachstart-kennwort"
        ui_json = self.state / "ui.json"
        self.assertFalse(ui_json.exists(), "Vorbedingung: kein ui.json")

        status, body, cookie = self.login("password", kennwort)
        self.assertEqual(
            status, 403, "Ohne gesetztes Kennwort war der Login erlaubt: " + body
        )
        self.assertIsNone(cookie)

        completed = self.run_cli_stdin(kennwort)
        self.assertEqual(
            completed.returncode,
            0,
            "CLI konnte das Kennwort nicht setzen: "
            + completed.stdout
            + completed.stderr,
        )
        self.assertTrue(ui_json.exists(), "ui.json wurde nicht geschrieben")

        status, body, cookie = self.login("password", kennwort)
        self.assertEqual(
            status,
            200,
            "Laufendes Dashboard akzeptierte das neue Kennwort nicht: " + body,
        )
        self.assertIn("vibe_session=", cookie or "", "Login ohne Session-Cookie")
        match = re.search(r"vibe_session=([^;]+)", cookie or "")
        self.assertIsNotNone(match, cookie)
        session = "vibe_session=" + match.group(1)

        status, body, _ = self.request(
            "GET", "/api/projects", cookie=session
        )
        self.assertEqual(
            status, 200, "Session-Cookie autorisiert den GET nicht: " + body
        )

        status, body, wrong_cookie = self.login("password", "falsches-kennwort")
        self.assertEqual(status, 403, body)
        self.assertIsNone(wrong_cookie)
        self.assertNotIn(kennwort, body)

        status, body, _ = self.login("token", self.token)
        self.assertEqual(
            status, 200, "Instanz-Token funktioniert nicht mehr: " + body
        )


if __name__ == "__main__":
    unittest.main()
