"""Tests für die gemeinsame Storage-Schicht (V-005).

Geprüft werden atomare Writes, konkurrierende Änderungen, abgebrochene und
fehlgeschlagene Schreibvorgänge, kollisionsfreie Sicherungen, Wiederherstellung
sowie die ehrliche Einordnung von FUSE-/NTFS-Dateisystemen. Die Integration
schreibt echte Agenten- und MCP-Konfigurationsdateien in temporären
Verzeichnissen; die API-Tests starten das Dashboard auf einem eigenen Port.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import multiprocessing
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
sys.path.insert(0, str(BIN))

import vibe_storage  # noqa: E402


AGENT_V1 = """---
description: Agent Fassung eins
mode: subagent
permission:
  edit: deny
---

Prompt Fassung eins.
"""

AGENT_V2 = """---
description: Agent Fassung zwei
mode: subagent
permission:
  edit: deny
---

Prompt Fassung zwei.
"""

AGENT_V3 = """---
description: Agent Fassung drei
mode: subagent
permission:
  edit: deny
---

Prompt Fassung drei.
"""

MCP_CONFIG = """{
  // Kommentar außerhalb des mcp-Blocks bleibt erhalten
  "mcp": {
    "servers": {
      "alt": {"type": "local", "command": ["echo", "alt"]}
    }
  }
}
"""


def _concurrent_writer(path, expected, content, barrier, queue):
    barrier.wait(20)
    try:
        vibe_storage.write_text(path, content, expected=expected)
        queue.put(("ok", content))
    except vibe_storage.ConcurrentChangeError as error:
        queue.put(("conflict", str(error)))
    except Exception as error:  # pragma: no cover - diagnostics for the test
        queue.put(("error", f"{type(error).__name__}: {error}"))


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader("vibe_storage_under_test", str(CLI))
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


def load_mcp(vibe_module):
    sys.modules["vibe"] = vibe_module
    spec = importlib.util.spec_from_file_location("vibe_mcp_storage_under_test", BIN / "vibe_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StorageWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "config.json"
        self.locks = self.dir / "locks"
        self.env = mock.patch.dict(os.environ, {"VIBE_STORAGE_LOCK_DIR": str(self.locks)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def temps(self):
        return sorted(p.name for p in self.dir.iterdir() if p.name.startswith(".vibe-"))

    def test_write_replaces_content_without_leaving_temp_files(self):
        snapshot = vibe_storage.write_text(self.path, "eins\n")

        self.assertEqual(self.path.read_text(encoding="utf-8"), "eins\n")
        self.assertEqual(snapshot.digest, vibe_storage.digest_bytes(b"eins\n"))
        self.assertEqual(self.temps(), [])

    def test_overwrite_keeps_existing_permissions(self):
        vibe_storage.write_text(self.path, "alt", mode=0o600)

        vibe_storage.write_text(self.path, "neu")

        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "neu")

    def test_stale_expected_digest_is_rejected_without_changing_the_file(self):
        vibe_storage.write_text(self.path, "alt")

        with self.assertRaises(vibe_storage.ConcurrentChangeError) as raised:
            vibe_storage.write_text(self.path, "neu", expected="0" * 64)

        self.assertIn("zwischenzeitlich geändert", str(raised.exception))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "alt")

    def test_missing_guard_refuses_an_existing_file(self):
        vibe_storage.write_text(self.path, "alt")

        with self.assertRaises(vibe_storage.ConcurrentChangeError):
            vibe_storage.write_text(self.path, "neu", expected=vibe_storage.MISSING)

        self.assertEqual(self.path.read_text(encoding="utf-8"), "alt")

    def test_expected_digest_detects_removed_file(self):
        vibe_storage.write_text(self.path, "alt")
        digest = vibe_storage.file_digest(self.path)
        self.path.unlink()

        with self.assertRaises(vibe_storage.ConcurrentChangeError) as raised:
            vibe_storage.write_text(self.path, "neu", expected=digest)

        self.assertIn("entfernt", str(raised.exception))
        self.assertFalse(self.path.exists())

    def test_write_error_keeps_original_and_removes_the_temp_file(self):
        vibe_storage.write_text(self.path, "alt")

        with mock.patch("vibe_storage.os.replace", side_effect=OSError(28, "Kein Platz")):
            with self.assertRaises(OSError):
                vibe_storage.write_text(self.path, "neu")

        self.assertEqual(self.path.read_text(encoding="utf-8"), "alt")
        self.assertEqual(self.temps(), [])

    def test_interrupted_write_leaves_target_untouched(self):
        self.path.write_text("original", encoding="utf-8")
        code = (
            "import os,sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import vibe_storage\n"
            "staged = vibe_storage.stage_text(sys.argv[2], 'halb geschrieben')\n"
            "print(staged, flush=True)\n"
            "os._exit(9)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code, str(BIN), str(self.path)],
            capture_output=True, text=True, timeout=30,
        )

        self.assertEqual(proc.returncode, 9, proc.stderr)
        staged = Path(proc.stdout.strip())
        self.assertTrue(staged.exists(), "temporäre Datei fehlt")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "original")

        vibe_storage.write_text(self.path, "neu", expected=vibe_storage.file_digest(self.path))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "neu")
        staged.unlink()

    def test_concurrent_saving_allows_exactly_one_writer(self):
        vibe_storage.write_text(self.path, "start")
        expected = vibe_storage.file_digest(self.path)
        context = multiprocessing.get_context("fork")
        barrier = context.Barrier(2)
        queue = context.Queue()
        processes = [
            context.Process(
                target=_concurrent_writer,
                args=(str(self.path), expected, content, barrier, queue),
            )
            for content in ("schreiber-a", "schreiber-b")
        ]
        for process in processes:
            process.start()
        results = [queue.get(timeout=20) for _ in range(2)]
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(process.exitcode, 0)

        outcomes = sorted(result[0] for result in results)
        self.assertEqual(outcomes, ["conflict", "ok"], results)
        conflict = next(result for result in results if result[0] == "conflict")
        self.assertIn("zwischenzeitlich geändert", conflict[1])
        winner = next(result[1] for result in results if result[0] == "ok")
        self.assertEqual(self.path.read_text(encoding="utf-8"), winner)
        self.assertEqual(self.temps(), [])


class StorageBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.backups = self.dir / "backups"
        self.target = self.dir / "agent.md"
        self.env = mock.patch.dict(
            os.environ, {"VIBE_STORAGE_LOCK_DIR": str(self.dir / "locks")}
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_backups_in_the_same_microsecond_do_not_collide(self):
        with mock.patch("vibe_storage.secrets.token_hex", return_value="abcd"):
            first = vibe_storage.backup_bytes(
                self.target, b"eins", self.backups, label="agent", now=1700000000.123456
            )
            second = vibe_storage.backup_bytes(
                self.target, b"zwei", self.backups, label="agent", now=1700000000.123456
            )

        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b"eins")
        self.assertEqual(Path(second).read_bytes(), b"zwei")
        self.assertEqual(
            vibe_storage.list_backups(self.backups, label="agent"),
            sorted([Path(first).name, Path(second).name]),
        )

    def test_backup_directory_and_files_are_restricted(self):
        path = vibe_storage.backup_bytes(self.target, b"geheim", self.backups, label="agent")

        self.assertEqual(stat.S_IMODE(self.backups.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode), 0o600)

    def test_restore_brings_back_the_old_content_and_secures_the_current_one(self):
        vibe_storage.write_text(self.target, "version1")
        backup = vibe_storage.backup_file(self.target, self.backups, label="agent")
        vibe_storage.write_text(self.target, "version2")

        result = vibe_storage.restore_backup(
            self.backups, Path(backup).name, self.target,
            expected=vibe_storage.file_digest(self.target), label="agent",
        )

        self.assertEqual(self.target.read_text(encoding="utf-8"), "version1")
        self.assertIsNotNone(result["safety"])
        self.assertEqual(Path(result["safety"]).read_text(encoding="utf-8"), "version2")
        self.assertIn(Path(backup).name, vibe_storage.list_backups(self.backups, label="agent"))

    def test_restore_rejects_names_outside_the_backup_directory(self):
        outside = self.dir / "fremd.md"
        outside.write_text("fremd", encoding="utf-8")

        with self.assertRaises(vibe_storage.BackupError):
            vibe_storage.restore_backup(self.backups, "../fremd.md", self.target)

        self.assertFalse(self.target.exists())

    def test_restore_rejects_a_stale_expected_digest(self):
        vibe_storage.write_text(self.target, "version1")
        backup = vibe_storage.backup_file(self.target, self.backups, label="agent")
        stale = vibe_storage.file_digest(self.target)
        vibe_storage.write_text(self.target, "version2")
        before = vibe_storage.list_backups(self.backups, label="agent")

        with self.assertRaises(vibe_storage.ConcurrentChangeError):
            vibe_storage.restore_backup(
                self.backups, Path(backup).name, self.target, expected=stale, label="agent"
            )

        self.assertEqual(self.target.read_text(encoding="utf-8"), "version2")
        self.assertEqual(vibe_storage.list_backups(self.backups, label="agent"), before,
                         "abgelehnte Wiederherstellung darf keine Sicherung anlegen")

    def test_restore_missing_backup_is_reported(self):
        with self.assertRaises(vibe_storage.BackupError):
            vibe_storage.restore_backup(self.backups, "gibtsnicht.md", self.target)


class FilesystemNotesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.mountinfo = self.dir / "mounts"
        self.mountinfo.write_text(
            "/dev/sda1 / ext4 rw,relatime 0 0\n"
            "/dev/sdb1 /mnt/data fuseblk rw,nosuid,nodev 0 0\n"
            "/dev/sdc1 /mnt/ntfs ntfs3 rw 0 0\n"
            "/dev/sdd1 /mnt/glatt magicfs rw 0 0\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def notes(self, path):
        return vibe_storage.filesystem_notes(path, mountinfo=self.mountinfo)

    def test_local_linux_filesystem_is_reported_as_atomic(self):
        notes = self.notes("/home/nutzer/projekt/agent.md")

        self.assertEqual(notes["fstype"], "ext4")
        self.assertTrue(notes["atomic"])
        self.assertTrue(notes["posix_permissions"])
        self.assertEqual(notes["warning"], "")

    def test_fuse_ntfs_gets_no_atomicity_or_permission_promise(self):
        notes = self.notes("/mnt/data/projekt/agent.md")

        self.assertEqual(notes["fstype"], "fuseblk")
        self.assertFalse(notes["atomic"])
        self.assertFalse(notes["posix_permissions"])
        self.assertIn("fuseblk", notes["warning"])
        self.assertIn("nicht garantiert", notes["warning"])

    def test_ntfs3_gets_no_atomicity_promise(self):
        notes = self.notes("/mnt/ntfs/agent.md")

        self.assertFalse(notes["atomic"])
        self.assertIn("ntfs3", notes["warning"])

    def test_unknown_filesystem_is_not_claimed_as_safe(self):
        notes = self.notes("/mnt/glatt/agent.md")

        self.assertIsNone(notes["atomic"])
        self.assertIsNone(notes["posix_permissions"])
        self.assertIn("unbekannt", notes["warning"])

    def test_missing_mount_table_is_not_claimed_as_safe(self):
        notes = vibe_storage.filesystem_notes(
            "/mnt/data/agent.md", mountinfo=self.dir / "fehlt"
        )

        self.assertIsNone(notes["atomic"])
        self.assertIn("unbekannt", notes["warning"])


class AgentStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cli = load_cli(self.root / "vibe", self.home)
        self.path = self.agents / "tester.md"

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_update_and_restore_use_collision_free_backups(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)
        first = vibe_storage.read_snapshot(self.path)
        self.cli.agent_write("global", "tester", AGENT_V2, expected=first.digest)
        second = vibe_storage.read_snapshot(self.path)
        self.cli.agent_write("global", "tester", AGENT_V3, expected=second.digest)

        backups = self.cli.agent_backups("global", "tester")
        self.assertEqual(len(backups), 2)
        self.assertEqual(len(set(backups)), 2)
        newest = Path(self.cli.agent_backup_dir("global")) / backups[-1]
        self.assertEqual(newest.read_text(encoding="utf-8"), AGENT_V2)

        result = self.cli.agent_restore("global", "tester")

        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V2)
        self.assertEqual(Path(result["safety"]).read_text(encoding="utf-8"), AGENT_V3)
        self.assertEqual(
            self.cli.agent_backups("global", "tester")[0],
            backups[0],
        )

    def test_restore_an_explicit_older_backup(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)
        first = vibe_storage.read_snapshot(self.path)
        self.cli.agent_write("global", "tester", AGENT_V2, expected=first.digest)
        backups = self.cli.agent_backups("global", "tester")

        self.cli.agent_restore("global", "tester", backups[0])

        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_stale_digest_is_rejected_and_creates_no_backup(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)
        stale = vibe_storage.read_snapshot(self.path).digest
        self.cli.agent_write("global", "tester", AGENT_V2, expected=stale)
        backups = self.cli.agent_backups("global", "tester")

        with self.assertRaises(vibe_storage.ConcurrentChangeError):
            self.cli.agent_write("global", "tester", AGENT_V3, expected=stale)

        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V2)
        self.assertEqual(self.cli.agent_backups("global", "tester"), backups)

    def test_create_refuses_an_existing_agent_without_changing_it(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)

        with self.assertRaises(ValueError):
            self.cli.agent_write("global", "tester", AGENT_V2,
                                 create=True, expected=vibe_storage.MISSING)

        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_delete_creates_a_restorable_backup(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)

        self.cli.agent_delete("global", "tester")
        self.assertFalse(self.path.exists())

        self.cli.agent_restore("global", "tester")
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_cli_lists_and_restores_the_chosen_backup(self):
        self.cli.agent_write("global", "tester", AGENT_V1,
                             create=True, expected=vibe_storage.MISSING)
        first = vibe_storage.read_snapshot(self.path)
        self.cli.agent_write("global", "tester", AGENT_V2, expected=first.digest)
        backups = self.cli.agent_backups("global", "tester")

        listing = io.StringIO()
        with contextlib.redirect_stdout(listing):
            self.cli.cmd_agent("backups", "tester", "global")

        for name in backups:
            self.assertIn(name, listing.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.cli.cmd_agent("restore", "tester", "global", backups[0])

        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENT_V1)

    def test_profile_save_rejects_a_stale_digest(self):
        data = self.cli.profiles_load()
        self.cli.profiles_save(data)
        stale = "0" * 64

        with self.assertRaises(vibe_storage.ConcurrentChangeError):
            self.cli.profiles_save(data, expected=stale)

    def test_unsafe_filesystem_warning_is_reported_on_save(self):
        warning = "Dateisystem fuseblk: atomare Ersetzung ist nicht garantiert."
        with mock.patch.object(
            vibe_storage, "filesystem_notes", return_value={"warning": warning}
        ):
            warnings = self.cli.agent_write(
                "global", "tester", AGENT_V1,
                create=True, expected=vibe_storage.MISSING,
            )

        self.assertIn(warning, warnings)


class McpStorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.config = self.home / ".config" / "opencode" / "opencode.json"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(MCP_CONFIG, encoding="utf-8")
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cli = load_cli(self.root / "vibe", self.home)
        self.mcp = load_mcp(self.cli)

    def tearDown(self):
        sys.modules.pop("vibe", None)
        self.tmp.cleanup()

    def servers(self):
        return self.mcp.load("global")[4]

    def test_save_keeps_other_servers_and_creates_collision_free_backups(self):
        self.mcp.save("global", "eins", {"type": "local", "command": ["echo", "eins"]})
        self.mcp.save("global", "zwei", {"type": "local", "command": ["echo", "zwei"]})

        servers = self.servers()
        self.assertEqual(sorted(servers), ["alt", "eins", "zwei"])
        backups = self.mcp.backups("global")
        self.assertEqual(len(backups), 2)
        self.assertEqual(len(set(backups)), 2)
        self.assertIn("Kommentar außerhalb", self.config.read_text(encoding="utf-8"))
        self.assertEqual(
            [p.name for p in self.config.parent.iterdir() if p.name.startswith(".vibe-")],
            [],
        )

    def test_stale_expected_digest_is_rejected_without_changing_the_config(self):
        self.mcp.save("global", "eins", {"type": "local", "command": ["echo", "eins"]})
        stale = vibe_storage.file_digest(self.config)
        updated = self.config.read_text(encoding="utf-8") + "\n"
        self.config.write_text(updated, encoding="utf-8")

        with self.assertRaises(vibe_storage.ConcurrentChangeError):
            self.mcp.save("global", "zwei", {"type": "local", "command": ["echo", "zwei"]},
                          expected=stale)

        self.assertEqual(self.config.read_text(encoding="utf-8"), updated)
        self.assertNotIn("zwei", self.servers())

    def test_restore_brings_back_the_previous_configuration(self):
        self.mcp.save("global", "eins", {"type": "local", "command": ["echo", "eins"]})
        first = self.mcp.backups("global")[0]
        self.mcp.save("global", "zwei", {"type": "local", "command": ["echo", "zwei"]})

        result = self.mcp.restore("global", first)

        self.assertEqual(sorted(self.servers()), ["alt"])
        self.assertIsNotNone(result["safety"])
        self.assertIn("zwei", Path(result["safety"]).read_text(encoding="utf-8"))

    def test_cli_restore_uses_the_given_backup(self):
        self.mcp.save("global", "eins", {"type": "local", "command": ["echo", "eins"]})
        first = self.mcp.backups("global")[0]
        self.mcp.save("global", "zwei", {"type": "local", "command": ["echo", "zwei"]})

        listing = io.StringIO()
        with contextlib.redirect_stdout(listing):
            self.mcp.cli("backups", "global")

        self.assertIn(first, listing.getvalue())
        self.assertIn("vibe mcp restore global", listing.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.mcp.cli("restore", "global", first)

        self.assertEqual(sorted(self.servers()), ["alt"])


class AgentApiConflictTest(unittest.TestCase):
    """Die Weboberfläche erkennt eine Änderung zwischen Laden und Speichern."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.port = free_port()
        # Der Testserver muss auf 127.0.0.1 binden (kein geerbtes
        # VIBE_UI_BIND) und darf keine persönliche config.json lesen.
        env = env_support.isolated_environ()
        env.update({
            "VIBE": str(cls.root / "vibe"),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.home),
            "VIBE_STORAGE_LOCK_DIR": str(cls.root / "locks"),
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.root / "vibe" / "_logs" / "web.token"
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
        for path in self.agents.iterdir():
            path.unlink()

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, json.loads(body)

    def test_stale_digest_returns_conflict_and_keeps_the_saved_file(self):
        path = self.agents / "tester.md"
        path.write_text(AGENT_V1, encoding="utf-8")
        status, loaded = self.request("/api/agent?scope=global&name=tester")
        self.assertEqual(status, 200, loaded)
        self.assertEqual(loaded["text"], AGENT_V1)
        self.assertTrue(loaded["digest"])

        status, saved = self.request("/api/agent", {
            "action": "save", "scope": "global", "name": "tester",
            "text": AGENT_V2, "expected": loaded["digest"],
        })
        self.assertEqual(status, 200, saved)
        self.assertTrue(saved["ok"])
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V2)

        status, conflict = self.request("/api/agent", {
            "action": "save", "scope": "global", "name": "tester",
            "text": AGENT_V3, "expected": loaded["digest"],
        })
        self.assertEqual(status, 409, conflict)
        self.assertEqual(conflict["error"]["code"], "conflict")
        self.assertIn("zwischenzeitlich geändert", conflict["error"]["message"])
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V2)


if __name__ == "__main__":
    unittest.main()
