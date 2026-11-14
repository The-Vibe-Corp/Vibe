"""Unit-Abnahme F24: Die Subagenten-API nennt den aktuell arbeitenden Agenten.

Arbeitspaket F24 (FEEDBACK.md): "Ich möchte in der Ausgabemaske eines Projektes
immer sehen, welcher agent aktuell arbeitet." Die fachliche Quelle der
Agentennamens ist der Laufregister-Eintrag des Projekts
(``_logs/runs.json``, Feld ``agent``). Das Dashboard darf den Namen nicht
erfinden; ohne aktiven Lauf (kein Eintrag oder Eintrag beendet) enthält die
Antwort keinen Agentennamen.

Backend-Kontrakt: ``GET /api/subagents?name=proj`` (Token) antwortet bei
aktivem Registereintrag im Zustand ``starting``/``running`` zusätzlich mit
``agent`` = Agentname des Registers. Ohne aktiven Eintrag fehlt ``agent``
oder ist leer.

Testfälle (je AKbindung dokumentiert):
1. test_active_run_reports_the_registered_agent        [AK1: aktiven Agenten zeigen]
   Vorbedingung: Registereintrag ``state=running``, ``agent=vibe-agent``.
   Aktion: GET /api/subagents?name=proj mit Token.
   Erwartung: 200/ok, ``running`` ist True, ``agent`` == "vibe-agent".
   Fehlerfall: Status ungleich 200, ``running`` False oder ``agent`` falsch/leer.
2. test_starting_run_reports_the_registered_agent      [AK1]
   Wie 1, Registereintrag im Zustand ``starting`` (LIVE-Zustand).
3. test_the_newest_register_entry_decides              [AK1]
   Zwei Registereinträge (alt: ``halt-agent``, neu: ``vibe-agent``);
   der jüngste Eintrag gewinnt → ``agent`` == "vibe-agent".
4. test_finished_run_reports_no_agent                  [AK1]
   Registereintrag ``state=finished`` → ``running`` False, ``agent`` fehlt
   oder ist leer (""). Der Name darf nicht mehr angezeigt werden.
5. test_without_register_entry_no_agent_is_reported    [AK1]
   Kein Registereintrag → ``running`` False, ``agent`` fehlt oder leer.

Wird das echte Dashboard (bin/vibe-web.py) in einem isolierten VIBE-Root auf
einem freien Port gestartet (Vorlage: tests/unit/test_output_view_f19_api.py).
Es gibt keine Attrappen bezüglich des Kontrakts: Die fachliche Quelle (Lauf-
register) wird über das echte Werkzeug bin/vibe_runs.py beschrieben. Keine
echten Modellaufrufe, keine produktive Installation.
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ApiFixture(unittest.TestCase):
    """Startet das echte Dashboard im isolierten VIBE-Root (eigener Port,
    eigene HOME-/Laufzeitpfade, keine tmux-Sitzung) und beschreibt den
    Laufregister-Eintrag mit bin/vibe_runs.py — demselben Werkzeug der
    echten Läufer."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.log_dir = cls.root / "_logs"
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "HOME": str(cls.root / "home"),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
                "TMPDIR": str(cls.root / "tmp"),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        (cls.root / "tmp").mkdir(parents=True)
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.server_log.close()
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        # Sauberer Start je Testfall: kein Register, keine Zustandsdatei.
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        state = self.log_dir / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def write_register(self, agent=AGENT, state="running", key="proj"):
        """Vorbedingung Register: Eintrag mit bin/vibe_runs.py (keine Hand-
        nachbildung des Formats) — dieselbe Quelle wie ein echter Läufer."""
        # runs.json wurde in setUp geleert; jede Vorbedingung entsteht neu.
        result = subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.log_dir),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", key, "--agent", agent,
                "--state", state,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung Registereintrag fehlgeschlagen: "
            + result.stdout + result.stderr,
        )

    def get_subagents(self):
        """Fachliche Abfrage: GET /api/subagents mit Token (Header und
        t=-Parameter, wie die Oberfläche die Route aufrufen darf)."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {"X-Token": self.token}
        try:
            connection.request(
                "GET",
                "/api/subagents?name=proj&t=" + self.token,
                headers=headers,
            )
            response = connection.getresponse()
            body = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            return response.status, payload, body
        finally:
            connection.close()


class ActiveRunAgentTest(ApiFixture):
    """AK1: Solange ein Lauf aktiv ist, zeigt die Ausgabemaske den Agenten.
    Die API ist die fachliche Quelle des Namens für den Anzeigeteil."""

    def test_active_run_reports_the_registered_agent(self):
        self.write_register(agent=AGENT, state="running")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertTrue(
            data.get("running"),
            "Vorbedingung aktiver Lauf muss gemeldet werden: " + raw,
        )
        self.assertEqual(
            data.get("agent"), AGENT,
            "Die API muss den Agentennamen des Laufregisters melden: " + raw,
        )

    def test_starting_run_reports_the_registered_agent(self):
        # starting ist ebenfalls ein LIVE-Zustand (bin/vibe_runs.py).
        self.write_register(agent=AGENT, state="starting")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertTrue(data.get("running"), raw)
        self.assertEqual(data.get("agent"), AGENT, raw)

    def test_the_newest_register_entry_decides(self):
        self.write_register(agent="halt-agent", state="running")
        self.write_register(agent=AGENT, state="running")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertEqual(
            data.get("agent"), AGENT,
            "Der jüngste Registereintrag ist maßgeblich: " + raw,
        )


class InactiveRunAgentTest(ApiFixture):
    """AK1: Ohne aktiven Lauf wird kein Agentenname angezeigt."""

    def test_finished_run_reports_no_agent(self):
        self.write_register(agent=AGENT, state="finished")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertFalse(data.get("running"), raw)
        self.assertIn(
            data.get("agent", ""), (None, ""),
            "Ein beendeter Lauf darf keinen Agentennamen zeigen: " + raw,
        )

    def test_without_register_entry_no_agent_is_reported(self):
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertFalse(data.get("running"), raw)
        self.assertIn(
            data.get("agent", ""), (None, ""),
            "Ohne Register darf kein Agentenname erscheinen: " + raw,
        )


if __name__ == "__main__":
    unittest.main()
