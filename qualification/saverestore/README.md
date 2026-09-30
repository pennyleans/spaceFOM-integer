# Saved-state round trip

`state-roundtrip.cpp` compiles the publisher and observer sources unchanged and checks their saved-state encodings without an RTI, using a recording:

- The observer's state after the midpoint frame, restored into an observer that has received up to three quarters, re-encodes to the saved bytes, returns to the saved tick and sets the later frames aside for comparison.
- The publisher's state re-encodes to the saved bytes.
- Truncated and extended states, and an observer state saved for a different recording, are refused.

It checks the encodings only. HLA save and restore themselves need an RTI that implements them; see [native/spacefom/README.md](../../native/spacefom/README.md#save-and-restore).

```bash
cmake -S qualification/saverestore -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Release -DOPENRTI_ROOT=<transport>/runtime
cmake --build <build>
LD_LIBRARY_PATH=<transport>/runtime/lib <build>/spacefom-state-roundtrip data/published-icrf.sf
```

Any 1516e RTI's headers and libraries will do for the build; the program does not connect to one. The Linux result is in [evidence/linux/current/state-roundtrip](../../evidence/linux/current/state-roundtrip/stdout.txt).
