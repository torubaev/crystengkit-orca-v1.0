#!/usr/bin/env python3
"""
HOMO–LUMO Levels Plot GUI
Input:
  Browse ORCA/Gaussian output/input -> auto-detect supported file content

Stability fixes vs “crash” reports:
- ALL GUI callbacks are wrapped in try/except and show an error dialog instead of terminating.
- The __main__ block DOES NOT re-raise exceptions (prevents the app from closing on errors).
- Left panel is fixed width; long file paths are wrapped (prevents layout collapse).

Save: PNG or SVG (only selected one).
"""

from __future__ import annotations

import os
import re
import sys
import json
import math
import gc
import shutil
import zipfile
import subprocess
import datetime as _dt
import traceback
import webbrowser
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from xml.sax.saxutils import escape as xml_escape

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import numpy as np
except Exception:
    np = None

try:
    import pyvista as pv
except Exception:
    pv = None

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageTk = None
    ImageDraw = None
    ImageFont = None


LOGFILE = "homo_lumo_gui_error.log"

_FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"

TOOLS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TOOLS_ROOT.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from app_identity import configure_tk_window_identity, set_windows_app_id

HOMO_LUMO_ICON_PATH = TOOLS_ROOT / "images" / "tr_homo_lumo_icon.png"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
CONTACT_EMAIL = "torubaev(at)gmail.com"
LINKEDIN_URL = "https://www.linkedin.com/in/torubaev/"
README_LINK_TEXT = "README section: HOMO-LUMO Plotter"
README_ANCHOR = "homo-lumo-plotter"


def wiki_url() -> str:
    return GITHUB_URL + f"#{README_ANCHOR}"


def open_readme_or_wiki():
    webbrowser.open(wiki_url(), new=2)
ABOUT_PURPOSE = (
    "Creates frontier-orbital energy diagrams from ORCA/Gaussian output or pasted orbital "
    "energies. For finished ORCA jobs, it can also generate MO cube files with orca_plot, "
    "render HOMO/LUMO surface images, and collect saved orbital views into a contact sheet."
)
FILE_PLACEHOLDER_TEXT = "Your Orca/Gaussian input here"
RECENT_FILES_PATH = Path.home() / ".homo_lumo_recent_files.json"
MAX_RECENT_FILES = 5
THUMBNAIL_SIZE = (400, 400)
LIVE_MO_VIEW_SIZE = (1100, 800)
CONTACT_HEADER_BG = "#0f2d44"
CONTACT_HEADER_FG = "#ffffff"
IMAGE_PRESETS = {
    "Preview: 1600 x 1200 px": (1600, 1200),
    "Paper 300 dpi: 3000 x 2250 px": (3000, 2250),
    "Paper 600 dpi: 6000 x 4500 px": (6000, 4500),
    "Poster / high-res: 8000 x 6000 px": (8000, 6000),
}
DEFAULT_IMAGE_PRESET = "Paper 600 dpi: 6000 x 4500 px"
MO_MOLECULE_STYLES = ["Capped sticks", "Wireframe", "Ball-and-stick"]
DEFAULT_MO_MOLECULE_STYLE = "Capped sticks"
MO_COLOR_SCHEMES = {
    "Classic blue/red": ("#0000ff", "#ff0000"),
    "Cyan / amber": ("#67e8f9", "#fde047"),
    "Emerald / violet": ("#6ee7b7", "#d8b4fe"),
    "Teal / rose": ("#5eead4", "#fda4af"),
    "Royal / gold": ("#93c5fd", "#facc15"),
}
DEFAULT_MO_COLOR_SCHEME = "Classic blue/red"


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
    style.configure("Info.TButton", padding=(3, 1), font=("Segoe UI", 9, "bold"))
    style.configure("TCheckbutton", background="#f8fafc", padding=(1, 2), font=("Segoe UI", 9))
    style.configure("TLabel", background="#f8fafc", foreground="#263348", padding=(1, 1), font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background="#f4f6f9", foreground="#53627a", font=("Segoe UI", 9))


def _log_exception(exc: BaseException) -> None:
    try:
        with open(LOGFILE, "w", encoding="utf-8") as f:
            f.write("Exception:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass


def _show_error(title: str, exc: BaseException) -> None:
    _log_exception(exc)
    msg = (
        f"{exc}\n\n"
        f"Details were written to:\n{os.path.abspath(LOGFILE)}"
    )
    try:
        messagebox.showerror(title, msg)
    except Exception:
        print(msg, file=sys.stderr)


def open_image_in_system_viewer(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showwarning("Open image", f"Saved image, but could not open it:\n{exc}")


def visible_surface_components(mesh: Any, min_fraction_of_largest: float = 0.015, min_points: int = 80) -> List[Any]:
    try:
        bodies = list(mesh.split_bodies())
    except Exception:
        return [mesh]
    if not bodies:
        return []
    largest = max(int(getattr(body, "n_points", 0)) for body in bodies)
    threshold = max(min_points, int(largest * min_fraction_of_largest))
    kept = [body for body in bodies if int(getattr(body, "n_points", 0)) >= threshold]
    return kept or [max(bodies, key=lambda body: int(getattr(body, "n_points", 0)))]


def contact_sheet_orbital_label(orbital: Dict[str, Any]) -> str:
    return str(orbital.get("display_label", "")).replace("\u2212", "-").replace("âˆ’", "-")


def contact_sheet_rows(orbitals: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    lumo = sorted([o for o in orbitals if o.get("row") == 1], key=lambda o: int(o.get("mo_number", 0)))
    homo = sorted([o for o in orbitals if o.get("row") == 0], key=lambda o: int(o.get("mo_number", 0)), reverse=True)
    return [lumo, homo]


def xlsx_col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def xlsx_inline_cell(row: int, col: int, text: str, style: int = 0) -> str:
    ref = f"{xlsx_col_name(col)}{row}"
    style_attr = f' s="{style}"' if style else ""
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{xml_escape(str(text))}</t></is></c>'


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


def is_png_path(path: str | Path) -> bool:
    return str(path).lower().endswith(".png")


def pyvista_screenshot(plotter: Any, path: Optional[str] = None, **kwargs: Any) -> Any:
    if path and is_png_path(path):
        try:
            return plotter.screenshot(path, transparent_background=False, **kwargs)
        except TypeError:
            pass
    return plotter.screenshot(path, **kwargs) if path else plotter.screenshot(**kwargs)


def bring_pyvista_window_to_front(plotter: Any, delay_s: float = 0.25) -> None:
    def worker() -> None:
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


def add_pyvista_keypress_observer(plotter: Any, key: str, callback: Any) -> None:
    target_key = str(key).lower()

    def on_key_press(obj: Any, _event: Any = None) -> None:
        try:
            key_sym = str(obj.GetKeySym() or "") if hasattr(obj, "GetKeySym") else ""
            key_code = str(obj.GetKeyCode() or "") if hasattr(obj, "GetKeyCode") else ""
            if key_sym.lower() == target_key or key_code.lower() == target_key:
                callback()
        except Exception as exc:
            _show_error("PyVista key command", exc)

    candidates = [
        getattr(plotter, "iren", None),
        getattr(plotter, "interactor", None),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        for obj in (candidate, getattr(candidate, "interactor", None)):
            add_observer = getattr(obj, "AddObserver", None) or getattr(obj, "add_observer", None)
            if callable(add_observer):
                try:
                    add_observer(
                        "KeyPressEvent",
                        lambda *args, _obj=obj: on_key_press(args[0] if args else _obj, args[1] if len(args) > 1 else None),
                    )
                    return
                except Exception:
                    pass


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
    if not clean or clean == FILE_PLACEHOLDER_TEXT:
        return paths
    try:
        clean = str(Path(clean).resolve())
    except Exception:
        pass
    updated = [clean] + [item for item in paths if os.path.normcase(item) != os.path.normcase(clean)]
    updated = updated[:MAX_RECENT_FILES]
    save_recent_files(updated)
    return updated


def filename_token(value: str, fallback: str = "item") -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\\/:\*\?\"<>\|]+", "_", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-Za-z0-9._+\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def _first_orca_keyword_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("!"):
            return stripped[1:].strip()
    return ""


def _first_gaussian_route(text: str) -> str:
    route_lines: List[str] = []
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            collecting = True
        if collecting:
            if not stripped and route_lines:
                break
            route_lines.append(stripped)
    return " ".join(route_lines)


def infer_calculation_filename_parts(path: str, file_kind: Optional[str]) -> Dict[str, str]:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8", errors="replace")[:400000]
    except Exception:
        text = ""

    functional = ""
    basis = ""
    solvent = ""
    job = "sp"

    if file_kind == "gaussian" or (file_kind is None and "#" in text[:2000]):
        route = _first_gaussian_route(text)
        method_match = re.search(r"([A-Za-z0-9+\-]+)\s*/\s*([A-Za-z0-9()*,+\-]+)", route)
        if method_match:
            functional = method_match.group(1)
            basis = method_match.group(2)
        solvent_match = re.search(r"Solvent\s*=\s*([A-Za-z0-9+\-]+)", route, re.IGNORECASE)
        if solvent_match and "SMD" in route.upper():
            solvent = solvent_match.group(1)
        route_upper = route.upper()
        if "OPT" in route_upper:
            job = "opt"
        elif "FREQ" in route_upper:
            job = "freq"
    else:
        keyword_line = _first_orca_keyword_line(text)
        tokens = keyword_line.split()
        skip = {
            "SP", "OPT", "FREQ", "ENGRAD", "NUMFREQ", "TIGHTSCF", "VERYTIGHTSCF", "NORMALSCF",
            "RIJCOSX", "DEFGRID1", "DEFGRID2", "DEFGRID3", "DEFGRID4", "DEFGRID5",
            "D3", "D3BJ", "D4", "MINIPRINT", "NORMALPRINT", "LARGEPRINT", "MAYER",
        }
        method_tokens = [tok for tok in tokens if tok.upper() not in skip and not tok.upper().startswith("GRID")]
        if method_tokens:
            functional = method_tokens[0]
        if len(method_tokens) > 1:
            basis = method_tokens[1]
        solvent_match = re.search(r"SMDsolvent\s+\"?([^\"\n\r]+)\"?", text, re.IGNORECASE)
        if solvent_match:
            solvent = solvent_match.group(1).strip()
        text_upper = text.upper()
        if re.search(r"^\s*%\s*GEOM\b", text, re.IGNORECASE | re.MULTILINE) and re.search(r"\{\s*[A-Za-z]+\s+\d+\s+C\s*\}", text):
            job = "constr"
        elif " OPT" in f" {keyword_line.upper()} ":
            job = "opt"
        elif " FREQ" in f" {keyword_line.upper()} ":
            job = "freq"
        elif "CONSTRAINTS" in text_upper:
            job = "constr"

    method = "_".join(part for part in (filename_token(functional, ""), filename_token(basis, "")) if part)
    stem = source.stem
    project = stem
    for marker in (functional, basis):
        clean_marker = filename_token(marker, "")
        if not clean_marker:
            continue
        idx = project.lower().find(clean_marker.lower())
        if idx > 0:
            project = project[:idx].rstrip("_- .")
            break
    project = filename_token(project, source.stem or "HOMO_LUMO")
    if not method:
        method = "method"

    return {
        "project": project,
        "method": method,
        "solvent": filename_token(solvent, "") if solvent else "",
        "job": filename_token(job, "sp"),
    }


# -----------------------------
# Plotting helpers
# -----------------------------

def build_labels(n: int, homo_i: int) -> List[str]:
    labels: List[str] = []
    for i in range(n):
        if i < homo_i:
            labels.append(f"HOMO-{homo_i - i}")
        elif i == homo_i:
            labels.append("HOMO")
        elif i == homo_i + 1:
            labels.append("LUMO")
        else:
            labels.append(f"LUMO+{i - (homo_i + 1)}")
    return labels


def _stagger_label_positions(
    energies: List[float],
    x1: float,
    base_dx: float = 0.035,
    col_dx: float = 0.075,
    min_sep_ev: float = 0.18,
    y_nudge_ev: float = 0.04,
) -> List[Tuple[float, float]]:
    positions: List[Tuple[float, float]] = []
    prev_e: Optional[float] = None
    toggle = 1

    for e in energies:
        x_text = x1 + base_dx
        y_text = e

        if prev_e is not None and abs(e - prev_e) < min_sep_ev:
            x_text = x1 + base_dx + col_dx
            y_text = e + toggle * y_nudge_ev
            toggle *= -1
        else:
            toggle = 1

        positions.append((x_text, y_text))
        prev_e = e

    return positions


def make_figure(
    energies: List[float],
    homo_i: int,
    title: str = "",
    label_min_sep_ev: float = 0.18,
    show_energy_values: bool = True,
) -> Tuple[plt.Figure, float]:
    if homo_i < 0 or homo_i >= len(energies) - 1:
        raise ValueError("Invalid HOMO index (LUMO = HOMO+1 must exist).")

    labels = build_labels(len(energies), homo_i)
    homo_e = energies[homo_i]
    lumo_e = energies[homo_i + 1]

    gap = lumo_e - homo_e
    gap_display = abs(gap)

    fig = plt.Figure(figsize=(6.2, 4.8), dpi=150, constrained_layout=False)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.28, right=0.96, top=0.92 if title.strip() else 0.96, bottom=0.08)

    ymin, ymax = min(energies), max(energies)
    pad = 0.10 * (ymax - ymin if ymax != ymin else 1.0)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_ylabel("Energy (eV)", labelpad=18)

    x0, x1 = 0.21, 0.58
    label_pos = _stagger_label_positions(
        energies=energies,
        x1=x1,
        base_dx=0.035,
        col_dx=0.075,
        min_sep_ev=label_min_sep_ev,
        y_nudge_ev=0.04,
    )

    for (lab, e), (x_text, y_text) in zip(zip(labels, energies), label_pos):
        ax.hlines(e, x0, x1, linewidth=2.2)
        if show_energy_values:
            ax.text(
                x0 - 0.025,
                e,
                f"{e:.3f}",
                va="center",
                ha="right",
                fontsize=8.5,
                color="#334155",
            )
        ax.text(x_text, y_text, lab, va="center")

    x_gap = 0.5 * (x0 + x1)
    ax.annotate(
        "",
        xy=(x_gap, lumo_e),
        xytext=(x_gap, homo_e),
        arrowprops=dict(arrowstyle="<->", linewidth=2.0),
    )
    ax.text(
        x_gap + 0.02,
        0.5 * (homo_e + lumo_e),
        f"{gap_display:.3f} eV",
        va="center",
        ha="left",
    )

    ax.set_xlim(0.0, 1.0)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if title.strip():
        ax.set_title(title.strip())

    return fig, gap_display


# -----------------------------
# ORCA parsing
# -----------------------------

_ORB_HEADER_RE = re.compile(r"^\s*ORBITAL\s+ENERGIES\s*$")
_ORB_ROW_RE = re.compile(rf"^\s*(\d+)\s+({_FLOAT})\s+({_FLOAT})\s+({_FLOAT})\s*$")

def parse_orca_orbital_energies_ev(out_path: str) -> List[Tuple[int, float, float]]:
    with open(out_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    start = None
    for i, line in enumerate(lines):
        if _ORB_HEADER_RE.match(line):
            start = i
            break
    if start is None:
        raise ValueError('Could not find "ORBITAL ENERGIES" in ORCA output.')

    rows: List[Tuple[int, float, float]] = []
    in_table = False

    for j in range(start + 1, len(lines)):
        line = lines[j].rstrip("\n")

        m = _ORB_ROW_RE.match(line)
        if m:
            in_table = True
            orb_no = int(m.group(1))
            occ = float(m.group(2))
            e_ev = float(m.group(4))
            rows.append((orb_no, occ, e_ev))
            continue

        if in_table:
            if not line.strip():
                break
            if line.strip().startswith("-"):
                break
            if _ORB_HEADER_RE.match(line):
                break

    if len(rows) < 2:
        raise ValueError('Found "ORBITAL ENERGIES" but could not parse rows (format mismatch).')

    return rows


def detect_homo_lumo_from_orca_rows(rows: List[Tuple[int, float, float]]) -> Tuple[int, int]:
    occ_positive = [r for r in rows if r[1] > 0.0]
    if not occ_positive:
        raise ValueError("Could not detect HOMO: no orbitals with OCC > 0.0.")
    homo_orb = max(occ_positive, key=lambda r: r[0])[0]
    lumo_orb = homo_orb + 1
    orb_numbers = {r[0] for r in rows}
    if lumo_orb not in orb_numbers:
        raise ValueError(f"Detected HOMO #{homo_orb}, but LUMO #{lumo_orb} not present.")
    return homo_orb, lumo_orb


def extract_window_from_orca(
    rows: List[Tuple[int, float, float]],
    homo_orb: int,
    n_below_homo: int,
    n_above_lumo: int,
) -> Tuple[List[float], int, Tuple[int, int]]:
    if n_below_homo < 0 or n_above_lumo < 0:
        raise ValueError("Range values must be non-negative integers.")

    orb_to_e = {orb: e for (orb, _occ, e) in rows}
    orb_start = homo_orb - n_below_homo
    orb_end = (homo_orb + 1) + n_above_lumo

    missing = [orb for orb in range(orb_start, orb_end + 1) if orb not in orb_to_e]
    if missing:
        raise ValueError(f"Requested MO range not fully present. Missing: {missing[:12]}")

    energies = [orb_to_e[orb] for orb in range(orb_start, orb_end + 1)]
    homo_i = homo_orb - orb_start
    return energies, homo_i, (orb_start, orb_end)


# -----------------------------
# ORCA MO surface helpers
# -----------------------------

def safe_orbital_label(prefix: str, offset: int) -> Tuple[str, str]:
    if prefix == "HOMO":
        if offset == 0:
            return "HOMO", "HOMO"
        return f"HOMO_m{abs(offset)}", f"HOMO−{abs(offset)}"
    if offset == 0:
        return "LUMO", "LUMO"
    return f"LUMO_p{offset}", f"LUMO+{offset}"


def build_orbital_surface_list(
    rows: List[Tuple[int, float, float]],
    homo_orb: int,
    n_below_homo: int,
    n_above_lumo: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if n_below_homo not in {0, 1, 2, 3} or n_above_lumo not in {0, 1, 2, 3}:
        raise ValueError("MO surface plot range supports values 0, 1, 2, or 3.")
    orb_to_e = {orb: e for orb, _occ, e in rows}
    orbitals: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for delta in range(-n_below_homo, 1):
        mo_no = homo_orb + delta
        safe, display = safe_orbital_label("HOMO", delta)
        if mo_no not in orb_to_e:
            warnings.append(f"Requested {display} maps to ORCA MO #{mo_no}, which is outside the parsed orbital table.")
            continue
        orbitals.append({"safe_label": safe, "display_label": display, "mo_number": mo_no, "energy_ev": orb_to_e.get(mo_no), "row": 0})

    lumo_orb = homo_orb + 1
    for delta in range(0, n_above_lumo + 1):
        mo_no = lumo_orb + delta
        safe, display = safe_orbital_label("LUMO", delta)
        if mo_no not in orb_to_e:
            warnings.append(f"Requested {display} maps to ORCA MO #{mo_no}, which is outside the parsed orbital table.")
            continue
        orbitals.append({"safe_label": safe, "display_label": display, "mo_number": mo_no, "energy_ev": orb_to_e.get(mo_no), "row": 1})

    if not orbitals:
        raise ValueError("No requested orbitals are available in the parsed ORBITAL ENERGIES table.")
    return orbitals, warnings


def mo_surface_paths(out_path: Path) -> Dict[str, Path]:
    base = out_path.stem
    root = out_path.with_name(f"{base}_MO_surfaces")
    return {
        "root": root,
        "cubes": root / "cubes",
        "images": root / "images",
        "thumbnails": root / "thumbnails",
        "metadata": root / "metadata",
        "metadata_file": root / "metadata" / f"{base}_MO_surfaces.json",
    }


def ensure_mo_surface_dirs(out_path: Path) -> Dict[str, Path]:
    paths = mo_surface_paths(out_path)
    for key in ("cubes", "images", "thumbnails", "metadata"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def load_mo_metadata(meta_path: Path) -> Dict[str, Any]:
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"orbitals": {}}


def save_mo_metadata(meta_path: Path, metadata: Dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def read_builder_orca_path() -> Optional[Path]:
    settings_paths = [
        TOOLS_ROOT / "Orca_input" / "orca_gaussian_builder_settings.json",
        APP_ROOT / "orca_gaussian_builder_settings.json",
    ]
    for settings_path in settings_paths:
        if not settings_path.is_file():
            continue
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("orca_path", "orca_executable", "ORCA executable"):
            raw = str(data.get(key) or "").strip().strip('"')
            if raw and Path(raw).is_file():
                return Path(raw)
    return None


def find_orca_plot(out_path: Path) -> Tuple[Optional[Path], List[Path]]:
    names = ["orca_plot.exe"] if os.name == "nt" else ["orca_plot", "orca_plot.exe"]
    searched: List[Path] = []

    def add_dir(directory: Optional[Path]) -> Optional[Path]:
        if not directory:
            return None
        for name in names:
            candidate = directory / name
            searched.append(candidate)
            if candidate.is_file():
                return candidate
        return None

    builder_orca = read_builder_orca_path()
    if builder_orca:
        found = add_dir(builder_orca.parent)
        if found:
            return found, searched

    for exe_name in ("orca.exe", "orca"):
        found_orca = shutil.which(exe_name)
        if found_orca:
            found = add_dir(Path(found_orca).parent)
            if found:
                return found, searched

    for plot_name in names:
        found_plot = shutil.which(plot_name)
        if found_plot:
            path = Path(found_plot)
            searched.append(path)
            return path, searched

    for directory in (out_path.parent, Path("C:/ORCA_6.0.1"), Path("C:/ORCA_6.0.0"), Path("C:/Program Files/ORCA")):
        found = add_dir(directory)
        if found:
            return found, searched

    return None, searched


def orca_plot_command_text(mo_number: int) -> str:
    # Documented ORCA interactive route:
    # 2 MO number, 3 alpha/beta operator, 4 grid intervals, 5 cube format,
    # 8 MO rather than AO, 11 generate, 12 exit.
    return "\n".join(["2", str(mo_number), "3", "0", "4", "80", "5", "7", "8", "0", "11", "12", ""]) 


def run_orca_plot_for_cube(gbw_path: Path, cube_path: Path, mo_number: int, orca_plot: Path, log_path: Path) -> None:
    before = {p.resolve() for p in gbw_path.parent.glob("*.cube")}
    command_text = orca_plot_command_text(mo_number)
    try:
        proc = subprocess.run(
            [str(orca_plot), str(gbw_path), "-i"],
            input=command_text,
            text=True,
            cwd=str(gbw_path.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            shell=False,
        )
    except Exception as exc:
        log_path.write_text(f"orca_plot execution failed:\n{exc}\n", encoding="utf-8")
        raise RuntimeError(f"Cube generation failed for MO #{mo_number}. Log: {log_path}") from exc

    log_path.write_text(
        "Command:\n"
        f"{orca_plot} {gbw_path} -i\n\n"
        "Input sent to orca_plot:\n"
        f"{command_text}\n\n"
        "STDOUT:\n"
        f"{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"orca_plot failed for MO #{mo_number}. See log: {log_path}")

    after = [p for p in gbw_path.parent.glob("*.cube") if p.resolve() not in before]
    if cube_path.is_file():
        return
    if len(after) == 1:
        shutil.move(str(after[0]), str(cube_path))
        return
    matching = sorted(gbw_path.parent.glob(f"*{mo_number}*.cube"), key=lambda p: p.stat().st_mtime, reverse=True)
    if matching:
        shutil.move(str(matching[0]), str(cube_path))
        return
    raise RuntimeError(f"orca_plot finished but no cube was detected for MO #{mo_number}. See log: {log_path}")


BOHR_PER_ANGSTROM = 1.8897259886


def parse_cube_file(cube_path: Path) -> Dict[str, Any]:
    lines = cube_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 6:
        raise ValueError(f"Cube file is too short: {cube_path}")
    parts = lines[2].split()
    natoms_signed = int(float(parts[0]))
    natoms = abs(natoms_signed)
    # ORCA/orca_plot cube coordinates are in Bohr. Negative atom count in
    # orbital cube files indicates dataset IDs follow the atom block, not
    # Angstrom coordinates.
    unit_scale = BOHR_PER_ANGSTROM
    origin = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=float)
    axes = []
    dims = []
    for idx in range(3, 6):
        row = lines[idx].split()
        dims.append(abs(int(float(row[0]))))
        axes.append([float(row[1]), float(row[2]), float(row[3])])
    atoms = []
    for line in lines[6:6 + natoms]:
        row = line.split()
        if len(row) >= 5:
            atomic_no = int(float(row[0]))
            atoms.append((atomic_no, float(row[2]), float(row[3]), float(row[4])))
    data_start = 6 + natoms
    dataset_ids: List[int] = []
    if natoms_signed < 0 and data_start < len(lines):
        id_row = lines[data_start].split()
        if id_row:
            try:
                n_dataset_ids = int(float(id_row[0]))
                dataset_ids = [int(float(x)) for x in id_row[1:1 + max(0, n_dataset_ids)]]
                data_start += 1
            except ValueError:
                dataset_ids = []

    values: List[float] = []
    for line in lines[data_start:]:
        values.extend(float(x.replace("D", "E").replace("d", "e")) for x in line.split())
    expected = dims[0] * dims[1] * dims[2]
    if len(values) < expected:
        raise ValueError(f"Cube file has {len(values)} values, expected {expected}: {cube_path}")
    data = np.array(values[:expected], dtype=float).reshape(tuple(dims), order="C")
    return {
        "origin": origin,
        "axes": np.array(axes, dtype=float),
        "dims": tuple(dims),
        "atoms": atoms,
        "data": data,
        "unit_scale": unit_scale,
        "dataset_ids": dataset_ids,
    }


def atomic_symbol(atomic_no: int) -> str:
    symbols = {
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
        83: "Bi", 84: "Po", 85: "At", 86: "Rn", 87: "Fr", 88: "Ra", 89: "Ac", 90: "Th",
        91: "Pa", 92: "U", 93: "Np", 94: "Pu", 95: "Am", 96: "Cm",
    }
    return symbols.get(atomic_no, str(atomic_no))


ATOM_COLORS = {
    "H": "white", "C": "#d1d5db", "N": "#93c5fd", "O": "#fca5a5", "F": "#bbf7d0",
    "Cl": "#86efac", "Br": "#fca5a5", "I": "#d8b4fe", "Fe": "#f4a261",
    "Co": "#f0a0b8", "Ni": "#86efac", "Cu": "#d19a66", "Zn": "#a5b4fc",
    "Ru": "#5eead4", "Rh": "#67e8f9", "Pd": "#67e8f9", "Ag": "#d1d5db",
    "Ir": "#60a5fa", "Pt": "#c7d2fe", "Au": "#fde047",
}
WIREFRAME_ATOM_COLORS = {
    "H": "#ffffff",
    "C": "#e5e7eb",
    "N": "#bfdbfe",
    "O": "#fecdd3",
    "F": "#dcfce7",
    "Cl": "#bbf7d0",
    "Br": "#fecaca",
    "I": "#e9d5ff",
    "Fe": "#fed7aa",
    "Co": "#fbcfe8",
    "Ni": "#bbf7d0",
    "Cu": "#fdba74",
    "Zn": "#c7d2fe",
    "Ru": "#99f6e4",
    "Rh": "#a5f3fc",
    "Pd": "#a5f3fc",
    "Ag": "#e5e7eb",
    "Ir": "#bfdbfe",
    "Pt": "#ddd6fe",
    "Au": "#fef08a",
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


def molecule_material_parameters(
    ambient: float = 0.82,
    diffuse: float = 0.86,
    specular: float = 0.16,
    specular_power: float = 20,
    pbr: bool = False,
    metallic: float = 0.0,
    roughness: float = 0.42,
) -> Dict[str, object]:
    params: Dict[str, object] = {
        "lighting": True,
        "smooth_shading": True,
        "ambient": ambient,
        "diffuse": diffuse,
        "specular": specular,
        "specular_power": specular_power,
    }
    if pbr:
        params.update({"pbr": True, "metallic": metallic, "roughness": roughness})
    return params


def capped_stick_material_parameters() -> Dict[str, object]:
    return {
        **molecule_material_parameters(
            ambient=0.86,
            diffuse=0.88,
            specular=0.20,
            specular_power=32,
            pbr=True,
            roughness=0.24,
        )
    }


def wireframe_material_parameters() -> Dict[str, object]:
    return molecule_material_parameters(
        ambient=0.92,
        diffuse=0.78,
        specular=0.14,
        specular_power=22,
        pbr=True,
        roughness=0.30,
    )


def add_mesh_safe(plotter, mesh, **kwargs):
    try:
        return plotter.add_mesh(mesh, **kwargs)
    except TypeError:
        safe_kwargs = dict(kwargs)
        safe_kwargs.pop("pbr", None)
        safe_kwargs.pop("metallic", None)
        safe_kwargs.pop("roughness", None)
        return plotter.add_mesh(mesh, **safe_kwargs)


def display_atom_radius(symbol: str, unit_scale: float = 1.0) -> float:
    radius_ang = float(np.clip(COVALENT_RADII.get(symbol, 0.77) * 0.42, 0.16, 0.55))
    return radius_ang * unit_scale


def cylinder_between(pv_module, p1, p2, radius, resolution=48):
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


def add_split_colored_bond(pv_module, plotter, p1, p2, color1, color2, radius, resolution=48, material=None):
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    midpoint = (p1 + p2) / 2.0
    material = molecule_material_parameters() if material is None else material
    for a, b, color in ((p1, midpoint, color1), (midpoint, p2, color2)):
        cylinder = cylinder_between(pv_module, a, b, radius=radius, resolution=resolution)
        if cylinder is not None:
            add_mesh_safe(plotter, cylinder, color=color, **material)


def add_atom_sphere(pv_module, plotter, center, radius, color, material=None, theta_resolution=64, phi_resolution=64):
    material = molecule_material_parameters() if material is None else material
    sphere = pv_module.Sphere(
        radius=radius,
        center=tuple(center),
        theta_resolution=theta_resolution,
        phi_resolution=phi_resolution,
    )
    add_mesh_safe(plotter, sphere, color=color, **material)


def infer_cube_bonds(atoms: List[Tuple[int, float, float, float]], unit_scale: float = 1.0) -> List[Tuple[int, int]]:
    bonds = []
    coords = [np.array([x, y, z], dtype=float) for _z, x, y, z in atoms]
    syms = [atomic_symbol(z) for z, *_ in atoms]
    for i in range(len(atoms)):
        for j in range(i + 1, len(atoms)):
            ri = COVALENT_RADII.get(syms[i], 0.8) * unit_scale
            rj = COVALENT_RADII.get(syms[j], 0.8) * unit_scale
            d = float(np.linalg.norm(coords[i] - coords[j]))
            if 0.25 * unit_scale < d <= 1.20 * (ri + rj):
                bonds.append((i, j))
    return bonds


def cube_to_pyvista_grid(cube: Dict[str, Any]):
    dims = cube["dims"]
    axes = cube["axes"]
    origin = cube["origin"]
    ii, jj, kk = np.meshgrid(
        np.arange(dims[0], dtype=float),
        np.arange(dims[1], dtype=float),
        np.arange(dims[2], dtype=float),
        indexing="ij",
    )
    points = (
        origin
        + ii[..., None] * axes[0]
        + jj[..., None] * axes[1]
        + kk[..., None] * axes[2]
    )
    grid = pv.StructuredGrid(points[..., 0], points[..., 1], points[..., 2])
    grid.point_data["orbital"] = cube["data"].ravel(order="F")
    return grid


def camera_position_to_json(camera_position: Any) -> Any:
    try:
        return [[float(v) for v in point] for point in camera_position]
    except Exception:
        return repr(camera_position)


def camera_position_from_state(camera_state: Any) -> Any:
    if isinstance(camera_state, dict):
        return camera_state.get("camera_position")
    return None


def capture_plotter_camera_state(plotter: Any) -> Dict[str, Any]:
    camera = getattr(plotter, "camera", None)
    state: Dict[str, Any] = {"camera_position": camera_position_to_json(plotter.camera_position)}
    if camera is None:
        return state
    for attr in ("parallel_scale", "view_angle", "clipping_range"):
        try:
            value = getattr(camera, attr)
            if isinstance(value, (tuple, list)):
                state[attr] = [float(v) for v in value]
            else:
                state[attr] = float(value)
        except Exception:
            pass
    try:
        state["parallel_projection"] = bool(camera.GetParallelProjection())
    except Exception:
        pass
    return state


def apply_plotter_camera_state(plotter: Any, camera_position: Any, camera_state: Optional[Dict[str, Any]] = None) -> None:
    plotter.camera_position = camera_position
    camera = getattr(plotter, "camera", None)
    if camera is None or not isinstance(camera_state, dict):
        return
    if "parallel_scale" in camera_state:
        try:
            camera.parallel_scale = float(camera_state["parallel_scale"])
        except Exception:
            pass
    if "view_angle" in camera_state:
        try:
            camera.view_angle = float(camera_state["view_angle"])
        except Exception:
            pass
    if "clipping_range" in camera_state:
        try:
            clipping = camera_state["clipping_range"]
            if isinstance(clipping, (list, tuple)) and len(clipping) == 2:
                camera.clipping_range = (float(clipping[0]), float(clipping[1]))
        except Exception:
            pass
    if "parallel_projection" in camera_state:
        try:
            if bool(camera_state["parallel_projection"]):
                camera.ParallelProjectionOn()
            else:
                camera.ParallelProjectionOff()
        except Exception:
            pass


# -----------------------------
# Gaussian parsing
# -----------------------------

_G_OCC_RE = re.compile(r"^\s*(?:Alpha|Beta)?\s*occ\.\s*eigenvalues\s*--\s*(.*)$", re.IGNORECASE)
_G_VIRT_RE = re.compile(r"^\s*(?:Alpha|Beta)?\s*virt\.\s*eigenvalues\s*--\s*(.*)$", re.IGNORECASE)
_G_FLOAT_RE = re.compile(_FLOAT)

HARTREE_TO_EV = 27.211386245988

def parse_gaussian_eigenvalues_ev(log_path: str) -> Tuple[List[float], int]:
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    occ_idx: List[int] = []
    virt_idx: List[int] = []
    for i, line in enumerate(lines):
        if _G_OCC_RE.match(line):
            occ_idx.append(i)
        if _G_VIRT_RE.match(line):
            virt_idx.append(i)

    if not occ_idx or not virt_idx:
        raise ValueError('Could not find Gaussian "occ./virt. eigenvalues" lines.')

    start = min(occ_idx[-1], virt_idx[-1])

    occ_h: List[float] = []
    virt_h: List[float] = []

    for j in range(start, len(lines)):
        line = lines[j]
        m_occ = _G_OCC_RE.match(line)
        m_virt = _G_VIRT_RE.match(line)

        if m_occ:
            occ_h.extend(float(x) for x in _G_FLOAT_RE.findall(m_occ.group(1)))
            continue
        if m_virt:
            virt_h.extend(float(x) for x in _G_FLOAT_RE.findall(m_virt.group(1)))
            continue

        if (occ_h or virt_h) and not line.strip():
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k >= len(lines):
                break
            if not (_G_OCC_RE.match(lines[k]) or _G_VIRT_RE.match(lines[k])):
                break

    if len(occ_h) < 1 or len(virt_h) < 1:
        raise ValueError("Gaussian eigenvalues found, but occ/virt lists could not be built (unexpected format).")

    energies_ev = [x * HARTREE_TO_EV for x in occ_h] + [x * HARTREE_TO_EV for x in virt_h]
    homo_i = len(occ_h) - 1
    return energies_ev, homo_i


def extract_window_from_gaussian(
    energies_ev: List[float],
    homo_i: int,
    n_below_homo: int,
    n_above_lumo: int,
) -> Tuple[List[float], int, Tuple[int, int]]:
    if n_below_homo < 0 or n_above_lumo < 0:
        raise ValueError("Range values must be non-negative integers.")
    if homo_i < 0 or homo_i >= len(energies_ev) - 1:
        raise ValueError("Gaussian HOMO index invalid.")

    start = homo_i - n_below_homo
    end = (homo_i + 1) + n_above_lumo
    if start < 0 or end >= len(energies_ev):
        raise ValueError("Requested range exceeds available Gaussian eigenvalues.")
    window = energies_ev[start:end + 1]
    homo_in_window = homo_i - start
    return window, homo_in_window, (start, end)


# -----------------------------
# GUI
# -----------------------------

def screen_fraction_height(widget: tk.Misc, fraction: float = 0.80, fallback: int = 800) -> int:
    try:
        return max(1, int(widget.winfo_screenheight() * fraction))
    except Exception:
        return fallback


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
        ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=8, sticky="n", padx=(0, 18))

    ttk.Label(box, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
    ttk.Label(box, text=purpose, justify="left", wraplength=420).grid(row=1, column=1, sticky="w", pady=(8, 0))
    ttk.Separator(box, orient="horizontal").grid(row=2, column=1, sticky="ew", pady=(12, 8))
    ttk.Label(box, text="GitHub").grid(row=3, column=1, sticky="w")
    github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
    github_link.grid(row=4, column=1, sticky="w", pady=(2, 0))
    github_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL))
    ttk.Label(box, text="Documentation").grid(row=5, column=1, sticky="w", pady=(8, 0))
    wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
    wiki_link.grid(row=6, column=1, sticky="w", pady=(2, 0))
    wiki_link.bind("<Button-1>", lambda _event: open_readme_or_wiki())
    ttk.Separator(box, orient="horizontal").grid(row=7, column=1, sticky="ew", pady=(12, 8))
    ttk.Label(box, text=COPYRIGHT_NOTE, foreground="#4b5563").grid(row=8, column=1, sticky="w")
    contact = ttk.Frame(box)
    contact.grid(row=9, column=1, sticky="w", pady=(7, 0))
    ttk.Label(contact, text=f"Email: {CONTACT_EMAIL}").grid(row=0, column=0, sticky="w")
    linkedin_icon = tk.Label(contact, text="in", bg="#0a66c2", fg="white", cursor="hand2", font=("Arial", 9, "bold"), padx=4, pady=1)
    linkedin_icon.grid(row=0, column=1, padx=(10, 0))
    linkedin_icon.bind("<Button-1>", lambda _event: webbrowser.open(LINKEDIN_URL))

    ttk.Button(box, text="Close", command=win.destroy).grid(row=10, column=0, columnspan=2, sticky="e", pady=(14, 0))
    win.geometry("590x370")
    win.minsize(530, 340)
    win.grab_set()


class MOSurfaceContactSheet(tk.Toplevel):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.title("MO Surface Contact Sheet")
        self.geometry("860x520")
        self.minsize(760, 420)
        configure_builder_ui_style(self)
        self.tiles: Dict[str, Dict[str, Any]] = {}
        self.thumbnail_refs: Dict[str, Any] = {}

        top = ttk.Frame(self, style="Panel.TFrame", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="MO Surface Contact Sheet", font=("Segoe UI", 11, "bold")).pack(side="left")
        ttk.Button(top, text="Save", command=self._save).pack(side="right")
        ttk.Button(top, text="Clean all", command=self._clean_all).pack(side="right", padx=(0, 6))

        self.grid_frame = ttk.Frame(self, style="Panel.TFrame", padding=8)
        self.grid_frame.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.tiles.clear()
        self.thumbnail_refs.clear()

        orbitals = self.app.mo_orbitals
        if not orbitals:
            ttk.Label(self.grid_frame, text="Generate MO cubes first.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            return

        for row_idx, row_orbs in enumerate(contact_sheet_rows(orbitals)):
            for col_idx, orbital in enumerate(row_orbs):
                self._add_tile(row_idx, col_idx, orbital)

    def _add_tile(self, row: int, col: int, orbital: Dict[str, Any]) -> None:
        safe = orbital["safe_label"]
        tile = ttk.Frame(self.grid_frame, relief="solid", padding=6)
        tile.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
        self.grid_frame.columnconfigure(col, weight=1)

        energy = orbital.get("energy_ev")
        tk.Label(
            tile,
            text=contact_sheet_orbital_label(orbital),
            font=("Segoe UI", 20, "bold"),
            bg=CONTACT_HEADER_BG,
            fg=CONTACT_HEADER_FG,
            anchor="center",
            padx=4,
            pady=2,
        ).pack(fill="x", pady=(0, 4))
        ttk.Label(tile, text=f"MO #{orbital['mo_number']}").pack(anchor="w")
        ttk.Label(tile, text="" if energy is None else f"{energy:.4f} eV", font=("Segoe UI", 18)).pack(anchor="w")

        img_label = ttk.Label(tile, text="No saved image", width=22, anchor="center", relief="groove")
        img_label.pack(fill="both", expand=True, pady=(6, 6))
        thumb_path = Path(orbital.get("thumbnail_path") or "")
        if Image is not None and ImageTk is not None and thumb_path.is_file():
            try:
                img = Image.open(thumb_path)
                img.thumbnail((170, 170))
                photo = ImageTk.PhotoImage(img)
                self.thumbnail_refs[safe] = photo
                img_label.configure(image=photo, text="")
            except Exception:
                pass

        ttk.Button(tile, text="Open / Replace view", command=lambda o=orbital: self.app.open_mo_surface_viewer(o)).pack(fill="x")
        ttk.Button(tile, text="Use view for all", command=lambda o=orbital: self.app.apply_mo_surface_view_to_all(o)).pack(fill="x", pady=(4, 0))
        self.tiles[safe] = {"frame": tile, "image": img_label}

    def _save(self) -> None:
        try:
            self.app.save_contact_sheet()
        except Exception as exc:
            _show_error("Save contact sheet", exc)

    def _clean_all(self) -> None:
        try:
            self.app.clean_all_mo_surfaces()
        except Exception as exc:
            _show_error("Clean MO surfaces", exc)


class App(tk.Tk):
    def __init__(self) -> None:
        set_windows_app_id("HOMOLUMO")
        super().__init__()
        configure_tk_window_identity(self, "HOMOLUMO")
        self.title("HOMO–LUMO Levels Plot")
        window_height = screen_fraction_height(self)
        self.geometry(f"1100x{window_height}")
        self.minsize(980, min(650, window_height))
        self.title("HOMO-LUMO")
        configure_builder_ui_style(self)

        self.current_fig: Optional[plt.Figure] = None
        self.current_gap: Optional[float] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.header_icon: Optional[tk.PhotoImage] = None

        self.file_kind: Optional[str] = None
        self.file_path: Optional[str] = None
        self.orca_rows: Optional[List[Tuple[int, float, float]]] = None
        self.orca_homo_lumo: Optional[Tuple[int, int]] = None
        self.gau_energies: Optional[List[float]] = None
        self.gau_homo_i: Optional[int] = None
        self.mo_orbitals: List[Dict[str, Any]] = []
        self.mo_metadata: Dict[str, Any] = {"orbitals": {}}
        self.mo_contact_sheet: Optional[MOSurfaceContactSheet] = None
        self.active_mo_plotter: Any = None
        self.mo_viewer_opening = False
        self.mo_batch_thread: Optional[threading.Thread] = None
        self.mo_status_var = tk.StringVar(value="No ORCA output loaded.")
        self.recent_input_files = load_recent_files()

        self._build_ui()
        self._load_startup_file()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        self.header_icon = load_header_icon(HOMO_LUMO_ICON_PATH)
        if self.header_icon is not None:
            tk.Label(header, image=self.header_icon, bg="#1e3a5f", bd=0, highlightthickness=0).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
        ttk.Label(header, text="HOMO-LUMO", style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(
            header,
            text="Frontier Orbital Energy Levels Plotter",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=1, sticky="w")
        header.columnconfigure(2, weight=1)
        about_link = ttk.Label(header, text="About", style="HeaderLink.TLabel", cursor="hand2")
        about_link.grid(row=0, column=3, rowspan=2, sticky="e")
        about_link.bind(
            "<Button-1>",
            lambda _event: open_about_dialog(self, "HOMO-LUMO Plotter", HOMO_LUMO_ICON_PATH, ABOUT_PURPOSE),
        )

        body = ttk.Frame(self, style="Panel.TFrame", padding=10)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        left_host = ttk.Frame(body, style="Panel.TFrame", width=400)
        left_host.grid(row=0, column=0, sticky="nsw")
        left_host.grid_propagate(False)
        left_host.rowconfigure(0, weight=1)
        left_host.columnconfigure(0, weight=1)
        left_canvas = tk.Canvas(left_host, width=380, highlightthickness=0, borderwidth=0, bg="#f4f6f9")
        left_scroll = ttk.Scrollbar(left_host, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll.grid(row=0, column=1, sticky="ns")
        self.left = ttk.Frame(left_canvas, style="Panel.TFrame", padding=(0, 0, 10, 0))
        left_window = left_canvas.create_window((0, 0), window=self.left, anchor="nw")
        self.left.bind("<Configure>", lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>", lambda e: left_canvas.itemconfigure(left_window, width=e.width))
        bind_mousewheel_to_canvas(left_canvas, self.left)

        self.right = ttk.Frame(body, style="Panel.TFrame")
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.grid_rowconfigure(1, weight=1)
        self.right.grid_columnconfigure(0, weight=1)

        self.opts = ttk.LabelFrame(self.left, text="HOMO LUMO gap image options", padding=8)

        ttk.Label(self.opts, text="Title (optional):").pack(anchor="w")
        self.title_var = tk.StringVar(value="")
        ttk.Entry(self.opts, textvariable=self.title_var, width=34).pack(anchor="w", pady=(2, 8))

        ttk.Label(self.opts, text="Label crowding threshold (eV):").pack(anchor="w")
        self.sep_var = tk.StringVar(value="0.18")
        ttk.Entry(self.opts, textvariable=self.sep_var, width=10).pack(anchor="w", pady=(2, 8))
        self.show_energy_values_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.opts,
            text="Show eV values beside levels",
            variable=self.show_energy_values_var,
        ).pack(anchor="w", pady=(0, 0))

        self.info = ttk.Label(self.left, text="", style="Muted.TLabel", wraplength=360, justify="left")

        # Auto-detected ORCA/Gaussian file
        self.file_box = ttk.LabelFrame(self.left, text="ORCA/Gaussian file", padding=8)
        self.file_path_var = tk.StringVar(value="")
        self.file_entry = ttk.Combobox(self.file_box, textvariable=self.file_path_var, values=self.recent_input_files, width=36)
        keep_entry_end_visible(self.file_entry, self.file_path_var)
        self.file_entry.pack(fill="x")
        self.file_entry.bind("<<ComboboxSelected>>", lambda _e: self._load_recent_selection())
        self._init_file_placeholder()
        ttk.Button(self.file_box, text="Browse file...", command=self.on_browse_file).pack(fill="x", pady=(6, 0))

        self.file_homo_minus_var = tk.StringVar(value="2")
        self.file_lumo_plus_var = tk.StringVar(value="2")
        self._add_range_controls(self.file_box, self.file_homo_minus_var, self.file_lumo_plus_var)

        self.file_box.pack(fill="x")

        self._build_mo_surface_controls()
        self.opts.pack(fill="x", pady=(10, 0))
        self.info.pack(anchor="w", pady=(10, 0), fill="x")

        # Preview
        ttk.Label(self.right, text="Preview", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.preview_frame = ttk.Frame(self.right, style="Panel.TFrame", relief="solid")
        self.preview_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        self.btns = ttk.Frame(self.right, style="Panel.TFrame")
        self.btns.grid(row=2, column=0, pady=(10, 0))
        ttk.Button(self.btns, text="Preview plot", command=self.on_preview, style="Primary.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(self.btns, text="Save (PNG or SVG)", command=self.on_save).pack(side="left")

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 6))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, text=COPYRIGHT_NOTE, style="Muted.TLabel").pack(anchor="w")

    def _build_mo_surface_controls(self) -> None:
        self.mo_box = ttk.LabelFrame(self.left, text="MO surfaces", padding=8)
        self.mo_box.pack(fill="x", pady=(10, 0))

        row1 = ttk.Frame(self.mo_box)
        row1.pack(fill="x")
        ttk.Label(row1, text="Window from plot range").grid(row=0, column=0, columnspan=2, sticky="w")

        row2 = ttk.Frame(self.mo_box)
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Isovalue").grid(row=0, column=0, sticky="w")
        self.mo_isovalue_var = tk.StringVar(value="0.03")
        ttk.Entry(row2, textvariable=self.mo_isovalue_var, width=8).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(row2, text="Opacity").grid(row=0, column=2, sticky="w")
        self.mo_opacity_var = tk.DoubleVar(value=1.00)
        self.mo_opacity_label_var = tk.StringVar(value="1.00")
        opacity_scale = ttk.Scale(
            row2,
            from_=0.05,
            to=1.0,
            variable=self.mo_opacity_var,
            command=self._on_mo_opacity_changed,
            length=115,
        )
        opacity_scale.grid(row=0, column=3, sticky="we", padx=(6, 4))
        ttk.Label(row2, textvariable=self.mo_opacity_label_var, width=4).grid(row=0, column=4, sticky="w")

        row3 = ttk.Frame(self.mo_box)
        row3.pack(fill="x", pady=(8, 0))
        ttk.Label(row3, text="Molecule style").grid(row=0, column=0, sticky="w")
        self.mo_molecule_style_var = tk.StringVar(value=DEFAULT_MO_MOLECULE_STYLE)
        ttk.Combobox(
            row3,
            textvariable=self.mo_molecule_style_var,
            values=MO_MOLECULE_STYLES,
            width=24,
            state="readonly",
        ).grid(row=0, column=1, columnspan=3, sticky="w", padx=(6, 0))

        row3b = ttk.Frame(self.mo_box)
        row3b.pack(fill="x", pady=(8, 0))
        ttk.Label(row3b, text="Image resolution").grid(row=0, column=0, sticky="w")
        self.image_resolution_var = tk.StringVar(value=DEFAULT_IMAGE_PRESET)
        presets = list(IMAGE_PRESETS.keys()) + ["Custom"]
        ttk.Combobox(row3b, textvariable=self.image_resolution_var, values=presets, width=30, state="readonly").grid(row=0, column=1, columnspan=3, sticky="w", padx=(6, 0))

        row4 = ttk.Frame(self.mo_box)
        row4.pack(fill="x", pady=(6, 0))
        ttk.Label(row4, text="Color scheme").grid(row=0, column=0, sticky="w")
        self.mo_color_scheme_var = tk.StringVar(value=DEFAULT_MO_COLOR_SCHEME)
        ttk.Combobox(row4, textvariable=self.mo_color_scheme_var, values=list(MO_COLOR_SCHEMES.keys()), width=24, state="readonly").grid(row=0, column=1, columnspan=3, sticky="w", padx=(6, 0))

        row4b = ttk.Frame(self.mo_box)
        row4b.pack(fill="x", pady=(6, 0))
        ttk.Label(row4b, text="Width").grid(row=0, column=0, sticky="w")
        self.custom_width_var = tk.StringVar(value="6000")
        ttk.Entry(row4b, textvariable=self.custom_width_var, width=8).grid(row=0, column=1, sticky="w", padx=(6, 12))
        ttk.Label(row4b, text="Height").grid(row=0, column=2, sticky="w")
        self.custom_height_var = tk.StringVar(value="4500")
        ttk.Entry(row4b, textvariable=self.custom_height_var, width=8).grid(row=0, column=3, sticky="w", padx=(6, 0))

        row5 = ttk.Frame(self.mo_box)
        row5.pack(fill="x", pady=(8, 0))
        row5.columnconfigure(0, weight=1)
        row5.columnconfigure(1, weight=1)
        ttk.Button(row5, text="Generate cubes", command=self.generate_mo_cubes).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(row5, text="MO surfaces view", command=self.open_mo_contact_sheet).grid(row=0, column=1, sticky="ew")

    def _on_mo_opacity_changed(self, _value: Any = None) -> None:
        try:
            self.mo_opacity_label_var.set(f"{float(self.mo_opacity_var.get()):.2f}")
        except Exception:
            self.mo_opacity_label_var.set("?")

    def _add_range_controls(self, parent: ttk.LabelFrame, homo_minus_var: tk.StringVar, lumo_plus_var: tk.StringVar) -> None:
        rng = ttk.Frame(parent)
        rng.pack(fill="x", pady=(10, 0))

        ttk.Label(rng, text="Plot range:").grid(row=0, column=0, sticky="w", padx=(0, 8))

        ttk.Label(rng, text="HOMO -").grid(row=0, column=1, sticky="w", padx=(0, 4))
        ttk.Entry(rng, textvariable=homo_minus_var, width=6).grid(row=0, column=2, sticky="w")

        ttk.Label(rng, text="LUMO +").grid(row=0, column=3, sticky="w", padx=(12, 4))
        ttk.Entry(rng, textvariable=lumo_plus_var, width=6).grid(row=0, column=4, sticky="w")

    def _init_file_placeholder(self) -> None:
        self.file_path_var.set(FILE_PLACEHOLDER_TEXT)
        self.file_entry.bind("<FocusIn>", self._on_file_focus_in)
        self.file_entry.bind("<FocusOut>", self._on_file_focus_out)

    def _on_file_focus_in(self, _event=None) -> None:
        if self.file_path_var.get().strip() == FILE_PLACEHOLDER_TEXT:
            self.file_path_var.set("")

    def _on_file_focus_out(self, _event=None) -> None:
        if not self.file_path_var.get().strip():
            self.file_path_var.set(FILE_PLACEHOLDER_TEXT)

    def _load_startup_file(self) -> None:
        if len(sys.argv) < 2:
            return
        path = sys.argv[1].strip().strip('"')
        if not path:
            return
        try:
            self.file_path_var.set(path)
            self._load_detected_file(path)
            self._remember_recent_input(path)
            self.after(100, self.on_preview)
        except Exception as e:
            _show_error("Startup file parse error", e)

    def _remember_recent_input(self, path: str) -> None:
        self.recent_input_files = remember_recent_file(path, self.recent_input_files)
        try:
            self.file_entry.configure(values=self.recent_input_files)
        except Exception:
            pass

    def _load_recent_selection(self) -> None:
        path = self.file_path_var.get().strip()
        if not path or path == FILE_PLACEHOLDER_TEXT:
            return
        try:
            self._load_detected_file(path)
            self._remember_recent_input(path)
        except Exception as e:
            self._reset_file_data()
            _show_error("File parse error", e)

    def _get_label_sep(self) -> float:
        v = float(self.sep_var.get().strip())
        if v <= 0:
            raise ValueError("Label crowding threshold must be > 0.")
        return v

    def _safe_int(self, s: str, field: str) -> int:
        s = s.strip()
        if not s:
            raise ValueError(f"{field} must be an integer.")
        try:
            v = int(s)
        except ValueError as e:
            raise ValueError(f"{field} must be an integer.") from e
        if v < 0:
            raise ValueError(f"{field} must be >= 0.")
        return v

    # -------- Auto-detected ORCA/Gaussian file --------
    def _reset_file_data(self) -> None:
        self._close_active_mo_plotter()
        self.file_kind = None
        self.file_path = None
        self.orca_rows = None
        self.orca_homo_lumo = None
        self.gau_energies = None
        self.gau_homo_i = None
        self.mo_orbitals = []
        self.mo_metadata = {"orbitals": {}}
        self.mo_status_var.set("No ORCA output loaded.")

    def _load_detected_file(self, path: str) -> None:
        self._reset_file_data()

        orca_error: Optional[BaseException] = None
        gaussian_error: Optional[BaseException] = None

        try:
            rows = parse_orca_orbital_energies_ev(path)
            homo_orb, lumo_orb = detect_homo_lumo_from_orca_rows(rows)
            self.file_kind = "orca"
            self.file_path = path
            self.orca_rows = rows
            self.orca_homo_lumo = (homo_orb, lumo_orb)
            self.mo_status_var.set("")
            self._remember_recent_input(path)
            return
        except Exception as e:
            orca_error = e

        try:
            energies_ev, homo_i = parse_gaussian_eigenvalues_ev(path)
            self.file_kind = "gaussian"
            self.file_path = path
            self.gau_energies = energies_ev
            self.gau_homo_i = homo_i
            self._remember_recent_input(path)
            return
        except Exception as e:
            gaussian_error = e

        raise ValueError(
            "Could not detect a supported ORCA or Gaussian file.\n\n"
            f"ORCA check: {orca_error}\n"
            f"Gaussian check: {gaussian_error}"
        )

    def on_browse_file(self) -> None:
        try:
            path = filedialog.askopenfilename(
                title="Select ORCA or Gaussian file",
                filetypes=[
                    ("ORCA/Gaussian files", "*.inp *.in *.out *.log *.gjf *.com *.txt"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return

            self.file_path_var.set(path)
            self._load_detected_file(path)
        except Exception as e:
            self._reset_file_data()
            _show_error("File parse error", e)

    def _ensure_file_loaded(self) -> None:
        path = self.file_path_var.get().strip()
        if path == FILE_PLACEHOLDER_TEXT:
            path = ""
        if not path:
            raise ValueError("Select an ORCA/Gaussian file first.")
        if path != self.file_path or self.file_kind is None:
            self._load_detected_file(path)

    def _get_orca_inputs(self) -> Tuple[List[float], int, str]:
        if self.orca_rows is None or self.orca_homo_lumo is None:
            raise ValueError("Select a supported ORCA file first.")

        n_below = self._safe_int(self.file_homo_minus_var.get(), "HOMO -")
        n_above = self._safe_int(self.file_lumo_plus_var.get(), "LUMO +")

        homo_orb, _ = self.orca_homo_lumo
        energies, homo_i, (orb_start, orb_end) = extract_window_from_orca(
            rows=self.orca_rows,
            homo_orb=homo_orb,
            n_below_homo=n_below,
            n_above_lumo=n_above,
        )
        return energies, homo_i, f"ORCA: orbitals #{orb_start} ... #{orb_end}"

    def _get_gaussian_inputs(self) -> Tuple[List[float], int, str]:
        if self.gau_energies is None or self.gau_homo_i is None:
            raise ValueError("Select a supported Gaussian file first.")

        n_below = self._safe_int(self.file_homo_minus_var.get(), "HOMO -")
        n_above = self._safe_int(self.file_lumo_plus_var.get(), "LUMO +")

        window, homo_in_window, (start, end) = extract_window_from_gaussian(
            energies_ev=self.gau_energies,
            homo_i=self.gau_homo_i,
            n_below_homo=n_below,
            n_above_lumo=n_above,
        )
        return window, homo_in_window, f"Gaussian: levels idx {start+1} ... {end+1}"

    # -------- MO surface workflow --------
    def _require_orca_out_for_surfaces(self) -> Path:
        self._ensure_file_loaded()
        if self.file_kind != "orca" or not self.file_path:
            raise ValueError("MO surfaces require a finished ORCA .out file.")
        out_path = Path(self.file_path)
        if not out_path.is_file():
            raise FileNotFoundError("Missing .out file.")
        if out_path.suffix.lower() != ".out":
            raise ValueError("MO surfaces require a finished ORCA .out file.")
        return out_path

    def _mo_surface_settings(self) -> Tuple[int, int, float, float]:
        n_below = self._safe_int(self.file_homo_minus_var.get(), "HOMO -")
        n_above = self._safe_int(self.file_lumo_plus_var.get(), "LUMO +")
        if n_below not in {0, 1, 2, 3} or n_above not in {0, 1, 2, 3}:
            raise ValueError("MO surfaces support plot range values 0, 1, 2, or 3 for HOMO - and LUMO +.")
        try:
            isovalue = float(self.mo_isovalue_var.get())
        except ValueError as exc:
            raise ValueError("Invalid isovalue.") from exc
        if isovalue <= 0:
            raise ValueError("Invalid isovalue: value must be > 0.")
        try:
            opacity = float(self.mo_opacity_var.get())
        except ValueError as exc:
            raise ValueError("Invalid opacity.") from exc
        if not (0.0 < opacity <= 1.0):
            raise ValueError("Invalid opacity: value must be > 0 and <= 1.")
        return n_below, n_above, isovalue, opacity

    def _current_mo_visual_settings(self) -> Tuple[float, float]:
        try:
            isovalue = float(self.mo_isovalue_var.get())
        except Exception as exc:
            raise ValueError("Invalid isovalue.") from exc
        if isovalue <= 0:
            raise ValueError("Invalid isovalue: value must be > 0.")
        try:
            opacity = float(self.mo_opacity_var.get())
        except Exception as exc:
            raise ValueError("Invalid opacity.") from exc
        if not (0.0 < opacity <= 1.0):
            raise ValueError("Invalid opacity: value must be > 0 and <= 1.")
        return isovalue, opacity

    def _selected_image_resolution(self) -> Tuple[str, int, int]:
        preset = self.image_resolution_var.get()
        if preset in IMAGE_PRESETS:
            w, h = IMAGE_PRESETS[preset]
            return preset, w, h
        if preset != "Custom":
            raise ValueError("Invalid image resolution preset.")
        try:
            w = int(self.custom_width_var.get())
            h = int(self.custom_height_var.get())
        except ValueError as exc:
            raise ValueError("Custom image width and height must be positive integers.") from exc
        if w < 500 or h < 500:
            raise ValueError("Custom image width and height must be at least 500 px.")
        if w > 10000 or h > 10000:
            if not messagebox.askyesno("Large image", "One custom image dimension is above 10000 px. Continue?"):
                raise ValueError("High-resolution save cancelled.")
        return "Custom", w, h

    def _prepare_mo_orbitals(self) -> Tuple[Path, Dict[str, Path], List[Dict[str, Any]], float, float]:
        out_path = self._require_orca_out_for_surfaces()
        if self.orca_rows is None or self.orca_homo_lumo is None:
            raise ValueError("ORBITAL ENERGIES not found or not parsed.")
        n_below, n_above, isovalue, opacity = self._mo_surface_settings()
        orbitals, warnings = build_orbital_surface_list(self.orca_rows, self.orca_homo_lumo[0], n_below, n_above)
        paths = ensure_mo_surface_dirs(out_path)
        base = out_path.stem
        meta = load_mo_metadata(paths["metadata_file"])

        for orbital in orbitals:
            cube = paths["cubes"] / f"{base}_{orbital['safe_label']}.cube"
            image = paths["images"] / f"{base}_{orbital['safe_label']}_view.png"
            thumb = paths["thumbnails"] / f"{base}_{orbital['safe_label']}_thumb.png"
            orbital.update({"cube_path": str(cube), "image_path": str(image), "thumbnail_path": str(thumb), "isovalue": isovalue, "opacity": opacity})
            saved = image.is_file()
            existing = meta.get("orbitals", {}).get(orbital["safe_label"], {})
            existing_camera_position = existing.get("camera_position")
            if existing_camera_position is None:
                existing_camera_position = camera_position_from_state(existing.get("camera_state"))
            if existing_camera_position is not None:
                orbital["camera_position"] = existing_camera_position
            if existing.get("camera_state") is not None:
                orbital["camera_state"] = existing.get("camera_state")
            for visual_key in ("isovalue", "opacity", "color_scheme"):
                if existing.get(visual_key) is not None:
                    orbital[visual_key] = existing.get(visual_key)
            existing.update({
                "safe_label": orbital["safe_label"],
                "display_label": orbital["display_label"],
                "orca_mo_number": orbital["mo_number"],
                "orbital_energy_ev": orbital.get("energy_ev"),
                "cube_path": str(cube),
                "image_path": str(image),
                "thumbnail_path": str(thumb),
                "isovalue": isovalue,
                "opacity": opacity,
                "saved_status": bool(saved),
            })
            meta.setdefault("orbitals", {})[orbital["safe_label"]] = existing

        save_mo_metadata(paths["metadata_file"], meta)
        self.mo_metadata = meta
        self.mo_orbitals = orbitals
        if warnings:
            messagebox.showwarning("MO surface range", "\n".join(warnings))
        return out_path, paths, orbitals, isovalue, opacity

    def generate_mo_cubes(self) -> None:
        try:
            self._close_active_mo_plotter()
            out_path, paths, orbitals, _isovalue, _opacity = self._prepare_mo_orbitals()
            gbw_path = out_path.with_suffix(".gbw")
            if not gbw_path.is_file():
                raise FileNotFoundError("Cannot generate MO cubes: matching .gbw file was not found.")
            orca_plot, searched = find_orca_plot(out_path)
            if orca_plot is None:
                searched_text = "\n".join(str(p) for p in searched) or "(no paths searched)"
                raise FileNotFoundError("orca_plot was not found. Searched paths:\n" + searched_text)

            report = []
            regenerate = True
            for orbital in orbitals:
                cube_path = Path(orbital["cube_path"])
                if cube_path.is_file() and not regenerate:
                    report.append(f"Reused {cube_path.name}")
                    continue
                log_path = paths["metadata"] / f"{out_path.stem}_{orbital['safe_label']}_orca_plot.log"
                if cube_path.exists():
                    cube_path.unlink()
                run_orca_plot_for_cube(gbw_path, cube_path, int(orbital["mo_number"]), orca_plot, log_path)
                report.append(f"Generated {cube_path.name}")

            self.mo_status_var.set(f"MO cubes ready in {paths['cubes']}")
            messagebox.showinfo("MO cubes", "\n".join(report))
            self.open_mo_contact_sheet()
        except Exception as exc:
            _show_error("Generate MO cubes", exc)

    def open_mo_contact_sheet(self) -> None:
        try:
            if not self.mo_orbitals:
                self._prepare_mo_orbitals()
            if self.mo_contact_sheet is None or not self.mo_contact_sheet.winfo_exists():
                self.mo_contact_sheet = MOSurfaceContactSheet(self)
            else:
                self.mo_contact_sheet.refresh()
                self.mo_contact_sheet.lift()
        except Exception as exc:
            _show_error("MO Surface Contact Sheet", exc)

    def _build_orbital_plotter(
        self,
        orbital: Dict[str, Any],
        off_screen: bool = False,
        window_size: Tuple[int, int] = (1100, 800),
        show_prompt: bool = False,
        render_options: Optional[Dict[str, Any]] = None,
    ):
        if pv is None or np is None:
            raise RuntimeError("PyVista and NumPy are required for MO surface viewing.")
        cube_path = Path(orbital["cube_path"])
        if not cube_path.is_file():
            raise FileNotFoundError(f"Cube file was not found:\n{cube_path}")
        cube = parse_cube_file(cube_path)
        grid = cube_to_pyvista_grid(cube)
        render_options = render_options or {}
        if "isovalue" in render_options and "opacity" in render_options:
            isovalue = float(render_options["isovalue"])
            opacity = float(render_options["opacity"])
        else:
            isovalue, opacity = self._current_mo_visual_settings()
        orbital["isovalue"] = isovalue
        orbital["opacity"] = opacity

        plotter = pv.Plotter(window_size=window_size, off_screen=off_screen, lighting="light kit")
        plotter.set_background("white")
        try:
            plotter.hide_axes()
            plotter.remove_bounds_axes()
            if hasattr(plotter.renderer, "hide_axes"):
                plotter.renderer.hide_axes()
            axes_widget = getattr(plotter.renderer, "axes_widget", None)
            if axes_widget is not None:
                axes_widget.EnabledOff()
        except Exception:
            pass
        try:
            plotter.enable_parallel_projection()
            plotter.enable_depth_peeling(number_of_peels=8, occlusion_ratio=0.0)
            plotter.renderer.SetTwoSidedLighting(True)
        except Exception:
            pass
        try:
            plotter.remove_all_lights()
            for light_type, intensity in (("headlight", 0.80), ("camera light", 0.35)):
                light = pv.Light(light_type=light_type)
                light.intensity = intensity
                plotter.add_light(light)
            plotter.add_light(pv.Light(position=(8, -10, 12), focal_point=(0, 0, 0), intensity=0.95, light_type="scene light"))
            plotter.add_light(pv.Light(position=(-8, 9, 10), focal_point=(0, 0, 0), intensity=0.55, light_type="scene light"))
            plotter.add_light(pv.Light(position=(0, 14, 6), focal_point=(0, 0, 0), intensity=0.25, light_type="scene light"))
        except Exception:
            pass

        color_scheme = str(render_options.get("color_scheme") or self.mo_color_scheme_var.get())
        pos_color, neg_color = MO_COLOR_SCHEMES.get(color_scheme, MO_COLOR_SCHEMES[DEFAULT_MO_COLOR_SCHEME])
        surface_material = {
            "lighting": True,
            "smooth_shading": True,
            "pbr": True,
            "metallic": 0.0,
            "roughness": 0.18,
            "specular": 0.55,
            "specular_power": 48,
            "ambient": 0.34,
            "diffuse": 0.96,
        }
        for value, color in ((isovalue, pos_color), (-isovalue, neg_color)):
            try:
                mesh = grid.contour([value], scalars="orbital")
                if mesh.n_points > 0:
                    for component in visible_surface_components(mesh):
                        try:
                            plotter.add_mesh(component, color=color, opacity=opacity, **surface_material)
                        except TypeError:
                            fallback = dict(surface_material)
                            fallback.pop("pbr", None)
                            fallback.pop("metallic", None)
                            fallback.pop("roughness", None)
                            plotter.add_mesh(component, color=color, opacity=opacity, **fallback)
            except Exception:
                pass

        atoms = cube["atoms"]
        unit_scale = float(cube.get("unit_scale", 1.0))
        coords = [np.array([x, y, z], dtype=float) for _z, x, y, z in atoms]
        bonds = infer_cube_bonds(atoms, unit_scale=unit_scale)
        atom_bond_counts = [0] * len(atoms)
        for i, j in bonds:
            atom_bond_counts[i] += 1
            atom_bond_counts[j] += 1
        molecule_style = str(render_options.get("molecule_style") or self.mo_molecule_style_var.get())
        if molecule_style not in MO_MOLECULE_STYLES:
            molecule_style = DEFAULT_MO_MOLECULE_STYLE

        if molecule_style == "Capped sticks":
            bond_radius = 0.085 * unit_scale
            cap_radius = 0.108 * unit_scale
            material = capped_stick_material_parameters()
            for i, j in bonds:
                sym_i = atomic_symbol(atoms[i][0])
                sym_j = atomic_symbol(atoms[j][0])
                add_split_colored_bond(
                    pv,
                    plotter,
                    coords[i],
                    coords[j],
                    ATOM_COLORS.get(sym_i, "#FF69B4"),
                    ATOM_COLORS.get(sym_j, "#FF69B4"),
                    radius=bond_radius,
                    resolution=72,
                    material=material,
                )
            for atom_idx, (atomic_no, x, y, z) in enumerate(atoms):
                sym = atomic_symbol(atomic_no)
                radius = cap_radius if atom_bond_counts[atom_idx] else display_atom_radius(sym, unit_scale=unit_scale) * 0.72
                add_atom_sphere(
                    pv,
                    plotter,
                    (x, y, z),
                    radius=radius,
                    color=ATOM_COLORS.get(sym, "#FF69B4"),
                    material=material,
                    theta_resolution=72,
                    phi_resolution=72,
                )
        elif molecule_style == "Ball-and-stick":
            bond_radius = 0.065 * unit_scale
            material = capped_stick_material_parameters()
            for i, j in bonds:
                sym_i = atomic_symbol(atoms[i][0])
                sym_j = atomic_symbol(atoms[j][0])
                add_split_colored_bond(
                    pv,
                    plotter,
                    coords[i],
                    coords[j],
                    ATOM_COLORS.get(sym_i, "#FF69B4"),
                    ATOM_COLORS.get(sym_j, "#FF69B4"),
                    radius=bond_radius,
                    resolution=64,
                    material=material,
                )
            for atomic_no, x, y, z in atoms:
                sym = atomic_symbol(atomic_no)
                add_atom_sphere(
                    pv,
                    plotter,
                    (x, y, z),
                    radius=display_atom_radius(sym, unit_scale=unit_scale),
                    color=ATOM_COLORS.get(sym, "#FF69B4"),
                    material=material,
                    theta_resolution=72,
                    phi_resolution=72,
                )
        else:
            bond_radius = 0.024 * unit_scale
            point_radius = 0.055 * unit_scale
            material = wireframe_material_parameters()
            for i, j in bonds:
                sym_i = atomic_symbol(atoms[i][0])
                sym_j = atomic_symbol(atoms[j][0])
                add_split_colored_bond(
                    pv,
                    plotter,
                    coords[i],
                    coords[j],
                    WIREFRAME_ATOM_COLORS.get(sym_i, ATOM_COLORS.get(sym_i, "#FF69B4")),
                    WIREFRAME_ATOM_COLORS.get(sym_j, ATOM_COLORS.get(sym_j, "#FF69B4")),
                    radius=bond_radius,
                    resolution=32,
                    material=material,
                )
            for atomic_no, x, y, z in atoms:
                sym = atomic_symbol(atomic_no)
                add_atom_sphere(
                    pv,
                    plotter,
                    (x, y, z),
                    radius=point_radius,
                    color=WIREFRAME_ATOM_COLORS.get(sym, ATOM_COLORS.get(sym, "#FF69B4")),
                    material=material,
                    theta_resolution=32,
                    phi_resolution=32,
                )

        if show_prompt:
            plotter.add_text("Click S to save", position="upper_left", font_size=11, color="black", name="save_prompt")

        plotter.reset_camera()
        return plotter

    def _close_active_mo_plotter(self) -> None:
        plotter = self.active_mo_plotter
        self.active_mo_plotter = None
        self._dispose_mo_plotter(plotter)

    def _dispose_mo_plotter(self, plotter: Any) -> None:
        if plotter is None:
            return
        for action in ("close", "deep_clean"):
            method = getattr(plotter, action, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        try:
            gc.collect()
        except Exception:
            pass

    def open_mo_surface_viewer(self, orbital: Dict[str, Any]) -> None:
        if self.mo_viewer_opening:
            return
        self.mo_viewer_opening = True
        plotter = None
        try:
            self._close_active_mo_plotter()
            self._restore_mo_visual_settings_for_orbital(orbital)
            plotter = self._build_orbital_plotter(orbital, off_screen=False, window_size=LIVE_MO_VIEW_SIZE, show_prompt=True)
            self.active_mo_plotter = plotter
            try:
                apply_plotter_camera_state(
                    plotter,
                    self._saved_camera_position_for_orbital(orbital),
                    self._saved_camera_state_for_orbital(orbital, require=False),
                )
                plotter.render()
            except ValueError:
                pass

            save_in_progress = False
            save_completed = False

            def save_current_view() -> None:
                nonlocal save_in_progress, save_completed
                if save_in_progress or save_completed:
                    return
                save_in_progress = True
                try:
                    try:
                        plotter.remove_actor("save_prompt", render=False)
                    except Exception:
                        pass
                    try:
                        plotter.render()
                    except Exception:
                        pass
                    live_image = plotter.screenshot(return_img=True, window_size=plotter.window_size, scale=1)
                    camera_position = plotter.camera_position
                    camera_state = capture_plotter_camera_state(plotter)
                    self._close_active_mo_plotter()
                    self.save_mo_surface_view(
                        orbital,
                        camera_position,
                        live_image=live_image,
                        camera_state=camera_state,
                    )
                    save_completed = True
                except Exception as exc:
                    _show_error("Save MO surface image", exc)
                finally:
                    save_in_progress = False

            plotter.add_key_event("s", save_current_view)
            plotter.add_key_event("S", save_current_view)
            add_pyvista_keypress_observer(plotter, "s", save_current_view)
            plotter.add_key_event("r", lambda: plotter.reset_camera())
            plotter.add_key_event("R", lambda: plotter.reset_camera())
            plotter.add_key_event("Escape", self._close_active_mo_plotter)
            try:
                bring_pyvista_window_to_front(plotter)
                plotter.show(title=f"{orbital['display_label']} MO #{orbital['mo_number']}", auto_close=False)
                bring_pyvista_window_to_front(plotter, delay_s=0.05)
            except TypeError:
                bring_pyvista_window_to_front(plotter)
                plotter.show(title=f"{orbital['display_label']} MO #{orbital['mo_number']}")
        except Exception as exc:
            _show_error("MO surface viewer", exc)
        finally:
            self.mo_viewer_opening = False
            if plotter is not None and plotter is self.active_mo_plotter:
                self._close_active_mo_plotter()

    def _restore_mo_visual_settings_for_orbital(self, orbital: Dict[str, Any], restore_style: bool = False) -> None:
        meta_orbital = self.mo_metadata.get("orbitals", {}).get(orbital["safe_label"], {})

        isovalue = orbital.get("isovalue", meta_orbital.get("isovalue"))
        if isovalue is not None:
            try:
                self.mo_isovalue_var.set(str(isovalue))
            except Exception:
                pass

        opacity = orbital.get("opacity", meta_orbital.get("opacity"))
        if opacity is not None:
            try:
                self.mo_opacity_var.set(float(opacity))
                self._on_mo_opacity_changed()
            except Exception:
                pass

        if restore_style:
            molecule_style = orbital.get("molecule_style", meta_orbital.get("molecule_style"))
            if molecule_style in MO_MOLECULE_STYLES:
                self.mo_molecule_style_var.set(str(molecule_style))

        color_scheme = orbital.get("color_scheme", meta_orbital.get("color_scheme"))
        if color_scheme in MO_COLOR_SCHEMES:
            self.mo_color_scheme_var.set(str(color_scheme))

    def _refresh_mo_metadata_from_disk(self) -> None:
        try:
            out_path = self._require_orca_out_for_surfaces()
            paths = mo_surface_paths(out_path)
            self.mo_metadata = load_mo_metadata(paths["metadata_file"])
        except Exception:
            pass

    def _camera_position_from_orbital_record(self, record: Any) -> Any:
        if not isinstance(record, dict):
            return None
        camera_position = record.get("camera_position")
        if camera_position is None:
            camera_position = camera_position_from_state(record.get("camera_state"))
        return camera_position

    def _saved_camera_position_for_orbital(self, orbital: Dict[str, Any]) -> Any:
        camera_position = self._camera_position_from_orbital_record(orbital)
        if camera_position is not None:
            orbital["camera_position"] = camera_position
            return camera_position

        self._refresh_mo_metadata_from_disk()
        meta_orbital = self.mo_metadata.get("orbitals", {}).get(orbital["safe_label"], {})
        camera_position = self._camera_position_from_orbital_record(meta_orbital)
        if camera_position is not None:
            orbital["camera_position"] = camera_position
            if isinstance(meta_orbital.get("camera_state"), dict):
                orbital["camera_state"] = meta_orbital["camera_state"]
            return camera_position

        raise ValueError(
            "No saved orientation is available for this MO tile.\n\n"
            "Open / Replace view first, orient the molecule, then press S to save that view."
        )

    def _saved_camera_state_for_orbital(self, orbital: Dict[str, Any], require: bool = True) -> Optional[Dict[str, Any]]:
        camera_state = orbital.get("camera_state")
        if isinstance(camera_state, dict):
            return camera_state
        camera_position = orbital.get("camera_position")
        if camera_position is not None:
            camera_state = {"camera_position": camera_position}
            orbital["camera_state"] = camera_state
            return camera_state

        self._refresh_mo_metadata_from_disk()
        meta_orbital = self.mo_metadata.get("orbitals", {}).get(orbital["safe_label"], {})
        camera_state = meta_orbital.get("camera_state")
        if isinstance(camera_state, dict):
            orbital["camera_state"] = camera_state
            if orbital.get("camera_position") is None:
                camera_position = camera_position_from_state(camera_state)
                if camera_position is not None:
                    orbital["camera_position"] = camera_position
            return camera_state
        camera_position = meta_orbital.get("camera_position")
        if camera_position is not None:
            camera_state = {"camera_position": camera_position}
            orbital["camera_position"] = camera_position
            orbital["camera_state"] = camera_state
            return camera_state

        if require:
            raise ValueError(
                "No saved zoom/scale is available for this MO tile.\n\n"
                "Open / Replace view first, orient and zoom the molecule, then press S to save that view."
            )
        return None

    def apply_mo_surface_view_to_all(self, source_orbital: Dict[str, Any]) -> None:
        try:
            if self.mo_batch_thread is not None and self.mo_batch_thread.is_alive():
                messagebox.showinfo("Use view for all", "MO surface rendering is already running.")
                return
            self._close_active_mo_plotter()
            self._refresh_mo_metadata_from_disk()
            camera_position = self._saved_camera_position_for_orbital(source_orbital)
            camera_state = self._saved_camera_state_for_orbital(source_orbital, require=False)
            if not self.mo_orbitals:
                raise ValueError("No MO surface tiles are available.")
            label = contact_sheet_orbital_label(source_orbital)
            count = len(self.mo_orbitals)
            preset, width, height = self._selected_image_resolution()
            isovalue, opacity = self._current_mo_visual_settings()
            render_options = {
                "preset": preset,
                "width": width,
                "height": height,
                "isovalue": isovalue,
                "opacity": opacity,
                "molecule_style": self.mo_molecule_style_var.get(),
                "color_scheme": self.mo_color_scheme_var.get(),
            }
            if not messagebox.askyesno(
                "Use view for all",
                f"Apply the saved orientation and zoom/scale from {label} to all {count} MO tiles in this contact sheet?\n\n"
                "This will overwrite the saved MO surface images for the current contact sheet.",
                parent=self.mo_contact_sheet if self.mo_contact_sheet is not None and self.mo_contact_sheet.winfo_exists() else self,
            ):
                return

            orbitals = list(self.mo_orbitals)
            self.mo_status_var.set(f"Rendering MO surfaces: 0/{count}")
            self.mo_batch_thread = threading.Thread(
                target=self._apply_mo_surface_view_to_all_worker,
                args=(orbitals, camera_position, camera_state, render_options),
                daemon=True,
            )
            self.mo_batch_thread.start()
        except Exception as exc:
            self.mo_status_var.set("Use view for all failed.")
            _show_error("Use view for all", exc)

    def _set_mo_status_from_worker(self, text: str) -> None:
        try:
            self.after(0, lambda: self.mo_status_var.set(text))
        except Exception:
            pass

    def _apply_mo_surface_view_to_all_worker(
        self,
        orbitals: List[Dict[str, Any]],
        camera_position: Any,
        camera_state: Optional[Dict[str, Any]],
        render_options: Dict[str, Any],
    ) -> None:
        count = len(orbitals)
        try:
            for index, orbital in enumerate(orbitals, start=1):
                label = contact_sheet_orbital_label(orbital)
                self._set_mo_status_from_worker(f"Rendering MO surface {index}/{count}: {label}")
                self.save_mo_surface_view(
                    orbital,
                    camera_position,
                    camera_state=camera_state,
                    refresh_contact_sheet=False,
                    render_options=render_options,
                )
            self.after(0, lambda: self._finish_apply_mo_surface_view_to_all(count, None))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._finish_apply_mo_surface_view_to_all(count, exc))

    def _finish_apply_mo_surface_view_to_all(self, count: int, exc: Optional[BaseException]) -> None:
        if exc is not None:
            self.mo_status_var.set("Use view for all failed.")
            _show_error("Use view for all", exc)
            return
        if self.mo_contact_sheet is not None and self.mo_contact_sheet.winfo_exists():
            self.mo_contact_sheet.refresh()
            self.mo_contact_sheet.lift()
        self.mo_status_var.set(f"Applied saved MO surface view to {count} tiles.")
        messagebox.showinfo("Use view for all", "The saved orientation was applied to all MO tiles.")

    def save_mo_surface_view(
        self,
        orbital: Dict[str, Any],
        camera_position: Any,
        live_image: Any = None,
        refresh_contact_sheet: bool = True,
        camera_state: Optional[Dict[str, Any]] = None,
        render_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        if Image is None:
            raise RuntimeError("Pillow is required to verify saved images and generate thumbnails.")
        render_options = dict(render_options or {})
        if {"preset", "width", "height", "isovalue", "opacity", "molecule_style", "color_scheme"}.issubset(render_options):
            preset = str(render_options["preset"])
            width = int(render_options["width"])
            height = int(render_options["height"])
            orbital["isovalue"] = float(render_options["isovalue"])
            orbital["opacity"] = float(render_options["opacity"])
            orbital["molecule_style"] = str(render_options["molecule_style"])
            orbital["color_scheme"] = str(render_options["color_scheme"])
        else:
            preset, width, height = self._selected_image_resolution()
            orbital["isovalue"], orbital["opacity"] = self._current_mo_visual_settings()
            orbital["molecule_style"] = self.mo_molecule_style_var.get()
            orbital["color_scheme"] = self.mo_color_scheme_var.get()
            render_options.update({
                "preset": preset,
                "width": width,
                "height": height,
                "isovalue": orbital["isovalue"],
                "opacity": orbital["opacity"],
                "molecule_style": orbital["molecule_style"],
                "color_scheme": orbital["color_scheme"],
            })
        plotter = self._build_orbital_plotter(orbital, off_screen=True, window_size=(width, height), render_options=render_options)
        apply_plotter_camera_state(plotter, camera_position, camera_state)
        image_path = Path(orbital["image_path"])
        thumb_path = Path(orbital["thumbnail_path"])
        try:
            for old_path in (image_path, thumb_path):
                try:
                    if old_path.exists():
                        old_path.unlink()
                except Exception:
                    pass
            img = pyvista_screenshot(plotter, str(image_path), window_size=(width, height), return_img=True)
        except Exception as exc:
            raise RuntimeError("High-resolution image saving failed. Try a smaller preset.") from exc
        finally:
            self._dispose_mo_plotter(plotter)
        if img is None or getattr(img, "size", 0) == 0:
            raise RuntimeError("Screenshot saving failed: blank image returned.")
        with Image.open(image_path) as opened:
            im = opened.convert("RGB")
        if im.size != (width, height):
            raise RuntimeError(f"Saved image has unexpected size {im.size}; expected {(width, height)}.")
        extrema = im.convert("L").getextrema()
        if extrema[0] == extrema[1]:
            raise RuntimeError("Screenshot appears blank; image was not marked as saved.")
        thumb = Image.fromarray(live_image).convert("RGB") if live_image is not None else im.copy()
        thumb.thumbnail(THUMBNAIL_SIZE)
        thumb.save(thumb_path)

        out_path = self._require_orca_out_for_surfaces()
        paths = ensure_mo_surface_dirs(out_path)
        meta = load_mo_metadata(paths["metadata_file"])
        meta.setdefault("orbitals", {})[orbital["safe_label"]] = {
            "safe_label": orbital["safe_label"],
            "display_label": orbital["display_label"],
            "orca_mo_number": orbital["mo_number"],
            "orbital_energy_ev": orbital.get("energy_ev"),
            "cube_path": orbital["cube_path"],
            "image_path": str(image_path),
            "thumbnail_path": str(thumb_path),
            "isovalue": orbital["isovalue"],
            "opacity": orbital["opacity"],
            "molecule_style": orbital["molecule_style"],
            "color_scheme": orbital["color_scheme"],
            "camera_position": camera_position_to_json(camera_position),
            "camera_state": camera_state or {"camera_position": camera_position_to_json(camera_position)},
            "saved_status": True,
            "last_saved_timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
            "resolution_preset": preset,
            "saved_image_width_px": width,
            "saved_image_height_px": height,
        }
        save_mo_metadata(paths["metadata_file"], meta)
        self.mo_metadata = meta
        orbital["image_path"] = str(image_path)
        orbital["thumbnail_path"] = str(thumb_path)
        orbital["camera_position"] = camera_position_to_json(camera_position)
        orbital["camera_state"] = camera_state or {"camera_position": camera_position_to_json(camera_position)}
        if refresh_contact_sheet:
            self.open_mo_contact_sheet()

    def clean_all_mo_surfaces(self) -> None:
        out_path = self._require_orca_out_for_surfaces()
        if self.mo_batch_thread is not None and self.mo_batch_thread.is_alive():
            messagebox.showinfo("Clean MO surfaces", "MO surface rendering is still running. Wait for it to finish, then clean again.")
            return

        paths = ensure_mo_surface_dirs(out_path)
        root = paths["root"].resolve()
        base = out_path.stem
        if not messagebox.askyesno(
            "Clean all MO surfaces",
            "Delete generated cube files, saved images, thumbnails, and MO surface metadata for the current ORCA output?\n\n"
            "The source .out and .gbw files will not be changed.",
            parent=self.mo_contact_sheet if self.mo_contact_sheet is not None and self.mo_contact_sheet.winfo_exists() else self,
        ):
            return

        self._close_active_mo_plotter()
        patterns = [
            (paths["cubes"], f"{base}_*.cube"),
            (paths["images"], f"{base}_*_view.png"),
            (paths["thumbnails"], f"{base}_*_thumb.png"),
            (paths["metadata"], f"{base}_MO_surfaces.json"),
            (paths["metadata"], f"{base}_*_orca_plot.log"),
        ]
        candidates: List[Path] = []
        seen: set[str] = set()
        for folder, pattern in patterns:
            for candidate in folder.glob(pattern):
                try:
                    resolved = candidate.resolve()
                except Exception:
                    continue
                if root != resolved and root not in resolved.parents:
                    continue
                key = str(resolved).lower()
                if key not in seen and candidate.is_file():
                    seen.add(key)
                    candidates.append(candidate)

        errors: List[str] = []
        deleted = 0
        for candidate in candidates:
            try:
                candidate.unlink()
                deleted += 1
            except Exception as exc:
                errors.append(f"{candidate.name}: {exc}")

        self.mo_metadata = {"orbitals": {}}
        self.mo_orbitals = []
        try:
            self._prepare_mo_orbitals()
        except Exception:
            pass
        if self.mo_contact_sheet is not None and self.mo_contact_sheet.winfo_exists():
            self.mo_contact_sheet.refresh()
        self.mo_status_var.set(f"Cleaned {deleted} MO surface file(s). Generate cubes to rebuild from scratch.")
        if errors:
            raise RuntimeError("Some files could not be deleted:\n" + "\n".join(errors))
        messagebox.showinfo("Clean MO surfaces", f"Cleaned {deleted} generated MO surface file(s).")

    def save_contact_sheet(self) -> None:
        out_path = self._require_orca_out_for_surfaces()
        paths = ensure_mo_surface_dirs(out_path)
        if not self.mo_orbitals:
            raise ValueError("No MO surface tiles are available.")
        selected = filedialog.asksaveasfilename(
            title="Save HOMO-LUMO contact sheet",
            initialdir=str(paths["root"]),
            initialfile=f"{out_path.stem}_HOMO_LUMO_contactsheet.png",
            defaultextension=".png",
            filetypes=[
                ("PNG image", "*.png"),
                ("Excel workbook", "*.xlsx"),
                ("OpenDocument spreadsheet", "*.ods"),
                ("All files", "*.*"),
            ],
            parent=self.mo_contact_sheet if self.mo_contact_sheet is not None and self.mo_contact_sheet.winfo_exists() else self,
        )
        if not selected:
            return
        output = Path(selected)
        suffix = output.suffix.lower()
        if suffix == ".png":
            self._write_contact_sheet_png(output)
        elif suffix == ".xlsx":
            self._write_contact_sheet_xlsx(output)
        elif suffix == ".ods":
            self._write_contact_sheet_ods(output)
        else:
            raise ValueError("Choose .png, .xlsx, or .ods.")
        messagebox.showinfo("Contact sheet saved", f"Saved:\n{output}")
        open_image_in_system_viewer(output)

    def _write_contact_sheet_png(self, output: Path) -> None:
        if Image is None or ImageDraw is None:
            raise RuntimeError("Pillow is required for contact-sheet image export.")
        if not self.mo_orbitals:
            raise ValueError("No MO surface tiles are available.")
        rows_by_kind = contact_sheet_rows(self.mo_orbitals)
        cols = max(1, max(len(row) for row in rows_by_kind))
        _preset, min_width, min_height = self._selected_image_resolution()
        base_tile_w, base_tile_h = 430, 430
        scale = max(
            1.0,
            min_width / max(1, cols * base_tile_w),
            min_height / max(1, 2 * base_tile_h),
        )
        tile_w = max(base_tile_w, int(math.ceil(base_tile_w * scale)))
        tile_h = max(base_tile_h, int(math.ceil(base_tile_h * scale)))
        header_h = max(58, int(math.ceil(58 * scale)))
        margin = max(5, int(math.ceil(5 * scale)))
        image_margin_x = max(35, int(math.ceil(35 * scale)))
        image_margin_y = max(105, int(math.ceil(105 * scale)))
        image_box = max(260, min(int(math.ceil(360 * scale)), tile_h - image_margin_y - margin * 3))
        text_y = max(12, int(math.ceil(12 * scale)))
        detail_y = max(72, int(math.ceil(72 * scale)))
        header_font = self._contact_sheet_font(max(20, int(round(24 * scale))), bold=True)
        detail_font = self._contact_sheet_font(max(18, int(round(22 * scale))), bold=False)
        sheet = Image.new("RGB", (cols * tile_w, 2 * tile_h), "white")
        draw = ImageDraw.Draw(sheet)
        for row, row_orbitals in enumerate(rows_by_kind):
            for col, orbital in enumerate(row_orbitals):
                x, y = col * tile_w, row * tile_h
                draw.rectangle([x + margin, y + margin, x + tile_w - margin, y + tile_h - margin], outline="#cbd5e1")
                text = contact_sheet_orbital_label(orbital)
                draw.rectangle([x + margin, y + margin, x + tile_w - margin, y + margin + header_h], fill=CONTACT_HEADER_BG, outline=CONTACT_HEADER_BG)
                try:
                    bbox = draw.textbbox((0, 0), text, font=header_font)
                    text_w = bbox[2] - bbox[0]
                except Exception:
                    text_w = int(len(text) * 7 * scale)
                draw.text((x + max(text_y, (tile_w - text_w) // 2), y + text_y), text, fill=CONTACT_HEADER_FG, font=header_font)
                if orbital.get("energy_ev") is not None:
                    draw.text((x + max(15, int(math.ceil(15 * scale))), y + detail_y), f"{orbital['energy_ev']:.4f} eV", fill="black", font=detail_font)
                image_path = Path(orbital.get("image_path") or "")
                thumb_path = Path(orbital.get("thumbnail_path") or "")
                source_path = image_path if image_path.is_file() else thumb_path
                if source_path.is_file():
                    img = Image.open(source_path).convert("RGB")
                    img.thumbnail((image_box, image_box))
                    paste_x = x + image_margin_x + max(0, (image_box - img.width) // 2)
                    paste_y = y + image_margin_y + max(0, (image_box - img.height) // 2)
                    sheet.paste(img, (paste_x, paste_y))
                else:
                    draw.rectangle([x + image_margin_x, y + image_margin_y, x + image_margin_x + image_box, y + image_margin_y + image_box], outline="#e2e8f0")
                    draw.text((x + max(140, int(math.ceil(140 * scale))), y + max(220, int(math.ceil(220 * scale)))), "No saved image", fill="#64748b", font=detail_font)
        sheet.save(output)

    def _contact_sheet_font(self, size: int, bold: bool = False) -> Any:
        if ImageFont is None:
            return None
        names = [
            "arialbd.ttf" if bold else "arial.ttf",
            "Arial Bold.ttf" if bold else "Arial.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
        for name in names:
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                pass
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def _write_contact_sheet_xlsx(self, output: Path) -> None:
        if Image is None:
            raise RuntimeError("Pillow is required for spreadsheet thumbnail export.")
        rows_by_kind = contact_sheet_rows(self.mo_orbitals)
        cols = max(1, max(len(row) for row in rows_by_kind))
        media: List[Tuple[int, Path]] = []
        image_cells: List[Tuple[int, int, int]] = []
        cell_rows: Dict[int, List[str]] = {}

        for row_idx, orbitals in enumerate(rows_by_kind):
            label_row = 1 + row_idx * 4
            detail_row = label_row + 1
            image_row = label_row + 2
            cell_rows.setdefault(label_row, [])
            cell_rows.setdefault(detail_row, [])
            for col_idx, orbital in enumerate(orbitals):
                label = contact_sheet_orbital_label(orbital)
                energy = orbital.get("energy_ev")
                detail = "" if energy is None else f"{energy:.4f} eV"
                cell_rows[label_row].append(xlsx_inline_cell(label_row, col_idx, label, style=1))
                cell_rows[detail_row].append(xlsx_inline_cell(detail_row, col_idx, detail, style=2))
                thumb_path = Path(orbital.get("thumbnail_path") or "")
                if thumb_path.is_file():
                    media.append((len(media) + 1, thumb_path))
                    image_cells.append((len(media), image_row - 1, col_idx))
                else:
                    cell_rows.setdefault(image_row, []).append(xlsx_inline_cell(image_row, col_idx, "No saved image", style=2))

        cols_xml = "".join(f'<col min="{i + 1}" max="{i + 1}" width="31" customWidth="1"/>' for i in range(cols))
        row_xml_parts: List[str] = []
        for row_num in range(1, 8):
            height = 205 if row_num in (3, 7) else 48
            cells = "".join(cell_rows.get(row_num, []))
            row_xml_parts.append(f'<row r="{row_num}" ht="{height}" customHeight="1">{cells}</row>')
        worksheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheetViews><sheetView workbookViewId="0" showGridLines="1"/></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols_xml}</cols>'
            f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
            '<drawing r:id="rId1"/>'
            '</worksheet>'
        )

        image_ext = 205 * 12700
        anchors = []
        drawing_rels = []
        for image_index, row_zero, col_zero in image_cells:
            rel_id = f"rId{image_index}"
            anchors.append(
                '<xdr:oneCellAnchor>'
                f'<xdr:from><xdr:col>{col_zero}</xdr:col><xdr:colOff>120000</xdr:colOff><xdr:row>{row_zero}</xdr:row><xdr:rowOff>120000</xdr:rowOff></xdr:from>'
                f'<xdr:ext cx="{image_ext}" cy="{image_ext}"/>'
                '<xdr:pic>'
                f'<xdr:nvPicPr><xdr:cNvPr id="{image_index}" name="MO thumbnail {image_index}"/><xdr:cNvPicPr/></xdr:nvPicPr>'
                f'<xdr:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
                '<xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
                '</xdr:pic><xdr:clientData/>'
                '</xdr:oneCellAnchor>'
            )
            drawing_rels.append(
                f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{image_index}.png"/>'
            )
        drawing_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'{"".join(anchors)}'
            '</xdr:wsDr>'
        )

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="26"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><sz val="20"/><color rgb="FF475569"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F2D44"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>'
        )

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MO contact sheet" sheetId="1" r:id="rId1"/></sheets></workbook>')
            zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
            zf.writestr("xl/styles.xml", styles_xml)
            zf.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
            zf.writestr("xl/worksheets/_rels/sheet1.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>')
            zf.writestr("xl/drawings/drawing1.xml", drawing_xml)
            zf.writestr("xl/drawings/_rels/drawing1.xml.rels", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(drawing_rels)}</Relationships>')
            for image_index, thumb_path in media:
                with Image.open(thumb_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail((400, 400))
                    from io import BytesIO
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    zf.writestr(f"xl/media/image{image_index}.png", buf.getvalue())

    def _write_contact_sheet_ods(self, output: Path) -> None:
        if Image is None:
            raise RuntimeError("Pillow is required for spreadsheet thumbnail export.")
        rows_by_kind = contact_sheet_rows(self.mo_orbitals)
        cols = max(1, max(len(row) for row in rows_by_kind))
        pictures: List[Tuple[str, bytes]] = []
        table_rows: List[str] = []

        def cell_text(text: str, style_name: str = "") -> str:
            style_attr = f' table:style-name="{style_name}"' if style_name else ""
            return f'<table:table-cell office:value-type="string"{style_attr}><text:p>{xml_escape(str(text))}</text:p></table:table-cell>'

        def empty_cells(count: int) -> str:
            return "".join('<table:table-cell/>' for _ in range(max(0, count)))

        for row_idx, orbitals in enumerate(rows_by_kind):
            label_cells: List[str] = []
            detail_cells: List[str] = []
            image_cells: List[str] = []
            for orbital in orbitals:
                label = contact_sheet_orbital_label(orbital)
                energy = orbital.get("energy_ev")
                detail = "" if energy is None else f"{energy:.4f} eV"
                label_cells.append(cell_text(label, "ceHeader"))
                detail_cells.append(cell_text(detail, "ceDetail"))
                thumb_path = Path(orbital.get("thumbnail_path") or "")
                if thumb_path.is_file():
                    image_name = f"Pictures/mo_{len(pictures) + 1}.png"
                    with Image.open(thumb_path) as img:
                        img = img.convert("RGB")
                        img.thumbnail((400, 400))
                        from io import BytesIO
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        pictures.append((image_name, buf.getvalue()))
                    image_cells.append(
                        '<table:table-cell office:value-type="string">'
                        '<draw:frame draw:style-name="gr1" draw:name="MO thumbnail" text:anchor-type="paragraph" svg:width="5.6cm" svg:height="5.6cm">'
                        f'<draw:image xlink:href="{xml_escape(image_name)}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/>'
                        '</draw:frame>'
                        '</table:table-cell>'
                    )
                else:
                    image_cells.append(cell_text("No saved image"))
            label_cells.append(empty_cells(cols - len(orbitals)))
            detail_cells.append(empty_cells(cols - len(orbitals)))
            image_cells.append(empty_cells(cols - len(orbitals)))
            table_rows.append(f'<table:table-row table:style-name="roText">{"".join(label_cells)}</table:table-row>')
            table_rows.append(f'<table:table-row table:style-name="roText">{"".join(detail_cells)}</table:table-row>')
            table_rows.append(f'<table:table-row table:style-name="roImage">{"".join(image_cells)}</table:table-row>')
            if row_idx == 0:
                table_rows.append(f'<table:table-row table:style-name="roGap">{empty_cells(cols)}</table:table-row>')

        columns = "".join('<table:table-column table:style-name="co1"/>' for _ in range(cols))
        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
            'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
            'office:version="1.2">'
            '<office:automatic-styles>'
            '<style:style style:name="co1" style:family="table-column"><style:table-column-properties style:column-width="6.2cm"/></style:style>'
            '<style:style style:name="roText" style:family="table-row"><style:table-row-properties style:row-height="1.1cm"/></style:style>'
            '<style:style style:name="roImage" style:family="table-row"><style:table-row-properties style:row-height="6.2cm"/></style:style>'
            '<style:style style:name="roGap" style:family="table-row"><style:table-row-properties style:row-height="0.35cm"/></style:style>'
            '<style:style style:name="ceHeader" style:family="table-cell"><style:table-cell-properties fo:background-color="#0f2d44"/><style:text-properties fo:color="#ffffff" fo:font-size="20pt" fo:font-weight="bold"/></style:style>'
            '<style:style style:name="ceDetail" style:family="table-cell"><style:text-properties fo:color="#475569" fo:font-size="18pt"/></style:style>'
            '<style:style style:name="gr1" style:family="graphic"><style:graphic-properties fo:clip="rect(0cm, 0cm, 0cm, 0cm)" draw:luminance="0%" draw:contrast="0%" draw:gamma="100%" draw:color-inversion="false"/></style:style>'
            '</office:automatic-styles>'
            '<office:body><office:spreadsheet>'
            f'<table:table table:name="MO contact sheet">{columns}{"".join(table_rows)}</table:table>'
            '</office:spreadsheet></office:body>'
            '</office:document-content>'
        )
        manifest_entries = [
            '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>',
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>',
        ]
        for name, _data in pictures:
            manifest_entries.append(f'<manifest:file-entry manifest:full-path="{xml_escape(name)}" manifest:media-type="image/png"/>')
        manifest_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
            f'{"".join(manifest_entries)}'
            '</manifest:manifest>'
        )

        with zipfile.ZipFile(output, "w") as zf:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.spreadsheet", compress_type=zipfile.ZIP_STORED)
            zf.writestr("content.xml", content_xml, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr("META-INF/manifest.xml", manifest_xml, compress_type=zipfile.ZIP_DEFLATED)
            for name, data in pictures:
                zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    # -------- Preview / Save --------
    def on_preview(self) -> None:
        try:
            self._ensure_file_loaded()
            if self.file_kind == "orca":
                energies, homo_i, msg = self._get_orca_inputs()
            elif self.file_kind == "gaussian":
                energies, homo_i, msg = self._get_gaussian_inputs()
            else:
                raise ValueError("Could not detect whether the file is ORCA or Gaussian.")

            fig, gap = make_figure(
                energies=energies,
                homo_i=homo_i,
                title=self.title_var.get(),
                label_min_sep_ev=self._get_label_sep(),
                show_energy_values=bool(self.show_energy_values_var.get()),
            )

            for w in self.preview_frame.winfo_children():
                w.destroy()

            self.current_fig = fig
            self.current_gap = gap

            self.canvas = FigureCanvasTkAgg(fig, master=self.preview_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill="both", expand=True)

            self.info.config(text=f"{msg}\nHOMO–LUMO gap = {gap:.3f} eV")
        except Exception as e:
            _show_error("Preview error", e)

    def on_save(self) -> None:
        try:
            if self.current_fig is None:
                self.on_preview()
                if self.current_fig is None:
                    return

            initialdir = None
            initialfile = "HOMO_LUMO_gap.png"
            if self.file_path:
                source_path = Path(self.file_path)
                initialdir = str(source_path.parent)
                parts = infer_calculation_filename_parts(self.file_path, self.file_kind)
                name_parts = [parts["project"], parts["method"]]
                if parts.get("solvent"):
                    name_parts.extend(["smd", parts["solvent"]])
                name_parts.append(parts["job"])
                initialfile = filename_token("_".join(name_parts), "HOMO_LUMO_gap") + ".png"

            path = filedialog.asksaveasfilename(
                title="Save figure",
                initialdir=initialdir,
                initialfile=initialfile,
                defaultextension=".png",
                filetypes=[("PNG image", "*.png"), ("SVG vector", "*.svg")],
            )
            if not path:
                return

            if path.lower().endswith(".png"):
                _preset, width, height = self._selected_image_resolution()
                fig_w, fig_h = self.current_fig.get_size_inches()
                dpi = max(width / max(fig_w, 1.0e-6), height / max(fig_h, 1.0e-6))
                self.current_fig.savefig(path, dpi=dpi, transparent=True)
                if Image is not None:
                    with Image.open(path) as img:
                        if img.size != (width, height):
                            fitted = Image.new("RGBA", (width, height), (255, 255, 255, 0))
                            work = img.convert("RGBA")
                            work.thumbnail((width, height), Image.LANCZOS)
                            x = max(0, (width - work.width) // 2)
                            y = max(0, (height - work.height) // 2)
                            fitted.paste(work, (x, y))
                            fitted.save(path)
            elif path.lower().endswith(".svg"):
                self.current_fig.savefig(path, bbox_inches="tight")
            else:
                raise ValueError("Choose .png or .svg.")

            open_image_in_system_viewer(Path(path))
            messagebox.showinfo("Saved", f"Saved:\n{path}")
        except Exception as e:
            _show_error("Save error", e)


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _show_error("Fatal error", e)
        # Do NOT re-raise: prevents the app from closing without explanation when double-clicked.
