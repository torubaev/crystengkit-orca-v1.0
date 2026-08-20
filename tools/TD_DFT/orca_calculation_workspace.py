"""Self-contained single-job ORCA editor and monitor for the TD-DFT panel."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from shared.orca_parallel import add_mpi_to_path


def subprocess_environment(executable: str) -> dict[str, str]:
    env = os.environ.copy()
    folder = str(Path(executable).resolve().parent)
    env["PATH"] = folder + os.pathsep + env.get("PATH", "")
    return add_mpi_to_path(env)


def orca_stage(text: str) -> str:
    upper = text.upper()
    checks = (
        ("ORCA TERMINATED NORMALLY", "Finished normally"),
        ("ORCA FINISHED BY ERROR TERMINATION", "Error termination"),
        ("ABORTING THE RUN", "Error termination"),
        ("TD-DFT/TDA EXCITED STATES", "TD-DFT excited states"),
        ("VIBRATIONAL FREQUENCIES", "Frequency calculation"),
        ("GEOMETRY OPTIMIZATION CYCLE", "Geometry optimization"),
        ("SCF ITERATION", "SCF iterations"),
        ("STARTING SCF", "SCF start"),
    )
    return next((stage for marker, stage in checks if marker in upper), "")


def output_summary(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [f"Output: {path}", f"Size: {path.stat().st_size:,} bytes"]
    lines.append("Status: Normal termination" if "ORCA TERMINATED NORMALLY" in text.upper() else "Status: Incomplete or failed")
    for label, pattern in (
        ("Final energy", r"(?im)^\s*FINAL SINGLE POINT ENERGY\s+([-+0-9.Ee]+)"),
        ("Runtime", r"(?im)^\s*TOTAL RUN TIME:\s*(.+)$"),
    ):
        matches = re.findall(pattern, text)
        if matches:
            lines.append(f"{label}: {matches[-1].strip()}")
    states = text.upper().count("STATE ")
    if states:
        lines.append(f"Excited-state records: {states}")
    return "\n".join(lines)


class OrcaCalculationWorkspace(ttk.LabelFrame):
    """Editable ORCA input plus an independent local-process monitor."""

    def __init__(
        self,
        parent,
        *,
        input_provider: Callable[[], str],
        orca_path_provider: Callable[[], str],
        initial_path_provider: Optional[Callable[[], str]] = None,
        active_job_provider: Optional[Callable[[], dict]] = None,
        completed_callback: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent, text="Input preview / ORCA job monitor", padding=8)
        self.input_provider = input_provider
        self.orca_path_provider = orca_path_provider
        self.initial_path_provider = initial_path_provider
        self.active_job_provider = active_job_provider
        self.completed_callback = completed_callback
        self.input_path = ""
        self.output_path = ""
        self.process: Optional[subprocess.Popen] = None
        self.started_at = 0.0
        self.monitor_offset = 0
        self.mode = "input"
        self.input_buffer = ""
        self.monitor_buffer = ""
        self.external_monitor = False
        self.status_var = tk.StringVar(value="Status: Idle")
        self.elapsed_var = tk.StringVar(value="Elapsed: 00:00:00")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        toolbar.columnconfigure(6, weight=1)
        ttk.Button(toolbar, text="Input", command=self.show_input).grid(row=0, column=0)
        ttk.Button(toolbar, text="Monitor", command=self.show_monitor).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(toolbar, text="Prepare / refresh", command=self.refresh_input).grid(row=0, column=2, padx=(10, 0))
        ttk.Button(toolbar, text="Open input...", command=self.open_input).grid(row=0, column=3, padx=(4, 0))
        ttk.Button(toolbar, text="Save input...", command=self.save_input).grid(row=0, column=4, padx=(4, 0))
        ttk.Button(toolbar, text="View summary", command=self.show_summary).grid(row=0, column=5, padx=(4, 0))
        self.run_button = ttk.Button(toolbar, text="Run this input", command=self.run_orca, style="Primary.TButton")
        self.run_button.grid(row=0, column=7, padx=(10, 0))
        self.stop_button = ttk.Button(toolbar, text="Stop", command=self.stop_orca, state="disabled")
        self.stop_button.grid(row=0, column=8, padx=(4, 0))
        secondary = ttk.Frame(self)
        secondary.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        ttk.Button(secondary, text="Open output", command=self.open_output).pack(side="left")
        ttk.Button(secondary, text="Open job folder", command=self.open_job_folder).pack(side="left", padx=(4, 0))
        ttk.Button(secondary, text="Clear monitor", command=self.clear_monitor).pack(side="left", padx=(4, 0))
        status = ttk.Frame(self)
        status.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(status, textvariable=self.elapsed_var, font=("Consolas", 9)).grid(row=0, column=2, sticky="e")
        self.text = tk.Text(self, wrap="none", height=18, font=("Consolas", 10), undo=True, relief="solid", bd=1)
        self.text.grid(row=3, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        yscroll.grid(row=3, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        xscroll.grid(row=4, column=0, sticky="ew")
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

    def _capture(self) -> None:
        value = self.text.get("1.0", "end-1c")
        if self.mode == "input":
            self.input_buffer = value
        else:
            self.monitor_buffer = value

    def show_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        self._capture()
        self.mode = mode
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.input_buffer if mode == "input" else self.monitor_buffer)
        self.text.configure(state="normal" if mode == "input" else "disabled")
        self.text.see("1.0" if mode == "input" else "end")

    def show_input(self) -> None:
        """Show the editor and fetch prepared input when it has no content yet."""
        if not self.input_buffer.strip():
            self.refresh_input()
        else:
            self.show_mode("input")

    def show_monitor(self) -> None:
        """Show local output or attach to the current Builder-launched job."""
        if self.process and self.process.poll() is None:
            self.show_mode("monitor")
            return
        job = self.active_job_provider() if callable(self.active_job_provider) else {}
        output_path = str((job or {}).get("output_path", "") or "")
        if output_path:
            changed_source = os.path.normcase(output_path) != os.path.normcase(self.output_path or "")
            if self.external_monitor and not changed_source:
                self.show_mode("monitor")
                return
            self.output_path = output_path
            self.input_path = str((job or {}).get("input_path", "") or self.input_path)
            fallback_started = Path(output_path).stat().st_mtime if Path(output_path).is_file() else time.time()
            self.started_at = float((job or {}).get("started_at", 0.0) or fallback_started)
            if changed_source or not self.external_monitor:
                self.monitor_buffer = ""
                self.monitor_offset = 0
            self.external_monitor = True
            self.show_mode("monitor")
            self.status_var.set(f"Status: {(job or {}).get('stage') or 'Attached to Builder output'}")
            self._poll()
            return
        self.show_mode("monitor")
        self.status_var.set("Status: No Builder or TD-DFT output is available")

    def set_input(self, text: str, path: str = "", *, status: str = "Input synchronized") -> bool:
        """Adopt an existing input without regenerating or overwriting local edits."""
        value = str(text or "")
        if not value.strip():
            return False
        self.input_buffer = value
        if path:
            self.input_path = str(path)
        if self.mode == "input":
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", value)
        self.status_var.set(f"Status: {status}")
        return True

    def refresh_input(self) -> bool:
        try:
            self.input_buffer = self.input_provider()
            self.show_mode("input")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.input_buffer)
            self.status_var.set("Status: Input prepared")
            return True
        except Exception as exc:
            messagebox.showerror("Prepare ORCA input", str(exc), parent=self)
            return False

    def open_input(self) -> None:
        path = filedialog.askopenfilename(parent=self, filetypes=[("ORCA input", "*.inp"), ("All files", "*.*")])
        if not path:
            return
        self.input_path = path
        self.input_buffer = Path(path).read_text(encoding="utf-8", errors="replace")
        self.show_mode("input")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.input_buffer)
        self.status_var.set(f"Status: Loaded {Path(path).name}")

    def save_input(self) -> str:
        if self.mode == "input":
            self._capture()
        if not self.input_buffer.strip() and not self.refresh_input():
            return ""
        suggested = self.input_path or (self.initial_path_provider() if self.initial_path_provider else "")
        initial = Path(suggested) if suggested else Path("tddft.inp")
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".inp", initialdir=str(initial.parent), initialfile=initial.name, filetypes=[("ORCA input", "*.inp")])
        if not path:
            return ""
        Path(path).write_text(self.input_buffer, encoding="utf-8")
        self.input_path = path
        self.status_var.set(f"Status: Saved {Path(path).name}")
        return path

    def _append_monitor(self, value: str) -> None:
        self.monitor_buffer += value
        if self.mode == "monitor":
            self.text.configure(state="normal")
            self.text.insert("end", value)
            self.text.see("end")
            self.text.configure(state="disabled")

    def run_orca(self) -> None:
        try:
            if self.process and self.process.poll() is None:
                raise ValueError("An ORCA calculation is already running in TD-DFT.")
            executable = self.orca_path_provider().strip().strip('"')
            if not executable or not Path(executable).is_file():
                selected = filedialog.askopenfilename(parent=self, title="Locate ORCA executable", filetypes=[("ORCA executable", "orca.exe"), ("All files", "*.*")])
                executable = selected or ""
            if not executable:
                return
            if not self.input_buffer.strip():
                if not self.refresh_input():
                    return
            path = self.input_path
            if not path or not Path(path).is_file():
                path = self.save_input()
            if not path:
                return
            output_path = Path(path).with_suffix(".out")
            if output_path.exists():
                for number in range(1, 10000):
                    safe_input = Path(path).with_name(f"{Path(path).stem}_{number:02d}.inp")
                    if not safe_input.exists() and not safe_input.with_suffix(".out").exists():
                        break
                if not messagebox.askyesno(
                    "Preserve completed files",
                    f"An output already exists for this input:\n{output_path}\n\n"
                    f"Run with the safe filename instead?\n{safe_input}",
                    parent=self,
                ):
                    return
                safe_input.write_text(self.input_buffer, encoding="utf-8")
                path = str(safe_input)
                self.input_path = path
                output_path = safe_input.with_suffix(".out")
            self.output_path = str(output_path)
            self.external_monitor = False
            self.monitor_buffer = ""
            self.monitor_offset = 0
            self.started_at = time.time()
            output = open(self.output_path, "w", encoding="utf-8", errors="replace")
            try:
                self.process = subprocess.Popen([executable, Path(path).name], cwd=str(Path(path).parent), env=subprocess_environment(executable), stdout=output, stderr=subprocess.STDOUT, shell=False)
            finally:
                output.close()
            self.show_mode("monitor")
            self._append_monitor(f"ORCA PID {self.process.pid}\nInput: {path}\nOutput: {self.output_path}\n\n")
            self.run_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status_var.set("Status: Starting ORCA")
            self.after(250, self._poll)
        except Exception as exc:
            messagebox.showerror("Run this ORCA input", str(exc), parent=self)

    def _poll(self) -> None:
        if self.output_path and Path(self.output_path).is_file():
            with Path(self.output_path).open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.monitor_offset)
                chunk = handle.read()
                self.monitor_offset = handle.tell()
            if chunk:
                self._append_monitor(chunk)
                stage = orca_stage(chunk)
                if stage:
                    self.status_var.set(f"Status: {stage}")
        elapsed = max(0, int(time.time() - self.started_at))
        self.elapsed_var.set(f"Elapsed: {elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}")
        if self.process and self.process.poll() is None:
            self.after(750, self._poll)
            return
        if self.external_monitor:
            job = self.active_job_provider() if callable(self.active_job_provider) else {}
            if bool((job or {}).get("running")):
                self.status_var.set(f"Status: {(job or {}).get('stage') or 'Running in Input Builder'}")
                self.after(750, self._poll)
                return
            self.external_monitor = False
            normal = "ORCA TERMINATED NORMALLY" in self.monitor_buffer.upper()
            self.status_var.set("Status: Finished normally" if normal else f"Status: {(job or {}).get('stage') or 'Builder job stopped'}")
            if self.completed_callback and self.output_path and Path(self.output_path).is_file():
                self.completed_callback(self.output_path)
            return
        code = self.process.poll() if self.process else -1
        self.process = None
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status_var.set("Status: Finished normally" if code == 0 and "ORCA TERMINATED NORMALLY" in self.monitor_buffer.upper() else f"Status: ORCA exited with code {code}")
        if self.completed_callback and self.output_path:
            self.completed_callback(self.output_path)

    def stop_orca(self) -> None:
        if self.process and self.process.poll() is None and messagebox.askyesno("Stop ORCA", "Stop this ORCA calculation?", parent=self):
            self.process.terminate()
            self.status_var.set("Status: Stop requested")

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], shell=False)
        else:
            subprocess.Popen(["xdg-open", str(path)], shell=False)

    def open_output(self) -> None:
        path = Path(self.output_path) if self.output_path else None
        if path is None or not path.is_file():
            messagebox.showinfo("Open ORCA output", "No output file is available yet.", parent=self)
            return
        self._open_path(path)

    def open_job_folder(self) -> None:
        value = self.output_path or self.input_path
        if not value:
            messagebox.showinfo("Open job folder", "Save or open an input file first.", parent=self)
            return
        self._open_path(Path(value).parent)

    def clear_monitor(self) -> None:
        self.monitor_buffer = ""
        if self.mode == "monitor":
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")

    def show_summary(self) -> None:
        path = Path(self.output_path) if self.output_path else (Path(self.input_path).with_suffix(".out") if self.input_path else None)
        if path is None or not path.is_file():
            messagebox.showinfo("ORCA summary", "No output file is available yet.", parent=self)
            return
        messagebox.showinfo("ORCA summary", output_summary(path), parent=self)
