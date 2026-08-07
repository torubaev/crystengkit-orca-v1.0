# Builder workspace architecture

The Builder is the application shell. Its top navigation remains visible while
the central workspace changes between Input, HOMO-LUMO, ESP / VisMap, NCI,
QTAIM, TD-DFT, and Torsion Scan pages.

- The active tool name is shown at the left and its navigation button is
  highlighted.
- Each page is mounted once in the shared content area. Navigation raises the
  selected page instead of destroying and rebuilding it, preserving current
  entries, selections, results, and scroll positions.
- The Input button returns to the Builder page.
- A `.crystengkit-workspace.json` file beside the loaded geometry stores the
  explicit state dictionary published by each tool. Calculation data is not
  copied between projects.
- Confirmations, file choosers, and errors remain ordinary modal dialogs.

PyVista remains a native graphics window. ESP, NCI, and QTAIM open a narrow
always-on-top visualization-control panel beside the viewer. Controls update the
existing scene in real time. Closing that panel leaves the viewer open, and the
Viewer controls button on the corresponding page restores it. Native window
reparenting is not used.

Class-based tools expose reusable page components. Compatibility wrappers may
still be used by development or direct-launch entry points, but normal user
navigation is provided by the persistent Builder workspace and one Tk event
loop.
