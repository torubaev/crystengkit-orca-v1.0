# Crystal Habit Builder

Windows GUI for sequential CrystalClear and CrystoGen crystal-habit calculations.

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

Select a CIF, one or more solvents, and a results folder. The editable solvent dropdown contains common laboratory solvents from the installed OCC SMD database and also accepts manual solvent names. The monitor displays the active stage, elapsed time, CPU time, memory, dimer or iteration progress, and program output.

Use **Preview** beside the CIF field to open the same PyVista molecular viewer used by ORCA Input Builder, including its parser, atom and bond styles, background, lighting and rendering settings.

The application creates a timestamped result directory containing CrystalClear results, Crystal Grower results, logs, inputs, and a JSON copy of the selected settings.
