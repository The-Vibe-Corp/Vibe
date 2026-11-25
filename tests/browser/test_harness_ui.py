"""Harness-Oberfläche: Auswahl, Pi und opencode-Regression.

Aufruf: python3 -m unittest tests.browser.test_harness_ui -v
"""


# ===========================================================================
# Browserabnahme der Harness-Auswahl in der Oberfläche
# ===========================================================================

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

FAKE_PI = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
if [ "$1" = "--list-models" ]; then
  printf 'anthropic/claude-sonnet\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/model-a\\n'
  exit 0
fi
exit 2
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


class HarnessBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1", "installed_at": "2026-11-07"}),
            encoding="utf-8",
        )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.logs),
                "HOME": str(cls.home),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.logs / "web.token"
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

    def open_env(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector("nav button")
        self.page.get_by_role("button", name="Environment").click()
        self.page.wait_for_selector("#harness")

    def test_harness_is_visible_and_pi_can_be_selected(self):
        self.open_env()

        select = self.page.locator("#harness-select")
        self.assertEqual(select.input_value(), "opencode")
        card = self.page.locator("#harness")
        self.assertIn("Pi", card.inner_text())
        self.assertIn("22.19", card.inner_text())
        self.assertIn("pi.dev", card.inner_text())

        select.select_option("pi")
        self.page.locator("#harness-use").click()
        self.page.wait_for_function(
            "document.querySelector('#harness') && document.querySelector('#harness').innerText.includes('Gespeichert')"
        )

        selection = json.loads((self.toolchain / "harness.json").read_text(encoding="utf-8"))
        self.assertEqual(selection["harness"], "pi")

        self.page.reload()
        self.page.wait_for_selector("nav button")
        self.page.get_by_role("button", name="Environment").click()
        self.page.wait_for_selector("#harness")
        self.assertEqual(self.page.locator("#harness-select").input_value(), "pi")

    def test_header_names_the_active_harness(self):
        self.open_env()

        header = self.page.locator("#srv").inner_text()
        self.assertIn("Harness", header)
        self.assertIn("opencode", header)


# ===========================================================================
# Browserabnahme — Harness nur auswählbar, wenn installiert
# ===========================================================================

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

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


PI_COMMAND = "npm install -g --ignore-scripts @earendil-works/pi-coding-agent"

FAKE_OPENCODE_b18 = """#!/usr/bin/env bash
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

FAKE_PI_b18 = """#!/usr/bin/env bash
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
        for name, text in (("opencode", FAKE_OPENCODE_b18), ("npm", FAKE_NPM)):
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
        path.write_text(FAKE_PI_b18, encoding="utf-8")
        path.chmod(0o755)

    def boot_nova(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def _rerender_settings(self):
        """Settings-Ansicht durch einen echten Routenwechsel neu rendern.

        Nach einem Reload kann der erste Render stattfinden, bevor
        ``nova-settings.js`` geladen ist; ``NV.views.settings`` fehlt dann und
        der Router fällt auf die Startseite zurück. Ein Klick auf denselben
        Hash löst kein ``hashchange`` aus, deshalb wird über die Startseite
        navigiert.
        """
        self.page.locator("nav[data-nv-navs] [data-nv-nav='home']").click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=20000)
        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def open_settings(self):
        view = self.page.locator("main#nv-main[data-nv-view='settings']")
        if not view.count():
            self.page.locator(
                "nav[data-nv-navs] [data-nv-nav='settings']").click()
        view.wait_for(state="visible", timeout=20000)
        # Das Sicht-Attribut wird synchron gesetzt, das Gerüst der Ansicht
        # direkt danach erzeugt. Fehlt es, ist der Render auf die Startseite
        # zurückgefallen → Navigation erneut anstoßen.
        if self.page.locator("[data-nv-ssection]").count() == 0:
            self._rerender_settings()

    def wait_for_settings_feature(self, selector, timeout=25, attempt_seconds=8):
        """Warten, bis fillFeatures den Schalter gerendert hat.

        Das Settings-Gerüst ist synchron, die Funktionsschalter entstehen
        asynchron. Fehlt nach einem Zeitfenster sogar das Gerüst, wurde die
        Ansicht vor dem Laden von ``nova-settings.js`` gerendert; dann wird
        die Navigation neu angestoßen und weiter gewartet.
        """
        feature = self.page.locator(selector)
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.fail(
                    "Der Funktions-Schalter " + selector
                    + " erschien nach dem Neuladen nicht (sections="
                    + str(self.page.locator("[data-nv-ssection]").count())
                    + ", inputs="
                    + str(self.page.locator("input[data-nv-feature]").count())
                    + ")")
            try:
                feature.first.wait_for(
                    state="visible",
                    timeout=int(min(attempt_seconds, remaining) * 1000))
                return feature
            except PlaywrightError:
                pass
            if self.page.locator("[data-nv-ssection]").count() == 0:
                self._rerender_settings()
            else:
                self.page.wait_for_timeout(200)

    def wait_harness_section_filled(self, section, timeout=25):
        """Warten, bis fillHarness Auswahl, Status und Feedback aufgebaut hat.

        Die Sektion steht als leeres Gerüst sofort; der Inhalt entsteht erst
        mit ``fillHarness`` (GET /api/harness) nach dem Render, den
        ``setFeature`` auslöst.
        """
        self.wait_until(
            lambda: section.locator(
                "select[data-nv-field='harness'] option").count() >= 1,
            timeout=timeout,
            message="Die Harness-Auswahl der Nova wurde nicht gefüllt")

    def open_nova_harness(self):
        self.boot_nova()
        self.open_settings()
        box = self.wait_for_settings_feature("input[data-nv-feature='harness']")
        self.assertEqual(1, box.count(),
                         "Feature-Schalter data-nv-feature='harness' fehlt")
        if not box.is_checked():
            box.check()
        box.wait_for(state="visible", timeout=20000)
        section = self.page.locator("[data-nv-ssection='harness']")
        section.wait_for(state="visible", timeout=25000)
        self.wait_harness_section_filled(section)
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
        # Echte Hooks: Statuszeilen der Nova sind ``div.nv-card`` direkt in
        # ``[data-nv-harness-status]`` (implementiert, siehe nova-settings.js
        # ``fillHarness``/``draw``); ``.nv-row`` ist Bestand von wegen und
        # existiert nicht mehr.
        rows = section.locator("[data-nv-harness-status] > .nv-card")
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
        # Vertragsableitung: Settings-View-Gerüst ist synchr., fillFeatures
        # läuft nach asynchron — auf das Erscheinen warten, nicht nur auf
        # die View (same as open_nova_harness). Bleibt der Schalter aus, wurde
        # die Ansicht vor dem Laden von nova-settings.js gerendert; dann stößt
        # der Helfer die Navigation erneut an.
        box = self.wait_for_settings_feature("input[data-nv-feature='harness']")
        if not box.is_checked():
            box.check()
        section = self.page.locator("[data-nv-ssection='harness']")
        section.wait_for(state="visible", timeout=25000)
        self.wait_harness_section_filled(section)
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


# ===========================================================================
# Browserabnahme: die Oberfläche stellt sich bei Pi auf Pi um
# ===========================================================================

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


FAKE_PI_f20 = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '1.5.0\\n'
  exit 0
fi
if [ "$1" = "--list-models" ]; then
  printf 'anthropic/claude-sonnet\\n'
  exit 0
fi
exit 2
"""


CATALOG = {
    "schema": 2,
    "version": "2026-10-30.1",
    "stand": "2026-10-30",
    "waehrung": "USD",
    "einheit": "1 Mio. Tokens",
    "hinweis": "Testkatalog für die F20-Browserabnahme.",
    "quellen": [],
    "modelle": [
        {
            "id": "opencode/test-free",
            "name": "Test Free",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models --standalone", "datum": "2026-10-30"},
        },
    ],
}


def mentions_serverless_run(text):
    """Erkennung „Pi läuft ohne opencode-Server“ trotz freier Formulierung."""
    patterns = (
        r"(?i)(?:ohne|kein\w*|nicht|frei von)\s+[^<]{0,60}\bopencode",
        r"(?i)(?:ohne|kein\w*|nicht)\s+[^<]{0,40}\bserver\b",
        r"(?i)\bpi\b[^<]{0,80}(?:ohne|kein\w*|nicht)[^<]{0,40}\bserver\b",
        r"(?i)(?:without|no|not)\s+[^<]{0,60}\bopencode",
        r"(?i)(?:without|no|not)\s+[^<]{0,40}\bserver\b",
        r"(?i)\bpi\b[^<]{0,80}(?:without|no|not)[^<]{0,40}\bserver\b",
    )
    import re as _re
    return any(_re.search(p, text) for p in patterns)


def mentions_pi_limit(text, subject):
    """„Pi-Grenzwert bei <subject>“ in freier Formulierung erkennen."""
    import re as _re
    patterns = (
        r"(?i)(?:kein[eonsr]?|nicht|ohne|nur|limit|grenz\w*)[^<]{0,90}" + subject,
        subject + r"[^<]{0,60}(?:kein[eonsr]?|nicht|ohne|nur)",
    )
    return any(_re.search(p, text) for p in patterns)


class HarnessUiBase(unittest.TestCase):
    """Gemeinsames Nachbildchen: echtes Dashboard, Attrappen, ein Projekt."""

    selection = None  # None = keine Datei (Default opencode), sonst "pi"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1",
                        "installed_at": "2026-11-07"}),
            encoding="utf-8",
        )
        (cls.toolchain / "models.json").write_text(
            json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8"
        )
        if cls.selection is not None:
            (cls.toolchain / "harness.json").write_text(
                json.dumps({"harness": cls.selection}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F20 PI integration\n"
            "  Beschreibung: Umstellung auf Pi\n",
            encoding="utf-8",
        )
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI_f20)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.logs),
                "HOME": str(cls.home),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "PATH": str(fakebin) + os.pathsep + env.get("PATH", ""),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.logs / "web.token"
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

    def open_dashboard(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector("nav button")

    def open_detail(self):
        self.open_dashboard()
        self.page.locator("tr.row").first.click()
        self.page.wait_for_selector("#runstate")

    def open_detail_tab(self, label):
        self.page.get_by_role("tab", name=label).click()

    def open_nav(self, label, tab=None):
        # Nav-Tests müssen die Vorbedingung selbst herstellen (frische Seite
        # startet auf about:blank): Dashboard öffnen, dann den Nav-Knopf
        # anklicken (Muster der übrigen Browser-Suiten). Danach abwarten, bis
        # der Klick das Register gewechselt hat (Klasse „on“ am Zielknopf) –
        # das Registerrendern selbst folgt asynchron.
        self.open_dashboard()
        self.page.get_by_role("button", name=label).click()
        marker = "b.dataset.t" if tab else "b.textContent"
        target = json.dumps(tab if tab else label)
        self.page.wait_for_function(
            "[...document.querySelectorAll('nav button')].some((b) => "
            "b.classList.contains('on') && " + marker + " === " + target + ")"
        )

    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Einstellungsabschnitt auf, falls er als
        <details> umgesetzt ist. Auf der Bestandsstruktur bleibt der Aufruf
        ein No-op."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                assert section.evaluate("el => !!el.open"), \
                    "%s ließ sich nicht aufklappen" % selector

    def open_models_table(self):
        """Klappt die Modell-Liste auf (Muster tests/browser/test_models_ui.py)."""
        details = self.page.locator("#models details").first
        if not details.get_attribute("open"):
            details.locator(":scope > summary").click()


class PiHarnessUiTest(HarnessUiBase):
    """Fallgruppe B: Pi gewählt (harness.json = {"harness":"pi"})."""

    selection = "pi"

    def test_server_box_runs_pi_without_opencode_server_controls(self):
        # AK B1. Vorbedingung: Pi gewählt, Dashboard geöffnet; Aktion: Kopf-
        # leiste lesen; Erwartung: kein „opencode-Server:“-Text, keine Knöpfe
        # „opencode stoppen“/„opencode starten“, Pi-Freiheits-Merkmal sichtbar,
        # „Dashboard beenden“ bleibt.
        self.open_dashboard()
        box = self.page.locator("#srv")
        box.wait_for()
        self.page.wait_for_function(
            "document.querySelector('#srv') && document.querySelector('#srv').innerText.length > 0"
        )
        text = box.inner_text()
        self.assertNotRegex(text, r"opencode-Server:|opencode server:",
                            "Bei Pi bleibt der opencode-Server-Text in der Kopfleiste?")
        self.assertEqual(
            self.page.get_by_role("button", name="Stop opencode").count(), 0)
        self.assertEqual(
            self.page.get_by_role("button", name="Start opencode").count(), 0)
        self.assertNotRegex(text, r"opencode stoppen|Stop opencode")
        self.assertNotIn("Start opencode", text)
        self.assertIn("Stop dashboard", text,
                      "Der Knopf „Dashboard beenden“ darf nicht verschwinden")
        import re
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Kopfleiste nennt die Pi-Laufart nicht: " + text)
        self.assertTrue(
            mentions_serverless_run(text),
            "Kopfleiste ist nicht erkennbar, dass Pi ohne opencode-Server läuft: "
            + text,
        )

    def test_project_detail_has_no_opencode_weblink(self):
        # AK B2. Vorbedingung: Pi gewählt, Projekt geöffnet; Aktion: Detail
        # betrachten; Erwartung: kein Linktext „opencode-Weboberfläche“.
        self.open_detail()
        self.assertEqual(
            self.page.locator('a:has-text("opencode-Weboberfläche")').count(), 0)
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode-Weboberfläche", body)

    def test_models_detail_points_to_pi_list_models(self):
        # AK B5a. Vorbedingung: Pi gewählt, Modellkatalog vorhanden, Katalog-
        # modell fehlt in der Pi-Modellliste; Aktion: Register „Agenten &
        # Modelle“, Modellzeile aufklappen; Erwartung: „pi --list-models“ statt
        # „Nicht in „opencode models““.
        self.open_nav("Agents & Models")
        self.open_models_table()
        row = self.page.locator('tr[data-model-row="opencode/test-free"]')
        row.wait_for()
        row.click()
        detail = self.page.locator('tr[data-model-detail="opencode/test-free"]')
        text = detail.inner_text()
        self.assertNotIn("Nicht in „opencode models“", text)
        self.assertIn("pi --list-models", text,
                      "Aufklapper verweist nicht auf „pi --list-models“: " + text)

    def test_profiles_hint_names_pi_instead_of_opencode_login(self):
        # AK B5b. Vorbedingung: Pi gewählt; Aktion: Register „Agenten &
        # Modelle“, Profilhinweis lesen; Erwartung: Anmelde-Hinweis nennt Pi,
        # „opencode auth login“ erscheint nicht.
        self.open_nav("Agents & Models")
        self.page.wait_for_selector("#agents")
        import re
        self.assertTrue(
            re.search(r"(?i)\bpi\b", self.page.locator("main").inner_text()),
            "Agenten-/Modellansicht erwähnt Pi nicht")
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode auth login", body)

    def test_agents_dir_hint_explains_prompt_source(self):
        # AK B5c. Vorbedingung: Pi gewählt; Aktion: Agenten-Karte lesen;
        # Erwartung: Hinweis erklärt Agentendateien als Prompt-Quelle für Pi.
        self.open_nav("Agents & Models")
        card = self.page.locator("#agents")
        card.wait_for()
        import re
        text = card.inner_text()
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Agenten-Hinweis nennt Pi nicht: " + text)
        self.assertTrue(re.search(r"(?i)prompt", text),
                        "Agenten-Hinweis erklärt die Prompt-Quelle nicht: " + text)

    def test_sandbox_card_describes_pi_runtime(self):
        # AK B6. Vorbedingung: Pi gewählt; Aktion: Projekt → Register
        # „Einstellungen“, Sandbox-Karte lesen; Erwartung: keine „mit eigenem
        # opencode-Server in bubblewrap“-Formulierung, Pi-Laufart erkennbar.
        self.open_detail()
        self.open_detail_tab("Settings")
        card = self.page.locator("#sandbox")
        card.wait_for()
        self.expand_optional("#sandbox")
        import re
        text = card.inner_text()
        self.assertNotIn("opencode-Server in bubblewrap", text)
        self.assertNotIn("mit eigenem opencode-Server", text)
        self.assertTrue(re.search(r"(?i)\bpi\b", text),
                        "Sandbox-Karte nennt die Pi-Laufart nicht: " + text)

    def test_mcp_hint_points_to_pi_limit(self):
        # AK B7. Vorbedingung: Pi gewählt; Aktion: Register „MCP-Tools“ öffnen;
        # Erwartung: kein „opencode mcp auth“-Hinweis, Pi-spezifischer Grenzwert
        # erkennbar.
        self.open_nav("MCP Tools", tab="mcp")
        # #mcpres ist eine leere Ergebnisbox (DOM vorhanden, ohne Inhalt
        # unsichtbar): auf DOM-Präsenz warten, nicht auf Sichtbarkeit.
        self.page.wait_for_selector("#mcpres", state="attached")
        import re
        body = self.page.locator("main").inner_text()
        self.assertNotIn("opencode mcp auth", body)
        self.assertTrue(re.search(r"(?i)\bpi\b", body),
                        "MCP-Hinweis nennt den Pi-Grenzwert nicht: " + body)


class OpencodeRegressionUiTest(HarnessUiBase):
    """Regression: ohne Auswahl (Default opencode) bleiben Texte/Knöpfe wie
    bisher."""

    selection = None

    def test_server_box_keeps_opencode_controls(self):
        # AK Regression B1. Vorbedingung: keine Auswahl; Aktion: Kopfleiste;
        # Erwartung: „opencode-Server:“ und Knopf „opencode starten“ (Server
        # aus) vorhanden, „Dashboard beenden“ bleibt.
        self.open_dashboard()
        box = self.page.locator("#srv")
        self.page.wait_for_function(
            "document.querySelector('#srv') && /opencode[ -]server:/i.test(document.querySelector('#srv').innerText)"
        )
        text = box.inner_text()
        self.assertRegex(text, r"opencode-Server:|opencode server:")
        self.assertIn("Start opencode", text)
        self.assertEqual(
            self.page.get_by_role("button", name="Start opencode").count(), 1)
        self.assertIn("Stop dashboard", text)

    def test_detail_link_and_cards_keep_opencode_wording(self):
        # AK Regression B2/B6 (B11: Ausgabe-Karten entfallen aus der Prüfung).
        # Vorbedingung: keine Auswahl; Aktion: Projekt öffnen, Register
        # lesen; Erwartung: Link „opencode-Weboberfläche“ und Sandbox-Text
        # „mit eigenem opencode-Server in bubblewrap“.
        # B11: Der Ausgabebereich wird komplett neu gebaut (Vertrag
        # tests/browser/test_b11_output_ui.py); die alten Karten #steer-card
        # und #subagents-card sind dort nicht mehr Teil der Oberfläche. Die
        # opencode-Wortwahl dieser Karten wird deshalb nicht mehr geprüft;
        # die fachliche Pi-Sperre bleibt an der API geprüft
        # (tests/unit/test_ap14_output_view_api.py). Weblink- und Sandbox-
        # Regression bleiben unverändert.
        self.open_detail()
        self.assertEqual(
            self.page.locator('a:has-text("opencode-Weboberfläche"), a:has-text("opencode web UI")').count(), 1)
        self.open_detail_tab("Settings")
        sandbox = self.page.locator("#sandbox")
        sandbox.wait_for()
        self.expand_optional("#sandbox")
        self.assertRegex(sandbox.inner_text(),
                         r"opencode-Server in bubblewrap|opencode server inside bubblewrap")
        # „Voreingestellt sind …“ steht in der Karte „Schreibrechte (Agenten)“,
        # nicht in der Sandbox-Karte (Bestandsstruktur bin/web/app.js).
        self.expand_optional("#settings-rechte")
        self.assertRegex(
            self.page.locator(
                ".card", has_text="Write access (agents)").inner_text(),
            r"Voreingestellt sind /tmp/opencode"
            r"|/tmp/opencode and the project directory are preset")

    def test_agents_models_and_mcp_keep_opencode_wording(self):
        # AK Regression B5/B7. Vorbedingung: keine Auswahl; Aktion: Agenten->
        # Modellzeile aufklappen und MCP-Tab öffnen; Erwartung: „Nicht in
        # „opencode models““, „opencode auth login“,	     ~/.config/opencode/agents
        # und „opencode mcp auth“ bleiben.
        self.open_nav("Agents & Models")
        self.open_models_table()
        row = self.page.locator('tr[data-model-row="opencode/test-free"]')
        row.wait_for()
        row.click()
        detail = self.page.locator('tr[data-model-detail="opencode/test-free"]')
        text = detail.inner_text()
        self.assertRegex(text, r"Nicht in „opencode models“|Not in \"opencode models\"")
        agents_card = self.page.locator("#agents")
        agents_card.wait_for()
        agents_text = agents_card.inner_text()
        self.assertRegex(
            agents_text,
            r"Systemweite Agenten liegen unter ~/.config/opencode/agents"
            r"|System-wide agents reside under ~/.config/opencode/agents")
        self.assertNotIn("Pi", agents_text)
        self.page.locator("main").inner_text()
        self.assertIn("opencode auth login", self.page.locator("main").inner_text())
        self.open_nav("MCP Tools", tab="mcp")
        # #mcpres ist eine leere Ergebnisbox (DOM vorhanden, ohne Inhalt
        # unsichtbar): auf DOM-Präsenz warten, nicht auf Sichtbarkeit.
        self.page.wait_for_selector("#mcpres", state="attached")
        self.assertIn("opencode mcp auth", self.page.locator("main").inner_text())


if __name__ == "__main__":
    unittest.main()
