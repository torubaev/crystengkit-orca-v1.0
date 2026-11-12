[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$CifPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string[]]$Solvents,

    [ValidateSet('ce-b3lyp', 'ce-hf', 'ce-1p', 'ce-2p', 'ce-5p', 'gfn2', 'gfn2-xtb', 'xtb', 'williams', 'dma', 'fit', 'w99')]
    [string]$Model = 'ce-1p',

    [ValidateSet('smd', 'cosmo-rs', 'none')]
    [string]$SolvationModel = 'smd',

    [ValidateRange(0.1, 100.0)]
    [double]$Radius = 4.1,

    [ValidateRange(1, 10000)]
    [int]$SurfaceEnergies = 0,

    [ValidateRange(0.0, 100.0)]
    [double]$SurfaceDMin = 0.0,

    [ValidateRange(1, 256)]
    [int]$Threads = 4,

    [string]$OutputDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'OCC-CrystalClear\runs'),

    [string]$OccExe = (Join-Path $PSScriptRoot 'occ-0.9.7-windows-x86_64\bin\occ.exe'),

    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($SurfaceEnergies -le 0 -and $SurfaceDMin -le 0) {
    throw 'Specify either -SurfaceDMin (preferred) or -SurfaceEnergies.'
}
if ($SurfaceEnergies -gt 0 -and $SurfaceDMin -gt 0) {
    throw 'Use only one of -SurfaceDMin or -SurfaceEnergies.'
}
if (-not (Test-Path -LiteralPath $OccExe -PathType Leaf)) {
    throw "OCC executable not found: $OccExe"
}

$occRoot = Split-Path -Parent (Split-Path -Parent $OccExe)
$occData = Join-Path $occRoot 'share\occ'
if (-not (Test-Path -LiteralPath (Join-Path $occData 'basis\def2-svp.json'))) {
    throw "OCC data directory is incomplete: $occData"
}

$version = (& $OccExe --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^occ 0\.9\.7\b') {
    throw "Expected OCC 0.9.7, received: $version"
}

$resolvedCif = (Resolve-Path -LiteralPath $CifPath).Path
$cifStem = [IO.Path]::GetFileNameWithoutExtension($resolvedCif)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runRoot = Join-Path $OutputDirectory ("{0}_{1}_{2}" -f $cifStem, $Model, $stamp)
if (Test-Path -LiteralPath $runRoot) {
    throw "Refusing to overwrite existing run directory: $runRoot"
}

function ConvertTo-SafeName([string]$Value) {
    $safe = $Value -replace '[^A-Za-z0-9._-]+', '_'
    if ([string]::IsNullOrWhiteSpace($safe)) { throw "Invalid solvent name: $Value" }
    return $safe.Trim('_')
}

function Export-GmfFacets {
    param(
        [Parameter(Mandatory)][string]$GmfPath,
        [Parameter(Mandatory)][string]$Solvent,
        [Parameter(Mandatory)][string]$CsvPath
    )
    $rows = [Collections.Generic.List[object]]::new()
    $h = $null; $k = $null; $l = $null
    foreach ($line in Get-Content -LiteralPath $GmfPath) {
        if ($line -match '^\s*miller:\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)') {
            $h = [int]$Matches[1]; $k = [int]$Matches[2]; $l = [int]$Matches[3]
            continue
        }
        if ($null -ne $h -and $line -match '^\s*([-+0-9.Ee]+)\s+\d+\s+\d+\s+([-+0-9.Ee]+)') {
            $rows.Add([pscustomobject]@{
                Solvent = $Solvent
                H = $h; K = $k; L = $l
                Offset = [double]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture)
                SurfaceEnergy = [double]::Parse($Matches[2], [Globalization.CultureInfo]::InvariantCulture)
                SourceGmf = $GmfPath
            })
            $h = $null; $k = $null; $l = $null
        }
    }
    if ($rows.Count -eq 0) { throw "No facet energies found in $GmfPath" }
    $rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding utf8
    return $rows
}

$surfaceArgument = if ($SurfaceDMin -gt 0) {
    "--surface-d-min=$($SurfaceDMin.ToString([Globalization.CultureInfo]::InvariantCulture))"
} else {
    "--surface-energies=$SurfaceEnergies"
}

$planned = foreach ($solvent in $Solvents) {
    $safeSolvent = ConvertTo-SafeName $solvent
    $arguments = @(
        "--threads=$Threads", '--verbosity=2', 'cg', 'input.cif',
        "--model=$Model", "--solvent=$solvent", "--solvation-model=$SolvationModel",
        "--radius=$($Radius.ToString([Globalization.CultureInfo]::InvariantCulture))",
        $surfaceArgument
    )
    [pscustomobject]@{ Solvent = $solvent; SafeName = $safeSolvent; Arguments = $arguments }
}

if ($PlanOnly) {
    $planned | ForEach-Object { '"{0}" {1}' -f $OccExe, ($_.Arguments -join ' ') }
    return
}

New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
$env:OCC_DATA_PATH = $occData

$manifest = [ordered]@{
    created = (Get-Date).ToString('o')
    occ_version = $version
    occ_executable = $OccExe
    occ_data_path = $occData
    source_cif = $resolvedCif
    model = $Model
    solvation_model = $SolvationModel
    radius_angstrom = $Radius
    surface_energies = $SurfaceEnergies
    surface_d_min_angstrom = $SurfaceDMin
    solvents = $Solvents
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runRoot 'run-manifest.json') -Encoding utf8

$allFacets = [Collections.Generic.List[object]]::new()
$failures = [Collections.Generic.List[string]]::new()

foreach ($item in $planned) {
    $solventDir = Join-Path $runRoot $item.SafeName
    New-Item -ItemType Directory -Path $solventDir | Out-Null
    Copy-Item -LiteralPath $resolvedCif -Destination (Join-Path $solventDir 'input.cif')
    $commandLine = '"{0}" {1}' -f $OccExe, ($item.Arguments -join ' ')
    $commandLine | Set-Content -LiteralPath (Join-Path $solventDir 'command.txt') -Encoding utf8

    Push-Location -LiteralPath $solventDir
    try {
        & $OccExe @($item.Arguments) 2>&1 | Tee-Object -FilePath 'occ.log'
        $exitCode = $LASTEXITCODE
        "OCC_EXIT_CODE=$exitCode" | Set-Content -LiteralPath 'exit_code.txt' -Encoding ascii
        if ($exitCode -ne 0) { throw "OCC exited with code $exitCode" }
        if (-not (Select-String -LiteralPath 'occ.log' -SimpleMatch 'A job well done' -Quiet)) {
            throw 'OCC log did not contain its completion marker.'
        }

        $result = Get-ChildItem -LiteralPath . -Filter '*_cg_results.json' -File | Select-Object -First 1
        $gmf = Get-ChildItem -LiteralPath . -Filter "*_$($item.SafeName).gmf" -File | Select-Object -First 1
        $ply = Get-ChildItem -LiteralPath . -Filter "*_$($item.SafeName).ply" -File | Select-Object -First 1
        if (-not $result) { throw 'No *_cg_results.json file was generated.' }
        if (-not $gmf) { $gmf = Get-ChildItem -LiteralPath . -Filter '*.gmf' -File | Where-Object Name -NotMatch 'vacuum' | Select-Object -First 1 }
        if (-not $ply) { $ply = Get-ChildItem -LiteralPath . -Filter '*.ply' -File | Where-Object Name -NotMatch 'vacuum' | Select-Object -First 1 }
        if (-not $gmf -or -not $ply) { throw 'Expected solvated GMF/PLY morphology files were not generated.' }

        $facetCsv = Join-Path $solventDir 'facet-energies.csv'
        $rows = Export-GmfFacets -GmfPath $gmf.FullName -Solvent $item.Solvent -CsvPath $facetCsv
        foreach ($row in $rows) { $allFacets.Add($row) }
    } catch {
        $failures.Add("$($item.Solvent): $($_.Exception.Message)")
    } finally {
        Pop-Location
    }
}

if ($allFacets.Count -gt 0) {
    $allFacets | Export-Csv -LiteralPath (Join-Path $runRoot 'facet-energy-comparison.csv') -NoTypeInformation -Encoding utf8
}
if ($failures.Count -gt 0) {
    $failures | Set-Content -LiteralPath (Join-Path $runRoot 'failures.txt') -Encoding utf8
    throw "One or more solvent calculations failed. See $runRoot\failures.txt"
}

Write-Host "Completed solvent comparison: $runRoot"
Write-Host "Facet comparison: $(Join-Path $runRoot 'facet-energy-comparison.csv')"

