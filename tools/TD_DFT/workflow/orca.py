from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..td_dft_emission_sequence import extract_last_orca_cartesian_geometry, write_xyz
from ..td_dft_module import parse_orca_tddft_output
from .models import method_signature


def read_xyz(path: Path) -> List[Tuple[str, float, float, float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"Empty XYZ file: {path}")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ValueError(f"Invalid XYZ atom count: {path}") from exc
    atoms = []
    for line in lines[2:2 + count]:
        parts = line.split()
        if len(parts) < 4:
            raise ValueError(f"Invalid XYZ coordinate line in {path}: {line}")
        atoms.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3])))
    if len(atoms) != count:
        raise ValueError(f"XYZ declared {count} atoms but contains {len(atoms)}: {path}")
    return atoms


def _simple_keywords(config, job: str) -> List[str]:
    method = config.method
    words = [method.functional, method.basis]
    if method.auxiliary_basis:
        words.append(method.auxiliary_basis)
    if method.rijcosx:
        words.append("RIJCOSX")
    if method.dispersion:
        words.append(method.dispersion)
    words.extend([method.scf_convergence, method.grid])
    if method.relativistic:
        words.append(method.relativistic)
    if method.ecp:
        words.append(method.ecp)
    words.extend(method.extra_keywords)
    if config.solvent.enabled and not config.solvent.smd and config.solvent.model.upper() == "CPCM":
        words.append(f"CPCM({config.solvent.name})")
    if job in {"s0_opt", "es_opt"}:
        words.extend(["Opt", method.geometry_convergence])
    elif job == "s0_freq":
        words.append("Freq")
    else:
        words.append("SP")
    return words


def _blocks(config, job: str, moinp: Optional[str], atoms: Optional[Sequence[Tuple[str, float, float, float]]] = None) -> str:
    lines = [
        "%pal", f"  nprocs {config.resources.nprocs}", "end", "",
        f"%maxcore {config.resources.maxcore_mb}",
    ]
    if moinp:
        lines.extend(["", f'%moinp "{moinp}"'])
    if config.solvent.enabled:
        model = config.solvent.model.upper()
        if model == "CPCM" and config.solvent.smd:
            lines.extend(["", "%cpcm", "  smd true", f'  SMDsolvent "{config.solvent.name}"', "end"])
        elif model == "SMD":
            lines.extend(["", "%cpcm", "  smd true", f'  SMDsolvent "{config.solvent.name}"', "end"])
    if job in {"absorption", "es_opt", "emission"}:
        es = config.excited_states
        lines.extend([
            "", "%tddft", f"  NRoots {es.nroots}", f"  TDA {'true' if es.use_tda else 'false'}",
            f"  MaxDim {es.maxdim}", f"  MaxIter {es.maxiter}",
        ])
        if es.request_nto:
            lines.extend(["  DoNTO true", "  NTOThresh 1e-4"])
        if job == "es_opt":
            lines.extend([f"  IRoot {es.target_root}", f"  IRootMult {es.target_multiplicity.lower()}"])
        if es.target_multiplicity.lower() == "triplet":
            lines.append("  Triplets true")
        lines.append("end")
    if job in {"s0_opt", "es_opt"} and (config.geometry.freeze_all or config.geometry.freeze_heavy):
        if not atoms:
            raise ValueError("Geometry constraints require a readable starting XYZ geometry.")
        constraints = []
        for index, (symbol, *_coordinates) in enumerate(atoms, 1):
            if config.geometry.freeze_all or symbol.upper() != "H":
                constraints.append(f"    {{ {symbol} {index} C }}")
        lines.extend(["", "%geom", "  Constraints", *constraints, "  end", "end"])
    return "\n".join(lines)


def generate_input(config, job: str, geometry: str, moinp: Optional[str] = None, geometry_path: Optional[Path] = None) -> str:
    if job not in {"s0_opt", "s0_freq", "absorption", "es_opt", "emission"}:
        raise ValueError(f"Unknown workflow job: {job}")
    keywords = _simple_keywords(config, job)
    if moinp:
        keywords.append("MOREAD")
    signature = method_signature(config, include_excited_state=job in {"absorption", "es_opt", "emission"})
    atoms = read_xyz(geometry_path) if geometry_path and geometry_path.is_file() else None
    return (
        f"# CrystEngKit method-signature: {signature}\n"
        f"! {' '.join(keywords)}\n\n{_blocks(config, job, moinp, atoms)}\n\n"
        f"* xyzfile {config.system.charge} {config.system.multiplicity} {geometry}\n"
    )


def normal_termination(text: str) -> bool:
    return "ORCA TERMINATED NORMALLY" in text.upper()


def geometry_converged(text: str) -> bool:
    upper = text.upper()
    return "OPTIMIZATION HAS CONVERGED" in upper or "THE OPTIMIZATION DID CONVERGE" in upper


def scf_converged(text: str) -> bool:
    upper = text.upper()
    failures = ("SCF NOT CONVERGED", "SCF DID NOT CONVERGE", "SCF CONVERGENCE FAILURE")
    return not any(item in upper for item in failures)


def final_energy(text: str) -> Optional[float]:
    matches = re.findall(r"(?im)^\s*FINAL SINGLE POINT ENERGY\s+(-?\d+(?:\.\d+)?)", text)
    return float(matches[-1]) if matches else None


def orca_version(text: str) -> Optional[str]:
    match = re.search(r"(?im)^\s*(?:Program\s+)?Version\s+([0-9]+(?:\.[0-9]+){1,3})", text)
    return match.group(1) if match else None


def imaginary_frequencies(text: str) -> List[float]:
    values = []
    for match in re.finditer(r"(?im)^\s*\d+\s*:\s*(-?\d+(?:\.\d+)?)\s*cm\*\*-1", text):
        value = float(match.group(1))
        if value < 0:
            values.append(value)
    for match in re.finditer(r"(?i)(-?\d+(?:\.\d+)?)\s*cm(?:\^-?1|\*\*-1).*?imaginary", text):
        value = float(match.group(1))
        if value < 0 and value not in values:
            values.append(value)
    return values


def validate_output(path: Path, job: str, imaginary_threshold: float = -30.0) -> Dict:
    if not path.is_file():
        raise FileNotFoundError(f"Expected ORCA output is missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not normal_termination(text):
        raise ValueError(f"ORCA did not terminate normally: {path}")
    if not scf_converged(text):
        raise ValueError(f"SCF did not converge: {path}")
    result = {"normal_termination": True, "scf_converged": True, "final_energy_eh": final_energy(text), "orca_version": orca_version(text)}
    if job in {"s0_opt", "es_opt"}:
        if not geometry_converged(text):
            raise ValueError(f"Geometry optimization did not converge: {path}")
        result["geometry_converged"] = True
    if job == "s0_freq":
        imag = imaginary_frequencies(text)
        result.update({"imaginary_frequencies_cm1": imag, "large_imaginary_frequencies_cm1": [v for v in imag if v < imaginary_threshold]})
    if job in {"absorption", "emission"}:
        states = parse_orca_tddft_output(str(path))
        result["states"] = states
    return result


def extract_geometry(output: Path, destination: Path, title: str) -> Path:
    atoms = extract_last_orca_cartesian_geometry(output.read_text(encoding="utf-8", errors="replace"))
    write_xyz(destination, atoms, title)
    return destination


def write_states_csv(states: Sequence[Dict], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["State", "Energy_eV", "Wavelength_nm", "Oscillator_Strength", "Dominant_Transitions", "State_Character"])
        for state in states:
            transitions = "; ".join(
                f"{t.get('from')}->{t.get('to')} ({float(t.get('contribution_percent', 0)):.1f}%)"
                for t in state.get("transitions", [])[:5]
            )
            writer.writerow([state.get("state"), state.get("energy_ev"), state.get("wavelength_nm"), state.get("oscillator_strength"), transitions, "REVIEW_NTO"])
    return destination
