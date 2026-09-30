# Follow-up interoperability report: late joiners against the updated publisher

Branch `interop/20260928-2`, started from `review/public-candidate` at
`06b21de` (the publisher that answers attribute update requests). All runs used
the Pitch pRTI Free 5.5.10 central component on the Windows host and our
federates in WSL2 Ubuntu 24.04, reached at `{crc-host}`. Host names are
written as `{host}` and local addresses as `{crc-host}`. Paths under the WSL
home directory are written as `{work}`.

## Results

| Run | Federates | Recording | Result |
|---|---|---|---|
| `pitch/published-icrf` | our publisher and observer | `data/published-icrf.sf` | Pass: exits 0, byte-identical, freeze and resume observed |
| `pitch/published-legacy` | our publisher and observer | `data/published.sf` | Pass: exits 0, byte-identical |
| `pitch/published-icrf-attempt1..4` | our publisher and observer | `data/published-icrf.sf` | Fail: same-tick update arrived after the time advance grant on a long-lived CRC session. All four are kept as evidence |
| `latejoin` | publisher, observer, late-join probe | `data/published-icrf.sf` | Recording byte-identical; the probe was refused the third federate seat |
| `trickhla-attempt1-datacycle` | publisher, observer, TrickHLA | `data/published-icrf.sf` | TrickHLA joined and received the ExCO; it stopped on the 0.25 s data cycle; the observer hit the grant race |
| `trickhla-attempt2-seat` | publisher, observer, TrickHLA | `data/published-icrf.sf` | Recording byte-identical; TrickHLA refused the third seat |
| `trickhla-attempt3-admitted` | publisher, observer, TrickHLA | `data/published-icrf.sf` | TrickHLA joined, received the ExCO, discovered the root frame and `orbital_vessel`, then stopped on our input configuration; the observer hit the grant race |
| `trickhla` and the five attempts in `{work}/thla-attempts2` | publisher, observer, TrickHLA | `data/published-icrf.sf` | Recording byte-identical in all six; TrickHLA refused the third seat in all six |
| `trickhla-control-old-publisher` | publisher and observer from before the update, TrickHLA | `data/published-icrf.sf` | Control: the pre-update publisher shows the same observer grant race when TrickHLA joins |

After a Pitch restart, every run with only two live federates completed
byte-identically. The four failed `published-icrf` attempts were made on a
long-lived CRC session; a control A/B on that session (`pitch/session-control.txt`)
shows the pre-update adapter failing the same way, so the session, not the
adapter change, caused those failures. Restarting the Pitch application before
each critical run removed them.

## Late-join probe

We built the probe from `qualification/latejoin` against Pitch with a new
runner, `qualification/latejoin/run-latejoin-pitch.sh`, which builds the
adapter and the probe against a Pitch shim and starts the probe once `^run `
appears in `publisher.log`:

```
PITCH_SHA256=5d2e7e1d35acb38a054878c704818c2b75675e3d38cb03ccdd353ae2589a1ddf \
./qualification/latejoin/run-latejoin-pitch.sh data/published-icrf.sf \
  evidence/interop/followup/latejoin {work}/pRTI {crc-host} 8989
```

The probe connected and attempted to join, and the Pitch Free edition refused
it: `RTI failure: No available pRTI federate seats`. Our publisher and observer
completed the whole exchange and the recording stayed byte-identical, which is
the expected result for a refused third seat. The probe never
classified itself, and the ExCO and root frame requests were never exercised on
Pitch.

The probe's late-join sequence is exercised on the project's reference RTI: the
runs recorded in `evidence/linux/latejoin/with-update-requests` show the probe
receiving the ExCO (root `SolarSystemBarycentricInertial`, run mode) and the
root frame, with the observer byte-identical. On Pitch the two-seat limit
prevents the same three-federate arrangement, so the two-federate runs and the
seat refusal are what we can record here.

## TrickHLA

Setup. TrickHLA v3.2.2 at `9faa0c5e` was built against the same pRTI install.
The stock `SIM_Entity_Test` was copied to a working tree and rebuilt with
`THLA_DATA_CYCLE_TIME` and `THLA_INTERACTION_CYCLE_TIME` both set to 0.015625 s,
because our least common time step is 15,625 microseconds and TrickHLA requires
`LCTS >= data cycle` and `LCTS % data cycle == 0`. The federate joins as
`orbital_other` with `qualification/trickhla/input-latejoin.py`, which is
`input.py` with lag compensation off and with the subscribed PhysicalEntity
name and parent frame set. It was started after `^run ` appeared in
`publisher.log`.

Seat limit. On fresh CRC sessions the Free edition refused the third seat in
every attempt: six consecutive refusals in the final batch, plus the probe. Our
publisher and observer completed byte-identically each time. On sessions that
had served several earlier runs the third seat was sometimes admitted; those
admitted runs are the ones below.

What TrickHLA did when admitted.

- Receives the ExCO: yes. After joining, it logged `This is a Late Joining
  Federate`, recognized the pending `initialization_completed` point, subscribed
  to the ExCO, requested its values and received them. It decoded the root frame
  `SolarSystemBarycentricInertial`, the scenario epoch 7529673600.00018024, the
  current and next execution mode RUNNING, and the least common time step 15625
  microseconds. This is the new answer path working end to end with TrickHLA on
  Pitch.
- Discovers the root frame and `orbital_vessel`: yes. It discovered the root
  frame, `body_10`, `orbital_vessel` and the other body frames, and registered
  ExCO, the root frame, `body_10` and `orbital_vessel` as its required objects.
- Leaves late-joiner initialization: it left the role determination and the
  ExCO wait. It then stopped on its own initialization in both admitted forms of
  the run. With the stock 0.25 s data cycle it terminated on
  `The Least Common Time Step (LCTS:0.015625 seconds) must be greater or equal
  to the data cycle time for the Trick main thread (thread-id:0,
  data_cycle:0.25 seconds)`. With the 1/64 s cycle it terminated on
  `SpaceFOM::PhysicalEntityBase::initialize(): ERROR: Unexpected empty
  federation instance name`, which is a defect in our
  `qualification/trickhla/input.py` (see the findings).
- Follows the freeze, run and shutdown mode transitions: not observed. In every
  admitted run our observer failed before the freeze with
  `failure: time grant without complete frame`, so the publisher ended with
  `failure: timeout: MTR 3` and the exchange never reached the freeze.

Our observer's recording with TrickHLA present. It stayed byte-identical in
every run where TrickHLA was refused and neither third federate was live. In
every run where TrickHLA joined, the observer failed with
`time grant without complete frame`: a time advance grant for a tick arrived
while one or more state updates with that tick's timestamp were still in
flight. The instrumented runs show the same failure at a single missing
same-tick update (for example `body_8` missing at tick 1), and on one degraded
session no tick 1 updates at all. The pre-update publisher shows the same
failure with TrickHLA present (`trickhla-control-old-publisher`), so the answer
path is not the cause. The `state received before metadata` error seen in the
previous report did not recur in any run; the complete observer logs are
included in each run directory.

## Verifier runs

The verifier runs were not done, because the verifier packages were not yet available:

- The repository has no GitHub releases and no workflow artifacts
  (`gh api .../releases` returns an empty list and
  `gh api .../actions/artifacts` returns `total_count: 0`).
- No `iss-verify-*` file exists under the Windows user profile, `Downloads`,
  `Public` or `temp`.
- The Mac mini is reachable over SSH (macOS 26.6.1, arm64). Searches with
  `mdfind` and `find` found no `iss-verify` package anywhere, including the
  volume that holds the simulator checkout. The simulator checkout is
  at a work revision with local changes, not at the
  content identity pinned by `verify/expected.json`, and the machine has no
  PowerShell 7, which `tools/package-verifier.ps1` needs.

No receipts are included. Running the verifier on the Mac mini would need the
osx-arm64 release package on that machine, or PowerShell 7 plus the simulator
source at the pinned revision.

## Findings

1. In four runs the observer received a time advance grant before every update
   stamped with that tick, and aborted with `time grant without complete frame`.
   This first reading blamed the third federate and the RTI's ordering; the
   analysis at the end of this report supersedes it. IEEE 1516.1-2010 does
   require the complete delivery the observer checks, and the failures followed
   long-lived Free sessions rather than the third federate. The pre-update adapter fails the same
   way, so this is not a regression from the answer path. The check is kept. Evidence:
   `trickhla-attempt3-admitted`, `trickhla-attempt1-datacycle`,
   `trickhla-control-old-publisher`, `trickhla-attempt1-datacycle` again for
   the stock cycle.

2. `qualification/trickhla/input.py` cannot configure a subscribed
   PhysicalEntity. TrickHLA's `SpaceFOMPhysicalEntityObject` clears the packing
   name when `create_entity_object` is false, and the packing initialization
   then requires `pe_packing_data.name` and `parent_frame` to be non-empty, so
   the federate terminates with `Unexpected empty federation instance name`.
   The corrected variant is `qualification/trickhla/input-latejoin.py`, which
   sets both fields and turns lag compensation off. `input.py` should be
   updated the same way. Evidence: `trickhla-attempt3-admitted`.

3. The new publisher answer path works with TrickHLA on Pitch. TrickHLA
   received the ExCO through `provideAttributeValueUpdate` and decoded the
   epoch, the run mode and the least common time step that it needs for its
   late-joiner initialization. This resolves the finding recorded in section 7
   of the main interoperability report on this RTI.

4. Session hygiene for the Pitch Free edition. The Windows central component
   degrades after several federate sessions: first single same-tick updates
   arrive after the observer's grant, then whole ticks can be lost. Restarting
   the Pitch application restores clean runs. We restarted it before each
   critical run and recorded the failed attempts and the A/B control under
   `pitch/`.

## What was not done

- Three-federate byte identity on Pitch. The Free edition admits only two live
  federates on clean sessions, and when it did admit TrickHLA, the observer
  grant race aborted the exchange. A licensed RTI with at least three federates
  is needed to repeat this test.
- The freeze, resume and shutdown sequence with TrickHLA present. TrickHLA
  never reached run mode in an exchange that completed, because it stopped on
  the data cycle or the entity configuration first, and because the observer
  aborted.
- The per-update decoded state logging from `qualification/trickhla/README.md`.
  It needs the compiled packing override that logs the object name, the HLA
  logical time and the fourteen values, and it was not worth adding while
  TrickHLA could not reach run mode. The 1/64 s data cycle and lag
  compensation off are already in place for it.
- The reverse direction, with TrickHLA as Master, Pacing federate and Root
  Reference Frame Publisher, was not attempted.
- Verifier runs, for the reasons in the verifier section.
- OpenRTI was not rerun; its late-join evidence from the previous work is in
  `evidence/linux/latejoin`.
- The Pitch runs used the Windows central component because the Free edition
  refuses headless mode inside WSL; the federates themselves ran in WSL.

## Analysis of the incomplete-frame failures

Every state attribute in the SpaceFOM modules is declared `HLAreliable` with
timestamp order, and our observer is time-constrained and advances with
`timeAdvanceRequest`. IEEE 1516.1-2010 requires the RTI to deliver every
timestamp-ordered message stamped at or before the requested time before it
grants that time. The observer's check that a frame is complete at its grant
tests exactly that guarantee, so we keep it as it is.

The failures do not depend on the third federate. Three of the four failed
`published-icrf` attempts were two-federate runs on a long-lived session and
failed the same way, with either adapter. The Free edition admitted a third
federate only on long-lived sessions; on fresh sessions it refused every third
seat and every two-federate run passed. The evidence therefore points to the
long-lived Pitch Free session, not to the late joiner or to the answer path.

To tell a late message from a lost one, the observer now records which objects
are missing when a grant arrives without a complete frame, waits up to one
second, and logs whether the frame completes late or remains incomplete before
failing as before.

The publisher also gained two options. `--required <federate>` names the
federate it waits for before initialization, and `--master-modes` makes the
Master schedule the freeze, resume and shutdown itself, as a SpaceFOM Master
may, instead of waiting for mode transition requests. Together they allow a
two-federate test in which a TrickHLA federate takes the observer's place, within
the Free edition's two seats, on a freshly started session.

