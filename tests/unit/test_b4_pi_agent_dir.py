"""Unabhängige Tests für Arbeitspaket B4 (Bug: „Fehler bei Verwendung von
PI harness").

Quellen: FEEDBACK.md Eintrag B4 und docs/compatibility.md (Abschnitt
„Pi 1.5.0"). Die Fälle wurden ohne Einsicht in einen Implementierungsdiff
aus den Akzeptanzkriterien abgeleitet. Defekt: Ein Pi-Agentenlauf in einer
Sandbox bricht mit ``EROFS`` ab, weil Pi sein Agentenverzeichnis unter
``~/.pi/agent`` anlegt (``trust.json`` inkl. Sperrdatei
``trust.json.lock``), obwohl ``/`` nur lesend gebunden ist. Pi unterstützt
``PI_CODING_AGENT_DIR`` als vollständige Umleitung des Agentenverzeichnisses
und liest seine Modellanmeldungen aus ``<agentdir>/auth.json``.

Akzeptanzkriterien der Testfälle:

- AK1: ``bwrap_argv`` setzt das Paar ``--setenv PI_CODING_AGENT_DIR
  <state>/pi/agent`` (genau einmal); der Pfad liegt unter dem Zustandsort,
  der in ``write_dirs`` geführt wird, und das Verzeichnis existiert nach
  dem Aufruf (Vorbildung).
- AK2: Enthält ``HOME`` ``.pi/agent/auth.json``, wird ausschließlich
  ``--ro-bind`` dieser Datei auf ``<state>/pi/agent/auth.json`` gebunden —
  keine beschreibende Bindung, kein weiteres Bindungsziel dafür; die
  Quelldatei bleibt unangetastet.
- AK3: Ist ``HOME`` leer (keine ``auth.json``), entsteht keine
  ``auth.json``-Bindung, der Aufruf läuft fehlerfrei durch und das
  ``PI_CODING_AGENT_DIR``-setenv bleibt erhalten.
- AK4: Ohne Sandbox (SANDBOX off) zeigt ``--print-command`` den Befehl
  plain ohne bubblewrap und ohne ``PI_CODING_AGENT_DIR``.
- AK5 (echte bwrap-Läufe): Schreiben nach
  ``$PI_CODING_AGENT_DIR/trust.json.lock`` gelingt innerhalb der Sandbox;
  die Datei liegt danach auf dem Host unter dem Zustandsort; Schreiben in
  das (fremde) ``HOME``-Verzeichnis scheitert weiterhin; außer dem
  Zustandsort des Projekts bleibt unter ``/tmp/opencode/vibe-sandbox`` und
  ``/tmp/opencode/vsb`` nichts zurück (Aufräumen des state_dir je Test mit
  addCleanup).

Sicherheitsregeln des Testpakets: Die reale ``~/.pi``-Hierarchie wird nie
verändert; alle ``HOME``-Aspekte der Tests nutzen isolierende
Tempverzeichnisse neben dem Repository (in dieser Sitzung sind ``/tmp`` und
``/var/tmp`` schreibgeschützt). Keine echten Modellaufrufe; ``pi`` selbst
wird nicht gestartet — die Grenze wird über die Umgebungsvariable und
reale Dateioperationen in der Sandbox geprüft.
"""

import hashlib
import importlib.machinery
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

# Direkte Einträge dieser beiden Wurzeln werden unmittelbar vor und nach
# den echten Läufen verglichen; das Aufräumen des state_dir muss den
# Unterschied vollständig zurücknehmen.
SANDBOX_ROOTS = ("/tmp/opencode/vibe-sandbox", "/tmp/opencode/vsb")


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def collect_setenv(argv):
    """Tabelle der --setenv-Paare eines bwrap-argv."""
    result = {}
    for first, key, value in zip(argv, argv[1:], argv[2:]):
        if first == "--setenv":
            result[key] = value
    return result


def setenv_frequencies(argv):
    """Anzahl der --setenv-Einträge je Variablen."""
    result = {}
    for first, key in zip(argv, argv[1:]):
        if first == "--setenv":
            result[key] = result.get(key, 0) + 1
    return result


def bind_triples(argv):
    """Tabelle der Bindungsdreier (Flag, Quelle, Ziel)."""
    return [
        (first, source, target)
        for first, source, target in zip(argv, argv[1:], argv[2:])
        if first in ("--bind", "--ro-bind", "--dev-bind", "--dev-bind-try")
    ]


def roots_snapshot():
    """Liste der direkten Einträge der beiden Sandbox-Zustandswurzeln."""
    items = []
    for root in SANDBOX_ROOTS:
        base = Path(root)
        if base.is_dir():
            items.extend(sorted(str(path) for path in base.iterdir()))
    return items


class B4Fixture(unittest.TestCase):
    def setUp(self):
        # Die aktuelle Agentensitzung kennt /tmp und /var/tmp als
        # schreibgeschützt; der Projektbaum wurde wie bei F16 als
        # Prüfverzeichnis im Repository belegt. Er liegt — anders als
        # /tmp/opencode — nie in einem als Schreibverzeichnis gebundenen
        # Baum, damit die Verneinungsfälle von AK5 beobachtbar bleiben.
        self.tmp = tempfile.TemporaryDirectory(prefix=".b4-", dir=str(REPO))
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_file = self.project / ".vibe" / "project.env"
        self.env_file.write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore, "HOME", old_home)
        self.bwrap = shutil.which("bwrap")
        self.sandbox = load_module(SANDBOX, "b4_vibe_sandbox_under_test")

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        self.tmp.cleanup()

    def cleanup_state_dir(self):
        """Räumt genau den state_dir(project) je Test weg (B5-Regel)."""
        path = self.sandbox.state_dir(self.project)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def expected_pi_dir(self):
        return os.path.join(self.sandbox.state_dir(self.project), "pi", "agent")

    def run_sandboxed(self, script):
        env = dict(os.environ, HOME=str(self.home), VIBE=str(self.root))
        env.pop("VIBE_SANDBOX_ROOT", None)
        return subprocess.run(
            [sys.executable, str(SANDBOX), str(self.project), "--",
             "/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )


class SetEnvTest(B4Fixture):
    """AK1: setenv-Paar und Anlage des Pi-Agentenordners im Zustandsort."""

    def test_bwrap_argv_sets_pi_agent_dir_exactly_once_under_state(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        state = self.sandbox.status(self.project)

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        setenv = collect_setenv(argv)
        pi_dir = setenv.get("PI_CODING_AGENT_DIR")
        self.assertEqual(
            pi_dir, self.expected_pi_dir(),
            "PI_CODING_AGENT_DIR zeigt nicht auf den Zustandsort/pi/agent",
        )
        # Genau ein setenv-Paar für die Variable.
        self.assertEqual(setenv_frequencies(argv).get("PI_CODING_AGENT_DIR"), 1)
        # Verzeichnis nach dem Aufruf vorhanden (Vorbildung).
        self.assertTrue(
            os.path.isdir(pi_dir), "Pi-Agentenordner fehlt nach dem Aufruf"
        )
        # Der Pfad liegt unter dem Zustandsort, der ein Schreibverzeichnis
        # des Laufs ist.
        self.assertIn(state["state_dir"], state["write_dirs"])
        self.assertTrue(pi_dir.startswith(state["state_dir"] + os.sep))

    def test_pi_agent_dir_wins_over_a_preexisting_environment_variable(self):
        """Die Umleitung ist unabhängig von einer umgebungsseits gesetzten
        Variablen (Pi-Option, nicht Nutzerwahl des Laufs)."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        old = os.environ.get("PI_CODING_AGENT_DIR")
        os.environ["PI_CODING_AGENT_DIR"] = "/nicht/der/pi-ordner"
        self.addCleanup(self._restore, "PI_CODING_AGENT_DIR", old)

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        setenv = collect_setenv(argv)
        self.assertEqual(setenv["PI_CODING_AGENT_DIR"], self.expected_pi_dir())
        self.assertTrue(os.path.isdir(self.expected_pi_dir()))


class AuthBindTest(B4Fixture):
    """AK2: auth.json nur lesend in den Pi-Agentenordner gebunden."""

    def setUp(self):
        super().setUp()
        (self.home / ".pi" / "agent").mkdir(parents=True)
        self.auth = self.home / ".pi" / "agent" / "auth.json"
        self.auth.write_text('{"marker":"pruefstand"}', encoding="utf-8")

    def test_auth_json_is_read_only_bound_into_the_pi_agent_dir(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        pi_dir = collect_setenv(argv)["PI_CODING_AGENT_DIR"]
        target = os.path.join(pi_dir, "auth.json")
        triples = [
            triple for triple in bind_triples(argv)
            if triple[1] == str(self.auth) or triple[2] == str(self.auth)
        ]
        self.assertEqual(
            len(triples), 1,
            "Mehr als eine Bindung auf auth.json: " + repr(triples),
        )
        self.assertEqual(
            triples[0],
            ("--ro-bind", str(self.auth), target),
            "auth.json muss ausschließlich lesend in den "
            "Pi-Agentenordner gebunden werden",
        )
        # Kein beschreibendes Doppel derselben Quelle.
        pairs = list(zip(argv, argv[1:]))
        self.assertNotIn(("--bind", str(self.auth)), pairs)
        # Das Ziel ist der Pi-Agentenordner, nicht der opencode-Datenort.
        self.assertEqual(os.path.dirname(target), pi_dir)
        self.assertNotEqual(
            os.path.dirname(target),
            os.path.join(
                self.sandbox.state_dir(self.project),
                "data", "opencode",
            ),
        )
        # Die Quelldatei bleibt unverändert vorhanden.
        self.assertEqual(
            self.auth.read_text(encoding="utf-8"), '{"marker":"pruefstand"}'
        )


class MissingAuthTest(B4Fixture):
    """AK3: Fehlende auth.json erzeugt keine Bindung und keinen Abbruch."""

    def test_empty_home_binds_no_auth_file_but_keeps_the_setenv(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        self.assertFalse(
            (self.home / ".pi" / "agent" / "auth.json").exists(),
            "Vorbedingung verletzt: HOME enthält auth.json",
        )

        # Der Aufruf darf nicht an der fehlenden Datei scheitern.
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        for triple in bind_triples(argv):
            for part in (triple[1], triple[2]):
                self.assertFalse(
                    part.endswith("auth.json"),
                    "unerwartete auth.json-Bindung: " + repr(triple),
                )
        # Das setenv bleibt trotzdem erhalten (Pi-Agentenordner angelegt).
        pi_dir = collect_setenv(argv)["PI_CODING_AGENT_DIR"]
        self.assertEqual(pi_dir, self.expected_pi_dir())
        self.assertTrue(os.path.isdir(pi_dir))


class DisabledSandboxTest(B4Fixture):
    """AK4: Ohne Sandbox bleibt --print-command ohne den Pi-Zusatz."""

    def test_print_command_off_shows_plain_command_without_pi_agent_dir(self):
        self.env_file.write_text("TYPE=generic\n", encoding="utf-8")
        # Auch ein vorhandenes auth.json im isolierten HOME ändert am
        # deaktivierten Verhalten nichts.
        (self.home / ".pi" / "agent").mkdir(parents=True, exist_ok=True)
        (self.home / ".pi" / "agent" / "auth.json").write_text(
            '{"marker":true}', encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(SANDBOX), str(self.project),
             "--print-command", "--", "/bin/sh", "-c", "echo probe"],
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=str(self.home), VIBE=str(self.root)),
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        # Plain-Befehl: kein bubblewrap, kein Pi-Zusatz.
        self.assertEqual(
            result.stdout.strip(),
            shlex.join(["/bin/sh", "-c", "echo probe"]),
        )
        self.assertNotIn("PI_CODING_AGENT_DIR", result.stdout + result.stderr)
        self.assertNotIn("bwrap", result.stdout)


class PiAgentDirRunTest(B4Fixture):
    """AK5: Echte bwrap-Läufe — Pi-Agentenordner schreibbar, Host sichtbar."""

    def test_pi_agent_dir_writable_state_visible_and_home_denied(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        before = roots_snapshot()
        self.cleanup_state_dir()
        pi_dir = self.expected_pi_dir()
        escape = self.home / "darf-nicht-gelingen"
        self.assertFalse(escape.exists())
        script = (
            'echo probe > "$PI_CODING_AGENT_DIR/trust.json.lock" 2>/dev/null '
            "&& echo PI_WRITE_OK || echo PI_WRITE_FAILED; "
            'if cat "$PI_CODING_AGENT_DIR/trust.json.lock" 2>/dev/null '
            "| grep -q probe; then echo PI_READBACK_OK; fi; "
            f"if echo x > {shlex.quote(str(escape))} "
            "2>/dev/null; then echo HOME_OPEN; else echo HOME_DENIED; fi"
        )

        result = self.run_sandboxed(script)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PI_WRITE_OK", result.stdout)
        self.assertNotIn("PI_WRITE_FAILED", result.stdout)
        # Die geschriebene Sperrdatei liegt auf dem Host unter dem
        # Zustandsort (kein flüchtiges tmpfs, kein EROFS-Abbruch).
        lock = Path(pi_dir) / "trust.json.lock"
        self.assertTrue(lock.is_file(), "Sperrdatei fehlt auf dem Host")
        self.assertEqual(lock.read_text(encoding="utf-8"), "probe\n")
        # Fremdes HOME bleibt gesperrt (wie vor B4).
        self.assertIn("HOME_DENIED", result.stdout)
        self.assertFalse(escape.exists())
        # Aufräumbeweis (im Testkörper, damit die leere-Wurzeln-Prüfung
        # NACH dem Entfernen des Zustandsorts sieht; addCleanup läuft LIFO
        # und hätte eine dort registrierte Assertion zu früh ausgeführt).
        # Fremde gleichzeitige Sitzungen ändern die Wurzeln unabhängig von
        # diesem Test; der Abgleich betrachtet deshalb ausschließlich
        # Einträge mit dem SHA-256-Digest dieses Projekts — beide Aussagen
        # bleiben bestehen, nichts wird abgeschwächt.
        state_path = self.sandbox.state_dir(self.project)
        digest = hashlib.sha256(
            os.path.realpath(self.project).encode("utf-8")
        ).hexdigest()[:10]

        def own_entries(paths):
            return [
                path for path in paths
                if os.path.basename(path).endswith("-" + digest)
                or os.path.basename(path) == digest
            ]

        appeared = [
            path for path in roots_snapshot()
            if path not in set(before) and own_entries([path])
        ]
        for path in appeared:
            self.assertTrue(
                path == state_path or path.startswith(state_path + os.sep),
                "Der Lauf hinterließ Einträge außerhalb des Zustandsorts: "
                + repr(path),
            )
        self.assertTrue(
            appeared,
            "Der Lauf hat unter der Sandbox-Wurzel keinen Zustandsort "
            "angelegt",
        )
        # Das standardsmäßig registrierte Aufräumen (cleanup_state_dir)
        # bleibt als Netz für früher scheiternde Assertions erhalten;
        # hier wird zusätzlich konkret aufgeräumt, damit die nachfolgende
        # Prüfung den bereinigten Stand sieht.
        shutil.rmtree(state_path, ignore_errors=True)
        remaining = own_entries(roots_snapshot())
        self.assertEqual(
            remaining, [],
            "Nach dem Aufräumen blieben Einträge unter den "
            "Sandbox-Wurzeln: " + repr(remaining),
        )


if __name__ == "__main__":
    unittest.main()
