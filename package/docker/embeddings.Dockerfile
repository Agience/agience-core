# package/docker/embeddings.Dockerfile
# Build context is the repo root (see compose: context: .)
#
# Agience embeddings server — serves the POST /embed {input:[...]} -> {vectors:[...]}
# contract consumed by kernel/embeddings.py's AgienceHTTPEmbeddings. Runs the
# BAAI/bge-m3 dense model (1024-dim, multilingual), CPU-only by default.
#
# GPU note: this image installs the CPU-only torch wheel (keeps it ~2GB
# smaller than CUDA torch). To run on a GPU, rebuild FROM a CUDA base image
# with a CUDA torch wheel and set EMBEDDINGS_DEVICE=cuda.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/app/.hf

WORKDIR /app

# ---- System deps ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# ---- Torch (CPU-only wheel — avoids pulling ~2GB of CUDA libraries) ----
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# ---- Python deps (cacheable) ----
COPY src/embeddings/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- App code ----
COPY src/embeddings/ ./embeddings/
COPY build_info.json /app/build_info.json

# ---- Bake the model into the image: no runtime download, works fully offline,
#      and keeps chunk plaintext from ever leaving the deployment boundary. ----
ARG EMBEDDINGS_MODEL=BAAI/bge-m3
ENV EMBEDDINGS_MODEL=${EMBEDDINGS_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDINGS_MODEL}')"

# Runtime stays offline — the model is already cached in the image above.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

EXPOSE 8083
CMD ["uvicorn", "embeddings.main:app", "--host", "0.0.0.0", "--port", "8083", "--timeout-graceful-shutdown", "10"]
