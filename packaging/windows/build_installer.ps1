param(
    [string]$CertificateThumbprint = $env:CRYSTENGKIT_SIGN_CERT_SHA1,
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$issPath = Join-Path $PSScriptRoot "CrystEngKit_ORCA.iss"
$outputPath = Join-Path $repoRoot "install\releases\CrystEngKit-ORCA-Setup-v.10.exe"
$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 compiler was not found."
}

New-Item -ItemType Directory -Path (Split-Path $outputPath) -Force | Out-Null
& $iscc $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

if ($CertificateThumbprint) {
    $certificate = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Thumbprint -eq $CertificateThumbprint } |
        Select-Object -First 1
    if (-not $certificate) {
        throw "Code-signing certificate $CertificateThumbprint was not found."
    }
    $signature = Set-AuthenticodeSignature `
        -FilePath $outputPath `
        -Certificate $certificate `
        -TimestampServer "http://timestamp.digicert.com" `
        -HashAlgorithm SHA256
    if ($signature.Status -ne "Valid") {
        throw "Installer signing failed: $($signature.StatusMessage)"
    }
}

$finalSignature = Get-AuthenticodeSignature -FilePath $outputPath
if ($finalSignature.Status -ne "Valid" -and -not $AllowUnsigned) {
    Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
    throw "The installer is unsigned. Provide -CertificateThumbprint or use -AllowUnsigned."
}

Write-Host "Built full offline installer: $outputPath"
Write-Host "Installer SHA-256: $((Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash)"
Write-Host "Signature status: $($finalSignature.Status)"
