# Reference comparisons

These comparisons use the baseline setting of one integration step per tick. Method and reproduction steps are in [qualification/reference](../../../qualification/reference/README.md).

| Path | Contents |
|---|---|
| `final-v1/numerical/` | Eight receipts comparing the simulator with closed-form and refined multi-body references at 64 Hz and 128 Hz |
| `final-v1/refinement-summary.json` | Sample coverage and the 64 Hz to 128 Hz refinement checks |
| `final-v1/gmat-*` | Four orbit and two finite-burn runs of NASA GMAT R2026a: script, console output, state table and receipt |
| `final-v1/horizons-model-64.json` | Comparison of the multi-body model with JPL Horizons after 60 s |
| `final-v1/oracle-self-tests.txt` | Five reference self-tests |
| `horizons-acquisition/` | The original Horizons responses, with request parameters and hashes |
| `gmat-acquisition.json` | Identity of the downloaded GMAT archive and the runtime files used |
| `export-provenance.json` | Original and exported hashes of files whose local paths were replaced |

GMAT scripts and console logs have local paths replaced with `<reference-root>`, `<gmat-home>` and `<private-results>`. They are for inspection; the generators in `qualification/reference` produce runnable scripts. State tables, observations, Horizons responses and numerical receipts are unchanged. The script hashes in GMAT receipts identify the scripts before path replacement, and `export-provenance.json` maps them to the files here.

The first multi-body reference accumulated rounding in outer-planet coordinates of order 1e12 m, which showed as a 0.117 m refinement discrepancy for Neptune. The corrected reference integrates each body's deviation from its initial straight-line path and subtracts initial states in decimal before converting to binary64. Its largest refinement residual is below 8.53e-14 m. Early GMAT scripts had setup errors: a propagation stop treated as absolute rather than relative, accumulated epoch rounding, a misspelled thruster property, a tank too small to initialize, and an empty force model that GMAT silently replaced with Earth gravity. Each was found by the comparison checks and corrected. No simulator threshold or state changed. Those attempts are kept in our private archive.
