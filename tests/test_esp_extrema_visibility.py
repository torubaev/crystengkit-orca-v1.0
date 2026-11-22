import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISMAP = ROOT / "tools" / "VisMap_5.0" / "VisMap5.6_pyvista.py"


def _function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(VISMAP.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_extrema_markers_use_renderer_visibility_filter():
    method = _function_node("_render_extrema")
    constructor_calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "vtkSelectVisiblePoints"
    ]
    assert len(constructor_calls) == 1
    direct_point_calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_points"
    ]
    assert direct_point_calls == []

    marker_call = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_mesh"
    )
    assert isinstance(marker_call.args[0], ast.Name)
    assert marker_call.args[0].id == "visible_points"

    renderer_calls = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "SetRenderer"
    ]
    assert len(renderer_calls) == 1


def test_extrema_labels_are_not_forced_visible():
    method = _function_node("_render_extrema")
    label_call = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_point_labels"
    )
    keywords = {keyword.arg: keyword.value for keyword in label_call.keywords}
    assert isinstance(keywords["always_visible"], ast.Constant)
    assert keywords["always_visible"].value is False
    assert isinstance(keywords["tolerance"], ast.Constant)
    assert keywords["tolerance"].value == 0.001
