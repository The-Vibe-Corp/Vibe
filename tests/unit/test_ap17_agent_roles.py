"""AP17 — Weitere Agentenrollen: Unit- und Backend-Tests.

Die Fälle sind aus dem Arbeitspaket AP17 und der SPEC.md abgeleitet, nicht aus
einer Implementierung. Geprüft wird:

* der Rollenkatalog enthält ``tester``, ``analyst``, ``sonstiges`` und
  ``content-creator`` neben den bestehenden Rollen,
* alle vier Rollen lassen sich globalen Agenten zuweisen und landen in
  ``profiles.json`` unter ``rollen``,
* die Agentenliste (``agents_all``) liefert die zugewiesene Rolle zurück,
* unbekannte Rollen werden abgelehnt, ohne ``profiles.json`` zu verändern,
* die bestehenden Vibe-Schutzregeln bleiben unverändert,
* der Preflight ergänzt einen fehlenden TESTER aus der Rolle ``tester`` in
  ``<state>/profiles.json`` (analog zum REVIEWER-Fallback), ein ausdrücklich
  gesetzter TESTER bleibt vorrangig, ein nicht verfügbarer Rollenagent wird
  mit Namen gemeldet und ohne Zustandsordner bleibt es beim bisherigen
  Befund ``TESTER fehlt``,
* der REVIEWER-Fallback funktioniert unverändert.

Alle Tests arbeiten in temporären VIBE-/HOME-Verzeichnissen. Es findet kein
Modellaufruf und kein Netzzugriff statt; ``models_list`` wird durch eine leere
Liste ersetzt.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
PACKAGES = BIN / "vibe_packages.py"

NEW_ROLES = ("tester", "analyst", "sonstiges", "content-creator")
EXISTING_ROLES = ("coder", "reviewer", "vibe")

AGENT_BASE = """---
description: Testagent
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""

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
            "vibe_ap17_under_test", str(CLI)
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


def load_module(path, name):
    """Lädt ein eigenständiges Modul (hier den Paketläufer)."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def agent_name(role):
    """Gültiger globaler Agentenname für eine Rolle."""
    return "agent-" + role


def project_env(tester=None, reviewer="code-reviewer"):
    """Projektdatei mit optionalem explizitem TESTER und Reviewer."""
    lines = ["TYPE=generic", "AGENT=test-agent"]
    if tester is not None:
        lines.append("TESTER=" + tester)
    if reviewer is not None:
        lines.append("REVIEWER=" + reviewer)
    lines.append('VERIFY_PACKAGE="true"')
    return "\n".join(lines) + "\n"


class RoleCatalogTest(unittest.TestCase):
    """Rollenkatalog und Zuweisung über die Agentenverwaltung (AK 1 und 2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli = load_cli(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def write_global(self, name, text=AGENT_BASE):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def profiles_path(self):
        return Path(self.root) / "_toolchain" / "profiles.json"

    def roles_on_disk(self):
        return json.loads(self.profiles_path().read_text(encoding="utf-8"))[
            "rollen"
        ]

    def test_role_catalog_contains_existing_and_new_roles(self):
        """Name: Rollenkatalog enthält alle vereinbarten Rollen.

        Vorbedingung: bin/vibe ist mit isoliertem Zustandsordner geladen.
        Aktion: ``ROLE_NAMES`` wird gelesen.
        Erwartetes Ergebnis: coder, reviewer und vibe bleiben enthalten;
        zusätzlich sind tester, analyst, sonstiges und content-creator
        vorhanden. Weitere Rollen gibt es nicht.
        """
        roles = tuple(self.cli.ROLE_NAMES)

        self.assertEqual(
            set(roles), set(EXISTING_ROLES) | set(NEW_ROLES), roles
        )

    def test_all_new_roles_can_be_assigned_and_are_saved_in_profiles_json(self):
        """Name: Alle vier neuen Rollen werden gespeichert.

        Vorbedingung: Für jede neue Rolle existiert ein globaler Agent.
        Aktion: ``agent_role_set`` wird für tester, analyst, sonstiges und
        content-creator aufgerufen.
        Erwartetes Ergebnis: Jede Rolle ist im Rückgabewert und in
        ``profiles.json`` unter ``rollen`` gespeichert.
        """
        for role in NEW_ROLES:
            self.write_global(agent_name(role))

        for role in NEW_ROLES:
            returned = self.cli.agent_role_set(agent_name(role), role)
            self.assertEqual(returned[agent_name(role)], role)

        stored = self.roles_on_disk()
        for role in NEW_ROLES:
            self.assertEqual(stored.get(agent_name(role)), role)

    def test_new_roles_are_visible_in_the_agent_list(self):
        """Name: Agentenliste zeigt die neuen Rollen.

        Vorbedingung: Vier globale Agenten tragen je eine neue Rolle.
        Aktion: ``agents_all`` wird ausgewertet.
        Erwartetes Ergebnis: Jede globale Agentenzeile liefert ihre
        zugewiesene Rolle; die Rollen sind damit in der Agentenliste sichtbar.
        """
        for role in NEW_ROLES:
            self.write_global(agent_name(role))
            self.cli.agent_role_set(agent_name(role), role)

        rows = {
            row["name"]: row
            for row in self.cli.agents_all()
            if row["scope"] == "global"
        }

        for role in NEW_ROLES:
            self.assertEqual(rows[agent_name(role)]["role"], role)

    def test_unknown_role_is_rejected_without_changing_profiles_json(self):
        """Name: Unbekannte Rolle wird abgelehnt, Datei bleibt unverändert.

        Vorbedingung: Ein globaler Agent hat die Rolle coder; profiles.json
        liegt vor.
        Aktion: ``agent_role_set`` wird mit unbekannten Rollen aufgerufen.
        Erwartetes Ergebnis: ``ValueError``; profiles.json und die
        Agentendatei bleiben bytegleich.
        """
        name = "tester"
        path = self.write_global(name)
        self.set_roles({name: "coder"})
        before_profiles = self.profiles_path().read_bytes()
        before_agent = path.read_bytes()

        for unknown in ("supervisor", "Tester", "content_creator", "vibe-agent"):
            with self.subTest(role=unknown):
                with self.assertRaises(ValueError):
                    self.cli.agent_role_set(name, unknown)
                self.assertEqual(
                    self.profiles_path().read_bytes(), before_profiles
                )
                self.assertEqual(path.read_bytes(), before_agent)

    def test_new_roles_do_not_change_the_vibe_protection_rules(self):
        """Name: Vibe-Schutzregeln gelten unverändert.

        Vorbedingung: Ein Agent trägt vibe, ein zweiter ist vorhanden.
        Aktion: Dem zweiten wird eine neue Rolle zugewiesen; anschließend wird
        versucht, dem letzten Vibe-Agenten die Rolle zu entziehen.
        Erwartetes Ergebnis: Die neue Rolle stört den Vibe-Agenten nicht.
        Entfernen oder Umwidmen des letzten Vibe-Agenten bleibt verboten;
        genau ein Agent trägt weiterhin vibe.
        """
        self.write_global("vibe-agent", VIBE_AGENT)
        self.write_global("second")
        self.cli.agent_role_set("vibe-agent", "vibe")

        self.cli.agent_role_set("second", "analyst")

        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(roles.get("second"), "analyst")
        self.assertEqual(
            [name for name, role in roles.items() if role == "vibe"],
            ["vibe-agent"],
        )

        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "tester")
        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "")

        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(roles.get("vibe-agent"), "vibe")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        # Umsetzen bleibt durch gleichzeitige Zuweisung möglich; danach trägt
        # weiterhin genau ein Agent die Rolle vibe.
        self.cli.agent_role_set("second", "vibe")
        roles = self.cli.profiles_load()["rollen"]
        self.assertEqual(
            [name for name, role in roles.items() if role == "vibe"], ["second"]
        )
        self.assertEqual(self.cli.vibe_agent_name(), "second")


class PreflightFixture(unittest.TestCase):
    """Temporäres Git-Projekt mit Agentenordner und Zustandsordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.git("init", "-q", "-b", "main", str(self.project), cwd=self.root)
        self.agents = self.root / "agents"
        self.agents.mkdir()
        for name in ("test-agent", "code-reviewer", "fallback-tester"):
            (self.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n",
                encoding="utf-8",
            )
        self.write_project(project_env())
        self.state = self.root / "state"
        self.state.mkdir()
        self.write_profiles(
            {"fallback-tester": "tester", "code-reviewer": "reviewer"}
        )
        self.commit_all("Ausgangsstand")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.project),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
        return result

    def write_project(self, env_text):
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            env_text, encoding="utf-8"
        )

    def commit_all(self, message):
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def write_profiles(self, rollen):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": rollen}), encoding="utf-8"
        )


class TesterRolePreflightTest(PreflightFixture):
    """Preflight: TESTER-Fallback über die Rolle ``tester`` (AK 4)."""

    def setUp(self):
        super().setUp()
        self.module = load_module(PACKAGES, "vibe_packages_ap17_preflight")

    def errors(self, tester="", reviewer="code-reviewer", state_dir="__default__"):
        if state_dir == "__default__":
            state_dir = self.state
        return self.module.preflight_errors(
            str(self.project),
            agents_dir=str(self.agents),
            tester=tester,
            reviewer=reviewer,
            state_dir=str(state_dir) if state_dir else state_dir,
        )

    def test_missing_tester_is_resolved_from_tester_role(self):
        """Name: Fehlender TESTER wird aus der Rolle tester ergänzt.

        Vorbedingung: project.env enthält keinen TESTER; profiles.json enthält
        die Rolle tester für einen verfügbaren Agenten.
        Aktion: ``preflight_errors`` wird mit leerem tester und Zustandsordner
        aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der Rollenagent übernimmt TESTER.
        """
        self.assertNotIn(
            "TESTER", (self.project / ".vibe" / "project.env").read_text(
                encoding="utf-8"
            )
        )

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_project_local_agent_file_satisfies_the_tester_role(self):
        """Name: Projektlokaler Agent erfüllt die Tester-Rolle.

        Vorbedingung: Die globale Datei des Rollenagenten fehlt; dieselbe
        Agentendatei liegt im Projektordner.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; auch der Projektordner ist ein
        gültiger Agentenort.
        """
        (self.agents / "fallback-tester.md").unlink()
        local = self.project / ".opencode" / "agents"
        local.mkdir(parents=True)
        (local / "fallback-tester.md").write_text(
            "---\ndescription: lokaler Tester\nmode: subagent\n---\n",
            encoding="utf-8",
        )
        self.commit_all("lokaler Tester")

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_stale_tester_role_entry_does_not_block_available_agent(self):
        """Name: Veralteter Rolleneintrag blockiert verfügbaren Tester nicht.

        Vorbedingung: profiles.json nennt zuerst einen nicht vorhandenen
        Agenten und danach einen verfügbaren Agenten mit Rolle tester.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der verfügbare Rollenagent wird
        gewählt (analog zum REVIEWER-Fallback).
        """
        self.write_profiles(
            {
                "veralteter-tester": "tester",
                "fallback-tester": "tester",
                "code-reviewer": "reviewer",
            }
        )

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_unavailable_tester_role_is_reported_with_its_name(self):
        """Name: Nicht verfügbarer Rollen-Tester wird mit Namen gemeldet.

        Vorbedingung: profiles.json enthält die Rolle tester für einen Agenten,
        dessen Datei weder global noch im Projekt liegt.
        Aktion: ``preflight_errors`` wird ohne expliziten TESTER aufgerufen.
        Erwartetes Ergebnis: Ein TESTER-Befund nennt den Namen
        ``veralteter-tester`` und meldet die fehlende Agentendatei.
        """
        self.write_profiles(
            {"veralteter-tester": "tester", "code-reviewer": "reviewer"}
        )

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("veralteter-tester" in error for error in errors), errors
        )
        self.assertTrue(
            any("nicht verfügbar" in error for error in errors), errors
        )

    def test_explicit_tester_argument_wins_over_the_tester_role(self):
        """Name: Ausdrücklicher TESTER hat Vorrang vor der Rolle.

        Vorbedingung: Die Rolle tester zeigt auf einen nicht vorhandenen
        Agenten; der als Argument übergebene Agent ist verfügbar.
        Aktion: ``preflight_errors`` wird mit ``tester="test-agent"``
        aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der ausdrückliche TESTER wird
        verwendet und nicht durch die Rolle ersetzt.
        """
        self.write_profiles(
            {"veralteter-tester": "tester", "code-reviewer": "reviewer"}
        )

        errors = self.errors(tester="test-agent")

        self.assertEqual(errors, [])

    def test_unavailable_explicit_tester_blocks_despite_a_valid_role(self):
        """Name: Nicht verfügbarer ausdrücklicher TESTER blockiert.

        Vorbedingung: Die Rolle tester zeigt auf einen verfügbaren Agenten.
        Aktion: ``preflight_errors`` wird mit einem nicht vorhandenen
        ausdrücklichen TESTER aufgerufen.
        Erwartetes Ergebnis: Ein TESTER-Befund nennt den ausdrücklichen Namen;
        die Rolle ersetzt ihn nicht.
        """
        errors = self.errors(tester="nicht-vorhanden")

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    def test_project_env_tester_wins_over_the_tester_role(self):
        """Name: TESTER aus project.env hat Vorrang vor der Rolle.

        Vorbedingung: Die Rolle tester zeigt auf einen verfügbaren Agenten;
        project.env setzt ausdrücklich einen nicht vorhandenen TESTER.
        Aktion: ``preflight_errors`` wird ohne Argument aufgerufen.
        Erwartetes Ergebnis: Der Befund nennt den Wert aus project.env; die
        Rolle wird nicht als Ersatz verwendet.
        """
        self.write_project(project_env(tester="nicht-vorhanden"))
        self.commit_all("expliziter TESTER")

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    def test_without_state_directory_missing_tester_still_blocks(self):
        """Name: Ohne Zustandsordner bleibt der Befund TESTER fehlt.

        Vorbedingung: project.env enthält keinen TESTER.
        Aktion: ``preflight_errors`` wird ohne Zustandsordner aufgerufen.
        Erwartetes Ergebnis: Der bisherige Befund ``TESTER fehlt`` bleibt
        bestehen; es wird keine Rolle erfunden.
        """
        errors = self.errors(state_dir=None)

        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

    def test_missing_or_broken_profiles_file_blocks_with_tester_message(self):
        """Name: Fehlende oder kaputte profiles.json blockiert ohne Absturz.

        Vorbedingung: project.env enthält keinen TESTER.
        Aktion: profiles.json wird entfernt bzw. mit ungültigem JSON gefüllt
        und ``preflight_errors`` erneut aufgerufen.
        Erwartetes Ergebnis: Jeweils der Befund ``TESTER fehlt``; kein
        Absturz.
        """
        (self.state / "profiles.json").unlink()
        errors = self.errors()
        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

        (self.state / "profiles.json").write_text(
            "{kein gültiges JSON", encoding="utf-8"
        )
        errors = self.errors()
        self.assertTrue(
            any("TESTER fehlt" in error for error in errors), errors
        )

    def test_reviewer_fallback_still_resolves_from_profiles_json(self):
        """Name: REVIEWER-Fallback bleibt unverändert.

        Vorbedingung: project.env enthält einen verfügbaren TESTER, aber
        keinen REVIEWER; profiles.json enthält die Rolle reviewer.
        Aktion: ``preflight_errors`` wird aufgerufen.
        Erwartetes Ergebnis: Keine Befunde; der Reviewer wird weiterhin aus
        der Rolle reviewer ergänzt.
        """
        self.write_project(project_env(tester="test-agent", reviewer=None))
        self.commit_all("ohne REVIEWER")

        errors = self.errors(reviewer="")

        self.assertEqual(errors, [])


class TesterRoleCliTest(PreflightFixture):
    """CLI ``preflight --state`` löst den TESTER aus der Rolle auf (AK 4)."""

    def run_preflight(self, *state_args):
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGES),
                "preflight",
                "--project",
                str(self.project),
                "--agents-dir",
                str(self.agents),
                *state_args,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_preflight_resolves_tester_from_state_directory(self):
        """Name: CLI-Preflight löst TESTER über --state auf.

        Vorbedingung: project.env ohne TESTER; profiles.json im Zustandsordner
        enthält die Rolle tester für einen verfügbaren Agenten.
        Aktion: ``preflight --state <ordner>`` wird ausgeführt.
        Erwartetes Ergebnis: Rückgabewert 0 und keine BLOCKIERT-Meldung.
        """
        result = self.run_preflight("--state", str(self.state))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BLOCKIERT", result.stdout, result.stdout)

    def test_cli_preflight_without_state_still_blocks_missing_tester(self):
        """Name: CLI-Preflight ohne --state meldet TESTER fehlt.

        Vorbedingung: project.env ohne TESTER; ein Zustandsordner wird nicht
        übergeben.
        Aktion: ``preflight`` wird ohne ``--state`` ausgeführt.
        Erwartetes Ergebnis: Rückgabewert 2 und eine TESTER-Meldung.
        """
        result = self.run_preflight()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("TESTER", result.stdout)


if __name__ == "__main__":
    unittest.main()
