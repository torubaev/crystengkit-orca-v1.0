import ast
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install" / "install.py"
CHECKER_LAUNCHER_PATH = ROOT / "packaging" / "windows" / "run_install_checker.cmd"
INNO_SETUP_PATH = ROOT / "packaging" / "windows" / "CrystEngKit_ORCA.iss"
INSTALLER_BUILD_PATH = ROOT / "packaging" / "windows" / "build_installer.ps1"
OPENBABEL_INSTALL_PATH = ROOT / "packaging" / "windows" / "install_openbabel.ps1"


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

    def test_windows_launcher_reuses_existing_managed_environment_first(self):
        launcher = CHECKER_LAUNCHER_PATH.read_text(encoding="utf-8")
        managed_python = '%PROJECT_ROOT%\\.venv\\Scripts\\python.exe'
        self.assertIn(f'if exist "{managed_python}"', launcher)
        self.assertIn(
            f'"{managed_python}" "%PROJECT_ROOT%\\install\\install.py" --using-venv',
            launcher,
        )
        self.assertLess(launcher.index(f'if exist "{managed_python}"'), launcher.index("where py.exe"))

    def test_windows_installer_uses_user_writable_installation_root(self):
        setup = INNO_SETUP_PATH.read_text(encoding="utf-8")
        self.assertIn("DefaultDirName={localappdata}\\Programs\\CrystEngKit_ORCA", setup)
        self.assertIn("PrivilegesRequired=lowest", setup)
        self.assertNotIn("DefaultDirName={autopf}", setup)

    def test_windows_openbabel_install_is_selected_but_optional(self):
        setup = INNO_SETUP_PATH.read_text(encoding="utf-8")
        launcher = CHECKER_LAUNCHER_PATH.read_text(encoding="utf-8")
        helper = OPENBABEL_INSTALL_PATH.read_text(encoding="utf-8")
        self.assertIn('Name: "installopenbabel"', setup)
        self.assertIn('Flags: checkedonce', setup[setup.index('Name: "installopenbabel"'):].splitlines()[0])
        self.assertIn("--install-openbabel-if-missing", setup)
        self.assertIn("--install-openbabel-if-missing", launcher)
        self.assertIn("call :install_openbabel", launcher)
        self.assertIn("OpenBabel-3.1.1-x64.exe", helper)
        self.assertIn("F3BFC11F54174F2A634F9657429886F68281F1E3355BD67E711F49CC57A57E0C", helper)
        self.assertIn("Get-FileHash", helper)

    def test_installer_build_uses_only_git_tracked_release_source(self):
        build = INSTALLER_BUILD_PATH.read_text(encoding="utf-8")
        self.assertIn("git -C $repoRoot archive", build)
        self.assertIn("tmp\\codex_work\\windows_installer_source", build)
        self.assertIn('"/DSourceRoot=$stageRoot"', build)

    def test_windows_release_outputs_are_grouped_by_version(self):
        build = INSTALLER_BUILD_PATH.read_text(encoding="utf-8")
        setup = INNO_SETUP_PATH.read_text(encoding="utf-8")
        web_build = (ROOT / "packaging" / "windows" / "build_web_installer.ps1").read_text(encoding="utf-8")
        self.assertIn('"install\\releases\\v$appVersion"', build)
        self.assertIn('"install\\releases\\v$appVersion"', web_build)
        self.assertIn("OutputDir=..\\..\\install\\releases\\v{#MyAppVersion}", setup)

    def test_checker_configures_locally_found_multiwfn(self):
        source = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertIn('default_settings["multiwfn_path"] = executable', source)
        self.assertIn("ensure_settings_file(base_dir, external_info)", source)
        self.assertIn("PATH is not required", source)

    def test_shared_locator_reads_builder_multiwfn_setting(self):
        import sys

        tools_root = str(ROOT / "tools")
        if tools_root not in sys.path:
            sys.path.insert(0, tools_root)
        from shared import multiwfn_locator

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "custom" / "renamed-multiwfn.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"test")
            settings = root / "orca_gaussian_builder_settings.json"
            settings.write_text(json.dumps({"multiwfn_path": str(executable)}), encoding="utf-8")
            with mock.patch.object(multiwfn_locator, "builder_settings_paths", return_value=[settings]):
                self.assertEqual(Path(multiwfn_locator.find_multiwfn()).resolve(), executable.resolve())

    def test_embedded_analysis_tools_receive_builder_multiwfn_path(self):
        builder = (ROOT / "tools" / "Orca_input" / "orca_input.py").read_text(encoding="utf-8")
        nci = (ROOT / "tools" / "NCI_plot" / "nci_plotter.py").read_text(encoding="utf-8")
        qtaim = (ROOT / "tools" / "qtaim-cp" / "qtaim.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(builder.count("initial_multiwfn=self.multiwfn_path_var.get().strip() or None"), 3)
        self.assertIn("initial_multiwfn: Optional[str] = None", nci)
        self.assertIn("find_multiwfn(configured_multiwfn)", nci)
        self.assertIn("initial_multiwfn: Optional[str] = None", qtaim)
        self.assertIn('find_multiwfn(initial_multiwfn or "")', qtaim)

    def test_orca_validation_does_not_require_a_fixed_filename(self):
        source = INSTALLER_PATH.read_text(encoding="utf-8")
        self.assertNotIn('candidate.name.lower() not in {"orca", "orca.exe"}', source)


if __name__ == "__main__":
    unittest.main()
