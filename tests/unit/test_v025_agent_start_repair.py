"""V-025 — Ungültigen Startagenten aus der Projektauswahl beheben.

Die Fälle sind aus TICKETS.md (V-025), SPEC.md und AGENTS.md abgeleitet und
nicht aus dem Implementierungsdiff. Geprüft wird ausschließlich das
beobachtbare Verhalten von ``cmd_run``:

* ein in ``.vibe/project.env`` gespeicherter ``AGENT``, der global nicht
  existiert, wird durch den gültigen, aktiven Vibe-Agenten ersetzt,
* ein global vorhandener, im Projekt aber nicht aktiver ``AGENT`` wird
  ebenfalls ersetzt,
* ein gültiger, aktiver ``AGENT`` bleibt unverändert,
* ein ausdrücklich per CLI übergebener, nicht aktiver Agent wird weiterhin
  abgelehnt und ändert die Projektdatei nicht,
* ein Schreibfehler bei der Korrektur verhindert den Start mit dem
  Vibe-Agenten nicht und wird gemeldet,
* die Ausgabe nennt den veralteten und den ersetzenden Agenten,
* mitgelieferte Projektvorlagen enthalten keinen fest eingebauten
  ``AGENT``-Namen.

Testfälle (Name, Vorbedingung, Aktion, erwartetes Ergebnis):

=========================================  =====================================
``test_missing_agent_falls_back_to_vibe``   AK1. ``AGENT=alter-agent`` ohne
                                          globale Datei; Vibe-Agent aktiv.
                                          ``cmd_run`` startet mit
                                          ``vibe-agent``; ``AGENT`` wird
                                          ersetzt, alle anderen Zeilen
                                          bleiben zeichengleich.
``test_repair_message_names_old_and_new``   AK6. Wie AK1. Die Ausgabe nennt
                                          ``alter-agent`` und ``vibe-agent``.
``test_global_but_inactive_agent_is_``      AK2. ``AGENT=tester`` existiert
``repaired``                              global, fehlt aber in
                                          ``.vibe/agents.json``; Vibe-Agent
                                          aktiv. Start mit ``vibe-agent`` und
                                          Korrektur der Projektdatei.
``test_active_agent_is_used_unchanged``     AK3. ``AGENT=tester`` global und
                                          im Projekt aktiv. Start mit
                                          ``tester``; Projektdatei
                                          bytegleich unverändert.
``test_explicit_inactive_agent_is_``        AK4. ``cmd_run(..., "tester")``
``rejected_without_writing``              mit nicht aktivem ``tester``.
                                          ``SystemExit``, kein Start,
                                          Projektdatei unverändert.
``test_write_error_still_starts_with_``     AK5. Schreibzugriff auf
``vibe_and_reports_error``                ``.vibe/project.env`` schlägt fehl.
                                          Start trotzdem mit ``vibe-agent``;
                                          Fehler wird ausgegeben; Datei
                                          bleibt unverändert.
``test_shipped_project_templates_``         AK Vorlagen. Alle Dateien
``contain_no_agent_entry``                ``templates/*/.vibe/project.env``
                                          enthalten keine wirksame
                                          ``AGENT=``-Zeile; neue Projekte
                                          starten ohne Korrektur mit dem
                                          Vibe-Agenten.
``test_repair_preserves_crlf_line_``        Format. Projektdatei mit CRLF
``endings``                               und veraltetem ``AGENT``; nur die
                                          AGENT-Zeile ändert sich, CRLF
                                          bleibt erhalten.
``test_quoted_agent_value_is_replaced``      Format. ``AGENT="alter-agent"``
                                          wird durch ``AGENT=vibe-agent``
                                          ersetzt, übrige Zeilen bleiben.
``test_repair_rejects_invalid_agent_``       Sicherheit. ``repair_project_agent``
``names``                                 darf Namen außerhalb von
                                          ``NAME_RE`` nicht schreiben und
                                          meldet einen Fehler; Datei bleibt
                                          unverändert.
=========================================  =====================================

Es findet kein Modellaufruf, kein tmux-Start und kein Netzzugriff statt.
``run``, ``tmux_has``, ``is_init``, ``sandbox_status``, ``run_registry`` und
``ensure_opencode_password`` sind Attrappen; alle Dateien liegen in einem
temporären VIBE-/HOME-Verzeichnis.
"""
import builtins
import contextlib
import errno
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

GLOBAL_AGENT = """---
description: Global vorhandener Agent
mode: subagent
model: opencode/global-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

# Ausgangsdatei für AK1: AGENT zeigt auf einen nicht mehr vorhandenen Agenten.
MISSING_AGENT_ENV = (
    "TYPE=generic\n"
    "AGENT=alter-agent\n"
    "TESTER=test-agent\n"
    'VERIFY_QUICK="true"\n'
)

# Ausgangsdatei für AK2/AK3: AGENT zeigt auf einen global vorhandenen Agenten.
GLOBAL_AGENT_ENV = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    'VERIFY_QUICK="true"\n'
)

# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "AGENT",
    "MAX_PACKAGES",
)


def isolated_env(root, home):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_v025_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


@contextlib.contextmanager
def failing_writes(path):
    """Simuliert ein Dateisystem, das Schreibzugriffe auf ``path`` verweigert.

    Der Test kennt die spätere Implementierung nicht und blockiert deshalb
    alle üblichen Schreibwege: direkte ``open``-Aufrufe (auch über ``io.open``
    und ``pathlib``), ``os.open`` mit Schreibflags sowie die atomare
    Ersetzung per ``os.replace``/``os.rename``. Lesen bleibt möglich.
    """
    target = os.path.realpath(os.fspath(path))
    real_builtin_open = builtins.open
    real_io_open = io.open
    real_replace = os.replace
    real_rename = os.rename
    real_os_open = os.open

    def is_target(candidate):
        try:
            return os.path.realpath(os.fspath(candidate)) == target
        except TypeError:
            return False

    def refuse(action):
        return OSError(
            errno.EACCES,
            f"{action} verweigert (Testfall V-025)",
            str(path),
        )

    def guarded_open(file, mode="r", *args, **kwargs):
        if is_target(file) and any(flag in mode for flag in "wax+"):
            raise refuse("Schreiben")
        return real_builtin_open(file, mode, *args, **kwargs)

    def guarded_io_open(file, mode="r", *args, **kwargs):
        if is_target(file) and any(flag in mode for flag in "wax+"):
            raise refuse("Schreiben")
        return real_io_open(file, mode, *args, **kwargs)

    def guarded_replace(src, dst, *args, **kwargs):
        if is_target(dst):
            raise refuse("Ersetzen")
        return real_replace(src, dst, *args, **kwargs)

    def guarded_rename(src, dst, *args, **kwargs):
        if is_target(dst):
            raise refuse("Umbenennen")
        return real_rename(src, dst, *args, **kwargs)

    def guarded_os_open(file, flags, *args, **kwargs):
        write_flags = (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        if is_target(file) and flags & write_flags:
            raise refuse("Schreiben")
        return real_os_open(file, flags, *args, **kwargs)

    with mock.patch("builtins.open", guarded_open):
        with mock.patch("io.open", guarded_io_open):
            with mock.patch("os.replace", guarded_replace):
                with mock.patch("os.rename", guarded_rename):
                    with mock.patch("os.open", guarded_os_open):
                        yield


class AgentStartRepairFixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt, Agentenordner und Rollen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.cli = load_cli(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            MISSING_AGENT_ENV, encoding="utf-8"
        )
        return project

    # ---------- Aufbau ----------

    def write_global(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_vibe(self):
        """Legt den globalen Vibe-Agenten samt Rolle ``vibe`` an."""
        path = self.write_global("vibe-agent", VIBE_AGENT)
        data = self.cli.profiles_load()
        data["rollen"] = dict(data.get("rollen", {}))
        data["rollen"]["vibe-agent"] = "vibe"
        self.cli.profiles_save(data)
        return path

    def write_active_agents(self, names):
        """Schreibt die Projektauswahl (Version 2) mit genau diesen Agenten."""
        path = self.project / ".vibe" / "agents.json"
        path.write_text(
            json.dumps(
                {"version": 2, "aktiv": list(names), "modelle": {}},
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def set_project_env(self, text):
        (self.project / ".vibe" / "project.env").write_text(
            text, encoding="utf-8"
        )

    def set_project_env_bytes(self, data):
        (self.project / ".vibe" / "project.env").write_bytes(data)

    def project_env_text(self):
        return (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8"
        )

    def project_env_bytes(self):
        return (self.project / ".vibe" / "project.env").read_bytes()

    # ---------- Ausführung ----------

    def run_cmd(self, agent=None, write_error=None):
        """Ruft ``cmd_run`` mit allen externen Grenzen als Attrappen auf.

        Liefert die Aufrufe von ``run`` (tmux) und die gesammelte Ausgabe aus
        ``out`` und ``stderr``. ``write_error`` aktiviert die
        Schreibfehlersimulation für ``.vibe/project.env``.
        """
        calls = []
        out = io.StringIO()
        err = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(self.cli, "tmux_has", return_value=False))
        stack.enter_context(mock.patch.object(self.cli, "is_init", return_value=True))
        stack.enter_context(
            mock.patch.object(
                self.cli, "sandbox_status", return_value={"enabled": False}
            )
        )
        stack.enter_context(
            mock.patch.object(self.cli, "changed_file", return_value=False)
        )
        stack.enter_context(
            mock.patch.object(
                self.cli, "ensure_opencode_password", return_value=""
            )
        )
        stack.enter_context(
            mock.patch.object(self.cli, "run_registry", return_value=mock.MagicMock())
        )
        stack.enter_context(
            mock.patch.object(self.cli.vibe_runs, "rotate_log")
        )
        stack.enter_context(
            mock.patch.object(
                self.cli,
                "run",
                side_effect=lambda argv, **kwargs: calls.append(argv) or (0, ""),
            )
        )
        if write_error is not None:
            stack.enter_context(failing_writes(write_error))
        with contextlib.redirect_stderr(err):
            self.cli.cmd_run("proj", agent, out=out)
        return calls, out.getvalue() + err.getvalue()

    def assert_started_with(self, calls, agent):
        self.assertEqual(len(calls), 1, "cmd_run hat keinen Start ausgelöst")
        # Der Agent ist das vorletzte Argument; das letzte ist die (leere)
        # Modellüberschreibung des Projekts.
        self.assertEqual(calls[0][-2], agent)


class RepairTest(AgentStartRepairFixture):
    """AK1, AK2, AK6: veralteten Projektagenten erkennen und ersetzen."""

    def test_missing_agent_falls_back_to_vibe_and_repairs_project_env(self):
        """AK1: ``AGENT`` existiert global nicht; Start mit dem Vibe-Agenten."""
        self.write_vibe()

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n',
        )

    def test_global_but_inactive_agent_is_repaired(self):
        """AK2: ``AGENT`` existiert global, ist aber im Projekt nicht aktiv."""
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT)
        self.write_active_agents(["vibe-agent"])
        self.set_project_env(GLOBAL_AGENT_ENV)

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n',
        )

    def test_repair_message_names_old_and_new_agent(self):
        """AK6: Die Ausgabe macht den veralteten und den neuen Agenten sichtbar."""
        self.write_vibe()

        _calls, output = self.run_cmd()

        self.assertIn("alter-agent", output)
        self.assertIn("vibe-agent", output)

    def test_repair_preserves_other_lines_verbatim(self):
        """AK1: Nur die ``AGENT``-Zeile ändert sich, alles andere bleibt."""
        self.write_vibe()
        original = (
            "# Kopfkommentar\n"
            "TYPE=generic\n"
            "AGENT=alter-agent\n"
            "MODEL_OVERRIDE=opencode/bleibt\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n'
        )
        self.set_project_env(original)

        _calls, _output = self.run_cmd()

        self.assertEqual(
            self.project_env_text(),
            original.replace("AGENT=alter-agent", "AGENT=vibe-agent"),
        )


class StableSelectionTest(AgentStartRepairFixture):
    """AK3: gültiger, aktiver Agent bleibt unangetastet."""

    def test_active_agent_is_used_and_env_stays_unchanged(self):
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT)
        self.write_active_agents(["vibe-agent", "tester"])
        self.set_project_env(GLOBAL_AGENT_ENV)
        before = self.project_env_text()

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "tester")
        self.assertEqual(self.project_env_text(), before)


class ExplicitAgentTest(AgentStartRepairFixture):
    """AK4: ein ausdrücklich übergebener Agent wird nicht still ersetzt."""

    def test_explicit_inactive_agent_is_rejected_without_writing(self):
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT)
        self.write_active_agents(["vibe-agent"])
        self.set_project_env(GLOBAL_AGENT_ENV)
        before = self.project_env_text()

        with self.assertRaises(SystemExit) as caught:
            self.run_cmd(agent="tester")

        message = str(caught.exception.code).lower()
        self.assertIn("tester", message)
        self.assertIn("nicht", message)
        # Die Projektdatei darf durch die Ablehnung nicht verändert werden.
        self.assertEqual(self.project_env_text(), before)


class WriteErrorTest(AgentStartRepairFixture):
    """AK5: ein Schreibfehler bei der Korrektur bricht den Start nicht ab."""

    def test_write_error_still_starts_with_vibe_and_reports_error(self):
        self.write_vibe()
        before = self.project_env_text()

        calls, output = self.run_cmd(
            write_error=self.project / ".vibe" / "project.env"
        )

        self.assert_started_with(calls, "vibe-agent")
        # Der fehlgeschlagene Schreibvorgang hinterlässt die alte Zeile.
        self.assertEqual(self.project_env_text(), before)
        self.assertTrue(output.strip(), "Der Schreibfehler wurde nicht gemeldet")
        lowered = output.lower()
        self.assertTrue(
            any(hint in lowered for hint in ("konnte", "nicht", "fehl", "schreib")),
            "Die Ausgabe enthält keinen Hinweis auf den Schreibfehler: "
            + output,
        )


class RepairFormatTest(AgentStartRepairFixture):
    """Formaterhalt: Zeilenenden und gequotete Werte bei der Korrektur."""

    def test_repair_preserves_crlf_line_endings(self):
        """Eine CRLF-Projektdatei behält CRLF; nur die AGENT-Zeile ändert sich."""
        self.write_vibe()
        self.set_project_env_bytes(
            b"TYPE=generic\r\n"
            b"AGENT=alter-agent\r\n"
            b"TESTER=test-agent\r\n"
            b'VERIFY_QUICK="true"\r\n'
        )

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_bytes(),
            b"TYPE=generic\r\n"
            b"AGENT=vibe-agent\r\n"
            b"TESTER=test-agent\r\n"
            b'VERIFY_QUICK="true"\r\n',
        )

    def test_quoted_agent_value_is_replaced(self):
        """Ein gequoteter AGENT-Wert wird vollständig durch den Vibe-Agenten ersetzt."""
        self.write_vibe()
        self.set_project_env(
            "TYPE=generic\n"
            'AGENT="alter-agent"\n'
            "TESTER=test-agent\n"
        )

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n",
        )


class RepairHelperGuardTest(AgentStartRepairFixture):
    """Sicherheitsgrenze: die Reparatur schreibt keinen ungültigen Agentennamen."""

    def test_repair_rejects_invalid_agent_names(self):
        """Namen außerhalb von ``NAME_RE`` lösen einen Fehler aus, ohne zu schreiben.

        ``NAME_RE`` erlaubt nur ``^[a-z0-9][a-z0-9_-]*$``; Leerzeichen und
        Shellzeichen dürfen nie in die Projektdatei gelangen.
        """
        self.write_vibe()
        before = self.project_env_bytes()

        for invalid in ("mit leerzeichen", "boese;rm -rf /"):
            with self.subTest(agent=invalid):
                with self.assertRaises((ValueError, SystemExit)) as caught:
                    self.cli.repair_project_agent("proj", invalid)

                message = str(caught.exception).strip()
                self.assertTrue(
                    message, "Der ungültige Agentenname wurde nicht gemeldet"
                )
                self.assertTrue(
                    any(
                        hint in message.lower()
                        for hint in ("agent", "name", "ungültig")
                    ),
                    "Die Meldung benennt den Agentennamen nicht: " + message,
                )
                self.assertEqual(
                    self.project_env_bytes(),
                    before,
                    "Die Projektdatei wurde trotz ungültigem Agentennamen geschrieben",
                )


class TemplateDefaultsTest(unittest.TestCase):
    """Vorlagen-AK: kein fest eingebauter ``AGENT`` in mitgelieferten Projekten."""

    def test_shipped_project_templates_contain_no_agent_entry(self):
        """Jede ``templates/*/.vibe/project.env`` ist frei von ``AGENT=``.

        Geprüft wird die wirksame Zuweisung: Kommentarzeilen zählen nicht,
        weil sie beim Anlegen eines Projekts keine Wirkung entfalten. Fehlt
        jede Vorlage, ist der Test nicht erfüllt, statt leer zu bestehen.
        """
        paths = sorted((REPO / "templates").glob("*/.vibe/project.env"))
        self.assertTrue(
            paths,
            "Keine Projektvorlagen unter templates/*/.vibe/project.env gefunden",
        )
        findings = []
        for path in paths:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if re.match(r"^AGENT\s*=", stripped):
                    findings.append(
                        f"{path.relative_to(REPO)}:{number}: {line}"
                    )
        self.assertEqual(
            findings,
            [],
            "Mitgelieferte Vorlagen mit fest eingebautem AGENT:\n"
            + "\n".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
