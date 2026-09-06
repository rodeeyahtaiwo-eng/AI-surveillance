# Build context is the repo root (see docker/docker-compose.yml) so ../models resolves
# the same way inside the container as it does on the host.
FROM python:3.12-slim

# opencv-python-headless still needs a couple of shared libs at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ai-service ./ai-service
COPY models ./models

WORKDIR /app/ai-service
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
