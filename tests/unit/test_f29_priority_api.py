"""HTTP-Abnahme F29 „Priorisierung: Speichern-Fehler und neue Bedienstelle“.

Das Feedback zum Arbeitspaket F29 meldet zwei Defekte:

* Beim Speichern der Priorisierung über das Dashboard bricht
  ``POST /api/priority`` mit
  ``UnboundLocalError: cannot access local variable 'ok' …`` ab; die
  Reihenfolge wird (aus Nutzersicht) nicht gespeichert. (AK 1)
* Ungültige Eingaben müssen weiterhin ohne Absturz mit ``ok: false`` und
  Klartext-Fehlermeldung beantwortet werden, ohne die Ablage zu ändern.
  (AK 2)

Akzeptanzkriterien und Testfälle (unabhängig aus FEEDBACK.md F29,
docs/features/AP11.md und den gemeldeten Defekten abgeleitet, nicht aus dem
Implementierungsdiff):

 1. ``test_post_set_returns_ok_and_writes_package_order`` (AK 1)
    Vor: Testprojekt mit erledigter T0 und offenen T1/T2; project.env ohne
    PACKAGE_ORDER. Aktion: POST /api/priority {name, action:"set",
    order:"T2,T1"} mit Token. Erwartet: HTTP 200, JSON ``ok`` wahr,
    nichtleere Klartext-Meldung, Feld ``priority`` mit aktualisierter
    Ansicht (``queue`` = ["T2","T1"]); project.env enthält PACKAGE_ORDER
    mit T2 vor T1; TYPE/TESTER bleiben.
    Rotphase: aktuell HTTP 500 (UnboundLocalError um ``ok``).
 2. ``test_post_clear_returns_ok_and_empties_package_order`` (AK 1)
    Vor: PACKAGE_ORDER="T2,T1" abgelegt. Aktion: POST action:"clear".
    Erwartet: HTTP 200, ``ok`` wahr, Klartext-Meldung, ``priority`` zeigt
    die Standardordnung (queue ["T1","T2"]); PACKAGE_ORDER ohne Kennung;
    übrige Zeilen bleiben.
 3. ``test_post_set_preserves_other_env_lines`` (AK 1)
    Vor: project.env mit Kommentarzeile, TYPE und TESTER. Aktion: set
    "T2,T1". Erwartet: die Kommentarzeile und TYPE/TESTER bleiben
    erhalten (atomare Änderung, keine Neuordnung der Datei).
 4. ``test_post_set_rejects_unknown_id_without_change`` (AK 2)
    Vor: project.env ohne PACKAGE_ORDER. Aktion: set order="X9,T1".
    Erwartet: kein Absturz (kein 500); JSON ``ok`` falsch mit nichtleerer
    Klartext-Fehlermeldung; project.env byte-identisch.
 5. ``test_post_unknown_action_is_rejected_without_crash`` (AK 2)
    Aktion: action="unsinn". Erwartet: wie 4 (``ok`` falsch, Datei
    unverändert, keine 500).
 6. ``test_post_unknown_project_is_rejected_without_crash`` (AK 2)
    Aktion: name eines unbekannten Projekts. Erwartet: kein Absturz
    (kein 500), strukturierte Fehlerantwort; die project.env des
    Testprojekts bleibt unverändert.

Die Tests starten das echte Dashboard (bin/vibe-web.py) auf einem eigenen
Port mit vollständig isolierten VIBE_*-Pfaden (Muster
tests/browser/test_ap11_priority_ui.py) und sprechen es über urllib an —
kein Chromium nötig. Bewusste Wahl der Ablage: als eigene Unit-Datei, weil
diese Prüfungen nur HTTP/Datei-Ebene betreten und die bestehende
tests/unit/test_ap11_priority.py die Fachlogik ohne Dashboard abdeckt;
die Browserdatei bleibt den AK 3–5 (UI) vorbehalten. Keine produktiven
Pfade, keine echten externen Dienste, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_f29_priority_api -v
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

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


class F29PriorityApiTest(unittest.TestCase):
    """AK 1/2: POST /api/priority des echten, isolierten Dashboards."""

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
        # Eine nachweislich erledigte Aufgabe und zwei offene Aufgaben —
        # dieselbe Fixture wie in tests/browser/test_ap11_priority_ui.py,
        # damit die Statusanzeige der API (erledigt/offen) prüfbar bleibt.
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

    @classmethod
    def tearDownClass(cls):
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

    # ------------------------------------------------------------ Helfer
    def post_priority(self, body):
        """POST /api/priority; liefert (Statuscode, JSON-Antwort).

        HTTP-Fehler (4xx/5xx) werden wie erfolgreiche Antworten als
        strukturierte JSON-Körper zurückgegeben, damit die Tests genau
        zwischen „strukturierte Ablehnung“ und „Absturz (500)“
        unterscheiden können.
        """
        request = urllib.request.Request(
            self.base + "/api/priority",
            data=json.dumps(body).encode("utf-8"),
            method="POST")
        request.add_header("X-Token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw}

    def env_text(self):
        return self.env_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------ AK 1
    def test_post_set_returns_ok_and_writes_package_order(self):
        """AK 1 — Speichern antwortet erfolgreich und legt PACKAGE_ORDER ab."""
        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "T2,T1"})

        self.assertEqual(200, status,
                         "Speichern antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertTrue(payload.get("ok"),
                        "Speichern meldet ok falsch: "
                        + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip(),
                        "Speichern ohne Klartext-Meldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertIn("priority", payload,
                      "Antwort ohne aktualisierte Ansicht (priority): "
                      + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry
                 in payload["priority"].get("queue", [])]
        self.assertEqual(["T2", "T1"], queue,
                         "aktualisierte Ansicht zeigt andere Ordnung: "
                         + json.dumps(payload["priority"],
                                      ensure_ascii=False))

        text = self.env_text()
        self.assertIn("PACKAGE_ORDER", text,
                      "Speichern schrieb kein PACKAGE_ORDER: " + text)
        self.assertLess(text.index("T2"), text.index("T1"),
                        "PACKAGE_ORDER nicht in gewählter Reihenfolge: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

    def test_post_clear_returns_ok_and_empties_package_order(self):
        """AK 1 — Leeren antwortet erfolgreich und stellt die Standardordnung her."""
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="T2,T1"\n', encoding="utf-8")

        status, payload = self.post_priority(
            {"name": "proj", "action": "clear"})

        self.assertEqual(200, status,
                         "Leeren antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertTrue(payload.get("ok"),
                        "Leeren meldet ok falsch: "
                        + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Leeren ohne Klartext-Meldung: "
                        + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry
                 in payload.get("priority", {}).get("queue", [])]
        self.assertEqual(["T1", "T2"], queue,
                         "Leeren zeigte nicht die Standardordnung: "
                         + json.dumps(payload, ensure_ascii=False))

        text = self.env_text()
        self.assertNotRegex(
            text, r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?\s*[^"\'\s]+',
            "Leeren hinterließ Kennungen in PACKAGE_ORDER: " + text)
        self.assertIn("TYPE=generic", text, "Leeren beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Leeren beschädigte project.env")

    def test_post_set_preserves_other_env_lines(self):
        """AK 1 — Speichern erhält die übrigen Zeilen von project.env."""
        self.env_path.write_text(
            "# Projekt-Hinweis\n"
            "TYPE=generic\n"
            "TESTER=test-agent\n",
            encoding="utf-8")

        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "T2,T1"})

        self.assertEqual(200, status,
                         "Speichern antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        text = self.env_text()
        self.assertIn("# Projekt-Hinweis", text,
                      "Kommentarzeile ging verloren: " + text)
        self.assertIn("TYPE=generic", text, "TYPE-Zeile ging verloren: " + text)
        self.assertIn("TESTER=test-agent", text,
                      "TESTER-Zeile ging verloren: " + text)
        self.assertLess(text.index("T2"), text.index("T1"),
                        "PACKAGE_ORDER nicht in gewählter Reihenfolge: " + text)

    # ------------------------------------------------------------ AK 2
    def test_post_set_rejects_unknown_id_without_change(self):
        """AK 2 — Unbekannte Kennung wird ohne Dateiänderung abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "X9,T1"})

        self.assertNotEqual(500, status,
                            "Unbekannte Kennung führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekannte Kennung meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Ablehnung ohne Klartext-Fehlermeldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die Ablehnung veränderte project.env")

    def test_post_unknown_action_is_rejected_without_crash(self):
        """AK 2 — Unbekannte Aktion wird strukturiert abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "proj", "action": "unsinn", "order": "T2,T1"})

        self.assertNotEqual(500, status,
                            "Unbekannte Aktion führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekannte Aktion meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Ablehnung ohne Klartext-Fehlermeldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die unbekannte Aktion veränderte project.env")

    def test_post_unknown_project_is_rejected_without_crash(self):
        """AK 2 — Unbekanntes Projekt wird ohne Absturz abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "does-not-exist", "action": "set", "order": "T2,T1"})

        self.assertNotEqual(500, status,
                            "Unbekanntes Projekt führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekanntes Projekt meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die Anfrage veränderte project.env")


if __name__ == "__main__":
    unittest.main()
