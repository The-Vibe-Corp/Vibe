"""GH-47: Vertragstests für Web-API, CLI und Oberflächenstruktur.

Quelle der Ableitung: Arbeitspaket GH-47 (TICKETS.md), ``SPEC.md`` und die
verbindlichen Nutzerentscheidungen:

* q6cbba05d8ca9: genau EIN Sync; ``issues``/``issues-import`` entfallen in
  Web-API, CLI, Nova und Classic, der Label-Filter der Issues-Sektion ebenfalls.
* q8907138c500b: Löschen schließt ein verbundenes Issue best effort; bei
  REST-Fehlschlag bleibt das lokale Löschen bestehen und die Issue-Nummer wird
  als Tombstone (``github_deletions``) vermerkt. done-Tickets bleiben vor
  jedem REST-Versuch geschützt.
* Zustandssteuerung im Ticket-Detail: ``draft``/``open``/``in-progress``
  lokal bzw. verbunden über ``action=state``.

Geprüft wird ausschließlich beobachtbares Verhalten: HTTP-Antworten des echten
Dashboards gegen den Loopback-Fake, CLI-Ausgaben/Exit-Codes, gespeicherte
Dokumente und JS-Struktur. Kein echtes Netz, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_gh47_surfaces -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
NOVA = REPO / "bin" / "web" / "nova-project.js"
CLASSIC = REPO / "bin" / "web" / "app.js"
BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from tests.unit.test_ap3_korbat_issues_backend import (  # noqa: E402
    FAKE_TOKEN,
    FakeIssuesServer,
    ISOLATED_ENV,
    issue,
    ticket_record,
)
from tests.unit.test_ap3_korbat_surfaces import (  # noqa: E402
    IssuesWebFixture,
    js_region,
)

STAT_KEYS = {
    "created", "updated", "closed", "pushed",
    "text_pushed", "text_pulled", "conflicts", "closed_remote",
}


class Gh47WebCase(IssuesWebFixture):
    """Dashboard-Fixture mit Dokumentzugriff und Feedback-POST."""

    def write_document(self, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        path = self.project / ".vibe" / "tickets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
        return path

    def read_document(self):
        return json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))

    def deletions(self):
        return list(self.read_document().get("github_deletions") or [])

    def feedback(self, body):
        status, text, _headers = self.post(
            "/api/feedback", dict({"name": "proj"}, **body))
        return status, json.loads(text)

    def patches(self, suffix=None):
        calls = self.server.calls("PATCH")
        if suffix is None:
            return calls
        return [call for call in calls
                if call["path"].rstrip("/").endswith(suffix)]


class LegacyGithubActionsRemovedTest(Gh47WebCase):
    """q6cbba05d8ca9: die getrennten Aktionen sind aus der Web-API entfernt."""

    def test_action_issues_is_unknown_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``/api/github action=issues``.
        Erwartet: ok false, Meldung „Unbekannte Aktion“, kein REST-Aufruf."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "issues"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertRegex(str(data.get("message") or ""), r"(?i)unbekannt")
        self.assertEqual([], self.server.requests)

    def test_action_import_is_unknown_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``/api/github action=import``.
        Erwartet: ok false, Meldung „Unbekannte Aktion“, kein REST-Aufruf."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "import"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertRegex(str(data.get("message") or ""), r"(?i)unbekannt")
        self.assertEqual([], self.server.requests)

    def test_issues_sync_and_state_remain_available(self):
        """Vor: Issues-Sync aktiv, Remote 101. Aktion: ``issues.sync``.
        Erwartet: ok, GH-101 entsteht; die Sync-Aktion bleibt erreichbar."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([])

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("GH-101", self.tickets())


class ConnectedDeleteApiTest(Gh47WebCase):
    """q8907138c500b: verbundenes Löschen über /api/ticket und /api/feedback."""

    def test_delete_without_github_reference_is_local_only(self):
        """Vor: Issues-Sync aktiv, AP1 ohne GitHub-Bezug.
        Aktion: ``/api/ticket delete``. Erwartet: ok, Ticket weg, kein PATCH,
        keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("AP1", "Nur lokal")])

        status, data = self.ticket({"action": "delete", "id": "AP1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("AP1", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertEqual([], self.deletions())

    def test_successful_close_deletes_locally_and_names_the_issue(self):
        """Vor: GH-101 mit github=101. Aktion: ``/api/ticket delete``.
        Erwartet: ok, Ticket weg, PATCH state=closed, Meldung nennt #101 und
        „geschlossen“, keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("GH-101", "Verknüpft", github=101)])

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("GH-101", self.tickets())
        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        patches = self.patches("/issues/101")
        self.assertEqual(1, len(patches), patches)
        self.assertEqual("closed", patches[0]["body"].get("state"))
        message = str(data.get("message") or "")
        self.assertIn("101", message, data)
        self.assertRegex(message, r"(?i)geschlossen")
        self.assertEqual([], self.deletions())

    def test_failed_close_deletes_locally_and_records_a_tombstone(self):
        """Vor: GH-101, PATCH scheitert mit 403. Aktion: delete.
        Erwartet: ok nicht false, Ticket weg, 101 in ``github_deletions``,
        Meldung nennt Fehlschlag + erneuten Sync-Versuch, kein Token."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("GH-101", "Verknüpft", github=101)])
        self.server.httpd.fail_patch_numbers.add(101)

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertIsNot(data.get("ok"), False, data)
        self.assertNotIn("GH-101", self.tickets())
        self.assertEqual([101], self.deletions())
        message = str(data.get("message") or "")
        self.assertRegex(message, r"(?i)fehl|konnte nicht|nicht geschlossen",
                         data)
        self.assertIn("erneut", message.lower(), data)
        self.assertNotIn(FAKE_TOKEN, message, data)

    def test_failed_close_tombstones_are_deduplicated(self):
        """Vor: GH-101 und AP1 zeigen auf Issue 101; PATCH scheitert.
        Aktion: beide löschen. Erwartet: ``github_deletions`` enthält 101
        genau einmal."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Verknüpft", github=101),
            ticket_record("AP1", "Zweiter Bezug", github=101),
        ])
        self.server.httpd.fail_patch_numbers.add(101)

        self.ticket({"action": "delete", "id": "GH-101"})
        self.ticket({"action": "delete", "id": "AP1"})

        self.assertEqual([101], self.deletions())
        self.assertNotIn("GH-101", self.tickets())
        self.assertNotIn("AP1", self.tickets())

    def test_done_ticket_is_refused_before_any_rest_call(self):
        """Vor: erledigtes GH-101 mit GitHub-Bezug. Aktion: delete.
        Erwartet: ok false, Nachweis-Meldung, Ticket bleibt, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Fertig", state="done", github=101,
                          commit="abcdef1", test="test_gh47")])

        status, data = self.ticket({"action": "delete", "id": "GH-101"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertIn("GH-101", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertRegex(str(data.get("message") or ""), r"(?i)erledigt|nachweis")

    def test_feedback_delete_uses_the_connected_path(self):
        """Vor: Bug B1 mit github=101. Aktion: ``/api/feedback delete``.
        Erwartet: Issue geschlossen, B1 lokal weg, PATCH state=closed."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "delete", "id": "B1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("B1", self.tickets())
        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        self.assertEqual(1, len(self.patches("/issues/101")))

    def test_feedback_delete_without_issue_sync_stays_local(self):
        """Vor: Issues-Sync aus, B1 mit github=101. Aktion: feedback delete.
        Erwartet: lokal gelöscht, kein PATCH, keine Tombstone-Nummer."""
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "delete", "id": "B1"})

        self.assertIn(status, (200, 400), data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("B1", self.tickets())
        self.assertEqual([], self.server.calls("PATCH"))
        self.assertEqual([], self.deletions())


class TicketStateApiTest(Gh47WebCase):
    """D: Zustandssteuerung über /api/ticket und /api/feedback."""

    def test_state_without_issue_sync_is_local_only(self):
        """Vor: Issues-Sync aus, AP1 offen. Aktion: state=draft.
        Erwartet: lokal draft, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets([ticket_record("AP1", "Offen")])

        status, data = self.ticket({"action": "state", "id": "AP1",
                                    "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["AP1"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))

    def test_state_with_github_reference_patches_labels_and_local_state(self):
        """Vor: Issues-Sync aktiv, GH-101. Aktion: state draft, dann open.
        Erwartet: draft entfernt Ready/In-Progress lokal+remote; open setzt
        Ready (GH-47-Fix) und lokal offen."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [
            {"name": "ready"}, {"name": "in-progress"}]
        self.write_tickets([
            ticket_record("GH-101", "Offen", github=101,
                          state="in-progress")])

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "draft"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Ticket")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "open"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Ticket")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

    def test_state_with_issue_sync_but_no_github_reference_stays_local(self):
        """Vor: Issues-Sync aktiv, AP1 ohne GitHub-Bezug. Aktion:
        state=in-progress. Erwartet: ok, lokal in-progress, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([ticket_record("AP1", "Offen")])

        status, data = self.ticket({"action": "state", "id": "AP1",
                                    "state": "in-progress"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("in-progress", self.tickets()["AP1"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))

    def test_feedback_state_with_github_reference_patches_labels(self):
        """Vor: Issues-Sync aktiv, B1 mit github=101. Aktion: feedback state
        draft. Erwartet: PATCH entfernt Ready/In-Progress, B1 lokal draft."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"}]
        self.write_tickets([
            ticket_record("B1", "Bug", type="bug", github=101)])

        status, data = self.feedback({"action": "state", "id": "B1",
                                      "state": "draft"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertEqual("draft", self.tickets()["B1"]["state"])
        self.assertTrue(self.patches("/issues/101"),
                        "Kein Label-PATCH für das verbundene Feedback")
        labels = self.patches("/issues/101")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)

    def test_done_ticket_state_is_refused_without_rest(self):
        """Vor: erledigtes GH-101. Aktion: state=open.
        Erwartet: ok false, Zustand bleibt done, kein PATCH."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets([
            ticket_record("GH-101", "Fertig", state="done", github=101,
                          commit="abcdef1", test="test_gh47")])

        status, data = self.ticket({"action": "state", "id": "GH-101",
                                    "state": "open"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertEqual("done", self.tickets()["GH-101"]["state"])
        self.assertEqual([], self.server.calls("PATCH"))


class SyncMessageTest(Gh47WebCase):
    """q9a10d0cf6e7f: Statistik und Web-Meldung nennen die neuen Anteile."""

    def test_conflict_is_reported_in_message_and_statistics(self):
        """Vor: Baseline für GH-201, danach beide Seiten geändert.
        Aktion: issues.sync. Erwartet: Meldung nennt Konflikt; Statistik hat
        die acht Vertragsschlüssel mit conflicts=1; lokale Fassung bleibt."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[:] = [
            issue(201, "Titel", labels=["ready"], body="Beschreibung")]
        self.write_tickets([])
        first = self.github({"action": "issues.sync"})
        self.assertTrue(first[1].get("ok"), first)

        import vibe_tickets
        vibe_tickets.update(str(self.project), "GH-201",
                            title="Lokal gewinnt", description="Lokal Body")
        self.server.httpd.issues[0]["title"] = "Remote anders"
        self.server.httpd.issues[0]["body"] = "Remote anders Body"

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("GH-201", self.tickets())
        self.assertEqual("Lokal gewinnt", self.tickets()["GH-201"]["title"])
        message = str(data.get("message") or "")
        self.assertRegex(message, r"(?i)konflikt", data)
        stats = data.get("stats") or {}
        self.assertEqual(STAT_KEYS, set(stats), data)
        self.assertEqual(1, stats.get("conflicts"), data)


class IssuesCliCase(unittest.TestCase):
    """CLI mit isolierten Pfaden und Loopback-REST-Fake."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "vibe"
        self.home = self.base / "home"
        self.state = self.base / "state"
        self.project = self.root / "proj"
        for path in (self.home, self.state, self.project / ".vibe"):
            path.mkdir(parents=True, exist_ok=True)
        self.server = FakeIssuesServer(issues=[]).start()
        self.addCleanup(self.server.close)

    def write_env(self, **values):
        base = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": self.server.base,
        }
        base.update(values)
        (self.project / ".vibe" / "project.env").write_text(
            "".join('%s="%s"\n' % (key, value)
                    for key, value in base.items()),
            encoding="utf-8")

    def write_document(self, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_document(self):
        return json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))

    def tickets(self):
        return {item["id"]: item
                for item in self.read_document()["tickets"]}

    def run_cli(self, *argv):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV and not key.startswith("GIT_")}
        env.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_STATE": str(self.state),
            "GITHUB_TOKEN": FAKE_TOKEN,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        return subprocess.run(
            [sys.executable, str(CLI), "github", "proj", *argv],
            cwd=str(self.base), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=False)


class CliLegacyActionsTest(IssuesCliCase):
    """q6cbba05d8ca9: ``issues``/``issues-import`` sind aus der CLI entfernt."""

    def test_cli_issues_is_removed_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``vibe github proj issues``.
        Erwartet: Exit != 0, verständliche „unbekannt“-Meldung, kein REST."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_document([])

        result = self.run_cli("issues")

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output, r"(?i)unbekannt|aktion")
        self.assertEqual([], self.server.requests)

    def test_cli_issues_import_is_removed_without_network(self):
        """Vor: Issues-Sync aktiv. Aktion: ``issues-import``.
        Erwartet: Exit != 0, „unbekannt“-Meldung, kein REST."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_document([])

        result = self.run_cli("issues-import")

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output, r"(?i)unbekannt|aktion")
        self.assertEqual([], self.server.requests)

    def test_usage_no_longer_offers_issues_or_import(self):
        """Vor: ``bin/vibe``. Aktion: Quelltext/Docstring prüfen.
        Erwartet: ``issues-import`` kommt nicht mehr vor; ``issues-sync`` und
        ``issues-state`` bleiben dokumentiert."""
        source = CLI.read_text(encoding="utf-8")

        self.assertNotIn("issues-import", source)
        self.assertIn("issues-sync", source)
        self.assertIn("issues-state", source)


class CliSyncMessageTest(IssuesCliCase):
    """q9a10d0cf6e7f: CLI-Meldung nennt Text- und Konfliktanteile."""

    def test_sync_output_mentions_text_upload_and_conflicts(self):
        """Vor: zwei Baseline-Tickets; danach lokale Textänderung (201) und
        beidseitige Änderung (202). Aktion: issues-sync.
        Erwartet: Exit 0; Ausgabe nennt Text/hochgeladen und Konflikt."""
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[:] = [
            issue(201, "Titel A", labels=["ready"], body="Body A"),
            issue(202, "Titel B", labels=["ready"], body="Body B"),
        ]
        self.write_document([])
        first = self.run_cli("issues-sync")
        self.assertEqual(0, first.returncode,
                         first.stdout + first.stderr)
        self.assertEqual({"GH-201", "GH-202"}, set(self.tickets()))

        import vibe_tickets
        vibe_tickets.update(str(self.project), "GH-201",
                            title="Lokal A", description="Lokal A Body")
        vibe_tickets.update(str(self.project), "GH-202",
                            title="Lokal B", description="Lokal B Body")
        self.server.httpd.issues[1]["title"] = "Remote B"
        self.server.httpd.issues[1]["body"] = "Remote B Body"

        second = self.run_cli("issues-sync")

        output = (second.stdout + second.stderr).lower()
        self.assertEqual(0, second.returncode, output)
        self.assertIn("text", output)
        self.assertIn("hochgeladen", output)
        self.assertIn("konflikt", output)


class SurfaceStructureTest(unittest.TestCase):
    """q6cbba05d8ca9: genau ein Sync, keine Laden/Import/Filtreste."""

    @classmethod
    def setUpClass(cls):
        cls.nova = NOVA.read_text(encoding="utf-8")
        cls.classic = CLASSIC.read_text(encoding="utf-8")

    def test_nova_issues_section_has_exactly_one_sync_and_no_legacy(self):
        """Vor: ``nvpGithubSection``. Aktion: Aktionen/Felder prüfen.
        Erwartet: genau ein ``issues-sync``, kein ``github-issues``/
        ``github-import``, kein ``github-issue-label``; Erklärung nennt
        Synchronisieren, Ready/Entwurf und Schließen."""
        region = js_region(self.nova, "function nvpGithubSection(")
        self.assertTrue(region, "nvpGithubSection nicht gefunden")
        self.assertEqual(1, region.count("issues-sync"), region)
        self.assertNotIn("'github-issues'", region)
        self.assertNotIn("'github-import'", region)
        self.assertNotIn("github-issue-label", region)
        self.assertRegex(region, r"(?i)synchronisier")
        self.assertRegex(region, r"(?i)ready")
        self.assertRegex(region, r"(?i)entwurf|draft")
        self.assertRegex(region, r"(?i)schließ|schliess|close")

    def test_classic_issues_section_drops_load_import_and_filter(self):
        """Vor: ``app.js``. Aktion: Issues-Bedienung prüfen.
        Erwartet: kein ``action:'issues'``/``action:'import'``, keine Buttons
        „Issues laden“/„Issues importieren“, kein ``issueFilter``; ein
        Sync-Button mit ``issues.sync``."""
        self.assertNotIn("Issues laden", self.classic)
        self.assertNotIn("Issues importieren", self.classic)
        self.assertNotIn("issueFilter", self.classic)
        self.assertNotRegex(self.classic, r"action\s*:\s*'issues'")
        self.assertNotRegex(self.classic, r"action\s*:\s*'import'")
        self.assertIn("Issues synchronisieren", self.classic)
        self.assertRegex(self.classic, r"action\s*:\s*['\"]issues\.sync['\"]")

    def test_product_import_helpers_are_removed(self):
        """Vor: Produktmodule. Aktion: Attribute prüfen.
        Erwartet: ``vibe_github.import_issues_into_tickets`` fehlt,
        ``list_issues`` bleibt; ``bin/vibe`` hat keine Legacy-Liste/Import."""
        import vibe_github

        self.assertFalse(hasattr(vibe_github, "import_issues_into_tickets"))
        self.assertTrue(callable(getattr(vibe_github, "list_issues", None)))
        source = CLI.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?m)^def github_issues\(")
        self.assertNotRegex(source, r"(?m)^def github_issues_import\(")


if __name__ == "__main__":
    unittest.main()
