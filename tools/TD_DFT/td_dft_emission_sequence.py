"""Fluorescence emission calculation sequence helpers for TD-DFT.

The module is deliberately service-oriented: it prepares, validates, advances,
and parses the dependent ORCA inputs without importing the ORCA Input Builder.
Builder/UI code can call these functions and use the existing ORCA runner for
each generated input.
"""
from __future__ import annotations

import csv
import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

try:
    from .td_dft_module import (
        HC_EV_NM,
        build_gaussian_broadened_spectrum,
        build_tddft_block,
        normalize_spectrum,
        parse_orca_tddft_output,
    )
except ImportError:  # direct execution from tools/TD_DFT
    from td_dft_module import (  # type: ignore
        HC_EV_NM,
        build_gaussian_broadened_spectrum,
        build_tddft_block,
        normalize_spectrum,
        parse_orca_tddft_output,
    )


SCHEMA_VERSION = 1
STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_OPTIONAL_FAILED = "optional_failed"
STATUS_STOPPED = "stopped"


@dataclass
class EmissionSequenceSettings:
    source_output: str
    source_input: Optional[str] = None
    target_root: int = 1
    target_manifold: str = "Singlet"
    follow_root: bool = True
    nroots: int = 10
    run_frequencies: bool = False
    broadening_ev: float = 0.20
    wavelength_min_nm: float = 200.0
    wavelength_max_nm: float = 800.0
    normalize: bool = False
    run_automatically: bool = False


@dataclass
class EmissionSequenceStep:
    step_id: str
    label: str
    required: bool
    depends_on: List[str] = field(default_factory=list)
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    status: str = STATUS_PENDING
    message: str = ""


@dataclass
class EmissionSequenceManifest:
    schema_version: int
    sequence_id: str
    source_absorption_output: str
    source_absorption_input: Optional[str]
    settings: Dict
    steps: List[EmissionSequenceStep]
    requested_root: int
    final_followed_root: Optional[int]
    created_at: str
    updated_at: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class EmissionResult:
    requested_root: int
    final_followed_root: int
    manifold: str
    emission_energy_ev: float
    emission_wavelength_nm: float
    oscillator_strength: float
    absorption_energy_ev: Optional[float] = None
    absorption_wavelength_nm: Optional[float] = None
    stokes_shift_ev: Optional[float] = None
    stokes_shift_nm: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _safe_stem(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._")
    return value or "emission"


PathLike = Union[str, Path]


def _read_text(path: PathLike) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def validate_absorption_source(out_path: str, target_root: int = 1) -> List[Dict]:
    path = Path(out_path)
    if not path.is_file():
        raise FileNotFoundError(f"Absorption output was not found: {path}")
    text = _read_text(path)
    if "ORCA TERMINATED NORMALLY" not in text.upper():
        raise ValueError("Absorption output did not terminate normally.")
    states = parse_orca_tddft_output(str(path))
    if target_root < 1:
        raise ValueError("Target root must be positive.")
    if not any(int(state.get("state_index", -1)) == target_root for state in states):
        raise ValueError(f"Selected root S{target_root} was not found in the absorption output.")
    return states


def matching_input_for_output(out_path: str) -> Optional[str]:
    output = Path(out_path)
    candidates = [
        output.with_suffix(".inp"),
        output.with_suffix(".in"),
        output.with_name(output.stem.replace("_TD-DFT", "").replace("_td-dft", "") + ".inp"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    same_dir = sorted(output.parent.glob("*.inp"), key=lambda p: (p.stem != output.stem, p.stat().st_mtime))
    return str(same_dir[-1].resolve()) if same_dir else None


def parse_xyz_from_orca_input(inp_text: str) -> Tuple[int, int, List[Tuple[str, float, float, float]]]:
    match = re.search(r"(?ims)^\s*\*\s*xyz\s+([+-]?\d+)\s+(\d+)\s*\n(.*?)^\s*\*", inp_text)
    if not match:
        raise ValueError("No '* xyz charge multiplicity' coordinate block was found in the ORCA input.")
    charge, multiplicity = int(match.group(1)), int(match.group(2))
    atoms: List[Tuple[str, float, float, float]] = []
    for line in match.group(3).splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
        except ValueError:
            continue
    if not atoms:
        raise ValueError("The ORCA input coordinate block contains no Cartesian atoms.")
    return charge, multiplicity, atoms


def xyz_block(atoms: Iterable[Tuple[str, float, float, float]]) -> str:
    return "\n".join(f"{sym:<2} {x: .8f} {y: .8f} {z: .8f}" for sym, x, y, z in atoms)


def write_xyz(path: PathLike, atoms: Sequence[Tuple[str, float, float, float]], title: str) -> None:
    Path(path).write_text(
        f"{len(atoms)}\n{title}\n{xyz_block(atoms)}\n",
        encoding="utf-8",
    )


def _replace_xyz_block(inp_text: str, charge: int, multiplicity: int, atoms: Sequence[Tuple[str, float, float, float]]) -> str:
    replacement = f"* xyz {charge} {multiplicity}\n{xyz_block(atoms)}\n*"
    return re.sub(r"(?ims)^\s*\*\s*xyz\s+[+-]?\d+\s+\d+\s*\n.*?^\s*\*", replacement, inp_text, count=1)


def _replace_or_add_tddft_block(inp_text: str, block: str) -> str:
    pattern = re.compile(r"(?ims)^\s*%(?:tddft|cis)\b.*?^\s*end\s*$")
    if pattern.search(inp_text):
        return pattern.sub(block.strip(), inp_text, count=1)
    coord = re.search(r"(?im)^\s*\*\s*xyz\b", inp_text)
    if coord:
        return inp_text[: coord.start()].rstrip() + "\n\n" + block.strip() + "\n\n" + inp_text[coord.start():]
    return inp_text.rstrip() + "\n\n" + block.strip() + "\n"


def _rewrite_simple_keywords(line: str, add: Sequence[str], remove: Sequence[str]) -> str:
    if not line.lstrip().startswith("!"):
        return line
    tokens = line.strip().split()
    kept = [tokens[0]]
    remove_norm = {item.lower() for item in remove}
    add_norm = {item.lower() for item in add}
    seen = set()
    for token in tokens[1:]:
        norm = token.lower()
        if norm in remove_norm:
            continue
        if norm in seen:
            continue
        kept.append(token)
        seen.add(norm)
    for token in add:
        if token.lower() not in seen and token.lower() not in remove_norm:
            kept.append(token)
            seen.add(token.lower())
    return " ".join(kept)


def build_emission_tddft_settings(settings: EmissionSequenceSettings, optimization: bool) -> Dict:
    manifold = "Triplets" if settings.target_manifold == "Triplet" else "Singlets"
    data = {
        "vertical_excitation": not optimization,
        "excited_state_optimization": optimization,
        "excited_state_frequencies": False,
        "td_method": "TDDFT",
        "nroots": int(settings.nroots),
        "root": int(settings.target_root),
        "manifold": manifold,
        "target_manifold": settings.target_manifold,
    }
    return data


def add_follow_iroot(block: str, follow: bool = True) -> str:
    if not follow:
        return block
    lines = block.splitlines()
    if any(re.match(r"^\s*FollowIRoot\b", line, re.I) for line in lines):
        return block
    for idx, line in enumerate(lines):
        if line.strip().lower() == "end":
            lines.insert(idx, "  FollowIRoot true")
            break
    return "\n".join(lines)


def build_excited_state_optimization_input(source_input_text: str, settings: EmissionSequenceSettings) -> str:
    block = build_tddft_block(build_emission_tddft_settings(settings, optimization=True))
    block = add_follow_iroot(block, settings.follow_root)
    lines = source_input_text.splitlines()
    rewritten = [
        _rewrite_simple_keywords(line, add=["Opt"], remove=["SP", "Freq"])
        for line in lines
    ]
    text = "\n".join(rewritten)
    return _replace_or_add_tddft_block(text, block).rstrip() + "\n"


def build_vertical_emission_input(
    source_input_text: str,
    atoms: Sequence[Tuple[str, float, float, float]],
    settings: EmissionSequenceSettings,
) -> str:
    charge, multiplicity, _source_atoms = parse_xyz_from_orca_input(source_input_text)
    block = build_tddft_block(build_emission_tddft_settings(settings, optimization=False))
    lines = source_input_text.splitlines()
    rewritten = [
        _rewrite_simple_keywords(line, add=["SP"], remove=["Opt", "Freq"])
        for line in lines
    ]
    text = "\n".join(rewritten)
    text = _replace_or_add_tddft_block(text, block)
    text = _replace_xyz_block(text, charge, multiplicity, atoms)
    return text.rstrip() + "\n"


def extract_final_optimized_geometry(out_path: str) -> List[Tuple[str, float, float, float]]:
    text = _read_text(out_path)
    upper = text.upper()
    if "ORCA TERMINATED NORMALLY" not in upper:
        raise ValueError("Optimization output did not terminate normally.")
    if "OPTIMIZATION HAS CONVERGED" not in upper and "THE OPTIMIZATION DID CONVERGE" not in upper:
        raise ValueError("Excited-state optimization did not report convergence.")
    return extract_last_orca_cartesian_geometry(text)


def extract_last_orca_cartesian_geometry(text: str) -> List[Tuple[str, float, float, float]]:
    lines = text.splitlines()
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
            if not stripped or set(stripped) <= {"-"}:
                j += 1
                continue
            parts = stripped.split()
            if len(parts) >= 4:
                try:
                    atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
                    j += 1
                    continue
                except ValueError:
                    pass
            if atoms:
                break
            j += 1
        if atoms:
            last_atoms = atoms
        idx = max(j, idx + 1)
    if not last_atoms:
        raise ValueError("No final ORCA Cartesian coordinate block was found.")
    return last_atoms


def parse_root_following_history(out_path: str) -> Dict:
    text = _read_text(out_path)
    changes = []
    for match in re.finditer(r"(?i)(?:current\s+)?IRoot\s*(?:changed|=|is|:)?\s*(?:to)?\s*(\d+)", text):
        changes.append(int(match.group(1)))
    warnings = [line.strip() for line in text.splitlines() if re.search(r"(?i)root.*(?:flip|changed|warning|follow)", line)]
    return {
        "root_changes": changes,
        "final_followed_root": changes[-1] if changes else None,
        "warnings": warnings,
    }


def _state_by_root(states: Sequence[Dict], root: int) -> Dict:
    for state in states:
        if int(state.get("state_index", -1)) == int(root):
            return state
    raise ValueError(f"State/root S{root} was not found in the TD-DFT output.")


def parse_vertical_emission_result(
    vertical_out_path: str,
    settings: EmissionSequenceSettings,
    absorption_out_path: Optional[str] = None,
    final_followed_root: Optional[int] = None,
) -> EmissionResult:
    states = parse_orca_tddft_output(vertical_out_path)
    root = int(final_followed_root or settings.target_root)
    state = _state_by_root(states, root)
    energy = float(state["energy_ev"])
    if energy <= 0:
        raise ValueError("Emission energy must be positive.")
    wavelength = HC_EV_NM / energy
    absorption_energy = None
    absorption_wavelength = None
    stokes_ev = None
    stokes_nm = None
    warnings = [
        "Vertical emission is estimated from the upward TD-DFT excitation at the optimized excited-state geometry.",
        "This is a vertical electronic emission approximation, not a vibronic fluorescence simulation.",
    ]
    if absorption_out_path:
        try:
            absorption_state = _state_by_root(parse_orca_tddft_output(absorption_out_path), settings.target_root)
            absorption_energy = float(absorption_state["energy_ev"])
            absorption_wavelength = float(absorption_state.get("wavelength_nm") or HC_EV_NM / absorption_energy)
            stokes_ev = absorption_energy - energy
            stokes_nm = wavelength - absorption_wavelength
        except Exception as exc:
            warnings.append(f"Stokes shift was not reported because absorption matching failed: {exc}")
    return EmissionResult(
        requested_root=settings.target_root,
        final_followed_root=root,
        manifold=settings.target_manifold,
        emission_energy_ev=energy,
        emission_wavelength_nm=wavelength,
        oscillator_strength=float(state.get("oscillator_strength", 0.0)),
        absorption_energy_ev=absorption_energy,
        absorption_wavelength_nm=absorption_wavelength,
        stokes_shift_ev=stokes_ev,
        stokes_shift_nm=stokes_nm,
        warnings=warnings,
    )


def build_emission_stick_spectrum(result: EmissionResult) -> List[Tuple[float, float]]:
    return [(result.emission_wavelength_nm, result.oscillator_strength)]


def build_emission_broadened_spectrum(result: EmissionResult, settings: EmissionSequenceSettings, points: int = 2000):
    state = [{"energy_ev": result.emission_energy_ev, "oscillator_strength": result.oscillator_strength}]
    curve = build_gaussian_broadened_spectrum(
        state,
        broadening_ev=settings.broadening_ev,
        x_min_nm=settings.wavelength_min_nm,
        x_max_nm=settings.wavelength_max_nm,
        x_axis="nm",
        points=points,
    )
    return normalize_spectrum(curve) if settings.normalize else curve


def write_emission_outputs(sequence_dir: PathLike, result: EmissionResult, settings: EmissionSequenceSettings) -> Dict[str, str]:
    root = Path(sequence_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "state_csv": root / "emission_state.csv",
        "spectrum_csv": root / "emission_spectrum.csv",
        "result_json": root / "emission_result.json",
        "summary_txt": root / "emission_summary.txt",
    }
    with paths["state_csv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["root", "manifold", "energy_ev", "wavelength_nm", "oscillator_strength"])
        writer.writerow([
            result.final_followed_root,
            result.manifold,
            f"{result.emission_energy_ev:.8f}",
            f"{result.emission_wavelength_nm:.4f}",
            f"{result.oscillator_strength:.8g}",
        ])
    broadened = build_emission_broadened_spectrum(result, settings)
    with paths["spectrum_csv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["wavelength_nm", "relative_intensity"])
        writer.writerows(broadened)
    paths["result_json"].write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    paths["summary_txt"].write_text(build_emission_summary(result, settings), encoding="utf-8")
    try:
        import matplotlib.pyplot as plt

        for suffix in ("png", "svg"):
            fig, ax = plt.subplots(figsize=(8, 5))
            xs = [x for x, _ in broadened]
            ys = [y for _, y in broadened]
            ax.plot(xs, ys, color="#991b1b", linewidth=2)
            ax.vlines([result.emission_wavelength_nm], 0, [max(ys, default=result.oscillator_strength)], color="#6b7280", linewidth=1)
            ax.set_xlabel("Wavelength / nm")
            ax.set_ylabel("Relative intensity")
            ax.set_title("Simulated vertical fluorescence band")
            fig.tight_layout()
            plot_path = root / f"emission_spectrum.{suffix}"
            fig.savefig(plot_path, dpi=220)
            plt.close(fig)
            paths[f"spectrum_{suffix}"] = plot_path
    except Exception:
        pass
    return {key: str(path) for key, path in paths.items()}


def build_emission_summary(result: EmissionResult, settings: EmissionSequenceSettings) -> str:
    lines = [
        "Fluorescence emission calculation",
        "",
        f"Source absorption output: {settings.source_output}",
        f"Requested emitting state: {settings.target_manifold} root {settings.target_root}",
        f"Final followed root: {result.final_followed_root}",
        f"Vertical emission energy: {result.emission_energy_ev:.6f} eV",
        f"Vertical emission wavelength: {result.emission_wavelength_nm:.2f} nm",
        f"Oscillator strength proxy: {result.oscillator_strength:.6g}",
    ]
    if result.absorption_energy_ev is not None:
        lines.extend([
            f"Matched absorption energy: {result.absorption_energy_ev:.6f} eV",
            f"Matched absorption wavelength: {result.absorption_wavelength_nm:.2f} nm",
            f"Stokes shift: {result.stokes_shift_ev:.6f} eV; {result.stokes_shift_nm:.2f} nm",
        ])
    lines.extend([
        "",
        "This is a vertical electronic emission approximation, not a vibronic fluorescence simulation.",
        "Root following does not prove electronic-state identity; inspect ORCA warnings and dominant transitions.",
    ])
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    return "\n".join(lines) + "\n"


def manifest_path(sequence_dir: PathLike) -> Path:
    return Path(sequence_dir) / "emission_sequence.json"


def save_manifest(manifest: EmissionSequenceManifest, sequence_dir: PathLike) -> Path:
    path = manifest_path(sequence_dir)
    path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    return path


def load_manifest(sequence_dir: PathLike) -> EmissionSequenceManifest:
    payload = json.loads(manifest_path(sequence_dir).read_text(encoding="utf-8"))
    payload["steps"] = [EmissionSequenceStep(**step) for step in payload.get("steps", [])]
    return EmissionSequenceManifest(**payload)


def prepare_emission_sequence(settings: EmissionSequenceSettings, sequence_dir: Optional[PathLike] = None) -> EmissionSequenceManifest:
    states = validate_absorption_source(settings.source_output, settings.target_root)
    source_input = settings.source_input or matching_input_for_output(settings.source_output)
    if not source_input:
        raise FileNotFoundError("Could not find the matching absorption ORCA input file.")
    settings.source_input = source_input
    if settings.target_root > settings.nroots:
        settings.nroots = settings.target_root
    source_text = _read_text(source_input)
    parse_xyz_from_orca_input(source_text)
    source_output = Path(settings.source_output).resolve()
    root = Path(sequence_dir) if sequence_dir else source_output.parent / f"{source_output.stem}_fluorescence_S{settings.target_root}"
    root.mkdir(parents=True, exist_ok=True)
    opt_inp = root / f"01_esopt_S{settings.target_root}.inp"
    opt_inp.write_text(build_excited_state_optimization_input(source_text, settings), encoding="utf-8")
    steps = [
        EmissionSequenceStep(
            step_id="01_esopt",
            label=f"Excited-state optimization S{settings.target_root}",
            required=True,
            input_path=str(opt_inp),
            output_path=str(opt_inp.with_suffix(".out")),
            status=STATUS_READY,
        ),
        EmissionSequenceStep(
            step_id="02_vertical_emission",
            label=f"Vertical emission S{settings.target_root}",
            required=True,
            depends_on=["01_esopt"],
            status=STATUS_BLOCKED,
            message="Waiting for validated excited-state optimized geometry.",
        ),
    ]
    if settings.run_frequencies:
        steps.append(
            EmissionSequenceStep(
                step_id="03_esfreq",
                label=f"Excited-state frequencies S{settings.target_root}",
                required=False,
                depends_on=["01_esopt"],
                status=STATUS_BLOCKED,
                message="Frequency input is generated after excited-state optimization.",
            )
        )
    manifest = EmissionSequenceManifest(
        schema_version=SCHEMA_VERSION,
        sequence_id=f"{_safe_stem(source_output.stem)}_S{settings.target_root}_{int(time.time())}",
        source_absorption_output=str(source_output),
        source_absorption_input=str(Path(source_input).resolve()),
        settings=asdict(settings),
        steps=steps,
        requested_root=settings.target_root,
        final_followed_root=None,
        created_at=_now(),
        updated_at=_now(),
        warnings=[] if settings.target_root < len(states) else ["Selected root is the highest computed root; root following may be less reliable."],
    )
    save_manifest(manifest, root)
    return manifest


def advance_after_optimization(sequence_dir: PathLike, optimization_output: Optional[str] = None) -> EmissionSequenceManifest:
    manifest = load_manifest(sequence_dir)
    settings = EmissionSequenceSettings(**manifest.settings)
    opt_step = next(step for step in manifest.steps if step.step_id == "01_esopt")
    opt_out = optimization_output or opt_step.output_path
    if not opt_out:
        raise ValueError("Optimization output path is missing.")
    atoms = extract_final_optimized_geometry(opt_out)
    history = parse_root_following_history(opt_out)
    manifest.final_followed_root = history.get("final_followed_root") or manifest.requested_root
    manifest.warnings.extend(history.get("warnings", []))
    final_xyz = Path(sequence_dir) / f"01_esopt_S{manifest.requested_root}_final.xyz"
    write_xyz(final_xyz, atoms, f"Final S{manifest.requested_root} excited-state geometry")
    source_text = _read_text(manifest.source_absorption_input or settings.source_input or "")
    vert_inp = Path(sequence_dir) / f"02_vertical_emission_S{manifest.requested_root}.inp"
    vert_inp.write_text(build_vertical_emission_input(source_text, atoms, settings), encoding="utf-8")
    opt_step.status = STATUS_COMPLETED
    opt_step.message = f"Final geometry written: {final_xyz.name}"
    for step in manifest.steps:
        if step.step_id == "02_vertical_emission":
            step.input_path = str(vert_inp)
            step.output_path = str(vert_inp.with_suffix(".out"))
            step.status = STATUS_READY
            step.message = "Ready after validated excited-state optimization."
    manifest.updated_at = _now()
    save_manifest(manifest, sequence_dir)
    return manifest


def finalize_after_vertical(sequence_dir: PathLike, vertical_output: Optional[str] = None) -> Tuple[EmissionSequenceManifest, EmissionResult]:
    manifest = load_manifest(sequence_dir)
    settings = EmissionSequenceSettings(**manifest.settings)
    vertical_step = next(step for step in manifest.steps if step.step_id == "02_vertical_emission")
    out_path = vertical_output or vertical_step.output_path
    if not out_path:
        raise ValueError("Vertical emission output path is missing.")
    text = _read_text(out_path)
    if "ORCA TERMINATED NORMALLY" not in text.upper():
        raise ValueError("Vertical emission output did not terminate normally.")
    result = parse_vertical_emission_result(
        out_path,
        settings,
        absorption_out_path=manifest.source_absorption_output,
        final_followed_root=manifest.final_followed_root,
    )
    write_emission_outputs(sequence_dir, result, settings)
    vertical_step.status = STATUS_COMPLETED
    vertical_step.message = f"Emission wavelength {result.emission_wavelength_nm:.2f} nm"
    manifest.updated_at = _now()
    save_manifest(manifest, sequence_dir)
    return manifest, result


def mark_step_failed(sequence_dir: PathLike, step_id: str, message: str) -> EmissionSequenceManifest:
    manifest = load_manifest(sequence_dir)
    for step in manifest.steps:
        if step.step_id == step_id:
            step.status = STATUS_FAILED
            step.message = message
            break
    manifest.updated_at = _now()
    save_manifest(manifest, sequence_dir)
    return manifest
