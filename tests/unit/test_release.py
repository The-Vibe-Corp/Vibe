"""Tests für Releasebasis und reproduzierbare Quellrelease (V-020).

Geprüft wird zweierlei:

* ``bin/vibe_paths.release_info`` nennt Version und Commit des laufenden
  Stands, ohne bei fehlenden Angaben zu raten.
* ``scripts/build-release.py`` erzeugt aus einem Git-Stand eine
  byte-identische Quellrelease, nimmt keine unversionierten Laufzeit- oder
  Sicherungsdateien auf und lehnt persönliche Pfade sowie Geheimnisse ab.
  ``verify`` prüft ein vorhandenes Archiv gegen sein Manifest.
"""
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "build-release.py"
PATHS_MODULE = REPO / "bin" / "vibe_paths.py"

MINIMAL_FILES = {
    "VERSION": "0.18.0\n",
    "README.md": "# vibe\n",
    "SPEC.md": "# SPEC\n",
    "AGENTS.md": "# AGENTS\n",
    "bin/vibe": "#!/usr/bin/env python3\nprint('vibe')\n",
    "bin/vibe-web.py": "print('web')\n",
    "scripts/setup-vibe.py": "print('setup')\n",
    "scripts/verify.sh": "#!/usr/bin/env bash\nexit 0\n",
    "tests/unit/test_x.py": "import unittest\n",
}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *arguments):
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def commit(root, message="init"):
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "add", "-A")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", message)


def make_repo(base):
    root = Path(base) / "kit"
    for name, text in MINIMAL_FILES.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "bin" / "vibe").chmod(0o755)
    (root / "scripts" / "verify.sh").chmod(0o755)
    git(root, "init", "-q")
    commit(root)
    return root


def archive_names(path):
    with tarfile.open(path, "r:gz") as archive:
        return sorted(member.name for member in archive.getmembers())


def read_member(path, name):
    with tarfile.open(path, "r:gz") as archive:
        handle = archive.extractfile(name)
        if handle is None:
            raise AssertionError("Archivmitglied fehlt: " + name)
        return handle.read()


class ReleaseInfoTest(unittest.TestCase):
    def setUp(self):
        self.paths_module = load_module(PATHS_MODULE, "vibe_paths_release_test")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "src"
        self.state = self.root / "state"
        self.source.mkdir()
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def paths(self):
        return SimpleNamespace(state=str(self.state), source=str(self.source))

    def test_source_version_is_used_and_no_commit_is_invented(self):
        (self.source / "VERSION").write_text("0.18.0\n", encoding="utf-8")
        info = self.paths_module.release_info(self.paths())
        self.assertEqual(info["version"], "0.18.0")
        self.assertEqual(info["commit"], "")
        self.assertEqual(info["origin"], "quelle")

    def test_installed_metadata_wins_over_the_source_version(self):
        (self.source / "VERSION").write_text("0.17.0\n", encoding="utf-8")
        (self.state / "version.json").write_text(
            json.dumps(
                {
                    "version": "0.18.0",
                    "commit": "abcdef1",
                    "installed_at": "2026-11-03T12:00:00Z",
                    "mode": "update",
                    "source": "/tmp/kit",
                }
            ),
            encoding="utf-8",
        )
        info = self.paths_module.release_info(self.paths())
        self.assertEqual(info["version"], "0.18.0")
        self.assertEqual(info["commit"], "abcdef1")
        self.assertEqual(info["installed_at"], "2026-11-03T12:00:00Z")
        self.assertEqual(info["origin"], "installation")

    def test_missing_metadata_is_reported_as_unknown(self):
        info = self.paths_module.release_info(self.paths())
        self.assertEqual(info["version"], "unbekannt")
        self.assertEqual(info["commit"], "")
        self.assertEqual(info["origin"], "unbekannt")

    def test_broken_metadata_falls_back_without_guessing(self):
        (self.source / "VERSION").write_text("0.18.0\n", encoding="utf-8")
        (self.state / "version.json").write_text("{kaputt", encoding="utf-8")
        info = self.paths_module.release_info(self.paths())
        self.assertEqual(info["version"], "0.18.0")
        self.assertEqual(info["commit"], "")
        self.assertEqual(info["origin"], "quelle")


class ReleaseBuildTest(unittest.TestCase):
    def setUp(self):
        self.release = load_module(SCRIPT, "build_release_test")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, source, output="dist"):
        return self.release.build_release(
            source=source, output=Path(self.root) / output
        )

    def test_release_is_reproducible_and_excludes_untracked_runtime_data(self):
        source = make_repo(self.root)
        (source / "web.token").write_text("geheim", encoding="utf-8")
        (source / "_logs").mkdir()
        (source / "_logs" / "vibe.log").write_text("laufzeit", encoding="utf-8")
        (source / "_secrets.env").write_text(
            "API_TOKEN=0123456789abcdef\n", encoding="utf-8"
        )
        (source / "_toolchain").mkdir()
        (source / "_toolchain" / "version.json").write_text(
            "{}\n", encoding="utf-8"
        )

        first = self.build(source, "dist-a")
        second = self.build(source, "dist-b")

        self.assertEqual(
            hashlib.sha256(first.read_bytes()).hexdigest(),
            hashlib.sha256(second.read_bytes()).hexdigest(),
            "Zwei Releases desselben Commits sind nicht byte-identisch",
        )
        names = archive_names(first)
        for excluded in (
            "web.token",
            "_logs/vibe.log",
            "_secrets.env",
            "_toolchain/version.json",
        ):
            self.assertNotIn(excluded, names)
        for required in ("VERSION", "RELEASE.json", "bin/vibe"):
            self.assertIn(required, names)

        manifest = json.loads(read_member(first, "RELEASE.json"))
        self.assertEqual(manifest["version"], "0.18.0")
        self.assertEqual(
            sorted(entry["path"] for entry in manifest["files"]),
            sorted(name for name in names if name != "RELEASE.json"),
        )
        self.assertEqual(self.release.verify_archive(first), [])

    def test_tracked_checksum_manifest_is_included(self):
        # docs/baseline-installation.sha256 ist versioniert und gehört zur
        # Release. Nur erzeugte Release-Prüfsummen (<archiv>.sha256) sind
        # unversioniert und dürfen nicht als Ausschlussgrund für versionierte
        # Dateien wirken.
        source = make_repo(self.root)
        (source / "docs").mkdir()
        (source / "docs" / "baseline-installation.sha256").write_text(
            "abc  install.sh\n", encoding="utf-8"
        )
        commit(source, "pruefsummenmanifest")
        archive = self.build(source)
        self.assertIn("docs/baseline-installation.sha256", archive_names(archive))
        self.assertEqual(self.release.verify_archive(archive), [])

    def test_temp_directory_named_home_is_not_a_personal_path(self):
        # Ein temporäres Verzeichnis namens "home" ist kein absoluter
        # Benutzerpfad. Nur /home/<benutzer>/ bzw. /Users/<benutzer>/ zählt.
        source = make_repo(self.root)
        (source / "docs").mkdir()
        (source / "docs" / "beispiel.md").write_text(
            "Startbefehl: /tmp/pruefung/home/.local/bin/vibe\n", encoding="utf-8"
        )
        commit(source, "temporaerer pfad")
        archive = self.build(source)
        self.assertEqual(self.release.verify_archive(archive), [])

    def test_verify_accepts_a_release_and_reports_a_missing_manifest(self):
        source = make_repo(self.root)
        archive = self.build(source)
        self.assertEqual(self.release.verify_archive(archive), [])

        broken = Path(self.root) / "broken.tar.gz"
        with tarfile.open(broken, "w:gz") as handle:
            data = b"0.18.0\n"
            info = tarfile.TarInfo("VERSION")
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
        problems = self.release.verify_archive(broken)
        self.assertTrue(problems, "Archiv ohne RELEASE.json wurde akzeptiert")
        self.assertTrue(
            any("RELEASE.json" in problem for problem in problems),
            problems,
        )

    def test_verify_rejects_an_altered_file(self):
        source = make_repo(self.root)
        archive = self.build(source)
        members = {}
        with tarfile.open(archive, "r:gz") as handle:
            for member in handle.getmembers():
                handle_file = handle.extractfile(member)
                members[member.name] = (
                    member,
                    handle_file.read() if handle_file else b"",
                )
        altered = Path(self.root) / "altered.tar.gz"
        with tarfile.open(altered, "w:gz") as handle:
            for name, (member, data) in members.items():
                payload = b"manipuliert\n" if name == "README.md" else data
                new = tarfile.TarInfo(name)
                new.size = len(payload)
                new.mode = member.mode
                handle.addfile(new, io.BytesIO(payload))
        problems = self.release.verify_archive(altered)
        self.assertTrue(problems, "Manipuliertes Archiv wurde akzeptiert")
        self.assertTrue(any("README.md" in problem for problem in problems), problems)

    def test_tracked_personal_path_is_refused_and_no_archive_is_written(self):
        source = make_repo(self.root)
        (source / "docs").mkdir()
        # Der Pfad wird zusammengesetzt, damit diese Testdatei selbst nicht
        # gegen die Release-Regel für absolute Home-Pfade verstößt.
        personal = "/".join(("", "home", "marc", "privat", "projekt"))
        (source / "docs" / "notizen.md").write_text(
            "Beispiel: " + personal + "\n", encoding="utf-8"
        )
        commit(source, "persoenlicher Pfad")

        with self.assertRaises(self.release.ReleaseError) as caught:
            self.build(source)
        self.assertIn("docs/notizen.md", str(caught.exception))
        self.assertFalse(
            list((Path(self.root) / "dist").glob("*.tar.gz")),
            "Trotz persönlichem Pfad wurde ein Archiv geschrieben",
        )

    def test_source_without_git_is_reported(self):
        plain = Path(self.root) / "ohne-git"
        plain.mkdir()
        (plain / "VERSION").write_text("0.18.0\n", encoding="utf-8")
        with self.assertRaises(self.release.ReleaseError) as caught:
            self.build(plain)
        self.assertIn("git", str(caught.exception).lower())

    def test_tracked_symlink_is_refused_instead_of_becoming_a_regular_file(self):
        # Ein versionierter Symlink würde sonst als reguläre Datei mit dem
        # Zielpfad als Inhalt im Archiv landen. Der Bau bricht stattdessen ab,
        # statt den Inhalt still zu verfälschen.
        source = make_repo(self.root)
        (source / "docs").mkdir()
        os.symlink("../VERSION", source / "docs" / "version-link")
        commit(source, "symlink")

        with self.assertRaises(self.release.ReleaseError) as caught:
            self.build(source)
        self.assertIn("docs/version-link", str(caught.exception))
        self.assertFalse(
            list((Path(self.root) / "dist").glob("*.tar.gz")),
            "Trotz Symlink wurde ein Archiv geschrieben",
        )

    def test_repository_content_has_no_personal_home_paths_or_secrets(self):
        # Der Releasebau lehnt persönliche Home-Pfade und Geheimnisse ab.
        # Diese Prüfung stellt sicher, dass das Repository selbst diese Regel
        # einhält, damit ein Release des eigenen Stands nicht blockiert.
        raw = git(
            REPO,
            "-c",
            "safe.directory=" + str(REPO),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ).stdout
        patterns = self.release.secret_patterns(REPO / "scripts")
        problems = []
        for name in raw.split("\0"):
            if not name:
                continue
            path = REPO / name
            if self.release.excluded(name) or not path.is_file():
                continue
            data = path.read_bytes()
            text = (
                self.release.decode_text(data)
                if len(data) <= self.release.MAX_SCAN_BYTES
                else None
            )
            if text is not None:
                problems.extend(self.release.scan_text(name, text, patterns))
        self.assertEqual(
            problems, [], "Repository verletzt die Release-Regeln für Inhalte"
        )

    def test_published_documents_exist_and_are_not_empty(self):
        for document in (
            "docs/handbuch.md",
            "docs/betrieb.md",
            "docs/grenzen.md",
            "docs/checkliste.md",
            "docs/abnahme-bazzite.md",
            "docs/features/V-020.md",
        ):
            path = REPO / document
            self.assertTrue(path.is_file(), "Dokument fehlt: " + document)
            self.assertGreater(
                path.stat().st_size, 200, "Dokument ist leer: " + document
            )


if __name__ == "__main__":
    unittest.main()
