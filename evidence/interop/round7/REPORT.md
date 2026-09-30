# Round 7 interoperability report: save and restore pass on Pitch, TrickHLA save does not complete

Branch `interop/20260929-7`, started from `review/public-candidate` at `ac5854e`. The Pitch
pRTI Free 5.5.10 central component ran on the Windows host; our federates and TrickHLA ran in
WSL2 Ubuntu 24.04 and reached it at `{crc-host}`. Host names are written as `{host}`,
addresses as `{crc-host}`, and every absolute path under a home directory, on either
platform, as `{work}`. The Pitch application was restarted before each federation run, three
restarts in all; the first restart attempt after the previous round did not bind its port and
was redone before any federate ran, so it has no effect on the results. No saved state files
are committed; only the `saved-states.sha256` files the runner writes.

## Results

| Run | What ran | Result |
|---|---|---|
| `msvc/build-ac5854e.log` | `tools/build-spacefom-native.ps1` from `ac5854e`, no extra flags | Pass: both federates compile cleanly under `/W4 /WX`, no compiler diagnostics |
| `msvc/saverestore-build-ac5854e.log` | `qualification/saverestore` with the same CMake project and OpenRTI runtime | Pass: builds with no compiler diagnostics |
| `msvc/state-roundtrip-run.txt` | `spacefom-state-roundtrip` against `data/published-icrf.sf` | Pass: `all checks passed` |
| `save-restore` | `PUBLISHER_OPTIONS="--master-modes --save-restore"`, fresh CRC | Pass: exits 0 and 0, `byte_identity: true`, `rematerialized_frames: 960` |
| `control-master` | `PUBLISHER_OPTIONS="--master-modes"`, fresh CRC | Pass: exits 0 and 0, `byte_identity: true` |
| `trickhla` | publisher with `--master-modes --required orbital_observer --save-restore`, TrickHLA unmodified, fresh CRC | Fail: publisher exit 1, `timeout: federation saved`; TrickHLA never completed the save; exit 0 |

## Windows build

`tools/build-spacefom-native.ps1` from `ac5854e` completes with no extra flags. The adapter
was rebuilt from scratch so both sources recompiled:

```
observer.cpp
publisher.cpp
spacefom-observer.vcxproj -> {work}\agents\2207-spacefom-candidate\out\transport\adapter-build\Release\spacefom-observer.exe
spacefom-publisher.vcxproj -> {work}\agents\2207-spacefom-candidate\out\transport\adapter-build\Release\spacefom-publisher.exe
```

There are no `warning C` or `error C` lines anywhere in `msvc/build-ac5854e.log`; the only
warning text is the long-standing OpenRTI CMakeLists deprecation notice that the build has
always printed. The four `C4458` warnings from round 6 are gone: `ac5854e` renamed the
observer and publisher member to `currentTick` and added `-Wshadow` to the GCC options, so
the shadowing cannot return unnoticed on either toolchain.

The state round trip project builds cleanly against the same OpenRTI runtime and prints:

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

The full output is `msvc/state-roundtrip-run.txt`.

## Save and restore on Pitch pRTI

Command, from the repository tree at `ac5854e`, with the adapter rebuilt inside the runner
against the Pitch pRTI headers and libraries:

```
PUBLISHER_OPTIONS="--master-modes --save-restore" \
  native/spacefom/run-interop-pitch.sh data/published-icrf.sf <new-dir> <pitch-home> {crc-host}
```

This passes end to end. Publisher and observer both exit 0, the recording is byte-identical
to `data/published-icrf.sf` at sha256
`bc70068a89751697ecbe75e45ce7bbdd5cadbc5f3b4b74d2859a3a2baf745ade`, and the receipt records
`rematerialized_frames: 960`.

The publisher log shows the full choreography: `saved label=freeze_1920 bytes=38`,
`federation_saved`, then at the three-quarter freeze `restored label=freeze_1920 bytes=38
reencoded_identical`, `federation_restored`, `rewound tick=1920`, the resumed run, `shutdown
frames=3841` and `destroyed_disconnected`. The observer log shows `saved
label=freeze_1920 bytes=3060732`, `freeze_verified wall_ms=100 no_time_advance`, `restored
label=freeze_1920 bytes=3060732 reencoded_identical`, `rewound tick=1920`, the resumed run,
and finally `rematerialized_identical frames=960 from=1921 to=2880` followed by
`observed_spool_committed frames=3841 tso_updates=46080`. The `restoreStarts` counter from
`ac5854e` is what lets the observer treat the in-flight restore as the reason its logical time
moved during the second freeze, instead of failing the check as it did in round 6.

The saved states re-encode to the same bytes as in round 6:

```
ec6e5394b3a1c5730ac1fb3a1086c4380aa9fdb278a13a32f07246361503a541  publisher-work/freeze_1920.orbital_master.state
28ba9baf29a4a181b56534dd70fe7af50c07ccb44acf764e3ab299f3cccebabe  observer-work/freeze_1920.orbital_observer.state
```

The state files themselves are not committed, only these hashes. The control run, again on a
fresh CRC, is byte-identical with exits 0 and 0 in `control-master/`.

## TrickHLA save and restore

One attempt, on a fresh CRC, with the publisher command from round 5 plus the save option:

```
spacefom-publisher data/published-icrf.sf fom <designator> orbital_8989 \
  --master-modes --required orbital_observer --save-restore
```

TrickHLA joined as an early joining federate with the same unmodified input file and
completed initialization as in round 5, and synchronized `mtr_freeze` at simulation time 30.
The RTI then delivered `initiateFederateSave` at 30.000000 (line 79203 of the log), and
TrickHLA set the save name and its start-to-save flag. The simulation logged `Freeze ON.
Simulation time holding at 30.000000 seconds.` and printed its ExCO dump, and then nothing
further: no `federateSaveBegun`, no checkpoint activity, no `federateSaveComplete`, and no
`federationSaved`. After the publisher's thirty second save wait expired it exited with
`failure: timeout: federation saved` (exit 1) and deleted the ExCO. TrickHLA's shutdown then
raised `SaveInProgress EXCEPTION!` from both `shutdown_time_constrained` and
`shutdown_time_regulating`, resigned, and exited 0. `initiateFederateRestore` was never
delivered because the run stopped in the save phase.

The per-update comparison over the final received states covers everything up to the freeze:
`orbital_vessel` 1920 of 3841 updates and `body_10` 1920 of 3841, all fourteen fields bit for
bit with zero difference, 1921 ticks missing because the run stopped; the root frame's single
update matches all fourteen fields with the right time. The log holds 3,843 per-update lines.
The evidence is in `trickhla/`, including the trimmed event view, the per-update lines and the
comparison JSON.

## Findings

1. The two round 6 blockers are fixed. The MSVC `/W4 /WX` build is clean, the state round trip
   passes on the Windows OpenRTI runtime, and the save and restore exchange on Pitch pRTI
   Free now completes: exits 0 and 0, byte-identical output and 960 frames re-materialized
   and checked after the restore. The saved-state encodings are unchanged, so the fix was
   purely in the restore timing and the shadowed names.
2. TrickHLA receives `initiateFederateSave` but does not complete the save while the
   simulation is held at the freeze. The log shows the save flag set inside the callback and
   then no save progress at all, so the publisher's thirty second save wait expires and the
   exchange ends there. The analysis below finds the cause in TrickHLA's SpaceFOM execution
   control scheme, which does not support save and restore; the timing of the request is not
   the cause.
3. Because the save never completed, the restore half was not exercised with TrickHLA; the
   restore callback was never delivered.
4. The control runs show no regression: the ordinary master-scheduled exchange is still
   byte-identical with our observer.

## What was not done

- TrickHLA was run once.
- The TrickHLA comparison covers ticks 0 to 1919 only; the restore, the re-materialized
  frames and the second half of the recording were never reached with TrickHLA.
- No change was made to TrickHLA or to our federates in response to the failed save; this
  round records the behavior.
- The exchange remains a bounded two-federate subset over Pitch pRTI Free, not a full
  SpaceFOM or RTI compliance claim.

## Analysis of the TrickHLA save

Finding 2 is explained by the TrickHLA source at the pinned revision `9faa0c5e547acb2596047c9bb875cb34ccb0fa2a`, which is also the head of its default branch at the time of this round. `FedAmb::initiateFederateSave` only records the label and sets a flag (`source/TrickHLA/FedAmb.cpp`, line 323). The save itself runs in `ExecutionControlBase::perform_checkpoint`, which returns at once unless the execution control scheme reports `is_save_and_restore_supported()` (`source/TrickHLA/ExecutionControlBase.cpp`, line 1195). The base class returns false (`include/TrickHLA/ExecutionControlBase.hh`, line 712), and only the IMSim scheme overrides it to return true (`include/IMSim/ExecutionControl.hh`, line 300). The SpaceFOM scheme does not, so a SpaceFOM TrickHLA federate never calls `federateSaveBegun` or `federateSaveComplete`, wherever the save is requested. This is a limitation of the SpaceFOM scheme in TrickHLA 3.2.2, not a timing problem, and moving the save request would not change it.

