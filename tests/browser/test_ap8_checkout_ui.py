"""Browser acceptance tests for the AP8 „Aus GitHub auschecken“ flow.

Das Dashboard läuft als echter Prozess gegen eine Fake-Toolchain in einem
temporären Verzeichnis (Muster von tests/browser/test_ap06_github_ui.py).
Der Auscheckvorgang läuft ausschliesslich gegen ein lokales Bare-Repository
über ``file://``: Es gibt keine echten Netzaufrufe und keinen github.com-Kontakt.
Fehler werden über die Oberfläche gemeldet und dürfen kein halb angelegtes
Projekt hinterlassen (AK5, AK1, AK2, AK4).

Run:

    python3 -m unittest tests.browser.test_ap8_checkout_ui -v
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

from playwright.sync_api import sync_playwright

_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

FAKE_PI = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
exit 2
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
exit 2
"""

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
)

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True, timeout=60)


def git_out(cwd, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60).stdout.strip()


def make_project(root, name):
    """Erzeugt ein minimales bestehendes Projekt mit git und project.env."""
    project = root / name
    project.mkdir(parents=True)
    git(project, "init", "-q", "-b", "main")
    git(project, "commit", "--allow-empty", "-q", "-m", "init")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "project.env").write_text(
        "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8"
    )
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
    return project


def seed_bare(root, name, files):
    """Lokale Bare-Quelle ohne Netz; liefert die file://-Adresse."""
    work = root / "seed" / name
    work.mkdir(parents=True)
    for relative, content in files.items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(work, "init", "-q", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "seed")
    bare = root / "origin" / (name + ".git")
    bare.mkdir(parents=True)
    git(bare, "init", "-q", "--bare")
    git(work, "push", "-q", str(bare), "main")
    git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return "file://" + str(bare)


def write_template(templates, typ, files):
    for relative, content in files.items():
        target = templates / typ / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def build_templates(templates):
    """Lokale Vorlage: Nach dem Clone gelten GENAU diese Einstellungen."""
    write_template(templates, "common", {
        "FEEDBACK.md": "# FEEDBACK A8-LOK-VORLAGE\n",
        "TICKETS.md": "# TICKETS A8-LOK-VORLAGE\n",
        "opencode.json": '{\n  "$schema": "a8-lokale-vorlage"\n}\n',
        ".opencode/agents/test-agent.md": "# Lokale Test-Agent-Vorlage\n",
    })
    write_template(templates, "generic", {
        "AGENTS.md": "# AGENTS fuer {{NAME}}\n",
        ".vibe/project.env": (
            "TYPE=generic\n"
            "REVIEWER=lokal-reviewer\n"
            "TESTER=test-agent\n"
            "SANDBOX=aus\n"
            'VERIFY_QUICK="echo lokal-quick"\n'
            'VERIFY_PACKAGE="echo lokal-paket"\n'
            'VERIFY_FULL="echo lokal-full"\n'
        ),
    })


def wait_for_file_content(path, needle, timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if needle in Path(path).read_text(encoding="utf-8"):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def wait_for_toast(page, pattern, timeout=25.0):
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        texts = []
        for toast in page.locator(".toast").all():
            try:
                texts.append(toast.inner_text())
            except Exception:  # noqa: BLE001 - Toast kann verschwinden
                pass
        if texts:
            last = texts
        for value in texts:
            if re.search(pattern, value, re.IGNORECASE):
                return value
        time.sleep(0.1)
    raise AssertionError(
        "kein Toast passend zu %r; zuletzt gesehen: %r" % (pattern, last)
    )


class CheckoutUiTest(unittest.TestCase):
    """Die Projektliste bietet das Auschecken an (AK5)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.toolchain = cls.root / "_toolchain"
        build_templates(cls.toolchain / "templates")
        (cls.toolchain / "version.json").write_text(
            json.dumps({"version": "0.18.0", "commit": "abcdef1",
                        "installed_at": "2026-11-10"}),
            encoding="utf-8",
        )
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.workspace = cls.root  # VIBE ist die Wurzel des Prüfstands
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        for name, script in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = cls.fakebin / name
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)

        # Bestehendes Projekt, damit die Projektliste nicht leer startet.
        make_project(cls.workspace, "bestand")

        # Lokale Bare-Quellen für den Auschecklauf ohne Netz.
        cls.aushang_url = seed_bare(cls.workspace, "aushang", {
            "README.md": "Aushang-Inhalt\n",
        })
        cls.karte_url = seed_bare(cls.workspace, "karte", {
            "README.md": "Karte-Inhalt\n",
        })

        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.workspace),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.toolchain),
            "VIBE_INSTALL": str(cls.toolchain),
            "VIBE_RUNTIME": str(cls.logs),
            "HOME": str(cls.home),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        cls.token_file = cls.logs / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if cls.token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = cls.token_file.read_text(encoding="utf-8").strip()
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

    # ------------------------------------------------------- helpers
    def open_project_list(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.wait_for_selector(".row", timeout=20000)
        return self.new_project_card()

    def new_project_card(self):
        card = self.page.locator(".card").filter(
            has_text=re.compile("New project", re.I)
        ).first
        card.wait_for(state="visible", timeout=20000)
        return card

    def url_input(self, card):
        """Das URL-Feld der Auscheck-Karte (per Bezeichnung oder Stellvertreter)."""
        inputs = card.locator("input:not([type='checkbox'])")
        pattern = re.compile(r"(URL|Adresse|GitHub|auschecken|Remote)", re.I)
        for index in range(inputs.count()):
            field = inputs.nth(index)
            label = " ".join(filter(None, (
                field.get_attribute("aria-label") or "",
                field.get_attribute("placeholder") or "",
            )))
            if field.is_editable() and pattern.search(label):
                return field
        self.fail(
            "kein URL-Feld gefunden; Felder: %r" %
            [inputs.nth(i).get_attribute("placeholder") or
             inputs.nth(i).get_attribute("aria-label")
             for i in range(inputs.count())]
        )

    def checkout_button(self, card):
        button = card.get_by_role(
            "button", name=re.compile(r"Check out from GitHub", re.I)
        )
        self.assertEqual(button.count(), 1,
                         "Genau ein Auschecken-Knopf wird erwartet")
        return button

    # ------------------------------------------------------- tests
    def test_the_project_list_offers_the_github_checkout_card(self):
        """AK5: Karte „Neues Projekt“ mit URL-Feld und Auschecken-Knopf."""
        card = self.open_project_list()

        self.url_input(card)
        self.checkout_button(card)
        # Bestehende Kartenfunktionen bleiben (kein blockierender Umstand):
        self.assertTrue(card.get_by_role("button").count() >= 1)

    def test_checkout_from_a_local_file_url_creates_and_opens_the_project(self):
        """AK1+AK2+AK5: Auschecken legt das Projekt an, übernimmt lokale
        Einstellungen und öffnet das Projekt."""
        card = self.open_project_list()
        field = self.url_input(card)
        field.fill(self.aushang_url)
        self.checkout_button(card).click()

        # Das neue Projekt entsteht mit lokal übernommenen Einstellungen.
        env_file = self.workspace / "aushang" / ".vibe" / "project.env"
        self.assertTrue(
            wait_for_file_content(env_file, "TESTER=test-agent"),
            "Die lokale Projektvorlage wurde nicht auf das neue Projekt übernommen",
        )
        env_value = env_file.read_text(encoding="utf-8")
        self.assertIn("TYPE=", env_value)
        self.assertNotIn("GITHUB_REPO=", env_value)

        agents_file = self.workspace / "aushang" / "AGENTS.md"
        self.assertTrue(
            wait_for_file_content(agents_file, "# AGENTS fuer"),
            "AGENTS.md ohne die Vorlage",
        )

        # In der Liste auffindbar und geöffnet (Projektansicht im Schaubereich).
        row = self.page.locator(".row").filter(has_text="aushang").first
        row.wait_for(state="visible", timeout=25000)
        heading = self.page.get_by_role("heading", name=re.compile("aushang", re.I))
        heading.wait_for(state="visible", timeout=25000)

        # Remote origin zeigt auf die ausgecheckte Adresse.
        origin = git_out(self.workspace / "aushang",
                         "remote", "get-url", "origin")
        self.assertEqual(origin, self.aushang_url)

        # Der bestehende Projektbestand bleibt in der Liste sichtbar.
        if self.page.url.endswith("#t=" + self.token):
            self.page.locator(".row").filter(has_text="bestand").first \
                .wait_for(state="visible", timeout=10000)

    def test_the_clone_api_creates_the_project_and_requires_the_token(self):
        """AK5: POST /api/clone {url, name} -> {ok, message, project}; nur
        mit gültiger Anmeldung (Token oder Session); Fehler strukturiert."""
        # Die API läuft über die geöffnete Oberfläche (Standardursprung);
        # die Seite muss dafür tatsächlich geladen sein.
        self.open_project_list()
        # Mit Token: Erfolg.
        payload = self.page.evaluate(
            """async ([token, url]) => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    headers: {'X-Token': token, 'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, name: 'karte'})
                });
                return [r.status, await r.json()];
            }""",
            [self.token, self.karte_url],
        )
        status, data = payload
        self.assertEqual(status, 200, data)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("message", data)
        self.assertIn("project", data)
        self.assertTrue((self.workspace / "karte" / ".vibe" / "project.env").exists())

        # Ohne Token: nichts angelegt, strukturierte Fehler. Die geladene
        # Seite hat über boot() bereits ein Session-Cookie erhalten; das ist
        # laut SPEC eine gültige Anmeldung. Die Tokenpflicht wird deshalb mit
        # einer Anfrage ohne jegliche Credentials geprüft.
        without = self.page.evaluate(
            """async () => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    credentials: 'omit',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: '%s', name: 'untersignal'})
                });
                return [r.status, await r.json().catch(() => ({}))];
            }""" % (self.aushang_url,)
        )
        status, data = without
        self.assertTrue(status >= 400 or not data.get("ok"), data)
        self.assertFalse((self.workspace / "untersignal").exists())

        # Mit Token, aber ungültiger Adresse: strukturierte Fehler.
        invalid = self.page.evaluate(
            """async ([token]) => {
                const r = await fetch('/api/clone', {
                    method: 'POST',
                    headers: {'X-Token': token, 'Content-Type': 'application/json'},
                    body: JSON.stringify({url: '://kaputt'})
                });
                return [r.status, await r.json().catch(() => ({}))];
            }""",
            [self.token],
        )
        status, data = invalid
        self.assertTrue(status >= 400 or not data.get("ok"), data)
        self.assertTrue(
            data.get("message") or data.get("error") or not data,
            "keine gemeldete Fehlbegründung",
        )
        self.assertFalse((self.workspace / "kaputt").exists())

    def test_an_invalid_url_reports_an_error_and_keeps_the_form_usable(self):
        """AK4+AK5: Klar gemeldeter Fehler, kein halb angelegtes Projekt, die
        Karte bleibt ohne blockierenden Dialog nutzbar."""
        card = self.open_project_list()
        field = self.url_input(card)
        field.fill("://kaputt")
        self.checkout_button(card).click()

        toast = wait_for_toast(self.page, r".", timeout=25.0)
        self.assertTrue(toast.strip(), "Fehlermeldung fehlt")
        self.assertFalse((self.workspace / "kaputt").exists())
        self.assertFalse(
            self.page.locator(".row").filter(has_text="kaputt").count()
        )
        # Keine blockierende Sackgasse: Feld und Knopf sind erneut nutzbar.
        self.assertTrue(field.is_editable())
        self.assertTrue(self.checkout_button(card).is_visible())


if __name__ == "__main__":
    unittest.main()
