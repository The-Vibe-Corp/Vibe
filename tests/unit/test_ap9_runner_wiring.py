"""Abnahme AP9: Verkabelung der GitHub-Subkommandos im Paketläufer.

Geprüft wird die fachliche Verkabelung in ``bin/vibe-run.sh`` (nicht die
Subkommandos selbst — die deckt ``test_ap9_runner_github.py`` ab):

* ``github-pull`` läuft nach der Paketauswahl und vor dem Erfassen des
  Paketbases (``PACKAGE_BASE``/Arbeitskopie); ein Fehlschlag erzeugt nur
  einen HINWEIS und blockiert das Paket nicht (AP9: „Vor jedem neuen AP
  den Haupt-Branch aktualisieren").
* ``github-complete`` läuft erst nach grüner Abschlussschranke und vor
  ``merge_package``; ein Fehlschlag erzeugt nur einen HINWEIS, das Paket
  wird trotzdem lokal gemergt (AP9: „Nach AP-Abschluss automatisch einen
  Merge-Request stellen, ohne das Paket an GitHub zu hängen").
* Ein erfolgreicher github-pull läuft unsichtbar weiter (keine HINWEIS-
  Zeile, kein Block).

Der echte Läufer läuft in einer Fake-Toolchain (Muster
``tests/unit/test_b9_self_repair.py`` / ``test_runner_package_gates.py``):
nachgebildete Agenten, lokale Bare-Repositories über ``file://``, keine
Modellaufrufe, kein Netz außer 127.0.0.1-Verweigerungen, keine
produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_ap9_runner_wiring -v
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=1
"""

FEEDBACK_ONE = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

DEAD_API = "http://127.0.0.1:9"  # Loopback ohne Dienst: schnelle Verweigerung

GIT_IDENTITY = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *args):
    return support.git(cwd, *args)


class AP9WiringFixture(unittest.TestCase):
    """Isolierter ``bin/vibe-run.sh`` mit nachgebildeten Agenten."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        # install_runner kennt die GitHub-Verkabelung nicht; das Subkommando-
        # Modul gehört trotzdem in die Fake-Toolchain, damit der Läufer die
        # zu prüfenden Aufrufe wirklich ausführen kann (Muster: B6-Test,
        # der die Harness-Module nachkopiert).
        (self.tool_bin / "vibe_github.py").write_text(
            (support.BIN / "vibe_github.py").read_text(encoding="utf-8"),
            encoding="utf-8")
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()
        self.fakebin = support.install_fake_tools(self.root)

    # ------------------------------------------------------------ Projekt
    def make_project(self, env_extra="", feedback=FEEDBACK_ONE, name="proj"):
        project = self.root / name
        support.init_repo(project)
        support.write_project(
            project, PROJECT_ENV + env_extra, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        return project

    def link_origin(self, project, bare):
        """Verknüpft das Projekt mit einer lokalen Bare-Quelle (file://)."""
        result = git(project, "remote", "add", "origin", "file://" + str(bare))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def empty_bare(self, name):
        """Leere lokale Bare-Quelle mit main als Anfangsbranch.

        Kein Seed-Commit: Jede Fernhistorie entsteht aus dem Projektstand
        selbst, damit der Pull des Läufers fast-forward-fähig ist.
        """
        bare = self.root / "origin" / (name + ".git")
        bare.mkdir(parents=True, exist_ok=True)
        self.assertEqual(
            0, git(bare, "init", "-q", "--bare", "-b", "main").returncode)
        return bare

    def publish(self, project, bare, ahead_commits=0):
        """Setzt den Projektstand auf die Bare-Quelle und schiebt ihn
        optional um ``ahead_commits`` leere Fern-Commits voraus, die lokal
        wieder verworfen werden. Liefert den Fernstand (Rev-Parse)."""
        self.assertEqual(
            0, git(project, "push", "-q", "-u", "origin", "main").returncode)
        for step in range(ahead_commits):
            self.assertEqual(
                0, git(project, "commit", "--allow-empty", "-q", "-m",
                       "fernauftrag-%d" % step).returncode)
            self.assertEqual(
                0, git(project, "push", "-q", "origin", "main").returncode)
        remote_tip = git(bare, "rev-parse", "main").stdout.strip()
        if ahead_commits:
            self.assertEqual(
                0, git(project, "reset", "-q", "--hard",
                       "HEAD~%d" % ahead_commits).returncode)
            self.assertNotEqual(
                remote_tip, git(project, "rev-parse", "HEAD").stdout.strip(),
                "Vorbedingung: der Fernstand ist um Commits voraus")
        return remote_tip

    # -------------------------------------------------------------- Läufer
    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in ("AGENT", "MAX_PACKAGES", "MAX_RETRIES", "SANDBOX",
                    "SANDBOX_TOOLS", "VERIFY_FULL", "VERIFY_PACKAGE",
                    "GITHUB_TOKEN", "GH_TOKEN"):
            env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": project.name,
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "15",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_COUNTER": str(self.root / "counter"),
            "FAKE_CALLS": str(self.root / "calls.jsonl"),
        })
        env.update(GIT_IDENTITY)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=180, check=False,
        )

    def log(self, project=None):
        project = project or self.root / "proj"
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ---------------------------------------------------------- Assertions
    def log_index(self, log, needle):
        for index, line in enumerate(log.splitlines()):
            if needle in line:
                return index
        return -1


class PullWiringTest(AP9WiringFixture):
    """github-pull: Reihenfolge nach Auswahl, vor der Arbeitskopie."""

    def test_a_failing_github_pull_is_only_a_hint_and_does_not_block(self):
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\n'))
        # origin zeigt ins Leere: fetch scheitert, push scheitert später —
        # beide Subkommandos enden mit Exit 1.
        self.link_origin(project, self.root / "origin" / "fehlt.git")

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode,
                         "Ein GitHub-Fehlschlag darf den Lauf nicht abbrechen:\n"
                         + result.stdout + result.stderr)
        log = self.log(project)
        hint_pull = self.log_index(
            log, "HINWEIS: GitHub-Pull des Haupt-Branchs vor F1 fehlgeschlagen")
        header = self.log_index(log, "Arbeitspaket F1, Durchgang")
        hint_complete = self.log_index(
            log, "HINWEIS: GitHub-Abschluss für F1")
        fertig = self.log_index(log, "FERTIG")

        self.assertGreaterEqual(hint_pull, 0,
                                "Fehlender Pull erzeugt keinen HINWEIS:\n" + log)
        # Reihenfolge: HINWEIS vor dem Paketkopf — der Pull läuft nach der
        # Auswahl (er kennt F1) und vor dem Erfassen des Paketbases.
        self.assertLess(hint_pull, header, log)
        self.assertGreaterEqual(hint_complete, 0,
                                "Fehlender Abschluss erzeugt keinen HINWEIS:\n"
                                + log)
        self.assertLess(hint_complete, fertig,
                        "Der Merge läuft nach dem GitHub-Abschluss weiter:\n"
                        + log)
        self.assertNotIn("BLOCKIERT", log,
                         "Ein GitHub-Fehlschlag darf das Paket nicht "
                         "blockieren:\n" + log)
        # Das Paket ist trotzdem lokal gemergt:
        self.assertEqual(0, git(project, "cat-file", "-e",
                                "HEAD:impl-F1.txt").returncode,
                         "Das Paket wurde nicht in den Integrationsstand "
                         "gemergt:\n" + log)

    def test_a_successful_pull_updates_the_base_before_the_worktree(self):
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % DEAD_API))
        bare = self.empty_bare("aktuell")
        self.link_origin(project, bare)
        # Projektstand auf origin bringen; der Fernstand ist danach um einen
        # Commit voraus, der lokal wieder verworfen wurde.
        remote_tip = self.publish(project, bare, ahead_commits=1)

        result = self.run_runner(project)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        log = self.log(project)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Pull"),
            "Ein erfolgreicher Pull läuft unsichtbar weiter:\n" + log)
        # Der erste Paketcommit baut unmittelbar auf dem gezogenen
        # Fernstand auf: der Pull ist vor Arbeitskopie/Paketbase gelaufen.
        history = git(project, "log", "--format=%H %P %s",
                      "main").stdout.splitlines()
        parent = None
        for line in reversed(history):
            fields = line.split(" ", 2)
            if len(fields) >= 3 and fields[2].startswith("F1:"):
                # Ältester Paketcommit: sein Elternteil ist der Paketbase.
                parent = fields[1].split(" ")[0]
                break
        self.assertIsNotNone(parent, "Kein Paketcommit F1 gefunden:\n" + log)
        self.assertEqual(remote_tip, parent,
                         "Der Paketbase ist nicht der gezogene Fernstand:\n"
                         + log)


class CompleteWiringTest(AP9WiringFixture):
    """github-complete: erst nach grüner Schranke, vor dem Merge."""

    def test_complete_is_not_called_when_the_gate_is_red(self):
        project = self.make_project(
            env_extra=('GITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n'
                       'GITHUB_BASE="main"\nGITHUB_API="%s"\n' % DEAD_API))
        bare = self.empty_bare("schranke")
        self.link_origin(project, bare)
        self.publish(project, bare)
        # Der Agent beendet sich sauber, liefert aber keine Nachweise:
        # die Paketprüfung ist grün, die Abschlussschranke rot.

        result = self.run_runner(project, FAKE_MODE="no-artifacts")

        self.assertNotEqual(0, result.returncode,
                            "Eine rote Schranke darf nicht FERTIG melden")
        log = self.log(project)
        self.assertIn("Abschlussschranke für F1 nicht erfüllt", log, log)
        self.assertIn("BLOCKIERT", log, log)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Abschluss"),
            "github-complete darf erst nach grüner Schranke laufen:\n" + log)
        self.assertEqual(
            -1, self.log_index(log, "HINWEIS: GitHub-Pull"),
            "Der Pull läuft auch hier (unsichtbar) vor dem Paket:\n" + log)
        listing = git(project, "ls-tree", "--name-only", "HEAD",
                      "impl-F1.txt")
        self.assertEqual(0, listing.returncode, listing.stderr)
        self.assertEqual(
            "", listing.stdout.strip(),
            "Ohne grüne Schranke darf nichts in den Integrationsstand "
            "gemergt sein:\n" + log)


if __name__ == "__main__":
    unittest.main()
