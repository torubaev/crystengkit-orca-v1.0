# Strict ORCA TD-DFT workflow

The strict workflow is an independent orchestration layer. It preserves the
existing TD-DFT setup, post-processing, NTO, and cube-viewer behavior.

Create a configuration template:

```powershell
python -m TD_DFT.workflow.cli example-config config.yaml
```

Put the `tools` directory on `PYTHONPATH`, edit `config.yaml`, then prepare or
run a project:

```powershell
python -m TD_DFT.workflow.cli prepare config.yaml project
python -m TD_DFT.workflow.cli run config.yaml project
```

Generate dependency-aware SLURM files without submitting them:

```powershell
python -m TD_DFT.workflow.cli slurm config.yaml project
```

Explicitly submit the generated jobs with `afterok` dependencies:

```powershell
python -m TD_DFT.workflow.cli submit config.yaml project
```

The pipeline is strictly ordered as S0 optimization, optional S0 frequency,
absorption, excited-state optimization, and emission. Every downstream stage
requires validated normal termination, required geometry and GBW artifacts,
and the expected canonical method signature. A large imaginary frequency puts
the frequency stage into `NEEDS_REVIEW` unless continuation is explicitly
allowed. Existing completed calculations are never silently replaced; failed
or interrupted files are copied into `restarts/` before regeneration.

The generated `workflow_status.json` is the authoritative execution state.
Traceable CSV/JSON summaries and file hashes are written under `results/`.
SLURM submission is intentionally not automatic unless a later UI action
explicitly requests external submission.

## TD-DFT workspace

Builder and use **Run complete workflow...**. Functional, basis, dispersion,
Normally no command line is needed. Select **TD-DFT** in the Builder's top
navigation and use **Run complete workflow...**. Functional, basis, dispersion,
grid, solvent, charge, multiplicity, constraints, geometry, and ORCA path come
from the Builder. Roots, target state, TDA/TD-DFT, MaxDim, and MaxIter come from
the TD-DFT page.

Every complete workflow starts from the geometry currently loaded in Builder
and creates all stages inside the selected project directory. External `.out`
drop-in continuation is disabled so a geometry or wavefunction from another
molecule cannot enter the workflow. External outputs may still be loaded in
Post-processing for analysis and visualization only.
