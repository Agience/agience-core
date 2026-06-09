"""Tests for `POST /auth/bootstrap/claim` — Phase B first-operator bootstrap.

Covers:
  - Happy path: valid token creates person + can_admin grant + sets setup_complete
  - Idempotency: second call after success returns 410
  - Wrong token: 401
  - Token already cleared in manifest: 410
  - Manifest absent: 503
  - Password too short: 422
  - Email collision: 409
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


def _seed_authority_manifest(keys_dir: Path, *, token: str = "the-secret-token") -> dict:
    """Write a minimal authority.manifest.json to KEYS_DIR. Returns the manifest dict."""
    manifest = {
        "artifact_id": "11111111-2222-3333-4444-555555555555",
        "content_type": "application/vnd.agience.authority+json",
        "schema_version": 1,
        "issuer": "https://platform.test",
        "trust_anchors": {},
        "bootstrap_token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    (keys_dir / "authority.manifest.json").write_text(json.dumps(manifest, indent=2))
    # Also drop a mantle/origin/chorus key for service_identity tests in this conftest.
    for name in ("origin", "mantle", "chorus"):
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        from cryptography.hazmat.primitives import serialization
        (keys_dir / f"{name}.private.pem").write_bytes(
            priv.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    return manifest


@pytest.fixture
def with_authority(jwt_keypair):
    """Make `core.authority_trust` see a fresh in-memory manifest."""
    from kernel import authority_trust
    authority_trust.reset_authority_manifest_for_tests()
    yield _seed_authority_manifest(jwt_keypair, token="the-secret-token")
    authority_trust.reset_authority_manifest_for_tests()


@pytest.fixture(autouse=True)
def _ensure_db_tables(client):
    """ORIGIN_SKIP_MIGRATIONS is set in conftest, so Postgres tables don't exist
    in the in-memory SQLite. Create them via SQLAlchemy metadata for these tests.
    Depends on `client` so the app's lifespan has run and `init_engine()` has
    been called. Also clears the in-memory platform_settings cache between
    tests (module-level singleton would otherwise leak setup_complete=true).
    """
    # Importing models registers them on Base.metadata.
    from origin import models  # noqa: F401  (side-effect: registers models)
    from origin.db.base import Base
    from origin.db.session import get_engine
    from origin.services.platform_settings_service import settings as _settings

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _settings._values.clear()
    _settings._secrets.clear()
    yield
    _settings._values.clear()
    _settings._secrets.clear()
    Base.metadata.drop_all(bind=engine)


def test_claim_happy_path(client: TestClient, origin_app, with_authority):
    """Valid token creates the operator + grant + flips setup_complete."""
    resp = client.post(
        "/auth/bootstrap/claim",
        json={
            "token": "the-secret-token",
            "email": "operator@example.com",
            "name": "Op",
            "password": "averylongpassword",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    operator_id = body["person_id"]
    assert operator_id

    # Person row exists
    from origin.db.session import SessionLocal
    from origin.services import person_service
    from origin.db import grants as db_grants
    from origin.services.platform_settings_service import settings as platform_settings

    with SessionLocal() as db:
        platform_settings.load_all(db)
        person = person_service.get_user_by_id(db, operator_id)
        assert person is not None
        assert person.email == "operator@example.com"
        assert person.name == "Op"

        # can_admin grant on the authority artifact
        grants = db_grants.get_active_for_principal_resource(
            db,
            grantee_id=operator_id,
            resource_id=with_authority["artifact_id"],
        )
        assert len(grants) == 1
        g = grants[0]
        assert g.can_admin is True
        assert g.can_read is True
        assert g.can_update is True
        assert g.effect == "allow"

        # setup_complete flag
        assert (platform_settings.get("platform.setup_complete") or "").lower() == "true"
        assert platform_settings.get("platform.operator_id") == operator_id


def test_claim_rejects_wrong_token(client: TestClient, origin_app, with_authority):
    resp = client.post(
        "/auth/bootstrap/claim",
        json={"token": "definitely-not-the-real-token"},
    )
    assert resp.status_code == 401
    assert "Invalid bootstrap token" in resp.json()["detail"]


def test_claim_idempotent_410(client: TestClient, origin_app, with_authority):
    """A successful claim flips setup_complete; second attempt returns 410."""
    r1 = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token"},
    )
    assert r1.status_code == 200, r1.text

    r2 = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token"},
    )
    assert r2.status_code == 410
    assert "already completed" in r2.json()["detail"].lower()


def test_claim_410_when_manifest_hash_cleared(client: TestClient, origin_app, jwt_keypair):
    """Manifest with bootstrap_token_hash=null returns 410 before token check."""
    from kernel import authority_trust
    authority_trust.reset_authority_manifest_for_tests()
    manifest = {
        "artifact_id": "11111111-2222-3333-4444-555555555555",
        "content_type": "application/vnd.agience.authority+json",
        "schema_version": 1,
        "issuer": "https://platform.test",
        "trust_anchors": {},
        "bootstrap_token_hash": None,
    }
    (jwt_keypair / "authority.manifest.json").write_text(json.dumps(manifest))
    try:
        resp = client.post(
            "/auth/bootstrap/claim",
            json={"token": "anything"},
        )
        assert resp.status_code == 410
        assert "already consumed" in resp.json()["detail"].lower()
    finally:
        authority_trust.reset_authority_manifest_for_tests()


def test_claim_503_when_manifest_missing(client: TestClient, origin_app, jwt_keypair):
    """No manifest at all → 503 (operator must re-run init)."""
    from kernel import authority_trust
    authority_trust.reset_authority_manifest_for_tests()

    manifest_path = jwt_keypair / "authority.manifest.json"
    saved = manifest_path.read_bytes() if manifest_path.exists() else None
    if manifest_path.exists():
        manifest_path.unlink()
    try:
        resp = client.post(
            "/auth/bootstrap/claim",
            json={"token": "x"},
        )
        assert resp.status_code == 503
        assert "manifest not found" in resp.json()["detail"].lower()
    finally:
        if saved is not None:
            manifest_path.write_bytes(saved)
        authority_trust.reset_authority_manifest_for_tests()


def test_claim_password_too_short_422(client: TestClient, origin_app, with_authority):
    resp = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token", "password": "short"},
    )
    assert resp.status_code == 422
    assert "12 characters" in resp.json()["detail"]


def test_claim_passwordless_operator_succeeds(client: TestClient, origin_app, with_authority):
    """Operator may skip password — they'll add one later via OAuth/passkey/reset."""
    resp = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token", "email": "op@example.com"},
    )
    assert resp.status_code == 200, resp.text

    from origin.db.session import SessionLocal
    from origin.services import person_service

    with SessionLocal() as db:
        person = person_service.get_user_by_email(db, "op@example.com")
        assert person is not None
        assert person.password_hash is None


def test_claim_email_collision_409(client: TestClient, origin_app, with_authority):
    """Pre-existing person with that email → 409. (Setup hasn't been claimed yet
    at this point — we manually seed a person to simulate the collision.)"""
    from origin.db.session import SessionLocal
    from origin.db import persons as db_persons

    with SessionLocal() as db:
        db_persons.create(
            db,
            {"email": "taken@example.com", "name": "Pre-existing", "username": "pre"},
        )
        db.commit()

    resp = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token", "email": "taken@example.com"},
    )
    assert resp.status_code == 409


def test_claim_rejects_extra_fields(client: TestClient, origin_app, with_authority):
    """Body schema is strict — unknown fields rejected."""
    resp = client.post(
        "/auth/bootstrap/claim",
        json={"token": "the-secret-token", "rogue": "field"},
    )
    assert resp.status_code == 422

