# /docker/origin.Dockerfile
# Build context is the repo root (see compose: context: ..)
#
# Origin runs the FastAPI app at origin/main.py on port 8080.
# Shares mantle/requirements.txt with Mantle — same venv, two processes.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# ---- System deps ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps (cacheable) ----
COPY src/mantle/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- App code ----
COPY src/origin/ ./origin/
COPY src/kernel/ ./kernel/
COPY src/chorus/manifest.json /chorus/manifest.json
COPY build_info.json /app/build_info.json
COPY .scripts/stamp_build_time.py /app/scripts/stamp_build_time.py

RUN python /app/scripts/stamp_build_time.py /app/build_info.json

ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

EXPOSE 8080
CMD ["uvicorn", "origin.main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-graceful-shutdown", "10"]
