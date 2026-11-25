"""AGENTS.md: Anzeigen, Speichern und Wiederherstellen sowie globale AGENTS.md-Dateien.

Aufruf: python3 -m unittest tests.unit.test_agents_md -v
"""


# ===========================================================================
# Unit-Tests: AGENTS.md in der Assistent-Ansicht ansehen und bearbeiten
# ===========================================================================

import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"


def general_rules():
    """Der frühere deutsche Regelblock als Bestands-Fixture (GH-76).

    Der Block wird von ``bin/vibe`` nicht mehr erzeugt. Für die Ansicht und
    das byte-identische Speichern eines bestehenden Projekts bleibt er aber
    ein gültiger Bestandsfall; der Test darf ihn deshalb nicht aus einer
    Produktionskonstante ableiten.
    """
    return (
        "<!-- vibe:general-rules -->\n"
        "## Altbestand (nicht mehr erzeugt)\n\n"
        "- Diese Zeile bleibt beim Speichern byte-identisch.\n"
        "<!-- /vibe:general-rules -->"
    )


BLOCK = general_rules()
MARK = "<!-- vibe:general-rules -->"
MARK_END = "<!-- /vibe:general-rules -->"


def symlink_supported():
    """Funktionstest-Probe: lassen sich in der Prüfumgebung Symlinks anlegen?

    Auf FUSE/NTFS-Arbeitskopien ist ``os.symlink`` nicht garantiert verfügbar.
    AK7 verlangt die Ablehnung von Symlinks; die zugehörigen Fälle skippen
    nachweislich (kein stiller Verzicht), wenn die Umgebung sie nicht erlaubt.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "probe-link"
            os.symlink("probe-target", link)
            if not link.is_symlink():
                return False
            os.remove(link)
    except (OSError, NotImplementedError):
        return False
    return True


SYMLINKS_SUPPORTED = symlink_supported()


# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben (Muster tests/unit/test_agent_management.py).
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
)


def isolated_env(root, home):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f31_agents_file_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def make_project(root, name, env):
    project = Path(root) / name
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env, encoding="utf-8")
    return project


class AgentsFileFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        # Eigene Vorlagenkopie, damit create() nicht an der produktiven
        # Installation arbeitet.
        toolchain = self.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
        self.proj = make_project(self.root, "proj", "TYPE=generic\n")
        self.webproj = make_project(self.root, "webproj", "TYPE=web\n")
        self.fancy = make_project(self.root, "fancyproj", "TYPE=fancyx\n")
        self.cli = load_cli(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    # ---------- Hilfen ----------

    def agents_path(self, name="proj"):
        return self.root / name / "AGENTS.md"

    def write_agents(self, text, name="proj"):
        self.agents_path(name).write_text(text, encoding="utf-8")

    def read_agents(self, name="proj"):
        return self.agents_path(name).read_text(encoding="utf-8")

    def make_agents_symlink(self, name="proj"):
        """AGENTS.md als Symlink auf eine echte Datei im Projekt anlegen."""
        target = self.root / name / "agents-real.md"
        target.write_text("Zielinhalt-F31\n", encoding="utf-8")
        path = self.agents_path(name)
        os.symlink(target.name, path)
        self.assertTrue(path.is_symlink(), "Vorbedingung: Symlink nicht angelegt")
        return target

    def with_block(self, before, after):
        """Dateiinhalt mit byte-identischem verwaltetem Block in der Mitte."""
        return before + BLOCK + after

    # ---------- AK1: Ansicht ----------

    def test_view_splits_managed_block_from_free_parts(self):
        self.write_agents(self.with_block("Kopfteil-F31\n", "\nFußteil-F31\n"))
        view = self.cli.agents_file_view("proj")
        self.assertTrue(view["exists"])
        self.assertEqual(view["before"], "Kopfteil-F31\n")
        self.assertEqual(view["managed"], BLOCK)
        self.assertEqual(view["after"], "\nFußteil-F31\n")
        self.assertTrue(view["digest"], "Digest fehlt in der Ansicht")

    def test_view_without_markers_reports_whole_text_as_after(self):
        text = "Nur freier Text, keine Marker.\n"
        self.write_agents(text)
        view = self.cli.agents_file_view("proj")
        self.assertTrue(view["exists"])
        self.assertIsNone(view["managed"])
        self.assertEqual(view["after"], text)
        self.assertTrue(view["digest"])

    def test_view_missing_file_reports_empty_view(self):
        view = self.cli.agents_file_view("proj")
        self.assertFalse(view["exists"])
        self.assertEqual(view["before"], "")
        self.assertIsNone(view["managed"])
        self.assertEqual(view["after"], "")
        self.assertEqual(view["digest"], "")

    # ---------- AK3: Bearbeiten und Speichern ----------

    def test_save_merges_free_parts_with_byte_identical_block(self):
        self.write_agents(self.with_block("Alt oben\n", "\nAlt unten\n"))
        view = self.cli.agents_file_view("proj")
        storage = self.cli.vibe_storage
        with mock.patch.object(storage, "write_text", wraps=storage.write_text) as spy:
            self.cli.agents_file_save("proj", "Neu oben\n", "Neu unten\n", view["digest"])
        self.assertEqual(self.read_agents(), self.with_block("Neu oben\n", "Neu unten\n"))
        # Atomar über die Speicherschicht (V-005): Der Digest-Schutz wurde
        # an write_text durchgereicht.
        self.assertTrue(
            any(
                (call.kwargs.get("expected") == view["digest"])
                or (call.args and view["digest"] in call.args)
                for call in spy.call_args_list
            ),
            "save hat nicht mit Digest-Schutz über vibe_storage geschrieben",
        )
        # Der Digest der Ansicht ist für einen zweiten Lauf verwendbar.
        fresh = self.cli.agents_file_view("proj")
        self.cli.agents_file_save(
            "proj", fresh["before"], fresh["after"], fresh["digest"]
        )
        self.assertEqual(self.read_agents(), self.with_block("Neu oben\n", "Neu unten\n"))

    # ---------- AK4: Gleichzeitigkeit ----------

    def test_save_rejects_stale_digest_and_leaves_file_untouched(self):
        original = self.with_block("Alt oben\n", "\nAlt unten\n")
        self.write_agents(original)
        view = self.cli.agents_file_view("proj")
        # Gleichzeitige fremde Änderung außerhalb des Blocks.
        self.write_agents(original + "Fremde Änderung\n")
        with self.assertRaises(ValueError):
            self.cli.agents_file_save("proj", "Neu oben\n", "Neu unten\n", view["digest"])
        self.assertEqual(
            self.agents_path().read_bytes(),
            (original + "Fremde Änderung\n").encode("utf-8"),
        )

    # ---------- AK5: Schutz der Marker ----------

    def test_save_rejects_markers_in_free_parts(self):
        cases = [
            ("before", "Oben " + MARK + "\n"),
            ("before", "Oben " + MARK + " ... " + MARK_END + "\n"),
            ("before", "Oben " + MARK_END + "\n"),
            ("after", "\nUnten " + MARK + "\n"),
            ("after", "\nUnten " + MARK + " ... " + MARK_END + "\n"),
            ("after", "\nUnten " + MARK_END + "\n"),
        ]
        original = self.with_block("Alt oben\n", "\nAlt unten\n")
        for side, snippet in cases:
            with self.subTest(side=side, snippet=snippet):
                self.write_agents(original)
                view = self.cli.agents_file_view("proj")
                before = snippet if side == "before" else "Neu oben\n"
                after = snippet if side == "after" else "Neu unten\n"
                with self.assertRaises(ValueError):
                    self.cli.agents_file_save("proj", before, after, view["digest"])
                self.assertEqual(self.agents_path().read_bytes(), original.encode("utf-8"))

    def test_save_without_block_writes_after_verbatim(self):
        self.write_agents("Nur freier Text, keine Marker.\n")
        view = self.cli.agents_file_view("proj")
        self.assertIsNone(view["managed"])
        self.cli.agents_file_save("proj", "", "Ersetzt ohne Block.\n", view["digest"])
        text = self.read_agents()
        self.assertEqual(text, "Ersetzt ohne Block.\n")
        self.assertNotIn(MARK, text)
        self.assertNotIn(MARK_END, text)
        # Kein Block wurde still eingefügt: die Ansicht bleibt blockfrei.
        self.assertIsNone(self.cli.agents_file_view("proj")["managed"])

    def test_save_without_block_writes_before_and_after(self):
        """GH-76: Für blockfreie Dateien sind beide Editor-Teile speicherbar."""
        self.write_agents("Alter Inhalt ohne Marker.\n")
        view = self.cli.agents_file_view("proj")
        self.assertIsNone(view["managed"])

        self.cli.agents_file_save(
            "proj", "Neuer oberer Teil.\n", "Neuer unterer Teil.\n",
            view["digest"])

        self.assertEqual(
            "Neuer oberer Teil.\nNeuer unterer Teil.\n", self.read_agents())
        self.assertNotIn(MARK, self.read_agents())
        self.assertIsNone(self.cli.agents_file_view("proj")["managed"])

    # ---------- AK6: Aus Vorlage anlegen ----------

    def test_create_uses_type_template_with_name_replaced(self):
        self.assertFalse(self.agents_path("webproj").exists())
        self.cli.agents_file_create("webproj")
        text = self.agents_path("webproj").read_text(encoding="utf-8")
        template = (REPO / "templates" / "web" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text, template.replace("{{NAME}}", "webproj"))
        # GH-76: Die Typ-Vorlage trägt keinen verwalteten Block mehr.
        self.assertNotIn(MARK, text)
        self.assertNotIn(MARK_END, text)

    def test_create_unknown_type_falls_back_to_generic(self):
        self.cli.agents_file_create("fancyproj")
        text = self.agents_path("fancyproj").read_text(encoding="utf-8")
        template = (REPO / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text, template.replace("{{NAME}}", "fancyproj"))
        self.assertNotIn(MARK, text)
        self.assertNotIn(MARK_END, text)

    def test_create_never_overwrites_existing_file(self):
        self.write_agents("Bestehender Inhalt.\n")
        result = self.cli.agents_file_create("proj")
        self.assertEqual(result, "kept")
        self.assertEqual(self.read_agents(), "Bestehender Inhalt.\n")

    # ---------- AK7: Pfadsicherung ----------

    def test_unknown_or_traversal_names_are_rejected(self):
        bad_names = ["does-not-exist", "proj/../webproj", "../f31-outside"]
        for name in bad_names:
            with self.subTest(name=name):
                with self.assertRaises((ValueError, SystemExit)):
                    self.cli.agents_file_view(name)
                with self.assertRaises((ValueError, SystemExit)):
                    self.cli.agents_file_create(name)
                with self.assertRaises((ValueError, SystemExit)):
                    self.cli.agents_file_save(name, "a", "b", "0" * 64)
        # Es wurde nichts außerhalb der Projekte angelegt oder verändert.
        self.assertFalse((self.root.parent / "f31-outside" / "AGENTS.md").exists())
        self.assertFalse((self.root.parent / "AGENTS.md").exists())
        self.assertFalse(self.agents_path("webproj").exists())
        self.assertFalse(self.agents_path("proj").exists())

    # ---------- AK7: Symlinks werden abgelehnt ----------

    _skip_no_symlinks = "os.symlink funktioniert in der Prüfumgebung nicht"

    @unittest.skipUnless(SYMLINKS_SUPPORTED, _skip_no_symlinks)
    def test_view_rejects_symlink_and_reports_missing_file(self):
        target = self.make_agents_symlink()
        view = self.cli.agents_file_view("proj")
        # Der Symlink zählt als fehlende Datei; der Link-Zielinhalt wird
        # nicht als AGENTS.md-Inhalt ausgespielt.
        self.assertFalse(view["exists"])
        self.assertEqual(view["before"], "")
        self.assertIsNone(view["managed"])
        self.assertEqual(view["after"], "")
        self.assertEqual(view["digest"], "")
        # Das Link-Ziel bleibt unverändert.
        self.assertEqual(
            target.read_text(encoding="utf-8"), "Zielinhalt-F31\n"
        )

    @unittest.skipUnless(SYMLINKS_SUPPORTED, _skip_no_symlinks)
    def test_save_rejects_symlink_and_leaves_target_untouched(self):
        target = self.make_agents_symlink()
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            self.cli.agents_file_save("proj", "Neu oben\n", "Neu unten\n", "0" * 64)
        # Das Link-Ziel bleibt byte-identisch, der Symlink bleibt Symlink.
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(self.agents_path().is_symlink())

    @unittest.skipUnless(SYMLINKS_SUPPORTED, _skip_no_symlinks)
    def test_create_rejects_symlink_and_leaves_target_untouched(self):
        target = self.make_agents_symlink()
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            self.cli.agents_file_create("proj")
        # Das Link-Ziel bleibt byte-identisch, der Symlink wurde weder
        # überschrieben noch durch eine echte Datei ersetzt.
        self.assertEqual(target.read_bytes(), original)
        # Der Symlink wurde weder überschrieben noch durch eine echte
        # Datei ersetzt.
        self.assertTrue(self.agents_path().is_symlink())


# ===========================================================================
# Unit-Tests, AGENTS.md sichern und wiederherstellen
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

WEB = REPO / "bin" / "vibe-web.py"

AGENTS_V1 = "# Projekt-AGENTS F33\n\nErster Stand.\n"
AGENTS_V2 = "# Projekt-AGENTS F33\n\nZweiter Stand.\n"
AGENTS_V3 = "# Projekt-AGENTS F33\n\nDritter Stand (nicht gesichert).\n"

ISOLATED_ENV_f33 = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "XDG_CONFIG_HOME",
    "VIBE_GLOBAL_AGENTS",
)


def isolated_env_f33(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_f33:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_toolchain"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli_f33(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_f33}
    for key in ISOLATED_ENV_f33:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_f33(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f33_agents_file_backup_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def snapshot(root):
    """SHA-256 je Datei relativ zum Prüfbereich."""
    root = Path(root)
    digests = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return digests


def content_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AgentsFileBackupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (self.proj / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        self.cli = load_cli_f33(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def agents_path(self):
        return self.proj / "AGENTS.md"

    def write_agents(self, text):
        self.agents_path().write_text(text, encoding="utf-8")

    def read_agents(self):
        return self.agents_path().read_text(encoding="utf-8")

    def new_files(self, before):
        after = snapshot(self.root)
        return {name: digest for name, digest in after.items()
                if name not in before}

    def assert_backup_of(self, files, text):
        self.assertIn(
            content_digest(text), set(files.values()),
            "Keine neue Sicherungsdatei enthält den erwarteten Inhalt: "
            + repr(sorted(files)))


class AgentsFileBackupFunctionTest(AgentsFileBackupFixture):
    def test_backup_stores_the_file_and_keeps_the_original(self):
        """Vorbedingung: Projekt-AGENTS.md mit Inhalt.

        Aktion: ``agents_file_backup("proj")``.
        Erwartung: Das Original bleibt byte-identisch; eine neue Sicherungsdatei
        enthält genau diesen Inhalt.
        """
        self.write_agents(AGENTS_V1)
        before = snapshot(self.root)
        original = self.agents_path().read_bytes()

        self.cli.agents_file_backup("proj")

        self.assertEqual(self.agents_path().read_bytes(), original,
                         "Die Sicherung veränderte die AGENTS.md")
        files = self.new_files(before)
        self.assertTrue(files, "Es entstand keine Sicherungsdatei")
        self.assert_backup_of(files, AGENTS_V1)

    def test_repeated_backups_get_distinct_timestamped_names(self):
        """Vorbedingung: zwei Stände der AGENTS.md.

        Aktion: Nach jedem Stand eine Sicherung.
        Erwartung: Zwei verschiedene Sicherungsdateien; keine überschreibt die
        andere, beide Inhalte bleiben erhalten.
        """
        self.write_agents(AGENTS_V1)
        before = snapshot(self.root)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V2)
        self.cli.agents_file_backup("proj")

        files = self.new_files(before)
        self.assertGreaterEqual(
            len(files), 2,
            "Wiederholte Sicherungen erzeugen keine eigenen Dateien: "
            + repr(sorted(files)))
        contents = set(files.values())
        self.assertIn(content_digest(AGENTS_V1), contents,
                      "Die erste Sicherung ging verloren: "
                      + repr(sorted(files)))
        self.assertIn(content_digest(AGENTS_V2), contents,
                      "Die zweite Sicherung fehlt: " + repr(sorted(files)))
        self.assertEqual(self.read_agents(), AGENTS_V2)

    def test_restore_brings_back_the_newest_backup_with_a_safety_backup(self):
        """Vorbedingung: v1 gesichert, v2 gesichert, v3 ungesichert.

        Aktion: ``agents_file_restore("proj")``.
        Erwartung: Die Datei enthält v2 (neueste Sicherung); eine zusätzliche
        Safety-Sicherung enthält den vorherigen Stand v3.
        """
        self.write_agents(AGENTS_V1)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V2)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V3)
        before = snapshot(self.root)

        self.cli.agents_file_restore("proj")

        self.assertEqual(
            self.read_agents(), AGENTS_V2,
            "Die Wiederherstellung brachte nicht die neueste Sicherung zurück")
        files = self.new_files(before)
        self.assert_backup_of(files, AGENTS_V3)
        # v1 und v2 bleiben als Sicherungen erhalten.
        all_digests = set(snapshot(self.root).values())
        self.assertIn(content_digest(AGENTS_V1), all_digests)
        self.assertIn(content_digest(AGENTS_V2), all_digests)

    def test_restore_without_a_backup_is_rejected(self):
        """Vorbedingung: keine Sicherung vorhanden.

        Erwartung: ``agents_file_restore`` wirft ``ValueError`` und die Datei
        bleibt unverändert.
        """
        self.write_agents(AGENTS_V1)
        with self.assertRaises(ValueError):
            self.cli.agents_file_restore("proj")
        self.assertEqual(self.read_agents(), AGENTS_V1)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AgentsFileBackupApiTest(unittest.TestCase):
    """POST /api/agents_file backup/restore gegen ein Server-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.port = free_port()
        env = isolated_env_f33(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.path = self.project / "AGENTS.md"
        self.path.write_text(AGENTS_V1, encoding="utf-8")
        for item in self.root.rglob("*"):
            if item.is_file() and item != self.path and "AGENTS" in item.name:
                item.unlink()

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method="POST" if data else "GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def assert_view(self, payload):
        view = payload.get("agents_file")
        self.assertIsInstance(view, dict, payload)
        for key in ("exists", "before", "managed", "after", "digest"):
            self.assertIn(key, view, "agents_file-Ansicht ohne " + key
                          + ": " + repr(view))
        self.assertTrue(view["exists"], view)

    def test_backup_reports_the_exact_message_and_view(self):
        """Vorbedingung: Projekt-AGENTS.md.

        Aktion: POST ``{action:"backup"}``.
        Erwartung: ``ok``, Meldung exakt „AGENTS.md gesichert“, aktualisierte
        ``agents_file``-Ansicht; die Datei bleibt unverändert.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("AGENTS.md gesichert", payload.get("message"), payload)
        self.assert_view(payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V1)

    def test_restore_with_confirm_brings_back_the_backup(self):
        """Vorbedingung: v1 gesichert, danach v2 geschrieben.

        Aktion: POST ``{action:"restore", confirm:true}``.
        Erwartung: Meldung exakt „AGENTS.md wiederhergestellt“, die Datei
        enthält wieder v1, die Antwort bringt die aktualisierte Ansicht.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.path.write_text(AGENTS_V2, encoding="utf-8")

        status, payload = self.request(
            "/api/agents_file",
            {"name": "proj", "action": "restore", "confirm": True})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(
            "AGENTS.md wiederhergestellt", payload.get("message"), payload)
        self.assert_view(payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V1,
                         "Die Wiederherstellung brachte nicht v1 zurück")

    def test_restore_without_confirm_is_rejected_and_keeps_the_file(self):
        """Vorbedingung: v1 gesichert, danach v2 geschrieben.

        Aktion: Erst eine gültige Sicherung, dann POST ``{action:"restore"}``
        ohne ``confirm:true``.
        Erwartung: Die Sicherung bestätigt die Aktion; die Wiederherstellung
        ohne Bestätigung wird abgelehnt (Status 400, ``ok`` falsch) und die
        Datei bleibt v2.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.assertEqual("AGENTS.md gesichert", payload.get("message"), payload)
        self.path.write_text(AGENTS_V2, encoding="utf-8")

        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "restore"})
        self.assertEqual(400, status, payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V2,
                         "Ohne Bestätigung wurde die Datei verändert")


# ===========================================================================
# Unit-Tests, Globale AGENTS.md im opencode-Konfigurationsordner
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


GLOBAL_TEXT = "# Globale AGENTS.md\n\nImmer gültig — F33.\n"
GLOBAL_TEXT_NEW = "# Globale AGENTS.md\n\nNeu mit Umlauten: äöü ß und Emoji.\n"

ISOLATED_ENV_f332 = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "XDG_CONFIG_HOME",
    "VIBE_GLOBAL_AGENTS",
)


def agents_md_symlink_supported():
    """Funktionstest-Probe für Symlink-Fälle (Muster test_f31_agents_file)."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "probe-link"
            os.symlink("probe-target", link)
            if not link.is_symlink():
                return False
            os.remove(link)
    except (OSError, NotImplementedError):
        return False
    return True


def isolated_environ(home, **extra):
    """Bereinigte Umgebung mit temporärem HOME und ohne Produktivpfade."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_f332:
        env.pop(key, None)
    env["HOME"] = str(home)
    env.update(extra)
    return env


def load_cli_f332(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_f332}
    for key in ISOLATED_ENV_f332:
        os.environ.pop(key, None)
    os.environ.update({
        "VIBE": str(vibe_root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_STATE": str(Path(vibe_root) / "_toolchain"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f33_global_agents_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


class GlobalAgentsFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.config = self.home / ".config" / "opencode"
        self.config.mkdir(parents=True)
        self.path = self.config / "AGENTS.md"
        self.env = isolated_environ(self.home)
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cli = load_cli_f332(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def write_global(self, text=GLOBAL_TEXT):
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def make_symlink(self):
        target = self.root / "aussen" / "AGENTS.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Zielinhalt-GLOBAL-F33\n", encoding="utf-8")
        os.symlink(target, self.path)
        self.assertTrue(self.path.is_symlink(),
                        "Vorbedingung: Symlink nicht angelegt")
        return target


class GlobalAgentsPathTest(GlobalAgentsFixture):
    def test_env_override_wins(self):
        """Vorbedingung: ``VIBE_GLOBAL_AGENTS`` gesetzt.

        Erwartung: ``global_agents_path`` liefert genau diesen Pfad, auch wenn
        ``XDG_CONFIG_HOME`` und ``HOME`` gesetzt sind.
        """
        override = self.root / "eigener-ort" / "AGENTS.md"
        environ = {
            "VIBE_GLOBAL_AGENTS": str(override),
            "XDG_CONFIG_HOME": str(self.root / "xdg"),
            "HOME": str(self.home),
        }
        self.assertEqual(
            Path(self.cli.global_agents_path(environ)), override,
            "VIBE_GLOBAL_AGENTS wurde nicht bevorzugt")

    def test_xdg_config_home_is_used_when_present(self):
        """Vorbedingung: ``XDG_CONFIG_HOME`` ohne Override.

        Erwartung: ``<XDG>/opencode/AGENTS.md``.
        """
        xdg = self.root / "xdg"
        environ = {"XDG_CONFIG_HOME": str(xdg), "HOME": str(self.home)}
        self.assertEqual(
            Path(self.cli.global_agents_path(environ)),
            xdg / "opencode" / "AGENTS.md",
            "XDG_CONFIG_HOME wurde nicht für den opencode-Ordner verwendet")

    def test_home_config_directory_is_the_fallback(self):
        """Vorbedingung: nur ``HOME`` gesetzt.

        Erwartung: ``<HOME>/.config/opencode/AGENTS.md``.
        """
        environ = {"HOME": str(self.home)}
        self.assertEqual(
            Path(self.cli.global_agents_path(environ)),
            self.home / ".config" / "opencode" / "AGENTS.md",
            "Der Fallback auf das Home-Konfigurationsverzeichnis fehlt")

    def test_resolution_never_touches_the_real_home(self):
        """Vorbedingung: temporäres HOME.

        Erwartung: Der aufgelöste Pfad liegt unter dem temporären HOME; es
        entsteht keine Datei.
        """
        resolved = Path(self.cli.global_agents_path({"HOME": str(self.home)}))
        self.assertTrue(
            str(resolved).startswith(str(self.home) + os.sep),
            "Der aufgelöste Pfad liegt außerhalb des temporären HOME: "
            + str(resolved))
        self.assertFalse(resolved.exists(),
                         "Die Auflösung legte eine Datei an")


class GlobalAgentsViewTest(GlobalAgentsFixture):
    def test_missing_file_is_an_empty_view_without_error(self):
        """Vorbedingung: keine globale AGENTS.md.

        Erwartung: ``exists`` falsch, ``text``/``digest`` leer, nichtleerer
        ``path_hint``; keine Datei entsteht.
        """
        view = self.cli.global_agents_view()
        self.assertFalse(view["exists"], view)
        self.assertEqual("", view["text"], view)
        self.assertEqual("", view["digest"], view)
        self.assertTrue(str(view.get("path_hint") or "").strip(),
                        "Die Ansicht nennt keinen Pfadhinweis: " + repr(view))
        self.assertFalse(self.path.exists(),
                         "Die Ansicht legte eine Datei an")

    def test_existing_file_is_returned_with_digest(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: ``exists`` wahr, Text byte-gleich, Digest = SHA-256.
        """
        self.write_global()
        view = self.cli.global_agents_view()
        self.assertTrue(view["exists"], view)
        self.assertEqual(view["text"], GLOBAL_TEXT)
        self.assertEqual(
            view["digest"],
            hashlib.sha256(GLOBAL_TEXT.encode("utf-8")).hexdigest(),
            "Der Digest entspricht nicht dem Dateiinhalt")
        self.assertTrue(str(view.get("path_hint") or "").strip())

    @unittest.skipUnless(SYMLINKS_SUPPORTED,
                         "os.symlink funktioniert in der Prüfumgebung nicht")
    def test_symlink_is_reported_as_missing_and_not_read(self):
        """Vorbedingung: AGENTS.md ist ein Symlink auf eine fremde Datei.

        Erwartung: ``exists`` falsch, ``text`` leer, der Pfadhinweis nennt den
        Symlink; das Ziel bleibt unberührt.
        """
        target = self.make_symlink()
        view = self.cli.global_agents_view()
        self.assertFalse(view["exists"], view)
        self.assertEqual("", view["text"],
                         "Der Inhalt des Symlink-Ziels wurde ausgespielt")
        self.assertRegex(
            str(view.get("path_hint") or ""), r"symlink|link|verknüpf",
            "Der Pfadhinweis nennt den Symlink nicht: " + repr(view))
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "Zielinhalt-GLOBAL-F33\n")


class GlobalAgentsSaveTest(GlobalAgentsFixture):
    def test_save_writes_utf8_with_the_expected_digest(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Aktion: ``global_agents_save`` mit aktuellem Digest.
        Erwartung: Der neue Text steht UTF-8-kodiert in der Datei; der neue
        Digest passt zum Inhalt.
        """
        self.write_global()
        digest = self.cli.global_agents_view()["digest"]

        self.cli.global_agents_save(GLOBAL_TEXT_NEW, digest)

        self.assertEqual(self.path.read_text(encoding="utf-8"), GLOBAL_TEXT_NEW)
        self.assertEqual(
            self.cli.global_agents_view()["digest"],
            hashlib.sha256(GLOBAL_TEXT_NEW.encode("utf-8")).hexdigest(),
            "Der Digest nach dem Speichern passt nicht zum Inhalt")

    def test_stale_digest_is_rejected_and_changes_nothing(self):
        """Vorbedingung: fremde Änderung nach dem Lesen.

        Aktion: Speichern mit veraltetem Digest.
        Erwartung: ``ValueError``; die Datei bleibt byte-identisch.
        """
        self.write_global()
        stale = self.cli.global_agents_view()["digest"]
        self.write_global(GLOBAL_TEXT + "Fremde Änderung\n")
        before = self.path.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.global_agents_save(GLOBAL_TEXT_NEW, stale)

        self.assertEqual(self.path.read_bytes(), before,
                         "Der veraltete Digest veränderte die Datei")

    def test_missing_digest_is_rejected(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: Ohne Digest wird nicht geschrieben.
        """
        self.write_global()
        before = self.path.read_bytes()
        for digest in ("", None):
            with self.subTest(digest=digest):
                with self.assertRaises(ValueError):
                    self.cli.global_agents_save(GLOBAL_TEXT_NEW, digest)
                self.assertEqual(self.path.read_bytes(), before)

    @unittest.skipUnless(SYMLINKS_SUPPORTED,
                         "os.symlink funktioniert in der Prüfumgebung nicht")
    def test_symlink_is_rejected_and_the_target_stays_untouched(self):
        """Vorbedingung: AGENTS.md ist ein Symlink.

        Erwartung: ``ValueError``; das Link-Ziel bleibt byte-identisch und der
        Symlink bleibt Symlink.
        """
        target = self.make_symlink()
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            self.cli.global_agents_save(GLOBAL_TEXT_NEW, "0" * 64)
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(self.path.is_symlink())


class GlobalAgentsCreateTest(GlobalAgentsFixture):
    def test_create_writes_a_minimal_template_when_missing(self):
        """Vorbedingung: keine globale AGENTS.md.

        Aktion: ``global_agents_create()``.
        Erwartung: Die Datei existiert mit nichtleerem UTF-8-Inhalt; die
        Ansicht meldet ``exists``.
        """
        self.cli.global_agents_create()
        self.assertTrue(self.path.is_file(), "Die Vorlage wurde nicht angelegt")
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.strip(), "Die Vorlage ist leer")
        self.assertTrue(self.cli.global_agents_view()["exists"])

    def test_create_never_overwrites_an_existing_file(self):
        """Vorbedingung: globale AGENTS.md mit eigenem Inhalt.

        Aktion: ``global_agents_create()``.
        Erwartung: Der Inhalt bleibt byte-identisch.
        """
        self.write_global()
        before = self.path.read_bytes()
        self.cli.global_agents_create()
        self.assertEqual(self.path.read_bytes(), before,
                         "create() überschrieb eine vorhandene Datei")

    @unittest.skipUnless(SYMLINKS_SUPPORTED,
                         "os.symlink funktioniert in der Prüfumgebung nicht")
    def test_create_rejects_a_symlink(self):
        """Vorbedingung: AGENTS.md ist ein Symlink.

        Erwartung: ``ValueError``; das Ziel bleibt unverändert.
        """
        target = self.make_symlink()
        original = target.read_bytes()
        with self.assertRaises(ValueError):
            self.cli.global_agents_create()
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(self.path.is_symlink())


class GlobalAgentsApiTest(unittest.TestCase):
    """GET /api/global_agents_file und POST save/create."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.xdg = cls.root / "xdg"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        (cls.xdg / "opencode").mkdir(parents=True)
        cls.path = cls.xdg / "opencode" / "AGENTS.md"
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.port = free_port()
        env = isolated_environ(cls.home, XDG_CONFIG_HOME=str(cls.xdg))
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.root / "_toolchain"),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.path.unlink(missing_ok=True)

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method="POST" if data else "GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def test_get_missing_file_reports_an_empty_view(self):
        """Vorbedingung: keine globale AGENTS.md im XDG-Ordner.

        Erwartung: ``GET`` antwortet 200 mit ``exists`` falsch, leerem Text und
        Pfadhinweis.
        """
        status, payload = self.request("/api/global_agents_file")
        self.assertEqual(200, status, payload)
        self.assertFalse(payload.get("exists"), payload)
        self.assertEqual("", payload.get("text"), payload)
        self.assertTrue(str(payload.get("path_hint") or "").strip(), payload)

    def test_save_and_create_work_over_the_handler(self):
        """Vorbedingung: keine Datei.

        Aktion: ``{action:"create"}``, dann ``{action:"save", text, digest}``.
        Erwartung: Die Vorlage entsteht; Speichern mit aktuellem Digest
        schreibt den Text und liefert einen passenden Digest.
        """
        status, payload = self.request(
            "/api/global_agents_file", {"action": "create"})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertTrue(self.path.is_file(), "create legte keine Datei an")

        status, view = self.request("/api/global_agents_file")
        self.assertEqual(200, status, view)
        status, payload = self.request("/api/global_agents_file", {
            "action": "save", "text": GLOBAL_TEXT_NEW,
            "digest": view.get("digest")})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"),
                         GLOBAL_TEXT_NEW)
        self.assertEqual(
            payload.get("digest"),
            hashlib.sha256(GLOBAL_TEXT_NEW.encode("utf-8")).hexdigest(),
            "Die Antwort nennt keinen passenden Digest: " + repr(payload))

    def test_save_with_a_stale_digest_is_rejected(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Aktion: Speichern mit falschem Digest.
        Erwartung: Status 400, ``ok`` falsch, Datei unverändert.
        """
        self.path.write_text(GLOBAL_TEXT, encoding="utf-8")
        status, payload = self.request("/api/global_agents_file", {
            "action": "save", "text": GLOBAL_TEXT_NEW, "digest": "0" * 64})
        self.assertEqual(400, status, payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), GLOBAL_TEXT)


if __name__ == "__main__":
    unittest.main()
