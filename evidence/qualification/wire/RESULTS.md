# Wire results

The exchange reproduced the recording exactly, and incomplete exchanges produced no output. Graceful recovery from a failed peer was not tested.

## Results

The final evidence is `run02/summary.json`, its per-probe receipts and `fault-build02/build.json`.

- The decoder's 61 tests passed. The 112-byte known-value fixture has SHA-256 `973f4be0115ffacdf91c7b057c10088da1b8524b6d910e40d6872ba11172ff90`.
- The recording holds 3,841 frames of 11 bodies and one vessel, 46,092 states in all. Every dimension, metadata field, time field and state component was decoded without the adapter's own code.
- The normal exchange and the exchange with the observer delayed by 500 ms both exited cleanly and reproduced every byte. The received SHA-256 is `b83ad5e6eada4626606e1d5358af97e49a25c102a51b5a8364b3b1efdf0efc56`.
- With one body update omitted at tick 128, the observer exited with `time grant without complete frame` and wrote neither a final nor a partial recording. The publisher did not exit on its own and was stopped at the 15-second test deadline.
- With the publisher interrupted after its tick 256 time grant, the observer exited with the same message and wrote no output.
- With the observer interrupted, it wrote no output. The injected publisher was held for 20 seconds by design, so the 15-second cleanup does not measure how the publisher detects a failed peer.
- A copy of the accepted recording placed at the observer's output path was refused, and the copy was unchanged. The input recording and adapter sources were unchanged throughout.

## Interpretation

The decoder was written separately from the adapter but by an author who had read the adapter source. It uses only the Python standard library and loads no adapter, managed or simulator code. Because both federates and the RTI are ours, these tests do not establish interoperation with other implementations. Byte equality does not establish orbital accuracy, authenticity of the carried hash, or SpaceFOM compliance.

The fault builds modify only a scratch copy of the publisher; the source diff and all hashes are recorded. The accepted observer was used in every trial. Launched processes were stopped through their own handles, never by process name.

A `passed` field on a fault receipt means only that no complete or partial output was written under that fault. Natural exit, forced interruption and deadline cleanup are recorded separately. Reconnection, late joining, restart and network partition were not tested.

Log paths are redacted, and each log records its original and redacted SHA-256. Received recordings identical to `data/published.sf` are not duplicated here.

The [semantic tests](semantic-v1/RESULTS.md) extend the decoder to an asymmetric attitude.
