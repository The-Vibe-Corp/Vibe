"""Abnahme B16 „Arbeitspakete für GitHub vorbereiten und als PR erstellen“
(Bug): Branch-Namen nach Repository-Regeln.

Die Testfälle leiten sich aus Arbeitspaket B16 (FEEDBACK.md) und SPEC.md ab,
unabhängig von einer Implementierung. Geprüft wird die neue Schnittstelle in
``bin/vibe_packages.py``:

* ``package_branch_name(project, pid, pattern=None) -> str``: erzeugt den
  Branch-Namen eines Arbeitspakets aus einem Muster. Das Muster kommt aus
  ``.vibe/project.env`` (``PACKAGE_BRANCH_PATTERN``), Standard ist
  ``feature/{owner}/{id}``. Platzhalter sind ``{owner}`` (kebab-case des
  lokalen ``git config user.name``, Fallback ``vibe``), ``{id}`` (kebab-case
  der Paket-ID) und ``{slug}`` (kebab-case des Tickettitels, auf höchstens 24
  Zeichen gekürzt, Fallback ``paket``).
* Das Ergebnis wird gegen die Repository-Regeln geprüft (nur Kleinbuchstaben,
  Ziffern, Bindestrich; ``/`` nur als Segmenttrenner; keine leeren Segmente,
  kein ``..``, kein Segmentende ``.lock``, Gesamtlänge ≤ 200, kein Segment
  mit führendem/abschließendem Bindestrich).
* Ein ungültiges Muster oder Ergebnis wirft ``ValueError`` mit klarer
  deutscher Meldung.
* Lokale Kollisionen (``refs/heads/<name>`` existiert) werden mit den
  Suffixen ``-2``, ``-3``, ... aufgelöst.
* Das Subkommando ``python3 bin/vibe_packages.py branch-name --project P
  --id ID`` druckt ausschließlich den Branch-Namen (eine stdout-Zeile) und
  endet mit 0; Fehler drucken ``FEHLT: <Grund>`` und enden mit 1.

Es werden keine Modellaufrufe und keine externen Dienste verwendet; alle
Projekte sind temporäre lokale Git-Repositories mit fester Test-Identität.

Run:

    python3 -m unittest tests.unit.test_b16_branch_name -v
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"

# Umgebungsvariablen, die für Prozessaufrufe isoliert werden müssen, damit
# weder die produktive Installation noch persönliche Konfigurationen erreicht
# werden (Muster tests/unit/test_ap11_priority.py).
ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
)

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def load_packages():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul (Rotphase: Lücken)."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b16_branch_under_test", str(PACKAGES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def real_git(cwd, *argv, check=True):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True, timeout=60,
    )


class BranchNameCase(unittest.TestCase):
    """Isolierte Umgebung mit temporären Projekten je Test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS"):
            os.environ.pop(key, None)
        os.environ.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.packages = load_packages()

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # ------------------------------------------------------------ Projekt
    def make_project(self, name="proj", env_extra="", feedback="",
                     tickets="", user_name=None):
        project = self.base / name
        project.mkdir(parents=True, exist_ok=True)
        real_git(project, "init", "-q", "-b", "main")
        real_git(project, "commit", "--allow-empty", "-q", "-m", "init")
        if user_name is not None:
            real_git(project, "config", "user.name", user_name)
        (project / ".vibe").mkdir(exist_ok=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n" + env_extra, encoding="utf-8")
        (project / "TICKETS.md").write_text(
            "# TICKETS\n\n" + tickets, encoding="utf-8")
        (project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + feedback, encoding="utf-8")
        return project

    def create_branch(self, project, name):
        real_git(project, "branch", name)

    def run_branch_name(self, project, pid):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE_STATE": str(self.state),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        env.update(GIT_IDENTITY)
        return subprocess.run(
            [sys.executable, str(PACKAGES), "branch-name",
             "--project", str(project), "--id", pid],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=120, check=False,
        )


# ------------------------------------------------------------- Standardmuster
class DefaultPatternTest(BranchNameCase):
    """AK: Branch-Namen entsprechen den Repository-Regeln (feature/...)."""

    def test_default_pattern_uses_sanitized_git_user_name(self):
        project = self.make_project(user_name="M0P")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/m0p/b16", name)

    def test_owner_is_kebab_cased_from_a_name_with_spaces_and_uppercase(self):
        project = self.make_project(user_name="Max Mustermann")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/max-mustermann/b16", name)

    def test_missing_user_name_falls_back_to_vibe(self):
        project = self.make_project(user_name=None)

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/vibe/b16", name)

    def test_package_id_is_kebab_cased(self):
        project = self.make_project(user_name="Test")

        name = self.packages.package_branch_name(project, "AP_19")

        self.assertEqual("feature/test/ap-19", name)


# ------------------------------------------------------ Konfigurierbares Muster
class PatternConfigurationTest(BranchNameCase):
    """AK: Muster ist über PACKAGE_BRANCH_PATTERN konfigurierbar."""

    def test_configured_pattern_with_slug_uses_the_ticket_title(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{owner}/{id}-{slug}"\n',
            feedback="- [ ] F1 Kurzer Titel\n  Beschreibung: Test\n",
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/test/f1-kurzer-titel", name)

    def test_slug_is_limited_to_24_characters(self):
        title = "Ein sehr langer Pakettitel mit vielen Woertern"
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{id}-{slug}"\n',
            feedback="- [ ] F1 " + title + "\n",
            user_name="Test",
        )
        full_slug = "ein-sehr-langer-pakettitel-mit-vielen-woertern"
        expected = full_slug[:24].rstrip("-")

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/f1-" + expected, name)
        self.assertLessEqual(len(expected), 24)

    def test_slug_falls_back_to_paket_without_a_title(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature/{id}-{slug}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "F1")

        self.assertEqual("feature/f1-paket", name)

    def test_pattern_without_owner_works(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("pkg/b16", name)

    def test_explicit_pattern_argument_overrides_the_configuration(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        name = self.packages.package_branch_name(
            project, "B16", pattern="feature/{owner}/{id}")

        self.assertEqual("feature/test/b16", name)


# ------------------------------------------------------------- Ungültige Fälle
class InvalidPatternTest(BranchNameCase):
    """AK: Ungültiges Muster/Ergebnis wird klar abgelehnt (ValueError)."""

    def test_unknown_placeholder_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError) as raised:
            self.packages.package_branch_name(
                project, "B16", pattern="feature/{foo}/{id}")

        self.assertIn("{foo}", str(raised.exception))

    def test_empty_pattern_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(project, "B16", pattern="")

    def test_empty_segment_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="feature//{id}")

    def test_segment_ending_on_lock_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="feature/{id}.lock")

    def test_uppercase_in_the_result_is_rejected(self):
        project = self.make_project(user_name="Test")

        with self.assertRaises(ValueError):
            self.packages.package_branch_name(
                project, "B16", pattern="Feature/{id}")

    def test_subcommand_reports_an_invalid_pattern_with_exit_one(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="{foo}/{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(1, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout + result.stderr)
        self.assertNotIn("feature/", result.stdout)

    def test_subcommand_reports_an_invalid_result_with_exit_one(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="feature//{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(1, result.returncode,
                         result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout + result.stderr)


# ---------------------------------------------------------------- Kollisionen
class CollisionTest(BranchNameCase):
    """AK: Lokale Branch-Kollisionen werden mit Suffixen aufgelöst."""

    def test_existing_branch_gets_the_suffix_two(self):
        project = self.make_project(user_name="Test")
        self.create_branch(project, "feature/test/b16")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/test/b16-2", name)

    def test_two_existing_branches_get_the_suffix_three(self):
        project = self.make_project(user_name="Test")
        self.create_branch(project, "feature/test/b16")
        self.create_branch(project, "feature/test/b16-2")

        name = self.packages.package_branch_name(project, "B16")

        self.assertEqual("feature/test/b16-3", name)


# ---------------------------------------------------------------- Subkommando
class BranchNameSubcommandTest(BranchNameCase):
    """AK: Der Läufer erhält den Branch-Namen über ein Subkommando."""

    def test_subcommand_prints_exactly_the_branch_name_and_exits_zero(self):
        project = self.make_project(user_name="M0P")

        result = self.run_branch_name(project, "B16")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("feature/m0p/b16", result.stdout.strip())
        self.assertEqual(1, len(result.stdout.strip().splitlines()),
                         "Genau eine stdout-Zeile erwartet")

    def test_subcommand_uses_the_configured_pattern(self):
        project = self.make_project(
            env_extra='PACKAGE_BRANCH_PATTERN="pkg/{id}"\n',
            user_name="Test",
        )

        result = self.run_branch_name(project, "B16")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("pkg/b16", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
