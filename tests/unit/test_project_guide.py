"""Tests für den Projektassistenten (F9).

Der Assistent führt durch das fachliche Setup eines Projekts. Er erzeugt die
fachlichen Dateien (SPEC.md, TICKETS.md, AGENTS.md, FEEDBACK.md,
.vibe/project.env, README.md), ohne vorhandene Inhalte still zu überschreiben.
Fehlende Angaben kann ein Agent als Entwurf ergänzen; der Entwurf wird erst
nach ausdrücklicher Bestätigung übernommen.

Geprüft wird auf echten Dateien in temporären Verzeichnissen. Die API-Tests
starten bin/vibe-web.py auf einem eigenen Port. Es werden keine echten
Modellaufrufe ausgeführt.
"""
import importlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.unit import env_support
from tests.unit.web_page import served_page

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
WEB = BIN / "vibe-web.py"

sys.path.insert(0, str(BIN))
guide = importlib.import_module("vibe_guide")
sandbox = importlib.import_module("vibe_sandbox")


def make_project(root, name="proj", env="TYPE=generic\nAGENT=test-agent\n"):
    project = Path(root) / name
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(env, encoding="utf-8")
    return project


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ProjectGuideModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self):
        return (self.project / "SPEC.md").read_text(encoding="utf-8")

    def answers(self, **overrides):
        values = {
            "ziel": "Eine lokale Entwicklungszentrale für KI-Projekte.",
            "nutzer": "Entwicklerinnen und Entwickler am Arbeitsplatz.",
            "umfang": "- Projekte verwalten\n- Agenten starten",
            "nicht_umfang": "- Öffentlicher Remotezugriff",
            "umgebung": "Linux, Distrobox-Container, Python 3",
            "qualitaet": "Automatisierte Tests und ein dokumentierter Review.",
        }
        values.update(overrides)
        return values

    # ---------- Zustand lesen ----------

    def test_state_reports_missing_spec_and_files(self):
        state = guide.state(self.project, name="proj")

        self.assertEqual(state["name"], "proj")
        self.assertFalse(state["complete"])
        self.assertEqual(state["next"], "ziel")
        self.assertEqual(state["filled"], 0)
        self.assertGreaterEqual(state["total"], 1)
        self.assertIn("SPEC.md", state["missing_files"])
        self.assertIn("TICKETS.md", state["missing_files"])
        self.assertIn(".vibe/project.env", {
            entry["path"] for entry in state["files"] if entry["exists"]
        })
        statuses = {step["id"]: step["status"] for step in state["steps"]}
        self.assertEqual(statuses["ziel"], "fehlt")

    def test_state_reads_filled_sections_and_reports_completion(self):
        self.project.joinpath("SPEC.md").write_text(
            "# proj\n\n## Product goal\n\nEin fertiges Ziel.\n\n"
            "## Functional scope\n\n- Eine Funktion\n\n"
            "## Target environment\n\nLinux\n",
            encoding="utf-8",
        )
        for name in ("TICKETS.md", "AGENTS.md", "FEEDBACK.md", "README.md"):
            self.project.joinpath(name).write_text("Inhalt\n", encoding="utf-8")

        state = guide.state(self.project, name="proj")

        statuses = {step["id"]: step["status"] for step in state["steps"]}
        self.assertEqual(statuses["ziel"], "gefüllt")
        self.assertEqual(statuses["umfang"], "gefüllt")
        self.assertEqual(statuses["umgebung"], "gefüllt")
        self.assertEqual(statuses["nutzer"], "offen")
        self.assertEqual(state["next"], "nutzer")
        self.assertFalse(state["complete"])

    # ---------- Dateien anlegen und Abschnitte schreiben ----------

    def test_apply_creates_spec_and_all_missing_fachliche_files(self):
        result = guide.apply(
            self.project,
            self.answers(),
            name="proj",
            templates_dir=REPO / "templates",
        )

        self.assertTrue(result["state"]["complete"],
                        "Assistent meldet trotz vollständiger Angaben keine Vollständigkeit")
        for name in ("SPEC.md", "TICKETS.md", "AGENTS.md", "FEEDBACK.md",
                     ".vibe/project.env", "README.md"):
            self.assertTrue(self.project.joinpath(name).is_file(), name + " fehlt")
        text = self.spec()
        for heading in ("Product goal", "Audience and use", "Functional scope",
                        "Out of scope", "Target environment",
                        "Quality and acceptance", "Locked decisions",
                        "Open questions"):
            self.assertIn("## " + heading, text)
        for heading in ("Produktziel", "Zielgruppe und Nutzung",
                        "Funktionsumfang", "Nicht im Umfang", "Zielumgebung",
                        "Qualität und Abnahme", "Decisions Locked",
                        "Offene Fragen"):
            self.assertNotIn("## " + heading, text)
        self.assertIn("Eine lokale Entwicklungszentrale für KI-Projekte.", text)
        env = self.project.joinpath(".vibe", "project.env").read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", env)
        tickets = self.project.joinpath("TICKETS.md").read_text(encoding="utf-8")
        self.assertNotIn("{{NAME}}", tickets)
        self.assertIn("proj", tickets)
        self.assertIn("Projektassistent", result["message"])

    def test_new_spec_uses_exactly_the_eight_english_section_headings(self):
        guide.apply(self.project, self.answers(), name="proj")

        headings = re.findall(r"(?m)^##[ \t]+(.+?)[ \t]*$", self.spec())

        self.assertEqual(
            [
                "Product goal",
                "Audience and use",
                "Functional scope",
                "Out of scope",
                "Target environment",
                "Quality and acceptance",
                "Locked decisions",
                "Open questions",
            ],
            headings,
        )

    def test_state_pulls_sections_from_english_spec_headings(self):
        (self.project / "SPEC.md").write_text(
            "# proj — Produktspezifikation\n\n"
            "## Product goal\n\nEin bestehendes Ziel.\n\n"
            "## Audience and use\n\nEntwicklerinnen und Entwickler.\n\n"
            "## Functional scope\n\n- Bestehende Funktion\n\n"
            "## Out of scope\n\n- Kein öffentlicher Zugriff\n\n"
            "## Target environment\n\nLinux-Container\n\n"
            "## Quality and acceptance\n\nAutomatisierte Tests\n\n"
            "## Locked decisions\n\n- Bleibt so\n\n"
            "## Open questions\n\n- Noch zu klären\n",
            encoding="utf-8",
        )

        state = guide.state(self.project, name="proj")
        values = {step["id"]: step["value"] for step in state["steps"]}

        self.assertEqual("Ein bestehendes Ziel.", values["ziel"])
        self.assertEqual("Entwicklerinnen und Entwickler.", values["nutzer"])
        self.assertEqual("- Bestehende Funktion", values["umfang"])
        self.assertEqual("- Kein öffentlicher Zugriff", values["nicht_umfang"])
        self.assertEqual("Linux-Container", values["umgebung"])
        self.assertEqual("Automatisierte Tests", values["qualitaet"])
        self.assertEqual("- Bleibt so", values["entscheidungen"])
        self.assertEqual("- Noch zu klären", values["offene_fragen"])
        self.assertEqual([], state["open"])
        self.assertTrue(all(step["status"] == "gefüllt" for step in state["steps"]))

    def test_apply_preserves_and_updates_english_spec_sections(self):
        (self.project / "SPEC.md").write_text(
            "# proj — Produktspezifikation\n\n"
            "## Product goal\n\nEin bestehendes Ziel.\n\n"
            "## Audience and use\n\nEntwicklerinnen und Entwickler.\n\n"
            "## Functional scope\n\n- Bestehende Funktion\n\n"
            "## Out of scope\n\n- Kein öffentlicher Zugriff\n\n"
            "## Target environment\n\nLinux-Container\n\n"
            "## Quality and acceptance\n\nAutomatisierte Tests\n\n"
            "## Locked decisions\n\n- Bleibt so\n\n"
            "## Open questions\n\n- Noch zu klären\n",
            encoding="utf-8",
        )

        kept = guide.apply(self.project, {"ziel": "Neues Ziel."}, name="proj")
        self.assertIn("ziel", kept["sections_kept"])
        self.assertIn("Ein bestehendes Ziel.", self.spec())

        updated = guide.apply(
            self.project,
            {"umfang": "- Neue Funktion"},
            replace=["umfang"],
            name="proj",
        )

        self.assertIn("umfang", updated["sections_written"])
        text = self.spec()
        self.assertIn("## Functional scope\n\n- Neue Funktion", text)
        self.assertNotIn("- Bestehende Funktion", text)
        self.assertIn("## Product goal\n\nEin bestehendes Ziel.", text)
        self.assertEqual(
            [
                "Product goal",
                "Audience and use",
                "Functional scope",
                "Out of scope",
                "Target environment",
                "Quality and acceptance",
                "Locked decisions",
                "Open questions",
            ],
            re.findall(r"(?m)^##[ \t]+(.+?)[ \t]*$", text),
        )

    def test_existing_files_are_kept_and_never_overwritten(self):
        self.project.joinpath("AGENTS.md").write_text("EIGENE REGEL\n", encoding="utf-8")
        self.project.joinpath("TICKETS.md").write_text("EIGENE TICKETS\n", encoding="utf-8")

        result = guide.apply(self.project, self.answers(), name="proj",
                             templates_dir=REPO / "templates")

        self.assertEqual(
            self.project.joinpath("AGENTS.md").read_text(encoding="utf-8"),
            "EIGENE REGEL\n",
        )
        self.assertEqual(
            self.project.joinpath("TICKETS.md").read_text(encoding="utf-8"),
            "EIGENE TICKETS\n",
        )
        self.assertIn("AGENTS.md", result["files_kept"])
        self.assertIn("TICKETS.md", result["files_kept"])
        self.assertNotIn("AGENTS.md", result["files_created"])
        self.assertNotIn("TICKETS.md", result["files_created"])

    def test_existing_filled_section_is_not_overwritten_without_replace(self):
        self.project.joinpath("SPEC.md").write_text(
            "# proj\n\n## Product goal\n\nBestehendes Ziel.\n", encoding="utf-8"
        )

        result = guide.apply(
            self.project, {"ziel": "Neues Ziel."}, name="proj",
            templates_dir=REPO / "templates",
        )

        self.assertIn("Bestehendes Ziel.", self.spec())
        self.assertNotIn("Neues Ziel.", self.spec())
        self.assertIn("ziel", result["sections_kept"])

    def test_explicit_replace_overwrites_the_selected_section_only(self):
        self.project.joinpath("SPEC.md").write_text(
            "# proj\n\n## Product goal\n\nBestehendes Ziel.\n\n"
            "## Target environment\n\nBestehende Umgebung.\n",
            encoding="utf-8",
        )

        guide.apply(
            self.project,
            {"ziel": "Neues Ziel.", "umgebung": "Neue Umgebung."},
            replace=["ziel"],
            name="proj",
            templates_dir=REPO / "templates",
        )

        text = self.spec()
        self.assertIn("Neues Ziel.", text)
        self.assertNotIn("Bestehendes Ziel.", text)
        self.assertIn("Bestehende Umgebung.", text)
        self.assertNotIn("Neue Umgebung.", text)

    def test_empty_answers_create_visible_open_placeholders(self):
        result = guide.apply(self.project, {}, name="proj",
                             templates_dir=REPO / "templates")

        text = self.spec()
        self.assertIn(guide.PLACEHOLDER, text)
        self.assertFalse(result["state"]["complete"])
        statuses = {step["id"]: step["status"] for step in result["state"]["steps"]}
        self.assertEqual(statuses["ziel"], "offen")

    def test_apply_rejects_unknown_steps_and_non_string_answers(self):
        self.project.joinpath("SPEC.md").write_text("# proj\n", encoding="utf-8")
        before = self.spec()

        with self.assertRaisesRegex(ValueError, "Unbekannter Schritt"):
            guide.apply(self.project, {"gibt-es-nicht": "x"}, name="proj")
        with self.assertRaisesRegex(ValueError, "Text"):
            guide.apply(self.project, {"ziel": 42}, name="proj")

        self.assertEqual(self.spec(), before)

    def test_apply_rejects_spec_symlink_leaving_the_project(self):
        outside = self.root / "aussen.md"
        outside.write_text("NICHT ÄNDERN\n", encoding="utf-8")
        os.symlink(outside, self.project / "SPEC.md")

        with self.assertRaisesRegex(ValueError, "verlässt das Projekt"):
            guide.apply(self.project, {"ziel": "Neu"}, name="proj")

        self.assertEqual(outside.read_text(encoding="utf-8"), "NICHT ÄNDERN\n")

    def test_apply_without_templates_still_writes_spec_and_readme(self):
        result = guide.apply(self.project, self.answers(), name="proj")

        self.assertTrue(self.project.joinpath("SPEC.md").is_file())
        self.assertTrue(self.project.joinpath("README.md").is_file())
        self.assertIn("TICKETS.md", result["files_without_template"])


class ProjectGuideAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, argv):
        self.calls.append(list(argv))
        return 0, ""

    def test_agent_prompt_contains_context_and_rules(self):
        self.project.joinpath("SPEC.md").write_text(
            "# proj\n\n## Functional scope\n\nBisheriger Stand.\n", encoding="utf-8"
        )

        prompt = guide.agent_prompt(
            self.project, "umfang", name="proj", note="Bitte knapp halten."
        )

        self.assertIn("proj", prompt)
        self.assertIn("Funktionsumfang", prompt)
        self.assertIn("Welche Funktionen", prompt)
        self.assertIn("Bisheriger Stand.", prompt)
        self.assertIn("Bitte knapp halten.", prompt)
        self.assertIn("UNBEKANNT", prompt)
        self.assertIn("Ändere keine anderen Dateien", prompt)
        self.assertIn(guide.DRAFT_REL.format(step="umfang"), prompt)

    def test_start_agent_uses_argument_list_and_creates_draft_folder(self):
        started = guide.start_agent(
            self.project,
            "ziel",
            name="proj",
            note="Kurz",
            log_dir=self.logs,
            runner=self.runner,
            tmux_has=lambda session: False,
        )

        self.assertEqual(len(self.calls), 1)
        argv = self.calls[0]
        self.assertEqual(argv[0], "tmux")
        self.assertIn("new-session", argv)
        self.assertIn("test-agent", argv)
        self.assertEqual(started["session"], "vibe-guide~proj")
        self.assertTrue(self.project.joinpath(".vibe", "guide").is_dir())
        self.assertTrue(any("Entwirf ausschließlich den Abschnitt" in arg for arg in argv))
        self.assertIn(str(self.logs), started["log"])

    def test_default_runner_reports_a_missing_program_without_shell(self):
        code, output = guide._default_runner(["gibt-es-nicht-f9", "a;b"])

        self.assertEqual(code, 127)
        self.assertIn("gibt-es-nicht-f9", output)

    def test_guide_session_cannot_collide_with_a_package_run(self):
        # Projekt "guide-proj" läuft als Paket in "vibe-guide-proj".
        started = guide.start_agent(
            self.project,
            "ziel",
            name="proj",
            log_dir=self.logs,
            runner=self.runner,
            tmux_has=lambda session: session == "vibe-guide-proj",
        )

        self.assertEqual(started["session"], "vibe-guide~proj")
        self.assertNotEqual(started["session"], "vibe-guide-proj")
        self.assertEqual(len(self.calls), 1)

    def test_start_agent_fails_closed_when_the_sandbox_is_not_startable(self):
        with (
            mock.patch.object(sandbox, "status", return_value={"enabled": True}),
            mock.patch.object(
                sandbox, "check", return_value={"ok": False, "message": "bwrap fehlt"}
            ),
        ):
            with self.assertRaisesRegex(ValueError, "nicht startbar"):
                guide.start_agent(
                    self.project,
                    "ziel",
                    name="proj",
                    log_dir=self.logs,
                    runner=self.runner,
                    tmux_has=lambda session: False,
                )

        self.assertEqual(self.calls, [])

    def test_failed_start_keeps_an_existing_draft(self):
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        draft = folder / "ziel.md"
        draft.write_text("Alter Entwurf\n", encoding="utf-8")

        def failing(argv):
            self.calls.append(argv)
            return 1, "tmux: Start fehlgeschlagen"

        with self.assertRaisesRegex(ValueError, "Start fehlgeschlagen"):
            guide.start_agent(
                self.project,
                "ziel",
                name="proj",
                log_dir=self.logs,
                runner=failing,
                tmux_has=lambda session: False,
            )

        self.assertTrue(draft.is_file())
        self.assertEqual(draft.read_text(encoding="utf-8"), "Alter Entwurf\n")

    def test_started_run_keeps_the_draft_the_agent_has_already_written(self):
        """Ein schneller Agent darf seinen frischen Entwurf nicht verlieren.

        Ein alter Entwurf wird beim Start aufgeräumt. Passiert das erst nach
        dem Start, kann es den Entwurf löschen, den der Agent in der
        Zwischenzeit geschrieben hat.
        """
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        draft = folder / "ziel.md"
        draft.write_text("Alter Entwurf\n", encoding="utf-8")

        def fast_agent(argv):
            self.calls.append(argv)
            draft.write_text("Neuer Entwurf des Agenten\n", encoding="utf-8")
            return 0, ""

        started = guide.start_agent(
            self.project,
            "ziel",
            name="proj",
            log_dir=self.logs,
            runner=fast_agent,
            tmux_has=lambda session: False,
        )

        self.assertEqual(started["draft"], ".vibe/guide/ziel.md")
        self.assertTrue(
            draft.is_file(), "der frisch geschriebene Entwurf wurde gelöscht"
        )
        self.assertEqual(
            draft.read_text(encoding="utf-8"), "Neuer Entwurf des Agenten\n"
        )

    def write_sandbox_env(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nAGENT=test-agent\nSANDBOX=on\nSANDBOX_TOOLS=""\n',
            encoding="utf-8",
        )

    def test_agent_command_stays_direct_when_the_sandbox_is_off(self):
        command = guide._agent_command(self.project, "test-agent", "titel", "prompt")

        self.assertEqual(command[0], "opencode")
        self.assertNotIn("bwrap", command)

    @env_support.skip_if_sandbox_nested
    def test_agent_command_is_wrapped_when_the_sandbox_is_on(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_sandbox_env()
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)

        command = guide._agent_command(self.project, "test-agent", "titel", "prompt")

        self.assertEqual(command[0], sandbox.status(self.project)["bwrap"])
        marker = command.index("--")
        self.assertIn("opencode", command[marker + 1:])
        self.assertEqual(command[marker - 3:marker], ["--bind", str(folder), str(folder)])

    @env_support.skip_if_sandbox_nested
    def test_sandboxed_command_can_write_the_draft_but_not_the_configuration(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_sandbox_env()
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        self.addCleanup(
            lambda: shutil.rmtree(sandbox.state_dir(self.project), ignore_errors=True)
        )
        before = (self.project / ".vibe" / "project.env").read_text(encoding="utf-8")
        script = (
            "if echo entwurf > .vibe/guide/probe.md; then echo DRAFT_OK; "
            "else echo DRAFT_DENIED; fi; "
            "if echo x >> .vibe/project.env 2>/dev/null; then echo ENV_OPEN; "
            "else echo ENV_DENIED; fi"
        )

        command = guide._sandbox_command(self.project, ["/bin/sh", "-c", script])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=os.path.expanduser("~")),
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRAFT_OK", result.stdout)
        self.assertIn("ENV_DENIED", result.stdout)
        self.assertTrue((folder / "probe.md").is_file())
        self.assertEqual(
            (self.project / ".vibe" / "project.env").read_text(encoding="utf-8"), before
        )

    def test_start_agent_refuses_when_a_guide_run_is_active(self):
        with self.assertRaisesRegex(ValueError, "läuft bereits"):
            guide.start_agent(
                self.project,
                "ziel",
                name="proj",
                log_dir=self.logs,
                runner=self.runner,
                tmux_has=lambda session: True,
            )

        self.assertEqual(self.calls, [])

    def test_start_agent_rejects_an_invalid_agent_name(self):
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=boese shell; rm -rf /\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "Agentenname"):
            guide.start_agent(
                self.project,
                "ziel",
                name="proj",
                log_dir=self.logs,
                runner=self.runner,
                tmux_has=lambda session: False,
            )

        self.assertEqual(self.calls, [])

    def test_start_agent_rejects_unknown_step(self):
        with self.assertRaisesRegex(ValueError, "Unbekannter Schritt"):
            guide.start_agent(
                self.project,
                "gibt-es-nicht",
                name="proj",
                log_dir=self.logs,
                runner=self.runner,
                tmux_has=lambda session: False,
            )

        self.assertEqual(self.calls, [])

    def test_draft_can_be_applied_and_is_removed(self):
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        guide.draft_path(self.project, "umfang").write_text(
            "## Functional scope\n\n- Projekte verwalten\n- Agenten starten\n",
            encoding="utf-8",
        )

        result = guide.draft_apply(self.project, "umfang", name="proj")

        text = self.project.joinpath("SPEC.md").read_text(encoding="utf-8")
        self.assertIn("- Projekte verwalten", text)
        self.assertEqual(text.count("## Functional scope"), 1)
        self.assertIn("umfang", result["sections_written"])
        self.assertFalse(guide.draft_path(self.project, "umfang").exists())

    def test_inner_heading_in_a_draft_does_not_become_a_spec_section(self):
        """Ein Agentenentwurf darf die Abschnittsstruktur der SPEC nicht aufbrechen."""
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        guide.draft_path(self.project, "umfang").write_text(
            "## Functional scope\n\n- Rechnungen einlesen\n\n"
            "## Zusatzhinweis\n\nNur ein Unterpunkt des Entwurfs.\n",
            encoding="utf-8",
        )

        guide.draft_apply(self.project, "umfang", name="proj")

        text = self.project.joinpath("SPEC.md").read_text(encoding="utf-8")
        self.assertEqual(
            text.count("\n## Zusatzhinweis"), 0, "Entwurf erzeugte einen eigenen Abschnitt"
        )
        self.assertIn("### Zusatzhinweis", text)
        self.assertIn("Nur ein Unterpunkt des Entwurfs.", text)
        state = guide.state(self.project, name="proj")
        self.assertNotIn("Zusatzhinweis", [item["heading"] for item in state["steps"]])

    def test_headings_inside_a_fenced_block_stay_unchanged(self):
        """Codebeispiele im Entwurf bleiben wortgleich, auch mit ##-Zeilen."""
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        guide.draft_path(self.project, "umfang").write_text(
            "Der Aufruf sieht so aus:\n\n"
            "```\n"
            "## Beispiel\n"
            "```\n",
            encoding="utf-8",
        )

        guide.draft_apply(self.project, "umfang", name="proj")

        text = self.project.joinpath("SPEC.md").read_text(encoding="utf-8")
        self.assertIn("```\n## Beispiel\n```", text, "Codebeispiel wurde verfälscht")
        self.assertNotIn("### Beispiel", text)

    def test_draft_discard_removes_only_the_draft(self):
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        draft = guide.draft_path(self.project, "ziel")
        draft.write_text("Entwurf\n", encoding="utf-8")

        self.assertTrue(guide.draft_discard(self.project, "ziel"))
        self.assertFalse(draft.exists())
        with self.assertRaisesRegex(ValueError, "Kein Entwurf"):
            guide.draft_discard(self.project, "ziel")


class GuideApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = make_project(cls.root)
        toolchain = cls.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        # Instanzvariablen nicht erben: Der Testserver muss auf 127.0.0.1
        # binden, und eine geerbte persönliche config.json darf Laufzeit/State
        # nicht auf produktive Pfade legen (EROFS im Läufer).
        env = env_support.isolated_environ(
            VIBE=cls.root,
            VIBE_NO_CONTAINER="1",
            VIBE_UI_PORT=cls.port,
            VIBE_RUNTIME=cls.log_dir,
            VIBE_STATE=cls.root / "_toolchain",
            HOME=cls.root / "home",
            VIBE_CONFIG_FILE=(
                cls.root / "home" / ".config" / "vibe" / "config.json"
            ),
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        for name in ("SPEC.md", "TICKETS.md", "AGENTS.md", "FEEDBACK.md", "README.md"):
            path = self.project / name
            if path.exists():
                path.unlink()
        shutil.rmtree(self.project / ".vibe" / "guide", ignore_errors=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\n", encoding="utf-8"
        )

    def request(self, path, payload=None, token=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        if token:
            req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body


class ProjectGuideApiTest(GuideApiFixture):
    def test_api_returns_steps_files_and_drafts(self):
        status, body = self.request("/api/guide?name=proj")

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertFalse(data["complete"])
        self.assertEqual(data["next"], "ziel")
        self.assertIn("SPEC.md", data["missing_files"])
        self.assertEqual(len(data["steps"]), len(guide.steps()))
        self.assertIn("agent", data)

    def test_api_saves_answers_and_creates_fachliche_files(self):
        status, body = self.request(
            "/api/guide",
            {
                "name": "proj",
                "action": "save",
                "answers": {
                    "ziel": "Ein Ziel.",
                    "nutzer": "Nutzer.",
                    "umfang": "- Funktion",
                    "nicht_umfang": "- Nichts",
                    "umgebung": "Linux",
                    "qualitaet": "Tests",
                },
            },
        )

        self.assertEqual(status, 200, body)
        self.assertTrue((self.project / "SPEC.md").is_file())
        self.assertTrue((self.project / "TICKETS.md").is_file())
        self.assertTrue((self.project / "AGENTS.md").is_file())
        self.assertIn("Ein Ziel.", (self.project / "SPEC.md").read_text(encoding="utf-8"))
        self.assertTrue(json.loads(body)["guide"]["state"]["complete"])

    def test_api_rejects_unknown_step_without_writing(self):
        status, body = self.request(
            "/api/guide",
            {"name": "proj", "action": "save", "answers": {"gibt-es-nicht": "x"}},
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannter Schritt", body)
        self.assertFalse((self.project / "SPEC.md").exists())

    def test_api_applies_and_discards_an_agent_draft(self):
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True)
        guide.draft_path(self.project, "ziel").write_text(
            "Entwurfsziel aus dem Agenten.\n", encoding="utf-8"
        )

        status, body = self.request(
            "/api/guide", {"name": "proj", "action": "draft_apply", "step": "ziel"}
        )
        self.assertEqual(status, 200, body)
        self.assertIn(
            "Entwurfsziel aus dem Agenten.",
            (self.project / "SPEC.md").read_text(encoding="utf-8"),
        )

        status, body = self.request(
            "/api/guide", {"name": "proj", "action": "draft_discard", "step": "umfang"}
        )
        self.assertEqual(status, 400, body)

    def test_api_rejects_agent_run_for_unknown_step_without_starting_tmux(self):
        status, body = self.request(
            "/api/guide",
            {"name": "proj", "action": "agent", "step": "gibt-es-nicht"},
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannter Schritt", body)
        self.assertFalse((self.project / ".vibe" / "guide").exists())

    def test_api_rejects_a_too_long_agent_note(self):
        status, body = self.request(
            "/api/guide",
            {"name": "proj", "action": "agent", "step": "ziel", "note": "x" * 2001},
        )

        self.assertEqual(status, 400, body)
        self.assertIn("zu lang", body)

    def test_api_rejects_a_non_text_agent_note(self):
        status, body = self.request(
            "/api/guide",
            {"name": "proj", "action": "agent", "step": "ziel", "note": ["x"]},
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Hinweis muss Text sein", body)

    def test_api_requires_a_valid_token(self):
        status, body = self.request("/api/guide?name=proj", token=False)

        self.assertEqual(status, 403, body)

    def test_dashboard_contains_the_project_assistant(self):
        html = served_page(self.request)

        self.assertIn("Projektassistent", html)
        self.assertIn("Mit Agent entwerfen", html)


if __name__ == "__main__":
    unittest.main()
