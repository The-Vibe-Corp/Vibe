"""Tests für die verlustarme MCP-Konfigurationsbearbeitung (V-013).

Geprüft werden die fachlichen Akzeptanzkriterien aus TICKETS.md:

* JSONC-Kommentare und Trailing Commas bleiben erhalten.
* Unbekannte Einstellungen in der Datei und in bestehenden Servereinträgen
  werden nicht stillschweigend verworfen.
* Nicht unterstützte Felder werden nicht blind angeboten oder gespeichert.
* Mehrere Konfigurationsdateien folgen der tatsächlichen opencode-Priorität.
* Umbenennen erkennt Konflikte und fehlende Server.
* Maskierte Geheimnisse in Headern, Umgebungsvariablen und URL-Parametern
  werden beim Speichern unverändert wiederhergestellt.

Alle Dateien liegen in temporären Verzeichnissen. Es werden keine echten
MCP-Server, opencode-Dienste oder Modellaufrufe gestartet.
"""
import importlib.machinery
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
MCP = BIN / "vibe_mcp.py"


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def write_fake_opencode(directory, version="opencode v2.1.4"):
    """Schreibt eine ausführbare opencode-Attrappe für Versionsprüfungen."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opencode"
    path.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        f"  printf '%b\\n' {version!r}\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unerwarteter Aufruf' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class McpConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.vibe_root = self.root / "vibe"
        self.vibe_root.mkdir()
        self.project = self.vibe_root / "projekt"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        self.config_dir = self.home / ".config" / "opencode"
        self.config_dir.mkdir(parents=True)
        self.config = self.config_dir / "opencode.json"
        self.fakebin = self.root / "fakebin"
        write_fake_opencode(self.fakebin)
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE": str(self.vibe_root),
                "VIBE_NO_CONTAINER": "1",
                "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cli = load_module(CLI, "vibe_mcp_config_cli_under_test")
        sys.modules["vibe"] = self.cli
        self.addCleanup(sys.modules.pop, "vibe", None)
        self.mcp = load_module(MCP, "vibe_mcp_config_under_test")

    def write(self, text, path=None):
        path = Path(path) if path else self.config
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read(self, path=None):
        return (Path(path) if path else self.config).read_text(encoding="utf-8")


class JsoncPreservationTest(McpConfigTestCase):
    def test_comments_trailing_commas_and_unknown_settings_survive_saving(self):
        original = """{
  // global comment
  "theme": "dark",
  "mcp": {
    // server list comment
    "servers": {
      // alt comment
      "alt": {
        "type": "local",
        "command": ["echo", "alt"]
      },
    },
    "meta": {"keep": true},
  },
}
"""
        self.write(original)

        self.mcp.save("global", "neu", {"type": "local", "command": ["echo", "neu"]})

        written = self.read()
        self.assertIn("// global comment", written)
        self.assertIn("// server list comment", written)
        self.assertIn("// alt comment", written)
        self.assertIn('"theme": "dark"', written)
        self.assertIn('"meta": {"keep": true}', written)
        data = self.mcp.jsonc_loads(written)
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["mcp"]["meta"], {"keep": True})
        self.assertEqual(data["mcp"]["servers"]["alt"]["command"], ["echo", "alt"])
        self.assertEqual(data["mcp"]["servers"]["neu"]["command"], ["echo", "neu"])

    def test_comments_inside_an_edited_entry_stay_on_unchanged_fields(self):
        self.write(
            '{\n  "mcp": {\n    "servers": {\n      "alt": {\n'
            '        // type comment\n'
            '        "type": "local",\n'
            '        "command": ["echo"]\n'
            '      }\n    }\n  }\n}\n'
        )

        self.mcp.save("global", "alt", {"type": "local", "command": ["echo", "neu"]})

        written = self.read()
        self.assertIn("// type comment", written)
        data = self.mcp.jsonc_loads(written)
        self.assertEqual(data["mcp"]["servers"]["alt"]["command"], ["echo", "neu"])

    def test_delete_keeps_comments_and_the_other_server(self):
        self.write(
            '{\n  // keep this\n  "mcp": {\n    "servers": {\n'
            '      "alt": {"type": "local", "command": ["echo"]},\n'
            '      "b": {"type": "local", "command": ["echo", "b"]}\n'
            '    }\n  }\n}\n'
        )

        self.mcp.delete("global", "alt")

        written = self.read()
        self.assertIn("// keep this", written)
        self.assertNotIn('"alt"', written)
        data = self.mcp.jsonc_loads(written)
        self.assertEqual(list(data["mcp"]["servers"]), ["b"])

    def test_classic_layout_keeps_unknown_non_server_settings(self):
        self.write(
            '{"mcp": {"alt": {"type": "local", "command": ["echo"]}, "note": "keep"}}\n'
        )

        self.mcp.save(
            "global", "alt", {"type": "local", "command": ["echo", "neu"]}
        )

        data = self.mcp.jsonc_loads(self.read())
        self.assertEqual(data["mcp"]["note"], "keep")
        self.assertEqual(data["mcp"]["alt"]["command"], ["echo", "neu"])

    def test_non_object_mcp_block_is_refused_and_kept_unchanged(self):
        original = '{"mcp": "kaputt"}\n'
        self.write(original)

        with self.assertRaises(ValueError) as raised:
            self.mcp.save("global", "neu", {"type": "local", "command": ["echo"]})

        self.assertIn("nicht feststellbar", str(raised.exception))
        self.assertEqual(self.read(), original)


class SchemaFieldsTest(McpConfigTestCase):
    def test_supported_fields_of_the_actual_schema_are_accepted(self):
        local = {
            "type": "local",
            "command": ["echo"],
            "cwd": "/tmp",
            "environment": {"A": "B"},
            "enabled": True,
            "timeout": 1000,
        }
        remote = {
            "type": "remote",
            "url": "https://example.test/mcp",
            "headers": {"Authorization": "Bearer x"},
            "oauth": False,
            "enabled": False,
            "timeout": 1000,
        }

        self.assertIs(self.mcp.validate(local), local)
        self.assertIs(self.mcp.validate(remote), remote)

    def test_unsupported_fields_are_rejected(self):
        cases = [
            {"type": "local", "command": ["echo"], "url": "https://example.test"},
            {"type": "remote", "url": "https://example.test", "command": ["echo"]},
            {"type": "local", "command": ["echo"], "oauth": False},
            {"type": "remote", "url": "https://example.test", "cwd": "/tmp"},
            {"type": "remote", "url": "https://example.test", "blind": True},
        ]

        for entry in cases:
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError) as raised:
                    self.mcp.validate(entry)
                self.assertIn("nicht unterstützt", str(raised.exception))

    def test_unknown_field_of_an_existing_entry_is_preserved_but_new_ones_are_rejected(self):
        self.write(
            '{"mcp": {"servers": {"alt": {"type": "local", "command": ["echo"],'
            ' "x-custom": {"keep": true}}}}}\n'
        )

        self.mcp.save("global", "alt", {"type": "local", "command": ["echo", "neu"]})

        data = self.mcp.jsonc_loads(self.read())
        self.assertEqual(
            data["mcp"]["servers"]["alt"]["x-custom"], {"keep": True}
        )

        before = self.read()
        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "alt",
                {"type": "local", "command": ["echo"], "blind": True},
            )
        self.assertIn("nicht unterstützt", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_testing_an_existing_entry_keeps_its_unknown_fields_usable(self):
        self.write(
            '{"mcp": {"servers": {"alt": {"type": "local", "command": ["echo"],'
            ' "x-custom": {"keep": true}}}}}\n'
        )
        calls = []
        self.mcp.test_local = lambda entry, cwd: calls.append(entry) or {"ok": True}

        result = self.mcp.test("global", "alt")

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0]["x-custom"], {"keep": True})

    def test_changing_an_existing_unknown_field_is_rejected(self):
        self.write(
            '{"mcp": {"servers": {"alt": {"type": "local", "command": ["echo"],'
            ' "x-custom": {"keep": true}}}}}\n'
        )
        before = self.read()

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "alt",
                {"type": "local", "command": ["echo"], "x-custom": "geändert"},
            )

        self.assertIn("nicht geändert", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_invalid_oauth_shape_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.mcp.validate(
                {
                    "type": "remote",
                    "url": "https://example.test",
                    "oauth": {"clientSecret": "x", "unbekannt": True},
                }
            )

        self.assertIn("nicht unterstützt", str(raised.exception))


class ConfigFileSelectionTest(McpConfigTestCase):
    def test_file_priority_matches_opencode_mcp_add(self):
        json_file = self.write('{"mcp": {"servers": {}}}\n', self.config)
        jsonc_file = self.write(
            '{"mcp": {"servers": {"jsonc": {"type": "local", "command": ["echo"]}}}}\n',
            self.config_dir / "opencode.jsonc",
        )
        self.assertEqual(self.mcp.cfg_path("global"), str(json_file))
        self.assertEqual(self.mcp.load("global")[0], str(json_file))

        json_file.unlink()
        self.assertEqual(self.mcp.cfg_path("global"), str(jsonc_file))

        jsonc_file.unlink()
        nested = self.write(
            '{"mcp": {"servers": {"nested": {"type": "local", "command": ["echo"]}}}}\n',
            self.config_dir / ".opencode" / "opencode.json",
        )
        self.assertEqual(self.mcp.cfg_path("global"), str(nested))
        self.assertEqual(list(self.mcp.load("global")[4]), ["nested"])

        nested.unlink()
        self.assertEqual(self.mcp.cfg_path("global"), str(self.config))

    def test_project_falls_back_to_the_dot_opencode_directory(self):
        nested = self.write(
            '{"mcp": {"servers": {"p": {"type": "local", "command": ["echo"]}}}}\n',
            self.project / ".opencode" / "opencode.json",
        )

        self.assertEqual(self.mcp.cfg_path("projekt"), str(nested))
        self.assertEqual(list(self.mcp.load("projekt")[4]), ["p"])

    def test_global_and_project_configurations_are_edited_separately(self):
        project_config = self.write(
            '{"mcp": {"servers": {"p": {"type": "local", "command": ["echo", "p"]}}}}\n',
            self.project / "opencode.json",
        )
        self.write(
            '{"mcp": {"servers": {"g": {"type": "local", "command": ["echo", "g"]}}}}\n'
        )

        self.mcp.save("global", "neu", {"type": "local", "command": ["echo", "neu"]})
        global_data = self.mcp.jsonc_loads(self.read())
        project_data = self.mcp.jsonc_loads(self.read(project_config))
        self.assertEqual(sorted(global_data["mcp"]["servers"]), ["g", "neu"])
        self.assertEqual(list(project_data["mcp"]["servers"]), ["p"])

        self.mcp.save(
            "projekt", "neu2", {"type": "local", "command": ["echo", "neu2"]}
        )
        global_data = self.mcp.jsonc_loads(self.read())
        project_data = self.mcp.jsonc_loads(self.read(project_config))
        self.assertEqual(sorted(global_data["mcp"]["servers"]), ["g", "neu"])
        self.assertEqual(sorted(project_data["mcp"]["servers"]), ["neu2", "p"])

        rows = self.mcp.list_all()
        by_scope = {(row["scope"], row["name"]): row for row in rows if "name" in row}
        self.assertEqual(by_scope[("global", "neu")]["path"], str(self.config))
        self.assertEqual(by_scope[("projekt", "neu2")]["path"], str(project_config))

    def test_backups_of_base_and_nested_files_use_distinct_labels(self):
        base = self.write('{"mcp": {"servers": {}}}\n', self.config)
        nested = self.write(
            '{"mcp": {"servers": {}}}\n',
            self.config_dir / ".opencode" / "opencode.json",
        )
        base_label = self.mcp.backup_label("global", str(base))
        nested_label = self.mcp.backup_label("global", str(nested))
        self.assertNotEqual(base_label, nested_label)

        base.unlink()
        self.mcp.save("global", "n", {"type": "local", "command": ["echo"]})

        rows = self.mcp.backups("global")
        self.assertEqual(len(rows), 1)
        self.assertIn(".opencode_opencode", rows[0])
        self.assertEqual(
            self.mcp.vibe_storage.list_backups(self.mcp.backup_dir(), label=base_label),
            [],
        )


class RenameTest(McpConfigTestCase):
    def setUp(self):
        super().setUp()
        self.write(
            '{"mcp": {"servers": {'
            '"a": {"type": "local", "command": ["echo", "a"]},'
            '"b": {"type": "local", "command": ["echo", "b"]}}}}\n'
        )

    def test_rename_to_an_existing_name_is_rejected_without_changes(self):
        before = self.read()

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "b",
                {"type": "local", "command": ["echo", "a"]},
                old_name="a",
            )

        self.assertIn("existiert schon", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_rename_of_a_missing_server_is_rejected(self):
        before = self.read()

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "neu",
                {"type": "local", "command": ["echo"]},
                old_name="fehlt",
            )

        self.assertIn("nicht gefunden", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_rename_moves_the_entry(self):
        self.mcp.save(
            "global", "neu", {"type": "local", "command": ["echo", "a"]}, old_name="a"
        )

        servers = self.mcp.load("global")[4]
        self.assertEqual(sorted(servers), ["b", "neu"])
        self.assertEqual(servers["neu"]["command"], ["echo", "a"])


class SecretMaskingTest(McpConfigTestCase):
    def test_masked_secrets_are_restored_when_other_parts_change(self):
        self.write(
            '{"mcp": {"servers": {"remote": {'
            '"type": "remote",'
            '"url": "https://example.test/mcp?token=abc123&mode=read",'
            '"headers": {"Authorization": "Bearer topsecret"},'
            '"environment": {"API_KEY": "envsecret"}}}}}\n'
        )

        masked = self.mcp.get_entry("global", "remote")["entry"]
        self.assertEqual(masked["url"], "https://example.test/mcp?token=***&mode=read")
        self.assertEqual(masked["headers"]["Authorization"], "***")
        self.assertEqual(masked["environment"]["API_KEY"], "***")

        self.mcp.save(
            "global",
            "remote",
            {
                "type": "remote",
                "url": "https://example.test/mcp?token=***&mode=write",
                "headers": {"Authorization": "***"},
                "environment": {"API_KEY": "***"},
            },
        )

        saved = self.mcp.load("global")[4]["remote"]
        self.assertEqual(
            saved["url"], "https://example.test/mcp?token=abc123&mode=write"
        )
        self.assertEqual(saved["headers"]["Authorization"], "Bearer topsecret")
        self.assertEqual(saved["environment"]["API_KEY"], "envsecret")

    def test_masked_secret_without_original_is_rejected(self):
        self.write(
            '{"mcp": {"servers": {"remote": {'
            '"type": "remote", "url": "https://example.test/mcp"}}}}\n'
        )

        before = self.read()
        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "remote",
                {
                    "type": "remote",
                    "url": "https://example.test/mcp?token=***",
                },
            )
        self.assertIn("nicht wiederhergestellt", str(raised.exception))
        self.assertEqual(self.read(), before)

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "remote",
                {
                    "type": "remote",
                    "url": "https://example.test/mcp",
                    "headers": {"Authorization": "***"},
                },
            )
        self.assertIn("nicht wiederhergestellt", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_masked_oauth_client_secret_is_restored(self):
        self.write(
            '{"mcp": {"servers": {"remote": {'
            '"type": "remote", "url": "https://example.test/mcp",'
            '"oauth": {"clientId": "id", "clientSecret": "s3cret"}}}}}\n'
        )

        masked = self.mcp.get_entry("global", "remote")["entry"]
        self.assertEqual(masked["oauth"]["clientSecret"], "***")

        self.mcp.save(
            "global",
            "remote",
            {
                "type": "remote",
                "url": "https://example.test/mcp",
                "oauth": {"clientId": "id2", "clientSecret": "***"},
            },
        )

        saved = self.mcp.load("global")[4]["remote"]
        self.assertEqual(saved["oauth"]["clientId"], "id2")
        self.assertEqual(saved["oauth"]["clientSecret"], "s3cret")

    def test_duplicate_secret_url_parameters_are_not_silently_rewritten(self):
        self.write(
            '{"mcp": {"servers": {"remote": {'
            '"type": "remote",'
            '"url": "https://example.test/mcp?token=A&token=B"}}}}\n'
        )
        before = self.read()

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "remote",
                {
                    "type": "remote",
                    "url": "https://example.test/mcp?token=***&token=***",
                },
            )
        self.assertIn("nicht wiederhergestellt", str(raised.exception))
        self.assertEqual(self.read(), before)

        with self.assertRaises(ValueError) as raised:
            self.mcp.save(
                "global",
                "remote",
                {"type": "remote", "url": "https://example.test/mcp?token=***"},
            )
        self.assertIn("nicht wiederhergestellt", str(raised.exception))
        self.assertEqual(self.read(), before)

    def test_environment_placeholders_are_not_masked(self):
        masked = self.mcp.mask_entry(
            {
                "type": "remote",
                "url": "https://example.test/mcp?token={env:TOKEN}&key=abc",
            }
        )

        self.assertEqual(
            masked["url"], "https://example.test/mcp?token={env:TOKEN}&key=***"
        )

    def test_literal_mask_outside_a_secret_parameter_is_kept(self):
        self.write(
            '{"mcp": {"servers": {"remote": {'
            '"type": "remote", "url": "https://example.test/***/mcp"}}}}\n'
        )

        self.mcp.save(
            "global",
            "remote",
            {"type": "remote", "url": "https://example.test/***/mcp"},
        )

        saved = self.mcp.load("global")[4]["remote"]
        self.assertEqual(saved["url"], "https://example.test/***/mcp")

    def test_parameter_names_are_matched_as_whole_words(self):
        masked = self.mcp.mask_entry(
            {
                "type": "remote",
                "url": "https://example.test/mcp?oauth=public&token=abc",
            }
        )

        self.assertEqual(
            masked["url"], "https://example.test/mcp?oauth=public&token=***"
        )


if __name__ == "__main__":
    unittest.main()
