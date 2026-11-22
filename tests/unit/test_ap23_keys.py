"""Unabhängige Unit-Tests für das Arbeitspaket AP23 „Key Management“ (``vibe keys``).

Gemäß der Regel „Independent Test-Agent“ (Vibe-Working-Orders) wurden die Fälle
BEFORE-Implementierung abgeleitet aus Arbeitspaket und Konzept
(``docs/features/AP23.md``; ``TICKETS.md`` Zeilen 1154–1157). Dies ist der rote
Start: ``bin/vibe_keys.py`` existiert noch nicht, die Tests sind also
erwartungsgemäß fehlschlägig.

Vertragsfälle (25, aus ``docs/features/AP23.md``): AES-GCM-Vektoren, Vault
(``keys.json``), select/list/remove sowie Harness-Sync (opencode ``auth.json``,
Pi nicht unterstützt) und das CLI ``main(argv)``. Einzelne Testklasse
``TestAP23Keys``; je Test eigene ``tempfile.TemporaryDirectory`` (setUp/tearDown),
``state = tmp/state`` und ``environ={"VIBE_KEYS_VAULT_KEY": base64(os.urandom(32))}``
wird explizit an die Klassen-Funktionen übergeben. Nur Python-APIs; keine
externen Prozesse, kein Netzwerk; Fake-Secrets wie
``b"ghp_test_secret_for_ap23_0000000001"``.
"""
import base64
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bin"))

import vibe_keys  # noqa: E402


class TestAP23Keys(unittest.TestCase):
    """Vertragsfälle aus ``docs/features/AP23.md`` für ``bin/vibe_keys.py``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.vault = self.state / "keys.json"
        self.env = {"VIBE_KEYS_VAULT_KEY": base64.b64encode(os.urandom(32)).decode()}
        self.secret = b"ghp_test_secret_for_ap23_0000000001"

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _text(value):
        """Wandelt bytes nach str (Masken-Prüfung auf bytes- und str-Wert)."""
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return str(value)

    # ------------------------------------------------------------------ A) AES-GCM

    def test_aes_128_gcm_empty_vector(self):
        key = bytes(16)
        nonce = bytes(12)
        ciphertext, tag = vibe_keys.aes_gcm_encrypt(key, nonce, b"")
        self.assertEqual(tag, bytes.fromhex("58e2fccefa7e3061367f1d57a4e7455a"))
        self.assertEqual(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, tag), b"")

    def test_aes_128_gcm_one_block_vector(self):
        key = bytes(16)
        nonce = bytes(12)
        plaintext = bytes(16)
        ciphertext, tag = vibe_keys.aes_gcm_encrypt(key, nonce, plaintext)
        self.assertEqual(ciphertext, bytes.fromhex("0388dace60b6a392f328c2b971b2fe78"))
        self.assertEqual(tag, bytes.fromhex("ab6e47d42cec13bdf53a67b21257bddf"))
        self.assertEqual(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, tag), plaintext)

    def test_aes_gcm_roundtrip_256(self):
        key = os.urandom(32)
        for payload in (b"", b"ghp_abc123", os.urandom(1024)):
            nonce = os.urandom(12)
            ciphertext, tag = vibe_keys.aes_gcm_encrypt(key, nonce, payload)
            self.assertEqual(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, tag), payload)

    def test_aes_gcm_tamper_detected(self):
        key = os.urandom(32)
        nonce = os.urandom(12)
        payload = b"integrity-check-payload"
        ciphertext, tag = vibe_keys.aes_gcm_encrypt(key, nonce, payload)
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0x01
        self.assertIsNone(vibe_keys.aes_gcm_decrypt(key, nonce, bytes(tampered), tag))
        wrong_tag = bytes([tag[0] ^ 0x01]) + tag[1:]
        self.assertIsNone(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, wrong_tag))
        self.assertIsNone(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, bytes(len(tag))))

    def test_aes_gcm_aad_bound(self):
        key = os.urandom(32)
        nonce = os.urandom(12)
        payload = b"aad-bound-payload"
        ciphertext, tag = vibe_keys.aes_gcm_encrypt(key, nonce, payload, aad=b"ctx-1")
        self.assertEqual(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, tag, aad=b"ctx-1"), payload)
        self.assertIsNone(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext, tag, aad=b"ctx-2"))
        ciphertext2, tag2 = vibe_keys.aes_gcm_encrypt(key, nonce, payload)
        self.assertEqual(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext2, tag2, aad=b""), payload)
        self.assertIsNone(vibe_keys.aes_gcm_decrypt(key, nonce, ciphertext2, tag2, aad=b"ctx-1"))

    # ------------------------------------------------------------------ B) Vault / Einträge

    def test_vault_key_env(self):
        raw = os.urandom(32)
        env = {"VIBE_KEYS_VAULT_KEY": base64.b64encode(raw).decode()}
        key = vibe_keys.vault_key(environ=env)
        self.assertEqual(len(key), 32)
        self.assertEqual(key, raw)

    def test_vault_key_missing(self):
        with self.assertRaises(Exception) as ctx:
            vibe_keys.vault_key(environ={})
        self.assertIn("VIBE_KEYS_VAULT_KEY", str(ctx.exception))

    def test_add_entry_persists_and_encrypts(self):
        entry = vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        self.assertEqual(entry["name"], "n")
        self.assertEqual(entry["provider"], "p")
        self.assertTrue(entry["id"])
        vault_text = self.vault.read_text()
        json.loads(vault_text)  # muss gültiges JSON sein
        self.assertNotIn(self.secret.decode(), vault_text)
        self.assertEqual(stat.S_IMODE(os.stat(self.vault).st_mode), 0o600)

    def test_add_entry_requires_key(self):
        with self.assertRaises(Exception):
            vibe_keys.add_entry(self.state, "n", "p", self.secret, environ={})

    def test_add_entry_duplicate_rejected(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        with self.assertRaises(Exception):
            vibe_keys.add_entry(self.state, "n", "p2", b"another-secret-value-12345", environ=self.env)

    def test_list_entries_masks(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.add_entry(self.state, "m", "q", b"ab", environ=self.env)
        entries = vibe_keys.list_entries(self.state, environ=self.env)
        by_name = {e["name"]: e for e in entries}
        self.assertEqual(set(by_name), {"n", "m"})
        for name, value, provider in (("n", self.secret, "p"), ("m", b"ab", "q")):
            entry = by_name[name]
            self.assertEqual(entry["provider"], provider)
            masked = self._text(entry["masked"])
            plain = self._text(value)
            self.assertNotEqual(masked, plain)
            self.assertIn(str(len(value)), masked)
            self.assertIn(self._text(value[:3]), masked)

    def test_list_entries_empty_ok(self):
        self.assertEqual(vibe_keys.list_entries(self.state, environ=self.env), [])
        self.assertEqual(vibe_keys.list_entries(self.state), [])

    def test_select_and_selected_entry(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        selected = vibe_keys.select_entry(self.state, "n", environ=self.env)
        self.assertEqual(selected["name"], "n")
        self.assertIsNotNone(vibe_keys.selected_entry(self.state))
        self.assertEqual(vibe_keys.selected_entry(self.state)["name"], "n")

    def test_select_unknown_rejected(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        with self.assertRaises(Exception):
            vibe_keys.select_entry(self.state, "missing", environ=self.env)

    def test_remove_entry_clears_selection(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        ok, message = vibe_keys.remove_entry(self.state, "n", environ=self.env)
        self.assertTrue(ok)
        self.assertIsNone(vibe_keys.selected_entry(self.state))
        self.assertEqual(vibe_keys.list_entries(self.state, environ=self.env), [])

    def test_remove_unknown(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        ok, message = vibe_keys.remove_entry(self.state, "missing", environ=self.env)
        self.assertFalse(ok)

    # ------------------------------------------------------------------ C) Harness-Sync (opencode)

    def _write_auth(self, auth_path, data):
        auth_path = Path(auth_path)
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(json.dumps(data))

    def _read_auth(self, auth_path):
        return json.loads(Path(auth_path).read_text())

    def test_sync_opencode_writes_auth_json(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        auth_path = self.tmp / "opencode" / "auth.json"
        ok, message = vibe_keys.sync(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        data = self._read_auth(auth_path)
        self.assertIn("p", data)
        self.assertIn(self._text(self.secret), json.dumps(data["p"]))
        self.assertFalse(any(".tmp" in f.name for f in auth_path.parent.iterdir()))

    def test_sync_opencode_preserves_other_providers(self):
        auth_path = self.tmp / "opencode2" / "auth.json"
        self._write_auth(auth_path, {"other": {"key": "other-key"}})
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        ok, message = vibe_keys.sync(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        data = self._read_auth(auth_path)
        self.assertIn("p", data)
        self.assertIn("other", data)

    def test_sync_empty_selection_noop(self):
        auth_path = self.tmp / "opencode3" / "auth.json"
        ok, message = vibe_keys.sync(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        self.assertFalse(auth_path.exists())

    def test_sync_pi_unsupported(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        ok, message = vibe_keys.sync(self.state, "pi", environ=self.env, auth_path=self.tmp / "pi" / "auth.json")
        self.assertFalse(ok)
        self.assertIn("pi", str(message).lower())

    def test_sync_requires_vault_key(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        ok, message = vibe_keys.sync(self.state, "opencode", environ={}, auth_path=self.tmp / "opencode4" / "auth.json")
        self.assertFalse(ok)
        self.assertIn("vault", str(message).lower())

    def test_sync_reset_removes_provider(self):
        auth_path = self.tmp / "opencode5" / "auth.json"
        self._write_auth(auth_path, {"other": {"key": "other-key"}})
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.add_entry(self.state, "m", "q", b"other-secret-12345", environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        ok, _ = vibe_keys.sync(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        self.assertIn("p", self._read_auth(auth_path))
        ok, _ = vibe_keys.sync_reset(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        data = self._read_auth(auth_path)
        self.assertNotIn("p", data)
        self.assertIn("other", data)
        names = {e["name"] for e in vibe_keys.list_entries(self.state, environ=self.env)}
        self.assertIn("m", names)

    def test_sync_reset_without_selection(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        auth_path = self.tmp / "opencode6" / "auth.json"
        self._write_auth(auth_path, {"other": {"key": "other-key"}})
        ok, _ = vibe_keys.sync_reset(self.state, "opencode", environ=self.env, auth_path=auth_path)
        self.assertTrue(ok)
        self.assertIn("other", self._read_auth(auth_path))

    # ------------------------------------------------------------------ D) CLI

    def test_cli_sync_and_reset(self):
        vibe_keys.add_entry(self.state, "n", "p", self.secret, environ=self.env)
        vibe_keys.select_entry(self.state, "n", environ=self.env)
        auth_path = self.tmp / "opencode7" / "auth.json"
        rc = vibe_keys.main(["sync", "--state", str(self.state), "--harness", "opencode", "--auth-path", str(auth_path)])
        self.assertEqual(rc, 0)
        self.assertIn("p", self._read_auth(auth_path))
        rc = vibe_keys.main(["sync-reset", "--state", str(self.state), "--harness", "opencode", "--auth-path", str(auth_path)])
        self.assertEqual(rc, 0)
        self.assertNotIn("p", self._read_auth(auth_path))

    def test_cli_sync_no_selection(self):
        state2 = self.tmp / "state2"
        state2.mkdir()
        auth_path = self.tmp / "opencode8" / "auth.json"
        rc = vibe_keys.main(["sync", "--state", str(state2), "--harness", "opencode", "--auth-path", str(auth_path)])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
