"""Abnahme AP8 „Bereit für Github Teil 2“: Auschecken aus GitHub.

Die Tests leiten sich aus Arbeitspaket AP8, SPEC.md und der Nutzerentscheidung
ab (nicht aus einer Implementierung): Im Idealfall enthält das Repository nur
Projektcode. Die vibe-Einstellungen passen Nutzer individuell an ihre Instanz
an (analog wie bei einer IDE). Nach dem Auschecken gelten daher die
lokalen Einstellungen. Die im Projekt aktiven Agenten werden auf die lokal
konfigurierten globalen Agenten angepasst.

Geprüfte fachliche Schnittstellen:

* ``vibe_github.clone(url, zielordner)``: ``git clone`` mit Argumentlisten
  (keine Shell, kein Terminal-Prompt, Zeitlimit). Bei Fehlschlag bleibt kein
  halbes Projektverzeichnis übrig.
* ``vibe.checkout_from_github(url, name=None)`` -> (name, Zusammenfassung):
  URL-Prüfung über ``vibe_github.parse_remote_url``; Name aus Parameter oder
  URL; Ziel ``VIBE/<name>``; danach lokale Übernahme von project.env
  (verwaltete Schlüssel durch lokale Vorlagewerte ersetzt), AGENTS.md
  (verwalteter Regelblock auf lokalen Stand), Test-Agent, fehlende
  Vorlagedateien; Agenten-Neumapping in ``.vibe/agents.json``; Projekt ist
  direkt in der Projektliste auffindbar; origin zeigt auf die ausgecheckte
  Adresse; github.com-URLs setzen GITHUB_REPO/GITHUB_ENABLED.
* CLI ``vibe clone <url> [name]``: verständliche Zusammenfassung; Fehler klar
  und ohne Restzustand.

Kein echtes Netz: alle Clone-Vorgänge nutzen lokale Bare-Repositories über
``file://`` in temporären Verzeichnissen. github.com-Adressen werden ohne
Kontaktaufnahme über die URL-Analyse geprüft; der echte Clone-Tätigkeit wird
durch eine fiktive Quelle ersetzt. Alle Läufe arbeiten mit temporären
VIBE-/HOME-Verzeichnissen; keine produktiven Pfade, keine Modellaufrufe, kein
Verlass auf wirksame Unix-Rechte.

Run:

    python3 -m unittest tests.unit.test_ap8_github_checkout -v
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

# Isolierte Umgebungsvariablen (Muster tests/unit/test_project_agents.py).
ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE", "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_STATE",
    "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE", "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "MAX_PACKAGES", "VERIFY_QUICK", "VERIFY_FULL",
    "AGENT", "SANDBOX", "SANDBOX_TOOLS", "GITHUB_TOKEN", "GH_TOKEN",
)

# Werte der lokalen Vorlage, die mit dem Projekt mitgelieferte
# Einstellungen überschreiben müssen (AP8, Nutzerentscheidung).
LOKALE_REVIEWER = "lokal-reviewer"
LOKALE_SANDBOX = "aus"
LOKALE_QUICK = "echo lokal-quick"
LOKALE_PAKET = "echo lokal-paket"
LOKALE_FULL = "echo lokal-full"
TEST_AGENT_TEMPLATE = "LOKALER-PRUEFAGENT-STAND-4711\n"
TICKETS_TEMPLATE = "# TICKETS-LUECKE-A-LDOK\n"
FEEDBACK_TEMPLATE = "# FEEDBACK-LUECKE-A-LDOK\n"
OPENCODE_JSON_TEMPLATE = '{\n  "$schema": "lokale-opencode-vorlage"\n}\n'

REPO_ENV = (
    "TYPE=generic\n"
    "REVIEWER=repo-reviewer\n"
    "TESTER=repo-tester\n"
    "SANDBOX=an\n"
    'SANDBOX_TOOLS="git,cargo"\n'
    'VERIFY_QUICK="echo repo-quick"\n'
    'VERIFY_PACKAGE="echo repo-paket"\n'
    'VERIFY_FULL="echo repo-full"\n'
    "BENUTZER=EIGEN\n"
    "EXTRA=bleibt\n"
)

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/global-modell
---

Globaler Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent
mode: primary
model: opencode/vibe-modell
---

Vibe-Prompt.
"""

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True, timeout=60)


def git_out(cwd, *argv):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60).stdout


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update({
        "VIBE": str(vibe_root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap8_github_checkout_under_test", str(CLI)
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


def write_template(templates, typ, files):
    for relative, content in files.items():
        target = Path(templates) / typ / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class StorageFixture(unittest.TestCase):
    """Temporärer Arbeitsbereich mit lokalen Vorlagen und lokalen Agenten."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "ws"
        self.workspace.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        # Die Prüfumgebung wird nur für diesen Test gesetzt und danach
        # zurückgebaut: Ohne Rückbau leakt VIBE_STATE/VIBE_STORAGE_LOCK_DIR in
        # nachfolgende Testmodule desselben Prozesses (Fehlbefund Fixlauf 2).
        environment = mock.patch.dict(os.environ, {
            "VIBE_STORAGE_LOCK_DIR": str(self.workspace / "locks"),
            "VIBE_STATE": str(self.install),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.cli = load_cli(self.workspace, self.home)
        self.build_local_templates()
        self.build_local_agents()

    # --------------------------------------------- lokale Welt (Vorlagen)
    def build_local_templates(self):
        """Lokale Vorlagen: Genau sie sollen nach dem Clone gelten."""
        templates = self.root / "templates"
        write_template(templates, "common", {
            "FEEDBACK.md": FEEDBACK_TEMPLATE,
            "TICKETS.md": TICKETS_TEMPLATE,
            "opencode.json": OPENCODE_JSON_TEMPLATE,
            ".opencode/agents/test-agent.md": TEST_AGENT_TEMPLATE,
        })
        write_template(templates, "generic", {
            "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n" + self.cli.GENERAL_RULES + "\n",
            ".vibe/project.env": (
                "TYPE=generic\n"
                "REVIEWER=" + LOKALE_REVIEWER + "\n"
                "TESTER=test-agent\n"
                "SANDBOX=" + LOKALE_SANDBOX + "\n"
                "SANDBOX_TOOLS=\n"
                "VERIFY_QUICK=" + LOKALE_QUICK + "\n"
                "VERIFY_PACKAGE=" + LOKALE_PAKET + "\n"
                "VERIFY_FULL=" + LOKALE_FULL + "\n"
            ),
        })
        self.cli.TPL = str(templates)

    def build_local_agents(self):
        """Lokal konfigurierte globale Agenten: „tester“ plus Vibe-Agent."""
        (self.agents / "tester.md").write_text(GLOBAL_AGENT, encoding="utf-8")
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        data = self.cli.profiles_load()
        data["rollen"] = dict(data.get("rollen", {}))
        data["rollen"]["vibe-agent"] = "vibe"
        self.cli.profiles_save(data)

    # --------------------------------------------- Bare-Repositories
    def bare_path(self, name):
        return self.root / "origin" / (name + ".git")

    def seed_bare(self, name, files):
        """Erzeugt eine Bare-Quelle ohne Netz und liefert die file://-Adresse."""
        work = self.root / "seed" / name
        work.mkdir(parents=True)
        for relative, content in files.items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(work, "init", "-q", "-b", "main")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "seed")
        bare = self.bare_path(name)
        bare.mkdir(parents=True)
        git(bare, "init", "-q", "--bare")
        git(work, "push", "-q", str(bare), "main")
        git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
        self.cli._pm.clear()
        return "file://" + str(bare)

    # --------------------------------------------- hilfreiche Projekte
    def checkout(self, url, name=None):
        """Führt ``checkout_from_github`` aus und listet im Anschluss frisch."""
        out = io.StringIO()
        with redirect_stdout(out):
            result = self.cli.checkout_from_github(url, name=name)
        self.assertTrue(bool(result), "Fehlendes (name, Zusammenfassung)-Ergebnis")
        found, summary = result
        return found, str(summary or "")

    def expect_error(self, url, name=None):
        """Führt das Auschecken aus und liefert die geworfene Ausnahme."""
        with self.assertRaises(Exception) as caught:
            self.checkout(url, name=name)
        self.assertTrue(str(caught.exception).strip(),
                        "Eine Fehlermeldung darf nicht leer sein")
        return caught.exception

    def project_env_path(self, name):
        return self.workspace / name / ".vibe" / "project.env"

    def env_values(self, name):
        return self.cli.read_env(str(self.project_env_path(name)))


# ================================================================ Cloning
class CloneAndProjectTest(StorageFixture):
    """AK1: Auschecken legt ein neues Projekt an; Name aus Parameter oder URL."""

    def test_checkout_clones_the_repository_and_lists_the_new_project(self):
        url = self.seed_bare("koffer", {"README.md": "Koffer-Inhalt\n"})
        self.assertEqual(self.cli.projects(), [])

        found, summary = self.checkout(url)

        self.assertEqual(found, "koffer")
        self.assertTrue(summary.strip(), "Eine Zusammenfassung ist erwartet")
        self.assertTrue((self.workspace / "koffer" / ".git").is_dir())
        self.assertEqual(
            (self.workspace / "koffer" / "README.md").read_text(encoding="utf-8"),
            "Koffer-Inhalt\n",
        )
        # Direkt (ohne jeden Zusatz-Reload) in der Projektliste auffindbar:
        self.assertIn("koffer", self.cli.projects())
        mapping = self.cli.project_map()
        self.assertIn("koffer", mapping)
        self.assertEqual(
            os.path.realpath(mapping["koffer"]),
            os.path.realpath(self.workspace / "koffer"),
        )

    def test_project_name_is_taken_from_the_url_when_not_given(self):
        url = self.seed_bare("mein-koffer", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertEqual(found, "mein-koffer")
        self.assertTrue((self.workspace / "mein-koffer" / ".git").is_dir())
        self.assertIn("mein-koffer", self.cli.projects())

    def test_project_name_is_cleaned_to_the_allowed_pattern(self):
        """Ordnername mit Leer- und Großbuchstaben wird auf das zulässige
        Muster ^[a-z0-9][a-z0-9_-]*$ bereinigt."""
        url = self.seed_bare("Mein Projekt", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertRegex(found, r"^[a-z0-9][a-z0-9_-]*$")
        self.assertTrue((self.workspace / found / ".git").is_dir())
        self.assertIn(found, self.cli.projects())

    def test_given_name_wins_over_the_derived_name(self):
        url = self.seed_bare("autoform", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url, name="lager")

        self.assertEqual(found, "lager")
        self.assertTrue((self.workspace / "lager" / "README.md").is_file())
        self.assertFalse((self.workspace / "autoform").exists())
        self.assertIn("lager", self.cli.projects())
        self.assertNotIn("autoform", self.cli.projects())

    def test_remote_origin_points_to_the_checked_out_address(self):
        url = self.seed_bare("adresse", {"README.md": "Inhalt\n"})

        self.checkout(url)

        origin = git_out(self.workspace / "adresse",
                         "remote", "get-url", "origin").strip()
        self.assertEqual(origin, url)


# ============================================================= Übernahme
class LocalAdoptionTest(StorageFixture):
    """AK2: Lokale vibe-Einstellungen überschreiben die Projekteinstellungen."""

    def full_remote(self):
        """Bare-Quelle, die alles mitbringt, was laut Nutzerentscheidung von
        der lokalen Vorlage übernommen/ersetzt werden muss."""
        return self.seed_bare("koffer", {
            "README.md": "Koffer\n",
            ".vibe/project.env": REPO_ENV,
            ".vibe/agents.json": json.dumps({
                "version": 2,
                "aktiv": ["vibe-agent", "fremd", "tester"],
                "modelle": {"fremd": "x/fremd", "tester": "opencode/behalt"},
            }),
            ".opencode/agents/test-agent.md": "# Mitgelieferter V99\n",
            "AGENTS.md": (
                "# Repo-Regel\n\n"
                + self.cli.GENERAL_RULES_MARK
                + "\n## Alt\n- veraltet\n"
                + self.cli.GENERAL_RULES_END
                + "\n\n## Eigener Rest\n"
            ),
            "FEEDBACK.md": "# Eigenes Feedback\n",
        })

    def test_missing_project_env_is_created_from_the_local_template(self):
        url = self.seed_bare("blanko", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertTrue(self.project_env_path(found).is_file(),
                        "project.env fehlt nach dem Auschecken")
        values = self.env_values(found)
        self.assertEqual(values.get("TESTER"), "test-agent")
        self.assertEqual(values.get("REVIEWER"), LOKALE_REVIEWER)
        self.assertEqual(values.get("VERIFY_QUICK"), LOKALE_QUICK)
        self.assertIn(values.get("TYPE") or "", self.cli.types())

    def test_local_template_values_overwrite_the_managed_repository_keys(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        for key, expected in (
            ("REVIEWER", LOKALE_REVIEWER),
            ("TESTER", "test-agent"),
            ("SANDBOX", LOKALE_SANDBOX),
            ("VERIFY_QUICK", LOKALE_QUICK),
            ("VERIFY_PACKAGE", LOKALE_PAKET),
            ("VERIFY_FULL", LOKALE_FULL),
        ):
            self.assertEqual(values.get(key), expected, key)
        text = self.project_env_path(found).read_text(encoding="utf-8")
        for verboten in ("repo-quick", "repo-paket", "repo-full",
                         "repo-tester", "repo-reviewer"):
            self.assertNotIn(verboten, text, verboten)
        # Eigene, nicht verwaltete Schlüssel bleiben:
        self.assertEqual(values.get("EXTRA"), "bleibt")
        self.assertIn("BENUTZER=EIGEN", text)
        # TYPE steht auf dem erkannten Typ; die verwalteten Werte stammen aus
        # der lokalen Vorlage dieses Typs.
        typ = values.get("TYPE") or ""
        self.assertIn(typ, self.cli.types(), typ)
        template_values = self.cli.read_env(
            os.path.join(self.cli.TPL, typ, ".vibe", "project.env")
        )
        for key in ("REVIEWER", "VERIFY_QUICK"):
            self.assertEqual(values.get(key), template_values.get(key),
                             "Vorlagewert von " + key)

    def test_github_com_url_sets_the_github_link_without_contacting_github(self):
        """github.com-Adresse: GITHUB_REPO=owner/name und GITHUB_ENABLED=1.
        github.com wird dabei nicht kontaktiert — der echte Clone-Tätigkeit
        wird durch eine fiktive, in den Zielordner gestellte Quelle ersetzt."""
        url = "https://github.com/owner/beispiel.git"
        fake_state = {}

        def fake_clone(given_url, given_target):
            self.assertEqual(str(given_url), url)
            fake_state["target"] = str(given_target)
            target = str(given_target)
            os.makedirs(target, exist_ok=True)
            git(target, "init", "-q", "-b", "main")
            (Path(target) / "README.md").write_text("GitHub-Inhalt\n", encoding="utf-8")
            git(target, "add", "-A")
            git(target, "commit", "-q", "-m", "github")
            git(target, "remote", "add", "origin", given_url)
            return 0, "fiktives geklontes Ergebnis"

        # MagicMock als Stand-in: Nur so bleibt die Aufrufprüfung (genau
        # einmal) erhalten; die Prüfung der Argumente macht fake_clone selbst.
        standin = mock.MagicMock(side_effect=fake_clone)
        with mock.patch.object(self.cli.vibe_github, "clone", standin):
            found, _summary = self.checkout(url)

        standin.assert_called_once()
        self.assertEqual(fake_state["target"],
                         str(self.workspace / "beispiel"))
        self.assertEqual(found, "beispiel")
        self.assertIn("beispiel", self.cli.projects())
        values = self.env_values("beispiel")
        self.assertEqual(values.get("GITHUB_REPO"), "owner/beispiel")
        self.assertEqual(values.get("GITHUB_ENABLED"), "1")

    def test_file_remotes_stay_without_github_keys(self):
        url = self.seed_bare("nur-localekle", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        self.assertEqual(values.get("GITHUB_REPO") or "", "")
        self.assertIsNone(values.get("GITHUB_ENABLED"))

    def test_the_managed_rules_block_is_brought_to_the_local_state(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        text = (self.workspace / found / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Repo-Regel\n"))
        self.assertIn("## Eigener Rest\n", text)
        self.assertNotIn("- veraltet", text)
        for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
            self.assertIn(rule, text)
        self.assertEqual(text.count(self.cli.GENERAL_RULES_MARK), 1)

    def test_a_missing_agents_file_is_created_with_the_rules(self):
        url = self.seed_bare("ohne-regeln", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        text = (self.workspace / found / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text.count(self.cli.GENERAL_RULES_MARK), 1)
        self.assertEqual(text.count(self.cli.GENERAL_RULES_END), 1)
        self.assertIn("Projektordner sauber halten", text)

    def test_missing_template_files_are_added_and_own_content_survives(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)
        project = self.workspace / found

        self.assertEqual((project / "TICKETS.md").read_text(encoding="utf-8"),
                         TICKETS_TEMPLATE)
        self.assertEqual((project / "opencode.json").read_text(encoding="utf-8"),
                         OPENCODE_JSON_TEMPLATE)
        # Vorhandene Dateien bleiben unverändert:
        self.assertEqual((project / "FEEDBACK.md").read_text(encoding="utf-8"),
                         "# Eigenes Feedback\n")
        self.assertEqual((project / "README.md").read_text(encoding="utf-8"),
                         "Koffer\n")

    def test_the_shipped_test_agent_is_replaced_by_the_local_template(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        agent = self.workspace / found / ".opencode" / "agents" / "test-agent.md"
        self.assertEqual(agent.read_text(encoding="utf-8"), TEST_AGENT_TEMPLATE)
        self.assertEqual(self.env_values(found).get("TESTER"), "test-agent")


    def test_unmanaged_keys_keep_the_repository_value_while_managed_keys_move_local(self):
        """Ein Schlüssel, der nicht zur verwalteten Menge gehört, bleibt beim
        mitgelieferten Wert — auch wenn die lokale Vorlage ihn ebenfalls kennt;
        abweichende verwaltete Schlüssel gehen auf den lokalen Stand."""
        template = Path(self.cli.TPL) / "generic" / ".vibe" / "project.env"
        template.write_text(
            template.read_text(encoding="utf-8") + "EXTRA_KEY=lokal-vorlage\n",
            encoding="utf-8",
        )
        url = self.seed_bare("fremdschluessel", {
            "README.md": "fremd\n",
            ".vibe/project.env": (
                "TYPE=generic\n"
                "TESTER=repo-tester\n"
                "EXTRA_KEY=projektwert\n"
                "BENUTZER=EIGEN\n"
            ),
        })

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        self.assertEqual(values.get("EXTRA_KEY"), "projektwert")
        self.assertEqual(values.get("TESTER"), "test-agent")
        self.assertEqual(values.get("REVIEWER"), LOKALE_REVIEWER)
        self.assertIn(values.get("TYPE") or "", self.cli.types())
        self.assertIn(
            "BENUTZER=EIGEN",
            self.project_env_path(found).read_text(encoding="utf-8"),
        )


# ================================================================ Agenten
class AgentRemapTest(StorageFixture):
    """AK3: Aktive Agenten des Projekts werden neu auf lokale Agenten gesetzt."""

    def url_with_agents_config(self, aktiv, modelle):
        return self.seed_bare("agentfuder", {
            "README.md": "Agenten\n",
            ".vibe/project.env": "TYPE=generic\n",
            ".vibe/agents.json": json.dumps({
                "version": 2, "aktiv": aktiv, "modelle": modelle,
            }),
        })

    def test_active_agents_are_limited_to_locally_configured_agents(self):
        url = self.url_with_agents_config(
            aktiv=["vibe-agent", "fremd", "tester"],
            modelle={"fremd": "x/fremd", "tester": "opencode/behalt"},
        )

        self.checkout(url)

        path = self.workspace / "agentfuder" / ".vibe" / "agents.json"
        self.assertTrue(path.is_file(), "agents.json bleibt nach dem Clone gesetzt")
        stored = json.loads(path.read_text(encoding="utf-8"))
        aktiv = sorted(stored["aktiv"])
        self.assertNotIn("fremd", aktiv)
        self.assertIn("vibe-agent", aktiv)
        self.assertIn("tester", aktiv)
        modelle = stored.get("modelle") or {}
        self.assertNotIn("fremd", modelle)
        self.assertEqual(modelle.get("tester"), "opencode/behalt")

    def test_without_agents_file_the_default_selection_stays_active(self):
        url = self.seed_bare("ohne-farbe", {"README.md": "Inhalt\n"})

        self.checkout(url)

        path = self.workspace / "ohne-farbe" / ".vibe" / "agents.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sorted(stored["aktiv"]), ["vibe-agent"])
            self.assertEqual(stored.get("modelle") or {}, {})
        else:
            with mock.patch.object(self.cli, "models_list", return_value=[]):
                rows = self.cli.project_agent_rows("ohne-farbe")
            konfiguriert = sorted(row["name"] for row in rows if row.get("configured"))
            # AP2-Korbat: Die opencode-eigenen Agenten general/explore sind
            # standardmäßig aktiv, aber keine Startagenten.
            self.assertEqual(konfiguriert, ["explore", "general", "vibe-agent"])

    def test_the_summary_names_the_removed_agents(self):
        url = self.url_with_agents_config(
            aktiv=["vibe-agent", "fremd", "tester"],
            modelle={"fremd": "x/fremd", "tester": "opencode/behalt"},
        )

        _found, summary = self.checkout(url)

        self.assertIn("fremd", summary)


# ============================================================== Fehlerfälle
class ErrorCaseTest(StorageFixture):
    """AK4: Fehler verständlich; kein halb angelegtes Projekt."""

    def test_an_invalid_url_is_rejected_with_a_clear_error(self):
        exception = self.expect_error("://kaputt")

        self.assertIsInstance(exception, ValueError, type(exception))
        self.assertIn("Remote-Adresse", str(exception))

    def test_an_invalid_name_is_rejected_with_a_clear_error(self):
        url = self.seed_bare("urform", {"README.md": "Inhalt\n"})

        exception = self.expect_error(url, name="Falscher Name!")

        self.assertIn("Name", str(exception))

    def test_an_existing_project_name_is_rejected_without_changes(self):
        url = self.seed_bare("anderware", {"README.md": "Inhalt\n"})
        existing = self.workspace / "belegt"
        (existing / ".vibe").mkdir(parents=True)
        (existing / ".git").mkdir()
        env_text = "TYPE=generic\nTESTER=eigener-tester\n"
        (existing / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
        self.cli._pm.clear()

        exception = self.expect_error(url, name="belegt")

        self.assertIn("belegt", str(exception))
        self.assertEqual(
            self.project_env_path("belegt").read_text(encoding="utf-8"), env_text
        )
        self.assertNotIn("anderware", self.cli.projects())
        self.assertFalse((existing / "README.md").exists())

    def test_an_existing_target_folder_rejects_the_checkout(self):
        url = self.seed_bare("lagerhaus", {"README.md": "Inhalt\n"})
        folder = self.workspace / "brotdose"
        folder.mkdir()
        (folder / "markierungsdatei").write_text("bleibt\n", encoding="utf-8")

        exception = self.expect_error(url, name="brotdose")

        self.assertIn("brotdose", str(exception))
        self.assertEqual(
            (folder / "markierungsdatei").read_text(encoding="utf-8"), "bleibt\n"
        )
        self.assertFalse((folder / ".git").exists())

    def test_an_adoption_failure_removes_the_target_folder_and_reports_the_reason(self):
        """Scheitert die lokale Übernahme nach dem Clone, bleibt kein halbes
        Projekt zurück; die Meldung benennt die Ursache."""
        url = self.seed_bare("scheiteruebernahme", {"README.md": "scheitert\n"})

        with mock.patch.object(self.cli, "ensure_general_rules",
                               side_effect=OSError("gesperrt")):
            exception = self.expect_error(url)

        self.assertIsInstance(exception, ValueError, type(exception))
        self.assertIn("Übernahme fehlgeschlagen", str(exception))
        self.assertIn("gesperrt", str(exception))
        self.assertFalse((self.workspace / "scheiteruebernahme").exists())
        self.assertNotIn("scheiteruebernahme", self.cli.projects())

    def test_a_failed_clone_leaves_no_project_folder(self):
        url = "file://" + str(self.bare_path("nicht-da"))

        exception = self.expect_error(url)

        self.assertTrue(str(exception).strip())
        self.assertFalse((self.workspace / "nicht-da").exists())
        self.assertEqual(self.cli.projects(), [])

    def test_a_missing_git_command_is_reported_without_a_project_folder(self):
        url = self.seed_bare("machtzeit", {"README.md": "Inhalt\n"})
        empty_bin = self.root / "ohnegit"
        empty_bin.mkdir()

        with mock.patch.dict(os.environ, {"PATH": str(empty_bin)}):
            exception = self.expect_error(url)

        self.assertIn("git", str(exception).lower())
        self.assertFalse((self.workspace / "machtzeit").exists())
        self.assertEqual(self.cli.projects(), [])


class CloneBehaviorTest(StorageFixture):
    """``vibe_github.clone`` direkt: Argumentliste, kein Restzustand."""

    def test_clone_copies_the_repository_to_the_target(self):
        url = self.seed_bare("ladefinger", {"README.md": "Ladewerk\n"})
        target = self.workspace / "ladefinger"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertEqual(rc, 0, message)
        self.assertTrue((target / ".git").is_dir())
        self.assertEqual((target / "README.md").read_text(encoding="utf-8"),
                         "Ladewerk\n")

    def test_clone_reports_a_failed_source_without_a_project_folder(self):
        url = "file://" + str(self.bare_path("leer"))
        target = self.workspace / "leer"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertTrue(str(message).strip())
        self.assertFalse(target.exists())

    def test_clone_runs_without_a_shell(self):
        """Die URL wird als ein Argument übergeben: ein in der URL
        versteckter Shell-Befehl wird nicht ausgeführt (Marker bleibt weg)."""
        marker = self.root / "shell-marker"
        url = "file://rueckweg; touch " + str(marker) + " #"
        target = self.workspace / "betrug"

        rc, _message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertFalse(marker.exists(), "URL wurde über eine Shell ausgeführt")
        self.assertFalse(target.exists())


class CredentialMaskingTest(StorageFixture):
    """Meldungen dürfen eingebettete Zugangsdaten nicht weitergeben."""

    def test_mask_embedded_credentials_masks_all_urls_and_keeps_plain_ones(self):
        """Mehrzeilige Git-Ausgaben: Zugangsdaten in allen URLs werden zu
        ``***@`` ersetzt; Adressen ohne Zugangsdaten bleiben unverändert."""
        mask = self.cli.vibe_github.mask_embedded_credentials
        text = (
            "fatal: unable to access 'https://nutzer:geheim@github.com/owner/repo.git/'\n"
            "weitere Zeile: https://person:brief@github.com/anderes/repo.git und\n"
            "nur Anmeldung: https://klartext@github.com/ohne/pass.git, aber\n"
            "klar bleibt: https://github.com/owner/plain.git"
        )

        masked = mask(text)

        for geheim in ("geheim", "nutzer:geheim", "person:brief", "brief@", "klartext@"):
            self.assertNotIn(geheim, masked, geheim)
        self.assertEqual(masked.count("***@github.com"), 3)
        self.assertIn("https://github.com/owner/plain.git", masked)
        self.assertIn("fatal: unable to access", masked)
        # Erneutes Maskieren ändert nichts mehr (Idempotenz).
        self.assertEqual(mask(masked), masked)

    def test_clone_masks_embedded_credentials_in_its_message(self):
        """``clone`` gibt Fehlermeldungen von Git nur maskiert weiter; der
        Hinweis auf fehlende Zugangsdaten bleibt erhalten."""
        url = "https://nutzer:geheim@github.com/owner/repo.git"
        target = self.workspace / "maskprobe"

        with mock.patch.object(
            self.cli.vibe_github, "git",
            side_effect=lambda *_args, **_kwargs: (
                128,
                "fatal: unable to access '" + url + "/': could not read "
                "Username for 'https://github.com': Terminal prompts disabled",
            ),
        ) as standin:
            rc, message = self.cli.vibe_github.clone(url, target)

        standin.assert_called_once()
        self.assertNotEqual(rc, 0)
        self.assertNotIn("geheim", message)
        self.assertNotIn("nutzer:", message)
        self.assertIn("***@github.com", message)
        self.assertIn("Zugangsdaten", message)

    def test_clone_failure_without_a_live_service_leaks_no_credentials(self):
        """Echter Ausfallpfad (nur Loopback, kein externer Dienst): die
        Meldung trägt keine Zugangsdaten und es bleibt kein Zielordner."""
        url = "https://nutzer:geheim@127.0.0.1:1/owner/repo.git"
        target = self.workspace / "loopbackprobe"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertNotIn("geheim", message)
        self.assertNotIn("nutzer:", message)
        self.assertFalse(target.exists())


# ==================================================================== CLI
def write_cli_templates(install):
    """Vorlagen für Subprozessläufe: TPL liegt unter VIBE_INSTALL/templates."""
    write_template(install, "common", {
        "FEEDBACK.md": FEEDBACK_TEMPLATE,
        "TICKETS.md": TICKETS_TEMPLATE,
        "opencode.json": OPENCODE_JSON_TEMPLATE,
        ".opencode/agents/test-agent.md": TEST_AGENT_TEMPLATE,
    })
    write_template(install, "generic", {
        "AGENTS.md": "# AGENTS fuer {{NAME}}\n",
        ".vibe/project.env": (
            "TYPE=generic\n"
            "REVIEWER=" + LOKALE_REVIEWER + "\n"
            "TESTER=test-agent\n"
            "SANDBOX=" + LOKALE_SANDBOX + "\n"
            "VERIFY_QUICK=" + LOKALE_QUICK + "\n"
            "VERIFY_PACKAGE=" + LOKALE_PAKET + "\n"
            "VERIFY_FULL=" + LOKALE_FULL + "\n"
        ),
    })


class CommandLineTest(unittest.TestCase):
    """CLI ``vibe clone <url> [name]``: Erfolg meldet klar, Fehler bricht ab."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "ws"
        self.workspace.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        write_cli_templates(self.install / "templates")

    def isolated_env(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE": str(self.workspace),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
        })
        env.update(GIT_IDENTITY)
        return env

    def seed_bare(self, name, files):
        work = self.root / "seed" / name
        work.mkdir(parents=True)
        for relative, content in files.items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(work, "init", "-q", "-b", "main")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "seed")
        bare = self.root / "origin" / (name + ".git")
        bare.mkdir(parents=True)
        git(bare, "init", "-q", "--bare")
        git(work, "push", "-q", str(bare), "main")
        git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
        return "file://" + str(bare)

    def run_cli(self, *argv, env=None):
        return subprocess.run(
            [sys.executable, str(CLI), "clone", *argv],
            cwd=str(self.workspace), env=env or self.isolated_env(),
            capture_output=True, text=True, timeout=120, check=False,
        )

    def test_cli_clone_prints_a_summary_and_creates_the_project(self):
        url = self.seed_bare("scriptor", {"README.md": "Scriptor\n"})

        result = self.run_cli(url)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertIn("scriptor", output)
        self.assertTrue((self.workspace / "scriptor" / ".git").is_dir())
        env_text = (self.workspace / "scriptor" / ".vibe" / "project.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("TESTER=test-agent", env_text)

    def test_cli_clone_rejects_invalid_urls_and_existing_names(self):
        bad = self.run_cli("://kaputt")
        self.assertNotEqual(bad.returncode, 0)
        self.assertTrue((bad.stdout + bad.stderr).strip())

        url = self.seed_bare("ontoform", {"README.md": "ontoform\n"})
        existing = self.workspace / "belegt"
        (existing / ".vibe").mkdir(parents=True)
        (existing / ".git").mkdir()
        (existing / ".vibe" / "project.env").write_text("TYPE=generic\n",
                                                        encoding="utf-8")
        reused = self.run_cli(url, "belegt")
        self.assertNotEqual(reused.returncode, 0)
        self.assertIn("belegt", reused.stdout + reused.stderr)
        self.assertFalse((existing / "README.md").exists())
        self.assertFalse((self.workspace / "ontoform").exists())

    def test_cli_clone_reports_a_missing_git(self):
        url = self.seed_bare("ohnewerkzeug", {"README.md": "ohnewerkzeug\n"})
        empty_bin = self.root / "leck"
        empty_bin.mkdir()
        env = self.isolated_env()
        # Kein git im Suchpfad: nur ein leeres Verzeichnis statt PATH sperrt
        # git zuverlässig, ohne Unix-Rechte anzunehmen.
        env["PATH"] = str(empty_bin)

        result = self.run_cli(url, env=env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git", (result.stdout + result.stderr).lower())
        self.assertFalse((self.workspace / "ohnewerkzeug").exists())


if __name__ == "__main__":
    unittest.main()
