"""Isolated X3D-S CPU benchmark — Phase 2B feasibility check.

This is a MANUAL verification script, not part of the automated test suite and not
wired into the application. It does not import or touch anything under app/ and does
not change any pipeline behavior — see docs/ai-pipeline.md for the (not-yet-changed)
production action-recognition adapter.

Usage:
    venv\\Scripts\\python.exe scripts\\benchmark_x3d.py                # architecture only, no weights
    venv\\Scripts\\python.exe scripts\\benchmark_x3d.py --pretrained    # real pretrained checkpoint
    venv\\Scripts\\python.exe scripts\\benchmark_x3d.py --pretrained --video path\\to\\clip.mp4

Measures, per thread-count (1, 4, 8 by default): model load time, warm-up time,
average/min/max inference time over >=10 timed runs, clips/sec, and process RSS before
loading / after loading / after inference — using psutil (already a project dependency
via ultralytics).
"""

import argparse
import time

import numpy as np
import psutil
import torch

# X3D-S's exact expected input, per docs/ai-pipeline.md Phase 2A investigation:
# 13 frames, 182x182, verified against PyTorch Hub's own model page.
NUM_FRAMES = 13
CROP_SIZE = 182
MEAN = [0.45, 0.45, 0.45]
STD = [0.225, 0.225, 0.225]

THREAD_COUNTS = [1, 4, 8]
NUM_TIMED_RUNS = 10


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 1e6


def load_model(pretrained: bool):
    return torch.hub.load("facebookresearch/pytorchvideo", "x3d_s", pretrained=pretrained)


def synthetic_clip() -> torch.Tensor:
    """A random tensor matching X3D-S's exact expected shape — no dataset/video needed."""
    return torch.randn(1, 3, NUM_FRAMES, CROP_SIZE, CROP_SIZE)


def real_clip_from_video(video_path: str) -> torch.Tensor:
    """Extracts and preprocesses a real 13-frame clip from a local video file, per
    X3D-S's documented input transform (uniform temporal subsample -> scale to [0,1]
    -> normalize -> short-side scale -> center crop). See Step 5 of the Phase 2B plan.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < NUM_FRAMES:
        raise RuntimeError(f"Video has only {total_frames} frames, need at least {NUM_FRAMES}")

    # Uniform temporal subsample across the whole video, matching
    # pytorchvideo.transforms.UniformTemporalSubsample's behavior.
    indices = np.linspace(0, total_frames - 1, NUM_FRAMES).astype(int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Failed to read frame {idx} from {video_path}")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # OpenCV is BGR; model expects RGB
        frames.append(frame)
    cap.release()

    # Short-side scale to CROP_SIZE, then center-crop CROP_SIZE x CROP_SIZE.
    processed = []
    for frame in frames:
        h, w = frame.shape[:2]
        scale = CROP_SIZE / min(h, w)
        new_h, new_w = round(h * scale), round(w * scale)
        resized = cv2.resize(frame, (new_w, new_h))
        top = (new_h - CROP_SIZE) // 2
        left = (new_w - CROP_SIZE) // 2
        cropped = resized[top : top + CROP_SIZE, left : left + CROP_SIZE]
        processed.append(cropped)

    clip = np.stack(processed, axis=0).astype(np.float32) / 255.0  # [T, H, W, C], 0-1
    clip = (clip - np.array(MEAN)) / np.array(STD)
    clip = torch.from_numpy(clip).permute(3, 0, 1, 2).float()  # -> [C, T, H, W]
    return clip.unsqueeze(0)  # -> [1, C, T, H, W]


def benchmark_thread_count(model: torch.nn.Module, clip: torch.Tensor, num_threads: int) -> dict:
    torch.set_num_threads(num_threads)

    with torch.no_grad():
        t0 = time.perf_counter()
        model(clip)  # warm-up
        warmup_time = time.perf_counter() - t0

        times = []
        for _ in range(NUM_TIMED_RUNS):
            t0 = time.perf_counter()
            model(clip)
            times.append(time.perf_counter() - t0)

    avg = sum(times) / len(times)
    return {
        "threads": num_threads,
        "warmup_s": warmup_time,
        "avg_s": avg,
        "min_s": min(times),
        "max_s": max(times),
        "clips_per_sec": 1.0 / avg,
        "rss_mb": rss_mb(),
    }


def run(pretrained: bool, video_path: str | None) -> None:
    print(f"{'=' * 70}\nX3D-S benchmark — pretrained={pretrained}\n{'=' * 70}")

    rss_before = rss_mb()
    print(f"Process RSS before loading model: {rss_before:.0f} MB")

    t0 = time.perf_counter()
    model = load_model(pretrained=pretrained)
    model.eval()
    load_time = time.perf_counter() - t0

    rss_after_load = rss_mb()
    print(f"Model load time: {load_time:.2f}s")
    print(f"Process RSS after loading model: {rss_after_load:.0f} MB "
          f"(+{rss_after_load - rss_before:.0f} MB)")
    print(f"Param count: {sum(p.numel() for p in model.parameters()):,}")

    if video_path:
        print(f"\nExtracting real 13-frame clip from: {video_path}")
        clip = real_clip_from_video(video_path)
        print(f"Clip tensor shape: {tuple(clip.shape)} (expected (1, 3, 13, 182, 182))")
    else:
        clip = synthetic_clip()
        print(f"\nUsing synthetic random clip, shape: {tuple(clip.shape)}")

    print()
    results = []
    for n in THREAD_COUNTS:
        r = benchmark_thread_count(model, clip, n)
        results.append(r)
        print(
            f"threads={r['threads']:<2} warmup={r['warmup_s']*1000:6.0f}ms  "
            f"avg={r['avg_s']*1000:6.0f}ms  min={r['min_s']*1000:6.0f}ms  "
            f"max={r['max_s']*1000:6.0f}ms  clips/sec={r['clips_per_sec']:.2f}  "
            f"rss={r['rss_mb']:.0f}MB"
        )

    print("\n| Threads | Avg inference | Min | Max | Approx RAM |")
    print("|---|---|---|---|---|")
    for r in results:
        print(
            f"| {r['threads']} | {r['avg_s']*1000:.0f}ms | {r['min_s']*1000:.0f}ms | "
            f"{r['max_s']*1000:.0f}ms | {r['rss_mb']:.0f}MB |"
        )

    rss_after_inference = rss_mb()
    print(f"\nProcess RSS after inference: {rss_after_inference:.0f} MB "
          f"(+{rss_after_inference - rss_after_load:.0f} MB vs. after-load)")

    best = min(results, key=lambda r: r["avg_s"])
    print(f"\nBest thread count: {best['threads']} ({best['avg_s']*1000:.0f}ms avg)")

    if video_path:
        with torch.no_grad():
            output = model(clip)
        pred_class = int(output.argmax(dim=1).item())
        print(f"\nOutput tensor shape: {tuple(output.shape)}")
        print(f"Predicted Kinetics-400 class index: {pred_class} "
              f"(NOT meaningful for fighting detection yet — untrained on our task, "
              f"see docs/ai-pipeline.md)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X3D-S CPU benchmark (manual, isolated — not an automated test)")
    parser.add_argument("--pretrained", action="store_true", help="Load real pretrained Kinetics-400 weights")
    parser.add_argument("--video", type=str, default=None, help="Path to a local video file for a real-clip smoke test")
    args = parser.parse_args()
    run(pretrained=args.pretrained, video_path=args.video)
