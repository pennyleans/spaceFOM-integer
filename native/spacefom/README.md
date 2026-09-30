# Native SpaceFOM adapter

A C++ publisher and observer using the IEEE 1516-2010 API and the SISO-STD-018-2020 FOM modules. The publisher sends a recording produced by the simulator; the observer reconstructs it and never acts as a simulator. This is a prototype and makes no claim of full SpaceFOM or RTI compliance.

## Build and run

```powershell
.\tools\build-spacefom-native.ps1
.\native\spacefom\run-interop.ps1 -InputSpool .\data\published-icrf.sf -EvidenceDirectory .\runs\new-run
.\native\spacefom\test-rejections.ps1 -InputSpool .\data\published-icrf.sf -EvidenceDirectory .\runs\new-rejections
```

On Linux, build the pinned OpenRTI source with CMake and GCC, then configure this directory with `OPENRTI_ROOT` pointing at the installation; `run-interop.sh <recording> <new-directory> <transport-root>` replaces the PowerShell runner. The steps are in [docs/build.md](../../docs/build.md#linux).

Publisher options, after the four positional arguments:

- `--required <federate>`: the federate to wait for before initialization; the default is `orbital_observer`.
- `--master-modes`: the Master schedules the freeze at the midpoint, announced one second (64 ticks) ahead, a 250 ms hold, the resume and the shutdown itself, instead of waiting for mode transition requests. Requests that arrive are logged and not required.
- `--save-restore`, with `--master-modes`: HLA save at the midpoint freeze, a second freeze at three quarters, and a restore of the midpoint save; the run then continues from the midpoint to the end. Needs an RTI that implements save and restore; OpenRTI does not.
- `--state-dir <directory>`: where saved states are written; the default is the working directory. The observer accepts the same option after its three arguments.

The runners pass the contents of the `PUBLISHER_OPTIONS` environment variable to the publisher.

If a time advance grant arrives without every state of that tick, the observer logs the missing objects, waits up to one second to show whether they arrive late, and then fails.

On Windows this needs the Visual Studio 2022 x64 tools and CMake. The build script builds OpenRTI separately and links both executables to it dynamically, keeping all dependency sources and binaries under the transport directory. The runner binds the RTI to loopback, starts the publisher and observer as separate processes, limits the run to 120 seconds, compares SHA-256 hashes and stops only the processes it started. No window opens.

## Recording format

A recording begins with the eight ASCII bytes `2207SF01`, a little-endian int32 frame count and a little-endian int32 body count. Each body then has a little-endian uint32 ID length and the ID bytes, a uint32 name length and the name bytes, the radius in metres as a little-endian float64, and the gravitational parameter in m³/s² as a little-endian float64. This prototype restricts metadata to printable ASCII.

Each frame holds a little-endian int64 tick, a 32-byte hash of the source state, the vessel state, and one state per body in header order. Each state is 112 bytes: fourteen little-endian float64 values for position xyz, velocity xyz, quaternion wxyz, angular velocity xyz and time. Ticks run contiguously from zero. Position and velocity are barycentric with ICRF axes; recordings made before the move to ICRF use Horizons ecliptic J2000 axes. The quaternion is the passive parent-to-body rotation, and angular velocity is in body axes. States are encoded by the simulator's exporter and published unchanged.

## HLA mapping

The root reference frame is `SolarSystemBarycentricInertial`, with an empty parent name. The vessel is the `PhysicalEntity` instance `orbital_vessel`; each body is a `ReferenceFrame` instance `body_<id>` parented to the root. The vessel's name, type, status, parent, zero centre of mass, identity body-to-structural quaternion and state are sent together. Names are `HLAunicodeString`, and state follows the standard `SpaceTimeCoordinateState` layout. The two-byte execution mode enumerations are little-endian, and `least_common_time_step` uses the standard big-endian `HLAinteger64Time` encoding.

Logical time is the tick multiplied by 15,625 µs, with a 15,625 µs lookahead, and both federates advance with time advance requests and grants. State time is TT seconds from the Truncated Julian Date origin, `7529673600.00018 + tick/64` for this recording. The constant TDB-to-TT offset is an approximation, described in the [federation profile](../../docs/federation-profile.md#time).

The recording header travels once, as the user-supplied tag on the first ExCO update. The tick and source hash travel as user-supplied tags on each state update. These are prototype conventions, not SpaceFOM attributes, and the hash is not a signature. Radius and gravitational parameter are carried in the header tag, not as `ReferenceFrame` attributes.

The observer is not given the input file. It builds its output entirely from RTI callbacks, and it rejects unexpected field widths, non-finite values, invalid quaternion norms, time mismatches, duplicate updates and incomplete frames. Output is written only after a complete run, and an existing output file is refused.

## Execution

The publisher is Master, Pacing federate and Root Reference Frame Publisher; `orbital_observer` is the required early joiner. The required instances are `ExCO`, the root frame, `orbital_vessel` and every declared `body_<id>`. The federates reserve names, discover instances, synchronize on `objects_discovered` and `root_frame_discovered`, exchange static data and frame zero under `prototype_metadata`, and complete `initialization_started`. As a SpaceFOM Master does, the publisher updates the ExCO again once the root frame is published and sends the initial data again after `prototype_metadata`; `initialization_completed` is registered but not achieved. Delivery is asynchronous, with time-constrained and time-regulating modes enabled. Initialization data and ExCO use receive order; state updates use timestamp order.

One tick before the midpoint, the observer requests a freeze with the standard `ModeTransitionRequest` interaction. The master announces the freeze time through ExCO, and both federates synchronize on `mtr_freeze` at that boundary. The observer processes callbacks for at least 100 ms and checks that neither logical time nor the received state count advances. It then requests run, and both synchronize on `mtr_run`. Shutdown uses an ExCO mode update and an unachieved `mtr_shutdown` point, followed by immediate resignation. The publisher then destroys the empty federation.

## Save and restore

Each federate writes its own state under the save label as canonical little-endian bytes, never a memory image: the publisher its tick, logical time, last ExCO modes and unconsumed requests; the observer its tick, logical time, ExCO view, counters and every frame received so far. On restore a federate loads the state, requires it to re-encode to the saved bytes, and after the federation is restored requires the RTI's logical time to match. The observer keeps the frames it received after the save and, before writing its recording, requires every one of them to equal the same frame received again after the restore. [`qualification/saverestore`](../../qualification/saverestore/README.md) checks the encodings without an RTI.

On Pitch pRTI the full sequence passes: both federates save at the midpoint, restore at three quarters with identically re-encoded state and the saved logical time, and the 960 frames received again after the restore equal the first pass bit for bit; the recording is byte-identical. [Round 7 report](../../evidence/interop/round7/REPORT.md). TrickHLA 3.2.2 does not take part: its SpaceFOM execution control scheme does not support HLA save and restore, so it never completes the save.

## Not yet addressed

- Certification and a complete FESFA or FCD declaration.
- Automatic role determination, more than one observer, rejoining and recovery. HLA save and restore are tested only for the scripted midpoint case, between our own federates. The publisher answers attribute update requests, which a SpaceFOM late joiner uses to obtain the ExCO; late joining has been tested with a probe on OpenRTI only; the Pitch pRTI Free edition refuses a third federate.
- Central timing equipment, wall-clock pacing and real-time guarantees. The 60-second scenario runs as fast as logical time coordination allows.
- Arbitrary mode-request precedence, shutdown during every wait, duplicate mode handling, unknown synchronization points and fault-tolerant cleanup.
- OpenRTI lacks working MOM services, ownership management, DDM, HLA save/restore and some other services, so it cannot establish full RTI compliance. Auto-Provide is handled with the standard switches module and explicit initial updates rather than through MOM.
- Start-up discovery waits for the root frame, ExCO and the vessel before the header lists the bodies. Every declared body's static attributes and initial state are required before the metadata synchronization point, but generic discovery from a published FESFA object list is not implemented.
- Network security and authentication of the carried hash.
- The encoding helpers assume a little-endian platform; the adapter has been built and run on Windows x64 and Linux x86-64. Metadata and malformed-input limits are deliberately narrower than the standard.

References: [SISO-STD-018-2020](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-018-2020_srfom.pdf), sections 4.5 and 5 to 8; [OpenRTI source](https://sourceforge.net/p/openrti/OpenRTI/ci/6e31e0cd50de1852813a98679e8731ad2c97e54b/tree/); [SpaceFOM modules](https://github.com/nasa/TrickHLA/tree/9faa0c5e547acb2596047c9bb875cb34ccb0fa2a/FOMs/SpaceFOM).
