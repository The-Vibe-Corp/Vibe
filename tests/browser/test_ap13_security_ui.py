"""Browserabnahme AP13: Anmeldung und Karte „Zugriffssicherheit“.

Die Fälle leiten sich aus dem Arbeitspaket AP13 (TICKETS.md) und SPEC.md
(„Sicherheit und Datenintegrität") ab. Das echte Dashboard läuft als eigener
Prozess auf einem freien Port mit vollständig isolierten VIBE_*/HOME-Pfaden
(Muster tests/browser/test_ap7_settings_ui.py); Chromium über Playwright aus
dem Nur-Lese-Nutzer-Cache, niemals heruntergeladen, keine echten externen
Dienste.

Erwartete Zielstruktur (vereinbarter Vertrag; die Implementierung folgt
exakt dieser Struktur, die Tests laufen vor der Umsetzung):
- Ohne gültige Berechtigung zeigt das Dashboard eine Anmeldekarte mit einer
  Eingabe (Kennwort oder Token) und einem Knopf „Anmelden“; die normale
  Projektliste ist nicht sichtbar.
- Nach erfolgreichem Anmelden erscheint die normale Oberfläche; der
  ``#t=``-Hash wurde beim Laden einmalig gegen einen Session-Cookie
  eingetauscht, location.hash und sessionStorage.t sind danach leer.
- Globale Ansicht: Karte „Zugriffssicherheit“ zeigt Port, Bind-Adresse,
  Allowlist-Zustand und Passwortstatus; Port/Bind sind änderbar, nach dem
  Speichern erscheint ein Hinweis, dass die Änderung nach einem Neustart
  wirkt, und ui.json im Zustandsordner enthält die neuen Werte.
- In der Karte lässt sich ein Passwort setzen (mindestens 8 Zeichen); mit
  dem Passwort ist die Anmeldung über die Anmeldekarte möglich.
- Die Karte hat den Knopf „Alle Clients zulassen“. Ein Klick öffnet den
  bestehenden Inline-Bestätigungsdialog (askInline-Muster wie bei „Passwort
  entfernen“) mit einer Warnung, dass danach alle Clients im Netz zugreifen
  dürfen; der Bestätigungsknopf sendet POST /api/security mit
  ``{action:'save', allowlist: []}``. Der Server schreibt ui.json ohne
  Allowlist-Einträge und antwortet ok; die Karte lädt die Ansicht neu.
- Nach dem Bestätigen zeigt die Fakt-Zeile „Allowlist“ „alle Clients
  erlaubt“ statt der Netz-Einträge; ui.json enthält keine Allowlist-Einträge
  mehr (leeres Array oder kein allowlist-Schlüssel).
- Der Platzhalter der Allowlist-Eingabe lautet „… (leer = unverändert)“ und
  suggeriert nicht mehr „(leer = alle Clients)“; ein leeres Feld bedeutet
  „nicht ändern“, das Leeren geht nur über den Knopf.

Testfälle
---------
``test_anmeldekarte_ohne_session``
    Vorbedingung: frischer Browser-Kontext ohne Cookies. Aktion: Dashboard
    öffnen. Erwartet: Anmeldekarte sichtbar (Eingabe + Knopf „Anmelden“),
    Projektliste nicht sichtbar.
``test_hash_wird_gegen_session_eingetauscht_und_geleert``
    Vorbedingung: Kontext ohne Cookies. Aktion: ``/#t=<token>`` öffnen.
    Erwartet: Oberfläche erscheint, ``location.hash`` ist leer,
    ``sessionStorage.t`` ist leer, die URL enthält kein Token mehr.
``test_zugriffssicherheit_karte_zeigt_werte``
    Vorbedingung: angemeldet über ``#t=``. Aktion: Karte öffnen/lesen.
    Erwartet: Karte nennt Port (laufender Port), Bind „127.0.0.1“ und den
    Passwortstatus (nicht gesetzt).
``test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json``
    Vorbedingung: angemeldet, kein ui.json. Aktion: Port auf einen anderen
    freien Port ändern, speichern. Erwartet: Hinweis „Neustart“ sichtbar;
    ui.json enthält ``ui_port`` mit dem neuen Wert.
``test_passwort_setzen_und_anmeldung_mit_passwort``
    Vorbedingung: angemeldet. Aktion: Passwort in der Karte setzen; danach
    frischer Kontext ohne Cookies: Passwort in Anmeldekarte eingeben und
    anmelden. Erwartet: Anmeldung gelingt, Oberfläche sichtbar; nach dem
    Löschen der Cookies erscheint wieder die Anmeldekarte (Abmeldung).
``test_alle_clients_zulassen_entfernt_allowlist``
    Vorbedingung: angemeldet; ui.json im Zustandsordner enthält vorab eine
    Allowlist mit mindestens einem Eintrag (192.168.1.0/24). Der Server
    liest ui.json beim Start und nach jeder security-Aktion; deshalb wird
    die Vorbedingung über den authentifizierten POST im angemeldeten
    Browser-Kontext gesetzt und der Schreibvorgang in ui.json verifiziert,
    bevor die Aktion beginnt. Aktion: Karte öffnen, Fakt-Zeile „Allowlist“
    mit dem Eintrag prüfen, Knopf „Alle Clients zulassen“ anklicken,
    Inline-Bestätigung bestätigen. Erwartet: Der Dialog warnt, dass danach
    alle Clients im Netz zugreifen dürfen; danach zeigt die Fakt-Zeile
    „alle Clients erlaubt“ (ohne Netz-Eintrag), ui.json enthält keine
    Allowlist-Einträge mehr und GET /api/security in der gleichen Session
    meldet eine leere/fehlende Allowlist.
``test_allowlist_platzhalter_sagt_leer_ist_unveraendert``
    Vorbedingung: angemeldet, Karte „Zugriffssicherheit“ offen. Aktion:
    Platzhalter der Eingabe mit aria-label „IP-Allowlist“ lesen. Erwartet:
    Er enthält „(leer = unverändert)“ und nicht „(leer = alle Clients)“.

Testbefehl: python3 -m unittest tests.browser.test_ap13_security_ui -v
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
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap7_settings_ui.py); niemals in
# einem Test heruntergeladen.
_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

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


class Ap13SecurityBrowserTest(unittest.TestCase):
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
        cls.state = cls.toolchain
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
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
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
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output
                )
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
        # Jeder Test beginnt in einem frischen Kontext ohne Session-Cookie
        # und ohne gespeicherte ui.json; die Vorbedingungen hängen nicht
        # von der (alphabetischen) Ausführungsreihenfolge der Tests ab.
        ui_json_path = self.state / "ui.json"
        if ui_json_path.exists():
            ui_json_path.unlink()
        self.context = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def login_card(self, page=None):
        """Die Anmeldekarte: Behälter mit Eingabe plus Knopf „Anmelden“."""
        page = page or self.page
        button = page.get_by_role("button", name=re.compile("anmelden", re.I))
        button.wait_for()
        card = page.locator("div.card").filter(has=button)
        card.wait_for()
        self.assertTrue(
            card.locator("input").count() >= 1, "Anmeldekarte ohne Eingabefeld"
        )
        return card

    def login(self, secret, page=None):
        page = page or self.page
        card = self.login_card(page)
        card.locator("input").first.fill(secret)
        card.get_by_role("button", name=re.compile("anmelden", re.I)).first.click()
        self.wait_until(
            lambda: self.project_list_visible(page),
            timeout=10,
            message="Nach dem Anmelden erschien keine Projektliste",
        )

    def project_list_visible(self, page=None):
        return (page or self.page).locator("tr.row").first.is_visible()

    def open_security_card(self):
        self.page.get_by_text("Zugriffssicherheit", exact=False).first.click()
        # Warten auf das konkrete Karten-Merkmal (Review-Minor 6): Der
        # Nav-Knopf trägt denselben Text wie die Karte und wäre schon vor
        # dem Karten-Render sichtbar; div#security existiert erst mit der
        # gerenderten Karte.
        self.wait_until(
            lambda: self.page.locator("div#security").count() > 0,
            message="Karte „Zugriffssicherheit“ (div#security) nicht gefunden",
        )

    def security_card(self):
        return self.page.locator(
            "xpath=//*[contains(text(),'Zugriffssicherheit')]"
            "/ancestor-or-self::*[self::section or self::details or "
            "self::div][1]"
        ).first

    def ui_json(self):
        path = self.state / "ui.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ Testfälle
    def test_anmeldekarte_ohne_session(self):
        """AK Anmeldekarte. Vorbedingung: Kontext ohne Cookies.

        Aktion: Dashboard öffnen. Erwartet: Eingabe + Knopf „Anmelden“
        sichtbar, Projektliste nicht sichtbar.
        """
        self.page.goto(self.base + "/")

        self.login_card()
        self.assertFalse(
            self.project_list_visible(), "Projektliste ohne Anmeldung sichtbar"
        )

    def test_hash_wird_gegen_session_eingetauscht_und_geleert(self):
        """AK Token-Tausch. Vorbedingung: Kontext ohne Cookies.

        Aktion: ``/#t=<token>`` öffnen. Erwartet: Oberfläche sichtbar,
        location.hash leer, sessionStorage.t leer, kein Token in der URL.
        """
        self.page.goto(self.base + "/#t=" + self.token)

        self.wait_until(
            lambda: self.project_list_visible(),
            timeout=10,
            message="Nach dem Token-Eintausch erschien keine Projektliste",
        )
        self.assertEqual(
            self.page.evaluate("location.hash"), "", "Hash blieb stehen"
        )
        self.assertEqual(
            self.page.evaluate("sessionStorage.getItem('t') || ''"),
            "",
            "Token liegt weiter im sessionStorage",
        )
        self.assertNotIn("#t=", self.page.url)

        # Neu laden ohne Hash bleibt angemeldet (Session-Cookie).
        self.page.reload()
        self.wait_until(
            lambda: self.project_list_visible(),
            timeout=10,
            message="Nach dem Neuladen fiel die Session weg",
        )

    def test_zugriffssicherheit_karte_zeigt_werte(self):
        """AK Sicherheitskarte. Vorbedingung: angemeldet über ``#t=``.

        Aktion: Karte „Zugriffssicherheit“ öffnen. Erwartet: Karte nennt den
        laufenden Port, die Bind-Adresse 127.0.0.1 und den Passwortstatus
        (nicht gesetzt).
        """
        self.page.goto(self.base + "/#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        self.open_security_card()
        card_text = self.security_card().inner_text()
        self.assertIn(str(self.port), card_text, "Karte nennt den Port nicht")
        self.assertIn("127.0.0.1", card_text, "Karte nennt die Bind-Adresse nicht")
        self.assertTrue(
            re.search(r"passwort", card_text, re.I),
            "Karte zeigt keinen Passwortstatus",
        )

    def test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json(self):
        """AK Port ändern. Vorbedingung: angemeldet, kein ui.json.

        Aktion: Port auf einen anderen freien Port ändern, speichern.
        Erwartet: Hinweis „Neustart“ sichtbar; ui.json enthält ui_port.
        """
        self.page.goto(self.base + "/#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)
        self.assertIsNone(self.ui_json(), "Vorab existierte schon ui.json")

        self.open_security_card()
        card = self.security_card()
        port_field = card.locator("input").first
        new_port = free_port()
        port_field.fill(str(new_port))
        card.get_by_role("button", name=re.compile("speichern|ändern|setzen", re.I)).first.click()
        self.wait_until(
            lambda: "neustart" in self.page.inner_text("body").lower(),
            timeout=10,
            message="Kein Hinweis auf Neustart nach dem Speichern",
        )
        stored = self.ui_json()
        self.assertIsNotNone(stored, "ui.json wurde nicht geschrieben")
        self.assertEqual(stored.get("ui_port"), new_port)

    def test_passwort_setzen_und_anmeldung_mit_passwort(self):
        """AK Passwort. Vorbedingung: angemeldet.

        Aktion: Passwort in der Karte setzen; frischer Kontext ohne Cookies:
        Anmeldung mit dem Passwort; danach Cookies löschen (Abmeldung).
        Erwartet: Anmeldung gelingt; ohne Cookies erscheint die
        Anmeldekarte wieder.
        """
        self.page.goto(self.base + "/#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        self.open_security_card()
        card = self.security_card()
        password_field = card.locator("input[type=password]").first
        password_field.fill("ap13-ui-paswort-42")
        card.get_by_role(
            "button", name=re.compile("passwort|speichern|setzen", re.I)
        ).first.click()
        # Wirksamer Sync-Punkt (Review-Minor 5): Die frühere Bedingung
        # („ap13-ui-paswort-42 nicht in inner_text") konnte nie fehlschlagen,
        # weil Eingabewerte von type=password nie im Klartext-Text stehen.
        # Der Server bestätigt das Setzen mit der Toast-Meldung
        # „Kennwort gesetzt“; darauf warten wir.
        self.wait_until(
            lambda: "kennwort gesetzt" in self.page.inner_text("body").lower(),
            timeout=10,
            message="Keine Bestätigung „Kennwort gesetzt“ nach dem Speichern",
        )

        # Frischer Kontext ohne Cookies: Anmeldung mit dem Passwort.
        fresh = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        fresh_page = fresh.new_page()
        try:
            fresh_page.goto(self.base + "/")
            self.login("ap13-ui-paswort-42", page=fresh_page)
        finally:
            fresh.close()

        # Abmeldung: ohne Cookies erscheint wieder die Anmeldekarte.
        self.context.clear_cookies()
        self.page.reload()
        self.wait_until(
            lambda: self.page.get_by_role(
                "button", name=re.compile("anmelden", re.I)
            ).count() > 0,
            timeout=10,
            message="Ohne Cookies erschien keine Anmeldekarte",
        )

    def test_alle_clients_zulassen_entfernt_allowlist(self):
        """AK Alle Clients zulassen. Vorbedingung: angemeldet; ui.json enthält
        vorab eine Allowlist mit mindestens einem Eintrag (192.168.1.0/24);
        gesetzt über den authentifizierten POST im angemeldeten Browser-
        Kontext, weil der Server ui.json beim Start lädt und nach jeder
        security-Aktion neu liest (Schreibvorgang wird verifiziert). Aktion:
        Karte öffnen, Fakt-Zeile „Allowlist“ mit Eintrag prüfen, Knopf „Alle
        Clients zulassen“ anklicken, Inline-Bestätigung bestätigen. Erwartet:
        Dialog warnt vor Zugriff aller Clients im Netz; danach Fakt-Zeile
        „alle Clients erlaubt“, ui.json ohne Allowlist-Einträge,
        GET /api/security (gleiche Session) ohne Allowlist.
        """
        self.page.goto(self.base + "/#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        # Vorbedingung: Allowlist-Eintrag über die gleiche Session setzen
        # und den Schreibvorgang in ui.json prüfen.
        saved = self.page.evaluate(
            "async (tok) => { const r = await fetch('/api/security',"
            "{method:'POST',"
            "headers:{'X-Token':tok,'Content-Type':'application/json'},"
            "body: JSON.stringify({action:'save',"
            "allowlist:['192.168.1.0/24']})}); return await r.json(); }",
            self.token,
        )
        self.assertTrue(
            saved.get("ok"),
            "Vorbedingung: Allowlist-Eintrag nicht gesetzt: " + str(saved),
        )
        before = self.ui_json()
        self.assertIsNotNone(
            before, "Vorbedingung: ui.json wurde nicht geschrieben"
        )
        self.assertEqual(
            before.get("allowlist"), ["192.168.1.0/24"],
            "Vorbedingung: ui.json enthält den Allowlist-Eintrag nicht",
        )

        self.open_security_card()
        card = self.page.locator("#security")
        self.wait_until(
            lambda: card.count() == 1, timeout=5,
            message="Karte „Zugriffssicherheit“ (id=security) nicht gerendert",
        )
        self.wait_until(
            lambda: "192.168.1.0/24" in card.inner_text(), timeout=10,
            message="Fakt-Zeile „Allowlist“ zeigt den Eintrag nicht",
        )

        zulassen = card.get_by_role(
            "button", name=re.compile("alle clients zulassen", re.I)
        )
        self.wait_until(
            lambda: zulassen.count() > 0,
            message="Knopf „Alle Clients zulassen“ fehlt in der Sicherheitskarte",
        )
        zulassen.first.click()

        # askInline-Muster (siehe „Passwort entfernen“): ein Bestätigungs-
        # dialog mit Warnung, Bestätigungs- und Abbruchknopf.
        confirm = card.locator("span.confirm")
        self.wait_until(
            lambda: confirm.count() > 0, timeout=5,
            message="Kein Inline-Bestätigungsdialog nach dem Klick",
        )
        dialog_text = confirm.first.inner_text()
        self.assertRegex(
            dialog_text, re.compile("client", re.I),
            "Bestätigungsdialog warnt nicht vor dem Zugriff aller Clients",
        )
        self.assertRegex(
            dialog_text, re.compile("netz", re.I),
            "Bestätigungsdialog warnt nicht vor dem Zugriff im Netz",
        )
        yes = confirm.first.locator("button").filter(
            has_not_text=re.compile("abbrechen", re.I)
        )
        self.assertEqual(
            yes.count(), 1,
            "Bestätigungsdialog ohne genau einen Bestätigungsknopf",
        )
        yes.click()

        self.wait_until(
            lambda: "alle Clients erlaubt" in self.security_card().inner_text(),
            timeout=10,
            message="Fakt-Zeile zeigt nach dem Bestätigen nicht "
                    "„alle Clients erlaubt“",
        )
        self.assertNotIn(
            "192.168.1.0/24", self.security_card().inner_text(),
            "Fakt-Zeile zeigt weiterhin den Netz-Eintrag",
        )

        stored = self.ui_json()
        self.assertIsNotNone(
            stored,
            "ui.json fehlt nach dem Zulassen aller Clients",
        )
        self.assertEqual(
            stored.get("allowlist") or [], [],
            "ui.json enthält weiterhin Allowlist-Einträge",
        )

        view = self.page.evaluate(
            "async () => await (await fetch('/api/security')).json()"
        )
        self.assertTrue(
            view.get("ok"),
            "GET /api/security schlug in der gleichen Session fehl: "
            + str(view),
        )
        self.assertEqual(
            view.get("allowlist") or [], [],
            "GET /api/security meldet weiterhin Allowlist-Einträge",
        )

    def test_allowlist_platzhalter_sagt_leer_ist_unveraendert(self):
        """AK Allowlist-Platzhalter. Vorbedingung: angemeldet, Karte
        „Zugriffssicherheit“ offen. Aktion: Platzhalter der Eingabe mit
        aria-label „IP-Allowlist“ lesen. Erwartet: Er enthält
        „(leer = unverändert)“ und nicht „(leer = alle Clients)“.
        """
        self.page.goto(self.base + "/#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)
        self.open_security_card()

        card = self.page.locator("#security")
        self.wait_until(
            lambda: card.count() == 1, timeout=5,
            message="Karte „Zugriffssicherheit“ (id=security) nicht gerendert",
        )
        allow_input = card.locator('input[aria-label="IP-Allowlist"]')
        self.wait_until(
            lambda: allow_input.count() == 1, timeout=5,
            message="Allowlist-Eingabe (aria-label „IP-Allowlist“) nicht gefunden",
        )
        placeholder = allow_input.get_attribute("placeholder") or ""
        self.assertNotIn(
            "(leer = alle Clients)", placeholder,
            "Platzhalter suggeriert weiterhin, ein leeres Feld setze die "
            "Allowlist auf alle Clients",
        )
        self.assertIn(
            "(leer = unverändert)", placeholder,
            "Platzhalter sagt nicht, dass ein leeres Feld die Allowlist "
            "unverändert lässt",
        )


if __name__ == "__main__":
    unittest.main()
