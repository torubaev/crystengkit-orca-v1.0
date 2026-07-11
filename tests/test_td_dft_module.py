import sys
import tempfile
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1] / "tools" / "TD_DFT"
sys.path.insert(0, str(MODULE_DIR))

from td_dft_module import (  # noqa: E402
    build_gaussian_broadened_spectrum,
    build_tddft_block,
    parse_orca_tddft_output,
    detect_associated_files,
)
from td_dft_multiwfn_runner import MultiwfnTDDFTRunner  # noqa: E402
from td_dft_cube_viewer import read_cube  # noqa: E402


class TDDFTModuleTests(unittest.TestCase):
    def test_block_uses_selected_manifold_and_tda(self):
        block = build_tddft_block({"nroots": 12, "root": 1, "td_method": "TDA", "manifold": "Both"})
        self.assertIn("NRoots 12", block)
        self.assertIn("TDA true", block)
        self.assertIn("Singlets true", block)
        self.assertIn("Triplets true", block)

    def test_excited_state_optimization_emits_verified_target_root(self):
        block = build_tddft_block({
            "vertical_excitation": True,
            "excited_state_optimization": True,
            "root": 2,
            "nroots": 8,
            "manifold": "Both",
            "target_manifold": "Triplet",
        })
        self.assertIn("IRoot 2", block)
        self.assertIn("IRootMult triplet", block)

    def test_at_least_one_calculation_is_required(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            build_tddft_block({"vertical_excitation": False})

    def test_frequency_dependency_is_validated(self):
        with self.assertRaisesRegex(ValueError, "require excited-state optimization"):
            build_tddft_block({
                "vertical_excitation": True,
                "excited_state_optimization": False,
                "excited_state_frequencies": True,
            })

    def test_parse_state_absorption_and_calculated_contribution(self):
        sample = """STATE   1: E= 0.100000 au  2.7211 eV  455.64 nm
  34a -> 35a : 0.900000

ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
  1  21948.0  455.62  0.5400  0.0 0.0 0.0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.out"
            path.write_text(sample, encoding="utf-8")
            states = parse_orca_tddft_output(str(path))
        self.assertEqual(states[0]["state"], "S1")
        self.assertAlmostEqual(states[0]["oscillator_strength"], 0.54)
        transition = states[0]["transitions"][0]
        self.assertAlmostEqual(transition["contribution_percent"], 81.0)
        self.assertEqual(transition["contribution_source"], "calculated_from_coefficient_squared")

    def test_broadened_spectrum_respects_point_count(self):
        states = [{"energy_ev": 2.5, "wavelength_nm": 495.9, "oscillator_strength": 0.4}]
        spectrum = build_gaussian_broadened_spectrum(states, points=101)
        self.assertEqual(len(spectrum), 101)
        self.assertGreater(max(y for _, y in spectrum), 0.38)

    def test_associated_file_detection_prefers_matching_basename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "job.out"; output.write_text("", encoding="utf-8")
            (root / "other.wfx").write_text("other", encoding="utf-8"); expected = root / "job.wfx"; expected.write_text("match", encoding="utf-8")
            found = detect_associated_files(str(output))
        self.assertEqual(Path(found[".wfx"]).name, expected.name)

    def test_runner_reports_unsupported_without_wavefunction_and_writes_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "job.out"; output.write_text("result", encoding="utf-8")
            package = root / "TDDFT_analysis" / "S1"
            result = MultiwfnTDDFTRunner("", str(root)).generate_all_analyses(1, "", str(output), str(package))
            self.assertTrue(Path(result["metadata_path"]).is_file())
            self.assertTrue((package / "multiwfn.log").is_file())
            self.assertTrue(all(item["status"] == "Unsupported by available input" for item in result["analyses"].values()))

    def test_cube_parser_validates_grid(self):
        cube = """title
comment
 1 0.0 0.0 0.0
 2 1.0 0.0 0.0
 2 0.0 1.0 0.0
 2 0.0 0.0 1.0
 1 0.0 0.0 0.0 0.0
 0.0 0.1 0.2 0.3 0.4 0.5
 0.6 0.7
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.cube"; path.write_text(cube, encoding="utf-8"); parsed = read_cube(str(path))
        self.assertEqual(parsed.dimensions, (2, 2, 2))
        self.assertEqual(parsed.values.size, 8)


if __name__ == "__main__":
    unittest.main()
