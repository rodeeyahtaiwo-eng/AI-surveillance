import numpy as np

from app.common.clip_buffer import CameraClipBuffer, ClipBufferStore


def frame(value: int = 0):
    return np.full((4, 4, 3), value, dtype=np.uint8)


def test_buffer_caps_at_max_frames():
    buf = CameraClipBuffer(max_frames=5)
    for i in range(10):
        buf.add(frame(i))
    assert len(buf.frames) == 5


def test_buffer_keeps_most_recent_frames_oldest_first():
    buf = CameraClipBuffer(max_frames=3)
    for i in range(5):
        buf.add(frame(i))
    snapshot = buf.snapshot()
    # Frames 0,1 should have been evicted — only 2,3,4 remain, oldest first.
    assert [int(f[0, 0, 0]) for f in snapshot] == [2, 3, 4]


def test_is_full_enough():
    buf = CameraClipBuffer(max_frames=16)
    assert not buf.is_full_enough(13)
    for i in range(13):
        buf.add(frame(i))
    assert buf.is_full_enough(13)


def test_snapshot_is_a_copy_not_a_live_view():
    buf = CameraClipBuffer(max_frames=5)
    buf.add(frame(1))
    snap = buf.snapshot()
    buf.add(frame(2))
    assert len(snap) == 1  # the earlier snapshot must not see the later add


def test_store_isolates_buffers_per_camera():
    store = ClipBufferStore(max_frames=5)
    store.get("cam-a").add(frame(1))
    store.get("cam-b").add(frame(2))
    assert len(store.get("cam-a").frames) == 1
    assert len(store.get("cam-b").frames) == 1
    assert int(store.get("cam-a").snapshot()[0][0, 0, 0]) == 1
    assert int(store.get("cam-b").snapshot()[0][0, 0, 0]) == 2


def test_store_reuses_the_same_buffer_for_the_same_camera():
    store = ClipBufferStore(max_frames=5)
    store.get("cam-a").add(frame(1))
    store.get("cam-a").add(frame(2))
    assert len(store.get("cam-a").frames) == 2
