"""Raw-pixel clip buffer — Phase 2H. Deliberately separate from FrameBufferStore
(app/common/frame_buffer.py), which buffers (timestamp, detections) — cheap, small,
kept for the full sequence_window_seconds. This buffers actual decoded frames, which
are not cheap to hold indefinitely, so it's capped by *count*, not just time, and lives
in its own store so cameras/adapters that never enable X3D-S pay zero cost for it.
"""

from collections import deque
from typing import Deque, Dict, List

import numpy as np


class CameraClipBuffer:
    """Fixed-size ring buffer of raw frames for one camera."""

    def __init__(self, max_frames: int) -> None:
        self.max_frames = max_frames
        self.frames: Deque[np.ndarray] = deque(maxlen=max_frames)

    def add(self, frame: np.ndarray) -> None:
        self.frames.append(frame)

    def is_full_enough(self, min_frames: int) -> bool:
        return len(self.frames) >= min_frames

    def snapshot(self) -> List[np.ndarray]:
        """A copy of the currently buffered frames, oldest first — safe for a caller to
        hand off to a background thread without it changing underfoot."""
        return list(self.frames)


class ClipBufferStore:
    """Per-camera CameraClipBuffer registry — one process-wide instance, mirroring
    FrameBufferStore's pattern (see app/services/pipeline.py)."""

    def __init__(self, max_frames: int) -> None:
        self.max_frames = max_frames
        self._buffers: Dict[str, CameraClipBuffer] = {}

    def get(self, camera_id: str) -> CameraClipBuffer:
        if camera_id not in self._buffers:
            self._buffers[camera_id] = CameraClipBuffer(self.max_frames)
        return self._buffers[camera_id]
