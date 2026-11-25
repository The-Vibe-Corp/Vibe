"""Unit-Tests F31: AGENTS.md in der Assistent-Ansicht ansehen und bearbeiten.

Ableitung ausschließlich aus dem Arbeitspaket F31 und SPEC.md/AGENTS.md, nicht
aus einer Implementierung. Geprüft werden die geplanten Schnittstellen in
``bin/vibe``:

* ``agents_file_view(name)`` — liest AGENTS.md und trennt die freien Teile vom
  verwalteten Bestandsblock samt Digest.
* ``agents_file_save(name, before, after, digest)`` — schreibt die freien Teile
  zusammen mit dem byte-identischen vorhandenen Block atomar über die
  Speicherschicht (V-005); ohne Block werden ``before`` und ``after``
  gemeinsam geschrieben (GH-76: blockfreie Dateien sind der Normalfall).
  Überholte Digests und Marker in den freien Teilen werden abgewiesen, ohne
  die Datei zu verändern.
* ``agents_file_create(name)`` — legt eine fehlende AGENTS.md aus der
  Typ-Vorlage an, überschreibt niemals eine vorhandene Datei.

Alle Tests arbeiten in einem isolierten temporären Arbeitsbereich mit eigenen
Vorlagen; keine produktiven HOME-/VIBE-Konfigurationen, keine Modellaufrufe.
"""
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


if __name__ == "__main__":
    unittest.main()
