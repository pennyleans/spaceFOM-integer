# Second RTI and TrickHLA interoperability report

Branch `interop/20260928`, started from `review/public-candidate` at `af543f8`.
All commands ran in WSL2 Ubuntu 24.04 on the machine described in
`environment.json` unless stated otherwise. Paths under the WSL home directory
are written as `{work}`.

## 1. Summary

We built and ran the exchange against Portico 2.2.0 and against Pitch pRTI Free
5.5.10. Portico cannot complete the exchange: its IEEE 1516e interface does not
implement `getFederateHandle`, which our publisher uses to wait for the required
observer, and the C++ wrapper turns the resulting null into a
`NullPointerException`. Pitch passed both recordings byte for byte, including
the freeze and resume. We installed Trick 25.1.1 and TrickHLA v3.2.2, ran the
stock `SIM_Roles_Test` example successfully, and attempted the three-federate
test with a TrickHLA federate configured as the "other" role. The attempt did
not complete. When TrickHLA joined before our observer, the Pitch Free edition
refused the observer a seat. When TrickHLA joined last, it correctly identified
itself as a late joiner from our pending `initialization_completed` point and
then waited for the ExCO values it had requested, which our publisher did not
provide. Section 9 describes the follow-up fix.

| Run | RTI | Recording | Federates | Result |
|---|---|---|---|---|
| `portico/published-icrf` | Portico 2.2.0 | `data/published-icrf.sf` | our publisher and observer | Fail: `getFederateHandle` unimplemented, publisher aborts, no output |
| `portico/published-legacy` | Portico 2.2.0 | `data/published.sf` | our publisher and observer | Fail: same service, no output |
| `pitch/published-icrf` | Pitch pRTI Free 5.5.10 | `data/published-icrf.sf` | our publisher and observer | Pass: exits 0, byte-identical, freeze and resume observed |
| `pitch/published-legacy` | Pitch pRTI Free 5.5.10 | `data/published.sf` | our publisher and observer | Pass: exits 0, byte-identical (transport check) |
| `trickhla/stock` | Pitch pRTI Free 5.5.10 | stock `SIM_Roles_Test` | `RUN_mpr`, `RUN_other` | Pass: installation check |
| `trickhla/three-federate-early-trickhla` | Pitch pRTI Free 5.5.10 | `data/published-icrf.sf` | publisher, TrickHLA, observer | Fail: two-seat limit refused the observer |
| `trickhla/three-federate-late-trickhla` | Pitch pRTI Free 5.5.10 | `data/published-icrf.sf` | publisher, observer, TrickHLA | Fail: late joiner waited for requested ExCO values; observer reported a state before metadata |

## 2. Environment

Host Windows 11 10.0.26200.9168, AMD Ryzen 9 5900X, WSL 2.7.12.0, WSLg
1.0.73.2. Guest Ubuntu 24.04.4 LTS, kernel 6.18.33.2-microsoft-standard-WSL2,
x86-64. GCC 13.3.0, Clang 18.1.3, CMake 3.28.3, GNU Make 4.3, Maven 3.8.7, SWIG
4.2.0, OpenJDK 21.0.12.1. The base image had only the JRE, so the official
Ubuntu `openjdk-21-jdk-headless` package was unpacked into `{work}/jdk21` for
the Portico build.

Repositories and RTIs:

| Component | Version | Commit |
|---|---|---|
| 2207-spacefom-candidate | starting point | `af543f881b80a45f0bc28b64ec6c5c046af95db7` |
| Portico | 2.2.0 | `5345bf2ad90d1b792a0d89039d166e971152e6de` |
| Pitch pRTI Free | 5.5.10 build 9905 | installer sha256 `5d2e7e1d35acb38a054878c704818c2b75675e3d38cb03ccdd353ae2589a1ddf` |
| Trick | 25.1.1 | `c2a3e5480dfdbe975fb94a3d54271116dbc8d89f` |
| TrickHLA | v3.2.2, 2026-04-01 | `9faa0c5e547acb2596047c9bb875cb34ccb0fa2a` |
| OpenRTI (existing pin, not rerun) | | `6e31e0cd50de1852813a98679e8731ad2c97e54b` |

## 3. Portico

Steps. We cloned Portico branch `maintenance-2.2.x` at
`5345bf2ad90d1b792a0d89039d166e971152e6de` and built it with `./ant sandbox`
under a JDK 21 that we unpacked from the official Ubuntu package, because the
image had only a JRE. The first attempt failed on the missing JDK release file;
the build log is `portico/portico-build-attempt1.log`. After the override the
build succeeded (`portico/portico-build-success.log`) and produced
`{work}/portico/codebase/dist/portico-2.2.0`.

We adapted `run-interop.sh` into `native/spacefom/run-interop-portico.sh`. The
runner copies `dist/portico-2.2.0/include/ieee1516e` into a shim, removes only
the non-empty dynamic exception specifications, links
`lib/gcc11/librti1516e64.so` and `lib/gcc11/libfedtime1516e64.so` under the
names the adapter CMake expects, and adds `-Wno-deprecated-declarations`. The
link also needed `-Wl,-rpath-link,<jvm>/lib/server` because Portico's
`librti1516e64.so` needs the JVM's `JNI_CreateJavaVM` at link time; Portico's
own build profile passes the same flag. The adapter sources were not modified.
The RTI runs from an `RTI.rid` that binds JGroups to loopback, with `RTI_HOME`
and `RTI_RID_FILE` set and no `rtinode`.

First attempt. Both recordings failed at the observer's join. The coordinator
(publisher) logged a `NullPointerException` in `Manifest.federateJoined`
(`members.get(uuid)` was null) and the observer received
`RTIinternalError: Federation coordinator never acknowledged that we joined`.
The coordinator records a member's channel handle only while answering a
find-coordinator request (`Federation.receiveFindCoordinator`), and the observer
obtained the manifest from the coordinator's broadcast instead. The full logs
are in `portico/published-icrf-attempt1`.

One targeted setup change. We changed only the runner: the observer now starts
after the publisher logs `SUCCESS Created federation execution`, so the
coordinator answers the observer's find-coordinator request and records its
handle before the join arrives. With that change the observer join succeeded and
the coordinator logged `I am coordinator - received request for me from ...`.
The adapter was not changed.

Remaining failure. The publisher's first `getFederateHandle("orbital_observer")`
call, used to wait for the required observer, aborts the publisher:

```
WARN portico.lrc: The IEEE 1516e interface doesn't yet support getFederateHandle()
RTI failure: java.lang.NullPointerException: Cannot read field "handle" because "handle" is null
  at org.portico.impl.hla1516e.types.HLA1516eHandle.fromHandle(HLA1516eHandle.java:172)
  at org.portico.impl.cpp1516e.ProxyRtiAmbassador.getFederateHandle(ProxyRtiAmbassador.java:1730)
```

In Portico's source, `Rti1516eAmbassador.getFederateHandle` calls
`featureNotSupported("getFederateHandle()")` (`Rti1516eAmbassador.java:4812` and
`:4818`), which logs the warning and returns null when
`portico.unsupportedExceptions` is false. The C++ proxy then dereferences the
null handle. The declared exception for this service in IEEE 1516.1-2010 is
`NameNotFound`, which our adapter catches, so a compliant RTI would let the wait
loop continue. Both recordings behaved identically (`published-icrf`,
`published-legacy`); the observer then timed out waiting for the publisher's
objects, and no output was produced.

Diagnosis: Portico's IEEE 1516e interface omits the mandatory support service
`getFederateHandle(federateName)`, and its C++ wrapper converts the unsupported
result into a `NullPointerException` rather than a standard exception. The
adapter needs no change to satisfy the standard; Portico would have to implement
the service or throw `NameNotFound`/`RTIinternalError` instead of returning
null. The two earlier build failures in `portico/icrf-build-attempt` are the
missing JVM rpath-link, fixed as described above.

## 4. Pitch pRTI

Installation. We obtained the installer from Pitch and installed it
unattended into `{work}/pRTI`; `versioninfo.txt` reports
`Pitch pRTI Free v 5.5.10`. No licence key was needed. The Free edition states a
limit of two federates in its banner and in the CRC window.

Headless restriction. The bundled Linux central component cannot run in this
environment: with `DISPLAY` unset or with `-Djava.awt.headless=true` it prints
`pRTI Free edition does not support running in headless mode` and exits; without
headless it blocks on an interactive End User License Agreement dialog and
never opens port 8989. That attempt is preserved in
`pitch/published-icrf-local-attempt1`. We therefore ran the CRC of the same
release (5.5.10 build 9905, direct mode, `CRC.port` 8989) on the Windows host,
which we launched and whose licence agreement we accepted interactively, and ran our federates in WSL. The
Windows host was reachable from WSL at its local network address; the WSL
gateway address was not reachable on 8989. `native/spacefom/run-interop-pitch.sh`
starts a local CRC when the host is `localhost` and otherwise uses the given
host and port.

Adapter. The Pitch 1516-2010 headers already remove dynamic exception
specifications under C++17 through their `RTI_THROW` macro, so the shim copy is
unmodified. The runner links `lib/gcc73_64/librti1516e64.so` and
`libfedtime1516e64.so` and adds `-Wno-deprecated-declarations`. The adapter
sources were not modified.

Results. Both recordings completed with exit code 0:

- `pitch/published-icrf`: published and observed SHA-256
  `bc70068a89751697ecbe75e45ce7bbdd5cadbc5f3b4b74d2859a3a2baf745ade`,
  byte identity true, freeze and resume observed in the observer log.
- `pitch/published-legacy`: published and observed SHA-256
  `b83ad5e6eada4626606e1d5358af97e49a25c102a51b5a8364b3b1efdf0efc56`,
  byte identity true. The adapter labels the root ICRF in every run, so this is
  the transport check for the ICRF root.

The observer log shows the full exchange: discovery of ExCO, the root and all
bodies, the initialization synchronization points, the freeze at
`hlt_us=30000000`, the verified 100 ms freeze window with no time advance, the
resume, the shutdown request and the committed recording of 3,841 frames. This
is the second RTI implementation, after OpenRTI, on which our exchange
completes.

## 5. TrickHLA

Installation. Trick was built from tag 25.1.1 (`c2a3e54`) with the official
Ubuntu dependency list from the install guide and completed with
`Trick compilation complete`. TrickHLA was cloned and checked out at
`9faa0c5e547acb2596047c9bb875cb34ccb0fa2a` (v3.2.2). The stock
`sims/SpaceFOM/SIM_Roles_Test` was built with `trick-CP` against
`RTI_HOME={work}/pRTI` and `RTI_VENDOR=Pitch_HLA_Evolved` and ran against the
Windows CRC as `RUN_mpr` plus `RUN_other`. Both federates joined, found all
required federates, achieved `objects_discovered`, `root_frame_discovered` and
`initialization_started`, and the combined run exercised `mtr_freeze` without
errors. Logs and the receipt are in `trickhla/stock`. The stock inputs were
copied to a working tree and their `crcHost` was changed to the Windows host;
the TrickHLA clone and our repository were not modified.

Custom federate. `qualification/trickhla/input.py` configures the "other" role:
federation `orbital_8989`, federate `orbital_other`, no Master, Pacing or RRFP
role, required federates `orbital_master` and `orbital_observer`, the same five
SISO SpaceFOM modules, and subscriptions to the root frame
`SolarSystemBarycentricInertial`, one body frame and the `orbital_vessel`
PhysicalEntity. Its known limits are in `qualification/trickhla/README.md`: the
stock sim defines only two frame packings, and logging the fourteen decoded
state values at every received update needs a compiled override of the SpaceFOM
packing `unpack()` methods; trace logging is enabled instead.

Three-federate test. Two attempts were made, both against the Windows CRC with
the federation `orbital_8989`.

- TrickHLA started between our publisher and our observer
  (`three-federate-early-trickhla`). TrickHLA joined and took the second
  federate seat; our observer then failed with
  `RTI failure: No available pRTI federate seats`, and the publisher ended with
  `failure: timeout: required observer join`. No exchange took place.
- TrickHLA started after our publisher and observer
  (`three-federate-late-trickhla`). All three joined. TrickHLA logged
  `This is a Late Joining Federate`, which TrickHLA concludes only after seeing
  the `initialization_completed` announcement, discovered the ExCO object, and
  did not progress further. In the other attempt TrickHLA had joined before
  initialization began and logged `'initialization_completed' sync-point
  announced: No, Still waiting...` while our publisher waited for the observer
  that the seat limit had refused. Our
  observer failed with `failure: state received before metadata` and the
  publisher then ended with `failure: timeout: MTR 3`, because the observer
  never sent its freeze request. No observer output was written and no byte
  comparison was possible.

In detail:

- Joining: TrickHLA joined in both attempts. In the early attempt the third
  seat was refused to our observer; in the late attempt all three joined.
- Discovering the root and the ExCO: the late joiner discovered the ExCO
  (`FedAmb::discoverObjectInstance(): DISCOVERED 'ExCO'`). It did not reach the
  root frame or the entity subscriptions before it stalled.
- Initialization synchronization points: in the early attempt TrickHLA waited
  because our initialization never started. In the late attempt it received the
  pending `initialization_completed` point and classified itself correctly as a
  late joiner.
- Mode transitions: not followed. TrickHLA never left initialization, so the
  freeze, run and shutdown transitions were not exercised with TrickHLA present.
- Byte identity with TrickHLA present: not achieved. Our observer failed before
  the freeze in the late attempt and never started the exchange in the early
  attempt. The two-federate Pitch runs remain the byte-identity evidence.
- State comparison: not performed. A successful run would need both the
  compiled per-update decoder and, for exact comparison, lag compensation set to
  none; the stock sim also compiles a TrickHLA data cycle of 0.250 s while our
  least common time step is 15,625 microseconds, so a full run would want a sim
  built with a matching cycle.

First failure point in SpaceFOM terms. Leaving `initialization_completed`
registered and unachieved is the intended SpaceFOM pattern: TrickHLA's own
Master does the same, and the pending point is announced to any federate that
joins later, which is how a late joiner recognizes itself. The late-joiner
process in `SpaceFOM::ExecutionControl::late_joiner_hla_init_process` then
requests an update of the ExCO and waits for it. Our publisher did not answer
attribute update requests, so TrickHLA waited indefinitely. In the early
ordering the stall came from the Free edition's two-seat limit.

## 6. Verifier runs

The verifier packages were not run on this machine in this round, so no receipts are included.

## 7. Findings that need changes on our side

1. Late-join gap. Our publisher did not answer `provideAttributeValueUpdate`,
   so a SpaceFOM late joiner's request for the ExCO went unanswered. Evidence:
   `trickhla/three-federate-late-trickhla`. Fixed in section 9.

2. Observer error in the late attempt. Our observer reported `state received
   before metadata`. The publisher sends the tagged ExCO update only after the
   `objects_discovered` point, which the observer achieves after subscribing and
   discovering the objects, so the ordering described in the original analysis
   cannot occur in this sequence. The trimmed logs do not show the cause. The
   late-join runs in section 9 did not reproduce it.

3. Required-federate detection limits RTI portability. The publisher waits for
   the observer with `getFederateHandle`, a mandatory 1516e support service that
   Portico does not implement and whose C++ wrapper throws a
   `NullPointerException`. Evidence: `portico/published-icrf`. If other RTIs are
   to be supported, the wait could use a startup synchronization point or a MOM
   query instead.

Recorded without a required change: TrickHLA automatically achieves
synchronization points it does not recognize
(`SyncPointManagerBase.cpp`, `sync_point_announced`), so the prototype
`prototype_metadata` point does not block it.

## 8. What was not done, and why

- The three-federate test did not complete. The Pitch Free edition refused a
  third federate seat in one ordering and the prototype's early-joiner-only
  initialization stalled the late-joining TrickHLA federate in the other, as
  described above. A licensed RTI with at least three federates is needed for a
  meaningful retry.
- The decoded-state comparison between TrickHLA and the recording was not
  performed, because no three-federate run reached the run mode and because the
  per-update decoder needs a compiled packing override.
- The reverse direction, with TrickHLA as Master, Pacing federate and Root
  Reference Frame Publisher, was not attempted.
- Verifier runs were not performed in this round.
- OpenRTI was not rerun; it remains the project's reference RTI.
- The Pitch exchange used the CRC on the Windows host rather than inside WSL,
  because the Free edition refuses headless mode; the federates themselves ran
  in WSL. The federation name kept the project's `orbital_<port>` form as
  `orbital_8989`.

## 9. Follow-up: answering update requests

After this report we changed the publisher to answer attribute update
requests. It queues each `provideAttributeValueUpdate` and, outside the
callback, sends the latest values without a tag: the ExCO's current mode fields,
the root frame, and the static attributes of the vessel and body frames. States
are not resent, because each carries its tick. No other behaviour changed, and
the two-federate exchange remains byte-identical.

A small probe, `qualification/latejoin`, follows the same steps as TrickHLA's
late-joiner process: it joins after initialization, recognizes the pending
`initialization_completed` point, requests the ExCO and the root frame, and
waits for both. On OpenRTI under Linux:

- With the change, the probe classified itself as a late joiner, received the
  ExCO (`SolarSystemBarycentricInertial`, run mode) and the root frame, and
  resigned. Our observer's recording stayed byte-identical with the third
  federate present, through the freeze, resume and shutdown.
- With the previous publisher, the probe received the ExCO only because a mode
  change followed its request, and never received the root frame. A late
  joiner arriving after the last mode change, as TrickHLA did, waits
  indefinitely.

Evidence: `evidence/linux/latejoin/`. TrickHLA has not yet been rerun against
the changed publisher.

