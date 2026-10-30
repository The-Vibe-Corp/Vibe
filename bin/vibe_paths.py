#!/usr/bin/env python3
"""Pfadmodell und Konfigurationspriorität für vibe (V-006).

vibe kennt vier getrennte Rollen von Verzeichnissen:

* **Quellen** (``source``) — der laufende Programmcode. Beim Aufruf aus dem
  Repository ist das das Repository, nach einer Installation der Ordner
  ``_toolchain``. Der Import dieses Moduls liest nur; er legt nichts an.
* **Installation** (``install``) — der bereitgestellte Programmstand mit
  Vorlagen, Prüfskripten und mitgelieferten Katalogen. Standard ist
  ``$VIBE/_toolchain``.
* **Laufzeit** (``runtime``) — schreibbare Laufzeitdaten wie Logs, Token,
  Instanzkennung und Pause-Markierungen. Standard ist ``$VIBE/_logs``.
* **Zustand** (``state``) — schreibbare persönliche Einstellungen und
  Sicherungen (``vibe.json``, ``profiles.json``, ``fritz.json``,
  ``agent-backups``, ``config-backups``). Standard ist der Installationsordner,
  damit bestehende Installationen ihre Daten unverändert wiederfinden.

Konfigurationspriorität (niedrig nach hoch):

1. mitgelieferte Defaults (pro Profil)
2. persönliche Datei ``~/.config/vibe/config.json``
   (oder ``$XDG_CONFIG_HOME/vibe/config.json``, ``$VIBE_CONFIG_DIR``,
   ``$VIBE_CONFIG_FILE``)
3. Umgebungsvariablen (``VIBE``, ``VIBE_PROFILE``, ``VIBE_INSTALL``,
   ``VIBE_RUNTIME``, ``VIBE_STATE``, ``VIBE_UI_PORT``,
   ``VIBE_OPENCODE_PORT``, ``VIBE_UI_BIND``, ``VIBE_CONTAINER``,
   ``VIBE_AGENTS_DIR``)
4. ausdrückliche Übergaben an :func:`resolve`

Das Dev-Profil (``VIBE_PROFILE=dev``) nutzt standardmäßig ``~/VibeCode-dev``,
Port 8788 für das Dashboard und 4097 für den opencode-Server. Es verweigert
Pfade, die mit dem produktiven Arbeitsbereich geteilt würden, damit ein
Entwicklungslauf die laufende Instanz nicht beschreibt.

Fehlende Verzeichnisse sind bei der Auflösung kein Fehler; erst :func:`ensure`
legt die ausdrücklich benötigten Ordner an. Dieses Modul startet niemals
Prozesse und schreibt beim Import keine Dateien.
"""
import ipaddress
import json
import os

DEFAULT_PROFILE = "prod"
PROFILES = ("prod", "dev")
PROFILE_UI_PORTS = {"prod": 8787, "dev": 8788}
PROFILE_OPENCODE_PORTS = {"prod": 4096, "dev": 4097}
DEFAULT_UI_BIND = "127.0.0.1"
DEFAULT_CONTAINER = "android-dev"

ENV_KEYS = {
    "workspace": "VIBE",
    "install": "VIBE_INSTALL",
    "runtime": "VIBE_RUNTIME",
    "state": "VIBE_STATE",
    "ui_port": "VIBE_UI_PORT",
    "opencode_port": "VIBE_OPENCODE_PORT",
    "ui_bind": "VIBE_UI_BIND",
    "container": "VIBE_CONTAINER",
    "agents_dir": "VIBE_AGENTS_DIR",
}


class ConfigError(ValueError):
    """Die Pfad- oder Portkonfiguration ist ungültig."""


def _home(environ):
    return environ.get("HOME") or os.path.expanduser("~")


def _expand_user(text, home):
    """Ersetzt ``~`` mit dem übergebenen Home, nicht mit dem Prozess-Home."""
    if text == "~":
        return home
    if text.startswith("~/"):
        return os.path.join(home, text[2:])
    return os.path.expanduser(text)


def _path(value, name, home=None):
    """Normalisiert einen Pfad, ohne ihn anzulegen oder Existenz zu verlangen."""
    if value is None:
        raise ConfigError(f"{name} fehlt")
    if not isinstance(value, str):
        raise ConfigError(f"{name} muss eine Zeichenkette sein: {value!r}")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ConfigError(f"{name} enthält ein Steuerzeichen")
    text = value.strip()
    if not text:
        raise ConfigError(f"{name} ist leer")
    return os.path.abspath(_expand_user(text, home or _home(os.environ)))


def validate_port(value):
    """Liefert einen gültigen TCP-Port oder wirft :class:`ConfigError`."""
    if isinstance(value, bool):
        raise ConfigError(f"Port ist keine ganze Zahl: {value!r}")
    try:
        text = str(value).strip()
        if not text or not text.lstrip("+").isdigit():
            raise ValueError(text)
        port = int(text, 10)
    except (TypeError, ValueError):
        raise ConfigError(f"Port ist keine ganze Zahl: {value!r}")
    if not 1 <= port <= 65535:
        raise ConfigError(f"Port liegt außerhalb von 1..65535: {port}")
    return port


def validate_bind(value):
    """Akzeptiert ausschließlich IPv4-Loopback (``localhost`` eingeschlossen)."""
    text = str(value or "").strip()
    if text == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        raise ConfigError(
            "vibe bindet nur an Loopback (z. B. 127.0.0.1); "
            f"{text!r} ist keine IP-Adresse"
        )
    if address.version != 4 or not address.is_loopback:
        raise ConfigError(
            "vibe bindet nur an IPv4-Loopback; "
            f"{text!r} ist nicht erlaubt"
        )
    return str(address)


def source_root(start=None):
    """Quellordner des laufenden Programms (Elternordner von ``bin``)."""
    return os.path.dirname(os.path.dirname(os.path.realpath(start or __file__)))


def default_workspace(environ=None):
    """Produktiver Standard-Arbeitsbereich (wie im Setup)."""
    environ = dict(os.environ if environ is None else environ)
    return os.path.join(_home(environ), "VibeCode")


def default_dev_workspace(environ=None):
    """Eigener Standard-Arbeitsbereich des Dev-Profils."""
    environ = dict(os.environ if environ is None else environ)
    return os.path.join(_home(environ), "VibeCode-dev")


def default_config_path(environ=None):
    """Ort der persönlichen Einstellungen, ohne die Datei anzulegen."""
    environ = dict(os.environ if environ is None else environ)
    home = _home(environ)
    explicit = environ.get("VIBE_CONFIG_FILE")
    if explicit:
        return _path(explicit, "VIBE_CONFIG_FILE", home)
    directory = environ.get("VIBE_CONFIG_DIR")
    if directory:
        return os.path.join(_path(directory, "VIBE_CONFIG_DIR", home), "config.json")
    xdg = environ.get("XDG_CONFIG_HOME")
    base = _path(xdg, "XDG_CONFIG_HOME", home) if xdg else os.path.join(home, ".config")
    return os.path.join(base, "vibe", "config.json")


def load_config(path=None, environ=None):
    """Liest die persönliche Konfiguration; eine fehlende Datei ist leer.

    Eine vorhandene, aber unlesbare oder ungültige Datei wird gemeldet, nicht
    still ignoriert — sonst würden persönliche Einstellungen unbemerkt durch
    Defaults ersetzt.
    """
    environ = dict(os.environ if environ is None else environ)
    target = path or default_config_path(environ)
    try:
        with open(target, encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ConfigError(f"Konfiguration {target} ist nicht lesbar: {error}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"Konfiguration {target} ist kein gültiges JSON: {error}")
    if not isinstance(data, dict):
        raise ConfigError(f"Konfiguration {target} muss ein JSON-Objekt enthalten")
    return data


def _given(value):
    return value is not None and value != ""


def _pick(key, overrides, environ, config, default):
    if overrides and _given(overrides.get(key)):
        return overrides[key]
    env_key = ENV_KEYS[key]
    if _given(environ.get(env_key)):
        return environ[env_key]
    if _given(config.get(key)):
        return config[key]
    return default


def _profile_config(config, profile, config_file):
    """Führt den Profilabschnitt über die allgemeinen Einstellungen zusammen.

    ``{"profiles": {"dev": {"ui_port": 8788}}}`` erlaubt abweichende
    persönliche Einstellungen je Profil, ohne die allgemeinen Werte zu
    verlieren. Eine fehlerhafte Sektion wird gemeldet statt ignoriert.
    """
    sections = config.get("profiles")
    if sections is None:
        return config
    if not isinstance(sections, dict):
        raise ConfigError(f"Konfiguration {config_file}: 'profiles' muss ein Objekt sein")
    section = sections.get(profile, {})
    if section is None:
        section = {}
    if not isinstance(section, dict):
        raise ConfigError(
            f"Konfiguration {config_file}: 'profiles.{profile}' muss ein Objekt sein"
        )
    merged = dict(config)
    merged.pop("profiles", None)
    merged.update(section)
    return merged


def _resolve_profile(overrides, environ, config):
    if overrides and _given(overrides.get("profile")):
        value = overrides["profile"]
    elif _given(environ.get("VIBE_PROFILE")):
        value = environ["VIBE_PROFILE"]
    elif _given(config.get("profile")):
        value = config["profile"]
    else:
        value = DEFAULT_PROFILE
    profile = str(value).strip().lower()
    if profile not in PROFILES:
        raise ConfigError(
            f"Unbekanntes Profil {value!r}; erlaubt: {', '.join(PROFILES)}"
        )
    return profile


class Paths:
    """Aufgelöste Pfade, Ports und Profile für einen vibe-Aufruf."""

    FIELDS = (
        "profile",
        "workspace",
        "source",
        "install",
        "runtime",
        "state",
        "code_bin",
        "config_file",
        "agents_dir",
        "ui_port",
        "opencode_port",
        "ui_bind",
        "container",
    )

    def __init__(self, **values):
        for field in self.FIELDS:
            setattr(self, field, values[field])

    @property
    def opencode_url(self):
        return f"http://127.0.0.1:{self.opencode_port}"

    def as_dict(self):
        values = {field: getattr(self, field) for field in self.FIELDS}
        values["opencode_url"] = self.opencode_url
        return values

    def child_env(self):
        """Umgebung, mit der Kindprozesse dieselben Pfade auflösen."""
        return {
            "VIBE": self.workspace,
            "VIBE_PROFILE": self.profile,
            "VIBE_INSTALL": self.install,
            "VIBE_RUNTIME": self.runtime,
            "VIBE_STATE": self.state,
            "VIBE_UI_PORT": str(self.ui_port),
            "VIBE_OPENCODE_PORT": str(self.opencode_port),
            "VIBE_UI_BIND": self.ui_bind,
            "VIBE_CONTAINER": self.container,
            "VIBE_AGENTS_DIR": self.agents_dir,
            "VIBE_CONFIG_FILE": self.config_file,
        }

    def __repr__(self):
        values = ", ".join(f"{field}={getattr(self, field)!r}" for field in self.FIELDS)
        return f"Paths({values})"


def _productive_reference(base_config, environ, config_file):
    """Pfade, die als produktiv gelten, ohne den aktuellen Dev-Aufruf.

    Nur Defaults und die persönliche Datei zählen. Die Umgebung wird bewusst
    nicht verwendet: ``VIBE`` beschreibt in einem Dev-Aufruf den Dev-Pfad.
    """
    config = _profile_config(base_config, "prod", config_file)
    workspace = _path(
        config.get("workspace") or default_workspace(environ),
        "produktiver Arbeitsbereich",
        _home(environ),
    )
    install = _path(
        config.get("install") or os.path.join(workspace, "_toolchain"),
        "produktive Installation",
        _home(environ),
    )
    runtime = _path(
        config.get("runtime") or os.path.join(workspace, "_logs"),
        "produktive Laufzeit",
        _home(environ),
    )
    state = _path(
        config.get("state") or install,
        "produktiver Zustand",
        _home(environ),
    )
    return workspace, install, runtime, state


def resolve(profile=None, overrides=None, environ=None, source=None):
    """Löst Defaults, persönliche Datei, Umgebung und Übergaben auf.

    ``profile`` ist eine Kurzform für ``overrides={"profile": ...}``. Es werden
    keine Verzeichnisse angelegt und keine Programme gestartet.
    """
    environ = dict(os.environ if environ is None else environ)
    home = _home(environ)
    overrides = dict(overrides or {})
    if profile is not None:
        overrides["profile"] = profile

    config_file = (
        _path(overrides["config_file"], "config_file", home)
        if _given(overrides.get("config_file"))
        else default_config_path(environ)
    )
    base_config = load_config(config_file, environ)
    selected = _resolve_profile(overrides, environ, base_config)
    config = _profile_config(base_config, selected, config_file)

    workspace_default = (
        default_dev_workspace(environ) if selected == "dev" else default_workspace(environ)
    )
    workspace = _path(
        _pick("workspace", overrides, environ, config, workspace_default),
        "Arbeitsbereich",
        home,
    )
    install = _path(
        _pick("install", overrides, environ, config, os.path.join(workspace, "_toolchain")),
        "Installationsordner",
        home,
    )
    runtime = _path(
        _pick("runtime", overrides, environ, config, os.path.join(workspace, "_logs")),
        "Laufzeitordner",
        home,
    )
    state = _path(
        _pick("state", overrides, environ, config, install),
        "Zustandsordner",
        home,
    )

    if selected == "dev":
        prod_workspace, prod_install, prod_runtime, prod_state = _productive_reference(
            base_config, environ, config_file
        )
        conflicts = [
            f"{label} ({dev_path}, {variable})"
            for label, dev_path, prod_path, variable in (
                ("Installation", install, prod_install, "VIBE_INSTALL"),
                ("Laufzeit", runtime, prod_runtime, "VIBE_RUNTIME"),
                ("Zustand", state, prod_state, "VIBE_STATE"),
            )
            if dev_path == prod_path
        ]
        if conflicts:
            raise ConfigError(
                "Das Dev-Profil würde Pfade des produktiven Arbeitsbereichs "
                f"{prod_workspace} verwenden: " + "; ".join(conflicts)
                + f"; eigene Pfade in {config_file} (profiles.dev) oder über die "
                "genannten Umgebungsvariablen setzen"
            )

    ui_port = validate_port(
        _pick("ui_port", overrides, environ, config, PROFILE_UI_PORTS[selected])
    )
    opencode_port = validate_port(
        _pick(
            "opencode_port",
            overrides,
            environ,
            config,
            PROFILE_OPENCODE_PORTS[selected],
        )
    )
    ui_bind = validate_bind(
        _pick("ui_bind", overrides, environ, config, DEFAULT_UI_BIND)
    )
    container = str(
        _pick("container", overrides, environ, config, DEFAULT_CONTAINER)
    ).strip()
    if not container or any(char.isspace() for char in container):
        raise ConfigError(f"Container-Name ist leer oder enthält Leerraum: {container!r}")
    agents_default = os.path.join(home, ".config", "opencode", "agents")
    agents_dir = _path(
        _pick("agents_dir", overrides, environ, config, agents_default),
        "Agentenordner",
        home,
    )
    source_dir = _path(
        source if source is not None else source_root(), "Quellordner", home
    )

    return Paths(
        profile=selected,
        workspace=workspace,
        source=source_dir,
        install=install,
        runtime=runtime,
        state=state,
        code_bin=os.path.join(source_dir, "bin"),
        config_file=config_file,
        agents_dir=agents_dir,
        ui_port=ui_port,
        opencode_port=opencode_port,
        ui_bind=ui_bind,
        container=container,
    )


def ensure(paths, *roles):
    """Legt die ausdrücklich genannten Verzeichnisse an und meldet sie."""
    created = []
    for role in roles:
        if role not in ("workspace", "install", "runtime", "state", "agents_dir"):
            raise ConfigError(f"Unbekannte Pfadrolle: {role}")
        target = getattr(paths, role)
        if os.path.isdir(target):
            continue
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as error:
            raise ConfigError(f"Verzeichnis {target} konnte nicht angelegt werden: {error}")
        created.append(target)
    return created
