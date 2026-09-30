# HLA save and restore with the TrickHLA Checkpoint branch

30 September 2026.

An unmodified TrickHLA federate from the `Checkpoint` development branch of NASA's TrickHLA saved and restored mid-run in a federation it did not control. In two runs, every update it received matched the recording exactly, and every update it received again after the restore matched the first reception.

## What ran

- **TrickHLA:** the `Checkpoint` branch of [nasa/TrickHLA](https://github.com/nasa/TrickHLA) at `4f72205772d55301aefe395bda45daecf0d6855d`, with no source changes. It is a development branch; these results apply to that commit only.
- **Trick:** 25.1.1, revision `c2a3e5480dfdbe975fb94a3d54271116dbc8d89f`.
- **RTI:** Pitch pRTI Free 5.5.10, two federates, with the central component restarted before each run. The federates ran under WSL2 Ubuntu 24.04 and the RTI on Windows.
- **Our publisher:** `--master-modes --save-restore`. It saves the federation at the midpoint freeze (tick 1920, 30 s), freezes again at 45 s (tick 2880), restores the save and continues to the end of the 3,841-frame recording `data/published-icrf.sf`.
- **The TrickHLA federate,** as `orbital_observer`: the branch's `sims/SpaceFOM/SIM_Entity_Test` with the data and interaction cycle set to 1/64 s and some unused objects removed, plus the files in [qualification/trickhla](../../../qualification/trickhla/README.md): the per-update logging override, `observer-timelines.sdefine` and `input-observer-checkpoint.py`.

## Results

| Run | Exits (publisher / TrickHLA) | TrickHLA | Publisher | Updates compared per object | Missing | Received twice | Repeats differing |
|---|---|---|---|---:|---:|---|---:|
| [stock-1](stock-1/receipt.json) | 0 / 0 | checkpoint written, `federationSaved`; checkpoint loaded, `federationRestored` | `federation_saved`, `federation_restored`, `rewound tick=1920`, shutdown at 3,841 frames | 4,800 | 0 | 959 (ticks 1921 to 2879) | 0 |
| [stock-2](stock-2/receipt.json) | 0 / 0 | same | same | 4,800 | 0 | 959 (ticks 1921 to 2879) | 0 |

Both objects, `orbital_vessel` and `body_10`, matched the recording in all fourteen fields of every update ([stock-1 comparison](stock-1/comparison.json), [stock-2 comparison](stock-2/comparison.json)). A separate audit reconstructs the binary64 values from the logged text and finds every one bit-equal ([stock-1](stock-1/decoded-binary64.json), [stock-2](stock-2/decoded-binary64.json)).

The acceptance declared before these runs expected 960 repeated ticks and 4,801 updates, the count our own observer produces; each run's [acceptance.json](stock-1/acceptance.json) records that it was not met, and we have not changed it. TrickHLA had not logged tick 2880 before the second freeze. After the restore it received ticks 1921 to 3840 again, so 1921 to 2879 arrived twice and 2880 once. No tick is missing and no value differs.

## What restore needed

- **Trick-managed timelines.** TrickHLA's default simulation and scenario timelines are namespace globals outside the memory Trick manages. A checkpoint cannot reference them, writes placeholders for those two pointers, and the restore then fails to parse. Declaring the timelines in the simulation definition and pointing the execution control at them, as the branch's `SIM_Ball` example does, resolved it. [observer-timelines.sdefine](../../../qualification/trickhla/observer-timelines.sdefine) does this for our federate.
- **Our logging override.** An update without state carries a sentinel time; our override multiplied it and overflowed, which Trick traps. The override now logs only times inside the recording's window.

## Scope

- One development commit, one scripted save and restore, both in Freeze, with TrickHLA as a follower of our Master on a two-federate edition of Pitch pRTI.
- The comparison uses the states TrickHLA decoded and logged, printed with 17 significant digits, not raw RTI bytes. Logged HLA times are derived from the state time.
- Diagnostic runs with the branch's own example simulations are not included here yet; we will share them with the TrickHLA developers first.

## Files

- `stock-1/`, `stock-2/`: receipts, publisher logs, TrickHLA logs (compressed), save and restore traces, comparisons, audits and acceptance records.
- `build/`: build logs and identities for the TrickHLA federate and our publisher, and the tool versions.
- Checkpoint and saved-state files are recorded by size and SHA-256 in each receipt; their contents are not included.
