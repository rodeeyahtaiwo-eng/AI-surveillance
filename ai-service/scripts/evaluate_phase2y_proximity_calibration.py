"""Phase 2Y — offline, read-only proximity-calibration audit. Uses the REAL, already-
corrected (Phase 2X) app.action_recognition.demo_heuristic._proximity_and_speed()
against real historical detection data in database/dev.db. Does NOT modify any
production code, config, or threshold — this is purely an evaluation script, exactly
like scripts/evaluate_phase2l_firearm.py or evaluate_phase2t_temporal_walkforward.py.

Usage (from ai-service/, venv active):
    venv/Scripts/python scripts/evaluate_phase2y_proximity_calibration.py
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # ai-service/ root

from app.action_recognition.demo_heuristic import _deduplicate_boxes, _proximity_and_speed
from app.schemas import DetectionResult

DB_PATH = r"c:\Users\PC-TT\Documents\AIsurveillance\database\dev.db"
FRAME_W, FRAME_H = 640, 480  # this camera's real, consistently-observed resolution
CANDIDATES = [0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20, 0.25]


def det(row):
    box = json.loads(row["boundingBox"]) if isinstance(row["boundingBox"], str) else row["boundingBox"]
    return DetectionResult(object=row["objectLabel"], confidence=row["confidence"], bounding_box=box, mode="REAL")


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def containment(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / min(area_a, area_b) if min(area_a, area_b) > 0 else 0.0


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cam = conn.execute(
        "SELECT cameraId FROM Action GROUP BY cameraId ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()[0]

    labels_wanted = ["standing", "walking", "running", "approaching", "close_contact", "fighting_candidate"]
    rows = []
    for lbl in labels_wanted:
        sample = conn.execute(
            "SELECT id,label,threatScoreHint,description,windowStart FROM Action "
            "WHERE cameraId=? AND label=? ORDER BY windowStart",
            (cam, lbl),
        ).fetchall()
        n = len(sample)
        if n == 0:
            continue
        step = max(1, n // 6)
        rows.extend(dict(r) for r in sample[::step][:6])

    print(f"Sampled {len(rows)} representative real Action rows across {len(labels_wanted)} labels "
          f"(camera={cam}, evenly spaced across each label's full real history).\n")

    results = []
    for a in rows:
        ws = a["windowStart"]
        det_rows = conn.execute(
            "SELECT objectLabel,confidence,boundingBox,frameTimestamp FROM Detection "
            "WHERE cameraId=? AND frameTimestamp BETWEEN ? AND ?",
            (cam, ws - 6000, ws + 500),
        ).fetchall()
        frame_dets = {}
        for r in det_rows:
            frame_dets.setdefault(r["frameTimestamp"], []).append(det(r))
        win = [(ts(t), dd) for t, dd in sorted(frame_dets.items())]
        if not win:
            continue

        ratio, speed = _proximity_and_speed(win, FRAME_W, FRAME_H)

        cont = None
        last_people = []
        for _, dd in reversed(win):
            people = _deduplicate_boxes([d for d in dd if d.object == "person"])
            if len(people) >= 2:
                last_people = people
                break
        if len(last_people) >= 2:
            cont = containment(last_people[0].bounding_box, last_people[1].bounding_box)

        results.append({
            "old_label": a["label"], "old_score": a["threatScoreHint"], "caption": a["description"][:60],
            "new_ratio": ratio, "containment": cont, "speed": round(speed, 1),
        })

    conn.close()

    print(f"{'old_label':<20}{'old_score':<10}{'ratio':<9}{'contain':<9}{'speed':<8}{'caption'}")
    for r in results:
        ratio_str = f"{r['new_ratio']:.4f}" if r["new_ratio"] is not None else "n/a"
        contain_str = f"{r['containment']:.3f}" if r["containment"] is not None else "n/a"
        print(f"{r['old_label']:<20}{r['old_score']:<10}{ratio_str:<9}{contain_str:<9}{r['speed']:<8}{r['caption']}")

    print()
    print("=" * 110)
    print("THRESHOLD SWEEP -- would this window's real-geometry ratio count as 'close' at each candidate?")
    print("=" * 110)
    with_ratio = [r for r in results if r["new_ratio"] is not None]
    header = "old_label/score".ljust(24) + "".join(f"{c:<7}" for c in CANDIDATES)
    print(header)
    for r in with_ratio:
        row_str = f"{r['old_label']}/{r['old_score']}".ljust(24)
        for c in CANDIDATES:
            row_str += ("YES".ljust(7) if r["new_ratio"] < c else "no".ljust(7))
        print(row_str)


if __name__ == "__main__":
    main()
