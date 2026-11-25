"""B1: Die Kostentabelle muss nach jedem Arbeitspaket aktuell sein.

Das Ticket nennt zwei Ausprägungen desselben Fehlers:

* Die Tabelle aktualisiert sich nur träge, weil das Dashboard die Kosten nicht
  von selbst neu liest.
* Bei manchen Projekten erscheinen gar keine Werte, weil deren
  opencode-Sitzungen unter einem gleichwertigen Alternativpfad liegen
  (beobachtet: Container-Alias ``/run/host/var/mnt/...`` gegenüber
  ``/var/mnt/...``). OpenCode führt dazu die Tabelle ``project`` mit dem
  kanonischen Pfad in ``worktree``; ``session.project_id`` verweist darauf.

Geprüft werden hier die Datenebene (Zuordnung über den kanonischen
Projektpfad und frisches Lesen nach neuen Sitzungsdaten). Die automatische
Aktualisierung der Oberfläche prüft ``tests/browser/test_costs_refresh_ui.py``.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sqlite3
import unittest
from pathlib import Path

from tests.unit.test_costs import CostFixture, DDL_V2, add_message, make_db

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

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
    """Sitzungen unter einem gleichwertigen Alternativpfad."""

    def create_db(self):
        con = make_db(self.db)
        con.executescript(PROJECT_DDL)
        con.execute(
            "insert into project (id, worktree, time_created, time_updated)"
            " values (?, ?, ?, ?)",
            ("proj-id", str(self.proj), 1, 1),
        )
        con.commit()
        return con

    def test_session_under_equivalent_mount_alias_belongs_to_the_project(self):
        con = self.create_db()
        alias = "/run/host" + str(self.proj)
        insert_session(con, "ses_alias", alias, "proj F1")
        add_message(con, "ses_alias", "coding-agent", "model-a", 1000, 100, 0, 500)
        con.commit()
        con.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 1500, "cached": 500, "output": 100}
        )
        self.assertEqual([p["id"] for p in data["packages"]], ["F1"])

    def test_alias_does_not_attribute_unrelated_sessions(self):
        con = self.create_db()
        insert_session(con, "ses_foreign", "/run/host/irgendwo/aussen", "proj F1",
                       project_id="foreign-id")
        add_message(con, "ses_foreign", "coding-agent", "model-a", 999, 10, 0, 0)
        con.commit()
        con.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 0)
        self.assertEqual(data["total"]["tokens"], {"input": 0, "cached": 0, "output": 0})

    def test_new_session_data_is_visible_on_the_next_read(self):
        con = self.create_db()
        insert_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 100, 10, 0, 0)
        con.commit()

        first = self.cli.costs_project("proj")
        self.assertEqual(first["total"]["tokens"], {"input": 100, "cached": 0, "output": 10})

        insert_session(con, "ses_b", self.proj, "proj F2")
        add_message(con, "ses_b", "coding-agent", "model-a", 200, 20, 0, 0)
        con.commit()
        con.close()

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
    """opencode-Sitzungen aus dem Sandbox-Zustand eines Projekts.

    Ein Lauf in der Sandbox setzt ``XDG_DATA_HOME`` auf ein eigenes
    Zustandsverzeichnis. Dessen opencode-Datenbank liegt deshalb nicht am
    primären Ort; ihre Sitzungen fehlten bisher in der Kostentabelle.
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

    def make_sandbox_db(self, project=None):
        path = sandbox_db_for(self.sandbox_root, project or self.proj)
        path.parent.mkdir(parents=True, exist_ok=True)
        return make_db(path)

    def empty_primary_db(self):
        make_db(self.db).close()

    def test_sessions_in_the_project_sandbox_database_are_counted(self):
        self.empty_primary_db()
        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_sandbox", self.proj, "proj F1")
        add_message(sandbox, "ses_sandbox", "coding-agent", "model-a", 400, 40, 0, 0)
        sandbox.commit()
        sandbox.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["available"], True)
        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 400, "cached": 0, "output": 40}
        )
        self.assertEqual([p["id"] for p in data["packages"]], ["F1"])

    def test_sandbox_alias_session_uses_the_project_table_of_that_database(self):
        self.empty_primary_db()
        alias = "/run/host" + str(self.proj)
        sandbox = self.make_sandbox_db()
        sandbox.executescript(PROJECT_DDL)
        sandbox.execute(
            "insert into project (id, worktree, time_created, time_updated)"
            " values (?, ?, ?, ?)",
            ("sandbox-proj-id", str(self.proj), 1, 1),
        )
        insert_session(sandbox, "ses_alias", alias, "proj F1",
                       project_id="sandbox-proj-id")
        add_message(sandbox, "ses_alias", "coding-agent", "model-a", 700, 70, 0, 0)
        sandbox.commit()
        sandbox.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 700, "cached": 0, "output": 70}
        )

    def test_sessions_of_other_projects_in_the_sandbox_are_not_counted(self):
        self.empty_primary_db()
        foreign = self.root / "foreign"
        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_own", self.proj, "proj F1")
        add_message(sandbox, "ses_own", "coding-agent", "model-a", 100, 10, 0, 0)
        insert_session(sandbox, "ses_foreign", foreign, "fremd F9")
        add_message(sandbox, "ses_foreign", "coding-agent", "model-a", 999, 99, 0, 0)
        sandbox.commit()
        sandbox.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 100, "cached": 0, "output": 10}
        )

    def test_duplicate_session_id_in_both_databases_is_counted_once(self):
        con = make_db(self.db)
        insert_session(con, "ses_dup", self.proj, "proj F1")
        add_message(con, "ses_dup", "coding-agent", "model-a", 100, 10, 0, 0)
        con.commit()
        con.close()

        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_dup", self.proj, "proj F1")
        add_message(sandbox, "ses_dup", "coding-agent", "model-a", 999, 99, 0, 0)
        sandbox.commit()
        sandbox.close()

        data = self.cli.costs_project("proj")

        self.assertEqual(data["sessions"], 1)
        self.assertEqual(
            data["total"]["tokens"], {"input": 100, "cached": 0, "output": 10}
        )

    def test_new_sandbox_session_is_visible_on_the_next_read(self):
        self.empty_primary_db()

        first = self.cli.costs_project("proj")
        self.assertEqual(first["sessions"], 0)

        sandbox = self.make_sandbox_db()
        insert_session(sandbox, "ses_later", self.proj, "proj F2")
        add_message(sandbox, "ses_later", "coding-agent", "model-a", 200, 20, 0, 0)
        sandbox.commit()
        sandbox.close()

        second = self.cli.costs_project("proj")
        self.assertEqual(second["sessions"], 1)
        self.assertEqual(
            second["total"]["tokens"], {"input": 200, "cached": 0, "output": 20}
        )
        self.assertEqual([p["id"] for p in second["packages"]], ["F2"])



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
