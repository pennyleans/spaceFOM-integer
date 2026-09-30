# Round 8 interoperability report: renamed verifier packages and full runs on three platforms

Branch `interop/20260929-8`, started from `review/public-candidate` at `f71d0e8`. The
replay verifier was rebuilt as `2207-verify` against the simulator source at revision
`33aa8e6`, the verifier assets of draft release `verify-9e44426` were replaced, and the
new packages ran full checks on Windows x64, Linux x64 and Apple silicon. Host names are
written as `{host}` and every absolute path under a home directory as `{work}`. The
release was left as a draft and was not published.

## Results

| Run | What ran | Result |
|---|---|---|
| `verifier/packages.txt` | all six packages rebuilt with the packaging script from `f71d0e8` against the simulator source at `33aa8e6` | Pass: stamp `9e44426` matches `verify/expected.json`; archives named `2207-verify-9e44426-<rid>` |
| Release housekeeping | every `iss-verify-*` asset and the old `SHA256SUMS` deleted, six new archives and the new `SHA256SUMS` uploaded, exchange zip kept | Draft release `verify-9e44426` (id 398836095) holds eight assets, still a draft |
| `verifier/windows-win-x64` | win-x64 zip from the release, full run | Pass: 1,497,350 states in 141 s, exit 0 |
| `verifier/wsl-linux-x64` | linux-x64 archive from the release, full run in WSL2 | Pass: 1,497,350 states in 109 s, exit 0 |
| `verifier/mac-mini-full` | osx-arm64 archive from the release, full run, quarantine clear only | Pass: 1,497,350 states in 70 s, exit 0 |

## Verifier packages

The packaging script was run from the candidate tree at `f71d0e8` against the simulator
source at `33aa8e6`; the stamp check printed
`9e4442614ca9534752166510dcd1ef069fbe66c0c595510ef2423f745dd7be2f`, the identity in
`verify/expected.json`. The verifier's name change in `f71d0e8` also renames the
archives: the six new files are `2207-verify-9e44426-<rid>`, where the replaced assets
carried the earlier name. New SHA-256 values:

```
b11a11ec712edb5743df712de3dfe585c8e79cf98efef414d8179c2b33e9746f  2207-verify-9e44426-linux-arm64.tar.gz
c729dbbd7044c2259659815fb4149b737ccfa5f5d1413ce6426acfb9836e884b  2207-verify-9e44426-linux-x64.tar.gz
13f1602c2a14209288b97de9ed9704946a8794dbf23f8a57e7755fb39f3c9387  2207-verify-9e44426-osx-arm64.tar.gz
40a6e6fbf3239a6ac270ab0d695df1f5fda8b0abb07b23c8983cff261f85f91d  2207-verify-9e44426-osx-x64.tar.gz
13bc7cddc280e7220b50b81f86faf44f2c83dd837b2ae726e9a57de2563455d4  2207-verify-9e44426-win-arm64.zip
bc67cf64c8a1b163414b65124f64079b0d3ece42d432fe6001d04aa5e9fa0553  2207-verify-9e44426-win-x64.zip
```

Every `iss-verify-*` asset and the previous `SHA256SUMS` were deleted from draft release
`verify-9e44426` (id 398836095), and the six new archives plus the new `SHA256SUMS` were
uploaded in their place; the exchange zip stayed. The final asset list, with sizes, is in
`verifier/packages.txt`. The release is still a draft.

## Full runs

All three packages were downloaded from that draft release, their hashes checked against
`SHA256SUMS`, extracted fresh, and run in full, without `--quick`, with `--receipt`.
Each run passed all six digest streams: `earth-orbit` 384,001 states, `moon-orbit`
460,801, `inertial-burn` 7,681, `lunar-fixture` 3,841, `earth-eccentric-inclined`
640,001 and the `session` 1,025, 1,497,350 states in all, bit for bit against the
published hashes.

- Windows x64: single executable, 141 s, wall 141.7 s, exit 0, on the AMD Ryzen 9
  machine with 48 GB.
- Linux x64: single executable in WSL2 Ubuntu 24.04.4 LTS, 109 s, exit 0.
- Apple silicon: folder package, 70 s, wall 71 s, exit 0, with only
  `xattr -dr com.apple.quarantine .`, no re-signing and no `chmod`.

Receipts, stdout and machine notes for each run are under `verifier/`.

## Findings

1. The rename and rebuild did not change behavior. All six digest streams match on all
   three platforms, so the recording remains bit-reproducible across the three operating
   systems and the two architectures tested.
2. The archives keep the intended layout and permissions: single executables on Windows
   and Linux, a self-contained folder with the executable bit on macOS.
3. The macOS package runs after only the quarantine clear, with no re-signing and no
   `chmod`, as it has since the folder layout.
4. The draft release now carries only `2207-verify` assets and the exchange zip;
   nothing with the earlier verifier name remains.

## What was not done

- The win-arm64, linux-arm64 and osx-x64 packages were built and uploaded but not run;
  no machines with those platforms were available.
- No federated exchange, save and restore, or third-party federate work was done this
  round.
- The release was left as a draft.
