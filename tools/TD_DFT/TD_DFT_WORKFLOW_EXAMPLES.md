# TD-DFT workflow examples

## Vertical excitation only

For 10 singlet roots with TD-DFT, **Show ORCA block** generates:

```text
%tddft
  NRoots 10
  TDA false
  MaxDim 5
  MaxIter 300
  DoNTO true
  NTOThresh 1e-4
end
```

## Vertical excitation plus excited-state optimization

The module contributes:

```text
%tddft
  NRoots 10
  TDA false
  MaxDim 5
  MaxIter 300
  DoNTO true
  NTOThresh 1e-4
  IRoot 1
  IRootMult singlet
end
```

The connected Builder adds `Opt` to its complete ORCA keyword line.

## Vertical excitation, optimization, and excited-state frequencies

The TD-DFT fragment is the same targeted block above. The connected Builder
adds `Opt Freq` to the complete ORCA keyword line, so frequencies are evaluated
after the excited-state optimization in the same ORCA job.

`DoNTO true` is included in every generated TD-DFT/TDA block. Because
`NTOStates` is intentionally omitted, ORCA generates NTOs for all calculated
states. `NTOThresh 1e-4` controls the printed NTO occupation threshold.
