"""Abnahme B17: Testläufe dürfen die laufende Instanz nicht verändern.

Arbeitspaket B17 (FEEDBACK.md) beschreibt den Vorfall vom 19.11.2026: Der
AP-Lauf exportiert Produktivpfade (``VIBE_INSTALL``, ``VIBE_STATE``,
``VIBE_RUNTIME``, ``VIBE_CONFIG_FILE``). Ein Test rief ``setup.main(...,
'--update')`` in-process auf; ``main`` hatte keinen ``environ``-Parameter und
löste Installations-/Logpfade aus ``os.environ`` auf. Dadurch wurde die echte
Installation aktualisiert.

Die Tests in dieser Datei bilden den Vorfall mit ausschließlich temporären
Fake-Produktivpfaden nach. Sie rufen den Setup nie in einer simulierten
Produktivumgebung ohne ``environ=`` auf: Die Vorfall-Umgebung wird
ausschließlich über den neuen Parameter ``environ`` übergeben. In der
Rotphase bricht der Aufruf mit ``TypeError`` ab, bevor irgendetwas geschrieben
wird.

Geprüfte Soll-Semantik:

* ``setup.main(..., environ=...)`` nutzt für alle Pfadauflösungen
  ausschließlich das übergebene ``environ`` (``None`` bleibt ``os.environ``).
* Ein ``--update`` auf die laufende Instanz wird ohne explizite autorisierte
  Quelle ``--source`` verweigert; ``--dry-run`` bleibt erlaubt. Das gilt auch,
  wenn das laufende Ziel ausdrücklich als ``--install`` genannt wird
  (Review 1, Finding 3).
* Mit ``--source`` wird das benannte Verzeichnis als Kit verwendet und in
  ``version.json`` als ``source`` vermerkt.
* Ein Test-Update schreibt ausschließlich unter den Temp-Root.

Run:

    env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE \
        -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR \
        python3 -m unittest tests.unit.test_b17_isolation -v
"""
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "scripts" / "setup-vibe.py"
WRAPPER = REPO / "install-vibe.sh"

PROGRAM_FILES = (
    "vibe",
    "vibe-run.sh",
    "vibe_runs.py",
    "vibe_packages.py",
    "vibe-web.py",
    "vibe_mcp.py",
    "vibe_opencode.py",
    "vibe_models.py",
    "vibe_sandbox.py",
    "vibe_paths.py",
    "vibe_ui_config.py",
    "vibe_storage.py",
    "vibe_guide.py",
    "vibe_questions.py",
    "vibe_autonomous.py",
    "vibe_harness.py",
    "vibe_limits.py",
    "vibe_gates.py",
    "vibe_services.py",
    "vibe_github.py",
    "vibe_issues.py",
    "fritz-reconnect.py",
)
WEB_FILES = (
    "index.html", "styles.css", "app.js", "i18n.js",
    "classic.html", "nova.css", "nova-core.js", "nova-home.js",
    "nova-project.js", "nova-output.js", "nova-agents.js",
    "nova-activity.js", "nova-settings.js",
)

# Variablen, die im Vorfall Produktivpfade trugen. Ein Test darf sie nie aus
# dem Prozess erben; die Vorfall-Umgebung wird nur als ``environ`` übergeben.
INCIDENT_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
)


setup = None


def setUpModule():
    global setup
    loader = importlib.machinery.SourceFileLoader("setup_vibe_b17", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module


def make_kit(root, version="0.18.0"):
    """Minimales Kit-Abbild; alle Programmdateien und Vorlagen sind vorhanden."""
    root = Path(root)
    (root / "bin").mkdir(parents=True)
    for name in PROGRAM_FILES:
        (root / "bin" / name).write_text(
            "#!/usr/bin/env python3\n# " + name + "\n", encoding="utf-8"
        )
    (root / "bin" / "web").mkdir()
    for name in WEB_FILES:
        (root / "bin" / "web" / name).write_text("/* " + name + " */\n", encoding="utf-8")
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    templates = root / "templates" / "generic" / ".vibe"
    templates.mkdir(parents=True)
    (templates / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
    (root / "templates" / "generic" / "AGENTS.md").write_text("# generic\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "models.json").write_text('{"models": []}\n', encoding="utf-8")
    return root


def essential_which(name):
    """Alle benötigten Werkzeuge gelten als vorhanden, tmux aber nicht.

    ``tmux`` bleibt absichtlich unsichtbar: ``running_installation`` soll keine
    Sitzung prüfen und damit keine echte Umgebung des Rechners anfassen.
    """
    return None if name == "tmux" else "/fake/" + name


def platform_info():
    return {
        "os": "linux",
        "distro": "ubuntu",
        "family": "debian",
        "manager": "apt-get",
        "container": True,
        "immutable": False,
        "wsl": False,
        "wsl_available": False,
        "npm_available": True,
        "label": "Test-Container",
        "release": {},
    }


def snapshot(root):
    """SHA-256 je Datei relativ zum Wurzelordner."""
    root = Path(root)
    digests = {}
    if not root.exists():
        return digests
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


class B17Base(unittest.TestCase):
    """Fake-Produktivbereich und ein davon getrennter Temp-Prüfbereich."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        # Fake-Produktivbereich: sieht aus wie die laufende Installation des
        # Vorfalls, liegt aber vollständig unter tempfile.
        self.prod_root = self.root / "produktion"
        self.fake_home = self.prod_root / "home"
        self.fake_workspace = self.prod_root / "VibeCode"
        self.fake_install = self.fake_workspace / "_toolchain"
        # Eigener Laufzeitordner (nicht <workspace>/_logs), damit ein
        # unveränderter Reuse-Lauf die Fake-Konfiguration nicht neu schreibt.
        self.fake_runtime = self.prod_root / "runtime"
        self.fake_config = self.fake_home / ".config" / "vibe" / "config.json"
        self._make_fake_installation()

        # Prüfbereich: alle schreibenden Soll-Pfade.
        self.temp_root = self.root / "pruefung"
        self.temp_root.mkdir()

        self.kit = make_kit(self.root / "kit")

        self.incident_environ = {
            "HOME": str(self.fake_home),
            "VIBE": str(self.fake_workspace),
            "VIBE_INSTALL": str(self.fake_install),
            "VIBE_STATE": str(self.fake_install),
            "VIBE_RUNTIME": str(self.fake_runtime),
            "VIBE_CONFIG_FILE": str(self.fake_config),
            "PATH": os.environ.get("PATH", ""),
        }

    def _make_fake_installation(self):
        (self.fake_install / "bin").mkdir(parents=True)
        (self.fake_install / "bin" / "vibe").write_text(
            "#!/bin/sh\necho vibe\n", encoding="utf-8"
        )
        write_json(self.fake_install / "harness.json", {"harness": "opencode"})
        write_json(
            self.fake_install / "version.json",
            {"version": "0.1.0", "mode": "update", "source": str(self.fake_install)},
        )
        write_json(
            self.fake_config,
            {
                "profiles": {
                    "prod": {
                        "workspace": str(self.fake_workspace),
                        "install": str(self.fake_install),
                        "state": str(self.fake_install),
                        "runtime": str(self.fake_runtime),
                    }
                }
            },
        )

    def runner(self, command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "")

    def run_main(self, args, environ=None, kit=None):
        out = io.StringIO()
        code = setup.main(
            list(args),
            output=lambda text="": out.write(str(text) + "\n"),
            which=essential_which,
            runner=self.runner,
            platform_info=platform_info(),
            kit=kit or self.kit,
            interactive=False,
            is_root=True,
            has_sudo=False,
            environ=self.incident_environ if environ is None else environ,
        )
        return code, out.getvalue()

    def clean_environ(self, home):
        return {"HOME": str(home), "PATH": os.environ.get("PATH", "")}

    def assert_prod_unchanged(self, before):
        self.assertEqual(before, snapshot(self.prod_root),
                         "Der Fake-Produktivbereich wurde verändert")
        self.assertEqual(
            [], sorted(self.fake_install.glob("backup-*")),
            "Im Fake-Produktivbereich entstand eine Sicherung",
        )


class MainEnvironTest(B17Base):
    """AK1: main löst alle Pfade aus dem übergebenen environ auf."""

    def test_dry_run_resolves_defaults_from_the_given_environ(self):
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        environ = {
            "HOME": str(home),
            "VIBE": str(workspace),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(["--yes", "--dry-run"], environ=environ)

        self.assertEqual(code, 0, output)
        self.assertIn(str(workspace), output)
        self.assertIn(str(install), output)
        self.assertIn(str(runtime), output)
        self.assertIn(
            str(home / ".config" / "vibe" / "config.json"), output,
            "Die dry-run-Ausgabe nennt nicht den Konfigurationspfad aus environ",
        )
        # Eine Vorschau schreibt nichts.
        self.assertFalse(workspace.exists(), output)
        self.assertFalse(install.exists(), output)

    def test_closing_hint_reads_the_given_environ(self):
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        other_vibe = self.temp_root / "andere-quelle"
        environ = {
            "HOME": str(home),
            "VIBE": str(other_vibe),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(
            ["--yes", "--skip-deps", "--no-launcher", "--no-register",
             "--vibe", str(workspace), "--install", str(install),
             "--logs", str(runtime)],
            environ=environ,
        )

        self.assertEqual(code, 0, output)
        self.assertIn("Hinweis: VIBE=" + str(other_vibe), output)
        self.assertFalse(other_vibe.exists(), output)


class UpdateGuardTest(B17Base):
    """AK2: --update auf die laufende Instanz wird ohne --source verweigert."""

    def test_update_on_the_running_instance_is_refused_without_writes(self):
        before = snapshot(self.prod_root)
        temp_workspace = self.temp_root / "Arbeitsbereich"

        code, output = self.run_main([
            "--vibe", str(temp_workspace), "--update", "--yes",
            "--skip-deps", "--no-launcher", "--no-register",
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("--source", output,
                      "Die Verweigerung muss die autorisierte Quelle nennen")
        self.assert_prod_unchanged(before)
        self.assertFalse(temp_workspace.exists(),
                         "Trotz Verweigerung wurde ein Workspace angelegt")

    def test_update_with_an_explicit_install_on_the_running_instance_is_refused(self):
        """Review 1/Medium: Ein explizites ``--install`` befreit den Guard nicht.

        Zeigt ``--install`` auf die erkannte laufende Installation, ist das
        ebenso eine Aktualisierung der laufenden Instanz wie das implizit
        aufgelöste Ziel. Ohne ``--source`` darf sie nichts schreiben.
        """
        before = snapshot(self.prod_root)

        code, output = self.run_main([
            "--vibe", str(self.fake_workspace), "--install", str(self.fake_install),
            "--update", "--yes", "--skip-deps", "--no-launcher", "--no-register",
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("--source", output,
                      "Die Verweigerung muss die autorisierte Quelle nennen")
        self.assert_prod_unchanged(before)

    def test_update_with_an_explicit_install_and_source_is_allowed(self):
        """Gegenprobe: ``--source`` autorisiert dasselbe explizite Ziel."""
        kit = make_kit(self.temp_root / "kit-quelle", version="9.9.9")

        code, output = self.run_main([
            "--vibe", str(self.fake_workspace), "--install", str(self.fake_install),
            "--update", "--yes", "--skip-deps", "--no-launcher", "--no-register",
            "--source", str(kit),
        ])

        self.assertEqual(code, 0, output)
        recorded = json.loads(
            (self.fake_install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded["version"], "9.9.9",
                         "Das autorisierte Update hat die Installation nicht aktualisiert")
        self.assertEqual(Path(recorded["source"]), kit.resolve())

    def test_dry_run_on_the_running_instance_is_allowed_and_explains_the_guard(self):
        before = snapshot(self.prod_root)

        code, output = self.run_main(["--yes", "--dry-run", "--update"])

        self.assertEqual(code, 0, output)
        self.assertIn("--source", output,
                      "Auch die Vorschau muss den Guard-Hinweis zeigen")
        self.assert_prod_unchanged(before)

    def test_reuse_on_the_running_instance_is_not_blocked(self):
        """``--reuse`` ist keine autorisierte Aktualisierung.

        Der Guard betrifft nur ``--update``. Wiederverwenden darf fehlende
        Dateien ergänzen, aber keine vorhandenen überschreiben und keine
        Sicherung anlegen. Die globale Konfiguration bleibt unverändert.
        """
        config_before = snapshot(self.fake_home)
        existing = {}
        for name in ("bin/vibe", "harness.json", "version.json"):
            path = self.fake_install / name
            existing[name] = path.read_bytes()

        code, output = self.run_main([
            "--reuse", "--yes", "--skip-deps", "--no-launcher", "--no-register",
            "--vibe", str(self.fake_workspace), "--logs", str(self.fake_runtime),
        ])

        self.assertEqual(code, 0, output)
        for name, content in existing.items():
            self.assertEqual(
                (self.fake_install / name).read_bytes(), content,
                "Wiederverwenden hat " + name + " überschrieben",
            )
        self.assertEqual(
            [], sorted(self.fake_install.glob("backup-*")),
            "Wiederverwenden legte eine Sicherung an",
        )
        self.assertEqual(
            config_before, snapshot(self.fake_home),
            "Wiederverwenden hat die Konfiguration neu geschrieben",
        )


class IsolatedUpdateTest(B17Base):
    """AK4/AK5: Ein Test-Update schreibt ausschließlich unter den Temp-Root."""

    def test_test_update_writes_only_into_the_temp_root(self):
        """AK5: Ein Test--update schreibt ausschließlich in den Temp-Root.

        Die Prüf-Installation simuliert eine bestehende Installation. Nach dem
        Update liegen Programmdateien, Sicherung, ``version.json`` und die
        Konfiguration unter dem Temp-Root; der Fake-Produktivbereich bleibt
        byte-identisch.
        """
        before = snapshot(self.prod_root)
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        (install / "bin").mkdir(parents=True)
        (install / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")

        code, output = self.run_main(
            ["--update", "--yes", "--skip-deps", "--no-launcher",
             "--no-register", "--vibe", str(workspace),
             "--install", str(install), "--logs", str(runtime)],
            environ=self.clean_environ(home),
        )

        self.assertEqual(code, 0, output)
        self.assertNotEqual(
            (install / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n",
            "Das Test--update hat die Prüf-Installation nicht aktualisiert",
        )
        self.assertTrue((install / "harness.json").is_file(), output)
        self.assertTrue((install / "version.json").is_file(), output)
        self.assertTrue(
            list(install.glob("backup-*")),
            "Das Update legte keine Sicherung unter dem Temp-Root an",
        )
        recorded = json.loads(
            (install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(Path(recorded["source"]), self.kit.resolve())
        config_path = home / ".config" / "vibe" / "config.json"
        self.assertTrue(config_path.is_file(), output)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        prod = data["profiles"]["prod"]
        self.assertEqual(prod["workspace"], str(workspace))
        self.assertEqual(prod["install"], str(install))
        self.assertEqual(prod["runtime"], str(runtime))
        self.assert_prod_unchanged(before)

    def test_environ_install_target_wins_without_a_cli_option(self):
        before = snapshot(self.prod_root)
        home = self.temp_root / "home"
        workspace = self.temp_root / "EnvironWorkspace"
        install = self.temp_root / "environ-toolchain"
        runtime = self.temp_root / "environ-logs"
        environ = {
            "HOME": str(home),
            "VIBE": str(workspace),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(
            ["--yes", "--skip-deps", "--no-launcher", "--no-register"],
            environ=environ,
        )

        self.assertEqual(code, 0, output)
        self.assertTrue((install / "bin" / "vibe").is_file(),
                        "Das Installationsziel kam nicht aus environ:\n" + output)
        self.assertFalse(
            (home / "VibeCode" / "_toolchain").exists(),
            "Das Standardziel der Prozessumgebung wurde verwendet",
        )
        config_path = home / ".config" / "vibe" / "config.json"
        self.assertTrue(config_path.is_file(), output)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["profiles"]["prod"]["install"], str(install))
        self.assertEqual(data["profiles"]["prod"]["runtime"], str(runtime))
        self.assert_prod_unchanged(before)


class SourceOptionTest(B17Base):
    """AK3: --source benennt die autorisierte Quelle ausdrücklich."""

    def test_update_with_an_explicit_source_updates_the_instance(self):
        kit = make_kit(self.temp_root / "kit-quelle", version="9.9.9")

        code, output = self.run_main([
            "--update", "--yes", "--skip-deps", "--no-launcher",
            "--no-register", "--vibe", str(self.fake_workspace),
            "--source", str(kit),
        ])

        self.assertEqual(code, 0, output)
        recorded = json.loads(
            (self.fake_install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded["version"], "9.9.9")
        self.assertEqual(Path(recorded["source"]), kit.resolve(),
                         "version.json nennt nicht die benannte Quelle")

    def test_source_with_a_broken_directory_changes_nothing(self):
        before = snapshot(self.prod_root)
        broken = self.temp_root / "kaputte-quelle"
        broken.mkdir()

        code, output = self.run_main([
            "--update", "--yes", "--skip-deps", "--no-launcher",
            "--no-register", "--vibe", str(self.fake_workspace),
            "--source", str(broken),
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("Unvollständiges Quellverzeichnis", output)
        self.assert_prod_unchanged(before)

    def test_install_wrapper_names_its_own_source(self):
        text = WRAPPER.read_text(encoding="utf-8")

        self.assertIn("--source", text)
        self.assertIn('"$KIT"', text)


if __name__ == "__main__":
    unittest.main()
