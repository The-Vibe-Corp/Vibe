"""Unabhängige Abnahmetests für AP12 „Bereit für github teil 4".

Abgeleitet aus TICKETS.md (AP12), SPEC.md und AGENTS.md, ohne die
Implementierung zu kennen. Geprüft wird der Zustand des lokalen
Git-Repositories, nicht Implementierungscode:

* AK1: .gitignore deckt alle lokalen Einstellungen des vibe-Projekts ab
  (TICKETS.md, FEEDBACK.md, .vibe/, opencode.json, .opencode/) und
  beschädigt nicht die versionierten Vorlagen unter templates/.
* AK2: systemspezifische OS- und Editor-Artefakte werden ausgeschlossen.
* AK3: lokal vorhandene, bisher versionierte lokale Einstellungsdateien
  (opencode.json, .opencode/agents/test-agent.md) sind aus dem Index
  entfernt, existieren aber weiterhin lokal.
* AK4: keine versionierte Datei enthält persönliche Home-Pfade oder
  Geheimnisse; die üblichen GitHub-Dokumente existieren und sind
  versioniert.
* AK5: ein dokumentierter Merge-/Push-Plan für das öffentliche
  Repository (M0P/Vibe) existiert in docs/features/AP12.md.

Für persönliche Pfade und Geheimnisse wird die im Projekt bereits
etablierte Regel aus scripts/build-release.py (HOME_PATH_RE,
PLACEHOLDER_USERS, scan_text) samt den Mustern aus
scripts/check-no-secrets.py wiederverwendet, damit die Prüfung zur
bestehenden Release-Regel konsistent ist.

Keine Netzzugriffe; git wird nur lokal mit Lesebefehlen aufgerufen
(ls-files, check-ignore). Diese Tests schlagen ohne Umsetzung von AP12
fehl (Rotphase). Ausführen mit:

    python3 -m unittest tests.unit.test_ap12_github_readiness -v
"""
import importlib.util
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD_RELEASE = REPO / "scripts" / "build-release.py"

# Lokale Einstellungen des vibe-Projekts, die nicht ins öffentliche
# Repository gehören (Rahmenentscheidung zu AP12).
LOCAL_SETTINGS = (
    "TICKETS.md",
    "FEEDBACK.md",
    "opencode.json",
    ".vibe/project.env",
    ".vibe/agents.json",
    ".vibe/sitzung.json",
    ".opencode/agent-testdatei.md",
    ".opencode/agents/test-agent.md",
)

# Laufzeitregeln, die das alte .gitignore bereits enthielt. Sie müssen
# auch nach der AP12-Anpassung weiterhin greifen (Regressionsschutz).
EXISTING_RUNTIME_IGNORES = (
    "web.token",
    "_secrets.env",
    "vibe.log",
    "config-backups/einstellungen.json",
    "agent-backups/agent.json",
    "vibe-storage-locks-test/sperre.json",
    "ordner/__pycache__/modul.pyc",
)

# Typische systemspezifische OS- und Editor-Artefakte (Wurzel und
# verschachtelt), die vom Push ausgeschlossen werden müssen.
SYSTEM_ARTIFACTS = (
    ".DS_Store",
    "docs/.DS_Store",
    "Thumbs.db",
    "web/Thumbs.db",
    "desktop.ini",
    "docs/desktop.ini",
    ".directory",
    "notizen.md~",
    "editor.swo",
    "editor.swp",
    ".idea/workspace.xml",
    ".vscode/settings.json",
)

GITHUB_DOCUMENTS = (
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
)

MERGE_PLAN = REPO / "docs" / "features" / "AP12.md"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_files():
    """Liefert die versionierten Dateien als Liste relativer Pfade."""
    result = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--cached"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [name for name in result.stdout.split("\0") if name]


def is_ignored(relpath):
    """True, wenn der Pfad von den Ignore-Regeln des Projekts erfasst wird."""
    result = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "--", relpath],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            "git check-ignore fehlgeschlagen (%d): %s"
            % (result.returncode, result.stderr.strip())
        )
    return result.returncode == 0


class GitignoreLocalSettingsTest(unittest.TestCase):
    """AK1: lokale Einstellungen werden ignoriert, Vorlagen bleiben drin."""

    def test_local_settings_are_ignored(self):
        verstoß = [
            path for path in LOCAL_SETTINGS if not is_ignored(path)
        ]
        self.assertEqual(
            verstoß,
            [],
            "Diese lokalen Einstellungen werden von .gitignore nicht "
            "erfasst: " + ", ".join(verstoß),
        )

    def test_existing_runtime_ignores_are_kept(self):
        verstoß = [
            path for path in EXISTING_RUNTIME_IGNORES if not is_ignored(path)
        ]
        self.assertEqual(
            verstoß,
            [],
            "Bisher geltende Laufzeitregeln wurden beim Anpassen der "
            ".gitignore verloren: " + ", ".join(verstoß),
        )

    def test_templates_stay_versioned_and_not_ignored(self):
        vorlagen = [name for name in tracked_files()
                    if name.startswith("templates/")]
        self.assertGreater(
            len(vorlagen),
            0,
            "Vorbedingung verletzt: keine versionierten Vorlagen unter "
            "templates/ vorhanden",
        )
        ignoriert = [name for name in vorlagen if is_ignored(name)]
        self.assertEqual(
            ignoriert,
            [],
            "Versionierte Vorlagen dürfen nicht ignoriert werden: "
            + ", ".join(ignoriert),
        )


class SystemArtifactsTest(unittest.TestCase):
    """AK2: systemspezifische Dateien sind ausgeschlossen."""

    def test_os_and_editor_artifacts_are_ignored(self):
        verstoß = [
            path for path in SYSTEM_ARTIFACTS if not is_ignored(path)
        ]
        self.assertEqual(
            verstoß,
            [],
            "Systemspezifische Artefakte werden von .gitignore nicht "
            "ausgeschlossen: " + ", ".join(verstoß),
        )


class UntrackedLocalSettingsTest(unittest.TestCase):
    """AK3: lokale Einstellungen unversioniert, aber lokal vorhanden."""

    def test_local_config_files_are_untracked_but_present(self):
        versioniert = set(tracked_files())
        verstoß = [
            path for path in ("opencode.json", ".opencode/agents/test-agent.md")
            if path in versioniert
        ]
        self.assertEqual(
            verstoß,
            [],
            "Lokale Einstellungsdateien sind weiterhin versioniert "
            "(git rm --cached -- erforderlich): " + ", ".join(verstoß),
        )

    def test_no_opencode_or_vibe_paths_are_tracked(self):
        verstoß = [
            name for name in tracked_files()
            if name == "opencode.json"
            or name.startswith(".opencode/")
            or name.startswith(".vibe/")
        ]
        self.assertEqual(
            verstoß,
            [],
            "Lokale Konfigurationspfade dürfen nicht versioniert sein: "
            + ", ".join(verstoß),
        )

    def test_local_config_files_still_exist_locally(self):
        fehlt = [
            path for path in ("opencode.json", ".opencode/agents/test-agent.md")
            if not (REPO / path).is_file()
        ]
        self.assertEqual(
            fehlt,
            [],
            "Lokale Einstellungsdateien müssen trotz Entfernen aus dem "
            "Index lokal erhalten bleiben: " + ", ".join(fehlt),
        )


class TrackedContentHygieneTest(unittest.TestCase):
    """AK4: keine persönlichen Pfade/Geheimnisse, GitHub-Dokumente da."""

    def test_no_tracked_file_contains_personal_home_paths_or_secrets(self):
        release = load_module(BUILD_RELEASE, "build_release_ap12_test")
        patterns = release.secret_patterns(REPO / "scripts")
        self.assertTrue(
            patterns,
            "Vorbedingung verletzt: Geheimnismuster aus "
            "scripts/check-no-secrets.py konnten nicht geladen werden",
        )
        problems = []
        for name in tracked_files():
            path = REPO / name
            if not path.is_file() or release.excluded(name):
                continue
            data = path.read_bytes()
            text = (
                release.decode_text(data)
                if len(data) <= release.MAX_SCAN_BYTES
                else None
            )
            if text is not None:
                problems.extend(release.scan_text(name, text, patterns))
        self.assertEqual(
            problems,
            [],
            "Versionierte Dateien verletzen die Regeln für persönliche "
            "Home-Pfade oder Geheimnisse:\n" + "\n".join(problems),
        )

    def test_github_documents_exist_and_are_tracked(self):
        versioniert = set(tracked_files())
        for document in GITHUB_DOCUMENTS:
            path = REPO / document
            self.assertTrue(
                path.is_file(), "GitHub-Dokument fehlt: " + document
            )
            self.assertGreater(
                path.stat().st_size,
                0,
                "GitHub-Dokument ist leer: " + document,
            )
            self.assertIn(
                document,
                versioniert,
                "GitHub-Dokument ist nicht versioniert: " + document,
            )
        lizenz = (REPO / "LICENSE").read_text(encoding="utf-8")
        self.assertIn(
            "MIT", lizenz, "LICENSE nennt die Lizenz nicht als MIT"
        )

    def test_pull_request_and_issue_templates_exist(self):
        versioniert = set(tracked_files())
        pr_kandidaten = (
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/pull_request_template.md",
            ".github/PULL_REQUEST_TEMPLATE/pull_request_template.md",
        )
        pr_vorlage = [
            kandidat for kandidat in pr_kandidaten
            if (REPO / kandidat).is_file()
        ]
        self.assertTrue(
            pr_vorlage,
            "Keine Pull-Request-Vorlage unter .github/ vorhanden",
        )
        self.assertTrue(
            all(kandidat in versioniert for kandidat in pr_vorlage),
            "Pull-Request-Vorlage ist nicht versioniert: "
            + ", ".join(pr_vorlage),
        )
        issue_verzeichnis = REPO / ".github" / "ISSUE_TEMPLATE"
        issue_vorlagen = sorted(
            str(path.relative_to(REPO).as_posix())
            for path in issue_verzeichnis.glob("*.md")
            if path.is_file()
        ) if issue_verzeichnis.is_dir() else []
        self.assertTrue(
            issue_vorlagen,
            "Keine Issue-Vorlagen unter .github/ISSUE_TEMPLATE/ vorhanden",
        )
        nicht_versioniert = [
            name for name in issue_vorlagen if name not in versioniert
        ]
        self.assertEqual(
            nicht_versioniert,
            [],
            "Issue-Vorlagen sind nicht versioniert: "
            + ", ".join(nicht_versioniert),
        )
        for name in pr_vorlage + issue_vorlagen:
            self.assertGreater(
                (REPO / name).stat().st_size,
                0,
                "Vorlage ist leer: " + name,
            )


class MergePushPlanTest(unittest.TestCase):
    """AK5: dokumentierter Merge-/Push-Plan für das öffentliche Repo."""

    def test_merge_and_push_plan_is_documented(self):
        self.assertTrue(
            MERGE_PLAN.is_file(),
            "Merge-/Push-Plan fehlt: docs/features/AP12.md",
        )
        inhalt = MERGE_PLAN.read_text(encoding="utf-8")
        self.assertGreater(
            len(inhalt.strip()),
            200,
            "docs/features/AP12.md enthält keinen nennenswerten Plan",
        )
        klein = inhalt.lower()
        self.assertIn(
            "m0p/vibe",
            klein,
            "Der Plan nennt das öffentliche Zielrepository (M0P/Vibe) nicht",
        )
        self.assertIn(
            "push", klein, "Der Plan beschreibt keinen Push-Schritt"
        )
        self.assertIn(
            "merge", klein, "Der Plan beschreibt keinen Merge-Schritt"
        )


if __name__ == "__main__":
    unittest.main()
