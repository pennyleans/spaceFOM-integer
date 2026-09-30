# Round 5 interoperability report: the committed publisher with TrickHLA, licensed packages

Branch `interop/20260929-5`, started from `review/public-candidate` at `bb84ebf`. The Pitch
pRTI Free 5.5.10 central component ran on the Windows host; our federates and TrickHLA ran in
WSL2 Ubuntu 24.04 and reached it at `{crc-host}`. Host names are written as `{host}` and
paths under the home directories as `{work}`. The Pitch application was restarted before
every federation run, three restarts in all.

## Results

| Run | What ran | Result |
|---|---|---|
| `observer` | committed publisher from `bb84ebf` with `--master-modes --required orbital_observer`, TrickHLA as `orbital_observer` | Pass: publisher and TrickHLA both exit 0, every sync point achieved, freeze, resume and shutdown followed, all 7,682 compared updates bit for bit |
| `baseline-master` | publisher `--master-modes` with our observer | Pass: exits 0, byte-identical |
| `baseline-default` | publisher default options with our observer | Pass: exits 0, byte-identical |
| `verifier/packages.txt` | six verifier packages rebuilt with LICENSE and NOTICE | Draft release `verify-9e44426` (id 398836095) holds only the new files and `SHA256SUMS`; still a draft |
| `verifier/windows-win-x64` | new win-x64 package, quick run | Pass: 12,547 states in 20 s |
| `verifier/mac-mini-quick` | new osx-arm64 package, quick run, quarantine clear only | Pass: 12,547 states in 13 s |
| `exchange` | Windows exchange package from `bb84ebf` | Pass: `byte_identity: True` |
| Release housekeeping | duplicate draft release id 398819190 deleted | `gh release list` shows the one remaining draft, `verify-9e44426` |

## TrickHLA confirmation with the committed publisher

We rebuilt the adapter from `bb84ebf` and ran our publisher with
`--master-modes --required orbital_observer`, with TrickHLA v3.2.2 at the pinned revision as
`orbital_observer`. The TrickHLA side used `qualification/trickhla/input-observer.py`,
unchanged from round 4, and the simulation carries the compiled per-update logging override.
The two additions that round 4 kept in a diagnostic copy are now part of the committed
publisher, so no diagnostic build was used.

TrickHLA classified itself as an early joining federate. Every synchronization point was
announced, achieved and synchronized: `objects_discovered`, `root_frame_discovered`,
`prototype_metadata` (unknown to TrickHLA, which achieves unrecognized points),
`initialization_started`, `mtr_run`, `mtr_freeze` and `mtr_run` again after the resume.
`mtr_shutdown` was announced and, as SpaceFOM specifies, never achieved; TrickHLA detected it
and shut down. Both federates exited 0.

The freeze followed at the announced time: the execution mode moved to freeze at simulation
time 30, the log shows scenario freeze 7529673630.00018024 with simulation freeze time 30,
Freeze ON at 30.000000, a hold of about 242 ms (02:24:25.537732 to 02:24:25.780108), Freeze
OFF, and `mtr_run` synchronized again for the resume. The shutdown came with the `mtr_shutdown`
announcement at 60.0, and the federate resigned cleanly.

`qualification/trickhla/compare-states.py` against `data/published-icrf.sf` reports
`orbital_vessel` 3,841 of 3,841 updates and `body_10` 3,841 of 3,841 updates, all fourteen
fields bit for bit with no missing ticks, plus the root frame's single update, all fourteen
fields exact, with matching times. The log holds 7,685 per-update lines.

Evidence: `observer/trickhla-events.log` (trimmed key lines with source line numbers),
`observer/trickhla-interop.log` (per-update lines), `observer/state-comparison.json`,
`observer/publisher.log`, `observer/receipt.json`.

## Control runs

Both controls used our observer and the committed publisher, each after a fresh CRC restart.
With `--master-modes` the publisher scheduled the freeze 64 ticks ahead; with default options
the observer requested the freeze, resume and shutdown (`sent_mtr` lines in the observer log). Both runs ended with
publisher and observer exit codes 0, and both recordings are byte-identical to
`data/published-icrf.sf` at sha256
`bc70068a89751697ecbe75e45ce7bbdd5cadbc5f3b4b74d2859a3a2baf745ade`, with the freeze at
simulation time 30 and the resume observed. Receipts in `baseline-master/` and
`baseline-default/`.

## Verifier packages

We rebuilt all six packages with `pwsh tools/package-verifier.ps1` from the SpaceFOM
candidate tree at `bb84ebf`, against the ISS source at revision `33aa8e6`; the stamp check
printed `9e4442614ca9534752166510dcd1ef069fbe66c0c595510ef2423f745dd7be2f`. The packaging
scripts now copy `LICENSE` and `NOTICE` into each package, so every archive differs from the
round 4 set and carries new hashes:

```
19092c7696dab02298e8971fea4a99cae234cec47133a58db80877ba8093bab1  iss-verify-9e44426-linux-arm64.tar.gz
b8c59d68edc800299e65da71c7ed400666b3fe0988efb1adb0554866a5a721f1  iss-verify-9e44426-linux-x64.tar.gz
63de839b8af1f72d09b14ac5df9802b136b9dac1da205cd5339ea687d24d8110  iss-verify-9e44426-osx-arm64.tar.gz
0ed70cf253175f4750f39a1005eccfcc5ac402df2ddf2b8914141d9ec00b352d  iss-verify-9e44426-osx-x64.tar.gz
f235f1279bc6714e6338bdc1a0a832821840a2b33b9536a73374a48af585e334  iss-verify-9e44426-win-arm64.zip
5c990bde2d19636487f70c9151adc7ecb3e25f4783a2f0d523188122bf388298  iss-verify-9e44426-win-x64.zip
```

Every previous asset of draft release `verify-9e44426` (id 398836095) was deleted and the six
archives plus the new `SHA256SUMS` were uploaded in their place; the exchange zip was
replaced as described below. The full asset list with ids is in `verifier/packages.txt`. The
release is still a draft and was not published.

Quick runs from the new packages: the win-x64 single executable passed all 12,547 states in
20 s on the Windows host, and the osx-arm64 folder package passed all 12,547 states in 13 s
on the Mac mini with only the quarantine cleared, no re-signing and no chmod.

## Windows exchange package

We rebuilt the transport with `tools/build-spacefom-native.ps1` (Visual Studio 2022 x64,
pinned OpenRTI revision `6e31e0cd`, adapter from `bb84ebf`, which recompiled the changed
publisher) and packaged it with `tools/package-transport.ps1`. The resulting
`2207-spacefom-exchange-win-x64.zip` is 3,367,468 bytes with sha256
`252eaf53e6aa85499e662ddadf3f3a02d28ab4fef1362b314a30b940596ffcac`. Running
`run-exchange.ps1` from the extracted package gave `byte_identity: True` with an observed
hash equal to the published recording hash. The archive was uploaded to the same draft
release (asset id 597470142) in place of the previous one.

Every file in the package's `bin/`:

```
librti1516e.dll        1,033,728
libfedtime1516e.dll       10,240
OpenRTI.dll            1,443,840
rtinode.exe               23,040
spacefom-publisher.exe   144,384
spacefom-observer.exe    147,456
```

The package root also holds `fom/`, `recordings/`, `licenses/`, `source/`, `README.txt`,
`run-exchange.ps1`, `LICENSE` and `NOTICE`.

## Findings

1. The committed publisher at `bb84ebf` completes the full TrickHLA exchange without any
   diagnostic build. The two round 4 additions, the second ExCO update after the root frame
   publication and the repeat of the initial data inside the multiphase initialization
   window, resolved both deadlocks: the peer now reaches `root_frame_discovered` and
   `initialization_started`, and every later sync point follows.
2. With initialization aligned, TrickHLA follows the master-scheduled freeze exactly: it
   switches to freeze at the announced time, holds for about the length of the publisher's
   hold, resumes when `mtr_run` is announced again, and shuts down and resigns cleanly.
3. The request-driven default publisher mode still works with our observer, and both control
   runs are byte-identical to the published recording, so the round 4 finding is confirmed
   from both freeze directions.
4. The package scripts now ship `LICENSE` and `NOTICE` inside the verifier and exchange
   archives, so all hashes changed relative to round 4 even though the payload code is the
   same apart from the publisher.
5. The duplicate draft release with the same tag was removed, so the repository now has a
   single draft for the verifier and exchange assets.

## What was not done

- This is a bounded two-federate subset over Pitch pRTI Free, which admits at most two
  federates; it is not a full SpaceFOM or RTI compliance claim.
- The simulation defines two reference frame packings, so only the root frame and one body
  frame are subscribed; the other ten bodies are not.
- The verifier was run in quick mode only this round, as asked, on Windows x64 and Mac arm64;
  Linux and the other architectures were not exercised.
- The exchange package was run only on this machine.
- The release was left as a draft.
