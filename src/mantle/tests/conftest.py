import uuid

import pytest
from typing import AsyncGenerator
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

import bcrypt as _bcrypt
import kernel.config as _cfg
from entities.person import Person
from services.bootstrap_types import (
    ALL_PLATFORM_COLLECTION_SLUGS,
    AUTHORITY_ARTIFACT_SLUG,
    HOST_ARTIFACT_SLUG,
    AGENCY_ARTIFACT_SLUG,
    AGENT_ARTIFACT_SLUG_PREFIX,
    PLATFORM_AGENT_SLUGS,
)
from services.platform_topology import register_id
from services.dependencies import (
    get_auth,
    get_person,
    get_end_user_claims,
    AuthContext,
)
from services.dependencies import get_arango_db
from main import app
from unittest.mock import MagicMock
import main as _main_module

# ---------------------------------------------------------------------------
# Fast crypto: reduce bcrypt cost and PBKDF2 iterations so tests don't spend
# seconds on real key-stretching.  Applied before any test module imports.
# ---------------------------------------------------------------------------
_orig_gensalt = _bcrypt.gensalt
_bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _orig_gensalt(rounds=4, prefix=prefix)
_cfg.PASSWORD_PBKDF2_ITERS = 1000

# Disable setup mode for all tests — the middleware blocks all non-setup routes
# when _setup_mode is True (the default at import time).
_main_module._setup_mode = False

_TEST_PLATFORM_IDS: dict[str, str] = {}

def _ensure_platform_registry():
    """Populate the platform topology registry with stable test UUIDs."""
    if not _TEST_PLATFORM_IDS:
        for slug in ALL_PLATFORM_COLLECTION_SLUGS:
            _TEST_PLATFORM_IDS[slug] = str(uuid.uuid4())
        for slug in [AUTHORITY_ARTIFACT_SLUG, HOST_ARTIFACT_SLUG, AGENCY_ARTIFACT_SLUG]:
            _TEST_PLATFORM_IDS[slug] = str(uuid.uuid4())
        for agent_slug in PLATFORM_AGENT_SLUGS:
            _TEST_PLATFORM_IDS[f"{AGENT_ARTIFACT_SLUG_PREFIX}{agent_slug}"] = str(uuid.uuid4())
    for slug, uid in _TEST_PLATFORM_IDS.items():
        register_id(slug, uid)

@pytest.fixture(autouse=True)
def _seed_platform_registry():
    """Ensure platform topology registry is populated before every test."""
    _ensure_platform_registry()

@pytest.fixture(autouse=True, scope="session")
def _init_test_encryption_key():
    """Initialize the encryption key with a test value so secrets_service works in tests."""
    from cryptography.fernet import Fernet
    import kernel.key_manager as _km
    _km._encryption_key = Fernet.generate_key().decode()


@pytest.fixture(autouse=True, scope="session")
def _init_test_jwt_keys():
    """
    Generate an in-memory RSA key pair so create_jwt_token / verify_token work
    in tests without key files on disk.  Mirrors what the init container does at
    runtime so tests never need to call init_jwt_keys() directly.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import kernel.key_manager as _km

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    _km._private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    _km._public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    _km._key_id = "test"


@pytest.fixture(scope="session")
def _test_trust_keys():
    """Generate origin/mantle/chorus keypairs once per test session (expensive)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    return {
        name: rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for name in ("origin", "mantle", "chorus")
    }


@pytest.fixture(autouse=True)
def _install_test_service_identity_and_authority(_test_trust_keys):
    """Phase C: install in-memory service identity (`mantle`) + authority manifest
    before every test. Function-scoped because individual test files
    (test_service_identity, test_authority_trust) reset module state to
    exercise their own setup paths — this fixture restores the canonical
    test identity afterwards.
    """
    import base64
    from kernel import service_identity, authority_trust

    def _b64url(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    def _public_jwk(public_key, kid: str) -> dict:
        nums = public_key.public_numbers()
        n = nums.n.to_bytes((nums.n.bit_length() + 7) // 8, "big")
        e = nums.e.to_bytes((nums.e.bit_length() + 7) // 8, "big")
        return {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": kid,
                "n": _b64url(n), "e": _b64url(e)}

    keys = _test_trust_keys

    service_identity.reset_service_identity_for_tests()
    service_identity._loaded = service_identity.ServiceIdentity(
        name="mantle", kid="mantle-1", private_key=keys["mantle"]
    )

    authority_trust.reset_authority_manifest_for_tests()
    raw = {
        "artifact_id": "test-authority",
        "content_type": "application/vnd.agience.authority+json",
        "schema_version": 1,
        "issuer": "https://platform.test",
        "trust_anchors": {
            name: {"uri": f"http://{name}:8080",
                   "jwks": {"keys": [_public_jwk(keys[name].public_key(), f"{name}-1")]}}
            for name in ("origin", "mantle", "chorus")
        },
        "bootstrap_token_hash": None,
    }
    authority_trust._manifest = authority_trust.AuthorityManifest(
        issuer=raw["issuer"],
        trust_anchors=raw["trust_anchors"],
        bootstrap_token_hash=raw["bootstrap_token_hash"],
        artifact_id=raw["artifact_id"],
        raw=raw,
    )
    yield

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture(autouse=True)
def override_dependencies():
    def _unified_auth():
        return AuthContext(
            principal_id="user-123",
            principal_type="user",
            user_id="user-123",
        )

    def _person():
        return Person(
            id="user-123",
            email="test@example.com",
            name="Test User",
            picture="https://example.com/avatar.png",
        )

    def _user_claims():
        return {"sub": "user-123", "client_id": "agience-frontend"}

    def _arango_db():
        yield MagicMock()

    app.dependency_overrides[get_auth] = _unified_auth
    app.dependency_overrides[get_person] = _person
    app.dependency_overrides[get_end_user_claims] = _user_claims
    app.dependency_overrides[get_arango_db] = _arango_db

    yield
    app.dependency_overrides.clear()

@pytest.fixture
def mock_user():
    return Person(
        id="user-123",
        email="test@example.com",
        name="Test User",
        picture="https://example.com/avatar.png"
    )


