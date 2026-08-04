from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class StageStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    SUBMITTED = "SUBMITTED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SKIPPED = "SKIPPED"


@dataclass
class StageRecord:
    stage_id: str
    status: StageStatus = StageStatus.NOT_STARTED
    input_file: str = ""
    output_file: str = ""
    geometry_file: str = ""
    wavefunction_file: str = ""
    method_signature: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    scheduler_job_id: Optional[str] = None
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    results: Dict = field(default_factory=dict)


def _canon(value) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    return re.sub(r"\s+", "", str(value)).lower()


def method_signature(config, *, include_excited_state: bool = True) -> str:
    """Return the immutable principal-method signature for a workflow stage."""
    method = config.method
    solvent = config.solvent
    fields = [
        method.functional,
        method.dispersion or "none",
        method.basis,
        method.auxiliary_basis or "none",
        "RIJCOSX" if method.rijcosx else "no-RIJCOSX",
        (f"SMD:{solvent.name}" if solvent.smd or solvent.model.upper() == "SMD" else f"{solvent.model}:{solvent.name}") if solvent.enabled else "gas",
        method.relativistic or "none",
        method.ecp or "none",
        method.grid,
        method.scf_convergence,
        method.geometry_convergence,
        ",".join(sorted(method.extra_keywords)) or "no-extra-keywords",
    ]
    if include_excited_state:
        fields.append("TDA" if config.excited_states.use_tda else "TDDFT")
    return "|".join(_canon(item) for item in fields)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def records_to_dict(records: Dict[str, StageRecord]) -> Dict:
    return {key: asdict(value) for key, value in records.items()}
