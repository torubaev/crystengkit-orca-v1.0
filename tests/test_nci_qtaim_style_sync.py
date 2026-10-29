import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
OVERLAY_PATH = ROOT / "tools" / "NCI_QTAIM_overlay" / "nci_qtaim_overlay.py"


def load_overlay_module():
    name = "nci_qtaim_overlay_style_test"
    spec = importlib.util.spec_from_file_location(name, OVERLAY_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeProperty:
    def __init__(self):
        self.width = None
        self.color = None

    def SetLighting(self, _value):
        pass

    def SetRenderLinesAsTubes(self, _value):
        pass

    def SetLineWidth(self, value):
        self.width = value

    def SetColor(self, *value):
        self.color = value


class FakeActor:
    def __init__(self):
        self.property = FakeProperty()

    def GetProperty(self):
        return self.property


class FakePlotter:
    def __init__(self):
        self.line_calls = []
        self.mesh_calls = []
        self.actor = FakeActor()

    def add_lines(self, points, **kwargs):
        self.line_calls.append((points, kwargs))
        return self.actor

    def add_mesh(self, mesh, **kwargs):
        self.mesh_calls.append((mesh, kwargs))


def test_overlay_bond_paths_honor_qtaim_color_and_width():
    overlay = load_overlay_module()
    plotter = FakePlotter()
    path = SimpleNamespace(points=[(0, 0, 0), (1, 0, 0)])

    assert overlay.add_bond_paths(plotter, [path], color="#123456", width=3.5) == 1
    assert plotter.line_calls[0][1]["color"] == "#123456"
    assert plotter.line_calls[0][1]["width"] == 3.5
    assert plotter.actor.property.width == 3.5
    assert plotter.actor.property.color == overlay.color_to_rgb01("#123456")


def test_overlay_critical_points_honor_qtaim_color_map(monkeypatch):
    overlay = load_overlay_module()
    monkeypatch.setattr(overlay, "pv", SimpleNamespace(Sphere=lambda **kwargs: kwargs))
    plotter = FakePlotter()
    cp = SimpleNamespace(cp_type="(3,-1)", x=0, y=0, z=0, index=7)
    qtaim = SimpleNamespace(normalize_cp_type=lambda value: value)

    count = overlay.add_qtaim_bcps(
        plotter,
        qtaim,
        [cp],
        show_labels=False,
        cp_colors={"(3,-1)": "#abcdef"},
    )

    assert count == 1
    assert plotter.mesh_calls[0][1]["color"] == "#abcdef"
