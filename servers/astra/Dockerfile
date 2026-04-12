FROM python:3.12-slim

WORKDIR /app

# ffmpeg is required for HLS->MP4 muxing on stream finalization.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY stream_routes.py .
COPY ui/ ui/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Runtime config — override via -e or compose env_file
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8087 \
    LOG_LEVEL=INFO

EXPOSE 8087

ENTRYPOINT ["/app/entrypoint.sh"]
