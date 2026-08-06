#!/usr/bin/env python3
"""Generate controlled torsional distortions from an XYZ geometry.

Atom numbers in configuration files are one-based. Coordinates and atom order
are preserved exactly except for atoms explicitly listed in ``rotating_atoms``.
Both atoms defining an axis are mathematically pinned: either may be listed as
rotating, but neither coordinate is changed by a rotation.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


LOGGER = logging.getLogger("torsion_generator")
DEFAULT_MAX_STRUCTURES = 1000
DEFAULT_ORCA_TEMPLATE = """! CAM-B3LYP def2-SVP def2/J RIJCOSX TightSCF DefGrid2

%tddft
NRoots 10
TDA true
MaxDim 10
MaxIter 100
IRoot 1
IRootMult singlet
FollowIRoot true
DoNTO true
NTOStates 1
NTOThresh 1e-4
end

%cpcm
smd true
SMDsolvent "CHLOROFORM"
end

* xyz {{CHARGE}} {{MULTIPLICITY}}
{{XYZ_BLOCK}}
*
"""

# Compact covalent radii table (angstrom); unknown elements use 0.77 A.
COVALENT_RADII = {
    "H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66,
    "F": 0.57, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02,
    "Br": 1.20, "I": 1.39,
}


class ConfigurationError(ValueError):
    """Raised when a scan configuration is malformed or unsafe."""


@dataclass(frozen=True)
class Molecule:
    symbols: tuple[str, ...]
    coordinates: np.ndarray
    comment: str = ""


@dataclass(frozen=True)
class RotationDefinition:
    name: str
    axis: tuple[int, int]
    rotating: tuple[int, ...]
    angles: tuple[float, ...] = ()
    angle_range: tuple[float, ...] = ()


@dataclass(frozen=True)
class ValidationSettings:
    collision_threshold: float = 0.8
    maximum_displacement: float | None = None
    strict: bool = False


@dataclass(frozen=True)
class GeneratedGeometry:
    filename: str
    mode: str
    rotation_names: tuple[str, ...]
    angles: tuple[float, ...]
    coordinates: np.ndarray
    rms_displacement: float
    minimum_distance: float
    warnings: tuple[str, ...]


def read_xyz(path: Path) -> Molecule:
    """Read a conventional XYZ file without changing atom order."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigurationError(f"Could not read XYZ file {path}: {exc}") from exc
    if len(lines) < 2:
        raise ConfigurationError(f"XYZ file is incomplete: {path}")
    try:
        count = int(lines[0].strip())
    except ValueError as exc:
        raise ConfigurationError("The first XYZ line must be an atom count.") from exc
    if count < 1 or len(lines) < count + 2:
        raise ConfigurationError(f"XYZ declares {count} atoms but has too few coordinate lines.")
    symbols: list[str] = []
    coordinates: list[list[float]] = []
    for number, line in enumerate(lines[2:2 + count], 1):
        fields = line.split()
        if len(fields) < 4:
            raise ConfigurationError(f"Invalid XYZ atom line {number}: {line!r}")
        symbol = fields[0][0].upper() + fields[0][1:].lower()
        try:
            xyz = [float(value) for value in fields[1:4]]
        except ValueError as exc:
            raise ConfigurationError(f"Non-numeric coordinate on XYZ atom line {number}.") from exc
        symbols.append(symbol)
        coordinates.append(xyz)
    array = np.asarray(coordinates, dtype=float)
    if not np.isfinite(array).all():
        raise ConfigurationError("Input XYZ contains NaN or infinite coordinates.")
    return Molecule(tuple(symbols), array, lines[1])


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ConfigurationError(f"{label} must be numeric, not boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"{label} must be numeric.") from exc
    if not math.isfinite(result):
        raise ConfigurationError(f"{label} must be finite.")
    return result


def _index_list(value: Any, label: str, atom_count: int, *, exactly: int | None = None) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{label} must be a JSON list of one-based atom numbers.")
    if exactly is not None and len(value) != exactly:
        raise ConfigurationError(f"{label} must contain exactly {exactly} atom numbers.")
    if not value:
        raise ConfigurationError(f"{label} must not be empty.")
    converted: list[int] = []
    for raw in value:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ConfigurationError(f"{label} entries must be integer atom numbers.")
        if raw < 1 or raw > atom_count:
            raise ConfigurationError(f"{label} atom {raw} is outside 1..{atom_count}.")
        converted.append(raw - 1)
    if len(set(converted)) != len(converted):
        raise ConfigurationError(f"{label} contains duplicate atom numbers.")
    return tuple(converted)


def _float_list(value: Any, label: str, *, minimum: int = 1) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ConfigurationError(f"{label} must be a JSON list with at least {minimum} value(s).")
    return tuple(_number(item, f"{label} entry") for item in value)


def infer_bonds(molecule: Molecule, scale: float = 1.25) -> set[tuple[int, int]]:
    """Infer a validation graph from covalent radii; it never changes geometry."""
    bonds: set[tuple[int, int]] = set()
    for i in range(len(molecule.symbols)):
        ri = COVALENT_RADII.get(molecule.symbols[i], 0.77)
        for j in range(i + 1, len(molecule.symbols)):
            rj = COVALENT_RADII.get(molecule.symbols[j], 0.77)
            distance = float(np.linalg.norm(molecule.coordinates[i] - molecule.coordinates[j]))
            if 0.1 < distance <= scale * (ri + rj):
                bonds.add((i, j))
    return bonds


def _component(start: int, bonds: set[tuple[int, int]], omitted: tuple[int, int]) -> set[int]:
    adjacency: dict[int, set[int]] = {}
    omitted_key = tuple(sorted(omitted))
    for left, right in bonds:
        if (left, right) == omitted_key:
            continue
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    seen, pending = {start}, [start]
    while pending:
        node = pending.pop()
        for neighbor in adjacency.get(node, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen


def parse_config_data(raw: dict[str, Any], molecule: Molecule) -> tuple[dict[str, Any], list[RotationDefinition], ValidationSettings]:
    """Strictly validate an already decoded scan configuration."""
    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be a JSON object.")
    mode = str(raw.get("mode", "")).lower()
    allowed = {"single", "independent", "collective", "alternating", "combinations", "random"}
    if mode not in allowed:
        raise ConfigurationError(f"mode must be one of: {', '.join(sorted(allowed))}.")
    entries = raw.get("rotations")
    if not isinstance(entries, list) or not entries:
        raise ConfigurationError("rotations must be a non-empty JSON list.")
    bonds = infer_bonds(molecule)
    rotations: list[RotationDefinition] = []
    names: set[str] = set()
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ConfigurationError(f"rotations[{position}] must be a JSON object.")
        name = str(entry.get("name", "")).strip()
        if not name or name in names:
            raise ConfigurationError(f"rotations[{position}].name must be non-empty and unique.")
        names.add(name)
        axis = _index_list(entry.get("axis_atoms"), f"rotation {name} axis_atoms", len(molecule.symbols), exactly=2)
        rotating = _index_list(entry.get("rotating_atoms"), f"rotation {name} rotating_atoms", len(molecule.symbols))
        if axis[0] == axis[1]:
            raise ConfigurationError(f"Rotation {name} has identical axis atom numbers.")
        if np.linalg.norm(molecule.coordinates[axis[1]] - molecule.coordinates[axis[0]]) <= 1e-12:
            raise ConfigurationError(f"Rotation {name} axis atoms have identical coordinates.")
        if axis[0] in rotating:
            raise ConfigurationError(
                f"Rotation {name}: fixed-side axis atom {axis[0] + 1} must not be in rotating_atoms. "
                f"The second axis atom {axis[1] + 1} may be listed and remains pinned."
            )
        if not any(atom not in axis for atom in rotating):
            raise ConfigurationError(f"Rotation {name} has no movable atom beyond its axis atoms.")
        # When removing the axis bond actually splits the inferred graph, reject
        # selections reaching into the fixed-side component. Cyclic macrocycles
        # may remain connected; their explicit fragment selection is authoritative.
        fixed_side = _component(axis[0], bonds, axis)
        rotating_side = _component(axis[1], bonds, axis)
        if axis[1] not in fixed_side:  # the graph split into two sides
            wrong_side = sorted(atom + 1 for atom in rotating if atom in fixed_side and atom not in axis)
            if wrong_side:
                raise ConfigurationError(
                    f"Rotation {name} includes fixed-side atom(s) {wrong_side}; this mixes both sides of the axis bond."
                )
            if not any(atom in rotating_side and atom not in axis for atom in rotating):
                raise ConfigurationError(f"Rotation {name} does not contain atoms on the rotating side of its axis.")
        angles = _float_list(entry["angles_deg"], f"rotation {name} angles_deg") if "angles_deg" in entry else ()
        angle_range = _float_list(entry["angle_range_deg"], f"rotation {name} angle_range_deg", minimum=2) if "angle_range_deg" in entry else ()
        if not angles and not angle_range:
            raise ConfigurationError(f"Rotation {name} requires angles_deg or angle_range_deg.")
        if angle_range and len(angle_range) not in {2, 3}:
            raise ConfigurationError(f"Rotation {name} angle_range_deg must be [min,max] or [min,max,step].")
        rotations.append(RotationDefinition(name, axis, rotating, angles, angle_range))
    if mode == "single" and len(rotations) != 1:
        raise ConfigurationError("single mode requires exactly one rotation definition.")
    charge = raw.get("charge", 0)
    multiplicity = raw.get("multiplicity", 1)
    if isinstance(charge, bool) or not isinstance(charge, int):
        raise ConfigurationError("charge must be an integer.")
    if isinstance(multiplicity, bool) or not isinstance(multiplicity, int) or multiplicity < 1:
        raise ConfigurationError("multiplicity must be a positive integer.")
    validation_raw = raw.get("validation", {})
    if not isinstance(validation_raw, dict):
        raise ConfigurationError("validation must be a JSON object.")
    threshold = _number(validation_raw.get("collision_threshold_angstrom", 0.8), "collision threshold")
    max_disp_raw = validation_raw.get("maximum_displacement_angstrom")
    maximum = None if max_disp_raw is None else _number(max_disp_raw, "maximum displacement")
    if threshold <= 0 or (maximum is not None and maximum <= 0):
        raise ConfigurationError("Validation distance thresholds must be positive.")
    settings = ValidationSettings(threshold, maximum, bool(validation_raw.get("strict", False)))
    return raw, rotations, settings


def parse_config(path: Path, molecule: Molecule) -> tuple[dict[str, Any], list[RotationDefinition], ValidationSettings]:
    """Load and strictly validate a JSON scan configuration file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Could not read configuration {path}: {exc}") from exc
    return parse_config_data(raw, molecule)


def range_angles(values: tuple[float, ...], *, stepped_default: bool = False) -> tuple[float, ...]:
    if len(values) == 2:
        if stepped_default:
            raise ConfigurationError("This mode requires angles_deg or angle_range_deg with an explicit step.")
        return values
    start, stop, step = values
    if step == 0 or (stop - start) * step < 0:
        raise ConfigurationError("angle_range_deg step must move from minimum toward maximum.")
    count = int(math.floor((stop - start) / step + 1e-10)) + 1
    return tuple(start + index * step for index in range(count))


def available_angles(rotation: RotationDefinition) -> tuple[float, ...]:
    return rotation.angles or range_angles(rotation.angle_range, stepped_default=True)


def rotate_coordinates(coordinates: np.ndarray, rotation: RotationDefinition, angle_deg: float) -> np.ndarray:
    """Apply Rodrigues' formula to one explicit fragment and return a copy."""
    result = np.array(coordinates, dtype=float, copy=True)
    first, second = rotation.axis
    origin = result[first].copy()
    axis = result[second] - origin
    norm = float(np.linalg.norm(axis))
    if norm <= 1e-12:
        raise ConfigurationError(f"Rotation {rotation.name} has a zero-length current axis.")
    unit = axis / norm
    theta = math.radians(angle_deg)
    cosine, sine = math.cos(theta), math.sin(theta)
    pinned = {first, second}
    for atom in rotation.rotating:
        if atom in pinned:
            continue
        vector = result[atom] - origin
        result[atom] = origin + vector * cosine + np.cross(unit, vector) * sine + unit * np.dot(unit, vector) * (1.0 - cosine)
    if not np.allclose(result[first], coordinates[first], atol=1e-8, rtol=0.0) or not np.allclose(result[second], coordinates[second], atol=1e-8, rtol=0.0):
        raise RuntimeError(f"Internal error: rotation {rotation.name} moved an axis atom.")
    return result


def angle_tag(angle: float) -> str:
    magnitude = abs(angle)
    if math.isclose(magnitude, 0.0, abs_tol=1e-12):
        return "000"
    number = f"{magnitude:02.0f}" if math.isclose(magnitude, round(magnitude), abs_tol=1e-9) else f"{magnitude:05.2f}".rstrip("0").rstrip(".")
    return ("p" if angle > 0 else "m" if angle < 0 else "") + number


def safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.") or "rotation"


def scan_plan(raw: dict[str, Any], rotations: Sequence[RotationDefinition]) -> list[tuple[str, tuple[float, ...]]]:
    """Return deterministic filename stems and angle vectors."""
    mode = str(raw["mode"]).lower()
    plans: list[tuple[str, tuple[float, ...]]] = []
    if mode == "single":
        rotation = rotations[0]
        plans = [(f"single-{safe_part(rotation.name)}_{angle_tag(angle)}", (angle,)) for angle in available_angles(rotation)]
    elif mode == "independent":
        for index, rotation in enumerate(rotations):
            for angle in available_angles(rotation):
                vector = tuple(angle if i == index else 0.0 for i in range(len(rotations)))
                plans.append((f"independent-{safe_part(rotation.name)}_{angle_tag(angle)}", vector))
    elif mode in {"collective", "alternating"}:
        common_raw = raw.get("angles_deg")
        common = _float_list(common_raw, "top-level angles_deg") if common_raw is not None else available_angles(rotations[0])
        for angle in common:
            vector = tuple(angle if mode == "collective" or i % 2 == 0 else -angle for i in range(len(rotations)))
            plans.append((f"{mode}_{angle_tag(angle)}", vector))
    elif mode == "combinations":
        products = itertools.product(*(available_angles(rotation) for rotation in rotations))
        for vector in products:
            tags = "_".join(f"{safe_part(rotation.name)}-{angle_tag(angle)}" for rotation, angle in zip(rotations, vector))
            plans.append((f"combinations_{tags}", tuple(vector)))
    elif mode == "random":
        count = raw.get("random_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ConfigurationError("random mode requires a positive integer random_count.")
        seed = raw.get("random_seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ConfigurationError("random_seed must be an integer.")
        generator = np.random.default_rng(seed)
        for number in range(1, count + 1):
            vector = []
            for rotation in rotations:
                if len(rotation.angle_range) < 2:
                    raise ConfigurationError(f"Random rotation {rotation.name} requires angle_range_deg [min,max].")
                low, high = rotation.angle_range[:2]
                if high < low:
                    raise ConfigurationError(f"Random rotation {rotation.name} has max angle below min angle.")
                vector.append(float(generator.uniform(low, high)))
            plans.append((f"random_{number:04d}", tuple(vector)))
    limit = raw.get("max_structures", DEFAULT_MAX_STRUCTURES)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ConfigurationError("max_structures must be a positive integer.")
    if len(plans) > limit:
        raise ConfigurationError(f"Requested {len(plans)} structures exceeds max_structures={limit}.")
    if len({stem for stem, _ in plans}) != len(plans):
        raise ConfigurationError("Angle formatting produced duplicate filenames; use distinct angle values.")
    return plans


def pairwise_distances(coordinates: np.ndarray) -> tuple[float, dict[tuple[int, int], float]]:
    distances: dict[tuple[int, int], float] = {}
    minimum = math.inf
    for i in range(len(coordinates)):
        for j in range(i + 1, len(coordinates)):
            value = float(np.linalg.norm(coordinates[i] - coordinates[j]))
            distances[(i, j)] = value
            minimum = min(minimum, value)
    return minimum, distances


def validate_geometry(original: Molecule, coordinates: np.ndarray, settings: ValidationSettings, bonds: set[tuple[int, int]]) -> tuple[float, float, tuple[str, ...]]:
    warnings: list[str] = []
    if not np.isfinite(coordinates).all():
        raise ConfigurationError("Generated geometry contains NaN or infinite coordinates.")
    displacement = np.linalg.norm(coordinates - original.coordinates, axis=1)
    rms = float(np.sqrt(np.mean(np.sum((coordinates - original.coordinates) ** 2, axis=1))))
    minimum, distances = pairwise_distances(coordinates)
    close_nonbonded = [(i + 1, j + 1, value) for (i, j), value in distances.items() if (i, j) not in bonds and value < settings.collision_threshold]
    if close_nonbonded:
        preview = ", ".join(f"{i}-{j}:{value:.3f} A" for i, j, value in close_nonbonded[:8])
        warnings.append(f"Nonbonded contact(s) below {settings.collision_threshold:.3f} A: {preview}")
    generated_bonds = infer_bonds(Molecule(original.symbols, coordinates, original.comment))
    lost = sorted(bonds - generated_bonds)
    gained = sorted(generated_bonds - bonds)
    if lost:
        warnings.append("Inferred original bond(s) stretched beyond the connectivity cutoff: " + ", ".join(f"{i + 1}-{j + 1}" for i, j in lost[:12]))
    if gained:
        warnings.append("New inferred bond contact(s) appeared: " + ", ".join(f"{i + 1}-{j + 1}" for i, j in gained[:12]))
    maximum = float(displacement.max(initial=0.0))
    if settings.maximum_displacement is not None and maximum > settings.maximum_displacement:
        warnings.append(f"Maximum atomic displacement {maximum:.4f} A exceeds {settings.maximum_displacement:.4f} A.")
    if settings.strict and warnings:
        raise ConfigurationError("Strict validation rejected generated geometry: " + " | ".join(warnings))
    return rms, minimum, tuple(warnings)


def xyz_block(symbols: Sequence[str], coordinates: np.ndarray) -> str:
    return "\n".join(f"{symbol:<3s} {x: .10f} {y: .10f} {z: .10f}" for symbol, (x, y, z) in zip(symbols, coordinates))


def write_xyz(path: Path, molecule: Molecule, coordinates: np.ndarray, comment: str) -> None:
    path.write_text(f"{len(molecule.symbols)}\n{comment}\n{xyz_block(molecule.symbols, coordinates)}\n", encoding="utf-8")


def render_orca(template: str, molecule: Molecule, coordinates: np.ndarray, charge: int, multiplicity: int) -> str:
    if "{{XYZ_BLOCK}}" not in template:
        raise ConfigurationError("ORCA template must contain the {{XYZ_BLOCK}} placeholder.")
    rendered = template.replace("{{XYZ_BLOCK}}", xyz_block(molecule.symbols, coordinates))
    rendered = rendered.replace("{{CHARGE}}", str(charge)).replace("{{MULTIPLICITY}}", str(multiplicity))
    # A custom template may use a literal '* xyz q m' line. Configuration is
    # authoritative, so replace those two values when the line is recognizable.
    rendered = re.sub(r"(?im)^(\s*\*\s*xyz\s+)[+-]?\d+\s+\d+(\s*)$", rf"\g<1>{charge} {multiplicity}\2", rendered, count=1)
    return rendered.rstrip() + "\n"


def generate(molecule: Molecule, raw: dict[str, Any], rotations: Sequence[RotationDefinition], settings: ValidationSettings, output: Path, *, write_orca_files: bool, template: str) -> list[GeneratedGeometry]:
    output.mkdir(parents=True, exist_ok=True)
    bonds = infer_bonds(molecule)
    results: list[GeneratedGeometry] = []
    for stem, angles in scan_plan(raw, rotations):
        coordinates = np.array(molecule.coordinates, copy=True)
        applied_names: list[str] = []
        applied_angles: list[float] = []
        for rotation, angle in zip(rotations, angles):
            if not math.isclose(angle, 0.0, abs_tol=1e-15):
                coordinates = rotate_coordinates(coordinates, rotation, angle)
            applied_names.append(rotation.name)
            applied_angles.append(angle)
        for rotation in rotations:
            for axis_atom in rotation.axis:
                if not np.allclose(coordinates[axis_atom], molecule.coordinates[axis_atom], atol=1e-8, rtol=0.0):
                    raise ConfigurationError(
                        f"Combined rotations moved axis atom {axis_atom + 1} of {rotation.name}. "
                        "Revise overlapping rotating_atoms selections."
                    )
        rms, minimum, warnings = validate_geometry(molecule, coordinates, settings, bonds)
        filename = stem + ".xyz"
        write_xyz(output / filename, molecule, coordinates, f"{raw['mode']} torsion: " + ", ".join(f"{name}={angle:g} deg" for name, angle in zip(applied_names, applied_angles)))
        if write_orca_files:
            charge = int(raw.get("charge", 0))
            multiplicity = int(raw.get("multiplicity", 1))
            (output / (stem + ".inp")).write_text(render_orca(template, molecule, coordinates, charge, multiplicity), encoding="utf-8")
        results.append(GeneratedGeometry(filename, str(raw["mode"]), tuple(applied_names), tuple(applied_angles), coordinates, rms, minimum, warnings))
        LOGGER.info("Wrote %s (RMS %.4f A, minimum distance %.4f A)%s", filename, rms, minimum, f"; {' | '.join(warnings)}" if warnings else "")
    return results


def write_summary(path: Path, results: Iterable[GeneratedGeometry]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["structure_filename", "mode", "rotation_names", "applied_angles_deg", "rms_displacement_angstrom", "minimum_interatomic_distance_angstrom", "validation_warnings"])
        for item in results:
            writer.writerow([item.filename, item.mode, ";".join(item.rotation_names), ";".join(f"{angle:.10g}" for angle in item.angles), f"{item.rms_displacement:.10g}", f"{item.minimum_distance:.10g}", " | ".join(item.warnings)])


def inspect_molecule(molecule: Molecule) -> None:
    print(f"{'Atom':>6s}  {'Element':<7s} {'X / A':>16s} {'Y / A':>16s} {'Z / A':>16s}")
    for number, (symbol, coordinate) in enumerate(zip(molecule.symbols, molecule.coordinates), 1):
        print(f"{number:6d}  {symbol:<7s} {coordinate[0]:16.8f} {coordinate[1]:16.8f} {coordinate[2]:16.8f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate systematic molecular torsion geometries for ORCA calculations.")
    parser.add_argument("input", type=Path, help="Input XYZ file")
    parser.add_argument("--config", type=Path, help="JSON scan configuration")
    parser.add_argument("--output", type=Path, default=Path("generated_structures"), help="Output directory")
    parser.add_argument("--write-orca", action="store_true", help="Write a matching ORCA .inp for every XYZ")
    parser.add_argument("--orca-template", type=Path, help="Custom ORCA template containing {{XYZ_BLOCK}}")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of files in an existing output directory")
    parser.add_argument("--verbose", action="store_true", help="Print detailed generation information")
    parser.add_argument("--inspect", action="store_true", help="Print one-based atom numbers and coordinates, then exit")
    return parser


def run(args: argparse.Namespace) -> int:
    molecule = read_xyz(args.input.expanduser().resolve())
    if args.inspect:
        inspect_molecule(molecule)
        return 0
    if args.config is None:
        raise ConfigurationError("--config is required unless --inspect is used.")
    output = args.output.expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise ConfigurationError(f"Output path exists and is not a directory: {output}")
    if output.exists() and any(output.iterdir()) and not args.overwrite:
        raise ConfigurationError(f"Output directory is not empty: {output}. Use --overwrite to replace matching generated files.")
    raw, rotations, settings = parse_config(args.config.expanduser().resolve(), molecule)
    template = DEFAULT_ORCA_TEMPLATE
    if args.orca_template:
        try:
            template = args.orca_template.expanduser().resolve().read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(f"Could not read ORCA template: {exc}") from exc
    if args.write_orca and "{{XYZ_BLOCK}}" not in template:
        raise ConfigurationError("ORCA template must contain {{XYZ_BLOCK}}.")
    results = generate(molecule, raw, rotations, settings, output, write_orca_files=args.write_orca, template=template)
    write_summary(output / "torsion_scan_summary.csv", results)
    metadata = {"generator": "torsion_generator", "input": str(args.input.resolve()), "config": str(args.config.resolve()), "structures": len(results)}
    (output / "torsion_scan_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    LOGGER.info("Generated %d structure(s) in %s", len(results), output)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        return run(args)
    except (ConfigurationError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
