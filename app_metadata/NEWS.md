# CrystEngKit-ORCA news

## Version 1.1.13 — August 8, 2026

CrystEngKit-ORCA 1.1.13 improves the stability of analysis viewers and Windows installation.

### What is new

- More reliable switching between NCI and QTAIM workspaces.
- PyVista viewers and visual controls can be reopened independently without rerunning Multiwfn.
- NCI surface opacity changes only the surface, leaving the molecule and QTAIM graphics intact.
- NCI+QTAIM overlays now use the cube files belonging to the active wavefunction instead of ambiguous folder-wide discovery.
- Better Multiwfn discovery and automatic configuration when it is installed outside `PATH`.
- More reliable ESP cube generation and diagnostic logging.
- Cleaner per-user Windows installation and managed Python environment detection.
- Improved HOMO–LUMO contact-sheet responsiveness and progress reporting.

### Installation

Download either installer from the [v1.1.13 release page](https://github.com/torubaev/crystengkit-orca-v1.0/releases/tag/v1.1.13):

- The full installer contains the application files.
- The web installer downloads and verifies the matching full installer.

Projects and user settings are preserved when updating an existing installation.

---

This page is the shared startup-news page for all CrystEngKit-ORCA releases. It can be updated without rebuilding the installers.
