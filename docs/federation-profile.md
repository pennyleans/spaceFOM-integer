# Federation profile

Prototype agreement, version 1.1, 2026-09-29. Target: SISO-STD-018-2020 with the IEEE 1516-2010 API. This profile describes what the prototype implements. It is not a federate compliance declaration.

## Participants and execution

| Item | Declared profile |
|---|---|
| Federates | `orbital_master` and `orbital_observer`, both required early joiners |
| Master, Pacing and Root Reference Frame Publisher | `orbital_master` |
| Pacing | Coordinated as-fast-as-possible logical execution; no wall-clock pacing and no central timing equipment (CTE) |
| Root reference frame | `SolarSystemBarycentricInertial`, ICRF axes, no parent |
| Vessel | `orbital_vessel`, a `PhysicalEntity` with its centre of mass at the structural origin |
| Bodies | `body_10`, `body_199`, `body_299`, `body_301`, `body_399`, `body_499`, `body_5`, `body_606`, `body_699`, `body_799`, `body_8`, each a `ReferenceFrame` parented to the root |
| Logical time | `HLAinteger64Time` in microseconds; 15,625 µs per tick and lookahead |
| State | Position, velocity, attitude quaternion (scalar first) and body angular velocity, with a time tag |
| Static vessel attributes | Name, type, parent reference frame and centre of mass |
| Transport | Reliable TCP; loopback with OpenRTI, a local network link to the Pitch pRTI central component |
| Content | A bounded 60-second coast; no remote commands; HLA save and restore for one scripted case |

Body identifiers are the numeric IDs in [`data/catalogue.json`](../data/catalogue.json) and in the recording header; the instance name is `body_` followed by the ID.

The master and the observer join as required early joiners. Both reserve and discover the required instance names, exchange static data and the first frame under a `prototype_metadata` synchronization point, and complete `initialization_started`. The early-joiner points `objects_discovered`, `root_frame_discovered`, `prototype_metadata` and `initialization_started` are registered for an explicit set, the Master and the required federate, so the required federate is always a member. `initialization_completed` and the mode transition points apply to the whole federation. The observer then requests a freeze through the standard `ModeTransitionRequest` interaction. The master announces the freeze time through the execution configuration object (ExCO), and both synchronize on `mtr_freeze` and later on `mtr_run`. Shutdown uses an ExCO mode update, then resignation. With the publisher's `--master-modes` option the Master schedules the freeze, resume and shutdown itself; with `--save-restore` it also saves the federation at the midpoint freeze and restores that save at a second freeze. A third federate may join late and request the ExCO; this was tested with a probe on OpenRTI.

## Frames and attitude

The simulator works in solar-system barycentric coordinates with ecliptic J2000 axes, as Horizons defines them: the ICRF rotated about its x axis by the IAU 1976 obliquity of 84,381.448 arcseconds. The exporter rotates positions and velocities back to ICRF axes about the shared x axis, so the wire uses the SpaceFOM root `SolarSystemBarycentricInertial`. The rotation uses correctly rounded binary64 values of the cosine and sine of the obliquity and of its half, with only IEEE 754 multiplication and addition, which the standard requires to be correctly rounded. Exports made on Windows and Linux, both x86-64, are byte-identical; other architectures have not been compared. The attitude quaternion is converted from the simulator's body-to-parent rotation to SpaceFOM's parent-to-body convention and composed with the same rotation. Angular velocity stays in body axes, in radians per second.

Earlier recordings, `data/published.sf` and `evidence/precision64/precision8-observed.sf`, use ecliptic axes under the root name `SolarSystemBarycentricEclipticJ2000`. The evidence recorded with them is unchanged.

## Time

Scenario time starts at JD 2527149.5 TDB, which is 2207-01-01 00:00:00 TDB. SpaceFOM time stamps are TT seconds from the Truncated Julian Date origin (JD 2440000.5). The recording uses

`t = 7529673600.00018 + tick / 64`

where 7,529,673,600 s is the 87,149 days between the two origins and 0.00018 s approximates TT minus TDB at the start (ERFA `eraDtdb`, the Fairhead-Bretagnon series, gives 1.807e-4 s). We hold this offset constant. The model's stated accuracy does not extend to 2207, and the simulator has a single time scale, so this is an approximate mapping and not an astronomical clock conversion. At this magnitude binary64 resolves about 0.954 µs, and every 1/64-second tick is exactly representable.

## Requirement coverage

| Area of SISO-STD-018-2020 | Implemented and measured | Not yet addressed |
|---|---|---|
| Documentation (rules 3-1 to 3-4) | This profile, source pins and evidence | A complete FCD reviewed with another federation |
| Time (section 4) | Integer logical time, lookahead, ordered 64 Hz data | Clock accuracy beyond the declared approximation |
| Data and frames (sections 5 and 6) | Names, hierarchy, required attributes, coherent received samples | Deeper frame trees and `DynamicalEntity` attributes |
| Execution (section 7) | Early-joiner initialization; run, freeze, run, shutdown; ExCO and object values supplied to late joiners on request; HLA save and restore for one scripted case | Arbitrary mode precedence, recovery; late joining on Pitch pRTI or with TrickHLA |
| Services (section 8) | Publication, subscription and time management | MOM-driven Auto-Provide handling; services OpenRTI lacks |

## Deviations from SpaceFOM conventions

| Area | This prototype | SpaceFOM convention |
|---|---|---|
| Frame tree | Every body is a `ReferenceFrame` named `body_<id>`, parented directly to the root | A hierarchy of standard frames, such as `EarthMoonBarycentricInertial`, `EarthCentricInertial` and `MoonCentricInertial` |
| Vessel frame | `orbital_vessel` is parented to the solar-system barycentric root. Near the Moon, about 1.5e11 m from the barycentre, binary64 resolves about 30 µm, which limits what the wire can carry. The accuracy study does not use the wire: its samples are exact decimal expansions of the integer state | The vessel parented to a nearby body frame |
| Body metadata | Radius and gravitational parameter travel in a user-supplied tag | Not part of the standard `ReferenceFrame` attributes |
| Required federates | The Master waits for the required federate by polling `getFederateHandle`; Portico does not implement it | Discovery of joined federates through the MOM |
| Pacing | The Master holds the Pacing role but runs as fast as logical time allows | The Pacing federate relates scenario time to wall-clock time |
| Roles | Master, Pacing and Root Reference Frame Publisher are fixed to one federate | Roles may be assigned among federates |

## Extensions

The recording header, the per-frame tick and a provenance hash of the source state travel as user-supplied tags. Body radius and gravitational parameter travel in the header tag. These are prototype conventions, not SpaceFOM attributes, and a recipient needs this profile to decode them. The standard physical-entity state is meaningful without them. The hash identifies the source state; it does not authenticate it.

## Terms

| Term | Meaning |
|---|---|
| ExCO | Execution configuration object, the SpaceFOM object through which the Master announces execution modes |
| MTR | Mode transition request, the SpaceFOM interaction a federate sends to ask for a mode change |
| TSO, TAR, TAG | Timestamp order; time advance request; time advance grant |
| LCTS | Least common time step, the federation's logical time step, carried in the ExCO |
| CTE | Central timing equipment, an external wall clock shared by a federation |
| FCD | Federate compliance declaration |
| FESFA | Federation execution-specific federation agreement |
| MOM | HLA Management Object Model |
| CRC | Pitch pRTI's central RTI component |
| Recording | The binary file of published states, described in [native/spacefom/README.md](../native/spacefom/README.md#recording-format) |
| Receipt | A JSON record of one measurement: its inputs, outputs and their SHA-256 hashes |

## References

- [SISO-STD-018-2020](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-018-2020_srfom.pdf)
- [OpenRTI source at the pinned revision](https://sourceforge.net/p/openrti/OpenRTI/ci/6e31e0cd50de1852813a98679e8731ad2c97e54b/tree/)
- [SpaceFOM modules at the pinned TrickHLA revision](https://github.com/nasa/TrickHLA/tree/9faa0c5e547acb2596047c9bb875cb34ccb0fa2a/FOMs/SpaceFOM)
