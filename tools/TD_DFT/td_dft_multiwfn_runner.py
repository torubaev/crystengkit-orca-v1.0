"""Guarded Multiwfn orchestration and cache for TD-DFT post-processing.

No TD-DFT menu sequence is embedded until it has been verified against a
supported Multiwfn release. Existing, valid cube files are safely reused.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ANALYSES = {
    "NTO hole/electron": ("NTO_hole.cube", "NTO_electron.cube"),
    "Difference density": ("difference_density.cube",),
    "Transition density": ("transition_density.cube",),
    "Attachment/detachment": ("attachment.cube", "detachment.cube"),
    "Hole/electron density": ("hole_density.cube", "electron_density.cube"),
    "Hole-electron descriptors": ("descriptors.csv",),
}


def is_cube_file_valid(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = [next(handle) for _ in range(6)]
        atom_count = abs(int(lines[2].split()[0]))
        dims = [abs(int(lines[i].split()[0])) for i in range(3, 6)]
        return atom_count >= 0 and all(value > 1 for value in dims) and path.stat().st_size > 128
    except Exception:
        return False


class MultiwfnTDDFTRunner:
    def __init__(self, multiwfn_path: str, workdir: str):
        self.multiwfn_path = str(multiwfn_path or "").strip()
        self.workdir = Path(workdir).expanduser().resolve()

    def executable(self) -> str:
        candidate = Path(self.multiwfn_path).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        found = shutil.which(self.multiwfn_path) if self.multiwfn_path else None
        if found:
            return found
        raise FileNotFoundError(f"Multiwfn executable was not found: {self.multiwfn_path or '(not configured)'}")

    def version(self) -> str:
        try:
            result = subprocess.run([self.executable(), "-h"], cwd=str(self.workdir), text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=8, shell=False)
            first = next((line.strip() for line in result.stdout.splitlines() if "Multiwfn" in line), "")
            return first[:200] or "Unknown"
        except Exception:
            return "Unknown"

    @staticmethod
    def _base_name(orca_output_file: str) -> str:
        return Path(orca_output_file).stem

    def expected_paths(self, state_index: int, orca_output_file: str, output_directory: str) -> Dict[str, List[Path]]:
        base = self._base_name(orca_output_file)
        prefix = f"{base}_stateS{state_index}_"
        root = Path(output_directory)
        return {name: [root / (prefix + suffix) for suffix in suffixes] for name, suffixes in ANALYSES.items()}

    def _guarded_unverified(self, analysis: str) -> Dict:
        # TODO(Multiwfn-version): add a command script only after its exact menu
        # route and expected filenames are verified for a supported release.
        return {"status": "Disabled: unverified Multiwfn workflow", "files": [],
                "message": f"No verified Multiwfn command sequence is bundled for {analysis}."}

    def generate_nto_cubes(self, state_index: int, wavefunction_file: str, output_directory: str) -> List[str]:
        raise NotImplementedError(self._guarded_unverified("NTO hole/electron")["message"])

    def generate_difference_density_cube(self, state_index: int, wavefunction_file: str, output_directory: str) -> List[str]:
        raise NotImplementedError(self._guarded_unverified("difference density")["message"])

    def generate_transition_density_cube(self, state_index: int, wavefunction_file: str, output_directory: str) -> List[str]:
        raise NotImplementedError(self._guarded_unverified("transition density")["message"])

    def generate_attachment_detachment_cubes(self, state_index: int, wavefunction_file: str, output_directory: str) -> List[str]:
        raise NotImplementedError(self._guarded_unverified("attachment/detachment")["message"])

    def generate_hole_electron_cubes(self, state_index: int, wavefunction_file: str, output_directory: str) -> List[str]:
        raise NotImplementedError(self._guarded_unverified("hole/electron density")["message"])

    def generate_hole_electron_descriptors(self, state_index: int, wavefunction_file: str, output_directory: str) -> Dict:
        raise NotImplementedError(self._guarded_unverified("hole-electron descriptors")["message"])

    def generate_all_analyses(self, state_index: int, wavefunction_file: str,
                              orca_output_file: str, output_directory: str,
                              associated_files: Optional[Dict[str, str]] = None,
                              force: bool = False) -> Dict:
        output = Path(output_directory).resolve()
        output.mkdir(parents=True, exist_ok=True)
        expected = self.expected_paths(state_index, orca_output_file, str(output))
        results: Dict[str, Dict] = {}
        wavefunction_available = bool(wavefunction_file and Path(wavefunction_file).is_file())
        for analysis, paths in expected.items():
            valid = all((is_cube_file_valid(path) if path.suffix.lower() in {".cube", ".cub"} else path.is_file() and path.stat().st_size > 0) for path in paths)
            if valid and not force:
                results[analysis] = {"status": "Reused existing file", "files": [str(path) for path in paths], "message": "Validated cached output."}
            elif not wavefunction_available:
                results[analysis] = {"status": "Unsupported by available input", "files": [], "message": "No supported wavefunction file was detected."}
            else:
                # Forced regeneration never destroys cached data. Workflows are
                # currently guarded, so valid files remain in place.
                results[analysis] = self._guarded_unverified(analysis)
        metadata = {
            "source_orca_output": str(Path(orca_output_file).resolve()),
            "source_mtime": Path(orca_output_file).stat().st_mtime,
            "associated_files": associated_files or {},
            "associated_mtimes": {key: Path(value).stat().st_mtime for key, value in (associated_files or {}).items() if value and Path(value).is_file()},
            "selected_state": state_index,
            "multiwfn_path": self.multiwfn_path,
            "multiwfn_version": self.version() if self.multiwfn_path else "Not configured",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "forced_regeneration": bool(force),
            "analyses": results,
        }
        metadata_path = output / f"{Path(orca_output_file).stem}_stateS{state_index}_analysis.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (output / "multiwfn.log").write_text(
            "No Multiwfn process was started. Bundled TD-DFT menu workflows remain disabled until verified.\n" +
            "\n".join(f"{name}: {item['status']}" for name, item in results.items()) + "\n", encoding="utf-8")
        metadata["metadata_path"] = str(metadata_path)
        return metadata
