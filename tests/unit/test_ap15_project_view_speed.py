"""AP15 — Schnelles Öffnen der Projektansicht (scrypt-Ableitung einmal je Anfrage).

Akzeptanzkriterien aus dem Arbeitspaket AP15 (TICKETS.md), unabhängig vom
Implementierungsdiff abgeleitet:

* AK1: Die Token-Entschlüsselung (scrypt-Key-Ableitung in
  ``vibe_github._derive_key``) läuft pro Dashboard-Anfrage höchstens genau
  einmal: ``project_detail()`` leitet das Credential einmal ab;
  ``status()``/``branches()`` reichen es an alle ``git()``-Aufrufe ihres
  Durchgangs weiter. Kein Cache über Anfragen hinweg: zwei
  aufeinanderfolgende Anfragen leiten jeweils neu ab.
* AK2: ``remotes()`` wird je Durchgang einmal geprüft, nicht je Branch
  (bei 120+ Branches: genau ein ``git remote -v``-Aufruf im
  ``branches()``-Durchgang).
* AK3: ``branches()`` bleibt funktional identisch: Branchname,
  current-Flag, last, ahead/behind unverändert; ``remote=False`` liest nur
  lokale Referenzen, kein Netz, keine Schreibzugriffe.
* AK4: Die Credential-Kette (Umgebung ``GITHUB_TOKEN``/``GH_TOKEN`` >
  verschlüsselter Projekt-Token > legacy globaler Token in
  ``<VIBE_STATE>/github-token``) bleibt wirksam; URL-Maskierung
  (``mask_url``/``mask_embedded_credentials``) bleibt wirksam; der
  ``remote=True``-Pfad bleibt unangetastet.
* AK5: Fehlende oder defekte Token-Datei bleibt ohne Absturz
  (Leerwert-Kette, Projektansicht degradiert nicht, ``git()`` verhält sich
  ohne Token unverändert).
* AK6: Bei gesetztem ``GITHUB_TOKEN`` gilt dieses Credential weiterhin für
  alle ``git()``-Aufrufe des Durchgangs (``VIBE_GITHUB_CREDENTIAL`` in der
  Prozessumgebung jedes git-Kindprozesses).

Testfälle und erwartetes Ergebnis am unveränderten Basisstand (Rotphase):

* AK1  test_branches_durchgang_leitet_credential_genau_einmal_ab — ROT
       (hunderte scrypt-Aufrufe statt genau 1)
* AK1  test_status_durchgang_leitet_credential_hoechstens_einmal_ab — ROT
       (mehrere scrypt-Aufrufe statt genau 1)
* AK1  test_project_detail_leitet_das_credential_genau_einmal_ab — ROT
       (status + branches leiten getrennt ab)
* AK1  test_zwei_durchgaenge_leiten_jeweils_neu_ab_kein_anfrage_cache —
       GRÜN (bewusste Negativerwartung/Regressionsschutz)
* AK2  test_branches_durchgang_prueft_remotes_genau_einmal — ROT
       (ein ``git remote -v`` je Branch)
* AK3  test_branches_121_branches_liefert_alle_zeilen_ohne_aenderung —
       GRÜN (Verhaltensgleichheit am Basisstand)
* AK4  test_remotes_und_fehlermaskierung_bleiben_wirksam — GRÜN
* AK4  test_fernmodus_remote_true_liest_die_aktuelle_fern_referenz — GRÜN
* AK4  test_projekt_token_gilt_fuer_jeden_git_aufruf_des_durchgangs — GRÜN
* AK4  test_legacy_globaler_token_als_rueckfall — GRÜN
* AK5  test_fehlende_token_datei_liefert_leerwert_ohne_credential — GRÜN
* AK5  test_defekte_token_datei_liefert_leerwert_ansicht_draeft_nicht — GRÜN
* AK5  test_defekter_masterschluessel_liefert_leerwert_ohne_absturz — GRÜN
* AK6  test_umgebungs_token_gilt_fuer_jeden_git_aufruf_des_durchgangs —
       GRÜN (Regressionsschutz)

Isolierte Umgebung: eigene ``VIBE_STATE``/``HOME``-Ordner unter tempfile,
feste Git-Identität, keine produktiven Pfade, kein echtes Netz (alle
Remotes sind lokale ``file://``-Repos). Der ``subprocess.run``-Spy ersetzt
nichts: echte Prozesse laufen weiter, es werden nur argv und env
protokolliert (Muster: tests/unit/test_b8_no_remote_block.py). Die
scrypt-Zählung patcht ``hashlib.scrypt`` (unittest.mock) und führt die
echte Ableitung unverändert aus. Auf FUSE/NTFS werden Dateirechte nicht
als wirksam vorausgesetzt.

Ausführen mit:

    python3 -m unittest tests.unit.test_ap15_project_view_speed -v
"""
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


if __name__ == "__main__":
    unittest.main()
