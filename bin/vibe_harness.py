#!/usr/bin/env python3
"""Austauschbare Harness-Schicht für vibe (AP04).

Ein *Harness* ist das Programm, das ein Arbeitspaket tatsächlich ausführt.
Bisher war das fest opencode. Dieses Modul kapselt Auswahl, Diagnose,
Einrichtungshinweise, Agenten-Prompt und Startbefehl an einer Stelle, damit
weitere Harnesses ergänzt werden können, ohne CLI, Web-API und Läufer zu
verteilen.

Auswahl:
* ``VIBE_HARNESS`` (nur für diesen Prozess) hat Vorrang.
* Sonst ``<Zustand>/harness.json``.
* Fehlt die Datei, bleibt opencode der Default; bestehende Installationen
  ändern ihr Verhalten dadurch nicht.
* Eine vorhandene, aber ungültige Datei wird gemeldet und nicht still durch
  opencode ersetzt.

Pi wird als erster alternativer Harness über seine dokumentierte CLI im
Print-Modus gestartet. Pi kennt keine opencode-Agentenverwaltung; vibe übergibt
deshalb den Prompt-Text der gewählten Agentendatei als Teil der Aufgabe. Die
Grenzen (keine Subagenten-/Rechteprüfung durch Pi, eigenes MCP-Schema) sind in
``docs/compatibility.md`` dokumentiert.

Der Import dieses Moduls startet keine Prozesse und schreibt keine Dateien.
"""
import argparse
import json
import os
import re
import shutil
import sys

import vibe_opencode
import vibe_storage

DEFAULT_HARNESS = "opencode"
SELECTION_FILE = "harness.json"
SHORT_LIMIT = 200
VERSION_RE = re.compile(r"\bv?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?\b")
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
FRONTMATTER_RE = re.compile(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)
CONTEXT_RE = re.compile(r"^\d+(?:\.\d+)?[KM]?$")
NO_MODELS = "No models available"

HARNESSES = {
    "opencode": {
        "id": "opencode",
        "name": "opencode",
        "binary": "opencode",
        "alternative": False,
        "server": True,
        "official": "https://opencode.ai/docs/",
        "npm_package": "opencode-ai",
        "hint": "Agentenläufe, Dashboard und opencode-Server.",
    },
    "pi": {
        "id": "pi",
        "name": "Pi",
        "binary": "pi",
        "alternative": True,
        "server": False,
        "official": "https://pi.dev/docs/latest",
        "npm_package": "@earendil-works/pi-coding-agent",
        "hint": "Pi benötigt Node.js 22.19 oder neuer. Offizielle Anleitung: "
                "https://pi.dev/docs/latest",
    },
}

# AP14: Fähigkeitsschicht je Harness. opencode kann Zusatzanweisungen
# entgegennehmen (steer) und eine Session fortsetzen (continue). Pi läuft im
# Print-Modus (--no-session): keine fortsetzbare Session, also keine der
# beiden Fähigkeiten. Die Abfrage ist eine reine Funktion; Harnesses ohne
# Eintrag melden jede Fähigkeit als nicht unterstützt.
CAPABILITIES = {"opencode": ("steer", "continue")}


def supports(name, capability):
    """Meldet, ob ein Harness die Fähigkeit unterstützt (reine Funktion).

    Unbekannte oder ungültige Harness-Namen und unbekannte oder ungültige
    Fähigkeiten ergeben ``False`` statt eines Fehlers, damit Aufrufer (Web-API
    und Oberfläche) ohne Ausnahmebehandlung entscheiden können.
    """
    harness = str(name or "").strip().lower()
    return capability in CAPABILITIES.get(harness, ())


class HarnessError(ValueError):
    """Die Harness-Auswahl oder ihre Konfiguration ist ungültig."""


def harness_ids():
    """Stabile Reihenfolge: opencode bleibt der Default, Pi ist die Alternative."""
    return ["opencode", "pi"]


def definition(name):
    """Liefert die Beschreibung eines Harness oder wirft :class:`HarnessError`."""
    value = str(name or "").strip().lower()
    if value not in HARNESSES:
        raise HarnessError(
            "Unbekannter Harness: " + str(name)
            + " (erlaubt: " + ", ".join(harness_ids()) + ")"
        )
    return HARNESSES[value]


def selection_path(state_dir):
    """Pfad der Auswahl-Datei im Zustandsordner."""
    return os.path.join(str(state_dir), SELECTION_FILE)


def _short(text, limit=SHORT_LIMIT):
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def read_selection(state_dir, environ=None):
    """Liest den aktiven Harness; ``VIBE_HARNESS`` hat Vorrang.

    Eine fehlende Datei ist der Default. Eine vorhandene, unlesbare oder
    unbekannte Auswahl wird gemeldet, damit sie nicht unbemerkt zu opencode
    zurückfällt.
    """
    environ = dict(os.environ if environ is None else environ)
    override = environ.get("VIBE_HARNESS")
    if override is not None and str(override).strip():
        return definition(override)["id"]

    path = selection_path(state_dir)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return DEFAULT_HARNESS
    except OSError as error:
        raise HarnessError(f"Harness-Auswahl {path} ist nicht lesbar: {error}") from error
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise HarnessError(f"Harness-Auswahl {path} ist kein gültiges JSON: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("harness"), str):
        raise HarnessError(f"Harness-Auswahl {path} enthält kein Feld 'harness'.")
    return definition(data["harness"])["id"]


def write_selection(state_dir, name, expected=None):
    """Speichert die Auswahl atomar und liefert den Pfad."""
    chosen = definition(name)["id"]
    path = selection_path(state_dir)
    try:
        os.makedirs(str(state_dir), exist_ok=True)
    except OSError as error:
        raise HarnessError(f"Zustandsordner {state_dir} konnte nicht angelegt werden: {error}") from error
    text = json.dumps({"harness": chosen}, indent=1) + "\n"
    snapshot = vibe_storage.read_snapshot(path)
    if expected is None:
        expected = snapshot.digest if snapshot.exists else vibe_storage.MISSING
    try:
        vibe_storage.write_text(path, text, expected=expected)
    except vibe_storage.StorageError as error:
        raise HarnessError(f"Harness-Auswahl {path} konnte nicht gespeichert werden: {error}") from error
    return path


def _run(runner, argv, timeout, environ=None):
    """Startet das Programm für Diagnosen; ``runner`` ersetzt es in Tests.

    Ohne Test-Runner wird auf die gemeinsame Semantik des opencode-Adapters
    zurückgegriffen (127/124/126), optional mit eigener Umgebung für
    PATH-beschränkte Diagnosen.
    """
    if runner is not None:
        return runner(argv, timeout)
    return vibe_opencode.run_command(argv, timeout, environ=environ)


def probe(name=None, state_dir=None, binary=None, runner=None, timeout=10, environ=None):
    """Prüft, ob der Harness startbar ist, ohne eine Modellaufgabe zu senden.

    ``status`` ist ``ready``, ``missing``, ``timeout``, ``error`` oder
    ``unknown`` (Programm antwortet, aber ohne erkennbare Version).
    """
    if name is None:
        if state_dir is None:
            raise HarnessError("probe braucht einen Harness oder einen Zustandsordner.")
        name = read_selection(state_dir, environ=environ)
    info = definition(name)
    target = binary or info["binary"]
    code, output = _run(runner, [target, "--version"], timeout, environ=environ)
    result = {
        "harness": info["id"],
        "name": info["name"],
        "binary": target,
        "installed": False,
        "status": "error",
        "version": "",
        "message": "",
    }
    if code == 127:
        result.update(
            status="missing",
            message=f"{info['name']} wurde nicht gefunden ({target}; PATH prüfen oder installieren).",
        )
        return result
    if code == 124:
        result.update(
            status="timeout",
            message=f"Zeitüberschreitung: {target} --version antwortet nicht innerhalb von {timeout:g} s.",
        )
        return result
    if code != 0:
        result.update(
            status="error",
            message=f"{target} --version endete mit Exit {code}: {_short(output)}",
        )
        return result

    match = VERSION_RE.search(output or "")
    if not match:
        result.update(
            status="unknown",
            installed=True,
            message=f"{info['name']} ist vorhanden, die Version wurde aber nicht erkannt: {_short(output) or '(leer)'}",
        )
        return result
    version = ".".join(match.groups())
    result.update(
        status="ready",
        installed=True,
        version=version,
        message=f"{info['name']} {version} ist vorhanden.",
    )
    return result


def setup_plan(name, which=None):
    """Liefert Einrichtungshinweis und Installationsbefehl als Argumentliste."""
    info = definition(name)
    which = which or shutil.which
    installed = bool(which(info["binary"]))
    command = []
    if not installed:
        command = ["npm", "install", "-g", "--ignore-scripts", info["npm_package"]]
        if info["id"] == "opencode":
            command = ["npm", "install", "-g", info["npm_package"]]
    return {
        "harness": info["id"],
        "name": info["name"],
        "binary": info["binary"],
        "installed": installed,
        "install_command": command,
        "hint": info["hint"],
        "official": info["official"],
    }


def install(name, which=None, runner=None, timeout=300, environ=None):
    """Führt den Registry-Befehl der Installation aus und prüft danach erneut.

    Der Befehl kommt nur aus ``setup_plan`` (B18: Aufrufargumente laufen
    nicht an den Installer). Bereits installiert (``which(binary)``): kein
    Befehl, ``already=True``, ``output=""``. Danach prüft ``install``
    erneut (``already=False``).
    """
    info = definition(name)
    which = which or shutil.which
    if which(info["binary"]):
        return {
            "harness": info["id"],
            "code": 0,
            "output": "",
            "already": True,
            "probe": probe(name, runner=runner, environ=environ),
        }
    plan = setup_plan(name, which=which)
    code, output = _run(runner, plan["install_command"], timeout, environ=environ)
    return {
        "harness": info["id"],
        "code": code,
        "output": _short(output),
        "already": False,
        "probe": probe(name, runner=runner, environ=environ),
    }


def status(state_dir, environ=None, runner=None, which=None):
    """Aktive Auswahl plus Diagnose aller bekannten Harnesses."""
    selected = read_selection(state_dir, environ=environ)
    entries = []
    for name in harness_ids():
        plan = setup_plan(name, which=which)
        result = probe(name, binary=None, runner=runner, environ=environ)
        result["install_command"] = plan["install_command"]
        result["hint"] = plan["hint"]
        result["official"] = plan["official"]
        result["selected"] = name == selected
        entries.append(result)
    return {"selected": selected, "harnesses": entries}


def agent_prompt(project, agent, agents_dir=None):
    """Liest den Prompt-Text einer opencode-Agentendatei für Pi.

    Projektagenten haben Vorrang vor globalen Agenten; das entspricht der
    dokumentierten opencode-Priorität. Frontmatter wird nicht mitgesendet.
    """
    if not AGENT_RE.match(str(agent or "")):
        raise HarnessError("Agentenname ungültig: " + str(agent))
    candidates = [os.path.join(str(project), ".opencode", "agents", agent + ".md")]
    if agents_dir:
        candidates.append(os.path.join(str(agents_dir), agent + ".md"))
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HarnessError(f"Agentendatei {path} ist nicht lesbar: {error}") from error
        match = FRONTMATTER_RE.match(text)
        body = text[match.end():] if match else text
        if not body.strip():
            raise HarnessError(f"Agent '{agent}' hat keinen Prompt-Text: {path}")
        return body.strip()
    raise HarnessError(
        f"Agent '{agent}' wurde für den Harness nicht gefunden "
        f"(gesucht: {', '.join(candidates)})."
    )


def run_argv(name, prompt, project, agent=None, model=None, server_url=None,
             title=None, binary=None, agents_dir=None, events=False):
    """Baut die Argumentliste für einen Agentenlauf.

    opencode erhält unverändert die bisher geprüften Argumente. Pi läuft im
    Print-Modus; der Prompt der Agentendatei wird der Aufgabe vorangestellt,
    weil Pi keine opencode-Agentendateien liest.

    ``events=True`` baut bei Pi die strukturierte Ereignisausgabe ein
    (``--mode json``, Pi-Dokumentation docs/json.md); der Läufer nutzt sie
    für die Subagentenerfassung (F19/F24). Ohne ``events`` bleibt die Liste
    byte-identisch zum bisherigen Verhalten. opencode erhält seine
    Ereignisoption weiterhin vom Läufer (``--format json``) und wird von
    ``events`` nie beeinflusst.
    """
    info = definition(name)
    if not isinstance(prompt, str) or not prompt.strip():
        raise HarnessError("Der Prompt ist leer.")
    target = binary or info["binary"]
    model_args = ["--model", str(model)] if model else []

    if info["id"] == "opencode":
        argv = [target, "run"]
        if server_url:
            argv += ["--server", str(server_url)]
        else:
            argv += ["--standalone"]
        argv += ["--auto", "--thinking"]
        if agent:
            argv += ["--agent", str(agent)]
        argv += model_args
        if title:
            argv += ["--title", str(title)]
        argv += [prompt]
        return argv

    if not agent:
        raise HarnessError("Für Pi muss ein Agent mit Prompt-Datei gewählt sein.")
    message = agent_prompt(project, agent, agents_dir=agents_dir) + "\n\n---\n\n" + prompt
    # Agentenläufe sind einmalig. Ohne Sitzungsdatei schreibt Pi keine
    # Sitzungsdateien; sein Agentenverzeichnis ~/.pi/agent liest und
    # schreibt Pi trotzdem — auch mit --no-session (Sperrdatei
    # trust.json.lock beim Lesen des Vertrauensspeichers; Bug B4). Die
    # Scratch-Sandbox stellt deshalb über die Umgebungsvariable
    # PI_CODING_AGENT_DIR einen beschreibbaren Agentenordner bereit
    # (bin/vibe_sandbox.py, bwrap_argv()).
    argv = [target, "--print", "--no-session"]
    if events:
        argv += ["--mode", "json"]
    argv += model_args
    if title:
        argv += ["--name", str(title)]
    # "--" beendet die Optionsauswertung; Aufgaben dürfen mit "-" beginnen.
    argv += ["--", message]
    return argv


def _parse_pi_models(output):
    """Liest die Modelltabelle von ``pi --list-models``.

    Pi 1.5.0 gibt eine Tabelle mit den Spalten ``provider``, ``model``,
    ``context``, ``max-out``, ``thinking`` und ``images`` aus. Ältere
    Ausgaben und die Test-Attrappen nennen nur ``anbieter/modell`` je Zeile;
    beide Formen werden akzeptiert. Hinweis- und Pfadzeilen werden ignoriert.
    """
    models = []
    for line in (output or "").splitlines():
        parts = line.split()
        candidate = ""
        if (len(parts) >= 6 and parts[0] != "provider"
                and CONTEXT_RE.match(parts[2]) and CONTEXT_RE.match(parts[3])
                and parts[4] in ("yes", "no") and parts[5] in ("yes", "no")):
            candidate = parts[0] + "/" + parts[1]
        elif (len(parts) == 1 and parts[0].count("/") == 1
              and not parts[0].startswith("/")):
            candidate = parts[0]
        if candidate and candidate not in models:
            models.append(candidate)
    return models


def list_models(name=None, state_dir=None, binary=None, runner=None, timeout=30,
                environ=None):
    """Listet Modelle des aktiven Harness für die Agentenverwaltung."""
    if name is None:
        if state_dir is None:
            raise HarnessError("list_models braucht einen Harness oder einen Zustandsordner.")
        name = read_selection(state_dir, environ=environ)
    info = definition(name)
    target = binary or info["binary"]
    result = {
        "harness": info["id"], "ok": False, "models": [], "error": "", "warning": "",
    }
    if info["id"] == "opencode":
        models = vibe_opencode.list_models(binary=target, timeout=timeout, runner=runner)
        result.update(
            ok=models["ok"], models=models["models"],
            error=models.get("error", ""), warning=models.get("warning", ""),
        )
        return result

    code, output = _run(runner, [target, "--list-models"], timeout, environ=environ)
    if code == 127:
        result["error"] = "pi wurde nicht gefunden (PATH prüfen oder installieren)."
    elif code == 124:
        result["error"] = f"Zeitüberschreitung: 'pi --list-models' antwortet nicht innerhalb von {timeout:g} s."
    elif code != 0:
        result["error"] = f"'pi --list-models' endete mit Exit {code}: {_short(output)}"
    else:
        models = _parse_pi_models(output)
        if models:
            result["models"] = models
            result["ok"] = True
        elif NO_MODELS in (output or ""):
            # Pi ist startbar, hat aber noch keinen Anbieter angemeldet.
            result["ok"] = True
            result["warning"] = (
                "Pi meldet keine Modelle. Pi einmal starten und /login ausführen "
                "oder Modelle in Pi konfigurieren."
            )
        elif (output or "").strip():
            result["error"] = f"Ausgabe von 'pi --list-models' nicht erkannt: {_short(output)}"
        else:
            result["ok"] = True
    return result


def _state_default(value=None):
    return (value or os.environ.get("VIBE_STATE")
            or os.environ.get("VIBE_INSTALL") or ".")


def _print_status(data, out=None):
    out = out or sys.stdout
    print("Harness:", data["selected"], file=out)
    for item in data["harnesses"]:
        marker = "*" if item["selected"] else " "
        version = " " + item["version"] if item["version"] else ""
        print(f" {marker} {item['harness']:<9} {item['status']:<8}{version}  {item['message']}", file=out)
        if item["install_command"]:
            print("     Einrichten: " + " ".join(item["install_command"]), file=out)
        if not item["installed"]:
            print("     Hinweis: " + item["hint"], file=out)


def _cmd_run(args):
    prompt = args.prompt
    if args.prompt_file:
        try:
            with open(args.prompt_file, encoding="utf-8") as handle:
                prompt = handle.read()
        except OSError as error:
            print(f"Prompt-Datei nicht lesbar: {error}", file=sys.stderr)
            return 2
    try:
        argv = run_argv(
            args.harness, prompt, args.project,
            agent=args.agent, model=args.model, server_url=args.server_url,
            title=args.title, agents_dir=args.agents_dir, events=args.json,
        )
    except HarnessError as error:
        print("Harness: " + str(error), file=sys.stderr)
        return 2
    try:
        os.execvp(argv[0], argv)
    except FileNotFoundError:
        print(f"Harness-Programm nicht gefunden: {argv[0]}", file=sys.stderr)
        return 127
    except OSError as error:
        print(f"Harness-Programm nicht ausführbar: {argv[0]}: {error}", file=sys.stderr)
        return 126
    # execvp ersetzt das Prozessbild; ein Ende im selben Pythonprozess gibt
    # es nicht. Diese Rückgabe ist konsistenzhalber vorhanden.
    return 126


PLATFORM_INSTRUCTIONS = """## Vibe platform instructions

These rules apply to runner-managed work. User templates and project instructions define how to do the work; they do not replace the runner's handoff requirements.

### Workspace and checks

- Work in the assigned worktree. Preserve unrelated changes. Do not modify the integration checkout, the running installation, or the project's runner settings in `.vibe/project.env`.
- Use the configured checks. Do not change commands, limits, or results to pass a gate. Report what was actually checked and any failure or omission.
- Keep secrets, personal configuration, and temporary artifacts out of commits and reports. A test assignment does not authorize extra paid requests or actions against production systems.
- Prefer the simplest solution that fully meets the requirements. Avoid unrelated changes and speculative abstractions.

### Package evidence and review

- Work on the supplied ticket. Record the acceptance evidence appropriate to the task. The project defines its testing method; a dedicated tester or test-first workflow is not a platform default.
- Obtain the required independent review. The reviewer returns the report; the coordinating agent saves it to `docs/reviews/<ID>-review-<round>.md`.
- The final line of the saved report must be exactly `Verdict: PASS` or `Verdict: CHANGES REQUIRED`, in plain text. A heading, bullet, or bold label is not a substitute. Only PASS permits handoff.
- The coordinator may correct the formatting of an explicit, unambiguous verdict, never the decision. If the verdict is missing or contradictory, ask the reviewer to clarify it.

### Commit and ticket handoff

- The coordinator stages only package changes and required evidence, inspects the staged diff, and commits with a subject starting `<ID>:`. Leave the worktree clean without disturbing unrelated work.
- After the commit exists, update the runner-supplied `TICKET-<ID>.json` in the worktree: set `state` to `done`, set `commit` to the actual hash, and put the verification evidence in `test`. This file is runtime state: do not stage it or edit the central `.vibe/tickets.json`.
- Stop any temporary background processes you started for the task once they are no longer needed. After updating the ticket working copy, give a brief final handoff and end your turn; do not wait for the runner.

### Runner-owned Git operations

- The runner owns worktrees, branches, integration, push, PR creation, merge, and cleanup. Do not perform those actions yourself.
- If the runner returns an in-progress merge conflict, resolve it in the assigned worktree, stage the resolved files, continue that merge, and validate the resolution. Do not start another merge, abort, rebase, or choose one side wholesale.
"""
PLATFORM_INSTRUCTIONS_FILENAME = "platform_instructions.md"


def platform_instructions_path(directory):
    """Zielpfad des versteckten Plattformtexts in ``directory``."""
    return os.path.abspath(os.path.join(directory, PLATFORM_INSTRUCTIONS_FILENAME))


def write_platform_instructions(directory):
    """Schreibt den Plattformtext atomar und liefert den absoluten Pfad.

    GH-76: Der Text liegt außerhalb jedes Projekts und wird opencode als
    zusätzliche ``instructions``-Quelle übergeben. Ein vorhandener Pfad wird
    byte-identisch neu geschrieben; ein Symlink wird abgelehnt, damit nie eine
    fremde Datei verändert wird.
    """
    path = platform_instructions_path(directory)
    if os.path.islink(path):
        raise HarnessError(
            "Plattform-Anweisungen: " + path + " ist ein Symlink und wird nicht verfolgt.")
    os.makedirs(directory, exist_ok=True)
    vibe_storage.write_text(path, PLATFORM_INSTRUCTIONS)
    return path


def main(argv=None):
    """Kommandozeileneinstieg; Rückgabe ist der Prozessende-Code."""
    parser = argparse.ArgumentParser(prog="vibe_harness.py")
    sub = parser.add_subparsers(dest="command", required=True)

    selected = sub.add_parser("selected")
    selected.add_argument("--state", default=None)

    listing = sub.add_parser("list")
    listing.add_argument("--state", default=None)
    listing.add_argument("--json", action="store_true")

    use = sub.add_parser("use")
    use.add_argument("harness")
    use.add_argument("--state", default=None)

    plan = sub.add_parser("setup")
    plan.add_argument("harness", nargs="?")
    plan.add_argument("--state", default=None)
    plan.add_argument("--json", action="store_true")

    models = sub.add_parser("models")
    models.add_argument("--harness", default=None)
    models.add_argument("--state", default=None)
    models.add_argument("--json", action="store_true")

    run = sub.add_parser("run")
    run.add_argument("--harness", required=True)
    run.add_argument("--project", required=True)
    run.add_argument("--agent", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--server-url", default=None)
    run.add_argument("--title", default=None)
    run.add_argument("--agents-dir", default=None)
    run.add_argument("--prompt", default=None)
    run.add_argument("--prompt-file", default=None)
    run.add_argument("--state", default=None)
    # B6: Pi mit strukturiertem Ereignisstrom starten (--mode json). Die
    # Erfassung (F19/F24) setzt diese Argumente; ohne Flag bleibt der
    # Klartext-Print-Modus (bisheriges Verhalten).
    run.add_argument("--json", action="store_true",
                     help="Pi: Ereignisausgabe --mode json ankoppeln")

    platform = sub.add_parser(
        "platform-instructions",
        help="versteckte Plattform-Regeln für opencode-Läufe schreiben (GH-76)")
    platform.add_argument("--directory", required=True)

    args = parser.parse_args(argv)

    if args.command == "platform-instructions":
        try:
            print(write_platform_instructions(args.directory))
        except (HarnessError, OSError, vibe_storage.StorageError) as error:
            print(str(error), file=sys.stderr)
            return 2
        return 0

    if args.command == "selected":
        try:
            print(read_selection(_state_default(args.state)))
            return 0
        except HarnessError as error:
            print(str(error), file=sys.stderr)
            return 2
    if args.command == "list":
        try:
            data = status(_state_default(args.state))
        except HarnessError as error:
            print(str(error), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            _print_status(data)
        return 0
    if args.command == "use":
        try:
            path = write_selection(_state_default(args.state), args.harness)
        except HarnessError as error:
            print(str(error), file=sys.stderr)
            return 2
        print("Harness gespeichert: " + args.harness + " (" + path + ")")
        return 0
    if args.command == "setup":
        try:
            name = args.harness or read_selection(_state_default(args.state))
            data = setup_plan(name)
        except HarnessError as error:
            print(str(error), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("Harness:", data["harness"])
            print("Installiert:", "ja" if data["installed"] else "nein")
            print("Hinweis:", data["hint"])
            print("Offiziell:", data["official"])
            if data["install_command"]:
                print("Einrichten:", " ".join(data["install_command"]))
        return 0
    if args.command == "models":
        try:
            data = list_models(args.harness, state_dir=args.state)
        except HarnessError as error:
            print(str(error), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif data["ok"]:
            for model in data["models"]:
                print(model)
        else:
            print("Modelle nicht lesbar: " + data["error"], file=sys.stderr)
            return 1
        return 0
    if args.command == "run":
        return _cmd_run(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
