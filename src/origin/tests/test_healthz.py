def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version_present(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert "build_time" in body
