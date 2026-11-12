"""Unabhängige Abnahme AP13: Netzwerkbetrieb, Port-/Bind-Konfiguration.

Die Fälle leiten sich aus dem Arbeitspaket AP13 (TICKETS.md) und aus SPEC.md
(„Sicherheit und Datenintegrität", „Qualität und Abnahme") ab. Getestet wird
der vereinbarte Vertrag:

* ``<state>/ui.json`` ist eine persönliche Einstellungsdatei im
  Zustandsordner. Fehlende oder leere Dateien laden als leeres Objekt; eine
  defekte Datei wird gemeldet statt still ignoriert (Muster V-006).
* ``client_allowed``: fehlende/leere Allowlist erlaubt alles; Loopback-IPs
  sind immer erlaubt (Aussperrschutz); sonst gilt nur der Allowlist-Eintrag
  (Einzel-IP oder CIDR, IPv4). Die Funktion ist eine reine Match-Hilfe ohne
  erreichbaren Verkehr: In Produktion sind ihre IPv6-Pfade nicht erreichbar
  (``validate`` lehnt IPv6-Allowlist-Einträge ab, ``validate_bind`` ist
  IPv4-only); die IPv6-Testfälle belegen nur den internen
  Hilfsfunktion-Vertrag.
* Passwörter werden gesalzen gespeichert (kein Klartext, keine doppelten
  Hashes bei gleichem Kennwort), Mindestlänge 8, Löschen entfernt den Hash.
* Priorität: Defaults < ui.json < Umgebung (VIBE_UI_PORT/VIBE_UI_BIND) <
  CLI-Übergabe. „CLI überschreibt immer Konfig."
* ``validate`` lehnt IPv6-Allowlist-Einträge (Einzel-IP und CIDR) ab:
  Bei IPv4-only-Bindung könnten keine IPv6-Clients ankommen; ein
  akzeptierter IPv6-Eintrag wäre toter, nie wirksamer Zustand in ui.json.
  Die Ablehnungsmeldung nennt IPv6 und den IPv4-Heimnetzstand.
* ``validate_bind`` erlaubt zusätzlich IPv4-Adressliterale inklusive
  ``0.0.0.0``; IPv6-Literale (``::``, ``::1``, ``2001:db8::1``) werden
  ausdrücklich abgelehnt (Nutzerentscheidung Reviewrunde 1: Heimnetz —
  IPv4 genügt), die Meldung nennt IPv6; Hostnamen außer ``localhost``
  bleiben abgelehnt; der Standard ``127.0.0.1`` bleibt Loopback-Vorgabe.
* ``config_extra`` liefert nur die gesetzten Felder ``ui_port``/``ui_bind``
  zur Übergabe an ``vibe_paths.resolve(extra_config=...)``.

Testfälle
---------
``UiConfigFileTest.test_missing_file_loads_an_empty_object``
    Vorbedingung: kein ``ui.json``. Aktion: ``load``. Erwartung: ``{}``, kein
    Fehler, keine Datei angelegt.
``UiConfigFileTest.test_empty_file_loads_an_empty_object``
    Vorbedingung: leere Datei. Aktion: ``load``. Erwartung: ``{}``.
``UiConfigFileTest.test_corrupt_file_is_reported_instead_of_ignored``
    Vorbedingung: Datei mit defektem JSON. Aktion: ``load``. Erwartung:
    ``ConfigError``, der die Datei nennt.
``UiConfigFileTest.test_save_validates_roundtrip_and_returns_the_path``
    Vorbedingung: kein ``ui.json``. Aktion: ``save`` gültiger Werte.
    Erwartung: Rückgabewert ist der Dateipfad, Datei enthält die Werte als
    JSON-Objekt.
``UiConfigFileTest.test_save_rejects_invalid_data_without_writing``
    Vorbedingung: kein ``ui.json``. Aktion: ``save`` ungültiger Werte.
    Erwartung: ``ConfigError``, keine Datei angelegt.
``UiConfigFileTest.test_save_rejects_non_object_data``
    Vorbedingung: kein ``ui.json``. Aktion: ``save`` einer Liste. Erwartung:
    ``ConfigError``.
``ValidateTest.test_validate_returns_a_cleaned_dict``
    Vorbedingung: gültige Werte mit zusätzlichem unbekannten Feld. Aktion:
    ``validate``. Erwartung: bereinigtes Objekt ohne das unbekannte Feld.
``ValidateTest.test_validate_rejects_invalid_values``
    Vorbedingung: ungültige Ports, Binds und Typen. Aktion: ``validate``.
    Erwartung: ``ConfigError`` (ValueError-Unterklasse).
``ValidateTest.test_validate_rejects_non_ip_allowlist_entries``
    Vorbedingung: Allowlist mit „nicht-ip" und „10.0.0.0/99". Aktion:
    ``validate``. Erwartung: ``ConfigError``.
``ValidateTest.test_validate_rejects_ipv6_allowlist_entries``
    Vorbedingung: Allowlist mit IPv6-Einzel-IP (``2001:db8::7``) und
    IPv6-Netz (``2001:db8::/32``). Aktion: ``validate``. Erwartung:
    ``ConfigError``; die Meldung nennt IPv6 und den IPv4-Heimnetzstand.
``AllowlistTest.test_empty_or_missing_allowlist_allows_every_client`` /
``test_loopback_is_always_allowed_lockout_protection`` /
``test_single_ip_entry_matches_exactly`` / ``test_cidr_entry_matches_a_network``
    / ``test_ipv6_entries_match_ipv6_clients`` /
    ``test_mixed_entries_match_each_rule`` /
    ``test_invalid_client_ip_is_denied_not_crashing``
    Vorbedingung: ``ui.json``-Objekte wie im jeweiligen Fall. Aktion:
    ``client_allowed``. Erwartung: genau die dokumentierten Ergebnisse; eine
    nicht parsende Client-IP wird abgelehnt, ohne den Server abstürzen zu
    lassen. Die IPv6-Match-Fälle prüfen den reinen Hilfsfunktion-Vertrag;
    Produktion erreicht diese Pfade nicht (``validate`` lehnt IPv6-Einträge
    ab, ``validate_bind`` ist IPv4-only — weder IPv6-Einträge in ui.json
    noch IPv6-Clients können ankommen).
``PasswordTest`` (siehe Methodendokumentation)
    Vorbedingung: Zustandsordner in temporärem Verzeichnis. Aktion:
    ``set_password``/``verify_password``/``clear_password``. Erwartung:
    Mindestlänge 8, gesalzener Hash ohne Klartext in der Datei, Löschen
    entfernt den Hash, Nicht-Zeichenketten werden abgelehnt.
``ConfigExtraTest.test_config_extra_contains_only_set_fields`` /
``test_config_extra_is_empty_when_nothing_is_set``
    Vorbedingung: ``ui.json``-Objekte wie im Fall. Aktion: ``config_extra``.
    Erwartung: nur ``ui_port``/``ui_bind`` wenn gesetzt, sonst ``{}``.
``ResolvePriorityTest.test_ui_json_overrides_defaults`` /
``test_environment_overrides_ui_json`` /
``test_cli_override_wins_over_environment_and_ui_json`` /
``test_invalid_extra_config_is_rejected`` /
``test_default_bind_stays_loopback``
    Vorbedingung: isolierte Umgebung ohne persönliche config.json; ``ui.json``
    nur über ``extra_config``. Aktion: ``vibe_paths.resolve(extra_config=...)``.
    Erwartung: Priorität Default < ui.json < Umgebung < CLI-Übergabe.
``ValidateBindExtensionTest.test_address_literals_are_now_allowed`` /
``test_ipv6_literals_are_rejected`` / ``test_hostnames_stay_rejected`` /
``test_localhost_maps_to_loopback`` / ``test_invalid_values_stay_rejected`` /
``test_default_resolution_keeps_loopback``
    Vorbedingung: keine besondere Datei. Aktion: ``vibe_paths.validate_bind``
    bzw. ``resolve``. Erwartung: IPv4-Adressliterale erlaubt, IPv6-Literale
    abgelehnt (Heimnetz-Betrieb ist IPv4; die Meldung nennt IPv6),
    DNS-Namen abgelehnt, Standard bleibt ``127.0.0.1``.
``UiCliOverrideTest.test_cli_port_and_bind_win_over_ui_json`` /
``test_ui_json_is_applied_when_no_cli_argument_is_given`` /
``test_cli_rejects_an_invalid_bind_without_starting`` /
``test_cli_rejects_an_invalid_port_without_starting`` /
``test_ui_stop_stays_unchanged`` / ``test_ui_without_subcommand_still_starts`` /
``test_network_bind_start_hints_other_machines_use_this_machines_ip``
    Vorbedingung: isolierte VIBE_*/HOME-Pfade, tmux-Attrappe auf PATH, freier
    Port. Aktion: ``vibe ui start [--port N] [--bind A]`` als echter Prozess.
    Erwartung: die tmux-Attrappe sieht die effektiv aufgelösten Werte im
    Kind-Export; CLI schlägt ui.json; ungültige Werte starten nichts;
    ``stop`` verhält sich unverändert; bei Netz-Bindung nennt die
    Startmeldung, dass andere Rechner das Dashboard über die IP-Adresse
    dieses Rechners erreichen („anderen Rechner" und „IP-Adresse"), beim
    Loopback-Start fehlt dieser Hinweis.

Keine produktiven Konfigurationen, keine echten externen Dienste, keine
tmux-Server von vibe; tmux ist eine Attrappe. Standardbibliothek only.
"""
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
PATHS_MODULE = BIN / "vibe_paths.py"
UI_CONFIG_MODULE = BIN / "vibe_ui_config.py"
CLI = BIN / "vibe"

ENV_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
    "HOME",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_paths():
    return load_module(PATHS_MODULE, "vibe_paths_ap13")


def load_ui_config():
    """Lädt das neue AP13-Modul; in der Rotphase fehlt es mit klarer Meldung."""
    if not UI_CONFIG_MODULE.exists():
        raise AssertionError(
            "AP13-Modul bin/vibe_ui_config.py existiert nicht (erwarteter "
            "Rot-Status, bis die Implementierung es anlegt)"
        )
    return load_module(UI_CONFIG_MODULE, "vibe_ui_config_ap13")


class StateDirFixture(unittest.TestCase):
    """Temporärer Zustandsordner ohne Berührung produktiver Pfade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def ui_json(self):
        return self.state / "ui.json"

    def write_ui_json(self, raw):
        self.ui_json.write_text(raw, encoding="utf-8")


class UiConfigFileTest(StateDirFixture):
    """ui.json laden und speichern; Defekte werden gemeldet."""

    def test_missing_file_loads_an_empty_object(self):
        ui_config = load_ui_config()

        data = ui_config.load(str(self.state))

        self.assertEqual(data, {})
        self.assertFalse(self.ui_json.exists(), "load darf keine Datei anlegen")

    def test_empty_file_loads_an_empty_object(self):
        self.write_ui_json("")
        ui_config = load_ui_config()

        self.assertEqual(ui_config.load(str(self.state)), {})

    def test_corrupt_file_is_reported_instead_of_ignored(self):
        self.write_ui_json("{kein json")
        ui_config = load_ui_config()

        with self.assertRaises(ValueError) as raised:
            ui_config.load(str(self.state))

        self.assertIn("ui.json", str(raised.exception))

    def test_save_validates_roundtrip_and_returns_the_path(self):
        ui_config = load_ui_config()

        path = ui_config.save(str(self.state), {"ui_port": 9151, "ui_bind": "0.0.0.0"})

        self.assertIn("ui.json", str(path))
        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertEqual(stored, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertEqual(ui_config.load(str(self.state)), stored)

    def test_save_rejects_invalid_data_without_writing(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.save(str(self.state), {"ui_port": 70000})

        self.assertFalse(self.ui_json.exists(), "Ungültige Daten wurden gespeichert")

    def test_save_rejects_non_object_data(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.save(str(self.state), ["kein", "objekt"])

        self.assertFalse(self.ui_json.exists())


class ValidateTest(StateDirFixture):
    def test_validate_returns_a_cleaned_dict(self):
        ui_config = load_ui_config()

        cleaned = ui_config.validate(
            {"ui_port": 9151, "ui_bind": "0.0.0.0", "unbekannt": 1}
        )

        self.assertEqual(cleaned, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertNotIn("unbekannt", cleaned)

    def test_validate_accepts_an_empty_object(self):
        ui_config = load_ui_config()

        self.assertEqual(ui_config.validate({}), {})

    def test_validate_rejects_invalid_values(self):
        cases = (
            {"ui_port": 0},
            {"ui_port": 65536},
            {"ui_port": "abc"},
            {"ui_bind": "example.test"},
            {"ui_bind": ""},
            {"allowlist": "keine liste"},
            {"allowlist": [42]},
            {"password_hash": "kein objekt"},
        )
        ui_config = load_ui_config()
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    ui_config.validate(data)

    def test_validate_rejects_non_ip_allowlist_entries(self):
        ui_config = load_ui_config()

        for entry in ("nicht-ip", "10.0.0.0/99", "300.1.2.3", ""):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    ui_config.validate({"allowlist": [entry]})

    def test_validate_rejects_ipv6_allowlist_entries(self):
        # IPv6-Allowlist-Einträge wären bei IPv4-only-Bindung toter, nie
        # wirksamer Zustand in ui.json; sie werden abgelehnt statt still
        # akzeptiert. Die Meldung nennt IPv6 und den IPv4-Heimnetzstand.
        ui_config = load_ui_config()

        for entry in ("2001:db8::7", "2001:db8::/32"):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError) as raised:
                    ui_config.validate({"allowlist": [entry]})
                self.assertIn("IPv6", str(raised.exception))
                self.assertIn("IPv4", str(raised.exception))

    def test_config_error_is_a_value_error(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.validate({"ui_port": 70000})


class AllowlistTest(StateDirFixture):
    """``client_allowed``: reine Match-Funktion ohne erreichbaren Verkehr.

    Die IPv6-Fälle prüfen den internen Hilfsfunktion-Vertrag. Produktion
    erreicht diese Pfade nicht: ``validate`` lehnt IPv6-Allowlist-Einträge
    ab und ``validate_bind`` ist IPv4-only, sodass weder IPv6-Einträge in
    ui.json noch IPv6-Clients ankommen können. Die Fälle bleiben als
    Robustheitsnachweis der Match-Logik (fail-closed statt Absturz)
    bestehen; kein Produktionspfad ändert sich dadurch.
    """

    def test_empty_or_missing_allowlist_allows_every_client(self):
        ui_config = load_ui_config()

        for data in ({}, {"allowlist": []}, {"ui_port": 9151}):
            for ip in ("192.168.1.5", "10.0.0.5", "2001:db8::1"):
                with self.subTest(data=data, ip=ip):
                    self.assertTrue(ui_config.client_allowed(data, ip))

    def test_loopback_is_always_allowed_lockout_protection(self):
        # Aussperrschutz: Auch wenn die Allowlist Loopback nicht nennt, muss
        # ein lokaler Client weiterarbeiten können.
        ui_config = load_ui_config()

        for ip in ("127.0.0.1", "127.5.5.5", "::1"):
            with self.subTest(ip=ip):
                self.assertTrue(
                    ui_config.client_allowed({"allowlist": ["1.2.3.4"]}, ip)
                )

    def test_single_ip_entry_matches_exactly(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["192.168.1.5"]}

        self.assertTrue(ui_config.client_allowed(data, "192.168.1.5"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.6"))
        self.assertFalse(ui_config.client_allowed(data, "10.0.0.5"))

    def test_cidr_entry_matches_a_network(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["10.0.0.0/8"]}

        self.assertTrue(ui_config.client_allowed(data, "10.255.0.1"))
        self.assertTrue(ui_config.client_allowed(data, "10.0.0.0"))
        self.assertFalse(ui_config.client_allowed(data, "11.0.0.1"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.5"))

    def test_ipv6_entries_match_ipv6_clients(self):
        ui_config = load_ui_config()
        single = {"allowlist": ["2001:db8::7"]}
        network = {"allowlist": ["2001:db8::/32"]}

        self.assertTrue(ui_config.client_allowed(single, "2001:db8::7"))
        self.assertFalse(ui_config.client_allowed(single, "2001:db8::8"))
        self.assertTrue(ui_config.client_allowed(network, "2001:db8:aaaa::1"))
        self.assertFalse(ui_config.client_allowed(network, "2001:db9::1"))

    def test_mixed_entries_match_each_rule(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["192.168.1.5", "10.0.0.0/8", "2001:db8::/32"]}

        self.assertTrue(ui_config.client_allowed(data, "192.168.1.5"))
        self.assertTrue(ui_config.client_allowed(data, "10.1.2.3"))
        self.assertTrue(ui_config.client_allowed(data, "2001:db8::9"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.6"))
        self.assertFalse(ui_config.client_allowed(data, "11.1.1.1"))
        self.assertFalse(ui_config.client_allowed(data, "2001:db9::9"))

    def test_invalid_client_ip_is_denied_not_crashing(self):
        ui_config = load_ui_config()

        self.assertFalse(ui_config.client_allowed({"allowlist": []}, ""))
        self.assertFalse(
            ui_config.client_allowed({"allowlist": ["10.0.0.0/8"]}, "nicht-ip")
        )


class PasswordTest(StateDirFixture):
    def test_short_password_is_rejected_without_change(self):
        ui_config = load_ui_config()

        for text in ("", "kurz", "1234567"):
            with self.subTest(length=len(text)):
                with self.assertRaises(ValueError):
                    ui_config.set_password(str(self.state), text)

        self.assertFalse(self.ui_json.exists())

    def test_password_is_stored_salted_without_plaintext(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"

        ui_config.set_password(str(self.state), text)

        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertIn("password_hash", stored)
        self.assertNotIn(text, self.ui_json.read_text(encoding="utf-8"))
        hash_value = stored["password_hash"]
        self.assertIsInstance(hash_value, dict)
        self.assertTrue(hash_value, "Der Hash enthält Daten")

    def test_two_set_password_calls_use_different_salts(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"

        ui_config.set_password(str(self.state), text)
        first = json.loads(self.ui_json.read_text(encoding="utf-8"))["password_hash"]
        ui_config.set_password(str(self.state), text)
        second = json.loads(self.ui_json.read_text(encoding="utf-8"))["password_hash"]

        self.assertNotEqual(
            first, second, "Zweimal dasselbe Kennwort ergab denselben Hash"
        )

    def test_verify_accepts_only_the_correct_password(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"
        ui_config.set_password(str(self.state), text)
        data = ui_config.load(str(self.state))

        self.assertTrue(ui_config.verify_password(data, text))
        self.assertFalse(ui_config.verify_password(data, "falsches kennwort"))
        self.assertFalse(ui_config.verify_password(data, ""))

    def test_verify_without_a_set_password_is_false(self):
        ui_config = load_ui_config()

        self.assertFalse(ui_config.verify_password({}, "egal"))

    def test_clear_password_removes_the_hash_and_verification_fails(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"
        ui_config.set_password(str(self.state), text)

        ui_config.clear_password(str(self.state))

        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertNotIn("password_hash", stored)
        self.assertFalse(ui_config.verify_password(stored, text))

    def test_password_must_be_a_string(self):
        ui_config = load_ui_config()

        for value in (None, 12345, ["liste"]):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ui_config.set_password(str(self.state), value)


class ConfigExtraTest(StateDirFixture):
    def test_config_extra_contains_only_set_fields(self):
        ui_config = load_ui_config()

        extra = ui_config.config_extra(str(self.state))

        self.assertEqual(extra, {})

        ui_config.save(
            str(self.state),
            {"ui_port": 9151, "ui_bind": "0.0.0.0", "allowlist": ["10.0.0.0/8"]},
        )

        extra = ui_config.config_extra(str(self.state))

        self.assertEqual(extra, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertNotIn("allowlist", extra)

    def test_config_extra_is_empty_when_nothing_is_set(self):
        ui_config = load_ui_config()
        ui_config.save(str(self.state), {"allowlist": ["192.168.1.5"]})

        self.assertEqual(ui_config.config_extra(str(self.state)), {})


class ResolvePriorityTest(unittest.TestCase):
    """Priorität: Defaults < ui.json (extra_config) < Umgebung < CLI-Übergabe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, extra_config=None, **kwargs):
        environ = dict(kwargs.pop("environ", {}))
        environ.setdefault("HOME", str(self.home))
        paths = load_paths()
        return paths.resolve(environ=environ, extra_config=extra_config, **kwargs)

    def test_ui_json_overrides_defaults(self):
        result = self.resolve(
            extra_config={"ui_port": 9151, "ui_bind": "0.0.0.0"},
            environ={"VIBE": str(self.workspace)},
        )

        self.assertEqual(result.ui_port, 9151)
        self.assertEqual(result.ui_bind, "0.0.0.0")

    def test_environment_overrides_ui_json(self):
        result = self.resolve(
            extra_config={"ui_port": 9151, "ui_bind": "0.0.0.0"},
            environ={
                "VIBE": str(self.workspace),
                "VIBE_UI_PORT": "9202",
                "VIBE_UI_BIND": "127.0.0.1",
            },
        )

        self.assertEqual(result.ui_port, 9202)
        self.assertEqual(result.ui_bind, "127.0.0.1")

    def test_cli_override_wins_over_environment_and_ui_json(self):
        result = self.resolve(
            extra_config={"ui_port": 9151},
            environ={"VIBE": str(self.workspace), "VIBE_UI_PORT": "9202"},
            overrides={"ui_port": 9303},
        )

        self.assertEqual(result.ui_port, 9303)

    def test_invalid_extra_config_is_rejected(self):
        # ConfigError ist eine ValueError-Unterklasse; die Prüfung läuft
        # über ValueError, weil self.resolve() das Modul selbst lädt und
        # ein zweites ConfigError-Klassenobjekt erzeugen würde, das ein
        # hier geladenes nicht fangen kann.
        for extra in ({"ui_port": 70000}, {"ui_bind": "example.test"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    self.resolve(
                        extra_config=extra, environ={"VIBE": str(self.workspace)}
                    )

    def test_default_bind_stays_loopback(self):
        result = self.resolve(environ={"VIBE": str(self.workspace)})

        self.assertEqual(result.ui_bind, "127.0.0.1")
        self.assertEqual(result.ui_port, 8787)


class ValidateBindExtensionTest(unittest.TestCase):
    """``validate_bind``: IPv4-Literale erlaubt, IPv6 ausdrücklich abgelehnt.

    Nutzerentscheidung Reviewrunde 1: Der Heimnetz-Betrieb ist IPv4;
    IPv6-Bind-Adressen werden abgelehnt, damit keine validierte, aber
    nicht bindbare Konfiguration entsteht. DNS-Hostnamen außer
    ``localhost`` bleiben abgelehnt (DNS-Rebinding-Schutz).
    """

    def setUp(self):
        self.paths = load_paths()

    def test_address_literals_are_now_allowed(self):
        for value in ("0.0.0.0", "192.0.2.5", "127.0.0.1"):
            with self.subTest(value=value):
                self.assertEqual(self.paths.validate_bind(value), value)

    def test_ipv6_literals_are_rejected(self):
        # IPv6 ist für die Bind-Adresse ausdrücklich ausgeschlossen
        # (Heimnetz-Betrieb ist IPv4); die Ablehnungsmeldung nennt IPv6.
        for value in ("::", "::1", "2001:db8::1"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError) as raised:
                    self.paths.validate_bind(value)
                self.assertIn("IPv6", str(raised.exception))

    def test_hostnames_stay_rejected(self):
        for value in ("example.test", "vibe", "localhost.local", "192.0.2.something"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError):
                    self.paths.validate_bind(value)

    def test_localhost_maps_to_loopback(self):
        self.assertEqual(self.paths.validate_bind("localhost"), "127.0.0.1")

    def test_invalid_values_stay_rejected(self):
        for value in ("", "999.1.1.1", "127.0.0.256"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError):
                    self.paths.validate_bind(value)

    def test_default_resolution_keeps_loopback(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            paths = self.paths.resolve(environ={"HOME": tmp.name, "VIBE": tmp.name})
            self.assertEqual(paths.ui_bind, "127.0.0.1")
        finally:
            tmp.cleanup()


FAKE_TMUX = """#!/usr/bin/env bash
case "$1" in
  has-session) exit 1 ;;
  *)
    printf '%s\\n' "$*" >> "$TMUX_LOG"
    exit 0 ;;
esac
"""


class UiCliOverrideTest(unittest.TestCase):
    """``vibe ui`` übergibt die effektiv aufgelösten Werte an den Kindprozess."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.state = self.root / "state"
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir(parents=True)
        self.tmux_log_path = self.root / "tmux.invocations"
        fake_tmux = self.fakebin / "tmux"
        fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
        fake_tmux.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *arguments, ui_json=None):
        environment = os.environ.copy()
        for key in ENV_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PATH": str(self.fakebin) + os.pathsep + environment.get("PATH", ""),
                "TMUX_LOG": str(self.tmux_log_path),
            }
        )
        if ui_json is not None:
            self.state.mkdir(parents=True, exist_ok=True)
            (self.state / "ui.json").write_text(
                json.dumps(ui_json), encoding="utf-8"
            )
        return subprocess.run(
            [sys.executable, str(CLI), "ui", *arguments],
            cwd=str(REPO),
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def tmux_log(self):
        return (
            self.tmux_log_path.read_text(encoding="utf-8")
            if self.tmux_log_path.exists()
            else ""
        )

    def test_cli_port_and_bind_win_over_ui_json(self):
        port = free_port()

        completed = self.run_cli(
            "start", "--port", str(port), "--bind", "0.0.0.0",
            ui_json={"ui_port": 9151, "ui_bind": "127.0.0.1"},
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log, "Dashboard-Start fehlt im tmux-Log")
        self.assertIn(f"VIBE_UI_PORT={port}", log)
        self.assertIn("VIBE_UI_BIND=0.0.0.0", log)
        self.assertNotIn("VIBE_UI_PORT=9151", log)

    def test_ui_json_is_applied_when_no_cli_argument_is_given(self):
        completed = self.run_cli("start", ui_json={"ui_port": 9152, "ui_bind": "0.0.0.0"})

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log)
        self.assertIn("VIBE_UI_PORT=9152", log)
        self.assertIn("VIBE_UI_BIND=0.0.0.0", log)

    def test_network_bind_start_hints_other_machines_use_this_machines_ip(self):
        """AK Startmeldung bei Netz-Bindung (Review-Minor 7).

        Vorbedingung: isolierte Umgebung, tmux-Attrappe. Aktion:
        ``vibe ui start --bind 0.0.0.0`` und ``vibe ui start --bind
        127.0.0.1``. Erwartet: Bei Netz-Bindung nennt die Startmeldung,
        dass andere Rechner das Dashboard über die IP-Adresse dieses
        Rechners erreichen — die gedruckte 0.0.0.0-URL ist vom fremden
        Rechner aus nicht adressierbar. Beim Loopback-Start fehlt dieser
        Hinweis (wie bisher).
        """
        with self.subTest(bind="0.0.0.0"):
            port = free_port()
            network = self.run_cli(
                "start", "--port", str(port), "--bind", "0.0.0.0"
            )
            self.assertEqual(
                network.returncode, 0, network.stdout + network.stderr
            )
            self.assertIn(
                "new-session", self.tmux_log(), "Dashboard-Start fehlt im tmux-Log"
            )
            self.assertIn(
                "anderen Rechner", network.stdout,
                "Netz-Bindung ohne Hinweis auf fremde Rechner",
            )
            self.assertIn(
                "IP-Adresse", network.stdout,
                "Netz-Bindung ohne Hinweis auf die IP-Adresse dieses Rechners",
            )
        with self.subTest(bind="127.0.0.1"):
            port = free_port()
            loopback = self.run_cli(
                "start", "--port", str(port), "--bind", "127.0.0.1"
            )
            self.assertEqual(
                loopback.returncode, 0, loopback.stdout + loopback.stderr
            )
            self.assertNotIn(
                "anderen Rechner", loopback.stdout,
                "Loopback-Start nennt fälschlich fremde Rechner",
            )
            self.assertNotIn(
                "IP-Adresse", loopback.stdout,
                "Loopback-Start nennt fälschlich eine IP-Adresse",
            )

    def test_cli_rejects_an_invalid_bind_without_starting(self):
        completed = self.run_cli("start", "--bind", "example.test")

        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertNotIn(
            "new-session", self.tmux_log(),
            "Ungültige Bind-Adresse hat trotzdem gestartet",
        )

    def test_cli_rejects_an_invalid_port_without_starting(self):
        completed = self.run_cli("start", "--port", "70000")

        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertNotIn("new-session", self.tmux_log())

    def test_ui_stop_stays_unchanged(self):
        completed = self.run_cli("stop")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertNotIn(
            "kill-session", log,
            "Ohne laufende Sitzung darf stop nichts beenden",
        )
        self.assertNotIn("new-session", log, "stop darf nichts starten")

    def test_ui_without_subcommand_still_starts(self):
        port = free_port()

        completed = self.run_cli("--port", str(port), "--bind", "0.0.0.0")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log)
        self.assertIn(f"VIBE_UI_PORT={port}", log)


if __name__ == "__main__":
    unittest.main()
