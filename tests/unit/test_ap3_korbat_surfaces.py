"""AP3-Korbat (Web-API, CLI, Nova-Oberflaeche): unabhaengige Abnahmetests.

Quellen: Arbeitspaket AP3-Korbat, ``SPEC.md`` und die verbindlichen
Design-Entscheidungen 9-11. Browser/Playwright steht in dieser Umgebung nicht
zur Verfuegung; die Nova-Oberflaeche wird deshalb wie AP4/AP2 ueber
Strukturpruefungen des JS-Quelltexts abgesichert.

Abgedeckt:

* ``/api/github action=settings`` persistiert die neuen Schluessel
  ``issues_enabled``/``issues_in_progress``/``issues_assignee`` in
  ``GITHUB_ISSUES_ENABLED``/``GITHUB_ISSUES_IN_PROGRESS``/
  ``GITHUB_ISSUES_ASSIGNEE`` und liefert sie im Status.
* ``/api/github action=issues.sync`` verweigert ohne Opt-in ohne Netzaufruf
  und liefert bei aktivem Sync die Statistik ``created/updated/closed/pushed``.
* ``/api/github action=issues.state`` setzt/entfernt das In-Progress-Label per
  PATCH und spiegelt die lokale ``Status:``-Zeile.
* ``/api/ticket action=add`` legt im verbundenen Projekt zuerst das Issue an
  (Kategorie ``bug``/``feature`` -> Label) und schreibt ``GH-<n>`` plus
  ``GitHub: #<n>``; ein Fehlschlag hinterlaesst keinen halben Eintrag; ohne
  Opt-in bleibt die lokale AP-ID-Vergabe unveraendert.
* CLI ``vibe github <projekt> issues-sync`` / ``issues-state <id>
  in-progress|open``: gleiches Verhalten, ohne Opt-in klare Meldung und kein
  Netz.
* Nova: integrierte Liste ohne Board, Karten mit ``data-nv-kind``/
  ``data-nv-state`` und Zustands-Pille (In Progress gelb, Entwurf grau,
  Entwurf-Kachel mit ``title``-Erklärung), Kartenaktionen im Kontext-Panel,
  Sync-Button ``issues-sync``, Kategorieauswahl ``category`` im Ticketformular
  sowie Issues-Felder in der GitHub-Karte.

F34-Anpassung: Das Kanban-Board ist entfernt (F34 Leitentscheidung 7). Die
Nova-Fälle prüfen deshalb die integrierte Liste (``data-nv-ticket-list``), die
Karten-Hooks, die Zustands-Pillen und die Aktionen im Kontext-Panel statt der
alten ``nvpStateColumn``/``nvpBoardColumn``-Struktur. Board-Hooks dürfen nicht
mehr existieren.

Kein echtes Netz: REST nur gegen den Loopback-Fake aus
``test_ap3_korbat_issues_backend``. Der Webserver laeuft auf einem freien
Loopback-Port mit isolierten VIBE_*/HOME-Pfaden.

Run:

    python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_ap22_web_routes import DashboardFixture
from tests.unit.test_ap3_korbat_issues_backend import (
    FAKE_TOKEN,
    FakeIssuesServer,
    stats_dict,
)

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
NOVA = REPO / "bin" / "web" / "nova-project.js"
WAITING_AP3 = "WARTET AUF MERGE"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
)


def js_region(text, marker, fallback=8000):
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


def entry_block(text, ident):
    entry = re.compile(r"^- \[[^\]]*\] ")
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if entry.match(line) and line[6:].split(" ", 1)[0] == ident:
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if entry.match(lines[index]):
            end = index
            break
    return "\n".join(lines[start:end])


# ----------------------------------------------------------- Web-API-Fixture
class IssuesWebFixture(DashboardFixture):
    """Dashboard-Fixture mit Fake-GitHub und GitHub-Token in der Umgebung."""

    @classmethod
    def setUpClass(cls):
        previous = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN
        try:
            cls.start_server()
        finally:
            if previous is None:
                os.environ.pop("GITHUB_TOKEN", None)
            else:
                os.environ["GITHUB_TOKEN"] = previous

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer().start()
        self.addCleanup(self.server.close)
        self.write_tickets("# TICKETS\n\n")

    def write_env(self, **values):
        base = {
            "TYPE": "generic",
            "GITHUB_ENABLED": "1",
            "GITHUB_REPO": "owner/name",
            "GITHUB_API": self.server.base,
        }
        base.update(values)
        text = "".join('%s="%s"\n' % (key, value)
                       for key, value in base.items())
        (self.project / ".vibe" / "project.env").write_text(text,
                                                           encoding="utf-8")

    def write_tickets(self, text):
        (self.project / "TICKETS.md").write_text(text, encoding="utf-8")

    def tickets(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def github(self, body):
        status, text, _headers = self.post(
            "/api/github", dict({"name": "proj"}, **body))
        return status, json.loads(text)

    def ticket(self, body):
        status, text, _headers = self.post(
            "/api/ticket", dict({"name": "proj"}, **body))
        return status, json.loads(text)


# ------------------------------------------------------------- Web-API-Faelle
class IssuesSettingsApiTest(IssuesWebFixture):
    """AK Design 1/2/11: Einstellungen der neuen Issues-Karte."""

    def test_settings_persist_issues_options_and_status(self):
        """Vorbedingung: verbundenes Projekt mit aktivem Issues-Sync.
        Aktion: ``/api/github action=settings`` mit ``issues_enabled``,
        ``issues_in_progress`` und ``issues_assignee``.
        Erwartung: 200; ``project.env`` traegt
        ``GITHUB_ISSUES_ENABLED="1"``, ``GITHUB_ISSUES_IN_PROGRESS``,
        ``GITHUB_ISSUES_ASSIGNEE``; der Status liefert die Werte.
        Fehlerfall: Schluessel werden verworfen oder nicht gespeichert.
        """
        self.write_env()

        status, data = self.github({
            "action": "settings",
            "issues_enabled": True,
            "issues_in_progress": "triaged",
            "issues_ready": "freigegeben",
            "issues_assignee": "alice",
        })

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn('GITHUB_ISSUES_ENABLED="1"', env_text)
        self.assertIn('GITHUB_ISSUES_IN_PROGRESS="triaged"', env_text)
        self.assertIn('GITHUB_ISSUES_READY="freigegeben"', env_text)
        self.assertIn('GITHUB_ISSUES_ASSIGNEE="alice"', env_text)
        view = data.get("github") or {}
        self.assertIs(view.get("issues_enabled"), True, data)
        self.assertEqual("triaged", view.get("issues_in_progress_label"), data)
        self.assertEqual("freigegeben", view.get("issues_ready_label"), data)
        self.assertEqual("alice", view.get("issues_assignee"), data)

    def test_settings_can_turn_the_issue_sync_off_again(self):
        """Vorbedingung: Issues-Sync ist aktiv.
        Aktion: ``settings`` mit ``issues_enabled: false``.
        Erwartung: ``GITHUB_ISSUES_ENABLED=""``; Status meldet aus.
        Fehlerfall: Der Schalter laesst sich nicht zuruecksetzen.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.github({"action": "settings",
                                    "issues_enabled": False})

        self.assertEqual(200, status, data)
        env_text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn('GITHUB_ISSUES_ENABLED=""', env_text)
        self.assertIs((data.get("github") or {}).get("issues_enabled"), False,
                      data)


class IssuesSyncApiTest(IssuesWebFixture):
    """AK Design 4/6/10: Sync ueber die Web-API."""

    def test_sync_without_opt_in_is_refused_without_network(self):
        """Vorbedingung: GitHub verknuepft, aber ``GITHUB_ISSUES_ENABLED``
        fehlt.
        Aktion: ``/api/github action=issues.sync``.
        Erwartung: ``ok:false`` mit verstaendlicher Meldung; der Fake erhaelt
        keinen einzigen Aufruf; TICKETS.md bleibt unveraendert.
        Fehlerfall: Netzaufruf oder stilles Anlegen lokaler Eintraege.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")
        before = self.tickets()

        status, data = self.github({"action": "issues.sync"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        message = str(data.get("message") or "").lower()
        self.assertTrue(any(word in message for word in
                            ("issue", "sync", "nicht aktiv", "deaktiviert")),
                        data)
        self.assertEqual([], self.server.requests)
        self.assertEqual(before, self.tickets())

    def test_sync_returns_statistics_and_updates_tickets(self):
        """Vorbedingung: Issues-Sync aktiv; Remote hat Issue 101, lokal wartet
        AP1.
        Aktion: ``issues.sync``.
        Erwartung: 200; Statistik ``created``/``updated``/``closed``/
        ``pushed``; TICKETS.md enthaelt GH-101 und einen GitHub-Verweis am
        lokalen AP1.
        Fehlerfall: keine Statistik, kein Pull oder kein Push.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets("# TICKETS\n\n- [ ] AP1 Local task\n"
                           "  Beschreibung: Do it\n")

        status, data = self.github({"action": "issues.sync"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        stats = stats_dict(data)
        for key in ("created", "updated", "closed", "pushed"):
            self.assertIn(key, stats, data)
        text = self.tickets()
        self.assertIn("- [ ] GH-101 Remote open", text)
        self.assertRegex(entry_block(text, "AP1"), r"GitHub: #\d+")

    def test_state_action_sets_and_removes_the_in_progress_label(self):
        """Vorbedingung: lokaler Block GH-101, Issues-Sync aktiv.
        Aktion: ``issues.state`` mit ``in-progress`` und danach ``open``.
        Erwartung: PATCH setzt/entfernt das Label; die lokale
        ``Status: in-progress``-Zeile erscheint und verschwindet wieder.
        Fehlerfall: Label und lokaler Zustand laufen auseinander.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets("# TICKETS\n\n- [ ] GH-101 Remote open\n"
                           "  Beschreibung: Open body\n"
                           "  GitHub: #101\n")

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "in-progress"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        block = entry_block(self.tickets(), "GH-101")
        self.assertIn("Status: in-progress", block)
        patches = self.server.calls("PATCH")
        self.assertEqual(1, len(patches), patches)
        self.assertIn("in-progress",
                      patches[0]["body"].get("labels") or [], patches)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "open"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotIn("Status: in-progress",
                         entry_block(self.tickets(), "GH-101"))
        patches = self.server.calls("PATCH")
        self.assertEqual(2, len(patches), patches)
        self.assertNotIn("in-progress",
                         patches[1]["body"].get("labels") or [], patches)

    def test_state_action_supports_draft_and_ready(self):
        """Vorbedingung: Remote-Issue 101 traegt ``ready`` und
        ``in-progress``; lokal steht ``Status: in-progress``.
        Aktion: ``issues.state`` nacheinander mit ``draft``, ``ready`` und
        ``in-progress``.
        Erwartung: draft entfernt Ready- und In-Progress-Label, ready setzt
        Ready und entfernt In-Progress, in-progress setzt In-Progress und
        laesst Ready stehen; die lokale Statuszeile folgt sofort.
        Fehlerfall: Labels/Statuszeile laufen auseinander oder Ready geht
        verloren.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"},
                                                 {"name": "in-progress"}]
        self.write_tickets("# TICKETS\n\n- [ ] GH-101 Remote open\n"
                           "  GitHub: #101\n"
                           "  Status: in-progress\n")

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "draft"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("Status: draft", entry_block(self.tickets(), "GH-101"))
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "ready"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertNotRegex(entry_block(self.tickets(), "GH-101"),
                            r"(?m)^\s+Status:")
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        status, data = self.github({"action": "issues.state", "id": "GH-101",
                                    "state": "in-progress"})
        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("Status: in-progress",
                      entry_block(self.tickets(), "GH-101"))
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("in-progress", labels)
        self.assertIn("ready", labels)


class TicketAddApiTest(IssuesWebFixture):
    """AK Design 9: Ticket-Anlage im verbundenen und lokalen Projekt."""

    def test_bug_category_creates_issue_and_github_block(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``category="bug"``.
        Erwartung: Issue wird mit Label ``bug`` angelegt; TICKETS.md enthaelt
        ``GH-<n>``, ``GitHub: #<n>`` und ``Art: Bug``.
        Fehlerfall: lokale AP-ID statt GH-Block oder fehlendes Label.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web bug", "description": "kaputt",
            "category": "bug"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        text = self.tickets()
        self.assertRegex(text, r"(?m)^- \[ \] GH-\d+ Web bug", text)
        block = entry_block(text, re.search(r"GH-\d+", text).group(0))
        self.assertIn("Art: Bug", block)
        self.assertRegex(block, r"GitHub: #\d+")
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(1, len(posts), posts)
        self.assertIn("bug", posts[0]["body"].get("labels") or [], posts)

    def test_feature_category_uses_the_feature_label(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``category="feature"``.
        Erwartung: Issue mit Label ``feature``; lokaler Block ohne ``Art: Bug``.
        Fehlerfall: Feature wird als Bug markiert oder ohne Label angelegt.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web feature", "description": "neu",
            "category": "feature"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        text = self.tickets()
        self.assertRegex(text, r"(?m)^- \[ \] GH-\d+ Web feature", text)
        post = self.server.by_path("POST", "/issues")[0]
        self.assertIn("feature", post["body"].get("labels") or [], post)
        ident = re.search(r"GH-\d+", text).group(0)
        self.assertNotIn("Art: Bug", entry_block(text, ident))

    def test_ticket_add_defaults_to_draft_in_connected_projects(self):
        """Vorbedingung: Issues-Sync aktiv, kein ``draft``-Feld im Request.
        Aktion: ``/api/ticket action=add`` mit Kategorie ``bug``.
        Erwartung: Das Issue wird OHNE Ready-Label angelegt; der lokale Block
        traegt ``Status: draft``.
        Fehlerfall: Neue Tickets sind sofort arbeitbar, obwohl Entwurf der
        Standard ist.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web draft", "description": "entwurf",
            "category": "bug"})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        text = self.tickets()
        self.assertRegex(text, r"(?m)^- \[ \] GH-\d+ Web draft", text)
        ident = re.search(r"GH-\d+", text).group(0)
        self.assertIn("Status: draft", entry_block(text, ident))
        post = self.server.by_path("POST", "/issues")[0]
        self.assertNotIn("ready", post["body"].get("labels") or [], post)

    def test_ticket_add_with_draft_false_creates_a_ready_issue(self):
        """Vorbedingung: Issues-Sync aktiv.
        Aktion: ``/api/ticket action=add`` mit ``draft:false``.
        Erwartung: Das Issue traegt das Ready-Label; der lokale Block hat
        keine Statuszeile.
        Fehlerfall: Die ausdrueckliche Freigabe wird ignoriert.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")

        status, data = self.ticket({
            "action": "add", "title": "Web ready", "description": "frei",
            "draft": False})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        text = self.tickets()
        self.assertRegex(text, r"(?m)^- \[ \] GH-\d+ Web ready", text)
        ident = re.search(r"GH-\d+", text).group(0)
        self.assertNotRegex(entry_block(text, ident), r"(?m)^\s+Status:")
        post = self.server.by_path("POST", "/issues")[0]
        self.assertIn("ready", post["body"].get("labels") or [], post)

    def test_failed_issue_creation_leaves_no_local_entry(self):
        """Vorbedingung: Issues-Sync aktiv, der Fake lehnt die Anlage ab.
        Aktion: ``/api/ticket action=add`` mit Kategorie ``bug``.
        Erwartung: ``ok:false``; TICKETS.md bleibt leer (kein GH- und kein
        AP-Block).
        Fehlerfall: halbfertiger lokaler Eintrag trotz GitHub-Fehler.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.fail_create = True
        before = self.tickets()

        status, data = self.ticket({
            "action": "add", "title": "Web bug", "description": "kaputt",
            "category": "bug"})

        self.assertIn(status, (200, 400), data)
        self.assertIs(data.get("ok"), False, data)
        self.assertTrue(str(data.get("message") or "").strip(), data)
        self.assertEqual(before, self.tickets())

    def test_without_issue_sync_the_local_auto_id_is_kept(self):
        """Vorbedingung: GitHub verknuepft, Issues-Sync aus.
        Aktion: ``/api/ticket action=add`` mit ``draft:true``.
        Erwartung: lokaler ``AP1``-Block ohne Statuszeile; kein REST-Aufruf;
        das Draft-Feld bleibt wirkungslos.
        Fehlerfall: Opt-out erzwingt GitHub-Issues oder eine Draft-Markierung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")

        status, data = self.ticket({
            "action": "add", "title": "Nur lokal", "description": "Text",
            "draft": True})

        self.assertEqual(200, status, data)
        self.assertTrue(data.get("ok"), data)
        text = self.tickets()
        self.assertIn("- [ ] AP1 Nur lokal", text)
        self.assertNotRegex(text, r"GH-\d+")
        self.assertNotIn("Status: draft", entry_block(text, "AP1"))
        self.assertEqual([], self.server.calls("POST"))


# --------------------------------------------------------------- CLI-Faelle
class IssuesCliTest(unittest.TestCase):
    """AK Design 10: CLI-Aktionen mit isolierter Umgebung und Fake-REST."""

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
        self.server = FakeIssuesServer().start()
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

    def write_tickets(self, text):
        (self.project / "TICKETS.md").write_text(text, encoding="utf-8")

    def tickets(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

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

    def test_issues_sync_without_opt_in_makes_no_request(self):
        """Vorbedingung: GitHub verknuepft, Issues-Sync aus.
        Aktion: ``vibe github proj issues-sync``.
        Erwartung: Exit ungleich 0 mit klarer Meldung; kein REST-Aufruf;
        TICKETS.md unveraendert.
        Fehlerfall: stiller Netzaufruf oder Erfolgsmeldung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="")
        self.write_tickets("# TICKETS\n\n")
        before = self.tickets()

        result = self.run_cli("issues-sync")

        output = (result.stdout + result.stderr).lower()
        self.assertNotEqual(0, result.returncode, output)
        self.assertTrue(any(word in output for word in
                            ("issue", "sync", "nicht aktiv", "deaktiviert")),
                        output)
        self.assertEqual([], self.server.requests)
        self.assertEqual(before, self.tickets())

    def test_issues_sync_pulls_a_remote_issue(self):
        """Vorbedingung: Issues-Sync aktiv, Remote hat Issue 101.
        Aktion: ``vibe github proj issues-sync``.
        Erwartung: Exit 0; TICKETS.md enthaelt GH-101.
        Fehlerfall: Befehl unbekannt oder ohne Wirkung.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets("# TICKETS\n\n")

        result = self.run_cli("issues-sync")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("GH-101", self.tickets())

    def test_issues_state_sets_and_removes_the_local_status_line(self):
        """Vorbedingung: lokaler Block GH-101, Issues-Sync aktiv.
        Aktion: ``issues-state GH-101 in-progress`` und danach ``open``.
        Erwartung: Status-Zeile erscheint/verschwindet; PATCH-Aufrufe tragen
        bzw. entfernen das Label.
        Fehlerfall: CLI-Aktion fehlt oder Statuszeile bleibt stehen.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.write_tickets("# TICKETS\n\n- [ ] GH-101 Remote open\n"
                           "  GitHub: #101\n")

        first = self.run_cli("issues-state", "GH-101", "in-progress")
        first_out = first.stdout + first.stderr
        self.assertEqual(0, first.returncode, first_out)
        self.assertIn("Status: in-progress",
                      entry_block(self.tickets(), "GH-101"))

        second = self.run_cli("issues-state", "GH-101", "open")
        second_out = second.stdout + second.stderr
        self.assertEqual(0, second.returncode, second_out)
        self.assertNotIn("Status: in-progress",
                         entry_block(self.tickets(), "GH-101"))
        self.assertGreaterEqual(len(self.server.calls("PATCH")), 2)

    def test_issues_state_supports_draft_and_ready(self):
        """Vorbedingung: Remote-Issue 101 traegt ``ready`` und
        ``in-progress``; lokaler Block GH-101.
        Aktion: ``issues-state GH-101 draft``, ``... ready`` und
        ``... in-progress``.
        Erwartung: Exit 0 je Aktion; lokale Statuszeile draft -> keine ->
        in-progress; PATCH-Labels wie in Design 19.
        Fehlerfall: CLI kennt die neuen Zustaende nicht oder synchronisiert
        die Statuszeile nicht.
        """
        self.write_env(GITHUB_ISSUES_ENABLED="1")
        self.server.httpd.issues[0]["labels"] = [{"name": "ready"},
                                                 {"name": "in-progress"}]
        self.write_tickets("# TICKETS\n\n- [ ] GH-101 Remote open\n"
                           "  GitHub: #101\n")

        draft = self.run_cli("issues-state", "GH-101", "draft")
        self.assertEqual(0, draft.returncode, draft.stdout + draft.stderr)
        self.assertIn("Status: draft", entry_block(self.tickets(), "GH-101"))
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertNotIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        ready = self.run_cli("issues-state", "GH-101", "ready")
        self.assertEqual(0, ready.returncode, ready.stdout + ready.stderr)
        self.assertNotRegex(entry_block(self.tickets(), "GH-101"),
                            r"(?m)^\s+Status:")
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)

        progress = self.run_cli("issues-state", "GH-101", "in-progress")
        self.assertEqual(0, progress.returncode,
                         progress.stdout + progress.stderr)
        self.assertIn("Status: in-progress",
                      entry_block(self.tickets(), "GH-101"))
        labels = self.server.calls("PATCH")[-1]["body"].get("labels") or []
        self.assertIn("in-progress", labels)
        self.assertIn("ready", labels)


# --------------------------------------------------------- Nova-Oberflaeche
class NovaIssuesSurfaceTest(unittest.TestCase):
    """AK Design 11: Struktur der Nova-Oberflaeche (kein Browser noetig)."""

    @classmethod
    def setUpClass(cls):
        cls.text = NOVA.read_text(encoding="utf-8")

    def test_state_helpers_know_in_progress(self):
        """Vorbedingung: ``nova-project.js`` mit Zustandshelfer und Karte.
        Aktion: ``nvpStateLabel`` und die Zustands-Pille der Karte pruefen.
        Erwartung (F34): Ein In-Progress-Zustand wird mit „In Progress“
        beschriftet und als gelbe Pille (``nv-warn``) an der Karte dargestellt;
        die fruehere Board-Spaltenabbildung existiert nicht mehr.
        Fehlerfall: In Progress faellt auf „offen“ zurueck.
        """
        label = js_region(self.text, "function nvpStateLabel(")
        card = js_region(self.text, "function nvpTicketCard(")
        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertRegex(label, r"(?i)in[ _-]?progress")
        self.assertIn("data-nv-state", card)
        self.assertRegex(card, r"(?i)in[ _-]?progress")
        self.assertRegex(card, r"nv-warn")
        self.assertNotIn("nvpStateColumn", self.text,
                         "Die entfernte Board-Spaltenabbildung existiert noch")

    def test_work_list_and_tiles_include_progress_without_board(self):
        """Vorbedingung: Uebersichtskacheln und Arbeit-Reiter.
        Aktion: Kacheldefinitionen, integrierte Liste und Board-Abwesenheit
        pruefen.
        Erwartung (F34): Die Uebersicht zaehlt In-Progress-Pakete; die Arbeit
        ist eine Liste ``div.nv-ticket-list[data-nv-ticket-list]`` mit
        ``nvpTicketCard``-Karten; ein Board (``.nv-board``/``nvpBoardColumn``)
        existiert nicht.
        Fehlerfall: Zustand ist nur im Parser, nicht in der Oberflaeche, oder
        das entfernte Board ist noch vorhanden.
        """
        overview = js_region(self.text, "var tiles = el('div'")
        work = js_region(self.text, "var ticketList = el('div'")
        self.assertTrue(overview, "Uebersichts-Kacheln nicht gefunden")
        self.assertIn("nvpCount(tickets", overview)
        self.assertRegex(overview, r"(?i)progress")
        self.assertTrue(work, "Integrierte Arbeitsliste nicht gefunden")
        self.assertIn("data-nv-ticket-list", work)
        self.assertIn("nvpTicketCard", work)
        self.assertIn("allItems.forEach", work)
        self.assertNotIn(".nv-board", self.text,
                         "Das entfernte Board existiert noch")
        self.assertNotIn("nvpBoardColumn", self.text,
                         "Die entfernte Board-Spalte existiert noch")

    def test_github_card_has_sync_button_and_issues_fields(self):
        """Vorbedingung: ``nvpGithubSection``.
        Aktion: Aktionen und Formularfelder pruefen.
        Erwartung: ``data-nv-action`` ``issues-sync``; Schalter
        ``github-issues-enabled``; Felder fuer In-Progress-Label und Assignee,
        die ueber ``settings`` mit ``issues_enabled``/``issues_in_progress``/
        ``issues_assignee`` gespeichert werden.
        Fehlerfall: Sync nicht ausloesbar oder Einstellungen nicht speicherbar.
        """
        region = js_region(self.text, "function nvpGithubSection(")
        self.assertTrue(region, "nvpGithubSection nicht gefunden")
        self.assertIn("issues-sync", region)
        self.assertIn("github-issues-enabled", region)
        self.assertRegex(region, r"(?i)in[ _-]?progress")
        self.assertRegex(region, r"(?i)assignee")
        self.assertIn("issues_enabled", region)
        self.assertIn("issues_in_progress", region)
        self.assertIn("issues_ready", region)
        self.assertIn("issues_assignee", region)

    def test_cards_show_draft_state_with_gray_pill_and_explanation(self):
        """Vorbedingung: ``nova-project.js``.
        Aktion: Zustandshelfer, Karten-Pille und Entwurf-Kachel pruefen.
        Erwartung (F34): Draft/Entwurf wird mit „Entwurf“ beschriftet, an der
        Karte als graue Pille ``nv-muted`` dargestellt und in der Uebersicht
        als Kachel mit ``title``-Erklaerung gefuehrt; ein Board gibt es nicht.
        Fehlerfall: Entwurf erscheint als offen oder ohne Kennzeichnung.
        """
        label = js_region(self.text, "function nvpStateLabel(")
        card = js_region(self.text, "function nvpTicketCard(")
        overview = js_region(self.text, "var tiles = el('div'")
        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertTrue(overview, "Uebersichts-Kacheln nicht gefunden")
        self.assertRegex(label, r"(?i)draft|entwurf")
        self.assertRegex(card, r"(?i)draft|entwurf")
        self.assertRegex(card, r"nv-muted")
        self.assertIn("data-nv-state", card)
        self.assertRegex(
            overview,
            r"\[\s*'draft'\s*,\s*nvpCount\(tickets\s*,\s*'Draft'\)")
        self.assertIn("Noch nicht freigegebene Pakete", overview)
        self.assertIn("title: tile[3]", overview,
                      "Die Entwurf-Kachel traegt keine title-Erklaerung")
        self.assertNotIn(".nv-board", self.text,
                         "Das entfernte Board existiert noch")

    def test_ticket_cards_are_generic_and_actions_live_in_the_detail_panel(self):
        """Vorbedingung: ``nvpTicketCard``/``nvpOpenTicketDetail``.
        Aktion: Karten-Hooks und Aktionen im Kontext-Panel pruefen.
        Erwartung (F34): Eine Karte bedient alle Typen (``data-nv-kind``,
        ``data-nv-state``, Paket- oder Feedback-Hook) und oeffnet das
        Kontext-Panel; dort liegen Bearbeiten/Loeschen sowie „Paket
        abschliessen“ fuer blockierte/wartende Pakete. Die frueheren
        Board-Issueaktionen (``issues-state``) sind mit dem Board entfallen;
        die Issue-Zustands-API bleibt in den Backend-Faellen geprueft.
        Fehlerfall: Kartenaktionen sind nicht erreichbar oder der
        Abschluss-Knopf erscheint fuer Feedback.
        """
        card = js_region(self.text, "function nvpTicketCard(")
        detail = js_region(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertTrue(detail, "nvpOpenTicketDetail nicht gefunden")
        self.assertIn("data-nv-kind", card)
        self.assertIn("data-nv-state", card)
        self.assertIn("data-nv-ticket", card)
        self.assertIn("data-nv-feedback-item", card)
        self.assertIn("nvpOpenTicketDetail", card)
        self.assertIn("ticket-edit", detail)
        self.assertIn("ticket-delete", detail)
        self.assertIn("package-close", detail)
        self.assertRegex(detail, r"kind\s*===\s*'package'")
        self.assertIn("BLOCKIERT", detail)
        self.assertIn(WAITING_AP3, detail)
        self.assertNotIn("issues-state", self.text,
                         "Board-Issueaktionen gehoeren nicht mehr zur "
                         "integrierten Liste")

    def test_ticket_form_has_draft_checkbox(self):
        """Vorbedingung: ``nvpOpenTicketForm``.
        Aktion: Formularfelder und Save-Payload pruefen.
        Erwartung: Checkbox ``data-nv-field="draft"`` mit Vorgabe gesetzt und
        ``draft`` im Request-Body.
        Fehlerfall: Entwurf ist beim Anlegen nicht waehlbar.
        """
        form = js_region(self.text, "function nvpOpenTicketForm(")
        self.assertTrue(form, "nvpOpenTicketForm nicht gefunden")
        self.assertIn("draft", form)
        self.assertRegex(form, r"(?i)checked")
        self.assertRegex(form, r"data-nv-field[^\n]*draft|draft[^\n]*data-nv-field")

    def test_in_progress_pill_uses_warn_class_and_draft_stays_muted(self):
        """Vorbedingung: ``nvpTicketCard`` mit Zustands-Pille.
        Aktion: Klassenzuweisung der Pille pruefen.
        Erwartung: ``In Progress`` erhaelt ``nv-warn`` (gelb) wie
        ``WARTET AUF MERGE``; ``Draft`` erhaelt weiterhin ``nv-muted``.
        Fehlerfall: In Progress faellt auf das neutrale Pillen-Grau zurueck.
        """
        card = js_region(self.text, "function nvpTicketCard(")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        warn_lines = [line for line in card.splitlines() if "nv-warn" in line]
        self.assertTrue(warn_lines, card)
        self.assertTrue(any("In Progress" in line for line in warn_lines),
                        "In Progress erhaelt kein nv-warn: " + repr(warn_lines))
        muted_lines = [line for line in card.splitlines()
                       if "nv-muted" in line]
        self.assertTrue(any("Draft" in line for line in muted_lines),
                        "Draft erhaelt kein nv-muted: " + repr(muted_lines))

    def test_legacy_gh_package_cards_keep_the_package_close_action(self):
        """Vorbedingung: Paketkarte mit ID ``GH-<n>`` ohne
        ``GitHub: #n``-Zeile (Legacy-Import) im Zustand BLOCKIERT/WARTET.
        Aktion: Gate der Kartenaktionen im Kontext-Panel pruefen.
        Erwartung (F34): Der Abschluss haengt nicht an einem GitHub-Verweis,
        sondern an ``kind === 'package'`` und dem Zustand; Legacy-GH-Bloecke
        erhalten „Paket abschliessen“ damit weiterhin. Board-Issueaktionen
        entfallen mit dem Board.
        Fehlerfall: Legacy-GH-Bloecke lassen sich nicht abschliessen, weil die
        GitHub-Referenz fehlt.
        """
        detail = js_region(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(detail, "nvpOpenTicketDetail nicht gefunden")
        self.assertIn("package-close", detail)
        self.assertRegex(detail, r"kind\s*===\s*'package'")
        self.assertRegex(detail, r"row\.state\s*===\s*'BLOCKIERT'")
        self.assertIn(WAITING_AP3, detail)
        self.assertNotIn("row.github", detail,
                         "Die Paketaktion haengt noch an einer GitHub-Referenz")
        self.assertNotIn("issues-state", self.text,
                         "Board-Issueaktionen gehoeren nicht mehr zur "
                         "integrierten Liste")

    def test_ticket_form_offers_bug_and_feature_categories(self):
        """Vorbedingung: ``nvpOpenTicketForm`` und der Arbeiten-Reiter.
        Aktion: Kategorieauswahl und Verbindungskontext pruefen.
        Erwartung: Ein Feld ``data-nv-field`` ``category`` mit den Optionen
        Bug und Feature; der Arbeitsbereich kennt ``issues_enabled`` fuer die
        Sichtbarkeit.
        Fehlerfall: Kategorien sind im verbundenen Projekt nicht waehlbar.
        """
        form = js_region(self.text, "function nvpOpenTicketForm(")
        # F33 WP3: der alte /* ---- Work ---- */-Kommentar wurde durch die
        # Arbeit-Sektion ersetzt; issues_enabled steht jetzt am Board-Aufbau.
        work = js_region(self.text, "var issuesEnabled = !!(data.github")
        self.assertTrue(form, "nvpOpenTicketForm nicht gefunden")
        self.assertIn("category", form)
        self.assertRegex(form, r"(?i)bug")
        self.assertRegex(form, r"(?i)feature")
        self.assertTrue(work, "Arbeitsbereich nicht gefunden")
        self.assertIn("issues_enabled", work)


if __name__ == "__main__":
    unittest.main()
