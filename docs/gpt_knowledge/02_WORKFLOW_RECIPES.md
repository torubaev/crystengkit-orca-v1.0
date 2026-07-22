# CrystEngKit workflow recipes

Step-oriented procedures. Always ask the user to verify structure, charge, multiplicity, method, convergence, and generated results.


## Source: tmp/crystengkit_documentation/docs/quick-start/configure-a-calculation.md


---
    title: Configure a calculation
    sidebar_position: 5
    description: Select the calculation type and electronic-structure settings without treating defaults as universal recommendations.
    ---

    Select the target calculation and enter the model settings.



## Calculation type

Choose the operation actually needed:

- single-point energy or property calculation at fixed coordinates;
- geometry optimization;
- frequencies or thermochemistry;
- TD-DFT or another exposed excited-state calculation;
- NMR-related input;
- ESP/wavefunction preparation;
- dimer interaction energy.

Each choice has different validation requirements. An optimization should be followed by a frequency calculation when a verified stationary point and thermochemistry are needed.

## Electronic-structure method

The Builder exposes method and basis-set lists, but presence in a list is not a recommendation. Check:

- element coverage;
- compatibility with effective core potentials or relativistic treatment;
- suitability for noncovalent interactions;
- open-shell or transition-metal requirements;
- cost for the system size;
- consistency with literature or benchmark data relevant to the property.

## Dispersion and solvent

Select a dispersion correction only when it is compatible with the chosen functional and protocol. Select an implicit solvent only when the intended model is a solvated species rather than a gas-phase or crystal-environment calculation.

## Resources

Set processors and memory conservatively. ORCA memory directives are commonly interpreted per process or per computational worker, depending on the setting and module. Confirm the generated input and consult the ORCA manual for the exact version used.

## Preview the input

Use **Input preview** in the shared right panel to generate or refresh the current ORCA text, then read the complete generated input. Verify:

- keyword line;
- `%` blocks;
- charge and multiplicity;
- coordinate count and ordering;
- paths and file references;
- fragment or ghost-atom definitions;
- resource directives.

:::important
The input preview is the last point at which a wrong charge, multiplicity, geometry, or method can be caught before computational time is spent. When the job is started, the same right-side panel switches to **Job monitor** automatically.


## Source: tmp/crystengkit_documentation/docs/quick-start/first-figure.md


---
    title: Create a first figure
    sidebar_position: 8
    description: Open a companion analysis tool and save a reproducible figure.
    ---

    Choose one analysis from the Builder’s top panel after a successful calculation.

For a first test, a HOMO–LUMO energy diagram is usually the least dependent on external volumetric analysis. ESP, NCI, and QTAIM require wavefunction data and Multiwfn.



## Example: HOMO–LUMO diagram

1. Open **HOMO LUMO**.
2. Select the completed ORCA or Gaussian output.
3. Confirm that the detected occupied and virtual orbitals correspond to the output.
4. Select the desired orbital window.
5. preview the diagram;
6. save PNG or SVG.



## Record the settings

For any saved figure, retain:

- source calculation and file basename;
- program versions;
- geometry source;
- surface or contour isovalue;
- scalar colour range and colormap;
- camera orientation and scale;
- molecular display style;
- image dimensions;
- any filtered or hidden components.

**TIP:**
Use the same orientation, isovalue, colour range, and rendering style for figures intended for direct comparison.


## Source: tmp/crystengkit_documentation/docs/quick-start/index.md


---
    title: Quick Start
    sidebar_position: 1
    description: The shortest defensible route through CrystEngKit.
    ---

    The Quick Start is operational. It shows where to click and what to verify, but it does not recommend a universal computational method.

Follow these pages in order:

1. [Install and launch](install-and-launch.md)
2. [Load a structure](load-a-structure.md)
3. [Inspect the molecular model](inspect-the-model.md)
4. [Configure a calculation](configure-a-calculation.md)
5. [Save and run ORCA](save-and-run.md)
6. [Monitor and validate the job](monitor-and-validate.md)
7. [Create a first figure](first-figure.md)



A suitable first test is a small, neutral, closed-shell organic molecule with a known charge and no disorder. Do not begin with a transition-metal complex, radical, highly charged species, disordered CIF, or very large aggregate unless you already know how to validate the electronic structure.


## Source: tmp/crystengkit_documentation/docs/quick-start/inspect-the-model.md


---
    title: Inspect the molecular model
    sidebar_position: 4
    description: Verify the explicit atoms, fragments, and geometry before preparing an input.
    ---

Open **Structure preview** before choosing the computational method. The preview uses a compact PyVista window with a black background, so it is meant for quick geometry inspection rather than replacing a full molecular editor.



Check the following.

## Composition

- Are all expected atoms present?
- Are any solvent molecules, counterions, or duplicated disorder components present unintentionally?
- Are hydrogen atoms present where required?
- Does the elemental composition match the intended chemical species?

## Connectivity and fragments

The viewer may infer bonds for display or fragment assignment. Bond inference is geometrical and can fail for unusual bond lengths, metals, multicentre bonding, weak contacts, or disorder.

For a dimer calculation, verify that fragment A and fragment B correspond exactly to the intended monomers.

## Geometry source

Record whether the coordinates are:

- experimental crystal coordinates;
- symmetry-expanded crystal coordinates prepared elsewhere;
- an extracted cluster;
- an isolated-molecule geometry;
- a previously optimized geometry.

## Charge and multiplicity

Determine the total charge and spin multiplicity independently from the chemical model. For a dimer or counterpoise calculation, verify fragment charges and multiplicities as well as the total values.

**WARNING:**
A plausible ball-and-stick image can conceal an incorrect electronic model. Charge and multiplicity are not recoverable reliably from coordinates alone.

## Save a clean structure when necessary

If the imported model is not the exact calculation target, correct it in an appropriate crystallographic or molecular editor, save a new explicit structure, and reload that file. Keep the unmodified experimental source separately.


## Source: tmp/crystengkit_documentation/docs/quick-start/install-and-launch.md


---
    title: Install and launch
    sidebar_position: 2
    description: Install dependencies, identify external programs, and start the Builder.
    ---

    ## 1. Obtain CrystEngKit

Use a tagged release when available. If working from the repository, record the commit used.

## 2. Install Python dependencies

From the repository root:

```bash
python -m pip install -r requirements.txt
```

The current requirements file lists NumPy, PyVista, Matplotlib, periodictable, Gemmi, and Pillow.

Tkinter is supplied separately by some Python or Linux distributions. If the GUI fails before opening, verify that Tkinter can be imported by the same Python executable used to launch CrystEngKit.

## 3. Install external chemistry programs

Install ORCA from the official ORCA/FACCTs distribution route. Install Multiwfn from its official distribution route. Do not copy executables from an unverified third party.

CrystEngKit does not redistribute or automatically license these programs.

## 4. Platform launch routes

Windows checker/launcher:

```bat
install\install.bat
```

Linux or macOS repository checker:

```bash
sh install/run_checker.sh
```

Direct launch:

```bash
python tools/Orca_input/orca_input.py
```



## 5. Confirm executable identity

On Linux, “Orca” may also refer to the GNOME screen reader. CrystEngKit contains checks intended to reject that program as the quantum-chemistry executable. Nevertheless, verify that the selected executable is the ORCA quantum-chemistry program.

## 6. Open Settings

Confirm paths for:

- ORCA;
- Multiwfn;
- companion scripts, if paths have been changed from the repository layout;
- Python interpreter used by the visualization tools.

**WARNING:**
Installing a Python package into one interpreter does not install it into every Python interpreter. When a module is reported missing, compare the executable shown by CrystEngKit with the executable used for `pip`.


## Source: tmp/crystengkit_documentation/docs/quick-start/load-a-structure.md


---
    title: Load a structure
    sidebar_position: 3
    description: Open a CIF, XYZ, or supported ORCA input and identify what was imported.
    ---

    Open the ORCA Input Builder and select the structure file.

Supported starting points documented for the Builder are:

- `.cif`;
- `.xyz`;
- supported ORCA `.inp` content.



## CIF input

A CIF is a crystallographic description, not automatically a chemically complete quantum-chemical model. It may describe an asymmetric unit, contain disorder or partial occupancy, omit or constrain hydrogen atoms, and rely on symmetry to generate the intended molecular aggregate.

After loading a CIF, do not proceed directly to calculation. Continue to [Inspect the molecular model](inspect-the-model.md).

## XYZ input

An XYZ file contains an explicit atom list and Cartesian coordinates. It does not encode bond orders, formal charge, spin multiplicity, crystallographic symmetry, or disorder. Those properties must be established independently.

## Existing ORCA input

When loading an existing input, distinguish between:

- geometry imported from the file;
- settings successfully recognized by the Builder;
- settings retained only in the text but not represented in GUI controls;
- settings that may be changed when the input is regenerated.

Always compare the final generated input with the original before execution.

**NOTE:**
The displayed molecule is not proof that every atom, fragment, charge, and multiplicity is correct. It proves only that the program constructed a view from the explicit coordinates it currently holds.


## Source: tmp/crystengkit_documentation/docs/quick-start/monitor-and-validate.md


---
    title: Monitor and validate the job
    sidebar_position: 7
    description: Distinguish process completion from scientifically valid completion.
    ---

After pressing **Run Orca**, the shared right panel switches automatically to **Job monitor**. Follow the live output, status, progress, and elapsed time there.



## Program-level success

CrystEngKit checks completed ORCA output for the normal-termination marker. This is necessary but not sufficient.

A job can terminate normally while still being scientifically unsuitable because of:

- an unintended charge or multiplicity;
- convergence to the wrong electronic state;
- significant spin contamination;
- an optimization that did not reach the desired structure;
- imaginary frequencies;
- an inappropriate model chemistry;
- a geometry that changed into an unintended species;
- insufficient numerical accuracy.

## Minimum validation

For every calculation, inspect:

- ORCA version;
- final energy and termination;
- SCF convergence;
- warnings;
- charge and multiplicity;
- final geometry, where applicable.

For an optimization, inspect the convergence table and final coordinates. For a minimum, perform and inspect a frequency calculation. For an open-shell or transition-metal system, inspect spin expectation values, populations, orbital character, and alternative electronic states as appropriate.

## Analysis-file generation

ESP, NCI, and QTAIM require a real wavefunction file such as `.wfn` or `.wfx`. MO surface generation from ORCA requires the matching `.out` and `.gbw` and access to `orca_plot`.

**WARNING:**
Do not continue to visualization when the underlying electronic-structure calculation is unvalidated. A polished surface can make an incorrect calculation look convincing.


## Source: tmp/crystengkit_documentation/docs/quick-start/save-and-run.md


---
    title: Save and run ORCA
    sidebar_position: 6
    description: Save the generated input, start ORCA, and preserve a recoverable job folder.
    ---

    Save the `.inp` file in a dedicated job directory. Avoid running unrelated calculations with the same basename in the same directory because ORCA utilities and restart files are basename-dependent.

A useful folder contains:

```text
project/
  structure_source/
  job_01/
    system.inp
    system.out
    system.gbw
    generated_analysis_files/
```



Click **Input preview** in the shared right panel to generate or refresh the current input text, inspect it, and save it with **Save input file**. Then click **Run Orca**. The Builder launches the selected ORCA executable, directs output to the job output file, and switches the shared right panel to **Job monitor** automatically.

Before leaving a long job unattended, confirm that:

- the output header identifies the expected ORCA program and version;
- the coordinates and atom count are correct;
- charge and multiplicity match the intended system;
- the selected basis is found for every element;
- the number of processes and memory are plausible;
- the SCF iterations have begun rather than failing during input parsing.

**CAUTION:**
Do not overwrite a `.gbw` file needed for restart or orbital analysis. Keep completed jobs immutable and start modified calculations in a new folder or with a new basename.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-1-cif-to-orca.md


---
    title: Exercise 1 — CIF to inspected ORCA input
    sidebar_position: 2
    description: Prepare a defensible explicit molecular model from crystallographic coordinates.
    ---

    ## Objective

Create an ORCA input from a CIF while documenting every structural choice.

## Procedure

1. Copy the original CIF into a read-only source folder.
2. Open it in a crystallographic viewer.
3. identify the intended molecule, dimer, or cluster;
4. inspect disorder, occupancy, symmetry, solvent, counterions, and hydrogen atoms;
5. export or construct one explicit Cartesian model;
6. load the explicit model into CrystEngKit;
7. open Structure Preview;
8. verify composition, atom count, fragments, and close contacts;
9. enter independently determined charge and multiplicity;
10. choose a low-cost test single point suitable only for input validation;
11. inspect and save the generated input;
12. compare the coordinate list with the explicit model.



## Success criteria

- no mixed disorder components;
- no unintended symmetry omissions or duplicates;
- documented hydrogen treatment;
- explicit charge and multiplicity;
- final coordinate list matches the intended model;
- source and processed structures are both preserved.

## Reflection

Explain why the selected model answers the intended question and what crystal-environment effects it omits.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-2-s22.md


---
    title: Exercise 2 — S22 dimer interaction energy
    sidebar_position: 3
    description: Test fragment assignment and counterpoise workflow without inventing benchmark equivalence.
    ---

    ## Objective

Use one structure from the repository’s S22-related benchmark material to test the dimer workflow.

## Procedure

1. Select one small dimer from `benchmark_sets/S22_NCI_benchmark_set/`.
2. load the explicit structure;
3. inspect both monomers and the intermolecular geometry;
4. enable the dimer interaction-energy option;
5. inspect automatic fragment assignment;
6. correct it manually if required;
7. verify fragment charges and multiplicities;
8. generate the dimer, monomer, and ghost-basis/counterpoise input components;
9. inspect all generated coordinates and ghost definitions;
10. run the calculation;
11. record raw and CP-corrected energies exactly as defined by the generated summary;
12. compare only with a reference using the same geometry and after stating the methodological differences.



## Success criteria

- A and B partition all atoms exactly once;
- each component uses consistent settings;
- every component terminates normally;
- raw and CP-corrected definitions are reported explicitly;
- no claim of reproducing the high-level S22 reference protocol is made unless the protocols are identical.

## Reflection

Discuss why a workflow-consistency test and a benchmark-method reproduction are not the same claim.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-3-esp.md


---
    title: Exercise 3 — ESP surface
    sidebar_position: 4
    description: Generate and document one electrostatic-potential surface.
    ---

    ## Objective

Produce one reproducible ESP-mapped electron-density surface.

## Procedure

1. complete and validate an electronic-structure calculation;
2. obtain the matching `.wfn`, `.wfx`, or `.fchk`;
3. open ESP/VisMap;
4. confirm input provenance and Multiwfn path;
5. generate the density and ESP grids;
6. select a density isovalue;
7. choose a numerical ESP range and colormap;
8. inspect extrema if required;
9. save the figure;
10. record all settings in a sidecar text file.



## Success criteria

- surface is not clipped by the grid;
- molecular geometry aligns with the surface;
- scalar bar and units are visible;
- density isovalue and ESP range are recorded;
- source calculation is identifiable.

## Reflection

Describe which apparent features change when the density isovalue or colour range changes and which numerical data remain unchanged.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-4-nci-qtaim.md


---
    title: Exercise 4 — NCI and QTAIM
    sidebar_position: 5
    description: Generate two complementary density analyses for the same dimer.
    ---

    ## Objective

Create NCI and QTAIM views from one wavefunction and combine them without treating co-location as an energy measurement.

## Procedure

1. select a validated dimer `.wfn` or `.wfx`;
2. generate NCI data through Multiwfn;
3. save one NCI view with documented RDG isovalue and scalar range;
4. open the QTAIM viewer with the same wavefunction;
5. run or edit the Multiwfn command sequence;
6. verify CP classes against the Multiwfn log;
7. verify that displayed paths come from exported path coordinates;
8. save an unfiltered QTAIM view;
9. open the NCI + QTAIM overlay;
10. confirm coordinate and atom-order agreement.



## Success criteria

- one common source wavefunction;
- no `.out` or `.log` substituted for a wavefunction file;
- raw Multiwfn logs preserved;
- CP/path counts checked;
- NCI and QTAIM settings recorded;
- interpretation remains topological/qualitative unless separate energetic analysis is supplied.

## Reflection

Identify what each method adds and why neither surface colour nor a BCP alone equals the full dimer interaction energy.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-5-homo-lumo.md


---
    title: Exercise 5 — HOMO–LUMO and MO surfaces
    sidebar_position: 6
    description: Build a frontier-orbital diagram and a consistently oriented orbital set.
    ---

    ## Objective

Generate a HOMO–LUMO diagram and a small MO contact sheet from one completed ORCA calculation.

## Procedure

1. load the ORCA output in the HOMO–LUMO tool;
2. verify orbital numbering and occupations;
3. choose a window such as HOMO−2 to LUMO+2;
4. save the energy diagram;
5. provide the matching `.gbw`;
6. generate MO cubes with `orca_plot`;
7. select one isovalue for the series;
8. orient one saved orbital view;
9. use **Use view for all** to reproduce camera and scale;
10. export the contact sheet.



## Success criteria

- detected orbitals match the output;
- open-shell character is handled explicitly if present;
- one isovalue, camera, and scale are used across the set;
- source `.out`, `.gbw`, cubes, and view settings are retained;
- the orbital gap is not labelled as an experimental optical gap.

## Reflection

Describe orbital localization and phase without claiming a transition assignment not supported by excited-state analysis.


## Source: tmp/crystengkit_documentation/docs/workshop/exercise-6-reporting.md


---
    title: Exercise 6 — Reproducible reporting
    sidebar_position: 7
    description: Turn one completed workflow into a methods paragraph, figure caption, and archive.
    ---

    ## Objective

Prepare a publication-ready record without relying on generated prose alone.

## Deliverables

1. **Methods paragraph** containing geometry source, electronic method, basis, dispersion, solvent, charge, multiplicity, software versions, and analysis procedure.
2. **Figure caption** containing surface definition, isovalue, scalar range, units, and meaning of colours.
3. **Data archive** containing input, output, wavefunction, grids/topology, logs, settings, and final figure.
4. **Validation note** listing convergence checks and limitations.

## Procedure

1. generate CrystEngKit’s summary;
2. compare it line by line with the input and output;
3. correct incomplete or misleading wording;
4. add missing scientific context;
5. add primary references;
6. create a checksummed archive or deposit in an appropriate repository.



## Success criteria

Another researcher can identify exactly what was calculated and can reconstruct the plotted object without guessing a default.


## Source: tmp/crystengkit_documentation/docs/workshop/introduction.md


---
    title: Workshop introduction
    sidebar_position: 1
    description: Scope, prerequisites, and rules for the guided exercises.
    ---

    The workshop is designed for users who can identify the chemical species and basic electronic state but are new to the CrystEngKit interface.

It does not provide universal “best settings.” Each exercise emphasizes model inspection and reproducibility.

## Prerequisites

- working CrystEngKit installation;
- ORCA available for calculation exercises;
- Multiwfn available for ESP, NCI, and QTAIM exercises;
- a small test structure;
- permission to use and share any structure included in a report.

## Exercises

1. [CIF to inspected ORCA input](exercise-1-cif-to-orca.md)
2. [Dimer interaction energy with an S22 structure](exercise-2-s22.md)
3. [ESP surface](exercise-3-esp.md)
4. [NCI and QTAIM](exercise-4-nci-qtaim.md)
5. [HOMO–LUMO and MO surfaces](exercise-5-homo-lumo.md)
6. [Reproducible reporting](exercise-6-reporting.md)

## Rule for expected results

These exercises define structural and procedural success criteria. They deliberately do not invent expected energies, extrema, gaps, or critical-point properties. Numerical reference values should be added only after the exact files and computational protocols are frozen and independently verified.


## Source: tools/TD_DFT/TD_DFT_WORKFLOW_EXAMPLES.md


# TD-DFT workflow examples

## Vertical excitation only

For 10 singlet roots with TD-DFT, **Show ORCA block** generates:

```text
%tddft
  NRoots 10
  TDA false
  MaxDim 10
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
  MaxDim 10
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

## Absorption and UV-Vis analysis

Load a completed TD-DFT/TDA `.out` in the post-processing tab. The module
detects associated files beside the output, parses excited-state energies and
oscillator strengths, and presents the state table together with stick or
Gaussian-broadened spectra. State tables, spectrum data, and PNG/SVG figures
use editable, descriptive save suggestions based on the loaded calculation.

## Natural transition orbital analysis

Select an excited state and validate the Multiwfn executable. **Generate all
analyses** prepares the selected-state package and generates the dominant NTO
hole/electron cube pair from the matching `.gbw` through the validated
Multiwfn workflow. Existing valid cubes are reused unless regeneration is
requested. The signed cube viewer supports molecular overlays, bonds, labels,
positive/negative isosurfaces, opacity, screenshots, and cube export.

## Fluorescence emission sequence

Start from a completed absorption calculation and select the emitting root.
The Builder prepares an excited-state optimization targeting that root, then a
vertical-emission calculation at the optimized excited-state geometry. Method,
basis, solvent, charge, multiplicity, TD-DFT/TDA choice, and root count are
carried forward from the source workflow. Generated files use numbered,
method- and step-specific names so absorption, optimization, and emission
outputs remain distinguishable.
