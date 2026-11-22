#!/usr/bin/env python3
"""AP23 – lokales Key Management für vibe (nur Python-Standardbibliothek).

Der Vault liegt unter ``<state>/keys.json`` und enthält nur AES-256-GCM-
Chiffretexte; der 32-Byte-Vault-Key kommt aus ``VIBE_KEYS_VAULT_KEY`` (Base64)
oder – im regulären CLI-Pfad – aus dem OS-Keyring (Linux: secret-tool).
Secrets landen nie in Logs, nie im Vault-Klartext und bleiben im Harness nur
für die Dauer eines Agentenlaufs (Least Privilege).

Die Auswahl für den nächsten Lauf wird zusätzlich als 0600-geschützte
Sitzungsdatei ``<state>/selected.json`` abgelegt: Der ``select`` entschlüsselt
das Secret einmalig mit dem Vault-Key, ``sync`` kann es danach auch dann in die
Harness-Config übernehmen, wenn der Läufer die VIBE_*-Umgebung bereinigt hat.
``sync-reset`` entfernt diese Datei wieder. Ist ein Vault-Key verfügbar, wird
bei ``sync`` grundsätzlich frisch aus dem Vault entschlüsselt.
"""
import argparse
import base64
import binascii
import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from vibe_packages import write_text_atomic

VAULT_NAME = "keys.json"
SESSION_NAME = "selected.json"
ENV_KEY = "VIBE_KEYS_VAULT_KEY"
KEYRING_SERVICE = "vibe-keys"
KEYRING_USER = "vibe-key-manager"
DEFAULT_AUTH_PATH = "~/.local/share/opencode/auth.json"
SUPPORTED_HARNESSES = ("opencode",)
FILE_MODE = 0o600
KEY_LENGTH = 32
NONCE_LENGTH = 12


# ---------------------------------------------------------------------------
# AES (FIPS-197) – rein rechnerisch, ohne externe Abhängigkeit
# ---------------------------------------------------------------------------

def _gf_mul(left, right):
    """Multiplikation zweier Bytes in GF(2^8) mit dem AES-Polynom."""
    result = 0
    for _ in range(8):
        if right & 1:
            result ^= left
        carry = left & 0x80
        left = (left << 1) & 0xFF
        if carry:
            left ^= 0x1B
        right >>= 1
    return result


def _gf_power(value, exponent):
    """Potenz in GF(2^8), für die Inversion im S-Box-Aufbau."""
    result = 1
    for _ in range(exponent):
        result = _gf_mul(result, value)
    return result


def _build_sbox():
    """Erzeugt die AES-S-Box aus Inversion und affiner Transformation."""
    box = bytearray(256)
    for value in range(256):
        inverse = _gf_power(value, 254) if value else 0
        transformed = inverse
        for shift in (1, 2, 3, 4):
            transformed ^= ((inverse << shift) | (inverse >> (8 - shift))) & 0xFF
        box[value] = transformed ^ 0x63
    return bytes(box)


S_BOX = _build_sbox()


def _expand_key(key):
    """Erweitert einen 128/192/256-Bit-Key auf Rundenschlüssel."""
    if len(key) not in (16, 24, 32):
        raise ValueError("AES-Schlüssel muss 16, 24 oder 32 Bytes lang sein")
    words = [list(key[offset:offset + 4]) for offset in range(0, len(key), 4)]
    columns = len(words)
    rounds = columns + 6
    rcon = 1
    for index in range(columns, 4 * (rounds + 1)):
        temp = words[index - 1][:]
        if index % columns == 0:
            temp = [S_BOX[byte] for byte in temp[1:] + temp[:1]]
            temp[0] ^= rcon
            rcon = _gf_mul(rcon, 2)
        elif columns > 6 and index % columns == 4:
            temp = [S_BOX[byte] for byte in temp]
        words.append([words[index - columns][pos] ^ temp[pos] for pos in range(4)])
    return [bytes(byte for word in words[round * 4:round * 4 + 4] for byte in word)
            for round in range(rounds + 1)]


def _shift_rows(state):
    """Dreht die Zeilen des Spalten-major-Zustands um 0..3 Positionen."""
    shifted = bytearray(16)
    for row in range(4):
        for column in range(4):
            shifted[row + 4 * column] = state[row + 4 * ((column + row) % 4)]
    return shifted


def _mix_columns(state):
    """Mischt jede Zustandsspalte mit der festen AES-Matrix."""
    mixed = bytearray(16)
    for column in range(4):
        pos = 4 * column
        a0, a1, a2, a3 = state[pos:pos + 4]
        mixed[pos] = _gf_mul(a0, 2) ^ _gf_mul(a1, 3) ^ a2 ^ a3
        mixed[pos + 1] = a0 ^ _gf_mul(a1, 2) ^ _gf_mul(a2, 3) ^ a3
        mixed[pos + 2] = a0 ^ a1 ^ _gf_mul(a2, 2) ^ _gf_mul(a3, 3)
        mixed[pos + 3] = _gf_mul(a0, 3) ^ a1 ^ a2 ^ _gf_mul(a3, 2)
    return mixed


def _encrypt_block(round_keys, block):
    """Verschlüsselt genau einen 16-Byte-Block mit AES."""
    state = bytearray(a ^ b for a, b in zip(block, round_keys[0]))
    for round_key in round_keys[1:-1]:
        state = bytearray(S_BOX[byte] for byte in state)
        state = _mix_columns(_shift_rows(state))
        state = bytearray(a ^ b for a, b in zip(state, round_key))
    state = bytearray(S_BOX[byte] for byte in state)
    state = _shift_rows(state)
    return bytes(a ^ b for a, b in zip(state, round_keys[-1]))


# ---------------------------------------------------------------------------
# GCM (NIST SP 800-38D)
# ---------------------------------------------------------------------------

def _gf128_mul(left, right):
    """Blockmultiplikation im GCM-Körper GF(2^128) (bitreflektiert)."""
    result = 0
    value = right
    reducer = 0xE1000000000000000000000000000000
    for bit in range(127, -1, -1):
        if (left >> bit) & 1:
            result ^= value
        value = (value >> 1) ^ reducer if value & 1 else value >> 1
    return result


def _ghash(hash_key, data):
    """GHASH über eine Folge von 16-Byte-Blöcken; liefert 16 Bytes."""
    state = 0
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16].ljust(16, b"\x00")
        state = _gf128_mul(state ^ int.from_bytes(block, "big"), hash_key)
    return state.to_bytes(16, "big")


def _pad16(data):
    """Füllt Daten auf ein Vielfaches von 16 Bytes auf."""
    remainder = len(data) % 16
    return bytes(16 - remainder) if remainder else b""


def _increment32(counter):
    """Erhöht nur das niedrigste 32-Bit-Wort eines GCM-Zählers."""
    value = int.from_bytes(counter, "big") if isinstance(counter, (bytes, bytearray)) else counter
    return (value & ~0xFFFFFFFF) | ((value + 1) & 0xFFFFFFFF)


def _gctr(round_keys, initial_counter, data):
    """GCM-Zählermodus: XOR der Daten mit E(K, INC32(Zähler))."""
    output = bytearray()
    counter = int.from_bytes(initial_counter, "big")
    for offset in range(0, len(data), 16):
        stream = _encrypt_block(round_keys, counter.to_bytes(16, "big"))
        chunk = data[offset:offset + 16]
        output.extend(a ^ b for a, b in zip(chunk, stream))
        counter = _increment32(counter)
    return bytes(output)


def _gcm_parts(key, nonce):
    """Liefert Rundenschlüssel, GHASH-Key und den Initialisierungsblock J0."""
    if not nonce:
        raise ValueError("GCM-Nonce darf nicht leer sein")
    round_keys = _expand_key(key)
    hash_block = _encrypt_block(round_keys, bytes(16))
    hash_key = int.from_bytes(hash_block, "big")
    if len(nonce) == NONCE_LENGTH:
        j0 = nonce + b"\x00\x00\x00\x01"
    else:
        j0 = _ghash(hash_key, _pad16(nonce) + bytes(8) + len(nonce).to_bytes(8, "big"))
    return round_keys, hash_block, j0


def _gcm_tag(round_keys, hash_block, j0, ciphertext, aad):
    """Berechnet das 16-Byte-Authentifizierungstag über AAD und Chiffretext."""
    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    authenticated = _ghash(int.from_bytes(hash_block, "big"),
                           aad + _pad16(aad) + ciphertext + _pad16(ciphertext) + lengths)
    return _gctr(round_keys, j0, authenticated)


def aes_gcm_encrypt(key, nonce, plaintext, aad=b""):
    """Verschlüsselt ``plaintext`` mit AES-GCM; liefert (Chiffretext, Tag)."""
    round_keys, hash_block, j0 = _gcm_parts(bytes(key), bytes(nonce))
    plaintext = bytes(plaintext)
    aad = bytes(aad)
    ciphertext = _gctr(round_keys, _increment32(j0).to_bytes(16, "big"), plaintext)
    return ciphertext, _gcm_tag(round_keys, hash_block, j0, ciphertext, aad)


def aes_gcm_decrypt(key, nonce, ciphertext, tag, aad=b""):
    """Prüft das GCM-Tag und entschlüsselt; bei Manipulation ``None``."""
    round_keys, hash_block, j0 = _gcm_parts(bytes(key), bytes(nonce))
    ciphertext = bytes(ciphertext)
    expected = _gcm_tag(round_keys, hash_block, j0, ciphertext, bytes(aad))
    if not hmac.compare_digest(expected, bytes(tag)):
        return None
    return _gctr(round_keys, _increment32(j0).to_bytes(16, "big"), ciphertext)


# ---------------------------------------------------------------------------
# Vault-Schlüssel und Datei-Zugriff
# ---------------------------------------------------------------------------

def _decode_key(raw, source):
    """Dekodiert einen Base64-Schlüssel und erzwingt genau 32 Bytes."""
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="replace").strip()
    try:
        key = base64.b64decode(str(raw).strip(), validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError(f"{source} enthält keinen gültigen Base64-Schlüssel: {error}") from error
    if len(key) != KEY_LENGTH:
        raise ValueError(f"{source} muss genau {KEY_LENGTH} Bytes enthalten")
    return key


def _keyring_runner(command):
    """Führt secret-tool mit harter Zeitgrenze und ohne stdin aus."""
    return subprocess.run(command, capture_output=True, text=True, check=False,
                          timeout=5, stdin=subprocess.DEVNULL)


def vault_key(environ=None, runner=None):
    """Liefert den 32-Byte-Vault-Key aus Umgebung oder OS-Keyring.

    Ein explizit übergebenes ``environ`` ist eine Sandbox-Grenze: ohne
    injizierten ``runner`` werden dort keine externen Prozesse gestartet.
    """
    env = os.environ if environ is None else environ
    raw = env.get(ENV_KEY)
    if raw:
        return _decode_key(raw, ENV_KEY)
    if environ is not None and runner is None:
        raise ValueError(f"{ENV_KEY} nicht gesetzt; Vault-Schlüssel nicht verfügbar")
    if not sys.platform.startswith("linux"):
        raise ValueError(f"{ENV_KEY} nicht gesetzt; OS-Keyring nicht verfügbar")
    if not shutil.which("secret-tool"):
        raise ValueError(f"{ENV_KEY} nicht gesetzt; secret-tool nicht verfügbar")
    command = ["secret-tool", "lookup", "service", KEYRING_SERVICE,
               "user", KEYRING_USER]
    try:
        result = (runner or _keyring_runner)(command)
        raw = result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"OS-Keyring nicht lesbar: {error}") from error
    if not raw:
        raise ValueError(f"{ENV_KEY} nicht gesetzt; OS-Keyring liefert keinen Schlüssel")
    return _decode_key(raw, "OS-Keyring")


def _vault_path(state_dir):
    return Path(state_dir) / VAULT_NAME


def _session_path(state_dir):
    return Path(state_dir) / SESSION_NAME


def _empty_vault():
    return {"version": 1, "entries": [], "selected": None}


def _read_json(path, default):
    """Liest JSON; fehlt die Datei, gilt ``default`` als leerer Stand."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except OSError as error:
        raise ValueError(f"{Path(path).name} kann nicht gelesen werden: {error}") from error
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{Path(path).name} enthält kein gültiges JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{Path(path).name} muss ein JSON-Objekt enthalten")
    return data


def _write_private_json(path, data):
    """Schreibt JSON atomar und anschließend ausschließlich mit 0600."""
    path = Path(path)
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    os.chmod(path, FILE_MODE)
    # Best effort: Elternverzeichnis 0700. Auf FUSE/NTFS können Unix-Rechte
    # wirkungslos sein; ein OSError ist dort kein Schreibfehler (wie in
    # vibe_packages.py).
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _read_vault(state_dir):
    vault = _read_json(_vault_path(state_dir), _empty_vault())
    vault.setdefault("entries", [])
    vault.setdefault("selected", None)
    if not isinstance(vault["entries"], list):
        raise ValueError("keys.json: entries muss eine Liste sein")
    return vault


def _write_vault(state_dir, vault):
    _write_private_json(_vault_path(state_dir), vault)


def _find_entry(state_dir, name):
    """Liefert den vollständigen Vault-Eintrag einschließlich Chiffretext."""
    vault = _read_vault(state_dir)
    return next((item for item in vault["entries"] if item["name"] == name), None)


def _aad(name, provider):
    """Bindet Name und Provider kryptografisch an den Geheimtext."""
    return f"vibe-keys:v1:{name}:{provider}".encode("utf-8")


def _encrypted_bytes(entry, field):
    return base64.b64decode(entry[field], validate=True)


def _decrypt_entry(entry, key):
    """Entschlüsselt einen Vault-Eintrag; bei Manipulation ``None``."""
    if key is None:
        return None
    return aes_gcm_decrypt(key, _encrypted_bytes(entry, "nonce"),
                           _encrypted_bytes(entry, "ciphertext"),
                           _encrypted_bytes(entry, "tag"),
                           aad=_aad(entry["name"], entry["provider"]))


def _public_entry(entry):
    """Metadaten ohne Schlüsselmaterial für die Aufrufer."""
    return {"id": entry.get("id", ""), "name": entry["name"],
            "provider": entry["provider"], "created": entry.get("created", "")}


def _mask(secret, entry):
    """Zeigt nur die ersten drei Zeichen und die Länge, nie den Wert."""
    length = len(secret) if secret is not None else len(_encrypted_bytes(entry, "ciphertext"))
    prefix = (secret or b"")[:3].decode("utf-8", errors="replace") or "???"
    return f"{prefix}… ({length} Zeichen)"


def _try_vault_key(environ, runner):
    """Liefert den Key oder ``None``; der Aufrufer entscheidet über den Fehler."""
    try:
        return vault_key(environ=environ, runner=runner)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Vault-Einträge
# ---------------------------------------------------------------------------

def add_entry(state_dir, name, provider, value, environ=None, runner=None):
    """Speichert ein Secret verschlüsselt im Vault; Name muss eindeutig sein."""
    name = str(name).strip()
    provider = str(provider).strip() or "generic"
    if not name:
        raise ValueError("Der Name darf nicht leer sein")
    vault = _read_vault(state_dir)
    if any(entry["name"] == name for entry in vault["entries"]):
        raise ValueError(f"Eintrag '{name}' existiert bereits")
    secret = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    key = vault_key(environ=environ, runner=runner)
    nonce = secrets.token_bytes(NONCE_LENGTH)
    ciphertext, tag = aes_gcm_encrypt(key, nonce, secret, aad=_aad(name, provider))
    entry = {
        "id": uuid.uuid4().hex,
        "name": name,
        "provider": provider,
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    vault["entries"].append(entry)
    _write_vault(state_dir, vault)
    return _public_entry(entry)


def list_entries(state_dir, environ=None, runner=None):
    """Listet Name, Provider und Maske; ohne Key nur ohne Entschlüsselung."""
    vault = _read_vault(state_dir)
    key = _try_vault_key(environ, runner) if vault["entries"] else None
    result = []
    for entry in vault["entries"]:
        masked = _mask(_decrypt_entry(entry, key), entry)
        result.append({**_public_entry(entry), "masked": masked})
    return result


def select_entry(state_dir, name, environ=None, runner=None):
    """Wählt einen Eintrag für den nächsten ``vibe run`` aus."""
    vault = _read_vault(state_dir)
    entry = next((item for item in vault["entries"] if item["name"] == name), None)
    if entry is None:
        raise ValueError(f"Eintrag '{name}' ist nicht vorhanden")
    vault["selected"] = entry["name"]
    _write_vault(state_dir, vault)
    key = _try_vault_key(environ, runner)
    secret = _decrypt_entry(entry, key)
    session = _session_path(state_dir)
    if secret is None:
        session.unlink(missing_ok=True)
    else:
        _write_private_json(session, {"name": entry["name"], "provider": entry["provider"],
                                      "secret": base64.b64encode(secret).decode("ascii")})
    return _public_entry(entry)


def selected_entry(state_dir):
    """Liefert den ausgewählten Eintrag ohne Secret oder ``None``."""
    vault = _read_vault(state_dir)
    name = vault.get("selected")
    if not name:
        return None
    entry = next((item for item in vault["entries"] if item["name"] == name), None)
    return _public_entry(entry) if entry else None


def remove_entry(state_dir, name, environ=None, runner=None):
    """Löscht einen Eintrag und bereinigt die Auswahl."""
    vault = _read_vault(state_dir)
    entry = next((item for item in vault["entries"] if item["name"] == name), None)
    if entry is None:
        return False, f"Eintrag '{name}' ist nicht vorhanden"
    vault["entries"] = [item for item in vault["entries"] if item["name"] != name]
    if vault.get("selected") == name:
        vault["selected"] = None
    _write_vault(state_dir, vault)
    session = _session_path(state_dir)
    if session.exists():
        if _read_json(session, {}).get("name") == name:
            session.unlink()
    return True, f"Eintrag '{name}' entfernt"


# ---------------------------------------------------------------------------
# Harness-Sync
# ---------------------------------------------------------------------------

def _auth_path(auth_path):
    return Path(os.path.expanduser(str(auth_path))) if auth_path else Path(os.path.expanduser(DEFAULT_AUTH_PATH))


def _selected_secret(state_dir, entry, environ, runner):
    """Liefert das Secret der Auswahl, bevorzugt frisch aus dem Vault.

    Mit explizitem ``environ`` ist der Vault-Key Vertragsbestandteil: Fehlt er,
    wird der Fehler weitergegeben. Im CLI-/Läuferpfad (``environ is None``)
    dient die von ``select`` vorbereitete Sitzungsauswahl als Fallback.
    """
    key = None
    try:
        key = vault_key(environ=environ, runner=runner)
    except ValueError:
        if environ is not None:
            raise
    if key is not None:
        secret = _decrypt_entry(entry, key)
        if secret is not None:
            return secret
    if environ is None:
        session = _read_json(_session_path(state_dir), {})
        if session.get("name") == entry["name"] and session.get("provider") == entry["provider"]:
            return base64.b64decode(session["secret"], validate=True)
    return None


def sync(state_dir, harness, environ=None, runner=None, auth_path=None):
    """Überträgt die Auswahl in die opencode-auth.json (0600, atomar)."""
    if harness not in SUPPORTED_HARNESSES:
        return False, f"Harness '{harness}' wird für den Key-Sync nicht unterstützt (nur opencode)"
    entry = selected_entry(state_dir)
    if entry is None:
        return True, "Keine Auswahl vorhanden; Harness-Config unverändert"
    entry = _find_entry(state_dir, entry["name"])
    try:
        secret = _selected_secret(state_dir, entry, environ, runner)
    except ValueError as error:
        return False, f"Vault-Schlüssel nicht verfügbar: {error}"
    if secret is None:
        return False, "Vault-Schlüssel nicht verfügbar oder Eintrag nicht entschlüsselbar"
    path = _auth_path(auth_path)
    data = _read_json(path, {})
    data[entry["provider"]] = {"type": "api", "key": secret.decode("utf-8", errors="replace")}
    _write_private_json(path, data)
    return True, f"Provider '{entry['provider']}' in {path} synchronisiert"


def sync_reset(state_dir, harness, environ=None, runner=None, auth_path=None):
    """Entfernt den synchronisierten Provider und die Sitzungsauswahl."""
    if harness not in SUPPORTED_HARNESSES:
        return False, f"Harness '{harness}' wird für den Key-Sync nicht unterstützt (nur opencode)"
    entry = selected_entry(state_dir)
    if entry is None:
        return True, "Keine Auswahl vorhanden; Harness-Config unverändert"
    path = _auth_path(auth_path)
    if path.exists():
        data = _read_json(path, {})
        data.pop(entry["provider"], None)
        _write_private_json(path, data)
    session = _session_path(state_dir)
    if session.exists() and _read_json(session, {}).get("name") == entry["name"]:
        session.unlink()
    return True, f"Provider '{entry['provider']}' aus {path} entfernt"


# ---------------------------------------------------------------------------
# Kommandozeile (vom Läufer und direkt aufrufbar)
# ---------------------------------------------------------------------------

def main(argv=None):
    """Führt sync bzw. sync-reset aus; 0 bei Erfolg, 2 bei Fehler."""
    parser = argparse.ArgumentParser(prog="vibe_keys.py", description="AP23: Secrets in die Harness-Config übernehmen")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("sync", "sync-reset"):
        command = commands.add_parser(name)
        command.add_argument("--state", required=True, help="Zustandsordner mit keys.json")
        command.add_argument("--harness", default="opencode", help="Ziel-Harness (nur opencode)")
        command.add_argument("--auth-path", default=None, help="Pfad zur auth.json")
        if name == "sync":
            command.add_argument("--reset", action="store_true", help="sync-reset ausführen")
    args = parser.parse_args(argv)
    reset = args.command == "sync-reset" or args.reset
    try:
        if reset:
            ok, message = sync_reset(args.state, args.harness, auth_path=args.auth_path)
        else:
            ok, message = sync(args.state, args.harness, auth_path=args.auth_path)
    except (OSError, ValueError) as error:
        print(f"FEHLT: {error}", file=sys.stderr)
        return 2
    print(message)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
