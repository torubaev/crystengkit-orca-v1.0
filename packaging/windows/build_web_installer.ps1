param(
    [string]$CertificateThumbprint = $env:CRYSTENGKIT_SIGN_CERT_SHA1,
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$issPath = Join-Path $PSScriptRoot "CrystEngKit_ORCA_Web.iss"
$outputPath = Join-Path $repoRoot "dist\installer\CrystEngKit-ORCA-WebSetup-1.0.exe"
$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 compiler was not found."
}

$status = git -C $repoRoot status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "Could not read Git status."
}
if ($status) {
    throw "Commit or stash all changes before building. The web installer must target an exact public commit."
}

$repoRef = (git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $repoRef) {
    throw "Could not determine the current Git commit."
}

$remoteMain = git -C $repoRoot ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or -not $remoteMain) {
    throw "Could not read origin/main."
}
$remoteMainCommit = ($remoteMain -split "\s+")[0]
if ($remoteMainCommit -ne $repoRef) {
    throw "Current commit $repoRef is not origin/main. Push it before building the public installer."
}

$zipUrl = "https://github.com/torubaev/crystengkit-orca-v1.0/archive/$repoRef.zip"
$tempZip = Join-Path ([IO.Path]::GetTempPath()) "CrystEngKit-ORCA-$repoRef.zip"
try {
    Invoke-WebRequest -Uri $zipUrl -OutFile $tempZip
    $sha256 = (Get-FileHash -LiteralPath $tempZip -Algorithm SHA256).Hash

    & $iscc "/DMyRepoRef=$repoRef" "/DMyRepoSha256=$sha256" $issPath
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }

    if ($CertificateThumbprint) {
        $certificate = Get-ChildItem Cert:\CurrentUser\My |
            Where-Object { $_.Thumbprint -eq $CertificateThumbprint } |
            Select-Object -First 1
        if (-not $certificate) {
            throw "Code-signing certificate $CertificateThumbprint was not found in Cert:\CurrentUser\My."
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
        throw "The installer is unsigned. Provide -CertificateThumbprint or use -AllowUnsigned only for local testing."
    }

    Write-Host "Built installer: $outputPath"
    Write-Host "Repository commit: $repoRef"
    Write-Host "Repository ZIP SHA-256: $sha256"
    Write-Host "Signature status: $($finalSignature.Status)"
}
finally {
    Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
}
