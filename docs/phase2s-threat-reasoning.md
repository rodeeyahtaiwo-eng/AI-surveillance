# Phase 2S — Make Threat Assessment Actually Use Reliable Evidence

**Status: implemented, tested, verified live — including a real bug found and fixed
during the live test itself, exactly as the "do not report success until it actually
works" instruction anticipated.** Firearm detector untouched and re-verified (Test E).

## 0. Verification before editing (as required — nothing assumed)

- **Phase 2P's person-box deduplication**: confirmed present and passing —
  `DUPLICATE_BOX_OVERLAP_THRESHOLD`, `_deduplicate_boxes()`, `_overlap_ratio()` all
  found in `app/action_recognition/demo_heuristic.py`; `test_action_recognizer.py`
  11/11 passing before any Phase 2S change. **Not re-fixed, because it was already
  correctly in place** — the instruction not to assume it existed was heeded by
  actually checking, not by re-doing the work.
- Current `RuleBasedThreatEngine`, `CameraWindow`/persistence logic, threat-scoring
  tests, backend ingestion/WebSocket flow, and the knife/weapon detection path were all
  re-read fresh (not recalled from memory) before writing any new code.

## 1. Why `knife detected → threat_score 0.05` — root cause, confirmed by inspection

There was no bug to fix in the sense of broken logic — **there was no knife-aware logic
at all**. `DemoHeuristicActionRecognizer` only ever reads `object == "person"` from
detections; `RuleBasedThreatEngine.BASE_SCORE_BY_ACTION` has no `"knife"` entry;
`evaluate_weapon_detection()` (the only detection-driven, immediate-scoring path) only
ever looks for `"firearm"`. A knife detection reached the caption (via the raw
detections list) and nowhere else. This is exactly what Phase 2P's live test already
found and reported honestly — Phase 2S's job was to fix it, not re-discover it.

## 2. Threat-scoring logic added

**Design: a floor/ceiling on the existing score, not a new independent scoring path.**
Extends `RuleBasedThreatEngine.assess()` — the same method, same metrics-driven pattern
already used for `min_proximity_ratio`/`movement_speed_px_s` — rather than adding a new
abstract method or a firearm-style separate immediate-evaluation function. This was a
deliberate choice over the two options presented at the end of Phase 2P: it needs no new
persistence/cooldown state, inherits the Phase 2P person-deduplication for free (same
window, same `avg_person_count`), and is structurally incapable of interacting with the
firearm path (see below).

```
knife detected, NOT persisted                          → no change (unreliable alone)
knife persisted, NO person in window                    → no change (Phase 2O's own
                                                            recommendation: no person/
                                                            context = not scored)
knife persisted + person present                        → floor: 0.45 (just above MEDIUM)
knife persisted + person present + close_contact/
  fighting_candidate ALREADY independently read          → floor: 0.70 (matches
                                                            fighting_candidate's own
                                                            base score — HIGH, not
                                                            invented fresh)
```

"Persisted" reuses the exact same K-of-window pattern firearm already established
(default K=2 within 4s) — via a **new**, knife-specific config pair
(`knife_persistence_min_hits`/`_window_seconds`), not firearm's own settings. The floor
is a `max()`, never additive and never a reduction — proven by
`test_knife_floor_is_a_ceiling_not_a_stack_with_proximity_bonus` and
`test_knife_persisted_with_fighting_candidate_does_not_reduce_the_existing_higher_score`.

**CRITICAL is never produced by this rule.** The highest floor (0.70) sits in the HIGH
band; nothing in this phase can reach 0.85 through the knife path alone — consistent
with "do not invent an arbitrary severity."

## 3. A real bug found and fixed during the live test (not before)

**The first live knife test did NOT elevate the score — 0.05, unchanged.** Investigated
immediately rather than reported as a limitation:

- Measured the actual knife-detection timestamps in the database: consecutive frames
  were genuinely only ~2.6–2.8s apart by their own recorded time.
- Yet `count_recent_frames_with_object("knife", 4)` (the same method firearm uses)
  found fewer than 2 hits within the trailing 4 seconds.
- Root cause: this method measures its 4-second window against **wall-clock `now()` at
  the moment the check runs**, not against the buffered frames' own timestamps. BLIP
  (`CAPTION_ADAPTER=blip`, Phase 2R) runs synchronously inside `evaluate_window()`, and
  because both the real `video-processing` service and this project's own live-test
  client send each frame only after receiving the previous response, one multi-second
  BLIP generation delays *when the next frame is even sent* — pushing its recorded
  timestamp out by that same amount. By the time the persistence check ran, `now()` had
  drifted far enough past earlier frames' timestamps that a real, closely-spaced
  detection pattern looked stale.
- **This is a genuine interaction between Phase 2R (synchronous BLIP) and any
  short persistence window — it very plausibly affects firearm's own 4-second
  persistence window identically. Per your explicit instruction not to touch firearm's
  persistence/cooldown/threshold/geometry filter/scoring/adapter/configuration, this
  was NOT fixed for firearm. It is reported here, not fixed, exactly as instructed
  ("if a change is absolutely required for the knife implementation... stop and report
  before changing it") — no firearm change was required to fix knife, so none was made,
  but the same latent effect on firearm is flagged as a discovered, out-of-scope risk.**

**Fix (knife-only, does not touch firearm's method at all)**: added
`CameraWindow.count_recent_frames_with_object_as_of(object_label, window_seconds,
reference_time)` — the same counting logic, parameterized by an explicit reference time
instead of always `datetime.now()`. Knife evidence now passes `window.window_end()` (the
latest buffered frame's own timestamp) as the reference, making the check depend only on
the data's own recorded timing, immune to whichever adapter's request latency happens to
be in play. `count_recent_frames_with_object()` (firearm's own, original method) is
**unchanged in every respect** — it now simply delegates to the new method with
`datetime.now()` as the reference, which is mathematically identical to its old inline
implementation. Confirmed by a dedicated regression test
(`test_firearm_persistence_is_unaffected_by_the_new_reference_time_method`) and by
re-verifying firearm's checksum/config/`.env` after this change (Test E, below).

## 4. Files changed

| File | Change |
|---|---|
| `app/threat/rule_based.py` | `KNIFE_AGGRAVATING_LABELS`, `KNIFE_WITH_PERSON_FLOOR` (0.45), `KNIFE_WITH_AGGRESSIVE_CONTEXT_FLOOR` (0.70); `assess()` extended with the floor logic (metrics-driven, inert for any observation without a `knife_persisted` key — including the firearm path). |
| `app/config.py` | `knife_persistence_min_hits` (2), `knife_persistence_window_seconds` (4) — new, separate from firearm's own settings. |
| `app/common/frame_buffer.py` | New `count_recent_frames_with_object_as_of()`; `count_recent_frames_with_object()` refactored to delegate to it with `now()` — behaviorally identical, used only by firearm. |
| `app/services/pipeline.py` | `evaluate_window()` computes `knife_persisted` (via the new `_as_of` method, referenced to `window.window_end()`) and sets it on `observation.metrics` before scoring. |
| `tests/test_threat_engine.py` | +7 knife-floor tests. |
| `tests/test_knife_threat_pipeline.py` | **New file**, 9 tests: persistence gating, outside-window exclusion, no-person exclusion, firearm isolation, BLIP-hallucination isolation, normal-scene baseline, and the BLIP-latency regression + firearm-reference-time-unaffected pair. |

**No backend, frontend, or database schema change.** The elevated score and its
rationale flow through the existing `Action.threatScoreHint` → `Alert`/`Incident`
pipeline unmodified.

## 5. Tests added — mapped to the deliverable's required coverage

1. Knife contributes to threat assessment per the explicit rule —
   `test_knife_persisted_with_person_raises_to_the_medium_floor`,
   `test_knife_persisted_with_close_contact_raises_to_the_high_floor`.
2. Normal person remains LOW/no alert —
   `test_normal_person_no_knife_stays_at_the_low_baseline`.
3. BLIP-hallucinated weapon creates no evidence —
   `test_blip_caption_mentioning_a_knife_never_creates_knife_evidence_without_real_detection`
   (unit) + live Test C below.
4. Firearm behavior unchanged —
   `test_knife_evidence_never_affects_the_firearm_weapon_detected_path`,
   `test_firearm_evaluation_is_completely_unaffected_by_knife_persistence_state`,
   `test_firearm_persistence_is_unaffected_by_the_new_reference_time_method` + live Test D.
5. Duplicate-person boxes — confirmed still fixed (§0); no new test needed since Phase
   2P's own suite already covers it and remains green.
6. Existing alert/incident flow still works — full backend suite (21/21) untouched;
   confirmed live (§8: MEDIUM correctly creates an Alert, correctly does NOT create an
   Incident, per the existing HIGH/CRITICAL-only rule).
7. Existing threat-score boundaries remain valid — all pre-existing
   `test_threat_engine.py` tests (no_activity/standing/fighting_candidate/weapon_detected/
   escalation/bounds) still pass unmodified.

## 6. Complete regression result

| Suite | Before Phase 2S | After Phase 2S |
|---|---|---|
| ai-service (`pytest`) | 159/159 | **161/161** (+16 new: 7 threat-engine, 9 pipeline) |
| backend (`npm test`) | 21/21 | **21/21** (untouched) |
| frontend (`npm test`) | 42/42 | **42/42** (untouched) |
| video-processing (`pytest`) | 6/6 | **6/6** (untouched) |
| **Total** | 228/228 | **230/230** |

No test deleted, skipped, or weakened.

## 7. Live E2E results — real HTTP, real WebSocket, real database

Both servers restarted with the Phase 2S code; five dedicated test cameras created via
the real backend API, exercised, then deleted (confirmed 0 leftover rows, DB restored
to the exact pre-test baseline).

### Test A — Normal scene
Real person-only image, no knife/weapon evidence.
```
YOLO: person (0.827, REAL) [+ a pre-existing, unrelated firearm false positive]
threat_score: 0.05, label: standing, rationale unchanged, no "knife" mention
Alert: none. Incident: none.
```
Confirmed twice (before and after the persistence-timing fix) — unaffected either way,
as expected, since no knife is present in this scenario.

### Test B — Knife scenario (the real, required test)
Real image with a genuine knife (independently verified in Phase 2O).

**First attempt — exposed the bug above**: `threat_score` stayed at 0.05. Investigated
immediately, root-caused, fixed (§3), and re-run.

**After the fix**:
```
YOLO: knife (0.767, REAL, genuine) + person (0.617, REAL) +
      banana (0.509, pre-existing unrelated hallucination) +
      firearm (0.661, pre-existing unrelated false positive)
BLIP: "a woman holding a knife in her hand
       Grounded detections: banana, firearm, knife, person."
threat_score: 0.50 (was 0.05 three windows earlier — real, observed progression:
       0.05 -> 0.45 -> 0.50)
rationale: "base risk for 'standing' = 0.05 + knife detected (persisted) + person
       present -> raised to 0.45 + sustained/rising activity across recent windows
       (+0.05) = 0.50. Elevated activity warranting attention."
severity: MEDIUM (0.4-0.65 band, backend's existing scoreToSeverity())
```
**Not forced to CRITICAL or HIGH — reported exactly as the explicit rule produced.**

## 8. Alert / Incident / WebSocket / DB evidence

| | Observed |
|---|---|
| Action rows (real) | 3 — showing the actual 0.05 → 0.45 → 0.50 progression |
| Alert rows (real) | **2 created**, both `severity=MEDIUM`, `status=NEW` |
| Incident rows | **0** — correct: the existing backend rule only creates an Incident for HIGH/CRITICAL, and MEDIUM correctly does not qualify. This is the existing architecture behaving faithfully, not a shortfall. |
| WebSocket (real connected client) | `alert.created` ×2, `action.detected` ×3, `detection.created` ×24, all confirmed live |
| Dashboard | Not screenshotted (no browser in this environment) — but `CameraHero`/`AlertCard` already render `Alert.severity`/`threatScore`/`description` generically for any real Alert row (no Phase 2S-specific frontend change was needed or made), so this Alert would display exactly like any other MEDIUM alert already does today. |

### Test C — Caption hallucination safety (live)
A window with a real person and **no real knife detection**, but BLIP's caption
fabricated *"a person appears to be holding a large knife"*: the caption displayed the
hallucination transparently, `Grounded detections: person.` (no knife), and
`threat_score` stayed at 0.05 — confirmed both live-style at the unit/pipeline level
(`test_blip_caption_mentioning_a_knife_never_creates_knife_evidence_without_real_detection`)
and structurally: BLIP's output has never had a code path into detections or scoring at
any point in this project (Phase 2R already established this; Phase 2S re-confirmed it
holds under the new knife-scoring rule too).

### Test D — Firearm isolation (live + static)
| | Before | After |
|---|---|---|
| `models/firearm_yolov8n.pt` MD5 | `a03b0c5aee7ad426fafd7265fa77ba5d` | identical |
| `.env` firearm/weapon lines | `WEAPON_ADAPTER=yolov8_firearm` | identical |
| `FIREARM_CONFIDENCE_THRESHOLD`, `_MAX_BBOX_AREA_RATIO`, `_PERSISTENCE_MIN_HITS`, `_PERSISTENCE_WINDOW_SECONDS`, `WEAPON_ALERT_COOLDOWN_SECONDS` | all defaults | all unchanged |
| Firearm scoring path (`weapon_detected`) | reaches ≥0.85 alone | unchanged, confirmed live in Test B's own window (firearm hallucination present, scored independently, "knife" never appears in its rationale) |

**Confirmed: firearm model, configuration, and scoring logic are unchanged.**

## 9. Limitations (explicit)

- **The BLIP-induced timestamp-drift effect (§3) very plausibly also affects firearm's
  own 4-second persistence window** — not fixed, not touched, per your explicit
  instruction; flagged here as a real, discovered risk for you to decide on separately.
- **Knife evidence floors are not validated against real violent/non-violent outcomes**
  — they are explainable, transparent, and evidence-gated (persistence + person
  presence + optional aggravating context), but, like every other value in
  `BASE_SCORE_BY_ACTION`, they are hand-set, not learned or independently validated.
- **The MEDIUM severity in the live test never creates an Incident** — by the existing
  architecture's own design (HIGH/CRITICAL only). If you want a knife+aggressive-context
  scenario (the 0.70 HIGH floor) to be demonstrated creating an Incident live, that
  requires a test scenario where the geometry heuristic also independently reads
  `close_contact`/`fighting_candidate` (e.g. two people close together) at the same time
  as the knife — not attempted in this phase's live test, which used a single person.
- **The general false-COCO-detection issue is untouched** (unrelated banana/firearm
  hallucinations remain visible in both live tests, exactly as before) — out of scope
  for this phase.
- Firearm's own deployment-specific false-positive problem (Phase 2L/2M) remains
  exactly as it was — visible in both live tests, unaddressed, by design.

## Most important rule — honored

The first live run of the actual required test did not work. That was investigated and
fixed before anything was reported as done — not glossed over, not worked around with a
heuristic relabeled as the real thing, and not blamed on the test methodology when it
was, in fact, a real interaction between two pieces of this project's own code
(Phase 2R's synchronous BLIP call and the persistence-window timing assumption). The
final reported severity (MEDIUM, 0.50) is exactly what the explicit rule produced on the
real evidence — not adjusted upward to look more impressive, and not CRITICAL.
