"""Tests für die Harness-Auswahl im Setup (AP04).

Der Setup muss bei der ersten Installation einen Harness anbieten, die Auswahl
speichern und die passenden Abhängigkeiten prüfen. Die Tests arbeiten in
temporären Zielordnern und führen keine Paketmanager oder Netzbefehle aus.
"""
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "scripts" / "setup-vibe.py"

setup = None
harness = None


def setUpModule():
    global setup, harness
    loader = importlib.machinery.SourceFileLoader("setup_vibe_ap04", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module

    import sys
    sys.path.insert(0, str(REPO / "bin"))
    import vibe_harness
    harness = vibe_harness


def fake_which(name):
    return "/tmp/" + name


def platform_info():
    return {
        "os": "linux",
        "distro": "ubuntu",
        "family": "debian",
        "manager": "apt-get",
        "container": True,
        "immutable": False,
        "wsl": False,
        "wsl_available": False,
        "npm_available": True,
        "label": "Test-Container",
        "release": {},
    }


class SetupHarnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target = self.root / "vibe"
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_setup(self, *extra, which=fake_which):
        # B17: Der Setup erhält eine bereinigte Umgebung ohne VIBE_*-Variablen
        # und explizite Temp-Pfade. Ein geerbtes Produktiv-VIBE_* darf den
        # Testlauf nicht mehr auf die echte Installation lenken.
        output = io.StringIO()
        environ = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}
        code = setup.main(
            ["--vibe", str(self.target),
             "--install", str(self.target / "_toolchain"),
             "--logs", str(self.target / "_logs"),
             "--yes", "--skip-deps", "--no-launcher",
             "--no-register", *extra],
            output=lambda text="": output.write(str(text) + "\n"),
            which=which,
            platform_info=platform_info(),
            home=self.home,
            kit=REPO,
            interactive=False,
            is_root=True,
            has_sudo=False,
            environ=environ,
        )
        return code, output.getvalue()

    def test_dry_run_explains_pi_and_its_install_command(self):
        code, output = self.run_setup("--dry-run", "--harness", "pi")

        self.assertEqual(code, 0, output)
        self.assertIn("Harness: pi", output)
        self.assertIn("@earendil-works/pi-coding-agent", output)
        self.assertFalse((self.target / "_toolchain").exists())

    def test_first_install_stores_the_chosen_harness(self):
        code, output = self.run_setup("--harness", "pi")

        self.assertEqual(code, 0, output)
        selection = self.target / "_toolchain" / "harness.json"
        self.assertTrue(selection.is_file(), output)
        self.assertEqual(harness.read_selection(self.target / "_toolchain", environ={}), "pi")

    def test_update_without_a_new_choice_keeps_the_stored_harness(self):
        first, output = self.run_setup("--harness", "pi")
        self.assertEqual(first, 0, output)

        second, output = self.run_setup("--update")

        self.assertEqual(second, 0, output)
        self.assertEqual(harness.read_selection(self.target / "_toolchain", environ={}), "pi")

    def test_pi_is_the_required_dependency_only_for_the_pi_harness(self):
        report = setup.dependency_report(platform_info(), which=lambda name: None, harness="pi")
        required = {item["name"] for item in report if item["required"]}

        self.assertIn("pi", required)
        self.assertIn("node", required)
        self.assertNotIn("opencode", required)

    def test_opencode_stays_required_for_the_opencode_harness(self):
        report = setup.dependency_report(platform_info(), which=lambda name: None, harness="opencode")
        required = {item["name"] for item in report if item["required"]}

        self.assertIn("opencode", required)
        self.assertNotIn("pi", required)

    def test_pi_install_command_is_an_argument_list(self):
        commands = setup.install_commands(
            platform_info(), ["pi"], prefix=[]
        )

        self.assertEqual(
            commands,
            [["npm", "install", "-g", "--ignore-scripts", "@earendil-works/pi-coding-agent"]],
        )


if __name__ == "__main__":
    unittest.main()
