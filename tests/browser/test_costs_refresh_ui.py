"""Browserabnahme für B1: Kostentabelle aktualisiert sich nach jedem AP.

Das Dashboard muss die Kostenansicht von selbst neu laden, sobald opencode
neue Sitzungsdaten (ein abgeschlossenes Arbeitspaket) geschrieben hat. Dabei
sollen nur die tatsächlich geänderten Zeilen ersetzt werden; unveränderte
Projekt- und Paketzeilen bleiben dasselbe DOM-Element. Bereits eingetippte,
noch nicht gespeicherte Preise dürfen nicht überschrieben werden.

Der Test startet das echte Dashboard auf einem eigenen Port gegen eine
temporäre opencode-Datenbank und schreibt neue Sitzungen direkt in diese
Datenbank, während die Seite geöffnet ist. Es werden keine echten Sitzungen
verändert und keine Modellaufrufe ausgelöst.
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

from tests.browser.test_costs_ui import DDL_V2, free_port

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"


def insert_session(con, session_id, directory, title, agent="coding-agent",
                   model_id="model-a", project_id="proj"):
    con.execute(
        "insert into session_v2 (id, project_id, slug, directory, title,"
        " version, agent, model, time_created, time_updated)"
        " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            project_id,
            "slug-" + session_id,
            str(directory),
            title,
            "2.1.4",
            agent,
            json.dumps({"id": model_id, "providerID": "opencode"}),
            1,
            1,
        ),
    )


def insert_message(con, session_id, agent="coding-agent", model_id="model-a",
                   input_tokens=0, output_tokens=0, reasoning=0, cache_read=0,
                   seq=1):
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


class CostsRefreshBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.proj = self.root / "proj"
        self.proj2 = self.root / "proj2"
        for project, feedback in (
            (self.proj, "- [ ] F1 Erster Punkt\n  Beschreibung: Erste\n\n"
                       "- [ ] F2 Zweiter Punkt\n  Beschreibung: Zweite\n"),
            (self.proj2, "- [ ] X1 Anderer Punkt\n  Beschreibung: Andere\n"),
        ):
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8"
            )
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n\n" + feedback, encoding="utf-8"
            )
        (self.root / "_toolchain").mkdir()
        self.db = self.root / "opencode.db"
        con = sqlite3.connect(str(self.db))
        con.executescript(DDL_V2)
        insert_session(con, "ses_a", self.proj, "proj F1")
        insert_message(con, "ses_a", input_tokens=400000, output_tokens=300000,
                       reasoning=200000, cache_read=600000)
        insert_session(con, "ses_b", self.proj, "proj F2")
        insert_message(con, "ses_b", input_tokens=100000, output_tokens=10000)
        insert_session(con, "ses_p2", self.proj2, "proj2 X1")
        insert_message(con, "ses_p2", input_tokens=200000, output_tokens=20000)
        con.commit()
        con.close()

        self.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(self.port),
                "VIBE_OPENCODE_DB": str(self.db),
                "HOME": str(self.root / "home"),
            }
        )
        for key in list(env):
            if key.startswith("VIBE_") and key not in {
                "VIBE", "VIBE_NO_CONTAINER", "VIBE_UI_PORT", "VIBE_OPENCODE_DB"
            }:
                env.pop(key)
        env.pop("SANDBOX", None)
        env.pop("SANDBOX_TOOLS", None)
        self.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
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
                output = self.proc.stdout.read() if self.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        self.token = token_file.read_text(encoding="utf-8").strip()
        self.base = f"http://127.0.0.1:{self.port}"
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self.proc.stdout:
            self.proc.stdout.close()
        self.tmp.cleanup()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def add_session(self, session_id, project, title, input_tokens,
                    output_tokens=0, cache_read=0):
        con = sqlite3.connect(str(self.db))
        insert_session(con, session_id, project, title)
        insert_message(con, session_id, input_tokens=input_tokens,
                       output_tokens=output_tokens, cache_read=cache_read)
        con.commit()
        con.close()

    def open_costs(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.get_by_role("button", name="Kosten", exact=True).click()
        self.page.locator("#costs").wait_for()

    def open_detail(self):
        self.open_costs()
        self.page.locator('tr.row[data-project="proj"]').click()
        self.page.locator("#cost-detail").wait_for()
        self.page.locator('#cost-detail tr[data-package]').first.wait_for()

    def test_overview_refreshes_automatically_and_keeps_unchanged_rows(self):
        self.open_costs()
        self.page.locator('tr[data-project="proj"]').wait_for()
        self.page.locator('tr[data-project="proj2"]').wait_for()
        self.assertNotIn(
            "1.200.000",
            self.page.locator('tr[data-project="proj"]').inner_text(),
            "Ausgangswert ist bereits vorhanden; der Test würde nichts prüfen",
        )
        self.page.evaluate(
            "window.__unchanged = document.querySelector('tr[data-project=\"proj2\"]')"
        )

        self.add_session("ses_new", self.proj, "proj F1", input_tokens=100000)

        self.wait_until(
            lambda: "1.200.000" in self.page.locator('tr[data-project="proj"]').inner_text(),
            message="Die Projektzeile wurde ohne Klick nicht aktualisiert",
        )
        self.assertTrue(
            self.page.evaluate(
                "window.__unchanged === document.querySelector('tr[data-project=\"proj2\"]')"
            ),
            "Unveränderte Projektzeile wurde neu aufgebaut",
        )

    def test_detail_refreshes_changed_package_and_keeps_entered_price(self):
        self.open_detail()
        self.page.locator('#cost-detail tr[data-package="F2"]').wait_for()
        self.page.evaluate(
            "window.__unchanged = document.querySelector("
            "'#cost-detail tr[data-package=\"F2\"]')"
        )
        price = self.page.locator(
            'input[data-model="opencode/model-a"][data-field="input"]'
        )
        price.fill("2.5")

        self.add_session("ses_new", self.proj, "proj F1", input_tokens=100000)

        self.wait_until(
            lambda: "1.200.000" in self.page.locator("#cost-detail").inner_text(),
            message="Die Paketzeile wurde ohne Klick nicht aktualisiert",
        )
        self.assertTrue(
            self.page.evaluate(
                "window.__unchanged === document.querySelector("
                "'#cost-detail tr[data-package=\"F2\"]')"
            ),
            "Unverändertes Paket wurde neu aufgebaut",
        )
        self.assertEqual(
            price.input_value(), "2.5",
            "Eingetippter, noch nicht gespeicherter Preis wurde überschrieben",
        )

    def test_alias_sessions_show_values_for_the_project(self):
        con = sqlite3.connect(str(self.db))
        con.execute(
            "create table project (id text primary key, worktree text not null,"
            " time_created integer not null, time_updated integer not null,"
            " sandboxes text not null default '[]')"
        )
        con.execute(
            "insert into project (id, worktree, time_created, time_updated)"
            " values (?, ?, ?, ?)",
            ("proj2-id", str(self.proj2), 1, 1),
        )
        insert_session(
            con, "ses_alias", "/run/host" + str(self.proj2), "proj2 X1",
            project_id="proj2-id",
        )
        insert_message(con, "ses_alias", input_tokens=500000, output_tokens=50000)
        con.commit()
        con.close()

        self.open_costs()

        row = self.page.locator('tr[data-project="proj2"]')
        row.wait_for()
        text = row.inner_text()
        self.assertIn("700.000", text, "Alias-Sitzung fehlt in der Projektzeile")
        self.assertIn("70.000", text, "Alias-Ausgabe fehlt in der Projektzeile")


if __name__ == "__main__":
    unittest.main()
