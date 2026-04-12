FROM python:3.12-slim

# ── System deps ─────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI ──────────────────────────────────────────────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub Copilot CLI extension ─────────────────────────────────────────────
# GH_TOKEN is optional at build time. If not provided, the Copilot extension
# is skipped and nexus runs without it (tools requiring Copilot will be unavailable).
ARG GH_TOKEN
RUN if [ -n "$GH_TOKEN" ]; then \
        gh extension install github/gh-copilot --force; \
        ln -s "$(find /root/.local/share/gh/extensions -name 'gh-copilot' -type f 2>/dev/null | head -1)" \
              /usr/local/bin/copilot 2>/dev/null || true; \
    else \
        echo "GH_TOKEN not set — skipping GitHub Copilot extension install"; \
    fi

# ── Python app ───────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# ── Runtime config ───────────────────────────────────────────────────────────
# Override at `docker run` time via -e or compose env_file
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8086 \
    LOG_LEVEL=INFO \
    COPILOT_CWD=/workspace

EXPOSE 8086

# Mount host project directory here for Copilot to operate on
VOLUME ["/workspace"]

CMD ["python", "server.py"]
