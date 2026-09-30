# Acceptance for the 64 Hz refinement

[`acceptance.json`](acceptance.json) declares the thresholds; it was written before any candidate was measured. `assess_candidate.py` reads the exported observations and the hash-pinned reference in `qualification/reference/oracle.py`. It does not read or import simulator code.

## Accuracy

Keep three input roots, `legacy`, `coarse` and `selected`. Each holds the four nominal scenario directories and `earth-eccentric-inclined`; a directory is named after its scenario, optionally with a `-64` suffix. Each contains `initial.json` and `samples.jsonl`. `steps_per_second` stays at 64, and `integration_substeps` gives the internal step count. Only the legacy one-step observations may omit it. Every one-second sample must be present, with its original tick index.

```powershell
py -3 assess_candidate.py physics --oracle <pinned-oracle.py> --selected-root <selected> --coarse-root <coarse> --legacy-root <legacy> --factor 16 --output <new-physics-receipt.json>
```

The factor shown is an example. `--nominal-only` screens the four nominal scenarios and always leaves full acceptance false. The procedure is to choose a setting from nominal accuracy and measured timing, then run the held-out eccentric, inclined orbit at that setting, at half of it and at one step. Its initial conditions are in [`held-out-initial.json`](held-out-initial.json) and must otherwise be identical across runs.

## Timing

Timing input uses schema `precision-benchmark-v1` with a `runs` array. Each run needs:

- `platform`: `windows-x64` or `macos-arm64`;
- `integration_substeps`: 1, 2, 4, 8, 16 or 32;
- `outer_hz`: 64;
- `warmup_ticks`: at least 1,024;
- `measurements_ms`: at least 8,192 finite, nonnegative per-tick costs;
- `workload_id`: `coast` or `coupled-controls`, with the same `workload_sha256` for a workload across settings and platforms;
- true for `includes_physics`, `includes_controls_and_shared_session`, `includes_transport_serialization` and `includes_display_capture`.

Each measured tick must include all of the stated work. Physics-only timings may not be scaled by an assumed overhead.

```powershell
py -3 assess_candidate.py timing --benchmarks <benchmark-input.json> --output <new-timing-receipt.json>
```

The mean and the nearest-rank 99th percentile must both be at most 12.5 ms, leaving 20% of the 15.625 ms tick, on both platforms and both workloads. A pass at the selected setting and a failure at the next higher setting establish the selection. Acceptance also requires a complete accuracy receipt at the same setting, a pass on the held-out orbit, and the cross-machine replay evidence.

Neither command overwrites an existing receipt. Numerical error, model differences from Horizons and byte equality are reported separately.

## Files

| File | Contents |
|---|---|
| `physics-nominal-v1.json`, `physics-complete-v1.json` | Accuracy receipts before and after the held-out orbit |
| `selection-freeze-v1.json` | The setting chosen before the held-out run |
| `timing-final-independent-v2.json` | Timing receipt for the final build |
| `high-spin-independent-v1.json` | Recomputed statistics for the high-spin workload |
| `test_assess_candidate.py` | Tests for the assessment script |
