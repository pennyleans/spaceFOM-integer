param(
    [string]$Recording = (Join-Path $PSScriptRoot 'recordings/published-icrf.sf'),
    [string]$Output = (Join-Path $PSScriptRoot ('runs/run-' + (Get-Date -Format 'yyyyMMddTHHmmss'))),
    [int]$Port = 31416
)
# Runs the RTI, publisher and observer on loopback from a transport package and compares the recordings.
$ErrorActionPreference = 'Stop'
$windows = $env:OS -eq 'Windows_NT'
$bin = Join-Path $PSScriptRoot 'bin'
$suffix = if ($windows) { '.exe' } else { '' }
$Recording = (Resolve-Path $Recording).Path
if (Test-Path $Output) { throw "Output directory already exists: $Output" }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
New-Item -ItemType Directory -Path $Output | Out-Null
$Output = (Resolve-Path $Output).Path
if ($windows) { $env:PATH = "$bin;$env:PATH" } else { $env:LD_LIBRARY_PATH = "$bin$([IO.Path]::PathSeparator)$env:LD_LIBRARY_PATH" }
$url = "rti://127.0.0.1:$Port"
$federation = "orbital_$Port"

function Start-Federate([string]$Name, [string[]]$Arguments, [string]$Log) {
    $options = @{
        FilePath = Join-Path $bin "$Name$suffix"; ArgumentList = $Arguments; PassThru = $true
        RedirectStandardOutput = Join-Path $Output "$Log.log"; RedirectStandardError = Join-Path $Output "$Log.err"
    }
    if ($windows) { $options.WindowStyle = 'Hidden' }
    Start-Process @options
}

$processes = @()
try {
    $server = Start-Federate 'rtinode' @('-i', $url) 'rti'
    $processes += $server
    Start-Sleep -Milliseconds 200
    if ($server.HasExited) { throw 'The RTI server did not start.' }
    $publisher = Start-Federate 'spacefom-publisher' @("`"$Recording`"", "`"$(Join-Path $PSScriptRoot 'fom')`"", $url, $federation) 'publisher'
    $processes += $publisher
    $observer = Start-Federate 'spacefom-observer' @("`"$(Join-Path $Output 'observed.sf')`"", $url, $federation) 'observer'
    $processes += $observer
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while (!$publisher.HasExited -or !$observer.HasExited) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'The exchange did not finish within 120 seconds.' }
        Start-Sleep -Milliseconds 100
    }
    $publisher.WaitForExit(); $observer.WaitForExit()
    if ($publisher.ExitCode -ne 0 -or $observer.ExitCode -ne 0) { throw "Federate failed: publisher $($publisher.ExitCode), observer $($observer.ExitCode). See $Output." }
    $sent = (Get-FileHash $Recording -Algorithm SHA256).Hash.ToLowerInvariant()
    $received = (Get-FileHash (Join-Path $Output 'observed.sf') -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt = [ordered]@{
        transport = 'OpenRTI IEEE 1516-2010 TCP loopback'; platform = [Runtime.InteropServices.RuntimeInformation]::OSDescription
        url = $url; federation = $federation; publisher_exit = $publisher.ExitCode; observer_exit = $observer.ExitCode
        published_sha256 = $sent; observed_sha256 = $received; byte_identity = ($sent -eq $received)
        scope = 'bounded two-federate subset; no full SpaceFOM or RTI compliance claim'
    }
    $receipt | ConvertTo-Json | Set-Content (Join-Path $Output 'receipt.json') -Encoding utf8
    "byte_identity: $($receipt.byte_identity)"
    "sha256: $received"
    "results: $Output"
    if ($sent -ne $received) { exit 1 }
}
finally {
    foreach ($process in $processes) { if (!$process.HasExited) { Stop-Process -Id $process.Id -Force } }
}
