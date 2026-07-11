"""TD-DFT input settings, ORCA output parsing, and UV-Vis analysis GUI.

This module is intentionally independent of the Builder's structure parsing and
general input machinery.  Only ``build_tddft_block`` is used during generation.
"""
from __future__ import annotations

import csv
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

TOOLS_ROOT = Path(__file__).resolve().parents[1]
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from app_identity import configure_tk_window_identity, set_windows_app_id

from td_dft_cube_viewer import SignedCubeViewer
from td_dft_multiwfn_runner import MultiwfnTDDFTRunner

HC_EV_NM = 1239.841984
MODULE_SETTINGS = Path(__file__).with_name("td_dft_settings.json")
ASSOCIATED_SUFFIXES = (".gbw", ".molden.input", ".molden", ".wfn", ".wfx", ".fchk")
TD_DFT_ICON_PATH = TOOLS_ROOT / "images" / "tr_orca_icon.png"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
CONTACT_EMAIL = "torubaev(at)gmail.com"
LINKEDIN_URL = "https://www.linkedin.com/in/torubaev/"
README_LINK_TEXT = "README section: TD-DFT / UV-Vis"
CITATION_REFERENCE = (
    "Torubaev, Y. CrystEngKit-ORCA: practical GUI tools for ORCA and "
    "Multiwfn calculations in supramolecular chemistry and crystal engineering, "
    "version 1.0; GitHub, 2026. https://github.com/torubaev/crystengkit-orca-v1.0"
)
CITATION_TEXT = f"Cite as: {CITATION_REFERENCE}"
ABOUT_PURPOSE = (
    "Builds validated ORCA TD-DFT/TDA blocks, reads excited-state output, "
    "plots UV-Vis spectra, and manages state-resolved visualization data."
)

DEFAULT_TDDFT_SETTINGS = {
    "vertical_excitation": True,
    "excited_state_optimization": False,
    "excited_state_frequencies": False,
    "td_method": "TDDFT",
    "nroots": 20,
    "root": 1,
    "manifold": "Singlets",
    "target_manifold": "Singlet",
    "print_ntos": False,
    "difference_density": False,
    "transition_density": False,
    "excited_state_density": False,
    "broadening_ev": 0.20,
    "wavelength_min_nm": 200.0,
    "wavelength_max_nm": 800.0,
    "x_axis": "nm",
    "normalize": False,
}


def configure_builder_ui_style(widget: tk.Misc) -> None:
    """Apply the shared CrystEngKit tool palette and widget styling."""
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
    style.configure(
        "Blue.Horizontal.TProgressbar",
        troughcolor="#dbeafe",
        background="#2563eb",
        lightcolor="#3b82f6",
        darkcolor="#1d4ed8",
        bordercolor="#93c5fd",
        thickness=14,
    )


def load_header_icon(path: Path, max_size: int = 56) -> Optional[tk.PhotoImage]:
    if not path.is_file():
        return None
    image = tk.PhotoImage(file=str(path))
    factor = max(1, int(max(image.width() / max_size, image.height() / max_size) + 0.999))
    return image.subsample(factor, factor) if factor > 1 else image


def bind_mousewheel_to_canvas(canvas: tk.Canvas) -> None:
    def pointer_is_over_canvas() -> bool:
        try:
            x, y = canvas.winfo_pointerx(), canvas.winfo_pointery()
            left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
            return left <= x < left + canvas.winfo_width() and top <= y < top + canvas.winfo_height()
        except tk.TclError:
            return False

    def on_mousewheel(event):
        if not pointer_is_over_canvas():
            return None
        try:
            first, last = canvas.yview()
            if first <= 0.0 and last >= 1.0:
                return None
        except tk.TclError:
            return None
        delta = getattr(event, "delta", 0)
        units = (-int(delta / 120) * 5) if abs(delta) >= 120 else (-5 if delta > 0 else 5)
        if getattr(event, "num", None) == 4: units = -5
        if getattr(event, "num", None) == 5: units = 5
        canvas.yview_scroll(units, "units")
        return "break"

    canvas.bind_all("<MouseWheel>", on_mousewheel, add="+")
    canvas.bind_all("<Button-4>", on_mousewheel, add="+")
    canvas.bind_all("<Button-5>", on_mousewheel, add="+")


def validate_tddft_settings(settings: Dict) -> Dict:
    data = dict(DEFAULT_TDDFT_SETTINGS)
    data.update(settings or {})
    # Read settings saved by the former single-choice calculation dropdown.
    legacy_calculation = (settings or {}).get("calculation_type")
    if legacy_calculation and not any(
        key in (settings or {})
        for key in ("vertical_excitation", "excited_state_optimization", "excited_state_frequencies")
    ):
        data["vertical_excitation"] = True
        data["excited_state_optimization"] = legacy_calculation == "Excited-state optimization"
        data["excited_state_frequencies"] = legacy_calculation == "Excited-state frequencies"
    data["nroots"] = int(data["nroots"])
    data["root"] = int(data["root"])
    data["broadening_ev"] = float(data["broadening_ev"])
    data["wavelength_min_nm"] = float(data["wavelength_min_nm"])
    data["wavelength_max_nm"] = float(data["wavelength_max_nm"])
    if data["nroots"] < 1 or data["root"] < 1:
        raise ValueError("NROOTS and ROOT must be positive integers.")
    if data["root"] > data["nroots"]:
        raise ValueError("ROOT cannot be greater than NROOTS.")
    if data["broadening_ev"] <= 0:
        raise ValueError("Gaussian broadening must be greater than zero.")
    if data["wavelength_min_nm"] <= 0 or data["wavelength_max_nm"] <= data["wavelength_min_nm"]:
        raise ValueError("The wavelength range must be positive and increasing.")
    if data["td_method"] not in {"TDDFT", "TDA"}:
        raise ValueError("TD method must be TDDFT or TDA.")
    if data["manifold"] not in {"Singlets", "Triplets", "Both"}:
        raise ValueError("Unknown excited-state manifold.")
    if data["target_manifold"] not in {"Singlet", "Triplet"}:
        raise ValueError("Target-state manifold must be Singlet or Triplet.")
    selected = [
        bool(data["vertical_excitation"]),
        bool(data["excited_state_optimization"]),
        bool(data["excited_state_frequencies"]),
    ]
    if not any(selected):
        raise ValueError("Select at least one TD-DFT calculation.")
    if data["excited_state_frequencies"] and not data["excited_state_optimization"]:
        raise ValueError("Excited-state frequencies require excited-state optimization.")
    if data["excited_state_optimization"] and not data["vertical_excitation"]:
        raise ValueError("Excited-state optimization requires vertical excitation.")
    if data["manifold"] == "Singlets":
        data["target_manifold"] = "Singlet"
    elif data["manifold"] == "Triplets":
        data["target_manifold"] = "Triplet"
    return data


def build_tddft_block(settings: Dict) -> str:
    """Return a conservative ORCA 6 ``%tddft`` block.

    Vertical singlet/triplet controls and TDA are established ORCA controls.
    NTO and density requests are not emitted because the corresponding ORCA 6
    syntax has not yet been verified against the project-supported manual.
    """
    data = validate_tddft_settings(settings)
    lines = ["%tddft", f"  NRoots {data['nroots']}", f"  TDA {'true' if data['td_method'] == 'TDA' else 'false'}"]
    if data["manifold"] == "Singlets":
        lines += ["  Singlets true", "  Triplets false"]
    elif data["manifold"] == "Triplets":
        lines += ["  Singlets false", "  Triplets true"]
    else:
        lines += ["  Singlets true", "  Triplets true"]
    if data["excited_state_optimization"] or data["excited_state_frequencies"]:
        lines.append(f"  IRoot {data['root']}")
        lines.append(f"  IRootMult {data['target_manifold'].lower()}")
    # TODO(ORCA-6-manual): add NTO/difference/transition/excited-density output
    # controls only after their exact version-supported keywords are verified.
    lines.append("end")
    return "\n".join(lines)


def _state_label(index: int, multiplicity: str = "S") -> str:
    return f"{multiplicity}{index}"


def parse_orca_tddft_output(out_path: str) -> List[Dict]:
    text = Path(out_path).read_text(encoding="utf-8", errors="replace")
    states: Dict[int, Dict] = {}
    state_re = re.compile(
        r"^\s*STATE\s+(\d+)\s*:\s*E\s*=.*?([+-]?\d+(?:\.\d+)?)\s*eV(?:\s+([+-]?\d+(?:\.\d+)?)\s*nm)?",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in state_re.finditer(text):
        idx = int(match.group(1))
        energy = float(match.group(2))
        wavelength = float(match.group(3)) if match.group(3) else HC_EV_NM / energy
        tail = text[match.end(): text.find("\n", match.end()) if text.find("\n", match.end()) >= 0 else None]
        fmatch = re.search(r"f(?:osc)?\s*=\s*([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)", tail, re.I)
        states[idx] = {
            "state": _state_label(idx), "state_index": idx, "energy_ev": energy,
            "wavelength_nm": wavelength, "oscillator_strength": float(fmatch.group(1)) if fmatch else 0.0,
            "transitions": [],
        }

    # ORCA absorption table: state, energy(cm-1), wavelength(nm), fosc, ...
    in_absorption = False
    for line in text.splitlines():
        upper = line.upper()
        if "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS" in upper:
            in_absorption = True
            continue
        if in_absorption and (not line.strip() or set(line.strip()) <= {"-"}):
            continue
        if in_absorption:
            match = re.match(r"^\s*(\d+)\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)", line)
            if match:
                idx, wavenumber, wavelength, fosc = int(match.group(1)), float(match.group(2)), float(match.group(3)), float(match.group(4))
                state = states.setdefault(idx, {"state": _state_label(idx), "state_index": idx, "transitions": []})
                state.update({"energy_ev": wavenumber / 8065.544, "wavelength_nm": wavelength, "oscillator_strength": fosc})
            elif "CD SPECTRUM" in upper or "ABSORPTION SPECTRUM" in upper or "TRANSIENT" in upper:
                in_absorption = False

    ordered_matches = list(state_re.finditer(text))
    transition_re = re.compile(
        r"^\s*(\d+[ab]?)\s*[-=]+>\s*(\d+[ab]?)\s*[:=]\s*([+-]?\d+(?:\.\d+)?)([^\n]*)",
        re.IGNORECASE | re.MULTILINE,
    )
    for pos, smatch in enumerate(ordered_matches):
        idx = int(smatch.group(1))
        end = ordered_matches[pos + 1].start() if pos + 1 < len(ordered_matches) else min(len(text), smatch.end() + 5000)
        for match in transition_re.finditer(text, smatch.end(), end):
            coefficient = float(match.group(3))
            percent_match = re.search(r"(?:percent|contribution)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)\s*%?", match.group(4), re.I)
            printed = float(percent_match.group(1)) if percent_match else None
            states[idx]["transitions"].append({
                "from": match.group(1), "to": match.group(2), "coefficient": coefficient,
                "contribution_percent": printed if printed is not None else coefficient * coefficient * 100.0,
                "contribution_source": "printed" if printed is not None else "calculated_from_coefficient_squared",
            })
    result = [state for _, state in sorted(states.items()) if state.get("energy_ev", 0) > 0]
    if not result:
        raise ValueError("No ORCA TD-DFT excited states were found in this output.")
    return result


def build_stick_spectrum(states: Sequence[Dict], x_axis: str = "nm") -> List[Tuple[float, float]]:
    key = "wavelength_nm" if x_axis.lower() == "nm" else "energy_ev"
    return sorted((float(s[key]), float(s.get("oscillator_strength", 0.0))) for s in states)


def build_gaussian_broadened_spectrum(states: Sequence[Dict], broadening_ev: float = 0.20,
                                        x_min_nm: float = 200.0, x_max_nm: float = 800.0,
                                        x_axis: str = "nm", points: int = 2000) -> List[Tuple[float, float]]:
    if broadening_ev <= 0 or x_min_nm <= 0 or x_max_nm <= x_min_nm or points < 2:
        raise ValueError("Invalid spectrum range, broadening, or point count.")
    e_low, e_high = HC_EV_NM / x_max_nm, HC_EV_NM / x_min_nm
    energies = [e_low + (e_high - e_low) * i / (points - 1) for i in range(points)]
    sigma = broadening_ev / (2.0 * math.sqrt(2.0 * math.log(2.0)))  # broadening is FWHM
    values = []
    for energy in energies:
        intensity = sum(float(s.get("oscillator_strength", 0.0)) * math.exp(-0.5 * ((energy - float(s["energy_ev"])) / sigma) ** 2) for s in states)
        values.append(intensity)
    pairs = list(zip(energies, values))
    if x_axis.lower() == "nm":
        pairs = sorted((HC_EV_NM / energy, intensity) for energy, intensity in pairs)
    return pairs


def export_spectrum_csv(path: str, sticks, broadened, x_axis: str = "nm") -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([f"stick_{x_axis}", "oscillator_strength"])
        writer.writerows(sticks)
        writer.writerow([])
        writer.writerow([f"broadened_{x_axis}", "intensity"])
        writer.writerows(broadened)


def normalize_spectrum(points):
    maximum = max((value for _, value in points), default=0.0)
    return [(x, value / maximum) for x, value in points] if maximum > 0 else list(points)


def save_spectrum(path: str, states: Sequence[Dict], settings: Dict) -> None:
    import matplotlib.pyplot as plt
    data = validate_tddft_settings(settings)
    axis = data["x_axis"]
    sticks = build_stick_spectrum(states, axis)
    curve = build_gaussian_broadened_spectrum(states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], axis)
    if data["normalize"]: curve = normalize_spectrum(curve)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.vlines([x for x, _ in sticks], 0, [y for _, y in sticks], color="#6b7280", linewidth=1, label="Sticks")
    ax.plot([x for x, _ in curve], [y for _, y in curve], color="#1d4ed8", linewidth=2, label="Gaussian broadened")
    ax.set_xlabel("Wavelength / nm" if axis == "nm" else "Energy / eV")
    ax.set_ylabel("Oscillator strength / relative intensity")
    ax.legend(); fig.tight_layout(); fig.savefig(path, dpi=220); plt.close(fig)


def detect_associated_files(output_path: str) -> Dict[str, str]:
    output = Path(output_path).resolve(); result = {}
    for suffix in ASSOCIATED_SUFFIXES:
        exact = output.with_name(output.stem + suffix)
        candidates = [exact] if exact.is_file() else sorted(output.parent.glob("*" + suffix), key=lambda p: (p.stem != output.stem, p.name.lower()))
        if candidates:
            result[suffix] = str(candidates[0].resolve())
    return result


def load_saved_multiwfn_path() -> str:
    candidates = [MODULE_SETTINGS, Path(__file__).with_name("orca_gaussian_builder_settings.json"), Path(__file__).resolve().parents[2] / "orca_gaussian_builder_settings.json"]
    for config in candidates:
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            for key in ("multiwfn_path", "multiwfn_executable", "Multiwfnpath"):
                value = str(data.get(key, "")).strip()
                if value: return value
        except Exception:
            pass
    env_value = os.environ.get("Multiwfnpath", "").strip()
    if env_value:
        env_path = Path(env_value).expanduser()
        if env_path.is_dir():
            for name in ("Multiwfn.exe", "Multiwfn", "multiwfn"):
                if (env_path / name).is_file(): return str(env_path / name)
        return env_value
    return ""


class TDDFTWindow(tk.Toplevel):
    def __init__(self, parent, settings: Dict, on_apply=None, on_close=None, builder_context=None):
        super().__init__(parent)
        configure_tk_window_identity(self, "TDDFT")
        self.title("TD-DFT setup, analysis, and visualization")
        screen_width = max(1, int(self.winfo_screenwidth()))
        screen_height = max(1, int(self.winfo_screenheight()))
        window_width = max(1, int(screen_width * 0.50))
        window_height = max(1, int(screen_height * 0.85))
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.minsize(min(640, window_width), min(560, window_height))
        configure_builder_ui_style(self)
        self.on_apply, self.on_close, self.states, self.output_path = on_apply, on_close, [], ""
        self.builder_enabled = bool(on_apply)
        self.ui_mode = "input"
        self.connection_status_var = tk.StringVar(value="Connected to ORCA Input Builder" if on_apply else "Standalone mode - no ORCA Builder connected")
        self.builder_context_var = tk.StringVar(value="")
        self.set_builder_context(builder_context or {})
        self.associated_files, self.analysis_result = {}, {}
        self.multiwfn_var = tk.StringVar(value=load_saved_multiwfn_path())
        self.progress_var = tk.IntVar(value=0)
        self.progress_text = tk.StringVar(value="0%")
        self.associated_summary_var = tk.StringVar(value="Load an ORCA .out file to detect associated files.")
        self.workdir_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value="UV-Vis spectrum")
        self.orbital_iso_var = tk.StringVar(value="0.03"); self.density_iso_var = tk.StringVar(value="0.001")
        self.positive_iso_var = tk.StringVar(value="0.001"); self.negative_iso_var = tk.StringVar(value="0.001")
        self.opacity_var = tk.StringVar(value="0.65")
        self.show_molecule_var = tk.BooleanVar(value=True); self.show_bonds_var = tk.BooleanVar(value=True); self.show_labels_var = tk.BooleanVar(value=False)
        initial = dict(DEFAULT_TDDFT_SETTINGS); initial.update(settings or {})
        self.vars = {key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))) for key, value in initial.items()}
        self.vertical_excitation_var = self.vars["vertical_excitation"]
        self.excited_state_opt_var = self.vars["excited_state_optimization"]
        self.excited_state_freq_var = self.vars["excited_state_frequencies"]
        self.workflow_summary_var = tk.StringVar()
        for variable in (self.vertical_excitation_var, self.excited_state_opt_var, self.excited_state_freq_var):
            variable.trace_add("write", lambda *_args: self._sync_calculation_dependencies())
        for key in ("nroots", "root", "td_method", "manifold"):
            self.vars[key].trace_add("write", lambda *_args: self._sync_calculation_dependencies())
        self._build()
        self._sync_calculation_dependencies()
        for variable in self.vars.values():
            variable.trace_add("write", lambda *_args: self._mark_tddft_modified())
        self.protocol("WM_DELETE_WINDOW", self._close_window)

    def _build(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(14, 10))
        header.pack(fill="x")
        self.header_icon = load_header_icon(TD_DFT_ICON_PATH)
        if self.header_icon is not None:
            tk.Label(header, image=self.header_icon, bg="#1e3a5f", bd=0, highlightthickness=0).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
        ttk.Label(header, text="TD-DFT", style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="Excited-State Setup, Analysis and Visualization", style="HeaderSub.TLabel").grid(row=1, column=1, sticky="w")
        header.columnconfigure(2, weight=1)
        about_link = ttk.Label(header, text="About", style="HeaderLink.TLabel", cursor="hand2")
        about_link.grid(row=0, column=3, rowspan=2, sticky="e")
        about_link.bind("<Button-1>", lambda _event: self.open_about_window())

        mode_bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8, 10, 0))
        mode_bar.pack(fill="x")
        self.input_mode_button = tk.Button(mode_bar, text="Input", command=lambda: self._set_ui_mode("input"), relief="solid", borderwidth=1, padx=18, pady=5, cursor="hand2", font=("Segoe UI", 9, "bold"))
        self.input_mode_button.pack(side="left")
        self.post_mode_button = tk.Button(mode_bar, text="Post-processing", command=lambda: self._set_ui_mode("post"), relief="solid", borderwidth=1, padx=18, pady=5, cursor="hand2", font=("Segoe UI", 9, "bold"))
        self.post_mode_button.pack(side="left", padx=(4, 0))

        body = ttk.Frame(self, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body_canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0, bg="#f4f6f9")
        body_scroll = ttk.Scrollbar(body, orient="vertical", command=body_canvas.yview)
        body_canvas.configure(yscrollcommand=body_scroll.set)
        body_canvas.grid(row=0, column=0, sticky="nsew")
        body_scroll.grid(row=0, column=1, sticky="ns")
        root = ttk.Frame(body_canvas, style="Panel.TFrame", padding=10)
        root_window = body_canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind("<Configure>", lambda _event: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_canvas.bind("<Configure>", lambda event: body_canvas.itemconfigure(root_window, width=event.width))
        bind_mousewheel_to_canvas(body_canvas)
        self.body_canvas = body_canvas
        root.columnconfigure(0, weight=1)
        connection_box = ttk.LabelFrame(root, text="Builder connection", padding=8); connection_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(connection_box, textvariable=self.connection_status_var).pack(anchor="w")
        ttk.Label(connection_box, textvariable=self.builder_context_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        setup = ttk.LabelFrame(root, text="TD-DFT input settings", padding=10); setup.grid(row=1, column=0, sticky="ew")
        setup.columnconfigure(0, weight=1, uniform="setup")
        setup.columnconfigure(1, weight=1, uniform="setup")
        calculation_box = ttk.Frame(setup); calculation_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(calculation_box, text="Calculation steps", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 3))
        ttk.Checkbutton(calculation_box, text="Vertical excitation", variable=self.vertical_excitation_var).pack(anchor="w")
        ttk.Checkbutton(calculation_box, text="Excited-state optimization", variable=self.excited_state_opt_var).pack(anchor="w")
        ttk.Checkbutton(calculation_box, text="Excited-state frequencies", variable=self.excited_state_freq_var).pack(anchor="w")
        ttk.Label(
            calculation_box,
            text="Optimization uses the selected target root; frequencies run after the optimized excited-state geometry.",
            foreground="#53627a",
            wraplength=255,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))
        parameters = ttk.Frame(setup); parameters.grid(row=0, column=1, sticky="nsew")
        parameters.columnconfigure(1, weight=1)
        ttk.Label(parameters, text="Excited-state parameters", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))
        for row, (label, key, values) in enumerate([("Method", "td_method", ["TDDFT", "TDA"]), ("Manifold", "manifold", ["Singlets", "Triplets", "Both"])], start=1):
            ttk.Label(parameters, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            ttk.Combobox(parameters, textvariable=self.vars[key], values=values, state="readonly", width=14).grid(row=row, column=1, sticky="ew", pady=2)
        ttk.Label(parameters, text="Number of roots").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(parameters, textvariable=self.vars["nroots"], width=10).grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(parameters, text="Target root").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(parameters, textvariable=self.vars["root"], width=10).grid(row=4, column=1, sticky="ew", pady=2)
        ttk.Label(parameters, text="Target state").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=2)
        self.target_manifold_combo = ttk.Combobox(parameters, textvariable=self.vars["target_manifold"], values=["Singlet", "Triplet"], state="readonly", width=14)
        self.target_manifold_combo.grid(row=5, column=1, sticky="ew", pady=2)
        ttk.Separator(setup, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        ttk.Label(setup, textvariable=self.workflow_summary_var, justify="left").grid(row=2, column=0, sticky="w")
        apply_box = ttk.Frame(setup); apply_box.grid(row=2, column=1, sticky="e")
        ttk.Label(apply_box, text="NTO/density keywords: post-processing only", style="Muted.TLabel").pack(anchor="e", pady=(0, 3))
        ttk.Button(apply_box, text="Show ORCA Block", command=self._apply, style="Primary.TButton").pack(anchor="e")

        spectrum = ttk.LabelFrame(root, text="Spectrum options", padding=10); spectrum.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        spectrum.columnconfigure(0, weight=1); spectrum.columnconfigure(1, weight=1); spectrum.columnconfigure(2, weight=1); spectrum.columnconfigure(3, weight=1)
        for column, (label, key, kind) in enumerate([("Broadening (eV)", "broadening_ev", "entry"), ("Range (nm)", "wavelength_min_nm", "range"), ("X axis", "x_axis", "combo"), ("Scale", "normalize", "check")]):
            cell = ttk.Frame(spectrum); cell.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            ttk.Label(cell, text=label, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 3))
            if kind == "entry": ttk.Entry(cell, textvariable=self.vars[key], width=10).pack(fill="x")
            elif kind == "range":
                range_box = ttk.Frame(cell); range_box.pack(fill="x")
                ttk.Entry(range_box, textvariable=self.vars["wavelength_min_nm"], width=6).pack(side="left", fill="x", expand=True)
                ttk.Label(range_box, text="–").pack(side="left", padx=3)
                ttk.Entry(range_box, textvariable=self.vars["wavelength_max_nm"], width=6).pack(side="left", fill="x", expand=True)
            elif kind == "combo": ttk.Combobox(cell, textvariable=self.vars[key], values=["nm", "eV"], state="readonly", width=7).pack(fill="x")
            else: ttk.Checkbutton(cell, text="Normalize", variable=self.vars[key]).pack(anchor="w")
        progress_frame = ttk.Frame(root, style="Panel.TFrame")
        progress_frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate", maximum=100, variable=self.progress_var, style="Blue.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.progress_text, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        tablebox = ttk.LabelFrame(root, text="ORCA TD-DFT states", padding=8); tablebox.grid(row=4, column=0, sticky="nsew"); tablebox.columnconfigure(0, weight=1); tablebox.rowconfigure(1, weight=1)
        actions = ttk.Frame(tablebox); actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        result_actions = [("Load ORCA output", self._load), ("Plot UV-Vis", self._plot), ("Export states CSV", self._export_table), ("Export spectrum CSV", self._export_spectrum), ("Save PNG", lambda: self._save_plot(".png")), ("Save SVG", lambda: self._save_plot(".svg"))]
        for index, (text, command) in enumerate(result_actions):
            ttk.Button(actions, text=text, command=command, style="Primary.TButton" if index == 0 else "TButton").grid(row=index // 3, column=index % 3, sticky="ew", padx=(0 if index % 3 == 0 else 5, 0), pady=(0, 5))
        for column in range(3): actions.columnconfigure(column, weight=1)
        columns = ("state", "ev", "nm", "f", "transition", "percent"); self.tree = ttk.Treeview(tablebox, columns=columns, show="headings")
        for key, label, width in zip(columns, ["State", "Energy / eV", "Wavelength / nm", "f", "Main transition", "Contribution / %"], [52, 82, 105, 68, 158, 105]): self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=48, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tablebox, orient="horizontal", command=self.tree.xview); tree_scroll.grid(row=2, column=0, sticky="ew"); self.tree.configure(xscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_mode_availability())

        viz = ttk.LabelFrame(root, text="Analysis and visualization", padding=8); viz.grid(row=5, column=0, sticky="ew"); viz.columnconfigure(0, weight=1)
        context = ttk.LabelFrame(viz, text="Files and executable", padding=8); context.grid(row=0, column=0, sticky="ew"); context.columnconfigure(1, weight=1)
        ttk.Label(context, text="ORCA output").grid(row=0, column=0, sticky="nw", padx=(0, 8)); self.output_label = ttk.Label(context, text="Not loaded", wraplength=430, justify="left"); self.output_label.grid(row=0, column=1, sticky="w")
        ttk.Label(context, text="Working directory").grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(3, 0)); ttk.Label(context, textvariable=self.workdir_var, wraplength=430, justify="left").grid(row=1, column=1, sticky="w", pady=(3, 0))
        ttk.Label(context, text="Associated files").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=(3, 0)); ttk.Label(context, textvariable=self.associated_summary_var, wraplength=430, justify="left").grid(row=2, column=1, sticky="w", pady=(3, 0))
        file_buttons = ttk.Frame(context); file_buttons.grid(row=3, column=1, sticky="w", pady=(5, 0))
        ttk.Button(file_buttons, text="Refresh files", command=lambda: self._guard("Associated files", self._detect_files)).pack(side="left", padx=(0, 6)); ttk.Button(file_buttons, text="Replace wavefunction...", command=self._replace_wavefunction).pack(side="left")
        ttk.Separator(context, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=7)
        ttk.Label(context, text="Multiwfn").grid(row=5, column=0, sticky="w", padx=(0, 8)); ttk.Entry(context, textvariable=self.multiwfn_var).grid(row=5, column=1, sticky="ew")
        multiwfn_buttons = ttk.Frame(context); multiwfn_buttons.grid(row=6, column=1, sticky="w", pady=(5, 0))
        ttk.Button(multiwfn_buttons, text="Browse...", command=self._browse_multiwfn).pack(side="left", padx=(0, 6)); ttk.Button(multiwfn_buttons, text="Validate", command=lambda: self._guard("Multiwfn", self._validate_multiwfn)).pack(side="left")

        analysis = ttk.LabelFrame(viz, text="Selected-state analysis", padding=8); analysis.grid(row=1, column=0, sticky="ew", pady=(8, 0)); analysis.columnconfigure(0, weight=1)
        buttons = ttk.Frame(analysis); buttons.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.generate_button = ttk.Button(buttons, text="Generate all analyses", command=lambda: self._start_analysis(False), style="Primary.TButton"); self.generate_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Regenerate package", command=lambda: self._start_analysis(True)).grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Open directory", command=self._open_analysis_directory).grid(row=0, column=2, sticky="ew")
        for column in range(3): buttons.columnconfigure(column, weight=1)
        status_columns = ("analysis", "status"); self.status_tree = ttk.Treeview(analysis, columns=status_columns, show="headings", height=5)
        self.status_tree.heading("analysis", text="Analysis"); self.status_tree.heading("status", text="Status"); self.status_tree.column("analysis", width=190); self.status_tree.column("status", width=330)
        self.status_tree.grid(row=1, column=0, sticky="ew")
        for name in ["UV-Vis spectrum", "NTO hole/electron", "Difference density", "Transition density", "Attachment/detachment", "Hole/electron density", "Hole-electron descriptors"]: self.status_tree.insert("", "end", iid=name, values=(name, "Not started"))

        display = ttk.LabelFrame(viz, text="Display settings", padding=8); display.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        modes = ["UV-Vis spectrum", "NTO hole", "NTO electron", "NTO pair", "Difference density", "Transition density", "Attachment density", "Detachment density", "Attachment/detachment overlay", "Hole density", "Electron density", "Hole/electron overlay"]
        ttk.Label(display, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 8)); ttk.Combobox(display, textvariable=self.mode_var, values=modes, state="readonly").grid(row=0, column=1, columnspan=4, sticky="ew")
        display.columnconfigure(1, weight=1); display.columnconfigure(2, weight=1); display.columnconfigure(3, weight=1); display.columnconfigure(4, weight=1)
        value_row = ttk.Frame(display); value_row.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(7, 0))
        value_items = [("Orbital iso", self.orbital_iso_var), ("Density iso", self.density_iso_var), ("Positive iso", self.positive_iso_var), ("Negative iso", self.negative_iso_var), ("Opacity", self.opacity_var)]
        for column, (label, variable) in enumerate(value_items):
            cell = ttk.Frame(value_row); cell.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0)); value_row.columnconfigure(column, weight=1)
            ttk.Label(cell, text=label).pack(anchor="w"); ttk.Entry(cell, textvariable=variable, width=8).pack(fill="x")
        visibility = ttk.Frame(display); visibility.grid(row=2, column=0, columnspan=5, sticky="w", pady=(7, 0))
        ttk.Checkbutton(visibility, text="Molecule", variable=self.show_molecule_var).pack(side="left"); ttk.Checkbutton(visibility, text="Bonds", variable=self.show_bonds_var).pack(side="left", padx=(10, 0)); ttk.Checkbutton(visibility, text="Atom labels", variable=self.show_labels_var).pack(side="left", padx=(10, 0))
        display_actions = ttk.Frame(display); display_actions.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(7, 0))
        for column, (text, command) in enumerate([("Display", self._display_mode), ("Reset camera", self._display_mode), ("Save screenshot", self._save_screenshot), ("Export cubes", self._export_cubes)]):
            ttk.Button(display_actions, text=text, command=command, style="Primary.TButton" if column == 0 else "TButton").grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0)); display_actions.columnconfigure(column, weight=1)

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 6))
        footer.pack(fill="x")
        ttk.Label(footer, text=COPYRIGHT_NOTE, style="Muted.TLabel").pack(anchor="w")
        self.input_sections = (connection_box, setup)
        self.post_sections = (spectrum, progress_frame, tablebox, viz)
        self._set_ui_mode("input")

    def _set_ui_mode(self, mode: str) -> None:
        if mode not in {"input", "post"}:
            return
        self.ui_mode = mode
        for section in getattr(self, "input_sections", ()):
            section.grid() if mode == "input" else section.grid_remove()
        for section in getattr(self, "post_sections", ()):
            section.grid() if mode == "post" else section.grid_remove()
        colors = {"active_bg": "#1d4ed8", "active_fg": "#ffffff", "inactive_bg": "#f8fafc", "inactive_fg": "#1d4ed8"}
        for name, button in (("input", self.input_mode_button), ("post", self.post_mode_button)):
            active = name == mode
            button.configure(
                bg=colors["active_bg"] if active else colors["inactive_bg"],
                fg=colors["active_fg"] if active else colors["inactive_fg"],
                activebackground=colors["active_bg"] if active else "#e8f0ff",
                activeforeground=colors["active_fg"] if active else colors["inactive_fg"],
            )
        try:
            self.body_canvas.yview_moveto(0.0)
            self.after_idle(lambda: self.body_canvas.configure(scrollregion=self.body_canvas.bbox("all")))
        except Exception:
            pass

    def open_about_window(self):
        win = tk.Toplevel(self)
        win.title("About")
        win.transient(self)
        win.withdraw()
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        configure_builder_ui_style(win)

        box = ttk.Frame(win, padding=14)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(1, weight=1)
        icon = load_header_icon(TD_DFT_ICON_PATH, max_size=144)
        if icon is not None:
            win.about_icon = icon
            ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=8, sticky="n", padx=(0, 18))

        ttk.Label(box, text="TD-DFT", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text=ABOUT_PURPOSE, justify="left", wraplength=380).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Separator(box, orient="horizontal").grid(row=2, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text="GitHub", justify="left").grid(row=3, column=1, sticky="w")
        github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
        github_link.grid(row=4, column=1, sticky="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL, new=2))
        ttk.Label(box, text="Documentation", justify="left").grid(row=5, column=1, sticky="w", pady=(8, 0))
        wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
        wiki_link.grid(row=6, column=1, sticky="w", pady=(2, 0))
        wiki_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL + "#readme", new=2))
        citation_label = ttk.Label(box, text=CITATION_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left", wraplength=430)
        citation_label.grid(row=7, column=1, sticky="w", pady=(10, 0))
        citation_label.bind("<Button-1>", lambda _event: self._copy_about_citation(win, citation_label))
        ttk.Separator(box, orient="horizontal").grid(row=8, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text=COPYRIGHT_NOTE, foreground="#4b5563").grid(row=9, column=1, sticky="w")
        contact = ttk.Frame(box)
        contact.grid(row=10, column=1, sticky="w", pady=(7, 0))
        ttk.Label(contact, text=f"Email: {CONTACT_EMAIL}").grid(row=0, column=0, sticky="w")
        linkedin_icon = tk.Label(contact, text="in", bg="#0a66c2", fg="white", cursor="hand2", font=("Arial", 9, "bold"), padx=4, pady=1)
        linkedin_icon.grid(row=0, column=1, padx=(10, 0))
        linkedin_icon.bind("<Button-1>", lambda _event: webbrowser.open(LINKEDIN_URL, new=2))
        ttk.Button(box, text="Close", command=win.destroy).grid(row=11, column=0, columnspan=2, sticky="e", pady=(14, 0))

        win.update_idletasks()
        screen_width = max(1, win.winfo_screenwidth())
        screen_height = max(1, win.winfo_screenheight())
        width = min(max(570, win.winfo_reqwidth()), max(1, screen_width - 80))
        height = min(max(350, win.winfo_reqheight()), max(1, int(screen_height * 0.85)))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.resizable(False, False)
        win.deiconify(); win.lift(self); win.focus_force(); win.grab_set()

    def _copy_about_citation(self, window: tk.Toplevel, label: ttk.Label):
        try:
            window.clipboard_clear(); window.clipboard_append(CITATION_REFERENCE)
            label.configure(text="Cite as: copied to clipboard", foreground="#047857")
            window.after(1400, lambda: label.configure(text=CITATION_TEXT, foreground="#1d4ed8") if label.winfo_exists() else None)
        except Exception as exc:
            messagebox.showerror("Copy citation", str(exc), parent=window)

    def _sync_calculation_dependencies(self):
        manifold = self.vars["manifold"].get()
        if manifold == "Singlets" and self.vars["target_manifold"].get() != "Singlet":
            self.vars["target_manifold"].set("Singlet")
        elif manifold == "Triplets" and self.vars["target_manifold"].get() != "Triplet":
            self.vars["target_manifold"].set("Triplet")
        if hasattr(self, "target_manifold_combo"):
            self.target_manifold_combo.configure(state="readonly" if manifold == "Both" else "disabled")
        if self.excited_state_freq_var.get():
            if not self.excited_state_opt_var.get(): self.excited_state_opt_var.set(True)
            if not self.vertical_excitation_var.get(): self.vertical_excitation_var.set(True)
        elif self.excited_state_opt_var.get():
            if not self.vertical_excitation_var.get(): self.vertical_excitation_var.set(True)
        elif not self.vertical_excitation_var.get():
            if self.excited_state_opt_var.get(): self.excited_state_opt_var.set(False)
            if self.excited_state_freq_var.get(): self.excited_state_freq_var.set(False)
        steps = []
        if self.vertical_excitation_var.get():
            steps.append(f"1. Vertical excitation: {self.vars['nroots'].get()} roots, {self.vars['td_method'].get()}")
        if self.excited_state_opt_var.get():
            prefix = "S" if self.vars["target_manifold"].get() == "Singlet" else "T"
            steps.append(f"{len(steps) + 1}. Excited-state optimization: {prefix}{self.vars['root'].get()}")
        if self.excited_state_freq_var.get():
            prefix = "S" if self.vars["target_manifold"].get() == "Singlet" else "T"
            steps.append(f"{len(steps) + 1}. Excited-state frequencies: {prefix}{self.vars['root'].get()}")
        self.workflow_summary_var.set("TD-DFT calculation steps:\n" + ("\n".join(steps) if steps else "No calculation selected"))

    def _mark_tddft_modified(self):
        if self.on_apply and self.builder_enabled:
            self.connection_status_var.set("TD-DFT modified - click Show ORCA Block to synchronize")

    def set_builder_enabled(self, enabled: bool, synchronized: bool = False) -> None:
        self.builder_enabled = bool(enabled)
        if self.builder_enabled and synchronized:
            self.connection_status_var.set("TD-DFT block synchronized with ORCA Input Builder.")
        elif self.builder_enabled:
            self.connection_status_var.set("Connected to ORCA Input Builder - TD-DFT not yet synchronized")
        else:
            self.connection_status_var.set("TD-DFT is disabled in ORCA Input Builder")

    def set_builder_context(self, context: Dict) -> None:
        if not context:
            self.builder_context_var.set("")
            return
        solvent = context.get("solvent") or "gas phase"
        self.builder_context_var.set(
            f"Builder: {context.get('functional', '')} / {context.get('basis', '')} · "
            f"{solvent} · charge {context.get('charge', 0)} · multiplicity {context.get('multiplicity', 1)}"
        )

    def _close_window(self):
        if self.on_close:
            try:
                self.on_close(self)
            except Exception:
                pass
        self.destroy()

    def _settings(self): return validate_tddft_settings({key: var.get() for key, var in self.vars.items()})
    def update_progress(self, percent: int, message: str = "", color: str = "blue") -> None:
        percent = max(0, min(100, int(percent)))

        def apply() -> None:
            self.progress_var.set(percent)
            self.progress_text.set(f"{percent}%" + (f" - {message}" if message else ""))
            try:
                self.progress_bar.configure(style="Blue.Horizontal.TProgressbar")
            except Exception:
                pass

        try:
            self.after(0, apply)
        except Exception:
            pass

    def _guard(self, title, callback):
        try: return callback()
        except Exception as exc:
            self.update_progress(0, "Failed.", "red")
            messagebox.showerror(title, str(exc), parent=self)
    def _apply(self):
        def action():
            data = self._settings(); block = build_tddft_block(data)
            self.clipboard_clear(); self.clipboard_append(block)
            if self.on_apply:
                if not self.builder_enabled:
                    raise ValueError("TD-DFT is disabled in ORCA Input Builder. Enable it before synchronizing.")
                self.on_apply(block, data)
                self.connection_status_var.set("TD-DFT block synchronized with ORCA Input Builder.")
            else:
                self.connection_status_var.set("TD-DFT block generated. No ORCA Builder is connected.")
                messagebox.showinfo("ORCA TD-DFT block", block + "\n\nCopied to the clipboard.\n\nNo ORCA Builder is connected.", parent=self)
        self._guard("TD-DFT settings", action)
    def _load(self):
        def action():
            path = filedialog.askopenfilename(parent=self, filetypes=[("ORCA output", "*.out"), ("All files", "*.*")]);
            if not path: return
            self._set_loaded_output(path)
        self._guard("Load TD-DFT output", action)
    def _need_states(self):
        if not self.states: raise ValueError("Load an ORCA TD-DFT output first.")
        return self.states
    def _export_table(self):
        def action():
            states = self._need_states(); path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")]);
            if not path: return
            with Path(path).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle); writer.writerow(["State", "Energy_eV", "Wavelength_nm", "Oscillator_strength", "From", "To", "Coefficient", "Contribution_percent", "Contribution_source"])
                for state in states:
                    rows = state["transitions"] or [{}]
                    for tr in rows: writer.writerow([state["state"], state["energy_ev"], state["wavelength_nm"], state["oscillator_strength"], tr.get("from", ""), tr.get("to", ""), tr.get("coefficient", ""), tr.get("contribution_percent", ""), tr.get("contribution_source", "")])
        self._guard("Export TD-DFT table", action)
    def _plot(self):
        def action():
            import matplotlib.pyplot as plt
            states, data = self._need_states(), self._settings(); sticks = build_stick_spectrum(states, data["x_axis"]); curve = build_gaussian_broadened_spectrum(states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], data["x_axis"])
            if data["normalize"]: curve = normalize_spectrum(curve)
            plt.figure(figsize=(8, 5)); plt.vlines([x for x, _ in sticks], 0, [y for _, y in sticks], colors="#6b7280"); plt.plot([x for x, _ in curve], [y for _, y in curve], color="#1d4ed8"); plt.xlabel("Wavelength / nm" if data["x_axis"] == "nm" else "Energy / eV"); plt.ylabel("Oscillator strength / relative intensity"); plt.tight_layout(); plt.show()
        self._guard("Plot spectrum", action)
    def _export_spectrum(self):
        def action():
            states, data = self._need_states(), self._settings(); path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")]);
            if path:
                curve = build_gaussian_broadened_spectrum(states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], data["x_axis"])
                if data["normalize"]: curve = normalize_spectrum(curve)
                export_spectrum_csv(path, build_stick_spectrum(states, data["x_axis"]), curve, data["x_axis"])
        self._guard("Export spectrum", action)
    def _save_plot(self, suffix):
        def action():
            states, data = self._need_states(), self._settings(); path = filedialog.asksaveasfilename(parent=self, defaultextension=suffix, filetypes=[(suffix.upper()[1:], "*" + suffix)]);
            if path: save_spectrum(path, states, data)
        self._guard("Save spectrum", action)

    def _set_loaded_output(self, path):
        self._set_ui_mode("post")
        self.update_progress(10, "Reading ORCA TD-DFT output...")
        self.states, self.output_path = parse_orca_tddft_output(str(path)), str(Path(path).resolve())
        self.update_progress(40, "Populating excited-state results...")
        self.tree.delete(*self.tree.get_children())
        for state in self.states:
            trans = max(state["transitions"], key=lambda x: x["contribution_percent"], default=None)
            self.tree.insert("", "end", iid=str(state["state_index"]), values=(state["state"], f"{state['energy_ev']:.4f}", f"{state['wavelength_nm']:.2f}", f"{state['oscillator_strength']:.6g}", f"{trans['from']} -> {trans['to']}" if trans else "", f"{trans['contribution_percent']:.1f}" if trans else ""))
        self.update_progress(65, "Detecting associated files...")
        self.output_label.configure(text=self.output_path); self.workdir_var.set(str(Path(self.output_path).parent)); self._detect_files()
        if self.tree.get_children(): self.tree.selection_set(self.tree.get_children()[0])
        self.update_progress(80, "Writing spectrum package...")
        self._write_shared_spectrum_package()
        self.update_progress(100, "ORCA output loaded.", "darkgreen")

    def _detect_files(self):
        if not self.output_path: raise ValueError("Load an ORCA output first.")
        manual = self.associated_files.get("manual")
        self.associated_files = detect_associated_files(self.output_path)
        if manual and Path(manual).is_file(): self.associated_files["manual"] = manual
        self.associated_summary_var.set("\n".join(f"{key}: {value}" for key, value in self.associated_files.items()) or "No associated files detected.")

    def _replace_wavefunction(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Wavefunction files", "*.wfn *.wfx *.fchk *.molden *.input *.gbw"), ("All files", "*.*")])
        if path:
            self.associated_files["manual"] = str(Path(path).resolve()); self.associated_summary_var.set("\n".join(f"{key}: {value}" for key, value in self.associated_files.items()))

    def _browse_multiwfn(self):
        path = filedialog.askopenfilename(parent=self, title="Select Multiwfn executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if path: self.multiwfn_var.set(path); self._save_module_settings()

    def _save_module_settings(self):
        MODULE_SETTINGS.write_text(json.dumps({"multiwfn_path": self.multiwfn_var.get().strip()}, indent=2), encoding="utf-8")

    def _validate_multiwfn(self):
        if not self.output_path: raise ValueError("Load an ORCA output first.")
        runner = MultiwfnTDDFTRunner(self.multiwfn_var.get(), str(Path(self.output_path).parent)); executable = runner.executable(); self._save_module_settings()
        messagebox.showinfo("Multiwfn", f"Executable: {executable}\nVersion: {runner.version()}", parent=self)

    def _selected_state(self):
        selected = self.tree.selection()
        if not selected: raise ValueError("Select an excited state in the state table.")
        index = int(selected[0]); return next(state for state in self.states if int(state["state_index"]) == index)

    def _analysis_directory(self, state_index=None):
        if not self.output_path: raise ValueError("Load an ORCA output first.")
        root = Path(self.output_path).parent / "TDDFT_analysis"
        return root / f"S{state_index}" if state_index else root

    def _write_shared_spectrum_package(self):
        if not self.states or not self.output_path: return
        root = self._analysis_directory(); root.mkdir(parents=True, exist_ok=True); base = Path(self.output_path).stem; data = self._settings()
        with (root / f"{base}_TDDFT_states.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle); writer.writerow(["State", "Energy_eV", "Wavelength_nm", "Oscillator_strength"]); writer.writerows((s["state"], s["energy_ev"], s["wavelength_nm"], s["oscillator_strength"]) for s in self.states)
        sticks = build_stick_spectrum(self.states, data["x_axis"]); curve = build_gaussian_broadened_spectrum(self.states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], data["x_axis"])
        if data["normalize"]: curve = normalize_spectrum(curve)
        for name, header, rows in [(f"{base}_UVVis_stick.csv", [data["x_axis"], "oscillator_strength"], sticks), (f"{base}_UVVis_broadened.csv", [data["x_axis"], "intensity"], curve)]:
            with (root / name).open("w", newline="", encoding="utf-8") as handle: writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
        save_spectrum(str(root / f"{base}_UVVis.png"), self.states, data); save_spectrum(str(root / f"{base}_UVVis.svg"), self.states, data)
        self.status_tree.item("UV-Vis spectrum", values=("UV-Vis spectrum", "Ready"))

    def _wavefunction_file(self):
        for key in ("manual", ".wfx", ".wfn", ".fchk", ".molden.input", ".molden", ".gbw"):
            value = self.associated_files.get(key)
            if value and Path(value).is_file(): return value
        return ""

    def _start_analysis(self, force=False):
        def action():
            self.update_progress(0, "Starting TD-DFT analysis...")
            state = self._selected_state(); self._write_shared_spectrum_package()
            for iid in self.status_tree.get_children():
                if iid != "UV-Vis spectrum": self.status_tree.item(iid, values=(iid, "Running"))
            self.generate_button.configure(state="disabled")
            self.update_progress(20, "Preparing selected-state analysis...")
            threading.Thread(target=self._analysis_worker, args=(state, force), daemon=True).start()
        self._guard("TD-DFT analysis", action)

    def _analysis_worker(self, state, force):
        try:
            self.update_progress(35, "Resolving wavefunction and Multiwfn...")
            state_index = int(state["state_index"]); output = self._analysis_directory(state_index); wavefunction = self._wavefunction_file()
            runner = MultiwfnTDDFTRunner(self.multiwfn_var.get(), str(Path(self.output_path).parent))
            self.update_progress(55, f"Generating analysis package for state {state_index}...")
            result = runner.generate_all_analyses(state_index, wavefunction, self.output_path, str(output), self.associated_files, force)
            self.update_progress(90, "Updating analysis results...")
            self.after(0, lambda: self._analysis_finished(result, None))
        except Exception as exc:
            self.after(0, lambda error=exc: self._analysis_finished(None, error))

    def _analysis_finished(self, result, error):
        self.generate_button.configure(state="normal")
        if error:
            self.update_progress(0, "Analysis failed.", "red")
            for iid in self.status_tree.get_children():
                if self.status_tree.item(iid, "values")[1] == "Running": self.status_tree.item(iid, values=(iid, "Failed"))
            messagebox.showerror("TD-DFT analysis", str(error), parent=self); return
        self.analysis_result = result
        for name, item in result["analyses"].items(): self.status_tree.item(name, values=(name, item["status"]))
        self._refresh_mode_availability()
        self.update_progress(100, "Analysis complete.", "darkgreen")

    def _refresh_mode_availability(self):
        pass  # The display action validates the exact files for the chosen mode.

    def _mode_files(self):
        state = self._selected_state(); runner = MultiwfnTDDFTRunner(self.multiwfn_var.get(), str(Path(self.output_path).parent)); paths = runner.expected_paths(state["state_index"], self.output_path, str(self._analysis_directory(state["state_index"])))
        p = {name: [str(value) for value in values] for name, values in paths.items()}; mode = self.mode_var.get()
        mapping = {"NTO hole": (p["NTO hole/electron"][:1], ["NTO hole"]), "NTO electron": (p["NTO hole/electron"][1:], ["NTO electron"]), "NTO pair": (p["NTO hole/electron"], ["NTO hole", "NTO electron"]), "Difference density": (p["Difference density"], ["Density gain/loss"]), "Transition density": (p["Transition density"], ["Transition-density phase"]), "Attachment density": (p["Attachment/detachment"][:1], ["Attachment"]), "Detachment density": (p["Attachment/detachment"][1:], ["Detachment"]), "Attachment/detachment overlay": (p["Attachment/detachment"], ["Attachment", "Detachment"]), "Hole density": (p["Hole/electron density"][:1], ["Hole"]), "Electron density": (p["Hole/electron density"][1:], ["Electron"]), "Hole/electron overlay": (p["Hole/electron density"], ["Hole", "Electron"])}
        return mapping.get(mode, ([], []))

    def _viewer_options(self):
        mode = self.mode_var.get(); orbital = mode.startswith("NTO"); signed = mode in {"Difference density", "Transition density"}
        positive = float(self.orbital_iso_var.get() if orbital else self.positive_iso_var.get() if signed else self.density_iso_var.get())
        negative = float(self.orbital_iso_var.get() if orbital else self.negative_iso_var.get() if signed else self.density_iso_var.get()); opacity = float(self.opacity_var.get())
        if min(positive, negative) <= 0 or not 0 < opacity <= 1: raise ValueError("Isovalues must be positive and opacity must be in (0, 1].")
        return positive, negative, opacity

    def _display_mode(self):
        def action():
            if self.mode_var.get() == "UV-Vis spectrum": self._plot(); return
            files, labels = self._mode_files(); missing = [path for path in files if not Path(path).is_file()]
            if missing: raise FileNotFoundError("Required generated cube file(s) are unavailable:\n" + "\n".join(missing))
            iso, negative, opacity = self._viewer_options(); SignedCubeViewer().show(files, iso, negative, opacity, self.show_molecule_var.get(), self.show_bonds_var.get(), self.show_labels_var.get(), labels=labels)
        self._guard("TD-DFT visualization", action)

    def _save_screenshot(self):
        def action():
            if self.mode_var.get() == "UV-Vis spectrum": self._save_plot(".png"); return
            files, labels = self._mode_files();
            if not files or any(not Path(path).is_file() for path in files): raise FileNotFoundError("Generate or provide the required cube files first.")
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".png", filetypes=[("PNG", "*.png")]);
            if path:
                iso, negative, opacity = self._viewer_options(); SignedCubeViewer().show(files, iso, negative, opacity, self.show_molecule_var.get(), self.show_bonds_var.get(), self.show_labels_var.get(), screenshot=path, labels=labels)
        self._guard("Save screenshot", action)

    def _export_cubes(self):
        def action():
            files, _ = self._mode_files(); files = [Path(path) for path in files if Path(path).is_file()]
            if not files: raise FileNotFoundError("No generated cube files are available for this mode.")
            directory = filedialog.askdirectory(parent=self, title="Export generated cube files");
            if not directory: return
            for source in files:
                target = Path(directory) / source.name; counter = 1
                while target.exists(): target = Path(directory) / f"{source.stem}_{counter}{source.suffix}"; counter += 1
                shutil.copy2(source, target)
        self._guard("Export cubes", action)

    def _open_analysis_directory(self):
        def action():
            directory = self._analysis_directory(); directory.mkdir(parents=True, exist_ok=True)
            if os.name == "nt": os.startfile(str(directory))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(directory)], shell=False)
            else: subprocess.Popen(["xdg-open", str(directory)], shell=False)
        self._guard("Open analysis directory", action)


def open_tddft_window(parent=None, initial_settings=None, on_apply=None, on_close=None, builder_context=None) -> TDDFTWindow:
    """Open one Builder-connected TD-DFT ``Toplevel`` without creating a new Tk root."""
    if parent is None:
        raise ValueError("A Tk parent is required when embedding the TD-DFT window.")
    return TDDFTWindow(parent, initial_settings or DEFAULT_TDDFT_SETTINGS, on_apply=on_apply, on_close=on_close, builder_context=builder_context)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone CrystEngKit TD-DFT setup and UV-Vis analyzer")
    parser.add_argument("--output", "-o", help="ORCA .out file to load after startup")
    args = parser.parse_args(argv)
    root = tk.Tk()
    root.withdraw()
    window = TDDFTWindow(root, DEFAULT_TDDFT_SETTINGS)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    if args.output:
        path = Path(args.output).expanduser().resolve()
        def load_argument():
            try:
                window._set_loaded_output(path)
            except Exception as exc:
                messagebox.showerror("Load TD-DFT output", str(exc), parent=window)
        window.after(50, load_argument)
    root.mainloop()


if __name__ == "__main__":
    main()
