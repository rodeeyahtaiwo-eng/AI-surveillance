"""CLI entry point for ingesting one camera source and forwarding sampled frames to
ai-service. See video-processing/README.md for usage examples.

Usage:
  python -m src.run_camera --camera-id <id> --source webcam --device 0
  python -m src.run_camera --camera-id <id> --source file --path C:\\path\\to\\demo.mp4
  python -m src.run_camera --camera-id <id> --source rtsp --url rtsp://user:pass@host/stream

<camera-id> must match a camera already registered in the backend (Cameras page) — this
script does not create cameras, it only ingests video for one that already exists.
"""

import argparse
import logging

from src.pipeline import run
from src.sources.file_source import FileSource
from src.sources.rtsp_source import RtspSource
from src.sources.webcam_source import WebcamSource

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a camera source into the AI pipeline.")
    parser.add_argument("--camera-id", required=True, help="Camera ID as registered in the backend")
    parser.add_argument("--source", required=True, choices=["webcam", "file", "rtsp"])
    parser.add_argument("--device", type=int, default=0, help="Webcam device index (source=webcam)")
    parser.add_argument("--path", help="Video file path (source=file)")
    parser.add_argument("--url", help="RTSP URL (source=rtsp)")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N frames (testing)")
    args = parser.parse_args()

    if args.source == "webcam":
        source = WebcamSource(device_index=args.device)
    elif args.source == "file":
        if not args.path:
            parser.error("--path is required for --source file")
        source = FileSource(path=args.path)
    else:
        if not args.url:
            parser.error("--url is required for --source rtsp")
        source = RtspSource(rtsp_url=args.url)

    run(camera_id=args.camera_id, source=source, max_frames=args.max_frames)


if __name__ == "__main__":
    main()
