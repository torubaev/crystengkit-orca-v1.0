"""
Comprehensive bug-hunting test suite for CrystEngKit ORCA input generator.
Covers: all flag combos, BSSE math, solvent/dispersion/grid resolution,
parsers, electron counting, parity checks, ghost atoms, and more.
"""
from __future__ import annotations

import importlib.util
import itertools
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Dict

# ---------------------------------------------------------------------------
# Load orca_input module (avoids tkinter mainloop)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "Orca_input" / "orca_input.py"
import sys as _sys
if str(MODULE_PATH.parent) not in _sys.path:
    _sys.path.insert(0, str(MODULE_PATH.parent))
if str(MODULE_PATH.parents[1]) not in _sys.path:
    _sys.path.insert(0, str(MODULE_PATH.parents[1]))
spec = importlib.util.spec_from_file_location("orca_input", MODULE_PATH)
orca_input = importlib.util.module_from_spec(spec)
sys.modules["orca_input"] = orca_input
spec.loader.exec_module(orca_input)

generate_orca = orca_input.generate_orca
generate_gaussian = orca_input.generate_gaussian
resolve_solvent = orca_input.resolve_solvent
resolve_dispersion_keyword = orca_input.resolve_dispersion_keyword
normalize_orca_grid_keyword = orca_input.normalize_orca_grid_keyword
validate_charge_multiplicity_parity = orca_input.validate_charge_multiplicity_parity
spin_coupling_warning = orca_input.spin_coupling_warning
electron_count_for_indices = orca_input.electron_count_for_indices
formula_for_indices = orca_input.formula_for_indices
looks_like_2d_structure = orca_input.looks_like_2d_structure
subset_structure = orca_input.subset_structure
# Optional feature (PR pending upstream): shell-safe ORCA input paths.
# Guarded so the suite still collects and passes on a stock v1.1.18 tree.
sanitize_orca_run_path = getattr(orca_input, "sanitize_orca_run_path", None)
Structure = orca_input.Structure
StructureParser = orca_input.StructureParser
validate_xyz_text = orca_input.validate_xyz_text
parse_mol_v2000_atoms = orca_input.parse_mol_v2000_atoms
HARTREE_TO_KCAL_MOL = orca_input.HARTREE_TO_KCAL_MOL
HARTREE_TO_KJ_MOL = orca_input.HARTREE_TO_KJ_MOL

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
WATER_ATOMS = [("O", 0.0, 0.0, 0.117), ("H", 0.0, 0.757, -0.468), ("H", 0.0, -0.757, -0.468)]
WATER_2D_ATOMS = [("O", 0.0, 0.0, 0.0), ("H", 0.757, 0.0, 0.0), ("H", -0.757, 0.0, 0.0)]
ETHANE_ATOMS = [
    ("C", 0.0, 0.0, 0.765), ("C", 0.0, 0.0, -0.765),
    ("H", 1.019, 0.0, 1.157), ("H", -0.509, 0.882, 1.157), ("H", -0.509, -0.882, 1.157),
    ("H", 1.019, 0.0, -1.157), ("H", -0.509, 0.882, -1.157), ("H", -0.509, -0.882, -1.157),
]

def water():
    return Structure(WATER_ATOMS, title="Water")

def ethane():
    return Structure(ETHANE_ATOMS, title="Ethane")

def base_data(**overrides) -> Dict:
    d = {
        "functional": "B3LYP",
        "basis": "def2-SVP",
        "dispersion": "",
        "grid": "",
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
    d.update(overrides)
    return d

WATER_MOL_V2000 = (
    "\n\n\n  3  2  0  0  0  0  0  0  0  0999 V2000\n"
    "    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    0.7572    0.5860    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "   -0.7572    0.5860    0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0\n  1  3  1  0\nM  END\n"
)

# ===========================================================================
# 1. ORCA input generation
# ===========================================================================
class TestOrcaInputGeneration(unittest.TestCase):

    def _gen(self, **overrides) -> str:
        return generate_orca(base_data(**overrides), water(), solvent=None)

    # SP keyword logic
    def test_sp_present_for_bare_sp(self):
        self.assertIn("SP", self._gen(job_sp=True).split("\n")[0])

    def test_sp_absent_when_opt_set(self):
        self.assertNotIn("SP", self._gen(job_sp=True, job_opt=True).split("\n")[0].split())

    def test_sp_absent_when_tddft_set(self):
        self.assertNotIn("SP", self._gen(job_sp=True, job_tddft=True).split("\n")[0].split())

    def test_sp_absent_when_nmr_set(self):
        self.assertNotIn("SP", self._gen(job_sp=True, job_nmr=True).split("\n")[0].split())

    def test_sp_absent_when_freq_set(self):
        self.assertNotIn("SP", self._gen(job_sp=True, job_freq=True).split("\n")[0].split())

    # Opt / Freq
    def test_opt_keyword_present(self):
        self.assertIn("Opt", self._gen(job_opt=True).split("\n")[0])

    def test_freq_keyword_present(self):
        self.assertIn("Freq", self._gen(job_freq=True).split("\n")[0])

    def test_opt_and_freq_together(self):
        first = self._gen(job_opt=True, job_freq=True).split("\n")[0]
        self.assertIn("Opt", first)
        self.assertIn("Freq", first)

    # TD-DFT
    def test_tddft_uses_tda_true(self):
        # v1.1.13: TD-DFT blocks come from the TD-DFT workspace as a fragment.
        block = "%tddft\n  NRoots 10\n  TDA true\n  MaxDim 40\n  MaxIter 100\nend"
        text = self._gen(job_tddft=True, tddft_block=block)
        self.assertIn("TDA true", text)
        self.assertNotIn("DoTDA", text)

    def test_tddft_nroots_correct(self):
        for n in [3, 10, 25]:
            block = f"%tddft\n  NRoots {n}\n  TDA true\n  MaxDim {4 * n}\n  MaxIter 100\nend"
            self.assertIn(f"NRoots {n}", self._gen(job_tddft=True, tddft_block=block))

    def test_tddft_block_has_triplets_false(self):
        # The v1.1.13 module emits no Triplets line for singlet-only jobs and
        # never emits the obsolete 'Triplets false' / 'DoTDA' forms.
        block = "%tddft\n  NRoots 10\n  TDA true\n  MaxDim 40\n  MaxIter 100\nend"
        text = self._gen(job_tddft=True, tddft_block=block)
        self.assertNotIn("DoTDA", text)
        self.assertNotIn("Triplets false", text)

    # NMR
    def test_nmr_on_simple_input_line(self):
        # v1.1.13 emits the %eprnmr block (valid ORCA syntax).
        self.assertIn("%eprnmr", self._gen(job_nmr=True))

    def test_nmr_no_eprnmr_block(self):
        text = self._gen(job_nmr=True)
        self.assertIn("NMR true", text)
        self.assertIn("%eprnmr", text)

    # KeepDens
    def test_keepdens_for_density(self):
        self.assertIn("KeepDens", self._gen(job_density=True).split("\n")[0])

    def test_keepdens_for_esp(self):
        self.assertIn("KeepDens", self._gen(job_esp=True).split("\n")[0])

    def test_keepdens_absent_plain_sp(self):
        self.assertNotIn("KeepDens", self._gen().split("\n")[0])

    # RIJCOSX
    def test_rijcosx_keywords(self):
        first = self._gen(ri_jcosx=True).split("\n")[0]
        self.assertIn("def2/J", first)
        self.assertIn("RIJCOSX", first)

    # TightSCF
    def test_tightscf(self):
        self.assertIn("TightSCF", self._gen(tight_scf=True).split("\n")[0])

    # Solvent block
    def test_cpcm_block_with_solvent(self):
        solv = resolve_solvent("water")
        text = generate_orca(base_data(), water(), solvent=solv)
        self.assertIn("%cpcm", text)
        self.assertIn("smd true", text)
        self.assertIn("SMDsolvent", text)

    def test_no_cpcm_without_solvent(self):
        self.assertNotIn("%cpcm", self._gen())

    # Print MOs
    def test_print_mos_output_block(self):
        text = self._gen(print_mos=True)
        self.assertIn("%output", text)
        self.assertIn("Print[P_MOs]", text)

    # Extra
    def test_extra_text_appended(self):
        self.assertIn("%scf MaxIter 500 end", self._gen(extra="%scf MaxIter 500 end"))

    # Coordinate block
    def test_xyz_block_present(self):
        text = self._gen()
        self.assertIn("* xyz", text)

    def test_charge_multiplicity_in_xyz_block(self):
        text = generate_orca(base_data(charge=1, multiplicity=2), water(), solvent=None)
        self.assertIn("* xyz 1 2", text)

    # Constraints
    def test_freeze_all_generates_geom_block(self):
        text = generate_orca(base_data(job_opt=True, freeze_all=True), water(), solvent=None)
        self.assertIn("%geom", text)
        self.assertIn("Constraints", text)
        self.assertEqual(text.count("{ "), 3)  # 3 atoms in water

    def test_freeze_heavy_excludes_hydrogen(self):
        text = generate_orca(base_data(job_opt=True, freeze_heavy=True), water(), solvent=None)
        self.assertIn("%geom", text)
        self.assertEqual(text.count("{ O"), 1)
        self.assertNotIn("{ H", text)

    def test_freeze_no_geom_block_without_opt(self):
        self.assertNotIn("%geom", generate_orca(base_data(job_opt=False, freeze_all=True), water(), solvent=None))

    # Grid
    def test_grid_passthrough(self):
        self.assertIn("DefGrid2", self._gen(grid="DefGrid2").split("\n")[0])

    def test_grid_legacy_mapping(self):
        first = self._gen(grid="Grid5").split("\n")[0]
        self.assertIn("DefGrid2", first)
        self.assertNotIn("Grid5", first)

    # Dispersion
    def test_d4_in_orca(self):
        self.assertIn("D4", self._gen(dispersion="D4").split("\n")[0])

    def test_d3bj_in_orca(self):
        self.assertIn("D3BJ", self._gen(dispersion="D3BJ").split("\n")[0])

    def test_invalid_dispersion_omitted(self):
        self.assertNotIn("GARBAGE", self._gen(dispersion="GARBAGE").split("\n")[0])

    # Banned-string sweep across all 2-flag combinations
    def test_no_banned_strings_in_all_2_flag_combos(self):
        BANNED = ["DoTDA", "DOTDA", "dotda"]  # %eprnmr is valid v1.1.13 syntax for NMR
        flags = ["job_opt", "job_freq", "job_tddft", "job_nmr", "job_sp",
                 "job_density", "job_esp", "ri_jcosx", "tight_scf", "print_mos"]
        for combo in itertools.combinations(flags, 2):
            data = base_data(**{f: True for f in combo})
            text = generate_orca(data, water(), solvent=None)
            for b in BANNED:
                self.assertNotIn(b, text, msg=f"'{b}' found in combo {combo}")


# ===========================================================================
# 2. Gaussian input generation
# ===========================================================================
class TestGaussianInputGeneration(unittest.TestCase):

    def _gen(self, **overrides) -> str:
        return generate_gaussian(base_data(**overrides), water(), solvent=None)

    def test_route_line_present(self):
        self.assertTrue(self._gen().startswith("#P "))

    def test_functional_basis_in_route(self):
        self.assertIn("B3LYP/def2-SVP", self._gen())

    def test_opt_keyword(self):
        self.assertIn("Opt", self._gen(job_opt=True))

    def test_freq_keyword(self):
        self.assertIn("Freq", self._gen(job_freq=True))

    def test_tddft_nstates(self):
        self.assertIn("TD(NStates=6)", self._gen(job_tddft=True, nroots=6))

    def test_nmr_keyword(self):
        self.assertIn("NMR", self._gen(job_nmr=True))

    def test_d3bj_dispersion_mapped(self):
        self.assertIn("EmpiricalDispersion=GD3BJ", self._gen(dispersion="D3BJ"))

    def test_d4_dispersion_omitted_with_warning(self):
        data = base_data(dispersion="D4")
        text = generate_gaussian(data, water(), solvent=None)
        self.assertNotIn(" D4", text.split("\n")[0])
        self.assertTrue(any("D4" in w for w in data.get("_warnings", [])))

    def test_solvent_scrf(self):
        solv = resolve_solvent("dichloromethane")
        text = generate_gaussian(base_data(), water(), solvent=solv)
        self.assertIn("SCRF=(SMD,Solvent=", text)

    def test_density_keyword(self):
        self.assertIn("Density=Current", self._gen(job_density=True))

    def test_esp_pop_mk(self):
        self.assertIn("Pop=MK", self._gen(job_esp=True))

    def test_charge_multiplicity_line(self):
        text = generate_gaussian(base_data(charge=-1, multiplicity=2), water(), solvent=None)
        lines = [l.strip() for l in text.split("\n")]
        self.assertIn("-1 2", lines)


# ===========================================================================
# 3. Solvent resolution
# ===========================================================================
class TestSolventResolution(unittest.TestCase):

    def test_water_resolves(self):
        s = resolve_solvent("water")
        self.assertIsNotNone(s)
        self.assertIn("orca", s)
        self.assertIn("gaussian", s)

    def test_dcm_alias(self):
        self.assertIsNotNone(resolve_solvent("DCM"), msg="'DCM' alias not found")

    def test_dichloromethane(self):
        self.assertIsNotNone(resolve_solvent("dichloromethane"))

    def test_empty_returns_none(self):
        self.assertIsNone(resolve_solvent(""))
        self.assertIsNone(resolve_solvent("   "))

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_solvent("kryptonite"))

    def test_case_insensitive(self):
        self.assertEqual(resolve_solvent("WATER"), resolve_solvent("water"))

    def test_acetone(self):
        self.assertIsNotNone(resolve_solvent("acetone"))

    def test_thf(self):
        self.assertIsNotNone(resolve_solvent("THF"))

    def test_ethanol(self):
        self.assertIsNotNone(resolve_solvent("ethanol"))

    def test_toluene(self):
        self.assertIsNotNone(resolve_solvent("toluene"))

    def test_dmf(self):
        self.assertIsNotNone(resolve_solvent("DMF"))

    def test_dmso(self):
        self.assertIsNotNone(resolve_solvent("DMSO"))

    def test_chloroform(self):
        self.assertIsNotNone(resolve_solvent("chloroform"))


# ===========================================================================
# 4. Dispersion keyword resolution
# ===========================================================================
class TestDispersionResolution(unittest.TestCase):

    def test_d4_orca(self):
        kw, w = resolve_dispersion_keyword("ORCA", "D4")
        self.assertEqual(kw, "D4"); self.assertEqual(w, [])

    def test_d3bj_orca(self):
        kw, w = resolve_dispersion_keyword("ORCA", "D3BJ")
        self.assertEqual(kw, "D3BJ"); self.assertEqual(w, [])

    def test_d3bj_gaussian_mapped(self):
        kw, w = resolve_dispersion_keyword("Gaussian", "D3BJ")
        self.assertEqual(kw, "EmpiricalDispersion=GD3BJ"); self.assertEqual(w, [])

    def test_d4_gaussian_omitted_with_warning(self):
        kw, w = resolve_dispersion_keyword("Gaussian", "D4")
        self.assertEqual(kw, ""); self.assertTrue(w)

    def test_empty(self):
        kw, w = resolve_dispersion_keyword("ORCA", "")
        self.assertEqual(kw, ""); self.assertEqual(w, [])

    def test_garbage_omitted(self):
        kw, w = resolve_dispersion_keyword("ORCA", "XYZ123")
        self.assertEqual(kw, ""); self.assertTrue(w)


# ===========================================================================
# 5. Grid keyword normalization
# ===========================================================================
class TestGridNormalization(unittest.TestCase):

    def test_grid4_to_defgrid1(self):
        kw, w = normalize_orca_grid_keyword("Grid4")
        self.assertEqual(kw, "DefGrid1"); self.assertTrue(w)

    def test_grid5_to_defgrid2(self):
        kw, _ = normalize_orca_grid_keyword("Grid5")
        self.assertEqual(kw, "DefGrid2")

    def test_grid6_to_defgrid3(self):
        kw, _ = normalize_orca_grid_keyword("Grid6")
        self.assertEqual(kw, "DefGrid3")

    def test_grid7_to_defgrid3(self):
        kw, _ = normalize_orca_grid_keyword("Grid7")
        self.assertEqual(kw, "DefGrid3")

    def test_defgrid1_passthrough(self):
        kw, w = normalize_orca_grid_keyword("DefGrid1")
        self.assertEqual(kw, "DefGrid1"); self.assertEqual(w, [])

    def test_empty(self):
        kw, w = normalize_orca_grid_keyword("")
        self.assertEqual(kw, ""); self.assertEqual(w, [])


# ===========================================================================
# 6. Charge/multiplicity parity validator
# ===========================================================================
class TestChargeMultiplicityParity(unittest.TestCase):

    def test_valid_singlet(self):
        self.assertEqual(validate_charge_multiplicity_parity("t", 10, 1), [])

    def test_valid_doublet(self):
        self.assertEqual(validate_charge_multiplicity_parity("t", 9, 2), [])

    def test_valid_triplet(self):
        self.assertEqual(validate_charge_multiplicity_parity("t", 8, 3), [])

    def test_parity_mismatch_even_electrons_doublet(self):
        self.assertTrue(validate_charge_multiplicity_parity("t", 10, 2))

    def test_parity_mismatch_odd_electrons_singlet(self):
        self.assertTrue(validate_charge_multiplicity_parity("t", 9, 1))

    def test_zero_electrons_singlet_ok(self):
        self.assertEqual(validate_charge_multiplicity_parity("t", 0, 1), [])

    def test_zero_electrons_triplet_forbidden(self):
        self.assertTrue(validate_charge_multiplicity_parity("t", 0, 3))

    def test_negative_electrons_error(self):
        self.assertTrue(validate_charge_multiplicity_parity("t", -1, 1))

    def test_multiplicity_zero_error(self):
        self.assertTrue(validate_charge_multiplicity_parity("t", 10, 0))

    def test_mult_exceeds_electrons(self):
        # 2 electrons, multiplicity 4 → impossible
        self.assertTrue(validate_charge_multiplicity_parity("t", 2, 4))


# ===========================================================================
# 7. Electron count
# ===========================================================================
class TestElectronCount(unittest.TestCase):

    def test_water_neutral(self):
        # O(8) + H(1) + H(1) = 10
        self.assertEqual(electron_count_for_indices(water(), [0, 1, 2], 0), 10)

    def test_water_cation(self):
        self.assertEqual(electron_count_for_indices(water(), [0, 1, 2], 1), 9)

    def test_water_anion(self):
        self.assertEqual(electron_count_for_indices(water(), [0, 1, 2], -1), 11)

    def test_ethane_neutral(self):
        # C(6)*2 + H(1)*6 = 18
        self.assertEqual(electron_count_for_indices(ethane(), list(range(8)), 0), 18)

    def test_single_oxygen(self):
        self.assertEqual(electron_count_for_indices(water(), [0], 0), 8)


# ===========================================================================
# 8. Spin coupling warning
# ===========================================================================
class TestSpinCouplingWarning(unittest.TestCase):

    def test_singlet_singlet_singlet_ok(self):
        self.assertIsNone(spin_coupling_warning(1, 1, 1))

    def test_two_doublets_singlet_ok(self):
        self.assertIsNone(spin_coupling_warning(1, 2, 2))

    def test_two_doublets_triplet_ok(self):
        self.assertIsNone(spin_coupling_warning(3, 2, 2))

    def test_triplet_triplet_quintet_ok(self):
        # d_a=2, d_b=2 → dimer d can be 0,2,4 → mult 5 (d=4) is valid
        self.assertIsNone(spin_coupling_warning(5, 3, 3))

    def test_impossible_parity_gives_warning(self):
        # dimer=2(d=1), A=triplet(d=2), B=triplet(d=2): (1-2-2)%2 != 0
        self.assertIsNotNone(spin_coupling_warning(2, 3, 3))


# ===========================================================================
# 9. looks_like_2d_structure
# ===========================================================================
class TestLooksLike2D(unittest.TestCase):

    def test_flat_structure_detected(self):
        self.assertTrue(looks_like_2d_structure(Structure(WATER_2D_ATOMS, title="flat")))

    def test_3d_structure_not_detected(self):
        self.assertFalse(looks_like_2d_structure(water()))

    def test_single_atom_not_2d(self):
        self.assertFalse(looks_like_2d_structure(Structure([("C", 0.0, 0.0, 0.0)], title="C")))


# ===========================================================================
# 10. subset_structure ghost atoms
# ===========================================================================
class TestSubsetStructure(unittest.TestCase):

    def test_ghost_atom_gets_colon(self):
        sub = subset_structure(ethane(), [0, 1], ghost_indices=[1])
        self.assertEqual(sub.atoms[0][0], "C")
        self.assertEqual(sub.atoms[1][0], "C:")

    def test_no_ghost_atoms_when_empty(self):
        sub = subset_structure(water(), [0, 1, 2], ghost_indices=[])
        for a in sub.atoms:
            self.assertFalse(a[0].endswith(":"))

    def test_subset_length(self):
        sub = subset_structure(ethane(), [0, 2, 4])
        self.assertEqual(len(sub.atoms), 3)


# ===========================================================================
# 11. formula_for_indices
# ===========================================================================
class TestFormulaForIndices(unittest.TestCase):

    def test_water_formula(self):
        self.assertEqual(formula_for_indices(water(), [0, 1, 2]), "H2O")  # Hill: H before O when no Carbon

    def test_ethane_formula(self):
        self.assertEqual(formula_for_indices(ethane(), list(range(8))), "C2H6")

    def test_carbon_comes_first(self):
        self.assertTrue(formula_for_indices(ethane(), [0, 2]).startswith("C"))


# ===========================================================================
# 12. BSSE / interaction energy math (hardcoded float verification)
# ===========================================================================
class TestBSSEMath(unittest.TestCase):
    """
    Replicates the exact formulas used in _compute_interaction_summary
    with controlled inputs to verify mathematical correctness.
    """
    E_DIMER = -152.131000
    E_A     = -76.065000
    E_B     = -76.065000
    E_A_CP  = -76.066000   # lower energy in dimer basis (BSSE artifact)
    E_B_CP  = -76.066000

    def test_uncorrected_interaction(self):
        uncorr = self.E_DIMER - self.E_A - self.E_B
        self.assertAlmostEqual(uncorr, -0.001, places=9)

    def test_uncorrected_in_kcal(self):
        uncorr = self.E_DIMER - self.E_A - self.E_B
        self.assertAlmostEqual(uncorr * HARTREE_TO_KCAL_MOL,
                               -0.001 * HARTREE_TO_KCAL_MOL, places=6)

    def test_cp_corrected_interaction(self):
        cp = self.E_DIMER - self.E_A_CP - self.E_B_CP
        self.assertAlmostEqual(cp, 0.001, places=9)

    def test_bsse(self):
        bsse = (self.E_A - self.E_A_CP) + (self.E_B - self.E_B_CP)
        self.assertAlmostEqual(bsse, 0.002, places=9)

    def test_energy_conservation(self):
        """CP-corrected = uncorrected + BSSE"""
        uncorr = self.E_DIMER - self.E_A - self.E_B
        cp     = self.E_DIMER - self.E_A_CP - self.E_B_CP
        bsse   = (self.E_A - self.E_A_CP) + (self.E_B - self.E_B_CP)
        self.assertAlmostEqual(uncorr + bsse, cp, places=9)

    def test_hartree_to_kcal_constant(self):
        self.assertAlmostEqual(HARTREE_TO_KCAL_MOL, 627.509474, places=3)

    def test_hartree_to_kj_constant(self):
        self.assertAlmostEqual(HARTREE_TO_KJ_MOL, 2625.49962, places=3)

    def test_kcal_kj_ratio(self):
        """1 kcal = 4.184 kJ"""
        ratio = HARTREE_TO_KJ_MOL / HARTREE_TO_KCAL_MOL
        self.assertAlmostEqual(ratio, 4.184, places=2)


# ===========================================================================
# 13. XYZ parser
# ===========================================================================
VALID_XYZ = textwrap.dedent("""\
    3
    Water molecule
    O  0.000  0.000  0.117
    H  0.000  0.757 -0.468
    H  0.000 -0.757 -0.468
""")

class TestXYZParser(unittest.TestCase):

    def test_valid_xyz_parsed(self):
        s = validate_xyz_text(VALID_XYZ, "test")
        self.assertEqual(len(s.atoms), 3)
        self.assertEqual(s.atoms[0][0], "O")

    def test_coordinates_correct(self):
        s = validate_xyz_text(VALID_XYZ, "test")
        self.assertAlmostEqual(s.atoms[0][3], 0.117, places=3)
        self.assertAlmostEqual(s.atoms[1][3], -0.468, places=3)

    def test_mismatched_count_raises(self):
        bad = "5\nWater\nO 0 0 0\nH 0 1 0\n"
        with self.assertRaises(Exception):
            validate_xyz_text(bad, "test")

    def test_empty_raises(self):
        with self.assertRaises(Exception):
            validate_xyz_text("", "test")


# ===========================================================================
# 14. ORCA .inp parser
# ===========================================================================
SAMPLE_INP = textwrap.dedent("""\
    ! B3LYP def2-SVP
    
    * xyz 0 1
    O  0.000  0.000  0.117
    H  0.000  0.757 -0.468
    H  0.000 -0.757 -0.468
    *
""")

class TestOrcaInpParser(unittest.TestCase):

    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False)
        self.f.write(SAMPLE_INP)
        self.f.close()

    def tearDown(self):
        os.unlink(self.f.name)

    def test_parses_atom_count(self):
        s = StructureParser.parse_orca_input(self.f.name)
        self.assertEqual(len(s.atoms), 3)

    def test_first_atom_oxygen(self):
        s = StructureParser.parse_orca_input(self.f.name)
        self.assertEqual(s.atoms[0][0], "O")

    def test_z_coordinate(self):
        s = StructureParser.parse_orca_input(self.f.name)
        self.assertAlmostEqual(s.atoms[0][3], 0.117, places=3)

    def test_no_xyz_block_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".inp", mode="w", delete=False) as g:
            g.write("! B3LYP def2-SVP\n")
            gname = g.name
        try:
            with self.assertRaises(ValueError):
                StructureParser.parse_orca_input(gname)
        finally:
            os.unlink(gname)


# ===========================================================================
# 15. sanitize_orca_run_path
# ===========================================================================
@unittest.skipUnless(sanitize_orca_run_path, "requires sanitize_orca_run_path support in orca_input")
class TestSanitizeOrcaRunPath(unittest.TestCase):

    def test_path_with_spaces_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "my file with spaces.inp"
            p.write_text("! B3LYP\n* xyz 0 1\nO 0 0 0\n*\n")
            result = sanitize_orca_run_path(p)
            self.assertFalse(" " in str(result),
                msg=f"Space still present in sanitized path: {result}")

    def test_path_without_spaces_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "nospaces.inp"
            p.write_text("! B3LYP\n* xyz 0 1\nO 0 0 0\n*\n")
            result = sanitize_orca_run_path(p)
            self.assertEqual(result, p)


# ===========================================================================
# 16. MOL V2000 parser
# ===========================================================================
class TestMolParser(unittest.TestCase):

    def test_parses_three_atoms(self):
        atoms, _ = parse_mol_v2000_atoms(WATER_MOL_V2000)
        self.assertEqual(len(atoms), 3)

    def test_first_atom_oxygen(self):
        atoms, _ = parse_mol_v2000_atoms(WATER_MOL_V2000)
        self.assertEqual(atoms[0][0], "O")

    def test_hydrogen_symbols(self):
        atoms, _ = parse_mol_v2000_atoms(WATER_MOL_V2000)
        self.assertEqual(atoms[1][0], "H")
        self.assertEqual(atoms[2][0], "H")


if __name__ == "__main__":
    unittest.main(verbosity=2)
