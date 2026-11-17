FROM python:3.11-slim

# ffmpeg is required for upload transcode + Opus compression.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data (db, audio) and the Whisper model cache should be mounted volumes so they
# persist across container restarts:
#   -v autolect-data:/app/data -v autolect-models:/root/.cache/huggingface
VOLUME ["/app/data", "/root/.cache/huggingface"]
EXPOSE 8000

# NOTE: inside Linux containers faster-whisper runs on CPU (no Metal/MPS). Set
# WHISPER_DEVICE=cpu in .env; the provider also falls back to CPU automatically.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
