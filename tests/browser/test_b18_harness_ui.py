"""Browserabnahme B18 — Harness nur auswählbar, wenn installiert.

Fachlicher Rahmen
-----------------
Das Ticket B18 verlangt, dass ein nicht installierter Harness (Pi) über die
Oberfläche nicht wirksam gewählt und gespeichert werden kann. Standard und
Initialwert bleiben ``opencode``. Für nicht installierte Harnesses zeigen
Nova und Classic einen Installieren-Knopf mit dem Installationsbefehl aus der
Registry, eine Rückmeldung im Feedback-Bereich und eine erneute Prüfung
(Status und Auswahl aktualisieren sich ohne Neuladen).

Vertrag (``docs/features/B18.md``, verbindlich):

* ``POST /api/harness {action:"use", harness:"pi"}`` prüft vor dem Speichern
  ``vibe_harness.probe``. Ist Pi nicht installiert, antwortet die API mit
  **400** und einer Meldung, die „Auswahl nicht gespeichert“ enthält; die
  Datei ``harness.json`` bleibt unverändert.
* ``POST /api/harness {action:"install", harness:"pi"}`` führt ausschließlich
  den Registry-Befehl aus (Pi: ``npm install -g --ignore-scripts
  @earendil-works/pi-coding-agent``), prüft danach erneut und meldet Erfolg
  bzw. Misserfolg. ``GET /api/harness`` bleibt unverändert.
* Nova (``bin/web/nova-settings.js``): Option nicht installiert →
  ``disabled`` mit Suffix „ (nicht installiert)“; Statuszeile
  „Nicht installiert“; Installieren-Knopf
  ``button[data-nv-action="harness-install"][data-nv-harness="<id>"]``;
  Feedback ``div[data-nv-harness-install-feedback]`` (``[hidden]`` bis zur
  ersten Rückmeldung).
* Classic (``bin/web/app.js``): Option in ``#harness-select`` ``disabled``;
  Knopf ``button.harness-install[data-harness="<id>"]`` (id
  ``harness-install-<id>``); Feedback ``div#harness-install-feedback``
  (``[hidden]`` bis zur ersten Rückmeldung).
* Beide Oberflächen zeigen den persistierten Wert, auch wenn seine Option
  deaktiviert ist; bei Ablehnung wird die Auswahl-Anzeige auf den
  persistierten Wert zurückgesetzt.

Testumgebung
------------
Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``/``VIBE_STATE``/``VIBE_INSTALL``/
``VIBE_RUNTIME``. Im temporären ``PATH`` liegen Attrappen für ``opencode``
und ``npm``; Pi fehlt zunächst. Die ``npm``-Attrappe legt beim Aufruf des
Registry-Befehls eine Pi-Attrappe in denselben Ordner und macht sie
ausführbar — die Installation ist damit nachstellbar, ohne Netz und ohne
echtes npm. Es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von
Loopback.

Testfälle (Name — Vorbedingung — Aktion — Erwartung)
---------------------------------------------------
``test_01_default_is_opencode_and_installed``
    Vorbedingung: frischer Zustand ohne ``harness.json``, Fake-opencode im
    PATH. Aktion: Nova-Einstellungen (Feature ``harness``) und Classic-
    Umgebung öffnen. Erwartung: beide Auswahlen zeigen ``opencode``; die
    Statuszeile nennt opencode „Installiert“ (Classic ebenfalls „Installiert“).
``test_02_missing_pi_is_disabled_with_install_button``
    Vorbedingung: Pi fehlt im PATH. Aktion: beide Oberflächen öffnen.
    Erwartung: Nova-Option ``pi`` ist ``disabled`` und trägt „(nicht
    installiert)“; Statuszeile „Nicht installiert“; Installieren-Knopf
    vorhanden, Registry-Befehl im Textumfeld. Classic: Option in
    ``#harness-select`` ``disabled`` mit Suffix, Knopf
    ``.harness-install[data-harness="pi"]``, Registry-Befehl sichtbar.
``test_03_use_of_missing_pi_is_rejected``
    Vorbedingung: ``harness.json`` enthält ``opencode``, Pi fehlt.
    Aktion: POST ``use`` pi; danach in Nova und Classic Pi erzwingen und
    „übernehmen“ klicken. Erwartung: API 400 mit „Auswahl nicht gespeichert“;
    ``harness.json`` unverändert; beide Oberflächen zeigen die Meldung und
    setzen die Auswahl auf ``opencode`` zurück.
``test_04a_install_from_nova_enables_pi``
    Vorbedingung: Pi fehlt, Fake-npm im PATH. Aktion: Installieren-Knopf in
    Nova klicken. Erwartung: Feedback-Bereich sichtbar mit „Installation
    abgeschlossen“; frisches ``GET /api/harness`` meldet Pi installiert;
    Option ``pi`` aktiviert, Status „Installiert“, Knopf verschwunden.
``test_04b_install_from_classic_enables_pi``
    Wie 4a, jedoch über den Classic-Knopf und ``#harness-install-feedback``.
``test_05_selected_pi_persists_in_file_and_both_views``
    Vorbedingung: Pi-Attrappe im PATH (installiert). Aktion: in Nova Pi
    wählen und übernehmen; Seite neu laden; Classic öffnen. Erwartung:
    ``GET /api/harness`` meldet ``selected: "pi"``; ``harness.json`` enthält
    ``pi``; beide Ansichten zeigen nach dem Neuladen ``pi`` (Anzeige == Datei).

ROT-PHASE (2026-11-21, vor der Implementierung)
----------------------------------------------
Aufruf::

    PLAYWRIGHT_BROWSERS_PATH="$HOME/vibe-logs/playwright-browsers" \\
      python3 -m unittest discover -s tests/browser \\
      -p 'test_b18_harness_ui.py' -v

Ergebnis: 6 Tests, 5 FAIL, 1 ok.

* ``test_01`` — FAIL (AssertionError): Classic zeigt als Statuszeile
  „opencode (opencode) – Version 2.1.4“; der Vertrag verlangt dort
  „Installiert“. Die Nova-Seite ist bereits grün (Bestand); der Fall ist
  über die Classic-Statuszeile rot.
* ``test_02`` — FAIL (AssertionError): die Nova-Option ``pi`` trägt kein
  ``disabled`` und keinen Suffix; Installieren-Knopf und Feedback fehlen.
  Das geforderte Verhalten existiert nicht.
* ``test_03`` — FAIL (AssertionError): ``POST /api/harness {action:"use",
  harness:"pi"}`` antwortet 200 („Gespeichert: pi“) statt 400; der
  Probe-Guard fehlt.
* ``test_04a`` — FAIL (AssertionError): ``div[data-nv-harness-install-
  feedback]`` existiert nicht (count 0); der Nova-Installationspfad fehlt.
* ``test_04b`` — FAIL (AssertionError): ``div#harness-install-feedback``
  existiert nicht; der Classic-Installationspfad fehlt.
* ``test_05`` — ok: Bestandsverhalten (installiertes Pi ist wählbar, Datei,
  API und beide Ansichten bleiben konsistent). Der Fall ist eine
  Regressionsschranke und kann in der Rotphase nicht fehlschlagen, weil B18
  dieses Verhalten nicht ändert; er sichert es gegen die neuen Eingriffe ab.
"""
import http.client
import json
import os
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

PI_COMMAND = "npm install -g --ignore-scripts @earendil-works/pi-coding-agent"

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

FAKE_PI = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf '0.72.0\\n'
    exit 0
    ;;
  --list-models)
    printf 'anthropic/claude-sonnet\\n'
    exit 0
    ;;
esac
exit 2
"""

# Die Attrappe erkennt ausschließlich den im Vertrag festgelegten
# Registry-Befehl und legt dann eine Pi-Attrappe neben sich selbst ab.
FAKE_NPM = """#!/usr/bin/env bash
set -eu
case " $* " in
  *" @earendil-works/pi-coding-agent "*)
    ;;
  *)
    printf 'unerwarteter npm-Aufruf: %s\\n' "$*" >&2
    exit 3
    ;;
esac
dir="$(cd "$(dirname "$0")" && pwd)"
cat > "$dir/pi" <<'PI'
#!/usr/bin/env bash
case "$1" in
  --version)
    printf '0.72.0\\n'
    exit 0
    ;;
  --list-models)
    printf 'anthropic/claude-sonnet\\n'
    exit 0
    ;;
esac
exit 2
PI
chmod 755 "$dir/pi"
printf 'added 1 package\\n'
exit 0
"""

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


class HarnessUiTest(unittest.TestCase):
    """Dashboard, Browser, Attrappen und isolierter Zustand."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.install = cls.root / "_toolchain"
        cls.install.mkdir()
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        (cls.root / "tmp").mkdir()
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("npm", FAKE_NPM)):
            path = cls.fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key in ("TMUX", "TMUX_PANE"):
                env.pop(key, None)
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.install),
                "VIBE_RUNTIME": str(cls.logs),
                "HOME": str(cls.home),
                "TMPDIR": str(cls.root / "tmp"),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.logs / "web.token"
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
        # Zustand, den einzelne Fälle verändern, deterministisch zurücksetzen.
        (self.state / "harness.json").unlink(missing_ok=True)
        (self.fakebin / "pi").unlink(missing_ok=True)
        self.api_post("/api/language", {"language": "de"})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            headers = {"Host": f"127.0.0.1:{self.port}",
                       "X-Token": self.token}
            if body is not None:
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_post(self, path, payload):
        return self.api_request("POST", path, payload)

    def api_harness(self):
        status, body = self.api_request("GET", "/api/harness")
        self.assertEqual(200, status, body)
        return json.loads(body)

    def wait_harness(self, predicate, timeout=30, message=""):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.api_harness()
            if predicate(last):
                return last
            self.page.wait_for_timeout(200)
        self.fail(message + " Letzte Antwort: " + repr(last))

    def harness_file(self):
        path = self.state / "harness.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_harness_file(self, harness):
        (self.state / "harness.json").write_text(
            json.dumps({"harness": harness}) + "\n", encoding="utf-8")

    def install_fake_pi(self):
        path = self.fakebin / "pi"
        path.write_text(FAKE_PI, encoding="utf-8")
        path.chmod(0o755)

    def boot_nova(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        if not self.page.locator(
                "main#nv-main[data-nv-view='settings']").count():
            self.page.locator("[data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def open_nova_harness(self):
        self.boot_nova()
        self.open_settings()
        box = self.page.locator("input[data-nv-feature='harness']")
        self.assertEqual(1, box.count(),
                         "Feature-Schalter data-nv-feature='harness' fehlt")
        if not box.is_checked():
            box.check()
        section = self.page.locator("[data-nv-advanced='harness']")
        section.wait_for(state="visible", timeout=25000)
        return section

    def boot_classic_env(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector("nav button[data-t='env']")
        self.page.locator("nav button[data-t='env']").click()
        self.page.wait_for_selector("#harness")
        return self.page.locator("#harness")

    def force_select(self, select, value):
        select.evaluate(
            "(node, value) => { node.value = value;"
            " node.dispatchEvent(new Event('change', {bubbles: true})); }",
            value)

    def nova_rows(self, section):
        rows = section.locator("[data-nv-harness-status] .nv-row")
        return [rows.nth(index).inner_text()
                for index in range(rows.count())]

    def nova_row(self, section, harness):
        for text in self.nova_rows(section):
            if f"({harness})" in text:
                return text
        self.fail(f"Statuszeile für {harness!r} fehlt: "
                  + repr(self.nova_rows(section)))

    def classic_entries(self):
        """Statuszeilen der Classic-Karte ohne die Auswahlliste."""
        return self.page.evaluate(
            """() => Array.from(document.querySelectorAll('#harness > div'))
                 .filter(node => !node.querySelector('select'))
                 .map(node => node.innerText)""")

    def classic_entry_line(self, card, harness):
        entries = self.classic_entries()
        for text in entries:
            if f"({harness})" in text:
                return text
        self.fail(f"Classic-Statuszeile für {harness!r} fehlt: "
                  + repr(entries))

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    # ---------- Fälle ----------

    def test_01_default_is_opencode_and_installed(self):
        """Frischer Zustand: beide Auswahlen opencode, Status Installiert."""
        self.assertIsNone(self.harness_file(),
                          "Vorbedingung verletzt: harness.json existiert")

        section = self.open_nova_harness()
        select = section.locator("select[data-nv-field='harness']")
        self.assertEqual("opencode", select.input_value(),
                         "Nova wählt nicht opencode als Standard")
        self.assertIn("Installiert", self.nova_row(section, "opencode"),
                      "Nova meldet opencode nicht als installiert")
        self.assert_no_page_errors()

        card = self.boot_classic_env()
        self.assertEqual("opencode",
                         self.page.locator("#harness-select").input_value(),
                         "Classic wählt nicht opencode als Standard")
        self.assertIn("Installiert",
                      self.classic_entry_line(card, "opencode"),
                      "Classic meldet opencode nicht als installiert")
        self.assert_no_page_errors()

    def test_02_missing_pi_is_disabled_with_install_button(self):
        """Pi fehlt: Option deaktiviert, Status, Installieren-Knopf."""
        section = self.open_nova_harness()
        option = section.locator(
            "select[data-nv-field='harness'] option[value='pi']")
        self.assertEqual(1, option.count(), "Nova-Option pi fehlt")
        self.assertIsNotNone(option.get_attribute("disabled"),
                             "Nova-Option pi ist ohne Installation wählbar")
        self.assertIn("nicht installiert",
                      (option.inner_text() or "").lower(),
                      "Nova-Option pi trägt nicht den Suffix "
                      "'(nicht installiert)'")
        self.assertIn("Nicht installiert", self.nova_row(section, "pi"),
                      "Nova meldet Pi nicht als nicht installiert")
        button = section.locator(
            "button[data-nv-action='harness-install'][data-nv-harness='pi']")
        self.assertEqual(1, button.count(),
                         "Nova-Installieren-Knopf für Pi fehlt")
        self.assertIn("install", (button.inner_text() or "").lower(),
                      "Der Nova-Knopf heißt nicht Installieren: "
                      + repr(button.inner_text()))
        self.assertIn(PI_COMMAND, section.inner_text(),
                      "Der Registry-Befehl fehlt im Textumfeld des Knopfs")
        self.assert_no_page_errors()

        card = self.boot_classic_env()
        classic_option = self.page.locator(
            "#harness-select option[value='pi']")
        self.assertEqual(1, classic_option.count(),
                         "Classic-Option pi fehlt")
        self.assertIsNotNone(classic_option.get_attribute("disabled"),
                             "Classic-Option pi ist ohne Installation "
                             "wählbar")
        self.assertIn("nicht installiert",
                      (classic_option.inner_text() or "").lower(),
                      "Classic-Option pi trägt nicht den Suffix "
                      "'(nicht installiert)'")
        self.assertIn("nicht installiert",
                      self.classic_entry_line(card, "pi").lower(),
                      "Classic meldet Pi nicht als nicht installiert")
        classic_button = card.locator(
            "button.harness-install[data-harness='pi']")
        self.assertEqual(1, classic_button.count(),
                         "Classic-Installieren-Knopf für Pi fehlt")
        self.assertIn("install", (classic_button.inner_text() or "").lower(),
                      "Der Classic-Knopf heißt nicht Installieren: "
                      + repr(classic_button.inner_text()))
        self.assertIn(PI_COMMAND, card.inner_text(),
                      "Der Registry-Befehl fehlt im Textumfeld des Knopfs")
        self.assert_no_page_errors()

    def test_03_use_of_missing_pi_is_rejected(self):
        """POST use pi → 400; UI zeigt Meldung; Datei bleibt unverändert."""
        self.write_harness_file("opencode")
        before = (self.state / "harness.json").read_bytes()

        status, body = self.api_post(
            "/api/harness", {"action": "use", "harness": "pi"})
        self.assertEqual(400, status,
                         "Die API speicherte einen nicht installierten "
                         "Harness: " + body)
        self.assertIn("Auswahl nicht gespeichert", body,
                      "Die Ablehnung nennt nicht 'Auswahl nicht gespeichert': "
                      + body)
        self.assertEqual(before, (self.state / "harness.json").read_bytes(),
                         "Die abgelehnte Auswahl veränderte harness.json")
        self.assertEqual("opencode", self.harness_file()["harness"])

        section = self.open_nova_harness()
        self.force_select(
            section.locator("select[data-nv-field='harness']"), "pi")
        section.locator("[data-nv-action='harness-use']").click()
        error = section.locator("[data-nv-form-error]")
        error.wait_for(state="visible", timeout=20000)
        self.assertIn("Auswahl nicht gespeichert", error.inner_text(),
                      "Nova zeigt die Ablehnung nicht: "
                      + repr(error.inner_text()))
        self.wait_until(
            lambda: section.locator(
                "select[data-nv-field='harness']").input_value() == "opencode",
            timeout=20000,
            message="Nova setzte die Auswahl nicht auf den persistierten "
                    "Wert opencode zurück")
        self.assertEqual(before, (self.state / "harness.json").read_bytes(),
                         "Die Nova-Auswahl veränderte harness.json")

        card = self.boot_classic_env()
        self.force_select(self.page.locator("#harness-select"), "pi")
        self.page.locator("#harness-use").click()
        self.wait_until(
            lambda: "Auswahl nicht gespeichert" in (card.inner_text() or ""),
            timeout=20000,
            message="Classic zeigt die Ablehnung nicht: "
                    + repr(card.inner_text()))
        self.wait_until(
            lambda: self.page.locator("#harness-select").input_value()
            == "opencode",
            timeout=20000,
            message="Classic setzte die Auswahl nicht auf den persistierten "
                    "Wert opencode zurück")
        self.assertEqual(before, (self.state / "harness.json").read_bytes(),
                         "Die Classic-Auswahl veränderte harness.json")
        self.assert_no_page_errors()

    def test_04a_install_from_nova_enables_pi(self):
        """Klick auf Installieren in Nova installiert Pi und prüft erneut."""
        section = self.open_nova_harness()
        feedback = section.locator(
            "div[data-nv-harness-install-feedback]")
        self.assertEqual(1, feedback.count(),
                         "Nova-Feedbackbereich fehlt vor der Installation")
        self.assertFalse(feedback.is_visible(),
                         "Der Nova-Feedbackbereich ist vor der ersten "
                         "Rückmeldung sichtbar")

        section.locator(
            "button[data-nv-action='harness-install'][data-nv-harness='pi']"
        ).click()
        feedback.wait_for(state="visible", timeout=30000)
        self.assertIn("Installation abgeschlossen", feedback.inner_text(),
                      "Der Nova-Feedbackbereich meldet keinen Erfolg: "
                      + repr(feedback.inner_text()))

        data = self.wait_harness(
            lambda item: any(entry["harness"] == "pi" and entry["installed"]
                             for entry in item.get("harnesses", [])),
            timeout=30000,
            message="GET /api/harness meldet Pi nach der Installation nicht "
                    "als installiert")
        self.assertEqual("opencode", data["selected"],
                         "Die Installation änderte die gespeicherte Auswahl")

        option = section.locator(
            "select[data-nv-field='harness'] option[value='pi']")
        self.wait_until(
            lambda: option.get_attribute("disabled") is None,
            timeout=20000,
            message="Nova aktiviert die Pi-Option nach der Installation nicht")
        self.assertNotIn("nicht installiert",
                         (option.inner_text() or "").lower(),
                         "Die Pi-Option behält den Suffix '(nicht "
                         "installiert)'")
        self.wait_until(
            lambda: section.locator(
                "button[data-nv-action='harness-install']"
                "[data-nv-harness='pi']").count() == 0,
            timeout=20000,
            message="Der Installieren-Knopf bleibt nach der Installation "
                    "sichtbar")
        self.assertIn("Installiert", self.nova_row(section, "pi"),
                      "Nova meldet Pi nach der Installation nicht als "
                      "installiert")
        self.assert_no_page_errors()

    def test_04b_install_from_classic_enables_pi(self):
        """Klick auf Installieren in Classic installiert Pi und prüft erneut."""
        card = self.boot_classic_env()
        feedback = self.page.locator("div#harness-install-feedback")
        self.assertEqual(1, feedback.count(),
                         "Classic-Feedbackbereich fehlt vor der Installation")
        self.assertFalse(feedback.is_visible(),
                         "Der Classic-Feedbackbereich ist vor der ersten "
                         "Rückmeldung sichtbar")

        card.locator("button.harness-install[data-harness='pi']").click()
        feedback.wait_for(state="visible", timeout=30000)
        self.assertIn("Installation abgeschlossen", feedback.inner_text(),
                      "Der Classic-Feedbackbereich meldet keinen Erfolg: "
                      + repr(feedback.inner_text()))

        self.wait_harness(
            lambda item: any(entry["harness"] == "pi" and entry["installed"]
                             for entry in item.get("harnesses", [])),
            timeout=30000,
            message="GET /api/harness meldet Pi nach der Installation nicht "
                    "als installiert")

        option = self.page.locator("#harness-select option[value='pi']")
        self.wait_until(
            lambda: option.get_attribute("disabled") is None,
            timeout=20000,
            message="Classic aktiviert die Pi-Option nach der Installation "
                    "nicht")
        self.wait_until(
            lambda: card.locator(
                "button.harness-install[data-harness='pi']").count() == 0,
            timeout=20000,
            message="Der Classic-Installieren-Knopf bleibt nach der "
                    "Installation sichtbar")
        self.assertIn("Installiert", self.classic_entry_line(card, "pi"),
                      "Classic meldet Pi nach der Installation nicht als "
                      "installiert")
        self.assert_no_page_errors()

    def test_05_selected_pi_persists_in_file_and_both_views(self):
        """Installiertes Pi wählen: Datei, API und beide Ansichten bleiben."""
        self.install_fake_pi()
        section = self.open_nova_harness()
        section.locator("select[data-nv-field='harness']").select_option("pi")
        section.locator("[data-nv-action='harness-use']").click()

        self.wait_until(
            lambda: (self.harness_file() or {}).get("harness") == "pi",
            timeout=20000,
            message="harness.json enthält nach dem Wechsel nicht pi: "
                    + repr(self.harness_file()))
        data = self.api_harness()
        self.assertEqual("pi", data["selected"],
                         "GET /api/harness meldet nicht selected pi: "
                         + repr(data))
        self.wait_until(
            lambda: section.locator(
                "select[data-nv-field='harness']").input_value() == "pi",
            timeout=20000,
            message="Nova zeigt den Wechsel zu pi nicht")

        self.page.reload()
        self.page.locator("main#nv-main").wait_for(
            state="visible", timeout=25000)
        self.open_settings()
        box = self.page.locator("input[data-nv-feature='harness']")
        if box.count() and not box.is_checked():
            box.check()
        section = self.page.locator("[data-nv-advanced='harness']")
        section.wait_for(state="visible", timeout=25000)
        self.assertEqual(
            "pi",
            section.locator("select[data-nv-field='harness']").input_value(),
            "Nova zeigt nach dem Neuladen nicht mehr pi")

        card = self.boot_classic_env()
        self.assertEqual("pi",
                         self.page.locator("#harness-select").input_value(),
                         "Classic zeigt nach dem Neuladen nicht mehr pi")
        self.assertEqual("pi", self.harness_file()["harness"],
                         "Anzeige und harness.json laufen auseinander")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
