"""Origin pytest fixtures.

DB-dependent tests are skipped unless `ORIGIN_TEST_DATABASE_URL` is set —
typically pointing at a Postgres testcontainer or the local dev `identity`
service. JWT/JWKS tests stub key loading via tmp PEM files so they don't
need a running Origin container.
"""

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def jwt_keypair(tmp_path_factory) -> Path:
    """Materialize all Origin key files in a tmp dir for the test session.

    Origin's lifespan reads several files: jwt private/public PEMs, encryption
    key (Fernet), platform internal secret, inbound nonce secret, identity
    password. We write minimal-but-real values so lifespan completes cleanly.
    """
    from cryptography.fernet import Fernet
    import secrets as _secrets

    keys_dir = tmp_path_factory.mktemp("origin_keys")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (keys_dir / "origin.private.pem").write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (keys_dir / "origin.public.pem").write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (keys_dir / "encryption.key").write_text(Fernet.generate_key().decode())
    (keys_dir / "platform_internal.secret").write_text(_secrets.token_urlsafe(48))
    (keys_dir / "inbound_nonce.secret").write_text(_secrets.token_urlsafe(48))
    return keys_dir


@pytest.fixture
def origin_app(monkeypatch, jwt_keypair):
    """Build a fresh Origin FastAPI app with stubbed key paths.

    Migrations are skipped via ORIGIN_SKIP_MIGRATIONS=1. The DB engine is
    initialized against an in-memory SQLite (matches production engine).
    """
    monkeypatch.setenv("KEYS_DIR", str(jwt_keypair))
    monkeypatch.setenv("ORIGIN_SKIP_MIGRATIONS", "1")
    monkeypatch.setenv("ORIGIN_SKIP_DB_SETTINGS", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    # Re-import after env vars are set so module-level Path resolution picks them up.
    import importlib
    import sys

    import kernel.config as _cfg
    import kernel.key_manager as _km
    import origin.db.session as _session
    import origin.main as _origin_main

    importlib.reload(_cfg)
    importlib.reload(_km)
    importlib.reload(_session)

    # Refresh anything routing or dependency-related that may already be in
    # sys.modules with stale references. test_auth_foundation reloads
    # `origin.services.dependencies`, which detaches `get_auth` from any
    # previously-loaded router module. Without this sweep, dependency_overrides
    # set on the rebuilt app never matches the stale `get_auth` symbol the
    # routers still reference.
    for mod_name in [
        "origin.services.auth_service",
        "origin.services.auth_verifier",
        "origin.services.dependencies",
        "origin.routers.auth_router",
        "origin.routers.api_keys_router",
        "origin.routers.grants_router",
        "origin.routers.passkey_router",
        "origin.routers.otp_router",
        "origin.routers.platform_router",
        "origin.routers.server_credentials_router",
        "origin.routers.setup_router",
    ]:
        mod = sys.modules.get(mod_name)
        if mod is not None:
            importlib.reload(mod)

    importlib.reload(_origin_main)

    return _origin_main.app


@pytest.fixture
def client(origin_app):
    with TestClient(origin_app) as c:
        yield c
