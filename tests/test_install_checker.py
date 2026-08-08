import ast
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install" / "install.py"


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


if __name__ == "__main__":
    unittest.main()
