# Restore and projection probes

These probes close two gaps found in the first qualification: refusal had been tested only at the parser, not through restore, and the attitude test used the identity quaternion, which cannot reveal swapped or conjugated components.

`run02/receipt.json` records four refusals, each of which leaves the live session's complete encoding unchanged: truncated bytes, an invalid attitude, a duplicate vessel or body identity, and an invalid guidance target. The last three pass decoding and are refused by the internal restore path. Truncation is refused by the decoder, as intended.

`mapped-state.bin` is the production projection of an exact cyclic rotation, in which body x maps to parent y and parent x maps to body z. Its fourteen fields match hand-declared binary64 values exactly. `asymmetric-mapped-state.bin` uses a quaternion with distinct components proportional to (1, 2, 4, 10). The projected parent-to-body quaternion is (1, -2, -4, -10)/11, and parent x maps to (-111, -4, 48)/121, both within 1e-15. Distinct position, velocity and angular-rate components also test units and signs. The Python wire decoder checks the same payload separately.

A first run stopped on the simulator's documented `unnormalized snapshot attitude` fault because the probe's exception filter was too narrow. The probe was corrected; the simulator was not changed, and the first run is not counted.

The probe source is [`qualification/BoundaryProbe`](../../../qualification/BoundaryProbe/), with a fixture helper from [`qualification/CoreProbe/Fixtures.cs`](../../../qualification/CoreProbe/Fixtures.cs). These probes ran on x86-64 Windows only. They do not establish general frame transformations, absolute time accuracy, authenticated restore or cross-machine agreement for every refusal.
