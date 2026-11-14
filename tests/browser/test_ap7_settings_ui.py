"""Browserabnahme AP7: neue Zugänglichkeitsstruktur der Einstellungen.

Die Projektdetail-Einstellungen werden neu aufgeteilt (AP7): eine kompakte
Abschnittsleiste oben, darunter der dauerhaft offene Abschnitt „Agenten“,
gefolgt von drei optionalen, eingeklappten Abschnitten (Schreibrechte,
Sandbox, Git & GitHub). Standardzustand soll ohne Scrollen bedienbar sein.

Die Tests starten das echte Dashboard auf einem eigenen Port mit
vollständig isolierten VIBE_*-Pfaden (Muster tests/browser/test_write_dirs_ui.py)
und bedienen es mit Chromium über Playwright. Keine echten externen Dienste:
die GitHub-Aktivierung läuft über die Checkbox plus „Speichern“ der Karte,
nicht über „Mit GitHub verknüpfen“ (gäbe eine github.com-URL an).

Erwartete Zielstruktur (siehe Timeticket AP7; die Implementierung folgt
exakt dieser Struktur, die Tests laufen vor der Umsetzung):
- Register „Einstellungen“ mit Panel #panel-einstellungen (hidden wie bisher).
- div.settings-nav oben mit vier Sprungknöpfen
  data-goto="agenten|rechte|sandbox|github", jeder mit Status-Pill.
- section.card#project-agents dauerhaft offen; details.card#settings-rechte,
  details.card#sandbox, details.card#github eingeklappt.
- In #github erscheinen die Aktionsknöpfe (Abrufen/Push/Pull/Merge-Request)
  und der Issues-Block nur bei aktiver Verknüpfung.

Testbefehl: python3 -m unittest tests.browser.test_ap7_settings_ui -v
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Installed developer dependency: Chromium is read-only from the user
# cache (same pattern as tests/browser/test_ap06_github_ui.py); never
# downloaded inside a test.
_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

# Ambient VIBE_* values (sandbox/container) would point vibe-web at the
# productive installation; the test must own all runtime paths.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
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
    "VIBE_HARNESS",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Ap7SettingsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            }
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
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_settings(self):
        # Vorbedingung einstellen: Projekt öffnen, Register „Einstellungen“.
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        panel = self.page.locator("#panel-einstellungen")
        panel.wait_for()
        self.assertTrue(panel.is_visible(), "Einstellungen-Panel ist nicht sichtbar")

    def nav(self):
        return self.page.locator(".settings-nav")

    def chip(self, goto):
        return self.nav().locator('[data-goto="%s"]' % goto)

    def chip_gotos(self):
        return self.nav().locator("[data-goto]").evaluate_all(
            "els => els.map(el => el.getAttribute('data-goto'))"
        )

    def chip_texts(self):
        return self.nav().locator("[data-goto]").all_inner_texts()

    def expand(self, section_selector):
        """Klappt einen optionalen Abschnitt auf, falls er als <details> liegt.

        Für Tests, die gegen die aktuelle Bestandsstruktur neutral
        bleiben sollen, ist der Klick ein No-op, solange der Abschnitt
        noch kein <summary> enthält (Bestandsstruktur zeigt alles
        ohne Aufklappen).
        """
        section = self.page.locator(section_selector).first
        summary = section.locator("summary")
        if not summary.count():
            return
        section.evaluate("el => el.scrollIntoView({block: 'center'})")
        if not section.evaluate("el => !!el.open"):
            summary.click()
        self.wait_until(
            lambda: section.evaluate("el => !!el.open"),
            message="Abschnitt %s ließ sich nicht aufklappen" % section_selector,
        )

    def section_visible_without_scroll(self, selector):
        box = self.page.evaluate(
            """(sel) => {
              const el = document.querySelector(sel);
              if (!el) return null;
              const b = el.getBoundingClientRect();
              return {top: b.top, bottom: b.bottom,
                      viewport: window.innerHeight};
            }""",
            selector,
        )
        self.assertIsNotNone(box, "Abschnitt %s fehlt" % selector)
        self.assertLessEqual(
            box["bottom"], box["viewport"],
            "%s liegt unter dem sichtbaren Bereich" % selector,
        )
        self.assertGreaterEqual(
            box["top"], 0, "%s liegt über dem sichtbaren Bereich" % selector,
        )

    def order_by_document_position(self, *selectors):
        # AK-Hilfsnachweis: DOM-Reihenfolge (vorbereitet für Tab-Reihenfolge).
        return self.page.evaluate(
            """(sels) => {
              const picked = sels.map(s => document.querySelector(s));
              if (picked.some(el => el == null)) return false;
              for (let i = 1; i < picked.length; i += 1) {
                const rel = picked[i - 1].compareDocumentPosition(picked[i]);
                if (!(rel & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
              }
              return true;
            }""",
            list(selectors),
        )

    # ------------------------------------------------------------ Testfälle
    def test_settings_tab_shows_section_nav_and_open_agents_first(self):
        """AK 2a/2b/2c/2d/3.

        Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“
        frisch aktiviert, nichts aufgeklappt.
        Aktion: Abschnittsleiste, Agentenabschnitt und die drei optionalen
        Abschnitte inspizieren.
        Erwartet: .settings-nav mit den vier Sprungknöpfen (Bedienknöpfe,
        Status-Pills: Agenten „…“ oder Zahl, Schreibrechte „Standardliste“,
        Sandbox „aus“, GitHub „aus“); #project-agents offen und bedienbar;
        #settings-rechte/#sandbox/#github vorhanden als eingeklappte
        <details>; ihr Steuerelemente unsichtbar; DOM-Reihenfolge nav →
        Agenten → Schreibrechte → Sandbox → GitHub; Abschnittsleiste und
        Agentensteuerung ohne Scrollen im sichtbaren Bereich.
        """
        self.open_settings()

        gotos = self.chip_gotos()
        self.assertEqual(
            set(gotos), {"agenten", "rechte", "sandbox", "github"},
            "Sprungknöpfe der Abschnittsleiste unvollständig: %r" % (gotos,),
        )
        for goto in ("agenten", "rechte", "sandbox", "github"):
            chip = self.chip(goto)
            self.assertGreater(chip.count(), 0, "Chip %s fehlt" % goto)
            self.assertTrue(
                chip.evaluate(
                    "el => el.matches('button, [role=button]')", timeout=2000),
                "Chip %s ist kein Bedienknopf" % goto,
            )

        # Status-Pills: Agenten zeigt nach dem Laden „…“ oder eine Zahl.
        self.wait_until(
            lambda: any(
                "…" in text or any(c.isdigit() for c in text)
                for text in self.chip_texts()
            ),
            timeout=15,
            message="Der Agenten-Chip zeigt weder … noch eine Zahl",
        )
        self.assertIn("Standardliste", " ".join(self.chip_texts()),
                      "Der Schreibrechte-Chip nennt „Standardliste“ nicht")
        self.assertIn("aus", self.chip("sandbox").inner_text(),
                      "Der Sandbox-Chip zeigt nicht „aus“")
        self.assertIn("aus", self.chip("github").inner_text(),
                      "Der GitHub-Chip zeigt nicht „aus“")

        agents = self.page.locator("#project-agents")
        agents.wait_for()
        self.assertTrue(agents.is_visible(), "Agenten-Abschnitt ist nicht offen")
        toggle = agents.locator('input[data-toggle="unconfigured"]')
        toggle.wait_for()
        self.assertTrue(
            toggle.is_visible() and toggle.is_enabled(),
            "Agenten-Auswahl ist im Standardzustand nicht bedienbar",
        )

        for section_selector, probe in (
            ("#settings-rechte", "Standard wiederherstellen"),
            ("#sandbox", None),
            ("#github", "Mit GitHub verknüpfen"),
        ):
            section = self.page.locator(section_selector)
            section.wait_for()
            self.assertFalse(
                section.evaluate("el => !!el.open"),
                "%s ist im Standardzustand nicht eingeklappt" % section_selector,
            )
            if probe:
                button = section.get_by_role("button", name=probe)
                self.assertFalse(
                    button.first.is_visible() if button.count() else False,
                    "Inhalt von %s ist sichtbar, obwohl eingeklappt"
                    % section_selector,
                )
        sandbox_input = self.page.get_by_label("Build-Werkzeuge")
        self.assertFalse(
            sandbox_input.first.is_visible() if sandbox_input.count() else False,
            "Build-Werkzeuge-Eingabe ist im eingeklappten Zustand sichtbar",
        )

        self.assertTrue(
            self.order_by_document_position(
                ".settings-nav", "#project-agents",
                "#settings-rechte", "#sandbox", "#github",
            ),
            "DOM-Reihenfolge ist nicht Leiste, Agenten, Schreibrechte, "
            "Sandbox, GitHub",
        )

        self.section_visible_without_scroll(".settings-nav")
        toggle_box = toggle.evaluate(
            "el => {const b = el.getBoundingClientRect();"
            "return {bottom: b.bottom, viewport: window.innerHeight}}"
        )
        self.assertLessEqual(
            toggle_box["bottom"], toggle_box["viewport"],
            "Agenten-Steuerung ist ohne Scrollen nicht vollständig sichtbar",
        )

    def test_chips_open_optional_sections_without_full_reload(self):
        """AK 2a (Chips öffnen die Abschnitte), AK 3/4 (kein Neuladen).

        Vorbedingung: Register „Einstellungen“ geöffnet; ein Marker „__ap7“
        ist in window gesetzt.
        Aktion: Chips für Sandbox, Schreibrechte und Git & GitHub nacheinander
        klicken.
        Erwartet: jeder Abschnitt klappt sich auf und sein Steuerinhalt wird
        sichtbar und in den sichtbaren Bereich gescrollt; der Marker überlebt
        den Klick (kein Neuladen); der Agenten-Abschnitt bleibt
        dabei sichtbar (nicht geschlossen).
        """
        self.open_settings()
        self.page.evaluate("window.__ap7_marker = 1")
        agents_toggle = self.page.locator('#project-agents input[data-toggle="unconfigured"]')
        # Die Agententabelle lädt asynchron (/api/project-agents); der
        # Abschlussvergleich läuft erst gegen den geladenen Zustand.
        agents_toggle.wait_for()

        self.chip("sandbox").click(timeout=2000)
        self.wait_until(
            lambda: self.page.locator("#sandbox").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Sandbox einschalten").is_visible(),
            message="Sandbox-Chip klappte den Sandbox-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#sandbox")
        self.assertEqual(self.page.evaluate("window.__ap7_marker"), 1,
                         "Der Chipklick lud die Seite neu statt nur aufzuklappen")

        self.chip("rechte").click(timeout=2000)
        self.wait_until(
            lambda: self.page.get_by_role("button", name="Standard wiederherstellen").is_visible(),
            message="Rechte-Chip klappte den Schreibrechte-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#settings-rechte")

        self.chip("github").click(timeout=2000)
        self.wait_until(
            lambda: self.page.locator("#github").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Mit GitHub verknüpfen").is_visible(),
            message="GitHub-Chip klappte den Git-und-GitHub-Abschnitt nicht auf",
        )
        self.section_visible_without_scroll("#github")

        # Der wcześniej offene Agenten-Abschnitt bleibt offen und sichtbar.
        self.assertTrue(
            self.page.locator("#project-agents").is_visible(),
            "Agenten-Abschnitt wurde beim Chip-Klick geschlossen",
        )
        self.assertTrue(
            agents_toggle.is_visible(),
            "Agenten-Checkbox ist nach den Chip-Klicks nicht mehr sichtbar",
        )
        self.assertEqual(self.page.evaluate("window.__ap7_marker"), 1,
                         "Chips verursachten einen kompletten Seitenaufbau")

    def test_github_optional_blocks_hidden_when_disabled_collapse_and_after_enable(self):
        """AK 2e.

        Vorbedingung: Projekt „proj“ ohne GitHub-Verknüpfung; Einstellungen
        geöffnet, GitHub-Abschnitt aufgeklappt.
        Aktion 1: die Aktionsknöpfe und den Issues-Block im aus-Zustand
        prüfen.
        Aktion 2: Verknüpfungs-Checkbox aktivieren, „Speichern“ klicken, das
        Register einmal﻿﻿﻿﻿ verlassen und neu öffnen, den Abschnitt aufklappen.
        Erwartet: aus = Aktionsknöpfe und „Issues als Arbeitspakete“ unsicht-
        bar; nach Aktivieren + erneutem Öffnen sind „Abrufen (fetch, kein
        Merge)“, „Push (Branch nach origin)“, „Pull (aufholen, --ff-only)“,
        „Merge-Request stellen“ und der Issues-Block sichtbar; project.env
        erhalten GITHUB_ENABLED="1", ohne andere Zeilen zu verlieren.
        """
        self.open_settings()
        self.expand("#github")
        github = self.page.locator("#github")

        action_names = (
            "Abrufen (fetch, kein Merge)",
            "Push (Branch nach origin)",
            "Pull (aufholen, --ff-only)",
            "Merge-Request stellen",
        )
        for name in action_names:
            button = github.get_by_role("button", name=name)
            self.assertFalse(
                button.first.is_visible() if button.count() else False,
                "„%s“ ist ohne Verknüpfung sichtbar" % name,
            )
        issues_block = github.get_by_text("Issues als Arbeitspakete")
        self.assertFalse(
            issues_block.first.is_visible() if issues_block.count() else False,
            "Der Issues-Block ist ohne Verknüpfung sichtbar",
        )

        checkbox = github.locator('input[type="checkbox"]').first
        checkbox.wait_for()
        self.assertFalse(checkbox.is_checked(), "Verknüpfung startete aktiv")
        checkbox.check()
        github.get_by_role("button", name="Speichern").click()

        env_file = self.project / ".vibe" / "project.env"
        self.wait_until(
            lambda: 'GITHUB_ENABLED="1"' in env_file.read_text(encoding="utf-8"),
            message="Aktivieren schrieb kein GITHUB_ENABLED=1 nach project.env",
        )

        # Das Einstellungsregister wurde nach dem Speichern neu gebaut;
        # der Test verlässt das Register und öffnet es erneut.
        self.page.get_by_role("tab", name="Arbeit", exact=True).click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#panel-einstellungen").wait_for()
        self.expand("#github")
        github = self.page.locator("#github")
        for name in action_names:
            self.wait_until(
                lambda: github.get_by_role("button", name=name).first.is_visible(),
                message="„%s“ nach Verknüpfungsaufbau nicht sichtbar" % name,
            )
        self.assertTrue(
            github.get_by_text("Issues als Arbeitspakete").first.is_visible(),
            "Der Issues-Block nach Verknüpfungsaufbau nicht sichtbar",
        )

        new_text = env_file.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", new_text, "Speichern beschädigte project.env")

        # Aufräumen über dieselbe UI: Verknüpfung wieder deaktivieren, damit
        # spätere Fälle (GitHub-Chip „aus“) reihenfolgeunabhängig laufen. Der
        # Server liest das Projekt beim Neuaufbau neu ein; deshalb das
        # Register einmal betreten/verlassen statt die Datei im Hintergrund
        # zu editieren.
        self.page.get_by_role("tab", name="Arbeit", exact=True).click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#panel-einstellungen").wait_for()
        self.expand("#github")
        github = self.page.locator("#github")
        checkbox = github.locator('input[type="checkbox"]').first
        self.assertTrue(checkbox.is_checked(),
                        "Die Verknüpfung ist beim Aufräumen nicht mehr aktiv")
        checkbox.uncheck()
        github.get_by_role("button", name="Speichern").click()
        self.wait_until(
            lambda: 'GITHUB_ENABLED="1"'
                    not in env_file.read_text(encoding="utf-8"),
            message="Abschalten schrieb GITHUB_ENABLED=1 nicht zurück",
        )
        self.assertIn(
            "TYPE=generic", env_file.read_text(encoding="utf-8"),
            "Abschalten beschädigte project.env",
        )

    def test_settings_default_state_needs_no_hidden_content(self):
        """AK 3.

        Vorbedingung: frisches „Einstellungen“-Register, nichts aufgeklappt.
        Aktion: nur den Standardzustand inspizieren und die wichtigen
        Agenten-Steuerelemente bedienen.
        Erwartet: Agentenfilter und Agententabelle sofort sichtbar und
        schaltbar; Build-Werkzeuge-, Verzeichnis- und Repository-Eingabe
        der optionalen Abschnitte sind ohne Aufklappen unsichtbar.
        """
        self.open_settings()

        toggle = self.page.locator('input[data-toggle="unconfigured"]')
        toggle.wait_for()
        self.assertTrue(
            toggle.is_visible() and toggle.is_enabled(),
            "Agentenfilter ist im Standardzustand nicht bedienbar",
        )
        toggle.click()
        self.wait_until(
            lambda: toggle.is_checked(),
            message="Agentenfilter ließ sich nicht umschalten",
        )

        probe_specs = (
            ("Build-Werkzeuge", lambda: self.page.get_by_label("Build-Werkzeuge")),
            ("Verzeichnis-Eingabe der Schreibrechte",
             lambda: self.page.get_by_placeholder("/absoluter/pfad")),
            ("GitHub-Repository-Eingabe",
             lambda: self.page.locator('input[aria-label*="Repository"]')),
        )
        for label, probe_factory in probe_specs:
            probe = probe_factory()
            self.assertFalse(
                probe.first.is_visible() if probe.count() else False,
                "%s ist im Standardzustand sichtbar" % label,
            )

    def test_keyboard(self):
        """AK 4.

        Vorbedingung: Register „Einstellungen“ geöffnet.
        Aktion: mit der Tastatur die Abschnittsleiste durchtabben und mit
        Enter das Sandbox-summary bedienen.
        Erwartet: der erste fokussierbare Knoten des Panels ist der
        Agenten-Chip der Abschnittsleiste; Tab-Reihenfolge ist
        agenten → rechte → sandbox → github; Enter auf „summary“ von #sandbox
        macht den Abschnitt samt „Sandbox einschalten“ sichtbar.
        """
        self.open_settings()

        # Native Bedienelemente ohne tabindex: DOM-Reihenfolge = Tab-Reihen-
        # folge. Prüfung 1: der erste fokussierbare Knoten ist ein Chip.
        first_focusable = self.page.evaluate(
            """() => {
              const panel = document.querySelector('#panel-einstellungen');
              const candidates = panel.querySelectorAll(
                'button, input, select, textarea, summary');
              return candidates.length ? candidates[0].outerHTML : null;
            }"""
        )
        self.assertIsNotNone(first_focusable, "Kein fokussierbares Element im Panel")
        chip = self.chip("agenten")
        self.assertEqual(
            chip.evaluate("el => el.outerHTML", timeout=2000), first_focusable,
            "Das erste fokussierbare Element des Panels ist nicht der "
            "Agenten-Chip: %s" % first_focusable[:120],
        )

        # Prüfung 2: Tab-Reihenfolge über die Chips referenzieren.
        self.chip("agenten").focus(timeout=2000)
        expected_after_tab = {"agenten": "rechte", "rechte": "sandbox",
                              "sandbox": "github"}
        for goto, expected in sorted(expected_after_tab.items()):
            current = self.page.evaluate(
                "document.activeElement &&"
                " document.activeElement.getAttribute('data-goto') || ''"
            )
            self.assertEqual(current, goto,
                             "Fokus lag vor Tab nicht auf Chip %s" % goto)
            self.page.keyboard.press("Tab")
            next_goto = self.page.evaluate(
                "document.activeElement &&"
                " document.activeElement.getAttribute('data-goto') || ''"
            )
            self.assertEqual(next_goto, expected,
                             "Tab von %s landete nicht auf %s" % (goto, expected))

        # Prüfung 3: Enter auf dem summary macht den Abschnitt sichtbar.
        summary = self.page.locator("#sandbox summary")
        summary.wait_for()
        summary.focus()
        self.assertEqual(
            self.page.evaluate(
                "document.activeElement === document.querySelector('#sandbox summary')"
            ),
            True,
            "Das Sandbox-summary ist nicht oder nicht allein fokussierbar",
        )
        self.page.keyboard.press("Enter")
        self.wait_until(
            lambda: self.page.locator("#sandbox").evaluate("el => !!el.open")
            and self.page.get_by_role("button", name="Sandbox einschalten").is_visible(),
            message="Enter auf dem Sandbox-summary klappte den Abschnitt nicht auf",
        )

    def test_chip_jump_leaves_section_summary_below_fixed_header(self):
        """Review-Runde 1, Medium-Befund; verschärft in Review-Runde 2 (M1):
        der Test muss das Alignment-Regime erreichen, sonst gilt die
        Geometrie-Invariante auch ohne Gegenmaßnahme.

        Vorbedingung: Register „Einstellungen“ offen; danach wird der
        Viewport auf 400 px Höhe verengt, damit der Inhalt die Fensterhöhe
        übersteigt und scrollIntoView({block:'start'}) das Sprungziel
        tatsächlich an die Kopfleiste schieben kann (Kontrast zur
        Standardfixture, in der alles in den Viewport passt und der Sprung
        ein No-op bleibt).
        Aktion: je Chip (Schreibrechte, Sandbox, Git & GitHub) Klick, dann
        prüfen, dass wirklich gescrollt wurde, und die gerenderte Geometrie
        von .detailbar (position:sticky) und Ziel-summary lesen.
        Erwartet (Invariante): summary.top >= detailbar.bottom - 2 —
        der summary-Anfang muss unter der Unterkante der fixen Kopfleiste
        liegen. Ergänzend: nach dem Sprung window.scrollY > 0 (Alignment
        wurde erreicht — der Test fällt nicht auf einen No-op-Sprung zurück),
        summary.height > 0 und summary.top >= 0. Die Invariante ist bindend:
        im Alignment-Regime gilt gerundet summary.top ≈ scroll-margin-top; mit margin 0
        gilt die Invariante nachweisbar nicht mehr.
        Gegenmaßnahme: scroll-margin-top auf .seccard/#project-agents
        (bin/web/styles.css, AP7-Abschnitt).
        """
        self.open_settings()
        self.page.set_viewport_size({"width": 1280, "height": 400})

        for goto, selector in (
            ("rechte", "#settings-rechte"),
            ("sandbox", "#sandbox"),
            ("github", "#github"),
        ):
            self.chip(goto).click(timeout=2000)
            self.wait_until(
                lambda: self.page.locator(selector).evaluate("el => !!el.open"),
                message="Chip %s klappte den Abschnitt nicht auf" % goto,
            )
            # Vorbedingung der Invariante: der Sprung hat wirklich gescrollt.
            self.wait_until(
                lambda: self.page.evaluate("window.scrollY") > 0,
                message="Chip %s scrollte nicht: Alignment-Regime "
                "nicht erreicht" % goto,
            )
            geom = self.page.evaluate(
                """(sel) => {
                  const bar = document.querySelector('.detailbar');
                  const section = document.querySelector(sel);
                  if (!bar || !section) return null;
                  const summary = section.querySelector(':scope > summary');
                  if (!summary) return null;
                  const barBox = bar.getBoundingClientRect();
                  const sumBox = summary.getBoundingClientRect();
                  return {barBottom: barBox.bottom, barHeight: barBox.height,
                          sumTop: sumBox.top, sumHeight: sumBox.height};
                }""",
                selector,
            )
            self.assertIsNotNone(
                geom, "Kopfzeile oder Sprungziel %s nicht im DOM" % selector)
            self.assertGreater(
                geom["sumHeight"], 0,
                "summary von %s hat keine Höhe: %r" % (selector, geom),
            )
            self.assertGreaterEqual(
                geom["sumTop"], 0,
                "summary von %s liegt über dem Fensteranfang: %r"
                % (selector, geom),
            )
            self.assertGreaterEqual(
                geom["sumTop"], geom["barBottom"] - 2,
                "Sprungziel %s wird von der fixen Kopfleiste verdeckt "
                "(summary.top=%.2f < detailbar.bottom=%.2f; "
                "detailbar Höhe %.2f): %r"
                % (selector, geom["sumTop"], geom["barBottom"],
                   geom["barHeight"], geom),
            )

    def test_agents_chip_shows_error_when_agents_api_fails(self):
        """Agenten-Chip im Fehlerfall (Robustheit der Status-Pills).

        Vorbedingung: das Register startet mit blockierter Agenten-API
        (/api/project-agents wird per page.route abgebrochen (abort) —
        deterministisch, kein echtes Backend).
        Aktion: Einstellungsregister öffnen und den Agenten-Chip lesen.
        Erwartet: Der Agentenabschnitt zeigt die Fehlermeldung
        „Agentenauswahl nicht verfügbar …", und der Agenten-Chip zeigt die
        Status-Pill „Fehler" statt „…" (Ton bad, kein Stillstand bei
        „Lade …").
        """
        self.page.route(
            re.compile(r"/api/project-agents.*"),
            lambda route: route.abort(),
        )
        self.open_settings()

        error_box = self.page.locator("#project-agents .bad")
        self.wait_until(
            lambda: error_box.count() > 0
            and "Agentenauswahl nicht verfügbar" in error_box.first.inner_text(),
            timeout=15,
            message="Der Agentenabschnitt meldete die blockierte API nicht",
        )
        chip = self.chip("agenten")
        self.wait_until(
            lambda: "Fehler" in chip.inner_text(),
            message="Agenten-Chip zeigt bei API-Fehler nicht „Fehler“",
        )
        pill_class = chip.locator(".pill").evaluate(
            "el => el.className", timeout=2000
        )
        self.assertIn("bad", pill_class,
                      "Fehler-Pill des Agenten-Chips trägt nicht den bad-Ton")


if __name__ == "__main__":
    unittest.main()
