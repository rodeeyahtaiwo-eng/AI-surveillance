# X3D-S Feasibility Benchmark (Phase 2B)

**Status: investigation/benchmark only.** X3D-S is not integrated into the production
pipeline. `ACTION_ADAPTER` is still `demo_heuristic` (see
`ai-service/app/action_recognition/demo_heuristic.py`) and nothing under `app/` was
modified to produce this report — see [`ai-pipeline.md`](./ai-pipeline.md) for what's
actually running in production today.

This document records empirical measurements on the project's actual dev machine, not
estimates — every number below came from actually running the model, not from reading
documentation. See `ai-service/scripts/benchmark_x3d.py` (isolated benchmark script,
not wired into the app) for the exact code used.

## Hardware

Intel Core i5-8250U (4 physical / 8 logical cores), 16GB RAM, Intel UHD 620 (integrated,
no CUDA), CPU-only PyTorch. Deployment target is this same machine.

## Dependency install

`pytorchvideo`, `fvcore`, `iopath` installed into the existing `ai-service` venv.
**Verified via `pip install --dry-run` before installing for real**: the resolver did
**not** need to touch `torch` or `torchvision` — both remained at their existing
versions (`2.13.0+cpu` / `0.28.0+cpu`) after install, confirmed with `pip show` before
and after.

| Package | Version |
|---|---|
| torch | 2.13.0+cpu (unchanged) |
| torchvision | 0.28.0+cpu (unchanged) |
| pytorchvideo | 0.1.5 |
| fvcore | 0.1.5.post20221221 |
| iopath | 0.1.10 |
| av (PyAV, pulled in by pytorchvideo) | 18.1.0 |

No compatibility errors at any step — despite `pytorchvideo`'s last PyPI release being
January 2022 (a real risk flagged before installing), it loaded and ran cleanly against
torch 2.13.0.

## Model load

- Architecture load (`torch.hub.load(..., pretrained=False)`): 3,794,274 parameters —
  matches the expected ~3.79M exactly.
- Pretrained checkpoint (`X3D_S.pyth`): **30,779,313 bytes exactly**, downloaded from
  `dl.fbaipublicfiles.com` via `torch.hub`, verified against a HEAD-request check made
  before downloading anything.
- Model load time (architecture + checkpoint deserialization): ~3.4–4.2s across runs —
  a one-time cost, not per-clip.

## CPU inference benchmark

Synthetic input `torch.randn(1, 3, 13, 182, 182)` (X3D-S's exact expected shape), 1
warm-up call, 10 timed runs per thread count, `torch.no_grad()`, `model.eval()`.

| Threads | Avg inference | Min | Max | Approx RAM |
|---|---|---|---|---|
| 1 | 388ms | 374ms | 403ms | 407MB |
| 4 | 235ms | 224ms | 242ms | 415MB |
| 8 | 221ms | 209ms | 259ms | 421MB |

**Observations:**
- 1 thread is consistently ~65-75% slower than 4 or 8 — do not run this single-threaded.
- 4 vs. 8 threads is close and noisy across repeated runs (each has won in different
  runs across this investigation) — not a clean, stable winner either way.
- RAM is essentially flat across thread counts (~407–421MB) — `torch.set_num_threads()`
  controls compute parallelism, not memory allocation, so this is expected, not a
  measurement artifact.
- **Recommendation for later integration:** `torch.set_num_threads(4)`, not 8 — it
  captures nearly all the available speedup while leaving the other logical cores free
  for the rest of the concurrently-running pipeline (YOLOv8n, firearm YOLOv8n, FastAPI,
  JPEG decode, backend, WebSocket). This is a recommendation to validate once X3D-S is
  actually running alongside everything else, not a final decision from an isolated
  benchmark.

## Real-time feasibility at 2 fps (500ms/frame budget)

**B — X3D-S can run periodically or when triggered, not on every sampled frame.**

At best measured cost (~221ms/clip), X3D-S alone would fit inside the 500ms budget with
margin — but that is not the right comparison. Phase 1 already measured general
YOLOv8n + firearm YOLOv8n running together on every sampled frame at **~379ms/frame**
(real image, real models). Adding X3D-S's ~221-388ms on top of every frame would push
total per-frame cost to **~600ms–770ms, over budget** — before accounting for JPEG
decode, HTTP/FastAPI overhead, or backend round-trips, none of which this benchmark
measures.

This confirms the design already established in the Phase 2 investigation: X3D-S must
run on a rolling clip buffer at a slower cadence than the 2 fps detector loop (e.g. one
evaluation per multi-second window, or triggered early when the geometry heuristic
already flags elevated proximity/movement) — never as a per-frame call alongside the two
YOLO detectors.

## Existing system regression check

- `ai-service` test suite: **36/36 passing**, unchanged from before this phase's
  dependency install.
- `backend` test suite: **21/21 passing**.
- Phase 1's firearm detector (`YoloV8FirearmAdapter`) re-run live against the same test
  image used in Phase 1: identical result (`firearm`, confidence 0.829, mode REAL).
- General `YoloV8Adapter` re-run live: identical result (4 persons + 1 tv detected).

No dependency conflict, no regression, nothing under `app/` was modified.

## Open item: RLVS dataset

Not yet inspected — see the chat report for why (Kaggle requires authenticated access;
this machine has no Kaggle account credentials configured, and no alternative mirror of
RLVS exists on Hugging Face, GitHub, or Zenodo, per a search done as part of this
phase). Steps 5–6 of this phase are blocked on that, not on disk space (28.99GB free,
comfortably enough for RLVS's ~1.86GB) or anything technical on the X3D-S side.
