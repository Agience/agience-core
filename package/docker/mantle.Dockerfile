# package/docker/mantle.Dockerfile
# Build context is the repo root (see compose: context: .)
#
# Mantle runs the FastAPI app at src/mantle/main.py on port 8081.
#
# Layout note: Mantle's modules import bare (`from db.arango import …`,
# `from kernel import config`) and several paths resolve *relative to the repo*:
#   - config.BASE_DIR keys off a parent dir named `src`  (kernel/config.py)
#   - types_service._repo_root() uses parents[3]          (services/types_service.py)
#   - the seed loader reads config.BASE_DIR/package/seeds (seed_provisioning/loader.py)
# To keep every one of those resolvers correct, the image MIRRORS the repo
# layout under /app (src/… and package/…) and puts src/mantle + src on
# PYTHONPATH, rather than flattening source into /app like the old
# flare.Dockerfile did (that flattening silently broke these path resolvers).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src/mantle:/app/src

WORKDIR /app

# ---- System deps ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps (cacheable) ----
COPY src/mantle/requirements.txt ./src/mantle/requirements.txt
RUN pip install --no-cache-dir -r src/mantle/requirements.txt

# ---- App code (mirror repo layout so path resolvers match local dev) ----
COPY src/kernel/ ./src/kernel/
COPY src/mantle/ ./src/mantle/
COPY package/types/ ./package/types/
# Server-owned content-type definitions live under src/chorus/<persona>/ui/.
# types_service walks these (get_types_roots → _default_server_ui_roots), and the
# mcp-server type's operations (resources_read / resources_import) are declared
# there — NOT in package/types. Without the chorus ui/ trees, mantle's operation
# dispatch can't resolve them → 404 on every `ui://` resource read. mantle never
# imports chorus code; it only reads the ui/ type.json + view.html files.
COPY src/chorus/ ./src/chorus/
# Declarative platform/user/admin seed tree — loaded on first boot from
# config.BASE_DIR/package/seeds (= /app/package/seeds here). Carrying it in
# the image is the fix for the seeds-missing-in-image bug.
COPY package/seeds/ ./package/seeds/
# Server topology manifest — server_registry reads the /chorus/manifest.json
# Docker fallback path (same as origin's kernel_servers).
COPY src/chorus/manifest.json /chorus/manifest.json
COPY build_info.json ./build_info.json
COPY .scripts/stamp_build_time.py ./scripts/stamp_build_time.py

RUN python ./scripts/stamp_build_time.py ./build_info.json

ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app/src/mantle
EXPOSE 8081
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081", "--timeout-graceful-shutdown", "10"]
