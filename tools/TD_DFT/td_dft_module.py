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

MODULE_DIR = Path(__file__).resolve().parent
TOOLS_ROOT = MODULE_DIR.parent
APP_ROOT = TOOLS_ROOT.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from app_identity import configure_tk_window_identity, install_dev_reload_shortcut, set_windows_app_id

try:
    from .td_dft_cube_viewer import SignedCubeViewer
    from .td_dft_multiwfn_runner import MultiwfnTDDFTRunner
except ImportError:
    # Keep direct `python td_dft_module.py` execution working from this folder.
    from td_dft_cube_viewer import SignedCubeViewer
    from td_dft_multiwfn_runner import MultiwfnTDDFTRunner

HC_EV_NM = 1239.841984
MODULE_SETTINGS = Path(__file__).with_name("td_dft_settings.json")
ASSOCIATED_SUFFIXES = (".gbw", ".molden.input", ".molden", ".wfn", ".wfx", ".fchk")
TD_DFT_ICON_PATH = TOOLS_ROOT / "images" / "tr_homo_lumo_icon.png"
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
WORKFLOW_VERTICAL = "Vertical excitation / UV-Vis"
WORKFLOW_OPT = "Excited-state optimization"
WORKFLOW_OPT_FREQ = "Excited-state optimization + frequencies"
WORKFLOW_OPTIONS = (WORKFLOW_VERTICAL, WORKFLOW_OPT, WORKFLOW_OPT_FREQ)

DEFAULT_TDDFT_SETTINGS = {
    "vertical_excitation": True,
    "excited_state_optimization": False,
    "excited_state_frequencies": False,
    "td_method": "TDDFT",
    "nroots": 10,
    "root": 1,
    "maxdim": 5,
    "maxiter": 300,
    "manifold": "Singlets",
    "target_manifold": "Singlet",
    "print_ntos": True,
    "difference_density": False,
    "transition_density": False,
    "excited_state_density": False,
    "broadening_ev": 0.20,
    "wavelength_min_nm": 150.0,
    "wavelength_max_nm": 800.0,
    "x_axis": "nm",
    "normalize": False,
}

LEGACY_ERRONEOUS_MAXDIM_DEFAULT = 120
SAFE_DEFAULT_MAXDIM = 5
MAXDIM_STRONG_WARNING_THRESHOLD = 20
EXPANSION_WARNING_THRESHOLD = 300


def estimate_tddft_expansion_vectors(nroots: int, maxdim: int) -> int:
    """Return ORCA's practical iterative expansion-space indicator."""
    return int(nroots) * int(maxdim)


def migrate_legacy_tddft_settings(settings: Dict) -> Tuple[Dict, List[str]]:
    """Migrate known unsafe saved TD-DFT defaults without changing new defaults."""
    data = dict(settings or {})
    warnings: List[str] = []
    try:
        maxdim = int(data.get("maxdim"))
    except Exception:
        return data, warnings
    if maxdim == LEGACY_ERRONEOUS_MAXDIM_DEFAULT:
        data["maxdim"] = SAFE_DEFAULT_MAXDIM
        warnings.append(
            "The legacy TD-DFT MaxDim default of 120 was corrected to 5 "
            "to reduce excessive TD-DFT expansion-space memory use."
        )
    return data, warnings


def tddft_memory_risk_warnings(settings: Dict, context: Optional[Dict] = None) -> List[str]:
    """Return qualitative TD-DFT memory-risk warnings; this is not a RAM formula."""
    data = validate_tddft_settings(settings)
    context = context or {}
    nroots, maxdim = int(data["nroots"]), int(data["maxdim"])
    expansion = estimate_tddft_expansion_vectors(nroots, maxdim)
    warnings: List[str] = []
    if maxdim > MAXDIM_STRONG_WARNING_THRESHOLD or expansion > EXPANSION_WARNING_THRESHOLD:
        warnings.append(
            "Large TD-DFT expansion space\n\n"
            f"NRoots: {nroots}\n"
            f"MaxDim: {maxdim}\n"
            f"Estimated maximum expansion space: approximately {expansion} vectors.\n\n"
            "Large MaxDim values can require excessive memory and may cause ORCA to fail with:\n\n"
            "Not a single batch is possible with the present MaxCore.\n\n"
            "A typical MaxDim value is approximately 5."
        )
    maxcore = context.get("maxcore_mb")
    basis_functions = context.get("basis_functions")
    try:
        maxcore_value = int(maxcore)
    except Exception:
        maxcore_value = None
    try:
        basis_count = int(basis_functions)
    except Exception:
        basis_count = None
    if maxcore_value is not None and maxcore_value < 1000 and (basis_count is None or basis_count > 1000 or expansion > EXPANSION_WARNING_THRESHOLD):
        warnings.append(
            "TD-DFT memory-risk warning\n\n"
            f"Global MaxCore: {maxcore_value} MB per process\n"
            f"Basis functions: {basis_count if basis_count is not None else 'not known'}\n\n"
            "This setup may be memory-limited for TD-DFT. Consider increasing MaxCore "
            "according to available physical RAM and reducing MaxDim to approximately 5."
        )
    return warnings


def classify_orca_tddft_failure_text(text: str) -> Dict:
    """Classify known ORCA TD-DFT memory-batching failures."""
    upper = str(text or "").upper()
    if "NOT A SINGLE BATCH IS POSSIBLE WITH THE PRESENT MAXCORE" in upper:
        return {
            "category": "tddft_memory",
            "module": "CIS/TD-DFT",
            "message": (
                "ORCA TD-DFT failed because no integral batch could fit "
                "within the available MaxCore memory."
            ),
            "recommendations": [
                "Reduce MaxDim to approximately 5.",
                "Increase MaxCore according to available physical RAM.",
                "Check NRoots.",
                "Check the number of ORCA processes.",
            ],
            "matched": True,
        }
    if "ORCA FINISHED BY ERROR TERMINATION IN CIS" in upper and "RPA/TD-DFT DID NOT CONVERGE" in upper:
        return {
            "category": "tddft_nonconvergence",
            "module": "CIS/TD-DFT",
            "message": "ORCA TD-DFT/RPA did not converge.",
            "recommendations": [
                "Increase TD-DFT MaxIter if scientifically appropriate.",
                "Try TDA only as a deliberate approximation.",
                "Check the requested roots and starting wavefunction.",
            ],
            "matched": True,
        }
    return {"category": "", "module": "", "message": "", "recommendations": [], "matched": False}


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
    data["maxdim"] = int(data["maxdim"])
    data["maxiter"] = int(data["maxiter"])
    data["broadening_ev"] = float(data["broadening_ev"])
    data["wavelength_min_nm"] = float(data["wavelength_min_nm"])
    data["wavelength_max_nm"] = float(data["wavelength_max_nm"])
    # NTO preparation is a required part of every CrystEngKit TD-DFT job.
    # Keep legacy profiles that stored print_ntos=False from disabling it.
    data["print_ntos"] = True
    if data["excited_state_frequencies"]:
        data["vertical_excitation"] = False
        data["excited_state_optimization"] = True
    elif data["excited_state_optimization"]:
        data["vertical_excitation"] = False
    elif not data["vertical_excitation"]:
        data["vertical_excitation"] = True
    if data["nroots"] < 1 or data["root"] < 1:
        raise ValueError("NROOTS and ROOT must be positive integers.")
    if data["maxdim"] < 1:
        raise ValueError("MaxDim must be a positive integer.")
    if data["maxiter"] < 1:
        raise ValueError("MaxIter must be a positive integer.")
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
    if data["manifold"] == "Singlets":
        data["target_manifold"] = "Singlet"
    elif data["manifold"] == "Triplets":
        data["target_manifold"] = "Triplet"
    return data


def normalize_tddft_block(block: str) -> str:
    """Normalize legacy or mixed TD-DFT fragment syntax to ORCA-compatible form."""
    text = str(block or "").strip()
    if not text:
        return ""
    lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*%tdg\b", line, re.I):
            lines.append("%tddft")
            continue
        if re.match(r"^\s*FollowIRoot\b", line, re.I):
            continue
        if re.match(r"^\s*Mult\b", line, re.I):
            tokens = line.split(None, 1)
            if len(tokens) == 2:
                lines.append(f"  IRootMult {tokens[1].strip()}")
            else:
                lines.append("  IRootMult")
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def build_tddft_block(settings: Dict) -> str:
    """Return an ORCA-compatible TD-DFT block for excited-state work.

    For excited-state optimization or gradient calculations, ORCA 6.0.1 accepts
    the classical ``%tddft`` block with ``IRoot`` and ``IRootMult`` keywords.
    The obsolete ``FollowIRoot`` keyword is not emitted here; it should be added
    only by the emission-sequence helper if required by a specific workflow.
    """
    data = validate_tddft_settings(settings)
    lines = ["%tddft", f"  NRoots {data['nroots']}"]
    lines.extend([
        f"  TDA {'true' if data['td_method'] == 'TDA' else 'false'}",
        f"  MaxDim {data['maxdim']}",
        f"  MaxIter {data['maxiter']}",
        "  DoNTO true",
        "  NTOThresh 1e-4",
    ])
    if bool(data["excited_state_optimization"] or data["excited_state_frequencies"]):
        lines.extend([
            f"  IRoot {data['root']}",
            f"  IRootMult {data['target_manifold'].lower()}",
        ])
    if data["manifold"] in {"Triplets", "Both"} or data["target_manifold"] == "Triplet":
        lines.append("  Triplets true")
    lines.append("end")
    return normalize_tddft_block("\n".join(lines))


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
            if not match:
                match = re.match(
                    r"^\s*\S+\s+->\s+(\d+)-\S+\s+"
                    r"([+-]?\d+(?:\.\d+)?)\s+"
                    r"([+-]?\d+(?:\.\d+)?)\s+"
                    r"([+-]?\d+(?:\.\d+)?)\s+"
                    r"([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)",
                    line,
                )
            if match:
                idx = int(match.group(1))
                if len(match.groups()) == 4:
                    wavenumber, wavelength, fosc = float(match.group(2)), float(match.group(3)), float(match.group(4))
                    energy_ev = wavenumber / 8065.544
                else:
                    energy_ev, wavenumber, wavelength, fosc = float(match.group(2)), float(match.group(3)), float(match.group(4)), float(match.group(5))
                state = states.setdefault(idx, {"state": _state_label(idx), "state_index": idx, "transitions": []})
                state.update({"energy_ev": energy_ev, "wavelength_nm": wavelength, "oscillator_strength": fosc})
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


def suggest_wavelength_range_for_states(states: Sequence[Dict], current_min_nm: float, current_max_nm: float) -> Tuple[float, float]:
    bright = [s for s in states if float(s.get("oscillator_strength", 0.0)) > 1.0e-8]
    if not bright:
        return current_min_nm, current_max_nm
    max_fosc = max(float(s.get("oscillator_strength", 0.0)) for s in bright)
    important = [s for s in bright if float(s.get("oscillator_strength", 0.0)) >= max_fosc * 0.01]
    wavelengths = [float(s["wavelength_nm"]) for s in important if float(s.get("wavelength_nm", 0.0)) > 0]
    if not wavelengths:
        return current_min_nm, current_max_nm
    visible = any(current_min_nm <= wavelength <= current_max_nm for wavelength in wavelengths)
    if visible:
        return current_min_nm, current_max_nm
    lower = max(1.0, math.floor(min(wavelengths) * 0.9))
    upper = math.ceil(max(wavelengths) * 1.1)
    return min(current_min_nm, lower), max(current_max_nm, upper)


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


def suggested_tddft_export_path(output_path: str, artifact: str, suffix: str) -> Path:
    """Suggest a user-facing export name without renaming calculation files."""
    source = Path(output_path) if output_path else Path.cwd() / "td-dft.out"
    tag = re.sub(r"[^A-Za-z0-9.-]+", "-", str(artifact or "export").strip()).strip("-.").lower()
    extension = str(suffix or "")
    if not extension.startswith("."):
        extension = "." + extension
    return source.with_name(f"{source.stem}_{tag or 'export'}{extension.lower()}")


def detect_associated_files(output_path: str) -> Dict[str, str]:
    output = Path(output_path).resolve(); result = {}
    for suffix in ASSOCIATED_SUFFIXES:
        exact = output.with_name(output.stem + suffix)
        candidates = [exact] if exact.is_file() else sorted(output.parent.glob("*" + suffix), key=lambda p: (p.stem != output.stem, p.name.lower()))
        if candidates:
            result[suffix] = str(candidates[0].resolve())
    return result


def load_saved_multiwfn_path() -> str:
    candidates = [MODULE_SETTINGS, MODULE_DIR / "orca_gaussian_builder_settings.json", APP_ROOT / "orca_gaussian_builder_settings.json"]
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
    return auto_detect_multiwfn_path()


def auto_detect_multiwfn_path(saved: str = "") -> str:
    names = ("Multiwfn.exe", "Multiwfn", "multiwfn")
    candidates: List[Path] = []
    for value in (saved, os.environ.get("Multiwfnpath", "")):
        value = str(value or "").strip().strip('"')
        if not value:
            continue
        path = Path(value).expanduser()
        candidates.extend([path / name for name in names] if path.is_dir() else [path])
    for root in (
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
        "C:\\Multiwfn",
        "C:\\Program Files\\Multiwfn",
    ):
        if str(root).strip():
            base = Path(root).expanduser()
            candidates.extend(base / name for name in names)
            candidates.extend(base / "Multiwfn" / name for name in names)
    for name in names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return str(resolved)
    return ""


class TDDFTWindow(tk.Toplevel):
    def __init__(self, parent, settings: Dict, on_apply=None, on_close=None, builder_context=None, on_run_emission_sequence=None):
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
        self.on_apply, self.on_close, self.on_run_emission_sequence = on_apply, on_close, on_run_emission_sequence
        self.states, self.output_path = [], ""
        self.builder_enabled = bool(on_apply)
        self.builder_context: Dict = {}
        self.ui_mode = "input"
        self._pending_builder_output_path = ""
        self.connection_status_var = tk.StringVar(value="Connected to ORCA Input Builder" if on_apply else "Standalone mode - no ORCA Builder connected")
        self.builder_context_var = tk.StringVar(value="")
        self.set_builder_context(builder_context or {})
        self.associated_files, self.analysis_result = {}, {}
        self.multiwfn_var = tk.StringVar(value=load_saved_multiwfn_path())
        context_multiwfn = str((builder_context or {}).get("multiwfn_path", "")).strip()
        if context_multiwfn and not self.multiwfn_var.get().strip():
            self.multiwfn_var.set(context_multiwfn)
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
        migration_warnings: List[str] = []
        if settings:
            initial, migration_warnings = migrate_legacy_tddft_settings(initial)
        self.migration_warnings = migration_warnings
        self.vars = {key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))) for key, value in initial.items()}
        self.vertical_excitation_var = self.vars["vertical_excitation"]
        self.excited_state_opt_var = self.vars["excited_state_optimization"]
        self.excited_state_freq_var = self.vars["excited_state_frequencies"]
        self.workflow_var = tk.StringVar(value=self._workflow_from_settings())
        self.workflow_summary_var = tk.StringVar()
        self.workflow_var.trace_add("write", lambda *_args: self._apply_workflow_selection())
        for key in ("nroots", "root", "td_method", "manifold", "maxdim"):
            self.vars[key].trace_add("write", lambda *_args: self._sync_calculation_dependencies())
        self._build()
        self._apply_workflow_selection()
        self._auto_load_builder_output()
        if self.migration_warnings:
            self.update_progress(0, self.migration_warnings[0], "blue")
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
        ttk.Label(calculation_box, text="Workflow", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 3))
        ttk.Combobox(
            calculation_box,
            textvariable=self.workflow_var,
            values=WORKFLOW_OPTIONS,
            state="readonly",
            width=34,
        ).pack(anchor="w", fill="x")
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
        ttk.Label(parameters, text="MaxDim multiplier").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(parameters, textvariable=self.vars["maxdim"], width=10).grid(row=6, column=1, sticky="ew", pady=2)
        ttk.Label(parameters, text="Max iterations").grid(row=7, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(parameters, textvariable=self.vars["maxiter"], width=10).grid(row=7, column=1, sticky="ew", pady=2)
        ttk.Label(
            parameters,
            text="Approximate maximum iterative expansion: NRoots x MaxDim. Typical MaxDim: 5.",
            style="Muted.TLabel",
            wraplength=330,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(3, 0))
        ttk.Separator(setup, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 6))
        ttk.Label(setup, textvariable=self.workflow_summary_var, style="Muted.TLabel", justify="left", wraplength=430).grid(row=2, column=0, sticky="w")
        apply_box = ttk.Frame(setup); apply_box.grid(row=2, column=1, sticky="e")
        ttk.Label(apply_box, text="NTO generation: enabled for all calculated states", style="Muted.TLabel").pack(anchor="e", pady=(0, 3))
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
        result_actions = [
            ("Load ORCA output", self._load),
            ("Plot UV-Vis", self._plot),
            ("Save image...", self._save_plot_image),
            ("Export states CSV", self._export_table),
            ("Export spectrum CSV", self._export_spectrum),
        ]
        for index, (text, command) in enumerate(result_actions):
            ttk.Button(actions, text=text, command=command, style="Primary.TButton" if index == 0 else "TButton").grid(row=index // 3, column=index % 3, sticky="ew", padx=(0 if index % 3 == 0 else 5, 0), pady=(0, 5))
        for column in range(3): actions.columnconfigure(column, weight=1)
        columns = ("state", "ev", "nm", "f", "transition", "percent"); self.tree = ttk.Treeview(tablebox, columns=columns, show="headings")
        for key, label, width in zip(columns, ["State", "Energy / eV", "Wavelength / nm", "f", "Main transition", "Contribution / %"], [52, 82, 105, 68, 158, 105]): self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=48, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tablebox, orient="horizontal", command=self.tree.xview); tree_scroll.grid(row=2, column=0, sticky="ew"); self.tree.configure(xscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_mode_availability())

        emission = ttk.LabelFrame(root, text="Fluorescence emission", padding=8); emission.grid(row=5, column=0, sticky="ew", pady=(8, 0)); emission.columnconfigure(1, weight=1)
        self.emission_status_var = tk.StringVar(value="Load a completed absorption TD-DFT output to prepare an emission calculation sequence.")
        ttk.Label(emission, text="Emitting root").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(emission, textvariable=self.vars["root"], width=8).grid(row=0, column=1, sticky="w")
        emission_actions = ttk.Frame(emission)
        emission_actions.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        ttk.Button(emission_actions, text="Prepare calculation sequence", command=self._prepare_emission_sequence, style="Primary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(emission_actions, text="Prepare + Run sequence", command=self._run_emission_sequence, style="Primary.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(emission_actions, text="Open emission directory", command=self._open_emission_directory).pack(side="left")
        ttk.Label(emission, textvariable=self.emission_status_var, style="Muted.TLabel", justify="left", wraplength=560).grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self.emission_directory = ""

        viz = ttk.LabelFrame(root, text="Analysis and visualization", padding=8); viz.grid(row=6, column=0, sticky="ew", pady=(8, 0)); viz.columnconfigure(0, weight=1)
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
        self.post_sections = (spectrum, progress_frame, tablebox, emission, viz)
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

    def _workflow_from_settings(self) -> str:
        if self.excited_state_freq_var.get():
            return WORKFLOW_OPT_FREQ
        if self.excited_state_opt_var.get():
            return WORKFLOW_OPT
        return WORKFLOW_VERTICAL

    def _apply_workflow_selection(self):
        mode = self.workflow_var.get()
        if mode not in WORKFLOW_OPTIONS:
            mode = WORKFLOW_VERTICAL
            self.workflow_var.set(mode)
        values = {
            WORKFLOW_VERTICAL: (True, False, False),
            WORKFLOW_OPT: (False, True, False),
            WORKFLOW_OPT_FREQ: (False, True, True),
        }[mode]
        for variable, value in zip(
            (self.vertical_excitation_var, self.excited_state_opt_var, self.excited_state_freq_var),
            values,
        ):
            if variable.get() != value:
                variable.set(value)
        self._sync_calculation_dependencies()

    def _sync_calculation_dependencies(self):
        manifold = self.vars["manifold"].get()
        if manifold == "Singlets" and self.vars["target_manifold"].get() != "Singlet":
            self.vars["target_manifold"].set("Singlet")
        elif manifold == "Triplets" and self.vars["target_manifold"].get() != "Triplet":
            self.vars["target_manifold"].set("Triplet")
        if hasattr(self, "target_manifold_combo"):
            self.target_manifold_combo.configure(state="readonly" if manifold == "Both" else "disabled")
        steps = []
        if self.vertical_excitation_var.get():
            steps.append(f"Vertical {self.vars['nroots'].get()} roots, {self.vars['td_method'].get()}")
        if self.excited_state_opt_var.get():
            prefix = "S" if self.vars["target_manifold"].get() == "Singlet" else "T"
            steps.append(f"Opt {prefix}{self.vars['root'].get()}")
        if self.excited_state_freq_var.get():
            prefix = "S" if self.vars["target_manifold"].get() == "Singlet" else "T"
            steps.append(f"Freq {prefix}{self.vars['root'].get()}")
        try:
            nroots = int(self.vars["nroots"].get())
            maxdim = int(self.vars["maxdim"].get())
            expansion = estimate_tddft_expansion_vectors(nroots, maxdim)
            estimate = f"\nEstimated maximum expansion space: approximately {expansion} vectors"
        except Exception:
            estimate = "\nEstimated maximum expansion space: enter valid NRoots and MaxDim"
        self.workflow_summary_var.set("Steps: " + (" | ".join(steps) if steps else "none selected") + estimate)

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
        self.builder_context = dict(context or {})
        if not context:
            self.builder_context_var.set("")
            self._pending_builder_output_path = ""
            return
        context_multiwfn = str(context.get("multiwfn_path", "")).strip()
        if context_multiwfn and hasattr(self, "multiwfn_var") and not self.multiwfn_var.get().strip():
            self.multiwfn_var.set(context_multiwfn)
        self._pending_builder_output_path = str(context.get("output_path", "")).strip()
        solvent = context.get("solvent") or "gas phase"
        self.builder_context_var.set(
            f"Builder: {context.get('functional', '')} / {context.get('basis', '')} · "
            f"{solvent} · charge {context.get('charge', 0)} · multiplicity {context.get('multiplicity', 1)}"
        )

        maxcore = context.get("maxcore_mb")
        nprocs = context.get("nprocs")
        try:
            if maxcore not in (None, "") and nprocs not in (None, ""):
                total = int(maxcore) * int(nprocs)
                memory_line = (
                    f"\nGlobal MaxCore: {int(maxcore)} MB per process | "
                    f"ORCA processes: {int(nprocs)} | Approximate requested memory: {total} MB"
                )
            else:
                memory_line = "\nGlobal MaxCore: not set in Builder context | ORCA processes: not set"
        except Exception:
            memory_line = "\nGlobal MaxCore / ORCA process count: unavailable"
        self.builder_context_var.set(self.builder_context_var.get() + memory_line)

        if hasattr(self, "output_label"):
            self._auto_load_builder_output()

    def _auto_load_builder_output(self) -> None:
        path_text = str(getattr(self, "_pending_builder_output_path", "") or "").strip()
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.lower() != ".out" or not path.is_file():
            return
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if self.output_path and os.path.normcase(self.output_path) == os.path.normcase(resolved):
            return
        try:
            self._set_loaded_output(resolved)
        except Exception as exc:
            self.update_progress(0, f"Builder output not loaded: {exc}", "red")

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

    def _confirm_tddft_memory_risk(self, data: Dict) -> None:
        warnings = tddft_memory_risk_warnings(data, self.builder_context)
        if not warnings:
            return
        message = "\n\n".join(warnings) + "\n\nContinue with these TD-DFT settings?"
        if not messagebox.askokcancel("TD-DFT memory-risk warning", message, parent=self):
            raise ValueError("TD-DFT synchronization cancelled after memory-risk warning.")

    def _apply(self):
        def action():
            data = self._settings(); block = build_tddft_block(data)
            self._confirm_tddft_memory_risk(data)
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
            states = self._need_states(); suggested = suggested_tddft_export_path(self.output_path, "states", ".csv")
            path = filedialog.asksaveasfilename(parent=self, title="Export excited-state table", defaultextension=".csv", initialdir=str(suggested.parent), initialfile=suggested.name, filetypes=[("CSV", "*.csv")]);
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
            states = self._need_states()
            try:
                current_min = float(self.vars["wavelength_min_nm"].get())
                current_max = float(self.vars["wavelength_max_nm"].get())
                new_min, new_max = suggest_wavelength_range_for_states(states, current_min, current_max)
                if new_min != current_min or new_max != current_max:
                    self.vars["wavelength_min_nm"].set(f"{new_min:g}")
                    self.vars["wavelength_max_nm"].set(f"{new_max:g}")
            except Exception:
                pass
            data = self._settings(); sticks = build_stick_spectrum(states, data["x_axis"]); curve = build_gaussian_broadened_spectrum(states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], data["x_axis"])
            if data["normalize"]: curve = normalize_spectrum(curve)
            plt.figure(figsize=(8, 5)); plt.vlines([x for x, _ in sticks], 0, [y for _, y in sticks], colors="#6b7280"); plt.plot([x for x, _ in curve], [y for _, y in curve], color="#1d4ed8"); plt.xlabel("Wavelength / nm" if data["x_axis"] == "nm" else "Energy / eV"); plt.ylabel("Oscillator strength / relative intensity"); plt.tight_layout(); plt.show()
        self._guard("Plot spectrum", action)
    def _export_spectrum(self):
        def action():
            states, data = self._need_states(), self._settings(); suggested = suggested_tddft_export_path(self.output_path, "uv-vis-spectrum", ".csv")
            path = filedialog.asksaveasfilename(parent=self, title="Export UV-Vis spectrum", defaultextension=".csv", initialdir=str(suggested.parent), initialfile=suggested.name, filetypes=[("CSV", "*.csv")]);
            if path:
                curve = build_gaussian_broadened_spectrum(states, data["broadening_ev"], data["wavelength_min_nm"], data["wavelength_max_nm"], data["x_axis"])
                if data["normalize"]: curve = normalize_spectrum(curve)
                export_spectrum_csv(path, build_stick_spectrum(states, data["x_axis"]), curve, data["x_axis"])
        self._guard("Export spectrum", action)
    def _save_plot(self, suffix):
        def action():
            states, data = self._need_states(), self._settings(); suggested = suggested_tddft_export_path(self.output_path, "uv-vis-spectrum", suffix)
            path = filedialog.asksaveasfilename(parent=self, title="Save UV-Vis spectrum image", defaultextension=suffix, initialdir=str(suggested.parent), initialfile=suggested.name, filetypes=[(suffix.upper()[1:], "*" + suffix)]);
            if path: save_spectrum(path, states, data)
        self._guard("Save spectrum", action)

    def _save_plot_image(self):
        def action():
            states, data = self._need_states(), self._settings()
            suggested = suggested_tddft_export_path(self.output_path, "uv-vis-spectrum", ".png")
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Save spectrum image",
                defaultextension=".png",
                initialdir=str(suggested.parent),
                initialfile=suggested.name,
                filetypes=[("PNG image", "*.png"), ("SVG vector image", "*.svg")],
            )
            if path:
                save_spectrum(path, states, data)
        self._guard("Save image", action)

    def _emission_module(self):
        try:
            from . import td_dft_emission_sequence as emission
        except ImportError:
            import td_dft_emission_sequence as emission  # type: ignore
        return emission

    def _prepare_emission_sequence_manifest(self, run_automatically: bool = False):
        if not self.output_path:
            raise ValueError("Load a completed absorption TD-DFT output first.")
        emission = self._emission_module()
        data = self._settings()
        settings = emission.EmissionSequenceSettings(
            source_output=self.output_path,
            target_root=int(data["root"]),
            target_manifold=str(data["target_manifold"]),
            td_method=str(data["td_method"]),
            follow_root=True,
            nroots=int(data["nroots"]),
            run_frequencies=False,
            broadening_ev=float(data["broadening_ev"]),
            wavelength_min_nm=float(data["wavelength_min_nm"]),
            wavelength_max_nm=float(data["wavelength_max_nm"]),
            normalize=bool(data["normalize"]),
            run_automatically=run_automatically,
        )
        manifest = emission.prepare_emission_sequence(settings)
        first_step = next((step for step in manifest.steps if step.step_id == "01_esopt"), None)
        directory = str(Path(first_step.input_path).parent if first_step and first_step.input_path else Path(self.output_path).parent)
        self.emission_directory = directory
        self.emission_status_var.set(
            "Prepared emission calculation sequence.\n"
            f"Directory: {directory}\n"
            f"Next input: {first_step.input_path if first_step else 'not available'}"
        )
        self.update_progress(100, "Emission calculation sequence prepared.", "darkgreen")
        return manifest

    def _prepare_emission_sequence(self):
        def action():
            manifest = self._prepare_emission_sequence_manifest(run_automatically=False)
            first_step = next((step for step in manifest.steps if step.step_id == "01_esopt"), None)
            directory = self.emission_directory or str(Path(self.output_path).parent)
            messagebox.showinfo(
                "Fluorescence emission",
                "Prepared the emission calculation sequence.\n\n"
                f"Directory:\n{directory}\n\n"
                "Run the sequence from the Builder to automate S1 optimization, vertical emission, and result export.",
                parent=self,
            )
        self._guard("Fluorescence emission", action)

    def _run_emission_sequence(self):
        def action():
            if not self.on_run_emission_sequence:
                raise ValueError("Automatic emission running is available only when TD-DFT is opened from ORCA Input Builder.")
            manifest = self._prepare_emission_sequence_manifest(run_automatically=True)
            if not self.emission_directory:
                raise ValueError("Emission sequence directory was not created.")
            self.on_run_emission_sequence(self.emission_directory)
            first_step = next((step for step in manifest.steps if step.step_id == "01_esopt"), None)
            self.emission_status_var.set(
                "Emission calculation sequence started in ORCA Input Builder.\n"
                f"Directory: {self.emission_directory}\n"
                f"Running: {first_step.input_path if first_step else '01_esopt'}"
            )
            self.update_progress(100, "Emission calculation sequence started.", "darkgreen")
        self._guard("Run emission sequence", action)

    def _open_emission_directory(self):
        def action():
            if not self.emission_directory and not self.output_path:
                raise ValueError("No emission directory is available yet.")
            directory = Path(self.emission_directory or Path(self.output_path).parent)
            directory.mkdir(parents=True, exist_ok=True)
            if os.name == "nt": os.startfile(str(directory))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(directory)], shell=False)
            else: subprocess.Popen(["xdg-open", str(directory)], shell=False)
        self._guard("Open emission directory", action)

    def _set_loaded_output(self, path):
        self._set_ui_mode("post")
        self.update_progress(10, "Reading ORCA TD-DFT output...")
        self.states, self.output_path = parse_orca_tddft_output(str(path)), str(Path(path).resolve())
        try:
            current_min = float(self.vars["wavelength_min_nm"].get())
            current_max = float(self.vars["wavelength_max_nm"].get())
            new_min, new_max = suggest_wavelength_range_for_states(self.states, current_min, current_max)
            if new_min != current_min or new_max != current_max:
                self.vars["wavelength_min_nm"].set(f"{new_min:g}")
                self.vars["wavelength_max_nm"].set(f"{new_max:g}")
        except Exception:
            pass
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
            suggested = suggested_tddft_export_path(self.output_path, self.mode_var.get(), ".png")
            path = filedialog.asksaveasfilename(parent=self, title="Save TD-DFT visualization", defaultextension=".png", initialdir=str(suggested.parent), initialfile=suggested.name, filetypes=[("PNG", "*.png")]);
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


def open_tddft_window(parent=None, initial_settings=None, on_apply=None, on_close=None, builder_context=None, on_run_emission_sequence=None) -> TDDFTWindow:
    """Open one Builder-connected TD-DFT ``Toplevel`` without creating a new Tk root."""
    if parent is None:
        raise ValueError("A Tk parent is required when embedding the TD-DFT window.")
    return TDDFTWindow(
        parent,
        initial_settings or DEFAULT_TDDFT_SETTINGS,
        on_apply=on_apply,
        on_close=on_close,
        builder_context=builder_context,
        on_run_emission_sequence=on_run_emission_sequence,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone CrystEngKit TD-DFT setup and UV-Vis analyzer")
    parser.add_argument("--output", "-o", help="ORCA .out file to load after startup")
    args = parser.parse_args(argv)
    root = tk.Tk()
    root.withdraw()
    install_dev_reload_shortcut(root, Path(__file__), argv=list(argv) if argv is not None else None)
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
