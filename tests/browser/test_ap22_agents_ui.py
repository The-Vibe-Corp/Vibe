"""Browserabnahme AP22, Meilenstein C: Agenten (Liste, Wizard, Ein-Seiten-Editor).

Die Fälle leiten sich aus ``docs/features/AP22.md`` ab — Abschnitt
„Agenten (nova-agents.js)“ sowie „Paritätsmatrix“ (``vibe agents`` /
``agent`` / ``model`` / ``project-agents``). Das echte Dashboard läuft als
eigener Prozess auf einem freien Loopback-Port mit isoliertem ``VIBE``/``HOME``
und einer opencode-Attrappe (Muster ``tests/browser/test_ap22_shell_ui.py``,
Agenten-Fixtures ``tests/browser/test_agents_ui.py``). Es gibt keine
Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Fachlicher Rahmen
-----------------
Die verwalteten Agenten sind Dateien unter
``~/.config/opencode/agents/<name>.md`` mit Frontmatter. Der Vertrag verlangt
für die neue Oberfläche:

* eine Liste ``div[data-nv-agent-list]`` mit ``article[data-nv-agent="<name>"]``
  (Rolle ``[data-nv-role]``, Modell, Beschreibung, ``is_vibe``-Badge,
  ungültig-Markierung, Neuanlage ``[data-nv-action="agent-new"]``),
* einen Wizard ``[data-nv-wizard]`` mit ``section[data-nv-step="1|2|3|4"]``
  (Name/Rolle, Modell, Prompt mit Vorlagenknopf, Prüfen & Anlegen),
* einen Ein-Seiten-Editor ``[data-nv-agent-editor]`` unter ``#/agents/<name>``
  mit allen strukturierten Feldern, Rohmodus, Sicherungen, Kopieren, Löschen,
  Speichern und Projektzuordnung ``[data-nv-assign="<projekt>"]``.

Abgeleitete DOM-Hooks (Test-Vertrag)
------------------------------------
Der Vertrag nennt nicht für jedes Feld einen Hook. Wo er nur das Muster
``data-nv-field``/``data-nv-action`` festschreibt, binden diese Tests an die
folgenden, hier verbindlich dokumentierten Namen:

===============================  ==========================================
Hook                             Bedeutung
===============================  ==========================================
``[data-nv-field="description"]``  Beschreibung (input)
``[data-nv-field="mode"]``         Modus (select: primary/subagent/all)
``[data-nv-field="model"]``        Modell (select)
``[data-nv-field="temperature"]``  Temperatur (input)
``[data-nv-field="steps"]``        maximale Schritte (input)
``[data-nv-field="permissions"]``  Rechte-Vorlage (select)
``[data-nv-field="prompt"]``       Prompt (textarea)
``[data-nv-assign-model="<p>"]``   Modell-Override je Projekt (select)
``[data-nv-action="agent-create"]``  Anlegen (Vertrag, Wizard Schritt 4)
``[data-nv-action="agent-save"]``    Speichern (Vertrag)
``[data-nv-action="agent-backup"]``  Sicherung anlegen (Vertrag)
``[data-nv-action="agent-restore"]`` Sicherung wiederherstellen (Vertrag)
``[data-nv-action="agent-copy"]``    Kopieren (Vertrag)
``[data-nv-action="agent-delete"]``  Löschen (Vertrag)
``[data-nv-raw"]``/``[data-nv-raw-text"]``  Rohmodus (Vertrag)
``[data-nv-assign="<projekt>"]``     Projektzuordnung, Schalter (Vertrag)
``article[data-nv-agent][data-nv-agent-scope="global|<projekt>"]``
                                    Geltungsbereich der Listenkarte
``[data-nv-agent-scope-badge]``      sichtbare Geltungsbereichs-Markierung
``[data-nv-agent-editor][data-nv-agent-scope="global|<projekt>"]``
                                    Geltungsbereich des Editors
``#/agents/<scope>/<name>``          Route des geltungsbereichsgenauen Editors
===============================  ==========================================

Der Rollen-Katalog des Wizard ist im Vertrag nur als „Rollen-Select aus
``/api/agents`` → ``roles``“ beschrieben. ``/api/agents`` liefert ``roles``
allerdings als Zuordnung *Agent → Rolle*, keinen Katalog; der Katalog ist
``bin/vibe`` ``ROLE_NAMES`` (coder, reviewer, vibe, tester, analyst,
sonstiges, content-creator). Der Test verlangt deshalb die fachlich
dokumentierten Rollen ``coder``, ``reviewer``, ``tester``, ``analyst``,
``content-creator`` und ``sonstiges`` (die englische Entsprechung von
„other“) — nicht die Reihenfolge und nicht die leere Option.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``ListTest.test_list_shows_agents_with_role_model_and_description``
``ListTest.test_list_marks_an_invalid_agent_file``
``WizardTest.test_wizard_has_four_steps_and_the_role_catalog``
``WizardTest.test_wizard_model_select_lists_connected_models``
``WizardTest.test_prompt_template_fills_the_prompt_field``
``WizardTest.test_create_adds_the_agent_file_and_the_list_card``
``WizardTest.test_missing_name_shows_a_form_error_and_writes_nothing``
``EditorTest.test_editor_shows_all_structured_fields_on_one_page``
``EditorTest.test_save_persists_the_description_across_reload``
``EditorTest.test_raw_mode_shows_frontmatter_and_saves_raw_text``
``EditorTest.test_raw_mode_conflict_shows_a_form_error_without_writing``
``EditorTest.test_backup_action_creates_a_backup_entry``
``EditorTest.test_restore_brings_back_the_previous_version``
``EditorTest.test_copy_creates_a_copy_that_appears_in_the_list``
``EditorTest.test_delete_removes_the_agent_file``
``AssignmentTest.test_project_toggle_and_model_override_are_saved``
``ProjectScopeTest.test_list_shows_scope_badges_for_same_named_agents``
``ProjectScopeTest.test_project_card_edit_opens_project_scoped_editor``
``ProjectScopeTest.test_save_project_agent_keeps_global_file_unchanged``
``ProjectScopeTest.test_card_delete_removes_project_agent_but_keeps_global``

Review-Fix AP22 (Runde 1)
-------------------------
Die vier ``ProjectScopeTest``-Fälle binden die Review-Feststellung
„projektbezogene Agenten bearbeiten“: Gleichnamige Agenten in ``global`` und
einem Projekt müssen in Liste und Editor über ihren Geltungsbereich
unterscheidbar sein; Speichern und Löschen dürfen ausschließlich die gemeinte
Datei treffen. Der Löschfall verlangt den Löschknopf
``[data-nv-action="agent-delete"]`` ausdrücklich **auf der Karte**
(Review-Befund 7). Die verbindlichen Hooks stehen in der Tabelle oben.
"""
import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\nopencode/schnell-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/vibe-modell
temperature: 0.1
steps: 5
permission:
  read: allow
  edit: deny
  task: allow
---

Globaler Prompt.
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

BROKEN_AGENT = """---
description: Defekter Agent
mode: quatsch
---

Defekter Prompt.
"""

# Review-Fix AP22: derselbe Name in beiden Geltungsbereichen mit
# unterschiedlicher Beschreibung. Der Editor darf niemals den globalen Agenten
# laden oder überschreiben, wenn der projektbezogene gemeint ist.
SHARED_GLOBAL_AGENT = """---
description: Globaler geteilter Agent
mode: subagent
model: opencode/vibe-modell
---

Globaler geteilter Prompt.
"""

SHARED_PROJECT_AGENT = """---
description: Projektgebundener Agent
mode: subagent
model: opencode/test-modell
---

Projektgebundener Prompt.
"""

CATALOG = {
    "schema": 2,
    "version": "2026-11-20.1",
    "stand": "2026-11-20",
    "waehrung": "USD",
    "einheit": "1 Mio. Tokens",
    "hinweis": "Testkatalog für die AP22-Agentenabnahme.",
    "quellen": [],
    "modelle": [
        {
            "id": "opencode/vibe-modell",
            "name": "Vibe Modell",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models", "datum": "2026-11-20"},
        }
    ],
}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Ap22AgentsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.state / "models.json").write_text(
            json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
        (cls.root / "tmp").mkdir()
        (cls.root / "tmux").mkdir()

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.root / "tmux"),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            try:
                os.killpg(cls.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self._reset_fixture()
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        # Bestätigungen (Löschen/Wiederherstellen) werden angenommen; ein
        # eigener Bestätigungsdialog ist im Vertrag nicht benannt.
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Fixture und Helfer ----------

    def _reset_fixture(self):
        """Schreibt die Agenten-Fixture neu und räumt Sicherungen auf."""
        for item in self.agents_dir.glob("*.md"):
            item.unlink()
        (self.agents_dir / "tester.md").write_text(
            GLOBAL_AGENT, encoding="utf-8")
        (self.agents_dir / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8")
        (self.agents_dir / "defekt.md").write_text(
            BROKEN_AGENT, encoding="utf-8")
        (self.agents_dir / "shared.md").write_text(
            SHARED_GLOBAL_AGENT, encoding="utf-8")
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe", "tester": "coder"}},
                       ensure_ascii=False), encoding="utf-8")
        backups = self.state / "agent-backups"
        if backups.exists():
            for item in sorted(backups.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        project_agents = self.project / ".opencode" / "agents"
        if project_agents.exists():
            for item in project_agents.glob("*.md"):
                item.unlink()
        project_agents.mkdir(parents=True, exist_ok=True)
        # Review-Fix AP22: gleicher Name wie der globale Agent, aber eigener
        # Geltungsbereich und eigene Beschreibung.
        (project_agents / "shared.md").write_text(
            SHARED_PROJECT_AGENT, encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_agents(self):
        self.boot()
        self.page.goto(self.base + "/#/agents")
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=25000)

    def open_editor(self, name="tester"):
        self.boot()
        self.page.goto(self.base + f"/#/agents/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)

    def open_scoped_editor(self, scope, name):
        """Öffnet den Editor eines Geltungsbereichs (Review-Fix AP22)."""
        self.boot()
        self.page.goto(self.base + f"/#/agents/{scope}/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=20000)

    def project_agent_file(self, name):
        return self.project / ".opencode" / "agents" / f"{name}.md"

    def open_wizard(self):
        """Öffnet die Agentenliste und stellt den Wizard sicher."""
        self.open_agents()
        wizard = self.page.locator("[data-nv-wizard]")
        if not (wizard.count() and wizard.first.is_visible()):
            self.page.locator("[data-nv-action='agent-new']").click()
        wizard.first.wait_for(state="visible", timeout=20000)
        return wizard.first

    def wizard_next(self):
        self.page.locator("[data-nv-wizard-next]").click()

    def goto_step(self, step):
        self.page.locator(
            f"[data-nv-wizard] section[data-nv-step='{step}']").wait_for(
                state="visible", timeout=15000)

    def card(self, name):
        return self.page.locator(f"article[data-nv-agent='{name}']")

    def visible_error(self, root):
        """True, wenn ein sichtbarer Formularfehler im Bereich steht."""
        errors = root.locator("[data-nv-form-error]")
        for index in range(errors.count()):
            if errors.nth(index).is_visible():
                return True
        return False

    def error_text(self, root):
        errors = root.locator("[data-nv-form-error]")
        for index in range(errors.count()):
            if errors.nth(index).is_visible():
                return (errors.nth(index).inner_text() or "").strip()
        return ""

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path);
              return await response.json();
            }""", path)

    def backup_files(self):
        folder = self.state / "agent-backups" / "global"
        if not folder.exists():
            return []
        return sorted(folder.glob("tester-*.md"))

    def click_confirm_if_shown(self, root):
        """Klickt einen sichtbaren „Ja/Bestätigen“-Knopf, falls vorhanden."""
        buttons = root.locator("button")
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if not button.is_visible():
                continue
            text = (button.inner_text() or "").strip()
            if re.match(r"(?i)^(ja|yes|bestätig|bestaetig|confirm|ok)\b", text):
                button.click()
                return True
        return False

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()


class ListTest(Ap22AgentsBrowserTest):
    def test_list_shows_agents_with_role_model_and_description(self):
        """Vorbedingung: globale Agenten ``tester`` (Rolle coder) und
        ``vibe-agent`` (Rolle vibe) liegen als Dateien vor.

        Aktion: ``#/agents`` öffnen. Erwartung: ``div[data-nv-agent-list]``
        mit je einer Karte ``article[data-nv-agent=…]``; ``tester`` zeigt
        Rolle ``[data-nv-role]`` = coder, Modell und Beschreibung; der
        ``is_vibe``-Agent ist als solcher erkennbar; der Neuanlage-Knopf
        ``[data-nv-action="agent-new"]`` existiert.
        """
        self.open_agents()
        self.assertEqual(
            1, self.page.locator("[data-nv-agent-list]").count(),
            "Die Agentenliste div[data-nv-agent-list] fehlt")
        tester = self.card("tester")
        tester.wait_for(state="visible", timeout=20000)

        role = tester.locator("[data-nv-role]")
        self.assertEqual(1, role.count(),
                         "Die Rollen-Markierung [data-nv-role] fehlt")
        self.assertEqual("coder", (role.inner_text() or "").strip().lower(),
                         "Die Rolle des Agenten tester wird nicht angezeigt")
        text = tester.inner_text()
        self.assertIn("opencode/vibe-modell", text,
                      "Das Modell des Agenten tester fehlt in der Karte")
        self.assertIn("Globaler Agent", text,
                      "Die Beschreibung des Agenten tester fehlt in der Karte")

        vibe = self.card("vibe-agent")
        self.assertEqual(1, vibe.count(), "Der Vibe-Agent fehlt in der Liste")
        self.assertRegex(
            vibe.inner_text(), r"(?i)vibe",
            "Der Vibe-Status ist an der Karte nicht erkennbar")

        self.assertEqual(
            1, self.page.locator("[data-nv-action='agent-new']").count(),
            "Der Neuanlage-Knopf [data-nv-action='agent-new'] fehlt")
        self.assert_clean_page()

    def test_list_marks_an_invalid_agent_file(self):
        """Vorbedingung: ``defekt.md`` hat einen ungültigen Modus
        (``mode: quatsch``) und ist damit fachlich ungültig.

        Aktion: Liste öffnen. Erwartung: Die Karte ``defekt`` existiert und
        trägt eine ungültig-Markierung (Text „ungültig“/„invalid“, da der
        Vertrag keinen eigenen Hook nennt).
        """
        self.open_agents()
        card = self.card("defekt")
        card.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            card.inner_text(), r"(?i)ungültig|ungueltig|invalid|defekt",
            "Die defekte Agentendatei ist nicht als ungültig markiert: "
            + card.inner_text())


class WizardTest(Ap22AgentsBrowserTest):
    def test_wizard_has_four_steps_and_the_role_catalog(self):
        """Vorbedingung: angemeldet. Aktion: Agentenansicht öffnen und
        (falls nötig) „Neuer Agent“ klicken.

        Erwartung: ``[data-nv-wizard]`` mit den vier Schritten; Schritt 1
        trägt Name ``[data-nv-field="name"]`` und Rollen-Select
        ``[data-nv-field="role"]``; der Katalog enthält die dokumentierten
        Rollen coder, reviewer, tester, analyst, content-creator, sonstiges.
        """
        wizard = self.open_wizard()
        for step in (1, 2, 3, 4):
            self.assertEqual(
                1, wizard.locator(f"section[data-nv-step='{step}']").count(),
                f"Wizard-Schritt {step} fehlt")
        self.goto_step(1)
        self.assertEqual(1, wizard.locator(
            "[data-nv-field='name']").count(),
            "Das Namensfeld des Wizards fehlt")
        role = wizard.locator("select[data-nv-field='role']")
        self.assertEqual(1, role.count(),
                         "Der Rollen-Select des Wizards fehlt")
        options = role.locator("option").evaluate_all(
            "nodes => nodes.map(node => node.value)")
        for expected in ("coder", "reviewer", "tester", "analyst",
                         "content-creator", "sonstiges"):
            self.assertIn(expected, options,
                          f"Die Rolle {expected!r} fehlt im Rollen-Select: "
                          + repr(options))

    def test_wizard_model_select_lists_connected_models(self):
        """Vorbedingung: die opencode-Attrappe meldet drei Modelle.

        Aktion: Wizard öffnen, Schritt 1 ausfüllen, weiter zu Schritt 2.
        Erwartung: die Modell-Combobox ``div[data-nv-combobox][data-nv-field="model"]``
        ist sichtbar und bietet nach dem Öffnen die gemeldeten Modelle
        (u. a. ``opencode/vibe-modell``) als Optionen an.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("modellprobe")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: das Modell ist eine Combobox (kein select); die Optionsliste
        # wird erst durch einen Klick auf das Eingabefeld geöffnet.
        model = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        model.wait_for(state="visible", timeout=15000)
        model.locator("input[data-nv-combobox-input]").click()
        options = model.locator("li[data-nv-combobox-option]").all_inner_texts()
        self.assertIn("opencode/vibe-modell", options,
                      "Die Modell-Combobox bietet die verbundenen Modelle "
                      "nicht an: " + repr(options))

    def test_prompt_template_fills_the_prompt_field(self):
        """Vorbedingung: Wizard mit Name und Beschreibung.

        Aktion: bis Schritt 4 navigieren, Vorlagenknopf
        ``[data-nv-action="prompt-template"]`` klicken. Erwartung: Das
        Prompt-Feld ``textarea[data-nv-field="prompt"]`` ist vorher leer und
        wird durch die Vorlage (POST ``/api/agent_template``) gefüllt; ein
        Hilfetext ist sichtbar; kein Formularfehler.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("vorlagenprobe")
        wizard.locator("[data-nv-field='description']").fill(
            "Prüft die Vorlage")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: Schritt 3 ist neu (Rechte); der Prompt steht in Schritt 4.
        self.wizard_next()
        self.goto_step(3)
        self.wizard_next()
        self.goto_step(4)
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.wait_for(state="visible", timeout=15000)
        self.assertEqual("", prompt.input_value(),
                         "Das Prompt-Feld ist vor der Vorlage nicht leer")
        helper = wizard.locator("[data-nv-step='4'] .nv-muted")
        self.assertTrue(
            helper.count() and helper.first.is_visible(),
            "Der Hilfetext zum Prompt fehlt in Schritt 4")
        wizard.locator("[data-nv-action='prompt-template']").click()
        self.wait_until(
            lambda: len(prompt.input_value().strip()) > 0,
            timeout=15000,
            message="Der Vorlagenknopf füllte das Prompt-Feld nicht")
        self.assertFalse(self.visible_error(wizard),
                         "Die Vorlage erzeugte einen Formularfehler")

    def test_create_adds_the_agent_file_and_the_list_card(self):
        """Vorbedingung: Wizard, kein Agent ``neuling``.

        Aktion: alle Schritte ausfüllen, Schritt 5 prüfen, „Anlegen“.
        Erwartung: ``~/.config/opencode/agents/neuling.md`` existiert mit
        Beschreibung und Prompt; die Liste zeigt eine Karte ``neuling``.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("neuling")
        wizard.locator("[data-nv-field='description']").fill(
            "Frischer Agent")
        wizard.locator("[data-nv-field='role']").select_option("coder")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: Modell als Combobox in Schritt 2; Auswahl über Eingabefeld
        # und Optionsliste statt select_option.
        model = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        model.locator("input[data-nv-combobox-input]").click()
        model.locator("li[data-nv-combobox-option]",
                      has_text="opencode/test-modell").first.click()
        self.assertEqual(
            "opencode/test-modell", model.get_attribute("data-nv-value"),
            "Die Modellauswahl wurde nicht übernommen")
        self.wizard_next()
        self.goto_step(3)
        # F33 WP2: Schritt 3 ist neu (Rechte); der vorgegebene Standard genügt.
        self.wizard_next()
        self.goto_step(4)
        wizard.locator("textarea[data-nv-field='prompt']").fill(
            "Arbeite sorgfältig.")
        self.wizard_next()
        self.goto_step(5)
        # F33 WP2: Prüfen & Anlegen ist Schritt 5 (statt 4).
        self.assertIn("neuling",
                      wizard.locator("[data-nv-step='5']").inner_text(),
                      "Die Prüfseite nennt den Agentennamen nicht")

        wizard.locator("[data-nv-action='agent-create']").click()
        target = self.agents_dir / "neuling.md"
        self.wait_until(target.exists, timeout=20000,
                        message="Der neue Agent wurde nicht geschrieben")
        text = target.read_text(encoding="utf-8")
        self.assertIn("description: Frischer Agent", text)
        self.assertIn("Arbeite sorgfältig.", text)

        # Das Ziel nach dem Anlegen ist im Vertrag nicht genannt: Die Karte
        # wird in der Liste geprüft; bleibt der Wizard stehen, wird die Liste
        # über die dokumentierte Route geöffnet.
        card = self.card("neuling")
        if not (card.count() and card.first.is_visible()):
            self.page.goto(self.base + "/#/agents")
        card.first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "coder",
            (card.first.locator("[data-nv-role]").inner_text() or "")
            .strip().lower(),
            "Die neue Karte zeigt die gewählte Rolle nicht")

    def test_missing_name_shows_a_form_error_and_writes_nothing(self):
        """Vorbedingung: Wizard, kein Name eingegeben.

        Aktion: Weiter/Anlegen ohne Namen versuchen. Erwartung: In der
        Wizard-Karte erscheint ein sichtbarer Formularfehler
        ``[data-nv-form-error]`` (Vertrag: jede Formular-Karte zeigt
        Validierungsfehler dort); es entsteht keine neue Agentendatei.
        """
        before = {item.name for item in self.agents_dir.glob("*.md")}
        wizard = self.open_wizard()
        self.goto_step(1)
        for _ in range(3):
            if self.visible_error(wizard):
                break
            self.wizard_next()
            self.page.wait_for_timeout(300)
        if not self.visible_error(wizard):
            create = wizard.locator("[data-nv-action='agent-create']")
            if create.count() and create.first.is_visible():
                create.first.click()
        self.wait_until(
            lambda: self.visible_error(wizard),
            timeout=15000,
            message="Ohne Namen erscheint kein Formularfehler")
        after = {item.name for item in self.agents_dir.glob("*.md")}
        self.assertEqual(before, after,
                         "Trotz fehlendem Namen wurde eine Agentendatei "
                         "geschrieben")


class EditorTest(Ap22AgentsBrowserTest):
    def test_editor_shows_all_structured_fields_on_one_page(self):
        """Vorbedingung: Agent ``tester`` liegt vor.

        Aktion: ``#/agents/tester`` öffnen. Erwartung:
        ``[data-nv-agent-editor]`` enthält Beschreibung, Modus, Modell,
        Temperatur, Schritte, Rechte und Prompt — alle auf einer Seite; der
        Prompt ist ein Textfeld (textarea). Die Hooks sind im Moduldocstring
        dokumentiert.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        expected = {
            "description": "input",
            "mode": "select",
            "model": "select",
            "temperature": "input",
            "steps": "input",
            "permissions": "select",
            "prompt": "textarea",
        }
        for field, tag in expected.items():
            locator = editor.locator(f"{tag}[data-nv-field='{field}']")
            self.assertEqual(
                1, locator.count(),
                f"Das Feld {field!r} fehlt als {tag} im Ein-Seiten-Editor")
            self.assertTrue(locator.is_visible(),
                            f"Das Feld {field!r} ist nicht sichtbar")
        self.assertEqual(
            "0.1", editor.locator(
                "input[data-nv-field='temperature']").input_value(),
            "Der Editor zeigt die gespeicherte Temperatur nicht")
        self.assertIn(
            "Globaler Prompt.",
            editor.locator("textarea[data-nv-field='prompt']").input_value(),
            "Der Editor zeigt den Prompt nicht")

    def test_save_persists_the_description_across_reload(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: Beschreibung ändern, ``agent-save`` klicken, Seite neu laden.
        Erwartung: Die Datei enthält die neue Beschreibung; nach dem Reload
        zeigt das Feld den neuen Wert.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        field = editor.locator("input[data-nv-field='description']")
        field.fill("Geänderte Beschreibung")
        editor.locator("[data-nv-action='agent-save']").click()
        target = self.agents_dir / "tester.md"
        self.wait_until(
            lambda: "Geänderte Beschreibung" in target.read_text(
                encoding="utf-8"),
            timeout=20000,
            message="Die geänderte Beschreibung wurde nicht gespeichert")
        self.assertFalse(self.visible_error(editor),
                         "Das Speichern meldete einen Formularfehler")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "Geänderte Beschreibung",
            self.page.locator(
                "[data-nv-agent-editor] input[data-nv-field='description']"
            ).input_value(),
            "Nach dem Reload zeigt der Editor nicht die gespeicherte "
            "Beschreibung")

    def test_raw_mode_shows_frontmatter_and_saves_raw_text(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: ``[data-nv-raw]`` aktivieren, Rohtext ansehen und ergänzen,
        speichern. Erwartung: ``textarea[data-nv-raw-text]`` zeigt den
        vollständigen Text mit ``---``-Frontmatter; die Rohtext-Änderung
        landet in der Datei, ohne Formularfehler.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-raw]").click()
        raw = editor.locator("textarea[data-nv-raw-text]")
        raw.wait_for(state="visible", timeout=15000)
        text = raw.input_value()
        self.assertTrue(text.startswith("---"),
                        "Der Rohmodus zeigt kein Frontmatter: " + text[:60])
        self.assertIn("description: Globaler Agent", text)

        raw.fill(text.rstrip() + "\nZusatz aus dem Rohtext.\n")
        editor.locator("[data-nv-action='agent-save']").click()
        target = self.agents_dir / "tester.md"
        self.wait_until(
            lambda: "Zusatz aus dem Rohtext." in target.read_text(
                encoding="utf-8"),
            timeout=20000,
            message="Der geänderte Rohtext wurde nicht gespeichert")
        self.assertFalse(self.visible_error(editor),
                         "Der unveränderte Digest erzeugte einen Konflikt")

    def test_raw_mode_conflict_shows_a_form_error_without_writing(self):
        """Vorbedingung: Editor ``tester`` im Rohmodus, Datei wurde danach
        außerhalb der Oberfläche verändert (abweichender Digest).

        Aktion: Rohtext bearbeiten und speichern. Erwartung: Der Server
        lehnt den veralteten Stand ab (Bestand: Digest-Konflikt); die
        Oberfläche zeigt ``[data-nv-form-error]``; die externe Änderung
        bleibt erhalten (nichts wird überschrieben).
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-raw]").click()
        raw = editor.locator("textarea[data-nv-raw-text]")
        raw.wait_for(state="visible", timeout=15000)

        external = (GLOBAL_AGENT
                    .replace("Globaler Agent", "Extern geändert")
                    .replace("Globaler Prompt.", "Externer Prompt."))
        (self.agents_dir / "tester.md").write_text(external, encoding="utf-8")

        raw.fill(raw.input_value().rstrip() + "\nÄnderung aus der Oberfläche.\n")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(
            lambda: self.visible_error(editor),
            timeout=20000,
            message="Der Digest-Konflikt wird nicht als Formularfehler "
                    "angezeigt")
        self.assertIn(
            "Externer Prompt.",
            (self.agents_dir / "tester.md").read_text(encoding="utf-8"),
            "Der Konflikt überschrieb trotzdem die externe Änderung")

    def test_backup_action_creates_a_backup_entry(self):
        """Vorbedingung: Agent ``tester`` ohne Sicherungen.

        Aktion: ``[data-nv-action="agent-backup"]`` klicken. Erwartung: Im
        Sicherungsordner ``<state>/agent-backups/global`` entsteht eine
        Sicherung des Agenten (Bestandsablage der API).
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        before = len(self.backup_files())
        editor.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: len(self.backup_files()) > before,
            timeout=20000,
            message="Die Sicherung wurde nicht angelegt")
        newest = self.backup_files()[-1].read_text(encoding="utf-8")
        self.assertIn("Globaler Agent", newest,
                      "Die Sicherung enthält nicht den Agentenstand")

    def test_restore_brings_back_the_previous_version(self):
        """Vorbedingung: Agent ``tester``.

        Aktion: Beschreibung ändern und speichern (legt eine Sicherung an),
        erneut ändern und speichern, dann
        ``[data-nv-action="agent-restore"]`` ausführen (Bestätigung wird
        angenommen). Erwartung: Die Datei enthält wieder den vorherigen
        Stand; nach dem Reload zeigt der Editor ihn an.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        field = editor.locator("input[data-nv-field='description']")
        target = self.agents_dir / "tester.md"

        field.fill("Erste Fassung")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(lambda: "Erste Fassung" in target.read_text(
            encoding="utf-8"), timeout=20000,
            message="Die erste Fassung wurde nicht gespeichert")

        field.fill("Zweite Fassung")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(lambda: "Zweite Fassung" in target.read_text(
            encoding="utf-8"), timeout=20000,
            message="Die zweite Fassung wurde nicht gespeichert")

        editor.locator("[data-nv-action='agent-restore']").click()
        self.page.wait_for_timeout(300)
        self.click_confirm_if_shown(self.page.locator("[data-nv-agent-editor]"))
        self.wait_until(
            lambda: "Erste Fassung" in target.read_text(encoding="utf-8"),
            timeout=20000,
            message="Die Sicherung wurde nicht wiederhergestellt")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "Erste Fassung",
            self.page.locator(
                "[data-nv-agent-editor] input[data-nv-field='description']"
            ).input_value(),
            "Der Editor zeigt nach der Wiederherstellung nicht den "
            "Sicherungsstand")

    def test_copy_creates_a_copy_that_appears_in_the_list(self):
        """Vorbedingung: Agent ``tester`` (global).

        Aktion: Im Editor ``[data-nv-action="agent-copy"]`` ausführen
        (etwaige Bestätigung/Zielauswahl wird bedient). Erwartung: Über
        ``GET /api/agents`` erscheint ein weiterer Eintrag; die Liste zeigt
        für ``tester`` mindestens zwei Karten (global + Kopie im Projekt).

        Der Vertrag nennt weder Zielbereich noch Namen der Kopie; die API
        kopiert in einen anderen Geltungsbereich unter demselben Namen. Der
        Test akzeptiert daher dieselbe Karte (zweiter Geltungsbereich) wie
        auch einen abgeleiteten Namen ``tester-…``.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        before = len(self.api_json("/api/agents").get("agents") or [])

        editor.locator("[data-nv-action='agent-copy']").click()
        self.page.wait_for_timeout(300)
        dialogs = self.page.locator("[data-nv-agent-editor] select")
        for index in range(dialogs.count()):
            select = dialogs.nth(index)
            options = select.locator("option").evaluate_all(
                "nodes => nodes.map(node => node.value)")
            if "proj" in options:
                select.select_option("proj")
        self.click_confirm_if_shown(editor)

        self.wait_until(
            lambda: len(self.api_json("/api/agents").get("agents") or [])
            > before,
            timeout=20000,
            message="Das Kopieren legte keinen weiteren Agenten an")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        names = self.page.locator(
            "[data-nv-agent-list] article[data-nv-agent]").evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-nv-agent'))")
        copies = [name for name in names if name == "tester"
                  or name.startswith("tester-")]
        self.assertGreaterEqual(
            len(copies), 2,
            "Die Kopie erscheint nicht als eigene Karte in der Liste: "
            + repr(names))

    def test_delete_removes_the_agent_file(self):
        """Vorbedingung: Agent ``tester``.

        Aktion: ``[data-nv-action="agent-delete"]`` klicken; eine etwaige
        native Bestätigung wird angenommen. Erwartung: Die Agentendatei ist
        entfernt (die API legt vorher eine Sicherung an), die Karte
        verschwindet aus der Liste.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        target = self.agents_dir / "tester.md"
        editor.locator("[data-nv-action='agent-delete']").click()
        self.page.wait_for_timeout(300)
        self.click_confirm_if_shown(editor)
        self.wait_until(lambda: not target.exists(), timeout=20000,
                        message="Der Agent wurde nicht gelöscht")
        self.assertTrue(self.backup_files(),
                        "Beim Löschen wurde keine Sicherung angelegt")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(0, self.card("tester").count(),
                         "Die gelöschte Karte steht weiterhin in der Liste")


class AssignmentTest(Ap22AgentsBrowserTest):
    def test_project_toggle_and_model_override_are_saved(self):
        """Vorbedingung: Projekt ``proj`` (generic), Agent ``tester`` noch
        nicht zugeordnet.

        Aktion: Im Editor den Schalter ``[data-nv-assign="proj"]`` aktivieren,
        im Modell-Override ``div[data-nv-assign-model="proj"]`` ein Modell
        wählen und speichern. Erwartung: ``GET /api/project-agents?name=proj``
        führt ``tester`` als gewählt (``selected``) und mit
        ``override=opencode/test-modell``; nach dem Reload sind Schalter und
        Override weiterhin gesetzt. Die Zuordnungen liegen vertragsgemäß im
        standardmäßig geschlossenen ``details[data-nv-assignments]`` und
        werden beim Aufklappen nachgeladen.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        # F33 WP2: Zuordnungen erst beim Aufklappen laden (Vertrag).
        details = editor.locator("details[data-nv-assignments]")
        details.locator("summary").click()
        toggle = editor.locator("[data-nv-assign='proj']")
        toggle.wait_for(state="visible", timeout=15000)
        if not toggle.is_checked():
            toggle.check()
        # F33 WP2: der Override ist eine Combobox (kein select).
        override = editor.locator(
            "div[data-nv-combobox][data-nv-assign-model='proj']")
        override.wait_for(state="visible", timeout=15000)
        override.locator("input[data-nv-combobox-input]").click()
        override.locator("li[data-nv-combobox-option]",
                         has_text="opencode/test-modell").first.click()
        self.assertEqual(
            "opencode/test-modell", override.get_attribute("data-nv-value"),
            "Die Modellüberschreibung wurde nicht übernommen")
        editor.locator("[data-nv-action='agent-save']").click()

        def assigned():
            data = self.api_json("/api/project-agents?name=proj")
            rows = {row.get("name"): row for row in data.get("agents") or []}
            row = rows.get("tester") or {}
            return row.get("selected") is True and row.get(
                "override") == "opencode/test-modell"

        self.wait_until(assigned, timeout=20000,
                        message="Die Projektzuordnung wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        editor = self.page.locator("[data-nv-agent-editor]")
        # F33 WP2: nach dem Reload ist das details wieder geschlossen.
        editor.locator("details[data-nv-assignments] summary").click()
        toggle = editor.locator("[data-nv-assign='proj']")
        toggle.wait_for(state="visible", timeout=15000)
        self.assertTrue(
            toggle.is_checked(),
            "Nach dem Reload ist der Projekt-Schalter nicht mehr gesetzt")
        override = editor.locator(
            "div[data-nv-combobox][data-nv-assign-model='proj']")
        override.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "opencode/test-modell", override.get_attribute("data-nv-value"),
            "Nach dem Reload fehlt die Modellüberschreibung")


class ProjectScopeTest(Ap22AgentsBrowserTest):
    """Review-Fix AP22: Projekt-Agenten sind nicht die globalen Agenten.

    ``shared`` liegt bewusst zweimal vor — global und projektbezogen in
    ``proj`` — und trägt unterschiedliche Beschreibungen. Die Oberfläche muss
    beide Karten unterscheidbar machen, beim Bearbeiten den richtigen
    Geltungsbereich adressieren und beim Speichern/Löschen ausschließlich die
    gemeinte Datei verändern.
    """

    def test_list_shows_scope_badges_for_same_named_agents(self):
        """Vorbedingung: ``shared`` existiert global und in Projekt ``proj``
        mit unterschiedlicher Beschreibung.

        Aktion: ``#/agents`` öffnen. Erwartung: Je eine Karte
        ``article[data-nv-agent="shared"]`` mit
        ``data-nv-agent-scope="global"`` bzw. ``"proj"``; jede Karte trägt
        genau eine Geltungsbereichs-Markierung
        ``[data-nv-agent-scope-badge]`` (global vs. Projekt) und die eigene
        Beschreibung.
        """
        self.open_agents()
        global_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='global']")
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")

        def both_scoped():
            return (global_card.count() == 1 and project_card.count() == 1
                    and global_card.first.is_visible()
                    and project_card.first.is_visible())

        self.wait_until(
            both_scoped, timeout=20,
            message="Gleichnamige globale und projektbezogene Agenten sind "
                    "in der Liste nicht über ihren Geltungsbereich "
                    "unterscheidbar")

        global_badge = global_card.locator("[data-nv-agent-scope-badge]")
        project_badge = project_card.locator("[data-nv-agent-scope-badge]")
        self.assertEqual(
            1, global_badge.count(),
            "Der globalen Karte fehlt die Geltungsbereichs-Markierung")
        self.assertEqual(
            1, project_badge.count(),
            "Der projektbezogenen Karte fehlt die "
            "Geltungsbereichs-Markierung")
        self.assertRegex(
            (global_badge.inner_text() or "").strip(), r"(?i)global",
            "Die globale Karte ist nicht als global markiert")
        self.assertRegex(
            (project_badge.inner_text() or "").strip(),
            r"(?i)proj|projekt",
            "Die projektbezogene Karte ist nicht als Projekt-Agent markiert")

        self.assertIn(
            "Globaler geteilter Agent", global_card.inner_text(),
            "Die globale Karte zeigt nicht die globale Beschreibung")
        self.assertIn(
            "Projektgebundener Agent", project_card.inner_text(),
            "Die projektbezogene Karte zeigt nicht die "
            "projektbezogene Beschreibung")

    def test_project_card_edit_opens_project_scoped_editor(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Auf der projektbezogenen Karte
        ``[data-nv-action="agent-edit"]`` klicken. Erwartung: Die Route ist
        ``#/agents/proj/shared``, der Editor trägt
        ``data-nv-agent-scope="proj"`` und zeigt die projektbezogene
        Beschreibung sowie das projektbezogene Modell — nicht den globalen
        Agenten.
        """
        self.open_agents()
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")
        self.wait_until(
            lambda: project_card.count() == 1,
            timeout=20,
            message="Die projektbezogene Karte des Agenten shared fehlt")
        project_card.locator("[data-nv-action='agent-edit']").click()

        self.wait_until(
            lambda: self.page.url.endswith("#/agents/proj/shared"),
            timeout=20,
            message="Der Projekt-Agent wird nicht über den "
                    "projektbezogenen Pfad geöffnet: " + self.page.url)
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "proj", editor.get_attribute("data-nv-agent-scope"),
            "Der Editor weist den projektbezogenen Geltungsbereich nicht aus")
        self.assertEqual(
            "Projektgebundener Agent",
            editor.locator(
                "input[data-nv-field='description']").input_value(),
            "Der Editor zeigt die Beschreibung des globalen Agenten statt "
            "der projektbezogenen")
        self.assertEqual(
            "opencode/test-modell",
            editor.locator("select[data-nv-field='model']").input_value(),
            "Der Editor zeigt das Modell des globalen Agenten statt des "
            "projektbezogenen")
        self.assertIn(
            "Projektgebundener Prompt.",
            editor.locator("textarea[data-nv-field='prompt']").input_value(),
            "Der Editor zeigt den globalen Prompt statt des "
            "projektbezogenen")

    def test_save_project_agent_keeps_global_file_unchanged(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Projekt-Editor ``#/agents/proj/shared`` öffnen, Beschreibung
        auf ``Projekt geändert`` setzen und speichern. Erwartung: Nur
        ``proj/.opencode/agents/shared.md`` ändert sich; die globale Datei
        ``~/.config/opencode/agents/shared.md`` bleibt byte-gleich.
        """
        self.open_scoped_editor("proj", "shared")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("input[data-nv-field='description']").fill(
            "Projekt geändert")
        editor.locator("[data-nv-action='agent-save']").click()

        project_file = self.project_agent_file("shared")
        global_file = self.agents_dir / "shared.md"
        self.wait_until(
            lambda: "Projekt geändert" in project_file.read_text(
                encoding="utf-8"),
            timeout=20,
            message="Die Änderung wurde nicht in die projektbezogene "
                    "Agentendatei geschrieben")
        self.assertEqual(
            SHARED_GLOBAL_AGENT, global_file.read_text(encoding="utf-8"),
            "Das Speichern des Projekt-Agenten überschrieb die globale "
            "Agentendatei")
        project_text = project_file.read_text(encoding="utf-8")
        self.assertIn(
            "Projektgebundener Prompt.", project_text,
            "Die projektbezogene Agentendatei wurde nicht gezielt geändert")
        self.assertNotIn(
            "Globaler geteilter Prompt.", project_text,
            "Die projektbezogene Datei enthält den globalen Prompt")

    def test_card_delete_removes_project_agent_but_keeps_global(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Auf der projektbezogenen Karte
        ``article[data-nv-agent="shared"][data-nv-agent-scope="proj"]``
        ``[data-nv-action="agent-delete"]`` ausführen (Dialog oder inline
        angebotene Bestätigung wird angenommen). Erwartung: Der Löschknopf
        liegt auf der Karte (Review-Befund 7); nur die projektbezogene Datei
        ist entfernt, die globale bleibt bestehen; die Liste zeigt danach nur
        noch die globale Karte ``data-nv-agent-scope="global"``.
        """
        self.open_agents()
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")
        self.wait_until(
            lambda: project_card.count() == 1,
            timeout=20,
            message="Die projektbezogene Karte des Agenten shared fehlt")
        delete = project_card.locator("[data-nv-action='agent-delete']")
        self.assertEqual(
            1, delete.count(),
            "Die Agentenkarte bietet keinen Löschknopf "
            "[data-nv-action='agent-delete']")
        project_file = self.project_agent_file("shared")
        global_file = self.agents_dir / "shared.md"
        delete.first.click()
        self.page.wait_for_timeout(300)
        # Der Bestätigungsweg ist nicht vorgeschrieben: Dialog (wird in
        # setUp angenommen) oder sichtbarer Inline-Knopf in Karte/Seite.
        for root in (project_card, self.page.locator("[data-nv-confirm]"),
                     self.page.locator("[role='dialog']"), self.page):
            if self.click_confirm_if_shown(root):
                break
        self.wait_until(
            lambda: not project_file.exists(), timeout=20,
            message="Der Projekt-Agent wurde nicht gelöscht")
        self.assertTrue(
            global_file.exists(),
            "Das Löschen des Projekt-Agenten entfernte die globale Datei")
        self.assertEqual(
            SHARED_GLOBAL_AGENT, global_file.read_text(encoding="utf-8"),
            "Das Löschen des Projekt-Agenten veränderte die globale Datei")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator(
                "article[data-nv-agent='shared']"
                "[data-nv-agent-scope='global']").count(),
            "Nach dem Löschen fehlt die globale Karte des Agenten shared")
        self.assertEqual(
            0, self.page.locator(
                "article[data-nv-agent='shared']"
                "[data-nv-agent-scope='proj']").count(),
            "Die gelöschte projektbezogene Karte steht weiterhin in der "
            "Liste")


if __name__ == "__main__":
    unittest.main()
