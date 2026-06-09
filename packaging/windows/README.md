# Windows Installer

This folder builds a single Windows setup executable for CrystEngKit ORCA using
Inno Setup.

The installer packages CrystEngKit itself, creates Start Menu/Desktop shortcuts,
and can run the existing installation checker after setup. It does not bundle
ORCA or Multiwfn; those programs must still be installed from their official
sources because of their own licenses and distribution routes.

By default, the installer performs a normal per-machine Windows installation in:

```text
C:\Program Files\CrystEngKit ORCA
```

Administrator permission is required.

## Build

1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
2. From the repository root, run:

```bat
ISCC.exe packaging\windows\CrystEngKit_ORCA.iss
```

The output installer is written to:

```text
dist\installer\CrystEngKit-ORCA-Setup-1.0.exe
```

## Installed Shortcuts

- `ORCA Input Builder`
- `Installation Checker`
- optional Desktop shortcut for `ORCA Input Builder`

The launcher uses `pyw.exe`, `pythonw.exe`, `py.exe`, or `python.exe`, in that
order. Python 3.9 or newer is still required for this installer route.

## Later Fully Frozen EXE Route

A future PyInstaller build can bundle Python into native tool executables, but
that needs separate handling for companion tools launched by the ORCA Input
Builder. This Inno Setup route is the lower-risk professional installer first.
