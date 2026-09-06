# Phase 2N — Offline Firearm-Model Benchmark: Inspection Only

**Status: inspection only. Nothing downloaded except small annotation/metadata files and
one ~550KB sample video (see §3). No production defaults, thresholds, geometry filter,
or detector changed. No training, fine-tuning, or dataset merging performed.**

## 1. Existing firearm model — inspected directly from the loaded weights

| Property | Value | How verified |
|---|---|---|
| Architecture | YOLOv8n (`ultralytics.nn.tasks.DetectionModel`) | `YOLO(...).model` introspection |
| Parameters | 3,011,043 (225 layers, 8.2 GFLOPs) | `model.info()` |
| Weights file | `models/firearm_yolov8n.pt`, 6,238,307 bytes | matches `models/README.md` |
| Input size | 640×640 | `model.overrides["imgsz"]` and `ckpt["train_args"]["imgsz"]` |
| Class mapping | `{0: "Gun"}` — single class | `model.names` |
| Confidence threshold (production) | 0.5 | `app/config.py: firearm_confidence_threshold` |
| Geometry filter (production, Phase 2K) | reject boxes >90% of frame area | `app/config.py: firearm_max_bbox_area_ratio` |
| Persistence / cooldown (production, Phase 2J) | K=2 hits / 4s window; 15s alert cooldown | unchanged |

**New provenance detail, extracted from the checkpoint's embedded training metadata**
(`ckpt["train_args"]`, `ckpt["train_metrics"]` — not previously documented in this
project): trained on Kaggle (`/kaggle/working/shuffled_dataset/data.yaml`), 100 epochs,
batch 16, imgsz 640, starting from COCO-pretrained `yolov8n.pt` (`pretrained=True`),
ultralytics version 8.3.204, checkpoint dated 2025-10-03. Final training-run metrics:
precision 0.867, recall 0.817, mAP50 0.890, mAP50-95 0.603 — consistent with the model
card's published 89.0%/60.2% mAP figures (already documented in `models/README.md`),
confirming this checkpoint matches its documentation.

**Offline evaluability: confirmed, already in continuous use.** `ultralytics.YOLO(path)`
loads and runs standalone via `.predict()` with zero dependency on the FastAPI service,
video-processing pipeline, or backend — exactly the method every Phase 2K/2L/2M
evaluation script has already used. No production code needs to run for any offline
benchmark in this phase.

## 2. CCTV-Gun (github.com/srikarym/CCTV-Gun)

**This is not a self-hosted image dataset — it is a benchmark-construction repo.** It
provides only annotations (already obtained, see below); the actual images must be
downloaded separately from three original sources it references. Repo itself:
Apache-2.0, 33,895 KB (code + annotations only, verified via GitHub API).

### Annotations (fully obtained — 8.7MB total, MS-COCO format)

| Source | Images | Annotations | Resolution (uniform) | Images WITH a gun | Images with NO gun (true negatives) |
|---|---|---|---|---|---|
| MGD (Monash Gun Dataset) | 2,852 | 6,656 | 512×512 | 2,852 (100%) | **0** |
| USRT (US Real-time Gun Detection) | 3,294 | 8,029 | 1920×1080 | 1,115 (34%) | **2,179 (66%)** |
| UCF (UCF-Crime frames) | 1,597 | 5,719 | 320×240 | 1,597 (100%) | **0** |

Categories in every annotation file: `{1: person, 2: handgun}`. Bounding boxes are
standard COCO `[x, y, w, h]` — a direct, well-understood conversion to YOLO's normalized
`cx, cy, w, h` format, no research needed. UCF's annotations additionally carry a
`pair_id`/`pair_bbox` field linking each handgun box to the person holding it.

**True-negative finding**: USRT is the one source with a substantial true-negative
pool — 2,179 images confirmed person-present, no-handgun. MGD and UCF, as curated for
this specific benchmark, are 100% positive (every image was pre-selected to contain a
gun) — they offer no true negatives on their own.

### Actual image availability — checked, not assumed

| Source | Link in `dataset_instructions.md` | Status (checked directly) |
|---|---|---|
| MGD | Google Drive file | **404 Not Found — dead link** |
| USRT | University of Seville SharePoint | **401 Unauthorized — requires institutional credentials we don't have** |
| UCF | Dropbox shared folder (`Anomaly-Videos-Part-3.zip`) | Reachable (302 to a live folder), but this is the full UCF-Crime anomaly-video collection — publicly documented (Sultani et al. 2018) as tens of GB across its parts, to extract roughly 1,600 needed frames. Exact current size could not be read from Dropbox's page (JavaScript-rendered, no size metadata exposed to a plain fetch). |

**Conclusion: none of CCTV-Gun's three image sources are practically obtainable right
now.** Two links are simply broken/gated; the third would require a large, disproportionate
download relative to the small number of frames actually needed, and I did not attempt
it given the disk-space constraint you raised. The annotation-only evidence above (counts,
resolutions, class balance, true-negative counts) is real and fully usable for planning,
but no CCTV-Gun pixel data can be benchmarked against without either you obtaining MGD/USRT
through another channel, or an explicit decision to pull the large UCF archive.

**License caveat**: the CCTV-Gun repo's Apache-2.0 license covers its own code; MGD,
USRT, and UCF each carry their own original dataset licenses, none of which are
restated in this repo. These were not independently verified here (their source links
are currently inaccessible), so must be treated as unconfirmed pending direct access.

## 3. Mendeley firearm action-recognition dataset (bbzpxhd22j, v2)

**Confirmed exact size: 2,248,654,752 bytes (2.25 GB / 2.09 GiB), one file:
`Gun_Action_Recognition_Dataset.zip`.** License: **CC BY-NC 3.0**, with the dataset's
own description explicitly permitting commercial use "if prior permission is obtained"
— compatible with this academic/non-commercial project as-is.

**Inspected without downloading the archive** — via HTTP range requests against its
S3-hosted zip (which supports `Accept-Ranges: bytes`), reading only the central
directory (a zip's internal file listing) plus one ~550KB sample video and its label
file. Total data actually transferred for this inspection: well under 1MB.

| Category | Video subfolders | `video.mp4` files | Uncompressed size | `label.json` files |
|---|---|---|---|---|
| Handgun | 142 | 141 | 875.5 MB | 140 |
| Machine_Gun | 140 | 139 | 709.3 MB | 139 |
| No_Gun | 119 | 118 | 666.6 MB | **0** |

(One Handgun subfolder's video/label count is off by one, and totals include a few
empty directory entries — noted, not investigated further at this stage.)

**Sample video verified directly** (`Handgun/PCH1_C1_P4_V1_HB_2/video.mp4`, 561,893
bytes): opens cleanly with OpenCV, 640×480 @ 25fps, 125 frames (5s) — **matching this
project's own webcam capture resolution**, unlike the Phase 2M external Roboflow images
(416×416 studio crops). This is a meaningfully better resolution match for eventual
deployment-relevant evaluation, if pursued.

**Annotation format, confirmed from two real samples** (one Handgun, one Machine_Gun
video): each video has its own COCO-style `label.json` — `info`/`licenses`/`categories`/
`images`/`annotations`, one `images` entry per video *frame* (not per separate file —
`file_name` is literally `"video.mp4"` repeated per frame id), one category matching the
folder name (`Handgun` or `Machine_Gun`), bounding boxes in standard COCO `[x, y, w, h]`.
**Not every frame has an annotation** — the Machine_Gun sample had 175 frame entries but
only 85 annotations, meaning the gun is not visible in every frame of a "positive" video
(consistent with this being an action-recognition dataset, not a static-image one).

**Convertibility to our YOLO detector's format**: straightforward in principle (COCO
bbox → YOLO normalized xywh, same as CCTV-Gun), but requires an extra step CCTV-Gun
doesn't: **frame extraction from video** at each annotated frame id before any
image-based conversion, since there are no standalone image files. A well-understood,
standard preprocessing step — not attempted in this inspection-only phase.

**True-negative findings — two distinct sources here**:
1. The `No_Gun` category: 118 videos, confirmed no-gun by category design, but **zero
   annotation files at all** (not just empty ones) — usable as whole-video-level true
   negatives once frames are extracted, with no bounding-box work needed since there is
   nothing to box.
2. Un-annotated frames *within* Handgun/Machine_Gun videos (the 175-vs-85 gap above) —
   frame-level true negatives inside otherwise-positive videos. Usable, but requires
   care: a frame here is negative only until the gun (re)appears later in the same clip,
   so this needs per-frame cross-referencing against the annotation list, not a blanket
   per-video label.

Both are two classes our current model doesn't distinguish (Handgun vs. Machine_Gun) —
irrelevant to a single-class "Gun" detector; both would map to the same positive label.

## 4. Storage requirements — reported before any large download, as requested

| Source | Size | Downloaded this phase? |
|---|---|---|
| CCTV-Gun annotations (all 3 sources) | ~8.7 MB | **Yes** — small, already obtained |
| CCTV-Gun images — MGD | unknown (link dead) | No |
| CCTV-Gun images — USRT | unknown (link gated) | No |
| CCTV-Gun images — UCF | unknown, implied large (multi-GB video archive) | No |
| Mendeley `Gun_Action_Recognition_Dataset.zip` | **2.25 GB exact** | **No** — inspected via range requests only (<1MB transferred) |

**No large download has been performed.** The only files saved to disk this phase are
the ~8.7MB of CCTV-Gun annotation JSON and one ~550KB Mendeley sample video+label,
kept in scratch space for this inspection — not added to the project's tracked
datasets. Downloading the full 2.25GB Mendeley archive, or any of CCTV-Gun's image
sources (if you can get past the dead/gated links), is a decision for you to make
explicitly — I have not done either.

## 5. Dataset separation (per your instruction — kept apart, not merged)

- CCTV-Gun and Mendeley are reported entirely separately above and would be evaluated
  separately if pursued — different sources, different annotation schemes (static-image
  COCO vs. per-video COCO), different licenses, different resolution profiles.
- Neither is combined with Phase 2K/2L/2M evidence (the 45 known false positives, the
  205-frame unbiased sample, the 17+6 external/replica positives, the 10 curated hard
  negatives) — those remain a separate, distinct evaluation lineage.

## 6. What this phase does NOT claim

No accuracy, precision, recall, or suitability claim is made about either dataset or
about the detector against them — no detector inference was run against any CCTV-Gun or
Mendeley image/frame in this phase. This is a structural and logistical inspection only.

## Recommended next step (pending your decision — no action taken)

1. **Mendeley (2.25GB)**: size and structure are now fully known. If you want to
   proceed, the next step would be downloading the archive, extracting a modest,
   explicitly-labeled subset (mirroring Phase 2M's manifest convention) — likely
   prioritizing `No_Gun` for true negatives and a handful of `Handgun` clips for
   positives, rather than all 2.25GB — and keeping it as its own separate evaluation
   lineage per your instruction.
2. **CCTV-Gun**: MGD and USRT need a working access path from you (an alternate MGD
   mirror, or USRT SharePoint credentials) before any image evaluation is possible;
   UCF's frame subset is technically reachable but disproportionately expensive to pull
   for ~1,600 frames — worth reconsidering only if the other two remain inaccessible.
3. Neither should proceed without your explicit go-ahead, consistent with this phase's
   inspection-only scope.
