"""GH-48: Vertragstests für den Läufer auf dem Ticketspeicher.

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` (Git & work-package
closing, Qualität und Abnahme) und der verbindliche Implementierungsvertrag
GH-48 (§4 ``bin/vibe_packages.py``). Geprüft werden:

* ``select_package``: Kandidaten, übersprungene Zustände, PACKAGE_ORDER vor
  Standardordnung (Priorität, Speicherposition), Abhängigkeiten, ``prefer``.
* ``gate_errors``: ``TICKET-<ID>.json`` (vorhanden, lesbar, done, Commit im
  Repository, Test nicht leer), Already-Integrated, unveränderte docs/review/
  Sauberkeitsprüfungen.
* ``sync_ticket``: Übernahme von state/commit/test/pr_url, Räumung der
  Blockier-/Wartefelder, ``require_commit=False``.
* ``mark_blocked``/``mark_waiting_merge``/``status_report``.
* ``priority_view``/``normalize_order``.
* ``copy_work_notes`` (nur AGENTS.md), ``transport_ticket``,
  ``copy-notes --id``, ``is_work_note_path`` und ``ensure_project_exclude``.

Alle Repositories, Arbeitskopien und Speicher liegen in ``tempfile``-Pfaden;
es gibt keine Modellaufrufe, keine Netzzugriffe und keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_gh48_runner_tickets -v
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "bin" / "vibe_packages.py"
STAMP = "2026-01-01T00:00:00+00:00"

_CACHE = {}


def load_module():
    if "packages" not in _CACHE:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_packages_gh48_under_test", str(MODULE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHE["packages"] = module
    return _CACHE["packages"]


def requires(module, name):
    """Liefert die Vertragsfunktion oder scheitert mit klarem GH-48-Befund."""
    function = getattr(module, name, None)
    if function is None:
        raise AssertionError(
            "vibe_packages." + name + " fehlt (Vertrag GH-48).")
    return function


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class RunnerCase(unittest.TestCase):
    """Echtes Git-Projekt; Ticketspeicher je Fall nach Bedarf."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        self.env_path = self.project / ".vibe" / "project.env"
        self.env_path.write_text("TYPE=generic\n", encoding="utf-8")
        (self.project / "AGENTS.md").write_text("# Regeln\n", encoding="utf-8")
        support.commit_all(self.project)
        self.module = load_module()
        self.base = self.head(self.project)
        self.worktrees = []

    def tearDown(self):
        for worktree in self.worktrees:
            support.git(self.project, "worktree", "remove", "--force",
                        str(worktree))

    # ------------------------------------------------------------- fixtures
    def head(self, cwd):
        return support.git(cwd, "rev-parse", "HEAD").stdout.strip()

    def git_ok(self, cwd, *args):
        result = support.git(cwd, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def add_worktree(self, name="wt"):
        worktree = self.root / name
        self.git_ok(self.project, "worktree", "add", "-q", "-b",
                    "feature/test/" + name, str(worktree), "HEAD")
        self.worktrees.append(worktree)
        return worktree

    def store(self, *records):
        return support.write_ticket_store(self.project, list(records))

    def read_store(self):
        path = self.project / ".vibe" / "tickets.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def records(self):
        return {item["id"]: item for item in self.read_store()["tickets"]}

    def write_ticket_file(self, worktree, record):
        path = worktree / ("TICKET-" + record["id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        return path

    def set_order(self, value):
        self.env_path.write_text("TYPE=generic\nPACKAGE_ORDER=\"%s\"\n" % value,
                                 encoding="utf-8")

    def select(self, **kwargs):
        kwargs.setdefault("state_path", str(self.root / "next-package.json"))
        return requires(self.module, "select_package")(self.project, **kwargs)

    def prepare_package(self, worktree, pid="AP7", state="done", commit=None,
                        test="test_ap7", docs=True, review="PASS"):
        """Vollständiger Paketstand in der Arbeitskopie."""
        (worktree / ("impl-" + pid + ".txt")).write_text(pid + "\n",
                                                         encoding="utf-8")
        if docs:
            (worktree / "docs" / "features").mkdir(parents=True, exist_ok=True)
            (worktree / "docs" / "features" / (pid + ".md")).write_text(
                "# " + pid + "\n", encoding="utf-8")
        if review is not None:
            (worktree / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
            (worktree / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
                "# Review\n\nVerdict: " + review + "\n", encoding="utf-8")
        self.git_ok(worktree, "add", "-A")
        self.git_ok(worktree, "commit", "-q", "-m", pid + ": Umsetzung")
        revision = self.head(worktree)
        record = ticket(pid, "Titel", state=state,
                        commit=revision if commit is None else commit,
                        test=test)
        self.write_ticket_file(worktree, record)
        return revision


class SelectPackageTest(RunnerCase):
    """Kandidaten, Ordnung, Abhängigkeiten und Reattach."""

    def test_open_and_in_progress_are_candidates_in_store_order(self):
        """Vor: AP1 offen, AP2 in-progress. Aktion: select_package.
        Erwartet: AP1 (Speicherposition), danach mit skip AP1 -> AP2;
        Zeilenform enthält id, type, title, description, priority, ordered,
        github."""
        self.store(ticket("AP1", "Offen"), ticket("AP2", "Läuft",
                                                 state="in-progress"))

        first = self.select()
        self.assertEqual("AP1", first["id"])
        for key in ("id", "type", "title", "description", "priority",
                    "ordered", "github"):
            self.assertIn(key, first)
        self.assertEqual("task", first["type"])
        self.assertEqual("Offen", first["title"])
        self.assertIs(False, first["ordered"])

        self.assertEqual("AP2", self.select(skip={"AP1"})["id"])

    def test_draft_blocked_waiting_and_done_are_never_selected(self):
        """Vor: nur draft/blocked/waiting-merge/done. Aktion: select_package.
        Erwartet: None — Entwürfe und Nachweise starten nicht."""
        self.store(
            ticket("AP1", "Entwurf", state="draft"),
            ticket("AP2", "Blockiert", state="blocked",
                   blocked_reason="Grund"),
            ticket("AP3", "Wartet", state="waiting-merge",
                   waiting_note="PR"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
        )

        self.assertIsNone(self.select())

    def test_package_order_wins_over_priority_and_position(self):
        """Vor: PACKAGE_ORDER="AP2 AP1"; AP1 hat P0, AP2 P1.
        Aktion: select_package. Erwartet: AP2 zuerst mit ordered=True."""
        self.set_order("AP2 AP1")
        self.store(ticket("AP1", "Wichtig", priority="P0"),
                   ticket("AP2", "Zweit", priority="P1"))

        selected = self.select()

        self.assertEqual("AP2", selected["id"])
        self.assertIs(True, selected["ordered"])
        self.assertEqual("P1", selected["priority"])

    def test_standard_order_is_priority_then_store_position(self):
        """Vor: B1 (Bug) zuerst im Speicher, danach AP1 P1, AP2 P0, AP3 ohne
        Priorität. Aktion: select_package (mit skip).
        Erwartet: AP2 -> AP1 -> B1 -> AP3. Die alte Trennung TICKETS vor
        FEEDBACK entfällt; bei gleicher Priorität zählt nur die
        Speicherposition (kein Typ-Tiebreaker)."""
        self.store(ticket("B1", "Bug zuerst", type="bug"),
                   ticket("AP1", "Eins", priority="P1"),
                   ticket("AP2", "Zwei", priority="P0"),
                   ticket("AP3", "Drei"))

        order = []
        skip = set()
        while True:
            selected = self.select(skip=skip)
            if selected is None:
                break
            order.append(selected["id"])
            skip.add(selected["id"])

        self.assertEqual(["AP2", "AP1", "B1", "AP3"], order)

    def test_a_known_dependency_must_be_done(self):
        """Vor: AP2 hängt von AP1 ab; AP1 offen, danach erledigt.
        Aktion: select_package. Erwartet: zuerst nur AP1 wählbar; nach
        Abschluss von AP1 wird AP2 gewählt. Unbekannte Abhängigkeiten
        blockieren nicht."""
        self.store(ticket("AP1", "Basis"),
                   ticket("AP2", "Abhängig", dependencies=["AP1"]))
        self.assertEqual("AP1", self.select()["id"])

        stored = self.read_store()
        for item in stored["tickets"]:
            if item["id"] == "AP1":
                item.update(state="done", commit="abcdef1", test="test_ap1")
        support.write_ticket_store(self.project, stored["tickets"])
        self.assertEqual("AP2", self.select()["id"])

        support.write_ticket_store(self.project, [
            ticket("AP3", "Fremd", dependencies=["X9"])])
        self.assertEqual("AP3", self.select()["id"])

    def test_prefer_reattaches_even_a_blocked_package(self):
        """Vor: AP1 offen, AP2 blockiert. Aktion: select_package(prefer=AP2).
        Erwartet: AP2 wird vorrangig gewählt (Nutzer-Intention Reattach);
        ein unbekanntes prefer wird ignoriert."""
        self.store(ticket("AP1", "Offen"),
                   ticket("AP2", "Blockiert", state="blocked",
                          blocked_reason="Grund"))

        self.assertEqual("AP2", self.select(prefer="AP2")["id"])
        self.assertEqual("AP1", self.select(prefer="X9")["id"])


class GateTest(RunnerCase):
    """Abschlussschranke auf ``TICKET-<ID>.json``."""

    def gate(self, worktree, pid="AP7"):
        return requires(self.module, "gate_errors")(worktree, pid, self.base)

    def test_complete_package_passes_without_findings(self):
        """Vor: Commit mit Paketpräfix, docs/features, Review PASS, saubere
        Arbeitskopie und TICKET-Datei mit state done/commit/test.
        Aktion: gate_errors. Erwartet: []."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)

        self.assertEqual([], self.gate(worktree))

    def test_missing_ticket_file_is_a_finding(self):
        """Vor: vollständiger Paketstand, aber keine TICKET-AP7.json.
        Aktion: gate_errors. Erwartet: Befund nennt die Datei."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "TICKET-AP7.json").unlink()

        errors = self.gate(worktree)

        self.assertTrue(any("TICKET-AP7.json" in error for error in errors),
                        errors)

    def test_unreadable_ticket_file_is_a_finding(self):
        """Vor: TICKET-Datei mit defektem JSON. Aktion: gate_errors.
        Erwartet: Befund nennt die Datei und die Lesbarkeit."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "TICKET-AP7.json").write_text("{", encoding="utf-8")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("TICKET-AP7.json", text)
        self.assertIn("lesbar", text.lower())

    def test_state_must_be_done(self):
        """Vor: TICKET-Datei mit state=in-progress. Aktion: gate_errors.
        Erwartet: Befund nennt state und done."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        revision = self.head(worktree)
        self.write_ticket_file(worktree, ticket(
            "AP7", "Titel", state="in-progress", commit=revision,
            test="test_ap7"))

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("state", text)
        self.assertIn("done", text)

    def test_commit_must_exist_in_the_repository(self):
        """Vor: TICKET-Datei nennt einen unbekannten Commit. Aktion:
        gate_errors. Erwartet: Befund nennt commit und Repository."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, commit="deadbee")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("commit", text.lower())
        self.assertIn("deadbee", text)

    def test_test_field_must_not_be_empty(self):
        """Vor: TICKET-Datei mit leerem test-Feld. Aktion: gate_errors.
        Erwartet: Befund nennt test."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, test="")

        errors = self.gate(worktree)

        self.assertTrue(any("test" in error.lower() for error in errors),
                        errors)

    def test_already_integrated_package_passes_without_new_commits(self):
        """Vor: Paketcommit liegt bereits als Vorfahre der Basis vor, die
        TICKET-Datei nennt ihn; kein neuer Commit seit der Basis.
        Aktion: gate_errors. Erwartet: kein Befund (Already-Integrated-Regel)."""
        (self.project / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (self.project / "docs" / "features" / "AP7.md").write_text(
            "# AP7\n", encoding="utf-8")
        (self.project / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (self.project / "docs" / "reviews" / "AP7-review-1.md").write_text(
            "# Review\n\nVerdict: PASS\n", encoding="utf-8")
        (self.project / "impl-AP7.txt").write_text("x\n", encoding="utf-8")
        self.git_ok(self.project, "add", "-A")
        self.git_ok(self.project, "commit", "-q", "-m", "AP7: Umsetzung")
        revision = self.head(self.project)
        self.base = revision
        self.write_ticket_file(self.project, ticket(
            "AP7", "Titel", state="done", commit=revision,
            test="test_ap7"))

        self.assertEqual([], self.gate(self.project))

    def test_docs_review_and_clean_checks_are_unchanged(self):
        """Vor: fehlende Feature-Doku, Review ohne PASS, uncommittete Datei.
        Aktion: gate_errors. Erwartet: je ein Befund zu docs/features,
        Review-PASS und Sauberkeit."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, docs=False, review="FAIL")
        (worktree / "offen.txt").write_text("x\n", encoding="utf-8")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("docs/features/AP7.md", text)
        self.assertIn("Verdict: PASS", text)
        self.assertIn("sauber", text)
        self.assertIn("offen.txt", text)


class SyncTicketTest(RunnerCase):
    """Übernahme des Paketabschlusses in den Projektspeicher."""

    def sync(self, worktree, pid="AP1", **kwargs):
        return requires(self.module, "sync_ticket")(
            self.project, worktree, pid, **kwargs)

    def test_a_complete_ticket_is_taken_over_and_clears_block_fields(self):
        """Vor: Projekt AP1 blockiert; Arbeitskopie TICKET-AP1.json done mit
        commit/test/pr_url. Aktion: sync_ticket(require_commit=False).
        Erwartet: changed=True; state/commit/test/pr_url übernommen,
        blocked_reason/waiting_note geräumt."""
        self.store(ticket("AP1", "Titel", state="blocked",
                          blocked_reason="alt", waiting_note="alt"))
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit="deadbee",
            test="test_ap1", pr_url="http://example.invalid/pr/1"))

        changed, message = self.sync(worktree, require_commit=False)

        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("done", record["state"])
        self.assertEqual("deadbee", record["commit"])
        self.assertEqual("test_ap1", record["test"])
        self.assertEqual("http://example.invalid/pr/1", record["pr_url"])
        self.assertEqual("", record["blocked_reason"])
        self.assertEqual("", record["waiting_note"])

    def test_require_commit_rejects_a_commit_unknown_to_the_project(self):
        """Vor: Arbeitskopie nennt einen Commit, den das Projekt nicht kennt.
        Aktion: sync_ticket ohne require_commit=False.
        Erwartet: changed=False, Speicher unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit="deadbee",
            test="test_ap1"))

        changed, message = self.sync(worktree)

        self.assertFalse(changed, message)
        self.assertEqual(before, self.read_store())

    def test_missing_or_incomplete_source_is_refused_without_change(self):
        """Vor: fehlende Datei, defekte Datei und nicht-done-Datei.
        Aktion: sync_ticket. Erwartet: jeweils changed=False und ein Grund;
        der Speicher bleibt unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()

        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)
        self.assertEqual(before, self.read_store())

        (worktree / "TICKET-AP1.json").write_text("{", encoding="utf-8")
        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)

        self.write_ticket_file(worktree, ticket("AP1", "Titel",
                                                state="open"))
        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)
        self.assertEqual(before, self.read_store())

    def test_a_ticket_missing_in_the_project_is_refused(self):
        """Vor: Arbeitskopie X9 done, Projekt kennt X9 nicht. Aktion:
        sync_ticket. Erwartet: changed=False, kein Ticket wird erfunden."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "X9", "Fremd", state="done", commit="abcdef1", test="test_x9"))

        changed, message = self.sync(worktree, "X9", require_commit=False)

        self.assertFalse(changed, message)
        self.assertNotIn("X9", self.records())


class MarkAndReportTest(RunnerCase):
    """Blockier-/Wartevermerke und der Statusbericht."""

    def test_mark_blocked_sets_state_and_reason_idempotently(self):
        """Vor: AP1 offen. Aktion: mark_blocked zweimal. Erwartet: erster
        Aufruf changed=True mit state=blocked und Grund, zweiter changed=False
        ohne weiteren Zustandswechsel."""
        self.store(ticket("AP1", "Titel"))

        changed, message = requires(self.module, "mark_blocked")(
            self.project, "AP1", "Merge kaputt")
        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("blocked", record["state"])
        self.assertEqual("Merge kaputt", record["blocked_reason"])

        changed, message = self.module.mark_blocked(
            self.project, "AP1", "anderer Grund")
        self.assertFalse(changed, message)
        self.assertEqual("Merge kaputt", self.records()["AP1"]["blocked_reason"])

    def test_mark_waiting_merge_sets_note_and_pr_url(self):
        """Vor: AP1 offen. Aktion: mark_waiting_merge mit Notiz und PR-URL.
        Erwartet: state=waiting-merge, waiting_note und pr_url gesetzt;
        ein zweiter Aufruf ändert nichts."""
        self.store(ticket("AP1", "Titel"))

        changed, message = requires(self.module, "mark_waiting_merge")(
            self.project, "AP1", "PR offen", "http://example.invalid/pr/9")

        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("PR offen", record["waiting_note"])
        self.assertEqual("http://example.invalid/pr/9", record["pr_url"])

        changed, message = self.module.mark_waiting_merge(
            self.project, "AP1", "neu", "http://example.invalid/pr/10")
        self.assertFalse(changed, message)
        self.assertEqual("PR offen", self.records()["AP1"]["waiting_note"])

    def test_status_report_groups_by_store_state(self):
        """Vor: offen/in-progress/blockiert/wartend/erledigt im Speicher.
        Aktion: status_report. Erwartet: open enthält offen und in-progress,
        waiting/blocked/done jeweils die passenden IDs."""
        self.store(
            ticket("AP1", "Offen"),
            ticket("AP2", "Läuft", state="in-progress"),
            ticket("AP3", "Blockiert", state="blocked",
                   blocked_reason="x"),
            ticket("AP4", "Wartet", state="waiting-merge",
                   waiting_note="x"),
            ticket("AP5", "Fertig", state="done", commit="abcdef1",
                   test="test_ap5"),
        )

        report = requires(self.module, "status_report")(self.project)

        self.assertEqual(["AP1", "AP2"], report["open"])
        self.assertEqual(["AP4"], report["waiting"])
        self.assertEqual(["AP3"], report["blocked"])
        self.assertEqual(["AP5"], report["done"])


class PriorityViewTest(RunnerCase):
    """Priorisierungsansicht und -validierung auf dem Speicher."""

    def setUp(self):
        super().setUp()
        self.store(
            ticket("AP1", "Eins", priority="P1"),
            ticket("AP2", "Zwei", priority="P0"),
            ticket("AP3", "Fertig", state="done", commit="abcdef1",
                   test="test_ap3"),
            ticket("B1", "Bug", type="bug"),
        )
        self.set_order("AP3 AP2 AP1 X9")

    def test_priority_view_reports_status_and_effective_queue(self):
        """Vor: PACKAGE_ORDER mit erledigtem und unbekanntem Eintrag.
        Aktion: priority_view. Erwartet: Status erledigt/offen/fehlt je
        Eintrag; queue in Standardordnung AP2, AP1, B1 (erledigt entfällt)."""
        view = requires(self.module, "priority_view")(self.project)

        statuses = {entry["id"]: entry["status"] for entry in view["order"]}
        self.assertEqual("erledigt", statuses["AP3"])
        self.assertEqual("offen", statuses["AP2"])
        self.assertEqual("fehlt", statuses["X9"])
        self.assertEqual(["AP2", "AP1", "B1"],
                         [entry["id"] for entry in view["queue"]])

    def test_normalize_order_deduplicates_and_rejects_unknown_ids(self):
        """Vor: gültige und unbekannte IDs. Aktion: normalize_order.
        Erwartet: Dubletten entfallen, Reihenfolge bleibt; unbekannte ID
        ist ValueError mit der ID in der Meldung."""
        normalize_order = requires(self.module, "normalize_order")

        self.assertEqual(["AP2", "AP1"],
                         normalize_order(self.project, "AP2, AP1, AP2"))
        with self.assertRaises(ValueError) as caught:
            normalize_order(self.project, "AP2 X9")
        self.assertIn("X9", str(caught.exception))


class WorkCopyTest(RunnerCase):
    """Arbeitsnotizen, Tickettransport und Git-Exclude."""

    def test_copy_work_notes_transfers_only_agents_md(self):
        """Vor: Projekt mit AGENTS.md, TICKETS.md und FEEDBACK.md.
        Aktion: copy_work_notes. Erwartet: nur AGENTS.md in der Arbeitskopie;
        die alten Ledger-Dateien werden nicht mehr transportiert."""
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n",
                                                  encoding="utf-8")
        worktree = self.add_worktree()

        copied, skipped = requires(self.module, "copy_work_notes")(
            self.project, worktree)

        self.assertEqual(["AGENTS.md"], copied)
        self.assertEqual([], skipped)
        self.assertTrue((worktree / "AGENTS.md").is_file())
        self.assertFalse((worktree / "TICKETS.md").exists())
        self.assertFalse((worktree / "FEEDBACK.md").exists())

    def exclude_path(self, worktree):
        result = support.git(worktree, "rev-parse", "--git-path", "info/exclude")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else worktree / path

    def test_transport_ticket_writes_a_visible_file_and_excludes_it(self):
        """Vor: AP1 im Projekt-Speicher, echte Arbeitskopie. Aktion:
        transport_ticket zweimal. Erwartet: TICKET-AP1.json in der Wurzel mit
        dem Ticketinhalt; genau ein Exclude-Eintrag, auch nach dem zweiten
        Lauf."""
        self.store(ticket("AP1", "Titel", state="in-progress"))
        worktree = self.add_worktree()
        transport = requires(self.module, "transport_ticket")

        ok, exclude_ok = transport(self.project, worktree, "AP1")

        self.assertTrue(ok)
        self.assertTrue(exclude_ok)
        target = worktree / "TICKET-AP1.json"
        self.assertTrue(target.is_file())
        self.assertEqual("AP1",
                         json.loads(target.read_text(encoding="utf-8"))["id"])
        exclude = self.exclude_path(worktree)
        first = exclude.read_text(encoding="utf-8")
        self.assertIn("TICKET-AP1.json", first)

        transport(self.project, worktree, "AP1")
        self.assertEqual(1, exclude.read_text(encoding="utf-8")
                         .count("TICKET-AP1.json"))

    def test_transport_ticket_missing_in_the_store_fails(self):
        """Vor: Projekt ohne Ticket AP9. Aktion: transport_ticket.
        Erwartet: ok=False, keine Datei, kein Exclude-Eintrag."""
        worktree = self.add_worktree()

        ok, _ = requires(self.module, "transport_ticket")(
            self.project, worktree, "AP9")

        self.assertFalse(ok)
        self.assertFalse((worktree / "TICKET-AP9.json").exists())
        exclude = self.exclude_path(worktree)
        text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        self.assertNotIn("TICKET-AP9.json", text)

    def test_copy_notes_id_transports_the_ticket_and_reports_missing_ones(self):
        """Vor: AP1 im Speicher, AP9 nicht. Aktion: copy-notes --id AP1 bzw.
        --id AP9 über die CLI. Erwartet: AP1 Exit 0 mit OK-Zeile und Datei;
        AP9 Exit 1 mit FEHLT-Zeile und ohne Datei."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("VIBE")}
        env.update({
            "HOME": str(self.root / "home"),
            "VIBE": str(self.root),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_NO_CONTAINER": "1",
        })
        (self.root / "home").mkdir(exist_ok=True)

        def run(pid):
            return subprocess.run(
                [sys.executable, str(MODULE), "copy-notes",
                 "--project", str(self.project),
                 "--worktree", str(worktree), "--id", pid],
                cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=60)

        ok = run("AP1")
        self.assertEqual(0, ok.returncode, ok.stdout + ok.stderr)
        self.assertIn("OK:", ok.stdout)
        self.assertTrue((worktree / "TICKET-AP1.json").is_file())

        missing = run("AP9")
        self.assertEqual(1, missing.returncode,
                         missing.stdout + missing.stderr)
        self.assertIn("FEHLT:", missing.stdout)
        self.assertFalse((worktree / "TICKET-AP9.json").exists())

    def test_is_work_note_path_covers_ticket_files_at_the_root_only(self):
        """Vor: Stammdateien TICKET-<ID>.json und Pfade in Unterordnern.
        Aktion: is_work_note_path. Erwartet: Stammdateien sind Arbeitsnotizen
        (kein Dirty-Befund), Unterordner und andere Endungen nicht."""
        check = requires(self.module, "is_work_note_path")

        for value in ("TICKET-AP7.json", "TICKET-GH-48.json",
                      "AGENTS.md"):
            with self.subTest(path=value):
                self.assertTrue(check(value))
        for value in ("sub/TICKET-AP7.json", "TICKET-AP7.txt",
                      "TICKET-.json", "notiz.md"):
            with self.subTest(path=value):
                self.assertFalse(check(value))

    def test_project_exclude_mentions_only_current_work_notes(self):
        """Vor: Git-Projekt. Aktion: ensure_project_exclude. Erwartet:
        .vibe/tmp/ und AGENTS.md sind eingetragen; TICKETS.md/FEEDBACK.md
        nicht mehr."""
        requires(self.module, "ensure_project_exclude")(self.project)

        exclude = self.project / ".git" / "info" / "exclude"
        text = exclude.read_text(encoding="utf-8")
        self.assertIn(".vibe/tmp/", text)
        self.assertIn("AGENTS.md", text)
        self.assertNotIn("TICKETS.md", text)
        self.assertNotIn("FEEDBACK.md", text)


if __name__ == "__main__":
    unittest.main()
