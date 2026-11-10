#!/usr/bin/env python3
"""vibe_services — gemeinsame Fachdienste für CLI und Dashboard (V-019).

Die Weboberfläche enthält keine eigene Fachlogik mehr. Sie liest Ansichten
über die Funktionen dieses Moduls und ruft schreibende Kommando-Funktionen der
CLI direkt auf. Damit gilt für beide Zugänge derselbe Code.

Der wichtige Unterschied zu einem globalen ``redirect_stdout``: Jeder Aufruf
erhält mit :func:`capture` einen eigenen Ausgabestrom. Parallele Anfragen im
``ThreadingHTTPServer`` können ihre Ausgabe deshalb nicht vermischen.

Die Ansichtsfunktionen bekommen das geladene CLI-Modul als erstes Argument.
So bleibt dieses Modul frei von einem zweiten, konkurrierenden Import des
CLI-Moduls und lässt sich mit einem Ersatzmodul testen.
"""
import io
import os
import re
import subprocess

import vibe_autonomous
import vibe_github
import vibe_guide

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text):
    """Entfernt Farbsteuerzeichen aus protokollierter Ausgabe."""
    return ANSI.sub("", str(text))


def capture(fn, *args, **kwargs):
    """Ruft eine CLI-Funktion mit eigenem Ausgabestrom auf.

    ``fn`` muss einen Parameter ``out`` akzeptieren. Der Rückgabewert entspricht
    dem bisherigen Verhalten des Dashboards: ``(True, Ausgabe)`` bei Erfolg,
    ``(False, Meldung)`` bei ``SystemExit`` oder einer Ausnahme. Der globale
    ``sys.stdout`` wird dabei weder gelesen noch ersetzt und bleibt für andere
    Threads unverändert.
    """
    buffer = io.StringIO()
    try:
        fn(*args, out=buffer, **kwargs)
        return True, strip_ansi(buffer.getvalue()).strip()
    except SystemExit as error:
        code = error.code
        if code in (None, 0):
            return True, strip_ansi(buffer.getvalue()).strip()
        message = str(code)
        if not message or message == "None":
            message = strip_ansi(buffer.getvalue()).strip()
        return False, strip_ansi(message).strip()
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        # Wie bisher: Ausnahmen werden als Meldungstext zurückgegeben; der
        # aufrufende Thread endet also nicht abstürzend.
        return False, str(error)


def tail(path, n=120):
    """Letzte Zeilen einer Protokolldatei ohne Steuerzeichen."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as handle:
        data = handle.read()[-60000:]
    return strip_ansi(data.decode("utf-8", "replace")).splitlines()[-n:]


def project_row(vibe, name):
    """Kurzansicht eines Projekts für Liste und Detailkopf."""
    branch, dirty, last = vibe.git_info(name)
    items = vibe.open_items(name)
    state = vibe.run_state(name)
    return {
        "name": name,
        "type": vibe.ptype(name),
        "branch": branch,
        "dirty": dirty,
        "last": last,
        "open": len(items),
        "path": vibe.ppath(name),
        "running": state["running"],
        "run": state,
        "init": vibe.is_init(name),
        "log": os.path.exists(vibe.logpath(name)),
        "pause_after": vibe.pause_after_active(name),
    }


def project_detail(vibe, paths, name):
    """Vollständige Projektansicht für das Dashboard."""
    data = project_row(vibe, name)
    data["items"] = [{"id": i, "title": t, "state": s} for i, t, s in vibe.open_items(name)]
    data["feedback"] = vibe.feedback_items(name)
    data["tickets"] = vibe.ticket_items(name)
    data["tail"] = tail(vibe.logpath(name), 80)
    try:
        data["verify_cmd"] = bool(vibe.verify_command(name, "quick"))
    except ValueError:
        data["verify_cmd"] = False
    data["env"] = vibe.penv(name)
    try:
        data["write_dirs"] = vibe.write_dirs(name)
        data["write_dirs_error"] = None
    except ValueError as error:
        data["write_dirs"] = []
        data["write_dirs_error"] = str(error)
    data["write_dirs_default"] = vibe.write_dirs_default(name)
    data["write_dirs_custom"] = vibe.write_dirs_custom(name)
    try:
        data["sandbox"] = vibe.sandbox_status(name)
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        # Bewusstes Abfangen: Die Dashboard-Ansicht zeigt den Fehler im Zustand
        # und bleibt sonst nutzbar, statt das Dashboard ganz abzubrechen.
        data["sandbox"] = {
            "enabled": False,
            "tools": [],
            "write_dirs": [],
            "tool_caches": [],
            "missing_tools": [],
            "bwrap": "",
            "state_dir": "",
            "error": str(error),
        }
    try:
        data["autonomous"] = vibe_autonomous.is_enabled(paths.runtime, name)
    except ValueError:
        data["autonomous"] = False
    try:
        # Die Projektansicht darf nie auf ein Git-Remote warten. Fernstatus
        # (ahead/behind) kommt hier ausschließlich aus lokalen Referenzen;
        # bewusste Netzaktionen laufen über die GitHub-Aktionen.
        data["github"] = vibe_github.status(vibe.ppath(name), remote=False)
        data["github"]["branches"] = vibe_github.branches(vibe.ppath(name),
                                                          remote=False)
    except Exception as error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        # Bewusste Entschärfung: Die Ansicht degradiert, das Dashboard bleibt
        # nutzbar; Git-Fehler tragen den Klartext im Feld "error".
        data["github"] = {"enabled": False, "repo": "", "label": vibe_github.DEFAULT_LABEL,
                          "api": vibe_github.OFFICIAL_API, "remotes": [], "branch": "-",
                          "ahead": 0, "behind": 0, "unpushed": False, "branches": [],
                          "auth": vibe_github.token_status(),
                          "error": str(error)}
    return data


def guide_info(vibe, name):
    """Zustand des Projektassistenten inklusive laufendem Agentenauftrag."""
    path = vibe.ppath(name)
    data = vibe_guide.state(path, name=name)
    status = vibe_guide.agent_status(path, name=name, log_dir=vibe.LOGS)
    data["agent"] = {
        "session": status["session"],
        "running": status["running"],
        "agent": status["agent"],
        "log": status["log"],
        "log_tail": status["log_tail"],
    }
    return data


def roots_info(vibe):
    """Entwicklungsordner mit den darin gefundenen Projekten."""
    project_map = vibe.project_map()
    rows = []
    for root in vibe.roots():
        rows.append(
            {
                "path": root,
                "fixed": root == vibe.VIBE,
                "projects": [
                    key for key, value in project_map.items() if os.path.dirname(value) == root
                ],
            }
        )
    return rows


def project_agents_info(vibe, name):
    """Agentenauswahl eines Projekts samt Modellen für die Oberfläche."""
    info = vibe.models_info()
    data = {
        "project": name,
        "agents": [],
        "error": None,
        "models": [],
        "info": {model["id"]: model for model in info.get("models", [])},
        "stand": info.get("stand", ""),
        "hinweis": info.get("hinweis", ""),
        "available_unconfigured": 0,
    }
    try:
        data["agents"] = vibe.project_agent_rows(name)
        data["available_unconfigured"] = sum(
            1 for row in data["agents"] if not row.get("configured")
        )
    except ValueError as error:
        data["error"] = str(error)
    try:
        data["models"] = vibe.models_list()
    except Exception as _error:  # noqa: BLE001; pylint: disable=broad-exception-caught
        # Bewusst ohne Fehlerpfad: Ein nicht lesbarer Modellkatalog ist ein
        # gültiger Zustand; die Oberfläche zeigt die leere Liste an.
        data["models"] = []
    return data


def agents_info(vibe):
    """Globale und projektbezogene Agenten samt Katalog und Profilen."""
    info = vibe.models_info()
    projects = vibe.projects()
    write_dirs, write_dirs_errors = {}, {}
    for project in projects:
        try:
            write_dirs[project] = vibe.write_dirs(project)
        except ValueError as error:
            write_dirs[project] = []
            write_dirs_errors[project] = str(error)
    profiles = vibe.profiles_load()
    agents = vibe.agents_all()
    return {
        "agents": agents,
        "global_agents": [row for row in agents if row["scope"] == "global"],
        "vibe_agent": vibe.vibe_agent_status(),
        "roles": profiles.get("rollen", {}),
        "projects": projects,
        "models": vibe.models_list(),
        "info": {model["id"]: model for model in info.get("models", [])},
        "stand": info.get("stand", ""),
        "hinweis": info.get("hinweis", ""),
        "katalog": {
            "schema": info.get("schema"),
            "version": info.get("version", ""),
            "legacy": info.get("legacy", False),
            "findings": info.get("findings", []),
            "quellen": info.get("quellen", []),
            "nicht_uebernommen": info.get("nicht_uebernommen", []),
        },
        "perms": vibe.PERM_LABELS,
        "perms_project": vibe.PERM_LABELS_PROJECT,
        "write_dirs": write_dirs,
        "write_dirs_errors": write_dirs_errors,
        "profiles": profiles,
    }


def verify_bg(vibe, name, mode):
    """Startet eine Projektprüfung im Hintergrund und schreibt in ihr Protokoll."""
    try:
        argv = vibe.verify_argv(name, mode)
    except ValueError as error:
        return False, str(error)
    if not argv:
        return False, "Keine Prüfbefehle in .vibe/project.env"
    # Bewusster Hintergrundstart (consider-using-with): Ein mit-Block um den
    # Startvorgang würde die Dashboard-Anfrage auf die Prüfungsdauer blockieren.
    with open(vibe.logpath(name, "verify"), "w", encoding="utf-8") as log:
        log.write(f"$ {vibe.verify_command(name, mode)}\n")
        log.flush()
        subprocess.Popen(  # pylint: disable=consider-using-with
            argv, cwd=vibe.ppath(name), stdout=log, stderr=subprocess.STDOUT)
    return True, "Prüfung gestartet"
