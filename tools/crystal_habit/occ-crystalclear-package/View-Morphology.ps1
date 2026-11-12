[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PlyPath
)

$resolved = (Resolve-Path -LiteralPath $PlyPath).Path
if ([IO.Path]::GetExtension($resolved) -ne '.ply') { throw 'Expected an OCC .ply morphology file.' }
Write-Host "Opening Wulff morphology mesh: $resolved"
Write-Host 'If Windows has no PLY association, import the file into ParaView, MeshLab, or Blender.'
Start-Process -FilePath $resolved

