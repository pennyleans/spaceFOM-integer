param(
    [Parameter(Mandatory = $true)][string]$SourceRoot,
    [Parameter(Mandatory = $true)][string]$Output,
    [string[]]$Runtime = @('win-x64', 'win-arm64', 'osx-arm64', 'osx-x64', 'linux-x64', 'linux-arm64')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$SourceRoot = (Resolve-Path $SourceRoot).Path
if (Test-Path $Output) { throw "Output directory already exists: $Output" }

$expected = Get-Content (Join-Path $repo 'verify/expected.json') -Raw | ConvertFrom-Json
$stamp = Get-Content (Join-Path $SourceRoot 'src/Flight.Data/FlightAuthorityIdentity.cs') -Raw
if ($stamp -notmatch 'Value="([0-9a-f]{64})"') { throw 'Source identity stamp not found.' }
if ($Matches[1] -ne $expected.source_identity) { throw "Source identity $($Matches[1]) does not match the published $($expected.source_identity)." }
$short = $expected.source_identity.Substring(0, 7)

# Writes a gzip tar with explicit Unix modes, so archives made on Windows keep the executable bit.
function New-TarGz([string]$Folder, [string]$Destination) {
    $root = Split-Path -Leaf $Folder
    $file = [IO.File]::Create($Destination)
    $gzip = [IO.Compression.GZipStream]::new($file, [IO.Compression.CompressionLevel]::Optimal)
    $tar = [Formats.Tar.TarWriter]::new($gzip, [Formats.Tar.TarEntryFormat]::Pax, $false)
    try {
        $directory = [Formats.Tar.PaxTarEntry]::new([Formats.Tar.TarEntryType]::Directory, "$root/")
        $directory.Mode = [IO.UnixFileMode]493
        $tar.WriteEntry($directory)
        foreach ($item in Get-ChildItem $Folder -Recurse | Sort-Object FullName) {
            $name = "$root/" + [IO.Path]::GetRelativePath($Folder, $item.FullName).Replace('\', '/')
            if ($item.PSIsContainer) {
                $entry = [Formats.Tar.PaxTarEntry]::new([Formats.Tar.TarEntryType]::Directory, "$name/")
                $entry.Mode = [IO.UnixFileMode]493
                $tar.WriteEntry($entry)
                continue
            }
            $entry = [Formats.Tar.PaxTarEntry]::new([Formats.Tar.TarEntryType]::RegularFile, $name)
            # Files without an extension are the executable and the runtime's helper tools.
            $entry.Mode = if ($item.Extension -eq '') { [IO.UnixFileMode]493 } else { [IO.UnixFileMode]420 }
            $entry.DataStream = [IO.File]::OpenRead($item.FullName)
            try { $tar.WriteEntry($entry) } finally { $entry.DataStream.Dispose() }
        }
    }
    finally { $tar.Dispose(); $gzip.Dispose(); $file.Dispose() }
}

New-Item -ItemType Directory -Path $Output | Out-Null
$Output = (Resolve-Path $Output).Path
$stage = Join-Path $Output 'stage'
$packages = if ($env:NUGET_PACKAGES) { $env:NUGET_PACKAGES } else { Join-Path $HOME '.nuget/packages' }
foreach ($rid in $Runtime) {
    $name = "2207-verify-$short-$rid"
    $target = Join-Path $stage $name
    $arguments = @('publish', (Join-Path $repo 'verify/Verify.csproj'), '-c', 'Release', '-r', $rid, '--self-contained', 'true',
        '-p:DebugType=none', "-p:FlightSourceRoot=$SourceRoot", '-o', $target)
    # macOS gets a conventional self-contained folder; the other platforms get one executable.
    if (-not $rid.StartsWith('osx-')) { $arguments += @('-p:PublishSingleFile=true', '-p:EnableCompressionInSingleFile=true') }
    & dotnet @arguments
    if ($LASTEXITCODE -ne 0) { throw "Publish failed for $rid." }
    Copy-Item (Join-Path $repo 'verify/expected.json') $target
    Copy-Item (Join-Path $repo 'verify/README.txt') $target
    Copy-Item (Join-Path $repo 'LICENSE'), (Join-Path $repo 'NOTICE') $target
    # The self-contained runtime ships with its licence and third-party notices.
    $pack = Join-Path $packages "microsoft.netcore.app.runtime.$rid/10.0.12"
    New-Item -ItemType Directory -Path (Join-Path $target 'licenses/dotnet') | Out-Null
    Copy-Item (Join-Path $pack 'LICENSE.TXT'), (Join-Path $pack 'THIRD-PARTY-NOTICES.TXT') (Join-Path $target 'licenses/dotnet')
    New-Item -ItemType Directory -Path (Join-Path $target 'data/ships') | Out-Null
    Copy-Item (Join-Path $SourceRoot 'data/sol-2207.json') (Join-Path $target 'data')
    Copy-Item (Join-Path $SourceRoot 'data/ships/reference-tug.ship.toml') (Join-Path $target 'data/ships')
    Copy-Item (Join-Path $SourceRoot 'data/ships/reference-tug.flight.json') (Join-Path $target 'data/ships')
    if ($rid.StartsWith('win-')) { Compress-Archive -Path $target -DestinationPath (Join-Path $Output "$name.zip") }
    else { New-TarGz $target (Join-Path $Output "$name.tar.gz") }
}
Remove-Item -Recurse -Force $stage
$sums = Get-ChildItem $Output -File | Sort-Object Name | ForEach-Object {
    "$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($_.Name)"
}
Set-Content -Path (Join-Path $Output 'SHA256SUMS') -Value $sums -Encoding ascii
$sums
