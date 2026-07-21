# TD-DFT module

## Default NTO preparation

- Every Builder and standalone TD-DFT/TDA block now includes `DoNTO true` and
  `NTOThresh 1e-4`; omitting `NTOStates` requests every calculated state.
- Legacy saved `print_ntos: false` values are migrated to the required enabled
  behavior.

## Builder-owned excited-state jobs

- TD-DFT now sends structured calculation-step settings alongside its validated
  `%tddft` fragment.
- The Builder derives verified `Opt` and `Freq` job keywords from those settings;
  the module emits `IRoot` and `IRootMult` for the selected target state.
- Excited-state optimization and frequency controls are enabled with automatic
  vertical-excitation and optimization dependencies.
- Builder-owned functional, basis, solvent, charge, and multiplicity are shown
  read-only in the independent TD-DFT screen.

## ORCA Input Builder synchronization

- The Builder TD-DFT checkbox now opens the existing module as one embedded
  `Toplevel`; reopening focuses the same window.
- **Show ORCA Block** sends the validated fragment and structured settings to
  the connected Builder, which regenerates and displays the complete input.
- Repeated synchronization replaces the dedicated Builder TD-DFT component,
  so `%tddft` is emitted exactly once; unchecking removes that component.
- Closing and reopening preserves the last synchronized Builder-session
  settings and block. Standalone block generation remains supported.

## Calculation-selection update

- Replaced the single calculation-type dropdown with independent vertical,
  optimization, and frequency checkboxes in fixed workflow order.
- Added automatic calculation dependencies and validation requiring at least
  one selected calculation and a target root between 1 and `NROOTS`.
- Extended validated block generation with excited-state target-root controls;
  complete job-level assembly remains in the Builder.
- Added an ordered TD-DFT workflow summary to the setup panel.

- Added `td_dft_module.py` with validated ORCA `%tddft` block generation for
  vertical excitations, ORCA output parsing, stick and Gaussian-broadened
  spectra, CSV export, and PNG/SVG plotting.
- Added a standalone TD-DFT setup/analysis window with calculation, method,
  manifold, roots, guarded post-processing requests, spectrum controls, and an
  excited-state results table.
- Kept unverified excited-state optimization/frequency/emission and NTO/density
  keywords guarded with TODO notes instead of emitting speculative ORCA input.
- Added associated-file detection, remembered Multiwfn configuration, selected-
  state analysis packages, JSON metadata, logs, spectrum caching, and status
  reporting directly to the existing TD-DFT window.
- Added automatic reuse and validation of existing state cube files. Missing
  TD-DFT Multiwfn workflows are clearly disabled because the repository does
  not contain release-verified menu sequences; no commands are fabricated.
- Added signed Gaussian-cube rendering through PyVista with molecular, bond,
  label, isovalue, opacity, overlay, screenshot, and safe cube-export controls.

Run `python -m TD_DFT.td_dft_module` from the `tools` folder to start it
independently, or pass an output as
`python -m TD_DFT.td_dft_module --output calculation.out`.

Load the completed `.out`; matching `.gbw`, Molden, WFN/WFX, and FCHK files are
detected beside it. Select a state row and press **Generate All Analyses for
Selected State**. Shared spectra are stored in `TDDFT_analysis/`, while state
metadata, logs, and cubes are stored in `TDDFT_analysis/Sn/`. Normal runs reuse
validated files; **Regenerate Analysis Package** requests a fresh package
without silently overwriting cached volumetric files. Select a display mode to
view available results without recomputation.
