# GUI control reference

## ORCA Input Builder

- **Browse**: load a supported structure, ORCA input, or ORCA/Gaussian output.
- **Structure preview**: inspect imported geometry and, for dimers, fragment assignment.
- **Calculation setup**: program, solvent, functional, basis, dispersion, charge, multiplicity, grid, and SCF options.
- **Calculation targets**: single point, optimization, frequencies, ESP/MEP, NMR, TD-DFT, constraints, and intermolecular interaction workflow.
- **Show input**: display the generated input or the exact input currently being executed.
- **Job monitor**: live ORCA text, estimated stage progress, and elapsed time.
- **Save input file**: save editable generated input with a descriptive suggested name.
- **Add to Queue / Queue Jobs**: maintain and run named persistent queues sequentially.
- **Generate WFN/WFX**: use `orca_2aim` with matching completed `.out` and `.gbw` files.
- **Stop job / Open .out / Open folder / Show summary / Ask AI about progress / Clear monitor**: monitor actions.
- **Settings**: executable paths, helper scripts, Python commands, and browser AI selection.

## TD-DFT

- **Input tab**: TD-DFT/TDA method, manifold, roots, target root, vertical excitation, excited-state optimization, and frequencies.
- **Show ORCA Block**: validate and synchronize one `%tddft` block with the Builder.
- **Post-processing tab**: load completed absorption output or prepare emission sequence.
- **Refresh files / Replace wavefunction**: detect or select associated files.
- **Generate all analyses / Regenerate package**: prepare selected-state artifacts and validated NTO cubes.
- **Display mode**: UV-Vis, NTO hole/electron, and available volumetric results.
- **Display / Reset camera / Save screenshot / Export cubes**: visualization controls.

## Analysis tools

- **HOMO-LUMO**: orbital-energy diagrams, ORCA MO cubes, surface viewer, saved tiles, and contact sheets.
- **ESP/VisMap**: density/ESP cube generation, mapped surface, extrema, ranges, and figure export.
- **NCI Plotter**: Multiwfn RDG/sign(lambda2)rho grids, NCI surface settings, and NCI + QTAIM overlay launch.
- **QTAIM**: Multiwfn critical points and paths, CP filters, energy labels when available, and visualization settings.
- **NCI + QTAIM Overlay**: combined molecule, NCI surface, critical points, and bond paths.

## Hidden developer shortcut

`Ctrl+R` restarts the active primary tool with the same interpreter and arguments. It is blocked during active ORCA jobs/queues, MO rendering, NCI generation, and QTAIM processing.
