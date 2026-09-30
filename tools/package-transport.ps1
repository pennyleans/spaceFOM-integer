param(
    [string]$TransportRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) 'out/transport'),
    [Parameter(Mandatory = $true)][string]$Output
)
# Assembles a runnable exchange package from a completed build (tools/build-spacefom-native.ps1 on Windows).
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$windows = $env:OS -eq 'Windows_NT'
$TransportRoot = (Resolve-Path $TransportRoot).Path
if (Test-Path $Output) { throw "Output directory already exists: $Output" }
$platform = if ($windows) { 'win-x64' } else { 'linux-x64' }
$name = "2207-spacefom-exchange-$platform"
New-Item -ItemType Directory -Path $Output | Out-Null
$Output = (Resolve-Path $Output).Path
$target = Join-Path $Output $name
foreach ($folder in 'bin', 'fom', 'recordings', 'licenses', 'source') { New-Item -ItemType Directory -Path (Join-Path $target $folder) | Out-Null }

if ($windows) {
    Copy-Item (Join-Path $TransportRoot 'adapter-build/Release/spacefom-*.exe') (Join-Path $target 'bin')
    Copy-Item (Join-Path $TransportRoot 'runtime/bin/*') (Join-Path $target 'bin')
}
else {
    Copy-Item (Join-Path $TransportRoot 'adapter-build/spacefom-publisher'), (Join-Path $TransportRoot 'adapter-build/spacefom-observer'), (Join-Path $TransportRoot 'runtime/bin/rtinode') (Join-Path $target 'bin')
    foreach ($library in 'libOpenRTI.so.1', 'librti1516e.so.1', 'libfedtime1516e.so.1') {
        Copy-Item (Get-Item (Join-Path $TransportRoot "runtime/lib/$library")).ResolvedTarget (Join-Path $target "bin/$library")
    }
    # Replace build-machine library paths so the package finds its own libraries.
    foreach ($file in Get-ChildItem (Join-Path $target 'bin') -File) {
        & patchelf --set-rpath '$ORIGIN' $file.FullName
        if ($LASTEXITCODE -ne 0) { throw 'patchelf is required on Linux.' }
    }
}
Copy-Item (Join-Path $repo 'fom/*.xml') (Join-Path $target 'fom')
Copy-Item (Join-Path $repo 'data/published-icrf.sf') (Join-Path $target 'recordings')
Copy-Item (Join-Path $repo 'licenses/*') (Join-Path $target 'licenses') -Recurse
Copy-Item (Join-Path $repo 'THIRD-PARTY-NOTICES.md') (Join-Path $target 'licenses')
Copy-Item (Join-Path $repo 'LICENSE'), (Join-Path $repo 'NOTICE') $target
Copy-Item (Join-Path $PSScriptRoot 'run-exchange.ps1') $target
Copy-Item (Join-Path $PSScriptRoot 'transport-README.txt') (Join-Path $target 'README.txt')
& tar -czf (Join-Path $target 'source/OpenRTI-6e31e0cd.tar.gz') --exclude=.git -C $TransportRoot OpenRTI
if ($LASTEXITCODE -ne 0) { throw 'Could not archive the OpenRTI source.' }

if ($windows) { Compress-Archive -Path $target -DestinationPath (Join-Path $Output "$name.zip"); $archive = "$name.zip" }
else { & tar -czf (Join-Path $Output "$name.tar.gz") -C $Output $name; $archive = "$name.tar.gz" }
"$((Get-FileHash (Join-Path $Output $archive) -Algorithm SHA256).Hash.ToLowerInvariant())  $archive"
