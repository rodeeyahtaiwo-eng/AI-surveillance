import base64
from unittest.mock import MagicMock, patch

import numpy as np

from src.pipeline import encode_frame, send_frame


def test_encode_frame_returns_valid_base64_jpeg():
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    encoded = encode_frame(frame)
    raw = base64.b64decode(encoded)
    # JPEG files start with the SOI marker 0xFFD8.
    assert raw[:2] == b"\xff\xd8"


@patch("src.pipeline.requests.post")
def test_send_frame_posts_expected_payload(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"detections": [], "action_evaluated": False}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    result = send_frame("camera-123", frame)

    assert result == {"detections": [], "action_evaluated": False}
    called_url = mock_post.call_args.args[0]
    called_body = mock_post.call_args.kwargs["json"]
    assert called_url.endswith("/infer/frame")
    assert called_body["camera_id"] == "camera-123"
    assert "image_base64" in called_body
    assert "frame_timestamp" in called_body
