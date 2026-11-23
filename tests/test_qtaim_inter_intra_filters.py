from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
MODULE_PATH = TOOLS / "qtaim-cp" / "qtaim.py"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("qtaim_scope_filters", MODULE_PATH)
qtaim = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = qtaim
spec.loader.exec_module(qtaim)


def _two_fragments():
    return [
        qtaim.Atom("H", 0.00, 0.0, 0.0),
        qtaim.Atom("H", 0.74, 0.0, 0.0),
        qtaim.Atom("H", 5.00, 0.0, 0.0),
        qtaim.Atom("H", 5.74, 0.0, 0.0),
    ]


def test_bcp_scope_separates_inter_and_intramolecular_connections():
    atoms = _two_fragments()
    fragment_ids = qtaim.molecular_fragment_ids(atoms, [(0, 1), (2, 3)])
    intramolecular = qtaim.CriticalPoint(1, "(3,-1)", 0.37, 0.0, 0.0)
    intermolecular = qtaim.CriticalPoint(2, "(3,-1)", 2.87, 0.0, 0.0)

    assert qtaim.bcp_scope(intramolecular, atoms, fragment_ids) == "intramolecular"
    assert qtaim.bcp_scope(intermolecular, atoms, fragment_ids) == "intermolecular"


def test_bond_path_scope_uses_path_endpoints():
    atoms = _two_fragments()
    fragment_ids = qtaim.molecular_fragment_ids(atoms, [(0, 1), (2, 3)])
    intra_path = qtaim.BondPath(1, [(0.0, 0.0, 0.0), (0.74, 0.0, 0.0)])
    inter_path = qtaim.BondPath(2, [(0.74, 0.0, 0.0), (5.0, 0.0, 0.0)])

    assert qtaim.bond_path_scope(intra_path, atoms, fragment_ids) == "intramolecular"
    assert qtaim.bond_path_scope(inter_path, atoms, fragment_ids) == "intermolecular"
    assert qtaim.qtaim_scope_visible("intermolecular", False, True) is False
    assert qtaim.qtaim_scope_visible("intramolecular", False, True) is True


def test_both_scope_checkboxes_default_to_enabled():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "self.show_intermolecular_bcp_paths = tk.BooleanVar(value=True)" in source
    assert "self.show_intramolecular_bcp_paths = tk.BooleanVar(value=True)" in source


def test_manual_bcp_table_parses_edits_and_preserves_other_properties():
    original = qtaim.CriticalPoint(
        7, "(3,-1)", 1.0, 2.0, 3.0,
        rho=0.02, laplacian=0.04, ellipticity=0.1,
        potential_energy_density=-0.03,
    )

    class FakeText:
        def get(self, *_args):
            return "7\t(3,-1)\tintermolecular\t1.5\t2.5\t3.5\t0.025\t0.045\n"

    app = object.__new__(qtaim.QTAIMGui)
    app.bcp_manager_text = FakeText()
    app._bcp_manager_original_cps = [original]
    parsed = app._parse_bcp_manager_table()

    assert len(parsed) == 1
    assert (parsed[0].x, parsed[0].y, parsed[0].z) == (1.5, 2.5, 3.5)
    assert parsed[0].rho == 0.025
    assert parsed[0].laplacian == 0.045
    assert parsed[0].ellipticity == 0.1
    assert parsed[0].potential_energy_density == -0.03


def test_manual_bcp_manager_button_and_range_actions_are_wired():
    source = MODULE_PATH.read_text(encoding="utf-8")
    for expected in (
        "Manual BCP management...",
        "Delete selected lines",
        "Apply edited list",
        "Restore all",
        "Remove range",
    ):
        assert expected in source
