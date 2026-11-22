import importlib.util
import sys
import tempfile
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
        self.label_calls = []
        self.text_calls = []

    def add_lines(self, points, **kwargs):
        self.line_calls.append((points, kwargs))
        return self.actor

    def add_mesh(self, mesh, **kwargs):
        self.mesh_calls.append((mesh, kwargs))

    def add_point_labels(self, points, labels, **kwargs):
        self.label_calls.append((points, labels, kwargs))

    def add_text(self, text, **kwargs):
        self.text_calls.append((text, kwargs))


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


def test_overlay_bcp_energy_checkbox_uses_qtaim_energy_formatter(monkeypatch):
    overlay = load_overlay_module()
    monkeypatch.setattr(overlay, "pv", SimpleNamespace(Sphere=lambda **kwargs: kwargs))
    plotter = FakePlotter()
    cp = SimpleNamespace(cp_type="(3,-1)", x=0, y=0, z=0, index=4)
    qtaim = SimpleNamespace(
        normalize_cp_type=lambda value: value,
        format_cp_energy_label=lambda point, unit: f"-12.3 {unit}",
        BCP_ENERGY_HEADER="BCP interaction energy: 0.5V(r)",
    )

    overlay.add_qtaim_bcps(
        plotter,
        qtaim,
        [cp],
        show_labels=False,
        show_bcp_energy=True,
        cp_energy_unit="kJ/mol",
    )

    assert plotter.label_calls[0][1] == ["-12.3 kJ/mol"]
    assert plotter.text_calls[0][0] == "BCP interaction energy: 0.5V(r)"


def test_cp_autodetection_prefers_property_table_over_pdb():
    overlay = load_overlay_module()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "CPs.pdb").write_text("coordinate-only", encoding="utf-8")
        property_table = folder / "CPprop.txt"
        property_table.write_text("contains V(r)", encoding="utf-8")

        assert overlay.find_qtaim_cp_file(folder, "sample") == property_table


def test_coordinate_only_cps_are_enriched_from_companion_properties():
    overlay = load_overlay_module()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        pdb = folder / "CPs.pdb"
        table = folder / "CPprop.txt"
        pdb.write_text("coordinates", encoding="utf-8")
        table.write_text("properties", encoding="utf-8")
        target = SimpleNamespace(
            index=2,
            cp_type="(3,-1)",
            kinetic_energy_density=None,
            potential_energy_density=None,
            energy_density=None,
        )
        source = SimpleNamespace(
            index=2,
            cp_type="(3,-1)",
            kinetic_energy_density=0.01,
            potential_energy_density=-0.02,
            energy_density=-0.01,
        )
        qtaim = SimpleNamespace(
            normalize_cp_type=lambda value: value,
            parse_critical_points_file=lambda path: [source] if path.name == "CPprop.txt" else [target],
        )

        enriched, companion = overlay.enrich_cps_with_companion_energies([target], pdb, qtaim)

        assert companion == table
        assert enriched[0].potential_energy_density == -0.02


def test_coordinate_alignment_preserves_bcp_energy_properties():
    overlay = load_overlay_module()

    class CriticalPoint:
        def __init__(
            self, index, cp_type, x, y, z, rho=None, laplacian=None,
            ellipticity=None, kinetic_energy_density=None,
            potential_energy_density=None, energy_density=None,
        ):
            self.index = index
            self.cp_type = cp_type
            self.x, self.y, self.z = x, y, z
            self.rho = rho
            self.laplacian = laplacian
            self.ellipticity = ellipticity
            self.kinetic_energy_density = kinetic_energy_density
            self.potential_energy_density = potential_energy_density
            self.energy_density = energy_density

    source = CriticalPoint(
        87, "(3,-1)", 1, 2, 3,
        kinetic_energy_density=0.002,
        potential_energy_density=-0.004,
        energy_density=-0.002,
    )

    transformed = overlay.transform_cps([source], lambda xyz: tuple(value * 0.5 for value in xyz))

    assert transformed[0].potential_energy_density == -0.004
    assert transformed[0].kinetic_energy_density == 0.002
    assert (transformed[0].x, transformed[0].y, transformed[0].z) == (0.5, 1.0, 1.5)
