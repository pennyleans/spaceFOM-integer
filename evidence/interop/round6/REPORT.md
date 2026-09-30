# Round 6 interoperability report: save and restore on Pitch pRTI, and the MSVC /W4 /WX build

Branch `interop/20260929-6`, started from `review/public-candidate` at `899e6ed`. The Pitch
pRTI Free 5.5.10 central component ran on the Windows host; our federates ran in WSL2
Ubuntu 24.04 and reached it at `{crc-host}`. Host names are written as `{host}`, addresses as
`{crc-host}`, and paths under the home directories as `{work}` or `{user}`. The Pitch
application was restarted before each federation run, three restarts in all. No saved state
files are committed; only the `saved-states.sha256` files the runner writes.

## Results

| Run | What ran | Result |
|---|---|---|
| `msvc/build-899e6ed.log` | `tools/build-spacefom-native.ps1` from `899e6ed` | Fail: `error C2220` and four `warning C4458` in `observer.cpp` under `/W4 /WX` |
| `msvc/saverestore-build-899e6ed.log` | `qualification/saverestore` with the same CMake project and OpenRTI runtime | Fail: the same four `C4458`, so no executable was produced |
| `msvc/build-with-wd4458.log` | the same build script with `/wd4458` added through the `CL` environment | Pass: both executables built; the four warnings are the only issues |
| `msvc/state-roundtrip-run.txt` | `spacefom-state-roundtrip` against `data/published-icrf.sf` | Pass: `all checks passed` |
| `save-restore` | `PUBLISHER_OPTIONS="--master-modes --save-restore"`, fresh CRC | Fail: publisher exit 0, observer exit 1, `byte_identity: false`, `rematerialized_frames: 0` |
| `save-restore-retry` | the same run again on a fresh CRC | Fail identically at the same point |
| `control-master` | `PUBLISHER_OPTIONS="--master-modes"`, fresh CRC | Pass: exits 0 and 0, `byte_identity: true` |
| TrickHLA save and restore | not run | Skipped: item 2 did not pass, and this item was conditional on it |

## Windows build

`tools/build-spacefom-native.ps1` from `899e6ed` fails. The OpenRTI side was already up to
date, the publisher compiled, and the observer hit the project's `/W4 /WX` flags. The exact
lines, with the machine paths shortened:

```
native\spacefom\observer.cpp(87,21): error C2220: the following warning is treated as an error [{user}\out\transport\adapter-build\spacefom-observer.vcxproj]
native\spacefom\observer.cpp(87,21): warning C4458: declaration of 'tick' hides class member
native\spacefom\observer.cpp(98,27): warning C4458: declaration of 'tick' hides class member
native\spacefom\observer.cpp(100,33): warning C4458: declaration of 'tick' hides class member
native\spacefom\observer.cpp(136,21): warning C4458: declaration of 'tick' hides class member
```

The whole log is in `msvc/build-899e6ed.log`. It also holds the OpenRTI CMakeLists
deprecation warning that the build has always printed; nothing else is emitted. The cause is
in `899e6ed` itself: the save and restore work adds the member `int32_t tick=0;` to the
observer, and the four pre-existing declarations named `tick` in `reflect`, `complete`,
`failIncomplete` and the output loop now hide it. The same failure comes from the
`qualification/saverestore` project, because it compiles `observer.cpp` with the same `/W4
/WX` options; see `msvc/saverestore-build-899e6ed.log`. This is why the earlier Windows
builds were clean: the observer object was compiled before the member was added and was never
recompiled.

To let the state round trip run against the same Windows OpenRTI runtime anyway, we added
`/wd4458` through the `CL` environment variable. That build completes, both executables are
produced (`msvc/build-with-wd4458.log`), and `spacefom-state-roundtrip data/published-icrf.sf`
prints:

```
pass observer state re-encodes to the saved bytes (3060732 bytes)
pass observer returns to the saved tick
pass frames after the save are kept for comparison
pass truncated observer state refused
pass extended observer state refused
pass observer state for another recording refused
pass publisher state re-encodes to the saved bytes (38 bytes)
pass truncated publisher state refused
all checks passed
```

So the saved-state encodings are correct; the MSVC build failure is separately fixed by
renaming either the member or the four locals. The suppression was used only for this
diagnostic run, and the verbatim failure above is the committed build result.

## Save and restore on Pitch pRTI

Command, from the repository tree at `899e6ed`, with the adapter rebuilt inside the runner
against the Pitch pRTI headers and libraries:

```
PUBLISHER_OPTIONS="--master-modes --save-restore" \
  native/spacefom/run-interop-pitch.sh data/published-icrf.sf <new-dir> <pitch-home> {crc-host}
```

Pitch pRTI Free did not refuse the save or the restore. Both federates saved at the midpoint
freeze under the label `freeze_1920`, both restored it, and both re-encoded the restored
state to the saved bytes. The publisher then continued to the end of the recording and
completed the run: `federation_saved`, `federation_restored`, `rewound tick=1920`, shutdown
at 60.0 and a clean resignation, exit code 0. Its saved state is 38 bytes.

The observer failed at the second freeze, in both the first run and the retry, with

```
failure: logical time or state changed during freeze
```

Its log shows the sequence: `saved label=freeze_1920 bytes=3060732`,
`freeze_verified wall_ms=100 no_time_advance` at the first freeze, and then at the second
freeze, which is the three-quarter mark where the Master requests the restore,
`restored label=freeze_1920 bytes=3060732 reencoded_identical` with the logical time back at
30 seconds. The restore begins inside the observer's hundred-millisecond no-time-advance
window. The transport restores the observer's own state and completes the federate restore,
but the RTI's federation-restored callback that increments the observer's restore counter
has not arrived yet, so the observer's check `logical time or state changed during freeze`
fires on the legitimate rewind. The same failure happened on the second fresh run, at the
same log line, so it is deterministic, not a timing fluke. Both full logs and receipts are in
`save-restore/` and `save-restore-retry/`; the observer log is 47 lines, so the whole run is
there.

The two runs saved identical state bytes:

```
ec6e5394b3a1c5730ac1fb3a1086c4380aa9fdb278a13a32f07246361503a541  publisher-work/freeze_1920.orbital_master.state
28ba9baf29a4a181b56534dd70fe7af50c07ccb44acf764e3ab299f3cccebabe  observer-work/freeze_1920.orbital_observer.state
```

The state files themselves are not committed, only these hashes.

The control run, again on a fresh CRC, completed both ways: publisher and observer exit 0,
`byte_identity: true`, freeze and resume seen, in `control-master/`.

## TrickHLA save and restore

Not run. The instructions make this item conditional on item 2 passing, and item 2 did not
meet its pass criteria: the observer exits 1, the recording is not byte-identical, and
`rematerialized_frames` is 0. The publisher side proved that Pitch performs the save and the
restore; the blocker is the observer's freeze check described above.

## Findings

1. The MSVC `/W4 /WX` build is broken at `899e6ed` by the four `C4458` warnings, all caused
   by the new observer member `tick` shadowed by existing locals and parameters. This is a
   compile-time blocker on Windows and in the `qualification/saverestore` project; renaming
   either side clears it. The state round trip itself passes on the same OpenRTI runtime once
   the warning is suppressed, so no other Windows problem is hidden behind it.
2. Pitch pRTI Free 5.5.10 supports federation save and restore: both federates saved at the
   midpoint freeze, restored the save, re-encoded identical state bytes, and the publisher
   rewound and ran to completion. The two independent runs produced identical saved-state
   hashes.
3. The observer's second-freeze verification races the restore. Because the Master requests
   the restore at the start of the three-quarter freeze, the rewind arrives inside the
   observer's hundred-millisecond no-time-advance check, before the RTI's
   federation-restored callback has advanced the restore counter. The check then treats the
   correct rewind as a freeze violation. Treating an in-flight restore like a completed one,
   or delaying the restore until both federates finish the freeze check, would fix it. This
   is deterministic in both attempts.
4. The control run confirms the change did not disturb the ordinary exchange: the
   master-scheduled run is still byte-identical.

## What was not done

- TrickHLA save and restore, skipped because item 2 did not pass.
- The rematerialized comparison, because the observer stopped before it. The publisher
  rewound and re-sent from tick 1921, but no `rematerialized_identical` line was produced.
- The Windows executables were built with `/wd4458` added; the requested clean `/W4 /WX`
  build does not produce them at `899e6ed`.
- This remains a bounded two-federate subset over Pitch pRTI Free, not a full SpaceFOM or RTI
  compliance claim.
