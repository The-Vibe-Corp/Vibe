"""Browserabnahme für die Kostenübersicht (F12).

Das Dashboard zeigt je Projekt und je Arbeitspaket die verbrauchten Tokens
(Eingabe, davon cached, Ausgabe) und die daraus berechneten Euro-Kosten.
Eigene Preise werden je Projekt eingetragen, schlagen systemische Preise und
bleiben nach einem Neuladen erhalten.

Der Test startet das echte Dashboard auf einem eigenen Port gegen eine
temporäre opencode-Datenbank. Es werden keine echten Sitzungen verändert und
keine Modellaufrufe ausgelöst.
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F12-kosten.png"

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
CREATE TABLE "session_message" (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `type` text NOT NULL,
  `seq` integer NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL
);
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CostsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Erster Punkt\n  Beschreibung: Erste Beschreibung\n",
            encoding="utf-8",
        )
        (cls.root / "_toolchain").mkdir()
        cls.db = cls.root / "opencode.db"
        con = sqlite3.connect(str(cls.db))
        con.executescript(DDL_V2)
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title, version,"
            " agent, model, time_created, time_updated) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ses_a",
                "proj",
                "slug-a",
                str(cls.project),
                "proj F1",
                "2.1.4",
                "coding-agent",
                json.dumps({"id": "model-a", "providerID": "opencode"}),
                1,
                1,
            ),
        )
        data = {
            "agent": "coding-agent",
            "model": {"id": "model-a", "providerID": "opencode"},
            "tokens": {
                "input": 400000,
                "output": 300000,
                "reasoning": 200000,
                "cache": {"read": 600000, "write": 0},
            },
        }
        con.execute(
            "insert into session_message (id, session_id, type, seq, time_created,"
            " time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_a", "ses_a", "assistant", 1, 1, 1, json.dumps(data)),
        )
        con.commit()
        con.close()

        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_OPENCODE_DB": str(cls.db),
                "HOME": str(cls.root / "home"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        costs = self.root / "_toolchain" / "costs.json"
        if costs.exists():
            costs.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_costs(self):
        self.page.goto(self.base + "/#t=" + self.token)
        nav = self.page.get_by_role("button", name="Costs", exact=True)
        nav.wait_for()
        nav.click()
        self.page.locator("#costs").wait_for()

    def open_detail(self):
        self.open_costs()
        self.page.locator('tr.row[data-project="proj"]').click()
        self.page.locator("#cost-detail").wait_for()

    def fill_prices(self, input_price, cached_price, output_price):
        for field, value in (
            ("input", input_price),
            ("cached_input", cached_price),
            ("output", output_price),
        ):
            self.page.locator(
                f'input[data-model="opencode/model-a"][data-field="{field}"]'
            ).fill(value)

    def test_project_overview_lists_tokens_and_costs(self):
        self.open_costs()

        card = self.page.locator("#costs")
        text = card.inner_text()
        self.assertIn("proj", text)
        self.assertIn("1,000,000", text)
        self.assertIn("600,000", text)
        self.assertIn("500,000", text)
        self.assertIn("0.0000 €", text)
        self.assertIn("Total", text)

    def test_detail_shows_packages_models_and_unknown_prices(self):
        self.open_detail()

        text = self.page.locator("#cost-detail").inner_text()
        self.assertIn("F1", text)
        self.assertIn("coding-agent", text)
        self.assertIn("opencode/model-a", text)
        self.assertIn("1,000,000", text)
        self.assertIn("600,000", text)
        self.assertIn("500,000", text)
        self.assertIn("Price unknown", text)

    def test_entered_prices_override_unknown_costs_and_persist(self):
        self.open_detail()

        self.fill_prices("2", "0.5", "4")
        self.page.get_by_role("button", name="Save prices").click()

        self.wait_until(
            lambda: "3.1000" in self.page.locator("#cost-detail").inner_text(),
            message="Kosten wurden nach dem Speichern nicht neu berechnet",
        )
        self.assertIn(
            "custom price", self.page.locator("#cost-prices").inner_text()
        )
        stored = json.loads(
            (self.root / "_toolchain" / "costs.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            stored["projects"]["proj"]["models"]["opencode/model-a"],
            {"input": 2.0, "cached_input": 0.5, "output": 4.0},
        )

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT), full_page=True)
        self.assertTrue(
            SHOT.exists() and SHOT.stat().st_size > 0,
            "Screenshot der Kostenübersicht fehlt",
        )

        self.page.reload()
        self.page.get_by_role("button", name="Costs", exact=True).click()
        self.page.locator("#costs").wait_for()
        self.page.locator('tr.row[data-project="proj"]').click()
        self.page.locator("#cost-detail").wait_for()
        self.assertIn(
            "3.1000",
            self.page.locator("#cost-detail").inner_text(),
            "gespeicherte Preise gelten nach dem Neuladen nicht",
        )

    def test_invalid_input_is_reported_and_nothing_is_stored(self):
        self.open_detail()

        self.fill_prices("2", "0.5", "")
        self.page.get_by_role("button", name="Save prices").click()

        toast = self.page.locator("#toasts")
        toast.wait_for()
        self.assertRegex(
            toast.inner_text(),
            r"Bitte für opencode/model-a|Please enter opencode/model-a")
        self.assertFalse((self.root / "_toolchain" / "costs.json").exists())
        self.assertIn("0.0000", self.page.locator("#cost-detail").inner_text())


if __name__ == "__main__":
    unittest.main()
