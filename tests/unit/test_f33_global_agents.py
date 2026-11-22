"""Unit-Tests F33, WP6.3: Globale AGENTS.md im opencode-Konfigurationsordner.

Ableitung ausschließlich aus ``docs/features/F33.md`` („WP6 — Backend-Verträge“
Punkt 3) und dem Arbeitspaket. Geprüft wird:

* ``global_agents_path(environ=None)`` löst den Ort in dieser Reihenfolge auf:
  ``VIBE_GLOBAL_AGENTS`` → ``XDG_CONFIG_HOME/opencode/AGENTS.md`` →
  ``~/.config/opencode/AGENTS.md``. Alle Tests übergeben ausschließlich
  temporäre ``environ``-Werte (B17-Regel: keine echten Home-Pfade).
* ``global_agents_view()`` liefert ``{"exists", "digest", "text", "path_hint"}``;
  eine fehlende Datei ist kein Fehler (``exists`` falsch, Text leer), ein
  Symlink wird nicht gelesen.
* ``global_agents_save(text, digest)`` schreibt UTF-8 mit Digest-Schutz: ein
  überholter Digest wird abgelehnt, ohne die Datei zu verändern; Symlinks
  werden abgelehnt.
* ``global_agents_create()`` legt nur bei fehlender Datei eine minimale Vorlage
  an; eine vorhandene Datei bleibt unverändert.
* ``GET /api/global_agents_file`` und ``POST {action:"save"|"create"}`` nutzen
  denselben Vertrag über den Handler.

Isolation wie ``tests/unit/test_b17_isolation.py``: alle Pfade liegen unter
``tempfile``; die Prozessumgebung wird je Test auf das temporäre HOME gesetzt.

ROT-PHASE (2026-11-21, vor der Implementierung von WP6.3)
--------------------------------------------------------
Ausgeführt mit::

    python3 -m unittest tests.unit.test_f33_global_agents -v

Ergebnis: 17 Fälle, 17 rot (14 ``AttributeError`` = Vertragsfunktion fehlt,
3 Endpoint 404 = Handler fehlt).

* ``test_env_override_wins``, ``test_xdg_config_home_is_used_when_present``,
  ``test_home_config_directory_is_the_fallback``,
  ``test_resolution_never_touches_the_real_home`` — AttributeError:
  ``global_agents_path`` fehlt.
* ``test_missing_file_is_an_empty_view_without_error``,
  ``test_existing_file_is_returned_with_digest``,
  ``test_symlink_is_reported_as_missing_and_not_read`` — AttributeError:
  ``global_agents_view`` fehlt.
* ``test_save_writes_utf8_with_the_expected_digest``,
  ``test_stale_digest_is_rejected_and_changes_nothing``,
  ``test_missing_digest_is_rejected``,
  ``test_symlink_is_rejected_and_the_target_stays_untouched`` —
  AttributeError: ``global_agents_save`` fehlt.
* ``test_create_writes_a_minimal_template_when_missing``,
  ``test_create_never_overwrites_an_existing_file``,
  ``test_create_rejects_a_symlink`` — AttributeError:
  ``global_agents_create`` fehlt.
* ``test_get_missing_file_reports_an_empty_view``,
  ``test_save_and_create_work_over_the_handler``,
  ``test_save_with_a_stale_digest_is_rejected`` — 404 „nicht gefunden“
  (``/api/global_agents_file`` fehlt).
"""
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

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

GLOBAL_TEXT = "# Globale AGENTS.md\n\nImmer gültig — F33.\n"
GLOBAL_TEXT_NEW = "# Globale AGENTS.md\n\nNeu mit Umlauten: äöü ß und Emoji.\n"

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
    "XDG_CONFIG_HOME",
    "VIBE_GLOBAL_AGENTS",
)


def symlink_supported():
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


SYMLINKS_SUPPORTED = symlink_supported()


def isolated_environ(home, **extra):
    """Bereinigte Umgebung mit temporärem HOME und ohne Produktivpfade."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env["HOME"] = str(home)
    env.update(extra)
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
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
        self.cli = load_cli(self.root, self.home)

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
