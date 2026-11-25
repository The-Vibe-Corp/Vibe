"""Worktrees: Register, Sitzungsbindung, Kollisionen, Aufräumen und Projekt-Env-Transport.

Aufruf: python3 -m unittest tests.unit.test_worktrees -v
"""


# ===========================================================================
# (Arbeitskopien/Sessions): T-W2, T-W1, T-S1, T-G5, T-G1
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
RUNS_PY = BIN / "vibe_runs.py"
PACKAGES = BIN / "vibe_packages.py"
CLI = BIN / "vibe"

sys.path.insert(0, str(BIN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "VIBE_GITHUB_CREDENTIAL",
    "XDG_CONFIG_HOME",
)

_RUNS_CACHE = {}


def runs_module():
    """Lädt ``bin/vibe_runs.py`` als eigenes Modul (Rotphase: Lücken)."""
    if "runs" in _RUNS_CACHE:
        return _RUNS_CACHE["runs"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_runs_ap4_under_test", str(RUNS_PY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _RUNS_CACHE["runs"] = module
    return module


def real_git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


def real_git_out(cwd, *argv):
    return real_git(cwd, *argv).stdout.strip()


def fresh_env(root=None, **extra):
    env = {key: value for key, value in os.environ.items()
           if key not in ISOLATED_ENV and not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "NO_PROXY": "127.0.0.1,localhost",
    })
    env.update(GIT_IDENTITY)
    if root is not None:
        env["HOME"] = str(Path(root) / "home")
        env["VIBE_NO_CONTAINER"] = "1"
    env.update({key: str(value) for key, value in extra.items()})
    return env


# ------------------------------------------------------- T-W2 Worktree registry
class WorktreeRegistryTest(unittest.TestCase):
    """AK T-W2: Registry-API, Felder, Persistenz, Upsert und realpath."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.runtime = self.base / "_logs"
        self.module = runs_module()

    def registry(self):
        return self.module.WorktreeRegistry(str(self.runtime))

    def project(self, name="proj", real=True):
        path = self.base / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path.resolve()) if real else str(path)

    def register(self, registry=None, project=None, pid="F1", path=None,
                 branch="feature/test/f1", **extra):
        registry = registry or self.registry()
        return registry.register(
            project=project or self.project(),
            id=pid,
            branch=branch,
            path=path or str(self.base / "worktrees" / pid),
            base_commit="0" * 40,
            **extra,
        )

    def test_register_and_get_roundtrip_with_all_contract_fields(self):
        """Vorbedingung: leere Registry.
        Aktion: einen Worktree registrieren und per ``get`` lesen.
        Erwartung: Eintrag mit project (realpath), id, branch, path,
        base_commit, created, updated, pr_url, session, state; created und
        updated sind Zeitangaben.
        Fehlerfall: Feld fehlt, Pfad ist nicht realpath oder get liefert
        einen anderen Eintrag.
        """
        project = self.project()
        path = str(self.base / "worktrees" / "F1")

        self.register(project=project, path=path, pr_url="http://127.0.0.1/pull/42",
                      session="ses_1", state="waiting")

        entry = self.registry().get(project, "F1")
        self.assertIsNotNone(entry, "Registry-Eintrag nicht gefunden")
        for field in ("project", "id", "branch", "path", "base_commit",
                      "created", "updated", "pr_url", "session", "state"):
            self.assertIn(field, entry, "Feld %r fehlt: %r" % (field, entry))
        self.assertEqual(os.path.realpath(project), entry["project"])
        self.assertEqual("F1", entry["id"])
        self.assertEqual("feature/test/f1", entry["branch"])
        self.assertEqual(path, entry["path"])
        self.assertEqual("http://127.0.0.1/pull/42", entry["pr_url"])
        self.assertEqual("ses_1", entry["session"])
        self.assertEqual("waiting", entry["state"])
        self.assertTrue(str(entry["created"]).strip())
        self.assertTrue(str(entry["updated"]).strip())

    def test_get_is_keyed_by_project_and_id(self):
        """Vorbedingung: zwei Projekte mit gleicher Paket-ID.
        Aktion: ``get`` je Projekt und für ein unbekanntes Projekt.
        Erwartung: jeweils der richtige Eintrag; unbekannt → None.
        Fehlerfall: Einträge verwechseln sich.
        """
        first = self.project("eins")
        second = self.project("zwei")
        self.register(project=first, path=str(self.base / "wt1"))
        self.register(project=second, path=str(self.base / "wt2"))

        self.assertEqual(str(self.base / "wt1"),
                         self.registry().get(first, "F1")["path"])
        self.assertEqual(str(self.base / "wt2"),
                         self.registry().get(second, "F1")["path"])
        self.assertIsNone(self.registry().get(self.project("fremd"), "F1"))

    def test_all_filters_by_project_and_returns_all_without_argument(self):
        """Vorbedingung: drei Einträge in zwei Projekten.
        Aktion: ``all(project)`` und ``all()``.
        Erwartung: Projektfilter liefert nur dessen Einträge; ohne Argument
        alle Einträge.
        Fehlerfall: Filter wirkungslos oder fremde Einträge gemischt.
        """
        first = self.project("eins")
        second = self.project("zwei")
        self.register(project=first, pid="F1")
        self.register(project=first, pid="F2")
        self.register(project=second, pid="F1")

        self.assertEqual({"F1", "F2"},
                         {item["id"] for item in self.registry().all(first)})
        self.assertEqual(3, len(self.registry().all()))

    def test_register_updates_existing_entry_and_keeps_created(self):
        """Vorbedingung: ein registrierter Worktree.
        Aktion: denselben Eintrag mit neuer MR-URL/Status erneut registrieren.
        Erwartung: genau ein Eintrag; ``created`` bleibt, ``updated`` und die
        neuen Werte sind übernommen.
        Fehlerfall: Duplikat oder verlorene Aktualisierung.
        """
        project = self.project()
        self.register(project=project, pr_url="", state="waiting")
        first = self.registry().get(project, "F1")

        self.register(project=project, pr_url="http://127.0.0.1/pull/7",
                      state="merged")

        entries = self.registry().all(project)
        self.assertEqual(1, len(entries), entries)
        self.assertEqual(first["created"], entries[0]["created"])
        self.assertEqual("http://127.0.0.1/pull/7", entries[0]["pr_url"])
        self.assertEqual("merged", entries[0]["state"])

    def test_unregister_removes_only_the_named_entry(self):
        """Vorbedingung: zwei Einträge im selben Projekt.
        Aktion: einen davon abmelden.
        Erwartung: nur dieser fehlt; der andere bleibt.
        Fehlerfall: falscher oder kein Eintrag entfernt.
        """
        project = self.project()
        self.register(project=project, pid="F1")
        self.register(project=project, pid="F2")

        self.registry().unregister(project, "F1")

        self.assertIsNone(self.registry().get(project, "F1"))
        self.assertIsNotNone(self.registry().get(project, "F2"))

    def test_registry_file_is_written_atomically_next_to_the_lock(self):
        """Vorbedingung: leere Registry.
        Aktion: einen Eintrag registrieren.
        Erwartung: ``<runtime>/worktrees.json`` existiert und ist gültiges
        JSON; eine Sperrdatei wird beim Schreiben verwendet.
        Fehlerfall: andere Ablage oder unlesbare Datei.
        """
        self.register()

        target = self.runtime / "worktrees.json"
        self.assertTrue(target.is_file(), "worktrees.json fehlt")
        json.loads(target.read_text(encoding="utf-8"))
        self.assertTrue((self.runtime / "worktrees.lock").exists(),
                        "Sperrdatei <runtime>/worktrees.lock fehlt")


# ------------------------------------------------- T-W1 Session worktree attach
class SessionWorktreeAttachmentTest(unittest.TestCase):
    """AK T-W1: Session-Einträge tragen den Worktree-Anhang."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.runtime = self.base / "_logs"
        self.project = self.base / "proj"
        self.project.mkdir()
        self.module = runs_module()

    def registry(self):
        return self.module.SessionRegistry(str(self.runtime))

    def test_observe_persists_worktree_path_package_and_branch(self):
        """Vorbedingung: leeres Session-Register.
        Aktion: Session mit ``worktree_path``, ``package_id`` und ``branch``
        beobachten.
        Erwartung: alle drei Felder stehen im Eintrag.
        Fehlerfall: Felder werden ignoriert.
        """
        entry = self.registry().observe(
            session="ses_wt", project=str(self.project), name="proj",
            run_id="lauf-1", agent="vibe", harness="opencode", now=100,
            worktree_path=str(self.base / "worktrees" / "F1"),
            package_id="F1", branch="feature/test/f1",
        )

        self.assertEqual(str(self.base / "worktrees" / "F1"),
                         entry.get("worktree_path"), entry)
        self.assertEqual("F1", entry.get("package_id"), entry)
        self.assertEqual("feature/test/f1", entry.get("branch"), entry)

    def test_old_entries_without_attachment_remain_readable(self):
        """Vorbedingung: ein Session-Eintrag ohne die neuen Felder (Alteintrag).
        Aktion: ``get`` und ``session_overview`` lesen.
        Erwartung: kein Fehler; fehlende Anhänge gelten als Integrationsstand
        (leer/fehlend).
        Fehlerfall: Ausnahme oder erfundener Worktree.
        """
        self.registry().observe(
            session="ses_alt", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=100)

        entry = self.registry().get("ses_alt")
        self.assertEqual("", str(entry.get("worktree_path") or ""), entry)
        overview = self.module.session_overview(str(self.runtime))
        self.assertEqual(1, len(overview), overview)
        self.assertFalse(overview[0].get("worktree_path"), overview[0])

    def test_overview_exposes_the_attachment_fields(self):
        """Vorbedingung: Session mit Worktree-Anhang.
        Aktion: ``session_overview`` lesen.
        Erwartung: ``worktree_path``, ``package_id`` und ``branch`` sind im
        Übersichtseintrag enthalten.
        Fehlerfall: UI/API erhalten den Anhang nicht.
        """
        self.registry().observe(
            session="ses_wt", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=100,
            worktree_path=str(self.base / "wt"), package_id="F1",
            branch="feature/x")

        entry = self.module.session_overview(str(self.runtime))[0]

        self.assertEqual(str(self.base / "wt"), entry.get("worktree_path"))
        self.assertEqual("F1", entry.get("package_id"))
        self.assertEqual("feature/x", entry.get("branch"))

    def test_stream_cli_passes_the_worktree_options(self):
        """Vorbedingung: leeres Session-Register; ein JSON-Ereignis mit
        Hauptsession auf stdin.
        Aktion: ``vibe_runs.py stream`` mit ``--session-worktree``,
        ``--session-package`` und ``--session-branch`` ausführen.
        Erwartung: der Registereintrag enthält die drei Angaben.
        Fehlerfall: Optionen werden nicht durchgereicht.
        """
        state_path = self.base / "stream.state.json"
        event = json.dumps({
            "type": "text", "sessionID": "ses_stream",
            "part": {"type": "text", "text": "Hallo"},
        }) + "\n"
        worktree = str(self.base / "worktrees" / "F1")

        result = subprocess.run(
            [sys.executable, str(RUNS_PY), "stream",
             "--state", str(state_path), "--attempt",
             "--sessions", str(self.runtime / "sessions.json"),
             "--session-project", str(self.project),
             "--session-name", "proj", "--session-run", "lauf-1",
             "--session-agent", "vibe", "--session-harness", "opencode",
             "--session-worktree", worktree,
             "--session-package", "F1",
             "--session-branch", "feature/test/f1"],
            input=event, env=fresh_env(self.base), capture_output=True,
            text=True, timeout=60, check=False)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        entry = self.registry().get("ses_stream")
        self.assertIsNotNone(entry, "Session wurde nicht registriert")
        self.assertEqual(worktree, entry.get("worktree_path"), entry)
        self.assertEqual("F1", entry.get("package_id"), entry)
        self.assertEqual("feature/test/f1", entry.get("branch"), entry)


# --------------------------------------------------------------- T-S1 persist
class SessionStatePersistTest(unittest.TestCase):
    """AK T-S1: Endzustand persistieren, Vorrang und Altersaufräumen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.runtime = self.base / "_logs"
        self.project = self.base / "proj"
        self.project.mkdir()
        self.module = runs_module()

    def registry(self):
        return self.module.SessionRegistry(str(self.runtime))

    def overview(self):
        return self.module.session_overview(str(self.runtime), limit=100)

    def sessions_finish(self, run_id, state):
        return subprocess.run(
            [sys.executable, str(RUNS_PY), "sessions-finish",
             "--runtime", str(self.runtime), "--run-id", run_id,
             "--state", state],
            env=fresh_env(self.base), capture_output=True, text=True,
            timeout=60, check=False)

    def test_sessions_finish_persists_the_state_without_a_run_record(self):
        """Vorbedingung: Session mit ``run_id``, aber ohne Eintrag im
        Laufregister (z. B. weggealtert).
        Aktion: ``sessions-finish --run-id … --state finished`` ausführen.
        Erwartung: ``session_overview`` zeigt ``finished``/„abgeschlossen“
        statt ``unknown``.
        Fehlerfall: Zustand bleibt unbekannt.
        """
        self.registry().observe(
            session="ses_1", project=str(self.project), name="proj",
            run_id="lauf-1", agent="vibe", harness="opencode", now=100)

        result = self.sessions_finish("lauf-1", "finished")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        entry = self.overview()[0]
        self.assertEqual("finished", entry.get("state"), entry)
        self.assertEqual("abgeschlossen", entry.get("state_label"), entry)

    def test_run_registry_state_wins_over_persisted_state(self):
        """Vorbedingung: Session persistiert ``finished``, das Laufregister
        führt dieselbe ``run_id`` aber als ``running``.
        Aktion: ``session_overview`` lesen.
        Erwartung: ``running`` (das Laufregister bleibt maßgeblich).
        Fehlerfall: der persistierte Zustand überdeckt den Live-Lauf.
        """
        self.registry().observe(
            session="ses_1", project=str(self.project), name="proj",
            run_id="lauf-1", agent="vibe", harness="opencode", now=100)
        self.assertEqual(0, self.sessions_finish("lauf-1", "finished").returncode)
        self.module.RunRegistry(str(self.runtime)).start(
            project=str(self.project), name="proj", key="proj",
            agent="vibe", session="ses_1", run_id="lauf-1", state="running")

        entry = self.overview()[0]

        self.assertEqual("running", entry.get("state"), entry)

    def test_aging_prune_removes_old_entries_without_a_worktree(self):
        """Vorbedingung: ein Eintrag ohne Worktree-Anhang mit ``last_seen``
        älter als 30 Tage und ein aktueller Eintrag.
        Aktion: ``sessions-finish`` für den aktuellen Lauf ausführen.
        Erwartung: der alte Eintrag ist entfernt, der aktuelle bleibt.
        Fehlerfall: alte Einträge bleiben unbegrenzt stehen.
        """
        old = int(time.time()) - 40 * 86400
        self.registry().observe(
            session="ses_alt", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=old)
        self.registry().observe(
            session="ses_neu", project=str(self.project), name="proj",
            run_id="lauf-neu", agent="vibe", harness="opencode")

        result = self.sessions_finish("lauf-neu", "finished")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        sessions = {item["session"] for item in self.overview()}
        self.assertNotIn("ses_alt", sessions,
                         "Alter Eintrag ohne Worktree wurde nicht entfernt")
        self.assertIn("ses_neu", sessions)

    def test_aging_prune_keeps_old_entries_with_an_existing_worktree(self):
        """Vorbedingung: ein alter Eintrag, dessen ``worktree_path`` auf ein
        existierendes Verzeichnis zeigt.
        Aktion: ``sessions-finish`` für einen aktuellen Lauf ausführen.
        Erwartung: der alte Eintrag bleibt erhalten (Worktree-Anhang).
        Fehlerfall: eine fortsetzbare Arbeitskopie wird vergessen.
        """
        worktree = self.base / "worktrees" / "F1"
        worktree.mkdir(parents=True)
        old = int(time.time()) - 40 * 86400
        self.registry().observe(
            session="ses_wt", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=old,
            worktree_path=str(worktree), package_id="F1",
            branch="feature/test/f1")
        self.registry().observe(
            session="ses_neu", project=str(self.project), name="proj",
            run_id="lauf-neu", agent="vibe", harness="opencode")

        result = self.sessions_finish("lauf-neu", "finished")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        sessions = {item["session"] for item in self.overview()}
        self.assertIn("ses_wt", sessions,
                      "Alter Eintrag mit existierendem Worktree wurde entfernt")

    def test_aging_prune_removes_old_entries_whose_worktree_is_gone(self):
        """Vorbedingung: alter Eintrag mit ``worktree_path`` auf ein nicht
        mehr existierendes Verzeichnis.
        Aktion: ``sessions-finish`` für einen aktuellen Lauf ausführen.
        Erwartung: der Eintrag ist entfernt (kein noch existierender Anhang).
        Fehlerfall: verwaiste Session bleibt stehen.
        """
        old = int(time.time()) - 40 * 86400
        self.registry().observe(
            session="ses_weg", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=old,
            worktree_path=str(self.base / "worktrees" / "weg"),
            package_id="F1", branch="feature/test/f1")
        self.registry().observe(
            session="ses_neu", project=str(self.project), name="proj",
            run_id="lauf-neu", agent="vibe", harness="opencode")

        result = self.sessions_finish("lauf-neu", "finished")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        sessions = {item["session"] for item in self.overview()}
        self.assertNotIn("ses_weg", sessions,
                         "Eintrag mit fehlendem Worktree blieb stehen")


# ------------------------------------------------------- T-G5 branch collisions
class BranchCollisionTest(unittest.TestCase):
    """AK T-G5: Kollisionsprüfung berücksichtigt Remotes und Worktrees."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project = self.base / "proj"
        real_git(self.base, "init", "-q", "-b", "main", "proj")
        real_git(self.project, "config", "user.name", "Test")
        real_git(self.project, "commit", "--allow-empty", "-q", "-m", "init")
        (self.project / ".vibe").mkdir()
        # Standardmuster feature/<owner>/<id>; Owner ist der Git-Benutzer.
        (self.project / ".vibe" / "project.env").write_text(
            'PACKAGE_BRANCH_PATTERN="feature/{owner}/{id}"\n',
            encoding="utf-8")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] F1 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8")
        real_git(self.project, "add", "-A")
        real_git(self.project, "commit", "-q", "-m", "tickets")
        sys.path.insert(0, str(BIN))
        try:
            import vibe_packages  # noqa: PLC0415
        finally:
            sys.path.remove(str(BIN))
        self.packages = vibe_packages

    def test_remote_only_branch_collision_gets_a_suffix(self):
        """Vorbedingung: ``refs/remotes/origin/feature/test/f1`` existiert,
        aber kein lokaler Branch gleichen Namens.
        Aktion: ``package_branch_name(project, "F1")``.
        Erwartung: der nächste freie Name mit Suffix (``…-2``).
        Fehlerfall: derselbe Name wird erneut vergeben (Kollision mit dem
        Fernstand).
        """
        real_git(self.project, "update-ref",
                 "refs/remotes/origin/feature/test/f1", "HEAD")

        name = self.packages.package_branch_name(self.project, "F1")

        self.assertEqual("feature/test/f1-2", name)

    def test_branch_checked_out_in_a_worktree_is_a_collision(self):
        """Vorbedingung: ``feature/test/f1`` ist in einer zweiten
        Arbeitskopie ausgecheckt (der lokale Branch existiert dadurch).
        Aktion: ``package_branch_name(project, "F1")``.
        Erwartung: ein freier Name mit Suffix, nicht der belegte Branch.
        Fehlerfall: der belegte Branch wird wiederverwendet.
        """
        real_git(self.project, "branch", "feature/test/f1")
        second = self.base / "second"
        real_git(self.project, "worktree", "add", "-q", str(second),
                 "feature/test/f1")

        name = self.packages.package_branch_name(self.project, "F1")

        self.assertNotEqual("feature/test/f1", name)
        self.assertTrue(name.startswith("feature/test/f1-"), name)


# --------------------------------------------- T-W2/T-G1 runner reconnect path
class RunnerFixtureMixin:
    """AP9-Läuferfixture mit Registry-Zugriff."""

    def _fixture(self):
        from tests.unit.test_github_runner import AP9WiringFixture
        return AP9WiringFixture

    def setUp(self):
        self.fixture = self._fixture()
        self.fixture.setUp(self)

    def tearDown(self):
        self.fixture.tearDown(self)

    def run_runner(self, project, **extra):
        return self.fixture.run_runner(self, project, **extra)

    def env(self, project, **extra):
        return self.fixture.env(self, project, **extra)

    def log(self, project=None):
        return self.fixture.log(self, project)

    def make_project(self, name="proj"):
        from tests.unit.test_github_runner import FEEDBACK_ONE
        return self.fixture.make_project(
            self, feedback=FEEDBACK_ONE, name=name)

    def register_worktree(self, project, path, branch="feature/test/f1",
                          pid="F1"):
        return runs_module().WorktreeRegistry(str(self.runtime)).register(
            project=str(project), id=pid, branch=branch, path=str(path),
            base_commit=real_git_out(project, "rev-parse", "HEAD"))

    def called_dirs(self):
        if not self.calls.exists():
            return []
        rows = []
        for line in self.calls.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] == "F1":
                rows.append(parts[1])
        return rows

    @property
    def calls(self):
        return self.root / "calls.jsonl"


class ReconnectTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-W2: gültiger Registry-Eintrag wird wiederverwendet."""

    def test_valid_registered_worktree_is_reused_instead_of_a_new_one(self):
        """Vorbedingung: offenes Paket F1; ein gültiger Worktree mit Branch
        ``feature/test/f1`` ist angelegt und in der Registry eingetragen.
        Aktion: Läufer (ohne GitHub, lokaler Merge-Pfad) ausführen.
        Erwartung: Der Agent läuft in genau diesem Worktree (calls.jsonl);
        es entsteht keine zweite Arbeitskopie; nach dem lokalen Abschluss
        sind Worktree, Branch und Registry-Eintrag entfernt.
        Fehlerfall: neuer mktemp-Worktree statt Reconnect oder veralteter
        Registry-Eintrag bleibt stehen.
        """
        project = self.make_project()
        path = self.runtime / "worktrees" / "reconnect-F1"
        path.parent.mkdir(parents=True, exist_ok=True)
        real_git(project, "worktree", "add", "-q", "-b", "feature/test/f1",
                 str(path), "HEAD")
        self.register_worktree(project, path)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        used = self.called_dirs()
        self.assertEqual([str(path)], used,
                         "Der registrierte Worktree wurde nicht verwendet: "
                         + repr(used) + "\n" + self.log(project))
        self.assertFalse(path.exists(), "Worktree wurde nicht entfernt")
        self.assertNotEqual(
            0, real_git(project, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Branch wurde nicht entfernt")
        self.assertEqual([], runs_module().WorktreeRegistry(
            str(self.runtime)).all(), "Registry-Eintrag blieb stehen")

    def test_stale_registry_entry_is_discarded_and_a_fresh_worktree_is_used(self):
        """Vorbedingung: Registry-Eintrag zeigt auf ein nicht mehr
        existierendes Verzeichnis.
        Aktion: Läufer ausführen.
        Erwartung: Der Läufer ignoriert den veralteten Eintrag, legt einen
        neuen Worktree an und das Paket schließt ab; der alte Pfad wird
        nicht verwendet.
        Fehlerfall: Lauf scheitert am fehlenden Pfad oder nutzt ihn.
        """
        project = self.make_project()
        stale = self.runtime / "worktrees" / "veraltet-F1"
        self.register_worktree(project, stale)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        used = self.called_dirs()
        self.assertTrue(used, "Kein Agentenlauf gefunden")
        self.assertNotIn(str(stale), used,
                         "Der veraltete Worktree wurde verwendet")


class RunnerSessionPersistTest(RunnerFixtureMixin, unittest.TestCase):
    """AK T-S1: Der Läufer persistiert den Endzustand auf der Session."""

    def test_final_state_survives_a_missing_run_record(self):
        """Vorbedingung: lokales Projekt ohne GitHub; der Läufer schließt F1
        erfolgreich ab und erfasst die Session.
        Aktion: ``runs.json`` entfernen (Lauf weggealtert) und
        ``session_overview`` lesen.
        Erwartung: Die Session zeigt ``finished``/„abgeschlossen“ statt
        ``unknown`` (Endzustand wurde beim Laufende persistiert).
        Fehlerfall: Zustand geht mit dem Laufregister verloren.
        """
        project = self.make_project()

        result = self.run_runner(project)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        sessions_path = self.runtime / "sessions.json"
        self.assertTrue(sessions_path.is_file(),
                        "Der Läufer hat keine Session registriert")
        data = json.loads(sessions_path.read_text(encoding="utf-8"))
        self.assertTrue(data.get("sessions"), data)
        (self.runtime / "runs.json").unlink()

        overview = runs_module().session_overview(str(self.runtime))

        self.assertEqual(1, len(overview), overview)
        self.assertEqual("finished", overview[0].get("state"), overview[0])
        self.assertEqual("abgeschlossen", overview[0].get("state_label"),
                         overview[0])


class CleanupWiringTest(unittest.TestCase):
    """AK T-G4: Der Läufer prüft Arbeitskopien vor dem Branch-Löschen."""

    def test_cleanup_consults_worktree_list_before_deleting_the_branch(self):
        """Vorbedingung: ``bin/vibe-run.sh``.
        Aktion: Quelltext der Aufräumfunktion prüfen.
        Erwartung: ``git worktree list --porcelain`` wird ausgewertet; ein
        noch ausgecheckter Branch erzeugt eine verständliche Meldung
        („Arbeitskopie“), und gelöscht wird mit ``branch -d``.
        Fehlerfall: Branch wird trotz Arbeitskopie gelöscht oder die Meldung
        ist unverständlich.
        """
        text = (BIN / "vibe-run.sh").read_text(encoding="utf-8")
        self.assertIn("worktree list --porcelain", text)
        self.assertIn("branch -d", text)
        self.assertRegex(text, r"(?i)arbeitskopie")


# ------------------------------------------- T-W1 resume environment hints
from tests.unit.test_sessions_cli import SessionsCliFixture  # noqa: E402


class SessionResumeHintsTest(SessionsCliFixture):
    """AK T-W1: ``vibe sessions resume`` reicht den Worktree-Anhang weiter.

    Nutzt die echte CLI mit einer aufzeichnenden tmux-Attrappe. Der Export
    landet im Startbefehl des Läufers; es wird kein Modell gestartet.
    """

    def seed_with_worktree(self):
        worktree = self.root / "worktrees" / "F1"
        worktree.mkdir(parents=True)
        entry = self.session("ses_wt", first=100, last=100)
        entry.update({
            "worktree_path": str(worktree),
            "package_id": "F1",
            "branch": "feature/test/f1",
        })
        self.seed_sessions([entry])

    def exports(self, name):
        values = []
        for command in self.new_session_commands():
            values.extend(re.findall(
                r"%s=([^\s;\"']+)" % re.escape(name), command))
        return values

    def test_resume_exports_the_worktree_package_and_branch(self):
        """Vorbedingung: Session mit Worktree-Anhang im Register.
        Aktion: ``vibe sessions resume proj --session ses_wt``.
        Erwartung: Der Startbefehl exportiert ``VIBE_RESUME_WORKTREE``,
        ``VIBE_RESUME_PACKAGE`` und ``VIBE_RESUME_BRANCH`` mit den
        gespeicherten Werten; ``VIBE_CONTINUE_SESSION`` bleibt gesetzt.
        Fehlerfall: Hints fehlen; der Agent landet wieder im falschen Baum.
        """
        self.seed_with_worktree()

        result = self.cli("sessions", "resume", "proj", "--session", "ses_wt")

        self.assertEqual(0, result.returncode, self.output(result))
        self.assertEqual([str(self.root / "worktrees" / "F1")],
                         self.exports("VIBE_RESUME_WORKTREE"),
                         self.output(result))
        self.assertEqual(["F1"], self.exports("VIBE_RESUME_PACKAGE"),
                         self.output(result))
        self.assertEqual(["feature/test/f1"],
                         self.exports("VIBE_RESUME_BRANCH"),
                         self.output(result))
        self.assertEqual(["ses_wt"], self.continue_exports(),
                         self.output(result))

    def test_resume_hints_are_quoted_for_the_shell(self):
        """Vorbedingung: Session mit ``worktree_path`` mit Leerzeichen und
        einem ``branch``-Wert mit Shell-Sonderzeichen (Semikolon/Leerzeichen);
        ``vibe sessions resume`` ruft ``cmd_run(..., resume_worktree=…,
        resume_branch=…)`` auf.
        Aktion: Resume über die echte CLI mit aufzeichnender tmux-Attrappe.
        Erwartung: Der exportierte Innenteil enthält die Werte in
        ``shlex.quote``-Form (z. B. ``'…x y'``), sodass Leerzeichen und
        Semikolon nicht als Befehlstrenner wirken; der ungeschützte
        ``VIBE_RESUME_BRANCH=<wert>;``-String kommt nicht vor.
        Fehlerfall: Unquotierte Werte zerlegen den Startbefehl oder führen
        Fremdkommandos aus.
        """
        worktree = self.root / "worktrees" / "x y"
        worktree.mkdir(parents=True)
        branch = "feature/test/f1;echo PWNED"
        entry = self.session("ses_q", first=100, last=100)
        entry.update({
            "worktree_path": str(worktree),
            "package_id": "F1",
            "branch": branch,
        })
        self.seed_sessions([entry])

        result = self.cli("sessions", "resume", "proj", "--session", "ses_q")

        self.assertEqual(0, result.returncode, self.output(result))
        command = "\n".join(self.new_session_commands())
        self.assertIn(shlex.quote(str(worktree)), command,
                      "Worktree-Pfad ist nicht shell-quotiert: " + command)
        self.assertIn(shlex.quote(branch), command,
                      "Branch ist nicht shell-quotiert: " + command)
        self.assertNotIn("VIBE_RESUME_BRANCH=" + branch + ";", command,
                         "Unquotierter Branch bricht den Startbefehl: "
                         + command)
        # Der bestehende Export-Parser bleibt für einfache Werte nutzbar.
        self.assertEqual(["F1"], self.exports("VIBE_RESUME_PACKAGE"))

    def test_runner_contains_a_logged_fallback_for_a_closed_package(self):
        """Vorbedingung: Läuferquelltext.
        Aktion: nach der Behandlung der Resume-Hinweise suchen.
        Erwartung: ``VIBE_RESUME_PACKAGE`` wird ausgewertet und ein Fallback
        (Paket geschlossen) ist vorgesehen/protokolliert.
        Fehlerfall: Hints werden ignoriert; ein geschlossenes Paket blockiert
        die Fortsetzung ohne Erklärung.
        """
        text = (BIN / "vibe-run.sh").read_text(encoding="utf-8")
        self.assertIn("VIBE_RESUME_PACKAGE", text)
        self.assertRegex(
            text,
            r"VIBE_RESUME_PACKAGE[\s\S]{0,4000}?(geschlossen|normal|Rückfall|Fallback)",
            "Kein protokollierter Rückfall für ein geschlossenes Paket")


# ------------------------------------- T-G1/T-W1 `vibe package close` CLI
class _PullHandler(BaseHTTPRequestHandler):
    """REST-Fake: gemergter/nicht gemergter PR."""

    def log_message(self, fmt, *args):
        pass

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.server.requests.append({"method": "GET", "path": self.path})
        pr = {"number": 42, "state": "closed" if self.server.merged else "open",
              "merged": bool(self.server.merged),
              "merged_at": "2026-01-01T00:00:00Z" if self.server.merged else None,
              "merge_commit_sha": self.server.tip,
              "html_url": self.server.pr_url}
        if re.search(r"/pulls/\d+$", self.path):
            self._respond(200, pr)
            return
        if re.search(r"/pulls(\?|$)", self.path):
            self._respond(200, [pr])
            return
        self._respond(404, {"message": "Not Found"})


class PullFakeServer:
    def __init__(self, merged=True):
        self.requests = []
        self.merged = merged
        self.tip = ""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.pr_url = "http://127.0.0.1:%d/pull/42" % self.port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _PullHandler)
        self.httpd.requests = self.requests
        self.httpd.merged = merged
        self.httpd.pr_url = self.pr_url
        self.httpd.tip = ""
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class PackageCloseCliTest(unittest.TestCase):
    """AK T-G1/T-W1: ``vibe package close`` als zweite Abschlussphase."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        (self.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.runtime.mkdir()
        self.state.mkdir()
        (self.root / "tmp").mkdir()
        self.project = self.root / "proj"
        self.bare = self.root / "origin.git"
        self._build_project()
        self.tip = self._simulate_squash_merge()

    # ---------------------------------------------------------------- setup
    def write_github_env(self, api="", enabled=True):
        """Schreibt GITHUB_ENABLED/API je Testfall in die Projektdatei."""
        text = ('TYPE=generic\n'
                'GITHUB_ENABLED="%s"\n'
                'GITHUB_REPO="owner/name"\n'
                'GITHUB_BASE="main"\n' % ("1" if enabled else ""))
        if api:
            text += 'GITHUB_API="%s"\n' % api
        (self.project / ".vibe" / "project.env").write_text(
            text, encoding="utf-8")

    def env(self, api="", enabled=True, **extra):
        # Die Werte müssen wirksam werden: ``vibe package close`` liest die
        # Projektdatei, nicht die Prozessumgebung. Ohne GITHUB_API würde der
        # Befehl die echte api.github.com kontaktieren.
        self.write_github_env(api=api, enabled=enabled)
        env = fresh_env(self.root)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.root / "_toolchain"),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(
                self.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(
                self.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "TMPDIR": str(self.root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def _build_project(self):
        real_git(self.root, "init", "-q", "-b", "main", "proj")
        (self.project / ".vibe").mkdir(exist_ok=True)
        self.write_github_env(api="", enabled=True)
        # GH-48: Der Abschluss lebt im Ticketspeicher; der Worktree traegt nur
        # die sichtbare Einzeldatei TICKET-F1.json. Der Speicher ist
        # Laufzeitstand und bleibt deshalb unversioniert.
        (self.project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [{
                "id": "F1", "title": "Testpaket", "type": "feedback",
                "state": "waiting-merge", "description": "Test",
                "github": None, "pr_url": "", "commit": "", "test": "",
                "blocked_reason": "", "waiting_note": "PR offen",
                "priority": "", "dependencies": [],
                "created": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00",
            }]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        real_git(self.project, "add", "-A")
        real_git(self.project, "commit", "-q", "-m", "Ausgangsstand")
        real_git(self.root, "init", "-q", "--bare", "origin.git")
        real_git(self.bare, "symbolic-ref", "HEAD", "refs/heads/main")
        real_git(self.project, "remote", "add", "origin", "file://" + str(self.bare))
        real_git(self.project, "push", "-q", "-u", "origin", "main")

    def _worktree(self):
        path = self.runtime / "worktrees" / "proj-F1"
        path.parent.mkdir(parents=True, exist_ok=True)
        real_git(self.project, "worktree", "add", "-q", "-b", "feature/test/f1",
                 str(path), "HEAD")
        (path / "docs" / "features").mkdir(parents=True)
        (path / "docs" / "features" / "F1.md").write_text(
            "# F1\n", encoding="utf-8")
        (path / "docs" / "reviews").mkdir(parents=True)
        (path / "docs" / "reviews" / "F1-review-1.md").write_text(
            "# Review\n\nVerdict: PASS\n", encoding="utf-8")
        real_git(path, "add", "-A")
        real_git(path, "commit", "-q", "-m", "F1: Nachweis")
        # GH-48: Der Abschluss steht in der Laufzeitdatei; sie wird nie
        # committet (deshalb erst nach dem Commit geschrieben).
        (path / "TICKET-F1.json").write_text(
            json.dumps({
                "id": "F1", "title": "Testpaket", "type": "feedback",
                "state": "done", "description": "Test",
                "github": None, "pr_url": "", "commit": "abc1234",
                "test": "test_ap4", "blocked_reason": "",
                "waiting_note": "", "priority": "", "dependencies": [],
                "created": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00",
            }, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return path

    def _simulate_squash_merge(self):
        seed = self.root / "squash"
        real_git(self.root, "clone", "-q", "file://" + str(self.bare), str(seed))
        (seed / "impl-F1.txt").write_text("F1\n", encoding="utf-8")
        real_git(seed, "add", "-A")
        real_git(seed, "-c", "user.name=Test", "-c",
                 "user.email=test@example.invalid", "commit", "-q", "-m",
                 "F1: squash merge")
        real_git(seed, "push", "-q", "origin", "main")
        return real_git_out(self.bare, "rev-parse", "main")

    def register(self, path, pr_url):
        return runs_module().WorktreeRegistry(str(self.runtime)).register(
            project=str(self.project), id="F1", branch="feature/test/f1",
            path=str(path), base_commit=real_git_out(self.project, "rev-parse",
                                                     "HEAD"),
            pr_url=pr_url, session="ses_wt", state="waiting")

    def observe_session(self, path, now=None):
        return runs_module().SessionRegistry(str(self.runtime)).observe(
            session="ses_wt", project=str(self.project), name="proj",
            run_id="", agent="vibe", harness="opencode", now=now,
            worktree_path=str(path), package_id="F1",
            branch="feature/test/f1")

    def close(self, api, enabled=True, extra=None):
        env = self.env(api=api, enabled=enabled,
                       GITHUB_TOKEN="ap4-close-token", **(extra or {}))
        return subprocess.run(
            [sys.executable, str(CLI), "package", "close", "proj", "F1"],
            cwd=str(self.root), env=env, capture_output=True, text=True,
            timeout=120, check=False)

    # ---------------------------------------------------------------- cases
    def test_merged_pr_syncs_notes_cleans_up_and_forgets_sessions(self):
        """Vorbedingung: registrierter Worktree, Session-Anhang, PR laut REST
        gemergt (``state=closed``, ``merged=true``), Fernspitze enthält den
        Squash-Commit.
        Aktion: ``vibe package close proj F1``.
        Erwartung: Exit 0; lokaler Integrationsstand erreicht die Fernspitze
        samt Paketänderung; das Ticket steht im Projekt-Speicher auf
        ``state=done`` mit Commit und Test; Worktree, Branch, Registry-Eintrag
        und Session sind entfernt.
        Fehlerfall: nichts wird aufgeräumt oder der Nachweis fehlt.
        """
        server = PullFakeServer(merged=True).start()
        self.addCleanup(server.close)
        path = self._worktree()
        self.register(path, server.pr_url)
        self.observe_session(path)

        result = self.close(server.base)

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertTrue(server.requests,
                        "Der Fake wurde nicht kontaktiert; Verdacht auf "
                        "echte GitHub-API: " + output)
        self.assertFalse(path.exists(), "Worktree wurde nicht entfernt: " + output)
        self.assertNotEqual(
            0, real_git(self.project, "rev-parse", "--verify",
                        "refs/heads/feature/test/f1", check=False).returncode,
            "Branch wurde nicht entfernt")
        registry = runs_module().WorktreeRegistry(str(self.runtime))
        self.assertIsNone(registry.get(str(self.project), "F1"))
        self.assertIsNone(
            runs_module().SessionRegistry(str(self.runtime)).get("ses_wt"),
            "Session des geschlossenen Worktrees wurde nicht vergessen")
        self.assertEqual(
            0, real_git(self.project, "cat-file", "-e", "HEAD:impl-F1.txt",
                        check=False).returncode,
            "Der Squash-Commit wurde nicht in den Integrationsstand geholt")
        document = json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))
        ticket = {item["id"]: item for item in document["tickets"]}["F1"]
        self.assertEqual("done", ticket["state"], ticket)
        self.assertEqual("abc1234", ticket["commit"], ticket)
        self.assertEqual("test_ap4", ticket["test"], ticket)

    def test_unmerged_pr_fails_without_any_change(self):
        """Vorbedingung: wie oben, aber REST meldet ``merged=false``.
        Aktion: ``vibe package close`` ausführen.
        Erwartung: Exit ≠ 0 mit verständlicher Meldung; Worktree, Branch,
        Registry-Eintrag und Session bleiben; der Projektstand ändert sich
        nicht.
        Fehlerfall: Abschluss ohne gemergten PR.
        """
        server = PullFakeServer(merged=False).start()
        self.addCleanup(server.close)
        path = self._worktree()
        self.register(path, server.pr_url)
        self.observe_session(path)
        before = real_git_out(self.project, "rev-parse", "HEAD")

        result = self.close(server.base)

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output.lower(), r"merge|gemergt|zusammengef",
                         "Meldung nennt den fehlenden Merge nicht: " + output)
        self.assertTrue(path.exists(), "Worktree wurde trotz fehlendem Merge entfernt")
        self.assertEqual(0, real_git(self.project, "rev-parse", "--verify",
                                     "refs/heads/feature/test/f1",
                                     check=False).returncode)
        self.assertIsNotNone(
            runs_module().WorktreeRegistry(str(self.runtime)).get(
                str(self.project), "F1"))
        self.assertIsNotNone(
            runs_module().SessionRegistry(str(self.runtime)).get("ses_wt"))
        self.assertEqual(before, real_git_out(self.project, "rev-parse", "HEAD"))

    def test_without_an_active_github_link_close_refuses_clearly(self):
        """Vorbedingung: keine aktive GitHub-Verknüpfung (GITHUB_ENABLED leer).
        Aktion: ``vibe package close`` ausführen.
        Erwartung: Exit ≠ 0; Meldung nennt die fehlende Verknüpfung; keine
        Änderungen an Worktree/Registry/Session.
        Fehlerfall: Close verhält sich trotzdem wie ein Merge-Abschluss.
        """
        path = self._worktree()
        self.register(path, "")
        self.observe_session(path)

        result = self.close("", enabled=False)

        output = result.stdout + result.stderr
        self.assertNotEqual(0, result.returncode, output)
        self.assertRegex(output, r"GitHub|verknüpf",
                         "Meldung nennt die fehlende Verknüpfung nicht: " + output)
        self.assertTrue(path.exists())
        self.assertIsNotNone(
            runs_module().WorktreeRegistry(str(self.runtime)).get(
                str(self.project), "F1"))


# ===========================================================================
# (Oberflächen): T-G0, T-W1, T-G1, T-S1 im Web-UI
# ===========================================================================

import json
import re
import unittest
from pathlib import Path

from tests.unit.test_sessions_api import Ap19SessionsApiFixture
from tests.unit.test_web_routes import DashboardFixture

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

    def test_nova_work_tab_has_no_manual_package_close_action(self):
        """Vorbedingung: Arbeiten-Reiter in ``nova-project.js``.
        Aktion: Oberflächenquelltext auf Abschluss-Steuerelemente prüfen.
        Erwartung (GH-82): kein „Paket abschließen“, kein
        ``package-close``/``ticket-close`` und kein ``/api/package``-Aufruf
        aus der Oberfläche. Der Endpunkt bleibt im Backend verfügbar und
        wird dort separat geprüft.
        Fehlerfall: die Oberfläche bietet weiterhin manuelles Schließen.
        """
        self.assertNotIn("Paket abschließen", self.text)
        self.assertNotIn("package-close", self.text)
        self.assertNotIn("ticket-close", self.text)
        self.assertNotIn("/api/package", self.text,
                         "Die Nova-Oberfläche ruft den Runner-Endpunkt direkt "
                         "auf")
        backend = WEB.read_text(encoding="utf-8")
        self.assertIn("/api/package", backend,
                      "Der Runner-Endpunkt fehlt im Backend")


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


# ===========================================================================
# Read-only Einweg-Transport von ``.vibe/project.env``
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

MODULE = REPO / "bin" / "vibe_packages.py"

ENV_TEXT = (
    "TYPE=generic\n"
    'VERIFY_QUICK="true"\n'
    'VERIFY_PACKAGE="true"\n'
)

BASELINE_TEXT = (
    "{\n"
    '  "version": 1,\n'
    '  "min_tests": 1,\n'
    '  "envs": {}\n'
    "}\n"
)


def load_module():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap5_transport_under_test", str(MODULE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ProjectEnvTransportTest(unittest.TestCase):
    """Echtes Projekt-Repository und echte Arbeitskopie."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        (self.project / "README.md").write_text("basis\n", encoding="utf-8")
        support.commit_all(self.project)
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()
        (self.project / ".vibe").mkdir()
        self.project_env = self.project / ".vibe" / "project.env"
        self.project_env.write_text(ENV_TEXT, encoding="utf-8")
        # GH-48: Ticket im Projektspeicher statt im Markdown-Ledger.
        support.write_ticket_store(self.project, [
            support.ticket_record("T1", "Paket", type="task")])
        self.worktree = self.add_worktree()
        self.assertFalse((self.worktree / ".vibe").exists(),
                         "Vorbedingung: Arbeitskopie kennt .vibe noch nicht")

    def add_worktree(self, name="wt"):
        worktree = self.root / name
        result = support.git(
            self.project, "worktree", "add", "-q", "-b", "branch-" + name,
            str(worktree), "HEAD",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.addCleanup(self.remove_worktree, worktree, name)
        return worktree

    def remove_worktree(self, worktree, name):
        support.git(self.project, "worktree", "remove", "--force", str(worktree))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(MODULE), *args],
            cwd=str(self.root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def copy_notes(self):
        return self.run_cli(
            "copy-notes", "--project", str(self.project),
            "--worktree", str(self.worktree),
        )

    def exclude_path(self):
        result = support.git(
            self.worktree, "rev-parse", "--git-path", "info/exclude"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else self.worktree / path

    def exclude_lines(self):
        path = self.exclude_path()
        if not path.is_file():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

    def chmod_effective(self):
        """True, wenn Schreibschutz auf diesem Dateisystem wirksam ist."""
        probe = self.root / ".chmod-probe"
        probe.write_text("x\n", encoding="utf-8")
        try:
            os.chmod(probe, 0o444)
            return not (stat.S_IMODE(probe.stat().st_mode) & 0o222)
        finally:
            probe.unlink()

    def test_project_env_is_copied_read_only_and_excluded(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env``; Arbeitskopie ohne
        ``.vibe``.
        Aktion: ``copy-notes --project … --worktree …`` ausführen.
        Erwartung: Exit 0; ``.vibe/project.env`` existiert im Worktree mit
        identischem Inhalt; Schreibbits sind nicht gesetzt (0444 best effort);
        die Git-Exclude enthält genau einmal ``.vibe/project.env``; die
        Ausgabe hat eine eigene OK-Zeile mit „project.env“.
        Fehlerfall: fehlende/abweichende Kopie, beschreibbare Datei, fehlender
        oder doppelter Exclude-Eintrag, fehlende OK-Zeile.
        """
        exclude = self.exclude_path()
        exclude.unlink(missing_ok=True)
        self.assertFalse(exclude.exists(), "Vorbedingung: Exclude fehlt")

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        copied = self.worktree / ".vibe" / "project.env"
        self.assertTrue(copied.is_file(), "project.env wurde nicht kopiert")
        self.assertEqual(copied.read_text(encoding="utf-8"), ENV_TEXT)
        if self.chmod_effective():
            mode = stat.S_IMODE(copied.stat().st_mode)
            self.assertEqual(0, mode & 0o222,
                             "Die Kopie ist beschreibbar (Modus %o)" % mode)
        self.assertTrue(exclude.is_file(), "Exclude-Datei wurde nicht angelegt")
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertTrue(
            any("OK:" in line and "project.env" in line
                for line in result.stdout.splitlines()),
            "Eigene OK-Zeile für den Transport fehlt:\n" + result.stdout,
        )

    def test_missing_project_env_creates_no_vibe_folder_and_no_exclude(self):
        """Vorbedingung: Projekt ohne ``.vibe/project.env`` (aber mit
        ``.vibe/_secrets.env``); Arbeitskopie ohne ``.vibe``.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Exit 0; im Worktree entsteht kein ``.vibe/``; die
        Git-Exclude enthält keinen ``.vibe/project.env``-Eintrag; keine
        Transport-OK-Zeile.
        Fehlerfall: leerer Ordner, Exclude-Eintrag oder falsche Erfolgsmeldung.
        """
        (self.project / ".vibe" / "_secrets.env").write_text(
            "GEHEIM=1\n", encoding="utf-8"
        )
        self.project_env.unlink()

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.worktree / ".vibe").exists(),
                         "Ohne project.env darf kein .vibe/ entstehen")
        self.assertNotIn(".vibe/project.env", self.exclude_lines())
        self.assertFalse(
            any("OK:" in line and "project.env" in line
                for line in result.stdout.splitlines()),
            result.stdout,
        )

    def test_only_project_env_is_transported_never_secrets(self):
        """Vorbedingung: Projekt-``.vibe`` enthält ``project.env``,
        ``_secrets.env`` und eine weitere Datei.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Im Worktree liegt ``.vibe/project.env``; ``_secrets.env``
        und die weitere Datei fehlen.
        Fehlerfall: Geheimnis oder fremde Datei wird übertragen.
        """
        (self.project / ".vibe" / "_secrets.env").write_text(
            "GEHEIM=1\n", encoding="utf-8"
        )
        (self.project / ".vibe" / "notizen.txt").write_text(
            "nicht uebertragen\n", encoding="utf-8"
        )

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.worktree / ".vibe"
        self.assertTrue((target / "project.env").is_file())
        self.assertFalse((target / "_secrets.env").exists(),
                         "Geheimnisse dürfen nie transportiert werden")
        self.assertFalse((target / "notizen.txt").exists())

    def test_copy_and_exclude_are_idempotent(self):
        """Vorbedingung: ``copy-notes`` lief bereits einmal.
        Aktion: Projekt-``project.env`` ändern und ``copy-notes`` erneut
        ausführen.
        Erwartung: Die Worktree-Kopie enthält den neuen Projektstand; der
        Exclude-Eintrag bleibt genau einmal vorhanden.
        Fehlerfall: doppelter Exclude-Eintrag oder alter Inhalt.
        """
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        updated = ENV_TEXT + "GEAENDERT=ja\n"
        self.project_env.write_text(updated, encoding="utf-8")

        second = self.copy_notes()

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        copied = self.worktree / ".vibe" / "project.env"
        self.assertEqual(copied.read_text(encoding="utf-8"), updated)
        self.assertEqual(self.exclude_lines().count(".vibe/project.env"), 1,
                         self.exclude_lines())

    def test_sync_ticket_never_writes_the_project_env_back(self):
        """Vorbedingung: ``copy-notes`` hat die Datei transportiert; im
        Worktree liegt ein abgeschlossenes TICKET-T1.json, die Worktree-Kopie
        der project.env wurde lokal geändert. Der Projektstand ist autoritativ.
        Aktion: ``sync-ticket --project … --worktree … --id T1`` ausführen.
        Erwartung: Exit 0; die Projekt-``project.env`` bleibt byte-gleich; die
        Worktree-Kopie bleibt mit ihrem lokalen Inhalt liegen.
        Fehlerfall: Rückschreiben in das Projekt oder Löschen der Kopie.
        """
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        local = "TYPE=generic\nLOKAL=1\n"
        copied = self.worktree / ".vibe" / "project.env"
        os.chmod(copied, 0o644)
        copied.write_text(local, encoding="utf-8")
        revision = support.git(
            self.project, "rev-parse", "--short", "HEAD"
        ).stdout.strip()
        record = support.ticket_record(
            "T1", "Paket", type="task", state="done",
            commit=revision, test="test_t1")
        (self.worktree / "TICKET-T1.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        project_before = self.project_env.read_bytes()

        result = self.run_cli(
            "sync-ticket", "--project", str(self.project),
            "--worktree", str(self.worktree), "--id", "T1",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_env.read_bytes(), project_before,
                         "sync-ticket darf project.env nie zurückschreiben")
        self.assertEqual(copied.read_text(encoding="utf-8"), local,
                         "Die Worktree-Kopie muss liegen bleiben")

    # ---------------------------------- GH-46: kein verify-baseline-Transport
    def write_project_baseline(self, text=BASELINE_TEXT):
        path = self.project / ".vibe" / "verify-baseline"
        path.write_text(text, encoding="utf-8")
        return path

    def test_verify_baseline_is_not_transported_and_not_excluded(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env`` und
        ``.vibe/verify-baseline``; Arbeitskopie ohne ``.vibe``.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Exit 0; nur ``.vibe/project.env`` liegt in der Arbeitskopie,
        ``.vibe/verify-baseline`` fehlt dort vollständig; die Git-Exclude
        enthält ``.vibe/project.env`` genau einmal und keinen
        ``.vibe/verify-baseline``-Eintrag (die Baseline wird nicht
        transportiert, Agenten nutzen die committete Kopie aus dem Branch).
        Fehlerfall: Die lokale Baseline wird in die Arbeitskopie kopiert oder
        ausgeschlossen und überdeckt dort die committete Baseline.
        """
        exclude = self.exclude_path()
        exclude.unlink(missing_ok=True)
        self.write_project_baseline()

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.worktree / ".vibe"
        self.assertTrue((target / "project.env").is_file(),
                        "project.env muss weiterhin transportiert werden")
        self.assertEqual(
            (target / "project.env").read_text(encoding="utf-8"), ENV_TEXT
        )
        self.assertFalse(
            (target / "verify-baseline").exists(),
            "Die lokale Baseline darf die committete Baseline nicht überdecken",
        )
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertNotIn(".vibe/verify-baseline", lines,
                         "Kein Exclude-Eintrag für die nicht transportierte "
                         "Baseline: %r" % (lines,))

    def test_repeated_copy_keeps_the_baseline_out_of_the_worktree(self):
        """Vorbedingung: ``copy-notes`` lief bereits einmal; Projekt und
        Baseline existieren weiter, die Projekt-Baseline wurde geändert.
        Aktion: ``copy-notes`` erneut ausführen.
        Erwartung: Exit 0; die Arbeitskopie enthält weiterhin keine
        ``.vibe/verify-baseline``; der Exclude-Eintrag für ``project.env``
        bleibt genau einmal vorhanden und es entsteht kein Baseline-Eintrag.
        Fehlerfall: Ein zweiter Lauf schleust die Baseline doch ein oder
        dupliziert Exclude-Einträge.
        """
        self.write_project_baseline()
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        updated = (
            "{\n"
            '  "version": 1,\n'
            '  "min_tests": 2,\n'
            '  "envs": {}\n'
            "}\n"
        )
        self.write_project_baseline(updated)

        second = self.copy_notes()

        self.assertEqual(second.returncode, 0,
                         second.stdout + second.stderr)
        self.assertFalse(
            (self.worktree / ".vibe" / "verify-baseline").exists(),
            "Ein zweiter Lauf darf die Baseline nicht transportieren",
        )
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertNotIn(".vibe/verify-baseline", lines, lines)


if __name__ == "__main__":
    unittest.main()
