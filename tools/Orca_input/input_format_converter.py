"""Standalone Gaussian/ORCA input conversion dispatcher.

The Input Builder calls this module only when Save As changes the input format.
The directional converter modules contain the engine-specific parsing and
mapping logic; this module owns format detection and conversion dispatch.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from gaussian_orca_converter import GaussianOrcaConverter
from orca_gaussian_converter import OrcaGaussianConverter


GAUSSIAN_EXTENSIONS = {".gjf", ".com", ".gau", ".gjc"}
ORCA_EXTENSIONS = {".inp"}


@dataclass
class InputConversionResult:
    text: str
    source_program: str
    target_program: str
    converted: bool
    warnings: List[str] = field(default_factory=list)
    conversion_notes: List[str] = field(default_factory=list)


def detect_input_program(path: str) -> Optional[str]:
    """Identify an input engine from its conventional filename extension."""
    extension = Path(str(path or "")).suffix.lower()
    if extension in ORCA_EXTENSIONS:
        return "ORCA"
    if extension in GAUSSIAN_EXTENSIONS:
        return "Gaussian"
    return None


def convert_input_text(text: str, source_program: str, target_program: str) -> InputConversionResult:
    """Convert input text between Gaussian and ORCA, or return it unchanged."""
    source = str(source_program or "").strip().lower()
    target = str(target_program or "").strip().lower()
    canonical = {"orca": "ORCA", "gaussian": "Gaussian"}
    if source not in canonical or target not in canonical:
        raise ValueError("Input format must be ORCA or Gaussian.")
    source_name, target_name = canonical[source], canonical[target]
    if not str(text or "").strip():
        raise ValueError("The source input is empty.")
    if source == target:
        return InputConversionResult(str(text), source_name, target_name, False)
    if source == "gaussian":
        result = GaussianOrcaConverter().convert_text(text)
        return InputConversionResult(
            result.orca_input, source_name, target_name, True,
            list(result.warnings), list(result.conversion_notes),
        )
    result = OrcaGaussianConverter().convert_text(text)
    return InputConversionResult(
        result.gaussian_input, source_name, target_name, True,
        list(result.warnings), list(result.conversion_notes),
    )


def convert_input_file(source_path: str, output_path: str) -> InputConversionResult:
    """Convert according to source/output extensions and write the result."""
    source_program = detect_input_program(source_path)
    target_program = detect_input_program(output_path)
    if source_program is None:
        raise ValueError("Source must use .inp, .gjf, .com, .gau, or .gjc.")
    if target_program is None:
        raise ValueError("Output must use .inp, .gjf, .com, .gau, or .gjc.")
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    result = convert_input_text(text, source_program, target_program)
    Path(output_path).write_text(result.text, encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Gaussian and ORCA input files.")
    parser.add_argument("source", help="Source .gjf/.com or .inp file")
    parser.add_argument("output", help="Destination .inp or .gjf/.com file")
    args = parser.parse_args()
    result = convert_input_file(args.source, args.output)
    action = "Converted" if result.converted else "Copied"
    print(f"{action} {result.source_program} -> {result.target_program}: {args.output}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    for note in result.conversion_notes:
        print(f"Note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
