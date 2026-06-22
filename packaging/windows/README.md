# Windows Web Installer

CrystEngKit ORCA uses a small .NET Framework web installer. It downloads a ZIP
for one exact Git commit, verifies the archive SHA-256, installs per-user, and
then runs the Python/environment checker. The installer is compiled with the
C# compiler included with Windows; it does not use an Inno Setup bootstrapper.

The installer does not bundle or install ORCA or Multiwfn. Those programs keep
their own licenses and official distribution routes.

## Release Build

1. Commit and push the release changes to `origin/main`.
2. Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_web_installer.ps1 `
  -CertificateThumbprint YOUR_CODE_SIGNING_CERTIFICATE_THUMBPRINT
```

The build script:

- refuses a dirty or unpushed working tree;
- pins the download to the current Git commit;
- downloads the same GitHub archive and embeds its SHA-256;
- compiles `CrystEngKitInstaller.cs` as a Windows AnyCPU executable;
- runs the executable with `/probe` to verify Windows can launch it;
- signs the resulting executable;
- rejects unsigned public builds.

For local testing only, use `-AllowUnsigned`.

The output is:

```text
install\releases\CrystEngKit-ORCA-WebSetup-1.0.2.exe
```

## Linux Release Command

The same commit and archive SHA-256 printed by the Windows build script can be
used for a verified Linux web installation:

```bash
REPO_REF=COMMIT_SHA REPO_SHA256=ARCHIVE_SHA256 \
  sh packaging/linux/install_crystengkit_orca.sh
```
