# CrystEngKit: A practical GUI for supramolecular chemistry and crystal engineering (from .CIF file to ESP, NCI, and QTAIM plots in a few clicks).

<img title="" src="images/wiki/CpFe(CO)2X_DITFB_COVER_1000x1300.png" alt="" width="207"> <img title="" src="images/wiki/ZfK_C2H2I2_COVER.png" alt="" width="203"> <img title="" src="images/wiki/jctcce.2014.10.issue-2.largecover.jpg" alt="" width="204">

*ESP maps, NCI plots, BCP/bonding paths, and HOMO-LUMO shapes are not only illustrations of your work but also good ideas for journal cover art*.

## Table of Contents

- [Introduction](README.md#introduction)
- [Installation and prerequisites](README.md#installation-and-prerequisites)
- [Launching the programs](README.md#launching-the-programs)
- [GUI functions and usage](README.md#gui-functions-and-usage)
- [ORCA Input Builder](README.md#orca-input-builder)
- [HOMO-LUMO Plotter](README.md#homo-lumo-plotter)
- [ESP / VisMap](README.md#esp--vismap)
- [NCI Plotter](README.md#nci-plotter)
- [QTAIM Critical Points Viewer](README.md#qtaim-critical-points-viewer)
- [NCI + QTAIM Overlay](README.md#nci--qtaim-overlay)
- [Intermolecular interaction workflow](README.md#intermolecular-interaction-workflow)
- [Practical use cases](README.md#practical-use-cases)
- [Good to know](README.md#good-to-know)
- [Troubleshooting](README.md#troubleshooting)
- [Repository contents](README.md#repository-contents)
- [Notes](README.md#notes)


## Introduction

CrystEngKit is a practical GUI suite for basic quantum-chemical computations and visualization in supramolecular chemistry and crystal engineering. It helps experimental researchers prepare ORCA/Gaussian input files, run ORCA calculations, monitor results, and turn finished calculations into figures and summary text.

Typical input formats are `.xyz`, existing ORCA `.inp` files, and `.cif` files from single-crystal X-ray diffraction, publications or Cambridge Structural Database (CSD)[^csd].

The suite provides one-click automation and publication-quality visualization of intermolecular energy computations[^counterpoise], molecular electrostatic potential maps (ESP)[^esp], HOMO-LUMO diagrams[^frontier-orbitals], ORCA molecular-orbital surface images, NCI plots[^nci], QTAIM critical-point plots[^qtaim], NCI/QTAIM overlay figures, and bond-path images.

CrystEngKit is built around widely used, freely available academic/freeware programs. In the standard workflow, ORCA[^orca-site] is used for quantum-chemical calculations, and Multiwfn[^multiwfn-site] is used for wavefunction analysis, ESP/NCI cube generation, and QTAIM critical-point analysis. CrystEngKit does not replace these programs; it provides a practical shell that helps experimental chemists make the first steps into quantum-chemical calculations and convert results into publication-ready images, tables, and text.

CrystEngKit is intended to run on Windows, Linux, and macOS with Python 3.9 or newer. The Orca Input Builder checks for installed Python interpreters on startup and uses the newest suitable Python it finds for companion tools such as ESP, NCI, and QTAIM viewers. ORCA, Multiwfn, and optional external tools must still be installed in versions suitable for your operating system.

![](images/wiki/orca-input_2.png)

The suite is based on the **ORCA Input Builder**[^orca], which can:

- read molecular structures directly from `.cif` and `.xyz` files.
- generate ORCA input files for isolated molecules and bimolecular associates.
- run and monitor ORCA jobs directly from the GUI.
- generate manuscript-ready computation summaries for experimental sections and supporting information
- launch HOMO-LUMO, ESP, NCI, QTAIM, and interaction-energy computations and visualizations.

The repository also includes five companion tools, which can be used as part of a workflow or independently as standalone applications:

1. **HOMO-LUMO Plotter**  
   Used to create orbital energy diagrams showing the frontier orbital gap and the desired number of HOMO and LUMO levels. For ORCA outputs with matching `.gbw` files, it can also generate and render HOMO/LUMO molecular-orbital surfaces. Can be used as part of the ORCA Input Builder workflow or as a standalone tool.

2. **VisMap**  
   Used to generate and plot Molecular Electrostatic Potential (ESP) surfaces in an interactive PyVista viewer. Can be used as part of the ORCA Input Builder workflow or as a standalone tool. Requires Multiwfn software[^multiwfn].

3. **NCI Plotter**  
   Used to generate and visualize Non-Covalent Interaction (NCI) plots from `.wfn` / `.wfx` wavefunction files. It uses Multiwfn to produce RDG[^nci] and sign(lambda2)rho cube files, then displays the RDG isosurface colored by sign(lambda2)rho in an interactive image viewer (PyVista-based). Can be used from the Builder after a finished ORCA job or as a standalone tool.

4. **QTAIM Critical Points Viewer**  
   Used to inspect QTAIM critical points from `.wfn` and `.wfx` files. It helps show where bond, ring, and cage critical points are located in the molecule. Can be launched from the Builder with the current ORCA wavefunction file or used as a standalone tool.

5. **NCI + QTAIM Overlay**
   Used to combine the molecular structure, NCI surface, QTAIM bond critical points, and exported QTAIM bond paths in one PyVista view. It can be opened from the NCI Plotter or used directly on an analysis folder containing matching NCI and QTAIM files.



Typical workflow:

1. Build the input file (.inp) in the Builder. Save it.
2. Run ORCA.
3. Inspect the output in the monitor.
4. Create HOMO-LUMO plots, MO surface images, ESP maps, NCI plots, QTAIM critical-point views, or NCI/QTAIM overlay figures from the finished job by clicking the respective buttons on the top panel.

## Installation and prerequisites

The Builder is a Python GUI application. It can usually be launched directly if Python is already associated with `.py` files on your system, but it is better to make sure the environment is complete first.

### External software

Install the following software before using the full suite:

- **Python 3.9+**
- **ORCA** for running calculations from the Builder. ORCA is available free of charge for academic users; download and license information are provided by the official ORCA/FACCTs pages[^orca-site].
- **orca_2aim** for automatic `.wfn` / `.wfx` generation after ORCA runs
- **Multiwfn** for VisMap ESP, density cube generation, NCI/RDG analysis, and QTAIM critical-point analysis. Multiwfn and its manual are available from the official Multiwfn website[^multiwfn-site].

### Python modules

The suite uses standard-library Python modules plus a small set of extra packages.

Main optional Python packages:

- `numpy`
- `pyvista`
- `matplotlib`
- `periodictable`
- `gemmi`
- `Pillow`

Install them with:

```bash
pip install numpy pyvista matplotlib periodictable gemmi Pillow
```

## Launching the programs

### ORCA Input Builder

Run:

```bash
python tools/Orca_input/orca_input.py
```

Or double-click the `tools/Orca_input/orca_input.py` file.

### HOMO-LUMO Plotter

From the ORCA Input Builder, use the corresponding button, or run:

```bash
python tools/HOMO_LUMO/HOMO_LUMO_v2.py
```

### ESP / VisMap

From the ORCA Input Builder, use the corresponding button, or run:

```bash
python tools/VisMap_5.0/VisMap5.6_pyvista.py
```

### NCI Plotter

From the ORCA Input Builder, use the corresponding button, or run:

```bash
python tools/NCI_plot/nci_plotter.py
```

### QTAIM Critical Points Viewer

From the ORCA Input Builder, use the corresponding button, or run:

```bash
python tools/qtaim-cp/qtaim.py
```

### NCI + QTAIM Overlay

From the NCI Plotter, use `NCI + QTAIM overlay`, or run:

```bash
python tools/NCI_QTAIM_overlay/nci_qtaim_overlay.py
```

## GUI functions and usage

This suite contains six practical tools. Each is usable on its own, but they are designed to work together.

## ORCA Input Builder

![](images/wiki/orca-input_1.png)

The Orca Input Builder is the main entry point.

### What it does

- prepares ORCA input files
- accepts `.xyz`, `.cif`, and embedded-coordinate ORCA `.inp` sources
- previews the generated input file
- runs ORCA directly
- shows live ORCA output in the GUI
- creates a manuscript-ready computation summary after successful runs
- launches HOMO-LUMO, ESP, NCI, QTAIM, and interaction-energy computations and visualizations
- supports dimer interaction-energy workflows

### Main window structure

The Builder window is divided into:

- **Header**  
  Main actions: `Run Orca`, `HOMO LUMO`, `ESP map`, `NCI plot`, `QTAIM CP`, `Settings / About`

- **FILE INPUT**  
  Choose the structure file and output behavior.

- **STRUCTURE**  
  Open a molecular preview for a quick geometry check.

- **CALCULATION SETUP**  
  Program, solvent, functional, basis, dispersion, charge, multiplicity, grid, and SCF options.

- **CALCULATION TARGETS**  
  Single-point energy[^orca-runtypes], geometry optimization, frequencies, ESP package, TD-DFT, NMR, and intermolecular-interaction options.

- **INTERMOLECULAR INTERACTION**  
  Fragment assignment, binding-energy controls, and interaction-job generation.

- **INPUT PREVIEW**  
  Generated ORCA or Gaussian input text.

- **JOB MONITOR**  
  Live output, status, summary text, and output access.

### Builder buttons and checkboxes

- **Run Orca** starts the ORCA calculation using the currently prepared input file.
- **Structure preview** opens a 3D view of the current molecular structure so you can check atom positions, fragments, and possible problems before running a calculation.
- **HOMO LUMO** opens the frontier-orbital plotter after a calculation or from suitable orbital-energy data.
- **ESP map** opens the VisMap ESP workflow. It needs a wavefunction file such as `.wfn`, `.wfx`, or `.fchk`.
- **NCI plot** opens the NCI Plotter. It needs `.wfn` or `.wfx` input and Multiwfn-generated NCI data.
- **QTAIM CP** opens the QTAIM critical-point viewer for BCP/RCP/CCP inspection and bond-path visualization.
- **Settings / About** stores paths to external programs and companion scripts, such as ORCA, Multiwfn, VisMap, NCI Plotter, and QTAIM viewer.
- **Single-point energy** requests an energy calculation at the current fixed geometry.
- **Geometry optimization** requests an optimized structure. Use this when the input geometry should be relaxed before analysis.
- **Frequencies / thermochemistry** requests vibrational frequencies and thermochemical quantities.
- **ESP / MEP package** requests output suitable for electrostatic-potential analysis and downstream ESP visualization.
- **TD-DFT / UV-Vis** requests excited-state calculations for predicted UV-Vis transitions.
- **NMR** requests NMR-related calculated properties.
- **Intermolecular interaction energy** activates the dimer workflow for fragment assignment, frozen interaction energies, counterpoise correction, and optional relaxed/thermodynamic follow-up jobs.

### Modeling of Solvation Effects

In the Builder, the `Solvent` field is intended for ORCA or Gaussian implicit-solvent calculations[^pcm].

For ORCA, this workflow uses the **SMD solvation model**[^smd]. In practical terms, SMD treats the solvent as a continuum medium rather than placing explicit solvent molecules around the solute. The model uses the quantum-mechanical electron density of the solute together with solvent-specific descriptors, making it a convenient way to estimate solution-phase effects without building a full solvent shell.

In the Builder, this means:

- choose a solvent from the dropdown for common cases
- or use `Other solvent...` for a custom solvent name
- the Builder translates recognized solvents into the appropriate ORCA or Gaussian solvent keyword

For ORCA, the generated input uses the SMD route through the `%cpcm` block[^pcm] with:

```text
%cpcm
  smd true
  SMDsolvent "solvent"
end
```

The Builder does not require you to type this block manually.

A few practical notes:

- SMD is useful for single-point energies, geometry optimizations, and other standard solution-phase calculations.
- The solvent must match an ORCA-recognized solvent keyword for ORCA to accept it.
- The dropdown contains a short curated list for convenience, while `Other solvent...` lets you try additional names supported by ORCA.

### Calculation setup elements

Below is the practical meaning of each item in `CALCULATION SETUP`.

- **Program**  
  Chooses whether the Builder writes an ORCA input or a Gaussian input. `Run Orca` is available only when `Program = ORCA`.

- **Solvent**  
  Adds an implicit-solvent model to the calculation setup. In ORCA, this is handled through the SMD route described above. Leave it blank for gas-phase calculations.

- **Functional**  
  Chooses the electronic-structure method. For most routine DFT work[^dft], this is the main method selector.

- **Basis set**  
  Chooses the orbital basis[^basis-sets] used for the calculation. Larger basis sets are usually more accurate but computationally more expensive.

- **Dispersion**  
  Adds an empirical dispersion correction such as `D3BJ` or `D4`[^dispersion]. This is especially important for noncovalent interactions, packing effects, and many intermolecular-energy calculations.

- **Charge**  
  Sets the total molecular charge of the calculation.

- **Multiplicity**  
  Sets the spin multiplicity. Typical closed-shell neutral systems use multiplicity `1`.

- **ORCA grid**  
  Controls the numerical integration grid in ORCA[^orca-runtypes]. A denser grid may improve stability or accuracy for some functionals, but increases cost.

- **TD-DFT roots**  
  Sets how many excited states to request when `TD-DFT / UV-Vis`[^tddft] is enabled.

- **Tight SCF**  
  Requests stricter SCF convergence[^scf]. This is often a good default for cleaner final energies.

- **RIJCOSX**  
  Enables the RIJCOSX approximation[^rijcosx] in ORCA, which usually improves speed for hybrid DFT calculations with little practical loss of accuracy.

- **Print frontier MO data**  
  Requests extra molecular-orbital output that can be useful for post-processing and orbital analysis.

### Typical Builder workflow

1. Select an `.xyz` or `.cif` file in `FILE INPUT`.
   
   ![](images/wiki/orca-input_1.png)
2. If needed, open `Structure preview` and verify the geometry.
   
   ![](images/wiki/orca-input_viewer_1.png)
3. In `CALCULATION SETUP`, choose:
   - `Program`
   - `Functional`
   - `Basis set`
   - `Dispersion`
   - `Solvent`
   - `Charge`
   - `Multiplicity`
4. In `CALCULATION TARGETS`, choose the type of calculation:
   - `Single-point energy`
   - `Geometry optimization`
   - `Frequencies / thermochemistry`
   - `ESP / MEP package`
   - `TD-DFT / UV-Vis`
   - `NMR`
5. Click `*.inp file preview`.
6. Review the generated input text.
7. Save the input file if desired.
8. Click `Run Orca` if `Program = ORCA`.
9. Follow the progress in `JOB MONITOR`.
10. After completion, use the header buttons for further analysis.
    
    ![](images/wiki/orca_top_panel_1.png)

### Output from the Builder

Depending on the calculation, the Builder can produce:

- ORCA `.inp`
- Gaussian `.gjf` / `.com`
- ORCA `.out`
- project summary text file
- `.wfn` / `.wfx` files through `orca_2aim` for ESP, NCI, and QTAIM workflows
- interaction-job folders for dimer workflows

## HOMO-LUMO Plotter

![](images/wiki/orca_homo-lumo_2.png)

This tool makes orbital energy diagrams suitable for quick analysis and manuscript figures.

### What it accepts

- pasted orbital energies
- ORCA output-like text files
- Gaussian output-like text files
- supported plain-text input sources containing orbital energies
- finished ORCA `.out` files with matching `.gbw` files for MO surface rendering

### Typical HOMO-LUMO workflow

1. Launch the Plotter directly, or click `HOMO LUMO` from the Builder after an ORCA run.
2. Choose one of two modes:
   - paste energies manually
   - open a calculation file
3. Adjust the display range around HOMO/LUMO if needed.
4. Click `Preview plot`.
5. Save the figure as `.png` or `.svg`.

### ORCA MO surface workflow

For finished ORCA jobs, the Plotter can generate and view molecular-orbital surfaces around the frontier orbitals.

1. Open a finished ORCA `.out` file.
2. Keep the matching `.gbw` file in the same folder.
3. Choose the orbital window around HOMO/LUMO, isovalue, opacity, color scheme, and image size.
4. Click `Generate MO cubes`; the Plotter uses `orca_plot` to create cube files for the selected orbitals.
5. Open the MO surface table, inspect each orbital tile, and open or replace individual saved views.
6. Save high-resolution orbital images and export the table when the views are ready.

![](images/wiki/orca_homo-lumo_3.png)

### What the Plotter reports

- HOMO position
- LUMO position
- HOMO-LUMO gap in eV
- energy-level diagram
- saved MO surface views, thumbnails, and a table for ORCA jobs when the cube workflow is used

### Files used by the MO surface workflow

- ORCA `.out`
- matching ORCA `.gbw`
- `orca_plot`
- generated `.cube` files
- generated `.png` views, thumbnails, metadata, and contact-sheet images

## ESP / VisMap

VisMap is the ESP and electron-density viewer used for visual analysis of electrostatic potential on electron-density isosurfaces.

![](images/wiki/orca_vismap_output_1.png)

This PyVista-based branch of VisMap is built on the original VisMap code by aaan1s:

- https://github.com/aaan1s/VisMap

In VisMap 5.6, the original workflow was adapted with several practical modifications:

- PyVista is used for 3D visualization instead of Mayavi, making the visualization workflow more practical and interactive for routine ESP plotting
- a graphical user interface was added for ESP data generation and plotting
- extrema plotting was added for easier inspection of ESP minima and maxima
- the workflow was integrated into the ORCA Input Builder so ESP mapping can be launched directly after ORCA runs

### What it does

- starts from supported wavefunction files such as `.wfn`, `.wfx`, and `.fchk`
- uses Multiwfn to generate electron-density and electrostatic-potential cube data
- opens a PyVista window for interactive 3D viewing
- supports one-click ESP plot generation from the Builder workflow
- supports surface styling, labels, extrema analysis, and image export

### Typical VisMap workflow

1. Complete an ORCA run with ESP-ready output enabled, or open VisMap directly from an existing wavefunction file.
2. In the Builder, click `ESP map` after the run finishes, or launch VisMap separately.
3. In VisMap, select the input file.
4. Run the calculation and viewer workflow.
5. Adjust:
   - isovalue
   - ESP scale range
   - background and label colors
   - display options
6. Save or copy the image when satisfied.

### Files used by VisMap

- `.wfn`
- `.wfx`
- `.fchk`
- generated cube files such as:
  - `*_Dens.cub`
  - `*_ESP.cub`

### Practical notes

- The ESP surface is plotted over an electron-density isosurface; changing the isovalue regenerates the displayed surface.
- Existing cube files, such as `*_Dens.cub` and `*_ESP.cub`, can be reused if they are already present, which speeds up repeated visualization of the same system.
- VisMap can be used as a standalone viewer or launched directly from the ORCA Input Builder after a finished run.

## NCI Plotter

![](images/wiki/orca_nci_output_1.png)

The NCI Plotter is used for visual analysis of weak and noncovalent interactions from wavefunction-based NCI/RDG data.

It is designed to avoid approximate or fake NCI surfaces: the plot is generated from volumetric data produced by Multiwfn from a selected wavefunction file.

### What it does

- accepts `.wfn` and `.wfx` wavefunction files
- rejects `.out` and `.log` files because they do not contain the full wavefunction and electron-density information required for NCI/RDG analysis
- uses Multiwfn batch mode to generate RDG and sign(lambda2)rho cube files
- opens an interactive PyVista viewer
- displays the RDG isosurface colored by sign(lambda2)rho
- can reuse existing NCI cube files if they are already present
- supports image export from the viewer
- can launch the NCI + QTAIM overlay viewer for combined NCI surface and QTAIM bond-path figures

### Typical NCI workflow

1. Complete an ORCA run that produces a `.wfn` or `.wfx` file, or open the NCI Plotter directly with an existing wavefunction file.
2. In the Builder, click `NCI plot` after the run finishes, or launch the NCI Plotter separately.
3. Select the wavefunction file and the Multiwfn executable if they are not already set.
4. Generate the NCI data.
5. Adjust:
   - RDG isovalue
   - opacity
   - sign(lambda2)rho color range
   - colormap
   - molecule, bond, scalar-bar, and background display options
6. Save the image when satisfied.

### Files used by NCI Plotter

- `.wfn`
- `.wfx`
- generated cube files such as:
  - `func1.cub` for sign(lambda2)rho in the default Multiwfn export route
  - `func2.cub` for RDG in the default Multiwfn export route

### Practical notes

- NCI plotting requires a real wavefunction file, not only the text ORCA output.
- The default Multiwfn batch template is intended for the currently supported route, but Multiwfn menu numbers can differ between versions.
- If your Multiwfn version uses a different command sequence, edit the command template from the NCI Plotter before generating data.
- The Builder tries to find a matching `.wfn` or `.wfx` file for the current ORCA task when `NCI plot` is clicked.

## QTAIM Critical Points Viewer

![](images/wiki/orca_qtaim_1.png)

The QTAIM Critical Points Viewer helps you inspect bonding features from an Atoms in Molecules analysis.

It starts from a wavefunction file and shows the molecule together with the critical points detected by Multiwfn. This is useful for examining possible bonding interactions, ring features, or cage features in a structure.

![](images/wiki/orca_qtaim_2.png)

### What it does

- opens `.wfn` and `.wfx` wavefunction files
- uses Multiwfn for the QTAIM critical-point search
- displays the molecule and detected critical points in a 3D viewer
- helps distinguish between common critical-point types:
  - nuclear critical points
  - bond critical points
  - ring critical points
  - cage critical points
- can show simple guidelines from bond critical points to nearby atoms

### Typical QTAIM workflow

1. Complete an ORCA run that produces a `.wfn` or `.wfx` file, or open the QTAIM viewer directly with an existing wavefunction file.
2. In the Builder, click `QTAIM CP` after the run finishes, or launch the QTAIM viewer separately.
3. Confirm the wavefunction file and the Multiwfn executable.
4. Run the QTAIM analysis, or load an already generated critical-point file.
5. Open the 3D viewer and inspect where the critical points appear.

### Files used by QTAIM Critical Points Viewer

- `.wfn`
- `.wfx`
- generated Multiwfn QTAIM result files

### Practical notes

- QTAIM analysis requires a real wavefunction file, not only the text ORCA output.
- The QTAIM viewer is intended for visual inspection. Use the results together with distances, interaction energies, and chemical judgment.
- The color swatches in the visualization settings are clickable and can be used to change CP and QTAIM bond-path colors.
- The guidelines shown in the viewer are only visual aids. Exact QTAIM bond paths should be checked in Multiwfn if needed.
- The Builder tries to find a matching `.wfn` or `.wfx` file for the current ORCA task when `QTAIM CP` is clicked.

## NCI + QTAIM Overlay

![](images/wiki/orca_qtaim_nci_overlay.png)

The NCI + QTAIM Overlay tool combines two post-processing views for the same structure: the NCI surface and the QTAIM bond critical points / bond paths.

It is useful when you want one figure that shows where a weak-contact surface lies relative to the QTAIM topology.

### What it does

- loads RDG and sign(lambda2)rho cube files from the NCI workflow
- loads the matching `.wfn` or `.wfx` structure
- loads QTAIM critical-point and bond-path output files
- auto-detects matching files from a selected wavefunction folder when possible
- aligns QTAIM coordinates to the NCI molecule if the exported coordinate frames differ
- lets you show or hide the molecule, NCI surface, BCPs, QTAIM paths, and labels

### Typical overlay workflow

1. Generate NCI cube files for a `.wfn` or `.wfx` file.
2. Generate QTAIM critical points and bond paths for the same structure.
3. Open `NCI + QTAIM overlay` from the NCI Plotter, or launch the overlay tool directly.
4. Use auto-detection from the analysis folder, or manually select the RDG cube, sign(lambda2)rho cube, wavefunction file, QTAIM CP file, and QTAIM path file.
5. Open the overlay and adjust visibility toggles for the figure you need.

### Files used by NCI + QTAIM Overlay

- RDG cube file
- sign(lambda2)rho cube file
- `.wfn` or `.wfx` structure file
- generated QTAIM critical-point file
- generated QTAIM bond-path file

### Practical notes

- The overlay assumes the NCI and QTAIM files belong to the same molecular structure.
- Auto-detection searches the selected folder and nearby subfolders for common NCI and QTAIM output names.
- If the QTAIM coordinates appear shifted or scaled relative to the NCI molecule, the overlay attempts a symbol-aware alignment before plotting.
- The overlay is for combined visual inspection; quantitative QTAIM values should still be checked in the source Multiwfn output.

## Intermolecular interaction workflow

The Builder also supports dimer interaction-energy workflows.

### What it can do

- define fragments A and B automatically or with PyVista help
- generate frozen monomer and ghost-basis jobs
- assemble uncorrected and CP-corrected interaction energies[^counterpoise]
- optionally generate relaxed follow-up jobs for binding-energy analysis
- optionally include thermodynamic frequency jobs for `ΔH` and `ΔG`

### Practical use

1. Load the dimer structure.
2. Enable `Intermolecular interaction energy (dimer)`.
3. Define fragments A and B.
   
   ![](images/wiki/orca-input_viewer_2.png)
4. Set fragment charges and multiplicities.
5. If needed, enable:
   - `Relaxation energy / binding E`
   - `Delta H and G / thermodynamic frequencies`
6. Run ORCA from the Builder.
7. Read the interaction section of the project summary after the run finishes.

## Practical use cases

### 1. ORCA single-point job from an `.xyz`

1. Open the Builder.
2. Load the `.xyz` structure.
3. Set `Program = ORCA`.
4. Choose the functional, basis set, solvent, charge, and multiplicity.
5. Leave `Single-point energy` enabled.
6. Preview the input.
7. Run ORCA.

### 2. Optimized structure with thermochemistry

1. Load a structure.
2. Choose `Geometry optimization`.
3. Enable `Frequencies / thermochemistry`.
4. Preview the input and run the calculation.
5. Read the summary in the monitor and the saved summary file.

### 3. HOMO-LUMO figure after an ORCA run

1. Complete an ORCA calculation.
2. Click `HOMO LUMO`.
3. Review the automatically generated preview.
4. Save the plot.

### 4. ESP map after an ORCA run

1. Before running ORCA, enable `ESP / MEP package`.
2. Run the ORCA job.
3. Click `ESP map`.
4. Adjust the visual settings in VisMap.
5. Export the image.

### 5. NCI plot after an ORCA run

1. Run an ORCA job that produces a `.wfn` or `.wfx` file.
2. Click `NCI plot`.
3. Confirm the wavefunction file and Multiwfn executable.
4. Generate the NCI/RDG cube data.
5. Adjust the RDG isosurface and color scale.
6. Export the image.

### 6. QTAIM critical points after an ORCA run

1. Run an ORCA job that produces a `.wfn` or `.wfx` file.
2. Click `QTAIM CP`.
3. Confirm the wavefunction file and Multiwfn executable.
4. Run the QTAIM analysis, or load existing results.
5. Open the 3D viewer to inspect the critical-point map.

### 7. Dimer interaction-energy setup

1. Load a dimer structure.
2. Enable the intermolecular interaction workflow (checkbox).
3. Assign fragments (autoamtically or manually). 
4. Check if the assignment is correct (in grahick window, press "View" button) 
4. Choose whether to include relaxed binding analysis and thermodynamic terms.
5. Run ORCA and review the final combined summary.

   ![](images/wiki/orca-output_3.png)
   ![](images/wiki/orca-output_4.png)

## Good to know

- The solvent dropdown is intentionally short and practical.
- `Other solvent...` allows custom solvent entry.
- Custom solvent entries are checked against the expanded internal ORCA solvent library when possible.
- The project summary is shown in the monitor after successful ORCA runs.
- VisMap and Builder structure preview require `numpy` and `pyvista`.
- HOMO-LUMO MO surface rendering requires an ORCA `.out` file, its matching `.gbw` file, `orca_plot`, `numpy`, `pyvista`, and `Pillow`.
- NCI Plotter also requires `numpy`, `pyvista`, and Multiwfn.
- NCI Plotter needs `.wfn` or `.wfx` input; `.out` and `.log` files are not sufficient for NCI/RDG surfaces.
- QTAIM Critical Points Viewer requires `pyvista` and Multiwfn.
- QTAIM Critical Points Viewer needs `.wfn` or `.wfx` input; `.out` and `.log` files are not sufficient for topology analysis.
- NCI + QTAIM Overlay needs matching NCI cube files and QTAIM output files for the same structure.

## Troubleshooting

### ORCA does not start

Check:

- `Settings` -> ORCA executable path
- whether `orca` / `orca.exe` exists and is accessible
- whether the input file was saved correctly

### HOMO-LUMO button does not work

Check:

- that a valid ORCA output exists
- that the HOMO-LUMO script path in `Settings` is correct

For MO surface images, also check:

- that the matching `.gbw` file is next to the ORCA `.out` file
- that `orca_plot` is available from the ORCA installation
- that `numpy`, `pyvista`, and `Pillow` are installed

### ESP map does not work

Check:

- that the ORCA run produced a usable `.wfn`, `.wfx`, or `.fchk` file
- that `orca_2aim` and Multiwfn are available
- that the ESP script path and Python command are correct

### NCI plot does not work

Check:

- that the ORCA run produced a usable `.wfn` or `.wfx` file
- that Multiwfn is available and selected in the NCI Plotter
- that the NCI Plotter script path and Python command are correct
- that the Multiwfn command template matches your installed Multiwfn version

### QTAIM CP does not work

Check:

- that the ORCA run produced a usable `.wfn` or `.wfx` file
- that Multiwfn is available and selected in the QTAIM Critical Points Viewer
- that the QTAIM CP script path and Python 3.9+ command are correct in `Settings`
- that Multiwfn is able to complete the QTAIM critical-point search for your structure
- that the selected file is from a completed calculation, not a failed or unfinished job

### NCI + QTAIM overlay does not open

Check:

- that NCI cube files exist for the selected structure
- that QTAIM critical-point and bond-path files exist for the same structure
- that the overlay script path is correct
- that `numpy` and `pyvista` are installed

### Structure preview does not open

Check:

- `numpy`
- `pyvista`
- `matplotlib`
- `periodictable`

### Interaction workflow finishes partially

This can happen when:

- frozen interaction jobs succeed
- but a later relaxed or thermodynamic follow-up job fails

In that case, the summary should still preserve the successful interaction terms and report a crash note.

## Repository contents

Typical root structure:

```text
README.md
LICENSE
docs/
images/                         # README/wiki screenshots and figures
install/
examples/                       # reserved for future examples
benchmark_sets/
  S22_NCI_benchmark_set/
tools/
  images/                       # shared tool icons
  Orca_input/
  HOMO_LUMO/
  VisMap_5.0/
  NCI_plot/
  NCI_QTAIM_overlay/
  qtaim-cp/
  shared/
```

## Glossary

This short glossary explains the quantum-chemistry terms that appear in the Builder. It is not meant to replace a textbook; it is a quick practical guide to what the options mean before you click `Run Orca`.

### Main Calculation Types

**Single-point energy**  
A calculation of the energy and electronic structure at one fixed geometry. The atoms do not move. Use it when you trust the geometry and want the energy or properties at that structure. FACCTs: [Basic calculation settings](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/basics.html).

**Geometry optimization**  
A calculation that moves the atoms to find a nearby low-energy structure. In practical terms, ORCA changes the geometry step by step until the forces become small. Wiki: [Energy minimization](https://en.wikipedia.org/wiki/Energy_minimization). FACCTs: [Geometry optimizations](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations.html).

**Frequencies / thermochemistry**  
A vibrational-frequency calculation. It is used to check whether an optimized structure is a minimum and to estimate thermochemical quantities such as enthalpy and Gibbs free energy. Wiki: [Molecular vibration](https://en.wikipedia.org/wiki/Molecular_vibration). FACCTs: [Vibrational frequencies](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/frequencies.html).

**TD-DFT / UV-Vis**  
Time-dependent DFT is commonly used to estimate electronic excitations and UV-Vis absorption bands. Wiki: [Time-dependent density functional theory](https://en.wikipedia.org/wiki/Time-dependent_density_functional_theory). FACCTs: [Excited states via RPA, CIS, TD-DFT and SF-TDA](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html).

**NMR calculation**  
A calculation of NMR-related properties such as nuclear shielding, which can be converted or compared with chemical shifts. Wiki: [Nuclear magnetic resonance spectroscopy](https://en.wikipedia.org/wiki/Nuclear_magnetic_resonance_spectroscopy). FACCTs: [Nuclear Magnetic Resonance parameters](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/nmr.html).

### Method Setup

**DFT**  
Density functional theory is a widely used quantum-chemistry approach where the electron density is the central quantity. Wiki: [Density functional theory](https://en.wikipedia.org/wiki/Density_functional_theory). FACCTs: [Density Functional Theory](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/DensityFunctionalTheory.html).

**Functional**  
The chosen DFT approximation, such as B3LYP, PBE0, or wB97X-D. The functional strongly affects energies, geometries, noncovalent interactions, and predicted properties. Wiki: [Density functional theory](https://en.wikipedia.org/wiki/Density_functional_theory). FACCTs: [Density Functional Theory](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/DensityFunctionalTheory.html).

**Basis set**  
The mathematical functions used to describe molecular orbitals. Larger basis sets usually give better accuracy but take more time. Wiki: [Basis set in quantum chemistry](https://en.wikipedia.org/wiki/Basis_set_(chemistry)). FACCTs: [Basis sets](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/basisset.html).

**Dispersion correction**  
An added correction for London dispersion interactions, which are important for crystal packing, pi-stacking, halogen bonding, and many weak contacts. Wiki: [London dispersion force](https://en.wikipedia.org/wiki/London_dispersion_force). FACCTs: [Dispersion corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/dispersioncorrections.html).

**Charge**  
The total charge of the molecule or molecular assembly. A neutral molecule usually has charge `0`; a cation might be `+1`; an anion might be `-1`. Wiki: [Electric charge](https://en.wikipedia.org/wiki/Electric_charge). FACCTs: [Input of coordinates](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/coordinates.html).

**Multiplicity**  
The spin state of the system. Closed-shell organic molecules are usually singlets with multiplicity `1`. Radicals and metal complexes may require other values. Wiki: [Multiplicity in quantum chemistry](https://en.wikipedia.org/wiki/Multiplicity_(chemistry)). FACCTs: [Input of coordinates](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/coordinates.html).

**SCF**  
Self-consistent field procedure. This is the iterative process used to solve the electronic structure. If SCF does not converge, the calculation cannot reliably finish. Wiki: [Self-consistent field](https://en.wikipedia.org/wiki/Self-consistent_field). FACCTs: [Self-Consistent-Field](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/scf.html).

**Tight SCF**  
A stricter SCF convergence setting. It asks ORCA to converge the electronic structure more carefully, which is often useful for cleaner final energies and post-processing. FACCTs: [SCF convergence settings](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/scf.html).

**ORCA grid**  
The numerical integration grid used in DFT calculations. A finer grid can improve accuracy and stability, but it increases calculation time. FACCTs: [Numerical integration grids](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/numericalintegration.html).

**RIJCOSX**  
An ORCA approximation that can speed up hybrid DFT calculations. For many routine calculations, it gives a useful speed improvement with very small practical loss of accuracy. FACCTs: [Resolution-of-the-Identity](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/RI.html).

### Solvent and Environment

**Implicit solvent**  
A calculation where the solvent is represented as a continuous medium instead of explicit solvent molecules. This is useful when you want approximate solution effects without building many solvent molecules. Wiki: [Implicit solvation](https://en.wikipedia.org/wiki/Implicit_solvation). FACCTs: [Implicit solvation](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html).

**CPCM / PCM**  
A common family of continuum solvent models. In ORCA, CPCM settings are often used as part of the solvent setup. Wiki: [Polarizable continuum model](https://en.wikipedia.org/wiki/Polarizable_continuum_model). FACCTs: [Implicit solvation](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html).

**SMD**  
A solvation model commonly used for solution-phase DFT calculations. In the Builder, selecting a solvent for ORCA uses the SMD route through the `%cpcm` block when appropriate. Wiki: [Solvent model](https://en.wikipedia.org/wiki/Solvent_model). FACCTs: [The SMD solvation model](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html).

### Orbitals and Plots

**HOMO**  
Highest occupied molecular orbital. It is the highest-energy orbital that contains electrons. Wiki: [HOMO/LUMO](https://en.wikipedia.org/wiki/HOMO_and_LUMO). FACCTs: [Orbital and density plots](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html).

**LUMO**  
Lowest unoccupied molecular orbital. It is the lowest-energy orbital that is empty in the ground-state electron configuration. Wiki: [HOMO/LUMO](https://en.wikipedia.org/wiki/HOMO_and_LUMO). FACCTs: [Orbital and density plots](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html).

**HOMO-LUMO gap**  
The energy difference between the HOMO and LUMO. It is often used as a rough descriptor of electronic softness, reactivity, or optical/electronic behavior, but it should not be overinterpreted alone. Wiki: [HOMO/LUMO](https://en.wikipedia.org/wiki/HOMO_and_LUMO). FACCTs: [Orbital and density plots](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html).

**ESP / MEP**  
Electrostatic potential, also called molecular electrostatic potential. It helps visualize electron-rich and electron-poor regions on a molecular surface. This is useful for discussing hydrogen bonding, halogen bonding, electrophilic/nucleophilic regions, and molecular recognition. Wiki: [Electric potential](https://en.wikipedia.org/wiki/Electric_potential). FACCTs: [Electrostatic potentials](https://www.faccts.de/docs/orca/6.1/tutorials/prop/esp.html).

**Electron-density surface**  
A molecular surface defined by a chosen electron-density value. Wiki: [Electron density](https://en.wikipedia.org/wiki/Electron_density). FACCTs: [Orbital and density plots](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/plots.html).

**Extrema plotting**  
Marking local minima and maxima of the electrostatic potential. These points can help identify likely attractive or repulsive regions around a molecule.

### NCI Analysis

**NCI**  
Noncovalent interaction analysis. It helps visualize weak interactions such as hydrogen bonds, halogen bonds, pi-stacking, dispersion contacts, and steric repulsion. Wiki: [Non-covalent interactions index](https://en.wikipedia.org/wiki/Non-covalent_interactions_index).

**RDG**  
Reduced density gradient. In NCI plotting, an RDG isosurface is colored by a density-related quantity to show attractive, weak, and repulsive regions. Wiki: [Non-covalent interactions index](https://en.wikipedia.org/wiki/Non-covalent_interactions_index).

**sign(lambda2)rho**  
A common NCI coloring quantity. Negative values are usually associated with attractive interactions, values near zero with weak van der Waals contacts, and positive values with steric repulsion. Interpret the colors together with the structure and chemical context. Wiki: [Non-covalent interactions index](https://en.wikipedia.org/wiki/Non-covalent_interactions_index).

### QTAIM Analysis

**QTAIM**  
Quantum Theory of Atoms in Molecules. It analyzes the topology of the electron density and is often used to discuss bonding, bond paths, and critical points. Wiki: [Atoms in molecules](https://en.wikipedia.org/wiki/Atoms_in_molecules). FACCTs: [Utility programs](https://www.faccts.de/docs/orca/6.1/manual/contents/utilitiesvisualization/index_utilitiesvisualization.html).

**Critical point**  
A point in the electron density where the gradient is zero. Different kinds of critical points correspond to nuclei, bonds, rings, or cages. Wiki: [Atoms in molecules](https://en.wikipedia.org/wiki/Atoms_in_molecules).

**BCP**  
Bond critical point. In QTAIM, a BCP is often discussed in connection with a bond path between atoms. Its presence should be interpreted chemically, not treated as automatic proof of a conventional bond. Wiki: [Atoms in molecules](https://en.wikipedia.org/wiki/Atoms_in_molecules).

**RCP and CCP**  
Ring critical point and cage critical point. These appear in ring-like or cage-like topological features of the electron density. Wiki: [Atoms in molecules](https://en.wikipedia.org/wiki/Atoms_in_molecules).

**Bond path**  
A path through the electron density connecting atoms through a bond critical point. Bond paths are useful for visual discussion of QTAIM results. Wiki: [Atoms in molecules](https://en.wikipedia.org/wiki/Atoms_in_molecules).

### Dimer and Interaction-Energy Terms

**Dimer**  
A pair of molecules or molecular fragments treated together in one calculation. In crystal-engineering work, this is often used to study a contact or molecular pair from a crystal structure. Wiki: [Dimer](https://en.wikipedia.org/wiki/Dimer_(chemistry)). FACCTs: [Counterpoise corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html).

**Fragment A / Fragment B**  
The two parts of a dimer. Correct fragment assignment matters because interaction energies and counterpoise correction depend on which atoms belong to each fragment. FACCTs: [Fragment specification](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/fragmentation.html).

**Interaction energy**  
The energy difference between the dimer and the separated fragments, usually computed to estimate how strongly two fragments interact. Wiki: [Interaction energy](https://en.wikipedia.org/wiki/Interaction_energy). FACCTs: [Counterpoise corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html).

**Binding energy**  
Often used similarly to interaction energy, but the exact meaning depends on whether geometry relaxation, thermal terms, and basis-set corrections are included. Always check what definition is being used. Wiki: [Binding energy](https://en.wikipedia.org/wiki/Binding_energy).

**BSSE**  
Basis-set superposition error. It occurs when fragments in a dimer artificially benefit from each other's basis functions, making the interaction look too strong. Wiki: [Basis set superposition error](https://en.wikipedia.org/wiki/Basis_set_superposition_error). FACCTs: [Counterpoise corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html).

**Counterpoise correction**  
A correction used to estimate and reduce BSSE in interaction-energy calculations. Wiki: [Basis set superposition error](https://en.wikipedia.org/wiki/Basis_set_superposition_error). FACCTs: [Counterpoise corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html).

**Ghost atoms / ghost basis**  
Basis functions placed on atoms that are not actually present as nuclei/electrons in a fragment calculation. They are used in counterpoise correction. FACCTs: [Counterpoise corrections](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/counterpoise.html).

**Relaxation energy**  
The energy change associated with allowing a fragment or complex to relax from one geometry to another. It helps distinguish frozen-geometry interaction from geometry-relaxed binding.

**Delta H and Delta G**  
Changes in enthalpy and Gibbs free energy. These require thermochemical information from frequency calculations and are more expensive than a simple electronic interaction energy. Wiki: [Enthalpy](https://en.wikipedia.org/wiki/Enthalpy) and [Gibbs free energy](https://en.wikipedia.org/wiki/Gibbs_free_energy). FACCTs: [Vibrational frequencies](https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/frequencies.html).

## Examples and Benchmark Data

The `benchmark_sets/S22_NCI_benchmark_set/` folder contains the S22 benchmark structures for training, testing, and evaluation of CrystEngKit calculations. The S22 data are provided as reference examples, not as newly generated CrystEngKit results. The `examples/` folder is currently left empty and reserved for future examples.

When using S22 or other BEGDB-derived benchmark data, cite both the original paper(s) attached to the respective BEGDB record and the BEGDB database paper itself[^begdb].

## Notes

For more detailed reference, extended UI documentation, and workflow notes, see:

- [ORCA_Suite_User_Manual.md](./ORCA_Suite_User_Manual.md)

[^csd]: C. R. Groom, I. J. Bruno, M. P. Lightfoot and S. C. Ward, *The Cambridge Structural Database*, Acta Cryst. B, 2016, 72, 171–179. DOI: [10.1107/S2052520616003954](https://doi.org/10.1107/S2052520616003954)

[^orca]: Neese, F.; Wennmohs, F.; Becker, U.; Riplinger, C. The ORCA quantum chemistry program package. *J. Chem. Phys.* **2020**, *152*, 224108. https://doi.org/10.1063/5.0004608; Neese, F. Software Update: The ORCA Program System—Version 6.0. *WIREs Comput. Mol. Sci.* **2025**, *15*, e70019. https://doi.org/10.1002/wcms.70019

[^orca-site]: Official ORCA / FACCTs site: https://www.faccts.de/orca/ ; ORCA forum and downloads: https://orcaforum.kofo.mpg.de/

[^gaussian]: Frisch, M. J.; Trucks, G. W.; Schlegel, H. B.; Scuseria, G. E.; Robb, M. A.; Cheeseman, J. R.; Scalmani, G.; Barone, V.; Petersson, G. A.; Nakatsuji, H.; et al. *Gaussian 16*, Revision C.01; Gaussian, Inc.: Wallingford, CT, 2016. https://gaussian.com/citation/

[^multiwfn]: Lu, T.; Chen, F. Multiwfn: A multifunctional wavefunction analyzer. *J. Comput. Chem.* **2012**, *33*, 580–592. https://doi.org/10.1002/jcc.22885

[^multiwfn-site]: Official Multiwfn site: http://sobereva.com/multiwfn

[^esp]: Politzer, P.; Murray, J. S. The fundamental nature and role of the electrostatic potential in atoms and molecules. *Theor. Chem. Acc.* **2002**, *108*, 134–142. https://doi.org/10.1007/s00214-002-0363-9; Murray, J. S.; Politzer, P. The electrostatic potential: an overview. *WIREs Comput. Mol. Sci.* **2011**, *1*, 153–163. https://doi.org/10.1002/wcms.19

[^frontier-orbitals]: Fukui, K. Role of frontier orbitals in chemical reactions. *Science* **1982**, *218*, 747–754. https://doi.org/10.1126/science.218.4574.747

[^nci]: Johnson, E. R.; Keinan, S.; Mori-Sánchez, P.; Contreras-García, J.; Cohen, A. J.; Yang, W. Revealing noncovalent interactions. *J. Am. Chem. Soc.* **2010**, *132*, 6498–6506. https://doi.org/10.1021/ja100936w; Contreras-García, J.; Johnson, E. R.; Keinan, S.; Chaudret, R.; Piquemal, J.-P.; Beratan, D. N.; Yang, W. NCIPLOT: A program for plotting noncovalent interaction regions. *J. Chem. Theory Comput.* **2011**, *7*, 625–632. https://doi.org/10.1021/ct100641a

[^qtaim]: Bader, R. F. W. A quantum theory of molecular structure and its applications. *Chem. Rev.* **1991**, *91*, 893–928. https://doi.org/10.1021/cr00005a013; Bader, R. F. W. *Atoms in Molecules: A Quantum Theory*; Oxford University Press: Oxford, 1990.

[^pcm]: Cossi, M.; Rega, N.; Scalmani, G.; Barone, V. Energies, structures, and electronic properties of molecules in solution with the C-PCM solvation model. *J. Comput. Chem.* **2003**, *24*, 669–681. https://doi.org/10.1002/jcc.10189; Tomasi, J.; Mennucci, B.; Cammi, R. Quantum mechanical continuum solvation models. *Chem. Rev.* **2005**, *105*, 2999–3093. https://doi.org/10.1021/cr9904009

[^smd]: Marenich, A. V.; Cramer, C. J.; Truhlar, D. G. Universal solvation model based on solute electron density and on a continuum model of the solvent defined by the bulk dielectric constant and atomic surface tensions. *J. Phys. Chem. B* **2009**, *113*, 6378–6396. https://doi.org/10.1021/jp810292n

[^dft]: Hohenberg, P.; Kohn, W. Inhomogeneous electron gas. *Phys. Rev.* **1964**, *136*, B864–B871. https://doi.org/10.1103/PhysRev.136.B864; Kohn, W.; Sham, L. J. Self-consistent equations including exchange and correlation effects. *Phys. Rev.* **1965**, *140*, A1133–A1138. https://doi.org/10.1103/PhysRev.140.A1133

[^basis-sets]: Weigend, F.; Ahlrichs, R. Balanced basis sets of split valence, triple zeta valence and quadruple zeta valence quality for H to Rn: Design and assessment of accuracy. *Phys. Chem. Chem. Phys.* **2005**, *7*, 3297–3305. https://doi.org/10.1039/B508541A

[^dispersion]: Grimme, S.; Antony, J.; Ehrlich, S.; Krieg, H. A consistent and accurate ab initio parametrization of density functional dispersion correction (DFT-D) for the 94 elements H–Pu. *J. Chem. Phys.* **2010**, *132*, 154104. https://doi.org/10.1063/1.3382344; Grimme, S.; Ehrlich, S.; Goerigk, L. Effect of the damping function in dispersion corrected density functional theory. *J. Comput. Chem.* **2011**, *32*, 1456–1465. https://doi.org/10.1002/jcc.21759; Caldeweyher, E.; Ehlert, S.; Hansen, A.; Neugebauer, H.; Spicher, S.; Bannwarth, C.; Grimme, S. A generally applicable atomic-charge dependent London dispersion correction. *J. Chem. Phys.* **2019**, *150*, 154122. https://doi.org/10.1063/1.5090222

[^orca-runtypes]: Neese, F. *ORCA Manual*, Release 6.1; FACCTs GmbH, 2026. https://www.faccts.de/docs/orca/6.1/manual/

[^tddft]: Runge, E.; Gross, E. K. U. Density-functional theory for time-dependent systems. *Phys. Rev. Lett.* **1984**, *52*, 997–1000. https://doi.org/10.1103/PhysRevLett.52.997

[^scf]: Roothaan, C. C. J. New developments in molecular orbital theory. *Rev. Mod. Phys.* **1951**, *23*, 69–89. https://doi.org/10.1103/RevModPhys.23.69; Roothaan, C. C. J. Self-consistent field theory for open shells of electronic systems. *Rev. Mod. Phys.* **1960**, *32*, 179–185. https://doi.org/10.1103/RevModPhys.32.179

[^rijcosx]: Izsák, R.; Neese, F. An overlap fitted chain of spheres exchange method. *J. Chem. Phys.* **2011**, *135*, 144105. https://doi.org/10.1063/1.3646921; Helmich-Paris, B.; de Souza, B.; Neese, F.; Izsák, R. An improved chain of spheres for exchange algorithm. *J. Chem. Phys.* **2021**, *155*, 104109. https://doi.org/10.1063/5.0058766

[^counterpoise]: Boys, S. F.; Bernardi, F. The calculation of small molecular interactions by the differences of separate total energies. Some procedures with reduced errors. *Mol. Phys.* **1970**, *19*, 553–566. https://doi.org/10.1080/00268977000101561

[^begdb]: Řezáč, J.; Jurečka, P.; Riley, K. E.; Černý, J.; Valdes, H.; Pluháčková, K.; Berka, K.; Řezáč, T.; Pitoňák, M.; Vondrášek, J.; Hobza, P. *Collect. Czech. Chem. Commun.* **2008**, *73*, 1261-1270. http://dx.doi.org/10.1135/cccc20081261 ; http://cccc.uochb.cas.cz/73/10/1261/
