# Windows Offline Installer

CrystEngKit ORCA uses a full offline Inno Setup package. The EXE contains the
repository files needed by the tools and does not contact GitHub during setup.
ORCA, Multiwfn, Python, and optional Python packages retain their own separate
installation and licensing requirements.

Build from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1 -AllowUnsigned
```

Public releases should be Authenticode-signed by passing
`-CertificateThumbprint`.

Output:

```text
install\releases\CrystEngKit-ORCA-Setup-v.10.exe
```
