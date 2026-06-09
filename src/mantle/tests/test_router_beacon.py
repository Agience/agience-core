"""Router tests for /internal/beacon/* — the gated Beacon callback surface.

Covers the `beacon` capability gate (403 without it), the anchorset read
(200 / 409), and profile apply+read. `has_feature` is patched per test so the
gate behavior is deterministic regardless of the billing-enforcement config.
"""

from unittest.mock import patch

import numpy as np
import pytest

_HAS_FEATURE = "routers.beacon_router.gate_service.has_feature"
_LIVE_ANCHORSET = "search.anchors.get_live_anchorset"


class _Anchor:
    def __init__(self, label, aid):
        self.label = label
        self.anchor_id = aid


class _FakeAnchorSet:
    model_id = "hf:BAAI/bge-m3@1.0"
    dim = 3

    def __init__(self):
        self.matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        self.anchors = [_Anchor("alpha", "id-a"), _Anchor("beta", "id-b")]

    def __len__(self):
        return 2


@pytest.mark.asyncio
async def test_anchorset_returns_matrix_when_entitled(client):
    with patch(_HAS_FEATURE, return_value=True), \
         patch(_LIVE_ANCHORSET, return_value=_FakeAnchorSet()):
        resp = await client.get("/internal/beacon/anchorset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["labels"] == ["alpha", "beta"]
    assert body["model_id"] == "hf:BAAI/bge-m3@1.0"
    assert len(body["matrix"]) == 2


@pytest.mark.asyncio
async def test_anchorset_403_without_beacon_entitlement(client):
    with patch(_HAS_FEATURE, return_value=False):
        resp = await client.get("/internal/beacon/anchorset")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_anchorset_409_when_no_live_anchorset(client):
    with patch(_HAS_FEATURE, return_value=True), patch(_LIVE_ANCHORSET, return_value=None):
        resp = await client.get("/internal/beacon/anchorset")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_profile_apply_then_read(client):
    profile = {"model_id": "m", "thresholds": {"t_low": 0.3, "t_high": 0.7, "concentration": 0.2}}
    with patch(_HAS_FEATURE, return_value=True):
        applied = await client.post("/internal/beacon/profile", json=profile)
        assert applied.status_code == 204
        got = await client.get("/internal/beacon/profile")
    assert got.status_code == 200
    assert got.json()["thresholds"]["concentration"] == 0.2
