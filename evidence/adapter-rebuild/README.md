# Adapter rebuild

We rebuilt the publisher and observer from this repository with MSVC 19.44 against the same pinned OpenRTI runtime. The four native source and build files are identical to those used in the original prototype; only script defaults and documentation changed.

The loopback exchange reproduced the recording byte for byte, and all six refusal probes passed. `identities.json` binds the source files to the deployed binaries. The receipt and transition logs are included. Workstation paths are replaced with `{work}`, and the original hashes are recorded separately.
