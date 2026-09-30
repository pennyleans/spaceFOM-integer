param(
    [Parameter(Mandatory=$true)][string]$InputSpool,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$TransportRoot = (Join-Path $PSScriptRoot '../../out/transport')
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'refusing existing evidence directory' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$originalPath = $env:PATH
$env:PATH = "$TransportRoot\runtime\bin;$env:PATH"
try {
    $accepted = [IO.File]::ReadAllBytes($InputSpool)
    $stream = [IO.MemoryStream]::new($accepted)
    $reader = [IO.BinaryReader]::new($stream)
    $stream.Position = 12
    $bodyCount = $reader.ReadInt32()
    for ($i=0; $i -lt $bodyCount; $i++) {
        $idLength = $reader.ReadInt32(); $stream.Position += $idLength
        $nameLength = $reader.ReadInt32(); $stream.Position += $nameLength + 16
    }
    $frameOffset = [int]$stream.Position
    $recordSize = 40 + 112 * ($bodyCount + 1)
    $reader.Dispose(); $stream.Dispose()
    $cases = @(
        @{ name='bad_magic'; offset=0; bytes=[byte[]]@(0); expected='spool magic mismatch' },
        @{ name='skipped_tick'; offset=$frameOffset+$recordSize; bytes=[BitConverter]::GetBytes([long]99); expected='ticks must be contiguous' },
        @{ name='nonfinite_state'; offset=$frameOffset+40; bytes=[BitConverter]::GetBytes([double]::NaN); expected='nonfinite state' },
        @{ name='invalid_quaternion'; offset=$frameOffset+40+48; bytes=[BitConverter]::GetBytes([double]2); expected='quaternion not normalized' },
        @{ name='wrong_time'; offset=$frameOffset+40+104; bytes=[BitConverter]::GetBytes([double]7529673601); expected='state time disagrees' }
    )
    $results = @()
    foreach ($case in $cases) {
        $candidate = [byte[]]$accepted.Clone()
        [Array]::Copy($case.bytes,0,$candidate,$case.offset,$case.bytes.Length)
        $path = Join-Path $EvidenceDirectory ($case.name+'.sf')
        [IO.File]::WriteAllBytes($path,$candidate)
        $output = & "$TransportRoot\adapter-build\Release\spacefom-publisher.exe" $path "$TransportRoot\TrickHLA\FOMs\SpaceFOM" 'rti://127.0.0.1:1' 'invalid_probe' 2>&1
        $code = $LASTEXITCODE
        $output | Set-Content -LiteralPath (Join-Path $EvidenceDirectory ($case.name+'.log'))
        if ($code -eq 0 -or "$output" -notmatch $case.expected) { throw "rejection did not match: $($case.name)" }
        $results += @{ name=$case.name; exit=$code; expected=$case.expected; rejected_before_connection=$true }
    }
    $sentinel = Join-Path $EvidenceDirectory 'existing-output.sf'
    [IO.File]::WriteAllText($sentinel,'immutable sentinel')
    $before = (Get-FileHash -LiteralPath $sentinel).Hash
    $output = & "$TransportRoot\adapter-build\Release\spacefom-observer.exe" $sentinel 'rti://127.0.0.1:1' 'invalid_probe' 2>&1
    $code = $LASTEXITCODE
    if ($code -eq 0 -or "$output" -notmatch 'refusing existing output' -or (Get-FileHash -LiteralPath $sentinel).Hash -ne $before) { throw 'existing output protection failed' }
    $results += @{ name='existing_observer_output'; exit=$code; unchanged=$true }
    $results | ConvertTo-Json | Set-Content -LiteralPath "$EvidenceDirectory\rejections.json"
    Get-Content -LiteralPath "$EvidenceDirectory\rejections.json"
}
finally { $env:PATH = $originalPath }
