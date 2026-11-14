"""Unit-Abnahme F31: geerbtes OPENCODE_PASSWORD erreicht den Server nicht.

Defekt (Lauf vibe-20261114-192106-c11f59, reproduziert an opencode v2.3.0):
opencode ``serve`` steuert seinen Basic-Auth auch über die Umgebungsvariable
``OPENCODE_PASSWORD``, und ein gesetzter Wert schlägt
``OPENCODE_SERVER_PASSWORD``. Enthielt die Startumgebung des Paket-Läufers
(Dashboard/tmux-Kette) eine veraltete Belegung, erbte der private
Serverprozess diesen Wert und die Gesundheitsprüfung mit dem Kennwort aus
``$RUNTIME/opencode.password`` scheiterte dauerhaft mit 401 — der Lauf
brach mit „Der private opencode-Server konnte nicht gestartet werden“ ab.

Vereinbartes Verhalten (umsetzungsneutral):

* AK1: Die Umgebung des ``opencode serve``-Prozesses des privaten Servers
  enthält keine Belegung von ``OPENCODE_PASSWORD`` — auch dann nicht, wenn
  die Startumgebung des Läufers eine (veraltete) Belegung enthält.
  ``OPENCODE_SERVER_PASSWORD`` stammt unverändert aus der Kennwortdatei
  (B13-Verhalten).
* AK2: Ohne geerbtes ``OPENCODE_PASSWORD`` in der Startumgebung bleibt das
  B13-Verhalten vollständig unverändert.
* AK3: Derselbe Schutz gilt für den gemeinsamen Server-Start von ``bin/vibe``
  (``vibe server start``): Ein geerbtes ``OPENCODE_PASSWORD`` gelangt nicht
  in die Umgebung des Serverprozesses, den die tmux-Sitzung startet.
* AK4 (Geheimhygiene): Der Kennwortwert selbst (weder Datei- noch geerbter
  Wert) taucht in keinem Testartefakt/Record im Klartext auf; nur
  Anwesenheit/Länge.

Die opencode-Attrappe aus ``runner_support.py`` zeichnet je
``listening``-Ereignis nur Anwesenheit und Länge der beiden
Kennwortvariablen auf. AK3 wird mit echtem tmux auf isoliertem Socket
(TMUX_TMPDIR) und einer opencode-Attrappe geprüft, die ihre eigene Umgebung
aufzeichnet. Keine echten Modellaufrufe, kein echtes opencode, keine
produktive Installation, keine externen Dienste.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402
import test_b13_private_server_runner as b13  # noqa: E402

# Kennwort aus der Laufzeitdatei (B13-Verhalten): Length 15.
FILE_PASSWORD = b13.PASSWORD
# Veraltete geerbte Belegung aus der Startumgebung: andere Länge (18), damit
# ein vererbter Wert anhand der Länge vom Datei-Kennwort unterscheidbar ist.
STALE_PASSWORD = "veraltet-16zeichen"
# Kennwort für den gemeinsamen Server (AK3), deutlich länger als der
# geerbte Wert.
SHARED_PASSWORD = "gemeinsam-32-zeichen-kennwort-f31"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_jsonl(path):
    """Liest eine JSONL-Datei; fehlt sie, ist die Liste leer."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


class PrivateServerIgnoresInheritedPasswordTest(b13.B13RunnerFixture):
    """AK1/AK2: Der private Server erbt kein OPENCODE_PASSWORD."""

    def listening_entry(self):
        entries = self.listening_events()
        self.assertTrue(
            entries, "Der private Server lauschte nie: "
            + repr(self.serve_records()))
        return entries[0]

    def assert_health_checked_with_file_password(self):
        """Die Gesundheitsprüfung kam mit gültiger Anmeldung an."""
        health = [entry for entry in self.serve_records()
                  if entry.get("method") == "GET"
                  and "/api/info" in entry.get("path", "")]
        self.assertTrue(
            health, "Der Server wurde nie auf Gesundheit geprüft")
        self.assertTrue(
            any(entry.get("auth_ok") for entry in health),
            "Die Gesundheitsprüfung scheiterte: "
            + repr(health))

    def assert_no_password_leak(self):
        """AK4: Kein Kennwortwert im Klartext in den Testartefakten."""
        record = (self.serve_record.read_text(encoding="utf-8")
                  if self.serve_record.exists() else "")
        args = (self.args_file.read_bytes().decode("utf-8", "surrogateescape")
                if self.args_file.exists() else "")
        log = self.log_text()
        for label, text in (
            ("Serve-Record", record),
            ("opencode-Argumenten", args),
            ("Laufprotokoll", log),
        ):
            for name, value in (
                ("Datei-Kennwort", FILE_PASSWORD),
                ("geerbtes Kennwort", STALE_PASSWORD),
            ):
                self.assertNotIn(
                    value, text,
                    f"Der {name} ist im {label} gelandet")

    def test_inherited_opencode_password_is_absent_from_the_server_env(self):
        """AK1: Geerbtes OPENCODE_PASSWORD erreicht den privaten Server nicht.

        Vorbedingung: Kennwortdatei ``$RUNTIME/opencode.password`` nichtleer;
        die Startumgebung des Läufers enthält eine veraltete
        ``OPENCODE_PASSWORD``-Belegung; Attrappen zeichnen opencode-Aufrufe
        und Serve-Beobachtungen auf.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf läuft durch (FERTIG); genau ein ``serve``-Aufruf;
        im ``listening``-Record der Attrappe ist ``OPENCODE_PASSWORD``
        abwesend (present False, Länge 0), während
        ``OPENCODE_SERVER_PASSWORD`` vorhanden ist und exakt die Länge des
        Datei-Kennworts hat; die Gesundheitsprüfung (GET /api/info) wird mit
        gültiger Basic-Auth aus der Kennwortdatei beantwortet; der
        Agentenaufruf nutzt ``--server http://127.0.0.1:<Port>`` ohne
        ``--standalone``; kein Kennwortwert steht im Klartext in einem
        Artefakt (AK4).
        Fehlerfall: Die Attrappe beobachtet eine ``OPENCODE_PASSWORD``-
        Belegung in ihrer eigenen Umgebung oder der Lauf scheitert an der
        Gesundheitsprüfung.
        """
        self.write_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)
        env["OPENCODE_PASSWORD"] = STALE_PASSWORD

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der private Server-Prozess erbte ein OPENCODE_PASSWORD: "
            + repr({key: entry[key] for key in entry
                    if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines geerbten OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        bound_port = entry["port_bound"]
        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()

    def test_without_inherited_password_b13_behaviour_is_unchanged(self):
        """AK2: Ohne geerbtes OPENCODE_PASSWORD bleibt B13 unverändert.

        Vorbedingung: Kennwortdatei nichtleer; die Startumgebung enthält
        kein ``OPENCODE_PASSWORD``.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: wie B13: Lauf läuft durch (FERTIG), genau ein
        ``serve``-Aufruf, ``OPENCODE_PASSWORD`` abwesend im Serverprozess,
        ``OPENCODE_SERVER_PASSWORD`` mit Datei-Kennwort-Länge, Gesundheits-
        prüfung gültig, Agent mit ``--server`` ohne ``--standalone``.
        Fehlerfall: Abweichendes B13-Verhalten (Regression).
        """
        self.write_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Ohne Belegung in der Startumgebung tauchte OPENCODE_PASSWORD "
            "im Serverprozess auf")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        url = "http://127.0.0.1:" + str(entry["port_bound"])
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()

    def define_project_env_password(self):
        """AK1b: Belegt OPENCODE_PASSWORD in der .vibe/project.env.

        Der Wert steht genau einmal in der Datei, in doppelten
        Anführungszeichen — so exportiert ``set -a; . file; set +a`` ihn,
        wie der Läufer die Projektdatei einliest. Der Baum wird neu
        committet, damit der Läufer an einem sauberen Stand startet.
        """
        env_file = self.project / ".vibe" / "project.env"
        self.assertTrue(env_file.exists())
        text = env_file.read_text(encoding="utf-8")
        line = 'OPENCODE_PASSWORD="' + STALE_PASSWORD + '"\n'
        self.assertNotIn("OPENCODE_PASSWORD=", text)
        env_file.write_text(text + line, encoding="utf-8")
        self.assertEqual(
            1, env_file.read_text(encoding="utf-8").count(line.strip()),
            "OPENCODE_PASSWORD muss genau einmal in der Projektdatei stehen")
        support.commit_all(self.project, "AK1b: Projektdatei belegt Kennwort")

    def test_project_env_opencode_password_is_absent_from_the_server_env(self):
        """AK1b: OPENCODE_PASSWORD aus .vibe/project.env erreicht den Server nicht.

        Vorbedingung: Kennwortdatei ``$RUNTIME/opencode.password`` nichtleer;
        die übergeordnete Prozessumgebung enthält KEIN ``OPENCODE_PASSWORD``;
        die ``.vibe/project.env`` des Testprojekts definiert
        ``OPENCODE_PASSWORD="<veralteter Attrappenwert>"`` (genau eine Zeile);
        Attrappen zeichnen opencode-Aufrufe und Serve-Beobachtungen auf.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf läuft durch (FERTIG); genau ein ``serve``-Aufruf;
        im ``listening``-Record der Attrappe ist ``OPENCODE_PASSWORD``
        abwesend (present False, Länge 0), während
        ``OPENCODE_SERVER_PASSWORD`` vorhanden ist und exakt die Länge des
        Datei-Kennworts hat; die Gesundheitsprüfung (GET /api/info) wird mit
        gültiger Basic-Auth aus der Kennwortdatei beantwortet; der
        Agentenaufruf nutzt ``--server http://127.0.0.1:<Port>`` ohne
        ``--standalone``; kein Kennwortwert steht im Klartext in einem
        Artefakt (AK4).
        Fehlerfall: Das späte Einlesen der Projektdatei exportiert den
        ``OPENCODE_PASSWORD``-Wert erneut und die Attrappe beobachtet eine
        Belegung in ihrer eigenen Umgebung, oder der Lauf scheitert an der
        Gesundheitsprüfung (401), weil der falsche Wert das Datei-Kennwort
        schlägt.
        """
        self.write_password()
        self.define_project_env_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der private Server-Prozess erhielt ein OPENCODE_PASSWORD aus "
            "der Projektdatei: "
            + repr({key: entry[key] for key in entry
                    if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines aus der Projektdatei exportierten "
            "OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        bound_port = entry["port_bound"]
        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()


# Attrappe des opencode-CLI für ``vibe server start`` (AK3): ``--version``
# antwortet wie die geprüfte Version; ``serve`` schreibt nur Anwesenheit und
# Länge der Kennwortvariablen in den Record (AK4: nie der Wert) und endet —
# die tmux-Sitzung beendet sich damit selbst.
FAKE_VIBE_OPENCODE = r"""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args and args[0] == "--version":
    print("opencode v2.1.4")
    sys.exit(0)
if args and args[0] == "serve":
    record = os.environ.get("FAKE_SERVE_RECORD", "")

    def password_shape(name):
        value = os.environ.get(name)
        return bool(value), (len(value) if value is not None else 0)

    op_present, op_len = password_shape("OPENCODE_PASSWORD")
    server_present, server_len = password_shape("OPENCODE_SERVER_PASSWORD")
    if record:
        with open(record, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": "listening",
                "opencode_password_present": op_present,
                "opencode_password_len": op_len,
                "server_password_present": server_present,
                "server_password_len": server_len,
            }, ensure_ascii=False) + "\n")
    sys.exit(0)
sys.stderr.write("unerwarteter Aufruf: %s\n" % " ".join(args))
sys.exit(2)
"""

FAKE_CURL_DEAD = """#!/usr/bin/env bash
exit 7
"""


class SharedServerIgnoresInheritedPasswordTest(unittest.TestCase):
    """AK3: ``vibe server start`` vererbt kein OPENCODE_PASSWORD.

    Echter tmux auf isoliertem Socket (TMUX_TMPDIR); die Attrappe des
    opencode-CLI zeichnet die eigene Umgebung auf. Der gemeinsame Server
    „startet“ mit einer Attrappe, die sich sofort beendet — die
    Gesundheitsprüfung bleibt unbeantwortet, der Startbefehl meldet das als
    „angestoßen“ und endet erfolgreich.
    """

    def setUp(self):
        if shutil.which("tmux") is None:
            raise unittest.SkipTest("tmux ist nicht verfügbar")
        self.tmp = tempfile.TemporaryDirectory(prefix="f31-server-",
                                               dir="/tmp/opencode")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.home.mkdir()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        # bash -lc der tmux-Kette liest ~/.bashrc; dort bleibt der PATH der
        # Attrappen erhalten, unabhängig von /etc/profile.
        (self.home / ".bashrc").write_text(
            "export PATH=" + str(self.fakebin) + ":$PATH\n", encoding="utf-8")
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        opencode = self.fakebin / "opencode"
        opencode.write_text(FAKE_VIBE_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)
        curl = self.fakebin / "curl"
        curl.write_text(FAKE_CURL_DEAD, encoding="utf-8")
        curl.chmod(0o755)
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte.
        self.tmux_dir.chmod(0o700)
        self.record = self.root / "serve.record.jsonl"
        (self.runtime / "opencode.password").write_text(
            SHARED_PASSWORD + "\n", encoding="utf-8")
        self.env = os.environ.copy()
        for key in ("TMUX", "TMUX_PANE"):
            self.env.pop(key, None)
        self.env.update({
            "HOME": str(self.home),
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.root / "_toolchain"),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "PATH": str(self.fakebin) + os.pathsep + self.env.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": self.env.get("TERM", "xterm"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENCODE_PASSWORD": STALE_PASSWORD,
            "FAKE_SERVE_RECORD": str(self.record),
        })

    def tearDown(self):
        # Nur der isolierte tmux-Server dieser Umgebung; die Attrappe endet
        # von selbst, es bleibt kein Serverprozess zurück.
        subprocess.run(
            ["tmux", "kill-server"], env=self.env,
            capture_output=True, text=True, timeout=30)

    def test_server_start_does_not_inherit_opencode_password(self):
        """AK3: Die tmux-Sitzung des gemeinsamen Servers erbt nichts.

        Vorbedingung: Kennwortdatei in der Laufzeit nichtleer; die
        Startumgebung von ``vibe server start`` enthält eine veraltete
        ``OPENCODE_PASSWORD``-Belegung; echte tmux-Sitzung auf isoliertem
        Socket; die opencode-Attrappe zeichnet ihre Umgebung auf.
        Aktion: ``vibe server start``.
        Erwartung: Der Befehl endet erfolgreich; die tmux-Kette startete
        ``opencode serve`` (genau ein Record), dessen Umgebung kein
        ``OPENCODE_PASSWORD`` enthält (present False, Länge 0) und dessen
        ``OPENCODE_SERVER_PASSWORD`` die Kennwortdatei-Länge hat, nicht die
        Länge des geerbten Werts; kein Kennwortwert steht im Klartext in
        Record oder Ausgabe (AK4).
        Fehlerfall: Die Attrappe beobachtet eine ``OPENCODE_PASSWORD``-
        Belegung in ihrer Umgebung.
        """
        result = subprocess.run(
            [sys.executable, str(CLI), "server", "start"],
            env=self.env, cwd=str(self.root),
            capture_output=True, text=True, timeout=120)

        self.assertEqual(
            result.returncode, 0, "vibe server start bricht ab:\n"
            + result.stdout + result.stderr)
        deadline = time.time() + 5
        while not self.record.exists() and time.time() < deadline:
            time.sleep(0.1)
        entries = read_jsonl(self.record)
        self.assertEqual(
            1, len(entries),
            "Genau ein opencode-serve-Aufruf erwartet: " + repr(entries))
        entry = entries[0]
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der Serverprozess der tmux-Sitzung erbte ein "
            "OPENCODE_PASSWORD: " + repr({key: entry[key] for key in entry
                                          if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines geerbten OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(SHARED_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")
        self.assertNotEqual(
            len(STALE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stimmt mit dem geerbten Wert überein")

        raw = self.record.read_text(encoding="utf-8")
        out = result.stdout + result.stderr
        for name, value in (
            ("Datei-Kennwort", SHARED_PASSWORD),
            ("geerbtes Kennwort", STALE_PASSWORD),
        ):
            self.assertNotIn(
                value, raw,
                f"Der {name} ist im Serve-Record gelandet")
            self.assertNotIn(
                value, out,
                f"Der {name} ist in der Befehlsausgabe gelandet")


if __name__ == "__main__":
    unittest.main()
