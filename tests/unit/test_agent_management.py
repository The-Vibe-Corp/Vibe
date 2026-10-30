"""Tests für die vollständige Agentenverwaltung (V-010).

Geprüft werden die fachlichen Regeln hinter CLI und Dashboard:

* ungültiges Frontmatter verändert keine vorhandene Datei,
* doppelte Namen und Projektüberschattung sind sichtbar,
* der tatsächlich wirksame Agent folgt der opencode-Priorität
  (Projektagent überschreibt gleichnamigen globalen Agenten),
* Namen mit Pfadanteilen werden abgelehnt,
* der strukturierte Editor erhält unbekannte Frontmatter-Felder,
* ungültige strukturierte Werte werden vor jedem Schreibvorgang abgelehnt,
* Sicherungen lassen sich wiederherstellen,
* es gibt keine fest eingebauten Kernagentennamen mehr.

Die Tests arbeiten auf echten Dateien in einem temporären Arbeitsbereich.
opencode wird nur für die Versionsprüfung aufgerufen; es findet kein
Modellaufruf statt.
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
        self.assertIn("permission:\n  read: allow", changed)
        self.assertIn("  edit: deny", changed)
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

        self.assertIn("permission:\n  read: allow", changed)
        self.assertIn("  edit: deny", changed)
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
        self.assertIn("  read: allow", preview)
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            AGENT_V1,
            "Die Vorschau darf die Datei nicht verändern",
        )

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


if __name__ == "__main__":
    unittest.main()
