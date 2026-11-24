"""GH-47: Vertragstests für Issue-Löschen/Sync und Text-Sync (Backend).

Quelle der Ableitung: Arbeitspaket GH-47 (TICKETS.md), ``SPEC.md`` und die
verbindlichen Nutzerentscheidungen q8907138c500b (Löschen -> Issue schließen,
Tombstone bei Fehlschlag), q9a10d0cf6e7f (lokale Textfassung gewinnt bei
Konflikt) und q6cbba05d8ca9 (genau ein Sync).

Geprüft werden ausschließlich beobachtbare Verträge:

* **Tombstone-Sync** (q8907138c500b): Eine Nummer im Dokumentschlüssel
  ``github_deletions`` verhindert die Neuanlage des Issues; der Sync versucht
  das Schließen erneut, entfernt den Eintrag bei Erfolg oder wenn das Issue
  bereits geschlossen/verschwunden ist, und bricht bei einem Fehlschlag nicht
  ab.
* **Bidirektionaler Text-Sync** (q9a10d0cf6e7f): ``gh_text`` hält den zuletzt
  synchronisierten (Titel, Beschreibung)-Stand; lokale Änderungen werden
  gepusht, Remote-Änderungen inklusive Beschreibung gezogen, bei beidseitiger
  Änderung oder fehlender Basislinie mit unterschiedlichen Texten gewinnt die
  lokale Fassung (``conflicts``), done-Tickets bleiben textstabil.
* **Statistik**: exakt ``created``/``updated``/``closed``/``pushed`` plus
  ``text_pushed``/``text_pulled``/``conflicts``/``closed_remote``.
* **Zustands-Fix** (D): ``set_issue_state(..., "open")`` setzt das
  Ready-Label, damit der nächste Pull nicht auf draft zurücksetzt.
* **Laufdisziplin** (D): nur ``open``/``in-progress`` sind wählbar; Drafts
  erscheinen in ``status_report`` als eigener Bucket und in ``priority_view``
  als „Entwurf“.

Kein echtes Netz und kein echtes GitHub: REST ausschließlich gegen den
``ThreadingHTTPServer``-Fake aus ``test_ap3_korbat_issues_backend`` auf
``127.0.0.1``; isolierte VIBE_*/HOME-Pfade, Fake-Token, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_gh47_issues_backend -v
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_packages  # noqa: E402
import vibe_tickets  # noqa: E402

from tests.unit.test_ap3_korbat_issues_backend import (  # noqa: E402
    FakeIssuesServer,
    GithubCase,
    issue,
    ticket_record,
)

STAT_KEYS = {
    "created", "updated", "closed", "pushed",
    "text_pushed", "text_pulled", "conflicts", "closed_remote",
}


class Gh47Case(GithubCase):
    """Isolierte Umgebung mit Fake-REST und Ticketspeicher-Helfern."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer(issues=[]).start()
        self.addCleanup(self.server.close)

    # ---------------------------------------------------------- Speicher
    def config_for(self, project):
        return self.gh.read_config(str(project / ".vibe" / "project.env"))

    def write_document(self, project, tickets, deletions=None):
        document = {"version": 1, "tickets": list(tickets)}
        if deletions is not None:
            document["github_deletions"] = list(deletions)
        path = project / ".vibe" / "tickets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
        return path

    def read_document(self, project):
        return json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))

    def records(self, project):
        return {item["id"]: item for item in self.read_document(project)["tickets"]}

    def deletions(self, project):
        return list(self.read_document(project).get("github_deletions") or [])

    def sync(self, project):
        return vibe_packages_issues_module().sync_issues(
            str(project), self.config_for(project))

    def project(self, name="proj"):
        return self.make_project(name=name, env_text=self.issues_env(self.server))


def vibe_packages_issues_module():
    if "gh47_issues" not in _CACHE:
        from tests.unit.test_ap3_korbat_issues_backend import load_module
        _CACHE["gh47_issues"] = load_module(
            REPO / "bin" / "vibe_issues.py", "vibe_issues_gh47_under_test")
    return _CACHE["gh47_issues"]


_CACHE = {}


class StatsContractTest(Gh47Case):
    """Statistikvertrag: vier bestehende plus vier neue Zähler."""

    def test_sync_statistics_use_the_contract_keys(self):
        """Vor: Remote-Ready-Issue. Aktion: sync.
        Erwartet: genau die acht Vertragsschlüssel, alle ganzzahlig."""
        self.server.httpd.issues[:] = [
            issue(201, "Titel", labels=["ready"], body="Beschreibung")]
        project = self.project()

        stats = self.sync(project)

        self.assertEqual(STAT_KEYS, set(stats), stats)
        for key in STAT_KEYS:
            self.assertIsInstance(stats[key], int, (key, stats))


class TombstoneSyncTest(Gh47Case):
    """q8907138c500b: Tombstones verhindern Wiederbelegung und werden
    nachgearbeitet, ohne den Gesamtsync abzubrechen."""

    def test_failed_close_keeps_tombstone_and_does_not_recreate_the_issue(self):
        """Vor: Remote 101 offen (PATCH scheitert), 102 ready; Tombstone 101.
        Aktion: sync. Erwartet: kein GH-101, GH-102 entsteht, Tombstone bleibt,
        closed_remote 0; der übrige Pull läuft weiter."""
        self.server.httpd.issues[:] = [
            issue(101, "Gelöscht lokal", labels=["ready"], body="x"),
            issue(102, "Neu", labels=["ready"], body="y"),
        ]
        self.server.httpd.fail_patch_numbers.add(101)
        project = self.project()
        self.write_document(project, [], deletions=[101])

        stats = self.sync(project)

        self.assertNotIn("GH-101", self.records(project))
        self.assertIn("GH-102", self.records(project))
        self.assertEqual([101], self.deletions(project))
        self.assertEqual(0, stats["closed_remote"], stats)
        self.assertTrue(self.server.by_path("PATCH", "/issues/101"),
                        self.server.requests)

    def test_successful_retry_closes_the_issue_and_drops_the_tombstone(self):
        """Vor: Remote 101 offen, Tombstone 101. Aktion: sync.
        Erwartet: Issue 101 geschlossen, Tombstone entfernt, kein GH-101,
        closed_remote 1."""
        self.server.httpd.issues[:] = [
            issue(101, "Gelöscht lokal", labels=["ready"], body="x")]
        project = self.project()
        self.write_document(project, [], deletions=[101])

        stats = self.sync(project)

        self.assertEqual("closed", self.server.httpd.issues[0]["state"])
        self.assertEqual([], self.deletions(project))
        self.assertNotIn("GH-101", self.records(project))
        self.assertEqual(1, stats["closed_remote"], stats)

    def test_tombstone_drops_for_already_closed_or_missing_issues(self):
        """Vor: Tombstones 103 (remote geschlossen) und 999 (fehlt).
        Aktion: sync. Erwartet: beide Einträge entfernt, kein Ticket, kein
        Abbruch."""
        self.server.httpd.issues[:] = [
            issue(103, "Bereits zu", state="closed", body="z")]
        project = self.project()
        self.write_document(project, [], deletions=[103, 999])

        self.sync(project)

        self.assertEqual([], self.deletions(project))
        self.assertNotIn("GH-103", self.records(project))


class TextSyncTest(Gh47Case):
    """q9a10d0cf6e7f: bidirektionaler Text-Sync mit lokalem Vorrang."""

    def seed_ready(self, number=201, title="Titel", body="Beschreibung"):
        self.server.httpd.issues[:] = [
            issue(number, title, labels=["ready"], body=body)]

    def test_pull_creation_sets_a_gh_text_baseline(self):
        """Vor: Remote-Ready-Issue 201. Aktion: sync.
        Erwartet: GH-201 trägt ein nichtleeres ``gh_text``."""
        self.seed_ready()
        project = self.project()

        self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertIsInstance(record.get("gh_text"), str, record)
        self.assertTrue(record["gh_text"], record)

    def test_local_text_change_is_pushed_only_once(self):
        """Vor: Baseline nach Pull; danach lokaler Titel/Beschreibung neu.
        Aktion: sync zweimal. Erwartet: PATCH mit lokalem Titel/Body,
        text_pushed 1, gh_text aktualisiert; zweiter Lauf ohne PATCH."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        before_hash = self.records(project)["GH-201"]["gh_text"]
        vibe_tickets.update(str(project), "GH-201",
                            title="Lokal neu", description="Lokaler Body")
        patches_before = len(self.server.by_path("PATCH", "/issues/201"))

        stats = self.sync(project)

        patches = self.server.by_path("PATCH", "/issues/201")
        self.assertEqual(patches_before + 1, len(patches), patches)
        self.assertEqual("Lokal neu", patches[-1]["body"].get("title"))
        self.assertEqual("Lokaler Body", patches[-1]["body"].get("body"))
        self.assertEqual("Lokal neu", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["text_pushed"], stats)
        self.assertEqual(0, stats["conflicts"], stats)
        self.assertNotEqual(before_hash,
                            self.records(project)["GH-201"]["gh_text"])

        again = self.sync(project)
        self.assertEqual(len(patches), len(self.server.by_path("PATCH",
                                                               "/issues/201")))
        self.assertEqual(0, again["text_pushed"], again)

    def test_remote_text_change_is_pulled_including_the_description(self):
        """Vor: Baseline; danach Remote-Titel/-Beschreibung neu, lokal unverändert.
        Aktion: sync. Erwartet: lokaler Titel UND Beschreibung übernommen,
        text_pulled 1, kein PATCH."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        self.server.httpd.issues[0]["title"] = "Remote neu"
        self.server.httpd.issues[0]["body"] = "Remote Body"

        stats = self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertEqual("Remote neu", record["title"])
        self.assertEqual("Remote Body", record["description"])
        self.assertEqual(1, stats["text_pulled"], stats)
        self.assertFalse(self.server.by_path("PATCH", "/issues/201"))

    def test_conflict_keeps_local_text_counts_it_and_continues(self):
        """Vor: Baseline; danach beide Seiten geändert, dazu neues Remote-Issue.
        Aktion: sync. Erwartet: lokale Fassung bleibt und wird gepusht,
        conflicts 1, GH-202 entsteht (Sync bricht nicht ab)."""
        self.seed_ready()
        project = self.project()
        self.sync(project)
        vibe_tickets.update(str(project), "GH-201",
                            title="Lokal gewinnt", description="Lokal Body")
        self.server.httpd.issues[0]["title"] = "Remote anders"
        self.server.httpd.issues[0]["body"] = "Remote anders Body"
        self.server.httpd.issues.append(
            issue(202, "Zweites", labels=["ready"], body="zwei"))

        stats = self.sync(project)

        record = self.records(project)["GH-201"]
        self.assertEqual("Lokal gewinnt", record["title"])
        self.assertEqual("Lokal Body", record["description"])
        self.assertEqual("Lokal gewinnt", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["conflicts"], stats)
        self.assertIn("GH-202", self.records(project))

    def test_missing_baseline_with_different_texts_is_a_conflict(self):
        """Vor: lokales Ticket mit github=203 und abweichendem Text, kein
        gh_text; Remote anders. Aktion: sync.
        Erwartet: lokale Fassung gewinnt und wird gepusht, conflicts 1."""
        self.server.httpd.issues[:] = [
            issue(203, "Remote", labels=["ready"], body="Remote Body")]
        project = self.project()
        self.write_document(project, [
            ticket_record("AP1", "Lokal", github=203,
                          description="Lokaler Body")])

        stats = self.sync(project)

        record = self.records(project)["AP1"]
        self.assertEqual("Lokal", record["title"])
        self.assertEqual("Lokaler Body", record["description"])
        self.assertEqual("Lokal", self.server.httpd.issues[0]["title"])
        self.assertEqual(1, stats["conflicts"], stats)

    def test_missing_baseline_with_equal_texts_adopts_without_push(self):
        """Vor: gleicher Text beidseitig, aber kein gh_text. Aktion: sync.
        Erwartet: gh_text wird gesetzt, kein PATCH/Text-Push, conflicts 0."""
        self.seed_ready()
        project = self.project()
        self.write_document(project, [
            ticket_record("AP1", "Titel", github=201,
                          description="Beschreibung")])

        stats = self.sync(project)

        self.assertFalse(self.server.by_path("PATCH", "/issues/201"))
        self.assertEqual(0, stats["text_pushed"], stats)
        self.assertEqual(0, stats["conflicts"], stats)
        self.assertTrue(self.records(project)["AP1"]["gh_text"])

    def test_done_ticket_text_is_not_synced_in_either_direction(self):
        """Vor: erledigtes GH-202 mit altem Text, Remote geändert; neues
        Ready-Issue. Aktion: sync. Erwartet: GH-202 bleibt textstabil, kein
        PATCH an 202; GH-201 entsteht."""
        self.server.httpd.issues[:] = [
            issue(201, "Neu", labels=["ready"], body="neu"),
            issue(202, "Remote neu", labels=["ready"], body="Remote Body"),
        ]
        project = self.project()
        self.write_document(project, [
            ticket_record("GH-202", "Fertig", state="done", github=202,
                          commit="abcdef1", test="test_gh47",
                          description="Alt")])

        self.sync(project)

        record = self.records(project)["GH-202"]
        self.assertEqual("Fertig", record["title"])
        self.assertEqual("Alt", record["description"])
        self.assertFalse(self.server.by_path("PATCH", "/issues/202"))
        self.assertIn("GH-201", self.records(project))


class StorePreservationTest(Gh47Case):
    """Speicherhaltung für gh_text und Tombstones."""

    def test_gh_text_survives_a_ticket_update(self):
        """Vor: Ticket mit gh_text. Aktion: Titel ändern.
        Erwartet: gh_text bleibt erhalten (normalize bewahrt unbekannte
        Felder)."""
        project = self.make_project()
        vibe_tickets.add(str(project), "Titel", tid="AP1",
                         extra={"gh_text": "abc123"})

        vibe_tickets.update(str(project), "AP1", title="Neuer Titel")

        self.assertEqual("abc123", self.records(project)["AP1"]["gh_text"])

    def test_github_deletions_survives_ticket_writes(self):
        """Vor: Dokument mit github_deletions [7]. Aktion: Ticket ändern und
        neues anlegen. Erwartet: der Dokumentschlüssel bleibt erhalten."""
        project = self.make_project()
        self.write_document(project, [ticket_record("AP1", "Alt")],
                            deletions=[7])

        vibe_tickets.update(str(project), "AP1", title="Neu")
        vibe_tickets.add(str(project), "Zusatz", tid="AP2")

        self.assertEqual([7], self.deletions(project))
        self.assertEqual({"AP1", "AP2"}, set(self.records(project)))


class IssueStateFixTest(Gh47Case):
    """D: open setzt das Ready-Label statt beide Labels zu entfernen."""

    def test_open_state_sets_ready_label_and_survives_the_next_sync(self):
        """Vor: GH-101, Remote trägt in-progress. Aktion: set_issue_state open,
        dann sync. Erwartet: PATCH setzt ready/entfernt in-progress; der Sync
        setzt das Ticket nicht auf draft zurück."""
        self.server.httpd.issues[:] = [
            issue(101, "Offen", labels=["in-progress"], body="x")]
        project = self.project()
        self.write_document(project, [
            ticket_record("GH-101", "Offen", github=101, state="in-progress")])

        issue_module = vibe_packages_issues_module()
        issue_module.set_issue_state(str(project), self.config_for(project),
                                     "GH-101", "open")

        labels = self.server.by_path("PATCH", "/issues/101")[-1]["body"].get(
            "labels") or []
        self.assertIn("ready", labels)
        self.assertNotIn("in-progress", labels)
        self.assertEqual("open", self.records(project)["GH-101"]["state"])

        self.sync(project)
        self.assertEqual("open", self.records(project)["GH-101"]["state"])


class DraftRunDisciplineTest(Gh47Case):
    """D: nur lauffähige Tickets werden gewählt; Drafts sind sichtbar, aber
    nicht startbar."""

    def select(self, project, **kwargs):
        return vibe_packages.select_package(
            project, state_path=str(self.base / "next.json"), **kwargs)

    def test_only_open_and_in_progress_are_eligible(self):
        """Vor: Draft, blocked, waiting-merge, open und in-progress.
        Aktion: select zweimal. Erwartet: erst open, dann in-progress; nie
        draft/blocked/waiting."""
        project = self.make_project()
        self.write_document(project, [
            ticket_record("D1", "Entwurf", state="draft"),
            ticket_record("B1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("W1", "Wartet", state="waiting-merge"),
            ticket_record("T1", "Offen"),
            ticket_record("P1", "Läuft", state="in-progress"),
        ])

        first = self.select(project)
        second = self.select(project, skip={first["id"]})

        self.assertEqual("T1", first["id"])
        self.assertEqual("P1", second["id"])

    def test_order_and_priority_fallbacks_skip_drafts(self):
        """Vor: Draft D1 in PACKAGE_ORDER und mit P0; offenes T2.
        Aktion: select. Erwartet: T2 (beide Ordnungen überspringen den
        Entwurf)."""
        project = self.make_project(
            env_text='TYPE=generic\nPACKAGE_ORDER="D1 T2"\n')
        self.write_document(project, [
            ticket_record("D1", "Entwurf", state="draft", priority="P0"),
            ticket_record("T2", "Offen"),
        ])

        self.assertEqual("T2", self.select(project)["id"])

    def test_connected_pull_maps_missing_ready_label_to_draft(self):
        """Vor: Remote 101 ohne Ready-Label, 102 mit Ready.
        Aktion: sync, dann select. Erwartet: 101 draft, 102 open; nur GH-102
        ist wählbar."""
        self.server.httpd.issues[:] = [
            issue(101, "Ohne Ready", labels=[], body="a"),
            issue(102, "Mit Ready", labels=["ready"], body="b"),
        ]
        project = self.project()

        self.sync(project)

        records = self.records(project)
        self.assertEqual("draft", records["GH-101"]["state"])
        self.assertEqual("open", records["GH-102"]["state"])
        self.assertEqual("GH-102", self.select(project)["id"])


if __name__ == "__main__":
    unittest.main()
