"""Abnahme AP11 „Priorisierung der Abarbeitungsreihenfolge“.

Die Reihenfolge der Arbeitspakete/Feedback/Bugs soll je Projekt über den
Schlüssel ``PACKAGE_ORDER`` in ``.vibe/project.env`` einstellbar sein und ist
dann verbindlich für die Agenten; erledigte Aufgaben werden der Priorisierung
entnommen (TICKETS.md AP11). Die Testfälle sind unabhängig von der
Implementierung aus dem Arbeitspaket und SPEC.md abgeleitet:

 1. Ohne konfigurierte Priorisierung bleibt die bisherige Auswahl unver-
    ändert: TICKETS vor FEEDBACK, innerhalb der TICKETS nach Priorität
    (P0..P2, ohne Angabe zuletzt), sonst Dateireihenfolge. (AK 1)
 2. Der Auswahlstand (next-package.json) vermerkt ohne Priorisierung nicht,
    aus einer projektweiten Priorisierung zu stammen (``ordered`` fehlt
    bzw. ist nicht wahr). (AK 7)
 3. Ein konfigurierter Eintrag in ``PACKAGE_ORDER`` schlägt Quellen-Reihen-
    folge und Prioritätsfelder: gewählt wird der erste Eintrag, der offen,
    nicht BLOCKIERT, nicht geskippt und bereit ist. (AK 2)
 4. Trennung der Einträge durch Komma, Semikolon und/oder Leerraum. (AK 2)
 5. Erledigte Aufgaben (abgehakt mit Nachweis) werden der Priorisierung
    entnommen: sie werden übersprungen, nachfolgende Einträge rücken auf,
    erledigte erscheinen nie als Wahl. (AK 3)
 6. Gesperrte (BLOCKIERT) und abhängigkeitsgeblockte Einträge in der
    Priorisierung werden übersprungen, ohne die Auswahl zu blockieren. (AK 4)
 7. Unbekannte und doppelte Kennungen behindern das Wählen nicht (stilles
    Überspringen). (AK 5)
 8. Die Skip-Liste (--skip) bleibt auch für priorisierte Einträge wirksam. (AK 6)
 9. Der Auswahlstand vermerkt ``ordered: true``, wenn das gewählte Paket
    aus der Priorisierung kam. (AK 7)
10. Der echte Läufer-Einstiegspunkt (``bin/vibe_packages.py select``) liest
    die Priorisierung, überspringt unbekannte IDs still und wendet --skip
    an. (AK 2/5/6)
11. CLI ``vibe priority <projekt>``: Anzeige der konfigurierten und der
    effektiven Reihenfolge; ``set`` schreibt ``PACKAGE_ORDER`` per atomarer
    Änderung und erhält alle anderen Zeilen (auch Kommentare, CRLF); set
    lehnt unbekannte IDs ohne Dateiänderung ab und reduziert Dubletten
    still; ``clear`` leert die Priorisierung, die Auswahl fällt auf die
    Standardordnung zurück. (AK 5/8)

Geprüfte Einstiegspunkte: ``select_package`` in ``bin/vibe_packages.py``
(wie der Läufer sie benutzt), das Subkommando ``select`` desselben Skripts
als echte Prozessaufrufe und die CLI ``bin/vibe`` (``vibe priority``). Keine
Modellaufrufe, keine externen Dienste, keine produktiven Pfade.

Browserabnahme des Dashboards: tests/browser/test_ap11_priority_ui.py.

Run:

    python3 -m unittest tests.unit.test_ap11_priority -v
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"

# Umgebungsvariablen, die für Prozessaufrufe isoliert werden müssen, damit
# weder die produktive Installation noch persönliche Konfigurationen erreicht
# werden (Muster tests/unit/test_ap9_github.py).
ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
)

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def load_packages():
    """Lädt bin/vibe_packages.py als eigenes Modul (Rotphase: Lücken)."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap11_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def env_values(path):
    """Liest ``SCHLUESSEL=WERT``-Zeilen (einschließlich Anführungszeichen)."""
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def package_order(env_path):
    """Wert von PACKAGE_ORDER als Kennungsliste (Trenner: , ; Leerraum)."""
    raw = env_values(env_path).get("PACKAGE_ORDER", "")
    return [token for token in re.split(r"[,;\s]+", raw) if token]


def write_env(env_path, text):
    """Schreibt project.env; Paketpriorisierung gehört in .vibe/project.env."""
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(project, *argv):
    """Echtes git mit fester Test-Identität, ohne Netzaufrufe."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60,
        env=env,
    )


def git_commit(project):
    """Commitet alles und liefert den Kurzhash (Nachweis erledigter Aufgaben)."""
    git(project, "add", "-A")
    result = git(project, "commit", "-q", "-m", "Teststand")
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return git(project, "rev-parse", "--short", "HEAD").stdout.strip()


def make_project(root, name="proj", tickets="", feedback="", env_text=""):
    """Minimales eigenes Git-Projekt mit Arbeitsnotizen und project.env."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    git(project, "init", "-q", "-b", "main")
    (project / ".vibe").mkdir(exist_ok=True)
    write_env(
        project / ".vibe" / "project.env",
        env_text or "TYPE=generic\nTESTER=test-agent\n",
    )
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8")
    git_commit(project)
    return project


def new_proof_commit(project):
    """Erzeugt einen echten neuen Commit und liefert den Kurzhash.

    make_project committet bereits; ein erledigter Nachweis braucht einen
    eigenen, vorhandenen Commit im Projektrepository.
    """
    (Path(project) / "umsetzung.txt").write_text("x\n", encoding="utf-8")
    return git_commit(project)


def done_ticket(commit):
    """Blocktext einer nachweislich erledigten Aufgabe."""
    return "- [x] T0 Erledigt\n  Beschreibung: fertig\n" \
           "  Commit: %s; Test: test_ap11\n" % commit


OPEN_TICKETS = (
    "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
    "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n"
)


class SelectionOrderTest(unittest.TestCase):
    """AK 1–7: Auswahllogik von select_package mit und ohne Priorisierung."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root, tickets=OPEN_TICKETS)
        self.state_path = self.root / "next-package.json"

    def select(self, skip=None):
        """Wählt über die Läuferfunktion und liefert den Auswahlstand."""
        module = load_packages()
        selected = module.select_package(
            str(self.project), skip=skip, state_path=self.state_path)
        state = {}
        if self.state_path.is_file():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        return selected, state

    def set_order(self, raw):
        """Trägt PACKAGE_ORDER so ab, wie es das Projekt vorsieht."""
        env_path = self.project / ".vibe" / "project.env"
        write_env(env_path, "TYPE=generic\nTESTER=test-agent\n"
                            'PACKAGE_ORDER="%s"\n' % raw)

    # ------------------------------------------------------------- AK 1
    def test_without_configuration_tickets_are_selected_before_feedback(self):
        """AK 1.

        Vorbedingung: Projekt ohne PACKAGE_ORDER; je eine offene Aufgabe in
        TICKETS.md und FEEDBACK.md.
        Aktion: select_package aufrufen.
        Erwartet: die TICKETS-Aufgabe wird gewählt (bisherige feste Ordnung).
        """
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text(
            "# FEEDBACK\n\n- [ ] F1 Feedbackaufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])
        self.assertEqual("TICKETS.md", selected["source"])

    def test_without_configuration_the_priority_field_orders_tickets(self):
        """AK 1.

        Vorbedingung: Projekt ohne PACKAGE_ORDER; T1 mit Priorität P2 steht
        vor T2 mit Priorität P0.
        Aktion: select_package aufrufen.
        Erwartet: T2 (höhere Priorität schlägt Dateireihenfolge).
        """
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Später\n  Priorität: P2\n"
            "- [ ] T2 Sofort\n  Priorität: P0\n",
            encoding="utf-8")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_without_configuration_file_order_decides_within_priority(self):
        """AK 1.

        Vorbedingung: Projekt ohne PACKAGE_ORDER; drei offene Aufgaben ohne
        unterschiedliches Prioritätsfeld.
        Aktion: select_package aufrufen.
        Erwartet: die erste Aufgabe der Datei wird gewählt (Dateireihenfolge).
        """
        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])

    def test_without_configuration_state_is_not_marked_as_ordered(self):
        """AK 7 (Grundfall).

        Vorbedingung: Projekt ohne PACKAGE_ORDER.
        Aktion: select_package aufrufen und den Auswahlstand lesen.
        Erwartet: der Auswahlstand vermerkt nicht, aus einer Priorisierung
        zu stammen (Feld ``ordered`` fehlt oder ist nicht wahr).
        """
        selected, state = self.select()

        self.assertIsNotNone(selected)
        self.assertNotEqual(True, state.get("ordered"))

    # ------------------------------------------------------------- AK 2
    def test_package_order_beats_source_order_and_priority_fields(self):
        """AK 2.

        Vorbedingung: PACKAGE_ORDER="F1,T2"; T1 ist das P0-Ticket, T2 ein
        offenes Ticket, F1 ein offener Feedbackeintrag.
        Aktion: select_package aufrufen.
        Erwartet: F1 wird gewählt — der konfigurierte Eintrag schlägt die
        Quellen-Reihenfolge (TICKETS vor FEEDBACK) und das Prioritätsfeld.
        """
        self.set_order("F1,T2")
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Sofort\n  Priorität: P0\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text(
            "# FEEDBACK\n\n- [ ] F1 Feedbackaufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("F1", selected["id"])

    def test_package_order_accepts_comma_semicolon_and_whitespace(self):
        """AK 2.

        Vorbedingung: PACKAGE_ORDER="T2; T1,F3" (Semikolon, Leerraum, Komma
        als Trenner); T1 und T2 offen, F3 ein offener Feedbackeintrag.
        Aktion: select_package aufrufen.
        Erwartet: T2 wird gewählt — alle genannten Trenner trennen Einträge.
        """
        self.set_order("T2; T1,F3")
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text(
            "# FEEDBACK\n\n- [ ] F3 Dritter Eintrag\n  Beschreibung: offen\n",
            encoding="utf-8")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_quoted_package_order_with_spaces_is_understood(self):
        """AK 2 (Ablageform).

        Vorbedingung: PACKAGE_ORDER="T2, T1" mit Leerraum nach dem Trenner,
        wie in .vibe/project.env abgelegt.
        Aktion: select_package aufrufen.
        Erwartet: T2 wird gewählt; die Ablageform behindert die Auswahl nicht.
        """
        self.set_order("T2, T1")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    # ------------------------------------------------------------- AK 3
    def test_done_entries_are_removed_from_the_priority(self):
        """AK 3.

        Vorbedingung: PACKAGE_ORDER="T0,T1"; T0 ist abgehakt und hat einen
        Nachweis (Commit + Test), T1 ist offen.
        Aktion: select_package aufrufen.
        Erwartet: T0 wird übersprungen (nie als Wahl), der nachfolgende
        Eintrag T1 rückt auf.
        """
        commit = new_proof_commit(self.project)
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n" + done_ticket(commit) + OPEN_TICKETS,
            encoding="utf-8")
        self.set_order("T0,T1")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])

    def test_a_done_first_entry_never_becomes_the_choice(self):
        """AK 3 (Negativfall).

        Vorbedingung: PACKAGE_ORDER="T0"; T0 ist nachweislich erledigt und
        die einzige priorisierte Kennung; T1, T2 bleiben offen.
        Aktion: select_package aufrufen.
        Erwartet: erledigte Aufgaben erscheinen nie als Wahl — die Auswahl
        fällt nicht auf das erledigte T0 zurück, sondern auf die
        Standardordnung (T1).
        """
        commit = new_proof_commit(self.project)
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n" + done_ticket(commit) + OPEN_TICKETS,
            encoding="utf-8")
        self.set_order("T0")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertNotEqual("T0", selected["id"])
        self.assertEqual("T1", selected["id"])

    # ------------------------------------------------------------- AK 4
    def test_blocked_entries_in_the_priority_are_skipped(self):
        """AK 4.

        Vorbedingung: PACKAGE_ORDER="T1,T2"; T1 trägt BLOCKIERT.
        Aktion: select_package aufrufen.
        Erwartet: T1 wird übersprungen; T2 wird gewählt (die Auswahl bleibt
        unblockiert).
        """
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Blockiert\n  BLOCKIERT: fehlende Freigabe\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        self.set_order("T1,T2")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_dependency_blocked_entries_in_the_priority_are_skipped(self):
        """AK 4.

        Vorbedingung: PACKAGE_ORDER="T1,T2"; T1 hat die offene Abhängigkeit
        T2 (alle bekannten Abhängigkeiten müssen nachweislich erledigt sein).
        Aktion: select_package aufrufen.
        Erwartet: T1 wird übersprungen; T2 wird gewählt.
        """
        tickets = self.project / "TICKETS.md"
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Abhängig\n  Abhängigkeiten: T2\n"
            "- [ ] T2 Grundlage\n  Beschreibung: offen\n",
            encoding="utf-8")
        self.set_order("T1,T2")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    # ------------------------------------------------------------- AK 5
    def test_unknown_and_duplicate_ids_are_skipped_silently(self):
        """AK 5 (Wahl).

        Vorbedingung: PACKAGE_ORDER="X9,X9,T2"; X9 existiert in keiner
        Arbeitsnotiz.
        Aktion: select_package aufrufen.
        Erwartet: unbekannte und doppelte Kennungen behindern die Auswahl
        nicht (stilles Überspringen); T2 wird gewählt.
        """
        self.set_order("X9,X9,T2")

        selected, _ = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    # ------------------------------------------------------------- AK 6
    def test_skip_list_applies_to_ordered_entries(self):
        """AK 6.

        Vorbedingung: PACKAGE_ORDER="F1,T2"; F1 ist ein offener Feedback-
        eintrag und steht auf der Skip-Liste; T1 ist das erste Ticket.
        Aktion: select_package mit skip=["F1"] aufrufen.
        Erwartet: F1 wird trotz Priorisierung übersprungen; T2 rückt auf.
        Ohne Priorisierung würde die Standardordnung T1 wählen — der Fall
        beweist damit die Wirkung der Priorisierung über die Skip-Liste
        hinaus.
        """
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text(
            "# FEEDBACK\n\n- [ ] F1 Feedbackaufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        self.set_order("F1,T2")

        selected, _ = self.select(skip=["F1"])

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    # ------------------------------------------------------------- AK 7
    def test_ordered_selection_is_marked_in_the_state(self):
        """AK 7.

        Vorbedingung: PACKAGE_ORDER="T2,T1".
        Aktion: select_package aufrufen und den Auswahlstand lesen.
        Erwartet: der Auswahlstand vermerkt, dass das gewählte Paket aus der
        projektweiten Priorisierung kam (``ordered`` wahr).
        """
        self.set_order("T2,T1")

        selected, state = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])
        self.assertEqual(True, state.get("ordered"))


class RunnerCommandTest(unittest.TestCase):
    """AK 2/5/6: Das echte Subkommando ``vibe_packages.py select``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root, tickets=OPEN_TICKETS)
        self.state = self.root / "state.json"

    def set_order(self, raw):
        write_env(self.project / ".vibe" / "project.env",
                  "TYPE=generic\nTESTER=test-agent\n"
                  'PACKAGE_ORDER="%s"\n' % raw)

    def run_select(self, *extra):
        """Führt den Läufer-Aufruf als echten Prozess aus."""
        return subprocess.run(
            [sys.executable, str(PACKAGES), "select",
             "--project", str(self.project), "--state", str(self.state),
             *extra],
            capture_output=True, text=True, check=False, timeout=120,
        )

    def test_select_command_honors_the_package_order(self):
        """AK 2 (Läufer-Einstiegspunkt).

        Vorbedingung: PACKAGE_ORDER="T2,T1" in project.env.
        Aktion: bin/vibe_packages.py select ausführen.
        Erwartet: Exit 0, Ausgabe „T2“, Auswahlstand mit ``ordered`` wahr.
        """
        self.set_order("T2,T1")

        result = self.run_select()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(True, state.get("ordered"))

    def test_select_command_skips_unknown_ids_without_failure(self):
        """AK 5 (Läufer).

        Vorbedingung: PACKAGE_ORDER="X9,T2".
        Aktion: bin/vibe_packages.py select ausführen.
        Erwartet: Exit 0, Ausgabe „T2“ — unbekannte IDs werden still
        übersprungen (die Standardordnung würde T1 wählen).
        """
        self.set_order("X9,T2")

        result = self.run_select()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())

    def test_select_command_applies_the_skip_list(self):
        """AK 6 (Läufer).

        Vorbedingung: PACKAGE_ORDER="F1,T2"; F1 ist ein offener Feedback-
        eintrag und steht auf der Skip-Liste.
        Aktion: bin/vibe_packages.py select --skip F1 ausführen.
        Erwartet: Exit 0, Ausgabe „T2“ — die Skip-Liste bleibt für
        priorisierte Einträge wirksam (die Standardordnung würde T1 wählen).
        """
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text(
            "# FEEDBACK\n\n- [ ] F1 Feedbackaufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        self.set_order("F1,T2")

        result = self.run_select("--skip", "F1")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())


class PriorityCommandLineTest(unittest.TestCase):
    """AK 5/8: CLI ``vibe priority <projekt> [set|clear]``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = self.root = Path(self.tmp.name)
        self.project = make_project(self.workspace, tickets=OPEN_TICKETS)
        self.env_path = self.project / ".vibe" / "project.env"

    def isolated_env(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE": str(self.workspace),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.workspace / "home"),
            "VIBE_INSTALL": str(self.workspace / "_toolchain"),
            "VIBE_STATE": str(self.workspace / "_toolchain"),
            "VIBE_RUNTIME": str(self.workspace / "_logs"),
            "VIBE_AGENTS_DIR": str(
                self.workspace / "home" / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(
                self.workspace / "home" / ".config" / "vibe" / "config.json"),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        env.update(GIT_IDENTITY)
        return env

    def run_cli(self, *argv):
        """Führt „vibe …“ als echten Prozess mit isolierten Pfaden aus."""
        return subprocess.run(
            [sys.executable, str(CLI), *argv],
            cwd=str(self.workspace), env=self.isolated_env(),
            capture_output=True, text=True, check=False, timeout=180,
        )

    def run_select(self):
        """Läufer-Aufruf gegen das Testprojekt (Fallback-Prüfung)."""
        return subprocess.run(
            [sys.executable, str(PACKAGES), "select",
             "--project", str(self.project)],
            capture_output=True, text=True, check=False, timeout=120,
        )

    def read_env_file(self):
        return self.env_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------- AK 8
    def test_cli_priority_shows_configured_and_effective_order(self):
        """AK 8 (Anzeige).

        Vorbedingung: PACKAGE_ORDER="T2,T1" in project.env; T1 und T2 offen.
        Aktion: „vibe priority proj“ ausführen.
        Erwartet: Exit 0; Ausgabe nennt die konfigurierte Reihenfolge und
        die effektive Abarbeitungsreihenfolge; T2 steht vor T1.
        """
        write_env(self.env_path, "TYPE=generic\nTESTER=test-agent\n"
                                 'PACKAGE_ORDER="T2,T1"\n')

        result = self.run_cli("priority", "proj")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("T2", output, "konfigurierte Reihenfolge fehlt: " + output)
        self.assertIn("T1", output, "effektive Reihenfolge fehlt: " + output)
        self.assertLess(output.index("T2"), output.index("T1"),
                        "T2 steht in der Anzeige nicht vor T1: " + output)

    def test_cli_priority_without_configuration_shows_effective_order(self):
        """AK 8 (Anzeige ohne Konfiguration).

        Vorbedingung: kein PACKAGE_ORDER-Eintrag.
        Aktion: „vibe priority proj“ ausführen.
        Erwartet: Exit 0; die effektive Standardordnung (T1 vor T2) wird
        angezeigt, ohne dass die Datei verändert wird.
        """
        before = self.read_env_file()

        result = self.run_cli("priority", "proj")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertIn("T1", output)
        self.assertIn("T2", output)
        self.assertLess(output.index("T1"), output.index("T2"))
        self.assertEqual(before, self.read_env_file(),
                         "Die Anzeige veränderte project.env")

    def test_cli_priority_set_writes_package_order_and_preserves_lines(self):
        """AK 8 (Ablage).

        Vorbedingung: project.env mit Kommentarzeilen und CRLF-Zeilenenden.
        Aktion: „vibe priority proj set T2,T1“ ausführen.
        Erwartet: Exit 0; PACKAGE_ORDER enthält in dieser Reihenfolge T2, T1;
        alle anderen Zeilen (auch Kommentare) bleiben unverändert erhalten;
        die CRLF-Zeilenenden bleiben bestehen.
        """
        write_env(self.env_path,
                  "# Kommentar oben\r\n"
                  "TYPE=generic\r\n"
                  "TESTER=test-agent\r\n"
                  "# Kommentar unten\n")
        before_lines = [line for line in self.read_env_file().splitlines()]

        result = self.run_cli("priority", "proj", "set", "T2,T1")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        text = self.read_env_file()
        self.assertEqual(["T2", "T1"], package_order(self.env_path), text)
        self.assertIn("# Kommentar oben", text)
        self.assertIn("# Kommentar unten", text)
        self.assertIn("TYPE=generic", text)
        self.assertIn("TESTER=test-agent", text)
        # Universal-Newlines übersetzt beim Lesen \r\n zu \n; die Zeilenenden
        # sind deshalb byte-genau zu messen.
        self.assertIn(b"\r\n", self.env_path.read_bytes(),
                      "CRLF-Zeilenenden gingen verloren")
        for line in ("# Kommentar oben", "TYPE=generic", "TESTER=test-agent"):
            self.assertIn(line, text.splitlines())

    def test_cli_priority_set_rejects_unknown_ids_without_change(self):
        """AK 5 (Ablage).

        Vorbedingung: project.env mit bekannten Aufgaben T1, T2.
        Aktion: „vibe priority proj set X9“ ausführen.
        Erwartet: Exitcode ungleich 0; die Datei bleibt byte-identisch
        (unbekannte IDs werden abgelehnt, ohne die Datei zu ändern).
        """
        before = self.read_env_file()

        result = self.run_cli("priority", "proj", "set", "X9")

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        self.assertEqual(before, self.read_env_file(),
                         "Unbekannte ID veränderte project.env")

    def test_cli_priority_set_reduces_duplicates_silently(self):
        """AK 5 (Ablage).

        Vorbedingung: bekannte Aufgaben T1, T2.
        Aktion: „vibe priority proj set T2,T1,T2“ ausführen.
        Erwartet: Exit 0; die abgelegte Reihenfolge enthält T2 und T1
        (Reihenfolge erhalten) und jede Kennung genau einmal.
        """
        result = self.run_cli("priority", "proj", "set", "T2,T1,T2")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        self.assertEqual(["T2", "T1"], package_order(self.env_path))

    def test_cli_priority_clear_empties_and_falls_back(self):
        """AK 8 + AK 2 (Löschen).

        Vorbedingung: PACKAGE_ORDER="T2,T1" abgelegt; T1, T2 offen.
        Aktion: „vibe priority proj clear“ ausführen, danach den
        Läufer-Aufruf „select“ gegen das Projekt starten.
        Erwartet: Exit 0; PACKAGE_ORDER ist geleert (keine Kennung mehr);
        die übrigen project.env-Zeilen bleiben; die Auswahl fällt auf die
        Standardordnung zurück (T1 statt T2).
        """
        write_env(self.env_path, "TYPE=generic\nTESTER=test-agent\n"
                                 'PACKAGE_ORDER="T2,T1"\n')

        result = self.run_cli("priority", "proj", "clear")

        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        text = self.read_env_file()
        self.assertEqual([], package_order(self.env_path), text)
        self.assertIn("TYPE=generic", text)
        self.assertIn("TESTER=test-agent", text)

        fallback = self.run_select()
        self.assertEqual(0, fallback.returncode,
                         fallback.stdout + fallback.stderr)
        self.assertEqual("T1", fallback.stdout.strip())


if __name__ == "__main__":
    unittest.main()
