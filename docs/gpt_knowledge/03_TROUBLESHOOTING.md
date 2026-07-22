# CrystEngKit troubleshooting reference

Use symptom, likely cause, checks, and safe next action. Distinguish normal termination from scientific validity.


## Source: tmp/crystengkit_documentation/docs/faq.md


---
    title: FAQ and troubleshooting
    sidebar_position: 4
    description: Common installation, execution, file, and interpretation problems.
    ---

    ## General

### Is CrystEngKit a quantum-chemistry program?

No. It is a GUI and coordination/visualization suite. ORCA performs ORCA calculations, and Multiwfn performs the wavefunction analyses used by the ESP, NCI, and QTAIM workflows.

### Does a generated input guarantee a valid calculation?

No. It may be syntactically valid while containing the wrong structure, charge, multiplicity, method, or resources.

### Can I calculate directly from any CIF?

Not safely without inspection. Resolve disorder, occupancies, symmetry-generated partners, hydrogen atoms, solvent, and the intended molecular aggregate first.

## Installation

### The GUI does not start

Run from a terminal with the same Python executable and read the traceback:

```bash
python tools/Orca_input/orca_input.py
```

Test:

```bash
python -c "import tkinter, numpy, matplotlib, pyvista, periodictable, gemmi, PIL"
```

Install missing packages into that exact interpreter.

### ORCA is not found

Select the ORCA executable in Settings or add its directory to the environment expected by the launcher. Confirm that the executable is the quantum-chemistry ORCA, not the GNOME screen reader.

### Multiwfn is not found

Select the Multiwfn executable manually. Verify that it runs directly and that the job directory is writable.

### PyVista opens a blank or unusable window

Check the graphics driver, OpenGL support, remote-desktop environment, and PyVista/VTK installation. Test a minimal PyVista example in the same Python environment.

## ORCA jobs

### How can I run several saved inputs sequentially?

Use **Add to Queue**, then open **Queue Jobs**. Inspect and reorder the named
queue before starting it. Queue state is saved in JSON between sessions.

### Why did the AI assistant report a truncated output?

The completion marker at the end of the clipboard payload was not received.
Paste again or reduce the supplied output. Do not trust a timing or convergence
diagnosis made from a paste that lacks the marker.

### The process stopped without a normal-termination message

Treat the job as failed or incomplete. Inspect the last output section for input, SCF, memory, disk, MPI, geometry, or external-termination errors.

### ORCA terminated normally. Is the result valid?

Normal termination confirms process completion only. Inspect convergence, warnings, electronic state, geometry, and property-specific validation.

### The wrong “orca” executable runs on Ubuntu

Ubuntu may contain the GNOME Orca screen reader. Use the full path to the ORCA quantum-chemistry executable. CrystEngKit attempts to detect and reject the screen reader, but the path should still be checked.

### A `.gbw` disappeared or was overwritten

ORCA files are basename-dependent. Avoid reusing completed-job basenames in the same directory. Restore from backup and rerun with a unique basename if necessary.

## NCI

### Why does NCI reject my `.out` file?

An ORCA text output does not contain the full volumetric wavefunction required for RDG analysis. Use a matching `.wfn` or `.wfx`.

### The NCI surface is missing or clipped

Check that Multiwfn generated the expected grids, the grid covers the entire contact, and the selected RDG isovalue intersects the data. Inspect the raw grid and log before changing visualization settings.

### Can I convert green surface area into interaction energy?

Not directly. NCI is a qualitative density-topology visualization. Use a separately defined energetic method for interaction energy.

## ESP

### Two molecules have different colours even though their extrema are similar

The figures may use different automatic scalar ranges. Re-render with one common numerical range and identical surface isovalue.

### Extrema move when I change the density isovalue

That is expected because the extrema are searched on a different surface. Report the surface definition.

## QTAIM

### Multiwfn runs but no critical points appear

The automated command sequence may not match the installed Multiwfn version or settings. Run the file manually once, record the correct menu sequence, paste it into the editable command box, and preserve the log.

### The displayed sticks and QTAIM paths disagree

Molecular sticks can be inferred from distances. QTAIM paths should come from exported path coordinates. They represent different objects.

### Does a BCP prove a chemical bond?

No. It is a topological feature of the electron density. Interpretation requires context and does not directly supply interaction energy.

## HOMO–LUMO

### Is the plotted HOMO–LUMO gap the optical gap?

Not generally. It is an orbital-energy difference. Optical excitation energies require an appropriate excited-state calculation and interpretation.

### MO surfaces have different apparent sizes

Check that all orbitals use the same isovalue, camera projection, and scale. Use the documented saved-view and **Use view for all** workflow.

## TD-DFT

### Why is the UV-Vis spectrum available but NTO generation disabled?

The spectrum uses excitation data parsed from the `.out`. NTO generation also
requires the matching `.gbw` and a validated Multiwfn executable.

### Why is an analysis row marked disabled?

The required associated file or a release-verified workflow is unavailable.
The module disables unsupported paths rather than inventing Multiwfn commands.

## Dimer energies

### Why are raw and CP-corrected values different?

Counterpoise changes the monomer basis by including ghost functions of the partner, reducing finite-basis borrowing. Report both definitions and the correction sign explicitly.

### Is a dimer interaction energy a lattice energy?

No. A lattice energy requires the extended crystal and many interactions, including long-range and many-body effects.


## Source: tmp/crystengkit_documentation/docs/support.md


---
    title: Support and issue reports
    sidebar_position: 8
    description: How to provide a reproducible problem report.
    ---

    Before reporting a problem, identify which layer failed:

1. CrystEngKit GUI or parser;
2. Python/Tk/PyVista environment;
3. ORCA;
4. `orca_plot` or `orca_2aim`;
5. Multiwfn;
6. graphics driver or OpenGL;
7. scientific input rather than software execution.

## Minimum issue report

Include:

- operating system and version;
- CrystEngKit release tag or commit;
- Python executable path and version;
- ORCA and Multiwfn versions;
- exact tool used;
- exact action that failed;
- complete error message;
- relevant log file;
- smallest non-confidential input that reproduces the problem;
- whether the same ORCA or Multiwfn step works when run directly.

Remove confidential or unpublished coordinates before posting publicly.

## Files commonly needed

Depending on the tool, a report may require:

- `.cif`, `.xyz`, or `.inp`;
- ORCA `.out` and matching `.gbw`;
- `.wfn`, `.wfx`, or `.fchk`;
- Multiwfn log;
- `CPprop.txt`, `paths.pdb`, or other exported topology files;
- CrystEngKit error log;
- a screenshot showing the complete window and error, not a cropped message alone.

**TIP:**
Use a small test system first. A reduced example distinguishes a software defect from memory, disk, convergence, or system-size limitations.


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
