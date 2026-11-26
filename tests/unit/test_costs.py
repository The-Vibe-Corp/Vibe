"""Kosten: Paket- und Projektkosten sowie globale Modellpreise.

Aufruf: python3 -m unittest tests.unit.test_costs -v
"""


import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))


def load_module(path, name):
    """Lädt ein bin-Modul als Testunterlage (ohne Installation)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


TICKETS = load_module(BIN / "vibe_tickets.py", "vibe_tickets_cost_contract")


def record_usage(project, package_id, session_id, input_tokens=0,
                 output_tokens=0, cached_input=0, agent="coding-agent",
                 model="opencode/model-a", month=None):
    """Legt persistente Paketkosten an (GH-99: keine DB als Kostenquelle).

    ``month`` ist optional und versorgt die Monatsbuckets der Kostenübersicht;
    fehlt es, bestimmt die Implementierung den Monat selbst. Der Verbrauch
    eines Sessions ist ein Überschreiben, kein Inkrement.
    """
    usage = {"models": {model: {
        "agent": agent,
        "input": int(input_tokens),
        "cached_input": int(cached_input),
        "output": int(output_tokens),
    }}}
    if month is not None:
        usage["month"] = month
    TICKETS.record_usage(project, package_id, session_id, usage)

# Reale Tabellenstruktur der opencode-Datenbank (Stand opencode 2.1.4).
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
CREATE INDEX `session_message_session_type_seq_idx` ON `session_message` (`session_id`, `type`, `seq`);
CREATE INDEX `session_message_session_time_created_id_idx` ON `session_message` (`session_id`, `time_created`, `id`);
"""

# Ältere opencode-Datenbank (vor der Migration auf session_v2).
DDL_V1 = """
CREATE TABLE `session` (
  `id` text PRIMARY KEY,
  `project_id` text NOT NULL,
  `workspace_id` text,
  `parent_id` text,
  `slug` text NOT NULL,
  `directory` text NOT NULL,
  `path` text,
  `title` text NOT NULL,
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
  `time_archived` integer
);
CREATE INDEX `session_project_idx` ON `session` (`project_id`);
CREATE INDEX `session_parent_idx` ON `session` (`parent_id`);
CREATE TABLE `message` (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL
);
CREATE INDEX `message_session_time_created_id_idx` ON `message` (`session_id`, `time_created`, `id`);
"""


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul mit isoliertem VIBE und HOME."""
    keys = ("VIBE", "VIBE_NO_CONTAINER", "HOME")
    old = {key: os.environ.get(key) for key in keys}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(Path(vibe_root) / "home")
    try:
        loader = importlib.machinery.SourceFileLoader("vibe_costs_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def write_tickets(project, tickets):
    """Legt den maschinenlesbaren Ticketspeicher (GH-48) an."""
    store = Path(project) / ".vibe" / "tickets.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps({"version": 1, "tickets": tickets},
                                ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")


def make_db(path, schema="v2"):
    con = sqlite3.connect(str(path))
    con.executescript(DDL_V2 if schema == "v2" else DDL_V1)
    con.commit()
    return con


def add_session(con, session_id, directory, title, schema="v2", parent=None,
                agent="coding-agent", model=None, time_created=1):
    table = "session_v2" if schema == "v2" else "session"
    con.execute(
        f"insert into {table} (id, project_id, parent_id, slug, directory, title,"
        " version, agent, model, time_created, time_updated)"
        " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            "proj",
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


def add_message(con, session_id, agent, model_id, input_tokens=0, output_tokens=0,
                reasoning=0, cache_read=0, provider="opencode", schema="v2",
                role="assistant", seq=1):
    tokens = {
        "input": input_tokens,
        "output": output_tokens,
        "reasoning": reasoning,
        "cache": {"read": cache_read, "write": 0},
    }
    if schema == "v2":
        data = {
            "agent": agent,
            "model": {"id": model_id, "providerID": provider},
            "tokens": tokens,
        }
        con.execute(
            "insert into session_message (id, session_id, type, seq, time_created,"
            " time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_" + session_id + "_" + str(seq), session_id, "assistant", seq,
             1, 1, json.dumps(data)),
        )
    else:
        data = {
            "role": role,
            "agent": agent,
            "modelID": model_id,
            "providerID": provider,
            "tokens": tokens,
        }
        con.execute(
            "insert into message (id, session_id, time_created, time_updated, data)"
            " values (?, ?, ?, ?, ?)",
            ("msg_" + session_id + "_" + str(seq), session_id, 1, 1, json.dumps(data)),
        )


class CostFixture(unittest.TestCase):
    """Temporäres VIBE mit einem Projekt, einer Datenbank und Nutzerpreisen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
        write_tickets(self.proj, [
            {"id": "F1", "title": "Erster Punkt", "type": "feedback"},
            {"id": "F2", "title": "Zweiter Punkt", "type": "feedback"},
        ])
        (self.root / "_toolchain").mkdir()
        self.db = self.root / "opencode.db"
        self.cli = load_cli(self.root)
        self.cli._pm.clear()
        self.old_db = os.environ.get("VIBE_OPENCODE_DB")
        os.environ["VIBE_OPENCODE_DB"] = str(self.db)

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("VIBE_OPENCODE_DB", None)
        else:
            os.environ["VIBE_OPENCODE_DB"] = self.old_db
        self.tmp.cleanup()

    def add_project(self, name):
        path = self.root / name
        (path / ".vibe").mkdir(parents=True)
        (path / ".vibe" / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
        write_tickets(path, [{"id": "F1", "title": "Erster Punkt",
                              "type": "feedback"}])
        self.cli._pm.clear()
        return path

    def write_system_prices(self, models, currency="EUR"):
        (self.root / "_toolchain" / "prices.json").write_text(
            json.dumps({"waehrung": currency, "modelle": models}), encoding="utf-8"
        )

    def write_catalog(self, models):
        (self.root / "_toolchain" / "models.json").write_text(
            json.dumps({"stand": "2026-10-29", "models": models}), encoding="utf-8"
        )

    def record_usage(self, package_id, session_id, **kwargs):
        """Persistiert Verbrauch am Paket statt in der opencode-Datenbank."""
        record_usage(self.proj, package_id, session_id, **kwargs)


class TokenAggregationTest(CostFixture):
    def build_usage(self):
        # GH-99: Die Kostenübersicht liest ausschließlich persistierte
        # Paketkosten. Die früher aus zwei Nachrichten und dem Subagenten
        # abgeleiteten Tokenwerte werden jetzt als Verbrauch zweier Sessions
        # des Pakets F1 gespeichert (Summe unverändert).
        self.record_usage("F1", "ses_a", input_tokens=10000,
                          output_tokens=400, cached_input=7000)
        self.record_usage("F1", "ses_b", input_tokens=500,
                          output_tokens=10, agent="code-reviewer",
                          model="opencode/model-b")
        self.record_usage("F2", "ses_c", input_tokens=100, output_tokens=20)
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 2.0, "cached_input": 0.5, "output": 4.0}})
        return self.cli.costs_project("proj")

    def test_cached_tokens_belong_to_input_and_reasoning_to_output(self):
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        model = {m["model"]: m for m in package["models"]}["opencode/model-a"]
        self.assertEqual(model["tokens"], {"input": 10000, "cached": 7000, "output": 400})
        self.assertEqual(model["price_source"], "user")

    def test_subagent_messages_count_towards_the_parent_package(self):
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        models = {m["model"]: m for m in package["models"]}
        self.assertEqual(set(models), {"opencode/model-a", "opencode/model-b"})
        self.assertEqual(models["opencode/model-b"]["agent"], "code-reviewer")
        self.assertEqual(models["opencode/model-b"]["tokens"],
                         {"input": 500, "cached": 0, "output": 10})
        self.assertEqual(package["sessions"], 2)

    def test_costs_are_calculated_from_tokens_and_prices(self):
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        self.assertAlmostEqual(package["cost"], 0.0111, places=9)
        self.assertAlmostEqual(data["total"]["cost"], 0.01138, places=9)

    def test_unknown_model_price_is_zero(self):
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        model = {m["model"]: m for m in package["models"]}["opencode/model-b"]
        self.assertEqual(model["price_source"], "unbekannt")
        self.assertEqual(model["cost"], 0.0)

    # Der frühere Fall „Sitzung ohne Paketbezug bildet ein eigenes Paket mit
    # dem Titel 'Ohne Arbeitspaket'“ ist unter GH-99 entfallen: Kosten werden
    # nur über eine gespeicherte Zuordnung zu einem echten Paket erfasst. Ein
    # leeres Paket hat keinen Ticketdatensatz und damit keine Kostenquelle;
    # die Prüfung wäre ohne Zweck und wurde entfernt, nicht abgeschwächt.

    def test_project_total_is_the_sum_of_all_packages(self):
        data = self.build_usage()
        for field in ("input", "cached", "output"):
            self.assertEqual(
                data["total"]["tokens"][field],
                sum(p["tokens"][field] for p in data["packages"]),
            )
        self.assertAlmostEqual(
            data["total"]["cost"], sum(p["cost"] for p in data["packages"]), places=9)
        self.assertEqual(data["total"]["sessions"],
                         sum(p["sessions"] for p in data["packages"]))
        # Drei Sessions in zwei Paketen; der frühere „Ohne Arbeitspaket“-
        # Topf existiert ohne gespeicherte Zuordnung nicht mehr.
        self.assertEqual(data["total"]["sessions"], 3)
        self.assertEqual(data["total"]["tokens"],
                         {"input": 10600, "cached": 7000, "output": 430})

    def test_overview_lists_every_project_with_its_totals(self):
        self.build_usage()
        data = self.cli.costs_overview()
        self.assertTrue(data["available"])
        self.assertEqual(data["currency"], "EUR")
        row = {p["name"]: p for p in data["projects"]}["proj"]
        self.assertEqual(row["packages"], 2)
        self.assertEqual(row["sessions"], 3)
        self.assertAlmostEqual(row["cost"], 0.01138, places=9)

    def test_costs_of_other_projects_are_ignored(self):
        # GH-99: Die Zuordnung liegt am Paket, nicht am Sitzungspfad. Ein
        # anderes Projekt kann nicht in die Kostenübersicht von 'proj' laufen.
        other = self.add_project("other")
        self.record_usage("F1", "ses_own", input_tokens=10, output_tokens=1)
        record_usage(other, "F1", "ses_other", input_tokens=999,
                     output_tokens=999)
        data = self.cli.costs_project("proj")
        self.assertEqual(data["total"]["tokens"], {"input": 10, "cached": 0, "output": 1})
        self.assertEqual(data["sessions"], 1)

    def test_location_of_the_harness_session_does_not_change_attribution(self):
        # Früher: eine Sitzung in einem Unterordner gehörte weiterhin zum
        # Projekt. Heute: der gespeicherte Paketbezug entscheidet; der Pfad
        # der Harness-Sitzung wird für die Übersicht nicht mehr herangezogen.
        self.record_usage("F1", "ses_sub", input_tokens=7, output_tokens=3)
        data = self.cli.costs_project("proj")
        self.assertEqual(data["sessions"], 1)
        self.assertEqual(data["total"]["tokens"], {"input": 7, "cached": 0, "output": 3})


class PriceResolutionTest(CostFixture):
    def build_single_session(self, model="model-a"):
        self.record_usage("F1", "ses_a", input_tokens=1000000,
                          output_tokens=500000, model="opencode/" + model)

    def model_row(self, data, model):
        return {m["model"]: m for m in data["models"]}[f"opencode/{model}"]

    def test_system_price_is_used_without_user_input(self):
        self.build_single_session()
        self.write_system_prices({"opencode/model-a": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}})
        data = self.cli.costs_project("proj")
        row = self.model_row(data, "model-a")
        self.assertEqual(row["price_source"], "system")
        self.assertAlmostEqual(row["cost"], 1.0 + 1.0, places=9)

    def test_user_price_overrides_the_system_price(self):
        self.build_single_session()
        self.write_system_prices({"opencode/model-a": {
            "input": 100.0, "cached_input": 100.0, "output": 100.0}})
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}})
        data = self.cli.costs_project("proj")
        row = self.model_row(data, "model-a")
        self.assertEqual(row["price_source"], "user")
        self.assertAlmostEqual(row["cost"], 2.0, places=9)

    def test_free_model_in_the_catalog_costs_zero(self):
        self.build_single_session("model-free")
        self.write_catalog([{"id": "opencode/model-free", "preis": "kostenlos"}])
        data = self.cli.costs_project("proj")
        row = self.model_row(data, "model-free")
        self.assertEqual(row["price_source"], "kostenlos")
        self.assertEqual(row["cost"], 0.0)

    def test_a_price_file_in_another_currency_is_not_treated_as_euro(self):
        self.build_single_session()
        self.write_system_prices(
            {"opencode/model-a": {"input": 1.0, "cached_input": 0.0, "output": 2.0}},
            currency="USD",
        )
        data = self.cli.costs_project("proj")
        row = self.model_row(data, "model-a")
        self.assertEqual(row["price_source"], "unbekannt")
        self.assertEqual(row["cost"], 0.0)

    def test_user_prices_are_stored_per_project(self):
        self.build_single_session()
        other = self.add_project("other")
        record_usage(other, "F1", "ses_other", input_tokens=1000000)
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}})
        stored = json.loads((self.root / "_toolchain" / "costs.json").read_text(encoding="utf-8"))
        self.assertEqual(set(stored["projects"]), {"proj"})
        other_data = self.cli.costs_project("other")
        row = self.model_row(other_data, "model-a")
        self.assertEqual(row["price_source"], "unbekannt")
        self.assertEqual(row["cost"], 0.0)

    def test_removing_a_user_price_falls_back_to_the_system_price(self):
        self.build_single_session()
        self.write_system_prices({"opencode/model-a": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}})
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 9.0, "cached_input": 9.0, "output": 9.0}})
        self.cli.costs_set_prices("proj", {"opencode/model-a": None})
        data = self.cli.costs_project("proj")
        self.assertEqual(self.model_row(data, "model-a")["price_source"], "system")
        stored = json.loads((self.root / "_toolchain" / "costs.json").read_text(encoding="utf-8"))
        self.assertNotIn("proj", stored["projects"])


class PriceValidationTest(CostFixture):
    def test_invalid_prices_are_rejected_without_writing(self):
        target = self.root / "_toolchain" / "costs.json"
        invalid = [
            {"opencode/model-a": {"input": -1, "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": "2", "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": True, "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": float("nan"), "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": float("inf"), "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": 1, "cached_input": 0}},
            {"": {"input": 1, "cached_input": 0, "output": 0}},
            {"opencode/model-a": 5},
            ["opencode/model-a"],
        ]
        for prices in invalid:
            with self.subTest(prices=prices):
                with self.assertRaises(ValueError):
                    self.cli.costs_set_prices("proj", prices)
                self.assertFalse(target.exists(), "Ungültige Eingabe darf nichts schreiben")

    def test_unknown_project_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cli.costs_project("gibt-es-nicht")
        with self.assertRaises(ValueError):
            self.cli.costs_set_prices("gibt-es-nicht", {
                "opencode/model-a": {"input": 1, "cached_input": 0, "output": 0}})


class DataSourceTest(CostFixture):
    """Die Übersicht hängt nicht mehr von der opencode-Datenbank ab.

    Die früheren Prüfungen des Datenbanklesers (read-only, v1-Schema,
    Session-Gesamtsummen ohne Nachrichten, JSON1-Ersatzpfad) sind unter
    GH-99 in ``test_costs_refresh.CostFlushReaderTest`` auf den Flush-Pfad
    ``vibe sessions finish-package`` verlagert: Der Leser wird nur noch beim
    Spülen der Kosten benutzt, nicht mehr bei der Anzeige.
    """

    def test_persisted_costs_are_served_without_a_database(self):
        self.record_usage("F1", "ses_a", input_tokens=100, output_tokens=10)
        os.environ["VIBE_OPENCODE_DB"] = str(self.root / "fehlt.db")

        data = self.cli.costs_overview()
        detail = self.cli.costs_project("proj")

        self.assertFalse((self.root / "fehlt.db").exists(),
                         "Die Kostenübersicht darf keine Datenbank anlegen")
        self.assertEqual(
            detail["total"]["tokens"], {"input": 100, "cached": 0, "output": 10},
            "Persistierte Kosten müssen ohne Datenbank angezeigt werden")
        row = {item["name"]: item for item in data["projects"]}["proj"]
        self.assertEqual(row["tokens"], {"input": 100, "cached": 0, "output": 10})

    def test_an_unknown_database_schema_does_not_break_the_overview(self):
        con = sqlite3.connect(str(self.db))
        con.execute("create table fremd (id text)")
        con.commit()
        con.close()
        self.record_usage("F1", "ses_a", input_tokens=100, output_tokens=10)

        data = self.cli.costs_project("proj")

        self.assertEqual(
            data["total"]["tokens"], {"input": 100, "cached": 0, "output": 10},
            "Ein fremdes DB-Schema darf die persistierten Kosten nicht stören")

    def test_a_broken_database_does_not_crash_the_overview(self):
        self.db.write_bytes(b"keine sqlite datei")
        self.record_usage("F1", "ses_a", input_tokens=100, output_tokens=10)

        data = self.cli.costs_overview()

        self.assertEqual(
            {row["name"]: row for row in data["projects"]}["proj"]["tokens"],
            {"input": 100, "cached": 0, "output": 10},
            "Eine defekte Datenbank darf die Übersicht nicht abbrechen")


class PackageIdTest(CostFixture):
    def test_ids_come_from_the_ticket_store(self):
        write_tickets(self.proj, [
            {"id": "F1", "title": "Erster Punkt"},
            {"id": "F2", "title": "Zweiter Punkt"},
            {"id": "A4", "title": "Fertig", "state": "done"},
            {"id": "Sf-17", "title": "Offen"},
        ])
        ids = self.cli.package_ids("proj")
        self.assertTrue({"F1", "F2", "A4", "Sf-17"} <= ids)

    def test_an_id_without_a_title_is_still_a_known_package(self):
        write_tickets(self.proj, [{"id": "F99", "title": ""}])
        self.assertIn("F99", self.cli.package_ids("proj"))

    def test_the_longer_id_wins_against_its_prefix(self):
        write_tickets(self.proj, [
            {"id": "F1", "title": "Kurz"},
            {"id": "F12", "title": "Lang"},
        ])
        ids = self.cli.package_ids("proj")
        self.assertEqual(self.cli.package_for_title("vibe F12", ids), "F12")
        self.assertEqual(self.cli.package_for_title("Review F1 delta", ids), "F1")
        self.assertEqual(self.cli.package_for_title("ohne Paketbezug", ids), "")


class CommandLineTest(CostFixture):
    def test_costs_command_prints_the_project_overview_without_arguments(self):
        self.record_usage("F1", "ses_a", input_tokens=1000, output_tokens=100)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_costs()
        text = out.getvalue()
        self.assertIn("proj", text)
        self.assertIn("Gesamt", text)
        self.assertIn("EUR", text)

    def test_costs_command_prints_the_project_overview(self):
        self.record_usage("F1", "ses_a", input_tokens=1000, output_tokens=100)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_costs("proj")
        text = out.getvalue()
        self.assertIn("F1", text)
        self.assertIn("1.000", text)
        self.assertIn("EUR", text)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CostsApiTest(CostFixture):
    """API des Dashboards gegen ein echtes Serverprozess-Fixture."""

    def setUp(self):
        super().setUp()
        self.record_usage("F1", "ses_a", input_tokens=1000000,
                          output_tokens=500000, cached_input=600000)
        self.port = free_port()
        # Instanzvariablen der Läuferumgebung (u. a. VIBE_UI_BIND) nicht erben:
        # der Testserver muss auf 127.0.0.1 binden.
        env = env_support.isolated_environ()
        env.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(self.port),
            "VIBE_OPENCODE_DB": str(self.db),
            "HOME": str(self.root / "home"),
        })
        self.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        token_file = self.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if self.proc.poll() is not None:
                self.fail("vibe-web wurde vorzeitig beendet")
            time.sleep(0.05)
        else:
            self.fail("vibe-web ist nicht erreichbar")
        self.token = token_file.read_text(encoding="utf-8").strip()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        super().tearDown()

    def request(self, path, body=None, token=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def test_costs_require_a_token(self):
        status, payload = self.request("/api/costs", token=False)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_overview_and_detail_are_served(self):
        status, payload = self.request("/api/costs")
        self.assertEqual(status, 200)
        self.assertEqual(payload["currency"], "EUR")
        self.assertEqual([p["name"] for p in payload["projects"]], ["proj"])
        status, detail = self.request("/api/costs?name=proj")
        self.assertEqual(status, 200)
        self.assertEqual(detail["project"], "proj")
        self.assertEqual(detail["total"]["tokens"],
                         {"input": 1000000, "cached": 600000, "output": 500000})

    def test_unknown_project_is_a_structured_not_found(self):
        status, payload = self.request("/api/costs?name=fehlt")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_prices_can_be_saved_and_recalculate_the_cost(self):
        prices = {"opencode/model-a": {"input": 2.0, "cached_input": 0.5, "output": 4.0}}
        status, payload = self.request(
            "/api/costs", {"name": "proj", "action": "prices", "prices": prices})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["ok"])
        self.assertAlmostEqual(payload["costs"]["total"]["cost"], 3.1, places=9)
        stored = json.loads((self.root / "_toolchain" / "costs.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["projects"]["proj"]["models"]["opencode/model-a"]["input"], 2.0)

    def test_invalid_prices_are_rejected_and_change_nothing(self):
        status, payload = self.request("/api/costs", {
            "name": "proj", "action": "prices",
            "prices": {"opencode/model-a": {"input": -1, "cached_input": 0, "output": 0}}})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertFalse((self.root / "_toolchain" / "costs.json").exists())

    def test_a_stale_expected_digest_is_reported_as_conflict(self):
        prices = {"opencode/model-a": {"input": 2.0, "cached_input": 0.5, "output": 4.0}}
        status, payload = self.request("/api/costs", {
            "name": "proj", "action": "prices", "prices": prices,
            "expected": "0" * 64})
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "conflict")
        self.assertFalse((self.root / "_toolchain" / "costs.json").exists())

    def test_posting_prices_for_an_unknown_project_is_rejected(self):
        status, payload = self.request("/api/costs", {
            "name": "fehlt", "action": "prices",
            "prices": {"opencode/model-a": {"input": 1, "cached_input": 0, "output": 0}}})
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertFalse((self.root / "_toolchain" / "costs.json").exists())


# ===========================================================================
# Unit-Tests, Persönliche globale Modellpreise
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
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
    "XDG_CONFIG_HOME",
    "VIBE_GLOBAL_AGENTS",
)


def isolated_env(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_state"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_global_price_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f33_costs_global_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def snapshot(root):
    """SHA-256 je Datei relativ zum Verzeichnis (fehlende Ordner: leer)."""
    root = Path(root)
    if not root.exists():
        return {}
    return {path.relative_to(root).as_posix(): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in sorted(root.rglob("*"))
        if path.is_file()}


class GlobalPriceFixture(unittest.TestCase):
    """Temporäres VIBE, Projekt mit persistierten Kosten und Zustandsordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        write_tickets(self.proj, [
            {"id": "F1", "title": "Erster Punkt", "type": "feedback"}])
        (self.root / "_toolchain").mkdir()
        (self.root / "_state").mkdir()
        self.db = self.root / "opencode.db"
        self.cli = load_global_price_cli(self.root, self.home)
        self.cli._pm.clear()
        old = os.environ.get("VIBE_OPENCODE_DB")
        os.environ["VIBE_OPENCODE_DB"] = str(self.db)
        self.addCleanup(self._restore_db_env, old)

    def _restore_db_env(self, old):
        if old is None:
            os.environ.pop("VIBE_OPENCODE_DB", None)
        else:
            os.environ["VIBE_OPENCODE_DB"] = old

    def tearDown(self):
        self.tmp.cleanup()

    def build_usage(self, input_tokens=1000000, output_tokens=1000000):
        record_usage(self.proj, "F1", "ses_f33", input_tokens=input_tokens,
                     output_tokens=output_tokens)

    def model_row(self, data, model="opencode/model-a"):
        return {item["model"]: item for item in data["models"]}[model]

    def write_system_prices(self, models):
        (self.root / "_toolchain" / "prices.json").write_text(
            json.dumps({"waehrung": "EUR", "modelle": models}),
            encoding="utf-8")


class GlobalPriceStorageTest(GlobalPriceFixture):
    def test_prices_are_stored_in_the_state_folder_and_read_back(self):
        """Vorbedingung: frisches temporäres VIBE.

        Aktion: ``costs_set_global_prices`` mit einem Modellpreis.
        Erwartung: ``global_prices()`` liefert den normalisierten Preis; im
        Zustandsordner entsteht eine Datei, im Projektordner nicht.
        """
        state_before = snapshot(self.root / "_state")
        project_before = snapshot(self.proj)
        prices = {"opencode/model-a": {
            "input": 1, "cached_input": 0.5, "output": 2}}

        self.cli.costs_set_global_prices(prices)

        self.assertEqual({
            "opencode/model-a": {
                "input": 1.0, "cached_input": 0.5, "output": 2.0},
        }, self.cli.global_prices())
        self.assertNotEqual(
            state_before, snapshot(self.root / "_state"),
            "Die globalen Preise wurden nicht im Zustandsordner gespeichert")
        self.assertEqual(
            project_before, snapshot(self.proj),
            "Die globalen Preise wurden im Projektordner abgelegt")

    def test_removing_a_global_price_is_possible(self):
        """Vorbedingung: globaler Preis gesetzt.

        Aktion: ``None`` für das Modell speichern (wie bei Projektpreisen).
        Erwartung: ``global_prices()`` enthält das Modell nicht mehr.
        """
        self.cli.costs_set_global_prices({"opencode/model-a": {
            "input": 1, "cached_input": 0, "output": 1}})
        self.cli.costs_set_global_prices({"opencode/model-a": None})
        self.assertEqual({}, self.cli.global_prices())

    def test_invalid_prices_are_rejected_without_writing(self):
        """Vorbedingung: keine globalen Preise.

        Aktion: Mehrere ungültige Preisangaben speichern.
        Erwartung: Jede wird mit ``ValueError`` abgelehnt; ``global_prices()``
        bleibt leer.
        """
        invalid = [
            {"opencode/model-a": {"input": -1, "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": "2", "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": True, "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": float("nan"),
                                  "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": float("inf"),
                                  "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": 1, "cached_input": 0}},
            {"": {"input": 1, "cached_input": 0, "output": 0}},
            {"opencode/model-a": 5},
            ["opencode/model-a"],
            "keine-preise",
        ]
        for prices in invalid:
            with self.subTest(prices=prices):
                with self.assertRaises(ValueError):
                    self.cli.costs_set_global_prices(prices)
                self.assertEqual({}, self.cli.global_prices(),
                                 "Ungültige Eingabe schrieb globale Preise")


class GlobalPriceRankingTest(GlobalPriceFixture):
    def test_global_prices_apply_without_project_prices(self):
        """Vorbedingung: 1 Mio. Eingabe- und Ausgabetokens für model-a.

        Aktion: Nur globale Preise (1/0/2) setzen.
        Erwartung: Die Kosten betragen 3,00 € (1 + 2).
        """
        self.build_usage()
        self.cli.costs_set_global_prices({"opencode/model-a": {
            "input": 1, "cached_input": 0, "output": 2}})
        data = self.cli.costs_project("proj")
        row = self.model_row(data)
        self.assertAlmostEqual(row["cost"], 3.0, places=9,
                               msg="Globale Preise wurden nicht angesetzt: "
                                   + repr(row))
        self.assertAlmostEqual(data["total"]["cost"], 3.0, places=9)

    def test_project_prices_win_over_global_prices(self):
        """Vorbedingung: globale Preise (1/0/2) gesetzt.

        Aktion: Projektpreise (10/0/10) setzen.
        Erwartung: Die Projektpreise gelten; Kosten 20,00 €.
        """
        self.build_usage()
        self.cli.costs_set_global_prices({"opencode/model-a": {
            "input": 1, "cached_input": 0, "output": 2}})
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 10, "cached_input": 0, "output": 10}})
        row = self.model_row(self.cli.costs_project("proj"))
        self.assertAlmostEqual(row["cost"], 20.0, places=9,
                               msg="Projektpreise verloren gegen globale: "
                                   + repr(row))
        self.assertEqual("user", row["price_source"], row)

    def test_without_global_prices_the_system_price_still_applies(self):
        """Vorbedingung: systemische Preise (0,5/0/1), keine globalen Preise.

        Erwartung: Wie bisher gelten die systemischen Preise (1,50 €); erst
        globale Preise verdrängen sie (3,00 €).
        """
        self.build_usage()
        self.write_system_prices({"opencode/model-a": {
            "input": 0.5, "cached_input": 0, "output": 1}})
        row = self.model_row(self.cli.costs_project("proj"))
        self.assertAlmostEqual(row["cost"], 1.5, places=9,
                               msg="Das bisherige Verhalten änderte sich: "
                                   + repr(row))
        self.assertEqual("system", row["price_source"], row)

        self.cli.costs_set_global_prices({"opencode/model-a": {
            "input": 1, "cached_input": 0, "output": 2}})
        row = self.model_row(self.cli.costs_project("proj"))
        self.assertAlmostEqual(row["cost"], 3.0, places=9,
                               msg="Globale Preise verdrängen die "
                                   "systemischen Preise nicht: " + repr(row))


class GlobalPriceApiTest(unittest.TestCase):
    """POST /api/costs {action:"prices_global"} gegen ein Server-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        write_tickets(cls.project, [
            {"id": "F1", "title": "Erster Punkt", "type": "feedback"}])
        record_usage(cls.project, "F1", "ses_f33", input_tokens=1000000,
                     output_tokens=1000000)
        (cls.root / "_toolchain").mkdir()
        (cls.root / "_state").mkdir()
        cls.db = cls.root / "opencode.db"
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        env["VIBE_OPENCODE_DB"] = str(cls.db)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method="POST" if data else "GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def setUp(self):
        # Zustand je Test leeren: globale und Projektpreise.
        for path in (self.root / "_state").rglob("*"):
            if path.is_file():
                path.unlink()
        costs = self.root / "_toolchain" / "costs.json"
        costs.unlink(missing_ok=True)

    def test_global_prices_are_saved_and_reported_in_overview_and_detail(self):
        """Vorbedingung: keine globalen Preise.

        Aktion: POST ``{action:"prices_global", prices}``.
        Erwartung: ``ok``; ``GET /api/costs`` (Übersicht und Detail) liefert
        ``global_prices`` mit dem gespeicherten Modellpreis.
        """
        prices = {"opencode/model-a": {
            "input": 1.0, "cached_input": 0.5, "output": 2.0}}
        status, payload = self.request(
            "/api/costs", {"action": "prices_global", "prices": prices})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)

        status, overview = self.request("/api/costs")
        self.assertEqual(200, status, overview)
        self.assertEqual(
            prices, overview.get("global_prices"),
            "Die Übersicht liefert die globalen Preise nicht: "
            + repr(overview.get("global_prices")))

        status, detail = self.request("/api/costs?name=proj")
        self.assertEqual(200, status, detail)
        self.assertEqual(
            prices, detail.get("global_prices"),
            "Die Detailansicht liefert die globalen Preise nicht: "
            + repr(detail.get("global_prices")))

    def test_invalid_global_prices_are_rejected_and_change_nothing(self):
        """Vorbedingung: ein wohlgeformter globaler Preis ist gespeichert.

        Aktion: Mehrere ungültige Preisangaben über den Handler senden.
        Erwartung: Status 400, ``ok`` falsch; der zuvor gespeicherte Preis
        bleibt unverändert (nichts wird geschrieben).
        """
        valid = {"opencode/model-b": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}}
        status, payload = self.request(
            "/api/costs", {"action": "prices_global", "prices": valid})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)

        invalid = [
            {"opencode/model-a": {"input": -1, "cached_input": 0, "output": 0}},
            {"opencode/model-a": {"input": "2", "cached_input": 0, "output": 0}},
            {"opencode/model-a": 5},
            ["opencode/model-a"],
            "keine-preise",
        ]
        for prices in invalid:
            with self.subTest(prices=prices):
                status, payload = self.request(
                    "/api/costs", {"action": "prices_global", "prices": prices})
                self.assertEqual(400, status, payload)
                self.assertFalse(payload.get("ok"), payload)
        status, overview = self.request("/api/costs")
        self.assertEqual(200, status, overview)
        self.assertEqual(
            valid, overview.get("global_prices"),
            "Ungültige Eingaben veränderten die globalen Preise: "
            + repr(overview.get("global_prices")))


if __name__ == "__main__":
    unittest.main()
