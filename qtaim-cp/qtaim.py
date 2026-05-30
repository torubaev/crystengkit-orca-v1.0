#!/usr/bin/env python3
"""
QTAIM Critical Points Viewer - draft standalone tool

Purpose
-------
- Assumes a .wfn or .wfx file already exists.
- Calls Multiwfn in batch mode using an editable command sequence.
- Saves the full Multiwfn text log.
- Tries to parse QTAIM critical points from the log or from a selected/exported CP text/PDB file.
- Tries to parse exact Multiwfn-exported QTAIM bond paths from paths.pdb or a path text file.
- Displays atoms, inferred bonds, CPs, and exact path polylines/tubes in a PyVista window.

Important
---------
Multiwfn menu numbers can differ between versions/settings. The default command sequence below
is intentionally editable in the GUI. If Multiwfn does not run the desired QTAIM search/export,
run the same .wfn/.wfx manually once in Multiwfn, note the exact menu choices, and paste them
into the "Multiwfn command sequence" box.

Exact QTAIM bond paths are not inferred geometrically. They are read from Multiwfn-exported
path-coordinate files, preferentially paths.pdb, and rendered by PyVista as curved tubes.

Tested assumptions
------------------
- Python 3.10+
- tkinter available
- pyvista installed
- Multiwfn executable available
"""

from __future__ import annotations

import math
import os
import re
import json
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from typing import Dict, List, Optional, Tuple

try:
    import pyvista as pv
except Exception:
    pv = None

APP_ROOT = Path(__file__).resolve().parents[1]
QTAIM_ICON_PATH = APP_ROOT / "Orca_input" / "images" / "qtaim.png"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
README_LINK_TEXT = "README section: QTAIM Critical Points Viewer"


def wiki_url() -> str:
    return GITHUB_URL + "#qtaim-critical-points-viewer"
ABOUT_PURPOSE = (
    "Shows QTAIM bond, ring, and cage critical points from .wfn or .wfx files and "
    "Multiwfn QTAIM output."
)
RECENT_FILES_PATH = Path.home() / ".qtaim_recent_files.json"
GRAPHICS_SETTINGS_PATH = Path.home() / ".qtaim_graphics_settings.json"
MAX_RECENT_FILES = 5
IMAGE_PRESETS = {
    "Viewer window": None,
    "Preview: 1600 x 1200 px": (1600, 1200),
    "Paper 300 dpi: 3000 x 2250 px": (3000, 2250),
    "Paper 600 dpi: 6000 x 4500 px": (6000, 4500),
    "Poster / high-res: 8000 x 6000 px": (8000, 6000),
}
DEFAULT_IMAGE_PRESET = "Paper 300 dpi: 3000 x 2250 px"


# -----------------------------
# Basic chemistry data
# -----------------------------

ELEMENTS_BY_Z = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F", 10: "Ne",
    11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
    19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr", 25: "Mn", 26: "Fe",
    27: "Co", 28: "Ni", 29: "Cu", 30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se",
    35: "Br", 36: "Kr", 37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo",
    43: "Tc", 44: "Ru", 45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn",
    51: "Sb", 52: "Te", 53: "I", 54: "Xe", 55: "Cs", 56: "Ba", 57: "La", 58: "Ce",
    59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd", 65: "Tb", 66: "Dy",
    67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu", 72: "Hf", 73: "Ta", 74: "W",
    75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au", 80: "Hg", 81: "Tl", 82: "Pb",
    83: "Bi", 84: "Po", 85: "At", 86: "Rn",
}
Z_BY_ELEMENT = {v: k for k, v in ELEMENTS_BY_Z.items()}

COVALENT_RADII = {
    "H": 0.31, "B": 0.85, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39,
    "Si": 1.11, "Se": 1.20, "Te": 1.38,
    "Li": 1.28, "Na": 1.66, "K": 2.03, "Mg": 1.41, "Ca": 1.76,
    "Fe": 1.24, "Co": 1.18, "Ni": 1.17, "Cu": 1.32, "Zn": 1.22,
    "Pd": 1.39, "Pt": 1.36, "Ag": 1.45, "Au": 1.36, "Rh": 1.42, "Ru": 1.46,
    "Cd": 1.44, "Hg": 1.32, "Al": 1.21, "Ga": 1.22, "Ge": 1.20, "As": 1.19,
    "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.39,
}

ATOM_COLORS = {
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

CP_DESCRIPTIONS = {
    "(3,-3)": "Nuclear critical point (NCP): local maximum of electron density at/near a nucleus.",
    "(3,-1)": "Bond critical point (BCP): saddle point between two attractors; commonly used to discuss bonding/interatomic interactions.",
    "(3,+1)": "Ring critical point (RCP): critical point associated with a ring of bond paths.",
    "(3,+3)": "Cage critical point (CCP): local minimum associated with a cage enclosed by ring paths.",
}

QTAIM_UI_BUILD = "2026-05-10 parser/run guard update"


def configure_builder_ui_style(widget: tk.Misc) -> None:
    style = ttk.Style(widget)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    try:
        widget.configure(background="#f4f6f9")
    except tk.TclError:
        pass

    style.configure("TFrame", background="#f4f6f9")
    style.configure("Panel.TFrame", background="#f4f6f9")
    style.configure("Header.TFrame", background="#1e3a5f")
    style.configure("HeaderTitle.TLabel", background="#1e3a5f", foreground="#f8fafc", font=("Segoe UI", 15, "bold"))
    style.configure("HeaderSub.TLabel", background="#1e3a5f", foreground="#d7e1ee", font=("Segoe UI", 10, "bold"))
    style.configure("HeaderAction.TLabel", background="#1e3a5f", foreground="#d7e1ee", font=("Segoe UI", 9, "bold"))
    style.configure("HeaderLink.TLabel", background="#1e3a5f", foreground="#ffffff", font=("Segoe UI", 11, "bold"))
    style.configure("TLabelframe", background="#f8fafc", bordercolor="#d8dee8", relief="solid", padding=8)
    style.configure("TLabelframe.Label", background="#f8fafc", foreground="#172033", font=("Segoe UI", 10, "bold"))
    style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
    style.configure("Primary.TButton", padding=(14, 8), font=("Segoe UI", 10, "bold"))
    style.configure(
        "HeaderCTA.TButton",
        background="#2f80c8",
        foreground="#ffffff",
        bordercolor="#61a5e8",
        lightcolor="#2f80c8",
        darkcolor="#2f80c8",
        focusthickness=0,
        padding=(14, 7),
        relief="flat",
        font=("Segoe UI", 9, "bold"),
    )
    style.map(
        "HeaderCTA.TButton",
        background=[("active", "#3b94df"), ("pressed", "#1f68a8")],
        foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        bordercolor=[("active", "#8ac4f4"), ("pressed", "#1f68a8")],
    )
    style.configure("Info.TButton", padding=(3, 1), font=("Segoe UI", 9, "bold"))
    style.configure("TCheckbutton", background="#f8fafc", padding=(1, 2), font=("Segoe UI", 9))
    style.configure("TLabel", background="#f8fafc", foreground="#263348", padding=(1, 1), font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background="#f4f6f9", foreground="#53627a", font=("Segoe UI", 9))


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


def bind_mousewheel_to_canvas(canvas: tk.Canvas, *_hover_widgets: tk.Misc) -> None:
    def _pointer_is_over_canvas() -> bool:
        try:
            x = canvas.winfo_pointerx()
            y = canvas.winfo_pointery()
            left = canvas.winfo_rootx()
            top = canvas.winfo_rooty()
            return left <= x < left + canvas.winfo_width() and top <= y < top + canvas.winfo_height()
        except tk.TclError:
            return False

    def _can_scroll() -> bool:
        try:
            first, last = canvas.yview()
            return first > 0.0 or last < 1.0
        except tk.TclError:
            return False

    def _wheel_units(event) -> int:
        if getattr(event, "num", None) == 4:
            return -5
        if getattr(event, "num", None) == 5:
            return 5
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return 0
        if abs(delta) >= 120:
            return int(-delta / 120) * 5
        return -5 if delta > 0 else 5

    def _on_mousewheel(event):
        if not _pointer_is_over_canvas() or not _can_scroll():
            return None
        units = _wheel_units(event)
        if units:
            canvas.yview_scroll(units, "units")
        return "break"

    canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")
    canvas.bind_all("<Button-4>", _on_mousewheel, add="+")
    canvas.bind_all("<Button-5>", _on_mousewheel, add="+")


def load_recent_files() -> List[str]:
    try:
        data = json.loads(RECENT_FILES_PATH.read_text(encoding="utf-8"))
        values = data.get("recent_input_files", [])
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()][:MAX_RECENT_FILES]
    except Exception:
        pass
    return []


def save_recent_files(paths: List[str]) -> None:
    try:
        RECENT_FILES_PATH.write_text(json.dumps({"recent_input_files": paths[:MAX_RECENT_FILES]}, indent=2), encoding="utf-8")
    except Exception:
        pass


def remember_recent_file(path: str, paths: List[str]) -> List[str]:
    clean = str(path or "").strip().strip('"')
    if not clean:
        return paths
    try:
        clean = str(Path(clean).resolve())
    except Exception:
        pass
    updated = [clean] + [item for item in paths if os.path.normcase(item) != os.path.normcase(clean)]
    updated = updated[:MAX_RECENT_FILES]
    save_recent_files(updated)
    return updated


def save_graphics_settings(settings: Dict[str, object]) -> None:
    try:
        GRAPHICS_SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_graphics_settings() -> Dict[str, object]:
    try:
        data = json.loads(GRAPHICS_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def graphics_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass
class Atom:
    symbol: str
    x: float
    y: float
    z: float


@dataclass
class CriticalPoint:
    index: int
    cp_type: str
    x: float
    y: float
    z: float
    rho: Optional[float] = None
    laplacian: Optional[float] = None
    ellipticity: Optional[float] = None


@dataclass
class BondPath:
    index: int
    points: List[Tuple[float, float, float]]
    bcp_index: Optional[int] = None
    atom1_index: Optional[int] = None
    atom2_index: Optional[int] = None
    source: str = ""


# -----------------------------
# File parsing
# -----------------------------

_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"


def _to_float(s: str) -> float:
    return float(s.replace("D", "E").replace("d", "e"))


def read_atoms_from_wfn(path: Path) -> List[Atom]:
    """
    Basic WFN atom parser.
    Common WFN atom lines look like:
      C    1    (CENTRE  1)    0.00000000  1.23400000  -0.10000000  CHARGE =  6.0
    """
    atoms: List[Atom] = []
    atom_line_re = re.compile(
        rf"^\s*([A-Za-z]{{1,2}})\s+\d+\s+\(CENTRE\s+\d+\)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})",
        re.IGNORECASE,
    )

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = atom_line_re.search(line)
            if not m:
                continue
            sym = m.group(1).capitalize()
            atoms.append(Atom(sym, _to_float(m.group(2)), _to_float(m.group(3)), _to_float(m.group(4))))

    if not atoms:
        raise ValueError("Could not parse atoms from WFN file. The WFN format may differ from the expected form.")
    return atoms


def _extract_wfx_block(text: str, tag_names: List[str]) -> Optional[str]:
    for tag in tag_names:
        m = re.search(rf"<\s*{re.escape(tag)}\s*>(.*?)<\s*/\s*{re.escape(tag)}\s*>", text, re.I | re.S)
        if m:
            return m.group(1)
    return None


def read_atoms_from_wfx(path: Path) -> List[Atom]:
    """
    Flexible WFX parser for common XML-like WFX blocks.
    """
    text = path.read_text(encoding="utf-8", errors="replace")

    z_block = _extract_wfx_block(text, ["Atomic Numbers", "AtomicNumbers", "Nuclear Charges", "NuclearCharges"])
    coord_block = _extract_wfx_block(text, ["Nuclear Cartesian Coordinates", "NuclearCartesianCoordinates"])

    if z_block is None or coord_block is None:
        raise ValueError("Could not find atomic-number and coordinate blocks in WFX file.")

    z_vals = [int(float(x)) for x in re.findall(_FLOAT, z_block)]
    coords = [_to_float(x) for x in re.findall(_FLOAT, coord_block)]

    if len(coords) < 3 * len(z_vals):
        raise ValueError("WFX coordinate block contains fewer coordinates than expected.")

    atoms: List[Atom] = []
    for i, z in enumerate(z_vals):
        sym = ELEMENTS_BY_Z.get(z, f"X{z}")
        x, y, zc = coords[3 * i: 3 * i + 3]
        atoms.append(Atom(sym, x, y, zc))

    if not atoms:
        raise ValueError("No atoms parsed from WFX file.")
    return atoms


def read_atoms(path: Path) -> List[Atom]:
    suffix = path.suffix.lower()
    if suffix == ".wfn":
        return read_atoms_from_wfn(path)
    if suffix == ".wfx":
        return read_atoms_from_wfx(path)
    raise ValueError("Input must be .wfn or .wfx")


# -----------------------------
# Bond inference
# -----------------------------

def distance(a: Atom, b: Atom) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


BOHR_PER_ANGSTROM = 1.8897259886
ANGSTROM_PER_BOHR = 0.529177210903


def estimate_coordinate_length_unit_factor(atoms: List[Atom]) -> float:
    """
    Returns the factor by which covalent radii in Angstrom should be multiplied.

    Multiwfn topology-analysis coordinates are in Bohr. WFN nuclear coordinates are also commonly
    in Bohr. If the nearest-neighbour distances look Bohr-like, use 1.8897; otherwise use 1.0.

    This is only for bond inference. It does not change atom or CP coordinates.
    """
    if len(atoms) < 2:
        return 1.0

    nearest = []
    for i, ai in enumerate(atoms):
        ds = []
        for j, aj in enumerate(atoms):
            if i == j:
                continue
            d = distance(ai, aj)
            if d > 0.1:
                ds.append(d)
        if ds:
            nearest.append(min(ds))

    if not nearest:
        return 1.0

    nearest.sort()
    med = nearest[len(nearest) // 2]

    # Typical organic nearest-neighbour distance:
    # ~1.0-1.5 if Angstrom, ~1.9-2.9 if Bohr.
    return BOHR_PER_ANGSTROM if med > 1.75 else 1.0


def infer_bonds(atoms: List[Atom], scale: float = 1.28) -> List[Tuple[int, int]]:
    primary_unit_factor = estimate_coordinate_length_unit_factor(atoms)

    def infer_with(unit_factor: float, scale_factor: float) -> List[Tuple[int, int]]:
        found: List[Tuple[int, int]] = []
        for i, ai in enumerate(atoms):
            ri = COVALENT_RADII.get(ai.symbol, 0.77) * unit_factor
            for j in range(i + 1, len(atoms)):
                aj = atoms[j]
                rj = COVALENT_RADII.get(aj.symbol, 0.77) * unit_factor
                d = distance(ai, aj)
                cutoff = scale_factor * (ri + rj)
                if 0.20 * unit_factor < d <= cutoff:
                    found.append((i, j))
        return found

    bonds = infer_with(primary_unit_factor, scale)
    if bonds:
        return bonds

    alternate_unit_factor = 1.0 if abs(primary_unit_factor - BOHR_PER_ANGSTROM) < 0.1 else BOHR_PER_ANGSTROM
    bonds = infer_with(alternate_unit_factor, scale)
    if bonds:
        return bonds

    # Some wavefunction exporters round or scale coordinates slightly differently.
    # If the normal covalent-radius test finds nothing, try conservative wider
    # thresholds before giving up. This is only for drawing the molecule layer.
    for fallback_scale in (1.38, 1.50, 1.65):
        bonds = infer_with(primary_unit_factor, fallback_scale)
        if bonds:
            return bonds
        bonds = infer_with(alternate_unit_factor, fallback_scale)
        if bonds:
            return bonds

    return []


def coordinate_extent_from_points(points: List[Tuple[float, float, float]]) -> float:
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def atom_coordinate_extent(atoms: List[Atom]) -> float:
    return coordinate_extent_from_points([(atom.x, atom.y, atom.z) for atom in atoms])


def points_need_bohr_to_angstrom(points: List[Tuple[float, float, float]], atoms: Optional[List[Atom]]) -> bool:
    if not points or not atoms:
        return False
    atom_unit_factor = estimate_coordinate_length_unit_factor(atoms)
    if abs(atom_unit_factor - 1.0) > 0.1:
        return False
    atom_extent = atom_coordinate_extent(atoms)
    point_extent = coordinate_extent_from_points(points)
    return atom_extent > 0.1 and point_extent > atom_extent * 1.45


def convert_cps_from_bohr_to_angstrom_if_needed(
    cps: List[CriticalPoint],
    atoms: Optional[List[Atom]],
) -> List[CriticalPoint]:
    points = [(cp.x, cp.y, cp.z) for cp in cps]
    if not points_need_bohr_to_angstrom(points, atoms):
        return cps
    return [
        CriticalPoint(
            cp.index,
            cp.cp_type,
            cp.x * ANGSTROM_PER_BOHR,
            cp.y * ANGSTROM_PER_BOHR,
            cp.z * ANGSTROM_PER_BOHR,
            cp.rho,
            cp.laplacian,
            cp.ellipticity,
        )
        for cp in cps
    ]


def convert_paths_from_bohr_to_angstrom_if_needed(
    paths: List[BondPath],
    atoms: Optional[List[Atom]],
) -> List[BondPath]:
    sample_points = [pt for bp in paths for pt in bp.points[:4]]
    if not points_need_bohr_to_angstrom(sample_points, atoms):
        return paths
    converted: List[BondPath] = []
    for bp in paths:
        pts = [(x * ANGSTROM_PER_BOHR, y * ANGSTROM_PER_BOHR, z * ANGSTROM_PER_BOHR) for x, y, z in bp.points]
        converted.append(BondPath(bp.index, pts, bp.bcp_index, bp.atom1_index, bp.atom2_index, bp.source))
    return converted


# -----------------------------
# Multiwfn execution and CP parsing
# -----------------------------

DEFAULT_MULTIWFN_COMMANDS = """\
# Multiwfn QTAIM topology + bond-path export template.
#
# This is the practical Multiwfn/VMD AIM route used by many Multiwfn tutorials:
#   2  = Topology analysis
#   2  = Search CPs from nuclear positions
#   3  = Search CPs from atom-pair midpoints
#   4  = Search CPs from triangle centers
#   5  = Search CPs from pyramid centers
#   8  = Generate paths connected with CPs
#   -4 = CP export menu
#   4  = Save CPs.txt
#   6  = Save CPs.pdb
#   0  = Return to topology menu
#   -5 = Path processing/export menu
#   4  = Save path points to paths.txt
#   6  = Export paths.pdb
#   0  = Return to topology menu
#   -10 = Return to main menu
#   q  = Quit
#
# Multiwfn menu numbers are version-dependent. The route intentionally avoids
# topology option 9 because systems without (3,+1) CPs can pause on an error and
# desynchronize the scripted export sequence. If this sequence does not generate
# paths.pdb for your Multiwfn build, run the same WFN/WFX manually once, record
# the exact successful menu sequence, and paste it here.
2
2
3
4
5
8
-4
4
6
0
-5
4
6
0
-10
q
"""

DEFAULT_MULTIWFN_NATIVE_VIEW_COMMANDS = """2
2
3
0
q
"""

def find_multiwfn() -> Optional[str]:
    candidates = [
        r"C:\Multiwfn_2026.2.2_bin_Win64\Multiwfn.exe",
        r"C:\Multiwfn\Multiwfn.exe",
        r"C:\Multiwfn_3.8_dev_bin_Win64\Multiwfn.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which("Multiwfn") or shutil.which("Multiwfn.exe") or shutil.which("multiwfn")


def likely_multiwfn_search_roots() -> List[Path]:
    roots: List[Path] = []
    home = Path.home()

    def add(path: Path) -> None:
        try:
            if path.exists() and path.is_dir():
                roots.append(path)
        except OSError:
            pass

    for item in [
        Path.cwd(),
        Path(__file__).resolve().parents[1],
        home / "Desktop",
        home / "Downloads",
        home / "Documents",
        home / "Applications",
        home / "bin",
        home / ".local" / "bin",
    ]:
        add(item)

    if os.name == "nt":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            env_value = os.environ.get(env_name)
            if env_value:
                env_path = Path(env_value)
                add(env_path)
                try:
                    for item in env_path.glob("*Multiwfn*"):
                        add(item)
                    for item in env_path.glob("*multiwfn*"):
                        add(item)
                except OSError:
                    pass
        add(Path("C:/"))
    else:
        for item in [Path("/"), Path("/opt"), Path("/usr/local"), Path("/usr/local/bin"), Path("/usr/bin")]:
            add(item)

    unique: List[Path] = []
    seen = set()
    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except OSError:
            key = str(root).lower()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_multiwfn_deep(max_seconds: float = 18.0, max_visited: int = 70000, max_depth: int = 6) -> Optional[str]:
    quick = find_multiwfn()
    if quick:
        return quick

    target_names = {"multiwfn", "multiwfn.exe"}
    skip_dirs = {
        "$Recycle.Bin", ".git", ".hg", ".svn", "__pycache__", "node_modules",
        "System Volume Information", "Windows", "WinSxS", "Microsoft", "Packages", "Temp", "tmp",
    }
    started = time.monotonic()
    visited = 0

    def timed_out() -> bool:
        return (time.monotonic() - started) > max_seconds

    def scan(folder: Path, depth: int) -> Optional[str]:
        nonlocal visited
        if timed_out() or visited >= max_visited or depth > max_depth:
            return None
        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except (OSError, PermissionError):
            return None
        for entry in entries:
            if timed_out() or visited >= max_visited:
                return None
            visited += 1
            try:
                if entry.is_file(follow_symlinks=False) and entry.name.lower() in target_names:
                    return str(Path(entry.path).resolve())
                if entry.is_dir(follow_symlinks=False) and entry.name not in skip_dirs:
                    found = scan(Path(entry.path), depth + 1)
                    if found:
                        return found
            except (OSError, PermissionError):
                continue
        return None

    for root in likely_multiwfn_search_roots():
        found = scan(root, 0)
        if found:
            return found
        if timed_out():
            break
    return None


def run_multiwfn(input_file: Path, multiwfn_exe: str, commands: str, log_path: Path, timeout_s: int = 600) -> int:
    """
    Run Multiwfn and always save stdout/stderr.

    Multiwfn sometimes returns non-zero after opening/closing its own graphics window or after
    an interactive branch receives an unexpected command. For this wrapper, that must not
    destroy useful CP data already printed to stdout. Therefore this function returns the code
    instead of raising on non-zero return.
    """
    if not input_file.exists():
        raise FileNotFoundError(str(input_file))
    if not multiwfn_exe:
        raise ValueError("Multiwfn executable path is empty.")
    if not Path(multiwfn_exe).exists() and shutil.which(multiwfn_exe) is None:
        raise FileNotFoundError(f"Multiwfn executable not found: {multiwfn_exe}")

    if not commands.endswith("\n"):
        commands += "\n"

    env = os.environ.copy()
    exe_path = Path(multiwfn_exe)
    if exe_path.exists():
        env.setdefault("Multiwfnpath", str(exe_path.resolve().parent))

    try:
        proc = subprocess.run(
            [multiwfn_exe, str(input_file)],
            input=commands,
            text=True,
            capture_output=True,
            cwd=str(input_file.parent),
            env=env,
            timeout=timeout_s,
            errors="replace",
        )
        log_text = ""
        log_text += "===== STDOUT =====\n"
        log_text += proc.stdout or ""
        log_text += "\n\n===== STDERR =====\n"
        log_text += proc.stderr or ""
        log_path.write_text(log_text, encoding="utf-8", errors="replace")
        return int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        log_text = "===== STDOUT =====\n"
        if exc.stdout:
            log_text += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode(errors="replace")
        log_text += "\n\n===== STDERR =====\n"
        if exc.stderr:
            log_text += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode(errors="replace")
        log_text += f"\n\n===== WRAPPER ERROR =====\nMultiwfn timed out after {timeout_s} s.\n"
        log_path.write_text(log_text, encoding="utf-8", errors="replace")
        return 124


def remove_generated_qtaim_files(folder: Path, input_stem: str = "") -> List[Path]:
    names = [
        "CPs.pdb",
        "CPs.txt",
        "CPprop.txt",
        "CPProp.txt",
        "CP.txt",
        "CP.pdb",
        "paths.txt",
        "Paths.txt",
        "paths.pdb",
        "Paths.pdb",
        "path.pdb",
        "bondpaths.pdb",
        "BondPaths.pdb",
        "bondpaths.txt",
        "BondPaths.txt",
    ]
    if input_stem:
        names.extend(
            [
                f"{input_stem}_CPprop.txt",
                f"{input_stem}_CPs.txt",
                f"{input_stem}_CP.txt",
                f"{input_stem}_CPs.pdb",
                f"{input_stem}_CP.pdb",
                f"{input_stem}_paths.txt",
                f"{input_stem}.paths.txt",
                f"{input_stem}_paths.pdb",
                f"{input_stem}.paths.pdb",
            ]
        )

    removed: List[Path] = []
    for name in dict.fromkeys(names):
        path = folder / name
        try:
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(path)
        except OSError:
            pass
    return removed


def normalize_cp_type(raw: str) -> str:
    """
    Normalize all common CP labels to one of:
      (3,-3), (3,-1), (3,+1), (3,+3), unknown

    This intentionally accepts variants such as:
      (3, -1), (3,+1), (3,1), BCP, RCP, CCP, NCP
    """
    s = str(raw).strip()

    low = s.lower().replace(" ", "")
    if "bond" in low or re.search(r"\bbcp\b", low) or "3n1" in low or "3-1" in low:
        return "(3,-1)"
    if "ring" in low or re.search(r"\brcp\b", low) or "3p1" in low or "3+1" in low:
        return "(3,+1)"
    if "cage" in low or re.search(r"\bccp\b", low) or "3p3" in low or "3+3" in low:
        return "(3,+3)"
    if "nuclear" in low or re.search(r"\bncp\b", low) or "3n3" in low or "3-3" in low:
        return "(3,-3)"

    m = re.search(r"\(\s*3\s*,\s*([+-]?)\s*([0-3])\s*\)", s)
    if not m:
        return "unknown"

    sign = m.group(1)
    val = m.group(2)

    if val == "3" and sign == "-":
        return "(3,-3)"
    if val == "1" and sign == "-":
        return "(3,-1)"
    if val == "1":
        return "(3,+1)"
    if val == "3":
        return "(3,+3)"

    return "unknown"


def parse_critical_points_from_text(text: str) -> List[CriticalPoint]:
    """
    Parser for Multiwfn topology-analysis output.

    Handles the important Multiwfn summary table format:
      Index                       Coordinate               Type
         1    14.80239428     3.71342894     6.79337107   (3,-1)

    Also handles:
      Index            XYZ Coordinate (Bohr)            Type
         1   14.80239428    3.71342894    6.79337107   (3,-1)

    and simple fallback rows:
      1 (3,-1) 14.80239428 3.71342894 6.79337107
      1 BCP    14.80239428 3.71342894 6.79337107
    """
    cps: List[CriticalPoint] = []

    def cp_type_from_text(s: str) -> str:
        low = s.lower()
        if re.search(r"\bbcp\b|bond critical|bond cp", low):
            return "(3,-1)"
        if re.search(r"\bncp\b|nuclear critical|nuclear cp", low):
            return "(3,-3)"
        if re.search(r"\brcp\b|ring critical|ring cp", low):
            return "(3,+1)"
        if re.search(r"\bccp\b|cage critical|cage cp", low):
            return "(3,+3)"
        m = re.search(r"\(\s*3\s*,\s*([+-]?)\s*([0-3])\s*\)", s)
        if m:
            sign = m.group(1)
            val = m.group(2)
            if val == "3" and sign == "-":
                return "(3,-3)"
            if val == "1" and sign == "-":
                return "(3,-1)"
            if val == "1":
                return "(3,+1)"
            if val == "3":
                return "(3,+3)"
        return "unknown"

    def add_cp(idx: int, cpt: str, xyz: Tuple[float, float, float], context: str = ""):
        rho = None
        lap = None
        ellip = None

        rho_m = re.search(rf"(?:rho|density|electron density)\s*(?:=|:)?\s*({_FLOAT})", context, re.I)
        if rho_m:
            rho = _to_float(rho_m.group(1))

        lap_m = re.search(rf"(?:laplacian|nabla\^2|∇²)\s*(?:=|:)?\s*({_FLOAT})", context, re.I)
        if lap_m:
            lap = _to_float(lap_m.group(1))

        ell_m = re.search(rf"(?:ellipticity)\s*(?:=|:)?\s*({_FLOAT})", context, re.I)
        if ell_m:
            ellip = _to_float(ell_m.group(1))

        cps.append(CriticalPoint(idx, normalize_cp_type(cpt), xyz[0], xyz[1], xyz[2], rho, lap, ellip))

    def coords_from_context(s: str) -> Optional[Tuple[float, float, float]]:
        coord_patterns = [
            rf"(?:Position|Coordinate|Coordinates|XYZ|X/Y/Z|Cartesian coordinate[s]?)\s*(?:\([^)]+\))?\s*(?:=|:)?\s*({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})",
            rf"\bX\s*(?:=|:)?\s*({_FLOAT}).*?\bY\s*(?:=|:)?\s*({_FLOAT}).*?\bZ\s*(?:=|:)?\s*({_FLOAT})",
        ]
        for pat in coord_patterns:
            m = re.search(pat, s, re.I | re.S)
            if m:
                return (_to_float(m.group(1)), _to_float(m.group(2)), _to_float(m.group(3)))
        return None

    # 1) Multiwfn summary table rows: index x y z (3,-1)
    summary_row_re = re.compile(
        rf"^\s*(\d+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})\s+(\(\s*3\s*,\s*[+-]?\s*[0-3]\s*\)|BCP|RCP|CCP|NCP)(?:[^\S\r\n]|$)[^\r\n]*",
        re.M,
    )
    for m in summary_row_re.finditer(text):
        idx = int(m.group(1))
        x = _to_float(m.group(2))
        y = _to_float(m.group(3))
        z = _to_float(m.group(4))
        cpt = cp_type_from_text(m.group(5))
        add_cp(idx, cpt, (x, y, z), m.group(0))

    # 2) Fallback table rows: index type x y z
    type_first_re = re.compile(
        rf"^\s*(\d+)\s+((?:\(\s*3\s*,\s*[+-]?\s*[0-3]\s*\))|BCP|RCP|CCP|NCP)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})",
        re.I | re.M,
    )
    for m in type_first_re.finditer(text):
        idx = int(m.group(1))
        cpt = cp_type_from_text(m.group(2))
        x = _to_float(m.group(3))
        y = _to_float(m.group(4))
        z = _to_float(m.group(5))
        add_cp(idx, cpt, (x, y, z), m.group(0))

    # 3) Fallback table rows: index x y z type, with more columns after type.
    coord_first_re = re.compile(
        rf"^\s*(\d+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})\s+((?:\(\s*3\s*,\s*[+-]?\s*[0-3]\s*\))|BCP|RCP|CCP|NCP)(?:[^\S\r\n]|$)[^\r\n]*",
        re.I | re.M,
    )
    for m in coord_first_re.finditer(text):
        idx = int(m.group(1))
        x = _to_float(m.group(2))
        y = _to_float(m.group(3))
        z = _to_float(m.group(4))
        cpt = cp_type_from_text(m.group(5))
        add_cp(idx, cpt, (x, y, z), m.group(0))

    # 4) Single-line verbose rows containing CP number, type and coordinates.
    line_cp_re = re.compile(
        rf"(?im)^\s*(?:CP|Critical point|Point)\s*#?\s*(\d+)(?P<rest>.*?(?:\(\s*3\s*,\s*[+-]?\s*[0-3]\s*\)|BCP|RCP|CCP|NCP).*?)$"
    )
    for m in line_cp_re.finditer(text):
        idx = int(m.group(1))
        row = m.group(0)
        cpt = cp_type_from_text(row)
        xyz = coords_from_context(row)
        if xyz is None:
            nums = [_to_float(x) for x in re.findall(_FLOAT, row)]
            if len(nums) >= 4:
                xyz = (nums[-3], nums[-2], nums[-1])
        if xyz is not None:
            add_cp(idx, cpt, xyz, row)

    # 5) Verbose CP blocks with labels/coordinates.
    block_patterns = [
        r"(?im)^\s*(?:CP|Critical point|Point)\s*#?\s*\d+\b.*?(?=^\s*(?:CP|Critical point|Point)\s*#?\s*\d+\b|\Z)",
        r"(?im)^\s*(?:The\s+)?\d+(?:st|nd|rd|th)?\s+critical point\b.*?(?=^\s*(?:The\s+)?\d+(?:st|nd|rd|th)?\s+critical point\b|\Z)",
    ]
    for pat in block_patterns:
        for mblock in re.finditer(pat, text, re.S):
            block = mblock.group(0)
            idx_m = re.search(r"(?:CP|Critical point|Point)\s*#?\s*(\d+)|(?:The\s+)?(\d+)(?:st|nd|rd|th)?\s+critical point", block, re.I)
            if idx_m and idx_m.group(1):
                idx = int(idx_m.group(1))
            elif idx_m and idx_m.group(2):
                idx = int(idx_m.group(2))
            else:
                idx = len(cps) + 1
            cpt = cp_type_from_text(block)

            xyz = coords_from_context(block)

            if xyz is not None:
                add_cp(idx, cpt, xyz, block)

    # Remove duplicates and re-index.
    unique: List[CriticalPoint] = []
    seen = set()
    for cp in cps:
        cpt = normalize_cp_type(cp.cp_type)
        key = (cpt, round(cp.x, 6), round(cp.y, 6), round(cp.z, 6))
        if key in seen:
            continue
        seen.add(key)
        cp.cp_type = cpt
        cp.index = len(unique) + 1
        unique.append(cp)

    return unique


def _pdb_xyz_from_line(line: str) -> Optional[Tuple[float, float, float]]:
    try:
        return (float(line[30:38]), float(line[38:46]), float(line[46:54]))
    except Exception:
        parts = line.split()
        for i in range(max(0, len(parts) - 7), len(parts) - 2):
            try:
                return (float(parts[i]), float(parts[i + 1]), float(parts[i + 2]))
            except Exception:
                continue
    return None


def _pdb_serial_from_line(line: str, fallback: int) -> int:
    try:
        return int(line[6:11])
    except Exception:
        parts = line.split()
        if len(parts) > 1:
            try:
                return int(parts[1])
            except Exception:
                pass
    return fallback


def _cp_type_from_pdb_line(line: str, remark_map: Dict[str, str]) -> str:
    atom_name = line[12:16].strip().upper()
    element = line[76:78].strip().upper() if len(line) >= 78 else ""
    for key in [atom_name, element]:
        if key in remark_map:
            return remark_map[key]
    label_bits = [
        atom_name,
        line[17:20].strip(),
        element,
        line,
    ]
    return normalize_cp_type(" ".join(label_bits))


def _cp_type_map_from_pdb_remarks(text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("REMARK"):
            continue
        for key, value in re.findall(r"\b([A-Za-z]{1,2})\s*=\s*(\(\s*3\s*,\s*[+-]?\s*[0-3]\s*\))", line):
            cpt = normalize_cp_type(value)
            if cpt != "unknown":
                mapping[key.upper()] = cpt
    if not mapping:
        mapping = {
            "C": "(3,-3)",
            "N": "(3,-1)",
            "O": "(3,+1)",
            "F": "(3,+3)",
        }
    return mapping


def parse_critical_points_from_pdb_text(text: str) -> List[CriticalPoint]:
    cps: List[CriticalPoint] = []
    remark_map = _cp_type_map_from_pdb_remarks(text)
    for fallback_idx, line in enumerate(text.splitlines(), start=1):
        if not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        xyz = _pdb_xyz_from_line(line)
        if xyz is None:
            continue
        cpt = _cp_type_from_pdb_line(line, remark_map)
        if cpt == "unknown":
            continue
        cps.append(CriticalPoint(len(cps) + 1, cpt, xyz[0], xyz[1], xyz[2]))
    return cps


def parse_critical_points_file(path: Path) -> List[CriticalPoint]:
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".pdb" or "ATOM" in text[:2000] or "HETATM" in text[:2000]:
        cps = parse_critical_points_from_pdb_text(text)
        if cps:
            return cps
    return parse_critical_points_from_text(text)


def save_cp_table(cps: List[CriticalPoint], out_path: Path) -> None:
    lines = ["index\ttype\tx\ty\tz\trho\tlaplacian\tellipticity"]
    for cp in cps:
        lines.append(
            f"{cp.index}\t{cp.cp_type}\t{cp.x:.10f}\t{cp.y:.10f}\t{cp.z:.10f}\t"
            f"{'' if cp.rho is None else f'{cp.rho:.10g}'}\t"
            f"{'' if cp.laplacian is None else f'{cp.laplacian:.10g}'}\t"
            f"{'' if cp.ellipticity is None else f'{cp.ellipticity:.10g}'}"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_pdb_cps_to_atom_units(cps: List[CriticalPoint], atoms: Optional[List[Atom]]) -> List[CriticalPoint]:
    if not cps or not atoms:
        return cps
    atom_unit_factor = estimate_coordinate_length_unit_factor(atoms)
    if abs(atom_unit_factor - BOHR_PER_ANGSTROM) >= 0.1:
        return cps
    return [
        CriticalPoint(
            cp.index,
            cp.cp_type,
            cp.x * BOHR_PER_ANGSTROM,
            cp.y * BOHR_PER_ANGSTROM,
            cp.z * BOHR_PER_ANGSTROM,
            cp.rho,
            cp.laplacian,
            cp.ellipticity,
        )
        for cp in cps
    ]


def convert_cps_to_atom_units(
    cps: List[CriticalPoint],
    atoms: Optional[List[Atom]],
    source_suffix: str = "",
) -> List[CriticalPoint]:
    if source_suffix.lower() == ".pdb":
        return convert_pdb_cps_to_atom_units(cps, atoms)
    return convert_cps_from_bohr_to_angstrom_if_needed(cps, atoms)


def _pdb_record_key(line: str) -> Tuple[str, str, str, str]:
    chain = line[21:22].strip() if len(line) >= 22 else ""
    resseq = line[22:26].strip() if len(line) >= 26 else ""
    icode = line[26:27].strip() if len(line) >= 27 else ""
    resname = line[17:20].strip() if len(line) >= 20 else ""
    return (chain, resseq, icode, resname)


def parse_bond_paths_from_pdb_text(text: str, source: str = "") -> List[BondPath]:
    """
    Parse Multiwfn/VMD paths.pdb-style files.

    The preferred Multiwfn export for exact AIM/QTAIM bond paths is paths.pdb. In typical
    paths.pdb files, each bond path is represented by a residue/group of ordered pseudo-atoms.
    This parser also supports CONECT-based ordering when residue grouping is absent.
    """
    records: Dict[int, Dict[str, object]] = {}
    order: List[int] = []
    conect: Dict[int, set[int]] = {}
    sequential_blocks: List[List[int]] = []
    current_block: List[int] = []

    def flush_block() -> None:
        nonlocal current_block
        if len(current_block) >= 2:
            sequential_blocks.append(current_block[:])
        current_block = []

    for fallback_idx, line in enumerate(text.splitlines(), start=1):
        rec = line[:6].strip().upper()
        if rec in {"ATOM", "HETATM"}:
            xyz = _pdb_xyz_from_line(line)
            if xyz is None:
                continue
            serial = _pdb_serial_from_line(line, fallback_idx)
            records[serial] = {
                "serial": serial,
                "xyz": xyz,
                "key": _pdb_record_key(line),
                "label": " ".join([line[12:16].strip(), line[17:20].strip()]),
                "line": line,
            }
            order.append(serial)
            current_block.append(serial)
        elif rec == "CONECT":
            parts = line.split()
            if len(parts) >= 3:
                try:
                    a = int(parts[1])
                except Exception:
                    continue
                for token in parts[2:]:
                    try:
                        b = int(token)
                    except Exception:
                        continue
                    conect.setdefault(a, set()).add(b)
                    conect.setdefault(b, set()).add(a)
        elif rec in {"TER", "END", "ENDMDL"}:
            flush_block()

    flush_block()

    if len(records) < 2:
        return []

    paths: List[BondPath] = []

    if conect:
        seen = set()
        components: List[List[int]] = []
        for start in sorted(records):
            if start in seen:
                continue
            stack = [start]
            seen.add(start)
            comp = []
            while stack:
                node = stack.pop()
                comp.append(node)
                for nb in sorted(conect.get(node, set())):
                    if nb in records and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            if len(comp) >= 2:
                components.append(comp)

        for comp in components:
            comp_set = set(comp)
            endpoints = [s for s in comp if len([n for n in conect.get(s, set()) if n in comp_set]) <= 1]
            start = min(endpoints or comp)
            ordered = []
            prev = None
            cur = start
            while cur is not None and cur not in ordered:
                ordered.append(cur)
                candidates = [n for n in sorted(conect.get(cur, set())) if n in comp_set and n != prev]
                nxt = candidates[0] if candidates else None
                prev, cur = cur, nxt
            if len(ordered) < len(comp):
                for s in sorted(comp):
                    if s not in ordered:
                        ordered.append(s)
            pts = [records[s]["xyz"] for s in ordered]  # type: ignore[index]
            if len(pts) >= 2:
                paths.append(BondPath(index=len(paths) + 1, points=list(pts), source=source))
        if paths:
            return paths

    if sequential_blocks:
        for block in sequential_blocks:
            pts = [records[s]["xyz"] for s in block if s in records]  # type: ignore[index]
            if len(pts) >= 2:
                paths.append(BondPath(index=len(paths) + 1, points=list(pts), source=source))
        if paths:
            return paths

    groups: Dict[Tuple[str, str, str, str], List[int]] = {}
    for serial in order:
        key = records[serial]["key"]  # type: ignore[index]
        groups.setdefault(key, []).append(serial)  # type: ignore[arg-type]

    usable_groups = [serials for serials in groups.values() if len(serials) >= 2]
    if usable_groups:
        for serials in usable_groups:
            pts = [records[s]["xyz"] for s in serials]  # type: ignore[index]
            if len(pts) >= 2:
                paths.append(BondPath(index=len(paths) + 1, points=list(pts), source=source))
        if paths:
            return paths

    pts = [records[s]["xyz"] for s in sorted(records)]  # type: ignore[index]
    return [BondPath(index=1, points=list(pts), source=source)] if len(pts) >= 2 else []


def parse_bond_paths_from_text(text: str, source: str = "") -> List[BondPath]:
    if "ATOM" in text[:4000] or "HETATM" in text[:4000]:
        return parse_bond_paths_from_pdb_text(text, source=source)

    paths: List[BondPath] = []
    current: List[Tuple[float, float, float]] = []
    saw_header = False

    def flush():
        nonlocal current
        if len(current) >= 2:
            paths.append(BondPath(index=len(paths) + 1, points=current[:], source=source))
        current = []

    def coords_from_numbers(nums: List[float]) -> Optional[Tuple[float, float, float]]:
        if len(nums) < 3:
            return None
        return (nums[-3], nums[-2], nums[-1])

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if saw_header:
                flush()
            continue
        if re.search(r"\b(?:bond\s*)?path\b", stripped, re.I):
            saw_header = True
            flush()
            nums = [_to_float(x) for x in re.findall(_FLOAT, stripped)]
            if len(nums) >= 3 and not re.match(r"^\s*(?:bond\s*)?path\s*\d+\s*$", stripped, re.I):
                coords = coords_from_numbers(nums)
                if coords is not None:
                    current.append(coords)
            continue
        nums = [_to_float(x) for x in re.findall(_FLOAT, stripped)]
        coords = coords_from_numbers(nums)
        if coords is not None:
            current.append(coords)
    flush()

    if not paths:
        rows = []
        for line in text.splitlines():
            nums = [_to_float(x) for x in re.findall(_FLOAT, line)]
            coords = coords_from_numbers(nums)
            if coords is not None:
                rows.append(coords)
        if len(rows) >= 2:
            paths.append(BondPath(index=1, points=rows, source=source))
    return paths


def _point_distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _point_to_segment_distance(
    p: Tuple[float, float, float],
    a: Tuple[float, float, float],
    b: Tuple[float, float, float],
) -> float:
    ax, ay, az = a
    bx, by, bz = b
    px, py, pz = p
    ab = (bx - ax, by - ay, bz - az)
    ap = (px - ax, py - ay, pz - az)
    ab2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
    if ab2 <= 1.0e-12:
        return _point_distance(p, a)
    t = max(0.0, min(1.0, (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / ab2))
    closest = (ax + t * ab[0], ay + t * ab[1], az + t * ab[2])
    return _point_distance(p, closest)


def count_covalent_bonds_with_nearby_bcp(
    atoms: List[Atom],
    bonds: List[Tuple[int, int]],
    cps: List[CriticalPoint],
) -> Tuple[int, int]:
    bcps = [cp for cp in cps if normalize_cp_type(cp.cp_type) == "(3,-1)"]
    if not atoms or not bonds or not bcps:
        return (0, len(bonds))
    unit_factor = estimate_coordinate_length_unit_factor(atoms)
    tolerance = max(0.20 * unit_factor, 0.35)
    matched = 0
    for i, j in bonds:
        a = (atoms[i].x, atoms[i].y, atoms[i].z)
        b = (atoms[j].x, atoms[j].y, atoms[j].z)
        if any(_point_to_segment_distance((cp.x, cp.y, cp.z), a, b) <= tolerance for cp in bcps):
            matched += 1
    return (matched, len(bonds))


def _typical_path_step(paths: List[BondPath]) -> float:
    steps = []
    for bp in paths:
        for p1, p2 in zip(bp.points, bp.points[1:]):
            d = _point_distance(p1, p2)
            if d > 1.0e-8:
                steps.append(d)
    if not steps:
        return 0.0
    steps.sort()
    return steps[len(steps) // 2]


def _endpoint_candidates_for_cp(
    path: BondPath,
    cp: CriticalPoint,
    tolerance: float,
) -> List[Tuple[str, float]]:
    cp_point = (cp.x, cp.y, cp.z)
    candidates = []
    d_start = _point_distance(path.points[0], cp_point)
    d_end = _point_distance(path.points[-1], cp_point)
    if d_start <= tolerance:
        candidates.append(("start", d_start))
    if d_end <= tolerance:
        candidates.append(("end", d_end))
    return candidates


def stitch_bond_path_fragments_at_bcps(
    paths: List[BondPath],
    cps: Optional[List[CriticalPoint]] = None,
) -> List[BondPath]:
    """
    Join two Multiwfn path halves only when both terminate at the same BCP.

    Some Multiwfn builds/export routes write two gradient-path halves per BCP
    instead of one atom-to-atom path. Rendering those halves directly looks like
    disconnected chunks. This function requires parsed BCP coordinates and will
    not merge merely because two arbitrary endpoints are close together.
    """
    if len(paths) < 2 or not cps:
        return paths

    bcps = [cp for cp in cps if normalize_cp_type(cp.cp_type) == "(3,-1)"]
    if not bcps:
        return paths

    typical_step = _typical_path_step(paths)
    bcp_tol = max(0.10, min(0.45, typical_step * 2.0 if typical_step else 0.20))

    unused = set(range(len(paths)))
    stitched: List[BondPath] = []

    for cp in bcps:
        matches: List[Tuple[int, str, float]] = []
        for idx in sorted(unused):
            candidates = _endpoint_candidates_for_cp(paths[idx], cp, bcp_tol)
            if not candidates:
                continue
            side, dist = min(candidates, key=lambda item: item[1])
            matches.append((idx, side, dist))

        # A proper BCP path has two branches terminating at the same BCP.
        # If there are more or fewer, keep the raw fragments rather than guess.
        if len(matches) != 2:
            continue

        (idx1, side1, _), (idx2, side2, _) = matches
        p1 = list(paths[idx1].points)
        p2 = list(paths[idx2].points)

        if side1 == "start":
            p1.reverse()
        if side2 == "end":
            p2.reverse()

        merged = p1 + p2[1:]
        stitched.append(
            BondPath(
                index=len(stitched) + 1,
                points=merged,
                bcp_index=cp.index,
                source=paths[idx1].source or paths[idx2].source,
            )
        )
        unused.remove(idx1)
        unused.remove(idx2)

    for idx in sorted(unused):
        bp = paths[idx]
        stitched.append(BondPath(len(stitched) + 1, bp.points, bp.bcp_index, bp.atom1_index, bp.atom2_index, bp.source))

    return stitched


def parse_bond_paths_file(
    path: Path,
    atoms: Optional[List[Atom]] = None,
    cps: Optional[List[CriticalPoint]] = None,
) -> List[BondPath]:
    text = path.read_text(encoding="utf-8", errors="replace")
    paths = parse_bond_paths_from_text(text, source=str(path))
    if not paths:
        return []
    if path.suffix.lower() == ".pdb" and atoms:
        atom_unit_factor = estimate_coordinate_length_unit_factor(atoms)
        if abs(atom_unit_factor - BOHR_PER_ANGSTROM) < 0.1:
            converted: List[BondPath] = []
            for bp in paths:
                pts = [(x * BOHR_PER_ANGSTROM, y * BOHR_PER_ANGSTROM, z * BOHR_PER_ANGSTROM) for x, y, z in bp.points]
                converted.append(BondPath(bp.index, pts, bp.bcp_index, bp.atom1_index, bp.atom2_index, bp.source))
            paths = converted
    else:
        paths = convert_paths_from_bohr_to_angstrom_if_needed(paths, atoms)
    return stitch_bond_path_fragments_at_bcps(paths, cps=cps)


def summarize_bond_paths(paths: List[BondPath]) -> str:
    if not paths:
        return "0 paths"
    point_counts = [len(bp.points) for bp in paths]
    total_points = sum(point_counts)
    return (
        f"{len(paths)} paths, {total_points} total points, "
        f"points/path min={min(point_counts)}, median={sorted(point_counts)[len(point_counts) // 2]}, "
        f"max={max(point_counts)}"
    )


def select_bond_paths_by_range(paths: List[BondPath], range_text: str) -> List[BondPath]:
    """
    Display-only path selector.

    Empty/"all" keeps every parsed path. Examples: "1-4", "1,3,8", "2-5,9".
    Path numbers are the visible 1-based path indices reported in the log.
    """
    text = (range_text or "").strip().lower()
    if not text or text in {"all", "*"}:
        return paths

    selected_indices = set()
    for chunk in re.split(r"[,;\s]+", text):
        if not chunk:
            continue
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            try:
                start = int(left) if left.strip() else 1
                end = int(right) if right.strip() else len(paths)
            except ValueError:
                continue
            if end < start:
                start, end = end, start
            selected_indices.update(range(max(1, start), min(len(paths), end) + 1))
        else:
            try:
                idx = int(chunk)
            except ValueError:
                continue
            if 1 <= idx <= len(paths):
                selected_indices.add(idx)

    if not selected_indices:
        return paths
    return [bp for display_idx, bp in enumerate(paths, start=1) if display_idx in selected_indices]


def _is_fresh_file(path: Path, min_mtime: Optional[float] = None) -> bool:
    if min_mtime is None:
        return True
    try:
        return path.stat().st_mtime >= min_mtime
    except OSError:
        return False


def find_generated_qtaim_path_file(input_file: Path, min_mtime: Optional[float] = None) -> Optional[Path]:
    candidates = [
        input_file.parent / "paths.txt",
        input_file.parent / "Paths.txt",
        input_file.parent / "paths.pdb",
        input_file.parent / "Paths.pdb",
        input_file.parent / "path.pdb",
        input_file.parent / f"{input_file.stem}_paths.txt",
        input_file.parent / f"{input_file.stem}.paths.txt",
        input_file.parent / f"{input_file.stem}_paths.pdb",
        input_file.parent / f"{input_file.stem}.paths.pdb",
        input_file.parent / "bondpaths.pdb",
        input_file.parent / "BondPaths.pdb",
    ]
    for c in candidates:
        if c.exists() and c.is_file() and _is_fresh_file(c, min_mtime):
            return c
    try:
        for child in input_file.parent.iterdir():
            if (
                child.is_file()
                and child.name.lower() in {"paths.txt", "paths.pdb", "path.pdb", "bondpaths.pdb"}
                and _is_fresh_file(child, min_mtime)
            ):
                return child
    except Exception:
        pass
    return None


def list_possible_qtaim_path_files(input_file: Path) -> List[Path]:
    names = {"paths.txt", "paths.pdb", "path.pdb", "bondpaths.pdb", "bondpaths.txt"}
    found: List[Path] = []
    try:
        for child in input_file.parent.iterdir():
            if child.is_file() and ("path" in child.name.lower() or child.name.lower() in names):
                found.append(child)
    except Exception:
        pass
    return sorted(found, key=lambda p: p.name.lower())


def find_generated_cp_file(input_file: Path, min_mtime: Optional[float] = None) -> Optional[Path]:
    names = [
        "CPprop.txt",
        "CPProp.txt",
        "CPs.txt",
        "CP.txt",
        f"{input_file.stem}_CPprop.txt",
        f"{input_file.stem}_CPs.txt",
        "CPs.pdb",
        "CP.pdb",
    ]
    for name in names:
        c = input_file.parent / name
        if c.exists() and c.is_file() and _is_fresh_file(c, min_mtime):
            return c
    try:
        for child in input_file.parent.iterdir():
            if (
                child.is_file()
                and child.name.lower() in {"cpprop.txt", "cps.txt", "cp.txt", "cps.pdb", "cp.pdb"}
                and _is_fresh_file(child, min_mtime)
            ):
                return child
    except Exception:
        pass
    return None


def list_possible_qtaim_cp_files(input_file: Path, min_mtime: Optional[float] = None) -> List[Path]:
    preferred_names = [
        "CPprop.txt",
        "CPProp.txt",
        "CPs.txt",
        "CP.txt",
        f"{input_file.stem}_CPprop.txt",
        f"{input_file.stem}_CPs.txt",
        "CPs.pdb",
        "CP.pdb",
        input_file.with_suffix(".multiwfn_qtaim.log").name,
    ]
    found: List[Path] = []
    seen = set()

    for name in preferred_names:
        path = input_file.parent / name
        key = str(path).lower()
        if key not in seen and path.exists() and path.is_file() and _is_fresh_file(path, min_mtime):
            found.append(path)
            seen.add(key)

    try:
        for child in input_file.parent.iterdir():
            low = child.name.lower()
            if (
                child.is_file()
                and _is_fresh_file(child, min_mtime)
                and ("cp" in low or "critical" in low or low.endswith(".multiwfn_qtaim.log"))
            ):
                key = str(child).lower()
                if key not in seen:
                    found.append(child)
                    seen.add(key)
    except Exception:
        pass

    return found


# -----------------------------
# Visualization
# -----------------------------

def molecule_extent(atoms: List[Atom]) -> float:
    if not atoms:
        return 1.0
    xs = [atom.x for atom in atoms]
    ys = [atom.y for atom in atoms]
    zs = [atom.z for atom in atoms]
    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    return max(math.sqrt(dx * dx + dy * dy + dz * dz), 1.0)


def configure_pyvista_defaults(pv_module, plotter, background="black", parallel_projection=True, antialiasing=None, extent=1.0):
    try:
        pv_module.global_theme.multi_samples = 16
    except Exception:
        pass
    try:
        pv_module.global_theme.smooth_shading = True
    except Exception:
        pass
    try:
        plotter.set_background(background)
    except Exception:
        pass
    if antialiasing:
        try:
            plotter.enable_anti_aliasing(antialiasing)
        except Exception:
            pass


def should_use_transparent_png(path: str, background: str) -> bool:
    return str(path).lower().endswith(".png") and str(background or "").strip().lower() == "white"


def save_pyvista_screenshot(plotter, path: str, background: str, **kwargs):
    if should_use_transparent_png(path, background):
        try:
            return plotter.screenshot(path, transparent_background=True, **kwargs)
        except TypeError:
            pass
    return plotter.screenshot(path, **kwargs)
    try:
        plotter.renderer.SetTwoSidedLighting(True)
    except Exception:
        pass
    if parallel_projection:
        try:
            plotter.enable_parallel_projection()
        except Exception:
            pass
    try:
        plotter.remove_all_lights()
    except Exception:
        pass
    try:
        extent = max(float(extent), 1.0)
    except Exception:
        extent = 1.0
    light_specs = [
        ("headlight", None, 0.95),
        ("camera light", None, 0.45),
        ("scene light", (3.0 * extent, -4.0 * extent, 5.0 * extent), 0.35),
        ("scene light", (-3.0 * extent, 3.0 * extent, 4.0 * extent), 0.25),
    ]
    for light_type, position, intensity in light_specs:
        try:
            if light_type in {"headlight", "camera light"}:
                light = pv_module.Light(light_type=light_type)
            else:
                light = pv_module.Light(
                    position=position,
                    focal_point=(0.0, 0.0, 0.0),
                    color="white",
                    light_type="scene light",
                )
            light.intensity = intensity
            plotter.add_light(light)
        except Exception:
            pass


def molecule_material_parameters() -> Dict[str, object]:
    return {
        "lighting": True,
        "smooth_shading": True,
        "ambient": 0.50,
        "diffuse": 0.62,
        "specular": 0.18,
        "specular_power": 20,
    }


def add_mesh_safe(plotter, mesh, **kwargs):
    try:
        return plotter.add_mesh(mesh, **kwargs)
    except TypeError:
        safe_kwargs = dict(kwargs)
        safe_kwargs.pop("pbr", None)
        safe_kwargs.pop("metallic", None)
        safe_kwargs.pop("roughness", None)
        return plotter.add_mesh(mesh, **safe_kwargs)


def display_atom_radius(symbol: str, unit_factor: float, scale: float = 1.0) -> float:
    covalent = COVALENT_RADII.get(symbol, 0.77) * unit_factor
    return float(max(0.16 * unit_factor, min(0.55 * unit_factor, covalent * 0.42 * scale)))


def molecule_bond_radius(unit_factor: float, scale: float = 1.0) -> float:
    return float(max(0.045 * unit_factor, 0.075 * unit_factor * scale))


def cylinder_between(pv_module, p1, p2, radius=0.075, resolution=48):
    import numpy as np

    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    vector = p2 - p1
    length = float(np.linalg.norm(vector))
    if length <= 1.0e-8:
        return None
    return pv_module.Cylinder(
        center=tuple((p1 + p2) / 2.0),
        direction=tuple(vector / length),
        radius=radius,
        height=length,
        resolution=resolution,
        capping=True,
    )


def add_split_colored_bond(pv_module, plotter, p1, p2, color1: str, color2: str, radius: float) -> None:
    import numpy as np

    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    midpoint = (p1 + p2) / 2.0
    for a, b, color in ((p1, midpoint, color1), (midpoint, p2, color2)):
        cylinder = cylinder_between(pv_module, a, b, radius=radius, resolution=48)
        if cylinder is not None:
            add_mesh_safe(plotter, cylinder, color=color, **molecule_material_parameters())


def add_ball_and_stick_atom(
    pv_module,
    plotter,
    atom: Atom,
    unit_factor: float,
    scale: float,
) -> None:
    sphere = pv_module.Sphere(
        radius=display_atom_radius(atom.symbol, unit_factor, scale=scale),
        center=(atom.x, atom.y, atom.z),
        theta_resolution=64,
        phi_resolution=64,
    )
    add_mesh_safe(
        plotter,
        sphere,
        color=ATOM_COLORS.get(atom.symbol, "#FF69B4"),
        **molecule_material_parameters(),
    )


def add_molecule_layer(
    pv_module,
    plotter,
    atoms: List[Atom],
    bonds: List[Tuple[int, int]],
    atom_scale: float,
    bond_radius: float,
) -> None:
    unit_factor = estimate_coordinate_length_unit_factor(atoms)
    for i, j in bonds:
        ai, aj = atoms[i], atoms[j]
        add_split_colored_bond(
            pv_module,
            plotter,
            (ai.x, ai.y, ai.z),
            (aj.x, aj.y, aj.z),
            ATOM_COLORS.get(ai.symbol, "#FF69B4"),
            ATOM_COLORS.get(aj.symbol, "#FF69B4"),
            radius=molecule_bond_radius(unit_factor, scale=max(0.2, bond_radius / 0.095)),
        )
    for atom in atoms:
        add_ball_and_stick_atom(pv_module, plotter, atom, unit_factor, scale=max(0.2, atom_scale / 0.38))


def add_exact_bond_paths(plotter, bond_paths: List[BondPath], radius: float = 0.10, color: str = "yellow") -> int:
    if not bond_paths:
        return 0
    import numpy as np
    count = 0
    for bp in bond_paths:
        if len(bp.points) < 2:
            continue
        pts = np.array(bp.points, dtype=float)
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


def count_bcps(cps: List[CriticalPoint]) -> int:
    return sum(1 for cp in cps if normalize_cp_type(cp.cp_type) == "(3,-1)")


def _path_min_distance_to_cp(path: BondPath, cp: CriticalPoint) -> float:
    cp_point = (cp.x, cp.y, cp.z)
    return min((_point_distance(point, cp_point) for point in path.points), default=float("inf"))


def _bond_path_associated_cp_type(
    path: BondPath,
    cps: List[CriticalPoint],
    tolerance: float,
) -> Optional[str]:
    if path.bcp_index is not None:
        for cp in cps:
            if cp.index == path.bcp_index:
                return normalize_cp_type(cp.cp_type)

    ranked = [
        (_path_min_distance_to_cp(path, cp), normalize_cp_type(cp.cp_type))
        for cp in cps
        if normalize_cp_type(cp.cp_type) != "(3,-3)"
    ]
    if not ranked:
        ranked = [(_path_min_distance_to_cp(path, cp), normalize_cp_type(cp.cp_type)) for cp in cps]
    if not ranked:
        return None

    distance, cp_type = min(ranked, key=lambda item: item[0])
    return cp_type if distance <= tolerance else None


def filter_bond_paths_by_visible_cp_types(
    bond_paths: List[BondPath],
    cps: List[CriticalPoint],
    visible_types: set[str],
) -> List[BondPath]:
    if not bond_paths or not cps:
        return bond_paths

    typical_step = _typical_path_step(bond_paths)
    tolerance = max(0.12, min(0.60, typical_step * 3.0 if typical_step else 0.30))
    visible_paths = []
    for path in bond_paths:
        cp_type = _bond_path_associated_cp_type(path, cps, tolerance)
        if cp_type is None or cp_type in visible_types:
            visible_paths.append(path)
    return visible_paths


def draw_qtaim_scene(
    plotter,
    atoms: List[Atom],
    cps: List[CriticalPoint],
    show_ncp: bool = False,
    show_bcp: bool = True,
    show_rcp: bool = False,
    show_ccp: bool = False,
    show_unknown: bool = False,
    show_labels: bool = False,
    show_molecule: bool = True,
    show_covalent_bonds: bool = True,
    show_bond_paths: bool = True,
    bond_paths: Optional[List[BondPath]] = None,
    atom_scale: float = 0.38,
    cp_scale: float = 0.32,
    bond_radius: float = 0.115,
    background: str = "black",
) -> None:
    if pv is None:
        raise RuntimeError("PyVista is not installed. Install with: pip install pyvista vtk")

    if not atoms:
        raise RuntimeError("No atoms loaded.")
    if not cps:
        raise RuntimeError(
            "No critical points were parsed. The viewer will not plot an empty CP scene. "
            "Check the Multiwfn log or load/export a CP table containing index, type, x, y, z."
        )

    try:
        plotter.clear()
    except Exception:
        pass
    configure_pyvista_defaults(pv, plotter, background=background, extent=molecule_extent(atoms))

    bonds = infer_bonds(atoms)

    # Draw the molecule layer with the same ball-and-stick style used by the
    # builder, NCI, and ESP PyVista viewers.
    if show_molecule:
        add_molecule_layer(
            pv,
            plotter,
            atoms,
            bonds if show_covalent_bonds else [],
            atom_scale=atom_scale,
            bond_radius=bond_radius,
        )

    visible_types = set()
    if show_ncp:
        visible_types.add(normalize_cp_type("(3,-3)"))
    if show_bcp:
        visible_types.add(normalize_cp_type("(3,-1)"))
    if show_rcp:
        visible_types.add(normalize_cp_type("(3,+1)"))
    if show_ccp:
        visible_types.add(normalize_cp_type("(3,+3)"))
    if show_unknown:
        visible_types.add("unknown")

    # Draw QTAIM bond paths before atoms/CPs, so CPs remain visible on top.
    exact_path_count = 0
    bcp_n = count_bcps(cps)
    if show_bond_paths and bond_paths:
        visible_bond_paths = filter_bond_paths_by_visible_cp_types(bond_paths, cps, visible_types)
        exact_path_count = add_exact_bond_paths(
            plotter,
            visible_bond_paths,
            radius=max(0.040, bond_radius * 0.95),
            color="yellow",
        )

    label_points = []
    label_text = []

    visible_cp_count = 0
    for cp in cps:
        cpt = normalize_cp_type(cp.cp_type)
        if cpt not in visible_types:
            continue
        visible_cp_count += 1
        color = CP_COLORS.get(cpt, "white")
        sphere = pv.Sphere(
            radius=cp_scale,
            center=(cp.x, cp.y, cp.z),
            theta_resolution=48,
            phi_resolution=48,
        )
        plotter.add_mesh(
            sphere,
            color=color,
            smooth_shading=True,
            ambient=0.75,
            diffuse=0.85,
            specular=0.50,
        )
        if show_labels:
            label_points.append((cp.x, cp.y, cp.z))
            label_text.append(f"{CP_LABELS.get(cpt, 'CP')}{cp.index}")

    if visible_cp_count == 0:
        parsed_types = sorted({normalize_cp_type(cp.cp_type) for cp in cps})
        raise RuntimeError(
            "Critical points were parsed, but none match the currently enabled CP-type checkboxes. "
            f"Parsed normalized CP types: {parsed_types}. "
            "Enable Unknown CPs or the corresponding CP type(s)."
        )

    if show_labels and label_points:
        plotter.add_point_labels(
            label_points,
            label_text,
            font_size=16,
            text_color="white" if background.lower() == "black" else "black",
            shape_color="black" if background.lower() == "black" else "white",
            shape_opacity=0.45,
            always_visible=True,
        )

    # Keep the scene free of depth-outline post-processing; eye-dome lighting
    # creates dark silhouettes around atoms, bonds, and QTAIM paths.
    plotter.camera_position = "iso"
    plotter.reset_camera()


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


def load_header_icon(path: Path, max_size: int = 56) -> Optional[tk.PhotoImage]:
    if not path.is_file():
        return None
    img = tk.PhotoImage(file=str(path))
    factor = max(1, int(max(img.width() / max_size, img.height() / max_size) + 0.999))
    if factor > 1:
        img = img.subsample(factor, factor)
    return img


def open_about_dialog(parent: tk.Misc, title: str, icon_path: Path, purpose: str) -> None:
    win = tk.Toplevel(parent)
    win.title("About")
    win.transient(parent)
    win.columnconfigure(0, weight=1)

    box = ttk.Frame(win, padding=14)
    box.grid(row=0, column=0, sticky="nsew")
    box.columnconfigure(1, weight=1)

    icon = load_header_icon(icon_path, max_size=144)
    if icon is not None:
        win.about_icon = icon
        ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=7, sticky="n", padx=(0, 14))

    ttk.Label(box, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
    ttk.Label(box, text=purpose, justify="left", wraplength=420).grid(row=1, column=1, sticky="w", pady=(8, 0))
    ttk.Label(box, text="GitHub:", justify="left").grid(row=2, column=1, sticky="w", pady=(10, 0))
    github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
    github_link.grid(row=3, column=1, sticky="w", pady=(2, 0))
    github_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL))
    ttk.Label(box, text="README:", justify="left").grid(row=4, column=1, sticky="w", pady=(10, 0))
    wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
    wiki_link.grid(row=5, column=1, sticky="w", pady=(2, 0))
    wiki_link.bind("<Button-1>", lambda _event: webbrowser.open(wiki_url(), new=2))
    ttk.Label(box, text=COPYRIGHT_NOTE, justify="left").grid(row=6, column=1, sticky="w", pady=(10, 0))

    ttk.Button(box, text="Close", command=win.destroy).grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
    win.geometry("570x340")
    win.minsize(470, 290)
    win.grab_set()


def visualize_qtaim(
    atoms: List[Atom],
    cps: List[CriticalPoint],
    show_ncp: bool = False,
    show_bcp: bool = True,
    show_rcp: bool = False,
    show_ccp: bool = False,
    show_unknown: bool = False,
    show_labels: bool = False,
    show_bond_paths: bool = True,
    bond_paths: Optional[List[BondPath]] = None,
    atom_scale: float = 0.38,
    cp_scale: float = 0.32,
    bond_radius: float = 0.115,
    background: str = "black",
) -> None:
    if pv is None:
        raise RuntimeError("PyVista is not installed. Install with: pip install pyvista vtk")
    plotter = pv.Plotter(window_size=screen_fraction_window_size(1300, 900), lighting="none")
    draw_qtaim_scene(
        plotter,
        atoms=atoms,
        cps=cps,
        show_ncp=show_ncp,
        show_bcp=show_bcp,
        show_rcp=show_rcp,
        show_ccp=show_ccp,
        show_unknown=show_unknown,
        show_labels=show_labels,
        show_bond_paths=show_bond_paths,
        bond_paths=bond_paths,
        atom_scale=atom_scale,
        cp_scale=cp_scale,
        bond_radius=bond_radius,
        background=background,
    )
    plotter.show(title="QTAIM")



# -----------------------------
# GUI
# -----------------------------

class QTAIMGui(tk.Tk):
    def __init__(self, initial_input_path: Optional[str] = None):
        super().__init__()
        self.title("QTAIM")
        self.main_window_size = self.detect_main_window_size()
        self.geometry(f"{self.main_window_size[0]}x{self.main_window_size[1]}")
        configure_builder_ui_style(self)

        self.input_path = tk.StringVar()
        self.multiwfn_path = tk.StringVar(value=find_multiwfn() or "")
        self.log_path = tk.StringVar()
        self.cp_file_path = tk.StringVar()
        self.path_file_path = tk.StringVar()

        self.show_ncp = tk.BooleanVar(value=False)
        self.show_bcp = tk.BooleanVar(value=True)
        self.show_rcp = tk.BooleanVar(value=False)
        self.show_ccp = tk.BooleanVar(value=False)
        self.show_unknown = tk.BooleanVar(value=False)
        self.show_labels = tk.BooleanVar(value=False)
        self.show_molecule = tk.BooleanVar(value=True)
        self.show_covalent_bonds = tk.BooleanVar(value=True)
        self.show_bond_paths = tk.BooleanVar(value=True)

        self.atom_scale = tk.DoubleVar(value=0.38)
        self.cp_scale = tk.DoubleVar(value=0.14)
        self.bond_radius = tk.DoubleVar(value=0.075)
        self.timeout_s = tk.IntVar(value=600)
        self.background = tk.StringVar(value="white")
        self.open_native_after_run = tk.BooleanVar(value=False)
        self.use_existing_outputs = tk.BooleanVar(value=False)
        self.path_display_range = tk.StringVar(value="")
        self.image_resolution = tk.StringVar(value=DEFAULT_IMAGE_PRESET)
        self.multiwfn_commands = DEFAULT_MULTIWFN_COMMANDS
        self._graphics_save_job = None
        self.apply_graphics_settings(load_graphics_settings())
        self.bind_graphics_setting_traces()
        self.settings_window: Optional[tk.Toplevel] = None
        self.settings_seq_text: Optional[tk.Text] = None

        self.atoms: List[Atom] = []
        self.cps: List[CriticalPoint] = []
        self.bond_paths: List[BondPath] = []
        self.run_in_progress = False
        self.plotter = None
        self.header_icon: Optional[tk.PhotoImage] = None
        self.pyvista_window_size = self.detect_pyvista_window_size()
        self.pending_visualize_job = None
        self.recent_input_files = load_recent_files()

        self._build_ui()
        self.log(f"QTAIM script build: {QTAIM_UI_BUILD}")
        self.log(f"Main window size: {self.main_window_size[0]} x {self.main_window_size[1]}")
        self.log(f"PyVista window size: {self.pyvista_window_size[0]} x {self.pyvista_window_size[1]}")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if initial_input_path:
            self.set_input_path(initial_input_path)
        self.start_multiwfn_locator()

    def apply_graphics_settings(self, settings: Dict[str, object]) -> None:
        if not settings:
            return

        bool_vars = {
            "show_ncp": self.show_ncp,
            "show_bcp": self.show_bcp,
            "show_rcp": self.show_rcp,
            "show_ccp": self.show_ccp,
            "show_unknown": self.show_unknown,
            "show_labels": self.show_labels,
            "show_molecule": self.show_molecule,
            "show_covalent_bonds": self.show_covalent_bonds,
            "show_bond_paths": self.show_bond_paths,
        }
        for key, var in bool_vars.items():
            if key in settings:
                var.set(graphics_bool(settings[key]))

        float_vars = {
            "atom_scale": self.atom_scale,
            "cp_scale": self.cp_scale,
            "bond_radius": self.bond_radius,
        }
        for key, var in float_vars.items():
            try:
                if key in settings:
                    var.set(float(settings[key]))
            except Exception:
                pass

        if str(settings.get("background", "")).lower() in {"white", "black"}:
            self.background.set(str(settings["background"]).lower())
        if settings.get("path_display_range") is not None:
            self.path_display_range.set(str(settings.get("path_display_range", "")))

    def current_graphics_settings(self) -> Dict[str, object]:
        return {
            "show_ncp": bool(self.show_ncp.get()),
            "show_bcp": bool(self.show_bcp.get()),
            "show_rcp": bool(self.show_rcp.get()),
            "show_ccp": bool(self.show_ccp.get()),
            "show_unknown": bool(self.show_unknown.get()),
            "show_labels": bool(self.show_labels.get()),
            "show_molecule": bool(self.show_molecule.get()),
            "show_covalent_bonds": bool(self.show_covalent_bonds.get()),
            "show_bond_paths": bool(self.show_bond_paths.get()),
            "atom_scale": float(self.atom_scale.get()),
            "cp_scale": float(self.cp_scale.get()),
            "bond_radius": float(self.bond_radius.get()),
            "background": str(self.background.get()),
            "path_display_range": str(self.path_display_range.get()),
        }

    def save_current_graphics_settings(self) -> None:
        try:
            save_graphics_settings(self.current_graphics_settings())
        except Exception:
            pass

    def schedule_graphics_settings_save(self, *_args) -> None:
        if self._graphics_save_job is not None:
            try:
                self.after_cancel(self._graphics_save_job)
            except Exception:
                pass
        self._graphics_save_job = self.after(150, self._run_graphics_settings_save)

    def _run_graphics_settings_save(self) -> None:
        self._graphics_save_job = None
        self.save_current_graphics_settings()

    def bind_graphics_setting_traces(self) -> None:
        for var in (
            self.show_ncp,
            self.show_bcp,
            self.show_rcp,
            self.show_ccp,
            self.show_unknown,
            self.show_labels,
            self.show_molecule,
            self.show_covalent_bonds,
            self.show_bond_paths,
            self.atom_scale,
            self.cp_scale,
            self.bond_radius,
            self.background,
            self.path_display_range,
        ):
            var.trace_add("write", self.schedule_graphics_settings_save)

    def schedule_final_visualize(self, delay_ms: int = 250) -> None:
        if self.pending_visualize_job is not None:
            try:
                self.after_cancel(self.pending_visualize_job)
            except Exception:
                pass
            self.pending_visualize_job = None
        self.pending_visualize_job = self.after(delay_ms, self.run_scheduled_visualize)

    def run_scheduled_visualize(self) -> None:
        self.pending_visualize_job = None
        if self.run_in_progress:
            self.schedule_final_visualize(250)
            return
        self.visualize()

    def start_multiwfn_locator(self) -> None:
        if self.multiwfn_path.get().strip():
            return

        def worker() -> None:
            found = find_multiwfn_deep()
            self.after(0, lambda: self.finish_multiwfn_locator(found))

        threading.Thread(target=worker, daemon=True).start()

    def finish_multiwfn_locator(self, found: Optional[str]) -> None:
        if found and not self.multiwfn_path.get().strip():
            self.multiwfn_path.set(found)

    def detect_main_window_size(self) -> Tuple[int, int]:
        try:
            screen_w = int(self.winfo_screenwidth())
            screen_h = int(self.winfo_screenheight())
        except Exception:
            return (1080, 800)

        width = max(700, int(screen_w * 0.50))
        height = max(1, int(screen_h * 0.80))
        return (width, height)

    def detect_pyvista_window_size(self) -> Tuple[int, int]:
        try:
            screen_w = int(self.winfo_screenwidth())
            screen_h = int(self.winfo_screenheight())
        except Exception:
            return (900, 760)

        width = max(640, int(screen_w * 0.50))
        height = max(1, int(screen_h * 0.80))
        return (width, height)

    def selected_image_size(self) -> Optional[Tuple[int, int]]:
        return IMAGE_PRESETS.get(self.image_resolution.get(), IMAGE_PRESETS[DEFAULT_IMAGE_PRESET])

    def _build_ui(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(14, 10))
        header.pack(fill="x")
        self.header_icon = load_header_icon(QTAIM_ICON_PATH)
        if self.header_icon is not None:
            tk.Label(header, image=self.header_icon, bg="#1e3a5f", bd=0, highlightthickness=0).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
        ttk.Label(header, text="QTAIM", style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(
            header,
            text="Critical Points and Bonding Paths Viewer",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=1, sticky="w")
        header.columnconfigure(2, weight=1)
        header_actions = ttk.Frame(header, style="Header.TFrame")
        header_actions.grid(row=0, column=3, rowspan=2, sticky="e")
        about_link = ttk.Label(header_actions, text="About", style="HeaderLink.TLabel", cursor="hand2")
        about_link.pack(side="right", padx=(12, 0))
        about_link.bind(
            "<Button-1>",
            lambda _event: open_about_dialog(self, "QTAIM Critical Points Viewer", QTAIM_ICON_PATH, ABOUT_PURPOSE),
        )
        ttk.Button(
            header_actions,
            text="NCI + QTAIM overlay",
            command=self.open_nci_qtaim_overlay,
            style="HeaderCTA.TButton",
        ).pack(side="right")
        body = ttk.Frame(self, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 6))
        footer.pack(side="bottom", fill="x")
        ttk.Label(footer, text=COPYRIGHT_NOTE, style="Muted.TLabel").pack(anchor="w")

        canvas = tk.Canvas(body, bg="#f4f6f9", highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        root = ttk.Frame(canvas, style="Panel.TFrame", padding=10)
        root_window = canvas.create_window((0, 0), window=root, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(event):
            canvas.itemconfigure(root_window, width=event.width)

        root.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        bind_mousewheel_to_canvas(canvas, root)

        file_frame = ttk.LabelFrame(root, text="Input", padding=10)
        file_frame.pack(fill="x", pady=(0, 8))

        top_buttons = ttk.Frame(file_frame)
        top_buttons.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 8))
        ttk.Button(top_buttons, text="Settings", command=self.open_settings).pack(side="left")

        ttk.Label(file_frame, text="WFN/WFX file:").grid(row=1, column=0, sticky="w")
        self.input_combo = ttk.Combobox(file_frame, textvariable=self.input_path, values=self.recent_input_files, width=46)
        keep_entry_end_visible(self.input_combo, self.input_path)
        self.input_combo.grid(row=1, column=1, sticky="ew", padx=5)
        self.input_combo.bind("<<ComboboxSelected>>", lambda _e: self.set_input_path(self.input_path.get().strip()))
        ttk.Button(file_frame, text="Browse", command=self.browse_input).grid(row=1, column=2)
        ttk.Button(file_frame, text="Run", command=self.run_multiwfn_threaded, style="Primary.TButton").grid(row=1, column=3, padx=(8, 0))

        file_frame.columnconfigure(1, weight=0)
        file_frame.columnconfigure(4, weight=1)

        settings = ttk.LabelFrame(root, text="Visualization settings", padding=10)
        settings.pack(fill="x", pady=(0, 8))

        cp_items = [
            ("NCP (3,-3)", self.show_ncp, "nuclei", CP_COLORS["(3,-3)"], 0, 0),
            ("BCP (3,-1)", self.show_bcp, "bond/contact", CP_COLORS["(3,-1)"], 0, 3),
            ("RCP (3,+1)", self.show_rcp, "ring", CP_COLORS["(3,+1)"], 0, 6),
            ("CCP (3,+3)", self.show_ccp, "cage", CP_COLORS["(3,+3)"], 1, 0),
            ("Unknown CPs", self.show_unknown, "unclassified", CP_COLORS["unknown"], 1, 3),
            ("Labels", self.show_labels, "names", None, 1, 6),
        ]
        for text, var, note, color, row, col in cp_items:
            cp_wrap = ttk.Frame(settings, style="Panel.TFrame")
            cp_wrap.grid(row=row, column=col, columnspan=3, sticky="w", padx=(0, 14), pady=(0 if row == 0 else 6, 0))
            ttk.Checkbutton(cp_wrap, text=text, variable=var).pack(side="left")
            if color:
                swatch = tk.Canvas(cp_wrap, width=16, height=16, bg="#f4f6f9", highlightthickness=0)
                swatch.create_oval(3, 3, 15, 15, fill=color, outline="#5f6f86", width=1)
                swatch.pack(side="left", padx=(3, 2))
            ttk.Label(cp_wrap, text=note, style="Muted.TLabel", anchor="w").pack(side="left", padx=(0, 0))

        ttk.Checkbutton(settings, text="Molecule", variable=self.show_molecule).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="Covalent bonds", variable=self.show_covalent_bonds).grid(row=2, column=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(settings, text="QTAIM paths", variable=self.show_bond_paths).grid(row=2, column=6, sticky="w", pady=(8, 0))

        ttk.Label(settings, text="Atom size").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.atom_scale, width=10).grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="CP size").grid(row=3, column=3, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.cp_scale, width=10).grid(row=3, column=4, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Bond/path radius").grid(row=3, column=6, sticky="w", pady=(8, 0))
        ttk.Entry(settings, textvariable=self.bond_radius, width=10).grid(row=3, column=7, sticky="w", pady=(8, 0))

        ttk.Label(settings, text="Background").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(settings, textvariable=self.background, values=["black", "white"], width=10, state="readonly").grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Image size").grid(row=4, column=3, sticky="w", pady=(8, 0))
        ttk.Combobox(
            settings,
            textvariable=self.image_resolution,
            values=list(IMAGE_PRESETS.keys()),
            width=28,
            state="readonly",
        ).grid(row=4, column=4, columnspan=4, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", pady=(0, 8))

        ttk.Button(buttons, text="Display CPs and bonding paths", command=self.visualize, style="Primary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Update plot", command=self.update_plot).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Reset view", command=self.reset_view).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Save image", command=self.save_image).pack(side="left", padx=(0, 6))

        log_frame = ttk.LabelFrame(root, text="Status", padding=10)
        log_frame.pack(fill="both", expand=True)

        self.status = tk.Text(log_frame, height=12, wrap="word", font=("Consolas", 10), relief="solid", bd=1)
        self.status.pack(fill="both", expand=True)

    def log(self, msg: str):
        self.status.insert("end", msg.rstrip() + "\n")
        self.status.see("end")
        self.update_idletasks()

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        win = tk.Toplevel(self)
        win.title("QTAIM Multiwfn Settings")
        win.geometry(f"980x{max(1, int(win.winfo_screenheight() * 0.80))}")
        configure_builder_ui_style(win)
        self.settings_window = win

        host = ttk.Frame(win, style="Panel.TFrame")
        host.pack(fill="both", expand=True)
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)
        canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0, bg="#f4f6f9")
        scrollbar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        root = ttk.Frame(canvas, style="Panel.TFrame", padding=10)
        root_window = canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(root_window, width=e.width))
        bind_mousewheel_to_canvas(canvas, root)

        exe_frame = ttk.LabelFrame(root, text="Execution", padding=10)
        exe_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(exe_frame, text="Timeout, s").grid(row=0, column=0, sticky="w")
        ttk.Entry(exe_frame, textvariable=self.timeout_s, width=10).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Checkbutton(
            exe_frame,
            text="Open Multiwfn native viewer after run",
            variable=self.open_native_after_run,
        ).grid(row=0, column=1, sticky="w", padx=(95, 5))
        ttk.Button(
            exe_frame,
            text="Open Multiwfn Native Viewer",
            command=self.open_native_multiwfn_threaded,
        ).grid(row=0, column=2, sticky="e")
        ttk.Checkbutton(
            exe_frame,
            text="Use existing CP/path files if present",
            variable=self.use_existing_outputs,
        ).grid(row=1, column=1, sticky="w", padx=5, pady=(8, 0))
        ttk.Label(
            exe_frame,
            text="Unchecked: delete old exports and recalculate everything.",
            style="Muted.TLabel",
        ).grid(row=2, column=1, sticky="w", padx=5, pady=(2, 0))
        exe_frame.columnconfigure(1, weight=1)

        files_frame = ttk.LabelFrame(root, text="Files", padding=10)
        files_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(files_frame, text="CP text/log/PDB file:").grid(row=0, column=0, sticky="w")
        cp_entry = ttk.Entry(files_frame, textvariable=self.cp_file_path, width=90)
        keep_entry_end_visible(cp_entry, self.cp_file_path)
        cp_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(files_frame, text="Browse", command=self.browse_cp_file).grid(row=0, column=2)
        ttk.Label(files_frame, text="Exact bond-path file:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        path_entry = ttk.Entry(files_frame, textvariable=self.path_file_path, width=90)
        keep_entry_end_visible(path_entry, self.path_file_path)
        path_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=(8, 0))
        ttk.Button(files_frame, text="Browse", command=self.browse_path_file).grid(row=1, column=2, pady=(8, 0))
        ttk.Label(
            files_frame,
            text="Usually filled automatically after running Multiwfn. Edit only when loading existing outputs manually.",
            style="Muted.TLabel",
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=(4, 0))
        files_frame.columnconfigure(1, weight=1)

        display_frame = ttk.LabelFrame(root, text="Display", padding=10)
        display_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(display_frame, text="QTAIM path range:").grid(row=0, column=0, sticky="w")
        ttk.Entry(display_frame, textvariable=self.path_display_range, width=30).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(
            display_frame,
            text="Empty/all = show every parsed path. Examples: 1-4, 1,3,8, 2-5,9.",
            style="Muted.TLabel",
        ).grid(row=0, column=2, sticky="w", padx=8)
        display_frame.columnconfigure(2, weight=1)

        seq_frame = ttk.LabelFrame(root, text="Multiwfn command sequence", padding=10)
        seq_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.settings_seq_text = tk.Text(seq_frame, height=12, wrap="none", font=("Consolas", 10), relief="solid", bd=1)
        self.settings_seq_text.pack(fill="both", expand=True)
        self.settings_seq_text.insert("1.0", self.multiwfn_commands)

        note = (
            "Important: Multiwfn menu numbers are version-dependent. These commands are used for the automatic "
            "QTAIM run and exact path export. PyVista only plots generated CP/path files."
        )
        ttk.Label(seq_frame, text=note, style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(root)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Apply", command=self.apply_settings).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Close", command=self.close_settings).pack(side="left")

        win.protocol("WM_DELETE_WINDOW", self.close_settings)

    def apply_settings(self):
        if self.settings_seq_text is not None:
            self.multiwfn_commands = self.settings_seq_text.get("1.0", "end")
        self.log("Settings applied.")

    def close_settings(self):
        self.apply_settings()
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.settings_window = None
        self.settings_seq_text = None

    def browse_input(self):
        path = filedialog.askopenfilename(
            title="Select WFN/WFX file",
            filetypes=[("Wavefunction files", "*.wfn *.wfx"), ("All files", "*.*")]
        )
        if path:
            self.set_input_path(path)

    def set_input_path(self, path: str):
        p = Path(path)
        self.input_path.set(str(p))
        self._remember_input_path(str(p))
        self.log_path.set(str(p.with_suffix(".multiwfn_qtaim.log")))
        self.cp_file_path.set(str(p.with_suffix(".multiwfn_qtaim.log")))
        self.path_file_path.set(str(p.parent / "paths.txt"))
        self.atoms = []
        self.cps = []
        self.bond_paths = []
        self.after(100, self.run_multiwfn_threaded)

    def _remember_input_path(self, path: str):
        self.recent_input_files = remember_recent_file(path, self.recent_input_files)
        try:
            self.input_combo.configure(values=self.recent_input_files)
        except Exception:
            pass

    def prompt_for_multiwfn(self) -> Optional[str]:
        path = filedialog.askopenfilename(
            title="Select Multiwfn executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.multiwfn_path.set(path)
            return path
        return None

    def ensure_multiwfn_available(self) -> str:
        raw = self.multiwfn_path.get().strip()
        if raw and (Path(raw).exists() or shutil.which(raw)):
            return raw

        messagebox.showwarning(
            "Multiwfn not found",
            "Multiwfn was not found automatically. Please select the Multiwfn executable.",
            parent=self,
        )
        selected = self.prompt_for_multiwfn()
        if selected and (Path(selected).exists() or shutil.which(selected)):
            return selected
        raise FileNotFoundError("Multiwfn executable was not selected or could not be found.")

    def browse_cp_file(self):
        path = filedialog.askopenfilename(
            title="Select CP text/log/PDB file",
            filetypes=[("CP/topology files", "*.txt *.log *.out *.pdb"), ("All files", "*.*")]
        )
        if path:
            self.cp_file_path.set(path)
            self.load_cp_file(Path(path))

    def browse_path_file(self):
        path = filedialog.askopenfilename(
            title="Select exact QTAIM bond-path file, preferably Multiwfn paths.pdb",
            filetypes=[("Path files", "*.pdb *.txt *.log *.out"), ("All files", "*.*")]
        )
        if path:
            self.path_file_path.set(path)
            self.load_path_file(Path(path))

    def load_atoms(self):
        try:
            input_text = self.input_path.get().strip()
            if not input_text:
                raise ValueError("Select a .wfn or .wfx file first.")
            p = Path(input_text)
            self.atoms = read_atoms(p)
            unit_factor = estimate_coordinate_length_unit_factor(self.atoms)
            unit_label = "Bohr-like" if abs(unit_factor - BOHR_PER_ANGSTROM) < 0.1 else "Angstrom-like"
            bonds = infer_bonds(self.atoms)
            self.log(f"Loaded atoms: {len(self.atoms)}")
            self.log(f"Atom coordinate scale: {unit_label}; molecule extent {molecule_extent(self.atoms):.3f}")
            self.log(f"Inferred covalent bonds: {len(bonds)}")
            return True
        except Exception as exc:
            self.show_exception("Could not load atoms", exc)
            return False

    def run_multiwfn_threaded(self):
        if self.run_in_progress:
            self.log("Multiwfn workflow is already running.")
            return
        try:
            self.ensure_multiwfn_available()
        except Exception as exc:
            self.show_exception("Multiwfn not found", exc)
            return
        t = threading.Thread(target=self.run_multiwfn_action, daemon=True)
        t.start()

    def load_existing_outputs_if_available(self, input_file: Path) -> bool:
        cp_candidate = find_generated_cp_file(input_file)
        log_candidate = input_file.with_suffix(".multiwfn_qtaim.log")
        if cp_candidate is None and log_candidate.exists() and log_candidate.is_file():
            cp_candidate = log_candidate

        if cp_candidate is None:
            self.log("No existing CP export/log found for this WFN/WFX folder.")
            return False

        self.log("Using existing QTAIM output files; Multiwfn recalculation is skipped.")
        self.cp_file_path.set(str(cp_candidate))
        self.load_cp_file(cp_candidate)

        path_candidate = find_generated_qtaim_path_file(input_file)
        if path_candidate is not None:
            self.path_file_path.set(str(path_candidate))
            self.load_path_file(path_candidate)
        else:
            self.bond_paths = []
            self.path_file_path.set(str(input_file.parent / "paths.txt"))
            self.log("No existing exact QTAIM path file found; CPs will be shown without gold paths.")

        return bool(self.cps)

    def run_multiwfn_action(self):
        self.run_in_progress = True
        try:
            input_text = self.input_path.get().strip()
            if not input_text:
                raise ValueError("Select a .wfn or .wfx file before running QTAIM.")
            input_file = Path(input_text)
            if input_file.suffix.lower() not in {".wfn", ".wfx"}:
                raise ValueError("QTAIM input must be a .wfn or .wfx file.")
            self.cps = []
            self.bond_paths = []
            self.log("")
            self.log("----- QTAIM run started -----")
            if not self.load_atoms():
                self.log("QTAIM run stopped because atoms could not be loaded.")
                return

            log_path = input_file.with_suffix(".multiwfn_qtaim.log")
            self.log_path.set(str(log_path))
            self.cp_file_path.set(str(log_path))

            if bool(self.use_existing_outputs.get()):
                if self.load_existing_outputs_if_available(input_file):
                    self.schedule_final_visualize()
                    return
                self.log("Existing-output option is enabled, but nothing usable was found. Recalculating now.")

            if self.settings_seq_text is not None:
                self.multiwfn_commands = self.settings_seq_text.get("1.0", "end")
            commands = self.multiwfn_commands
            effective_commands = "\n".join(
                line for line in commands.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ).strip()
            if not effective_commands:
                effective_commands = DEFAULT_MULTIWFN_COMMANDS.strip()

            run_started_at = time.time() - 2.0
            removed = remove_generated_qtaim_files(input_file.parent, input_stem=input_file.stem)
            if removed:
                self.log("Removed old QTAIM export files before this run:")
                for old_file in removed[:12]:
                    self.log(f"  {old_file.name}")
                if len(removed) > 12:
                    self.log(f"  ... plus {len(removed) - 12} more")
            else:
                self.log("No old QTAIM export files found before this run.")
            self.log("Running Multiwfn...")
            rc = run_multiwfn(
                input_file=input_file,
                multiwfn_exe=self.multiwfn_path.get().strip(),
                commands=effective_commands,
                log_path=log_path,
                timeout_s=int(self.timeout_s.get()),
            )
            self.log(f"Multiwfn log saved: {log_path}")
            if rc != 0:
                self.log(f"Multiwfn returned non-zero code {rc}; attempting to parse any CP/path files already produced.")

            fresh_cp_candidates = list_possible_qtaim_cp_files(input_file, min_mtime=run_started_at)
            if fresh_cp_candidates:
                self.log("Fresh CP/log candidates from this run:")
                for candidate in fresh_cp_candidates[:8]:
                    self.log(f"  {candidate.name}")
            else:
                self.log("No freshly generated CP export detected; parsing the current Multiwfn log instead.")
                fresh_cp_candidates = [log_path] if log_path.exists() else []

            for candidate in fresh_cp_candidates:
                self.cp_file_path.set(str(candidate))
                self.load_cp_file(candidate)
                if self.cps:
                    break

            generated_paths = find_generated_qtaim_path_file(input_file, min_mtime=run_started_at)
            if generated_paths is not None:
                self.path_file_path.set(str(generated_paths))
                self.load_path_file(generated_paths)
            else:
                self.bond_paths = []
                self.path_file_path.set(str(input_file.parent / "paths.txt"))
                possible_paths = list_possible_qtaim_path_files(input_file)
                if possible_paths:
                    self.log("Path-like files were found, but none matched the supported generated path names:")
                    for path_candidate in possible_paths[:8]:
                        self.log(f"  {path_candidate.name}")
                self.log("No generated paths.pdb/paths.txt detected. Exact paths can still be loaded manually via 'Load paths'.")
                self.log("If a BCP is visible but no gold path appears, Multiwfn did not export a parsable path file for this run/menu sequence.")

            if self.cps:
                if self.bond_paths:
                    self.log("CPs and exact paths were parsed. Opening PyVista viewer automatically.")
                else:
                    self.log("CPs were parsed. Opening PyVista viewer automatically without QTAIM paths.")
                self.schedule_final_visualize()
                if bool(self.open_native_after_run.get()):
                    self.open_native_multiwfn_threaded()
            else:
                self.log("No CPs were parsed. Check the generated CP/log file path above.")
        except Exception as exc:
            self.show_exception("Multiwfn run failed", exc)
        finally:
            self.run_in_progress = False

    def parse_log(self):
        try:
            primary = Path(self.cp_file_path.get().strip() or self.log_path.get().strip())
            self.load_cp_file(primary)
            if self.cps:
                return

            input_text = self.input_path.get().strip()
            if not input_text:
                return
            input_file = Path(input_text)
            primary_resolved = primary.expanduser().resolve() if primary.exists() else primary
            for candidate in list_possible_qtaim_cp_files(input_file):
                try:
                    candidate_resolved = candidate.expanduser().resolve()
                except Exception:
                    candidate_resolved = candidate
                if candidate_resolved == primary_resolved:
                    continue
                self.log(f"No CPs found in selected file; trying CP export: {candidate}")
                self.load_cp_file(candidate)
                if self.cps:
                    return
        except Exception as exc:
            self.show_exception("Could not parse CPs", exc)

    def load_cp_file(self, path: Path):
        path = path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(str(path))
        self.cp_file_path.set(str(path))
        self.cps = []
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
        self.log(f"Parsing CPs from: {path}")
        self.log(f"CP source modified: {stamp}; size {path.stat().st_size} bytes")
        self.cps = parse_critical_points_file(path)
        self.cps = convert_cps_to_atom_units(self.cps, self.atoms or None, path.suffix)
        self.log(f"Parsed CPs: {len(self.cps)}")
        counts: Dict[str, int] = {}
        for cp in self.cps:
            counts[normalize_cp_type(cp.cp_type)] = counts.get(normalize_cp_type(cp.cp_type), 0) + 1
        if counts:
            self.log("CP counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
            parsed_norm_types = {normalize_cp_type(cp.cp_type) for cp in self.cps}
            if "(3,-1)" in parsed_norm_types:
                self.show_bcp.set(True)

            preview = []
            for cp in self.cps[:8]:
                preview.append(f"{cp.index}:{normalize_cp_type(cp.cp_type)} ({cp.x:.4f}, {cp.y:.4f}, {cp.z:.4f})")
            self.log("CP preview: " + "; ".join(preview))
            bcp_count = sum(1 for cp in self.cps if normalize_cp_type(cp.cp_type) == "(3,-1)")
            self.log(f"BCPs available for exact Multiwfn path stitching: {bcp_count}")
            if self.atoms:
                bonds = infer_bonds(self.atoms)
                matched, total = count_covalent_bonds_with_nearby_bcp(self.atoms, bonds, self.cps)
                if total:
                    self.log(f"Covalent-bond BCP check: {matched}/{total} inferred covalent bonds have a nearby parsed BCP.")
                    if matched < total:
                        self.log(
                            "Missing covalent BCPs mean the selected/exported Multiwfn CP file does not contain them, "
                            "or they were not classified as BCPs by the parser."
                        )
        else:
            self.log("No CPs detected by parser. Check the Multiwfn log format or export a CP list from Multiwfn.")
            self.log("Accepted simple CP-table format: index  type  x  y  z   e.g. 1  (3,-1)  0.0  1.2  -0.4")

    def parse_paths(self):
        try:
            p = Path(self.path_file_path.get().strip())
            self.load_path_file(p)
        except Exception as exc:
            self.show_exception("Could not parse exact bond paths", exc)

    def load_path_file(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not self.atoms:
            try:
                self.atoms = read_atoms(Path(self.input_path.get().strip()))
            except Exception:
                pass
        if not self.cps:
            cp_candidate = Path(self.cp_file_path.get().strip() or self.log_path.get().strip())
            if cp_candidate.exists():
                try:
                    self.cps = parse_critical_points_file(cp_candidate)
                    self.cps = convert_cps_to_atom_units(self.cps, self.atoms or None, cp_candidate.suffix)
                except Exception:
                    pass
        self.bond_paths = parse_bond_paths_file(path, atoms=self.atoms or None, cps=self.cps or None)
        self.log(f"Parsed exact QTAIM bond paths from {path}")
        self.log("Path summary: " + summarize_bond_paths(self.bond_paths))
        if self.bond_paths:
            lengths = []
            for bp in self.bond_paths[:5]:
                length = 0.0
                for p1, p2 in zip(bp.points, bp.points[1:]):
                    length += math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2)
                lengths.append(f"path {bp.index}: {len(bp.points)} pts, length {length:.3f}")
            self.log("Exact path preview: " + "; ".join(lengths))
        else:
            self.log("No exact paths detected. Expected Multiwfn paths.pdb or text sections starting with 'Path'.")

    def is_plotter_alive(self) -> bool:
        if self.plotter is None:
            return False
        try:
            if getattr(self.plotter, "render_window", None) is None:
                return False
            if getattr(self.plotter, "iren", None) is None:
                return False
            if hasattr(self.plotter, "closed") and self.plotter.closed:
                return False
            return True
        except Exception:
            return False

    def close_plotter_reference(self, close_window: bool = True) -> None:
        if self.plotter is None:
            return
        if close_window:
            try:
                if not (hasattr(self.plotter, "closed") and self.plotter.closed):
                    self.plotter.close()
            except Exception:
                pass
        self.plotter = None

    def ensure_plot_data_loaded(self) -> None:
        if not self.atoms:
            self.load_atoms()
        if not self.cps:
            self.parse_log()

        if bool(self.show_bond_paths.get()) and not self.bond_paths:
            candidate = Path(self.path_file_path.get().strip()) if self.path_file_path.get().strip() else None
            if candidate and candidate.exists():
                self.load_path_file(candidate)

    def update_plot(self):
        try:
            if pv is None:
                raise RuntimeError("PyVista is not installed. Install with: pip install pyvista vtk")

            if self.run_in_progress:
                self.log("QTAIM run is still loading CPs and paths; the final PyVista plot will open automatically.")
                return

            self.ensure_plot_data_loaded()
            self.save_current_graphics_settings()

            if not self.is_plotter_alive():
                self.close_plotter_reference(close_window=False)
                self.plotter = pv.Plotter(window_size=self.pyvista_window_size, lighting="none")

            display_paths = select_bond_paths_by_range(self.bond_paths, self.path_display_range.get())
            draw_qtaim_scene(
                self.plotter,
                atoms=self.atoms,
                cps=self.cps,
                show_ncp=bool(self.show_ncp.get()),
                show_bcp=bool(self.show_bcp.get()),
                show_rcp=bool(self.show_rcp.get()),
                show_ccp=bool(self.show_ccp.get()),
                show_unknown=bool(self.show_unknown.get()),
                show_labels=bool(self.show_labels.get()),
                show_molecule=bool(self.show_molecule.get()),
                show_covalent_bonds=bool(self.show_covalent_bonds.get()),
                show_bond_paths=bool(self.show_bond_paths.get()),
                bond_paths=display_paths,
                atom_scale=float(self.atom_scale.get()),
                cp_scale=float(self.cp_scale.get()),
                bond_radius=float(self.bond_radius.get()),
                background=self.background.get(),
            )
            if self.bond_paths and bool(self.show_bond_paths.get()):
                if len(display_paths) == len(self.bond_paths):
                    self.log(f"PyVista plot updated with exact Multiwfn bond paths: {len(self.bond_paths)}")
                else:
                    self.log(f"PyVista plot updated with selected exact Multiwfn bond paths: {len(display_paths)}/{len(self.bond_paths)}")
            else:
                self.log("PyVista plot updated without QTAIM paths.")

            try:
                initialized = bool(getattr(getattr(self.plotter, "iren", None), "initialized", False))
            except Exception:
                initialized = False
            if initialized:
                self.plotter.render()
            else:
                self.plotter.show(title="QTAIM", interactive_update=True, auto_close=False)
        except Exception as exc:
            self.show_exception("Plot update failed", exc)

    def visualize(self):
        self.close_plotter_reference(close_window=True)
        self.update_plot()

    def reset_view(self):
        self.show_ncp.set(False)
        self.show_bcp.set(True)
        self.show_rcp.set(False)
        self.show_ccp.set(False)
        self.show_unknown.set(False)
        self.show_labels.set(False)
        self.show_molecule.set(True)
        self.show_covalent_bonds.set(True)
        self.show_bond_paths.set(True)
        self.atom_scale.set(0.38)
        self.cp_scale.set(0.14)
        self.bond_radius.set(0.075)
        self.background.set("white")
        self.update_plot()

    def save_image(self):
        if not self.is_plotter_alive():
            messagebox.showerror("No plot", "No active PyVista plot to save. Open or update the viewer first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save QTAIM image",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            image_size = self.selected_image_size()
            if image_size:
                save_pyvista_screenshot(self.plotter, path, self.background.get(), window_size=image_size, scale=1)
            else:
                save_pyvista_screenshot(self.plotter, path, self.background.get())
            self.log(f"Image saved: {path}")
        except Exception as exc:
            self.show_exception("Could not save image", exc)

    def open_nci_qtaim_overlay(self) -> None:
        overlay_script = APP_ROOT / "NCI_QTAIM_overlay" / "nci_qtaim_overlay.py"
        command = [sys.executable, str(overlay_script)]
        self.save_current_graphics_settings()

        wavefunction = self.input_path.get().strip()
        if wavefunction and Path(wavefunction).is_file():
            command.append(wavefunction)

        cp_file = self.cp_file_path.get().strip()
        if cp_file and Path(cp_file).is_file():
            command.extend(["--cp", cp_file])

        path_file = self.path_file_path.get().strip()
        if path_file and Path(path_file).is_file():
            command.extend(["--paths", path_file])

        image_size = self.selected_image_size()
        if image_size is None and self.is_plotter_alive():
            try:
                image_size = tuple(int(v) for v in self.plotter.window_size)
            except Exception:
                image_size = None
        if image_size:
            command.extend(["--image-width", str(image_size[0]), "--image-height", str(image_size[1])])

        command.extend(
            [
                "--background", str(self.background.get()),
                "--show-molecule", "1" if bool(self.show_molecule.get()) else "0",
                "--show-nci", "1",
                "--show-cps", "1" if any(
                    bool(var.get()) for var in (self.show_ncp, self.show_bcp, self.show_rcp, self.show_ccp, self.show_unknown)
                ) else "0",
                "--show-bond-paths", "1" if bool(self.show_bond_paths.get()) else "0",
                "--show-labels", "1" if bool(self.show_labels.get()) else "0",
                "--show-ncp", "1" if bool(self.show_ncp.get()) else "0",
                "--show-bcp", "1" if bool(self.show_bcp.get()) else "0",
                "--show-rcp", "1" if bool(self.show_rcp.get()) else "0",
                "--show-ccp", "1" if bool(self.show_ccp.get()) else "0",
                "--show-unknown", "1" if bool(self.show_unknown.get()) else "0",
                "--show-covalent-bonds", "1" if bool(self.show_covalent_bonds.get()) else "0",
                "--atom-scale", str(float(self.atom_scale.get())),
                "--cp-scale", str(float(self.cp_scale.get())),
                "--bond-radius", str(float(self.bond_radius.get())),
            ]
        )

        try:
            subprocess.Popen(command, cwd=str(overlay_script.parent))
            self.log("Opened NCI + QTAIM overlay.")
        except Exception as exc:
            self.log(f"ERROR: Could not open NCI + QTAIM overlay: {exc}")
            messagebox.showerror("Overlay failed", str(exc), parent=self)

    def open_native_multiwfn_threaded(self):
        try:
            self.ensure_multiwfn_available()
        except Exception as exc:
            self.show_exception("Multiwfn not found", exc)
            return
        t = threading.Thread(target=self.open_native_multiwfn_action, daemon=True)
        t.start()

    def open_native_multiwfn_action(self):
        """
        Open Multiwfn's own visualization branch in a separate run.

        This is intentionally independent from the PyVista/parse run. Multiwfn's native
        graphics window and its closing behavior are controlled by Multiwfn, not by this script.
        The PyVista data already parsed by this script is not affected.
        """
        try:
            input_file = Path(self.input_path.get().strip())
            if not input_file.exists():
                raise FileNotFoundError(str(input_file))

            multiwfn_exe = self.multiwfn_path.get().strip()

            commands = DEFAULT_MULTIWFN_NATIVE_VIEW_COMMANDS
            self.log("Opening Multiwfn native viewer in a separate run...")
            self.log("Native viewer sequence: 2 / 2 / 3 / 0 / q")

            # Use Popen so the GUI is not blocked. Multiwfn controls its own graphics window.
            proc = subprocess.Popen(
                [multiwfn_exe, str(input_file)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=str(input_file.parent),
            )

            try:
                proc.stdin.write(commands)
                proc.stdin.flush()
                proc.stdin.close()
            except Exception:
                pass

            self.log("Multiwfn native viewer launched. It is independent from the PyVista viewer.")
        except Exception as exc:
            self.show_exception("Could not open Multiwfn native viewer", exc)

    def save_table(self):
        try:
            if not self.cps:
                self.parse_log()
            input_file = Path(self.input_path.get().strip())
            default = input_file.with_suffix(".qtaim_cps.tsv")
            out = filedialog.asksaveasfilename(
                title="Save CP table",
                initialfile=default.name,
                initialdir=str(default.parent),
                defaultextension=".tsv",
                filetypes=[("TSV", "*.tsv"), ("Text", "*.txt"), ("All files", "*.*")]
            )
            if out:
                save_cp_table(self.cps, Path(out))
                self.log(f"Saved CP table: {out}")
        except Exception as exc:
            self.show_exception("Could not save CP table", exc)

    def show_exception(self, title: str, exc: Exception):
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log(f"{title}: {exc}")
        self.log(tb)
        try:
            messagebox.showerror(title, f"{exc}")
        except Exception:
            pass

    def on_close(self):
        self.close_plotter_reference(close_window=True)
        self.destroy()


def main():
    initial_input_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = QTAIMGui(initial_input_path)
    app.mainloop()


if __name__ == "__main__":
    main()
