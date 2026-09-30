# Build and run

These instructions assume familiarity with CMake, PowerShell and the .NET SDK. The release packages need none of them.

## Windows

Requirements: Visual Studio 2022 C++ tools (the measured build used toolset 14.44), CMake 3.20 or later, Git and PowerShell.

```powershell
.\tools\build-spacefom-native.ps1
.\run-interop.ps1
.\native\spacefom\test-rejections.ps1 -InputSpool .\data\published-icrf.sf -EvidenceDirectory .\runs\rejections
.\tools\package-transport.ps1 -Output .\out\packages
```

The first command fetches the pinned OpenRTI source and builds it and the adapter under `out/transport`. The second exchanges `data/published-icrf.sf` on loopback with a freeze and resume and prints `byte_identity: true` on success. The third checks that malformed recordings are refused. The fourth assembles `2207-spacefom-exchange-win-x64.zip`. Each run needs a new output directory; existing results are never overwritten.

## Linux

Requirements: GCC, CMake, Ninja, and PowerShell 7 and `patchelf` for packaging. With the pinned OpenRTI source in `<transport>/OpenRTI`:

```bash
cmake -S <transport>/OpenRTI -B <transport>/openrti-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DOPENRTI_ENABLE_RTI13=OFF -DOPENRTI_ENABLE_RTI1516=OFF -DOPENRTI_ENABLE_PYTHON_BINDINGS=OFF \
  -DCMAKE_INSTALL_PREFIX=<transport>/runtime
cmake --build <transport>/openrti-build --target install
ln -s librti1516e.so <transport>/runtime/lib/rti1516e.lib
ln -s libfedtime1516e.so <transport>/runtime/lib/fedtime1516e.lib
cmake -S native/spacefom -B <transport>/adapter-build -G Ninja -DCMAKE_BUILD_TYPE=Release -DOPENRTI_ROOT=<transport>/runtime
cmake --build <transport>/adapter-build
native/spacefom/run-interop.sh data/published-icrf.sf <new-directory> <transport>
pwsh tools/package-transport.ps1 -TransportRoot <transport> -Output <new-directory>
```

The two links let the Windows-oriented `CMakeLists.txt` find the Linux libraries unchanged. The OpenRTI source is also inside every exchange package, under `source/`.

## Verifier packages

Requirements: .NET SDK 10 with runtime 10.0.12, PowerShell 7, and the simulator source at the published revision.

```powershell
pwsh tools/package-verifier.ps1 -SourceRoot <simulator-source> -Output <new-directory>
```

This checks that the source matches the revision in `verify/expected.json`, then publishes a self-contained `2207-verify` for Windows, macOS and Linux on x86-64 and ARM64, with `SHA256SUMS`. Windows and Linux get a single executable; macOS gets a conventional folder. Tar archives are written with explicit Unix permissions, so packages built on Windows keep their executable bits. Each package holds the executable, the expected hashes, the data files the scenarios need, `LICENSE` and `NOTICE`, and the .NET licence and notices.

## Recordings

| File | Axes | Integration | SHA-256 |
|---|---|---|---|
| `data/published-icrf.sf` | ICRF | Eight steps per tick | `bc70068a89751697ecbe75e45ce7bbdd5cadbc5f3b4b74d2859a3a2baf745ade` |
| `data/published.sf` | Ecliptic J2000 | One step per tick | `b83ad5e6eada4626606e1d5358af97e49a25c102a51b5a8364b3b1efdf0efc56` |

`data/published.sf` is the recording used for the earlier Windows evidence and is kept unchanged. The format is described in [native/spacefom/README.md](../native/spacefom/README.md).

## Integrity check

```powershell
python tools/validate-export.py
```

This checks every file against `manifest.json`, confirms the baseline recording is unchanged and confirms that no simulator source directory is present. It checks file integrity only.
