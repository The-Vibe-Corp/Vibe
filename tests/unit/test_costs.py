"""Tests für die Kostenermittlung je Arbeitspaket und Projekt (F12).

Vibe liest die Sitzungsdaten von opencode ausschließlich lesend und rechnet die
verbrauchten Tokens je Arbeitspaket (Paket-ID im Sitzungstitel), Agent und
Modell in Euro um. Geprüft werden:

* Tokenzählung: Eingabe enthält die gecachten Tokens, Ausgabe enthält
  Reasoning-Tokens.
* Zuordnung: Sitzungen eines Projekts, Unterhaltungen von Unteragenten zum
  selben Paket, nicht zugeordnete Sitzungen als eigenes Paket.
* Summen: die Projektstatistik ist die Summe aller Paketstatistiken.
* Preise: Nutzereingabe je Projekt schlägt systemische Preise, kostenlose
  Modelle kosten 0, unbekannte Preise werden mit 0 angesetzt.
* Robustheit: fehlende oder fremde Datenbanken werden gemeldet statt
  angelegt oder als leerer Erfolg ausgegeben; die Datenbank bleibt unverändert.
* Speicherung: Nutzerpreise liegen je Projekt in ``_toolchain/costs.json``.

Alle Tests arbeiten in temporären Verzeichnissen mit einer eigens gebauten
Sitzungsdatenbank. Es werden keine echten opencode-Sitzungen verändert und
keine Modellaufrufe ausgelöst.
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

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

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
        (self.proj / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n"
            "- [ ] F1 Erster Punkt\n  Beschreibung: Erste Beschreibung\n\n"
            "- [ ] F2 Zweiter Punkt\n  Beschreibung: Zweite Beschreibung\n",
            encoding="utf-8",
        )
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
        (path / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
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


class TokenAggregationTest(CostFixture):
    def build_usage(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 50, 3000, seq=1)
        add_message(con, "ses_a", "coding-agent", "model-a", 2000, 200, 50, 4000, seq=2)
        add_session(con, "ses_b", self.proj, "Review F1 (@code-reviewer subagent)",
                    parent="ses_a", agent="code-reviewer")
        add_message(con, "ses_b", "code-reviewer", "model-b", 500, 10, 0, 0, seq=1)
        add_session(con, "ses_c", self.proj, "proj F2")
        add_message(con, "ses_c", "coding-agent", "model-a", 100, 20, 0, 0, seq=1)
        add_session(con, "ses_d", self.proj, "proj Nebenarbeit")
        add_message(con, "ses_d", "coding-agent", "model-a", 50, 5, 0, 0, seq=1)
        con.commit()
        con.close()
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
        self.assertAlmostEqual(data["total"]["cost"], 0.0115, places=9)

    def test_unknown_model_price_is_zero(self):
        data = self.build_usage()
        package = {p["id"]: p for p in data["packages"]}["F1"]
        model = {m["model"]: m for m in package["models"]}["opencode/model-b"]
        self.assertEqual(model["price_source"], "unbekannt")
        self.assertEqual(model["cost"], 0.0)

    def test_unassigned_sessions_form_their_own_package(self):
        data = self.build_usage()
        unassigned = [p for p in data["packages"] if p["id"] == ""]
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]["title"], "Ohne Arbeitspaket")
        self.assertEqual(unassigned[0]["tokens"], {"input": 50, "cached": 0, "output": 5})

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
        self.assertEqual(data["total"]["sessions"], 4)
        self.assertEqual(data["total"]["tokens"],
                         {"input": 10650, "cached": 7000, "output": 435})

    def test_overview_lists_every_project_with_its_totals(self):
        self.build_usage()
        data = self.cli.costs_overview()
        self.assertTrue(data["available"])
        self.assertEqual(data["currency"], "EUR")
        row = {p["name"]: p for p in data["projects"]}["proj"]
        self.assertEqual(row["packages"], 3)
        self.assertEqual(row["sessions"], 4)
        self.assertAlmostEqual(row["cost"], 0.0115, places=9)

    def test_sessions_of_other_projects_and_outside_roots_are_ignored(self):
        other = self.add_project("other")
        con = make_db(self.db)
        add_session(con, "ses_own", self.proj, "proj F1")
        add_message(con, "ses_own", "coding-agent", "model-a", 10, 1, 0, 0)
        add_session(con, "ses_other", other, "other F1")
        add_message(con, "ses_other", "coding-agent", "model-a", 999, 999, 0, 0)
        add_session(con, "ses_outside", self.root / "aussen", "proj F1")
        add_message(con, "ses_outside", "coding-agent", "model-a", 888, 888, 0, 0)
        con.commit()
        con.close()
        data = self.cli.costs_project("proj")
        self.assertEqual(data["total"]["tokens"], {"input": 10, "cached": 0, "output": 1})
        self.assertEqual(data["sessions"], 1)

    def test_a_session_in_a_subdirectory_belongs_to_the_project(self):
        con = make_db(self.db)
        add_session(con, "ses_sub", self.proj / "unterordner", "proj F1")
        add_message(con, "ses_sub", "coding-agent", "model-a", 7, 3, 0, 0)
        con.commit()
        con.close()
        data = self.cli.costs_project("proj")
        self.assertEqual(data["sessions"], 1)
        self.assertEqual(data["total"]["tokens"], {"input": 7, "cached": 0, "output": 3})


class PriceResolutionTest(CostFixture):
    def build_single_session(self, model="model-a"):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", model, 1000000, 500000, 0, 0)
        con.commit()
        con.close()

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
        con = sqlite3.connect(str(self.db))
        add_session(con, "ses_other", other, "other F1")
        add_message(con, "ses_other", "coding-agent", "model-a", 1000000, 0, 0, 0)
        con.commit()
        con.close()
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
    def test_missing_database_is_reported_and_not_created(self):
        os.environ["VIBE_OPENCODE_DB"] = str(self.root / "fehlt.db")
        data = self.cli.costs_overview()
        self.assertFalse(data["available"])
        self.assertIn("fehlt.db", data["message"])
        self.assertFalse((self.root / "fehlt.db").exists())
        detail = self.cli.costs_project("proj")
        self.assertFalse(detail["available"])
        self.assertEqual(detail["total"]["tokens"], {"input": 0, "cached": 0, "output": 0})

    def test_unknown_database_schema_is_reported(self):
        con = sqlite3.connect(str(self.db))
        con.execute("create table fremd (id text)")
        con.commit()
        con.close()
        data = self.cli.costs_overview()
        self.assertFalse(data["available"])
        self.assertIn("Schema", data["message"])

    def test_a_broken_database_is_reported_instead_of_crashing(self):
        self.db.write_bytes(b"keine sqlite datei")
        data = self.cli.costs_overview()
        self.assertFalse(data["available"])
        self.assertTrue(data["message"])

    def test_the_database_is_only_read(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 10, 1, 0, 0)
        con.commit()
        con.close()
        before = (self.db.stat().st_size, self.db.stat().st_mtime_ns)
        self.cli.costs_project("proj")
        after = (self.db.stat().st_size, self.db.stat().st_mtime_ns)
        self.assertEqual(before, after)
        self.assertFalse(Path(str(self.db) + "-wal").exists())
        self.assertFalse(Path(str(self.db) + "-shm").exists())

    def test_legacy_schema_is_read(self):
        con = make_db(self.db, schema="v1")
        add_session(con, "ses_a", self.proj, "proj F1", schema="v1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 10, 500,
                    schema="v1")
        add_message(con, "ses_a", "coding-agent", "model-a", 0, 0, 0, 0,
                    schema="v1", role="user", seq=2)
        con.commit()
        con.close()
        self.cli.costs_set_prices("proj", {"opencode/model-a": {
            "input": 1.0, "cached_input": 0.0, "output": 2.0}})
        data = self.cli.costs_project("proj")
        package = {p["id"]: p for p in data["packages"]}["F1"]
        self.assertEqual(package["tokens"], {"input": 1500, "cached": 500, "output": 110})
        self.assertAlmostEqual(package["cost"], 0.001 + 0.00022, places=9)

    def test_a_session_without_messages_uses_its_stored_totals(self):
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
        data = self.cli.costs_project("proj")
        package = {p["id"]: p for p in data["packages"]}["F1"]
        self.assertEqual(package["tokens"], {"input": 150, "cached": 50, "output": 25})
        self.assertEqual(package["models"][0]["model"], "opencode/model-a")


    def test_without_json1_the_messages_are_read_in_python(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 10, 500)
        add_message(con, "ses_a", "code-reviewer", "model-b", 200, 20, 0, 0, seq=2)
        con.commit()
        con.close()
        self.cli._json1_available = lambda conn: False
        data = self.cli.costs_project("proj")
        package = {p["id"]: p for p in data["packages"]}["F1"]
        self.assertEqual(package["tokens"], {"input": 1700, "cached": 500, "output": 130})
        self.assertEqual({m["model"] for m in package["models"]},
                         {"opencode/model-a", "opencode/model-b"})


class PackageIdTest(CostFixture):
    def test_ids_come_from_feedback_and_tickets(self):
        (self.proj / "TICKETS.md").write_text(
            "# TICKETS\n\n- [x] A4 Fertig\n- [ ] Sf-17 Offen\n", encoding="utf-8")
        ids = self.cli.package_ids("proj")
        self.assertTrue({"F1", "F2", "A4", "Sf-17"} <= ids)

    def test_an_id_without_a_title_is_still_a_known_package(self):
        (self.proj / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F99\n", encoding="utf-8")
        self.assertIn("F99", self.cli.package_ids("proj"))

    def test_the_longer_id_wins_against_its_prefix(self):
        (self.proj / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Kurz\n- [ ] F12 Lang\n", encoding="utf-8")
        ids = self.cli.package_ids("proj")
        self.assertEqual(self.cli.package_for_title("vibe F12", ids), "F12")
        self.assertEqual(self.cli.package_for_title("Review F1 delta", ids), "F1")
        self.assertEqual(self.cli.package_for_title("ohne Paketbezug", ids), "")


class CommandLineTest(CostFixture):
    def test_costs_command_prints_the_project_overview_without_arguments(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 0, 0)
        con.commit()
        con.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_costs()
        text = out.getvalue()
        self.assertIn("proj", text)
        self.assertIn("Gesamt", text)
        self.assertIn("EUR", text)

    def test_costs_command_prints_the_project_overview(self):
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 1000, 100, 0, 0)
        con.commit()
        con.close()
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
        con = make_db(self.db)
        add_session(con, "ses_a", self.proj, "proj F1")
        add_message(con, "ses_a", "coding-agent", "model-a", 400000, 300000, 200000, 600000)
        con.commit()
        con.close()
        self.port = free_port()
        env = os.environ.copy()
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


if __name__ == "__main__":
    unittest.main()
