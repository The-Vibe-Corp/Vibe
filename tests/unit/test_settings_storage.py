"""Persistente Nutzer-Einstellungen: Storage-Modul und Dashboard-API (GH-117).

Aufruf: python3 -m unittest tests.unit.test_settings_storage -v

Die Tests lesen und schreiben ausschließlich temporäre Zustandsordner und
starten das Dashboard auf einem eigenen Loopback-Port mit isolierter HOME/
VIBE-Konfiguration. Es werden keine echten Modelle aufgerufen und keine
produktive Konfiguration berührt.
"""

import html
import http.client
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
WEB = REPO / "bin" / "vibe-web.py"
INDEX_HTML = BIN / "web" / "index.html"
CLASSIC_HTML = BIN / "web" / "classic.html"

sys.path.insert(0, str(BIN))

try:
    import vibe_settings  # noqa: E402
except ImportError:  # Der rote Lauf vor der Implementierung ist aussagekräftig.
    vibe_settings = None

try:
    import vibe_storage  # noqa: E402
except ImportError:  # pragma: no cover - Storage ist Bestandscode.
    vibe_storage = None

USE_TOKEN = object()

EXPECTED_ACCENTS = (
    "blue", "teal", "cyan", "green", "lime", "yellow",
    "amber", "orange", "red", "pink", "violet", "indigo",
)
EXPECTED_FEATURES = (
    "github", "agentsfile", "writeaccess", "models", "profiles",
    "mcp", "harness", "gates", "sandbox", "priority",
)
EXPECTED_DEFAULTS = {
    "theme": "light",
    "accent": "blue",
    "features": {},
    "favorite_projects": [],
    "favorite_agents": [],
}


def free_port():
    """Reserviert kurz einen freien Loopback-Port und gibt ihn frei."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def settings_module():
    """Liefert das Modul oder bricht mit dem klaren Implementierungsgrund ab."""
    if vibe_settings is None:
        raise AssertionError(
            "bin/vibe_settings.py fehlt oder ist nicht importierbar (GH-117)")
    return vibe_settings


class SettingsStorageTest(unittest.TestCase):
    """Reine Datei-Verträge von bin/vibe_settings.py in einem temporären Ordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.settings = settings_module()
        self.addCleanup(self.tmp.cleanup)

    def target(self):
        return Path(self.settings.path(self.state))

    def write_raw(self, payload):
        """Legt eine beliebige (auch ungültige) Datei direkt an."""
        target = self.target()
        target.write_text(payload, encoding="utf-8")
        return target

    def raw(self):
        return json.loads(self.target().read_text(encoding="utf-8"))

    def test_public_contract_constants(self):
        s = self.settings
        self.assertEqual("settings.json", s.FILENAME)
        self.assertEqual(1, s.SCHEMA_VERSION)
        self.assertEqual(("light", "dark", "auto"), tuple(s.THEMES))
        self.assertEqual(EXPECTED_ACCENTS, tuple(s.ACCENTS))
        self.assertEqual(EXPECTED_FEATURES, tuple(s.FEATURE_IDS))
        self.assertEqual(EXPECTED_DEFAULTS, dict(s.DEFAULTS))

    def test_path_is_settings_json_inside_state_dir(self):
        self.assertEqual(
            self.state / "settings.json",
            Path(self.settings.path(self.state)),
        )

    def test_missing_file_yields_defaults(self):
        self.assertFalse((self.state / "settings.json").exists())

        loaded = self.settings.load(self.state)
        view = self.settings.view(self.state)

        self.assertEqual(EXPECTED_DEFAULTS["theme"], loaded["theme"])
        self.assertEqual(EXPECTED_DEFAULTS["accent"], loaded["accent"])
        self.assertEqual([], loaded["favorite_projects"])
        self.assertEqual([], loaded["favorite_agents"])
        self.assertIsInstance(loaded["features"], dict)
        self.assertTrue(all(not value for value in loaded["features"].values()))
        self.assertEqual(set(EXPECTED_DEFAULTS), set(loaded))
        self.assertTrue(view["ok"])
        self.assertEqual(1, view["version"])
        self.assertEqual(loaded, view["settings"])

    def test_update_roundtrip_writes_versioned_file_and_loads_all_five_settings(self):
        patch = {
            "theme": "dark",
            "accent": "violet",
            "features": {"github": True, "mcp": False},
            "favorite_projects": ["projekt-a", "projekt-b"],
            "favorite_agents": [{"scope": "global", "name": "reviewer"}],
        }

        saved = self.settings.update(self.state, patch)

        self.assertTrue(saved["ok"])
        self.assertTrue(saved["stored"])
        self.assertEqual([], saved["ignored"])
        self.assertEqual(1, saved["version"])
        effective = saved["settings"]
        self.assertEqual("dark", effective["theme"])
        self.assertEqual("violet", effective["accent"])
        for feature in EXPECTED_FEATURES:
            self.assertIn(feature, effective["features"])
            self.assertIsInstance(effective["features"][feature], bool)
        self.assertTrue(effective["features"]["github"])
        self.assertFalse(effective["features"]["mcp"])
        self.assertEqual(["projekt-a", "projekt-b"], effective["favorite_projects"])
        self.assertEqual([{"scope": "global", "name": "reviewer"}],
                         effective["favorite_agents"])

        on_disk = self.raw()
        self.assertEqual(1, on_disk["version"])
        self.assertEqual(set(EXPECTED_DEFAULTS), set(on_disk["settings"]))
        self.assertEqual(effective, self.settings.load(self.state))
        self.assertEqual(effective, self.settings.view(self.state)["settings"])

    def test_partial_update_merges_without_clearing_other_settings(self):
        self.settings.update(self.state, {
            "theme": "dark",
            "accent": "teal",
            "features": {"github": True},
            "favorite_projects": ["alpha", "beta"],
            "favorite_agents": [{"scope": "global", "name": "coder"}],
        })
        before = self.settings.load(self.state)

        after = self.settings.update(self.state, {"theme": "auto"})["settings"]

        self.assertEqual({**before, "theme": "auto"}, after)
        self.assertEqual(after, self.settings.load(self.state))

    def test_update_without_valid_key_does_not_create_or_change_the_file(self):
        target = self.target()

        result = self.settings.update(self.state, {"unknown": 1, "theme2": "dark"})

        self.assertTrue(result["ok"])
        self.assertIn("unknown", result["ignored"])
        self.assertIn("theme2", result["ignored"])
        self.assertFalse(target.exists(), "Ohne gültigen Schlüssel darf nichts geschrieben werden")

        self.settings.update(self.state, {"theme": "dark"})
        before = target.read_bytes()
        self.settings.update(self.state, {"future_setting": {"x": 1}})
        self.assertEqual(before, target.read_bytes())

    def test_invalid_patch_keys_are_ignored_individually_and_keep_valid_ones(self):
        self.settings.update(self.state, {"accent": "green"})

        result = self.settings.update(self.state, {
            "theme": "dark",
            "accent": "neon",                       # nicht in ACCENTS
            "features": "kein objekt",
            "favorite_projects": ["alpha", "beta"],
        })

        self.assertTrue(result["ok"])
        self.assertIn("accent", result["ignored"])
        self.assertIn("features", result["ignored"])
        effective = result["settings"]
        self.assertEqual("dark", effective["theme"])
        self.assertEqual(["alpha", "beta"], effective["favorite_projects"])
        self.assertIn(effective["accent"], EXPECTED_ACCENTS)
        self.assertTrue(all(not value for value in effective["features"].values()))
        self.assertEqual(effective, self.settings.load(self.state))

    def test_invalid_stored_values_fall_back_per_key_without_losing_others(self):
        self.write_raw(json.dumps({
            "version": 1,
            "settings": {
                "theme": "neon",
                "accent": "blue",
                "features": {"github": True, "bogus": "keep-me"},
                "favorite_projects": ["good", "good"],
                "favorite_agents": [{"scope": "global", "name": "a"}],
            },
        }))

        effective = self.settings.view(self.state)["settings"]

        self.assertEqual("light", effective["theme"])
        self.assertEqual("blue", effective["accent"])
        self.assertTrue(effective["features"]["github"])
        self.assertNotIn("bogus", effective["features"])
        self.assertEqual(["good"], effective["favorite_projects"])
        self.assertEqual([{"scope": "global", "name": "a"}],
                         effective["favorite_agents"])

        updated = self.settings.update(self.state, {"theme": "auto"})
        on_disk = self.raw()
        self.assertEqual("auto", on_disk["settings"]["theme"])
        self.assertEqual("blue", on_disk["settings"]["accent"])
        self.assertEqual("keep-me", on_disk["settings"]["features"]["bogus"],
                         "Unbekannte Feature-IDs müssen im File erhalten bleiben")
        self.assertNotIn("bogus", updated["settings"]["features"])

    def test_newer_version_keys_are_ignored_in_view_but_preserved_on_write(self):
        self.write_raw(json.dumps({
            "version": 9,
            "settings": {
                "theme": "dark",
                "accent": "violet",
                "future_setting": {"nested": True},
                "features": {"github": True, "future_flag": True},
            },
        }))

        view = self.settings.view(self.state)
        self.assertTrue(view["ok"])
        self.assertEqual(9, view["version"])
        self.assertEqual("dark", view["settings"]["theme"])
        self.assertEqual("violet", view["settings"]["accent"])
        self.assertNotIn("future_setting", view["settings"])
        self.assertNotIn("future_flag", view["settings"]["features"])

        updated = self.settings.update(self.state, {"accent": "teal"})
        on_disk = self.raw()

        self.assertEqual(9, updated["version"])
        self.assertGreaterEqual(on_disk["version"], 9, "Version darf nicht sinken")
        self.assertEqual(9, on_disk["version"])
        self.assertEqual("teal", on_disk["settings"]["accent"])
        self.assertEqual({"nested": True}, on_disk["settings"]["future_setting"])
        self.assertTrue(on_disk["settings"]["features"]["future_flag"])
        self.assertEqual("teal", updated["settings"]["accent"])
        self.assertNotIn("future_setting", updated["settings"])

    def test_missing_version_is_treated_as_one(self):
        self.write_raw(json.dumps({"settings": {"theme": "dark"}}))

        view = self.settings.view(self.state)

        self.assertEqual(1, view["version"])
        self.assertEqual("dark", view["settings"]["theme"])
        self.assertEqual("dark", self.settings.load(self.state)["theme"])

    def test_corrupt_json_never_raises_and_recovers_on_next_update(self):
        payloads = [
            "",
            "{das ist kein json",
            "[]",
            '"nur text"',
            '{"settings": []}',
            '{"version": "x", "settings": {}}',
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.write_raw(payload)
                loaded = self.settings.load(self.state)
                view = self.settings.view(self.state)
                self.assertTrue(view["ok"])
                self.assertIsInstance(view["version"], int)
                self.assertEqual("light", loaded["theme"])
                self.assertEqual("blue", loaded["accent"])
                self.assertEqual([], loaded["favorite_projects"])

        saved = self.settings.update(self.state, {"theme": "dark"})
        self.assertEqual("dark", saved["settings"]["theme"])
        self.assertEqual("dark", self.settings.load(self.state)["theme"])

    def test_favorites_are_deduped_and_capped(self):
        projects = [f"p{i}" for i in range(205)] + ["p0"]
        agents = [{"scope": "global", "name": "a"},
                  {"scope": "global", "name": "a"}]
        agents += [{"scope": "global", "name": f"a{i}"} for i in range(205)]

        effective = self.settings.update(self.state, {
            "favorite_projects": projects,
            "favorite_agents": agents,
        })["settings"]

        self.assertEqual(200, len(effective["favorite_projects"]))
        self.assertEqual([f"p{i}" for i in range(200)],
                         effective["favorite_projects"])
        self.assertEqual(200, len(effective["favorite_agents"]))
        self.assertEqual({"scope": "global", "name": "a"},
                         effective["favorite_agents"][0])
        self.assertEqual(200, len({(item["scope"], item["name"])
                                   for item in effective["favorite_agents"]}))

    def test_invalid_favorite_entries_are_dropped_not_the_whole_list(self):
        # Vertrag: "invalid/empty dropped" — ungültige Einträge werden
        # verworfen, die gültigen bleiben erhalten.
        result = self.settings.update(self.state, {
            "favorite_projects": ["alpha", 7, "", "alpha", "beta", "x" * 201],
            "favorite_agents": [
                {"scope": "global", "name": "keep"},
                {"scope": "global", "name": "keep"},
                {"scope": "", "name": "drop"},
                {"scope": "proj", "name": ""},
                {"scope": 5, "name": "drop"},
                "kein dict",
            ],
        })

        effective = result["settings"]
        self.assertEqual(["alpha", "beta"], effective["favorite_projects"])
        self.assertEqual([{"scope": "global", "name": "keep"}],
                         effective["favorite_agents"])

    def test_whitelist_validation_is_exact(self):
        for bad in ("Dark", "dark ", "AUTO", "", None, 1, ["light"]):
            with self.subTest(theme=bad):
                effective = self.settings.update(self.state, {"theme": bad})["settings"]
                self.assertIn(effective["theme"], ("light", "dark", "auto"))

        for bad in ("Blue", "blue ", "neon", None, 3):
            with self.subTest(accent=bad):
                effective = self.settings.update(self.state, {"accent": bad})["settings"]
                self.assertIn(effective["accent"], EXPECTED_ACCENTS)

    def test_update_preserves_existing_file_mode(self):
        self.settings.update(self.state, {"theme": "dark"})
        target = self.target()
        os.chmod(target, 0o600)

        self.settings.update(self.state, {"accent": "teal"})

        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))

    def test_failed_atomic_write_keeps_the_original_file(self):
        self.assertIsNotNone(vibe_storage, "bin/vibe_storage.py fehlt")
        self.settings.update(self.state, {
            "theme": "dark",
            "favorite_projects": ["alter-wert"],
        })
        target = self.target()
        before = target.read_bytes()
        mode_before = stat.S_IMODE(target.stat().st_mode)

        with mock.patch("vibe_storage.os.replace", side_effect=OSError(28, "Kein Platz")):
            try:
                self.settings.update(self.state, {"theme": "auto"})
            except OSError:
                pass  # Fehlerweiterleitung ist erlaubt; die Datei muss intact bleiben.

        self.assertEqual(before, target.read_bytes())
        self.assertEqual(mode_before, stat.S_IMODE(target.stat().st_mode))
        self.assertEqual([], [p.name for p in self.state.iterdir()
                              if p.name.startswith(".vibe-")])

    def test_concurrent_partial_updates_do_not_lose_each_other(self):
        """Ein konkurrierendes Teil-Update darf nicht still überschrieben werden.

        Der Wrapper lässt genau einmal — mitten im äußeren Schreibvorgang —
        ein echtes zweites Update laufen. Ohne optimistische Sperre liest der
        äußere Aufruf den alten Stand und überschreibt die Änderung des
        inneren Aufrufs (lost update). Mit erwarteter Prüfsumme und Retry
        müssen beide Teiländerungen im Ergebnis stehen.
        """
        settings = self.settings
        original_write = settings.vibe_storage.write_text
        injected = False
        attempts = 0

        def competing_write(*args, **kwargs):
            nonlocal injected, attempts
            attempts += 1
            if not injected:
                injected = True
                settings.update(self.state, {"theme": "dark"})
            return original_write(*args, **kwargs)

        with mock.patch.object(settings.vibe_storage, "write_text",
                               side_effect=competing_write):
            outer = settings.update(self.state, {"accent": "teal"})

        self.assertTrue(outer["ok"])
        self.assertGreaterEqual(
            attempts, 2, "Die konkurrierende Änderung wurde nicht ausgelöst")
        effective = settings.load(self.state)
        self.assertEqual("dark", effective["theme"],
                         "Lost update: das konkurrierende Theme ging verloren")
        self.assertEqual("teal", effective["accent"])
        self.assertEqual(effective, settings.view(self.state)["settings"])


class SettingsApiTest(unittest.TestCase):
    """Echter Dashboard-Prozess: /api/settings, Auth, Neustart und HTML-Meta."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.port = free_port()
        cls.restart_port = free_port()
        cls.env = env_support.isolated_environ(
            VIBE=str(cls.root),
            VIBE_NO_CONTAINER="1",
            VIBE_UI_PORT=str(cls.port),
            VIBE_OPENCODE_PORT=str(free_port()),
            VIBE_STATE=str(cls.state),
            VIBE_INSTALL=str(cls.root),
            VIBE_RUNTIME=str(cls.logs),
            VIBE_AGENTS_DIR=str(cls.home / ".config" / "opencode" / "agents"),
            VIBE_CONFIG_FILE=str(cls.home / ".config" / "vibe" / "config.json"),
            VIBE_STORAGE_LOCK_DIR=str(cls.root / "locks"),
            VIBE_SANDBOX_ACTIVE=None,
            HOME=str(cls.home),
            PYTHONDONTWRITEBYTECODE="1",
        )
        cls.start_server()

    @classmethod
    def tearDownClass(cls):
        cls.stop_server()
        cls.tmp.cleanup()

    @classmethod
    def server_log(cls):
        try:
            return cls.log_path.read_text(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            return ""

    @classmethod
    def start_server(cls, port=None):
        if port is not None:
            cls.port = port
        env = dict(cls.env)
        env["VIBE_UI_PORT"] = str(cls.port)
        token_file = cls.logs / "web.token"
        token_file.unlink(missing_ok=True)
        cls.log_path = cls.root / f"server-{cls.port}.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.log_file, stderr=subprocess.STDOUT, text=True,
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError("vibe-web wurde vorzeitig beendet:\n" + cls.server_log())
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar:\n" + cls.server_log())
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def stop_server(cls):
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        log_file = getattr(cls, "log_file", None)
        if log_file is not None:
            log_file.close()
            cls.log_file = None

    def setUp(self):
        # Jeder Fall beginnt ohne Datei; der Standard ist damit eindeutig.
        (self.state / "settings.json").unlink(missing_ok=True)

    def request(self, method, path, body=None, token=USE_TOKEN, raw=None):
        if token is USE_TOKEN:
            token = self.token
        if raw is not None:
            data = raw
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            data = None
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Token"] = token
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            return (response.status, response.read().decode("utf-8", "replace"),
                    dict(response.getheaders()))
        finally:
            conn.close()

    def test_get_settings_requires_auth(self):
        status, text, _ = self.request("GET", "/api/settings", token=None)

        self.assertEqual(403, status, text)
        self.assertEqual("unauthorized", json.loads(text)["error"]["code"])

    def test_post_settings_requires_auth(self):
        status, text, _ = self.request(
            "POST", "/api/settings", {"theme": "dark"}, token=None)

        self.assertEqual(403, status, text)
        self.assertEqual("unauthorized", json.loads(text)["error"]["code"])
        self.assertFalse((self.state / "settings.json").exists())

    def test_get_settings_defaults_when_no_file_exists(self):
        status, text, _ = self.request("GET", "/api/settings")

        self.assertEqual(200, status, text)
        view = json.loads(text)
        self.assertTrue(view["ok"])
        self.assertIsInstance(view["version"], int)
        self.assertEqual("light", view["settings"]["theme"])
        self.assertEqual("blue", view["settings"]["accent"])
        self.assertEqual([], view["settings"]["favorite_projects"])
        self.assertEqual([], view["settings"]["favorite_agents"])
        self.assertIsInstance(view["settings"]["features"], dict)

    def test_post_settings_persists_all_settings_and_get_returns_them(self):
        patch = {
            "theme": "dark",
            "accent": "teal",
            "features": {"github": True, "sandbox": False},
            "favorite_projects": ["alpha", "beta"],
            "favorite_agents": [{"scope": "global", "name": "reviewer"}],
        }

        status, text, _ = self.request("POST", "/api/settings", patch)
        self.assertEqual(200, status, text)
        saved = json.loads(text)
        self.assertTrue(saved["ok"], text)
        self.assertTrue(saved["stored"], text)
        self.assertIn("ignored", saved)
        self.assertEqual("dark", saved["settings"]["theme"])
        self.assertEqual("teal", saved["settings"]["accent"])
        self.assertEqual(["alpha", "beta"], saved["settings"]["favorite_projects"])
        self.assertTrue((self.state / "settings.json").exists())

        status, text, _ = self.request("GET", "/api/settings")
        self.assertEqual(200, status, text)
        view = json.loads(text)
        self.assertEqual(saved["settings"], view["settings"])
        self.assertEqual(saved["version"], view["version"])
        self.assertTrue(view["stored"])

    def test_post_settings_rejects_non_object_body(self):
        for raw in (b"[1, 2, 3]", b'"nur text"', b"42", b"{kein json"):
            with self.subTest(raw=raw):
                status, text, _ = self.request(
                    "POST", "/api/settings", raw=raw)

                self.assertEqual(400, status, text)
                self.assertFalse(json.loads(text)["ok"], text)

    def test_settings_survive_a_server_restart_with_same_state_dir(self):
        patch = {
            "theme": "auto",
            "accent": "violet",
            "features": {"github": True},
            "favorite_projects": ["projekt-nach-update"],
            "favorite_agents": [{"scope": "global", "name": "agent-nach-update"}],
        }
        status, text, _ = self.request("POST", "/api/settings", patch)
        self.assertEqual(200, status, text)
        expected = json.loads(text)["settings"]
        self.assertTrue((self.state / "settings.json").exists())

        self.stop_server()
        self.start_server(port=self.restart_port)

        status, text, _ = self.request("GET", "/api/settings")
        self.assertEqual(200, status, text)
        view = json.loads(text)
        self.assertTrue(view["stored"])
        self.assertEqual(expected, view["settings"],
                         "Nach Update/Neustart müssen alle Einstellungen erhalten sein")

    def test_index_embeds_escaped_settings_meta_classic_does_not(self):
        patch = {
            "theme": "dark",
            "accent": "pink",
            "favorite_projects": ['<script>alert("x")</script>&'],
            "favorite_agents": [{"scope": 'projekt & <x>', "name": 'agent "q"'}],
        }
        status, text, _ = self.request("POST", "/api/settings", patch)
        self.assertEqual(200, status, text)
        saved = json.loads(text)["settings"]

        status, page_html, _ = self.request("GET", "/", token=None)
        self.assertEqual(200, status, page_html[:400])
        self.assertNotIn("__VIBE_SETTINGS__", page_html)
        match = re.search(
            r'<meta\s+name=["\']vibe-settings["\']\s+'
            r'content=["\'](.*?)["\']\s*/?>',
            page_html, re.DOTALL)
        self.assertIsNotNone(match, "Nova-Meta fehlt: " + page_html[:800])
        content = match.group(1)
        self.assertIn("&quot;", content,
                      "JSON muss für ein HTML-Attribut escapet sein")
        self.assertNotIn("<script>", content)
        decoded = json.loads(html.unescape(content))
        embedded = decoded.get("settings", decoded) \
            if isinstance(decoded, dict) else decoded
        self.assertEqual(saved, embedded)

        # Die klassische Shell bleibt unverändert: kein Settings-Meta, kein
        # Platzhalter und damit keine GH-117-Abhängigkeit in classic.html.
        status, classic_html, _ = self.request("GET", "/classic", token=None)
        self.assertEqual(200, status, classic_html[:400])
        self.assertNotIn("vibe-settings", classic_html)
        self.assertNotIn("__VIBE_SETTINGS__", classic_html)

    def test_templates_declare_the_settings_placeholder(self):
        self.assertTrue(INDEX_HTML.is_file(), f"{INDEX_HTML} fehlt")
        index_source = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn("__VIBE_SETTINGS__", index_source)
        self.assertIn('name="vibe-settings"', index_source)

        # Vertrag der unveränderten klassischen Shell (byte-identisch zum
        # Startstand): GH-117 darf dort weder Meta noch Platzhalter einbringen.
        self.assertTrue(CLASSIC_HTML.is_file(), f"{CLASSIC_HTML} fehlt")
        classic_source = CLASSIC_HTML.read_text(encoding="utf-8")
        self.assertNotIn("__VIBE_SETTINGS__", classic_source)
        self.assertNotIn("vibe-settings", classic_source)


if __name__ == "__main__":
    unittest.main()
