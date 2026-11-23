"""Unabhängige Abnahme AP22: Server-Vertrag der neuen Oberfläche.

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Server-Vertrag“) und
``SPEC.md`` („Qualität und Abnahme“, „Sicherheit und Datenintegrität“) ab.
Getestet wird das echte Dashboard als eigener Prozess auf freiem Port mit
vollständig isolierten VIBE_*/HOME-Pfaden (Muster
``tests/unit/test_ap13_web_access.py``):

* ``GET /`` liefert die neue Shell (``web/index.html``) mit ``data-nv-app``;
  die alten Marker (``<nav id="nav">``) gehören nicht mehr dorthin.
* ``GET /classic`` liefert unverändert die alte Shell mit ``id="nav"`` und
  ``/static/app.js``; unbekannte Pfade bleiben 404. Host-Guard und
  Tokenpflicht gelten für beide Seiten gleich.
* ``STATIC_FILES`` enthält ``/static/nova.css`` und die sieben
  ``/static/nova-*.js``-Dateien aus dem Vertrag.
* Neue lesende/schreibende Endpunkte über die bestehenden Dienste:
  ``/api/limits``, ``/api/gates``, ``/api/runs``, ``/api/emu``,
  ``/api/paths``. Alle verlangen eine Berechtigung (ohne Token 403
  ``unauthorized``), Fachfehler sind ``200 {"ok": false, "message": …}`` und
  dürfen keinen Schreibvorgang auslösen.
* ``POST /api/sessions`` kennt neben ``continue`` die Aktion ``limit``
  (CLI-Parität zu ``vibe sessions limit N``). Gültig ist ein ganzzahliger
  Wert von 1 bis ``vibe_runs.SESSION_LIMIT_MAX``. Mit ``name`` wird das
  Projektlimit über ``SessionRegistry.set_project_limit`` gespeichert, ohne
  ``name`` das globale ``set_limit``; ein anschließendes
  ``GET /api/sessions?name=…`` meldet das wirksame Limit. Ungültige Werte
  und unbekannte Aktionen antworten ``ok:false`` ohne Schreibvorgang.

F34-Anpassung: Das Sitzungslimit gilt je Projekt. Die Sessions-Fälle prüfen
deshalb beide Scopes — Projekt-Override (``project_limits``, Schlüssel
realpath) und globales Registerlimit — und dass ein ungültiger Wert in keinem
Scope schreibt.

Vertragsdetails, die hier festgehalten werden:

* Schranken-Schlüssel sind die Schlüssel aus ``vibe_gates.DEFAULTS``
  (``repair_rounds``, ``assist_rounds``, ``retries``, ``packages``,
  ``override``). Nur diese akzeptiert ``vibe_gates.validate``, und
  ``vibe_gates.PROJECT_ENV_KEYS`` bildet sie auf die Projektvariablen
  (``REPAIR_ROUNDS``, ``MAX_RETRIES``, ``GATE_OVERRIDE`` …) ab. Die Antwort
  von ``GET /api/gates`` trägt genau diese Schlüssel mit ``value`` und
  ``origin`` (``Standard``/``global``/``projekt``/``Umgebung``).
* ``/api/emu`` wählt das Projekt über die bestehende Projektauflösung; im
  isolierten Arbeitsbereich ohne Android-Projekt antwortet es mit
  ``ok:false`` und einer Meldung, die „Android“ nennt.
* ``/api/paths`` gibt ausschließlich Pfade/Ports aus und enthält keine
  Geheimnisse (kein Instanz-Token).

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ShellRoutingTest.test_root_serves_the_new_shell_without_auth``
``ShellRoutingTest.test_classic_serves_the_old_shell_without_auth``
``ShellRoutingTest.test_unknown_path_stays_not_found``
``ShellRoutingTest.test_both_pages_keep_the_host_guard``
``ShellRoutingTest.test_static_map_serves_all_nova_files``
    Vorbedingung: laufendes Dashboard. Aktion: Seiten/Assets ohne bzw. mit
    fremdem Host-Header abrufen. Erwartung: wie im Vertrag; unbekannte Datei
    404.
``LimitsApiTest.test_limits_view_requires_token_and_reports_stop``
``LimitsApiTest.test_limits_post_continue_persists_in_state``
``LimitsApiTest.test_limits_unknown_action_changes_nothing``
    Vorbedingung: kein ``limits.json``. Aktion: GET/POST ``/api/limits``.
    Erwartung: Default ``stop``; ``continue`` landet über
    ``vibe_limits.save`` in ``<state>/limits.json``; unbekannte Aktion →
    ``ok:false`` ohne Dateiänderung.
``GatesApiTest.test_gates_view_requires_token_and_lists_defaults``
``GatesApiTest.test_gates_view_with_project_reports_project_view``
``GatesApiTest.test_gates_global_save_sets_effective_value``
``GatesApiTest.test_gates_invalid_value_changes_nothing``
``GatesApiTest.test_gates_unknown_key_changes_nothing``
``GatesApiTest.test_gates_project_override_sets_and_removes_env_key``
    Vorbedingung: registriertes Projekt ``proj`` mit ``.vibe/project.env``.
    Aktion: GET/POST ``/api/gates`` global und mit ``project``. Erwartung:
    wirksame Ansicht wie ``vibe_gates.effective``; Projektwert als
    ``PROJECT_ENV_KEYS``-Zeile in ``project.env``; leerer Wert entfernt sie.
``RunsApiTest.test_runs_view_requires_token_and_is_empty``
``RunsApiTest.test_runs_prune_on_empty_register_is_a_no_op``
``RunsApiTest.test_runs_unknown_action_is_rejected``
    Vorbedingung: frisches Laufregister. Aktion: GET/POST ``/api/runs``.
    Erwartung: ``records: []``; Prune meldet 0/0/0 und beendet nichts;
    unbekannte Aktion → ``ok:false``.
``SessionsApiTest.test_sessions_limit_post_persists_and_is_reported``
``SessionsApiTest.test_sessions_limit_invalid_values_change_nothing``
    Vorbedingung: kein ``sessions.json`` (Standardlimit). Aktion: POST
    ``/api/sessions`` mit ``action:"limit"``, mit und ohne ``name``.
    Erwartung (F34): ``name`` setzt das Projektlimit in ``project_limits``
    und wird von ``GET /api/sessions?name=`` gemeldet; ohne ``name`` gilt das
    globale Registerlimit; 0, ``"abc"``, ein Wert über dem Maximum und eine
    unbekannte Aktion antworten in beiden Scopes ``ok:false`` ohne
    Dateiänderung; ohne Token 403.
``EmuApiTest.test_emu_without_android_project_is_rejected``
    Vorbedingung: nur ein generisches Projekt. Aktion: POST ``/api/emu``
    ``{"action":"start"}``. Erwartung: ``ok:false`` mit Meldung „Android“;
    ohne Token 403.
``PathsApiTest.test_paths_requires_token_and_leaks_no_secrets``
    Vorbedingung: isolierte Pfade. Aktion: GET ``/api/paths``. Erwartung:
    ``ok:true`` mit den aufgelösten Pfaden; kein Token in der Antwort.

Keine echten externen Dienste, keine produktiven Konfigurationen. Der
Testserver läuft ausschließlich auf Loopback dieses Rechners.
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


if __name__ == "__main__":
    unittest.main()
