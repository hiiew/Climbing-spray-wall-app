# ── Base image ───────────────────────────────────────────────────────────────
# python:3.11-slim keeps the image small while providing all needed build tools.
# Switch to nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04 for GPU inference.
FROM python:3.11-slim

# ── Build args ───────────────────────────────────────────────────────────────
ARG APP_ENV=production

# ── System dependencies ──────────────────────────────────────────────────────
# libgl1 and libglib2.0-0 are required by opencv-python-headless.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Model weights directory ──────────────────────────────────────────────────
# Mount actual weights at runtime via a Docker volume or download script.
# The empty directory ensures the path exists on startup.
RUN mkdir -p models

# ── Non-root user for security ───────────────────────────────────────────────
RUN addgroup --system cvapp && adduser --system --ingroup cvapp cvapp
USER cvapp

# ── Environment variables ─────────────────────────────────────────────────────
ENV APP_ENV=${APP_ENV} \
    YOLO_WEIGHTS_PATH=/app/models/yolov8m-holds.pt \
    DETECTION_TIMEOUT_S=120 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ── Healthcheck ───────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# ── Expose port ───────────────────────────────────────────────────────────────
EXPOSE 8001

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
