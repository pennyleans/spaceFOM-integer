param(
    [Parameter(Mandatory=$true)][string]$InputSpool,
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [string]$TransportRoot = (Join-Path $PSScriptRoot '../../out/transport'),
    [int]$Port = 31416
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $EvidenceDirectory) { throw 'refusing an existing evidence directory' }
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'invalid port' }
New-Item -ItemType Directory -Path $EvidenceDirectory | Out-Null
$originalPath = $env:PATH
$env:PATH = "$TransportRoot\runtime\bin;$env:PATH"
$url = "rti://127.0.0.1:$Port"
$federation = "orbital_$Port"
$processes = @()
try {
    $server = Start-Process -FilePath "$TransportRoot\runtime\bin\rtinode.exe" -ArgumentList '-i',$url -WindowStyle Hidden -PassThru -RedirectStandardOutput "$EvidenceDirectory\rti.log" -RedirectStandardError "$EvidenceDirectory\rti.err"
    $processes += $server
    Start-Sleep -Milliseconds 150
    if ($server.HasExited) { throw 'RTI server failed to start' }
    $publisher = Start-Process -FilePath "$TransportRoot\adapter-build\Release\spacefom-publisher.exe" -ArgumentList @('"'+$InputSpool+'"','"'+"$TransportRoot\TrickHLA\FOMs\SpaceFOM"+'"',$url,$federation) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$EvidenceDirectory\publisher.log" -RedirectStandardError "$EvidenceDirectory\publisher.err"
    $processes += $publisher
    $observer = Start-Process -FilePath "$TransportRoot\adapter-build\Release\spacefom-observer.exe" -ArgumentList @('"'+"$EvidenceDirectory\observed.sf"+'"',$url,$federation) -WindowStyle Hidden -PassThru -RedirectStandardOutput "$EvidenceDirectory\observer.log" -RedirectStandardError "$EvidenceDirectory\observer.err"
    $processes += $observer
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while (!$publisher.HasExited -or !$observer.HasExited) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'federation exceeded 120 second bound' }
        Start-Sleep -Milliseconds 100
    }
    $publisher.WaitForExit(); $observer.WaitForExit()
    if ($publisher.ExitCode -ne 0 -or $observer.ExitCode -ne 0) { throw "federate failed: publisher=$($publisher.ExitCode), observer=$($observer.ExitCode)" }
    $publishedHash = (Get-FileHash -LiteralPath $InputSpool -Algorithm SHA256).Hash.ToLowerInvariant()
    $observedHash = (Get-FileHash -LiteralPath "$EvidenceDirectory\observed.sf" -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($publishedHash -ne $observedHash) { throw 'received spool bytes differ from published spool' }
    $receipt = [ordered]@{
        transport = 'OpenRTI IEEE1516e TCP loopback'; url = $url; federation = $federation
        server_pid = $server.Id; publisher_pid = $publisher.Id; observer_pid = $observer.Id
        publisher_exit = $publisher.ExitCode; observer_exit = $observer.ExitCode
        published_sha256 = $publishedHash; observed_sha256 = $observedHash; byte_identity = $true
        input_bytes = (Get-Item -LiteralPath $InputSpool).Length
        source_spool = $InputSpool; observed_spool = "$EvidenceDirectory\observed.sf"
        provenance = 'transferred source hash is metadata, not receiver authority or authenticity proof'
        scope = 'bounded two-federate subset; no full SpaceFOM or RTI compliance claim'
    }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath "$EvidenceDirectory\receipt.json" -Encoding utf8
    Get-Content -LiteralPath "$EvidenceDirectory\receipt.json"
}
finally {
    foreach ($process in $processes) { if (!$process.HasExited) { Stop-Process -Id $process.Id -Force } }
    $env:PATH = $originalPath
}
