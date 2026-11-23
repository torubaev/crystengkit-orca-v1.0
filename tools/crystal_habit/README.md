# Crystal Habit Builder

Crystal Habit Builder predicts solvent-dependent crystal morphology from a CIF structure. It runs CrystalClear for interaction and facet energetics, passes the results to CrystalGrower/CrystoGen for kinetic Monte Carlo growth simulation, and opens the resulting morphology in CGAspects.

It is available inside the CrystEngKit-ORCA Input Builder under **Advanced**, where it automatically reuses the currently loaded CIF. It can also run as a standalone Windows application.

Method references:

- [CrystalClear: Spackman *et al.*, *Chemical Science* 2023, 14, 7192–7207](https://doi.org/10.1039/D2SC06761G)
- [CrystalGrower/CrystoGen: Hill *et al.*, *Chemical Science* 2021, 12, 1126–1146](https://doi.org/10.1039/D0SC05017B)
- [CrystEngKit-ORCA main README](../../README.md)

## Start

Double-click `Launch-Crystal-Habit-GUI.bat`, or run:

```powershell
py -3 crystal_habit_gui.py
```

The default settings reproduce the established RJK2286 calculations:

- CE-1p interaction energies
- SMD solvation
- 4.1 Å interaction radius
- 3.0 Å surface cutoff
- 25 °C
- 1,000,000 CrystoGen iterations

Select a CIF, one or more solvents, and a results folder. The Builder suggests a dedicated `CrystalHabit_results` subfolder beside the loaded CIF; the user may accept it or choose another computational folder. If the CIF is inside the CrystEngKit source or installation tree, no result location is suggested and an external folder must be selected. Calculations are never allowed inside the application tree.

The editable solvent dropdown contains common laboratory solvents from the installed OCC SMD database and also accepts manual solvent names. The monitor displays the active stage, elapsed time, CPU time, memory, dimer or iteration progress, and program output.

Use **Preview** beside the CIF field to open the same PyVista molecular viewer used by ORCA Input Builder, including its parser, atom and bond styles, background, lighting and rendering settings.

The application creates a timestamped result directory containing CrystalClear results, Crystal Grower results, logs, inputs, and a JSON copy of the selected settings.
