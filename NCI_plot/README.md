# NCI Plotter User Guide

The NCI Plotter helps visualize weak interactions in a molecule or molecular pair, such as hydrogen bonds, halogen bonds, pi-stacking, van der Waals contacts, and steric repulsion.

It creates a colored 3D NCI surface from a wavefunction file. The result is useful for inspecting where noncovalent contacts are located and for preparing figures for reports, manuscripts, or supporting information.

## What NCI Means

NCI stands for **Non-Covalent Interaction**.

In a typical NCI plot:

- **blue regions** usually indicate attractive interactions, such as strong hydrogen bonds
- **green regions** usually indicate weak attractive contacts, such as van der Waals interactions
- **red regions** usually indicate steric repulsion or unfavorable close contacts

The exact appearance depends on the molecule, the calculation, and the chosen color scale, so use the plot as a visual analysis tool together with chemical judgment.

## Required Software

Before using the NCI Plotter, you need:

- a completed quantum-chemistry calculation
- a `.wfn` or `.wfx` wavefunction file
- Multiwfn installed on your computer
- Python installed on your computer
- the Python packages `numpy` and `pyvista`

Install the Python packages with:

```bash
pip install numpy pyvista
```

If the plot window does not open, the most common reason is that `pyvista` or one of its visualization dependencies is missing from the Python environment being used to start the NCI Plotter.

## Input Files

Use:

- `.wfn`
- `.wfx`

Do not use:

- `.out`
- `.log`

The `.out` or `.log` file is the text report from the calculation. It is not enough for an NCI surface. The NCI Plotter needs the wavefunction file because that file contains the electron-density information needed for the plot.

## Starting the NCI Plotter

Open the `NCI_plot` folder and run:

```bash
python nci_plotter.py
```

On some Windows installations, use:

```bash
py -3.12 nci_plotter.py
```

If the NCI Plotter is launched from another program, such as ORCA Builder, it may open with a wavefunction file already selected. The use of the plotter is the same after it opens.

## Basic Workflow

1. Open the NCI Plotter.
2. Select the `.wfn` or `.wfx` file.
3. Select the Multiwfn program if it is not already selected.
4. Click the button to generate the NCI data.
5. Wait until the plot appears.
6. Adjust the display settings if needed.
7. Save the image.

## Display Settings

### RDG Isovalue

The RDG isovalue controls which NCI surface is shown.

- lower values may show tighter or smaller interaction regions
- higher values may show broader surfaces
- if no surface appears, try changing this value

The default value is a reasonable starting point for many systems.

### Color Range

The color range controls how strongly the plot shows attractive and repulsive regions.

For many routine plots, a symmetric range around zero is useful. If the colors look too weak or too saturated, adjust the minimum and maximum values.

### Opacity

Opacity controls how transparent the NCI surface is.

- higher opacity makes the surface stronger and more solid
- lower opacity makes it easier to see the molecule underneath

### Colormap

The usual NCI color style is blue-white-red or a similar diverging color scale.

Use a color map that clearly separates attractive, weak, and repulsive regions.

### Molecule and Bonds

You can show or hide the molecule and bonds to make the interaction surface clearer.

For presentation figures, it is often useful to keep the molecule visible but make the NCI surface slightly transparent.

## Saving a Figure

When the view is ready, use `Save image`.

Before saving, rotate and zoom the molecule so the important interaction region is easy to see. For dimers or crystal fragments, choose a view that clearly shows the contact between the fragments.

## Practical Tips

- Start with the default settings.
- If the surface is missing, change the RDG isovalue.
- If the plot is too colorful or too pale, adjust the color range.
- If the molecule is hidden by the surface, reduce opacity.
- For comparison between related molecules, use the same RDG isovalue and color range.
- For publication figures, keep the same visual settings across related plots whenever possible.

## Common Problems

### The program says `.out` or `.log` is not valid

Choose the `.wfn` or `.wfx` file instead. The text output file cannot be used directly for NCI plotting.

### I do not have a `.wfn` or `.wfx` file

Generate one from your quantum-chemistry calculation. In the CrystEngKit workflow, this is normally done after the ORCA run using the wavefunction-generation step.

### Multiwfn is not found

Select the Multiwfn executable manually. If you are not sure where it is installed, check your Multiwfn installation folder.

### The plot does not appear

Try:

- changing the RDG isovalue
- checking that the selected input file is really `.wfn` or `.wfx`
- confirming that Multiwfn is installed and opens correctly
- using a completed calculation rather than an unfinished or failed job

### The colors are hard to interpret

Try a clearer blue-white-red style color map and use a symmetric color range around zero. Keep the same settings when comparing several structures.

## Good To Know

An NCI plot is a visual interpretation of electron-density features. It is most useful when combined with:

- molecular geometry
- interatomic distances
- interaction energies
- chemical intuition
- comparison with related structures

The plot helps you see where weak interactions are located, but it should not be the only evidence used to assign or rank interactions.

## Examples and Benchmark Data

The repository-level `examples/` folder may include the S22 benchmark dataset for training, testing, and evaluation of CrystEngKit workflows. The S22 data are provided as reference examples, not as newly generated CrystEngKit results.

When using S22 or other BEGDB-derived benchmark data, cite both the original paper(s) attached to the respective BEGDB record and the BEGDB database paper itself:

Řezáč, J.; Jurečka, P.; Riley, K. E.; Černý, J.; Valdes, H.; Pluháčková, K.; Berka, K.; Řezáč, T.; Pitoňák, M.; Vondrášek, J.; Hobza, P. *Collect. Czech. Chem. Commun.* **2008**, *73*, 1261-1270. http://dx.doi.org/10.1135/cccc20081261 ; http://cccc.uochb.cas.cz/73/10/1261/
