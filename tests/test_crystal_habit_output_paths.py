import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "crystal_habit" / "crystal_habit_gui.py"
SPEC = importlib.util.spec_from_file_location("crystal_habit_output_paths", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CrystalHabitOutputPathTests(unittest.TestCase):
    def test_results_folder_is_suggested_beside_external_cif(self):
        with tempfile.TemporaryDirectory() as directory:
            selected_cif = Path(directory) / "example.cif"
            selected_cif.write_text("data_example\n", encoding="utf-8")
            self.assertEqual(
                MODULE.default_results_folder(selected_cif).resolve(),
                (selected_cif.parent / "CrystalHabit_results").resolve(),
            )

    def test_repository_results_are_not_suggested_or_accepted(self):
        self.assertIsNone(MODULE.default_results_folder(ROOT / "example.cif"))
        with self.assertRaises(ValueError):
            MODULE.validate_results_folder(ROOT / "CrystalClear_inputs")

    def test_external_computational_folder_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "chosen-results"
            self.assertEqual(MODULE.validate_results_folder(external), external.resolve())


if __name__ == "__main__":
    unittest.main()
