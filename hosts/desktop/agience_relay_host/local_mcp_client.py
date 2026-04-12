from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .supervisor import LocalServerDefinition

log = logging.getLogger("agience-relay-desktop.local-mcp")


class LocalMCPDefinitionClient:
    def __init__(self, definition: LocalServerDefinition):
        self.definition = definition

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._send_request("tools/list")
        tools = result.get("tools", [])
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {},
            },
        )

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        env = os.environ.copy()
        env.update(self.definition.env or {})
        process = subprocess.Popen(
            self.definition.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.definition.cwd) if self.definition.cwd else None,
            env=env,
            text=True,
        )
        try:
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or {},
            }
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            if not response_line:
                stderr = ""
                if process.stderr is not None:
                    stderr = process.stderr.read()
                raise RuntimeError(stderr.strip() or "No response from local MCP server")
            response = json.loads(response_line)
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return dict(response.get("result") or {})
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)