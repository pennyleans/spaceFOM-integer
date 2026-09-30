# Wire decoder and HLA probes

This is a second implementation of the recording format, written in Python using only the standard library. Its author had read the native and managed adapters, so it is not a blind implementation. It is also not a federate or a trajectory reference.

## Files

- `oracle.py`: a strict, bounded `2207SF01` decoder and exact field-by-field comparison. It imports no simulator, managed, native or RTI code.
- `known_state.json`: fourteen hand-written little-endian binary64 values, 112 bytes. Powers of two make each expected value easy to check by hand.
- `asymmetric_state.json`: a normalized quaternion with distinct components, its hand-derived rotation, and distinct angular rates.
- `test_oracle.py`: known-value, metadata, dimension and state rejection tests, and first-difference examples.
- `run_semantic.py`: compares a production-encoded state with the asymmetric fixture and runs mutated copies of the decoder.
- `build_faults.py`: copies the native sources to a new scratch directory, injects faults into the publisher only, records the diff and hashes, and builds with the existing warnings-as-errors settings.
- `run_probes.py`: starts real local RTI, publisher and observer processes, runs the decoder and fault trials, records output and log identities, and stops only the processes it started.

## Decoder

The decoder checks the magic bytes, signed frame and body counts, total dimensions, every metadata length and value, unique IDs, physical metadata bounds, the exact file length, contiguous ticks, fourteen finite values per state, the quaternion norm and the state time. It accepts up to 115,201 frames, 128 bodies, two million body-frame pairs and 256 MiB. Metadata is printable ASCII of at most 128 bytes. These limits are stricter than some of the native adapter's.

Comparison covers every metadata field, tick, carried provenance byte and binary64 bit; signed zero counts as a difference. The first difference is reported with both offsets, the field name, the values and the bytes. Malformed input is rejected with a field and offset before comparison. Carried hashes are compared as bytes; the decoder cannot authenticate them or reconstruct the integer state.

```powershell
python qualification/wire/test_oracle.py
python qualification/wire/oracle.py decode data/published.sf
python qualification/wire/oracle.py compare data/published.sf <received-recording.sf>
```

## HLA probes

The runtime is expected under `out/transport`. The isolated fault build also needs an OpenRTI SDK with headers and import libraries, passed explicitly. Each invocation needs new scratch and evidence directory names.

```powershell
python qualification/wire/build_faults.py --scratch <new-fault-build-directory> --rti-sdk <openrti-sdk-directory> --evidence evidence/qualification/wire/<new-build-name>
python qualification/wire/run_probes.py --scratch <new-run-directory> --evidence evidence/qualification/wire/<new-run-name> --fault-publisher <new-fault-build-directory>/build/Release/spacefom-publisher.exe --fault-build-receipt evidence/qualification/wire/<new-build-name>/build.json --timeout 15
```

All traffic binds to `127.0.0.1` on a locally allocated port. The runner accepts deadlines from 10 to 20 seconds; the recorded run used 15.

| Probe | Implementation | Pass condition |
|---|---|---|
| Normal | Accepted publisher and observer | Both exit with zero; the decoder finds the exact recording |
| Observer delayed 500 ms | Accepted publisher and observer | The same exchange after a delayed early join; late joining is not tested |
| Missing body update | Publisher omits body 0 at tick 128 | Observer refuses the incomplete frame; no complete or partial output |
| Publisher interrupted | Publisher pauses after its tick 256 grant and is stopped | Observer writes no complete or partial output |
| Observer interrupted | Same pause; the observer is stopped | Observer writes no complete or partial output |
| Existing output | Accepted observer with an existing output file | Exits before connecting; file unchanged |

The 20-second pause in the fault publisher only makes interruption deterministic. It also means the observer-interruption probe cannot measure how the publisher detects a failed peer, so that probe shows output containment only. A containment pass is not a recovery pass.

Raw logs and received recordings stay in the scratch directory. Exported logs record both their original and redacted SHA-256. Received recordings identical to the input are not duplicated.

The first fault build failed because a test-only `getenv` call triggered an MSVC deprecation warning under `/WX`; the harness now uses `_dupenv_s`. The first probe run's log redactor shortened an `rti://` argument; it now distinguishes drive paths from URIs. `fault-build02` and `run02` are the final runs. Neither correction touched the adapter.

## Attitude semantic tests

The original fixture used the identity attitude, so swapped quaternion y and z labels passed all 61 original tests. The default suite now includes the asymmetric attitude (1, -2, -4, -10)/11, whose parent x axis must map to (-111, -4, 48)/121, and reports 80 tests. Expected components are addressed by field name. The tests reject label swaps, wire swaps and wrong conjugation, and mutated copies of the decoder must fail the full suite.

`evidence/qualification/wire/semantic-v1/` holds the 20-test supplemental receipt, including a production-encoded state from the boundary probe. All non-quaternion fields match bit for bit. The normalized production quaternion is compared with the rational fixture to within the declared 1e-15; its bytes differ from the ideal value, as expected. The receipt's scope line, written when it was produced, says an independent re-review was pending; no such review has been made.

```powershell
python qualification/wire/test_oracle.py --semantic-only --production-state <asymmetric-mapped-state.bin>
python qualification/wire/run_semantic.py --production-state <asymmetric-mapped-state.bin> --boundary-receipt <boundary-receipt.json> --boundary-source qualification/BoundaryProbe/Program.cs --scratch <new-semantic-scratch-directory> --evidence evidence/qualification/wire/<new-semantic-name>
```
