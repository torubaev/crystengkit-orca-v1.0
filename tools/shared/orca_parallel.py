"""Detect whether the local ORCA installation can launch parallel workers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_mpi_launcher() -> str:
    """Return the local MPI launcher path, including a newly installed MS-MPI."""
    found = shutil.which("mpiexec")
    if found:
        return found
    if os.name == "nt":
        candidates = [
            os.environ.get("MSMPI_BIN", ""),
            str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft MPI" / "Bin"),
        ]
        for directory in candidates:
            executable = Path(directory) / "mpiexec.exe" if directory else None
            if executable and executable.is_file():
                return str(executable)
    return ""


def default_orca_nprocs(parallel_processes: int = 4) -> int:
    """Use parallel defaults only when an MPI launcher is actually available."""
    return parallel_processes if find_mpi_launcher() else 1


def add_mpi_to_path(environment: dict[str, str]) -> dict[str, str]:
    """Return an environment that can invoke a detected MPI launcher by name."""
    env = dict(environment)
    launcher = find_mpi_launcher()
    if not launcher:
        return env
    mpi_dir = str(Path(launcher).resolve().parent)
    current = env.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    if not any(os.path.normcase(part) == os.path.normcase(mpi_dir) for part in parts):
        env["PATH"] = (current + os.pathsep if current else "") + mpi_dir
    return env
