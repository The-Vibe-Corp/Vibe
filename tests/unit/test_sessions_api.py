"""Sitzungs-API: Auflisten und Fortsetzen.

Aufruf: python3 -m unittest tests.unit.test_sessions_api -v
"""


# ===========================================================================
# Unit-Abnahme (Teil 4): Web-API des Session-Managements
# ===========================================================================

import http.client
import json
import os
import re
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

PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=test-agent\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)

ABORTED_SESSION = "ses_abgebrochen"
FINISHED_SESSION = "ses_fertig"
UNKNOWN_SESSION = "ses_unbekannt"
FOREIGN_SESSION = "ses_fremd"

# Aufzeichnende tmux-Attrappe: verhält sich wie ein frischer Server und
# protokolliert jeden Aufruf; ``new-session`` wird als Startbefehl geprüft.
FAKE_TMUX = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Ap19SessionsApiFixture(unittest.TestCase):
    """Dashboard, ein echtes Projekt, Session-/Laufregister und tmux-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP19 Session Management\n"
            "  Beschreibung: Test\n",
            encoding="utf-8",
        )
        cls.home = cls.root / "home"
        agents = cls.home / ".config" / "opencode" / "agents"
        agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8",
            )
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.runtime = cls.root / "_logs"
        cls.state_dir = cls.root / "_state"
        cls.runtime.mkdir()
        cls.state_dir.mkdir()
        (cls.root / "tmp").mkdir()
        cls.port = free_port()
        cls.env = cls.build_env()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=cls.env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.runtime / "web.token"
        deadline = time.time() + 20
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
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace")
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key.startswith(
                "SANDBOX"
            ) or key in ("TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.runtime),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_AGENTS_DIR": str(
                cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
            "HOME": str(cls.home),
            "XDG_CONFIG_HOME": str(cls.home / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(cls.tmux_log),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

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

    # ---------- Testzustand ----------

    def setUp(self):
        for path in (
            self.runtime / "sessions.json",
            self.runtime / "sessions.lock",
            self.runtime / "runs.json",
            self.runtime / "runs.lock",
            self.state_dir / "harness.json",
            self.tmux_log,
        ):
            path.unlink(missing_ok=True)

    # ---------- Seeds ----------

    def session(self, session, project=None, name="proj", run_id="",
                agent="vibe-agent", harness="opencode", first=100, last=100):
        return {
            "session": session,
            "project": str(Path(project or self.project).resolve()),
            "name": name,
            "run_id": run_id,
            "agent": agent,
            "harness": harness,
            "first_seen": int(first),
            "last_seen": int(last),
        }

    def seed_sessions(self, entries, limit=5):
        (self.runtime / "sessions.json").write_text(
            json.dumps({"limit": limit, "sessions": entries},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    def add_run(self, run_id, state):
        completed = subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.runtime),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", "proj", "--agent", "test-agent",
                "--session", "vibe-proj", "--id", run_id,
                "--state", state,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            0, completed.returncode,
            "Vorbedingung Laufregister fehlgeschlagen: "
            + completed.stdout + completed.stderr,
        )

    def select_pi(self):
        (self.state_dir / "harness.json").write_text(
            json.dumps({"harness": "pi"}) + "\n", encoding="utf-8")

    def seed_three_states(self):
        """Eine abgebrochene, eine abgeschlossene und eine unbekannte Session."""
        self.add_run("lauf-ab", "ended")
        self.add_run("lauf-ok", "finished")
        self.seed_sessions([
            self.session(ABORTED_SESSION, run_id="lauf-ab", first=100, last=300),
            self.session(FINISHED_SESSION, run_id="lauf-ok", first=100, last=200),
            self.session("ses_ohne_lauf", run_id="", first=100, last=100),
        ])

    def new_session_commands(self):
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def continue_exports(self):
        values = []
        for command in self.new_session_commands():
            values.extend(re.findall(
                r"VIBE_CONTINUE_SESSION=([^\s;\"']+)", command))
        return values

    # ---------- HTTP ----------

    def request(self, method, path, body=None, token=True):
        encoded = None
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is True:
            headers["X-Token"] = self.token
        elif isinstance(token, str):
            headers["X-Token"] = token
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        headers["Origin"] = f"http://127.0.0.1:{self.port}"
        headers["Sec-Fetch-Site"] = "same-origin"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            return response.status, payload, text
        finally:
            connection.close()

    def get_sessions(self, query="name=proj", token=True):
        return self.request("GET", "/api/sessions?" + query, token=token)

    def post_continue(self, session, name="proj", action="continue", token=True):
        return self.request(
            "POST", "/api/sessions",
            body={"name": name, "session": session, "action": action},
            token=token,
        )

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(
            payload.get("message")
            or (payload.get("error") or {}).get("message")
            or ""
        )

    def sessions_of(self, data):
        return list((data or {}).get("sessions") or [])

    def session_ids(self, data):
        return [entry.get("session") for entry in self.sessions_of(data)]


class SessionsListTest(Ap19SessionsApiFixture):
    """AK1/AK2: Auflistung, Zustandsableitung, Limit und Filter über die API."""

    def test_get_is_token_protected(self):
        """Ohne und mit falschem Token antwortet die API 403 und keine Daten."""
        status, data, raw = self.get_sessions(token=False)
        self.assertEqual(403, status, raw)
        self.assertEqual(
            "unauthorized", (data or {}).get("error", {}).get("code"), raw)
        status, data, raw = self.get_sessions(token="falsch")
        self.assertEqual(403, status, raw)

    def test_unknown_project_is_rejected(self):
        """Ein Projektname außerhalb der bekannten Projekte → 404."""
        status, data, raw = self.get_sessions(query="name=unbekannt")
        self.assertEqual(404, status, raw)
        self.assertFalse(self.ok_flag(data), raw)

    def test_list_returns_all_contract_fields_and_state_labels(self):
        """Jeder Eintrag trägt Registerfelder plus state/state_label; die
        Reihenfolge ist jüngste zuerst (last_seen absteigend)."""
        self.seed_three_states()

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertEqual(
            [ABORTED_SESSION, FINISHED_SESSION, "ses_ohne_lauf"],
            self.session_ids(data),
            f"Reihenfolge ist nicht jüngste zuerst: {raw}",
        )
        by_id = {entry["session"]: entry for entry in self.sessions_of(data)}
        expected_labels = {
            ABORTED_SESSION: "abgebrochen",
            FINISHED_SESSION: "abgeschlossen",
            "ses_ohne_lauf": "unbekannt",
        }
        for session, label in expected_labels.items():
            entry = by_id[session]
            self.assertEqual(label, entry.get("state_label"),
                             f"Falsches Zustandslabel für {session}: {entry}")
            for field in (
                "session", "project", "name", "run_id", "agent", "harness",
                "first_seen", "last_seen", "state",
            ):
                self.assertIn(
                    field, entry,
                    f"Feld {field!r} fehlt im API-Eintrag: {entry}")
        self.assertEqual(
            str(self.project.resolve()), by_id[ABORTED_SESSION]["project"],
            "Der Projekteintrag ist nicht der reale Projektpfad")

    def test_default_limit_comes_from_the_stored_value(self):
        """Ohne Parameter gilt der gespeicherte Standard (hier 2), nicht 5."""
        self.seed_sessions([
            self.session("ses_1", last=500),
            self.session("ses_2", last=400),
            self.session("ses_3", last=300),
            self.session("ses_4", last=200),
        ], limit=2)

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        self.assertEqual(
            ["ses_1", "ses_2"], self.session_ids(data),
            f"Das gespeicherte Limit 2 wurde nicht angewandt: {raw}")
        self.assertEqual(2, (data or {}).get("limit"), raw)

    def test_limit_parameter_limits_the_list(self):
        """``limit=1`` liefert genau die jüngste Session."""
        self.seed_sessions([
            self.session("ses_alt", last=100),
            self.session("ses_neu", last=200),
        ])

        status, data, raw = self.get_sessions(query="name=proj&limit=1")

        self.assertEqual(200, status, raw)
        self.assertEqual(["ses_neu"], self.session_ids(data), raw)

    def test_limit_parameter_is_capped_at_hundred(self):
        """``limit=500`` wird auf 100 begrenzt (Registerobergrenze)."""
        self.seed_sessions([self.session("ses_1", last=100)])

        status, data, raw = self.get_sessions(query="name=proj&limit=500")

        self.assertEqual(200, status, raw)
        self.assertEqual(
            100, (data or {}).get("limit"),
            f"Das wirksame Limit wurde nicht auf 100 begrenzt: {raw}")
        self.assertEqual(["ses_1"], self.session_ids(data), raw)

    def test_text_filter_is_case_insensitive_on_the_session_id(self):
        """``text`` sucht ohne Rücksicht auf Groß-/Kleinschreibung."""
        self.seed_sessions([
            self.session("ses_Alpha", last=300),
            self.session("ses_beta", last=200),
        ])

        status, data, raw = self.get_sessions(query="name=proj&text=alp")

        self.assertEqual(200, status, raw)
        self.assertEqual(["ses_Alpha"], self.session_ids(data), raw)

    def test_running_reflects_the_live_run_registry(self):
        """``running`` ist wahr genau dann, wenn das Laufregister den Lauf
        als live führt."""
        self.seed_sessions([self.session("ses_1", run_id="lauf-live")])
        status, data, raw = self.get_sessions()
        self.assertEqual(200, status, raw)
        self.assertFalse((data or {}).get("running"),
                         f"Ohne Laufregister darf running nicht wahr sein: {raw}")

        self.add_run("lauf-live", "running")

        status, data, raw = self.get_sessions()
        self.assertEqual(200, status, raw)
        self.assertTrue(
            (data or {}).get("running"),
            f"Ein laufender Registereintrag muss running wahr machen: {raw}")

    def test_resume_is_supported_for_opencode(self):
        """Der Standard-Harness opencode kann Sessions fortsetzen."""
        self.seed_sessions([self.session(ABORTED_SESSION)])

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        self.assertTrue(
            (data or {}).get("resume_supported"),
            f"opencode muss resume_supported wahr melden: {raw}")

    def test_resume_is_unsupported_for_pi(self):
        """Pi läuft im Print-Modus; ``resume_supported`` ist falsch."""
        self.select_pi()
        self.seed_sessions([self.session(ABORTED_SESSION, harness="pi")])

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        self.assertFalse(
            (data or {}).get("resume_supported"),
            f"Pi darf resume_supported nicht wahr melden: {raw}")


class SessionsContinueTest(Ap19SessionsApiFixture):
    """AK3: Fortsetzen genau einer gewählten Session; Ablehnungen starten nichts."""

    def test_post_is_token_protected(self):
        """Ohne Token 403 und kein Startbefehl."""
        self.seed_sessions([self.session(ABORTED_SESSION)])

        status, data, raw = self.post_continue(ABORTED_SESSION, token=False)

        self.assertEqual(403, status, raw)
        self.assertEqual(
            "unauthorized", (data or {}).get("error", {}).get("code"), raw)
        self.assertEqual([], self.new_session_commands(), raw)

    def test_unknown_session_is_refused_without_start(self):
        """Eine Session, die nicht im Register steht, wird abgelehnt."""
        self.seed_sessions([self.session(ABORTED_SESSION)])

        status, data, raw = self.post_continue(UNKNOWN_SESSION)

        self.assertFalse(
            self.ok_flag(data), f"Unbekannte Session wurde fortgesetzt: {raw}")
        self.assertTrue(
            self.message_of(data).strip(),
            f"Ablehnung ohne verständliche Meldung: {raw}")
        self.assertEqual([], self.new_session_commands(), raw)

    def test_session_of_another_project_is_refused_without_start(self):
        """Eine Session aus einem fremden Projekt darf nicht fortgesetzt werden,
        auch wenn ihre Kennung im Register steht."""
        foreign = self.root / "fremd"
        foreign.mkdir(exist_ok=True)
        self.seed_sessions([self.session(FOREIGN_SESSION, project=foreign)])

        status, data, raw = self.post_continue(FOREIGN_SESSION)

        self.assertFalse(
            self.ok_flag(data), f"Fremde Session wurde fortgesetzt: {raw}")
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.new_session_commands(), raw)

    def test_active_run_refuses_to_start_anew(self):
        """Bei aktivem Lauf wird nicht erneut gestartet."""
        self.seed_sessions([self.session(ABORTED_SESSION)])
        self.add_run("lauf-live", "running")

        status, data, raw = self.post_continue(ABORTED_SESSION)

        self.assertFalse(
            self.ok_flag(data), f"Fortsetzen bei aktivem Lauf erlaubt: {raw}")
        message = self.message_of(data)
        self.assertTrue(
            ("gestoppt" in message)
            or ("Fortsetz" in message and "Lauf" in message),
            f"Meldung nennt nicht, dass Fortsetzen nur bei gestopptem Lauf "
            f"möglich ist: {message}",
        )
        self.assertEqual([], self.new_session_commands(), raw)

    def test_pi_refuses_with_no_session_reason(self):
        """Pi wird abgelehnt und die Meldung nennt Pi sowie ``--no-session``."""
        self.select_pi()
        self.seed_sessions([self.session(ABORTED_SESSION, harness="pi")])

        status, data, raw = self.post_continue(ABORTED_SESSION)

        self.assertFalse(
            self.ok_flag(data), f"Fortsetzen bei Pi erlaubt: {raw}")
        message = self.message_of(data)
        self.assertIn("Pi", message, f"Meldung nennt Pi nicht: {message}")
        self.assertIn(
            "--no-session", message,
            f"Meldung nennt die --no-session-Begründung nicht: {message}")
        self.assertEqual([], self.new_session_commands(), raw)

    def test_unknown_action_is_refused_without_start(self):
        """Nur ``action='continue'`` ist zulässig; anderes startet nichts."""
        self.seed_sessions([self.session(ABORTED_SESSION)])

        status, data, raw = self.post_continue(
            ABORTED_SESSION, action="steer")

        self.assertFalse(
            self.ok_flag(data), f"Unbekannte Aktion wurde angenommen: {raw}")
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.new_session_commands(), raw)

    def test_continue_starts_exactly_the_given_session(self):
        """Erfolg: genau die gewählte, abgebrochene Session wird exportiert."""
        self.add_run("lauf-ab", "ended")
        self.seed_sessions([
            self.session(ABORTED_SESSION, run_id="lauf-ab")])

        status, data, raw = self.post_continue(ABORTED_SESSION)

        self.assertEqual(200, status, raw)
        self.assertTrue(
            self.ok_flag(data),
            "Fortsetzen der abgebrochenen Session wurde nicht angenommen: "
            + raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        commands = self.new_session_commands()
        self.assertTrue(
            commands,
            "Fortsetzen hat keinen Lauf gestartet (tmux-Attrappe leer)")
        self.assertEqual(
            [ABORTED_SESSION], self.continue_exports(),
            "Der Startbefehl exportiert nicht exakt die gewählte Session: "
            + "\n".join(commands))


class PackageContextTest(Ap19SessionsApiFixture):
    """Sessions are shown in the context of their stored package assignment.

    The ``packages`` array of ``GET /api/sessions`` is built from the saved
    assignments on the packages, not from a session's display name. A cleaned
    session disappears from every view.
    """

    def seed_tickets(self, records):
        store = self.project / ".vibe" / "tickets.json"
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(
            json.dumps({"version": 1, "tickets": records},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    def ticket(self, tid, sessions):
        return {
            "id": tid, "title": tid, "type": "task", "state": "open",
            "description": "", "github": None, "pr_url": "", "commit": "",
            "test": "", "blocked_reason": "", "waiting_note": "",
            "priority": "", "dependencies": [], "sessions": sessions,
        }

    def packages_of(self, data):
        return {item["id"]: item for item in (data or {}).get("packages", [])}

    def test_packages_array_is_built_from_stored_assignments(self):
        self.seed_tickets([self.ticket("AP1", ["ses_a"]),
                           self.ticket("AP2", ["ses_b"])])
        self.seed_sessions([
            self.session("ses_a", first=100, last=200),
            self.session("ses_b", first=100, last=100),
        ])

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        packages = self.packages_of(data)
        self.assertTrue(packages, "Die Antwort enthält keine packages: " + raw)
        for tid in ("AP1", "AP2"):
            self.assertIn(tid, packages, raw)
            self.assertIn("title", packages[tid], raw)
            self.assertIsInstance(packages[tid].get("sessions"), list, raw)
        self.assertEqual(["ses_a"], packages["AP1"]["sessions"], raw)
        self.assertEqual(["ses_b"], packages["AP2"]["sessions"], raw)

    def test_package_context_never_guesses_by_display_name(self):
        """A session named after AP1 is assigned to AP2; the stored assignment
        wins over the title."""
        self.seed_tickets([self.ticket("AP1", []),
                           self.ticket("AP2", ["ses_x"])])
        self.seed_sessions([self.session("ses_x", name="AP1")])

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        packages = self.packages_of(data)
        self.assertEqual([], packages["AP1"]["sessions"], raw)
        self.assertEqual(["ses_x"], packages["AP2"]["sessions"], raw)

    def test_cleaned_session_appears_in_no_view(self):
        self.seed_tickets([self.ticket("AP1", ["ses_a"])])
        self.seed_sessions([self.session("ses_a")])

        # Successful completion: remove the assignment and forget the session.
        store = self.project / ".vibe" / "tickets.json"
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["tickets"][0]["sessions"] = []
        store.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
        (self.runtime / "sessions.json").write_text(
            json.dumps({"limit": 5, "sessions": []}) + "\n", encoding="utf-8")

        status, data, raw = self.get_sessions()

        self.assertEqual(200, status, raw)
        self.assertNotIn("ses_a", self.session_ids(data), raw)
        packages = self.packages_of(data)
        self.assertTrue(packages, raw)
        self.assertEqual([], packages["AP1"]["sessions"], raw)


if __name__ == "__main__":
    unittest.main()
