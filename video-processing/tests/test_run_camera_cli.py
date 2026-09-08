"""Phase 2AM — tests the --no-loop CLI flag added to run_camera.py for one-shot
uploaded-video processing jobs. Uses FileSource's own existing `loop` constructor
parameter (untouched) — this only confirms the CLI wires it correctly."""

import sys

from src.run_camera import main


def test_default_source_file_loops(monkeypatch):
    captured = {}
    monkeypatch.setattr("src.run_camera.FileSource", lambda path, loop: captured.update(path=path, loop=loop))
    monkeypatch.setattr("src.run_camera.run", lambda **kwargs: None)
    monkeypatch.setattr(sys, "argv", ["run_camera.py", "--camera-id", "cam-1", "--source", "file", "--path", "x.mp4"])

    main()

    assert captured == {"path": "x.mp4", "loop": True}


def test_no_loop_flag_disables_looping(monkeypatch):
    captured = {}
    monkeypatch.setattr("src.run_camera.FileSource", lambda path, loop: captured.update(path=path, loop=loop))
    monkeypatch.setattr("src.run_camera.run", lambda **kwargs: None)
    monkeypatch.setattr(
        sys, "argv", ["run_camera.py", "--camera-id", "cam-1", "--source", "file", "--path", "x.mp4", "--no-loop"]
    )

    main()

    assert captured == {"path": "x.mp4", "loop": False}
