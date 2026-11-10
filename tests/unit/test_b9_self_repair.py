"""B9: Blockierte Pakete selbst beheben und Reparatur anbieten.

Die Tests leiten das Verhalten aus dem Arbeitspaket und ``SPEC.md`` ab, nicht
aus dem Implementierungsdiff. Geprüft werden:

* Die Abschlussschranke liest alle Commits einer Nachweiszeile. Das Paket gilt
  als belegt, sobald mindestens einer der gelisteten Commits auf dem
  Paketbranch liegt und mit ``<ID>:`` beginnt. Liegt keiner dort, bleibt die
  Schranke blockiert und nennt alle geprüften Commits.
* Die F16-Preflight-Rückfrage bietet drei Optionen in fester Reihenfolge;
  Option 2 liefert die Aktion ``agent`` mit einer aus den Befunden
  abgeleiteten Anweisung. Freitext hat weiterhin Vorrang, Option 0 prüft
  erneut und Option 1 bricht ab.
* Ein Pakettest- oder Schrankenbefund wird im selben Arbeitsbaum bis zu zwei
  Runden repariert. Eine erfolgreiche Reparatur führt zum Merge; ein
  dauerhafter Befund blockiert nach genau zwei Reparaturrunden ohne Merge und
  ohne neues Paket.
* Ein unsauberer Integrationsstand am Laufende ist mit aktiver Assistenz über
  dieselben drei Optionen behebbar. Ohne Assistenz oder nach Abbruch bleibt
  der bisherige Blockadeabbruch.

Es werden keine Modelle, Router oder echten externen Dienste aufgerufen. Die
opencode-Ablage, ``curl`` und ``vibe`` sind Attrappen; alle Pfade liegen in
temporären Verzeichnissen.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
PACKAGES = BIN / "vibe_packages.py"

# ``vibe_packages`` lädt für die Assistenz die F16-Module aus ``bin``.
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
import vibe_questions  # noqa: E402  (Pfad wird oben ergänzt)

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=1
"""

FEEDBACK_ONE = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"
FEEDBACK_TWO = (
    "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"
    "- [ ] F2 Zweites Paket\n  Beschreibung: Test\n"
)

FINAL_VERIFY_ENV = (
    'VERIFY_FULL=\'echo final > "$VIBE_RUNTIME/final-ran"\''
)

OPTIONS = ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"]


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Nachgebildeter Agent: erzeugt Pakete und repariert Befunde kontrolliert.
# ---------------------------------------------------------------------------
B9_FAKE_AGENT = r'''#!/usr/bin/env python3
"""B9-Testagent ohne Modellaufruf.

B9_MODE steuert das Verhalten:

* ``complete``          — vollständiges Paket, sofort schließbar.
* ``fix-tests``         — Paket lässt den Pakettest scheitern; Reparatur behebt ihn.
* ``fix-gate``          — Paket lässt Doku/Review fehlen; Reparatur ergänzt sie.
* ``persist-gate``      — Doku/Review fehlen dauerhaft; Reparatur ändert nichts.
* ``repair-quota``      — Schrankenbefund; die Reparatur endet mit Quota-Fehler.
* ``fix-integration``   — Paket vollständig; Reparatur räumt den Projektordner auf.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
prompt = args[-1] if args else ""
cwd = pathlib.Path.cwd()
mode = os.environ.get("B9_MODE", "complete")
calls_path = os.environ.get("B9_CALLS")


def log_call(kind):
    if not calls_path:
        return
    record = {"kind": kind, "cwd": str(cwd), "prompt": prompt}
    with open(calls_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(*command, check=True):
    return subprocess.run(
        list(command), cwd=str(cwd), check=check,
        capture_output=True, text=True,
    )


def commit(message):
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", message)
    return run("git", "rev-parse", "--short", "HEAD").stdout.strip()


def mark_done(pid, short):
    for name in ("TICKETS.md", "FEEDBACK.md"):
        path = cwd / name
        if not path.is_file():
            continue
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
                item for item in continuation
                if not re.match(r"\s*(Commit|Test|Datei):", item)
            ]
            out.extend(continuation)
            out.append(
                "  Commit: " + short + "; Test: test_"
                + pid.lower().replace("-", "_")
            )
        path.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_evidence(pid):
    (cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (cwd / "docs" / "features" / (pid + ".md")).write_text(
        "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
    )
    (cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
    (cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
        "# Review\n\nVerdict: PASS\n", encoding="utf-8"
    )


def complete_package(pid):
    (cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
    if mode == "fix-tests":
        (cwd / "package_test_fail.txt").write_text("rot\n", encoding="utf-8")
    short = commit(pid + ": Umsetzung")
    mark_done(pid, short)
    write_evidence(pid)
    commit(pid + ": Nachweis")


def incomplete_package(pid):
    (cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
    short = commit(pid + ": Umsetzung")
    mark_done(pid, short)
    commit(pid + ": Teilnachweis")


match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", prompt)
pid = match.group(1) if match else "F1"
if not match:
    repair_pid = re.search(r"\b([A-Z][A-Za-z0-9_-]*\d+)\b", prompt)
    if repair_pid:
        pid = repair_pid.group(1)
# Ein Reparaturauftrag darf den Wortlaut des Pakets wiederholen. Sobald die
# Arbeitskopie bereits eine Umsetzung enthält, ist ein weiterer Aufruf keine
# neue Paketbearbeitung, sondern eine Reparatur.
is_package = (
    "Wortlaut:" in prompt
    and "Arbeitspaket " in prompt
    and not (cwd / ("impl-" + pid + ".txt")).exists()
)

if is_package:
    log_call("package")
    if mode in ("fix-gate", "persist-gate", "repair-quota"):
        incomplete_package(pid)
    else:
        complete_package(pid)
    sys.exit(0)

log_call("repair")
if mode == "fix-integration":
    target = cwd / "unfertig.txt"
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    run("git", "add", "-A")
    staged = subprocess.run(
        ["git", "-C", str(cwd), "diff", "--cached", "--quiet"],
        check=False,
    )
    if staged.returncode != 0:
        commit("Reparatur: Integrationsstand")
    sys.exit(0)
if mode == "fix-tests":
    target = cwd / "package_test_fail.txt"
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    commit(pid + ": Pakettest repariert")
    sys.exit(0)
if mode == "fix-gate":
    write_evidence(pid)
    commit(pid + ": Reparatur")
    sys.exit(0)
if mode == "repair-quota":
    print("429 rate limit: quota exceeded", file=sys.stderr)
    sys.exit(1)
# persist-gate: absichtlich nichts beheben.
sys.exit(0)
'''


def install_b9_fake_tools(root):
    """Legt opencode-, package-agent- und curl-Attrappen in einem PATH ab."""
    fakebin = root / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    for name in ("opencode", "package-agent"):
        path = fakebin / name
        path.write_text(B9_FAKE_AGENT, encoding="utf-8")
        path.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(support.FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return fakebin


# ---------------------------------------------------------------------------
# (a) Abschlussschranke mit mehreren Commit-Hashes
# ---------------------------------------------------------------------------
class PackageGateTest(unittest.TestCase):
    """Schrankenlogik mit echten Mini-Repositories aus ``vibe_packages``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        support.write_project(
            self.project,
            PROJECT_ENV.replace("MAX_RETRIES=1\n", ""),
            feedback=FEEDBACK_ONE,
        )
        support.commit_all(self.project, "Ausgangsstand")
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()
        self.module = load_module(PACKAGES, "vibe_packages_b9_gate")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, message):
        support.commit_all(self.project, message)
        return support.git(
            self.project, "rev-parse", "--short", "HEAD"
        ).stdout.strip()

    def write_proof(self, first, second):
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n"
            "- [x] F1 Mehrfachnachweis\n"
            "  Beschreibung: Test\n"
            "  Commit: %s (Umsetzung), %s (Tests); Test: test_f1\n"
            % (first, second),
            encoding="utf-8",
        )

    def write_proof_block(self, text):
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + text, encoding="utf-8"
        )

    def write_evidence(self):
        self.write("docs/features/F1.md", "# F1\n\nDoku.\n")
        self.write(
            "docs/reviews/F1-review-1.md",
            "# Review\n\nVerdict: PASS\n",
        )

    def errors(self):
        return self.module.gate_errors(
            str(self.project), "F1", self.base
        )

    def test_gate_accepts_proof_when_one_of_several_commits_is_on_the_branch(self):
        """Ein Paket-Commit unter mehreren gelisteten Commits genügt."""
        self.write("impl.txt", "umsetzung\n")
        self.commit("F1: Umsetzung")
        self.write("tests/test_f1.py", "def test_f1():\n    pass\n")
        package_commit = self.commit("F1: Tests")
        # Der erste gelistete Commit liegt außerhalb des Paketbranches; nur
        # der zweite, ausdrücklich benannte Paket-Commit belegt das Paket.
        self.write_proof(self.base[:7], package_commit)
        self.write_evidence()
        self.commit("F1: Nachweis")

        self.assertEqual(self.errors(), [])

    def test_gate_blocks_and_names_all_checked_commits_when_none_is_on_the_branch(
        self,
    ):
        """Kein gelisteter Commit auf dem Paketbranch: blockiert mit Nennung."""
        support.git(self.project, "checkout", "-q", "-b", "other")
        self.write("fremd-a.txt", "a\n")
        foreign_a = self.commit("Other: alt")
        self.write("fremd-b.txt", "b\n")
        foreign_b = self.commit("Other: neu")
        support.git(self.project, "checkout", "-q", "main")

        self.write("impl.txt", "umsetzung\n")
        self.commit("F1: Umsetzung")
        self.write_proof(foreign_a, foreign_b)
        self.write_evidence()
        self.commit("F1: Nachweis")

        errors = self.errors()
        combined = "\n".join(errors)

        self.assertTrue(errors, "Schranke akzeptierte fremde Nachweise")
        self.assertIn(foreign_a, combined)
        self.assertIn(foreign_b, combined)

    def test_gate_finds_package_commit_on_wrapped_commit_line(self):
        """Ein Paket-Commit auf der eingerückten Fortsetzungszeile genügt.

        Charakterisierung: Dieses Verhalten ist in ``bb94d86`` bereits
        umgesetzt. Der Test wurde nachgezogen und ist deshalb sofort grün;
        eine Rotphase wird hier nicht behauptet.
        """
        self.write("impl.txt", "umsetzung\n")
        self.commit("F1: Umsetzung")
        self.write("tests/test_f1.py", "def test_f1():\n    pass\n")
        package_commit = self.commit("F1: Tests")
        self.write_proof_block(
            "- [x] F1 Umbrochener Nachweis\n"
            "  Beschreibung: Test\n"
            "  Commit: %s (Umsetzung),\n"
            "    %s (Tests); Test: test_f1\n"
            % (self.base[:7], package_commit)
        )
        self.write_evidence()
        self.commit("F1: Nachweis")

        self.assertEqual(self.errors(), [])

    def test_gate_stops_commit_collection_at_next_proof_field(self):
        """Ein Hash im folgenden ``Test:``-Feld gilt nicht als Commit.

        Charakterisierung: Auch dieses Verhalten ist in ``bb94d86`` bereits
        umgesetzt; der Test ist sofort grün und belegt nur die bestehende
        Feldgrenze, keine neue Rotphase.
        """
        support.git(self.project, "checkout", "-q", "-b", "other")
        self.write("fremd.txt", "fremd\n")
        foreign = self.commit("Other: fremd")
        support.git(self.project, "checkout", "-q", "main")
        self.write("impl.txt", "umsetzung\n")
        package_commit = self.commit("F1: Umsetzung")
        self.write_proof_block(
            "- [x] F1 Neues Feld\n"
            "  Beschreibung: Test\n"
            "  Commit: %s (Umsetzung),\n"
            "    %s (Tests)\n"
            "  Test: %s; test_f1\n"
            % (self.base[:7], foreign, package_commit)
        )
        self.write_evidence()
        self.commit("F1: Nachweis")

        errors = self.errors()
        combined = "\n".join(errors)

        self.assertTrue(errors, "Hash im Test-Feld wurde als Commit gelesen")
        self.assertIn(foreign, combined)
        self.assertNotIn(
            package_commit,
            combined,
            "Der Hash aus dem Test-Feld wurde als Commit geprüft.",
        )


# ---------------------------------------------------------------------------
# (b) F16-Preflight-Rückfrage: drei Optionen und Aktion ``agent``
# ---------------------------------------------------------------------------
class AssistUnitFixture(unittest.TestCase):
    """Direkter Aufruf der Preflight-Assistenz mit echten F16-Rückfragen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.state = self.root / "state"
        self.state.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project, PROJECT_ENV, feedback=FEEDBACK_ONE
        )
        support.commit_all(self.project, "Ausgangsstand")
        (self.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        self.packages = load_module(
            PACKAGES, "vibe_packages_b9_assist"
        )
        self.old_lock = os.environ.get("VIBE_STORAGE_LOCK_DIR")
        os.environ["VIBE_STORAGE_LOCK_DIR"] = str(self.root / "locks")

    def tearDown(self):
        if self.old_lock is None:
            os.environ.pop("VIBE_STORAGE_LOCK_DIR", None)
        else:
            os.environ["VIBE_STORAGE_LOCK_DIR"] = self.old_lock
        self.tmp.cleanup()

    def start(self, timeout=20):
        result = {}

        def run():
            result.update(
                self.packages.assist_preflight(
                    str(self.project),
                    str(self.agents),
                    "test-agent",
                    "code-reviewer",
                    state_dir=str(self.state),
                    runtime=str(self.runtime),
                    project_name="proj",
                    timeout=timeout,
                )
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return result, thread

    def wait_question(self, seen=(), timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in vibe_questions.open_questions(
                str(self.runtime)
            ):
                if record["id"] not in seen:
                    return record
            time.sleep(0.02)
        raise AssertionError("Keine Rückfrage innerhalb von %s s." % timeout)

    def answer(self, record, option, text=""):
        vibe_questions.answer(
            str(self.runtime), record["id"], option=option,
            text=text, by="test",
        )

    def join(self, thread):
        thread.join(10)
        self.assertFalse(thread.is_alive(), "Assistenz wartete weiter")


class PreflightAssistOptionsTest(AssistUnitFixture):
    """Verhalten 1-3: feste Reihenfolge, Aktion ``agent`` und Vorrang."""

    def test_assist_offers_three_options_and_option_two_returns_agent_action(self):
        """Option 2 liefert eine aus den Befunden abgeleitete Anweisung."""
        result, thread = self.start()
        record = self.wait_question()

        self.assertEqual(record.get("options"), OPTIONS)

        self.answer(record, 2)
        self.join(thread)

        self.assertEqual(result.get("action"), "agent", result)
        instruction = result.get("instruction", "")
        self.assertTrue(instruction, result)
        self.assertIn("Arbeitsbaum", instruction)
        self.assertIn("unfertig.txt", instruction)

    def test_free_text_wins_over_option_two(self):
        """Freitext ersetzt die Befund-Anweisung auch bei Option 2."""
        result, thread = self.start()
        record = self.wait_question()
        text = "Bitte nur die Notizen prüfen, nichts committen"

        self.answer(record, 2, text)
        self.join(thread)

        self.assertEqual(result.get("action"), "agent", result)
        self.assertEqual(result.get("instruction"), text)

    def test_option_zero_retries_and_option_one_aborts(self):
        """0 prüft erneut (neue Rückfrage), 1 bricht ohne Agentenauftrag ab."""
        result, thread = self.start()
        first = self.wait_question()
        self.assertEqual(first.get("options"), OPTIONS)

        self.answer(first, 0)
        second = self.wait_question(seen={first["id"]})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second.get("options"), OPTIONS)

        self.answer(second, 1)
        self.join(thread)

        self.assertEqual(result.get("action"), "abort", result)


# ---------------------------------------------------------------------------
# Gemeinsamer Läufer mit echtem Git und nachgebildeter opencode-Ablage
# ---------------------------------------------------------------------------
class B9RunnerFixture(unittest.TestCase):
    """Isolierter ``bin/vibe-run.sh`` ohne Modell- oder Netzaufrufe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(
            support.FAKE_VIBE, encoding="utf-8"
        )
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()
        self.calls_path = self.root / "b9-calls.jsonl"
        self.fakebin = install_b9_fake_tools(self.root)
        self.project = None
        self.proc = None
        self.out_path = None
        self.handles = []
        self.run_count = 0

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for handle in self.handles:
            handle.close()
        self.tmp.cleanup()

    def make_project(self, env_text=PROJECT_ENV, feedback=FEEDBACK_ONE,
                     name="proj"):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        self.project = project
        return project

    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") \
                    or key.startswith("B9_"):
                env.pop(key, None)
        for key in (
            "AGENT",
            "MAX_PACKAGES",
            "MAX_RETRIES",
            "SANDBOX",
            "SANDBOX_TOOLS",
            "VERIFY_FULL",
            "VERIFY_PACKAGE",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": project.name,
                "VIBE_RETRY_DELAY": "0",
                "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "15",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "B9_CALLS": str(self.calls_path),
                "B9_MODE": "complete",
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def start_runner(self, project, **extra):
        self.out_path = self.root / ("runner-%d.out" % self.run_count)
        self.run_count += 1
        handle = self.out_path.open("w", encoding="utf-8")
        self.handles.append(handle)
        self.proc = subprocess.Popen(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.proc

    def output(self):
        if self.out_path is None or not self.out_path.exists():
            return ""
        return self.out_path.read_text(encoding="utf-8", errors="replace")

    def log(self, project=None):
        project = project or self.project
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined(self, result):
        return result.stdout + result.stderr + "\n" + self.log()

    def wait_exit(self, timeout=90):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError(
                "Läufer lief nach %s s weiter.\n%s" % (timeout, self.output())
            )

    def calls(self):
        if not self.calls_path.is_file():
            return []
        result = []
        for line in self.calls_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if line.strip():
                result.append(json.loads(line))
        return result

    def kinds(self):
        return [call["kind"] for call in self.calls()]

    def question_folder(self):
        return self.runtime / "questions"

    def question_files(self):
        folder = self.question_folder()
        if not folder.is_dir():
            return []
        return sorted(
            path
            for path in folder.iterdir()
            if path.name.endswith(".json")
            and not path.name.endswith(".answer.json")
        )

    def open_questions(self):
        folder = self.question_folder()
        result = []
        for path in self.question_files():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict) or "id" not in record:
                continue
            if (folder / (record["id"] + ".answer.json")).exists():
                continue
            result.append(record)
        return result

    def wait_for_question(self, seen=(), timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in self.open_questions():
                if record["id"] not in seen:
                    return record
            if self.proc.poll() is not None:
                time.sleep(0.2)
                for record in self.open_questions():
                    if record["id"] not in seen:
                        return record
                raise AssertionError(
                    "Läufer endete ohne erwartete Rückfrage (Exit %s):\n%s"
                    % (self.proc.returncode, self.output())
                )
            time.sleep(0.05)
        raise AssertionError(
            "Keine Rückfrage innerhalb von %s s.\n%s"
            % (timeout, self.output())
        )

    def answer(self, record, option, text=""):
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": option,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            }
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def worktrees(self):
        return [
            path
            for path in (self.runtime / "worktrees").glob("*")
            if path.is_dir()
        ]

    def head(self, project):
        return support.git(
            project, "rev-parse", "HEAD"
        ).stdout.strip()

    def make_dirty(self, project, name="unfertig.txt"):
        path = project / name
        path.write_text("unfertig\n", encoding="utf-8")
        return path


class RunnerPreflightOptionTest(B9RunnerFixture):
    """Option 2 startet den Agenten im Projektordner und danach das Paket."""

    def test_preflight_option_two_runs_the_agent_in_the_project(self):
        project = self.make_project()
        self.make_dirty(project)

        self.start_runner(
            project, VIBE_PREFLIGHT_ASSIST="1", B9_MODE="fix-integration"
        )
        record = self.wait_for_question()

        self.assertEqual(record.get("options"), OPTIONS)
        self.answer(record, 2)
        rc = self.wait_exit(timeout=120)

        self.assertEqual(rc, 0, self.output())
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["repair", "package"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(str(project)),
            "Der Preflight-Agent lief nicht im Projektordner.",
        )
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertIn("unfertig.txt", calls[0]["prompt"])
        self.assertFalse((project / "unfertig.txt").exists())
        self.assertIn("Geschlossen: F1", self.output())
        # Option 2 nutzt die aus den Befunden abgeleitete Anweisung; das
        # Laufprotokoll darf sie nicht als Nutzeranweisung ausgeben.
        self.assertIn(
            "Befunden abgeleiteten Anweisung",
            self.output(),
            "Das Protokoll unterscheidet die Befund-Anweisung nicht.",
        )
        self.assertNotIn(
            "Anweisung des Nutzers",
            self.output(),
            "Option 2 wurde als Nutzeranweisung protokolliert.",
        )


class RunnerPackageRepairTest(B9RunnerFixture):
    """Verhalten 4-6: Pakettest- und Schrankenbefunde im Läufer."""

    def test_gate_finding_is_repaired_in_the_same_worktree_and_merged(self):
        project = self.make_project()
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="fix-gate", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)

        self.assertEqual(result.returncode, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(calls[1]["cwd"]),
            "Die Reparatur lief nicht im selben Arbeitsbaum.",
        )
        self.assertIn("docs/features/F1.md", calls[1]["prompt"])
        self.assertNotEqual(self.head(project), base, "Paket wurde nicht gemergt")
        merged = support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt")
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertIn("Geschlossen: F1", result.stdout)
        self.assertEqual(self.worktrees(), [], "Arbeitskopie blieb liegen")

    def test_package_test_finding_is_repaired_in_the_same_worktree_and_merged(self):
        env_text = PROJECT_ENV.replace(
            'VERIFY_PACKAGE="true"',
            'VERIFY_PACKAGE="test ! -f package_test_fail.txt"',
        )
        project = self.make_project(env_text=env_text)

        result = self.run_runner(
            project, B9_MODE="fix-tests", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)

        self.assertEqual(result.returncode, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(calls[1]["cwd"]),
            "Die Reparatur lief nicht im selben Arbeitsbaum.",
        )
        prompt = calls[1]["prompt"]
        self.assertIn("F1", prompt)
        self.assertRegex(
            prompt, r"(?i)(pakettest|paketprüfung|package_test_fail|nicht grün)"
        )
        self.assertFalse(
            (project / "package_test_fail.txt").exists(),
            "Reparatur wurde nicht gemergt.",
        )
        self.assertIn("Geschlossen: F1", result.stdout)

    def test_persistent_gate_finding_blocks_after_two_repairs_without_merge(self):
        project = self.make_project(feedback=FEEDBACK_TWO)
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="persist-gate", VIBE_MAX_PACKAGES="2"
        )
        output = self.combined(result)
        calls = self.calls()

        self.assertEqual(result.returncode, 1, output)
        self.assertEqual(
            [call["kind"] for call in calls],
            ["package", "repair", "repair"],
            "Es wurden nicht genau zwei Reparaturrunden versucht.",
        )
        self.assertEqual(
            len({os.path.realpath(call["cwd"]) for call in calls}),
            1,
            "Die Reparaturrunden liefen nicht im selben Arbeitsbaum.",
        )
        self.assertIn("docs/features/F1.md", calls[1]["prompt"])
        self.assertIn("docs/features/F1.md", calls[2]["prompt"])

        # Kein Merge und kein neues Paket.
        self.assertEqual(self.head(project), base, "Trotz Befund wurde gemergt")
        # ``cat-file -e`` liefert je nach Git-Version 1 oder 128 für einen
        # fehlenden Pfad; entscheidend ist der Nicht-Null-Status.
        self.assertNotEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
        )
        self.assertNotIn("Geschlossen: F1", result.stdout)
        self.assertFalse(
            any("Arbeitspaket F2" in call["prompt"] for call in calls),
            "Nach dem Befund wurde ein neues Paket gestartet.",
        )
        self.assertIn("BLOCKIERT", output)
        self.assertIn("docs/features/F1.md", output)

    def test_quota_during_repair_blocks_without_second_round_and_names_quota(self):
        """Quota beim Reparatur-Agenten blockiert sofort und ohne zweite Runde."""
        project = self.make_project()
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="repair-quota", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)
        calls = self.calls()

        self.assertEqual(result.returncode, 1, output)
        self.assertEqual(
            [call["kind"] for call in calls],
            ["package", "repair"],
            "Nach dem Quota-Fehler wurde eine weitere Reparaturrunde gestartet.",
        )
        self.assertEqual(self.head(project), base, "Trotz Quota-Fehler wurde gemergt")
        self.assertNotEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
        )
        # Die Quota-Meldung des Agenten steht zwar im Protokoll; entscheidend
        # ist die Klassifizierung durch den Läufer in der BLOCKIERT-Zeile.
        self.assertRegex(
            output,
            r"(?im)^BLOCKIERT:.*(?:Quota|Kontingent)",
            "Der Läufer nennt die Quota-Klassifizierung nicht: %s" % output,
        )


class RunnerIntegrationAssistTest(B9RunnerFixture):
    """Verhalten 7-9: unsauberer Stand am Laufende."""

    def make_integration_project(self):
        env_text = PROJECT_ENV.replace(
            'VERIFY_FULL="true"', FINAL_VERIFY_ENV
        )
        project = self.make_project(env_text=env_text)
        self.make_dirty(project)
        return project

    def start(self, project, assist):
        extra = {
            "VIBE_KEEP_CHANGES": "1",
            "VIBE_MAX_PACKAGES": "1",
            "B9_MODE": "fix-integration",
        }
        if assist:
            extra["VIBE_PREFLIGHT_ASSIST"] = "1"
        self.start_runner(project, **extra)

    def test_dirty_integration_is_repaired_with_assistance_and_final_check_runs(
        self,
    ):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=True)
        record = self.wait_for_question()

        self.assertEqual(record.get("options"), OPTIONS)
        self.answer(record, 2)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[1]["cwd"]),
            os.path.realpath(str(project)),
            "Die Reparatur lief nicht im Projektordner.",
        )
        self.assertIn("unfertig.txt", calls[1]["prompt"])
        self.assertRegex(
            calls[1]["prompt"],
            r"(?i)(integrationsstand|arbeitsbaum|nicht sauber)",
        )
        self.assertFalse((project / "unfertig.txt").exists())
        self.assertTrue(marker.is_file(), "Abschlussprüfung lief nicht")
        self.assertEqual(
            support.git(project, "status", "--porcelain").stdout, ""
        )

    def test_dirty_integration_abort_keeps_the_block(self):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=True)
        record = self.wait_for_question()
        self.answer(record, 1)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 1, output)
        self.assertEqual([call["kind"] for call in self.calls()], ["package"])
        self.assertFalse(marker.exists(), "Abschlussprüfung lief trotz Abbruch")
        self.assertIn("Integrationsstand ist nicht sauber", output)
        self.assertTrue((project / "unfertig.txt").exists())

    def test_dirty_integration_without_assistance_keeps_the_block(self):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=False)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 1, output)
        self.assertEqual([call["kind"] for call in self.calls()], ["package"])
        self.assertEqual(self.question_files(), [])
        self.assertFalse(marker.exists(), "Abschlussprüfung lief ohne Assistenz")
        self.assertIn("Integrationsstand ist nicht sauber", output)


if __name__ == "__main__":
    unittest.main()
