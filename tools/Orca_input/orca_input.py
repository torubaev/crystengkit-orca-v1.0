from __future__ import annotations

import math
import os
import base64
import importlib.util
import datetime
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import json
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass

try:
    import numpy as np
except Exception:
    np = None

pv = None
_pyvista_import_error = None
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Dict, List, Optional, Tuple

try:
    import gemmi  # optional, preferred CIF parser
except Exception:
    gemmi = None

TOOLS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TOOLS_ROOT.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from app_identity import configure_tk_window_identity, set_windows_app_id
from orca_job_queue import OrcaJobQueue, OrcaQueueJob

LAUNCHER_SETTINGS_PATH = Path(__file__).with_name("orca_gaussian_builder_settings.json")
DEFAULT_HOMO_LUMO_SCRIPT = TOOLS_ROOT / "HOMO_LUMO" / "HOMO_LUMO_v2.py"
DEFAULT_ESP_SCRIPT = TOOLS_ROOT / "VisMap_5.0" / "VisMap5.6_pyvista.py"
DEFAULT_NCI_SCRIPT = TOOLS_ROOT / "NCI_plot" / "nci_plotter.py"
DEFAULT_QTAIM_SCRIPT = TOOLS_ROOT / "qtaim-cp" / "qtaim.py"
DEFAULT_TD_DFT_SCRIPT = TOOLS_ROOT / "TD_DFT" / "td_dft_module.py"
APP_VERSION = "1.0.0"
STARTUP_NEWS_URL = "https://raw.githubusercontent.com/torubaev/crystengkit-orca-v1.0/main/app_metadata/startup_news.json"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
CONTACT_EMAIL = "torubaev(at)gmail.com"
LINKEDIN_URL = "https://www.linkedin.com/in/torubaev/"
README_LINK_TEXT = "README section: ORCA Input Builder"
README_ANCHOR = "orca-input-builder"
CITATION_REFERENCE = (
    "Torubaev, Y. CrystEngKit-ORCA: practical GUI tools for ORCA and "
    "Multiwfn calculations in supramolecular chemistry and crystal engineering, "
    "version 1.0; GitHub, 2026. https://github.com/torubaev/crystengkit-orca-v1.0"
)
CITATION_TEXT = f"Cite as: {CITATION_REFERENCE}"


def wiki_url() -> str:
    return GITHUB_URL + f"#{README_ANCHOR}"


def open_readme_or_wiki():
    webbrowser.open(wiki_url(), new=2)


def startup_news_cache_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "CrystEngKit-ORCA"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "CrystEngKit-ORCA"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "CrystEngKit-ORCA"


STARTUP_NEWS_CACHE_PATH = startup_news_cache_dir() / "startup_news_cache.json"
STARTUP_NEWS_SETTINGS_PATH = startup_news_cache_dir() / "startup_news_settings.json"
STARTUP_NEWS_TIMEOUT = 1.8
STARTUP_NEWS_TITLE_LIMIT = 90
STARTUP_NEWS_MESSAGE_LIMIT = 520
STARTUP_SPLASH_MIN_VISIBLE_MS = 10000


def safe_read_json(path: Path) -> Optional[Dict]:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def safe_write_json(path: Path, data: Dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    except Exception:
        pass


def normalize_news_text(value: object, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        text = text[: max(0, limit - 3)].rstrip() + "..."
    return text


def parse_iso_date(value: object) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except Exception:
        return None


def semantic_version_tuple(value: object) -> Tuple[int, int, int]:
    parts = re.findall(r"\d+", str(value or ""))[:3]
    nums = [int(part) for part in parts]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def is_valid_news_url(url: str) -> bool:
    return bool(re.match(r"^https?://", str(url or "").strip(), re.IGNORECASE))


def validate_startup_news(raw: object) -> Dict:
    if not isinstance(raw, dict):
        return {"title": "Startup news", "message": "No current online news available.", "severity": "info"}
    force_show = bool(raw.get("force_show", False))
    severity = str(raw.get("severity", "info")).strip().lower()
    if severity not in {"info", "warning", "critical"}:
        severity = "info"
    message_id = normalize_news_text(raw.get("message_id", ""), 120)
    show_until = normalize_news_text(raw.get("show_until", ""), 20)
    if show_until and not force_show:
        until_date = parse_iso_date(show_until)
        if until_date and datetime.date.today() > until_date:
            return {"title": "Startup news", "message": "No current online news available.", "severity": "info", "expired": True}

    title = normalize_news_text(raw.get("title", "Startup news"), STARTUP_NEWS_TITLE_LIMIT) or "Startup news"
    message = normalize_news_text(raw.get("message", "No current online news available."), STARTUP_NEWS_MESSAGE_LIMIT)
    latest_version = normalize_news_text(raw.get("latest_version", ""), 32)
    if latest_version and semantic_version_tuple(latest_version) > semantic_version_tuple(APP_VERSION):
        message = normalize_news_text(f"Update available: version {latest_version}. {message}", STARTUP_NEWS_MESSAGE_LIMIT)
    details_url = normalize_news_text(raw.get("details_url", ""), 240)
    if not is_valid_news_url(details_url):
        details_url = ""
    return {
        "schema": raw.get("schema", 1),
        "latest_version": latest_version,
        "release_date": normalize_news_text(raw.get("release_date", ""), 20),
        "title": title,
        "message": message or "No current online news available.",
        "details_url": details_url,
        "severity": severity,
        "message_id": message_id,
        "show_until": show_until,
        "force_show": force_show,
    }


def load_startup_news_settings() -> Dict:
    data = safe_read_json(STARTUP_NEWS_SETTINGS_PATH)
    if not isinstance(data, dict):
        return {"dismissed_message_ids": []}
    dismissed = data.get("dismissed_message_ids", [])
    if not isinstance(dismissed, list):
        dismissed = []
    return {"dismissed_message_ids": [str(item) for item in dismissed[:200]]}


def save_dismissed_startup_message(message_id: str) -> None:
    if not message_id:
        return
    settings = load_startup_news_settings()
    dismissed = list(dict.fromkeys(settings.get("dismissed_message_ids", []) + [message_id]))
    safe_write_json(STARTUP_NEWS_SETTINGS_PATH, {"dismissed_message_ids": dismissed[-200:]})


def load_cached_startup_news() -> Optional[Dict]:
    cached = safe_read_json(STARTUP_NEWS_CACHE_PATH)
    return validate_startup_news(cached) if cached else None


def load_development_startup_news() -> Optional[Dict]:
    local_path = APP_ROOT / "app_metadata" / "startup_news.json"
    local = safe_read_json(local_path)
    return validate_startup_news(local) if local else None


def fetch_startup_news() -> Dict:
    try:
        request = urllib.request.Request(STARTUP_NEWS_URL, headers={"User-Agent": "CrystEngKit-ORCA"})
        with urllib.request.urlopen(request, timeout=STARTUP_NEWS_TIMEOUT) as response:
            payload = response.read(20000).decode("utf-8", errors="replace")
        raw = json.loads(payload)
        news = validate_startup_news(raw)
        safe_write_json(STARTUP_NEWS_CACHE_PATH, raw if isinstance(raw, dict) else news)
        return news
    except Exception:
        if os.environ.get("CRYSTENGKIT_STARTUP_NEWS_DEV_FALLBACK") == "1":
            development_news = load_development_startup_news()
            if development_news:
                return development_news
        return load_cached_startup_news() or {
            "title": "Startup news",
            "message": "No current online news available.",
            "severity": "info",
            "message_id": "",
            "force_show": False,
            "details_url": "",
        }


class StartupSplash:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.closed = False
        self.news: Dict = {}
        self.require_continue = False
        self.ready = False
        self.created_at = time.monotonic()
        self.window = tk.Toplevel(master)
        self.window.title("CrystEngKit-ORCA")
        self.window.geometry("520x320")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        configure_tk_window_identity(self.window, "Startup", BUILDER_ICON_ICO_PATH)
        self.logo_image = None
        self._build()
        self._center()
        self.progress.start(12)
        self.set_status("Starting CrystEngKit-ORCA...")
        self.master.after(STARTUP_SPLASH_MIN_VISIBLE_MS, self._allow_close)
        self.fetch_thread = threading.Thread(target=self._fetch_news_worker, daemon=True)
        self.fetch_thread.start()

    def _build(self):
        outer = ttk.Frame(self.window, padding=16)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        if ORCA_ICON_PATH.is_file():
            try:
                self.logo_image = tk.PhotoImage(file=str(ORCA_ICON_PATH))
                self.logo_image = self.logo_image.subsample(max(1, self.logo_image.width() // 54), max(1, self.logo_image.height() // 54))
                ttk.Label(header, image=self.logo_image).pack(side="left", padx=(0, 12))
            except Exception:
                self.logo_image = None
        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="CrystEngKit-ORCA", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(title_box, text="ORCA Input Builder", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(1, 0))
        ttk.Label(title_box, text=f"Version: {APP_VERSION}", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(18, 4))
        self.status_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w")

        news_box = ttk.LabelFrame(outer, text="News", padding=10)
        news_box.pack(fill="both", expand=True, pady=(12, 8))
        self.news_title_var = tk.StringVar(value="Checking online news...")
        self.news_message_var = tk.StringVar(value="")
        ttk.Label(news_box, textvariable=self.news_title_var, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(news_box, textvariable=self.news_message_var, wraplength=465, justify="left").pack(anchor="w", fill="x", pady=(4, 0))

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")
        self.dismiss_var = tk.BooleanVar(value=False)
        self.release_button = ttk.Button(bottom, text="Open release page", command=self.open_details, state="disabled")
        self.release_button.pack(side="left")
        ttk.Checkbutton(bottom, text="Don't show this message again", variable=self.dismiss_var).pack(side="left", padx=(12, 0))
        self.close_button = ttk.Button(bottom, text="Close", command=self.close)
        self.close_button.pack(side="right")

    def _allow_close(self):
        if self.closed:
            return
        if self.ready and not self.require_continue:
            self.close()

    def _center(self):
        try:
            self.window.update_idletasks()
            width = self.window.winfo_width()
            height = self.window.winfo_height()
            x = (self.window.winfo_screenwidth() - width) // 2
            y = (self.window.winfo_screenheight() - height) // 2
            self.window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def set_status(self, text: str):
        if not self.closed:
            try:
                self.status_var.set(text)
                self.window.update_idletasks()
            except Exception:
                pass

    def _fetch_news_worker(self):
        news = fetch_startup_news()
        try:
            self.master.after(0, lambda: self.apply_news(news))
        except Exception:
            pass

    def apply_news(self, news: Dict):
        if self.closed:
            return
        self.news = validate_startup_news(news)
        settings = load_startup_news_settings()
        dismissed = set(settings.get("dismissed_message_ids", []))
        message_id = self.news.get("message_id", "")
        force_show = bool(self.news.get("force_show"))
        if message_id and message_id in dismissed and not force_show:
            self.news_title_var.set("Startup news")
            self.news_message_var.set("This startup message was dismissed earlier.")
        else:
            self.news_title_var.set(self.news.get("title", "Startup news"))
            self.news_message_var.set(self.news.get("message", "No current online news available."))
        details_url = self.news.get("details_url", "")
        self.release_button.configure(state="normal" if is_valid_news_url(details_url) else "disabled")
        self.require_continue = force_show or self.news.get("severity") == "critical"
        self.set_status("Checking online news...")

    def open_details(self):
        url = self.news.get("details_url", "")
        if is_valid_news_url(url):
            try:
                webbrowser.open(url, new=2)
            except Exception:
                pass

    def builder_ready(self):
        if self.closed:
            return
        self.ready = True
        try:
            self.progress.stop()
        except Exception:
            pass
        self.set_status("Ready.")
        try:
            self.window.attributes("-topmost", False)
        except Exception:
            pass
        if not self.require_continue:
            elapsed_ms = int((time.monotonic() - self.created_at) * 1000)
            remaining_ms = max(0, STARTUP_SPLASH_MIN_VISIBLE_MS - elapsed_ms)
            self.master.after(remaining_ms, self.close)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.dismiss_var.get():
            save_dismissed_startup_message(str(self.news.get("message_id", "")))
        try:
            self.progress.stop()
        except Exception:
            pass
        try:
            self.window.destroy()
        except Exception:
            pass


ENDNOTE_CITATION_RE = re.compile(r"\s*\[[^\[\]\r\n]{1,180}#[0-9]+[^\[\]\r\n]*\]")


def remove_endnote_citation_tokens(text: str) -> str:
    """Remove temporary EndNote citation placeholders from generated prose."""
    cleaned = ENDNOTE_CITATION_RE.sub("", text)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned
ICON_DIR = TOOLS_ROOT / "images"
ORCA_ICON_PATH = ICON_DIR / "tr_orca_icon.png"
HOMO_LUMO_ICON_PATH = ICON_DIR / "tr_homo_lumo_icon.png"
ESP_ICON_PATH = ICON_DIR / "tr_ESP_icon.png"
NCI_ICON_PATH = ICON_DIR / "tr_NCI_icon.png"
QTAIM_ICON_PATH = ICON_DIR / "qtaim.png"
BUILDER_ICON_ICO_PATH = ICON_DIR / "orca_builder.ico"
HARTREE_TO_KCAL_MOL = 627.509474
HARTREE_TO_KJ_MOL = 2625.49962
MONITOR_READ_CHARS_PER_POLL = 65536
MONITOR_POLL_DELAY_MS = 1000
MONITOR_CATCHUP_DELAY_MS = 50
MONITOR_BUFFER_MAX_CHARS = 750000
MONITOR_BUFFER_TRIM_TO_CHARS = 600000
FILE_SEARCH_MAX_SECONDS = 1.5
FILE_SEARCH_MAX_MATCHES = 80
FILE_SEARCH_MAX_DEPTH = 4
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


def require_pyvista():
    """Import PyVista only when a builder preview actually needs it."""
    global pv, _pyvista_import_error
    if pv is not None:
        return pv
    try:
        import pyvista as pv_module
    except Exception as exc:
        _pyvista_import_error = exc
        raise ValueError(f"PyVista is required for the molecule viewer but could not be imported: {exc}") from exc
    pv = pv_module
    _pyvista_import_error = None
    return pv


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
        plotter.set_background(background)
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


def bring_pyvista_window_to_front(plotter, delay_s: float = 0.25) -> None:
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
ELEMENT_BY_ATOMIC_NUMBER = {idx + 1: sym for idx, sym in enumerate(ELEMENT_SYMBOLS)}
BOHR_TO_ANGSTROM = 0.529177210903
OPEN_BABEL_TIMEOUT = 45.0
OPEN_BABEL_EXTENSIONS = {".mol", ".sdf", ".sd", ".cml", ".cdxml", ".cdx", ".ct"}
GAUSSIAN_INPUT_EXTENSIONS = {".gjf", ".com", ".gau", ".gjc"}
OUTPUT_STRUCTURE_EXTENSIONS = {".out", ".log"}
STRUCTURE_INPUT_EXTENSIONS = {".xyz", ".cif", ".inp"} | OPEN_BABEL_EXTENSIONS | GAUSSIAN_INPUT_EXTENSIONS | OUTPUT_STRUCTURE_EXTENSIONS

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
    canonical = KNOWN_SOLVENT_ALIAS_MAP.get(key)
    if canonical is not None:
        data = SOLVENT_LIBRARY[canonical]
        return {"canonical": canonical, "orca": str(data["orca"]), "gaussian": str(data["gaussian"])}
    if key not in ORCA_SMD_SOLVENT_NORMALIZED:
        return None
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


def clean_gaussian_atom_label(raw: str) -> str:
    token = raw.strip().strip(",")
    if not token:
        raise ValueError("Empty Gaussian atom label.")
    if token.lstrip("+-").isdigit():
        number = int(token)
        if number not in ELEMENT_BY_ATOMIC_NUMBER:
            raise ValueError(f"Unknown atomic number: {token}")
        return ELEMENT_BY_ATOMIC_NUMBER[number]
    token = re.split(r"[-_(]", token, maxsplit=1)[0]
    return clean_symbol(token)


def xyz_text_from_atoms(atoms: List[Tuple[str, float, float, float]], title: str = "Converted structure") -> str:
    return "\n".join([str(len(atoms)), title, xyz_block_from_atoms(atoms)]) + "\n"


def validate_xyz_text(text: str, source: str = "XYZ") -> Structure:
    if not text or not text.strip():
        raise ValueError(f"{source}: normalized XYZ output is empty.")
    raw_lines = text.splitlines()
    if not raw_lines:
        raise ValueError(f"{source}: normalized XYZ output is empty.")
    try:
        atom_count = int(raw_lines[0].strip())
    except Exception as exc:
        raise ValueError(f"{source}: first XYZ line must be a positive atom count.") from exc
    if atom_count <= 0:
        raise ValueError(f"{source}: XYZ atom count must be positive.")
    if len(raw_lines) < atom_count + 2:
        raise ValueError(f"{source}: XYZ has fewer coordinate lines than declared.")
    coord_lines = raw_lines[2:2 + atom_count]
    atoms: List[Tuple[str, float, float, float]] = []
    for line_number, line in enumerate(coord_lines, start=3):
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"{source}: invalid XYZ atom line {line_number}: {line}")
        try:
            sym = clean_symbol(parts[0])
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        except Exception as exc:
            raise ValueError(f"{source}: invalid XYZ atom line {line_number}: {line}") from exc
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError(f"{source}: non-finite coordinate on line {line_number}.")
        atoms.append((sym, x, y, z))
    if len(atoms) != atom_count:
        raise ValueError(f"{source}: XYZ header says {atom_count}, parsed {len(atoms)} atoms.")
    return Structure(atoms, title=raw_lines[1].strip() if len(raw_lines) > 1 else source)


@dataclass
class ImportResult:
    structure: Structure
    normalized_xyz: str
    source_path: str
    source_format: str
    title: str
    charge: Optional[int] = None
    multiplicity: Optional[int] = None
    warnings: Optional[List[str]] = None
    log_lines: Optional[List[str]] = None


@dataclass
class GaussianSection:
    index: int
    route: str
    title: str
    charge: Optional[int]
    multiplicity: Optional[int]
    atoms: List[Tuple[str, float, float, float]]
    coordinate_type: str
    units: str
    warnings: List[str]
    requires_openbabel: bool = False
    checkpoint_dependent: bool = False
    text: str = ""


def structure_input_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".xyz":
        return "XYZ"
    if ext == ".cif":
        return "CIF"
    if ext == ".inp":
        return "ORCA input"
    if ext in OUTPUT_STRUCTURE_EXTENSIONS:
        return "Quantum chemistry output"
    if ext in OPEN_BABEL_EXTENSIONS:
        return ext[1:].upper()
    if ext in GAUSSIAN_INPUT_EXTENSIONS:
        return "Gaussian input"
    raise ValueError(
        "Supported structure files: .xyz, .cif, ORCA .inp, ORCA/Gaussian .out/.log, .mol, .sdf/.sd, .cml, .cdxml, .cdx, .ct, and Gaussian .gjf/.com/.gau/.gjc."
    )


def looks_like_2d_structure(structure: Structure, tolerance: float = 1e-6) -> bool:
    if len(structure.atoms) < 2:
        return False
    return all(abs(z) <= tolerance for _sym, _x, _y, z in structure.atoms)


def sanitize_subprocess_error(text: str, limit: int = 1200) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] + ("..." if len(cleaned) > limit else "")


def validate_openbabel_executable(path: str, timeout: float = 5.0) -> Tuple[bool, str]:
    candidate = Path(str(path).strip().strip('"')).expanduser()
    if not candidate.is_file():
        return False, "file does not exist"
    expected = "obabel.exe" if os.name == "nt" else "obabel"
    if candidate.name.lower() != expected:
        return False, f"executable name is not {expected}"
    try:
        result = subprocess.run(
            [str(candidate), "-V"],
            cwd=str(candidate.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            errors="replace",
        )
    except Exception as exc:
        return False, f"could not run Open Babel: {exc}"
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0:
        return False, f"Open Babel version check failed with exit code {result.returncode}: {sanitize_subprocess_error(output)}"
    if "Open Babel" not in output and "OpenBabel" not in output:
        return False, "version output does not look like Open Babel"
    return True, output.splitlines()[0] if output else "Open Babel"


def find_openbabel_on_path() -> str:
    exe_name = "obabel.exe" if os.name == "nt" else "obabel"
    found = shutil.which(exe_name)
    return found or ""


def run_openbabel_to_xyz(
    obabel_path: str,
    source_path: str,
    input_format: Optional[str] = None,
    generate_3d: bool = False,
    record_index: Optional[int] = None,
    timeout: float = OPEN_BABEL_TIMEOUT,
) -> Tuple[str, List[str]]:
    fmt_args: List[str] = []
    if input_format:
        fmt_args = [f"-i{input_format.lower()}", source_path]
    else:
        fmt_args = [source_path]
    command = [obabel_path] + fmt_args
    if record_index is not None:
        command += ["-f", str(record_index), "-l", str(record_index)]
    if generate_3d:
        command += ["-h", "--gen3d"]
    command += ["-oxyz"]
    start = time.time()
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        errors="replace",
    )
    elapsed = time.time() - start
    logs = [
        "Open Babel command: " + repr(command),
        f"Open Babel return code: {proc.returncode}; duration: {elapsed:.2f} s",
    ]
    if proc.returncode != 0:
        raise RuntimeError(f"Open Babel conversion failed: {sanitize_subprocess_error(proc.stderr or proc.stdout)}")
    xyz_text = proc.stdout or ""
    validate_xyz_text(xyz_text, "Open Babel XYZ")
    return xyz_text, logs


def sdf_record_chunks(text: str) -> List[str]:
    chunks = re.split(r"^\$\$\$\$\s*$", text, flags=re.MULTILINE)
    return [chunk for chunk in chunks if chunk.strip()]


def mol_counts_line_index(lines: List[str]) -> int:
    for idx, line in enumerate(lines[:12]):
        if "V2000" in line.upper() or "V3000" in line.upper():
            return idx
    if len(lines) >= 4:
        return 3
    raise ValueError("MOL/SDF file is too short to contain a counts line.")


def parse_mol_v2000_atoms(text: str, source: str = "MOL/SDF") -> Tuple[List[Tuple[str, float, float, float]], str]:
    lines = text.splitlines()
    counts_idx = mol_counts_line_index(lines)
    counts_line = lines[counts_idx]
    if "V3000" in counts_line.upper():
        raise ValueError(f"{source}: V3000 MOL/SDF files still require Open Babel.")

    try:
        atom_count = int(counts_line[0:3])
    except Exception:
        parts = counts_line.split()
        if not parts:
            raise ValueError(f"{source}: missing atom count in MOL/SDF counts line.")
        try:
            atom_count = int(parts[0])
        except Exception as exc:
            raise ValueError(f"{source}: invalid atom count in MOL/SDF counts line.") from exc

    if atom_count <= 0:
        raise ValueError(f"{source}: MOL/SDF atom count must be positive.")

    start = counts_idx + 1
    atom_lines = lines[start:start + atom_count]
    if len(atom_lines) < atom_count:
        raise ValueError(f"{source}: MOL/SDF has fewer atom lines than declared.")

    atoms: List[Tuple[str, float, float, float]] = []
    for line_number, line in enumerate(atom_lines, start=start + 1):
        try:
            x = float(line[0:10])
            y = float(line[10:20])
            z = float(line[20:30])
            sym = clean_symbol(line[31:34].strip())
        except Exception:
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"{source}: invalid MOL/SDF atom line {line_number}: {line}")
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                sym = clean_symbol(parts[3])
            except Exception as exc:
                raise ValueError(f"{source}: invalid MOL/SDF atom line {line_number}: {line}") from exc
        if not all(math.isfinite(v) for v in (x, y, z)):
            raise ValueError(f"{source}: non-finite coordinate on atom line {line_number}.")
        atoms.append((sym, x, y, z))

    title = next((line.strip() for line in lines[:counts_idx] if line.strip()), source)
    return atoms, title


def mol_sdf_to_xyz_text(path: str, record_index: Optional[int] = None) -> Tuple[str, str, List[str]]:
    source_path = Path(path)
    ext = source_path.suffix.lower()
    source_format = ext[1:].upper()
    text = source_path.read_text(encoding="utf-8", errors="replace")
    log_lines = [f"Source format: {source_format}", "Direct parser: native MOL/SDF"]

    if ext in {".sdf", ".sd"}:
        records = sdf_record_chunks(text)
        log_lines.append(f"SDF records detected: {len(records)}")
        if not records:
            raise ValueError("SDF file did not contain any records.")
        selected_index = record_index or 1
        if selected_index < 1 or selected_index > len(records):
            raise ValueError(f"SDF record {selected_index} is not available.")
        text = records[selected_index - 1]
        log_lines.append(f"Selected SDF record: {selected_index}")

    atoms, title = parse_mol_v2000_atoms(text, source_format)
    xyz_text = xyz_text_from_atoms(atoms, title or source_path.name)
    validate_xyz_text(xyz_text, source_format)
    log_lines.append(f"Atom count: {len(atoms)}")
    return xyz_text, title or source_path.name, log_lines


def count_sdf_records(path: str) -> List[Dict[str, object]]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    chunks = sdf_record_chunks(text)
    records: List[Dict[str, object]] = []
    for idx, chunk in enumerate(chunks, start=1):
        lines = chunk.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        title = next((line.strip() for line in lines if line.strip()), f"Record {idx}")
        atom_count: Optional[int] = None
        if len(lines) >= 4:
            m = re.match(r"\s*(\d+)\s+(\d+)", lines[3])
            if m:
                atom_count = int(m.group(1))
        records.append({"index": len(records) + 1, "title": title, "atom_count": atom_count})
    return records


def split_gaussian_link1_sections(text: str) -> List[str]:
    return [part for part in re.split(r"^\s*--Link1--\s*$", text, flags=re.IGNORECASE | re.MULTILINE) if part.strip()]


def _next_nonempty(lines: List[str], start: int) -> int:
    idx = start
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    return idx


def _gaussian_route_has_bohr(route: str) -> bool:
    route_lower = route.lower()
    return bool(re.search(r"\b(bohr|au|units\s*=\s*(bohr|au|atomic))\b", route_lower))


def _gaussian_route_checkpoint_geometry(route: str) -> bool:
    return bool(re.search(r"\bgeom\s*=\s*\(?\s*(check|allcheck)", route, flags=re.IGNORECASE))


def _parse_gaussian_cartesian_line(line: str) -> Tuple[str, float, float, float, List[str]]:
    parts = line.replace(",", " ").split()
    if len(parts) < 4:
        raise ValueError("not enough fields")
    symbol = clean_gaussian_atom_label(parts[0])
    warnings: List[str] = []
    coord_start = 1
    if len(parts) >= 5:
        try:
            int(parts[1])
            float(parts[2])
            float(parts[3])
            float(parts[4])
            coord_start = 2
            warnings.append("Gaussian freeze-code fields were discarded.")
        except Exception:
            coord_start = 1
    x, y, z = float(parts[coord_start]), float(parts[coord_start + 1]), float(parts[coord_start + 2])
    extras = parts[coord_start + 3:]
    if extras:
        warnings.append("Gaussian atom-line annotations were discarded.")
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise ValueError("non-finite coordinate")
    return symbol, x, y, z, warnings


def parse_gaussian_input_text(text: str, source_name: str = "Gaussian input") -> List[GaussianSection]:
    sections: List[GaussianSection] = []
    for section_index, section_text in enumerate(split_gaussian_link1_sections(text), start=1):
        lines = [line.rstrip("\n") for line in section_text.splitlines()]
        idx = 0
        while idx < len(lines) and lines[idx].lstrip().startswith("%"):
            idx += 1
        idx = _next_nonempty(lines, idx)
        route_lines: List[str] = []
        while idx < len(lines):
            stripped = lines[idx].strip()
            if not stripped:
                if route_lines:
                    idx += 1
                    break
                idx += 1
                continue
            if not stripped.startswith("#") and route_lines:
                break
            route_lines.append(stripped)
            idx += 1
        route = " ".join(route_lines)
        idx = _next_nonempty(lines, idx)
        title_lines: List[str] = []
        while idx < len(lines) and lines[idx].strip():
            title_lines.append(lines[idx].strip())
            idx += 1
        title = " ".join(title_lines).strip() or f"{source_name} section {section_index}"
        idx = _next_nonempty(lines, idx)

        charge: Optional[int] = None
        multiplicity: Optional[int] = None
        if idx < len(lines):
            cm = re.match(r"^\s*([+-]?\d+)\s+(\d+)\b", lines[idx])
            if cm:
                charge = int(cm.group(1))
                multiplicity = int(cm.group(2))
                idx += 1

        atoms: List[Tuple[str, float, float, float]] = []
        warnings: List[str] = []
        requires_openbabel = False
        checkpoint_dependent = _gaussian_route_checkpoint_geometry(route)
        coordinate_type = "none"
        units = "bohr" if _gaussian_route_has_bohr(route) else "angstrom"
        saw_noncartesian = False
        while idx < len(lines):
            raw = lines[idx]
            stripped = raw.strip()
            if not stripped:
                break
            if stripped.startswith("!"):
                idx += 1
                continue
            try:
                atom = _parse_gaussian_cartesian_line(stripped)
            except Exception:
                first = stripped.split()[0] if stripped.split() else ""
                try:
                    clean_gaussian_atom_label(first)
                    looks_like_atom_start = True
                except Exception:
                    looks_like_atom_start = False
                if looks_like_atom_start:
                    saw_noncartesian = True
                break
            else:
                sym, x, y, z, line_warnings = atom
                atoms.append((sym, x, y, z))
                warnings.extend(line_warnings)
                idx += 1

        if atoms:
            coordinate_type = "Cartesian"
            if units == "bohr":
                atoms = [(sym, x * BOHR_TO_ANGSTROM, y * BOHR_TO_ANGSTROM, z * BOHR_TO_ANGSTROM) for sym, x, y, z in atoms]
                warnings.append("Gaussian coordinates declared in bohr/atomic units were converted to angstrom.")
        elif saw_noncartesian:
            coordinate_type = "Z-matrix"
            requires_openbabel = True
        elif checkpoint_dependent:
            coordinate_type = "checkpoint"

        sections.append(
            GaussianSection(
                index=section_index,
                route=route,
                title=title,
                charge=charge,
                multiplicity=multiplicity,
                atoms=atoms,
                coordinate_type=coordinate_type,
                units=units,
                warnings=sorted(set(warnings)),
                requires_openbabel=requires_openbabel,
                checkpoint_dependent=checkpoint_dependent,
                text=section_text,
            )
        )
    return sections


def gaussian_sections_with_geometry(sections: List[GaussianSection]) -> List[GaussianSection]:
    return [section for section in sections if section.atoms or section.requires_openbabel]


def parse_gaussian_output_charge_multiplicity(text: str) -> Tuple[Optional[int], Optional[int]]:
    matches = re.findall(r"Charge\s*=\s*([+-]?\d+)\s+Multiplicity\s*=\s*(\d+)", text, flags=re.IGNORECASE)
    if not matches:
        return None, None
    charge_text, mult_text = matches[-1]
    try:
        return int(charge_text), int(mult_text)
    except Exception:
        return None, None


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


ATOM_COLORS = {
    "H": "#E8E8E8", "C": "#5F5F5F", "N": "#2B48D8", "O": "#CC0000",
    "F": "#82CC49", "P": "#E67300", "S": "#E6E62B", "Cl": "#1CD91C",
    "Br": "#982626", "I": "#850085", "B": "#EAA6A6", "Si": "#DDB88F",
    "Pd": "#005F78", "Pt": "#BFC0CE", "Ru": "#218282", "Rh": "#097382",
    "Ir": "#154D7B", "Fe": "#CC5D2F", "Co": "#DC8493", "Ni": "#49BF49",
    "Cu": "#B8752F", "Zn": "#7376A2", "Ag": "#B0B0B0", "Au": "#EABB20",
    "Hg": "#A9A9BF", "Li": "#BA75EA", "Na": "#9D55DE", "K": "#833BC2",
    "Mg": "#7ED900", "Ca": "#38E800", "Al": "#AF9999", "Sn": "#5E7575",
    "Pb": "#575961", "Se": "#EA9400", "Te": "#C27000", "Cd": "#EAC781",
    "Ga": "#B28484", "Ge": "#5E8383", "As": "#AD76D0", "Ti": "#AFB2B7",
    "V": "#99999E", "Cr": "#7F8CB7", "Mn": "#8F70B7",
}
MOLECULE_BOND_COLOR = "#8E8E8E"
MOLECULE_FRAGMENT_BOND_COLOR = "#8E8E8E"
MOLECULE_FALLBACK_COLOR = "#E95FA5"


def get_atom_color(symbol: str) -> Tuple[int, int, int]:
    hex_color = ATOM_COLORS.get(symbol, MOLECULE_FALLBACK_COLOR).lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def molecule_atom_color(symbol: str) -> str:
    return ATOM_COLORS.get(symbol, MOLECULE_FALLBACK_COLOR)


def molecule_bond_end_color(symbol: str) -> str:
    return MOLECULE_BOND_COLOR if clean_symbol(symbol) in {"C", "H"} else molecule_atom_color(clean_symbol(symbol))


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
        color=color if color is not None else molecule_atom_color(symbol),
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


SUBSCRIPT_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def formula_with_subscripts(formula: str) -> str:
    return formula.translate(SUBSCRIPT_DIGITS)


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
        if ext in OUTPUT_STRUCTURE_EXTENSIONS:
            return StructureParser.parse_output_geometry(path)
        raise ValueError("Supported input files: .xyz, .cif, ORCA .inp, or ORCA/Gaussian .out/.log")

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
    def parse_gaussian_output_final_geometry(path: str) -> Structure:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        last_atoms: List[Tuple[str, float, float, float]] = []
        last_label = ""
        idx = 0
        while idx < len(lines):
            label = lines[idx].strip()
            if label not in {"Standard orientation:", "Input orientation:"}:
                idx += 1
                continue
            dashed_seen = 0
            j = idx + 1
            while j < len(lines) and dashed_seen < 2:
                if set(lines[j].strip()) <= {"-"} and lines[j].strip():
                    dashed_seen += 1
                j += 1
            atoms: List[Tuple[str, float, float, float]] = []
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:
                    j += 1
                    continue
                if set(stripped) <= {"-"}:
                    break
                parts = stripped.split()
                if len(parts) >= 6:
                    try:
                        atomic_number = int(parts[1])
                        symbol = ELEMENT_BY_ATOMIC_NUMBER.get(atomic_number)
                        if not symbol:
                            raise ValueError(f"Unknown atomic number: {atomic_number}")
                        atoms.append((symbol, float(parts[3]), float(parts[4]), float(parts[5])))
                    except Exception:
                        if atoms:
                            break
                elif atoms:
                    break
                j += 1
            if atoms:
                last_atoms = atoms
                last_label = label.rstrip(":")
            idx = max(j + 1, idx + 1)

        if not last_atoms:
            raise ValueError("No Gaussian Standard/Input orientation coordinate table was found in the output file.")
        return Structure(last_atoms, title=f"{os.path.basename(path)} (final Gaussian {last_label.lower()})")

    @staticmethod
    def parse_output_geometry(path: str) -> Structure:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        upper = text.upper()
        if _looks_like_gnome_orca(text):
            raise ValueError("This file appears to be from the GNOME Orca screen reader, not ORCA quantum chemistry.")
        if any(marker in upper for marker in ORCA_QM_IDENTITY_MARKERS) or "CARTESIAN COORDINATES (ANGSTROEM)" in upper:
            return StructureParser.parse_orca_output_final_geometry(path)
        if "STANDARD ORIENTATION:" in upper or "INPUT ORIENTATION:" in upper or "GAUSSIAN" in upper:
            return StructureParser.parse_gaussian_output_final_geometry(path)
        try:
            return StructureParser.parse_orca_output_final_geometry(path)
        except Exception as orca_exc:
            try:
                return StructureParser.parse_gaussian_output_final_geometry(path)
            except Exception as gaussian_exc:
                raise ValueError(
                    "Output file was not recognized as a readable ORCA or Gaussian output.\n"
                    f"ORCA parser: {orca_exc}\nGaussian parser: {gaussian_exc}"
                ) from gaussian_exc

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


def basis_supports_orca_rijcosx(basis: str) -> bool:
    normalized = re.sub(r"[\s_]+", "", str(basis or "").strip()).lower()
    return normalized.startswith("def2-") or normalized.startswith("def2") or normalized.startswith("ma-def2")


def generate_orca(data: Dict, structure: Structure, solvent: Optional[Dict[str, str]]) -> str:
    grid_kw, grid_warnings = normalize_orca_grid_keyword(data.get("grid", ""))
    if grid_warnings:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + grid_warnings
    disp_kw, disp_warnings = resolve_dispersion_keyword("ORCA", data.get("dispersion", ""))
    if disp_warnings:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + disp_warnings
    tddft_settings = data.get("tddft_settings") or {}
    tddft_optimization = bool(data.get("job_tddft") and tddft_settings.get("excited_state_optimization"))
    tddft_frequencies = bool(data.get("job_tddft") and tddft_settings.get("excited_state_frequencies"))
    effective_opt = bool(data["job_opt"] or tddft_optimization)
    effective_freq = bool(data["job_freq"] or tddft_frequencies)
    kw = [data["functional"], data["basis"]]
    if disp_kw:
        kw.append(disp_kw)
    use_rijcosx = bool(data["ri_jcosx"]) and basis_supports_orca_rijcosx(data.get("basis", ""))
    if data["ri_jcosx"] and not use_rijcosx:
        existing = data.get("_warnings", [])
        data["_warnings"] = existing + [
            f'RIJCOSX was omitted because basis "{data.get("basis", "")}" is not a def2-family ORCA basis.'
        ]
    if use_rijcosx:
        kw.extend(["def2/J", "RIJCOSX"])
    if data["tight_scf"]:
        kw.append("TightSCF")
    if grid_kw:
        kw.append(grid_kw)
    if effective_opt:
        kw.append("Opt")
    if effective_freq:
        kw.append("Freq")
    if data["job_density"] or data["job_esp"]:
        kw.append("KeepDens")
    if data["job_sp"] and not data["job_opt"] and not data["job_freq"] and not data["job_tddft"] and not data["job_nmr"]:
        kw.append("SP")

    lines = ["! " + " ".join(kw)]
    # --- Constraints (auto-generated) ---
    if effective_opt:
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


    if data["job_tddft"] and data.get("tddft_block", "").strip():
        lines += ["", data["tddft_block"].strip()]

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


def bounded_find_files(
    root: Path,
    names: Optional[Tuple[str, ...]] = None,
    pattern_suffix: str = "",
    max_depth: int = FILE_SEARCH_MAX_DEPTH,
    max_matches: int = FILE_SEARCH_MAX_MATCHES,
    max_seconds: float = FILE_SEARCH_MAX_SECONDS,
) -> List[Path]:
    root = Path(root)
    if not root.is_dir():
        return []
    expected = {name.lower() for name in (names or ())}
    suffix = pattern_suffix.lower()
    start = time.monotonic()
    matches: List[Path] = []
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root, followlinks=False):
        if time.monotonic() - start > max_seconds or len(matches) >= max_matches:
            break
        current_path = Path(current)
        depth = max(0, len(current_path.parts) - root_depth)
        if depth >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = [
                item for item in dirs
                if item not in {"$Recycle.Bin", "System Volume Information", "__pycache__", ".git"}
            ]
        for filename in files:
            lower = filename.lower()
            if expected and lower not in expected:
                continue
            if suffix and not lower.endswith(suffix):
                continue
            matches.append(current_path / filename)
            if len(matches) >= max_matches:
                break
    return matches


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
            for p in bounded_find_files(root, names=("orca.exe", "orca")):
                add(str(p))
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
            for p in bounded_find_files(root, names=("orca.exe", "orca")):
                add(str(p))
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


class ModeTextProxy:
    def __init__(self, app: "App", mode: str):
        self.app = app
        self.mode = mode

    def _widget(self):
        return self.app.output_text

    def _is_active(self) -> bool:
        return self.app.output_mode == self.mode

    def _set_buffer_from_widget(self) -> None:
        self.app.output_buffers[self.mode] = self._widget().get("1.0", "end-1c")

    def _set_buffer(self, text: str) -> None:
        if self.mode == "monitor" and len(text) > MONITOR_BUFFER_MAX_CHARS:
            trim_start = max(0, len(text) - MONITOR_BUFFER_TRIM_TO_CHARS)
            newline = text.find("\n", trim_start)
            if newline != -1:
                trim_start = newline + 1
            text = "[Monitor truncated older output to keep the GUI responsive. Full ORCA output remains in the .out file.]\n" + text[trim_start:]
            if self._is_active():
                self._widget().delete("1.0", "end")
                self._widget().insert("1.0", text)
                self._widget().see("end")
        self.app.output_buffers[self.mode] = text

    def delete(self, start, end=None):
        if self._is_active():
            self._widget().delete(start, end)
            self._set_buffer_from_widget()
        else:
            self.app.output_buffers[self.mode] = ""

    def insert(self, index, chars, *args):
        chars = str(chars)
        if self._is_active():
            self._widget().insert(index, chars, *args)
        current = self.app.output_buffers.get(self.mode, "")
        if str(index) == "1.0":
            self._set_buffer(chars + current)
        else:
            self._set_buffer(current + chars)

    def get(self, start, end=None):
        if self._is_active():
            return self._widget().get(start, end)
        return self.app.output_buffers.get(self.mode, "")

    def configure(self, **kwargs):
        if "wrap" in kwargs:
            self.app.output_wraps[self.mode] = kwargs["wrap"]
        if self._is_active():
            self._widget().configure(**kwargs)

    config = configure

    def cget(self, key):
        if key == "wrap":
            return self.app.output_wraps.get(self.mode, "none")
        return self._widget().cget(key)

    def see(self, index):
        if self._is_active():
            self._widget().see(index)


class App(tk.Tk):
    def __init__(self):
        set_windows_app_id("Builder")
        super().__init__()
        self.withdraw()
        self.title("ORCA input builder")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = max(760, int(screen_w * 0.70))
        win_h = max(1, int(screen_h * 0.80))
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(760, min(700, win_h))
        self._configure_styles()

        self.structure: Optional[Structure] = None
        self.structure_source_path: str = ""
        self.current_input_path: Optional[str] = None
        self.last_output_path: Optional[str] = None
        self.run_thread: Optional[threading.Thread] = None
        self.run_process: Optional[subprocess.Popen] = None
        self.monitor_job_id: Optional[str] = None
        self.monitor_offset: int = 0
        self.monitor_started_at: Optional[float] = None
        self.monitor_status_text: str = "Idle"
        self.monitor_progress_value: float = 0.0
        self.active_run_context: Optional[Dict] = None
        self.queue_state_path: Optional[Path] = None
        self.job_queue = OrcaJobQueue()
        self.queue_running = False
        self.active_queue_job: Optional[OrcaQueueJob] = None
        self.queue_window: Optional[tk.Toplevel] = None
        self.queue_tree: Optional[ttk.Treeview] = None
        self.queue_name_var = tk.StringVar(value=self.job_queue.active_queue)
        self.queue_combo: Optional[ttk.Combobox] = None
        self.preview_thread: Optional[threading.Thread] = None
        self.last_helper_launch_key: Optional[Tuple[str, ...]] = None
        self.last_helper_launch_time: float = 0.0
        self.current_tddft_block = ""
        self.current_tddft_settings: Dict = {}
        self.tddft_window: Optional[tk.Toplevel] = None
        self.tddft_sync_status_var = tk.StringVar(value="TD-DFT: Not configured")

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
        self.job_tddft_var.trace_add("write", lambda *args: self._on_tddft_toggle())
        self.freeze_heavy_var = tk.BooleanVar(value=False)
        self.freeze_all_var = tk.BooleanVar(value=False)
        self.freeze_heavy_var.trace_add("write", lambda *args: self._sync_constraint_flags("heavy"))
        self.freeze_all_var.trace_add("write", lambda *args: self._sync_constraint_flags("all"))

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
        self.basis_var.trace_add("write", lambda *args: self._sync_rijcosx_for_basis())

        self.orca_path_var = tk.StringVar(value="")
        self.openbabel_path_var = tk.StringVar(value="")
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
        self.output_mode = "preview"
        self.output_buffers = {"preview": "", "monitor": ""}
        self.output_wraps = {"preview": "none", "monitor": "none"}
        self.startup_splash: Optional[StartupSplash] = None

        self.auto_open_output_var.set(True)
        self.startup_splash = self._create_startup_splash()
        self._startup_status("Loading Builder interface...")
        self._apply_app_icon()
        self._build()
        self._startup_status("Loading saved settings...")
        self._load_launcher_settings()
        self.auto_open_output_var.set(True)
        self._startup_status("Checking Python tools...")
        self._use_latest_python_for_tools()
        self._refresh_engine_lists()
        self._startup_status("Locating ORCA...")
        self.auto_locate_orca(silent=True)
        if not Path(self.qtaim_script_var.get().strip()).is_file():
            self.auto_locate_qtaim(silent=True)
        self._report_runtime_environment()
        self._startup_status("Ready.")
        self.deiconify()
        self.after(150, self._finish_startup_splash)


    def _create_startup_splash(self) -> Optional[StartupSplash]:
        try:
            return StartupSplash(self)
        except Exception:
            return None

    def _startup_status(self, text: str):
        try:
            if self.startup_splash is not None:
                self.startup_splash.set_status(text)
        except Exception:
            pass

    def _finish_startup_splash(self):
        try:
            if self.startup_splash is not None:
                self.startup_splash.builder_ready()
        except Exception:
            pass

    def _apply_app_icon(self):
        try:
            if ORCA_ICON_PATH.is_file():
                with open(ORCA_ICON_PATH, "rb") as f:
                    img = tk.PhotoImage(data=base64.b64encode(f.read()))
                self.window_icon_image = img
                self.iconphoto(True, img)
            configure_tk_window_identity(self, "Builder", BUILDER_ICON_ICO_PATH)
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
        self._add_header_image_action(header, 7, ORCA_ICON_PATH, "TD-DFT", self.launch_td_dft)

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
        right.rowconfigure(0, weight=1)

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

        ttk.Label(setup, text="Gaussian TD roots").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
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
        esp_info = InfoIcon(esp_row, "ESP / MEP package = density retention and automatic ESP/MEP cube generation after a successful ORCA run. WFN/WFX generation is attempted after every successful ORCA run.")
        esp_info.grid(row=0, column=1, padx=(5, 0))
        ttk.Checkbutton(cbox, text="NMR", variable=self.job_nmr_var).grid(row=2, column=0, sticky="w", pady=(0, 3))
        tddft_row = ttk.Frame(cbox)
        tddft_row.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 3))
        ttk.Checkbutton(tddft_row, text="TD-DFT / UV-Vis", variable=self.job_tddft_var).pack(anchor="w")
        ttk.Label(tddft_row, textvariable=self.tddft_sync_status_var, style="Muted.TLabel").pack(anchor="w")
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

        output_box = ttk.LabelFrame(right, text="INPUT PREVIEW / JOB MONITOR", padding=8)
        output_box.grid(row=0, column=0, sticky="nsew")
        output_box.columnconfigure(0, weight=1)
        output_box.rowconfigure(1, weight=1)

        preview_actions = ttk.Frame(output_box)
        preview_actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        preview_actions.columnconfigure(0, weight=1)
        switch_box = ttk.Frame(preview_actions)
        switch_box.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.preview_mode_button = tk.Button(
            switch_box,
            text="Input preview",
            command=self.activate_input_preview,
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=4,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        self.preview_mode_button.grid(row=0, column=0, sticky="w")
        self.monitor_mode_button = tk.Button(
            switch_box,
            text="Job monitor",
            command=lambda: self._show_output_mode("monitor"),
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=4,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        self.monitor_mode_button.grid(row=0, column=1, sticky="w", padx=(3, 0))
        input_actions = ttk.Frame(preview_actions)
        input_actions.grid(row=1, column=0, sticky="ew")
        for column in range(4):
            input_actions.columnconfigure(column, weight=1)
        ttk.Button(input_actions, text="Save input file", command=self.save_input).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(input_actions, text="Add to Queue", command=self.add_current_input_to_queue).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(input_actions, text="Queue Jobs", command=self.open_job_queue).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(input_actions, text="Generate WFN/WFX", command=self.generate_wavefunction_files).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        monhdr = ttk.Frame(output_box)
        monhdr.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        monhdr.columnconfigure(1, weight=1)
        self.monitor_stage_label = ttk.Label(monhdr, text="Status: Idle")
        self.monitor_stage_label.grid(row=0, column=0, sticky="w")
        self.monitor_progress_label = ttk.Label(
            monhdr,
            text=self._format_monitor_progress(0.0),
            font=("Consolas", 9),
        )
        self.monitor_progress_label.grid(row=1, column=0, columnspan=3, sticky="e", pady=(3, 0))
        self.monitor_elapsed_label = ttk.Label(monhdr, text="Elapsed: 00:00:00")
        self.monitor_elapsed_label.grid(row=0, column=2, sticky="e")

        self.output_text = tk.Text(output_box, wrap="none", font=("Consolas", 10), relief="solid", bd=1)
        self.output_text.grid(row=1, column=0, sticky="nsew")
        ys = ttk.Scrollbar(output_box, orient="vertical", command=self.output_text.yview)
        xs = ttk.Scrollbar(output_box, orient="horizontal", command=self.output_text.xview)
        self.output_text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        ys.grid(row=1, column=1, sticky="ns")
        xs.grid(row=2, column=0, sticky="ew")

        monbtn = ttk.Frame(output_box)
        monbtn.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        for i in range(5):
            monbtn.columnconfigure(i, weight=1)
        ttk.Button(monbtn, text="Stop job", command=self.stop_orca).grid(row=0, column=0, sticky="ew")
        ttk.Button(monbtn, text="Open .out", command=self.open_last_output).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(monbtn, text="Open folder", command=self.open_last_output_folder).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(monbtn, text="Show summary", command=self.show_project_summary).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(monbtn, text="Clear monitor", command=self.clear_monitor).grid(row=0, column=4, sticky="ew", padx=(6, 0))
        self.preview_text = ModeTextProxy(self, "preview")
        self.monitor_text = ModeTextProxy(self, "monitor")
        self._refresh_output_mode_buttons()

        footer = ttk.Frame(self, style="Panel.TFrame", padding=(12, 6))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        ttk.Label(footer, text=COPYRIGHT_NOTE, style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.status = ttk.Label(footer, text="", style="Muted.TLabel")
        self._update_interaction_section()

    def _sync_active_output_buffer(self):
        if hasattr(self, "output_text"):
            self.output_buffers[self.output_mode] = self.output_text.get("1.0", "end-1c")

    def _show_output_mode(self, mode: str):
        if mode not in self.output_buffers or mode == self.output_mode:
            return
        self._sync_active_output_buffer()
        self.output_mode = mode
        self.output_text.configure(wrap=self.output_wraps.get(mode, "none"))
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", self.output_buffers.get(mode, ""))
        if mode == "monitor":
            self.output_text.see("end")
        else:
            self.output_text.see("1.0")
        self._refresh_output_mode_buttons()

    def _refresh_output_mode_buttons(self):
        if not hasattr(self, "preview_mode_button"):
            return
        colors = {
            "active_bg": "#1d4ed8",
            "active_fg": "#ffffff",
            "inactive_bg": "#f8fafc",
            "inactive_fg": "#1d4ed8",
        }
        for mode, button in (
            ("preview", self.preview_mode_button),
            ("monitor", self.monitor_mode_button),
        ):
            is_active = mode == self.output_mode
            button.configure(
                bg=colors["active_bg"] if is_active else colors["inactive_bg"],
                fg=colors["active_fg"] if is_active else colors["inactive_fg"],
                activebackground=colors["active_bg"] if is_active else "#e8f0ff",
                activeforeground=colors["active_fg"] if is_active else colors["inactive_fg"],
            )

    def activate_input_preview(self):
        self._show_output_mode("preview")
        self.preview()

    def _on_tddft_toggle(self):
        self._sync_job_target_flags("tddft")
        enabled = bool(self.job_tddft_var.get())
        if enabled:
            try:
                self.open_tddft_module()
            except Exception as exc:
                self.job_tddft_var.set(False)
                messagebox.showerror("TD-DFT", f"Could not open the TD-DFT module:\n{exc}", parent=self)
        else:
            self.clear_tddft_block()
            if self.tddft_window is not None and self.tddft_window.winfo_exists():
                try:
                    self.tddft_window.set_builder_enabled(False)
                except Exception:
                    pass
            if self.path_var.get().strip() and self.program_var.get() == "ORCA":
                try:
                    text = self.refresh_full_orca_input()
                    self.show_full_orca_input(text)
                except Exception as exc:
                    messagebox.showerror("TD-DFT", f"TD-DFT was removed, but the input preview could not be regenerated:\n{exc}", parent=self)

    def _load_tddft_module(self):
        module_name = "crystengkit_td_dft_module"
        cached = sys.modules.get(module_name)
        if cached is not None:
            return cached
        module_path = DEFAULT_TD_DFT_SCRIPT
        if not module_path.is_file():
            raise FileNotFoundError(f"TD-DFT module was not found:\n{module_path}")
        module_dir = str(module_path.parent)
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load TD-DFT module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        return module

    def open_tddft_module(self):
        if self.tddft_window is not None and self.tddft_window.winfo_exists():
            self.tddft_window.set_builder_enabled(bool(self.job_tddft_var.get()), bool(self.current_tddft_block))
            self.tddft_window.set_builder_context(self.get_tddft_global_context())
            self.tddft_window.deiconify(); self.tddft_window.lift(self); self.tddft_window.focus_force()
            return self.tddft_window
        module = self._load_tddft_module()
        initial = dict(self.current_tddft_settings) if self.current_tddft_settings else dict(module.DEFAULT_TDDFT_SETTINGS)
        self.tddft_window = module.open_tddft_window(
            parent=self,
            initial_settings=initial,
            on_apply=self.apply_tddft_from_module,
            on_close=self._on_tddft_window_closed,
            builder_context=self.get_tddft_global_context(),
        )
        self.tddft_window.set_builder_enabled(bool(self.job_tddft_var.get()), bool(self.current_tddft_block))
        self.tddft_window.lift(self); self.tddft_window.focus_force()
        return self.tddft_window

    def get_tddft_global_context(self) -> Dict:
        return {
            "functional": self.functional_var.get().strip(),
            "basis": self.basis_var.get().strip(),
            "solvent": self.solvent_var.get().strip(),
            "charge": int(self.charge_var.get()),
            "multiplicity": int(self.mult_var.get()),
        }

    def _on_tddft_window_closed(self, window):
        if self.tddft_window is window:
            self.tddft_window = None

    def set_tddft_block(self, block: str) -> None:
        cleaned = str(block or "").strip()
        markers = re.findall(r"(?im)^\s*%(?:tddft|cis)\b", cleaned)
        if len(markers) != 1:
            raise ValueError("The synchronized TD-DFT fragment must contain exactly one %tddft or %cis block.")
        self.current_tddft_block = cleaned

    def clear_tddft_block(self) -> None:
        self.current_tddft_block = ""
        self.tddft_sync_status_var.set("TD-DFT: Not configured" if self.job_tddft_var.get() else "TD-DFT: Disabled")

    def refresh_full_orca_input(self) -> str:
        text, _warnings = self.build_input()
        return text

    def show_full_orca_input(self, text: Optional[str] = None) -> None:
        if text is None:
            text = self.refresh_full_orca_input()
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self._show_output_mode("preview")
        self.status.configure(text="Input preview generated with synchronized TD-DFT block.")

    def focus_builder_window(self) -> None:
        self.deiconify(); self.lift(); self.focus_force()

    def apply_tddft_from_module(self, block: str, settings: Dict) -> None:
        if not self.job_tddft_var.get():
            raise ValueError("TD-DFT is disabled in ORCA Input Builder.")
        old_block = self.current_tddft_block
        old_settings = dict(self.current_tddft_settings)
        try:
            self.set_tddft_block(block)
            self.current_tddft_settings = dict(settings)
            text = self.refresh_full_orca_input()
        except Exception:
            self.current_tddft_block = old_block
            self.current_tddft_settings = old_settings
            raise
        self.tddft_sync_status_var.set("TD-DFT: Synchronized")
        self.show_full_orca_input(text)
        self.focus_builder_window()

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
                if self.freeze_heavy_var.get():
                    self.freeze_heavy_var.set(False)
                if self.freeze_all_var.get():
                    self.freeze_all_var.set(False)
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

    def _sync_constraint_flags(self, source: str = ""):
        if getattr(self, "_syncing_constraint_flags", False):
            return
        self._syncing_constraint_flags = True
        try:
            if source == "heavy" and self.freeze_heavy_var.get():
                if self.freeze_all_var.get():
                    self.freeze_all_var.set(False)
            elif source == "all" and self.freeze_all_var.get():
                if self.freeze_heavy_var.get():
                    self.freeze_heavy_var.set(False)

            if self.freeze_heavy_var.get() or self.freeze_all_var.get():
                if self.job_sp_var.get():
                    self.job_sp_var.set(False)
                if not self.job_opt_var.get():
                    self.job_opt_var.set(True)
        finally:
            self._syncing_constraint_flags = False

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

    def _sync_rijcosx_for_basis(self):
        try:
            if self.program_var.get() != "ORCA":
                self.ri_jcosx_var.set(False)
                return
            self.ri_jcosx_var.set(basis_supports_orca_rijcosx(self.basis_var.get()))
        except Exception:
            pass

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
        self._sync_rijcosx_for_basis()

    def _parse_xyz_through_existing_loader(self, xyz_text: str, title: str) -> Structure:
        validate_xyz_text(xyz_text, title)
        with tempfile.TemporaryDirectory(prefix="crystengkit_import_") as tmpdir:
            xyz_path = Path(tmpdir) / "normalized.xyz"
            xyz_path.write_text(xyz_text, encoding="utf-8")
            structure = StructureParser.parse_xyz(str(xyz_path))
        structure.title = title
        return structure

    def _select_sdf_record(self, records: List[Dict[str, object]]) -> Optional[int]:
        choices = []
        for record in records:
            count = record.get("atom_count")
            count_text = f", atoms: {count}" if count is not None else ""
            choices.append(f"{record['index']}: {record['title']}{count_text}")
        value = simpledialog.askstring(
            "Select SDF record",
            "Multiple SDF records were found. Enter the record number to import:\n\n" + "\n".join(choices[:30]),
            parent=self,
        )
        if value is None:
            return None
        try:
            selected = int(value.strip())
        except Exception as exc:
            raise ValueError("SDF record selection must be a number.") from exc
        valid = {int(record["index"]) for record in records}
        if selected not in valid:
            raise ValueError(f"SDF record {selected} is not available.")
        return selected

    def _select_gaussian_section(self, sections: List[GaussianSection]) -> Optional[GaussianSection]:
        choices = []
        for section in sections:
            route = section.route[:70] + ("..." if len(section.route) > 70 else "")
            choices.append(
                f"{section.index}: {section.title} | {section.coordinate_type} | "
                f"charge {section.charge}, mult {section.multiplicity} | atoms {len(section.atoms) or 'via Open Babel'} | {route}"
            )
        value = simpledialog.askstring(
            "Select Gaussian section",
            "Several Gaussian Link1 sections contain geometry. Enter the section number to import:\n\n" + "\n".join(choices[:20]),
            parent=self,
        )
        if value is None:
            return None
        try:
            selected = int(value.strip())
        except Exception as exc:
            raise ValueError("Gaussian section selection must be a number.") from exc
        for section in sections:
            if section.index == selected:
                return section
        raise ValueError(f"Gaussian section {selected} is not available.")

    def _apply_gaussian_charge_multiplicity(self, result: ImportResult) -> bool:
        if result.charge is None or result.multiplicity is None:
            return True
        current_charge = int(self.charge_var.get())
        current_mult = int(self.mult_var.get())
        if current_charge == result.charge and current_mult == result.multiplicity:
            return True
        if current_charge == 0 and current_mult == 1:
            self.charge_var.set(result.charge)
            self.mult_var.set(result.multiplicity)
            return True
        choice = messagebox.askyesnocancel(
            "Gaussian charge/multiplicity",
            "The Gaussian file declares charge/multiplicity "
            f"{result.charge}/{result.multiplicity}, while the builder currently has "
            f"{current_charge}/{current_mult}.\n\n"
            "Yes: use Gaussian values\nNo: keep current values\nCancel: cancel import",
        )
        if choice is None:
            return False
        if choice:
            self.charge_var.set(result.charge)
            self.mult_var.set(result.multiplicity)
        return True

    def _import_openbabel_structure(self, path: str, ext: str) -> ImportResult:
        obabel = self.require_openbabel_path()
        source_format = ext[1:].upper()
        record_index: Optional[int] = None
        log_lines = [f"Source format: {source_format}"]
        if ext in {".sdf", ".sd"}:
            records = count_sdf_records(path)
            log_lines.append(f"SDF records detected: {len(records)}")
            if len(records) > 1:
                selected = self._select_sdf_record(records)
                if selected is None:
                    raise ValueError("SDF import cancelled.")
                record_index = selected
                log_lines.append(f"Selected SDF record: {selected}")

        direct_xyz, logs = run_openbabel_to_xyz(obabel, path, record_index=record_index)
        log_lines.extend(logs)
        direct_structure = validate_xyz_text(direct_xyz, source_format)
        generated_3d = False
        if looks_like_2d_structure(direct_structure):
            proceed = messagebox.askyesno(
                "2D structure detected",
                "The imported structure appears to contain only 2D coordinates. Generate an initial 3D geometry with Open Babel and added hydrogens?\n\n"
                "The result is only an automatically generated starting geometry and is not optimized or experimental.",
            )
            if not proceed:
                raise ValueError("2D-to-3D generation cancelled; current structure was not changed.")
            direct_xyz, logs = run_openbabel_to_xyz(obabel, path, generate_3d=True, record_index=record_index)
            log_lines.extend(logs)
            generated_3d = True
            log_lines.append("Conversion mode: 2D-to-3D generation with hydrogen addition.")
        else:
            log_lines.append("Conversion mode: direct conversion preserving existing coordinates.")
        title = Path(path).name
        if generated_3d:
            title += " (Open Babel generated starting geometry; inspect before calculation)"
        structure = self._parse_xyz_through_existing_loader(direct_xyz, title)
        log_lines.append(f"Atom count: {len(structure.atoms)}")
        return ImportResult(structure, direct_xyz, path, source_format, title, warnings=[], log_lines=log_lines)

    def _import_mol_sdf_structure(self, path: str, ext: str) -> ImportResult:
        source_format = ext[1:].upper()
        record_index: Optional[int] = None
        if ext in {".sdf", ".sd"}:
            records = count_sdf_records(path)
            if len(records) > 1:
                selected = self._select_sdf_record(records)
                if selected is None:
                    raise ValueError("SDF import cancelled.")
                record_index = selected

        xyz_text, title, log_lines = mol_sdf_to_xyz_text(path, record_index=record_index)
        structure = self._parse_xyz_through_existing_loader(xyz_text, title)
        warnings: List[str] = []
        if looks_like_2d_structure(structure):
            warnings.append("MOL/SDF coordinates appear to be flat; imported as-is without 3D generation.")
            log_lines.append("Coordinate note: all Z values are near zero; no 3D generation was attempted.")
        return ImportResult(structure, xyz_text, path, source_format, title, warnings=warnings, log_lines=log_lines)

    def _import_gaussian_structure(self, path: str) -> ImportResult:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        sections = parse_gaussian_input_text(text, Path(path).name)
        geometry_sections = gaussian_sections_with_geometry(sections)
        if not geometry_sections:
            if any(section.checkpoint_dependent for section in sections):
                raise ValueError("Gaussian input uses checkpoint-dependent geometry (Geom=Check/AllCheck) and contains no explicit coordinates.")
            raise ValueError("No explicit Gaussian Cartesian coordinates or Z-matrix geometry was found.")
        section = geometry_sections[0]
        if len(geometry_sections) > 1:
            selected = self._select_gaussian_section(geometry_sections)
            if selected is None:
                raise ValueError("Gaussian section selection cancelled.")
            section = selected

        log_lines = [
            "Source format: Gaussian input",
            f"Selected Gaussian Link1 section: {section.index}",
            f"Gaussian coordinate type: {section.coordinate_type}",
        ]
        warnings = list(section.warnings)
        if section.requires_openbabel:
            obabel = self.require_openbabel_path()
            with tempfile.TemporaryDirectory(prefix="crystengkit_gaussian_") as tmpdir:
                section_path = Path(tmpdir) / (Path(path).stem + "_section.gjf")
                section_path.write_text(section.text, encoding="utf-8")
                xyz_text, logs = run_openbabel_to_xyz(obabel, str(section_path), input_format="g09")
            log_lines.extend(logs)
            warnings.append("Gaussian Z-matrix was converted through Open Babel; inspect the generated geometry before calculation.")
        else:
            if not section.atoms:
                raise ValueError("Selected Gaussian section contains no explicit Cartesian coordinates.")
            xyz_text = xyz_text_from_atoms(section.atoms, section.title)
        if warnings:
            proceed = messagebox.askokcancel(
                "Gaussian import warnings",
                "Some Gaussian-specific information will not be transferred to the ORCA builder:\n\n"
                + "\n".join(sorted(set(warnings)))
                + "\n\nOnly Cartesian coordinates, charge, and multiplicity are imported.",
            )
            if not proceed:
                raise ValueError("Gaussian import cancelled.")
        if section.units == "bohr":
            log_lines.append("Unit conversion: bohr to angstrom.")
        structure = self._parse_xyz_through_existing_loader(xyz_text, section.title)
        log_lines.append(f"Atom count: {len(structure.atoms)}")
        return ImportResult(
            structure,
            xyz_text,
            path,
            "Gaussian input",
            section.title,
            charge=section.charge,
            multiplicity=section.multiplicity,
            warnings=sorted(set(warnings)),
            log_lines=log_lines,
        )

    def _import_output_structure(self, path: str) -> ImportResult:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        upper = text.upper()
        is_orca = any(marker in upper for marker in ORCA_QM_IDENTITY_MARKERS) or "CARTESIAN COORDINATES (ANGSTROEM)" in upper
        is_gaussian = "STANDARD ORIENTATION:" in upper or "INPUT ORIENTATION:" in upper or "GAUSSIAN" in upper
        structure = StructureParser.parse_output_geometry(path)
        xyz_text = xyz_text_from_atoms(structure.atoms, structure.title)
        validate_xyz_text(xyz_text, "Output geometry")
        source_format = "ORCA output" if is_orca else "Gaussian output" if is_gaussian else "Quantum chemistry output"
        charge: Optional[int] = None
        multiplicity: Optional[int] = None
        if source_format == "Gaussian output":
            charge, multiplicity = parse_gaussian_output_charge_multiplicity(text)
        log_lines = [
            f"Source format: {source_format}",
            "Imported geometry: final/last Cartesian coordinates from output file",
            f"Atom count: {len(structure.atoms)}",
        ]
        warnings = [
            "Only Cartesian coordinates were imported from the output file; method, basis, constraints, and other job settings were not transferred."
        ]
        return ImportResult(
            structure,
            xyz_text,
            path,
            source_format,
            structure.title,
            charge=charge,
            multiplicity=multiplicity,
            warnings=warnings,
            log_lines=log_lines,
        )

    def import_structure_file(self, path: str) -> ImportResult:
        ext = Path(path).suffix.lower()
        source_format = structure_input_format(path)
        if ext in {".xyz", ".cif", ".inp"}:
            structure = StructureParser.parse(path)
            xyz_text = xyz_text_from_atoms(structure.atoms, structure.title)
            validate_xyz_text(xyz_text, source_format)
            return ImportResult(
                structure,
                xyz_text,
                path,
                source_format,
                structure.title,
                warnings=[],
                log_lines=[f"Source format: {source_format}", f"Direct parser: {source_format}", f"Atom count: {len(structure.atoms)}"],
            )
        if ext in {".mol", ".sdf", ".sd"}:
            return self._import_mol_sdf_structure(path, ext)
        if ext in OPEN_BABEL_EXTENSIONS:
            return self._import_openbabel_structure(path, ext)
        if ext in GAUSSIAN_INPUT_EXTENSIONS:
            return self._import_gaussian_structure(path)
        if ext in OUTPUT_STRUCTURE_EXTENSIONS:
            return self._import_output_structure(path)
        raise ValueError(f"Unsupported input format: {Path(path).suffix}")

    def browse(self):
        patterns = " ".join("*" + ext for ext in sorted(STRUCTURE_INPUT_EXTENSIONS))
        p = filedialog.askopenfilename(filetypes=[
            ("Supported structure files", patterns),
            ("ORCA queue files", "*.orcaqueue.json *.queue.json *.json"),
            ("XYZ/CIF/ORCA input", "*.xyz *.cif *.inp"),
            ("ORCA/Gaussian output", "*.out *.log"),
            ("MOL/SDF and Open Babel formats", "*.mol *.sdf *.sd *.cml *.cdxml *.cdx *.ct"),
            ("Gaussian input", "*.gjf *.com *.gau *.gjc"),
            ("All files", "*.*"),
        ])
        if not p:
            return
        try:
            if self._maybe_load_job_queue_file(p):
                return
            result = self.import_structure_file(p)
            if not self._apply_gaussian_charge_multiplicity(result):
                return
            self.path_var.set(p)
            self.structure = result.structure
            self.structure_source_path = str(Path(p).resolve())
            self.current_input_path = p if self._is_existing_orca_input_path(p) else None
            self.last_output_path = p if result.source_format == "ORCA output" else self.last_output_path
            self.preview_text.delete("1.0", "end")
            if self.current_input_path:
                self.preview_text.insert("1.0", Path(p).read_text(encoding="utf-8", errors="replace"))
            self._remember_input_file(p)
            for line in result.log_lines or []:
                self.append_monitor(line)
            self.status.configure(text=f"Imported {result.source_format}: {os.path.basename(p)} | atoms: {len(result.structure.atoms)}")
        except Exception as exc:
            messagebox.showerror("Import error", str(exc))

    def _is_existing_orca_input_path(self, path: str) -> bool:
        return bool(path) and path.lower().endswith(".inp") and os.path.isfile(path)

    def _on_input_path_entered(self, _event=None):
        path = self.path_var.get().strip().strip('"')
        if not path or not os.path.isfile(path):
            return
        try:
            if self._maybe_load_job_queue_file(path):
                return
            result = self.import_structure_file(path)
            if not self._apply_gaussian_charge_multiplicity(result):
                return
            self.structure = result.structure
            self.structure_source_path = str(Path(path).resolve())
            self.current_input_path = path if self._is_existing_orca_input_path(path) else None
            self.last_output_path = path if result.source_format == "ORCA output" else self.last_output_path
            if self.current_input_path:
                self._load_existing_orca_input_if_selected()
            else:
                self.preview_text.delete("1.0", "end")
            self._remember_input_file(path)
            for line in result.log_lines or []:
                self.append_monitor(line)
            self.status.configure(text=f"Imported {result.source_format}: {os.path.basename(path)} | atoms: {len(result.structure.atoms)}")
        except Exception as exc:
            messagebox.showerror("Import error", str(exc))

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
        self._show_output_mode("preview")
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
        self.auto_locate_openbabel(silent=True)
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
            openbabel_path = str(data.get("openbabel_executable") or "").strip()
            if openbabel_path:
                ok, _reason = validate_openbabel_executable(openbabel_path)
                if ok:
                    self.openbabel_path_var.set(openbabel_path)
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
            queue_file = str(data.get("queue_file") or "").strip()
            if queue_file:
                queue_path = Path(queue_file).expanduser()
                self.queue_state_path = queue_path
                if queue_path.is_file():
                    self.job_queue = OrcaJobQueue.load(queue_path)
                    self._refresh_queue_selector()
        except Exception as exc:
            self.append_monitor(f"Launcher settings could not be loaded: {exc}\n")

    def _save_launcher_settings(self):
        data = {
            "homo_lumo_script": app_relative_path(self.homo_lumo_script_var.get().strip()),
            "esp_script": app_relative_path(self.esp_script_var.get().strip()),
            "nci_script": app_relative_path(self.nci_script_var.get().strip()),
            "qtaim_script": app_relative_path(self.qtaim_script_var.get().strip()),
            "openbabel_executable": self.openbabel_path_var.get().strip(),
            "python_executable": active_python_command(),
            "esp_python_command": active_python_command(),
            "nci_python_command": active_python_command(),
            "qtaim_python_command": active_python_command(),
            "recent_input_files": self.recent_input_files[:5],
            "queue_file": str(self.queue_state_path) if self.queue_state_path else "",
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

    def browse_openbabel(self):
        expected = "obabel.exe" if os.name == "nt" else "obabel"
        filetypes = [("Open Babel executable", expected)] + executable_filetypes()
        path = filedialog.askopenfilename(title="Select Open Babel executable", filetypes=filetypes)
        if not path:
            return
        ok, reason = validate_openbabel_executable(path)
        if not ok:
            messagebox.showerror("Open Babel executable rejected", f"{path}\n\n{reason}")
            return
        self.openbabel_path_var.set(path)
        self._save_launcher_settings()
        self.append_monitor(f"Open Babel executable saved: {path}\n{reason}\n")

    def auto_locate_openbabel(self, silent: bool = False) -> str:
        candidates: List[str] = []
        saved = self.openbabel_path_var.get().strip().strip('"')
        if saved:
            candidates.append(saved)
        exe_name = "obabel.exe" if os.name == "nt" else "obabel"
        common_roots = [
            Path(os.environ.get("ProgramFiles", "")) / "OpenBabel-3.1.1" / exe_name,
            Path(os.environ.get("ProgramFiles", "")) / "Open Babel-3.1.1" / exe_name,
            Path(os.environ.get("ProgramFiles(x86)", "")) / "OpenBabel-3.1.1" / exe_name,
            Path("/usr/bin") / exe_name,
            Path("/usr/local/bin") / exe_name,
            Path.home() / ".local" / "bin" / exe_name,
        ]
        candidates.extend(str(path) for path in common_roots if str(path).strip())
        path_candidate = find_openbabel_on_path()
        if path_candidate:
            candidates.append(path_candidate)

        seen = set()
        rejected: List[Tuple[str, str]] = []
        for candidate in candidates:
            norm = os.path.normcase(candidate)
            if norm in seen:
                continue
            seen.add(norm)
            ok, reason = validate_openbabel_executable(candidate)
            if ok:
                self.openbabel_path_var.set(candidate)
                if not silent:
                    messagebox.showinfo("Open Babel located", f"{candidate}\n\n{reason}")
                return candidate
            rejected.append((candidate, reason))
        if not silent:
            detail = "\n".join(f"Rejected {path}: {reason}" for path, reason in rejected[:5])
            messagebox.showwarning("Open Babel not found", "No valid Open Babel executable was found automatically." + ("\n\n" + detail if detail else ""))
        return ""

    def require_openbabel_path(self) -> str:
        path = self.auto_locate_openbabel(silent=True)
        if path:
            ok, reason = validate_openbabel_executable(path)
            if ok:
                self.append_monitor(f"Open Babel: {path}\nVersion: {reason}\n")
                return path
        retry = messagebox.askyesno(
            "Open Babel required",
            "This file format requires Open Babel (`obabel`). Browse for the executable now?",
        )
        if not retry:
            raise ValueError("Open Babel is required for this import and was not selected.")
        self.browse_openbabel()
        path = self.openbabel_path_var.get().strip().strip('"')
        ok, reason = validate_openbabel_executable(path)
        if not ok:
            raise ValueError(f"Selected Open Babel executable is not valid:\n{path}\n\n{reason}")
        self.append_monitor(f"Open Babel: {path}\nVersion: {reason}\n")
        return path

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

    def _structure_preview_window_size(self) -> Tuple[int, int]:
        try:
            height = max(1, int(self.winfo_screenheight() * 0.80))
            return height, height
        except Exception:
            return 800, 800

    def open_launcher_settings(self):
        self._auto_locate_launcher_defaults()

        win = tk.Toplevel(self)
        win.title("Launcher settings")
        win.transient(self)
        win.withdraw()
        win.columnconfigure(1, weight=1)

        fields = [
            ("ORCA executable:", self.orca_path_var, self.browse_orca),
            ("Open Babel executable:", self.openbabel_path_var, self.browse_openbabel),
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
                if var is self.orca_path_var or var is self.openbabel_path_var:
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
            ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=8, sticky="n", padx=(0, 18))

        ttk.Label(box, text="Orca input builder", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text="Build ORCA and Gaussian input files from CIF and XYZ structures.", justify="left", wraplength=380).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Separator(box, orient="horizontal").grid(row=2, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text="GitHub", justify="left").grid(row=3, column=1, sticky="w")
        github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2", justify="left")
        github_link.grid(row=4, column=1, sticky="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _e: open_path_in_system(GITHUB_URL))
        ttk.Label(box, text="Documentation", justify="left").grid(row=5, column=1, sticky="w", pady=(8, 0))
        wiki_link = ttk.Label(box, text=README_LINK_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left")
        wiki_link.grid(row=6, column=1, sticky="w", pady=(2, 0))
        wiki_link.bind("<Button-1>", lambda _e: open_readme_or_wiki())
        citation_label = ttk.Label(box, text=CITATION_TEXT, foreground="#1d4ed8", cursor="hand2", justify="left", wraplength=430)
        citation_label.grid(row=7, column=1, sticky="w", pady=(10, 0))
        citation_label.bind("<Button-1>", lambda _e: self._copy_about_citation(win, citation_label))
        ttk.Separator(box, orient="horizontal").grid(row=8, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text=COPYRIGHT_NOTE, foreground="#4b5563").grid(row=9, column=1, sticky="w")
        contact = ttk.Frame(box)
        contact.grid(row=10, column=1, sticky="w", pady=(7, 0))
        ttk.Label(contact, text=f"Email: {CONTACT_EMAIL}").grid(row=0, column=0, sticky="w")
        linkedin_icon = tk.Label(contact, text="in", bg="#0a66c2", fg="white", cursor="hand2", font=("Arial", 9, "bold"), padx=4, pady=1)
        linkedin_icon.grid(row=0, column=1, padx=(10, 0))
        linkedin_icon.bind("<Button-1>", lambda _e: open_path_in_system(LINKEDIN_URL))

        buttons = ttk.Frame(box)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).grid(row=0, column=0)

        win.update_idletasks()
        width = max(570, win.winfo_reqwidth())
        height = max(350, win.winfo_reqheight())
        screen_w = max(1, win.winfo_screenwidth())
        screen_h = max(1, win.winfo_screenheight())
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.resizable(False, False)
        win.deiconify()
        win.lift(self)
        win.focus_force()
        win.grab_set()

    def _copy_about_citation(self, window: tk.Toplevel, label: ttk.Label):
        try:
            window.clipboard_clear()
            window.clipboard_append(CITATION_REFERENCE)
            label.configure(text="Cite as: copied to clipboard", foreground="#047857")
            window.after(1400, lambda: label.configure(text=CITATION_TEXT, foreground="#1d4ed8") if label.winfo_exists() else None)
        except Exception as exc:
            messagebox.showerror("Copy citation", str(exc))

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
                candidates.extend(
                    (2, path) for path in bounded_find_files(source_dir, names=(f"{source.stem}.out",))
                    if path.is_file() and not self._is_interaction_job_path(path)
                )
            except Exception:
                pass

        try:
            candidates.extend(
                (3, path) for path in bounded_find_files(source_dir, pattern_suffix=".out")
                if path.is_file() and not self._is_interaction_job_path(path)
            )
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

    @staticmethod
    def _is_interaction_job_path(path: Path) -> bool:
        return any(part.endswith("_interaction_jobs") for part in path.parts)

    def _same_folder_wavefunction_candidates(self, folder: Path, patterns: Tuple[str, ...]) -> List[Path]:
        candidates: List[Path] = []
        if not folder.is_dir():
            return candidates
        for pattern in patterns:
            candidates.extend(
                path for path in folder.glob(pattern)
                if path.is_file() and not self._is_interaction_job_path(path)
            )
        return candidates

    def _matching_wavefunction_path(self, out_path: str) -> str:
        out_file = Path(out_path)
        same_stem = [out_file.with_suffix(ext) for ext in (".wfn", ".wfx", ".fchk")]
        for candidate in same_stem:
            if candidate.is_file():
                return str(candidate)
        folder = out_file.parent
        candidates = self._same_folder_wavefunction_candidates(folder, ("*.wfn", "*.wfx", "*.fchk"))
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
        candidates = self._same_folder_wavefunction_candidates(folder, ("*.wfx", "*.wfn"))
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
            candidates = self._same_folder_wavefunction_candidates(folder, ("*.wfx", "*.wfn"))
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
        candidates = self._same_folder_wavefunction_candidates(folder, ("*.wfx", "*.wfn"))
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
            candidates = self._same_folder_wavefunction_candidates(folder, ("*.wfx", "*.wfn"))
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
        py_parts = self._python_command_parts(python_command or active_python_command())
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

    def launch_td_dft(self):
        try:
            if not self.job_tddft_var.get():
                self.job_tddft_var.set(True)
            else:
                self.open_tddft_module()
        except Exception as exc:
            messagebox.showerror("TD-DFT launcher", str(exc))

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
            raise ValueError("Please choose a supported structure file.")
        try:
            resolved_path = str(Path(path).resolve())
        except Exception:
            resolved_path = path
        if self.structure is not None and os.path.normcase(self.structure_source_path) == os.path.normcase(resolved_path):
            structure = self.structure
            backend = "cached import"
        else:
            result = self.import_structure_file(path)
            structure = result.structure
            self.structure_source_path = resolved_path
            backend = result.source_format
            for line in result.log_lines or []:
                self.append_monitor(line)
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
        freeze_heavy = bool(self.freeze_heavy_var.get())
        freeze_all = bool(self.freeze_all_var.get())
        constrained_opt = freeze_heavy or freeze_all
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
            "job_sp": bool(self.job_sp_var.get()) and not constrained_opt,
            "job_opt": bool(self.job_opt_var.get()) or constrained_opt,
            "job_freq": bool(self.job_freq_var.get()),
            "job_density": bool(self.job_esp_mep_var.get()),
            "job_esp": bool(self.job_esp_mep_var.get()),
            "job_wfn_wfx": bool(self.job_esp_mep_var.get()),
            "job_esp_mep": bool(self.job_esp_mep_var.get()),
            "job_nmr": bool(self.job_nmr_var.get()),
            "job_tddft": bool(self.job_tddft_var.get()),
            "tddft_block": self.current_tddft_block if self.job_tddft_var.get() else "",
            "tddft_settings": dict(self.current_tddft_settings) if self.job_tddft_var.get() else {},
            "job_interaction": bool(self.job_interaction_var.get()),
            "interaction_relaxation": bool(self.interaction_relax_var.get()),
            "interaction_thermo": bool(self.interaction_thermo_var.get()),
            "freeze_heavy": freeze_heavy,
            "freeze_all": freeze_all,
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
            pv_module = require_pyvista()
            if np is None:
                raise ValueError("NumPy is required for the molecule viewer.")
            structure = self.parse_current_structure()
            bonds = infer_bonds(structure, scale=1.20)
            points = np.array([[x, y, z] for _, x, y, z in structure.atoms], dtype=float)
            extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 1.0
            plotter = pv_module.Plotter(window_size=self._structure_preview_window_size(), lighting="none")
            configure_pyvista_defaults(pv_module, plotter, background="black", extent=extent)
            for i, j in bonds:
                sym_i = structure.atoms[i][0]
                sym_j = structure.atoms[j][0]
                add_split_colored_bond(pv_module, plotter, points[i], points[j], molecule_bond_end_color(sym_i), molecule_bond_end_color(sym_j))
            for idx, (sym, *_rest) in enumerate(structure.atoms):
                add_ball_and_stick_atom(pv_module, plotter, sym, points[idx])
            labels = [f"{idx+1}:{sym}" for idx, (sym, *_rest) in enumerate(structure.atoms)]
            plotter.add_point_labels(points, labels, font_size=10, show_points=False, always_visible=False)
            plotter.add_text("Molecule view", position="upper_left", font_size=10)
            title = "ORCA input builder - structure preview"
            bring_window_title_to_front(title)
            bring_pyvista_window_to_front(plotter)
            plotter.show(title=title)
        except Exception as exc:
            self.append_monitor(f"PyVista viewer error: {exc}")
            messagebox.showerror("PyVista viewer", str(exc))

    def update_fragment_selection_view(self):
        try:
            require_pyvista()
            if np is None:
                raise ValueError("NumPy is required for the selection view.")
            structure = self.parse_current_structure()
            if not self.fragment_a_indices or not self.fragment_b_indices:
                self._auto_detect_fragments_for_structure(structure)
            self._show_fragment_selection_view(structure)
        except Exception as exc:
            self.fragment_status_var.set(str(exc))
            messagebox.showerror("Selection view", str(exc))

    def _show_fragment_selection_view(self, structure: Structure):
        pv_module = require_pyvista()
        if np is None:
            raise ValueError("NumPy is required for the selection view.")
        if not self.fragment_a_indices or not self.fragment_b_indices:
            raise ValueError("Run Auto-detect A/B before opening the selection view.")
        try:
            bonds = infer_bonds(structure, scale=1.20)
            points = np.array([[x, y, z] for _, x, y, z in structure.atoms], dtype=float)
            extent = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 1.0
            plotter = pv_module.Plotter(window_size=self._screen_fraction_window_size(1200), lighting="none")
            configure_pyvista_defaults(pv_module, plotter, background="black", extent=extent)

            for i, j in bonds:
                add_split_colored_bond(pv_module, plotter, points[i], points[j], MOLECULE_FRAGMENT_BOND_COLOR, MOLECULE_FRAGMENT_BOND_COLOR)
            for idx, (sym, *_rest) in enumerate(structure.atoms):
                if idx in self.fragment_a_indices:
                    color = "#315BA8"
                elif idx in self.fragment_b_indices:
                    color = "#C94D3F"
                else:
                    color = "#B0B0B0"
                add_ball_and_stick_atom(pv_module, plotter, sym, points[idx], color=color, name=f"fragment_view_atom_{idx}")

            a_formula = formula_for_indices(structure, self.fragment_a_indices)
            b_formula = formula_for_indices(structure, self.fragment_b_indices)
            plotter.add_text(
                f"Blue = fragment A ({a_formula})\n"
                f"Red = fragment B ({b_formula})",
                position="upper_left",
                font_size=10,
                color="white",
                name="color_code_text",
            )
            bring_pyvista_window_to_front(plotter)
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
        if not match:
            return ""
        version = re.sub(r"\s+-\s+RELEASE\s+-\s*$", "", match.group(1).strip(), flags=re.IGNORECASE)
        return version.strip()

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

    def _matching_input_path_for_output(self, out_path: str) -> str:
        out_file = Path(out_path)
        candidates = [
            out_file.with_suffix(".inp"),
            out_file.with_suffix(".gjf"),
            out_file.with_suffix(".com"),
        ]
        if self.current_input_path:
            candidates.insert(0, Path(self.current_input_path))
        selected_text = self.path_var.get().strip()
        if selected_text:
            candidates.insert(0, Path(selected_text))
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stem == out_file.stem:
                    return str(candidate)
            except Exception:
                pass
        return ""

    def _data_from_orca_input_file(self, inp_path: str) -> Dict:
        data = self.collect()
        data.update({
            "program": "ORCA",
            "functional": "",
            "basis": "",
            "dispersion": "",
            "ri_jcosx": False,
            "tight_scf": False,
            "grid": "",
            "print_mos": False,
            "job_sp": False,
            "job_opt": False,
            "job_freq": False,
            "job_density": False,
            "job_esp": False,
            "job_wfn_wfx": False,
            "job_esp_mep": False,
            "job_nmr": False,
            "job_tddft": False,
            "job_interaction": False,
            "freeze_heavy": False,
            "freeze_all": False,
            "solvent_text": "",
        })

        simple = self._read_simple_input_line(inp_path)
        tokens = simple[1:].split() if simple.startswith("!") else []
        upper_tokens = {token.upper() for token in tokens}
        functional_lookup = {item.upper(): item for item in ORCA_FUNCTIONALS}
        basis_lookup = {item.upper(): item for item in ORCA_BASIS}

        for token in tokens:
            upper = token.upper()
            if not data["functional"] and upper in functional_lookup:
                data["functional"] = functional_lookup[upper]
            if not data["basis"] and upper in basis_lookup:
                data["basis"] = basis_lookup[upper]

        if "D3BJ" in upper_tokens:
            data["dispersion"] = "D3BJ"
        elif "D4" in upper_tokens:
            data["dispersion"] = "D4"
        data["ri_jcosx"] = "RIJCOSX" in upper_tokens
        data["tight_scf"] = "TIGHTSCF" in upper_tokens
        for token in tokens:
            if token in {"DefGrid1", "DefGrid2", "DefGrid3"}:
                data["grid"] = token
                break
        data["job_opt"] = "OPT" in upper_tokens
        data["job_freq"] = "FREQ" in upper_tokens
        data["job_sp"] = "SP" in upper_tokens or not any([data["job_opt"], data["job_freq"], data["job_nmr"], data["job_tddft"]])
        data["job_density"] = "KEEPDENS" in upper_tokens
        data["job_esp"] = data["job_density"]
        data["job_wfn_wfx"] = data["job_density"]
        data["job_esp_mep"] = data["job_density"]
        data["print_mos"] = "P_MOS" in simple.upper() or bool(re.search(r"Print\s*\[\s*P_MOs\s*\]\s+[1-9]", simple, re.IGNORECASE))

        try:
            text = Path(inp_path).read_text(encoding="utf-8", errors="replace")
            xyz_match = re.search(r"^\s*\*\s+xyz\s+(-?\d+)\s+(\d+)", text, re.IGNORECASE | re.MULTILINE)
            if xyz_match:
                data["charge"] = int(xyz_match.group(1))
                data["multiplicity"] = int(xyz_match.group(2))
            if re.search(r"^\s*Print\s*\[\s*P_MOs\s*\]\s+[1-9]", text, re.IGNORECASE | re.MULTILINE):
                data["print_mos"] = True
            solvent_match = re.search(r"^\s*SMD\s+true\s*$.*?^\s*SMDSolvent\s+\"?([^\"\r\n]+)\"?", text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if solvent_match:
                data["solvent_text"] = solvent_match.group(1).strip()
            if re.search(r"^\s*Constraints\s*$", text, re.IGNORECASE | re.MULTILINE):
                data["freeze_all"] = True
        except Exception:
            pass
        return data

    def _summary_context_for_output(self, out_path: str) -> Dict:
        active = dict(self.active_run_context or {})
        active_input = active.get("input_path")
        if active and active_input and Path(active_input).with_suffix(".out") == Path(out_path):
            return active

        inp_path = self._matching_input_path_for_output(out_path)
        data = self._data_from_orca_input_file(inp_path) if inp_path else self.collect()
        return {
            "input_path": inp_path,
            "data": data,
            "post_processing": {},
        }

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
                "job_sp": bool(data.get("job_sp")),
                "job_opt": bool(data.get("job_opt")),
                "freeze_heavy": bool(data.get("freeze_heavy")),
                "freeze_all": bool(data.get("freeze_all")),
            },
            "post_processing": dict(context.get("post_processing", {})),
            "analysis_files": {
                "wavefunction_files": wavefunction_files,
                "cube_files": cube_files,
            },
            "results_hartree": energies,
        }

    def _summary_reference_library(self) -> Dict[str, str]:
        return {
            "ORCA": "Neese, F.; Wennmohs, F.; Becker, U.; Riplinger, C. The ORCA quantum chemistry program package. J. Chem. Phys. 2020, 152, 224108. https://doi.org/10.1063/5.0004608; Neese, F. Software Update: The ORCA Program System-Version 6.0. WIREs Comput. Mol. Sci. 2025, 15, e70019. https://doi.org/10.1002/wcms.70019",
            "B3LYP": "Becke, A. D. Density-functional thermochemistry. III. The role of exact exchange. J. Chem. Phys. 1993, 98, 5648-5652. https://doi.org/10.1063/1.464913; Lee, C.; Yang, W.; Parr, R. G. Development of the Colle-Salvetti correlation-energy formula into a functional of the electron density. Phys. Rev. B 1988, 37, 785-789. https://doi.org/10.1103/PhysRevB.37.785",
            "PBE": "Perdew, J. P.; Burke, K.; Ernzerhof, M. Generalized Gradient Approximation Made Simple. Phys. Rev. Lett. 1996, 77, 3865-3868. https://doi.org/10.1103/PhysRevLett.77.3865",
            "PBE0": "Adamo, C.; Barone, V. Toward reliable density functional methods without adjustable parameters: The PBE0 model. J. Chem. Phys. 1999, 110, 6158-6170. https://doi.org/10.1063/1.478522",
            "DEF2_BASIS": "Weigend, F.; Ahlrichs, R. Balanced basis sets of split valence, triple zeta valence and quadruple zeta valence quality for H to Rn: Design and assessment of accuracy. Phys. Chem. Chem. Phys. 2005, 7, 3297-3305. https://doi.org/10.1039/b508541a",
            "DEF2_J": "Weigend, F. Accurate Coulomb-fitting basis sets for H to Rn. Phys. Chem. Chem. Phys. 2006, 8, 1057-1065. https://doi.org/10.1039/b515623h",
            "RIJCOSX": "Izsak, R.; Neese, F. An overlap fitted chain of spheres exchange method. J. Chem. Phys. 2011, 135, 144105. https://doi.org/10.1063/1.3646921",
            "D3BJ": "Grimme, S.; Ehrlich, S.; Goerigk, L. Effect of the damping function in dispersion corrected density functional theory. J. Comput. Chem. 2011, 32, 1456-1465. https://doi.org/10.1002/jcc.21759",
            "D4": "Caldeweyher, E.; Bannwarth, C.; Grimme, S. Extension of the D3 dispersion coefficient model. J. Chem. Phys. 2017, 147, 034112. https://doi.org/10.1063/1.4993215; Caldeweyher, E.; Ehlert, S.; Hansen, A.; Neugebauer, H.; Spicher, S.; Bannwarth, C.; Grimme, S. A generally applicable atomic-charge dependent London dispersion correction. J. Chem. Phys. 2019, 150, 154122. https://doi.org/10.1063/1.5090222",
            "BSSE": "Boys, S. F.; Bernardi, F. The calculation of small molecular interactions by the differences of separate total energies. Some procedures with reduced errors. Mol. Phys. 1970, 19, 553-566. https://doi.org/10.1080/00268977000101561",
            "MULTIWFN": "Lu, T.; Chen, F. Multiwfn: A multifunctional wavefunction analyzer. J. Comput. Chem. 2012, 33, 580-592. https://doi.org/10.1002/jcc.22885",
            "NCI": "Johnson, E. R.; Keinan, S.; Mori-Sanchez, P.; Contreras-Garcia, J.; Cohen, A. J.; Yang, W. Revealing noncovalent interactions. J. Am. Chem. Soc. 2010, 132, 6498-6506. https://doi.org/10.1021/ja100936w",
            "NCIPLOT": "Contreras-Garcia, J.; Johnson, E. R.; Keinan, S.; Chaudret, R.; Piquemal, J.-P.; Beratan, D. N.; Yang, W. NCIPLOT: A program for plotting noncovalent interaction regions. J. Chem. Theory Comput. 2011, 7, 625-632. https://doi.org/10.1021/ct100641a",
            "QTAIM": "Bader, R. F. W. Atoms in Molecules: A Quantum Theory; Oxford University Press: Oxford, 1990. https://doi.org/10.1093/oso/9780198551683.001.0001",
        }

    def _reference_marker(self, key: str, used_refs: List[str]) -> str:
        if key not in used_refs:
            used_refs.append(key)
        return f"[{used_refs.index(key) + 1}]"

    def _functional_reference_key(self, functional: str) -> str:
        key = functional.strip().upper().replace(" ", "").replace("-", "")
        if key in {"B3LYP", "B3LYPG"}:
            return "B3LYP"
        if key in {"PBE", "PBEPBE"}:
            return "PBE"
        if key in {"PBE0", "PBE1PBE"}:
            return "PBE0"
        return ""

    def _geometry_descriptor_for_summary(self, settings: Dict[str, object]) -> str:
        if settings.get("job_opt") and (settings.get("freeze_all") or settings.get("freeze_heavy")):
            return "constrained optimized"
        if settings.get("job_opt"):
            return "optimized"
        return "single-point"

    def _calculation_summary_lines(self, summary: Dict[str, object]) -> List[str]:
        settings = summary.get("settings", {})
        version = summary.get("orca_version", "")
        functional = settings.get("functional", "")
        basis = settings.get("basis", "")
        dispersion = settings.get("dispersion", "")
        grid = settings.get("grid", "")
        solvent = settings.get("solvent_resolved") or settings.get("solvent_input") or ""

        refs = self._summary_reference_library()
        used_refs: List[str] = []
        orca_ref = self._reference_marker("ORCA", used_refs)
        functional_ref_key = self._functional_reference_key(str(functional))
        functional_ref = self._reference_marker(functional_ref_key, used_refs) if functional_ref_key else ""
        basis_ref = self._reference_marker("DEF2_BASIS", used_refs) if str(basis).lower().startswith(("def2", "ma-def2")) else ""
        dispersion_ref_key = str(dispersion).upper()
        dispersion_ref = ""
        if dispersion_ref_key in {"D3BJ", "D4"}:
            dispersion_ref = self._reference_marker(dispersion_ref_key, used_refs)

        version_text = f" (version {version})" if version else ""
        method_bits = [f"a {functional} functional"]
        if functional_ref:
            method_bits[-1] += f" {functional_ref}"
        if dispersion:
            dispersion_text = f"dispersion correction ({dispersion})"
            if dispersion_ref:
                dispersion_text += f" {dispersion_ref}"
            method_bits.append(dispersion_text)
        if basis:
            basis_text = f"a {basis} basis set"
            if basis_ref:
                basis_text += f" {basis_ref}"
            method_bits.append(basis_text)

        primary_task = "geometry optimization" if settings.get("job_opt") else "the requested single-point calculation"
        paragraphs = [
            f"Theoretical calculations were carried out with the ORCA{version_text} program package {orca_ref}. "
            + ", ".join(method_bits)
            + f" were used for {primary_task}."
        ]
        if settings.get("ri_jcosx"):
            rij_ref = self._reference_marker("RIJCOSX", used_refs)
            aux_ref = self._reference_marker("DEF2_J", used_refs)
            paragraphs.append(
                f"The RIJCOSX approximation {rij_ref} was used to improve the computational speed of Hartree-Fock exchange together with the def2/J auxiliary basis set {aux_ref}."
            )

        extra = []
        if settings.get("tight_scf"):
            extra.append("TightSCF convergence criteria were requested.")
        if grid:
            extra.append(f"The numerical integration grid was {grid}.")
        if solvent:
            extra.append(f"Solvent effects were included with the SMD model for {solvent}.")
        if extra:
            paragraphs.append(" ".join(extra))

        if settings.get("job_interaction"):
            geometry_text = self._geometry_descriptor_for_summary(settings)
            interaction_text = (
                f"Dimer interaction energy was calculated using single-point energies evaluated using {geometry_text} geometry "
                f"with {functional} {basis}."
            )
            interaction_text += f" Basis set superposition error (BSSE) was accounted using counterpoise correction scheme {self._reference_marker('BSSE', used_refs)}."
            paragraphs.append(interaction_text)

        post = summary.get("post_processing", {})
        analysis_files = summary.get("analysis_files", {})
        has_analysis = bool(
            settings.get("print_mos")
            or settings.get("job_esp_mep")
            or post.get("esp_mep_generated")
            or analysis_files.get("cube_files")
        )
        if has_analysis:
            multiwfn_ref = self._reference_marker("MULTIWFN", used_refs)
            nci_ref = self._reference_marker("NCI", used_refs)
            nciplot_ref = self._reference_marker("NCIPLOT", used_refs)
            qtaim_ref = self._reference_marker("QTAIM", used_refs)
            paragraphs.append(
                "HOMO-LUMO, QTAIM, NCI plot and MEP were evaluated by the Multiwfn program "
                f"{multiwfn_ref}, and respective plot figures (Fig. X) were prepared using CrystEngKit software ({GITHUB_URL}). "
                f"NCI analysis follows the reduced-density-gradient/sign(lambda2)rho formalism {nci_ref} and NCIPLOT convention {nciplot_ref}; "
                f"QTAIM analysis follows Bader's atoms-in-molecules formalism {qtaim_ref}."
            )
            paragraphs.extend([
                "MEP parameters used in CrystEngKit: electron-density isovalue 0.001 e/A3 isosurface unless changed in the ESP/MEP viewer.",
                "QTAIM parameters used in CrystEngKit: Multiwfn critical-point and bond-path output with CrystEngKit viewer settings for CP visibility, CP colors, bond-path radius, and background.",
                "NCI parameters used in CrystEngKit: RDG isovalue 0.50 and sign(lambda2)rho coloring unless changed in the NCI plotter.",
            ])

        reference_lines = ["", "References"]
        reference_lines.extend(f"[{index}] {refs[key]}" for index, key in enumerate(used_refs, start=1) if key in refs)

        lines = [
            "Computational details",
            "",
            *paragraphs,
            *reference_lines,
        ]
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
        txt_path = self._project_summary_path(out_path)
        lines = self._calculation_summary_lines(calc_summary)
        if interaction_summary is not None:
            lines.extend(["", ""] + self._interaction_summary_lines(interaction_summary))
        elif interaction_error:
            lines.extend(["", "", "Intermolecular interaction results", "", f"Interaction workflow failed: {interaction_error}"])
        text = remove_endnote_citation_tokens("\n".join(lines) + "\n")
        txt_path.write_text(text, encoding="utf-8")
        return txt_path, text

    def _project_summary_path(self, out_path: str) -> Path:
        out_file = Path(out_path)
        return out_file.parent / f"{out_file.stem}_summary.txt"

    def _summary_candidates_for_source(self, source: Path) -> List[Tuple[int, Path]]:
        candidates: List[Tuple[int, Path]] = []
        if not source:
            return candidates

        source_dir = source if source.is_dir() else source.parent
        if not source_dir.is_dir():
            return candidates

        if source.name and not source.is_dir():
            same_stem = source_dir / f"{source.stem}_summary.txt"
            if same_stem.is_file():
                candidates.append((1, same_stem))
            try:
                candidates.extend(
                    (2, path) for path in bounded_find_files(source_dir, names=(f"{source.stem}_summary.txt",))
                    if path.is_file()
                )
            except Exception:
                pass

        try:
            candidates.extend(
                (3, path) for path in bounded_find_files(source_dir, pattern_suffix="_summary.txt")
                if path.is_file()
            )
        except Exception:
            pass
        return candidates

    def _best_summary_path(self, candidates: List[Tuple[int, Path]]) -> str:
        if not candidates:
            raise ValueError("No project summary file was found yet.")
        unique: Dict[str, Tuple[int, Path]] = {}
        for priority, path in candidates:
            key = str(path.resolve())
            if key not in unique or priority < unique[key][0]:
                unique[key] = (priority, path)
        values = list(unique.values())
        main_job_values = [(priority, path) for priority, path in values if not self._is_interaction_job_path(path)]
        if main_job_values:
            values = main_job_values
        best_priority = min(priority for priority, _path in values)
        priority_matches = [path for priority, path in values if priority == best_priority]
        newest = max(priority_matches, key=lambda p: p.stat().st_mtime)
        return str(newest)

    def _available_project_summary_path(self) -> str:
        candidates: List[Tuple[int, Path]] = []
        if self.last_output_path:
            summary_path = self._project_summary_path(self.last_output_path)
            if summary_path.is_file():
                candidates.append((0, summary_path))
        if self.current_input_path:
            candidates.extend(self._summary_candidates_for_source(Path(self.current_input_path)))
        selected_text = self.path_var.get().strip().strip('"')
        if selected_text:
            candidates.extend(self._summary_candidates_for_source(Path(selected_text)))
        return self._best_summary_path(candidates)

    def _project_summary_search_hint(self) -> str:
        source_text = self.current_input_path or self.path_var.get().strip().strip('"')
        if not source_text:
            return "No input file is currently selected."
        source = Path(source_text)
        expected = source.parent / f"{source.stem}_summary.txt"
        return (
            f"Loaded input:\n{source}\n\n"
            f"Expected matching summary:\n{expected}\n\n"
            "The summary must be in the same folder as the loaded input, or in a subfolder below it."
        )

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
        total_specs = max(1, len(specs))
        for spec_index, spec in enumerate(specs, start=1):
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
            self._set_monitor_progress(87.0 + 8.0 * spec_index / total_specs)

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
            if geometry_source and Path(geometry_source).suffix.lower() == ".out":
                src_name = Path(geometry_source).stem
            else:
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

    def append_monitor(self, message: str, clear: bool = False, scroll_to_end: bool = True, wrap: Optional[str] = None):
        previous_wrap = str(self.monitor_text.cget("wrap"))
        if wrap is not None:
            self.monitor_text.configure(wrap=wrap)
        if clear:
            self.monitor_text.delete("1.0", "end")
        elif wrap is None and previous_wrap != "none":
            self.monitor_text.configure(wrap="none")
        if message:
            if not message.endswith("\n"):
                message += "\n"
            self.monitor_text.insert("end", message)
            if scroll_to_end:
                self.monitor_text.see("end")
            else:
                self.monitor_text.see("1.0")

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
            try:
                resolved_path = str(Path(path).resolve())
            except Exception:
                resolved_path = path
            if self.structure is not None and os.path.normcase(self.structure_source_path) == os.path.normcase(resolved_path):
                structure = self.structure
            else:
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
        self._show_output_mode("preview")
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
                raise ValueError("Please choose a supported structure file.")
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

    def _queue_save_dialog_path(self) -> Optional[Path]:
        suggested = f"{self.job_queue.active_queue.replace(' ', '_')}.orcaqueue.json"
        initialdir = str(self.queue_state_path.parent) if self.queue_state_path else str(Path.home())
        path = filedialog.asksaveasfilename(
            title="Choose ORCA queue file",
            defaultextension=".orcaqueue.json",
            initialdir=initialdir,
            initialfile=suggested,
            filetypes=[("ORCA queue files", "*.orcaqueue.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        return Path(path) if path else None

    def _ensure_queue_state_path(self) -> bool:
        if self.queue_state_path:
            return True
        path = self._queue_save_dialog_path()
        if not path:
            return False
        self.queue_state_path = path
        self._save_launcher_settings()
        return True

    def _save_job_queue(self) -> bool:
        if not self._ensure_queue_state_path():
            return False
        try:
            self.job_queue.save(self.queue_state_path)
            self._save_launcher_settings()
            return True
        except Exception as exc:
            self.append_monitor(f"Could not save ORCA job queue: {exc}\n")
            return False

    def _load_job_queue_from_path(self, path: str, confirm_replace: bool = True) -> bool:
        queue_path = Path(path)
        if not OrcaJobQueue.looks_like_queue_file(queue_path):
            return False
        if self.run_process and self.run_process.poll() is None:
            messagebox.showinfo("Load Queue", "Stop the running ORCA job before loading another queue file.")
            return True
        if confirm_replace and self._queue_has_any_jobs():
            ok = messagebox.askyesno(
                "Load Queue",
                "Loading this queue file will replace the current queue manager list. Continue?",
            )
            if not ok:
                return True
        self.job_queue = OrcaJobQueue.load(queue_path)
        self.queue_state_path = queue_path
        self.queue_running = False
        self.active_queue_job = None
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.path_var.set(str(queue_path))
        self._show_output_mode("monitor")
        self.append_monitor(
            f"Loaded ORCA queue file: {queue_path}\n"
            f"Active queue: {self.job_queue.active_queue}\n"
            f"Queue: {self.job_queue.summary()}\n",
            clear=True,
        )
        self.status.configure(text=f"Loaded ORCA queue file: {queue_path.name}")
        return True

    def _maybe_load_job_queue_file(self, path: str) -> bool:
        try:
            return self._load_job_queue_from_path(path)
        except Exception as exc:
            messagebox.showerror("Load Queue error", str(exc))
            return True

    def save_job_queue_as(self):
        path = self._queue_save_dialog_path()
        if path is None:
            return
        try:
            self.queue_state_path = path
            self.job_queue.save(path)
            self._save_launcher_settings()
            self.status.configure(text=f"Saved ORCA queue file: {path}")
        except Exception as exc:
            messagebox.showerror("Save Queue error", str(exc))

    def load_job_queue_as(self):
        path = filedialog.askopenfilename(
            title="Load ORCA queue file",
            filetypes=[("ORCA queue files", "*.orcaqueue.json *.queue.json *.json"), ("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._maybe_load_job_queue_file(path)

    def _queue_has_any_jobs(self) -> bool:
        return any(bool(jobs) for jobs in self.job_queue.queues.values())

    def _refresh_queue_selector(self):
        self.queue_name_var.set(self.job_queue.active_queue)
        combo = self.queue_combo
        if combo is not None and combo.winfo_exists():
            combo.configure(values=self.job_queue.queue_names())

    def _on_queue_selected(self, _event=None):
        selected = self.queue_name_var.get().strip()
        if not selected:
            return
        self.job_queue.set_active_queue(selected)
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.status.configure(text=f"Active ORCA queue: {self.job_queue.active_queue}. Queue: {self.job_queue.summary()}")

    def _ask_for_queue_name(self, title: str = "Queue name") -> Optional[str]:
        name = simpledialog.askstring(title, "Queue name:", parent=self)
        if name is None:
            return None
        cleaned = name.strip()
        return cleaned or None

    def _ensure_queue_for_addition(self) -> bool:
        if not self._queue_has_any_jobs():
            name = self._ask_for_queue_name("New ORCA job queue")
            if not name:
                return False
            self.job_queue.create_queue(name)
            self._refresh_queue_selector()
        return self._ensure_queue_state_path()

    def _create_job_queue(self):
        name = self._ask_for_queue_name("New ORCA job queue")
        if not name:
            return
        self.job_queue.create_queue(name)
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.status.configure(text=f"Active ORCA queue: {self.job_queue.active_queue}")

    def _delete_active_job_queue(self):
        if self.run_process and self.run_process.poll() is None:
            messagebox.showinfo("Queue Jobs", "Stop the running ORCA job before deleting a queue.")
            return
        active_name = self.job_queue.active_queue
        if self.job_queue.jobs and not messagebox.askyesno("Delete queue", f"Delete queue '{active_name}' and its job list?"):
            return
        self.job_queue.delete_active_queue()
        self.queue_running = False
        self.active_queue_job = None
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.status.configure(text=f"Deleted ORCA queue: {active_name}. Active queue: {self.job_queue.active_queue}")

    def _refresh_queue_tree(self):
        tree = self.queue_tree
        if tree is None or not tree.winfo_exists():
            return
        tree.delete(*tree.get_children())
        for idx, job in enumerate(self.job_queue.jobs):
            tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(idx + 1, job.name, job.status, job.output_path, job.folder, job.message),
            )

    def _add_files_to_job_queue(self):
        if not self._ensure_queue_for_addition():
            return
        paths = filedialog.askopenfilenames(
            title="Add ORCA input files to queue",
            filetypes=[("ORCA input files", "*.inp"), ("All files", "*.*")],
        )
        if not paths:
            return
        added = self.job_queue.add_input_files(paths)
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.status.configure(text=f"Queue jobs added: {added}. Active queue: {self.job_queue.active_queue}. Queue: {self.job_queue.summary()}")

    def add_current_input_to_queue(self):
        try:
            if self.program_var.get() != "ORCA":
                raise ValueError("Only ORCA .inp files can be added to the ORCA job queue.")
            if not self._ensure_queue_for_addition():
                return
            inp_path = self.ensure_input_saved()
            if not inp_path:
                return
            if Path(inp_path).suffix.lower() != ".inp":
                raise ValueError(f"Only ORCA .inp files can be queued: {inp_path}")
            added = self.job_queue.add_input_files([inp_path])
            self._save_job_queue()
            self._refresh_queue_selector()
            self._refresh_queue_tree()
            if added:
                self.status.configure(text=f"Added to queue '{self.job_queue.active_queue}': {inp_path}")
            else:
                self.status.configure(text=f"Already in queue '{self.job_queue.active_queue}': {inp_path}")
        except Exception as exc:
            messagebox.showerror("Add to Queue error", str(exc))

    def _remove_selected_queue_jobs(self):
        if self.run_process and self.run_process.poll() is None:
            messagebox.showinfo("Queue Jobs", "Stop the running ORCA job before removing queued jobs.")
            return
        tree = self.queue_tree
        if tree is None or not tree.winfo_exists():
            return
        indices = []
        for item in tree.selection():
            try:
                indices.append(int(item))
            except Exception:
                pass
        if not indices:
            return
        running_indices = [
            idx for idx in indices
            if 0 <= idx < len(self.job_queue.jobs) and self.job_queue.jobs[idx].status == "running"
        ]
        if running_indices:
            messagebox.showinfo("Queue Jobs", "The running job cannot be removed. Stop it first if needed.")
            return
        self.job_queue.remove_indices(indices)
        self._save_job_queue()
        self._refresh_queue_tree()
        self.status.configure(text=f"Queue updated. Active queue: {self.job_queue.active_queue}. Queue: {self.job_queue.summary()}")

    def _clear_job_queue(self):
        if self.run_process and self.run_process.poll() is None:
            messagebox.showinfo("Queue Jobs", "Stop the running ORCA job before clearing the queue.")
            return
        self.job_queue.queues[self.job_queue.active_queue] = []
        self.job_queue.current_index = None
        self.job_queue.current_queue = None
        self.queue_running = False
        self.active_queue_job = None
        self._save_job_queue()
        self._refresh_queue_selector()
        self._refresh_queue_tree()
        self.status.configure(text=f"ORCA job queue cleared: {self.job_queue.active_queue}.")

    def _reset_job_queue(self):
        if self.run_process and self.run_process.poll() is None:
            messagebox.showinfo("Queue Jobs", "Stop the running ORCA job before resetting the queue.")
            return
        self.job_queue.reset_pending()
        self._save_job_queue()
        self._refresh_queue_tree()
        self.status.configure(text=f"Queue reset. Active queue: {self.job_queue.active_queue}. Queue: {self.job_queue.summary()}")

    def open_job_queue(self):
        if self.queue_window is not None and self.queue_window.winfo_exists():
            self.queue_window.lift()
            self._refresh_queue_selector()
            self._refresh_queue_tree()
            return

        win = tk.Toplevel(self)
        configure_tk_window_identity(win, "Builder")
        win.title("ORCA job queue")
        win.geometry("920x360")
        win.minsize(760, 260)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        self.queue_window = win

        top = ttk.Frame(win)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 0))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Active queue").grid(row=0, column=0, sticky="w")
        self.queue_combo = ttk.Combobox(
            top,
            textvariable=self.queue_name_var,
            values=self.job_queue.queue_names(),
            state="readonly",
            width=28,
        )
        self.queue_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.queue_combo.bind("<<ComboboxSelected>>", self._on_queue_selected)
        ttk.Button(top, text="New queue", command=self._create_job_queue).grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Button(top, text="Delete queue", command=self._delete_active_job_queue).grid(row=0, column=3, sticky="e", padx=(6, 0))

        columns = ("#", "Input", "Status", "Output", "Folder", "Message")
        tree = ttk.Treeview(win, columns=columns, show="headings", selectmode="extended")
        self.queue_tree = tree
        widths = {"#": 45, "Input": 190, "Status": 90, "Output": 230, "Folder": 260, "Message": 180}
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 120), anchor="w", stretch=True)
        tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(8, 0))

        yscroll = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))

        buttons = ttk.Frame(win)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        for idx in range(8):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="Add .inp files", command=self._add_files_to_job_queue).grid(row=0, column=0, sticky="ew")
        ttk.Button(buttons, text="Remove selected", command=self._remove_selected_queue_jobs).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Reset finished", command=self._reset_job_queue).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Clear queue", command=self._clear_job_queue).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Save Queue", command=self.save_job_queue_as).grid(row=0, column=4, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Load Queue", command=self.load_job_queue_as).grid(row=0, column=5, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Autosave now", command=self._save_job_queue).grid(row=0, column=6, sticky="ew", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).grid(row=0, column=7, sticky="ew", padx=(6, 0))

        self._refresh_queue_selector()
        self._refresh_queue_tree()
        if not self._queue_has_any_jobs():
            self.after(100, self._add_files_to_job_queue)

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
            orca_path = self._validated_orca_path()
            if self._has_queued_jobs():
                self._start_job_queue(orca_path)
                return
            inp_path = self.ensure_input_saved()
            if not inp_path:
                return
            context = self._context_for_current_input(inp_path, orca_path)
            self._start_orca_input(inp_path, orca_path, context)
        except Exception as exc:
            self.active_run_context = None
            messagebox.showerror("Run error", str(exc))

    def _validated_orca_path(self) -> str:
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
        return orca_path

    def _has_queued_jobs(self) -> bool:
        return any(job.status == "queued" for job in self.job_queue.jobs)

    def _context_for_current_input(self, inp_path: str, orca_path: str) -> Dict:
        context = {
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
        return context

    def _context_for_queued_input(self, inp_path: str, orca_path: str) -> Dict:
        return {
            "input_path": inp_path,
            "orca_path": orca_path,
            "data": self._data_from_orca_input_file(inp_path),
            "post_processing": {},
            "queue_job": True,
        }

    def _start_orca_input(self, inp_path: str, orca_path: str, context: Dict):
        if not os.path.isfile(inp_path):
            raise FileNotFoundError(f"ORCA input file was not found: {inp_path}")
        if Path(inp_path).suffix.lower() != ".inp":
            raise ValueError(f"Queued ORCA jobs must be .inp files: {inp_path}")
        out_path = str(Path(inp_path).with_suffix(".out"))
        self.current_input_path = inp_path
        self.last_output_path = out_path
        args = [orca_path, os.path.basename(inp_path)]
        workdir = os.path.dirname(inp_path) or os.getcwd()
        self.active_run_context = context
        interaction_warnings = []
        if context.get("interaction_enabled"):
            interaction_warnings = self._preflight_interaction_context(context)

        self.clear_monitor(reset_status=False)
        self._show_output_mode("monitor")
        if context.get("queue_job"):
            self.append_monitor(f"=== Queued ORCA job ===\nInput: {inp_path}\n")
        for warning in interaction_warnings:
            self.append_monitor(f"Interaction warning: {warning}")
        self.monitor_started_at = time.time()
        self.monitor_offset = 0
        self._set_monitor_progress(0.0, allow_decrease=True)
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
        self._set_monitor_progress(5.0)
        self._schedule_monitor_poll()

    def _start_job_queue(self, orca_path: str):
        if not self._has_queued_jobs():
            raise ValueError("The ORCA job queue is empty.")
        self.queue_running = True
        self._show_output_mode("monitor")
        self.append_monitor(
            f"=== Starting ORCA job queue ===\n"
            f"Active queue: {self.job_queue.active_queue}\n"
            f"Queue: {self.job_queue.summary()}\n",
            clear=True,
        )
        self._start_next_queued_job(orca_path)

    def _start_next_queued_job(self, orca_path: str):
        job = self.job_queue.next_queued()
        self.active_queue_job = job
        self._save_job_queue()
        self._refresh_queue_tree()
        if job is None:
            self.queue_running = False
            self.status.configure(text=f"ORCA queue finished: {self.job_queue.active_queue}. Queue: {self.job_queue.summary()}")
            self._set_monitor_stage("Queue finished")
            self._set_monitor_progress(100.0)
            messagebox.showinfo("ORCA queue finished", f"Queued ORCA jobs finished.\n\nQueue: {self.job_queue.active_queue}\n{self.job_queue.summary()}")
            return
        try:
            context = self._context_for_queued_input(job.input_path, orca_path)
            self._start_orca_input(job.input_path, orca_path, context)
        except Exception as exc:
            self.job_queue.mark_current("failed", str(exc))
            self.active_queue_job = None
            self._save_job_queue()
            self._refresh_queue_tree()
            self.append_monitor(f"Queued job failed before launch: {exc}\n")
            self.after(250, lambda: self._start_next_queued_job(orca_path))

    def _schedule_monitor_poll(self, delay_ms: int = MONITOR_POLL_DELAY_MS):
        if self.monitor_job_id:
            try:
                self.after_cancel(self.monitor_job_id)
            except Exception:
                pass
        self.monitor_job_id = self.after(delay_ms, self.poll_job_monitor)

    def poll_job_monitor(self):
        self.monitor_job_id = None
        out_path = self.last_output_path
        read_more_soon = False
        if out_path and os.path.isfile(out_path):
            try:
                with open(out_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.monitor_offset)
                    chunk = f.read(MONITOR_READ_CHARS_PER_POLL)
                    self.monitor_offset = f.tell()
                    read_more_soon = len(chunk) >= MONITOR_READ_CHARS_PER_POLL
                if chunk:
                    self.append_monitor(chunk)
                    stage = self.parse_orca_stage(chunk)
                    if stage:
                        self._set_monitor_stage(stage)
                        self._set_monitor_progress(self._progress_for_orca_stage(stage))
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
            if code is not None and read_more_soon:
                self._schedule_monitor_poll(MONITOR_CATCHUP_DELAY_MS)
                return
            if code is None:
                self._schedule_monitor_poll(MONITOR_CATCHUP_DELAY_MS if read_more_soon else MONITOR_POLL_DELAY_MS)
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

    @staticmethod
    def _progress_for_orca_stage(stage: str) -> float:
        return {
            "Starting ORCA": 5.0,
            "SCF start": 10.0,
            "SCF iterations": 15.0,
            "SCF / orbital analysis": 20.0,
            "Gradient evaluation": 25.0,
            "Geometry optimization": 30.0,
            "Frequency calculation": 45.0,
            "TD-DFT excited states": 45.0,
            "NMR property calculation": 45.0,
            "Finished normally": 65.0,
            "Error termination": 65.0,
        }.get(stage, 5.0)

    def _set_monitor_stage(self, stage: str):
        self.monitor_status_text = stage
        self.monitor_stage_label.configure(text=f"Status: {stage}")

    @staticmethod
    def _format_monitor_progress(percent: float, width: int = 30) -> str:
        value = max(0.0, min(100.0, float(percent)))
        filled = int(round(width * value / 100.0))
        bar = "#" * filled + "-" * (width - filled)
        return f"Progress: [{bar}] {value:5.1f} %"

    def _set_monitor_progress(self, percent: float, allow_decrease: bool = False):
        value = max(0.0, min(100.0, float(percent)))
        if not allow_decrease:
            value = max(self.monitor_progress_value, value)
        self.monitor_progress_value = value
        self.monitor_progress_label.configure(text=self._format_monitor_progress(value))
        self.update_idletasks()


    def clear_monitor(self, reset_status: bool = True):
        self.monitor_text.configure(wrap="none")
        self.monitor_text.delete("1.0", "end")
        self.monitor_offset = 0
        if reset_status:
            self.monitor_started_at = None
            self.monitor_elapsed_label.configure(text="Elapsed: 00:00:00")
            self._set_monitor_stage("Idle")
            self._set_monitor_progress(0.0, allow_decrease=True)

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
        if self.active_queue_job is not None:
            self.queue_running = False
            if self.active_run_context is not None:
                self.active_run_context["queue_stopped"] = True
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

    def show_project_summary(self):
        summary_path: Optional[Path] = None
        summary_text = ""
        try:
            summary_path = Path(self._available_project_summary_path())
            summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            summary_path = None

        out_path = ""
        if summary_path is None:
            try:
                out_path = self._available_output_path()
            except Exception:
                messagebox.showinfo(
                    "Show summary",
                    "Summary was not found, and no output file is available for regenerating it.\n\n"
                    + self._project_summary_search_hint(),
                )
                return

            summary_path = self._project_summary_path(out_path)

        if not summary_text and not summary_path.is_file():
            output_ok, output_reason = validate_orca_output_file(out_path)
            if not output_ok:
                messagebox.showinfo("Show summary", f"No valid completed ORCA output is available.\n{output_reason}\n\nOutput:\n{out_path}")
                return
            try:
                calc_summary = self._build_calculation_summary(self._summary_context_for_output(out_path), out_path)
                summary_path, summary_text = self._write_project_summary(out_path, calc_summary)
            except Exception as exc:
                messagebox.showerror("Show summary error", f"Summary file was not found and could not be generated:\n{exc}")
                return
        elif not summary_text:
            try:
                summary_text = summary_path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                messagebox.showerror("Show summary error", str(exc))
                return

        self._show_output_mode("monitor")
        self.append_monitor(f"=== Project summary ===\nSaved: {summary_path}\n\n{summary_text}", clear=True, scroll_to_end=False, wrap="word")
        self._set_monitor_stage("Summary shown")
        self.status.configure(text=f"Summary shown: {summary_path}")

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
        self.append_monitor(
            "\n=== WFN/WFX generation via orca_2aim ===\n"
            f"Executable: {orca_2aim_path}\n"
            f"GBW file: {gbw_path}\n"
            f"Base name: {base_name}\n"
            f"Working directory: {workdir}\n"
            "Status: running orca_2aim; this may take a moment...\n"
        )
        self.update_idletasks()
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
        self.append_monitor(f"Status: WFN/WFX generation completed.\nGenerated: {wfn_path}\nGenerated: {wfx_path}\n")
        return wfn_path

    def generate_wavefunction_files(self):
        try:
            out_path = self._available_output_path()
        except Exception as exc:
            messagebox.showinfo("Generate WFN/WFX", f"No ORCA output file is available yet.\n\n{exc}")
            return

        output_ok, output_reason = validate_orca_output_file(out_path)
        if not output_ok:
            messagebox.showinfo(
                "Generate WFN/WFX",
                f"No valid completed ORCA output is available.\n{output_reason}\n\nOutput:\n{out_path}",
            )
            return

        try:
            self._show_output_mode("monitor")
            self._set_monitor_stage("Generating WFN/WFX")
            self._set_monitor_progress(0.0, allow_decrease=True)
            self.status.configure(text=f"Generating WFN/WFX from {out_path}")
            self.append_monitor(f"\nManual WFN/WFX generation requested for:\n{out_path}\n")
            self._set_monitor_progress(25.0)
            wavefunction_path = self.run_orca_2aim(out_path)
            self._set_monitor_progress(100.0)
            fchk_path = str(Path(out_path).with_suffix(".fchk"))
            fchk_note = f"\nExisting FCHK: {fchk_path}" if os.path.isfile(fchk_path) else "\nFCHK was not generated; ORCA/orca_2aim normally produces WFN/WFX, not Gaussian FCHK."
            self.append_monitor(fchk_note + "\n")
            self._set_monitor_stage("WFN/WFX generated")
            self.status.configure(text=f"WFN/WFX generated: {wavefunction_path}")
            messagebox.showinfo(
                "Generate WFN/WFX",
                f"WFN/WFX generation completed.\n\nOutput:\n{out_path}{fchk_note}",
            )
        except Exception as exc:
            self._set_monitor_stage("WFN/WFX failed")
            self.append_monitor(f"WFN/WFX generation failed: {exc}\n")
            self.status.configure(text=f"WFN/WFX generation failed: {exc}")
            messagebox.showerror("Generate WFN/WFX error", str(exc))

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
        queue_job = bool(context.get("queue_job") and self.active_queue_job)
        output_ok, output_reason = validate_orca_output_file(out_path)
        if code == 0 and output_ok:
            self._set_monitor_progress(65.0)
            post_messages = []
            interaction_summary = None
            interaction_root = None
            interaction_error = ""
            context.setdefault("post_processing", {})
            wavefunction_path = ""
            try:
                self._set_monitor_stage("Generating WFN/WFX")
                self._set_monitor_progress(70.0)
                wavefunction_path = self.run_orca_2aim(out_path)
                self._set_monitor_progress(75.0)
                context["post_processing"]["wfn_wfx_generated"] = True
                context["post_processing"]["wavefunction_path"] = wavefunction_path
                post_messages.append("WFN/WFX generation completed.")
            except Exception as exc:
                self._set_monitor_progress(75.0)
                context["post_processing"]["wfn_wfx_error"] = str(exc)
                post_messages.append(f"WFN/WFX generation failed: {exc}")
                self.append_monitor(f"WFN/WFX generation failed: {exc}\n")
            if self.job_esp_mep_var.get():
                try:
                    self._set_monitor_stage("Generating ESP/MEP cubes")
                    self._set_monitor_progress(78.0)
                    self.run_esp_cube_generation(wavefunction_path)
                    self._set_monitor_progress(85.0)
                    context["post_processing"]["esp_mep_generated"] = True
                    post_messages.append("ESP/MEP cube generation completed.")
                except Exception as exc:
                    self._set_monitor_progress(85.0)
                    context["post_processing"]["esp_mep_error"] = str(exc)
                    post_messages.append(f"ESP/MEP post-processing failed: {exc}")
                    self.append_monitor(f"ESP/MEP post-processing failed: {exc}\n")
            if context.get("interaction_enabled"):
                try:
                    self._set_monitor_stage("Interaction workflow")
                    self._set_monitor_progress(87.0)
                    interaction_summary, interaction_root = self._run_interaction_pipeline(out_path, context)
                    self._set_monitor_progress(95.0)
                    post_messages.append(f"Interaction workflow completed: {interaction_root}")
                    warnings = interaction_summary.get("warnings", [])
                    if warnings:
                        post_messages.extend(warnings)
                except Exception as exc:
                    self._set_monitor_progress(95.0)
                    interaction_error = str(exc)
                    post_messages.append(f"Interaction workflow failed: {exc}")
                    self.append_monitor(f"Interaction workflow failed: {exc}\n")
            try:
                self._set_monitor_stage("Creating project summary")
                self._set_monitor_progress(97.0)
                calc_summary = self._build_calculation_summary(context, out_path)
                summary_path, summary_text = self._write_project_summary(out_path, calc_summary, interaction_summary, interaction_error)
                post_messages.append(f"Summary saved: {summary_path}")
                self.append_monitor(f"\n=== Project summary ===\nSaved: {summary_path}\n\n{summary_text}", wrap="word")
            except Exception as exc:
                post_messages.append(f"Project summary could not be created: {exc}")
                self.append_monitor(f"Project summary could not be created: {exc}\n")
            self._set_monitor_stage("Finished normally")
            self._set_monitor_progress(100.0)
            status = f"ORCA finished. Output: {out_path}"
            if post_messages:
                status += " | " + " ".join(post_messages)
            self.status.configure(text=status)
            if not queue_job and os.path.isfile(out_path):
                try:
                    open_path_in_system(out_path)
                except Exception:
                    pass
            if not queue_job:
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
            if not queue_job:
                messagebox.showwarning("ORCA finished with errors", message + "\n\n" + detail)
        self.active_run_context = None
        if queue_job:
            if context.get("queue_stopped"):
                status = "stopped"
                detail = "Stopped by user"
            else:
                status = "done" if code == 0 and output_ok else "failed"
                detail = "Finished normally" if status == "done" else f"Exit code {code}; {output_reason}"
            self.job_queue.mark_current(status, detail)
            self.active_queue_job = None
            self._save_job_queue()
            self._refresh_queue_tree()
            orca_path = str(context.get("orca_path", "")).strip()
            if self.queue_running and orca_path:
                self.after(500, lambda path=orca_path: self._start_next_queued_job(path))


if __name__ == "__main__":
    app = App()
    app.mainloop()
