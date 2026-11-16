from __future__ import annotations

import ctypes
from ctypes import wintypes
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Crystal Habit Builder"
APP_DIR = Path(__file__).resolve().parent
TOOLS_ROOT = APP_DIR.parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))
from app_identity import configure_tk_window_identity, install_dev_reload_shortcut, set_windows_app_id
from shared.tk_helpers import configure_builder_ui_style, load_header_icon

CRYSTAL_HABIT_ICON_PATH = TOOLS_ROOT / "images" / "tr_orca_icon.png"
GITHUB_URL = "https://github.com/torubaev/crystengkit-orca-v1.0"
DOCUMENTATION_URL = GITHUB_URL + "/blob/main/tools/crystal_habit/README.md"
AI_ASSISTANT_URL = "https://chatgpt.com/g/g-6a6063dcc6b88191b88ac7a6c3b9476d-crystengkit-orca-assistant"
LINKEDIN_URL = "https://www.linkedin.com/in/torubaev/"
CONTACT_EMAIL = "torubaev(at)gmail.com"
COPYRIGHT_NOTE = "(c) Yury Torubaev, 2026"
ABOUT_PURPOSE = (
    "Runs a solvent-dependent crystal-habit workflow from a CIF structure. It uses "
    "CrystalClear for interaction and facet energetics, CrystoGen/CrystalGrower for "
    "kinetic Monte Carlo growth simulations, and CGAspects for morphology inspection."
)
CITATION_REFERENCE = (
    "Torubaev, Y. CrystEngKit-ORCA: practical GUI tools for ORCA and "
    "Multiwfn calculations in supramolecular chemistry and crystal engineering, "
    "version 1.0; GitHub, 2026. https://github.com/torubaev/crystengkit-orca-v1.0"
)
CITATION_TEXT = f"Cite as: {CITATION_REFERENCE}"
DEFAULT_CRYSTALCLEAR = Path.home() / "Documents" / "OCC-CrystalClear" / "Run-CrystalClear.ps1"
DEFAULT_CRYSTOGEN = APP_DIR / "tools" / "crystogen" / "crystogen.exe"
DEFAULT_CGASPECTS = Path(r"C:\Program Files\CrystoGen\CGAspects\CGAspects.exe")
DEFAULT_OUTPUT = Path.home() / "Documents" / "CrystalHabitBuilder" / "runs"
ORCA_TOOLS = TOOLS_ROOT

SOLVENTS = (
    ("Water", "water"),
    ("Methanol (MeOH)", "methanol"),
    ("Ethanol (EtOH)", "ethanol"),
    ("1-Propanol", "1-propanol"),
    ("2-Propanol (IPA)", "2-propanol"),
    ("1-Butanol", "1-butanol"),
    ("2-Butanol", "2-butanol"),
    ("Isobutanol", "2-methyl-1-propanol"),
    ("tert-Butanol", "2-methyl-2-propanol"),
    ("Ethylene glycol", "1,2-ethanediol"),
    ("2,2,2-Trifluoroethanol", "2,2,2-trifluoroethanol"),
    ("Acetonitrile (MeCN)", "acetonitrile"),
    ("Acetone", "acetone"),
    ("N,N-Dimethylformamide (DMF)", "N,N-dimethylformamide"),
    ("N,N-Dimethylacetamide (DMAc)", "N,N-dimethylacetamide"),
    ("Dimethyl sulfoxide (DMSO)", "dimethylsulfoxide"),
    ("Tetrahydrofuran (THF)", "tetrahydrofuran"),
    ("1,4-Dioxane", "1,4-dioxane"),
    ("Diethyl ether", "diethylether"),
    ("Diisopropyl ether", "diisopropyl ether"),
    ("Dichloromethane (DCM)", "dichloromethane"),
    ("Chloroform", "chloroform"),
    ("1,2-Dichloroethane", "1,2-dichloroethane"),
    ("Chlorobenzene", "chlorobenzene"),
    ("Carbon tetrachloride", "carbon tetrachloride"),
    ("Benzene", "benzene"),
    ("Toluene", "toluene"),
    ("Ethylbenzene", "ethylbenzene"),
    ("Xylene mixture", "xylene (mixture)"),
    ("o-Xylene", "o-xylene"),
    ("m-Xylene", "m-xylene"),
    ("p-Xylene", "p-xylene"),
    ("Pyridine", "pyridine"),
    ("Nitromethane", "nitromethane"),
    ("Nitrobenzene", "nitrobenzene"),
    ("Acetic acid", "acetic acid"),
    ("Formamide", "formamide"),
    ("Triethylamine", "triethylamine"),
    ("Cyclohexane", "cyclohexane"),
    ("Methylcyclohexane", "methylcyclohexane"),
    ("n-Pentane", "n-pentane"),
    ("n-Hexane", "n-hexane"),
    ("n-Heptane", "n-heptane"),
    ("n-Octane", "n-octane"),
)


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_stats(pid: int) -> tuple[float | None, float | None]:
    """Return accumulated CPU seconds and working-set MB without external packages."""
    if os.name != "nt" or not pid:
        return None, None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None, None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        cpu = None
        if ctypes.windll.kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            def ticks(value: wintypes.FILETIME) -> int:
                return (value.dwHighDateTime << 32) | value.dwLowDateTime
            cpu = (ticks(kernel) + ticks(user)) / 10_000_000.0
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        ram = None
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            ram = counters.WorkingSetSize / (1024 * 1024)
        return cpu, ram
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("_")
    return value or "solvent"


def normalize_initial_cif(value: str | os.PathLike[str] | None) -> str:
    """Return an existing CIF as an absolute path, or an empty value."""
    if not value:
        return ""
    try:
        path = Path(value).expanduser().resolve()
    except (OSError, TypeError, ValueError):
        return ""
    if path.is_file() and path.suffix.lower() == ".cif":
        return str(path)
    return ""


def default_results_folder(cif_path: str | os.PathLike[str] | None) -> Path:
    """Use the selected CIF directory, falling back only when no CIF is available."""
    normalized = normalize_initial_cif(cif_path)
    return Path(normalized).parent if normalized else DEFAULT_OUTPUT


class CrystalHabitApp(tk.Tk):
    def __init__(self, initial_cif: str | os.PathLike[str] | None = None) -> None:
        set_windows_app_id("CrystalHabit")
        super().__init__()
        configure_tk_window_identity(self, "CrystalHabit")
        self.title(APP_TITLE)
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.stop_event = threading.Event()
        self.started_at: float | None = None
        self.current_run_root: Path | None = None
        self.current_config: dict[str, object] | None = None
        self.final_xyz: Path | None = None

        initial_cif_path = normalize_initial_cif(initial_cif)
        self.cif_var = tk.StringVar(value=initial_cif_path)
        self.output_var = tk.StringVar(value=str(default_results_folder(initial_cif_path)))
        self.crystalclear_var = tk.StringVar(value=str(DEFAULT_CRYSTALCLEAR))
        self.crystogen_var = tk.StringVar(value=str(DEFAULT_CRYSTOGEN))
        self.cgaspects_var = tk.StringVar(value=str(DEFAULT_CGASPECTS))
        self.model_var = tk.StringVar(value="ce-1p")
        self.solvation_var = tk.StringVar(value="smd")
        self.radius_var = tk.StringVar(value="4.1")
        self.dmin_var = tk.StringVar(value="3.0")
        self.threads_var = tk.StringVar(value="4")
        self.temperature_var = tk.StringVar(value="25.00")
        self.iterations_var = tk.StringVar(value="1000000")
        self.memory_var = tk.StringVar(value="10000")
        self.solvent_entry_var = tk.StringVar()
        self.stage_var = tk.StringVar(value="Ready")
        self.solvent_status_var = tk.StringVar(value="—")
        self.elapsed_var = tk.StringVar(value="00:00:00")
        self.cpu_var = tk.StringVar(value="—")
        self.ram_var = tk.StringVar(value="—")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="0%")

        self._configure_styles()
        self._build()
        install_dev_reload_shortcut(
            self,
            Path(__file__),
            can_restart=lambda: not (self.worker and self.worker.is_alive()),
        )
        self.after(150, self._drain_events)
        self.after(1000, self._update_metrics)

    def _configure_styles(self) -> None:
        configure_builder_ui_style(self)
        style = ttk.Style(self)
        style.map("Primary.TButton", background=[("active", "#3b94df"), ("pressed", "#1f68a8")], foreground=[("active", "#ffffff")])
        style.configure("Danger.TButton", background="#b91c1c", foreground="#ffffff", padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map(
            "Danger.TButton",
            background=[("disabled", "#d7dee8"), ("active", "#dc2626")],
            foreground=[("disabled", "#7b8798"), ("active", "#ffffff")],
        )
        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#dbe6f2", background="#2f80c8")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 12))
        header.grid(row=0, column=0, sticky="ew")
        self.header_icon = load_header_icon(CRYSTAL_HABIT_ICON_PATH)
        if self.header_icon is not None:
            tk.Label(header, image=self.header_icon, bg="#1e3a5f", bd=0, highlightthickness=0).grid(
                row=0, column=0, rowspan=2, sticky="w", padx=(0, 10)
            )
        ttk.Label(header, text=APP_TITLE, style="HeaderTitle.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="CrystalClear → CrystalGrower → CGAspects", style="HeaderSub.TLabel").grid(
            row=1, column=1, sticky="w", pady=(3, 0)
        )
        header.columnconfigure(2, weight=1)
        header_actions = ttk.Frame(header, style="Header.TFrame")
        header_actions.grid(row=0, column=3, rowspan=2, sticky="e")
        about_link = ttk.Label(header_actions, text="About", style="HeaderLink.TLabel", cursor="hand2")
        about_link.pack(side="right", padx=(12, 0))
        about_link.bind("<Button-1>", lambda _event: self.open_about_window())
        ttk.Label(header_actions, text="OCC / CrystoGen", style="HeaderAction.TLabel").pack(side="right")

        body = ttk.Frame(self, padding=12)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="cols")
        body.columnconfigure(1, weight=1, uniform="cols")
        body.rowconfigure(1, weight=1)

        setup = ttk.LabelFrame(body, text="Calculation setup")
        setup.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        setup.columnconfigure(1, weight=1)
        self._path_row(setup, 0, "CIF file", self.cif_var, self._browse_cif)
        ttk.Button(setup, text="Preview", command=self.launch_structure_viewer).grid(row=0, column=3, padx=4, pady=5)
        self._path_row(setup, 1, "Results folder", self.output_var, self._browse_output)

        solvent_box = ttk.LabelFrame(body, text="Solvents")
        solvent_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        ttk.Label(solvent_box, text="Choose or type a solvent:").grid(row=0, column=0, sticky="w", padx=5, pady=(2, 3))
        self.solvent_combo = ttk.Combobox(
            solvent_box,
            textvariable=self.solvent_entry_var,
            values=[key for _, key in SOLVENTS],
            state="normal",
        )
        self.solvent_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=(2, 3))
        self.solvent_combo.bind("<Return>", lambda _event: self.add_solvent())
        ttk.Button(solvent_box, text="Add", command=self.add_solvent).grid(row=0, column=2, padx=5, pady=(2, 3))

        self.solvent_list = tk.Listbox(
            solvent_box,
            height=3,
            exportselection=False,
            bg="#ffffff",
            fg="#263348",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
            relief="solid",
            borderwidth=1,
        )
        self.solvent_list.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=(2, 2))
        solvent_actions = ttk.Frame(solvent_box, style="Panel.TFrame")
        solvent_actions.grid(row=1, column=2, sticky="ns", padx=5, pady=2)
        ttk.Button(solvent_actions, text="Remove", command=self.remove_solvent).pack(fill="x")
        ttk.Button(solvent_actions, text="Clear", command=lambda: self.solvent_list.delete(0, "end")).pack(fill="x", pady=(4, 0))
        solvent_box.columnconfigure(1, weight=1)
        solvent_box.rowconfigure(1, weight=1)

        parameters = ttk.LabelFrame(body, text="Parameters")
        parameters.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(6, 0), pady=(0, 8))
        fields = [
            ("Interaction model", self.model_var, ("ce-1p", "ce-2p", "ce-b3lyp", "ce-hf", "gfn2")),
            ("Solvation model", self.solvation_var, ("smd", "cosmo-rs", "none")),
            ("Interaction radius (Å)", self.radius_var, None),
            ("Surface d-min (Å)", self.dmin_var, None),
            ("OCC threads", self.threads_var, None),
            ("Temperature (°C)", self.temperature_var, None),
            ("CrystoGen iterations", self.iterations_var, None),
            ("Maximum memory (MB)", self.memory_var, None),
        ]
        for row, (label, var, values) in enumerate(fields):
            ttk.Label(parameters, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            widget = ttk.Combobox(parameters, textvariable=var, values=values, state="readonly") if values else ttk.Entry(parameters, textvariable=var)
            widget.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
            parameters.grid_rowconfigure(row, minsize=25)
        parameters.columnconfigure(1, weight=1)
        ttk.Button(parameters, text="Program paths…", command=self._program_paths).grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 1))

        monitor = ttk.LabelFrame(body, text="Computation monitor")
        monitor.grid(row=2, column=0, columnspan=2, sticky="nsew")
        body.rowconfigure(2, weight=2)
        monitor.columnconfigure(0, weight=1)
        monitor.rowconfigure(3, weight=1)

        status = ttk.Frame(monitor, style="Panel.TFrame")
        status.grid(row=0, column=0, sticky="ew")
        for col, (title, variable) in enumerate((
            ("Stage", self.stage_var), ("Solvent", self.solvent_status_var),
            ("Elapsed", self.elapsed_var), ("CPU time", self.cpu_var), ("RAM", self.ram_var)
        )):
            box = ttk.Frame(status, style="Panel.TFrame", padding=(6, 2))
            box.grid(row=0, column=col, sticky="ew")
            status.columnconfigure(col, weight=1)
            ttk.Label(box, text=title, foreground="#53627a").pack(anchor="w")
            ttk.Label(box, textvariable=variable, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        progress_row = ttk.Frame(monitor, style="Panel.TFrame")
        progress_row.grid(row=1, column=0, sticky="ew", pady=(7, 4))
        progress_row.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100, style="Blue.Horizontal.TProgressbar").grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_row, textvariable=self.progress_text_var).grid(row=0, column=1, padx=(8, 0))

        buttons = ttk.Frame(monitor, style="Panel.TFrame")
        buttons.grid(row=2, column=0, sticky="ew", pady=(3, 6))
        self.run_button = ttk.Button(buttons, text="Run calculation", style="Primary.TButton", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", style="Danger.TButton", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=7)
        ttk.Button(buttons, text="Open results folder", command=self.open_results).pack(side="left", padx=4)
        self.report_button = ttk.Button(buttons, text="Show summary report", command=self.open_summary_report, state="disabled")
        self.report_button.pack(side="left", padx=4)
        self.aspects_button = ttk.Button(buttons, text="Open in CGAspects", command=self.open_cgaspects, state="disabled")
        self.aspects_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Clear log", command=lambda: self.log.delete("1.0", "end")).pack(side="right")

        self.log = tk.Text(monitor, wrap="none", bg="#ffffff", fg="#172033", insertbackground="#172033", relief="solid", borderwidth=1, font=("Consolas", 9))
        self.log.grid(row=3, column=0, sticky="nsew")
        self.log.tag_configure("error", foreground="#b91c1c")
        self.log.tag_configure("success", foreground="#047857")

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=4, pady=5)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, padx=4, pady=5)

    def _browse_cif(self) -> None:
        value = filedialog.askopenfilename(title="Select crystal structure", filetypes=[("CIF files", "*.cif"), ("All files", "*.*")])
        if value:
            self.cif_var.set(value)
            self.output_var.set(str(Path(value).resolve().parent))

    def _browse_output(self) -> None:
        value = filedialog.askdirectory(title="Select results folder")
        if value:
            self.output_var.set(value)

    def launch_structure_viewer(self) -> None:
        """Open the same PyVista molecular preview used by ORCA Input Builder."""
        cif = Path(self.cif_var.get().strip())
        if not cif.is_file():
            messagebox.showerror(APP_TITLE, "Select a valid CIF file first.", parent=self)
            return
        try:
            orca_input_dir = ORCA_TOOLS / "Orca_input"
            if not orca_input_dir.is_dir():
                raise FileNotFoundError(f"ORCA Input Builder source was not found: {orca_input_dir}")
            for location in (str(ORCA_TOOLS), str(orca_input_dir)):
                if location not in sys.path:
                    sys.path.insert(0, location)
            import orca_input as viewer

            pv_module = viewer.require_pyvista()
            if viewer.np is None:
                raise ValueError("NumPy is required for the structure preview.")
            structure = viewer.StructureParser.parse(str(cif))
            bonds = viewer.infer_bonds(structure, scale=1.20)
            points = viewer.np.array([[x, y, z] for _, x, y, z in structure.atoms], dtype=float)
            extent = float(viewer.np.linalg.norm(points.max(axis=0) - points.min(axis=0))) if len(points) else 1.0
            screen_height = max(1, int(self.winfo_screenheight() * 0.80))
            plotter = pv_module.Plotter(window_size=(screen_height, screen_height), lighting="none")
            viewer.configure_pyvista_defaults(
                pv_module,
                plotter,
                background="#555555",
                background_top="black",
                extent=extent,
            )
            for i, j in bonds:
                sym_i = structure.atoms[i][0]
                sym_j = structure.atoms[j][0]
                viewer.add_split_colored_bond(
                    pv_module,
                    plotter,
                    points[i],
                    points[j],
                    viewer.molecule_bond_end_color(sym_i),
                    viewer.molecule_bond_end_color(sym_j),
                )
            for index, (symbol, *_rest) in enumerate(structure.atoms):
                viewer.add_ball_and_stick_atom(pv_module, plotter, symbol, points[index])
            labels = [f"{index + 1}:{symbol}" for index, (symbol, *_rest) in enumerate(structure.atoms)]
            plotter.add_point_labels(points, labels, font_size=10, show_points=False, always_visible=False)
            plotter.add_text("Molecule view", position="upper_left", font_size=10)
            title = "Crystal Habit Builder - structure preview"
            viewer.bring_window_title_to_front(title)
            viewer.bring_pyvista_window_to_front(plotter)
            plotter.show(title=title)
        except Exception as exc:
            self.log.insert("end", f"\nPyVista viewer error: {exc}\n", "error")
            self.log.see("end")
            messagebox.showerror("PyVista viewer", str(exc), parent=self)

    def open_about_window(self) -> None:
        win = tk.Toplevel(self)
        win.title("About")
        win.transient(self)
        win.columnconfigure(0, weight=1)

        def copy_citation(_event=None) -> None:
            try:
                win.clipboard_clear()
                win.clipboard_append(CITATION_REFERENCE)
                citation_label.configure(text="Cite as: copied to clipboard", foreground="#047857")

                def restore_citation() -> None:
                    if citation_label.winfo_exists():
                        citation_label.configure(text=CITATION_TEXT, foreground="#1d4ed8")

                win.after(1400, restore_citation)
            except Exception as exc:
                messagebox.showerror("Copy citation", str(exc), parent=win)

        box = ttk.Frame(win, padding=14)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(1, weight=1)

        icon = load_header_icon(CRYSTAL_HABIT_ICON_PATH, max_size=144)
        if icon is not None:
            win.about_icon = icon
            ttk.Label(box, image=icon).grid(row=0, column=0, rowspan=8, sticky="n", padx=(0, 18))

        ttk.Label(box, text=APP_TITLE, font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(box, text=ABOUT_PURPOSE, justify="left", wraplength=420).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Separator(box, orient="horizontal").grid(row=2, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text="GitHub", font=("Segoe UI", 9, "bold")).grid(row=3, column=1, sticky="w")
        github_link = ttk.Label(box, text=GITHUB_URL, foreground="#1d4ed8", cursor="hand2")
        github_link.grid(row=4, column=1, sticky="w", pady=(2, 0))
        github_link.bind("<Button-1>", lambda _event: webbrowser.open(GITHUB_URL, new=2))
        ttk.Label(box, text="Documentation", font=("Segoe UI", 9, "bold")).grid(
            row=5, column=1, sticky="w", pady=(8, 0)
        )
        docs_link = ttk.Label(box, text="README: Crystal Habit Builder", foreground="#1d4ed8", cursor="hand2")
        docs_link.grid(row=6, column=1, sticky="w", pady=(2, 0))
        docs_link.bind("<Button-1>", lambda _event: webbrowser.open(DOCUMENTATION_URL, new=2))
        ai_link = ttk.Label(box, text="AI assistant", foreground="#1d4ed8", cursor="hand2")
        ai_link.grid(row=7, column=1, sticky="w", pady=(2, 0))
        ai_link.bind("<Button-1>", lambda _event: webbrowser.open(AI_ASSISTANT_URL, new=2))
        citation_label = ttk.Label(
            box,
            text=CITATION_TEXT,
            foreground="#1d4ed8",
            cursor="hand2",
            justify="left",
            wraplength=430,
        )
        citation_label.grid(row=8, column=1, sticky="w", pady=(10, 0))
        citation_label.bind("<Button-1>", copy_citation)
        ttk.Separator(box, orient="horizontal").grid(row=9, column=1, sticky="ew", pady=(12, 8))
        ttk.Label(box, text=COPYRIGHT_NOTE, foreground="#4b5563").grid(row=10, column=1, sticky="w")
        contact = ttk.Frame(box)
        contact.grid(row=11, column=1, sticky="w", pady=(7, 0))
        ttk.Label(contact, text=f"Email: {CONTACT_EMAIL}").grid(row=0, column=0, sticky="w")
        linkedin_icon = tk.Label(
            contact,
            text="in",
            bg="#0a66c2",
            fg="white",
            cursor="hand2",
            font=("Arial", 9, "bold"),
            padx=4,
            pady=1,
        )
        linkedin_icon.grid(row=0, column=1, padx=(10, 0))
        linkedin_icon.bind("<Button-1>", lambda _event: webbrowser.open(LINKEDIN_URL, new=2))
        ttk.Button(box, text="Close", command=win.destroy).grid(
            row=12, column=0, columnspan=2, sticky="e", pady=(14, 0)
        )
        win.geometry("620x430")
        win.minsize(560, 390)
        win.grab_set()

    def _program_paths(self) -> None:
        window = tk.Toplevel(self)
        window.title("Program paths")
        window.configure(bg="#f4f6f9")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        entries = [
            ("CrystalClear PowerShell script", self.crystalclear_var, [("PowerShell scripts", "*.ps1")]),
            ("CrystoGen executable", self.crystogen_var, [("Executable", "*.exe")]),
            ("CGAspects executable", self.cgaspects_var, [("Executable", "*.exe")]),
        ]
        for row, (label, var, filetypes) in enumerate(entries):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(frame, textvariable=var, width=70).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
            ttk.Button(frame, text="Browse…", command=lambda v=var, ft=filetypes: self._browse_program(v, ft)).grid(row=row, column=2, pady=5)
        frame.columnconfigure(1, weight=1)
        ttk.Button(frame, text="Close", style="Primary.TButton", command=window.destroy).grid(row=len(entries), column=0, columnspan=3, pady=(12, 0))

    @staticmethod
    def _browse_program(variable: tk.StringVar, filetypes) -> None:
        value = filedialog.askopenfilename(filetypes=filetypes)
        if value:
            variable.set(value)

    def add_solvent(self) -> None:
        value = self.solvent_entry_var.get().strip()
        if not value:
            return
        existing = [self.solvent_list.get(i) for i in range(self.solvent_list.size())]
        if value not in existing:
            self.solvent_list.insert("end", value)
        self.solvent_entry_var.set("")
        self.solvent_combo.focus_set()

    def remove_solvent(self) -> None:
        selected = list(self.solvent_list.curselection())
        for index in reversed(selected):
            self.solvent_list.delete(index)

    def selected_solvents(self) -> list[str]:
        values = [self.solvent_list.get(i).strip() for i in range(self.solvent_list.size())]
        pending = self.solvent_entry_var.get().strip()
        if pending and pending not in values:
            values.append(pending)
        return values

    def validate(self) -> dict[str, object]:
        cif = Path(self.cif_var.get().strip())
        if not cif.is_file() or cif.suffix.lower() != ".cif":
            raise ValueError("Select a valid CIF file.")
        solvents = self.selected_solvents()
        if not solvents:
            raise ValueError("Select at least one solvent.")
        paths = {
            "crystalclear": Path(self.crystalclear_var.get()),
            "crystogen": Path(self.crystogen_var.get()),
            "cgaspects": Path(self.cgaspects_var.get()),
        }
        for name in ("crystalclear", "crystogen"):
            if not paths[name].is_file():
                raise ValueError(f"Program not found: {paths[name]}")
        radius = float(self.radius_var.get())
        dmin = float(self.dmin_var.get())
        threads = int(self.threads_var.get())
        temperature = float(self.temperature_var.get())
        iterations = int(self.iterations_var.get())
        memory = int(self.memory_var.get())
        if min(radius, dmin, threads, iterations, memory) <= 0:
            raise ValueError("Numerical settings must be positive.")
        return {
            "cif": cif, "solvents": solvents, "paths": paths,
            "output": Path(self.output_var.get()), "model": self.model_var.get(),
            "solvation": self.solvation_var.get(), "radius": radius, "dmin": dmin,
            "threads": threads, "temperature": temperature, "iterations": iterations,
            "memory": memory,
        }

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            config = self.validate()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_root = config["output"] / f"{config['cif'].stem}_habit_{stamp}"
        run_root.mkdir(parents=True, exist_ok=False)
        self.current_run_root = run_root
        self.current_config = config
        self.final_xyz = None
        self.stop_event.clear()
        self.started_at = time.time()
        self.progress_var.set(0)
        self.progress_text_var.set("0%")
        self.log.delete("1.0", "end")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.aspects_button.configure(state="disabled")
        self.report_button.configure(state="normal")
        (run_root / "gui-settings.json").write_text(
            json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in config.items() if k != "paths"} | {"paths": {k: str(v) for k, v in config["paths"].items()}}, indent=2),
            encoding="utf-8",
        )
        self._write_summary_report(config, run_root, "Running")
        self.worker = threading.Thread(target=self._run_all, args=(config, run_root), daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        proc = self.process
        if proc and proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self._emit("log", "Stop requested.\n")

    def _run_all(self, config: dict[str, object], run_root: Path) -> None:
        completed_solvents: list[str] = []
        try:
            total = len(config["solvents"])
            for index, solvent in enumerate(config["solvents"]):
                if self.stop_event.is_set():
                    raise InterruptedError("Calculation stopped by user.")
                self._emit("solvent", solvent)
                self._emit("stage", "CrystalClear")
                crystal_dir = self._run_crystalclear(config, run_root, solvent, index, total)
                if self.stop_event.is_set():
                    raise InterruptedError("Calculation stopped by user.")
                self._emit("stage", "Crystal Grower")
                xyz = self._run_crystogen(config, run_root, solvent, crystal_dir, index, total)
                self.final_xyz = xyz
                completed_solvents.append(str(solvent))
            self._emit("progress", (100.0, "100%"))
            self._write_summary_report(config, run_root, "Completed", completed_solvents)
            self._emit("done", f"All calculations completed: {run_root}")
        except InterruptedError as exc:
            self._write_summary_report(config, run_root, "Stopped", completed_solvents, str(exc))
            self._emit("stopped", str(exc))
        except Exception as exc:
            self._write_summary_report(config, run_root, "Failed", completed_solvents, str(exc))
            self._emit("error", str(exc))
        finally:
            self.process = None

    def _run_crystalclear(self, config, run_root: Path, solvent: str, index: int, total: int) -> Path:
        output = run_root / "CrystalClear" / safe_name(solvent)
        output.mkdir(parents=True, exist_ok=True)
        occ_exe = config["paths"]["crystalclear"].parent / "occ-0.9.7-windows-x86_64" / "bin" / "occ.exe"
        if not occ_exe.is_file():
            raise RuntimeError(f"OCC executable was not found: {occ_exe}")
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(config["paths"]["crystalclear"]),
            "-CifPath", str(config["cif"]), "-Solvents", solvent,
            "-Model", str(config["model"]), "-SolvationModel", str(config["solvation"]),
            "-Radius", str(config["radius"]), "-SurfaceDMin", str(config["dmin"]),
            "-Threads", str(config["threads"]), "-OutputDirectory", str(output),
            "-OccExe", str(occ_exe),
        ]
        log_path = output / "gui-crystalclear.log"
        self._emit("log", f"\n=== CrystalClear: {solvent} ===\n{' '.join(command)}\n")
        completed_root: Path | None = None
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            for line in self._stream(command):
                log.write(line)
                self._emit("log", line)
                match = re.search(r"(\d+)/(\d+)\s+(\d+)%", line)
                if match:
                    within = int(match.group(3)) / 100
                    overall = ((index + within * 0.5) / total) * 100
                    self._emit("progress", (overall, f"CrystalClear dimer {match.group(1)}/{match.group(2)}"))
                match = re.search(r"Completed solvent comparison:\s*(.+)$", line.strip())
                if match:
                    completed_root = Path(match.group(1).strip())
        if self.process and self.process.returncode != 0:
            raise RuntimeError(f"CrystalClear failed for {solvent}; see {log_path}")
        if completed_root is None or not completed_root.is_dir():
            candidates = sorted(output.glob(f"{config['cif'].stem}_{config['model']}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
            completed_root = candidates[0] if candidates else None
        if completed_root is None:
            raise RuntimeError(f"Could not locate CrystalClear results for {solvent}.")
        solvent_dir = completed_root / safe_name(solvent)
        if not (solvent_dir / "input_cg.txt").is_file():
            raise RuntimeError(f"CrystalClear did not generate input_cg.txt for {solvent}.")
        return solvent_dir

    def _run_crystogen(self, config, run_root: Path, solvent: str, crystal_dir: Path, index: int, total: int) -> Path:
        safe = safe_name(solvent)
        result_dir = run_root / "CrystalGrower" / safe
        result_dir.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f"CrystalHabit_{safe}_"))
        try:
            shutil.copy2(crystal_dir / "input_cg.txt", stage / "structure.txt")
            net_candidates = list(crystal_dir.glob(f"*_{safe}_net.txt")) or list(crystal_dir.glob("*_net.txt"))
            if not net_candidates:
                raise RuntimeError(f"No Crystal Grower net file found for {solvent}.")
            shutil.copy2(net_candidates[0], stage / "net.txt")
            key = config["paths"]["crystogen"].parent / "CrystoGen.key"
            if not key.is_file():
                key = Path(r"C:\Program Files\CrystoGen\CrystoGen.key")
            if not key.is_file():
                raise RuntimeError("CrystoGen.key was not found.")
            shutil.copy2(key, stage / "CrystoGen.key")
            root = f"{config['cif'].stem}_{safe}"
            iterations = int(config["iterations"])
            main = "\n".join([
                ".", root, "no", "none", "yes", "structure.txt", "normal", "no", "none", "1", "1.0", "net", "yes",
                str(config["memory"]), f"{float(config['temperature']):.2f}", str(iterations), "3", "no", "100.00",
                "1", "1", str(iterations), "1000", "1", str(iterations), "no", "none", ""
            ])
            equilibration = min(100000, max(1, iterations // 10))
            add = f"no\nno\n{equilibration}\n{equilibration}\nno\n"
            (stage / "input.txt").write_text(main, encoding="ascii")
            (stage / "addinput.txt").write_text(add, encoding="ascii")
            for name in ("input.txt", "structure.txt", "net.txt"):
                shutil.copy2(stage / name, result_dir / name)
            self._emit("log", f"\n=== Crystal Grower: {solvent} ===\n")
            with (stage / "addinput.txt").open("r", encoding="ascii") as stdin, (stage / "stdout.log").open("w", encoding="utf-8") as logfile:
                command = [str(config["paths"]["crystogen"])]
                for line in self._stream(command, cwd=stage, stdin=stdin):
                    logfile.write(line)
                    self._emit("log", line)
                    match = re.search(r"Iterations\s+(\d+)", line)
                    if match:
                        current = min(int(match.group(1)), iterations)
                        within = current / iterations
                        overall = ((index + 0.5 + within * 0.5) / total) * 100
                        self._emit("progress", (overall, f"CrystoGen {current:,}/{iterations:,}"))
            if self.process and self.process.returncode != 0:
                raise RuntimeError(f"Crystal Grower failed for {solvent}.")
            # Copy the completed working files before validation so diagnostics
            # survive even when a CrystalGrower output check fails.
            for item in stage.iterdir():
                if item.is_file() and item.name != "CrystoGen.key":
                    shutil.copy2(item, result_dir / item.name)

            # Do not use glob here: CIF stems may contain glob metacharacters.
            parameter_file = stage / f".{root}_simulation_parameters.txt"
            parameter_text = parameter_file.read_text(encoding="utf-8", errors="replace") if parameter_file.is_file() else ""
            completion_pattern = rf"Total iterations completed[^\r\n]*\b{iterations}\b"
            if not re.search(completion_pattern, parameter_text):
                raise RuntimeError(f"Crystal Grower completion could not be validated for {solvent}.")
            xyz_files = list(result_dir.glob("*_CGAspects.XYZ"))
            if not xyz_files:
                raise RuntimeError(f"No CGAspects XYZ result was generated for {solvent}.")
            return xyz_files[0]
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def _stream(self, command: list[str], cwd: Path | None = None, stdin=None):
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            command, cwd=str(cwd) if cwd else None, stdin=stdin,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=flags,
        )
        assert self.process.stdout is not None
        for line in iter(self.process.stdout.readline, ""):
            yield line
            if self.stop_event.is_set():
                break
        self.process.wait()

    def _emit(self, kind: str, value: object) -> None:
        self.events.put((kind, value))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.log.insert("end", str(value))
                    self.log.see("end")
                elif kind == "stage":
                    self.stage_var.set(str(value))
                elif kind == "solvent":
                    self.solvent_status_var.set(str(value))
                elif kind == "progress":
                    progress, text = value
                    self.progress_var.set(progress)
                    self.progress_text_var.set(str(text))
                elif kind == "done":
                    self._finish_controls()
                    self.stage_var.set("Completed")
                    self.log.insert("end", f"\n{value}\n", "success")
                    self.aspects_button.configure(state="normal" if self.final_xyz else "disabled")
                    if self.final_xyz:
                        self.open_cgaspects()
                    messagebox.showinfo(APP_TITLE, str(value), parent=self)
                elif kind == "stopped":
                    self._finish_controls()
                    self.stage_var.set("Stopped")
                    self.log.insert("end", f"\n{value}\n", "error")
                elif kind == "error":
                    self._finish_controls()
                    self.stage_var.set("Failed")
                    self.log.insert("end", f"\nERROR: {value}\n", "error")
                    messagebox.showerror(APP_TITLE, str(value), parent=self)
        except queue.Empty:
            pass
        self.after(150, self._drain_events)

    def _finish_controls(self) -> None:
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.process = None

    def _update_metrics(self) -> None:
        if self.started_at and self.worker and self.worker.is_alive():
            elapsed = int(time.time() - self.started_at)
            self.elapsed_var.set(f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}")
            proc = self.process
            if proc and proc.poll() is None:
                cpu, ram = process_stats(proc.pid)
                self.cpu_var.set(f"{cpu:.1f} s" if cpu is not None else "—")
                self.ram_var.set(f"{ram:.0f} MB" if ram is not None else "—")
        self.after(1000, self._update_metrics)

    def open_results(self) -> None:
        folder = self.current_run_root or Path(self.output_var.get())
        if folder.exists():
            os.startfile(folder)
        else:
            messagebox.showwarning(APP_TITLE, "The results folder does not exist yet.", parent=self)

    def _write_summary_report(
        self,
        config: dict[str, object],
        run_root: Path,
        status: str,
        completed_solvents: list[str] | None = None,
        note: str = "",
    ) -> Path:
        completed = completed_solvents or []
        solvents = [str(item) for item in config["solvents"]]
        esc = lambda value: html.escape(str(value))
        solvent_text = ", ".join(esc(item) for item in solvents)
        completed_text = ", ".join(esc(item) for item in completed) if completed else "None"
        solvation = str(config["solvation"])
        smd_reference = "" if solvation.lower() != "smd" else """
          <li>Marenich, A. V.; Cramer, C. J.; Truhlar, D. G. <i>J. Phys. Chem. B</i> <b>2009</b>, 113, 6378–6396. <a href="https://doi.org/10.1021/jp810292n">https://doi.org/10.1021/jp810292n</a> (SMD).</li>"""
        note_html = f"<p><b>Status note:</b> {esc(note)}</p>" if note else ""
        report = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Crystal Habit Summary</title>
<style>
body {{ font-family: "Segoe UI", Arial, sans-serif; max-width: 900px; margin: 36px auto; color: #172033; line-height: 1.45; }}
h1 {{ color: #1e3a5f; margin-bottom: 0; }} h2 {{ color: #294f78; margin-top: 1.4em; }}
.status {{ display: inline-block; margin: 8px 0 16px; padding: 5px 10px; border-radius: 4px; background: #e8f1fb; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border-bottom: 1px solid #d8dee8; padding: 7px 9px; text-align: left; vertical-align: top; }}
th {{ width: 30%; background: #f4f6f9; }} code {{ color: #263348; }} .small {{ color: #53627a; font-size: 0.92em; }}
</style></head><body>
<h1>Crystal Habit Calculation Summary</h1>
<div class="status">{esc(status)}</div>
<p class="small">Generated {esc(time.strftime('%Y-%m-%d %H:%M:%S'))}</p>
{note_html}
<h2>Scientific workflow</h2>
<p>CrystalClear, executed through OCC 0.9.7, was used to calculate solvent-dependent crystal interaction and facet energetics. The resulting molecular structure and interaction net were supplied to CrystoGen/CrystalGrower for a kinetic Monte Carlo simulation of crystal growth and habit.</p>
<h2>Calculation</h2>
<table>
<tr><th>Crystal structure</th><td><code>{esc(config['cif'])}</code></td></tr>
<tr><th>Solvents</th><td>{solvent_text}</td></tr>
<tr><th>Completed solvents</th><td>{completed_text}</td></tr>
<tr><th>CrystalClear model</th><td>{esc(config['model'])}</td></tr>
<tr><th>Solvation treatment</th><td>{esc(solvation)}</td></tr>
<tr><th>Interaction radius</th><td>{esc(config['radius'])} Å</td></tr>
<tr><th>Surface cutoff, d<sub>min</sub></th><td>{esc(config['dmin'])} Å</td></tr>
<tr><th>CrystalClear threads</th><td>{esc(config['threads'])}</td></tr>
<tr><th>Growth temperature</th><td>{esc(config['temperature'])} °C</td></tr>
<tr><th>Monte Carlo iterations</th><td>{int(config['iterations']):,}</td></tr>
<tr><th>CrystoGen memory setting</th><td>{int(config['memory']):,}</td></tr>
<tr><th>Results directory</th><td><code>{esc(run_root)}</code></td></tr>
</table>
<h2>Software</h2>
<ul><li>Crystal Habit Builder (CrystEngKit-ORCA workflow interface)</li><li>OCC 0.9.7 / CrystalClear</li><li>CrystoGen / CrystalGrower kinetic Monte Carlo engine</li><li>CGAspects for morphology inspection</li></ul>
<h2>References</h2>
<ol>
<li>Spackman, P. R.; Walisinghe, A. J.; Anderson, M. W.; Gale, J. D. <i>Chem. Sci.</i> <b>2023</b>, 14, 7192–7207. <a href="https://doi.org/10.1039/D2SC06761G">https://doi.org/10.1039/D2SC06761G</a> (CrystalClear).</li>
<li>Hill, A. R. <i>et al.</i> <i>Chem. Sci.</i> <b>2021</b>, 12, 1126–1146. <a href="https://doi.org/10.1039/D0SC05017B">https://doi.org/10.1039/D0SC05017B</a> (CrystalGrower).</li>
{smd_reference}
</ol>
</body></html>"""
        report_path = run_root / "crystal-habit-summary.html"
        report_path.write_text(report, encoding="utf-8")
        return report_path

    def open_summary_report(self) -> None:
        if not self.current_run_root:
            messagebox.showwarning(APP_TITLE, "No calculation report is available yet.", parent=self)
            return
        report_path = self.current_run_root / "crystal-habit-summary.html"
        if not report_path.is_file() and self.current_config is not None:
            self._write_summary_report(self.current_config, self.current_run_root, self.stage_var.get())
        if report_path.is_file():
            os.startfile(report_path)
        else:
            messagebox.showerror(APP_TITLE, "The summary report could not be created.", parent=self)

    def open_cgaspects(self) -> None:
        exe = Path(self.cgaspects_var.get())
        if not exe.is_file():
            messagebox.showerror(APP_TITLE, "CGAspects executable was not found.", parent=self)
            return
        if not self.final_xyz or not self.final_xyz.is_file():
            messagebox.showwarning(APP_TITLE, "No completed CGAspects XYZ file is available.", parent=self)
            return
        stage = Path(tempfile.mkdtemp(prefix="CrystalHabit_CGAspects_"))
        staged_xyz = stage / self.final_xyz.name
        try:
            shutil.copy2(self.final_xyz, staged_xyz)
            process = subprocess.Popen([str(exe), str(staged_xyz)], cwd=str(stage))
        except Exception as exc:
            shutil.rmtree(stage, ignore_errors=True)
            messagebox.showerror(APP_TITLE, f"CGAspects could not be opened:\n{exc}", parent=self)
            return

        self.log.insert("end", f"\nOpened CGAspects with {self.final_xyz.name}\n")
        self.log.see("end")

        def cleanup_after_exit() -> None:
            process.wait()
            shutil.rmtree(stage, ignore_errors=True)

        threading.Thread(target=cleanup_after_exit, daemon=True).start()

    def on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_TITLE, "A calculation is running. Stop it and close?", parent=self):
                return
            self.stop()
        self.destroy()


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    initial_cif = arguments[0] if arguments else None
    CrystalHabitApp(initial_cif=initial_cif).mainloop()


if __name__ == "__main__":
    main()
