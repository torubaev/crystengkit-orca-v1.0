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
        "def2-sv(p)": "def2-SV(P)",
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
    def map_basis(cls, orca_basis: str) -> Tuple[str, Optional[str]]:
        """Map ORCA basis to Gaussian equivalent."""
        if not orca_basis:
            return "", "Empty basis set"

        normalized = orca_basis.strip().lower().replace("(", "").replace(")", "")

        if normalized in cls.ORCA_TO_GAUSSIAN_BASIS:
            return cls.ORCA_TO_GAUSSIAN_BASIS[normalized], None

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

        normalized = orca_functional.strip().lower().replace("-", "").replace("*", "")

        if normalized in cls.ORCA_TO_GAUSSIAN_FUNCTIONAL:
            return cls.ORCA_TO_GAUSSIAN_FUNCTIONAL[normalized], None

        # Partial match
        for key, value in cls.ORCA_TO_GAUSSIAN_FUNCTIONAL.items():
            if key in normalized or normalized in key:
                return value, f"Functional '{orca_functional}' partially matched to '{value}'"

        return orca_functional, f"Unknown functional '{orca_functional}'; using as-is"


class OrcaDispersionMapper:
    """Maps ORCA dispersion corrections to Gaussian equivalents."""

    DISPERSION_MAP = {
        "d3zero": "D3",
        "d3bj": "D3BJ",
        "d3": "D3",
        "d4": "D4",
        "d2": "D2",
    }

    @classmethod
    def map_dispersion(cls, orca_disp: str) -> Tuple[str, Optional[str]]:
        """Map ORCA dispersion to Gaussian equivalent."""
        if not orca_disp:
            return "", None

        normalized = orca_disp.strip().lower()

        if normalized in cls.DISPERSION_MAP:
            return cls.DISPERSION_MAP[normalized], None

        return orca_disp, f"Unknown dispersion '{orca_disp}'; using as-is"


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
            "extra_keywords": [],
            "has_tddft": False,
            "has_nmr": False,
            "has_freq": False,
            "has_opt": False,
        }

        lines = text.split("\n")

        # Extract keyword line (starts with !)
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("!"):
                keyword_line = stripped[1:].strip()
                extracted = OrcaKeywordExtractor._parse_keyword_line(keyword_line, extracted)
                break

        # Extract blocks
        in_pal = False
        in_cpcm = False
        in_tddft = False

        for i, line in enumerate(lines):
            stripped = line.strip().lower()

            # %pal block
            if stripped.startswith("%pal"):
                in_pal = True
                continue
            elif in_pal and stripped.startswith("end"):
                in_pal = False
            elif in_pal and stripped.startswith("nprocs"):
                try:
                    extracted["nprocs"] = int(stripped.split()[-1])
                except ValueError:
                    pass

            # %cpcm block
            if stripped.startswith("%cpcm"):
                in_cpcm = True
                extracted["solvation_model"] = "CPCM"
                continue
            elif in_cpcm and stripped.startswith("end"):
                in_cpcm = False
            elif in_cpcm and "smdsolvent" in stripped:
                match = re.search(r'smdsolvent\s+"([^"]+)"', stripped, re.IGNORECASE)
                if match:
                    extracted["solvation_solvent"] = match.group(1)

            # %tddft block
            if stripped.startswith("%tddft"):
                in_tddft = True
                extracted["has_tddft"] = True
                continue
            elif in_tddft and stripped.startswith("end"):
                in_tddft = False

        return extracted

    @staticmethod
    def _parse_keyword_line(kw_line: str, extracted: Dict) -> Dict:
        """Parse the ! keyword line."""
        tokens = kw_line.split()

        for token in tokens:
            token_lower = token.lower()

            # Functional (first token if looks like functional)
            if not extracted["functional"] and token_lower not in {"sp", "opt", "freq", "tddft", "tda", "nmr"}:
                extracted["functional"] = token
                continue

            # Basis (if contains numbers or known pattern)
            if not extracted["basis"] and (any(c.isdigit() for c in token) or token.startswith("cc-") or token.startswith("def2-")):
                extracted["basis"] = token
                continue

            # Job types
            if token_lower == "sp":
                extracted["job_types"].append("SP")
            elif token_lower == "opt":
                extracted["job_types"].append("Opt")
            elif token_lower == "optts":
                extracted["job_types"].append("TS")
            elif token_lower == "freq":
                extracted["job_types"].append("Freq")
                extracted["has_freq"] = True
            elif token_lower == "irc":
                extracted["job_types"].append("IRC")
            elif token_lower in {"tddft", "tda"}:
                extracted["job_types"].append("TD")
                extracted["has_tddft"] = True

            # Properties
            if token_lower == "nmr":
                extracted["properties"].append("NMR")
                extracted["has_nmr"] = True
            elif "keepdensity" in token_lower or "keepdensity" in token_lower:
                extracted["properties"].append("Density")

            # Dispersion
            if token_lower in {"d3", "d3bj", "d3zero", "d4", "d2"}:
                extracted["dispersion"] = token_lower

            # Other keywords
            elif token_lower not in {"sp", "opt", "freq", "keepdensity", "moread", "cpcm"}:
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
            solvation_solvent=keywords.get("solvation_solvent"),
            atoms=atoms,
            title=title,
            extra_keywords=keywords.get("extra_keywords", []),
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

            # Detect title from first non-empty, non-keyword, non-block line
            if not title.startswith("Converted") and stripped and not stripped.startswith("!") and not stripped.startswith("%"):
                if not in_xyz and "xyz" not in stripped:
                    title = stripped

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
        extra_keywords: List[str],
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

        # Job types
        if "Opt" in job_types:
            route.append("Opt")
        if "Freq" in job_types:
            route.append("Freq")
        if "TS" in job_types:
            route.append("TS")
        if "IRC" in job_types:
            route.append("IRC")
        if "TD" in job_types:
            route.append("TD")
        if "NMR" in properties:
            route.append("NMR")
        if not job_types:  # Default to single point
            if "SP" not in route:
                route.append("SP")

        # Properties/output
        if "Density" in properties:
            route.append("Density=Current")

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
        for extra in extra_keywords:
            if extra and len(extra) < 40:
                conversion_notes.append(f"Unknown ORCA keyword '{extra}' added to route")
                route.append(extra)

        # Build full route line
        lines.append("#P " + " ".join(route))
        lines.append("")
        lines.append(title)
        lines.append("")
        lines.append(f"{charge or 0} {multiplicity or 1}")
        lines.extend(atoms)
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
