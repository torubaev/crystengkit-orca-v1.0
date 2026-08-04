from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .config import (
    ExcitedStatesConfig, FrequencyConfig, MethodConfig, OrcaConfig, ResourcesConfig,
    SolventConfig, SystemConfig, WorkflowConfig,
)
from .orca import normal_termination, orca_version


@dataclass
class ExternalWorkflowSource:
    stage: str
    output_path: str
    input_path: str
    gbw_path: str
    config: WorkflowConfig
    message: str


def _matching_required(path: Path, suffixes) -> Path:
    for suffix in suffixes:
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"No same-basename {'/'.join(suffixes)} file was found beside {path.name}.")


def _simple_tokens(text: str):
    lines = [line.strip()[1:].strip() for line in text.splitlines() if line.lstrip().startswith("!")]
    if not lines:
        raise ValueError("The matching ORCA input contains no simple-input keyword line.")
    return " ".join(lines).split()


def _looks_like_basis(token: str) -> bool:
    value = token.lower()
    return any(mark in value for mark in ("def2", "6-31", "6-311", "cc-p", "aug-cc", "sto-", "lanl", "sdd", "ma-def2", "pcseg", "x2c-")) and not value.endswith("/j")


def _parse_source_config(inp: Path, out: Path, orca_executable: str, target_root: int, nprocs: int, maxcore_mb: int, frequency_enabled: bool, threshold: float) -> WorkflowConfig:
    text = inp.read_text(encoding="utf-8", errors="replace")
    tokens = _simple_tokens(text)
    basis_index = next((i for i, token in enumerate(tokens) if _looks_like_basis(token)), None)
    if basis_index is None:
        raise ValueError("Could not identify the basis set in the external ORCA input.")
    basis = tokens[basis_index]
    job_words = {"opt", "tightopt", "verytightopt", "looseopt", "freq", "numfreq", "anfreq", "sp", "moread", "keepdens"}
    technical = {"rijcosx", "tightscf", "normalscf", "loosescf", "defgrid1", "defgrid2", "defgrid3", "d3bj", "d4"}
    functional = next((token for i, token in enumerate(tokens) if i != basis_index and token.lower() not in job_words | technical and not token.lower().endswith("/j") and not token.lower().startswith("cpcm(")), "")
    if not functional:
        raise ValueError("Could not identify the density functional in the external ORCA input.")
    auxiliary = next((token for token in tokens if token.lower().endswith("/j")), "")
    dispersion = next((token.upper() for token in tokens if token.upper() in {"D3BJ", "D4"}), "")
    grid = next((token for token in tokens if token.lower() in {"defgrid1", "defgrid2", "defgrid3"}), "DefGrid2")
    scf = next((token for token in tokens if token.lower() in {"tightscf", "normalscf", "loosescf"}), "TightSCF")
    coord = re.search(r"(?im)^\s*\*\s*xyz(?:file)?\s+([+-]?\d+)\s+(\d+)", text)
    if not coord:
        raise ValueError("Could not determine charge and multiplicity from the external ORCA input.")
    tda_match = re.search(r"(?im)^\s*TDA\s+(true|false)", text)
    nroots_match = re.search(r"(?im)^\s*NRoots\s+(\d+)", text)
    maxdim_match = re.search(r"(?im)^\s*MaxDim\s+(\d+)", text)
    maxiter_match = re.search(r"(?im)^\s*MaxIter\s+(\d+)", text)
    iroot_match = re.search(r"(?im)^\s*IRoot\s+(\d+)", text)
    iroot_mult_match = re.search(r"(?im)^\s*IRootMult\s+(singlet|triplet)", text)
    solvent_match = re.search(r'(?im)^\s*SMDsolvent\s+["\']?([^"\'\r\n]+)', text)
    cpcm_match = next((re.match(r"(?i)CPCM\((.+)\)", token) for token in tokens if token.upper().startswith("CPCM(")), None)
    solvent_name = solvent_match.group(1).strip() if solvent_match else (cpcm_match.group(1).strip() if cpcm_match else "")
    smd = bool(solvent_match)
    known = job_words | technical | {functional.lower(), basis.lower(), auxiliary.lower()}
    extras = [token for token in tokens if token.lower() not in known and not token.lower().startswith("cpcm(")]
    return WorkflowConfig(
        system=SystemConfig(out.stem, int(coord.group(1)), int(coord.group(2)), ""),
        orca=OrcaConfig(orca_executable, orca_version(out.read_text(encoding="utf-8", errors="replace")) or ""),
        method=MethodConfig(functional, basis, auxiliary, dispersion, "rijcosx" in {t.lower() for t in tokens}, grid, scf, extra_keywords=extras),
        excited_states=ExcitedStatesConfig(
            use_tda=not tda_match or tda_match.group(1).lower() == "true",
            nroots=int(nroots_match.group(1)) if nroots_match else max(10, target_root),
            target_root=int(iroot_match.group(1)) if iroot_match else target_root,
            target_multiplicity=iroot_mult_match.group(1).lower() if iroot_mult_match else "singlet",
            maxdim=int(maxdim_match.group(1)) if maxdim_match else 10,
            maxiter=int(maxiter_match.group(1)) if maxiter_match else 300,
        ),
        solvent=SolventConfig(bool(solvent_name), "SMD" if smd else "CPCM", solvent_name, smd),
        frequency=FrequencyConfig(frequency_enabled, True, threshold),
        resources=ResourcesConfig(nprocs, maxcore_mb),
    )


def inspect_external_workflow_source(output_path: str, *, orca_executable: str, target_root: int = 1, nprocs: int = 1, maxcore_mb: int = 4000, frequency_enabled: bool = True, imaginary_threshold_cm1: float = -30.0) -> ExternalWorkflowSource:
    out = Path(output_path).expanduser().resolve()
    if not out.is_file() or out.suffix.lower() != ".out":
        raise FileNotFoundError(f"External ORCA output was not found: {out}")
    output_text = out.read_text(encoding="utf-8", errors="replace")
    if not normal_termination(output_text):
        raise ValueError("The external ORCA calculation did not terminate normally.")
    inp = _matching_required(out, (".inp", ".in"))
    gbw = _matching_required(out, (".gbw",))
    input_text = inp.read_text(encoding="utf-8", errors="replace")
    has_td = bool(re.search(r"(?im)^\s*%(?:tddft|cis)\b", input_text)) or "TD-DFT/TDA EXCITED STATES" in output_text.upper()
    optimized = "OPTIMIZATION HAS CONVERGED" in output_text.upper() or "THE OPTIMIZATION DID CONVERGE" in output_text.upper()
    targeted = bool(re.search(r"(?im)^\s*IRoot\s+\d+", input_text))
    if has_td and optimized and targeted:
        stage = "es_opt"
    elif has_td and not optimized:
        stage = "absorption"
    elif optimized and not has_td:
        stage = "s0_opt"
    else:
        raise ValueError("The external output is not a recognized completed S0 optimization, absorption, or excited-state optimization.")
    config = _parse_source_config(inp, out, orca_executable, target_root, nprocs, maxcore_mb, frequency_enabled, imaginary_threshold_cm1)
    return ExternalWorkflowSource(stage, str(out), str(inp), str(gbw), config, f"Detected completed {stage} calculation with matching input and GBW.")
