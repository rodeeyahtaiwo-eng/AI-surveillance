from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central config, loaded from environment variables / .env. See .env.example for
    what each adapter selector means — docs/ai-pipeline.md documents which adapters are
    real models vs. clearly-labeled demo implementations."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000

    detection_adapter: str = "yolov8"  # "yolov8" (real) | "mock"
    action_adapter: str = "demo_heuristic"
    # "template" (default) — deterministic sentence templates, no model.
    # "blip" (Phase 2R) — real Salesforce/blip-image-captioning-base over the latest
    # buffered frame, low/event-triggered cadence (see caption_blip_cooldown_seconds).
    # BLIP output is NOT ground truth: see app/captioning/blip_adapter.py and
    # docs/phase2r-integration.md "Grounding rules" — its raw caption is never used to
    # create Detection rows or threat signals; only real detector results are
    # authoritative for object presence.
    caption_adapter: str = "template"
    threat_adapter: str = "rule_based"

    # Orthogonal to action_adapter, not a value of it: X3D-S is an OPTIONAL refinement
    # layer bolted onto whatever action_adapter already produces. "none" (default) —
    # disabled, code path never runs, behavior is identical to no Phase 2H changes at
    # all. "x3d_violence" — real frozen X3D-S + Phase 2C's trained classifier head.
    # See docs/ai-pipeline.md "Stage 2 — X3D-S refinement" before enabling: mode="REAL"
    # here means genuine model inference, NOT a validated/reliable violence detector —
    # the Phase 2C-2G validation evidence is limited (see docs/phase2c-training.md
    # through docs/phase2g-controlled-retest.md).
    x3d_adapter: str = "none"
    x3d_head_path: str = "../models/violence_head.json"
    # Confidence (P(Violence)) X3D-S must clear to upgrade the heuristic's observation
    # from DEMO to REAL — matches the classifier's own training-time decision boundary.
    x3d_confidence_threshold: float = 0.5
    # Minimum seconds between X3D-S evaluations for the same camera — see
    # CameraWindow.should_evaluate_x3d() in app/common/frame_buffer.py.
    x3d_eval_cooldown_seconds: int = 15
    # Raw frames retained per camera for X3D-S's 13-frame input — see
    # app/common/clip_buffer.py. A few extra beyond 13 so a slightly-stale buffer can
    # still supply a full clip.
    clip_buffer_max_frames: int = 16

    # S3D Kinetics-400 (Phase 2R) — SUPPLEMENTARY, not a replacement for action_adapter
    # above. "none" (default) — disabled, zero cost, identical behavior to pre-Phase-2R.
    # "s3d_kinetics400" — real torchvision S3D inference over buffered raw frames,
    # returned as ActionResult.s3d_prediction using the model's OWN 400-class Kinetics
    # vocabulary, completely unmapped to any threat category (see
    # docs/phase2r-integration.md "Critical semantic rule" — Phase 2Q found its top-5 on
    # a staged-aggressive clip were low-confidence, unrelated everyday actions; this is
    # not a violence detector and RuleBasedThreatEngine never reads this field).
    s3d_adapter: str = "none"
    # Minimum seconds between S3D evaluations for the same camera (CPU-only, ~1-2s per
    # clip measured in Phase 2Q — must not run every frame). See
    # CameraWindow.should_evaluate_s3d() in app/common/frame_buffer.py.
    s3d_eval_cooldown_seconds: int = 20
    # Frames S3D needs per clip (torchvision's official Kinetics-400 recipe commonly
    # uses 16); reuses the SAME clip_buffer_max_frames pool as X3D-S above, not a
    # second buffer.
    s3d_num_frames: int = 16

    # Minimum seconds between BLIP caption generations for the same camera, when
    # CAPTION_ADAPTER=blip (Phase 2R) — event-triggered/low-cadence, never per-frame.
    # Phase 2Q measured ~2-4s inference and a ~854MB generation-time RAM spike on this
    # CPU; a cooldown well above the inference cost keeps it a small fraction of total
    # load. Ignored when CAPTION_ADAPTER=template (the default).
    #
    # Phase 2AE — lowered from 20 to 10 for more responsive AI-analysis text, per
    # explicit request. Confirmed no other coupling: this constant is read in exactly
    # one place (blip_adapter.py's on_cooldown check). FLAGGED, not hidden: BLIP's
    # caption() call is still fully synchronous in this codebase (Phase 2AB's
    # background-threading fix was reverted, see docs/phase2ab-live-stabilization.md's
    # own "REVERTED" note) — a cache miss still blocks the whole evaluate_window() call
    # for its measured ~1.8-2.2s (Phase 2AB) / ~2-4s (Phase 2Q) real inference cost on
    # this CPU. Halving the cooldown roughly doubles how often that stall happens: at
    # 20s, a ~2s block occupies ~10% of any 20s span; at 10s, the same ~2s block now
    # occupies ~20% of any 10s span. This is a real, non-hypothetical increase in how
    # often a camera's frame-processing round-trip will visibly stall for ~2s on this
    # CPU-only i5-8250U, not just a config-only change.
    caption_blip_cooldown_seconds: int = 10

    # Temporal next-event predictor (Phase 2R) — SUPPLEMENTARY, informational only;
    # RuleBasedThreatEngine never reads ActionResult.temporal_prediction. "none"
    # (default) — disabled. "markov_v1" — order-1 empirical transition model over this
    # camera's own recent action-label history, in-memory, this process's uptime only
    # (no historical backend data is read back in this phase — see
    # docs/phase2r-integration.md for why). Validated in Phase 2Q as a prototype
    # (71% walk-forward accuracy vs. 61% naive-repeat baseline on one historical
    # sequence dominated by repeated demo behavior) — not a generalization estimate.
    temporal_prediction_adapter: str = "none"
    # How many recent (timestamp, label) events to retain per camera for the transition
    # model — bounds memory; irrelevant once "seen", since transitions are counted
    # incrementally, not recomputed from the raw history each time.
    temporal_prediction_max_history: int = 50

    yolo_model_path: str = "../models/yolov8n.pt"
    yolo_confidence_threshold: float = 0.45

    # Knife evidence persistence (Phase 2S — see docs/phase2s-threat-reasoning.md and
    # app/threat/rule_based.py's KNIFE_* constants). Defaults derived from actual system
    # timing, not chosen arbitrarily: SAMPLE_FPS defaults to 2
    # (video-processing/src/config.py); a 4s window spans ~8 samples at that rate (more
    # at higher configured rates), and stays safely inside sequence_window_seconds (6s)
    # below — entries older than that are already pruned from the buffer, so this window
    # must not exceed it, or confirming hits could be pruned away before they're counted.
    #
    # Phase 2AD — lowered from 2 to 1 (CONFIRMED GAP, current-state audit): the one real
    # historical knife-threat scenario in this system's history produced exactly 1
    # knife-class detection (0.475 conf) in its window, never 2, so the K=2 gate never
    # engaged, before or after that audit's other fixes. Before lowering this, every
    # real knife-class Detection row ever logged (27 total, this camera, all history)
    # was cross-referenced against its nearest caption/context: zero occurred during an
    # unrelated, knife-free scene -- every one, including every isolated single-hit
    # instance, corresponds to a real knife-holding test session, confirmed either by
    # BLIP's own caption in that exact window or by immediate temporal adjacency to
    # frames that explicitly name it. No noise-level false-positive pattern was found
    # at the existing 0.45 confidence threshold, so K=1 was adopted directly rather
    # than the narrower person-gated alternative that was also considered.
    knife_persistence_min_hits: int = 1  # K
    knife_persistence_window_seconds: int = 4  # T — must be <= sequence_window_seconds

    sequence_window_seconds: int = 6

    # Local diagnostic frame capture (Phase 2J) — saves the source frame + metadata for
    # detections matching diagnostic_capture_classes, so false positives can be visually
    # reviewed before any threshold/model decision is made. See
    # app/common/diagnostic_capture.py and docs/ai-pipeline.md "Diagnostic frame
    # capture". Disabled by default: this saves real camera frames (potentially of a
    # real person) to local disk, and must be explicitly opted into. Never sent to the
    # backend, never exposed via any API — a local dev artifact only.
    diagnostic_capture_enabled: bool = False
    # comma-separated, e.g. "knife,cat,dog,toothbrush". Defaults to "knife" (Phase 2V) —
    # knife is now the most sensitive class in the active detection scope, following the
    # removal of firearm detection (docs/phase2v-firearm-removal.md); this mechanism
    # itself is generic and was previously demonstrated with "firearm" as the example
    # class (Phase 2J-2U), before that detector existed/was removed.
    diagnostic_capture_classes: str = "knife"
    diagnostic_capture_max_frames: int = 200  # per class subfolder — oldest evicted first
    diagnostic_capture_dir: str = "diagnostics/frames"  # relative to ai-service/'s CWD

    backend_url: str = "http://localhost:4000"
    ingest_api_key: str = "INSECURE-DEV-ONLY-INGEST-KEY-change-me-before-deploying"


settings = Settings()
