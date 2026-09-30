param(
    [string]$EvidenceDirectory = (Join-Path $PSScriptRoot ('runs/run-' + (Get-Date -Format 'yyyyMMddTHHmmss'))),
    [string]$TransportRoot = (Join-Path $PSScriptRoot 'out/transport'),
    [int]$Port = 31416
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'native/spacefom/run-interop.ps1') -InputSpool (Join-Path $PSScriptRoot 'data/published-icrf.sf') -EvidenceDirectory ([IO.Path]::GetFullPath($EvidenceDirectory)) -TransportRoot ([IO.Path]::GetFullPath($TransportRoot)) -Port $Port
