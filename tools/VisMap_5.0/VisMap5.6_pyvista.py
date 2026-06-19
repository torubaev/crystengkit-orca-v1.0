#!/usr/bin/env python3
"""
VisMap GUI + safer launcher for VisMap4.2 workflow

What this version does:
- starts with a GUI
- lets you browse for the input .wfn / .wfx / .fchk file
- lets you set nproc, mode, visualization, and optional CP isovalue
- fixes Windows path handling for Multiwfn.exe
- safely overwrites existing cube/output files instead of crashing
- runs Multiwfn from the folder containing the selected wavefunction file
- keeps original VisMap processing logic as much as possible

Run:
    py VisMapGUI_fixed.py

Optional CLI mode is also supported:
    py VisMapGUI_fixed.py yourfile.wfn -nproc=8 -mode=old -vis=y
"""

import os
import sys
import shutil
import subprocess
import platform
import threading
import time
import json
import webbrowser
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import tkinter.font as tkfont
from pathlib import Path

# ----------------------------
# Config
# ----------------------------

DEFAULT_MULTIWFN_PATHS = [
    r"C:/Multiwfn_2026.2.2_bin_Win64/Multiwfn.exe",
    r"C:\Multiwfn_3.8_dev_bin_Win64\Multiwfn.exe",
    r"C:\Multiwfn\Multiwfn.exe",
    "/opt/Multiwfn/Multiwfn",
    "/opt/multiwfn/Multiwfn",
    "/usr/local/bin/Multiwfn",
    "/usr/bin/Multiwfn",
    "/usr/local/bin/multiwfn",
    "/usr/bin/multiwfn",
]

Multiwfnpath = DEFAULT_MULTIWFN_PATHS[0]
TOOLS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TOOLS_ROOT.parent
ESP_ICON_PATH = TOOLS_ROOT / "images" / "tr_ESP_icon.png"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
CONTACT_EMAIL = "torubaev(at)gmail.com"
LINKEDIN_URL = "https://www.linkedin.com/in/torubaev/"
ORIGINAL_VISMAP_URL = "https://github.com/aaan1s/VisMap"
README_LINK_TEXT = "README section: ESP / VisMap"
README_ANCHOR = "esp--vismap"


def wiki_url():
    return GITHUB_URL + f"#{README_ANCHOR}"


def open_readme_or_wiki():
    webbrowser.open(wiki_url(), new=2)
ABOUT_PURPOSE = (
    "Creates electrostatic-potential maps on electron-density surfaces. This version is based "
    "on the original VisMap code by aaan1s and adapts it for this suite with a GUI for ESP "
    "data generation and plotting, extrema plotting, and PyVista visualization instead of "
    "Mayavi. It uses wavefunction files such as .wfn, .wfx, or .fchk."
)
RECENT_FILES_PATH = Path.home() / ".vismap_recent_files.json"
MAX_RECENT_FILES = 5
IMAGE_PRESETS = {
    "Viewer window": None,
    "Preview: 1600 x 1200 px": (1600, 1200),
    "Paper 300 dpi: 3000 x 2250 px": (3000, 2250),
    "Paper 600 dpi: 6000 x 4500 px": (6000, 4500),
    "Poster / high-res: 8000 x 6000 px": (8000, 6000),
}
DEFAULT_IMAGE_PRESET = "Paper 300 dpi: 3000 x 2250 px"
BOHR_PER_ANGSTROM = 1.0 / 0.529177210903
HQ_ATOM_RESOLUTION = 96
HQ_BOND_RESOLUTION = 72
HQ_BACKGROUND_TOP = {
    "white": "#eef3f8",
    "black": "#171b22",
}


def selected_image_size(var=None):
    name = var.get() if var is not None else DEFAULT_IMAGE_PRESET
    return IMAGE_PRESETS.get(name, IMAGE_PRESETS[DEFAULT_IMAGE_PRESET])


def should_use_transparent_png(path, background):
    return str(path).lower().endswith(".png") and str(background or "").strip().lower() == "white"


def save_pyvista_screenshot(plotter, path, background, **kwargs):
    if should_use_transparent_png(path, background):
        try:
            return plotter.screenshot(path, transparent_background=True, **kwargs)
        except TypeError:
            pass
    return plotter.screenshot(path, **kwargs)


def bring_pyvista_window_to_front(plotter, delay_s=0.25):
    def worker():
        try:
            if delay_s > 0:
                time.sleep(delay_s)
            render_window = getattr(plotter, "ren_win", None) or getattr(plotter, "render_window", None)
            if render_window is None:
                return
            handle = None
            for attr in ("GetGenericWindowId", "GetWindowId"):
                getter = getattr(render_window, attr, None)
                if callable(getter):
                    handle = getter()
                    if handle:
                        break
            if not handle or os.name != "nt":
                return
            hwnd = int(handle)
            import ctypes

            user32 = ctypes.windll.user32
            flags = 0x0001 | 0x0002 | 0x0040
            user32.ShowWindow(hwnd, 5)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def load_header_icon(path, max_size=56):
    if not path.is_file():
        return None
    img = tk.PhotoImage(file=str(path))
    factor = max(1, int(max(img.width() / max_size, img.height() / max_size) + 0.999))
    if factor > 1:
        img = img.subsample(factor, factor)
    return img


def open_about_dialog(parent, title, icon_path, purpose):
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
        ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=10, sticky="n", padx=(0, 18))

    ttk.Label(box, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
    ttk.Label(box, text=purpose, justify="left", wraplength=420).grid(row=1, column=1, sticky="w", pady=(8, 0))
    ttk.Separator(box, orient="horizontal").grid(row=2, column=1, sticky="ew", pady=(12, 8))
    ttk.Label(box, text="Original VisMap by aaan1s").grid(row=3, column=1, sticky="w")
    original_link = ttk.Label(box, text=ORIGINAL_VISMAP_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
    original_link.grid(row=4, column=1, sticky="w", pady=(2, 0))
    original_link.bind("<Button-1>", lambda _event: webbrowser.open(ORIGINAL_VISMAP_URL))
    ttk.Label(box, text="GitHub").grid(row=5, column=1, sticky="w", pady=(8, 0))
    github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
    github_link.grid(row=6, column=1, sticky="w", pady=(2, 0))
    github_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL))
    ttk.Label(box, text="Documentation").grid(row=7, column=1, sticky="w", pady=(8, 0))
    wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
    wiki_link.grid(row=8, column=1, sticky="w", pady=(2, 0))
    wiki_link.bind("<Button-1>", lambda _event: open_readme_or_wiki())
    ttk.Separator(box, orient="horizontal").grid(row=9, column=1, sticky="ew", pady=(12, 8))
    ttk.Label(box, text=COPYRIGHT_NOTE, foreground="#4b5563").grid(row=10, column=1, sticky="w")
    contact = ttk.Frame(box)
    contact.grid(row=11, column=1, sticky="w", pady=(7, 0))
    ttk.Label(contact, text=f"Email: {CONTACT_EMAIL}").grid(row=0, column=0, sticky="w")
    linkedin_icon = tk.Label(contact, text="in", bg="#0a66c2", fg="white", cursor="hand2", font=("Arial", 9, "bold"), padx=4, pady=1)
    linkedin_icon.grid(row=0, column=1, padx=(10, 0))
    linkedin_icon.bind("<Button-1>", lambda _event: webbrowser.open(LINKEDIN_URL))

    ttk.Button(box, text="Close", command=win.destroy).grid(row=12, column=0, columnspan=2, sticky="e", pady=(14, 0))
    win.geometry("610x410")
    win.minsize(550, 380)
    win.grab_set()


def keep_entry_end_visible(entry, variable=None):
    def show_end(*_args):
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


def bind_mousewheel_to_canvas(canvas, *_hover_widgets):
    def _pointer_is_over_canvas():
        try:
            x = canvas.winfo_pointerx()
            y = canvas.winfo_pointery()
            left = canvas.winfo_rootx()
            top = canvas.winfo_rooty()
            return left <= x < left + canvas.winfo_width() and top <= y < top + canvas.winfo_height()
        except tk.TclError:
            return False

    def _can_scroll():
        try:
            first, last = canvas.yview()
            return first > 0.0 or last < 1.0
        except tk.TclError:
            return False

    def _wheel_units(event):
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


def load_recent_files():
    try:
        data = json.loads(RECENT_FILES_PATH.read_text(encoding="utf-8"))
        values = data.get("recent_input_files", [])
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()][:MAX_RECENT_FILES]
    except Exception:
        pass
    return []


def save_recent_files(paths):
    try:
        RECENT_FILES_PATH.write_text(json.dumps({"recent_input_files": paths[:MAX_RECENT_FILES]}, indent=2), encoding="utf-8")
    except Exception:
        pass


def remember_recent_file(path, paths):
    clean = str(path or "").strip().strip('"')
    if not clean:
        return paths
    try:
        clean = os.path.abspath(clean)
    except Exception:
        pass
    updated = [clean] + [item for item in paths if os.path.normcase(item) != os.path.normcase(clean)]
    updated = updated[:MAX_RECENT_FILES]
    save_recent_files(updated)
    return updated


def configure_pyvista_defaults(pv_module, plotter, background="white", parallel_projection=True, antialiasing=None, extent=1.0):
    """Apply conservative PyVista defaults that work on limited OpenGL contexts."""
    try:
        pv_module.global_theme.multi_samples = 0
    except Exception:
        pass

    try:
        pv_module.global_theme.smooth_shading = False
    except Exception:
        pass

    try:
        bg = str(background or "white").strip().lower()
        plotter.set_background(background, top=HQ_BACKGROUND_TOP.get(bg))
    except Exception:
        try:
            plotter.set_background("white")
        except Exception:
            pass

    if antialiasing:
        try:
            plotter.enable_anti_aliasing(antialiasing)
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
        ("headlight", None, 0.72),
        ("camera light", None, 0.34),
        ("scene light", (2.6 * extent, -3.4 * extent, 4.2 * extent), 0.56),
        ("scene light", (-3.0 * extent, 2.4 * extent, 3.6 * extent), 0.30),
        ("scene light", (0.0, 3.2 * extent, -2.6 * extent), 0.18),
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




def configure_molecule_renderer_lights(pv_module, renderer, extent=1.0):
    try:
        renderer.RemoveAllLights()
    except Exception:
        pass

    try:
        extent = max(float(extent), 1.0)
    except Exception:
        extent = 1.0

    light_specs = [
        ("headlight", None, 0.72),
        ("camera light", None, 0.34),
        ("scene light", (2.6 * extent, -3.4 * extent, 4.2 * extent), 0.56),
        ("scene light", (-3.0 * extent, 2.4 * extent, 3.6 * extent), 0.30),
        ("scene light", (0.0, 3.2 * extent, -2.6 * extent), 0.18),
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
            renderer.AddLight(light)
        except Exception:
            pass


ELEMENT_COLORS = {
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

COVALENT_RADII = {
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84, "C": 0.76,
    "N": 0.71, "O": 0.66, "F": 0.57, "Ne": 0.58, "Na": 1.66, "Mg": 1.41,
    "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Ar": 1.06,
    "K": 2.03, "Ca": 1.76, "Sc": 1.70, "Ti": 1.60, "V": 1.53, "Cr": 1.39,
    "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20, "Kr": 1.16,
    "Rb": 2.20, "Sr": 1.95, "Y": 1.90, "Zr": 1.75, "Nb": 1.64, "Mo": 1.54,
    "Tc": 1.47, "Ru": 1.46, "Rh": 1.42, "Pd": 1.39, "Ag": 1.45, "Cd": 1.44,
    "In": 1.42, "Sn": 1.39, "Sb": 1.39, "Te": 1.38, "I": 1.39, "Xe": 1.40,
    "Cs": 2.44, "Ba": 2.15, "La": 2.07, "Ce": 2.04, "Pr": 2.03, "Nd": 2.01,
    "Pm": 1.99, "Sm": 1.98, "Eu": 1.98, "Gd": 1.96, "Tb": 1.94, "Dy": 1.92,
    "Ho": 1.92, "Er": 1.89, "Tm": 1.90, "Yb": 1.87, "Lu": 1.87, "Hf": 1.75,
    "Ta": 1.70, "W": 1.62, "Re": 1.51, "Os": 1.44, "Ir": 1.41, "Pt": 1.36,
    "Au": 1.36, "Hg": 1.32, "Tl": 1.45, "Pb": 1.46, "Bi": 1.48, "Po": 1.40,
    "At": 1.50, "Rn": 1.50, "Fr": 2.60, "Ra": 2.21, "Ac": 2.15, "Th": 2.06,
    "Pa": 2.00, "U": 1.96, "Np": 1.90, "Pu": 1.87, "Am": 1.80, "Cm": 1.69,
}

COVALENT_RADIUS_VARIANTS = {
    "C_sp3": 0.76,
    "C_sp2": 0.73,
    "C_sp": 0.69,
    "Mn_low_spin": 1.39,
    "Mn_high_spin": 1.61,
    "Fe_low_spin": 1.32,
    "Fe_high_spin": 1.52,
    "Co_low_spin": 1.26,
    "Co_high_spin": 1.50,
}

FALLBACK_COVALENT_RADII = COVALENT_RADII


def hex_to_rgb01(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def molecule_material_parameters():
    return {
        "ambient": 0.34,
        "diffuse": 0.72,
        "specular": 0.34,
        "specular_power": 38,
    }


def display_atom_radius_from_number(atomic_number):
    try:
        symbol = dnc2all[int(atomic_number)][0]
    except Exception:
        symbol = ""
    covalent = COVALENT_RADII.get(symbol, 0.77)
    return float(0.5 * np.clip(covalent * 0.42, 0.16, 0.55) * BOHR_PER_ANGSTROM)


def atom_color_from_number(atomic_number):
    try:
        symbol = dnc2all[int(atomic_number)][0]
    except Exception:
        symbol = ""
    return hex_to_rgb01(ELEMENT_COLORS.get(symbol, "#FF69B4"))


def cylinder_between(pv_module, p1, p2, radius=0.075, resolution=HQ_BOND_RESOLUTION):
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

# dictionary of (nuclear_charge : Nucleus, vdW radii in Angstroms)
dnc2all = {1: ['H', 1.09, 0.23, 1.00794, 0.99609375, 0.9765625, 0.80078125],
           2: ['He', 1.40, 1.50, 4.002602, 0.72265625, 0.82421875, 0.9296875],
           3: ['Li', 1.82, 1.28, 6.941, 0.7421875, 0.7421875, 0.7421875],
           4: ['Be', 2.00, 0.96, 9.012182, 0.7421875, 0.7421875, 0.7421875],
           5: ['B', 2.00, 0.83, 10.811, 0.625, 0.234375, 0.234375],
           6: ['C', 1.70, 0.68, 12.0107, 0.328125, 0.328125, 0.328125],
           7: ['N', 1.55, 0.68, 14.0067, 0.1171875, 0.5625, 0.99609375],
           8: ['O', 1.52, 0.68, 15.9994, 0.99609375, 0.0, 0.0],
           9: ['F', 1.47, 0.64, 18.998403, 0.99609375, 0.99609375, 0.0],
           10: ['Ne', 1.54, 1.50, 20.1797, 0.72265625, 0.82421875, 0.9296875],
           11: ['Na', 2.27, 1.66, 22.98977, 0.7421875, 0.7421875, 0.7421875],
           12: ['Mg', 1.73, 1.41, 24.305, 0.7421875, 0.7421875, 0.7421875],
           13: ['Al', 2.00, 1.21, 26.981538, 0.7421875, 0.7421875, 0.7421875],
           14: ['Si', 2.10, 1.20, 28.0855, 0.82421875, 0.82421875, 0.82421875],
           15: ['P', 1.80, 1.05, 30.973761, 0.99609375, 0.546875, 0.0],
           16: ['S', 1.80, 1.02, 32.065, 0.99609375, 0.9609375, 0.55859375],
           17: ['Cl', 1.75, 0.99, 35.453, 0.0, 0.99609375, 0.0],
           18: ['Ar', 1.88, 1.51, 39.948, 0.72265625, 0.82421875, 0.9296875],
           19: ['K', 2.75, 2.03, 39.0983, 0.7421875, 0.7421875, 0.7421875],
           20: ['Ca', 2.00, 1.76, 40.078, 0.7421875, 0.7421875, 0.7421875],
           21: ['Sc', 2.00, 1.70, 44.95591, 0.7421875, 0.7421875, 0.7421875],
           22: ['Ti', 2.00, 1.60, 47.867, 0.7421875, 0.7421875, 0.7421875],
           23: ['V', 2.00, 1.53, 50.9415, 0.7421875, 0.7421875, 0.7421875],
           24: ['Cr', 2.00, 1.39, 51.9961, 0.7421875, 0.7421875, 0.7421875],
           25: ['Mn', 2.50, 1.61, 54.938049, 0.7421875, 0.7421875, 0.7421875],
           26: ['Fe', 2.00, 1.52, 55.845, 0.7421875, 0.7421875, 0.7421875],
           27: ['Co', 2.00, 1.26, 58.9332, 0.7421875, 0.7421875, 0.7421875],
           28: ['Ni', 1.63, 1.24, 58.6934, 0.7421875, 0.7421875, 0.7421875],
           29: ['Cu', 1.40, 1.32, 63.546, 0.99609375, 0.5078125, 0.27734375],
           30: ['Zn', 1.39, 1.22, 65.409, 0.7421875, 0.7421875, 0.7421875],
           31: ['Ga', 1.87, 1.22, 69.723, 0.7421875, 0.7421875, 0.7421875],
           32: ['Ge', 2.00, 1.17, 72.64, 0.7421875, 0.7421875, 0.7421875],
           33: ['As', 1.85, 1.21, 74.9216, 0.7421875, 0.7421875, 0.7421875],
           34: ['Se', 1.90, 1.22, 78.96, 0.7421875, 0.7421875, 0.7421875],
           35: ['Br', 1.85, 1.21, 79.904, 0.7421875, 0.5078125, 0.234375],
           36: ['Kr', 2.02, 1.50, 83.798, 0.72265625, 0.82421875, 0.9296875],
           37: ['Rb', 2.00, 2.20, 85.4678, 0.7421875, 0.7421875, 0.7421875],
           38: ['Sr', 2.00, 1.95, 87.62, 0.7421875, 0.7421875, 0.7421875],
           39: ['Y', 2.00, 1.90, 88.90585, 0.7421875, 0.7421875, 0.7421875],
           40: ['Zr', 2.00, 1.75, 91.224, 0.7421875, 0.7421875, 0.7421875],
           41: ['Nb', 2.00, 1.64, 92.90638, 0.7421875, 0.7421875, 0.7421875],
           42: ['Mo', 2.00, 1.54, 95.94, 0.7421875, 0.7421875, 0.7421875],
           43: ['Tc', 2.00, 1.47, 98.0, 0.7421875, 0.7421875, 0.7421875],
           44: ['Ru', 2.00, 1.46, 101.07, 0.7421875, 0.7421875, 0.7421875],
           45: ['Rh', 2.00, 1.45, 102.9055, 0.7421875, 0.7421875, 0.7421875],
           46: ['Pd', 1.63, 1.39, 106.42, 0.7421875, 0.7421875, 0.7421875],
           47: ['Ag', 1.72, 1.45, 107.8682, 0.99609375, 0.99609375, 0.99609375],
           48: ['Cd', 1.58, 1.44, 112.411, 0.7421875, 0.7421875, 0.7421875],
           49: ['In', 1.93, 1.42, 114.818, 0.7421875, 0.7421875, 0.7421875],
           50: ['Sn', 2.17, 1.39, 118.71, 0.7421875, 0.7421875, 0.7421875],
           51: ['Sb', 2.00, 1.39, 121.76, 0.7421875, 0.7421875, 0.7421875],
           52: ['Te', 2.06, 1.47, 127.6, 0.7421875, 0.7421875, 0.7421875],
           53: ['I', 2.58, 1.40, 126.90447, 0.625, 0.125, 0.9375],
           54: ['Xe', 2.16, 1.50, 131.293, 0.72265625, 0.82421875, 0.9296875],
           55: ['Cs', 2.00, 2.44, 132.90545, 0.7421875, 0.7421875, 0.7421875],
           56: ['Ba', 2.00, 2.15, 137.327, 0.7421875, 0.7421875, 0.7421875],
           57: ['La', 2.00, 2.07, 138.9055, 0.7421875, 0.7421875, 0.7421875],
           58: ['Ce', 2.00, 2.04, 140.116, 0.7421875, 0.7421875, 0.7421875],
           59: ['Pr', 2.00, 2.03, 140.90765, 0.7421875, 0.7421875, 0.7421875],
           60: ['Nd', 2.00, 2.01, 144.24, 0.7421875, 0.7421875, 0.7421875],
           61: ['Pm', 2.00, 1.99, 145.0, 0.7421875, 0.7421875, 0.7421875],
           62: ['Sm', 2.00, 1.98, 150.36, 0.7421875, 0.7421875, 0.7421875],
           63: ['Eu', 2.00, 1.98, 151.964, 0.7421875, 0.7421875, 0.7421875],
           64: ['Gd', 2.00, 1.96, 157.25, 0.7421875, 0.7421875, 0.7421875],
           65: ['Tb', 2.00, 1.94, 158.92534, 0.7421875, 0.7421875, 0.7421875],
           66: ['Dy', 2.00, 1.92, 162.5, 0.7421875, 0.7421875, 0.7421875],
           67: ['Ho', 2.00, 1.92, 164.93032, 0.7421875, 0.7421875, 0.7421875],
           68: ['Er', 2.00, 1.89, 167.259, 0.7421875, 0.7421875, 0.7421875],
           69: ['Tm', 2.00, 1.90, 168.93421, 0.7421875, 0.7421875, 0.7421875],
           70: ['Yb', 2.00, 1.87, 173.04, 0.7421875, 0.7421875, 0.7421875],
           71: ['Lu', 2.00, 1.87, 174.967, 0.7421875, 0.7421875, 0.7421875],
           72: ['Hf', 2.00, 1.75, 178.49, 0.7421875, 0.7421875, 0.7421875],
           73: ['Ta', 2.00, 1.70, 180.9479, 0.7421875, 0.7421875, 0.7421875],
           74: ['W', 2.00, 1.62, 183.84, 0.7421875, 0.7421875, 0.7421875],
           75: ['Re', 2.00, 1.51, 186.207, 0.7421875, 0.7421875, 0.7421875],
           76: ['Os', 2.00, 1.44, 190.23, 0.7421875, 0.7421875, 0.7421875],
           77: ['Ir', 2.00, 1.41, 192.217, 0.7421875, 0.7421875, 0.7421875],
           78: ['Pt', 1.72, 1.36, 195.078, 0.7421875, 0.7421875, 0.7421875],
           79: ['Au', 1.66, 1.50, 196.96655, 0.99609375, 0.83984375, 0.0],
           80: ['Hg', 1.55, 1.32, 200.59, 0.7421875, 0.7421875, 0.7421875],
           81: ['Tl', 1.96, 1.45, 204.3833, 0.7421875, 0.7421875, 0.7421875],
           82: ['Pb', 2.02, 1.46, 207.2, 0.7421875, 0.7421875, 0.7421875],
           83: ['Bi', 2.00, 1.48, 208.98038, 0.7421875, 0.7421875, 0.7421875],
           84: ['Po', 2.00, 1.40, 290.0, 0.7421875, 0.7421875, 0.7421875],
           85: ['At', 2.00, 1.21, 210.0, 0.7421875, 0.7421875, 0.7421875],
           86: ['Rn', 2.00, 1.50, 222.0, 0.72265625, 0.82421875, 0.9296875],
           87: ['Fr', 2.00, 2.60, 223.0, 0.7421875, 0.7421875, 0.7421875],
           88: ['Ra', 2.00, 2.21, 226.0, 0.7421875, 0.7421875, 0.7421875],
           89: ['Ac', 2.00, 2.15, 227.0, 0.7421875, 0.7421875, 0.7421875],
           90: ['Th', 2.00, 2.06, 232.0381, 0.7421875, 0.7421875, 0.7421875],
           91: ['Pa', 2.00, 2.00, 231.03588, 0.7421875, 0.7421875, 0.7421875],
           92: ['U', 1.86, 1.96, 238.02891, 0.7421875, 0.7421875, 0.7421875],
           93: ['Np', 2.00, 1.90, 237.0, 0.7421875, 0.7421875, 0.7421875],
           94: ['Pu', 2.00, 1.87, 244.0, 0.7421875, 0.7421875, 0.7421875],
           95: ['Am', 2.00, 1.80, 243.0, 0.7421875, 0.7421875, 0.7421875],
           96: ['Cm', 2.00, 1.69, 247.0, 0.7421875, 0.7421875, 0.7421875],
           97: ['Bk', 2.00, 1.54, 247.0, 0.7421875, 0.7421875, 0.7421875],
           98: ['Cf', 2.00, 1.83, 251.0, 0.7421875, 0.7421875, 0.7421875],
           99: ['Es', 2.00, 1.50, 252.0, 0.7421875, 0.7421875, 0.7421875],
           100: ['Fm', 2.00, 1.50, 257.0, 0.7421875, 0.7421875, 0.7421875],
           101: ['Md', 2.00, 1.50, 258.0, 0.7421875, 0.7421875, 0.7421875],
           102: ['No', 2.00, 1.50, 259.0, 0.7421875, 0.7421875, 0.7421875],
           103: ['Lr', 2.00, 1.50, 262.0, 0.7421875, 0.7421875, 0.7421875]
           }


# ----------------------------
# Helpers
# ----------------------------

def find_multiwfn_path():
    env_path = os.environ.get("Multiwfnpath")
    if env_path:
        expanded = os.path.expanduser(os.path.expandvars(env_path))
        if os.path.isfile(expanded):
            return expanded
        if os.path.isdir(expanded):
            for exe_name in ("Multiwfn.exe", "Multiwfn", "multiwfn"):
                candidate = os.path.join(expanded, exe_name)
                if os.path.exists(candidate):
                    return candidate

    for exe_name in ("Multiwfn.exe", "Multiwfn", "multiwfn"):
        found = shutil.which(exe_name)
        if found:
            return found

    for p in DEFAULT_MULTIWFN_PATHS:
        if os.path.exists(p):
            return p

    return ""


def likely_multiwfn_search_roots():
    roots = []

    def add(path):
        if path and os.path.isdir(path):
            roots.append(os.path.abspath(path))

    system_name = platform.system()
    if system_name == "Windows":
        for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE"):
            add(os.environ.get(key))
        add("C:/")
    else:
        for path in ("/opt", "/usr/local", "/usr/local/bin", "/usr/bin", os.path.expanduser("~")):
            add(path)

    unique = []
    seen = set()
    for root in roots:
        key = os.path.normcase(os.path.abspath(root))
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def find_multiwfn_deep(max_seconds=18.0, max_visited=70000, max_depth=6):
    quick = find_multiwfn_path()
    if quick:
        return quick

    target_names = {"multiwfn", "multiwfn.exe"}
    skip_dirs = {
        "$Recycle.Bin", ".git", ".hg", ".svn", "__pycache__", "node_modules",
        "System Volume Information", "Windows", "WinSxS", "Microsoft", "Packages", "Temp", "tmp",
    }
    started = time.monotonic()
    visited = 0

    def timed_out():
        return (time.monotonic() - started) > max_seconds

    def scan(folder, depth):
        nonlocal visited
        if timed_out() or visited >= max_visited or depth > max_depth:
            return ""
        try:
            with os.scandir(folder) as iterator:
                entries = list(iterator)
        except (OSError, PermissionError):
            return ""
        for entry in entries:
            if timed_out() or visited >= max_visited:
                return ""
            visited += 1
            try:
                if entry.is_file(follow_symlinks=False) and entry.name.lower() in target_names:
                    return os.path.abspath(entry.path)
                if entry.is_dir(follow_symlinks=False) and entry.name not in skip_dirs:
                    found = scan(entry.path, depth + 1)
                    if found:
                        return found
            except (OSError, PermissionError):
                continue
        return ""

    for root in likely_multiwfn_search_roots():
        found = scan(root, 0)
        if found:
            return found
        if timed_out():
            break
    return ""


def resolve_multiwfn_executable(selected_multiwfn):
    raw = (selected_multiwfn or "").strip()
    if raw:
        expanded = os.path.expanduser(os.path.expandvars(raw))
        if os.path.exists(expanded):
            return os.path.abspath(expanded)
        found = shutil.which(raw)
        if found:
            return found
    return find_multiwfn_path()


def is_valid_multiwfn_executable(path):
    raw = (path or "").strip()
    if not raw:
        return False
    expanded = os.path.expanduser(os.path.expandvars(raw))
    return os.path.exists(expanded) or shutil.which(raw) is not None


def safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def safe_move(src, dst):
    if not os.path.exists(src):
        raise FileNotFoundError(f"Expected output file was not created: {src}")
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(src, dst)


def base_name_no_ext(path):
    return os.path.splitext(os.path.abspath(path))[0]


def run_command_capture(cmd, cwd=None):
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        shell=False
    )
    return proc.returncode, proc.stdout, proc.stderr


# ----------------------------
# Global runtime variables
# ----------------------------

inputfile = ""
fname = ""
nproc = "4"
mode = "old"
vis = "y"
PreGenCP = False
CPisov = None
workdir = ""
mwfn_exe = ""

APP_STATE = {
    "root": None,
    "status_label": None,
    "progress_var": None,
    "progress_label": None,
    "extrema_text": None,
    "viewer_controls": [],
    "extrema_scrollbar": None,
    "multiwfn_path": "",
    "multiwfn_search_done": False,
}

VIEWER_STATE = None


def _get_screen_size():
    root = APP_STATE.get("root")
    try:
        if root is not None and root.winfo_exists():
            return int(root.winfo_screenwidth()), int(root.winfo_screenheight())
    except Exception:
        pass
    try:
        probe = tk.Tk()
        probe.withdraw()
        width = int(probe.winfo_screenwidth())
        height = int(probe.winfo_screenheight())
        probe.destroy()
        return width, height
    except Exception:
        return 1920, 1080


def _main_window_size():
    screen_w, screen_h = _get_screen_size()
    width = int(screen_w * 0.95)
    height = int(screen_h * 0.80)
    width = min(width, 1400)
    return width, height


def _viewer_window_size():
    screen_w, screen_h = _get_screen_size()
    root = APP_STATE.get("root")
    if root is not None:
        try:
            root.update_idletasks()
            gui_x = int(root.winfo_rootx())
            gui_y = int(root.winfo_rooty())
            gui_w = int(root.winfo_width())
            gui_h = int(root.winfo_height())
            width = max(screen_w - (gui_x + gui_w) - 28, 720)
            height = max(1, int(screen_h * 0.80))
            width = min(width, max(screen_w - 40, 720))
            return width, height
        except Exception:
            pass
    width = int(screen_w * 0.95)
    height = int(screen_h * 0.80)
    width = min(width, 1400)
    return width, height


# ----------------------------
# Multiwfn execution
# ----------------------------

def Run_MWFN(mytext, needout=False):
    inp_path = os.path.join(workdir, "myprog.inp")
    out_path = os.path.join(workdir, "myprog.out")

    with open(inp_path, "w", newline="\n") as inp:
        inp.write("\n".join(mytext) + "\n")

    with open(inp_path, "r") as fin:
        if needout:
            with open(out_path, "w", newline="\n") as fout:
                proc = subprocess.run(
                    [mwfn_exe, inputfile],
                    stdin=fin,
                    stdout=fout,
                    stderr=subprocess.STDOUT,
                    cwd=workdir,
                    text=True,
                    shell=False
                )
        else:
            proc = subprocess.run(
                [mwfn_exe, inputfile],
                stdin=fin,
                cwd=workdir,
                text=True,
                shell=False
            )

    safe_remove(inp_path)

    # Multiwfn may exit non-zero after finishing useful work if scripted input ended.
    # We do not hard-fail here; downstream file existence is the real criterion.
    return proc.returncode


def ReadCUB(inputcube):
    CENTERS = []
    Scalars = []
    with open(inputcube, "r") as cube:
        lines = cube.readlines()[2:]
        nat = int(lines[0].split()[0])
        pointsv1 = int(lines[1].split()[0])
        pointsv2 = int(lines[2].split()[0])
        pointsv3 = int(lines[3].split()[0])

        origin = np.array([float(x) for x in lines[0].split()[-3:]])
        v1 = np.array([float(x) for x in lines[1].split()[1:]])
        v2 = np.array([float(x) for x in lines[2].split()[1:]])
        v3 = np.array([float(x) for x in lines[3].split()[1:]])

        for i in range(nat):
            line = lines[4 + i].split()
            CENTERS.append([int(line[0])] + [float(x) for x in line[2:]] + [dnc2all[int(line[0])][0] + str(i + 1)])
        for line in lines[4 + nat:]:
            Scalars += [float(x) for x in line.split()]

        print("Found", len(Scalars), "Scalars in", inputcube)

    XYZS_Data = [origin, v1, v2, v3, pointsv1, pointsv2, pointsv3, Scalars]
    return XYZS_Data, CENTERS


def CalcCub(IsCalced, fname_base):
    dens_target = fname_base + "_Dens.cub"
    esp_target = fname_base + "_ESP.cub"
    update_progress(10, "Checking cube files...")

    if IsCalced[0] is False:
        print("Calculating Density cube")
        update_progress(20, "Generating density cube with Multiwfn...")
        safe_remove(os.path.join(workdir, "density.cub"))

        if IsCalced[1]:
            text = ["1000", "10", nproc, "5", "1", "8", esp_target, "2"]
            Run_MWFN(text, False)
        else:
            text = ["1000", "10", nproc, "5", "1", "2", "2"]
            Run_MWFN(text, False)

        safe_move(os.path.join(workdir, "density.cub"), dens_target)
        IsCalced[0] = True
        update_progress(50, "Density cube generated.")
    else:
        update_progress(35, "Density cube already exists; reusing it.")

    if IsCalced[1] is False:
        print("Calculating ESP cube")
        update_progress(55, "Generating ESP cube with Multiwfn...")
        safe_remove(os.path.join(workdir, "totesp.cub"))

        if IsCalced[0]:
            text = ["1000", "10", nproc, "5", "12", "8", dens_target, "2"]
            Run_MWFN(text, False)
        else:
            text = ["1000", "10", nproc, "5", "12", "2", "2"]
            Run_MWFN(text, False)

        safe_move(os.path.join(workdir, "totesp.cub"), esp_target)
        IsCalced[1] = True
        update_progress(75, "ESP cube generated.")
    else:
        update_progress(70, "ESP cube already exists; reusing it.")


def CalcPoints(isoval):
    print("Searching surfanalysis.txt file with points")
    out_name = fname + "_sa_" + str(isoval) + ".txt"

    if not os.path.exists(out_name):
        print("File not found. Calling Multiwfn for min/max locating")
        safe_remove(os.path.join(workdir, "surfanalysis.txt"))
        text = ["1000", "10", nproc, "12", "1", "1", str(isoval), "0", "1"]
        Run_MWFN(text, False)
        safe_move(os.path.join(workdir, "surfanalysis.txt"), out_name)

    MAXMIN = []
    with open(out_name, "r") as out:
        for line in out:
            line = line.split()
            if len(line) > 5:
                if "*" not in line and "eV" not in line:
                    MAXMIN.append([float(line[3])] + [float(x) / 0.529 for x in line[4:]])
                elif "*" in line and "eV" not in line:
                    MAXMIN.append([float(line[4])] + [float(x) / 0.529 for x in line[5:]])

    print("Located", len(MAXMIN), "extremum points on the surface")
    return MAXMIN


def covalent_radius_from_number(atomic_number):
    try:
        symbol = dnc2all[int(atomic_number)][0]
    except Exception:
        symbol = ""
    return COVALENT_RADII.get(symbol, 0.77)


def BuildBondPairs(CENTERS, scale=1.20):
    bond_pairs = []
    for i, atom1 in enumerate(CENTERS):
        pos1 = np.array(atom1[1:4], dtype=float)
        radius1 = covalent_radius_from_number(atom1[0]) * BOHR_PER_ANGSTROM
        for j in range(i + 1, len(CENTERS)):
            atom2 = CENTERS[j]
            pos2 = np.array(atom2[1:4], dtype=float)
            radius2 = covalent_radius_from_number(atom2[0]) * BOHR_PER_ANGSTROM
            dist = np.linalg.norm(pos1 - pos2)
            if 1.0e-8 < dist <= scale * (radius1 + radius2):
                bond_pairs.append((i, j))
    return bond_pairs


def BuildPyVistaGrid(CUBdat, CUBdatESP, xx, yy, zz):
    import pyvista as pv

    shape = CUBdat.shape
    if shape != CUBdatESP.shape:
        raise ValueError("Density and ESP grids have different shapes.")

    if xx.shape != shape or yy.shape != shape or zz.shape != shape:
        raise ValueError("Coordinate grids and scalar grids have inconsistent shapes.")

    image = pv.ImageData()
    image.dimensions = np.array(shape, dtype=int)
    image.origin = (float(xx[0, 0, 0]), float(yy[0, 0, 0]), float(zz[0, 0, 0]))

    spacing_x = float(np.linalg.norm([xx[1, 0, 0] - xx[0, 0, 0], yy[1, 0, 0] - yy[0, 0, 0], zz[1, 0, 0] - zz[0, 0, 0]])) if shape[0] > 1 else 1.0
    spacing_y = float(np.linalg.norm([xx[0, 1, 0] - xx[0, 0, 0], yy[0, 1, 0] - yy[0, 0, 0], zz[0, 1, 0] - zz[0, 0, 0]])) if shape[1] > 1 else 1.0
    spacing_z = float(np.linalg.norm([xx[0, 0, 1] - xx[0, 0, 0], yy[0, 0, 1] - yy[0, 0, 0], zz[0, 0, 1] - zz[0, 0, 0]])) if shape[2] > 1 else 1.0
    image.spacing = (spacing_x, spacing_y, spacing_z)

    image.point_data["Density"] = np.ascontiguousarray(CUBdat).ravel(order="F")
    image.point_data["ESP"] = np.ascontiguousarray(CUBdatESP).ravel(order="F")
    image.set_active_scalars("Density")
    return image


def update_status(message, color="blue"):
    label = APP_STATE.get("status_label")
    if label is not None:
        label.config(text=message, fg=color)
        try:
            label.update_idletasks()
        except Exception:
            pass


def update_progress(percent, message=None, color="blue"):
    percent = max(0, min(100, int(percent)))
    progress_var = APP_STATE.get("progress_var")
    progress_label = APP_STATE.get("progress_label")
    root = APP_STATE.get("root")

    try:
        if progress_var is not None:
            progress_var.set(percent)
        if progress_label is not None:
            text = f"{percent}%"
            if message:
                text += f" - {message}"
            progress_label.config(text=text, fg=color)
        if message:
            update_status(message, color)
        if root is not None and root.winfo_exists():
            root.update_idletasks()
    except Exception:
        print(f"{percent}% - {message or ''}")


def set_viewer_controls_state(enabled):
    state = "normal" if enabled else "disabled"
    for widget in APP_STATE.get("viewer_controls", []):
        try:
            widget.config(state=state)
        except Exception:
            pass


def refresh_extrema_panel(lines=None):
    text_widget = APP_STATE.get("extrema_text")
    if text_widget is None:
        return
    try:
        text_widget.delete("1.0", tk.END)
        if lines:
            text_widget.insert(tk.END, "\n".join(lines))
        else:
            text_widget.insert(tk.END, "No extrema loaded.\n")
    except Exception:
        pass


def _cleanup_viewer_state():
    global VIEWER_STATE
    VIEWER_STATE = None
    set_viewer_controls_state(False)


def _viewer_is_alive():
    if VIEWER_STATE is None:
        return False
    plotter = VIEWER_STATE.get("plotter")
    return plotter is not None and getattr(plotter, "ren_win", None) is not None


def close_viewer():
    global VIEWER_STATE
    if VIEWER_STATE is None:
        return
    plotter = VIEWER_STATE.get("plotter")
    try:
        if plotter is not None and getattr(plotter, "ren_win", None) is not None:
            plotter.close()
    except Exception:
        pass
    _cleanup_viewer_state()


def pump_viewer():
    root = APP_STATE.get("root")
    if root is None:
        return
    if VIEWER_STATE is not None:
        plotter = VIEWER_STATE.get("plotter")
        try:
            if plotter is None or getattr(plotter, "ren_win", None) is None:
                _cleanup_viewer_state()
            else:
                plotter.update()
        except Exception:
            _cleanup_viewer_state()
    root.after(30, pump_viewer)


def viewer_apply_isovalue(*_args):
    if VIEWER_STATE is None:
        return
    value_text = APP_STATE["isovalue_var"].get().strip()
    try:
        value = float(value_text)
    except ValueError:
        messagebox.showerror("Invalid isovalue", "Density isovalue must be a numeric value.", parent=APP_STATE.get("root"))
        APP_STATE["isovalue_var"].set(f"{VIEWER_STATE['state']['isovalue']:.6g}")
        return
    VIEWER_STATE["state"]["isovalue"] = value
    VIEWER_STATE["rebuild_surface"]()


def viewer_apply_esp_range(*_args):
    if VIEWER_STATE is None:
        return
    min_text = APP_STATE["esp_min_var"].get().strip()
    max_text = APP_STATE["esp_max_var"].get().strip()

    if not min_text and not max_text:
        VIEWER_STATE["state"]["esp_use_custom_range"] = False
        VIEWER_STATE["rebuild_surface"]()
        update_status("ESP scale bar range reset to the original Multiwfn data range.", "darkgreen")
        return

    try:
        esp_min = float(min_text)
        esp_max = float(max_text)
    except ValueError:
        messagebox.showerror("Invalid ESP range", "Scale bar min and max must be numeric values.", parent=APP_STATE.get("root"))
        if VIEWER_STATE["state"].get("esp_use_custom_range"):
            APP_STATE["esp_min_var"].set(f"{VIEWER_STATE['state']['esp_min']:.6g}")
            APP_STATE["esp_max_var"].set(f"{VIEWER_STATE['state']['esp_max']:.6g}")
        else:
            APP_STATE["esp_min_var"].set("")
            APP_STATE["esp_max_var"].set("")
        return

    if esp_min >= esp_max:
        messagebox.showerror("Invalid ESP range", "Scale bar min must be smaller than max.", parent=APP_STATE.get("root"))
        if VIEWER_STATE["state"].get("esp_use_custom_range"):
            APP_STATE["esp_min_var"].set(f"{VIEWER_STATE['state']['esp_min']:.6g}")
            APP_STATE["esp_max_var"].set(f"{VIEWER_STATE['state']['esp_max']:.6g}")
        else:
            APP_STATE["esp_min_var"].set("")
            APP_STATE["esp_max_var"].set("")
        return

    VIEWER_STATE["state"]["esp_min"] = esp_min
    VIEWER_STATE["state"]["esp_max"] = esp_max
    VIEWER_STATE["state"]["esp_use_custom_range"] = True
    VIEWER_STATE["rebuild_surface"]()
    update_status(f"ESP scale bar range override set to {esp_min:.3f} ... {esp_max:.3f}", "darkgreen")


def viewer_update_opacity(value):
    if VIEWER_STATE is None:
        return
    VIEWER_STATE["state"]["opacity"] = float(value) / 100.0
    VIEWER_STATE["rebuild_surface"]()


def viewer_update_cmap(value):
    if VIEWER_STATE is None:
        return
    VIEWER_STATE["state"]["cmap_index"] = VIEWER_STATE["cmap_list"].index(value)
    VIEWER_STATE["rebuild_surface"]()


def viewer_toggle_molecule_overlay():
    if VIEWER_STATE is None:
        return
    show_overlay = bool(APP_STATE["show_molecule_var"].get())
    VIEWER_STATE["state"]["show_molecule_overlay"] = show_overlay
    VIEWER_STATE["build_overlay_atoms"]()
    VIEWER_STATE["build_overlay_bonds"]()


def viewer_update_molecule_opacity(value):
    if VIEWER_STATE is None:
        return
    VIEWER_STATE["state"]["overlay_opacity"] = float(value) / 100.0
    VIEWER_STATE["update_overlay_opacity"]()


def viewer_save_as():
    if not _viewer_is_alive():
        return
    file_path = filedialog.asksaveasfilename(
        title="Save current view",
        defaultextension=".png",
        filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg *.jpeg")],
        parent=APP_STATE.get("root"),
    )
    if not file_path:
        return
    image_size = selected_image_size(APP_STATE.get("image_resolution_var"))
    window_size = image_size or VIEWER_STATE["plotter"].window_size
    bg_color, _label_color = _get_viewer_colors()
    save_pyvista_screenshot(VIEWER_STATE["plotter"], file_path, bg_color, window_size=window_size, scale=1)
    update_status(f"Saved image: {file_path}", "darkgreen")


def _copy_image_to_clipboard_windows(rgb_image):
    try:
        import io
        from PIL import Image
        import win32clipboard
    except Exception as exc:
        raise RuntimeError("Clipboard image copy requires Pillow and pywin32 on Windows.") from exc

    image = Image.fromarray(rgb_image)
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    finally:
        win32clipboard.CloseClipboard()


def viewer_copy_to_clipboard():
    if not _viewer_is_alive():
        return
    if os.name != "nt":
        update_status("Ctrl+C image copy is currently implemented for Windows only.", "red")
        return
    try:
        rgb_image = VIEWER_STATE["plotter"].screenshot(return_img=True, window_size=VIEWER_STATE["plotter"].window_size, scale=1)
        _copy_image_to_clipboard_windows(rgb_image)
        update_status("Current PyVista view copied to clipboard.", "darkgreen")
    except Exception as exc:
        update_status(f"Clipboard copy failed: {exc}", "red")


ESP_SCALAR_BAR_TITLE = "ESP\n\nkcal/mol\n\n"


def _set_scalar_bar_style(plotter, text_color=None):
    if text_color is None:
        bg = APP_STATE.get("bg_color_var")
        text_color = contrast_text_color(bg.get() if bg else "black")
    try:
        try:
            import pyvista as pv
            rgb = pv.Color(text_color).float_rgb
        except Exception:
            rgb = (1.0, 1.0, 1.0) if str(text_color).lower() == "white" else (0.0, 0.0, 0.0)

        scalar_bars = getattr(plotter, "scalar_bars", {})
        bars = []
        for key in (ESP_SCALAR_BAR_TITLE, "ESP\n\nkcal/mol", "ESP\nkcal/mol\n\n", "ESP, kcal/mol\n\n\n", "ESP, kcal/mol"):
            bar = scalar_bars.get(key)
            if bar is not None and bar not in bars:
                bars.append(bar)
        for bar in scalar_bars.values():
            if bar not in bars:
                bars.append(bar)

        for scalar_bar in bars:
            title_prop = None
            label_prop = None
            try:
                title_prop = scalar_bar.GetTitleTextProperty()
            except Exception:
                pass
            try:
                label_prop = scalar_bar.GetLabelTextProperty()
            except Exception:
                pass
            for prop in (title_prop, label_prop):
                if prop is None:
                    continue
                try:
                    prop.SetColor(*rgb)
                    prop.BoldOn()
                    prop.Modified()
                except Exception:
                    pass
            try:
                annotation_prop = scalar_bar.GetAnnotationTextProperty()
                annotation_prop.SetColor(*rgb)
                annotation_prop.BoldOn()
                annotation_prop.Modified()
            except Exception:
                pass
            try:
                if title_prop is not None:
                    title_prop.SetFontSize(20)
                    title_prop.SetVerticalJustificationToBottom()
            except Exception:
                pass
            try:
                if label_prop is not None:
                    label_prop.SetFontSize(16)
            except Exception:
                pass
            try:
                scalar_bar.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
            except Exception:
                pass
            try:
                scalar_bar.SetPosition(0.82, 0.10)
                scalar_bar.SetWidth(0.07)
                scalar_bar.SetHeight(0.80)
            except Exception:
                pass
            try:
                scalar_bar.SetTextPositionToPrecedeScalarBar()
            except Exception:
                pass
            try:
                scalar_bar.SetUnconstrainedFontSize(False)
            except Exception:
                pass
            try:
                scalar_bar.Modified()
            except Exception:
                pass
    except Exception:
        pass


def _remove_esp_scalar_bars(plotter):
    try:
        scalar_bars = getattr(plotter, "scalar_bars", {})
        keys = [key for key in list(scalar_bars.keys()) if "ESP" in str(key)]
    except Exception:
        keys = []
    for key in keys:
        try:
            plotter.remove_scalar_bar(title=key, render=False)
            continue
        except Exception:
            pass
        try:
            scalar_bar = getattr(plotter, "scalar_bars", {}).get(key)
            if scalar_bar is not None:
                plotter.remove_actor(scalar_bar, render=False)
        except Exception:
            pass


def _extrema_to_lines(points):
    lines = []
    for idx, point in enumerate(sort_extrema_points(points), start=1):
        lines.append(f"{idx:>3d}  {point[0]:>+10.2f}  x={point[1]:>8.3f}  y={point[2]:>8.3f}  z={point[3]:>8.3f}")
    return lines


def sort_extrema_points(points):
    return sorted(list(points or []), key=lambda point: float(point[0]), reverse=True)


def _get_viewer_colors():
    bg = APP_STATE.get("bg_color_var")
    bg_color = str(bg.get() if bg else "black").strip().lower()
    if bg_color not in {"black", "white"}:
        bg_color = "black"
    return (bg_color, contrast_text_color(bg_color))


def contrast_text_color(background):
    return "white" if str(background or "").strip().lower() == "black" else "black"


def _parse_extrema_lines_from_widget():
    text_widget = APP_STATE.get("extrema_text")
    if text_widget is None:
        return None
    raw = text_widget.get("1.0", tk.END).strip()
    if not raw or raw == "No extrema loaded.":
        return []
    parsed = []
    import re
    number_re = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
    for line in raw.splitlines():
        nums = number_re.findall(line)
        if len(nums) < 4:
            continue
        if len(nums) >= 5:
            nums = nums[-4:]
        try:
            parsed.append([float(nums[0]), float(nums[1]), float(nums[2]), float(nums[3])])
        except Exception:
            continue
    return parsed


def _remove_extrema_actors():
    if VIEWER_STATE is None:
        return
    plotter = VIEWER_STATE["plotter"]
    for key in ["extrema_points_actor", "extrema_labels_actor"]:
        actor = VIEWER_STATE.get(key)
        if actor is not None:
            try:
                plotter.remove_actor(actor, render=False)
            except Exception:
                pass
            VIEWER_STATE[key] = None


def _render_extrema(points):
    if VIEWER_STATE is None:
        return
    plotter = VIEWER_STATE["plotter"]
    _remove_extrema_actors()
    sorted_points = sort_extrema_points(points)
    VIEWER_STATE["extrema_points"] = sorted_points
    refresh_extrema_panel(_extrema_to_lines(sorted_points))
    if not sorted_points:
        plotter.render()
        bring_pyvista_window_to_front(plotter, delay_s=0.05)
        return
    coords = np.array([p[1:4] for p in sorted_points], dtype=float)
    poly = VIEWER_STATE["pv"].PolyData(coords)
    labels = [f"{p[0]:+.2f}" for p in sorted_points]
    _bg_color, label_color = _get_viewer_colors()
    VIEWER_STATE["extrema_points_actor"] = plotter.add_points(
        poly,
        color=label_color,
        point_size=6,
        render_points_as_spheres=False,
        name="extrema_points",
        render=False,
    )
    VIEWER_STATE["extrema_labels_actor"] = plotter.add_point_labels(
        poly,
        labels,
        font_size=16,
        show_points=False,
        point_size=0,
        text_color=label_color,
        fill_shape=False,
        shape=None,
        margin=0,
        tolerance=0.025,
        always_visible=False,
        name="extrema_labels",
        render=False,
    )
    plotter.render()
    bring_pyvista_window_to_front(plotter, delay_s=0.05)


def viewer_generate_extrema(scan_near_ua=False):
    if VIEWER_STATE is None:
        return
    isoval = VIEWER_STATE["state"]["isovalue"]
    points = CalcPoints(isoval)
    if scan_near_ua:
        filtered = []
        for atom in VIEWER_STATE["centers"]:
            if atom[0] in [1, 8, 9, 16, 17, 34, 35, 52, 53, 84, 85]:
                for cp in points:
                    if np.linalg.norm(np.array(cp[1:]) - np.array(atom[1:-1])) < 5.0 and cp not in filtered:
                        filtered.append(cp)
        points = filtered
    _render_extrema(points)
    update_status(f"Loaded {len(points)} extrema point(s).", "darkgreen")


def viewer_clear_extrema():
    if VIEWER_STATE is None:
        return
    VIEWER_STATE["extrema_points"] = []
    _remove_extrema_actors()
    refresh_extrema_panel([])
    try:
        VIEWER_STATE["plotter"].render()
    except Exception:
        pass


def viewer_delete_selected_extrema():
    if VIEWER_STATE is None:
        return
    text_widget = APP_STATE.get("extrema_text")
    if text_widget is None:
        return
    ranges = list(text_widget.tag_ranges(tk.SEL))
    if not ranges:
        messagebox.showinfo("Delete extrema", "Select one or more lines in the extrema list first.", parent=APP_STATE.get("root"))
        return
    start = str(ranges[0])
    end = str(ranges[-1])
    first_line = int(start.split(".")[0])
    last_line = int(end.split(".")[0])
    current = VIEWER_STATE.get("extrema_points", [])
    kept = [p for idx, p in enumerate(current, start=1) if not (first_line <= idx <= last_line)]
    _render_extrema(kept)
    update_status(f"Removed {len(current) - len(kept)} extrema point(s) from list and screen.", "darkgreen")


def viewer_apply_edited_extrema():
    if VIEWER_STATE is None:
        return
    parsed = _parse_extrema_lines_from_widget()
    if parsed is None:
        return
    _render_extrema(parsed)
    update_status(f"Applied edited extrema list: {len(parsed)} point(s) kept on screen.", "darkgreen")


def viewer_kill_range():
    if VIEWER_STATE is None:
        return
    points = VIEWER_STATE.get("extrema_points", [])
    if not points:
        return
    try:
        killval = float(APP_STATE["kill_value_var"].get().strip())
        killpm = float(APP_STATE["kill_pm_var"].get().strip())
    except ValueError:
        messagebox.showerror("Invalid kill range", "Kill value and ± range must be numeric.", parent=APP_STATE.get("root"))
        return
    kept = [p for p in points if not (killval - killpm < p[0] < killval + killpm)]
    removed = len(points) - len(kept)
    _render_extrema(kept)
    update_status(f"Removed {removed} extrema point(s).", "darkgreen")


def viewer_update_background(*_args):
    if VIEWER_STATE is None:
        return
    VIEWER_STATE["apply_colors"]()


def viewer_reset():

    if not _viewer_is_alive():
        return
    VIEWER_STATE["plotter"].reset_camera()
    VIEWER_STATE["plotter"].render()


def sync_main_controls_from_viewer():
    if VIEWER_STATE is None:
        set_viewer_controls_state(False)
        return
    required_keys = {
        "isovalue_var",
        "opacity_scale",
        "cmap_var",
        "suggested_range_var",
        "esp_range_hint_var",
        "esp_min_var",
        "esp_max_var",
        "show_molecule_var",
        "molecule_opacity_scale",
    }
    if not required_keys.issubset(APP_STATE):
        return
    state = VIEWER_STATE["state"]
    APP_STATE["isovalue_var"].set(f"{state['isovalue']:.6g}")
    APP_STATE["opacity_scale"].set(int(round(state["opacity"] * 100.0)))
    APP_STATE["cmap_var"].set(VIEWER_STATE["cmap_list"][state["cmap_index"]])
    APP_STATE["show_molecule_var"].set(state.get("show_molecule_overlay", False))
    APP_STATE["molecule_opacity_scale"].set(int(round(state.get("overlay_opacity", 1.0) * 100.0)))
    APP_STATE["suggested_range_var"].set(
        f"Suggested density range: {VIEWER_STATE['dens_min']:.6g} to {VIEWER_STATE['dens_max']:.6g}"
    )
    APP_STATE["esp_range_hint_var"].set(
        f"ESP data range: {VIEWER_STATE['esp_min_data']:.6g} to {VIEWER_STATE['esp_max_data']:.6g}"
    )
    if state.get("esp_use_custom_range"):
        APP_STATE["esp_min_var"].set(f"{state['esp_min']:.6g}")
        APP_STATE["esp_max_var"].set(f"{state['esp_max']:.6g}")
    else:
        APP_STATE["esp_min_var"].set("")
        APP_STATE["esp_max_var"].set("")
    set_viewer_controls_state(True)


def VisualizeData(CENTERS, CUBdat, CUBdatESP, xx, yy, zz):
    import pyvista as pv

    global VIEWER_STATE

    if VIEWER_STATE is not None:
        close_viewer()

    grid = BuildPyVistaGrid(CUBdat, CUBdatESP, xx, yy, zz)
    dens_min = float(np.min(CUBdat))
    dens_max = float(np.max(CUBdat))
    esp_min_data = float(np.min(CUBdatESP))
    esp_max_data = float(np.max(CUBdatESP))
    bond_pairs = BuildBondPairs(CENTERS)

    cmap_list = [
        "gist_rainbow",
        "turbo",
        "coolwarm",
        "RdBu_r",
        "plasma",
        "viridis",
    ]

    state = {
        "isovalue": 0.001,
        "opacity": 1.0,
        "cmap_index": 0,
        "show_molecule_overlay": True,
        "overlay_opacity": 0.40,
        "esp_min": esp_min_data,
        "esp_max": esp_max_data,
        "esp_use_custom_range": False,
        "surface_actor": None,
        "scalar_bar_actor": None,
        "overlay_atom_actors": [],
        "overlay_bond_actors": [],
    }

    viewer_width, viewer_height = _viewer_window_size()
    bounds_extent = float(np.linalg.norm([xx.max() - xx.min(), yy.max() - yy.min(), zz.max() - zz.min()]))
    plotter = pv.Plotter(window_size=(viewer_width, viewer_height))
    main_renderer = plotter.renderer
    overlay_renderer = None

    try:
        plotter.ren_win.SetNumberOfLayers(2)
        overlay_renderer = pv._vtk.vtkRenderer()
        overlay_renderer.SetLayer(1)
        overlay_renderer.InteractiveOff()
        overlay_renderer.SetViewport(0.0, 0.0, 1.0, 1.0)
        try:
            overlay_renderer.SetActiveCamera(main_renderer.GetActiveCamera())
        except Exception:
            overlay_renderer.SetActiveCamera(main_renderer.camera)
        configure_molecule_renderer_lights(pv, overlay_renderer, bounds_extent)
        plotter.ren_win.AddRenderer(overlay_renderer)
    except Exception:
        overlay_renderer = None

    def _position_viewer_window():
        root = APP_STATE.get("root")
        if root is None:
            return
        try:
            root.update_idletasks()
            viewer_x = int(root.winfo_rootx() + root.winfo_width() + 12)
            viewer_y = int(root.winfo_rooty())
            ren_win = getattr(plotter, "ren_win", None)
            if ren_win is not None:
                ren_win.SetPosition(viewer_x, viewer_y)
        except Exception:
            pass
    def _sync_overlay_camera():
        if overlay_renderer is None:
            return
        try:
            overlay_renderer.SetActiveCamera(main_renderer.GetActiveCamera())
        except Exception:
            try:
                overlay_renderer.SetActiveCamera(main_renderer.camera)
            except Exception:
                pass

    def _remove_overlay_actor(actor):
        if actor is None:
            return
        if overlay_renderer is not None:
            try:
                overlay_renderer.RemoveActor(actor)
                return
            except Exception:
                pass
        try:
            plotter.remove_actor(actor, render=False)
        except Exception:
            pass

    def _make_overlay_actor(mesh, color):
        material = molecule_material_parameters()
        if overlay_renderer is None:
            actor = plotter.add_mesh(mesh, color=color, smooth_shading=True, lighting=True, render=False, **material)
            try:
                actor.prop.opacity = float(state.get("overlay_opacity", 1.0))
            except Exception:
                pass
            return actor
        mapper = pv._vtk.vtkPolyDataMapper()
        mapper.SetInputData(mesh)
        actor = pv._vtk.vtkActor()
        actor.SetMapper(mapper)
        if isinstance(color, str):
            color = (0.83, 0.83, 0.83)
        prop = actor.GetProperty()
        prop.SetColor(float(color[0]), float(color[1]), float(color[2]))
        prop.SetOpacity(float(state.get("overlay_opacity", 1.0)))
        try:
            prop.LightingOn()
            prop.SetInterpolationToPhong()
            prop.SetAmbient(float(material["ambient"]))
            prop.SetDiffuse(float(material["diffuse"]))
            prop.SetSpecular(float(material["specular"]))
            prop.SetSpecularPower(float(material["specular_power"]))
        except Exception:
            pass
        overlay_renderer.AddActor(actor)
        _sync_overlay_camera()
        return actor

    def _update_overlay_opacity():
        opacity = float(state.get("overlay_opacity", 1.0))
        for actor in state["overlay_atom_actors"] + state["overlay_bond_actors"]:
            try:
                actor.GetProperty().SetOpacity(opacity)
            except Exception:
                try:
                    actor.prop.opacity = opacity
                except Exception:
                    pass
        try:
            plotter.render()
            bring_pyvista_window_to_front(plotter, delay_s=0.05)
        except Exception:
            pass

    def _apply_molecule_overlay_positions():
        _sync_overlay_camera()

    def apply_colors():
        bg_color, label_color = _get_viewer_colors()
        try:
            try:
                plotter.set_background(bg_color, top=HQ_BACKGROUND_TOP.get(str(bg_color).strip().lower()))
            except Exception:
                plotter.set_background(bg_color)
        except Exception:
            pass
        rebuild_scalar_bar(label_color)
        _set_scalar_bar_style(plotter, label_color)
        if VIEWER_STATE is not None and VIEWER_STATE.get("extrema_points"):
            _render_extrema(VIEWER_STATE.get("extrema_points", []))
        else:
            try:
                plotter.render()
                bring_pyvista_window_to_front(plotter, delay_s=0.05)
            except Exception:
                pass

    def rebuild_scalar_bar(label_color):
        _remove_esp_scalar_bars(plotter)
        state["scalar_bar_actor"] = None
        actor = state.get("surface_actor")
        if actor is None:
            return
        mapper = None
        try:
            mapper = actor.mapper
        except Exception:
            try:
                mapper = actor.GetMapper()
            except Exception:
                mapper = None
        if mapper is None:
            return
        try:
            state["scalar_bar_actor"] = plotter.add_scalar_bar(
                title=ESP_SCALAR_BAR_TITLE,
                mapper=mapper,
                n_labels=5,
                fmt="%.1f",
                color=label_color,
                vertical=True,
                position_x=0.82,
                position_y=0.10,
                width=0.07,
                height=0.80,
                title_font_size=16,
                label_font_size=16,
                bold=True,
                render=False,
            )
        except Exception:
            state["scalar_bar_actor"] = None
        _set_scalar_bar_style(plotter, label_color)

    def rebuild_surface():
        bg_color, label_color = _get_viewer_colors()
        contour = grid.contour(isosurfaces=[float(state["isovalue"])], scalars="Density")
        if contour.n_points == 0:
            if state["surface_actor"] is not None:
                plotter.remove_actor(state["surface_actor"], render=False)
                state["surface_actor"] = None
            _remove_esp_scalar_bars(plotter)
            state["scalar_bar_actor"] = None
            plotter.add_text(
                "No surface at current isovalue",
                position="lower_right",
                font_size=10,
                color=label_color,
                name="surface_status",
            )
            plotter.render()
            bring_pyvista_window_to_front(plotter, delay_s=0.05)
            return
        if state["surface_actor"] is not None:
            plotter.remove_actor(state["surface_actor"], render=False)
        _remove_esp_scalar_bars(plotter)
        state["scalar_bar_actor"] = None
        plotter.add_text(
            " " * 32,
            position="lower_right",
            font_size=10,
            color=label_color,
            name="surface_status",
        )
        mesh_kwargs = dict(
            scalars="ESP",
            cmap=cmap_list[state["cmap_index"]],
            opacity=float(state["opacity"]),
            smooth_shading=True,
            show_scalar_bar=False,
            name="esp_surface",
            render=False,
        )
        if state.get("esp_use_custom_range"):
            mesh_kwargs["clim"] = [float(state["esp_min"]), float(state["esp_max"])]

        state["surface_actor"] = plotter.add_mesh(
            contour,
            **mesh_kwargs
        )
        rebuild_scalar_bar(label_color)
        plotter.render()
        bring_pyvista_window_to_front(plotter, delay_s=0.05)

    def _bond_segment_points(i, j):
        p1 = np.array(CENTERS[i][1:4], dtype=float)
        p2 = np.array(CENTERS[j][1:4], dtype=float)
        return p1, p2

    def _trim_bond_to_atom_surfaces(i, j):
        p1, p2 = _bond_segment_points(i, j)
        vector = p2 - p1
        length = float(np.linalg.norm(vector))
        if length <= 1.0e-8:
            return p1, p2
        direction = vector / length
        half_length = length * 0.5
        r1 = min(display_atom_radius_from_number(CENTERS[i][0]), half_length * 0.85)
        r2 = min(display_atom_radius_from_number(CENTERS[j][0]), half_length * 0.85)
        return p1 + direction * r1, p2 - direction * r2

    def build_overlay_atoms():
        for actor in state["overlay_atom_actors"]:
            _remove_overlay_actor(actor)
        state["overlay_atom_actors"] = []
        if not state.get("show_molecule_overlay"):
            plotter.render()
            bring_pyvista_window_to_front(plotter, delay_s=0.05)
            return
        for atom in CENTERS:
            center = np.array(atom[1:4], dtype=float)
            radius = display_atom_radius_from_number(atom[0])
            color = atom_color_from_number(atom[0])
            sphere = pv.Sphere(radius=radius, center=center, theta_resolution=HQ_ATOM_RESOLUTION, phi_resolution=HQ_ATOM_RESOLUTION)
            actor = _make_overlay_actor(sphere, color)
            state["overlay_atom_actors"].append(actor)
        _apply_molecule_overlay_positions()
        plotter.render()
        bring_pyvista_window_to_front(plotter, delay_s=0.05)
        bring_pyvista_window_to_front(plotter, delay_s=0.05)

    def build_overlay_bonds():
        for actor in state["overlay_bond_actors"]:
            _remove_overlay_actor(actor)
        state["overlay_bond_actors"] = []
        if not state.get("show_molecule_overlay"):
            plotter.render()
            bring_pyvista_window_to_front(plotter, delay_s=0.05)
            return
        for i, j in bond_pairs:
            p1, p2 = _trim_bond_to_atom_surfaces(i, j)
            midpoint = (np.asarray(p1, dtype=float) + np.asarray(p2, dtype=float)) / 2.0
            colors = (atom_color_from_number(CENTERS[i][0]), atom_color_from_number(CENTERS[j][0]))
            for a, b, color in ((p1, midpoint, colors[0]), (midpoint, p2, colors[1])):
                cylinder = cylinder_between(pv, a, b)
                if cylinder is None:
                    continue
                actor = _make_overlay_actor(cylinder, color)
                state["overlay_bond_actors"].append(actor)
        _apply_molecule_overlay_positions()
        plotter.render()

    VIEWER_STATE = {
        "pv": pv,
        "plotter": plotter,
        "state": state,
        "rebuild_surface": rebuild_surface,
        "build_overlay_atoms": build_overlay_atoms,
        "build_overlay_bonds": build_overlay_bonds,
        "update_overlay_opacity": _update_overlay_opacity,
        "apply_colors": apply_colors,
        "cmap_list": cmap_list,
        "dens_min": dens_min,
        "dens_max": dens_max,
        "esp_min_data": esp_min_data,
        "esp_max_data": esp_max_data,
        "centers": CENTERS,
        "extrema_points": [],
        "extrema_points_actor": None,
        "extrema_labels_actor": None,
    }

    try:
        plotter.add_on_render_callback(lambda _plotter: _apply_molecule_overlay_positions(), render_event=True)
    except Exception:
        pass

    try:
        interactor = getattr(plotter, "iren", None)
        vtk_interactor = getattr(interactor, "interactor", None)
        if vtk_interactor is not None:
            def _ctrl_c_observer(_obj, _event):
                try:
                    key = vtk_interactor.GetKeySym()
                    ctrl = vtk_interactor.GetControlKey()
                except Exception:
                    key = None
                    ctrl = 0
                if ctrl and str(key).lower() == "c":
                    viewer_copy_to_clipboard()

            vtk_interactor.AddObserver("KeyPressEvent", _ctrl_c_observer)
        else:
            plotter.add_key_event("c", viewer_copy_to_clipboard)
    except Exception:
        pass

    apply_colors()
    rebuild_surface()
    build_overlay_bonds()
    build_overlay_atoms()
    if APP_STATE.get("root") is None:
        bring_pyvista_window_to_front(plotter)
        plotter.show(title="VisMap PyVista Viewer", auto_close=False)
        bring_pyvista_window_to_front(plotter, delay_s=0.05)
    else:
        bring_pyvista_window_to_front(plotter)
        plotter.show(title="VisMap PyVista Viewer", auto_close=False, interactive_update=True)
        bring_pyvista_window_to_front(plotter, delay_s=0.05)
        _position_viewer_window()
        try:
            APP_STATE["root"].after(120, _position_viewer_window)
        except Exception:
            pass
        sync_main_controls_from_viewer()
        refresh_extrema_panel([])


# ----------------------------
# Main processing

# ----------------------------
# Main processing
# ----------------------------

def process_selected_file(selected_inputfile, selected_nproc="4", selected_mode="old", selected_vis="y",
                          selected_pregen=False, selected_cpisov=None, selected_multiwfn=None):
    global inputfile, fname, nproc, mode, vis, PreGenCP, CPisov, workdir, mwfn_exe

    update_progress(0, "Starting VisMap...")
    inputfile = os.path.abspath(selected_inputfile)
    fname = base_name_no_ext(inputfile)
    workdir = os.path.dirname(inputfile)

    update_progress(5, "Resolving Multiwfn executable...")
    mwfn_exe = resolve_multiwfn_executable(selected_multiwfn)

    if not os.path.exists(inputfile):
        raise FileNotFoundError(f"Input file not found:\n{inputfile}")

    if not mwfn_exe or (not os.path.exists(mwfn_exe) and shutil.which(mwfn_exe) is None):
        raise FileNotFoundError(
            "Multiwfn was not found.\n\n"
            "Select the Multiwfn executable when prompted, or install Multiwfn and make it available in PATH."
        )

    mode = selected_mode if selected_mode in ["new", "old"] else "old"
    vis = selected_vis if selected_vis in ["y", "n"] else "y"

    try:
        nproc = str(int(selected_nproc))
    except ValueError:
        print("Could not convert given nproc to integer. Using 4.")
        nproc = "4"

    PreGenCP = bool(selected_pregen)
    CPisov = selected_cpisov

    if PreGenCP:
        try:
            CPisov = str(float(CPisov))
        except Exception:
            print("Error reading CPisov. Canceling ECP CPs pre-generation.")
            PreGenCP = False
            CPisov = None

    if mode == "old":
        IsCalced = [True, True]
        for i, x in enumerate([fname + "_Dens.cub", fname + "_ESP.cub"]):
            if os.path.exists(x):
                print("Located", x)
            else:
                IsCalced[i] = False
                print("Could not locate", x, "- It will be (re)calculated")
    else:
        IsCalced = [False, False]

    CalcCub(IsCalced, fname)

    if PreGenCP:
        update_progress(78, "Generating extrema points...")
        CalcPoints(CPisov)

    update_progress(82, "Reading density cube...")
    CUB, CENTERS = ReadCUB(fname + "_Dens.cub")
    origin, v1, v2, v3, pointsv1, pointsv2, pointsv3, Scalars = CUB

    update_progress(88, "Preparing density grid...")
    CUBdat = np.empty((pointsv1, pointsv2, pointsv3))
    for x in range(pointsv1):
        for y in range(pointsv2):
            for z in range(pointsv3):
                CUBdat[x][y][z] = Scalars[x * pointsv2 * pointsv3 + y * pointsv3 + z]

    x = np.array([origin[0] + v1[0] * i for i in range(pointsv1)])
    y = np.array([origin[1] + v2[1] * i for i in range(pointsv2)])
    z = np.array([origin[2] + v3[2] * i for i in range(pointsv3)])
    xx, yy, zz = np.meshgrid(x, y, z, indexing="ij")

    update_progress(92, "Reading ESP cube...")
    CUB, CENTERS = ReadCUB(fname + "_ESP.cub")
    TotESP = CUB[-1]
    update_progress(96, "Preparing ESP grid...")
    CUBdatESP = np.empty((pointsv1, pointsv2, pointsv3))
    for x in range(pointsv1):
        for y in range(pointsv2):
            for z in range(pointsv3):
                CUBdatESP[x][y][z] = TotESP[x * pointsv2 * pointsv3 + y * pointsv3 + z] * 627.0

    if vis == "y":
        update_progress(98, "Opening PyVista viewer...")
        VisualizeData(CENTERS, CUBdat, CUBdatESP, xx, yy, zz)
        update_status("Viewer loaded.", "darkgreen")
        update_progress(100, "Viewer loaded.", "darkgreen")


# ----------------------------
# GUI
# ----------------------------

def launch_gui(initial_inputfile=None, initial_nproc="8", initial_mode="old", initial_vis="y",
               initial_pregen=False, initial_cpisov=None, initial_multiwfn=None, autorun=False):
    root = tk.Tk()
    APP_STATE["root"] = root
    root.title("VisMap GUI")
    root.resizable(True, True)

    base_font = tkfont.nametofont("TkDefaultFont").copy()
    base_font.configure(size=10)
    section_font = base_font.copy()
    section_font.configure(size=11, weight="bold")
    subsection_font = base_font.copy()
    subsection_font.configure(weight="bold")
    emphasis_font = base_font.copy()
    emphasis_font.configure(weight="bold")
    mono_font = tkfont.Font(family="Courier New", size=10)

    app_bg = "#f4f6f9"
    panel_bg = "#f8fafc"
    border_color = "#d8dee8"
    text_fg = "#263348"
    title_fg = "#172033"
    muted_fg = "#53627a"
    action_bg = "#2a4b75"
    action_active = "#345986"
    action_fg = "#f8fafc"
    accent_bg = "#1e3a5f"
    accent_fg = "#d7e1ee"

    root.configure(background=app_bg)

    root.option_add("*Font", base_font)
    root.option_add("*LabelFrame.Font", section_font)
    root.option_add("*Button.Font", base_font)
    root.option_add("*Checkbutton.Font", base_font)
    root.option_add("*Entry.Font", base_font)
    root.option_add("*Text.Font", mono_font)
    root.option_add("*Label.Background", panel_bg)
    root.option_add("*Label.Foreground", text_fg)
    root.option_add("*LabelFrame.Background", panel_bg)
    root.option_add("*LabelFrame.Foreground", title_fg)
    root.option_add("*Frame.Background", panel_bg)
    root.option_add("*Button.Background", "#eef2f6")
    root.option_add("*Button.Foreground", text_fg)
    root.option_add("*Button.ActiveBackground", "#e4eaf1")
    root.option_add("*Button.ActiveForeground", text_fg)
    root.option_add("*Button.Relief", "flat")
    root.option_add("*Checkbutton.Background", panel_bg)
    root.option_add("*Checkbutton.Foreground", text_fg)
    root.option_add("*Checkbutton.ActiveBackground", panel_bg)
    root.option_add("*Checkbutton.SelectColor", panel_bg)
    root.option_add("*Entry.Background", "#ffffff")
    root.option_add("*Entry.Foreground", text_fg)
    root.option_add("*Entry.InsertBackground", text_fg)
    root.option_add("*Text.Background", "#ffffff")
    root.option_add("*Text.Foreground", text_fg)
    root.option_add("*Text.InsertBackground", text_fg)
    root.option_add("*Scale.Background", panel_bg)
    root.option_add("*Scale.Foreground", text_fg)
    root.option_add("*Scale.troughColor", "#d7e1ee")

    screen_w, screen_h = _get_screen_size()
    gui_width = max(int(screen_w * 0.40), 720)
    gui_height = max(1, int(screen_h * 0.80))
    gui_width = min(gui_width, max(screen_w - 40, 600))
    x = 20 if screen_w - gui_width > 40 else max(screen_w - gui_width, 0)
    y = max((screen_h - gui_height) // 2, 0)
    root.geometry(f"{gui_width}x{gui_height}+{x}+{y}")
    root.minsize(720, min(700, gui_height))
    root.maxsize(screen_w, screen_h)

    header = tk.Frame(root, bg=accent_bg, padx=14, pady=10)
    header.pack(side="top", fill="x")
    header_icon = load_header_icon(ESP_ICON_PATH)
    if header_icon is not None:
        APP_STATE["header_icon"] = header_icon
        tk.Label(header, image=header_icon, bg=accent_bg).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
    tk.Label(header, text="VisMap", bg=accent_bg, fg="#f8fafc", font=("Segoe UI", 15, "bold")).grid(row=0, column=1, sticky="w")
    tk.Label(header, text="ESP and density visualization from wavefunction files", bg=accent_bg, fg=accent_fg, font=("Segoe UI", 10, "bold")).grid(row=1, column=1, sticky="w")
    header.columnconfigure(2, weight=1)
    about_link = tk.Label(header, text="About", bg=accent_bg, fg="#ffffff", cursor="hand2", font=("Segoe UI", 11, "bold"))
    about_link.grid(row=0, column=3, rowspan=2, sticky="e")
    about_link.bind("<Button-1>", lambda _event: open_about_dialog(root, "VisMap", ESP_ICON_PATH, ABOUT_PURPOSE))

    content_host = tk.Frame(root, background=app_bg)
    content_host.pack(side="top", fill="both", expand=True)

    canvas = tk.Canvas(content_host, borderwidth=0, highlightthickness=0, background=app_bg)
    vscroll = tk.Scrollbar(content_host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    frm = tk.Frame(canvas, padx=12, pady=12, background=app_bg)
    frm_id = canvas.create_window((0, 0), window=frm, anchor="nw")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(event):
        canvas.itemconfigure(frm_id, width=event.width)

    frm.bind("<Configure>", on_frame_configure)
    canvas.bind("<Configure>", on_canvas_configure)
    bind_mousewheel_to_canvas(canvas, frm)

    frm.grid_columnconfigure(0, weight=5)
    frm.grid_columnconfigure(1, weight=4)
    frm.grid_rowconfigure(3, weight=1)

    input_box = tk.LabelFrame(frm, text="1. Input and execution", padx=12, pady=12, font=section_font, labelanchor="nw")
    input_box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
    input_box.grid_columnconfigure(0, weight=1)
    input_box.grid_columnconfigure(2, weight=0)

    tk.Label(input_box, text="Input wavefunction file (.wfn / .wfx / .fchk)", font=subsection_font).grid(row=0, column=0, sticky="w")
    input_file_var = tk.StringVar(value="")
    recent_input_files = load_recent_files()
    entry_file = ttk.Combobox(input_box, textvariable=input_file_var, values=recent_input_files, width=88)
    keep_entry_end_visible(entry_file, input_file_var)
    entry_file.grid(row=1, column=0, padx=(0, 10), pady=(4, 12), sticky="we")
    if initial_inputfile:
        input_file_var.set(os.path.abspath(initial_inputfile))
        entry_file.after_idle(lambda: entry_file.xview_moveto(1.0))

    def remember_current_input(path):
        nonlocal recent_input_files
        recent_input_files = remember_recent_file(path, recent_input_files)
        entry_file.configure(values=recent_input_files)

    if initial_inputfile:
        remember_current_input(input_file_var.get())

    def browse_file():
        f = filedialog.askopenfilename(
            title="Select input file",
            filetypes=[("Wavefunction files", "*.wfn *.wfx *.fchk"), ("All files", "*.*")],
        )
        if f:
            input_file_var.set(f)
            remember_current_input(f)
            entry_file.after_idle(lambda: entry_file.xview_moveto(1.0))

    browse_file_btn = tk.Button(input_box, text="Browse...", command=browse_file, width=12)
    browse_file_btn.grid(row=1, column=1, sticky="w")

    APP_STATE["multiwfn_path"] = initial_multiwfn or find_multiwfn_path()
    APP_STATE["multiwfn_search_done"] = bool(APP_STATE["multiwfn_path"])

    def finish_mwfn_locator(found):
        if found and not APP_STATE.get("multiwfn_path"):
            APP_STATE["multiwfn_path"] = found
        APP_STATE["multiwfn_search_done"] = True

    if not APP_STATE.get("multiwfn_path"):
        def locate_mwfn_worker():
            found = find_multiwfn_deep()
            root.after(0, lambda: finish_mwfn_locator(found))

        threading.Thread(target=locate_mwfn_worker, daemon=True).start()

    def prompt_for_multiwfn():
        f = filedialog.askopenfilename(
            title="Select Multiwfn executable",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
            parent=root,
        )
        if f:
            APP_STATE["multiwfn_path"] = f
            APP_STATE["multiwfn_search_done"] = True
            return f
        return ""

    def ensure_multiwfn_available():
        selected = APP_STATE.get("multiwfn_path", "")
        if is_valid_multiwfn_executable(selected):
            return selected
        messagebox.showwarning(
            "Multiwfn not found",
            "Multiwfn was not found automatically. Please select the Multiwfn executable.",
            parent=root,
        )
        selected = prompt_for_multiwfn()
        if is_valid_multiwfn_executable(selected):
            return selected
        raise FileNotFoundError("Multiwfn executable was not selected or could not be found.")

    def _build_run_icon():
        icon = tk.PhotoImage(width=18, height=18)
        icon.put("#123b6d", to=(0, 0, 18, 18))
        icon.put("#1f5fa8", to=(2, 2, 16, 16))
        icon.put("#5fd1ff", to=(4, 4, 14, 14))
        icon.put("#ffffff", to=(5, 5, 13, 7))
        icon.put("#ffffff", to=(8, 7, 10, 13))
        icon.put("#ffffff", to=(5, 13, 13, 15))
        return icon

    run_icon = _build_run_icon()
    APP_STATE["run_button_icon"] = run_icon

    default_nproc = initial_nproc or "8"
    default_mode = initial_mode or "old"
    default_vis = initial_vis or "y"
    default_pregen = bool(initial_pregen)
    default_cp = initial_cpisov or "0.001"

    action_box = tk.LabelFrame(frm, text="2. Viewer controls", padx=12, pady=12, font=section_font, labelanchor="nw")
    action_box.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
    action_box.grid_columnconfigure(0, weight=1)
    action_box.grid_columnconfigure(1, weight=1)

    APP_STATE["suggested_range_var"] = tk.StringVar(value="Suggested density range: n/a")
    APP_STATE["esp_range_hint_var"] = tk.StringVar(value="ESP data range: n/a")
    APP_STATE["isovalue_var"] = tk.StringVar(value="0.001")
    APP_STATE["esp_min_var"] = tk.StringVar(value="-50")
    APP_STATE["esp_max_var"] = tk.StringVar(value="50")
    APP_STATE["cmap_var"] = tk.StringVar(value="gist_rainbow")
    APP_STATE["show_molecule_var"] = tk.BooleanVar(value=True)
    APP_STATE["kill_value_var"] = tk.StringVar(value="0.0")
    APP_STATE["kill_pm_var"] = tk.StringVar(value="1.0")
    APP_STATE["bg_color_var"] = tk.StringVar(value="black")
    APP_STATE["image_resolution_var"] = tk.StringVar(value=DEFAULT_IMAGE_PRESET)

    surface_box = tk.LabelFrame(action_box, text="Surface", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    surface_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 10))
    surface_box.grid_columnconfigure(1, weight=1)

    tk.Label(surface_box, text="Density isovalue", font=subsection_font).grid(row=0, column=0, sticky="w", pady=(0, 6))
    isovalue_entry = tk.Entry(surface_box, textvariable=APP_STATE["isovalue_var"], width=14, relief="solid", bd=1)
    isovalue_entry.grid(row=0, column=1, sticky="w", pady=(0, 6))
    isovalue_entry.bind("<Return>", viewer_apply_isovalue)
    apply_btn = tk.Button(surface_box, text="Apply", command=viewer_apply_isovalue, width=10)
    apply_btn.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 6))

    tk.Label(surface_box, text="Opacity", font=subsection_font).grid(row=1, column=0, sticky="w")
    opacity_scale = tk.Scale(surface_box, from_=0, to=100, orient="horizontal", resolution=1, command=viewer_update_opacity, showvalue=True, length=210)
    opacity_scale.set(100)
    opacity_scale.grid(row=1, column=1, columnspan=2, sticky="we", pady=(0, 6))
    APP_STATE["opacity_scale"] = opacity_scale

    tk.Label(surface_box, text="Colormap", font=subsection_font).grid(row=2, column=0, sticky="w")
    cmap_menu = tk.OptionMenu(surface_box, APP_STATE["cmap_var"], "gist_rainbow", "turbo", "coolwarm", "RdBu_r", "plasma", "viridis", command=viewer_update_cmap)
    cmap_menu.grid(row=2, column=1, sticky="w")

    molecule_cb = tk.Checkbutton(
        surface_box,
        text="Show molecule over ESP",
        variable=APP_STATE["show_molecule_var"],
        command=viewer_toggle_molecule_overlay,
    )
    molecule_cb.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

    tk.Label(surface_box, text="Molecule opacity", font=subsection_font).grid(row=4, column=0, sticky="w", pady=(8, 0))
    molecule_opacity_scale = tk.Scale(
        surface_box,
        from_=0,
        to=100,
        orient="horizontal",
        resolution=1,
        command=viewer_update_molecule_opacity,
        showvalue=True,
        length=210,
    )
    molecule_opacity_scale.set(40)
    molecule_opacity_scale.grid(row=4, column=1, columnspan=2, sticky="we", pady=(8, 0))
    APP_STATE["molecule_opacity_scale"] = molecule_opacity_scale

    range_box = tk.LabelFrame(action_box, text="ESP scale bar", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    range_box.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
    range_box.grid_columnconfigure(1, weight=1)

    tk.Label(range_box, textvariable=APP_STATE["suggested_range_var"], font=emphasis_font, anchor="w", justify="left").grid(row=0, column=0, columnspan=3, sticky="w")
    tk.Label(range_box, textvariable=APP_STATE["esp_range_hint_var"], anchor="w", justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))

    tk.Label(range_box, text="Scale bar min", font=subsection_font).grid(row=2, column=0, sticky="w")
    esp_min_entry = tk.Entry(range_box, textvariable=APP_STATE["esp_min_var"], width=14, relief="solid", bd=1)
    esp_min_entry.grid(row=2, column=1, sticky="w")
    esp_min_entry.bind("<Return>", viewer_apply_esp_range)
    tk.Label(range_box, text="Scale bar max", font=subsection_font).grid(row=3, column=0, sticky="w", pady=(6, 0))
    esp_max_entry = tk.Entry(range_box, textvariable=APP_STATE["esp_max_var"], width=14, relief="solid", bd=1)
    esp_max_entry.grid(row=3, column=1, sticky="w", pady=(6, 0))
    esp_max_entry.bind("<Return>", viewer_apply_esp_range)
    esp_apply_btn = tk.Button(range_box, text="Apply range", command=viewer_apply_esp_range, width=12)
    esp_apply_btn.grid(row=2, column=2, rowspan=2, sticky="w", padx=(8, 0))

    appearance_box = tk.LabelFrame(action_box, text="Display options", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    appearance_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    for idx in range(2):
        appearance_box.grid_columnconfigure(idx, weight=1)

    tk.Label(appearance_box, text="Background", font=subsection_font).grid(row=0, column=0, sticky="w")
    bg_menu = tk.OptionMenu(appearance_box, APP_STATE["bg_color_var"], "black", "white", command=viewer_update_background)
    bg_menu.grid(row=0, column=1, sticky="w")

    quick_box = tk.LabelFrame(action_box, text="Quick actions", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    quick_box.grid(row=1, column=1, sticky="nsew")
    for idx in range(2):
        quick_box.grid_columnconfigure(idx, weight=1)

    save_btn = tk.Button(quick_box, text="Save as...", command=viewer_save_as, width=14)
    save_btn.grid(row=0, column=0, sticky="we", padx=(0, 6), pady=(0, 6))
    copy_btn = tk.Button(quick_box, text="Copy image", command=viewer_copy_to_clipboard, width=14)
    copy_btn.grid(row=0, column=1, sticky="we", pady=(0, 6))
    tk.Label(quick_box, text="Image size", font=subsection_font).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(0, 6))
    image_resolution_menu = tk.OptionMenu(quick_box, APP_STATE["image_resolution_var"], *IMAGE_PRESETS.keys())
    image_resolution_menu.grid(row=1, column=1, sticky="we", pady=(0, 6))
    reset_btn = tk.Button(quick_box, text="Reset view", command=viewer_reset, width=14)
    reset_btn.grid(row=2, column=0, sticky="we", padx=(0, 6))
    close_btn = tk.Button(quick_box, text="Close viewer", command=close_viewer, width=14)
    close_btn.grid(row=2, column=1, sticky="we")

    main_area = tk.LabelFrame(frm, text="3. Extrema tools and values", padx=12, pady=12, font=section_font, labelanchor="nw")
    main_area.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
    main_area.grid_columnconfigure(0, weight=0)
    main_area.grid_columnconfigure(1, weight=1)
    main_area.grid_rowconfigure(0, weight=1)

    left_tools = tk.Frame(main_area, width=320)
    left_tools.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
    left_tools.grid_propagate(False)
    left_tools.grid_columnconfigure(0, weight=1)
    left_tools.grid_columnconfigure(1, weight=1)

    extrema_actions = tk.LabelFrame(left_tools, text="Extrema actions", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    extrema_actions.grid(row=0, column=0, sticky="nwe", padx=(0, 8))
    gen_btn = tk.Button(extrema_actions, text="Generate extrema", command=lambda: viewer_generate_extrema(False), width=18)
    gen_btn.grid(row=0, column=0, sticky="we", pady=(0, 6))
    scan_btn = tk.Button(extrema_actions, text="Scan near UA", command=lambda: viewer_generate_extrema(True), width=18)
    scan_btn.grid(row=1, column=0, sticky="we", pady=(0, 6))
    clear_btn = tk.Button(extrema_actions, text="Clear extrema", command=viewer_clear_extrema, width=18)
    clear_btn.grid(row=2, column=0, sticky="we")

    filter_box = tk.LabelFrame(left_tools, text="Range filter", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    filter_box.grid(row=0, column=1, sticky="nwe")
    tk.Label(filter_box, text="Kill value", font=subsection_font).grid(row=0, column=0, sticky="w")
    kill_value_entry = tk.Entry(filter_box, textvariable=APP_STATE["kill_value_var"], width=12, relief="solid", bd=1)
    kill_value_entry.grid(row=1, column=0, sticky="w", pady=(0, 6))
    tk.Label(filter_box, text="+/- range", font=subsection_font).grid(row=2, column=0, sticky="w")
    kill_pm_entry = tk.Entry(filter_box, textvariable=APP_STATE["kill_pm_var"], width=12, relief="solid", bd=1)
    kill_pm_entry.grid(row=3, column=0, sticky="w", pady=(0, 6))
    kill_btn = tk.Button(filter_box, text="Kill range", command=viewer_kill_range, width=18)
    kill_btn.grid(row=4, column=0, sticky="we")

    edit_box = tk.LabelFrame(left_tools, text="List editing", padx=10, pady=8, font=subsection_font, labelanchor="nw")
    edit_box.grid(row=1, column=0, columnspan=2, sticky="we", pady=(10, 0))
    del_btn = tk.Button(edit_box, text="Delete selected lines", command=viewer_delete_selected_extrema, width=18)
    del_btn.grid(row=0, column=0, sticky="we", pady=(0, 6))
    sync_btn = tk.Button(edit_box, text="Apply edited list", command=viewer_apply_edited_extrema, width=18)
    sync_btn.grid(row=1, column=0, sticky="we")

    right_panel = tk.Frame(main_area)
    right_panel.grid(row=0, column=1, sticky="nsew")
    right_panel.grid_columnconfigure(0, weight=1)
    right_panel.grid_rowconfigure(2, weight=1)

    tk.Label(right_panel, text="Editable extrema list", font=subsection_font).grid(row=0, column=0, sticky="w")
    tk.Label(
        right_panel,
        text="Edit values or remove lines, then apply the updated list to refresh the viewer.",
        justify="left",
        wraplength=640,
    ).grid(row=1, column=0, sticky="w", pady=(2, 8))
    extrema_text = tk.Text(right_panel, width=84, height=24, wrap="none", relief="solid", bd=1)
    extrema_text.grid(row=2, column=0, sticky="nsew")
    APP_STATE["extrema_text"] = extrema_text

    extrema_scroll_y = tk.Scrollbar(right_panel, orient="vertical", command=extrema_text.yview)
    extrema_scroll_y.grid(row=2, column=1, sticky="ns")
    extrema_text.configure(yscrollcommand=extrema_scroll_y.set)
    APP_STATE["extrema_scrollbar"] = extrema_scroll_y

    APP_STATE["viewer_controls"] = [
        isovalue_entry, apply_btn, esp_min_entry, esp_max_entry, esp_apply_btn, opacity_scale, cmap_menu,
        molecule_cb, molecule_opacity_scale, bg_menu, save_btn, copy_btn, reset_btn, close_btn,
        gen_btn, scan_btn, clear_btn, kill_value_entry, kill_pm_entry, kill_btn, del_btn, sync_btn
    ]
    set_viewer_controls_state(False)

    status = tk.Label(frm, text="", anchor="w", justify="left", fg="blue", bg=app_bg, font=emphasis_font)
    status.grid(row=4, column=0, columnspan=2, sticky="we", pady=(4, 0))
    APP_STATE["status_label"] = status

    progress_frame = tk.Frame(frm, bg=app_bg)
    progress_frame.grid(row=5, column=0, columnspan=2, sticky="we", pady=(2, 0))
    progress_frame.columnconfigure(0, weight=1)
    progress_var = tk.IntVar(value=0)
    progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate", maximum=100, variable=progress_var)
    progress_bar.grid(row=0, column=0, sticky="we")
    progress_label = tk.Label(progress_frame, text="0%", anchor="w", justify="left", fg="blue", bg=app_bg, font=base_font)
    progress_label.grid(row=1, column=0, sticky="we", pady=(2, 0))
    APP_STATE["progress_var"] = progress_var
    APP_STATE["progress_label"] = progress_label

    button_bar = tk.Frame(root, padx=12, pady=10, background=app_bg)
    button_bar.pack(side="bottom", fill="x")
    tk.Label(button_bar, text=COPYRIGHT_NOTE, anchor="w", fg=muted_fg, bg=app_bg, font=base_font).pack(side="left")

    def run_clicked():
        selected_file = input_file_var.get().strip()
        selected_nproc = str(default_nproc).strip() or "4"
        selected_mode = str(default_mode).strip()
        selected_vis = str(default_vis).strip()
        selected_pregen = bool(default_pregen)
        selected_cp = str(default_cp).strip()

        if not selected_file:
            messagebox.showerror("Error", "Please select an input .wfn/.wfx/.fchk file.")
            return
        remember_current_input(selected_file)

        update_status("Running...", "blue")
        root.update_idletasks()

        try:
            selected_mwfn = ensure_multiwfn_available()
            process_selected_file(
                selected_inputfile=selected_file,
                selected_nproc=selected_nproc,
                selected_mode=selected_mode,
                selected_vis=selected_vis,
                selected_pregen=selected_pregen,
                selected_cpisov=selected_cp,
                selected_multiwfn=selected_mwfn,
            )
            if selected_vis != "y":
                update_status("Done.", "darkgreen")
                update_progress(100, "Done.", "darkgreen")
                messagebox.showinfo("Finished", "Processing completed successfully.")
        except Exception as e:
            update_status("Failed.", "red")
            update_progress(0, "Failed.", "red")
            messagebox.showerror("Execution error", str(e))

    run_button = tk.Button(
        input_box,
        text="ESP map",
        image=run_icon,
        compound="left",
        command=run_clicked,
        width=140,
        height=44,
        font=section_font,
        padx=10,
        anchor="center",
        bg=accent_bg,
        fg=action_fg,
        activebackground=action_bg,
        activeforeground=action_fg,
    )
    run_button.grid(row=1, column=2, sticky="w", padx=(14, 0), pady=(4, 12))
    quit_button = tk.Button(button_bar, text="Quit", command=root.destroy, width=12)
    quit_button.pack(side="right")

    def _style_button(btn, accent=False):
        try:
            if accent:
                btn.configure(
                    bg=accent_bg,
                    fg=action_fg,
                    activebackground=action_bg,
                    activeforeground=action_fg,
                    disabledforeground="#d7e1ee",
                )
            else:
                btn.configure(
                    bg="#dcdad5",
                    fg="#000000",
                    activebackground="#eeebe7",
                    activeforeground="#000000",
                    disabledforeground=muted_fg,
                )
            btn.configure(
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2",
            )
        except Exception:
            pass

    for btn in [
        browse_file_btn, apply_btn, esp_apply_btn,
        save_btn, copy_btn, reset_btn, close_btn, gen_btn, scan_btn, clear_btn,
        kill_btn, del_btn, sync_btn, quit_button,
    ]:
        _style_button(btn)
    _style_button(run_button, accent=True)

    for widget in [input_box, action_box, surface_box, range_box, appearance_box, quick_box, main_area, extrema_actions, filter_box, edit_box]:
        try:
            widget.configure(bg=panel_bg, fg=title_fg, bd=1, relief="solid", highlightbackground=border_color, highlightcolor=border_color)
        except Exception:
            pass

    for widget in [left_tools, right_panel]:
        try:
            widget.configure(bg=panel_bg)
        except Exception:
            pass

    root.bind_all("<Control-c>", lambda _event: viewer_copy_to_clipboard())
    root.after(30, pump_viewer)
    if autorun and initial_inputfile:
        root.after(250, run_clicked)
    refresh_extrema_panel([])
    root.mainloop()


# ----------------------------
# CLI support
# ----------------------------

def run_from_cli(argv):
    selected_inputfile = argv[1]
    selected_nproc = "4"
    selected_mode = "old"
    selected_vis = "y"
    selected_pregen = False
    selected_cpisov = None
    selected_multiwfn = None
    generate_only = False

    for item in argv[2:]:
        if item.startswith("-nproc="):
            selected_nproc = item[7:]
        elif item.startswith("-mode="):
            selected_mode = item[6:]
        elif item.startswith("-vis="):
            selected_vis = item[5:]
        elif item.startswith("-CPisov="):
            selected_cpisov = item[8:]
            selected_pregen = True
        elif item.startswith("-mwfn="):
            selected_multiwfn = item[6:]
        elif item in {"--generate-only", "-generate-only"}:
            generate_only = True

    if generate_only:
        process_selected_file(
            selected_inputfile=selected_inputfile,
            selected_nproc=selected_nproc,
            selected_mode=selected_mode,
            selected_vis="n",
            selected_pregen=selected_pregen,
            selected_cpisov=selected_cpisov,
            selected_multiwfn=selected_multiwfn,
        )
        return

    launch_gui(
        initial_inputfile=selected_inputfile,
        initial_nproc=selected_nproc,
        initial_mode=selected_mode,
        initial_vis=selected_vis,
        initial_pregen=selected_pregen,
        initial_cpisov=selected_cpisov,
        initial_multiwfn=selected_multiwfn,
        autorun=True,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        run_from_cli(sys.argv)
    else:
        launch_gui()
