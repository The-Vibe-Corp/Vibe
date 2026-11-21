"""Browserabnahme F33 WP2: Combobox, Agentenliste, Wizard und Editor.

Die Fälle leiten sich aus ``docs/features/F33.md`` ab — Abschnitt
„Dom-Hook-Vertrag → WP2“ und „Nutzerentscheidungen“. Geprüft werden die dort
verbindlich vereinbarten ``data-nv-*``-Hooks und aria-Attribute; sichtbare
Texte nur dort, wo der Vertrag sie festlegt (Schrittzähler, Modus-Optionen,
Rohtext-Beschriftung, Sicherungs-Meldung).

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``, einem registrierten Projekt, globalen und
projektbezogenen Agentendateien sowie einer opencode-Attrappe
(``tests/browser/test_ap22_agents_ui.py`` als Muster). Es gibt keine
Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Fachlicher Rahmen
-----------------
* **Combobox (2d):** ``NV.combobox(values, current, opts)`` liefert
  ``div[data-nv-combobox][data-nv-field]`` mit
  ``input[data-nv-combobox-input]`` und ``ul[data-nv-combobox-list]``;
  Teilstringsuche case-insensitiv, Pfeiltasten + Enter wählen, Esc schließt,
  der Wert steht in ``data-nv-value``.
* **Agentenliste (2c/2h/2i):** Anpinnen über
  ``button[data-nv-action="agent-pin"]`` nach
  ``section[data-nv-pinned-agents]`` (``localStorage['nv-pinned-agents']`` als
  ``[{"scope","name"}]``), Suche ``input[data-nv-agent-search]``, Tag-Filter
  ``div[data-nv-agent-tag-filters]`` mit ``button[data-nv-tag-filter]``;
  ``h3.nv-agent-name`` und ``div[data-nv-agent-tags]`` liegen in getrennten
  Zeilen (keine Überblendung).
* **Wizard (2e/2f/2g):** fünf Schritte, Indikator „Schritt {{n}} von 5“;
  Einsatzart ``select[data-nv-field="mode"]`` mit erklärtem ``all`` = „Agent“;
  ``primary`` entfällt, sobald ein Primäragent existiert; Schritt 3 Rechte
  (``select[data-nv-field="perm"]`` + ``p[data-nv-perm-help]``); Schritt 4
  großer Prompt; Schritt 5 strukturierte Felder genau einmal, Prompt nur als
  ``pre[data-nv-review-prompt]``, Anlegen ohne Scrollen, kein toter
  „Weiter“-Knopf, Abbrechen mit Inline-Warnung.
* **Editor (2j/2k):** Projektzuordnungen erst beim Aufklappen von
  ``details[data-nv-assignments]`` (kein vorheriger
  ``/api/project-agents``-Abruf), ``button[data-nv-action="agent-back"]`` mit
  ``nv-secondary``, Rohtext-Umschalter mit dynamischer Beschriftung und
  Speichermodus ``data-nv-mode``, Hinweis ``p[data-nv-save-hint]``,
  Kopier-Bestätigung mit Ziel, Sicherungs-Toast „Sicherung angelegt“ ohne
  Versionswarnung, Wiederherstellungs-Info ``span[data-nv-backup-info]``.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ComboboxWidgetTest.test_combobox_opens_filters_selects_and_closes``
``AgentListTest.test_pinning_moves_agent_to_pinned_section_and_persists``
``AgentListTest.test_search_filters_agent_cards_live``
``AgentListTest.test_tag_filter_toggles_cards``
``AgentListTest.test_name_and_tags_are_separate_rows``
``WizardTest.test_wizard_has_five_steps_and_step_indicator``
``WizardTest.test_step_two_explains_modes_and_names_all_as_agent``
``WizardTest.test_mode_help_updates_with_the_selection``
``WizardTest.test_primary_option_exists_without_a_primary_agent``
``WizardTest.test_primary_option_is_hidden_when_a_primary_agent_exists``
``WizardTest.test_step_three_offers_permissions_and_uses_the_choice``
``WizardTest.test_step_four_prompt_is_large``
``WizardTest.test_step_five_lists_fields_once_and_formats_the_prompt``
``WizardTest.test_create_is_reachable_without_scrolling_on_step_five``
``WizardTest.test_cancel_warns_inline_before_discarding``
``EditorTest.test_assignments_are_loaded_only_after_expanding``
``EditorTest.test_back_button_is_secondary_and_returns_to_list``
``EditorTest.test_raw_toggle_changes_label_and_save_mode``
``EditorTest.test_copy_confirmation_names_the_target``
``EditorTest.test_backup_toast_says_backup_created_without_version_warning``
``EditorTest.test_restore_shows_the_last_backup_info``

ROT-PHASE (2026-11-21, vor der Implementierung von WP2)
------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f33_agents_ui.py' -v

Ergebnis: 21 Fälle, 20 rot (10 ``AssertionError`` = Verhalten fehlt,
10 ``playwright TimeoutError`` = DOM-Hook fehlt), 1 grün (Verhalten
existiert bereits, siehe unten). Kein Fall scheiterte aus
Umgebungsgründen (Server, Port, Browser, Syntax).

* ``test_combobox_opens_filters_selects_and_closes`` — AssertionError:
  ``NV.combobox`` ist nicht verfügbar.
* ``test_pinning_moves_agent_to_pinned_section_and_persists`` —
  AssertionError: ``[data-nv-action='agent-pin']`` fehlt an der Karte.
* ``test_search_filters_agent_cards_live`` — TimeoutError:
  ``input[data-nv-agent-search]`` fehlt.
* ``test_tag_filter_toggles_cards`` — TimeoutError:
  ``div[data-nv-agent-tag-filters]`` fehlt.
* ``test_name_and_tags_are_separate_rows`` — AssertionError:
  ``div[data-nv-agent-tags]`` fehlt (Tags stehen inline).
* ``test_wizard_has_five_steps_and_step_indicator`` — AssertionError:
  Wizard-Schritt 5 fehlt (bisher vier Schritte).
* ``test_step_two_explains_modes_and_names_all_as_agent`` —
  AssertionError: die Option ``subagent`` ist nicht erklärt (nur der
  Wert, keine Erläuterung).
* ``test_mode_help_updates_with_the_selection`` — TimeoutError:
  ``p[data-nv-mode-help]`` fehlt.
* ``test_primary_option_exists_without_a_primary_agent`` — **grün**:
  die Option ``primary`` existiert bereits im Modus-Select des
  AP22-Wizards. Der Fall kann daher nicht rot sein; er bleibt als
  Regressionsschutz (die Option darf nicht verschwinden).
* ``test_primary_option_is_hidden_when_a_primary_agent_exists`` —
  AssertionError: ``primary`` bleibt trotz vorhandenem Primäragenten in
  der Auswahl (``['subagent', 'primary', 'all']``).
* ``test_step_three_offers_permissions_and_uses_the_choice`` —
  TimeoutError: ``select[data-nv-field='perm']`` fehlt (Schritt 3 ist
  bisher der Prompt).
* ``test_step_four_prompt_is_large`` — TimeoutError:
  ``textarea[data-nv-field='prompt']`` fehlt im Schritt-4-Zustand.
* ``test_step_five_lists_fields_once_and_formats_the_prompt`` —
  TimeoutError: Schritt 5 fehlt, daher kein Prompt-Feld erreichbar.
* ``test_create_is_reachable_without_scrolling_on_step_five`` —
  TimeoutError: Schritt 5 fehlt, daher kein Prompt-Feld erreichbar.
* ``test_cancel_warns_inline_before_discarding`` — TimeoutError:
  ``div[data-nv-wizard-cancel-confirm]`` fehlt.
* ``test_assignments_are_loaded_only_after_expanding`` —
  AssertionError: der Editor lädt Projektzuordnungen bereits beim
  Rendern (vor dem Aufklappen).
* ``test_back_button_is_secondary_and_returns_to_list`` — TimeoutError:
  ``button[data-nv-action='agent-back']`` fehlt.
* ``test_raw_toggle_changes_label_and_save_mode`` — TimeoutError:
  ``p[data-nv-save-hint]`` fehlt.
* ``test_copy_confirmation_names_the_target`` — AssertionError: die
  Kopier-Bestätigung nennt das Ziel nicht deutlich (nur allgemeiner
  Editor-Text).
* ``test_backup_toast_says_backup_created_without_version_warning`` —
  AssertionError: der Toast meldet „Saved“ statt „Sicherung angelegt“.
* ``test_restore_shows_the_last_backup_info`` — AssertionError: schon
  die Vorbedingung (Sicherung anlegen) meldet „Saved“ statt
  „Sicherung angelegt“, daher fehlt ``span[data-nv-backup-info]``.
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
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

SECOND_AGENT = """---
description: Zweiter Agent
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Zweiter Prompt.
"""

BROKEN_AGENT = """---
description: Defekter Agent
mode: quatsch
---

Defekter Prompt.
"""

PROJECT_AGENT = """---
description: Projektgebundener Agent
mode: subagent
model: opencode/schnell-modell
permission:
  read: allow
  edit: deny
---

Projekt-Prompt.
"""

PRIMARY_AGENT = """---
description: Primaeragent Test
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Steuert die anderen Agenten.
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class F33AgentsTest(unittest.TestCase):
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

    def setUp(self):
        self._reset_fixture()
        self.post_language("en")
        self.page_errors = []
        self.requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("request",
                     lambda request: self.requests.append(request.url))

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
        (self.agents_dir / "zweiter.md").write_text(
            SECOND_AGENT, encoding="utf-8")
        (self.agents_dir / "defekt.md").write_text(
            BROKEN_AGENT, encoding="utf-8")
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"tester": "coder"}},
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
        project_agents.mkdir(parents=True, exist_ok=True)
        for item in project_agents.glob("*.md"):
            item.unlink()
        (project_agents / "projhelfer.md").write_text(
            PROJECT_AGENT, encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            conn.getresponse().read()
        finally:
            conn.close()

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

    def create_primary_agent(self, name="chief"):
        status, data = self.post_json("/api/agent", {
            "action": "save",
            "scope": "global",
            "name": name,
            "text": PRIMARY_AGENT,
            "create": True,
        })
        self.assertEqual(200, status,
                         "Der Test konnte keinen Primäragenten anlegen")
        self.assertTrue(data.get("ok"),
                        "Der Test konnte keinen Primäragenten anlegen: "
                        + repr(data))

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_agents(self):
        self.boot()
        self.page.goto(self.base + "/#/agents")
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)

    def open_editor(self, name="tester"):
        self.boot()
        self.page.goto(self.base + f"/#/agents/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)

    def open_wizard(self):
        self.open_agents()
        wizard = self.page.locator("[data-nv-wizard]")
        if not (wizard.count() and wizard.first.is_visible()):
            self.page.locator("[data-nv-action='agent-new']").click()
        wizard.first.wait_for(state="visible", timeout=20000)
        return wizard.first

    def wizard_goto(self, step, name="wizardprobe"):
        """Öffnet den Wizard, füllt den Namen und geht bis ``step``."""
        wizard = self.open_wizard()
        wizard.locator("[data-nv-field='name']").fill(name)
        for _ in range(step - 1):
            self.page.locator("[data-nv-wizard-next]").click()
            self.page.wait_for_timeout(150)
        wizard.locator(f"section[data-nv-step='{step}']").wait_for(
            state="visible", timeout=15000)
        return wizard

    def card(self, name, scope=None):
        selector = f"article[data-nv-agent='{name}']"
        if scope:
            selector += f"[data-nv-agent-scope='{scope}']"
        return self.page.locator(selector)

    def select_options(self, select):
        return select.locator("option").evaluate_all(
            "nodes => nodes.map(n => [n.value, (n.textContent || '').trim()])")

    def toast_text(self):
        nodes = self.page.locator("#nv-toasts .nv-toast")
        return "\n".join(nodes.all_inner_texts())

    def backup_files(self):
        folder = self.state / "agent-backups" / "global"
        if not folder.exists():
            return []
        return sorted(folder.glob("tester-*.md"))

    def confirmation_text(self):
        """Sichtbarer Bestätigungstext; fällt auf den Editor zurück."""
        for selector in ("[data-nv-confirm]:visible", "[role='dialog']:visible"):
            nodes = self.page.locator(selector)
            if nodes.count():
                return nodes.first.inner_text()
        return self.page.locator("[data-nv-agent-editor]").inner_text()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class ComboboxWidgetTest(F33AgentsTest):
    def test_combobox_opens_filters_selects_and_closes(self):
        """Vorbedingung: angemeldet. Aktion: ``NV.combobox`` mit vier Werten
        direkt erzeugen und bedienen.

        Erwartung: Container ``div[data-nv-combobox][data-nv-field]`` mit
        ``input[role=combobox]`` und ``ul[data-nv-combobox-list]``; Klick
        öffnet (``aria-expanded="true"``); Eingabe „BETA“ filtert
        case-insensitiv auf den einen Treffer; Pfeil ab + Enter wählt und
        setzt ``data-nv-value`` samt Eingabewert; Esc schließt die Liste.
        """
        self.boot()
        created = self.page.evaluate(
            """() => {
              const host = document.createElement('div');
              host.id = 'cb-probe';
              document.body.appendChild(host);
              if (!window.NV || typeof NV.combobox !== 'function') return false;
              const node = NV.combobox(
                ['alpha-model', 'beta-model', 'gamma-model', 'alpha-zwei'],
                'alpha-model', {field: 'model'});
              host.appendChild(node);
              return true;
            }""")
        self.assertTrue(created, "NV.combobox ist nicht verfügbar")
        container = self.page.locator(
            "#cb-probe div[data-nv-combobox][data-nv-field='model']")
        self.assertEqual(1, container.count(),
                         "Der Combobox-Container trägt nicht "
                         "data-nv-combobox/data-nv-field")
        field = container.locator("input[data-nv-combobox-input]")
        self.assertEqual(1, field.count(),
                         "Das Combobox-Eingabefeld fehlt")
        self.assertEqual("combobox", field.get_attribute("role"),
                         "Das Eingabefeld hat nicht role=combobox")
        self.assertNotEqual(
            "true", field.get_attribute("aria-expanded"),
            "Die Liste ist ohne Klick bereits geöffnet")
        self.assertEqual(
            1, container.locator("ul[data-nv-combobox-list]").count(),
            "Die Combobox-Liste ul[data-nv-combobox-list] fehlt")

        field.click()
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Der Klick öffnet die Combobox nicht (aria-expanded)")
        options = container.locator("li[data-nv-combobox-option]")
        self.assertGreaterEqual(options.count(), 4,
                                "Die geöffnete Liste zeigt nicht alle Werte")

        field.fill("BETA")
        self.wait_until(
            lambda: options.count() == 1,
            timeout=10,
            message="Die Eingabe filtert die Liste nicht case-insensitiv")
        self.assertIn("beta-model", (options.first.inner_text() or "").lower(),
                      "Der gefilterte Treffer ist nicht beta-model")

        field.press("ArrowDown")
        field.press("Enter")
        self.wait_until(
            lambda: container.get_attribute("data-nv-value") == "beta-model",
            timeout=10,
            message="Enter übernimmt die Auswahl nicht in data-nv-value")
        self.assertEqual(
            "beta-model", field.input_value(),
            "Der gewählte Wert steht nicht im Eingabefeld")

        field.click()
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Die Combobox ließ sich nicht erneut öffnen")
        field.press("Escape")
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") != "true",
            timeout=10,
            message="Esc schließt die Combobox nicht")
        self.assertFalse(
            container.locator("ul[data-nv-combobox-list]").is_visible(),
            "Die Liste bleibt nach Esc sichtbar")
        self.assert_no_page_errors()


class AgentListTest(F33AgentsTest):
    def test_pinning_moves_agent_to_pinned_section_and_persists(self):
        """Vorbedingung: globale Agenten ``tester``/``zweiter``, Projektagent
        ``projhelfer``, nichts angeheftet.

        Aktion: Anpinn-Knopf der Karte ``tester`` klicken, dann erneut.
        Erwartung: ``aria-pressed`` false → true; die Karte steht in
        ``section[data-nv-pinned-agents]`` oberhalb der Liste;
        ``localStorage['nv-pinned-agents']`` enthält
        ``{"scope":"global","name":"tester"}``. Erneuter Klick hebt auf
        (Storage leer, Karte nicht mehr angeheftet).
        """
        self.open_agents()
        card = self.card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='agent-pin']")
        self.assertEqual(
            1, pin.count(),
            "Die Agentenkarte hat keinen Anpinn-Knopf "
            "[data-nv-action='agent-pin']")
        self.assertNotEqual(
            "true", pin.first.get_attribute("aria-pressed"),
            "Die Karte ist ohne Zutun bereits angeheftet")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Anpinn-Knopf setzt aria-pressed nicht auf true")
        pinned = self.page.locator("section[data-nv-pinned-agents]")
        pinned.wait_for(state="visible", timeout=10000)
        self.assertEqual(
            1, pinned.locator(
                "article[data-nv-agent='tester']"
                "[data-nv-agent-scope='global']").count(),
            "Die angeheftete Karte fehlt in section[data-nv-pinned-agents]")
        stored = json.loads(self.page.evaluate(
            "() => window.localStorage.getItem('nv-pinned-agents')") or "[]")
        self.assertTrue(
            any(isinstance(item, dict)
                and item.get("name") == "tester"
                and item.get("scope") == "global"
                for item in stored),
            "nv-pinned-agents enthält nicht {scope:global,name:tester}: "
            + repr(stored))
        pinned_box = pinned.bounding_box()
        list_box = self.page.locator("[data-nv-agent-list]").bounding_box()
        self.assertIsNotNone(pinned_box)
        self.assertIsNotNone(list_box)
        self.assertLess(
            pinned_box["y"], list_box["y"],
            "Die angeheftete Sektion steht nicht oberhalb der Liste")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "false",
            timeout=10,
            message="Der erneute Klick hebt das Anheften nicht auf")
        stored = json.loads(self.page.evaluate(
            "() => window.localStorage.getItem('nv-pinned-agents')") or "[]")
        self.assertEqual([], stored,
                         "nv-pinned-agents ist nach dem Aufheben nicht leer: "
                         + repr(stored))
        self.assertEqual(
            0, pinned.locator(
                "article[data-nv-agent='tester']"
                "[data-nv-agent-scope='global']").count(),
            "Die Karte bleibt nach dem Aufheben angeheftet")
        self.assert_no_page_errors()

    def test_search_filters_agent_cards_live(self):
        """Vorbedingung: Agenten mit unterschiedlichen Namen/Beschreibungen.

        Aktion: ``input[data-nv-agent-search]`` mit „Zweiter“ füllen, dann
        leeren. Erwartung: Nur ``zweiter`` bleibt sichtbar (Treffer in der
        Beschreibung), ``tester``/``defekt`` werden verborgen; nach dem Leeren
        sind wieder alle Karten sichtbar.
        """
        self.open_agents()
        search = self.page.locator("input[data-nv-agent-search]")
        search.wait_for(state="visible", timeout=20000)
        search.fill("Zweiter")
        self.wait_until(
            lambda: self.card("zweiter").is_visible()
            and not self.card("tester").is_visible(),
            timeout=10,
            message="Die Agentensuche filtert die Karten nicht live")
        self.assertFalse(self.card("defekt").is_visible(),
                         "Die Suche blendet defekt trotz Nichttreffer ein")

        search.fill("")
        self.wait_until(
            lambda: self.card("tester").is_visible()
            and self.card("defekt").is_visible(),
            timeout=10,
            message="Nach dem Leeren sind nicht wieder alle Karten sichtbar")
        self.assert_no_page_errors()

    def test_tag_filter_toggles_cards(self):
        """Vorbedingung: globaler Agent ``tester`` und Projektagent
        ``projhelfer``.

        Aktion: Tag-Filter „Global“ klicken, dann erneut.
        Erwartung: ``div[data-nv-agent-tag-filters]`` enthält
        ``button[data-nv-tag-filter]``; der Global-Filter blendet den
        Projektagenten aus (``aria-pressed="true"``), der erneute Klick hebt
        den Filter auf und zeigt ihn wieder.
        """
        self.open_agents()
        filters = self.page.locator("div[data-nv-agent-tag-filters]")
        filters.wait_for(state="visible", timeout=20000)
        chips = filters.locator("button[data-nv-tag-filter]")
        self.assertGreaterEqual(
            chips.count(), 1,
            "Die Tag-Filter-Leiste enthält keine Umschalt-Chips")
        global_filter = filters.locator(
            "button[data-nv-tag-filter]", has_text=re.compile("global", re.I))
        self.assertGreaterEqual(
            global_filter.count(), 1,
            "Es gibt keinen Global-Tag-Filter")
        project_card = self.card("projhelfer")
        project_card.wait_for(state="visible", timeout=20000)

        global_filter.first.click()
        self.wait_until(
            lambda: not project_card.is_visible(),
            timeout=10,
            message="Der Global-Filter blendet den Projektagenten nicht aus")
        self.assertEqual(
            "true", global_filter.first.get_attribute("aria-pressed"),
            "Der aktive Tag-Filter setzt aria-pressed nicht auf true")
        self.assertTrue(self.card("tester").is_visible(),
                        "Der Global-Filter blendet globale Karten aus")

        global_filter.first.click()
        self.wait_until(
            lambda: project_card.is_visible(),
            timeout=10,
            message="Der erneute Klick hebt den Tag-Filter nicht auf")
        self.assertNotEqual(
            "true", global_filter.first.get_attribute("aria-pressed"),
            "Der aufgehobene Filter lässt aria-pressed auf true")
        self.assert_no_page_errors()

    def test_name_and_tags_are_separate_rows(self):
        """Vorbedingung: Agent ``tester`` mit Rolle (Tag vorhanden).

        Aktion: Karte messen. Erwartung: ``h3.nv-agent-name`` und
        ``div[data-nv-agent-tags]`` existieren; die Tags sind kein Kind des
        Namens und stehen vollständig unter der Namenszeile (Tags-Oberkante
        nicht über der Namensunterkante) — keine Überblendung.
        """
        self.open_agents()
        card = self.card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        name = card.locator("h3.nv-agent-name")
        self.assertEqual(1, name.count(),
                         "Die Karte hat keinen Namen h3.nv-agent-name")
        tags = card.locator("div[data-nv-agent-tags]")
        self.assertEqual(1, tags.count(),
                         "Die Karte hat keine Tag-Zeile "
                         "div[data-nv-agent-tags]")
        self.assertEqual(
            0, name.locator("[data-nv-agent-tags]").count(),
            "Die Tags liegen innerhalb des Namens statt in einer eigenen Zeile")
        self.assertTrue(tags.is_visible(), "Die Tag-Zeile ist nicht sichtbar")
        name_box = name.bounding_box()
        tags_box = tags.bounding_box()
        self.assertIsNotNone(name_box, "Der Name hat keine Position")
        self.assertIsNotNone(tags_box, "Die Tag-Zeile hat keine Position")
        self.assertGreaterEqual(
            tags_box["y"], name_box["y"] + name_box["height"] - 1,
            "Die Tags überblenden die Namenszeile: "
            f"Name {name_box}, Tags {tags_box}")
        self.assert_no_page_errors()


class WizardTest(F33AgentsTest):
    def test_wizard_has_five_steps_and_step_indicator(self):
        """Vorbedingung: angemeldet, Wizard geöffnet.

        Aktion: Schritte zählen, Indikator auf Schritt 1 und 2 lesen.
        Erwartung: Genau fünf ``section[data-nv-step="1..5"]``; der Indikator
        nennt „Schritt 1 von 5“ (bzw. „Step 1 of 5“) und nach „Weiter“
        „Schritt 2 von 5“.
        """
        wizard = self.open_wizard()
        for step in (1, 2, 3, 4, 5):
            self.assertEqual(
                1, wizard.locator(f"section[data-nv-step='{step}']").count(),
                f"Wizard-Schritt {step} fehlt")
        self.assertEqual(
            0, wizard.locator("section[data-nv-step='6']").count(),
            "Der Wizard hat mehr als fünf Schritte")
        self.assertRegex(
            wizard.inner_text(), r"(?i)(schritt|step)\s*1\s*(von|of)\s*5",
            "Der Schrittzähler nennt nicht „Schritt 1 von 5“: "
            + wizard.inner_text()[:200])

        wizard.locator("[data-nv-field='name']").fill("zaehlprobe")
        self.page.locator("[data-nv-wizard-next]").click()
        self.wait_until(
            lambda: re.search(r"(?i)(schritt|step)\s*2\s*(von|of)\s*5",
                              wizard.inner_text()) is not None,
            timeout=10,
            message="Der Schrittzähler folgt dem Wechsel nicht (2 von 5)")
        self.assert_no_page_errors()

    def test_step_two_explains_modes_and_names_all_as_agent(self):
        """Vorbedingung: kein Primäragent in der Fixture.

        Aktion: Schritt 2 öffnen, Modus-Optionen lesen.
        Erwartung: ``select[data-nv-field="mode"]`` bietet subagent, all und
        primary; jede Option trägt eine Erklärung (länger als der Wert); die
        Option ``all`` heißt sichtbar „Agent“ (nicht „all“). Das Modell ist
        eine Combobox (``div[data-nv-combobox][data-nv-field="model"]``) mit
        leerer Standardoption („— Standardmodell —“).
        """
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        mode.wait_for(state="visible", timeout=15000)
        options = dict(self.select_options(mode))
        for value in ("subagent", "all", "primary"):
            self.assertIn(value, options,
                          f"Die Einsatzart {value!r} fehlt: {options}")
            self.assertGreater(
                len(options[value]), len(value) + 3,
                f"Die Option {value!r} ist nicht erklärt: {options[value]!r}")
        self.assertNotEqual(
            "all", options["all"].strip().lower(),
            "Die Option all heißt sichtbar weiterhin „all“")
        self.assertRegex(
            options["all"], r"(?i)agent",
            "Die Option all wird nicht als „Agent“ bezeichnet: "
            + repr(options["all"]))

        combobox = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        self.assertEqual(
            1, combobox.count(),
            "Das Modellfeld ist keine Combobox "
            "(div[data-nv-combobox][data-nv-field=model])")
        field = combobox.locator("input[data-nv-combobox-input]")
        field.click()
        options_text = combobox.locator(
            "li[data-nv-combobox-option]").all_inner_texts()
        self.assertTrue(
            any(re.search(r"(?i)standard", text) for text in options_text),
            "Der Modell-Combobox fehlt die leere Standardoption: "
            + repr(options_text))
        self.assert_no_page_errors()

    def test_mode_help_updates_with_the_selection(self):
        """Vorbedingung: Wizard Schritt 2.

        Aktion: ``p[data-nv-mode-help]`` lesen, dann all, subagent und primary
        wählen. Erwartung: Der Hilfetext ist sichtbar, nicht leer und ändert
        sich je Auswahl; er nennt die gewählte Einsatzart (agent/subagent/
        primary).
        """
        wizard = self.wizard_goto(2)
        help_text = wizard.locator("p[data-nv-mode-help]")
        help_text.wait_for(state="visible", timeout=15000)
        initial = (help_text.inner_text() or "").strip()
        self.assertTrue(initial, "Der Modus-Hilfetext ist leer")
        mode = wizard.locator("select[data-nv-field='mode']")

        mode.select_option("all")
        self.wait_until(
            lambda: (help_text.inner_text() or "").strip() != initial,
            timeout=10,
            message="Der Modus-Hilfetext folgt der Auswahl all nicht")
        self.assertRegex(
            help_text.inner_text(), r"(?i)agent",
            "Der Hilfetext zu all nennt nicht „Agent“")
        all_help = help_text.inner_text()

        mode.select_option("subagent")
        self.wait_until(
            lambda: (help_text.inner_text() or "").strip() != all_help.strip(),
            timeout=10,
            message="Der Modus-Hilfetext folgt der Auswahl subagent nicht")
        self.assertRegex(
            help_text.inner_text(), r"(?i)subagent",
            "Der Hilfetext zu subagent nennt nicht „Subagent“")

        mode.select_option("primary")
        self.wait_until(
            lambda: re.search(r"(?i)primary|primär",
                              help_text.inner_text() or "") is not None,
            timeout=10,
            message="Der Hilfetext zu primary erklärt die Einsatzart nicht")
        self.assert_no_page_errors()

    def test_primary_option_exists_without_a_primary_agent(self):
        """Vorbedingung: kein Agent mit ``mode: primary`` in der Fixture.

        Aktion: Wizard Schritt 2 öffnen. Erwartung:
        ``select[data-nv-field="mode"]`` bietet die Option ``primary`` an.
        """
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        values = [value for value, _text in self.select_options(mode)]
        self.assertIn(
            "primary", values,
            "Ohne Primäragenten fehlt die Option primary: " + repr(values))

    def test_primary_option_is_hidden_when_a_primary_agent_exists(self):
        """Vorbedingung: per API angelegter Agent ``chief`` mit
        ``mode: primary`` (POST /api/agent action=save).

        Aktion: Wizard Schritt 2 öffnen. Erwartung: Die Option ``primary``
        fehlt in ``select[data-nv-field="mode"]``, weil bereits ein
        Primäragent existiert.
        """
        self.create_primary_agent("chief")
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        values = [value for value, _text in self.select_options(mode)]
        self.assertNotIn(
            "primary", values,
            "Trotz vorhandenem Primäragenten bietet der Wizard primary an: "
            + repr(values))
        self.assertIn("all", values,
                      "Der Wizard bietet die Einsatzart all nicht mehr an")

    def test_step_three_offers_permissions_and_uses_the_choice(self):
        """Vorbedingung: Wizard.

        Aktion: Schritt 3 öffnen, ``select[data-nv-field="perm"]`` und
        ``p[data-nv-perm-help]`` lesen, ``voll`` wählen, zu Schritt 4 gehen
        und die Prompt-Vorlage anfordern.
        Erwartung: Der Rechte-Select bietet mehrere Optionen (u. a. ``voll``),
        der Hilfetext ändert sich mit der Auswahl; der Template-Abruf
        (``POST /api/agent_template``) übergibt ``perm: "voll"`` statt fest
        ``lesen``.
        """
        wizard = self.wizard_goto(3)
        perm = wizard.locator("select[data-nv-field='perm']")
        perm.wait_for(state="visible", timeout=15000)
        values = [value for value, _text in self.select_options(perm)]
        self.assertGreaterEqual(len(values), 2,
                                "Der Rechte-Select bietet keine Auswahl: "
                                + repr(values))
        self.assertIn("voll", values,
                      "Die Rechte-Option voll fehlt: " + repr(values))
        perm_help = wizard.locator("p[data-nv-perm-help]")
        perm_help.wait_for(state="visible", timeout=10000)
        initial_help = (perm_help.inner_text() or "").strip()
        self.assertTrue(initial_help, "Der Rechte-Hilfetext ist leer")

        perm.select_option("voll")
        self.wait_until(
            lambda: (perm_help.inner_text() or "").strip() != initial_help,
            timeout=10,
            message="Der Rechte-Hilfetext folgt der Auswahl nicht")

        captured = {}

        def remember(request):
            if "/api/agent_template" in request.url and request.method == "POST":
                try:
                    captured["body"] = json.loads(request.post_data or "{}")
                except ValueError:
                    captured["body"] = {}

        self.page.on("request", remember)
        self.page.locator("[data-nv-wizard-next]").click()
        wizard.locator("section[data-nv-step='4']").wait_for(
            state="visible", timeout=15000)
        wizard.locator("[data-nv-action='prompt-template']").click()
        self.wait_until(
            lambda: "body" in captured, timeout=15,
            message="Der Vorlagenknopf löste keinen Template-Abruf aus")
        self.assertEqual(
            "voll", captured["body"].get("perm"),
            "Der Template-Aufruf übergibt nicht die gewählte Berechtigung: "
            + repr(captured["body"]))
        self.assert_no_page_errors()

    def test_step_four_prompt_is_large(self):
        """Vorbedingung: Wizard Schritt 4.

        Aktion: Prompt-Feld messen. Erwartung:
        ``textarea[data-nv-field="prompt"]`` hat ``rows >= 12`` und ist
        veränderbar (nicht ``disabled``/``readonly``).
        """
        wizard = self.wizard_goto(4)
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.wait_for(state="visible", timeout=15000)
        rows = prompt.get_attribute("rows")
        self.assertIsNotNone(rows, "Das Prompt-Feld hat kein rows-Attribut")
        self.assertGreaterEqual(
            int(rows), 12,
            "Das Prompt-Feld ist zu klein (rows=" + str(rows) + ")")
        self.assertFalse(prompt.is_disabled(), "Das Prompt-Feld ist deaktiviert")
        self.assertNotEqual(
            "true", (prompt.get_attribute("readonly") or "").lower(),
            "Das Prompt-Feld ist schreibgeschützt")
        self.assert_no_page_errors()

    def test_step_five_lists_fields_once_and_formats_the_prompt(self):
        """Vorbedingung: Wizard bis Schritt 4, Prompt mit zwei Zeilen.

        Aktion: Weiter zu Schritt 5. Erwartung: Die strukturierten Felder
        stehen genau einmal (der Agentenname erscheint einmal); der Prompt
        steht ausschließlich im formatierten Block
        ``pre[data-nv-review-prompt]`` mit sichtbarem Zeilenumbruch
        (``white-space: pre-wrap``) — nicht zusätzlich als Fließtext in der
        Feldliste.
        """
        wizard = self.wizard_goto(4, "reviewprobe")
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.fill("Zeile eins\nZeile zwei")
        self.page.locator("[data-nv-wizard-next]").click()
        step5 = wizard.locator("section[data-nv-step='5']")
        step5.wait_for(state="visible", timeout=15000)

        review = step5.locator("pre[data-nv-review-prompt]")
        self.assertEqual(
            1, review.count(),
            "Der formatierte Prompt-Block pre[data-nv-review-prompt] fehlt")
        review_text = review.inner_text()
        self.assertIn("Zeile eins", review_text)
        self.assertIn("Zeile zwei", review_text)
        self.assertIn(
            "\n", review_text,
            "Der Prompt-Block zeigt den Zeilenumbruch nicht an")
        white_space = review.evaluate(
            "node => getComputedStyle(node).whiteSpace")
        self.assertIn(
            white_space, ("pre-wrap", "break-spaces"),
            "Der Prompt-Block bricht Zeilen nicht sichtbar um: "
            + repr(white_space))

        text = step5.inner_text()
        self.assertEqual(
            1, text.count("Zeile eins"),
            "Der Prompt erscheint doppelt auf der Prüfseite: " + text)
        self.assertEqual(
            1, text.count("reviewprobe"),
            "Die strukturierten Felder nennen den Namen mehrfach: " + text)
        self.assert_no_page_errors()

    def test_create_is_reachable_without_scrolling_on_step_five(self):
        """Vorbedingung: Wizard bis Schritt 4 mit sehr langem Prompt (80
        Zeilen).

        Aktion: Weiter zu Schritt 5, Position des Anlegen-Knopfs messen.
        Erwartung: ``button[data-nv-action="agent-create"]`` liegt sichtbar im
        Viewport (sticky Aktionsleiste, kein Scrollen nötig); der
        „Weiter“-Knopf ``[data-nv-wizard-next]`` ist auf Schritt 5 nicht
        sichtbar (kein toter Knopf).
        """
        wizard = self.wizard_goto(4, "langprompt")
        wizard.locator("textarea[data-nv-field='prompt']").fill(
            "\n".join(f"Zeile {index} des langen Prompts" for index in range(1, 81)))
        self.page.locator("[data-nv-wizard-next]").click()
        wizard.locator("section[data-nv-step='5']").wait_for(
            state="visible", timeout=15000)

        create = wizard.locator("[data-nv-action='agent-create']")
        create.wait_for(state="visible", timeout=10000)
        box = create.bounding_box()
        self.assertIsNotNone(box, "Der Anlegen-Knopf hat keine Position")
        viewport = self.page.viewport_size
        self.assertGreaterEqual(box["y"], 0,
                                "Der Anlegen-Knopf liegt über dem Viewport")
        self.assertLessEqual(
            box["y"] + box["height"], viewport["height"] + 1,
            "Der Anlegen-Knopf liegt unterhalb des Viewports und ist nur "
            f"nach Scrollen erreichbar: {box} bei {viewport}")

        next_button = self.page.locator("[data-nv-wizard-next]")
        self.assertFalse(
            next_button.is_visible() if next_button.count() else False,
            "Auf Schritt 5 ist der tote „Weiter“-Knopf sichtbar")
        self.assert_no_page_errors()

    def test_cancel_warns_inline_before_discarding(self):
        """Vorbedingung: Wizard Schritt 1 mit eingegebenem Namen.

        Aktion: „Abbrechen“ klicken. Erwartung: Es erscheint die Inline-Warnung
        ``div[data-nv-wizard-cancel-confirm]`` mit „Ja, abbrechen“; der Wizard
        bleibt zunächst offen und der Name erhalten (kein Datenverlust ohne
        Bestätigung); erst der bestätigte Abbruch schließt den Wizard.
        """
        wizard = self.open_wizard()
        name = wizard.locator("[data-nv-field='name']")
        name.fill("abbrechprobe")
        self.page.locator("[data-nv-wizard-cancel]").click()

        confirm = wizard.locator("div[data-nv-wizard-cancel-confirm]")
        confirm.wait_for(state="visible", timeout=10000)
        self.assertRegex(
            confirm.inner_text(), r"(?i)verloren|lost|abbrechen|cancel",
            "Die Abbruch-Warnung erklärt den Datenverlust nicht: "
            + repr(confirm.inner_text()))
        yes = confirm.locator(
            "button", has_text=re.compile(r"(?i)(ja,?\s*abbrechen|yes,?\s*cancel)"))
        self.assertGreaterEqual(
            yes.count(), 1,
            "Die Abbruch-Warnung bietet keinen „Ja, abbrechen“-Knopf")
        self.assertTrue(wizard.is_visible(),
                        "Der Wizard schließt sich vor der Bestätigung")
        self.assertEqual(
            "abbrechprobe", name.input_value(),
            "Die Eingaben gingen vor der Bestätigung verloren")

        yes.first.click()
        self.wait_until(
            lambda: not wizard.is_visible(), timeout=10,
            message="Der bestätigte Abbruch schließt den Wizard nicht")
        self.assertTrue(
            self.page.locator("[data-nv-agent-list]").is_visible(),
            "Nach dem Abbruch erscheint die Agentenliste nicht")
        self.assert_no_page_errors()


class EditorTest(F33AgentsTest):
    def test_assignments_are_loaded_only_after_expanding(self):
        """Vorbedingung: Agent ``tester``, Projekt ``proj``.

        Aktion: Editor öffnen, kurz warten, dann
        ``details[data-nv-assignments]`` aufklappen.
        Erwartung: Vor dem Aufklappen kein Abruf von ``/api/project-agents``;
        die Details sind geschlossen und enthalten den Platzhalter
        ``p[data-nv-assignments-hint]``; erst nach dem Aufklappen wird geladen
        (Request sichtbar) und die Zuordnung ``input[data-nv-assign="proj"]``
        erscheint.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.wait_for(state="visible", timeout=20000)
        self.page.wait_for_timeout(800)
        self.assertFalse(
            any("/api/project-agents" in url for url in self.requests),
            "Der Editor lädt die Projektzuordnungen bereits beim Rendern")

        details = editor.locator("details[data-nv-assignments]")
        self.assertEqual(
            1, details.count(),
            "Die Projektzuordnungen liegen nicht in "
            "details[data-nv-assignments]")
        self.assertIsNone(details.get_attribute("open"),
                          "details[data-nv-assignments] ist standardmäßig offen")
        self.assertEqual(
            1, details.locator("p[data-nv-assignments-hint]").count(),
            "Der Platzhalter p[data-nv-assignments-hint] fehlt")

        summary = details.locator("summary")
        if summary.count():
            summary.first.click()
        else:
            details.first.click()
        self.wait_until(
            lambda: any("/api/project-agents" in url for url in self.requests),
            timeout=15,
            message="Beim Aufklappen wird /api/project-agents nicht geladen")
        editor.locator("input[data-nv-assign='proj']").wait_for(
            state="visible", timeout=15000)
        self.assert_no_page_errors()

    def test_back_button_is_secondary_and_returns_to_list(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: ``button[data-nv-action="agent-back"]`` prüfen und klicken.
        Erwartung: Der Knopf ist sichtbar, trägt die Klasse ``nv-secondary``
        und ein ``aria-label``; der Klick öffnet die Agentenliste
        (``data-nv-view="agents"``).
        """
        self.open_editor("tester")
        back = self.page.locator("button[data-nv-action='agent-back']")
        back.wait_for(state="visible", timeout=15000)
        classes = (back.get_attribute("class") or "").split()
        self.assertIn(
            "nv-secondary", classes,
            "Der Zurück-Knopf ist nicht als nv-secondary gestaltet: "
            + repr(classes))
        self.assertTrue(
            (back.get_attribute("aria-label") or "").strip(),
            "Der Zurück-Knopf hat kein aria-label")
        back.click()
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=20000)
        self.assertTrue(
            self.page.locator("[data-nv-agent-list]").is_visible(),
            "Nach dem Zurück-Klick erscheint die Agentenliste nicht")
        self.assert_no_page_errors()

    def test_raw_toggle_changes_label_and_save_mode(self):
        """Vorbedingung: Editor ``tester`` im Feldmodus.

        Aktion: ``[data-nv-raw]`` klicken, Beschriftung und Speichermodus
        lesen. Erwartung: Die Beschriftung wechselt von „Rohtext anzeigen“ zu
        „Strukturierte Ansicht“ (``aria-pressed`` false → true); der
        Speichern-Knopf trägt sonst ``data-nv-mode="fields"`` („Änderungen
        speichern") und im Rohtextmodus ``data-nv-mode="raw"`` („Rohtext
        speichern"); ``p[data-nv-save-hint]`` nennt den gespeicherten Umfang
        und ändert sich mit dem Modus.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        raw = editor.locator("[data-nv-raw]")
        raw.wait_for(state="visible", timeout=15000)
        save = editor.locator("[data-nv-action='agent-save']")
        hint = editor.locator("p[data-nv-save-hint]")
        hint.wait_for(state="visible", timeout=10000)
        fields_hint = (hint.inner_text() or "").strip()
        self.assertTrue(fields_hint, "Der Speicher-Hinweis ist leer")
        self.assertRegex(
            raw.inner_text(), r"(?i)rohtext|raw",
            "Der Umschalter heißt nicht „Rohtext anzeigen“: "
            + repr(raw.inner_text()))
        self.assertNotEqual(
            "true", raw.get_attribute("aria-pressed"),
            "Der Rohtextmodus ist ohne Klick bereits aktiv")
        self.assertEqual(
            "fields", save.get_attribute("data-nv-mode"),
            "Der Speichern-Knopf trägt im Feldmodus nicht "
            "data-nv-mode=fields")
        self.assertRegex(
            save.inner_text(), r"(?i)änderungen|changes",
            "Der Speichern-Knopf heißt im Feldmodus nicht "
            "„Änderungen speichern“: " + repr(save.inner_text()))

        raw.click()
        self.wait_until(
            lambda: raw.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Umschalter setzt aria-pressed nicht auf true")
        self.assertRegex(
            raw.inner_text(), r"(?i)struktur|structured",
            "Der Umschalter heißt im Rohtextmodus nicht "
            "„Strukturierte Ansicht“: " + repr(raw.inner_text()))
        self.assertEqual(
            "raw", save.get_attribute("data-nv-mode"),
            "Der Speichern-Knopf trägt im Rohtextmodus nicht "
            "data-nv-mode=raw")
        self.assertRegex(
            save.inner_text(), r"(?i)rohtext|raw",
            "Der Speichern-Knopf heißt im Rohtextmodus nicht "
            "„Rohtext speichern“: " + repr(save.inner_text()))
        self.wait_until(
            lambda: (hint.inner_text() or "").strip() != fields_hint,
            timeout=10,
            message="Der Speicher-Hinweis nennt den Rohtextmodus nicht")
        self.assert_no_page_errors()

    def test_copy_confirmation_names_the_target(self):
        """Vorbedingung: Editor ``tester``, Projekt ``proj``.

        Aktion: ``[data-nv-action="agent-copy"]`` klicken. Erwartung: Die
        sichtbare Bestätigung nennt das Ziel deutlich („Nach 'proj'
        kopieren?" / „Copy to 'proj'?“), nicht nur eine stumme Auswahl.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-action='agent-copy']").click()
        self.wait_until(
            lambda: re.search(
                r"(?i)(nach|to)\s*['\"„]?proj", self.confirmation_text())
            is not None,
            timeout=15,
            message="Die Kopier-Bestätigung nennt das Ziel nicht deutlich: "
                    + repr(self.confirmation_text()[:300]))
        self.assert_no_page_errors()

    def test_backup_toast_says_backup_created_without_version_warning(self):
        """Vorbedingung: Agent ``tester`` ohne Sicherungen.

        Aktion: ``[data-nv-action="agent-backup"]`` klicken.
        Erwartung: Es entsteht eine Sicherungsdatei; der Toast meldet
        „Sicherung angelegt“ (Backend-Aktion ``backup`` aus WP6) und enthält
        keinen Versions-/Modellhinweis („nicht geprüft“).
        """
        self.open_editor("tester")
        before = len(self.backup_files())
        self.page.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: "Sicherung angelegt" in self.toast_text(),
            timeout=25,
            message="Der Sicherungs-Toast meldet nicht „Sicherung angelegt“: "
                    + repr(self.toast_text()))
        self.assertNotIn(
            "nicht geprüft", self.toast_text(),
            "Der Sicherungs-Toast enthält weiterhin einen Versionshinweis: "
            + repr(self.toast_text()))
        self.wait_until(
            lambda: len(self.backup_files()) > before, timeout=15,
            message="Die Sicherung wurde nicht angelegt")
        self.assert_no_page_errors()

    def test_restore_shows_the_last_backup_info(self):
        """Vorbedingung: Agent ``tester`` mit angelegter Sicherung.

        Aktion: Sicherung anlegen, Editor neu laden,
        ``[data-nv-action="agent-restore"]`` klicken.
        Erwartung: Die Bestätigung zeigt ``span[data-nv-backup-info]`` mit
        einem Hinweis auf die letzte Sicherung (aus ``GET /api/agent`` →
        ``backups``).
        """
        self.open_editor("tester")
        self.page.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: "Sicherung angelegt" in self.toast_text(),
            timeout=25,
            message="Die Vorbedingung (Sicherung anlegen) scheiterte: "
                    + repr(self.toast_text()))

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-action='agent-restore']").click()
        info = self.page.locator("span[data-nv-backup-info]")
        info.wait_for(state="visible", timeout=15000)
        text = (info.inner_text() or "").strip()
        self.assertTrue(text, "span[data-nv-backup-info] ist leer")
        self.assertRegex(
            text, r"(?i)sicherung|backup",
            "span[data-nv-backup-info] nennt die Sicherung nicht: "
            + repr(text))
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
