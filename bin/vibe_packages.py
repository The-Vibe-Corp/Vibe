#!/usr/bin/env python3
"""Paketauswahl und Abschlussschranke für den vibe-Paketläufer.

Der Läufer benutzt dieses Modul, damit Auswahl, Vorabprüfung, Bewertung des
Agentenergebnisses und Abschlussbericht versioniert und testbar sind. Die
Datei arbeitet ansonsten ausschließlich lokal: keine Modellaufrufe, keine
Netzverbindung. Seit B16 liefert ``branch-name`` den Branch-Namen eines Pakets
nach den Repository-Regeln. Ausnahme seit AP9: Die Unterbefehle ``github-pull``
(Aktualisierung des Haupt-Branches vor einem Arbeitspaket) und
``github-complete`` (Push und Merge-Request nach dem Abschluss) nutzen die
GitHub-Ebene aus ``vibe_github`` — nur wenn das Projekt dies ausdrücklich
konfiguriert hat (``GITHUB_ENABLED``), sonst überspringen sie bewusst.
Sie schreibt nur den projektlokalen Auswahlstand unter ``.vibe/tmp/``; der
Paketabschluss wird seit GH-48 in den Ticketspeicher ``.vibe/tickets.json``
übernommen. Die Arbeitskopie erhält das aktuelle Ticket als sichtbare Datei
``TICKET-<ID>.json`` und eine Kopie der Arbeitsnotiz ``AGENTS.md``.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if os.path.dirname(os.path.realpath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import vibe_tickets  # pylint: disable=wrong-import-position
EXIT_OK = 0
EXIT_NONE = 1
EXIT_USAGE = 2


def _github_module():
    """Lädt die GitHub-Ebene träge (AP9).

    Das Modul liegt im selben Verzeichnis wie dieses Skript. In Teil-
    installationen (Prüfumgebungen, ältere Toolchains) kann ``vibe_github.py``
    fehlen; dann dürfen die übrigen Subkommandos (gate, copy-notes, select)
    nicht beeinträchtigt werden. Die GitHub-Befehle melden das als klar
    benannten Fehlschlag statt das ganze Skript abbrechen zu lassen."""
    try:
        import vibe_github  # pylint: disable=import-outside-toplevel
    except ImportError as error:
        raise SystemExit(
            "GitHub-Befehl nicht verfügbar: vibe_github.py fehlt in der "
            "Installation (" + str(error) + ")") from error
    return vibe_github

# F22: Ein blockierter Preflight darf den Nutzer über F16 nach einer
# Entscheidung fragen. Die Assistenz ist nur im Produktpfad ``vibe run``
# aktiv; ein direkter Läuferaufruf und Tests ohne die Variable bleiben beim
# bisherigen sofortigen Abbruch.
ASSIST_OPTIONS = ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"]
ASSIST_AGENT_OPTION = 2
ASSIST_DEFAULT_TIMEOUT = 600.0
ASSIST_MAX_ROUNDS = 10
# Im autonomen Modus gibt es keine Rückfrage. Der Preflight beauftragt den
# Agenten deshalb genau einmal mit den Befunden; bleibt der Befund bestehen,
# blockiert der Lauf mit dem letzten Stand.
ASSIST_AUTONOMOUS_REPAIR_ROUNDS = 1
# AP10: Feste Optionen der Schranken-Rückfrage an blockierten Paketen. Die
# Nummerierung ist nullbasiert (wie in vibe_questions.answer): 0 überspringt
# das Paket, 1 bricht den Lauf ab, 2 beauftragt den Agenten; Freitext hat
# Vorrang und wird als Anweisung übergeben.
BARRIER_OPTIONS = [
    "Paket überspringen und Lauf fortsetzen",
    "Lauf abbrechen",
    "Agent behebt die Befunde",
]
BARRIER_SKIP_OPTION = 0
BARRIER_ABORT_OPTION = 1
BARRIER_AGENT_OPTION = 2

# GH-48: Keine Markdown-Marker mehr — Zustand, Priorität und Abhängigkeiten
# sind Felder im Ticketspeicher (.vibe/tickets.json). Die Kennungsform bleibt
# für Branch-Namen und Platzhalter relevant.
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\d+")
# Agentennamen werden wie im Läufer und in der Agentenverwaltung geprüft.
# profiles.json ist Nutzerzustand; ein Name mit Pfadanteilen darf nie in eine
# Dateiprüfung außerhalb der Agentenordner führen.
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VERDICT_PATTERN = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?verdict\s*:\s*\**\s*PASS\b"
)

# Arbeitsnotizen sind Laufzeitstand, kein versionierter Produktinhalt. Seit
# GH-48 ist AGENTS.md die einzige Arbeitsnotiz; die getrennten Ledger
# TICKETS.md/FEEDBACK.md sind entfallen. Die sichtbare Einzeldatei
# TICKET-<ID>.json am Projektstamm zählt ebenso als Laufzeitstand.
WORK_NOTE_FILES = ("AGENTS.md",)
# Projekt-spezifische Regeldatei: Sie ist nicht immer versioniert, soll aber
# wie die Arbeitsnotizen in die Paket-Arbeitskopie übernommen werden (B2).
PROJECT_RULES_FILE = "AGENTS.md"
WORK_COPY_FILES = WORK_NOTE_FILES
# GH-48: Sichtbare Ticketdatei am Projektstamm (Laufzeitstand, nie committet).
TICKET_FILE_RE = re.compile(r"^TICKET-[A-Za-z0-9_.-]+\.json$")
# AP5: .vibe/project.env ist Laufzeitstand wie die Arbeitsnotizen, wird aber
# nur read-only einwegig in die Arbeitskopie transportiert. Die Datei des
# Hauptprojekts bleibt autoritativ; .vibe/_secrets.env wird nie transportiert.
# GH-46: Der AP7-Baseline-Transport ist entfallen; Arbeitskopien beziehen die
# Baseline aus der committeten tests/verify-baseline.json des Branchs (der
# lokale Bootstrap-Vorschlag ist ephemeral und wird nicht dauerhaft transportiert).
PROJECT_ENV_REL = os.path.join(".vibe", "project.env")
TRANSPORTED_PATHS = (PROJECT_ENV_REL,)

QUOTA_PATTERNS = (
    r"\bquota\b",
    r"rate[\s_-]?limit",
    r"insufficient[_\s-]?(?:quota|credits?)",
    r"\b429\b",
    r"too many requests",
    r"out of credits?",
)
AUTH_PATTERNS = (
    r"\b401\b",
    r"\b403\b",
    r"unauthori[sz]ed",
    r"forbidden",
    r"invalid[_\s-]?api[_\s-]?key",
    r"authentication (?:failed|required)",
)
NETWORK_PATTERNS = (
    r"\b(?:econnreset|econnrefused|etimedout|eai_again|enotfound|epipe)\b",
    r"network (?:error|unreachable)",
    r"connection (?:reset|refused|closed|timed out)",
    r"temporary failure in name resolution",
    r"\b50[234]\b",
    r"timed? out",
    r"timeout",
)


def read_text(path):
    """Liest eine Datei als Text; bei Lesefehler eine leere Zeichenkette."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def write_text_atomic(path, text):
    """Schreibt Text über eine temporäre Datei, damit kein Halbstand bleibt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def run_git(project, *args):
    """Führt Git im Projektordner aus; Aufrufer werten den Exitcode aus."""
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        check=False,  # bewusst: fehlgeschlagene Prüfungen werten die Aufrufer über returncode aus
    )


def is_work_note_path(path):
    """True, wenn ein Git-Statuspfad eine Arbeitsnotiz im Projektstamm ist."""
    value = path.strip().strip('"').replace("\\", "/")
    if " -> " in value:
        value = value.split(" -> ", 1)[1].strip().strip('"')
    # Nur Dateien am Projektstamm; gleichnamige Dateien in Unterordnern sind
    # normale Projektdateien. AGENTS.md ist Arbeitsnotiz (B2); die sichtbare
    # Ticketdatei TICKET-<ID>.json ist Laufzeitstand (GH-48).
    if value in WORK_COPY_FILES:
        return True
    return "/" not in value and bool(TICKET_FILE_RE.match(value))


def dirty_report(project):
    """Git-Status ohne Arbeitsnotizen; andere Änderungen bleiben sichtbar."""
    status = run_git(project, "status", "--porcelain")
    if status.returncode != 0:
        return ""
    return "\n".join(
        line
        for line in status.stdout.splitlines()
        if not (len(line) > 3 and is_work_note_path(line[3:]))
    )


def _file_has_uncommitted_changes(project, name):
    """True, wenn ``name`` im Projekt gestagt oder ungestagt geändert ist."""
    for extra in (("--name-only",), ("--name-only", "--cached")):
        result = run_git(project, "diff", *extra, "--", name)
        if result.returncode == 0 and name in result.stdout.splitlines():
            return True
    return False


def copy_work_notes(project, worktree):
    """Kopiert vorhandene Arbeitsnotizen in die Paket-Arbeitskopie.

    F27: Eine uncommittet geänderte ``AGENTS.md`` gehört dem Nutzer. Sie wird
    weder kopiert noch im Paketbranch committet noch vom Abschluss-Merge
    überschrieben; der Paketbranch arbeitet mit dem committeten Stand (die
    Arbeitskopie entsteht ohnehin aus HEAD). Rückgabe: (copied, skipped).
    """
    project, worktree = Path(project), Path(worktree)
    copied, skipped = [], []
    for name in WORK_COPY_FILES:
        source = project / name
        if not source.is_file():
            continue
        if name == PROJECT_RULES_FILE and _file_has_uncommitted_changes(
                project, name):
            skipped.append(name)
            continue
        write_text_atomic(worktree / name, read_text(source))
        copied.append(name)
    return copied, skipped


def _exclude_rel_paths(worktree, rel_paths):
    """Trägt die Relativpfade idempotent in die Git-Exclude des Worktrees ein.

    Liefert ``False`` bei einem Git- oder Schreibfehler, ohne zu werfen; die
    transportierten Dateien bleiben davon unberührt.
    """
    result = run_git(worktree, "rev-parse", "--git-path", "info/exclude")
    if result.returncode != 0:
        return False
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = worktree / path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        stripped = {line.strip() for line in lines}
        additions = [rel for rel in rel_paths if rel not in stripped]
        if not additions:
            return True
        with open(path, "a", encoding="utf-8") as handle:
            if lines and lines[-1].strip():
                handle.write("\n")
            handle.write("\n".join(additions) + "\n")
        return True
    except OSError:
        return False


def transport_project_env(project, worktree):
    """Transportiert ``.vibe/project.env`` read-only einwegig in die
    Arbeitskopie (AP5).

    Für die vorhandene Quelldatei wird ``<worktree>/.vibe/`` angelegt, der
    Inhalt 1:1 kopiert und best effort schreibgeschützt (0444). Danach wird der
    transportierte Pfad idempotent in die Git-Exclude des Worktrees
    eingetragen. Ohne Quelldatei geschieht nichts — insbesondere entsteht kein
    ``.vibe/``-Ordner. Transportiert wird ausschließlich diese eine Datei;
    ``_secrets.env`` und andere ``.vibe/``-Dateien bleiben zurück. Liefert
    ``(transported_paths, exclude_ok)``.
    """
    project, worktree = Path(project), Path(worktree)
    transported = []
    for rel in TRANSPORTED_PATHS:
        source = project / rel
        if not source.is_file():
            continue
        target = worktree / rel
        write_text_atomic(target, read_text(source))
        # Best effort Schreibschutz: auf FUSE/NTFS können Unix-Rechte wirkungslos
        # sein; ein OSError ist dort kein Transportfehler (SPEC-Konvention).
        try:
            os.chmod(target, 0o444)
        except OSError:
            pass
        transported.append(rel)
    if not transported:
        return transported, True
    return transported, _exclude_rel_paths(worktree, transported)


def transport_ticket(project, worktree, pid):
    """Schreibt das aktuelle Ticket als ``TICKET-<ID>.json`` in die Arbeitskopie.

    Die Datei liegt sichtbar in der Wurzel und wird idempotent in die
    Git-Exclude des Worktrees eingetragen (best effort). Fehlt das Ticket im
    Projekt-Speicher, liefert ``(False, True)`` und legt nichts an.
    """
    project, worktree = Path(project), Path(worktree)
    record = vibe_tickets.find(vibe_tickets.load(project), pid)
    if record is None:
        return False, True
    name = vibe_tickets.ticket_file_name(pid)
    vibe_tickets.write_ticket_file(worktree / name, record)
    exclude_ok = _exclude_rel_paths(worktree, [name])
    return True, exclude_ok


def sync_ticket(project, worktree, pid, require_commit=True):
    """Übernimmt den Abschluss (state/commit/test/pr_url) in den Ticketspeicher.

    Quelle ist ``<worktree>/TICKET-<ID>.json``; Ziel ist der Projekt-Speicher.
    Der Nachweis wird nur übernommen, wenn er vollständig ist. Liefert
    ``(changed, message)``; bei ``changed=False`` bleibt der Speicher
    unverändert. Mit ``require_commit=False`` (``package close``) entfällt die
    Prüfung auf einen im Projekt vorhandenen Nachweis-Commit.
    """
    project, worktree = Path(project), Path(worktree)
    source = worktree / vibe_tickets.ticket_file_name(pid)
    if not source.is_file():
        return False, "Ticket-Datei " + str(source) + " fehlt in der Arbeitskopie."
    try:
        record = vibe_tickets.read_ticket_file(source)
    except ValueError as error:
        return False, "Ticket-Datei ist nicht lesbar: " + str(error)
    if record.get("state") != "done":
        return False, "Ticket " + pid + " ist in der Arbeitskopie nicht erledigt."
    commit = record.get("commit") or ""
    if require_commit and not commit_exists(project, commit):
        return False, "Nachweis-Commit für " + pid + " fehlt oder ist nicht vorhanden."
    if vibe_tickets.find(vibe_tickets.load(project), pid) is None:
        return False, "Ticket " + pid + " fehlt im Ticketspeicher."
    vibe_tickets.update(project, pid, state="done", commit=commit,
                        test=record.get("test") or "",
                        pr_url=record.get("pr_url") or "",
                        blocked_reason="", waiting_note="")
    return True, pid + " in den Ticketspeicher übernommen."


def read_env(path):
    """Liest ``SCHLUESSEL=WERT``-Zeilen aus einer Env-Datei."""
    values = {}
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def commit_exists(project, revision):
    """True, wenn der Commit im Projektordner vorhanden ist."""
    if not revision:
        return False
    return run_git(project, "cat-file", "-e", revision + "^{commit}").returncode == 0


def commit_subject(project, revision):
    """Liefert die Betreffzeile eines Commits oder ``""``."""
    if not revision:
        return ""
    result = run_git(project, "log", "-1", "--format=%s", revision)
    return result.stdout.strip() if result.returncode == 0 else ""


def commit_is_ancestor(project, revision, base):
    """True, wenn ``revision`` bereits im Stand ``base`` enthalten ist."""
    if not revision or not base:
        return False
    return (
        run_git(project, "merge-base", "--is-ancestor", revision, base).returncode
        == 0
    )


def priority(record):
    """Priorität als Zahl (0-8); ohne Angabe 9 (hinter allen genannten)."""
    value = (record.get("priority") or "").strip()
    match = re.fullmatch(r"P(\d)", value)
    return int(match.group(1)) if match else 9


ORDER_KEY = "PACKAGE_ORDER"
ORDER_SPLIT = re.compile(r"[,;\s]+")

# B16: Paket-Branches folgen den Repository-Regeln. Das Muster kommt aus
# .vibe/project.env (PACKAGE_BRANCH_PATTERN), der Standard gilt ohne Eintrag.
DEFAULT_PACKAGE_BRANCH_PATTERN = "feature/{owner}/{id}"
PACKAGE_BRANCH_PATTERN_KEY = "PACKAGE_BRANCH_PATTERN"
BRANCH_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
MAX_BRANCH_LENGTH = 200
MAX_BRANCH_COLLISIONS = 100
BRANCH_SEGMENT_RE = re.compile(r"^[a-z0-9-]+$")


def package_order(project):
    """Je Projekt konfigurierte Priorisierung, Dubletten in Eintragsreihenfolge.

    Gelesen wird ``PACKAGE_ORDER`` aus ``.vibe/project.env``. Trenner sind
    Komma, Semikolon und Leerraum. Eine fehlende oder leere Einstellung
    bedeutet: keine Priorisierung, der Läufer wählt nach Standardordnung.
    Unbekannte Kennungen bleiben stehen; sie werden bei der Auswahl
    übersprungen und beim Ablegen über die Oberfläche bzw. CLI abgelehnt.
    """
    values = read_env(Path(project) / ".vibe" / "project.env")
    order, seen = [], set()
    for token in ORDER_SPLIT.split(values.get(ORDER_KEY, "")):
        if token and token not in seen:
            seen.add(token)
            order.append(token)
    return order


def _kebab(value):
    """Kleinbuchstaben; jeder Lauf von Nicht-[a-z0-9] wird ein Bindestrich."""
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _package_title(project, pid):
    """Tickettitel aus dem Ticketspeicher; leerer Wert, wenn unbekannt."""
    record = vibe_tickets.find(vibe_tickets.load(project), pid)
    return (record.get("title") or "") if record else ""


def _validate_branch_name(name):
    """Prüft einen Branch-Namen gegen die Repository-Regeln (B16)."""
    if not name or len(name) > MAX_BRANCH_LENGTH:
        raise ValueError(
            "Branch-Name ist leer oder länger als " + str(MAX_BRANCH_LENGTH)
            + " Zeichen: " + repr(name))
    if ".." in name or name.endswith(".lock"):
        raise ValueError("Branch-Name enthält unerlaubte Zeichenfolgen: " + name)
    segments = name.split("/")
    if any(not segment for segment in segments):
        raise ValueError("Branch-Name enthält ein leeres Segment: " + name)
    if any(not BRANCH_SEGMENT_RE.match(segment) for segment in segments):
        raise ValueError(
            "Branch-Name darf nur Kleinbuchstaben, Ziffern und Bindestriche "
            "enthalten ('/' trennt Segmente): " + name)
    if any(segment.startswith("-") or segment.endswith("-")
           for segment in segments):
        raise ValueError(
            "Branch-Segment darf nicht mit einem Bindestrich beginnen oder "
            "enden: " + name)


def package_branch_name(project, pid, pattern=None):
    """Branch-Name eines Pakets nach dem konfigurierten Muster (B16).

    Platzhalter sind ``{owner}`` (lokales ``git config user.name``,
    Fallback ``vibe``), ``{id}`` und ``{slug}`` (Tickettitel, auf 24 Zeichen
    gekürzt). Ein ungültiges Muster oder Ergebnis wirft ``ValueError``; lokale
    Kollisionen werden mit ``-2``, ``-3``, ... aufgelöst.
    """
    if pattern is None:
        values = read_env(Path(project) / ".vibe" / "project.env")
        pattern = values.get(PACKAGE_BRANCH_PATTERN_KEY) or \
            DEFAULT_PACKAGE_BRANCH_PATTERN
    if not str(pattern).strip():
        raise ValueError("Ungültiges Branch-Muster: Muster ist leer.")

    owner = _kebab(run_git(project, "config", "--get", "user.name").stdout.strip()) \
        or "vibe"
    slug = _kebab(_package_title(project, pid))[:24].rstrip("-") or "paket"
    replacements = {
        "owner": owner,
        "id": _kebab(pid),
        "slug": slug,
    }

    def substitute(match):
        key = match.group(1)
        if key not in ("owner", "id", "slug"):
            raise ValueError("Unbekanntes Platzhalter-Muster im Branch-Muster: "
                             + "{" + key + "}")
        return replacements[key]

    name = BRANCH_PLACEHOLDER_RE.sub(substitute, str(pattern))
    _validate_branch_name(name)

    # AP4 (T-G5): Auch Fern-Refs (refs/remotes/origin/...) und in einer
    # Arbeitskopie ausgecheckte Branches sind Kollisionen — nicht nur lokale
    # refs/heads/. Die Worktree-Liste wird einmal gelesen und wiederverwendet.
    worktree_branches = set()
    listing = run_git(project, "worktree", "list", "--porcelain")
    if listing.returncode == 0:
        for line in listing.stdout.splitlines():
            if line.startswith("branch "):
                branch = line[len("branch "):].strip()
                if branch.startswith("refs/heads/"):
                    branch = branch[len("refs/heads/"):]
                worktree_branches.add(branch)

    for attempt in range(1, MAX_BRANCH_COLLISIONS + 1):
        candidate = name if attempt == 1 else name + "-" + str(attempt)
        if len(candidate) > MAX_BRANCH_LENGTH:
            break
        exists = (
            run_git(project, "rev-parse", "--verify", "--quiet",
                    "refs/heads/" + candidate).returncode == 0
            or run_git(project, "rev-parse", "--verify", "--quiet",
                       "refs/remotes/origin/" + candidate).returncode == 0
            or candidate in worktree_branches
        )
        if not exists:
            return candidate
    raise ValueError(
        "Kein freier Branch-Name für " + name + " nach "
        + str(MAX_BRANCH_COLLISIONS) + " Versuchen gefunden.")


def select_package(project, skip=None, state_path=None, prefer=""):
    """Liefert das nächste offene Paket oder ``None``.

    Steht in ``.vibe/project.env`` eine Priorisierung (``PACKAGE_ORDER``),
    wählt der Läufer zuerst den ersten Eintrag dieser Liste, der offen, nicht
    übersprungen und bereit ist; er ist damit verbindlich vor der
    Standardordnung. Erledigte, blockierte, wartende, abhängigkeitsgeblockte
    oder unbekannte Einträge werden der Priorisierung entnommen, ohne die Wahl
    aufzuhalten. Ohne geeigneten Eintrag gilt die Standardordnung: Kandidaten
    sind ``open`` und ``in-progress``; sortiert wird nach Priorität (P0..P8,
    ohne Angabe hinten) und dann nach der Position im Ticketspeicher. Ein
    Paket wird nur gewählt, wenn alle bekannten Abhängigkeiten erledigt sind.

    ``prefer`` (AP4/T-W1) nennt ein ausdrücklich bevorzugtes Paket (Reattach):
    Ist es im Kandidatenbestand und noch nicht erledigt, wird es vorrangig
    gewählt — auch wenn es als blockiert vermerkt ist (bewusste
    Nutzer-Intention). Sonst wird ``prefer`` ignoriert und normal gewählt.
    """
    project = Path(project)
    if isinstance(skip, str):
        skip = {item for item in skip.split(",") if item}
    else:
        skip = set(skip or [])
    tickets = vibe_tickets.load(project)
    located = {}
    for record in tickets:
        pid = record.get("id")
        if pid and pid not in located:
            located[pid] = record
    done = {pid for pid, record in located.items()
            if record.get("state") == "done"}

    def _ready(pid):
        record = located[pid]
        if record.get("state") not in ("open", "in-progress"):
            return False
        return not any(
            dep in located and dep not in done
            for dep in (record.get("dependencies") or [])
        )

    chosen = None
    preferred = str(prefer or "").strip()
    if (preferred and preferred in located
            and preferred not in done and preferred not in skip):
        chosen = (preferred, False)
    if chosen is None:
        for pid in package_order(project):
            if pid in skip or pid not in located or not _ready(pid):
                continue
            chosen = (pid, True)
            break
    if chosen is None:
        candidates = []
        for index, record in enumerate(tickets):
            pid = record.get("id")
            if not pid or pid in skip or not _ready(pid):
                continue
            key = (priority(record), index)
            candidates.append((key, pid))
        if candidates:
            candidates.sort(key=lambda item: item[0])
            chosen = (candidates[0][1], False)
    if chosen is None:
        return None
    pid, ordered = chosen
    record = located[pid]
    selected = {
        "id": pid,
        "type": record.get("type"),
        "title": record.get("title"),
        "description": record.get("description") or "",
        "priority": record.get("priority") or "",
        "ordered": ordered,
        "github": record.get("github"),
    }
    target = Path(state_path) if state_path else project / ".vibe" / "tmp" / "next-package.json"
    write_text_atomic(target, json.dumps(selected, ensure_ascii=False, indent=1) + "\n")
    return selected


def agent_available(name, project, agents_dir):
    """True, wenn die Agentendatei im Projekt oder im globalen Ordner liegt."""
    if not name:
        return False
    candidates = [
        Path(project) / ".opencode" / "agents" / (name + ".md"),
        Path(agents_dir) / (name + ".md"),
    ]
    return any(candidate.is_file() for candidate in candidates)


def ensure_project_exclude(project):
    """Hält Auswahlstand und Arbeitsnotizen aus dem Git-Status heraus.

    Die Notizen bleiben so auch dann unsichtbar, wenn sie (noch) nicht
    versioniert sind; ein späteres ``git add`` ist weiterhin möglich.
    """
    git_dir = run_git(project, "rev-parse", "--absolute-git-dir")
    if git_dir.returncode != 0:
        return
    exclude = Path(git_dir.stdout.strip()) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = read_text(exclude).splitlines()
    missing = [
        entry for entry in (".vibe/tmp/", ".vibe/") + WORK_NOTE_FILES
        if entry not in lines
    ]
    if missing:
        text = read_text(exclude)
        if text and not text.endswith("\n"):
            text += "\n"
        write_text_atomic(exclude, text + "\n".join(missing) + "\n")


def role_agents(state_dir, role):
    """Namen der Agenten mit dieser Rolle aus ``<state_dir>/profiles.json``.

    Die Reihenfolge der Datei bleibt erhalten. Eine fehlende oder unlesbare
    Datei ist kein Fehler, sondern liefert keine Kandidaten; der Aufrufer
    meldet dann wie bisher die fehlende Zuordnung.
    """
    if not state_dir:
        return []
    try:
        with open(Path(state_dir) / "profiles.json", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    roles = data.get("rollen") if isinstance(data, dict) else None
    if not isinstance(roles, dict):
        return []
    return [
        name for name, value in roles.items()
        if isinstance(name, str) and value == role and AGENT_NAME_PATTERN.match(name)
    ]


def agent_for_role(role, state_dir, project, agents_dir):
    """Erster verfügbarer Agent mit dieser Rolle, sonst erster Kandidat.

    Ein veralteter Rolleneintrag ohne Agentendatei darf einen späteren,
    verfügbaren Eintrag nicht blockieren. Bleibt kein Kandidat verfügbar,
    wird der erste zurückgegeben, damit der Preflight ihn als nicht verfügbar
    melden kann.
    """
    candidates = role_agents(state_dir, role)
    for name in candidates:
        if agent_available(name, project, agents_dir):
            return name
    return candidates[0] if candidates else ""


def preflight_errors(project, agents_dir, tester, reviewer, state_dir=None,
                     allow_dirty=False):
    """Prüft die Startbedingungen und liefert alle Befunde als Liste.

    Eine fehlende TESTER-Zuordnung wird aus der Rolle ``tester`` in
    ``<state_dir>/profiles.json`` ergänzt. Ebenso wird eine fehlende
    REVIEWER-Zuordnung aus der Rolle ``reviewer`` ergänzt. Ein ausdrücklich
    gesetzter TESTER oder REVIEWER (Argument oder project.env) bleibt
    vorrangig.

    ``allow_dirty`` überspringt ausschließlich den Befund eines unsauberen
    Arbeitsbaums. Alle anderen Startbedingungen bleiben unverändert streng;
    die Änderungen selbst werden weder gelesen noch verändert.
    """
    project = Path(project)
    errors = []
    top = run_git(project, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return ["Kein Git-Repository: " + str(project)]
    if os.path.realpath(top.stdout.strip()) != os.path.realpath(project):
        errors.append("Projektordner ist nicht die Wurzel des Git-Repositorys.")
    branch = run_git(project, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch.returncode != 0:
        errors.append("Detached HEAD: Der Lauf braucht einen Integrationsbranch.")
    ensure_project_exclude(project)
    dirty = dirty_report(project)
    if dirty and not allow_dirty:
        errors.append("Arbeitsbaum ist nicht leer:\n" + dirty)

    env = read_env(project / ".vibe" / "project.env")
    tester = tester or env.get("TESTER", "")
    reviewer = reviewer or env.get("REVIEWER", "")
    agents_dir = agents_dir or os.path.join(
        os.path.expanduser("~"), ".config", "opencode", "agents"
    )
    if not tester:
        tester = agent_for_role("tester", state_dir, project, agents_dir)
    if not reviewer:
        reviewer = agent_for_role("reviewer", state_dir, project, agents_dir)
    if not tester:
        errors.append("TESTER fehlt: Der unabhängige Test-Agent ist nicht konfiguriert.")
    elif not agent_available(tester, project, agents_dir):
        errors.append("TESTER '" + tester + "' ist nicht verfügbar (Agentendatei fehlt).")
    if not reviewer:
        errors.append("REVIEWER fehlt: Der unabhängige Review-Agent ist nicht konfiguriert.")
    elif not agent_available(reviewer, project, agents_dir):
        errors.append("REVIEWER '" + reviewer + "' ist nicht verfügbar (Agentendatei fehlt).")

    check_command = env.get("VERIFY_PACKAGE") or env.get("VERIFY_FULL") or ""
    if not check_command.strip() or "TODO" in check_command:
        errors.append(
            "Paketprüfung fehlt: VERIFY_PACKAGE oder VERIFY_FULL muss in "
            ".vibe/project.env einen echten Prüfbefehl enthalten (TODO ersetzen)."
        )
    return errors


def _question_modules():
    """Lädt die F16-Module; eine unvollständige Installation ist kein Absturz."""
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    try:
        # Späte Einbindung ist Absicht: Ein unvollständiger Auslieferungsstand
        # ohne F16 darf bereits das Laden dieses Moduls nicht abbrechen.
        import vibe_questions  # pylint: disable=import-outside-toplevel
        import vibe_autonomous  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None, None
    return vibe_questions, vibe_autonomous


def _assist_text(project_name, errors, intro=""):
    """Formuliert die Rückfrage aus den aktuellen Preflight-Befunden."""
    if not intro:
        intro = "Der Preflight für '" + project_name + "' ist nicht bestanden."
    lines = [intro, ""]
    for error in errors:
        lines.append("- " + str(error).replace("\n", "\n  "))
    lines.append("")
    lines.append(
        "Bitte die genannten Voraussetzungen herstellen und danach "
        "'Erneut prüfen' wählen."
    )
    lines.append(
        "'Agent behebt die Befunde' beauftragt den Agenten, die Befunde im "
        "Projektordner zu beheben; danach wird erneut geprüft. Alternativ "
        "eine Anweisung als freie Antwort senden: Sie hat Vorrang und wird "
        "dem Agenten als Anweisung übergeben."
    )
    text = "\n".join(lines).strip()
    if len(text) > 3900:
        text = text[:3899] + "…"
    return text


def _agent_instruction(errors):
    """Auftrag an den Agenten, der ohne Freitext aus den Befunden entsteht."""
    lines = [
        "Behebe die folgenden Befunde im Projektordner, ohne fremde "
        "Änderungen zu verwerfen:"
    ]
    for error in errors:
        lines.append("- " + str(error).replace("\n", "\n  "))
    return "\n".join(lines)


def _assist_result(errors, action, instruction="", source=""):
    """Ergebnis der Assistenz für den Aufrufer und die Aktionsdatei.

    ``source`` unterscheidet die Nutzeranweisung (``user``) von der aus den
    Befunden abgeleiteten Anweisung (``findings``) und der autonomen
    Entscheidung (``autonomous``), damit das Protokoll die Herkunft korrekt
    benennt.
    """
    return {
        "errors": errors,
        "action": action,
        "instruction": instruction,
        "source": source,
    }


def _autonomous_result(errors, rounds):
    """Entscheidet im autonomen Modus ohne Rückfrage über die Reparatur.

    Vor der ersten Runde entsteht ein Auftrag aus den Befunden. Danach ist
    genau eine autonome Reparatur versucht; ein weiterer identischer Auftrag
    würde nur Kosten verursachen. Der Lauf blockiert dann mit dem letzten
    Befund.
    """
    if rounds >= ASSIST_AUTONOMOUS_REPAIR_ROUNDS:
        print(
            "PREFLIGHT: Autonome Reparatur nach "
            + str(ASSIST_AUTONOMOUS_REPAIR_ROUNDS)
            + " Runde beendet; der Befund besteht weiter."
        )
        return _assist_result(errors + [
            "Autonome Reparatur nach "
            + str(ASSIST_AUTONOMOUS_REPAIR_ROUNDS)
            + " Runde beendet; der Befund besteht weiter."
        ], "max")
    print(
        "PREFLIGHT: Autonomer Modus aktiv; Agent wird ohne Rückfrage mit der "
        "Behebung der Befunde beauftragt."
    )
    return _assist_result(
        errors, "agent", _agent_instruction(errors), "autonomous"
    )


def assist_preflight(project, agents_dir, tester, reviewer, state_dir=None,
                     runtime=None, project_name="", timeout=ASSIST_DEFAULT_TIMEOUT,
                     rounds=0, allow_dirty=False, intro="", max_rounds=None):
    """Führt den Preflight mit F16-Rückfragen zu einem startbaren Stand.

    Liefert ein Ergebnis mit den zuletzt bestehenden Befunden und der nächsten
    Aktion. Eine leere Fehlerliste bedeutet, dass der Preflight bestanden ist.
    Eine freie Antwort ist eine Anweisung an den Agenten; der Aufrufer führt
    sie im Projektordner aus und ruft diese Funktion danach erneut auf. Die
    Option ``Agent behebt die Befunde`` erzeugt denselben Agentenauftrag aus
    den aktuellen Befunden. Ist der autonome Modus aktiv, entsteht keine
    Rückfrage: Die Assistenz liefert einen Auftrag aus den Befunden
    (``source="autonomous"``) und lässt ihn genau eine Runde ausführen. Ohne
    nutzbare F16-Module oder nach einem Abbruch/Zeitlimit bleiben die Befunde
    bestehen.
    ``intro`` ersetzt den Einleitungssatz, wenn die Assistenz nicht am
    Laufstart, sondern an der Abschlussprüfung eingesetzt wird. ``max_rounds``
    begrenzt die Agentenrunden ausdrücklich (AP10: ``assist_rounds``); ohne
    Angabe gilt der Modulstandard.
    """
    questions, autonomous = _question_modules()
    errors = preflight_errors(
        project, agents_dir, tester, reviewer, state_dir,
        allow_dirty=allow_dirty,
    )
    if not errors:
        return _assist_result([], "pass")
    if questions is None or autonomous is None or not runtime:
        return _assist_result(errors, "unavailable")
    limit = ASSIST_MAX_ROUNDS if max_rounds is None else max_rounds
    name = project_name or os.path.basename(os.path.normpath(str(project)))
    if autonomous.is_enabled(runtime, name):
        return _autonomous_result(errors, rounds)
    if rounds >= limit:
        return _assist_result(errors + [
            "Rückfrage-Assistenz nach " + str(limit)
            + " Runden beendet."
        ], "max")

    for _round in range(limit):
        try:
            qid = questions.create(
                runtime,
                project=name,
                agent="vibe",
                text=_assist_text(name, errors, intro),
                options=ASSIST_OPTIONS,
                free_text=True,
            )
        except (OSError, ValueError) as error:
            print("PREFLIGHT: Rückfrage konnte nicht gestellt werden: " + str(error))
            return _assist_result(errors, "unavailable")
        print(
            "PREFLIGHT: Rückfrage " + qid + " gestellt; Antwort im Dashboard "
            "oder mit: vibe answer --runtime " + runtime + " " + qid
            + " --option <1|2|3> oder --text \"Anweisung\""
        )
        try:
            mode, answer = questions.wait_for(
                runtime,
                qid,
                timeout=timeout,
                stop=lambda: autonomous.is_enabled(runtime, name),
            )
        except ValueError as error:
            print("PREFLIGHT: Rückfrage " + qid + " nicht lesbar: " + str(error))
            return _assist_result(errors + [
                "Rückfrage " + qid + " nicht lesbar; Lauf abgebrochen."
            ], "invalid")
        if mode == "stop":
            return _autonomous_result(errors, rounds)
        if mode != "answer":
            print(
                "PREFLIGHT: Keine Antwort auf Rückfrage " + qid
                + " innerhalb von " + f"{timeout:g}" + " s."
            )
            return _assist_result(errors + [
                "Rückfrage " + qid + " blieb ohne Antwort; Lauf abgebrochen."
            ], "timeout")
        option = answer.get("option")
        text = answer.get("text")
        instruction = text.strip() if isinstance(text, str) else ""
        if instruction:
            # Freitext hat Vorrang: Der Nutzer gibt dem Agenten eine Anweisung,
            # wie die Befunde zu beheben sind. Die Ausführung übernimmt der
            # Aufrufer im Projektordner; danach wird erneut geprüft.
            print(
                "PREFLIGHT: Anweisung des Nutzers erhalten; Agent wird "
                "beauftragt."
            )
            return _assist_result(errors, "agent", instruction, "user")
        if option == 1:
            print("PREFLIGHT: Lauf auf Wunsch abgebrochen.")
            return _assist_result(errors, "abort")
        if option == ASSIST_AGENT_OPTION:
            print(
                "PREFLIGHT: Agent wird beauftragt, die Befunde zu beheben."
            )
            return _assist_result(
                errors, "agent", _agent_instruction(errors), "findings"
            )
        if option != 0:
            print(
                "PREFLIGHT: Ungültige Antwort auf Rückfrage " + qid
                + " (Option " + repr(option) + "); Lauf abgebrochen."
            )
            return _assist_result(errors + [
                "Ungültige Antwort auf Rückfrage " + qid + "; Lauf abgebrochen."
            ], "invalid")
        errors = preflight_errors(
            project, agents_dir, tester, reviewer, state_dir,
            allow_dirty=allow_dirty,
        )
        if not errors:
            return _assist_result([], "pass")
        if autonomous.is_enabled(runtime, name):
            return _autonomous_result(errors, rounds)
    return _assist_result(errors + [
        "Rückfrage-Assistenz nach " + str(limit) + " Runden beendet."
    ], "max")


def _barrier_text(project_name, package_id, reason):
    """Formuliert die Rückfrage an der blockierten Schranke."""
    lines = [
        "Projekt '" + project_name + "', Arbeitspaket " + package_id
        + ": Die Abschlussschranke ist nicht erfüllt; das Paket ist "
        "blockiert.",
        "",
        "Grund: " + (reason.strip() if isinstance(reason, str) and reason.strip()
                     else "nicht angegeben"),
        "",
        "'Paket überspringen und Lauf fortsetzen' lässt das Paket ungemergt "
        "blockiert zurück und arbeitet mit den weiteren Paketen weiter. "
        "'Lauf abbrechen' hält den Lauf an (bisheriges Verhalten).",
        "'Agent behebt die Befunde' startet eine weitere Reparaturrunde im "
        "Arbeitsbaum; danach wird erneut geprüft. Alternativ eine Anweisung "
        "als freie Antwort senden: Sie hat Vorrang und wird dem Agenten als "
        "Anweisung übergeben.",
    ]
    text = "\n".join(lines).strip()
    if len(text) > 3900:
        text = text[:3899] + "…"
    return text


def assist_barrier(project, package_id, reason="", runtime=None,
                   project_name="", timeout=ASSIST_DEFAULT_TIMEOUT):
    """Stellt die Schranken-Rückfrage für ein blockiertes Paket (AP10).

    Analog ``assist_preflight`` über F16, aber unabhängig von
    ``VIBE_PREFLIGHT_ASSIST``: Bei einem blockierten Paket (Reparaturlimit
    erreicht oder Reparatur-/Schrankenbefund endgültig) fragt die Funktion,
    wie weiter zu verfahren ist. Die Optionen sind in ``BARRIER_OPTIONS``
    festgelegt; eine freie Antwort ist eine Anweisung an den Agenten und hat
    Vorrang. Liefert ein Ergebnis mit ``action``:

    * ``skip`` — Paket überspringen; der Aufrufer setzt mit dem nächsten
      Paket fort (die Abschlussschranke bleibt unangetastet, das Paket wird
      nicht gemergt).
    * ``abort`` — Lauf abbrechen (bisheriges Verhalten).
    * ``agent`` — weitere Reparaturrunde; ``instruction`` trägt die
      Nutzeranweisung (``source`` = ``user``) oder ist leer für die aus dem
      Befund abgeleitete Anweisung (``source`` = ``findings``).
    * ``autonomous`` — der Agent entscheidet selbst und überspringt.
    * ``timeout`` — die Rückfrage blieb ohne Antwort.
    * ``unavailable`` — ohne nutzbare F16-Module oder Laufzeit; der Aufrufer
      blockiert wie bisher.
    * ``invalid`` — die Antwort war nicht lesbar oder ungültig.
    """
    questions, autonomous = _question_modules()
    errors = [reason] if isinstance(reason, str) and reason.strip() else []
    if questions is None or autonomous is None or not runtime:
        return _assist_result(errors, "unavailable")
    name = project_name or os.path.basename(os.path.normpath(str(project)))
    if autonomous.is_enabled(runtime, name):
        print(
            "BARRIER: Autonomer Modus aktiv für " + name
            + "; der Agent überspringt das blockierte Paket."
        )
        return _assist_result(errors, "autonomous")
    try:
        qid = questions.create(
            runtime,
            project=name,
            agent="vibe",
            text=_barrier_text(name, package_id, reason),
            options=BARRIER_OPTIONS,
            free_text=True,
        )
    except (OSError, ValueError) as error:
        print("BARRIER: Rückfrage konnte nicht gestellt werden: " + str(error))
        return _assist_result(errors, "unavailable")
    print(
        "BARRIER: Rückfrage " + qid + " gestellt; Antwort im Dashboard "
        "oder mit: vibe answer --runtime " + runtime + " " + qid
        + " --option <1|2|3> oder --text \"Anweisung\""
    )
    try:
        mode, answer = questions.wait_for(
            runtime,
            qid,
            timeout=timeout,
            stop=lambda: autonomous.is_enabled(runtime, name),
        )
    except ValueError as error:
        print("BARRIER: Rückfrage " + qid + " nicht lesbar: " + str(error))
        return _assist_result(errors + [
            "Rückfrage " + qid + " nicht lesbar; Lauf abgebrochen."
        ], "invalid")
    if mode == "stop":
        print("BARRIER: Autonomer Modus aktiv; keine Rückfrage mehr.")
        return _assist_result(errors, "autonomous")
    if mode != "answer":
        print(
            "BARRIER: Keine Antwort auf Rückfrage " + qid
            + " innerhalb von " + f"{timeout:g}" + " s."
        )
        return _assist_result(errors + [
            "Rückfrage " + qid + " blieb ohne Antwort; Lauf abgebrochen."
        ], "timeout")
    option = answer.get("option")
    text = answer.get("text")
    instruction = text.strip() if isinstance(text, str) else ""
    if instruction:
        print(
            "BARRIER: Anweisung des Nutzers erhalten; Agent wird beauftragt."
        )
        return _assist_result(errors, "agent", instruction, "user")
    if option == BARRIER_SKIP_OPTION:
        print(
            "BARRIER: Paket " + package_id
            + " wird auf Nutzerentscheidung übersprungen; der Lauf setzt fort."
        )
        return _assist_result(errors, "skip")
    if option == BARRIER_ABORT_OPTION:
        print("BARRIER: Lauf auf Nutzerentscheidung abgebrochen.")
        return _assist_result(errors, "abort")
    if option == BARRIER_AGENT_OPTION:
        print(
            "BARRIER: Agent wird beauftragt, die Befunde zu beheben."
        )
        return _assist_result(errors, "agent", "", "findings")
    print(
        "BARRIER: Ungültige Antwort auf Rückfrage " + qid
        + " (Option " + repr(option) + "); Lauf abgebrochen."
    )
    return _assist_result(errors + [
        "Ungültige Antwort auf Rückfrage " + qid + "; Lauf abgebrochen."
    ], "invalid")


def mark_blocked(project, pid, note):
    """Setzt ``state=blocked`` und ``blocked_reason=note`` am Ticket (idempotent).

    Liefert ``(changed, message)``; ein bereits blockiertes Ticket wird nicht
    erneut geändert.
    """
    project = Path(project)
    record = vibe_tickets.find(vibe_tickets.load(project), pid)
    if record is None:
        return False, "Ticket " + pid + " fehlt im Ticketspeicher."
    if record.get("state") == "blocked":
        return False, "Ticket " + pid + " ist bereits als blockiert vermerkt."
    vibe_tickets.update(project, pid, state="blocked", blocked_reason=note)
    return True, "Ticket " + pid + " als blockiert vermerkt."


def mark_waiting_merge(project, pid, note, pr_url=""):
    """Setzt ``state=waiting-merge``, ``waiting_note`` und ggf. ``pr_url``
    (idempotent). Liefert ``(changed, message)``.
    """
    project = Path(project)
    record = vibe_tickets.find(vibe_tickets.load(project), pid)
    if record is None:
        return False, "Ticket " + pid + " fehlt im Ticketspeicher."
    if record.get("state") == "waiting-merge":
        return False, "Ticket " + pid + " wartet bereits auf den Merge."
    fields = {"state": "waiting-merge", "waiting_note": note}
    if pr_url:
        fields["pr_url"] = pr_url
    vibe_tickets.update(project, pid, **fields)
    return True, "Ticket " + pid + " wartet auf den Merge."


def review_order(path):
    """Sortierschlüssel für ``<ID>-review-N.md``; höhere Nummer ist neuer."""
    match = re.search(r"-review-?(\d+)", path.name)
    return (int(match.group(1)) if match else -1, path.name)


def gate_errors(project, pid, base):
    """Prüft die Abschlussschranke eines Pakets und liefert alle Befunde.

    Statt der alten Markdown-Blöcke liest die Schranke die sichtbare Datei
    ``TICKET-<ID>.json`` in der Arbeitskopie: vorhanden, lesbar, ``state``
    ``done``, ``commit`` im Repository (oder Already-Integrated) und ``test``
    nicht leer. Die übrigen Prüfungen (Commit-Präfix, Feature-Doku, jüngstes
    Review PASS, saubere Arbeitskopie) bleiben unverändert.
    """
    project = Path(project)
    errors = []
    head = run_git(project, "rev-parse", "HEAD")
    if head.returncode != 0:
        return ["HEAD ist nicht lesbar."]
    log = run_git(project, "log", "--format=%H%x09%s", base + "..HEAD")
    commits = []
    if log.returncode == 0:
        for line in log.stdout.splitlines():
            if "\t" in line:
                commits.append(tuple(line.split("\t", 1)))

    ticket_name = vibe_tickets.ticket_file_name(pid)
    record = None
    if not (project / ticket_name).is_file():
        errors.append("Ticket-Datei " + ticket_name + " fehlt in der Arbeitskopie.")
    else:
        try:
            record = vibe_tickets.read_ticket_file(project / ticket_name)
        except ValueError as error:
            errors.append("Ticket-Datei " + ticket_name + " ist nicht lesbar: "
                          + str(error))

    commit = ""
    if record is not None:
        if record.get("state") != "done":
            errors.append("Ticket " + pid + " ist nicht erledigt "
                          "(state muss 'done' sein).")
        commit = record.get("commit") or ""
        if not record.get("test"):
            errors.append("Nachweis für " + pid + " fehlt: das test-Feld ist leer.")

    # Ein Paket kann bereits in den Integrationsstand gemergt sein; dann gibt
    # es keine neuen Commits, aber der Nachweis-Commit liegt als Vorfahre der
    # Basis vor. Dieser Fall ist kein fehlender Paketabschluss.
    already_integrated = (
        not commits
        and bool(commit)
        and commit_subject(project, commit).startswith(pid + ":")
        and commit_is_ancestor(project, commit, base)
    )
    if not already_integrated:
        if not commits:
            errors.append("Kein Commit seit dem Integrationsstand.")
        if not any(subject.startswith(pid + ":") for _, subject in commits):
            errors.append("Commit mit Präfix '" + pid + ":' fehlt.")
    if record is not None and commit and not commit_exists(project, commit) \
            and not already_integrated:
        errors.append("Nachweis-Commit " + commit + " ist im Repository nicht vorhanden.")

    feature = project / "docs" / "features" / (pid + ".md")
    if not feature.is_file() or not read_text(feature).strip():
        errors.append("docs/features/" + pid + ".md fehlt oder ist leer.")

    reviews = project / "docs" / "reviews"
    review_ok = False
    if reviews.is_dir():
        paths = sorted(reviews.glob(pid + "-review*.md"), key=review_order)
        # Das jüngste Review entscheidet: ein früheres PASS darf einen neueren
        # Einwand nicht überdecken.
        if paths and VERDICT_PATTERN.search(read_text(paths[-1])):
            review_ok = True
    if not review_ok:
        errors.append(
            "Jüngstes Review mit 'Verdict: PASS' fehlt (docs/reviews/"
            + pid + "-review*.md)."
        )

    dirty = dirty_report(project)
    if dirty:
        errors.append("Arbeitskopie ist nicht sauber:\n" + dirty)
    return errors


def classify_output(exit_code, text):
    """Ordnet einen Agentenfehler einer Behandlungsart zu."""
    if exit_code == 0:
        return "ok"
    lowered = text.lower()
    for pattern in QUOTA_PATTERNS:
        if re.search(pattern, lowered):
            return "quota"
    for pattern in AUTH_PATTERNS:
        if re.search(pattern, lowered):
            return "auth"
    for pattern in NETWORK_PATTERNS:
        if re.search(pattern, lowered):
            return "network"
    return "other"


def status_report(project):
    """Liefert offene, wartende, blockierte, erledigte und Entwurf-Pakete."""
    report = {"open": [], "waiting": [], "blocked": [], "done": [],
              "draft": []}
    for record in vibe_tickets.load(project):
        pid = record.get("id")
        if not pid:
            continue
        state = record.get("state")
        if state == "done":
            report["done"].append(pid)
        elif state == "blocked":
            report["blocked"].append(pid)
        elif state == "waiting-merge":
            report["waiting"].append(pid)
        elif state == "draft":
            report["draft"].append(pid)
        else:
            report["open"].append(pid)
    return report


def priority_view(project):
    """Priorisierung je Projekt: konfigurierte Einträge und wirksame Ordnung.

    Liefert ``order`` mit Status je konfiguriertem Eintrag (erledigt, gesperrt,
    wartet auf Merge, offen oder fehlt), ``queue`` mit der effektiven
    Abarbeitungsreihenfolge aller bereiten offenen Pakete und ``standard`` mit
    der Standardordnung über alle nicht erledigten Pakete. Die Ansicht ändert
    nichts; sie nutzt dieselbe Auswahllogik wie der Läufer.
    """
    project = Path(project)
    tickets = vibe_tickets.load(project)
    located = {}
    for record in tickets:
        pid = record.get("id")
        if pid and pid not in located:
            located[pid] = record

    def _status(record):
        state = record.get("state")
        if state == "done":
            return "erledigt"
        if state == "blocked":
            return "gesperrt"
        if state == "waiting-merge":
            return "wartet auf Merge"
        if state == "draft":
            return "Entwurf"
        return "offen"

    entries = []
    for pid in package_order(project):
        entry = {"id": pid}
        record = located.get(pid)
        if record is None:
            entry["status"] = "fehlt"
        else:
            entry["title"] = record.get("title")
            entry["status"] = _status(record)
        entries.append(entry)
    skip = set()
    queue = []
    with tempfile.TemporaryDirectory() as folder:
        state = Path(folder) / "next-package.json"
        while True:
            selected = select_package(project, skip=skip, state_path=state)
            if selected is None:
                break
            queue.append({
                "id": selected["id"],
                "ordered": selected["ordered"],
                "title": selected["title"],
            })
            skip.add(selected["id"])
    # Standardordnung wie im Fallback von select_package, ohne Ready-Prüfung,
    # damit gesperrte/geblockte Pakete ihre spätere Position behalten.
    standard = []
    candidates = []
    for index, record in enumerate(tickets):
        if not record.get("id"):
            continue
        candidates.append(((priority(record), index), record))
    candidates.sort(key=lambda item: item[0])
    for _, record in candidates:
        if record.get("state") == "done":
            continue
        standard.append({
            "id": record["id"],
            "title": record.get("title"),
            "status": _status(record),
        })
    return {"key": ORDER_KEY, "order": entries, "queue": queue,
            "standard": standard}


def normalize_order(project, text):
    """Erzwingt eine gültige Priorisierung; Dubletten entfallen.

    ``text`` ist eine Liste von Kennungen mit denselben Trennern wie
    ``PACKAGE_ORDER``. Jede Kennung muss im Ticketspeicher existieren; die
    Reihenfolge bleibt erhalten. Liefert die bereinigte Liste oder wirft
    ``ValueError`` mit den unbekannten Kennungen.
    """
    located = {record.get("id") for record in vibe_tickets.load(project)
               if record.get("id")}
    order, seen, unknown = [], set(), []
    for token in ORDER_SPLIT.split(text or ""):
        if not token:
            continue
        if token not in located and token not in unknown:
            unknown.append(token)
        if token not in seen:
            seen.add(token)
            order.append(token)
    if unknown:
        raise ValueError(
            "Unbekannte Kennungen (nicht im Ticketspeicher): "
            + ", ".join(unknown))
    return order


def command_select(args):
    """Befehl ``select``: wählt ein Paket und gibt seine Kennung aus."""
    selected = select_package(args.project, skip=args.skip, state_path=args.state,
                              prefer=getattr(args, "prefer", "") or "")
    if selected is None:
        return EXIT_NONE
    print(selected["id"])
    return EXIT_OK


def command_preflight(args):
    """Befehl ``preflight``: prüft die Startbedingungen und meldet Befunde."""
    if args.assist:
        result = assist_preflight(
            args.project,
            args.agents_dir,
            args.tester,
            args.reviewer,
            args.state,
            runtime=args.runtime,
            project_name=args.project_name,
            timeout=args.timeout,
            rounds=args.assist_rounds,
            allow_dirty=args.allow_dirty,
            intro=args.assist_reason,
            max_rounds=args.assist_max,
        )
        errors = result["errors"]
        if args.action_file:
            try:
                with open(args.action_file, "w", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False)
            except OSError as error:
                print("PREFLIGHT: Aktionsdatei nicht schreibbar: " + str(error))
                return EXIT_USAGE
    else:
        errors = preflight_errors(
            args.project, args.agents_dir, args.tester, args.reviewer, args.state,
            allow_dirty=args.allow_dirty,
        )
    if args.allow_dirty:
        dirty = dirty_report(args.project)
        if dirty:
            print("HINWEIS: Lauf trotz nicht committeter Änderungen; sie "
                  "bleiben unverändert:\n" + dirty)
    for error in errors:
        print("BLOCKIERT: " + error)
    return EXIT_USAGE if errors else EXIT_OK


def command_copy_notes(args):
    """Befehl ``copy-notes``: übernimmt Arbeitsnotizen und ggf. das Ticket.

    Mit ``--id <pid>`` wird zusätzlich das aktuelle Ticket als sichtbare Datei
    ``TICKET-<ID>.json`` in die Arbeitskopie transportiert; ein fehlendes
    Ticket ist ein Fehler (``FEHLT:``, Exit 1). Ohne ``--id`` bleibt der
    Transport von AGENTS.md/.vibe/project.env wie bisher.
    """
    pid = (getattr(args, "id", None) or "").strip()
    if pid:
        ok, _exclude = transport_ticket(args.project, args.worktree, pid)
        if not ok:
            print("FEHLT: Ticket " + pid + " fehlt im Ticketspeicher.")
            return EXIT_NONE
        print("OK: " + vibe_tickets.ticket_file_name(pid)
              + " in die Arbeitskopie übernommen.")
    copied, skipped = copy_work_notes(args.project, args.worktree)
    for name in copied:
        print("OK: " + name + " in die Arbeitskopie übernommen.")
    for name in skipped:
        print("HINWEIS: " + name + " hat nicht committete Änderungen; "
              "sie wurden nicht in die Arbeitskopie übernommen.")
    # AP5: read-only Einweg-Transport von .vibe/project.env (nie zurück).
    transported, exclude_ok = transport_project_env(args.project, args.worktree)
    if transported:
        names = " und ".join(transported)
        if exclude_ok:
            print("OK: " + names + " read-only in die Arbeitskopie "
                  "übernommen.")
        else:
            print("WARNUNG: " + names + " wurde kopiert, aber der "
                  "Git-Exclude-Eintrag ist fehlgeschlagen.")
    return EXIT_OK


def command_sync_ticket(args):
    """Befehl ``sync-ticket``: übernimmt den Abschluss in den Ticketspeicher."""
    changed, message = sync_ticket(args.project, args.worktree, args.id)
    if not changed:
        print("FEHLT: " + message)
        return EXIT_NONE
    print("OK: " + message)
    return EXIT_OK


def command_branch_name(args):
    """Befehl ``branch-name``: gibt den Paket-Branch nach Repository-Regeln aus.

    Nur der Name geht auf stdout; ein ungültiges Muster oder Ergebnis meldet
    ``FEHLT: <Grund>`` und endet mit Exit 1 (B16).
    """
    try:
        name = package_branch_name(args.project, args.id)
    except ValueError as error:
        print("FEHLT: " + str(error))
        return EXIT_NONE
    print(name)
    return EXIT_OK


def command_gate(args):
    """Befehl ``gate``: prüft die Abschlussschranke eines Pakets."""
    errors = gate_errors(args.project, args.id, args.base)
    for error in errors:
        print("FEHLT: " + error)
    if errors:
        print("BLOCKIERT: Abschlussschranke für " + args.id + " nicht erfüllt.")
        return EXIT_NONE
    print("OK: Abschlussschranke für " + args.id + " erfüllt.")
    return EXIT_OK


def command_barrier(args):
    """Befehl ``barrier``: stellt die Schranken-Rückfrage eines Pakets (AP10).

    Der Läufer ruft dies auf, wenn ein Arbeitspaket an der Reparatur-
    schranke blockiert ist und ``override="ask"`` wirksam ist. Diagnosen der
    Rückfrage gehen auf die Standardfehlerausgabe, damit die Standardausgabe
    ausschließlich das Ergebnis als JSON enthält und der Läufer sie parsen
    kann.
    """
    real_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        result = assist_barrier(
            args.project,
            args.id,
            reason=args.reason,
            runtime=args.runtime,
            project_name=args.project_name,
            timeout=args.timeout,
        )
    finally:
        sys.stdout = real_stdout
    print(json.dumps(result, ensure_ascii=False))
    return EXIT_OK


def command_mark_blocked(args):
    """Befehl ``mark-blocked``: vermerkt ein Paket als blockiert (AP10).

    Wird vom Läufer genutzt, wenn der Nutzer das Überspringen eines
    blockierten Pakets entschieden hat; die Blockierungsmarke verhindert die
    erneute Auswahl im Projektordner.
    """
    changed, message = mark_blocked(args.project, args.id, args.note)
    print(("OK: " if changed else "HINWEIS: ") + message)
    return EXIT_OK if changed else EXIT_NONE


def command_mark_waiting(args):
    """Befehl ``mark-waiting``: vermerkt ein Paket als wartend (AP5 4a).

    Wird vom Läufer im PR-only-Abschluss genutzt; die Marke verhindert die
    erneute Auswahl, lässt den Eigentümer das Paket aber nach dem Merge über
    ``vibe package close`` abschließen.
    """
    changed, message = mark_waiting_merge(args.project, args.id, args.note,
                                          pr_url=args.pr_url)
    print(("OK: " if changed else "HINWEIS: ") + message)
    return EXIT_OK if changed else EXIT_NONE


def command_classify(args):
    """Befehl ``classify``: ordnet einen Agentenfehler einer Kategorie zu."""
    text = ""
    if args.log:
        lines = read_text(args.log).splitlines()
        text = "\n".join(lines[args.since:])
    else:
        text = sys.stdin.read()
    print(classify_output(args.exit_code, text))
    return EXIT_OK


def command_status(args):
    """Befehl ``status``: gibt den Paketstand als JSON aus."""
    print(json.dumps(status_report(args.project), ensure_ascii=False))
    return EXIT_OK


def command_github_pull(args):
    """Befehl ``github-pull``: Haupt-Branch vor einem Arbeitspaket aktualisieren.

    Ohne Konfiguration bewusster Skip (Exit 0); ein Fehlschlag meldet sich
    verständlich und endet mit 1, wirft aber niemals."""
    performed, ok, message = _github_module().pull_integration(args.project)
    print(("GitHub: " if performed else "Skip: ") + message)
    return EXIT_OK if ok else EXIT_NONE


def command_github_complete(args):
    """Befehl ``github-complete``: Branch pushen und Merge-Request stellen.

    Seit B16 ist ein Fehlschlag eine echte Abschlussschranke: Der Läufer
    blockiert das Paket (Exit 1) statt einen bloßen Hinweis zu melden. Die
    letzte Ausgabezeile nennt immer Branch und Merge-Request-URL."""
    performed, ok, message, result = _github_module().complete_package(
        args.project, args.branch, package_id=args.id)
    print(("GitHub: " if performed else "Skip: ") + message)
    branch = result.get("branch") or args.branch
    pr_url = result.get("pr_url") or "keine"
    print("ABGABE: Branch " + str(branch) + ", Merge-Request " + str(pr_url))
    return EXIT_OK if ok else EXIT_NONE


def command_github_push(args):
    """Befehl ``github-push``: Branch nach origin übertragen (Retry-Pfad).

    Wrappt ``vibe_github.push``; Exit 0 bei Erfolg, 1 bei Fehlschlag."""
    ok, message = _github_module().push(args.project, args.branch)
    print(message)
    return EXIT_OK if ok else EXIT_NONE


def command_github_merge(args):
    """Befehl ``github-merge``: offenen Merge-Request per REST squash-mergen.

    Exit 0 = gemergt, Exit 2 = Konflikt (der Läufer erkennt den begrenzten
    Reparaturpfad), Exit 1 = sonstiger Fehler. Die letzte Zeile ist die
    maschinenlesbare ``MERGE:``-Zeile."""
    ok, message, result = _github_module().merge_pull_request(
        args.project, args.branch, package_id=args.id)
    print(message)
    state = "ok" if ok else ("konflikt" if result.get("conflict") else "fehler")
    sha = result.get("sha") or ""
    print("MERGE: " + state + (" " + sha if sha else ""))
    if ok:
        return EXIT_OK
    if result.get("conflict"):
        return 2
    return EXIT_NONE


def command_ensure_mergeable(args):
    """Befehl ``ensure-mergeable``: Basis in den Paketbranch mergen (T-G7).

    Exit 0 = mergebar/Skip, Exit 2 = Konflikt (je Pfad eine ``KONFLIKT:``-
    Zeile), Exit 1 = Fehler. ``--abort`` bricht einen laufenden Merge ab."""
    gh = _github_module()
    worktree = args.worktree or args.project
    if getattr(args, "abort", False):
        rc, out = gh.git(worktree, "merge", "--abort")
        if rc != 0:
            print("FEHLT: merge --abort: " + (out or "unbekannter Fehler"))
            return EXIT_NONE
        print("OK: Merge abgebrochen.")
        return EXIT_OK
    ok, message, result = gh.ensure_mergeable(
        args.project, worktree, base=getattr(args, "base", "") or "")
    if result.get("conflict"):
        for path in result.get("paths") or []:
            print("KONFLIKT: " + path)
        print("KONFLIKT: " + message)
        return 2
    if ok:
        print("OK: " + message)
        return EXIT_OK
    print("FEHLT: " + message)
    return EXIT_NONE


def build_parser():
    """Baut die argparse-Befehlszeile aller Unterbefehle."""
    parser = argparse.ArgumentParser(
        description="Paketauswahl und Abschlussschranke für vibe-run.sh"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="nächstes offenes Paket wählen")
    select.add_argument("--project", required=True)
    select.add_argument("--skip", default="")
    select.add_argument("--state", default=None)
    select.add_argument("--prefer", default="",
                        help="bevorzugtes Paket (Reattach), falls offen")
    select.set_defaults(handler=command_select)

    preflight = subparsers.add_parser("preflight", help="Startbedingungen prüfen")
    preflight.add_argument("--project", required=True)
    preflight.add_argument("--agents-dir", default=None)
    preflight.add_argument("--tester", default="")
    preflight.add_argument("--reviewer", default="")
    preflight.add_argument(
        "--state", default=None,
        help="Zustandsordner mit profiles.json für die Rollenauflösung",
    )
    preflight.add_argument(
        "--assist", action="store_true",
        help="bei Befunden über F16 nachfragen und den Preflight wiederholen",
    )
    preflight.add_argument(
        "--runtime", default=None,
        help="Laufzeitordner für Rückfragen (F22)",
    )
    preflight.add_argument(
        "--project-name", default="",
        help="Projektname für die Rückfrage (F22)",
    )
    preflight.add_argument(
        "--timeout", type=float, default=ASSIST_DEFAULT_TIMEOUT,
        help="Wartezeit je Rückfrage in Sekunden (F22)",
    )
    preflight.add_argument(
        "--action-file", default=None,
        help="schreibt die nächste Aktion der Assistenz als JSON (F22)",
    )
    preflight.add_argument(
        "--assist-rounds", type=int, default=0,
        help="bereits ausgeführte Agentenrunden der Assistenz (F22)",
    )
    preflight.add_argument(
        "--assist-max", type=int, default=None,
        help="Höchstzahl der Agentenrunden der Assistenz (AP10)",
    )
    preflight.add_argument(
        "--assist-reason", default="",
        help="Einleitungssatz der Rückfrage (Standard: Preflight)",
    )
    preflight.add_argument(
        "--allow-dirty", action="store_true",
        help="unsauberen Arbeitsbaum ausdrücklich zulassen (F27)",
    )
    preflight.set_defaults(handler=command_preflight)

    gate = subparsers.add_parser("gate", help="Abschlussschranke prüfen")
    gate.add_argument("--project", required=True)
    gate.add_argument("--id", required=True)
    gate.add_argument("--base", required=True)
    gate.set_defaults(handler=command_gate)

    branch_name_parser = subparsers.add_parser(
        "branch-name", help="Branch-Name eines Pakets nach Repository-Regeln (B16)"
    )
    branch_name_parser.add_argument("--project", required=True)
    branch_name_parser.add_argument("--id", required=True)
    branch_name_parser.set_defaults(handler=command_branch_name)

    copy_notes = subparsers.add_parser(
        "copy-notes", help="Arbeitsnotizen in die Arbeitskopie übernehmen"
    )
    copy_notes.add_argument("--project", required=True)
    copy_notes.add_argument("--worktree", required=True)
    copy_notes.add_argument("--id", default="",
                            help="zusätzlich das Ticket TICKET-<id>.json transportieren")
    copy_notes.set_defaults(handler=command_copy_notes)

    sync_ticket_parser = subparsers.add_parser(
        "sync-ticket", help="Paketabschluss in den Ticketspeicher übernehmen"
    )
    sync_ticket_parser.add_argument("--project", required=True)
    sync_ticket_parser.add_argument("--worktree", required=True)
    sync_ticket_parser.add_argument("--id", required=True)
    sync_ticket_parser.set_defaults(handler=command_sync_ticket)

    classify = subparsers.add_parser("classify", help="Agentenfehler einordnen")
    classify.add_argument("--exit-code", type=int, required=True)
    classify.add_argument("--log", default=None)
    classify.add_argument("--since", type=int, default=0)
    classify.set_defaults(handler=command_classify)

    barrier = subparsers.add_parser(
        "barrier",
        help="Schranken-Rückfrage für ein blockiertes Paket stellen (AP10)",
    )
    barrier.add_argument("--project", required=True)
    barrier.add_argument("--id", required=True)
    barrier.add_argument("--reason", default="")
    barrier.add_argument("--runtime", default=None)
    barrier.add_argument("--project-name", default="")
    barrier.add_argument("--timeout", type=float, default=ASSIST_DEFAULT_TIMEOUT)
    barrier.set_defaults(handler=command_barrier)

    mark_blocked_parser = subparsers.add_parser(
        "mark-blocked",
        help="Arbeitspaket als blockiert vermerken (AP10)",
    )
    mark_blocked_parser.add_argument("--project", required=True)
    mark_blocked_parser.add_argument("--id", required=True)
    mark_blocked_parser.add_argument("--note", required=True)
    mark_blocked_parser.set_defaults(handler=command_mark_blocked)

    mark_waiting_parser = subparsers.add_parser(
        "mark-waiting",
        help="Arbeitspaket als auf Merge wartend vermerken (AP5)",
    )
    mark_waiting_parser.add_argument("--project", required=True)
    mark_waiting_parser.add_argument("--id", required=True)
    mark_waiting_parser.add_argument("--note", required=True)
    mark_waiting_parser.add_argument("--pr-url", default="")
    mark_waiting_parser.set_defaults(handler=command_mark_waiting)

    status = subparsers.add_parser("status", help="Paketstand ausgeben")
    status.add_argument("--project", required=True)
    status.set_defaults(handler=command_status)

    github_pull = subparsers.add_parser(
        "github-pull",
        help="Haupt-Branch vor einem Arbeitspaket aktualisieren (AP9)",
    )
    github_pull.add_argument("--project", required=True)
    github_pull.set_defaults(handler=command_github_pull)

    github_complete = subparsers.add_parser(
        "github-complete",
        help="Paket-Branch pushen und Merge-Request stellen (AP9)",
    )
    github_complete.add_argument("--project", required=True)
    github_complete.add_argument("--branch", required=True)
    github_complete.add_argument("--id", default=None)
    github_complete.set_defaults(handler=command_github_complete)

    github_push = subparsers.add_parser(
        "github-push",
        help="Paket-Branch nach origin übertragen (Retry-Pfad)",
    )
    github_push.add_argument("--project", required=True)
    github_push.add_argument("--branch", required=True)
    github_push.set_defaults(handler=command_github_push)

    github_merge = subparsers.add_parser(
        "github-merge",
        help="offenen Merge-Request per REST squash-mergen (AP4)",
    )
    github_merge.add_argument("--project", required=True)
    github_merge.add_argument("--branch", required=True)
    github_merge.add_argument("--id", default=None)
    github_merge.set_defaults(handler=command_github_merge)

    ensure_mergeable = subparsers.add_parser(
        "ensure-mergeable",
        help="Basis in den Paketbranch mergen, Konflikte stehen lassen (AP4)",
    )
    ensure_mergeable.add_argument("--project", required=True)
    ensure_mergeable.add_argument("--worktree", default="")
    ensure_mergeable.add_argument("--base", default="")
    ensure_mergeable.add_argument("--abort", action="store_true")
    ensure_mergeable.set_defaults(handler=command_ensure_mergeable)

    return parser


def main(argv=None):
    """Führt den gewählten Unterbefehl aus und liefert seinen Exitcode."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
