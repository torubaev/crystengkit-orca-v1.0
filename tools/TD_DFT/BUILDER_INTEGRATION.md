# TD-DFT Builder usage

1. In ORCA Input Builder, select **TD-DFT / UV-Vis**.
2. Configure TD-DFT/TDA, roots, and manifold in the TD-DFT window.
3. Select **Show ORCA Block**.

The module validates and generates only the `%tddft` fragment. The connected
Builder stores that fragment once, regenerates the complete ORCA input, opens
its existing input preview, and returns focus to the Builder. Change settings
freely; the Builder changes only after **Show ORCA Block** is selected again.

Every generated fragment enables ORCA natural transition orbitals for all
calculated roots with `DoNTO true` and `NTOThresh 1e-4`. The matching `.gbw`
and `.out` files can then be loaded in TD-DFT post-processing to generate and
display the dominant NTO hole/electron cube pair for a selected state.

TD-DFT calculation names follow
`structure_functional_basis_solvent_method_analysis`, using `td-dft` or `tda`
from the actual method. User-selected CSV and image exports retain the loaded
output stem and add a descriptive artifact suffix.

The post-processing tab parses excitation data directly from a completed ORCA
output. UV-Vis tables and plots do not require Multiwfn. Selected-state NTO
cube generation requires the matching `.gbw` and a validated Multiwfn
executable; unsupported or missing workflows remain visibly disabled instead
of issuing speculative menu commands.

For fluorescence, the module uses a completed absorption output to prepare the
excited-state optimization and vertical-emission sequence. The Builder runs
these as monitored ORCA jobs and preserves the source electronic-structure and
solvent settings.

Uncheck **TD-DFT / UV-Vis** in the Builder to exclude the synchronized block.
Closing the module does not remove the last synchronized block. When the module
is launched independently, **Show ORCA Block** displays and copies the fragment
without requiring a Builder connection.
