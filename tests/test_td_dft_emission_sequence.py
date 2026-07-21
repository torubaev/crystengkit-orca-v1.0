import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from TD_DFT.td_dft_emission_sequence import (  # noqa: E402
    EmissionSequenceSettings,
    advance_after_optimization,
    build_excited_state_optimization_input,
    build_vertical_emission_input,
    finalize_after_vertical,
    prepare_emission_sequence,
)


ABS_OUT = """PROGRAM ORCA
STATE   1: E= 0.100000 au  2.5000 eV  495.94 nm

ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
  1  20163.9  495.94  0.4000  0.0 0.0 0.0

ORCA TERMINATED NORMALLY
"""

SOURCE_INP = """! CAM-B3LYP def2-TZVP TightSCF SP

%maxcore 8000

%pal
  nprocs 1
end

%cpcm
  smd true
  SMDsolvent "CHLOROFORM"
end

%tddft
  NRoots 10
  TDA false
  MaxDim 120
  MaxIter 300
end

* xyz 0 1
C  0.00000000  0.00000000  0.00000000
H  0.00000000  0.00000000  1.00000000
*
"""

OPT_OUT = """PROGRAM ORCA
THE OPTIMIZATION HAS CONVERGED

CARTESIAN COORDINATES (ANGSTROEM)
---------------------------------
C      0.10000000      0.20000000      0.30000000
H      0.10000000      0.20000000      1.30000000

ORCA TERMINATED NORMALLY
"""

VERT_OUT = """PROGRAM ORCA
STATE   1: E= 0.090000 au  2.2500 eV  551.04 nm

ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
  1  18147.5  551.04  0.3000  0.0 0.0 0.0

ORCA TERMINATED NORMALLY
"""


class TDDFTEmissionSequenceTests(unittest.TestCase):
    def test_excited_state_optimization_input_targets_s1_and_preserves_settings(self):
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10)

        text = build_excited_state_optimization_input(SOURCE_INP, settings)

        self.assertIn("! CAM-B3LYP def2-TZVP TightSCF Opt", text)
        self.assertNotIn(" SP", text)
        self.assertIn('%cpcm\n  smd true\n  SMDsolvent "CHLOROFORM"\nend', text)
        self.assertIn("NRoots 10", text)
        self.assertIn("TDA false", text)
        self.assertIn("IRoot 1", text)
        self.assertIn("IRootMult singlet", text)
        self.assertNotIn("FollowIRoot", text)

    def test_excited_state_optimization_input_preserves_tda_method(self):
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10, td_method="TDA")

        text = build_excited_state_optimization_input(SOURCE_INP, settings)

        self.assertIn("TDA true", text)
        self.assertNotIn("TDA false", text)

    def test_vertical_emission_input_preserves_tda_method(self):
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10, td_method="TDA")
        atoms = [("C", 0.1, 0.2, 0.3), ("H", 0.1, 0.2, 1.3)]

        text = build_vertical_emission_input(SOURCE_INP, atoms, settings)

        self.assertIn("TDA true", text)
        self.assertNotIn("TDA false", text)
        self.assertIn("C   0.10000000  0.20000000  0.30000000", text)
        self.assertIn("H   0.10000000  0.20000000  1.30000000", text)

    def test_excited_state_optimization_input_drops_guess_reuse_directives(self):
        source_input_text = """! CAM-B3LYP def2-TZVP TightSCF SP Guess=Read

%maxcore 8000

%moinp "old.gbw"
end

* xyz 0 1
C  0.00000000  0.00000000  0.00000000
H  0.00000000  0.00000000  1.00000000
*
"""
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10)
        text = build_excited_state_optimization_input(source_input_text, settings)
        self.assertNotIn("Guess=Read", text)
        self.assertNotIn("%moinp", text)
        self.assertIn("! CAM-B3LYP def2-TZVP TightSCF Opt", text)

    def test_excited_state_optimization_input_drops_spaced_guess_reuse_syntax(self):
        source_input_text = """! CAM-B3LYP def2-TZVP TightSCF SP Guess = Read

* xyz 0 1
C  0.00000000  0.00000000  0.00000000
H  0.00000000  0.00000000  1.00000000
*
"""
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10)
        text = build_excited_state_optimization_input(source_input_text, settings)
        self.assertNotIn("Guess", text)
        self.assertNotIn("Read", text)
        self.assertIn("! CAM-B3LYP def2-TZVP TightSCF Opt", text)

    def test_legacy_tdg_block_in_source_input_is_replaced(self):
        source_input_text = """! CAM-B3LYP def2-TZVP TightSCF SP

%tdg
  NRoots 10
  TDA false
  MaxDim 5
  MaxIter 300
  IRoot 1
  Mult singlet
end

* xyz 0 1
C  0.00000000  0.00000000  0.00000000
H  0.00000000  0.00000000  1.00000000
*
"""
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10)
        text = build_excited_state_optimization_input(source_input_text, settings)
        self.assertIn("%tddft", text)
        self.assertIn("IRootMult singlet", text)
        self.assertNotIn("%tdg", text)

    def test_vertical_emission_input_uses_optimized_geometry(self):
        settings = EmissionSequenceSettings(source_output="abs.out", target_root=1, nroots=10)
        atoms = [("C", 0.1, 0.2, 0.3), ("H", 0.1, 0.2, 1.3)]

        text = build_vertical_emission_input(SOURCE_INP, atoms, settings)

        self.assertIn("! CAM-B3LYP def2-TZVP TightSCF SP", text)
        self.assertNotIn(" Opt", text)
        self.assertNotIn("IRoot", text)
        self.assertIn("C   0.10000000  0.20000000  0.30000000", text)
        self.assertIn("H   0.10000000  0.20000000  1.30000000", text)

    def test_prepare_advance_finalize_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "abs.out"
            inp = root / "abs.inp"
            out.write_text(ABS_OUT, encoding="utf-8")
            inp.write_text(SOURCE_INP, encoding="utf-8")
            settings = EmissionSequenceSettings(source_output=str(out), source_input=str(inp), target_root=1, nroots=10)

            manifest = prepare_emission_sequence(settings)

            seq_dir = Path(manifest.steps[0].input_path).parent
            self.assertTrue((seq_dir / "emission_sequence.json").is_file())
            self.assertTrue((seq_dir / "01_esopt_S1.inp").is_file())

            Path(manifest.steps[0].output_path).write_text(OPT_OUT, encoding="utf-8")
            manifest = advance_after_optimization(seq_dir)

            vertical = seq_dir / "02_vertical_emission_S1.inp"
            self.assertTrue(vertical.is_file())
            self.assertTrue((seq_dir / "01_esopt_S1_final.xyz").is_file())
            self.assertIn("0.10000000", vertical.read_text(encoding="utf-8"))

            vertical.with_suffix(".out").write_text(VERT_OUT, encoding="utf-8")
            _manifest, result = finalize_after_vertical(seq_dir)

            self.assertAlmostEqual(result.emission_energy_ev, 2.25, places=4)
            self.assertAlmostEqual(result.emission_wavelength_nm, 1239.841984 / result.emission_energy_ev)
            self.assertAlmostEqual(result.stokes_shift_ev, 0.25, places=4)
            self.assertTrue((seq_dir / "emission_result.json").is_file())
            self.assertTrue((seq_dir / "emission_spectrum.csv").is_file())
            self.assertTrue((seq_dir / "emission_summary.txt").is_file())

if __name__ == "__main__":
    unittest.main()
