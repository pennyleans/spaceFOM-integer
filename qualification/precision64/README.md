# Refinement study

The assessment and plots run from the included observations. The probe that produced those observations needs the simulator source.

## Reassess accuracy and timing

From the repository root:

```powershell
python qualification/precision64/reference/assess_candidate.py physics --oracle qualification/reference/oracle.py --selected-root evidence/precision64/observations/selected --coarse-root evidence/precision64/observations/coarse --legacy-root evidence/precision64/observations/legacy --factor 8 --output <new-physics-receipt.json>
python qualification/precision64/reference/assess_candidate.py timing --benchmarks evidence/precision64/benchmark-input.json --output <new-timing-receipt.json>
```

`selected`, `coarse` and `legacy` hold observations at eight, four and one internal steps per tick. Output paths must be new. The reference evaluates closed-form solutions with the platform's floating-point math library, which can differ in the last bit between operating systems. Rerunning the eight-step assessment on Linux x86-64 with Python 3.11, 3.12 and 3.13 reproduces every maximum error, gate and outcome exactly; the RMS fields differ by at most 6e-7 relative. The reference's hash and the acceptance limits are fixed in [`reference/acceptance.json`](reference/acceptance.json). The timing receipt evaluates eight and sixteen steps; the high-spin workload is assessed separately in `evidence/precision64/timing/`.

## Regenerate the figures

The figures were produced with Python 3.14 and Matplotlib 3.10.8, which is used for analysis only. In an environment with that version:

```powershell
python qualification/precision64/plot_results.py
```

This writes the SVG and PNG figures in `docs/figures/`. `precision64-plot-data.json` records the plotted values, input hashes, script hash, output hashes and renderer versions. Image metadata omits dates, and the SVG hash salt is fixed, so the output is reproducible.

The convergence figure shows the maximum sampled error of the three orbital scenarios at one, four and eight steps. The timing figure shows the eight-step mean and empirical 99th percentile on both machines.

## Probe

```powershell
dotnet build qualification/precision64/Probe -c Release -p:FlightSourceRoot=<simulator-source>
dotnet qualification/precision64/Probe/bin/Release/net10.0/Flight.Session.Tests.dll case earth-orbit 3 <simulator-data> <new-output>
dotnet qualification/precision64/Probe/bin/Release/net10.0/Flight.Session.Tests.dll bench 3 8192 <simulator-data> <new-output>
dotnet qualification/precision64/Probe/bin/Release/net10.0/Flight.Session.Tests.dll spin 3 8192 <simulator-data> <new-output>
```

The numeric argument is a power of two: `3` selects eight internal steps. Command ticks stay at 64 Hz. The scripts in `runners/` record how the runs were launched; set `DOTNET_EXE` to choose the .NET executable.
