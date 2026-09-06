import os

import cv2
import numpy as np
import pytest

from src.sources.file_source import FileSource


@pytest.fixture
def tiny_video_path(tmp_path):
    path = str(tmp_path / "tiny.avi")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"XVID"), 5, (32, 32))
    for i in range(3):
        frame = np.full((32, 32, 3), fill_value=i * 50, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    assert os.path.exists(path)
    return path


def test_file_source_reads_frames(tiny_video_path):
    source = FileSource(tiny_video_path, loop=False)
    frames = []
    while True:
        frame = source.read()
        if frame is None:
            break
        frames.append(frame)
    assert len(frames) == 3
    source.release()


def test_file_source_loops_when_configured(tiny_video_path):
    source = FileSource(tiny_video_path, loop=True)
    # Read more frames than exist in the 3-frame clip — looping should keep it going.
    frames = [source.read() for _ in range(7)]
    assert all(f is not None for f in frames)
    source.release()


def test_file_source_raises_on_missing_file():
    with pytest.raises(RuntimeError):
        FileSource("this/path/does/not/exist.mp4", loop=False)


def test_file_source_is_labeled_not_live(tiny_video_path):
    source = FileSource(tiny_video_path)
    assert source.is_live is False
    assert source.label == "file"
    source.release()
