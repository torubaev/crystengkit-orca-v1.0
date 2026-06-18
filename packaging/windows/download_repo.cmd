@echo off
setlocal EnableExtensions

set "REPO_ZIP_URL=%~1"
set "EXPECTED_SHA256=%~2"
set "APP_DIR=%~3"

if "%REPO_ZIP_URL%"=="" (
    echo ERROR: Repository ZIP URL was not provided.
    exit /b 2
)
if "%EXPECTED_SHA256%"=="" (
    echo ERROR: Expected SHA-256 was not provided.
    exit /b 2
)
if "%APP_DIR%"=="" (
    echo ERROR: Installation directory was not provided.
    exit /b 2
)

set "TEMP_ROOT=%TEMP%\CrystEngKit_ORCA_download_%RANDOM%%RANDOM%"
set "ZIP_PATH=%TEMP_ROOT%\repo.zip"
set "EXTRACT_DIR=%TEMP_ROOT%\extract"

echo Downloading CrystEngKit ORCA from:
echo   %REPO_ZIP_URL%
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$app = Resolve-Path -LiteralPath $env:APP_DIR;" ^
  "$tempRoot = $env:TEMP_ROOT;" ^
  "$zipPath = $env:ZIP_PATH;" ^
  "$extractDir = $env:EXTRACT_DIR;" ^
  "New-Item -ItemType Directory -Force -Path $tempRoot, $extractDir | Out-Null;" ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "Invoke-WebRequest -Uri $env:REPO_ZIP_URL -OutFile $zipPath;" ^
  "$actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash;" ^
  "if ($actualHash -ne $env:EXPECTED_SHA256) { throw ('Repository archive checksum mismatch. Expected {0}, got {1}.' -f $env:EXPECTED_SHA256, $actualHash) }" ^
  "Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force;" ^
  "$root = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1;" ^
  "if (-not $root) { throw 'Downloaded archive did not contain a repository folder.' }" ^
  "Get-ChildItem -LiteralPath $root.FullName -Force | ForEach-Object {" ^
  "  Copy-Item -LiteralPath $_.FullName -Destination $app -Recurse -Force" ^
  "};" ^
  "Remove-Item -LiteralPath $tempRoot -Recurse -Force;" ^
  "Write-Host 'Repository files installed into:' $app"

if errorlevel 1 (
    echo.
    echo ERROR: Could not download or extract the CrystEngKit ORCA repository.
    echo Please check the internet connection and GitHub access, then run this installer again.
    pause
    exit /b 1
)

echo.
echo Repository download finished.
exit /b 0
