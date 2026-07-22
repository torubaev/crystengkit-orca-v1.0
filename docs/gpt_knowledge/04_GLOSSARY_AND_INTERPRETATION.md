# Glossary and scientific interpretation boundaries

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

**Strong and weak interaction CPs**  
In the QTAIM viewer, BCPs can be filtered as strong or weak interactions using local CP properties such as H(r), |V|/G, the Laplacian, and rho when available.

**CP energy labels**  
The `CP energy` checkbox shows an energy label for selected CPs, using 0.5V(r) when Multiwfn exports V(r), with units chosen as kJ/mol or kcal/mol.

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

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/charge-multiplicity-open-shell.md

---
    title: Charge, multiplicity, and open-shell systems
    sidebar_position: 5
    description: Defining and validating the electronic state.
    ---

    Coordinates do not uniquely determine charge or spin multiplicity. Enter these values from the chemical model.

## Total system

For multiplicity \(M\):

\[
M = 2S + 1
\]

where \(S\) is the total spin quantum number.

## Fragments

In an interaction-energy calculation, fragment charges and multiplicities must be compatible with the total dimer state and with the chosen physical dissociation model. Ionic, radical, antiferromagnetically coupled, and transition-metal systems require special care.

## Validation

For open-shell calculations, inspect at least:

- \(\langle S^2\rangle\) and spin contamination;
- spin populations;
- singly occupied or corresponding orbitals;
- convergence from alternative initial guesses;
- plausible alternative spin states;
- broken-symmetry interpretation when used.

For transition-metal complexes, also consider oxidation state, ligand field, relativistic treatment, basis/ECP coverage, and whether single-reference DFT is adequate.

**WARNING:**
The lowest SCF energy found from one initial guess is not automatically the physically correct electronic state.

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/crystal-vs-optimized-geometry.md

---
    title: Crystal geometry versus optimized geometry
    sidebar_position: 4
    description: Choosing a geometry model that matches the scientific question.
    ---

    A crystal geometry contains the effects of packing, temperature, disorder treatment, refinement constraints, and the experimental environment. An isolated-molecule optimization removes most of those constraints and can produce a different conformation.

## Crystal-geometry single point

Use a fixed experimental geometry when the question concerns the electronic structure of the observed arrangement or a specific intermolecular contact. Report that the calculation is a single point on experimental coordinates and describe any hydrogen-atom adjustment.

## Isolated optimization

Use an isolated optimization when the question concerns a gas-phase or implicit-solvent minimum. Do not describe the result as the crystal geometry after the atoms have moved.

## Constrained or partial optimization

A constrained optimization may be appropriate when preserving an experimental heavy-atom framework while relaxing hydrogen positions or selected coordinates. Report every constraint.

## Comparing energies

Do not compare energies from different geometries as though they were pure interaction energies. Geometry relaxation introduces deformation contributions.

For dimers:

\[
\Delta E_\mathrm{bind} =
E_{AB}^{\mathrm{relaxed}} -
E_A^{\mathrm{relaxed}} -
E_B^{\mathrm{relaxed}}
\]

is conceptually different from an interaction energy evaluated with monomers frozen in the dimer geometry.

**NOTE:**
The correct geometry protocol is determined by the physical question, not by which option gives the most attractive energy or most visually striking surface.

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/disorder-symmetry-hydrogen.md

---
    title: Disorder, symmetry, and hydrogen atoms
    sidebar_position: 3
    description: Constructing one explicit molecular model from crystallographic data.
    ---

    ## Disorder

A disordered crystallographic model can represent multiple mutually exclusive local arrangements. Quantum chemistry generally requires one explicit arrangement per calculation.

Possible strategies include:

- calculate one refined disorder component at a time;
- construct chemically plausible ordered local models;
- compare multiple alternatives;
- omit unresolved solvent only when omission is scientifically justified and reported.

Do not combine atoms from mutually exclusive disorder components merely because they appear in one CIF atom-site loop.

## Symmetry

Crystal contacts often involve symmetry-generated partners. A calculation on the asymmetric unit alone may omit the interaction of interest.

Prepare the exact dimer or cluster explicitly. Record the symmetry operation and translation used to generate each partner.

## Hydrogen atoms

Hydrogen positions may be constrained, idealized, omitted, disordered, or derived from X-ray data with limited nuclear-position accuracy. Their treatment can materially affect hydrogen bonding, proton transfer, ESP, NCI, QTAIM, and energy calculations.

Record whether hydrogen atoms were:

- taken directly from the refined structure;
- normalized to standard distances;
- generated by a molecular editor;
- optimized while heavy atoms were fixed;
- fully optimized.

## Partial occupancies

Partial occupancy is not a fractional atom in a conventional molecular wavefunction. Choose a definite structural model or use a method specifically designed for statistical/periodic disorder.

**CAUTION:**
The visualizer may draw an inferred bond across a close contact or fail to draw a chemically meaningful metal–ligand bond. Use it as a geometry check, not a bond-order authority.

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/input-files-and-structure-quality.md

---
    title: Input files and structure quality
    sidebar_position: 2
    description: What CIF, XYZ, and ORCA input files contain and omit.
    ---

    ## CIF

A CIF may contain unit-cell parameters, symmetry, atom sites, occupancies, displacement parameters, disorder models, restraints, and refinement metadata. A quantum-chemical calculation, however, requires an explicit set of nuclei and an electronic state.

Before using CIF coordinates:

- identify the relevant data block;
- inspect occupancies and alternate locations;
- decide which disorder component is chemically intended;
- generate any required symmetry-related molecules or contacts;
- remove duplicated or unwanted atoms;
- check hydrogen atoms;
- identify solvent and counterions;
- verify whether the model represents an asymmetric unit, molecule, dimer, or larger aggregate.

CrystEngKit should be given the explicit model you intend to calculate. Do not assume that a visually plausible import has reconstructed every crystallographic relationship required for the scientific question.

## XYZ

XYZ provides an atom count, comment line, and Cartesian coordinates. It normally does not provide:

- formal charge;
- spin multiplicity;
- bond orders;
- fragments;
- periodicity;
- crystallographic symmetry;
- occupancy;
- method settings.

## ORCA input

An ORCA input may contain far more information than the Builder exposes as GUI controls. If an existing input uses advanced blocks, manually compare the original and regenerated files.

## Geometry precision

Do not round coordinates unnecessarily. Preserve the source file and record every transformation applied to it.

**WARNING:**
A calculation on an unintended symmetry fragment or mixed disorder model may converge perfectly and still be chemically meaningless.

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/reproducibility.md

---
    title: File organization and reproducibility
    sidebar_position: 6
    description: Preserving the information needed to repeat calculations and figures.
    ---

    A reproducible project separates source structures, calculations, analyses, and final figures.

Recommended layout:

```text
project/
  00_source_structures/
  01_models/
  02_orca_jobs/
  03_wavefunctions/
  04_analysis/
  05_figures/
  06_tables_and_text/
  README_method_record.md
```

For each job, retain:

- original and processed geometry;
- generated input;
- complete output;
- `.gbw` and other restart/property files needed for analysis;
- exported `.wfn` or `.wfx`;
- Multiwfn command sequence and log;
- generated cube/grid/topology files;
- CrystEngKit settings or JSON files;
- final figure plus camera, isovalue, colour range, and resolution;
- software versions.

## Naming

Use unique, descriptive basenames. Include model and method information in a method record rather than creating filenames so long that external programs or operating systems fail.

## Immutable completed jobs

Do not edit a completed input or output in place. Copy the job to a new directory or create a new basename for each changed protocol.

## Figure comparability

For a series, define a figure protocol before final export:

- same surface definition;
- same scalar range;
- same colormap direction;
- same molecular style;
- same projection;
- same image dimensions;
- same orientation when structurally meaningful.

:::important
A publication figure should be traceable to one exact calculation and one exact set of rendering parameters.

## Source: tmp/crystengkit_documentation/docs/manual/general-considerations/scope-and-responsibility.md

---
    title: Scope and responsibility
    sidebar_position: 1
    description: What automation can verify and what remains the user's scientific responsibility.
    ---

    CrystEngKit automates file preparation, external-program calls, selected parsing, and visualization. These are procedural tasks. The scientific model remains the user’s responsibility.

## Three levels of validity

A defensible result must pass three distinct tests.

### 1. Syntactic validity

The input is readable by ORCA or Multiwfn. Keywords, coordinates, and file paths are accepted.

### 2. Numerical validity

The requested calculation completes with appropriate convergence and without disqualifying warnings.

### 3. Chemical validity

The molecular model, electronic state, computational method, and interpretation address the intended chemical question.

CrystEngKit can help with the first level and parts of the second. It cannot guarantee the third.

## Required pre-calculation decisions

Before running, establish:

- chemical identity and protonation state;
- total and fragment charges;
- spin multiplicity and plausible alternative spin states;
- whether crystal coordinates, an extracted cluster, or an optimized geometry answer the question;
- which solvent or environment is represented;
- whether counterions or solvent molecules are included;
- treatment of disorder and symmetry;
- method and basis-set suitability.

## Required post-calculation checks

After running, establish:

- convergence to the intended state;
- stability or plausibility of the wavefunction;
- preservation of the intended connectivity;
- stationary-point character when relevant;
- sensitivity to model or method choices where the conclusion depends on them;
- reproducibility of every reported figure and energy.

:::important
Automation should reduce transcription errors, not remove expert review. Every generated input and every scientific summary should be read before publication.
