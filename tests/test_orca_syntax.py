import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"
import sys as _sys
if str(MODULE_PATH.parent) not in _sys.path:
    _sys.path.insert(0, str(MODULE_PATH.parent))
if str(MODULE_PATH.parents[1]) not in _sys.path:
    _sys.path.insert(0, str(MODULE_PATH.parents[1]))
spec = importlib.util.spec_from_file_location("orca_input", MODULE_PATH)
orca_input = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys = __import__("sys")
sys.modules["orca_input"] = orca_input
spec.loader.exec_module(orca_input)

# Known bad strings that should NEVER appear in our generated input
BANNED_STRINGS = [
    "DoTDA",      # Caused parsing error in ORCA 6
    "UNKNOWN",
]

class OrcaSyntaxTests(unittest.TestCase):
    def setUp(self):
        # Create a simple water molecule for testing
        self.water = orca_input.Structure(
            atoms=[("O", 0.0, 0.0, 0.0), ("H", 0.0, 0.75, 0.5), ("H", 0.0, -0.75, 0.5)],
            title="Water Test"
        )
        
        # Base valid data dictionary
        self.base_data = {
            "functional": "B3LYP",
            "basis": "def2-SVP",
            "dispersion": "D4",
            "grid": "Grid4",
            "charge": 0,
            "multiplicity": 1,
            "ri_jcosx": False,
            "tight_scf": False,
            "job_opt": False,
            "job_freq": False,
            "job_density": False,
            "job_esp": False,
            "job_sp": True,
            "job_tddft": False,
            "job_nmr": False,
            "print_mos": False,
            "nroots": 10,
            "extra": "",
            "freeze_all": False,
            "freeze_heavy": False,
            "solvent": None,
        }

    def test_tddft_syntax_does_not_contain_dotda(self):
        """Ensure the TD-DFT block uses 'TDA true' instead of the removed 'DoTDA true'."""
        data = self.base_data.copy()
        data["job_tddft"] = True
        data["tddft_block"] = "%tddft\n  NRoots 10\n  TDA true\n  MaxDim 40\n  MaxIter 100\nend"

        inp_text = orca_input.generate_orca(data, self.water, solvent=None)

        self.assertNotIn("DoTDA", inp_text, "Found banned string 'DoTDA' in ORCA input!")
        self.assertIn("tda true", inp_text.lower(), "TD-DFT block should contain 'TDA true'")

    def test_nmr_syntax(self):
        """Ensure an NMR job emits the valid %eprnmr block (v1.1.13)."""
        data = self.base_data.copy()
        data["job_nmr"] = True

        inp_text = orca_input.generate_orca(data, self.water, solvent=None)

        self.assertIn("%eprnmr", inp_text, "NMR job should generate a %eprnmr block")
        self.assertIn("NMR true", inp_text, "The %eprnmr block should enable NMR true")

    def test_all_combinations_against_banned_strings(self):
        """Generates inputs with various flags and verifies no banned typos are present."""
        combinations = [
            {"job_opt": True, "job_freq": True},
            {"job_nmr": True},
            {"job_esp": True},
            {"job_tddft": True, "freeze_heavy": True}
        ]
        
        for overrides in combinations:
            data = self.base_data.copy()
            data.update(overrides)
            inp_text = orca_input.generate_orca(data, self.water, solvent=None)
            
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, inp_text, f"Banned string '{banned}' found in config: {overrides}")

    def test_dry_run_with_orca_executable(self):
        """If ORCA is available, pass the TD-DFT input to it to ensure it parses successfully."""
        candidates = orca_input.find_orca_candidates()
        if not candidates:
            self.skipTest("ORCA executable not found on the system. Skipping dry-run syntax check.")
            
        orca_path = candidates[0]
        
        data = self.base_data.copy()
        data["job_tddft"] = True
        # Speed up by using cheap parameters for the dry-run calculation itself
        data["functional"] = "HF"
        data["basis"] = "MINI"
        data["dispersion"] = ""
        inp_text = orca_input.generate_orca(data, self.water, solvent=None)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_file = Path(tmpdir) / "test_tddft.inp"
            inp_file.write_text(inp_text)
            
            # Run ORCA and capture output
            result = subprocess.run([orca_path, str(inp_file)], cwd=tmpdir, capture_output=True, text=True)
            
            output = result.stdout + result.stderr
            
            # ORCA might fail because of lack of memory/basis sets in a minimal environment,
            # but it should NEVER fail with "Unknown identifier" parsing errors.
            self.assertNotIn("Unknown identifier", output, "ORCA reported an unknown identifier during TDDFT parsing.")

        # Test NMR syntax dry-run
        data_nmr = self.base_data.copy()
        data_nmr["job_nmr"] = True
        data_nmr["functional"] = "HF"
        data_nmr["basis"] = "MINI"
        data_nmr["dispersion"] = ""
        inp_text_nmr = orca_input.generate_orca(data_nmr, self.water, solvent=None)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            inp_file = Path(tmpdir) / "test_nmr.inp"
            inp_file.write_text(inp_text_nmr)
            result = subprocess.run([orca_path, str(inp_file)], cwd=tmpdir, capture_output=True, text=True)
            output = result.stdout + result.stderr
            self.assertNotIn("Unknown identifier", output, "ORCA reported an unknown identifier during NMR parsing.")

if __name__ == '__main__':
    unittest.main()
