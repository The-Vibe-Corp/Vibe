#!/usr/bin/env python3
"""Paketauswahl und Abschlussschranke für den vibe-Paketläufer.

Der Läufer benutzt dieses Modul, damit Auswahl, Vorabprüfung, Bewertung des
Agentenergebnisses und Abschlussbericht versioniert und testbar sind. Die
Datei arbeitet ausschließlich lokal: keine Modellaufrufe, keine Netzverbindung
und keine Änderung an Projektdateien außer dem projektlokalen Auswahlstand
unter ``.vibe/tmp/``.
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

CHECKBOX_DONE = re.compile(r"^- \[[xX]\]")
CHECKBOX_ANY = re.compile(r"^- \[[ xX]\]")
BLOCK_MARKER = "BLOCKIERT:"
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\d+")
COMMIT_PATTERN = re.compile(r"Commit\s*:\s*`?([0-9a-fA-F]{7,40})`?")
PROOF_PATTERN = re.compile(r"(?:Test|Datei)\s*:\s*\S+")
DEPENDENCY_PATTERN = re.compile(r"Abhängigkeiten\s*:\s*(.+)")
PRIORITY_PATTERN = re.compile(r"Priorität\s*:\s*(P\d)")
VERDICT_PATTERN = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?verdict\s*:\s*\**\s*PASS\b"
)

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


def proof_commit(block):
    match = COMMIT_PATTERN.search(block)
    return match.group(1) if match else ""


def commit_exists(project, revision):
    if not revision:
        return False
    return run_git(project, "cat-file", "-e", revision + "^{commit}").returncode == 0


def proof_ok(project, block):
    revision = proof_commit(block)
    if not revision or not commit_exists(project, revision):
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
    """Hält den projektlokalen Auswahlstand aus dem Git-Status heraus."""
    git_dir = run_git(project, "rev-parse", "--absolute-git-dir")
    if git_dir.returncode != 0:
        return
    exclude = Path(git_dir.stdout.strip()) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = read_text(exclude).splitlines()
    if ".vibe/tmp/" not in lines:
        text = read_text(exclude)
        if text and not text.endswith("\n"):
            text += "\n"
        write_text_atomic(exclude, text + ".vibe/tmp/\n")


def preflight_errors(project, agents_dir, tester, reviewer):
    """Prüft die Startbedingungen und liefert alle Befunde als Liste."""
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
    dirty = run_git(project, "status", "--porcelain").stdout.strip()
    if dirty:
        errors.append("Arbeitsbaum ist nicht leer:\n" + dirty)

    env = read_env(project / ".vibe" / "project.env")
    tester = tester or env.get("TESTER", "")
    reviewer = reviewer or env.get("REVIEWER", "")
    agents_dir = agents_dir or os.path.join(
        os.path.expanduser("~"), ".config", "opencode", "agents"
    )
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
    if not commits:
        errors.append("Kein Commit seit dem Integrationsstand.")
    if not any(subject.startswith(pid + ":") for _, subject in commits):
        errors.append("Commit mit Präfix '" + pid + ":' fehlt.")

    block = None
    for _, blocks in collect_blocks(project):
        for candidate in blocks:
            if block_id(candidate) == pid:
                block = candidate
                break
        if block is not None:
            break
    if block is None:
        errors.append("Ticket " + pid + " fehlt in TICKETS.md/FEEDBACK.md.")
    else:
        if not is_done(block):
            errors.append("Ticket " + pid + " ist nicht abgehakt ([x] fehlt).")
        proof, reason = proof_ok(project, block)
        if not proof:
            errors.append("Nachweis für " + pid + " fehlt: " + reason + ".")
        else:
            revision = proof_commit(block)
            if not any(commit.startswith(revision) for commit, _ in commits):
                errors.append(
                    "Nachweis-Commit " + revision + " gehört nicht zu diesem Paketbranch."
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

    dirty = run_git(project, "status", "--porcelain").stdout.strip()
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
    errors = preflight_errors(
        args.project, args.agents_dir, args.tester, args.reviewer
    )
    for error in errors:
        print("BLOCKIERT: " + error)
    return EXIT_USAGE if errors else EXIT_OK


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
    preflight.set_defaults(handler=command_preflight)

    gate = subparsers.add_parser("gate", help="Abschlussschranke prüfen")
    gate.add_argument("--project", required=True)
    gate.add_argument("--id", required=True)
    gate.add_argument("--base", required=True)
    gate.set_defaults(handler=command_gate)

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
