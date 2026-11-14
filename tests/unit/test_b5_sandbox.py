"""Unabhängige Tests für Arbeitspaket B5 (Bug: „Sandbox fehlerhaft“).

Quellen: FEEDBACK.md Eintrag B5 und SPEC.md (F7-Sandbox). Die Fälle wurden
ohne Einsicht in einen Implementierungsdiff aus den Akzeptanzkriterien
abgeleitet; die Ergänzungen aus Reviewrunde 1 (docs/reviews/B5-review-1.md)
sind als Methoden M3a, M3b, M4 und M5 markiert:

1. Escape-Loch /dev/shm: Ohne ausdrückliche Freigabe in
   .vibe/permissions.json bekommt /dev/shm ein frisches, isoliertes tmpfs
   (kein Host-Verzeichnis). M3a: Das tmpfs-Paar muss auf Argumentebene vor
   allen Bindungen stehen; M3b: Ein echter Lauf mit Projekt unter /dev/shm
   schreibt in das Projekt (Bindung sichtbar) und hinterlässt keine
   Schreibmarke im Host-/dev/shm (isoliert).
2. Zeichenlimit: state_dir(project) weicht bei Zustandspfaden über der
   Begrenzung auf die tmpfs-Wurzel /tmp/opencode/vsb mit dem SHA-256-Präfix
   des Projektwegs aus. Die Begrenzung von 84 Zeichen hält Sicherheitsabstand
   zur AF_UNIX-Grenze von 108: TMPDIR = state + "/tmp" bleibt <= 88 Zeichen
   und der tmux-Socket darunter <= 106. M4: Das Ausweichen greift schon im
   Band 85..100 Zeichen, nicht erst ab der alten 100er-Grenze.
3. status() meldet state_dir konsistent zu state_dir(project).
4. Rückfälle des Bestands brechen nicht: write_dirs enthält weiterhin das
   Projekt-Workflow-Verzeichnis, /tmp/opencode und den Zustandsort; setenv
   belegt XDG_DATA_HOME, XDG_CACHE_HOME, XDG_STATE_HOME und TMPDIR.
   M5: Die in den Tests erzeugten Zustandsordner werden wieder entfernt.
"""

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANDBOX = REPO / "bin" / "vibe_sandbox.py"

# Sichere Grenze für Zustandspfade; nachgeschaltete Werkzeugpfade (Sockets)
# dürfen die AF_UNIX-Grenze von 108 Zeichen nicht erreichen. Die
# Implementierung begrenzt Zustandspfade selbst auf 84 Zeichen
# (STATE_PATH_LIMIT); hier gilt dieselbe Schwelle. Pfade über 84 weichen
# auf die kurze Rückfallform aus.
LIMIT = 84
# Fester Kurzpfad (tmpfs) für den Rückfall, wenn der Zustandsort zu lang wäre.
FALLBACK_ROOT = "/tmp/opencode/vsb"


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class B5Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="b5-base-")
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_file = self.project / ".vibe" / "project.env"
        self.env_file.write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore, "HOME", old_home)
        self.bwrap = shutil.which("bwrap")
        self.sandbox = load_module(SANDBOX, "b5_vibe_sandbox_under_test")

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        self.tmp.cleanup()

    def override_root_env(self, value):
        old = os.environ.get("VIBE_SANDBOX_ROOT")
        self.addCleanup(self._restore, "VIBE_SANDBOX_ROOT", old)
        if value is None:
            os.environ.pop("VIBE_SANDBOX_ROOT", None)
        else:
            os.environ["VIBE_SANDBOX_ROOT"] = value

    def long_project(self, name_len=200):
        """Projekt mit ausdrücklich sehr langem Namen und langem Vorbereich."""
        name = "b" * name_len
        base = self.root / ("lang-" + "x" * 120)
        project = base / name
        (project / ".vibe").mkdir(parents=True, exist_ok=True)
        (project / ".vibe" / "project.env").write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        return project

    def cleanup_state_dir(self, project):
        """M5: Den von state_dir(project) bestimmten Zustandsordner leeren.

        Genau der zurückgegebene Pfad, keine anderen Verzeichnisse.
        """
        path = self.sandbox.state_dir(project)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def shm_project(self):
        """Projektverzeichnis unter /dev/shm, vor dem Lauf aus dem Test-
        prozess angelegt und in die Schreibrechte-Liste aufgenommen."""
        base = Path("/dev/shm") / (
            "b5-proj-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        project = base / "proj"
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        (project / ".vibe" / "permissions.json").write_text(
            json.dumps({"write_dirs": [str(project)]}),
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, str(base), ignore_errors=True)
        return project

    @staticmethod
    def digest_of(project):
        return hashlib.sha256(
            os.path.realpath(project).encode("utf-8")
        ).hexdigest()[:10]

    def run_sandboxed(self, project, script):
        env = dict(
            os.environ,
            HOME=str(self.home),
            VIBE=str(self.root),
        )
        env.pop("VIBE_SANDBOX_ROOT", None)
        return subprocess.run(
            [sys.executable, str(SANDBOX), str(project), "--", "/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    def unique_shm_marker(self, label):
        return "/dev/shm/b5-" + label + "-" + str(os.getpid()) + "-" + str(time.time_ns())


def pair_positions(argv, flag):
    """Positionen, an denen `flag` beginnt; Ziel/Beiwerk folgt dahinter."""
    return [index for index in range(len(argv) - 1) if argv[index] == flag]


def collect_setenv(argv):
    """Tabelle der --setenv-Paare eines bwrap-argv."""
    result = {}
    for first, key, value in zip(argv, argv[1:], argv[2:]):
        if first == "--setenv":
            result[key] = value
    return result



class ShmArgumentTest(B5Fixture):
    """Zu 1: Auf Argumentebene bekommt /dev/shm ein privates tmpfs."""

    def test_bwrap_arguments_mount_a_private_shm_unless_allowed(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        pairs = list(zip(argv, argv[1:]))
        expected = ("--tmpfs", "/dev/shm")
        self.assertIn(expected, pairs)
        self.assertEqual(pairs.count(expected), 1)
        # Nicht erlaubt heißt: kein Binden des Host-Verzeichnisses.
        self.assertNotIn(("--bind", "/dev/shm"), pairs)
        self.assertNotIn(("--ro-bind", "/dev/shm"), pairs)

        # Ausdrücklich erlaubt: kein privates tmpfs, Host-Verzeichnis bleibt
        # über die Schreibfreigabe erreichbar.
        self.project.joinpath(".vibe", "permissions.json").write_text(
            json.dumps({"write_dirs": ["/dev/shm", str(self.project)]}),
            encoding="utf-8",
        )
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        pairs = list(zip(argv, argv[1:]))
        self.assertNotIn(("--tmpfs", "/dev/shm"), pairs)


    def test_shm_tmpfs_pair_precedes_every_regular_bind_pair(self):
        """M3a: tmpfs-Paar vor jeder --bind-Einleitung (bwrap stapelt Mounts
        in Argumentreihenfolge; danach überschattet der frische Mount
        Bindungen auf /dev/shm-Unterpfade — Defekt aus Runde 1)."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        shm_pair = [
            index for index in pair_positions(argv, "--tmpfs")
            if argv[index + 1] == "/dev/shm"
        ]
        self.assertEqual(len(shm_pair), 1)
        bind_positions = pair_positions(argv, "--bind")
        self.assertTrue(bind_positions, "Mindestens eine --bind-Bindung erwartet")
        for index in bind_positions:
            self.assertLess(shm_pair[0], index)

    def test_bind_of_a_project_under_shm_is_not_shadowed_by_the_tmpfs(self):
        """M3a-Variante: Bindung auf einen /dev/shm-Unterpfad (Projektort)
        steht nach dem tmpfs-Paar; /dev/shm selbst bleibt unerlaubt."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        project = self.shm_project()
        self.cleanup_state_dir(project)
        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        shm_pair = [
            index for index in pair_positions(argv, "--tmpfs")
            if argv[index + 1] == "/dev/shm"
        ]
        self.assertEqual(
            len(shm_pair), 1,
            "Ohne Freigabe von /dev/shm muss das tmpfs-Paar existieren",
        )
        shm_binds = [
            index for index in range(len(argv) - 1)
            if argv[index] in ("--bind", "--ro-bind")
            and argv[index + 1].startswith("/dev/shm")
        ]
        self.assertTrue(
            shm_binds,
            "Das Projekt unter /dev/shm muss eingebunden werden",
        )
        for index in shm_binds:
            self.assertLess(shm_pair[0], index)


class ShmIsolationTest(B5Fixture):
    """Zu 1: Echte bwrap-Läufe — /dev/shm ist isoliert und schreibbar."""

    def test_host_shm_content_is_invisible_inside_the_sandbox(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        host_marker = self.unique_shm_marker("host")
        Path(host_marker).write_text("das-sieht-man-nicht", encoding="utf-8")
        self.addCleanup(lambda: Path(host_marker).unlink(missing_ok=True))

        result = self.run_sandboxed(
            self.project,
            "if [ -f '%s' ]; then echo HOST_SHM_VISIBLE; "
            "else echo HOST_SHM_HIDDEN; fi; "
            "echo inhalt > /dev/shm/b5-probe && echo SHM_WRITABLE "
            "|| echo SHM_DENIED" % shlex.quote(host_marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOST_SHM_HIDDEN", result.stdout)
        self.assertIn("SHM_WRITABLE", result.stdout)
        self.assertIn("das-sieht-man-nicht", Path(host_marker).read_text(encoding="utf-8"))

    def test_sandbox_shm_content_is_invisible_to_the_host(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        marker = self.unique_shm_marker("innen")

        result = self.run_sandboxed(
            self.project,
            "echo aus-der-sandbox > %s 2>/dev/null && echo INNEN_OK "
            "|| echo INNEN_GESCHEITERT" % shlex.quote(marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INNEN_OK", result.stdout)
        self.assertFalse(Path(marker).exists())

class ShmProjectRunTest(B5Fixture):
    """Zu M3b (Reviewrunde 1): Echter Lauf mit Projekt unter /dev/shm.

    Genau der Defekt aus Umsetzungsrunde 1: Stand das tmpfs hinter den
    Bindungen, überschattete es die Projekt-Bindung. Sichtbar wird der
    Unterschied außerhalb: Die Projekt-Datei muss nach dem Lauf im
    Testprozess existieren, die Schreibmarke im /dev/shm-Wurzelbereich
    darf nicht auftauchen.
    """

    def test_project_under_shm_is_writable_and_host_shm_stays_isolated(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        project = self.shm_project()
        self.cleanup_state_dir(project)
        host_marker = self.unique_shm_marker("host-run")

        result = self.run_sandboxed(
            project,
            "echo in-der-sandbox-geschrieben > inside.txt && echo INSIDE_OK "
            "|| echo INSIDE_FAILED; "
            "echo geheim > %s 2>/dev/null && echo MARKER_WRITTEN "
            "|| echo MARKER_DENIED" % shlex.quote(host_marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSIDE_OK", result.stdout)
        # Die Projekt-Bindung hebt die /dev/shm-Überschattung auf: Die
        # geschriebene Datei ist nach dem Lauf im Testprozess sichtbar.
        self.assertTrue((project / "inside.txt").exists())
        self.assertEqual(
            (project / "inside.txt").read_text(encoding="utf-8"),
            "in-der-sandbox-geschrieben\n",
        )
        # Schreibmarke in einer NICHT erlaubten Stelle unter /dev/shm:
        # frisches tmpfs, nach dem Lauf für den Testprozess unsichtbar.
        self.assertIn("MARKER_WRITTEN", result.stdout)
        self.assertFalse(Path(host_marker).exists())


class BandLimitTest(B5Fixture):
    """Zu M4 (Reviewrunde 1): Ausweichen greift schon im Band 85..100.

    Der Root ist so konstruiert, dass der nicht-ausgewichene Zustandspfad
    über der neuen Begrenzung (84) liegt, aber unter der alten 100er-Grenze
    bliebe: genau dort darf die Implementierung nicht nach der alten Regel
    hängen bleiben.
    """

    def test_state_dir_falls_back_in_the_85_to_100_character_band(self):
        root = "/tmp/opencode/b5-band-" + "z" * 60
        self.override_root_env(root)
        digest = self.digest_of(self.project)
        band_pfad = os.path.join(os.path.abspath(root), "proj-" + digest)
        self.assertGreaterEqual(
            len(band_pfad), 85,
            "Vorbedingung: Pfad muss oberhalb der 84er-Begrenzung liegen",
        )
        self.assertLessEqual(
            len(band_pfad), 100,
            "Vorbedingung: Pfad muss im Band 85..100 liegen",
        )

        self.cleanup_state_dir(self.project)
        result = self.sandbox.state_dir(self.project)

        self.assertTrue(result.startswith(FALLBACK_ROOT + os.sep), result)
        self.assertLess(len(result), 96, result)
        self.assertIn(digest, result)


class StateDirTest(B5Fixture):
    """Zu 2 und 3: Zustandsort bleibt kurz, Rückfall und status()-Konsistenz."""

    def test_state_dir_stays_under_the_limit_for_a_very_long_project_name(self):
        project = self.long_project()
        self.assertGreater(
            len(os.path.basename(os.path.realpath(project))), 100,
            "Vorbedingung: Projektname muss sehr lang sein",
        )

        self.override_root_env(None)
        result = self.sandbox.state_dir(project)
        self.assertLess(len(result), LIMIT, result)

        self.override_root_env("/tmp/opencode")
        result = self.sandbox.state_dir(project)
        self.assertLess(len(result), LIMIT, result)

    def test_state_dir_falls_back_to_the_short_tmpfs_root_with_the_same_digest(self):
        project = self.long_project()
        long_root = "/tmp/opencode/" + "zu-lang-" + "y" * 80
        self.override_root_env(long_root)

        self.cleanup_state_dir(project)
        result = self.sandbox.state_dir(project)

        self.assertTrue(result.startswith(FALLBACK_ROOT + os.sep), result)
        self.assertLess(len(result), LIMIT, result)
        expected_digest = self.digest_of(project)
        tail = result[len(FALLBACK_ROOT) + 1:]
        self.assertTrue(
            tail.endswith("-" + expected_digest) or expected_digest in tail,
            result + " fehlt Projekt-Digest " + expected_digest,
        )

    def test_state_dir_honors_a_short_custom_root(self):
        self.override_root_env("/tmp/opencode/kurze-wald")

        self.cleanup_state_dir(self.project)
        result = self.sandbox.state_dir(self.project)

        self.assertTrue(result.startswith("/tmp/opencode/kurze-wald" + os.sep), result)
        self.assertIn(self.digest_of(self.project), result)

    def test_status_reports_the_same_state_dir_as_state_dir(self):
        for value in (None, "/tmp/opencode", "/tmp/opencode/" + "y" * 80):
            with self.subTest(root=value):
                self.override_root_env(value)
                project = self.long_project()
                self.cleanup_state_dir(project)
                status = self.sandbox.status(project)
                self.assertEqual(status["state_dir"], self.sandbox.state_dir(project))
                self.assertLess(len(status["state_dir"]), LIMIT)

    def test_write_dirs_keep_workflow_directory_in_fallback(self):
        self.override_root_env("/tmp/opencode/" + "y" * 80)
        project = self.long_project()

        self.cleanup_state_dir(project)
        status = self.sandbox.status(project)

        self.assertTrue(status["enabled"])
        for expected in (
            os.path.realpath(project),
            "/tmp/opencode",
            status["state_dir"],
        ):
            self.assertIn(expected, status["write_dirs"], expected)


class SetEnvTest(B5Fixture):
    """Zu 4: XDG- und TMPDIR-Belegungen bleiben kurz und zeigen in state_dir."""

    def test_setenv_paths_stay_under_the_limit(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.override_root_env("/tmp/opencode/" + "y" * 80)
        project = self.long_project()

        self.cleanup_state_dir(project)
        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        state_dir = self.sandbox.state_dir(project)

        setenv = collect_setenv(argv)
        for variable in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "TMPDIR"):
            with self.subTest(variable=variable):
                self.assertIn(variable, setenv, "setenv fehlt: " + variable)
                self.assertLess(len(setenv[variable]), LIMIT, setenv[variable])
                self.assertTrue(
                    setenv[variable].startswith(state_dir + os.sep),
                    setenv[variable] + " zeigt nicht in den Zustandsort",
                )


    def test_setenv_from_band_root_stays_below_the_af_unix_limit(self):
        """M4: Auch vom Band-Root (85..100) bleibt TMPDIR samt angenommenem
        tmux-Socket unter der AF_UNIX-Grenze von 108 Zeichen."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        root = "/tmp/opencode/b5-band-" + "z" * 60
        self.override_root_env(root)
        project = self.long_project()
        self.cleanup_state_dir(project)

        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        state_dir = self.sandbox.state_dir(project)
        self.assertTrue(state_dir.startswith(FALLBACK_ROOT + os.sep), state_dir)

        setenv = collect_setenv(argv)
        tmpdir = setenv["TMPDIR"]
        tmux_socket = tmpdir + "/tmux-1000/default"
        self.assertEqual(tmpdir, state_dir + os.sep + "tmp", tmpdir)
        self.assertLess(len(tmpdir), 108, tmpdir)
        self.assertLess(len(tmux_socket), 108, tmux_socket)

if __name__ == "__main__":
    unittest.main()
