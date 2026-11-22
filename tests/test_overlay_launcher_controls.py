import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _overlay_button_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.keyword)
        and node.arg == "text"
        and isinstance(node.value, ast.Constant)
        and node.value.value == "NCI + QTAIM overlay"
    )


def test_qtaim_has_overlay_launcher_in_main_and_viewer_controls():
    path = ROOT / "tools" / "qtaim-cp" / "qtaim.py"
    assert _overlay_button_count(path) >= 3


def test_nci_has_overlay_launcher_in_main_and_viewer_controls():
    path = ROOT / "tools" / "NCI_plot" / "nci_plotter.py"
    assert _overlay_button_count(path) >= 3
