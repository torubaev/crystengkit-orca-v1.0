param(
    [string]$CertificateThumbprint = $env:CRYSTENGKIT_SIGN_CERT_SHA1,
    [string]$FullInstallerPath = "",
    [switch]$AllowUnsigned
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sourcePath = Join-Path $PSScriptRoot "CrystEngKitInstaller.cs"
$versionPath = Join-Path $repoRoot "app_metadata\version.json"
$appVersion = (Get-Content -LiteralPath $versionPath -Raw | ConvertFrom-Json).version
if ($appVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid application version '$appVersion' in $versionPath. Expected MAJOR.MINOR.PATCH."
}

$fullInstallerName = "CrystEngKit-ORCA-Setup-$appVersion.exe"
if (-not $FullInstallerPath) {
    $FullInstallerPath = Join-Path $repoRoot "install\releases\$fullInstallerName"
}
$FullInstallerPath = [IO.Path]::GetFullPath($FullInstallerPath)
if (-not (Test-Path -LiteralPath $FullInstallerPath -PathType Leaf)) {
    throw "Build the full Inno installer first. Expected: $FullInstallerPath"
}
$fullInstallerHash = (Get-FileHash -LiteralPath $FullInstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$packageUrl = "https://github.com/torubaev/crystengkit-orca-v1.0/releases/download/v$appVersion/$fullInstallerName"
$outputPath = Join-Path $repoRoot "install\releases\CrystEngKit-ORCA-Setup-$appVersion-web.exe"
$compiler = "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "The Windows .NET Framework C# compiler was not found."
}

$tempSource = Join-Path ([IO.Path]::GetTempPath()) "CrystEngKitInstaller-web.cs"
try {
    $source = Get-Content -LiteralPath $sourcePath -Raw
    $source = $source.Replace("__APP_VERSION__", $appVersion)
    $source = $source.Replace("__PACKAGE_URL__", $packageUrl)
    $source = $source.Replace("__PACKAGE_SHA256__", $fullInstallerHash)
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
        /reference:Microsoft.CSharp.dll `
        $tempSource
    if ($LASTEXITCODE -ne 0) {
        throw "C# bootstrapper compilation failed with exit code $LASTEXITCODE."
    }

    $probe = Start-Process -FilePath $outputPath -ArgumentList "/probe" -Wait -PassThru
    if ($probe.ExitCode -ne 0) {
        throw "The built bootstrapper failed its Windows launch probe with exit code $($probe.ExitCode)."
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
            throw "Bootstrapper signing failed: $($signature.StatusMessage)"
        }
    }

    $finalSignature = Get-AuthenticodeSignature -FilePath $outputPath
    if ($finalSignature.Status -ne "Valid" -and -not $AllowUnsigned) {
        Remove-Item -LiteralPath $outputPath -Force -ErrorAction SilentlyContinue
        throw "The bootstrapper is unsigned. Provide -CertificateThumbprint or use -AllowUnsigned only for local testing."
    }

    $bootstrapperHash = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumPath = "$outputPath.sha256"
    Set-Content -LiteralPath $checksumPath -Value "$bootstrapperHash  $([IO.Path]::GetFileName($outputPath))" -Encoding ASCII
    Write-Host "Built web bootstrapper: $outputPath"
    Write-Host "Full installer asset: $packageUrl"
    Write-Host "Embedded full-installer SHA-256: $fullInstallerHash"
    Write-Host "Bootstrapper SHA-256: $bootstrapperHash"
    Write-Host "Checksum asset: $checksumPath"
    Write-Host "Signature status: $($finalSignature.Status)"
}
finally {
    Remove-Item -LiteralPath $tempSource -Force -ErrorAction SilentlyContinue
}
