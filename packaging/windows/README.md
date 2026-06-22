# Windows Installers

The full offline Inno Setup package contains the
repository files needed by the tools and does not contact GitHub during setup.
ORCA, Multiwfn, Python, and optional Python packages retain their own separate
installation and licensing requirements.

Build the offline installer from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1 -AllowUnsigned
```

Public releases should be Authenticode-signed by passing
`-CertificateThumbprint`.

Output:

```text
install\releases\CrystEngKit-ORCA-Setup-v.10.exe
```

The alternative web installer is a much smaller .NET executable. It downloads
and verifies the ZIP for the exact public Git commit embedded at build time.
Commit and push all source changes before building it:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_web_installer.ps1 -AllowUnsigned
```

Output:

```text
install\releases\CrystEngKit-ORCA-Setup-v.10_web.exe
```
