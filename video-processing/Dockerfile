# Build context is the repo root (see docker/docker-compose.yml).
# NOTE: this container has no access to a host webcam device — it's only useful for
# --source file (mount a demo video, see docker-compose.yml's `ingestion` profile) or
# --source rtsp. For webcam ingestion, run video-processing on the host instead (see
# video-processing/README.md).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/video-processing
COPY video-processing/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY video-processing ./

ENTRYPOINT ["python", "-m", "src.run_camera"]
CMD ["--help"]
