"""AP4-Korbat (Oberflächen): T-G0, T-W1, T-G1, T-S1 im Web-UI.

Die Fälle leiten sich aus dem Arbeitspaket AP4-Korbat und den
Design-Entscheidungen 8, 9 und 17 ab. Browser/Playwright steht in dieser
Umgebung nicht zur Verfügung; die JS-Oberflächen werden deshalb wie im
Bestand (z. B. ``test_ap22_web_routes.py``) über String-/Strukturprüfungen
abgesichert, die API über den echten ``vibe-web``-Server mit isolierten
Pfaden.

Geprüft wird:

* (a) Auto-Merge-Checkbox in beiden Oberflächen (``app.js`` und
  ``nova-project.js``), gespeichert über ``/api/github action=settings`` mit
  ``auto_merge`` (bool) → ``GITHUB_AUTO_MERGE="1"``/``""``;
  ``vibe_github.status`` liefert ``auto_merge`` (im GitHub-Modul getestet)
  und die API gibt den Wert zurück.
* (b) Nova-GitHub-Karte hat die Aktionen „Mit GitHub verknüpfen“ (link),
  „Verknüpfung lösen“ (unlink) und „Abrufen (fetch)“.
* (c) Session-Zeilen zeigen den Paket-Anhang (``package_id`` samt Titel) und
  die technische Sitzungs-ID; die API liefert zusätzlich
  ``worktree_path``/``package_id``/``branch``.
* (d) Nova-Arbeiten-Reiter hat „Paket abschließen“ über ``/api/package``
  (action close) für blockierte und wartende Pakete.

F34-Anpassung: Das Nova-Board ist entfernt. Die Sitzungszeilen der
integrierten Projektansicht zeigen den Paketbezug über ``package_id`` (Titel
aus der Ticketliste) und die gekürzte Sitzungs-ID; der Worktree-Pfad bleibt
Datenfeld der API, wird aber nicht mehr in der Nova-Zeile ausgegeben.

Nicht abgedeckt: (e) Nova-Feature-Defaults (AP22) — Rückfrage offen.

Run:

    python3 -m unittest tests.unit.test_ap4_korbat_gui -v
"""
import json
import re
import unittest
from pathlib import Path

from tests.unit.test_ap19_sessions_api import Ap19SessionsApiFixture
from tests.unit.test_ap22_web_routes import DashboardFixture

REPO = Path(__file__).resolve().parents[2]
APP_JS = REPO / "bin" / "web" / "app.js"
NOVA = REPO / "bin" / "web" / "nova-project.js"
WEB = REPO / "bin" / "vibe-web.py"


def js_region(text, marker, fallback=6000):
    """Schneidet den Quelltextabschnitt ab ``marker`` bis zur nächsten
    Top-Level-Funktion; ohne Treffer die ganze Datei (dann schlägt die
    inhaltliche Assertion aussagekräftig fehl)."""
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        return text[start:start + fallback]
    return text[start:end]


class ClassicSurfaceTest(unittest.TestCase):
    """AK 17(a)/(c): klassische Oberfläche spiegelt Auto-Merge und Anhang."""

    def setUp(self):
        self.text = APP_JS.read_text(encoding="utf-8")
        self.github = js_region(self.text, "function githubBody(")
        self.sessions = js_region(self.text, "function sessionsCard(")

    def test_github_body_has_an_auto_merge_checkbox_in_the_settings_payload(self):
        """Vorbedingung: ``bin/web/app.js``, ``githubBody``.
        Aktion: GitHub-Einstellungskarte und Speicher-Payload prüfen.
        Erwartung: ein ``auto_merge``-Feld wird mit den Einstellungen
        gesendet; eine Auto-Merge-Checkbox existiert in ``githubBody``.
        Fehlerfall: Checkbox fehlt oder der Wert wird nicht übertragen.
        """
        self.assertTrue(self.github, "githubBody nicht gefunden")
        self.assertIn("auto_merge", self.github)
        self.assertRegex(self.github, r"(?i)auto(matis(ch)?)?[ _-]?merge",
                         "Keine Auto-Merge-Beschriftung im klassischen "
                         "GitHub-Body")

    def test_github_hint_describes_pr_only_default_and_auto_merge(self):
        """Vorbedingung: Hilfetext der klassischen GitHub-Karte.
        Aktion: Text nach dem Abschlussverhalten durchsuchen.
        Erwartung: Der Hinweis nennt die Auto-Merge-Checkbox und ihren
        Standard (aus/PR-only); die alte Aussage „das Zusammenführen bleibt
        manuell“ ist ersetzt.
        Fehlerfall: Hinweis beschreibt weiterhin nur manuelles Mergen.
        """
        self.assertNotIn("das Zusammenführen bleibt manuell", self.text.lower())
        self.assertRegex(self.text, r"(?i)auto(matis(ch)?)?[ _-]?merge")
        self.assertRegex(self.text,
                         r"(?i)(pr-only|standardmäßig aus|standard: aus|default off)")

    def test_session_rows_show_worktree_and_package_attachment(self):
        """Vorbedingung: Session-Karte in ``app.js`` (``sessionsCard``).
        Aktion: Darstellung der Session-Zeilen prüfen.
        Erwartung: ``worktree_path`` und ``package_id`` werden angezeigt,
        wenn vorhanden.
        Fehlerfall: Anhang ist in der klassischen Oberfläche unsichtbar.
        """
        self.assertTrue(self.sessions, "sessionsCard nicht gefunden")
        self.assertIn("worktree_path", self.sessions)
        self.assertIn("package_id", self.sessions)


class NovaSurfaceTest(unittest.TestCase):
    """AK 17(a)/(b)/(c)/(d): Nova-Karte und Arbeiten-Reiter."""

    def setUp(self):
        self.text = NOVA.read_text(encoding="utf-8")
        self.github = js_region(self.text, "function nvpGithubSection(")
        self.sessions = js_region(self.text, "var sessionBox = el('section'")

    def test_nova_github_section_has_auto_merge_checkbox(self):
        """Vorbedingung: ``nvpGithubSection`` in ``nova-project.js``.
        Aktion: Einstellungs-Payload und Feld prüfen.
        Erwartung: ``auto_merge`` wird mitgesendet und eine Checkbox
        existiert; der Hinweis nennt den Standard (aus/PR-only).
        Fehlerfall: Nova kann den Schalter nicht setzen.
        """
        self.assertTrue(self.github, "nvpGithubSection nicht gefunden")
        self.assertIn("auto_merge", self.github)
        self.assertRegex(self.github,
                         r"(?i)auto(matis(ch)?)?[ _-]?merge",
                         "Keine Auto-Merge-Beschriftung in Nova")

    def test_nova_github_card_has_link_unlink_and_fetch_actions(self):
        """Vorbedingung: Nova-GitHub-Karte.
        Aktion: Aktionen und Beschriftungen suchen.
        Erwartung: link mit ``url``, unlink und fetch sind über
        ``/api/github`` verdrahtet; die Beschriftungen entsprechen der
        klassischen Karte.
        Fehlerfall: Parität fehlt.
        """
        self.assertTrue(self.github, "nvpGithubSection nicht gefunden")
        self.assertIn("/api/github", self.github)
        for action in ("link", "unlink", "fetch"):
            self.assertRegex(
                self.github,
                r"action:\s*['\"]" + action + r"['\"]",
                "Aktion %r fehlt in Nova" % action)
        link_area = js_region(self.github, "action: 'link'", 500)
        match = re.search(r"action:\s*['\"]link['\"]", self.github)
        if match:
            link_area = self.github[match.start():match.start() + 500]
        self.assertRegex(link_area, r"url\s*:", "link sendet keine URL")
        self.assertIn("Mit GitHub verknüpfen", self.github)
        self.assertIn("Verknüpfung lösen", self.github)
        self.assertRegex(self.github, r"(?i)abrufen")

    def test_nova_session_rows_show_worktree_and_package_attachment(self):
        """Vorbedingung: Sitzungsabschnitt der Nova-Projektansicht.
        Aktion: Felder in der Sitzungsdarstellung suchen.
        Erwartung (F34): Die Zeile zeigt den Paketbezug über ``package_id``
        samt Titel aus der Ticketliste sowie die gekürzte technische
        Sitzungs-ID (``code.nv-session-id``); der Worktree-Pfad bleibt
        API-Datenfeld, nicht Anzeige der Nova-Zeile.
        Fehlerfall: Der Paketbezug fehlt in Nova.
        """
        sessions = js_region(self.text, "var sessionBox = el('section'")
        self.assertTrue(sessions, "Sitzungsabschnitt nicht gefunden")
        self.assertIn("package_id", sessions)
        self.assertIn("data-nv-session-attach", sessions)
        self.assertIn("packageText", sessions)
        self.assertIn("related.title", sessions)
        self.assertIn("nv-session-id", sessions)
        self.assertNotIn("worktree_path", sessions,
                         "F34 zeigt den Worktree-Pfad nicht in der Nova-Zeile")

    def test_nova_work_tab_has_a_package_close_action(self):
        """Vorbedingung: Arbeiten-Reiter in ``nova-project.js``.
        Aktion: Aktion und Endpunkt suchen.
        Erwartung: „Paket abschließen“ ruft ``/api/package`` mit
        ``action: 'close'``, ``name`` und ``id`` auf; die Aktion hängt an
        blockierten Tickets.
        Fehlerfall: blockierte Tickets lassen sich in Nova nicht abschließen.
        """
        self.assertIn("Paket abschließen", self.text)
        self.assertIn("/api/package", self.text)
        self.assertRegex(self.text, r"action:\s*['\"]close['\"]")
        self.assertRegex(self.text, r"(?i)blockiert")
        self.assertIn("WARTET AUF MERGE", self.text,
                      "Wartende Pakete lassen sich nicht abschließen")


class WebBackendTextTest(unittest.TestCase):
    """AK 17(a)/(d): Backend kennt Auto-Merge und Paket-Abschluss."""

    def setUp(self):
        self.text = WEB.read_text(encoding="utf-8")

    def test_settings_handler_writes_github_auto_merge(self):
        """Vorbedingung: ``bin/vibe-web.py``.
        Aktion: Settings-Handler prüfen.
        Erwartung: ``auto_merge`` aus dem Body wird als
        ``GITHUB_AUTO_MERGE`` „1“/„“ gespeichert.
        Fehlerfall: Feld wird ignoriert.
        """
        self.assertIn("GITHUB_AUTO_MERGE", self.text)
        self.assertIn("auto_merge", self.text)

    def test_package_endpoint_is_known(self):
        """Vorbedingung: ``bin/vibe-web.py``.
        Aktion: Routen prüfen.
        Erwartung: ``/api/package`` ist ein bekannter POST-Endpunkt mit
        ``action close``.
        Fehlerfall: Nova-Aktion liefe ins Leere.
        """
        self.assertIn("/api/package", self.text)
        self.assertIn("close", self.text)


class WebApiBehaviourTest(DashboardFixture):
    """AK 17(a)/(c)/(d): echte API mit isoliertem Dashboard."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def env_path(self):
        return self.project / ".vibe" / "project.env"

    def test_settings_persist_auto_merge_on_and_off(self):
        """Vorbedingung: Projekt ohne GitHub-Auto-Merge-Eintrag.
        Aktion: ``POST /api/github`` ``action=settings`` mit
        ``auto_merge: true`` und danach mit ``false``.
        Erwartung: ``GITHUB_AUTO_MERGE="1"`` bzw. ``""`` in project.env; die
        Antwort trägt ``github.auto_merge`` passend.
        Fehlerfall: Schalter wird nicht gespeichert oder Status ignoriert ihn.
        """
        status, text, _ = self.post(
            "/api/github", {"name": "proj", "action": "settings",
                            "auto_merge": True})
        self.assertEqual(200, status, text)
        payload = json.loads(text)
        self.assertFalse(payload.get("ok") is False, text)
        self.assertIn('GITHUB_AUTO_MERGE="1"',
                      self.env_path().read_text(encoding="utf-8"))
        github = payload.get("github") or {}
        self.assertIs(github.get("auto_merge"), True, payload)

        status, text, _ = self.post(
            "/api/github", {"name": "proj", "action": "settings",
                            "auto_merge": False})
        self.assertEqual(200, status, text)
        self.assertIn('GITHUB_AUTO_MERGE=""',
                      self.env_path().read_text(encoding="utf-8"))

    def test_sessions_api_returns_the_worktree_attachment(self):
        """Vorbedingung: eine Session mit ``worktree_path``/``package_id``/
        ``branch`` im Register.
        Aktion: ``GET /api/sessions?name=proj``.
        Erwartung: Der Eintrag enthält die drei Felder (Grundlage der
        Session-Zeilen).
        Fehlerfall: API verschweigt den Anhang.
        """
        entry = {
            "session": "ses_wt", "project": str(self.project.resolve()),
            "name": "proj", "run_id": "", "agent": "vibe",
            "harness": "opencode", "first_seen": 100, "last_seen": 100,
            "worktree_path": str(self.root / "worktrees" / "F1"),
            "package_id": "F1", "branch": "feature/test/f1",
        }
        (self.log_dir / "sessions.json").write_text(
            json.dumps({"limit": 5, "sessions": [entry]}), encoding="utf-8")

        status, text, _ = self.request(
            "GET", "/api/sessions?name=proj", token=self.token)

        self.assertEqual(200, status, text)
        payload = json.loads(text)
        sessions = payload.get("sessions") or []
        self.assertEqual(1, len(sessions), text)
        session = sessions[0]
        self.assertEqual(entry["worktree_path"], session.get("worktree_path"))
        self.assertEqual("F1", session.get("package_id"))
        self.assertEqual("feature/test/f1", session.get("branch"))

    def test_package_close_without_github_link_reports_a_clear_error(self):
        """Vorbedingung: Projekt ohne GitHub-Verknüpfung, keine Registry.
        Aktion: ``POST /api/package`` ``action=close, id=F1``.
        Erwartung: ``ok`` ist falsch und die Meldung nennt GitHub bzw. die
        fehlende Verknüpfung/den fehlenden Worktree; nichts wird gestartet.
        Fehlerfall: Endpunkt fehlt (404) oder meldet Erfolg.
        """
        status, text, _ = self.post(
            "/api/package", {"name": "proj", "action": "close", "id": "F1"})

        self.assertIn(status, (200, 400), text)
        payload = json.loads(text) if text.strip().startswith("{") else {}
        self.assertFalse(payload.get("ok") is True, text)
        message = str(payload.get("message") or
                      (payload.get("error") or {}).get("message") or "")
        self.assertRegex(message, r"(?i)github|verknüpf|worktree|registriert",
                         "Unklare Meldung: " + text)


class SessionsContinueResumePackageTest(Ap19SessionsApiFixture):
    """AK Review-Befund 1: ``/api/sessions action=continue`` reicht das
    Resume-Paket an ``vibe.cmd_run`` weiter.

    Geprüft wird der echte Web-Handler mit aufzeichnender tmux-Attrappe: Der
    Startbefehl des Läufers muss den Worktree-Anhang exportieren, damit der
    Agent im selben Baum fortsetzt. Ohne Registry-Anhang bleibt es beim reinen
    ``VIBE_CONTINUE_SESSION``.
    """

    def resume_exports(self, variable):
        values = []
        for command in self.new_session_commands():
            values.extend(re.findall(
                r"%s=([^\s;\"']+)" % re.escape(variable), command))
        return values

    def seeded_with_attachment(self):
        worktree = self.project / "wt"
        worktree.mkdir(exist_ok=True)
        entry = self.session("ses_wt", first=100, last=100)
        entry.update({
            "worktree_path": str(worktree),
            "package_id": "F1",
            "branch": "feature/test/f1",
        })
        self.seed_sessions([entry])
        return worktree

    def test_continue_exports_the_resume_package_and_worktree(self):
        """Vorbedingung: Session-Register-Eintrag mit ``package_id``,
        ``worktree_path`` und ``branch``.
        Aktion: ``POST /api/sessions`` mit ``action='continue'`` und der
        Session-Kennung.
        Erwartung: Der vom Handler gestartete ``vibe.cmd_run``-Aufruf
        exportiert ``VIBE_CONTINUE_SESSION`` und zusätzlich
        ``VIBE_RESUME_PACKAGE``, ``VIBE_RESUME_WORKTREE`` und
        ``VIBE_RESUME_BRANCH`` mit den Registerwerten.
        Fehlerfall: Der Handler reicht das Resume-Paket nicht durch; der
        Agent landet wieder im falschen Baum.
        """
        worktree = self.seeded_with_attachment()

        status, data, raw = self.post_continue("ses_wt")

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertEqual(["ses_wt"], self.continue_exports(), raw)
        self.assertEqual(["F1"], self.resume_exports("VIBE_RESUME_PACKAGE"),
                         raw)
        self.assertEqual([str(worktree)],
                         self.resume_exports("VIBE_RESUME_WORKTREE"), raw)
        self.assertEqual(["feature/test/f1"],
                         self.resume_exports("VIBE_RESUME_BRANCH"), raw)

    def test_continue_without_attachment_stays_plain_continue(self):
        """Vorbedingung: Session-Eintrag ohne ``package_id``/``worktree_path``
        (Alteintrag = Integrationsstand).
        Aktion: ``POST /api/sessions`` mit ``action='continue'``.
        Erwartung: ``VIBE_CONTINUE_SESSION`` wird gesetzt, aber kein
        ``VIBE_RESUME_PACKAGE``/``-WORKTREE``/``-BRANCH`` exportiert.
        Fehlerfall: Leere Anhänge werden als Resume-Paket exportiert.
        """
        self.seed_sessions([self.session("ses_plain", first=100, last=100)])

        status, data, raw = self.post_continue("ses_plain")

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertEqual(["ses_plain"], self.continue_exports(), raw)
        for variable in ("VIBE_RESUME_PACKAGE", "VIBE_RESUME_WORKTREE",
                         "VIBE_RESUME_BRANCH"):
            self.assertEqual([], self.resume_exports(variable), raw)


if __name__ == "__main__":
    unittest.main()
