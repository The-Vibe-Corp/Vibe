#!/usr/bin/env python3
"""Zugriffssicherheit des Dashboards: ui.json laden, prüfen, schreiben (AP13).

``<state>/ui.json`` ist eine persönliche Einstellungsdatei im Zustandsordner
(dasselbe Muster wie die persönliche config.json in vibe_paths.py). Sie hält
ausschließlich die Zugriffs-Einstellungen des Dashboards:

* ``ui_port`` — Port des Dashboards (Validierung über vibe_paths)
* ``ui_bind`` — Bind-Adresse (IP-Adressliteral; Standard bleibt 127.0.0.1)
* ``allowlist`` — Liste aus Einzel-IPs und CIDR-Netzen; fehlende oder leere
  Liste erlaubt alle Clients, Loopback bleibt immer erlaubt (Aussperrschutz)
* ``password_hash`` — gesalzener PBKDF2-Hash eines optionalen Anmeldung-
  Kennworts; niemals der Klartext

Unbekannte Felder werden beim Prüfen still entfernt. Eine defekte Datei wird
gemeldet statt still ignoriert, damit persönliche Einstellungen nicht
unbemerkt durch Defaults ersetzt werden (V-006).

Dieses Modul startet keine Prozesse und liest nur ui.json im übergebenen
Zustandsordner; beim Import wird keine Datei berührt.
"""
import hashlib
import ipaddress
import json
import os
import secrets
import tempfile

try:
    import vibe_paths
except ImportError:
    # Tests laden dieses Modul per SourceFileLoader direkt aus bin/, ohne
    # bin/ im sys.path. Dann wird das Schwestermodul über seinen Pfad
    # geladen und unter dem Namen registriert, den der normale Import
    # ebenfalls nutzen würde (keine zweite Kopie im sys.modules).
    import importlib.machinery
    import importlib.util
    import sys

    _loader = importlib.machinery.SourceFileLoader(
        "vibe_paths",
        os.path.join(os.path.dirname(os.path.realpath(__file__)), "vibe_paths.py"),
    )
    _spec = importlib.util.spec_from_loader(_loader.name, _loader)
    vibe_paths = importlib.util.module_from_spec(_spec)
    sys.modules["vibe_paths"] = vibe_paths
    _loader.exec_module(vibe_paths)

FILENAME = "ui.json"
PBKDF2_ITERATIONS = 200000

# AP21 v2: Die Sprache ist eine GLOBALE Einstellung (eine pro Installation,
# nicht pro Projekt). Sie liegt in <state>/ui.json unter "language"; der
# Standard ist Englisch. Weitere Sprachen ergänzen LANGUAGES und die i18n-
# Wörterbücher in bin/web/i18n.js.
LANGUAGES = ("en", "de")
DEFAULT_LANGUAGE = "en"


class ConfigError(ValueError):
    """Die Dashboard-Konfiguration (ui.json) ist ungültig."""


def _ui_path(state_dir):
    return os.path.join(state_dir, FILENAME)


def load(state_dir):
    """Liest ui.json; fehlend oder leer gilt als leeres Objekt.

    Eine vorhandene, aber unlesbare oder defekte Datei wird gemeldet statt
    still als leer behandelt — sonst würden Allowlist und Kennwort unbemerkt
    abgeschaltet und der Zugriff wäre offen oder gesperrt, ohne dass jemand
    davon erfährt.
    """
    target = _ui_path(state_dir)
    try:
        raw = vibe_paths.read_config_text(target)
    except vibe_paths.ConfigError as error:
        raise ConfigError(str(error)) from error
    if raw is None or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{FILENAME} in {state_dir} ist kein gültiges JSON: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{FILENAME} in {state_dir} muss ein JSON-Objekt enthalten")
    return data


def _allowlist_entry(entry):
    """IPv4-Einzel-IP oder IPv4-CIDR normalisiert; alles andere wird abgelehnt.

    IPv6-Einträge sind ausdrücklich ausgeschlossen (Nutzerentscheidung:
    Heimnetz-Betrieb ist IPv4; bei reiner IPv4-Bindung könnten sie nie
    wirksam werden und wären toter, nie passender Zustand in ui.json).
    """
    if not isinstance(entry, str):
        raise ConfigError("Allowlist-Einträge müssen Zeichenketten sein")
    text = entry.strip()
    if not text:
        raise ConfigError("Allowlist-Eintrag ist leer")
    try:
        if "/" in text:
            network = ipaddress.ip_network(text, strict=False)
        else:
            network = ipaddress.ip_address(text)
    except ValueError as error:
        raise ConfigError(
            f"Allowlist-Eintrag {entry!r} ist weder IP-Adresse noch CIDR-Netz"
        ) from error
    if network.version != 4:
        raise ConfigError(
            "IPv6-Allowlist-Einträge werden nicht unterstützt; der "
            f"Heimnetz-Betrieb ist IPv4: {entry!r}"
        )
    return str(network)


def validate_language(value):
    """Prüft einen Sprachcode; nur Werte aus LANGUAGES sind gültig (AP21 v2).

    Streng getippt: kein Leerzeichen-Trimming, keine Groß-/Kleinschreibung,
    keine anderen Typen. Ein unbekannter Code muss die Datei unverändert
    lassen (der Aufrufer meldet ihn als ``invalid_language``), weil sonst eine
    still auf ``en`` zurückgefallene Wahl die Oberfläche unerwartet umstellen
    würde.
    """
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ConfigError(
            f"language muss einer der Werte {', '.join(LANGUAGES)} sein"
        )
    return value


def validate(data):
    """Prüft ui.json-Inhalt und liefert ein bereinigtes Objekt ohne Unbekanntes.

    Die Prüfung erfolgt vor jedem Schreiben: Ungültige Werte dürfen die
    Datei nicht verändern (sonst bliebe der Zugriff bei einem Tippfehler
    offen oder gesperrt, bis jemand die Datei von Hand repariert).
    """
    if not isinstance(data, dict):
        raise ConfigError(f"{FILENAME} muss ein JSON-Objekt enthalten")
    cleaned = {}
    if data.get("language") is not None:
        cleaned["language"] = validate_language(data["language"])
    if data.get("ui_port") is not None:
        cleaned["ui_port"] = vibe_paths.validate_port(data["ui_port"])
    if data.get("ui_bind") is not None:
        cleaned["ui_bind"] = vibe_paths.validate_bind(data["ui_bind"])
    if data.get("allowlist") is not None:
        allowlist = data["allowlist"]
        if not isinstance(allowlist, list):
            raise ConfigError("allowlist muss eine Liste aus IPs oder CIDR-Netzen sein")
        cleaned["allowlist"] = [_allowlist_entry(entry) for entry in allowlist]
    if data.get("password_hash") is not None:
        hash_value = data["password_hash"]
        if not isinstance(hash_value, dict) or not hash_value:
            raise ConfigError("password_hash muss ein nichtleeres Objekt sein")
        cleaned["password_hash"] = dict(hash_value)
    return cleaned


def save(state_dir, data):
    """Prüft und schreibt ui.json atomar; Rückgabe ist der Dateipfad.

    Atomar über Tempdatei plus replace, damit ein abgebrochener Schreibvorgang
    keine halbe Konfigurationsdatei hinterlässt. Rechte 0600 sind best effort:
    Auf FUSE/NTFS wirken Unix-Rechte nicht zwingend (siehe vibe-web.py).
    """
    cleaned = validate(data)
    target = _ui_path(state_dir)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".ui-", suffix=".json", dir=state_dir
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(cleaned, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            # Beste Anstrengung; die Ablehnung des Systems wird nicht
            # vorgetäuscht, sondern nur ignoriert (FUSE/NTFS).
            pass
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def client_allowed(data, client_ip):
    """Entscheidet, ob eine Client-IP auf das Dashboard darf.

    Reihenfolge: eine nicht parsende Client-IP wird abgelehnt (nie ein
    Absturz); fehlende oder leere Allowlist erlaubt alle Clients; Loopback
    bleibt immer erlaubt (Aussperrschutz — sonst würde eine restriktive
    Liste den Nutzer vom eigenen Rechner ausschließen); sonst muss die
    Adresse in die Liste passen (Einzel-IP exakt, CIDR als Netz). Defekte
    Einträge werden übersprungen statt den Server abstürzen zu lassen.
    """
    try:
        address = ipaddress.ip_address(str(client_ip or "").strip())
    except ValueError:
        return False
    allowlist = data.get("allowlist") if isinstance(data, dict) else None
    if not isinstance(allowlist, list) or not allowlist:
        return True
    if address.is_loopback:
        return True
    for entry in allowlist:
        text = entry.strip() if isinstance(entry, str) else ""
        if not text:
            continue
        try:
            if "/" in text:
                if address in ipaddress.ip_network(text, strict=False):
                    return True
            elif address == ipaddress.ip_address(text):
                return True
        except ValueError:
            continue
    return False


def _password_hash(password):
    """Gesalzener PBKDF2-Hash; das Kennwort selbst wird nie gespeichert."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return {
        "algo": "pbkdf2_sha256",
        "salt": salt.hex(),
        "hash": digest.hex(),
        "iterations": PBKDF2_ITERATIONS,
    }


def set_password(state_dir, password):
    """Setzt das Anmeldung-Kennwort (mindestens 8 Zeichen) und schreibt ui.json.

    Das Kennwort wird nicht abgeschnitten oder geleert: Zeichenketten mit
    führenden oder schließenden Leerzeichen sind gültige Kennwörter, und ein
    stiller Eingriff würde die Anmeldung verändern. Ungültige Eingaben
    verändern die Datei nicht.
    """
    if not isinstance(password, str) or len(password) < 8:
        raise ConfigError("Das Kennwort muss eine Zeichenkette mit mindestens 8 Zeichen sein")
    data = load(state_dir)
    data["password_hash"] = _password_hash(password)
    return save(state_dir, data)


def verify_password(data, password):
    """Prüft ein Kennwort gegen den gespeicherten Hash; ohne Hash nie wahr."""
    stored = data.get("password_hash") if isinstance(data, dict) else None
    if not isinstance(stored, dict) or not isinstance(password, str):
        return False
    try:
        if str(stored.get("algo") or "") != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(str(stored["salt"]))
        iterations = int(stored["iterations"])
        expected = str(stored["hash"])
    except (KeyError, TypeError, ValueError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()
    # compare_digest statt ==: kein Timing-Orakel beim Kennwortvergleich.
    return secrets.compare_digest(digest, expected)


def clear_password(state_dir):
    """Entfernt den Kennwort-Hash; ohne vorhandenen Hash wird nicht geschrieben."""
    data = load(state_dir)
    if "password_hash" not in data:
        return None
    del data["password_hash"]
    return save(state_dir, data)


def config_extra(state_dir):
    """Nur die gesetzten Felder ui_port/ui_bind für vibe_paths.resolve()."""
    data = load(state_dir)
    return {key: data[key] for key in ("ui_port", "ui_bind") if key in data}
