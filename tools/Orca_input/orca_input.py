
import math
import os
import base64
import importlib.util
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import json
import webbrowser

try:
    import numpy as np
except Exception:
    np = None

try:
    import pyvista as pv
except Exception:
    pv = None
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional, Tuple

try:
    import gemmi  # optional, preferred CIF parser
except Exception:
    gemmi = None

TOOLS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TOOLS_ROOT.parent
LAUNCHER_SETTINGS_PATH = Path(__file__).with_name("orca_gaussian_builder_settings.json")
DEFAULT_HOMO_LUMO_SCRIPT = TOOLS_ROOT / "HOMO_LUMO" / "HOMO_LUMO_v2.py"
DEFAULT_ESP_SCRIPT = TOOLS_ROOT / "VisMap_5.0" / "VisMap5.6_pyvista.py"
DEFAULT_NCI_SCRIPT = TOOLS_ROOT / "NCI_plot" / "nci_plotter.py"
DEFAULT_QTAIM_SCRIPT = TOOLS_ROOT / "qtaim-cp" / "qtaim.py"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
README_LINK_TEXT = "README section: ORCA Input Builder"


def wiki_url() -> str:
    return GITHUB_URL + "#orca-input-builder"
ICON_DIR = TOOLS_ROOT / "images"
ORCA_ICON_PATH = ICON_DIR / "tr_orca_icon.png"
HOMO_LUMO_ICON_PATH = ICON_DIR / "tr_homo_lumo_icon.png"
ESP_ICON_PATH = ICON_DIR / "tr_ESP_icon.png"
NCI_ICON_PATH = ICON_DIR / "tr_NCI_icon.png"
QTAIM_ICON_PATH = ICON_DIR / "qtaim.png"
BUILDER_ICON_ICO_PATH = ICON_DIR / "orca_builder.ico"
HARTREE_TO_KCAL_MOL = 627.509474
HARTREE_TO_KJ_MOL = 2625.49962
GNOME_ORCA_REJECTION_MARKERS = (
    "EVENT MANAGER",
    "PYATSPI",
    "DIST-PACKAGES/ORCA",
    "DIST-PACKAGES\\ORCA",
    "GNOME ORCA",
    "SCREEN READER",
    "ACCESSIBILITY",
)
ORCA_QM_IDENTITY_MARKERS = (
    "PROGRAM ORCA",
    "O   R   C   A",
    "ORCA VERSION",
    "ORCA_2AIM",
    "ORCA TERMINATED",
    "FACCTS",
    "FRANK NEESE",
    "MAX-PLANCK",
)


def _looks_like_gnome_orca(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in GNOME_ORCA_REJECTION_MARKERS)


def active_python_command() -> str:
    if sys.executable and os.path.isfile(sys.executable):
        return sys.executable
    return "python3" if os.name != "nt" else "python"


def subprocess_env_with_executable_dir(executable_path: str) -> Dict[str, str]:
    env = os.environ.copy()
    exe_dir = str(Path(executable_path).expanduser().resolve().parent)
    current_path = env.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    if exe_dir and exe_dir not in path_parts:
        env["PATH"] = exe_dir + (os.pathsep + current_path if current_path else "")
    return env


def validate_orca_qm_executable(path: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """Return whether path appears to be the ORCA quantum-chemistry executable."""
    candidate = Path(str(path).strip().strip('"')).expanduser()
    if not candidate.is_file():
        return False, "file does not exist"
    if candidate.name.lower() not in {"orca", "orca.exe"}:
        return False, "executable name is not orca/orca.exe"

    identity_text = f"{candidate}\n{candidate.resolve()}"
    if _looks_like_gnome_orca(identity_text):
        return False, "this appears to be Ubuntu GNOME Orca screen reader, not ORCA quantum chemistry"

    outputs: List[str] = []
    for args in ([str(candidate), "--version"], [str(candidate), "-v"], [str(candidate), "-h"], [str(candidate)]):
        try:
            result = subprocess.run(
                args,
                cwd=str(candidate.parent),
                env=subprocess_env_with_executable_dir(str(candidate)),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                errors="replace",
            )
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            if output:
                outputs.append(output[:4000])
        except subprocess.TimeoutExpired:
            continue
        except Exception as exc:
            outputs.append(f"{type(exc).__name__}: {exc}")

    combined = "\n".join(outputs)
    if _looks_like_gnome_orca(combined):
        return False, "this appears to be Ubuntu GNOME Orca screen reader, not ORCA quantum chemistry"
    upper = combined.upper()
    if any(marker in upper for marker in ORCA_QM_IDENTITY_MARKERS):
        return True, "valid ORCA QM executable"
    return False, "could not verify ORCA quantum-chemistry identity"


def active_interpreter_dependency_report() -> Tuple[List[str], str]:
    checks = [
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
        ("pyvista", "pyvista"),
        ("periodictable", "periodictable"),
        ("gemmi", "gemmi"),
        ("Pillow", "PIL"),
    ]
    missing = [package for package, import_name in checks if importlib.util.find_spec(import_name) is None]
    if not missing:
        return [], "Python dependencies OK for active interpreter."
    pip_line = f"{sys.executable} -m pip install --user numpy matplotlib pyvista periodictable gemmi pillow"
    apt_line = "sudo apt update && sudo apt install python-is-python3 python3-pip python3-numpy python3-matplotlib python3-tk"
    message = (
        "Missing Python packages for the active interpreter: "
        + ", ".join(missing)
        + "\nInstall with:\n"
        + pip_line
    )
    if os.name != "nt":
        message += "\nUbuntu apt option:\n" + apt_line
    return missing, message


def validate_orca_output_file(out_path: str) -> Tuple[bool, str]:
    path = Path(str(out_path))
    if not path.is_file():
        return False, "output file was not created"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return False, f"output file could not be read: {exc}"
    upper = text.upper()
    if _looks_like_gnome_orca(text):
        return False, "output appears to come from Ubuntu GNOME Orca screen reader, not ORCA QM"
    if "ORCA TERMINATED NORMALLY" not in upper:
        return False, "ORCA did not terminate normally"
    identity_hits = ("PROGRAM ORCA", "O   R   C   A", "ORCA VERSION", "ORCA TERMINATED NORMALLY")
    if not any(marker in upper for marker in identity_hits):
        return False, "output does not look like an ORCA quantum-chemistry output"
    return True, "valid completed ORCA output"


def app_relative_path(path: str) -> str:
    """Store repo-owned paths relative to APP_ROOT so settings travel between machines."""
    if not path:
        return ""
    try:
        resolved = Path(path).expanduser().resolve()
        return resolved.relative_to(APP_ROOT).as_posix()
    except Exception:
        return str(path)


def resolve_app_path(value: object, default: Path) -> Path:
    """Resolve settings paths from the fixed repository layout, not from local disk names."""
    if not value:
        return default

    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return default

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    if candidate.is_file():
        return candidate

    legacy_candidate = TOOLS_ROOT / candidate.name if candidate.parent == APP_ROOT else None
    if legacy_candidate and legacy_candidate.is_file():
        return legacy_candidate

    if not Path(raw).is_absolute():
        legacy_tool_candidate = TOOLS_ROOT / Path(raw)
        if legacy_tool_candidate.is_file():
            return legacy_tool_candidate

    normalized = raw.replace("\\", "/")
    marker = "/crystengkit-orca/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        candidate = APP_ROOT / Path(suffix)
        if candidate.is_file():
            return candidate

    for tool_name in ("HOMO_LUMO", "VisMap_5.0", "NCI_plot", "NCI_QTAIM_overlay", "qtaim-cp"):
        marker = f"/{tool_name}/"
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1]
            candidate = TOOLS_ROOT / tool_name / Path(suffix)
            if candidate.is_file():
                return candidate

    return default


def configure_pyvista_defaults(pv_module, plotter, background="white", parallel_projection=True, antialiasing="msaa", extent=1.0):
    """Apply the default PyVista viewer quality/lighting used by 3Dview.py."""
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
        try:
            plotter.set_background("white")
        except Exception:
            pass

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


def bring_window_title_to_front(title: str):
    """Bring a newly-created native window to the foreground on Windows."""
    if os.name != "nt" or not title:
        return

    def _raise_when_created():
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd_topmost = -1
            hwnd_notopmost = -2
            sw_show = 5
            swp_flags = 0x0001 | 0x0002 | 0x0040  # NOSIZE | NOMOVE | SHOWWINDOW

            for _ in range(20):
                hwnd = user32.FindWindowW(None, title)
                if hwnd:
                    user32.ShowWindow(hwnd, sw_show)
                    user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_flags)
                    user32.SetForegroundWindow(hwnd)
                    time.sleep(0.15)
                    user32.SetWindowPos(hwnd, hwnd_notopmost, 0, 0, 0, 0, swp_flags)
                    return
                time.sleep(0.1)
        except Exception:
            pass

    threading.Thread(target=_raise_when_created, daemon=True).start()


def default_python312_command() -> str:
    return default_python39plus_command()


def default_esp_python_command() -> str:
    if sys.executable and os.path.isfile(sys.executable):
        return sys.executable
    return default_python312_command()


def default_nci_python_command() -> str:
    return default_python39plus_command()


def default_python39plus_command() -> str:
    if sys.version_info >= (3, 9) and sys.executable and os.path.isfile(sys.executable):
        return sys.executable

    candidates = find_python39plus_candidates()
    if candidates:
        return candidates[0]

    return active_python_command()


def default_qtaim_python_command() -> str:
    return default_python39plus_command()


def python_version_tuple(executable: Path) -> Optional[Tuple[int, int, int]]:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=4,
            shell=False,
        )
    except Exception:
        return None

    text = (result.stdout or result.stderr or "").strip()
    match = re.search(r"Python\s+(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def python_path_rank(executable: Path) -> int:
    """Prefer real Python installs over launch aliases, shims, and project-local paths."""
    text = str(executable).replace("\\", "/").lower()
    name = executable.name.lower()

    if "windowsapps" in text:
        return -100
    if name in {"py.exe", "py"}:
        return -50
    if "/.pyenv/shims/" in text or "/.asdf/shims/" in text:
        return 5
    if "conda" in text or "anaconda" in text or "miniconda" in text:
        return 20
    if str(APP_ROOT).replace("\\", "/").lower() in text:
        return 25
    if os.name == "nt":
        if re.search(r"/python3\d+/python\.exe$", text):
            return 100
        if "/appdata/local/programs/python/python" in text:
            return 95
        if "/program files/python" in text:
            return 90
    else:
        if text.startswith("/usr/local/") or text.startswith("/opt/homebrew/"):
            return 100
        if text.startswith("/usr/"):
            return 90

    return 50


def find_python39plus_candidates() -> List[str]:
    candidates: List[Path] = []

    if sys.executable and os.path.isfile(sys.executable):
        candidates.append(Path(sys.executable))

    version_names = [
        "python3.13",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3.9",
        "python3",
        "python",
    ]

    if os.name == "nt":
        version_names = [
            "python.exe",
            "python3.exe",
            "python3.13.exe",
            "python3.12.exe",
            "python3.11.exe",
            "python3.10.exe",
            "python3.9.exe",
        ] + version_names

    for name in version_names:
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    if os.name == "nt":
        local_programs = Path.home() / "AppData" / "Local" / "Programs" / "Python"
        for version in ("Python313", "Python312", "Python311", "Python310", "Python39"):
            candidates.append(local_programs / version / "python.exe")

        for candidate in (
            Path("C:/Python313/python.exe"),
            Path("C:/Python312/python.exe"),
            Path("C:/Python311/python.exe"),
            Path("C:/Python310/python.exe"),
            Path("C:/Python39/python.exe"),
        ):
            candidates.append(candidate)
    else:
        for directory in (
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
            Path("/opt/local/bin"),
            Path.home() / ".pyenv" / "shims",
            Path.home() / ".asdf" / "shims",
            Path.home() / "miniconda3" / "bin",
            Path.home() / "anaconda3" / "bin",
        ):
            for name in version_names:
                candidates.append(directory / name)

    valid: List[Tuple[Tuple[int, int, int], int, str]] = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved).lower()
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        rank = python_path_rank(resolved)
        if rank < 0:
            continue
        version = python_version_tuple(resolved)
        if version and version >= (3, 9, 0):
            valid.append((version, rank, str(resolved)))

    valid.sort(key=lambda item: (item[0], item[1], item[2].lower()), reverse=True)
    return [path for _version, _rank, path in valid]


def latest_python39plus_command() -> str:
    if sys.version_info >= (3, 9) and sys.executable and os.path.isfile(sys.executable):
        return sys.executable
    candidates = find_python39plus_candidates()
    if not candidates:
        return default_python39plus_command()
    return candidates[0]


def open_path_in_system(path: str):
    if os.name == "nt":
        os.startfile(path)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", path], shell=False)
        return
    subprocess.Popen(["xdg-open", path], shell=False)


def executable_filetypes(label: str = "Executable files"):
    if os.name == "nt":
        return [(label, "*.exe"), ("All files", "*.*")]
    return [(label, "*"), ("All files", "*.*")]


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


ELEMENT_SYMBOLS = (
    "H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar",
    "K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr",
    "Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe",
    "Cs","Ba","La","Ce","Pr","Nd","Pm","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu",
    "Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn","Fr","Ra","Ac",
    "Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr","Rf","Db","Sg","Bh",
    "Hs","Mt","Ds","Rg","Cn","Nh","Fl","Mc","Lv","Ts","Og"
)
PERIODIC_TABLE = set(ELEMENT_SYMBOLS)
ATOMIC_NUMBERS = {sym: idx + 1 for idx, sym in enumerate(ELEMENT_SYMBOLS)}

ORCA_FUNCTIONALS = sorted({
    "HF","BP86","BLYP","PBE","PBE0","B3LYP","B3LYP/G","TPSSh","TPSS0","TPSS","M06L","M06","M062X",
    "B97M-V","B97M-D3BJ","B97M-D4","SCANfunc","r2SCAN","r2SCANh","r2SCAN0","CAM-B3LYP","LC-BLYP",
    "LC-PBE","wB97","wB97X","wB97X-D3","wB97X-D4","wB97X-V","wB97M-V","PW6B95","B2PLYP",
    "HF-3c","B97-3c","r2SCAN-3c","PBEh-3c","wB97X-3c"
})
GAUSSIAN_FUNCTIONALS = sorted({
    "HF","B3LYP","BP86","BLYP","PBEPBE","PBE1PBE","PBE0","TPSSTPSS","M06L","M06","M062X",
    "CAM-B3LYP","LC-wPBE","wB97XD","B2PLYP"
})

ORCA_BASIS = sorted({
    "STO-3G","3-21G","6-31G","6-31G(d)","6-31G(d,p)","6-31+G(d,p)","6-311G","6-311G(d,p)",
    "6-311+G(d,p)","SVP","TZVP","TZVPP","QZVP","QZVPP",
    "def2-SVP","def2-SV(P)","def2-TZVP","def2-TZVP(-f)","def2-TZVPP","def2-QZVP","def2-QZVPP",
    "ma-def2-SVP","ma-def2-TZVP","ma-def2-TZVPP","def2-SVPD","def2-TZVPD","def2-TZVPPD",
    "cc-pVDZ","cc-pVTZ","cc-pVQZ","aug-cc-pVDZ","aug-cc-pVTZ","aug-cc-pVQZ",
    "x2c-SVPall","x2c-TZVPall","x2c-TZVPPall","SARC-DKH-TZVP","SARC-DKH-TZVPP",
    "SARC-ZORA-TZVP","SARC-ZORA-TZVPP","MINIX","vDZP","pc-1","pc-2","pcseg-1","pcseg-2"
})
GAUSSIAN_BASIS = sorted({
    "STO-3G","3-21G","6-31G","6-31G(d)","6-31G(d,p)","6-31+G(d,p)","6-311G","6-311G(d,p)",
    "6-311+G(d,p)","6-311++G(d,p)","cc-pVDZ","cc-pVTZ","cc-pVQZ","aug-cc-pVDZ","aug-cc-pVTZ",
    "aug-cc-pVQZ","def2SVP","def2TZVP","def2TZVPP","Def2SVP","Def2TZVP","Def2TZVPP","LanL2DZ",
    "SDD","Gen","GenECP"
})

DISPERSION_OPTIONS = ["", "D3BJ", "D4"]

ORCA_SMD_SOLVENT_NAMES = {
    '1,1,1-trichloroethane',
    '1,1,2-trichloroethane',
    '1,2,4-trimethylbenzene',
    '1,2-dibromoethane',
    '1,2-dichloroethane',
    '1,2-ethanediol',
    '1,4-dioxane',
    '1-bromo-2-methylpropane',
    '1-bromooctane',
    '1-bromopentane',
    '1-bromopropane',
    '1-butanol',
    '1-chlorohexane',
    '1-chloropentane',
    '1-chloropropane',
    '1-decanol',
    '1-fluorooctane',
    '1-heptanol',
    '1-hexanol',
    '1-hexene',
    '1-hexyne',
    '1-iodobutane',
    '1-iodohexadecane',
    '1-iodopentane',
    '1-iodopropane',
    '1-nitropropane',
    '1-nonanol',
    '1-octanol',
    '1-pentanol',
    '1-pentene',
    '1-propanol',
    '2,2,2-trifluoroethanol',
    '2,2,4-trimethylpentane',
    '2,4-dimethylpentane',
    '2,4-dimethylpyridine',
    '2,6-dimethylpyridine',
    '2-bromopropane',
    '2-butanol',
    '2-chlorobutane',
    '2-heptanone',
    '2-hexanone',
    '2-methoxyethanol',
    '2-methyl-1-propanol',
    '2-methyl-2-propanol',
    '2-methylpentane',
    '2-methylpyridine',
    '2-nitropropane',
    '2-octanone',
    '2-pentanone',
    '2-propanol',
    '2-propen-1-ol',
    '2methylpyridine',
    '3-methylpyridine',
    '3-pentanone',
    '4-heptanone',
    '4-methyl-2-pentanone',
    '4-methylpyridine',
    '4methyl2pentanone',
    '5-nonanone',
    'a-chlorotoluene',
    'acetic acid',
    'aceticacid',
    'acetone',
    'acetonitrile',
    'acetophenone',
    'ammonia',
    'aniline',
    'anisole',
    'benzaldehyde',
    'benzene',
    'benzonitrile',
    'benzyl alcohol',
    'benzylalcohol',
    'bromobenzene',
    'bromoethane',
    'bromoform',
    'bromooctane',
    'butanal',
    'butanoic acid',
    'butanol',
    'butanone',
    'butanonitrile',
    'butyl acetate',
    'butyl ethanoate',
    'butylacetate',
    'butylamine',
    'butylbenzene',
    'c2cl4',
    'carbon disulfide',
    'carbon tetrachloride',
    'carbondisulfide',
    'ccl4',
    'ch2cl2',
    'ch3cn',
    'chcl3',
    'chlorobenzene',
    'chloroform',
    'chlorohexane',
    'cis-1,2-dimethylcyclohexane',
    'cis-decalin',
    'conductor',
    'cs2',
    'cyclohexane',
    'cyclohexanone',
    'cyclopentane',
    'cyclopentanol',
    'dcm',
    'decane',
    'decanol',
    'dibromomethane',
    'dibutylether',
    'dichloromethane',
    'diethyl ether',
    'diethyl sulfide',
    'diethylamine',
    'diethylether',
    'diiodomethane',
    'diisopropyl ether',
    'diisopropylether',
    'dimethyl disulfide',
    'dimethylacetamide',
    'dimethylformamide',
    'dimethylsulfoxide',
    'dioxane',
    'diphenylether',
    'dipropylamine',
    'dmf',
    'dmso',
    'dodecane',
    'e-1,2-dichloroethene',
    'e-2-pentene',
    'ethanethiol',
    'ethanoate',
    'ethanol',
    'ethoxybenzene',
    'ethyl acetate',
    'ethyl methanoate',
    'ethyl phenyl ether',
    'ethylacetate',
    'ethylbenzene',
    'fluorobenzene',
    'formamide',
    'formic acid',
    'furan',
    'furane',
    'h2o',
    'heptane',
    'heptanol',
    'hexadecane',
    'hexadecyliodide',
    'hexafluorobenzene',
    'hexane',
    'hexanoic acid',
    'hexanol',
    'iodobenzene',
    'iodoethane',
    'iodomethane',
    'isobutanol',
    'isooctane',
    'isopropanol',
    'isopropylbenzene',
    'isopropyltoluene',
    'm-cresol',
    'm-xylene',
    'mcresol',
    'mecn',
    'meno2',
    'mesitylene',
    'methanol',
    'methoxyethanol',
    'methyl benzoate',
    'methyl butanoate',
    'methyl ethanoate',
    'methyl methanoate',
    'methyl propanoate',
    'methylcyclohexane',
    'methylformamide',
    'n,n-dimethylacetamide',
    'n,n-dimethylformamide',
    'n-butylbenzene',
    'n-decane',
    'n-dodecane',
    'n-heptane',
    'n-hexadecane',
    'n-hexane',
    'n-methylaniline',
    'n-methylformamide',
    'n-nonane',
    'n-octane',
    'n-pentadecane',
    'n-pentane',
    'n-undecane',
    'nitrobenzene',
    'nitroethane',
    'nitromethane',
    'nonane',
    'nonanol',
    'o-chlorotoluene',
    'o-cresol',
    'o-dichlorobenzene',
    'o-nitrotoluene',
    'o-xylene',
    'octane',
    'octanol',
    'octanol(wet)',
    'odichlorobenzene',
    'onitrotoluene',
    'p-isopropyltoluene',
    'p-xylene',
    'pentadecane',
    'pentanal',
    'pentane',
    'pentanoic acid',
    'pentanol',
    'pentyl ethanoate',
    'pentylamine',
    'perfluorobenzene',
    'phenol',
    'phno2',
    'propanal',
    'propanoic acid',
    'propanol',
    'propanonitrile',
    'propyl ethanoate',
    'propylamine',
    'pyridine',
    'sec-butylbenzene',
    'secbutanol',
    'secbutylbenzene',
    'sulfolane',
    'tbutylbenzene',
    'tert-butylbenzene',
    'tetrachloroethene',
    'tetrahydrofuran',
    'tetrahydrothiophene-s,s-dioxide',
    'tetrahydrothiophenedioxide',
    'tetralin',
    'thf',
    'thiophene',
    'thiophenol',
    'toluene',
    'trans-decalin',
    'tributylphosphate',
    'trichloroethene',
    'triethylamine',
    'undecane',
    'water',
    'wetoctanol',
    'woctanol',
    'xylene',
    'z-1,2-dichloroethene',
}

SOLVENT_LIBRARY: Dict[str, Dict[str, object]] = {
    "water": {"label": "Water", "formula": "H2O", "orca": "WATER", "gaussian": "Water", "aliases": ["h2o", "water"]},
    "acetonitrile": {"label": "Acetonitrile", "formula": "CH3CN", "orca": "ACETONITRILE", "gaussian": "Acetonitrile", "aliases": ["acetonitrile", "mecn", "ch3cn"]},
    "methanol": {"label": "Methanol", "formula": "CH3OH", "orca": "METHANOL", "gaussian": "Methanol", "aliases": ["methanol", "meoh", "ch3oh"]},
    "ethanol": {"label": "Ethanol", "formula": "C2H5OH", "orca": "ETHANOL", "gaussian": "Ethanol", "aliases": ["ethanol", "etoh", "c2h5oh"]},
    "chloroform": {"label": "Chloroform", "formula": "CHCl3", "orca": "CHLOROFORM", "gaussian": "Chloroform", "aliases": ["chloroform", "chcl3"]},
    "dichloromethane": {"label": "Dichloromethane", "formula": "CH2Cl2", "orca": "DICHLOROMETHANE", "gaussian": "Dichloromethane", "aliases": ["dichloromethane", "dcm", "ch2cl2", "methylene chloride"]},
    "tetrahydrofuran": {"label": "Tetrahydrofuran", "formula": "C4H8O", "orca": "TETRAHYDROFURAN", "gaussian": "TetraHydroFuran", "aliases": ["tetrahydrofuran", "thf", "c4h8o"]},
    "dmso": {"label": "DMSO", "formula": "(CH3)2SO", "orca": "DMSO", "gaussian": "DMSO", "aliases": ["dmso", "(ch3)2so", "dimethyl sulfoxide"]},
    "dmf": {"label": "DMF", "formula": "HCON(CH3)2", "orca": "DMF", "gaussian": "DMF", "aliases": ["dmf", "dimethylformamide", "hcon(ch3)2"]},
    "toluene": {"label": "Toluene", "formula": "C6H5CH3", "orca": "TOLUENE", "gaussian": "Toluene", "aliases": ["toluene", "c7h8", "phme"]},
    "hexane": {"label": "n-Hexane", "formula": "C6H14", "orca": "N-HEXANE", "gaussian": "n-Hexane", "aliases": ["hexane", "n-hexane", "c6h14"]},
    "benzene": {"label": "Benzene", "formula": "C6H6", "orca": "BENZENE", "gaussian": "Benzene", "aliases": ["benzene", "c6h6"]},
    "acetone": {"label": "Acetone", "formula": "(CH3)2CO", "orca": "ACETONE", "gaussian": "Acetone", "aliases": ["acetone", "propanone", "c3h6o"]},
    "diethyl ether": {"label": "Diethyl ether", "formula": "C2H5OC2H5", "orca": "DIETHYLETHER", "gaussian": "DiethylEther", "aliases": ["diethyl ether", "ether", "et2o", "c4h10o"]},
}


def normalize_text(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.strip().lower())

ORCA_SMD_SOLVENT_NORMALIZED = {normalize_text(name) for name in ORCA_SMD_SOLVENT_NAMES}


def solvent_display_name(canonical: str, data: Dict[str, object]) -> str:
    label = str(data.get("label") or canonical.title())
    formula = str(data.get("formula") or "").strip()
    return f"{label} ({formula})" if formula else label

KNOWN_SOLVENT_ALIAS_MAP = {
    normalize_text(canonical): canonical
    for canonical in SOLVENT_LIBRARY
}
for canonical, data in SOLVENT_LIBRARY.items():
    for alias in data.get("aliases", []):
        KNOWN_SOLVENT_ALIAS_MAP[normalize_text(str(alias))] = canonical
    KNOWN_SOLVENT_ALIAS_MAP[normalize_text(solvent_display_name(canonical, data))] = canonical
    KNOWN_SOLVENT_ALIAS_MAP[normalize_text(str(data.get("label", "")))] = canonical
    KNOWN_SOLVENT_ALIAS_MAP[normalize_text(str(data.get("formula", "")))] = canonical


def resolve_solvent(user_text: str) -> Optional[Dict[str, str]]:
    key = normalize_text(user_text)
    if not key:
        return None
    if key not in ORCA_SMD_SOLVENT_NORMALIZED:
        return None
    canonical = KNOWN_SOLVENT_ALIAS_MAP.get(key)
    if canonical is not None:
        data = SOLVENT_LIBRARY[canonical]
        return {"canonical": canonical, "orca": str(data["orca"]), "gaussian": str(data["gaussian"])}
    normalized_text = user_text.strip()
    return {"canonical": normalized_text, "orca": normalized_text, "gaussian": normalized_text}


def clean_symbol(raw: str) -> str:
    raw = raw.strip().strip('"').strip("'")
    raw = re.sub(r"[^A-Za-z]", "", raw)
    if not raw:
        raise ValueError("Empty atom symbol encountered.")
    sym = raw[0].upper() + raw[1:].lower() if len(raw) > 1 else raw.upper()
    if sym not in PERIODIC_TABLE:
        raise ValueError(f"Unknown element symbol: {raw}")
    return sym


def cif_unquote(value: str) -> str:
    value = value.strip()
    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
        return value[1:-1]
    return value


def strip_cif_esd(value: str) -> str:
    return re.sub(r"\([^)]*\)", "", cif_unquote(value)).strip()


class Structure:
    def __init__(self, atoms: List[Tuple[str, float, float, float]], title: str = "Generated"):
        if not atoms:
            raise ValueError("No atoms found.")
        self.atoms = atoms
        self.title = title

    def xyz_block(self) -> str:
        return "\n".join(f"{sym:<2} {x: .8f} {y: .8f} {z: .8f}" for sym, x, y, z in self.atoms)


COVALENT_RADII = {
    "H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39, "Si": 1.11,
    "Pd": 1.39, "Pt": 1.36, "Ru": 1.46, "Rh": 1.42, "Ir": 1.41,
    "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
    "Ag": 1.45, "Au": 1.36, "Hg": 1.32, "Li": 1.28, "Na": 1.66, "K": 2.03,
    "Mg": 1.41, "Ca": 1.76, "Al": 1.21, "Sn": 1.39, "Pb": 1.46,
    "Se": 1.20, "Te": 1.38, "Cd": 1.44, "Ga": 1.22, "Ge": 1.20, "As": 1.19,
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


def get_atom_color(symbol: str) -> Tuple[int, int, int]:
    hex_color = ATOM_COLORS.get(symbol, "#B0B0B0").lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def covalent_radius(symbol: str) -> float:
    return COVALENT_RADII.get(symbol, 0.77)


def display_atom_radius(symbol: str) -> float:
    return float(np.clip(covalent_radius(symbol) * 0.42, 0.16, 0.55))


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


def cylinder_between(pv_module, p1, p2, radius=0.075, resolution=48):
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


def add_ball_and_stick_atom(pv_module, plotter, symbol, point, color=None, name=None):
    sphere = pv_module.Sphere(
        radius=display_atom_radius(symbol),
        center=tuple(float(x) for x in point),
        theta_resolution=64,
        phi_resolution=64,
    )
    return add_mesh_safe(
        plotter,
        sphere,
        color=color if color is not None else ATOM_COLORS.get(symbol, "#FF69B4"),
        name=name,
        **molecule_material_parameters(),
    )


def add_split_colored_bond(pv_module, plotter, p1, p2, color1, color2):
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    midpoint = (p1 + p2) / 2.0
    for a, b, color in ((p1, midpoint, color1), (midpoint, p2, color2)):
        cylinder = cylinder_between(pv_module, a, b)
        if cylinder is not None:
            add_mesh_safe(plotter, cylinder, color=color, **molecule_material_parameters())


def distance(a: Tuple[str, float, float, float], b: Tuple[str, float, float, float]) -> float:
    return math.sqrt((a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2 + (a[3] - b[3]) ** 2)


def infer_bonds(structure: Structure, scale: float = 1.20) -> List[Tuple[int, int]]:
    bonds: List[Tuple[int, int]] = []
    atoms = structure.atoms
    for i in range(len(atoms)):
        sym_i = atoms[i][0]
        ri = covalent_radius(sym_i)
        for j in range(i + 1, len(atoms)):
            sym_j = atoms[j][0]
            rj = covalent_radius(sym_j)
            d = distance(atoms[i], atoms[j])
            cutoff = scale * (ri + rj)
            if d <= cutoff:
                bonds.append((i, j))
    return bonds


def connected_components(n_atoms: int, bonds: List[Tuple[int, int]]) -> List[List[int]]:
    adj = [[] for _ in range(n_atoms)]
    for i, j in bonds:
        adj[i].append(j)
        adj[j].append(i)
    seen = [False] * n_atoms
    comps: List[List[int]] = []
    for start in range(n_atoms):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp: List[int] = []
        while stack:
            node = stack.pop()
            comp.append(node)
            for nb in adj[node]:
                if not seen[nb]:
                    seen[nb] = True
                    stack.append(nb)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), c[0]))
    return comps


def atom_ranges_text(indices: List[int]) -> str:
    if not indices:
        return ""
    sorted_idx = sorted(indices)
    ranges = []
    start = prev = sorted_idx[0] + 1
    for idx0 in sorted_idx[1:]:
        idx = idx0 + 1
        if idx == prev + 1:
            prev = idx
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = idx
    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ", ".join(ranges)


def formula_for_indices(structure: Structure, indices: List[int]) -> str:
    counts: Dict[str, int] = {}
    for idx in indices:
        sym = structure.atoms[idx][0]
        counts[sym] = counts.get(sym, 0) + 1

    def sort_key(sym: str):
        if sym == "C":
            return (0, sym)
        if sym == "H":
            return (1, sym)
        return (2, sym)

    parts = []
    for sym in sorted(counts, key=sort_key):
        n = counts[sym]
        parts.append(sym if n == 1 else f"{sym}{n}")
    return "".join(parts)


def electron_count_for_indices(structure: Structure, indices: List[int], charge: int) -> int:
    electrons = 0
    for idx in indices:
        sym = structure.atoms[idx][0].rstrip(":")
        if sym not in ATOMIC_NUMBERS:
            raise ValueError(f"Unknown element symbol for electron count: {sym}")
        electrons += ATOMIC_NUMBERS[sym]
    return electrons - charge


def validate_charge_multiplicity_parity(label: str, electrons: int, multiplicity: int) -> List[str]:
    errors: List[str] = []
    if multiplicity < 1:
        errors.append(f"{label}: multiplicity must be >= 1.")
        return errors
    if electrons < 0:
        errors.append(f"{label}: electron count is negative after applying charge.")
        return errors
    if (electrons % 2) != ((multiplicity - 1) % 2):
        errors.append(
            f"{label}: charge/multiplicity parity is inconsistent "
            f"({electrons} electrons with multiplicity {multiplicity})."
        )
    if electrons == 0 and multiplicity != 1:
        errors.append(f"{label}: zero-electron species must be singlet.")
    elif multiplicity > electrons + 1:
        errors.append(f"{label}: multiplicity {multiplicity} is impossible for {electrons} electrons.")
    return errors


def spin_coupling_warning(dimer_mult: int, a_mult: int, b_mult: int) -> Optional[str]:
    d_dimer = dimer_mult - 1
    d_a = a_mult - 1
    d_b = b_mult - 1
    if d_dimer < abs(d_a - d_b) or d_dimer > d_a + d_b or (d_dimer - d_a - d_b) % 2:
        return (
            "Dimer multiplicity is not obtainable by simple spin coupling of fragment multiplicities "
            f"(A={a_mult}, B={b_mult}, dimer={dimer_mult}). Check fragment spin states."
        )
    return None


def subset_structure(structure: Structure, indices: List[int], ghost_indices: Optional[List[int]] = None) -> Structure:
    ghost_set = set(ghost_indices or [])
    atoms: List[Tuple[str, float, float, float]] = []
    for idx in indices:
        sym, x, y, z = structure.atoms[idx]
        if idx in ghost_set:
            sym = sym + ":"
        atoms.append((sym, x, y, z))
    return Structure(atoms, title=structure.title)


def xyz_block_from_atoms(atoms: List[Tuple[str, float, float, float]]) -> str:
    return "\n".join(f"{sym:<2} {x: .8f} {y: .8f} {z: .8f}" for sym, x, y, z in atoms)


def fractional_to_cartesian(fx, fy, fz, a, b, c, alpha_deg, beta_deg, gamma_deg):
    alpha = math.radians(alpha_deg)
    beta = math.radians(beta_deg)
    gamma = math.radians(gamma_deg)

    cos_a, cos_b, cos_g = math.cos(alpha), math.cos(beta), math.cos(gamma)
    sin_g = math.sin(gamma)
    if abs(sin_g) < 1e-12:
        raise ValueError("Invalid unit cell: sin(gamma)=0")

    ax, ay, az = a, 0.0, 0.0
    bx, by, bz = b * cos_g, b * sin_g, 0.0
    cx = c * cos_b
    cy = c * (cos_a - cos_b * cos_g) / sin_g
    cz_sq = c * c - cx * cx - cy * cy
    if cz_sq < -1e-8:
        raise ValueError("Invalid unit-cell parameters.")
    cz = math.sqrt(max(cz_sq, 0.0))
    x = fx * ax + fy * bx + fz * cx
    y = fx * ay + fy * by + fz * cy
    z = fx * az + fy * bz + fz * cz
    return x, y, z


class StructureParser:
    @staticmethod
    def parse(path: str) -> Structure:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".xyz":
            return StructureParser.parse_xyz(path)
        if ext == ".cif":
            if gemmi is not None:
                try:
                    return StructureParser.parse_cif_gemmi(path)
                except Exception:
                    pass
            return StructureParser.parse_cif_fallback(path)
        if ext == ".inp":
            return StructureParser.parse_orca_input(path)
        raise ValueError("Supported input files: .xyz, .cif, or ORCA .inp")

    @staticmethod
    def parse_xyz(path: str) -> Structure:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            raise ValueError("XYZ file is empty.")
        if len(lines) < 1:
            raise ValueError("XYZ file is too short.")

        atoms = []
        def looks_like_atom_line(line: str) -> bool:
            parts = line.split()
            if len(parts) < 4:
                return False
            try:
                float(parts[1])
                float(parts[2])
                float(parts[3])
            except ValueError:
                return False
            return True

        try:
            n = int(lines[0].strip())
        except Exception as exc:
            n = None
            atom_lines = lines
        else:
            start = 1 if len(lines) > 1 and looks_like_atom_line(lines[1]) else 2
            atom_lines = lines[start:start + n]
            if len(atom_lines) < n:
                raise ValueError("XYZ file has fewer atom lines than declared.")

        for line in atom_lines:
            parts = line.split()
            if len(parts) < 4:
                if n is None:
                    continue
                raise ValueError(f"Invalid XYZ atom line: {line}")
            try:
                atoms.append((clean_symbol(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError as exc:
                if n is None:
                    continue
                raise ValueError(f"Invalid XYZ atom line: {line}") from exc

        if not atoms:
            raise ValueError("No valid atom coordinates were found.")
        if n is not None and len(atoms) != n:
            raise ValueError(f"XYZ header says {n} atoms, but {len(atoms)} coordinate lines were parsed.")

        title = lines[1].strip() if n is not None and len(lines) > 1 and not looks_like_atom_line(lines[1]) else os.path.basename(path)
        return Structure(atoms, title=title or os.path.basename(path))

    @staticmethod
    def parse_orca_input(path: str) -> Structure:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\n") for line in f]

        atoms = []
        in_xyz_block = False
        for raw in lines:
            stripped = raw.strip()
            lower = stripped.lower()
            if not in_xyz_block:
                if lower.startswith("* xyz "):
                    in_xyz_block = True
                continue

            if stripped == "*":
                break
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 4:
                continue
            try:
                atoms.append((clean_symbol(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))
            except Exception as exc:
                raise ValueError(f"Invalid ORCA xyz atom line: {raw}") from exc

        if not atoms:
            raise ValueError('No embedded ORCA "* xyz charge multiplicity" coordinate block was found.')
        return Structure(atoms, title=f"{os.path.basename(path)} (ORCA input)")

    @staticmethod
    def parse_orca_output_final_geometry(path: str) -> Structure:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\n") for line in f]

        joined = "\n".join(lines).upper()
        if "ORCA TERMINATED NORMALLY" not in joined:
            raise ValueError("The ORCA output is not finished normally yet.")

        last_atoms: List[Tuple[str, float, float, float]] = []
        idx = 0
        while idx < len(lines):
            if "CARTESIAN COORDINATES (ANGSTROEM)" not in lines[idx].upper():
                idx += 1
                continue
            atoms: List[Tuple[str, float, float, float]] = []
            j = idx + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:
                    if atoms:
                        break
                    j += 1
                    continue
                if set(stripped) <= {"-", " "}:
                    j += 1
                    continue
                parts = stripped.split()
                if len(parts) >= 4:
                    try:
                        atoms.append((clean_symbol(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))
                        j += 1
                        continue
                    except Exception:
                        if atoms:
                            break
                elif atoms:
                    break
                j += 1
            if atoms:
                last_atoms = atoms
            idx = j

        if not last_atoms:
            raise ValueError("No final ORCA Cartesian coordinate block was found in the output file.")
        return Structure(last_atoms, title=f"{os.path.basename(path)} (final ORCA geometry)")

    @staticmethod
    def parse_cif_gemmi(path: str) -> Structure:
        doc = gemmi.cif.read_file(path)
        block = doc.sole_block()
        st = gemmi.make_small_structure_from_block(block)
        atoms = []
        for site in st.sites:
            pos = st.cell.orthogonalize(site.fract)
            atoms.append((clean_symbol(site.element.name), float(pos.x), float(pos.y), float(pos.z)))
        if not atoms:
            raise ValueError("No atoms extracted from CIF.")
        return Structure(atoms, title=f"{os.path.basename(path)} (gemmi)")

    @staticmethod
    def parse_cif_fallback(path: str) -> Structure:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\n") for line in f]

        cell_keys = {
            "_cell_length_a": None,
            "_cell_length_b": None,
            "_cell_length_c": None,
            "_cell_angle_alpha": None,
            "_cell_angle_beta": None,
            "_cell_angle_gamma": None,
        }
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split(None, 1)
            if len(parts) == 2 and parts[0] in cell_keys:
                cell_keys[parts[0]] = float(strip_cif_esd(parts[1]))
        cell = None
        if all(v is not None for v in cell_keys.values()):
            cell = (
                cell_keys["_cell_length_a"], cell_keys["_cell_length_b"], cell_keys["_cell_length_c"],
                cell_keys["_cell_angle_alpha"], cell_keys["_cell_angle_beta"], cell_keys["_cell_angle_gamma"]
            )

        tables = StructureParser._read_cif_tables(lines)
        atoms = []
        for rows in tables:
            if not rows:
                continue
            keys = set().union(*(r.keys() for r in rows))
            has_frac = all(k in keys for k in ("_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z"))
            has_cart = all(k in keys for k in ("_atom_site_cartn_x", "_atom_site_cartn_y", "_atom_site_cartn_z"))
            if not (has_frac or has_cart):
                continue
            for row in rows:
                sym = StructureParser._extract_symbol(row)
                if not sym:
                    continue
                occ = row.get("_atom_site_occupancy")
                if occ not in (None, ".", "?"):
                    try:
                        if float(strip_cif_esd(occ)) <= 0.0:
                            continue
                    except Exception:
                        pass
                if has_frac:
                    if cell is None:
                        raise ValueError("Fractional coordinates found, but unit-cell parameters are missing.")
                    fx = float(strip_cif_esd(row["_atom_site_fract_x"]))
                    fy = float(strip_cif_esd(row["_atom_site_fract_y"]))
                    fz = float(strip_cif_esd(row["_atom_site_fract_z"]))
                    x, y, z = fractional_to_cartesian(fx, fy, fz, *cell)
                else:
                    x = float(strip_cif_esd(row["_atom_site_cartn_x"]))
                    y = float(strip_cif_esd(row["_atom_site_cartn_y"]))
                    z = float(strip_cif_esd(row["_atom_site_cartn_z"]))
                atoms.append((sym, x, y, z))
            if atoms:
                break
        if not atoms:
            raise ValueError("No usable atom-site table was found in the CIF.")
        return Structure(atoms, title=f"{os.path.basename(path)} (fallback parser)")

    @staticmethod
    def _tokenize(line: str) -> List[str]:
        return re.findall(r"'(?:[^']*)'|\"(?:[^\"]*)\"|\S+", line.strip())

    @staticmethod
    def _read_cif_tables(lines: List[str]) -> List[List[Dict[str, str]]]:
        tables = []
        i, n = 0, len(lines)
        while i < n:
            if lines[i].strip().lower() != "loop_":
                i += 1
                continue
            i += 1
            headers = []
            while i < n and lines[i].strip().startswith("_"):
                headers.append(lines[i].strip())
                i += 1
            rows = []
            while i < n:
                s = lines[i].strip()
                if not s or s.startswith("#"):
                    i += 1
                    continue
                if s == "loop_" or s.startswith("data_") or s.startswith("_"):
                    break
                toks = StructureParser._tokenize(lines[i])
                if len(toks) >= len(headers) and headers:
                    rows.append(dict(zip(headers, toks[:len(headers)])))
                i += 1
            if headers:
                tables.append(rows)
        return tables

    @staticmethod
    def _extract_symbol(row: Dict[str, str]) -> Optional[str]:
        for field in ("_atom_site_type_symbol", "_atom_site_label"):
            v = row.get(field)
            if v is None:
                continue
            m = re.match(r"([A-Za-z]{1,3})", cif_unquote(v))
            if m:
                try:
                    return clean_symbol(m.group(1))
                except Exception:
                    pass
        return None


def validate_engine_choices(program: str, functional: str, basis: str, solvent_text: str) -> Tuple[List[str], List[str], Optional[Dict[str, str]]]:
    errors: List[str] = []
    warnings: List[str] = []

    functional = functional.strip()
    basis = basis.strip()
    if not functional:
        errors.append("Functional / method field is empty.")
    if not basis:
        errors.append("Basis-set field is empty.")

    solvent = resolve_solvent(solvent_text) if solvent_text.strip() else None
    if solvent_text.strip() and solvent is None:
        warnings.append("Solvent was not found in the official ORCA SMD solvent list; ORCA/Gaussian may still accept it if the name matches their solvent keywords.")

    if program == "ORCA":
        if functional and functional not in ORCA_FUNCTIONALS:
            warnings.append(f'Functional "{functional}" is not in the built-in ORCA library.')
        if basis and basis not in ORCA_BASIS:
            warnings.append(f'Basis set "{basis}" is not in the built-in ORCA library.')
        if "/" in functional:
            warnings.append("ORCA expects method and basis as separate tokens, not a combined method/basis string.")
        if basis in {"Def2SVP", "Def2TZVP", "Def2TZVPP"}:
            warnings.append("These look like Gaussian-style def2 basis names. ORCA usually uses def2-SVP / def2-TZVP / def2-TZVPP.")
    else:
        if functional and functional not in GAUSSIAN_FUNCTIONALS:
            warnings.append(f'Functional "{functional}" is not in the built-in Gaussian library.')
        if basis and basis not in GAUSSIAN_BASIS:
            warnings.append(f'Basis set "{basis}" is not in the built-in Gaussian library.')
        if basis in {"def2-SVP", "def2-TZVP", "def2-TZVPP"}:
            warnings.append("Gaussian usually expects Def2SVP / Def2TZVP / Def2TZVPP naming instead of ORCA-style hyphenated names.")
        if basis.endswith("/J") or basis.endswith("/JK") or basis.endswith("/C"):
            warnings.append("Auxiliary basis labels like /J, /JK, /C are ORCA-style, not standard Gaussian route-section basis names.")
    return errors, warnings, solvent


def normalize_orca_grid_keyword(grid_text: str) -> Tuple[str, List[str]]:
    grid = (grid_text or "").strip()
    warnings: List[str] = []
    if not grid:
        return "", warnings
    mapping = {
        "Grid4": "DefGrid1",
        "Grid5": "DefGrid2",
        "Grid6": "DefGrid3",
        "Grid7": "DefGrid3",
    }
    if grid in mapping:
        new_grid = mapping[grid]
        warnings.append(f'ORCA grid keyword "{grid}" was replaced by "{new_grid}" to avoid invalid simple-input syntax.')
        return new_grid, warnings
    return grid, warnings


def resolve_dispersion_keyword(program: str, dispersion: str) -> Tuple[str, List[str]]:
    disp = (dispersion or "").strip().upper()
    warnings: List[str] = []
    if not disp:
        return "", warnings
    if program == "ORCA":
        if disp in {"D3BJ", "D4"}:
            return disp, warnings
        warnings.append(f'Dispersion model "{dispersion}" is not recognized by the built-in ORCA mapping and was omitted.')
        return "", warnings
    if program == "Gaussian":
        if disp == "D3BJ":
            return "EmpiricalDispersion=GD3BJ", warnings
        if disp == "D4":
            warnings.append('Gaussian input generation does not map D4 automatically; the dispersion keyword was omitted.')
            return "", warnings
        warnings.append(f'Dispersion model "{dispersion}" is not recognized by the built-in Gaussian mapping and was omitted.')
        return "", warnings
    return "", warnings


def generate_orca(data: Dict, structure: Structure, solvent: Optional[Dict[str, str]]) -> str:
    grid_kw, grid_warnings = normalize_orca_grid_keyword(data.get("grid", ""))
    if grid_warnings:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + grid_warnings
    disp_kw, disp_warnings = resolve_dispersion_keyword("ORCA", data.get("dispersion", ""))
    if disp_warnings:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + disp_warnings
    kw = [data["functional"], data["basis"]]
    if disp_kw:
        kw.append(disp_kw)
    if data["ri_jcosx"]:
        kw.extend(["def2/J", "RIJCOSX"])
    if data["tight_scf"]:
        kw.append("TightSCF")
    if grid_kw:
        kw.append(grid_kw)
    if data["job_opt"]:
        kw.append("Opt")
    if data["job_freq"]:
        kw.append("Freq")
    if data["job_density"] or data["job_esp"]:
        kw.append("KeepDens")
    if data["job_sp"] and not data["job_opt"] and not data["job_freq"] and not data["job_tddft"] and not data["job_nmr"]:
        kw.append("SP")

    lines = ["! " + " ".join(kw)]
    # --- Constraints (auto-generated) ---
    if data.get("job_opt"):
        atoms = structure.atoms
        constraints = []
        if data.get("freeze_all"):
            for i, (sym, *_rest) in enumerate(atoms):
                constraints.append(f"{{ {sym} {i+1} C }}")
        elif data.get("freeze_heavy"):
            for i, (sym, *_rest) in enumerate(atoms):
                if sym != "H":
                    constraints.append(f"{{ {sym} {i+1} C }}")
        if constraints:
            lines += ["", "%geom", "  Constraints"]
            lines += ["    " + c for c in constraints]
            lines += ["  end", "end"]


    if data["job_tddft"]:
        lines += ["", "%tddft", f"  NRoots {data['nroots']}", "  Triplets false", "  DoTDA true", "end"]

    if data["job_nmr"]:
        lines += ["", "%eprnmr", "  NMR true", "end"]

    if solvent:
        lines += ["", "%cpcm", "  smd true", f'  SMDsolvent "{solvent["orca"]}"', "end"]

    if data["print_mos"] or data["job_density"] or data["job_esp"]:
        lines += ["", "%output", f"  Print[P_MOs] {1 if data['print_mos'] else 0}", f"  Print[P_OrbEn] {2 if data['print_mos'] else 0}", "end"]

    if data["extra"]:
        lines += ["", data["extra"].rstrip()]

    lines += ["", f"* xyz {data['charge']} {data['multiplicity']}", structure.xyz_block(), "*", ""]
    return "\n".join(lines)


def generate_gaussian(data: Dict, structure: Structure, solvent: Optional[Dict[str, str]]) -> str:
    disp_kw, disp_warnings = resolve_dispersion_keyword("Gaussian", data.get("dispersion", ""))
    if disp_warnings:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + disp_warnings
    route = [f"{data['functional']}/{data['basis']}"]
    if disp_kw:
        route.append(disp_kw)
    if data["job_opt"]:
        route.append("Opt")
    if data["job_freq"]:
        route.append("Freq")
    if data["job_tddft"]:
        route.append(f"TD(NStates={data['nroots']})")
    if data["job_nmr"]:
        route.append("NMR")
    if data["job_density"]:
        route.append("Density=Current")
    if data["job_esp"]:
        route.append("Pop=MK")
    if solvent:
        route.append(f"SCRF=(SMD,Solvent={solvent['gaussian']})")
    if data["extra"]:
        route.append(data["extra"].strip())
    lines = [
        "#P " + " ".join(route),
        "",
        structure.title,
        "",
        f"{data['charge']} {data['multiplicity']}",
        structure.xyz_block(),
        "",
    ]
    return "\n".join(lines)


def split_cli_args(arg_string: str) -> List[str]:
    text = arg_string.strip()
    if not text:
        return []
    try:
        import shlex
        return shlex.split(text, posix=(os.name != "nt"))
    except Exception:
        return text.split()


def find_orca_candidates() -> List[str]:
    candidates: List[str] = []
    seen = set()

    def add(p: Optional[str]):
        if not p:
            return
        norm = os.path.normcase(os.path.abspath(p))
        if norm in seen:
            return
        seen.add(norm)
        candidates.append(os.path.abspath(p))

    which_path = shutil.which("orca.exe") or shutil.which("orca")
    add(which_path)

    env_vars = ["ORCA_PATH", "ORCA_DIR", "ORCA_HOME"]
    for var in env_vars:
        val = os.environ.get(var, "").strip().strip('"')
        if not val:
            continue
        p = Path(val)
        if p.is_dir():
            add(str(p / "orca.exe"))
            add(str(p / "orca"))
        else:
            add(str(p))

    if os.name == "nt":
        common_roots = [
            Path("C:/orca"),
            Path("C:/ORCA"),
            Path("C:/Program Files/ORCA"),
            Path("C:/Program Files/orca"),
            Path("C:/Program Files (x86)/ORCA"),
            Path("C:/Program Files (x86)/orca"),
            Path.home() / "orca",
            Path.home() / "ORCA",
            Path.home() / "Downloads",
        ]
    else:
        common_roots = [
            Path("/opt"),
            Path("/usr/local"),
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path.home() / "orca",
            Path.home() / "ORCA",
            Path.home() / "Downloads",
            Path.home() / ".local" / "bin",
        ]
    for root in common_roots:
        if not root.exists():
            continue
        if root.is_file():
            add(str(root))
            continue
        direct = root / "orca.exe"
        if direct.exists():
            add(str(direct))
        direct2 = root / "orca"
        if direct2.exists():
            add(str(direct2))
        try:
            for executable_name in ("orca.exe", "orca"):
                for p in root.rglob(executable_name):
                    add(str(p))
                    break
        except Exception:
            pass

    valid = []
    for p in candidates:
        ok, _reason = validate_orca_qm_executable(p)
        if ok:
            valid.append(p)
    return valid


def find_orca_candidates_with_rejections() -> Tuple[List[str], List[Tuple[str, str]]]:
    raw_candidates: List[str] = []
    seen = set()

    def add(p: Optional[str]):
        if not p:
            return
        norm = os.path.normcase(os.path.abspath(p))
        if norm in seen:
            return
        seen.add(norm)
        raw_candidates.append(os.path.abspath(p))

    for exe_name in ("orca.exe", "orca"):
        add(shutil.which(exe_name))

    for var in ("ORCA_PATH", "ORCA_DIR", "ORCA_HOME"):
        val = os.environ.get(var, "").strip().strip('"')
        if not val:
            continue
        p = Path(val)
        if p.is_dir():
            add(str(p / "orca.exe"))
            add(str(p / "orca"))
        else:
            add(str(p))

    roots = [
        Path("/opt"),
        Path("/usr/local"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path.home() / "orca",
        Path.home() / "ORCA",
        Path.home() / "Downloads",
        Path.home() / ".local" / "bin",
    ] if os.name != "nt" else [
        Path("C:/orca"),
        Path("C:/ORCA"),
        Path("C:/Program Files/ORCA"),
        Path("C:/Program Files/orca"),
        Path("C:/Program Files (x86)/ORCA"),
        Path("C:/Program Files (x86)/orca"),
        Path.home() / "orca",
        Path.home() / "ORCA",
        Path.home() / "Downloads",
    ]
    for root in roots:
        if not root.exists():
            continue
        for executable_name in ("orca.exe", "orca"):
            direct = root / executable_name
            if direct.exists():
                add(str(direct))
        try:
            for executable_name in ("orca.exe", "orca"):
                for p in root.rglob(executable_name):
                    add(str(p))
                    break
        except Exception:
            pass

    accepted: List[str] = []
    rejected: List[Tuple[str, str]] = []
    for path in raw_candidates:
        ok, reason = validate_orca_qm_executable(path)
        if ok:
            accepted.append(path)
        elif os.path.isfile(path):
            rejected.append((path, reason))
    return accepted, rejected


class FilteredCombo(ttk.Combobox):
    def __init__(self, master=None, values=None, **kwargs):
        super().__init__(master, values=values or [], **kwargs)
        self._all_values = list(values or [])
        self.bind("<KeyRelease>", self._on_keyrelease)

    def set_values(self, values):
        self._all_values = list(values)
        self.configure(values=self._all_values)

    def _on_keyrelease(self, event):
        if event.keysym in {"Up", "Down", "Return", "Tab", "Escape"}:
            return
        typed = self.get().strip().lower()
        if not typed:
            self.configure(values=self._all_values)
            return
        filtered = [v for v in self._all_values if typed in v.lower()]
        self.configure(values=filtered if filtered else self._all_values)


class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.show)

    def show(self, _event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + 24
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip,
            text=self.text,
            justify="left",
            background="#ffffff",
            foreground="#1f2937",
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=8,
            wraplength=300,
            font=("Segoe UI", 9),
        )
        label.pack()

    def hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class InfoIcon(tk.Canvas):
    def __init__(self, master, tooltip_text: str):
        super().__init__(master, width=18, height=18, highlightthickness=0, bg="#f8fafc", cursor="hand2")
        self.create_oval(2, 2, 16, 16, fill="#1d4ed8", outline="#1d4ed8")
        self.create_text(9, 9, text="i", fill="#ffffff", font=("Segoe UI", 10, "italic bold"))
        ToolTip(self, tooltip_text)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ORCA input builder")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = max(760, int(screen_w * 0.70))
        win_h = max(1, int(screen_h * 0.80))
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(760, min(700, win_h))
        self._configure_styles()

        self.structure: Optional[Structure] = None
        self.current_input_path: Optional[str] = None
        self.last_output_path: Optional[str] = None
        self.run_thread: Optional[threading.Thread] = None
        self.run_process: Optional[subprocess.Popen] = None
        self.monitor_job_id: Optional[str] = None
        self.monitor_offset: int = 0
        self.monitor_started_at: Optional[float] = None
        self.monitor_status_text: str = "Idle"
        self.active_run_context: Optional[Dict] = None
        self.preview_thread: Optional[threading.Thread] = None
        self.last_helper_launch_key: Optional[Tuple[str, ...]] = None
        self.last_helper_launch_time: float = 0.0

        self.path_var = tk.StringVar()
        self.program_var = tk.StringVar(value="ORCA")
        self.functional_var = tk.StringVar(value="B3LYP")
        self.basis_var = tk.StringVar(value="def2-SVP")
        self.dispersion_var = tk.StringVar(value="")
        self.solvent_var = tk.StringVar(value="")
        self.charge_var = tk.IntVar(value=0)
        self.mult_var = tk.IntVar(value=1)
        self.grid_var = tk.StringVar(value="DefGrid2")
        self.nroots_var = tk.IntVar(value=10)

        self.job_sp_var = tk.BooleanVar(value=True)
        self.job_opt_var = tk.BooleanVar(value=False)
        self.job_freq_var = tk.BooleanVar(value=False)
        self.job_esp_mep_var = tk.BooleanVar(value=False)
        self.job_nmr_var = tk.BooleanVar(value=False)
        self.job_tddft_var = tk.BooleanVar(value=False)
        self.job_interaction_var = tk.BooleanVar(value=False)
        self.job_interaction_var.trace_add("write", lambda *args: self._update_interaction_section())
        self.job_sp_var.trace_add("write", lambda *args: self._sync_job_target_flags("sp"))
        self.job_opt_var.trace_add("write", lambda *args: self._sync_job_target_flags("opt"))
        self.job_freq_var.trace_add("write", lambda *args: self._sync_job_target_flags("freq"))
        self.job_nmr_var.trace_add("write", lambda *args: self._sync_job_target_flags("nmr"))
        self.job_tddft_var.trace_add("write", lambda *args: self._sync_job_target_flags("tddft"))
        self.freeze_heavy_var = tk.BooleanVar(value=False)
        self.freeze_all_var = tk.BooleanVar(value=False)

        self.interaction_relax_var = tk.BooleanVar(value=False)
        self.interaction_relax_var.trace_add("write", lambda *args: self._update_interaction_section())
        self.interaction_thermo_var = tk.BooleanVar(value=True)
        self.interaction_thermo_var.trace_add("write", lambda *args: self._update_interaction_section())
        self.frag_a_charge_var = tk.StringVar(value="0")
        self.frag_a_mult_var = tk.StringVar(value="1")
        self.frag_b_charge_var = tk.StringVar(value="0")
        self.frag_b_mult_var = tk.StringVar(value="1")
        self.fragment_a_summary_var = tk.StringVar(value="Not assigned")
        self.fragment_b_summary_var = tk.StringVar(value="Not assigned")
        self.fragment_a_formula_var = tk.StringVar(value="")
        self.fragment_b_formula_var = tk.StringVar(value="")
        self.fragment_status_var = tk.StringVar(value="Interaction mode is off.")

        self.fragment_a_indices: List[int] = []
        self.fragment_b_indices: List[int] = []
        self.current_connectivity_bonds: List[Tuple[int, int]] = []
        self.current_components: List[List[int]] = []

        self.tight_scf_var = tk.BooleanVar(value=True)
        self.ri_jcosx_var = tk.BooleanVar(value=True)
        self.print_mos_var = tk.BooleanVar(value=True)

        self.orca_path_var = tk.StringVar(value="")
        self.auto_open_output_var = tk.BooleanVar(value=True)
        self.homo_lumo_script_var = tk.StringVar(value=str(DEFAULT_HOMO_LUMO_SCRIPT))
        self.esp_script_var = tk.StringVar(value=str(DEFAULT_ESP_SCRIPT))
        self.nci_script_var = tk.StringVar(value=str(DEFAULT_NCI_SCRIPT))
        self.qtaim_script_var = tk.StringVar(value=str(DEFAULT_QTAIM_SCRIPT))
        self.launch_python_var = tk.StringVar(value=sys.executable)
        self.esp_python_var = tk.StringVar(value=default_esp_python_command())
        self.nci_python_var = tk.StringVar(value=default_nci_python_command())
        self.qtaim_python_var = tk.StringVar(value=default_qtaim_python_command())
        self.recent_input_files: List[str] = []
        self.header_images = []
        self.window_icon_image = None

        self.auto_open_output_var.set(True)
        self._apply_app_icon()
        self._build()
        self._load_launcher_settings()
        self.auto_open_output_var.set(True)
        self._use_latest_python_for_tools()
        self._refresh_engine_lists()
        self.auto_locate_orca(silent=True)
        if not Path(self.qtaim_script_var.get().strip()).is_file():
            self.auto_locate_qtaim(silent=True)
        self._report_runtime_environment()


    def _apply_app_icon(self):
        try:
            if ORCA_ICON_PATH.is_file():
                with open(ORCA_ICON_PATH, "rb") as f:
                    img = tk.PhotoImage(data=base64.b64encode(f.read()))
                self.window_icon_image = img
                self.iconphoto(True, img)
            if os.name == "nt" and BUILDER_ICON_ICO_PATH.is_file():
                try:
                    self.iconbitmap(default=str(BUILDER_ICON_ICO_PATH))
                except Exception:
                    pass
        except Exception:
            self.window_icon_image = None

    def _report_runtime_environment(self):
        diagnostics = [
            f"Python executable: {sys.executable}",
            f"Python version: {sys.version}",
            "Python path: " + repr(sys.path),
        ]
        print("\n".join(diagnostics))
        missing, dependency_message = active_interpreter_dependency_report()
        try:
            self.append_monitor("\n".join(diagnostics) + "\n" + dependency_message + "\n")
        except Exception:
            pass
        if missing:
            try:
                self.status.configure(text="Missing Python dependencies for active interpreter: " + ", ".join(missing))
            except Exception:
                pass

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        self.configure(background="#f4f6f9")
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

    def _load_header_icon(self, path: Path, max_size: int = 72):
        if not path.is_file():
            return None
        with open(path, "rb") as f:
            img = tk.PhotoImage(data=base64.b64encode(f.read()))
        factor = max(1, math.ceil(max(img.width() / max_size, img.height() / max_size)))
        if factor > 1:
            img = img.subsample(factor, factor)
        self.header_images.append(img)
        return img

    def _add_header_image_action(self, parent, column: int, icon_path: Path, label: str, command):
        box = ttk.Frame(parent, style="Header.TFrame")
        box.grid(row=0, column=column, rowspan=2, padx=(8, 0), sticky="ns")
        icon = self._load_header_icon(icon_path)
        if icon is None:
            tk.Button(
                box,
                text=label,
                command=command,
                bg="#2a4b75",
                fg="#f8fafc",
                activebackground="#345986",
                activeforeground="#f8fafc",
                relief="flat",
                padx=10,
                pady=8,
                cursor="hand2",
            ).grid(row=0, column=0, sticky="n")
        else:
            tk.Button(
                box,
                image=icon,
                command=command,
                bg="#1e3a5f",
                activebackground="#2a4b75",
                relief="flat",
                borderwidth=0,
                width=88,
                height=78,
                cursor="hand2",
            ).grid(row=0, column=0, sticky="n")
        action_link = ttk.Label(box, text=label, style="HeaderAction.TLabel", cursor="hand2")
        action_link.grid(row=1, column=0, sticky="n", pady=(3, 0))
        action_link.bind("<Button-1>", lambda _e: command())

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="ORCA input builder", style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        settings_box = ttk.Frame(header, style="Header.TFrame")
        settings_box.grid(row=1, column=0, sticky="w")
        settings_link = ttk.Label(settings_box, text="Settings", style="HeaderLink.TLabel", cursor="hand2")
        settings_link.grid(row=0, column=0, sticky="w")
        settings_link.bind("<Button-1>", lambda _e: self.open_launcher_settings())
        ttk.Label(settings_box, text="/", style="HeaderLink.TLabel").grid(row=0, column=1, sticky="w", padx=(6, 6))
        about_link = ttk.Label(settings_box, text="About", style="HeaderLink.TLabel", cursor="hand2")
        about_link.grid(row=0, column=2, sticky="w")
        about_link.bind("<Button-1>", lambda _e: self.open_about_window())
        self._add_header_image_action(header, 2, ORCA_ICON_PATH, "Run Orca", self.run_orca)
        self._add_header_image_action(header, 3, HOMO_LUMO_ICON_PATH, "HOMO LUMO", self.launch_homo_lumo)
        self._add_header_image_action(header, 4, ESP_ICON_PATH, "ESP map", self.launch_esp)
        self._add_header_image_action(header, 5, NCI_ICON_PATH, "NCI plot", self.launch_nci)
        self._add_header_image_action(header, 6, QTAIM_ICON_PATH, "QTAIM CP", self.launch_qtaim)

        body = ttk.Frame(self, style="Panel.TFrame", padding=10)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=450)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left_host = ttk.Frame(body, style="Panel.TFrame", width=450)
        left_host.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_host.columnconfigure(0, weight=1)
        left_host.rowconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_host, highlightthickness=0, borderwidth=0)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll = ttk.Scrollbar(left_host, orient="vertical", command=left_canvas.yview)
        left_scroll.grid(row=0, column=1, sticky="ns")
        left_canvas.configure(yscrollcommand=left_scroll.set)

        left = ttk.Frame(left_canvas, style="Panel.TFrame")
        left.columnconfigure(0, weight=1)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

        def _sync_left_scroll(_event=None):
            left_canvas.configure(scrollregion=left_canvas.bbox("all"))

        def _sync_left_width(_event):
            left_canvas.itemconfigure(left_window, width=_event.width)

        left.bind("<Configure>", _sync_left_scroll)
        left_canvas.bind("<Configure>", _sync_left_width)
        bind_mousewheel_to_canvas(left_canvas, left)

        right = ttk.Frame(body, style="Panel.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=2)
        right.rowconfigure(1, weight=5)

        fbox = ttk.LabelFrame(left, text="FILE INPUT", padding=8)
        fbox.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        fbox.columnconfigure(0, weight=1)
        fbox.columnconfigure(1, weight=0)
        self.path_entry = ttk.Combobox(fbox, textvariable=self.path_var, values=self.recent_input_files, width=28)
        keep_entry_end_visible(self.path_entry, self.path_var)
        self.path_entry.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.path_entry.bind("<Return>", self._on_input_path_entered)
        self.path_entry.bind("<FocusOut>", self._on_input_path_entered)
        self.path_entry.bind("<<ComboboxSelected>>", self._on_input_path_entered)
        ToolTip(self.path_entry, "Choose a structure file: .cif or .xyz. Existing ORCA .inp files can be loaded for preview.")
        ttk.Button(fbox, text="Browse...", command=self.browse).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(fbox, text="Structure preview", command=self.launch_structure_viewer).grid(row=1, column=1, sticky="e", padx=(6, 0), pady=(6, 0))

        setup = ttk.LabelFrame(left, text="CALCULATION SETUP", padding=8)
        setup.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        setup.columnconfigure(1, weight=0)
        setup.columnconfigure(3, weight=0)

        ttk.Label(setup, text="Program").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        prog = ttk.Combobox(setup, state="readonly", textvariable=self.program_var, values=["ORCA", "Gaussian"], width=10)
        prog.grid(row=0, column=1, sticky="w", pady=(0, 4))
        prog.bind("<<ComboboxSelected>>", lambda e: self._refresh_engine_lists())

        ttk.Label(setup, text="Solvent").grid(row=0, column=2, sticky="w", padx=(14, 8), pady=(0, 4))
        solvent_display = sorted(solvent_display_name(canonical, data) for canonical, data in SOLVENT_LIBRARY.items()) + ["Other solvent..."]
        self.solvent_combo = FilteredCombo(setup, values=solvent_display, textvariable=self.solvent_var, width=12)
        self.solvent_combo.grid(row=0, column=3, sticky="w", pady=(0, 4))
        self.solvent_combo.bind("<<ComboboxSelected>>", self._on_solvent_selected)

        ttk.Label(setup, text="Functional").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        self.functional_combo = FilteredCombo(setup, textvariable=self.functional_var, width=12)
        self.functional_combo.grid(row=1, column=1, sticky="w", pady=(0, 4))

        ttk.Label(setup, text="Basis set").grid(row=1, column=2, sticky="w", padx=(14, 8), pady=(0, 4))
        self.basis_combo = FilteredCombo(setup, textvariable=self.basis_var, width=12)
        self.basis_combo.grid(row=1, column=3, sticky="w", pady=(0, 4))

        ttk.Label(setup, text="Dispersion").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(4, 4))
        ttk.Combobox(setup, textvariable=self.dispersion_var, values=DISPERSION_OPTIONS, state="readonly", width=10).grid(row=2, column=1, sticky="w", pady=(4, 4))
        ttk.Label(setup, text="Charge").grid(row=2, column=2, sticky="w", padx=(14, 8), pady=(4, 4))
        ttk.Entry(setup, textvariable=self.charge_var, width=8).grid(row=2, column=3, sticky="w", pady=(4, 4))

        ttk.Label(setup, text="Multiplicity").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        ttk.Entry(setup, textvariable=self.mult_var, width=8).grid(row=3, column=1, sticky="w", pady=(0, 4))
        ttk.Label(setup, text="ORCA grid").grid(row=3, column=2, sticky="w", padx=(14, 8), pady=(0, 4))
        ttk.Combobox(setup, textvariable=self.grid_var, values=["", "DefGrid1", "DefGrid2", "DefGrid3"], state="readonly", width=10).grid(row=3, column=3, sticky="w", pady=(0, 4))

        ttk.Label(setup, text="TD-DFT roots").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        ttk.Entry(setup, textvariable=self.nroots_var, width=8).grid(row=4, column=1, sticky="w", pady=(0, 4))

        opts = ttk.Frame(setup)
        opts.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        opts.columnconfigure(0, weight=1)
        opts.columnconfigure(1, weight=1)
        opts.columnconfigure(2, weight=1)
        ttk.Checkbutton(opts, text="Tight SCF", variable=self.tight_scf_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="RIJCOSX", variable=self.ri_jcosx_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(opts, text="Print frontier MO data", variable=self.print_mos_var).grid(row=0, column=2, sticky="w")

        cbox = ttk.LabelFrame(left, text="CALCULATION TARGETS", padding=8)
        cbox.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        cbox.columnconfigure(0, weight=1)
        cbox.columnconfigure(1, weight=1)
        sp_row = ttk.Frame(cbox)
        sp_row.grid(row=0, column=0, sticky="w", pady=(0, 3))
        ttk.Checkbutton(sp_row, text="Single-point energy", variable=self.job_sp_var).grid(row=0, column=0, sticky="w")
        sp_info = InfoIcon(sp_row, "Single-point energy evaluates the current geometry without moving atoms. Use it for energies and properties on a fixed structure.")
        sp_info.grid(row=0, column=1, padx=(5, 0))
        ttk.Checkbutton(cbox, text="Geometry optimization", variable=self.job_opt_var).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 3))
        freq_row = ttk.Frame(cbox)
        freq_row.grid(row=1, column=0, sticky="w", pady=(0, 3))
        ttk.Checkbutton(freq_row, text="Frequencies / thermochemistry", variable=self.job_freq_var).grid(row=0, column=0, sticky="w")
        freq_info = InfoIcon(freq_row, "Frequency calculation is required for enthalpy and Gibbs energy. On a single-point geometry without optimization, thermodynamic results may be unreliable.")
        freq_info.grid(row=0, column=1, padx=(5, 0))
        esp_row = ttk.Frame(cbox)
        esp_row.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(0, 3))
        ttk.Checkbutton(esp_row, text="ESP / MEP package", variable=self.job_esp_mep_var).grid(row=0, column=0, sticky="w")
        esp_info = InfoIcon(esp_row, "ESP / MEP package = density retention, ESP-ready output, and automatic WFN/WFX generation after a successful ORCA run.")
        esp_info.grid(row=0, column=1, padx=(5, 0))
        ttk.Checkbutton(cbox, text="NMR", variable=self.job_nmr_var).grid(row=2, column=0, sticky="w", pady=(0, 3))
        ttk.Checkbutton(cbox, text="TD-DFT / UV-Vis", variable=self.job_tddft_var).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 3))
        ttk.Checkbutton(cbox, text="Constrain all atoms except hydrogens", variable=self.freeze_heavy_var).grid(row=3, column=0, sticky="w", pady=(3, 0))
        ttk.Checkbutton(cbox, text="Constrain all atoms", variable=self.freeze_all_var).grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(3, 0))
        self.interaction_toggle_button = ttk.Button(cbox, text="Intermolecular interactions", command=self._toggle_interaction_target)
        self.interaction_toggle_button.grid(row=4, column=0, sticky="ew", pady=(7, 0))
        self.interaction_toggle_state_label = tk.Label(
            cbox,
            text="OFF",
            bg="#f8fafc",
            fg="#b91c1c",
            font=("Segoe UI", 9, "bold"),
            padx=6,
            pady=5,
            cursor="hand2",
        )
        self.interaction_toggle_state_label.grid(row=4, column=1, sticky="w", padx=(8, 0), pady=(7, 0))
        self.interaction_toggle_state_label.bind("<Button-1>", lambda _e: self._toggle_interaction_target())

        self.interaction_box = ttk.LabelFrame(left, text="INTERMOLECULAR INTERACTION", padding=8)
        self.interaction_box.grid(row=3, column=0, sticky="ew", pady=(0, 7))
        self.interaction_box.columnconfigure(1, weight=1)
        self.interaction_box.columnconfigure(3, weight=1)

        ttk.Label(self.interaction_box, text="Fragment definition").grid(row=0, column=0, sticky="w")
        ttk.Label(self.interaction_box, text="Automatic", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Button(self.interaction_box, text="Auto-detect A/B", command=self.auto_detect_fragments).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(self.interaction_box, text="Update selection view", command=self.update_fragment_selection_view).grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6, 0), padx=(6, 0))
        ttk.Label(self.interaction_box, text="Fragment A atoms").grid(row=2, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(self.interaction_box, textvariable=self.fragment_a_summary_var, state="readonly").grid(row=2, column=1, columnspan=3, sticky="ew", pady=(7, 0))
        ttk.Label(self.interaction_box, text="Fragment B atoms").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(self.interaction_box, textvariable=self.fragment_b_summary_var, state="readonly").grid(row=3, column=1, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Label(self.interaction_box, text="Fragment A formula").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Label(self.interaction_box, textvariable=self.fragment_a_formula_var).grid(row=4, column=1, sticky="w", pady=(4, 0))
        ttk.Label(self.interaction_box, text="Fragment B formula").grid(row=4, column=2, sticky="w", pady=(4, 0))
        ttk.Label(self.interaction_box, textvariable=self.fragment_b_formula_var).grid(row=4, column=3, sticky="w", pady=(4, 0))
        ttk.Label(self.interaction_box, text="A charge / mult").grid(row=5, column=0, sticky="w", pady=(4, 0))
        arow = ttk.Frame(self.interaction_box)
        arow.grid(row=5, column=1, sticky="w", pady=(4, 0))
        ttk.Entry(arow, textvariable=self.frag_a_charge_var, width=6).grid(row=0, column=0, sticky="w")
        ttk.Entry(arow, textvariable=self.frag_a_mult_var, width=6).grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(self.interaction_box, text="B charge / mult").grid(row=5, column=2, sticky="w", pady=(4, 0))
        brow = ttk.Frame(self.interaction_box)
        brow.grid(row=5, column=3, sticky="w", pady=(4, 0))
        ttk.Entry(brow, textvariable=self.frag_b_charge_var, width=6).grid(row=0, column=0, sticky="w")
        ttk.Entry(brow, textvariable=self.frag_b_mult_var, width=6).grid(row=0, column=1, sticky="w", padx=(6, 0))
        cp_note = ttk.Frame(self.interaction_box)
        cp_note.grid(row=6, column=0, columnspan=4, sticky="w", pady=(7, 0))
        ttk.Label(cp_note, text="BSSE / CP correction included by default").grid(row=0, column=0, sticky="w")
        cp_info = InfoIcon(cp_note, "Intermolecular interaction calculations include counterpoise (ghost-basis) correction by default to estimate BSSE-corrected interaction energies.")
        cp_info.grid(row=0, column=1, padx=(5, 0))
        relax_row = ttk.Frame(self.interaction_box)
        relax_row.grid(row=7, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Checkbutton(relax_row, text="Relaxation energy / binding E (separate optimized jobs)", variable=self.interaction_relax_var).grid(row=0, column=0, sticky="w")
        relax_info = InfoIcon(relax_row, "Relaxation/binding analysis creates separate optimized follow-up jobs for the dimer and monomers. The main job remains as selected above.")
        relax_info.grid(row=0, column=1, padx=(5, 0))
        thermo_row = ttk.Frame(self.interaction_box)
        thermo_row.grid(row=8, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Checkbutton(thermo_row, text="Delta H and G / thermodynamic frequencies", variable=self.interaction_thermo_var).grid(row=0, column=0, sticky="w")
        thermo_info = InfoIcon(thermo_row, "When enabled together with relaxation/binding mode, optimized dimer and monomer follow-up jobs include frequencies for Delta H and G. Vertical CP interaction energies remain electronic-energy terms.")
        thermo_info.grid(row=0, column=1, padx=(5, 0))
        ttk.Button(self.interaction_box, text="Generate interaction job folders", command=self.generate_interaction_jobs).grid(row=9, column=0, columnspan=4, sticky="ew", pady=(7, 0))
        ttk.Label(self.interaction_box, textvariable=self.fragment_status_var, wraplength=380, justify="left").grid(row=10, column=0, columnspan=4, sticky="w", pady=(6, 0))

        preview_box = ttk.LabelFrame(right, text="INPUT FILE PREVIEW", padding=8)
        preview_box.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(1, weight=1)
        preview_actions = ttk.Frame(preview_box)
        preview_actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        preview_actions.columnconfigure(0, weight=1)
        ttk.Button(preview_actions, text="Preview input file", command=self.preview).grid(row=0, column=1, sticky="e")
        ttk.Button(preview_actions, text="Save input file", command=self.save_input).grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.preview_text = tk.Text(preview_box, wrap="none", height=10, font=("Consolas", 10), relief="solid", bd=1)
        self.preview_text.grid(row=1, column=0, sticky="nsew")
        ys = ttk.Scrollbar(preview_box, orient="vertical", command=self.preview_text.yview)
        xs = ttk.Scrollbar(preview_box, orient="horizontal", command=self.preview_text.xview)
        self.preview_text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.grid(row=1, column=1, sticky="ns")
        xs.grid(row=2, column=0, sticky="ew")

        monbox = ttk.LabelFrame(right, text="JOB MONITOR", padding=8)
        monbox.grid(row=1, column=0, sticky="nsew")
        monbox.columnconfigure(0, weight=1)
        monbox.rowconfigure(2, weight=1)

        monhdr = ttk.Frame(monbox)
        monhdr.grid(row=0, column=0, sticky="ew")
        monhdr.columnconfigure(1, weight=1)
        self.monitor_stage_label = ttk.Label(monhdr, text="Status: Idle")
        self.monitor_stage_label.grid(row=0, column=0, sticky="w")
        self.monitor_elapsed_label = ttk.Label(monhdr, text="Elapsed: 00:00:00")
        self.monitor_elapsed_label.grid(row=0, column=1, sticky="e")

        monbtn = ttk.Frame(monbox)
        monbtn.grid(row=1, column=0, sticky="ew", pady=(6, 6))
        for i in range(4):
            monbtn.columnconfigure(i, weight=1)
        ttk.Button(monbtn, text="Stop job", command=self.stop_orca).grid(row=0, column=0, sticky="ew")
        ttk.Button(monbtn, text="Open .out", command=self.open_last_output).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(monbtn, text="Open folder", command=self.open_last_output_folder).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(monbtn, text="Clear monitor", command=self.clear_monitor).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        self.monitor_text = tk.Text(monbox, wrap="none", height=24, font=("Consolas", 10), relief="solid", bd=1)
        self.monitor_text.grid(row=2, column=0, sticky="nsew")
        monys = ttk.Scrollbar(monbox, orient="vertical", command=self.monitor_text.yview)
        monxs = ttk.Scrollbar(monbox, orient="horizontal", command=self.monitor_text.xview)
        self.monitor_text.configure(yscrollcommand=monys.set, xscrollcommand=monxs.set)
        monys.grid(row=2, column=1, sticky="ns")
        monxs.grid(row=3, column=0, sticky="ew")

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 6))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        ttk.Label(footer, text=COPYRIGHT_NOTE, style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.status = ttk.Label(footer, text="", style="Muted.TLabel")
        self._update_interaction_section()

    def _toggle_interaction_target(self):
        self.job_interaction_var.set(not self.job_interaction_var.get())

    def _sync_job_target_flags(self, source: str = ""):
        if getattr(self, "_syncing_job_flags", False):
            return
        self._syncing_job_flags = True
        try:
            advanced_on = any([
                self.job_opt_var.get(),
                self.job_freq_var.get(),
                self.job_nmr_var.get(),
                self.job_tddft_var.get(),
            ])
            if source == "sp" and self.job_sp_var.get():
                if self.job_opt_var.get():
                    self.job_opt_var.set(False)
                if self.job_freq_var.get() and not self.job_interaction_var.get():
                    self.job_freq_var.set(False)
                if self.job_nmr_var.get():
                    self.job_nmr_var.set(False)
                if self.job_tddft_var.get():
                    self.job_tddft_var.set(False)
            elif source in {"opt", "freq", "nmr", "tddft"} and advanced_on and self.job_sp_var.get():
                self.job_sp_var.set(False)
            if not any([
                self.job_sp_var.get(),
                self.job_opt_var.get(),
                self.job_freq_var.get(),
                self.job_nmr_var.get(),
                self.job_tddft_var.get(),
            ]):
                self.job_sp_var.set(True)
        finally:
            self._syncing_job_flags = False

    def _update_interaction_section(self):
        if getattr(self, "interaction_box", None) is None:
            return
        if getattr(self, "interaction_toggle_button", None) is not None:
            if self.job_interaction_var.get():
                self.interaction_toggle_state_label.configure(text="ON", fg="#047857")
            else:
                self.interaction_toggle_state_label.configure(text="OFF", fg="#b91c1c")
        if self.job_interaction_var.get():
            self.interaction_box.grid()
            if not self.dispersion_var.get().strip():
                self.dispersion_var.set("D4")
            if self.interaction_relax_var.get() and self.interaction_thermo_var.get():
                self.fragment_status_var.set("Relaxation/binding mode will create separate optimized dimer and monomer follow-up jobs with thermodynamic frequencies; the main job stays as selected.")
            elif self.interaction_relax_var.get():
                self.fragment_status_var.set("Relaxation/binding mode will create separate optimized dimer and monomer follow-up jobs without thermodynamic frequencies; the main job stays as selected.")
            elif self.interaction_thermo_var.get():
                self.fragment_status_var.set("Thermodynamic Delta H/G requires relaxation/binding mode; vertical CP interaction energies will be electronic only.")
            elif not self.fragment_a_indices and not self.fragment_b_indices:
                self.fragment_status_var.set("Define fragments A and B automatically, then run ORCA to evaluate interaction energies automatically.")
        else:
            self.interaction_box.grid_remove()
            self.fragment_status_var.set("Interaction mode is off.")

    def _on_solvent_selected(self, _event=None):
        value = self.solvent_var.get().strip()
        if value != "Other solvent...":
            return
        custom = simpledialog.askstring(
            "Other solvent",
            "Enter solvent name or formula as recognized by ORCA/Gaussian:",
            parent=self,
        )
        if custom and custom.strip():
            self.solvent_var.set(custom.strip())
        else:
            self.solvent_var.set("")

    def _refresh_engine_lists(self):
        if self.program_var.get() == "ORCA":
            self.functional_combo.set_values(ORCA_FUNCTIONALS)
            self.basis_combo.set_values(ORCA_BASIS)
            if self.basis_var.get() not in ORCA_BASIS:
                self.basis_var.set("def2-SVP")
            if self.functional_var.get() not in ORCA_FUNCTIONALS:
                self.functional_var.set("B3LYP")
            self.grid_var.set("DefGrid2")
        else:
            self.functional_combo.set_values(GAUSSIAN_FUNCTIONALS)
            self.basis_combo.set_values(GAUSSIAN_BASIS)
            if self.basis_var.get() not in GAUSSIAN_BASIS:
                self.basis_var.set("6-31G(d)")
            if self.functional_var.get() not in GAUSSIAN_FUNCTIONALS:
                self.functional_var.set("B3LYP")

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("Input files", "*.xyz *.cif *.inp"), ("Structure files", "*.xyz *.cif"), ("ORCA input", "*.inp"), ("All files", "*.*")])
        if p:
            self.path_var.set(p)
            self._remember_input_file(p)
            self._load_existing_orca_input_if_selected()

    def _is_existing_orca_input_path(self, path: str) -> bool:
        return bool(path) and path.lower().endswith(".inp") and os.path.isfile(path)

    def _on_input_path_entered(self, _event=None):
        path = self.path_var.get().strip().strip('"')
        if path and os.path.isfile(path):
            self._remember_input_file(path)
        self._load_existing_orca_input_if_selected()

    def _remember_input_file(self, path: str):
        clean = str(path or "").strip().strip('"')
        if not clean:
            return
        try:
            clean = str(Path(clean).resolve())
        except Exception:
            pass
        self.recent_input_files = [clean] + [
            item for item in self.recent_input_files
            if os.path.normcase(item) != os.path.normcase(clean)
        ]
        self.recent_input_files = self.recent_input_files[:5]
        try:
            self.path_entry.configure(values=self.recent_input_files)
        except Exception:
            pass
        try:
            self._save_launcher_settings()
        except Exception:
            pass

    def _load_existing_orca_input_if_selected(self) -> bool:
        path = self.path_var.get().strip().strip('"')
        if not self._is_existing_orca_input_path(path):
            return False
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.current_input_path = path
        self.status.configure(text=f"Loaded existing ORCA input: {path}")
        return True

    def browse_orca(self):
        filetypes = [("ORCA executable", "orca.exe orca")] if os.name == "nt" else [("ORCA executable", "*")]
        filetypes += executable_filetypes()
        p = filedialog.askopenfilename(filetypes=filetypes)
        if p:
            ok, reason = validate_orca_qm_executable(p)
            if not ok:
                messagebox.showerror("ORCA executable rejected", f"{p}\n\n{reason}")
                return
            self.orca_path_var.set(p)

    def auto_locate_orca(self, silent: bool = False):
        candidates, rejected = find_orca_candidates_with_rejections()
        if candidates:
            self.orca_path_var.set(candidates[0])
            self.status.configure(text=f"ORCA executable found: {candidates[0]}")
            if not silent and len(candidates) > 1:
                messagebox.showinfo("ORCA located", "Using:\n" + candidates[0] + "\n\nOther candidates:\n" + "\n".join(candidates[1:5]))
            elif not silent:
                messagebox.showinfo("ORCA located", candidates[0])
        else:
            if rejected:
                self.status.configure(text=f"ORCA QM not found. Rejected: {rejected[0][0]}")
                if not silent:
                    messagebox.showwarning(
                        "ORCA not found",
                        "No valid ORCA quantum-chemistry executable was found automatically.\n\n"
                        + "\n".join(f"Rejected {path}: {reason}" for path, reason in rejected[:5])
                        + "\n\nPlease browse to the real ORCA QM executable, for example /opt/orca*/orca or ~/programs/orca_*/orca.",
                    )
                return
            if not silent:
                messagebox.showwarning("ORCA not found", "No valid ORCA quantum-chemistry executable was found automatically.\nPlease browse to `orca` / `orca.exe` manually.")

    def auto_locate_qtaim(self, silent: bool = False):
        candidates = [
            DEFAULT_QTAIM_SCRIPT,
            TOOLS_ROOT / "qtaim-cp" / "qtaim.py",
            TOOLS_ROOT / "qtaim-cp" / "qtaim_cp.py",
            TOOLS_ROOT / "qtaim-cp" / "qtaim-cp.py",
            APP_ROOT / "tools" / "qtaim-cp" / "qtaim.py",
            APP_ROOT / "tools" / "qtaim-cp" / "qtaim_cp.py",
            APP_ROOT / "tools" / "qtaim-cp" / "qtaim-cp.py",
        ]

        found = None
        for candidate in candidates:
            if candidate.is_file():
                found = candidate
                break

        if found is None:
            for root in (TOOLS_ROOT, APP_ROOT):
                try:
                    matches = sorted(
                        list(root.glob("**/qtaim.py")) + list(root.glob("**/qtaim_cp.py")),
                        key=lambda p: len(str(p)),
                    )
                except Exception:
                    matches = []
                if matches:
                    found = matches[0]
                    break

        if found is not None:
            self.qtaim_script_var.set(str(found))
            self.status.configure(text=f"QTAIM CP script found: {found}")
            if not self.qtaim_python_var.get().strip():
                self.qtaim_python_var.set(default_qtaim_python_command())
            if not silent:
                messagebox.showinfo("QTAIM CP located", str(found))
        elif not silent:
            messagebox.showwarning("QTAIM CP not found", "No qtaim.py script was found automatically.\nPlease browse to the QTAIM CP script manually.")

    def auto_locate_python(self, silent: bool = False):
        candidates = find_python39plus_candidates()
        if candidates:
            python_exe = latest_python39plus_command()
            self.launch_python_var.set(python_exe)
            self.esp_python_var.set(python_exe)
            self.nci_python_var.set(python_exe)
            self.qtaim_python_var.set(python_exe)
            self.status.configure(text=f"Python 3.9+ executable found: {python_exe}")
            if not silent and len(candidates) > 1:
                messagebox.showinfo(
                    "Python located",
                    "Using:\n" + python_exe + "\n\nOther candidates:\n" + "\n".join(candidates[1:5]),
                )
            elif not silent:
                messagebox.showinfo("Python located", python_exe)
        elif not silent:
            messagebox.showwarning(
                "Python not found",
                "No Python 3.9+ executable was found automatically.\nPlease browse to `python3` / `python.exe` manually.",
            )

    def _python_command_is_usable(self, command: str) -> bool:
        parts = self._python_command_parts(command)
        if not parts:
            return False
        executable = parts[0]
        if os.path.isfile(executable):
            version = python_version_tuple(Path(executable))
            return bool(version and version >= (3, 9, 0))
        found = shutil.which(executable)
        if not found:
            return False
        version = python_version_tuple(Path(found))
        return bool(version and version >= (3, 9, 0))

    def _python_command_rank(self, command: str) -> Tuple[Tuple[int, int, int], int]:
        parts = self._python_command_parts(command)
        if not parts:
            return (0, 0, 0), -100
        executable = parts[0]
        if not os.path.isfile(executable):
            found = shutil.which(executable)
            if not found:
                return (0, 0, 0), -100
            executable = found
        path = Path(executable)
        return python_version_tuple(path) or (0, 0, 0), python_path_rank(path)

    def _use_latest_python_for_tools(self):
        latest = active_python_command()
        for var in (
            self.launch_python_var,
            self.esp_python_var,
            self.nci_python_var,
            self.qtaim_python_var,
        ):
            var.set(latest)

        self.status.configure(text=f"Python for all helper tools: {latest}")

    def _auto_locate_launcher_defaults(self):
        self.auto_locate_orca(silent=True)
        self.auto_locate_qtaim(silent=True)
        self._use_latest_python_for_tools()

    def _load_launcher_settings(self):
        try:
            if not LAUNCHER_SETTINGS_PATH.is_file():
                return
            data = json.loads(LAUNCHER_SETTINGS_PATH.read_text(encoding="utf-8"))
            self.homo_lumo_script_var.set(str(resolve_app_path(data.get("homo_lumo_script"), DEFAULT_HOMO_LUMO_SCRIPT)))
            self.esp_script_var.set(str(resolve_app_path(data.get("esp_script"), DEFAULT_ESP_SCRIPT)))
            nci_script = resolve_app_path(data.get("nci_script"), DEFAULT_NCI_SCRIPT)
            if (
                not nci_script.is_file()
                or nci_script.name == "nci_plotter_reset_defaults_FULL_UI.py"
            ):
                nci_script = DEFAULT_NCI_SCRIPT
            self.nci_script_var.set(str(nci_script))
            self.qtaim_script_var.set(str(resolve_app_path(data.get("qtaim_script"), DEFAULT_QTAIM_SCRIPT)))
            active_python = active_python_command()
            self.launch_python_var.set(active_python)
            self.esp_python_var.set(active_python)
            self.nci_python_var.set(active_python)
            self.qtaim_python_var.set(active_python)
            recent = data.get("recent_input_files", [])
            if isinstance(recent, list):
                self.recent_input_files = [str(item) for item in recent if str(item).strip()][:5]
                try:
                    self.path_entry.configure(values=self.recent_input_files)
                except Exception:
                    pass
        except Exception as exc:
            self.append_monitor(f"Launcher settings could not be loaded: {exc}\n")

    def _save_launcher_settings(self):
        data = {
            "homo_lumo_script": app_relative_path(self.homo_lumo_script_var.get().strip()),
            "esp_script": app_relative_path(self.esp_script_var.get().strip()),
            "nci_script": app_relative_path(self.nci_script_var.get().strip()),
            "qtaim_script": app_relative_path(self.qtaim_script_var.get().strip()),
            "python_executable": active_python_command(),
            "esp_python_command": active_python_command(),
            "nci_python_command": active_python_command(),
            "qtaim_python_command": active_python_command(),
            "recent_input_files": self.recent_input_files[:5],
        }
        LAUNCHER_SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _browse_script_into(self, var: tk.StringVar):
        path = filedialog.askopenfilename(
            title="Select Python script",
            filetypes=[("Python scripts", "*.py"), ("All files", "*.*")]
        )
        if path:
            var.set(path)

    def _browse_executable_into(self, var: tk.StringVar):
        path = filedialog.askopenfilename(
            title="Select Python executable",
            filetypes=executable_filetypes()
        )
        if path:
            var.set(path)

    def _prepare_dialog_window(self, win: tk.Toplevel, width: int, height: int, min_width: int, min_height: int):
        win.update_idletasks()
        try:
            screen_w = max(1, int(self.winfo_screenwidth()))
            screen_h = max(1, int(self.winfo_screenheight()))
        except Exception:
            screen_w, screen_h = 1280, 800
        width = min(max(width, min_width), max(min_width, screen_w - 80))
        height = max(1, int(screen_h * 0.80))
        min_height = min(min_height, height)
        x = max(0, int((screen_w - width) / 2))
        y = max(0, int((screen_h - height) / 2))
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.minsize(min_width, min_height)
        win.update_idletasks()
        try:
            win.lift(self)
            win.focus_force()
        except Exception:
            pass

    def _screen_width_fraction(self, fraction: float, minimum: int, margin: int = 80) -> int:
        try:
            screen_w = max(1, int(self.winfo_screenwidth()))
        except Exception:
            screen_w = 1280
        return min(max(minimum, int(screen_w * fraction)), max(minimum, screen_w - margin))

    def _screen_fraction_window_size(self, width: int, fallback_height: int = 800) -> Tuple[int, int]:
        try:
            return width, max(1, int(self.winfo_screenheight() * 0.80))
        except Exception:
            return width, fallback_height

    def open_launcher_settings(self):
        self._auto_locate_launcher_defaults()

        win = tk.Toplevel(self)
        win.title("Launcher settings")
        win.transient(self)
        win.withdraw()
        win.columnconfigure(1, weight=1)

        fields = [
            ("ORCA executable:", self.orca_path_var, self.browse_orca),
            ("HOMO-LUMO script:", self.homo_lumo_script_var, self._browse_script_into),
            ("ESP script:", self.esp_script_var, self._browse_script_into),
            ("NCI plotter script:", self.nci_script_var, self._browse_script_into),
            ("QTAIM CP script:", self.qtaim_script_var, self._browse_script_into),
            ("HOMO-LUMO Python:", self.launch_python_var, self._browse_executable_into),
            ("ESP Python command:", self.esp_python_var, self._browse_executable_into),
            ("NCI Python command:", self.nci_python_var, self._browse_executable_into),
            ("QTAIM Python command (3.9+):", self.qtaim_python_var, self._browse_executable_into),
        ]
        for row, (label, var, browse_func) in enumerate(fields):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=(10 if row == 0 else 6, 0))
            entry = ttk.Entry(win, textvariable=var, width=36)
            keep_entry_end_visible(entry, var)
            entry.grid(row=row, column=1, sticky="ew", padx=(6, 6), pady=(10 if row == 0 else 6, 0))
            if browse_func is None:
                ttk.Label(win, text="").grid(row=row, column=2, padx=(0, 10), pady=(10 if row == 0 else 6, 0))
            else:
                if var is self.orca_path_var:
                    command = browse_func
                else:
                    command = lambda v=var, fn=browse_func: fn(v)
                ttk.Button(win, text="Browse...", command=command).grid(row=row, column=2, padx=(0, 10), pady=(10 if row == 0 else 6, 0))

        launcher_options = ttk.Frame(win)
        launcher_options.grid(row=len(fields), column=0, columnspan=3, sticky="ew", padx=10, pady=(8, 0))
        ttk.Label(launcher_options, text="ORCA output opens automatically after a completed run.").grid(row=0, column=0, sticky="w")

        buttons = ttk.Frame(win)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=3, sticky="e", padx=10, pady=12)

        def save_and_close():
            try:
                self._save_launcher_settings()
                self.append_monitor(f"Launcher settings saved: {LAUNCHER_SETTINGS_PATH}\n")
                win.destroy()
            except Exception as exc:
                messagebox.showerror("Settings error", str(exc))

        ttk.Button(buttons, text="Save", command=save_and_close).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=win.destroy).grid(row=0, column=1)
        settings_width = self._screen_width_fraction(0.44, 560)
        settings_min_width = self._screen_width_fraction(0.36, 500)
        self._prepare_dialog_window(win, settings_width, 520, settings_min_width, 420)
        win.deiconify()
        win.grab_set()

    def open_about_window(self):
        win = tk.Toplevel(self)
        win.title("About")
        win.transient(self)
        win.withdraw()
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)

        box = ttk.Frame(win, padding=14)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(1, weight=1)

        icon = self._load_header_icon(ORCA_ICON_PATH, max_size=144)
        if icon is not None:
            ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=7, sticky="n", padx=(0, 14))

        ttk.Label(box, text="Orca input builder", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="Build ORCA and Gaussian input files from CIF and XYZ structures.", justify="left", wraplength=380).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(box, text="GitHub:", justify="left").grid(row=2, column=1, sticky="w", pady=(10, 0))
        github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
        github_link.grid(row=3, column=1, sticky="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _e: open_path_in_system(GITHUB_URL))
        ttk.Label(box, text="README:", justify="left").grid(row=4, column=1, sticky="w", pady=(10, 0))
        wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
        wiki_link.grid(row=5, column=1, sticky="w", pady=(2, 0))
        wiki_link.bind("<Button-1>", lambda _e: webbrowser.open(wiki_url(), new=2))
        ttk.Label(box, text=COPYRIGHT_NOTE, justify="left").grid(row=6, column=1, sticky="w", pady=(10, 0))

        buttons = ttk.Frame(box)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).grid(row=0, column=0)
        self._prepare_dialog_window(win, 560, 360, 480, 300)
        win.deiconify()
        win.grab_set()

    def _output_candidates_for_source(self, source: Path) -> List[Tuple[int, Path]]:
        candidates: List[Tuple[int, Path]] = []
        if source.is_file() and source.suffix.lower() == ".out":
            candidates.append((0, source))

        source_dir = source if source.is_dir() else source.parent
        if not source_dir.is_dir():
            return candidates

        if source.name and not source.is_dir():
            same_stem = source.with_suffix(".out")
            if same_stem.is_file():
                candidates.append((1, same_stem))
            try:
                candidates.extend((2, path) for path in source_dir.rglob(f"{source.stem}.out") if path.is_file())
            except Exception:
                pass

        try:
            candidates.extend((3, path) for path in source_dir.rglob("*.out") if path.is_file())
        except Exception:
            pass
        return candidates

    def _best_output_path(self, candidates: List[Tuple[int, Path]]) -> str:
        if not candidates:
            raise ValueError("No ORCA .out file was found yet. Run ORCA first, or save/run from this builder.")
        unique: Dict[str, Tuple[int, Path]] = {}
        for priority, path in candidates:
            key = str(path.resolve())
            if key not in unique or priority < unique[key][0]:
                unique[key] = (priority, path)
        best_priority = min(priority for priority, _path in unique.values())
        priority_matches = [path for priority, path in unique.values() if priority == best_priority]
        newest = max(priority_matches, key=lambda p: p.stat().st_mtime)
        return str(newest)

    def _recent_output_path(self) -> str:
        candidates: List[Tuple[int, Path]] = []
        if self.last_output_path and os.path.isfile(self.last_output_path):
            candidates.append((0, Path(self.last_output_path)))
        if self.current_input_path:
            candidates.extend(self._output_candidates_for_source(Path(self.current_input_path)))
        if self.path_var.get().strip():
            candidates.extend(self._output_candidates_for_source(Path(self.path_var.get().strip())))
        newest = Path(self._best_output_path(candidates))
        ok, reason = validate_orca_output_file(str(newest))
        if not ok:
            raise ValueError(
                "No valid completed ORCA QM output is available for downstream analysis.\n"
                f"Rejected {newest}: {reason}"
            )
        return str(newest)

    def _available_output_path(self) -> str:
        candidates: List[Tuple[int, Path]] = []
        if self.last_output_path and os.path.isfile(self.last_output_path):
            candidates.append((0, Path(self.last_output_path)))
        if self.current_input_path:
            candidates.extend(self._output_candidates_for_source(Path(self.current_input_path)))
        selected_text = self.path_var.get().strip()
        if selected_text:
            candidates.extend(self._output_candidates_for_source(Path(selected_text)))
        try:
            return self._best_output_path(candidates)
        except ValueError:
            raise ValueError("No output file is available yet.")

    def _active_working_folder(self) -> str:
        try:
            return str(Path(self._available_output_path()).parent)
        except Exception:
            pass
        candidates: List[Path] = []
        for value in (self.last_output_path, self.current_input_path, self.path_var.get().strip()):
            if not value:
                continue
            path = Path(value)
            if path.is_dir():
                candidates.append(path)
            else:
                candidates.append(path.parent)
        for folder in candidates:
            if folder.is_dir():
                return str(folder)
        return ""

    def _matching_wavefunction_path(self, out_path: str) -> str:
        out_file = Path(out_path)
        same_stem = [out_file.with_suffix(ext) for ext in (".wfn", ".wfx", ".fchk")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)
        folder = out_file.parent
        candidates: List[Path] = []
        for pattern in ("*.wfn", "*.wfx", "*.fchk"):
            candidates.extend(folder.glob(pattern))
        if not candidates:
            raise ValueError(f"No .wfn/.wfx/.fchk file was found in:\n{folder}")
        return str(max(candidates, key=lambda p: p.stat().st_mtime))

    def _matching_nci_input_path(self, out_path: str) -> str:
        out_file = Path(out_path)
        same_stem = [out_file.with_suffix(ext) for ext in (".wfx", ".wfn")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)
        folder = out_file.parent
        candidates: List[Path] = []
        for pattern in ("*.wfx", "*.wfn"):
            candidates.extend(folder.glob(pattern))
        if not candidates:
            raise ValueError(f"No .wfx/.wfn file was found for NCI plotting in:\n{folder}")
        return str(max(candidates, key=lambda p: p.stat().st_mtime))

    def _matching_nci_input_for_path(self, path: str) -> str:
        source = Path(path)
        if source.suffix.lower() in {".wfx", ".wfn"} and source.is_file():
            return str(source)

        same_stem = [source.with_suffix(ext) for ext in (".wfx", ".wfn")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)

        folder = source.parent
        if folder.is_dir():
            candidates: List[Path] = []
            for pattern in ("*.wfx", "*.wfn"):
                candidates.extend(folder.glob(pattern))
            if candidates:
                return str(max(candidates, key=lambda p: p.stat().st_mtime))

        raise ValueError(f"No .wfx/.wfn file was found for NCI plotting in:\n{folder}")

    def _matching_qtaim_input_path(self, out_path: str) -> str:
        out_file = Path(out_path)
        same_stem = [out_file.with_suffix(ext) for ext in (".wfx", ".wfn")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)
        folder = out_file.parent
        candidates: List[Path] = []
        for pattern in ("*.wfx", "*.wfn"):
            candidates.extend(folder.glob(pattern))
        if not candidates:
            raise ValueError(f"No .wfx/.wfn file was found for QTAIM CP analysis in:\n{folder}")
        return str(max(candidates, key=lambda p: p.stat().st_mtime))

    def _matching_qtaim_input_for_path(self, path: str) -> str:
        source = Path(path)
        if source.suffix.lower() in {".wfx", ".wfn"} and source.is_file():
            return str(source)

        same_stem = [source.with_suffix(ext) for ext in (".wfx", ".wfn")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)

        folder = source.parent
        if folder.is_dir():
            candidates: List[Path] = []
            for pattern in ("*.wfx", "*.wfn"):
                candidates.extend(folder.glob(pattern))
            if candidates:
                return str(max(candidates, key=lambda p: p.stat().st_mtime))

        raise ValueError(f"No .wfx/.wfn file was found for QTAIM CP analysis in:\n{folder}")

    def _active_orca_output_path(self) -> Optional[str]:
        proc = self.run_process
        if proc is None or proc.poll() is not None:
            return None

        context = self.active_run_context or {}
        input_path = context.get("input_path")
        if input_path:
            return str(Path(input_path).with_suffix(".out"))

        if self.last_output_path:
            return self.last_output_path

        return None

    def _current_orca_task_output_path(self) -> Optional[str]:
        active_out = self._active_orca_output_path()
        if active_out:
            return active_out

        if self.current_input_path:
            current_input = Path(self.current_input_path)
            if current_input.suffix.lower() in {".inp", ".out"}:
                return str(current_input.with_suffix(".out"))

        selected_path = self.path_var.get().strip().strip('"')
        if selected_path:
            selected = Path(selected_path)
            if selected.suffix.lower() in {".inp", ".out"}:
                return str(selected.with_suffix(".out"))

        return None

    def _require_valid_orca_output_if_present(self, out_path: str) -> None:
        if not out_path or not os.path.isfile(out_path):
            return
        ok, reason = validate_orca_output_file(out_path)
        if not ok:
            raise ValueError(
                "ORCA calculation did not run successfully. The configured executable is not ORCA QM or the calculation failed. "
                "Downstream analysis was not launched.\n"
                f"Rejected {out_path}: {reason}"
            )

    def _current_nci_input_path(self) -> Optional[str]:
        task_out = self._current_orca_task_output_path()
        if task_out:
            self._require_valid_orca_output_if_present(task_out)
            return self._matching_nci_input_path(task_out)

        for candidate in (
            self.current_input_path,
            self.path_var.get().strip().strip('"'),
            self.last_output_path,
        ):
            if not candidate:
                continue
            try:
                return self._matching_nci_input_for_path(candidate)
            except ValueError:
                pass

        return None

    def _current_qtaim_input_path(self) -> Optional[str]:
        task_out = self._current_orca_task_output_path()
        if task_out:
            self._require_valid_orca_output_if_present(task_out)
            return self._matching_qtaim_input_path(task_out)

        for candidate in (
            self.current_input_path,
            self.path_var.get().strip().strip('"'),
            self.last_output_path,
        ):
            if not candidate:
                continue
            try:
                return self._matching_qtaim_input_for_path(candidate)
            except ValueError:
                pass

        return None

    def _python_command_parts(self, command: str) -> List[str]:
        command = command.strip()
        if not command:
            return [sys.executable]
        if command.lower() == "py -3.12":
            command = default_python39plus_command()
        unquoted = command.strip('"').strip("'")
        if os.path.isfile(unquoted):
            return [unquoted]
        return [part.strip().strip('"').strip("'") for part in split_cli_args(command) if part.strip()]

    def _launch_python_tool(self, script_path: str, input_path: Optional[str] = None, python_command: Optional[str] = None) -> bool:
        py_parts = [active_python_command()]
        script = script_path.strip().strip('"')
        if py_parts[0].lower().endswith(".exe") and not os.path.isfile(py_parts[0]):
            raise ValueError(f"Python executable was not found:\n{py_parts[0]}")
        if not os.path.isfile(script):
            raise ValueError(f"Launcher script was not found:\n{script}")
        command = py_parts + [script]
        launch_cwd = os.path.dirname(script) or os.getcwd()
        if input_path:
            if not os.path.isfile(input_path):
                raise ValueError(f"Input file was not found:\n{input_path}")
            command.append(input_path)
            launch_cwd = os.path.dirname(input_path) or launch_cwd
        launch_key = tuple(command + [launch_cwd])
        now = time.time()
        if launch_key == self.last_helper_launch_key and now - self.last_helper_launch_time < 1.0:
            self.append_monitor("Skipped duplicate helper launch.\n")
            return False
        self.last_helper_launch_key = launch_key
        self.last_helper_launch_time = now
        subprocess.Popen(command, cwd=launch_cwd, shell=False)
        self.append_monitor(f"Launched helper with Python: {py_parts[0]}\n")
        return True

    def launch_homo_lumo(self):
        try:
            try:
                out_path = self._recent_output_path()
            except ValueError as exc:
                if "No ORCA .out file was found yet." not in str(exc):
                    raise
                if self._launch_python_tool(self.homo_lumo_script_var.get(), None, self.launch_python_var.get()):
                    self.append_monitor("Launched HOMO-LUMO in standalone mode.\n")
                return
            if self._launch_python_tool(self.homo_lumo_script_var.get(), out_path, self.launch_python_var.get()):
                self.append_monitor(f"Launched HOMO-LUMO with: {out_path}\n")
        except Exception as exc:
            messagebox.showerror("HOMO-LUMO launcher", str(exc))

    def launch_esp(self):
        try:
            wavefunction_path = None
            try:
                out_path = self._recent_output_path()
                wavefunction_path = self._matching_wavefunction_path(out_path)
            except ValueError as exc:
                if "No valid completed ORCA QM output" in str(exc) or "ORCA calculation did not run successfully" in str(exc):
                    raise
                wavefunction_path = None

            if not wavefunction_path:
                if self._launch_python_tool(self.esp_script_var.get(), None, self.esp_python_var.get()):
                    self.append_monitor("Launched ESP in standalone mode.\n")
                return

            if self._launch_python_tool(self.esp_script_var.get(), wavefunction_path, self.esp_python_var.get()):
                self.append_monitor(f"Launched ESP with: {wavefunction_path}\n")
        except Exception as exc:
            messagebox.showerror("ESP launcher", str(exc))


    def launch_nci(self):
        try:
            wavefunction_path = self._current_nci_input_path()
            if not wavefunction_path:
                if self._launch_python_tool(self.nci_script_var.get(), None, self.nci_python_var.get()):
                    self.append_monitor("Launched NCI plotter in standalone mode.\n")
                return

            if self._launch_python_tool(self.nci_script_var.get(), wavefunction_path, self.nci_python_var.get()):
                self.append_monitor(f"Launched NCI plotter for current ORCA task with: {wavefunction_path}\n")
        except ValueError as exc:
            if "No .wfx/.wfn file was found for NCI plotting" in str(exc):
                if self._launch_python_tool(self.nci_script_var.get(), None, self.nci_python_var.get()):
                    self.append_monitor(f"Launched NCI plotter in standalone mode. {exc}\n")
                return
            messagebox.showerror("NCI plotter launcher", str(exc))
        except Exception as exc:
            messagebox.showerror("NCI plotter launcher", str(exc))


    def launch_qtaim(self):
        try:
            wavefunction_path = self._current_qtaim_input_path()
            if not wavefunction_path:
                if self._launch_python_tool(self.qtaim_script_var.get(), None, self.qtaim_python_var.get()):
                    self.append_monitor("Launched QTAIM CP viewer in standalone mode.\n")
                return

            if self._launch_python_tool(self.qtaim_script_var.get(), wavefunction_path, self.qtaim_python_var.get()):
                self.append_monitor(f"Launched QTAIM CP viewer for current ORCA task with: {wavefunction_path}\n")
        except ValueError as exc:
            if "No .wfx/.wfn file was found for QTAIM CP analysis" in str(exc):
                if self._launch_python_tool(self.qtaim_script_var.get(), None, self.qtaim_python_var.get()):
                    self.append_monitor(f"Launched QTAIM CP viewer in standalone mode. {exc}\n")
                return
            messagebox.showerror("QTAIM CP launcher", str(exc))
        except Exception as exc:
            messagebox.showerror("QTAIM CP launcher", str(exc))


    def parse_current_structure(self) -> Structure:
        path = self.path_var.get().strip()
        if not path:
            raise ValueError("Please choose an XYZ, CIF, or ORCA input file.")
        structure = StructureParser.parse(path)
        if path.lower().endswith(".cif") and gemmi is not None:
            backend = "gemmi"
        elif path.lower().endswith(".inp"):
            backend = "ORCA input"
        else:
            backend = "internal"
        self.structure = structure
        self.status.configure(text=f"Structure ready: {os.path.basename(path)} | atoms: {len(structure.atoms)} | parser: {backend}")
        return structure

    def _interaction_output_candidates(self) -> List[Path]:
        candidates: List[Path] = []
        if self.current_input_path:
            current_out = Path(self.current_input_path).with_suffix(".out")
            if current_out.is_file():
                candidates.append(current_out)
        if self.last_output_path and os.path.isfile(self.last_output_path):
            candidates.append(Path(self.last_output_path))
        unique = {str(p.resolve()): p for p in candidates if p.is_file()}
        return sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)

    def _interaction_reference_structure(self) -> Tuple[Structure, Optional[str]]:
        input_structure = self.parse_current_structure()
        input_symbols = [atom[0] for atom in input_structure.atoms]
        for out_path in self._interaction_output_candidates():
            try:
                out_structure = StructureParser.parse_orca_output_final_geometry(str(out_path))
            except Exception:
                continue
            out_symbols = [atom[0] for atom in out_structure.atoms]
            if len(out_symbols) != len(input_symbols) or out_symbols != input_symbols:
                continue
            self.structure = out_structure
            return out_structure, str(out_path)
        self.structure = input_structure
        return input_structure, None

    def collect(self):
        return {
            "program": self.program_var.get(),
            "functional": self.functional_var.get().strip(),
            "basis": self.basis_var.get().strip(),
            "dispersion": self.dispersion_var.get().strip(),
            "charge": int(self.charge_var.get()),
            "multiplicity": int(self.mult_var.get()),
            "grid": self.grid_var.get().strip(),
            "nroots": max(1, int(self.nroots_var.get())),
            "ri_jcosx": bool(self.ri_jcosx_var.get()),
            "tight_scf": bool(self.tight_scf_var.get()),
            "print_mos": bool(self.print_mos_var.get()),
            "job_sp": bool(self.job_sp_var.get()),
            "job_opt": bool(self.job_opt_var.get()),
            "job_freq": bool(self.job_freq_var.get()),
            "job_density": bool(self.job_esp_mep_var.get()),
            "job_esp": bool(self.job_esp_mep_var.get()),
            "job_wfn_wfx": bool(self.job_esp_mep_var.get()),
            "job_esp_mep": bool(self.job_esp_mep_var.get()),
            "job_nmr": bool(self.job_nmr_var.get()),
            "job_tddft": bool(self.job_tddft_var.get()),
            "job_interaction": bool(self.job_interaction_var.get()),
            "interaction_relaxation": bool(self.interaction_relax_var.get()),
            "interaction_thermo": bool(self.interaction_thermo_var.get()),
            "freeze_heavy": bool(self.freeze_heavy_var.get()),
            "freeze_all": bool(self.freeze_all_var.get()),
            "solvent_text": self.solvent_var.get().strip(),
            "extra": "",
        }

    def _update_fragment_summary(self):
        structure = getattr(self, "structure", None)
        self.fragment_a_summary_var.set(atom_ranges_text(self.fragment_a_indices) or "Not assigned")
        self.fragment_b_summary_var.set(atom_ranges_text(self.fragment_b_indices) or "Not assigned")
        if structure and self.fragment_a_indices:
            self.fragment_a_formula_var.set(formula_for_indices(structure, self.fragment_a_indices))
        else:
            self.fragment_a_formula_var.set("")
        if structure and self.fragment_b_indices:
            self.fragment_b_formula_var.set(formula_for_indices(structure, self.fragment_b_indices))
        else:
            self.fragment_b_formula_var.set("")

    def _validate_interaction_science(
        self,
        structure: Structure,
        data: Dict,
        a_charge: int,
        a_mult: int,
        b_charge: int,
        b_mult: int,
        include_relax: bool,
        include_thermo: bool,
    ) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        warnings: List[str] = []

        dimer_charge = int(data["charge"])
        dimer_mult = int(data["multiplicity"])
        if a_charge + b_charge != dimer_charge:
            errors.append(
                "Fragment charges must sum to the dimer charge "
                f"(A {a_charge} + B {b_charge} != dimer {dimer_charge})."
            )

        all_indices = list(range(len(structure.atoms)))
        dimer_e = electron_count_for_indices(structure, all_indices, dimer_charge)
        a_e = electron_count_for_indices(structure, self.fragment_a_indices, a_charge)
        b_e = electron_count_for_indices(structure, self.fragment_b_indices, b_charge)
        errors.extend(validate_charge_multiplicity_parity("Dimer", dimer_e, dimer_mult))
        errors.extend(validate_charge_multiplicity_parity("Fragment A", a_e, a_mult))
        errors.extend(validate_charge_multiplicity_parity("Fragment B", b_e, b_mult))

        spin_warning = spin_coupling_warning(dimer_mult, a_mult, b_mult)
        if spin_warning:
            warnings.append(spin_warning)

        if include_thermo and not include_relax:
            warnings.append(
                "Delta H/G thermochemistry is requested, but relaxation/binding mode is off. "
                "The vertical uncorrected and CP-corrected interaction energies will be electronic-energy terms only."
            )
        if data.get("job_opt") and not include_relax:
            warnings.append(
                "The dimer may be optimized before the interaction workflow, but monomer deformation/binding terms "
                "are not computed unless relaxation/binding mode is enabled."
            )
        warnings.append(
            "Automatic fragment detection is based on covalent connectivity. Inspect fragments for salts, "
            "coordination compounds, covalent adducts, or unusual contacts."
        )
        return errors, warnings

    def _auto_detect_fragments_for_structure(self, structure: Structure, source_note: Optional[str] = None):
        thresholds = [1.20, 1.15, 1.10, 1.05]
        for scale in thresholds:
            bonds = infer_bonds(structure, scale=scale)
            comps = connected_components(len(structure.atoms), bonds)
            if len(comps) == 2 and all(comp for comp in comps):
                self.current_connectivity_bonds = bonds
                self.current_components = comps
                self.fragment_a_indices = sorted(comps[0])
                self.fragment_b_indices = sorted(comps[1])
                self._update_fragment_summary()
                suffix = f" using {source_note}" if source_note else ""
                self.fragment_status_var.set(f"Automatic detection succeeded at {scale:.2f} ? covalent radii{suffix}.")
                self.append_monitor(f"Interaction fragments assigned automatically at scale {scale:.2f}{suffix}: A={atom_ranges_text(self.fragment_a_indices)} | B={atom_ranges_text(self.fragment_b_indices)}")
                return
        raise ValueError("Automatic detection did not find exactly two fragments.")

    def auto_detect_fragments(self):
        try:
            structure = self.parse_current_structure()
            self._auto_detect_fragments_for_structure(structure)
            try:
                self._show_fragment_selection_view(structure)
            except Exception as view_exc:
                self.append_monitor(f"Selection view warning: {view_exc}")
        except Exception as exc:
            self.fragment_status_var.set(str(exc))
            messagebox.showerror("Fragment detection", str(exc))

    def launch_structure_viewer(self):
        try:
            if pv is None or np is None:
                raise ValueError("PyVista and NumPy are required for the molecule viewer.")
            structure = self.parse_current_structure()
            bonds = infer_bonds(structure, scale=1.20)
            points = np.array([[x, y, z] for _, x, y, z in structure.atoms], dtype=float)
            extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 1.0
            plotter = pv.Plotter(window_size=self._screen_fraction_window_size(1200), lighting="none")
            configure_pyvista_defaults(pv, plotter, extent=extent)
            for i, j in bonds:
                sym_i = structure.atoms[i][0]
                sym_j = structure.atoms[j][0]
                add_split_colored_bond(pv, plotter, points[i], points[j], ATOM_COLORS.get(sym_i, "#FF69B4"), ATOM_COLORS.get(sym_j, "#FF69B4"))
            for idx, (sym, *_rest) in enumerate(structure.atoms):
                add_ball_and_stick_atom(pv, plotter, sym, points[idx])
            labels = [f"{idx+1}:{sym}" for idx, (sym, *_rest) in enumerate(structure.atoms)]
            plotter.add_point_labels(points, labels, font_size=10, show_points=False, always_visible=False)
            plotter.add_text("Molecule view", position="upper_left", font_size=10)
            title = "ORCA input builder - structure preview"
            bring_window_title_to_front(title)
            plotter.show(title=title)
        except Exception as exc:
            self.append_monitor(f"PyVista viewer error: {exc}")
            messagebox.showerror("PyVista viewer", str(exc))

    def update_fragment_selection_view(self):
        try:
            if pv is None or np is None:
                raise ValueError("PyVista and NumPy are required for the selection view.")
            structure = self.parse_current_structure()
            if not self.fragment_a_indices or not self.fragment_b_indices:
                self._auto_detect_fragments_for_structure(structure)
            self._show_fragment_selection_view(structure)
        except Exception as exc:
            self.fragment_status_var.set(str(exc))
            messagebox.showerror("Selection view", str(exc))

    def _show_fragment_selection_view(self, structure: Structure):
        if pv is None or np is None:
            raise ValueError("PyVista and NumPy are required for the selection view.")
        if not self.fragment_a_indices or not self.fragment_b_indices:
            raise ValueError("Run Auto-detect A/B before opening the selection view.")
        try:
            bonds = infer_bonds(structure, scale=1.20)
            points = np.array([[x, y, z] for _, x, y, z in structure.atoms], dtype=float)
            extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 1.0
            plotter = pv.Plotter(window_size=self._screen_fraction_window_size(1200), lighting="none")
            configure_pyvista_defaults(pv, plotter, extent=extent)

            for i, j in bonds:
                add_split_colored_bond(pv, plotter, points[i], points[j], "#A8A8A8", "#A8A8A8")
            for idx, (sym, *_rest) in enumerate(structure.atoms):
                if idx in self.fragment_a_indices:
                    color = "royalblue"
                elif idx in self.fragment_b_indices:
                    color = "tomato"
                else:
                    color = "lightgray"
                add_ball_and_stick_atom(pv, plotter, sym, points[idx], color=color, name=f"fragment_view_atom_{idx}")

            plotter.add_text(
                "Blue = fragment A\n"
                "Red = fragment B",
                position="upper_left",
                font_size=10,
                name="color_code_text",
            )
            plotter.show()
        except Exception as exc:
            raise ValueError(f"Selection view could not be opened: {exc}") from exc

    def _build_orca_input_for_structure(self, data: Dict, structure: Structure, charge: int, multiplicity: int, solvent: Optional[Dict[str, str]]) -> str:
        local = dict(data)
        local["charge"] = charge
        local["multiplicity"] = multiplicity
        local["job_opt"] = False
        local["job_freq"] = False
        local["job_tddft"] = False
        local["job_nmr"] = False
        local["job_density"] = False
        local["job_esp"] = False
        local["job_wfn_wfx"] = False
        local["job_esp_mep"] = False
        local["print_mos"] = False
        local["job_sp"] = True
        return generate_orca(local, structure, solvent)

    def _build_orca_relaxed_fragment_input(self, data: Dict, structure: Structure, charge: int, multiplicity: int, solvent: Optional[Dict[str, str]], do_freq: bool = True) -> str:
        local = dict(data)
        local["charge"] = charge
        local["multiplicity"] = multiplicity
        local["job_opt"] = True
        local["job_freq"] = bool(do_freq)
        local["job_tddft"] = False
        local["job_nmr"] = False
        local["job_density"] = False
        local["job_esp"] = False
        local["job_wfn_wfx"] = False
        local["job_esp_mep"] = False
        local["print_mos"] = False
        local["freeze_heavy"] = False
        local["freeze_all"] = False
        local["job_sp"] = True
        return generate_orca(local, structure, solvent)

    def _build_orca_relaxed_dimer_input(self, data: Dict, structure: Structure, charge: int, multiplicity: int, solvent: Optional[Dict[str, str]], do_freq: bool = True) -> str:
        local = dict(data)
        local["charge"] = charge
        local["multiplicity"] = multiplicity
        local["job_opt"] = True
        local["job_freq"] = bool(do_freq)
        local["job_tddft"] = False
        local["job_nmr"] = False
        local["job_density"] = False
        local["job_esp"] = False
        local["job_wfn_wfx"] = False
        local["job_esp_mep"] = False
        local["print_mos"] = False
        local["freeze_heavy"] = False
        local["freeze_all"] = False
        local["job_sp"] = True
        return generate_orca(local, structure, solvent)

    def _build_interaction_job_specs(self, data: Dict, structure: Structure, solvent: Optional[Dict[str, str]], a_charge: int, a_mult: int, b_charge: int, b_mult: int, include_dimer: bool = True, include_cp: bool = True, include_relax: bool = False, include_thermo: bool = True) -> List[Dict[str, str]]:
        specs: List[Dict[str, str]] = []
        all_indices = list(range(len(structure.atoms)))
        if include_dimer:
            dimer_structure = subset_structure(structure, all_indices)
            specs.append({"name": "dimer", "text": self._build_orca_input_for_structure(data, dimer_structure, int(data["charge"]), int(data["multiplicity"]), solvent)})
        specs.append({"name": "monomer_A", "text": self._build_orca_input_for_structure(data, subset_structure(structure, self.fragment_a_indices), a_charge, a_mult, solvent)})
        specs.append({"name": "monomer_B", "text": self._build_orca_input_for_structure(data, subset_structure(structure, self.fragment_b_indices), b_charge, b_mult, solvent)})
        if include_cp:
            a_cp_structure = subset_structure(structure, all_indices, ghost_indices=self.fragment_b_indices)
            b_cp_structure = subset_structure(structure, all_indices, ghost_indices=self.fragment_a_indices)
            specs.append({"name": "A_in_AB_basis", "text": self._build_orca_input_for_structure(data, a_cp_structure, a_charge, a_mult, solvent)})
            specs.append({"name": "B_in_AB_basis", "text": self._build_orca_input_for_structure(data, b_cp_structure, b_charge, b_mult, solvent)})
        if include_relax:
            specs.append({"name": "dimer_relaxed", "text": self._build_orca_relaxed_dimer_input(data, subset_structure(structure, all_indices), int(data["charge"]), int(data["multiplicity"]), solvent, do_freq=include_thermo)})
            specs.append({"name": "monomer_A_relaxed", "text": self._build_orca_relaxed_fragment_input(data, subset_structure(structure, self.fragment_a_indices), a_charge, a_mult, solvent, do_freq=include_thermo)})
            specs.append({"name": "monomer_B_relaxed", "text": self._build_orca_relaxed_fragment_input(data, subset_structure(structure, self.fragment_b_indices), b_charge, b_mult, solvent, do_freq=include_thermo)})
        return specs

    def _parse_orca_energy_terms(self, out_path: str) -> Dict[str, Optional[float]]:
        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if "ORCA TERMINATED NORMALLY" not in text.upper():
            raise RuntimeError(f"ORCA job did not terminate normally: {out_path}")

        def pick(pattern: str, flags: int = 0) -> Optional[float]:
            matches = re.findall(pattern, text, flags)
            return float(matches[-1]) if matches else None

        return {
            "electronic": pick(r"FINAL SINGLE POINT ENERGY(?:\s+\([^)]+\))?\s+(-?\d+\.\d+)"),
            "enthalpy": pick(r"Total enthalpy\s+\.\.\.\s+(-?\d+\.\d+)\s+Eh", re.IGNORECASE),
            "gibbs": pick(r"Final Gibbs free energy\s+\.\.\.\s+(-?\d+\.\d+)", re.IGNORECASE),
        }

    def _read_orca_version(self, out_path: str) -> str:
        try:
            with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(12000)
        except Exception:
            return ""
        match = re.search(r"Program Version\s+([^\r\n]+)", text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _read_simple_input_line(self, inp_path: str) -> str:
        if not inp_path or not os.path.isfile(inp_path):
            return ""
        try:
            with open(inp_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("!"):
                        return stripped
        except Exception:
            return ""
        return ""

    def _describe_requested_targets(self, data: Dict) -> List[str]:
        targets: List[str] = []
        if data.get("job_sp"):
            targets.append("single-point energy")
        if data.get("job_opt"):
            targets.append("geometry optimization")
        if data.get("job_freq"):
            targets.append("frequencies / thermochemistry")
        if data.get("job_tddft"):
            targets.append("TD-DFT / UV-Vis")
        if data.get("job_nmr"):
            targets.append("NMR")
        if data.get("job_esp_mep"):
            targets.append("ESP / MEP package")
        if data.get("job_interaction"):
            targets.append("intermolecular interaction workflow")
        return targets

    def _build_calculation_summary(self, context: Dict, out_path: str) -> Dict[str, object]:
        data = dict(context.get("data", {}))
        inp_path = context.get("input_path", "")
        resolved_solvent = resolve_solvent(data.get("solvent_text", "")) if data.get("solvent_text") else None
        energies = self._parse_orca_energy_terms(out_path)
        out_file = Path(out_path)
        wavefunction_files = [str(path) for path in (out_file.with_suffix(".wfn"), out_file.with_suffix(".wfx")) if path.is_file()]
        cube_files = [
            str(path)
            for path in (
                out_file.with_name(out_file.stem + "_Dens.cub"),
                out_file.with_name(out_file.stem + "_ESP.cub"),
            )
            if path.is_file()
        ]
        return {
            "program": "ORCA",
            "orca_version": self._read_orca_version(out_path),
            "input_file": inp_path,
            "output_file": out_path,
            "simple_input_line": self._read_simple_input_line(inp_path),
            "settings": {
                "functional": data.get("functional", ""),
                "basis": data.get("basis", ""),
                "dispersion": data.get("dispersion", ""),
                "ri_jcosx": bool(data.get("ri_jcosx")),
                "tight_scf": bool(data.get("tight_scf")),
                "grid": data.get("grid", ""),
                "charge": data.get("charge"),
                "multiplicity": data.get("multiplicity"),
                "solvent_input": data.get("solvent_text", ""),
                "solvent_resolved": resolved_solvent["canonical"] if resolved_solvent else "",
                "requested_targets": self._describe_requested_targets(data),
                "print_mos": bool(data.get("print_mos")),
                "job_esp_mep": bool(data.get("job_esp_mep")),
                "job_interaction": bool(data.get("job_interaction")),
            },
            "post_processing": dict(context.get("post_processing", {})),
            "analysis_files": {
                "wavefunction_files": wavefunction_files,
                "cube_files": cube_files,
            },
            "results_hartree": energies,
        }

    def _computational_details_paragraphs(self, summary: Dict[str, object], line1: str, line2: str, extra: List[str], ref_map: Dict[str, str]) -> List[str]:
        settings = summary.get("settings", {})
        post = summary.get("post_processing", {})
        files = summary.get("analysis_files", {})
        targets = settings.get("requested_targets", [])
        wavefunction_files = files.get("wavefunction_files", [])
        cube_files = files.get("cube_files", [])

        paragraphs = [line1 + line2]
        if extra:
            paragraphs.append(" ".join(extra))

        workflow_notes = [
            "CrystEngKit was used to prepare the ORCA input, launch the calculation, collect the output, and assemble the present calculation summary."
        ]
        workflow_notes.append(
            "The CrystEngKit analysis route links ORCA outputs and, where available, WFN/WFX wavefunction data to HOMO-LUMO inspection, ESP/MEP mapping with Multiwfn "
            f"{ref_map['MULTIWFN']}, Non-Covalent Interaction (NCI) index analysis {ref_map['NCI']}, and Quantum Theory of Atoms in Molecules (QTAIM) "
            f"critical-point analysis {ref_map['QTAIM']}."
        )
        if settings.get("print_mos"):
            workflow_notes.append(
                "Frontier-orbital information was requested from ORCA output for HOMO-LUMO inspection and electronic-structure evaluation in the CrystEngKit HOMO-LUMO workflow."
            )
        if settings.get("job_esp_mep"):
            if post.get("wfn_wfx_generated") or wavefunction_files:
                workflow_notes.append(
                    "Wavefunction files were generated from the ORCA result with orca_2aim for subsequent property analysis."
                )
            else:
                workflow_notes.append(
                    "WFN/WFX generation was requested for subsequent property analysis, but generated wavefunction files were not confirmed in this summary."
                )
            if post.get("esp_mep_generated") or cube_files:
                workflow_notes.append(
                    f"Electrostatic-potential and electron-density cube files for ESP/MEP analysis were generated with the CrystEngKit ESP workflow using Multiwfn {ref_map['MULTIWFN']}."
                )
            else:
                workflow_notes.append(
                    "ESP/MEP post-processing was requested through the CrystEngKit ESP workflow; generated cube files were not confirmed in this summary."
                )
        elif wavefunction_files:
            workflow_notes.append(
                "Existing wavefunction files were available alongside the ORCA output and can be used by CrystEngKit for ESP/MEP, NCI, and QTAIM analyses."
            )

        if settings.get("job_interaction"):
            workflow_notes.append(
                "Intermolecular interaction calculations were coordinated by CrystEngKit using dimer, monomer, and counterpoise job folders generated from the selected fragment definitions."
            )

        if settings.get("job_esp_mep") or wavefunction_files:
            workflow_notes.append(
                "The resulting wavefunction data provide the basis for Non-Covalent Interaction (NCI) index analysis "
                f"{ref_map['NCI']}, NCIPLOT-style visualization {ref_map['NCIPLOT']}, and Quantum Theory of Atoms in Molecules (QTAIM) critical-point analysis "
                f"{ref_map['QTAIM']} using the CrystEngKit NCI and QTAIM tools."
            )

        paragraphs.append(" ".join(workflow_notes))
        if targets:
            paragraphs.append("Requested job types: " + ", ".join(str(x) for x in targets) + ".")
        return paragraphs

    def _calculation_summary_lines(self, summary: Dict[str, object]) -> List[str]:
        settings = summary.get("settings", {})
        results = summary.get("results_hartree", {})
        version = summary.get("orca_version", "")
        functional = settings.get("functional", "")
        basis = settings.get("basis", "")
        dispersion = settings.get("dispersion", "")
        grid = settings.get("grid", "")
        charge = settings.get("charge")
        mult = settings.get("multiplicity")
        solvent = settings.get("solvent_resolved") or settings.get("solvent_input") or ""
        targets = settings.get("requested_targets", [])
        simple_line = summary.get("simple_input_line", "")

        ref_map = {
            "ORCA": "[Neese, 2017, #2682] {DOI:10.1002/wcms.1327}",
            "PBE": "[Perdew, 1996, #2797] {DOI:10.1103/PhysRevLett.77.3865}",
            "PBE0": "[Adamo, 1999, #2688] {DOI:10.1063/1.478522}",
            "DEF2_BASIS": "[Weigend, 2005, #2684] {DOI:10.1039/b508541a}",
            "DEF2_J": "[Weigend, 2006, #2799] {DOI:10.1039/b515623h}",
            "RIJCOSX": "[Izsak, 2011, #3168] {DOI:10.1063/1.3646921}",
            "D3BJ": "[Grimme, 2011, #2689] {DOI:10.1002/jcc.21759}",
            "DLPNO_CCSDT": "[Riplinger, 2016, #2683] {DOI:10.1063/1.4939030}",
            "BSSE": "[Boys, 2006, #4937] {DOI:10.1080/00268977000101561}",
            "MULTIWFN": "[Lu, 2012, #6001] {DOI:10.1002/jcc.22885}",
            "NCI": "[Johnson, 2010, #6002] {DOI:10.1021/ja100936w}",
            "NCIPLOT": "[Contreras-Garcia, 2011, #6003] {DOI:10.1021/ct100641a}",
            "QTAIM": "[Bader, 1990, #6004] {DOI:10.1093/oso/9780198551683.001.0001}",
        }

        functional_key = functional.strip().upper().replace(" ", "")
        functional_ref = ""
        if functional_key in {"PBE", "PBEPBE"}:
            functional_ref = ref_map["PBE"]
        elif functional_key in {"PBE0", "PBE1PBE"}:
            functional_ref = ref_map["PBE0"]

        basis_ref = ref_map["DEF2_BASIS"] if basis.lower().startswith("def2") or basis.lower().startswith("ma-def2") else ""
        dispersion_ref = ref_map["D3BJ"] if dispersion.upper() == "D3BJ" else ""

        line1 = "Theoretical calculations were carried out with the ORCA program package"
        if version:
            line1 += f" (version {version})"
        line1 += f" {ref_map['ORCA']}."
        line2 = f" The calculation used the {functional} functional"
        if functional_ref:
            line2 += f" {functional_ref}"
        if dispersion:
            line2 += f" with the {dispersion} dispersion correction"
            if dispersion_ref:
                line2 += f" {dispersion_ref}"
        if basis:
            line2 += f" and the {basis} basis set"
            if basis_ref:
                line2 += f" {basis_ref}"
            line2 += "."
        else:
            line2 += "."

        extra = []
        if settings.get("ri_jcosx"):
            extra.append(f"The RIJCOSX approximation {ref_map['RIJCOSX']} was used together with the def2/J auxiliary basis set {ref_map['DEF2_J']}.")
        if settings.get("tight_scf"):
            extra.append("TightSCF convergence criteria were requested.")
        if grid:
            extra.append(f"The numerical integration grid was {grid}.")
        if solvent:
            extra.append(f"Solvent effects were included with the SMD model for {solvent}.")

        lines = [
            "Computational details",
            "",
            *self._computational_details_paragraphs(summary, line1, line2, extra, ref_map),
        ]
        if charge is not None and mult is not None:
            lines.append(f"Charge and multiplicity were {charge} and {mult}, respectively.")
        if simple_line:
            lines.extend(["", "Actual ORCA simple-input line:", simple_line])

        lines.extend(["", "Results"])
        if results.get("electronic") is not None:
            lines.append(f"Final electronic energy: {results['electronic']:.10f} Eh")
        if results.get("enthalpy") is not None:
            lines.append(f"Total enthalpy: {results['enthalpy']:.10f} Eh")
        if results.get("gibbs") is not None:
            lines.append(f"Final Gibbs free energy: {results['gibbs']:.10f} Eh")
        return lines

    def _interaction_summary_lines(self, summary: Dict[str, object]) -> List[str]:
        lines = ["Intermolecular interaction results", f"Geometry source: {summary['geometry_source']}", f"Dimer output: {summary['dimer_output']}", ""]
        eh = summary.get("electronic_hartree", {})
        kcal = summary.get("electronic_kcal_mol", {})
        kj = summary.get("electronic_kj_mol", {})
        labels = {
            "interaction_uncorrected": "interaction_uncorrected",
            "bsse": "bsse_magnitude",
            "interaction_cp_corrected": "interaction_cp_corrected",
            "fragment_deformation_energy": "fragment_deformation_energy",
            "dimer_geometry_relaxation": "dimer_geometry_relaxation",
            "relaxation_energy": "relaxation_energy",
            "binding_electronic": "binding_electronic",
            "binding_enthalpy": "binding_enthalpy",
            "binding_gibbs": "binding_gibbs",
        }
        for key in [
            "interaction_uncorrected",
            "bsse",
            "interaction_cp_corrected",
            "fragment_deformation_energy",
            "dimer_geometry_relaxation",
            "relaxation_energy",
            "binding_electronic",
            "binding_enthalpy",
            "binding_gibbs",
        ]:
            if key in eh:
                lines.append(f"{labels.get(key, key)}: {eh[key]: .10f} Eh   ({kcal.get(key, 0.0): .4f} kcal/mol | {kj.get(key, 0.0): .4f} kJ/mol)")
        failed_jobs = summary.get("failed_jobs", [])
        if failed_jobs:
            lines.append("")
            lines.append("Crash notes:")
            for item in failed_jobs:
                lines.append(f"- {item['name']}: {item['error']}")
        warnings = summary.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {item}" for item in warnings)
        return lines

    def _write_project_summary(self, out_path: str, calc_summary: Dict[str, object], interaction_summary: Optional[Dict[str, object]] = None, interaction_error: str = "") -> Tuple[Path, str]:
        out_file = Path(out_path)
        txt_path = out_file.parent / f"{out_file.stem}_summary.txt"
        lines = self._calculation_summary_lines(calc_summary)
        if interaction_summary is not None:
            lines.extend(["", ""] + self._interaction_summary_lines(interaction_summary))
        elif interaction_error:
            lines.extend(["", "", "Intermolecular interaction results", "", f"Interaction workflow failed: {interaction_error}"])
        text = "\n".join(lines) + "\n"
        txt_path.write_text(text, encoding="utf-8")
        return txt_path, text

    def _interaction_root_for_output(self, dimer_out_path: str) -> Path:
        out_file = Path(dimer_out_path)
        return out_file.parent / f"{out_file.stem}_interaction_jobs"

    def _run_orca_subjob(self, inp_path: Path, orca_path: str) -> str:
        ok, reason = validate_orca_qm_executable(orca_path)
        if not ok:
            raise RuntimeError(f"Configured ORCA executable rejected: {orca_path} ({reason})")
        out_path = inp_path.with_suffix(".out")
        self._set_monitor_stage(f"Interaction: {inp_path.stem}")
        self.append_monitor(f"\n=== Running interaction job: {inp_path.stem} ===\nInput: {inp_path}\nOutput: {out_path}\n")
        with open(out_path, "w", encoding="utf-8", errors="replace") as fout:
            proc = subprocess.run(
                [orca_path, inp_path.name],
                cwd=str(inp_path.parent),
                env=subprocess_env_with_executable_dir(orca_path),
                stdout=fout,
                stderr=subprocess.STDOUT,
                shell=False,
            )
        with open(out_path, "r", encoding="utf-8", errors="replace") as f:
            chunk = f.read()
        if chunk:
            self.append_monitor(chunk)
        if proc.returncode != 0:
            raise RuntimeError(f"Interaction job {inp_path.stem} finished with exit code {proc.returncode}.")
        output_ok, output_reason = validate_orca_output_file(str(out_path))
        if not output_ok:
            raise RuntimeError(f"Interaction job {inp_path.stem} output was rejected: {output_reason}")
        return str(out_path)

    def _preflight_interaction_context(self, context: Dict) -> List[str]:
        if not context.get("interaction_enabled"):
            return []
        if not context.get("fragment_a_indices") or not context.get("fragment_b_indices"):
            return ["Interaction fragments will be auto-detected from the final ORCA geometry before monomer/CP jobs are generated."]

        structure = self.parse_current_structure()
        data = dict(context["data"])
        errors, warnings = self._validate_interaction_science(
            structure,
            data,
            int(context["frag_a_charge"]),
            int(context["frag_a_mult"]),
            int(context["frag_b_charge"]),
            int(context["frag_b_mult"]),
            bool(context.get("interaction_relax")),
            bool(context.get("interaction_thermo", True)),
        )
        if errors:
            raise ValueError("\n".join(errors))
        return warnings

    def _compute_interaction_summary(self, results: Dict[str, Dict[str, Optional[float]]], dimer_out_path: str, geometry_source: str, interaction_relax: bool, include_cp: bool, dimer_optimized: bool, failed_jobs: Optional[List[Dict[str, str]]] = None) -> Dict[str, object]:
        summary: Dict[str, object] = {
            "dimer_output": dimer_out_path,
            "geometry_source": geometry_source,
            "electronic_hartree": {},
            "electronic_kcal_mol": {},
            "electronic_kj_mol": {},
            "warnings": [],
        }
        if failed_jobs:
            summary["failed_jobs"] = failed_jobs
            for item in failed_jobs:
                summary["warnings"].append(f"Crash note: {item['name']} failed ({item['error']})")
        if interaction_relax:
            summary["warnings"].append(
                "Relaxed binding terms use separately optimized dimer and monomer geometries. "
                "CP correction is reported for vertical electronic interaction energy only."
            )

        e_dimer = results.get("dimer", {}).get("electronic")
        e_a = results.get("monomer_A", {}).get("electronic")
        e_b = results.get("monomer_B", {}).get("electronic")
        summary["electronic_hartree"].update({
            "dimer": e_dimer,
            "monomer_A_frozen": e_a,
            "monomer_B_frozen": e_b,
        })
        if e_dimer is not None and e_a is not None and e_b is not None:
            uncorr = e_dimer - e_a - e_b
            summary["electronic_hartree"]["interaction_uncorrected"] = uncorr
            summary["electronic_kcal_mol"]["interaction_uncorrected"] = uncorr * HARTREE_TO_KCAL_MOL
            summary["electronic_kj_mol"]["interaction_uncorrected"] = uncorr * HARTREE_TO_KJ_MOL
        else:
            summary["warnings"].append("Uncorrected interaction energy could not be assembled because one or more frozen monomer energies are missing.")
        if include_cp:
            e_a_cp = results.get("A_in_AB_basis", {}).get("electronic")
            e_b_cp = results.get("B_in_AB_basis", {}).get("electronic")
            summary["electronic_hartree"].update({
                "monomer_A_in_AB_basis": e_a_cp,
                "monomer_B_in_AB_basis": e_b_cp,
            })
            if None not in (e_dimer, e_a_cp, e_b_cp, e_a, e_b):
                cp_corr = e_dimer - e_a_cp - e_b_cp
                bsse = (e_a - e_a_cp) + (e_b - e_b_cp)
                summary["electronic_hartree"]["interaction_cp_corrected"] = cp_corr
                summary["electronic_hartree"]["bsse"] = bsse
                summary["electronic_kcal_mol"]["interaction_cp_corrected"] = cp_corr * HARTREE_TO_KCAL_MOL
                summary["electronic_kj_mol"]["interaction_cp_corrected"] = cp_corr * HARTREE_TO_KJ_MOL
                summary["electronic_kcal_mol"]["bsse"] = bsse * HARTREE_TO_KCAL_MOL
                summary["electronic_kj_mol"]["bsse"] = bsse * HARTREE_TO_KJ_MOL
            else:
                summary["warnings"].append("CP-corrected interaction energy could not be assembled because one or more ghost-basis energies are missing.")
        if interaction_relax:
            e_dimer_rel = results.get("dimer_relaxed", {}).get("electronic")
            e_a_rel = results.get("monomer_A_relaxed", {}).get("electronic")
            e_b_rel = results.get("monomer_B_relaxed", {}).get("electronic")
            summary["electronic_hartree"].update({
                "dimer_relaxed": e_dimer_rel,
                "monomer_A_relaxed": e_a_rel,
                "monomer_B_relaxed": e_b_rel,
            })
            if None in (e_dimer_rel, e_a_rel, e_b_rel):
                summary["warnings"].append("Relaxation/binding terms were skipped because one or more optimized follow-up jobs did not produce usable results.")
            else:
                bind_e = e_dimer_rel - e_a_rel - e_b_rel
                summary["electronic_hartree"]["binding_electronic"] = bind_e
                summary["electronic_kcal_mol"]["binding_electronic"] = bind_e * HARTREE_TO_KCAL_MOL
                summary["electronic_kj_mol"]["binding_electronic"] = bind_e * HARTREE_TO_KJ_MOL
                if None not in (e_dimer, e_a, e_b, e_dimer_rel, e_a_rel, e_b_rel):
                    fragment_deformation = (e_a - e_a_rel) + (e_b - e_b_rel)
                    dimer_geometry_relaxation = e_dimer_rel - e_dimer
                    relax_e = dimer_geometry_relaxation + fragment_deformation
                    summary["electronic_hartree"]["fragment_deformation_energy"] = fragment_deformation
                    summary["electronic_hartree"]["dimer_geometry_relaxation"] = dimer_geometry_relaxation
                    summary["electronic_hartree"]["relaxation_energy"] = relax_e
                    summary["electronic_kcal_mol"]["fragment_deformation_energy"] = fragment_deformation * HARTREE_TO_KCAL_MOL
                    summary["electronic_kcal_mol"]["dimer_geometry_relaxation"] = dimer_geometry_relaxation * HARTREE_TO_KCAL_MOL
                    summary["electronic_kcal_mol"]["relaxation_energy"] = relax_e * HARTREE_TO_KCAL_MOL
                    summary["electronic_kj_mol"]["fragment_deformation_energy"] = fragment_deformation * HARTREE_TO_KJ_MOL
                    summary["electronic_kj_mol"]["dimer_geometry_relaxation"] = dimer_geometry_relaxation * HARTREE_TO_KJ_MOL
                    summary["electronic_kj_mol"]["relaxation_energy"] = relax_e * HARTREE_TO_KJ_MOL
                h_dimer_rel = results.get("dimer_relaxed", {}).get("enthalpy")
                g_dimer_rel = results.get("dimer_relaxed", {}).get("gibbs")
                h_a_rel = results.get("monomer_A_relaxed", {}).get("enthalpy")
                h_b_rel = results.get("monomer_B_relaxed", {}).get("enthalpy")
                g_a_rel = results.get("monomer_A_relaxed", {}).get("gibbs")
                g_b_rel = results.get("monomer_B_relaxed", {}).get("gibbs")
                if None not in (h_dimer_rel, h_a_rel, h_b_rel):
                    delta_h = h_dimer_rel - h_a_rel - h_b_rel
                    summary["electronic_hartree"]["binding_enthalpy"] = delta_h
                    summary["electronic_kcal_mol"]["binding_enthalpy"] = delta_h * HARTREE_TO_KCAL_MOL
                    summary["electronic_kj_mol"]["binding_enthalpy"] = delta_h * HARTREE_TO_KJ_MOL
                if None not in (g_dimer_rel, g_a_rel, g_b_rel):
                    delta_g = g_dimer_rel - g_a_rel - g_b_rel
                    summary["electronic_hartree"]["binding_gibbs"] = delta_g
                    summary["electronic_kcal_mol"]["binding_gibbs"] = delta_g * HARTREE_TO_KCAL_MOL
                    summary["electronic_kj_mol"]["binding_gibbs"] = delta_g * HARTREE_TO_KJ_MOL
        return summary


    def _run_interaction_pipeline(self, dimer_out_path: str, context: Dict) -> Tuple[Dict[str, object], Path]:
        structure = StructureParser.parse_orca_output_final_geometry(dimer_out_path)
        self.structure = structure
        self.fragment_a_indices = list(context.get("fragment_a_indices", []))
        self.fragment_b_indices = list(context.get("fragment_b_indices", []))
        if (not self.fragment_a_indices or not self.fragment_b_indices):
            self._auto_detect_fragments_for_structure(structure, source_note=f"final geometry from {os.path.basename(dimer_out_path)}")
        self._update_fragment_summary()
        if set(self.fragment_a_indices) & set(self.fragment_b_indices):
            raise ValueError("Fragments A and B overlap. Clear and redefine them.")
        if sorted(self.fragment_a_indices + self.fragment_b_indices) != list(range(len(structure.atoms))):
            raise ValueError("Fragments A and B must cover all atoms of the dimer for interaction analysis.")

        data = dict(context["data"])
        errors, warnings, solvent = validate_engine_choices(data["program"], data["functional"], data["basis"], data["solvent_text"])
        science_errors, science_warnings = self._validate_interaction_science(
            structure,
            data,
            int(context["frag_a_charge"]),
            int(context["frag_a_mult"]),
            int(context["frag_b_charge"]),
            int(context["frag_b_mult"]),
            bool(context.get("interaction_relax")),
            bool(context.get("interaction_thermo", True)),
        )
        errors.extend(science_errors)
        warnings.extend(science_warnings)
        if errors:
            raise ValueError("\n".join(errors))
        for warning in warnings:
            self.append_monitor(f"Interaction warning: {warning}")

        root = self._interaction_root_for_output(dimer_out_path)
        root.mkdir(parents=True, exist_ok=True)
        dimer_dir = root / "dimer"
        dimer_dir.mkdir(exist_ok=True)
        if context.get("input_path") and os.path.isfile(context["input_path"]):
            try:
                shutil.copy2(context["input_path"], dimer_dir / Path(context["input_path"]).name)
            except Exception:
                pass
        try:
            shutil.copy2(dimer_out_path, dimer_dir / Path(dimer_out_path).name)
        except Exception:
            pass

        specs = self._build_interaction_job_specs(
            data,
            structure,
            solvent,
            int(context["frag_a_charge"]),
            int(context["frag_a_mult"]),
            int(context["frag_b_charge"]),
            int(context["frag_b_mult"]),
            include_dimer=False,
            include_cp=True,
            include_relax=bool(context.get("interaction_relax")),
            include_thermo=bool(context.get("interaction_thermo", True)),
        )
        orca_path = context["orca_path"]
        results: Dict[str, Dict[str, Optional[float]]] = {"dimer": {"output": dimer_out_path, **self._parse_orca_energy_terms(dimer_out_path)}}
        failed_jobs: List[Dict[str, str]] = []
        for spec in specs:
            job_dir = root / spec["name"]
            job_dir.mkdir(exist_ok=True)
            inp_path = job_dir / f"{spec['name']}.inp"
            inp_path.write_text(spec["text"], encoding="utf-8")
            try:
                out_path = self._run_orca_subjob(inp_path, orca_path)
                results[spec["name"]] = {"output": out_path, **self._parse_orca_energy_terms(out_path)}
            except Exception as exc:
                failed_jobs.append({"name": spec["name"], "error": str(exc)})
                results[spec["name"]] = {"output": None, "electronic": None, "enthalpy": None, "gibbs": None}
                self.append_monitor(f"Interaction subjob failed: {spec['name']} - {exc}\n")

        summary = self._compute_interaction_summary(
            results,
            dimer_out_path,
            dimer_out_path,
            bool(context.get("interaction_relax")),
            True,
            bool(context.get("dimer_optimized")),
            failed_jobs=failed_jobs,
        )
        if summary.get("electronic_hartree", {}).get("interaction_cp_corrected") is not None:
            val = summary["electronic_kcal_mol"]["interaction_cp_corrected"]
            self.append_monitor(f"CP-corrected interaction energy: {val: .4f} kcal/mol")
        if summary.get("electronic_hartree", {}).get("binding_gibbs") is not None:
            val = summary["electronic_kcal_mol"]["binding_gibbs"]
            self.append_monitor(f"Binding Gibbs energy: {val: .4f} kcal/mol")
        return summary, root

    def generate_interaction_jobs(self):
        try:
            if self.program_var.get() != "ORCA":
                raise ValueError("Interaction-energy job generation is implemented only for ORCA.")
            structure, geometry_source = self._interaction_reference_structure()
            if not self.fragment_a_indices or not self.fragment_b_indices:
                source_note = f"final geometry from {os.path.basename(geometry_source)}" if geometry_source else None
                self._auto_detect_fragments_for_structure(structure, source_note=source_note)
            if set(self.fragment_a_indices) & set(self.fragment_b_indices):
                raise ValueError("Fragments A and B overlap. Clear and redefine them.")
            if sorted(self.fragment_a_indices + self.fragment_b_indices) != list(range(len(structure.atoms))):
                raise ValueError("Fragments A and B must cover all atoms of the loaded dimer.")

            data = self.collect()
            errors, warnings, solvent = validate_engine_choices(data["program"], data["functional"], data["basis"], data["solvent_text"])
            self.report_validation(errors, warnings, solvent)
            if errors:
                raise ValueError("\n".join(errors))

            a_charge = int(self.frag_a_charge_var.get())
            a_mult = int(self.frag_a_mult_var.get())
            b_charge = int(self.frag_b_charge_var.get())
            b_mult = int(self.frag_b_mult_var.get())
            science_errors, science_warnings = self._validate_interaction_science(
                structure,
                data,
                a_charge,
                a_mult,
                b_charge,
                b_mult,
                bool(self.interaction_relax_var.get()),
                bool(self.interaction_thermo_var.get()),
            )
            if science_errors or science_warnings:
                self.report_validation(science_errors, science_warnings, solvent)
            if science_errors:
                raise ValueError("\n".join(science_errors))

            base_dir = filedialog.askdirectory(title="Choose parent folder for interaction jobs")
            if not base_dir:
                return
            src_name = Path(self.path_var.get().strip()).stem or "dimer"
            root = Path(base_dir) / f"{src_name}_interaction_jobs"
            root.mkdir(parents=True, exist_ok=True)

            if geometry_source:
                self.append_monitor(f"Interaction jobs will use final dimer geometry from: {geometry_source}")
            else:
                self.append_monitor("Interaction jobs will use the current input geometry because no matching completed ORCA output was found.")

            specs = self._build_interaction_job_specs(
                data,
                structure,
                solvent,
                a_charge,
                a_mult,
                b_charge,
                b_mult,
                include_dimer=True,
                include_cp=True,
                include_relax=bool(self.interaction_relax_var.get()),
                include_thermo=bool(self.interaction_thermo_var.get()),
            )

            for spec in specs:
                job_dir = root / spec["name"]
                job_dir.mkdir(exist_ok=True)
                inp_path = job_dir / f"{spec['name']}.inp"
                inp_path.write_text(spec["text"], encoding="utf-8")

            summary = {
                "source": self.path_var.get().strip(),
                "geometry_source": geometry_source or self.path_var.get().strip(),
                "fragment_A_indices_1based": [i + 1 for i in self.fragment_a_indices],
                "fragment_B_indices_1based": [i + 1 for i in self.fragment_b_indices],
                "fragment_A_formula": formula_for_indices(structure, self.fragment_a_indices),
                "fragment_B_formula": formula_for_indices(structure, self.fragment_b_indices),
                "jobs": [spec["name"] for spec in specs],
            }
            (root / "fragment_definition.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

            self.fragment_status_var.set(f"Generated {len(specs)} interaction job folders in {root}")
            self.append_monitor(f"Interaction jobs created in: {root}\nJobs: {', '.join(spec['name'] for spec in specs)}")
            self.status.configure(text=f"Interaction job folders created: {root}")
        except Exception as exc:
            self.fragment_status_var.set(str(exc))
            messagebox.showerror("Interaction job generation", str(exc))

    def append_monitor(self, message: str, clear: bool = False):
        if clear:
            self.monitor_text.delete("1.0", "end")
        if message:
            if not message.endswith("\n"):
                message += "\n"
            self.monitor_text.insert("end", message)
            self.monitor_text.see("end")

    def report_validation(self, errors, warnings, solvent):
        lines = ["=== Validation ==="]
        if solvent:
            lines.append(f"Resolved solvent: {solvent['canonical']} -> ORCA:{solvent['orca']} | Gaussian:{solvent['gaussian']}")
        if errors:
            lines.append("Errors:")
            lines.extend(f"  - {x}" for x in errors)
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {x}" for x in warnings)
        if not errors and not warnings:
            lines.append("Validation finished: no issues found by the built-in library.")
        self.append_monitor("\n".join(lines))
        return "\n".join(lines)

    def build_input(self):
        structure = self.parse_current_structure()
        data = self.collect()
        return self._build_input_from_data(structure, data)

    def _build_input_from_data(self, structure: Structure, data: Dict):
        errors, warnings, solvent = validate_engine_choices(data["program"], data["functional"], data["basis"], data["solvent_text"])
        if data.get("job_wfn_wfx") and data["program"] != "ORCA":
            warnings.append("WFN/WFX generation is available only for ORCA runs via orca_2aim.")
        if errors:
            self.report_validation(errors, warnings, solvent)
            raise ValueError("\n".join(errors))
        text = generate_orca(data, structure, solvent) if data["program"] == "ORCA" else generate_gaussian(data, structure, solvent)
        generator_warnings = list(data.get("_warnings", []))
        merged_warnings = list(warnings)
        for item in generator_warnings:
            if item not in merged_warnings:
                merged_warnings.append(item)
        self.report_validation(errors, merged_warnings, solvent)
        return text, merged_warnings

    def _build_input_worker(self, path: str, data: Dict):
        try:
            structure = StructureParser.parse(path)
            errors, warnings, solvent = validate_engine_choices(data["program"], data["functional"], data["basis"], data["solvent_text"])
            if data.get("job_wfn_wfx") and data["program"] != "ORCA":
                warnings.append("WFN/WFX generation is available only for ORCA runs via orca_2aim.")
            if errors:
                raise ValueError("\n".join(errors))
            text = generate_orca(data, structure, solvent) if data["program"] == "ORCA" else generate_gaussian(data, structure, solvent)
            generator_warnings = list(data.get("_warnings", []))
            merged_warnings = list(warnings)
            for item in generator_warnings:
                if item not in merged_warnings:
                    merged_warnings.append(item)
            self.after(0, lambda: self._finish_preview(structure, text, merged_warnings, solvent))
        except Exception as exc:
            self.after(0, lambda exc=exc: self._fail_preview(exc))

    def _finish_preview(self, structure: Structure, text: str, warnings: List[str], solvent: Optional[Dict[str, str]]):
        self.preview_thread = None
        self.structure = structure
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.report_validation([], warnings, solvent)
        status = "Input preview generated."
        if warnings:
            status += " Warnings present."
            self.append_monitor("Preview generated with validation warnings.")
        self.status.configure(text=status)

    def _fail_preview(self, exc: Exception):
        self.preview_thread = None
        self.append_monitor(f"Preview error: {exc}")
        self.status.configure(text="Preview failed.")
        messagebox.showerror("Preview error", str(exc))

    def preview(self):
        if self.preview_thread and self.preview_thread.is_alive():
            self.status.configure(text="Preview is already running.")
            return
        try:
            path = self.path_var.get().strip()
            if not path:
                raise ValueError("Please choose an XYZ, CIF, or ORCA input file.")
            data = self.collect()
            self.status.configure(text="Generating input preview...")
            self.preview_thread = threading.Thread(target=self._build_input_worker, args=(path, data), daemon=True)
            self.preview_thread.start()
        except Exception as exc:
            self._fail_preview(exc)

    def suggest_input_save_path(self) -> str:
        src = self.path_var.get().strip()
        src_path = Path(src) if src else Path.cwd() / "job.xyz"
        base = src_path.stem if src else "job"

        data = self.collect()
        functional = data.get("functional", "").strip().replace(" ", "")
        basis = data.get("basis", "").strip().replace(" ", "")
        solvent_text = data.get("solvent_text", "").strip()

        parts = [base]
        if functional:
            parts.append(functional)
        if basis:
            parts.append(basis)

        if solvent_text:
            resolved = resolve_solvent(solvent_text)
            if resolved:
                solvent_cmd = resolved["orca"] if self.program_var.get() == "ORCA" else resolved["gaussian"]
            else:
                solvent_cmd = solvent_text.replace(" ", "")
            if solvent_cmd:
                parts.append(solvent_cmd)

        if self.freeze_all_var.get() or self.freeze_heavy_var.get():
            parts.append("constr")
        elif self.job_opt_var.get():
            parts.append("opt")
        else:
            parts.append("sp")

        ext = ".inp" if self.program_var.get() == "ORCA" else ".gjf"
        return str(src_path.with_name("_".join(parts) + ext))

    def get_preview_text(self) -> str:
        return self.preview_text.get("1.0", "end-1c")

    def ensure_input_saved(self) -> Optional[str]:
        selected_path = self.path_var.get().strip().strip('"')
        if self._is_existing_orca_input_path(selected_path):
            if self.current_input_path != selected_path or not self.get_preview_text().strip():
                self._load_existing_orca_input_if_selected()
            return selected_path

        text = self.get_preview_text()
        if not text.strip():
            text, warnings = self.build_input()
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", text)
            if warnings:
                self.append_monitor("Validation warnings were detected before saving.")
        out_path = self.current_input_path
        if not out_path or not os.path.isfile(out_path):
            out_path = filedialog.asksaveasfilename(
                defaultextension=".inp" if self.program_var.get() == "ORCA" else ".gjf",
                initialfile=os.path.basename(self.suggest_input_save_path()),
                initialdir=os.path.dirname(self.suggest_input_save_path()),
                filetypes=[("Input files", "*.inp *.gjf *.com"), ("All files", "*.*")]
            )
            if not out_path:
                return None
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.get_preview_text())
        self.current_input_path = out_path
        self.status.configure(text=f"Saved preview text: {out_path}")
        return out_path

    def save_input(self):
        try:
            text = self.get_preview_text()
            if not text.strip():
                text, warnings = self.build_input()
                self.preview_text.delete("1.0", "end")
                self.preview_text.insert("1.0", text)
                if warnings:
                    self.append_monitor("Validation warnings were detected before saving.")
            suggested = self.suggest_input_save_path()
            out = filedialog.asksaveasfilename(
                defaultextension=".inp" if self.program_var.get() == "ORCA" else ".gjf",
                initialfile=os.path.basename(suggested),
                initialdir=os.path.dirname(suggested),
                filetypes=[("Input files", "*.inp *.gjf *.com"), ("All files", "*.*")]
            )
            if not out:
                return
            with open(out, "w", encoding="utf-8") as f:
                f.write(self.get_preview_text())
            self.current_input_path = out
            self.status.configure(text=f"Saved preview text: {out}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def run_orca(self):
        try:
            self.auto_open_output_var.set(True)
            if self.program_var.get() != "ORCA":
                raise ValueError("Run ORCA is available only when Program = ORCA.")
            if self.run_process and self.run_process.poll() is None:
                raise ValueError("An ORCA run is already in progress.")
            orca_path = self.orca_path_var.get().strip().strip('"')
            if not orca_path:
                self.auto_locate_orca(silent=True)
                orca_path = self.orca_path_var.get().strip().strip('"')
            if not orca_path or not os.path.isfile(orca_path):
                raise ValueError("ORCA executable was not found. Please locate `orca` / `orca.exe` manually.")
            ok, reason = validate_orca_qm_executable(orca_path)
            if not ok:
                self.orca_path_var.set("")
                raise ValueError(
                    "The configured executable is not valid ORCA quantum chemistry:\n"
                    f"{orca_path}\n\n{reason}\n\n"
                    "Please select the real ORCA QM executable, for example /opt/orca*/orca or ~/programs/orca_*/orca."
                )
            inp_path = self.ensure_input_saved()
            if not inp_path:
                return
            out_path = str(Path(inp_path).with_suffix(".out"))
            self.last_output_path = out_path
            args = [orca_path, os.path.basename(inp_path)]
            workdir = os.path.dirname(inp_path) or os.getcwd()
            self.active_run_context = {
                "interaction_enabled": bool(self.job_interaction_var.get()),
                "interaction_relax": bool(self.interaction_relax_var.get()),
                "interaction_thermo": bool(self.interaction_thermo_var.get()),
                "interaction_cp": True,
                "fragment_a_indices": list(self.fragment_a_indices),
                "fragment_b_indices": list(self.fragment_b_indices),
                "frag_a_charge": int(self.frag_a_charge_var.get()),
                "frag_a_mult": int(self.frag_a_mult_var.get()),
                "frag_b_charge": int(self.frag_b_charge_var.get()),
                "frag_b_mult": int(self.frag_b_mult_var.get()),
                "input_path": inp_path,
                "orca_path": orca_path,
                "data": self.collect(),
                "dimer_optimized": bool(self.job_opt_var.get()),
            }
            interaction_warnings = self._preflight_interaction_context(self.active_run_context)

            self.clear_monitor(reset_status=False)
            for warning in interaction_warnings:
                self.append_monitor(f"Interaction warning: {warning}")
            self.monitor_started_at = time.time()
            self.monitor_offset = 0
            self._set_monitor_stage("Starting ORCA")
            self.status.configure(text="Starting ORCA...")

            fout = open(out_path, "w", encoding="utf-8", errors="replace")
            try:
                self.run_process = subprocess.Popen(
                    args,
                    cwd=workdir,
                    env=subprocess_env_with_executable_dir(orca_path),
                    stdout=fout,
                    stderr=subprocess.STDOUT,
                    shell=False
                )
            finally:
                fout.close()

            self.append_monitor(f"$ {' '.join(args)}\nWorking directory: {workdir}\nOutput file: {out_path}\n\n")
            self._schedule_monitor_poll()
        except Exception as exc:
            self.active_run_context = None
            messagebox.showerror("Run error", str(exc))

    def _schedule_monitor_poll(self):
        if self.monitor_job_id:
            try:
                self.after_cancel(self.monitor_job_id)
            except Exception:
                pass
        self.monitor_job_id = self.after(1000, self.poll_job_monitor)

    def poll_job_monitor(self):
        self.monitor_job_id = None
        out_path = self.last_output_path
        if out_path and os.path.isfile(out_path):
            try:
                with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.monitor_offset)
                    chunk = f.read()
                    self.monitor_offset = f.tell()
                if chunk:
                    self.append_monitor(chunk)
                    stage = self.parse_orca_stage(chunk)
                    if stage:
                        self._set_monitor_stage(stage)
            except Exception:
                pass

        if self.monitor_started_at:
            elapsed = max(0, int(time.time() - self.monitor_started_at))
            hh = elapsed // 3600
            mm = (elapsed % 3600) // 60
            ss = elapsed % 60
            self.monitor_elapsed_label.configure(text=f"Elapsed: {hh:02d}:{mm:02d}:{ss:02d}")

        proc = self.run_process
        if proc is not None:
            code = proc.poll()
            if code is None:
                self._schedule_monitor_poll()
                return
            self.run_process = None
            self._run_finished(code, out_path or "")
            return

    def parse_orca_stage(self, text: str) -> Optional[str]:
        t = text.upper()
        stage_checks = [
            ("ORCA TERMINATED NORMALLY", "Finished normally"),
            ("ORCA FINISHED BY ERROR TERMINATION", "Error termination"),
            ("ABORTING THE RUN", "Error termination"),
            ("GEOMETRY OPTIMIZATION CYCLE", "Geometry optimization"),
            ("ORCA GEOMETRY OPTIMIZATION", "Geometry optimization"),
            ("VIBRATIONAL FREQUENCIES", "Frequency calculation"),
            ("TD-DFT/TDA EXCITED STATES", "TD-DFT excited states"),
            ("ORBITAL ENERGIES", "SCF / orbital analysis"),
            ("SCF ITERATION", "SCF iterations"),
            ("STARTING SCF", "SCF start"),
            ("CARTESIAN GRADIENT", "Gradient evaluation"),
            ("CHEMICAL SHIELDINGS", "NMR property calculation"),
        ]
        for needle, stage in stage_checks:
            if needle in t:
                return stage
        return None

    def _set_monitor_stage(self, stage: str):
        self.monitor_status_text = stage
        self.monitor_stage_label.configure(text=f"Status: {stage}")


    def clear_monitor(self, reset_status: bool = True):
        self.monitor_text.delete("1.0", "end")
        self.monitor_offset = 0
        if reset_status:
            self.monitor_started_at = None
            self.monitor_elapsed_label.configure(text="Elapsed: 00:00:00")
            self._set_monitor_stage("Idle")

    def stop_orca(self):
        proc = self.run_process
        if proc is None or proc.poll() is not None:
            messagebox.showinfo("Stop job", "No running ORCA job was found.")
            return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
        except Exception as exc:
            messagebox.showerror("Stop job error", str(exc))
            return
        self._set_monitor_stage("Stopping job")
        self.status.configure(text="Stopping ORCA job...")
        self._schedule_monitor_poll()

    def open_last_output(self):
        try:
            out_path = self._available_output_path()
        except Exception as exc:
            messagebox.showinfo("Open .out", str(exc))
            return
        try:
            open_path_in_system(out_path)
        except Exception as exc:
            messagebox.showerror("Open .out error", str(exc))

    def open_last_output_folder(self):
        folder = self._active_working_folder()
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Open folder", "No output folder is available yet.")
            return
        try:
            open_path_in_system(folder)
        except Exception as exc:
            messagebox.showerror("Open folder error", str(exc))

    def _find_orca_2aim(self) -> str:
        orca_path = self.orca_path_var.get().strip().strip('"')
        candidates: List[str] = []
        if orca_path:
            orca_dir = os.path.dirname(orca_path)
            candidates.extend([
                os.path.join(orca_dir, "orca_2aim.exe"),
                os.path.join(orca_dir, "orca_2aim"),
            ])
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        raise FileNotFoundError("orca_2aim was not found in the same folder as the ORCA executable.")

    def run_orca_2aim(self, out_path: str) -> str:
        if self.program_var.get() != "ORCA":
            self.append_monitor("WFN/WFX generation was requested, but the selected program is not ORCA.\n")
            return ""
        gbw_path = str(Path(out_path).with_suffix(".gbw"))
        if not os.path.isfile(gbw_path):
            raise FileNotFoundError(f"GBW file was not found: {gbw_path}")
        orca_2aim_path = self._find_orca_2aim()
        base_name = Path(gbw_path).stem
        workdir = str(Path(gbw_path).parent)
        self.append_monitor(f"\n=== WFN/WFX generation via orca_2aim ===\nExecutable: {orca_2aim_path}\nBase name: {base_name}\nWorking directory: {workdir}\n")
        proc = subprocess.run(
            [orca_2aim_path, base_name],
            cwd=workdir,
            env=subprocess_env_with_executable_dir(orca_2aim_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False
        )
        if proc.stdout:
            self.append_monitor(proc.stdout)
        wfn_path = str(Path(workdir) / f"{base_name}.wfn")
        wfx_path = str(Path(workdir) / f"{base_name}.wfx")
        missing = [p for p in (wfn_path, wfx_path) if not os.path.isfile(p)]
        if proc.returncode != 0:
            raise RuntimeError(f"orca_2aim finished with exit code {proc.returncode}.")
        if missing:
            raise FileNotFoundError("orca_2aim finished, but the expected file(s) were not created: " + ", ".join(missing))
        self.append_monitor(f"Generated: {wfn_path}\nGenerated: {wfx_path}\n")
        return wfn_path

    def run_esp_cube_generation(self, wavefunction_path: str):
        if not wavefunction_path:
            wavefunction_path = self._matching_wavefunction_path(self.last_output_path)
        script = Path(self.esp_script_var.get().strip().strip('"'))
        if not script.is_file():
            raise FileNotFoundError(f"ESP script was not found: {script}")
        if not os.path.isfile(wavefunction_path):
            raise FileNotFoundError(f"Wavefunction file was not found: {wavefunction_path}")

        py_parts = self._python_command_parts(self.esp_python_var.get())
        command = py_parts + [
            str(script),
            str(wavefunction_path),
            "-mode=old",
            "-vis=n",
            "--generate-only",
        ]
        workdir = str(Path(wavefunction_path).parent)
        self.append_monitor(
            "\n=== ESP/MEP cube generation via Multiwfn ===\n"
            f"Wavefunction: {wavefunction_path}\n"
            f"Script: {script}\n"
            f"Working directory: {workdir}\n"
        )
        proc = subprocess.run(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
        )
        if proc.stdout:
            self.append_monitor(proc.stdout)
        if proc.returncode != 0:
            raise RuntimeError(f"ESP/MEP cube generation finished with exit code {proc.returncode}.")

        base = str(Path(wavefunction_path).with_suffix(""))
        dens_cube = base + "_Dens.cub"
        esp_cube = base + "_ESP.cub"
        missing = [path for path in (dens_cube, esp_cube) if not os.path.isfile(path)]
        if missing:
            raise FileNotFoundError("ESP/MEP cube generation finished, but expected cube file(s) were not created: " + ", ".join(missing))
        self.append_monitor(f"Generated/reused: {dens_cube}\nGenerated/reused: {esp_cube}\n")

    def _run_finished(self, code: int, out_path: str):
        if self.monitor_job_id:
            try:
                self.after_cancel(self.monitor_job_id)
            except Exception:
                pass
            self.monitor_job_id = None
        context = self.active_run_context or {}
        output_ok, output_reason = validate_orca_output_file(out_path)
        if code == 0 and output_ok:
            post_messages = []
            interaction_summary = None
            interaction_root = None
            interaction_error = ""
            context.setdefault("post_processing", {})
            if self.job_esp_mep_var.get():
                try:
                    self._set_monitor_stage("Generating WFN/WFX")
                    wavefunction_path = self.run_orca_2aim(out_path)
                    context["post_processing"]["wfn_wfx_generated"] = True
                    context["post_processing"]["wavefunction_path"] = wavefunction_path
                    post_messages.append("WFN/WFX generation completed.")
                    self._set_monitor_stage("Generating ESP/MEP cubes")
                    self.run_esp_cube_generation(wavefunction_path)
                    context["post_processing"]["esp_mep_generated"] = True
                    post_messages.append("ESP/MEP cube generation completed.")
                except Exception as exc:
                    context["post_processing"]["esp_mep_error"] = str(exc)
                    post_messages.append(f"ESP/MEP post-processing failed: {exc}")
                    self.append_monitor(f"ESP/MEP post-processing failed: {exc}\n")
            if context.get("interaction_enabled"):
                try:
                    self._set_monitor_stage("Interaction workflow")
                    interaction_summary, interaction_root = self._run_interaction_pipeline(out_path, context)
                    post_messages.append(f"Interaction workflow completed: {interaction_root}")
                    warnings = interaction_summary.get("warnings", [])
                    if warnings:
                        post_messages.extend(warnings)
                except Exception as exc:
                    interaction_error = str(exc)
                    post_messages.append(f"Interaction workflow failed: {exc}")
                    self.append_monitor(f"Interaction workflow failed: {exc}\n")
            try:
                calc_summary = self._build_calculation_summary(context, out_path)
                summary_path, summary_text = self._write_project_summary(out_path, calc_summary, interaction_summary, interaction_error)
                post_messages.append(f"Summary saved: {summary_path}")
                self.append_monitor(f"\n=== Project summary ===\nSaved: {summary_path}\n\n{summary_text}")
            except Exception as exc:
                post_messages.append(f"Project summary could not be created: {exc}")
                self.append_monitor(f"Project summary could not be created: {exc}\n")
            self._set_monitor_stage("Finished normally")
            status = f"ORCA finished. Output: {out_path}"
            if post_messages:
                status += " | " + " ".join(post_messages)
            self.status.configure(text=status)
            if os.path.isfile(out_path):
                try:
                    open_path_in_system(out_path)
                except Exception:
                    pass
            message = f"Exit code: {code}\nOutput file:\n{out_path}"
            if post_messages:
                message += "\n\n" + "\n".join(post_messages)
            messagebox.showinfo("ORCA finished", message)
        else:
            self._set_monitor_stage(f"Finished with exit code {code}")
            message = (
                "ORCA calculation did not run successfully. The configured executable is not ORCA QM or the calculation failed. "
                "Downstream analysis was not launched."
            )
            detail = f"Exit code: {code}\nOutput check: {output_reason}\nOutput: {out_path}"
            self.append_monitor("\n" + message + "\n" + detail + "\n")
            self.status.configure(text=message)
            messagebox.showwarning("ORCA finished with errors", message + "\n\n" + detail)
        self.active_run_context = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
