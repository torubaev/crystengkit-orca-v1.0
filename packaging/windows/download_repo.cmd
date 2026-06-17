@echo off
setlocal EnableExtensions

set "APP_DIR=%~dp0"
set "REPO_ZIP_URL=%~1"
if "%REPO_ZIP_URL%"=="" set "REPO_ZIP_URL=https://github.com/torubaev/crystengkit-orca-v1.0/archive/refs/heads/main.zip"

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
