import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NCI_PLOTTER = ROOT / "tools" / "NCI_plot" / "nci_plotter.py"


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(NCI_PLOTTER.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method_name)


def test_background_change_schedules_deterministic_scene_rebuild():
    method = _method_node("NCIPlotterApp", "apply_live_background")
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "schedule_live_plot_update"
    ]
    assert len(calls) == 1


def test_plot_rebuild_reapplies_standard_pyvista_lighting():
    method = _method_node("NCIPlotterApp", "update_plot")
    calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "configure_pyvista_defaults"
    ]
    assert len(calls) == 1
