"""Reusable signed Gaussian-cube viewer for the TD-DFT application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

BOHR_TO_ANGSTROM = 0.529177210903


@dataclass
class CubeData:
    path: Path
    origin: object
    axes: object
    dimensions: Tuple[int, int, int]
    atoms: List[Tuple[int, float, float, float]]
    values: object


def read_cube(path: str) -> CubeData:
    import numpy as np
    cube_path = Path(path)
    lines = cube_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 7:
        raise ValueError(f"Cube file is too short: {cube_path}")
    header = lines[2].split()
    atom_count = abs(int(header[0])); origin = np.asarray([float(x) for x in header[1:4]], dtype=float)
    dims, axes, signed_dims = [], [], []
    for line in lines[3:6]:
        fields = line.split(); signed_dims.append(int(fields[0])); dims.append(abs(int(fields[0]))); axes.append([float(x) for x in fields[1:4]])
    if any(value < 2 for value in dims):
        raise ValueError(f"Invalid cube dimensions: {dims}")
    atoms = []
    for line in lines[6:6 + atom_count]:
        fields = line.split(); atoms.append((int(float(fields[0])), float(fields[2]), float(fields[3]), float(fields[4])))
    value_start = 6 + atom_count
    # Negative atom counts may be followed by an orbital/dataset-ID record.
    if int(header[0]) < 0 and value_start < len(lines):
        fields = lines[value_start].split()
        if fields and fields[0].lstrip("+-").isdigit():
            value_start += 1
    raw = [float(token.replace("D", "E")) for line in lines[value_start:] for token in line.split()]
    expected = dims[0] * dims[1] * dims[2]
    if len(raw) < expected:
        raise ValueError(f"Cube contains {len(raw)} grid values; expected {expected}: {cube_path}")
    unit_scale = BOHR_TO_ANGSTROM if all(value > 0 for value in signed_dims) else 1.0
    origin *= unit_scale; axes = np.asarray(axes) * unit_scale
    atoms = [(atomic, x * unit_scale, y * unit_scale, z * unit_scale) for atomic, x, y, z in atoms]
    return CubeData(cube_path, origin, axes, tuple(dims), atoms,
                    np.asarray(raw[:expected], dtype=float).reshape(tuple(dims), order="C"))


def _grid(cube: CubeData):
    import numpy as np
    import pyvista as pv
    axes = cube.axes
    diagonal = all(abs(axes[i, j]) < 1e-12 for i in range(3) for j in range(3) if i != j)
    if diagonal:
        grid = pv.ImageData(dimensions=cube.dimensions, spacing=tuple(abs(float(axes[i, i])) for i in range(3)), origin=tuple(cube.origin))
    else:
        i, j, k = np.indices(cube.dimensions)
        points = cube.origin + i[..., None] * axes[0] + j[..., None] * axes[1] + k[..., None] * axes[2]
        grid = pv.StructuredGrid(points[..., 0], points[..., 1], points[..., 2])
    grid.point_data["values"] = cube.values.ravel(order="F")
    return grid


def _add_molecule(plotter, cube: CubeData, show_bonds: bool, show_labels: bool):
    import numpy as np
    import pyvista as pv
    coords = np.asarray([[x, y, z] for _, x, y, z in cube.atoms])
    radii = {1: .31, 6: .76, 7: .71, 8: .66, 9: .57, 15: 1.07, 16: 1.05, 17: 1.02, 35: 1.20, 53: 1.39}
    colors = {1: "white", 6: "#555555", 7: "blue", 8: "red", 9: "#90e050", 15: "orange", 16: "yellow", 17: "green", 35: "#a52a2a", 53: "purple"}
    for (atomic, x, y, z) in cube.atoms:
        plotter.add_mesh(pv.Sphere(radius=max(.18, radii.get(atomic, .85) * .35), center=(x, y, z)), color=colors.get(atomic, "pink"))
    if show_bonds:
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                cutoff = 1.25 * (radii.get(cube.atoms[i][0], .85) + radii.get(cube.atoms[j][0], .85))
                if .25 < float(np.linalg.norm(coords[i] - coords[j])) <= cutoff:
                    plotter.add_mesh(pv.Cylinder(center=tuple((coords[i] + coords[j]) / 2), direction=tuple(coords[j] - coords[i]), radius=.08, height=float(np.linalg.norm(coords[j] - coords[i]))), color="#aaaaaa")
    if show_labels:
        plotter.add_point_labels(coords, [str(atom[0]) for atom in cube.atoms], font_size=12, point_size=0, shape=None)


class SignedCubeViewer:
    def show(self, cube_paths: Sequence[str], isovalue: float, negative_isovalue: float | None = None,
             opacity: float = 0.65, show_molecule: bool = True, show_bonds: bool = True,
             show_labels: bool = False, screenshot: str | None = None,
             labels: Sequence[str] | None = None):
        import pyvista as pv
        if not cube_paths:
            raise ValueError("No cube file is selected for this visualization mode.")
        if isovalue <= 0 or opacity <= 0 or opacity > 1:
            raise ValueError("Isovalue must be positive and opacity must be in (0, 1].")
        negative = abs(float(negative_isovalue if negative_isovalue is not None else isovalue))
        plotter = pv.Plotter(off_screen=bool(screenshot))
        colors = [("#2563eb", "#dc2626"), ("#16a34a", "#f59e0b")]
        cubes = [read_cube(path) for path in cube_paths]
        for index, cube in enumerate(cubes):
            grid = _grid(cube); positive_color, negative_color = colors[index % len(colors)]
            low, high = float(cube.values.min()), float(cube.values.max())
            if high >= isovalue:
                plotter.add_mesh(grid.contour([isovalue], scalars="values"), color=positive_color, opacity=opacity, label=(labels[index] if labels else cube.path.stem) + " (+)")
            if low <= -negative:
                plotter.add_mesh(grid.contour([-negative], scalars="values"), color=negative_color, opacity=opacity, label=(labels[index] if labels else cube.path.stem) + " (-)")
        if show_molecule:
            _add_molecule(plotter, cubes[0], show_bonds, show_labels)
        plotter.add_legend(); plotter.add_axes(); plotter.reset_camera()
        if screenshot:
            plotter.show(screenshot=screenshot, auto_close=True)
        else:
            plotter.show()
