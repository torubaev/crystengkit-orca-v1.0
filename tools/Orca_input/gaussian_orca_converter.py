"""
Semantic Gaussian → ORCA Input File Converter

This module converts the transferable parts of Gaussian input files to ORCA and
reports or comments every construct that cannot be translated safely. Gaussian
and ORCA do not have one-to-one semantics, so unsupported directives must never
be silently activated as ORCA keywords.

Key Features:
- Parses complete Gaussian route lines and translates to ORCA keywords
- Maps basis sets (6-31G* → 6-31G(d), def2-TZVP, etc.)
- Maps DFT functionals (B3LYP, PBE, CAM-B3LYP, etc.)
- Converts solvation models (PCM → CPCM, SMD)
- Handles job types (Opt, Freq, TD, NMR, etc.)
- Manages dispersion corrections (D3BJ, D3BJ, etc.)
- Converts constraints and geometry optimization settings
- Generates production-ready ORCA input files

Usage:
    from gaussian_orca_converter import GaussianOrcaConverter, ConversionResult

    converter = GaussianOrcaConverter()
    result = converter.convert_file("input.gjf")

    print(result.orca_input)          # Generated ORCA input text
    print(result.warnings)             # Any lost or unsupported features
    print(result.conversion_notes)     # Mapping decisions made
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class ConversionDiagnostic:
    """A machine-readable statement about one translated source feature."""

    severity: str
    status: str
    feature: str
    location: str
    explanation: str
    source_text: str = ""


@dataclass
class ConversionResult:
    """Result of Gaussian → ORCA conversion."""
    orca_input: str = ""
    warnings: List[str] = field(default_factory=list)
    conversion_notes: List[str] = field(default_factory=list)
    charge: Optional[int] = None
    multiplicity: Optional[int] = None
    title: str = ""
    source_route: str = ""
    extracted_keywords: Dict[str, any] = field(default_factory=dict)
    diagnostics: List[ConversionDiagnostic] = field(default_factory=list)
    blocked: bool = False
    draft_output: str = ""
    target_version: str = "ORCA 6.1"


class BasisSetMapper:
    """Maps Gaussian basis set names to ORCA equivalents."""

    GAUSSIAN_TO_ORCA_BASIS = {
        # Minimal basis
        "sto-3g": "STO-3G",
        "sto3g": "STO-3G",

        # Split-valence (Pople)
        "3-21g": "3-21G",
        "321g": "3-21G",
        "6-31g": "6-31G",
        "631g": "6-31G",
        "6-31g*": "6-31G(d)",
        "631g*": "6-31G(d)",
        "6-31g**": "6-31G(d,p)",
        "631g**": "6-31G(d,p)",
        "6-31g(d)": "6-31G(d)",
        "6-31g(d,p)": "6-31G(d,p)",
        "6-31+g": "6-31+G",
        "631+g": "6-31+G",
        "6-31+g(d)": "6-31+G(d)",
        "6-31+g(d,p)": "6-31+G(d,p)",
        "6-31++g": "6-31++G",
        "631++g": "6-31++G",
        "6-31++g(d,p)": "6-31++G(d,p)",

        # 6-311G basis
        "6-311g": "6-311G",
        "6311g": "6-311G",
        "6-311g*": "6-311G(d)",
        "6311g*": "6-311G(d)",
        "6-311g**": "6-311G(d,p)",
        "6311g**": "6-311G(d,p)",
        "6-311g(d)": "6-311G(d)",
        "6-311g(d,p)": "6-311G(d,p)",
        "6-311+g": "6-311+G",
        "6-311++g": "6-311++G",

        # Dunning basis sets
        "cc-pvdz": "cc-pVDZ",
        "ccpvdz": "cc-pVDZ",
        "cc-pvtz": "cc-pVTZ",
        "ccpvtz": "cc-pVTZ",
        "cc-pvqz": "cc-pVQZ",
        "ccpvqz": "cc-pVQZ",
        "aug-cc-pvdz": "aug-cc-pVDZ",
        "augccpvdz": "aug-cc-pVDZ",
        "aug-cc-pvtz": "aug-cc-pVTZ",
        "augccpvtz": "aug-cc-pVTZ",

        # Def2 basis (Karlsruhe)
        "def2-sv": "def2-SV(P)",
        "def2-svp": "def2-SVP",
        "def2-svpd": "def2-SVPD",
        "def2-tzvp": "def2-TZVP",
        "def2-tzvpp": "def2-TZVPP",
        "def2-tzvpd": "def2-TZVPD",
        "def2-qzvp": "def2-QZVP",
        "def2-qzvpp": "def2-QZVPP",

        # Double-zeta
        "lanl2dz": "LANL2DZ",
        "sdd": "SDD",
        "cep-31g": "CEP-31G",
        "cep-121g": "CEP-121G",
    }

    @classmethod
    def map_basis(cls, gaussian_basis: str) -> Tuple[str, Optional[str]]:
        """
        Map Gaussian basis to ORCA equivalent.

        Returns:
            (orca_basis, warning_message)
            warning_message is None if successful, contains reason if unsupported
        """
        if not gaussian_basis:
            return "", "Empty basis set"

        normalized = gaussian_basis.strip().lower()
        if normalized in cls.GAUSSIAN_TO_ORCA_BASIS:
            return cls.GAUSSIAN_TO_ORCA_BASIS[normalized], None
        aliases = {
            "def2svp": "def2-SVP", "def2svpd": "def2-SVPD",
            "def2tzvp": "def2-TZVP", "def2tzvpp": "def2-TZVPP",
            "def2tzvpd": "def2-TZVPD", "def2qzvp": "def2-QZVP",
            "def2qzvpp": "def2-QZVPP",
        }
        if normalized in aliases:
            return aliases[normalized], None
        return "", f"Unsupported or unknown Gaussian basis set '{gaussian_basis}'"


class FunctionalMapper:
    """Maps Gaussian functional names to ORCA equivalents."""

    GAUSSIAN_TO_ORCA_FUNCTIONAL = {
        # Wave-function and semiempirical methods with direct ORCA spellings
        "hf": "HF", "rhf": "RHF", "uhf": "UHF", "rohf": "ROHF",
        "mp2": "MP2", "mp3": "MP3", "ccsd": "CCSD", "ccsd(t)": "CCSD(T)",
        "am1": "AM1", "pm3": "PM3",
        # LDA / Local Density Approximation
        "lsda": "SVWN5",
        "svwn": "SVWN5",
        "svwn5": "SVWN5",
        "vwn": "VWN5",
        "slater": "Slater",

        # GGA (Generalized Gradient Approximation)
        "blyp": "BLYP",
        "bp86": "BP86",
        "pbe": "PBE",
        "pbe0": "PBE0",
        "pw91": "PW91",
        "pwp": "PWP",
        "rpbe": "RPBE",

        # Hybrid GGA
        "b3lyp": "B3LYP",
        "b3lyp*": "B3LYP",
        "b3pw91": "B3PW91",
        "pbe0": "PBE0",
        "pbe1pbe": "PBE0",
        "bh&h": "BHandH",
        "bh&hlyp": "BHandHLYP",
        "x3lyp": "X3LYP",

        # Range-separated hybrid
        "cam-b3lyp": "CAM-B3LYP",
        "cabb3lyp": "CAM-B3LYP",
        "lc-blyp": "LC-BLYP",
        "lc-bp": "LC-BP",
        "lrc-bpbe": "LRC-BPBE",
        "lrc-omega": "LRC-wPBEh",
        "wB97X": "wB97X",
        "wb97xd": "wB97X-D",
        "m062x": "M06-2X",
        "m06-2x": "M06-2X",
        "m06": "M06",
        "m06l": "M06-L",
        "lrc-wpbe": "LRC-wPBEh",

        # Meta-GGA
        "tpss": "TPSS",
        "tpss0": "TPSS0",
        "revtpss": "revTPSS",
        "scan": "SCAN",
        "scanl": "SCAN",
        "metagga": "TPSS",
        "vs98": "VS98",

        # Double-hybrid
        "b2plyp": "B2PLYP",
        "dsd-blyp": "DSD-BLYP",
        "dsd-pbe": "DSD-PBE",
        "b2gp-plyp": "B2GP-PLYP",

        "pm3": "PM3",
        "am1": "AM1",
        "pddg": "PDDG",
        "mindo3": "MINDO3",
    }

    @classmethod
    def map_functional(cls, gaussian_functional: str) -> Tuple[str, Optional[str]]:
        """
        Map Gaussian functional to ORCA equivalent.

        Returns:
            (orca_functional, warning_message)
        """
        if not gaussian_functional:
            return "", "Empty functional"

        normalized = gaussian_functional.strip().lower()
        if normalized in cls.GAUSSIAN_TO_ORCA_FUNCTIONAL:
            return cls.GAUSSIAN_TO_ORCA_FUNCTIONAL[normalized], None
        compact = normalized.replace("-", "").replace("*", "")
        for key, value in cls.GAUSSIAN_TO_ORCA_FUNCTIONAL.items():
            if key.lower().replace("-", "").replace("*", "") == compact:
                return value, None

        if normalized in {"g2", "g3", "cbs-qb3", "cbsqb3"}:
            return "", f"Gaussian composite workflow '{gaussian_functional}' has no single-job ORCA equivalent"
        return "", f"Unsupported or unknown Gaussian method '{gaussian_functional}'"


class SolvationMapper:
    """Maps Gaussian solvation models to ORCA equivalents."""

    GAUSSIAN_TO_ORCA_SOLVENT = {
        # Common solvents - map to ORCA solvent names
        "water": "Water",
        "chloroform": "Chloroform",
        "dichloromethane": "Dichloromethane",
        "dimethylsulfoxide": "DMSO",
        "dmso": "DMSO",
        "acetone": "Acetone",
        "methanol": "Methanol",
        "ethanol": "Ethanol",
        "acetonitrile": "Acetonitrile",
        "ether": "Ether",
        "toluene": "Toluene",
        "benzene": "Benzene",
        "dioxane": "Dioxane",
        "thf": "THF",
        "tetrahydrofuran": "THF",
        "dmf": "DMF",
        "n,n-dimethylformamide": "DMF",
        "hexane": "Hexane",
        "cyclohexane": "Cyclohexane",
        "acetonitrile": "Acetonitrile",
        "pyridine": "Pyridine",
    }

    SOLVATION_MODEL_MAP = {
        "pcm": "CPCM",
        "ipcm": "CPCM",
        "smd": "CPCM",
        "smdsolvent": "CPCM",
        "alpb": "CPCM",
    }

    @classmethod
    def map_solvation(cls, gaussian_solvent: str) -> Tuple[str, Optional[str]]:
        """
        Map Gaussian solvent name to ORCA equivalent.

        Returns:
            (orca_solvent, warning_message)
        """
        if not gaussian_solvent:
            return "", "No solvent specified"

        normalized = gaussian_solvent.strip().lower().replace("-", "").replace("_", "").replace(",", "")

        if normalized in cls.GAUSSIAN_TO_ORCA_SOLVENT:
            return cls.GAUSSIAN_TO_ORCA_SOLVENT[normalized], None

        return "", f"Unsupported or unknown ORCA SMD/CPCM solvent '{gaussian_solvent}'"


class DispersionMapper:
    """Maps Gaussian dispersion corrections to ORCA equivalents."""

    DISPERSION_MAP = {
        "d3": "D3ZERO",
        "d3bj": "D3BJ",
        "d3(bj)": "D3BJ",
        "d4": "D4",
        "d2": "D2",
        "eps": "EmpiricalDispersion",
        "gd3": "D3ZERO",
        "gd3bj": "D3BJ",
    }

    @classmethod
    def map_dispersion(cls, gaussian_disp: str) -> Tuple[str, Optional[str]]:
        """Map Gaussian dispersion to ORCA equivalent."""
        if not gaussian_disp:
            return "", None

        normalized = gaussian_disp.strip().lower()

        if normalized in cls.DISPERSION_MAP:
            return cls.DISPERSION_MAP[normalized], None

        return "", f"Unsupported or unknown Gaussian dispersion '{gaussian_disp}'"


def _split_route_tokens(route: str) -> List[str]:
    """Split a Gaussian route at whitespace while preserving nested options."""
    tokens: List[str] = []
    current: List[str] = []
    depth = 0
    for char in route:
        if char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
    if current:
        tokens.append("".join(current))
    return tokens


def _option_values(token: str) -> List[str]:
    """Return comma-separated values from KEY=VALUE or KEY=(VALUES)."""
    if "(" in token and token.endswith(")"):
        value = token[token.find("(") + 1:-1]
    elif "=" in token:
        value = token.split("=", 1)[1].strip().strip("()")
    else:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_route_line_complete(route_text: str) -> Dict[str, object]:
    """Translate supported Gaussian route semantics into structured ORCA data."""
    extracted: Dict[str, object] = {
        "functional": None, "basis": None, "charged_method": None,
        "job_types": [], "solvation": None, "solvation_model": None,
        "properties": [], "dispersion": None, "extra_keywords": [],
        "constraints": [], "iops": [], "raw_tokens": [], "warnings": [],
        "orca_keywords": [], "scf": {}, "geom": {}, "tddft": {},
        "unmapped_keywords": [],
    }
    if not route_text:
        extracted["warnings"].append("Gaussian route section is empty.")
        return extracted

    route = re.sub(r"^#+[pn]?(?:\s+|$)", "", route_text.strip(), flags=re.IGNORECASE)
    tokens = _split_route_tokens(route)
    extracted["raw_tokens"] = [token.lower() for token in tokens]
    method_token = next((token for token in tokens if "/" in token and not token.lower().startswith("iop")), "")
    if method_token:
        method, basis = method_token.split("/", 1)
        extracted["functional"] = method.strip()
        extracted["basis"] = basis.strip()

    known_methods = {
        "hf", "rhf", "uhf", "rohf", "b3lyp", "pbe0", "pbe1pbe", "bp86",
        "blyp", "cam-b3lyp", "wb97xd", "m062x", "tpss", "tpss0", "mp2",
        "mp3", "mp4", "ccsd", "ccsd(t)", "qcisd", "qcisd(t)", "am1", "pm3",
    }
    if not extracted["functional"]:
        for token in tokens:
            if token.lower() in known_methods:
                extracted["functional"] = token
                break

    def add_unique(name: str, value: str) -> None:
        values = extracted[name]
        if value not in values:
            values.append(value)

    for token in tokens:
        lower = token.lower()
        if token == method_token or lower in {str(extracted["functional"]).lower()}:
            continue
        base = re.split(r"[=(]", lower, maxsplit=1)[0]
        options = _option_values(token)
        option_map = {
            part.split("=", 1)[0].lower(): part.split("=", 1)[1] if "=" in part else True
            for part in options
        }

        if base in {"sp", "force"}:
            add_unique("job_types", "SP")
        elif base in {"opt", "fopt"}:
            add_unique("job_types", "Opt")
            if any(key in option_map for key in {"ts", "saddle"}):
                add_unique("job_types", "TS")
            if "calcfc" in option_map or "calcall" in option_map:
                extracted["geom"]["calc_hess"] = True
            if "modredundant" in option_map:
                extracted["geom"]["modredundant"] = True
            if "tight" in option_map or "verytight" in option_map:
                add_unique("orca_keywords", "TightOpt" if "tight" in option_map else "VeryTightOpt")
            max_iter = option_map.get("maxcycles") or option_map.get("maxcycle")
            if max_iter is not None:
                extracted["geom"]["max_iter"] = max_iter
            unsupported = [item for item in options if item.split("=", 1)[0].lower() not in {
                "ts", "saddle", "calcfc", "calcall", "tight", "verytight", "maxcycles", "maxcycle", "modredundant"
            }]
            if unsupported:
                extracted["warnings"].append("Unsupported Gaussian Opt options: " + ", ".join(unsupported))
        elif base in {"freq", "freqchk"}:
            add_unique("job_types", "Freq")
            if "numer" in option_map:
                add_unique("orca_keywords", "NumFreq")
            unsupported = [item for item in options if item.split("=", 1)[0].lower() not in {"noraman", "raman", "numer"}]
            if unsupported:
                extracted["warnings"].append("Unsupported Gaussian Freq options: " + ", ".join(unsupported))
        elif base in {"td", "tda"}:
            add_unique("job_types", "TDDFT")
            if base == "tda" or "tda" in option_map:
                extracted["tddft"]["tda"] = True
            for source, target in (("nstates", "nroots"), ("root", "iroot")):
                if source in option_map:
                    extracted["tddft"][target] = option_map[source]
        elif base == "nmr":
            add_unique("properties", "NMR")
        elif base == "density":
            add_unique("properties", "Density")
        elif base == "pop":
            pop_options = {str(item).split("=", 1)[0].lower() for item in options}
            if pop_options & {"mk", "chelpg", "esp"}:
                add_unique("properties", "ESP")
            elif pop_options & {"full", "regular", "orbitals"}:
                add_unique("properties", "PrintMOs")
            else:
                extracted["warnings"].append(
                    f"Gaussian population analysis '{token}' needs manual ORCA review."
                )
        elif base == "irc":
            add_unique("job_types", "IRC")
        elif base == "scrf":
            extracted["solvation_model"] = "smd" if "smd" in option_map else "pcm"
            solvent = option_map.get("solvent")
            if solvent is not None:
                extracted["solvation"] = solvent
            unsupported = [item for item in options if item.split("=", 1)[0].lower() not in {"smd", "pcm", "cpcm", "solvent"}]
            if unsupported:
                extracted["warnings"].append("Unsupported Gaussian SCRF options: " + ", ".join(unsupported))
        elif base == "empiricaldispersion":
            extracted["dispersion"] = token.split("=", 1)[1].strip().strip("()") if "=" in token else ""
        elif lower in {"d2", "d3", "d3bj", "gd3", "gd3bj", "d4"}:
            extracted["dispersion"] = lower
        elif base == "scf":
            for item in options:
                key, _, value = item.partition("=")
                key = key.lower()
                if key in {"maxcycle", "maxcycles"}:
                    extracted["scf"]["max_iter"] = value
                elif key in {"tight", "verytight"}:
                    add_unique("orca_keywords", "TightSCF" if key == "tight" else "VeryTightSCF")
                elif key in {"xqc", "qc"}:
                    add_unique("orca_keywords", "SlowConv")
                elif key not in {"direct", "novaracc"}:
                    extracted["warnings"].append(f"Unsupported Gaussian SCF option: {item}")
        elif base in {"integral", "int"}:
            grid = option_map.get("grid")
            if grid is None and options:
                direct_grid = str(options[0]).lower()
                if direct_grid in {"coarsegrid", "finegrid", "ultrafine", "superfinegrid"}:
                    grid = direct_grid
            if grid:
                grid_key = str(grid).lower()
                add_unique("orca_keywords", {
                    "coarsegrid": "DefGrid1", "finegrid": "DefGrid2",
                    "ultrafine": "DefGrid3", "superfinegrid": "DefGrid3",
                }.get(grid_key, "DefGrid3"))
        elif base in {"nosymm", "nosymmetry"}:
            add_unique("orca_keywords", "NoSym")
        elif base == "geom":
            if any(key in option_map for key in {"check", "allcheck"}) or any(str(item).lower() in {"check", "allcheck"} for item in options):
                extracted["warnings"].append("Geom=Check/AllCheck needs checkpoint geometry and cannot be reproduced without coordinates.")
        elif base == "guess":
            if "mix" in option_map or any(str(item).lower() == "mix" for item in options):
                extracted["scf"]["hftyp"] = "UHF"
                extracted["warnings"].append("Guess=Mix was approximated with ORCA HFTyp UHF; verify the initial guess.")
            else:
                add_unique("unmapped_keywords", token)
        elif base == "units":
            pass
        elif base == "iop":
            add_unique("iops", token)
            extracted["warnings"].append(f"Gaussian-specific {token} has no automatic ORCA translation.")
        elif base in {"gen", "genecp", "pseudo", "stable", "counterpoise", "oniom", "external"}:
            add_unique("unmapped_keywords", token)
            extracted["warnings"].append(f"Gaussian keyword '{token}' requires manual ORCA translation.")
        elif lower not in {"p", "n"}:
            add_unique("unmapped_keywords", token)
            extracted["warnings"].append(f"Unmapped Gaussian keyword '{token}' was preserved as a comment, not activated.")

    return extracted


class GaussianRouteParser:
    """Parses Gaussian route lines and extracts all keywords."""

    # Recognized Gaussian keywords and their types
    ROUTE_KEYWORDS = {
        # Method/Theory
        "rhf": ("method", "single"),
        "uhf": ("method", "single"),
        "rohf": ("method", "single"),
        "dft": ("method", "block"),
        "semi": ("method", "single"),
        "pm3": ("method", "single"),
        "am1": ("method", "single"),
        "indo": ("method", "single"),
        "cndo": ("method", "single"),

        # Job type
        "opt": ("job", "block"),
        "freq": ("job", "block"),
        "fopt": ("job", "block"),
        "irc": ("job", "single"),
        "saddle": ("job", "single"),
        "ts": ("job", "single"),
        "conical": ("job", "single"),
        "rstesp": ("job", "single"),
        "scan": ("job", "block"),
        "pop": ("property", "block"),
        "density": ("property", "block"),

        # Excited states
        "td": ("excited", "block"),
        "tda": ("excited", "single"),
        "eom": ("excited", "block"),
        "casscf": ("excited", "block"),
        "oci": ("excited", "single"),

        # Properties
        "nmr": ("property", "single"),
        "polar": ("property", "single"),
        "hyperpol": ("property", "single"),
        "efield": ("property", "block"),
        "scf": ("scf", "block"),
        "field": ("property", "block"),

        # Integral/Basis
        "int": ("integral", "block"),
        "genecp": ("basis", "single"),
        "gen": ("basis", "single"),
        "empiricaldispersion": ("dispersion", "single"),

        # Output
        "output": ("output", "block"),
        "iop": ("iop", "single"),
        "formcheck": ("output", "single"),
        "graphf": ("output", "single"),

        # Geometry
        "geom": ("geom", "block"),

        # Solvation
        "scrf": ("solvation", "block"),

        # Misc
        "nosymm": ("control", "single"),
        "symm": ("control", "single"),
        "test": ("control", "single"),
        "units": ("control", "block"),
        "pseudo": ("basis", "single"),
    }

    @staticmethod
    def parse_route_line(route_text: str) -> Dict[str, any]:
        """
        Parse a Gaussian route line and extract keywords.

        Returns:
            Dict with keys: functional, basis, charged_method, job_types,
                           solvation, properties, extra_keywords
        """
        return _parse_route_line_complete(route_text)


class GaussianOrcaConverter:
    """Main converter class for Gaussian → ORCA transformation."""

    def __init__(self):
        self.parser = GaussianRouteParser()
        self.basis_mapper = BasisSetMapper()
        self.functional_mapper = FunctionalMapper()
        self.solvation_mapper = SolvationMapper()
        self.dispersion_mapper = DispersionMapper()

    def convert_file(self, gaussian_file_path: str) -> ConversionResult:
        """Convert a Gaussian input file to ORCA format."""
        path = Path(gaussian_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Gaussian input file not found: {gaussian_file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        return self.convert_text(text)

    def convert_text(self, gaussian_input_text: str) -> ConversionResult:
        """Convert Gaussian input text to ORCA format."""
        result = ConversionResult()

        link1_sections = [part for part in re.split(
            r"^\s*--Link1--\s*$", gaussian_input_text, flags=re.IGNORECASE | re.MULTILINE
        ) if part.strip()]
        if len(link1_sections) > 1:
            result.warnings.append(
                f"Gaussian input contains {len(link1_sections)} Link1 jobs. Only the first job was converted; "
                "later checkpoint-dependent jobs require an explicit ORCA compound-job workflow."
            )
        gaussian_input_text = link1_sections[0] if link1_sections else gaussian_input_text
        link0 = self._parse_link0(gaussian_input_text)

        # Parse Gaussian input structure
        title, route_line, charge, mult, atoms, warnings = self._parse_gaussian_structure(gaussian_input_text)

        result.title = title
        result.charge = charge
        result.multiplicity = mult
        result.source_route = route_line
        result.warnings.extend(warnings)

        # Parse route line
        route_data = self.parser.parse_route_line(route_line)
        result.extracted_keywords = route_data
        result.warnings.extend(route_data.get("warnings", []))
        constraints, constraint_warnings = self._parse_modredundant(gaussian_input_text, route_data)
        if constraints:
            route_data["geom"]["constraints"] = constraints
        result.warnings.extend(constraint_warnings)

        # Map keywords
        functional, func_warn = self.functional_mapper.map_functional(route_data.get("functional", ""))
        if func_warn:
            result.conversion_notes.append(f"Functional: {func_warn}")

        basis, basis_warn = self.basis_mapper.map_basis(route_data.get("basis", ""))
        if basis_warn:
            result.conversion_notes.append(f"Basis: {basis_warn}")
        if str(route_data.get("basis") or "").lower() in {"gen", "genecp"}:
            basis = ""
            result.warnings.append(
                "Gaussian Gen/GenECP basis and ECP definitions were preserved as comments but require manual conversion to ORCA %basis syntax."
            )

        dispersion = route_data.get("dispersion", "")
        if dispersion:
            disp_mapped, disp_warn = self.dispersion_mapper.map_dispersion(dispersion)
            if disp_warn:
                result.conversion_notes.append(f"Dispersion: {disp_warn}")
        else:
            disp_mapped = ""

        if not atoms:
            raise ValueError(
                "Gaussian input has no explicit Cartesian geometry. Z-matrices and checkpoint-only "
                "Geom=Check/AllCheck jobs must be resolved to coordinates before conversion."
            )

        post_geometry = self._post_geometry_lines(gaussian_input_text)
        if post_geometry and not route_data.get("geom", {}).get("modredundant") and str(route_data.get("basis") or "").lower() not in {"gen", "genecp"}:
            result.warnings.append(
                "Gaussian post-geometry data was preserved as comments because its semantics could not be identified safely."
            )
        if (route_data.get("solvation_model") or "").lower() == "smd" and not route_data.get("solvation"):
            result.warnings.append("Gaussian SMD did not specify a solvent; add and verify SMDsolvent in the ORCA %cpcm block.")

        # Build ORCA input
        orca_lines = self._build_orca_input(
            functional=functional,
            basis=basis,
            charge=charge,
            multiplicity=mult,
            job_types=route_data.get("job_types", []),
            properties=route_data.get("properties", []),
            dispersion=disp_mapped,
            solvation_model=route_data.get("solvation_model"),
            solvation_solvent=route_data.get("solvation"),
            atoms=atoms,
            title=title,
            extra_keywords=route_data.get("extra_keywords", []),
            conversion_notes=result.conversion_notes,
            route_data=route_data,
            link0=link0,
            post_geometry=post_geometry,
        )

        result.orca_input = "\n".join(orca_lines)

        return result

    @staticmethod
    def _parse_link0(text: str) -> Dict[str, str]:
        directives: Dict[str, str] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            match = re.match(r"^%\s*([^=\s]+)\s*(?:=\s*)?(.*)$", stripped)
            if match:
                directives[match.group(1).lower()] = match.group(2).strip()
        return directives

    @staticmethod
    def _parse_modredundant(text: str, route_data: Dict[str, object]) -> Tuple[List[str], List[str]]:
        if not route_data.get("geom", {}).get("modredundant"):
            return [], []
        constraints: List[str] = []
        warnings: List[str] = []
        lines = text.splitlines()
        charge_index = next((i for i, line in enumerate(lines) if re.match(r"^\s*[+-]?\d+\s+\d+\s*$", line)), -1)
        if charge_index < 0:
            return constraints, ["Opt=ModRedundant was requested, but its coordinate section could not be located."]
        idx = charge_index + 1
        while idx < len(lines) and lines[idx].strip():
            idx += 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        for line in lines[idx:]:
            stripped = line.strip()
            if not stripped:
                break
            parts = stripped.split()
            coordinate = parts[0].upper() if parts else ""
            arity = {"B": 2, "A": 3, "D": 4}.get(coordinate)
            if arity and len(parts) >= arity + 2 and parts[arity + 1].upper() == "F":
                try:
                    indices = [str(int(value) - 1) for value in parts[1:arity + 1]]
                except ValueError:
                    warnings.append(f"Could not translate ModRedundant line: {stripped}")
                else:
                    constraints.append("{ " + coordinate + " " + " ".join(indices) + " C }")
            elif arity and any(part.upper() == "S" for part in parts):
                warnings.append(f"Gaussian relaxed scan needs manual ORCA scan limits: {stripped}")
            else:
                warnings.append(f"Unsupported ModRedundant directive: {stripped}")
        return constraints, warnings

    @staticmethod
    def _post_geometry_lines(text: str) -> List[str]:
        """Return nonempty data following the Cartesian geometry section."""
        lines = text.splitlines()
        charge_index = next((i for i, line in enumerate(lines) if re.match(r"^\s*[+-]?\d+\s+\d+\s*$", line)), -1)
        if charge_index < 0:
            return []
        idx = charge_index + 1
        while idx < len(lines) and lines[idx].strip():
            idx += 1
        return [line.rstrip() for line in lines[idx:] if line.strip()]

    def _parse_gaussian_structure(self, text: str) -> Tuple[str, str, Optional[int], Optional[int], List[str], List[str]]:
        """Extract title, route, charge, multiplicity, atoms from Gaussian input."""
        warnings = []
        title = "Converted from Gaussian"
        route_line = ""
        charge = None
        mult = None
        atoms = []

        lines = [line.rstrip("\n") for line in text.splitlines()]
        idx = 0

        # Skip comment/link lines
        while idx < len(lines) and lines[idx].lstrip().startswith(("%", "--")):
            idx += 1

        # Extract route line
        while idx < len(lines):
            stripped = lines[idx].strip()
            if not stripped:
                idx += 1
                continue
            if stripped.startswith("#"):
                route_parts = [stripped]
                idx += 1
                while idx < len(lines) and lines[idx].strip():
                    continuation = lines[idx].strip()
                    route_parts.append(continuation.lstrip("#").strip())
                    idx += 1
                route_line = " ".join(part for part in route_parts if part)
                break
            idx += 1

        # Extract title
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        title_lines = []
        while idx < len(lines) and lines[idx].strip():
            title_lines.append(lines[idx].strip())
            idx += 1
        if title_lines:
            title = " ".join(title_lines)

        # Skip blank line
        while idx < len(lines) and not lines[idx].strip():
            idx += 1

        # Extract charge and multiplicity
        if idx < len(lines):
            cm_match = re.match(r"^\s*([+-]?\d+)\s+(\d+)", lines[idx])
            if cm_match:
                charge = int(cm_match.group(1))
                mult = int(cm_match.group(2))
                idx += 1

        # Extract atoms
        while idx < len(lines):
            stripped = lines[idx].strip()
            if not stripped or stripped.startswith("!"):
                if atoms:  # Stop at first blank after atoms start
                    break
                idx += 1
                continue

            # Try to parse as atom line
            parts = stripped.replace(",", " ").split()
            if len(parts) >= 4:
                try:
                    symbol_match = re.match(r"^([A-Za-z]{1,3})", parts[0])
                    if not symbol_match:
                        raise ValueError
                    symbol = symbol_match.group(1)
                    coord_start = 1
                    if len(parts) >= 5 and re.fullmatch(r"[+-]?\d+", parts[1]):
                        coord_start = 2
                        warnings.append("Gaussian atom freeze-code fields were removed from the ORCA geometry.")
                    x, y, z = (float(parts[coord_start + offset]) for offset in range(3))
                    atoms.append(f"{symbol:<3} {x: .10f} {y: .10f} {z: .10f}")
                except (ValueError, IndexError):
                    if atoms:  # Done with atom section
                        break
            idx += 1

        if atoms and re.search(r"\b(?:units\s*=\s*)?(?:bohr|au|atomic)\b", route_line, re.IGNORECASE):
            converted_atoms = []
            for atom in atoms:
                fields = atom.split()
                converted_atoms.append(
                    f"{fields[0]:<3} {float(fields[1]) * 0.529177210903: .10f} "
                    f"{float(fields[2]) * 0.529177210903: .10f} {float(fields[3]) * 0.529177210903: .10f}"
                )
            atoms = converted_atoms
            warnings.append("Gaussian bohr coordinates were converted to angstrom.")

        return title, route_line, charge, mult, atoms, warnings

    def _build_orca_input(
        self,
        functional: str,
        basis: str,
        charge: Optional[int],
        multiplicity: Optional[int],
        job_types: List[str],
        properties: List[str],
        dispersion: str,
        solvation_model: Optional[str],
        solvation_solvent: Optional[str],
        atoms: List[str],
        title: str,
        extra_keywords: List[str],
        conversion_notes: List[str],
        route_data: Dict[str, object],
        link0: Dict[str, str],
        post_geometry: List[str],
    ) -> List[str]:
        """Build ORCA input lines."""
        lines = []

        # Build keyword line
        kw = []
        if functional:
            kw.append(functional)
        if basis:
            kw.append(basis)

        # Add job types
        if "SP" in job_types or (not job_types):
            kw.append("SP")
        else:
            if "TS" in job_types:
                kw.append("OptTS")
            elif "Opt" in job_types:
                kw.append("Opt")
            if "Freq" in job_types:
                kw.append("Freq")
            if "IRC" in job_types:
                kw.append("IRC")

        # Add properties
        if "NMR" in properties:
            kw.append("NMR")
        if "Density" in properties or "ESP" in properties:
            kw.append("KeepDens")

        # Add dispersion
        if dispersion:
            kw.append(dispersion)

        kw.extend(str(item) for item in route_data.get("orca_keywords", []))

        # Never activate an unknown Gaussian token as an ORCA keyword.  It may
        # be syntactically valid but have a different meaning in the two codes.
        unmapped = (
            list(route_data.get("unmapped_keywords", []))
            + list(route_data.get("iops", []))
            + list(extra_keywords)
        )

        solvent_mapped = ""
        if solvation_solvent:
            solvent_mapped, solvent_warning = self.solvation_mapper.map_solvation(solvation_solvent)
            if solvent_warning:
                conversion_notes.append(f"Solvent: {solvent_warning}")
        if solvation_model and (solvation_model or "").lower() != "smd":
            kw.append(f"CPCM({solvent_mapped})" if solvent_mapped else "CPCM")

        lines.append("! " + " ".join(kw))
        if title:
            lines.append(f"# {title}")
        for extra in unmapped:
            lines.append(f"# Unmapped Gaussian route token: {extra}")
        if post_geometry and not route_data.get("geom", {}).get("modredundant"):
            lines.append("# Untranslated Gaussian post-geometry data follows:")
            lines.extend(f"#   {line}" for line in post_geometry)
        lines.append("")

        # Solvation block
        if (solvation_model or "").lower() == "smd":
            lines.append("%cpcm")
            lines.append("  smd true")
            if solvent_mapped:
                lines.append(f'  SMDsolvent "{solvent_mapped}"')
            lines.append("end")
            lines.append("")

        # Link0 resource directives
        nprocs_text = link0.get("nprocshared") or link0.get("nproc") or link0.get("nproclinda") or "4"
        try:
            nprocs = max(1, int(nprocs_text))
        except ValueError:
            nprocs = 4
            conversion_notes.append(f"Could not parse Gaussian processor count '{nprocs_text}'; using 4")
        maxcore = self._gaussian_mem_to_maxcore(link0.get("mem", ""), nprocs)
        if maxcore:
            lines.append(f"%maxcore {maxcore}")
            lines.append("")
        lines.append("%pal")
        lines.append(f"  nprocs {nprocs}")
        lines.append("end")
        lines.append("")

        chk = link0.get("chk")
        if chk:
            lines.append(f'%base "{Path(chk).stem}"')
            lines.append("")
        oldchk = link0.get("oldchk")
        if oldchk:
            gbw = str(Path(oldchk).with_suffix(".gbw"))
            lines.append(f'%moinp "{gbw}"')
            lines.append("")
            conversion_notes.append(f"Gaussian old checkpoint '{oldchk}' mapped to ORCA GBW guess '{gbw}'; verify that the GBW exists.")

        scf = route_data.get("scf", {})
        if scf:
            lines.append("%scf")
            if scf.get("max_iter"):
                lines.append(f"  MaxIter {scf['max_iter']}")
            if scf.get("hftyp"):
                lines.append(f"  HFTyp {scf['hftyp']}")
            lines.append("end")
            lines.append("")

        geom = route_data.get("geom", {})
        if geom:
            lines.append("%geom")
            if geom.get("max_iter"):
                lines.append(f"  MaxIter {geom['max_iter']}")
            if geom.get("calc_hess"):
                lines.append("  Calc_Hess true")
            if geom.get("constraints"):
                lines.append("  Constraints")
                for constraint in geom["constraints"]:
                    lines.append(f"    {constraint}")
                lines.append("  end")
            lines.append("end")
            lines.append("")

        tddft = route_data.get("tddft", {})
        if "TDDFT" in job_types:
            lines.append("%tddft")
            if tddft.get("nroots"):
                lines.append(f"  NRoots {tddft['nroots']}")
            if tddft.get("iroot"):
                lines.append(f"  IRoot {tddft['iroot']}")
            if tddft.get("tda"):
                lines.append("  TDA true")
            lines.append("end")
            lines.append("")

        if "PrintMOs" in properties:
            lines.append("%output")
            lines.append("  Print[P_MOs] 1")
            lines.append("  Print[P_OrbEn] 2")
            lines.append("end")
            lines.append("")

        # Geometry block with charge and multiplicity
        lines.append(f"* xyz {charge or 0} {multiplicity or 1}")
        lines.extend(atoms)
        lines.append("*")
        lines.append("")

        return lines

    @staticmethod
    def _gaussian_mem_to_maxcore(memory: str, nprocs: int) -> Optional[int]:
        """Convert Gaussian total %Mem to conservative ORCA MB per process."""
        match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?b)?\s*$", memory, re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1))
        unit = (match.group(2) or "MB").lower()
        total_mb = value * {"kb": 1 / 1024, "mb": 1, "gb": 1024, "tb": 1024 * 1024}.get(unit, 1)
        return max(1, int(total_mb * 0.75 / max(1, nprocs)))


# Convenience functions
def convert_gaussian_file(input_path: str, output_path: Optional[str] = None) -> ConversionResult:
    """
    Convert a Gaussian input file to ORCA format.

    Args:
        input_path: Path to Gaussian input file
        output_path: Optional path to write ORCA input. If None, prints to stdout.

    Returns:
        ConversionResult with orca_input, warnings, conversion_notes
    """
    converter = GaussianOrcaConverter()
    result = converter.convert_file(input_path)

    if output_path:
        Path(output_path).write_text(result.orca_input, encoding="utf-8")
        print(f"✓ ORCA input written to: {output_path}")
    else:
        print(result.orca_input)

    if result.warnings:
        print("\n⚠ Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if result.conversion_notes:
        print("\n📝 Conversion notes:")
        for note in result.conversion_notes:
            print(f"  - {note}")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gaussian_orca_converter.py <gaussian_input_file> [output_file]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    convert_gaussian_file(input_file, output_file)
