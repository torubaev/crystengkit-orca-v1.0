# Windows Installers

The full offline Inno Setup package contains the
repository files needed by the tools and does not contact GitHub during setup.
ORCA, Multiwfn, Python, and optional Python packages retain their own separate
installation and licensing requirements. Setup offers Microsoft MPI Runtime as
a checked optional component for parallel ORCA calculations. If it is skipped
or unavailable, CrystEngKit defaults ORCA inputs to one process.

Build the offline installer from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1 -AllowUnsigned
```

Public releases should be Authenticode-signed by passing
`-CertificateThumbprint`.

Output:

```text
install\releases\CrystEngKit-ORCA-Setup-<version>.exe
```

The web installer is a small .NET bootstrapper. It downloads and verifies the
full Inno installer for the same version, then launches that package. The Inno
package is the single installation engine: its stable `AppId` makes the same
package perform either a clean installation or an in-place update.

Build the full installer first, then build the web bootstrapper:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_web_installer.ps1 -AllowUnsigned
```

Output:

```text
install\releases\CrystEngKit-ORCA-Setup-<version>-web.exe
```

Both builders read `app_metadata\version.json`. Change the version there once
before creating a release; the GUI and package filenames then use the same
`MAJOR.MINOR.PATCH` value.

Publish the full installer, web bootstrapper, and both generated `.sha256`
files in the same GitHub release tagged `v<version>`. The bootstrapper embeds
the full installer's exact release URL and SHA-256 checksum.
