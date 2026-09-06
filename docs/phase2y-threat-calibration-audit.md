# Phase 2Y — Threat Calibration Audit (evidence-gathering only, no code changed)

**Status: audit only.** No production code, config, or threshold was modified.
Reproducible via `ai-service/scripts/evaluate_phase2y_proximity_calibration.py`
(real, read-only, uses the actual Phase 2X `_proximity_and_speed()` against real
historical data in `database/dev.db`).

## Headline finding

**None of 17 real historical `close_contact`/`fighting_candidate`/`running`/
`approaching` windows sampled across this project's entire history reach "close" under
the corrected geometry, at ANY candidate threshold from 0.05 up to 0.25** (one
`running` sample crosses at 0.25, but no `close_contact` or `fighting_candidate`
sample ever does). Their real proximity ratios cluster tightly in **0.30–0.44**,
statistically indistinguishable from each other regardless of whether the real caption
describes "sitting on a couch," "posing for a photo," or the real knife/struggle
sequence. See the full report delivered in-conversation for the complete 10-section
breakdown (real-data table, threshold sweep, knife-path trace, architecture
limitation, and recommendation).

## One-line conclusion

**No single `CLOSE_PROXIMITY_RATIO` value can be found in the tested range that
separates ordinary two-person proximity from the one real dangerous-contact
recording, because both occupy the same ratio band in this project's own real data.**
This is reported as a data-insufficiency finding, not a recommendation to abandon
proximity as a signal — see the full report's "Architecture Limitation" and
"Recommended Next Change" sections.
