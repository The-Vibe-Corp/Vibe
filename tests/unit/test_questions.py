"""Tests für Rückfragen von Agenten an den Nutzer (F16).

Ein Agent stellt eine Rückfrage in den Laufzeitordner, das Dashboard zeigt sie
mit den angebotenen Auswahlmöglichkeiten an und schreibt die Antwort zurück.
Geprüft werden Modell, CLI, HTTP-API, die ausgelieferte Seite und die
i18n-Wörterbücher. Alle Schreibvorgänge arbeiten in einem temporären
Laufzeitordner.
"""
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
# Seit V-019 besteht die ausgelieferte Seite aus getrennten Dateien. Der Test
# liest HTML und Skript zusammen, damit die Zusagen unverändert geprüft werden.
WEB_PAGE_FILES = (REPO / "bin" / "web" / "classic.html", REPO / "bin" / "web" / "app.js")
I18N = REPO / "bin" / "web" / "i18n.js"
QUESTIONS = REPO / "bin" / "vibe_questions.py"
RUNNER = REPO / "bin" / "vibe-run.sh"

# Die Prüfumgebung kann eine produktive vibe-Umgebung erben. Ohne diese Liste
# würde das Dashboard den echten Agentenordner, Zustandsordner und die echte
# Laufzeit lesen und beschreiben.
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
)


def isolated_env(root, home, port):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(port),
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_module(name, path):
    bin_dir = str(Path(path).parent)
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_questions():
    return load_module("vibe_questions_under_test", QUESTIONS)


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, mit isoliertem VIBE."""
    root = Path(vibe_root)
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(root, root / "home", 8787))
    try:
        return load_module("vibe_questions_cli_under_test", CLI)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def question_id(text):
    match = re.search(r"q[0-9a-f]{12}", text)
    return match.group(0) if match else None


class QuestionStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.questions = load_questions()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, **overrides):
        values = {"text": "Welche Farbe soll der Knopf haben?"}
        values.update(overrides)
        return self.questions.create(self.runtime, **values)

    def test_create_returns_an_open_question_with_options(self):
        qid = self.make(
            project="proj", agent="coder", options=["Rot", "Blau"]
        )

        self.assertRegex(qid, r"^q[0-9a-f]{12}$")
        open_questions = self.questions.open_questions(self.runtime)
        self.assertEqual(len(open_questions), 1)
        question = open_questions[0]
        self.assertEqual(question["id"], qid)
        self.assertEqual(question["project"], "proj")
        self.assertEqual(question["agent"], "coder")
        self.assertEqual(question["text"], "Welche Farbe soll der Knopf haben?")
        self.assertEqual(question["options"], ["Rot", "Blau"])
        self.assertTrue(question["free_text"])
        self.assertIsNone(question["answer"])
        self.assertTrue(question["created"].endswith("Z"))
        stored = json.loads(
            (self.runtime / "questions" / (qid + ".json")).read_text(encoding="utf-8")
        )
        self.assertEqual(stored["id"], qid)
        self.assertNotIn("answer", stored)

    def test_text_and_options_are_trimmed(self):
        qid = self.make(text="  Frage mit Rand  ", options=["  Ja  "])

        question = self.questions.load(self.runtime, qid)

        self.assertEqual(question["text"], "Frage mit Rand")
        self.assertEqual(question["options"], ["Ja"])

    def test_invalid_questions_are_rejected_without_files(self):
        cases = [
            {"text": ""},
            {"text": "   "},
            {"text": "x" * 4001},
            {"text": "a\x00b"},
            {"text": "Frage", "options": ["A", "A"]},
            {"text": "Frage", "options": [""]},
            {"text": "Frage", "options": ["A" * 201]},
            {"text": "Frage", "options": ["A"] * 11},
            {"text": "Frage", "options": "keine Liste"},
            {"text": "Frage", "agent": "a\nb"},
        ]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.questions.create(self.runtime, **values)
        folder = self.runtime / "questions"
        self.assertEqual(
            [] if not folder.exists() else sorted(folder.iterdir()), []
        )

    def test_answer_with_option_removes_the_question_from_the_open_list(self):
        qid = self.make(options=["Rot", "Blau"], free_text=False)

        answer = self.questions.answer(self.runtime, qid, option=1, by="web")

        self.assertEqual(answer["option"], 1)
        self.assertEqual(answer["option_text"], "Blau")
        self.assertEqual(answer["text"], "")
        self.assertEqual(answer["by"], "web")
        self.assertEqual(self.questions.open_questions(self.runtime), [])
        stored = self.questions.load(self.runtime, qid)
        self.assertEqual(stored["answer"]["option_text"], "Blau")
        self.assertEqual(stored["id"], qid)

    def test_free_text_answer_is_stored(self):
        qid = self.make(options=["Rot", "Blau"])

        answer = self.questions.answer(self.runtime, qid, text="  Lieber Grün  ")

        self.assertIsNone(answer["option"])
        self.assertIsNone(answer["option_text"])
        self.assertEqual(answer["text"], "Lieber Grün")
        self.assertEqual(self.questions.open_questions(self.runtime), [])

    def test_invalid_answers_are_rejected_without_writing(self):
        qid = self.make(options=["Ja", "Nein"], free_text=False)
        cases = [
            {},
            {"text": "Hallo"},
            {"option": 2},
            {"option": -1},
            {"option": True},
            {"option": 0, "text": "x" * 4001},
        ]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    self.questions.answer(self.runtime, qid, **values)
        self.assertEqual(len(self.questions.open_questions(self.runtime)), 1)
        self.assertEqual(
            list((self.runtime / "questions").glob("*.answer.json")), []
        )

    def test_second_answer_is_rejected_without_overwriting_the_first(self):
        qid = self.make(options=["Ja", "Nein"])

        first = self.questions.answer(self.runtime, qid, option=0)
        with self.assertRaises(ValueError) as raised:
            self.questions.answer(self.runtime, qid, option=1)

        self.assertIn("bereits beantwortet", str(raised.exception))
        self.assertEqual(self.questions.load(self.runtime, qid)["answer"], first)

    def test_unknown_and_manipulated_ids_are_rejected(self):
        qid = self.make()
        for bad in ("", "q", "q1234", "../" + qid, qid + "/x", "q" + "g" * 12):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.questions.load(self.runtime, bad)
        self.assertIsNotNone(self.questions.load(self.runtime, qid))
        self.assertNotEqual(qid, "q" + "0" * 12)

    def test_structurally_invalid_question_files_are_skipped(self):
        """F16: Eine defekte gespeicherte Frage verdrängt die übrigen nicht.

        Der Agent schreibt in den Rückfrageordner. Eine dort abgelegte Datei
        mit falschen Feldtypen oder übergroßen Werten darf die Anzeige der
        gültigen Fragen nicht verhindern.
        """
        qid = self.make(text="Gute Frage")
        folder = self.runtime / "questions"
        cases = [
            {"text": 1234},
            {"project": ["proj"]},
            {"options": "keine Liste"},
            {"options": ["A"] * (self.questions.MAX_OPTIONS + 1)},
            {"options": ["A" * (self.questions.MAX_OPTION + 1)]},
        ]
        for index, overrides in enumerate(cases):
            broken = "q" + f"{index:012x}"
            record = {
                "id": broken,
                "project": "proj",
                "agent": "",
                "text": "Kaputte Frage",
                "options": [],
                "free_text": True,
                "created": "2026-11-02T00:00:00Z",
            }
            record.update(overrides)
            (folder / (broken + ".json")).write_text(
                json.dumps(record), encoding="utf-8"
            )

        items = self.questions.open_questions(self.runtime)

        self.assertEqual([item["id"] for item in items], [qid])

    def test_wait_times_out_and_returns_a_later_answer(self):
        qid = self.make()

        started = time.monotonic()
        self.assertIsNone(
            self.questions.wait(self.runtime, qid, timeout=0.3, interval=0.05)
        )
        self.assertGreaterEqual(time.monotonic() - started, 0.2)
        self.assertEqual(len(self.questions.open_questions(self.runtime)), 1)

        self.questions.answer(self.runtime, qid, text="Späte Antwort")

        answer = self.questions.wait(self.runtime, qid, timeout=1)
        self.assertEqual(answer["text"], "Späte Antwort")

    def test_project_for_path_uses_only_whole_path_prefixes(self):
        projects = {"proj": "/w/proj", "inner": "/w/proj/inner"}

        self.assertEqual(
            self.questions.project_for_path("/w/proj/src", projects), "proj"
        )
        self.assertEqual(
            self.questions.project_for_path("/w/proj/inner/x", projects), "inner"
        )
        self.assertIsNone(self.questions.project_for_path("/w/proj2", projects))
        self.assertIsNone(self.questions.project_for_path("/w/other", projects))


class QuestionCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.cli = load_cli(self.root)
        self.runtime = self.root / "_logs"

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_ask(list(args))
        return out.getvalue()

    def test_ask_lists_the_question_and_the_answer_is_readable(self):
        text = self.ask(
            "Welche Farbe?", "--option", "Rot", "--option", "Blau",
            "--project", "proj", "--no-wait",
        )

        qid = question_id(text)
        self.assertIsNotNone(qid, text)
        self.assertIn("Rückfrage", text)
        questions = load_questions().open_questions(self.runtime)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["project"], "proj")
        self.assertEqual(questions[0]["options"], ["Rot", "Blau"])

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_answer([qid, "--option", "2"])
        self.assertIn("Blau", out.getvalue())
        self.assertEqual(load_questions().open_questions(self.runtime), [])

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_ask(["--wait", qid, "--timeout", "2"])
        self.assertIn("Antwort: Blau", out.getvalue())

    def test_ask_takes_the_project_from_the_current_directory(self):
        old = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, old)

        text = self.ask("Frage aus dem Projektordner", "--no-wait")

        question = load_questions().open_questions(self.runtime)[0]
        self.assertIsNotNone(question_id(text))
        self.assertEqual(question["project"], "proj")

    def test_ask_times_out_and_names_the_way_to_continue(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as raised:
                self.cli.cmd_ask(["Frage ohne Antwort", "--timeout", "0.2"])

        self.assertEqual(raised.exception.code, 3)
        self.assertIn("vibe ask --wait", out.getvalue())
        qid = question_id(out.getvalue())
        self.assertIsNotNone(qid)
        self.assertIn(
            qid, [entry["id"] for entry in load_questions().open_questions(self.runtime)]
        )

    def test_ask_rejects_an_unknown_project_without_writing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                self.cli.cmd_ask(["Frage", "--project", "gibtsnicht", "--no-wait"])

        self.assertIn("nicht gefunden", str(raised.exception))
        self.assertEqual(load_questions().open_questions(self.runtime), [])

    def test_questions_lists_open_questions_with_their_options(self):
        self.ask("Erste Frage", "--option", "Ja", "--project", "proj", "--no-wait")
        self.ask("Zweite Frage", "--project", "proj", "--no-wait")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_questions()

        text = out.getvalue()
        self.assertIn("Erste Frage", text)
        self.assertIn("1) Ja", text)
        self.assertIn("Zweite Frage", text)


class RunnerPromptTest(unittest.TestCase):
    def test_the_run_prompt_names_the_question_command(self):
        """Der Laufhinweis nennt den Fragbefehl, die Fortsetzung und die
        GH-58-Regel: Im autonomen Modus sind Fragen nicht möglich; der Agent
        kann den Zustand mit ``vibe autonomous status`` prüfen.
        """
        text = RUNNER.read_text(encoding="utf-8")

        self.assertIn("Rückfrage", text)
        self.assertIn('vibe ask "', text)
        self.assertIn("--wait", text)
        self.assertIn("autonom", text.lower())
        # GH-58: Der Hinweis verbindet den autonomen Modus mit „nicht möglich“
        # (Formulierungsfreiheit, aber in derselben Hinweiszeile) und nennt
        # den Statusbefehl, damit der Agent die Einstellung prüfen kann.
        self.assertIn("vibe ask --runtime", text)
        self.assertIn("vibe ask --wait", text)
        self.assertIn("vibe autonomous status", text)
        hint_lines = [
            line for line in text.splitlines() if "autonom" in line.lower()
        ]
        self.assertTrue(
            any("nicht möglich" in line.lower() for line in hint_lines),
            "Der Laufhinweis verbindet autonomen Modus und 'nicht möglich' nicht.",
        )


class QuestionApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
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
        cls.questions = load_questions()

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
        folder = self.log_dir / "questions"
        if folder.exists():
            for path in folder.iterdir():
                path.unlink()
        for name in ("autonomous.json",):
            path = self.log_dir / name
            if path.exists():
                path.unlink()

    def request(self, path, body=None, token=True):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"X-Token": self.token} if token else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers,
            method="GET" if body is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_api_lists_open_questions_with_their_options(self):
        qid = self.questions.create(
            self.log_dir, project="proj", text="Welche Farbe?",
            options=["Rot", "Blau"],
        )

        status, body = self.request("/api/questions")

        self.assertEqual(status, 200)
        self.assertEqual(len(body["questions"]), 1)
        question = body["questions"][0]
        self.assertEqual(question["id"], qid)
        self.assertEqual(question["project"], "proj")
        self.assertEqual(question["text"], "Welche Farbe?")
        self.assertEqual(question["options"], ["Rot", "Blau"])

    def test_api_requires_a_token(self):
        status, body = self.request("/api/questions", token=False)

        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_api_answers_a_question_and_returns_the_open_list(self):
        qid = self.questions.create(
            self.log_dir, project="proj", text="Welche Farbe?", options=["Rot", "Blau"]
        )

        status, body = self.request(
            "/api/questions", {"action": "answer", "id": qid, "option": 1}
        )

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("Antwort gespeichert", body["message"])
        self.assertEqual(body["questions"], [])
        answer = self.questions.load(self.log_dir, qid)["answer"]
        self.assertEqual(answer["option_text"], "Blau")
        self.assertEqual(answer["by"], "web")

        status, body = self.request("/api/questions")
        self.assertEqual(body["questions"], [])

    def test_api_accepts_a_free_text_answer(self):
        qid = self.questions.create(
            self.log_dir, project="proj", text="Wie lautet der Name?"
        )

        status, body = self.request(
            "/api/questions", {"action": "answer", "id": qid, "text": "Willkommen"}
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(
            self.questions.load(self.log_dir, qid)["answer"]["text"], "Willkommen"
        )

    def test_api_rejects_invalid_answers_and_keeps_the_question_open(self):
        qid = self.questions.create(
            self.log_dir, project="proj", text="Welche Farbe?", options=["Rot", "Blau"]
        )

        for payload in (
            {"action": "answer", "id": qid, "option": 7},
            {"action": "answer", "id": qid, "option": "1"},
            {"action": "answer", "id": "", "option": 0},
            {"action": "answer", "id": "q000000000000", "option": 0},
            {"action": "unbekannt", "id": qid},
        ):
            with self.subTest(payload=payload):
                status, body = self.request("/api/questions", payload)
                self.assertEqual(status, 400, body)
                self.assertFalse(body["ok"])

        self.assertEqual(len(self.request("/api/questions")[1]["questions"]), 1)

        first = self.request(
            "/api/questions", {"action": "answer", "id": qid, "option": 0}
        )
        self.assertEqual(first[0], 200)
        second = self.request(
            "/api/questions", {"action": "answer", "id": qid, "option": 1}
        )
        self.assertEqual(second[0], 400)
        self.assertIn("bereits beantwortet", second[1]["message"])

    def test_api_reports_and_switches_the_autonomous_mode(self):
        status, body = self.request("/api/autonomous?name=proj")
        self.assertEqual(status, 200, body)
        self.assertFalse(body["enabled"])

        status, body = self.request(
            "/api/autonomous", {"name": "proj", "action": "on"}
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertTrue(body["enabled"])
        self.assertIn("aktiviert", body["message"])
        self.assertTrue((self.log_dir / "autonomous.json").is_file())

        status, body = self.request("/api/autonomous?name=proj")
        self.assertTrue(body["enabled"])

        status, body = self.request(
            "/api/autonomous", {"name": "proj", "action": "off"}
        )
        self.assertEqual(status, 200, body)
        self.assertFalse(body["enabled"])
        status, body = self.request("/api/autonomous?name=proj")
        self.assertFalse(body["enabled"])

    def test_api_rejects_unknown_autonomous_requests_and_requires_a_token(self):
        status, body = self.request(
            "/api/autonomous", {"name": "proj", "action": "vielleicht"}
        )
        self.assertEqual(status, 400, body)
        self.assertFalse(body["ok"])

        status, body = self.request("/api/autonomous?name=gibtsnicht")
        self.assertEqual(status, 404, body)

        status, body = self.request("/api/autonomous?name=proj", token=False)
        self.assertEqual(status, 403, body)
        status, body = self.request(
            "/api/autonomous", {"name": "proj", "action": "on"}, token=False
        )
        self.assertEqual(status, 403, body)
        self.assertFalse((self.log_dir / "autonomous.json").exists())


def _notify_handler(context):
    """Lokaler opencode-Ersatz, der Zustellungen samt Anmeldung protokolliert."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _auth_ok(self):
            expected = "Basic " + base64.b64encode(
                ("opencode:" + context["password"]).encode("utf-8")
            ).decode("ascii")
            return self.headers.get("Authorization", "") == expected

        def _record(self, body=""):
            with open(context["record"], "a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "method": self.command,
                    "path": self.path,
                    "auth_ok": self._auth_ok(),
                    "body": body,
                }, ensure_ascii=False) + "\n")

        def _reply(self):
            payload = json.dumps({"ok": self._auth_ok()}).encode("utf-8")
            self.send_response(200 if self._auth_ok() else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._record()
            self._reply()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            self._record(body)
            self._reply()

    return Handler


class AutonomousNotifyApiTest(unittest.TestCase):
    """GH-58: Das Dashboard informiert den Agenten des aktiven Laufs (G)."""

    PASSWORD = "gh58-notify-471"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()
        # Der gemeinsame opencode-Port bleibt zuverlässig abgewiesen, damit
        # niemals ein echter Dienst kontaktiert wird.
        cls.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.dead_socket.bind(("127.0.0.1", 0))
        env = isolated_env(cls.root, cls.home, cls.port)
        env["VIBE_OPENCODE_PORT"] = str(cls.dead_socket.getsockname()[1])
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
        cls.runs = load_module(
            "vibe_runs_notify_under_test", REPO / "bin" / "vibe_runs.py"
        )

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
        cls.dead_socket.close()
        cls.tmp.cleanup()

    def setUp(self):
        folder = self.log_dir / "questions"
        if folder.exists():
            for path in folder.iterdir():
                path.unlink()
        for name in (
            "autonomous.json",
            "runs.json",
            "proj.log.state.json",
            "proj.log.server.json",
            "opencode.password",
            "notify.requests.jsonl",
        ):
            path = self.log_dir / name
            if path.exists():
                path.unlink()

        self.record = self.log_dir / "notify.requests.jsonl"
        self.password_file = self.log_dir / "opencode.password"
        self.password_file.write_text(self.PASSWORD, encoding="utf-8")
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _notify_handler({"password": self.PASSWORD, "record": str(self.record)}),
        )
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.addCleanup(self._stop_httpd)
        port = self.httpd.server_address[1]
        (self.log_dir / "proj.log.server.json").write_text(
            json.dumps({
                "url": f"http://127.0.0.1:{port}",
                "port": port,
                "password_file": str(self.password_file),
            }),
            encoding="utf-8",
        )
        self.runs.RunRegistry(self.log_dir).start(
            project=str(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="ses_main",
            run_id="proj-gh58",
            state="running",
        )
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({
                "session": "ses_main",
                "subagents": [{
                    "session": "ses_child",
                    "agent": "tester",
                    "description": "Kind arbeitet",
                    "status": "running",
                    "started": int(time.time()),
                    "ended": 0,
                    "output": "",
                }],
            }),
            encoding="utf-8",
        )

    def _stop_httpd(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def request(self, body):
        request = urllib.request.Request(
            self.base + "/api/autonomous",
            data=json.dumps(body).encode("utf-8"),
            headers={"X-Token": self.token, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def deliveries(self):
        if not self.record.exists():
            return []
        entries = [
            json.loads(line)
            for line in self.record.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            entry for entry in entries
            if entry["method"] == "POST" and "/prompt" in entry["path"]
        ]

    def test_on_and_off_inform_the_agent_of_the_active_run(self):
        """Vorbedingung: Ein Lauf ist im Register ``running``; die Zustandsdatei
        führt die Hauptsession ``ses_main`` und einen laufenden Subagenten; ein
        lokaler Ersatzserver samt Kennwort- und Serverdatei ist vorhanden.

        Aktion: ``POST /api/autonomous`` einmal mit ``on``, einmal mit ``off``.

        Erwartung: Beide Umschaltungen sind erfolgreich; die Antwortmeldung
        enthält case-insensitiv „informiert“; genau zwei Zustellungen gehen an
        ``/api/session/ses_main/prompt`` (nie an den Subagenten), jeweils mit
        gültiger Basic-Auth und nichtleerem Text.

        Signifikanz: GH-58/G — ein Moduswechsel während eines Laufs erreicht den
        Agenten; die Zustellung ist auf die Hauptsession begrenzt.
        """
        for action, enabled in (("on", True), ("off", False)):
            with self.subTest(action=action):
                status, body = self.request({"name": "proj", "action": action})
                self.assertEqual(status, 200, body)
                self.assertTrue(body["ok"], body)
                self.assertEqual(body["enabled"], enabled)
                self.assertIn("informiert", body["message"].lower())

        posts = self.deliveries()
        self.assertEqual(len(posts), 2, posts)
        for post in posts:
            self.assertEqual("/api/session/ses_main/prompt", post["path"], posts)
            self.assertTrue(post["auth_ok"], posts)
            self.assertTrue(post["body"].strip(), posts)

    def test_without_an_active_run_the_toggle_succeeds_without_delivery(self):
        """Vorbedingung: Kein Lauf im Register.

        Aktion: ``POST /api/autonomous`` mit ``on``.

        Erwartung: Das Umschalten gelingt (``ok``, ``enabled``), die Meldung
        nennt „aktiviert“, und es gibt keine Zustellung.

        Signifikanz: GH-58/G — die Benachrichtigung ist best effort und darf
        das Umschalten ohne aktiven Lauf nicht verhindern.
        """
        (self.log_dir / "runs.json").unlink()

        status, body = self.request({"name": "proj", "action": "on"})

        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"], body)
        self.assertTrue(body["enabled"])
        self.assertIn("aktiviert", body["message"])
        self.assertEqual(self.deliveries(), [])


class AutonomousModeTest(unittest.TestCase):
    """Der autonome Modus erlaubt dem Agenten eine eigene Entscheidung (F16)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.mode = load_module(
            "vibe_autonomous_under_test", REPO / "bin" / "vibe_autonomous.py"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_is_off_and_the_state_lives_outside_the_question_folder(self):
        self.assertFalse(self.mode.is_enabled(self.runtime, "proj"))
        self.assertFalse(self.mode.status(self.runtime, "proj")["enabled"])

        self.mode.set_enabled(self.runtime, "proj", True)

        self.assertTrue(self.mode.is_enabled(self.runtime, "proj"))
        self.assertTrue((self.runtime / "autonomous.json").is_file())
        self.assertFalse((self.runtime / "questions" / "autonomous.json").exists())

    def test_projects_are_switched_independently(self):
        self.mode.set_enabled(self.runtime, "proj", True)

        self.assertTrue(self.mode.is_enabled(self.runtime, "proj"))
        self.assertFalse(self.mode.is_enabled(self.runtime, "anderes"))

        self.mode.set_enabled(self.runtime, "anderes", True)
        self.mode.set_enabled(self.runtime, "proj", False)

        self.assertFalse(self.mode.is_enabled(self.runtime, "proj"))
        self.assertTrue(self.mode.is_enabled(self.runtime, "anderes"))

    def test_invalid_project_labels_are_rejected_without_writing(self):
        for bad in ("a\nb", "x" * 121, 5, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.mode.set_enabled(self.runtime, bad, True)
        self.assertFalse((self.runtime / "autonomous.json").exists())

    def test_a_corrupt_state_never_enables_autonomous_mode(self):
        self.runtime.mkdir(parents=True)
        (self.runtime / "autonomous.json").write_text("{kaputt", encoding="utf-8")

        self.assertFalse(self.mode.is_enabled(self.runtime, "proj"))


class AutonomousGuardTest(unittest.TestCase):
    """GH-58: Der zentrale Wächter verhindert Rückfragen im autonomen Modus."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.questions = load_questions()
        self.mode = load_module(
            "vibe_autonomous_guard_under_test", REPO / "bin" / "vibe_autonomous.py"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_refuses_without_writing_a_question(self):
        """Vorbedingung: Der autonome Modus ist für „proj“ eingeschaltet.

        Aktion: Eine Rückfrage wird direkt über den Store angelegt (nicht über
        die CLI).

        Erwartung: ``AutonomousActiveError`` mit „nicht möglich“; im
        Rückfrageordner entsteht keine Datei.

        Signifikanz: GH-58 — der Schutz sitzt zentral, nicht nur im CLI; ein
        Agent kann die Frage nicht am CLI vorbei anlegen.
        """
        self.mode.set_enabled(self.runtime, "proj", True)

        with self.assertRaises(self.questions.AutonomousActiveError) as raised:
            self.questions.create(
                self.runtime, project="proj", text="Welche Farbe?"
            )

        self.assertIn("nicht möglich", str(raised.exception))
        self.assertEqual(self.questions.open_questions(self.runtime), [])
        folder = self.runtime / "questions"
        self.assertEqual(
            sorted(folder.glob("*.json")) if folder.exists() else [],
            [],
        )

    def test_other_projects_and_switched_off_mode_still_ask(self):
        """Vorbedingung: Der Modus ist nur für „proj“ eingeschaltet.

        Aktion: Eine Frage für ein anderes Projekt anlegen; danach den Modus
        für „proj“ ausschalten und dort erneut fragen.

        Erwartung: Beide Fragen entstehen; der Wächter gilt projektweit und
        nur bei aktivem Modus.

        Signifikanz: GH-58 — keine globale Sperre, keine Regression für
        Projekte ohne autonomen Modus.
        """
        self.mode.set_enabled(self.runtime, "proj", True)

        other = self.questions.create(
            self.runtime, project="anderes", text="Frage im anderen Projekt"
        )
        self.mode.set_enabled(self.runtime, "proj", False)
        own = self.questions.create(
            self.runtime, project="proj", text="Frage nach dem Ausschalten"
        )

        self.assertEqual(
            {entry["id"] for entry in self.questions.open_questions(self.runtime)},
            {other, own},
        )


class AutonomousCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.cli = load_cli(self.root)
        self.runtime = self.root / "_logs"
        self.mode = load_module(
            "vibe_autonomous_cli_under_test", REPO / "bin" / "vibe_autonomous.py"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            getattr(self.cli, args[0])(list(args[1:]))
        return out.getvalue()

    def ask(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_ask(list(args))
        return out.getvalue()

    def test_autonomous_mode_can_be_switched_on_off_and_read_from_the_cli(self):
        text = self.run_cli("cmd_autonomous", "on", "--project", "proj")
        self.assertIn("aktiviert", text)
        self.assertTrue(self.mode.is_enabled(self.runtime, "proj"))

        text = self.run_cli("cmd_autonomous", "status", "--project", "proj")
        self.assertIn("aktiv", text)

        text = self.run_cli("cmd_autonomous", "off", "--project", "proj")
        self.assertIn("ausgeschaltet", text)
        self.assertFalse(self.mode.is_enabled(self.runtime, "proj"))

        with self.assertRaises(SystemExit) as raised:
            self.run_cli("cmd_autonomous", "vielleicht", "--project", "proj")
        self.assertIn("on|off|status", str(raised.exception))

    def test_ask_in_autonomous_mode_is_refused_without_creating_a_question(self):
        """Vorbedingung: Der autonome Modus ist für „proj“ eingeschaltet.

        Aktion: „vibe ask“ mit Auswahlmöglichkeiten und langem Zeitlimit.

        Erwartung: Sofortige Rückmeldung, die „Autonomer Modus“ und
        „nicht möglich“ nennt; es entsteht keine Rückfrage-ID und keine offene
        Frage. Kein Warten, kein Exit-Code 3.

        Signifikanz: GH-58 — Fragen sind im autonomen Modus systemisch
        unmöglich (Regression: die Frage wurde angelegt und der Agent wartete).
        """
        self.run_cli("cmd_autonomous", "on", "--project", "proj")

        started = time.monotonic()
        text = self.ask(
            "Welche Farbe?", "--option", "Rot", "--option", "Blau",
            "--project", "proj", "--timeout", "30",
        )

        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("nicht möglich", text)
        self.assertIsNone(question_id(text), text)
        self.assertEqual(load_questions().open_questions(self.runtime), [])

    def test_switching_the_mode_on_during_the_wait_ends_the_question(self):
        """Vorbedingung: Der Modus ist aus; eine Rückfrage wartet, während des
        Wartens wird der Modus eingeschaltet.

        Aktion: Das Warten läuft mit einem langen Zeitlimit.

        Erwartung: Es endet in unter 5 s; die Meldung nennt „Autonomer Modus“,
        „Entscheide selbst“ und „vibe answer“; die Rückfrage bleibt offen, bis
        der Agent sie dokumentiert.

        Signifikanz: GH-58 — Vertrag D (Wartefreigabe), unverändertes
        Kernverhalten von F16.
        """
        def enable():
            time.sleep(0.3)
            self.mode.set_enabled(self.runtime, "proj", True)

        thread = threading.Thread(target=enable)
        thread.start()
        self.addCleanup(thread.join, 5)

        started = time.monotonic()
        text = self.ask("Frage im laufenden Betrieb", "--project", "proj", "--timeout", "30")

        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("Entscheide selbst", text)
        self.assertIn("vibe answer", text)
        qid = question_id(text)
        self.assertIsNotNone(qid)
        self.assertEqual(
            [entry["id"] for entry in load_questions().open_questions(self.runtime)],
            [qid],
        )

    def test_the_agent_records_its_decision_after_the_wait_was_released(self):
        """Vorbedingung: Der Modus ist aus; eine Rückfrage läuft mit Zeitlimit,
        während des Wartens wird der Modus eingeschaltet.

        Aktion: Das Warten endet; der Agent dokumentiert seine Entscheidung mit
        ``vibe answer --by agent``.

        Erwartung: Das Warten endet in unter 5 s; die Meldung nennt
        „Autonomer Modus“, „Entscheide selbst“ und „vibe answer“; die Frage
        bleibt zunächst offen und wird erst durch die Agentenantwort
        geschlossen.

        Signifikanz: GH-58 — ein Moduswechsel während des Wartens befreit den
        Agenten von der Antwortpflicht, ohne die Rückfrage zu verlieren.
        """
        def enable():
            time.sleep(0.3)
            self.mode.set_enabled(self.runtime, "proj", True)

        thread = threading.Thread(target=enable)
        thread.start()
        self.addCleanup(thread.join, 5)

        started = time.monotonic()
        text = self.ask("Welche Farbe?", "--project", "proj", "--timeout", "30")

        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("Entscheide selbst", text)
        self.assertIn("vibe answer", text)
        qid = question_id(text)
        self.assertIsNotNone(qid, text)
        self.assertEqual(
            [entry["id"] for entry in load_questions().open_questions(self.runtime)],
            [qid],
        )

        out = self.run_cli(
            "cmd_answer", qid, "--text", "Ich nehme Blau", "--by", "agent"
        )

        self.assertIn("Ich nehme Blau", out)
        answer = load_questions().load(self.runtime, qid)["answer"]
        self.assertEqual(answer["by"], "agent")
        self.assertEqual(load_questions().open_questions(self.runtime), [])

    def test_the_released_wait_names_the_option_that_must_be_chosen(self):
        """Vorbedingung: Der Modus ist aus; eine Rückfrage mit fester Auswahl
        (``--no-free``) läuft, während des Wartens wird der Modus eingeschaltet.

        Aktion: Der Agent beantwortet die offene Frage mit ``--option 2`` und
        ``--by agent``.

        Erwartung: Die Freigabe-Meldung nennt „Autonomer Modus“, „Entscheide
        selbst“, „vibe answer“ und die konkrete Form ``--option <nummer>``; die
        Agentenantwort wird mit Auswahltext und Quelle gespeichert.

        Signifikanz: GH-58 — auch bei fester Auswahl bleibt die
        Dokumentationspflicht des Agenten eindeutig.
        """
        def enable():
            time.sleep(0.3)
            self.mode.set_enabled(self.runtime, "proj", True)

        thread = threading.Thread(target=enable)
        thread.start()
        self.addCleanup(thread.join, 5)

        started = time.monotonic()
        text = self.ask(
            "Welche Farbe?", "--option", "Rot", "--option", "Blau",
            "--no-free", "--project", "proj", "--timeout", "30",
        )

        self.assertLess(time.monotonic() - started, 5)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("Entscheide selbst", text)
        self.assertIn("vibe answer", text)
        self.assertIn("--option <nummer>", text)
        qid = question_id(text)
        self.assertIsNotNone(qid, text)
        self.assertEqual(
            [entry["id"] for entry in load_questions().open_questions(self.runtime)],
            [qid],
        )

        self.run_cli("cmd_answer", qid, "--option", "2", "--text", "Blau", "--by", "agent")
        answer = load_questions().load(self.runtime, qid)["answer"]
        self.assertEqual(answer["option_text"], "Blau")
        self.assertEqual(answer["text"], "Blau")
        self.assertEqual(answer["by"], "agent")

    def test_unknown_projects_and_actions_are_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_cli("cmd_autonomous", "on", "--project", "gibtsnicht")
        self.assertFalse((self.runtime / "autonomous.json").exists())


class WorktreeAutonomousTest(unittest.TestCase):
    """GH-58: Projektauflösung aus der Arbeitskopie und Wächter im CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.cli = load_cli(self.root)
        self.runtime = self.root / "_logs"
        self.runtime.mkdir(parents=True)
        self.worktree = self.runtime / "worktrees" / "gh58-wt"
        self.worktree.mkdir(parents=True)
        self.mode = load_module(
            "vibe_autonomous_worktree_under_test", REPO / "bin" / "vibe_autonomous.py"
        )
        self.runs = load_module(
            "vibe_runs_worktree_under_test", REPO / "bin" / "vibe_runs.py"
        )
        self.questions = load_questions()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            getattr(self.cli, args[0])(list(args[1:]))
        return out.getvalue()

    def ask(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_ask(list(args))
        return out.getvalue()

    def chdir(self, path):
        old = os.getcwd()
        os.chdir(path)
        self.addCleanup(os.chdir, old)

    def register_worktree(self):
        entry = self.runs.WorktreeRegistry(self.runtime).register(
            project=str(self.project),
            id="gh58wt",
            branch="feature/gh-58",
            path=str(self.worktree),
            base_commit="",
        )
        self.assertIsNotNone(entry, "Worktree wurde nicht registriert")
        return entry

    def test_ask_in_a_registered_worktree_refuses_for_the_project(self):
        """Vorbedingung: Der Modus ist nur für „proj“ an; die aktuelle
        Arbeitskopie ist in der Worktree-Registry mit dem Projektpfad
        registriert (Agenten laufen nicht unter dem Projektpfad).

        Aktion: ``vibe ask`` aus der Arbeitskopie ohne ``--project``.

        Erwartung: Das Projekt wird über die Registry aufgelöst; die Frage
        wird sofort mit „Autonomer Modus“ und „nicht möglich“ abgelehnt; keine
        Frage entsteht.

        Signifikanz: GH-58-Kernregression — vorher wurde das Projekt leer
        aufgelöst, die globale Voreinstellung (aus) geprüft und die Frage
        gestellt.
        """
        self.register_worktree()
        self.mode.set_enabled(self.runtime, "proj", True)
        self.chdir(self.worktree)

        started = time.monotonic()
        text = self.ask("Welche Farbe?", "--timeout", "2")

        self.assertLess(time.monotonic() - started, 2)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("nicht möglich", text)
        self.assertIsNone(question_id(text), text)
        self.assertEqual(self.questions.open_questions(self.runtime), [])

    def test_cmd_autonomous_status_resolves_the_project_from_the_worktree(self):
        """Vorbedingung: Modus für „proj“ an; Arbeit in der registrierten
        Arbeitskopie.

        Aktion: ``vibe autonomous status`` ohne ``--project``.

        Erwartung: Der Status meldet „aktiv“ für das aufgelöste Projekt.

        Signifikanz: GH-58 — der Agent kann den Zustand auch aus der
        Arbeitskopie korrekt prüfen.
        """
        self.register_worktree()
        self.mode.set_enabled(self.runtime, "proj", True)
        self.chdir(self.worktree)

        text = self.run_cli("cmd_autonomous", "status")

        self.assertIn("aktiv", text)

    def test_cmd_autonomous_reads_a_given_runtime(self):
        """Vorbedingung: Der Modus ist in einem abweichenden Laufzeitordner für
        „proj“ eingeschaltet.

        Aktion: ``vibe autonomous status --project proj --runtime <ordner>``.

        Erwartung: Der Status liest genau diesen Ordner und meldet „aktiv“.

        Signifikanz: GH-58 — Agents erhalten eine belastbare Prüfmöglichkeit
        für ihren Laufzeitordner.
        """
        other_runtime = self.root / "other_runtime"
        self.mode.set_enabled(other_runtime, "proj", True)

        text = self.run_cli(
            "cmd_autonomous", "status", "--project", "proj",
            "--runtime", str(other_runtime),
        )

        self.assertIn("aktiv", text)


class ServedPageTest(unittest.TestCase):
    def test_served_page_contains_the_question_region_and_polling(self):
        text = "\n".join(
            path.read_text(encoding="utf-8") for path in WEB_PAGE_FILES
        )

        self.assertIn('id="questions"', text)
        # Seit AP21 ist Englisch Standard: die Classic-Shell traegt das
        # woertliche aria-label="Questions"; das deutsche Literal existiert
        # nur noch als tr()-Quellschluessel in app.js/i18n.js.
        self.assertIn("aria-label=\"Questions\"", text)
        self.assertIn("/api/questions", text)
        self.assertIn("pollQuestions", text)
        self.assertIn("'Neue Rückfrage'", text)
        self.assertIn("/api/autonomous", text)
        self.assertIn("Autonomer Modus", text)
        self.assertIn("Autonom entscheiden", text)


class AutonomousTextI18nTest(unittest.TestCase):
    """GH-58: Die neuen Autonomie-Texte sind auch auf Deutsch gedeckt.

    ``t()`` in ``bin/web/i18n.js`` fällt bei fehlendem ``de``-Schlüssel auf
    ``DICTS[DEFAULT_LANG]`` (Englisch) zurück. Beide Oberflächen holen ihre
    Texte über ``tr()`` ab; ohne deutsches Identitätspaar zeigt die deutsche
    Oberfläche deshalb englische Sätze. Geprüft wird reiner Dateitext, ohne
    Browser und ohne Server.
    """

    # Schlüssel = deutscher Quelltext der Oberfläche (``tr(...)``) und damit
    # zugleich der Eintrag in ``DICTS.en``. Der zweite Text enthält Semikola
    # und Punkte; die Muster escapen ihn deshalb mit ``re.escape``.
    CARD_TEXT = (
        "Im autonomen Modus sind Rückfragen nicht möglich; der Agent "
        "entscheidet offene Punkte selbst"
    )
    CLASSIC_TEXT = (
        "Im autonomen Modus sind Rückfragen nicht möglich; der Agent entscheidet "
        "offene Punkte selbst. Rückfragen, die vor dem Einschalten entstanden "
        "sind, beantwortet der Agent selbst und dokumentiert die Entscheidung. "
        "Die Einstellung lässt sich auch während eines Laufs ändern und gilt "
        "nur für dieses Projekt."
    )

    def regions(self):
        """Liefert ``(DICTS.en, DICTS.de)`` als Textbereiche aus ``i18n.js``."""
        text = I18N.read_text(encoding="utf-8")
        marker = "    de: {"
        self.assertIn(marker, text, "DICTS.de nicht gefunden")
        split = text.index(marker)
        return text[:split], text[split:]

    def test_german_dictionary_defines_the_card_explanation(self):
        """Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``/``DICTS.de``;
        ``nova-project.js`` rendert die Kartenerklärung über ``tr()``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: ``DICTS.de`` enthält für den Kartenschlüssel das
        Identitätspaar (Schlüssel und Wert sind derselbe deutsche Text).
        Fehlerfall: ``tr()`` fällt bei deutscher Oberfläche auf den englischen
        Default zurück; die Karte erklärt den autonomen Modus auf Englisch.
        """
        _, de_region = self.regions()
        escaped = re.escape(self.CARD_TEXT)

        self.assertRegex(
            de_region,
            r'"' + escaped + r'"\s*:\s*"' + escaped + r'"',
            "Deutsches Identitätspaar für die Kartenerklärung fehlt in DICTS.de",
        )

    def test_german_dictionary_defines_the_classic_description(self):
        """Vorbedingung: ``bin/web/i18n.js``; ``app.js`` beschreibt den
        autonomen Modus in der klassischen Oberfläche über ``tr()``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: ``DICTS.de`` enthält für den langen GH-58-Schlüssel das
        Identitätspaar mit demselben Text als Wert.
        Fehlerfall: ``tr()`` fällt bei deutscher Oberfläche auf den englischen
        Default zurück; die Classic-Karte zeigt einen englischen Absatz.
        """
        _, de_region = self.regions()
        escaped = re.escape(self.CLASSIC_TEXT)

        self.assertRegex(
            de_region,
            r'"' + escaped + r'"\s*:\s*"' + escaped + r'"',
            "Deutsches Identitätspaar für den Classic-Text fehlt in DICTS.de",
        )

    def test_english_dictionary_translates_the_card_explanation(self):
        """Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``.
        Aktion: Bereich vor ``de: {`` prüfen.
        Erwartung: Der Kartenschlüssel existiert dort mit einem Wert, der vom
        Schlüssel abweicht (echte Übersetzung, nicht das Identitätspaar).
        Fehlerfall: Der englische Default fehlt; die englische Oberfläche
        zeigt den deutschen Quelltext.
        """
        en_region, _ = self.regions()
        escaped = re.escape(self.CARD_TEXT)

        self.assertRegex(
            en_region,
            r'"' + escaped + r'"\s*:\s*"(?!' + escaped + r'")[^"]+"',
            "Englischer Eintrag für die Kartenerklärung fehlt",
        )

    def test_english_dictionary_translates_the_classic_description(self):
        """Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``.
        Aktion: Bereich vor ``de: {`` prüfen.
        Erwartung: Der lange Classic-Schlüssel existiert dort mit einem Wert,
        der vom Schlüssel abweicht.
        Fehlerfall: Der englische Default fehlt; die englische Oberfläche
        zeigt den deutschen Absatz.
        """
        en_region, _ = self.regions()
        escaped = re.escape(self.CLASSIC_TEXT)

        self.assertRegex(
            en_region,
            r'"' + escaped + r'"\s*:\s*"(?!' + escaped + r'")[^"]+"',
            "Englischer Eintrag für den Classic-Text fehlt",
        )


if __name__ == "__main__":
    unittest.main()
