#!/usr/bin/env python3
"""Paketauswahl und Abschlussschranke für den vibe-Paketläufer.

Der Läufer benutzt dieses Modul, damit Auswahl, Vorabprüfung, Bewertung des
Agentenergebnisses und Abschlussbericht versioniert und testbar sind. Die
Datei arbeitet ausschließlich lokal: keine Modellaufrufe, keine Netzverbindung.
Sie schreibt nur den projektlokalen Auswahlstand unter ``.vibe/tmp/`` und den
Paketnachweis in die Laufzeitnotiz ``FEEDBACK.md`` bzw. ``TICKETS.md``; die
Arbeitskopie erhält eine Kopie dieser Notizen.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NONE = 1
EXIT_USAGE = 2

# F22: Ein blockierter Preflight darf den Nutzer über F16 nach einer
# Entscheidung fragen. Die Assistenz ist nur im Produktpfad ``vibe run``
# aktiv; ein direkter Läuferaufruf und Tests ohne die Variable bleiben beim
# bisherigen sofortigen Abbruch.
ASSIST_OPTIONS = ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"]
ASSIST_AGENT_OPTION = 2
ASSIST_DEFAULT_TIMEOUT = 600.0
ASSIST_MAX_ROUNDS = 10

CHECKBOX_DONE = re.compile(r"^- \[[xX]\]")
CHECKBOX_ANY = re.compile(r"^- \[[ xX]\]")
BLOCK_MARKER = "BLOCKIERT:"
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\d+")
PROOF_PATTERN = re.compile(r"(?:Test|Datei)\s*:\s*\S+")
DEPENDENCY_PATTERN = re.compile(r"Abhängigkeiten\s*:\s*(.+)")
PRIORITY_PATTERN = re.compile(r"Priorität\s*:\s*(P\d)")
# Agentennamen werden wie im Läufer und in der Agentenverwaltung geprüft.
# profiles.json ist Nutzerzustand; ein Name mit Pfadanteilen darf nie in eine
# Dateiprüfung außerhalb der Agentenordner führen.
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VERDICT_PATTERN = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?verdict\s*:\s*\**\s*PASS\b"
)

# Arbeitsnotizen sind Laufzeitstand (Datei oder UI), kein versionierter
# Produktinhalt. Ihre Änderungen dürfen weder den Start noch die
# Abschlussschranke blockieren. Die Arbeitskopie erhält eine Kopie; nach dem
# Merge wird der Paketnachweis gezielt in den Projektordner zurückgeschrieben.
WORK_NOTE_FILES = ("TICKETS.md", "FEEDBACK.md")
PROOF_KEYS = ("Commit", "Test", "Datei", "Review", "Doku")
PROOF_LINE = re.compile(r"^\s*(?:" + "|".join(PROOF_KEYS) + r")\s*:")

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
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def write_text_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def run_git(project, *args):
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
    )


def is_work_note_path(path):
    """True, wenn ein Git-Statuspfad eine Arbeitsnotiz im Projektstamm ist."""
    value = path.strip().strip('"').replace("\\", "/")
    if " -> " in value:
        value = value.split(" -> ", 1)[1].strip().strip('"')
    # Nur die Dateien am Projektstamm; gleichnamige Dateien in Unterordnern
    # sind normale Projektdateien und zählen weiterhin als Änderung.
    return value in WORK_NOTE_FILES


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


def copy_work_notes(project, worktree):
    """Kopiert vorhandene Arbeitsnotizen in die Paket-Arbeitskopie."""
    project, worktree = Path(project), Path(worktree)
    copied = []
    for name in WORK_NOTE_FILES:
        source = project / name
        if not source.is_file():
            continue
        write_text_atomic(worktree / name, read_text(source))
        copied.append(name)
    return copied


def block_span(lines, pid):
    """Zeilenbereich ``[start, end)`` des Ticketblocks mit dieser ID."""
    for index, line in enumerate(lines):
        if line.startswith("- ") and block_id(line) == pid:
            end = index + 1
            while end < len(lines) and (
                lines[end].startswith((" ", "\t")) or not lines[end].strip()
            ):
                end += 1
            return index, end
    return None


def _apply_proof(text, span, worktree_block):
    """Hakt den Block ab und ersetzt seine Nachweiszeilen.

    Nur die Checkbox und die Nachweiszeilen ändern sich; Beschreibungen,
    Nachbemerkungen und andere Blöcke bleiben unverändert.
    """
    lines = text.splitlines()
    start, end = span
    block = lines[start:end]
    block[0] = re.sub(r"^(- )\[ \]", r"\1[x]", block[0], count=1)
    reduced, insert_at = [block[0]], None
    for line in block[1:]:
        if PROOF_LINE.match(line):
            if insert_at is None:
                insert_at = len(reduced)
            continue
        reduced.append(line)
    if insert_at is None:
        insert_at = len(reduced)
        while insert_at > 1 and not reduced[insert_at - 1].strip():
            insert_at -= 1
    proof = [
        line.rstrip()
        for line in worktree_block.splitlines()
        if PROOF_LINE.match(line)
    ]
    reduced[insert_at:insert_at] = proof
    lines[start:end] = reduced
    result = "\n".join(lines)
    return result + "\n" if text.endswith("\n") else result


def sync_proof(project, worktree, pid):
    """Übernimmt ``[x]`` und Nachweiszeilen eines Pakets in den Projektordner.

    Quelle ist die Arbeitskopie; Ziel ist derselbe Dateiname im Projekt. Der
    Nachweis wird nur übernommen, wenn er vollständig ist. Liefert
    ``(changed, message)``; bei ``changed=False`` bleibt die Zieldatei
    unverändert.
    """
    project, worktree = Path(project), Path(worktree)
    source_name, worktree_block = "", ""
    for name in WORK_NOTE_FILES:
        note = worktree / name
        if not note.is_file():
            continue
        for block in read_blocks(note):
            if block_id(block) == pid:
                source_name, worktree_block = name, block
                break
        if worktree_block:
            break
    if not worktree_block:
        return False, "Block " + pid + " fehlt in der Arbeitskopie."
    if not is_done(worktree_block):
        return False, "Block " + pid + " ist in der Arbeitskopie nicht abgehakt."
    revisions = proof_commits(worktree_block)
    if not revisions or not any(
        commit_exists(project, revision) for revision in revisions
    ):
        return False, "Nachweis-Commit für " + pid + " fehlt oder ist nicht vorhanden."
    if not PROOF_PATTERN.search(worktree_block):
        return False, "Nachweis 'Test:' oder 'Datei:' für " + pid + " fehlt."
    target = project / source_name
    if not target.is_file():
        return False, source_name + " fehlt im Projektordner."
    text = read_text(target)
    span = block_span(text.splitlines(), pid)
    if span is None:
        return False, "Block " + pid + " fehlt in " + source_name + "."
    updated = _apply_proof(text, span, worktree_block)
    if updated != text:
        write_text_atomic(target, updated)
    return True, pid + " in " + source_name + " abgehakt."


def read_env(path):
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


def read_blocks(path):
    """Zerlegt eine Markdown-Arbeitsdatei in Blöcke ab ``- ``."""
    text = re.sub(r"<!--.*?-->", "", read_text(path), flags=re.S)
    blocks, current = [], None
    for line in text.splitlines():
        if line.startswith("- "):
            if current is not None:
                blocks.append(current)
            current = line
        elif current is not None and line.startswith((" ", "\t")):
            current += "\n" + line
        elif current is not None and not line.strip():
            current += "\n"
        else:
            if current is not None:
                blocks.append(current)
                current = None
    if current is not None:
        blocks.append(current)
    return [block.strip("\n") for block in blocks]


def block_id(block):
    match = re.match(r"- (?:\[[ xX]\]\s*)?(\S+)", block)
    return match.group(1) if match else ""


def is_done(block):
    return bool(CHECKBOX_DONE.match(block))


def is_blocked(block):
    return BLOCK_MARKER in block.upper()


def proof_commits(block):
    """Alle Commits einer Nachweiszeile, auch über umbrochene Zeilen.

    Das Nachweisfeld beginnt mit ``Commit:`` und darf auf Folgezeilen
    fortgesetzt werden, solange diese eingerückt sind und kein neues
    Nachweisfeld beginnen. Dadurch zählt ein Paket als belegt, sobald einer
    der genannten Commits zum Paketbranch gehört.
    """
    revisions = []
    collecting = False
    for line in (block or "").splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^Commit\s*:", stripped):
            collecting = True
            payload = stripped.split(":", 1)[1]
        elif collecting and line[:1] in (" ", "\t") and not PROOF_LINE.match(line):
            payload = stripped
        elif collecting:
            break
        else:
            continue
        for revision in re.findall(r"\b[0-9a-fA-F]{7,40}\b", payload):
            if revision not in revisions:
                revisions.append(revision)
    return revisions


def proof_commit(block):
    """Erster genannter Commit; bleibt für Aufrufer mit Einzelnachweis gültig."""
    revisions = proof_commits(block)
    return revisions[0] if revisions else ""


def commit_exists(project, revision):
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


def proof_ok(project, block):
    revisions = proof_commits(block)
    if not revisions or not any(
        commit_exists(project, revision) for revision in revisions
    ):
        return False, "Commit fehlt oder ist nicht vorhanden"
    if not PROOF_PATTERN.search(block):
        return False, "Test: oder Datei: fehlt"
    return True, ""


def dependencies(block):
    match = DEPENDENCY_PATTERN.search(block)
    if not match:
        return []
    return [
        token
        for token in re.split(r"[,;\s]+", match.group(1))
        if ID_PATTERN.fullmatch(token)
    ]


def priority(block):
    match = PRIORITY_PATTERN.search(block)
    return int(match.group(1)[1]) if match else 9


def collect_blocks(project):
    project = Path(project)
    return [
        ("TICKETS.md", read_blocks(project / "TICKETS.md")),
        ("FEEDBACK.md", read_blocks(project / "FEEDBACK.md")),
    ]


def done_ids(project):
    done = set()
    for _, blocks in collect_blocks(project):
        for block in blocks:
            pid = block_id(block)
            if pid and is_done(block) and proof_ok(project, block)[0]:
                done.add(pid)
    return done


def select_package(project, skip=None, state_path=None):
    """Liefert das nächste offene Paket oder ``None``.

    Reihenfolge: TICKETS vor FEEDBACK; innerhalb der TICKETS nach Priorität
    (P0, P1, P2, ohne Angabe) und sonst nach Dateireihenfolge. Ein Paket wird
    nur gewählt, wenn alle bekannten Abhängigkeiten nachweislich erledigt sind.
    """
    project = Path(project)
    if isinstance(skip, str):
        skip = {item for item in skip.split(",") if item}
    else:
        skip = set(skip or [])
    done = done_ids(project)
    known = set()
    for _, blocks in collect_blocks(project):
        known.update(block_id(block) for block in blocks if block_id(block))

    for source, blocks in collect_blocks(project):
        candidates = []
        for index, block in enumerate(blocks):
            pid = block_id(block)
            if not pid or pid in skip:
                continue
            if is_blocked(block) or pid in done:
                continue
            if any(dep in known and dep not in done for dep in dependencies(block)):
                continue
            order = (priority(block), index) if source == "TICKETS.md" else (0, index)
            candidates.append((order, pid, block))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0])
        _, pid, block = candidates[0]
        selected = {
            "id": pid,
            "block": block,
            "source": source,
            "priority": "P%d" % priority(block) if priority(block) < 9 else "",
        }
        target = Path(state_path) if state_path else project / ".vibe" / "tmp" / "next-package.json"
        write_text_atomic(target, json.dumps(selected, ensure_ascii=False, indent=1) + "\n")
        return selected
    return None


def agent_available(name, project, agents_dir):
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
        entry for entry in (".vibe/tmp/",) + WORK_NOTE_FILES
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

    Eine fehlende REVIEWER-Zuordnung wird aus der Rolle ``reviewer`` in
    ``<state_dir>/profiles.json`` ergänzt. Ein ausdrücklich gesetzter Reviewer
    (Argument oder project.env) bleibt vorrangig.

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
        import vibe_questions
        import vibe_autonomous
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
    Befunden abgeleiteten Anweisung (``findings``), damit das Protokoll die
    Herkunft korrekt benennt.
    """
    return {
        "errors": errors,
        "action": action,
        "instruction": instruction,
        "source": source,
    }


def assist_preflight(project, agents_dir, tester, reviewer, state_dir=None,
                     runtime=None, project_name="", timeout=ASSIST_DEFAULT_TIMEOUT,
                     rounds=0, allow_dirty=False, intro=""):
    """Führt den Preflight mit F16-Rückfragen zu einem startbaren Stand.

    Liefert ein Ergebnis mit den zuletzt bestehenden Befunden und der nächsten
    Aktion. Eine leere Fehlerliste bedeutet, dass der Preflight bestanden ist.
    Eine freie Antwort ist eine Anweisung an den Agenten; der Aufrufer führt
    sie im Projektordner aus und ruft diese Funktion danach erneut auf. Die
    Option ``Agent behebt die Befunde`` erzeugt denselben Agentenauftrag aus
    den aktuellen Befunden. Ohne nutzbare F16-Module, bei aktivem autonomem
    Modus oder nach einem Abbruch/Zeitlimit bleiben die Befunde bestehen.
    ``intro`` ersetzt den Einleitungssatz, wenn die Assistenz nicht am
    Laufstart, sondern an der Abschlussprüfung eingesetzt wird.
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

    name = project_name or os.path.basename(os.path.normpath(str(project)))
    if autonomous.is_enabled(runtime, name):
        return _assist_result(errors, "autonomous")
    if rounds >= ASSIST_MAX_ROUNDS:
        return _assist_result(errors + [
            "Rückfrage-Assistenz nach " + str(ASSIST_MAX_ROUNDS)
            + " Runden beendet."
        ], "max")

    for _round in range(ASSIST_MAX_ROUNDS):
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
            "oder mit: vibe answer " + qid
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
            print("PREFLIGHT: Autonomer Modus aktiv; keine Rückfrage mehr.")
            return _assist_result(errors, "autonomous")
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
            return _assist_result(errors, "autonomous")
    return _assist_result(errors + [
        "Rückfrage-Assistenz nach " + str(ASSIST_MAX_ROUNDS) + " Runden beendet."
    ], "max")


def review_order(path):
    """Sortierschlüssel für ``<ID>-review-N.md``; höhere Nummer ist neuer."""
    match = re.search(r"-review-?(\d+)", path.name)
    return (int(match.group(1)) if match else -1, path.name)


def gate_errors(project, pid, base):
    """Prüft die Abschlussschranke eines Pakets und liefert alle Befunde."""
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
    block = None
    for _, blocks in collect_blocks(project):
        for candidate in blocks:
            if block_id(candidate) == pid:
                block = candidate
                break
        if block is not None:
            break

    revisions = proof_commits(block)
    # Ein Paket kann bereits in den Integrationsstand gemergt sein, während
    # sein Nachweis nur in der unversionierten Arbeitsnotiz steht. Dann gibt es
    # keine neuen Commits; der Nachweis liegt vielmehr als Vorfahre der Basis
    # vor. Dieser Fall ist kein fehlender Paketabschluss. Bei mehreren
    # gelisteten Commits genügt einer, der Vorfahre der Basis ist und das
    # Paketpräfix trägt.
    already_integrated = (
        not commits
        and any(
            commit_subject(project, revision).startswith(pid + ":")
            and commit_is_ancestor(project, revision, base)
            for revision in revisions
        )
    )
    if not already_integrated:
        if not commits:
            errors.append("Kein Commit seit dem Integrationsstand.")
        if not any(subject.startswith(pid + ":") for _, subject in commits):
            errors.append("Commit mit Präfix '" + pid + ":' fehlt.")

    if block is None:
        errors.append("Ticket " + pid + " fehlt in TICKETS.md/FEEDBACK.md.")
    else:
        if not is_done(block):
            errors.append("Ticket " + pid + " ist nicht abgehakt ([x] fehlt).")
        proof, reason = proof_ok(project, block)
        if not proof:
            errors.append("Nachweis für " + pid + " fehlt: " + reason + ".")
        elif not already_integrated and not any(
            revision
            for revision in revisions
            if any(
                commit.startswith(revision) and subject.startswith(pid + ":")
                for commit, subject in commits
            )
        ):
            errors.append(
                "Nachweis-Commit(s) " + ", ".join(revisions)
                + " gehören nicht zu diesem Paketbranch."
            )

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
    """Liefert offene, blockierte und nachweislich erledigte Pakete."""
    report = {"open": [], "blocked": [], "done": []}
    seen = set()
    for _, blocks in collect_blocks(project):
        for block in blocks:
            pid = block_id(block)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            if is_blocked(block):
                report["blocked"].append(pid)
            elif is_done(block) and proof_ok(project, block)[0]:
                report["done"].append(pid)
            else:
                report["open"].append(pid)
    return report


def command_select(args):
    selected = select_package(args.project, skip=args.skip, state_path=args.state)
    if selected is None:
        return EXIT_NONE
    print(selected["id"])
    return EXIT_OK


def command_preflight(args):
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
    copied = copy_work_notes(args.project, args.worktree)
    for name in copied:
        print("OK: " + name + " in die Arbeitskopie übernommen.")
    return EXIT_OK


def command_sync_proof(args):
    changed, message = sync_proof(args.project, args.worktree, args.id)
    if not changed:
        print("FEHLT: " + message)
        return EXIT_NONE
    print("OK: " + message)
    return EXIT_OK


def command_gate(args):
    errors = gate_errors(args.project, args.id, args.base)
    for error in errors:
        print("FEHLT: " + error)
    if errors:
        print("BLOCKIERT: Abschlussschranke für " + args.id + " nicht erfüllt.")
        return EXIT_NONE
    print("OK: Abschlussschranke für " + args.id + " erfüllt.")
    return EXIT_OK


def command_classify(args):
    text = ""
    if args.log:
        lines = read_text(args.log).splitlines()
        text = "\n".join(lines[args.since:])
    else:
        text = sys.stdin.read()
    print(classify_output(args.exit_code, text))
    return EXIT_OK


def command_status(args):
    print(json.dumps(status_report(args.project), ensure_ascii=False))
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        description="Paketauswahl und Abschlussschranke für vibe-run.sh"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="nächstes offenes Paket wählen")
    select.add_argument("--project", required=True)
    select.add_argument("--skip", default="")
    select.add_argument("--state", default=None)
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

    copy_notes = subparsers.add_parser(
        "copy-notes", help="Arbeitsnotizen in die Arbeitskopie übernehmen"
    )
    copy_notes.add_argument("--project", required=True)
    copy_notes.add_argument("--worktree", required=True)
    copy_notes.set_defaults(handler=command_copy_notes)

    sync_proof = subparsers.add_parser(
        "sync-proof", help="Paketnachweis in den Projektordner zurückschreiben"
    )
    sync_proof.add_argument("--project", required=True)
    sync_proof.add_argument("--worktree", required=True)
    sync_proof.add_argument("--id", required=True)
    sync_proof.set_defaults(handler=command_sync_proof)

    classify = subparsers.add_parser("classify", help="Agentenfehler einordnen")
    classify.add_argument("--exit-code", type=int, required=True)
    classify.add_argument("--log", default=None)
    classify.add_argument("--since", type=int, default=0)
    classify.set_defaults(handler=command_classify)

    status = subparsers.add_parser("status", help="Paketstand ausgeben")
    status.add_argument("--project", required=True)
    status.set_defaults(handler=command_status)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
