# Qualification

Thresholds are declared before measurement: [`contract.json`](contract.json) for the baseline study and [`precision64/reference/acceptance.json`](precision64/reference/acceptance.json) for the refinement study. Accuracy, replay and exchange each receive a separate outcome. A failure stays a failure; changing a threshold would require a new, separately declared experiment.

| Directory | Purpose | Needs simulator source |
|---|---|---|
| [`reference/`](reference/README.md) | Closed-form, GMAT and Horizons comparisons | No |
| [`precision64/`](precision64/README.md) | Refinement study: assessment, plots and probe | Probe only |
| [`wire/`](wire/README.md) | Recording decoder and HLA fault probes | No |
| [`saverestore/`](saverestore/README.md) | Round trip of the federates' saved-state encodings | No |
| `CoreProbe/` | Baseline trajectories, replay and session restore | Yes |
| `BoundaryProbe/` | Restore refusals and attitude projection | Yes |

The Earth and Moon orbits run for more than one period. The finite burn is constant inertial thrust followed by coast. The 60-second lunar coast uses the released multi-body initial conditions. Initial conditions and sampled outputs are observations of the integer state, not restorable state.

`CoreProbe` and `BoundaryProbe` reference the simulator source through the `FlightSourceRoot` MSBuild property:

```powershell
dotnet build qualification/CoreProbe -c Release -p:FlightSourceRoot=<simulator-source>
dotnet qualification/CoreProbe/bin/Release/net10.0/Flight.Session.Tests.dll case earth-orbit 64 <simulator-data> <new-output>
dotnet qualification/CoreProbe/bin/Release/net10.0/Flight.Session.Tests.dll session <simulator-data> <new-session-output>
dotnet qualification/CoreProbe/bin/Release/net10.0/Flight.Session.Tests.dll interrupt <simulator-data> <session-output>
dotnet qualification/CoreProbe/bin/Release/net10.0/Flight.Session.Tests.dll resume <simulator-data> <session-output>
dotnet run --project qualification/BoundaryProbe -c Release -p:FlightSourceRoot=<simulator-source> -- <simulator-data> <new-boundary-output>
```

`interrupt` exits with code 23 after flushing the midpoint snapshot; the other commands exit with zero. Each run needs a new output directory. Results are summarized in the [report](../docs/report.md).
