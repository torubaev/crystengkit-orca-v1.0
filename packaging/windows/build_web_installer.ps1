param(
    [string]$CertificateThumbprint = $env:CRYSTENGKIT_SIGN_CERT_SHA1,
    [switch]$PinCurrentCommit,
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sourcePath = Join-Path $PSScriptRoot "CrystEngKitInstaller.cs"
$licensePath = Join-Path $repoRoot "LICENSE"
$outputPath = Join-Path $repoRoot "install\releases\CrystEngKit-ORCA-Setup-v.10_web.exe"
$compiler = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "The Windows .NET Framework C# compiler was not found."
}

$repoRef = "origin/main"
$zipUrl = "https://github.com/torubaev/crystengkit-orca-v1.0/archive/refs/heads/main.zip"
$sha256 = ""
if ($PinCurrentCommit) {
    $status = git -C $repoRoot status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Git status."
    }
    if ($status) {
        throw "Commit or stash all changes before building a pinned installer."
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
        throw "Current commit $repoRef is not origin/main. Push it before building a pinned installer."
    }

    $zipUrl = "https://github.com/torubaev/crystengkit-orca-v1.0/archive/$repoRef.zip"
}

$tempZip = Join-Path ([IO.Path]::GetTempPath()) "CrystEngKit-ORCA-web.zip"
$tempSource = Join-Path ([IO.Path]::GetTempPath()) "CrystEngKitInstaller-web.cs"
try {
    Invoke-WebRequest -Uri $zipUrl -OutFile $tempZip
    if ($PinCurrentCommit) {
        $sha256 = (Get-FileHash -LiteralPath $tempZip -Algorithm SHA256).Hash
    }

    $source = Get-Content -LiteralPath $sourcePath -Raw
    $source = $source.Replace("__REPO_URL__", $zipUrl)
    $source = $source.Replace("__REPO_SHA256__", $sha256)
    Set-Content -LiteralPath $tempSource -Value $source -Encoding UTF8

    New-Item -ItemType Directory -Path (Split-Path $outputPath) -Force | Out-Null
    & $compiler `
        /nologo `
        /target:winexe `
        /platform:anycpu `
        /optimize+ `
        /out:$outputPath `
        /win32icon:"$repoRoot\tools\images\orca_builder.ico" `
        /reference:System.dll `
        /reference:System.Core.dll `
        /reference:System.Drawing.dll `
        /reference:System.Windows.Forms.dll `
        /reference:System.IO.Compression.dll `
        /reference:System.IO.Compression.FileSystem.dll `
        /reference:Microsoft.CSharp.dll `
        /resource:"$licensePath",LICENSE `
        $tempSource
    if ($LASTEXITCODE -ne 0) {
        throw "C# installer compilation failed with exit code $LASTEXITCODE."
    }

    $probe = Start-Process -FilePath $outputPath -ArgumentList "/probe" -Wait -PassThru
    if ($probe.ExitCode -ne 0) {
        throw "The built installer failed its Windows launch probe with exit code $($probe.ExitCode)."
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
    Write-Host "Repository source: $repoRef"
    Write-Host "Repository ZIP SHA-256: $(if ($sha256) { $sha256 } else { 'not pinned; latest main is downloaded at install time' })"
    Write-Host "Installer SHA-256: $((Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash)"
    Write-Host "Signature status: $($finalSignature.Status)"
}
finally {
    Remove-Item -LiteralPath $tempZip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tempSource -Force -ErrorAction SilentlyContinue
}
