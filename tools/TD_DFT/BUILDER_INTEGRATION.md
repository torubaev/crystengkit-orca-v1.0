# TD-DFT Builder usage

1. In ORCA Input Builder, select **TD-DFT / UV-Vis**.
2. Configure TD-DFT/TDA, roots, and manifold in the TD-DFT window.
3. Select **Show ORCA Block**.

The module validates and generates only the `%tddft` fragment. The connected
Builder stores that fragment once, regenerates the complete ORCA input, opens
its existing input preview, and returns focus to the Builder. Change settings
freely; the Builder changes only after **Show ORCA Block** is selected again.

Uncheck **TD-DFT / UV-Vis** in the Builder to exclude the synchronized block.
Closing the module does not remove the last synchronized block. When the module
is launched independently, **Show ORCA Block** displays and copies the fragment
without requiring a Builder connection.
