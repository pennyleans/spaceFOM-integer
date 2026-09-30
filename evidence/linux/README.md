# Linux runs

Runs on an Intel Xeon virtual machine under Ubuntu 24.04, x86-64. [`environment.json`](environment.json) records the toolchain, and [`identities.json`](identities.json) records the source and binary hashes.

## Replay

`verify/` holds two full runs of the replay verifier against the published hashes: one framework-dependent on Ubuntu's source build of .NET 10.0.12, one from the self-contained package on Microsoft's .NET 10.0.12 runtime. Both match all 1,497,350 states: five scenarios at eight steps per tick and the 16-second session. The original probe, rebuilt here, also reproduced every published digest-stream, midpoint, endpoint and initial-state file.

## Export

The simulator's SpaceFOM exporter, run here, produced the eight-step ecliptic recording byte-identical to the one exported on Windows (`evidence/precision64/precision8-observed.sf`). [`export-icrf.json`](export-icrf.json) records the ICRF export, `data/published-icrf.sf`. Every one of its 46,092 states equals the corresponding ecliptic state rotated about x by the obliquity.

## Exchange

The adapter was built with GCC 13.3 against the pinned OpenRTI source.

- `exchange-ecliptic/`: the unmodified adapter exchanged `data/published.sf` byte for byte, matching the Windows result.
- `exchange-icrf/`: the adapter with the `SolarSystemBarycentricInertial` root exchanged `data/published-icrf.sf` byte for byte.

Both runs include the coordinated freeze, resume and shutdown. GCC reported two misleading-indentation warnings for one-line statements in `observer.cpp` and no other warnings with `-Wall -Wextra`.

## Late joining

`latejoin/` holds two runs of the exchange with a third federate, `qualification/latejoin`, that joins after initialization and follows the SpaceFOM late-joiner steps: it recognizes the pending `initialization_completed` point, requests the ExCO and the root frame, and waits for both.

- `with-update-requests/`: the current publisher answered both requests. The probe saw the ExCO in run mode with root `SolarSystemBarycentricInertial`, and the observer's recording stayed byte-identical through the freeze, resume and shutdown.
- `control-previous-publisher/`: the publisher before this change. The ExCO arrived only with the next mode change, and the root frame request timed out.

[`latejoin/identities.json`](latejoin/identities.json) records the source hashes.

## Current publisher

`current/` repeats the exchange with the publisher that follows the SpaceFOM Master's initialization sequence: a second ExCO update after the root frame is published, and the initial data sent again after `prototype_metadata`. These are the two steps TrickHLA waited for in the [round 4 report](../interop/round4/REPORT.md). The runs use the federates with HLA save and restore support; without `--save-restore` that support is inactive.

- `default/`: our observer's requests drive the freeze, resume and shutdown. Byte-identical.
- `master-modes/`: the `--master-modes` option. The Master announced the freeze 64 ticks ahead, at 28.98 s for a 30 s target, then scheduled the resume and shutdown itself. Our observer's requests were logged without being awaited. Byte-identical.
- `latejoin/`: the late-join probe received the ExCO in run mode and the root frame. Byte-identical.
- `state-roundtrip/`: the federates' saved-state encodings, checked without an RTI. The observer's state after 1,920 received frames and the publisher's state each re-encode to the same bytes after a restore, frames received after the save are set aside for comparison, and truncated, extended or mismatched states are refused.
- `openrti-save-refused/`: `--save-restore` on OpenRTI, which does not implement HLA save and restore. The publisher stops at the save request with `Save/Restore not implemented!` and no recording is written.

[`current/identities.json`](current/identities.json) records the source and binary hashes.

## Not run

The .NET runtime does not start under QEMU user-mode emulation, so the ARM64 Linux package was built but not run. ARM64 Windows and x86-64 macOS were not available.
