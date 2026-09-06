# Model Weights

This folder holds downloaded/trained model weights used by `ai-service`. Most of it is
git-ignored (see root `.gitignore`: `*.pt`/`*.onnx`/`*.pth`/`*.bin`, `models/weights/`)
because weight files are large binaries that don't belong in version control — with one
deliberate exception, `violence_head.json`, noted below.

## Expected contents (populated as each AI phase is built)

| File | Model | Source | Used by |
|---|---|---|---|
| `yolov8n.pt` | YOLOv8n (COCO-pretrained) | Auto-downloaded by `ultralytics` on first run, or place manually here | `ai-service/app/detection/yolov8_adapter.py` |
| `firearm_yolov8n.pt` | YOLOv8n fine-tuned for firearm detection | Manual download (not auto-fetched) — see below | **Not used by the active runtime** — firearm detection was removed in Phase 2V (see `docs/phase2v-firearm-removal.md`). Retained only because `ai-service/scripts/evaluate_phase2l_firearm.py` and `evaluate_phase2m_firearm.py` still reference it directly as a historical evaluation artifact. |
| `violence_head.json` | Logistic-regression head over frozen X3D-S features | Trained in Phase 2C, copied from `ai-service/datasets/violence_head.json` — see below | `ai-service/app/action_recognition/x3d_violence_adapter.py` (optional, `X3D_ADAPTER=none` by default) |

**Note on the X3D-S backbone itself**: unlike the two YOLO checkpoints above, X3D-S's
~29.4MB pretrained backbone is **not** placed in this folder — it's fetched by
`torch.hub.load("facebookresearch/pytorchvideo", "x3d_s", pretrained=True)` into
`~/.cache/torch/hub/checkpoints/` on first use, the same mechanism used throughout
Phases 2B–2G. Only the small, project-specific classifier head trained on top of it
lives here.

## Firearm detection model — provenance (REMOVED from the active runtime, Phase 2V)

**This model is no longer loaded or run by `ai-service`.** Phase 2V removed firearm
detection from the pipeline entirely: the evaluation evidence across Phases 2K, 2L, 2M,
and 2U did not establish reliable firearm-vs-non-firearm discrimination (including
confirmed false positives on real knife frames), so the capability was withdrawn rather
than shipped as an unreliable feature. This is not a claim that "the system cannot
detect guns" in general, nor a claim that knives and firearms have been reliably
distinguished — see `docs/phase2v-firearm-removal.md` for the full reasoning. The
provenance below is kept as a historical record and because the file itself is retained
for the reasons in the table above.

- **Source**: [`Subh775/Firearm_Detection_Yolov8n`](https://huggingface.co/Subh775/Firearm_Detection_Yolov8n) on Hugging Face, file `weights/best.pt`.
- **Download** (verified via HTTP HEAD before fetching — exactly 6,238,307 bytes / ~5.95 MiB):
  ```bash
  curl -L -o models/firearm_yolov8n.pt \
    https://huggingface.co/Subh775/Firearm_Detection_Yolov8n/resolve/main/weights/best.pt
  ```
- **Architecture**: YOLOv8n, ~3.2M params, trained at 640×640, single class `"Gun"`
  (index 0) — does **not** distinguish pistols/rifles/shotguns from each other, and is
  not a general weapon detector (no knives, blades, etc.).
- **Reported metrics** (from the model card, not independently reproduced here):
  89.0% mAP@0.5, 60.2% mAP@0.5:0.95, trained on ~7,068 images (5,642 train / 1,426 val)
  sourced from Roboflow/Kaggle.
- **License — genuinely ambiguous in the upstream repo itself**: the model card's YAML
  frontmatter declares `AGPL-3.0`; its README badge separately shows `Apache 2.0`. This
  project treats it as **AGPL-3.0** (the more restrictive reading) pending clarification
  from the maintainer. Fine for this academic/research project; revisit before any
  commercial or hosted-service use — AGPL-3.0's network-use clause would apply.
- **The model card states, verbatim**: *"This model is provided for research purposes
  only. The predictions can not be used to solve real world problems."* This project
  labels its output `mode="REAL"` because it is genuine model inference, not a mock —
  but treat its accuracy as unvalidated beyond the one manual smoke test documented in
  [`../docs/ai-pipeline.md`](../docs/ai-pipeline.md). Do not rely on it as a
  safety-critical detector.

## Violence classifier head — provenance and why it's committed, not git-ignored

- **What it is**: a logistic-regression head (2048 coefficients + intercept) trained in
  Phase 2C on frozen X3D-S pooled features. Small (tens of KB), human-readable JSON, not
  a multi-MB/GB binary — the one artifact from Phases 2C–2G worth version-controlling so
  the exact deployed weights are auditable, unlike the large checkpoints and datasets
  around it which stay git-ignored.
- **Training data, honestly**: RLVS (Kaggle, license ambiguous — "© Original Authors"),
  filtered for a documented production-style bias (see `docs/phase2c-training.md`), plus
  8 self-recorded webcam clips. **Validation accuracy (99.6%/100% recall) is explicitly
  flagged in `docs/phase2c-training.md` as not trustworthy at face value** — it's
  dominated by a still-imperfectly-filtered data stratum.
- **Real-camera evidence** (Phases 2E–2G, the more meaningful validation here): correctly
  read 8/8 real calm webcam clips as NonViolence; on staged safe positive clips, showed
  real motion-correlated behavior including one confirmed threshold crossing into
  "Violence" — but only n=3 confirmed-elevated-motion data points total, non-monotonic
  relationship to raw motion, never tested against genuine multi-person conflict.
- **`mode="REAL"` on this adapter's output means genuine model inference occurred — it
  is explicitly NOT a claim that violence was confirmed, and NOT a claim this classifier
  is fully validated.** See `docs/ai-pipeline.md` "Stage 2 — X3D-S refinement" and
  `docs/phase2c-training.md` through `docs/phase2g-controlled-retest.md` for the full
  evidence trail before trusting or extending this.

No custom-trained action-recognition *backbone* weights exist in this project (X3D-S's
backbone is the stock Kinetics-400 pretrained checkpoint, untouched) — only this small
head was trained. See [`../docs/ai-pipeline.md`](../docs/ai-pipeline.md) for what a
fully custom-trained backbone would additionally require.
