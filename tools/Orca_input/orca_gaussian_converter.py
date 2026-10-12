"""
ORCA → Gaussian Input File Converter (Reverse Direction)

Converts ORCA input files back to Gaussian format with automatic
keyword mapping and settings extraction.

Complements gaussian_orca_converter.py for bidirectional conversion.

Usage:
    from orca_gaussian_converter import OrcaGaussianConverter

    converter = OrcaGaussianConverter()
    result = converter.convert_file("input.inp")

    print(result.gaussian_input)       # Generated Gaussian input
    print(result.warnings)              # Any lost or unsupported features
    print(result.conversion_notes)     # Mapping decisions made
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class OrcaConversionResult:
    """Result of ORCA → Gaussian conversion."""
    gaussian_input: str = ""
    warnings: List[str] = field(default_factory=list)
    conversion_notes: List[str] = field(default_factory=list)
    charge: Optional[int] = None
    multiplicity: Optional[int] = None
    title: str = ""
    extracted_keywords: Dict[str, any] = field(default_factory=dict)
    source_route_line: str = ""


class OrcaBasisMapper:
    """Maps ORCA basis set names to Gaussian equivalents."""

    ORCA_TO_GAUSSIAN_BASIS = {
        # Minimal basis
        "sto-3g": "STO-3G",
        "sto3g": "STO-3G",

        # Split-valence (Pople)
        "3-21g": "3-21G",
        "321g": "3-21G",
        "6-31g": "6-31G",
        "631g": "6-31G",
        "6-31g(d)": "6-31G*",
        "6-31gd": "6-31G*",
        "6-31g(d,p)": "6-31G**",
        "6-31gdp": "6-31G**",
        "6-31+g": "6-31+G",
        "631+g": "6-31+G",
        "6-31+g(d)": "6-31+G(d)",
        "6-31++g": "6-31++G",
        "631++g": "6-31++G",
        "6-31++g(d,p)": "6-31++G(d,p)",

        # 6-311G basis
        "6-311g": "6-311G",
        "6311g": "6-311G",
        "6-311g(d)": "6-311G*",
        "6311gd": "6-311G*",
        "6-311g(d,p)": "6-311G**",
        "6311gdp": "6-311G**",
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
        "def2-sv(p)": "Def2SVP",
        "def2-svp": "Def2SVP",
        "def2-svpd": "Def2SVPD",
        "def2-tzvp": "Def2TZVP",
        "def2-tzvpp": "Def2TZVPP",
        "def2-tzvpd": "Def2TZVPD",
        "def2-qzvp": "Def2QZVP",
        "def2-qzvpp": "Def2QZVPP",

        # Double-zeta
        "lanl2dz": "LANL2DZ",
        "sdd": "SDD",
        "cep-31g": "CEP-31G",
        "cep-121g": "CEP-121G",
    }

    @classmethod
    def map_basis(cls, orca_basis: str) -> Tuple[str, Optional[str]]:
        """Map ORCA basis to Gaussian equivalent."""
        if not orca_basis:
            return "", "Empty basis set"

        normalized = orca_basis.strip().lower()

        if normalized in cls.ORCA_TO_GAUSSIAN_BASIS:
            return cls.ORCA_TO_GAUSSIAN_BASIS[normalized], None

        collapsed = re.sub(r"[()_\-]", "", normalized)
        for key, value in cls.ORCA_TO_GAUSSIAN_BASIS.items():
            if re.sub(r"[()_\-]", "", key) == collapsed:
                return value, None

        # Try partial match
        for key, value in cls.ORCA_TO_GAUSSIAN_BASIS.items():
            if key in normalized or normalized in key:
                return value, f"Basis '{orca_basis}' partially matched to '{value}'"

        return orca_basis, f"Unknown basis '{orca_basis}'; using as-is"


class OrcaFunctionalMapper:
    """Maps ORCA functional names to Gaussian equivalents."""

    ORCA_TO_GAUSSIAN_FUNCTIONAL = {
        # LDA
        "svwn5": "LSDA",
        "svwn": "SVWN",
        "vwn5": "VWN5",
        "slater": "Slater",

        # GGA
        "blyp": "BLYP",
        "bp86": "BP86",
        "pbe": "PBE",
        "pw91": "PW91",
        "pwp": "PWP",
        "rpbe": "RPBE",

        # Hybrid GGA
        "b3lyp": "B3LYP",
        "b3pw91": "B3PW91",
        "pbe0": "PBE1PBE",
        "bhandhlyp": "BHandHLYP",
        "bhandh": "BH&H",
        "x3lyp": "X3LYP",

        # Range-separated hybrid
        "cam-b3lyp": "CAM-B3LYP",
        "lc-blyp": "LC-BLYP",
        "lc-bp": "LC-BP",
        "lrc-bpbe": "LRC-BPBE",
        "lrc-omega": "wB97X",
        "wb97x": "wB97X",
        "wb97xd": "wB97X-D",

        # Meta-GGA
        "tpss": "TPSS",
        "tpss0": "TPSS0",
        "revtpss": "revTPSS",
        "scan": "SCAN",
        "vs98": "VS98",

        # Double-hybrid
        "b2plyp": "B2PLYP",
        "dsd-blyp": "DSD-BLYP",
        "dsd-pbe": "DSD-PBE",
        "b2gp-plyp": "B2GP-PLYP",
    }

    @classmethod
    def map_functional(cls, orca_functional: str) -> Tuple[str, Optional[str]]:
        """Map ORCA functional to Gaussian equivalent."""
        if not orca_functional:
            return "", "Empty functional"

        normalized = orca_functional.strip().lower()

        if normalized in cls.ORCA_TO_GAUSSIAN_FUNCTIONAL:
            return cls.ORCA_TO_GAUSSIAN_FUNCTIONAL[normalized], None

        collapsed = normalized.replace("-", "").replace("*", "")
        for key, value in cls.ORCA_TO_GAUSSIAN_FUNCTIONAL.items():
            if key.replace("-", "").replace("*", "") == collapsed:
                return value, None

        # Partial match
        for key, value in cls.ORCA_TO_GAUSSIAN_FUNCTIONAL.items():
            if key in normalized or normalized in key:
                return value, f"Functional '{orca_functional}' partially matched to '{value}'"

        return orca_functional, f"Unknown functional '{orca_functional}'; using as-is"


class OrcaDispersionMapper:
    """Maps ORCA dispersion corrections to Gaussian equivalents."""

    DISPERSION_MAP = {
        "d3zero": "EmpiricalDispersion=GD3",
        "d3bj": "EmpiricalDispersion=GD3BJ",
        "d3": "EmpiricalDispersion=GD3",
        "d2": "EmpiricalDispersion=GD2",
    }

    @classmethod
    def map_dispersion(cls, orca_disp: str) -> Tuple[str, Optional[str]]:
        """Map ORCA dispersion to Gaussian equivalent."""
        if not orca_disp:
            return "", None

        normalized = orca_disp.strip().lower()

        if normalized in cls.DISPERSION_MAP:
            return cls.DISPERSION_MAP[normalized], None

        return "", f"ORCA dispersion '{orca_disp}' has no verified Gaussian mapping and was omitted"


class OrcaSolvationMapper:
    """Maps ORCA solvation models to Gaussian equivalents."""

    SOLVENT_MAP = {
        "water": "Water",
        "acetonitrile": "Acetonitrile",
        "chloroform": "Chloroform",
        "dichloromethane": "Dichloromethane",
        "dmso": "DMSO",
        "dimethylsulfoxide": "DMSO",
        "acetone": "Acetone",
        "methanol": "Methanol",
        "ethanol": "Ethanol",
        "ether": "Ether",
        "thf": "THF",
        "tetrahydrofuran": "THF",
        "toluene": "Toluene",
        "benzene": "Benzene",
        "dioxane": "Dioxane",
        "dmf": "DMF",
        "hexane": "Hexane",
        "cyclohexane": "Cyclohexane",
    }

    @classmethod
    def map_solvent(cls, orca_solvent: str) -> Tuple[str, Optional[str]]:
        """Map ORCA solvent to Gaussian equivalent."""
        if not orca_solvent:
            return "", None

        normalized = orca_solvent.strip().lower()

        if normalized in cls.SOLVENT_MAP:
            return cls.SOLVENT_MAP[normalized], None

        return orca_solvent, f"Solvent '{orca_solvent}' not mapped; using as-is"


class OrcaKeywordExtractor:
    """Extracts keywords from ORCA input files."""

    @staticmethod
    def extract_keywords(text: str) -> Dict[str, any]:
        """
        Extract all keywords from ORCA input text.

        Returns dict with:
            functional, basis, job_types, properties, dispersion,
            solvation_model, solvation_solvent, nprocs, extra_keywords
        """
        extracted = {
            "functional": None,
            "basis": None,
            "job_types": [],
            "properties": [],
            "dispersion": None,
            "solvation_model": None,
            "solvation_solvent": None,
            "nprocs": 1,
            "maxcore": None,
            "base": None,
            "moinp": None,
            "extra_keywords": [],
            "gaussian_keywords": [],
            "warnings": [],
            "scf": {},
            "geom": {"constraints": []},
            "tddft": {},
            "output": {},
            "has_tddft": False,
            "has_nmr": False,
            "has_freq": False,
            "has_opt": False,
        }

        lines = text.split("\n")

        # ORCA permits multiple simple-input lines. Parse all of them.
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("!"):
                keyword_line = stripped[1:].strip()
                extracted = OrcaKeywordExtractor._parse_keyword_line(keyword_line, extracted)

        # Single-line percent directives.
        for line in lines:
            stripped = line.strip()
            maxcore = re.match(r"^%maxcore\s+(\d+)", stripped, re.IGNORECASE)
            if maxcore:
                extracted["maxcore"] = int(maxcore.group(1))
            base = re.match(r'^%base\s+"?([^"\s]+)"?', stripped, re.IGNORECASE)
            if base:
                extracted["base"] = base.group(1)
            moinp = re.match(r'^%moinp\s+"?([^"\r\n]+)"?', stripped, re.IGNORECASE)
            if moinp:
                extracted["moinp"] = moinp.group(1).strip()

        # Structured ORCA blocks.
        known_blocks = {"pal", "cpcm", "tddft", "cis", "scf", "geom", "output", "eprnmr"}
        i = 0
        while i < len(lines):
            start = re.match(r"^\s*%([A-Za-z0-9_]+)\b", lines[i])
            if not start:
                i += 1
                continue
            name = start.group(1).lower()
            if name not in known_blocks:
                if name not in {"maxcore", "base", "moinp"}:
                    extracted["warnings"].append(
                        f"ORCA %{name} block/directive has no automatic Gaussian translation"
                    )
                i += 1
                continue
            block, next_index = OrcaKeywordExtractor._collect_block(lines, i)
            OrcaKeywordExtractor._parse_block(name, block, extracted)
            i = next_index

        return extracted

    @staticmethod
    def _collect_block(lines: List[str], start: int) -> Tuple[List[str], int]:
        """Collect a percent block, accounting for nested Constraints/Scan sections."""
        content: List[str] = []
        nested = 0
        i = start + 1
        while i < len(lines):
            stripped = lines[i].strip()
            lower = stripped.lower()
            if lower in {"constraints", "scan"}:
                nested += 1
                content.append(stripped)
            elif lower == "end":
                if nested:
                    nested -= 1
                    content.append(stripped)
                else:
                    return content, i + 1
            else:
                content.append(stripped)
            i += 1
        return content, i

    @staticmethod
    def _parse_block(name: str, block: List[str], extracted: Dict) -> None:
        pairs: Dict[str, str] = {}
        for line in block:
            parts = line.split(None, 1)
            if len(parts) == 2:
                pairs[parts[0].lower()] = parts[1].strip().strip('"')

        if name == "pal":
            try:
                extracted["nprocs"] = max(1, int(pairs.get("nprocs", "1")))
            except ValueError:
                extracted["warnings"].append("Could not parse ORCA %pal NProcs; using 1")
        elif name == "cpcm":
            extracted["solvation_model"] = "SMD" if pairs.get("smd", "").lower() == "true" else "CPCM"
            extracted["solvation_solvent"] = pairs.get("smdsolvent") or pairs.get("solvent")
        elif name in {"tddft", "cis"}:
            extracted["has_tddft"] = True
            if "TD" not in extracted["job_types"]:
                extracted["job_types"].append("TD")
            for source, target in (("nroots", "nstates"), ("iroot", "root")):
                if source in pairs:
                    extracted["tddft"][target] = pairs[source]
            if pairs.get("tda", "").lower() == "true":
                extracted["tddft"]["tda"] = True
        elif name == "scf":
            if "maxiter" in pairs:
                extracted["scf"]["maxcycle"] = pairs["maxiter"]
            if "hftyp" in pairs:
                extracted["scf"]["hftyp"] = pairs["hftyp"]
        elif name == "geom":
            if "maxiter" in pairs:
                extracted["geom"]["maxcycle"] = pairs["maxiter"]
            if pairs.get("calc_hess", "").lower() == "true":
                extracted["geom"]["calcfc"] = True
            for line in block:
                match = re.match(r"^\{\s*([BAD])\s+([0-9\s]+)\s+C\s*\}$", line, re.IGNORECASE)
                if match:
                    indices = [str(int(item) + 1) for item in match.group(2).split()]
                    extracted["geom"]["constraints"].append(
                        f"{match.group(1).upper()} {' '.join(indices)} F"
                    )
                elif line.startswith("{"):
                    extracted["warnings"].append(
                        f"ORCA geometry constraint '{line}' needs manual Gaussian translation"
                    )
        elif name == "eprnmr":
            if pairs.get("nmr", "").lower() == "true":
                extracted["has_nmr"] = True
                if "NMR" not in extracted["properties"]:
                    extracted["properties"].append("NMR")
        elif name == "output":
            p_mos = pairs.get("print[p_mos]")
            p_orben = pairs.get("print[p_orben]")
            if (p_mos and p_mos != "0") or (p_orben and p_orben != "0"):
                extracted["output"]["pop_full"] = True
            unknown = [line for line in block if line and not re.match(
                r"^Print\[P_(?:MOs|OrbEn)\]\s+\d+\s*$", line, re.IGNORECASE
            )]
            if unknown:
                extracted["warnings"].append(
                    "Some ORCA %output controls have no automatic Gaussian translation: " + "; ".join(unknown)
                )

    @staticmethod
    def _parse_keyword_line(kw_line: str, extracted: Dict) -> Dict:
        """Parse the ! keyword line."""
        tokens = kw_line.split()

        for token in tokens:
            token_lower = token.lower()

            # Job types and properties
            if token_lower == "sp":
                extracted["job_types"].append("SP")
                continue
            if token_lower == "opt":
                extracted["job_types"].append("Opt")
                extracted["has_opt"] = True
                continue
            if token_lower == "optts":
                extracted["job_types"].append("TS")
                extracted["has_opt"] = True
                continue
            if token_lower == "freq":
                extracted["job_types"].append("Freq")
                extracted["has_freq"] = True
                continue
            if token_lower == "irc":
                extracted["job_types"].append("IRC")
                continue
            if token_lower in {"tddft", "tda"}:
                extracted["job_types"].append("TD")
                extracted["has_tddft"] = True
                continue
            if token_lower == "nmr":
                extracted["properties"].append("NMR")
                extracted["has_nmr"] = True
                continue
            if token_lower in {"keepdens", "keepdensity"}:
                extracted["properties"].append("Density")
                continue

            # Dispersion
            if token_lower in {"d3", "d3bj", "d3zero", "d4", "d2"}:
                extracted["dispersion"] = token_lower
                continue

            # ORCA controls with direct Gaussian equivalents.
            if token_lower in {"tightscf", "verytightscf", "loosescf"}:
                extracted["scf"]["convergence"] = {
                    "tightscf": "Tight", "verytightscf": "VeryTight", "loosescf": "Loose"
                }[token_lower]
                continue
            if token_lower == "slowconv":
                extracted["scf"]["xqc"] = True
                continue
            if token_lower in {"tightopt", "verytightopt"}:
                extracted["geom"]["convergence"] = "Tight" if token_lower == "tightopt" else "VeryTight"
                continue
            if token_lower == "numfreq":
                if "Freq" not in extracted["job_types"]:
                    extracted["job_types"].append("Freq")
                extracted["geom"]["numerical_freq"] = True
                continue
            gaussian_keyword_map = {
                "defgrid1": "Integral=CoarseGrid",
                "defgrid2": "Integral=FineGrid",
                "defgrid3": "Integral=UltraFine",
                "nosym": "NoSymm",
                "nosymm": "NoSymm",
            }
            if token_lower in gaussian_keyword_map:
                extracted["gaussian_keywords"].append(gaussian_keyword_map[token_lower])
                continue

            # RI/RIJCOSX and auxiliary bases are ORCA implementation details,
            # not valid Gaussian route keywords.
            if token_lower in {"ri", "rijcosx", "rijonk", "rijk", "rijdx", "nori"}:
                extracted["warnings"].append(
                    f"ORCA approximation keyword '{token}' was omitted (no direct Gaussian equivalent)"
                )
                continue
            if re.search(r"/(?:j|jk|c)$", token_lower):
                extracted["warnings"].append(
                    f"ORCA auxiliary basis '{token}' was omitted (no direct Gaussian equivalent)"
                )
                continue

            # Functional is conventionally the first remaining token.
            if not extracted["functional"]:
                extracted["functional"] = token
                continue

            # Orbital basis (after the functional).
            if not extracted["basis"] and (
                any(c.isdigit() for c in token)
                or token_lower.startswith("cc-")
                or token_lower.startswith("aug-cc-")
                or token_lower.startswith("def2-")
            ):
                extracted["basis"] = token
                continue

            cpcm = re.match(r"cpcm\(([^)]+)\)", token, re.IGNORECASE)
            if cpcm:
                extracted["solvation_model"] = "CPCM"
                extracted["solvation_solvent"] = cpcm.group(1)
                continue
            if token_lower == "cpcm":
                extracted["solvation_model"] = "CPCM"
                continue
            if token_lower == "moread":
                extracted["warnings"].append(
                    "ORCA MOREAD orbital reuse cannot be transferred without a Gaussian checkpoint"
                )
                continue
            extracted["extra_keywords"].append(token)

        return extracted


class OrcaGaussianConverter:
    """Main converter class for ORCA → Gaussian transformation."""

    def __init__(self):
        self.basis_mapper = OrcaBasisMapper()
        self.functional_mapper = OrcaFunctionalMapper()
        self.solvation_mapper = OrcaSolvationMapper()
        self.dispersion_mapper = OrcaDispersionMapper()
        self.keyword_extractor = OrcaKeywordExtractor()

    def convert_file(self, orca_file_path: str) -> OrcaConversionResult:
        """Convert an ORCA input file to Gaussian format."""
        path = Path(orca_file_path)
        if not path.exists():
            raise FileNotFoundError(f"ORCA input file not found: {orca_file_path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        return self.convert_text(text)

    def convert_text(self, orca_input_text: str) -> OrcaConversionResult:
        """Convert ORCA input text to Gaussian format."""
        result = OrcaConversionResult()

        # Extract structure and title
        title, charge, mult, atoms, xyz_content = self._parse_orca_structure(orca_input_text)
        result.title = title
        result.charge = charge
        result.multiplicity = mult

        # Extract keywords
        keywords = self.keyword_extractor.extract_keywords(orca_input_text)
        result.extracted_keywords = keywords
        result.warnings.extend(keywords.get("warnings", []))

        # Save original keyword line
        for line in orca_input_text.split("\n"):
            if line.strip().startswith("!"):
                result.source_route_line = line.strip()
                break

        # Map keywords
        functional, func_warn = self.functional_mapper.map_functional(keywords.get("functional", ""))
        if func_warn:
            result.conversion_notes.append(f"Functional: {func_warn}")

        basis, basis_warn = self.basis_mapper.map_basis(keywords.get("basis", ""))
        if basis_warn:
            result.conversion_notes.append(f"Basis: {basis_warn}")

        dispersion = keywords.get("dispersion", "")
        if dispersion:
            disp_mapped, disp_warn = self.dispersion_mapper.map_dispersion(dispersion)
            if disp_warn:
                result.conversion_notes.append(f"Dispersion: {disp_warn}")
        else:
            disp_mapped = ""

        if not atoms:
            raise ValueError(
                "ORCA input has no explicit Cartesian '* xyz' geometry. Resolve xyzfile/external geometry before conversion."
            )

        solvent = keywords.get("solvation_solvent")
        if solvent:
            solvent, solvent_warn = self.solvation_mapper.map_solvent(solvent)
            if solvent_warn:
                result.conversion_notes.append(f"Solvent: {solvent_warn}")

        # Build Gaussian input
        gaussian_lines = self._build_gaussian_input(
            functional=functional,
            basis=basis,
            charge=charge,
            multiplicity=mult,
            job_types=keywords.get("job_types", []),
            properties=keywords.get("properties", []),
            dispersion=disp_mapped,
            solvation_model=keywords.get("solvation_model"),
            solvation_solvent=solvent,
            atoms=atoms,
            title=title,
            nprocs=keywords.get("nprocs", 1),
            maxcore=keywords.get("maxcore"),
            base=keywords.get("base"),
            moinp=keywords.get("moinp"),
            scf=keywords.get("scf", {}),
            geom=keywords.get("geom", {}),
            tddft=keywords.get("tddft", {}),
            output=keywords.get("output", {}),
            gaussian_keywords=keywords.get("gaussian_keywords", []),
            extra_keywords=keywords.get("extra_keywords", []),
            warnings=result.warnings,
            conversion_notes=result.conversion_notes,
        )

        result.gaussian_input = "\n".join(gaussian_lines)

        return result

    def _parse_orca_structure(self, text: str) -> Tuple[str, Optional[int], Optional[int], List[str], str]:
        """Extract title, charge, multiplicity, atoms from ORCA input."""
        title = "Converted from ORCA"
        charge = 0
        mult = 1
        atoms = []
        xyz_content = ""

        lines = [line.rstrip("\n") for line in text.splitlines()]

        # Find geometry block (between * xyz charge mult and *)
        in_xyz = False
        xyz_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # ORCA comments are the only safe title source. Arbitrary block
            # contents must never become the Gaussian title.
            if title == "Converted from ORCA" and stripped.startswith("#"):
                candidate = stripped.lstrip("#").strip()
                if candidate and not candidate.lower().startswith(("unmapped ", "untranslated ")):
                    title = candidate

            # Start of geometry block
            if stripped.startswith("* xyz"):
                match = re.match(r"\*\s+xyz\s+([+-]?\d+)\s+(\d+)", stripped)
                if match:
                    charge = int(match.group(1))
                    mult = int(match.group(2))
                in_xyz = True
                continue

            # End of geometry block
            if in_xyz and stripped == "*":
                in_xyz = False
                continue

            # Collect atom lines
            if in_xyz and stripped:
                xyz_lines.append(stripped)

        # Convert xyz lines to Gaussian format
        for xyz_line in xyz_lines:
            parts = xyz_line.split()
            if len(parts) >= 4:
                try:
                    symbol = parts[0]
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    atoms.append(f"{symbol:>2}    {x:12.6f}    {y:12.6f}    {z:12.6f}")
                except ValueError:
                    pass

        xyz_content = "\n".join(xyz_lines)

        return title, charge, mult, atoms, xyz_content

    def _build_gaussian_input(
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
        nprocs: int,
        maxcore: Optional[int],
        base: Optional[str],
        moinp: Optional[str],
        scf: Dict[str, str],
        geom: Dict[str, object],
        tddft: Dict[str, object],
        output: Dict[str, object],
        gaussian_keywords: List[str],
        extra_keywords: List[str],
        warnings: List[str],
        conversion_notes: List[str],
    ) -> List[str]:
        """Build Gaussian input lines."""
        lines = []

        # Build route line
        route = []

        # Add functional/basis
        if functional and basis:
            route.append(f"{functional}/{basis}")
        elif functional:
            route.append(functional)
        elif basis:
            route.append(f"B3LYP/{basis}")
        else:
            route.append("B3LYP/6-31G(d,p)")

        # Job types and their block-level options.
        if "TS" in job_types:
            opt_options = ["TS", "NoEigenTest"]
            if geom.get("calcfc"):
                opt_options.append("CalcFC")
            if geom.get("convergence"):
                opt_options.append(str(geom["convergence"]))
            if geom.get("maxcycle"):
                opt_options.append(f"MaxCycles={geom['maxcycle']}")
            if geom.get("constraints"):
                opt_options.append("ModRedundant")
            route.append("Opt=(" + ",".join(opt_options) + ")")
        elif "Opt" in job_types:
            opt_options = []
            if geom.get("calcfc"):
                opt_options.append("CalcFC")
            if geom.get("convergence"):
                opt_options.append(str(geom["convergence"]))
            if geom.get("maxcycle"):
                opt_options.append(f"MaxCycles={geom['maxcycle']}")
            if geom.get("constraints"):
                opt_options.append("ModRedundant")
            route.append("Opt=(" + ",".join(opt_options) + ")" if opt_options else "Opt")
        if "Freq" in job_types:
            route.append("Freq=Numer" if geom.get("numerical_freq") else "Freq")
        if "IRC" in job_types:
            route.append("IRC")
        if "TD" in job_types:
            td_options = []
            if tddft.get("nstates"):
                td_options.append(f"NStates={tddft['nstates']}")
            if tddft.get("root"):
                td_options.append(f"Root={tddft['root']}")
            td_name = "TDA" if tddft.get("tda") else "TD"
            route.append(f"{td_name}=({','.join(td_options)})" if td_options else td_name)
        if "NMR" in properties:
            route.append("NMR")
        if "SP" in job_types or not job_types:
            route.append("SP")

        # Properties/output
        if "Density" in properties:
            route.append("Density=Current")
        if output.get("pop_full"):
            route.append("Pop=Full")

        scf_options = []
        if scf.get("convergence"):
            scf_options.append(str(scf["convergence"]))
        if scf.get("xqc"):
            scf_options.append("XQC")
        if scf.get("maxcycle"):
            scf_options.append(f"MaxCycle={scf['maxcycle']}")
        if scf_options:
            route.append(
                f"SCF={scf_options[0]}" if len(scf_options) == 1
                else "SCF=(" + ",".join(scf_options) + ")"
            )
        if scf.get("hftyp"):
            warnings.append(
                f"ORCA %scf HFTyp {scf['hftyp']} was not forced; verify the Gaussian method/reference"
            )

        # Dispersion
        if dispersion:
            route.append(dispersion)

        # Solvation
        if solvation_model or solvation_solvent:
            solvent_name = solvation_solvent or "Water"
            if solvation_model and "smd" in solvation_model.lower():
                route.append(f"SCRF=(SMD,Solvent={solvent_name})")
            else:
                route.append(f"SCRF=(PCM,Solvent={solvent_name})")

        # Extra keywords
        route.extend(gaussian_keywords)

        for extra in extra_keywords:
            if extra and len(extra) < 40:
                warnings.append(
                    f"Unknown ORCA keyword '{extra}' was omitted; review it manually"
                )

        # Build full route line
        if nprocs and nprocs > 0:
            lines.append(f"%NProcShared={nprocs}")
        if maxcore and maxcore > 0:
            total_mb = max(1, round(maxcore * max(1, nprocs) / 0.75))
            lines.append(f"%Mem={total_mb}MB")
        if base:
            chk_path = str(Path(base).with_suffix(".chk"))
            lines.append(f"%Chk={chk_path}")
        if moinp:
            oldchk = str(Path(moinp).with_suffix(".chk"))
            lines.append(f"%OldChk={oldchk}")
            warnings.append(
                f"ORCA MO input '{moinp}' was mapped by filename to '{oldchk}'; a compatible Gaussian checkpoint must exist"
            )
        lines.append("#P " + " ".join(route))
        lines.append("")
        lines.append(title)
        lines.append("")
        lines.append(f"{charge or 0} {multiplicity or 1}")
        lines.extend(atoms)
        lines.append("")
        if geom.get("constraints"):
            lines.extend(str(item) for item in geom["constraints"])
            lines.append("")

        return lines


# Convenience functions
def convert_orca_file(input_path: str, output_path: Optional[str] = None) -> OrcaConversionResult:
    """
    Convert an ORCA input file to Gaussian format.

    Args:
        input_path: Path to ORCA input file
        output_path: Optional path to write Gaussian input

    Returns:
        OrcaConversionResult with gaussian_input, warnings, conversion_notes
    """
    converter = OrcaGaussianConverter()
    result = converter.convert_file(input_path)

    if output_path:
        Path(output_path).write_text(result.gaussian_input, encoding="utf-8")
        print(f"✓ Gaussian input written to: {output_path}")
    else:
        print(result.gaussian_input)

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
        print("Usage: python orca_gaussian_converter.py <orca_input_file> [output_file]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    convert_orca_file(input_file, output_file)
