# Experimental single-window workspace

Branch: `experimental/single-window-tools`

The Builder remains the application window. Its top plate stays visible while
the central workspace changes between tools:

```text
Active tool name                         persistent tool navigation
------------------------------------------------------------------
                    active tool workspace
```

Navigation rules:

- The active tool name is shown at the left.
- Every navigation button remains visible and the active one is highlighted.
- Every page is mounted once in the same content cell. Switching calls
  `tkraise()` on the selected page; it does not remove, destroy, or rebuild
  interfaces, so unsaved entries, selections, results, and scroll positions
  remain in memory.
- A `.crystengkit-workspace.json` file beside the loaded geometry stores the
  explicit state dictionary returned by each tool. Builder no longer inspects
  arbitrary Tk variables.
- Tool panels never store calculation data in the session file and never copy
  results between projects.
- Short confirmations, file choosers, and errors may still be modal dialogs.
- Heavy PyVista/VTK viewers require explicit embedded-viewer adapters; native
  window reparenting is not used.

Converted workspace tools:

- HOMO-LUMO
- ESP / VisMap
- NCI Plotter
- QTAIM Critical Points
- TD-DFT
- Torsion Scan

The Builder has its own explicit navigation button. Class-based standalone
tools use the same reusable panels inside thin optional window wrappers. The
procedural ESP launcher accepts a panel parent and does not start a second Tk
event loop in Builder mode.
