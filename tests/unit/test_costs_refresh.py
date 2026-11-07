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
import json
import os
import re
import sqlite3
import unittest
from pathlib import Path

from tests.unit.test_costs import CostFixture, DDL_V2, add_message, make_db

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

    Entspricht ``vibe_sandbox.state_dir``: Basisverzeichnis, Projektname und
    die ersten zehn Zeichen des SHA-256 des realen Projektpfads.
    """
    real = os.path.realpath(str(project))
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", os.path.basename(real))
    return Path(base) / (name + "-" + digest) / "data" / "opencode" / "opencode.db"


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


if __name__ == "__main__":
    unittest.main()
