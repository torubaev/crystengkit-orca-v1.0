"""Visual Tk interface for systematic torsional geometry generation."""
from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Sequence

import numpy as np

try:
    from .torsion_generator import (
        DEFAULT_ORCA_TEMPLATE, ConfigurationError, Molecule, generate,
        infer_bonds, parse_config_data, read_xyz, rotate_coordinates,
        scan_plan, write_summary,
    )
except ImportError:
    from torsion_generator import (  # type: ignore
        DEFAULT_ORCA_TEMPLATE, ConfigurationError, Molecule, generate,
        infer_bonds, parse_config_data, read_xyz, rotate_coordinates,
        scan_plan, write_summary,
    )


ANGLE_PRESETS = {
    "Small: -15 to +15 / 5": [-15, -10, -5, 0, 5, 10, 15],
    "Medium: -30 to +30 / 10": [-30, -20, -10, 0, 10, 20, 30],
    "Full: -90 to +90 / 15": list(range(-90, 91, 15)),
}


def parse_atom_numbers(text: str) -> list[int]:
    """Parse optional advanced one-based syntax such as ``2, 5-8 11``."""
    values: list[int] = []
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if match:
            start, stop = map(int, match.groups())
            if stop < start:
                raise ConfigurationError(f"Descending atom range is not allowed: {token}")
            values.extend(range(start, stop + 1))
        elif token.isdigit():
            values.append(int(token))
        else:
            raise ConfigurationError(f"Invalid atom-number token: {token!r}")
    if not values:
        raise ConfigurationError("Enter at least one atom number.")
    return values


def parse_angles_text(text: str) -> list[float]:
    values: list[float] = []
    for token in re.split(r"[\s,;]+", text.strip()):
        if token:
            try:
                values.append(float(token))
            except ValueError as exc:
                raise ConfigurationError(f"Invalid angle: {token!r}") from exc
    if not values or not np.isfinite(values).all():
        raise ConfigurationError("Enter one or more finite angles.")
    return values


def molecule_from_atoms(atoms: Sequence[Sequence[Any]], title: str = "molecule") -> Molecule:
    symbols, coordinates = [], []
    for number, atom in enumerate(atoms, 1):
        if len(atom) < 4:
            raise ConfigurationError(f"Builder atom {number} has incomplete coordinates.")
        symbols.append(str(atom[0]))
        coordinates.append([float(atom[1]), float(atom[2]), float(atom[3])])
    if not symbols:
        raise ConfigurationError("Builder has no molecular geometry loaded.")
    return Molecule(tuple(symbols), np.asarray(coordinates, dtype=float), title)


def rotating_side_for_axis(molecule: Molecule, first: int, second: int) -> set[int] | None:
    """Return the second-atom component after deleting the axis bond.

    ``None`` means the inferred graph remains cyclic, so the fragment cannot be
    selected safely without user input.
    """
    bonds = infer_bonds(molecule)
    key = tuple(sorted((first, second)))
    if key not in bonds:
        return None
    adjacency = {index: set() for index in range(len(molecule.symbols))}
    for left, right in bonds:
        if (left, right) == key:
            continue
        adjacency[left].add(right); adjacency[right].add(left)
    seen, pending = {second}, [second]
    while pending:
        node = pending.pop()
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor); pending.append(neighbor)
    return None if first in seen else seen


class TorsionGeneratorPanel(ttk.Frame):
    """A click-first torsion workflow with advanced settings kept optional."""

    def __init__(self, parent, molecule: Molecule, source_path: str = "", charge: int = 0, multiplicity: int = 1, host_window=None):
        super().__init__(parent)
        self.host_window = host_window
        self.molecule, self.source_path = molecule, source_path
        self.rotations: list[dict[str, Any]] = []
        self.axis_selection: list[int] = []
        self.fragment_selection: set[int] = set()
        self.selection_phase = "axis"
        self.preview_canvas = self.preview_axis = self.preview_figure = None
        self.projected_atoms: dict[int, tuple[float, float]] = {}
        self.model_press: tuple[float, float] | None = None
        self.mode_var = tk.StringVar(value="single")
        self.preset_var = tk.StringVar(value=next(iter(ANGLE_PRESETS)))
        self.custom_angles_var = tk.StringVar(value="-15,-10,-5,0,5,10,15")
        self.preview_angle_var = tk.DoubleVar(value=0.0)
        self.output_var = tk.StringVar(value=str((Path(source_path).parent if source_path else Path.cwd()) / "generated_structures"))
        self.write_orca_var = tk.BooleanVar(value=False)
        self.charge_var = tk.StringVar(value=str(charge)); self.multiplicity_var = tk.StringVar(value=str(multiplicity))
        self.collision_var = tk.StringVar(value="0.8"); self.max_displacement_var = tk.StringVar(value="")
        self.strict_var = tk.BooleanVar(value=False); self.max_structures_var = tk.StringVar(value="1000")
        self.random_count_var = tk.StringVar(value="10"); self.random_seed_var = tk.StringVar(value="0")
        self.template_var = tk.StringVar(value="")
        self.axis_status_var = tk.StringVar(value="Click the first axis atom in the model.")
        self.fragment_status_var = tk.StringVar(value="Rotating fragment: not selected")
        self.status_var = tk.StringVar(value="1. Select an axis  →  2. Confirm fragment  →  3. Choose scan  →  4. Generate")
        self._build()
        self._draw_preview(self.molecule.coordinates, "Click the first axis atom")
        self.pack(fill="both", expand=True)

    def get_state(self) -> dict[str, Any]:
        names = (
            "mode_var", "preset_var", "custom_angles_var", "preview_angle_var", "output_var",
            "write_orca_var", "charge_var", "multiplicity_var", "collision_var",
            "max_displacement_var", "strict_var", "max_structures_var", "random_count_var",
            "random_seed_var", "template_var",
        )
        return {
            "variables": {name: getattr(self, name).get() for name in names},
            "rotations": self.rotations,
            "axis_selection": self.axis_selection,
            "fragment_selection": sorted(self.fragment_selection),
            "selection_phase": self.selection_phase,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        for name, value in (state or {}).get("variables", {}).items():
            variable = getattr(self, name, None)
            if isinstance(variable, tk.Variable):
                variable.set(value)
        self.rotations = list((state or {}).get("rotations", []))
        self.axis_selection = list((state or {}).get("axis_selection", []))
        self.fragment_selection = set((state or {}).get("fragment_selection", []))
        self.selection_phase = str((state or {}).get("selection_phase", "axis"))
        self._refresh_rotations()
        self._draw_preview(self.molecule.coordinates, "Restored project workspace")

    def set_molecule(self, molecule: Molecule, source_path: str = "", charge: int | None = None, multiplicity: int | None = None) -> None:
        self.molecule, self.source_path = molecule, source_path
        if charge is not None: self.charge_var.set(str(charge))
        if multiplicity is not None: self.multiplicity_var.set(str(multiplicity))
        self.rotations.clear(); self._reset_selection(); self._refresh_rotations()
        self._draw_preview(self.molecule.coordinates, "Current Builder geometry")

    def _build(self) -> None:
        root = ttk.Frame(self, padding=10); root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3); root.columnconfigure(1, weight=2); root.rowconfigure(1, weight=1)
        ttk.Label(root, text="Visual Torsion Scan", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text=f"Current molecule: {self.molecule.comment or 'molecule'}  |  {len(self.molecule.symbols)} atoms").grid(row=0, column=1, sticky="e")

        viewer = ttk.LabelFrame(root, text="Click atoms directly", padding=4)
        viewer.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0)); viewer.columnconfigure(0, weight=1); viewer.rowconfigure(0, weight=1)
        self.preview_host = ttk.Frame(viewer); self.preview_host.grid(row=0, column=0, sticky="nsew")
        preview_bar = ttk.Frame(viewer); preview_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0)); preview_bar.columnconfigure(1, weight=1)
        ttk.Label(preview_bar, text="Preview angle").grid(row=0, column=0, padx=(0, 5))
        scale = ttk.Scale(preview_bar, from_=-90, to=90, variable=self.preview_angle_var, command=lambda _v: self._preview_angle())
        scale.grid(row=0, column=1, sticky="ew")
        self.angle_label = ttk.Label(preview_bar, text="0°", width=6); self.angle_label.grid(row=0, column=2, padx=5)
        ttk.Button(preview_bar, text="Reset view", command=lambda: self._draw_preview(self.molecule.coordinates, "Original geometry")).grid(row=0, column=3)

        controls = ttk.Frame(root); controls.grid(row=1, column=1, sticky="nsew", pady=(8, 0)); controls.columnconfigure(0, weight=1)
        select_box = ttk.LabelFrame(controls, text="1. Select bond and rotating unit", padding=8)
        select_box.grid(row=0, column=0, sticky="ew"); select_box.columnconfigure(0, weight=1)
        ttk.Label(select_box, textvariable=self.axis_status_var, font=("Segoe UI", 11, "bold"), wraplength=380).grid(row=0, column=0, sticky="w")
        ttk.Label(select_box, textvariable=self.fragment_status_var, wraplength=380).grid(row=1, column=0, sticky="w", pady=(5, 5))
        select_buttons = ttk.Frame(select_box); select_buttons.grid(row=2, column=0, sticky="ew")
        ttk.Button(select_buttons, text="Start axis selection", command=self._reset_selection).pack(side="left")
        ttk.Button(select_buttons, text="Auto-select side", command=self._auto_select_side).pack(side="left", padx=5)
        ttk.Button(select_buttons, text="Add this rotation", command=self._add_visual_rotation).pack(side="right")

        rotations_box = ttk.LabelFrame(controls, text="Selected rotations", padding=6)
        rotations_box.grid(row=1, column=0, sticky="ew", pady=(8, 0)); rotations_box.columnconfigure(0, weight=1)
        self.rotation_tree = ttk.Treeview(rotations_box, columns=("axis", "atoms"), show="tree headings", height=4)
        self.rotation_tree.heading("#0", text="Unit"); self.rotation_tree.column("#0", width=90)
        self.rotation_tree.heading("axis", text="Axis"); self.rotation_tree.column("axis", width=80)
        self.rotation_tree.heading("atoms", text="Rotating atoms"); self.rotation_tree.column("atoms", width=190)
        self.rotation_tree.grid(row=0, column=0, sticky="ew")
        ttk.Button(rotations_box, text="Remove selected", command=self._remove_rotation).grid(row=1, column=0, sticky="e", pady=(4, 0))

        scan_box = ttk.LabelFrame(controls, text="2. Choose scan", padding=8)
        scan_box.grid(row=2, column=0, sticky="ew", pady=(8, 0)); scan_box.columnconfigure(1, weight=1)
        ttk.Label(scan_box, text="Pattern").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Combobox(scan_box, textvariable=self.mode_var, state="readonly", values=("single", "independent", "collective", "alternating", "combinations", "random")).grid(row=0, column=1, sticky="ew")
        ttk.Label(scan_box, text="Angles").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 0))
        preset = ttk.Combobox(scan_box, textvariable=self.preset_var, state="readonly", values=tuple(ANGLE_PRESETS) + ("Custom",))
        preset.grid(row=1, column=1, sticky="ew", pady=(5, 0)); preset.bind("<<ComboboxSelected>>", lambda _e: self._preset_changed())

        output_box = ttk.LabelFrame(controls, text="3. Generate", padding=8)
        output_box.grid(row=3, column=0, sticky="ew", pady=(8, 0)); output_box.columnconfigure(0, weight=1)
        output_line = ttk.Frame(output_box); output_line.grid(row=0, column=0, sticky="ew"); output_line.columnconfigure(0, weight=1)
        ttk.Entry(output_line, textvariable=self.output_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_line, text="Choose folder", command=self._browse_output).grid(row=0, column=1, padx=(5, 0))
        ttk.Checkbutton(output_box, text="Also write ORCA input files", variable=self.write_orca_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        action_line = ttk.Frame(output_box); action_line.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(action_line, text="Advanced…", command=self._open_advanced).pack(side="left")
        ttk.Button(action_line, text="Generate structures", command=self._generate).pack(side="right")

        ttk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _draw_preview(self, coordinates: np.ndarray, title: str) -> None:
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
            if self.preview_canvas is not None: self.preview_canvas.get_tk_widget().destroy()
            figure = Figure(figsize=(7, 6), dpi=100); axis = figure.add_subplot(111, projection="3d")
            colors = {"H": "#dddddd", "C": "#444444", "N": "#3050f8", "O": "#ff0d0d", "S": "#e0c800", "F": "#90e050", "Cl": "#1fcf1f", "Br": "#a62929", "I": "#940094"}
            for index, (symbol, xyz) in enumerate(zip(self.molecule.symbols, coordinates)):
                color, size = colors.get(symbol, "#cc77cc"), 55
                if index in self.fragment_selection: color, size = "#18a558", 85
                if self.axis_selection and index == self.axis_selection[0]: color, size = "#e53935", 105
                if len(self.axis_selection) > 1 and index == self.axis_selection[1]: color, size = "#ff9800", 105
                axis.scatter(*xyz, s=size, color=color, edgecolors="black", linewidths=.5, depthshade=False)
                axis.text(*xyz, str(index + 1), fontsize=8)
            for left, right in infer_bonds(Molecule(self.molecule.symbols, coordinates, title)):
                points = coordinates[[left, right]]; axis.plot(points[:, 0], points[:, 1], points[:, 2], color="#777777", linewidth=1)
            axis.set_title(title); axis.set_xlabel("X"); axis.set_ylabel("Y"); axis.set_zlabel("Z")
            figure.tight_layout(); self.preview_figure, self.preview_axis = figure, axis
            self.preview_canvas = FigureCanvasTkAgg(figure, master=self.preview_host)
            self.preview_canvas.draw(); self.preview_canvas.get_tk_widget().pack(fill="both", expand=True)
            self.preview_canvas.mpl_connect("button_press_event", self._on_model_press)
            self.preview_canvas.mpl_connect("button_release_event", self._on_model_release)
            self.preview_canvas.mpl_connect("draw_event", lambda _event: self._update_projected_atoms(coordinates))
            self._update_projected_atoms(coordinates)
        except Exception as exc:
            self.status_var.set(f"Preview unavailable: {exc}")

    def _update_projected_atoms(self, coordinates: np.ndarray) -> None:
        if self.preview_axis is None: return
        from mpl_toolkits.mplot3d import proj3d
        self.projected_atoms = {}
        for index, xyz in enumerate(coordinates):
            x2, y2, _ = proj3d.proj_transform(*xyz, self.preview_axis.get_proj())
            self.projected_atoms[index] = tuple(self.preview_axis.transData.transform((x2, y2)))

    def _on_model_press(self, event) -> None:
        self.model_press = (event.x, event.y) if event.button == 1 and event.x is not None and event.y is not None else None

    def _on_model_release(self, event) -> None:
        if self.model_press is None or event.button != 1 or event.x is None or event.y is None:
            self.model_press = None; return
        start = self.model_press; self.model_press = None
        # A drag rotates the camera; only a short click selects an atom.
        if np.hypot(event.x - start[0], event.y - start[1]) > 4:
            return
        self._on_model_click(event)

    def _on_model_click(self, event) -> None:
        if event.x is None or event.y is None or event.inaxes is not self.preview_axis or not self.projected_atoms: return
        atom, distance = min(((index, float(np.hypot(px - event.x, py - event.y))) for index, (px, py) in self.projected_atoms.items()), key=lambda item: item[1])
        if distance > 22: return
        if self.selection_phase == "axis":
            if not self.axis_selection:
                self.axis_selection = [atom]; self.axis_status_var.set(f"First axis atom: {atom + 1}. Now click the second axis atom.")
            elif atom == self.axis_selection[0]:
                return
            else:
                self.axis_selection.append(atom); self.selection_phase = "fragment"
                self.axis_status_var.set(f"Axis: {self.axis_selection[0] + 1} → {atom + 1}")
                self._auto_select_side(show_error=False)
        else:
            if atom == self.axis_selection[0]: return
            if atom in self.fragment_selection: self.fragment_selection.remove(atom)
            else: self.fragment_selection.add(atom)
            self._update_fragment_status()
        self._draw_preview(self.molecule.coordinates, "Red → orange axis; green atoms rotate")

    def _reset_selection(self) -> None:
        self.axis_selection, self.fragment_selection, self.selection_phase = [], set(), "axis"
        self.axis_status_var.set("Click the first axis atom in the model."); self.fragment_status_var.set("Rotating fragment: not selected")
        self._draw_preview(self.molecule.coordinates, "Click the first axis atom")

    def _auto_select_side(self, show_error: bool = True) -> bool:
        if len(self.axis_selection) != 2:
            if show_error: messagebox.showwarning("Select axis", "Click two bonded axis atoms first.", parent=self)
            return False
        side = rotating_side_for_axis(self.molecule, *self.axis_selection)
        if side is None:
            self.fragment_selection = {self.axis_selection[1]}
            self.fragment_status_var.set("Cyclic/ambiguous bond: click green fragment atoms individually to toggle them.")
            return False
        self.fragment_selection = set(side); self._update_fragment_status(); self._draw_preview(self.molecule.coordinates, "Automatically selected rotating side")
        return True

    def _update_fragment_status(self) -> None:
        movable = self.fragment_selection - set(self.axis_selection)
        self.fragment_status_var.set(f"Rotating fragment: {len(movable)} movable atom(s). Click atoms to add/remove.")

    def _angles(self) -> list[float]:
        return parse_angles_text(self.custom_angles_var.get()) if self.preset_var.get() == "Custom" else list(ANGLE_PRESETS[self.preset_var.get()])

    def _add_visual_rotation(self) -> None:
        try:
            if len(self.axis_selection) != 2: raise ConfigurationError("Select two axis atoms first.")
            fragment = sorted(self.fragment_selection | {self.axis_selection[1]})
            if not (set(fragment) - set(self.axis_selection)): raise ConfigurationError("Select at least one movable fragment atom.")
            entry = {"name": f"unit_{len(self.rotations) + 1}", "axis_atoms": [value + 1 for value in self.axis_selection], "rotating_atoms": [value + 1 for value in fragment], "angles_deg": self._angles()}
            trial = self.rotations + [entry]
            test_mode = self.mode_var.get() if len(trial) == 1 or self.mode_var.get() != "single" else "independent"
            parse_config_data({"mode": test_mode, "rotations": trial}, self.molecule)
            self.rotations.append(entry); self._refresh_rotations(); self._reset_selection()
            self.status_var.set(f"Added {entry['name']}. Select another unit or generate.")
        except Exception as exc: messagebox.showerror("Add rotation", str(exc), parent=self)

    def _refresh_rotations(self) -> None:
        self.rotation_tree.delete(*self.rotation_tree.get_children())
        for item in self.rotations:
            movable = [atom for atom in item["rotating_atoms"] if atom not in item["axis_atoms"]]
            self.rotation_tree.insert("", "end", iid=item["name"], text=item["name"], values=("→".join(map(str, item["axis_atoms"])), f"{len(movable)} atoms"))

    def _remove_rotation(self) -> None:
        selected = set(self.rotation_tree.selection()); self.rotations = [item for item in self.rotations if item["name"] not in selected]; self._refresh_rotations()

    def _preset_changed(self) -> None:
        if self.preset_var.get() == "Custom": self._open_advanced()

    def _preview_angle(self) -> None:
        angle = float(self.preview_angle_var.get()); self.angle_label.configure(text=f"{angle:.0f}°")
        if not self.rotations: return
        try:
            coordinates = np.array(self.molecule.coordinates, copy=True)
            mode = self.mode_var.get()
            selected = self.rotations if mode in {"collective", "alternating"} else self.rotations[:1]
            raw = {"mode": "independent" if len(selected) > 1 else "single", "rotations": selected}
            _raw, definitions, _settings = parse_config_data(raw, self.molecule)
            for index, rotation in enumerate(definitions):
                applied = -angle if mode == "alternating" and index % 2 else angle
                coordinates = rotate_coordinates(coordinates, rotation, applied)
            self._draw_preview(coordinates, f"Preview at {angle:.0f}°")
        except Exception as exc: self.status_var.set(f"Preview warning: {exc}")

    def _config(self) -> dict[str, Any]:
        if not self.rotations: raise ConfigurationError("Add at least one visual rotation.")
        rotations = [dict(item, angles_deg=self._angles()) for item in self.rotations]
        mode = self.mode_var.get()
        if mode == "single" and len(rotations) != 1: raise ConfigurationError("Single mode needs exactly one selected rotation. Choose Independent, Collective, or Alternating for several units.")
        raw: dict[str, Any] = {"mode": mode, "rotations": rotations, "charge": int(self.charge_var.get()), "multiplicity": int(self.multiplicity_var.get()), "max_structures": int(self.max_structures_var.get()), "validation": {"collision_threshold_angstrom": float(self.collision_var.get()), "strict": self.strict_var.get()}}
        if self.max_displacement_var.get().strip(): raw["validation"]["maximum_displacement_angstrom"] = float(self.max_displacement_var.get())
        if mode in {"collective", "alternating"}: raw["angles_deg"] = self._angles()
        if mode == "random":
            raw["random_count"], raw["random_seed"] = int(self.random_count_var.get()), int(self.random_seed_var.get())
            for item in raw["rotations"]: item["angle_range_deg"] = [min(self._angles()), max(self._angles())]; item.pop("angles_deg", None)
        return raw

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Choose generated-structure directory", mustexist=False)
        if path: self.output_var.set(path)

    def _open_advanced(self) -> None:
        win = tk.Toplevel(self); win.title("Advanced torsion settings"); win.transient(self.winfo_toplevel()); win.resizable(False, False)
        box = ttk.Frame(win, padding=12); box.pack(fill="both", expand=True)
        fields = (("Custom angles", self.custom_angles_var), ("Maximum structures", self.max_structures_var), ("Collision threshold / A", self.collision_var), ("Maximum displacement / A", self.max_displacement_var), ("Random count", self.random_count_var), ("Random seed", self.random_seed_var), ("Charge", self.charge_var), ("Multiplicity", self.multiplicity_var), ("ORCA template", self.template_var))
        for row, (label, variable) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", pady=3); ttk.Entry(box, textvariable=variable, width=38).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(box, text="Strict validation", variable=self.strict_var).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=4)
        actions = ttk.Frame(box); actions.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Load JSON…", command=lambda: self._load_json(win)).pack(side="left")
        ttk.Button(actions, text="Save JSON…", command=self._save_json).pack(side="left", padx=5)
        ttk.Button(actions, text="Choose template…", command=self._browse_template).pack(side="left")
        ttk.Button(actions, text="Done", command=win.destroy).pack(side="right")

    def _browse_template(self) -> None:
        path = filedialog.askopenfilename(parent=self, filetypes=[("ORCA template", "*.inp *.txt"), ("All files", "*.*")])
        if path: self.template_var.set(path)

    def _load_json(self, owner=None) -> None:
        path = filedialog.askopenfilename(parent=owner or self, filetypes=[("JSON", "*.json")])
        if not path: return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8")); parse_config_data(raw, self.molecule)
            self.rotations = list(raw["rotations"]); self.mode_var.set(raw["mode"]); self.custom_angles_var.set(",".join(map(str, raw.get("angles_deg", raw["rotations"][0].get("angles_deg", []))))); self.preset_var.set("Custom")
            self.charge_var.set(str(raw.get("charge", 0))); self.multiplicity_var.set(str(raw.get("multiplicity", 1))); self.max_structures_var.set(str(raw.get("max_structures", 1000)))
            validation = raw.get("validation", {}); self.collision_var.set(str(validation.get("collision_threshold_angstrom", .8))); self.max_displacement_var.set(str(validation.get("maximum_displacement_angstrom", ""))); self.strict_var.set(bool(validation.get("strict", False)))
            self._refresh_rotations(); self.status_var.set(f"Loaded {path}")
        except Exception as exc: messagebox.showerror("Load configuration", str(exc), parent=owner or self)

    def _save_json(self) -> None:
        try: raw = self._config(); parse_config_data(raw, self.molecule)
        except Exception as exc: messagebox.showerror("Save configuration", str(exc), parent=self); return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="torsion_scan.json")
        if path: Path(path).write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def _generate(self) -> None:
        try:
            raw, rotations, settings = parse_config_data(self._config(), self.molecule); plans = scan_plan(raw, rotations)
            output = Path(self.output_var.get()).expanduser().resolve()
            if output.exists() and any(output.iterdir()) and not messagebox.askyesno("Existing output", f"Replace matching generated files in:\n{output}\n\nOther files will be preserved.", parent=self): return
            template = Path(self.template_var.get()).read_text(encoding="utf-8") if self.template_var.get().strip() else DEFAULT_ORCA_TEMPLATE
            results = generate(self.molecule, raw, rotations, settings, output, write_orca_files=self.write_orca_var.get(), template=template)
            write_summary(output / "torsion_scan_summary.csv", results)
            metadata = {"generator": "torsion_generator_gui", "source": self.source_path, "structures": len(results), "config": raw}
            (output / "torsion_scan_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            self.status_var.set(f"Generated {len(results)} structure(s) in {output}")
            messagebox.showinfo("Finished", f"Generated {len(plans)} structure(s).\n\n{output}", parent=self)
        except Exception as exc: messagebox.showerror("Torsion generation", str(exc), parent=self)


def open_torsion_generator_window(parent, atoms: Sequence[Sequence[Any]], title: str = "molecule", source_path: str = "", charge: int = 0, multiplicity: int = 1, existing=None, embed_parent=None):
    molecule = molecule_from_atoms(atoms, title)
    if existing is not None and existing.winfo_exists():
        existing.set_molecule(molecule, source_path, charge, multiplicity)
        if existing.host_window is not None:
            existing.host_window.deiconify(); existing.host_window.lift(); existing.host_window.focus_force()
        return existing
    host = None
    panel_parent = embed_parent
    if panel_parent is None:
        host = tk.Toplevel(parent)
        host.title("Torsion geometry generator")
        host.geometry("1080x720")
        host.minsize(860, 620)
        panel_parent = host
    panel = TorsionGeneratorPanel(panel_parent, molecule, source_path, charge, multiplicity, host_window=host)
    if host is not None:
        host.protocol("WM_DELETE_WINDOW", host.withdraw)
    return panel


TorsionGeneratorWindow = TorsionGeneratorPanel


def main() -> None:
    root = tk.Tk(); root.withdraw()
    path = filedialog.askopenfilename(title="Choose XYZ geometry", filetypes=[("XYZ", "*.xyz")])
    if not path: root.destroy(); return
    host = tk.Toplevel(root); host.title("Torsion geometry generator"); host.geometry("1080x720")
    TorsionGeneratorPanel(host, read_xyz(Path(path)), path, host_window=host); host.protocol("WM_DELETE_WINDOW", root.destroy); root.mainloop()


if __name__ == "__main__":
    main()
