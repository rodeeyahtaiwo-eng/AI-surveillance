import os

# Must run before any `app.*` module is imported anywhere in the test session, so
# Settings() picks these up — DETECTION_ADAPTER=mock avoids loading the real YOLO model
# (slow, and unnecessary for testing the pipeline's logic/wiring).
os.environ.setdefault("DETECTION_ADAPTER", "mock")
os.environ.setdefault("X3D_ADAPTER", "none")  # never load real X3D-S weights in tests
os.environ.setdefault("S3D_ADAPTER", "none")  # never load real S3D weights in tests (Phase 2R)
os.environ.setdefault("CAPTION_ADAPTER", "template")  # never load real BLIP weights in tests (Phase 2R)
os.environ.setdefault("TEMPORAL_PREDICTION_ADAPTER", "none")  # opt-in per test via monkeypatch (Phase 2R)
# Insulate the suite from a developer's local .env (e.g. left enabled for manual
# inspection per docs/ai-pipeline.md "Diagnostic frame capture") — tests that want it
# enabled do so explicitly via monkeypatch, see tests/test_diagnostic_capture.py.
os.environ.setdefault("DIAGNOSTIC_CAPTURE_ENABLED", "false")
os.environ.setdefault("INGEST_API_KEY", "test-only-ingest-key-not-for-prod-1234567890")
os.environ.setdefault("BACKEND_URL", "http://127.0.0.1:59999")  # deliberately unreachable
