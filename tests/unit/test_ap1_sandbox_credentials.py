"""Abnahme AP1: opencode-go-Zugangsdaten in der Sandbox (Nutzerentscheidung A).

Die Zugangsdaten liegen in ``opencode.db`` (Tabelle ``credential``), nicht in
``auth.json``. ``vibe_sandbox.bwrap_argv`` muss vor dem bwrap-Aufbau eine
sandbox-lokale Datenbank mit Schema und nur den Zugangsdaten anlegen bzw. eine
bestehende Datenbank um die Zugangsdaten ergänzen — ohne Sitzungen, Nachrichten,
Blobs oder den kv-Modellkatalog zu übernehmen.

Die Sandbox wird nicht gestartet; ``VIBE_BWRAP`` zeigt auf eine ausführbare
Attrappe. HOME und XDG_DATA_HOME sind isoliert, damit weder echte Zugangsdaten
noch echte Sitzungen gelesen oder verändert werden.

Run:

    python3 -m unittest tests.unit.test_ap1_sandbox_credentials -v
"""
import contextlib
import importlib.machinery
import importlib.util
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

MODULE_KEYS = (
    "VIBE", "VIBE_RUNTIME", "VIBE_STATE", "VIBE_SANDBOX_ROOT",
    "VIBE_BWRAP", "XDG_DATA_HOME",
)

# (Typ, Name, SQL) — dieselbe Form, wie sie sqlite_master liefert.
SCHEMA = [
    ("table", "credential",
     "CREATE TABLE `credential` ("
     "`id` text PRIMARY KEY, `integration_id` text, `data` text)"),
    ("table", "account",
     "CREATE TABLE `account` (`id` text PRIMARY KEY, `email` text NOT NULL)"),
    ("table", "account_state",
     "CREATE TABLE `account_state` ("
     "`id` integer PRIMARY KEY, `active_account_id` text)"),
    ("table", "control_account",
     "CREATE TABLE `control_account` ("
     "`email` text PRIMARY KEY, `url` text NOT NULL)"),
    ("table", "migration",
     "CREATE TABLE `migration` "
     "(`id` TEXT PRIMARY KEY, `time_completed` INTEGER NOT NULL)"),
    ("table", "session_v2",
     "CREATE TABLE `session_v2` (`id` text PRIMARY KEY, `project_id` text)"),
    ("table", "session_message",
     "CREATE TABLE `session_message` (`id` text PRIMARY KEY, `session_id` text)"),
    ("table", "kv",
     "CREATE TABLE `kv` (`key` text PRIMARY KEY, `value` text NOT NULL)"),
    ("index", "credential_integration_idx",
     "CREATE INDEX `credential_integration_idx` ON `credential` (`integration_id`)"),
]
CREDENTIAL_OBJECTS = {"credential", "credential_integration_idx"}


def load_sandbox():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_sandbox_ap1_credentials", str(SANDBOX)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SandboxCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nSANDBOX=on\nSANDBOX_TOOLS=\"git\"\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg"
        self.xdg.mkdir()

        self.old = {key: os.environ.get(key) for key in MODULE_KEYS}
        self.addCleanup(self._restore_env)
        for key in MODULE_KEYS:
            os.environ.pop(key, None)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["XDG_DATA_HOME"] = str(self.xdg)
        os.environ["VIBE_SANDBOX_ROOT"] = str(self.root / "sandbox")
        fake_bwrap = self.root / "fake-bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_bwrap.chmod(0o755)
        os.environ["VIBE_BWRAP"] = str(fake_bwrap)

        self.sandbox = load_sandbox()

    def _restore_env(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def source_db(self):
        return self.xdg / "opencode" / "opencode.db"

    def target_db(self):
        return (
            Path(self.sandbox.state_dir(self.project))
            / "data" / "opencode" / "opencode.db"
        )

    def write_db(self, path, credential_value="test-token", sessions=False,
                 include_credential=True, session_id="source-session"):
        """Legt eine DB mit dem Test-Schema und ausgewählten Zeilen an."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(path)) as connection:
            for kind, name, sql in SCHEMA:
                if not include_credential and name in CREDENTIAL_OBJECTS:
                    continue
                connection.execute(sql)
            names = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            if credential_value is not None and "credential" in names:
                connection.execute(
                    'INSERT INTO "credential" VALUES (?, ?, ?)',
                    ("opencode-go", "opencode-go", credential_value),
                )
                connection.execute(
                    'INSERT INTO "account" VALUES (?, ?)',
                    ("acct-1", "test@example.invalid"),
                )
                connection.execute(
                    'INSERT INTO "account_state" VALUES (?, ?)',
                    (1, "acct-1"),
                )
                connection.execute(
                    'INSERT INTO "control_account" VALUES (?, ?)',
                    ("test@example.invalid", "https://example.invalid"),
                )
                connection.execute(
                    'INSERT INTO "migration" VALUES (?, ?)',
                    ("2026-01-01", 1),
                )
            if sessions:
                connection.execute(
                    'INSERT INTO "session_v2" VALUES (?, ?)',
                    (session_id, "source-project"),
                )
                connection.execute(
                    'INSERT INTO "session_message" VALUES (?, ?)',
                    ("source-message", session_id),
                )
                connection.execute(
                    'INSERT INTO "kv" VALUES (?, ?)',
                    ("model-catalog", "source-only"),
                )
            connection.commit()
        return path

    def values(self, path, query):
        with contextlib.closing(sqlite3.connect(path)) as connection:
            return connection.execute(query).fetchall()

    def object_names(self, path, kind):
        with contextlib.closing(sqlite3.connect(path)) as connection:
            return {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type=?", (kind,))
            }

    def bind_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]

    def test_ak1_schema_and_credentials_are_copied_without_session_data(self):
        """AK1: Schema und Zugangsdaten kopieren, keine Sitzungsdaten."""
        self.write_db(self.source_db(), sessions=True)

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        target = self.target_db()
        self.assertTrue(target.is_file(), "Sandbox-DB wurde nicht angelegt")
        self.assertEqual(
            0o600, stat.S_IMODE(target.stat().st_mode),
            "Die neue Datenbank ist nicht nur für den Besucher lesbar")
        tables = self.object_names(target, "table")
        indexes = self.object_names(target, "index")
        for kind, name, _sql in SCHEMA:
            self.assertIn(name, tables if kind == "table" else indexes)
        self.assertIn("sqlite_autoindex_credential_1", indexes)
        self.assertEqual(
            [("opencode-go", "test-token")],
            self.values(
                target,
                'SELECT integration_id, data FROM "credential" ORDER BY id'),
        )
        for table in ("account", "account_state", "control_account", "migration"):
            self.assertEqual(
                1, len(self.values(target, f'SELECT * FROM "{table}"')),
                f"Zugangsdatentabelle {table} wurde nicht kopiert")
        for table in ("session_v2", "session_message", "kv"):
            self.assertEqual(
                [], self.values(target, f'SELECT * FROM "{table}"'),
                f"Sitzungsdaten aus {table} wurden übernommen")

    def test_ak2_existing_credentials_are_not_overwritten(self):
        """AK2: Vorhandene sandbox-lokale Zugangsdaten bleiben unverändert."""
        self.write_db(self.source_db())
        target = self.write_db(
            self.target_db(), credential_value="sandbox-token", sessions=True,
            session_id="sandbox-session",
        )
        before = target.read_bytes()

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertEqual(before, target.read_bytes())
        self.assertEqual(
            [("sandbox-token",)],
            self.values(target, 'SELECT data FROM "credential"'),
        )

    def test_ak3_empty_credentials_are_filled_without_touching_sessions(self):
        """AK3: Upgrade füllt credential auf, lässt Sitzungen unangetastet."""
        self.write_db(self.source_db(), sessions=True)
        target = self.write_db(
            self.target_db(), credential_value=None, sessions=True,
            session_id="sandbox-session",
        )

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertEqual(
            [("opencode-go", "test-token")],
            self.values(
                target,
                'SELECT integration_id, data FROM "credential" ORDER BY id'),
        )
        self.assertEqual(
            [("sandbox-session", "source-project")],
            self.values(target, 'SELECT * FROM "session_v2"'),
        )
        self.assertEqual(
            [("source-message", "sandbox-session")],
            self.values(target, 'SELECT * FROM "session_message"'),
        )
        self.assertEqual(
            [("model-catalog", "source-only")],
            self.values(target, 'SELECT * FROM "kv"'),
        )

    def test_ak4_missing_source_db_creates_no_target_and_does_not_abort(self):
        """AK4: Fehlende Host-DB ist kein Abbruch und erzeugt keine Zieldatei."""
        self.assertFalse(self.source_db().exists())

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertFalse(self.target_db().exists())

    def test_ak5_source_without_credential_table_does_not_abort(self):
        """AK5: Alte Host-DB ohne credential-Tabelle ist kein Abbruch."""
        self.write_db(
            self.source_db(), include_credential=False, sessions=True)

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        target = self.target_db()
        if target.exists():
            self.assertNotIn("credential", self.object_names(target, "table"))

    def test_ak6_legacy_auth_json_binding_is_unchanged(self):
        """AK6: auth.json wird weiterhin nur lesend eingebunden."""
        auth = self.home / ".local" / "share" / "opencode" / "auth.json"
        auth.parent.mkdir(parents=True, exist_ok=True)
        auth.write_text("{}\n", encoding="utf-8")
        self.write_db(self.source_db())

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        data_home = Path(self.sandbox.state_dir(self.project)) / "data"
        self.assertIn(
            ("--ro-bind", str(auth),
             str(data_home / "opencode" / "auth.json")),
            self.bind_pairs(argv),
        )


if __name__ == "__main__":
    unittest.main()
