# Physical references

These scripts use only the Python standard library and the exported observations. They were written from the published equations without access to the simulator source. They measure numerical error against stated equations, not physical truth.

## Results at the baseline setting

The authoritative run is [`final-v1`](../../evidence/qualification/reference/final-v1). Every declared one-second sample is required: 6,001 for the Earth orbit, 7,201 for the Moon orbit, 121 for the burn and 61 for the multi-body coast, at each rate. All eight absolute-error gates and all four refinement gates pass.

| Scenario | Duration | Max position error, 64 Hz | Max position error, 128 Hz | Reference |
|---|---:|---:|---:|---|
| Earth orbit | 6,000 s | 4.6353 mm | 1.1588 mm | Universal-variable two-body solution |
| Moon orbit | 7,200 s | 0.77589 mm | 0.19398 mm | Universal-variable two-body solution |
| Finite burn and coast | 120 s | 8.38e-7 mm | 2.10e-7 mm | Closed-form variable-mass rocket |
| Multi-body lunar coast | 60 s | 3.15e-3 mm | 7.88e-4 mm | Refined mutual point-mass RK4 |

Both orbits run for more than one period. The closed-form solutions start from the exported initial velocity, including its integer rounding. Energy and angular-momentum drifts near 1e-16 are at the binary64 evaluation floor.

**Methods.** The two-body solution solves Kepler's time-of-flight equation in universal variables and evaluates the f and g coefficients. The rocket solution integrates constant inertial thrust with linear propellant depletion at constant exhaust velocity, using a series form to avoid cancellation over short burns. The burn scenario includes a distant gravitating body required by the snapshot format; its effect is bounded below 7.21e-27 m over 120 s. The multi-body reference integrates each body's deviation from its initial straight-line path, with initial states subtracted in decimal before conversion to binary64. For the vessel, the difference between steps of 0.25 s and 0.125 s is 2.33e-10 m and 7.11e-14 m/s. Five self-tests cover circular, eccentric and reverse-time conics, a half-mass rocket, fourth-order refinement, and invariance under translation and velocity boosts.

**Thresholds**, fixed before measurement: orbit and multi-body position below 0.1 m and velocity below 1e-4 m/s; orbital energy and angular-momentum drift below 2e-6; burn position below 0.01 m, velocity below 1e-4 m/s and mass below 1e-9 kg; multi-body reference refinement below 1 mm and 1e-6 m/s. The 128 Hz to 64 Hz error ratio must be below 0.4, unless both errors are already below 1e-5 m and 1e-8 m/s. [`refinement-summary.json`](../../evidence/qualification/reference/final-v1/refinement-summary.json) records each comparison.

## Outside references

**NASA GMAT.** We ran the [R2026a release](https://sourceforge.net/projects/gmat/files/GMAT/GMAT-R2026a/) through its console executable, with point-mass models matched to the exported relative state and gravitational parameter, fixed one-second RK89 steps and every exported sample time. The largest simulator-to-GMAT position differences at 64 Hz are 4.63615 mm for the Earth orbit and 0.775794 mm for the Moon orbit. Our closed-form solutions differ from GMAT by at most 1.20 µm and 0.233 µm. Reported elapsed times differ from commanded times by at most 1.57e-7 s, and every timestamp is checked to within 1 µs.

The GMAT finite burn uses a constant chemical-thruster force, the same exhaust speed, depleting propellant, a 60 s burn and a 60 s coast. At 64 Hz the largest differences from the simulator are 2.061e-7 m, 1.03e-14 m/s and 2.467e-11 kg. A constant 10,000 km position offset avoids GMAT's zero-radius state and is removed in decimal. An explicit, negligible point mass stops GMAT from substituting Earth gravity; its effect is bounded below 7.21e-17 m.

GMAT's bundled ephemerides do not reach 2207, so these runs use a 2000 epoch. The isolated problems do not depend on epoch, and only elapsed time and relative state are compared. This is not a GMAT propagation of the 2207 solar system.

**JPL Horizons.** [Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html) supplies barycentric ecliptic J2000 geometric vectors for all 11 bodies at 2207-01-01 00:01:00 TDB, converted exactly from km and km/s to SI units. The original JSON responses, [API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) parameters, version (1.2), dates and hashes are kept. These states are not used to initialize either solver. After 60 s the largest difference between our point-mass model and Horizons is 4.193 mm and 0.1109 mm/s, both for Uranus. Initial position differences range from 0.020 mm to 0.756 mm. These residuals combine initial-state rounding, Horizons output precision and its richer dynamics. They are model differences, not integration error, and there is no Horizons ephemeris for the vessel.

## Reproduce

Run from the repository root. The recorded runs used Python 3.14.7 on Windows x64. The reference evaluates closed-form solutions with the platform's floating-point math library, which can differ in the last bit between operating systems. Rerunning the eight-step assessment on Linux x86-64 with Python 3.11, 3.12 and 3.13 reproduces every maximum error, gate and outcome exactly; the RMS fields differ by at most 6e-7 relative. Output paths must be new.

```powershell
py -3 -m unittest discover -s qualification/reference -p test_oracle.py -v
py -3 qualification/reference/oracle.py evidence/qualification/replay/windows/earth-orbit-64 --output new-reference/earth-orbit-64.json
py -3 qualification/reference/oracle.py evidence/qualification/replay/windows/lunar-fixture-64 --output new-reference/lunar-fixture-64.json
```

Repeat for all eight scenario and rate directories, then collect the refinement checks:

```powershell
py -3 qualification/reference/summarize.py new-reference --output new-reference/refinement-summary.json
```

Download GMAT into a separate directory. The archive hash is fixed before extraction, optional plugins are disabled, and the acquisition script records the hash of every extracted file. GMAT is not redistributed here.

```powershell
py -3 qualification/reference/fetch_gmat.py ../external-reference
py -3 qualification/reference/gmat_reference.py evidence/qualification/replay/windows/earth-orbit-64 --gmat-dir (Resolve-Path ../external-reference/GMAT-R2026a-console).Path --output (Join-Path (Get-Location) 'new-reference/gmat-earth-64')
py -3 qualification/reference/gmat_burn.py evidence/qualification/replay/windows/inertial-burn-64 --gmat-dir (Resolve-Path ../external-reference/GMAT-R2026a-console).Path --output (Join-Path (Get-Location) 'new-reference/gmat-burn-64')
py -3 qualification/reference/horizons_reference.py evidence/qualification/replay/windows/lunar-fixture-64 --acquisition evidence/qualification/reference/horizons-acquisition/acquisition.json --output new-reference/horizons-model.json
```

Give GMAT absolute output paths when running it from another directory. To query Horizons again instead of reusing the stored responses, replace `--acquisition` with `--acquire` and a new directory; the result is a new dataset.

GMAT R2026a is used for reference only, under the [Apache-2.0 licence](https://github.com/nasa/GMAT/blob/R2026a/License.txt), from the archive with SHA-256 `f7b00bdeb51e75f5f0a93380a97109f0505e75396f69a43cd5583c21f5fed9fc`. Its dependencies and data keep their own terms. The [acquisition receipt](../../evidence/qualification/reference/gmat-acquisition.json) identifies the archive and the files used. [Evidence notes](../../evidence/qualification/reference/README.md) describe the corrections made along the way.
