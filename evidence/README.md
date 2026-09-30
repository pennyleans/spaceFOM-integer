# Evidence

Measured results, logs and receipts. Receipts bind each result to the SHA-256 of its inputs, sources and outputs. A hash identifies bytes; it does not authenticate them. Workstation paths are replaced with `{work}` or named placeholders, and each changed file has a record of its original and exported hash.

| Directory | Contents |
|---|---|
| [`precision64/`](precision64/) | The study that chose eight integration steps per 64 Hz tick: observations at one, four and eight steps, cross-machine replay, CPU timing, regression logs, the revised recording and its HLA exchange |
| [`qualification/replay/`](qualification/replay/README.md) | Baseline replay: paired full-snapshot runs and cross-machine digests |
| [`qualification/reference/`](qualification/reference/README.md) | Closed-form, GMAT and Horizons comparisons at the baseline setting |
| [`qualification/wire/`](qualification/wire/RESULTS.md) | HLA exchange, fault probes and decoder semantic tests |
| [`qualification/boundary/`](qualification/boundary/README.md) | Restore refusal and attitude projection probes |
| [`interop/`](interop/REPORT.md) | Pitch pRTI, Portico and TrickHLA runs, HLA save and restore, and the macOS and Windows verifier runs, in the rounds listed below |
| [`linux/`](linux/README.md) | Linux x86-64: replay verification on two .NET builds, the ICRF export, and HLA exchanges built with GCC, including the current publisher |
| [`adapter-rebuild/`](adapter-rebuild/README.md) | Windows exchange and refusal runs from the adapter as built from this repository, before the move to ICRF axes |
| `original-build/` | The first prototype's exchange, refusal, viewer and runtime test results |

Evidence recorded before the move to ICRF axes uses the ecliptic recording `data/published.sf` or `precision64/precision8-observed.sf` and the root name `SolarSystemBarycentricEclipticJ2000`. Results are summarized in the [report](../docs/report.md). Some records name simulator files that are not included; they identify what was measured. Earlier failed attempts are kept in our private archive; some provenance records list their hashes. Commit identifiers and branch names in the interoperability reports refer to our development history, which is also kept privately; the files each report cites are included here as they were recorded, and the source in this release is the source of the latest round.

## Interoperability rounds

These are lab notes, written by the AI coding agent that ran each round on our Windows and macOS machines, following written test plans. A later round or an analysis section supersedes an earlier finding where they differ.

| Round | Report | Main result |
|---|---|---|
| 1 | [`interop/REPORT.md`](interop/REPORT.md) | Byte-identical exchange on Pitch pRTI Free; Portico fails; first TrickHLA attempts |
| 2 | [`interop/followup/REPORT.md`](interop/followup/REPORT.md) | Update requests answered for late joiners; incomplete-frame failures on long-lived Pitch sessions |
| 3 | [`interop/round3/REPORT.md`](interop/round3/REPORT.md) | TrickHLA decodes 3,827 states bit for bit; first verifier runs on Windows and macOS |
| 4 | [`interop/round4/REPORT.md`](interop/round4/REPORT.md) | Two Master initialization steps found missing; macOS verifier fixed by the folder layout |
| 5 | [`interop/round5/REPORT.md`](interop/round5/REPORT.md) | Complete TrickHLA exchange with the corrected publisher; packages rebuilt with licence files |
| 6 | [`interop/round6/REPORT.md`](interop/round6/REPORT.md) | First HLA save and restore on Pitch; observer timing and MSVC build faults |
| 7 | [`interop/round7/REPORT.md`](interop/round7/REPORT.md) | Save and restore pass; TrickHLA 3.2.2's SpaceFOM scheme does not support them (superseded for the `Checkpoint` branch, below) |
| 8 | [`interop/round8/REPORT.md`](interop/round8/REPORT.md) | Verifier renamed `2207-verify`; full runs from the release pass on Windows, macOS and Linux |

## TrickHLA Checkpoint branch

[`interop/trickhla-checkpoint/REPORT.md`](interop/trickhla-checkpoint/REPORT.md), 30 September 2026: an unmodified federate from TrickHLA's `Checkpoint` development branch saves and restores in our federation, and every update it receives again after the restore matches the first reception bit for bit. This is a summary with its receipts; the lab notes of the rounds that led to it are not yet included.

