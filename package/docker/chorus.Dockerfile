# /package/docker/chorus.Dockerfile
# Build context is the repo root (see compose: context: ..)
#
# Chorus runs the unified MCP host at src/chorus/server.py on port 8082,
# exposing all eight persona servers under /<persona>/mcp.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# ---- System deps ----
# - build-essential / gcc: native wheels (cryptography, etc.)
# - ffmpeg: stream/transcription pipeline (astra)
# - curl / git / ca-certificates: gh CLI install + iris copilot extension
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential gcc \
        ffmpeg \
        curl git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# ---- GitHub CLI (iris copilot tools) ----
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ---- Python deps (cacheable) ----
COPY src/chorus/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ---- App code ----
COPY src/chorus/ ./
COPY src/kernel/ ./kernel/
COPY build_info.json /app/build_info.json
COPY .scripts/stamp_build_time.py /app/scripts/stamp_build_time.py

RUN python /app/scripts/stamp_build_time.py /app/build_info.json

# ---- Optional: GitHub Copilot CLI extension for iris ----
ARG GH_TOKEN
RUN if [ -n "$GH_TOKEN" ]; then \
        gh extension install github/gh-copilot --force \
        && ln -s "$(find /root/.local/share/gh/extensions -name 'gh-copilot' -type f 2>/dev/null | head -1)" \
                 /usr/local/bin/copilot 2>/dev/null || true; \
    else \
        echo "GH_TOKEN not set — skipping GitHub Copilot extension install"; \
    fi

ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

# ---- Runtime config ----
ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8082 \
    LOG_LEVEL=INFO \
    COPILOT_CWD=/workspace

EXPOSE 8082

# Mount host project directory here for iris/Copilot to operate on
VOLUME ["/workspace"]

CMD ["python", "server.py"]
