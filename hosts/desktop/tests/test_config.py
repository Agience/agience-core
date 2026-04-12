from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from agience_relay_host.config import DEFAULT_PERSONAS, DesktopRelayHostConfig
from agience_relay_host.host_service import DesktopHostService
from agience_relay_host.local_policy import LocalPolicy
from agience_relay_host.relay_client import RelayClient
from agience_relay_host.relay_protocol import RelayEnvelope
from agience_relay_host.relay_runtime import RelayRuntimeHandler
from agience_relay_host.relay_state import RelayState
from agience_relay_host.runtime_modes import RelayRuntimeMode
from agience_relay_host.supervisor import LocalServerSupervisor


def test_default_mapping_uses_host_mode_and_default_personas():
    config = DesktopRelayHostConfig.from_mapping({})

    assert config.mode is RelayRuntimeMode.HOST
    assert config.enabled_personas == DEFAULT_PERSONAS
    assert config.relay_server_id == "desktop-host"
    assert len(config.allowed_roots) == 1


def test_mapping_parses_authority_mode_and_persona_list():
    config = DesktopRelayHostConfig.from_mapping(
        {
            "mode": "authority",
            "authority_url": "https://agience.example.com",
            "enabled_personas": ["aria", "nexus"],
            "allowed_roots": ["."],
            "bind_port": 9191,
        }
    )

    assert config.mode is RelayRuntimeMode.AUTHORITY
    assert config.authority_url == "https://agience.example.com"
    assert config.enabled_personas == ("aria", "nexus")
    assert config.bind_port == 9191


def test_local_policy_restricts_paths_to_allowed_roots():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        allowed_file = root / "note.txt"
        allowed_file.write_text("hello", encoding="utf-8")
        policy = LocalPolicy((root,))

        result = policy.read_text(str(allowed_file))

        assert result["content"] == "hello"
        try:
            policy.resolve_allowed_path(str(root.parent / "blocked.txt"))
        except PermissionError:
            pass
        else:
            raise AssertionError("Expected path outside allowed roots to be rejected.")


def test_local_supervisor_lists_definitions_from_directory():
    with TemporaryDirectory() as temp_dir:
        definitions_dir = Path(temp_dir)
        (definitions_dir / "sample.json").write_text(
            '{"server_id":"sample","label":"Sample","command":["python","-V"]}',
            encoding="utf-8",
        )

        supervisor = LocalServerSupervisor(definitions_dir)

        assert supervisor.list_servers() == [
            {
                "server_id": "sample",
                "label": "Sample",
                "status": "stopped",
            }
        ]


def test_local_supervisor_proxies_stdio_tool_call():
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        script_path = temp_root / "mock_server.py"
        script_path.write_text(
            "import json,sys\n"
            "line=sys.stdin.readline()\n"
            "req=json.loads(line)\n"
            "if req['method']=='tools/list':\n"
            "    res={'jsonrpc':'2.0','id':req['id'],'result':{'tools':[{'name':'echo','description':'Echo tool','inputSchema':{'type':'object'}}]}}\n"
            "else:\n"
            "    res={'jsonrpc':'2.0','id':req['id'],'result':{'content':[{'type':'text','text':req['params']['arguments']['value']}]}}\n"
            "print(json.dumps(res), flush=True)\n",
            encoding="utf-8",
        )
        definitions_dir = temp_root / "definitions"
        definitions_dir.mkdir()
        (definitions_dir / "sample.json").write_text(
            json.dumps(
                {
                    "server_id": "sample",
                    "label": "Sample",
                    "command": [sys.executable, str(script_path)],
                }
            ),
            encoding="utf-8",
        )

        supervisor = LocalServerSupervisor(definitions_dir)

        tools = supervisor.list_server_tools("sample")
        result = supervisor.call_server_tool("sample", "echo", {"value": "hello"})

        assert tools[0]["name"] == "echo"
        assert result["content"][0]["text"] == "hello"


def test_relay_runtime_handler_responds_to_ping_and_host_status():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        config = DesktopRelayHostConfig.from_mapping(
            {
                "allowed_roots": [str(root)],
                "service_definitions_dir": str(root / "services"),
                "enabled_personas": ["aria"],
            }
        )
        service = DesktopHostService(config, LocalPolicy(config.allowed_roots), LocalServerSupervisor(config.service_definitions_dir))
        runtime = RelayRuntimeHandler(service)

        pong = runtime.handle_message(RelayEnvelope(type="ping", payload={"nonce": "abc"}))
        tool_result = runtime.handle_message(
            RelayEnvelope(
                type="invoke_tool",
                payload={
                    "request_id": "req-1",
                    "server_id": "desktop-host",
                    "tool_name": "host_status",
                    "arguments": {},
                },
            )
        )

        assert pong[0].type == "pong"
        assert pong[0].payload == {"nonce": "abc"}
        assert tool_result[0].type == "tool_result"
        assert tool_result[0].payload["ok"] is True
        assert tool_result[0].payload["result"]["relay_server_id"] == "desktop-host"


def test_relay_runtime_handler_routes_local_mcp_server_calls():
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        script_path = temp_root / "mock_server.py"
        script_path.write_text(
            "import json,sys\n"
            "req=json.loads(sys.stdin.readline())\n"
            "res={'jsonrpc':'2.0','id':req['id'],'result':{'ok':True,'tool':req['params']['name']}}\n"
            "print(json.dumps(res), flush=True)\n",
            encoding="utf-8",
        )
        definitions_dir = temp_root / "services"
        definitions_dir.mkdir()
        (definitions_dir / "sample.json").write_text(
            json.dumps(
                {
                    "server_id": "sample",
                    "label": "Sample",
                    "command": [sys.executable, str(script_path)],
                }
            ),
            encoding="utf-8",
        )
        config = DesktopRelayHostConfig.from_mapping(
            {
                "allowed_roots": [str(temp_root)],
                "service_definitions_dir": str(definitions_dir),
            }
        )
        service = DesktopHostService(config, LocalPolicy(config.allowed_roots), LocalServerSupervisor(config.service_definitions_dir))
        runtime = RelayRuntimeHandler(service)

        responses = runtime.handle_message(
            RelayEnvelope(
                type="invoke_tool",
                payload={
                    "request_id": "req-local",
                    "server_id": "local-mcp:sample",
                    "tool_name": "echo",
                    "arguments": {"value": "hello"},
                },
            )
        )

        assert responses[0].payload["ok"] is True
        assert responses[0].payload["result"]["tool"] == "echo"


def test_relay_client_builds_expected_websocket_url_and_enabled_state():
    config = DesktopRelayHostConfig.from_mapping(
        {
            "authority_url": "https://agience.example.com",
            "access_token": "token-123",
            "allowed_roots": ["."],
            "service_definitions_dir": "./service-definitions",
        }
    )
    service = DesktopHostService(config, LocalPolicy(config.allowed_roots), LocalServerSupervisor(config.service_definitions_dir))
    runtime = RelayRuntimeHandler(service)
    state = RelayState(config.authority_url, configured=True)
    client = RelayClient(config, runtime, state)

    assert client.enabled is True
    assert client._relay_url() == "wss://agience.example.com/relay/v1/connect"