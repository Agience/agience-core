"""Startup smoke test — verifies server_startup() completes without error."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Resolve paths absolutely so they work regardless of how pytest sets __file__.
_HERE = Path(__file__).resolve().parent  # .../servers/<name>/tests/
sys.path.insert(0, str(_HERE.parent.parent / "_shared"))  # .../servers/_shared
sys.path.insert(0, str(_HERE.parent))  # .../servers/<name>/

import server as _server


@pytest.mark.asyncio
async def test_server_startup_calls_auth_startup():
    """server_startup() must delegate to _auth.startup() and not raise."""
    with patch.object(_server._auth, "startup", new_callable=AsyncMock) as mock_startup:
        await _server.server_startup()
    mock_startup.assert_called_once_with(_server._exchange_token)
