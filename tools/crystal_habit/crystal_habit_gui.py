from __future__ import annotations

import ctypes
from ctypes import wintypes
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
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Crystal Habit Builder"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_CRYSTALCLEAR = Path.home() / "Documents" / "OCC-CrystalClear" / "Run-CrystalClear.ps1"
DEFAULT_CRYSTOGEN = APP_DIR / "tools" / "crystogen" / "crystogen.exe"
DEFAULT_CGASPECTS = Path(r"C:\Program Files\CrystoGen\CGAspects\CGAspects.exe")
DEFAULT_OUTPUT = Path.home() / "Documents" / "CrystalHabitBuilder" / "runs"
ORCA_TOOLS = Path.home() / "OneDrive" / "Python" / "crystengkit-orca-v1.0" / "tools"

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


class CrystalHabitApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
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
        self.final_xyz: Path | None = None

        self.cif_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT))
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
        self.bind_all("<Control-r>", self._reload_application, add="+")
        self.after(150, self._drain_events)
        self.after(1000, self._update_metrics)

    def _reload_application(self, _event=None) -> str:
        """Hidden Ctrl+R reload, matching ORCA Input Builder behavior."""
        if self.worker and self.worker.is_alive():
            self.bell()
            return "break"

        command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
        kwargs = {"cwd": os.getcwd()}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(command, **kwargs)
        except Exception:
            self.bell()
            return "break"

        self.after_idle(self.destroy)
        return "break"

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(background="#f4f6f9")
        style.configure("TFrame", background="#f4f6f9")
        style.configure("Panel.TFrame", background="#f8fafc")
        style.configure("Header.TFrame", background="#1e3a5f")
        style.configure("HeaderTitle.TLabel", background="#1e3a5f", foreground="#f8fafc", font=("Segoe UI", 15, "bold"))
        style.configure("HeaderSub.TLabel", background="#1e3a5f", foreground="#d7e1ee", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe", background="#f8fafc", bordercolor="#d8dee8", relief="solid", padding=10)
        style.configure("TLabelframe.Label", background="#f8fafc", foreground="#172033", font=("Segoe UI", 10, "bold"))
        style.configure("TLabel", background="#f8fafc", foreground="#263348", font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background="#f4f6f9", foreground="#53627a", font=("Segoe UI", 9))
        style.configure("TCheckbutton", background="#f8fafc", font=("Segoe UI", 9))
        style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
        style.configure("Primary.TButton", background="#2f80c8", foreground="#ffffff", padding=(14, 8), font=("Segoe UI", 10, "bold"))
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
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="CrystalClear → Crystal Grower → CGAspects", style="HeaderSub.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Label(header, text="OCC / CrystoGen", style="HeaderSub.TLabel").grid(row=0, column=1, rowspan=2, padx=10)

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
        self.final_xyz = None
        self.stop_event.clear()
        self.started_at = time.time()
        self.progress_var.set(0)
        self.progress_text_var.set("0%")
        self.log.delete("1.0", "end")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.aspects_button.configure(state="disabled")
        (run_root / "gui-settings.json").write_text(
            json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in config.items() if k != "paths"} | {"paths": {k: str(v) for k, v in config["paths"].items()}}, indent=2),
            encoding="utf-8",
        )
        self.worker = threading.Thread(target=self._run_all, args=(config, run_root), daemon=True)
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        proc = self.process
        if proc and proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        self._emit("log", "Stop requested.\n")

    def _run_all(self, config: dict[str, object], run_root: Path) -> None:
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
            self._emit("progress", (100.0, "100%"))
            self._emit("done", f"All calculations completed: {run_root}")
        except InterruptedError as exc:
            self._emit("stopped", str(exc))
        except Exception as exc:
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
            parameter_files = list(stage.glob(f".{root}_simulation_parameters.txt"))
            parameter_text = parameter_files[0].read_text(encoding="utf-8", errors="replace") if parameter_files else ""
            completion_pattern = rf"Total iterations completed[^\r\n]*\b{iterations}\b"
            if not re.search(completion_pattern, parameter_text):
                raise RuntimeError(f"Crystal Grower completion could not be validated for {solvent}.")
            for item in stage.iterdir():
                if item.is_file() and item.name != "CrystoGen.key":
                    shutil.copy2(item, result_dir / item.name)
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

    def open_cgaspects(self) -> None:
        exe = Path(self.cgaspects_var.get())
        if not exe.is_file():
            messagebox.showerror(APP_TITLE, "CGAspects executable was not found.", parent=self)
            return
        if not self.final_xyz or not self.final_xyz.is_file():
            messagebox.showwarning(APP_TITLE, "No completed CGAspects XYZ file is available.", parent=self)
            return
        subprocess.Popen([str(exe), str(self.final_xyz)], cwd=str(self.final_xyz.parent))

    def on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_TITLE, "A calculation is running. Stop it and close?", parent=self):
                return
            self.stop()
        self.destroy()


if __name__ == "__main__":
    CrystalHabitApp().mainloop()
