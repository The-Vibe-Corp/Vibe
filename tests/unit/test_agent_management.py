"""Agentenverwaltung: Rollen, Metadaten, Hierarchie, Projekt- und globale Agenten, Templates, opencode-Berechtigungssyntax, Subagentenrechte und Agentendatei-Sicherungen.

Aufruf: python3 -m unittest tests.unit.test_agent_management -v
"""


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

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

AGENT_V1 = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
temperature: 0.1
steps: 20
color: blau
tools:
  write: true
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""

AGENT_V2 = """---
description: Zweite Beschreibung
mode: subagent
model: opencode/test-modell
permission:
  edit: deny
---

Zweiter Prompt.
"""


# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
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


def isolated_env(root, home, port=None):
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
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
            "vibe_agent_management_under_test", str(CLI)
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


class AgentFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        self.other = self.root / "other"
        (self.other / ".vibe").mkdir(parents=True)
        (self.other / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        self.cli = load_cli(self.root, self.home)
        # Die Versionsprüfung wird je Test frisch ausgeführt, damit Attrappen
        # nicht durch einen früheren Test verdeckt werden.
        self.cli._AGENT_VERSION = None
        # Kein Modellaufruf und keine Anbieterabfrage in der Prüfung: das
        # Modelllisting gehört nicht zur Agentenverwaltung und würde je
        # Schreibvorgang einen opencode-Prozess starten.
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def global_path(self, name="tester"):
        return self.agents / (name + ".md")

    def project_path(self, project, name="tester"):
        return project / ".opencode" / "agents" / (name + ".md")

    def write_global(self, name="tester", text=AGENT_V1):
        snapshot = self.cli.vibe_storage.read_snapshot(self.global_path(name))
        self.cli.agent_write(
            "global",
            name,
            text,
            create=not snapshot.exists,
            expected=snapshot.digest if snapshot.exists else self.cli.vibe_storage.MISSING,
        )
        return self.global_path(name)

    def write_project(self, project, name="tester", text=AGENT_V1):
        path = self.project_path(project, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.cli.vibe_storage.read_snapshot(path)
        # agent_write erwartet den Projektnamen, nicht den absoluten Pfad.
        self.cli.agent_write(
            Path(project).name,
            name,
            text,
            create=not snapshot.exists,
            expected=snapshot.digest if snapshot.exists else self.cli.vibe_storage.MISSING,
        )
        return path

    def rows(self):
        return {(row["name"], row["scope"]): row for row in self.cli.agents_all()}


class InvalidFrontmatterTest(AgentFixture):
    def test_invalid_frontmatter_is_rejected_without_touching_the_file(self):
        path = self.write_global()
        before = path.read_text(encoding="utf-8")
        digest = self.cli.agent_snapshot("global", "tester").digest
        broken = (
            "kein Frontmatter\n",
            "---\nmode: subagent\n---\nPrompt\n",
            "---\ndescription: Test\nmode: falsch\n---\nPrompt\n",
            "---\ndescription: eins\ndescription: zwei\nmode: subagent\n---\nPrompt\n",
            "---\ndescription: Test\nmode: subagent\n---\n\n",
        )
        for text in broken:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.cli.agent_write(
                        "global", "tester", text, expected=digest
                    )
                self.assertEqual(path.read_text(encoding="utf-8"), before)


class DuplicateAndPriorityTest(AgentFixture):
    def test_project_agent_overrides_global_agent_and_shadowing_is_visible(self):
        self.write_global()
        self.write_project(self.project)

        rows = self.rows()
        global_row = rows[("tester", "global")]
        project_row = rows[("tester", "proj")]

        self.assertTrue(global_row["conflict"])
        self.assertTrue(project_row["conflict"])
        self.assertTrue(global_row["shadow"])
        self.assertIn("proj", global_row["overridden_in"])
        self.assertEqual(project_row["overrides"], "global")
        self.assertIn("überschreibt global", project_row["priority"])
        self.assertIn("überschrieben", global_row["priority"])

    def test_copy_to_an_existing_target_is_refused_and_changes_nothing(self):
        self.write_global()
        target = self.write_project(self.project, text=AGENT_V2)
        before = target.read_text(encoding="utf-8")

        with self.assertRaises(ValueError) as raised:
            self.cli.agent_copy("global", "tester", "proj")
        self.assertIn("existiert", str(raised.exception))
        self.assertEqual(target.read_text(encoding="utf-8"), before)

        with self.assertRaises(ValueError):
            self.cli.agent_write(
                "global",
                "tester",
                AGENT_V1,
                create=True,
                expected=self.cli.vibe_storage.MISSING,
            )

    def test_same_name_in_two_projects_stays_independent(self):
        self.write_project(self.project)
        self.write_project(self.other, text=AGENT_V2)

        rows = self.rows()
        first = rows[("tester", "proj")]
        second = rows[("tester", "other")]

        self.assertFalse(first["conflict"], "Gleicher Name in zwei Projekten ist kein Konflikt")
        self.assertFalse(second["conflict"])
        self.assertEqual(first["priority"], "gilt nur in proj")
        self.assertEqual(second["priority"], "gilt nur in other")
        self.assertEqual(first["overrides"], "")
        self.assertEqual(second["overrides"], "")

    def test_effective_agent_follows_the_project_over_global_rule(self):
        self.write_global()

        self.assertEqual(self.cli.effective_agent("tester", "global"), "global")
        self.assertEqual(self.cli.effective_agent("tester", "proj"), "global")
        self.assertEqual(self.cli.effective_agent("tester", "other"), "global")

        self.write_project(self.project)
        self.assertEqual(self.cli.effective_agent("tester", "proj"), "proj")
        self.assertEqual(self.cli.effective_agent("tester", "other"), "global")


class NameSafetyTest(AgentFixture):
    def test_path_traversal_and_invalid_names_are_rejected(self):
        self.write_global()
        for name in ("../evil", "a/b", "..", "/abs", "a b", "", "A-upper"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.cli.agent_path("global", name)
        with self.assertRaises(ValueError):
            self.cli.agent_read("global", "../evil")
        with self.assertRaises(ValueError):
            self.cli.agent_backups("global", "../evil")


class StructuredEditorTest(AgentFixture):
    def test_structured_fields_preserve_unknown_frontmatter_fields(self):
        fields = self.cli.agent_fields("global", AGENT_V1)
        self.assertEqual(fields["description"], "Erste Beschreibung")
        self.assertEqual(fields["mode"], "subagent")
        self.assertEqual(fields["model"], "opencode/test-modell")
        self.assertEqual(fields["temperature"], "0.1")
        self.assertEqual(fields["steps"], "20")
        self.assertEqual(fields["prompt"].strip(), "Erster Prompt.")
        self.assertIn("color", fields["unknown"])
        self.assertIn("tools", fields["unknown"])

        changed = self.cli.agent_render_fields(
            "global",
            AGENT_V1,
            {
                "description": "Neue Beschreibung",
                "mode": "primary",
                "model": "opencode/neu",
                "temperature": "0.7",
                "steps": "5",
                "permission": "lesen",
                "prompt": "Neuer Prompt.",
            },
        )

        self.assertIn("description: Neue Beschreibung", changed)
        self.assertIn("mode: primary", changed)
        self.assertIn("model: opencode/neu", changed)
        self.assertIn("temperature: 0.7", changed)
        self.assertIn("steps: 5", changed)
        self.assertIn("color: blau", changed)
        self.assertIn("tools:\n  write: true", changed)
        self.assertIn("permissions:\n  - action: read", changed)
        self.assertIn("action: edit", changed)
        self.assertIn("effect: deny", changed)
        self.assertIn("Neuer Prompt.", changed)
        self.assertNotIn("Erster Prompt.", changed)
        self.assertTrue(changed.endswith("\n"))

    def test_render_adds_a_permission_block_when_the_file_has_none(self):
        text = (
            "---\n"
            "description: Ohne Rechte\n"
            "mode: subagent\n"
            "color: blau\n"
            "---\n"
            "\n"
            "Prompt ohne Rechteblock.\n"
        )

        changed = self.cli.agent_render_fields("global", text, {"permission": "lesen"})

        self.assertIn("permissions:\n  - action: read", changed)
        self.assertIn("action: edit", changed)
        self.assertIn("effect: deny", changed)
        self.assertIn("color: blau", changed)
        fields = self.cli.agent_fields("global", changed)
        self.assertEqual(fields["permission"], "lesen")
        self.assertIn("color", fields["unknown"])

    def test_structured_editor_decodes_quoted_values_without_escape_artifacts(self):
        text = (
            "---\n"
            'description: "Agent: sagt \\"hallo\\""\n'
            "mode: subagent\n"
            "---\n"
            "\n"
            "Prompt.\n"
        )

        fields = self.cli.agent_fields("global", text)
        self.assertEqual(fields["description"], 'Agent: sagt "hallo"')

        changed = self.cli.agent_render_fields(
            "global", text, {"description": fields["description"]}
        )
        self.assertIn('description: "Agent: sagt \\"hallo\\""', changed)
        self.assertEqual(
            self.cli.agent_fields("global", changed)["description"],
            'Agent: sagt "hallo"',
        )

    def test_values_with_yaml_special_leading_characters_are_quoted(self):
        # Ein unbekanntes YAML-Sonderzeichen am Anfang würde den Wert als
        # Sequenz, Alias, Tag oder Block deuten und das Frontmatter zerstören.
        for value in (
            "[wichtig]",
            "{neu}",
            "*alias",
            "&anker",
            "!tag",
            "|block",
            ">fold",
            "%direktive",
            "@at",
            "`code`",
        ):
            with self.subTest(value=value):
                changed = self.cli.agent_render_fields(
                    "global", AGENT_V1, {"description": value}
                )
                self.assertIn(
                    "description: " + json.dumps(value, ensure_ascii=False), changed
                )
                self.assertEqual(
                    self.cli.agent_fields("global", changed)["description"], value
                )

    def test_invalid_structured_values_are_rejected_before_writing(self):
        path = self.write_global()
        before = path.read_text(encoding="utf-8")
        broken = (
            {"description": ""},
            {"description": "Zeile eins\nZeile zwei"},
            {"mode": "boese"},
            {"model": "opencode/modell mit leerzeichen"},
            {"temperature": "heiß"},
            {"temperature": "3"},
            {"steps": "0"},
            {"steps": "viele"},
            {"permission": "root"},
            {"prompt": ""},
        )
        for values in broken:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.cli.agent_render_fields("global", AGENT_V1, values)
                self.assertEqual(path.read_text(encoding="utf-8"), before)


class TemplateDraftTest(AgentFixture):
    def test_new_agent_draft_with_placeholder_description_can_be_created_but_not_saved(self):
        """`vibe agent new` schreibt einen Entwurf; erst das Speichern wird geprüft."""
        draft = self.cli.agent_template("Kurzbeschreibung eintragen", prompt="")

        self.assertTrue(draft.startswith("---\n"))
        self.assertIn("Kurzbeschreibung eintragen", draft)
        with self.assertRaises(ValueError) as raised:
            self.cli.agent_validate(draft)
        self.assertIn("Platzhalter", str(raised.exception))

    def test_template_rejects_values_with_line_breaks(self):
        with self.assertRaises(ValueError):
            self.cli.agent_template("Zeile eins\nZeile zwei")
        with self.assertRaises(ValueError):
            self.cli.agent_template("Test", model="opencode/x\nmode: primary")


class RawEditorFormattingTest(AgentFixture):
    def test_invalid_raw_frontmatter_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cli.agent_render_fields("global", "---\ndescription: Test\n", {"prompt": "x"})
        with self.assertRaises(ValueError):
            self.cli.agent_render_fields("global", AGENT_V1, "keine Felder")

    def test_render_keeps_a_file_without_prompt_valid(self):
        text = "---\ndescription: Ohne Prompt\nmode: subagent\n---"

        changed = self.cli.agent_render_fields("global", text, {"prompt": "Neuer Prompt."})

        self.assertTrue(changed.endswith("Neuer Prompt.\n"), repr(changed))
        self.assertIn("\n---\n", changed)
        fields = self.cli.agent_validate(changed)
        self.assertEqual(fields["description"], "Ohne Prompt")
        self.assertEqual(fields["mode"], "subagent")


class RestoreTest(AgentFixture):
    def test_backups_of_a_similarly_named_agent_are_not_offered_or_restored(self):
        self.write_global("tester")
        self.write_global("tester-2", text=AGENT_V2)
        second = self.cli.agent_snapshot("global", "tester-2")
        self.cli.agent_write("global", "tester-2", AGENT_V1, expected=second.digest)
        other_backups = self.cli.agent_backups("global", "tester-2")
        self.assertTrue(other_backups)

        # "tester-2-..." beginnt mit "tester-" und darf nicht als Sicherung
        # des Agenten "tester" gelten.
        self.assertEqual(self.cli.agent_backups("global", "tester"), [])
        with self.assertRaises(ValueError):
            self.cli.agent_restore("global", "tester", other_backups[-1])
        self.assertEqual(
            self.global_path("tester").read_text(encoding="utf-8"), AGENT_V1
        )

    def test_restore_brings_back_the_previous_version(self):
        path = self.write_global(text=AGENT_V1)
        first = self.cli.agent_snapshot("global", "tester")
        self.cli.agent_write("global", "tester", AGENT_V2, expected=first.digest)
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V2)

        backups = self.cli.agent_backups("global", "tester")
        self.assertTrue(backups)
        self.cli.agent_restore("global", "tester", backups[-1])
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V1)


class VersionAndRoleTest(AgentFixture):
    def test_agent_writes_warn_about_an_untested_version_instead_of_blocking(self):
        """Agentenregeln gelten unabhängig von der erkannten opencode-Version.

        V-007 hat die Regeln aus vorhandenen Agentendateien abgeleitet und
        ausdrücklich nicht an die geprüfte Version gebunden. Ein harter
        Versionsriegel würde die Agentenverwaltung nach jedem opencode-Update
        ohne fachlichen Grund sperren; die Warnung macht den Unterschied
        sichtbar, ohne die Datei unveränderbar zu machen.
        """
        info = self.cli.vibe_opencode.VersionInfo(
            "unknown", "opencode 9.9.9 ist nicht geprüft (geprüft: 2.1.4)."
        )
        with mock.patch.object(self.cli.vibe_opencode, "probe", return_value=info):
            self.cli._AGENT_VERSION = None
            warnings = self.cli.agent_write(
                "global",
                "tester",
                AGENT_V1,
                create=True,
                expected=self.cli.vibe_storage.MISSING,
            )

        self.assertTrue(self.global_path().exists())
        self.assertEqual(self.global_path().read_text(encoding="utf-8"), AGENT_V1)
        self.assertTrue(
            any("nicht geprüft" in warning for warning in warnings), warnings
        )
        self.assertTrue(
            any("Agentenregeln" in warning for warning in warnings), warnings
        )

    def test_agent_version_warning_warns_for_an_assumed_version(self):
        """Auch eine als "assumed" behandelte Version wird als ungeprüft gemeldet.

        Das Warnkriterium ist "nicht exakt geprüft", nicht das alte
        "supported=False": Eine Version mit Fallback-Profil gilt als
        unterstützt, darf aber nicht stillschweigend als geprüft gelten.
        """
        info = self.cli.vibe_opencode.VersionInfo(
            "assumed",
            "opencode 2.2.6 ist nicht geprüft (geprüft: 2.1.4).",
            version="2.2.6",
            profile=self.cli.vibe_opencode.PROFILES["2.1.4"],
        )
        with mock.patch.object(self.cli.vibe_opencode, "probe", return_value=info):
            self.cli._AGENT_VERSION = None

            warning = self.cli.agent_version_warning()

        self.assertIn("nicht geprüft", warning)
        self.assertIn("2.2.6", warning)

    def test_agent_version_warning_is_silent_for_the_checked_version(self):
        info = self.cli.vibe_opencode.VersionInfo(
            "supported",
            "opencode 2.1.4 ist geprüft.",
            version="2.1.4",
            profile=self.cli.vibe_opencode.PROFILES["2.1.4"],
        )
        with mock.patch.object(self.cli.vibe_opencode, "probe", return_value=info):
            self.cli._AGENT_VERSION = None

            warning = self.cli.agent_version_warning()

        self.assertEqual(warning, "")

    def test_roles_are_configured_instead_of_hardcoded_core_names(self):
        self.assertFalse(hasattr(self.cli, "CORE_AGENTS"))
        self.assertEqual(self.cli.profiles_load()["rollen"], {})

        self.write_global()
        data = self.cli.profiles_load()
        data["rollen"] = {"tester": "coder"}
        self.cli.profiles_save(data)

        row = self.rows()[("tester", "global")]
        self.assertEqual(row["role"], "coder")

        labels = [label for label, _ok, _hint in self.cli.doctor_checks()]
        self.assertTrue(any("tester" in label for label in labels))
        self.assertFalse(
            any("coding-agent_deepseek" in label for label in labels),
            "Doctor prüft weiterhin einen fest eingebauten Kernagenten",
        )


class RunnerAgentConfigTest(unittest.TestCase):
    """Der Paket-Läufer kennt keinen fest eingebauten Agentennamen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.calls = self.root / "opencode-calls"
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        support.install_runner(self.root / "_toolchain")
        fake = fakebin / "opencode"
        fake.write_text(
            "#!/usr/bin/env bash\nprintf 'x\\n' >> '" + str(self.calls) + "'\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.env = os.environ.copy()
        for key in ("AGENT", "VIBE_LOGNAME", "SANDBOX", "SANDBOX_TOOLS"):
            self.env.pop(key, None)
        self.env.update(
            {
                "VIBE": str(self.root),
                "HOME": str(self.root / "home"),
                "VIBE_MAX_PACKAGES": "1",
                "PATH": str(fakebin) + os.pathsep + self.env.get("PATH", ""),
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_runner_aborts_instead_of_using_a_built_in_agent_name(self):
        result = subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("Kein Agent", output)
        self.assertFalse(
            self.calls.exists(), "opencode wurde ohne konfigurierten Agenten gestartet"
        )


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AgentApiTest(unittest.TestCase):
    """Web-API: strukturierte Vorschau, Validierung und Wiederherstellung."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        # opencode startet beim Dashboard-Start Hilfsprozesse (z. B. npx), die
        # noch in das temporäre HOME schreiben. Sie laufen in der eigenen
        # Prozessgruppe des Servers und werden hier mit beendet, damit das
        # Aufräumen des Prüfverzeichnisses nicht mit ihnen kollidiert.
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.path = self.agents / "tester.md"
        self.path.write_text(AGENT_V1, encoding="utf-8")

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def test_api_exposes_structured_fields_and_backups(self):
        status, body = self.request("/api/agent?scope=global&name=tester")

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertEqual(data["text"], AGENT_V1)
        self.assertEqual(data["fields"]["description"], "Erste Beschreibung")
        self.assertEqual(data["fields"]["temperature"], "0.1")
        self.assertIn("color", data["fields"]["unknown"])
        self.assertIn("tools", data["fields"]["unknown"])
        self.assertEqual(data["backups"], [])

    def test_api_render_validates_and_never_writes(self):
        status, body = self.request(
            "/api/agent",
            {
                "action": "render",
                "scope": "global",
                "name": "tester",
                "text": AGENT_V1,
                "values": {"temperature": "heiß"},
            },
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Temperatur", json.loads(body)["message"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

        status, body = self.request(
            "/api/agent",
            {
                "action": "render",
                "scope": "global",
                "name": "tester",
                "text": AGENT_V1,
                "values": {"description": "Neu", "permission": "lesen"},
            },
        )
        self.assertEqual(status, 200, body)
        preview = json.loads(body)["text"]
        self.assertIn("description: Neu", preview)
        self.assertIn("color: blau", preview)
        self.assertIn("- action: read", preview)
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            AGENT_V1,
            "Die Vorschau darf die Datei nicht verändern",
        )

    def test_api_save_applies_changed_structured_values(self):
        status, body = self.request("/api/agent?scope=global&name=tester")
        digest = json.loads(body)["digest"]

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_V1,
                "values": {"model": "opencode/neu"},
                "expected": digest,
            },
        )

        self.assertEqual(status, 200, body)
        saved = self.path.read_text(encoding="utf-8")
        self.assertIn("model: opencode/neu", saved)
        # Nicht geänderte Felder und unbekannte Angaben bleiben erhalten.
        self.assertIn("description: Erste Beschreibung", saved)
        self.assertIn("temperature: 0.1", saved)
        self.assertIn("color: blau", saved)
        self.assertIn("Erster Prompt.", saved)

    def test_api_save_rejects_an_invalid_structured_value_without_writing(self):
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_V1,
                "values": {"temperature": "heiß"},
            },
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Temperatur", json.loads(body)["message"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_api_rejects_invalid_raw_text_and_keeps_the_file(self):
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": "kein Frontmatter\n",
            },
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Frontmatter", json.loads(body)["message"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_api_restores_a_backup(self):
        status, body = self.request("/api/agent?scope=global&name=tester")
        digest = json.loads(body)["digest"]
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_V2,
                "expected": digest,
            },
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V2)

        status, body = self.request("/api/agent?scope=global&name=tester")
        backups = json.loads(body)["backups"]
        self.assertTrue(backups, body)

        status, body = self.request(
            "/api/agent",
            {
                "action": "restore",
                "scope": "global",
                "name": "tester",
                "backup": backups[0],
            },
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["text"], AGENT_V1)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)


# ===========================================================================
# Agentenverwaltung: Backend- und Unit-Tests
# ===========================================================================

import contextlib
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

BIN = REPO / "bin"
CLI_ap03 = BIN / "vibe"
WEB_ap03 = BIN / "vibe-web.py"
SERVICES = BIN / "vibe_services.py"

AGENT_BASE = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

VIBE_AGENT_NO_MODEL = """---
description: Vibe-Agent ohne Modell
mode: primary
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV_ap03 = (
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
    "AGENT",
)


def isolated_env_agent_files(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_ap03:
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli_agent_files(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_ap03}
    for key in ISOLATED_ENV_ap03:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_agent_files(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap03_under_test", str(CLI_ap03)
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


def load_services():
    """Lädt bin/vibe_services.py mit den Modulen aus bin/."""
    sys.path.insert(0, str(BIN))
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_services_ap03_under_test", str(SERVICES)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(BIN))
        except ValueError:
            pass
    return module


def field(value, name):
    """Liest ein Feld aus einem Dict oder einem Objekt; die Schnittstelle erlaubt beides."""
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def task_agent(allowed, mode="subagent", model="opencode/test-modell", task=None):
    """Agentendatei mit einem ``permission.task``-Block."""
    lines = ["---", "description: Agent", "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines += ["permission:", "  read: allow", "  edit: deny"]
    if task is not None:
        lines.append("  task: " + task)
    else:
        lines.append("  task:")
        lines.append('    "*": deny')
        for agent in allowed:
            lines.append("    " + agent + ": allow")
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


class Ap03Fixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.other = self.make_project("other")
        self.cli = load_cli_agent_files(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        return project

    def write_global(self, name="tester", text=AGENT_BASE):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name="lokal", text=AGENT_BASE):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def write_vibe(self, name="vibe-agent", text=VIBE_AGENT):
        path = self.write_global(name, text)
        roles = dict(self.cli.profiles_load().get("rollen", {}))
        roles[name] = "vibe"
        self.set_roles(roles)
        return path

    def config_path(self, project=None):
        return (project or self.project) / ".vibe" / "agents.json"

    def rows(self, project="proj"):
        return {row["name"]: row for row in self.cli.project_agent_rows(project)}

    def cmd_run(self, project="proj", agent=None):
        """Ruft cmd_run mit allen externen Grenzen als Attrappen auf."""
        calls = []
        self.run_mock = mock.Mock(
            side_effect=lambda argv, **kwargs: calls.append(argv) or (0, "")
        )
        registry = mock.MagicMock()
        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with contextlib.nullcontext():
                        with mock.patch.object(
                            self.cli, "run_registry", return_value=registry
                        ):
                            with mock.patch.object(
                                self.cli.vibe_runs, "rotate_log"
                            ):
                                with mock.patch.object(
                                    self.cli, "run", self.run_mock
                                ):
                                    self.cli.cmd_run(project, agent)
        return calls


class VibeRoleTest(Ap03Fixture):
    """AK Rollen und Vibe-Agent."""

    def test_role_assignment_and_removal_for_non_vibe(self):
        self.write_global("tester")

        self.cli.agent_role_set("tester", "coder")
        self.assertEqual(
            self.cli.profiles_load()["rollen"].get("tester"), "coder"
        )

        self.cli.agent_role_set("tester", "")
        self.assertNotIn("tester", self.cli.profiles_load()["rollen"])

    def test_vibe_role_is_unique_and_cannot_be_removed_without_replacement(self):
        self.write_global("vibe-agent")
        self.write_global("second")

        self.cli.agent_role_set("vibe-agent", "vibe")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "")
        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "coder")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        # Umsetzen ist nur durch gleichzeitige Zuweisung an einen anderen
        # Agenten möglich; danach darf genau einer die Rolle tragen.
        self.cli.agent_role_set("second", "vibe")
        roles = self.cli.profiles_load()["rollen"]
        vibe_names = [name for name, role in roles.items() if role == "vibe"]
        self.assertEqual(vibe_names, ["second"])
        self.assertEqual(self.cli.vibe_agent_name(), "second")

    def test_vibe_agent_status_without_agent_reports_missing(self):
        status = self.cli.vibe_agent_status()

        self.assertFalse(field(status, "name"))
        self.assertFalse(field(status, "configured"))
        self.assertTrue(field(status, "missing_model"))

    def test_vibe_agent_status_without_model_reports_missing_model(self):
        self.write_global("vibe-agent", VIBE_AGENT_NO_MODEL)
        self.set_roles({"vibe-agent": "vibe"})

        status = self.cli.vibe_agent_status()

        self.assertEqual(field(status, "name"), "vibe-agent")
        self.assertFalse(field(status, "model"))
        self.assertFalse(field(status, "configured"))
        self.assertTrue(field(status, "missing_model"))

    def test_vibe_agent_status_with_model_is_configured(self):
        self.write_vibe()

        status = self.cli.vibe_agent_status()

        self.assertEqual(field(status, "name"), "vibe-agent")
        self.assertEqual(field(status, "model"), "opencode/vibe-modell")
        self.assertTrue(field(status, "configured"))
        self.assertFalse(field(status, "missing_model"))


class VibeRunGateTest(Ap03Fixture):
    """AK Rollen und Vibe-Agent: Projekte starten nur mit konfiguriertem Vibe-Agenten."""

    def test_cmd_run_aborts_without_a_vibe_agent(self):
        self.write_global("tester")

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertTrue(
            "vibe-agent" in message or "vibe agent" in message, message
        )
        self.run_mock.assert_not_called()

    def test_cmd_run_aborts_when_the_vibe_agent_has_no_model(self):
        self.write_global("vibe-agent", VIBE_AGENT_NO_MODEL)
        self.set_roles({"vibe-agent": "vibe"})

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertIn("vibe", message)
        self.assertIn("modell", message)
        self.run_mock.assert_not_called()

    def test_cmd_run_aborts_without_a_model_even_when_agent_is_set(self):
        # Ein Vibe-Agent ohne Modell sperrt jeden Lauf, auch wenn in der
        # Projektdatei noch ein alter AGENT-Eintrag steht. Die Ausnahme für
        # Altbestände gilt nur, solange gar kein Vibe-Agent definiert ist.
        self.write_global("tester")
        self.write_vibe("vibe-agent", VIBE_AGENT_NO_MODEL)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertIn("vibe", message)
        self.assertIn("modell", message)
        self.run_mock.assert_not_called()

    def test_cmd_run_uses_the_vibe_agent_when_no_agent_is_configured(self):
        self.write_vibe()

        calls = self.cmd_run()

        self.assertEqual(len(calls), 1)
        # Der Agent ist das vorletzte Argument; das letzte ist die (leere)
        # Modellüberschreibung des Projekts.
        self.assertEqual(calls[0][-2], "vibe-agent")

    def test_cmd_run_prefers_the_vibe_agent_over_a_coder_role(self):
        self.write_vibe()
        self.write_global("tester")
        self.set_roles({"vibe-agent": "vibe", "tester": "coder"})

        calls = self.cmd_run()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2], "vibe-agent")


class AgentMetadataTest(Ap03Fixture):
    """AK Aufgaben/Ergebnisse: eigene Zustandsdatei statt Agentendatei."""

    def test_agent_result_is_stored_outside_the_agent_file(self):
        path = self.write_global("tester")
        before = path.read_text(encoding="utf-8")

        self.cli.agent_result_set("tester", "Ergebnis: fertig")
        self.assertEqual(self.cli.agent_result("tester"), "Ergebnis: fertig")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

        meta = self.cli.agent_meta_load()
        self.assertIn("Ergebnis: fertig", json.dumps(meta, ensure_ascii=False))

        self.cli.agent_result_set("tester", "")
        self.assertEqual(self.cli.agent_result("tester"), "")

    def test_agent_meta_save_roundtrip(self):
        self.write_global("tester")
        self.cli.agent_result_set("tester", "gespeichert")

        meta = self.cli.agent_meta_load()
        self.cli.agent_meta_save(meta)

        self.assertEqual(self.cli.agent_result("tester"), "gespeichert")

    def test_agents_all_exposes_result_role_vibe_and_model_state(self):
        self.write_vibe()
        self.write_global("helper", task_agent(["vibe-agent"]))
        self.write_global("ohne-modell", VIBE_AGENT_NO_MODEL)
        self.cli.agent_result_set("helper", "hilft")
        self.set_roles({"vibe-agent": "vibe", "helper": "coder"})

        rows = {
            row["name"]: row
            for row in self.cli.agents_all()
            if row["scope"] == "global"
        }

        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["helper"]["is_vibe"])
        self.assertFalse(rows["vibe-agent"]["model_missing"])
        self.assertTrue(rows["ohne-modell"]["model_missing"])
        self.assertEqual(rows["helper"]["result"], "hilft")
        self.assertEqual(rows["helper"]["allowed_agents"], ["vibe-agent"])
        self.assertEqual(rows["helper"]["role"], "coder")


class HierarchyTest(Ap03Fixture):
    """AK Hierarchie und Berechtigungen."""

    def test_agent_task_policy_reads_all_none_and_custom(self):
        allowed = self.cli.agent_task_policy(task_agent([], task="allow"))
        self.assertEqual(allowed["mode"], "all")

        denied = self.cli.agent_task_policy(task_agent([], task="deny"))
        self.assertEqual(denied["mode"], "none")

        custom = self.cli.agent_task_policy(task_agent(["b", "a"]))
        self.assertEqual(custom["mode"], "custom")
        self.assertEqual(custom["allowed"], ["a", "b"])

    def test_agent_render_task_writes_a_permission_object_and_preserves_fields(self):
        self.write_global("a", task_agent([]))
        self.write_global("b", task_agent([]))

        rendered = self.cli.agent_render_task(
            "global", AGENT_BASE, ["b", "a"]
        )

        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["a", "b"])
        # Alle anderen Frontmatter-Zeilen und der Prompt bleiben erhalten.
        self.assertIn("description: Erste Beschreibung", rendered)
        self.assertIn("mode: subagent", rendered)
        self.assertIn("model: opencode/test-modell", rendered)
        self.assertIn("edit: deny", rendered)
        self.assertIn("Erster Prompt.", rendered)
        # Das Ergebnis ist weiterhin ein gültiger Agent.
        self.cli.agent_validate(rendered)

    def test_agent_render_task_all_writes_task_allow(self):
        rendered = self.cli.agent_render_task("global", AGENT_BASE, [], allow_all=True)

        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "all")
        self.assertIn("description: Erste Beschreibung", rendered)
        self.cli.agent_validate(rendered)

    def test_agent_validate_hierarchy_rejects_unknown_and_cycles(self):
        # F32 erlaubt den Selbstaufruf eines gewöhnlichen Subagenten. Die
        # vollständige Abdeckung (erlaubt und abgelehnt) liegt in
        # test_f32_subagent_self_spawn.py; hier bleiben nur die unveränderten
        # Regeln für unbekannte Agenten und echte Zyklen.
        self.write_global("a", task_agent(["b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["b"])

        # Ohne Rückkante ist dieselbe Beziehung zulässig.
        self.write_global("b", task_agent([]))
        self.cli.agent_validate_hierarchy("a", ["b"])

    def test_agent_validate_hierarchy_accepts_only_global_subagents(self):
        self.write_global("a", task_agent([]))
        self.write_global("primary", task_agent([], mode="primary"))
        self.write_global("alle", task_agent([], mode="all"))
        self.write_project_agent(self.project, "lokal", task_agent([]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["primary"])
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["lokal"])

        # Globale Agenten mit mode subagent oder all dürfen aufgerufen werden.
        self.cli.agent_validate_hierarchy("a", ["alle"])


class ProjectConfigurationTest(Ap03Fixture):
    """AK Projektkonfiguration: globale Agenten, Version 2, Vibe als Standard."""

    def test_missing_config_activates_only_the_vibe_agent(self):
        self.write_vibe()
        self.write_global("tester")

        rows = self.rows()

        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["tester"]["configured"])
        self.assertFalse(rows["tester"]["selected"])
        self.assertFalse(self.config_path().exists())

    def test_version_1_is_migrated_to_version_3_without_losing_overrides(self):
        self.write_vibe()
        self.write_global("tester")
        self.write_global("other")
        self.config_path().write_text(
            json.dumps(
                {
                    "version": 1,
                    "deaktiviert": ["other"],
                    "modelle": {"tester": "opencode/override"},
                }
            ),
            encoding="utf-8",
        )

        config, _snapshot = self.cli.project_agents_load("proj")
        self.assertEqual(config["version"], 3)
        self.assertEqual(set(config["aktiv"]), {"vibe-agent", "tester"})
        self.assertNotIn("other", config["aktiv"])

        rows = self.rows()
        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["tester"]["configured"])
        self.assertFalse(rows["other"]["configured"])
        self.assertEqual(rows["tester"]["override"], "opencode/override")
        self.assertEqual(rows["tester"]["effective_model"], "opencode/override")

    def test_project_agent_inventory_only_offers_global_agents(self):
        self.write_vibe()
        self.write_global("tester")
        self.write_project_agent(self.project, "lokal")

        inventory = self.cli.project_agent_inventory("proj")

        self.assertIn("vibe-agent", inventory)
        self.assertIn("tester", inventory)
        self.assertNotIn("lokal", inventory)

    def test_project_agent_rows_exposes_the_required_fields(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "Ergebnis des Testers")

        row = self.rows()["tester"]

        for key in (
            "configured",
            "selected",
            "is_vibe",
            "model",
            "effective_model",
            "override",
            "result",
            "role",
            "allowed_agents",
        ):
            self.assertIn(key, row)
        self.assertFalse(row["configured"])
        self.assertEqual(row["selected"], row["configured"])
        self.assertFalse(row["is_vibe"])
        self.assertEqual(row["result"], "Ergebnis des Testers")
        self.assertEqual(row["role"], "")
        self.assertIsInstance(row["allowed_agents"], list)

    def test_project_agent_set_refuses_deselecting_the_vibe_agent(self):
        self.write_vibe()
        self.write_global("tester")

        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "vibe-agent", selected=False)

        self.assertFalse(self.config_path().exists())
        self.assertTrue(self.rows()["vibe-agent"]["configured"])

    def test_project_agent_set_rejects_project_local_and_unknown_agents(self):
        self.write_vibe()
        self.write_project_agent(self.project, "lokal")

        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "lokal", selected=False)
        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "unbekannt", selected=False)

        self.assertFalse(self.config_path().exists())

    def test_model_override_is_independent_of_selection(self):
        self.write_vibe()
        self.write_global("tester")

        self.cli.project_agent_set("proj", "tester", model="opencode/override")

        row = self.rows()["tester"]
        self.assertFalse(row["configured"])
        self.assertEqual(row["override"], "opencode/override")
        stored = json.loads(self.config_path().read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 3)
        self.assertNotIn("tester", stored["aktiv"])
        self.assertEqual(stored["modelle"]["tester"], "opencode/override")

    def test_run_agent_selection_rejects_unconfigured_and_returns_override(self):
        self.write_vibe()
        self.write_global("tester")

        with self.assertRaises(ValueError):
            self.cli.run_agent_selection("proj", "tester")

        self.assertEqual(self.cli.run_agent_selection("proj", "vibe-agent"), "")

        self.cli.project_agent_set(
            "proj", "tester", selected=True, model="opencode/override"
        )
        self.assertEqual(
            self.cli.run_agent_selection("proj", "tester"), "opencode/override"
        )

        self.cli.project_agent_set("proj", "tester", selected=False)
        with self.assertRaises(ValueError):
            self.cli.run_agent_selection("proj", "tester")


class AgentTemplateTest(Ap03Fixture):
    """AK Agent speichern: Vorlage und Prompt-Gerüst."""

    def test_agent_template_still_produces_valid_frontmatter(self):
        text = self.cli.agent_template(
            "Neuer Agent", model="opencode/test-modell", prompt="Aufgabe"
        )

        self.assertTrue(text.startswith("---\n"))
        fields = self.cli.agent_validate(text)
        self.assertEqual(fields["description"], "Neuer Agent")

    def test_prompt_scaffold_contains_the_required_sections(self):
        text = self.cli.agent_prompt_scaffold(
            "Die Aufgabe", "Das Ergebnis", "Die Grenze"
        )

        for expected in (
            "## Aufgabe",
            "## Ergebnis",
            "## Grenzen",
            "Die Aufgabe",
            "Das Ergebnis",
            "Die Grenze",
        ):
            self.assertIn(expected, text)
        # Der Satz zur Abkapselung darf "Abkapselung" oder "abgekapselt" heißen.
        self.assertIn("kapsel", text.lower())

        without_limits = self.cli.agent_prompt_scaffold("A", "E")
        self.assertIn("## Grenzen", without_limits)


class UiInfoTest(Ap03Fixture):
    """AK UI-Daten aus vibe_services."""

    def setUp(self):
        super().setUp()
        self.services = load_services()

    def agent_row(self, data, name):
        for key in ("agents", "global_agents"):
            rows = data.get(key) or []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("name") == name:
                        return row
        self.fail(f"Agent {name!r} fehlt in der UI-Antwort: {data!r}")

    def test_agents_info_exposes_vibe_status_roles_and_agent_fields(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "UI-Ergebnis")
        self.set_roles({"vibe-agent": "vibe", "tester": "coder"})

        data = self.services.agents_info(self.cli)

        self.assertIn("vibe_agent", data)
        self.assertEqual(field(data["vibe_agent"], "name"), "vibe-agent")
        self.assertTrue(field(data["vibe_agent"], "configured"))
        self.assertIn("roles", data)
        self.assertEqual(data["roles"].get("tester"), "coder")
        self.assertIn("global_agents", data)

        row = self.agent_row(data, "tester")
        self.assertEqual(row["result"], "UI-Ergebnis")
        self.assertEqual(row["role"], "coder")
        self.assertIn("allowed_agents", row)
        self.assertIn("model_missing", row)

    def test_project_agents_info_exposes_configuration_and_unconfigured_count(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "Projekt-Ergebnis")

        data = self.services.project_agents_info(self.cli, "proj")

        rows = {row["name"]: row for row in data["agents"]}
        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["tester"]["configured"])
        for key in ("result", "role", "allowed_agents"):
            self.assertIn(key, rows["tester"])
        self.assertEqual(rows["tester"]["result"], "Projekt-Ergebnis")
        self.assertEqual(data["available_unconfigured"], 1)


class VibeAgentApiTest(unittest.TestCase):
    """AK Agent speichern: Web-API übernimmt die neuen Felder atomar."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (cls.agents / "helper.md").write_text(
            task_agent([]), encoding="utf-8"
        )
        (cls.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        state = cls.root / "_toolchain"
        state.mkdir()
        (state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
        )
        # Der Server ruft beim Speichern ``opencode --version`` und
        # ``opencode models`` auf. Beide werden hier durch ein schnelles
        # Ersatzprogramm beantwortet; es findet kein echter Modellaufruf statt.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\nopencode/helper-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env_agent_files(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_ap03)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        cls.cli = load_cli_agent_files(cls.root, cls.home)

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
        self.path = self.agents / "tester.md"
        self.path.write_text(AGENT_BASE, encoding="utf-8")

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self):
        status, body = self.request("/api/agent?scope=global&name=tester")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def test_api_save_accepts_result_task_allowed_and_role(self):
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "values": {"description": "Neu beschrieben"},
                "result": "Fertig",
                "task_allowed": ["helper"],
                "role": "coder",
                "expected": self.digest(),
            },
        )

        self.assertEqual(status, 200, body)
        saved = self.path.read_text(encoding="utf-8")
        self.assertIn("description: Neu beschrieben", saved)
        self.assertEqual(self.cli.agent_result("tester"), "Fertig")
        self.assertEqual(
            self.cli.profiles_load()["rollen"].get("tester"), "coder"
        )
        policy = self.cli.agent_task_policy(saved)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["helper"])

    def test_api_save_rejects_invalid_new_values_without_touching_the_file(self):
        broken = (
            {"result": 123},
            {"task_allowed": "helper"},
            {"task_allowed": ["unbekannt"]},
            {"role": 123},
        )
        for payload in broken:
            with self.subTest(payload=payload):
                status, body = self.request(
                    "/api/agent",
                    {
                        "action": "save",
                        "scope": "global",
                        "name": "tester",
                        "text": AGENT_BASE,
                        **payload,
                    },
                )
                self.assertEqual(status, 400, body)
                self.assertEqual(
                    self.path.read_text(encoding="utf-8"), AGENT_BASE
                )


# ===========================================================================
# Weitere Agentenrollen: Unit- und Backend-Tests
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CLI_ap17 = BIN / "vibe"
PACKAGES = BIN / "vibe_packages.py"

NEW_ROLES = ("tester", "analyst", "sonstiges", "content-creator")
EXISTING_ROLES = ("coder", "reviewer", "vibe")

AGENT_BASE_ap17 = """---
description: Testagent
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""


# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV_ap17 = (
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
    "AGENT",
)


def isolated_env_roles(root, home):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_ap17:
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


def load_cli_roles(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_ap17}
    for key in ISOLATED_ENV_ap17:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_roles(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap17_under_test", str(CLI_ap17)
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


def load_module(path, name):
    """Lädt ein eigenständiges Modul (hier den Paketläufer)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def agent_name(role):
    """Gültiger globaler Agentenname für eine Rolle."""
    return "agent-" + role


def project_env(tester=None, reviewer="code-reviewer"):
    """Projektdatei mit optionalem explizitem TESTER und Reviewer."""
    lines = ["TYPE=generic", "AGENT=test-agent"]
    if tester is not None:
        lines.append("TESTER=" + tester)
    if reviewer is not None:
        lines.append("REVIEWER=" + reviewer)
    lines.append('VERIFY_PACKAGE="true"')
    return "\n".join(lines) + "\n"


class RoleCatalogTest(unittest.TestCase):
    """Rollenkatalog und Zuweisung über die Agentenverwaltung (AK 1 und 2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli = load_cli_roles(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def write_global(self, name, text=AGENT_BASE_ap17):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def profiles_path(self):
        return Path(self.root) / "_toolchain" / "profiles.json"

    def roles_on_disk(self):
        return json.loads(self.profiles_path().read_text(encoding="utf-8"))[
            "rollen"
        ]

    def test_role_catalog_contains_existing_and_new_roles(self):
        """Name: Rollenkatalog enthält alle vereinbarten Rollen.

        Vorbedingung: bin/vibe ist mit isoliertem Zustandsordner geladen.
        Aktion: ``ROLE_NAMES`` wird gelesen.
        Erwartetes Ergebnis: coder, reviewer und vibe bleiben enthalten;
        zusätzlich sind tester, analyst, sonstiges und content-creator
        vorhanden. Weitere Rollen gibt es nicht.
        """
        roles = tuple(self.cli.ROLE_NAMES)

        self.assertEqual(
            set(roles), set(EXISTING_ROLES) | set(NEW_ROLES), roles
        )

    def test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json(self):
        """Name: Alle vier neuen Rollen werden gespeichert.

        Vorbedingung: Für jede neue Rolle existiert ein globaler Agent.
        Aktion: ``agent_role_set`` wird für tester, analyst, sonstiges und
        content-creator aufgerufen.
        Erwartetes Ergebnis: Jede Rolle ist im Rückgabewert und in
        ``profiles.json`` unter ``rollen`` gespeichert.
        """
        for role in NEW_ROLES:
            self.write_global(agent_name(role))

        for role in NEW_ROLES:
            returned = self.cli.agent_role_set(agent_name(role), role)
            self.assertEqual(returned[agent_name(role)], role)

        stored = self.roles_on_disk()
        for role in NEW_ROLES:
            self.assertEqual(stored.get(agent_name(role)), role)

    def test_new_roles_are_visible_in_the_agent_list(self):
        """Name: Agentenliste zeigt die neuen Rollen.

        Vorbedingung: Vier globale Agenten tragen je eine neue Rolle.
        Aktion: ``agents_all`` wird ausgewertet.
        Erwartetes Ergebnis: Jede globale Agentenzeile liefert ihre
        zugewiesene Rolle; die Rollen sind damit in der Agentenliste sichtbar.
        """
        for role in NEW_ROLES:
            self.write_global(agent_name(role))
            self.cli.agent_role_set(agent_name(role), role)

        rows = {
            row["name"]: row
            for row in self.cli.agents_all()
            if row["scope"] == "global"
        }

        for role in NEW_ROLES:
            self.assertEqual(rows[agent_name(role)]["role"], role)

    def test_unknown_role_is_rejected_without_changing_profiles_json(self):
        """Name: Unbekannte Rolle wird abgelehnt, Datei bleibt unverändert.

        Vorbedingung: Ein globaler Agent hat die Rolle coder; profiles.json
        liegt vor.
        Aktion: ``agent_role_set`` wird mit unbekannten Rollen aufgerufen.
        Erwartetes Ergebnis: ``ValueError``; profiles.json und die
        Agentendatei bleiben bytegleich.
        """
        name = "tester"
        path = self.write_global(name)
        self.set_roles({name: "coder"})
        before_profiles = self.profiles_path().read_bytes()
        before_agent = path.read_bytes()

        for unknown in ("supervisor", "Tester", "content_creator", "vibe-agent"):
            with self.subTest(role=unknown):
                with self.assertRaises(ValueError):
                    self.cli.agent_role_set(name, unknown)
                self.assertEqual(
                    self.profiles_path().read_bytes(), before_profiles
                )
                self.assertEqual(path.read_bytes(), before_agent)

    def test_new_roles_do_not_change_the_vibe_protection_rules(self):
        """Name: Vibe-Schutzregeln gelten unverändert.

        Vorbedingung: Ein Agent trägt vibe, ein zweiter ist vorhanden.
        Aktion: Dem zweiten wird eine neue Rolle zugewiesen; anschließend wird
        versucht, dem letzten Vibe-Agenten die Rolle zu entziehen.
        Erwartetes Ergebnis: Die neue Rolle stört den Vibe-Agenten nicht.
        Entfernen oder Umwidmen des letzten Vibe-Agenten bleibt verboten;
        genau ein Agent trägt weiterhin vibe.
        """
        self.write_global("vibe-agent", VIBE_AGENT)
        self.write_global("second")
        self.cli.agent_role_set("vibe-agent", "vibe")

        self.cli.agent_role_set("second", "analyst")

        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(roles.get("second"), "analyst")
        self.assertEqual(
            [name for name, role in roles.items() if role == "vibe"],
            ["vibe-agent"],
        )

        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "tester")
        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "")

        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(roles.get("vibe-agent"), "vibe")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        # Umsetzen bleibt durch gleichzeitige Zuweisung möglich; danach trägt
        # weiterhin genau ein Agent die Rolle vibe.
        self.cli.agent_role_set("second", "vibe")
        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(
            [name for name, role in roles.items() if role == "vibe"], ["second"]
        )
        self.assertEqual(self.cli.vibe_agent_name(), "second")


class PreflightFixture(unittest.TestCase):
    """Temporäres Git-Projekt mit Agentenordner und Zustandsordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.git("init", "-q", "-b", "main", str(self.project), cwd=self.root)
        self.agents = self.root / "agents"
        self.agents.mkdir()
        for name in ("test-agent", "code-reviewer", "fallback-tester"):
            (self.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n",
                encoding="utf-8",
            )
        self.write_project(project_env())
        self.state = self.root / "state"
        self.state.mkdir()
        self.write_profiles(
            {"fallback-tester": "tester", "code-reviewer": "reviewer"}
        )
        self.commit_all("Ausgangsstand")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.project),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        return result

    def write_project(self, env_text):
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            env_text, encoding="utf-8"
        )

    def commit_all(self, message):
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def write_profiles(self, rollen):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": rollen}), encoding="utf-8"
        )


class TesterRolePreflightTest(PreflightFixture):
    """Preflight: TESTER-Fallback über die Rolle ``tester`` (AK 4)."""

    def setUp(self):
        super().setUp()
        self.module = load_module(PACKAGES, "vibe_packages_ap17_preflight")

    def errors(self, tester="", reviewer="code-reviewer", state_dir="__default__"):
        if state_dir == "__default__":
            state_dir = self.state
        return self.module.preflight_errors(
            str(self.project),
            agents_dir=str(self.agents),
            tester=tester,
            reviewer=reviewer,
            state_dir=str(state_dir) if state_dir else state_dir,
        )

    def test_missing_tester_is_resolved_from_tester_role(self):
        """Name: Fehlender TESTER wird aus der Rolle tester ergänzt.

        Vorbedingung: project.env enthält keinen TESTER; profiles.json enthält
        die Rolle tester für einen verfügbaren Agenten.
        Aktion: ``preflight_errors`` wird mit leerem tester und Zustandsordner
        aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der Rollenagent übernimmt TESTER.
        """
        self.assertNotIn(
            "TESTER", (self.project / ".vibe" / "project.env").read_text(
                encoding="utf-8"
            )
        )

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_project_local_agent_file_satisfies_the_tester_role(self):
        """Name: Projektlokaler Agent erfüllt die Tester-Rolle.

        Vorbedingung: Die globale Datei des Rollenagenten fehlt; dieselbe
        Agentendatei liegt im Projektordner.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; auch der Projektordner ist ein
        gültiger Agentenort.
        """
        (self.agents / "fallback-tester.md").unlink()
        local = self.project / ".opencode" / "agents"
        local.mkdir(parents=True)
        (local / "fallback-tester.md").write_text(
            "---\ndescription: lokaler Tester\nmode: subagent\n---\n",
            encoding="utf-8",
        )
        self.commit_all("lokaler Tester")

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_stale_tester_role_entry_does_not_block_available_agent(self):
        """Name: Veralteter Rolleneintrag blockiert verfügbaren Tester nicht.

        Vorbedingung: profiles.json nennt zuerst einen nicht vorhandenen
        Agenten und danach einen verfügbaren Agenten mit Rolle tester.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der verfügbare Rollenagent wird
        gewählt (analog zum REVIEWER-Fallback).
        """
        self.write_profiles(
            {
                "veralteter-tester": "tester",
                "fallback-tester": "tester",
                "code-reviewer": "reviewer",
            }
        )

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_unavailable_tester_role_is_reported_with_its_name(self):
        """Name: Nicht verfügbarer Rollen-Tester wird mit Namen gemeldet.

        Vorbedingung: profiles.json enthält die Rolle tester für einen Agenten,
        dessen Datei weder global noch im Projekt liegt.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Ein TESTER-Befund nennt den Namen
        ``veralteter-tester`` und meldet die fehlende Agentendatei.
        """
        self.write_profiles(
            {"veralteter-tester": "tester", "code-reviewer": "reviewer"}
        )

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("veralteter-tester" in error for error in errors), errors
        )
        self.assertTrue(
            any("nicht verfügbar" in error for error in errors), errors
        )

    def test_explicit_tester_argument_wins_over_the_tester_role(self):
        """Name: Ausdrücklicher TESTER hat Vorrang vor der Rolle.

        Vorbedingung: Die Rolle tester zeigt auf einen nicht vorhandenen
        Agenten; der als Argument übergebene Agent ist verfügbar.
        Aktion: ``preflight_errors`` wird mit ``tester="test-agent"``
        aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der ausdrückliche TESTER wird
        verwendet und nicht durch die Rolle ersetzt.
        """
        self.write_profiles(
            {"veralteter-tester": "tester", "code-reviewer": "reviewer"}
        )

        errors = self.errors(tester="test-agent")

        self.assertEqual(errors, [])

    def test_unavailable_explicit_tester_blocks_despite_a_valid_role(self):
        """Name: Nicht verfügbarer ausdrücklicher TESTER blockiert.

        Vorbedingung: Die Rolle tester zeigt auf einen verfügbaren Agenten.
        Aktion: ``preflight_errors`` wird mit einem nicht vorhandenen
        ausdrücklichen TESTER aufgerufen.
        Erwartetes Ergebnis: Ein TESTER-Befund nennt den ausdrücklichen Namen;
        die Rolle ersetzt ihn nicht.
        """
        errors = self.errors(tester="nicht-vorhanden")

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    def test_project_env_tester_wins_over_the_tester_role(self):
        """Name: TESTER aus project.env hat Vorrang vor der Rolle.

        Vorbedingung: Die Rolle tester zeigt auf einen verfügbaren Agenten;
        project.env setzt ausdrücklich einen nicht vorhandenen TESTER.
        Aktion: ``preflight_errors`` wird ohne Argument aufgerufen.
        Erwartetes Ergebnis: Der Befund nennt den Wert aus project.env; die
        Rolle wird nicht als Ersatz verwendet.
        """
        self.write_project(project_env(tester="nicht-vorhanden"))
        self.commit_all("expliziter TESTER")

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    def test_without_state_directory_missing_tester_still_blocks(self):
        """Name: Ohne Zustandsordner bleibt der Befund TESTER fehlt.

        Vorbedingung: project.env enthält keinen TESTER.
        Aktion: ``preflight_errors`` wird ohne Zustandsordner aufgerufen.
        Erwartetes Ergebnis: Der bisherige Befund ``TESTER fehlt`` bleibt
        bestehen; es wird keine Rolle erfunden.
        """
        errors = self.errors(state_dir=None)

        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

    def test_missing_or_broken_profiles_file_blocks_with_tester_message(self):
        """Name: Fehlende oder kaputte profiles.json blockiert ohne Absturz.

        Vorbedingung: project.env enthält keinen TESTER.
        Aktion: profiles.json wird entfernt bzw. mit ungültigem JSON gefüllt
        und ``preflight_errors`` erneut aufgerufen.
        Erwartetes Ergebnis: Jeweils der Befund ``TESTER fehlt``; kein
        Absturz.
        """
        (self.state / "profiles.json").unlink()
        errors = self.errors()
        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

        (self.state / "profiles.json").write_text(
            "{kein gültiges JSON", encoding="utf-8"
        )
        errors = self.errors()
        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

    def test_reviewer_fallback_still_resolves_from_profiles_json(self):
        """Name: REVIEWER-Fallback bleibt unverändert.

        Vorbedingung: project.env enthält einen verfügbaren TESTER, aber
        keinen REVIEWER; profiles.json enthält die Rolle reviewer.
        Aktion: ``preflight_errors`` wird aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der Reviewer wird weiterhin aus
        der Rolle reviewer ergänzt.
        """
        self.write_project(project_env(tester="test-agent", reviewer=None))
        self.commit_all("ohne REVIEWER")

        errors = self.errors(reviewer="")

        self.assertEqual(errors, [])


class TesterRoleCliTest(PreflightFixture):
    """CLI ``preflight --state`` löst den TESTER aus der Rolle auf (AK 4)."""

    def run_preflight(self, *state_args):
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGES),
                "preflight",
                "--project",
                str(self.project),
                "--agents-dir",
                str(self.agents),
                *state_args,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_preflight_resolves_tester_from_state_directory(self):
        """Name: CLI-Preflight löst TESTER über --state auf.

        Vorbedingung: project.env ohne TESTER; profiles.json im Zustandsordner
        enthält die Rolle tester für einen verfügbaren Agenten.
        Aktion: ``preflight --state <ordner>`` wird ausgeführt.
        Erwartetes Ergebnis: Rückgabewert 0 und keine BLOCKIERT-Meldung.
        """
        result = self.run_preflight("--state", str(self.state))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BLOCKIERT", result.stdout, result.stdout)

    def test_cli_preflight_without_state_still_blocks_missing_tester(self):
        """Name: CLI-Preflight ohne --state meldet TESTER fehlt.

        Vorbedingung: project.env ohne TESTER; ein Zustandsordner wird nicht
        übergeben.
        Aktion: ``preflight`` wird ohne ``--state`` ausgeführt.
        Erwartetes Ergebnis: Rückgabewert 2 und eine TESTER-Meldung.
        """
        result = self.run_preflight()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("TESTER", result.stdout)


# ===========================================================================
# Unabhängige Abnahme
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

CLI_ap2 = BIN / "vibe"
WEB_ap2 = BIN / "vibe-web.py"
RUNNER_ap2 = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

ISOLATED_ENV_ap2 = (
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
    "VIBE_UI_BIND",
    "VIBE_OPENCODE_PORT",
    "VIBE_CONTAINER",
    "AGENT",
    "SANDBOX",
    "SANDBOX_TOOLS",
    "VIBE_SANDBOX_ROOT",
)


def isolated_env_ap2(root, home, port=None):
    env = os.environ.copy()
    for key in ISOLATED_ENV_ap2:
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli_ap2(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_ap2}
    for key in ISOLATED_ENV_ap2:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_ap2(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap2_under_test", str(CLI_ap2)
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


# --------------------------------------------------------------------------
# Parser-Helfer: unabhängig von der genauen Zeilenformatierung der Vorlagen.
# --------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)


def frontmatter_lines(text):
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise AssertionError("Kein Frontmatter in:\n" + text)
    return match.group(1).splitlines()


def unquote(value):
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _key_value(line):
    match = re.match(r"^[ \t]*(?:-[ \t]+)?([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
    if not match:
        return None
    return match.group(1), unquote(match.group(2))


def opencode_parse_permissions(text):
    """Liest einen v2-``permissions``-Block als Liste von Regel-Dicts.

    Akzeptiert sowohl einen vollständigen Agententext (``---``-Frontmatter)
    als auch einen losen Block. Die Reihenfolge der Regeln bleibt erhalten.
    Gibt ``None`` zurück, wenn kein v2-Block vorhanden ist.
    """
    if FRONTMATTER_RE.match(text):
        lines = frontmatter_lines(text)
    else:
        lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^permissions:[ \t]*$", line):
            start = index + 1
            break
    if start is None:
        return None
    rules, current = [], None
    for line in lines[start:]:
        if line and not line.startswith((" ", "\t")):
            break
        if not line.strip():
            continue
        if re.match(r"^[ \t]*-[ \t]+", line):
            if current is not None:
                rules.append(current)
            current = {}
        item = _key_value(line)
        if item is None:
            continue
        if current is None:
            current = {}
        current[item[0]] = item[1]
    if current is not None:
        rules.append(current)
    return rules


def block_rules(block, action=None):
    """Regeln eines ``permission_block``-Ergebnisses (mit oder ohne Kopfzeile)."""
    if isinstance(block, (list, tuple)):
        block = "\n".join(block)
    if not re.search(r"^permissions:[ \t]*$", block, re.M):
        block = "permissions:\n" + block
    rules = opencode_parse_permissions(block)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block:\n" + block)
    if action is None:
        return rules
    return [rule for rule in rules if rule.get("action") == action]


def pair_list(rules):
    return [(rule.get("resource"), rule.get("effect")) for rule in rules]


def rule_map(rules):
    """action -> (resource, effect) für Aktionen mit genau einer Regel."""
    out = {}
    for rule in rules:
        action = rule.get("action")
        if action in out:
            raise AssertionError("Aktion mehrfach vorhanden: " + str(action))
        out[action] = (rule.get("resource"), rule.get("effect"))
    return out


def has_top_level_key(text, key):
    return any(
        re.match(r"^" + re.escape(key) + r":[ \t]*(.*)$", line)
        for line in frontmatter_lines(text)
    )


def assert_no_v1_keys(testcase, text):
    """In neu erzeugten Blöcken darf keine v1-Syntax stehen."""
    testcase.assertFalse(has_top_level_key(text, "permission"),
                         "v1-Schlüssel 'permission:' wurde erzeugt")
    testcase.assertIsNotNone(opencode_parse_permissions(text),
                             "v2-Schlüssel 'permissions:' fehlt")
    for line in frontmatter_lines(text):
        testcase.assertFalse(
            re.match(r"^[ \t]+(bash|task|list):", line),
            "v1-Schlüssel in neuem Block: " + line)


def agent_text(extra_frontmatter, prompt="Prompt."):
    return "---\n" + extra_frontmatter.strip("\n") + "\n---\n\n" + prompt + "\n"


V1_LESEN_PERMISSION = """permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: deny
  bash: deny
  task: deny
  webfetch: deny
  websearch: deny"""

V1_LESEN_AGENT = (
    "---\ndescription: Alt-Lesen\nmode: subagent\n" + V1_LESEN_PERMISSION
    + "\n---\n\nAlt-Prompt.\n"
)

V1_FULL_PERMISSION = """permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  webfetch: deny
  websearch: deny"""

V1_CUSTOM_AGENT = """---
description: Alt mit individuellem Block
mode: subagent
color: blau
permission:
  read: allow
  edit: deny
  task: deny
---

Individueller Prompt.
"""


def v2_agent(rules, description="Agent", mode="subagent", model="opencode/test-modell"):
    lines = ["---", "description: " + description, "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines.append("permissions:")
    for action, resource, effect in rules:
        lines.append("  - action: " + action)
        lines.append("    resource: " + json.dumps(resource))
        lines.append("    effect: " + effect)
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


LESEN_RULES = [
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "deny"),
    ("shell", "*", "deny"),
    ("subagent", "*", "deny"),
    ("webfetch", "*", "deny"),
    ("websearch", "*", "deny"),
]

VOLL_RULES = [
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "allow"),
    ("subagent", "*", "deny"),
    ("webfetch", "*", "deny"),
    ("websearch", "*", "deny"),
]


class CliFixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.other = self.make_project("other")
        self.cli = load_cli_ap2(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        return project

    def write_global(self, name, text):
        self.agents.mkdir(parents=True, exist_ok=True)
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name, text):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def config_path(self, project):
        return project / ".vibe" / "agents.json"

    def write_config(self, project, data):
        path = self.config_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# A1: permission_block erzeugt v2-Regeln
# --------------------------------------------------------------------------

class A1PermissionBlockTest(CliFixture):
    def test_voll_block_uses_v2_rules(self):
        block = self.cli.permission_block("voll")
        if isinstance(block, (list, tuple)):
            block = "\n".join(block)
        rules = block_rules(block)

        self.assertEqual(
            rule_map(rules),
            {
                "read": ("*", "allow"),
                "glob": ("*", "allow"),
                "grep": ("*", "allow"),
                "edit": ("*", "allow"),
                "shell": ("*", "allow"),
                "subagent": ("*", "deny"),
                "webfetch": ("*", "deny"),
                "websearch": ("*", "deny"),
            },
        )
        self.assertNotRegex(block, r"(?m)^[ \t]*(bash|task|list):")

    def test_lesen_block_denies_write_shell_and_subagents(self):
        rules = block_rules(self.cli.permission_block("lesen"))

        self.assertEqual(
            rule_map(rules),
            {
                "read": ("*", "allow"),
                "glob": ("*", "allow"),
                "grep": ("*", "allow"),
                "edit": ("*", "deny"),
                "shell": ("*", "deny"),
                "subagent": ("*", "deny"),
                "webfetch": ("*", "deny"),
                "websearch": ("*", "deny"),
            },
        )

    def test_lesen_git_block_orders_shell_rules_correctly(self):
        rules = block_rules(self.cli.permission_block("lesen_git"))

        self.assertEqual(
            pair_list([rule for rule in rules if rule.get("action") == "shell"]),
            [
                ("*", "deny"),
                ("git status --short", "allow"),
                ("git diff *", "allow"),
                ("git show *", "allow"),
                ("git log *", "allow"),
            ],
        )
        mapped = rule_map([rule for rule in rules if rule.get("action") != "shell"])
        self.assertEqual(mapped["edit"], ("*", "deny"))
        self.assertEqual(mapped["subagent"], ("*", "deny"))
        self.assertEqual(mapped["webfetch"], ("*", "deny"))
        self.assertEqual(mapped["websearch"], ("*", "deny"))

    def test_project_full_block_denies_first_then_allows_each_write_dir(self):
        dirs = ["/tmp/opencode", "/tmp/opencode/projekt"]
        block = self.cli.permission_block("voll", write_dirs=dirs)
        edit = block_rules(block, "edit")

        self.assertEqual(
            pair_list(edit),
            [
                ("*", "deny"),
                ("/tmp/opencode", "allow"),
                ("/tmp/opencode/**", "allow"),
                ("/tmp/opencode/projekt", "allow"),
                ("/tmp/opencode/projekt/**", "allow"),
            ],
        )

    def test_empty_write_dir_list_denies_edits(self):
        block = self.cli.permission_block("voll", write_dirs=[])
        self.assertEqual(pair_list(block_rules(block, "edit")), [("*", "deny")])

    def test_edit_permission_lines_use_v2_list_items(self):
        lines = self.cli.edit_permission_lines(["/tmp/opencode"])
        rules = block_rules("\n".join(lines), "edit")
        self.assertEqual(
            pair_list(rules),
            [
                ("*", "deny"),
                ("/tmp/opencode", "allow"),
                ("/tmp/opencode/**", "allow"),
            ],
        )


# --------------------------------------------------------------------------
# A2: agent_template erzeugt v2-Frontmatter
# --------------------------------------------------------------------------

class A2TemplateTest(CliFixture):
    def test_template_frontmatter_is_v2_and_validates(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Testagent", perm=preset)
                assert_no_v1_keys(self, text)
                self.cli.agent_validate(text)

    def test_project_template_with_write_dirs_uses_v2_edit_rules(self):
        dirs = self.cli.write_dirs("proj")
        text = self.cli.agent_template(
            "Projektagent", perm="voll", write_dirs=dirs
        )

        assert_no_v1_keys(self, text)
        edit = block_rules(text, "edit")
        self.assertEqual(edit[0].get("resource"), "*")
        self.assertEqual(edit[0].get("effect"), "deny")
        resources = [rule["resource"] for rule in edit]
        for directory in dirs:
            self.assertIn(directory, resources)
            self.assertIn(directory + "/**", resources)
        self.cli.agent_validate(text)


# --------------------------------------------------------------------------
# A3: strukturierter Editor erkennt v2-Vorlagen
# --------------------------------------------------------------------------

class A3FieldsTest(CliFixture):
    def test_fields_recognise_global_v2_presets(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Agent", perm=preset)
                fields = self.cli.agent_fields("global", text)
                self.assertEqual(fields["permission"], preset)
                self.assertFalse(fields["permission_custom"])
                self.assertNotIn("permissions", fields["unknown"])

    def test_fields_recognise_project_v2_preset_with_write_dirs(self):
        dirs = self.cli.write_dirs("proj")
        text = self.cli.agent_template("Agent", perm="voll", write_dirs=dirs)

        fields = self.cli.agent_fields("proj", text)

        self.assertEqual(fields["permission"], "voll")
        self.assertFalse(fields["permission_custom"])

    def test_v1_block_is_custom_but_file_stays_readable_and_editable(self):
        fields = self.cli.agent_fields("global", V1_CUSTOM_AGENT)

        self.assertEqual(fields["permission"], "")
        self.assertTrue(fields["permission_custom"])
        self.assertNotIn("permission", fields["unknown"])
        changed = self.cli.agent_render_fields(
            "global", V1_CUSTOM_AGENT, {"description": "Neu"}
        )
        self.assertIn("description: Neu", changed)
        self.assertTrue(has_top_level_key(changed, "permission"),
                        "Der individuelle v1-Block wurde ohne Auftrag verändert")
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A4: agent_render_fields ersetzt v1/v2 durch v2
# --------------------------------------------------------------------------

class A4RenderFieldsTest(CliFixture):
    def test_render_replaces_a_v1_block_with_v2_and_keeps_unknown_fields(self):
        text = (
            "---\n"
            "description: Alt\n"
            "mode: subagent\n"
            "color: blau\n"
            "tools:\n"
            "  write: true\n"
            "permission:\n"
            "  read: allow\n"
            "  edit: deny\n"
            "  task: deny\n"
            "---\n"
            "\n"
            "Alter Prompt.\n"
        )

        changed = self.cli.agent_render_fields("global", text, {"permission": "lesen"})

        assert_no_v1_keys(self, changed)
        self.assertIn("color: blau", changed)
        self.assertIn("tools:\n  write: true", changed)
        self.assertIn("Alter Prompt.", changed)
        self.assertEqual(pair_list(block_rules(changed, "read")), [("*", "allow")])
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.cli.agent_validate(changed)

    def test_render_replaces_a_v2_block(self):
        text = self.cli.agent_template("Agent", perm="voll")

        changed = self.cli.agent_render_fields(
            "global", text, {"permission": "lesen"}
        )

        assert_no_v1_keys(self, changed)
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.assertEqual(pair_list(block_rules(changed, "shell")), [("*", "deny")])
        self.cli.agent_validate(changed)

    def test_unknown_permission_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cli.agent_render_fields(
                "global", self.cli.agent_template("Agent"), {"permission": "root"}
            )


# --------------------------------------------------------------------------
# A5: agent_task_policy liest v2-Subagenten-Regeln, v1-Fallback bleibt
# --------------------------------------------------------------------------

class A5TaskPolicyTest(CliFixture):
    def policy(self, rules):
        return self.cli.agent_task_policy(v2_agent(rules))

    def test_star_allow_means_all(self):
        self.assertEqual(
            self.policy([("subagent", "*", "allow")]),
            {"mode": "all", "allowed": []},
        )

    def test_star_deny_means_none(self):
        self.assertEqual(
            self.policy([("subagent", "*", "deny")]),
            {"mode": "none", "allowed": []},
        )

    def test_deny_star_plus_named_allows_is_sorted_custom(self):
        self.assertEqual(
            self.policy(
                [
                    ("subagent", "*", "deny"),
                    ("subagent", "b", "allow"),
                    ("subagent", "a", "allow"),
                ]
            ),
            {"mode": "custom", "allowed": ["a", "b"]},
        )

    def test_later_rules_win(self):
        self.assertEqual(
            self.policy(
                [("subagent", "*", "deny"), ("subagent", "*", "allow")]
            )["mode"],
            "all",
        )
        self.assertEqual(
            self.policy(
                [("subagent", "*", "allow"), ("subagent", "*", "deny")]
            )["mode"],
            "none",
        )
        self.assertEqual(
            self.policy(
                [
                    ("subagent", "a", "allow"),
                    ("subagent", "*", "deny"),
                ]
            )["mode"],
            "none",
        )

    def test_v1_permission_task_fallback_still_works(self):
        self.assertEqual(
            self.cli.agent_task_policy(V1_LESEN_AGENT),
            {"mode": "none", "allowed": []},
        )
        custom = agent_text(
            "description: Alt\nmode: subagent\n"
            "permission:\n  read: allow\n  edit: deny\n"
            "  task:\n    \"*\": deny\n    b: allow\n    a: allow"
        )
        self.assertEqual(
            self.cli.agent_task_policy(custom),
            {"mode": "custom", "allowed": ["a", "b"]},
        )
        allow = agent_text(
            "description: Alt\nmode: subagent\n"
            "permission:\n  read: allow\n  task: allow"
        )
        self.assertEqual(
            self.cli.agent_task_policy(allow), {"mode": "all", "allowed": []}
        )

    def test_generated_template_denies_subagents_by_default(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Agent", perm=preset)
                self.assertEqual(
                    self.cli.agent_task_policy(text),
                    {"mode": "none", "allowed": []},
                )


# --------------------------------------------------------------------------
# A6: agent_render_task schreibt v2-Subagenten-Regeln
# --------------------------------------------------------------------------

class A6RenderTaskTest(CliFixture):
    def test_allow_all_replaces_only_subagent_rules(self):
        text = self.cli.agent_template("Agent", perm="voll")
        before = opencode_parse_permissions(text)

        changed = self.cli.agent_render_task("global", text, [], allow_all=True)

        after = opencode_parse_permissions(changed) or []
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "subagent"]),
            [("*", "allow")],
        )
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "subagent"],
            [rule for rule in after if rule.get("action") != "subagent"],
        )
        self.cli.agent_validate(changed)

    def test_no_allowed_agents_writes_subagent_deny(self):
        text = self.cli.agent_template("Agent")

        changed = self.cli.agent_render_task("global", text, [])

        self.assertEqual(
            pair_list(block_rules(changed, "subagent")), [("*", "deny")]
        )
        self.cli.agent_validate(changed)

    def test_custom_agents_write_deny_star_and_sorted_allows(self):
        text = self.cli.agent_template("Agent")

        changed = self.cli.agent_render_task("global", text, ["b", "a"])

        self.assertEqual(
            pair_list(block_rules(changed, "subagent")),
            [("*", "deny"), ("a", "allow"), ("b", "allow")],
        )
        self.cli.agent_validate(changed)

    def test_matching_v1_template_block_is_migrated_completely(self):
        changed = self.cli.agent_render_task(
            "global", V1_LESEN_AGENT, ["x"]
        )

        assert_no_v1_keys(self, changed)
        self.assertIn("Alt-Prompt.", changed)
        self.assertEqual(pair_list(block_rules(changed, "read")), [("*", "allow")])
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.assertEqual(pair_list(block_rules(changed, "shell")), [("*", "deny")])
        self.assertEqual(
            pair_list(block_rules(changed, "subagent")),
            [("*", "deny"), ("x", "allow")],
        )
        self.cli.agent_validate(changed)

    def test_individual_v1_block_keeps_v1_task_syntax(self):
        changed = self.cli.agent_render_task("global", V1_CUSTOM_AGENT, ["x"])

        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(opencode_parse_permissions(changed))
        self.assertIn("task:", changed)
        self.assertNotIn("subagent:", changed)
        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["x"]},
        )
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A7: Schreibverzeichnisse mit v2-Blöcken
# --------------------------------------------------------------------------

class A7WriteDirsTest(CliFixture):
    def test_v2_full_grants_write_and_v2_readonly_does_not(self):
        self.assertTrue(
            self.cli._edit_grants_write(self.cli.agent_template("A", perm="voll"))
        )
        self.assertFalse(
            self.cli._edit_grants_write(self.cli.agent_template("A", perm="lesen"))
        )

    def test_rewrite_edit_block_changes_only_edit_rules(self):
        text = self.cli.agent_template(
            "A", perm="voll", write_dirs=["/tmp/opencode"]
        )
        before = opencode_parse_permissions(text) or []

        changed = self.cli._rewrite_edit_block(text, ["/tmp/zweites"])

        after = opencode_parse_permissions(changed) or []
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "edit"],
            [rule for rule in after if rule.get("action") != "edit"],
        )
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "edit"]),
            [
                ("*", "deny"),
                ("/tmp/zweites", "allow"),
                ("/tmp/zweites/**", "allow"),
            ],
        )
        self.cli.agent_validate(changed)

    def test_apply_write_dirs_rewrites_a_v2_project_agent(self):
        dirs = ["/tmp/opencode", str(self.project)]
        text = self.cli.agent_template("A", perm="voll", write_dirs=dirs)
        path = self.write_project_agent(self.project, "schreiber", text)
        before = opencode_parse_permissions(text) or []

        changed = self.cli.apply_write_dirs(
            "proj", "schreiber", ["/tmp/neu"]
        )

        self.assertEqual(changed, path.read_text(encoding="utf-8"))
        after = opencode_parse_permissions(changed) or []
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "edit"],
            [rule for rule in after if rule.get("action") != "edit"],
        )
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "edit"]),
            [("*", "deny"), ("/tmp/neu", "allow"), ("/tmp/neu/**", "allow")],
        )
        backups = list(
            (self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md")
        )
        self.assertEqual(len(backups), 1)

    def test_apply_write_dirs_to_project_skips_read_only_v2_agents(self):
        writable = self.write_project_agent(
            self.project,
            "schreiber",
            self.cli.agent_template("A", perm="voll", write_dirs=["/tmp/opencode"]),
        )
        readonly = self.write_project_agent(
            self.project,
            "leser",
            self.cli.agent_template("B", perm="lesen"),
        )
        # Ohne eigene permissions.json gelten die Standardverzeichnisse; die
        # Erwartung "/tmp/neu" setzt daher eine ausdrückliche Projektliste voraus.
        self.cli.write_dirs_save("proj", ["/tmp/neu"])

        changed = self.cli.apply_write_dirs_to_project("proj")

        self.assertEqual(changed, ["schreiber"])
        self.assertIn("/tmp/neu", writable.read_text(encoding="utf-8"))
        self.assertEqual(
            readonly.read_text(encoding="utf-8"),
            self.cli.agent_template("B", perm="lesen"),
        )

    def test_v1_blocks_stay_functional(self):
        self.assertTrue(self.cli._edit_grants_write(V1_LESEN_AGENT) is False)
        full = agent_text(
            "description: Alt\nmode: subagent\n" + V1_FULL_PERMISSION
        )
        self.assertTrue(self.cli._edit_grants_write(full))
        changed = self.cli._rewrite_edit_block(full, ["/tmp/opencode"])
        self.assertIn("/tmp/opencode", changed)
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A8: Hierarchie-Prüfung mit v2-Blöcken
# --------------------------------------------------------------------------

class A8HierarchyTest(CliFixture):
    def test_v2_hierarchy_unknown_and_cycle_rules_unchanged(self):
        self.write_global(
            "a", v2_agent(LESEN_RULES + [("subagent", "b", "allow")])
        )
        self.write_global(
            "b", v2_agent(LESEN_RULES + [("subagent", "a", "allow")])
        )

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["b"])
        self.assertIn("Zyklus", str(caught.exception))

        self.write_global("b", v2_agent(LESEN_RULES))
        self.assertEqual(self.cli.agent_validate_hierarchy("a", ["b"]), ["b"])

    def test_v2_self_call_allowed_for_subagent_but_not_for_vibe_agent(self):
        self.write_global(
            "a", v2_agent(LESEN_RULES + [("subagent", "a", "allow")])
        )

        self.assertEqual(self.cli.agent_validate_hierarchy("a", ["a"]), ["a"])

        data = self.cli.profiles_load()
        data["rollen"] = {"a": "vibe"}
        self.cli.profiles_save(data)

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["a"])

    def test_primary_agents_stay_unavailable_as_subagents(self):
        self.write_global("a", v2_agent(LESEN_RULES))
        self.write_global("p", v2_agent(LESEN_RULES, mode="primary"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["p"])
        self.assertIn("kein Subagent", str(caught.exception))


# --------------------------------------------------------------------------
# A9: mitgelieferte opencode.json nutzt v2
# --------------------------------------------------------------------------

class A9ShippedConfigTest(unittest.TestCase):
    def test_templates_common_opencode_json_uses_v2_permissions(self):
        path = REPO / "templates" / "common" / "opencode.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        self.assertNotIn("permission", data,
                         "Der v1-Schlüssel 'permission' ist noch vorhanden")
        self.assertIn("permissions", data)
        self.assertIsInstance(data["permissions"], list)
        actions = [rule.get("action") for rule in data["permissions"]]
        self.assertIn("shell", actions)
        self.assertNotIn("bash", json.dumps(data),
                         "Der v1-Schlüssel 'bash' ist noch vorhanden")
        for rule in data["permissions"]:
            self.assertEqual(set(rule), {"action", "resource", "effect"})


# --------------------------------------------------------------------------
# B1: Version 3 der Projekt-Agentenauswahl
# --------------------------------------------------------------------------

class B1ProjectConfigTest(CliFixture):
    def load(self, project="proj"):
        return self.cli.project_agents_load(project)[0]

    def test_missing_file_defaults_to_version_3_with_both_opencode_agents(self):
        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(set(config["opencode"]), {"general", "explore"})
        for name in ("general", "explore"):
            self.assertIs(config["opencode"][name]["aktiv"], True)
            self.assertEqual(config["opencode"][name]["modell"], "")
        self.assertNotIn("general", config["aktiv"])
        self.assertNotIn("explore", config["aktiv"])

    def test_version_2_is_migrated_with_opencode_defaults(self):
        self.write_config(
            self.project,
            {"version": 2, "aktiv": ["tester"], "modelle": {}},
        )

        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(config["aktiv"], ["tester"])
        self.assertEqual(config["opencode"]["general"]["aktiv"], True)
        self.assertEqual(config["opencode"]["explore"]["modell"], "")

    def test_valid_version_3_roundtrip(self):
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["tester"],
                "modelle": {"tester": "opencode/tester-modell"},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": ""},
                },
            },
        )

        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(config["opencode"]["general"]["aktiv"], False)
        self.assertEqual(config["opencode"]["general"]["modell"], "free/general")
        self.assertEqual(config["opencode"]["explore"]["aktiv"], True)

    def test_unknown_opencode_agent_name_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"build": {"aktiv": True, "modell": ""}}},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("build", str(caught.exception))

    def test_unknown_opencode_entry_field_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"general": {"aktiv": True, "farbe": "rot"}}},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("farbe", str(caught.exception))

    def test_aktiv_must_be_a_json_boolean(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"general": {"aktiv": "ja", "modell": ""}}},
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_modell_must_be_a_string_and_a_valid_model_pattern(self):
        for value in (5, "kein modell mit leerzeichen"):
            with self.subTest(value=value):
                self.write_config(
                    self.project,
                    {"version": 3, "aktiv": [], "modelle": {},
                     "opencode": {"explore": {"aktiv": True, "modell": value}}},
                )
                with self.assertRaises(ValueError):
                    self.load()

    def test_start_agent_list_rejects_opencode_agents(self):
        for name in ("general", "explore"):
            with self.subTest(name=name):
                self.write_config(
                    self.project,
                    {"version": 3, "aktiv": [name], "modelle": {}},
                )
                with self.assertRaises(ValueError):
                    self.load()

    def test_unknown_top_level_field_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {}, "farbe": "rot"},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("farbe", str(caught.exception))


# --------------------------------------------------------------------------
# B2: project_agent_rows zeigt opencode-Zeilen
# --------------------------------------------------------------------------

class B2RowsTest(CliFixture):
    def write_global_agents(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        self.write_global(
            "tester", v2_agent(LESEN_RULES, model="opencode/tester-modell")
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)

    def rows(self):
        return {row["name"]: row for row in self.cli.project_agent_rows("proj")}

    def test_rows_include_general_and_explore_with_marker(self):
        self.write_global_agents()

        rows = self.rows()

        for name in ("general", "explore"):
            self.assertIn(name, rows)
            self.assertIs(rows[name].get("opencode"), True)
        self.assertFalse(rows["tester"].get("opencode", False))

    def test_opencode_rows_reflect_toggle_and_effective_model(self):
        self.write_global_agents()
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["vibe-agent"],
                "modelle": {},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": ""},
                },
            },
        )

        rows = self.rows()

        self.assertFalse(rows["general"]["configured"])
        self.assertFalse(rows["general"]["selected"])
        self.assertEqual(rows["general"]["effective_model"], "free/general")
        self.assertTrue(rows["explore"]["configured"])
        self.assertEqual(rows["explore"]["effective_model"], "")

    def test_opencode_rows_are_not_file_agents(self):
        self.write_global_agents()

        inventory = self.cli.project_agent_inventory("proj")
        self.assertNotIn("general", inventory)
        self.assertNotIn("explore", inventory)
        with self.assertRaises(ValueError):
            self.cli.agent_read("global", "general")
        with self.assertRaises(ValueError):
            self.cli.agent_read("global", "explore")


# --------------------------------------------------------------------------
# B3: project_agent_set ändert nur den opencode-Abschnitt
# --------------------------------------------------------------------------

class B3SetTest(CliFixture):
    def write_global_agents(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        self.write_global(
            "tester", v2_agent(LESEN_RULES, model="opencode/tester-modell")
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)

    def test_toggle_changes_only_the_opencode_section(self):
        self.write_global_agents()
        tester_before = (self.agents / "tester.md").read_bytes()

        self.cli.project_agent_set("proj", "general", selected=False)

        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 3)
        self.assertIs(stored["opencode"]["general"]["aktiv"], False)
        self.assertNotIn("general", stored["aktiv"])
        self.assertEqual((self.agents / "tester.md").read_bytes(), tester_before)
        self.assertFalse(self.config_path(self.other).exists())

    def test_model_is_stored_and_can_be_cleared_without_changing_aktiv(self):
        self.write_global_agents()
        self.cli.project_agent_set("proj", "explore", selected=False)

        self.cli.project_agent_set("proj", "explore", model="free/explore")
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["opencode"]["explore"]["modell"], "free/explore")
        self.assertIs(stored["opencode"]["explore"]["aktiv"], False)

        self.cli.project_agent_set("proj", "explore", model="")
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["opencode"]["explore"].get("modell", ""), "")
        self.assertIs(stored["opencode"]["explore"]["aktiv"], False)

    def test_invalid_values_are_rejected_without_writing(self):
        self.write_global_agents()
        cases = [
            ("general", {"selected": "nein"}),
            ("general", {"model": "kein modell mit leerzeichen"}),
            ("general", {"model": 5}),
        ]
        for agent, kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.cli.project_agent_set("proj", agent, **kwargs)
                self.assertFalse(self.config_path(self.project).exists())

    def test_unknown_opencode_agent_is_rejected(self):
        self.write_global_agents()
        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "build", selected=False)
        self.assertFalse(self.config_path(self.project).exists())

    def test_concurrent_change_is_refused(self):
        self.write_global_agents()
        path = self.write_config(
            self.project,
            {"version": 3, "aktiv": ["vibe-agent"], "modelle": {}},
        )
        snapshot = self.cli.vibe_storage.read_snapshot(path)
        path.write_text(
            json.dumps({"version": 3, "aktiv": [], "modelle": {}}),
            encoding="utf-8",
        )

        with self.assertRaises(self.cli.vibe_storage.ConcurrentChangeError):
            self.cli.project_agents_save(
                "proj",
                {"version": 3, "aktiv": ["vibe-agent"], "modelle": {}},
                expected=snapshot.digest,
            )


# --------------------------------------------------------------------------
# B4/A2-API: HTTP-Endpunkte
# --------------------------------------------------------------------------

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version) printf 'opencode 2.3.0\\n' ;;
  models)
    printf 'opencode/start\\nopencode/free-modell\\nopencode/vibe-modell\\n'
    ;;
esac
exit 0
"""


class WebApiTest(unittest.TestCase):
    """GET/POST /api/project-agents und POST /api/agent_template."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.agents / "vibe-agent.md").write_text(
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
            encoding="utf-8",
        )
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
        cls.port = free_port()
        env = isolated_env_ap2(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_ap2)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        path = self.project / ".vibe" / "agents.json"
        path.unlink(missing_ok=True)

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", "127.0.0.1:%d" % self.port)
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def agent_rows(self):
        status, body = self.request("/api/project-agents?name=proj")
        self.assertEqual(status, 200, body)
        return json.loads(body)["agents"]

    def test_get_contains_opencode_rows(self):
        rows = {row["name"]: row for row in self.agent_rows()}
        for name in ("general", "explore"):
            self.assertIn(name, rows)
            self.assertIs(rows[name].get("opencode"), True)

    def test_post_toggle_and_model_for_opencode_agent(self):
        status, body = self.request(
            "/api/project-agents",
            {"name": "proj", "agent": "general", "selected": False},
        )
        self.assertEqual(status, 200, body)
        rows = {row["name"]: row for row in self.agent_rows()}
        self.assertFalse(rows["general"]["selected"])

        status, body = self.request(
            "/api/project-agents",
            {"name": "proj", "agent": "explore", "model": "free/explore"},
        )
        self.assertEqual(status, 200, body)
        rows = {row["name"]: row for row in self.agent_rows()}
        self.assertEqual(rows["explore"]["effective_model"], "free/explore")

    def test_invalid_post_returns_400_without_writing(self):
        path = self.project / ".vibe" / "agents.json"
        before = path.read_bytes() if path.exists() else None
        for payload in (
            {"name": "proj", "agent": "explore", "model": "bad model"},
            {"name": "proj", "agent": "build", "selected": True},
            {"name": "proj", "agent": "general", "selected": "ja"},
        ):
            with self.subTest(payload=payload):
                status, body = self.request("/api/project-agents", payload)
                self.assertEqual(status, 400, body)
                after = path.read_bytes() if path.exists() else None
                self.assertEqual(after, before)

    def test_agent_template_api_returns_v2_frontmatter(self):
        status, body = self.request(
            "/api/agent_template",
            {"scope": "proj", "description": "API-Agent", "perm": "lesen"},
        )
        self.assertEqual(status, 200, body)
        text = json.loads(body)["message"]
        assert_no_v1_keys(self, text)
        self.assertIn("description: API-Agent", text)


# --------------------------------------------------------------------------
# B7: CLI zeigt opencode-Zeilen
# --------------------------------------------------------------------------

class B7CliTest(CliFixture):
    def test_project_agents_cli_lists_opencode_state_and_model(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["vibe-agent"],
                "modelle": {},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": "free/explore"},
                },
            },
        )

        result = subprocess.run(
            [sys.executable, str(CLI_ap2), "project-agents", "proj"],
            cwd=str(self.root),
            env=isolated_env_ap2(self.root, self.home),
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        general = [line for line in output.splitlines() if line.startswith("general")]
        explore = [line for line in output.splitlines() if line.startswith("explore")]
        self.assertTrue(general, output)
        self.assertTrue(explore, output)
        self.assertRegex(general[0], r"nein|aus|verboten|inaktiv")
        self.assertIn("free/general", general[0])
        self.assertIn("free/explore", explore[0])


# --------------------------------------------------------------------------
# B6: Läufer mischt opencode-Einträge in OPENCODE_CONFIG_CONTENT
# --------------------------------------------------------------------------

ENV_RECORDING_OPENCODE = r'''#!/usr/bin/env python3
import json
import os
import sys

record = os.environ.get("FAKE_ENV_RECORD")
if record:
    entry = {
        "argv": sys.argv[1:],
        "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
    }
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

impl = os.environ.get("FAKE_OPENCODE_IMPL")
if not impl:
    raise SystemExit("FAKE_OPENCODE_IMPL fehlt")
os.execv(sys.executable, [sys.executable, impl] + sys.argv[1:])
'''


def effective_model(config, agent):
    if not isinstance(config, dict):
        return None
    for key in ("agents", "agent"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return entry["model"]
    return None


class SharedOpenCode:
    """Erreichbarer gemeinsamer opencode-Server für die Wiederverwendung."""

    def __init__(self, port):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        try:
            self.httpd.shutdown()
        finally:
            self.httpd.server_close()
            self.thread.join(timeout=5)


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer", "vibe-agent")
        self.runtime = self.root / "_logs"
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.fakebin = support.install_fake_tools(self.root)
        support.install_real_curl(self.fakebin)
        self.impl = self.fakebin / "opencode_impl"
        self.impl.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        self.impl.chmod(0o755)
        opencode = self.fakebin / "opencode"
        opencode.write_text(ENV_RECORDING_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)

        self.project = self.root / "proj"
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback=[support.ticket_record(
                "B6", "Testpaket",
                description="opencode-Agenten im Lauf")],
        )
        (self.project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        support.init_repo(self.project)
        support.commit_all(self.project)

        self.env_record = self.root / "opencode.env.jsonl"
        self.args_file = self.runtime / "opencode.args"
        self.serve_record = self.root / "serve.record.jsonl"
        self.shared = None
        self.addCleanup(self.stop_shared)

    def config_path(self):
        return self.project / ".vibe" / "agents.json"

    def write_config(self, data):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def write_opencode(self, general=None, explore=None, modelle=None, aktiv=None):
        data = {
            "version": 3,
            "aktiv": sorted(aktiv if aktiv is not None else (modelle or {})),
            "modelle": modelle or {},
            "opencode": {
                "general": general or {"aktiv": True, "modell": ""},
                "explore": explore or {"aktiv": True, "modell": ""},
            },
        }
        return self.write_config(data)

    def env(self, extra=None):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key.startswith("OPENCODE_")
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_OPENCODE_PORT": str(free_port()),
                "VIBE_MAX_PACKAGES": "1",
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.args_file),
                "FAKE_ENV_RECORD": str(self.env_record),
                "FAKE_OPENCODE_IMPL": str(self.impl),
                "FAKE_SERVE_RECORD": str(self.serve_record),
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
            }
        )
        if extra:
            env.update(extra)
        return env

    def start_shared_server(self):
        port = free_port()
        self.shared = SharedOpenCode(port).start()
        return port

    def stop_shared(self):
        if self.shared is not None:
            self.shared.stop()
            self.shared = None

    def run_runner(self, *arguments, extra_env=None, timeout=180):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project), *arguments],
            cwd=str(self.project),
            env=self.env(extra_env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def records(self):
        try:
            raw = self.env_record.read_text(encoding="utf-8")
        except OSError:
            return []
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def run_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "run"]

    def serve_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "serve"]

    def config_of(self, entry):
        raw = entry.get("config")
        self.assertIsInstance(
            raw, str,
            "opencode erhielt keine OPENCODE_CONFIG_CONTENT: " + repr(entry))
        return json.loads(raw)

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


class RunnerControlTest(RunnerFixture):
    def test_no_effective_entries_still_injects_platform_instructions(self):
        """GH-76: Auch ohne Modell-Einträge wird der Plattformtext gesetzt.

        Der frühere gemeinsame Server wird nicht wiederverwendet, weil er die
        Instruktion nicht kennt: der Lauf startet ``--standalone``. Es
        entstehen keine Agenten-Maps.
        """
        self.write_opencode()
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertNotIn("agent", config)
        self.assertNotIn("agents", config)
        instructions = config.get("instructions")
        self.assertEqual(1, len(instructions), config)
        path = Path(instructions[0])
        self.assertTrue(path.is_absolute(), instructions)
        self.assertTrue(path.is_file(), path)
        self.assertIn("## Vibe platform instructions",
                      path.read_text(encoding="utf-8"))
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))


class RunnerOpencodeConfigTest(RunnerFixture):
    def test_active_model_is_mixed_into_both_agent_maps(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
            modelle={"tester": "projekt/tester-modell"},
        )

        result = self.run_runner("tester", "auftrag/start-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(effective_model(config, "general"), "free/general")
        self.assertEqual(config["agent"]["general"]["model"], "free/general")
        self.assertEqual(config["agents"]["general"]["model"], "free/general")
        self.assertEqual(effective_model(config, "tester"), "projekt/tester-modell")

    def test_inactive_agent_disables_only_the_v2_agents_map(self):
        self.write_opencode(
            general={"aktiv": False, "modell": ""},
            explore={"aktiv": False, "modell": ""},
        )

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        for name in ("general", "explore"):
            self.assertIs(config["agents"][name].get("disabled"), True,
                          "opencode-Agent wurde nicht deaktiviert: " + name)
            self.assertNotIn(
                "disabled", config.get("agent", {}).get(name, {}),
                "Deaktivierung landete in der Legacy-agent-Map: " + name)
            self.assertNotIn(
                name, config.get("agent", {}),
                "Deaktivierter Agent wurde als Legacy-agent-Eintrag angelegt: " + name)

    def test_inactive_model_is_not_applied(self):
        self.write_opencode(
            explore={"aktiv": False, "modell": "free/explore"},
        )

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        config = self.config_of(self.run_calls()[0])
        self.assertIs(config["agents"]["explore"].get("disabled"), True)
        self.assertIsNone(effective_model(config, "explore"),
                          "Ein Modell eines verbotenen opencode-Agenten wurde gesetzt")

    def test_existing_jsonc_config_is_merged_and_preserved(self):
        jsonc = """{
  // Bestehende Anmerkung
  "theme": "dark",
  "agent": {
    "reviewer": {
      "model": "global/reviewer",
      "temperature": 0.2,
    },
  },
}
"""
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
            explore={"aktiv": False, "modell": ""},
        )

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        config = self.config_of(self.run_calls()[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(
            config["agent"]["reviewer"].get("temperature"), 0.2)
        self.assertEqual(effective_model(config, "general"), "free/general")
        self.assertIs(config["agents"]["explore"].get("disabled"), True)
        self.assertNotIn(
            "disabled", config.get("agent", {}).get("explore", {}))

    def test_shared_server_is_not_reused_with_effective_opencode_entry(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
        )
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))
        self.assertNotIn("http://127.0.0.1:" + str(shared_port), argv)
        self.assertEqual(effective_model(self.config_of(runs[0]), "general"),
                         "free/general")


class RunnerInvalidConfigTest(RunnerFixture):
    def assert_no_agent_started(self):
        self.assertEqual([], self.run_calls(),
                         "Agent wurde trotz fehlerhafter Konfiguration gestartet")
        self.assertEqual([], self.serve_calls(),
                         "Privater Server wurde trotz fehlerhafter Konfiguration gestartet")

    def test_invalid_opencode_model_aborts_before_agent_start(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "kein modell mit leerzeichen"},
        )
        secret = "ap2-geheim-4711"

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_SERVER_PASSWORD": secret}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(result.returncode, 0, detail)
        self.assert_no_agent_started()
        self.assertRegex(
            detail,
            r"Agentenauswahl|Modell|opencode",
            "Keine verständliche Meldung zur ungültigen opencode-Konfiguration:\n"
            + detail,
        )
        self.assertNotIn(secret, detail,
                         "Ein Geheimnis wurde im Protokoll ausgegeben")

    def test_unreadable_project_config_aborts_before_agent_start(self):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{kaputt", encoding="utf-8")

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(result.returncode, 0, detail)
        self.assert_no_agent_started()
        self.assertRegex(
            detail,
            r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei",
            "Keine verständliche Meldung zur fehlerhaften Projektdatei:\n" + detail,
        )


# ===========================================================================
# Unabhängige Abnahmetests: Subagenten-Rechte beim Regenerieren von Agentendateien
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
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

CLI_b7 = BIN / "vibe"
WEB_b7 = BIN / "vibe-web.py"

# Variablen der laufenden Instanz dürfen nie in einen Testprozess gelangen.
ISOLATED_ENV_b7 = (
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
    "VIBE_UI_BIND",
    "VIBE_OPENCODE_PORT",
    "VIBE_CONTAINER",
    "AGENT",
    "SANDBOX",
    "SANDBOX_TOOLS",
    "VIBE_SANDBOX_ROOT",
)


def isolated_env_b7(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_b7:
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli_b7(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_b7}
    for key in ISOLATED_ENV_b7:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_b7(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b7_under_test", str(CLI_b7)
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


# --------------------------------------------------------------------------
# Parser-Helfer: prüfen die Struktur, nicht die Byte-Position der Blöcke.
# --------------------------------------------------------------------------


def subagent_parse_permissions(text):
    """Liest einen v2-``permissions``-Block als Liste von Regel-Dicts.

    Die Reihenfolge der Regeln bleibt erhalten; ``None`` bedeutet, dass kein
    v2-Block vorhanden ist (z. B. ein v1-``permission``-Block).
    """
    if FRONTMATTER_RE.match(text):
        lines = frontmatter_lines(text)
    else:
        lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^permissions:[ \t]*$", line):
            start = index + 1
            break
    if start is None:
        return None
    rules, current = [], None
    for line in lines[start:]:
        if line and not line.startswith((" ", "\t")):
            break
        if not line.strip():
            continue
        if re.match(r"^[ \t]*-[ \t]+", line):
            if current is not None:
                rules.append(current)
            current = {}
        item = _key_value(line)
        if item is None:
            continue
        if current is None:
            current = {}
        current[item[0]] = item[1]
    if current is not None:
        rules.append(current)
    return rules


def rule_pairs(text, action):
    """(resource, effect)-Paare aller Regeln einer Aktion, in Blockreihenfolge."""
    rules = subagent_parse_permissions(text)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block in:\n" + text)
    return [
        (rule.get("resource"), rule.get("effect"))
        for rule in rules
        if rule.get("action") == action
    ]


def non_subagent_rules(text):
    """Alle Regeln außer ``subagent`` als (action, resource, effect)."""
    rules = subagent_parse_permissions(text)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block in:\n" + text)
    return [
        (rule.get("action"), rule.get("resource"), rule.get("effect"))
        for rule in rules
        if rule.get("action") != "subagent"
    ]


def preset_non_subagent(preset):
    """Erwartete Nicht-subagent-Regeln einer Rechte-Vorlage (AP2-Vertrag)."""
    return [rule for rule in PRESET_RULES[preset] if rule[0] != "subagent"]


# --------------------------------------------------------------------------
# Eingabedateien
# --------------------------------------------------------------------------

# Produktionsnahe v1-Datei aus dem gemeldeten Fall: der Nutzer hatte
# ``task: allow`` von Hand gesetzt, damit der Orchestrator Subagenten ruft.
V1_TASK_ALLOW_AGENT = """---
description: Orchestrator mit erlaubten Subagenten
mode: primary
model: opencode/orchestrator-modell
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  task: allow
  webfetch: deny
  websearch: deny
---

Bestehender Prompt.
"""

# v1-Datei mit individueller task-Map (deny-Grundregel plus zwei Freigaben).
V1_TASK_CUSTOM_AGENT = """---
description: Agent mit ausgewaehlten Subagenten
mode: subagent
permission:
  read: allow
  edit: deny
  task:
    "*": deny
    vibe-coder: allow
    tester: allow
---

Individueller Prompt.
"""

# v1-Vorlage „lesen“: Subagenten ausdrücklich gesperrt.
V1_TASK_DENY_AGENT = """---
description: Nur lesen ohne Subagenten
mode: subagent
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: deny
  bash: deny
  task: deny
  webfetch: deny
  websearch: deny
---

Lese-Prompt.
"""

# v1-Datei ganz ohne task-Eintrag: daraus darf keine Freigabe erfunden werden.
V1_NO_TASK_AGENT = """---
description: Alt ohne task-Eintrag
mode: subagent
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  webfetch: deny
  websearch: deny
---

Prompt ohne task.
"""


def subagent_v2_agent(rules, description="V2-Agent", mode="subagent", model="opencode/test-modell"):
    lines = ["---", "description: " + description, "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines.append("permissions:")
    for action, resource, effect in rules:
        lines.append("  - action: " + action)
        lines.append("    resource: " + json.dumps(resource))
        lines.append("    effect: " + effect)
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


V2_SUBAGENT_CUSTOM_RULES = [
    ("read", "*", "allow"),
    ("edit", "*", "deny"),
    ("shell", "*", "deny"),
    ("subagent", "*", "deny"),
    ("subagent", "tester", "allow"),
    ("subagent", "vibe-coder", "allow"),
]

V2_SUBAGENT_CUSTOM_AGENT = subagent_v2_agent(
    V2_SUBAGENT_CUSTOM_RULES, description="V2 mit ausgewaehlten Subagenten"
)

V2_SUBAGENT_ALL_AGENT = subagent_v2_agent(
    [
        ("read", "*", "allow"),
        ("edit", "*", "deny"),
        ("subagent", "*", "allow"),
    ],
    description="V2 mit allen Subagenten",
)

V2_WITHOUT_SUBAGENT_AGENT = subagent_v2_agent(
    [("read", "*", "allow"), ("edit", "*", "deny")],
    description="V2 ohne Subagentenregeln",
)

NO_BLOCK_AGENT = """---
description: Datei ohne Rechteblock
mode: subagent
---

Prompt ohne Rechte.
"""

# Vertrag der Rechte-Vorlagen (AP2 prüft die Vorlagen selbst; B7 nutzt sie als
# erwartete Nicht-subagent-Regeln).
PRESET_RULES = {
    "voll": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "allow"),
        ("shell", "*", "allow"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
    "lesen": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "deny"),
        ("shell", "*", "deny"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
    "lesen_git": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "deny"),
        ("shell", "*", "deny"),
        ("shell", "git status --short", "allow"),
        ("shell", "git diff *", "allow"),
        ("shell", "git show *", "allow"),
        ("shell", "git log *", "allow"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
}


class SubagentPermissionFixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.cli = load_cli_b7(self.root, self.home)
        self.cli._AGENT_VERSION = None
        # Kein opencode-Prozess und keine Anbieterabfrage in der Prüfung.
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        return project

    def write_global(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# 1. Vorlage anwenden: Subagenten-Policy der Eingabedatei bleibt erhalten
# --------------------------------------------------------------------------


class RenderFieldsSubagentPolicyTest(SubagentPermissionFixture):
    """``agent_render_fields`` (Serverpfad von „Speichern“ und „In Rohtext übernehmen“).

    Vorbedingung ist jeweils eine Agentendatei im temporären Agentenordner;
    Aktion ist das Anwenden einer Rechte-Vorlage über ``values.permission``;
    Erwartung ist, dass nur die Nicht-subagent-Regeln aus der Vorlage kommen
    und die Subagenten-Rechte die Policy der Eingabedatei wiedergeben.
    """

    def render(self, text, values):
        return self.cli.agent_render_fields("global", text, values)

    def test_v1_task_allow_survives_preset_application(self):
        """Gemeldeter Fall: v1 ``task: allow`` + Vorlage ``voll`` bleibt erlaubt.

        Vorher: Datei erlaubt Subagenten über v1 ``task: allow``.
        Aktion: ``agent_render_fields(..., {"permission": "voll"})``.
        Erwartet: v2-Block ohne v1-Schlüssel, Nicht-subagent-Regeln der Vorlage
        ``voll``, Subagenten-Policy weiterhin „alle“ (allow-Regel vorhanden).
        """
        changed = self.render(V1_TASK_ALLOW_AGENT, {"permission": "voll"})

        self.assertFalse(
            has_top_level_key(changed, "permission"),
            "Der v1-Block 'permission:' wurde nicht auf v2 migriert:\n" + changed,
        )
        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(changed, "subagent"))
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))
        self.assertIn("Bestehender Prompt.", changed)
        self.cli.agent_validate(changed)

    def test_v1_custom_task_map_survives_preset_application(self):
        """v1-task-Map (deny + Freigaben) bleibt nach Vorlage ``lesen`` erhalten.

        Vorher: ``task: {"*": deny, "vibe-coder": allow, "tester": allow}``.
        Aktion: Vorlage ``lesen`` anwenden.
        Erwartet: deny-Grundregel plus sortierte Freigaben ``tester``,
        ``vibe-coder``; die Freigaben dürfen nicht auf die Vorlagen-Sperre
        zurückfallen.
        """
        changed = self.render(V1_TASK_CUSTOM_AGENT, {"permission": "lesen"})

        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["tester", "vibe-coder"]},
        )
        self.assertEqual(
            rule_pairs(changed, "subagent"),
            [("*", "deny"), ("tester", "allow"), ("vibe-coder", "allow")],
        )
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("lesen"))
        self.cli.agent_validate(changed)

    def test_v2_subagent_rules_survive_preset_application(self):
        """Vorhandene v2-Subagenten-Regeln bleiben bei Vorlage ``lesen_git``.

        Vorher: v2-Datei mit ``subagent`` deny + zwei Freigaben (bzw. allow
        für ``*``).
        Aktion: Vorlage ``lesen_git`` anwenden.
        Erwartet: Subagenten-Regeln unverändert, alle anderen Regeln aus der
        Vorlage (inklusive der vier erlaubten Git-Lesebefehle).
        """
        for text in (V2_SUBAGENT_CUSTOM_AGENT, V2_SUBAGENT_ALL_AGENT):
            with self.subTest(text=text.splitlines()[1]):
                before = rule_pairs(text, "subagent")
                changed = self.render(text, {"permission": "lesen_git"})
                self.assertEqual(rule_pairs(changed, "subagent"), before)
                self.assertEqual(
                    non_subagent_rules(changed), preset_non_subagent("lesen_git")
                )
                self.cli.agent_validate(changed)

    def test_v2_without_subagent_rules_gets_template_default_deny(self):
        """Charakterisierung: v2 ohne subagent-Regeln erhält die Vorlagen-Sperre.

        Vorher: v2-Datei nur mit ``read``/``edit``. Aktion: Vorlage ``lesen``.
        Erwartet: genau eine Subagenten-Regel ``* deny`` (keine Regeln
        erfinden, identisch zum bisherigen Verhalten).
        """
        changed = self.render(V2_WITHOUT_SUBAGENT_AGENT, {"permission": "lesen"})

        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("lesen"))

    def test_file_without_permission_block_gets_template_default_deny(self):
        """Charakterisierung: Datei ohne Rechteblock erhält Vorlagen-Standard.

        Vorher: Frontmatter ohne ``permission``/``permissions``. Aktion:
        Vorlage ``voll``. Erwartet: neuer v2-Block mit Subagenten-Sperre.
        """
        changed = self.render(NO_BLOCK_AGENT, {"permission": "voll"})

        self.assertFalse(has_top_level_key(changed, "permission"))
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))

    def test_v1_task_deny_stays_denied_under_preset(self):
        """Guard: eine bestehende Sperre darf nicht in eine Freigabe kippen.

        Vorher: v1 ``task: deny``. Aktion: Vorlage ``voll``. Erwartet:
        Subagenten bleiben gesperrt (genau ``* deny``).
        """
        changed = self.render(V1_TASK_DENY_AGENT, {"permission": "voll"})

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])

    def test_v1_without_task_key_gets_template_default_deny(self):
        """Guard: ohne task-Eintrag wird keine Subagenten-Freigabe erfunden.

        Vorher: v1-Block ohne ``task`` (Standard ohne Eintrag = gesperrt).
        Aktion: Vorlage ``lesen``. Erwartet: Vorlagen-Standard ``* deny``.
        """
        changed = self.render(V1_NO_TASK_AGENT, {"permission": "lesen"})

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])

    def test_empty_permission_value_leaves_the_block_untouched(self):
        """Charakterisierung: ohne gewählte Vorlage bleibt der Block unverändert.

        Vorher: v1 ``task: allow``. Aktion: ``values`` mit ``permission: ""``
        und geänderter Beschreibung. Erwartet: v1-Block bleibt v1-Block,
        Subagenten bleiben erlaubt; nur die Beschreibung ändert sich.
        """
        changed = self.render(
            V1_TASK_ALLOW_AGENT,
            {"permission": "", "description": "Neu beschrieben"},
        )

        self.assertIn("description: Neu beschrieben", changed)
        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(subagent_parse_permissions(changed))
        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )


# --------------------------------------------------------------------------
# 2. Serverreihenfolge: erst Felder/Vorlage, dann ausdrückliche Auswahl
# --------------------------------------------------------------------------


class ExplicitSelectionTest(SubagentPermissionFixture):
    """Die ausdrückliche Subagenten-Auswahl gewinnt gegen die Vorlage.

    Die Serverreihenfolge ist ``agent_render_fields`` (Vorlage) und danach
    ``agent_render_task`` (Auswahl aus der Oberfläche); diese Reihenfolge wird
    hier nachgestellt.
    """

    def test_explicit_allowed_list_overrides_preset(self):
        """Vorlage ``voll`` + ``task_allowed=["tester"]`` ergibt nur tester.

        Vorher: v1 ``task: allow`` (würde nach der Korrektur „alle“ ergeben).
        Aktion: Vorlage anwenden, dann Auswahl ``["tester"]``.
        Erwartet: Policy ``custom`` mit genau ``tester`` — die ausdrückliche
        Auswahl gewinnt.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_ALLOW_AGENT, {"permission": "voll"}
        )

        changed = self.cli.agent_render_task("global", text, ["tester"])

        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["tester"]},
        )
        self.assertEqual(
            rule_pairs(changed, "subagent"),
            [("*", "deny"), ("tester", "allow")],
        )
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))

    def test_explicit_allow_all_overrides_denied_preset(self):
        """Vorlage ``lesen`` + ``task_all=true`` ergibt „alle“.

        Vorher: v1 ``task: deny``. Aktion: Vorlage anwenden, dann
        ``allow_all=True``. Erwartet: genau ``* allow``.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_DENY_AGENT, {"permission": "lesen"}
        )

        changed = self.cli.agent_render_task("global", text, [], allow_all=True)

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "allow")])

    def test_explicit_empty_selection_denies_even_when_input_allowed(self):
        """Vorlage ``voll`` + leere Auswahl („keine“) ergibt gesperrt.

        Vorher: v1 ``task: allow``. Aktion: Vorlage anwenden, dann
        ``agent_render_task(..., [])``. Erwartet: genau ``* deny``.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_ALLOW_AGENT, {"permission": "voll"}
        )

        changed = self.cli.agent_render_task("global", text, [])

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])


# --------------------------------------------------------------------------
# 3. Unverändert: Neuanlage und Auswahl ohne Vorlage
# --------------------------------------------------------------------------


class TemplateRegressionTest(SubagentPermissionFixture):
    """Charakterisierung von ``agent_template`` und ``agent_render_task``.

    Diese Fälle sichern das in Punkt 4 des Arbeitspakets verlangte
    unveränderte Verhalten ab; sie sind am unveränderten Stand grün.
    """

    def test_agent_template_still_denies_subagents_by_default(self):
        """Neuanlage erzeugt weiterhin den Vorlagen-Standard ``subagent * deny``.

        Vorher: keine Datei. Aktion: ``agent_template`` für alle Vorlagen
        (global und Projekt mit Schreibverzeichnissen). Erwartet: Policy
        ``none`` und genau eine Subagenten-Regel ``* deny``.
        """
        for preset in ("voll", "lesen", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Neu", perm=preset)
                self.assertEqual(
                    self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
                )
                self.assertEqual(rule_pairs(text, "subagent"), [("*", "deny")])

        dirs = self.cli.write_dirs("proj")
        project_text = self.cli.agent_template(
            "Neu", perm="voll", write_dirs=dirs
        )
        self.assertEqual(
            self.cli.agent_task_policy(project_text),
            {"mode": "none", "allowed": []},
        )

    def test_agent_render_task_without_preset_keeps_v1_syntax(self):
        """v1-individueller Block behält ohne Vorlage die v1-task-Syntax.

        Vorher: v1-Datei mit individueller task-Map. Aktion:
        ``agent_render_task(..., ["x"])`` ohne Vorlage. Erwartet: weiterhin
        ``permission:``-Block mit ``task``-Einträgen (keine v2-Umstellung).
        """
        changed = self.cli.agent_render_task(
            "global", V1_TASK_CUSTOM_AGENT, ["x"]
        )

        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(subagent_parse_permissions(changed))
        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["x"]},
        )
        self.cli.agent_validate(changed)

    def test_agent_render_task_without_preset_replaces_only_subagent_rules_in_v2(self):
        """v2-Block: Auswahl ohne Vorlage ersetzt nur die Subagenten-Regeln.

        Vorher: v2-Datei mit Subagenten-Regeln. Aktion: ``allow_all=True``
        ohne Vorlage. Erwartet: ``* allow``; alle anderen Regeln unverändert.
        """
        before = subagent_parse_permissions(V2_SUBAGENT_CUSTOM_AGENT)
        non_subagent_before = non_subagent_rules(V2_SUBAGENT_CUSTOM_AGENT)

        changed = self.cli.agent_render_task(
            "global", V2_SUBAGENT_CUSTOM_AGENT, [], allow_all=True
        )

        self.assertIsNotNone(before)
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "allow")])
        self.assertEqual(non_subagent_rules(changed), non_subagent_before)
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# 4. End-to-end über die Web-API mit der Payload-Sequenz der klassischen UI
# --------------------------------------------------------------------------

FAKE_OPENCODE_b7 = """#!/usr/bin/env bash
case "$1" in
  --version) printf 'opencode 2.1.4\\n' ;;
  models)
    printf 'opencode/test-modell\\nopencode/orchestrator-modell\\n'
    ;;
esac
exit 0
"""

HELPER_AGENT = subagent_v2_agent(
    [("read", "*", "allow"), ("subagent", "*", "deny")],
    description="Hilfsagent",
)


class SubagentPermissionApiTest(unittest.TestCase):
    """``/api/agent`` (save/render) und ``/api/agent_template`` über HTTP.

    Der Server läuft als Subprozess mit isoliertem VIBE/HOME und einer
    opencode-Attrappe. Die Payloads der Speicher- und Vorschaufälle
    entsprechen der klassischen UI (``bin/web/app.js``): ``save`` sendet nur
    geänderte strukturierte Felder plus Prüfsumme, ``render`` sendet alle
    Formularwerte.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.agents / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "opencode"
        fake.write_text(FAKE_OPENCODE_b7, encoding="utf-8")
        fake.chmod(0o755)
        cls.port = free_port()
        env = isolated_env_b7(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_b7)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        # Nur zum Auswerten von ``agent_task_policy``; der Server läuft separat.
        cls.cli = load_cli_b7(cls.root, cls.home)
        cls.cli._AGENT_VERSION = None

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

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", "127.0.0.1:%d" % self.port)
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def write_agent(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def load_agent(self, name):
        status, body = self.request(
            "/api/agent?scope=global&name=" + name
        )
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def render(self, name, text, values):
        return self.request(
            "/api/agent",
            {
                "action": "render",
                "scope": "global",
                "name": name,
                "text": text,
                "values": values,
            },
        )

    def save(self, name, text, values, expected=None, **extra):
        payload = {
            "action": "save",
            "scope": "global",
            "name": name,
            "text": text,
            "create": False,
            "expected": expected,
            "values": values,
        }
        payload.update(extra)
        return self.request("/api/agent", payload)

    def test_save_with_preset_and_without_task_fields_keeps_v1_task_allow(self):
        """Gemeldeter Fall end-to-end: save ``voll`` ohne task-Felder.

        Vorher: globale v1-Datei ``orchestrator`` mit ``task: allow``.
        Aktion: klassische UI-Sequenz — GET (Prüfsumme), dann POST
        ``action=save`` mit ``values:{permission:'voll'}`` und ohne
        ``task_all``/``task_allowed``.
        Erwartet: HTTP 200, Datei im v2-Format, Subagenten weiterhin erlaubt.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name, V1_TASK_ALLOW_AGENT, {"permission": "voll"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertFalse(has_top_level_key(saved, "permission"), saved)
        self.assertEqual(
            self.cli.agent_task_policy(saved), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(saved, "subagent"))
        self.assertEqual(
            non_subagent_rules(saved), preset_non_subagent("voll")
        )
        self.assertIn("Bestehender Prompt.", saved)
        self.assertEqual(json.loads(body)["text"], saved)

    def test_render_with_full_ui_form_values_keeps_v1_task_allow(self):
        """„In Rohtext übernehmen“ (render) mit allen Formularwerten.

        Vorher: v1-Datei mit ``task: allow``. Aktion: POST ``action=render``
        mit derselben Werte-Menge wie ``app.js`` (Beschreibung, Modus,
        Modell, Temperatur, Schritte, Rechte-Vorlage ``voll``, Prompt).
        Erwartet: Vorschau enthält Subagenten-Freigabe; die Datei bleibt
        unverändert (render schreibt nie).
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        values = {
            "description": "Orchestrator mit erlaubten Subagenten",
            "mode": "primary",
            "model": "opencode/orchestrator-modell",
            "temperature": "",
            "steps": "",
            "permission": "voll",
            "prompt": "Bestehender Prompt.",
        }

        status, body = self.render(name, V1_TASK_ALLOW_AGENT, values)

        self.assertEqual(status, 200, body)
        preview = json.loads(body)["text"]
        self.assertEqual(
            self.cli.agent_task_policy(preview), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(preview, "subagent"))
        self.assertEqual(
            non_subagent_rules(preview), preset_non_subagent("voll")
        )
        self.assertEqual(path.read_text(encoding="utf-8"), V1_TASK_ALLOW_AGENT)

    def test_save_with_preset_keeps_v1_custom_task_map(self):
        """Save mit Vorlage ``lesen`` erhält die individuellen Freigaben.

        Vorher: v1-Datei mit ``task``-Map (deny + ``vibe-coder``/``tester``).
        Aktion: GET-Prüfsumme, POST save mit ``values:{permission:'lesen'}``.
        Erwartet: HTTP 200, deny-Grundregel plus sortierte Freigaben.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_CUSTOM_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name, V1_TASK_CUSTOM_AGENT, {"permission": "lesen"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            rule_pairs(saved, "subagent"),
            [("*", "deny"), ("tester", "allow"), ("vibe-coder", "allow")],
        )
        self.assertEqual(non_subagent_rules(saved), preset_non_subagent("lesen"))

    def test_save_with_preset_keeps_v2_subagent_rules(self):
        """Save mit Vorlage ``voll`` erhält vorhandene v2-Subagenten-Regeln.

        Vorher: v2-Datei mit deny + zwei Freigaben.
        Aktion: GET-Prüfsumme, POST save mit ``values:{permission:'voll'}``.
        Erwartet: Subagenten-Regeln unverändert; Nicht-subagent-Regeln der
        Vorlage ``voll``.
        """
        name = "orchestrator"
        path = self.write_agent(name, V2_SUBAGENT_CUSTOM_AGENT)
        digest = self.load_agent(name)["digest"]
        before = rule_pairs(V2_SUBAGENT_CUSTOM_AGENT, "subagent")

        status, body = self.save(
            name, V2_SUBAGENT_CUSTOM_AGENT, {"permission": "voll"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(rule_pairs(saved, "subagent"), before)
        self.assertEqual(non_subagent_rules(saved), preset_non_subagent("voll"))

    def test_save_with_explicit_task_all_wins_over_preset(self):
        """Charakterisierung: ``task_all=true`` im selben Request gewinnt.

        Vorher: v1-Datei mit ``task: deny``. Aktion: save mit Vorlage
        ``lesen`` und ``task_all=true``. Erwartet: Subagenten erlaubt.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_DENY_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name,
            V1_TASK_DENY_AGENT,
            {"permission": "lesen"},
            expected=digest,
            task_all=True,
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            self.cli.agent_task_policy(saved), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(saved, "subagent"))

    def test_save_with_explicit_allowed_list_wins_over_preset(self):
        """Charakterisierung: ``task_allowed`` im selben Request gewinnt.

        Vorher: v1-Datei mit ``task: allow``; global existiert der
        Subagent ``helper``. Aktion: save mit Vorlage ``voll`` und
        ``task_allowed: ["helper"]``. Erwartet: Policy ``custom`` mit
        ``helper`` — nicht die geerbte „alle“-Freigabe.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name,
            V1_TASK_ALLOW_AGENT,
            {"permission": "voll"},
            expected=digest,
            task_allowed=["helper"],
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            rule_pairs(saved, "subagent"),
            [("*", "deny"), ("helper", "allow")],
        )

    def test_template_api_still_denies_subagents(self):
        """Charakterisierung: ``/api/agent_template`` erzeugt die Vorlagen-Sperre.

        Vorher: keine Datei. Aktion: POST ``/api/agent_template`` mit
        ``perm:'voll'``. Erwartet: erzeugter Text sperrt Subagenten
        (``* deny``) — Neuanlage bleibt unverändert.
        """
        status, body = self.request(
            "/api/agent_template",
            {"scope": "global", "description": "API-Agent", "perm": "voll"},
        )

        self.assertEqual(status, 200, body)
        text = json.loads(body)["message"]
        self.assertEqual(rule_pairs(text, "subagent"), [("*", "deny")])


# ===========================================================================
# Subagenten-Parallelisierung: Selbstaufruf eines Agenten
# ===========================================================================

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

CLI_f32 = BIN / "vibe"
WEB_f32 = BIN / "vibe-web.py"


# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV_f32 = (
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
    "AGENT",
)


def isolated_env_f32(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_f32:
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli_f32(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_f32}
    for key in ISOLATED_ENV_f32:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_f32(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f32_under_test", str(CLI_f32)
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


class F32Fixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.other = self.make_project("other")
        self.cli = load_cli_f32(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        return project

    def write_global(self, name, text=AGENT_BASE):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name="lokal", text=AGENT_BASE):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def write_vibe(self, name="vibe-agent", text=VIBE_AGENT):
        path = self.write_global(name, text)
        roles = dict(self.cli.profiles_load().get("rollen", {}))
        roles[name] = "vibe"
        self.set_roles(roles)
        return path


class SelfSpawnAllowedTest(F32Fixture):
    """AK1: Ein gewöhnlicher Subagent darf sich selbst aufrufen."""

    def test_self_spawn_for_regular_subagent_is_allowed_rendered_and_read_back(self):
        # Vorbedingung: globaler Agent 'tester', mode subagent, ohne Vibe-Rolle.
        # Aktion: Selbstaufruf validieren und in den task-Block schreiben.
        # Erwartung: zulässig, der Eigenname steht als allow im Block und wird
        # von der Politik zurückgelesen.
        self.write_global("tester", task_agent([], mode="subagent"))

        allowed = self.cli.agent_validate_hierarchy("tester", ["tester"])

        self.assertEqual(allowed, ["tester"])
        rendered = self.cli.agent_render_task(
            "global", task_agent([], mode="subagent"), ["tester"]
        )
        self.assertIn('"*": deny', rendered)
        self.assertIn("tester: allow", rendered)
        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])
        # Der gerenderte Agent bleibt gültig und verliert keine Felder.
        self.cli.agent_validate(rendered)
        self.assertIn("mode: subagent", rendered)

    def test_new_agent_file_may_enable_self_spawn_via_own_text(self):
        # Vorbedingung: Die Datei 'neu' existiert noch nicht; der Editor
        # übergibt den Entwurf als own_text.
        # Aktion: Selbstaufruf validieren, schreiben und erneut prüfen.
        # Erwartung: zulässig, weil der Entwurf mode subagent ist.
        self.assertFalse((self.agents / "neu.md").exists())
        draft = task_agent([], mode="subagent")

        allowed = self.cli.agent_validate_hierarchy(
            "neu", ["neu"], own_text=draft
        )

        self.assertEqual(allowed, ["neu"])
        rendered = self.cli.agent_render_task("global", draft, ["neu"])
        self.cli.agent_write("global", "neu", rendered, create=True)
        self.assertTrue((self.agents / "neu.md").exists())
        self.assertEqual(
            self.cli.agent_validate_hierarchy("neu", ["neu"]), ["neu"]
        )
        self.assertEqual(
            self.cli.agent_task_policy(
                (self.agents / "neu.md").read_text(encoding="utf-8")
            )["allowed"],
            ["neu"],
        )

    def test_missing_own_text_and_missing_file_is_reported_as_unknown(self):
        # Vorbedingung: weder Datei noch Entwurf vorhanden.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: klare Meldung 'Unbekannter ... Subagent' statt einer
        # Selbstaufruf-Meldung.
        self.assertFalse((self.agents / "neu.md").exists())

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("neu", ["neu"])

        self.assertIn("Unbekannter oder nicht systemweiter Subagent: neu",
                      str(caught.exception))


class VibeSelfSpawnRejectedTest(F32Fixture):
    """AK2: Der Vibe-Agent darf keine Subagenten seines eigenen Typs aufrufen."""

    def test_default_vibe_agent_cannot_spawn_itself(self):
        # Vorbedingung: 'vibe-agent' trägt die Rolle vibe (Default-Auflösung).
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit der F32-Meldung zum Vibe-Agenten.
        self.write_vibe("vibe-agent", VIBE_AGENT)

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("vibe-agent", ["vibe-agent"])

        message = str(caught.exception)
        self.assertIn("Vibe-Agent", message)
        self.assertIn("eigenen Typs", message)

    def test_vibe_agent_is_rejected_even_with_subagent_mode(self):
        # Vorbedingung: Der Vibe-Agent hat ausdrücklich mode subagent.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Die Vibe-Rolle allein verbietet den Selbstaufruf.
        self.write_vibe("cap", task_agent([], mode="subagent"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("cap", ["cap"])

        self.assertIn("eigenen Typs", str(caught.exception))

    def test_explicit_vibe_agent_parameter_is_honoured(self):
        # Vorbedingung: keine vibe-Rolle in profiles.json; der Aufrufer nennt
        # 'cap' ausdrücklich als Vibe-Agent.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit der Vibe-Meldung.
        self.write_global("cap", task_agent([], mode="subagent"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("cap", ["cap"], vibe_agent="cap")

        self.assertIn("eigenen Typs", str(caught.exception))

    def test_empty_vibe_agent_parameter_disables_the_vibe_gate(self):
        # Vorbedingung: 'vibe-agent' trägt die Rolle vibe.
        # Aktion: vibe_agent="" (kein Vibe-Agent) und Selbstaufruf validieren.
        # Erwartung: zulässig; die Testschnittstelle kann die Vibe-Prüfung
        # bewusst abschalten.
        self.write_vibe("vibe-agent", task_agent([], mode="subagent"))

        allowed = self.cli.agent_validate_hierarchy(
            "vibe-agent", ["vibe-agent"], vibe_agent=""
        )

        self.assertEqual(allowed, ["vibe-agent"])


class SelfSpawnModeTest(F32Fixture):
    """AK4: Der eigene Typ ist nur ab mode subagent/all aufrufbar."""

    def test_primary_own_text_rejects_self_spawn(self):
        # Vorbedingung: Entwurf mit mode primary, Datei existiert nicht.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit 'kein Subagent (mode primary)'.
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy(
                "neu", ["neu"], own_text=task_agent([], mode="primary")
            )

        message = str(caught.exception)
        self.assertIn("kein Subagent", message)
        self.assertIn("mode primary", message)

    def test_all_and_missing_mode_from_own_text_allow_self_spawn(self):
        # Vorbedingung: Entwürfe mit mode all bzw. leerem mode (nicht gesetzt).
        # Aktion: Selbstaufruf validieren.
        # Erwartung: beide zulässig — ein leerer mode zählt wie all,
        # konsistent zur Fremdagenten-Regel.
        for mode in ("all", ""):
            with self.subTest(mode=mode):
                allowed = self.cli.agent_validate_hierarchy(
                    "neu", ["neu"], own_text=task_agent([], mode=mode)
                )
                self.assertEqual(allowed, ["neu"])

    def test_existing_primary_agent_rejects_self_spawn(self):
        # Vorbedingung: globale Datei 'prim' mit mode primary, kein own_text.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit 'kein Subagent (mode primary)'.
        self.write_global("prim", task_agent([], mode="primary"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("prim", ["prim"])

        self.assertIn("kein Subagent", str(caught.exception))
        self.assertIn("mode primary", str(caught.exception))


class HierarchyCycleTest(F32Fixture):
    """Zyklusregeln: Selbstkanten sind kein Zyklus, Rückkanten bleiben verboten."""

    def test_two_agent_cycle_is_still_rejected(self):
        # Vorbedingung: a ruft b, b ruft a.
        # Aktion: a→b validieren.
        # Erwartung: Zyklusfehler (unveränderte Regel, grüner Anker).
        self.write_global("a", task_agent(["b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["b"])

        self.assertIn("Zyklus", str(caught.exception))

    def test_self_edge_alone_is_not_a_cycle(self):
        # Vorbedingung: a erlaubt sich selbst; b erlaubt a.
        # Aktion: a→a und b→a validieren.
        # Erwartung: beides zulässig; eine Selbstkante ist kein Zyklus.
        self.write_global("a", task_agent(["a"]))

        self.assertEqual(
            self.cli.agent_validate_hierarchy("a", ["a"]), ["a"]
        )

        self.write_global("b", task_agent(["a"]))
        self.assertEqual(
            self.cli.agent_validate_hierarchy("b", ["a"]), ["a"]
        )

    def test_self_and_foreign_without_back_cycle_are_allowed(self):
        # Vorbedingung: a und b sind globale Subagenten ohne Rückkante.
        # Aktion: a erlaubt [a, b].
        # Erwartung: zulässig; der Selbstaufruf blockiert den Fremdaufruf nicht.
        self.write_global("a", task_agent([]))
        self.write_global("b", task_agent([]))

        allowed = self.cli.agent_validate_hierarchy("a", ["a", "b"])

        self.assertEqual(allowed, ["a", "b"])

    def test_self_edge_does_not_hide_a_real_cycle(self):
        # Vorbedingung: a erlaubt [a, b], b ruft a zurück.
        # Aktion: a erlaubt [a, b] validieren.
        # Erwartung: echter Zyklus wird trotz Selbstkante erkannt.
        self.write_global("a", task_agent(["a", "b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["a", "b"])

        self.assertIn("Zyklus", str(caught.exception))


class ForeignAgentRulesTest(F32Fixture):
    """AK6: Regeln für fremde Agenten bleiben unverändert (grüne Anker)."""

    def test_unknown_project_local_and_primary_are_rejected(self):
        # Vorbedingung: globaler Subagent a, globaler primary, projektlokaler
        # Agent.
        # Aktion/Erwartung: fremde Agenten werden weiterhin abgelehnt.
        self.write_global("a", task_agent([]))
        self.write_global("primary", task_agent([], mode="primary"))
        self.write_project_agent(self.project, "lokal", task_agent([]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["primary"])
        self.assertIn("kein Subagent (mode primary)", str(caught.exception))
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["lokal"])

    def test_global_subagent_and_all_modes_remain_allowed(self):
        # Vorbedingung: globale Agenten mit mode subagent und all.
        # Aktion/Erwartung: beide bleiben aufrufbar.
        self.write_global("a", task_agent([]))
        self.write_global("unter", task_agent([], mode="subagent"))
        self.write_global("alle", task_agent([], mode="all"))

        self.assertEqual(
            self.cli.agent_validate_hierarchy("a", ["unter", "alle"]),
            ["alle", "unter"],
        )


class SelfSpawnTemplateTest(F32Fixture):
    """AK3: Eine neue Agentendatei erhält keine Selbstfreigabe (grüner Anker)."""

    def test_template_has_no_self_release_and_policy_is_none(self):
        # Vorbedingung: frische Vorlage. Je nach Rechtevorlage enthält sie
        # 'task: deny' oder gar keinen task-Eintrag — beides ist gesperrt.
        # Aktion: Vorlage rendern und Politik lesen.
        # Erwartung: mode none, kein Selbstaufruf als Standard.
        text = self.cli.agent_template(
            "Neuer Agent", model="opencode/test-modell", prompt="Aufgabe"
        )

        self.assertEqual(
            self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
        )
        self.assertNotIn("task: allow", text)
        self.cli.agent_validate(text)


class AgentSelfSpawnApiTest(unittest.TestCase):
    """AK2/AK6/Persistenz über die echte Web-API (HTTP 400, Datei unverändert)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        # Der Server ruft beim Speichern ``opencode --version`` und
        # ``opencode models`` auf. Beide werden hier durch ein schnelles
        # Ersatzprogramm beantwortet; es findet kein echter Modellaufruf statt.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env_f32(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_f32)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        cls.cli = load_cli_f32(cls.root, cls.home)

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
        # Jeder Test startet mit demselben Ausgangsstand; Fehlerfälle dürfen
        # keine Spuren im nächsten Test hinterlassen.
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (self.agents / "helper.md").write_text(task_agent([]), encoding="utf-8")
        (self.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        leftover = self.agents / "neu.md"
        if leftover.exists():
            leftover.unlink()
        self.write_profiles({"vibe-agent": "vibe"})

    def write_profiles(self, roles):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": dict(roles)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self, name="tester"):
        status, body = self.request(f"/api/agent?scope=global&name={name}")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def error_message(self, body):
        data = json.loads(body)
        return (data.get("error") or {}).get("message") or data.get("message") or ""

    def assert_rejected_with(self, status, body, expected, timeout_message=None):
        self.assertEqual(status, 400, body)
        self.assertIn(expected, self.error_message(body), timeout_message or body)

    def test_regular_agent_self_spawn_is_saved_and_plain_save_keeps_the_block(self):
        # Vorbedingung: 'tester' ist gewöhnlicher Subagent.
        # Aktion 1: Speichern mit task_allowed=['tester'].
        # Erwartung 1: 200, Datei enthält 'tester: allow' unter task.
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "expected": self.digest(),
            },
        )

        self.assertEqual(status, 200, body)
        path = self.agents / "tester.md"
        saved = path.read_text(encoding="utf-8")
        self.assertIn('"*": deny', saved)
        self.assertIn("tester: allow", saved)
        policy = self.cli.agent_task_policy(saved)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])

        # Aktion 2: Erneut speichern, ohne task_allowed (unveränderter Rohtext).
        # Erwartung 2: Der task-Block bleibt unverändert erhalten.
        status, body = self.request(
            "/api/agent?scope=global&name=tester"
        )
        self.assertEqual(status, 200, body)
        loaded = json.loads(body)
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": loaded["text"],
                "expected": loaded["digest"],
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(saved, path.read_text(encoding="utf-8"))
        policy = self.cli.agent_task_policy(path.read_text(encoding="utf-8"))
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])

    def test_new_agent_can_enable_self_spawn_in_the_same_save(self):
        # Vorbedingung: Die Datei 'neu' existiert noch nicht; der Editor
        # speichert Entwurf und task_allowed in einer Anfrage.
        # Aktion: Neuanlage mit Selbstaufruf.
        # Erwartung: 200, Datei enthält den Eigennamen als allow. Der Server
        # muss den Entwurf als own_text an die Hierarchieprüfung geben.
        self.assertFalse((self.agents / "neu.md").exists())

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "neu",
                "text": task_agent([], mode="subagent"),
                "task_allowed": ["neu"],
                "create": True,
            },
        )

        self.assertEqual(status, 200, body)
        saved = (self.agents / "neu.md").read_text(encoding="utf-8")
        self.assertIn("neu: allow", saved)
        self.assertEqual(self.cli.agent_task_policy(saved)["allowed"], ["neu"])

    def test_current_vibe_agent_cannot_self_spawn(self):
        # Vorbedingung: 'vibe-agent' ist der aktuelle Vibe-Agent.
        # Aktion: task_allowed=['vibe-agent'].
        # Erwartung: 400 mit F32-Meldung; Agentendatei unverändert.
        path = self.agents / "vibe-agent.md"
        before = path.read_text(encoding="utf-8")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "vibe-agent",
                "text": VIBE_AGENT,
                "task_allowed": ["vibe-agent"],
                "expected": self.digest("vibe-agent"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertIn("Vibe-Agent", self.error_message(body))
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_agent_becoming_vibe_in_the_same_request_cannot_self_spawn(self):
        # Vorbedingung: 'tester' ist kein Vibe-Agent.
        # Aktion: Speichern mit role='vibe' und Selbstaufruf.
        # Erwartung: 400, weil 'tester' durch dieselbe Anfrage Vibe-Agent wird.
        path = self.agents / "tester.md"
        before = path.read_text(encoding="utf-8")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_explicit_role_removal_allows_self_spawn_when_another_vibe_exists(self):
        # Vorbedingung: profiles.json führt 'tester' UND 'vibe-agent' als vibe.
        # Aktion: 'tester' speichern, Rolle ausdrücklich entfernen (role='')
        # und Selbstaufruf erlauben.
        # Erwartung: 200; der andere Agent bleibt Vibe-Agent, der Selbstaufruf
        # wird gespeichert.
        self.write_profiles({"tester": "vibe", "vibe-agent": "vibe"})

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "role": "",
                "expected": self.digest("tester"),
            },
        )

        self.assertEqual(status, 200, body)
        policy = self.cli.agent_task_policy(
            (self.agents / "tester.md").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["allowed"], ["tester"])
        roles = json.loads(
            (self.state / "profiles.json").read_text(encoding="utf-8")
        )["rollen"]
        self.assertNotIn("tester", roles)
        self.assertEqual(roles.get("vibe-agent"), "vibe")

    def test_task_all_stays_a_plain_allow_without_hierarchy_check(self):
        # Vorbedingung: 'helper' ist gewöhnlicher Subagent.
        # Aktion: Speichern mit task_all=true.
        # Erwartung: 200 und 'task: allow' (unverändert, grüner Anker).
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "helper",
                "text": task_agent([]),
                "task_all": True,
                "expected": self.digest("helper"),
            },
        )

        self.assertEqual(status, 200, body)
        saved = (self.agents / "helper.md").read_text(encoding="utf-8")
        self.assertIn("task: allow", saved)
        self.assertEqual(self.cli.agent_task_policy(saved)["mode"], "all")

    def test_task_allowed_for_project_scope_is_still_rejected(self):
        # Vorbedingung: Projekt 'proj' existiert, scope=proj.
        # Aktion: Speichern mit task_allowed.
        # Erwartung: 400, Subagenten-Rechte gelten nur systemweit (grüner Anker).
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "proj",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": [],
            },
        )

        self.assert_rejected_with(
            status, body, "Subagenten-Rechte gelten nur für systemweite Agenten."
        )
        self.assertFalse(
            (self.project / ".opencode" / "agents" / "tester.md").exists()
        )


class VibeInvariantApiTest(unittest.TestCase):
    """F32 Runde 2: Die Vibe-Sperre gilt bei *jeder* Rollenzuweisung.

    Fachlicher Hintergrund (Review Runde 1, High 1): Die Sperre aus Runde 1
    lief nur im ``task_allowed``-Zweig von ``/api/agent``. Zwei reale UI-Wege
    umgingen sie deshalb:

    * Editor-Speichern, das ausschließlich die Rolle auf ``vibe`` setzt,
    * das Rollen-Dropdown der Agentenliste (``action:'role'``).

    Der Vertrag lautet: Ein Agent mit Selbstfreigabe (``permission.task``
    erlaubt den eigenen Namen) darf niemals Vibe-Agent werden — unabhängig
    davon, ob ``task_allowed`` mitgesendet wird. Ein Agent ohne Selbstfreigabe
    darf die Rolle weiterhin erhalten.

    Der Testaufbau entspricht ``AgentSelfSpawnApiTest`` (eigener Server im
    Temp-Verzeichnis, ``opencode`` als Ersatzprogramm, kein Modellaufruf, kein
    Netzzugriff außer Loopback). Die Klasse ist bewusst eigenständig, damit die
    Runde-1-Fälle unverändert bleiben.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        # Ersatzprogramm wie in AgentSelfSpawnApiTest: beantwortet nur
        # Versions- und Modellabfragen, führt keinen Modellaufruf aus.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env_f32(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_f32)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        cls.cli = load_cli_f32(cls.root, cls.home)

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
        # Gleicher Ausgangsstand für jeden Fall: 'vibe-agent' ist der einzige
        # Vibe-Agent, 'tester' und 'helper' sind gewöhnliche Subagenten.
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (self.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        (self.agents / "helper.md").write_text(task_agent([]), encoding="utf-8")
        # 'neu' und 'kaputt' entstehen nur in einzelnen Fällen; damit die
        # Klasse wiederholbar bleibt, wird ein Rest aus dem Vorlauf entfernt.
        for leftover_name in ("neu.md", "kaputt.md"):
            leftover = self.agents / leftover_name
            if leftover.exists():
                leftover.unlink()
        self.write_profiles({"vibe-agent": "vibe"})

    # ------------------------------------------------------------------ Helfer
    def write_profiles(self, roles):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": dict(roles)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def roles(self):
        return json.loads(
            (self.state / "profiles.json").read_text(encoding="utf-8")
        )["rollen"]

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self, name="tester"):
        status, body = self.request(f"/api/agent?scope=global&name={name}")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def error_message(self, body):
        data = json.loads(body)
        return (data.get("error") or {}).get("message") or data.get("message") or ""

    def assert_rejected_with(self, status, body, expected):
        self.assertEqual(status, 400, body)
        self.assertIn(expected, self.error_message(body), body)

    def global_agent_row(self, name):
        status, body = self.request("/api/agents")
        self.assertEqual(status, 200, body)
        rows = json.loads(body)["global_agents"]
        return next(row for row in rows if row["name"] == name)

    # --------------------------------------------------------------- Testfälle
    def test_role_only_save_rejects_vibe_for_agent_with_self_allow(self):
        # Vorbedingung: 'tester' erlaubt sich selbst als Subagenten; die Datei
        # enthält also eine Selbstfreigabe, 'tester' ist aber kein Vibe-Agent.
        # Aktion: Speichern wie im Editor, wenn nur die Rolle auf 'vibe'
        # gestellt wird — ohne task_allowed-Feld.
        # Erwartung: 400 mit der F32-Meldung; Agentendatei und profiles.json
        # bleiben unverändert, 'tester' wird kein Vibe-Agent.
        path = self.agents / "tester.md"
        text = task_agent(["tester"], mode="subagent")
        path.write_text(text, encoding="utf-8")
        before_roles = self.roles()

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": text,
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("tester"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")

    def test_raw_text_self_allow_for_the_current_vibe_agent_is_rejected(self):
        # Vorbedingung: 'vibe-agent' ist der aktuelle Vibe-Agent.
        # Aktion: Speichern des Rohtexts, der im task-Block
        # 'vibe-agent: allow' enthält (keine Rolle, kein task_allowed).
        # Erwartung: 400 mit der F32-Meldung; die Datei bleibt unverändert.
        path = self.agents / "vibe-agent.md"
        before = path.read_text(encoding="utf-8")
        text = task_agent(["vibe-agent"], mode="primary")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "vibe-agent",
                "text": text,
                "expected": self.digest("vibe-agent"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertIn("Vibe-Agent", self.error_message(body))
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_role_only_save_allows_vibe_without_self_allow(self):
        # Vorbedingung: 'tester' hat keine Selbstfreigabe (kein task-Eintrag).
        # Aktion: Speichern mit ausschließlich role='vibe', ohne task_allowed.
        # Erwartung: 200, die Rolle ist gesetzt und /api/agents meldet
        # 'tester' als Vibe-Agent. Grüner Anker: die Invariante blockiert nur
        # die Selbstfreigabe, nicht die Rollenzuweisung an sich.
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("tester"), "vibe")
        row = self.global_agent_row("tester")
        self.assertTrue(row["is_vibe"], row)
        self.assertEqual(row["role"], "vibe")

    def test_role_action_rejects_vibe_for_agent_with_self_allow(self):
        # Vorbedingung: 'tester' erlaubt sich selbst; 'vibe-agent' ist der
        # bisherige Vibe-Agent.
        # Aktion: Rollen-Dropdown der Agentenliste (action='role').
        # Erwartung: 400 mit der Meldung aus agent_role_set; profiles.json
        # bleibt unverändert, 'tester' bekommt keine vibe-Rolle und der
        # bisherige Vibe-Agent behält seine Rolle.
        text = task_agent(["tester"], mode="subagent")
        (self.agents / "tester.md").write_text(text, encoding="utf-8")
        before_roles = self.roles()

        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "tester",
                "role": "vibe",
            },
        )

        self.assert_rejected_with(
            status, body, "erlaubt bereits Subagenten seines eigenen Typs"
        )
        self.assertIn(
            "nicht der Vibe-Agent werden", self.error_message(body), body
        )
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("tester"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")

    def test_role_action_allows_vibe_after_self_release_removed(self):
        # Vorbedingung: 'tester' hat keine Selbstfreigabe mehr (task: deny).
        # Aktion: Rollen-Dropdown der Agentenliste auf 'vibe'.
        # Erwartung: 200; profiles.json führt 'tester' als Vibe-Agent und der
        # bisherige Vibe-Agent verliert die Rolle (Eindeutigkeitsregel).
        # Grüner Anker für das bestehende Verhalten ohne Selbstfreigabe.
        text = task_agent([], mode="subagent")
        (self.agents / "tester.md").write_text(text, encoding="utf-8")
        self.assertEqual(
            self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
        )

        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "tester",
                "role": "vibe",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("tester"), "vibe")
        self.assertNotEqual(self.roles().get("vibe-agent"), "vibe")

    def test_role_action_still_assigns_vibe_for_unreadable_frontmatter(self):
        # Vorbedingung: 'kaputt' hat keinen Frontmatter-Block und keine Rolle;
        # 'vibe-agent' ist der bisherige Vibe-Agent. Der Parser kann die Datei
        # nicht lesen — genau das ist der Fall, für den agent_role_set den
        # defensiven Fallback (policy mode 'none') hinterlegt hat.
        broken = self.agents / "kaputt.md"
        broken.write_text("Kein Frontmatter.\n", encoding="utf-8")
        self.assertNotIn("kaputt", self.roles())
        with self.assertRaises(ValueError):
            self.cli.agent_task_policy(broken.read_text(encoding="utf-8"))

        # Aktion 1: Rollen-Dropdown der Agentenliste für die defekte Datei.
        # Erwartung: 200; 'kaputt' trägt die Rolle 'vibe' und der bisherige
        # Vibe-Agent verliert sie (Eindeutigkeitsregel). Eine Selbstfreigabe
        # ist nicht nachweisbar, deshalb bleibt die Zuweisung möglich.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "vibe",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("kaputt"), "vibe")
        self.assertNotEqual(self.roles().get("vibe-agent"), "vibe")

        # Gegenprobe: dieselbe Datei mit lesbarem Frontmatter, das die
        # Selbstfreigabe 'kaputt: allow' enthält (mode subagent).
        text = task_agent(["kaputt"], mode="subagent")
        broken.write_text(text, encoding="utf-8")
        policy = self.cli.agent_task_policy(text)
        self.assertEqual(policy["mode"], "custom")
        self.assertIn("kaputt", policy["allowed"])

        # Rolle zurücksetzen: zuerst bekommt 'vibe-agent' die Rolle wieder
        # (sonst wäre 'kaputt' der letzte Vibe-Agent), dann wird 'kaputt'
        # ausdrücklich auf '' gesetzt.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "vibe-agent",
                "role": "vibe",
            },
        )
        self.assertEqual(status, 200, body)
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "",
            },
        )
        self.assertEqual(status, 200, body)
        self.assertNotIn("kaputt", self.roles())
        before_roles = self.roles()

        # Aktion 1 wiederholen. Erwartung: 400 mit der F32-Meldung; profiles
        # bleibt unverändert, 'kaputt' wird kein Vibe-Agent und der bisherige
        # Vibe-Agent behält seine Rolle. So unterscheidet sich der lesbare
        # vom unlesbaren Fall.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "vibe",
            },
        )

        self.assert_rejected_with(
            status, body, "erlaubt bereits Subagenten seines eigenen Typs"
        )
        self.assertIn(
            "nicht der Vibe-Agent werden", self.error_message(body), body
        )
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("kaputt"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")


# ===========================================================================
# Unit-Tests, Agenten-Backup ohne Versionshinweis
# ===========================================================================

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


AGENT_V1_f33 = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
---
Erster Prompt.
"""

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
            "vibe_f33_agent_backup_under_test", str(CLI))
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


class AgentBackupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        self.cli = load_cli_f33(self.root, self.home)
        self.cli._AGENT_VERSION = None
        # Kein Modelllisting: die Sicherung gehört nicht zur Modellprüfung.
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def global_path(self, name="tester"):
        return self.agents / (name + ".md")

    def project_path(self, name="tester"):
        return self.proj / ".opencode" / "agents" / (name + ".md")

    def write_global(self, name="tester", text=AGENT_V1_f33):
        path = self.global_path(name)
        path.write_text(text, encoding="utf-8")
        return path

    def write_project(self, name="tester", text=AGENT_V1_f33):
        path = self.project_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def backup_files(self, scope, name):
        directory = Path(self.cli.agent_backup_dir(scope))
        return sorted(directory.glob(name + "-*")) if directory.exists() else []


class AgentBackupFunctionTest(AgentBackupFixture):
    def test_backup_creates_a_copy_and_leaves_the_original_unchanged(self):
        """Vorbedingung: globale Agentendatei vorhanden.

        Aktion: ``agent_backup("global", "tester")``.
        Erwartung: Die Datei bleibt byte-identisch; im Sicherungsordner liegt
        eine Datei mit exakt demselben Inhalt.
        """
        path = self.write_global()
        before = path.read_bytes()

        self.cli.agent_backup("global", "tester")

        self.assertEqual(path.read_bytes(), before,
                         "Das Backup veränderte die Agentendatei")
        files = self.backup_files("global", "tester")
        self.assertEqual(1, len(files), "Es entstand keine Sicherung: "
                         + repr([item.name for item in files]))
        self.assertEqual(files[0].read_text(encoding="utf-8"), AGENT_V1_f33,
                         "Die Sicherung enthält nicht den Dateiinhalt")
        self.assertEqual(
            [item.name for item in files], self.cli.agent_backups("global", "tester"),
            "Die Sicherung wird nicht als Sicherung des Agenten gelistet")

    def test_repeated_backups_are_collision_free(self):
        """Vorbedingung: globale Agentendatei.

        Aktion: Zwei Sicherungen ohne Änderung dazwischen.
        Erwartung: Zwei verschiedene Sicherungsdateien mit gleichem Inhalt;
        keine überschreibt die andere.
        """
        path = self.write_global()
        self.cli.agent_backup("global", "tester")
        self.cli.agent_backup("global", "tester")

        files = self.backup_files("global", "tester")
        self.assertEqual(
            2, len({item.name for item in files}),
            "Zwei Sicherungen kollidieren im Namen: "
            + repr([item.name for item in files]))
        for item in files:
            self.assertEqual(item.read_text(encoding="utf-8"), AGENT_V1_f33)
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V1_f33)

    def test_project_agent_backup_lands_in_the_project_scope_folder(self):
        """Vorbedingung: Projektagent vorhanden.

        Aktion: ``agent_backup("proj", "tester")``.
        Erwartung: Die Sicherung liegt im Bereich ``proj``; der globale
        Sicherungsordner bleibt leer.
        """
        path = self.write_project()

        self.cli.agent_backup("proj", "tester")

        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V1_f33)
        project_files = self.backup_files("proj", "tester")
        self.assertEqual(1, len(project_files),
                         "Es entstand keine Sicherung im Projektbereich")
        self.assertEqual([], self.backup_files("global", "tester"),
                         "Die Projektsicherung landete im globalen Ordner")

    def test_unknown_agent_and_unsafe_names_are_rejected(self):
        """Vorbedingung: keine Datei für ``fehlt``.

        Erwartung: Unbekannte Agenten und Pfadanteile werfen ``ValueError``
        und legen keine Sicherung an.
        """
        for scope, name in (("global", "fehlt"), ("global", "../evil"),
                            ("proj", "a/b")):
            with self.subTest(scope=scope, name=name):
                with self.assertRaises(ValueError):
                    self.cli.agent_backup(scope, name)
        self.assertEqual([], self.backup_files("global", "fehlt"))
        self.assertEqual([], self.backup_files("global", "evil"))


class AgentBackupApiTest(unittest.TestCase):
    """POST /api/agent {action:"backup"} gegen ein echtes Server-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
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
        self.path = self.agents / "tester.md"
        self.path.write_text(AGENT_V1_f33, encoding="utf-8")
        backups = self.root / "_toolchain" / "agent-backups" / "global"
        if backups.exists():
            for item in backups.iterdir():
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

    def test_backup_answers_with_the_exact_message_and_keeps_the_file(self):
        """Vorbedingung: globale Agentendatei.

        Aktion: POST ``{action:"backup", scope:"global", name:"tester"}``.
        Erwartung: ``ok``, Meldung exakt „Sicherung angelegt“ ohne
        Versions-/Modellwarnung; Antwort enthält ``backups`` (eine Sicherung),
        ``text`` und ``digest``; die Datei bleibt unverändert.
        """
        before = self.path.read_bytes()
        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "tester"})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("Sicherung angelegt", payload.get("message"), payload)
        self.assertNotIn("nicht geprüft", payload.get("message", ""))
        self.assertNotIn("Hinweis:", payload.get("message", ""))
        self.assertEqual(1, len(payload.get("backups") or []), payload)
        self.assertEqual(AGENT_V1_f33, payload.get("text"), payload)
        self.assertTrue(payload.get("digest"), payload)
        self.assertEqual(self.path.read_bytes(), before,
                         "Das Backup veränderte die Agentendatei")
        stored = (self.root / "_toolchain" / "agent-backups" / "global"
                  / payload["backups"][0])
        self.assertTrue(stored.is_file(), "Die Sicherungsdatei fehlt: "
                        + str(stored))
        self.assertEqual(stored.read_text(encoding="utf-8"), AGENT_V1_f33)

    def test_unknown_agent_is_rejected_without_a_backup(self):
        """Vorbedingung: Agent ``tester`` vorhanden, ``fehlt`` nicht.

        Aktion: Erst eine gültige Sicherung, dann POST
        ``{action:"backup", name:"fehlt"}``.
        Erwartung: Die gültige Sicherung bestätigt die Aktion; der unbekannte
        Agent wird abgelehnt (``ok`` falsch, Status 400) und erhält keine
        Sicherung.
        """
        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "tester"})
        self.assertEqual(200, status, payload)
        self.assertEqual("Sicherung angelegt", payload.get("message"), payload)

        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "fehlt"})
        self.assertEqual(400, status, payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertTrue((payload.get("message") or "").strip(), payload)
        backups = self.root / "_toolchain" / "agent-backups" / "global"
        self.assertFalse(
            backups.exists() and any(backups.glob("fehlt-*")),
            "Für einen unbekannten Agenten entstand eine Sicherung")


if __name__ == "__main__":
    unittest.main()
