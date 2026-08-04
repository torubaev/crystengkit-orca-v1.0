"""Consistent calculation and artifact names for TD-DFT workflows."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict


STAGE_FILE_LABELS = {
    "s0_opt": "S0-optimization",
    "s0_freq": "S0-frequencies",
    "absorption": "absorption",
    "es_opt": "excited-state-optimization",
    "emission": "emission",
}


def safe_filename_part(value, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._+-]+", "-", str(value or "").strip()).strip("-.")
    return text or fallback


def method_identity_stem(compound: str, functional: str, basis: str, solvent: str = "", td_method: str = "") -> str:
    parts = [safe_filename_part(compound, "molecule"), safe_filename_part(functional, "method"), safe_filename_part(basis, "basis")]
    if str(solvent or "").strip():
        parts.append(safe_filename_part(solvent))
    if str(td_method or "").strip():
        parts.append("tda" if str(td_method).strip().upper() == "TDA" else "td-dft")
    return "_".join(parts)


def workflow_calculation_stem(config, stage: str) -> str:
    identity = method_identity_stem(
        config.system.name,
        config.method.functional,
        config.method.basis,
        config.solvent.name if config.solvent.enabled else "",
        "TDA" if config.excited_states.use_tda else "TDDFT",
    )
    return f"{identity}_{STAGE_FILE_LABELS[stage]}"


def _looks_like_basis(token: str) -> bool:
    value = token.lower()
    return any(mark in value for mark in ("def2", "6-31", "6-311", "cc-p", "aug-cc", "sto-", "lanl", "sdd", "ma-def2", "pcseg", "x2c-")) and not value.endswith("/j")


def identity_from_output(output_path: str) -> Dict[str, str]:
    output = Path(output_path)
    result = {"compound": output.stem or "molecule", "functional": "", "basis": "", "solvent": "", "td_method": "", "analysis": ""}
    inp = next((candidate for candidate in (output.with_suffix(".inp"), output.with_suffix(".in")) if candidate.is_file()), None)
    if inp is None:
        return result
    text = inp.read_text(encoding="utf-8", errors="replace")
    simple = " ".join(line.lstrip()[1:].strip() for line in text.splitlines() if line.lstrip().startswith("!"))
    tokens = simple.split()
    basis = next((token for token in tokens if _looks_like_basis(token)), "")
    ignored = {"opt", "tightopt", "verytightopt", "looseopt", "freq", "numfreq", "anfreq", "sp", "moread", "keepdens", "rijcosx", "tightscf", "normalscf", "loosescf", "defgrid1", "defgrid2", "defgrid3", "d3bj", "d4"}
    functional = next((token for token in tokens if token != basis and token.lower() not in ignored and not token.lower().endswith("/j") and not token.lower().startswith("cpcm(")), "")
    solvent_match = re.search(r'(?im)^\s*SMDsolvent\s+["\']?([^"\'\r\n]+)', text)
    cpcm_match = next((re.match(r"(?i)CPCM\((.+)\)", token) for token in tokens if token.upper().startswith("CPCM(")), None)
    solvent = solvent_match.group(1).strip() if solvent_match else (cpcm_match.group(1).strip() if cpcm_match else "")
    tda = re.search(r"(?im)^\s*TDA\s+(true|false)", text)
    td_method = "TDA" if not tda or tda.group(1).lower() == "true" else "TDDFT"
    stem_analysis = re.search(
        r"_(absorption|emission|excited-state-optimization)(?:_S\d+)?$",
        output.stem,
        flags=re.I,
    )
    if stem_analysis:
        analysis = stem_analysis.group(1).lower()
    else:
        analysis = "excited-state-optimization" if re.search(r"(?im)^\s*IRoot\s+\d+", text) and re.search(r"(?i)\bOpt\b", simple) else "absorption"
    compound = output.stem
    if functional and basis:
        marker = f"_{functional}_{basis}_"
        position = compound.lower().find(marker.lower())
        if position >= 0:
            compound = compound[:position]
        compound = re.sub(r"_(?:td-?dft|tda)_(?:absorption|emission|excited-state-optimization)(?:_S\d+)?$", "", compound, flags=re.I)
    result.update({"compound": compound or "molecule", "functional": functional, "basis": basis, "solvent": solvent, "td_method": td_method, "analysis": analysis})
    return result


def identified_output_stem(output_path: str) -> str:
    identity = identity_from_output(output_path)
    if not identity["functional"] or not identity["basis"]:
        return safe_filename_part(identity["compound"], "td-dft")
    base = method_identity_stem(identity["compound"], identity["functional"], identity["basis"], identity["solvent"], identity["td_method"])
    return f"{base}_{safe_filename_part(identity['analysis'], 'absorption')}"
