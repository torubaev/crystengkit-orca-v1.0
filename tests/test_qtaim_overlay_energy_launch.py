import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QTAIM = ROOT / "tools" / "qtaim-cp" / "qtaim.py"


def test_qtaim_launcher_forwards_energy_visibility_and_unit():
    tree = ast.parse(QTAIM.read_text(encoding="utf-8"))
    gui = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "QTAIMGui")
    method = next(node for node in gui.body if isinstance(node, ast.FunctionDef) and node.name == "open_nci_qtaim_overlay")
    literals = {
        node.value
        for node in ast.walk(method)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "--show-bcp-energy" in literals
    assert "--cp-energy-unit" in literals
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "save_cp_table"
    ]
    assert len(calls) == 1
