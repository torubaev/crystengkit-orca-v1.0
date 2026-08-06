# Torsion generator

Generate systematic distorted XYZ geometries without changing atom order, and
optionally prepare matching ORCA TD-DFT inputs. The program never launches
ORCA.

## Builder GUI

Load and inspect a structure in ORCA Input Builder, open the **TD-DFT** module,
then click **Torsion scan** in the TD-DFT header. The window receives an
isolated copy of the current Builder geometry. Click the first and second axis atoms directly in the
numbered model. For an acyclic bond, the second-atom side is selected
automatically; for a cyclic or ambiguous bond, click atoms to toggle the green
rotating fragment. Choose an angle preset, use the slider to preview, and click
**Generate structures**. Less common numeric, JSON, random-scan, and template
controls are under **Advanced…**. Generated geometries never replace the
geometry currently loaded in Builder.

Install the required packages:

```text
python -m pip install numpy ase
```

ASE is compatible with the toolchain but is not required by the explicit XYZ
reader and Rodrigues rotation implementation.

Examples:

```text
python torsion_generator.py molecule.xyz --inspect
python torsion_generator.py molecule.xyz --config example_single_scan.json --output generated_structures
python torsion_generator.py molecule.xyz --config example_alternating_scan.json --output alternating --write-orca --overwrite --verbose
```

Atom numbers are one-based and match the order printed by `--inspect`. Choose
the two atoms forming the inter-unit bond as `axis_atoms`; the first is the
fixed-side axis atom and the second points toward the rotating unit. List the
atoms of the fragment to move in `rotating_atoms`. The second axis atom may be
listed, but both axis atoms remain mathematically fixed. The example atom
numbers are generic placeholders and must be replaced with selections from the
actual molecule.

Supported modes are `single`, `independent`, `collective`, `alternating`,
`combinations`, and seeded `random`. `max_structures` protects combination
scans from accidental explosion. Each output directory receives XYZ files,
optional ORCA inputs, `torsion_scan_summary.csv`, and provenance metadata.
