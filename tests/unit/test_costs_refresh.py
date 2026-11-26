"""Kosten aktuell und richtig zugeordnet — nach dem Flush-Contract von GH-99.

Die Kostenübersicht wird ausschließlich aus den persistierten Kosten der
Arbeitspakete gespeist. Der opencode-Datenbankleser wird nur noch beim Spülen
(``vibe sessions finish-package``) benutzt; die Zuordnung erfolgt über die am
Paket gespeicherte Session-Zuordnung, nicht über Pfade oder Anzeigenamen.

Geprüft werden hier:

* frische, persistierte Kosten je Paket und Ausschluss fremder Kosten;
* der Datenbankleser im Flush-Pfad, einschließlich Alternativpfaden
  (``/run/host/...``) und der Sandbox-Datenbank eines Projekts;
* die Pfadregel der Sandbox-Datenbank als Grundlage der Flush-Fixtur.

Die automatische Aktualisierung der Oberfläche prüft
``tests/browser/test_costs_refresh_ui.py``.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

from tests.unit.test_costs import (
    CostFixture, DDL_V2, add_message, add_session, make_db, record_usage,
    write_tickets,
)

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
SANDBOX = BIN / "vibe_sandbox.py"

PROJECT_DDL = """
CREATE TABLE `project` (
  `id` text PRIMARY KEY,
  `worktree` text NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `sandboxes` text NOT NULL DEFAULT '[]'
);
"""


def insert_session(con, session_id, directory, title, project_id="proj-id",
                   parent=None, agent="coding-agent", model=None, time_created=1):
    """Sitzungszeile mit frei wählbarer opencode-Projekt-ID."""
    con.execute(
        "insert into session_v2 (id, project_id, parent_id, slug, directory,"
        " title, version, agent, model, time_created, time_updated)"
        " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            project_id,
            parent,
            "slug-" + session_id,
            str(directory),
            title,
            "2.1.4",
            agent,
            json.dumps(model) if isinstance(model, dict) else model,
            time_created,
            time_created,
        ),
    )


class AliasDirectoryTest(CostFixture):
    """Persistierte Kosten werden unabhängig vom Sitzungspfad zugeordnet.

    Früher musste die Übersicht den Alias ``/run/host/...`` eines Projektpfads
    auflösen. Heute ist die gespeicherte Paketzuordnung maßgeblich; die
    Assertion „Sitzung gehört zum richtigen Paket“ bleibt erhalten, wird aber
    über ``record_usage`` am Paket statt über den DB-Pfad gespeist.
    """

    def test_session_under_equivalent_mount_alias_belongs_to_the_project(self):
        alias = "/run/host" + str(self.proj)
        self.record_usage("F1", "ses_alias", input_tokens=1000,
                          output_tokens=100, cached_input=500)
        # Der Alias ist nur noch Kontext des Harness-Laufs, keine Kostenquelle.
        self.assertTrue(alias.startswith("/run/host"))

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 1000, "cached": 500, "output": 100}
        )
        self.assertEqual([p["id"] for p in data["packages"]], ["F1"])

    def test_unrelated_session_costs_are_not_attributed(self):
        # Früher: fremde Sitzung unter einem Alias. Heute: fremde Kosten
        # gehören zu einem anderen Paket und dürfen nicht hier auftauchen.
        record_usage(self.proj, "F2", "ses_foreign", input_tokens=999,
                     output_tokens=10)
        data = self.cli.costs_project("proj")
        ids = [p["id"] for p in data["packages"]]

        # Nur Pakete mit eigenen Kostendaten erscheinen. F1 hat keinen
        # Verbrauch und darf die fremden Kosten nicht erben.
        self.assertNotIn("F1", ids, "Fremde Kosten wurden F1 zugeordnet")
        self.assertEqual(
            data["total"]["tokens"], {"input": 999, "cached": 0, "output": 10}
        )
        other = {p["id"]: p for p in data["packages"]}["F2"]
        self.assertEqual(other["tokens"], {"input": 999, "cached": 0, "output": 10})

    def test_new_session_data_is_visible_on_the_next_read(self):
        self.record_usage("F1", "ses_a", input_tokens=100, output_tokens=10)
        first = self.cli.costs_project("proj")
        self.assertEqual(first["total"]["tokens"], {"input": 100, "cached": 0, "output": 10})

        self.record_usage("F2", "ses_b", input_tokens=200, output_tokens=20)
        second = self.cli.costs_project("proj")
        self.assertEqual(
            second["total"]["tokens"], {"input": 300, "cached": 0, "output": 30}
        )
        self.assertEqual(
            {p["id"] for p in second["packages"]}, {"F1", "F2"}
        )


def sandbox_db_for(base, project):
    """Pfad der opencode-Datenbank im Sandbox-Zustand eines Projekts.

    Entspricht ``vibe_sandbox.state_dir`` (Bug B5): Der Zustandspfad folgt
    der Funktion ``state_dir`` der geladenen Sandbox-Implementierung. Er
    bleibt unter dem Basisverzeichnis, solange das Zeichenlimit (AF_UNIX-
    Grenze 108; sicheres Limit 84 gemäß ``STATE_PATH_LIMIT`` der
    Implementierung) respektiert wird; zu lange Pfade weichen
    auf die per-UID-Kurzform ``/dev/shm/vsb-<uid>/<sha256[:10]>`` aus. Die
    Regel steht nur einmal, damit die Fixtur nicht von ihr abdriftet.
    """
    module = load_sandbox_module()
    old = os.environ.get("VIBE_SANDBOX_ROOT")
    try:
        os.environ["VIBE_SANDBOX_ROOT"] = str(base)
        state = module.state_dir(project)
    finally:
        if old is None:
            os.environ.pop("VIBE_SANDBOX_ROOT", None)
        else:
            os.environ["VIBE_SANDBOX_ROOT"] = old
    return Path(state) / "data" / "opencode" / "opencode.db"


class SandboxDatabaseTest(CostFixture):
    """Persistierte Kosten eines Projekts, unabhängig vom Sandbox-Zustand.

    Ein Sandbox-Lauf setzte früher ``XDG_DATA_HOME`` auf ein eigenes
    Zustandsverzeichnis, dessen Datenbank separat gelesen werden musste.
    Heute zählt der gespeicherte Verbrauch am Paket; die Datenbank wird nur
    noch beim Flush gelesen (siehe ``CostFlushReaderTest``).
    """

    def test_costs_of_a_sandbox_session_are_counted(self):
        self.record_usage("F1", "ses_sandbox", input_tokens=400,
                          output_tokens=40)

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 400, "cached": 0, "output": 40}
        )
        self.assertEqual([p["id"] for p in data["packages"]], ["F1"])

    def test_alias_session_belongs_to_the_recorded_package(self):
        self.record_usage("F1", "ses_alias", input_tokens=700, output_tokens=70)

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 700, "cached": 0, "output": 70}
        )
        self.assertEqual([p["id"] for p in data["packages"]], ["F1"])

    def test_costs_of_other_projects_are_not_counted(self):
        foreign = self.root / "foreign"
        (foreign / ".vibe").mkdir(parents=True)
        (foreign / ".vibe" / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
        write_tickets(foreign, [{"id": "F9", "title": "Fremd", "type": "feedback"}])
        self.record_usage("F1", "ses_own", input_tokens=100, output_tokens=10)
        record_usage(foreign, "F9", "ses_foreign", input_tokens=999,
                     output_tokens=99)

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 100, "cached": 0, "output": 10}
        )

    def test_repeated_record_of_one_session_is_counted_once(self):
        self.record_usage("F1", "ses_dup", input_tokens=100, output_tokens=10)
        self.record_usage("F1", "ses_dup", input_tokens=999, output_tokens=99)

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 999, "cached": 0, "output": 99},
            "Ein erneuter Flush darf die Session nicht doppelt zählen",
        )

    def test_new_session_costs_are_visible_on_the_next_read(self):
        first = self.cli.costs_project("proj")
        self.assertEqual(first["sessions"], 0)

        self.record_usage("F2", "ses_later", input_tokens=200, output_tokens=20)
        second = self.cli.costs_project("proj")

        self.assertEqual(second["sessions"], 1)
        self.assertEqual(
            second["total"]["tokens"], {"input": 200, "cached": 0, "output": 20}
        )
        self.assertEqual([p["id"] for p in second["packages"]], ["F2"])



class CostFlushReaderTest(CostFixture):
    """Der opencode-Datenbankleser im Flush-Pfad ``vibe sessions finish-package``.

    Die früheren Datenbankprüfungen der Kostenübersicht sind hierher
    verlagert: Nur noch beim Spülen liest Vibe die Datenbank, und zwar
    schreibgeschützt. Die gespülten Werte landen als persistierte Kosten am
    Arbeitspaket und sind anschließend unabhängig von der Datenbank.
    """

    def setUp(self):
        super().setUp()
        self.sandbox_root = self.root / "sandbox"
        self.sandbox_root.mkdir()
        self.old_sandbox_root = os.environ.get("VIBE_SANDBOX_ROOT")
        os.environ["VIBE_SANDBOX_ROOT"] = str(self.sandbox_root)

    def tearDown(self):
        if self.old_sandbox_root is None:
            os.environ.pop("VIBE_SANDBOX_ROOT", None)
        else:
            os.environ["VIBE_SANDBOX_ROOT"] = self.old_sandbox_root
        super().tearDown()

    # ---------- fixture helpers ----------

    def make_sandbox_db(self, project=None):
        path = sandbox_db_for(self.sandbox_root, project or self.proj)
        path.parent.mkdir(parents=True, exist_ok=True)
        return make_db(path)

    def attach(self, session_id, package_id="F1"):
        """Verknüpft die Session wie ``attach_session`` am Paket (roh)."""
        path = self.proj / ".vibe" / "tickets.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for record in doc["tickets"]:
            if record.get("id") == package_id:
                sessions = record.setdefault("sessions", [])
                if session_id not in sessions:
                    sessions.append(session_id)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    def run_finish_package(self, package_id="F1"):
        env = os.environ.copy()
        env.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.root / "home"),
            "VIBE_INSTALL": str(self.root / "_toolchain"),
            "VIBE_RUNTIME": str(self.root / "_logs"),
            "VIBE_STATE": str(self.root / "_state"),
            "VIBE_OPENCODE_DB": str(self.db),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return subprocess.run(
            [sys.executable, str(CLI), "sessions", "finish-package",
             "proj", package_id],
            cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=90,
        )

    def usage_of(self, session_id, package_id="F1"):
        path = self.proj / ".vibe" / "tickets.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        record = next(item for item in doc["tickets"] if item["id"] == package_id)
        costs = record.get("costs") or {}
        return (costs.get("sessions") or {}).get(session_id)

    def tokens_of(self, session_id, package_id="F1"):
        usage = self.usage_of(session_id, package_id) or {}
        models = usage.get("models") or {}
        tokens = {"input": 0, "cached": 0, "output": 0}
        for entry in models.values():
            for field, key in (("input", "input"),
                               ("cached", "cached_input"),
                               ("output", "output")):
                tokens[field] += entry.get(key, 0)
        return tokens

    def assert_db_untouched(self):
        before = (self.db.stat().st_size, self.db.stat().st_mtime_ns)
        self.assertFalse(Path(str(self.db) + "-wal").exists())
        self.assertFalse(Path(str(self.db) + "-shm").exists())
        return before

    def assert_db_still_untouched(self, before):
        self.assertEqual(before, (self.db.stat().st_size,
                                  self.db.stat().st_mtime_ns))
        self.assertFalse(Path(str(self.db) + "-wal").exists())
        self.assertFalse(Path(str(self.db) + "-shm").exists())

    # ---------- tests ----------

    def test_session_under_mount_alias_is_flushed_and_db_stays_read_only(self):
        con = make_db(self.db)
        con.executescript(PROJECT_DDL)
        con.execute(
            "insert into project (id, worktree, time_created, time_updated)"
            " values (?, ?, ?, ?)", ("proj-id", str(self.proj), 1, 1))
        alias = "/run/host" + str(self.proj)
        insert_session(con, "ses_alias", alias, "proj F1")
        add_message(con, "ses_alias", "coding-agent", "model-a", 1000, 100, 0, 500)
        con.commit()
        con.close()
        self.attach("ses_alias")
        before = self.assert_db_untouched()

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assert_db_still_untouched(before)
        self.assertEqual({"input": 1500, "cached": 500, "output": 100},
                         self.tokens_of("ses_alias"))

    def test_sandbox_database_session_is_flushed(self):
        make_db(self.db).close()
        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_sandbox", self.proj, "proj F1")
        add_message(sandbox, "ses_sandbox", "coding-agent", "model-a", 400, 40)
        sandbox.commit()
        sandbox.close()
        self.attach("ses_sandbox")

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 400, "cached": 0, "output": 40},
                         self.tokens_of("ses_sandbox"))

    def test_foreign_sandbox_session_is_not_flushed(self):
        make_db(self.db).close()
        foreign = self.root / "foreign"
        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_own", self.proj, "proj F1")
        add_message(sandbox, "ses_own", "coding-agent", "model-a", 100, 10)
        insert_session(sandbox, "ses_foreign", foreign, "fremd F9")
        add_message(sandbox, "ses_foreign", "coding-agent", "model-a", 999, 99)
        sandbox.commit()
        sandbox.close()
        self.attach("ses_own")

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 100, "cached": 0, "output": 10},
                         self.tokens_of("ses_own"))
        self.assertIsNone(self.usage_of("ses_foreign"))

    def test_duplicate_session_in_both_databases_is_flushed_once(self):
        con = make_db(self.db)
        insert_session(con, "ses_dup", self.proj, "proj F1")
        add_message(con, "ses_dup", "coding-agent", "model-a", 100, 10)
        con.commit()
        con.close()
        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_dup", self.proj, "proj F1")
        add_message(sandbox, "ses_dup", "coding-agent", "model-a", 999, 99)
        sandbox.commit()
        sandbox.close()
        self.attach("ses_dup")

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 100, "cached": 0, "output": 10},
                         self.tokens_of("ses_dup"),
                         "Dieselbe Session wurde aus beiden Datenbanken addiert")

    def test_legacy_schema_session_is_flushed(self):
        con = make_db(self.db, schema="v1")
        add_session(con, "ses_a", self.proj, "proj F1", schema="v1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 10, 500,
                    schema="v1")
        add_message(con, "ses_a", "coding-agent", "model-a", 0, 0, 0, 0,
                    schema="v1", role="user", seq=2)
        con.commit()
        con.close()
        self.attach("ses_a")

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 1500, "cached": 500, "output": 110},
                         self.tokens_of("ses_a"))

    def test_session_stored_totals_are_flushed_without_messages(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        con.execute(
            "update session_v2 set tokens_input=100, tokens_output=20,"
            " tokens_reasoning=5, tokens_cache_read=50, agent='coding-agent',"
            " model=? where id='ses_a'",
            (json.dumps({"id": "model-a", "providerID": "opencode"}),),
        )
        con.commit()
        con.close()
        self.attach("ses_a")

        result = self.run_finish_package()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 150, "cached": 50, "output": 25},
                         self.tokens_of("ses_a"))
        self.assertIn("opencode/model-a",
                      (self.usage_of("ses_a") or {}).get("models") or {})

    def test_new_sandbox_session_is_flushed_on_the_next_finish(self):
        make_db(self.db).close()
        self.assertIsNone(self.usage_of("ses_later"))

        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_later", self.proj, "proj F2")
        add_message(sandbox, "ses_later", "coding-agent", "model-a", 200, 20)
        sandbox.commit()
        sandbox.close()
        self.attach("ses_later", package_id="F2")

        result = self.run_finish_package("F2")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"input": 200, "cached": 0, "output": 20},
                         self.tokens_of("ses_later", package_id="F2"))


_SANDBOX_MODULE = None


def load_sandbox_module():
    """Lädt bin/vibe_sandbox.py wie die benachbarten Sandbox-Tests."""
    global _SANDBOX_MODULE
    if _SANDBOX_MODULE is None:
        loader = importlib.machinery.SourceFileLoader(
            "costs_refresh_vibe_sandbox", str(SANDBOX))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _SANDBOX_MODULE = module
    return _SANDBOX_MODULE


def sandbox_db_path_of(module, base, project):
    """db-Pfad laut geladener Implementierung mit dem gegebenen Basispfad."""
    old = os.environ.get("VIBE_SANDBOX_ROOT")
    try:
        os.environ["VIBE_SANDBOX_ROOT"] = str(base)
        return Path(module.state_dir(project)) / "data" / "opencode" / "opencode.db"
    finally:
        if old is None:
            os.environ.pop("VIBE_SANDBOX_ROOT", None)
        else:
            os.environ["VIBE_SANDBOX_ROOT"] = old


class SandboxDbPathRuleTest(unittest.TestCase):
    """Der erwartete Sandbox-Datenbankpfad folgt der state_dir-Regel (B5).

    Bug B5: Der Zustandspfad bleibt unter 84 Zeichen; zu lange Pfade weichen
    auf die per-UID-Kurzform ``/dev/shm/vsb-<uid>/<sha256[:10]>`` aus (GH-89/F1:
    früher der geteilte Host-Ordner /tmp/opencode). Der Test prüft die
    Pfadberechnung der Fixtur ``sandbox_db_for``; die Sitzungs- und
    Tokenzählung decken die bestehenden SandboxDatabaseTest-Fälle ab (B1).

    Die Basen liegen unter /dev/shm: dort ist auch die Agenten-Sandbox
    beschreibbar (in ihr ist /tmp nur lesend), der Pfad bleibt kurz genug für
    die Formel (Vorbedingung: Zustandspfad < 84 Zeichen) und lang genug für
    den Rückfall (Basis >= 120 Zeichen). Ein äußeres TMPDIR spielt keine
    Rolle; in den geteilten Host-Ordner /tmp/opencode wird nicht mehr
    geschrieben. setUp legt beide Basen an, addCleanup räumt sie ab.
    """

    def setUp(self):
        # /dev/shm ist auf dem Host und in der Agenten-Sandbox beschreibbar
        # (dort ist /tmp nur lesend) und kurz genug für die 84er-Regel.
        self.short_base = "/dev/shm/b5-kurz-" + str(os.getpid())
        self.long_base = "/dev/shm/b5-lang-" + str(os.getpid()) + "-" + "z" * 100
        self.proj = Path(self.short_base) / "proj"
        os.makedirs(self.short_base, exist_ok=True)
        os.makedirs(self.long_base, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.short_base, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.long_base, ignore_errors=True)

    def digest_of(self, project):
        real = os.path.realpath(str(project))
        return hashlib.sha256(real.encode("utf-8")).hexdigest()[:10]

    def test_sandbox_db_path_follows_the_state_dir_rule(self):
        module = load_sandbox_module()
        digest = self.digest_of(self.proj)

        # Vorbedingung: die kurze Basis hängt unter /dev/shm (nicht im
        # geteilten Host-Ordner) und bleibt unter der 84er-Begrenzung; die
        # lange Basis überschreitet sie deutlich.
        self.assertGreaterEqual(len(self.long_base), 120)

        # Variante "kurz": die gewohnte Formel bleibt unverändert.
        short_state = os.path.join(self.short_base, "proj-" + digest)
        self.assertLess(
            len(short_state), 84,
            "Vorbedingung: kurzer Basispfad muss die 84er-Begrenzung"
            " (STATE_PATH_LIMIT) unterschreiten")
        self.assertEqual(
            sandbox_db_for(self.short_base, self.proj),
            Path(short_state) / "data" / "opencode" / "opencode.db",
        )

        # Variante "lang": Rückfall auf die feste Kurzform mit demselben
        # SHA-256-Präfix des Projektwegs.
        old_rule_state = os.path.join(self.long_base, "proj-" + digest)
        self.assertGreater(
            len(old_rule_state), 84,
            "Vorbedingung: langer Basispfad muss die 84er-Begrenzung"
            " (STATE_PATH_LIMIT) überschreiten")
        path = sandbox_db_for(self.long_base, self.proj)
        # sandbox_db_for liefert den db-Pfad (<state>/data/opencode/db)...
        expected_state = Path(f"/dev/shm/vsb-{os.getuid()}") / digest
        expected_db = expected_state / "data" / "opencode" / "opencode.db"
        self.assertEqual(path, expected_db)
        # ... dessen Zustandsordner ist exakt der per-UID-Kurzpfad mit dem
        # SHA-256-Präfix des Projektwegs.
        state = path.parent.parent.parent
        self.assertEqual(state, expected_state)
        self.assertFalse(
            str(state).startswith(self.long_base),
            "Rückfallpfad darf die lange Basis nicht enthalten")

        # Die Fixtur muss mit der geladenen Implementierung übereinstimmen.
        for label, base in (("kurz", self.short_base), ("lang", self.long_base)):
            with self.subTest(basis=label):
                self.assertEqual(
                    sandbox_db_for(base, self.proj),
                    sandbox_db_path_of(module, base, self.proj),
                )


if __name__ == "__main__":
    unittest.main()
