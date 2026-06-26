from pathlib import Path
import importlib.util
import os
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"
spec = importlib.util.spec_from_file_location("orca_input", MODULE_PATH)
orca_input = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["orca_input"] = orca_input
spec.loader.exec_module(orca_input)


class ImportHelperTests(unittest.TestCase):
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

    def test_openbabel_validation_failure(self):
        ok, reason = orca_input.validate_openbabel_executable(str(ROOT / "missing_obabel"))
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

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
