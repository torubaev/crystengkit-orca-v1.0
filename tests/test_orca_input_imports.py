from pathlib import Path
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("orca_input", MODULE_PATH)
orca_input = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["orca_input"] = orca_input
spec.loader.exec_module(orca_input)


class ImportHelperTests(unittest.TestCase):
    class _Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    def test_new_extensions_are_case_insensitive(self):
        for ext in [".mol", ".SDF", ".sd", ".CML", ".cdxml", ".CDX", ".ct", ".GJF", ".com", ".GAU", ".gjc"]:
            self.assertTrue(orca_input.structure_input_format("molecule" + ext))
        with self.assertRaises(ValueError):
            orca_input.structure_input_format("generic.inp2")

    def test_generic_inp_is_not_gaussian(self):
        self.assertEqual(orca_input.structure_input_format("job.inp"), "ORCA input")

    def test_valid_and_invalid_xyz_output(self):
        xyz = "2\nwater fragment\nO 0 0 0\nH 0 0 1\n"
        structure = orca_input.validate_xyz_text(xyz)
        self.assertEqual(len(structure.atoms), 2)
        with self.assertRaises(ValueError):
            orca_input.validate_xyz_text("2\nbad\nO 0 0 nan\nH 0 0 1\n")
        with self.assertRaises(ValueError):
            orca_input.validate_xyz_text("3\nbad\nO 0 0 0\n")

    @unittest.skipIf(orca_input.gemmi is None, "Gemmi is not installed")
    def test_cif_symmetry_completes_inversion_generated_molecule(self):
        cif = """data_inversion
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P -1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .45 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inversion.cif"
            path.write_text(cif, encoding="utf-8")
            structure = orca_input.StructureParser.parse(str(path))
        self.assertEqual([atom[0] for atom in structure.atoms], ["C", "C"])
        self.assertAlmostEqual(orca_input.distance(*structure.atoms), 1.0, places=6)

    @unittest.skipIf(orca_input.gemmi is None, "Gemmi is not installed")
    def test_cif_without_generated_symmetry_keeps_existing_coordinates(self):
        cif = """data_boundary
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P 1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .98 .5 .5
C2 C .08 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "boundary.cif"
            path.write_text(cif, encoding="utf-8")
            structure = orca_input.StructureParser.parse(str(path))
        self.assertEqual(len(structure.atoms), 2)
        self.assertAlmostEqual(orca_input.distance(*structure.atoms), 9.0, places=6)

    def test_cif_fallback_does_not_silently_return_asymmetric_unit(self):
        cif = """data_half
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
loop_
_space_group_symop_operation_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C .45 .5 .5
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "half.cif"
            path.write_text(cif, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Gemmi"):
                orca_input.StructureParser.parse_cif_fallback(str(path))

    def test_2d_detection(self):
        flat = orca_input.Structure([("C", 0.0, 0.0, 0.0), ("O", 1.2, 0.0, 0.0)])
        spatial = orca_input.Structure([("C", 0.0, 0.0, 0.0), ("O", 1.2, 0.0, 0.2)])
        self.assertTrue(orca_input.looks_like_2d_structure(flat))
        self.assertFalse(orca_input.looks_like_2d_structure(spatial))

    def test_gaussian_cartesian_charge_multiplicity_freeze_and_atomic_numbers(self):
        text = """%chk=test.chk
#p b3lyp/6-31g(d)

Title

-1 2
6 0 0.000000 0.000000 0.000000
O 0 1.200000 0.000000 0.000000
H(label) 0.000000 0.000000 1.000000

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertEqual(section.charge, -1)
        self.assertEqual(section.multiplicity, 2)
        self.assertEqual([atom[0] for atom in section.atoms], ["C", "O", "H"])
        self.assertTrue(any("freeze-code" in warning for warning in section.warnings))

    def test_gaussian_bohr_to_angstrom(self):
        text = """#p hf/sto-3g units=bohr

Bohr title

0 1
H 0 0 1.0

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertEqual(section.units, "bohr")
        self.assertAlmostEqual(section.atoms[0][3], orca_input.BOHR_TO_ANGSTROM)

    def test_gaussian_link1_selection_metadata_and_checkpoint_rejection(self):
        text = """#p hf/sto-3g

First

0 1
H 0 0 0

--Link1--
#p hf/sto-3g geom=check

Second

0 1

"""
        sections = orca_input.parse_gaussian_input_text(text)
        geometry = orca_input.gaussian_sections_with_geometry(sections)
        self.assertEqual([section.index for section in geometry], [1])
        self.assertTrue(sections[1].checkpoint_dependent)

    def test_gaussian_zmatrix_requires_openbabel(self):
        text = """#p hf/sto-3g

Zmat

0 1
O
H 1 0.96
H 1 0.96 2 104.5

"""
        section = orca_input.parse_gaussian_input_text(text)[0]
        self.assertTrue(section.requires_openbabel)
        self.assertEqual(section.coordinate_type, "Z-matrix")

    def test_sdf_record_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sdf = Path(tmpdir) / "multi.sdf"
            sdf.write_text(
                "one\n  test\n\n  2  1  0  0  0  0            999 V2000\n$$$$\n"
                "two\n  test\n\n  3  2  0  0  0  0            999 V2000\n$$$$\n",
                encoding="utf-8",
            )
            records = orca_input.count_sdf_records(str(sdf))
        self.assertEqual([record["atom_count"] for record in records], [2, 3])

    def test_native_mol_to_xyz(self):
        mol = """Water 3D
  CrystEngKit

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.7586    0.0000    0.5043 H   0  0  0  0  0  0  0  0  0  0  0  0
   -0.7586    0.0000    0.5043 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
"""
        atoms, title = orca_input.parse_mol_v2000_atoms(mol, "MOL")
        self.assertEqual(title, "Water 3D")
        self.assertEqual([atom[0] for atom in atoms], ["O", "H", "H"])
        self.assertAlmostEqual(atoms[1][3], 0.5043)

    def test_native_sdf_selects_record_to_xyz(self):
        sdf = """First
  CrystEngKit

  1  0  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
Second
  CrystEngKit

  2  1  0  0  0  0            999 V2000
    0.0000    0.0000    0.1000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.2000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
M  END
$$$$
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "multi.sdf"
            path.write_text(sdf, encoding="utf-8")
            xyz, title, logs = orca_input.mol_sdf_to_xyz_text(str(path), record_index=2)
        structure = orca_input.validate_xyz_text(xyz, "SDF")
        self.assertEqual(title, "Second")
        self.assertEqual([atom[0] for atom in structure.atoms], ["N", "H"])
        self.assertTrue(any("Selected SDF record: 2" in line for line in logs))

    def test_openbabel_validation_failure(self):
        ok, reason = orca_input.validate_openbabel_executable(str(ROOT / "missing_obabel"))
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

    def test_show_active_run_input_prefers_running_job_input(self):
        class DummyText:
            def __init__(self):
                self.content = ""

            def delete(self, *_args, **_kwargs):
                self.content = ""

            def insert(self, *_args, **_kwargs):
                self.content = _args[1] if len(_args) > 1 else ""

        class DummyStatus:
            def __init__(self):
                self.messages = []

            def configure(self, **kwargs):
                self.messages.append(kwargs)

        app = orca_input.App.__new__(orca_input.App)
        app.run_process = type("Proc", (), {"poll": lambda self: None})()
        app.current_input_path = None
        app.preview_text = DummyText()
        app.status = DummyStatus()
        app.output_mode = "monitor"
        app.output_buffers = {"preview": "", "monitor": ""}
        app.output_wraps = {"preview": "none", "monitor": "none"}
        app.preview_mode_button = None
        app.monitor_mode_button = None
        app._show_output_mode = lambda mode: setattr(app, "output_mode", mode)
        app.preview = lambda: setattr(app, "preview_called", True)
        app.preview_called = False

        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "running.inp"
            inp_path.write_text("! Running input\n", encoding="utf-8")
            app.current_input_path = str(inp_path)
            app._show_running_job_input_preview()

        self.assertFalse(getattr(app, "preview_called", False))
        self.assertEqual(app.preview_text.content, "! Running input\n")
        self.assertEqual(app.output_mode, "preview")

    def test_orca_uses_synchronized_tddft_block_exactly_once(self):
        structure = orca_input.Structure([("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.74)])
        data = {
            "functional": "B3LYP", "basis": "def2-SVP", "dispersion": "", "ri_jcosx": False,
            "tight_scf": True, "grid": "DefGrid2", "job_opt": False, "job_freq": False,
            "job_density": False, "job_esp": False, "job_sp": False, "job_tddft": True,
            "job_nmr": False, "print_mos": False, "extra": "", "charge": 0, "multiplicity": 1,
            "freeze_all": False, "freeze_heavy": False,
            "tddft_block": "%tddft\n  NRoots 7\n  TDA true\nend",
        }
        text = orca_input.generate_orca(data, structure, None)
        self.assertEqual(text.lower().count("%tddft"), 1)
        self.assertIn("NRoots 7", text)

        data["tddft_block"] = "%tddft\n  NRoots 11\n  TDA false\nend"
        updated = orca_input.generate_orca(data, structure, None)
        self.assertEqual(updated.lower().count("%tddft"), 1)
        self.assertNotIn("NRoots 7", updated)
        self.assertIn("NRoots 11", updated)

        data["tddft_settings"] = {"excited_state_optimization": True, "excited_state_frequencies": True}
        excited_state_job = orca_input.generate_orca(data, structure, None)
        self.assertIn(" Opt", excited_state_job.splitlines()[0])
        self.assertIn(" Freq", excited_state_job.splitlines()[0])

    def test_tddft_rpa_convergence_failure_is_reported_specifically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "failed.out"
            out_path.write_text(
                "ORCA finished by error termination in CIS\n"
                "[file orca_cis/cis_solve_rpa.cpp, line 248]: "
                "RPA/TD-DFT did not converge! You may try raising the number of iterations.\n",
                encoding="utf-8",
            )
            ok, reason = orca_input.validate_orca_output_file(str(out_path))
        self.assertFalse(ok)
        self.assertIn("TD-DFT/RPA did not converge", reason)

    def test_ai_progress_prompt_redacts_sensitive_details_and_requests_short_answer(self):
        output = (
            "INPUT FILE C:\\Users\\chemist\\secret\\private_job.inp\n"
            "C 0.000 1.000 2.000\nH 0.000 0.000 1.000\n"
            "SCF ITERATION 12 ENERGY -100.0\napi_key=do-not-send\n"
        )
        prompt = orca_input.build_orca_progress_prompt(output)
        self.assertTrue(prompt.startswith("ORCA Job progress report."))
        self.assertNotIn(r"C:\Users\chemist", prompt)
        self.assertNotIn("private_job", prompt)
        self.assertNotIn("do-not-send", prompt)
        self.assertNotIn("C 0.000 1.000 2.000", prompt)
        self.assertIn("SCF ITERATION 12", prompt)
        self.assertIn("at most 120 words", prompt)
        self.assertIn("intentionally bounded live extract", prompt)
        self.assertIn("Never describe the paste as truncated", prompt)
        self.assertTrue(prompt.endswith(orca_input.ORCA_PROMPT_END_MARKER))
        self.assertIn("never refuse analysis", prompt)
        self.assertIn("unfinished calculation", prompt)
        self.assertIn("likely sequence of remaining stages", prompt)
        self.assertIn("overall remaining time", prompt)
        self.assertNotIn("INPUT_COMPLETE: YES", prompt)

    def test_chatgpt_is_default_ai_web_model(self):
        self.assertEqual(orca_input.DEFAULT_AI_WEB_MODEL, "ChatGPT")
        self.assertEqual(next(iter(orca_input.AI_WEB_MODELS)), "ChatGPT")
        self.assertEqual(orca_input.AI_WEB_MODELS["ChatGPT"], orca_input.CHATGPT_ORCA_MONITOR_URL)
        self.assertIn("g-6a5f33b7e3b881918fa604bb19250b23", orca_input.CHATGPT_ORCA_MONITOR_URL)

    def test_orca_monitor_agent_payload_contains_data_but_no_analysis_instructions(self):
        payload = orca_input.build_orca_agent_payload("SCF ITERATION 9\nC 0.0 1.0 2.0")
        self.assertTrue(payload.startswith("ORCA Job progress report."))
        self.assertTrue(payload.endswith(orca_input.ORCA_PROMPT_END_MARKER))
        self.assertIn("PAYLOAD STATUS: COMPLETE BOUNDED LIVE EXTRACT", payload)
        self.assertGreaterEqual(payload.count(orca_input.ORCA_PROMPT_END_MARKER), 2)
        self.assertIn("SCF ITERATION 9", payload)
        self.assertNotIn("C 0.0 1.0 2.0", payload)
        self.assertNotIn("Answer in at most", payload)
        self.assertNotIn("Act as an expert", payload)
        self.assertIn("COMPLETE PAYLOAD: FINAL MARKER FOLLOWS", payload)

    def test_large_agent_payload_keeps_marker_header_evidence_and_tail(self):
        source = (
            "Program Version 6.1.0\n! CAM-B3LYP def2-SVP OPT TIGHTSCF\n"
            + "routine data\n" * 12000
            + "SCF ITERATION 77 NOT CONVERGED\n" + "more routine data\n" * 12000
            + "GEOMETRY OPTIMIZATION CYCLE 12\nTOTAL RUN TIME: 1 hours 2 minutes\n"
        )
        payload = orca_input.build_orca_agent_payload(source)
        self.assertLess(len(payload), orca_input.ORCA_AGENT_OUTPUT_MAX_CHARS + 500)
        self.assertIn("Program Version 6.1.0", payload)
        self.assertIn("CAM-B3LYP def2-SVP OPT", payload)
        self.assertIn("SCF ITERATION 77 NOT CONVERGED", payload)
        self.assertIn("GEOMETRY OPTIMIZATION CYCLE 12", payload)
        self.assertIn("TOTAL RUN TIME", payload)
        self.assertIn("CRYSTENGKIT SEMANTIC EXTRACT", payload)
        self.assertNotIn("routine data", payload)
        self.assertTrue(payload.endswith(orca_input.ORCA_PROMPT_END_MARKER))

    def test_monitor_actions_have_unique_standard_icons_and_handlers(self):
        actions = orca_input.MONITOR_ACTION_BUTTONS
        self.assertEqual(len(actions), 7)
        self.assertEqual([item[1] for item in actions], [
            "Stop job", "Reconnect", "Open .out", "Open folder", "Show summary",
            "Ask AI about progress", "Clear monitor",
        ])
        self.assertEqual(len({item[0] for item in actions}), len(actions))
        for _icon, _label, handler in actions:
            self.assertTrue(callable(getattr(orca_input.App, handler)))

    def test_attached_process_recognizes_current_live_pid(self):
        executable = orca_input.process_executable_path(os.getpid())
        self.assertTrue(executable)
        attached = orca_input.AttachedOrcaProcess(os.getpid(), executable)
        self.assertIsNone(attached.poll())

    def test_active_job_state_uses_user_config_location(self):
        self.assertEqual(
            orca_input.ACTIVE_ORCA_JOB_STATE_PATH.parent,
            orca_input.startup_news_cache_dir(),
        )

    def test_completed_output_rerun_suggests_and_creates_safe_alternative(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("! B3LYP\n* xyz 0 1\n*\n", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel", return_value=True) as confirm, \
                    mock.patch.object(
                        orca_input.filedialog, "asksaveasfilename",
                        return_value=str(Path(tmpdir) / "finished_custom.inp"),
                    ) as save_as:
                selected = app._resolve_completed_job_rerun_path(str(inp_path))
            self.assertEqual(selected, str(Path(tmpdir) / "finished_custom.inp"))
            self.assertEqual(Path(selected).read_text(encoding="utf-8"), inp_path.read_text(encoding="utf-8"))
        self.assertEqual(confirm.call_args.kwargs["icon"], "warning")
        self.assertEqual(confirm.call_args.kwargs["default"], orca_input.messagebox.YES)
        self.assertIn("finished_01.inp", confirm.call_args.args[1])
        self.assertEqual(save_as.call_args.kwargs["initialfile"], "finished_01.inp")

    def test_rerun_alternative_suffix_skips_existing_job_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "job.inp"
            inp_path.write_text("input", encoding="utf-8")
            (Path(tmpdir) / "job_01.gbw").write_text("existing", encoding="utf-8")
            self.assertEqual(
                orca_input.App._suggest_rerun_input_path(str(inp_path)),
                str(Path(tmpdir) / "job_02.inp"),
            )

    def test_overwrite_choice_requires_second_attention_confirmation(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(
                orca_input.messagebox, "askyesnocancel", side_effect=[False, True]
            ) as confirm:
                self.assertEqual(app._resolve_completed_job_rerun_path(str(inp_path)), str(inp_path))
        self.assertEqual(confirm.call_count, 2)
        self.assertIn("ARE YOU SURE?", confirm.call_args_list[1].args[1])
        self.assertEqual(confirm.call_args_list[1].kwargs["default"], orca_input.messagebox.NO)

    def test_no_on_second_overwrite_warning_uses_safe_alternative(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(
                orca_input.messagebox, "askyesnocancel", side_effect=[False, False]
            ), mock.patch.object(
                orca_input.filedialog, "asksaveasfilename",
                return_value=str(Path(tmpdir) / "finished_01.inp"),
            ):
                selected = app._resolve_completed_job_rerun_path(str(inp_path))
            self.assertEqual(selected, str(Path(tmpdir) / "finished_01.inp"))
            self.assertTrue(Path(selected).is_file())

    def test_cancelling_rerun_save_as_cancels_run(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_path = Path(tmpdir) / "finished.inp"
            out_path = Path(tmpdir) / "finished.out"
            inp_path.write_text("input", encoding="utf-8")
            out_path.write_text("Program ORCA\nORCA TERMINATED NORMALLY\n", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel", return_value=True), \
                    mock.patch.object(orca_input.filedialog, "asksaveasfilename", return_value=""):
                self.assertIsNone(app._resolve_completed_job_rerun_path(str(inp_path)))

    def test_incomplete_output_does_not_prompt_before_rerun(self):
        app = object.__new__(orca_input.App)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "unfinished.out"
            out_path.write_text("Program ORCA\nSCF ITERATION 4\n", encoding="utf-8")
            inp_path = Path(tmpdir) / "unfinished.inp"
            inp_path.write_text("input", encoding="utf-8")
            with mock.patch.object(orca_input.messagebox, "askyesnocancel") as confirm:
                self.assertEqual(app._resolve_completed_job_rerun_path(str(inp_path)), str(inp_path))
                confirm.assert_not_called()

    def test_orca_completion_summary_is_minimal(self):
        self.assertEqual(
            orca_input.orca_completion_summary(r"C:\jobs\water_B3LYP_opt.out", True),
            ("water_B3LYP_opt", "Finished successfully"),
        )
        self.assertEqual(
            orca_input.orca_completion_summary("failed_job.out", False),
            ("failed_job", "Failed"),
        )

    def test_legacy_gemini_default_migrates_but_explicit_new_choice_remains(self):
        self.assertEqual(orca_input.resolve_saved_ai_web_model({"ai_web_model": "Gemini"}), "ChatGPT")
        self.assertEqual(
            orca_input.resolve_saved_ai_web_model({
                "ai_web_model": "Gemini",
                "ai_web_model_settings_version": orca_input.AI_WEB_MODEL_SETTINGS_VERSION,
            }),
            "Gemini",
        )

    def test_ai_progress_prompt_rejects_empty_output(self):
        with self.assertRaisesRegex(ValueError, "No ORCA output"):
            orca_input.build_orca_progress_prompt("  ")

    def test_ai_progress_reads_full_output_file(self):
        app = object.__new__(orca_input.App)
        app._sync_active_output_buffer = lambda: None
        app.output_buffers = {"monitor": "trimmed monitor"}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "running.out"
            path.write_text("complete output\nlast iteration", encoding="utf-8")
            app.last_output_path = str(path)
            self.assertEqual(app._orca_output_for_ai(), "complete output\nlast iteration")

    def test_tddft_maxcore_batch_failure_is_reported_specifically(self):
        text = (
            "ORCA TD-DFT CALCULATION\n"
            "ORCA finished by error termination in CIS\n"
            "Error (BatchOrganizer): Not a single batch is possible with the present MaxCore\n"
            "aborting the run\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "failed.out"
            out_path.write_text(text, encoding="utf-8")
            ok, reason = orca_input.validate_orca_output_file(str(out_path))
        self.assertFalse(ok)
        self.assertIn("TD-DFT memory failure", reason)
        classified = orca_input.classify_orca_failure_output(text)
        self.assertEqual(classified["category"], "tddft_memory")
        self.assertNotIn("configured executable is not ORCA QM", classified["message"])

    def test_builder_rejects_duplicate_tddft_fragments(self):
        app = object.__new__(orca_input.App)
        app.current_tddft_block = ""
        app.set_tddft_block("%tddft\n  NRoots 5\nend")
        self.assertEqual(app.current_tddft_block.count("%tddft"), 1)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            app.set_tddft_block("%tddft\nend\n%cis\nend")

    def test_tddft_input_save_suggestion_adds_td_dft_tag_when_block_present(self):
        app = object.__new__(orca_input.App)
        app.path_var = self._Var(r"C:\calc\water.xyz")
        app.program_var = self._Var("ORCA")
        app.freeze_all_var = self._Var(False)
        app.freeze_heavy_var = self._Var(False)
        app.job_opt_var = self._Var(False)
        app.job_tddft_var = self._Var(True)
        app.current_tddft_block = "%tddft\n  NRoots 10\nend"
        app.collect = lambda: {"functional": "B3LYP", "basis": "def2-SVP", "solvent_text": ""}

        suggested = Path(app.suggest_input_save_path()).name

        self.assertEqual(suggested, "water_B3LYP_def2-SVP_td-dft_absorption.inp")

        app.current_tddft_settings = {"td_method": "TDA", "excited_state_optimization": True}
        app.current_tddft_block = "%tddft\n  TDA true\nend"
        self.assertEqual(Path(app.suggest_input_save_path()).name, "water_B3LYP_def2-SVP_tda_excited-state-optimization.inp")

    def test_tddft_input_save_suggestion_skips_td_dft_tag_without_block(self):
        app = object.__new__(orca_input.App)
        app.path_var = self._Var(r"C:\calc\water.xyz")
        app.program_var = self._Var("ORCA")
        app.freeze_all_var = self._Var(False)
        app.freeze_heavy_var = self._Var(False)
        app.job_opt_var = self._Var(False)
        app.job_tddft_var = self._Var(True)
        app.current_tddft_block = ""
        app.collect = lambda: {"functional": "B3LYP", "basis": "def2-SVP", "solvent_text": ""}

        suggested = Path(app.suggest_input_save_path()).name

        self.assertEqual(suggested, "water_B3LYP_def2-SVP_sp.inp")

    @unittest.skipIf(os.name == "nt", "POSIX fake executable script")
    def test_openbabel_safe_command_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake = tmp / "obabel"
            log = tmp / "args.txt"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv), encoding='utf-8')\n"
                "print('1')\nprint('converted')\nprint('C 0 0 0')\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            source = tmp / "space unicode alpha.mol"
            source.write_text("fake mol", encoding="utf-8")
            xyz, logs = orca_input.run_openbabel_to_xyz(str(fake), str(source), generate_3d=True)
            self.assertIn("C 0 0 0", xyz)
            args = log.read_text(encoding="utf-8").splitlines()
            self.assertIn(str(source), args)
            self.assertIn("--gen3d", args)
            self.assertTrue(any("return code: 0" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
