from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_screenshot_export_is_explicitly_opaque():
    tools_root = ROOT / "tools"
    sys.path.insert(0, str(tools_root))
    try:
        from shared.pyvista_window import save_pyvista_screenshot
    finally:
        sys.path.remove(str(tools_root))

    class Plotter:
        def __init__(self):
            self.calls = []

        def screenshot(self, path, **kwargs):
            self.calls.append((path, kwargs))
            return "saved"

    plotter = Plotter()
    assert save_pyvista_screenshot(plotter, "figure.png", "white", scale=2) == "saved"
    assert plotter.calls == [
        ("figure.png", {"transparent_background": False, "scale": 2})
    ]


def test_every_selectable_pyvista_background_is_uniform():
    paths = [
        ROOT / "tools" / "qtaim-cp" / "qtaim.py",
        ROOT / "tools" / "NCI_plot" / "nci_plotter.py",
        ROOT / "tools" / "VisMap_5.0" / "VisMap5.6_pyvista.py",
        ROOT / "tools" / "NCI_QTAIM_overlay" / "nci_qtaim_overlay.py",
    ]

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "HQ_BACKGROUND_TOP"
                for target in node.targets
            )
        )
        colors = ast.literal_eval(assignment.value)
        assert colors["white"] == "#ffffff", path
        assert colors["black"] == "#000000", path
