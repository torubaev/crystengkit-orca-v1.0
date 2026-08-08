import ast
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install" / "install.py"
CHECKER_LAUNCHER_PATH = ROOT / "packaging" / "windows" / "run_install_checker.cmd"
INNO_SETUP_PATH = ROOT / "packaging" / "windows" / "CrystEngKit_ORCA.iss"
INSTALLER_BUILD_PATH = ROOT / "packaging" / "windows" / "build_installer.ps1"


def load_installer_functions(*names):
    source = INSTALLER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(INSTALLER_PATH), "exec"), namespace)
    return namespace


class InstallationRootTests(unittest.TestCase):
    def test_packaged_root_is_recognized_without_a_command_line_argument(self):
        functions = load_installer_functions("is_project_root")
        with mock.patch.dict(functions, {"EXPECTED_PROJECT_ITEMS": [Path("tools/app.py")]}):
            with mock.patch.object(Path, "exists", return_value=True):
                self.assertTrue(functions["is_project_root"](Path("C:/CrystEngKit ORCA")))

    def test_main_accepts_valid_default_root_without_opening_folder_browser(self):
        source = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn("if is_project_root(default_project_root):", source)
        self.assertNotIn("if project_root_arg and is_project_root(default_project_root):", source)

    def test_windows_launcher_always_passes_installed_project_root(self):
        launcher = CHECKER_LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertIn('set "PROJECT_ROOT=%%~fI"', launcher)
        self.assertIn('set "CHECKER_ARGS= "--project-root=%PROJECT_ROOT%""', launcher)

    def test_windows_installer_uses_user_writable_installation_root(self):
        setup = INNO_SETUP_PATH.read_text(encoding="utf-8")
        self.assertIn("DefaultDirName={localappdata}\\Programs\\CrystEngKit_ORCA", setup)
        self.assertIn("PrivilegesRequired=lowest", setup)
        self.assertNotIn("DefaultDirName={autopf}", setup)

    def test_installer_build_uses_only_git_tracked_release_source(self):
        build = INSTALLER_BUILD_PATH.read_text(encoding="utf-8")
        self.assertIn("git -C $repoRoot archive", build)
        self.assertIn("tmp\\codex_work\\windows_installer_source", build)
        self.assertIn('"/DSourceRoot=$stageRoot"', build)


if __name__ == "__main__":
    unittest.main()
