# Files and folders reference

| Item | Purpose | Important relationship |
|---|---|---|
| `.cif`, `.xyz`, `.mol`, `.sdf`, `.sd` | Structure input | Inspect chemistry, disorder, hydrogen atoms, charge, and fragments before calculation. |
| `.inp` | ORCA input | Basename controls many ORCA companion filenames. Do not overwrite completed jobs casually. |
| `.out` | Text output | Normal termination does not by itself prove scientific validity. |
| `.gbw` | ORCA binary wavefunction/orbitals | Keep beside matching `.out`; required for ORCA plotting, WFN/WFX conversion, and TD-DFT NTO generation. |
| `.wfn`, `.wfx` | Wavefunction analysis file | Used by ESP, NCI, and QTAIM workflows. |
| `.fchk` | Formatted checkpoint | Accepted by ESP/VisMap where supported. |
| `.cube`, `.cub` | Volumetric grid | Density, ESP, MO, NCI, transition-density, or NTO content depends on its generating workflow. |
| `.hess`, `.engrad`, trajectory `.xyz` | ORCA optimization/frequency companions | Preserve with the calculation when restarts or detailed analysis may be needed. |
| queue JSON | Named Builder queue state | Contains input paths and execution status; inputs themselves remain separate files. |
| `TDDFT_analysis/` | TD-DFT post-processing root | Shared spectra at root; selected-state artifacts under `Sn/`. |
| project summary | Generated computational draft | Verify every setting, value, unit, sign, and claim against source input/output. |

Associated ORCA files should normally share a basename and directory. Copying only the `.out` often makes orbital, wavefunction, cube, or NTO operations unavailable.
