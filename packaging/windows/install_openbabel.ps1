$ErrorActionPreference = "Stop"

$downloadUrl = "https://github.com/openbabel/openbabel/releases/download/openbabel-3-1-1/OpenBabel-3.1.1-x64.exe"
$expectedSha256 = "F3BFC11F54174F2A634F9657429886F68281F1E3355BD67E711F49CC57A57E0C"
$temporaryInstaller = Join-Path ([System.IO.Path]::GetTempPath()) ("CrystEngKit-OpenBabel-3.1.1-{0}.exe" -f [guid]::NewGuid().ToString("N"))

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Write-Host "Downloading Open Babel from its official GitHub release..."
    Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $temporaryInstaller

    $actualSha256 = (Get-FileHash -LiteralPath $temporaryInstaller -Algorithm SHA256).Hash
    if ($actualSha256 -ne $expectedSha256) {
        throw "Open Babel download checksum verification failed."
    }

    Write-Host "Checksum verified. Starting the Open Babel installer..."
    & $temporaryInstaller /S
    if ($LASTEXITCODE -ne 0) {
        throw "Open Babel installer exited with code $LASTEXITCODE."
    }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if (Test-Path -LiteralPath $temporaryInstaller) {
        Remove-Item -LiteralPath $temporaryInstaller -Force -ErrorAction SilentlyContinue
    }
}

exit 0
