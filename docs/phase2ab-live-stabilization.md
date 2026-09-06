# Phase 2AB — Emergency Live-System Stabilization

> **REVERTED.** Following this phase, the user determined the live demo behavior was
> worse than the pre-Phase-2W (Phase 2V) baseline and requested a full rollback to that
> state. All of this phase's changes — BLIP background-threading, generation
> repetition controls, the structured-sentence-as-primary-caption format, and the
> three-tier knife floor (0.35/0.65/0.70) — were reverted. The active runtime is back to
> Phase 2V's synchronous BLIP captioner and the original two-tier knife floor
> (0.45/0.70). This document is kept as the historical record of what was tried and why
> it was undone, not as a description of current behavior.

**Status: implemented, tested (229/229 passing).** Targeted fixes only — no
architecture change, no new model, firearm remains removed, Phase 2T/2X untouched.

## Measured bottleneck (real numbers, this CPU)

| Stage | Measured latency |
|---|---|
| YOLO general detection | **~80ms** |
| BLIP caption generation | **~1.8–2.2s** (was fully synchronous, blocking the whole `evaluate_window()` call) |

BLIP was ~25x slower than YOLO and, before this phase, sat directly in the critical
path of every Action row (label + threat_score + description) reaching the backend —
not just the caption text.

## Changes made

1. **`app/captioning/blip_adapter.py`** — `caption()` no longer blocks: real generation
   now runs in a background thread (with an in-flight guard per camera, race-safe under
   a lock). The calling thread always returns immediately with the cached/previous text
   (or the existing "pending" placeholder on a cold camera) — the fresh text becomes
   available to the *next* call, exactly like the existing cooldown-cache already did.
   `evaluate_window()`'s own latency for label/threat_score/persistence is no longer
   coupled to BLIP's cost at all.
2. Added `no_repeat_ngram_size=3` and `repetition_penalty=1.3` to `generate()` — the
   real, measured cause of "self self self self" (greedy decoding with zero repetition
   control). A small defensive regex (`_collapse_degenerate_repetition`) collapses any
   3+ identical-word run as a safety net; it never touches a 2x repeat.
3. **`app/captioning/template_adapter.py`** — extracted the existing, already-tested
   activity-centric sentence builder into `build_structured_sentence()`, reused by both
   captioners.
4. **`app/captioning/blip_adapter.py`** — `caption()`'s primary text is now the
   structured sentence (real detections + real action label, no model call); BLIP's
   own text (fresh or cached) is demoted to a trailing "Visual context: ..." clause. It
   can never override or precede the structured signal.
5. **`app/services/pipeline.py`** — added a raw `knife_detected` metric (current
   window only, not gated by persistence) alongside the existing `knife_persisted`.
6. **`app/threat/rule_based.py`** — three knife tiers (see arithmetic below), still
   gated on a person being present, still a MAX/floor operation, persistence mechanism
   (K=2/4s) unchanged:
   - Unconfirmed (`knife_detected` only): floor **0.35** (new).
   - Confirmed (`knife_persisted`): floor **0.65**, was 0.45.
   - Confirmed + aggravated context: floor **0.70**, unchanged — can still stack toward
     CRITICAL via the engine's existing, untouched proximity/movement/escalation bonuses.

## Not touched

`CLOSE_PROXIMITY_RATIO`, Phase 2X geometry, Phase 2T, firearm (remains removed),
general YOLO model/threshold/classes, `sequence_window_seconds`, frontend, WebSocket.

## Remaining limitations

- General-detector recall on certain real knife presentations is unchanged (a
  pre-existing, separately-tracked limitation) — the unconfirmed floor (0.35) exists
  precisely because raw detection alone isn't fully reliable.
- Reaching CRITICAL still requires the same real-world proximity Phase 2X/2Y already
  found is rare in this camera's footage — the knife recalibration raises the *floor*,
  not the ceiling mechanics.
