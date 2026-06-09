from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .local_mcp_client import LocalMCPDefinitionClient


@dataclass(frozen=True)
class LocalServerDefinition:
    server_id: str
    label: str
    command: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None


class LocalServerSupervisor:
    def __init__(self, definitions_dir: Path):
        self.definitions_dir = definitions_dir
        self._definitions = self._load_definitions(definitions_dir)
        self._processes: dict[str, subprocess.Popen[str]] = {}

    def list_servers(self) -> list[dict[str, str]]:
        return [
            {
                "server_id": server_id,
                "label": definition.label,
                "status": self.status(server_id),
            }
            for server_id, definition in sorted(self._definitions.items())
        ]

    def status(self, server_id: str) -> str:
        process = self._processes.get(server_id)
        if process is None:
            return "stopped"
        if process.poll() is None:
            return "running"
        self._processes.pop(server_id, None)
        return "stopped"

    def start_server(self, server_id: str) -> dict[str, str]:
        definition = self._definitions.get(server_id)
        if definition is None:
            raise KeyError(f"Unknown local server '{server_id}'.")
        if self.status(server_id) == "running":
            return {"server_id": server_id, "status": "running"}

        env = os.environ.copy()
        env.update(definition.env or {})
        process = subprocess.Popen(
            definition.command,
            cwd=str(definition.cwd) if definition.cwd else None,
            env=env,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes[server_id] = process
        return {"server_id": server_id, "status": self.status(server_id)}

    def stop_server(self, server_id: str) -> dict[str, str]:
        process = self._processes.get(server_id)
        if process is None:
            return {"server_id": server_id, "status": "stopped"}
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._processes.pop(server_id, None)
        return {"server_id": server_id, "status": "stopped"}

    def get_definition(self, server_id: str) -> LocalServerDefinition:
        definition = self._definitions.get(server_id)
        if definition is None:
            raise KeyError(f"Unknown local server '{server_id}'.")
        return definition

    def list_server_tools(self, server_id: str) -> list[dict[str, object]]:
        definition = self.get_definition(server_id)
        client = LocalMCPDefinitionClient(definition)
        return client.list_tools()

    def call_server_tool(self, server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        definition = self.get_definition(server_id)
        client = LocalMCPDefinitionClient(definition)
        return client.call_tool(tool_name, arguments)

    def local_server_manifest(self) -> list[dict[str, object]]:
        manifest: list[dict[str, object]] = []
        for server in self.list_servers():
            server_id = str(server["server_id"])
            tools: list[dict[str, object]] = []
            try:
                tools = self.list_server_tools(server_id)
            except Exception:
                tools = []
            manifest.append(
                {
                    "server_id": f"local-mcp:{server_id}",
                    "label": server["label"],
                    "status": server["status"],
                    "tools": tools,
                }
            )
        return manifest

    @staticmethod
    def _load_definitions(definitions_dir: Path) -> dict[str, LocalServerDefinition]:
        if not definitions_dir.exists():
            return {}
        definitions: dict[str, LocalServerDefinition] = {}
        for path in sorted(definitions_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            definitions[payload["server_id"]] = LocalServerDefinition(
                server_id=str(payload["server_id"]),
                label=str(payload.get("label") or payload["server_id"]),
                command=[str(item) for item in payload["command"]],
                cwd=Path(str(payload["cwd"])).expanduser().resolve() if payload.get("cwd") else None,
                env={str(key): str(value) for key, value in (payload.get("env") or {}).items()} or None,
            )
        return definitions