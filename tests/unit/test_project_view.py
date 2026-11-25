"""Projektansicht: Latenz, Berechtigungs-Geltungsbereich und Öffnen ohne erreichbares Remote.

Aufruf: python3 -m unittest tests.unit.test_project_view -v
"""


# ===========================================================================
# Schnelles Öffnen der Projektansicht (scrypt-Ableitung einmal je Anfrage)
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
BIN = REPO / "bin"
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
SERVICES_MODULE = REPO / "bin" / "vibe_services.py"

STORED_TOKEN = "ap15-gespeicherter-projekt-token"
ENV_TOKEN = "ap15-umgebungs-token"
LEGACY_TOKEN = "ap15-legacy-globaler-token"
BRANCH_COUNT = 120  # zusätzlich zu main → 121 Branches (AK2: "120+ Branches")

ISOLATED_ENV_KEYS = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STATE",
    "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_PROFILE", "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "http_proxy", "https_proxy", "all_proxy", "NO_PROXY",
)

_GH_CACHE = {}


def github_module():
    """Lädt ``bin/vibe_github.py`` als eigenständiges Modul."""
    if _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_ap15_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def services_module():
    """Lädt ``bin/vibe_services.py`` mit bin/ im Modulpfad."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    loader = importlib.machinery.SourceFileLoader(
        "vibe_services_ap15_under_test", str(SERVICES_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME (V-008-Muster)."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap15_cli_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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


def git(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität; nie produktive Konfiguration."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )


def commit_file(project, name, content, message):
    (Path(project) / name).write_text(content, encoding="utf-8")
    git(project, "add", name)
    git(project, "commit", "-q", "-m", message)


def git_verb(argv):
    """Erster fachlicher Git-Unterbefehl nach dem festen Präfix."""
    argv = [str(a) for a in argv]
    if "core.fsmonitor=false" in argv:
        idx = argv.index("core.fsmonitor=false") + 1
    elif argv and argv[0] == "git":
        idx = 1
    else:
        idx = 0
    while idx < len(argv) and argv[idx].startswith("-"):
        idx += 1
    return argv[idx] if idx < len(argv) else ""


def subprocess_spy(calls):
    """Protokolliert subprocess.run und führt es unverändert aus."""
    real_run = subprocess.run

    def wrapper(argv, *rest, **kwargs):
        calls.append({
            "argv": [str(a) for a in argv],
            "timeout": kwargs.get("timeout"),
            "env": dict(kwargs.get("env") or {}),
        })
        return real_run(argv, *rest, **kwargs)

    return wrapper


NETWORK_VERBS = ("ls-remote", "fetch", "pull", "push")


def network_calls(calls):
    return [c for c in calls if git_verb(c["argv"]) in NETWORK_VERBS]


class ScryptCounter:
    """Zählt ``hashlib.scrypt``-Aufrufe und leitet sie unverändert weiter.

    Damit wird die Key-Ableitung (``vibe_github._derive_key``) gezählt,
    ohne ihr Verhalten zu ersetzen — inklusive des zweiten
    vibe_github-Modulinstanz, die ``vibe_services`` importiert."""

    def __init__(self):
        self.calls = 0
        self._real = hashlib.scrypt

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._real(*args, **kwargs)

    def patch(self):
        return mock.patch.object(hashlib, "scrypt", self)


class AP15Case(unittest.TestCase):
    """Isolierte Umgebung: eigene VIBE-Wurzel, eigene Token-Ablage, kein ENV-Token."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ws = self.base / "ws"
        self.ws.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.base / "state"
        self.state.mkdir()
        self.runtime = self.ws / "_logs"
        self.runtime.mkdir()
        self.install = self.base / "install"
        self.install.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_KEYS}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy",
                    "https_proxy", "all_proxy", "VIBE_CONFIG_FILE",
                    "VIBE_PROFILE"):
            os.environ.pop(key, None)
        (self.home / ".config" / "opencode" / "agents").mkdir(parents=True,
                                                              exist_ok=True)
        os.environ.update({
            "VIBE": str(self.ws),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.install),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module()

    def restore_env(self):
        """Stellt die ursprüngliche Umgebung wieder her (keine Reste an Tests)."""
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_project(self, name="proj", github_enabled=True):
        project = self.ws / name
        project.mkdir(parents=True, exist_ok=True)
        git(project, "init", "-q", "-b", "main")
        git(project, "commit", "--allow-empty", "-q", "-m", "init")
        (project / ".vibe").mkdir(exist_ok=True)
        lines = ["TYPE=generic", "TESTER=test-agent", 'SANDBOX="off"']
        if github_enabled:
            lines.append('GITHUB_ENABLED="1"')
            lines.append('GITHUB_REPO="ap15/proj"')
        (project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        return project

    def store_project_token(self, project):
        """Verschlüsselt einen Projekt-Token (geschieht vor der Zählung)."""
        self.gh.save_project_token(str(project), STORED_TOKEN)
        self.addCleanup(self.gh.delete_project_token, str(project))

    def make_many_branch_project(self, name="proj", count=BRANCH_COUNT):
        """Projekt mit 1 + count Branches; origin = lokales file://-Bare-Repo.

        Drei Branches führen lokal (ahead=1), zwei hinken der lokalen
        Fern-Referenz hinterher (behind=1); der Rest ist ausgeglichen."""
        project = self.make_project(name)
        bare = self.base / (name + "-origin.git")
        bare.mkdir()
        git(bare, "init", "-q", "--bare", "-b", "main")
        git(project, "remote", "add", "origin", "file://" + str(bare))
        git(project, "push", "-q", "-u", "origin", "main")
        for index in range(count):
            git(project, "branch", "ap15-b%03d" % index)
        git(project, "push", "-q", "origin", "--all")
        ahead_names = []
        for branch in ("ap15-b001", "ap15-b050", "ap15-b100"):
            git(project, "checkout", "-q", branch)
            commit_file(project, "arbeit.txt", branch,
                        "AP15: lokale Arbeit " + branch)
            ahead_names.append(branch)
        git(project, "checkout", "-q", "main")
        behind_names = []
        for branch in ("ap15-b002", "ap15-b101"):
            # Lokale Fern-Referenz vor dem lokalen Branch: Commit + Push,
            # dann lokales Zurücksetzen — wie nach einem Fetch ohne Merge
            # hinkt der lokale Branch der origin/<branch>-Referenz um 1
            # hinterher (behind=1, ahead=0).
            git(project, "checkout", "-q", branch)
            commit_file(project, "ferne.txt", branch,
                        "AP15: ferne Arbeit " + branch)
            git(project, "push", "-q", "origin", branch)
            git(project, "reset", "-q", "--hard", "HEAD~1")
            behind_names.append(branch)
        git(project, "checkout", "-q", "main")
        return project, tuple(ahead_names), tuple(behind_names)

    def make_small_remote_project(self, name="fern"):
        """Projekt mit main + ap15-voraus + ap15-hinter.

        Die Fernseite kennt einen zusätzlichen main-Commit, den das lokale
        Projekt noch nicht abgerufen hat — der Unterschied zwischen
        ``remote=False`` (lokale Referenz: 0/0) und ``remote=True``
        (ls-remote: behind=1) beweist, welcher Stand gelesen wurde."""
        project = self.make_project(name)
        bare = self.base / (name + "-origin.git")
        bare.mkdir()
        git(bare, "init", "-q", "--bare", "-b", "main")
        git(project, "remote", "add", "origin", "file://" + str(bare))
        git(project, "push", "-q", "-u", "origin", "main")
        git(project, "branch", "ap15-voraus")
        git(project, "push", "-q", "origin", "ap15-voraus")
        git(project, "branch", "ap15-hinter")
        git(project, "push", "-q", "origin", "ap15-hinter")
        # ap15-voraus: lokale Arbeit, die die Fernseite nicht kennt (ahead=1)
        git(project, "checkout", "-q", "ap15-voraus")
        commit_file(project, "arbeit.txt", "voraus", "AP15: voraus")
        git(project, "checkout", "-q", "main")
        # ap15-hinter: Commit + Push + lokales Zurücksetzen — die lokale
        # Fern-Referenz liegt vor dem lokalen Branch (behind=1 in beiden
        # Modi; das Commit-Objekt bleibt lokal vorhanden).
        git(project, "checkout", "-q", "ap15-hinter")
        commit_file(project, "ferne.txt", "hinter", "AP15: ferne Arbeit")
        git(project, "push", "-q", "origin", "ap15-hinter")
        git(project, "reset", "-q", "--hard", "HEAD~1")
        git(project, "checkout", "-q", "main")
        # main: Nur die Fernseite kennt einen zusätzlichen Commit (Zweitklon
        # schiebt); die lokale origin/main-Referenz bleibt zurück — sie wird
        # nur im remote=True-Modus über ls-remote sichtbar (behind=1).
        clone = self.base / (name + "-zweit-main")
        git(self.base, "clone", "-q", "file://" + str(bare), str(clone))
        commit_file(clone, "draussen.txt", "main", "AP15: ferne main-Arbeit")
        git(clone, "push", "-q", "origin", "main")
        return project

    def git_child_calls(self, calls):
        return [c for c in calls if c["argv"][:1] == ["git"]]

    def assert_credential_on_every_git_call(self, calls, token):
        """AK1/AK4/AK6: jedes git-Kindprogramm führt das Credential in seiner
        Prozessumgebung (VIBE_GITHUB_CREDENTIAL), nie im argv."""
        git_calls = self.git_child_calls(calls)
        self.assertTrue(git_calls, "Der Durchgang führte keine git-Aufrufe aus")
        for call in git_calls:
            self.assertEqual(
                token, call["env"].get(self.gh.CREDENTIAL_ENV_NAME),
                "Jeder git-Kindprozess muss VIBE_GITHUB_CREDENTIAL mit dem "
                "weitergereichten Credential führen (argv=%r)" % (call["argv"][:6],))
            joined = "\n".join(call["argv"])
            self.assertNotIn(token, joined,
                             "Der Credential-Inhalt darf nie im argv stehen")


# --------------------------------------------------- AK1 + AK2: Ableitung & remotes()
class DerivationOncePerPassTest(AP15Case):
    """AK1: scrypt-Ableitung genau einmal je Durchgang; kein Anfrage-Cache.
    AK2: remotes() genau einmal je branches()-Durchgang."""


    def test_branches_durchgang_leitet_credential_genau_einmal_ab(self):
        """AK1, Rotphase erwartet. Vorbedingung: Projekt mit 121 Branches,
        verschlüsseltem Projekt-Token, GITHUB_ENABLED; Aktion: ein kompletter
        branches(remote=False)-Durchgang; Erwartung: genau 1 scrypt-Aufruf
        und jedes git-Kindprogramm führt das abgeleitete Credential."""
        project, _ahead, _behind = self.make_many_branch_project()
        self.store_project_token(project)
        counter = ScryptCounter()
        calls = []
        with counter.patch(), mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project), remote=False)

        self.assertEqual(1 + BRANCH_COUNT, len(rows),
                         "Vorbereitung: der Durchgang muss alle Branches lesen")
        self.assert_credential_on_every_git_call(calls, STORED_TOKEN)
        self.assertEqual(1, counter.calls,
                         "Die scrypt-Key-Ableitung muss je Durchgang genau "
                         "einmal laufen, lief aber %d-mal" % counter.calls)

    def test_status_durchgang_leitet_credential_hoechstens_einmal_ab(self):
        """AK1, Rotphase erwartet. Ein kompletter status(remote=False)-
        Durchgang darf das Credential höchstens einmal ableiten und muss es
        an alle git()-Aufrufe weiterreichen."""
        project, _ahead, _behind = self.make_many_branch_project()
        self.store_project_token(project)
        counter = ScryptCounter()
        calls = []
        with counter.patch(), mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project), remote=False)

        self.assertEqual("main", info["branch"])
        self.assertTrue(info["unpushed"] in (True, False))
        self.assert_credential_on_every_git_call(calls, STORED_TOKEN)
        self.assertEqual(1, counter.calls,
                         "status(remote=False) leitet das Credential je "
                         "Durchgang genau einmal ab, lief aber %d-mal"
                         % counter.calls)

    def test_project_detail_leitet_das_credential_genau_einmal_ab(self):
        """AK1, Rotphase erwartet. Die Dashboard-Anfrage
        vibe_services.project_detail() leitet das Credential für status- UND
        branches-Durchgang zusammen genau einmal ab."""
        project, _ahead, _behind = self.make_many_branch_project()
        self.store_project_token(project)
        cli = load_cli(self.ws, self.home)
        services = services_module()
        counter = ScryptCounter()
        calls = []
        with counter.patch(), mock.patch("subprocess.run", subprocess_spy(calls)):
            data = services.project_detail(cli, cli.PATHS, project.name)

        self.assertEqual(1 + BRANCH_COUNT, len(data["github"]["branches"]),
                         "Die Ansicht muss alle Branches liefern")
        self.assertIn("main", [row["name"] for row in data["github"]["branches"]])
        self.assertEqual(1, counter.calls,
                         "project_detail() leitet das Credential je Anfrage "
                         "genau einmal ab, lief aber %d-mal" % counter.calls)

    def test_zwei_durchgaenge_leiten_jeweils_neu_ab_kein_anfrage_cache(self):
        """AK1, bewusst GRÜN am Basisstand (Regressionsschutz): zwei
        aufeinanderfolgende Anfragen leiten jeweils erneut ab — ein Cache
        über Anfragen hinweg ist verboten."""
        project = self.make_project("klein")
        self.store_project_token(project)
        counts = []
        for _ in range(2):
            counter = ScryptCounter()
            calls = []
            with counter.patch(), mock.patch("subprocess.run",
                                             subprocess_spy(calls)):
                rows = self.gh.branches(str(project), remote=False)
            self.assertEqual(["main"], [row["name"] for row in rows])
            self.assert_credential_on_every_git_call(calls, STORED_TOKEN)
            counts.append(counter.calls)

        self.assertGreaterEqual(counts[1], 1,
                                "Die zweite Anfrage muss erneut ableiten — "
                                "ein Cache über Anfragen ist verboten")
        self.assertEqual(counts[0], counts[1],
                         "Beide Anfragen leiten gleich oft neu ab (kein "
                         "partielles Caching): %r" % (counts,))


    def test_branches_durchgang_prueft_remotes_genau_einmal(self):
        """AK2, Rotphase erwartet. Bei 121 Branches darf der
        branches(remote=False)-Durchgang remotes() genau einmal prüfen
        (ein ``git remote -v``), nicht je Branch."""
        project, _ahead, _behind = self.make_many_branch_project()
        self.store_project_token(project)
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project), remote=False)

        self.assertEqual(1 + BRANCH_COUNT, len(rows),
                         "Vorbereitung: der Durchgang muss alle Branches lesen")
        self.assertEqual([], network_calls(calls),
                         "remote=False darf keinen Fernaufruf auslösen: %r"
                         % [c["argv"] for c in network_calls(calls)])
        remote_probes = [c for c in calls if git_verb(c["argv"]) == "remote"]
        self.assertEqual(1, len(remote_probes),
                         "remotes() muss je Durchgang genau einmal geprüft "
                         "werden, lief aber %d-mal (einmal je Branch)"
                         % len(remote_probes))


# ------------------------------------------- AK3 + AK4: Verhaltensgleichheit
class BranchesBehaviorTest(AP15Case):
    """AK3: branches() bleibt funktional identisch; remote=False liest nur
    lokale Referenzen. AK4: Maskierung und remote=True-Pfad bleiben wirksam.

    Diese Fälle sind bewusst am unveränderten Basisstand GRÜN: Sie schützen
    das bestehende Verhalten während der Beschleunigung."""


    def test_branches_121_branches_liefert_alle_zeilen_ohne_aenderung(self):
        """AK3, GRÜN am Basisstand. Vorbedingung: 121 Branches mit bekanntem
        Stand (3 ahead, 2 behind); Aktion: branches(remote=False);
        Erwartung: alle Zeilen mit name/current/last/ahead/behind wie direkt
        via git for-each-ref erwartet; kein Netzaufruf."""
        project, ahead_names, behind_names = self.make_many_branch_project()
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project), remote=False)

        # Erwartungswerte unabhängig von vibe_github direkt mit git gelesen:
        listing = git(project, "for-each-ref", "refs/heads",
                      "--format=%(refname:short)\t%(objectname:short)"
                      "\t%(contents:subject)")
        expected_last = {}
        for line in listing.stdout.splitlines():
            name, sha, subject = line.split("\t", 2)
            expected_last[name] = (sha + " " + subject).strip()

        self.assertEqual(len(expected_last), 1 + BRANCH_COUNT,
                         "Vorbereitung: alle Branches angelegt")
        names = {row["name"] for row in rows}
        self.assertEqual(set(expected_last), names,
                         "Alle angelegten Branches müssen erscheinen")
        currents = [row["name"] for row in rows if row["current"]]
        self.assertEqual(["main"], currents,
                         "Genau der ausgecheckte Branch trägt current")
        for row in rows:
            self.assertEqual({"name", "current", "last", "ahead", "behind"},
                             set(row), "Zeilenstruktur unverändert: %r" % (row,))
            self.assertEqual(expected_last[row["name"]], row["last"],
                             "last (SHA + Betreff) unverändert für %s"
                             % row["name"])
            self.assertIsInstance(row["ahead"], int)
            self.assertIsInstance(row["behind"], int)
            if row["name"] in ahead_names:
                self.assertEqual((1, 0), (row["ahead"], row["behind"]),
                                 "lokale Arbeit bleibt ahead=1: " + row["name"])
            elif row["name"] in behind_names:
                self.assertEqual((0, 1), (row["ahead"], row["behind"]),
                                 "ferne Arbeit bleibt behind=1: " + row["name"])
            else:
                self.assertEqual((0, 0), (row["ahead"], row["behind"]),
                                 "ausgeglichener Stand: " + row["name"])
        self.assertEqual([], network_calls(calls),
                         "remote=False liest nur lokale Referenzen: %r"
                         % [c["argv"] for c in network_calls(calls)])

    def test_fernmodus_remote_true_liest_die_aktuelle_fern_referenz(self):
        """AK4, GRÜN am Basisstand. Der remote=True-Pfad bleibt unangetastet:
        Er liest die aktuelle Fern-Referenz (hier gegen ein lokales
        file://-Bare-Repo, kein echtes Netz) und sieht den ferne main-Commit,
        den remote=False bewusst übersieht."""
        project = self.make_small_remote_project()

        local_rows = self.gh.branches(str(project), remote=False)
        remote_rows = self.gh.branches(str(project))  # remote=True (Standard)

        def mapping(rows):
            return {row["name"]: (row["ahead"], row["behind"]) for row in rows}

        self.assertEqual({"main": (0, 0), "ap15-voraus": (1, 0),
                          "ap15-hinter": (0, 1)}, mapping(local_rows),
                         "remote=False bleibt bei der lokalen Referenz")
        self.assertEqual({"main": (0, 1), "ap15-voraus": (1, 0),
                          "ap15-hinter": (0, 1)}, mapping(remote_rows),
                         "remote=True liest die aktuelle Fern-Referenz")

    def test_remotes_und_fehlermaskierung_bleiben_wirksam(self):
        """AK4, GRÜN am Basisstand. mask_url und
        mask_embedded_credentials verschleiern Zugangsdaten weiterhin."""
        project = self.make_project("mask", github_enabled=False)
        git(project, "remote", "add", "origin",
            "https://ap15-token:ap15-k@github.com/ap15/proj.git")

        rows = self.gh.remotes(str(project))

        self.assertEqual([{"name": "origin",
                           "url": "https://***@github.com/ap15/proj.git"}],
                         rows, "mask_url verschleiert weiterhin")
        self.assertNotIn("ap15-k", json.dumps(rows))
        masked = self.gh.mask_embedded_credentials(
            "fatal: unable to access 'https://ap15-token:ap15-k@"
            "github.com/ap15/proj.git/': Fehler")
        self.assertNotIn("ap15-k", masked,
                         "Fehlertexte geben keine Zugangsdaten weiter")
        self.assertIn("://***@", masked)


# ------------------------------------------- AK4 + AK6: Credential-Kette
class CredentialChainTest(AP15Case):
    """AK4: Kette Projekt-Token > legacy globaler Token bleibt wirksam.
    AK6: GITHUB_TOKEN übersteuert weiterhin jeden git()-Aufruf des Durchgangs."""


    def test_umgebungs_token_gilt_fuer_jeden_git_aufruf_des_durchgangs(self):
        """AK6, GRÜN am Basisstand. Mit gesetztem GITHUB_TOKEN gewinnt die
        Umgebung gegen den hinterlegten Projekt-Token; jeder git-Kindprozess
        des Durchgangs erhält VIBE_GITHUB_CREDENTIAL mit dem Umgebungstoken."""
        project = self.make_project("uebersteuert")
        self.store_project_token(project)
        os.environ["GITHUB_TOKEN"] = ENV_TOKEN
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project), remote=False)

        self.assert_credential_on_every_git_call(calls, ENV_TOKEN)
        self.assertEqual({"set": True, "source": "umgebung"}, info["auth"])

    def test_projekt_token_gilt_fuer_jeden_git_aufruf_des_durchgangs(self):
        """AK4, GRÜN am Basisstand. Ohne Umgebungstoken gilt der
        verschlüsselte Projekt-Token für jeden git()-Aufruf des Durchgangs."""
        project = self.make_project("projekt-token")
        self.store_project_token(project)
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project), remote=False)

        self.assert_credential_on_every_git_call(calls, STORED_TOKEN)
        self.assertEqual({"set": True, "source": "projekt"}, info["auth"])

    def test_legacy_globaler_token_als_rueckfall(self):
        """AK4, GRÜN am Basisstand. Ohne Projekt-Token gilt der legacy
        globale Token aus <VIBE_STATE>/github-token weiterhin."""
        project = self.make_project("legacy")
        self.gh.save_token(LEGACY_TOKEN)
        self.addCleanup(self.gh.delete_token)
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project), remote=False)

        self.assert_credential_on_every_git_call(calls, LEGACY_TOKEN)
        self.assertEqual({"set": True, "source": "gespeichert"}, info["auth"])


# ---------------------------------------------------- AK5: defekte Ablage
class BrokenTokenTest(AP15Case):
    """AK5: Fehlende oder defekte Token-Ablage bleibt ohne Absturz; git()
    läuft ohne Credential-Konfiguration unverändert weiter."""


    def test_fehlende_token_datei_liefert_leerwert_ohne_credential(self):
        """AK5, GRÜN am Basisstand. Ohne jede Token-Ablage liefert
        read_project_token den Leerwert, es wird nichts abgeleitet und git()
        läuft ohne Credential-Konfiguration."""
        project = self.make_project("ohne-token")
        counter = ScryptCounter()
        calls = []
        with counter.patch(), mock.patch("subprocess.run", subprocess_spy(calls)):
            self.assertEqual("", self.gh.read_project_token(str(project)))
            rows = self.gh.branches(str(project), remote=False)

        self.assertEqual(0, counter.calls,
                         "Ohne Ablage gibt es nichts abzuleiten")
        self.assertIn("main", [row["name"] for row in rows])
        for call in self.git_child_calls(calls):
            self.assertIsNone(call["env"].get(self.gh.CREDENTIAL_ENV_NAME),
                              "Ohne Token keine Credential-Umgebung")
            self.assertNotIn("credential.https://github.com.helper",
                             "\n".join(call["argv"]),
                             "Ohne Token keine Credential-Konfiguration im argv")

    def test_defekte_token_datei_liefert_leerwert_ansicht_draeft_nicht(self):
        """AK5, GRÜN am Basisstand. Eine defekte Token-Datei liefert den
        Leerwert; branches() und die Projektansicht werfen nicht und
        degradieren nicht."""
        project = self.make_project("defekt")
        self.store_project_token(project)
        token_file = Path(self.gh._project_token_path(str(project)))
        token_file.write_text("{kein json", encoding="utf-8")

        self.assertEqual("", self.gh.read_project_token(str(project)))
        rows = self.gh.branches(str(project), remote=False)  # wirft nicht
        self.assertIn("main", [row["name"] for row in rows])

        cli = load_cli(self.ws, self.home)
        services = services_module()
        data = services.project_detail(cli, cli.PATHS, project.name)
        self.assertIn("branches", data["github"])
        self.assertIn("main",
                      [row["name"] for row in data["github"]["branches"]],
                      "Die Projektansicht degradiert bei defekter Ablage nicht")
        self.assertFalse(data["github"].get("error"))

    def test_defekter_masterschluessel_liefert_leerwert_ohne_absturz(self):
        """AK5, GRÜN am Basisstand. Ein Masterschlüssel falscher Länge gilt
        als beschädigt: Lesen liefert den Leerwert, die Ansicht läuft weiter."""
        project = self.make_project("schluessel")
        self.store_project_token(project)
        key_file = Path(self.gh.token_state_dir()) / self.gh.KEY_FILE
        key_file.write_bytes(b"zu-kurz")

        self.assertEqual("", self.gh.read_project_token(str(project)))
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project), remote=False)  # wirft nicht
        self.assertIn("main", [row["name"] for row in rows])
        for call in self.git_child_calls(calls):
            self.assertIsNone(call["env"].get(self.gh.CREDENTIAL_ENV_NAME),
                              "Mit beschädigtem Schlüssel wird kein Credential "
                              "erraten oder weitergereicht")


# ===========================================================================
# Projektansicht blockiert nicht bei nicht erreichbarem Git-Remote
# ===========================================================================

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.unit import env_support

WEB = REPO / "bin" / "vibe-web.py"

FAKE_TOKEN_ENV = "b8-short-env-token"
FAKE_TOKEN_STORED = "b8-short-stored-t"

REMOTE_BOUND = 40.0  # Die Projektansicht darf nie das 120-s-Git-Limit ausreizen.


ISOLATED_ENV_KEYS_b8 = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STATE",
    "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_PROFILE", "VIBE_UI_PORT", "VIBE_UI_BIND", "VIBE_OPENCODE_PORT",
    "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "NO_PROXY",
)


def github_module_b8():
    """Lädt ``bin/vibe_github.py`` als eigenständiges Modul."""
    if _GH_CACHE:
        return _GH_CACHE["gh"]
    loader = importlib.machinery.SourceFileLoader(
        "vibe_github_b8_under_test", str(GITHUB_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    _GH_CACHE["gh"] = module
    return module


def services_module_b8():
    """Lädt ``bin/vibe_services.py`` mit bin/ im Modulpfad."""
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    loader = importlib.machinery.SourceFileLoader(
        "vibe_services_b8_under_test", str(SERVICES_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli_b8(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME (V-008-Muster)."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader("vibe_b8_cli_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def git_b8(cwd, *argv, check=True):
    """Echtes git mit fester Test-Identität; nie produktive Konfiguration."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env,
        check=check, capture_output=True, text=True,
    )


def commit_file_b8(project, name, content, message):
    (Path(project) / name).write_text(content, encoding="utf-8")
    git_b8(project, "add", name)
    git_b8(project, "commit", "-q", "-m", message)


class HangingGitServer:
    """Lokaler Dienst, der Verbindungen annimmt und schweigt.

    ``git ls-remote`` gegen diese Adresse wartet bis zum Zeitlimit — genau
    das Fehlerbild des Bugs (nachfragendes/nicht erreichbares Remote).
    """

    def __init__(self):
        self.connections = []
        self.stopped = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.url = "git://127.0.0.1:%d/blocked/proj.git" % self.port
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.sock.settimeout(0.3)
        while not self.stopped.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            self.connections.append(conn)
            # Bewusst keine Antwort: git wartet so auf Daten.

    @property
    def hit_count(self):
        return len(self.connections)

    def close(self):
        self.stopped.set()
        with contextlib.suppress(OSError):
            self.sock.close()
        self.thread.join(timeout=5)
        for conn in self.connections:
            with contextlib.suppress(OSError):
                conn.close()


class _DenyingAuthHandler(BaseHTTPRequestHandler):
    """Git-HTTP-Gegenstelle, die auf jeden Abruf Authentifizierung verlangt."""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.server.requests.append(self.path)
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="b8-probe"')
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "0")
        self.end_headers()


class DenyingAuthServer:
    """401-Fake für git über http; nur auf 127.0.0.1 erreichbar."""

    def __init__(self):
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _DenyingAuthHandler)
        self.httpd.requests = self.requests
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d/proj.git" % self.httpd.server_address[1]

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class B8Case(unittest.TestCase):
    """Isolierte Umgebung: eigener VIBE-Wurzelordner, keine Zugangsdaten im ENV."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ws = self.base / "ws"
        self.ws.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.state = self.base / "state"
        self.state.mkdir()
        self.runtime = self.ws / "_logs"
        self.runtime.mkdir()
        self.install = self.base / "install"
        self.install.mkdir()
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_KEYS_b8}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy",
                    "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        os.environ.pop("VIBE_CONFIG_FILE", None)
        os.environ.pop("VIBE_PROFILE", None)
        (self.home / ".config" / "opencode" / "agents").mkdir(parents=True,
                                                              exist_ok=True)
        os.environ.update({
            "VIBE": str(self.ws),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.install),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.gh = github_module_b8()

    def restore_env(self):
        """Stellt die ursprüngliche Umgebung wieder her (keine Reste an Tests)."""
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_project(self, name="proj", github_enabled=False):
        project = self.ws / name
        project.mkdir(parents=True, exist_ok=True)
        git_b8(project, "init", "-q", "-b", "main")
        git_b8(project, "commit", "--allow-empty", "-q", "-m", "init")
        (project / ".vibe").mkdir(exist_ok=True)
        lines = ['TYPE=generic', 'TESTER=test-agent', 'SANDBOX="off"']
        if github_enabled:
            lines.append('GITHUB_ENABLED="1"')
            lines.append('GITHUB_REPO="blocked/proj"')
        (project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        return project

    def set_remote(self, project, url):
        git_b8(project, "remote", "add", "origin", url)

    def make_bare(self, name):
        bare = self.base / name
        bare.mkdir()
        git_b8(bare, "init", "-q", "--bare", "-b", "main")
        return bare


# ---------------------------------------------------------------- AC1: Lokalmodus
class StatusLocalRefsTest(B8Case):
    """AC1: status(remote=False) liest Ahead/Behind nur aus lokalen Referenzen."""

    def test_status_liesst_ahead_behind_nur_aus_lokalen_referenzen(self):
        bare = self.make_bare("upstream.git")
        project = self.make_project(github_enabled=True)
        self.set_remote(project, "file://" + str(bare))
        git_b8(project, "push", "-q", "-u", "origin", "main")
        self.assertTrue(self.gh.status(str(project), remote=False)["unpushed"] is False)

        commit_file_b8(project, "arbeit.txt", "lokal", "B8: lokale Arbeit")
        info = self.gh.status(str(project), remote=False)

        self.assertEqual(info["branch"], "main")
        self.assertEqual((info["ahead"], info["behind"]), (1, 0),
                         "Der unveröffentlichte Commit muss aus der lokalen "
                         "origin/<branch>-Referenz als ahead=1 erkennbar sein")
        self.assertTrue(info["unpushed"])

        # Ein Zweitarbeiter schiebt ferne Arbeit ins Bare-Repo, ohne dass das
        # Projekt sie abruft. Die lokale Referenz kennt ihn nicht: behind
        # bleibt 0 (kein heimlicher Netzabruf in der Ansicht).
        zweit = self.base / "zweit"
        git_b8(self.base, "clone", "-q", "file://" + str(bare), str(zweit))
        commit_file_b8(zweit, "partner.txt", "draußen", "B8: ferne Arbeit")
        git_b8(zweit, "push", "-q", "origin", "main")

        info_after = self.gh.status(str(project), remote=False)

        self.assertEqual((info_after["ahead"], info_after["behind"]), (1, 0),
                         "Es wurde ausschließlich die lokale Referenz gelesen")

    def test_status_remote_false_wartet_nicht_auf_haengendes_remote(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        start = time.monotonic()
        info = self.gh.status(str(project), remote=False)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5.0,
                        "status(remote=False) wartete auf das blockierende "
                        "Remote (%.1fs)" % elapsed)
        self.assertEqual((info["ahead"], info["behind"]), (0, 0),
                         "Ohne lokale Fern-Referenz bleibt der Stand neutral")
        self.assertEqual(0, hanging.hit_count,
                         "Der Fake-Dienst wurde kontaktiert — Netzverbot im "
                         "Lokalmodus verletzt")

    def test_branches_remote_false_bleibt_fernfrei_und_vollstaendig(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            start = time.monotonic()
            rows = self.gh.branches(str(project), remote=False)
            elapsed = time.monotonic() - start

        self.assertLess(elapsed, 5.0, "branches(remote=False) wartete: %.1fs" % elapsed)
        names = [row["name"] for row in rows]
        self.assertIn("main", names)
        self.assertTrue(any(row.get("current") for row in rows))
        for row in rows:
            self.assertIsInstance(row["ahead"], int)
            self.assertIsInstance(row["behind"], int)
        self.assertEqual([], network_calls(calls),
                         "remote=False darf keinen Fernaufruf auslösen: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)


# ------------------------------------------------------ AC1: Projektansicht
class ProjectDetailLocalModeTest(B8Case):
    """AC1: ``vibe_services.project_detail`` fragt das Git-Remote nie an.

    Schlüssel der Aussage: GITHUB_ENABLED ist gesetzt; den Lokalmodus
    bezeugt somit der Aufrufort (remote=False), nicht die Konfiguration.
    """

    def setUp(self):
        super().setUp()
        self.cli = load_cli_b8(self.ws, self.home)
        self.services = services_module_b8()
        self.paths = self.cli.PATHS

    def test_project_detail_fragt_origin_trotz_github_enabled_nicht_an(self):
        bare = self.make_bare("upstream.git")
        project = self.make_project(github_enabled=True)
        self.set_remote(project, "file://" + str(bare))
        git_b8(project, "push", "-q", "-u", "origin", "main")
        commit_file_b8(project, "arbeit.txt", "lokal", "B8: ungesehene Arbeit")

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            data = self.services.project_detail(self.cli, self.paths, "proj")

        self.assertEqual([], network_calls(calls),
                         "Die Projektansicht darf das Git-Remote nie "
                         "ansprechen (ls-remote/fetch/pull/push verboten): %r"
                         % [c["argv"] for c in network_calls(calls)])
        github = data["github"]
        self.assertIn("branches", github)
        branch_names = [row["name"] for row in github["branches"]]
        self.assertIn("main", branch_names)
        for row in github["branches"]:
            self.assertIsInstance(row["ahead"], int)
            self.assertIsInstance(row["behind"], int)
        self.assertTrue(github["unpushed"],
                        "Ahead/Behind muss aus der lokalen Referenz stammen")
        self.assertTrue(github["enabled"])

    def test_project_detail_ohne_git_remote_bewahrt_die_karte(self):
        project = self.make_project(github_enabled=False)
        data = self.services.project_detail(self.cli, self.paths, "proj")

        github = data["github"]
        branch_names = [row["name"] for row in github["branches"]]
        self.assertIn("main", branch_names)
        self.assertFalse(github["enabled"])
        self.assertEqual((github["ahead"], github["behind"]), (0, 0))


# --------------------------------------------- AC1 Ende-an-Ende über das Dashboard
class ApiProjectBlockingTest(unittest.TestCase):
    """AC1 Ende-an-Ende: GET /api/project bleibt bei hängendem origin
    antwortend und beweist an der echten Oberfläche, dass vor dem Fix
    geleerte 120 Sekunden Wartezeit nur mehr Geschichte wären."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.ws = cls.root / "ws"
        cls.ws.mkdir()
        cls.hanging = HangingGitServer()
        project = cls.ws / "proj"
        project.mkdir()
        git_b8(project, "init", "-q", "-b", "main")
        git_b8(project, "commit", "--allow-empty", "-q", "-m", "init")
        git_b8(project, "remote", "add", "origin", cls.hanging.url)
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nTESTER=test-agent\nSANDBOX="off"\n'
            'GITHUB_ENABLED="1"\nGITHUB_REPO="blocked/proj"\n', encoding="utf-8")
        (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "state").mkdir()
        (cls.root / "install").mkdir()
        (cls.ws / "_logs").mkdir()
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        cls.port = probe.getsockname()[1]
        probe.close()
        env = env_support.isolated_environ()
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "http_proxy", "https_proxy",
                    "all_proxy"):
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.ws),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(cls.root / "state"),
            "VIBE_RUNTIME": str(cls.ws / "_logs"),
            "VIBE_AGENTS_DIR": str(cls.root / "home" / ".config" / "opencode"
                                   / "agents"),
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.root / "home"),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.ws / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
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
        cls.hanging.close()
        cls.tmp.cleanup()

    def get(self, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", method="GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_api_project_antwortet_ohne_fernkontakt_bei_haengendem_remote(self):
        started = time.monotonic()
        status, body = self.get("/api/project?name=proj")
        elapsed = time.monotonic() - started

        self.assertEqual(200, status, body)
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Projektansicht wartete %.1fs auf das Remote — "
                        "Vor-Fix-Verhalten" % elapsed)
        github = body["github"]
        self.assertIn("branches", github)
        self.assertIsInstance(github["branches"], list)
        self.assertEqual(github["branch"], "main")
        self.assertEqual(0, self.hanging.hit_count,
                         "Das Dashboard versuchte den Ferndienst zu "
                         "erreichen (%d Verbindungen)" % self.hanging.hit_count)


# ---------------------------------------------- AC2: kein Remote ohne GitHub
class NoRemoteWithoutGithubTest(B8Case):
    """AC2: Ohne GITHUB_ENABLED wird generell kein Remote kontaktiert."""

    def test_status_ohne_github_enabled_kontaktiert_nicht_den_ferndienst(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=False)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            info = self.gh.status(str(project))  # remote=True: Normalmodus!

        self.assertEqual([], network_calls(calls),
                         "Auch mit remote=True darf die Status-Ebene ohne "
                         "aktivierte Verknüpfung keinen Fernaufruf machen: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)
        self.assertFalse(info["enabled"])
        self.assertEqual((info["ahead"], info["behind"]), (0, 0))

    def test_branches_ohne_github_enabled_bleibt_fernfrei(self):
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=False)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            rows = self.gh.branches(str(project))  # remote=True: Normalmodus!

        self.assertEqual([], network_calls(calls),
                         "branches() ohne GITHUB_ENABLED darf nicht "
                         "ls-remote: %r"
                         % [c["argv"] for c in network_calls(calls)])
        self.assertEqual(0, hanging.hit_count)
        self.assertIn("main", [row["name"] for row in rows])


# ------------------------------------------------------------------ AC3: Zeitlimits
class RemoteReadTimeoutTest(B8Case):
    """AC3: Fernleseabfragen laufen beim hängenden Remote auf Timeout."""

    def test_reine_fernleseabfrage_grenzt_auf_10_sekunden(self):
        """Vorbedingung: GitHub aktiviert, origin hängt schweigend;
        Aktion: status(remote=True);
        Erwartung: ls-remote wird unternommen, bricht nach ~10 s ab
        (nicht 120 s), Ahead/Behind fällt auf 0/0 zurück."""
        hanging = HangingGitServer()
        self.addCleanup(hanging.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, hanging.url)

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            started = time.monotonic()
            info = self.gh.status(str(project), remote=True)
            elapsed = time.monotonic() - started

        verbs = [git_verb(c["argv"]) for c in network_calls(calls)]
        self.assertIn("ls-remote", verbs,
                      "Ohne den Fernkontaktversuch trägt der Test nichts bei")
        self.assertGreaterEqual(elapsed, 9.0,
                                "Ein Zeitlimit unter 10 s wäre eine "
                                "unangekündigte Verschärfung (%.1fs)" % elapsed)
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Fernlese wartete auf das 120-s-Git-Limit "
                        "(%.1fs) — Vor-Fix-Verhalten" % elapsed)
        self.assertEqual((info["ahead"], info["behind"]), (0, 0),
                         "Bei Fernausfall bleibt der Stand neutral (keine "
                         "veralteten Referenzen)")

    def test_fetch_pull_push_behalten_120_sekunden_zeitlimit(self):
        project = self.make_project(github_enabled=False)
        self.set_remote(project, "file:///nicht/angelegt/b8-missing")

        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            ok_fetch, _ = self.gh.fetch(str(project))
            ok_pull, _ = self.gh.pull(str(project))
            ok_push, _ = self.gh.push(str(project), "main")

        self.assertFalse(ok_fetch)
        self.assertFalse(ok_pull)
        self.assertFalse(ok_push)
        timeouts = {git_verb(c["argv"]): c["timeout"]
                    for c in network_calls(calls)}
        for verb in ("fetch", "pull", "push"):
            self.assertIn(verb, timeouts, "Aktion %s lief gar nicht" % verb)
            self.assertEqual(120, timeouts[verb],
                             "Bewusste Aktion %s muss 120 s behalten, hat %s"
                             % (verb, timeouts[verb]))
        self.assertEqual(10, self.gh.TIMEOUT_REMOTE_READ)
        self.assertEqual(120, self.gh.TIMEOUT_GIT)


# ----------------------------------------------------------------- AC4: Prompt-Freiheit
class PromptFreeGitTest(B8Case):
    """AC4: Git läuft ohne Terminal-Prompt, unabhängig vom Token."""

    def record_status(self, project):
        calls = []
        with mock.patch("subprocess.run", subprocess_spy(calls)):
            started = time.monotonic()
            info = self.gh.status(str(project), remote=True)
            elapsed = time.monotonic() - started
        return calls, info, elapsed

    def assert_prompt_free(self, calls):
        for call in calls:
            env = call["env"]
            self.assertEqual("0", env.get("GIT_TERMINAL_PROMPT"),
                             "GIT_TERMINAL_PROMPT=0 fehlt: argv=%r"
                             % (call["argv"],))
            self.assertEqual("never", env.get("GCM_INTERACTIVE"),
                             "GCM_INTERACTIVE=never fehlt: argv=%r"
                             % (call["argv"],))

    def test_git_aufrufe_sind_stets_ohne_terminal_prompt(self):
        project = self.make_project(github_enabled=True)

        calls, _info, _elapsed = self.record_status(project)

        self.assertTrue(calls)
        self.assert_prompt_free(calls)

    def test_git_aufrufe_bleiben_promptfrei_auch_mit_token(self):
        project = self.make_project(github_enabled=True)
        self.gh.save_token(FAKE_TOKEN_STORED)
        self.addCleanup(lambda: self.gh.delete_token())
        os.environ["GITHUB_TOKEN"] = FAKE_TOKEN_ENV

        calls, _info, _elapsed = self.record_status(project)

        self.assertTrue(calls)
        self.assert_prompt_free(calls)
        for call in calls:
            joined = "\n".join(call["argv"])
            self.assertNotIn(FAKE_TOKEN_STORED, joined)
            self.assertNotIn(FAKE_TOKEN_ENV, joined,
                             "Der Tokeninhalt darf nie im argv stehen")

    def test_http_remote_mit_auth_forderung_blockiert_nicht(self):
        """Authentifizierungs-Forderung (401) stoppt die Ansicht nicht."""
        denying = DenyingAuthServer().start()
        self.addCleanup(denying.close)
        project = self.make_project(github_enabled=True)
        self.set_remote(project, denying.url)

        calls, info, elapsed = self.record_status(project)

        self.assertGreater(len(list(denying.requests)), 0,
                           "Ein Kontaktversuch war für diesen Nachweis nötig")
        self.assertLess(elapsed, REMOTE_BOUND,
                        "Die Auth-Forderung blockierte die Ansicht (%.1fs)" % elapsed)
        self.assert_prompt_free(network_calls(calls))
        self.assertEqual((info["ahead"], info["behind"]), (0, 0))


# ===========================================================================
# Projekt öffnen, obwohl ``origin`` nicht erreichbar ist
# ===========================================================================

import contextlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import vibe_github  # noqa: E402 - Pfad muss zuerst gesetzt sein
import vibe_services  # noqa: E402 - nutzt dasselbe vibe_github-Modul

UNREACHABLE_ORIGIN = "https://192.0.2.1/b8/nie-erreichbar.git"
NETWORK_GIT = ("ls-remote", "fetch")

# Dieselbe ENV-Isolation wie in der etablierten B8-Suite (B8Case): kein
# produktives HOME, kein produktiver Zustand, keine geerbten Zugangsdaten.
ISOLATED_ENV_KEYS_b82 = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STATE",
    "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_PROFILE", "VIBE_UI_PORT", "VIBE_UI_BIND", "VIBE_OPENCODE_PORT",
    "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
    "GITHUB_TOKEN", "GH_TOKEN",
    "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM",
    "http_proxy", "https_proxy", "all_proxy", "NO_PROXY",
)

GIT_IDENTITY_b8 = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    # Persönliche Git-Konfiguration darf den Test nicht beeinflussen.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git_b82(cwd, *argv):
    """Echtes Git im temporären Verzeichnis mit fester Testidentität."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY_b8)
    return subprocess.run(
        ["git", *argv], cwd=str(cwd), env=env, check=True,
        capture_output=True, text=True,
    )


def git_out(cwd, *argv):
    return git_b82(cwd, *argv).stdout.strip()


class StubVibe:
    """Nur die für ``project_detail`` nötigen, nicht getesteten CLI-Ansichten.

    Die GitHub-Ebene wird bewusst nicht ersetzt: ``vibe_services`` ruft das
    echte ``vibe_github``-Modul gegen ein echtes Git-Repository auf.
    """

    def __init__(self, project):
        self.project = str(project)

    def ppath(self, name):
        return self.project

    def git_info(self, name):
        return "main", 1, "abc1234 lokaler Commit (jetzt)"

    def open_items(self, name):
        return []

    def run_state(self, name):
        return {
            "run_id": None, "state": "idle", "running": False,
            "started": False, "agent": "", "session": "", "log": "",
            "verify_log": "", "exit_code": None,
        }

    def ptype(self, name):
        return "generic"

    def is_init(self, name):
        return True

    def logpath(self, name, kind="run"):
        return os.path.join(self.project, "_logs", "proj.log")

    def pause_after_active(self, name):
        return False

    def feedback_items(self, name):
        return []

    def ticket_items(self, name):
        return []

    def verify_command(self, name, mode="quick"):
        return "true"

    def penv(self, name):
        return {"TYPE": "generic"}

    def write_dirs(self, name):
        return []

    def write_dirs_default(self, name):
        return []

    def write_dirs_custom(self, name):
        return False

    def sandbox_status(self, name):
        return {
            "enabled": False, "tools": [], "write_dirs": [], "tool_caches": [],
            "missing_tools": [], "bwrap": "", "state_dir": "", "error": "",
        }


class ProjectWithoutReachableOrigin(unittest.TestCase):
    """Echtes Git-Repo, dessen ``origin`` absichtlich nicht erreichbar ist."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.real_git = vibe_github.git
        self.network_calls = []

        # Isolierte Umgebung: eigener Home-/Zustands-/Laufzeitordner, keine
        # geerbten Zugangsdaten oder produktiven Pfade in den Modulaufrufen.
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.install = self.root / "install"
        self.install.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV_KEYS_b82}
        self.addCleanup(self.restore_env)
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TERMINAL_PROMPT",
                    "GIT_ASKPASS", "SSH_ASKPASS", "http_proxy",
                    "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        os.environ.pop("VIBE_CONFIG_FILE", None)
        os.environ.pop("VIBE_PROFILE", None)
        os.environ.update({
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.install),
            "VIBE_AGENTS_DIR": str(self.agents),
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_PROXY": "127.0.0.1,localhost",
        })

        git_b82(self.project, "init", "-q", "-b", "main")
        (self.project / "base.txt").write_text("Basis\n", encoding="utf-8")
        git_b82(self.project, "add", "base.txt")
        git_b82(self.project, "commit", "-q", "-m", "Basis")
        base_sha = git_out(self.project, "rev-parse", "HEAD")

        git_b82(self.project, "remote", "add", "origin", UNREACHABLE_ORIGIN)
        # Lokale Fern-Referenzen: genau der Stand, den ein früherer Abgleich
        # hinterlassen hätte. Kein Netzwerk ist daran beteiligt.
        git_b82(self.project, "update-ref", "refs/remotes/origin/main", base_sha)

        (self.project / "lokal.txt").write_text("lokal\n", encoding="utf-8")
        git_b82(self.project, "add", "lokal.txt")
        git_b82(self.project, "commit", "-q", "-m", "Lokaler Commit")
        self.local_sha = git_out(self.project, "rev-parse", "HEAD")

        # feature steht auf der Basis; origin/feature enthält einen nur dort
        # vorhandenen Commit -> feature ist 0 voraus und 1 hinter.
        git_b82(self.project, "branch", "feature", base_sha)
        tree = git_out(self.project, "rev-parse", "HEAD^{tree}")
        remote_only = git_out(
            self.project, "commit-tree", tree, "-p", base_sha, "-m", "Nur remote"
        )
        git_b82(self.project, "update-ref", "refs/remotes/origin/feature", remote_only)

        # Branch ohne jede origin-Referenz bleibt lokal bei 0/0.
        git_b82(self.project, "branch", "local-only", base_sha)

        (self.project / ".vibe").mkdir()
        self.write_env(enabled=True)

    def write_env(self, enabled):
        """Projektkonfiguration mit oder ohne ``GITHUB_ENABLED`` schreiben."""
        lines = ["TYPE=generic", 'SANDBOX="off"']
        if enabled:
            lines += ['GITHUB_ENABLED="1"', 'GITHUB_REPO="example/b8"']
        (self.project / ".vibe" / "project.env").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def restore_env(self):
        """Stellt die ursprüngliche Umgebung wieder her (keine Reste an Tests)."""
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @contextlib.contextmanager
    def no_network_git(self):
        """Lässt ``ls-remote``/``fetch`` sofort scheitern und protokolliert sie.

        Alle übrigen Git-Aufrufe (rev-parse, for-each-ref, rev-list, ...) gehen
        unverändert an das echte Git im temporären Repository.
        """

        def guarded(project_path, *args):
            argv = [str(arg) for arg in args]
            if argv and argv[0] in NETWORK_GIT:
                self.network_calls.append(argv)
                return 128, "Netzwerk im Test gesperrt"
            return self.real_git(project_path, *args)

        with mock.patch.object(vibe_github, "git", side_effect=guarded):
            yield

    # ---------------------------------------------------------------- AK1
    def test_project_detail_does_not_touch_unreachable_origin(self):
        """AK1: Dashboard-Ansicht bleibt ohne Netzwerk-Git-Abfrage nutzbar."""
        vibe = StubVibe(self.project)
        paths = SimpleNamespace(runtime=str(self.root / "runtime"))

        started = time.monotonic()
        with self.no_network_git():
            data = vibe_services.project_detail(vibe, paths, "proj")
        elapsed = time.monotonic() - started

        self.assertEqual(
            self.network_calls, [],
            "project_detail hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        self.assertLess(elapsed, 5.0, "project_detail hat zu lange gewartet")
        github = data["github"]
        self.assertNotIn("error", github, "GitHub-Ansicht wurde unerwartet degradiert")
        self.assertEqual(github["branch"], "main")
        self.assertEqual(github["ahead"], 1)
        self.assertEqual(github["behind"], 0)
        self.assertEqual([row["name"] for row in github["remotes"]], ["origin"])
        self.assertEqual(
            {row["name"] for row in github["branches"]},
            {"main", "feature", "local-only"},
        )

    # ---------------------------------------------------------------- AK2
    def test_status_offline_uses_local_origin_refs(self):
        """AK2: status(remote=False) rechnet gegen die lokale origin-Referenz."""
        with self.no_network_git():
            data = vibe_github.status(str(self.project), remote=False)

        self.assertEqual(
            self.network_calls, [],
            "status(remote=False) hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        self.assertTrue(data["enabled"])
        self.assertEqual(data["branch"], "main")
        self.assertEqual((data["ahead"], data["behind"]), (1, 0))
        self.assertTrue(data["unpushed"])
        self.assertEqual([row["name"] for row in data["remotes"]], ["origin"])

    def test_branches_offline_uses_local_origin_refs(self):
        """AK2: branches(remote=False) liefert Abstände aus lokalen Referenzen."""
        with self.no_network_git():
            rows = vibe_github.branches(str(self.project), remote=False)

        self.assertEqual(
            self.network_calls, [],
            "branches(remote=False) hat eine Fernabfrage ausgelöst: %r" % (self.network_calls,),
        )
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(set(by_name), {"main", "feature", "local-only"})
        self.assertTrue(by_name["main"]["current"])
        self.assertEqual((by_name["main"]["ahead"], by_name["main"]["behind"]), (1, 0))
        self.assertFalse(by_name["feature"]["current"])
        self.assertEqual((by_name["feature"]["ahead"], by_name["feature"]["behind"]), (0, 1))
        self.assertEqual((by_name["local-only"]["ahead"], by_name["local-only"]["behind"]), (0, 0))

    # ---------------------------------------------------------------- AK3
    def test_status_without_github_enabled_does_not_query_remote(self):
        """AK3: Ohne GITHUB_ENABLED bleibt der normale Status rein lokal."""
        self.write_env(enabled=False)

        with self.no_network_git():
            data = vibe_github.status(str(self.project))

        self.assertEqual(
            self.network_calls, [],
            "status ohne GITHUB_ENABLED hat eine Fernabfrage ausgelöst: %r"
            % (self.network_calls,),
        )
        self.assertFalse(data["enabled"])
        self.assertEqual(data["branch"], "main")


if __name__ == "__main__":
    unittest.main()
