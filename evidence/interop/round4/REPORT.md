# Round 4 interoperability report: repackaged macOS verifier, TrickHLA early joiner, exchange package

Branch `interop/20260929-4`, started from `review/public-candidate` at `131962d`. The Pitch
pRTI Free 5.5.10 central component ran on the Windows host; our federates and TrickHLA ran in
WSL2 Ubuntu 24.04 and reached it at `{crc-host}`. Host names are written as `{host}` and
paths under the home directories as `{work}`. The Pitch application was restarted before
every federation run, four restarts in all.

## Results

| Run | What ran | Result |
|---|---|---|
| `verifier/packages.txt` | six verifier packages rebuilt and staged | Draft release `verify-9e44426` (id 398836095) holds only the new files and `SHA256SUMS`; still a draft |
| `verifier/windows-win-x64` | new win-x64 package, quick then full | Pass: 12,547 states in 25 s and 1,497,350 states in 156 s |
| `verifier/mac-mini-old-single-file` | round 3 single-file package, quarantine clear only | Fail: `System.AccessViolationException` in .NET 10.0.12 in both runs, exit 134, no receipt |
| `verifier/mac-mini-new-folder` | new osx-arm64 folder package, quarantine clear only | Pass: 12,547 states in 13 s and 1,497,350 states in 69 s |
| `observer` | publisher `--master-modes --required orbital_observer` with TrickHLA as `orbital_observer` | Fail: early joiner, stalls at `root_frame_discovered`; publisher times out |
| `observer-variant` | diagnostic publisher adding the missing second ExCO update | Fail: gets through `root_frame_discovered`, stalls in the multiphase initial data wait |
| `observer-variant2` | diagnostic publisher also repeating the initial data | Pass: full exchange, all states bit-identical, freeze and resume followed |
| `baseline` | publisher `--master-modes` with our own observer | Pass: exits 0, byte-identical |
| `exchange` | Windows exchange package from `131962d` | Pass: `byte_identity: True` |

## Verifier packages

We rebuilt all six packages with `pwsh tools/package-verifier.ps1` from the simulator source at
revision `33aa8e6028b9c22a29145e751cb36748aa29c527`; the stamp check printed
`9e4442614ca9534752166510dcd1ef069fbe66c0c595510ef2423f745dd7be2f`. The machine already had
the official .NET SDK 10.0.401 with runtime 10.0.12 and PowerShell 7.6.6, and the runtime
packs were cached, so no NuGet or SDK configuration was touched. Every asset in draft release
`verify-9e44426` (id 398836095) was deleted and replaced with the new files and `SHA256SUMS`;
the release is still a draft and was not published. New SHA-256 values:

```
61aae72577b8e900515ad39d2f13bcba6b18a1416801aa1409a373f9a026975f  iss-verify-9e44426-linux-arm64.tar.gz
36812e7bcafab016895bad87a7808877ffa39a34a52e1fb700c005d05dd0c189  iss-verify-9e44426-linux-x64.tar.gz
4d1c2e23179a8a32722d0e8472c3ca6f734e4666ed0224cb45a471e82911bc91  iss-verify-9e44426-osx-arm64.tar.gz
dd7a8f0828fe7a75341f52afa10aa7d3c95a772df5594871393a60dd204583ab  iss-verify-9e44426-osx-x64.tar.gz
9f90cfb910f4d4729576d8297d447671626448d4c01178e33e5ab5e99bb94099  iss-verify-9e44426-win-arm64.zip
d01b7f2579f8ac4956686433e60ef76c48e09148174c6459fea0332a7d548433  iss-verify-9e44426-win-x64.zip
```

## Mac mini and Windows verifier runs

The Mac mini is an Apple M4 (Mac16,10) running macOS 26.6.1 (25G76), arm64. For the old
single-file package we extracted fresh, cleared the quarantine on the whole folder with
`xattr -dr com.apple.quarantine .` and did not re-sign. The archive does not carry the
executable bit, so `chmod +x` was needed before the run. Both the quick and the full run
aborted within a second with `System.AccessViolationException` inside the .NET 10.0.12
runtime, exit code 134, no receipt; the quick run crashed in the catalogue load and the full
run in ship inertia parsing. Because this run was not re-signed, re-signing did not cause the
round 3 crash.

The new osx-arm64 package is a conventional self-contained folder and carries the executable
bit in the tar. With only the quarantine cleared, the quick run passed all 12,547 states in
13 s and the full run passed all 1,497,350 states in 69 s, receipt written. On Windows the new
win-x64 package passed 12,547 states in 25 s and all 1,497,350 states in 156 s. Together these
show that the single-file compressed layout was the cause of the macOS crash, and the folder
layout from `131962d` fixes it.

## TrickHLA on Pitch pRTI

We rebuilt the adapter from `131962d` and ran our publisher with
`--master-modes --required orbital_observer`, with TrickHLA v3.2.2 at the pinned revision as
`orbital_observer`. The TrickHLA side used `qualification/trickhla/input-observer.py`, which
is the adjustment of `qualification/trickhla/input-latejoin.py` committed in round 3, and the
simulation carries the compiled per-update logging override.

Stock publisher. TrickHLA classified itself as an early joining federate, which the explicit
initialization set now forces. It achieved and synchronized `objects_discovered`. It received
the ExCO with the epoch, the root frame state, and then blocked in
`ExecutionConfiguration::wait_for_update()` waiting for the ExCO update that a SpaceFOM Master
sends after publishing the root reference frame (SISO-STD-018-2020 section 7.2.1.2, figure
7-6). Our publisher never sends that update, so TrickHLA never achieved
`root_frame_discovered` or `initialization_started`, and the publisher timed out after 30
seconds at `synchronize root_frame_discovered`. TrickHLA then resigned cleanly when the ExCO
was deleted. No freeze was announced and no vessel or body state was received; the only state
was the root frame's initial update. The state comparison therefore reports 0 of 3,841 updates
for `orbital_vessel` and `body_10`. Logs: `observer/`, including the publisher log and the
TrickHLA log around the ExCO and root frame waits.

Diagnostic publishers. To isolate the cause we built two scratch variants of
`native/spacefom/publisher.cpp` outside the repository, kept as one file,
`qualification/trickhla/publisher-multiphase-diag.cpp`:

- Adding only the second ExCO update after the root frame publication let TrickHLA achieve
  and synchronize `root_frame_discovered` and `prototype_metadata`, but it then blocked in
  `Manager::receive_init_data` waiting for the root frame's initial data to change. The
  publisher sends the initial data before that multiphase window and never repeats the root
  frame, so the publisher timed out at `synchronize initialization_started`. Logs:
  `observer-variant/`.
- Adding also a repeat of the initial data (root frame, vessel and bodies) after the
  `prototype_metadata` point let the whole exchange complete: publisher exit 0, TrickHLA exit
  0. TrickHLA achieved and synchronized `objects_discovered`, `root_frame_discovered`,
  `prototype_metadata`, `initialization_started`, `mtr_run` and `mtr_freeze`; it followed the
  freeze at the announced time (scenario freeze 7529673630.00018024, simulation freeze time
  30, Freeze ON at 30.000000, about 240 ms hold, Freeze OFF), synchronized `mtr_run` again for
  the resume, and followed the shutdown through the `mtr_shutdown` announcement and a clean
  resignation. The state comparison is complete: `orbital_vessel` 3,841 of 3,841 updates and
  `body_10` 3,841 of 3,841 updates, all fourteen fields bit for bit with no missing ticks,
  plus the root frame's single update, all fourteen fields exact. Logs and the comparison are
  in `observer-variant2/`.

Control. The publisher with `--master-modes` and our own observer completed the exchange with
both exit codes 0 and `observed.sf` byte-identical to `data/published-icrf.sf`, with the
freeze and resume observed. Receipt in `baseline/`.

## Windows exchange package

We built the transport with `tools/build-spacefom-native.ps1` (Visual Studio 2022 x64, pinned
OpenRTI revision `6e31e0cd`, adapter from `131962d`) and packaged it with
`tools/package-transport.ps1`. The resulting `2207-spacefom-exchange-win-x64.zip` (3,362,780
bytes, sha256 `6330bb49f7eb003e116e5aeb4d02c4ce756654434808093751c5717147e6b55f`) was
extracted and `run-exchange.ps1` was run from it: `byte_identity: True`, with an observed hash
equal to the published recording hash. The archive was uploaded to the same draft release
(asset id 597402096). It is well under the upload limit, so no split was needed.

## Findings

1. The publisher's initialization sequence does not match the SpaceFOM Master sequence that
   TrickHLA implements. Two gaps, in order:
   - After publishing the root reference frame the publisher does not send the ExCO update
     that the standard's Master flow sends before peers achieve `root_frame_discovered`
     (SISO-STD-018-2020 section 7.2.1.2, figure 7-6). A peer blocks in
     `ExecutionConfiguration::wait_for_update()`. With the explicit synchronization set from
     `131962d` the publisher waits at the same point, so both stall until the publisher's 30
     second timeout.
   - In the multiphase initialization window the publisher does not repeat the initial data.
     TrickHLA waits in `Manager::receive_init_data` for each required object's initial data to
     change, and the root frame is otherwise sent only once, before that window opens.
   Both are fixed in the diagnostic publisher `qualification/trickhla/publisher-multiphase-diag.cpp`,
   which completes the full exchange. The adapter build itself is unchanged.
2. With initialization aligned, the master scheduled freeze from `131962d` works with an
   ExCO driven peer: the 64 tick lead is enough for a late catching up federate to schedule
   the freeze at the announced time, and TrickHLA, our observer and the publisher all reach
   the midpoint freeze and the resume.
3. The macOS verifier crash was the single-file compressed layout, not re-signing and not the
   scenarios. The same scenarios pass bit for bit from the folder layout, with the quarantine
   cleared and no re-signing. The new tar writer also restores the executable bit that the
   old archive lost on Windows.
4. TrickHLA decodes every state of the full recording bit for bit once initialization
   completes, which extends the round 3 result (1913 updates before the freeze) to all 3,841
   updates across the freeze and resume.

## What was not done

- The stock publisher never completes with TrickHLA; the full TrickHLA exchange was shown
  only with the diagnostic publisher, which is not part of the adapter and was not committed
  to the build.
- The stock and first diagnostic runs received no vessel or body states, so their state
  comparison is empty; only the variant 2 run produced a full comparison.
- Only the root frame and one body frame are subscribed, because the simulation defines two
  frame packings; the other ten bodies are not subscribed.
- Verifier runs on Linux and on ARM64 Linux or Windows were not possible; only the Windows
  x64 and Mac mini arm64 machines were available.
- The Windows export package has not been run on any machine other than this one.
- Only a redacted excerpt of the macOS crash report was kept.
- The release was left as a draft.
