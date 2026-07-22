import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from TD_DFT.td_dft_module import (  # noqa: E402
    build_gaussian_broadened_spectrum,
    build_tddft_block,
    classify_orca_tddft_failure_text,
    estimate_tddft_expansion_vectors,
    migrate_legacy_tddft_settings,
    tddft_memory_risk_warnings,
    validate_tddft_settings,
    parse_orca_tddft_output,
    suggest_wavelength_range_for_states,
    suggested_tddft_export_path,
    auto_detect_multiwfn_path,
    detect_associated_files,
)
from TD_DFT.td_dft_multiwfn_runner import MultiwfnTDDFTRunner  # noqa: E402
from TD_DFT.td_dft_cube_viewer import read_cube  # noqa: E402
import TD_DFT.td_dft_module as td_dft_module  # noqa: E402


class TDDFTModuleTests(unittest.TestCase):
    def test_embedded_module_tolerates_cached_legacy_app_identity(self):
        original = td_dft_module._app_identity
        try:
            td_dft_module._app_identity = SimpleNamespace()
            td_dft_module.install_dev_reload_shortcut(None, Path("td_dft_module.py"))
        finally:
            td_dft_module._app_identity = original

    def test_export_filename_suggestion_uses_loaded_output_without_renaming_it(self):
        source = Path("calc") / "molecule_CAM-B3LYP_def2-TZVP_CHCl3_TDA.out"
        self.assertEqual(
            suggested_tddft_export_path(str(source), "states", ".csv").name,
            "molecule_CAM-B3LYP_def2-TZVP_CHCl3_TDA_states.csv",
        )
        self.assertEqual(
            suggested_tddft_export_path(str(source), "NTO pair", "png").name,
            "molecule_CAM-B3LYP_def2-TZVP_CHCl3_TDA_nto-pair.png",
        )

    def test_block_uses_selected_manifold_and_tda(self):
        block = build_tddft_block({"nroots": 12, "root": 1, "td_method": "TDA", "manifold": "Both"})
        self.assertIn("NRoots 12", block)
        self.assertIn("TDA true", block)
        self.assertIn("MaxDim 10", block)
        self.assertIn("MaxIter 300", block)
        self.assertIn("Triplets true", block)
        self.assertNotIn("Singlets", block)

    def test_default_maxdim_is_safe_small_multiplier(self):
        block = build_tddft_block({})
        self.assertIn("NRoots 10", block)
        self.assertIn("MaxDim 10", block)
        self.assertIn("DoNTO true", block)
        self.assertIn("NTOThresh 1e-4", block)
        self.assertNotIn("NTOStates", block)
        self.assertNotIn("MaxCore", block)

    def test_nto_generation_cannot_be_disabled_by_legacy_settings(self):
        settings = validate_tddft_settings({"print_ntos": False})
        self.assertTrue(settings["print_ntos"])
        self.assertIn("DoNTO true", build_tddft_block(settings))

    def test_maxdim_is_independent_of_nroots(self):
        settings = validate_tddft_settings({"nroots": 10, "maxdim": 5})
        self.assertEqual(settings["maxdim"], 5)
        settings = validate_tddft_settings({"nroots": 20, "root": 1, "maxdim": 3})
        self.assertEqual(settings["maxdim"], 3)
        settings = validate_tddft_settings({"nroots": 20, "root": 1, "maxdim": 1})
        self.assertEqual(settings["maxdim"], 1)

    def test_invalid_tddft_solver_values_are_rejected(self):
        for settings in (
            {"maxdim": 0},
            {"maxdim": -1},
            {"nroots": 0},
            {"nroots": 2, "root": 3},
            {"maxiter": 0},
        ):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    validate_tddft_settings(settings)

    def test_expansion_estimate_and_warnings(self):
        self.assertEqual(estimate_tddft_expansion_vectors(10, 5), 50)
        self.assertEqual(estimate_tddft_expansion_vectors(10, 120), 1200)
        self.assertFalse(tddft_memory_risk_warnings({"nroots": 10, "maxdim": 5}))
        warning = "\n".join(tddft_memory_risk_warnings({"nroots": 10, "maxdim": 120}))
        self.assertIn("approximately 1200 vectors", warning)
        self.assertIn("MaxCore", warning)
        warning = "\n".join(tddft_memory_risk_warnings({"nroots": 20, "maxdim": 16}))
        self.assertIn("Large TD-DFT expansion space", warning)

    def test_legacy_maxdim_default_migrates(self):
        migrated, warnings = migrate_legacy_tddft_settings({"maxdim": 120, "nroots": 10})
        self.assertEqual(migrated["maxdim"], 10)
        self.assertTrue(warnings)
        explicit, warnings = migrate_legacy_tddft_settings({"maxdim": 96, "nroots": 10})
        self.assertEqual(explicit["maxdim"], 96)
        self.assertFalse(warnings)

    def test_tddft_memory_failure_classifier(self):
        result = classify_orca_tddft_failure_text(
            "ORCA finished by error termination in CIS\n"
            "Error (BatchOrganizer): Not a single batch is possible with the present MaxCore\n"
            "aborting the run\n"
        )
        self.assertEqual(result["category"], "tddft_memory")
        self.assertEqual(result["module"], "CIS/TD-DFT")
        self.assertIn("Reduce MaxDim", result["recommendations"][0])

    def test_singlet_only_block_omits_rejected_singlets_keyword(self):
        block = build_tddft_block({"nroots": 12, "root": 1, "td_method": "TDDFT", "manifold": "Singlets"})
        self.assertNotIn("Singlets", block)
        self.assertNotIn("Triplets", block)

    def test_custom_solver_limits_are_emitted(self):
        block = build_tddft_block({"nroots": 8, "root": 1, "maxdim": 96, "maxiter": 250})
        self.assertIn("MaxDim 96", block)
        self.assertIn("MaxIter 250", block)

    def test_excited_state_optimization_emits_verified_target_root(self):
        block = build_tddft_block({
            "vertical_excitation": True,
            "excited_state_optimization": True,
            "root": 2,
            "nroots": 8,
            "manifold": "Both",
            "target_manifold": "Triplet",
        })
        self.assertIn("%tddft", block)
        self.assertIn("IRoot 2", block)
        self.assertIn("IRootMult triplet", block)
        self.assertNotIn("FollowIRoot", block)

    def test_excited_state_optimization_does_not_require_standalone_vertical_mode(self):
        block = build_tddft_block({
            "vertical_excitation": False,
            "excited_state_optimization": True,
            "root": 1,
            "nroots": 6,
        })
        self.assertIn("IRoot 1", block)

    def test_saved_all_true_workflow_is_normalized(self):
        settings = validate_tddft_settings({
            "vertical_excitation": True,
            "excited_state_optimization": True,
            "excited_state_frequencies": True,
        })
        self.assertFalse(settings["vertical_excitation"])
        self.assertTrue(settings["excited_state_optimization"])
        self.assertTrue(settings["excited_state_frequencies"])

    def test_at_least_one_calculation_is_required(self):
        settings = validate_tddft_settings({"vertical_excitation": False})
        self.assertTrue(settings["vertical_excitation"])
        self.assertFalse(settings["excited_state_optimization"])
        self.assertFalse(settings["excited_state_frequencies"])

    def test_frequency_dependency_is_validated(self):
        settings = validate_tddft_settings({
            "vertical_excitation": True,
            "excited_state_optimization": False,
            "excited_state_frequencies": True,
        })
        self.assertFalse(settings["vertical_excitation"])
        self.assertTrue(settings["excited_state_optimization"])
        self.assertTrue(settings["excited_state_frequencies"])

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

    def test_parse_orca6_transition_label_absorption_table(self):
        sample = """STATE  3:  E=   0.269045 au      7.321 eV    59048.6 cm**-1 <S**2> =   0.000000 Mult 1

ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
----------------------------------------------------------------------------------------------------
     Transition      Energy     Energy  Wavelength fosc(D2)      D2        DX        DY        DZ
                      (eV)      (cm-1)    (nm)                 (au**2)    (au)      (au)      (au)
----------------------------------------------------------------------------------------------------
  0-1A  ->  3-1A    7.321087   59048.6   169.4   0.591611955   3.29840   0.00128  -0.00180   1.81615
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.out"
            path.write_text(sample, encoding="utf-8")
            states = parse_orca_tddft_output(str(path))
        self.assertEqual(states[0]["state"], "S3")
        self.assertAlmostEqual(states[0]["energy_ev"], 7.321087)
        self.assertAlmostEqual(states[0]["wavelength_nm"], 169.4)
        self.assertAlmostEqual(states[0]["oscillator_strength"], 0.591611955)

    def test_broadened_spectrum_respects_point_count(self):
        states = [{"energy_ev": 2.5, "wavelength_nm": 495.9, "oscillator_strength": 0.4}]
        spectrum = build_gaussian_broadened_spectrum(states, points=101)
        self.assertEqual(len(spectrum), 101)
        self.assertGreater(max(y for _, y in spectrum), 0.38)

    def test_wavelength_range_expands_to_show_bright_uv_peaks(self):
        states = [
            {"energy_ev": 7.32, "wavelength_nm": 169.4, "oscillator_strength": 0.59},
            {"energy_ev": 5.51, "wavelength_nm": 224.9, "oscillator_strength": 1e-7},
        ]
        low, high = suggest_wavelength_range_for_states(states, 200.0, 800.0)
        self.assertLess(low, 170.0)
        self.assertEqual(high, 800.0)

    def test_multiwfn_autodetect_accepts_saved_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / ("Multiwfn.exe" if sys.platform.startswith("win") else "Multiwfn")
            exe.write_text("", encoding="utf-8")
            self.assertEqual(Path(auto_detect_multiwfn_path(directory)).resolve(), exe.resolve())

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

    def test_nto_workflow_exports_dominant_hole_electron_pair(self):
        class FakeRunner(MultiwfnTDDFTRunner):
            def __init__(self, workdir):
                super().__init__("Multiwfn", workdir)
                self.calls = []

            def _run_batch(self, wavefunction, run_dir, answers, timeout):
                answers = tuple(answers)
                self.calls.append((Path(wavefunction), answers))
                if answers[:2] == (18, 6):
                    Path(answers[5]).write_text("NTO molden\n" * 20, encoding="utf-8")
                    return "Orbitals from 1 to 12 are occupied\n"
                (Path(run_dir) / "orb000012.cub").write_text("hole", encoding="utf-8")
                (Path(run_dir) / "orb000013.cub").write_text("electron", encoding="utf-8")
                return "exported"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "job.out"; output.write_text("states", encoding="utf-8")
            wavefunction = root / "job.molden.input"; wavefunction.write_text("wf", encoding="utf-8")
            runner = FakeRunner(directory)
            hole, electron, log = runner._generate_nto_cubes(output, wavefunction, 2, root, 10)
            self.assertEqual(hole.name, "NTO_hole_00002.cub")
            self.assertEqual(electron.name, "NTO_electron_00002.cub")
            self.assertTrue(hole.is_file() and electron.is_file() and log.is_file())
            self.assertEqual(runner.calls[1][1][2], "12,13")

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
