"""Evidence-based ORCA calculation report parsing and rendering.

This module deliberately has no Tk dependency.  It can be imported by the
Builder, tests, or invoked directly for an existing ORCA input/output pair.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple


COMPOSITE_METHODS = {"HF-3C", "B97-3C", "R2SCAN-3C", "PBEH-3C", "WB97X-3C"}
DEFAULT_FUNCTIONALS = {
    "HF", "BP86", "BLYP", "PBE", "PBE0", "B3LYP", "B3LYP/G", "TPSSh", "TPSS0", "TPSS",
    "M06L", "M06", "M062X", "B97M-V", "B97M-D3BJ", "B97M-D4", "SCANfunc", "r2SCAN",
    "r2SCANh", "r2SCAN0", "CAM-B3LYP", "LC-BLYP", "LC-PBE", "wB97", "wB97X", "wB97X-D3",
    "wB97X-D4", "wB97X-V", "wB97M-V", "PW6B95", "B2PLYP", *COMPOSITE_METHODS,
}
DEFAULT_BASIS_SETS = {
    "STO-3G", "3-21G", "6-31G", "6-31G(d)", "6-31G(d,p)", "6-31+G(d,p)", "6-311G",
    "6-311G(d,p)", "6-311+G(d,p)", "SVP", "TZVP", "TZVPP", "QZVP", "QZVPP", "def2-SVP",
    "def2-SV(P)", "def2-TZVP", "def2-TZVP(-f)", "def2-TZVPP", "def2-QZVP", "def2-QZVPP",
    "ma-def2-SVP", "ma-def2-TZVP", "ma-def2-TZVPP", "def2-SVPD", "def2-TZVPD", "def2-TZVPPD",
    "cc-pVDZ", "cc-pVTZ", "cc-pVQZ", "aug-cc-pVDZ", "aug-cc-pVTZ", "aug-cc-pVQZ", "MINIX", "vDZP",
}

REFERENCES = {
    "ORCA": "Neese, F.; Wennmohs, F.; Becker, U.; Riplinger, C. The ORCA quantum chemistry program package. J. Chem. Phys. 2020, 152, 224108. https://doi.org/10.1063/5.0004608; Neese, F. Software Update: The ORCA Program System-Version 6.0. WIREs Comput. Mol. Sci. 2025, 15, e70019. https://doi.org/10.1002/wcms.70019",
    "B3LYP": "Becke, A. D. Density-functional thermochemistry. III. The role of exact exchange. J. Chem. Phys. 1993, 98, 5648-5652. https://doi.org/10.1063/1.464913; Lee, C.; Yang, W.; Parr, R. G. Development of the Colle-Salvetti correlation-energy formula into a functional of the electron density. Phys. Rev. B 1988, 37, 785-789. https://doi.org/10.1103/PhysRevB.37.785",
    "PBE": "Perdew, J. P.; Burke, K.; Ernzerhof, M. Generalized Gradient Approximation Made Simple. Phys. Rev. Lett. 1996, 77, 3865-3868. https://doi.org/10.1103/PhysRevLett.77.3865",
    "PBE0": "Adamo, C.; Barone, V. Toward reliable density functional methods without adjustable parameters: The PBE0 model. J. Chem. Phys. 1999, 110, 6158-6170. https://doi.org/10.1063/1.478522",
    "DEF2_BASIS": "Weigend, F.; Ahlrichs, R. Balanced basis sets of split valence, triple zeta valence and quadruple zeta valence quality for H to Rn. Phys. Chem. Chem. Phys. 2005, 7, 3297-3305. https://doi.org/10.1039/b508541a",
    "DEF2_J": "Weigend, F. Accurate Coulomb-fitting basis sets for H to Rn. Phys. Chem. Chem. Phys. 2006, 8, 1057-1065. https://doi.org/10.1039/b515623h",
    "RIJCOSX": "Izsak, R.; Neese, F. An overlap fitted chain of spheres exchange method. J. Chem. Phys. 2011, 135, 144105. https://doi.org/10.1063/1.3646921",
    "D3BJ": "Grimme, S.; Ehrlich, S.; Goerigk, L. Effect of the damping function in dispersion corrected DFT. J. Comput. Chem. 2011, 32, 1456-1465. https://doi.org/10.1002/jcc.21759",
    "D4": "Caldeweyher, E. et al. A generally applicable atomic-charge dependent London dispersion correction. J. Chem. Phys. 2019, 150, 154122. https://doi.org/10.1063/1.5090222",
    "BSSE": "Boys, S. F.; Bernardi, F. The calculation of small molecular interactions by the differences of separate total energies. Mol. Phys. 1970, 19, 553-566. https://doi.org/10.1080/00268977000101561",
    "MULTIWFN": "Lu, T.; Chen, F. Multiwfn: A multifunctional wavefunction analyzer. J. Comput. Chem. 2012, 33, 580-592. https://doi.org/10.1002/jcc.22885",
}


def parse_input_metadata(input_path: str) -> Dict:
    """Parse report-relevant metadata from an ORCA input without GUI state."""
    try:
        text = Path(input_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    match = re.search(r"(?m)^\s*!\s*(.+)$", text)
    if not match:
        return {}
    tokens = match.group(1).split()
    upper_tokens = {token.upper() for token in tokens}
    functionals = {item.upper(): item for item in DEFAULT_FUNCTIONALS}
    bases = {item.upper(): item for item in DEFAULT_BASIS_SETS}
    return {
        "functional": next((functionals[t.upper()] for t in tokens if t.upper() in functionals), ""),
        "basis": next((bases[t.upper()] for t in tokens if t.upper() in bases), ""),
        "dispersion": "D3BJ" if "D3BJ" in upper_tokens else ("D4" if "D4" in upper_tokens else ""),
        "ri_jcosx": "RIJCOSX" in upper_tokens,
        "tight_scf": "TIGHTSCF" in upper_tokens,
        "grid": next((t for t in tokens if t.upper() in {"DEFGRID1", "DEFGRID2", "DEFGRID3"}), ""),
        "job_opt": "OPT" in upper_tokens,
        "job_freq": "FREQ" in upper_tokens,
        "job_sp": "SP" in upper_tokens or not {"OPT", "FREQ"}.intersection(upper_tokens),
    }


def verify_from_output(
    output_path: str,
    fallback: Mapping,
    functionals: Iterable[str],
    basis_sets: Iterable[str],
) -> Tuple[Dict, Dict]:
    """Overlay fallback/input metadata with facts evidenced by ORCA output."""
    data = dict(fallback)
    functionals = tuple(functionals) or tuple(DEFAULT_FUNCTIONALS)
    basis_sets = tuple(basis_sets) or tuple(DEFAULT_BASIS_SETS)
    evidence = {
        "output_parsed": False, "normal_termination": False,
        "single_point_count": 0, "optimization_performed": False,
        "frequency_performed": False, "tddft_performed": False,
    }
    try:
        text = Path(output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data, evidence
    if not text.strip():
        return data, evidence

    upper_text = text.upper()
    evidence.update({
        "output_parsed": True,
        "normal_termination": "ORCA TERMINATED NORMALLY" in upper_text,
        "single_point_count": len(re.findall(r"(?m)^\s*FINAL SINGLE POINT ENERGY\b", text)),
        "optimization_performed": bool(re.search(r"GEOMETRY OPTIMIZATION (?:RUN|CYCLE)", text, re.I)),
        "frequency_performed": "VIBRATIONAL FREQUENCIES" in upper_text,
        "tddft_performed": bool(re.search(
            r"(?:TD-DFT/TDA EXCITED STATES|ORCA CIS CALCULATION|ABSORPTION SPECTRUM VIA)",
            text,
            re.I,
        )),
    })
    echoed = re.findall(r"(?m)^\|\s*\d+>\s*(![^\r\n]+)", text)
    if echoed:
        tokens = echoed[0].strip()[1:].split()
        upper_tokens = {token.upper() for token in tokens}
        functional_lookup = {item.upper(): item for item in functionals}
        basis_lookup = {item.upper(): item for item in basis_sets}
        data.update({
            "functional": "", "basis": "", "dispersion": "", "ri_jcosx": False,
            "tight_scf": False, "grid": "", "job_sp": False, "job_opt": False,
            "job_freq": False, "job_nmr": False, "job_tddft": False,
        })
        for token in tokens:
            upper = token.upper()
            if not data["functional"] and upper in functional_lookup:
                data["functional"] = functional_lookup[upper]
            if not data["basis"] and upper in basis_lookup:
                data["basis"] = basis_lookup[upper]
        data["dispersion"] = "D3BJ" if "D3BJ" in upper_tokens else ("D4" if "D4" in upper_tokens else "")
        data["ri_jcosx"] = "RIJCOSX" in upper_tokens
        data["tight_scf"] = "TIGHTSCF" in upper_tokens
        data["grid"] = next((t for t in tokens if t.upper() in {"DEFGRID1", "DEFGRID2", "DEFGRID3"}), "")
        data["job_opt"] = "OPT" in upper_tokens or evidence["optimization_performed"]
        data["job_freq"] = "FREQ" in upper_tokens or evidence["frequency_performed"]
        data["job_tddft"] = evidence["tddft_performed"]
        data["job_sp"] = bool(evidence["single_point_count"]) and not data["job_opt"]
    basis_matches = re.findall(r"(?im)^\s*Your calculation utilizes the basis:\s*([^\r\n]+)", text)
    if basis_matches and str(data.get("functional", "")).upper() not in COMPOSITE_METHODS:
        data["basis"] = basis_matches[-1].strip()
    return data, evidence


def _marker(key: str, used: List[str]) -> str:
    if key not in used:
        used.append(key)
    return f"[{used.index(key) + 1}]"


def _functional_reference(functional: str) -> str:
    key = functional.strip().upper().replace(" ", "").replace("-", "")
    return {"B3LYP": "B3LYP", "B3LYPG": "B3LYP", "PBE": "PBE", "PBEPBE": "PBE", "PBE0": "PBE0", "PBE1PBE": "PBE0"}.get(key, "")


def render_report(summary: Mapping, github_url: str) -> List[str]:
    """Render a publication-oriented report from parsed execution evidence."""
    settings = summary.get("settings", {})
    execution = summary.get("execution_evidence", {})
    functional = str(settings.get("functional", ""))
    basis = str(settings.get("basis", ""))
    dispersion = str(settings.get("dispersion", ""))
    used: List[str] = []
    orca_ref = _marker("ORCA", used)
    functional_key = _functional_reference(functional)
    functional_ref = _marker(functional_key, used) if functional_key else ""
    basis_ref = _marker("DEF2_BASIS", used) if basis.lower().startswith(("def2", "ma-def2")) else ""
    composite = functional.upper() in COMPOSITE_METHODS
    if composite:
        method_bits = [f"the {functional} composite method"]
    elif functional:
        method_bits = [f"the {functional} functional" + (f" {functional_ref}" if functional_ref else "")]
    else:
        method_bits = ["the electronic-structure method specified in the input"]
    if dispersion:
        ref = _marker(dispersion.upper(), used) if dispersion.upper() in {"D3BJ", "D4"} else ""
        method_bits.append(f"dispersion correction ({dispersion})" + (f" {ref}" if ref else ""))
    if basis and not composite:
        method_bits.append(f"a {basis} basis set" + (f" {basis_ref}" if basis_ref else ""))
    count = int(execution.get("single_point_count") or 0)
    if execution.get("optimization_performed"):
        task = "the geometry optimization that was performed"
    elif count > 1:
        task = f"the series of {count} single-point calculations that was performed"
    elif count == 1:
        task = "the single-point calculation that was performed"
    else:
        task = "the calculation"
    version = summary.get("orca_version", "")
    version_text = f" (version {version})" if version else ""
    paragraphs = [f"Theoretical calculations were carried out with the ORCA{version_text} program package {orca_ref}. " + ", ".join(method_bits) + f" were used for {task}."]
    if settings.get("ri_jcosx"):
        paragraphs.append(f"The RIJCOSX approximation {_marker('RIJCOSX', used)} was used together with the def2/J auxiliary basis set {_marker('DEF2_J', used)}.")
    extra = []
    if settings.get("tight_scf"):
        extra.append("TightSCF convergence criteria were requested.")
    if settings.get("grid"):
        extra.append(f"The numerical integration grid was {settings['grid']}.")
    solvent = settings.get("solvent_resolved") or settings.get("solvent_input") or ""
    if solvent:
        extra.append(f"Solvent effects were included with the SMD model for {solvent}.")
    if extra:
        paragraphs.append(" ".join(extra))
    if settings.get("job_interaction"):
        geometry = "constrained optimized" if settings.get("job_opt") and (settings.get("freeze_all") or settings.get("freeze_heavy")) else ("optimized" if settings.get("job_opt") else "single-point")
        paragraphs.append(f"Dimer interaction energy was calculated using single-point energies evaluated using {geometry} geometry with {functional} {basis}. Basis set superposition error (BSSE) was accounted using counterpoise correction scheme {_marker('BSSE', used)}.")
    post = summary.get("post_processing", {})
    files = summary.get("analysis_files", {})
    if post.get("esp_mep_generated"):
        paragraphs.append(f"Electrostatic-potential data were generated with Multiwfn {_marker('MULTIWFN', used)} through CrystEngKit software ({github_url}).")
        paragraphs.append("MEP parameters used in CrystEngKit: electron-density isovalue 0.001 e/A3 isosurface unless changed in the ESP/MEP viewer.")
    elif post.get("wfn_wfx_generated") or files.get("wavefunction_files"):
        paragraphs.append("A wavefunction file was generated for subsequent analysis; no downstream analysis is asserted in this report.")
    lines = ["Computational details", "", *paragraphs, "", "References"]
    lines.extend(f"[{i}] {REFERENCES[key]}" for i, key in enumerate(used, 1) if key in REFERENCES)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an evidence-based ORCA calculation report.")
    parser.add_argument("output", help="ORCA .out file")
    parser.add_argument("--input", default="", help="Associated ORCA .inp file")
    parser.add_argument("--json", action="store_true", help="Print parsed evidence as JSON instead of prose")
    args = parser.parse_args()
    fallback = parse_input_metadata(args.input) if args.input else {}
    data, evidence = verify_from_output(args.output, fallback, (), ())
    payload = {"input_file": args.input, "output_file": args.output, "settings": data, "execution_evidence": evidence, "post_processing": {}, "analysis_files": {}}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(render_report(payload, "https://github.com/torubaev/crystengkit-orca-v1.0")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
