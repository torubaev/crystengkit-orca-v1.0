# TD-DFT workflow examples

## Vertical excitation only

For the default 5 singlet roots with TD-DFT, **Show ORCA block** generates:

```text
%tddft
  NRoots 5
  TDA false
  MaxDim 20
  MaxIter 300
  DoNTO true
  NTOThresh 1e-4
end
```

## Excited-state optimization

The module contributes:

```text
%tddft
  NRoots 5
  TDA false
  MaxDim 20
  MaxIter 300
  IRoot 1
  IRootMult singlet
end
```

The connected Builder adds `Opt` to its complete ORCA keyword line. Changing
`NRoots` recalculates `MaxDim` as four times the root count. `MaxDim` remains
editable, and the generated input respects a subsequent manual override.

## Vertical excitation, optimization, and excited-state frequencies

The TD-DFT fragment is the same targeted block above. The connected Builder
adds `Opt Freq` to the complete ORCA keyword line, so frequencies are evaluated
after the excited-state optimization in the same ORCA job.

`DoNTO true` is included in vertical absorption and emission blocks. Because
`NTOStates` is intentionally omitted, ORCA generates NTOs for all calculated
states in those analysis-producing stages. `NTOThresh 1e-4` controls the
printed NTO occupation threshold. Optimization blocks omit NTO generation.

## Absorption and UV-Vis analysis

Load a completed TD-DFT/TDA `.out` in the post-processing tab. The module
detects associated files beside the output, parses excited-state energies and
oscillator strengths, and presents the state table together with stick or
Gaussian-broadened spectra. State tables, spectrum data, and PNG/SVG figures
use editable, descriptive save suggestions based on the loaded calculation.

## Natural transition orbital analysis

Select an excited state and validate the Multiwfn executable. **Generate all
analyses** prepares the selected-state package and generates the dominant NTO
hole/electron cube pair from the matching `.gbw` through the validated
Multiwfn workflow. Existing valid cubes are reused unless regeneration is
requested. The signed cube viewer supports molecular overlays, bonds, labels,
positive/negative isosurfaces, opacity, screenshots, and cube export.

## Fluorescence emission sequence

Start from a completed absorption calculation and select the emitting root.
The Builder prepares an excited-state optimization targeting that root, then a
vertical-emission calculation at the optimized excited-state geometry. Method,
basis, solvent, charge, multiplicity, TD-DFT/TDA choice, and root count are
carried forward from the source workflow. Generated files use numbered,
method- and step-specific names so absorption, optimization, and emission
outputs remain distinguishable.
