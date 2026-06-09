"""Tests for the internal delegation-token endpoint.

`POST /internal/delegation-token` mints short-lived RFC 8693 delegation JWTs
(sub=user_id, aud=server_client_id, act.sub=server_client_id,
principal_type=delegation). Mantle calls this when proxying user requests to
first-party MCP personas. Origin owns the RSA signing keys so the issuance
must happen here.

Phase C: kernel callers (mantle, chorus) authenticate to Origin via mutual
JWT signed with their own service identity. The auth guard checks
`principal_type=="service"` and `principal_id ∈ {"mantle","chorus"}`.

Covers:
  - Auth guard rejects non-service / non-kernel callers
  - Happy-path mints a JWT and returns it under the `token` key
  - Body validation rejects unknown fields
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _patch_kernel_auth(service_name: str = "mantle"):
    """Make the request authenticate as a kernel service (mantle or chorus)."""
    from origin.routers import auth_router
    from origin.services.dependencies import AuthContext

    return patch.object(
        auth_router,
        "get_auth",
        return_value=AuthContext(
            principal_id=service_name,
            principal_type="service",
            user_id=None,
        ),
    )


def test_delegation_token_happy_path(client: TestClient, origin_app):
    # Override auth via FastAPI dependency_overrides so the kernel-service
    # guard accepts our synthetic context.
    from origin.routers import auth_router
    from origin.services.dependencies import AuthContext, get_auth

    origin_app.dependency_overrides[get_auth] = lambda: AuthContext(
        principal_id="mantle",
        principal_type="service",
        user_id=None,
    )
    try:
        with patch.object(
            auth_router,
            "origin_auth_service",
        ) as svc:
            svc.issue_delegation_token.return_value = "minted-jwt"
            resp = client.post(
                "/internal/delegation-token",
                json={
                    "server_client_id": "agience-server-aria",
                    "user_id": "user-123",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"token": "minted-jwt"}
        svc.issue_delegation_token.assert_called_once_with(
            "agience-server-aria", "user-123", 300
        )
    finally:
        origin_app.dependency_overrides.pop(get_auth, None)


def test_delegation_token_rejects_non_kernel_caller(client: TestClient, origin_app):
    """Non-kernel service tokens get 403."""
    from origin.services.dependencies import AuthContext, get_auth

    origin_app.dependency_overrides[get_auth] = lambda: AuthContext(
        principal_id="some-third-party-service",
        principal_type="service",
        user_id=None,
    )
    try:
        resp = client.post(
            "/internal/delegation-token",
            json={
                "server_client_id": "agience-server-aria",
                "user_id": "user-123",
            },
        )
        assert resp.status_code == 403
    finally:
        origin_app.dependency_overrides.pop(get_auth, None)


def test_delegation_token_rejects_user_principal(client: TestClient, origin_app):
    """User JWTs are not allowed to mint delegation tokens."""
    from origin.services.dependencies import AuthContext, get_auth

    origin_app.dependency_overrides[get_auth] = lambda: AuthContext(
        principal_id="user-123",
        principal_type="user",
        user_id="user-123",
    )
    try:
        resp = client.post(
            "/internal/delegation-token",
            json={
                "server_client_id": "agience-server-aria",
                "user_id": "user-123",
            },
        )
        assert resp.status_code == 403
    finally:
        origin_app.dependency_overrides.pop(get_auth, None)


def test_delegation_token_rejects_extra_fields(client: TestClient, origin_app):
    """The request schema forbids unknown fields (extra='forbid')."""
    from origin.services.dependencies import AuthContext, get_auth

    origin_app.dependency_overrides[get_auth] = lambda: AuthContext(
        principal_id="mantle",
        principal_type="service",
        user_id=None,
    )
    try:
        resp = client.post(
            "/internal/delegation-token",
            json={
                "server_client_id": "x",
                "user_id": "y",
                "rogue_field": "z",
            },
        )
        assert resp.status_code == 422
    finally:
        origin_app.dependency_overrides.pop(get_auth, None)

