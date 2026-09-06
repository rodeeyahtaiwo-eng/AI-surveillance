"""Shared X3D-S loading / preprocessing / feature-extraction helpers — Phase 2C.

Kept separate from benchmark_x3d.py (Phase 2B, already verified/complete) to avoid
touching that artifact. Used by extract_features.py and train_classifier.py. Not
imported by anything under app/ — this is training-side tooling only.
"""

import cv2
import numpy as np
import torch

NUM_FRAMES = 13
CROP_SIZE = 182
MEAN = np.array([0.45, 0.45, 0.45])
STD = np.array([0.225, 0.225, 0.225])

# The pre-classification pooled-feature layer, verified by forward hook in Phase 2C:
# model.blocks[5] is the ResNetBasicHead; its .pool submodule outputs (1, 2048, 1, 2, 2)
# for a (1, 3, 13, 182, 182) input — averaged over the residual spatial dims below to a
# flat 2048-d feature vector. See docs/phase2c-training.md "Feature extraction".
FEATURE_DIM = 2048


def load_frozen_model() -> torch.nn.Module:
    model = torch.hub.load("facebookresearch/pytorchvideo", "x3d_s", pretrained=True)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    return model


class FeatureExtractor:
    """Wraps a frozen X3D-S model with a forward hook that captures the pre-
    classification pooled features instead of the 400-way Kinetics logits."""

    def __init__(self, model: torch.nn.Module):
        self.model = model
        self._captured = None
        model.blocks[5].pool.register_forward_hook(self._hook)

    def _hook(self, module, inp, out):
        self._captured = out

    def extract(self, clip: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            self.model(clip)
        # (1, 2048, 1, 2, 2) -> (2048,) via global average over residual spatial dims.
        feat = self._captured.mean(dim=[2, 3, 4]).squeeze(0)
        return feat.numpy()


def clip_tensor_from_video(video_path: str, num_frames: int = NUM_FRAMES, crop_size: int = CROP_SIZE) -> torch.Tensor:
    """Extracts and preprocesses a clip from a video file, per X3D-S's documented
    input transform. Same logic as benchmark_x3d.py's real_clip_from_video (Phase 2B),
    factored out here so extract_features.py doesn't duplicate it a second time."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 1:
        cap.release()
        raise RuntimeError(f"Video has no frames: {video_path}")

    indices = np.linspace(0, max(total_frames - 1, 0), num_frames).astype(int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            # Fall back to the previous frame rather than failing the whole clip —
            # some clips have minor seek inconsistencies near their tail.
            if frames:
                frames.append(frames[-1])
                continue
            cap.release()
            raise RuntimeError(f"Failed to read frame {idx} from {video_path}")
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(frame)
    cap.release()

    processed = []
    for frame in frames:
        h, w = frame.shape[:2]
        scale = crop_size / min(h, w)
        new_h, new_w = max(round(h * scale), crop_size), max(round(w * scale), crop_size)
        resized = cv2.resize(frame, (new_w, new_h))
        top = (new_h - crop_size) // 2
        left = (new_w - crop_size) // 2
        cropped = resized[top : top + crop_size, left : left + crop_size]
        processed.append(cropped)

    clip = np.stack(processed, axis=0).astype(np.float32) / 255.0
    clip = (clip - MEAN) / STD
    clip = torch.from_numpy(clip).permute(3, 0, 1, 2).float()
    return clip.unsqueeze(0)
