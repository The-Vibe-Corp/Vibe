"""Browserabnahme AP11/F29 „Priorisierung der Abarbeitungsreihenfolge“.

F29 (FEEDBACK.md) verlegt die Bedienstelle der Priorisierung aus dem
Einstellungs-Tab direkt in die Maske „Arbeit“: Die Karte „Offene
Arbeitspakete“ erhält je Paket ein Drag-Handle, Reihenfolge per Drag&Drop
(und ohne Maus per Tastatur) wird über „Speichern“ als ``PACKAGE_ORDER``
abgelegt, „Leeren (Standardordnung)“ setzt zurück; der Abschnitt
„Priorisierung“ samt Sprungchip entfällt im Einstellungs-Tab.

Dom-Vertrag (an die Implementierung gerichtet, aus den Akzeptanzkriterien
abgeleitet):

* Maske „Arbeit“ (``#panel-arbeit``): die Karte „Offene Arbeitspakete“
  (``.card`` mit dieser Kopfzeile) listet die offenen Pakete als
  ``.item`` in der wirksamen Reihenfolge; das erledigte Paket T0 steht
  nicht in der Karte.
* Je Paket genau ein Handle: ein Element mit Attribut ``data-drag-handle``
  und zugänglichem Namen (``aria-label``), der „verschieben“ enthält
  (Groß-/Kleinschreibung egal). Das Handle ist der Zieh- und Fokuspunkt.
* Die Karte enthält „Speichern“ (Rolle button, Name genau „Speichern“)
  und „Leeren (Standardordnung)“ (Name enthält „Leeren“).
* Drag&Drop: Ziehen des Handles und Ablegen an der OBEREN Kante eines
  Zielpakets (Drop-Punkt nahe der Ziellokator-Oberkante) fügt das Paket
  VOR dem Zielpaket ein. Geprüft mit Playwright ``drag_and_drop``.
* Tastatur: Fokus auf dem Handle, ``ArrowUp``/``ArrowDown`` verschieben
  das Paket eine Position (ohne zusätzlichen Moduswechsel).

Testfälle (AK aus FEEDBACK.md F29 / docs/features/AP11.md):

 1. ``test_settings_tab_has_no_priorisierung_section_or_chip`` (AK 4)
    Vor: Projekt geöffnet, Register „Einstellungen“. Aktion: Panel
    inspizieren. Erwartet: kein details-Abschnitt „Priorisierung“ und
    kein data-goto-Chip „Priorisierung“ (je 0 Treffer).
 2. ``test_open_packages_card_offers_drag_handles_save_and_clear`` (AK 3/5)
    Vor: Projekt mit erledigter T0 und offenen T1/T2; kein
    PACKAGE_ORDER; Maske „Arbeit“. Aktion: Karte inspizieren. Erwartet:
    Karte listet T1 und T2 (nicht T0) in der Standardordnung T1 vor T2;
    je Paket ein Handle mit data-drag-handle und aria-label
    „verschieben…“; „Speichern“ und „Leeren (Standardordnung)“ sind in
    der Karte vorhanden.
 3. ``test_drag_and_drop_reorders_and_save_writes_package_order`` (AK 3)
    Vor: kein PACKAGE_ORDER; Maske „Arbeit“. Aktion: Handle von T2 per
    Drag&Drop an die obere Kante von T1 ziehen, „Speichern“ klicken.
    Erwartet: project.env enthält PACKAGE_ORDER mit T2 vor T1 und behält
    TYPE/TESTER; nach erneutem Öffnen des Projekts zeigt die Karte die
    übernommene Reihenfolge T2 vor T1.
 4. ``test_clear_resets_to_the_standard_order`` (AK 3)
    Vor: PACKAGE_ORDER="T2,T1" abgelegt; Maske „Arbeit“ zeigt T2 vor T1.
    Aktion: „Leeren (Standardordnung)“ klicken. Erwartet: PACKAGE_ORDER
    ohne Kennung, TYPE/TESTER bleiben; nach erneutem Öffnen zeigt die
    Karte wieder die Standardordnung T1 vor T2.
 5. ``test_handle_is_keyboard_operable_with_arrow_keys`` (AK 5)
    Vor: kein PACKAGE_ORDER; Maske „Arbeit“. Aktion: Handle des T2-
    Pakets fokussieren, ArrowUp drücken; danach „Speichern“ klicken.
    Erwartet: die Karte zeigt T2 vor T1 (Verschieben ohne Maus);
    project.env enthält PACKAGE_ORDER mit T2 vor T1.
 6. ``test_priority_api_reports_configured_effective_and_status`` (AK 3,
    API-Grundlage, unverändert aus AP11 übernommen)
 7. ``test_blocked_package_keeps_its_saved_position_after_save``
    (Review M1) — ein BLOCKIERT-Paket behält die gezogene Position:
    Fixture T1 offen, T0 BLOCKIERT; T0 wird per Tastatur an die erste
    Position verschoben und „Speichern“ geklickt. Erwartet: PACKAGE_ORDER
    enthält T0 vor T1; nach komplettem Neuöffnen zeigt die Karte T0 vor
    T1, T0 mit BLOCKIERT- und „priorisiert“-Pille (T1 ist ebenfalls Teil
    der abgelegten Reihenfolge und trägt „priorisiert“).
 8. ``test_unknown_saved_id_is_reported_and_removed_on_save``
    (Review M2-Minor) — unbekannte Kennung sichtbar gemeldet:
    PACKAGE_ORDER="XX9,T1". Erwartet: die Karte nennt XX9 im Hinweis
    („Unbekannte Kennungen …“) und listet XX9 nicht als Zeile; nach
    „Speichern“ ist XX9 aus PACKAGE_ORDER entfernt (env-Datei), die
    bekannten Zeilen bleiben und der Hinweis verschwindet.

Anzeigevertrag (nach Review Runde 1): Die Karte baut ihre Zeilen aus der
gespeicherten Reihenfolge (``data.order``): sichtbare Einträge der
Priorisierung zuerst (Pille „priorisiert“, auch wenn BLOCKIERT), offene
Pakete ohne Eintrag folgen in Standardordnung (Pille „Standardordnung“);
erledigte und unbekannte („fehlt“) Einträge erscheinen nie als Zeile,
unbekannte werden im Hinweis genannt.
    Vor: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt (mit
    Nachweis), T1/T2 offen, X9 unbekannt. Aktion: GET
    /api/priority?name=proj mit Token. Erwartet: HTTP 200; Status je
    Eintrag (T0 erledigt, X9 fehlt), effektive Reihenfolge T2 vor T1
    ohne T0, Meldung vorhanden.

Review Runde 2, Finding M1 (Standardordnung in der Karte; Testfälle
unabhängig aus dem Arbeitspaket und SPEC.md abgeleitet):

 9. ``test_standard_order_display_and_pill_without_configuration``
    (AK-C) — ohne PACKAGE_ORDER zeigt die Karte die offenen Pakete in
    der Läufer-Standardordnung: gemischte offene Einträge aus
    TICKETS.md (nach Priorität: T2/P0 vor T1/P1, trotz Dateireihenfolge)
    und FEEDBACK.md (F1 dahinter); jede Zeile trägt die Pille
    „Standardordnung“.
10. ``test_blank_save_writes_the_displayed_standard_order`` (AK-D)
    — blankes „Speichern“ (ohne Verschiebung) legt genau die angezeigte
    Läufer-Standardordnung als PACKAGE_ORDER ab: nach Reload zeigt GET
    diese Reihenfolge als priorisiert, die Karte zeigt sie weiterhin und
    der Läufer (``bin/vibe_packages.py select``) wählt dasselbe Paket
    zuerst (T2).
11. ``test_blocked_package_appears_in_standard_order_and_keeps_position``
    (AK-E) — ein BLOCKIERT-Paket (T0, Priorität P0) und ein bereites
    offenes Paket (T1, P1) erscheinen ohne PACKAGE_ORDER in der
    Standardordnung (T0 vor T1); blankes „Speichern“ legt diese Position
    ab, das gesperrte Paket behält sie nach dem Neuöffnen (Konsistenz zu
    ``test_blocked_package_keeps_its_saved_position_after_save``).

Die Tests starten das echte Dashboard auf einem eigenen Port mit
vollständig isolierten VIBE_*-Pfaden (Muster
tests/browser/test_ap7_settings_ui.py) und bedienen es mit Chromium über
Playwright. Chromium wird nur aus dem Nutzer-Cache gelesen
(~/.cache/ms-playwright), nie heruntergeladen. Keine echten externen
Dienste, keine Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.browser.test_ap11_priority_ui -v
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap7_settings_ui.py).
_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

# Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
# produktive Installation zeigen lassen; der Test besitzt alle Laufzeitpfade.
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


def git(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60,
        env=env,
    )


class Ap11PriorityBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        git(cls.project, "init", "-q", "-b", "main")
        (cls.project / ".vibe").mkdir(exist_ok=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8")
        # Eine nachweislich erledigte Aufgabe und zwei offene Aufgaben:
        # die Statusanzeige der API (erledigt/offen) wird dadurch prüfbar.
        git(cls.project, "commit", "--allow-empty", "-q", "-m", "init")
        commit = subprocess.run(
            ["git", "-C", str(cls.project), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "- [x] T0 Erledigte Aufgabe\n"
            "  Beschreibung: fertig\n"
            "  Commit: %s; Test: test_ap11\n\n" % commit +
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        git(cls.project, "add", "-A")
        git(cls.project, "commit", "-q", "-m", "Nachweis T0")
        cls.env_path = cls.project / ".vibe" / "project.env"
        cls.base_env = "TYPE=generic\nTESTER=test-agent\n"

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
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"),
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
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
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
        """Jeder Test startet mit der Grundkonfiguration ohne Priorisierung."""
        self.env_path.write_text(self.base_env, encoding="utf-8")
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

    def open_project(self, tab="arbeit"):
        """Vorbedingung einstellen: Projekt „proj“ öffnen, Register wählen."""
        self.page.goto("about:blank")
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        if tab != "arbeit":
            self.page.locator(
                f"[role='tab'][aria-controls='panel-{tab}']").click()
        panel = self.page.locator("#panel-" + tab)
        panel.wait_for()
        self.assertTrue(panel.is_visible(),
                        "Panel „%s“ ist nicht sichtbar" % tab)
        return panel

    def open_settings(self):
        return self.open_project(tab="einstellungen")

    def open_work(self):
        return self.open_project(tab="arbeit")

    def items_card(self):
        """Die Karte „Offene Arbeitspakete“ in der Maske „Arbeit“."""
        card = self.page.locator("#panel-arbeit .card",
                                 has_text="Open work packages").first
        card.wait_for(timeout=10000)
        return card

    def item_ids(self):
        """Die Kennungen der Karte in sichtbarer Reihenfolge.

        Der Itemtext beginnt mit der Zustands-Pille (z. B. „offen“); die
        Kennung (T1, F3, …) wird deshalb per Muster herausgelesen.
        """
        items = self.items_card().locator(".item")
        ids = []
        for item in items.all():
            match = re.search(r"[TFB]\d+", item.inner_text())
            self.assertIsNotNone(
                match,
                "Item nennt keine Kennung: %r" % item.inner_text())
            ids.append(match.group(0))
        return ids

    def handles(self):
        """Die Drag-Handles der Karte (Elemente mit data-drag-handle)."""
        return self.items_card().locator("[data-drag-handle]")

    def save_button(self):
        return self.items_card().get_by_role("button", name="Save",
                                             exact=True).first

    def clear_button(self):
        return self.items_card().get_by_role(
            "button", name=re.compile("Clear", re.I)).first

    def handle_of(self, identifier):
        """Der Handle des Pakets mit der Kennung ``identifier``."""
        handle = self.items_card().locator(
            f".item:has-text('{identifier}') [data-drag-handle]").first
        self.wait_until(
            lambda: handle.count() > 0, timeout=5,
            message="Paket %s hat keinen Drag-Handle (data-drag-handle)"
                    % identifier)
        return handle

    # ------------------------------------------------------------ AK 4
    def test_settings_tab_has_no_priorisierung_section_or_chip(self):
        """AK 4 — Der Einstellungs-Tab enthält keine Priorisierung mehr.

        Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“.
        Aktion: das Einstellungs-Panel nach einem Abschnitt „Priorisierung“
        und einem data-goto-Sprungchip „Priorisierung“ durchsuchen.
        Erwartet: beides existiert nicht mehr (je 0 Treffer) — die
        Bedienstelle ist in die Maske „Arbeit“ verlagert.
        """
        self.open_settings()

        panel = self.page.locator("#panel-einstellungen")
        self.assertEqual(
            0, panel.locator(
                "details",
                has_text=re.compile("Priorisierung|Prioritization")).count(),
            "Einstellungs-Tab enthält noch einen Priorisierungs-Abschnitt")
        self.assertEqual(
            0, panel.locator('[data-goto*="prioris" i]').count(),
            "Einstellungs-Tab enthält noch den Sprungchip „Priorisierung“")

    # ------------------------------------------------------------ AK 3/5
    def test_open_packages_card_offers_drag_handles_save_and_clear(self):
        """AK 3/5 — Karte „Offene Arbeitspakete“ mit Handle je Paket.

        Vorbedingung: Projekt mit erledigter T0 und offenen T1/T2; kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren.
        Erwartet: die Karte listet die offenen Pakete T1 und T2 (nicht die
        erledigte T0) in der Standardordnung T1 vor T2; je Paket genau ein
        Drag-Handle (Element mit data-drag-handle und aria-label, der
        „verschieben“ enthält); „Speichern“ und „Leeren (Standardordnung)“
        sind in der Karte vorhanden.
        """
        self.open_work()

        card = self.items_card()
        self.assertEqual(["T1", "T2"], self.item_ids(),
                         "Karte zeigt nicht die Standardordnung der offenen "
                         "Pakete: " + ", ".join(self.item_ids()))

        handles = self.handles()
        self.assertEqual(2, handles.count(),
                         "nicht je Paket ein Drag-Handle (%d gefunden)"
                         % handles.count())
        for index in range(handles.count()):
            label = handles.nth(index).get_attribute("aria-label") or ""
            self.assertTrue(
                re.search(r"verschieben|move", label, re.I),
                "Handle %d ist nicht als solches erkennbar (aria-label=%r)"
                % (index, label))

        self.save_button()
        self.clear_button()

    # ------------------------------------------------------------ AK 3
    def test_drag_and_drop_reorders_and_save_writes_package_order(self):
        """AK 3 — Drag&Drop ändert die Reihenfolge, Speichern legt sie ab.

        Vorbedingung: kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des Pakets T2 per Drag&Drop an die obere Kante
        des Pakets T1 ziehen (Vertrag: Ablegen an der Oberkante fügt vor
        dem Zielpaket ein), danach „Speichern“ klicken.
        Erwartet: project.env enthält PACKAGE_ORDER mit T2 vor T1 und
        behält TYPE/TESTER; nach erneutem Öffnen des Projekts zeigt die
        Karte die übernommene Reihenfolge T2 vor T1.
        """
        self.open_work()
        self.assertEqual(["T1", "T2"], self.item_ids())

        self.handle_of("T2").drag_to(
            self.items_card().locator(".item", has_text="T1").first,
            target_position={"x": 20, "y": 4})
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T2"), text.index("T1"),
            "PACKAGE_ORDER wurde nicht in der gezogenen Reihenfolge "
            "abgelegt: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T2", "T1"], self.item_ids(),
            "die Karte zeigt nach dem Speichern nicht die übernommene "
            "Reihenfolge: " + ", ".join(self.item_ids()))

    def test_clear_resets_to_the_standard_order(self):
        """AK 3 — „Leeren (Standardordnung)“ setzt die gespeicherte Ordnung zurück.

        Vorbedingung: PACKAGE_ORDER="T2,T1" abgelegt; Maske „Arbeit“
        geöffnet. Die Karte zeigt die übernommene Reihenfolge T2 vor T1.
        Aktion: „Leeren (Standardordnung)“ klicken.
        Erwartet: PACKAGE_ORDER enthält keine Kennung mehr; TYPE/TESTER
        bleiben; nach erneutem Öffnen zeigt die Karte wieder die
        Standardordnung T1 vor T2.
        """
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="T2,T1"\n', encoding="utf-8")
        self.open_work()
        self.assertEqual(
            ["T2", "T1"], self.item_ids(),
            "die Karte zeigt die abgelegte Reihenfolge nicht: "
            + ", ".join(self.item_ids()))

        self.clear_button().click()

        self.wait_until(
            lambda: not re.search(
                r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?\s*[^"\'\s]+',
                self.env_path.read_text(encoding="utf-8")),
            message="Leeren leerte PACKAGE_ORDER nicht")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", text, "Leeren beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Leeren beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T1", "T2"], self.item_ids(),
            "die Karte zeigt nach dem Leeren nicht die Standardordnung: "
            + ", ".join(self.item_ids()))

    # ------------------------------------------------------------ AK 5
    def test_handle_is_keyboard_operable_with_arrow_keys(self):
        """AK 5 — Die Sortierung ist ohne Maus am Handle bedienbar.

        Vorbedingung: kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des Pakets T2 fokussieren und „ArrowUp“ drücken
        (Vertrag: Pfeiltaste verschiebt das fokussierte Paket eine
        Position, ohne Moduswechsel); danach „Speichern“ klicken.
        Erwartet: die Karte zeigt T2 vor T1 (Verschieben ohne Maus);
        project.env enthält PACKAGE_ORDER mit T2 vor T1.
        """
        self.open_work()
        self.assertEqual(["T1", "T2"], self.item_ids())

        handle = self.handle_of("T2")
        handle.focus()
        self.page.keyboard.press("ArrowUp")

        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1"],
            message="ArrowUp am fokussierten Handle verschob T2 nicht vor T1: "
                    + ", ".join(self.item_ids()))
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T2"), text.index("T1"),
            "PACKAGE_ORDER wurde nicht in der tastaturgezogenen Reihenfolge "
            "abgelegt: " + text)

    # --------------------------------------------- Review M1 (Anzeigeordnung)
    def test_blocked_package_keeps_its_saved_position_after_save(self):
        """Review M1 — BLOCKIERT-Paket behält die gezogene Position.

        Vorbedingung: TICKETS.md mit offenem T1 (zuerst) und gesperrtem T0
        (BLOCKIERT); kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des BLOCKIERT-Pakets T0 fokussieren, „ArrowUp“
        drücken (T0 rückt an die erste Position) und „Speichern“ klicken.
        Erwartet: project.env enthält PACKAGE_ORDER mit T0 vor T1; nach
        komplettem Neuöffnen der Projektseite zeigt die Karte weiterhin T0
        vor T1; die T0-Zeile trägt die BLOCKIERT-Pille und die
        „priorisiert“-Pille, die T1-Zeile die „Standardordnung“-Pille.
        """
        tickets = self.project / "TICKETS.md"
        original = tickets.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: tickets.write_text(original, encoding="utf-8"))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "- [ ] T0 Gesperrt\n  BLOCKIERT: fehlende Freigabe\n",
            encoding="utf-8")

        self.open_work()
        self.assertEqual(
            ["T1", "T0"], self.item_ids(),
            "Standardordnung ohne BLOCKIERT-Paket: "
            + ", ".join(self.item_ids()))

        self.handle_of("T0").focus()
        self.page.keyboard.press("ArrowUp")
        self.wait_until(
            lambda: self.item_ids() == ["T0", "T1"],
            message="ArrowUp am Handle verschob das BLOCKIERT-Paket T0 "
                    "nicht an die erste Position: "
                    + ", ".join(self.item_ids()))
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T0"), text.index("T1"),
            "PACKAGE_ORDER enthält die gezogene Position nicht: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T0", "T1"], self.item_ids(),
            "die Karte verwarf die gezogene Position des BLOCKIERT-Pakets: "
            + ", ".join(self.item_ids()))
        blocked_text = self.items_card().locator(
            ".item", has_text="T0").first.inner_text()
        self.assertIn("BLOCKIERT", blocked_text,
                      "T0-Zeile ohne BLOCKIERT-Pille: " + blocked_text)
        self.assertIn("prioritized", blocked_text,
                      "T0-Zeile ohne „priorisiert“-Pille: " + blocked_text)
        open_text = self.items_card().locator(
            ".item", has_text="T1").first.inner_text()
        # „Speichern“ legt die gesamte sichtbare Zeilenreihenfolge ab,
        # daher ist T1 Teil von PACKAGE_ORDER und priorisiert.
        self.assertIn("prioritized", open_text,
                      "T1-Zeile ist nicht als priorisiert gekennzeichnet: "
                      + open_text)

    # ---------------------------------------- Review M2-Minor (Hinweis fehlt)
    def test_unknown_saved_id_is_reported_and_removed_on_save(self):
        """Review M2-Minor — Unbekannte Kennung wird sichtbar gemeldet.

        Vorbedingung: PACKAGE_ORDER="XX9,T1" abgelegt; XX9 existiert in
        keiner Arbeitsnotiz; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren, danach „Speichern“ klicken.
        Erwartet: die Karte nennt XX9 im Hinweis („Unbekannte Kennungen …“,
        Entfernung beim nächsten Speichern angekündigt) und listet XX9
        nicht als Zeile; nach dem Speichern ist XX9 aus PACKAGE_ORDER
        entfernt (env-Datei), die bekannten Zeilen bleiben und der Hinweis
        verschwindet.
        """
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="XX9,T1"\n', encoding="utf-8")

        self.open_work()
        card = self.items_card()
        card_text = card.inner_text()
        self.assertIn("XX9", card_text,
                      "die Karte nennt die unbekannte Kennung nicht: "
                      + card_text)
        self.assertIn("Unknown IDs", card_text,
                      "kein Hinweistext zur unbekannten Kennung: "
                      + card_text)
        self.assertIn("removed", card_text,
                      "der Hinweis kündigt die Entfernung nicht an: "
                      + card_text)
        self.assertNotIn(
            "XX9", self.item_ids(),
            "die unbekannte Kennung erscheint als Zeile: "
            + ", ".join(self.item_ids()))
        self.assertIn("T1", self.item_ids(),
                      "die bekannte Zeile T1 fehlt: "
                      + ", ".join(self.item_ids()))

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8")
            and "XX9" not in self.env_path.read_text(encoding="utf-8"),
            message="Speichern entfernte XX9 nicht aus PACKAGE_ORDER: "
                    + self.env_path.read_text(encoding="utf-8"))
        env_text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("T1", env_text,
                      "die bekannte Kennung ging beim Speichern verloren: "
                      + env_text)
        self.assertIn("TYPE=generic", env_text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", env_text,
                      "Speichern beschädigte project.env")

        self.wait_until(
            lambda: "XX9" not in self.items_card().inner_text(),
            message="der Hinweis zur unbekannten Kennung verschwand nach "
                    "dem Speichern nicht")
        self.assertIn("T1", self.item_ids(),
                      "die bekannte Zeile T1 verschwand nach dem Speichern: "
                      + ", ".join(self.item_ids()))

    # ------------------------------------------------------------ AK 3 (API)
    def test_priority_api_reports_configured_effective_and_status(self):
        """AK 3 (API-Grundlage) — GET /api/priority (unverändert aus AP11).

        Vorbedingung: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt
        (mit Nachweis), T1/T2 offen, X9 unbekannt.
        Aktion: GET /api/priority?name=proj mit Token stellen und die JSON-
        Antwort auswerten.
        Erwartet: HTTP 200; die Antwort nennt die konfigurierten Einträge
        samt Status (erledigt für T0, fehlt für X9), enthält eine
        effektive Reihenfolge, die T2 vor T1 ohne erledigtes T0 zeigt, und
        eine Meldung.
        """
        write_env = self.env_path.read_text(encoding="utf-8")
        write_env = write_env + 'PACKAGE_ORDER="T2,T0,X9,T1"\n'
        self.env_path.write_text(write_env, encoding="utf-8")
        # Die Fixture-Datei ist geteilt: Nach diesem Test gilt wieder die
        # Standardkonfiguration, damit nachfolgende Tests unverändert laufen.
        self.addCleanup(
            lambda: self.env_path.write_text(
                self.base_env, encoding="utf-8"))

        request = urllib.request.Request(
            f"{self.base}/api/priority?name=proj", method="GET")
        request.add_header("X-Token", self.token)
        with urllib.request.urlopen(request, timeout=20) as response:
            self.assertEqual(200, response.status)
            payload = json.loads(response.read().decode("utf-8"))

        dumped = json.dumps(payload, ensure_ascii=False)
        for identifier in ("T0", "T1", "T2", "X9"):
            self.assertIn(identifier, dumped,
                          "Antwort nennt %s nicht: %s" % (identifier, dumped))
        self.assertIn("erledigt", dumped,
                      "Status erledigt fehlt: " + dumped)
        self.assertIn("fehlt", dumped, "Status fehlt für X9: " + dumped)

        # „order" und „queue" sind Listen von Objekten (id, title, status).
        order = {entry["id"]: entry.get("status", "")
                 for entry in payload.get("order", [])
                 if isinstance(entry, dict) and "id" in entry}
        queue = [entry["id"] for entry in payload.get("queue", [])
                 if isinstance(entry, dict) and "id" in entry]
        self.assertEqual({"T2": "offen", "T0": "erledigt", "X9": "fehlt",
                          "T1": "offen"},
                         order,
                         "Status je konfiguriertem Eintrag falsch: " + dumped)
        self.assertEqual(["T2", "T1"], queue,
                         "effektive Reihenfolge falsch: " + dumped)
        self.assertNotIn("T0", queue,
                         "die erledigte T0 rückt in die effektive "
                         "Reihenfolge: " + dumped)
        self.assertTrue(
            any("meldung" in key.lower() or "message" in key.lower()
                for key in self._keys(payload)),
            "keine Meldung in der Antwort: " + dumped,
        )

    def _keys(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from self._keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._keys(item)



    # ------------------- Review Runde 2, Finding M1 (AK-C/D/E)
    def write_mixed_open_fixture(self):
        """Gemischte offene Quellen: TICKETS mit Prioritäten, FEEDBACK.

        Ersetzt die Fixture durch zwei offene TICKETS-Einträge, deren
        Prioritäten gegen die Dateireihenfolge laufen (T1 zuerst in der
        Datei, aber P1; T2 danach mit P0) und einen offenen
        FEEDBACK-Eintrag F1. Stellt beide Dateien nach dem Test wieder
        her.
        """
        tickets = self.project / "TICKETS.md"
        feedback = self.project / "FEEDBACK.md"
        original_tickets = tickets.read_text(encoding="utf-8")
        original_feedback = feedback.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: (tickets.write_text(original_tickets, encoding="utf-8"),
                     feedback.write_text(original_feedback, encoding="utf-8")))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P1\n\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P0\n",
            encoding="utf-8")
        feedback.write_text(
            "# FEEDBACK\n\n"
            "- [ ] F1 Feedback-Paket\n  Beschreibung: offen\n",
            encoding="utf-8")

    def write_blocked_first_fixture(self):
        """Gesperrtes P0-Paket vor bereitem P1-Paket in TICKETS.md.

        Die Standardordnung des Läufers wählt T0 (BLOCKIERT, P0) vor T1
        (offen, P1); die Dateireihenfolge (d.items) listet T1 zuerst.
        Stellt die Datei nach dem Test wieder her.
        """
        tickets = self.project / "TICKETS.md"
        original = tickets.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: tickets.write_text(original, encoding="utf-8"))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Bereite Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P1\n\n"
            "- [ ] T0 Gesperrt\n  Beschreibung: wartet\n"
            "  BLOCKIERT: fehlende Freigabe\n  Priorität: P0\n",
            encoding="utf-8")

    def row_text(self, identifier):
        """Der Zeilentext eines Kartenpakets inklusive seiner Pillen."""
        row = self.items_card().locator(
            ".item", has_text=identifier).first
        row.wait_for(timeout=10000)
        return row.inner_text()

    def get_priority_payload(self):
        """GET /api/priority?name=proj mit Token als JSON-Antwort."""
        request = urllib.request.Request(
            self.base + "/api/priority?name=proj", method="GET")
        request.add_header("X-Token", self.token)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def package_order_value(self):
        """Der Kennungswert von PACKAGE_ORDER aus project.env als Liste."""
        text = self.env_path.read_text(encoding="utf-8")
        match = re.search(
            r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?([^"\'\n]*)', text)
        if not match:
            return None
        return [token for token in re.split(r"[,;\s]+", match.group(1))
                if token]

    def test_standard_order_display_and_pill_without_configuration(self):
        """AK-C — Karte zeigt die Läufer-Standardordnung samt Pille.

        Vorbedingung: gemischte offene Quellen (TICKETS: T2 mit P0, T1
        mit P1 — T1 steht zuerst in der Datei; FEEDBACK: F1 offen); kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren.
        Erwartet: die Karte listet die offenen Pakete in der Läufer-
        Standardordnung T2 (P0) vor T1 (P1) vor F1 (FEEDBACK dahinter)
        — nicht in der d.items-Dateireihenfolge F1/T1/T2 — und jede
        Zeile trägt die Pille „Standardordnung“.
        """
        self.write_mixed_open_fixture()
        self.open_work()

        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1", "F1"],
            message="die Karte zeigt ohne PACKAGE_ORDER nicht die "
                    "Läufer-Standardordnung (TICKETS nach Priorität vor "
                    "FEEDBACK): " + ", ".join(self.item_ids()))
        for identifier in ("T2", "T1", "F1"):
            self.assertIn(
                "Default order", self.row_text(identifier),
                "Zeile %s trägt nicht die „Standardordnung“-Pille: %r"
                % (identifier, self.row_text(identifier)))

    def test_blank_save_writes_the_displayed_standard_order(self):
        """AK-D — Blankes „Speichern“ legt die Standardordnung ab.

        Vorbedingung: gemischte offene Quellen wie in AK-C; kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet und die Karte
        zeigt die Läufer-Standardordnung.
        Aktion: „Speichern“ ohne jede Verschiebung klicken; danach das
        Projekt neu öffnen, GET /api/priority auswerten und den Läufer
        (``bin/vibe_packages.py select``) abfragen.
        Erwartet: PACKAGE_ORDER enthält genau die angezeigte Reihenfolge
        T2 vor T1 vor F1; nach dem Neuöffnen zeigt die Karte diese
        Reihenfolge mit „priorisiert“-Pille je Zeile; GET nennt sie als
        priorisierte (effektive) Reihenfolge; der Läufer wählt T2 zuerst.
        """
        self.write_mixed_open_fixture()
        self.open_work()
        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1", "F1"],
            message="Vorbedingung verletzt: die Karte zeigt nicht die "
                    "Läufer-Standardordnung: "
                    + ", ".join(self.item_ids()))

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        self.assertEqual(
            ["T2", "T1", "F1"], self.package_order_value(),
            "blankes Speichern legte nicht die angezeigte Standardordnung "
            "ab: " + self.env_path.read_text(encoding="utf-8"))
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        payload = self.get_priority_payload()
        queue = [entry["id"] for entry in payload.get("queue", [])
                 if isinstance(entry, dict) and "id" in entry]
        self.assertEqual(
            ["T2", "T1", "F1"], queue,
            "GET zeigt die gespeicherte Standardordnung nicht als "
            "effektive Reihenfolge: "
            + json.dumps(payload, ensure_ascii=False))

        runner = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parents[2] / "bin"
                 / "vibe_packages.py"),
             "select", "--project", str(self.project)],
            capture_output=True, text=True, check=False, timeout=60,
            env={key: value for key, value in os.environ.items()
                 if not key.startswith("VIBE_")})
        self.assertEqual(
            0, runner.returncode,
            "Läufer-Auswahl schlug fehl: " + runner.stdout + runner.stderr)
        self.assertEqual(
            "T2", runner.stdout.strip(),
            "der Läufer wählt nicht das erste Paket der gespeicherten "
            "Standardordnung: " + runner.stdout)

        self.open_project()
        self.assertEqual(
            ["T2", "T1", "F1"], self.item_ids(),
            "die Karte zeigt nach dem Speichern nicht die übernommene "
            "Standardordnung: " + ", ".join(self.item_ids()))
        for identifier in ("T2", "T1", "F1"):
            self.assertIn(
                "prioritized", self.row_text(identifier),
                "Zeile %s ist nach dem Speichern nicht als priorisiert "
                "gekennzeichnet: %r"
                % (identifier, self.row_text(identifier)))

    def test_blocked_package_appears_in_standard_order_and_keeps_position(
            self):
        """AK-E — BLOCKIERT-Paket steht in der Standardordnung und bleibt.

        Vorbedingung: TICKETS.md mit bereitem offenen T1 (Priorität P1)
        und gesperrtem T0 (BLOCKIERT, Priorität P0); kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren, danach blankes „Speichern“ (ohne
        Verschiebung) klicken und das Projekt neu öffnen.
        Erwartet: die Karte zeigt T0 vor T1 (Läufer-Standardordnung nach
        Priorität), die T0-Zeile trägt BLOCKIERT- und
        „Standardordnung“-Pille; PACKAGE_ORDER enthält T0 vor T1; nach
        dem Neuöffnen behält das gesperrte T0 seine Position (T0 vor T1)
        und ist dort als „priorisiert“ gekennzeichnet — konsistent zum
        bestehenden Verhalten nach gezogener Position.
        """
        self.write_blocked_first_fixture()
        self.open_work()

        self.wait_until(
            lambda: self.item_ids() == ["T0", "T1"],
            message="die Karte zeigt das gesperrte P0-Paket nicht vor dem "
                    "bereiten P1-Paket in der Standardordnung: "
                    + ", ".join(self.item_ids()))
        blocked_text = self.row_text("T0")
        self.assertIn(
            "BLOCKIERT", blocked_text,
            "T0-Zeile ohne BLOCKIERT-Pille: " + blocked_text)
        self.assertIn(
            "Default order", blocked_text,
            "T0-Zeile ohne „Standardordnung“-Pille: " + blocked_text)

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        self.assertEqual(
            ["T0", "T1"], self.package_order_value(),
            "blankes Speichern legte nicht die angezeigte Standardordnung "
            "ab: " + self.env_path.read_text(encoding="utf-8"))

        self.open_project()
        self.assertEqual(
            ["T0", "T1"], self.item_ids(),
            "das gesperrte Paket verlor nach dem Speichern seine "
            "Position: " + ", ".join(self.item_ids()))
        blocked_text = self.row_text("T0")
        self.assertIn(
            "BLOCKIERT", blocked_text,
            "T0-Zeile ohne BLOCKIERT-Pille nach dem Speichern: "
            + blocked_text)
        self.assertIn(
            "prioritized", blocked_text,
            "T0-Zeile ist nach dem Speichern nicht als priorisiert "
            "gekennzeichnet: " + blocked_text)


if __name__ == "__main__":
    unittest.main()
