FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# Runtime config — override via -e or compose env_file
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8083 \
    LOG_LEVEL=INFO

EXPOSE 8083

CMD ["python", "server.py"]
