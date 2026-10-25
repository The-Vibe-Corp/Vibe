"""Tests für die dynamischen Schreibrechte je Projekt (F3).

Jedes Projekt besitzt eine Liste erlaubter Verzeichnisse, in denen Agenten
Dateien ändern dürfen. Voreingestellt sind ``/tmp/opencode`` und das
Projektverzeichnis. Die Liste ist über CLI und Web-API änderbar und wird in
die ``edit``-Rechte neuer bzw. ausdrücklich aktualisierter Projektagenten
übernommen.
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

AGENT_TEMPLATE = """---
description: Projektagent für Tests
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

Du änderst ausschließlich Dateien im Projekt.
"""

AGENT_WITHOUT_EDIT = """---
description: Agent ohne Schreibrecht
mode: subagent
permission:
  read: allow
  edit: deny
---

Nur lesen.
"""

INLINE_WRITABLE = """---
description: Agent mit Inline-Rechten
mode: subagent
permission: { read: allow, edit: allow, bash: allow }
---

Prompt.
"""

INLINE_READ_ONLY = """---
description: Inline-Agent ohne Schreibrecht
mode: subagent
permission: { read: allow, edit: deny }
---

Nur lesen.
"""


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(Path(vibe_root) / "home")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_write_dirs_under_test", str(CLI)
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WriteDirsModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli = load_cli(self.root)
        self.permissions_file = self.project / ".vibe" / "permissions.json"

    def tearDown(self):
        self.tmp.cleanup()

    def defaults(self):
        return ["/tmp/opencode", os.path.realpath(self.project)]

    def agent_file(self, name, text=AGENT_TEMPLATE):
        folder = self.project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    # ---------- Liste lesen und ändern ----------

    def test_default_list_contains_tmp_opencode_and_project_directory(self):
        self.assertEqual(self.cli.write_dirs("proj"), self.defaults())

    def test_saved_list_replaces_defaults_and_is_read_again(self):
        wanted = ["/tmp/opencode/arbeit", str(self.project / "src")]

        returned = self.cli.write_dirs_save("proj", wanted)

        self.assertEqual(
            returned,
            [
                os.path.realpath("/tmp/opencode/arbeit"),
                os.path.realpath(self.project / "src"),
            ],
        )
        self.assertEqual(self.cli.write_dirs("proj"), returned)
        stored = json.loads(self.permissions_file.read_text(encoding="utf-8"))
        self.assertEqual(stored["write_dirs"], returned)

    def test_add_remove_and_reset_are_persisted(self):
        extra = "/tmp/opencode/f3-extra"

        after_add = self.cli.write_dirs_add("proj", extra)
        self.assertIn(os.path.realpath(extra), after_add)
        self.assertTrue(self.permissions_file.exists())

        after_remove = self.cli.write_dirs_remove("proj", extra)
        self.assertNotIn(os.path.realpath(extra), after_remove)
        self.assertEqual(after_remove, self.defaults())

        self.cli.write_dirs_remove("proj", os.path.realpath(self.project))
        self.assertNotIn(os.path.realpath(self.project), self.cli.write_dirs("proj"))

        after_reset = self.cli.write_dirs_reset("proj")
        self.assertEqual(after_reset, self.defaults())
        self.assertFalse(self.permissions_file.exists())

    def test_add_rejects_duplicate(self):
        with self.assertRaises(ValueError):
            self.cli.write_dirs_add("proj", "/tmp/opencode")

    def test_remove_rejects_path_that_is_not_listed(self):
        with self.assertRaises(ValueError):
            self.cli.write_dirs_remove("proj", "/tmp/opencode/nicht-gelistet")

    def test_save_deduplicates_paths(self):
        saved = self.cli.write_dirs_save(
            "proj", ["/tmp/opencode/x", "/tmp/opencode/x", "/tmp/opencode/x/"]
        )

        self.assertEqual(saved, [os.path.realpath("/tmp/opencode/x")])

    def test_invalid_paths_are_rejected_without_changing_the_file(self):
        self.cli.write_dirs_save("proj", ["/tmp/opencode/erlaubt"])
        before = self.permissions_file.read_text(encoding="utf-8")

        for invalid in ("", "relativ/pfad", "/", "/tmp/a\nb", "/tmp/a\x00b"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.cli.write_dirs_add("proj", invalid)
                self.assertEqual(
                    self.permissions_file.read_text(encoding="utf-8"), before
                )

    def test_corrupt_permissions_file_is_reported(self):
        self.permissions_file.write_text("{kein json", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.cli.write_dirs("proj")

    # ---------- Agentenvorlage und bestehende Agenten ----------

    def test_template_restricts_edit_to_project_write_dirs(self):
        text = self.cli.agent_template(
            "Testagent",
            perm="voll",
            write_dirs=["/tmp/opencode", str(self.project)],
            prompt="Du bist ein Testagent.",
        )

        self.assertIn("  edit:\n", text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn(f'    "{self.project}/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertNotIn("  edit: allow", text)
        self.assertIn("  bash: allow", text)
        self.assertIn("Du bist ein Testagent.", text)

    def test_template_without_write_dirs_keeps_full_edit_permission(self):
        text = self.cli.agent_template("Testagent", perm="voll")

        self.assertIn("  edit: allow", text)
        self.assertNotIn('    "*": deny', text)

    def test_template_with_empty_list_denies_edits(self):
        text = self.cli.agent_template("Testagent", perm="voll", write_dirs=[])

        self.assertIn("  edit: deny", text)
        self.assertNotIn("  edit:\n", text)

    def test_read_only_preset_stays_read_only(self):
        text = self.cli.agent_template(
            "Testagent", perm="lesen", write_dirs=["/tmp/opencode"]
        )

        self.assertIn("  edit: deny", text)
        self.assertNotIn("/tmp/opencode/**", text)

    def test_apply_write_dirs_rewrites_only_the_edit_block(self):
        path = self.agent_file("proj-agent")

        changed = self.cli.apply_write_dirs(
            "proj", "proj-agent", ["/tmp/opencode", str(self.project)]
        )

        text = path.read_text(encoding="utf-8")
        self.assertEqual(changed, text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn(f'    "{self.project}/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertNotIn("  edit: allow", text)
        self.assertIn("  bash: allow", text)
        self.assertIn("description: Projektagent für Tests", text)
        self.assertIn("Du änderst ausschließlich Dateien im Projekt.", text)
        backups = list((self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), AGENT_TEMPLATE)

    def test_apply_write_dirs_replaces_an_existing_edit_block(self):
        path = self.agent_file("proj-agent")
        self.cli.apply_write_dirs("proj", "proj-agent", ["/tmp/opencode/eins"])

        self.cli.apply_write_dirs("proj", "proj-agent", ["/tmp/opencode/zwei"])

        text = path.read_text(encoding="utf-8")
        self.assertNotIn("/tmp/opencode/eins", text)
        self.assertEqual(text.count('    "/tmp/opencode/zwei/**": allow'), 1)

    def test_apply_write_dirs_keeps_read_only_agent_unchanged(self):
        path = self.agent_file("leser", AGENT_WITHOUT_EDIT)

        returned = self.cli.apply_write_dirs("proj", "leser", ["/tmp/opencode"])

        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_WITHOUT_EDIT)
        self.assertEqual(returned, AGENT_WITHOUT_EDIT)
        self.assertNotIn('    "*": deny', returned)
        backups = list((self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md"))
        self.assertEqual(backups, [])

    def test_apply_write_dirs_keeps_mapping_deny_agent_read_only(self):
        text = """---
description: Agent mit Mapping-Deny
mode: subagent
permission:
  edit:
    "*": deny
  bash:
    "*": deny
    "git status --short": allow
---

Prompt.
"""
        path = self.agent_file("leser", text)

        returned = self.cli.apply_write_dirs("proj", "leser", ["/tmp/opencode"])

        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(returned, text)
        self.assertNotIn("/tmp/opencode", returned)

    def test_cli_rights_output_names_the_edit_limit(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.cli.cmd_rights("proj", "list")

        output = buffer.getvalue()
        self.assertIn("/tmp/opencode", output)
        self.assertIn("begrenzt edit, nicht Shell-Befehle", output)

    def test_apply_write_dirs_restricts_agent_without_permission_block(self):
        path = self.agent_file(
            "offen", "---\ndescription: Agent ohne Rechteblock\nmode: subagent\n---\n\nPrompt.\n"
        )

        self.cli.apply_write_dirs("proj", "offen", ["/tmp/opencode"])

        text = path.read_text(encoding="utf-8")
        self.assertIn("permission:\n  edit:\n", text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertIn("Prompt.", text)

    def test_apply_write_dirs_rejects_unknown_agent_without_creating_files(self):
        with self.assertRaises(ValueError):
            self.cli.apply_write_dirs("proj", "gibt-es-nicht", ["/tmp/opencode"])

        folder = self.project / ".opencode" / "agents"
        self.assertFalse(folder.exists() and any(folder.iterdir()))

    def test_apply_write_dirs_to_project_skips_agents_without_write_permission(self):
        writable = self.agent_file("eins")
        readonly = self.agent_file("zwei", AGENT_WITHOUT_EDIT)

        names = self.cli.apply_write_dirs_to_project("proj")

        self.assertEqual(names, ["eins"])
        text = writable.read_text(encoding="utf-8")
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertEqual(readonly.read_text(encoding="utf-8"), AGENT_WITHOUT_EDIT)

    def test_apply_write_dirs_to_project_ignores_files_with_unaddressable_names(self):
        writable = self.agent_file("eins")
        folder = self.project / ".opencode" / "agents"
        stray = folder / "meine notiz.md"
        stray.write_text(AGENT_TEMPLATE, encoding="utf-8")

        names = self.cli.apply_write_dirs_to_project("proj")

        self.assertEqual(names, ["eins"])
        self.assertIn('    "*": deny', writable.read_text(encoding="utf-8"))
        self.assertEqual(stray.read_text(encoding="utf-8"), AGENT_TEMPLATE)

    def test_apply_write_dirs_to_project_changes_nothing_when_an_agent_is_invalid(self):
        valid = self.agent_file("a-gut")
        invalid = self.agent_file(
            "z-kaputt",
            "---\nmode: subagent\n---\n\nPrompt ohne Beschreibung.\n",
        )

        with self.assertRaises(ValueError):
            self.cli.apply_write_dirs_to_project("proj")

        self.assertEqual(valid.read_text(encoding="utf-8"), AGENT_TEMPLATE)
        self.assertIn("Prompt ohne Beschreibung.", invalid.read_text(encoding="utf-8"))
        backups = list((self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md"))
        self.assertEqual(backups, [])

    def test_apply_write_dirs_rejects_inline_permission_without_changing_file(self):
        path = self.agent_file("fluss", INLINE_WRITABLE)

        with self.assertRaises(ValueError) as raised:
            self.cli.apply_write_dirs("proj", "fluss", ["/tmp/opencode"])

        self.assertIn("Blockform", str(raised.exception))
        self.assertEqual(path.read_text(encoding="utf-8"), INLINE_WRITABLE)
        backups = list((self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md"))
        self.assertEqual(backups, [])


class WriteDirsCopyTest(unittest.TestCase):
    """Kopieren von Agenten darf die Schreibrechte des Zielprojekts nicht umgehen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.other = self.root / "zweit"
        for project in (self.project, self.other):
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8"
            )
        self.home_agents = self.root / "home" / ".config" / "opencode" / "agents"
        self.home_agents.mkdir(parents=True)
        self.cli = load_cli(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def global_agent(self, name, text=AGENT_TEMPLATE):
        path = self.home_agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def project_agent(self, project, name, text=AGENT_TEMPLATE):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def test_copy_global_agent_into_project_restricts_write_dirs(self):
        source = self.global_agent("schreiber")

        self.cli.agent_copy("global", "schreiber", "proj")

        target = self.project / ".opencode" / "agents" / "schreiber.md"
        text = target.read_text(encoding="utf-8")
        self.assertNotIn("  edit: allow", text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn(f'    "{os.path.realpath(self.project)}/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertIn("  bash: allow", text)
        self.assertIn("Du änderst ausschließlich Dateien im Projekt.", text)
        self.assertEqual(source.read_text(encoding="utf-8"), AGENT_TEMPLATE)

    def test_copy_keeps_read_only_agent_read_only(self):
        self.global_agent("leser", AGENT_WITHOUT_EDIT)

        self.cli.agent_copy("global", "leser", "proj")

        text = (self.project / ".opencode" / "agents" / "leser.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("  edit: deny", text)
        self.assertNotIn("/tmp/opencode", text)
        self.assertNotIn('"*": deny', text)

    def test_copy_between_projects_uses_target_project_write_dirs(self):
        self.cli.write_dirs_save("zweit", ["/tmp/opencode/zweit"])
        self.project_agent(self.project, "eins")
        self.cli.apply_write_dirs("proj", "eins", self.cli.write_dirs("proj"))

        self.cli.agent_copy("proj", "eins", "zweit")

        text = (self.other / ".opencode" / "agents" / "eins.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('    "/tmp/opencode/zweit/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertNotIn(os.path.realpath(self.project), text)
        self.assertNotIn("/tmp/opencode/**", text)

    def test_copy_into_project_with_corrupt_list_creates_no_agent(self):
        self.global_agent("schreiber")
        permissions = self.project / ".vibe" / "permissions.json"
        permissions.write_text("{kein json", encoding="utf-8")

        with self.assertRaises(ValueError):
            self.cli.agent_copy("global", "schreiber", "proj")

        target = self.project / ".opencode" / "agents" / "schreiber.md"
        self.assertFalse(target.exists())

    def test_copy_inline_read_only_agent_keeps_file_unchanged(self):
        self.global_agent("leser", INLINE_READ_ONLY)

        self.cli.agent_copy("global", "leser", "proj")

        target = self.project / ".opencode" / "agents" / "leser.md"
        self.assertEqual(target.read_text(encoding="utf-8"), INLINE_READ_ONLY)

    def test_copy_inline_writable_agent_creates_no_agent(self):
        self.global_agent("fluss", INLINE_WRITABLE)

        with self.assertRaises(ValueError) as raised:
            self.cli.agent_copy("global", "fluss", "proj")

        self.assertIn("Blockform", str(raised.exception))
        target = self.project / ".opencode" / "agents" / "fluss.md"
        self.assertFalse(target.exists())


class WriteDirsApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
            }
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
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
        cls.tmp.cleanup()

    def setUp(self):
        permissions = self.project / ".vibe" / "permissions.json"
        if permissions.exists():
            permissions.unlink()
        agents = self.project / ".opencode" / "agents"
        if agents.exists():
            for path in agents.iterdir():
                path.unlink()
            agents.rmdir()
        for path in (self.root / "home" / ".config" / "opencode" / "agents").iterdir():
            path.unlink()

    def request(self, path, payload=None, token=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        if token:
            req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def permissions(self):
        path = self.project / ".vibe" / "permissions.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["write_dirs"]

    def write_agent(self, name, text=AGENT_TEMPLATE):
        folder = self.project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path


class WriteDirsApiTest(WriteDirsApiFixture):
    def test_project_detail_exposes_effective_and_default_write_dirs(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual(
            detail["write_dirs"], ["/tmp/opencode", os.path.realpath(self.project)]
        )
        self.assertEqual(
            detail["write_dirs_default"],
            ["/tmp/opencode", os.path.realpath(self.project)],
        )
        self.assertFalse(detail["write_dirs_custom"])

    def test_corrupt_permissions_file_keeps_detail_usable_and_reset_works(self):
        (self.project / ".vibe" / "permissions.json").write_text(
            "{kein json", encoding="utf-8"
        )

        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual(detail["write_dirs"], [])
        self.assertIn("nicht lesbar", detail["write_dirs_error"])

        status, body = self.request(
            "/api/rights", {"name": "proj", "action": "reset"}
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(
            json.loads(body)["write_dirs"],
            ["/tmp/opencode", os.path.realpath(self.project)],
        )
        self.assertFalse((self.project / ".vibe" / "permissions.json").exists())

    def test_api_adds_removes_and_resets_write_dirs(self):
        status, body = self.request(
            "/api/rights",
            {"name": "proj", "action": "add", "path": "/tmp/opencode/f3-extra"},
        )
        self.assertEqual(status, 200, body)
        self.assertIn(os.path.realpath("/tmp/opencode/f3-extra"), json.loads(body)["write_dirs"])
        self.assertIn(os.path.realpath("/tmp/opencode/f3-extra"), self.permissions())

        status, body = self.request(
            "/api/rights",
            {"name": "proj", "action": "remove", "path": "/tmp/opencode/f3-extra"},
        )
        self.assertEqual(status, 200, body)
        self.assertNotIn(
            os.path.realpath("/tmp/opencode/f3-extra"), json.loads(body)["write_dirs"]
        )

        status, body = self.request(
            "/api/rights", {"name": "proj", "action": "reset"}
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(
            json.loads(body)["write_dirs"],
            ["/tmp/opencode", os.path.realpath(self.project)],
        )
        self.assertIsNone(self.permissions())

    def test_api_rejects_invalid_path_without_writing(self):
        status, body = self.request(
            "/api/rights",
            {"name": "proj", "action": "add", "path": "relativ"},
        )

        self.assertEqual(status, 400, body)
        self.assertIn("absolut", body)
        self.assertIsNone(self.permissions())

    def test_api_rejects_unknown_action(self):
        status, body = self.request(
            "/api/rights", {"name": "proj", "action": "foo"}
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannte Aktion", body)

    def test_api_requires_token_for_rights_changes(self):
        status, body = self.request(
            "/api/rights",
            {"name": "proj", "action": "reset"},
            token=False,
        )

        self.assertEqual(status, 403, body)
        self.assertIsNone(self.permissions())

    def test_agent_template_for_project_uses_the_write_dirs(self):
        status, body = self.request(
            "/api/agent_template",
            {
                "description": "Testagent",
                "mode": "subagent",
                "perm": "voll",
                "prompt": "Prompt",
                "scope": "proj",
            },
        )

        self.assertEqual(status, 200, body)
        text = json.loads(body)["message"]
        self.assertIn(f'    "{os.path.realpath(self.project)}/**": allow', text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertNotIn("  edit: allow", text)

    def test_agent_template_for_global_scope_stays_unrestricted(self):
        status, body = self.request(
            "/api/agent_template",
            {
                "description": "Testagent",
                "mode": "subagent",
                "perm": "voll",
                "prompt": "Prompt",
                "scope": "global",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertIn("  edit: allow", json.loads(body)["message"])

    def test_api_copy_into_project_restricts_write_dirs(self):
        global_agent = self.root / "home" / ".config" / "opencode" / "agents" / "schreiber.md"
        global_agent.write_text(AGENT_TEMPLATE, encoding="utf-8")

        status, body = self.request(
            "/api/agent",
            {"action": "copy", "scope": "global", "name": "schreiber", "to": "proj"},
        )

        self.assertEqual(status, 200, body)
        target = self.project / ".opencode" / "agents" / "schreiber.md"
        text = target.read_text(encoding="utf-8")
        self.assertNotIn("  edit: allow", text)
        self.assertIn(f'    "{os.path.realpath(self.project)}/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertEqual(global_agent.read_text(encoding="utf-8"), AGENT_TEMPLATE)

    def test_api_applies_write_dirs_to_writable_project_agents(self):
        first = self.write_agent("eins")
        second = self.write_agent("zwei", AGENT_WITHOUT_EDIT)

        status, body = self.request(
            "/api/rights", {"name": "proj", "action": "apply"}
        )

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertTrue(result["ok"])
        self.assertEqual(result["changed"], ["eins"])
        text = first.read_text(encoding="utf-8")
        self.assertIn(f'    "{os.path.realpath(self.project)}/**": allow', text)
        self.assertIn('    "*": deny', text)
        self.assertEqual(second.read_text(encoding="utf-8"), AGENT_WITHOUT_EDIT)

    def test_detail_page_contains_write_dirs_controls(self):
        status, html = self.request("/", token=False)

        self.assertEqual(status, 200)
        self.assertIn("Schreibrechte", html)
        self.assertIn("Standard wiederherstellen", html)
        self.assertIn("Auf Projektagenten anwenden", html)
        self.assertIn("write_dirs", html)
        self.assertIn("/api/rights", html)
        self.assertIn("die Liste ist keine Sandbox", html)


if __name__ == "__main__":
    unittest.main()
