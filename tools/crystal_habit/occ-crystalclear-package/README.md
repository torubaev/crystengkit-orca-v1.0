# OCC CrystalClear solvent-comparison workflow

This folder contains a standalone official OCC v0.9.7 Windows installation and a reusable launcher for equilibrium (Wulff) crystal morphology calculations. It does not modify CrystalExplorer and it is not CrystalGrower kinetic Monte Carlo.

## Installed executable

`occ-0.9.7-windows-x86_64\bin\occ.exe`

Version verified: `occ 0.9.7 (c9803d157)`.

OCC requires `OCC_DATA_PATH` to point to `occ-0.9.7-windows-x86_64\share\occ`. The installer configured that user environment variable, and `Run-CrystalClear.ps1` also sets it for every run so a newly opened shell is not required.

## Run a solvent comparison

From PowerShell (the first line changes policy only for the current shell, because this PC currently blocks unsigned local scripts):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Set-Location "$HOME\Documents\OCC-CrystalClear"
.\Run-CrystalClear.ps1 -CifPath "C:\path\crystal.cif" -Solvents water,ethanol,acetone -Model ce-1p -Radius 4.1 -SurfaceDMin 1.0 -OutputDirectory "$HOME\Documents\OCC-CrystalClear\runs"
```

`-SurfaceDMin` is preferred in OCC v0.9.7 because a fixed facet count can split a Friedel pair. To reproduce the older published-style syntax, replace `-SurfaceDMin 1.0` with `-SurfaceEnergies 10`.

Use `-PlanOnly` to print the exact OCC commands without starting calculations. Each real run creates a timestamped parent directory and never overwrites a previous run.

## Outputs

Each solvent has its own folder containing:

- `input.cif`, `command.txt`, `occ.log`, and `exit_code.txt` for provenance.
- `*_cg_results.json` with molecular, interaction, solvation, and surface-cut results.
- `*.gmf` with Miller indices, selected offsets, and equilibrium facet energies.
- `*.ply` with the Wulff morphology mesh.
- `facet-energies.csv` for direct spreadsheet analysis.
- Cached `.owf.json`, surface JSON, and monomer-energy files that make exact reruns diagnosable.

The parent folder contains `run-manifest.json` and `facet-energy-comparison.csv`, which stacks facet energies for all solvents.

## Visualisation

Open a PLY file in ParaView, MeshLab, or Blender. If `.ply` is associated with a viewer, use:

```powershell
.\View-Morphology.ps1 -PlyPath ".\runs\RUN\water\crystal_water.ply"
```

The PLY is the equilibrium Wulff morphology. The GMF and CSV files contain the facet energies used to construct it.

## Verified example

`example\water_ce-1p` is an actual calculation using OCC's official `examples\external_energy\acenaphthene.cif`:

```text
occ --threads=4 --verbosity=2 cg acenaphthene.cif --model=ce-1p --solvent=water --solvation-model=smd --radius=4.1 --surface-energies=10
```

It completed with exit code 0 and the log marker `A job well done`. OCC read the CIF, converged gas and SMD-water B3LYP/def2-SVP wavefunctions for two unique molecules, evaluated 10 unique dimers, converged the lattice energy, calculated solvated and vacuum facet energies, and wrote GMF plus ASCII PLY morphology files.

Surface-cut dipole/discrepancy warnings are preserved in the example log; they are scientific warnings for this test structure, not an installation failure.

