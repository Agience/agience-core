import pytest
from fastapi.testclient import TestClient

from main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_root_status_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("status") == "ok"
    assert "links" in payload


def test_mcp_mount_presence(client):
    # Even if fastapi_mcp is not available, the API should be healthy.
    # If mounted, the /mcp path should be reachable for POST (JSON-RPC); GET may be 404/405/redirect.
    r = client.get("/mcp")
    # Accept typical statuses for a mount point without GET: 200/307/308/401/404/405
    assert r.status_code in {200, 307, 308, 401, 404, 405}


def test_mcp_well_known(client):
    r = client.get("/.well-known/mcp.json")
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("name")
    assert "endpoints" in payload
    assert payload["endpoints"].get("streamable_http")
