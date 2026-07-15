from pathlib import Path
import importlib.util
import os
import stat
import sys
import tempfile
import unittest


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

        self.assertEqual(suggested, "water_B3LYP_def2-SVP_sp_td-dft.inp")

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
