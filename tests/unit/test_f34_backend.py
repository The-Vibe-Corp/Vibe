"""Unit-Abnahme F34, WP7: Backend-Verträge (Löschschutz, Projektlimit,
Gates gesammelt, Kosten-Monate, Währung, Run-Cleanup, Statische Auslieferung).

Das Arbeitspaket F34 verlangt neue Backend-Verträge, die noch nicht
implementiert sind (dokumentierte Rotphase vor Implementierung). Die Fälle
leiten sich aus ``docs/features/F34.md`` („WP7 — Backend-Verträge“) ab.

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
------------------------------------------------
DeleteProtectionTest
  * ``test_feedback_delete_rejects_a_closed_entry_and_keeps_the_file`` —
    Vorbedingung: FEEDBACK.md mit geschlossenem Eintrag (``- [x]`` plus
    Commit/Test-Nachweis). Aktion: ``vibe.feedback_delete``. Erwartung:
    ``ValueError``; Datei unverändert.
  * ``test_ticket_delete_rejects_a_closed_entry_and_keeps_the_file`` —
    Vorbedingung: TICKETS.md mit geschlossenem Eintrag (``- [x]``). Aktion:
    ``vibe.ticket_delete``. Erwartung: ``ValueError``; Datei unverändert.
  * ``test_open_entries_stay_deletable`` — Vorbedingung: FEEDBACK/TICKETS mit
    offenem Eintrag. Aktion: Delete. Erwartung: Eintrag wird entfernt.

SessionLimitPerProjectTest
  * ``test_project_limit_defaults_to_none_and_set_project_limit_stores_it`` —
    Vorbedingung: leeres Register. Aktion: ``set_project_limit``. Erwartung:
    gespeichert unter ``project_limits`` (realpath-Schlüssel), Rücklesen über
    ``project_limit``.
  * ``test_project_limit_rejects_invalid_values`` — Vorbedingung: Limit 2.
    Aktion: ``set_project_limit`` mit 0/-1/>MAX. Erwartung: ``ValueError``,
    gespeicherter Wert bleibt.

GatesCollectedTest
  * ``test_gates_collected_batch_sets_a_project_override`` — POST
    ``/api/gates {project, values}``. Erwartung: Alle Werte validiert,
    Projekt-Override landet in ``.vibe/project.env``, Antwort mit
    defaults/overrides/global/origin je Schranke.
  * ``test_gates_collected_batch_invalid_value_writes_nothing`` — POST mit
    einem ungültigen Wert. Erwartung: ``ok:false``, nichts geschrieben.
  * ``test_gates_collected_batch_empty_project_value_removes_override`` —
    POST mit leerem Projektwert. Erwartung: Override entfernt, Rückfall auf
    global/Standard.
  * ``test_gates_single_post_still_sets_the_global_value`` — POST ``{key, value}``.
    Erwartung: unverändertes Single-POST-Verhalten.

CurrencyUiSettingsTest
  * ``test_vibe_ui_config_validate_accepts_eur_usd_and_rejects_invalid_values`` —
    Vorbedingung: ``vibe_ui_config.validate``. Aktion: EUR/USD, ``usd_rate``,
    unbekannte Felder. Erwartung: akzeptiert und validiert, ``ValueError`` bei
    ungültigem ``usd_rate``/currency, unbekannte Felder entfernt.
  * ``test_ui_settings_api_reads_and_writes_currency_atomically`` —
    Vorbedingung: isolierter Zustandsordner. Aktion: GET/POST
    ``/api/ui_settings`` mit/ohne Token. Erwartung: 403 ohne Token, POST
    speichert ``currency``/``usd_rate`` in ``ui.json``, GET liefert sie.

CostsMonthlyTest
  * ``test_package_reports_month_months_and_monthly`` — Vorbedingung: Sitzungs-
    Datenbank mit Sitzungen in zwei Monaten. Aktion: ``costs_project``. Erwartung:
    ``month`` (YYYY-MM der jüngsten Sitzung), ``months``, ``monthly`` neueste
    zuerst.
  * ``test_overview_reports_monthly_overall_and_per_project_row`` — Vorbedingung
    wie oben. Aktion: ``costs_overview``. Erwartung: ``monthly`` overall und je
    Projektzeile ``monthly``.

RunCleanupTest
  * ``test_runs_cleanup_removes_only_completed_entries`` — POST
    ``/api/runs {action:"cleanup"}``. Erwartung: ``{removed, remaining}``, nur
    abgeschlossene Einträge entfernt, laufender Eintrag bleibt.
  * ``test_runs_prune_unchanged_keeps_live_entries`` — POST
    ``/api/runs {action:"prune"}``. Erwartung: unverändertes Prune-Verhalten,
    laufende Sitzung wird nicht beendet.

StaticDeliveryTest
  * ``test_static_nova_evals_js_is_served_as_javascript`` — Vorbedingung: laufendes
    Dashboard. Aktion: GET ``/static/nova-evals.js``. Erwartung: 200 plus
    JavaScript-Inhalt.
  * ``test_setup_vibe_web_files_and_manifest_contain_nova_evals`` — Vorbedingung:
    Installations- und Manifestquellen. Aktion: Dateien prüfen. Erwartung:
    ``nova-evals.js`` in ``WEB_FILES`` und im Import-Manifest.

Alle Fälle laufen ohne Netz außer Loopback, ohne echten Modellaufruf und in
temporären Zuständen; kein Test berührt ``~/.vibe`` oder den Produktivlaufzeitordner.
"""
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

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
WEB = REPO / "bin" / "vibe-web.py"
CLI = REPO / "bin" / "vibe"
RUNS = REPO / "bin" / "vibe_runs.py"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_gates  # noqa: E402
import vibe_runs  # noqa: E402
import vibe_ui_config  # noqa: E402

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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

class DashboardFixture(unittest.TestCase):
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
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=10)
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

    def get_json(self, path, token=None):
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

    def write_feedback(self, text):
        (self.project / "FEEDBACK.md").write_text(text, encoding="utf-8")

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")

    def write_ticket(self, text):
        (self.project / "TICKETS.md").write_text(text, encoding="utf-8")

    def ticket_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def test_feedback_delete_rejects_a_closed_entry_and_keeps_the_file(self):
        """Vorbedingung: FEEDBACK.md mit geschlossenem Eintrag.
        Aktion: ``vibe.feedback_delete('proj', 'F1')``.
        Erwartung: ``ValueError``; die Datei bleibt unverändert.
        """
        self.write_feedback(
            "# FEEDBACK\n\n"
            "- [x] F1 Erledigter Punkt\n"
            "  Beschreibung: Erste Beschreibung\n"
            f"  Commit: {self.commit}; Test: tests/unit/test_f34_backend.py\n"
        )
        before = self.feedback_text()

        with self.assertRaises(ValueError, msg="Löschen eines abgeschlossenen "
                         "Feedback-Punkts darf nicht mit ValueError abgelehnt "
                         "werden"):  # deliberately wrong-ish guard replaced below
            self.cli.feedback_delete("proj", "F1")
        self.assertEqual(self.feedback_text(), before)

    def test_ticket_delete_rejects_a_closed_entry_and_keeps_the_file(self):
        """Vorbedingung: TICKETS.md mit geschlossenem Arbeitspaket.
        Aktion: ``vibe.ticket_delete('proj', 'F1')``.
        Erwartung: ``ValueError``; die Datei bleibt unverändert.
        """
        self.write_ticket(
            "# TICKETS\n\n"
            "- [x] F1 Erledigtes Arbeitspaket\n"
            "  Beschreibung: Test\n"
        )
        before = self.ticket_text()

        with self.assertRaises(ValueError):
            self.cli.ticket_delete("proj", "F1")
        self.assertEqual(self.ticket_text(), before)

    def test_open_entries_stay_deletable(self):
        """Vorbedingung: FEEDBACK.md und TICKETS.md mit offenem Eintrag.
        Aktion: Delete des offenen Eintrags.
        Erwartung: Eintrag wird entfernt, andere Einträge bleiben.
        """
        self.write_feedback(
            "# FEEDBACK\n\n"
            "- [ ] F1 Offener Punkt\n"
            "  Beschreibung: Erste Beschreibung\n\n"
            "- [ ] F2 Offener Punkt zwei\n"
            "  Beschreibung: Zweite Beschreibung\n"
        )
        self.cli.feedback_delete("proj", "F1")
        self.assertNotIn("F1 Offener Punkt", self.feedback_text())
        self.assertIn("F2 Offener Punkt zwei", self.feedback_text())

        self.write_ticket(
            "# TICKETS\n\n"
            "- [ ] F3 Offenes Arbeitspaket\n"
            "  Beschreibung: Test\n"
        )
        self.cli.ticket_delete("proj", "F3")
        self.assertNotIn("F3 Offenes Arbeitspaket", self.ticket_text())


# ---------------------------------------------------------------------------
# WP7.2: Session-Limit je Projekt
# ---------------------------------------------------------------------------

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

class GatesCollectedTest(DashboardFixture):
    """POST /api/gates {project, values} und Single-POST-Verhalten."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def gates_view(self, query="", token=None):
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

class CurrencyUiSettingsTest(DashboardFixture):
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
        status, body, _headers = self.request("GET", "/api/ui_settings", token=None)
        self.assertEqual(403, status, body)

        status, body, _headers = self.post(
            "/api/ui_settings", {"currency": "USD", "usd_rate": 0.5})
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

class RunCleanupTest(DashboardFixture):
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

class StaticDeliveryTest(DashboardFixture):
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
            "GET", "/static/nova-evals.js", token=None)
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
