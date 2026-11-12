"""Unabhängige Abnahme AP13: Web-Zugriffssicherheit (Session, Security-API).

Die Fälle leiten sich aus dem Arbeitspaket AP13 (TICKETS.md) und SPEC.md
(„Sicherheit und Datenintegrität") ab. Getestet wird das echte Dashboard als
eigener Prozess auf freiem Port mit vollständig isolierten VIBE_*/HOME-Pfaden
(Muster tests/unit/test_web_api_security.py):

* Allowlist-Prüfung je Anfrage vor allen anderen Prüfungen; abgelehnt =
  403 ``forbidden_ip``; Loopback immer erlaubt (Aussperrschutz). Da die
  Tests von Loopback laufen, werden echte Ablehnungen mit einem Server an
  ``0.0.0.0`` über die Nicht-Loopback-Adresse dieses Rechners geprüft; fehlt
  eine solche Adresse im Testsystem, wird der HTTP-Teil übersprungen und
  die Ablehnung nur auf ``client_allowed``-Ebene (test_ap13_network_config)
  geprüft.
* Authentisierung: HttpOnly-Session-Cookie ``vibe_session`` (SameSite=Strict,
  Path=/), weiterhin ``X-Token``, ``?t=`` nur für ``/api/stream``. Ohne
  gültige Berechtigung 403 ``unauthorized``. ``/``, ``/static/*`` und
  ``/api/health`` bleiben ohne Auth lesbar.
* ``POST /api/login`` akzeptiert Instanz-Token oder (wenn gesetzt) Passwort;
  Erfolg setzt Session-Cookie und antwortet ``{ok:true}``; Misserfolg 403
  strukturiert ohne Kennwortdetails. ``POST /api/logout`` beendet die
  Session.
* ``GET/POST /api/security``: Ansicht von Port/Bind/Allowlist/Passwortstatus/
  restart_required; Speichern validiert und schreibt ui.json; ungültige
  Eingaben → 400 ohne Dateiänderung.
* Host/Origin: reine IP-Literale (IPv4/IPv6) erlaubt, DNS-Hostnamen
  abgelehnt; Origin mit passendem Port.
* Tokens und Passwörter erscheinen nie in Logs oder Antworten.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``LoginFlowTest.test_health_and_page_and_static_stay_readable_without_auth``
    Vorbedingung: laufendes Dashboard. Aktion: GET ``/``, ``/static/app.js``,
    ``/api/health`` ohne Berechtigung. Erwartung: je 200 (Bestand bleibt).
``LoginFlowTest.test_login_with_instance_token_sets_a_session_cookie``
    Aktion: POST ``/api/login`` mit Token. Erwartung: 200 ``{ok:true}``,
    Set-Cookie ``vibe_session`` mit HttpOnly, SameSite=Strict, Path=/.
``LoginFlowTest.test_cookie_authorizes_get_and_post`` /
``test_cookie_write_still_requires_same_origin`` /
``test_logout_ends_the_session`` /
``test_forged_cookie_value_is_rejected`` /
``test_wrong_token_and_wrong_password_are_rejected_structured`` /
``test_x_token_header_still_works`` /
``test_query_token_is_only_accepted_for_the_stream`` /
``test_password_login_after_setting_it_via_security_api``
    Aktion/Erwartung: wie in der jeweiligen Methode dokumentiert; keine
    Kennwort- oder Token-Auskunft in Fehlern.
``SecurityApiTest.test_security_view_requires_authorization`` /
``test_security_view_reports_current_values`` /
``test_security_save_writes_ui_json_and_flags_restart`` /
``test_security_save_rejects_invalid_values_without_change`` /
``test_password_actions_validate_and_take_effect`` /
``test_password_is_never_in_logs_or_responses``
    Aktion/Erwartung: wie dokumentiert; ui.json-Änderung nur bei gültigen
    Eingaben.
``HostOriginLiteralTest.test_host_with_ip_literal_is_allowed`` /
``test_dns_hostnames_stay_rejected`` /
``test_origin_with_ip_literal_and_matching_port_is_allowed`` /
``test_origin_with_wrong_port_is_rejected``
    Aktion: GET/POST mit entsprechendem Host-/Origin-Header. Erwartung: wie
    dokumentiert.
``AllowlistHttpTest.test_open_server_allows_the_local_network_ip`` /
``test_allowlist_admitting_the_local_ip_allows_it`` /
``test_allowlist_denying_the_local_ip_returns_forbidden_ip`` /
``test_loopback_stays_allowed_with_a_restrictive_allowlist``
    Vorbedingung: drei isolierte Dashboards an 0.0.0.0 mit verschiedenen
    ui.json. Aktion: HTTP von Loopback und von der Nicht-Loopback-Adresse
    dieses Rechners. Erwartung: wie dokumentiert; ohne Nicht-Loopback-Adresse
    skip mit Begründung (dann Funktionsebene im Unit-Modul).

Keine echten externen Dienste, keine produktiven Konfigurationen. Der
Testserver läuft ausschließlich an Adressen dieses Rechners.
"""
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def local_non_loopback_ip():
    """Die eigene Nicht-Loopback-IPv4 oder None, wenn es keine gibt."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    if not address or address.startswith("127."):
        return None
    return address


class DashboardFixture(unittest.TestCase):
    """Startet ein echtes Dashboard mit isolierten Pfaden und eigener ui.json."""

    ui_json_data = None  # vom setUpClass der Unterklasse gesetzt

    @classmethod
    def start_server(cls, ui_json_data=None):
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
        if ui_json_data is not None:
            (cls.state / "ui.json").write_text(
                json.dumps(ui_json_data), encoding="utf-8"
            )
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
        via=None,
        port=None,
    ):
        """HTTP-Anfrage mit voller Header-Kontrolle; via=Client-IP.

        ``port`` adressiert einen der Extra-Server der Allowlist-Fälle;
        ohne Angabe wird der Klassen-Server angesprochen.
        """
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        port = self.port if port is None else port
        headers = {
            "Host": host if host is not None else f"127.0.0.1:{port}"
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
        connection = http.client.HTTPConnection(
            via or "127.0.0.1", port, timeout=10
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def login(self, field, value, origin=None):
        """POST /api/login und Rückgabe (status, body, cookie)."""
        status, body, headers = self.request(
            "POST",
            "/api/login",
            body={field: value},
            token=None,
            origin=origin or f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        cookie_header = None
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                cookie_header = value
        return status, body, cookie_header

    def session_cookie(self, field="token", value=None):
        """Meldet sich an und liefert den Cookie-String 'vibe_session=...'."""
        status, body, cookie_header = self.login(field, value or self.token)
        assert status == 200, body
        assert cookie_header, "Login setzte keinen Cookie: " + body
        match = re.search(r"vibe_session=([^;]+)", cookie_header)
        assert match, cookie_header
        return "vibe_session=" + match.group(1)

    def ui_json_path(self):
        return self.state / "ui.json"


class LoginFlowTest(DashboardFixture):
    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_health_and_page_and_static_stay_readable_without_auth(self):
        status, body, _ = self.request("GET", "/api/health", token=None)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["app"], "vibe", body)

        status, page, headers = self.request("GET", "/", token=None)
        self.assertEqual(status, 200, page)
        self.assertIn("text/html", headers.get("Content-Type", ""))

        status, asset, _ = self.request("GET", "/static/app.js", token=None)
        self.assertEqual(status, 200, asset)

    def test_reads_without_credentials_are_rejected(self):
        status, body, _ = self.request("GET", "/api/projects", token=None)
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_login_with_instance_token_sets_a_session_cookie(self):
        status, body, cookie = self.login("token", self.token)

        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)
        self.assertIn("vibe_session=", cookie)
        self.assertIn("HttpOnly", cookie, "Cookie ist nicht HttpOnly")
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn(self.token, cookie, "Cookie trägt das Token im Klartext")

    def test_wrong_token_and_wrong_password_are_rejected_structured(self):
        status, body, cookie = self.login("token", "falsches-token")
        self.assertEqual(status, 403, body)
        error = json.loads(body)["error"]
        self.assertTrue(error["code"], body)
        self.assertTrue(error["message"], body)
        self.assertFalse(json.loads(body)["ok"], body)
        self.assertIsNone(cookie, "Fehlgeschlagener Login setzte einen Cookie")

    def test_cookie_authorizes_get_and_post(self):
        cookie = self.session_cookie()

        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(json.loads(body), list)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

    def test_cookie_write_still_requires_same_origin(self):
        cookie = self.session_cookie()

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=None,
            cookie=cookie,
            origin="http://evil.example",
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden_origin")

    def test_logout_ends_the_session(self):
        cookie = self.session_cookie()
        status, body, set_cookie = self.request(
            "POST",
            "/api/logout",
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie=cookie
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_forged_cookie_value_is_rejected(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie="vibe_session=forged"
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_x_token_header_still_works(self):
        status, body, _ = self.request("GET", "/api/projects", token=self.token)
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

    def test_query_token_is_only_accepted_for_the_stream(self):
        status, body, _ = self.request(
            "GET", f"/api/projects?t={self.token}", token=None
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

        # Der Stream endet nicht von allein; wir lesen nur den Antwortkopf
        # und schließen die Verbindung danach.
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(
                "GET",
                f"/api/stream?name=proj&kind=run&t={self.token}",
                headers={"Host": f"127.0.0.1:{self.port}"},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200, response.status)
            self.assertIn(
                "text/event-stream", response.getheader("Content-Type") or ""
            )
        finally:
            connection.close()

    def test_password_login_after_setting_it_via_security_api(self):
        # Passwort setzen geht nur über die geschützte Security-API.
        cookie = self.session_cookie()
        status, body, _ = self.request(
            "POST",
            "/api/security",
            body={"action": "password", "password": "ap13-paswort-lang-42"},
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.login("password", "ap13-paswort-lang-42")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        status, body, _ = self.login("password", "falsches kennwort")
        self.assertEqual(status, 403, body)
        self.assertNotIn(
            "ap13-paswort-lang-42", body, "Fehler verrät das Kennwort"
        )

        # Token-Login bleibt daneben weiterhin gültig.
        status, body, _ = self.login("token", self.token)
        self.assertEqual(status, 200, body)


class SecurityApiTest(DashboardFixture):
    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def session(self):
        return self.session_cookie()

    def security_request(self, body, cookie=None, token=None):
        return self.request(
            "POST",
            "/api/security",
            body=body,
            token=token,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )

    def test_security_view_requires_authorization(self):
        status, body, _ = self.request("GET", "/api/security", token=None)
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_security_view_reports_current_values(self):
        for credentials in ({"token": self.token}, {"cookie": self.session()}):
            with self.subTest(credentials=sorted(credentials)):
                status, body, _ = self.request(
                    "GET", "/api/security", **credentials
                )
                self.assertEqual(status, 200, body)
                data = json.loads(body)
                self.assertTrue(data["ok"], body)
                self.assertEqual(data["port"], self.port)
                self.assertEqual(data["bind"], "127.0.0.1")
                self.assertEqual(data["allowlist"], [])
                self.assertFalse(data["password_set"])
                self.assertFalse(
                    data["restart_required"],
                    "Ohne ui.json ist kein Neustart nötig",
                )

    def test_security_save_writes_ui_json_and_flags_restart(self):
        cookie = self.session()
        new_port = free_port()

        status, body, _ = self.security_request(
            {"action": "save", "port": new_port, "bind": "0.0.0.0"}, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        stored = json.loads(self.ui_json_path().read_text(encoding="utf-8"))
        self.assertEqual(stored.get("ui_port"), new_port)
        self.assertEqual(stored.get("ui_bind"), "0.0.0.0")

        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        data = json.loads(body)
        self.assertTrue(data["restart_required"], body)

        # Zurücksetzen auf die laufenden Werte hebt die Neustart-Markierung.
        status, body, _ = self.security_request(
            {"action": "save", "port": self.port, "bind": "127.0.0.1"},
            cookie=cookie,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertFalse(json.loads(body)["restart_required"], body)

    def test_security_save_rejects_invalid_values_without_change(self):
        cookie = self.session()
        before = (
            self.ui_json_path().read_text(encoding="utf-8")
            if self.ui_json_path().exists()
            else None
        )

        for bad in (
            {"action": "save", "port": 70000},
            {"action": "save", "port": 0},
            {"action": "save", "bind": "example.test"},
            {"action": "save", "allowlist": ["nicht-ip"]},
            {"action": "save", "allowlist": "keine liste"},
            {"action": "unbekannt"},
        ):
            with self.subTest(bad=bad):
                status, body, _ = self.security_request(bad, cookie=cookie)
                self.assertEqual(status, 400, body)
                error = json.loads(body)["error"]
                self.assertTrue(error["code"], body)
                self.assertTrue(error["message"], body)

        after = (
            self.ui_json_path().read_text(encoding="utf-8")
            if self.ui_json_path().exists()
            else None
        )
        self.assertEqual(before, after, "Ungültige Eingabe veränderte ui.json")

    def test_password_actions_validate_and_take_effect(self):
        cookie = self.session()

        status, body, _ = self.security_request(
            {"action": "password", "password": "kurz"}, cookie=cookie
        )
        self.assertEqual(status, 400, body)

        status, body, _ = self.security_request(
            {"action": "password", "password": "ap13-paswort-lang-99"},
            cookie=cookie,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertTrue(json.loads(body)["password_set"], body)
        self.assertFalse(
            "ap13-paswort-lang-99" in body, "Antwort enthält das Kennwort"
        )

        # Anmeldung mit dem neuen Passwort, dann Entfernen.
        status, body, _ = self.login("password", "ap13-paswort-lang-99")
        self.assertEqual(status, 200, body)

        status, body, _ = self.security_request(
            {"action": "password", "clear": True}, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertFalse(json.loads(body)["password_set"], body)
        status, body, _ = self.login("password", "ap13-paswort-lang-99")
        self.assertEqual(status, 403, body)

    def test_password_is_never_in_logs_or_responses(self):
        kennwort = "ap13-topsecret-pass-77"
        cookie = self.session()
        self.security_request(
            {"action": "password", "password": kennwort}, cookie=cookie
        )
        self.login("password", "falsch-geraten-123")
        self.login("password", kennwort)
        time.sleep(0.5)

        log = self.server_log()
        self.assertNotIn(kennwort, log, "Kennwort steht im Server-Log")
        self.assertNotIn("falsch-geraten-123", log)
        self.assertNotIn(self.token, log)

        security = self.request("GET", "/api/security", token=self.token)
        self.assertNotIn(kennwort, security[1])
        self.assertNotIn("falsch-geraten-123", security[1])

        # Aufräumen: Kennwort entfernen, damit keine Erwartung eines
        # späteren Tests von der Ausführungsreihenfolge abhängt.
        status, body, _ = self.security_request(
            {"action": "password", "clear": True}, cookie=cookie
        )
        self.assertEqual(status, 200, body)


class HostOriginLiteralTest(DashboardFixture):
    """Netzwerkbetrieb erweitert die Host-/Origin-Prüfung auf IP-Literale."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_host_with_ip_literal_is_allowed(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, host=f"192.0.2.10:{self.port}"
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, host=f"[::1]:{self.port}"
        )
        self.assertEqual(status, 200, body)

    def test_dns_hostnames_stay_rejected(self):
        for host in ("vibe.example", "127.0.0.1.evil.example"):
            with self.subTest(host=host):
                status, body, _ = self.request(
                    "GET",
                    "/api/projects",
                    token=self.token,
                    host=f"{host}:{self.port}",
                )
                self.assertEqual(status, 403, body)
                self.assertEqual(
                    json.loads(body)["error"]["code"], "forbidden_host"
                )

    def test_origin_with_ip_literal_and_matching_port_is_allowed(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            host=f"192.0.2.10:{self.port}",
            origin=f"http://192.0.2.10:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            origin=f"http://192.0.2.10:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

    def test_origin_with_wrong_port_is_rejected(self):
        for origin in (
            f"http://192.0.2.10:{self.port + 1}",
            f"http://[::1]:{self.port + 1}",
            "http://192.0.2.10",
        ):
            with self.subTest(origin=origin):
                status, body, _ = self.request(
                    "POST",
                    "/api/pause",
                    body={"name": "proj", "action": "on"},
                    token=self.token,
                    origin=origin,
                    extra_headers={"Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(status, 403, body)
                self.assertEqual(
                    json.loads(body)["error"]["code"], "forbidden_origin"
                )


class AllowlistHttpTest(DashboardFixture):
    """Allowlist auf HTTP-Ebene; Loopback bleibt immer erlaubt."""

    @classmethod
    def setUpClass(cls):
        cls.local_ip = local_non_loopback_ip()
        if cls.local_ip is None:
            raise unittest.SkipTest(
                "Keine Nicht-Loopback-Adresse im Testsystem; Allowlist-Ablehnung "
                "wird auf Funktionsebene (test_ap13_network_config) geprüft"
            )
        cls.servers = []

    @classmethod
    def tearDownClass(cls):
        # Erst die Extra-Server stoppen, dann den Klassen-Server und zuletzt
        # den isolierten Bereich aufräumen; sonst bleiben Dashboards als
        # verwaiste Prozesse zurück. (Der Aufruf des Basis-tearDowns bindet
        # an DashboardFixture selbst, deshalb explizit hier.)
        for server in cls.servers:
            server()
        if getattr(cls, "proc", None) is not None and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if getattr(cls, "log_file", None) is not None:
            cls.log_file.close()
        if getattr(cls, "tmp", None) is not None and cls.tmp is not None:
            cls.tmp.cleanup()

    @classmethod
    def open_extra_server(cls, ui_json_data):
        """Startet ein weiteres Dashboard in demselben isolierten Bereich.

        Es erbt die isolierten Pfade und bekommt eigene Port-/Zustandsdaten;
        die Allowlist steckt ausschließlich in ui.json. Rückgabe (port, token).
        """
        port = free_port()
        extra_state = cls.root / f"state-{port}"
        extra_state.mkdir()
        (extra_state / "ui.json").write_text(
            json.dumps(ui_json_data), encoding="utf-8"
        )
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(extra_state),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        log_path = cls.root / f"server-{port}.log"
        log_file = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        previous_token = (
            token_file.read_text(encoding="utf-8") if token_file.exists() else None
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if proc.poll() is not None:
                log_file.close()
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + log_path.read_text(encoding="utf-8")
                )
            current = (
                token_file.read_text(encoding="utf-8")
                if token_file.exists()
                else ""
            )
            if current and current != previous_token:
                try:
                    with socket.create_connection(
                        ("127.0.0.1", port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            log_file.close()
            raise AssertionError("Extra-Server ist nicht erreichbar")
        token = current.strip()

        def stop():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            log_file.close()

        cls.servers.append(stop)
        return port, token

class AllowlistOpenServerTest(AllowlistHttpTest):
    @classmethod
    def setUpClass(cls):
        AllowlistHttpTest.setUpClass()
        cls.start_server({"ui_bind": "0.0.0.0", "allowlist": []})
        cls.open_port, cls.open_token = cls.open_extra_server(
            {"ui_bind": "0.0.0.0", "allowlist": []}
        )

    def test_open_server_allows_the_local_network_ip(self):
        status, body, _ = self.request(
            "GET", "/api/health", token=None, via=self.local_ip
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=self.open_token,
            via=self.local_ip, port=self.open_port,
        )
        self.assertEqual(status, 200, body)


class AllowlistRestrictiveServerTest(AllowlistHttpTest):
    @classmethod
    def setUpClass(cls):
        AllowlistHttpTest.setUpClass()
        cls.start_server(
            {"ui_bind": "0.0.0.0", "allowlist": ["203.0.113.7"]}
        )
        cls.admitting_port, cls.admitting_token = cls.open_extra_server(
            {"ui_bind": "0.0.0.0", "allowlist": [cls.local_ip]}
        )

    def test_allowlist_admitting_the_local_ip_allows_it(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.admitting_token,
            via=self.local_ip, port=self.admitting_port,
        )
        self.assertEqual(status, 200, body)
        # Loopback ist trotz Allowlist immer erlaubt (Aussperrschutz);
        # dieselbe Anfrage von Loopback an denselben Server.
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.admitting_token,
            port=self.admitting_port,
        )
        self.assertEqual(status, 200, body)

    def test_allowlist_denying_the_local_ip_returns_forbidden_ip(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, via=self.local_ip
        )
        self.assertEqual(status, 403, body)
        error = json.loads(body)["error"]
        self.assertEqual(error["code"], "forbidden_ip")
        self.assertTrue(error["message"], body)
        self.assertNotIn(self.local_ip, body, "Fehler verrät die Client-IP?")

    def test_loopback_stays_allowed_with_a_restrictive_allowlist(self):
        status, body, _ = self.request("GET", "/api/projects", token=self.token)
        self.assertEqual(status, 200, body)

    def test_source_really_is_the_non_loopback_address(self):
        # Vorbedingung der HTTP-Ebene: Verbindungen zur Nicht-Loopback-Adresse
        # dieses Rechners tragen sie auch als Quelladresse (sonst wäre der
        # Test ein Loopback-Test und beweist nichts).
        with socket.create_connection(
            (self.local_ip, self.port), timeout=5
        ) as probe:
            self.assertEqual(probe.getsockname()[0], self.local_ip)


if __name__ == "__main__":
    unittest.main()
