"""Gemeinsame Helfer für Tests des Paket-Läufers.

Die Datei ist kein Testmodul (der Name beginnt nicht mit ``test_``). Sie
liefert ein echtes, kleines Git-Repository, eine Installation mit den
Läufermodulen und einen nachgebildeten Agenten, der ein Arbeitspaket
vollständig abschließt (Commit, Nachweis, Feature-Dokumentation, Review).
Es werden keine Modellaufrufe ausgeführt.
"""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"


def git(project, *args, env=None):
    """Führt git im Projektordner aus, ohne eine Ausnahme zu werfen."""
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def init_repo(project):
    """Legt ein leeres Repository mit reproduzierbarer Identität an."""
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    git(project, "config", "user.name", "Test")
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "commit.gpgsign", "false")
    return project


def commit_all(project, message="Ausgangsstand"):
    """Commitet den aktuellen Stand; ein Fehler ist ein Testfehler."""
    git(project, "add", "-A")
    result = git(project, "commit", "-q", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def install_runner(install):
    """Kopiert Läufer und benötigte Module in eine Testinstallation."""
    bin_dir = install / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vibe-run.sh", "vibe_runs.py", "vibe_packages.py"):
        shutil.copy(BIN / name, bin_dir / name)
    return bin_dir


def write_agents(agents_dir, *names):
    """Legt minimale Agentendateien an; der Läufer prüft nur die Existenz."""
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        (agents_dir / (name + ".md")).write_text(
            "---\ndescription: Testagent\nmode: subagent\n---\n",
            encoding="utf-8",
        )


def write_project(project, env_text, feedback="", tickets=""):
    """Schreibt Projektdateien, die der Läufer und die Auswahl benötigen."""
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8"
    )
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8"
    )


FAKE_OPENCODE = r'''#!/usr/bin/env python3
"""Schließt ein Arbeitspaket so ab, wie es die Abschlussschranke verlangt."""
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
prompt = args[-1] if args else ""
match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", prompt)
pid = match.group(1) if match else "F1"
cwd = pathlib.Path.cwd()

args_path = os.environ.get("FAKE_ARGS_PATH")
if args_path:
    with open(args_path, "wb") as handle:
        for argument in args:
            handle.write(argument.encode("utf-8") + b"\0")

output = os.environ.get("FAKE_OUTPUT")
if output:
    sys.stdout.write(output)
    sys.stdout.flush()

calls = os.environ.get("FAKE_CALLS")
if calls:
    with open(calls, "a", encoding="utf-8") as handle:
        handle.write(pid + "\t" + str(cwd) + "\n")

counter_path = pathlib.Path(os.environ.get("FAKE_COUNTER", os.devnull))
try:
    counter = int(counter_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    counter = 0
counter_path.write_text(str(counter + 1), encoding="utf-8")

sequence = os.environ.get("FAKE_MODE_SEQUENCE", "")
if sequence:
    modes = [item.strip() for item in sequence.split(",") if item.strip()]
    mode = modes[min(counter, len(modes) - 1)]
else:
    mode = os.environ.get("FAKE_MODE", "complete")

if mode == "quota":
    sys.stderr.write("429 rate limit exceeded\n")
    sys.exit(1)
if mode == "auth":
    sys.stderr.write("401 unauthorized\n")
    sys.exit(1)
if mode == "network":
    sys.stderr.write("ECONNRESET connection reset by peer\n")
    sys.exit(1)
if mode == "network-first" and counter == 0:
    sys.stderr.write("ECONNRESET connection reset by peer\n")
    sys.exit(1)
if mode == "fail":
    sys.stderr.write("beliebiger Agentenfehler\n")
    sys.exit(1)
if mode == "no-artifacts":
    sys.exit(0)


def run(*command, check=True):
    return subprocess.run(
        list(command), cwd=cwd, check=check, capture_output=True, text=True
    )


def mark_done(path, commit):
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    index = 0
    pattern = re.compile(r"^- \[ \] " + re.escape(pid) + r"\b")
    while index < len(lines):
        line = lines[index]
        if not pattern.match(line):
            out.append(line)
            index += 1
            continue
        out.append(line.replace("- [ ]", "- [x]", 1))
        index += 1
        continuation = []
        while index < len(lines):
            candidate = lines[index]
            if candidate.startswith((" ", "\t")):
                continuation.append(candidate)
                index += 1
            elif not candidate.strip():
                index += 1
            else:
                break
        continuation = [
            item
            for item in continuation
            if not re.match(r"\s*(Commit|Test|Datei):", item)
        ]
        out.extend(continuation)
        out.append("  Commit: " + commit + "; Test: test_" + pid.lower().replace("-", "_"))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


(cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Umsetzung")
short = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

for name in ("TICKETS.md", "FEEDBACK.md"):
    mark_done(cwd / name, short)

(cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "features" / (pid + ".md")).write_text(
    "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
)
(cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
    "# Review\n\nVerdict: PASS\n", encoding="utf-8"
)
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Nachweis")
dirty = os.environ.get("FAKE_DIRTY_INTEGRATION")
if dirty and counter == 0:
    pathlib.Path(dirty, "dirty.txt").write_text("x\n", encoding="utf-8")
if os.environ.get("FAKE_PAUSE_AFTER_FIRST") and counter == 0:
    runtime = pathlib.Path(os.environ["VIBE_RUNTIME"])
    name = os.environ.get("VIBE_LOGNAME", "proj")
    (runtime / (name + ".pause-after")).touch()
sys.exit(0)
'''

FAKE_VIBE = '''#!/usr/bin/env python3
print("Fritzbox-Automatik ist aus")
raise SystemExit(3)
'''

FAKE_CURL = '''#!/usr/bin/env bash
exit 7
'''


def install_fake_tools(root):
    """Legt opencode-, curl- und vibe-Attrappen in einem eigenen PATH ab."""
    fakebin = root / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    for name in ("opencode", "package-agent"):
        path = fakebin / name
        path.write_text(FAKE_OPENCODE, encoding="utf-8")
        path.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return fakebin
