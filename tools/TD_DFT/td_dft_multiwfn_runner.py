"""Multiwfn runner for excited-state hole/electron and density analyses.

This module provides a reusable, thread-friendly execution layer that:
- ensures a Molden (or GBW) file is available for Multiwfn
- runs Multiwfn with an automated input sequence per excited state
- captures full Multiwfn logs
- locates generated cube files (hole/electron/transition/CDD)
- parses quantitative hole–electron descriptors from the log
- returns a typed result object including warnings and errors

The implementation strives to be robust to different Multiwfn versions and
uses defensive parsing. It runs external commands without shell=True and
supports long timeouts and log capture. The runner itself is UI-agnostic and
should be called from a worker thread by the GUI.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ExcitedStateDensityResult:
    state_index: int
    output_directory: Path
    hole_cube: Optional[Path]
    electron_cube: Optional[Path]
    transition_density_cube: Optional[Path]
    difference_density_cube: Optional[Path]
    log_file: Path
    descriptors: Dict[str, object] = field(default_factory=dict)
    success: bool = False
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


class MultiwfnRunnerError(Exception):
    pass


def ensure_molden_file(calc_dir: Path, base_name: str, gbw_path: Optional[Path] = None, orca_2mkl: Optional[str] = None, timeout: float = 120.0) -> Path:
    """Ensure a Molden file exists for the calculation.

    Returns path to the `.molden.input` file (or raises MultiwfnRunnerError).
    If absent and `orca_2mkl` is provided, runs `orca_2mkl <base> -molden` in
    `calc_dir` to generate it.
    """
    calc_dir = Path(calc_dir)
    molden = calc_dir / f"{base_name}.molden.input"
    if molden.is_file():
        return molden
    # accept common alternate names
    alt = calc_dir / f"{base_name}.molden"
    if alt.is_file():
        return alt
    # try gbw -> Multiwfn supports gbw directly, but ensure path
    if gbw_path:
        gbw = Path(gbw_path)
        if gbw.is_file():
            return gbw
    # try to run orca_2mkl
    if not orca_2mkl:
        raise MultiwfnRunnerError("No Molden file or GBW found and no orca_2mkl provided to generate it.")
    exe = shutil.which(orca_2mkl) or orca_2mkl
    if not exe or not Path(exe).exists():
        raise MultiwfnRunnerError(f"orca_2mkl executable not found: {orca_2mkl}")
    cmd = [str(exe), str(base_name), "-molden"]
    try:
        subprocess.run(cmd, cwd=str(calc_dir), check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        raise MultiwfnRunnerError(f"orca_2mkl failed: {exc}")
    except subprocess.TimeoutExpired:
        raise MultiwfnRunnerError("orca_2mkl timed out while generating Molden file")
    # check again
    if molden.is_file():
        return molden
    if alt.is_file():
        return alt
    raise MultiwfnRunnerError("orca_2mkl did not produce a Molden file as expected")


def _build_batch_input_lines(orca_out: Path, state: int) -> List[str]:
    # The canonical sequence requested by the user (as per instructions).
    seq = [
        "18",
        "1",
        str(orca_out),
        str(state),
        "1",
        "3",
        "-1",
        "10",
        "1",
        "11",
        "1",
        "13",
        "15",
        "0",
        "0",
        "0",
        "q",
    ]
    return [line + "\n" for line in seq]


def _write_log(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_multiwfn_excitation_analysis(
    multiwfn_exe: str,
    orca_out: Path,
    state: int,
    output_dir: Path,
    calc_dir: Optional[Path] = None,
    base_name: Optional[str] = None,
    gbw_path: Optional[Path] = None,
    orca_2mkl: Optional[str] = None,
    timeout: float = 3600.0,
) -> ExcitedStateDensityResult:
    """Run Multiwfn for the given ORCA output and state.

    This function runs Multiwfn with the automated input, captures logs,
    locates generated cube files and parses descriptors. It returns an
    ExcitedStateDensityResult describing outputs and errors. It does not
    interact with Tkinter; callers should run it in a worker thread.
    """
    orca_out = Path(orca_out)
    output_dir = Path(output_dir)
    calc_dir = Path(calc_dir) if calc_dir else orca_out.parent
    base_name = base_name or orca_out.stem

    result = ExcitedStateDensityResult(
        state_index=state,
        output_directory=output_dir,
        hole_cube=None,
        electron_cube=None,
        transition_density_cube=None,
        difference_density_cube=None,
        log_file=output_dir / f"multiwfn_state_{state:03d}.log",
    )

    if not shutil.which(multiwfn_exe) and not Path(multiwfn_exe).exists():
        result.error = f"Multiwfn executable not found: {multiwfn_exe}"
        return result

    try:
        # Ensure molden/gbw availability
        try:
            molden = ensure_molden_file(calc_dir, base_name, gbw_path=gbw_path, orca_2mkl=orca_2mkl, timeout=120)
        except MultiwfnRunnerError as exc:
            # If GBW was provided directly, proceed with it
            result.error = str(exc)
            return result

        # Prepare working directory for this state
        state_dir = output_dir / f"state_{state:03d}"
        state_dir.mkdir(parents=True, exist_ok=True)

        # Multiwfn may write files into the current working directory; run it from state_dir
        batch_lines = _build_batch_input_lines(orca_out.resolve(), state)
        input_text = "".join(batch_lines)

        cmd = [str(shutil.which(multiwfn_exe) or multiwfn_exe)]
        proc = subprocess.Popen(
            cmd,
            cwd=str(state_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            stdout, _ = proc.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate(timeout=30)
            result.error = "Multiwfn timed out"
            _write_log(result.log_file, stdout)
            return result

        _write_log(result.log_file, stdout)

        # Basic fatal error detection
        upper = (stdout or "").upper()
        if "FATAL" in upper or ("ERROR" in upper and "WARNING" not in upper):
            result.error = "Multiwfn reported a fatal error; see the log"
            return result

        # Find generated cube files
        hole = None
        electron = None
        trans = None
        cdd = None
        for p in state_dir.glob("*.cub"):
            name = p.name.lower()
            # find trailing digits
            m = re.search(r"(\d+)\.cub$", name)
            trailing = m.group(1) if m else ""
            if trailing and int(trailing.lstrip("0") or "0") != state:
                # allow different zero-padding but must match integer
                continue
            if "hole" in name and (hole is None):
                hole = p
            if "electron" in name and (electron is None):
                electron = p
            if "trans" in name and (trans is None):
                trans = p
            if "cdd" in name or "difference" in name:
                cdd = p

        # Fallback: accept files that contain the state index anywhere near the end
        if not any((hole, electron, trans, cdd)):
            for p in state_dir.glob("*.cub"):
                name = p.name.lower()
                if f"{state}" in name:
                    if "hole" in name and not hole:
                        hole = p
                    if "electron" in name and not electron:
                        electron = p
                    if "trans" in name and not trans:
                        trans = p
                    if ("cdd" in name or "difference" in name) and not cdd:
                        cdd = p

        result.hole_cube = hole
        result.electron_cube = electron
        result.transition_density_cube = trans
        result.difference_density_cube = cdd

        # Parse descriptors from the log
        descriptors = parse_hole_electron_descriptors(stdout or "")
        result.descriptors = descriptors

        # Validation: require at least hole and electron or transition and cdd
        if not (hole and electron) and not (trans and cdd):
            result.error = "Expected cube files not found after Multiwfn run"
            result.warnings.append(f"State dir contents: {[p.name for p in state_dir.iterdir()]}")
            return result

        result.success = True
        return result

    except Exception as exc:
        result.error = f"Unexpected error: {type(exc).__name__}: {exc}"
        return result


def parse_hole_electron_descriptors(log_text: str) -> Dict[str, object]:
    """Parse quantitative hole/electron descriptors from Multiwfn log text.

    Returns a dict mapping friendly keys to values or "Not reported".
    The parser is intentionally permissive and retains the original matched
    lines under the key '<name>_line'.
    """
    out: Dict[str, object] = {}
    text = str(log_text or "")

    patterns = {
        "integral_hole": r"Integral\s+of\s+hole\s*[:=]?\s*([+-]?[0-9Ee.+-]+)",
        "integral_electron": r"Integral\s+of\s+electron\s*[:=]?\s*([+-]?[0-9Ee.+-]+)",
        "integral_trans": r"Integral\s+of\s+transition\s+density\s*[:=]?\s*([+-]?[0-9Ee.+-]+)",
        "transition_dipole": r"Transition\s+dipole\s+moment\s+\(.*?\)\s*[:=]?\s*([+-]?[0-9Ee.+-]+)\s+([+-]?[0-9Ee.+-]+)\s+([+-]?[0-9Ee.+-]+)",
        "Sm": r"Sm\s*[:=]?\s*([0-9Ee.+-]+)",
        "Sr": r"Sr\s*[:=]?\s*([0-9Ee.+-]+)",
        "DxDyDz": r"Dx,\s*Dy,\s*Dz\s*[:=]?\s*\(?\s*([+-]?[0-9Ee.+-]+)\s*,\s*([+-]?[0-9Ee.+-]+)\s*,\s*([+-]?[0-9Ee.+-]+)\s*\)?",
    }

    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if m.lastindex and m.lastindex > 1:
                vals = [float(g) for g in m.groups()]
                out[key] = vals if len(vals) > 1 else vals[0]
                out[f"{key}_line"] = m.group(0).strip()
            else:
                try:
                    out[key] = float(m.group(1))
                except Exception:
                    out[key] = m.group(1).strip()
                out[f"{key}_line"] = m.group(0).strip()
        else:
            out[key] = "Not reported"

    # Generic captures for named lines that Multiwfn often prints
    generic_names = [
        (r"Hole centroid\s*[:=]?\s*\(?\s*([0-9Ee.+-]+)\s*,\s*([0-9Ee.+-]+)\s*,\s*([0-9Ee.+-]+)\s*\)?", "hole_centroid"),
        (r"Electron centroid\s*[:=]?\s*\(?\s*([0-9Ee.+-]+)\s*,\s*([0-9Ee.+-]+)\s*,\s*([0-9Ee.+-]+)\s*\)?", "electron_centroid"),
        (r"HCT\s*[:=]?\s*([0-9Ee.+-]+)", "HCT"),
        (r"t\s*index\s*[:=]?\s*([0-9Ee.+-]+)", "t_index"),
    ]
    for pat, key in generic_names:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            if m.lastindex and m.lastindex > 1:
                out[key] = [float(g) for g in m.groups()]
            else:
                try:
                    out[key] = float(m.group(1))
                except Exception:
                    out[key] = m.group(1).strip()
            out[f"{key}_line"] = m.group(0).strip()
        else:
            out[key] = "Not reported"

    return out


class MultiwfnTDDFTRunner:
    """Compatibility wrapper used by the TD-DFT UI.

    Provides the small set of methods expected by `td_dft_module.TDDFTWindow`:
    - `executable()` -> path or empty
    - `version()` -> best-effort string
    - `generate_all_analyses(state_index, wavefunction, orca_out, output_dir, associated_files, force)`
      -> returns dict with 'analyses' mapping names to dicts containing status and files
    - `expected_paths(state_index, orca_out, analysis_dir)` -> mapping name->list[str]
    """
    def __init__(self, executable: str, calc_dir: str):
        self._exe = str(executable or "").strip()
        self._calc_dir = Path(calc_dir) if calc_dir else Path.cwd()

    def executable(self) -> str:
        return self._exe

    def version(self) -> str:
        try:
            exe = shutil.which(self._exe) or self._exe
            if not exe:
                return ""
            proc = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=6)
            out = (proc.stdout or "").splitlines()
            if out:
                # return first non-empty line
                for line in out:
                    val = line.strip()
                    if val:
                        return val
            return ""
        except Exception:
            return ""

    def expected_paths(self, state_index: int, orca_out: str, analysis_dir: str) -> Dict[str, List[str]]:
        root = Path(analysis_dir)
        state_dir = root / f"state_{int(state_index):03d}"
        files = {"NTO hole/electron": [], "Difference density": [], "Transition density": [], "Attachment/detachment": [], "Hole/electron density": []}
        if state_dir.is_dir():
            for p in state_dir.glob("*.cub"):
                name = p.name.lower()
                if "hole" in name:
                    files["Hole/electron density"].append(str(p))
                    files["Attachment/detachment"].append(str(p))
                if "electron" in name:
                    files["Hole/electron density"].append(str(p))
                    files["Attachment/detachment"].append(str(p))
                if "trans" in name:
                    files["Transition density"].append(str(p))
                if "cdd" in name or "difference" in name:
                    files["Difference density"].append(str(p))
        # Ensure consistent ordering: attachment then detachment, hole then electron
        return files

    def generate_all_analyses(self, state_index: int, wavefunction: str, orca_out: str, output_dir: str, associated_files: Dict, force: bool) -> Dict:
        analyses = {}
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        multiwfn_exe = self._exe
        calc_dir = Path(associated_files.get("manual") or orca_out).__str__()
        try:
            orca_parent = Path(orca_out).parent
        except Exception:
            orca_parent = self._calc_dir

        gbw = associated_files.get(".gbw") or associated_files.get(".molden.input") or associated_files.get(".molden")
        orca_2mkl = associated_files.get("orca_2mkl") or shutil.which("orca_2mkl")

        # Run Multiwfn for this single state
        res = run_multiwfn_excitation_analysis(
            multiwfn_exe,
            Path(orca_out),
            int(state_index),
            out_root,
            calc_dir=Path(orca_parent),
            base_name=Path(orca_out).stem,
            gbw_path=Path(gbw) if gbw else None,
            orca_2mkl=orca_2mkl,
            timeout=3600.0,
        )

        # Populate analyses mapping following UI labels
        def status_for(r: ExcitedStateDensityResult) -> str:
            if r.success: return "Completed"
            if r.error: return "Failed"
            return "Failed"

        analyses["NTO hole/electron"] = {"status": "Not requested", "files": []}
        analyses["Difference density"] = {"status": status_for(res), "files": [str(res.difference_density_cube)] if res.difference_density_cube else [] , "log": str(res.log_file)}
        analyses["Transition density"] = {"status": status_for(res), "files": [str(res.transition_density_cube)] if res.transition_density_cube else [], "log": str(res.log_file)}
        # Attachment/detachment -> electron/hole mapping: attachment=electron, detachment=hole
        ad_files = []
        if res.electron_cube: ad_files.append(str(res.electron_cube))
        if res.hole_cube: ad_files.append(str(res.hole_cube))
        analyses["Attachment/detachment"] = {"status": status_for(res), "files": ad_files, "log": str(res.log_file)}
        he_files = []
        if res.hole_cube: he_files.append(str(res.hole_cube))
        if res.electron_cube: he_files.append(str(res.electron_cube))
        analyses["Hole/electron density"] = {"status": status_for(res), "files": he_files, "log": str(res.log_file)}
        analyses["Hole-electron descriptors"] = {"status": status_for(res), "files": [], "descriptors": res.descriptors, "log": str(res.log_file)}

        return {"analyses": analyses}

"""Guarded Multiwfn orchestration and cache for TD-DFT post-processing.

This module coordinates non-interactive Multiwfn excited-state density
analysis for ORCA TD-DFT results. It can generate CDD, transition-density,
attachment/detachment, hole/electron cube files, and parse quantitative
hole–electron descriptors into structured outputs.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Dict, Iterable, Iterator, List, Optional, Pattern, Tuple

ANALYSES = {
    "NTO hole/electron": ("NTO_hole.cube", "NTO_electron.cube"),
    "Difference density": ("CDD.cub",),
    "Transition density": ("transdens.cub",),
    "Attachment/detachment": ("hole.cub", "electron.cub"),
    "Hole/electron density": ("hole.cub", "electron.cub"),
    "Hole-electron descriptors": ("descriptors.json",),
}

DEFAULT_MULTIWFN_TIMEOUT = 3600
DEFAULT_MULTIWFN_GRID_QUALITY = 3

DESCRIPTOR_PATTERNS: Dict[str, List[Pattern[str]]] = {
    "Integral of hole": [re.compile(r"Integral of hole\s*[:=]\s*(.+)", re.I)],
    "Integral of electron": [re.compile(r"Integral of electron\s*[:=]\s*(.+)", re.I)],
    "Integral of transition density": [re.compile(r"Integral of transition density\s*[:=]\s*(.+)", re.I)],
    "Transition dipole moment": [re.compile(r"Transition dipole moment.*?([+-]?[0-9Ee.+-]+)\s*([+-]?[0-9Ee.+-]+)\s*([+-]?[0-9Ee.+-]+)", re.I)],
    "Sm index": [re.compile(r"Sm\s*[:=]\s*(.+)", re.I)],
    "Sr index": [re.compile(r"Sr\s*[:=]\s*(.+)", re.I)],
    "Hole centroid": [re.compile(r"Hole centroid\s*[:=]\s*(.+)", re.I)],
    "Electron centroid": [re.compile(r"Electron centroid\s*[:=]\s*(.+)", re.I)],
    "Dx, Dy, Dz": [re.compile(r"Dx\s*[:=]\s*([+-]?[0-9Ee.+-]+).*?Dy\s*[:=]\s*([+-]?[0-9Ee.+-]+).*?Dz\s*[:=]\s*([+-]?[0-9Ee.+-]+)", re.I),
                     re.compile(r"D\s*\(x\)\s*[:=]\s*([+-]?[0-9Ee.+-]+).*?D\s*\(y\).*?([+-]?[0-9Ee.+-]+).*?D\s*\(z\).*?([+-]?[0-9Ee.+-]+)", re.I)],
    "D index": [re.compile(r"D index\s*[:=]\s*(.+)", re.I)],
    "Hole RMSD": [re.compile(r"Hole RMSD\s*[:=]\s*(.+)", re.I)],
    "Electron RMSD": [re.compile(r"Electron RMSD\s*[:=]\s*(.+)", re.I)],
    "Delta-sigma values": [re.compile(r"Delta[- ]sigma values?\s*[:=]\s*(.+)", re.I)],
    "HCT": [re.compile(r"HCT\s*[:=]\s*(.+)", re.I)],
    "H index": [re.compile(r"H index\s*[:=]\s*(.+)", re.I)],
    "t index": [re.compile(r"t index\s*[:=]\s*(.+)", re.I)],
    "Hole delocalization index, HDI": [re.compile(r"Hole delocalization index\s*[:=]\s*(.+)", re.I), re.compile(r"HDI\s*[:=]\s*(.+)", re.I)],
    "Electron delocalization index, EDI": [re.compile(r"Electron delocalization index\s*[:=]\s*(.+)", re.I), re.compile(r"EDI\s*[:=]\s*(.+)", re.I)],
    "Ghost-hunter index": [re.compile(r"Ghost[- ]hunter index\s*[:=]\s*(.+)", re.I)],
    "Excitation energy": [re.compile(r"Excitation energy\s*[:=]\s*(.+)", re.I)],
}

PROMPT_SEQUENCE: List[Tuple[str, Pattern[str], str]] = [
    ("analysis", re.compile(r"(?:electronic excitation|excitation analyses|function\s*\(|enter.*option|Select.*function|choose.*option)", re.I), "18"),
    ("hole_electron_analysis", re.compile(r"(?:hole/electron and transition|hole and electron|hole/electron analyses|hole\s*electron and transition-density)", re.I), "1"),
    ("orca_output", re.compile(r"(?:load.*orca.*output|open.*orca.*output|orad.*output|input file|file.*name)", re.I), "{orca_output}"),
    ("state", re.compile(r"(?:select.*state|state number|choose.*state|enter.*state|please.*state)", re.I), "{state_index}"),
    ("calculate_distributions", re.compile(r"(?:calculate distributions|densit|quantitative descriptors|calculate.*distributions|select.*distribution)", re.I), "1"),
    ("grid_quality", re.compile(r"(?:high quality|quality .*grid|grid.*quality|choose grid|select quality)", re.I), str(DEFAULT_MULTIWFN_GRID_QUALITY)),
    ("suffix", re.compile(r"(?:add.*state number|add.*suffix|include state number|output name|state number.*export)", re.I), "-1"),
    ("export_hole", re.compile(r"(?:export.*hole.*distribution|hole.*distribution|hole.*cube)", re.I), "10"),
    ("export_total_hole", re.compile(r"(?:total hole|export.*total hole)", re.I), "1"),
    ("export_electron", re.compile(r"(?:export.*electron.*distribution|electron.*distribution|electron.*cube)", re.I), "11"),
    ("export_total_electron", re.compile(r"(?:total electron|export.*total electron)", re.I), "1"),
    ("export_transdens", re.compile(r"(?:export.*transition.*density|transition.*density|transdens|transition\s*density)", re.I), "13"),
    ("export_cdd", re.compile(r"(?:export.*charge.*density.*difference|charge.*density.*difference|difference.*density|CDD)", re.I), "15"),
    ("leave_post_processing", re.compile(r"(?:leave post|post[- ]processing|post process|0\)|0\s*$|0\s*\n)", re.I), "0"),
    ("leave_hole_electron_analysis", re.compile(r"(?:leave hole/electron|hole/electron analysis|0\)|0\s*$|0\s*\n)", re.I), "0"),
    ("leave_electron_excitation", re.compile(r"(?:leave electron[- ]excitation|electron excitation|0\)|0\s*$|0\s*\n)", re.I), "0"),
    ("quit", re.compile(r"(?:exit|quit|q\s*$|press.*q)", re.I), "q"),
]


@dataclass
class ExcitedStateDensityResult:
    state_index: int
    output_directory: Path
    hole_cube: Optional[Path] = None
    electron_cube: Optional[Path] = None
    transition_density_cube: Optional[Path] = None
    difference_density_cube: Optional[Path] = None
    log_file: Optional[Path] = None
    descriptors_json: Optional[Path] = None
    descriptors_csv: Optional[Path] = None
    descriptors: Dict[str, Dict[str, str]] = field(default_factory=dict)
    success: bool = False
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Path):
                data[key] = str(value)
        return data


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
        self._process: Optional[subprocess.Popen] = None

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
            result = subprocess.run(
                [self.executable(), "-h"],
                cwd=str(self.workdir),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=8,
                shell=False,
            )
            first = next((line.strip() for line in result.stdout.splitlines() if "Multiwfn" in line), "")
            return first[:200] or "Unknown"
        except Exception:
            return "Unknown"

    @staticmethod
    def _base_name(orca_output_file: str) -> str:
        return Path(orca_output_file).stem

    def expected_paths(self, state_index: int, orca_output_file: str, output_directory: str) -> Dict[str, List[Path]]:
        base = self._base_name(orca_output_file)
        root = Path(output_directory)
        hole = root / f"hole_{state_index:05d}.cub"
        electron = root / f"electron_{state_index:05d}.cub"
        return {
            "NTO hole/electron": [root / f"NTO_hole_{state_index:05d}.cub", root / f"NTO_electron_{state_index:05d}.cub"],
            "Difference density": [root / f"CDD_{state_index:05d}.cub"],
            "Transition density": [root / f"transdens_{state_index:05d}.cub"],
            "Attachment/detachment": [hole, electron],
            "Hole/electron density": [hole, electron],
            "Hole-electron descriptors": [root / f"descriptors_state_{state_index:03d}.json"],
        }

    def _guarded_unverified(self, analysis: str) -> Dict:
        return {"status": "Disabled: unverified Multiwfn workflow", "files": [],
                "message": f"No verified Multiwfn command sequence is bundled for {analysis}."}

    def _search_executable(self, name: str) -> Optional[str]:
        candidate = shutil.which(name)
        if candidate:
            return candidate
        return None

    def _find_orca_2mkl(self) -> str:
        candidates = []
        for name in ("orca_2mkl.exe", "orca_2mkl", "orca2mkl.exe", "orca2mkl"):
            candidates.append(name)
        for candidate in candidates:
            path = self._search_executable(candidate)
            if path:
                return path
        env_paths = [os.environ.get("ORCA_PATH", ""), os.environ.get("ORCA_DIR", ""), os.environ.get("ORCA_HOME", "")]
        for base in env_paths:
            if not base:
                continue
            for name in ("orca_2mkl.exe", "orca_2mkl", "orca2mkl.exe", "orca2mkl"):
                path = Path(base).expanduser() / name
                if path.is_file():
                    return str(path)
        raise FileNotFoundError("orca_2mkl executable was not found on PATH or in ORCA environment variables.")

    def _run_orca_2mkl(self, gbw_file: Path, orca_2mkl_path: Optional[str] = None) -> Path:
        gbw_dir = gbw_file.parent
        basename = gbw_file.stem
        orca_2mkl_exec = orca_2mkl_path or self._find_orca_2mkl()
        command = [orca_2mkl_exec, basename, "-molden"]
        result = subprocess.run(
            command,
            cwd=str(gbw_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            timeout=DEFAULT_MULTIWFN_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"orca_2mkl failed to generate Molden input from {gbw_file}.\n"
                f"Command: {' '.join(command)}\nOutput:\n{result.stdout}"
            )
        molden = gbw_dir / f"{basename}.molden.input"
        if not molden.is_file():
            molden = gbw_dir / f"{basename}.molden"
        if not molden.is_file():
            raise FileNotFoundError("orca_2mkl finished but Molden input was not found.")
        return molden

    def _ensure_wavefunction_file(self, orca_output_file: str, wavefunction_file: Optional[str], associated_files: Optional[Dict[str, str]]) -> Path:
        associated_files = associated_files or {}
        if wavefunction_file:
            candidate = Path(wavefunction_file).expanduser()
            if candidate.is_file():
                return candidate
        for key in (".molden.input", ".molden", ".gbw", ".wfn", ".wfx", ".fchk"):
            candidate = Path(associated_files.get(key, "")).expanduser()
            if candidate.is_file():
                if candidate.suffix.lower() == ".gbw":
                    try:
                        return self._run_orca_2mkl(candidate)
                    except FileNotFoundError:
                        return candidate
                return candidate
        raise FileNotFoundError("No ORCA GBW or Molden wavefunction file was found for Multiwfn analysis.")

    @staticmethod
    def _shallow_copy_or_link(source: Path, destination: Path) -> Path:
        if destination.exists():
            return destination
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(str(source), str(destination))
            return destination
        except Exception:
            try:
                if source.is_file():
                    shutil.copy2(str(source), str(destination))
                    return destination
            except Exception:
                pass
        raise IOError(f"Could not copy or link {source} to {destination}.")

    def _ensure_wavefunction_in_run_dir(self, wavefunction_file: Path, run_dir: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        if wavefunction_file.parent.resolve() == run_dir.resolve():
            return wavefunction_file
        target = run_dir / wavefunction_file.name
        return self._shallow_copy_or_link(wavefunction_file, target)

    def _build_prompt_queue(self, orca_output_file: str, state_index: int) -> List[Tuple[str, Pattern[str], str]]:
        sequence: List[Tuple[str, Pattern[str], str]] = []
        for name, pattern, answer in PROMPT_SEQUENCE:
            answer_text = answer.format(orca_output=str(Path(orca_output_file).resolve()), state_index=state_index)
            sequence.append((name, pattern, answer_text))
        return sequence

    @staticmethod
    def _detect_fatal_error(log_text: str) -> Optional[str]:
        for line in log_text.splitlines():
            text = line.strip()
            if not text:
                continue
            if re.search(r"\b(?:fatal|error|failed|aborted|abnormal|cannot|can not|not possible|invalid|segmentation fault)\b", text, re.I) and not re.search(r"no\s+error|without\s+error|error\s+free", text, re.I):
                return text
        return None

    def _read_subprocess_output(self, process: subprocess.Popen, timeout: int, prompt_queue: List[Tuple[str, Pattern[str], str]]) -> Tuple[int, str, List[Tuple[str, Pattern[str], str]]]:
        queue: "Queue[str]" = Queue()
        log_lines: List[str] = []

        def reader():
            try:
                for line in process.stdout:
                    queue.put(line)
            except Exception:
                pass
            finally:
                if process.stdout:
                    process.stdout.close()

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        start_time = time.time()
        pending = list(prompt_queue)

        while process.poll() is None or not queue.empty():
            try:
                line = queue.get(timeout=0.1)
            except Empty:
                if timeout and time.time() - start_time > timeout:
                    process.kill()
                    raise TimeoutError("Multiwfn analysis timed out.")
                continue
            log_lines.append(line)
            for index, (_name, prompt, answer) in enumerate(pending):
                if prompt.search(line):
                    try:
                        if process.stdin:
                            process.stdin.write(answer + "\n")
                            process.stdin.flush()
                    except Exception:
                        pass
                    pending.pop(index)
                    break
        if process.stdin:
            try:
                process.stdin.close()
            except Exception:
                pass
        returncode = process.wait(timeout=10)
        return returncode, "".join(log_lines), pending

    def cancel(self) -> None:
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
            time.sleep(0.2)
            if self._process.poll() is None:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def _find_generated_cube_files(self, run_dir: Path, state_index: int) -> Dict[str, Optional[Path]]:
        patterns = {
            "hole": re.compile(rf"(^|[_-.])hole[_-.]*0*{state_index}\.cub$", re.I),
            "electron": re.compile(rf"(^|[_-.])electron[_-.]*0*{state_index}\.cub$", re.I),
            "transdens": re.compile(rf"(^|[_-.])transdens?[_-.]*0*{state_index}\.cub$", re.I),
            "cdd": re.compile(rf"(^|[_-.])cdd[_-.]*0*{state_index}\.cub$", re.I),
        }
        found = {key: None for key in patterns}
        for path in run_dir.glob("*.cub"):
            for key, pattern in patterns.items():
                if pattern.search(path.name):
                    if found[key] is None or len(path.name) < len(found[key].name):
                        found[key] = path
        for path in run_dir.glob("*.cube"):
            for key, pattern in patterns.items():
                if pattern.search(path.name):
                    if found[key] is None or len(path.name) < len(found[key].name):
                        found[key] = path
        return found

    def _parse_descriptors(self, log_text: str) -> Dict[str, Dict[str, str]]:
        descriptors: Dict[str, Dict[str, str]] = {}
        for line in log_text.splitlines():
            text = line.strip()
            if not text:
                continue
            for name, patterns in DESCRIPTOR_PATTERNS.items():
                if name in descriptors:
                    continue
                for pattern in patterns:
                    match = pattern.search(text)
                    if match:
                        descriptors[name] = {
                            "value": " ".join(match.groups()).strip() if match.groups() else text,
                            "raw_line": text,
                        }
                        break
        return descriptors

    def _write_descriptors_files(self, descriptors: Dict[str, Dict[str, str]], output_dir: Path, state_index: int) -> Tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"descriptors_state_{state_index:03d}.json"
        csv_path = output_dir / f"descriptors_state_{state_index:03d}.csv"
        json_path.write_text(json.dumps(descriptors, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["descriptor", "value", "raw_line"])
            for name, data in sorted(descriptors.items()):
                writer.writerow([name, data["value"], data["raw_line"]])
        return json_path, csv_path

    def _state_status(self, cube_path: Optional[Path]) -> Tuple[str, List[str], str]:
        if cube_path and cube_path.is_file():
            return "Completed", [str(cube_path)], ""
        return "Failed", [], "Generated file was not found."

    def _bundle_files(self, files: Iterable[Optional[Path]]) -> List[str]:
        return [str(path) for path in files if path is not None]

    def _run_batch(self, wavefunction: Path, run_dir: Path, answers: Iterable[object], timeout: int) -> str:
        command = [self.executable(), str(wavefunction)]
        process_env = os.environ.copy()
        process_env.setdefault("Multiwfnpath", str(Path(command[0]).resolve().parent))
        process = subprocess.Popen(
            command,
            cwd=str(run_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            env=process_env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._process = process
        input_text = "\n".join(str(answer) for answer in answers) + "\n"
        try:
            output, _ = process.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=30)
            raise TimeoutError("Multiwfn NTO generation timed out.")
        if process.returncode != 0:
            fatal = self._detect_fatal_error(output or "")
            raise RuntimeError(fatal or f"Multiwfn exited with return code {process.returncode}.")
        return output or ""

    def _generate_nto_cubes(
        self,
        orca_output: Path,
        wavefunction: Path,
        state_index: int,
        output_dir: Path,
        timeout: int,
    ) -> Tuple[Path, Path, Path]:
        """Generate the dominant NTO hole/electron pair for one excited state."""
        nto_molden = output_dir / f"NTO_state_{state_index:03d}.molden"
        nto_log = output_dir / f"multiwfn_nto_state_{state_index:03d}.log"
        generation_log = self._run_batch(
            wavefunction,
            output_dir,
            (18, 6, str(orca_output), state_index, 1, str(nto_molden), 0, "q"),
            timeout,
        )
        nto_log.write_text(generation_log, encoding="utf-8")
        if not nto_molden.is_file() or nto_molden.stat().st_size < 128:
            raise RuntimeError("Multiwfn did not create the state-specific NTO Molden file.")

        occupied = re.search(r"Orbitals from 1 to\s+(\d+) are occupied", generation_log, re.I)
        if not occupied:
            raise RuntimeError("Could not identify the dominant NTO hole/electron orbital indices.")
        hole_index = int(occupied.group(1))
        electron_index = hole_index + 1
        export_log = self._run_batch(
            nto_molden,
            output_dir,
            (200, 3, f"{hole_index},{electron_index}", DEFAULT_MULTIWFN_GRID_QUALITY, 1, 0, "q"),
            timeout,
        )
        with nto_log.open("a", encoding="utf-8") as handle:
            handle.write("\n\n=== NTO cube export ===\n" + export_log)

        raw_hole = output_dir / f"orb{hole_index:06d}.cub"
        raw_electron = output_dir / f"orb{electron_index:06d}.cub"
        hole = output_dir / f"NTO_hole_{state_index:05d}.cub"
        electron = output_dir / f"NTO_electron_{state_index:05d}.cub"
        if not raw_hole.is_file() or not raw_electron.is_file():
            raise RuntimeError("Multiwfn did not export both dominant NTO cube files.")
        for source, target in ((raw_hole, hole), (raw_electron, electron)):
            if target.exists():
                target.unlink()
            source.replace(target)
        return hole, electron, nto_log

    def run_multiwfn_excitation_analysis(
        self,
        orca_output_file: str,
        state_index: int,
        run_dir: str,
        associated_files: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_MULTIWFN_TIMEOUT,
    ) -> ExcitedStateDensityResult:
        output_dir = Path(run_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        orca_output = Path(orca_output_file).expanduser().resolve()
        if not orca_output.is_file():
            raise FileNotFoundError(f"ORCA output file was not found: {orca_output}")
        wavefunction = self._ensure_wavefunction_file(
            str(orca_output), None, associated_files
        )
        wavefunction = self._ensure_wavefunction_in_run_dir(wavefunction, output_dir)

        log_path = output_dir / f"multiwfn_state_{state_index:03d}.log"
        # Multiwfn expects the wavefunction as its command-line input.  Starting
        # it without this argument only opens the main menu and makes the first
        # scripted answer get interpreted as a filename on many releases.
        command = [self.executable(), str(wavefunction)]
        process_env = os.environ.copy()
        # A run-specific working directory normally has no settings.ini. Point
        # Multiwfn at its installation directory so it does not insert the
        # interactive "Press ENTER" prompt and shift every scripted answer.
        process_env.setdefault("Multiwfnpath", str(Path(command[0]).resolve().parent))
        self._process = subprocess.Popen(
            command,
            cwd=str(output_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
            env=process_env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Prompts are not consistently newline-terminated on Windows, so a
        # line-oriented prompt watcher can deadlock. Multiwfn supports feeding
        # the complete menu route through standard input.
        batch_input = "".join(_build_batch_input_lines(orca_output, state_index))
        try:
            log_text, _ = self._process.communicate(input=batch_input, timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            log_text, _ = self._process.communicate(timeout=30)
            log_path.write_text(log_text or "", encoding="utf-8")
            raise TimeoutError("Multiwfn analysis timed out.")
        return_code = self._process.returncode
        log_path.write_text(log_text, encoding="utf-8")

        fatal = self._detect_fatal_error(log_text)
        if return_code != 0 and not fatal:
            fatal = f"Multiwfn exited with return code {return_code}."

        file_map = self._find_generated_cube_files(output_dir, state_index)
        descriptors = self._parse_descriptors(log_text)
        descriptor_json, descriptor_csv = self._write_descriptors_files(descriptors, output_dir, state_index)

        success = True
        result = ExcitedStateDensityResult(
            state_index=state_index,
            output_directory=output_dir,
            hole_cube=file_map["hole"],
            electron_cube=file_map["electron"],
            transition_density_cube=file_map["transdens"],
            difference_density_cube=file_map["cdd"],
            log_file=log_path,
            descriptors_json=descriptor_json,
            descriptors_csv=descriptor_csv,
            descriptors=descriptors,
            warnings=[],
        )
        if fatal:
            success = False
            result.error = fatal
        if not result.hole_cube or not result.electron_cube:
            success = False
            result.warnings.append("Hole/electron cubes were not both produced.")
        if not result.transition_density_cube:
            success = False
            result.warnings.append("Transition-density cube was not generated.")
        if not result.difference_density_cube:
            success = False
            result.warnings.append("Difference-density cube was not generated.")
        result.success = success
        return result

    def _unsupported_analysis_metadata(
        self,
        state_index: int,
        orca_output_file: str,
        output_directory: str,
        associated_files: Optional[Dict[str, str]],
        message: str,
    ) -> Dict:
        output = Path(output_directory).resolve()
        output.mkdir(parents=True, exist_ok=True)
        metadata = {
            "source_orca_output": str(Path(orca_output_file).resolve()),
            "source_mtime": Path(orca_output_file).stat().st_mtime,
            "associated_files": associated_files or {},
            "selected_state": state_index,
            "multiwfn_path": self.multiwfn_path,
            "multiwfn_version": self.version() if self.multiwfn_path else "Not configured",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "forced_regeneration": False,
            "success": False,
            "error": message,
            "warnings": [message],
            "analyses": {
                "Difference density": {"status": "Unsupported by available input", "files": [], "message": message},
                "Transition density": {"status": "Unsupported by available input", "files": [], "message": message},
                "Attachment/detachment": {"status": "Unsupported by available input", "files": [], "message": message},
                "Hole/electron density": {"status": "Unsupported by available input", "files": [], "message": message},
                "Hole-electron descriptors": {"status": "Unsupported by available input", "files": [], "message": message},
            },
            "descriptors": {},
            "log_file": "",
            "descriptor_json": "",
            "descriptor_csv": "",
        }
        metadata_path = output / f"analysis_state_{state_index:03d}.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["metadata_path"] = str(metadata_path)
        (output / "multiwfn.log").write_text(message + "\n", encoding="utf-8")
        return metadata

    def generate_all_analyses(
        self,
        state_index: int,
        wavefunction_file: str,
        orca_output_file: str,
        output_directory: str,
        associated_files: Optional[Dict[str, str]] = None,
        force: bool = False,
    ) -> Dict:
        output = Path(output_directory).resolve()
        output.mkdir(parents=True, exist_ok=True)
        if not self.multiwfn_path:
            return self._unsupported_analysis_metadata(
                state_index,
                orca_output_file,
                str(output),
                associated_files,
                "Multiwfn executable was not configured.",
            )
        try:
            analysis_result = self.run_multiwfn_excitation_analysis(
                orca_output_file=orca_output_file,
                state_index=state_index,
                run_dir=str(output),
                associated_files=associated_files,
                timeout=DEFAULT_MULTIWFN_TIMEOUT,
            )
        except FileNotFoundError as exc:
            return self._unsupported_analysis_metadata(
                state_index,
                orca_output_file,
                str(output),
                associated_files,
                str(exc),
            )

        results: Dict[str, Dict] = {}
        try:
            # Prefer Molden/GBW resolution over the UI's generic .wfx/.wfn
            # selection: Multiwfn requires basis-function information for NTOs.
            wavefunction = self._ensure_wavefunction_file(
                orca_output_file, None, associated_files
            )
            wavefunction = self._ensure_wavefunction_in_run_dir(wavefunction, output)
            nto_hole, nto_electron, nto_log = self._generate_nto_cubes(
                Path(orca_output_file).resolve(), wavefunction, state_index, output,
                DEFAULT_MULTIWFN_TIMEOUT,
            )
            results["NTO hole/electron"] = {
                "status": "Completed",
                "files": [str(nto_hole), str(nto_electron)],
                "log": str(nto_log),
                "message": "Dominant natural-transition-orbital hole/electron pair.",
            }
        except Exception as exc:
            results["NTO hole/electron"] = {
                "status": "Failed",
                "files": [],
                "message": str(exc),
            }
        files_for_attachment = self._bundle_files([analysis_result.hole_cube, analysis_result.electron_cube])
        files_for_difference = self._bundle_files([analysis_result.difference_density_cube])
        files_for_transition = self._bundle_files([analysis_result.transition_density_cube])
        descriptor_files = [str(analysis_result.descriptors_json)] if analysis_result.descriptors_json else []

        results["Difference density"] = {
            "status": "Completed" if analysis_result.difference_density_cube else "Failed",
            "files": files_for_difference,
            "message": "CDD = electron distribution - hole distribution.",
        }
        results["Transition density"] = {
            "status": "Completed" if analysis_result.transition_density_cube else "Failed",
            "files": files_for_transition,
            "message": "Transition density cube generated by Multiwfn.",
        }
        results["Attachment/detachment"] = {
            "status": "Completed" if files_for_attachment else "Failed",
            "files": files_for_attachment,
            "message": "Attachment = electron and detachment = hole distributions.",
        }
        results["Hole/electron density"] = {
            "status": "Completed" if files_for_attachment else "Failed",
            "files": files_for_attachment,
            "message": "Hole = detachment, Electron = attachment.",
        }
        results["Hole-electron descriptors"] = {
            "status": "Completed" if analysis_result.descriptors else "Failed",
            "files": descriptor_files,
            "message": "Parsed quantitative hole–electron descriptors from the Multiwfn log.",
        }

        metadata = {
            "source_orca_output": str(Path(orca_output_file).resolve()),
            "source_mtime": Path(orca_output_file).stat().st_mtime,
            "associated_files": associated_files or {},
            "selected_state": state_index,
            "multiwfn_path": self.multiwfn_path,
            "multiwfn_version": self.version() if self.multiwfn_path else "Not configured",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "forced_regeneration": bool(force),
            "success": analysis_result.success,
            "error": analysis_result.error,
            "warnings": analysis_result.warnings,
            "analyses": results,
            "descriptors": analysis_result.descriptors,
            "log_file": str(analysis_result.log_file) if analysis_result.log_file else "",
            "descriptor_json": str(analysis_result.descriptors_json) if analysis_result.descriptors_json else "",
            "descriptor_csv": str(analysis_result.descriptors_csv) if analysis_result.descriptors_csv else "",
        }

        metadata_path = output / f"analysis_state_{state_index:03d}.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        metadata["metadata_path"] = str(metadata_path)
        return metadata
