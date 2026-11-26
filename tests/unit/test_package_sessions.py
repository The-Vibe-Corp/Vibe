"""Package session assignments: persistence, resume, cleanup and migration.

The work package is the single owner of a session assignment. Assignments are
stored on the package record in ``.vibe/tickets.json`` and must never be
derived from a display name. This module tests the public helper contract of
``bin/vibe_tickets.py`` and the ``vibe sessions migrate`` CLI entry point.

Aufruf: python3 -m unittest tests.unit.test_package_sessions -v
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

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support  # noqa: E402


def load_module(path, name):
    """Loads a bin module without installing it."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


TICKETS = load_module(BIN / "vibe_tickets.py", "vibe_tickets_gh99_pkg_sessions")
RUNS = load_module(BIN / "vibe_runs.py", "vibe_runs_gh99_pkg_sessions")

# Same strict class the harness registry uses for harness session IDs.
INVALID_SESSION_IDS = ("", None, 17, "ses;rm", "ses x", "ses/../x",
                       "ses.punkt", "ä")

PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)


class TicketFixture(unittest.TestCase):
    """Two isolated projects with a small ticket store each."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.project_a = self.root / "projekt_a"
        self.project_b = self.root / "projekt_b"
        support.write_project(
            self.project_a, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Erster Auftrag"),
                     support.ticket_record("AP2", "Zweiter Auftrag")],
        )
        support.write_project(
            self.project_b, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Gleicher Titel im Ausland"),
                     support.ticket_record("BX1", "Nur im Ausland")],
        )

    # ---------- fixture helpers ----------

    def store_path(self, project=None):
        return Path(project or self.project_a) / ".vibe" / "tickets.json"

    def document(self, project=None):
        return json.loads(self.store_path(project).read_text(encoding="utf-8"))

    def write_document(self, doc, project=None):
        self.store_path(project).write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def ticket(self, tid, project=None):
        record = TICKETS.find(TICKETS.load(project or self.project_a), tid)
        self.assertIsNotNone(record, "Ticket fehlt: " + tid)
        return record

    def write_field(self, tid, field, value, project=None):
        """Seeds a raw package field without calling the helper under test."""
        doc = self.document(project)
        for record in doc["tickets"]:
            if record.get("id") == tid:
                record[field] = value
                break
        else:
            self.fail("Ticket fehlt beim Seeden: " + tid)
        self.write_document(doc, project)


class SessionsOfTest(TicketFixture):
    """Saved assignments are read back by package ID, never by title."""

    def test_missing_field_reads_as_an_empty_list(self):
        for tid in ("AP1", "AP2"):
            self.assertEqual([], TICKETS.sessions_of(self.ticket(tid)), tid)

    def test_the_stored_list_is_returned_unchanged(self):
        self.write_field("AP1", "sessions", ["ses_a", "ses_b"])

        self.assertEqual(["ses_a", "ses_b"],
                         TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP2")))


class AttachSessionTest(TicketFixture):
    """``attach_session`` persists a validated assignment on one package."""

    def test_attach_persists_on_the_given_package(self):
        result = TICKETS.attach_session(self.project_a, "AP1", "ses_eins")

        self.assertEqual(["ses_eins"], result)
        self.assertEqual(["ses_eins"],
                         TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP2")))

    def test_attach_is_idempotent_and_keeps_multiple_sessions(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        second = TICKETS.attach_session(self.project_a, "AP1", "ses_zwei")
        self.assertEqual(["ses_eins", "ses_zwei"], second)

        again = TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        self.assertEqual(["ses_eins", "ses_zwei"], again,
                         "Wiederholtes Anhängen erzeugte ein Duplikat")
        self.assertEqual(["ses_eins", "ses_zwei"],
                         TICKETS.sessions_of(self.ticket("AP1")))

    def test_assignment_survives_a_title_change(self):
        """The assignment is keyed by package ID, not by a display name."""
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        TICKETS.update(self.project_a, "AP1", title="Zweiter Auftrag")

        self.assertEqual(["ses_eins"],
                         TICKETS.sessions_of(TICKETS.find(
                             TICKETS.load(self.project_a), "AP1")))
        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP2")))

    def test_invalid_session_ids_are_rejected_without_writing(self):
        for sid in INVALID_SESSION_IDS:
            with self.subTest(session=sid):
                with self.assertRaises(ValueError):
                    TICKETS.attach_session(self.project_a, "AP1", sid)
                self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")),
                                 "Ungültige Kennung wurde gespeichert: "
                                 + repr(sid))

    def test_an_unknown_package_in_the_project_is_rejected(self):
        with self.assertRaises(ValueError):
            TICKETS.attach_session(self.project_a, "GIBT_ES_NICHT", "ses_eins")

    def test_a_package_that_only_exists_in_another_project_is_rejected(self):
        """``BX1`` belongs to project B; project A must not accept it."""
        with self.assertRaises(ValueError):
            TICKETS.attach_session(self.project_a, "BX1", "ses_eins")
        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))

    def test_a_session_cannot_be_assigned_to_a_second_package(self):
        """One session belongs to exactly one package of exactly one project."""
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")

        with self.assertRaises(ValueError):
            TICKETS.attach_session(self.project_a, "AP2", "ses_eins")
        self.assertEqual(["ses_eins"],
                         TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP2")))

    def test_a_session_cannot_be_assigned_across_projects(self):
        """Both projects have ``AP1``; the same session stays with its owner."""
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")

        with self.assertRaises(ValueError):
            TICKETS.attach_session(self.project_b, "AP1", "ses_eins")
        self.assertEqual([], TICKETS.sessions_of(
            self.ticket("AP1", self.project_b)))


class ResumeSessionTest(TicketFixture):
    """Resume reuses a stored session; an empty result means "start new"."""

    def test_without_a_stored_session_resume_is_empty(self):
        self.assertEqual("", TICKETS.resume_session(self.project_a, "AP1"))

    def test_resume_reuses_the_stored_session(self):
        TICKETS.attach_session(self.project_a, "AP2", "ses_pause")

        self.assertEqual("ses_pause",
                         TICKETS.resume_session(self.project_a, "AP2"))

    def test_resume_with_several_sessions_returns_a_stored_one_stably(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        TICKETS.attach_session(self.project_a, "AP1", "ses_zwei")

        first = TICKETS.resume_session(self.project_a, "AP1")
        self.assertIn(first, ["ses_eins", "ses_zwei"], first)
        self.assertEqual(first, TICKETS.resume_session(self.project_a, "AP1"),
                         "Die Fortsetzungswahl ist nicht deterministisch")

    def test_resume_never_crosses_the_project_boundary(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")

        self.assertEqual("", TICKETS.resume_session(self.project_b, "AP1"))

    def test_resume_after_cleanup_starts_fresh(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        TICKETS.clear_sessions(self.project_a, "AP1")

        self.assertEqual("", TICKETS.resume_session(self.project_a, "AP1"))


class CleanupTest(TicketFixture):
    """Cleanup removes assignments only, and only for one package."""

    def test_clear_removes_the_assignments_of_one_package_only(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        TICKETS.attach_session(self.project_a, "AP2", "ses_zwei")

        TICKETS.clear_sessions(self.project_a, "AP1")

        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual(["ses_zwei"], TICKETS.sessions_of(self.ticket("AP2")))

    def test_clear_is_idempotent(self):
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")

        TICKETS.clear_sessions(self.project_a, "AP1")
        TICKETS.clear_sessions(self.project_a, "AP1")

        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))

    def test_clear_keeps_the_package_costs(self):
        usage = {"models": {"opencode/model-a": {
            "agent": "coding-agent", "input": 1000,
            "cached_input": 100, "output": 50}}}
        TICKETS.attach_session(self.project_a, "AP1", "ses_eins")
        TICKETS.record_usage(self.project_a, "AP1", "ses_eins", usage)

        TICKETS.clear_sessions(self.project_a, "AP1")

        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual(
            usage, TICKETS.usage_of(self.ticket("AP1")).get("sessions", {}).get(
                "ses_eins"),
            "Bereinigung hat die Kosten gelöscht")

    def test_a_successful_completion_path_flushes_costs_before_cleanup(self):
        """Simulated runner success: persist both sessions' usage, then clear.

        The costs must stay complete even though no session is left attached.
        """
        for sid, tokens in (("ses_eins", 1000), ("ses_zwei", 2000)):
            TICKETS.attach_session(self.project_a, "AP1", sid)
            TICKETS.record_usage(self.project_a, "AP1", sid, {"models": {
                "opencode/model-a": {"agent": "coding-agent",
                                     "input": tokens, "cached_input": 0,
                                     "output": 0}}})
        before = TICKETS.usage_of(self.ticket("AP1"))

        TICKETS.clear_sessions(self.project_a, "AP1")

        self.assertEqual([], TICKETS.sessions_of(self.ticket("AP1")))
        self.assertEqual(before, TICKETS.usage_of(self.ticket("AP1")),
                         "Der Erfolgspfad hat Kosten verloren")

    def test_a_paused_or_aborted_session_is_not_cleared(self):
        """No cleanup is triggered by pause/abort/failure; the stored session
        remains available for a later resume."""
        TICKETS.attach_session(self.project_a, "AP1", "ses_pause")

        # A paused/aborted/failed run does not call clear_sessions.
        self.assertEqual("ses_pause",
                         TICKETS.resume_session(self.project_a, "AP1"))
        self.assertEqual(["ses_pause"],
                         TICKETS.sessions_of(self.ticket("AP1")))


class MigrationFixture(unittest.TestCase):
    """CLI migration against a legacy session registry in an isolated VIBE."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        for path in (self.home, self.install, self.runtime, self.state,
                     self.root / "tmp"):
            path.mkdir(parents=True, exist_ok=True)
        self.project = self.root / "proj"
        self.foreign = self.root / "fremd"
        support.write_project(
            self.project, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Erster Auftrag"),
                     support.ticket_record("AP2", "Zweiter Auftrag")],
        )
        support.write_project(
            self.foreign, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Ausländisches Paket")],
        )
        # Existing assignment + existing cost must survive the migration.
        existing_costs = {"version": 1, "sessions": {"ses_alt": {"models": {
            "opencode/model-a": {"agent": "coding-agent", "input": 7,
                                 "cached_input": 0, "output": 3}}}}}
        support.write_ticket_store(self.project, [
            support.ticket_record("AP1", "Erster Auftrag", sessions=["ses_alt"],
                                  costs=existing_costs),
            support.ticket_record("AP2", "Zweiter Auftrag"),
        ])
        # Legacy registry: one unambiguous (explicit package_id in this
        # project), one ambiguous (no package hint), one from another project.
        registry = RUNS.SessionRegistry(str(self.runtime))
        real = str(self.project.resolve())
        foreign_real = str(self.foreign.resolve())
        registry.observe("ses_eindeutig", project=real, name="proj",
                         run_id="", agent="vibe-agent", harness="opencode",
                         now=100, package_id="AP1")
        registry.observe("ses_mehrdeutig", project=real, name="proj",
                         run_id="", agent="vibe-agent", harness="opencode",
                         now=200)
        registry.observe("ses_ausland", project=foreign_real, name="fremd",
                         run_id="", agent="vibe-agent", harness="opencode",
                         now=300, package_id="AP1")

    def run_sessions(self, *args):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX"):
                env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "TMPDIR": str(self.root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return subprocess.run(
            [sys.executable, str(CLI), "sessions", *args],
            cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=90,
        )

    def run_migrate(self, *args):
        return self.run_sessions("migrate", *args)

    def sessions_of(self, tid):
        return TICKETS.sessions_of(TICKETS.find(TICKETS.load(self.project), tid))


class MigrationTest(MigrationFixture):
    """Migration adopts clear legacy data, refuses guesses, keeps old data."""

    def test_unambiguous_legacy_session_is_adopted(self):
        result = self.run_migrate("proj")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("ses_eindeutig", self.sessions_of("AP1"),
                      "Eindeutige Altdaten wurden nicht übernommen")

    def test_ambiguous_legacy_session_is_not_assigned_and_is_documented(self):
        result = self.run_migrate("proj")

        combined = result.stdout + result.stderr
        for tid in ("AP1", "AP2"):
            self.assertNotIn("ses_mehrdeutig", self.sessions_of(tid),
                             "Mehrdeutige Altdaten wurden auf Verdacht zugeordnet")
        self.assertIn("ses_mehrdeutig", combined,
                      "Nicht übernommene Altdaten wurden nicht dokumentiert: "
                      + combined)

    def test_foreign_project_session_is_not_assigned(self):
        result = self.run_migrate("proj")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        for tid in ("AP1", "AP2"):
            self.assertNotIn("ses_ausland", self.sessions_of(tid),
                             "Projektübergreifende Zuordnung übernommen")

    def test_existing_assignments_and_costs_survive_migration(self):
        before_costs = TICKETS.usage_of(
            TICKETS.find(TICKETS.load(self.project), "AP1"))

        result = self.run_migrate("proj")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("ses_alt", self.sessions_of("AP1"),
                      "Bestehende Zuordnung wurde verworfen")
        after_costs = TICKETS.usage_of(
            TICKETS.find(TICKETS.load(self.project), "AP1"))
        self.assertEqual(
            before_costs.get("sessions", {}).get("ses_alt"),
            after_costs.get("sessions", {}).get("ses_alt"),
            "Bestehende Kostendaten wurden überschrieben",
        )


class RunnerCleanupFixture(unittest.TestCase):
    """Real runner with a fake agent, isolating session cleanup behaviour."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project, PROJECT_ENV,
            tickets=[support.ticket_record("AP1", "Erster Auftrag")],
        )
        support.commit_all(self.project, "Ausgangsstand")
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"

    def seed_sessions(self, sessions):
        store = self.project / ".vibe" / "tickets.json"
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["tickets"][0]["sessions"] = sessions
        store.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")

    def sessions_of(self, tid="AP1"):
        """Raw read so the runner assertion is independent of helper APIs."""
        doc = json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        for record in doc["tickets"]:
            if record.get("id") == tid:
                return list(record.get("sessions") or [])
        self.fail("Ticket fehlt: " + tid)

    def run_runner(self, mode, max_retries=0):
        env = os.environ.copy()
        for key in list(env):
            if (key.startswith("VIBE") or key.startswith("SANDBOX")
                    or key.startswith("FAKE_")
                    or key in ("AGENT", "TESTER", "REVIEWER", "MAX_RETRIES",
                               "VERIFY_QUICK", "VERIFY_FULL", "VERIFY_PACKAGE")):
                env.pop(key, None)
        fakebin = support.install_fake_tools(self.root)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": "proj",
            "VIBE_RETRY_DELAY": "0",
            "VIBE_MAX_PACKAGES": "1",
            "HOME": str(self.home),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_CALLS": str(self.calls),
            "FAKE_COUNTER": str(self.counter),
            "FAKE_ARGS_PATH": str(self.root / "opencode.args"),
            "FAKE_MODE": mode,
        })
        return subprocess.run(
            ["bash", str(self.install / "bin" / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120,
        )


class RunnerCleanupTest(RunnerCleanupFixture):
    """Only a successful package completion clears its session assignments."""

    def test_successful_completion_clears_the_package_sessions(self):
        self.seed_sessions(["ses_vorher"])

        result = self.run_runner("complete")

        log_path = self.runtime / "proj.log"
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + log)
        self.assertIn("FERTIG", log, "Der Lauf schloss nicht erfolgreich ab:\n" + log)
        self.assertEqual([], self.sessions_of("AP1"),
                         "Erfolgreicher Abschluss hat die Sessions nicht bereinigt")

    def test_failed_run_keeps_the_package_sessions(self):
        self.seed_sessions(["ses_vorher"])

        result = self.run_runner("fail")

        # Ein fehlgeschlagener Lauf darf keine Bereinigung auslösen.
        self.assertIn("ses_vorher", self.sessions_of("AP1"),
                      "Ein fehlgeschlagener Lauf hat Sessions bereinigt: "
                      + result.stdout + result.stderr)


class SessionCommandsTest(MigrationFixture):
    """CLI verbs operating on a package's stored session assignment."""

    def test_attach_persists_the_assignment(self):
        result = self.run_sessions("attach", "proj", "AP1", "ses_cli")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("ses_cli", self.sessions_of("AP1"),
                      "sessions attach hat die Zuordnung nicht gespeichert")

    def test_attach_rejects_an_invalid_session_id(self):
        result = self.run_sessions("attach", "proj", "AP1", "ses;rm")

        self.assertNotEqual(0, result.returncode,
                            "Ungültige Kennung wurde angenommen")
        self.assertEqual(
            ["ses_alt"], self.sessions_of("AP1"),
            "Eine abgelehnte Kennung darf die bestehende Zuordnung nicht "
            "zerstören (Vorprüfung vor dem Schreiben)",
        )

    def test_for_package_lists_the_stored_sessions(self):
        TICKETS.attach_session(self.project, "AP2", "ses_gespeichert")

        result = self.run_sessions("for-package", "proj", "AP2")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("ses_gespeichert", result.stdout + result.stderr,
                      "Die gespeicherte Session wird nicht angezeigt")

    def test_finish_package_clears_sessions_but_keeps_costs(self):
        usage = {"models": {"opencode/model-a": {
            "agent": "coding-agent", "input": 100,
            "cached_input": 0, "output": 20}}}
        TICKETS.attach_session(self.project, "AP2", "ses_fertig")
        TICKETS.record_usage(self.project, "AP2", "ses_fertig", usage)

        result = self.run_sessions("finish-package", "proj", "AP2")

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        self.assertEqual([], self.sessions_of("AP2"),
                         "Erfolgreicher Abschluss hat Sessions nicht bereinigt")
        stored = TICKETS.usage_of(TICKETS.find(TICKETS.load(self.project), "AP2"))
        self.assertEqual(
            usage, stored.get("sessions", {}).get("ses_fertig"),
            "Erfolgreicher Abschluss hat die Kosten nicht gespeichert",
        )


if __name__ == "__main__":
    unittest.main()
