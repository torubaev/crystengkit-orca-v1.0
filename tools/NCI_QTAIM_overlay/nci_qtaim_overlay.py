#!/usr/bin/env python3
"""
NCI + QTAIM overlay viewer.

This standalone helper assumes the heavy calculations are already finished:

- NCI cube files already exist, normally RDG and sign(lambda2)rho cubes from NCI Plotter / Multiwfn.
- QTAIM critical-point output already exists, normally a Multiwfn CP text/log/PDB file.
- QTAIM bond-path output may exist, preferably Multiwfn paths.pdb.

The script combines these layers in one PyVista scene:

- molecule
- NCI RDG isosurface colored by sign(lambda2)rho
- QTAIM BCPs
- QTAIM bond paths
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import fnmatch
import sys
import tkinter as tk
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import numpy as np

try:
    import pyvista as pv
except Exception as exc:
    raise RuntimeError("PyVista is required. Install with: pip install pyvista vtk") from exc


TOOLS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TOOLS_ROOT.parent
NCI_MODULE_PATH = TOOLS_ROOT / "NCI_plot" / "nci_plotter.py"
QTAIM_GRAPHICS_SETTINGS_PATH = Path.home() / ".qtaim_graphics_settings.json"
QTAIM_MODULE_CANDIDATES = [
    TOOLS_ROOT / "qtaim-cp" / "qtaim.py",
    TOOLS_ROOT / "qtaim-cp" / "qtaim_cp.py",
    APP_ROOT / "tools" / "qtaim-cp" / "qtaim.py",
]


def load_qtaim_graphics_settings() -> dict:
    try:
        data = json.loads(QTAIM_GRAPHICS_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def bool_setting(settings: dict, key: str, default: bool) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def float_setting(settings: dict, key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except Exception:
        return default


def str_setting(settings: dict, key: str, default: str) -> str:
    value = str(settings.get(key, default))
    return value if value else default
MAX_SEARCH_DEPTH = 3
MAX_SEARCH_FILES = 2500
SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}

ELEMENT_SYMBOLS = {
    1: "H",
    2: "He",
    3: "Li",
    4: "Be",
    5: "B",
    6: "C",
    7: "N",
    8: "O",
    9: "F",
    10: "Ne",
    11: "Na",
    12: "Mg",
    13: "Al",
    14: "Si",
    15: "P",
    16: "S",
    17: "Cl",
    18: "Ar",
    19: "K",
    20: "Ca",
    21: "Sc",
    22: "Ti",
    23: "V",
    24: "Cr",
    25: "Mn",
    26: "Fe",
    27: "Co",
    28: "Ni",
    29: "Cu",
    30: "Zn",
    31: "Ga",
    32: "Ge",
    33: "As",
    34: "Se",
    35: "Br",
    36: "Kr",
    37: "Rb",
    38: "Sr",
    39: "Y",
    40: "Zr",
    41: "Nb",
    42: "Mo",
    43: "Tc",
    44: "Ru",
    45: "Rh",
    46: "Pd",
    47: "Ag",
    48: "Cd",
    49: "In",
    50: "Sn",
    51: "Sb",
    52: "Te",
    53: "I",
    54: "Xe",
    55: "Cs",
    56: "Ba",
    57: "La",
    58: "Ce",
    59: "Pr",
    60: "Nd",
    61: "Pm",
    62: "Sm",
    63: "Eu",
    64: "Gd",
    65: "Tb",
    66: "Dy",
    67: "Ho",
    68: "Er",
    69: "Tm",
    70: "Yb",
    71: "Lu",
    72: "Hf",
    73: "Ta",
    74: "W",
    75: "Re",
    76: "Os",
    77: "Ir",
    78: "Pt",
    79: "Au",
    80: "Hg",
    81: "Tl",
    82: "Pb",
    83: "Bi",
    84: "Po",
    85: "At",
    86: "Rn",
}

BUILDER_COVALENT_RADII = {
    "H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39, "Si": 1.11,
    "Pd": 1.39, "Pt": 1.36, "Ru": 1.46, "Rh": 1.42, "Ir": 1.41,
    "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ag": 1.45, "Au": 1.36, "Hg": 1.32, "Li": 1.28, "Na": 1.66, "K": 2.03,
    "Mg": 1.41, "Ca": 1.76, "Al": 1.21, "Sn": 1.39, "Pb": 1.46,
    "Se": 1.20, "Te": 1.38, "Cd": 1.44, "Ga": 1.22, "Ge": 1.20, "As": 1.19,
    "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.39,
}

BUILDER_ATOM_COLORS = {
    "H": "#F2F2F2", "C": "#5A5A5A", "N": "#3050F8", "O": "#FF0D0D",
    "F": "#90E050", "P": "#FF8000", "S": "#FFFF30", "Cl": "#1FF01F",
    "Br": "#A62929", "I": "#940094", "B": "#FFB5B5", "Si": "#F0C8A0",
    "Pd": "#006985", "Pt": "#D0D0E0", "Ru": "#248F8F", "Rh": "#0A7D8C",
    "Ir": "#175487", "Fe": "#E06633", "Co": "#F090A0", "Ni": "#50D050",
    "Cu": "#C88033", "Zn": "#7D80B0", "Ag": "#C0C0C0", "Au": "#FFD123",
    "Hg": "#B8B8D0", "Li": "#CC80FF", "Na": "#AB5CF2", "K": "#8F40D4",
    "Mg": "#8AFF00", "Ca": "#3DFF00", "Al": "#BFA6A6", "Sn": "#668080",
    "Pb": "#575961",
}

CP_COLORS = {
    "(3,-3)": "red",       # nuclear CP
    "(3,-1)": "orange",    # bond CP
    "(3,+1)": "cyan",      # ring CP
    "(3,1)": "cyan",
    "(3,+3)": "magenta",   # cage CP
    "(3,3)": "magenta",
    "unknown": "white",
}

CP_LABELS = {
    "(3,-3)": "NCP",
    "(3,-1)": "BCP",
    "(3,+1)": "RCP",
    "(3,1)": "RCP",
    "(3,+3)": "CCP",
    "(3,3)": "CCP",
    "unknown": "CP",
}


@dataclass
class OverlayInputs:
    rdg_cube: Optional[Path] = None
    signrho_cube: Optional[Path] = None
    wavefunction_file: Optional[Path] = None
    qtaim_cp_file: Optional[Path] = None
    qtaim_path_file: Optional[Path] = None


@dataclass
class FolderInspection:
    inputs: OverlayInputs
    missing: list[str]
    instructions: list[str]


def import_module_from_path(module_name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(str(path))
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import module from: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_nci_module():
    return import_module_from_path("crystengkit_nci_plotter", NCI_MODULE_PATH)


def load_qtaim_module():
    for path in QTAIM_MODULE_CANDIDATES:
        if path.is_file():
            return import_module_from_path("crystengkit_qtaim_cp", path)
    raise FileNotFoundError(
        "Could not find a QTAIM parser script. Expected one of:\n"
        + "\n".join(str(p) for p in QTAIM_MODULE_CANDIDATES)
    )


def iter_candidate_files(folder: Path, max_depth: int = MAX_SEARCH_DEPTH, max_files: int = MAX_SEARCH_FILES):
    seen = set()
    checked = 0
    queue: list[tuple[Path, int]] = [(folder, 0)]

    while queue:
        current, depth = queue.pop(0)
        try:
            children = list(current.iterdir())
        except Exception:
            continue

        for child in children:
            try:
                if child.is_dir():
                    if depth < max_depth and child.name not in SKIP_DIR_NAMES:
                        queue.append((child, depth + 1))
                    continue
                if not child.is_file():
                    continue
            except Exception:
                continue

            key = str(child.absolute()).lower()
            if key in seen:
                continue
            seen.add(key)
            checked += 1
            if checked > max_files:
                return
            yield child


def iter_output_files(folder: Path, patterns: list[str]):
    lowered_patterns = [p.lower() for p in patterns]
    for path in iter_candidate_files(folder):
        name = path.name.lower()
        if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in lowered_patterns):
            yield path


def detect_nci_cubes(folder: Path) -> tuple[Optional[Path], Optional[Path]]:
    cube_files = list(iter_output_files(folder, ["*.cube", "*.cub"]))
    if not cube_files:
        return None, None

    by_name = {path.name.lower(): path for path in cube_files}
    if "func1.cub" in by_name and "func2.cub" in by_name:
        # Multiwfn NCI convention used in the NCI Plotter: func1 = sign(lambda2)rho, func2 = RDG
        return by_name["func2.cub"], by_name["func1.cub"]

    rdg_candidates = []
    signrho_candidates = []
    for path in cube_files:
        name = path.name.lower()
        if "rdg" in name or "reduced" in name or "grad" in name:
            rdg_candidates.append(path)
        if "sign" in name or "lambda" in name or "lambda2" in name or "rho" in name:
            signrho_candidates.append(path)

    rdg = rdg_candidates[0] if rdg_candidates else None
    signrho = signrho_candidates[0] if signrho_candidates else None
    if rdg and signrho and rdg.resolve() == signrho.resolve():
        signrho = None
    return rdg, signrho


def find_qtaim_cp_file(folder: Path, stem: str) -> Optional[Path]:
    preferred_names = {
        "cpprop.txt",
        "cp.txt",
        "cps.pdb",
        "cp.pdb",
        f"{stem.lower()}.multiwfn_qtaim.log",
        f"{stem.lower()}_cpprop.txt",
    }
    for candidate in iter_output_files(folder, ["*.txt", "*.log", "*.out", "*.pdb"]):
        if candidate.name.lower() in preferred_names:
            return candidate

    patterns = ["*qtaim*.log", "*QTAIM*.log", "*CP*.txt", "*cp*.txt", "*CP*.pdb", "*cp*.pdb", "*critical*.txt", "*critical*.log"]
    for pattern in patterns:
        for candidate in sorted(iter_output_files(folder, [pattern])):
            if candidate.is_file():
                return candidate
    return None


def find_qtaim_path_file(folder: Path, stem: str) -> Optional[Path]:
    preferred_names = {
        "paths.pdb",
        "paths.txt",
        "path.pdb",
        "path.txt",
        "bondpaths.pdb",
        "bondpaths.txt",
        f"{stem.lower()}_paths.pdb",
        f"{stem.lower()}_paths.txt",
        f"{stem.lower()}.paths.pdb",
        f"{stem.lower()}.paths.txt",
    }
    for candidate in iter_output_files(folder, ["*.pdb", "*.txt", "*.log", "*.out"]):
        if candidate.name.lower() in preferred_names:
            return candidate

    patterns = ["*path*.pdb", "*Path*.pdb", "*path*.txt", "*Path*.txt", "*bondpath*.pdb", "*BondPath*.pdb", "*bondpath*.txt", "*BondPath*.txt"]
    for pattern in patterns:
        for candidate in sorted(iter_output_files(folder, [pattern])):
            if candidate.is_file():
                return candidate
    return None


def inspect_wavefunction_folder(wavefunction_file: Path) -> FolderInspection:
    wavefunction_file = wavefunction_file.resolve()
    folder = wavefunction_file.parent
    rdg_cube, signrho_cube = detect_nci_cubes(folder)
    qtaim_cp_file = find_qtaim_cp_file(folder, wavefunction_file.stem)
    qtaim_path_file = find_qtaim_path_file(folder, wavefunction_file.stem)

    inputs = OverlayInputs(
        rdg_cube=rdg_cube,
        signrho_cube=signrho_cube,
        wavefunction_file=wavefunction_file,
        qtaim_cp_file=qtaim_cp_file,
        qtaim_path_file=qtaim_path_file,
    )

    missing: list[str] = []
    instructions: list[str] = []

    if rdg_cube is None or signrho_cube is None:
        missing.append("NCI cube files: RDG cube and sign(lambda2)rho cube")
        instructions.append(
            "Run NCI Plotter for this .wfn/.wfx file and generate the NCI data. "
            "The selected .wfn/.wfx folder, or one of its subfolders, should contain the RDG cube and sign(lambda2)rho cube, commonly func2.cub and func1.cub."
        )

    return FolderInspection(inputs=inputs, missing=missing, instructions=instructions)


def format_inspection_message(wavefunction_file: Path, inspection: FolderInspection) -> str:
    lines = [
        "The overlay cannot be opened yet because some ready NCI/QTAIM output files are missing.",
        "",
        f"Selected wavefunction file:",
        f"{wavefunction_file}",
        "",
        "Missing:",
    ]
    lines.extend(f"- {item}" for item in inspection.missing)
    lines.extend(["", "What to run first:"])
    lines.extend(f"- {item}" for item in inspection.instructions)
    lines.extend(
        [
            "",
            "After these files are generated in the same folder, run this overlay viewer again and select the same .wfn/.wfx file.",
        ]
    )
    return "\n".join(lines)


def make_nci_grid(rdg_cube, signrho_cube):
    if rdg_cube.shape != signrho_cube.shape:
        raise ValueError(f"Cube shape mismatch: RDG {rdg_cube.shape}, sign(lambda2)rho {signrho_cube.shape}")

    spacing = np.array([np.linalg.norm(axis) for axis in rdg_cube.axes], dtype=float)
    if np.any(spacing <= 0):
        raise ValueError("Invalid cube spacing.")

    grid = pv.ImageData()
    grid.dimensions = np.array(rdg_cube.shape) + 1
    grid.origin = tuple(float(x) for x in rdg_cube.origin)
    grid.spacing = tuple(float(x) for x in spacing)
    grid.cell_data["RDG"] = rdg_cube.values.ravel(order="F")
    grid.cell_data["sign(lambda2)rho"] = signrho_cube.values.ravel(order="F")
    return grid.cell_data_to_point_data()


def screen_fraction_window_size(width: int, fallback_height: int, fraction: float = 0.80):
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


def cylinder_between(p1, p2, radius: float, color: str, opacity: float = 1.0):
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    direction = p2 - p1
    length = float(np.linalg.norm(direction))
    if length <= 1e-8:
        return None
    return pv.Cylinder(
        center=tuple((p1 + p2) / 2.0),
        direction=tuple(direction / length),
        radius=radius,
        height=length,
        resolution=48,
        capping=True,
    )


def add_mesh_material(plotter, mesh, color: str, opacity: float = 1.0):
    plotter.add_mesh(
        mesh,
        color=color,
        opacity=opacity,
        smooth_shading=True,
        ambient=0.50,
        diffuse=0.62,
        specular=0.18,
        specular_power=20,
    )


def add_molecule(plotter, nci_module, atom_numbers, atom_coords, show_bonds=True, atom_scale=1.0, bond_radius=0.075):
    atom_colors = getattr(nci_module, "ATOM_COLORS", {})
    covalent_radii = getattr(nci_module, "COVALENT_RADII", {})

    def atom_color(z: int) -> str:
        symbol = ELEMENT_SYMBOLS.get(int(z), "")
        return BUILDER_ATOM_COLORS.get(symbol, atom_colors.get(int(z), "#FF69B4"))

    def covalent_radius(z: int) -> float:
        symbol = ELEMENT_SYMBOLS.get(int(z), "")
        return float(BUILDER_COVALENT_RADII.get(symbol, covalent_radii.get(int(z), 0.77)))

    if show_bonds:
        for i in range(len(atom_numbers)):
            for j in range(i + 1, len(atom_numbers)):
                dist = float(np.linalg.norm(atom_coords[i] - atom_coords[j]))
                cutoff = 1.20 * (covalent_radius(atom_numbers[i]) + covalent_radius(atom_numbers[j]))
                if not (0.35 < dist < cutoff):
                    continue
                p1 = np.asarray(atom_coords[i], dtype=float)
                p2 = np.asarray(atom_coords[j], dtype=float)
                mid = (p1 + p2) / 2.0
                for a, b, color in ((p1, mid, atom_color(atom_numbers[i])), (mid, p2, atom_color(atom_numbers[j]))):
                    cyl = cylinder_between(a, b, radius=bond_radius, color=color)
                    if cyl is not None:
                        add_mesh_material(plotter, cyl, color=color, opacity=1.0)

    for z, coord in zip(atom_numbers, atom_coords):
        radius = float(np.clip(covalent_radius(int(z)) * 0.42 * atom_scale, 0.16, 0.55))
        sphere = pv.Sphere(
            radius=radius,
            center=tuple(float(x) for x in coord),
            theta_resolution=64,
            phi_resolution=64,
        )
        add_mesh_material(plotter, sphere, color=atom_color(int(z)), opacity=1.0)


def normalize_cp_type(qtaim_module, cp_type: str) -> str:
    normalizer = getattr(qtaim_module, "normalize_cp_type", None)
    if callable(normalizer):
        return normalizer(cp_type)
    text = str(cp_type).replace(" ", "")
    if "3,-1" in text or "BCP" in text.upper():
        return "(3,-1)"
    if "3,+1" in text or "3,1" in text or "RCP" in text.upper():
        return "(3,+1)"
    if "3,+3" in text or "3,3" in text or "CCP" in text.upper():
        return "(3,+3)"
    if "3,-3" in text or "NCP" in text.upper():
        return "(3,-3)"
    return "unknown"


def add_qtaim_bcps(
    plotter,
    qtaim_module,
    cps,
    cp_radius: float = 0.16,
    show_labels: bool = True,
    show_ncp: bool = False,
    show_bcp: bool = True,
    show_rcp: bool = False,
    show_ccp: bool = False,
    show_unknown: bool = False,
):
    """
    Add QTAIM critical points to the plotter, filtering by type based on visibility flags.
    
    Args:
        plotter: PyVista plotter instance
        qtaim_module: QTAIM module for CP type normalization
        cps: List of CriticalPoint objects
        cp_radius: Radius of CP spheres
        show_labels: Whether to show CP labels
        show_ncp: Show nuclear critical points (3,-3)
        show_bcp: Show bond critical points (3,-1)
        show_rcp: Show ring critical points (3,+1)
        show_ccp: Show cage critical points (3,+3)
        show_unknown: Show unclassified critical points
    
    Returns:
        Count of critical points added
    """
    # Build set of visible CP types
    visible_types = set()
    if show_ncp:
        visible_types.add("(3,-3)")
    if show_bcp:
        visible_types.add("(3,-1)")
    if show_rcp:
        visible_types.add("(3,+1)")
    if show_ccp:
        visible_types.add("(3,+3)")
    if show_unknown:
        visible_types.add("unknown")
    
    if not visible_types:
        # No CP types enabled
        return 0
    
    label_points = []
    label_text = []
    count = 0
    for cp in cps:
        normalized_type = normalize_cp_type(qtaim_module, cp.cp_type)
        if normalized_type not in visible_types:
            continue
        
        center = (float(cp.x), float(cp.y), float(cp.z))
        sphere = pv.Sphere(radius=cp_radius, center=center, theta_resolution=48, phi_resolution=48)
        
        # Color based on CP type
        color = CP_COLORS.get(normalized_type, "white")
        
        plotter.add_mesh(
            sphere,
            color=color,
            smooth_shading=True,
            ambient=0.75,
            diffuse=0.85,
            specular=0.45,
        )
        count += 1
        if show_labels:
            label_points.append(center)
            cp_label = CP_LABELS.get(normalized_type, "CP")
            label_text.append(f"{cp_label}{cp.index}")

    if show_labels and label_points:
        plotter.add_point_labels(
            label_points,
            label_text,
            font_size=13,
            text_color="black",
            shape_color="white",
            shape_opacity=0.55,
            always_visible=True,
        )
    return count


def add_bond_paths(plotter, bond_paths, radius: float = 0.055, color: str = "yellow"):
    count = 0
    for bp in bond_paths:
        pts = np.asarray(bp.points, dtype=float)
        if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] != 3:
            continue
        actor = plotter.add_lines(pts, color=color, width=6, connected=True)
        try:
            prop = actor.GetProperty()
            prop.SetLighting(False)
            prop.SetRenderLinesAsTubes(False)
            prop.SetLineWidth(6)
            prop.SetColor(1.0, 1.0, 0.0)
        except Exception:
            pass
        count += 1
    return count


def atom_symbol_from_number(atomic_number):
    try:
        return ELEMENT_SYMBOLS.get(int(atomic_number), "")
    except Exception:
        return ""


def normalized_symbol(symbol):
    symbol = str(symbol or "").strip()
    if not symbol:
        return ""
    return symbol[0].upper() + symbol[1:].lower()


def median_pair_distance_scale(source_coords, target_coords):
    ratios = []
    for i in range(len(source_coords)):
        for j in range(i + 1, len(source_coords)):
            sd = float(np.linalg.norm(source_coords[i] - source_coords[j]))
            td = float(np.linalg.norm(target_coords[i] - target_coords[j]))
            if sd > 1e-6 and td > 1e-6:
                ratios.append(td / sd)
    return float(np.median(ratios)) if ratios else 1.0


def greedy_symbol_matches(source_coords, target_coords, source_symbols, target_symbols):
    if Counter(source_symbols) != Counter(target_symbols):
        return None

    scale = median_pair_distance_scale(source_coords, target_coords)
    source_center = np.mean(source_coords, axis=0)
    target_center = np.mean(target_coords, axis=0)
    source_guess = (source_coords - source_center) * scale + target_center

    source_indices = []
    target_indices = []
    for symbol in sorted(set(target_symbols)):
        available = [i for i, item in enumerate(source_symbols) if item == symbol]
        for target_index in [i for i, item in enumerate(target_symbols) if item == symbol]:
            best = min(available, key=lambda i: float(np.linalg.norm(source_guess[i] - target_coords[target_index])))
            available.remove(best)
            source_indices.append(best)
            target_indices.append(target_index)

    return source_coords[source_indices], target_coords[target_indices]


def make_kabsch_transform(source_coords, target_coords):
    source_center = np.mean(source_coords, axis=0)
    target_center = np.mean(target_coords, axis=0)
    source_zero = source_coords - source_center
    target_zero = target_coords - target_center
    denominator = float(np.sum(source_zero * source_zero))
    if denominator < 1e-12:
        return None, math.inf, 1.0

    covariance = source_zero.T @ target_zero
    u_matrix, singular_values, vh_matrix = np.linalg.svd(covariance)
    rotation = vh_matrix.T @ u_matrix.T
    if np.linalg.det(rotation) < 0:
        vh_matrix[-1, :] *= -1
        rotation = vh_matrix.T @ u_matrix.T

    scale = float(np.sum(singular_values) / denominator)
    aligned = (source_coords - source_center) @ rotation * scale + target_center
    rmsd = float(np.sqrt(np.mean(np.sum((aligned - target_coords) ** 2, axis=1))))

    def transform_point(xyz):
        point = np.asarray(xyz, dtype=float)
        transformed = (point - source_center) @ rotation * scale + target_center
        return tuple(float(v) for v in transformed)

    return transform_point, rmsd, scale


def compute_qtaim_to_nci_transform(qtaim_atoms, nci_atom_coords, nci_atom_numbers=None):
    if not qtaim_atoms or len(qtaim_atoms) != len(nci_atom_coords):
        return None

    q_coords = np.array([(a.x, a.y, a.z) for a in qtaim_atoms], dtype=float)
    n_coords = np.array(nci_atom_coords, dtype=float)
    if q_coords.shape != n_coords.shape or q_coords.ndim != 2 or q_coords.shape[1] != 3:
        return None

    q_symbols = [normalized_symbol(getattr(atom, "symbol", "")) for atom in qtaim_atoms]
    n_symbols = [atom_symbol_from_number(number) for number in (nci_atom_numbers or [])]

    source_coords = q_coords
    target_coords = n_coords
    if len(n_symbols) == len(q_symbols) and all(q_symbols) and all(n_symbols):
        if q_symbols != n_symbols:
            matched = greedy_symbol_matches(q_coords, n_coords, q_symbols, n_symbols)
            if matched is not None:
                source_coords, target_coords = matched

    transform_point, rmsd, scale = make_kabsch_transform(source_coords, target_coords)
    if transform_point is None:
        return None

    molecule_extent = float(np.linalg.norm(np.max(n_coords, axis=0) - np.min(n_coords, axis=0)))
    acceptable_rmsd = max(0.25, min(1.0, 0.08 * max(molecule_extent, 1.0)))
    if rmsd > acceptable_rmsd:
        print(
            "QTAIM/NCI atom alignment was not reliable "
            f"(RMSD {rmsd:.3f} A, scale {scale:.4f}); using original QTAIM coordinates."
        )
        return None

    print(f"QTAIM/NCI atom alignment RMSD: {rmsd:.3f} A; scale: {scale:.4f}")
    return transform_point


def transform_cps(cps, transform_point):
    if transform_point is None:
        return cps
    transformed = []
    for cp in cps:
        x, y, z = transform_point((cp.x, cp.y, cp.z))
        cp_type = type(cp)
        try:
            transformed.append(cp_type(cp.index, cp.cp_type, x, y, z, cp.rho, cp.laplacian, cp.ellipticity))
        except TypeError:
            cp.x, cp.y, cp.z = x, y, z
            transformed.append(cp)
    return transformed


def transform_bond_paths(bond_paths, transform_point):
    if transform_point is None:
        return bond_paths
    transformed = []
    for bp in bond_paths:
        points = [transform_point(point) for point in bp.points]
        bp_type = type(bp)
        try:
            transformed.append(bp_type(bp.index, points, bp.bcp_index, bp.atom1_index, bp.atom2_index, bp.source))
        except TypeError:
            bp.points = points
            transformed.append(bp)
    return transformed


def molecule_bounds(atom_coords, margin=None):
    coords = np.asarray(atom_coords, dtype=float)
    if coords.ndim != 2 or coords.shape[0] == 0 or coords.shape[1] != 3:
        return None
    lower = np.min(coords, axis=0)
    upper = np.max(coords, axis=0)
    extent = float(np.linalg.norm(upper - lower))
    pad = float(margin if margin is not None else max(1.5, 0.20 * max(extent, 1.0)))
    return lower - pad, upper + pad


def point_in_bounds(point, bounds):
    if bounds is None:
        return True
    lower, upper = bounds
    xyz = np.asarray(point, dtype=float)
    return bool(np.all(xyz >= lower) and np.all(xyz <= upper))


def filter_cps_to_molecule(cps, atom_coords):
    bounds = molecule_bounds(atom_coords)
    return [cp for cp in cps if point_in_bounds((cp.x, cp.y, cp.z), bounds)]


def filter_paths_to_molecule(bond_paths, atom_coords):
    bounds = molecule_bounds(atom_coords)
    if bounds is None:
        return bond_paths
    filtered = []
    for path in bond_paths:
        if not path.points:
            continue
        local_points = sum(1 for point in path.points if point_in_bounds(point, bounds))
        local_fraction = local_points / max(len(path.points), 1)
        if local_fraction >= 0.60:
            filtered.append(path)
    return filtered


def choose_coordinate_set(raw_items, transformed_items, atom_coords, filter_func, label):
    raw_near = filter_func(raw_items, atom_coords)
    transformed_near = filter_func(transformed_items, atom_coords)

    raw_score = len(raw_near)
    transformed_score = len(transformed_near)
    if raw_score >= transformed_score:
        if transformed_score and raw_score != transformed_score:
            print(f"Using raw QTAIM {label} coordinates; transformed set had fewer molecule-local items.")
        return raw_near, False

    print(f"Using aligned QTAIM {label} coordinates.")
    return transformed_near, True


def build_overlay(
    inputs: OverlayInputs,
    rdg_isovalue: float = 0.50,
    nci_opacity: float = 0.55,
    clim_min: float = -0.05,
    clim_max: float = 0.05,
    colormap: str = "rainbow",
    show_molecule: bool = True,
    show_nci: bool = True,
    show_cps: bool = True,
    show_paths: bool = True,
    show_labels: bool = True,
    background: str = "white",
    window_size: Optional[tuple[int, int]] = None,
    # QTAIM graphics settings
    show_ncp: bool = False,
    show_bcp: bool = True,
    show_rcp: bool = False,
    show_ccp: bool = False,
    show_unknown: bool = False,
    cp_scale: float = 0.14,
    atom_scale: float = 0.38,
    bond_radius: float = 0.075,
    show_covalent_bonds: bool = True,
    show_bond_paths: bool = True,
) -> None:
    nci_module = load_nci_module()
    qtaim_module = load_qtaim_module()

    if inputs.rdg_cube is None or inputs.signrho_cube is None:
        raise ValueError("Both RDG and sign(lambda2)rho cube files are required.")

    rdg_cube = nci_module.CubeParser.parse(Path(inputs.rdg_cube))
    signrho_cube = nci_module.CubeParser.parse(Path(inputs.signrho_cube))

    plotter = pv.Plotter(window_size=window_size or screen_fraction_window_size(1400, 950))
    plotter.set_background(background)

    nci_surface_count = 0
    if show_nci:
        grid = make_nci_grid(rdg_cube, signrho_cube)
        surface = grid.contour(isosurfaces=[float(rdg_isovalue)], scalars="RDG")
        sampled = surface.sample(grid)
        if sampled.n_points == 0:
            raise RuntimeError(f"No NCI surface found at RDG isovalue {rdg_isovalue}.")
        plotter.add_mesh(
            sampled,
            scalars="sign(lambda2)rho",
            cmap=colormap,
            clim=[float(clim_min), float(clim_max)],
            opacity=float(nci_opacity),
            smooth_shading=False,
            show_scalar_bar=True,
            scalar_bar_args={
                "title": "sign(lambda2)rho",
                "vertical": True,
                "position_x": 0.86,
                "position_y": 0.15,
                "height": 0.70,
                "width": 0.08,
            },
        )
        nci_surface_count = 1

    if show_molecule:
        add_molecule(plotter, nci_module, rdg_cube.atom_numbers, rdg_cube.atom_coords, show_bonds=show_covalent_bonds, atom_scale=atom_scale, bond_radius=bond_radius)

    cp_count = 0
    path_count = 0
    cps = []
    qtaim_transform = None
    use_qtaim_transform = False
    if inputs.wavefunction_file and Path(inputs.wavefunction_file).is_file():
        try:
            qtaim_atoms = qtaim_module.read_atoms(Path(inputs.wavefunction_file))
            qtaim_transform = compute_qtaim_to_nci_transform(
                qtaim_atoms,
                rdg_cube.atom_coords,
                rdg_cube.atom_numbers,
            )
        except Exception:
            qtaim_transform = None

    if inputs.qtaim_cp_file and Path(inputs.qtaim_cp_file).is_file():
        cp_path = Path(inputs.qtaim_cp_file)
        raw_cps = qtaim_module.parse_critical_points_file(cp_path)
        transformed_cps = raw_cps
        if qtaim_transform is not None:
            transformed_cps = transform_cps(qtaim_module.parse_critical_points_file(cp_path), qtaim_transform)
        cps, use_qtaim_transform = choose_coordinate_set(
            raw_cps,
            transformed_cps,
            rdg_cube.atom_coords,
            filter_cps_to_molecule,
            "critical-point",
        )
        if show_cps:
            cp_count = add_qtaim_bcps(
                plotter,
                qtaim_module,
                cps,
                cp_radius=cp_scale,
                show_labels=show_labels,
                show_ncp=show_ncp,
                show_bcp=show_bcp,
                show_rcp=show_rcp,
                show_ccp=show_ccp,
                show_unknown=show_unknown,
            )

    if show_paths and show_bond_paths and inputs.qtaim_path_file and Path(inputs.qtaim_path_file).is_file():
        atoms_for_unit = None
        try:
            if inputs.wavefunction_file and Path(inputs.wavefunction_file).is_file():
                atoms_for_unit = qtaim_module.read_atoms(Path(inputs.wavefunction_file))
        except Exception:
            atoms_for_unit = None
        raw_paths = qtaim_module.parse_bond_paths_file(Path(inputs.qtaim_path_file), atoms=atoms_for_unit, cps=cps)
        transformed_paths = raw_paths
        if qtaim_transform is not None:
            transformed_paths = transform_bond_paths(raw_paths, qtaim_transform)
        paths, _ = choose_coordinate_set(
            raw_paths,
            transformed_paths,
            rdg_cube.atom_coords,
            filter_paths_to_molecule,
            "bond-path",
        )
        paths = filter_paths_to_molecule(paths, rdg_cube.atom_coords)
        path_count = add_bond_paths(plotter, paths, radius=max(0.040, bond_radius * 0.95))

    plotter.add_text(
        f"Layers: molecule {'on' if show_molecule else 'off'} | NCI {nci_surface_count} | BCPs {cp_count} | paths {path_count}",
        position="upper_left",
        font_size=10,
        color="black" if background.lower() == "white" else "white",
    )
    plotter.reset_camera()
    plotter.show(title="NCI + QTAIM overlay")


class OverlayApp(tk.Tk):
    def __init__(self, initial_folder: Optional[Path] = None):
        super().__init__()
        self.title("NCI + QTAIM Overlay Viewer")
        self.geometry(f"980x{max(1, int(self.winfo_screenheight() * 0.80))}")
        qtaim_graphics = load_qtaim_graphics_settings()

        self.rdg_cube = tk.StringVar()
        self.signrho_cube = tk.StringVar()
        self.wavefunction_file = tk.StringVar()
        self.qtaim_cp_file = tk.StringVar()
        self.qtaim_path_file = tk.StringVar()

        self.rdg_isovalue = tk.DoubleVar(value=0.50)
        self.nci_opacity = tk.DoubleVar(value=0.55)
        self.color_min = tk.StringVar(value="-0.05")
        self.color_max = tk.StringVar(value="0.05")
        self.colormap = tk.StringVar(value="rainbow")
        self.background = tk.StringVar(value=str_setting(qtaim_graphics, "background", "white"))

        self.show_molecule = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_molecule", True))
        self.show_nci = tk.BooleanVar(value=True)
        self.show_cps = tk.BooleanVar(value=True)
        self.show_bond_paths = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_bond_paths", True))
        self.show_labels = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_labels", True))
        
        # QTAIM-specific CP type visibility
        self.show_ncp = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_ncp", False))
        self.show_bcp = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_bcp", True))
        self.show_rcp = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_rcp", False))
        self.show_ccp = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_ccp", False))
        self.show_unknown = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_unknown", False))
        self.show_covalent_bonds = tk.BooleanVar(value=bool_setting(qtaim_graphics, "show_covalent_bonds", True))
        
        # QTAIM-specific size parameters
        self.cp_scale = tk.DoubleVar(value=float_setting(qtaim_graphics, "cp_scale", 0.14))
        self.atom_scale = tk.DoubleVar(value=float_setting(qtaim_graphics, "atom_scale", 0.38))
        self.bond_radius = tk.DoubleVar(value=float_setting(qtaim_graphics, "bond_radius", 0.075))
        
        self.image_width = tk.IntVar(value=3000)
        self.image_height = tk.IntVar(value=2250)

        self._build()
        if initial_folder:
            self.auto_detect(initial_folder)

    def _build(self):
        host = ttk.Frame(self)
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        root = ttk.Frame(canvas, padding=12)
        root_window = canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(root_window, width=e.width))
        root.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(root, text="RDG cube:").grid(row=row, column=0, sticky="w", pady=4)
        rdg_entry = ttk.Entry(root, textvariable=self.rdg_cube)
        keep_entry_end_visible(rdg_entry, self.rdg_cube)
        rdg_entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="Browse", command=lambda: self.browse_file(self.rdg_cube, "Select RDG cube")).grid(row=row, column=2)

        row += 1
        ttk.Label(root, text="sign(lambda2)rho cube:").grid(row=row, column=0, sticky="w", pady=4)
        signrho_entry = ttk.Entry(root, textvariable=self.signrho_cube)
        keep_entry_end_visible(signrho_entry, self.signrho_cube)
        signrho_entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="Browse", command=lambda: self.browse_file(self.signrho_cube, "Select sign(lambda2)rho cube")).grid(row=row, column=2)

        row += 1
        ttk.Label(root, text="WFN/WFX file:").grid(row=row, column=0, sticky="w", pady=4)
        wavefunction_entry = ttk.Entry(root, textvariable=self.wavefunction_file)
        keep_entry_end_visible(wavefunction_entry, self.wavefunction_file)
        wavefunction_entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="Browse", command=lambda: self.browse_file(self.wavefunction_file, "Select WFN/WFX file")).grid(row=row, column=2)

        row += 1
        ttk.Label(root, text="QTAIM CP file:").grid(row=row, column=0, sticky="w", pady=4)
        cp_entry = ttk.Entry(root, textvariable=self.qtaim_cp_file)
        keep_entry_end_visible(cp_entry, self.qtaim_cp_file)
        cp_entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="Browse", command=lambda: self.browse_file(self.qtaim_cp_file, "Select QTAIM CP file")).grid(row=row, column=2)

        row += 1
        ttk.Label(root, text="QTAIM paths file:").grid(row=row, column=0, sticky="w", pady=4)
        path_entry = ttk.Entry(root, textvariable=self.qtaim_path_file)
        keep_entry_end_visible(path_entry, self.qtaim_path_file)
        path_entry.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(root, text="Browse", command=lambda: self.browse_file(self.qtaim_path_file, "Select QTAIM paths file")).grid(row=row, column=2)

        row += 1
        auto_frame = ttk.Frame(root)
        auto_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        ttk.Button(auto_frame, text="Auto-detect from folder", command=self.choose_auto_folder).pack(side="left")

        row += 1
        settings = ttk.LabelFrame(root, text="Display", padding=10)
        settings.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        for i in range(9):
            settings.columnconfigure(i, weight=1)

        # Main visibility toggles
        ttk.Checkbutton(settings, text="Molecule", variable=self.show_molecule).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(settings, text="NCI surface", variable=self.show_nci).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(settings, text="CPs", variable=self.show_cps).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(settings, text="QTAIM paths", variable=self.show_bond_paths).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(settings, text="Labels", variable=self.show_labels).grid(row=0, column=4, sticky="w")

        # CP type selection (only enabled if show_cps is enabled)
        ttk.Label(settings, text="CP types:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="NCP (3,-3)", variable=self.show_ncp).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="BCP (3,-1)", variable=self.show_bcp).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="RCP (3,+1)", variable=self.show_rcp).grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="CCP (3,+3)", variable=self.show_ccp).grid(row=1, column=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="Unknown", variable=self.show_unknown).grid(row=1, column=5, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="Cov. bonds", variable=self.show_covalent_bonds).grid(row=1, column=6, sticky="w", pady=(8, 0))

        # NCI-specific parameters
        ttk.Label(settings, text="RDG isovalue").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.rdg_isovalue, width=10).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="NCI opacity").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.nci_opacity, width=10).grid(row=2, column=3, sticky="w", pady=(8, 0))

        # Color scale parameters
        ttk.Label(settings, text="Color min").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.color_min, width=10).grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Color max").grid(row=3, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.color_max, width=10).grid(row=3, column=3, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Colormap").grid(row=3, column=4, sticky="w", pady=(8, 0))
        ttk.Combobox(settings, textvariable=self.colormap, values=["bwr", "seismic", "coolwarm", "rainbow", "jet", "viridis"], width=12, state="readonly").grid(row=3, column=5, sticky="w", pady=(8, 0))

        # QTAIM-specific size parameters
        ttk.Label(settings, text="CP size").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.cp_scale, width=10).grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Atom size").grid(row=4, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.atom_scale, width=10).grid(row=4, column=3, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Bond radius").grid(row=4, column=4, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.bond_radius, width=10).grid(row=4, column=5, sticky="w", pady=(8, 0))

        # Image export parameters
        ttk.Label(settings, text="Background").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(settings, textvariable=self.background, values=["white", "black"], width=12, state="readonly").grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Image width").grid(row=5, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.image_width, width=10).grid(row=5, column=3, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Height").grid(row=5, column=4, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.image_height, width=10).grid(row=5, column=5, sticky="w", pady=(8, 0))

        row += 1
        buttons = ttk.Frame(root)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Open overlay", command=self.open_overlay).pack(side="right")

    def browse_file(self, var: tk.StringVar, title: str):
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Supported files", "*.cub *.cube *.txt *.log *.out *.pdb"),
                ("All files", "*.*"),
            ],
        )
        if path:
            var.set(path)

    def choose_auto_folder(self):
        folder = filedialog.askdirectory(title="Select folder with ready NCI/QTAIM outputs")
        if folder:
            self.auto_detect(Path(folder))

    def auto_detect(self, folder: Path):
        rdg, signrho = detect_nci_cubes(folder)
        if rdg:
            self.rdg_cube.set(str(rdg))
        if signrho:
            self.signrho_cube.set(str(signrho))

        for candidate in sorted(iter_output_files(folder, ["*.wfx", "*.wfn"])):
            if candidate.is_file():
                self.wavefunction_file.set(str(candidate))
                break

        cp_file = find_qtaim_cp_file(folder, Path(self.wavefunction_file.get()).stem if self.wavefunction_file.get() else "")
        if cp_file:
            self.qtaim_cp_file.set(str(cp_file))

        path_file = find_qtaim_path_file(folder, Path(self.wavefunction_file.get()).stem if self.wavefunction_file.get() else "")
        if path_file:
            self.qtaim_path_file.set(str(path_file))

    def open_overlay(self):
        try:
            inputs = OverlayInputs(
                rdg_cube=Path(self.rdg_cube.get().strip()) if self.rdg_cube.get().strip() else None,
                signrho_cube=Path(self.signrho_cube.get().strip()) if self.signrho_cube.get().strip() else None,
                wavefunction_file=Path(self.wavefunction_file.get().strip()) if self.wavefunction_file.get().strip() else None,
                qtaim_cp_file=Path(self.qtaim_cp_file.get().strip()) if self.qtaim_cp_file.get().strip() else None,
                qtaim_path_file=Path(self.qtaim_path_file.get().strip()) if self.qtaim_path_file.get().strip() else None,
            )
            build_overlay(
                inputs,
                rdg_isovalue=float(self.rdg_isovalue.get()),
                nci_opacity=float(self.nci_opacity.get()),
                clim_min=float(self.color_min.get()),
                clim_max=float(self.color_max.get()),
                colormap=self.colormap.get(),
                show_molecule=bool(self.show_molecule.get()),
                show_nci=bool(self.show_nci.get()),
                show_cps=bool(self.show_cps.get()),
                show_bond_paths=bool(self.show_bond_paths.get()),
                show_labels=bool(self.show_labels.get()),
                background=self.background.get(),
                window_size=(int(self.image_width.get()), int(self.image_height.get())),
                # QTAIM settings
                show_ncp=bool(self.show_ncp.get()),
                show_bcp=bool(self.show_bcp.get()),
                show_rcp=bool(self.show_rcp.get()),
                show_ccp=bool(self.show_ccp.get()),
                show_unknown=bool(self.show_unknown.get()),
                cp_scale=float(self.cp_scale.get()),
                atom_scale=float(self.atom_scale.get()),
                bond_radius=float(self.bond_radius.get()),
                show_covalent_bonds=bool(self.show_covalent_bonds.get()),
            )
        except Exception as exc:
            messagebox.showerror("Overlay failed", str(exc))


def parse_args():
    qtaim_graphics = load_qtaim_graphics_settings()
    parser = argparse.ArgumentParser(description="Overlay molecule, NCI surface, QTAIM BCPs, and QTAIM bond paths.")
    parser.add_argument("wavefunction", nargs="?", help="WFN/WFX file. Its folder will be inspected for all required NCI/QTAIM outputs.")
    parser.add_argument("--folder", help="Folder containing ready NCI and QTAIM output files.")
    parser.add_argument("--rdg", help="RDG cube file.")
    parser.add_argument("--signrho", help="sign(lambda2)rho cube file.")
    parser.add_argument("--wfn", help="WFN/WFX file used to align QTAIM coordinates with the NCI molecule.")
    parser.add_argument("--cp", help="QTAIM critical-point text/log/PDB file.")
    parser.add_argument("--paths", help="QTAIM bond-path file, preferably paths.pdb.")
    parser.add_argument("--advanced", action="store_true", help="Open the manual file-selection window.")
    parser.add_argument("--no-gui", action="store_true", help="Open the overlay directly from command-line paths.")
    parser.add_argument("--rdg-isovalue", type=float, default=0.50)
    parser.add_argument("--opacity", type=float, default=0.55)
    parser.add_argument("--color-min", type=float, default=-0.05)
    parser.add_argument("--color-max", type=float, default=0.05)
    parser.add_argument("--colormap", default="rainbow")
    parser.add_argument("--background", default=str_setting(qtaim_graphics, "background", "white"))
    parser.add_argument("--show-molecule", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_molecule", True) else "0")
    parser.add_argument("--show-nci", choices=["0", "1"], default="1")
    parser.add_argument("--show-cps", "--show-bcps", dest="show_cps", choices=["0", "1"], default="1")
    parser.add_argument("--show-bond-paths", "--show-paths", dest="show_bond_paths", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_bond_paths", True) else "0")
    parser.add_argument("--show-labels", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_labels", True) else "0")
    parser.add_argument("--show-ncp", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_ncp", False) else "0")
    parser.add_argument("--show-bcp", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_bcp", True) else "0")
    parser.add_argument("--show-rcp", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_rcp", False) else "0")
    parser.add_argument("--show-ccp", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_ccp", False) else "0")
    parser.add_argument("--show-unknown", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_unknown", False) else "0")
    parser.add_argument("--show-covalent-bonds", choices=["0", "1"], default="1" if bool_setting(qtaim_graphics, "show_covalent_bonds", True) else "0")
    parser.add_argument("--atom-scale", type=float, default=float_setting(qtaim_graphics, "atom_scale", 0.38))
    parser.add_argument("--cp-scale", type=float, default=float_setting(qtaim_graphics, "cp_scale", 0.14))
    parser.add_argument("--bond-radius", type=float, default=float_setting(qtaim_graphics, "bond_radius", 0.075))
    parser.add_argument("--image-width", type=int)
    parser.add_argument("--image-height", type=int)
    return parser.parse_args()


def cli_window_size(args) -> Optional[tuple[int, int]]:
    if args.image_width and args.image_height and args.image_width > 0 and args.image_height > 0:
        return (int(args.image_width), int(args.image_height))
    return None


def choose_wavefunction_file() -> Optional[Path]:
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select WFN/WFX file for NCI + QTAIM overlay",
        filetypes=[("Wavefunction files", "*.wfn *.wfx"), ("All files", "*.*")],
    )
    root.destroy()
    return Path(path) if path else None


def run_from_wavefunction(wavefunction_file: Path, args) -> bool:
    if wavefunction_file.suffix.lower() not in {".wfn", ".wfx"}:
        raise ValueError("Select a .wfn or .wfx wavefunction file.")
    if not wavefunction_file.is_file():
        raise FileNotFoundError(str(wavefunction_file))

    inspection = inspect_wavefunction_folder(wavefunction_file)
    if args.rdg:
        inspection.inputs.rdg_cube = Path(args.rdg)
    if args.signrho:
        inspection.inputs.signrho_cube = Path(args.signrho)
    if args.cp:
        inspection.inputs.qtaim_cp_file = Path(args.cp)
    if args.paths:
        inspection.inputs.qtaim_path_file = Path(args.paths)
    if any([args.rdg, args.signrho, args.cp, args.paths]):
        inspection = FolderInspection(
            inputs=inspection.inputs,
            missing=[],
            instructions=[],
        )
        if inspection.inputs.rdg_cube is None or inspection.inputs.signrho_cube is None:
            inspection.missing.append("NCI cube files: RDG cube and sign(lambda2)rho cube")
            inspection.instructions.append(
                "Run NCI Plotter for this .wfn/.wfx file and generate the NCI data."
            )
    if inspection.missing:
        message = format_inspection_message(wavefunction_file, inspection)
        if args.no_gui:
            print(message)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("Missing overlay files", message)
            root.destroy()
        return False

    build_overlay(
        inspection.inputs,
        rdg_isovalue=args.rdg_isovalue,
        nci_opacity=args.opacity,
        clim_min=args.color_min,
        clim_max=args.color_max,
        colormap=args.colormap,
        show_molecule=args.show_molecule == "1",
        show_nci=args.show_nci == "1",
        show_cps=args.show_cps == "1",
        show_paths=args.show_bond_paths == "1",
        show_labels=args.show_labels == "1",
        background=args.background,
        window_size=cli_window_size(args),
        show_ncp=args.show_ncp == "1",
        show_bcp=args.show_bcp == "1",
        show_rcp=args.show_rcp == "1",
        show_ccp=args.show_ccp == "1",
        show_unknown=args.show_unknown == "1",
        cp_scale=float(args.cp_scale),
        atom_scale=float(args.atom_scale),
        bond_radius=float(args.bond_radius),
        show_covalent_bonds=args.show_covalent_bonds == "1",
        show_bond_paths=args.show_bond_paths == "1",
    )
    return True


def main():
    args = parse_args()
    folder = Path(args.folder) if args.folder else None

    wavefunction_arg = args.wavefunction or args.wfn
    if wavefunction_arg:
        run_from_wavefunction(Path(wavefunction_arg), args)
        return

    if not args.no_gui and not args.advanced and not any([args.rdg, args.signrho, args.cp, args.paths, args.folder]):
        wavefunction_file = choose_wavefunction_file()
        if wavefunction_file is None:
            return
        run_from_wavefunction(wavefunction_file, args)
        return

    if args.no_gui:
        inputs = OverlayInputs(
            rdg_cube=Path(args.rdg) if args.rdg else None,
            signrho_cube=Path(args.signrho) if args.signrho else None,
            wavefunction_file=Path(args.wfn) if args.wfn else None,
            qtaim_cp_file=Path(args.cp) if args.cp else None,
            qtaim_path_file=Path(args.paths) if args.paths else None,
        )
        if folder and (inputs.rdg_cube is None or inputs.signrho_cube is None):
            rdg, signrho = detect_nci_cubes(folder)
            inputs.rdg_cube = inputs.rdg_cube or rdg
            inputs.signrho_cube = inputs.signrho_cube or signrho
            if inputs.wavefunction_file is None:
                for candidate in sorted(iter_output_files(folder, ["*.wfx", "*.wfn"])):
                    inputs.wavefunction_file = candidate
                    break
        build_overlay(
            inputs,
            rdg_isovalue=args.rdg_isovalue,
            nci_opacity=args.opacity,
            clim_min=args.color_min,
            clim_max=args.color_max,
            colormap=args.colormap,
            show_molecule=args.show_molecule == "1",
            show_nci=args.show_nci == "1",
            show_cps=args.show_cps == "1",
            show_paths=args.show_bond_paths == "1",
            show_labels=args.show_labels == "1",
            background=args.background,
            window_size=cli_window_size(args),
            show_ncp=args.show_ncp == "1",
            show_bcp=args.show_bcp == "1",
            show_rcp=args.show_rcp == "1",
            show_ccp=args.show_ccp == "1",
            show_unknown=args.show_unknown == "1",
            cp_scale=float(args.cp_scale),
            atom_scale=float(args.atom_scale),
            bond_radius=float(args.bond_radius),
            show_covalent_bonds=args.show_covalent_bonds == "1",
            show_bond_paths=args.show_bond_paths == "1",
        )
        return

    app = OverlayApp(initial_folder=folder)
    app.mainloop()


if __name__ == "__main__":
    main()
