"""Package costs: persisted per work package, aggregated over its sessions.

Costs are stored on the package record, summed over every session that ran for
that package, and survive session cleanup. The overview reads those persisted
numbers instead of live harness sessions. Repeated processing must not count a
session twice.

Aufruf: python3 -m unittest tests.unit.test_package_costs -v
"""

import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support  # noqa: E402
from tests.unit.test_costs import DDL_V2, add_message  # noqa: E402


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


TICKETS = load_module(BIN / "vibe_tickets.py", "vibe_tickets_gh99_pkg_costs")

PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)


def usage_entry(agent, input_tokens, cached=0, output=0,
                model="opencode/model-a"):
    return {model: {"agent": agent, "input": input_tokens,
                    "cached_input": cached, "output": output}}


def usage(input_tokens, cached=0, output=0, agent="coding-agent"):
    return {"models": usage_entry(agent, input_tokens, cached, output)}


class CostFixture(unittest.TestCase):
    """Isolated VIBE with one project and a ticket store."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        for path in (self.home, self.install, self.runtime, self.state,
                     self.root / "tmp"):
            path.mkdir(parents=True, exist_ok=True)
        self.project = self.root / "proj"
        support.write_project(
            self.project, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Erster Auftrag"),
                     support.ticket_record("AP2", "Zweiter Auftrag")],
        )
        self.db = self.root / "opencode.db"
        self.cli = self.load_cli()
        self.cli._pm.clear()
        old_db = os.environ.get("VIBE_OPENCODE_DB")
        os.environ["VIBE_OPENCODE_DB"] = str(self.db)
        if old_db is None:
            self.addCleanup(os.environ.pop, "VIBE_OPENCODE_DB", None)
        else:
            self.addCleanup(os.environ.__setitem__, "VIBE_OPENCODE_DB", old_db)

    def load_cli(self):
        names = ("VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_INSTALL",
                 "VIBE_RUNTIME", "VIBE_STATE", "VIBE_OPENCODE_DB", "TMPDIR")
        old = {key: os.environ.get(key) for key in names}
        os.environ.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_OPENCODE_DB": str(self.db),
            "TMPDIR": str(self.root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        try:
            return load_module(CLI, "vibe_gh99_package_costs_under_test")
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    # ---------- fixture helpers ----------

    def store_path(self):
        return self.project / ".vibe" / "tickets.json"

    def document(self):
        return json.loads(self.store_path().read_text(encoding="utf-8"))

    def write_document(self, doc):
        self.store_path().write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def ticket(self, tid):
        return TICKETS.find(TICKETS.load(self.project), tid)

    def write_field(self, tid, field, value):
        """Seeds a raw package field without calling the helper under test."""
        doc = self.document()
        for record in doc["tickets"]:
            if record.get("id") == tid:
                record[field] = value
                break
        else:
            self.fail("Ticket fehlt beim Seeden: " + tid)
        self.write_document(doc)

    def package(self, data, tid="AP1"):
        return {item["id"]: item for item in data["packages"]}[tid]

    def set_prices(self):
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 1.0, "cached_input": 0.5, "output": 2.0}})


class UsageContractTest(CostFixture):
    """``record_usage``/``usage_of`` persist validated per-session usage."""

    def test_missing_costs_read_as_an_empty_structure(self):
        data = TICKETS.usage_of(self.ticket("AP1"))
        self.assertEqual({}, data.get("sessions", {}), data)

    def test_record_usage_persists_one_session(self):
        data = usage(1000, 100, 50)

        TICKETS.record_usage(self.project, "AP1", "ses_eins", data)

        stored = TICKETS.usage_of(self.ticket("AP1"))
        self.assertEqual(data, stored.get("sessions", {}).get("ses_eins"),
                         "Verbrauch wurde nicht am Paket gespeichert")

    def test_record_usage_overwrites_instead_of_incrementing(self):
        """A re-flush replaces a session's usage, it never adds it again."""
        TICKETS.record_usage(self.project, "AP1", "ses_eins", usage(1000))
        TICKETS.record_usage(self.project, "AP1", "ses_eins", usage(4000, 400))

        stored = TICKETS.usage_of(self.ticket("AP1"))
        self.assertEqual(usage(4000, 400), stored["sessions"]["ses_eins"],
                         "Wiederholter Flush hat den Verbrauch addiert")

    def test_record_usage_rejects_an_unknown_package(self):
        with self.assertRaises(ValueError):
            TICKETS.record_usage(self.project, "GIBT_ES_NICHT", "ses_eins",
                                 usage(1000))

    def test_record_usage_rejects_an_invalid_session_id(self):
        for sid in ("", "ses;rm", "ses x", None):
            with self.subTest(session=sid):
                with self.assertRaises(ValueError):
                    TICKETS.record_usage(self.project, "AP1", sid, usage(1000))

    def test_record_usage_rejects_a_package_of_another_project(self):
        with self.assertRaises(ValueError):
            TICKETS.record_usage(self.project, "BX1", "ses_eins", usage(1000))


class AggregationTest(CostFixture):
    """The overview sums persisted usage across all sessions of a package."""

    def seed_two_sessions(self):
        TICKETS.attach_session(self.project, "AP1", "ses_eins")
        TICKETS.attach_session(self.project, "AP1", "ses_zwei")
        TICKETS.record_usage(self.project, "AP1", "ses_eins",
                             usage(1000, 100, 50))
        TICKETS.record_usage(self.project, "AP1", "ses_zwei",
                             usage(2000, 200, 150, agent="code-reviewer"))

    def test_tokens_of_two_sessions_are_summed(self):
        self.seed_two_sessions()

        package = self.package(self.cli.costs_project("proj"))

        self.assertEqual({"input": 3000, "cached": 300, "output": 200},
                         package["tokens"], package)

    def test_models_of_different_sessions_keep_their_agent(self):
        self.seed_two_sessions()

        package = self.package(self.cli.costs_project("proj"))
        models = {item["model"]: item for item in package["models"]}
        agents = {item["agent"] for item in package["models"]}

        self.assertIn("opencode/model-a", models)
        self.assertEqual({"coding-agent", "code-reviewer"}, agents,
                         "Agenten der einzelnen Sitzungen gingen verloren")

    def test_repeated_flush_does_not_double_count(self):
        self.seed_two_sessions()
        first = self.package(self.cli.costs_project("proj"))["tokens"]

        # The runner processes the package again and re-records the same data.
        TICKETS.record_usage(self.project, "AP1", "ses_eins",
                             usage(1000, 100, 50))
        TICKETS.record_usage(self.project, "AP1", "ses_zwei",
                             usage(2000, 200, 150, agent="code-reviewer"))
        second = self.package(self.cli.costs_project("proj"))["tokens"]

        self.assertEqual(first, second,
                         "Wiederholte Verarbeitung hat Kosten doppelt erfasst")

    def test_costs_survive_session_cleanup(self):
        """After successful completion the sessions are gone, costs are not."""
        self.seed_two_sessions()
        TICKETS.clear_sessions(self.project, "AP1")

        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))
        package = self.package(self.cli.costs_project("proj"))
        self.assertEqual({"input": 3000, "cached": 300, "output": 200},
                         package["tokens"],
                         "Bereinigung hat die Kostendaten verloren")

    def test_costs_are_computed_from_persisted_data_without_a_live_session(self):
        """A harness session in the database is not enough: only persisted
        package costs may feed the overview."""
        con = sqlite3.connect(str(self.db))
        con.executescript(DDL_V2)
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title,"
            " version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses_live", "proj", "s", str(self.project), "proj AP1",
             "2.1.4", "coding-agent",
             json.dumps({"id": "model-a", "providerID": "opencode"}), 1, 1),
        )
        add_message(con, "ses_live", "coding-agent", "model-a",
                    999999, 99999, 0, 88888)
        con.commit()
        con.close()
        TICKETS.record_usage(self.project, "AP1", "ses_persisted",
                             usage(1000, 100, 50))

        package = self.package(self.cli.costs_project("proj"))

        self.assertEqual({"input": 1000, "cached": 100, "output": 50},
                         package["tokens"],
                         "Die Übersicht liest aus der laufenden Harness-Session "
                         "statt aus den gespeicherten Paketkosten")

    def test_costs_are_still_available_without_the_database(self):
        self.seed_two_sessions()
        TICKETS.clear_sessions(self.project, "AP1")
        self.db.unlink(missing_ok=True)

        package = self.package(self.cli.costs_project("proj"))

        self.assertEqual({"input": 3000, "cached": 300, "output": 200},
                         package["tokens"],
                         "Ohne Datenbank verschwanden die gespeicherten Kosten")

    def test_package_costs_are_kept_separate(self):
        TICKETS.record_usage(self.project, "AP1", "ses_eins", usage(1000))
        TICKETS.record_usage(self.project, "AP2", "ses_zwei", usage(5000))

        data = self.cli.costs_project("proj")

        self.assertEqual({"input": 1000, "cached": 0, "output": 0},
                         self.package(data, "AP1")["tokens"])
        self.assertEqual({"input": 5000, "cached": 0, "output": 0},
                         self.package(data, "AP2")["tokens"])

    def test_persisted_tokens_are_priced_like_regular_usage(self):
        self.seed_two_sessions()
        self.set_prices()

        package = self.package(self.cli.costs_project("proj"))

        # Dokumentierte F12-Regel: (input-cached)*price_input
        # + cached*price_cached + output*price_output
        # = (3000-300)/1e6*1 + 300/1e6*0.5 + 200/1e6*2 = 0.00325
        self.assertAlmostEqual(0.0027 + 0.00015 + 0.0004,
                               package["cost"], places=9, msg=package)


if __name__ == "__main__":
    unittest.main()
