# Phase 2M — Controlled Positive Evidence

> **Superseded (Phase 2V)**: firearm detection has since been removed from the active
> runtime entirely — see [`phase2v-firearm-removal.md`](phase2v-firearm-removal.md).
> This document is kept as the historical evaluation record.

**Status: evaluation only. Detector, confidence threshold (0.5), and Phase 2K geometry
filter (0.9) unmodified. No production defaults changed.** This phase obtains the
confirmed-positive evidence Phase 2L identified as completely missing, and asks whether
the existing detector shows any useful separation between firearm-present and
firearm-absent images. Reproducible via
`ai-service/scripts/evaluate_phase2m_firearm.py`; dataset and manifest in
`ai-service/datasets/firearm_evaluation_v1/`; raw results in
`ai-service/datasets/phase2m_firearm_eval_results.json`.

## Phase 2L format, as inspected (done before collecting anything)

`evaluate_phase2l_firearm.py` had no positive-label support at all — both its evidence
sources hardcoded `firearm_present: False`. The project's own established convention
for labeled evidence is `datasets/webcam_validation_v1/manifest.json` (Phase 2I): a list
of per-item records with an `intended_class` written **before** any model run, plus
free-text condition notes. Phase 2M extends that exact convention —
`datasets/firearm_evaluation_v1/manifest.json` — rather than inventing a new format.

## Positive-evidence sourcing decision

I cannot capture images myself (no camera/physical access). Given the safety
constraint, the user chose **both** available paths:

1. **You capture a replica/prop** in your own webcam setting (pending — see
   "What's still pending" below).
2. **A public, appropriately-licensed real-firearm dataset**, sourced and vetted before
   import.

## 1. Positive evidence source and count

**Source**: the [Pistols dataset](https://universe.roboflow.com/joseph-nelson/pistols)
on Roboflow's public dataset library — real photographs originally collected by the
University of Granada's SCI2S research group
([sci2s.ugr.es/weapons-detection](https://sci2s.ugr.es/weapons-detection)), re-hosted by
Roboflow under a stated **CC0 / Public Domain** license (verified by fetching the
dataset page directly). This is a different, independently-sourced dataset from the one
used to train `firearm_yolov8n.pt` (that model's own card cites Roboflow+Kaggle+"curated"
sources with no reproducible link — see Phase 2L) — using a different source avoids any
train/test leakage concern entirely, though it also means these are not guaranteed
representative of the exact training distribution.

20 images were downloaded (416×416, the dataset's own resize version) and **every one
visually inspected before labeling**, per the "do not label ambiguous images as either
class" instruction. **3 were excluded**:
- Two were stylized/cartoon graphics (a cartoon-illustration character holding a toy gun,
  and a yellow line-art silhouette drawing) — not photographic firearm evidence.
- One (two people at a shooting range) had the firearm shape too small/unresolved in the
  frame to confirm visibility with confidence.

**17 confirmed positive images used**, with real variation across the requested
dimensions: distance (close/medium/far), location in frame, orientation (side profile,
three-quarter, aimed toward/away from camera), partial visibility (foreshortened,
occluded by the shooter's own body, obscured by muzzle flash/motion blur), and
lighting/background (studio white, indoor range, outdoor desert, outdoor dusk/forest).

**Licensing caveat, stated plainly**: 2 of the 17 (`ext_pos_08`, `ext_pos_19`) are
watermarked stock photos (Dreamstime, "Cheaper Than Dirt") that the original academic
dataset collected by web-mining — the re-hosting is CC0, but the underlying stock
photo's own copyright status was never independently re-cleared by that process. They
are used here only for internal, non-commercial evaluation, not redistribution.

## 2. Negative evidence source and count

**10 curated hard negatives**, all reused from the already-visually-confirmed Phase
2K/2L evidence (real webcam captures from this project's own camera/room — not new
images), one to two per requested hard-negative category:

| Category | Count |
|---|---|
| Empty hands (open palms, no object) | 1 |
| Hand near face/ear | 2 |
| Dark hair/hair-wrap silhouette | 2 |
| Holding a phone | 2 |
| Holding a bottle | 1 |
| Ordinary portrait composition | 1 |
| Close-range face/shoulders | 1 |

These are deliberately the *hardest* known negatives, not a random negative sample —
appropriate for testing separation at the margin, not for estimating a general
false-positive rate (Phase 2L's 250-frame sets remain the reference for that).

## 3. Detector results (unmodified: conf≥0.5, no geometry filter)

| | Detected as "Gun" | Rate |
|---|---|---|
| Positives (n=17) | 11/17 | 65% |
| Negatives (n=10) | 10/10 | 100% |

**The model does detect real firearms** — this is new information Phase 2L could not
provide. But that 65% figure is misleading taken alone: broken down by photo type —

| Positive subset | Detected |
|---|---|
| Studio/product photos (gun isolated, plain background, n=8) | **8/8 (100%)** |
| Scene-realistic photos (person, real background, distance/angle/motion, n=9) | **3/9 (33%)**|

The 6 undetected scene-realistic images are exactly the surveillance-relevant
conditions: far/foreshortened (2), viewed from behind at a shooting range (2),
motion-blurred with muzzle flash (1), and held near the face at an angle (1). **These
were not detected at any confidence** — the model produced no candidate box for the
firearm at all, at the current floor threshold of 0.5. No threshold adjustment can
recover a detection that was never candidate-generated in the first place.

## 4. Threshold analysis

| Threshold | TP | FN | FP | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| 0.50 (current) | 11 | 6 | 10 | 0 | 0.52 | 0.65 |
| 0.60 | 11 | 6 | 4 | 6 | 0.73 | 0.65 |
| 0.65 | 11 | 6 | 3 | 7 | 0.79 | 0.65 |
| 0.70 | 11 | 6 | 2 | 8 | 0.85 | 0.65 |
| 0.75 | 11 | 6 | 1 | 9 | 0.92 | 0.65 |
| **0.80** | **11** | **6** | **0** | **10** | **1.00** | **0.65** |
| 0.85 | 6 | 11 | 0 | 10 | 1.00 | 0.35 |
| 0.90 | 3 | 14 | 0 | 10 | 1.00 | 0.18 |

**Finding, stated directly**: at 0.80, all 10 curated hard negatives are correctly
rejected (0 false positives) while every positive that was ever detected at all (11/17)
is preserved. This is a materially different, more encouraging picture than Phase
2K/2L's threshold analysis could support — those phases only had one historical,
non-reproducible confidence-only positive reference (0.83) with no image or bounding
box, so no threshold experiment could be checked against it. **Recall does not fall
until 0.85**, where it drops sharply to 0.35 as several of the real (non-studio)
positives (0.80–0.84 confidence) get excluded. **0.80 sits right at the edge** — one
confidence point higher and genuine recall on this sample collapses.

## 5. Geometry analysis (current production filter, ratio≤0.9)

| | TP | FN | FP | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| Geometry only | 9 | 8 | 9 | 1 | 0.50 | 0.53 |

**This directly confirms a risk Phase 2K/2L could only flag as hypothetical.** The
geometry filter rejects 2 of the 17 positives — `ext_pos_02` and `ext_pos_09`, both
close-up studio product photos where the pistol fills 98–99% of the frame — for the
exact same reason it correctly rejects near-whole-frame false positives: a box that
large looks geometrically implausible regardless of what's actually in it. Phase 2K
wrote *"could, in principle, reject a genuine detection framed to fill nearly the entire
camera view... unvalidated either way, no such case on record"* — **that case is now on
record.** The geometry filter is not free; it trades away some genuine close-range
detections for its false-positive reduction, exactly as a pure-geometry heuristic
would be expected to.

## 6. Combined-filter analysis

| Threshold | TP | FN | FP | TN | Precision | Recall |
|---|---|---|---|---|---|---|
| 0.50 + geometry | 9 | 8 | 9 | 1 | 0.50 | 0.53 |
| 0.60 + geometry | 9 | 8 | 3 | 7 | 0.75 | 0.53 |
| 0.65 + geometry | 9 | 8 | 2 | 8 | 0.82 | 0.53 |
| 0.70 + geometry | 9 | 8 | 2 | 8 | 0.82 | 0.53 |
| 0.75 + geometry | 9 | 8 | 1 | 9 | 0.90 | 0.53 |
| **0.80 + geometry** | **9** | **8** | **0** | **10** | **1.00** | **0.53** |
| 0.85 + geometry | 4 | 13 | 0 | 10 | 1.00 | 0.24 |

Adding geometry on top of threshold 0.80 costs 2 more true positives (recall 0.65→0.53)
for no additional precision gain at that threshold (both already reach 0 FP at 0.80
alone). **On this evidence, geometry filtering adds no benefit once the confidence
threshold is already at 0.80** — its value (Phase 2K/2L) was in catching false
positives that stayed at lower confidence; at 0.80, confidence alone already screens
those out on this sample, and geometry only continues to remove genuine detections.

## 7. Confusion matrix / precision / recall — justification and limits

Computed above because the label set is explicit and the sample (n=27), while small, is
large enough to produce a non-degenerate confusion matrix at every threshold tested. **These
numbers must not be read as general accuracy figures**:
- n=17 positive / n=10 negative is small; one or two images shifting category would
  move precision/recall substantially.
- The negative set is deliberately adversarial (hardest known cases), inflating the
  apparent false-positive problem at low thresholds relative to "ordinary" footage —
  compare to Phase 2L's 26.3% unbiased-sample rate, which this 100%-at-0.50 figure is
  not meant to replace.
- The positive set is majority studio/product photography (8/17), not webcam
  surveillance style — inflating apparent recall relative to realistic deployment
  conditions, as the studio-vs-scene breakdown in §3 shows directly.
- Two positive images carry uncleared underlying stock-photo copyright (§1).

## 8. Small-positive-sample limitations (explicit)

- 17 positives, sourced entirely from one external, non-deployment dataset — no
  positive evidence from this project's own camera/room/lighting exists yet (pending
  replica capture, see below).
- No repeated positive of the *same* firearm under controlled, systematically varied
  conditions (the manifest varies condition informally across 17 *different* firearms/
  photos, not one firearm varied methodically) — Phase 2M establishes coarse signal,
  not a controlled ablation.
- The most deployment-relevant subset (scene-realistic, n=9) is itself small; 3/9
  detected is not a statistically stable estimate.

## 9. Whether the detector shows meaningful positive/negative separation

**Partially, and only in the least deployment-relevant condition.** There is a real,
non-degenerate confidence region (≈0.75–0.80) where this specific positive and negative
sample separate cleanly (precision reaches 1.00 while retaining every positive the
model ever fired on). That is genuine signal — the model has learned *something*
correctly, on close, clearly-composed views of a firearm. But:
- That separation is carried entirely by studio/product-style photos (100% detected)
  and largely absent on scene-realistic photos (33% detected, and 6 of 9 with **zero**
  candidate detection at any confidence).
- The geometry filter, while effective against Phase 2K/2L's false positives, measurably
  costs recall on exactly the kind of close-range genuine detection most likely in a
  confined indoor camera setting.

**Do not read this as "the detector works."** It reads as: the detector has some real
firearm-recognition capability, gated almost entirely to conditions unlike typical
surveillance footage (distance, awkward angle, partial occlusion, motion), and even
there its separation from this project's specific hard negatives is not free of
trade-offs.

## 10. Whether it is suitable for this project

**Not established as suitable, with more precision than Phase 2L could offer.** The
detector is not simply "randomly guessing" — Phase 2M rules that out. But its
demonstrated capability is concentrated in close-up, well-composed, well-lit
photography, and it shows a **complete detection failure (0/9 candidate boxes) on every
scene-realistic condition tested except three**, which is close to the opposite of what
a webcam/CCTV deployment needs (a firearm is far more likely to appear at a distance,
at an angle, or partially obstructed than centered and isolated).

## Recommended next engineering step

**Do not adopt any threshold or filter change on this evidence alone.** Three next
steps, in order of priority:

1. **Complete the pending replica capture** (still outstanding — see below). This is the
   single highest-value addition: it would test the model against gun-shaped objects in
   *this project's actual deployment conditions* (same camera, same room, same lighting
   as the 250 Phase 2L negatives), closing the biggest remaining gap in this report.
2. **If replica evidence confirms the same scene-realistic failure pattern**, this
   detector should be treated as **not suitable for safety-critical firearm alerting in
   this deployment as-is** — recommend downgrading its role to a secondary/advisory
   signal at most, and reviewing whether `docs/ai-pipeline.md` and `models/README.md`'s
   existing "unvalidated, not safety-critical" language needs to state this failure mode
   explicitly (a firearm at typical camera distance may simply not be detected at all).
3. **Fine-tuning or a different detector should only be considered after** step 1 —
   there is no evidence yet on whether a different single-class YOLO checkpoint would
   behave differently on the same scene-realistic conditions, and training a new model
   without first confirming *why* this one fails (resolution? scale? occlusion
   robustness? training-data composition bias toward studio photography?) risks
   repeating the same gap.

## What's still pending — UPDATE: replica capture inspected, mostly not fulfilled

8 files were added to `positive_replica/`. **Every one was visually inspected before
labeling anything.** Result: **only 1 of the 8 is an actual deployment-style capture**;
the other 7 are downloaded stock/internet images, not webcam self-captures of a
physical prop.

| File | Resolution | What it shows | Disposition |
|---|---|---|---|
| `images (3).jpg` | **640×480** (matches this project's webcam captures exactly) | Small toy/model gun (scope, short barrel, stock — action-figure scale), lying on a crumpled paper towel, informal/amateur framing | **`REPLICA_POSITIVE`** — the one genuine replica-evidence entry |
| `gettyimages-148351048-170667a.jpg` | 508×339 | Real photo, hand with pistol at waistband (Getty Images credit visible in-frame) | `REAL_FIREARM_POSITIVE`, external, unverified license |
| `images (1).jpg` | 464×431 | Real photo, tactical rifle+scope+bipod, studio white background | `REAL_FIREARM_POSITIVE`, external, unverified license |
| `images (2).jpg` | 739×415 | Real photo, pistol + tactical flashlight on carpet, dramatic lighting | `REAL_FIREARM_POSITIVE`, external, unverified license |
| `images.jpg` | 474×249 | Real photo, pistol with loose ammunition on a woven mat | `REAL_FIREARM_POSITIVE`, external, unverified license |
| `set-black-pistol-glock-17-260nw-2603013437.webp` | 1126×280 | Stock studio photo **set** — 4 angles of a Glock-17-style pistol composited into one image | `REAL_FIREARM_POSITIVE`, external, unverified license |
| `futuristic-sci-fi-metal-rifle-...-2BX7P23.jpg` | 1218×1390 | 3D-rendered **fictional** sci-fi weapon (Alamy watermark) | **Excluded** — synthetic/fictional, not a real or replica firearm |
| `gun-pistol-closeup-3d-rendering-...-PGNNNJ.jpg` | 1300×956 | 3D-rendered generic pistol (Alamy watermark) | **Excluded** — synthetic render, not a real or replica firearm |

The 640×480 resolution match plus the informal, non-studio composition is the basis for
treating `images (3).jpg` as the genuine capture; this is inferred, not independently
confirmed. **Even accepting it as genuine, it is a single image — none of the requested
variation (distance, angle, position, occlusion, lighting) was actually captured.**

### Results

`replica_01` (the one genuine replica image): **detected**, confidence **0.839**,
bounding box `[64.9, 303.7, 398.7, 447.9]`, area ratio **0.157** (well within the
geometry filter's 0.9 limit — passes). At the candidate threshold of 0.80, this single
detection survives both alone and combined with geometry.

The 5 new `REAL_FIREARM_POSITIVE` external images: 4/5 detected (`ext2_real_01`
0.819, `ext2_real_02` 0.787, `ext2_real_03` 0.804, `ext2_real_04` 0.923); the 4-angle
composite (`ext2_real_05`) produced **no detection at all** — a clearly unambiguous real
firearm image, missed entirely, joining the same "no candidate box produced" failure
mode already documented for scene-realistic photos.

**Recomputed real-firearm-only confusion matrix (n=22: the original 17 + these 5;
replica excluded)** — this replaces the earlier blended numbers, which incorrectly
folded the replica result into "positive":

| Threshold | TP | FN | FP | TN | Precision | Recall | +geometry TP/FN/FP/TN | +geometry P/R |
|---|---|---|---|---|---|---|---|---|
| 0.50 | 15 | 7 | 10 | 0 | 0.60 | 0.68 | 13/9/9/1 | 0.59/0.59 |
| 0.65 | 15 | 7 | 3 | 7 | 0.83 | 0.68 | 13/9/2/8 | 0.87/0.59 |
| **0.80** | **14** | **8** | **0** | **10** | **1.00** | **0.64** | 12/10/0/10 | 1.00/0.55 |
| 0.85 | 7 | 15 | 0 | 10 | 1.00 | 0.32 | 5/17/0/10 | 1.00/0.23 |

Broadly the same shape as the 17-image version — threshold 0.80 still reaches perfect
precision at ~0.64 recall on real-firearm evidence.

### Does the detector perform differently on deployment-style vs external images?

**The single replica data point is, on its own terms, a stronger result than most of the
external "scene-realistic" real-firearm photos** — detected confidently (0.839) with a
small, plausible bounding box, despite being an informal, low-quality snapshot. But this
must be read very cautiously, and **is not reported as evidence about real-firearm
detection**:
- n=1 — no statistical weight at all.
- A small dark object with an irregular silhouette on a plain light background is
  *exactly* the pattern already implicated in this detector's known false-positive bias
  (Phase 2K/2L's "no held object" and phone/bottle hard negatives share this same
  geometry). This detection cannot be distinguished, on one sample, from "the detector
  fired on a small dark shape again" versus "the detector recognized a gun silhouette."
- It says nothing about real firearms specifically — that is precisely why it is kept in
  its own `REPLICA_POSITIVE` category, never merged into the real-firearm confusion
  matrix above.

### Limitations of using replica images as evidence (explicit)

1. Only 1 of 8 provided files was assessed as an actual replica capture — the requested
   distance/angle/position/occlusion/lighting variation was not achieved (n=1, no
   variation at all).
2. A replica, even if perfectly detected every time, does not validate detection of a
   real firearm — different material, reflectance, and (in this case) very different
   scale (toy/action-figure sized) from an actual handgun.
3. The one result obtained is confounded with this detector's already-documented bias
   toward flagging small dark objects on plain backgrounds — it cannot be attributed to
   genuine firearm-shape recognition from a single sample.
4. 5 of the remaining 7 files, while usable as *additional* external real-firearm
   evidence, carry the same unverified stock-photo licensing caveat already flagged for
   2 images in the original Phase 2M set — now 7 of 27 external positives total have
   uncleared underlying copyright, used here for internal evaluation only.
5. The core question this replica request was meant to answer — does the detector
   recognize a gun-shaped object in *this project's own camera, room, and lighting* —
   remains almost entirely open. One low-quality, single-angle snapshot is not
   sufficient to answer it either way.

### What's still pending

Genuine multi-shot replica/prop capture, varied across distance/angle/position/
occlusion/lighting, taken with this project's own webcam — not yet obtained. The
`positive_replica/` folder and manifest schema are ready to receive it; re-running
`evaluate_phase2m_firearm.py` requires no code change.
