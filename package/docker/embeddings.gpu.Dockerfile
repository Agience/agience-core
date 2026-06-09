# package/docker/embeddings.gpu.Dockerfile
# GPU variant of the Agience embeddings server (bge-m3 on CUDA) — for RunPod.
# Build context is the repo root (docker build -f package/docker/embeddings.gpu.Dockerfile .)
#
# Same FastAPI app + /embed contract as the CPU image; the only differences are
# a CUDA base (torch with GPU support, provided by the pytorch base image) and
# EMBEDDINGS_DEVICE=cuda. Expose port 8083 over HTTP on RunPod and point
# Mantle's EMBEDDINGS_URI at the pod's proxy URL.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/app/.hf \
    EMBEDDINGS_DEVICE=cuda

WORKDIR /app

# ---- Python deps (torch + CUDA already in the base image) ----
COPY src/embeddings/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- App code ----
COPY src/embeddings/ ./embeddings/
COPY build_info.json /app/build_info.json

# ---- Bake the model into the image: no runtime download, works offline.
#      (For faster cold starts on RunPod you can instead mount a network volume
#      at /app/.hf and drop this RUN — the first request then downloads once.) ----
ARG EMBEDDINGS_MODEL=BAAI/bge-m3
ENV EMBEDDINGS_MODEL=${EMBEDDINGS_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDINGS_MODEL}')"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

EXPOSE 8083
CMD ["uvicorn", "embeddings.main:app", "--host", "0.0.0.0", "--port", "8083", "--timeout-graceful-shutdown", "10"]
