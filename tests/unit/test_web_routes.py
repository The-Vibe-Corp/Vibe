"""Web-Routen: Shell, Limits, Gates, Läufe, Sitzungen, Pfade und Backend-Verträge.

Aufruf: python3 -m unittest tests.unit.test_web_routes -v
"""


# ===========================================================================
# Unabhängige Abnahme: Server-Vertrag der neuen Oberfläche
# ===========================================================================

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
BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_gates  # noqa: E402
import vibe_limits  # noqa: E402
import vibe_runs  # noqa: E402

ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_HARNESS",
    "XDG_CONFIG_HOME",
)

# Die JavaScript-Dateien der neuen Oberfläche aus dem Vertrag
# (dazu nova.css; zusammen die acht Nova-Assets).
NOVA_SCRIPTS = (
    "nova-core.js",
    "nova-home.js",
    "nova-project.js",
    "nova-output.js",
    "nova-agents.js",
    "nova-activity.js",
    "nova-settings.js",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DashboardFixture(unittest.TestCase):
    """Startet ein echtes Dashboard mit isolierten Pfaden und Projekt."""

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
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
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

    def setUp(self):
        """Setzt die schreibbaren Zustände vor jedem Fall zurück."""
        for name in ("limits.json", "gates.json"):
            (self.state / name).unlink(missing_ok=True)
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )

    def request(
        self,
        method,
        path,
        body=None,
        token=None,
        cookie=None,
        host=None,
        origin=None,
        extra_headers=None,
    ):
        """HTTP-Anfrage mit Header-Kontrolle; Standard ist Loopback-Host."""
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Host": host if host is not None else f"127.0.0.1:{self.port}"
        }
        if token is not None:
            headers["X-Token"] = token
        if cookie is not None:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def post(self, path, body, token=None):
        """POST mit Token und Same-Origin-Kontext (Muster AP13)."""
        return self.request(
            "POST",
            path,
            body=body,
            token=self.token if token is None else token,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )

    def state_file(self, name):
        return self.state / name


class ShellRoutingTest(DashboardFixture):
    """Seiten und statische Dateien: neue Shell, /classic, 404, Guard."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_root_serves_the_new_shell_without_auth(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET / ohne Token.

        Erwartung: 200 text/html; der Rumpf trägt ``data-nv-app`` und nicht
        mehr den alten Navigationsmarker ``<nav id="nav">``.
        """
        status, body, headers = self.request("GET", "/", token=None)
        self.assertEqual(200, status, body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(
            "data-nv-app", body,
            "Die neue Shell (data-nv-app) wird unter / nicht ausgeliefert")
        self.assertNotIn(
            '<nav id="nav">', body,
            "Unter / erscheint noch der alte Navigationsmarker der alten UI")

    def test_classic_serves_the_old_shell_without_auth(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET /classic ohne Token.

        Erwartung: 200 text/html; der Rumpf trägt die alten Marker
        ``id="nav"`` und ``/static/app.js`` und nicht ``data-nv-app``.
        """
        status, body, headers = self.request("GET", "/classic", token=None)
        self.assertEqual(200, status, body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(
            'id="nav"', body,
            "Die klassische Shell (id=\"nav\") wird unter /classic nicht ausgeliefert")
        self.assertIn(
            "/static/app.js", body,
            "Die klassische Shell lädt nicht mehr /static/app.js")
        self.assertNotIn(
            "data-nv-app", body,
            "Unter /classic erscheint die neue Shell statt der alten")

    def test_unknown_path_stays_not_found(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET unbekannter Pfad
        mit Token.

        Erwartung: 404; die Einführung von /classic öffnet keinen Wildcard-
        Pfad. (Mit Token, damit die Antwort die Wegfindung und nicht die
        Tokenpflicht prüft.)
        """
        for path in ("/nicht-vorhanden", "/classic/mehr"):
            with self.subTest(path=path):
                status, body, _ = self.request(
                    "GET", path, token=self.token)
                self.assertEqual(404, status, body)

    def test_both_pages_keep_the_host_guard(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET / und /classic mit
        fremdem Host-Header.

        Erwartung: je 403 ``forbidden_host`` (Host-/Origin-Guard unverändert,
        AP13).
        """
        for path in ("/", "/classic"):
            with self.subTest(path=path):
                status, body, _ = self.request(
                    "GET", path, token=None, host=f"vibe.example:{self.port}"
                )
                self.assertEqual(403, status, body)
                self.assertEqual(
                    "forbidden_host", json.loads(body)["error"]["code"], body)

    def test_static_map_serves_all_nova_files(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET der Nova-Assets.

        Erwartung: ``/static/nova.css`` und alle sieben ``nova-*.js`` aus dem
        Vertrag liefern 200; ``/static/nova-missing.js`` liefert 404.
        """
        status, body, headers = self.request(
            "GET", "/static/nova.css", token=None)
        self.assertEqual(200, status, body)
        self.assertIn("text/css", headers.get("Content-Type", ""))

        for name in NOVA_SCRIPTS:
            with self.subTest(asset=name):
                status, body, headers = self.request(
                    "GET", "/static/" + name, token=None)
                self.assertEqual(200, status, "Asset fehlt: " + name)
                self.assertIn(
                    "javascript", headers.get("Content-Type", ""),
                    name + " wird nicht als JavaScript ausgeliefert")

        status, body, _ = self.request(
            "GET", "/static/nova-missing.js", token=None)
        self.assertEqual(404, status, body)


class LimitsApiTest(DashboardFixture):
    """GET/POST /api/limits spiegelt vibe_limits (global, kein Projekt)."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_limits_view_requires_token_and_reports_stop(self):
        """Vorbedingung: kein ``limits.json``. Aktion: GET ohne und mit Token.

        Erwartung: ohne Token 403 ``unauthorized``; mit Token 200 ``ok:true``,
        ``mode`` aus ``stop``/``continue`` (Default ``stop``), ``problem``
        leer/fehlend und ``lines`` als Liste der describe-Zeilen.
        """
        status, body, _ = self.request("GET", "/api/limits", token=None)
        self.assertEqual(403, status, body)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

        status, body, _ = self.request("GET", "/api/limits", token=self.token)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertIn(data["mode"], vibe_limits.MODES, body)
        self.assertEqual(vibe_limits.DEFAULT_MODE, data["mode"], body)
        self.assertIn(data.get("problem"), (None, ""), body)
        self.assertIsInstance(data.get("lines"), list, body)

    def test_limits_post_continue_persists_in_state(self):
        """Vorbedingung: Default ``stop``. Aktion: POST ``continue``.

        Erwartung: 200 ``ok:true`` mit ``mode:"continue"``; ``vibe_limits.load``
        auf dem isolierten Zustandsordner liest ``continue``; ein
        anschließendes GET bestätigt den neuen Zustand.
        """
        status, body, _ = self.post(
            "/api/limits", {"action": "continue"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual("continue", data["mode"], body)

        stored_mode, problem = vibe_limits.load(str(self.state))
        self.assertEqual("", problem, "Der gespeicherte Zustand ist defekt")
        self.assertEqual("continue", stored_mode,
                         "limits.json enthält den neuen Modus nicht")
        self.assertEqual(
            {"mode": "continue"},
            json.loads(self.state_file("limits.json").read_text(encoding="utf-8")),
            "limits.json hat nicht die dokumentierte Form")

        status, body, _ = self.request("GET", "/api/limits", token=self.token)
        self.assertEqual(200, status, body)
        self.assertEqual("continue", json.loads(body)["mode"], body)

    def test_limits_unknown_action_changes_nothing(self):
        """Vorbedingung: gespeicherter Modus ``continue``. Aktion: POST mit
        unbekannter Aktion.

        Erwartung: 200 ``ok:false`` mit Meldung; ``limits.json`` bleibt
        byte-gleich (kein Schreibvorgang).
        """
        status, body, _ = self.post("/api/limits", {"action": "continue"})
        self.assertEqual(200, status, body)
        before = self.state_file("limits.json").read_bytes()

        status, body, _ = self.post("/api/limits", {"action": "weiter"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        self.assertTrue(str(data.get("message") or "").strip(), body)
        self.assertEqual(
            before, self.state_file("limits.json").read_bytes(),
            "Unbekannte Aktion veränderte limits.json")


class GatesApiTest(DashboardFixture):
    """GET/POST /api/gates spiegelt vibe_gates (global + Projekt-Override)."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def gates_view(self, query="", token=None):
        status, body, _ = self.request(
            "GET", "/api/gates" + query,
            token=self.token if token is None else token)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        return data

    def test_gates_view_requires_token_and_lists_defaults(self):
        """Vorbedingung: keine ``gates.json``. Aktion: GET ohne und mit Token.

        Erwartung: ohne Token 403; mit Token 200 ``ok:true``, ``project``
        ``None``, ``gates`` mit genau den Schlüsseln aus
        ``vibe_gates.DEFAULTS`` (je ``value`` + ``origin``) und den
        Voreinstellungen als Herkunft.
        """
        status, body, _ = self.request("GET", "/api/gates", token=None)
        self.assertEqual(403, status, body)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

        data = self.gates_view()
        self.assertIsNone(data.get("project"), body)
        self.assertEqual(
            set(vibe_gates.DEFAULTS), set(data["gates"]),
            "Die Schrankenschlüssel weichen von vibe_gates.DEFAULTS ab: "
            + repr(sorted(data["gates"])))
        for key, default in vibe_gates.DEFAULTS.items():
            with self.subTest(gate=key):
                entry = data["gates"][key]
                self.assertEqual(default, entry["value"], data)
                self.assertEqual(
                    vibe_gates.ORIGIN_STANDARD, entry["origin"], data)
        self.assertIsInstance(data.get("lines"), list, data)

    def test_gates_view_with_project_reports_project_view(self):
        """Vorbedingung: registriertes Projekt ``proj``. Aktion: GET
        ``/api/gates?name=proj``.

        Erwartung: 200 ``ok:true``, ``project == "proj"`` und dieselbe
        Schrankenform wie global (Projekt ohne Overrides = Standard).
        """
        data = self.gates_view("?name=proj")
        self.assertEqual("proj", data.get("project"), data)
        self.assertEqual(set(vibe_gates.DEFAULTS), set(data["gates"]), data)
        self.assertEqual(
            vibe_gates.DEFAULTS["repair_rounds"],
            data["gates"]["repair_rounds"]["value"], data)

    def test_gates_global_save_sets_effective_value(self):
        """Vorbedingung: Voreinstellung ``repair_rounds=2``. Aktion: POST
        ``{"key":"repair_rounds","value":"5"}``.

        Erwartung: 200 ``ok:true``; die Antwort zeigt die neue wirksame
        Ansicht (Wert 5, Herkunft ``global``); ``gates.json`` enthält 5; ein
        GET bestätigt es.
        """
        status, body, _ = self.post(
            "/api/gates", {"key": "repair_rounds", "value": "5"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual(5, data["gates"]["repair_rounds"]["value"], body)
        self.assertEqual(
            vibe_gates.ORIGIN_GLOBAL,
            data["gates"]["repair_rounds"]["origin"], body)

        stored = json.loads(
            self.state_file("gates.json").read_text(encoding="utf-8"))
        self.assertEqual(5, stored.get("repair_rounds"),
                         "gates.json enthält den neuen Wert nicht")

        self.assertEqual(5, self.gates_view()["gates"]["repair_rounds"]["value"])

    def test_gates_invalid_value_changes_nothing(self):
        """Vorbedingung: gespeicherte Schranke. Aktion: POST mit Wert ``0``
        (``vibe_gates.validate`` verlangt ≥ 1).

        Erwartung: 200 ``ok:false`` mit Meldung; ``gates.json`` bleibt
        byte-gleich.
        """
        status, body, _ = self.post(
            "/api/gates", {"key": "repair_rounds", "value": "5"})
        self.assertEqual(200, status, body)
        before = self.state_file("gates.json").read_bytes()

        status, body, _ = self.post(
            "/api/gates", {"key": "repair_rounds", "value": "0"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        self.assertTrue(str(data.get("message") or "").strip(), body)
        self.assertEqual(
            before, self.state_file("gates.json").read_bytes(),
            "Ungültiger Wert veränderte gates.json")

    def test_gates_unknown_key_changes_nothing(self):
        """Vorbedingung: keine ``gates.json``. Aktion: POST mit unbekanntem
        Schlüssel (nicht in ``vibe_gates.DEFAULTS``).

        Erwartung: 200 ``ok:false``; keine Datei entsteht.
        """
        status, body, _ = self.post(
            "/api/gates", {"key": "unbekannte_schranke", "value": "1"})
        self.assertEqual(200, status, body)
        self.assertFalse(json.loads(body)["ok"], body)
        self.assertFalse(
            self.state_file("gates.json").exists(),
            "Unbekannter Schlüssel legte gates.json an")

    def test_gates_project_override_sets_and_removes_env_key(self):
        """Vorbedingung: Projekt ``proj`` mit ``project.env`` (TYPE=generic).

        Aktion: POST ``{"key":"retries","value":"7","project":"proj"}``, dann
        derselbe Aufruf mit leerem Wert.
        Erwartung: Der Projektwert landet als ``MAX_RETRIES=7``
        (``PROJECT_ENV_KEYS``) in ``.vibe/project.env``, die wirksame Ansicht
        meldet 7 mit Herkunft ``projekt``; der leere Wert entfernt die Zeile,
        TYPE bleibt erhalten, die Herkunft fällt auf ``Standard`` zurück.
        """
        env_path = self.project / ".vibe" / "project.env"

        status, body, _ = self.post(
            "/api/gates",
            {"key": "retries", "value": "7", "project": "proj"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual("proj", data.get("project"), body)
        self.assertEqual(7, data["gates"]["retries"]["value"], body)
        self.assertEqual(
            vibe_gates.ORIGIN_PROJECT, data["gates"]["retries"]["origin"], body)
        self.assertIn(
            "MAX_RETRIES=7", env_path.read_text(encoding="utf-8"),
            "Projektvariable MAX_RETRIES fehlt in .vibe/project.env")

        project_view = self.gates_view("?name=proj")
        self.assertEqual(7, project_view["gates"]["retries"]["value"])
        self.assertEqual(
            vibe_gates.ORIGIN_PROJECT, project_view["gates"]["retries"]["origin"])

        status, body, _ = self.post(
            "/api/gates",
            {"key": "retries", "value": "", "project": "proj"})
        self.assertEqual(200, status, body)
        self.assertTrue(json.loads(body)["ok"], body)
        text = env_path.read_text(encoding="utf-8")
        self.assertNotIn(
            "MAX_RETRIES", text,
            "Leerer Projektwert entfernte die Variable nicht: " + repr(text))
        self.assertIn("TYPE=generic", text,
                      "Andere Zeilen der project.env gingen verloren")

        project_view = self.gates_view("?name=proj")
        self.assertEqual(
            vibe_gates.DEFAULTS["retries"],
            project_view["gates"]["retries"]["value"])
        self.assertEqual(
            vibe_gates.ORIGIN_STANDARD,
            project_view["gates"]["retries"]["origin"])


class RunsApiTest(DashboardFixture):
    """GET/POST /api/runs: Register lesen und Prune ohne Register."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_runs_view_requires_token_and_is_empty(self):
        """Vorbedingung: frisches Laufregister. Aktion: GET ohne und mit Token.

        Erwartung: ohne Token 403; mit Token 200 ``ok:true`` mit
        ``records: []`` (keine erfundenen Läufe).
        """
        status, body, _ = self.request("GET", "/api/runs", token=None)
        self.assertEqual(403, status, body)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

        status, body, _ = self.request("GET", "/api/runs", token=self.token)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual([], data["records"], body)

    def test_runs_prune_on_empty_register_is_a_no_op(self):
        """Vorbedingung: leeres Register. Aktion: POST ``{"action":"prune"}``.

        Erwartung: 200 ``ok:true`` mit ``ended``/``running``/``unknown`` = 0;
        das Register bleibt leer.
        """
        status, body, _ = self.post("/api/runs", {"action": "prune"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        for key in ("ended", "running", "unknown"):
            self.assertEqual(0, data.get(key), body)

        status, body, _ = self.request("GET", "/api/runs", token=self.token)
        self.assertEqual([], json.loads(body)["records"], body)

    def test_runs_unknown_action_is_rejected(self):
        """Vorbedingung: leeres Register. Aktion: POST mit unbekannter Aktion.

        Erwartung: 200 ``ok:false`` mit Meldung; das Register bleibt leer.
        """
        status, body, _ = self.post("/api/runs", {"action": "loeschen"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        self.assertTrue(str(data.get("message") or "").strip(), body)
        status, body, _ = self.request("GET", "/api/runs", token=self.token)
        self.assertEqual([], json.loads(body)["records"], body)


class SessionsApiTest(DashboardFixture):
    """POST /api/sessions: CLI-Parität für ``vibe sessions limit N``."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def registry(self):
        """Register im isolierten Laufzeitordner (``VIBE_RUNTIME``)."""
        return vibe_runs.SessionRegistry(str(self.log_dir))

    def test_sessions_limit_post_persists_and_is_reported(self):
        """Vorbedingung: kein ``sessions.json`` (Standardlimit greift).

        Aktion: POST ohne Token; dann POST ``{"name":"proj",
        "action":"limit","limit":7}`` und GET ``/api/sessions?name=proj``
        ohne ``limit``-Parameter; danach der Grenzwert
        ``vibe_runs.SESSION_LIMIT_MAX`` für das Projekt; zuletzt ein POST
        ohne ``name``.

        Erwartung (F34): ``name`` setzt das PROJEKT-Limit
        (``SessionRegistry.project_limit``, Schlüssel realpath in
        ``project_limits``); das globale ``limit()`` bleibt der Standard und
        die Sessionliste unangetastet. GET meldet das wirksame Projektlimit.
        Ein POST ohne ``name`` setzt dagegen das globale Limit und lässt
        ``project_limits`` unverändert. Ohne Token: 403 ``unauthorized`` ohne
        Datei.
        """
        sessions_file = self.log_dir / "sessions.json"
        project_key = os.path.realpath(os.path.abspath(str(self.project)))
        sessions_file.unlink(missing_ok=True)
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_DEFAULT, self.registry().limit(),
            "Vorbedingung: ohne sessions.json gilt das Standardlimit")

        status, body, _ = self.request(
            "POST", "/api/sessions",
            body={"name": "proj", "action": "limit", "limit": 7},
            token=None,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(403, status, body)
        self.assertEqual(
            "unauthorized", json.loads(body)["error"]["code"], body)
        self.assertFalse(
            sessions_file.exists(),
            "POST ohne Token legte sessions.json an")

        status, body, _ = self.post(
            "/api/sessions",
            {"name": "proj", "action": "limit", "limit": 7})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual(7, data.get("limit"), body)
        self.assertEqual("proj", data.get("project"), body)

        registry = self.registry()
        self.assertEqual(
            7, registry.project_limit(str(self.project)),
            "Das Projektlimit wurde nicht über "
            "SessionRegistry.set_project_limit gespeichert")
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_DEFAULT, registry.limit(),
            "Das Projektlimit überschrieb das globale Limit")
        stored = json.loads(sessions_file.read_text(encoding="utf-8"))
        self.assertEqual(
            {project_key: 7}, stored.get("project_limits"),
            "sessions.json enthält das Projektlimit 7 nicht: " + body)
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_DEFAULT, stored.get("limit"),
            "sessions.json veränderte das globale Limit: " + body)
        self.assertEqual([], stored.get("sessions"),
                         "Das Setzen des Limits erfasste Sessions: " + body)

        status, body, _ = self.request(
            "GET", "/api/sessions?name=proj", token=self.token)
        self.assertEqual(200, status, body)
        self.assertEqual(
            7, json.loads(body).get("limit"),
            "GET /api/sessions meldet das wirksame Projektlimit nicht: " + body)

        status, body, _ = self.post(
            "/api/sessions",
            {"name": "proj", "action": "limit",
             "limit": vibe_runs.SESSION_LIMIT_MAX})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_MAX, data.get("limit"), body)
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_MAX,
            self.registry().project_limit(str(self.project)),
            "Der Grenzwert SESSION_LIMIT_MAX wurde nicht als Projektlimit "
            "gespeichert")
        self.assertEqual(
            vibe_runs.SESSION_LIMIT_DEFAULT, self.registry().limit(),
            "Der Projekt-Grenzwert veränderte das globale Limit")

        status, body, _ = self.post(
            "/api/sessions", {"action": "limit", "limit": 9})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual(9, data.get("limit"), body)
        self.assertIsNone(data.get("project"), body)
        self.assertEqual(
            9, self.registry().limit(),
            "Ein POST ohne name setzte das globale Limit nicht")
        global_stored = json.loads(sessions_file.read_text(encoding="utf-8"))
        self.assertEqual(
            {project_key: vibe_runs.SESSION_LIMIT_MAX},
            global_stored.get("project_limits"),
            "Das globale Limit veränderte project_limits: " + body)
        self.assertEqual([], global_stored.get("sessions"),
                         "Das globale Limit erfasste Sessions: " + body)

    def test_sessions_limit_invalid_values_change_nothing(self):
        """Vorbedingung: Projektlimit 7, globaler Standard.

        Aktion: POST ``action:"limit"`` mit ``0``, ``"abc"`` und einem Wert
        über ``SESSION_LIMIT_MAX`` — jeweils mit ``name`` und ohne ``name``;
        danach eine unbekannte Aktion in beiden Scopes.

        Erwartung (F34): je 200 ``ok:false`` mit Meldung; ``sessions.json``
        bleibt byte-gleich, das Projektlimit bleibt 7 und das globale Limit
        bleibt der Standard (kein Schreibvorgang in beiden Scopes).
        """
        sessions_file = self.log_dir / "sessions.json"
        project_key = os.path.realpath(os.path.abspath(str(self.project)))
        status, body, _ = self.post(
            "/api/sessions",
            {"name": "proj", "action": "limit", "limit": 7})
        self.assertEqual(200, status, body)
        self.assertTrue(json.loads(body)["ok"], body)
        before = sessions_file.read_bytes()

        for invalid in (0, "abc", vibe_runs.SESSION_LIMIT_MAX + 1):
            for scope in ("project", "global"):
                with self.subTest(limit=invalid, scope=scope):
                    payload = {"action": "limit", "limit": invalid}
                    if scope == "project":
                        payload["name"] = "proj"
                    status, body, _ = self.post("/api/sessions", payload)
                    self.assertEqual(200, status, body)
                    data = json.loads(body)
                    self.assertFalse(data["ok"], body)
                    self.assertTrue(
                        str(data.get("message") or "").strip(), body)
                    self.assertEqual(
                        before, sessions_file.read_bytes(),
                        "Ungültiges Limit veränderte sessions.json (%s)"
                        % scope)
                    registry = self.registry()
                    self.assertEqual(
                        7, registry.project_limit(str(self.project)), body)
                    self.assertEqual(
                        vibe_runs.SESSION_LIMIT_DEFAULT, registry.limit(),
                        body)
                    stored = json.loads(
                        sessions_file.read_text(encoding="utf-8"))
                    self.assertEqual({project_key: 7},
                                     stored.get("project_limits"), body)
                    self.assertEqual([], stored.get("sessions"), body)

        for scope in ("project", "global"):
            with self.subTest(action="weiter", scope=scope):
                payload = {"action": "weiter"}
                if scope == "project":
                    payload["name"] = "proj"
                status, body, _ = self.post("/api/sessions", payload)
                self.assertEqual(200, status, body)
                data = json.loads(body)
                self.assertFalse(data["ok"], body)
                self.assertTrue(
                    str(data.get("message") or "").strip(), body)
                self.assertEqual(
                    before, sessions_file.read_bytes(),
                    "Unbekannte Aktion veränderte sessions.json (%s)" % scope)
                registry = self.registry()
                self.assertEqual(
                    7, registry.project_limit(str(self.project)), body)
                self.assertEqual(
                    vibe_runs.SESSION_LIMIT_DEFAULT, registry.limit(), body)


class EmuApiTest(DashboardFixture):
    """POST /api/emu startet nur mit Android-Projekt."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_emu_without_android_project_is_rejected(self):
        """Vorbedingung: nur ein generisches Projekt. Aktion: POST
        ``/api/emu`` ``{"action":"start"}`` ohne und mit Token.

        Erwartung: ohne Token 403; mit Token 200 ``ok:false`` und einer
        Meldung, die „Android“ nennt (Fachfehler, kein Absturz).
        """
        status, body, _ = self.request(
            "POST", "/api/emu", body={"action": "start"}, token=None,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(403, status, body)

        status, body, _ = self.post("/api/emu", {"action": "start"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        message = str(data.get("message") or "")
        self.assertTrue(message.strip(), body)
        self.assertIn("Android", message, body)


class PathsApiTest(DashboardFixture):
    """GET /api/paths: schreibfreie Pfadauflösung ohne Geheimnisse."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_paths_requires_token_and_leaks_no_secrets(self):
        """Vorbedingung: isolierte Pfade (VIBE/VIBE_STATE/VIBE_RUNTIME).

        Aktion: GET ohne und mit Token; Antwort auf das Instanz-Token prüfen.
        Erwartung: ohne Token 403; mit Token 200 ``ok:true`` mit den
        aufgelösten Pfaden (workspace/install/state/runtime/agents_dir); kein
        Token und kein Kennwort in der Antwort.
        """
        status, body, _ = self.request("GET", "/api/paths", token=None)
        self.assertEqual(403, status, body)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

        status, body, _ = self.request("GET", "/api/paths", token=self.token)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        paths = data.get("paths")
        self.assertIsInstance(paths, dict, body)
        expected = {
            "workspace": self.root,
            "install": self.toolchain,
            "state": self.state,
            "runtime": self.log_dir,
            "agents_dir": self.home / ".config" / "opencode" / "agents",
        }
        for key, path in expected.items():
            with self.subTest(field=key):
                self.assertIn(key, paths, body)
                self.assertEqual(
                    os.path.realpath(str(path)),
                    os.path.realpath(str(paths[key])),
                    "Pfad %s weicht ab: %r" % (key, paths[key]))
        self.assertNotIn(self.token, body,
                         "Die Pfadantwort enthält das Instanz-Token")


# ===========================================================================
# Unit-Abnahme, Backend-Verträge (Löschschutz, Projektlimit
# ===========================================================================

import http.client
import importlib.machinery
import importlib.util
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.unit import env_support

CLI = REPO / "bin" / "vibe"
RUNS = REPO / "bin" / "vibe_runs.py"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_gates  # noqa: E402
import vibe_runs  # noqa: E402
import vibe_ui_config  # noqa: E402

# Expliziter Opt-out: Anfrage bewusst OHNE Token senden. Der Default aller
# Helfer ist dagegen, den Token des isolierten Dashboards mitzusenden.
NO_TOKEN = object()
USE_TOKEN = object()


DDL_V2 = """
CREATE TABLE `session_v2` (
  `id` text PRIMARY KEY,
  `project_id` text NOT NULL,
  `workspace_id` text,
  `parent_id` text,
  `fork_session_id` text,
  `fork_boundary` text,
  `slug` text NOT NULL,
  `directory` text NOT NULL,
  `path` text,
  `title` text,
  `version` text NOT NULL,
  `share_url` text,
  `summary_additions` integer,
  `summary_deletions` integer,
  `summary_files` integer,
  `summary_diffs` text,
  `metadata` text,
  `cost` real DEFAULT 0 NOT NULL,
  `tokens_input` integer DEFAULT 0 NOT NULL,
  `tokens_output` integer DEFAULT 0 NOT NULL,
  `tokens_reasoning` integer DEFAULT 0 NOT NULL,
  `tokens_cache_read` integer DEFAULT 0 NOT NULL,
  `tokens_cache_write` integer DEFAULT 0 NOT NULL,
  `revert` text,
  `permission` text,
  `agent` text,
  `model` text,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `time_compacting` integer,
  `time_archived` integer,
  `time_suspended` integer,
  `resume_attempts` integer DEFAULT 0 NOT NULL,
  `time_idle` integer,
  `time_viewed` integer,
  `idle_outcome` text
);
CREATE INDEX `session_v2_project_idx` ON `session_v2` (`project_id`);
CREATE INDEX `session_v2_parent_idx` ON `session_v2` (`parent_id`);
CREATE TABLE "session_message" (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `type` text NOT NULL,
  `seq` integer NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL
);
CREATE UNIQUE INDEX `session_message_session_seq_idx` ON `session_message` (`session_id`, `seq`);
"""


def _load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_vibe_module(vibe_root):
    """Lädt bin/vibe als Modul mit isoliertem VIBE/HOME (für Delete-/Cost-Fälle)."""
    with env_support.isolated_process_environment(
        VIBE=str(vibe_root),
        VIBE_NO_CONTAINER="1",
        HOME=str(vibe_root / "home"),
        VIBE_RUNTIME=str(vibe_root / "_logs"),
        VIBE_STATE=str(vibe_root / "_toolchain"),
        VIBE_CONFIG_FILE=str(vibe_root / "home" / ".config" / "vibe" / "config.json"),
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f34_under_test", str(CLI))
        spec = importlib.util.spec_from_loader("vibe_f34_under_test", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def load_vibe_runs_module():
    """Lädt bin/vibe_runs.py als Testunterlage (für Projektlimit-Fälle)."""
    return _load_module("vibe_runs_f34_under_test", RUNS)


# ---------------------------------------------------------------------------
# Dashboard-Fixture
# ---------------------------------------------------------------------------

class BackendContractsDashboard(unittest.TestCase):
    """Startet das echte Dashboard als eigener Prozess auf Loopback."""

    @classmethod
    def start_server(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.home),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.toolchain),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
        })
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log())
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: " + cls.server_log())
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

    def setUp(self):
        for name in ("limits.json", "gates.json"):
            (self.state / name).unlink(missing_ok=True)
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")

    def request(
        self,
        method,
        path,
        body=None,
        token=USE_TOKEN,
        cookie=None,
        host=None,
        origin=None,
        extra_headers=None,
    ):
        """HTTP-Anfrage mit Header-Kontrolle; Standard ist Loopback-Host.

        Standardmäßig wird der Token mitgesendet. ``token=NO_TOKEN`` sendet die
        Anfrage bewusst ohne Token (für die 403-Prüfungen); jeder andere Wert
        wird als Token verwendet.
        """
        if token is USE_TOKEN:
            token = self.token
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Host": host if host is not None else f"127.0.0.1:{self.port}"
        }
        if token is not NO_TOKEN:
            headers["X-Token"] = token
        if cookie is not None:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def post(self, path, body, token=USE_TOKEN):
        """POST mit Token und Same-Origin-Kontext (Muster AP13).

        ``token=NO_TOKEN`` erzeugt bewusst eine Anfrage ohne Token; ohne
        Argument wird der Token des Dashboards verwendet.
        """
        return self.request(
            "POST",
            path,
            body=body,
            token=token,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )

    def get_json(self, path, token=USE_TOKEN):
        status, text, _headers = self.request(
            "GET", path, token=token)
        self.assertEqual(
            200, status, "GET " + path + " lieferte HTTP " + str(status) + ": "
            + text)
        return json.loads(text)

    def state_file(self, name):
        return self.state / name


# ---------------------------------------------------------------------------
# WP7.1: Löschschutz abgeschlossener Einträge
# ---------------------------------------------------------------------------

def _init_git_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "--allow-empty", "-qm", "init"],
        cwd=path, check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=path, check=True, capture_output=True, text=True,
    ).stdout.strip()


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
    }
    record.update(extra)
    return record


class DeleteProtectionTest(unittest.TestCase):
    """Abgeschlossene Einträge (Feedback/Paket) sind nicht löschbar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        self.commit = _init_git_repo(self.root)
        self.cli = load_vibe_module(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write_store(self, records):
        path = self.project / ".vibe" / "tickets.json"
        path.write_text(
            json.dumps({"version": 1, "tickets": list(records)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return path

    def records(self):
        document = json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}

    def test_feedback_delete_rejects_a_done_entry_and_keeps_the_store(self):
        """Vorbedingung: erledigtes Feedback-Ticket mit Nachweis.
        Aktion: ``vibe.feedback_delete('proj', 'F1')``.
        Erwartung: ``ValueError``; der Speicher bleibt byte-identisch."""
        path = self.write_store([ticket_record(
            "F1", "Erledigter Punkt", type="feedback", state="done",
            commit=self.commit, test="tests/unit/test_f34_backend.py")])
        before = path.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.feedback_delete("proj", "F1")

        self.assertEqual(before, path.read_bytes())

    def test_ticket_delete_rejects_a_done_entry_and_keeps_the_store(self):
        """Vorbedingung: erledigtes Arbeitspaket mit Nachweis.
        Aktion: ``vibe.ticket_delete('proj', 'F1')``.
        Erwartung: ``ValueError``; der Speicher bleibt unverändert."""
        path = self.write_store([ticket_record(
            "F1", "Erledigtes Arbeitspaket", state="done",
            commit=self.commit, test="tests/unit/test_f34_backend.py")])
        before = path.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.ticket_delete("proj", "F1")

        self.assertEqual(before, path.read_bytes())

    def test_open_entries_stay_deletable(self):
        """Vorbedingung: offenes Feedback und offenes Arbeitspaket.
        Aktion: Delete der offenen Einträge.
        Erwartung: Einträge werden entfernt, andere bleiben erhalten."""
        self.write_store([
            ticket_record("F1", "Offener Punkt", type="feedback"),
            ticket_record("F2", "Offener Punkt zwei", type="feedback"),
            ticket_record("F3", "Offenes Arbeitspaket"),
        ])

        self.cli.feedback_delete("proj", "F1")
        self.cli.ticket_delete("proj", "F3")

        records = self.records()
        self.assertEqual(["F2"], list(records))
        self.assertIn("F2", records)


class SessionLimitPerProjectTest(unittest.TestCase):
    """Projekt-Limits für Sessions über das SessionRegistry."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.runtime.mkdir(parents=True)
        self.module = load_vibe_runs_module()
        self.registry = self.module.SessionRegistry(str(self.runtime))

    def tearDown(self):
        self.tmp.cleanup()

    def project(self, name="proj"):
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_project_limit_defaults_to_none_and_set_project_limit_stores_it(self):
        """Vorbedingung: leeres Register. Aktion: ``set_project_limit``.
        Erwartung: gespeichert unter ``project_limits`` (realpath-Schlüssel);
        Default ohne Override ist ``None``.
        """
        project = self.project()
        self.assertIsNone(self.registry.project_limit(str(project)))
        self.assertEqual(2, self.registry.set_project_limit(str(project), 2))
        self.assertEqual(2, self.registry.project_limit(str(project)))
        stored = json.loads(
            (self.runtime / "sessions.json").read_text(encoding="utf-8"))
        self.assertEqual(
            2, stored.get("project_limits", {}).get(
                os.path.realpath(str(project))),
            "project_limits fehlt oder hat den falschen Schlüssel: " + repr(stored),
        )

    def test_project_limit_rejects_invalid_values(self):
        """Vorbedingung: gespeichertes Projektlimit 2. Aktion: ``set_project_limit``
        mit 0/-1/>SESSION_LIMIT_MAX. Erwartung: ``ValueError``; gespeicherter
        Wert bleibt.
        """
        project = self.project()
        self.registry.set_project_limit(str(project), 2)
        for value in (0, -1, self.module.SESSION_LIMIT_MAX + 1, "viele", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.registry.set_project_limit(str(project), value)
        self.assertEqual(2, self.registry.project_limit(str(project)))


# ---------------------------------------------------------------------------
# WP7.3: Gates gesammelt
# ---------------------------------------------------------------------------

class GatesCollectedTest(BackendContractsDashboard):
    """POST /api/gates {project, values} und Single-POST-Verhalten."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def gates_view(self, query="", token=USE_TOKEN):
        status, body, _headers = self.request(
            "GET", "/api/gates" + query, token=token)
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        return data

    def test_gates_single_post_still_sets_the_global_value(self):
        """Vorbedingung: keine ``gates.json``. Aktion: Single-POST
        ``{"key": "retries", "value": "5"}``.
        Erwartung: global gespeichert; Antwort ok.
        """
        status, body, _headers = self.post(
            "/api/gates", {"key": "retries", "value": "5"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        stored = json.loads(
            (self.state / "gates.json").read_text(encoding="utf-8"))
        self.assertEqual(5, stored.get("retries"))

    def test_gates_collected_batch_sets_a_project_override(self):
        """Vorbedingung: keine Overrides. Aktion: POST
        ``{"project": "proj", "values": {"retries": 7}}``.
        Erwartung: Alle Werte validiert; Override in ``.vibe/project.env``;
        Antwort je Schranke mit defaults/overrides/global/origin.
        """
        status, body, _headers = self.post(
            "/api/gates", {"project": "proj", "values": {"retries": 7}})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        entry = data.get("gates", {}).get("retries", {})
        self.assertEqual(vibe_gates.DEFAULTS["retries"], entry.get("default"),
                         "Default fehlt: " + repr(entry))
        self.assertEqual(7, entry.get("override"),
                         "Projekt-Override fehlt: " + repr(entry))
        self.assertEqual(vibe_gates.ORIGIN_PROJECT, entry.get("origin"),
                         "Effektive Herkunft fehlt: " + repr(entry))
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn("MAX_RETRIES=7", env_text,
                      "Projekt-Override MAX_RETRIES fehlt: " + repr(env_text))

    def test_gates_collected_batch_invalid_value_writes_nothing(self):
        """Vorbedingung: keine ``gates.json``, keine Overrides.
        Aktion: POST ``{"project": "proj", "values": {"retries": 7,
        "repair_rounds": 0}}`` (eine invalid).
        Erwartung: ``ok:false``; nichts geschrieben.
        """
        status, body, _headers = self.post(
            "/api/gates", {"project": "proj",
                           "values": {"retries": 7, "repair_rounds": 0}})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertFalse(data.get("ok"), body)
        self.assertTrue(str(data.get("message") or "").strip(), body)
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertNotIn("MAX_RETRIES", env_text, "Ungültiger Wert hat das "
                         "Projekt überschrieben: " + repr(env_text))
        self.assertFalse((self.state / "gates.json").exists(),
                         "Ungültiger Wert hat gates.json angelegt")

    def test_gates_collected_batch_empty_project_value_removes_override(self):
        """Vorbedingung: Override ``retries=7`` gesetzt.
        Aktion: POST ``{"project": "proj", "values": {"retries": ""}}``.
        Erwartung: Override entfernt; Rückfall auf global/Standard.
        """
        self.post("/api/gates", {"project": "proj", "values": {"retries": 7}})
        status, body, _headers = self.post(
            "/api/gates", {"project": "proj", "values": {"retries": ""}})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        entry = data.get("gates", {}).get("retries", {})
        self.assertIsNone(entry.get("override"), "Leerer Wert hat den Override "
                         "nicht entfernt: " + repr(entry))
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertNotIn("MAX_RETRIES", env_text,
                         "Leerer Projektwert entfernte die Variable nicht")


# ---------------------------------------------------------------------------
# WP7.4/5: Währung (ui.json currency/usd_rate) und /api/ui_settings
# ---------------------------------------------------------------------------

class CurrencyUiSettingsTest(BackendContractsDashboard):
    """Währungswerte in ui.json und GET/POST /api/ui_settings."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_vibe_ui_config_validate_accepts_eur_usd_and_rejects_invalid_values(self):
        """Vorbedingung: ``vibe_ui_config.validate``.
        Aktion: currency EUR/USD, usd_rate, unbekannte Felder.
        Erwartung: akzeptiert/validiert, ``ValueError`` bei ungültigem
        ``usd_rate``/currency, unbekannte Felder entfernt.
        """
        cleaned = vibe_ui_config.validate(
            {"currency": "EUR", "usd_rate": 1.0})
        self.assertEqual("EUR", cleaned.get("currency"), cleaned)
        self.assertEqual(1.0, cleaned.get("usd_rate"), cleaned)

        cleaned = vibe_ui_config.validate({"currency": "USD", "usd_rate": 0.5})
        self.assertEqual("USD", cleaned.get("currency"), cleaned)
        self.assertEqual(0.5, cleaned.get("usd_rate"), cleaned)

        with self.assertRaises(ValueError):
            vibe_ui_config.validate({"currency": "CHF", "usd_rate": 1.0})

        with self.assertRaises(ValueError):
            vibe_ui_config.validate({"currency": "EUR", "usd_rate": 0.001})

        cleaned = vibe_ui_config.validate(
            {"currency": "EUR", "usd_rate": 1.0, "unknown_field": 1})
        self.assertEqual("EUR", cleaned.get("currency"), cleaned)
        self.assertNotIn("unknown_field", cleaned, cleaned)

    def test_ui_settings_api_reads_and_writes_currency_atomically(self):
        """Vorbedingung: isolierter Zustandsordner. Aktion: GET/POST
        ``/api/ui_settings`` mit/ohne Token.
        Erwartung: ohne Token 403; POST speichert; GET liefert.
        """
        status, body, _headers = self.request(
            "GET", "/api/ui_settings", token=NO_TOKEN)
        self.assertEqual(403, status, body)

        status, body, _headers = self.post(
            "/api/ui_settings", {"currency": "USD", "usd_rate": 0.5},
            token=NO_TOKEN)
        self.assertEqual(403, status, body)

        status, body, _headers = self.post(
            "/api/ui_settings", {"currency": "USD", "usd_rate": 0.5})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)

        data = self.get_json("/api/ui_settings")
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("USD", data.get("currency"), data)
        self.assertEqual(0.5, data.get("usd_rate"), data)

        stored = json.loads(
            (self.state / "ui.json").read_text(encoding="utf-8"))
        self.assertEqual("USD", stored.get("currency"), stored)
        self.assertEqual(0.5, stored.get("usd_rate"), stored)


# ---------------------------------------------------------------------------
# WP7.4: Kosten — Monat, months, monthly
# ---------------------------------------------------------------------------

class CostsMonthlyTest(unittest.TestCase):
    """Kosten: Monat je Paket, months und monthly (neueste zuerst)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        # package_catalog ordnet Sitzungen über die Paketkennungen im
        # Ticketspeicher zu; ohne Eintrag kennt der Katalog "F1" nicht.
        (self.proj / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [
                ticket_record("F1", "Testpaket", type="feedback")]},
                ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        self.root.joinpath("_toolchain").mkdir()
        self.db = self.root / "opencode.db"
        self.cli = load_vibe_module(self.root)
        self.cli._pm.clear()
        os.environ["VIBE_OPENCODE_DB"] = str(self.db)

    def tearDown(self):
        os.environ.pop("VIBE_OPENCODE_DB", None)
        self.tmp.cleanup()

    def make_db(self):
        con = sqlite3.connect(str(self.db))
        con.executescript(DDL_V2)
        con.commit()
        return con

    def add_session(self, con, session_id, directory, title, parent=None,
                    agent="coding-agent", time_created=1):
        con.execute(
            "insert into session_v2 (id, project_id, parent_id, slug, directory,"
            " title, version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "proj", parent, "slug-" + session_id, str(directory),
             title, "2.1.4", agent, "model-a", time_created, time_created),
        )

    def add_message(self, con, session_id, agent, model_id, input_tokens=0,
                    output_tokens=0, reasoning=0, cache_read=0, seq=1):
        data = {
            "agent": agent,
            "model": {"id": model_id, "providerID": "opencode"},
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "reasoning": reasoning,
                "cache": {"read": cache_read, "write": 0},
            },
        }
        con.execute(
            "insert into session_message (id, session_id, type, seq, time_created,"
            " time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_" + session_id + "_" + str(seq), session_id, "assistant", seq,
             1, 1, json.dumps(data)),
        )

    def build_usage(self):
        con = self.make_db()
        self.add_session(con, "ses_a", self.proj, "proj F1", time_created=1760000000)
        self.add_message(con, "ses_a", "coding-agent", "model-a",
                        input_tokens=1000, output_tokens=100, reasoning=50,
                        cache_read=3000)
        self.add_session(con, "ses_b", self.proj, "Review F1 (@code-reviewer subagent)",
                         parent="ses_a", agent="code-reviewer", time_created=1790000000)
        self.add_message(con, "ses_b", "code-reviewer", "model-a",
                        input_tokens=500, output_tokens=10, seq=1)
        con.commit()
        con.close()
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 2.0, "cached_input": 0.5, "output": 4.0}})
        return self.cli.costs_project("proj")

    def test_package_reports_month_months_and_monthly(self):
        """Vorbedingung: zwei Sitzungen des Pakets in unterschiedlichen Monaten.
        Aktion: ``costs_project('proj')``.
        Erwartung: ``month`` = YYYY-MM der jüngsten Sitzung, ``months`` mit
        Monatssummen, ``monthly`` neueste zuerst.
        """
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        self.assertEqual("2026-09", package.get("month"),
                         "Package-Monat fehlt oder falsch: " + repr(package))
        self.assertIn("2026-09", package.get("months") or {},
                     "months fehlt oder unvollständig: " + repr(package))
        monthly = package.get("monthly")
        self.assertIsInstance(monthly, list, "monthly fehlt oder falsch: " + repr(package))
        self.assertEqual(2, len(monthly), "monthly enthält nicht alle Monate: " + repr(monthly))
        self.assertEqual("2026-09", monthly[0].get("month"),
                         "monthly ist nicht neueste zuerst: " + repr(monthly))
        self.assertEqual("2025-10", monthly[-1].get("month"),
                         "monthly ist nicht aufsteigend/neueste zuerst: " + repr(monthly))

    def test_overview_reports_monthly_overall_and_per_project_row(self):
        """Vorbedingung: wie oben. Aktion: ``costs_overview()``.
        Erwartung: ``monthly`` overall und je Projektzeile ``monthly``.
        """
        self.build_usage()
        data = self.cli.costs_overview()
        self.assertIsInstance(data.get("monthly"), list, "costs_overview: monthly fehlt")
        rows = {row["name"]: row for row in data.get("projects") or []}
        self.assertIn("proj", rows, "Projektzeile fehlt: " + repr(list(rows)))
        self.assertIsInstance(rows["proj"].get("monthly"), list,
                             "Projektzeile ohne monthly: " + repr(rows["proj"]))


# ---------------------------------------------------------------------------
# WP7.6: Run-Cleanup
# ---------------------------------------------------------------------------

class RunCleanupTest(BackendContractsDashboard):
    """POST /api/runs {action:'cleanup'} und unverändertes prune."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_runs_cleanup_removes_only_completed_entries(self):
        """Vorbedingung: Register mit abgeschlossenem und laufendem Eintrag.
        Aktion: POST ``/api/runs {action:"cleanup"}``.
        Erwartung: ``{removed, remaining}``; nur abgeschlossene entfernt.
        """
        registry = vibe_runs.RunRegistry(str(self.log_dir))
        registry.start(project=str(self.project), name="proj", key="proj",
                       agent="vibe-agent", session="", state="finished")
        registry.start(project=str(self.project), name="proj", key="proj-2",
                       agent="vibe-agent", session="", state="running")
        status, body, _headers = self.post("/api/runs", {"action": "cleanup"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        self.assertEqual(1, data.get("removed"), "Cleanup hat falsche Anzahl "
                         "entfernt: " + repr(data))
        self.assertEqual(1, data.get("remaining"), "Cleanup hat falsche Anzahl "
                         "übrig gelassen: " + repr(data))
        records = self.get_json("/api/runs")["records"]
        self.assertEqual(1, len(records), "Cleanup hat den Lauf nicht entfernt: "
                         + repr(records))
        self.assertEqual("running", records[0].get("state"),
                         "Cleanup hat einen laufenden Eintrag entfernt: " + repr(records))

    def test_runs_prune_unchanged_keeps_live_entries(self):
        """Vorbedingung: Register mit abgeschlossenem Eintrag.
        Aktion: POST ``/api/runs {action:"prune"}``.
        Erwartung: Prune unverändert; laufende Sitzung nicht beendet.
        """
        registry = vibe_runs.RunRegistry(str(self.log_dir))
        registry.start(project=str(self.project), name="proj", key="proj",
                       agent="vibe-agent", session="", state="finished")
        status, body, _headers = self.post("/api/runs", {"action": "prune"})
        self.assertEqual(200, status, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), body)
        self.assertEqual(0, data.get("ended"), "Prune hat einen nicht-liveligen "
                         "Eintrag beendet: " + repr(data))
        records = self.get_json("/api/runs")["records"]
        self.assertEqual(1, len(records), "Prune hat einen Eintrag entfernt")


# ---------------------------------------------------------------------------
# WP7.7: Statische Auslieferung
# ---------------------------------------------------------------------------

class StaticDeliveryTest(BackendContractsDashboard):
    """GET /static/nova-evals.js, WEB_FILES und Import-Manifest."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_static_nova_evals_js_is_served_as_javascript(self):
        """Vorbedingung: laufendes Dashboard. Aktion: GET
        ``/static/nova-evals.js``.
        Erwartung: 200 plus JavaScript-Inhalt.
        """
        status, body, headers = self.request(
            "GET", "/static/nova-evals.js", token=NO_TOKEN)
        self.assertEqual(200, status, body)
        self.assertIn("javascript", headers.get("Content-Type", ""),
                     "nova-evals.js wird nicht als JavaScript ausgeliefert")
        self.assertTrue(len(body) > 0, "nova-evals.js wurde ohne Inhalt "
                         "ausgeliefert")

    def test_setup_vibe_web_files_and_manifest_contain_nova_evals(self):
        """Vorbedingung: Installations- und Manifestquellen.
        Aktion: Dateien prüfen.
        Erwartung: ``nova-evals.js`` in ``WEB_FILES`` und im Import-Manifest.
        """
        setup_source = (REPO / "scripts" / "setup-vibe.py").read_text(
            encoding="utf-8")
        self.assertIn('"nova-evals.js"', setup_source,
                     "nova-evals.js fehlt in WEB_FILES (scripts/setup-vibe.py)")
        manifest = json.loads(
            (REPO / "docs" / "import-manifest.json").read_text(encoding="utf-8"))
        paths = [entry.get("path") for entry in manifest.get("files") or []]
        self.assertIn("bin/web/nova-evals.js", paths,
                      "nova-evals.js fehlt im Import-Manifest")


if __name__ == "__main__":
    unittest.main()
