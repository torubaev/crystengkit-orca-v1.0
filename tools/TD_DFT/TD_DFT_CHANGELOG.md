# TD-DFT module feature reference

## TD-DFT filenames

- Builder and emission files use method- and workflow-specific names.
- User-selected table, spectrum, and screenshot saves receive descriptive
  default filenames without restricting manual filename editing.

## NTO preparation and analysis

- Every Builder and standalone TD-DFT/TDA block includes `DoNTO true` and
  `NTOThresh 1e-4`; omitting `NTOStates` requests every calculated state.
- Legacy saved `print_ntos: false` values are migrated to the required enabled
  behavior.
- The validated Multiwfn workflow generates the dominant selected-state NTO
  hole/electron cube pair from the matching `.gbw` and reuses valid cached
  cubes unless regeneration is requested.

## Builder-owned excited-state jobs

- TD-DFT sends structured calculation-step settings alongside its validated
  `%tddft` fragment.
- The Builder derives verified `Opt` and `Freq` job keywords from those settings;
  the module emits `IRoot` and `IRootMult` for the selected target state.
- Excited-state optimization and frequency controls are enabled with automatic
  vertical-excitation and optimization dependencies.
- Builder-owned functional, basis, solvent, charge, and multiplicity are shown
  read-only in the independent TD-DFT screen.

## ORCA Input Builder synchronization

- The Builder TD-DFT checkbox opens the module as one embedded
  `Toplevel`; reopening focuses the same window.
- **Show ORCA Block** sends the validated fragment and structured settings to
  the connected Builder, which regenerates and displays the complete input.
- Repeated synchronization replaces the dedicated Builder TD-DFT component,
  so `%tddft` is emitted exactly once; unchecking removes that component.
- Closing and reopening preserves the last synchronized Builder-session
  settings and block. Standalone block generation remains supported.

## Calculation selection

- The calculation selector provides independent vertical, optimization, and
  frequency checkboxes in fixed workflow order.
- Automatic calculation dependencies and validation require at least
  one selected calculation and a target root between 1 and `NROOTS`.
- Validated block generation includes excited-state target-root controls;
  complete job-level assembly remains in the Builder.
- The setup panel shows an ordered TD-DFT workflow summary.

- `td_dft_module.py` provides validated ORCA `%tddft` block generation for
  vertical excitations, ORCA output parsing, stick and Gaussian-broadened
  spectra, CSV export, and PNG/SVG plotting.
- The standalone TD-DFT setup/analysis window provides calculation, method,
  manifold, roots, guarded post-processing requests, spectrum controls, and an
  excited-state results table.
- Unverified density-analysis paths remain guarded instead of emitting
  speculative ORCA or Multiwfn commands.
- Associated-file detection, remembered Multiwfn configuration, selected-
  state analysis packages, JSON metadata, logs, spectrum caching, and status
  reporting directly to the existing TD-DFT window.
- Existing state cube files are reused after validation. Missing
  TD-DFT Multiwfn workflows are clearly disabled because the repository does
  not contain release-verified menu sequences; no commands are fabricated.
- Signed Gaussian-cube rendering through PyVista provides molecular, bond,
  label, isovalue, opacity, overlay, screenshot, and safe cube-export controls.

## Fluorescence sequence

- A completed absorption output seeds a targeted excited-state optimization
  followed by vertical emission at the optimized geometry.
- Source method, basis, solvent, charge, multiplicity, roots, and actual
  TD-DFT/TDA method are preserved across the sequence.
- Numbered, method- and step-specific filenames distinguish absorption,
  excited-state optimization, and vertical-emission artifacts.

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
