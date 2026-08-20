from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import json


@dataclass
class SystemConfig:
    name: str
    charge: int
    multiplicity: int
    initial_xyz: str


@dataclass
class OrcaConfig:
    executable: str
    version: str = ""


@dataclass
class MethodConfig:
    functional: str
    basis: str
    auxiliary_basis: str = ""
    dispersion: str = ""
    rijcosx: bool = True
    grid: str = "DefGrid2"
    scf_convergence: str = "TightSCF"
    geometry_convergence: str = "TightOpt"
    excited_state_geometry_convergence: str = ""
    relativistic: str = ""
    ecp: str = ""
    extra_keywords: List[str] = field(default_factory=list)


@dataclass
class ExcitedStatesConfig:
    use_tda: bool = True
    nroots: int = 10
    optimization_nroots: int = 5
    target_root: int = 1
    target_multiplicity: str = "singlet"
    maxdim: int = 10
    maxiter: int = 300
    request_nto: bool = True
    selection_rule: str = "user_selected"


@dataclass
class SolventConfig:
    enabled: bool = False
    model: str = "CPCM"
    name: str = ""
    smd: bool = False


@dataclass
class FrequencyConfig:
    enabled: bool = True
    reject_large_imaginary_modes: bool = True
    imaginary_frequency_threshold_cm1: float = -30.0
    allow_continue_after_large_imaginary: bool = False


@dataclass
class ResourcesConfig:
    nprocs: int = 4
    maxcore_mb: int = 2000


@dataclass
class ExecutionConfig:
    mode: str = "local"
    scheduler: str = "slurm"
    submit_automatically: bool = False
    use_separate_jobs: bool = True


@dataclass
class SchedulerConfig:
    partition: str = "compute"
    account: Optional[str] = None
    nodes: int = 1
    ntasks: int = 1
    memory: str = "4G"
    walltime: Dict[str, str] = field(default_factory=lambda: {
        "s0_opt": "24:00:00", "s0_freq": "24:00:00", "absorption": "04:00:00",
        "s1_opt": "48:00:00", "emission": "04:00:00",
    })


@dataclass
class GeometryConfig:
    constraints_file: Optional[str] = None
    freeze_heavy: bool = False
    freeze_all: bool = False
    excited_state_starting_geometries: List[str] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    system: SystemConfig
    orca: OrcaConfig
    method: MethodConfig
    excited_states: ExcitedStatesConfig = field(default_factory=ExcitedStatesConfig)
    solvent: SolventConfig = field(default_factory=SolventConfig)
    frequency: FrequencyConfig = field(default_factory=FrequencyConfig)
    resources: ResourcesConfig = field(default_factory=ResourcesConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    geometry: GeometryConfig = field(default_factory=GeometryConfig)

    def validate(self) -> None:
        if not self.system.name.strip():
            raise ValueError("system.name is required.")
        if self.system.multiplicity < 1:
            raise ValueError("system.multiplicity must be positive.")
        if not self.method.functional.strip() or not self.method.basis.strip():
            raise ValueError("method.functional and method.basis are required.")
        if self.excited_states.nroots < 1:
            raise ValueError("excited_states.nroots must be positive.")
        if self.excited_states.optimization_nroots < 1:
            raise ValueError("excited_states.optimization_nroots must be positive.")
        if not 1 <= self.excited_states.target_root <= self.excited_states.nroots:
            raise ValueError("target_root must be between 1 and nroots.")
        if self.excited_states.maxdim < 1 or self.excited_states.maxiter < 1:
            raise ValueError("excited-state MaxDim and MaxIter must be positive.")
        if self.excited_states.target_multiplicity.lower() not in {"singlet", "triplet"}:
            raise ValueError("target_multiplicity must be singlet or triplet.")
        if self.resources.nprocs < 1 or self.resources.maxcore_mb < 1:
            raise ValueError("resources must be positive.")
        if self.execution.mode not in {"local", "scheduler"}:
            raise ValueError("execution.mode must be local or scheduler.")
        if self.execution.mode == "scheduler" and self.execution.scheduler != "slurm":
            raise ValueError("Only the tested SLURM scheduler is currently supported.")
        if self.solvent.enabled and (not self.solvent.model.strip() or not self.solvent.name.strip()):
            raise ValueError("Enabled solvent requires model and name.")
        if self.solvent.enabled and self.solvent.model.upper() not in {"CPCM", "SMD"}:
            raise ValueError("The strict workflow currently supports only validated CPCM/SMD solvent generation.")
        if self.geometry.constraints_file:
            raise ValueError(
                "External geometry-constraint files are not emitted automatically yet; "
                "no unverified ORCA ConstraintsFile syntax will be generated."
            )
        if self.geometry.freeze_heavy and self.geometry.freeze_all:
            raise ValueError("Select either freeze_heavy or freeze_all, not both.")


def _construct(cls, payload):
    return cls(**(payload or {}))


def load_config(path: str) -> WorkflowConfig:
    try:
        import yaml
    except ImportError:
        yaml = None
    source = Path(path).expanduser().resolve()
    text = source.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        payload = json.loads(text)
    else:
        payload = (yaml.safe_load(text) if yaml is not None else _minimal_yaml_load(text)) or {}
    cfg = WorkflowConfig(
        system=_construct(SystemConfig, payload.get("system")),
        orca=_construct(OrcaConfig, payload.get("orca")),
        method=_construct(MethodConfig, payload.get("method")),
        excited_states=_construct(ExcitedStatesConfig, payload.get("excited_states")),
        solvent=_construct(SolventConfig, payload.get("solvent")),
        frequency=_construct(FrequencyConfig, payload.get("frequency")),
        resources=_construct(ResourcesConfig, payload.get("resources")),
        execution=_construct(ExecutionConfig, payload.get("execution")),
        scheduler=_construct(SchedulerConfig, payload.get("scheduler")),
        geometry=_construct(GeometryConfig, payload.get("geometry")),
    )
    initial = Path(cfg.system.initial_xyz).expanduser()
    if not initial.is_absolute():
        cfg.system.initial_xyz = str((source.parent / initial).resolve())
    cfg.validate()
    return cfg


def _yaml_scalar(value: str):
    value = value.strip()
    if not value:
        return {}
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith(("[", "{")):
        return json.loads(value.replace("'", '"'))
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    try:
        return float(value) if any(char in value for char in ".eE") else int(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> Dict:
    """Read the mapping-only YAML subset used by the bundled template.

    PyYAML remains preferred. This fallback keeps packaged/offline installations
    usable and deliberately rejects list-item and advanced YAML syntax.
    """
    root: Dict = {}
    stack = [(-1, root)]
    for number, raw in enumerate(text.splitlines(), 1):
        clean = raw.split(" #", 1)[0].rstrip()
        if not clean.strip() or clean.lstrip().startswith("#"):
            continue
        if clean.lstrip().startswith("-"):
            raise ValueError(f"YAML list-item syntax requires PyYAML (line {number}); use an inline list instead.")
        indent = len(clean) - len(clean.lstrip(" "))
        if "\t" in raw[:indent]:
            raise ValueError(f"Tabs are not allowed in YAML indentation (line {number}).")
        if ":" not in clean:
            raise ValueError(f"Expected a YAML key/value mapping on line {number}.")
        key, value = clean.strip().split(":", 1)
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        parsed = _yaml_scalar(value)
        parent[key.strip()] = parsed
        if parsed == {}:
            stack.append((indent, parsed))
    return root


EXAMPLE_CONFIG = """system:
  name: molecule
  charge: 0
  multiplicity: 1
  initial_xyz: input/initial_geometry.xyz
orca:
  executable: /path/to/orca
  version: "6.0.1"
method:
  functional: B3LYP
  basis: def2-SVP
  auxiliary_basis: def2/J
  dispersion: D3BJ
  rijcosx: true
  grid: DefGrid2
  scf_convergence: TightSCF
  geometry_convergence: TightOpt
  excited_state_geometry_convergence: ""
excited_states:
  use_tda: true
  nroots: 10
  optimization_nroots: 5
  target_root: 1
  target_multiplicity: singlet
  maxdim: 10
  maxiter: 300
  request_nto: true
  selection_rule: user_selected
solvent:
  enabled: true
  model: CPCM
  name: chloroform
  smd: true
frequency:
  enabled: true
  reject_large_imaginary_modes: true
  imaginary_frequency_threshold_cm1: -30
resources:
  nprocs: 4
  maxcore_mb: 2000
execution:
  mode: local
  scheduler: slurm
  submit_automatically: false
  use_separate_jobs: true
scheduler:
  partition: compute
  account: null
  nodes: 1
  ntasks: 4
  memory: 8G
  walltime:
    s0_opt: "24:00:00"
    s0_freq: "24:00:00"
    absorption: "04:00:00"
    s1_opt: "48:00:00"
    emission: "04:00:00"
geometry:
  constraints_file: null
  excited_state_starting_geometries: []
"""


def write_example_config(path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    return target


def save_config(config: WorkflowConfig, path: str) -> Path:
    """Write JSON-compatible YAML without requiring a YAML serializer."""
    config.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    return target
