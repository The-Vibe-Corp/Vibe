"""F32 — Subagenten-Parallelisierung: Selbstaufruf eines Agenten.

Fachlicher Auftrag: Jeder Agent außer dem Vibe-Hauptagenten darf — wenn er
selbst als Subagent läuft (``mode: subagent`` oder ``mode: all``) — einen
weiteren Subagenten *seines eigenen Typs* aufrufen, um Arbeit zu
parallelisieren. Das ist ausdrücklich kein Standard: ohne Eintrag im
``permission.task``-Block bleibt der Selbstaufruf gesperrt.

Diese Datei prüft ausschließlich den in F32 vereinbarten Vertrag und arbeitet
in einem vollständig temporären VIBE-/HOME-Verzeichnis. Es findet kein
Modellaufruf, kein tmux-Start und kein Netzzugriff außer Loopback statt;
``models_list`` wird durch eine leere Liste ersetzt, ``opencode`` im
API-Test durch ein Ersatzprogramm.

Zuordnung der Testklassen zu den Akzeptanzkriterien:

* ``SelfSpawnAllowedTest`` — AK1: Selbstaufruf für gewöhnliche Subagenten,
  auch für eine noch nicht existierende Agentendatei über ``own_text``.
* ``VibeSelfSpawnRejectedTest`` — AK2: der Vibe-Agent darf sich nicht selbst
  aufrufen; Parameter ``vibe_agent`` und dessen Deaktivierung mit ``""``.
* ``SelfSpawnModeTest`` — AK4: nur ``subagent``/``all`` (leer zählt wie all),
  ``primary`` wird abgelehnt.
* ``HierarchyCycleTest`` — Selbstkanten sind kein Zyklus, echte Zwei-Agenten-
  Zyklen und gemischte Fälle bleiben abgelehnt.
* ``ForeignAgentRulesTest`` — AK6: unveränderte Regeln für fremde Agenten
  (unbekannt, ``primary``, projektlokal).
* ``AgentTemplateTest`` — AK3: die Vorlage enthält keine Selbstfreigabe.
* ``AgentSelfSpawnApiTest`` — AK2/AK6/Persistenz über die echte Web-API:
  Selbstaufruf wird gespeichert, der Vibe-Agent abgelehnt, ``task_all`` und
  die Scope-Regel bleiben unverändert.

Rotphase (bewusst): Alle Fälle, die den neuen Selbstaufruf erlauben, müssen
am alten Produktcode scheitern (alte Meldung „Ein Agent darf sich nicht selbst
als Subagent aufrufen.“ bzw. fehlende Parameter). Grüne Anker sind die
unveränderten Fremdagenten- und Zyklusregeln, ``task_all``, die Scope-Regel
und die Vorlage ohne Selbstfreigabe.
"""
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"

AGENT_BASE = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
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
    "AGENT",
)


def isolated_env(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f32_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def task_agent(allowed, mode="subagent", model="opencode/test-modell", task=None):
    """Agentendatei mit einem ``permission.task``-Block."""
    lines = ["---", "description: Agent", "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines += ["permission:", "  read: allow", "  edit: deny"]
    if task is not None:
        lines.append("  task: " + task)
    else:
        lines.append("  task:")
        lines.append('    "*": deny')
        for agent in allowed:
            lines.append("    " + agent + ": allow")
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class F32Fixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.other = self.make_project("other")
        self.cli = load_cli(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        return project

    def write_global(self, name, text=AGENT_BASE):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name="lokal", text=AGENT_BASE):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def write_vibe(self, name="vibe-agent", text=VIBE_AGENT):
        path = self.write_global(name, text)
        roles = dict(self.cli.profiles_load().get("rollen", {}))
        roles[name] = "vibe"
        self.set_roles(roles)
        return path


class SelfSpawnAllowedTest(F32Fixture):
    """AK1: Ein gewöhnlicher Subagent darf sich selbst aufrufen."""

    def test_self_spawn_for_regular_subagent_is_allowed_rendered_and_read_back(self):
        # Vorbedingung: globaler Agent 'tester', mode subagent, ohne Vibe-Rolle.
        # Aktion: Selbstaufruf validieren und in den task-Block schreiben.
        # Erwartung: zulässig, der Eigenname steht als allow im Block und wird
        # von der Politik zurückgelesen.
        self.write_global("tester", task_agent([], mode="subagent"))

        allowed = self.cli.agent_validate_hierarchy("tester", ["tester"])

        self.assertEqual(allowed, ["tester"])
        rendered = self.cli.agent_render_task(
            "global", task_agent([], mode="subagent"), ["tester"]
        )
        self.assertIn('"*": deny', rendered)
        self.assertIn("tester: allow", rendered)
        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])
        # Der gerenderte Agent bleibt gültig und verliert keine Felder.
        self.cli.agent_validate(rendered)
        self.assertIn("mode: subagent", rendered)

    def test_new_agent_file_may_enable_self_spawn_via_own_text(self):
        # Vorbedingung: Die Datei 'neu' existiert noch nicht; der Editor
        # übergibt den Entwurf als own_text.
        # Aktion: Selbstaufruf validieren, schreiben und erneut prüfen.
        # Erwartung: zulässig, weil der Entwurf mode subagent ist.
        self.assertFalse((self.agents / "neu.md").exists())
        draft = task_agent([], mode="subagent")

        allowed = self.cli.agent_validate_hierarchy(
            "neu", ["neu"], own_text=draft
        )

        self.assertEqual(allowed, ["neu"])
        rendered = self.cli.agent_render_task("global", draft, ["neu"])
        self.cli.agent_write("global", "neu", rendered, create=True)
        self.assertTrue((self.agents / "neu.md").exists())
        self.assertEqual(
            self.cli.agent_validate_hierarchy("neu", ["neu"]), ["neu"]
        )
        self.assertEqual(
            self.cli.agent_task_policy(
                (self.agents / "neu.md").read_text(encoding="utf-8")
            )["allowed"],
            ["neu"],
        )

    def test_missing_own_text_and_missing_file_is_reported_as_unknown(self):
        # Vorbedingung: weder Datei noch Entwurf vorhanden.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: klare Meldung 'Unbekannter ... Subagent' statt einer
        # Selbstaufruf-Meldung.
        self.assertFalse((self.agents / "neu.md").exists())

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("neu", ["neu"])

        self.assertIn("Unbekannter oder nicht systemweiter Subagent: neu",
                      str(caught.exception))


class VibeSelfSpawnRejectedTest(F32Fixture):
    """AK2: Der Vibe-Agent darf keine Subagenten seines eigenen Typs aufrufen."""

    def test_default_vibe_agent_cannot_spawn_itself(self):
        # Vorbedingung: 'vibe-agent' trägt die Rolle vibe (Default-Auflösung).
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit der F32-Meldung zum Vibe-Agenten.
        self.write_vibe("vibe-agent", VIBE_AGENT)

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("vibe-agent", ["vibe-agent"])

        message = str(caught.exception)
        self.assertIn("Vibe-Agent", message)
        self.assertIn("eigenen Typs", message)

    def test_vibe_agent_is_rejected_even_with_subagent_mode(self):
        # Vorbedingung: Der Vibe-Agent hat ausdrücklich mode subagent.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Die Vibe-Rolle allein verbietet den Selbstaufruf.
        self.write_vibe("cap", task_agent([], mode="subagent"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("cap", ["cap"])

        self.assertIn("eigenen Typs", str(caught.exception))

    def test_explicit_vibe_agent_parameter_is_honoured(self):
        # Vorbedingung: keine vibe-Rolle in profiles.json; der Aufrufer nennt
        # 'cap' ausdrücklich als Vibe-Agent.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit der Vibe-Meldung.
        self.write_global("cap", task_agent([], mode="subagent"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("cap", ["cap"], vibe_agent="cap")

        self.assertIn("eigenen Typs", str(caught.exception))

    def test_empty_vibe_agent_parameter_disables_the_vibe_gate(self):
        # Vorbedingung: 'vibe-agent' trägt die Rolle vibe.
        # Aktion: vibe_agent="" (kein Vibe-Agent) und Selbstaufruf validieren.
        # Erwartung: zulässig; die Testschnittstelle kann die Vibe-Prüfung
        # bewusst abschalten.
        self.write_vibe("vibe-agent", task_agent([], mode="subagent"))

        allowed = self.cli.agent_validate_hierarchy(
            "vibe-agent", ["vibe-agent"], vibe_agent=""
        )

        self.assertEqual(allowed, ["vibe-agent"])


class SelfSpawnModeTest(F32Fixture):
    """AK4: Der eigene Typ ist nur ab mode subagent/all aufrufbar."""

    def test_primary_own_text_rejects_self_spawn(self):
        # Vorbedingung: Entwurf mit mode primary, Datei existiert nicht.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit 'kein Subagent (mode primary)'.
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy(
                "neu", ["neu"], own_text=task_agent([], mode="primary")
            )

        message = str(caught.exception)
        self.assertIn("kein Subagent", message)
        self.assertIn("mode primary", message)

    def test_all_and_missing_mode_from_own_text_allow_self_spawn(self):
        # Vorbedingung: Entwürfe mit mode all bzw. leerem mode (nicht gesetzt).
        # Aktion: Selbstaufruf validieren.
        # Erwartung: beide zulässig — ein leerer mode zählt wie all,
        # konsistent zur Fremdagenten-Regel.
        for mode in ("all", ""):
            with self.subTest(mode=mode):
                allowed = self.cli.agent_validate_hierarchy(
                    "neu", ["neu"], own_text=task_agent([], mode=mode)
                )
                self.assertEqual(allowed, ["neu"])

    def test_existing_primary_agent_rejects_self_spawn(self):
        # Vorbedingung: globale Datei 'prim' mit mode primary, kein own_text.
        # Aktion: Selbstaufruf validieren.
        # Erwartung: Ablehnung mit 'kein Subagent (mode primary)'.
        self.write_global("prim", task_agent([], mode="primary"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("prim", ["prim"])

        self.assertIn("kein Subagent", str(caught.exception))
        self.assertIn("mode primary", str(caught.exception))


class HierarchyCycleTest(F32Fixture):
    """Zyklusregeln: Selbstkanten sind kein Zyklus, Rückkanten bleiben verboten."""

    def test_two_agent_cycle_is_still_rejected(self):
        # Vorbedingung: a ruft b, b ruft a.
        # Aktion: a→b validieren.
        # Erwartung: Zyklusfehler (unveränderte Regel, grüner Anker).
        self.write_global("a", task_agent(["b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["b"])

        self.assertIn("Zyklus", str(caught.exception))

    def test_self_edge_alone_is_not_a_cycle(self):
        # Vorbedingung: a erlaubt sich selbst; b erlaubt a.
        # Aktion: a→a und b→a validieren.
        # Erwartung: beides zulässig; eine Selbstkante ist kein Zyklus.
        self.write_global("a", task_agent(["a"]))

        self.assertEqual(
            self.cli.agent_validate_hierarchy("a", ["a"]), ["a"]
        )

        self.write_global("b", task_agent(["a"]))
        self.assertEqual(
            self.cli.agent_validate_hierarchy("b", ["a"]), ["a"]
        )

    def test_self_and_foreign_without_back_cycle_are_allowed(self):
        # Vorbedingung: a und b sind globale Subagenten ohne Rückkante.
        # Aktion: a erlaubt [a, b].
        # Erwartung: zulässig; der Selbstaufruf blockiert den Fremdaufruf nicht.
        self.write_global("a", task_agent([]))
        self.write_global("b", task_agent([]))

        allowed = self.cli.agent_validate_hierarchy("a", ["a", "b"])

        self.assertEqual(allowed, ["a", "b"])

    def test_self_edge_does_not_hide_a_real_cycle(self):
        # Vorbedingung: a erlaubt [a, b], b ruft a zurück.
        # Aktion: a erlaubt [a, b] validieren.
        # Erwartung: echter Zyklus wird trotz Selbstkante erkannt.
        self.write_global("a", task_agent(["a", "b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["a", "b"])

        self.assertIn("Zyklus", str(caught.exception))


class ForeignAgentRulesTest(F32Fixture):
    """AK6: Regeln für fremde Agenten bleiben unverändert (grüne Anker)."""

    def test_unknown_project_local_and_primary_are_rejected(self):
        # Vorbedingung: globaler Subagent a, globaler primary, projektlokaler
        # Agent.
        # Aktion/Erwartung: fremde Agenten werden weiterhin abgelehnt.
        self.write_global("a", task_agent([]))
        self.write_global("primary", task_agent([], mode="primary"))
        self.write_project_agent(self.project, "lokal", task_agent([]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["primary"])
        self.assertIn("kein Subagent (mode primary)", str(caught.exception))
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["lokal"])

    def test_global_subagent_and_all_modes_remain_allowed(self):
        # Vorbedingung: globale Agenten mit mode subagent und all.
        # Aktion/Erwartung: beide bleiben aufrufbar.
        self.write_global("a", task_agent([]))
        self.write_global("unter", task_agent([], mode="subagent"))
        self.write_global("alle", task_agent([], mode="all"))

        self.assertEqual(
            self.cli.agent_validate_hierarchy("a", ["unter", "alle"]),
            ["alle", "unter"],
        )


class AgentTemplateTest(F32Fixture):
    """AK3: Eine neue Agentendatei erhält keine Selbstfreigabe (grüner Anker)."""

    def test_template_has_no_self_release_and_policy_is_none(self):
        # Vorbedingung: frische Vorlage. Je nach Rechtevorlage enthält sie
        # 'task: deny' oder gar keinen task-Eintrag — beides ist gesperrt.
        # Aktion: Vorlage rendern und Politik lesen.
        # Erwartung: mode none, kein Selbstaufruf als Standard.
        text = self.cli.agent_template(
            "Neuer Agent", model="opencode/test-modell", prompt="Aufgabe"
        )

        self.assertEqual(
            self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
        )
        self.assertNotIn("task: allow", text)
        self.cli.agent_validate(text)


class AgentSelfSpawnApiTest(unittest.TestCase):
    """AK2/AK6/Persistenz über die echte Web-API (HTTP 400, Datei unverändert)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        # Der Server ruft beim Speichern ``opencode --version`` und
        # ``opencode models`` auf. Beide werden hier durch ein schnelles
        # Ersatzprogramm beantwortet; es findet kein echter Modellaufruf statt.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
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
        cls.cli = load_cli(cls.root, cls.home)

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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        # Jeder Test startet mit demselben Ausgangsstand; Fehlerfälle dürfen
        # keine Spuren im nächsten Test hinterlassen.
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (self.agents / "helper.md").write_text(task_agent([]), encoding="utf-8")
        (self.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        leftover = self.agents / "neu.md"
        if leftover.exists():
            leftover.unlink()
        self.write_profiles({"vibe-agent": "vibe"})

    def write_profiles(self, roles):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": dict(roles)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self, name="tester"):
        status, body = self.request(f"/api/agent?scope=global&name={name}")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def error_message(self, body):
        data = json.loads(body)
        return (data.get("error") or {}).get("message") or data.get("message") or ""

    def assert_rejected_with(self, status, body, expected, timeout_message=None):
        self.assertEqual(status, 400, body)
        self.assertIn(expected, self.error_message(body), timeout_message or body)

    def test_regular_agent_self_spawn_is_saved_and_plain_save_keeps_the_block(self):
        # Vorbedingung: 'tester' ist gewöhnlicher Subagent.
        # Aktion 1: Speichern mit task_allowed=['tester'].
        # Erwartung 1: 200, Datei enthält 'tester: allow' unter task.
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "expected": self.digest(),
            },
        )

        self.assertEqual(status, 200, body)
        path = self.agents / "tester.md"
        saved = path.read_text(encoding="utf-8")
        self.assertIn('"*": deny', saved)
        self.assertIn("tester: allow", saved)
        policy = self.cli.agent_task_policy(saved)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])

        # Aktion 2: Erneut speichern, ohne task_allowed (unveränderter Rohtext).
        # Erwartung 2: Der task-Block bleibt unverändert erhalten.
        status, body = self.request(
            "/api/agent?scope=global&name=tester"
        )
        self.assertEqual(status, 200, body)
        loaded = json.loads(body)
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": loaded["text"],
                "expected": loaded["digest"],
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(saved, path.read_text(encoding="utf-8"))
        policy = self.cli.agent_task_policy(path.read_text(encoding="utf-8"))
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["tester"])

    def test_new_agent_can_enable_self_spawn_in_the_same_save(self):
        # Vorbedingung: Die Datei 'neu' existiert noch nicht; der Editor
        # speichert Entwurf und task_allowed in einer Anfrage.
        # Aktion: Neuanlage mit Selbstaufruf.
        # Erwartung: 200, Datei enthält den Eigennamen als allow. Der Server
        # muss den Entwurf als own_text an die Hierarchieprüfung geben.
        self.assertFalse((self.agents / "neu.md").exists())

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "neu",
                "text": task_agent([], mode="subagent"),
                "task_allowed": ["neu"],
                "create": True,
            },
        )

        self.assertEqual(status, 200, body)
        saved = (self.agents / "neu.md").read_text(encoding="utf-8")
        self.assertIn("neu: allow", saved)
        self.assertEqual(self.cli.agent_task_policy(saved)["allowed"], ["neu"])

    def test_current_vibe_agent_cannot_self_spawn(self):
        # Vorbedingung: 'vibe-agent' ist der aktuelle Vibe-Agent.
        # Aktion: task_allowed=['vibe-agent'].
        # Erwartung: 400 mit F32-Meldung; Agentendatei unverändert.
        path = self.agents / "vibe-agent.md"
        before = path.read_text(encoding="utf-8")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "vibe-agent",
                "text": VIBE_AGENT,
                "task_allowed": ["vibe-agent"],
                "expected": self.digest("vibe-agent"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertIn("Vibe-Agent", self.error_message(body))
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_agent_becoming_vibe_in_the_same_request_cannot_self_spawn(self):
        # Vorbedingung: 'tester' ist kein Vibe-Agent.
        # Aktion: Speichern mit role='vibe' und Selbstaufruf.
        # Erwartung: 400, weil 'tester' durch dieselbe Anfrage Vibe-Agent wird.
        path = self.agents / "tester.md"
        before = path.read_text(encoding="utf-8")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_explicit_role_removal_allows_self_spawn_when_another_vibe_exists(self):
        # Vorbedingung: profiles.json führt 'tester' UND 'vibe-agent' als vibe.
        # Aktion: 'tester' speichern, Rolle ausdrücklich entfernen (role='')
        # und Selbstaufruf erlauben.
        # Erwartung: 200; der andere Agent bleibt Vibe-Agent, der Selbstaufruf
        # wird gespeichert.
        self.write_profiles({"tester": "vibe", "vibe-agent": "vibe"})

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": ["tester"],
                "role": "",
                "expected": self.digest("tester"),
            },
        )

        self.assertEqual(status, 200, body)
        policy = self.cli.agent_task_policy(
            (self.agents / "tester.md").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["allowed"], ["tester"])
        roles = json.loads(
            (self.state / "profiles.json").read_text(encoding="utf-8")
        )["rollen"]
        self.assertNotIn("tester", roles)
        self.assertEqual(roles.get("vibe-agent"), "vibe")

    def test_task_all_stays_a_plain_allow_without_hierarchy_check(self):
        # Vorbedingung: 'helper' ist gewöhnlicher Subagent.
        # Aktion: Speichern mit task_all=true.
        # Erwartung: 200 und 'task: allow' (unverändert, grüner Anker).
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "helper",
                "text": task_agent([]),
                "task_all": True,
                "expected": self.digest("helper"),
            },
        )

        self.assertEqual(status, 200, body)
        saved = (self.agents / "helper.md").read_text(encoding="utf-8")
        self.assertIn("task: allow", saved)
        self.assertEqual(self.cli.agent_task_policy(saved)["mode"], "all")

    def test_task_allowed_for_project_scope_is_still_rejected(self):
        # Vorbedingung: Projekt 'proj' existiert, scope=proj.
        # Aktion: Speichern mit task_allowed.
        # Erwartung: 400, Subagenten-Rechte gelten nur systemweit (grüner Anker).
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "proj",
                "name": "tester",
                "text": AGENT_BASE,
                "task_allowed": [],
            },
        )

        self.assert_rejected_with(
            status, body, "Subagenten-Rechte gelten nur für systemweite Agenten."
        )
        self.assertFalse(
            (self.project / ".opencode" / "agents" / "tester.md").exists()
        )


class VibeInvariantApiTest(unittest.TestCase):
    """F32 Runde 2: Die Vibe-Sperre gilt bei *jeder* Rollenzuweisung.

    Fachlicher Hintergrund (Review Runde 1, High 1): Die Sperre aus Runde 1
    lief nur im ``task_allowed``-Zweig von ``/api/agent``. Zwei reale UI-Wege
    umgingen sie deshalb:

    * Editor-Speichern, das ausschließlich die Rolle auf ``vibe`` setzt,
    * das Rollen-Dropdown der Agentenliste (``action:'role'``).

    Der Vertrag lautet: Ein Agent mit Selbstfreigabe (``permission.task``
    erlaubt den eigenen Namen) darf niemals Vibe-Agent werden — unabhängig
    davon, ob ``task_allowed`` mitgesendet wird. Ein Agent ohne Selbstfreigabe
    darf die Rolle weiterhin erhalten.

    Der Testaufbau entspricht ``AgentSelfSpawnApiTest`` (eigener Server im
    Temp-Verzeichnis, ``opencode`` als Ersatzprogramm, kein Modellaufruf, kein
    Netzzugriff außer Loopback). Die Klasse ist bewusst eigenständig, damit die
    Runde-1-Fälle unverändert bleiben.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        # Ersatzprogramm wie in AgentSelfSpawnApiTest: beantwortet nur
        # Versions- und Modellabfragen, führt keinen Modellaufruf aus.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
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
        cls.cli = load_cli(cls.root, cls.home)

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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        # Gleicher Ausgangsstand für jeden Fall: 'vibe-agent' ist der einzige
        # Vibe-Agent, 'tester' und 'helper' sind gewöhnliche Subagenten.
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (self.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        (self.agents / "helper.md").write_text(task_agent([]), encoding="utf-8")
        # 'neu' und 'kaputt' entstehen nur in einzelnen Fällen; damit die
        # Klasse wiederholbar bleibt, wird ein Rest aus dem Vorlauf entfernt.
        for leftover_name in ("neu.md", "kaputt.md"):
            leftover = self.agents / leftover_name
            if leftover.exists():
                leftover.unlink()
        self.write_profiles({"vibe-agent": "vibe"})

    # ------------------------------------------------------------------ Helfer
    def write_profiles(self, roles):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": dict(roles)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def roles(self):
        return json.loads(
            (self.state / "profiles.json").read_text(encoding="utf-8")
        )["rollen"]

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self, name="tester"):
        status, body = self.request(f"/api/agent?scope=global&name={name}")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def error_message(self, body):
        data = json.loads(body)
        return (data.get("error") or {}).get("message") or data.get("message") or ""

    def assert_rejected_with(self, status, body, expected):
        self.assertEqual(status, 400, body)
        self.assertIn(expected, self.error_message(body), body)

    def global_agent_row(self, name):
        status, body = self.request("/api/agents")
        self.assertEqual(status, 200, body)
        rows = json.loads(body)["global_agents"]
        return next(row for row in rows if row["name"] == name)

    # --------------------------------------------------------------- Testfälle
    def test_role_only_save_rejects_vibe_for_agent_with_self_allow(self):
        # Vorbedingung: 'tester' erlaubt sich selbst als Subagenten; die Datei
        # enthält also eine Selbstfreigabe, 'tester' ist aber kein Vibe-Agent.
        # Aktion: Speichern wie im Editor, wenn nur die Rolle auf 'vibe'
        # gestellt wird — ohne task_allowed-Feld.
        # Erwartung: 400 mit der F32-Meldung; Agentendatei und profiles.json
        # bleiben unverändert, 'tester' wird kein Vibe-Agent.
        path = self.agents / "tester.md"
        text = task_agent(["tester"], mode="subagent")
        path.write_text(text, encoding="utf-8")
        before_roles = self.roles()

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": text,
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("tester"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")

    def test_raw_text_self_allow_for_the_current_vibe_agent_is_rejected(self):
        # Vorbedingung: 'vibe-agent' ist der aktuelle Vibe-Agent.
        # Aktion: Speichern des Rohtexts, der im task-Block
        # 'vibe-agent: allow' enthält (keine Rolle, kein task_allowed).
        # Erwartung: 400 mit der F32-Meldung; die Datei bleibt unverändert.
        path = self.agents / "vibe-agent.md"
        before = path.read_text(encoding="utf-8")
        text = task_agent(["vibe-agent"], mode="primary")

        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "vibe-agent",
                "text": text,
                "expected": self.digest("vibe-agent"),
            },
        )

        self.assert_rejected_with(status, body, "eigenen Typs")
        self.assertIn("Vibe-Agent", self.error_message(body))
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_role_only_save_allows_vibe_without_self_allow(self):
        # Vorbedingung: 'tester' hat keine Selbstfreigabe (kein task-Eintrag).
        # Aktion: Speichern mit ausschließlich role='vibe', ohne task_allowed.
        # Erwartung: 200, die Rolle ist gesetzt und /api/agents meldet
        # 'tester' als Vibe-Agent. Grüner Anker: die Invariante blockiert nur
        # die Selbstfreigabe, nicht die Rollenzuweisung an sich.
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "role": "vibe",
                "expected": self.digest("tester"),
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("tester"), "vibe")
        row = self.global_agent_row("tester")
        self.assertTrue(row["is_vibe"], row)
        self.assertEqual(row["role"], "vibe")

    def test_role_action_rejects_vibe_for_agent_with_self_allow(self):
        # Vorbedingung: 'tester' erlaubt sich selbst; 'vibe-agent' ist der
        # bisherige Vibe-Agent.
        # Aktion: Rollen-Dropdown der Agentenliste (action='role').
        # Erwartung: 400 mit der Meldung aus agent_role_set; profiles.json
        # bleibt unverändert, 'tester' bekommt keine vibe-Rolle und der
        # bisherige Vibe-Agent behält seine Rolle.
        text = task_agent(["tester"], mode="subagent")
        (self.agents / "tester.md").write_text(text, encoding="utf-8")
        before_roles = self.roles()

        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "tester",
                "role": "vibe",
            },
        )

        self.assert_rejected_with(
            status, body, "erlaubt bereits Subagenten seines eigenen Typs"
        )
        self.assertIn(
            "nicht der Vibe-Agent werden", self.error_message(body), body
        )
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("tester"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")

    def test_role_action_allows_vibe_after_self_release_removed(self):
        # Vorbedingung: 'tester' hat keine Selbstfreigabe mehr (task: deny).
        # Aktion: Rollen-Dropdown der Agentenliste auf 'vibe'.
        # Erwartung: 200; profiles.json führt 'tester' als Vibe-Agent und der
        # bisherige Vibe-Agent verliert die Rolle (Eindeutigkeitsregel).
        # Grüner Anker für das bestehende Verhalten ohne Selbstfreigabe.
        text = task_agent([], mode="subagent")
        (self.agents / "tester.md").write_text(text, encoding="utf-8")
        self.assertEqual(
            self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
        )

        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "tester",
                "role": "vibe",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("tester"), "vibe")
        self.assertNotEqual(self.roles().get("vibe-agent"), "vibe")

    def test_role_action_still_assigns_vibe_for_unreadable_frontmatter(self):
        # Vorbedingung: 'kaputt' hat keinen Frontmatter-Block und keine Rolle;
        # 'vibe-agent' ist der bisherige Vibe-Agent. Der Parser kann die Datei
        # nicht lesen — genau das ist der Fall, für den agent_role_set den
        # defensiven Fallback (policy mode 'none') hinterlegt hat.
        broken = self.agents / "kaputt.md"
        broken.write_text("Kein Frontmatter.\n", encoding="utf-8")
        self.assertNotIn("kaputt", self.roles())
        with self.assertRaises(ValueError):
            self.cli.agent_task_policy(broken.read_text(encoding="utf-8"))

        # Aktion 1: Rollen-Dropdown der Agentenliste für die defekte Datei.
        # Erwartung: 200; 'kaputt' trägt die Rolle 'vibe' und der bisherige
        # Vibe-Agent verliert sie (Eindeutigkeitsregel). Eine Selbstfreigabe
        # ist nicht nachweisbar, deshalb bleibt die Zuweisung möglich.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "vibe",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertEqual(self.roles().get("kaputt"), "vibe")
        self.assertNotEqual(self.roles().get("vibe-agent"), "vibe")

        # Gegenprobe: dieselbe Datei mit lesbarem Frontmatter, das die
        # Selbstfreigabe 'kaputt: allow' enthält (mode subagent).
        text = task_agent(["kaputt"], mode="subagent")
        broken.write_text(text, encoding="utf-8")
        policy = self.cli.agent_task_policy(text)
        self.assertEqual(policy["mode"], "custom")
        self.assertIn("kaputt", policy["allowed"])

        # Rolle zurücksetzen: zuerst bekommt 'vibe-agent' die Rolle wieder
        # (sonst wäre 'kaputt' der letzte Vibe-Agent), dann wird 'kaputt'
        # ausdrücklich auf '' gesetzt.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "vibe-agent",
                "role": "vibe",
            },
        )
        self.assertEqual(status, 200, body)
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "",
            },
        )
        self.assertEqual(status, 200, body)
        self.assertNotIn("kaputt", self.roles())
        before_roles = self.roles()

        # Aktion 1 wiederholen. Erwartung: 400 mit der F32-Meldung; profiles
        # bleibt unverändert, 'kaputt' wird kein Vibe-Agent und der bisherige
        # Vibe-Agent behält seine Rolle. So unterscheidet sich der lesbare
        # vom unlesbaren Fall.
        status, body = self.request(
            "/api/agent",
            {
                "action": "role",
                "scope": "global",
                "name": "kaputt",
                "role": "vibe",
            },
        )

        self.assert_rejected_with(
            status, body, "erlaubt bereits Subagenten seines eigenen Typs"
        )
        self.assertIn(
            "nicht der Vibe-Agent werden", self.error_message(body), body
        )
        self.assertEqual(self.roles(), before_roles)
        self.assertNotEqual(self.roles().get("kaputt"), "vibe")
        self.assertEqual(self.roles().get("vibe-agent"), "vibe")


if __name__ == "__main__":
    unittest.main()
