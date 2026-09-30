# Baseline replay evidence

These runs use the baseline setting of one integration step per 64 Hz tick.

`windows/` holds eight paired physical runs on x86-64 at 64 Hz and 128 Hz. Each pair compares the complete canonical snapshot bytes at every tick, restores the second branch from serialized midpoint bytes, and continues comparing. The 128 Hz runs serve the numerical refinement check only; the simulator runs at 64 Hz.

`cross-device.json` compares x86-64 Windows and AArch64 macOS on .NET 10.0.12. All four 64 Hz per-tick digest streams match, covering 856,324 complete physical states. The initial observations and the midpoint and endpoint snapshots match byte for byte. Within each paired run the full snapshot bytes are compared at every tick; across machines, per-tick SHA-256 digests are compared.

The 16-second session scenario compares all 1,025 canonical session records byte for byte across machines. It exercises translation, thrust, rotation, attitude hold, rotation damping and prograde guidance, with no mission defined. It does not cover every mission or command schedule.

`fresh-process-resume.json` covers the 513 records from tick 512 to 1024. One process writes and flushes the midpoint snapshot and exits deliberately with code 23; a second process restores the snapshot and continues. This tests restart after a complete snapshot, not recovery from an interrupted write.

`source-preservation.json` binds the simulator source used for these runs; all 3,944 files are unchanged apart from a regenerated build stamp. The per-tick digest streams are identified by hash in `retained-traces.json` and are not included. The sampled observations included here are enough to reproduce the numerical assessments.

`logs/` holds the simulator's own test suites (24 of 24 core tests pass, and the session suite passes), plus build and probe logs. `log-provenance.json` records the original and exported hash of each log. Probe timings in these logs include comparison and disk work and are not performance measurements.

The probe programs in `qualification/CoreProbe` and `qualification/BoundaryProbe` build against the simulator source under the assembly name `Flight.Session.Tests`, which the simulator already grants access to its internal restore path. Production visibility is unchanged.
