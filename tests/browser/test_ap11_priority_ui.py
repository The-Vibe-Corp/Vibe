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
    Vor: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt (mit
    Nachweis), T1/T2 offen, X9 unbekannt. Aktion: GET
    /api/priority?name=proj mit Token. Erwartet: HTTP 200; Status je
    Eintrag (T0 erledigt, X9 fehlt), effektive Reihenfolge T2 vor T1
    ohne T0, Meldung vorhanden.

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

    def open_project(self, tab="Arbeit"):
        """Vorbedingung einstellen: Projekt „proj“ öffnen, Register wählen."""
        self.page.goto("about:blank")
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        if tab != "Arbeit":
            self.page.get_by_role("tab", name=tab, exact=True).click()
        panel = self.page.locator("#panel-" + tab.lower())
        panel.wait_for()
        self.assertTrue(panel.is_visible(),
                        "Panel „%s“ ist nicht sichtbar" % tab)
        return panel

    def open_settings(self):
        return self.open_project(tab="Einstellungen")

    def open_work(self):
        return self.open_project(tab="Arbeit")

    def items_card(self):
        """Die Karte „Offene Arbeitspakete“ in der Maske „Arbeit“."""
        card = self.page.locator("#panel-arbeit .card",
                                 has_text="Offene Arbeitspakete").first
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
        return self.items_card().get_by_role("button", name="Speichern",
                                             exact=True).first

    def clear_button(self):
        return self.items_card().get_by_role(
            "button", name=re.compile("Leeren", re.I)).first

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
            0, panel.locator("details", has_text="Priorisierung").count(),
            "Einstellungs-Tab enthält noch einen Abschnitt „Priorisierung“")
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
                "verschieben" in label.lower(),
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


if __name__ == "__main__":
    unittest.main()
