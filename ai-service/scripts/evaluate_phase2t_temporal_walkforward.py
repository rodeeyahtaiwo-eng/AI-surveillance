"""Phase 2T — honest walk-forward validation of the PRODUCTION MarkovTemporalPredictor
class (not a reimplementation, unlike Phase 2Q's one-off prototype script) against the
real historical Action data in database/dev.db.

Methodology (unchanged from Phase 2Q, now exercised through the actual adapter code):
for each real historical event, predict_next() is called BEFORE observe() records that
event -- so every prediction is made using only labels that occurred strictly before it.
No future data leaks in. Compared against the naive "predict next = current" baseline
on the exact same sequence.

Usage (from ai-service/, venv active):
    venv/Scripts/python scripts/evaluate_phase2t_temporal_walkforward.py
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ai-service/ root, for `app.*`

from app.temporal_prediction.markov_adapter import MarkovTemporalPredictor

DB_PATH = r"c:\Users\PC-TT\Documents\AIsurveillance\database\dev.db"
CAMERA_ID = "walkforward-eval"  # isolated from any real camera_id in the predictor's own state


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT label, windowStart FROM Action WHERE cameraId="
        "(SELECT cameraId FROM Action GROUP BY cameraId ORDER BY count(*) DESC LIMIT 1) "
        "ORDER BY windowStart"
    ).fetchall()
    conn.close()

    labels = [r[0] for r in rows]
    print(f"Real historical Action rows: {len(labels)}")
    print(f"Distinct labels observed: {sorted(set(labels))}\n")

    predictor = MarkovTemporalPredictor()
    correct = 0
    evaluated = 0
    matched_outcomes = 0
    mismatched_outcomes = 0
    no_judgment_outcomes = 0

    for label in labels:
        t = datetime.now(timezone.utc)
        prediction = predictor.predict_next(CAMERA_ID)  # BEFORE observing `label` -- no leakage
        if prediction.predicted_label is not None:
            evaluated += 1
            if prediction.predicted_label == label:
                correct += 1
        outcome = predictor.observe(CAMERA_ID, label, t)
        if outcome is not None:
            if outcome.matched is True:
                matched_outcomes += 1
            elif outcome.matched is False:
                mismatched_outcomes += 1
            else:
                no_judgment_outcomes += 1

    naive_correct = sum(1 for a, b in zip(labels, labels[1:]) if a == b)
    naive_total = len(labels) - 1

    print("=== Walk-forward accuracy (production MarkovTemporalPredictor, no leakage) ===")
    print(f"  {correct}/{evaluated} correct ({correct/evaluated:.0%}) where a prediction was possible "
          f"({len(labels) - evaluated} cold-start/no-successor-yet cases had no prediction to judge)")
    print(f"\n=== Naive 'predict next = current' baseline, same sequence ===")
    print(f"  {naive_correct}/{naive_total} correct ({naive_correct/naive_total:.0%})")

    print(f"\n=== Prediction -> outcome validation totals (via observe()'s return value) ===")
    print(f"  matched:      {matched_outcomes}")
    print(f"  mismatched:   {mismatched_outcomes}")
    print(f"  no judgment (prior prediction had no label): {no_judgment_outcomes}")
    total_judged = matched_outcomes + mismatched_outcomes
    if total_judged:
        print(f"  match rate where a judgment was possible: {matched_outcomes}/{total_judged} "
              f"({matched_outcomes/total_judged:.0%})")

    # --- Honest check of specific "meaningful" transitions, per the task instruction:
    # "do NOT invent transitions merely because they sound good" ---
    print("\n=== Do the specific 'escalation story' transitions actually appear in the data? ===")
    from collections import Counter, defaultdict
    transitions = defaultdict(Counter)
    for a, b in zip(labels, labels[1:]):
        transitions[a][b] += 1

    candidates = [
        ("walking", "approaching"),
        ("approaching", "close_contact"),
        ("close_contact", "fighting_candidate"),
    ]
    for src, dst in candidates:
        count = transitions.get(src, {}).get(dst, 0)
        total = sum(transitions.get(src, {}).values())
        pct = f"{count/total:.0%}" if total else "n/a"
        print(f"  {src} -> {dst}: {count}/{total} ({pct})")


if __name__ == "__main__":
    main()
