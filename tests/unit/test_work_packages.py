"""Tests für Arbeitspakete und Bugmeldungen aus der Oberfläche (F15).

Geprüft werden das Markdown-Modell für TICKETS.md (Lesen, Anlegen, Ändern,
Löschen), die Bugmeldung in FEEDBACK.md, die HTTP-API des Dashboards und die
tatsächlich ausgelieferte Projektdetail-Seite. Alle Schreibvorgänge arbeiten
auf echten Dateien in einem temporären Arbeitsbereich.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.unit.web_page import served_page

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

TICKETS = """# TICKETS — Test

- [ ] F15 Arbeitspakete
  Beschreibung: Bestehendes Paket
  Priorität: P1

- [x] V-001 Erledigtes Paket
  Beschreibung: Fertig
  Priorität: P0
  Commit: abcdef1; Test: test_x

- [ ] V-099 Blockiertes Paket
  Beschreibung: Wartet
  BLOCKIERT: fehlende Freigabe
"""

FEEDBACK = """# FEEDBACK — Test

- [ ] F1 Bestehender Punkt
  Beschreibung: Bestehende Beschreibung
"""

# Die Prüfumgebung kann eine produktive vibe-Umgebung erben. Ohne diese Liste
# würde das Dashboard den echten Agentenordner, Zustandsordner und die echte
# Laufzeit lesen und beschreiben.
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
)


def isolated_env(root, home, port):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(port),
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, mit isoliertem VIBE."""
    root = Path(vibe_root)
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(root, root / "home", 8787))
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_work_packages_under_test", str(CLI)
        )
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def non_empty_lines(text):
    return [line for line in text.splitlines() if line.strip()]


def numbered_id_parts(ident):
    """Zerlegt eine fortlaufende ID in Präfix und Nummer, ohne ein konkretes
    Präfix festzulegen. Der Präfix ist ein Implementierungsbeschluss."""
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.:-]*?)(\d+)", ident)
    if not match:
        raise AssertionError(
            "Erwartete fortlaufende Auto-ID, erhalten: " + repr(ident)
        )
    return match.group(1), int(match.group(2))


class WorkPackageFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli = load_cli(self.root)
        self.tickets = self.project / "TICKETS.md"
        self.feedback = self.project / "FEEDBACK.md"

    def tearDown(self):
        self.tmp.cleanup()

    def write_tickets(self, text):
        self.tickets.write_text(text, encoding="utf-8")

    def write_feedback(self, text):
        self.feedback.write_text(text, encoding="utf-8")

    def ticket_text(self):
        return self.tickets.read_text(encoding="utf-8")

    def feedback_text(self):
        return self.feedback.read_text(encoding="utf-8")


class WorkPackageModelTest(WorkPackageFixture):
    def test_lists_work_packages_with_title_description_and_state(self):
        self.write_tickets(TICKETS)

        entries = self.cli.ticket_items("proj")

        self.assertEqual([e["id"] for e in entries], ["F15", "V-001", "V-099"])
        self.assertEqual(entries[0]["title"], "Arbeitspakete")
        self.assertEqual(entries[0]["description"], "Bestehendes Paket")
        self.assertEqual(entries[0]["state"], "offen")
        self.assertFalse(entries[0]["completed"])
        self.assertEqual(entries[1]["state"], "erledigt")
        self.assertTrue(entries[1]["completed"])
        self.assertEqual(entries[2]["state"], "BLOCKIERT")
        self.assertFalse(entries[2]["completed"])

    def test_missing_tickets_file_yields_no_entries(self):
        self.assertEqual([], self.cli.ticket_items("proj"))

    def test_update_changes_title_and_description_but_keeps_other_fields(self):
        self.write_tickets(TICKETS)

        self.cli.ticket_update(
            "proj", "F15", "Neuer Titel", "Neue Beschreibung"
        )

        text = self.ticket_text()
        self.assertIn("- [ ] F15 Neuer Titel", text)
        self.assertIn("  Beschreibung: Neue Beschreibung", text)
        self.assertIn("  Priorität: P1", text)
        self.assertIn("- [x] V-001 Erledigtes Paket", text)
        self.assertIn("V-099 Blockiertes Paket", text)

    def test_update_rejects_completed_work_package(self):
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "nicht bearbeitbar"):
            self.cli.ticket_update("proj", "V-001", "Neu", "Neu")

        self.assertEqual(self.ticket_text(), before)

    def test_update_rejects_empty_title_and_line_break(self):
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "Titel fehlt"):
            self.cli.ticket_update("proj", "F15", "  ", "Neu")
        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.ticket_update(
                "proj", "F15", "Neu\n- [ ] F99 Eingeschmuggelt", "Neu"
            )

        self.assertEqual(self.ticket_text(), before)

    def test_update_rejects_unknown_id_without_changing_file(self):
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.ticket_update("proj", "F99", "Neu", "Neu")

        self.assertEqual(self.ticket_text(), before)

    def test_add_work_package_appends_and_keeps_existing_entries(self):
        self.write_tickets(TICKETS)

        result = self.cli.add_ticket(
            "proj", "F18", "Neues Paket", "Zeile eins\nZeile zwei"
        )

        self.assertEqual(result, "F18")
        text = self.ticket_text()
        self.assertIn("- [ ] F18 Neues Paket", text)
        self.assertIn("  Beschreibung: Zeile eins\n  Zeile zwei", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)
        entry = {
            e["id"]: e for e in self.cli.ticket_items("proj")
        }["F18"]
        self.assertEqual(entry["description"], "Zeile eins\nZeile zwei")
        self.assertEqual(entry["state"], "offen")

    def test_add_work_package_rejects_duplicate_id(self):
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "existiert bereits"):
            self.cli.add_ticket("proj", "F15", "Doppelt", "Text")

        self.assertEqual(self.ticket_text(), before)

    def test_add_work_package_rejects_invalid_id(self):
        """F23/AK7: Eine leere ID wird jetzt automatisch vergeben, deshalb
        erwartet dieser Test für Blanks kein Fehler mehr. Manuell angegebene
        ungültige IDs müssen unverändert ablehnen."""
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "Ungültige ID"):
            self.cli.add_ticket("proj", "- [ ] F99", "Titel", "Text")
        with self.assertRaisesRegex(ValueError, "Titel fehlt"):
            self.cli.add_ticket("proj", "F18", "  ", "Text")
        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.add_ticket("proj", "F18", "Titel\n- [ ] F99", "Text")

        self.assertEqual(self.ticket_text(), before)

    def test_add_work_package_with_blank_id_gets_an_auto_assigned_id(self):
        """F23/AK1+AK2: Ohne ID (leer oder leerzeichen) wird das Paket
        trotzdem angelegt und erhält eine nicht-leere Auto-ID."""
        self.write_tickets(TICKETS)

        for blank in ("", "  "):
            assigned = self.cli.add_ticket(
                "proj", blank, "Paket ohne verwaltete ID", "Zeile eins"
            )
            self.assertTrue(assigned)
            text = self.ticket_text()
            self.assertIn("- [ ] %s Paket ohne verwaltete ID" % assigned, text)
            self.assertIn("  Beschreibung: Zeile eins", text)
            # Bestehende Einträge bleiben unverändert erhalten (AK1).
            self.assertIn("- [ ] F15 Arbeitspakete", text)
            self.assertIn("- [x] V-001 Erledigtes Paket", text)
            self.assertIn("- [ ] V-099 Blockiertes Paket", text)
            self.assertNotIn(assigned, ("F15", "V-001", "V-099"))

    def test_repeated_blank_ids_produce_distinct_sequential_ids(self):
        """F23/AK2: Jeder Aufruf ohne ID verbraucht die nächste freie Nummer
        desselben Auto-Präfixes. IDs wiederholen sich nicht."""
        self.write_tickets(TICKETS)

        first = self.cli.add_ticket("proj", "", "Erstes Auto-Paket")
        prefix, first_number = numbered_id_parts(first)
        second = self.cli.add_ticket("proj", "", "Zweites Auto-Paket")
        suffix, second_number = numbered_id_parts(second)

        self.assertEqual(suffix, prefix)
        self.assertGreater(second_number, first_number)
        text = self.ticket_text()
        self.assertIn("- [ ] %s Erstes Auto-Paket" % first, text)
        self.assertIn("- [ ] %s Zweites Auto-Paket" % second, text)
        self.assertNotEqual(first, second)

    def test_auto_assigned_id_skips_numbers_already_taken(self):
        """F23/AK3: Bestehende Auto-Präfix-Einträge und nutzereingetragene IDs
        desselben Musters erhalten die nächste freie Nummer."""
        self.write_tickets(TICKETS)
        observed = self.cli.add_ticket("proj", "", "Beobachtung")
        prefix, _ = numbered_id_parts(observed)

        # Bestandsnummern mit dem Auto-Präfix und eine Nutzer-ID desselben
        # Musters. Wird der Nutzer-ID-Konflikt nicht beachtet, ergibt der
        # nächste Aufruf eine schon vorhandene ID.
        neighbors = ("2", "40")
        seeds = TICKETS + "\n\n".join(
            "- [ ] %s%s Nachbarnummer %s\n  Beschreibung: Seed %s"
            % (prefix, n, n, n)
            for n in (2, 40)
        ) + "\n\n- [ ] %s1 Ältester Nachbar\n  Beschreibung: Seed 1\n" % prefix
        self.write_tickets(seeds)
        manual = "30"
        self.cli.add_ticket("proj", prefix + "30", "Nutzer-ID", "Manuell")

        assigned = self.cli.add_ticket("proj", "", "Danach", "Auto")
        prefix2, number = numbered_id_parts(assigned)

        self.assertEqual(prefix2, prefix)
        self.assertGreater(number, max(x for x in [int(n) for n in neighbors] + [30]))
        self.assertNotIn(assigned, {"F15", "V-001", "V-099", prefix + "2",
                                     prefix + "1", prefix + "30",
                                     prefix + "40"})
        text = self.ticket_text()
        self.assertIn("- [ ] %s Danach" % assigned, text)

    def test_auto_assignment_without_a_tickets_file_fails_and_creates_nothing(self):
        """F23/AK5: Wiederholungssicherer Fallback — derselbe Fehler wie bei
        manueller ID, keine Datei entsteht."""
        for blank in ("", "  "):
            with self.assertRaisesRegex(ValueError, "Keine TICKETS.md"):
                self.cli.add_ticket("proj", blank, "Titel", "Text")
        self.assertFalse(self.tickets.exists())

    def test_add_work_package_requires_an_existing_tickets_file(self):
        with self.assertRaisesRegex(ValueError, "Keine TICKETS.md"):
            self.cli.add_ticket("proj", "F18", "Titel", "Text")
        self.assertFalse(self.tickets.exists())

    def test_delete_removes_only_the_selected_work_package(self):
        self.write_tickets(TICKETS)

        self.cli.ticket_delete("proj", "F15")

        text = self.ticket_text()
        self.assertNotIn("F15 Arbeitspakete", text)
        self.assertNotIn("Bestehendes Paket", text)
        self.assertIn("V-001 Erledigtes Paket", text)
        self.assertIn("V-099 Blockiertes Paket", text)

    def test_delete_rejects_unknown_id_without_changing_file(self):
        self.write_tickets(TICKETS)
        before = self.ticket_text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.ticket_delete("proj", "F99")

        self.assertEqual(self.ticket_text(), before)

    def test_add_bug_writes_a_bug_marker_and_numbers_separately(self):
        self.write_feedback(FEEDBACK)

        number = self.cli.add_bug("proj", "Absturz beim Start", "Fenster bleibt leer")

        self.assertEqual(number, 1)
        text = self.feedback_text()
        self.assertIn("- [ ] B1 Absturz beim Start", text)
        self.assertIn("  Art: Bug", text)
        self.assertIn("  Beschreibung: Fenster bleibt leer", text)
        self.assertIn("F1 Bestehender Punkt", text)
        bug = {e["id"]: e for e in self.cli.feedback_items("proj")}["B1"]
        self.assertEqual(bug["kind"], "bug")
        self.assertEqual(bug["description"], "Fenster bleibt leer")

    def test_second_bug_gets_the_next_number_and_feedback_keeps_f_numbers(self):
        self.cli.add_bug("proj", "Erster Bug", "A")

        self.assertEqual(self.cli.add_bug("proj", "Zweiter Bug", "B"), 2)
        self.assertEqual(self.cli.add_feedback("proj", "Feedback", "C"), 1)
        text = self.feedback_text()
        self.assertIn("- [ ] B2 Zweiter Bug", text)
        self.assertIn("- [ ] F1 Feedback", text)

    def test_update_bug_keeps_the_bug_marker(self):
        self.write_feedback(FEEDBACK)
        self.cli.add_bug("proj", "Absturz", "Alt")

        self.cli.feedback_update("proj", "B1", "Absturz beim Start", "Neu")

        text = self.feedback_text()
        self.assertIn("- [ ] B1 Absturz beim Start", text)
        self.assertIn("  Art: Bug", text)
        self.assertIn("  Beschreibung: Neu", text)
        bug = {e["id"]: e for e in self.cli.feedback_items("proj")}["B1"]
        self.assertEqual(bug["kind"], "bug")

    def test_regular_feedback_has_kind_feedback(self):
        self.write_feedback(FEEDBACK)

        entry = self.cli.feedback_items("proj")[0]

        self.assertEqual(entry["kind"], "feedback")

    def test_bug_rejects_missing_title_without_writing(self):
        with self.assertRaisesRegex(ValueError, "Titel fehlt"):
            self.cli.add_bug("proj", "  ", "Text")

        self.assertFalse(self.feedback.exists())


class WorkPackageApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        log_dir = cls.root / "_logs"
        log_dir.mkdir()
        (log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
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
        cls.tmp.cleanup()

    def setUp(self):
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")

    def request(self, path, payload=None, token=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        if token:
            req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def ticket_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")


class WorkPackageApiTest(WorkPackageApiFixture):
    def test_project_detail_exposes_editable_work_packages(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual(
            [entry["id"] for entry in detail["tickets"]],
            ["F15", "V-001", "V-099"],
        )
        self.assertEqual(detail["tickets"][0]["title"], "Arbeitspakete")
        self.assertEqual(
            detail["tickets"][0]["description"], "Bestehendes Paket"
        )

    def test_api_adds_updates_and_deletes_a_work_package(self):
        status, body = self.request(
            "/api/ticket",
            {
                "name": "proj",
                "action": "add",
                "id": "F18",
                "title": "Neues Paket",
                "description": "Beschreibung",
            },
        )
        self.assertEqual(status, 200, body)
        self.assertIn("F18 angelegt", body)
        self.assertIn("- [ ] F18 Neues Paket", self.ticket_text())

        status, body = self.request(
            "/api/ticket",
            {
                "name": "proj",
                "action": "update",
                "id": "F18",
                "title": "Geändertes Paket",
                "description": "Geändert",
            },
        )
        self.assertEqual(status, 200, body)
        text = self.ticket_text()
        self.assertIn("- [ ] F18 Geändertes Paket", text)
        self.assertIn("  Beschreibung: Geändert", text)

        status, body = self.request(
            "/api/ticket", {"name": "proj", "action": "delete", "id": "F18"}
        )
        self.assertEqual(status, 200, body)
        text = self.ticket_text()
        self.assertNotIn("F18 Geändertes Paket", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)

    def test_api_adds_work_package_without_an_id_and_names_the_assigned_id(self):
        """F23/AK6: POST /api/ticket action=add ohne id liefert 200 und nennt
        die tatsächlich in TICKETS.md vergebene ID ('<ID> angelegt'); kein
        hartes Präfix im Test."""
        status, body = self.request(
            "/api/ticket",
            {"name": "proj", "action": "add", "title": "Auto Paket",
             "description": "Ohne ID"},
        )
        self.assertEqual(status, 200, body)
        detail = json.loads(
            self.request("/api/project?name=proj")[1]
        )
        assigned_ids = {
            entry["id"] for entry in detail["tickets"]
        } - {"F15", "V-001", "V-099"}
        self.assertEqual(len(assigned_ids), 1)
        assigned = assigned_ids.pop()
        self.assertTrue(assigned)
        self.assertIn("%s angelegt" % assigned, body)
        self.assertIn("- [ ] %s Auto Paket" % assigned, self.ticket_text())
        self.assertIn("  Beschreibung: Ohne ID", self.ticket_text())

    def test_api_rejects_duplicate_invalid_and_unknown_work_packages(self):
        before = self.ticket_text()

        status, body = self.request(
            "/api/ticket",
            {"name": "proj", "action": "add", "id": "F15", "title": "Doppelt"},
        )
        self.assertEqual(status, 400, body)
        self.assertIn("existiert bereits", body)

        status, body = self.request(
            "/api/ticket",
            {"name": "proj", "action": "add", "id": "- [ ] F99", "title": "Neu"},
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Ungültige ID", body)

        status, body = self.request(
            "/api/ticket",
            {"name": "proj", "action": "update", "id": "F99", "title": "Neu"},
        )
        self.assertEqual(status, 400, body)
        self.assertIn("nicht gefunden", body)
        self.assertEqual(self.ticket_text(), before)

    def test_api_rejects_unknown_action_and_missing_id_without_changing_file(self):
        before = self.ticket_text()

        status, body = self.request(
            "/api/ticket", {"name": "proj", "action": "foo", "id": "F15"}
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannte Aktion", body)

        status, body = self.request(
            "/api/ticket", {"name": "proj", "action": "delete", "title": "ohne ID"}
        )
        self.assertEqual(status, 400, body)
        self.assertIn("ID fehlt", body)
        self.assertEqual(self.ticket_text(), before)

    def test_api_reports_a_bug_as_feedback_of_kind_bug(self):
        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "kind": "bug",
                "title": "Absturz beim Start",
                "description": "Fenster bleibt leer",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertIn("B1 eingetragen", body)
        text = self.feedback_text()
        self.assertIn("- [ ] B1 Absturz beim Start", text)
        self.assertIn("  Art: Bug", text)
        self.assertIn("F1 Bestehender Punkt", text)

        status, body = self.request("/api/project?name=proj")
        self.assertEqual(status, 200, body)
        entries = {entry["id"]: entry for entry in json.loads(body)["feedback"]}
        self.assertEqual(entries["B1"]["kind"], "bug")
        self.assertEqual(entries["F1"]["kind"], "feedback")

    def test_detail_page_contains_work_package_and_bug_controls(self):
        html = served_page(self.request)

        self.assertIn("Arbeitspakete (", html)
        self.assertIn("Neues Arbeitspaket", html)
        self.assertIn("Arbeitspaket anlegen", html)
        self.assertIn("Bug melden", html)
        self.assertIn("action:'add'", html)
        self.assertIn("id:'tickets'", html)


if __name__ == "__main__":
    unittest.main()
