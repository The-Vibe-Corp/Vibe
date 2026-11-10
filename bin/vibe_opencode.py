"""Kompatibilitätsadapter für die opencode-CLI (V-007, F26; nur Standardbibliothek).

Der Adapter kapselt alle Annahmen über opencode an einer Stelle. Geprüft ist
ausschließlich die in ``docs/compatibility.md`` dokumentierte Version
(``TESTED_VERSION``). Eine lesbare, aber nicht exakt geprüfte Version (z. B.
nach einem opencode-Update) wird als ``assumed`` geführt und mit dem am besten
passenden geprüften Profil behandelt; Meldungen weisen weiterhin darauf hin,
dass die Version nicht geprüft ist. Ohne lesbare Version wird nichts
angenommen: versionabhängige Schreibvorgänge werden mit einer verständlichen
Meldung abgelehnt. Agentenregeln und Agentenverzeichnis gelten unabhängig von
der erkannten Version. Die Profile in ``PROFILES`` sind die Erweiterungsstelle
für weitere geprüfte Versionen; die Auswahl des Harness liegt in
``bin/vibe_harness.py`` (z. B. pi).

Der Import des Moduls startet keine Prozesse und verändert keine Dateien.
"""
import os
import re
import subprocess
from dataclasses import dataclass, field

TESTED_VERSION = "2.1.4"

# Ein Profil beschreibt nur, was für die genannte Version tatsächlich geprüft
# wurde. Neue Versionen werden erst nach einer Prüfung ergänzt.
PROFILES = {
    "2.1.4": {
        "version": "2.1.4",
        # `opencode models --standalone` nutzt einen eigenen Server und
        # kollidiert nicht mit einem bereits laufenden verwalteten Dienst.
        "models_command": ("models", "--standalone"),
        "server_command": ("serve", "--hostname", "{host}", "--port", "{port}"),
        # In einer leeren Konfiguration schreibt 2.1.4 nach `mcp.servers`
        # (geprüft mit `opencode mcp add` in einem temporären Projekt).
        "mcp_layout": "servers",
        # Felder der tatsächlichen Konfigurationsschemas von 2.1.4
        # (McpLocalConfig/McpRemoteConfig). Die Liste steuert, welche Felder
        # vibe anbietet und schreibt; unbekannte Felder werden nicht blind
        # übernommen.
        "mcp_fields": {
            "local": ("type", "command", "cwd", "environment", "enabled", "timeout"),
            "remote": ("type", "url", "enabled", "headers", "oauth", "timeout"),
        },
        "mcp_oauth_fields": (
            "clientId",
            "clientSecret",
            "scope",
            "callbackPort",
            "redirectUri",
        ),
        "agent_modes": ("primary", "subagent", "all"),
        "agent_required": ("description",),
        "agent_subdir": (".opencode", "agents"),
    },
}

TESTED_PROFILE = PROFILES[TESTED_VERSION]


def _closest_profile(detected):
    """Bestes geprüftes Profil für eine nicht exakt geprüfte Version (F26).

    Wählt die höchste geprüfte Version bis einschließlich der erkannten
    Version; liegt die erkannte Version vor allen geprüften, das älteste
    Profil. Liefert ``None``, wenn kein Profil existiert. Diese Annahme wird
    nie stillschweigend getroffen: die Meldungen nennen die ungeprüfte
    Version.
    """
    if not detected:
        return None
    candidates = []
    for key, profile in PROFILES.items():
        checked = tuple(int(part) for part in key.split("."))
        candidates.append((checked, profile))
    candidates.sort(key=lambda item: item[0])
    at_or_below = [item for item in candidates if item[0] <= detected]
    if at_or_below:
        return at_or_below[-1][1]
    # Erkannte Version unter allen geprüften: das älteste Profil liegt am nächsten.
    return candidates[0][1]


def mcp_entry_fields(type_name, profile=None):
    """Liefert die vom geprüften Schema unterstützten Felder eines Servertyps."""
    profile = profile or TESTED_PROFILE
    return tuple((profile.get("mcp_fields") or {}).get(type_name, ()))


def mcp_oauth_fields(profile=None):
    """Liefert die vom geprüften Schema unterstützten OAuth-Felder."""
    profile = profile or TESTED_PROFILE
    return tuple(profile.get("mcp_oauth_fields") or ())


LAYOUT_SERVERS = "servers"
LAYOUT_CLASSIC = "classic"
LAYOUT_UNKNOWN = "unknown"

VERSION_RE = re.compile(r"\bv?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?\b")
SHORT_LIMIT = 200


class CompatibilityError(Exception):
    """Die installierte opencode-Version ist für diese Aktion nicht geprüft."""


@dataclass(frozen=True)
class VersionInfo:
    """Ergebnis der Versionsprüfung.

    ``status`` ist ``supported`` (exakt geprüft), ``assumed`` (vermutlich
    kompatibel über ein Fallback-Profil), ``unknown`` (Version nicht lesbar),
    ``missing``, ``timeout`` oder ``error``.
    """

    status: str
    message: str
    version: str = ""
    major: int = 0
    exit_code: int = 0
    output: str = ""
    profile: dict = field(default_factory=dict, compare=False)

    @property
    def supported(self):
        return self.status in ("supported", "assumed") and bool(self.profile)

    @property
    def checked(self):
        """Nur die exakt geprüfte Version gilt als geprüft (F26)."""
        return self.status == "supported"

    def as_dict(self):
        return {
            "status": self.status,
            "version": self.version,
            "message": self.message,
            "tested_version": TESTED_VERSION,
        }


def _short(text, limit=SHORT_LIMIT):
    """Macht Ausgaben einzeilig und begrenzt sie für Meldungen."""
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def run_command(argv, timeout=15):
    """Startet ein Programm ohne Shell und liefert ``(Exitcode, Ausgabe)``.

    Die Semantik entspricht ``vibe.run``: 127 = Programm nicht gefunden,
    124 = Zeitüberschreitung, 126 = nicht ausführbar. Der Adapter bleibt
    dadurch unabhängig von ``bin/vibe`` und ohne zirkulären Import.
    """
    if (not isinstance(argv, (list, tuple)) or not argv
            or not all(isinstance(arg, str) for arg in argv)):
        raise ValueError("Argumentliste erwartet: Programm und Argumente als Zeichenketten")
    argv = list(argv)
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return process.returncode, (process.stdout + process.stderr).strip()
    except FileNotFoundError:
        return 127, "Programm nicht gefunden: " + argv[0]
    except subprocess.TimeoutExpired:
        return 124, f"Zeitüberschreitung nach {timeout:g} s: {argv[0]}"
    except OSError as error:
        return 126, f"Programm nicht ausführbar: {argv[0]}: {error}"


def probe(binary="opencode", timeout=15, runner=None):
    """Prüft die tatsächlich installierte opencode-Version.

    ``runner`` ist nur für Tests gedacht und hat die Signatur
    ``runner(argv, timeout) -> (exitcode, ausgabe)``.
    """
    runner = runner or run_command
    code, output = runner([binary, "--version"], timeout)
    if code == 127:
        return VersionInfo("missing", "opencode wurde nicht gefunden (PATH prüfen oder installieren).",
                           exit_code=code, output=_short(output))
    if code == 124:
        return VersionInfo("timeout", f"Zeitüberschreitung: opencode --version antwortet nicht innerhalb von {timeout:g} s.",
                           exit_code=code, output=_short(output))
    if code != 0:
        return VersionInfo("error", f"opencode --version endete mit Exit {code}: {_short(output)}",
                           exit_code=code, output=_short(output))

    match = VERSION_RE.search(output or "")
    if not match:
        return VersionInfo(
            "unknown",
            f"Versionsausgabe nicht erkannt: {_short(output) or '(leer)'} (geprüft: {TESTED_VERSION}).",
            exit_code=code,
            output=_short(output),
        )
    version = ".".join(match.groups())
    detected = tuple(int(part) for part in match.groups())
    profile = PROFILES.get(version)
    if profile is not None:
        return VersionInfo(
            "supported",
            f"opencode {version} ist geprüft.",
            version=version,
            major=detected[0],
            exit_code=code,
            output=_short(output),
            profile=profile,
        )
    fallback = _closest_profile(detected)
    if fallback is None:
        return VersionInfo(
            "unknown",
            f"opencode {version} ist nicht geprüft (geprüft: {TESTED_VERSION}).",
            version=version,
            major=detected[0],
            exit_code=code,
            output=_short(output),
        )
    return VersionInfo(
        "assumed",
        f"opencode {version} ist nicht geprüft (geprüft: {fallback['version']}); "
        "es wird das geprüfte Profil dieser Version verwendet.",
        version=version,
        major=detected[0],
        exit_code=code,
        output=_short(output),
        profile=fallback,
    )


def require_supported(info):
    """Bricht ab, wenn keine Version erkennbar ist; nennt die geprüfte Version.

    Geprüfte Versionen und als ``assumed`` behandelte Versionen mit
    Fallback-Profil geben ihr Profil zurück. Ohne lesbare Version
    (fehlendes Programm, Fehler, Zeitüberschreitung, unlesbare Ausgabe)
    gibt es keine Annahme und damit keinen Schreib- oder Startvorgang.
    """
    if not info.supported:
        suffix = "" if TESTED_VERSION in info.message else f" Geprüft ist opencode {TESTED_VERSION}."
        raise CompatibilityError(info.message + suffix)
    return info.profile


def parse_models(output):
    """Liest Modell-IDs im Format ``anbieter/modell`` aus der CLI-Ausgabe."""
    models = []
    for line in (output or "").splitlines():
        token = line.strip()
        if not token or token.startswith("#"):
            continue
        if "/" not in token or any(character.isspace() for character in token):
            continue
        if token not in models:
            models.append(token)
    return models


def list_models(binary="opencode", timeout=30, runner=None, info=None):
    """Liefert die Modelle der verbundenen Anbieter über den Adapter."""
    runner = runner or run_command
    info = info or probe(binary=binary, runner=runner)
    result = {"ok": False, "models": [], "version": info, "error": "", "warning": ""}
    if info.status in ("missing", "timeout", "error"):
        result["error"] = info.message
        return result

    command = [binary] + list((info.profile or {}).get("models_command") or ("models",))
    code, output = runner(command, timeout)
    if code == 127:
        result["error"] = "opencode wurde nicht gefunden (PATH prüfen oder installieren)."
    elif code == 124:
        result["error"] = f"Zeitüberschreitung: 'opencode models' antwortet nicht innerhalb von {timeout:g} s."
    elif code != 0:
        result["error"] = f"'opencode models' endete mit Exit {code}: {_short(output)}"
    else:
        models = parse_models(output)
        if not models and (output or "").strip():
            result["error"] = f"Ausgabe von 'opencode models' nicht erkannt: {_short(output)}"
        else:
            result["models"] = models
            result["ok"] = True
    if info.status in ("unknown", "assumed"):
        result["warning"] = info.message
    return result


def server_command(port, host="127.0.0.1", binary="opencode", info=None, runner=None):
    """Baut den Startbefehl des opencode-Servers als Argumentliste."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Port muss eine ganze Zahl zwischen 1 und 65535 sein.")
    if not isinstance(host, str) or not host or any(character.isspace() for character in host):
        raise ValueError("Host muss eine nichtleere Zeichenkette ohne Leerzeichen sein.")
    info = info or probe(binary=binary, runner=runner)
    profile = require_supported(info)
    return [binary] + [
        part.replace("{host}", host).replace("{port}", str(port))
        for part in profile["server_command"]
    ]


def is_mcp_server(value):
    """Erkennt einen Servereintrag anhand der tatsächlichen Schemamerkmale."""
    if not isinstance(value, dict):
        return False
    if value.get("type") in ("local", "remote"):
        return True
    if isinstance(value.get("command"), list):
        return True
    return isinstance(value.get("url"), str)


# Rückwärtskompatibler interner Name für vorhandene Aufrufer.
_looks_like_server = is_mcp_server


def detect_mcp_layout(config, info=None, binary="opencode", runner=None):
    """Ermittelt das tatsächliche MCP-Schema aus der Konfiguration.

    Vorhandene Konfigurationen sind die stärkste Evidenz. Nur wenn der
    ``mcp``-Block leer ist, darf das geprüfte Profil der getesteten Version
    verwendet werden. Unbekannte Versionen und unbekannte Strukturen führen zu
    ``LAYOUT_UNKNOWN``; der Aufrufer darf dann nicht schreiben.
    """
    data = config if isinstance(config, dict) else {}
    mcp = data.get("mcp")
    if "mcp" in data and mcp is not None and not isinstance(mcp, dict):
        return {
            "layout": LAYOUT_UNKNOWN,
            "servers": {},
            "source": "config",
            "message": "Der 'mcp'-Block ist kein Objekt. Die Konfiguration wird nicht verändert.",
        }
    if isinstance(mcp, dict):
        servers = mcp.get("servers")
        if isinstance(servers, dict):
            return {"layout": LAYOUT_SERVERS, "servers": servers, "source": "config", "message": ""}
        entries = {name: value for name, value in mcp.items() if _looks_like_server(value)}
        # Ein gemischter Block (Serverobjekte plus nicht zuordenbare Objekte)
        # darf nicht als schreibbares "classic" gelten: _store würde die
        # unbekannten Objekte sonst stillschweigend verwerfen.
        leftovers = [
            name for name, value in mcp.items()
            if isinstance(value, dict) and name not in entries
        ]
        if entries and not leftovers:
            return {"layout": LAYOUT_CLASSIC, "servers": entries, "source": "config", "message": ""}
        if mcp:
            return {
                "layout": LAYOUT_UNKNOWN,
                "servers": {},
                "source": "config",
                "message": "Der 'mcp'-Block enthält Einträge, die keinem bekannten Schema zugeordnet "
                           "werden können. Die Konfiguration wird nicht verändert.",
            }

    info = info or probe(binary=binary, runner=runner)
    if info.supported:
        layout = info.profile.get("mcp_layout")
        if layout in (LAYOUT_SERVERS, LAYOUT_CLASSIC):
            if info.checked:
                message = (f"Leere Konfiguration: geprüftes Schema für opencode "
                           f"{info.version} wird verwendet.")
            else:
                message = (f"Leere Konfiguration: für opencode {info.version} wird das "
                           f"Schema der geprüften Version {info.profile['version']} "
                           f"angenommen; {info.version} selbst ist nicht geprüft.")
            return {
                "layout": layout,
                "servers": {},
                "source": "profile",
                "message": message,
            }
    return {
        "layout": LAYOUT_UNKNOWN,
        "servers": {},
        "source": "none",
        "message": f"MCP-Schema nicht feststellbar: {info.message} "
                   "Die installierte opencode-Version ist nicht geprüft; es wird nichts geschrieben.",
    }


def agent_directory(base):
    """Projektverzeichnis für opencode-Agenten aus dem geprüften Profil."""
    return os.path.join(base, *TESTED_PROFILE["agent_subdir"])


def validate_agent(frontmatter, body, profile=None):
    """Prüft Frontmatter und Prompt gegen die Regeln der geprüften Version."""
    profile = profile or TESTED_PROFILE
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter konnte nicht gelesen werden.")
    for name in profile["agent_required"]:
        if not str(frontmatter.get(name) or "").strip():
            raise ValueError(f"Im Frontmatter fehlt '{name}' (Pflichtfeld in opencode {TESTED_VERSION}).")
    mode = frontmatter.get("mode")
    if mode and mode not in profile["agent_modes"]:
        raise ValueError("mode muss " + ", ".join(profile["agent_modes"]) + " sein.")
    if not str(body or "").strip():
        raise ValueError("Der Prompt (Text nach dem Frontmatter) ist leer.")
    return frontmatter
