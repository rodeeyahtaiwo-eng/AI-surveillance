# RLVS Dataset Inspection (Phase 2B, Step 5–6)

**Status: inspection only.** Not used for training yet. X3D-S is still `demo_heuristic` in
production — see [`x3d-benchmark.md`](./x3d-benchmark.md) for the model-side benchmark
this dataset would eventually pair with.

## Provenance / download

- Source: [Kaggle — Real Life Violence Situations Dataset](https://www.kaggle.com/datasets/mohamedmustafa/real-life-violence-situations-dataset)
- Downloaded manually (Kaggle requires an authenticated account; no API access was
  configured on this machine — see the Phase 2B chat log for why automated download
  wasn't possible).
- **Zip file: 3,847,870,446 bytes (~3.58 GiB)** — notably larger than the ~1.86GB
  reported by Kaggle's own dataset-metadata API in the earlier Phase 2A investigation.
- **Root cause found by inspecting the zip's internal structure before extracting**:
  the archive contains the same 2,000-video dataset **twice**, once at
  `Real Life Violence Dataset/` and again nested inside
  `real life violence situations/Real Life Violence Dataset/` — confirmed identical by
  comparing file sizes of a sample file present at both paths. This is a packaging
  artifact (a redundant folder wrapped around an already-organized copy), not a
  different/larger dataset version. **Only the non-duplicated copy was extracted.**
- Extracted to `ai-service/datasets/rlvs/` (git-ignored — see root `.gitignore`).
- Extracted size: **1.9 GB**. Disk space after extraction: **22.70 GB free** (was
  24.77GB before extraction, 28.99GB before the zip download) — no space concern at any
  point.
- License, unchanged from the Phase 2A finding: Kaggle lists it as **"Data files ©
  Original Authors"** — not a standard open license. Sourced from YouTube. Fine for
  this academic project's experimentation; not something to treat as freely
  redistributable.

## Structure & decodability (exhaustive, not sampled)

| | Violence | NonViolence |
|---|---|---|
| Count | 1,000 | 1,000 |
| Formats | 1,000 `.mp4` | 951 `.mp4`, 49 `.avi` |
| Decoded successfully (OpenCV) | **1,000 / 1,000** | **1,000 / 1,000** |

Every file in both classes opens and decodes (verified by actually reading each file's
first frame, not just parsing headers) — no corrupt or unreadable files found.

## Duration, resolution, frame rate (measured on all 2,000 files)

| | Violence | NonViolence |
|---|---|---|
| Duration: min / median / avg / max | 2.9s / 5.0s / 5.4s / **375.7s** | 1.0s / 5.0s / 5.1s / **179.9s** |
| Distinct resolutions | 140 | 7 |
| Most common resolution | 224×224 (19.9%) | 224×224 (74.9%) |
| Distinct fps values | 21 | 16 |
| Most common fps | 30.0fps (69.4%) | 25.0fps (37.2%), 30.0fps (18.3%) |

**Findings, not just numbers:**
- The median (5.0s, both classes) matches the dataset's documented "~5s clips"
  description — but the **max duration is a 6+ minute Violence clip and a 3-minute
  NonViolence clip**, clear long-tail outliers that are not short trimmed incidents.
  These are very likely uncut movie/broadcast scenes, not isolated events — a
  data-cleaning step (trimming or filtering by duration) would be needed before
  training, not just uniform temporal subsampling.
- **A large share of NonViolence clips (75%) are already exactly 224×224** — the
  standard CNN/ImageNet input size. This means a majority of the NonViolence class has
  already been through someone else's preprocessing pipeline at some point in its
  history, not left at original camera resolution. Violence has far more resolution
  diversity (140 distinct values), most much closer to real camera-native resolutions.
- Frame rate is inconsistent within and across classes (up to 21 distinct values,
  including non-standard rates like 37fps and as low as 11fps) — consistent with a
  YouTube-scraped collection of independently-encoded sources, not a uniform capture
  pipeline. `pytorchvideo`'s `UniformTemporalSubsample` handles variable-fps input fine
  (it samples by frame index, not wall-clock time), but this is worth knowing before
  assuming timing consistency across clips.

## Manual visual inspection (24 clips: 11 Violence, 13 NonViolence, middle frame of each)

This is the most important finding of this phase and was **not** visible from metadata
alone — it required actually looking at the frames.

**Violence (11 sampled):** 7 genuine amateur handheld street-altercation footage
(phone-shot, real people, real streets — matches the dataset's stated intent), 2 that
are actually **fixed-angle CCTV/surveillance-style footage** reposted via
compilation channels (exactly the intended domain — a genuinely good sign), 2 sports
broadcast scuffles (e.g. an AFL match altercation, stadium camera + scoreboard overlay).

**NonViolence (13 sampled):** only **2 of 13 (~15%)** looked like plausible
candid/amateur real-world footage. The rest: **6 professional sports broadcasts**
(chess, Olympic weightlifting, Davis Cup tennis, table tennis, track & field, Premier
League football — all with sponsor overlays/scoreboards/broadcast graphics), **3
archival black-and-white film/TV clips** (one with visible Arabic-network TV branding),
**2 color TV/movie drama scenes** (one with a visible AMC network watermark).

**This is a real suitability concern, not a minor cosmetic one.** The two classes differ
systematically in *production style*, not just in the presence/absence of violence:
Violence skews toward amateur handheld phone video; NonViolence skews heavily toward
professionally-produced broadcast and film content. A classifier trained directly on
this class split risks learning "shaky amateur footage vs. polished broadcast footage"
as a shortcut instead of actual violence-related motion/appearance features — a shortcut
that would **not transfer** to a real fixed-camera webcam/CCTV deployment, where neither
class would look like either extreme. This doesn't make the dataset unusable, but it
does mean **the non-representative NonViolence clips (sports broadcasts, archival film)
should be identified and likely excluded or down-weighted before fine-tuning**, and the
model's real-world performance should not be assumed from validation accuracy on this
dataset's own held-out split alone.

## Camera style / lighting / density observations (as requested)

- **Fixed vs. handheld**: Violence is majority handheld/phone-shot (motion blur,
  vertical/portrait framing common); the 2 genuine CCTV-style clips are the exception,
  not the rule. NonViolence's broadcast content is professionally stabilized
  fixed/tracking camera work — a different kind of "non-handheld" than a static
  surveillance camera.
- **Lighting**: Violence spans night (low-light, grainy) and day (harsh outdoor)
  conditions realistically. NonViolence's broadcast content is uniformly
  well-lit (stadium/studio lighting) — again, unrepresentative of real ambient
  conditions a webcam would see.
- **People density**: mostly 2-4 people in frame for genuine Violence clips (consistent
  with one-on-one or small-group altercations); broadcast NonViolence clips often have
  many people (crowds, teams) which is also not representative of a typical single-room
  webcam scene.
- **Visual quality**: highly variable in both classes — compressed/re-encoded/
  watermarked video-app exports (VivaVideo, compilation-channel logos) are common,
  consistent with this being a scraped/aggregated YouTube collection rather than
  original-source footage.

## Bottom line

The dataset is **not perfect and shouldn't be presented as such**: real licensing
ambiguity, un-trimmed duration outliers, heavy pre-resizing in a majority of one class,
and — the most consequential finding — a systematic production-style mismatch between
classes that risks teaching the wrong signal. It is still usable as a **starting point**
for head-only fine-tuning (per the Phase 2A training-strategy recommendation), but a
future phase should budget time to either filter out the clearly non-representative
NonViolence clips (broadcast sports, archival film) or accept that the initial model may
carry a real domain-generalization gap — not a decision to make silently.
