# TD-DFT workflow examples

## Vertical excitation only

For 20 singlet roots with TDA, **Show ORCA block** generates:

```text
%tddft
  NRoots 20
  TDA true
  Singlets true
  Triplets false
end
```

## Vertical excitation plus excited-state optimization

The module contributes:

```text
%tddft
  NRoots 20
  TDA true
  Singlets true
  Triplets false
  IRoot 1
  IRootMult singlet
end
```

The connected Builder adds `Opt` to its complete ORCA keyword line.

## Vertical excitation, optimization, and excited-state frequencies

The TD-DFT fragment is the same targeted block above. The connected Builder
adds `Opt Freq` to the complete ORCA keyword line, so frequencies are evaluated
after the excited-state optimization in the same ORCA job.
