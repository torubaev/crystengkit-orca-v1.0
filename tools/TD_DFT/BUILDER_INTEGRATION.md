# TD-DFT Builder usage

1. In ORCA Input Builder, select **TD-DFT / UV-Vis**.
2. Configure TD-DFT/TDA, roots, and manifold on the TD-DFT page.
3. Select **Show ORCA Block**.

The module validates and generates only the `%tddft` fragment. The connected
Builder stores that fragment once, regenerates the complete ORCA input, opens
its existing input preview, and returns focus to the Builder. Change settings
freely; the Builder changes only after **Show ORCA Block** is selected again.

Vertical absorption and emission fragments enable ORCA natural transition
orbitals for all calculated roots with `DoNTO true` and `NTOThresh 1e-4`.
Excited-state optimization omits repeated NTO generation and uses a compact
five-root window by default, expanded automatically when necessary to keep two
roots above the selected target. The matching `.gbw` and `.out` files from a
vertical calculation can be loaded in TD-DFT post-processing to generate and
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

Uncheck **TD-DFT / UV-Vis** in Input to exclude the synchronized block. Moving
to another workspace page does not remove the last synchronized block; return
to TD-DFT through the top navigation whenever it needs to be reviewed or
changed.
