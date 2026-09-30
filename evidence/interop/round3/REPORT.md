# Round 3 interoperability report: TrickHLA as the observer, and verifier runs

Branch `interop/20260929-3`, started from `review/public-candidate` at `2eb0d3d`. All
federation runs used the Pitch pRTI Free 5.5.10 central component on the Windows host and our
federates in WSL2 Ubuntu 24.04, reached at `{crc-host}`. Host names are written as `{host}`,
user names as `{user}` and paths under the home directories as `{work}`.

## Results

| Run | Federates | Recording | Result |
|---|---|---|---|
| `observer`, TrickHLA as `orbital_observer` | publisher with `--master-modes --required orbital_observer`, TrickHLA | `data/published-icrf.sf` | Partial: all received states matched bit for bit, run mode followed, freeze refused, clean resignation, publisher timed out |
| `baseline`, our observer | publisher (default options), our observer | `data/published-icrf.sf` | Pass: exits 0, byte-identical, freeze and resume observed |
| `verifier/windows-win-x64` | none | frozen data set | Pass: all 1,497,350 states match the published hashes |
| `verifier/mac-mini-osx-arm64` | none | frozen data set | Fail: the verifier aborts in the .NET 10.0.12 runtime, no receipt |

The Pitch central component was restarted before every run, eight restarts in all. A
long-lived session degrades as reported in round 2, so each of these runs began on a fresh
session. The connectivity check also refused the first join after the restart because the
federate advertised loopback and tailnet addresses the CRC could not verify; we set
`CRC.skipConnectivityCheck=true` in the CRC settings for these local runs.

## TrickHLA as the observer

Setup. Our publisher ran as Master, Pacing federate and Root Reference Frame Publisher with
`--master-modes --required orbital_observer`, so it freezes at the midpoint (30 s scenario
time), holds 250 ms, resumes and shuts down by itself. TrickHLA v3.2.2 at
`9faa0c5e` took the observer's place as `orbital_observer` using
`qualification/trickhla/input-observer.py` and a rebuilt `SIM_Entity_Test` with a 1/64 s
TrickHLA data cycle and lag compensation off. The per-update state logging is the compiled
override described in `qualification/trickhla/README.md`; the new
`qualification/trickhla/apply-logging-override.sh` copies
`qualification/trickhla/LoggingSpaceFOM.hh` into the TrickHLA include tree and switches the
ReferenceFrame and PhysicalEntity packings in `S_modules/SpaceFOM/RefFrame.sm` and
`PhysicalEntity.sm` to logging subclasses. It also patches
`TrickHLA_data/SpaceFOM/SpaceFOMPhysicalEntityObject.py` to set the subscribed entity's
instance name, mirroring what the reference frame class already does; the input also sets the
working data name and parent frame because the packing initialization copies the working data
into the packing.

Joining and initialization. TrickHLA joined and classified itself as a late joining federate.
The publisher registers its initialization synchronization points as soon as the required
observer's join is visible, and they are announced and completed before TrickHLA's role
determination finishes, so TrickHLA saw `objects_discovered`, `root_frame_discovered`,
`prototype_metadata`, `initialization_started` and `initialization_completed` as already
announced or known points and did not achieve them. It then used the publisher's attribute
update answer path to obtain the ExCO, decoded the epoch, the run mode and the least common
time step of 15,625 microseconds, and subscribed to the root frame, `body_10` and
`orbital_vessel`. It achieved and synchronized `mtr_run` and entered run mode.

State reception and comparison. The publisher sent frames 1 to 1,920 before it stopped at the
freeze. TrickHLA received the updates from tick 7 or 8 onwards and logged every
one with the object name, the HLA logical time derived from the state time tag, and the
fourteen decoded state values. `qualification/trickhla/compare-states.py` matched those lines
against the recording decoded with `qualification/wire/oracle.py` and compared them tick by
tick:

- `orbital_vessel`: 1913 updates (ticks 8 to 1920), all fourteen fields matched bit for bit,
  no field differed.
- `body_10`: 1914 updates (ticks 7 to 1920), all fourteen fields matched bit for bit.
- The root frame state was not received as an update, so no root frame comparison is
  possible; the object itself was discovered and subscribed.

The full comparison is in `observer/state-comparison.json`, and all per-update lines are in
`observer/trickhla-interop.log`.

Freeze, resume and shutdown. The freeze ExCO update arrived too late for TrickHLA to schedule
its freeze. Its late-join offset was 0.53125 s, so the master's freeze target of scenario time
epoch + 30 mapped to simulation time 29.46875, exactly TrickHLA's current simulation time at
the moment it processed the update. It logged `Freeze time specified in the past. specified
29.468750, current_time 29.468750`, did not schedule the freeze, and announced but never
achieved the `mtr_freeze` point. Our publisher's barrier timed out after 30 seconds
(`failure: timeout: synchronize mtr_freeze`), resigned and destroyed the federation.
TrickHLA then detected the ExCO deletion, disabled time constrained and regulating modes,
resigned cleanly and terminated with exit code 0. The resume was never reached. The trimmed
event log is in `observer/trickhla-events.log`; the publisher's log and error are next to it.

Diagnostics. None of these runs produced `time grant without complete frame`; the
observer diagnostics added in `2eb0d3d` were not triggered, and the session age was one run
since the restart.

## Our observer baseline

On a fresh session (restart 8) the publisher with default options and our own observer
completed the full exchange: both exit codes 0, `observed.sf` byte-identical to
`data/published-icrf.sf`, freeze and resume observed, shutdown as before. The receipt is in
`baseline/receipt.json`.

## Verifier receipts

C0 build and staging. We checked out the simulator source at
`33aa8e6028b9c22a29145e751cb36748aa29c527`; `python3 tools/stamp-authority.py --check`
printed the required identity `9e4442614ca9534752166510dcd1ef069fbe66c0c595510ef2423f745dd7be2f`.
We installed PowerShell 7.6.6 with winget; the machine already had the official .NET SDK
10.0.401 with runtime 10.0.12. The NuGet configuration deliberately has no package
sources, so we added nuget.org temporarily for the restore and restored the original
configuration afterwards. `tools/package-verifier.ps1` published all six packages; their
hashes are in `verifier/packages.txt`. They were uploaded to the draft release
`verify-9e44426` (release id 398836095, target `review/public-candidate`, never published).
A second, older draft with the same tag already existed with an exchange-package asset; the
six archives and `SHA256SUMS` are in release id 398836095.

Windows x64. `iss-verify-9e44426-win-x64.zip` ran the full verification with a receipt:
platform Microsoft Windows 10.0.26200 (X64), runtime .NET 10.0.12, source identity matches,
all six scenarios match, and `PASS: all 1,497,350 states match the published hashes (164 s)`.
The receipt and console output are in `verifier/windows-win-x64/`.

Mac mini. The Mac could not reach the unpublished release, so we downloaded the osx-arm64
archive on the Windows PC by asset id and copied it over ssh; its SHA-256 was verified on both
machines. The package is signed with an ad-hoc signature (`codesign --force --sign -`) and the
quarantine attribute was cleared, but the verifier aborts with
`System.AccessViolationException` inside the .NET 10.0.12 runtime. We tried a full run, a quick
run, a quick run with `DOTNET_EnableWriteXorExecute=0`, and a quick run with tiered compilation
disabled; all four crashed in different core routines (SHA-256 digest creation, `BigInteger`
addition, a collection builder, integer parsing), so no receipt was produced. The machine is
an Apple M4 (Mac16,10) running macOS 26.6.1 (25G76). The four console outputs are in
`verifier/mac-mini-osx-arm64/stdout.txt` and an excerpt of the macOS crash report is in
`verifier/mac-mini-osx-arm64/crash-report.txt`. The fallback `dotnet run` path was not
available either: the machine has no `dotnet` command and no clone of the simulator source or
the candidate repository.

## Findings

1. The publisher's initialization synchronization points are announced and completed within
   milliseconds of the required observer's join, so a peer that joins at that moment cannot
   participate as an early joiner. TrickHLA classified itself as a late joiner on every
   attempt. With the two-seat limit there is no way to start TrickHLA early enough alongside
   our publisher. If early-joiner participation matters, the publisher needs a readiness
   handshake before it registers the initialization points, or the peer must be able to
   participate from the first announcement.
2. The master-scheduled freeze gives less than one tick of lead. The freeze target is the tick
   in progress when the ExCO update is sent, so a peer that is catching up after a late join
   has already been granted the target when it processes the update. TrickHLA refuses to
   freeze in the past and the publisher times out at `mtr_freeze`. Scheduling the freeze a
   data cycle or more ahead, or using the request driven path, would let an ExCO driven peer
   freeze at the target.
3. The subscribed PhysicalEntity needs its name and parent frame before packing
   initialization. TrickHLA's `SpaceFOMPhysicalEntityObject` clears the packing name for
   subscribers and, unlike `SpaceFOMRefFrameObject`, never restores it, and the packing
   initialization copies the working data into the packing. The stock `SIM_Entity_Test`
   definition also instantiates a dynamical entity and a physical interface that our input
   does not configure; their initialization aborts on the same check. Both fixes are recorded
   in `apply-logging-override.sh` and `input-observer.py`, and this is the first run in which
   a subscribed PhysicalEntity works end to end.
4. The verifier crashes on macOS 26.6.1 with Apple silicon under .NET 10.0.12. The same
   package passes on Windows x64, which points at the runtime or platform rather than the
   data. No receipt could be produced on the Mac mini. A smaller packaging point: the
   osx and linux tar archives are created by Windows `tar` and lose the executable bit, so the
   extracted verifier needs `chmod +x`.

## What was not done

- The three-federate and freeze/resume tests did not complete with TrickHLA: it never reached
  the freeze because the master's freeze announcement had less than one tick of lead, and the
  publisher timed out at `mtr_freeze`.
- No byte identity was measured with TrickHLA in place of the observer, because it replaced
  the observer; only the decoded state comparison is available, and it covers the updates
  TrickHLA received before the freeze.
- Only the root frame and one body frame are configured, because the stock simulation
  defines two frame packings; the remaining ten body frames are not subscribed.
- The reverse direction, with TrickHLA as Master, Pacing federate and Root Reference Frame
  Publisher, was not attempted.
- Verifier runs on Linux and on ARM64 Linux or Windows were not done; only the Windows x64
  and Mac mini arm64 machines were available.
- The full macOS crash report was not committed, only an excerpt.
- The temporary NuGet source was removed and the configuration restored; the CRC
  settings keep `CRC.skipConnectivityCheck=true` for local runs.

## Follow-up changes

After this round we made three changes and verified them on OpenRTI under Linux. TrickHLA and
the Mac mini have not been rerun.

- Freeze lead. With `--master-modes` the publisher now announces the freeze one second (64
  ticks) before the target. Our observer's exchange stays byte-identical, and the ExCO
  announcing the freeze now arrives at scenario time 28.98 s for a 30 s target.
- Early-joiner points. The publisher registers `objects_discovered`, `root_frame_discovered`,
  `prototype_metadata` and `initialization_started` for an explicit set containing itself and
  the required federate, using the handle from `getFederateHandle`. A required federate is
  then always in the synchronization set, even when its join is still settling at the moment
  of registration. `initialization_completed` and the mode transition points still apply to
  the whole federation, so late joiners are unaffected; the late-join probe still passes.
- macOS packaging. The macOS verifier is now a conventional self-contained folder rather than
  a compressed single file, and its README asks only for the quarantine attribute to be
  cleared. The SDK already signs the executable when it publishes, so re-signing is
  unnecessary. The crashes began within seconds, on several threads, in unrelated core
  library routines, which suggests damaged code pages rather than a fault in the program; the
  manual re-signing of the compressed bundle is one candidate cause. Tar archives are now
  written with explicit Unix permissions, so archives built on Windows keep their executable
  bits.

We also removed device identifiers (crash reporter key, incident and boot session
identifiers) from the crash report excerpt.

