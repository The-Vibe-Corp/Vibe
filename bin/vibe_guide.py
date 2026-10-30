#!/usr/bin/env python3
"""Projektassistent für das fachliche Setup neuer Projekte (F9).

Der Assistent führt in festen Schritten durch die fachlichen Grundlagen eines
Projekts und schreibt daraus ``SPEC.md``. Fehlende fachliche Dateien werden aus
den Projektvorlagen ergänzt. Vorhandene Dateien und gefüllte Abschnitte werden
nie still überschrieben: Ein Abschnitt wird nur ersetzt, wenn der Schritt
ausdrücklich in ``replace`` genannt ist.

Für fehlende Angaben kann ein Agent einen Entwurf erzeugen. Der Agent schreibt
nur nach ``.vibe/guide/<schritt>.md``; übernommen wird der Entwurf erst durch
eine ausdrückliche Aktion (``draft_apply``). Der Agentenlauf startet nur auf
Anforderung, verwendet eine Argumentliste ohne Shellverkettung und eine eigene
tmux-Sitzung, damit ein laufender Paket-Agent nicht gestört wird.

Auf FUSE-/NTFS-Dateisystemen sind atomare Ersetzungen und Unix-Rechte nicht
garantiert. Geschrieben wird über die gemeinsame Storage-Schicht
(``vibe_storage.write_text``, V-005); sie verhindert einen halb geschriebenen
Zieldatei-Stand, wo das Dateisystem ``os.replace`` unterstützt, und behauptet
darüber hinaus keine Atomarität.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import vibe_storage

GUIDE_MARK = "<!-- vibe-guide:generated -->"
PLACEHOLDER = "Noch offen – im Projektassistenten ergänzen."
DRAFT_DIR = ".vibe/guide"
DRAFT_REL = DRAFT_DIR + "/{step}.md"
DEFAULT_AGENT = ""
# Das Zeichen "~" kann in einer Paketlauf-Sitzung ("vibe-" + safe(name), nur
# A-Za-z0-9_-) nie vorkommen. Damit kollidiert ein Projekt "proj" nicht mit
# dem Paketlauf eines Projekts "guide-proj".
SESSION_PREFIX = "vibe-guide~"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MAX_ANSWER = 20000
MAX_NOTE = 2000

STEPS = [
    {
        "id": "ziel",
        "title": "Produktziel",
        "heading": "Produktziel",
        "question": "Welches Problem löst das Projekt und welchen Nutzen stiftet es?",
        "help": "Ein bis drei Sätze. Keine technische Lösung, sondern der fachliche Zweck.",
        "required": True,
    },
    {
        "id": "nutzer",
        "title": "Zielgruppe und Nutzung",
        "heading": "Zielgruppe und Nutzung",
        "question": "Wer nutzt das Produkt und in welcher Situation?",
        "help": "Rollen, typische Aufgaben und der Ort der Nutzung.",
        "required": True,
    },
    {
        "id": "umfang",
        "title": "Funktionsumfang",
        "heading": "Funktionsumfang",
        "question": "Welche Funktionen gehören zum Produkt?",
        "help": "Als Liste. Jede Zeile eine überprüfbare Funktion.",
        "required": True,
    },
    {
        "id": "nicht_umfang",
        "title": "Nicht im Umfang",
        "heading": "Nicht im Umfang",
        "question": "Was gehört ausdrücklich nicht dazu?",
        "help": "Grenzen verhindern, dass Agenten den Umfang selbst erweitern.",
        "required": True,
    },
    {
        "id": "umgebung",
        "title": "Zielumgebung",
        "heading": "Zielumgebung",
        "question": "Wo läuft das Produkt?",
        "help": "Betriebssystem, Container, Geräte, Sprachen und Laufzeitumgebung.",
        "required": True,
    },
    {
        "id": "qualitaet",
        "title": "Qualität und Abnahme",
        "heading": "Qualität und Abnahme",
        "question": "Woran erkennt man, dass eine Änderung fertig und gut ist?",
        "help": "Tests, Prüfbefehle und fachliche Abnahmekriterien.",
        "required": True,
    },
    {
        "id": "entscheidungen",
        "title": "Decisions Locked",
        "heading": "Decisions Locked",
        "question": "Welche Entscheidungen sind bereits fixiert?",
        "help": "Nur Entscheidungen, die nicht mehr zur Disposition stehen.",
        "required": False,
    },
    {
        "id": "offene_fragen",
        "title": "Offene Fragen",
        "heading": "Offene Fragen",
        "question": "Welche fachlichen Fragen sind noch offen?",
        "help": "Offene Fragen bleiben sichtbar, bis sie entschieden sind.",
        "required": False,
    },
]

FILES = [
    {"path": "SPEC.md", "label": "Fachliche Wahrheit", "required": True},
    {"path": "TICKETS.md", "label": "Arbeitspakete", "required": True},
    {"path": "AGENTS.md", "label": "Regeln für Agenten", "required": True},
    {"path": "FEEDBACK.md", "label": "Rückmeldungen", "required": True},
    {"path": ".vibe/project.env", "label": "Prüf- und Agentenkonfiguration", "required": True},
    {"path": "README.md", "label": "Projektübersicht", "required": True},
]

STEP_IDS = {entry["id"] for entry in STEPS}


def steps():
    """Kopien der Schritte, damit Aufrufer die Definition nicht verändern."""
    return [dict(entry) for entry in STEPS]


def step(step_id):
    for entry in STEPS:
        if entry["id"] == step_id:
            return dict(entry)
    raise ValueError("Unbekannter Schritt: " + str(step_id))


# ---------- Pfade und Dateien ----------

def _project(project):
    path = os.path.realpath(str(project))
    if not os.path.isdir(path):
        raise ValueError("Projektordner nicht gefunden: " + str(project))
    return path


def _safe_path(project, rel):
    """Ziel innerhalb des Projektordners; Symlinks nach außen werden abgelehnt."""
    base = os.path.realpath(str(project))
    target = os.path.realpath(os.path.join(base, rel))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("Pfad verlässt das Projekt: " + str(rel))
    return target


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def _atomic_write(path, text):
    """Schreibt über die gemeinsame Storage-Schicht (V-005), nie halb geschrieben.

    Die Schicht legt eine temporäre Datei im Zielordner an, übernimmt die
    Rechte einer vorhandenen Datei und ersetzt sie erst nach dem Schreiben.
    Auf Dateisystemen ohne diese Zusicherung (FUSE/NTFS) wird keine
    Atomarität behauptet.
    """
    return vibe_storage.write_text(path, text)


def _sections(text):
    """Ordnet Überschriften (##) ihrem Fließtext zu."""
    result = {}
    matches = list(re.finditer(r"(?m)^##[ \t]+(.+?)[ \t]*$", text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).strip()] = text[start:end]
    return result


def _placeholder():
    return "_" + PLACEHOLDER + "_"


def _clean_value(body):
    stripped = (body or "").strip()
    if stripped in ("", PLACEHOLDER, _placeholder()):
        return ""
    return stripped


def _is_filled(body):
    return _clean_value(body) != ""


def _set_section(text, heading, value):
    """Ersetzt oder ergänzt genau einen Abschnitt; alles andere bleibt erhalten."""
    body = (value or "").strip() or _placeholder()
    pattern = re.compile(r"(?m)^##[ \t]+" + re.escape(heading) + r"[ \t]*$")
    match = pattern.search(text)
    if match:
        start = match.end()
        following = re.search(r"(?m)^##[ \t]", text[start:])
        end = start + following.start() if following else len(text)
        prefix = text[:start].rstrip("\n")
        suffix = text[end:].lstrip("\n")
        parts = [prefix, "", body]
        if suffix:
            parts += ["", suffix]
        return "\n".join(parts).rstrip("\n") + "\n"
    base = text.rstrip("\n")
    if base:
        base += "\n\n"
    return base + "## " + heading + "\n\n" + body + "\n"


def _new_spec(name, answers):
    parts = [
        "# " + name + " — Produktspezifikation",
        "",
        GUIDE_MARK,
        "Status: Entwurf aus dem Projektassistenten. Offene Abschnitte sind mit "
        "„Noch offen“ markiert.",
        "Sprache: Deutsch",
    ]
    for entry in STEPS:
        value = (answers.get(entry["id"]) or "").strip()
        parts += ["", "## " + entry["heading"], "", value or _placeholder()]
    return "\n".join(parts).rstrip("\n") + "\n"


def _readme(name, ziel):
    beschreibung = (ziel or "").strip() or "Kurzbeschreibung im Projektassistenten ergänzen."
    return (
        "# " + name + "\n\n"
        + beschreibung + "\n\n"
        + "## Grundlagen\n\n"
        + "- `SPEC.md` – fachliche Wahrheit\n"
        + "- `TICKETS.md` – Arbeitspakete\n"
        + "- `FEEDBACK.md` – Rückmeldungen\n"
        + "- `AGENTS.md` – Regeln für Agenten\n"
    )


def _project_type(project):
    env = os.path.join(project, ".vibe", "project.env")
    text = _read(env)
    match = re.search(r"(?m)^\s*TYPE\s*=\s*[\"']?([A-Za-z0-9_-]+)", text)
    return match.group(1) if match else "generic"


def _template_source(templates_dir, project_type, rel):
    if not templates_dir:
        return None
    base = os.path.realpath(str(templates_dir))
    kind = project_type if os.path.isdir(os.path.join(base, project_type)) else "generic"
    if rel in ("TICKETS.md", "FEEDBACK.md"):
        return os.path.join(base, "common", rel)
    return os.path.join(base, kind, rel)


def _ensure_files(project, name, answers, templates_dir):
    created, kept, without_template = [], [], []
    project_type = _project_type(project)
    for entry in FILES:
        rel = entry["path"]
        if rel == "SPEC.md":
            continue
        target = _safe_path(project, rel)
        if os.path.exists(target):
            kept.append(rel)
            continue
        if rel == "README.md":
            content = _readme(name, answers.get("ziel", ""))
        else:
            source = _template_source(templates_dir, project_type, rel)
            if not source or not os.path.isfile(source):
                without_template.append(rel)
                continue
            content = _read(source).replace("{{NAME}}", name)
        _atomic_write(target, content)
        created.append(rel)
    return created, kept, without_template


# ---------- Zustand, Entwürfe und Anwenden ----------

def draft_path(project, step_id):
    step(step_id)
    return Path(_safe_path(_project(project), DRAFT_REL.format(step=step_id)))


def _drafts(project):
    out = {}
    for entry in STEPS:
        path = draft_path(project, entry["id"])
        if os.path.exists(path):
            out[entry["id"]] = _read(path)
    return out


def state(project, name=None):
    project = _project(project)
    name = name or os.path.basename(project)
    spec = _safe_path(project, "SPEC.md")
    exists = os.path.exists(spec)
    text = _read(spec)
    sections = _sections(text)
    drafts = _drafts(project)

    out_steps, open_ids = [], []
    filled = total = 0
    for entry in STEPS:
        body = sections.get(entry["heading"], "")
        if not exists:
            status = "fehlt"
        elif _is_filled(body):
            status = "gefüllt"
        else:
            status = "offen"
        if entry["required"]:
            total += 1
            if status == "gefüllt":
                filled += 1
            else:
                open_ids.append(entry["id"])
        out_steps.append({
            "id": entry["id"],
            "title": entry["title"],
            "question": entry["question"],
            "help": entry["help"],
            "heading": entry["heading"],
            "required": entry["required"],
            "status": status,
            "value": _clean_value(body),
            "draft": entry["id"] in drafts,
        })

    files = []
    for entry in FILES:
        target = _safe_path(project, entry["path"])
        files.append({
            "path": entry["path"],
            "label": entry["label"],
            "required": entry["required"],
            "exists": os.path.exists(target),
            "bytes": os.path.getsize(target) if os.path.exists(target) else 0,
        })
    missing = [entry["path"] for entry in files if entry["required"] and not entry["exists"]]
    return {
        "name": name,
        "path": project,
        "spec": "SPEC.md",
        "complete": not open_ids and not missing,
        "filled": filled,
        "total": total,
        "open": open_ids,
        "next": open_ids[0] if open_ids else None,
        "files": files,
        "missing_files": missing,
        "steps": out_steps,
        "drafts": drafts,
    }


def _validate_answers(answers):
    if answers is None:
        answers = {}
    if not isinstance(answers, dict):
        raise ValueError("Antworten müssen ein Objekt sein.")
    cleaned = {}
    for key, value in answers.items():
        if key not in STEP_IDS:
            raise ValueError("Unbekannter Schritt: " + str(key))
        if not isinstance(value, str):
            raise ValueError("Antwort für '" + str(key) + "' muss Text sein.")
        if len(value) > MAX_ANSWER:
            raise ValueError("Antwort für '" + str(key) + "' ist zu lang (höchstens "
                             + str(MAX_ANSWER) + " Zeichen).")
        cleaned[key] = value
    return cleaned


def _validate_replace(replace):
    if replace is None:
        replace = ()
    if isinstance(replace, str) or not isinstance(replace, (list, tuple, set)):
        raise ValueError("'replace' muss eine Liste von Schritten sein.")
    result = []
    for key in replace:
        if key not in STEP_IDS:
            raise ValueError("Unbekannter Schritt: " + str(key))
        result.append(key)
    return result


def apply(project, answers, replace=(), name=None, templates_dir=None):
    project = _project(project)
    name = name or os.path.basename(project)
    answers = _validate_answers(answers)
    replace = _validate_replace(replace)

    spec = _safe_path(project, "SPEC.md")
    existed = os.path.exists(spec)
    text = _read(spec)
    sections = _sections(text)
    written, kept = [], []

    if not existed:
        new_text = _new_spec(name, answers)
        written = [entry["id"] for entry in STEPS if (answers.get(entry["id"]) or "").strip()]
    else:
        new_text = text
        for entry in STEPS:
            if entry["id"] not in answers:
                continue
            value = answers[entry["id"]].strip()
            if not value:
                # Eine leere Antwort löscht nie vorhandenen Inhalt.
                continue
            current = _clean_value(sections.get(entry["heading"], ""))
            if current and entry["id"] not in replace and value != current:
                kept.append(entry["id"])
                continue
            if value == current:
                continue
            new_text = _set_section(new_text, entry["heading"], value)
            written.append(entry["id"])

    spec_written = new_text != text
    if spec_written:
        _atomic_write(spec, new_text)

    created, files_kept, without_template = _ensure_files(project, name, answers, templates_dir)
    if not existed and os.path.exists(spec):
        created.insert(0, "SPEC.md")

    message = (
        "Projektassistent: "
        + str(len(created)) + " Datei(en) angelegt, "
        + str(len(written)) + " Abschnitt(e) geschrieben, "
        + str(len(kept)) + " vorhandene(r) Abschnitt(e) unverändert."
    )
    return {
        "files_created": created,
        "files_kept": files_kept,
        "files_without_template": without_template,
        "sections_written": written,
        "sections_kept": kept,
        "spec_written": spec_written,
        "message": message,
        "state": state(project, name=name),
    }


# ---------- Agentenunterstützung ----------

def _project_agent(project):
    text = _read(os.path.join(project, ".vibe", "project.env"))
    match = re.search(r"(?m)^\s*AGENT\s*=\s*(.*)$", text)
    agent = (match.group(1).strip().strip("\"'") if match else "") or DEFAULT_AGENT
    if not agent:
        raise ValueError("Kein Agent konfiguriert: AGENT in .vibe/project.env setzen.")
    if not NAME_RE.match(agent):
        raise ValueError("Agentenname: nur Buchstaben, Ziffern, _ und - "
                         "(keine Leerzeichen oder Shellzeichen).")
    return agent


def agent_prompt(project, step_id, name=None, note=""):
    project = _project(project)
    name = name or os.path.basename(project)
    entry = step(step_id)
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise ValueError("Hinweis muss Text sein.")
    note = note.strip()
    if len(note) > MAX_NOTE:
        raise ValueError("Hinweis ist zu lang (höchstens " + str(MAX_NOTE) + " Zeichen).")
    current = ""
    for item in state(project, name=name)["steps"]:
        if item["id"] == step_id:
            current = item["value"]
            break
    draft_rel = DRAFT_REL.format(step=step_id)
    lines = [
        'Du unterstützt das fachliche Setup des Projekts "' + name + '".',
        "Projektordner: " + project,
        'Aufgabe: Entwirf ausschließlich den Abschnitt "' + entry["title"] + '" für SPEC.md.',
        "Leitfrage: " + entry["question"],
    ]
    if note:
        lines.append("Hinweis des Nutzers: " + note)
    lines += [
        "Bisheriger Stand des Abschnitts:",
        current or "(noch leer)",
        "",
        "Regeln:",
        "- Erfinde keine Tatsachen und keine Anforderungen.",
        '- Was du nicht belegen kannst, markierst du ausdrücklich als "UNBEKANNT".',
        "- Schreibe nur den Fließtext des Abschnitts, ohne Überschrift und ohne Codeblock.",
        "- Ändere keine anderen Dateien.",
        "Schreibe das Ergebnis in die Datei: " + draft_rel,
    ]
    return "\n".join(lines)


def _tmux_has(session):
    if shutil.which("tmux") is None:
        return False
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _default_runner(argv):
    try:
        result = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return 127, "Programm nicht gefunden: " + str(argv[0])
    except subprocess.TimeoutExpired:
        return 124, "Zeitüberschreitung beim Start des Agentenauftrags."
    return result.returncode, (result.stdout or "").strip()


def _session(name):
    return SESSION_PREFIX + re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _log_path(project, name, log_dir):
    if log_dir:
        folder = os.path.realpath(str(log_dir))
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, re.sub(r"[^A-Za-z0-9_-]", "_", name) + ".guide.log")
    return os.path.join(project, DRAFT_DIR, "agent.log")


def _sandbox_command(project, command):
    """Wendet die F7-Sandbox an; ``.vibe/guide`` bleibt als Ausgabe schreibbar.

    ``vibe_sandbox.bwrap_argv()`` bindet das ganze ``.vibe``-Verzeichnis nach
    dem Projekt-Bind wieder read-only, damit der Agent seine eigene
    Konfiguration nicht ändern kann. Der Entwurfsordner ist die einzige
    Ausgabe des Assistenten und wird deshalb nach diesem Read-only-Bind gezielt
    schreibbar gebunden. Alles andere unter ``.vibe`` bleibt geschützt.
    """
    try:
        import vibe_sandbox
    except ImportError as error:
        raise ValueError(
            "Sandbox-Modul fehlt; der Agentenauftrag startet nicht ungeschützt."
        ) from error
    state = vibe_sandbox.status(project)
    if not state["enabled"]:
        return command
    checked = vibe_sandbox.check(project)
    if not checked["ok"]:
        raise ValueError(
            "Sandbox ist eingeschaltet, aber nicht startbar: "
            + str(checked.get("message") or "unbekannter Fehler")
        )
    argv = vibe_sandbox.bwrap_argv(project, command)
    folder = _safe_path(project, DRAFT_DIR)
    os.makedirs(folder, exist_ok=True)
    try:
        marker = argv.index("--")
    except ValueError as error:
        raise ValueError("Sandbox-Befehl ohne Argumenttrenner.") from error
    argv[marker:marker] = ["--bind", folder, folder]
    return argv


def _agent_command(project, agent, title, prompt):
    """Baut den Agentenbefehl; bei aktiver Sandbox fail-closed über bubblewrap."""
    command = [
        "opencode", "run", "--standalone", "--auto", "--thinking",
        "--agent", agent, "--title", title, prompt,
    ]
    return _sandbox_command(project, command)


def start_agent(project, step_id, name=None, note="", agent=None,
                log_dir=None, runner=None, tmux_has=None):
    project = _project(project)
    name = name or os.path.basename(project)
    step(step_id)
    agent = agent or _project_agent(project)
    if not NAME_RE.match(agent or ""):
        raise ValueError("Agentenname: nur Buchstaben, Ziffern, _ und - "
                         "(keine Leerzeichen oder Shellzeichen).")
    prompt = agent_prompt(project, step_id, name=name, note=note)
    session = _session(name)
    has = tmux_has or _tmux_has
    if has(session):
        raise ValueError("Für " + name + " läuft bereits ein Assistenten-Auftrag (" + session + ").")

    folder = _safe_path(project, DRAFT_DIR)
    os.makedirs(folder, exist_ok=True)

    log = _log_path(project, name, log_dir)
    title = name + " Guide " + step_id
    command = _agent_command(project, agent, title, prompt)
    # Projektumgebung wie im Paketlauf laden, aber den Befehl als Argumentliste
    # ausführen. Ein vorhandener Entwurf bleibt bei einem Startfehler erhalten.
    inner = (
        'source ~/.bashrc; '
        'if [ -f .vibe/project.env ]; then set -a; . ./.vibe/project.env; set +a; fi; '
        'log="$1"; shift; "$@" 2>&1 | tee -a "$log"'
    )
    argv = [
        "tmux", "new-session", "-d", "-s", session, "-c", project,
        "bash", "-lc", inner, "vibe-guide", log,
    ] + command
    target = _safe_path(project, DRAFT_REL.format(step=step_id))
    # Ein alter Entwurf wird vor dem Start beiseitegelegt, nicht danach
    # gelöscht: Ein schneller Agent kann die Datei bereits geschrieben haben,
    # ein späteres Löschen würde seinen frischen Entwurf entfernen.
    previous = _read(target) if os.path.exists(target) else None
    if previous is not None:
        os.unlink(target)
    run = runner or _default_runner
    try:
        code, output = run(argv)
    except Exception:
        if previous is not None and not os.path.exists(target):
            _atomic_write(target, previous)
        raise
    if code != 0:
        if previous is not None and not os.path.exists(target):
            _atomic_write(target, previous)
        raise ValueError(output or "Agentenlauf konnte nicht gestartet werden.")
    return {
        "session": session,
        "agent": agent,
        "log": log,
        "draft": DRAFT_REL.format(step=step_id),
    }


def _tail(path, limit=40):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 60000))
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()[-limit:]


def agent_status(project, name=None, log_dir=None, tmux_has=None):
    project = _project(project)
    name = name or os.path.basename(project)
    session = _session(name)
    has = tmux_has or _tmux_has
    try:
        agent = _project_agent(project)
    except ValueError:
        agent = ""
    log = _log_path(project, name, log_dir)
    return {
        "session": session,
        "running": has(session),
        "agent": agent,
        "log": log if os.path.exists(log) else "",
        "log_tail": _tail(log),
        "drafts": _drafts(project),
    }


def _draft_body(text, title):
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
    lines = text.splitlines()
    if lines and re.match(r"^#{1,6}[ \t]+", lines[0]):
        # Die Abschnittsüberschrift setzt apply(); ein doppeltes ## wäre falsch.
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return _shift_inner_headings(body)


def _shift_inner_headings(body):
    """Setzt innere ``##``-Überschriften eine Ebene tiefer, Codebeispiele nicht.

    Innere Überschriften der zweiten Ebene würden beim nächsten Lesen als
    eigene SPEC-Abschnitte gelten. Zeilen innerhalb eines eingezäunten
    Codeblocks (``` oder ~~~) bleiben wortgleich, damit Beispiele nicht
    verfälscht werden.
    """
    out, fence = [], ""
    for line in body.splitlines():
        stripped = line.lstrip()
        if fence:
            out.append(line)
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            out.append(line)
            continue
        out.append(re.sub(r"^##([ \t]+)", r"###\1", line))
    return "\n".join(out)


def draft_apply(project, step_id, name=None, templates_dir=None):
    project = _project(project)
    name = name or os.path.basename(project)
    entry = step(step_id)
    target = _safe_path(project, DRAFT_REL.format(step=step_id))
    if not os.path.exists(target):
        raise ValueError("Kein Entwurf für Schritt '" + entry["title"] + "' vorhanden.")
    body = _draft_body(_read(target), entry["title"])
    if not body:
        raise ValueError("Entwurf für Schritt '" + entry["title"] + "' ist leer.")
    result = apply(project, {step_id: body}, replace=[step_id], name=name,
                   templates_dir=templates_dir)
    os.unlink(target)
    return result


def draft_discard(project, step_id):
    project = _project(project)
    entry = step(step_id)
    target = _safe_path(project, DRAFT_REL.format(step=step_id))
    if not os.path.exists(target):
        raise ValueError("Kein Entwurf für Schritt '" + entry["title"] + "' vorhanden.")
    os.unlink(target)
    return True
