#!/usr/bin/env python3
"""
XYZ PyVista ball-and-stick viewer.

Stable-lighting version:
    - GUI starts before PyVista/VTK is imported.
    - PyVista is imported only when opening the viewer or saving PNG.
    - Uses camera-following light + high ambient lighting to avoid black-out during rotation.
    - Provides three lighting modes:
        1. Stable Mercury-like
        2. Studio fixed lights
        3. Flat/no-black
    - XYZ-only.
    - Bonds are guessed geometrically because XYZ has no stored connectivity.

Install:
    pip install pyvista numpy periodictable
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception as exc:
    raise SystemExit(f"Tkinter could not be imported:\n{exc}")


ELEMENT_COLORS: Dict[str, str] = {
    "H": "#F2F2F2",
    "C": "#5A5A5A",
    "N": "#3050F8",
    "O": "#FF0D0D",
    "F": "#90E050",
    "P": "#FF8000",
    "S": "#FFFF30",
    "Cl": "#1FF01F",
    "Br": "#A62929",
    "I": "#940094",
    "B": "#FFB5B5",
    "Si": "#F0C8A0",
    "Pd": "#006985",
    "Pt": "#D0D0E0",
    "Ru": "#248F8F",
    "Rh": "#0A7D8C",
    "Ir": "#175487",
    "Fe": "#E06633",
    "Co": "#F090A0",
    "Ni": "#50D050",
    "Cu": "#C88033",
    "Zn": "#7D80B0",
    "Ag": "#C0C0C0",
    "Au": "#FFD123",
    "Hg": "#B8B8D0",
    "Li": "#CC80FF",
    "Na": "#AB5CF2",
    "K": "#8F40D4",
    "Mg": "#8AFF00",
    "Ca": "#3DFF00",
    "Al": "#BFA6A6",
    "Sn": "#668080",
    "Pb": "#575961",
}

FALLBACK_COVALENT_RADII: Dict[str, float] = {
    "H": 0.31,
    "B": 0.84,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "P": 1.07,
    "S": 1.05,
    "Cl": 1.02,
    "Br": 1.20,
    "I": 1.39,
    "Si": 1.11,
    "Pd": 1.39,
    "Pt": 1.36,
    "Ru": 1.46,
    "Rh": 1.42,
    "Ir": 1.41,
    "Fe": 1.32,
    "Co": 1.26,
    "Ni": 1.24,
    "Cu": 1.32,
    "Zn": 1.22,
    "Ag": 1.45,
    "Au": 1.36,
    "Hg": 1.32,
    "Li": 1.28,
    "Na": 1.66,
    "K": 2.03,
    "Mg": 1.41,
    "Ca": 1.76,
    "Al": 1.21,
    "Sn": 1.39,
    "Pb": 1.46,
}


@dataclass
class Atom:
    element: str
    xyz: np.ndarray


@dataclass
class RenderSettings:
    atom_scale: float = 0.42
    min_atom_radius: float = 0.16
    max_atom_radius: float = 0.55
    bond_radius: float = 0.075
    bond_tolerance: float = 1.20
    min_bond_length: float = 0.35
    max_bond_length: float = 3.40
    sphere_resolution: int = 64
    cylinder_resolution: int = 48
    split_colored_bonds: bool = True
    background: str = "white"
    show_axes: bool = False
    parallel_projection: bool = True
    antialiasing: str = "msaa"
    lighting_mode: str = "Stable Mercury-like"
    screenshot_width: int = 2400
    screenshot_height: int = 1800
    screenshot_scale: int = 2
    transparent_background: bool = False


def import_pyvista():
    try:
        import pyvista as pv
        return pv
    except Exception as exc:
        raise RuntimeError(
            "PyVista could not be imported.\n\n"
            "Try:\n\n"
            "    pip install --upgrade pyvista vtk numpy\n\n"
            f"Original error:\n{exc}"
        )


def get_periodictable():
    try:
        import periodictable as pt
        return pt
    except Exception:
        return None


def normalize_element_symbol(raw: str) -> str:
    raw = raw.strip().replace(",", "")
    if not raw:
        return raw
    return raw[0].upper() + raw[1:].lower()


def parse_xyz(path: str) -> Tuple[List[Atom], str]:
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(str(p))

    text = p.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if not lines:
        raise ValueError("The XYZ file is empty.")

    atoms: List[Atom] = []
    comment = ""

    expected_n: Optional[int] = None
    start = 0

    try:
        expected_n = int(lines[0].split()[0])
        comment = lines[1] if len(lines) > 1 else ""
        start = 2
    except Exception:
        expected_n = None
        comment = "No XYZ atom-count header detected; parsed as plain coordinate lines."
        start = 0

    for line in lines[start:]:
        parts = line.split()
        if len(parts) < 4:
            continue

        element = normalize_element_symbol(parts[0])

        try:
            x = float(parts[1])
            y = float(parts[2])
            z = float(parts[3])
        except ValueError:
            continue

        atoms.append(Atom(element=element, xyz=np.array([x, y, z], dtype=float)))

    if expected_n is not None and expected_n != len(atoms):
        raise ValueError(
            f"XYZ header says {expected_n} atoms, but {len(atoms)} coordinate lines were parsed."
        )

    if not atoms:
        raise ValueError("No valid atom coordinates were found.")

    return atoms, comment


def covalent_radius(element: str) -> float:
    element = normalize_element_symbol(element)

    pt = get_periodictable()
    if pt is not None:
        try:
            el = getattr(pt, element)
            r = getattr(el, "covalent_radius", None)
            if r is not None and float(r) > 0:
                return float(r)
        except Exception:
            pass

    return FALLBACK_COVALENT_RADII.get(element, 0.77)


def atom_color(element: str) -> str:
    return ELEMENT_COLORS.get(normalize_element_symbol(element), "#FF69B4")


def display_atom_radius(element: str, settings: RenderSettings) -> float:
    r = covalent_radius(element) * settings.atom_scale
    return float(np.clip(r, settings.min_atom_radius, settings.max_atom_radius))


def centered_atoms(atoms: List[Atom]) -> List[Atom]:
    coords = np.array([a.xyz for a in atoms], dtype=float)
    center = coords.mean(axis=0)

    return [
        Atom(element=a.element, xyz=np.array(a.xyz - center, dtype=float))
        for a in atoms
    ]


def molecule_extent(atoms: List[Atom]) -> float:
    coords = np.array([a.xyz for a in atoms], dtype=float)
    span = coords.max(axis=0) - coords.min(axis=0)
    extent = float(np.linalg.norm(span))
    return max(extent, 1.0)


def guess_bonds(atoms: List[Atom], settings: RenderSettings) -> List[Tuple[int, int, float]]:
    coords = np.array([a.xyz for a in atoms], dtype=float)
    radii = np.array([covalent_radius(a.element) for a in atoms], dtype=float)

    bonds: List[Tuple[int, int, float]] = []
    n = len(atoms)

    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.linalg.norm(coords[i] - coords[j]))

            if d < settings.min_bond_length:
                continue

            if d > settings.max_bond_length:
                continue

            cutoff = settings.bond_tolerance * (radii[i] + radii[j])

            if d <= cutoff:
                bonds.append((i, j, d))

    return bonds


def configure_quality(pv, plotter, settings: RenderSettings) -> None:
    try:
        pv.global_theme.multi_samples = 16
    except Exception:
        pass

    try:
        pv.global_theme.smooth_shading = True
    except Exception:
        pass

    try:
        plotter.set_background(settings.background)
    except Exception:
        plotter.set_background("white")

    try:
        if settings.antialiasing == "ssaa":
            plotter.enable_anti_aliasing("ssaa")
        elif settings.antialiasing == "fxaa":
            plotter.enable_anti_aliasing("fxaa")
        elif settings.antialiasing == "msaa":
            plotter.enable_anti_aliasing("msaa")
    except Exception:
        pass

    try:
        plotter.enable_depth_peeling(number_of_peels=8, occlusion_ratio=0.0)
    except Exception:
        pass

    try:
        plotter.renderer.SetTwoSidedLighting(True)
    except Exception:
        pass

    if settings.parallel_projection:
        try:
            plotter.enable_parallel_projection()
        except Exception:
            pass


def configure_lighting(pv, plotter, extent: float, settings: RenderSettings) -> None:
    try:
        plotter.remove_all_lights()
    except Exception:
        pass

    mode = settings.lighting_mode

    if mode == "Flat/no-black":
        return

    if mode == "Stable Mercury-like":
        light_specs = [
            ("headlight", None, 0.95),
            ("camera light", None, 0.45),
            ("scene light", (3.0 * extent, -4.0 * extent, 5.0 * extent), 0.35),
            ("scene light", (-3.0 * extent, 3.0 * extent, 4.0 * extent), 0.25),
        ]
    else:
        light_specs = [
            ("scene light", (3.0 * extent, -4.0 * extent, 5.0 * extent), 0.95),
            ("scene light", (-3.0 * extent, 3.0 * extent, 4.0 * extent), 0.55),
            ("scene light", (0.0, 5.0 * extent, 2.0 * extent), 0.35),
        ]

    for light_type, position, intensity in light_specs:
        try:
            if light_type in {"headlight", "camera light"}:
                light = pv.Light(light_type=light_type)
            else:
                light = pv.Light(
                    position=position,
                    focal_point=(0.0, 0.0, 0.0),
                    color="white",
                    light_type="scene light",
                )

            light.intensity = intensity
            plotter.add_light(light)
        except Exception:
            pass


def cylinder_between(pv, p1: np.ndarray, p2: np.ndarray, radius: float, resolution: int):
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)

    vector = p2 - p1
    length = float(np.linalg.norm(vector))

    if length <= 1e-8:
        return None

    center = (p1 + p2) / 2.0
    direction = vector / length

    return pv.Cylinder(
        center=tuple(center),
        direction=tuple(direction),
        radius=radius,
        height=length,
        resolution=resolution,
        capping=True,
    )


def add_mesh_safe(plotter, mesh, **kwargs) -> None:
    try:
        plotter.add_mesh(mesh, **kwargs)
    except TypeError:
        safe_kwargs = dict(kwargs)
        safe_kwargs.pop("pbr", None)
        safe_kwargs.pop("metallic", None)
        safe_kwargs.pop("roughness", None)
        plotter.add_mesh(mesh, **safe_kwargs)


def material_parameters(settings: RenderSettings) -> Dict[str, object]:
    if settings.lighting_mode == "Flat/no-black":
        return {
            "lighting": False,
            "smooth_shading": True,
        }

    if settings.lighting_mode == "Stable Mercury-like":
        return {
            "lighting": True,
            "smooth_shading": True,
            "ambient": 0.50,
            "diffuse": 0.62,
            "specular": 0.18,
            "specular_power": 20,
        }

    return {
        "lighting": True,
        "smooth_shading": True,
        "ambient": 0.36,
        "diffuse": 0.74,
        "specular": 0.28,
        "specular_power": 28,
    }


def add_atom(pv, plotter, atom: Atom, settings: RenderSettings) -> None:
    sphere = pv.Sphere(
        radius=display_atom_radius(atom.element, settings),
        center=tuple(atom.xyz),
        theta_resolution=settings.sphere_resolution,
        phi_resolution=settings.sphere_resolution,
    )

    params = material_parameters(settings)

    add_mesh_safe(
        plotter,
        sphere,
        color=atom_color(atom.element),
        **params,
    )


def add_bond(pv, plotter, atom1: Atom, atom2: Atom, settings: RenderSettings) -> None:
    p1 = atom1.xyz
    p2 = atom2.xyz

    if settings.split_colored_bonds:
        midpoint = (p1 + p2) / 2.0
        segments = [
            (p1, midpoint, atom_color(atom1.element)),
            (midpoint, p2, atom_color(atom2.element)),
        ]
    else:
        segments = [
            (p1, p2, "#A8A8A8"),
        ]

    params = material_parameters(settings)

    for a, b, color in segments:
        cylinder = cylinder_between(
            pv,
            a,
            b,
            radius=settings.bond_radius,
            resolution=settings.cylinder_resolution,
        )

        if cylinder is None:
            continue

        add_mesh_safe(
            plotter,
            cylinder,
            color=color,
            **params,
        )


def set_camera(plotter, extent: float) -> None:
    distance = 4.0 * extent

    plotter.camera_position = [
        (distance, -distance, 0.75 * distance),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
    ]

    try:
        plotter.reset_camera()
    except Exception:
        pass

    try:
        plotter.camera.parallel_scale = 0.62 * extent
    except Exception:
        pass

    try:
        plotter.camera.zoom(1.15)
    except Exception:
        pass


def screen_fraction_window_size(width: int, fallback_height: int, fraction: float = 0.80) -> Tuple[int, int]:
    try:
        root = getattr(tk, "_default_root", None)
        if root is not None and root.winfo_exists():
            return width, max(1, int(root.winfo_screenheight() * fraction))
        probe = tk.Tk()
        probe.withdraw()
        height = max(1, int(probe.winfo_screenheight() * fraction))
        probe.destroy()
        return width, height
    except Exception:
        return width, fallback_height


def keep_entry_end_visible(entry: tk.Entry, variable: Optional[tk.Variable] = None) -> tk.Entry:
    def show_end(*_args) -> None:
        try:
            entry.icursor("end")
            entry.xview_moveto(1.0)
        except tk.TclError:
            pass

    entry.bind("<Configure>", lambda _event: entry.after_idle(show_end), add="+")
    entry.bind("<FocusOut>", lambda _event: entry.after_idle(show_end), add="+")
    if variable is not None:
        variable.trace_add("write", lambda *_args: entry.after_idle(show_end))
    entry.after_idle(show_end)
    return entry


def build_plotter(atoms: List[Atom], settings: RenderSettings, off_screen: bool = False):
    pv = import_pyvista()

    atoms = centered_atoms(atoms)
    bonds = guess_bonds(atoms, settings)
    extent = molecule_extent(atoms)

    plotter = pv.Plotter(
        off_screen=off_screen,
        window_size=screen_fraction_window_size(1400, 1000) if not off_screen else (settings.screenshot_width, settings.screenshot_height),
        lighting="none",
    )

    configure_quality(pv, plotter, settings)
    configure_lighting(pv, plotter, extent, settings)

    for i, j, _distance in bonds:
        add_bond(pv, plotter, atoms[i], atoms[j], settings)

    for atom in atoms:
        add_atom(pv, plotter, atom, settings)

    try:
        text_color = "black" if settings.background.lower() == "white" else "white"
        plotter.add_text(
            f"{len(atoms)} atoms, {len(bonds)} guessed bonds",
            position="lower_left",
            font_size=10,
            color=text_color,
        )
    except Exception:
        pass

    set_camera(plotter, extent)

    return plotter, bonds


def open_pyvista_viewer(path: str, settings: RenderSettings) -> Tuple[int, int]:
    atoms, _comment = parse_xyz(path)
    plotter, bonds = build_plotter(atoms, settings, off_screen=False)

    try:
        plotter.show(title=f"XYZ Viewer - {Path(path).name}")
    except TypeError:
        plotter.show()

    return len(atoms), len(bonds)


def save_png(path: str, png_path: str, settings: RenderSettings) -> Tuple[int, int]:
    atoms, _comment = parse_xyz(path)
    plotter, bonds = build_plotter(atoms, settings, off_screen=True)

    try:
        try:
            plotter.screenshot(
                png_path,
                window_size=(settings.screenshot_width, settings.screenshot_height),
                scale=settings.screenshot_scale,
                transparent_background=settings.transparent_background,
            )
        except TypeError:
            plotter.screenshot(
                png_path,
                window_size=(settings.screenshot_width, settings.screenshot_height),
                transparent_background=settings.transparent_background,
            )
    finally:
        try:
            plotter.close()
        except Exception:
            pass

    return len(atoms), len(bonds)


class XYZViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("XYZ PyVista Ball-and-Stick Viewer")
        window_height = max(1, int(self.winfo_screenheight() * 0.80))
        self.geometry(f"820x{window_height}")
        self.minsize(780, min(500, window_height))

        self.xyz_path = tk.StringVar()

        self.atom_scale = tk.DoubleVar(value=0.42)
        self.bond_radius = tk.DoubleVar(value=0.075)
        self.bond_tolerance = tk.DoubleVar(value=1.20)
        self.max_bond_length = tk.DoubleVar(value=3.40)

        self.sphere_resolution = tk.IntVar(value=64)
        self.cylinder_resolution = tk.IntVar(value=48)

        self.split_colored_bonds = tk.BooleanVar(value=True)
        self.show_axes = tk.BooleanVar(value=False)
        self.parallel_projection = tk.BooleanVar(value=True)
        self.transparent_background = tk.BooleanVar(value=False)

        self.background_choice = tk.StringVar(value="white")
        self.antialiasing_choice = tk.StringVar(value="msaa")
        self.lighting_choice = tk.StringVar(value="Stable Mercury-like")

        self._build_ui()

    def _build_ui(self):
        host = ttk.Frame(self)
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        root = ttk.Frame(canvas)
        root_window = canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(root_window, width=e.width))
        root.configure(padding=10)

        file_box = ttk.LabelFrame(root, text="XYZ file")
        file_box.pack(fill="x", padx=5, pady=5)
        file_box.columnconfigure(0, weight=1)

        xyz_entry = ttk.Entry(file_box, textvariable=self.xyz_path)
        keep_entry_end_visible(xyz_entry, self.xyz_path)
        xyz_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)

        ttk.Button(file_box, text="Browse XYZ", command=self.browse_xyz).grid(
            row=0, column=1, padx=8, pady=8
        )

        settings_box = ttk.LabelFrame(root, text="Quality, lighting, and bond settings")
        settings_box.pack(fill="x", padx=5, pady=5)

        for i in range(4):
            settings_box.columnconfigure(i, weight=1)

        self._float_entry(settings_box, "Atom scale", self.atom_scale, 0, 0)
        self._float_entry(settings_box, "Bond radius", self.bond_radius, 0, 2)

        self._float_entry(settings_box, "Bond tolerance", self.bond_tolerance, 1, 0)
        self._float_entry(settings_box, "Max bond length / Å", self.max_bond_length, 1, 2)

        self._int_entry(settings_box, "Sphere resolution", self.sphere_resolution, 2, 0)
        self._int_entry(settings_box, "Cylinder resolution", self.cylinder_resolution, 2, 2)

        ttk.Label(settings_box, text="Background").grid(row=3, column=0, sticky="w", padx=8, pady=5)
        ttk.Combobox(
            settings_box,
            textvariable=self.background_choice,
            values=["white", "black", "gray20", "transparent"],
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="w", padx=8, pady=5)

        ttk.Label(settings_box, text="Antialiasing").grid(row=3, column=2, sticky="w", padx=8, pady=5)
        ttk.Combobox(
            settings_box,
            textvariable=self.antialiasing_choice,
            values=["msaa", "ssaa", "fxaa", "none"],
            state="readonly",
            width=18,
        ).grid(row=3, column=3, sticky="w", padx=8, pady=5)

        ttk.Label(settings_box, text="Lighting").grid(row=4, column=0, sticky="w", padx=8, pady=5)
        ttk.Combobox(
            settings_box,
            textvariable=self.lighting_choice,
            values=[
                "Stable Mercury-like",
                "Studio fixed lights",
                "Flat/no-black",
            ],
            state="readonly",
            width=22,
        ).grid(row=4, column=1, sticky="w", padx=8, pady=5)

        check_box = ttk.Frame(settings_box)
        check_box.grid(row=5, column=0, columnspan=4, sticky="w", padx=4, pady=5)

        ttk.Checkbutton(
            check_box,
            text="Split-colored bonds",
            variable=self.split_colored_bonds,
        ).pack(side="left", padx=6)

        ttk.Checkbutton(
            check_box,
            text="Show axes",
            variable=self.show_axes,
        ).pack(side="left", padx=6)

        ttk.Checkbutton(
            check_box,
            text="Orthographic projection",
            variable=self.parallel_projection,
        ).pack(side="left", padx=6)

        ttk.Checkbutton(
            check_box,
            text="Transparent PNG",
            variable=self.transparent_background,
        ).pack(side="left", padx=6)

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", padx=5, pady=8)

        ttk.Button(
            buttons,
            text="Open viewer",
            command=self.open_viewer,
        ).pack(side="left", padx=5)

        ttk.Button(
            buttons,
            text="Save high-resolution PNG",
            command=self.save_png,
        ).pack(side="left", padx=5)

        ttk.Button(
            buttons,
            text="Quit",
            command=self.destroy,
        ).pack(side="right", padx=5)

        status_box = ttk.LabelFrame(root, text="Status / errors")
        status_box.pack(fill="both", expand=True, padx=5, pady=5)

        self.status_text = tk.Text(status_box, height=8, wrap="word")
        self.status_text.pack(fill="both", expand=True, padx=6, pady=6)

        self.log(
            "Ready. Browse an XYZ file first.\n\n"
            "Default lighting is now 'Stable Mercury-like'.\n"
            "If any molecule still becomes too dark during rotation, choose 'Flat/no-black'."
        )

    def _float_entry(self, parent, label, variable, row, col):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=8, pady=5)
        ttk.Entry(parent, textvariable=variable, width=12).grid(
            row=row, column=col + 1, sticky="w", padx=8, pady=5
        )

    def _int_entry(self, parent, label, variable, row, col):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=8, pady=5)
        ttk.Entry(parent, textvariable=variable, width=12).grid(
            row=row, column=col + 1, sticky="w", padx=8, pady=5
        )

    def log(self, text: str):
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")
        self.update_idletasks()

    def browse_xyz(self):
        path = filedialog.askopenfilename(
            title="Select XYZ file",
            filetypes=[
                ("XYZ files", "*.xyz"),
                ("All files", "*.*"),
            ],
        )

        if not path:
            return

        self.xyz_path.set(path)

        try:
            atoms, comment = parse_xyz(path)
            settings = self.current_settings()
            bonds = guess_bonds(centered_atoms(atoms), settings)

            self.log(
                f"Loaded:\n{path}\n\n"
                f"Atoms: {len(atoms)}\n"
                f"Guessed bonds with current settings: {len(bonds)}\n"
                f"Comment: {comment or '(none)'}"
            )
        except Exception as exc:
            self.log(f"XYZ parsing error:\n{exc}")
            messagebox.showerror("XYZ parsing error", str(exc))

    def current_settings(self) -> RenderSettings:
        background = self.background_choice.get()
        transparent = bool(self.transparent_background.get())

        if background == "transparent":
            background = "white"
            transparent = True

        antialiasing = self.antialiasing_choice.get()
        if antialiasing not in {"msaa", "ssaa", "fxaa", "none"}:
            antialiasing = "msaa"

        lighting_mode = self.lighting_choice.get()
        if lighting_mode not in {"Stable Mercury-like", "Studio fixed lights", "Flat/no-black"}:
            lighting_mode = "Stable Mercury-like"

        return RenderSettings(
            atom_scale=float(self.atom_scale.get()),
            bond_radius=float(self.bond_radius.get()),
            bond_tolerance=float(self.bond_tolerance.get()),
            max_bond_length=float(self.max_bond_length.get()),
            sphere_resolution=int(self.sphere_resolution.get()),
            cylinder_resolution=int(self.cylinder_resolution.get()),
            split_colored_bonds=bool(self.split_colored_bonds.get()),
            background=background,
            show_axes=bool(self.show_axes.get()),
            parallel_projection=bool(self.parallel_projection.get()),
            antialiasing=antialiasing,
            lighting_mode=lighting_mode,
            transparent_background=transparent,
        )

    def require_xyz(self) -> Optional[str]:
        path = self.xyz_path.get().strip()

        if not path:
            messagebox.showwarning("No XYZ file", "Select an XYZ file first.")
            return None

        if not Path(path).exists():
            messagebox.showerror("File not found", path)
            return None

        return path

    def open_viewer(self):
        path = self.require_xyz()
        if path is None:
            return

        try:
            settings = self.current_settings()
            self.log("Opening PyVista viewer...")
            atom_count, bond_count = open_pyvista_viewer(path, settings)
            self.log(
                f"Viewer closed.\n\n"
                f"File: {path}\n"
                f"Atoms: {atom_count}\n"
                f"Guessed bonds: {bond_count}\n"
                f"Lighting mode: {settings.lighting_mode}"
            )
        except Exception as exc:
            full = traceback.format_exc()
            self.log(full)
            messagebox.showerror("PyVista viewer error", str(exc))

    def save_png(self):
        path = self.require_xyz()
        if path is None:
            return

        default_name = Path(path).with_suffix(".png").name

        png_path = filedialog.asksaveasfilename(
            title="Save high-resolution PNG",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[
                ("PNG image", "*.png"),
                ("All files", "*.*"),
            ],
        )

        if not png_path:
            return

        try:
            settings = self.current_settings()
            self.log("Saving PNG...")
            atom_count, bond_count = save_png(path, png_path, settings)
            self.log(
                f"Saved:\n{png_path}\n\n"
                f"Atoms: {atom_count}\n"
                f"Guessed bonds: {bond_count}\n"
                f"Lighting mode: {settings.lighting_mode}"
            )
            messagebox.showinfo("Saved", f"Saved:\n{png_path}")
        except Exception as exc:
            full = traceback.format_exc()
            self.log(full)
            messagebox.showerror("PNG export error", str(exc))


def main():
    app = XYZViewerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
