#!/usr/bin/env python3
"""Fordert bei einer FRITZ!Box eine neue Internet-IP an (optionale Altintegration).

Aufruf über ``vibe fritz reconnect`` oder automatisch über den Paket-Läufer,
wenn die Automatik im Dashboard eingeschaltet ist.

Konfiguration: ``~/.config/fritz.env`` (oder ``FRITZ_ENV``) mit den Zeilen
``FRITZ_ADDR``, ``FRITZ_USER`` und ``FRITZ_PASS``. Die Datei gehört nicht ins
Repository; Ausgaben dieses Programms enthalten keine Zugangsdaten.

Voraussetzung ist das Python-Paket ``fritzconnection`` im aufrufenden
Interpreter. Exit-Codes: 0 = neue IP erkannt, 1 = IP unverändert,
2 = Fehler oder fehlende Konfiguration.
"""
import os
import sys
import time

try:
    from fritzconnection import FritzConnection
except ImportError:  # pragma: no cover - Umgebungsfehler, wird im Dashboard angezeigt
    print(
        "Fehler: Python-Paket 'fritzconnection' fehlt im verwendeten Interpreter.",
        file=sys.stderr,
    )
    sys.exit(2)

SERVICE = "WANPPPConnection1"
ENV_PATH = os.environ.get("FRITZ_ENV") or os.path.expanduser("~/.config/fritz.env")
REQUIRED = ("FRITZ_ADDR", "FRITZ_USER", "FRITZ_PASS")


def load_env(path):
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as error:
        print("Fehler: Konfiguration nicht lesbar:", path, "-", error, file=sys.stderr)
        sys.exit(2)
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [key for key in REQUIRED if not values.get(key)]
    if missing:
        print(
            "Fehler: Konfiguration unvollständig, es fehlt: " + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(2)
    return values


def connection(env):
    return FritzConnection(
        address=env["FRITZ_ADDR"],
        user=env["FRITZ_USER"],
        password=env["FRITZ_PASS"],
    )


def external_ip(connection_object):
    try:
        return connection_object.call_action(
            SERVICE, "GetExternalIPAddress"
        ).get("NewExternalIPAddress")
    except Exception:
        return None


def main():
    env = load_env(ENV_PATH)
    router = connection(env)
    old_ip = external_ip(router)
    print("alte IP:", old_ip or "unbekannt")
    try:
        router.call_action(SERVICE, "ForceTermination")
        print("ForceTermination ok")
    except Exception as error:
        message = str(error)
        if "707" in message or "711" in message:
            print(
                "Trennung läuft bereits oder Verbindung schon getrennt:",
                message.replace("\n", " "),
            )
        else:
            print("Fehler:", message.replace("\n", " "), file=sys.stderr)
            sys.exit(2)
    for _ in range(36):
        time.sleep(5)
        try:
            new_ip = external_ip(connection(env))
            if new_ip and new_ip != old_ip:
                print("neue IP:", new_ip)
                sys.exit(0)
        except Exception:
            pass
    print("IP hat sich nicht geändert", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
