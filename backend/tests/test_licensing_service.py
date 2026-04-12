from services import licensing_service
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _base_license() -> dict:
    return {
        "schema_version": "1",
        "license_id": "lic_123",
        "entitlement_id": "ent_123",
        "account_id": "acct_123",
        "issued_at": "2026-03-07T00:00:00Z",
        "not_before": "2026-03-07T00:00:00Z",
        "expires_at": "2027-03-07T00:00:00Z",
        "product": {
            "policy_id": "standard-hosted-core",
            "runtime_roles": ["standard"],
            "distribution_profiles": ["standard"],
            "product_surface": "core-app",
        },
        "controls": {
            "offline_allowed": True,
            "offline_lease_days": 30,
            "require_activation": True,
            "require_reporting": True,
            "enforcement_profile": "commercial-self-host",
        },
        "entitlements": ["host_standard"],
        "signature": {
            "alg": "EdDSA",
            "kid": "lic-2026-q1",
            "value": "sig",
        },
    }


def test_standard_profile_allows_matching_license():
    result = licensing_service.evaluate_profile_license_compatibility(
        "standard",
        _base_license(),
    )

    assert result.allowed is True
    assert result.issues == []
    assert result.control_class == "commercial-self-host"


def test_white_label_profile_requires_white_label_entitlement():
    payload = _base_license()
    payload["product"] = {
        "policy_id": "white-label-core-app",
        "runtime_roles": ["standard"],
        "distribution_profiles": ["white-label-core"],
        "product_surface": "core-app",
    }

    result = licensing_service.evaluate_profile_license_compatibility(
        "white-label-core",
        payload,
    )

    assert result.allowed is False
    assert any(issue.code == "missing_entitlements" for issue in result.issues)


def test_relay_profile_rejects_standard_runtime_license():
    payload = _base_license()
    payload["product"] = {
        "policy_id": "relay-desktop",
        "runtime_roles": ["standard"],
        "distribution_profiles": ["relay-desktop"],
        "product_surface": "relay-client",
    }
    payload["entitlements"] = ["relay_distribution"]

    result = licensing_service.evaluate_profile_license_compatibility(
        "relay-desktop",
        payload,
    )

    assert result.allowed is False
    assert any(issue.code == "runtime_role_mismatch" for issue in result.issues)


def test_license_parser_allows_future_extensions():
    payload = _base_license()
    payload["attributes"] = {
        "future_policy_toggle": "enabled",
    }
    payload["extensions"] = {
        "issuer_specific": {
            "channel": "partner-a",
        }
    }

    parsed = licensing_service.parse_license_artifact(payload)

    assert parsed.attributes["future_policy_toggle"] == "enabled"
    assert parsed.extensions["issuer_specific"]["channel"] == "partner-a"


def test_activation_lease_parser_allows_optional_runtime_ids():
    payload = {
        "schema_version": "1",
        "lease_id": "lease_123",
        "license_id": "lic_123",
        "install_id": "inst_123",
        "runtime_role": "relay",
        "profile": "relay-desktop",
        "issued_at": "2026-03-07T00:00:00Z",
        "not_before": "2026-03-07T00:00:00Z",
        "lease_expires_at": "2026-04-07T00:00:00Z",
        "device_id": "dev_123",
        "signature": {
            "alg": "EdDSA",
            "kid": "lic-2026-q1",
            "value": "sig",
        },
        "extensions": {
            "grace_reason": "manual-offline-renewal"
        }
    }

    parsed = licensing_service.parse_activation_lease(payload)

    assert parsed.device_id == "dev_123"
    assert parsed.extensions["grace_reason"] == "manual-offline-renewal"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_verify_license_artifact_signature_accepts_valid_signature():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()

    payload = _base_license()
    payload["signature"] = {
        "alg": "EdDSA",
        "kid": "lic-2026-q1",
        "value": "",
    }

    canonical = licensing_service._canonicalize_signed_payload(payload)
    payload["signature"]["value"] = _b64url(private_key.sign(canonical))

    result = licensing_service.verify_license_artifact(
        payload,
        trust_anchors={
            "keys": [
                {
                    "kid": "lic-2026-q1",
                    "alg": "EdDSA",
                    "public_key": _b64url(public_key),
                }
            ]
        },
    )

    assert result.valid is True
    assert result.key_id == "lic-2026-q1"


def test_issue_license_artifact_returns_signed_payload():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()

    payload = licensing_service.issue_license_artifact(
        license_id="lic_issued",
        entitlement_id="ent_issued",
        account_id="acct_issued",
        issued_at="2026-03-07T00:00:00Z",
        not_before="2026-03-07T00:00:00Z",
        expires_at="2027-03-07T00:00:00Z",
        policy_id="standard-hosted-core",
        runtime_roles=["standard"],
        distribution_profiles=["standard"],
        product_surface="core-app",
        entitlements=["host_standard"],
        private_key=private_key,
        signing_key_id="lic-2026-q1",
    )

    assert payload["signature"]["kid"] == "lic-2026-q1"
    assert payload["license_id"] == "lic_issued"

    result = licensing_service.verify_license_artifact(
        payload,
        trust_anchors={
            "keys": [
                {
                    "kid": "lic-2026-q1",
                    "alg": "EdDSA",
                    "public_key": _b64url(public_key),
                }
            ]
        },
    )

    assert result.valid is True


def test_issue_activation_lease_returns_signed_payload():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()

    payload = licensing_service.issue_activation_lease(
        lease_id="lease_issued",
        license_id="lic_issued",
        install_id="inst_issued",
        runtime_role="standard",
        issued_at="2026-03-07T00:00:00Z",
        not_before="2026-03-07T00:00:00Z",
        lease_expires_at="2026-04-07T00:00:00Z",
        profile="standard",
        private_key=private_key,
        signing_key_id="lic-2026-q1",
    )

    assert payload["signature"]["kid"] == "lic-2026-q1"
    assert payload["lease_id"] == "lease_issued"

    result = licensing_service.verify_activation_lease(
        payload,
        trust_anchors={
            "keys": [
                {
                    "kid": "lic-2026-q1",
                    "alg": "EdDSA",
                    "public_key": _b64url(public_key),
                }
            ]
        },
    )

    assert result.valid is True


def test_verify_license_artifact_signature_rejects_unknown_key():
    payload = _base_license()
    payload["signature"] = {
        "alg": "EdDSA",
        "kid": "missing-kid",
        "value": "abc",
    }

    result = licensing_service.verify_license_artifact(payload, trust_anchors={"keys": []})

    assert result.valid is False
    assert result.message == "Unknown signing key 'missing-kid'."


def test_verify_activation_lease_signature_rejects_tampered_payload():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()

    payload = {
        "schema_version": "1",
        "lease_id": "lease_123",
        "license_id": "lic_123",
        "install_id": "inst_123",
        "runtime_role": "relay",
        "profile": "relay-desktop",
        "issued_at": "2026-03-07T00:00:00Z",
        "not_before": "2026-03-07T00:00:00Z",
        "lease_expires_at": "2026-04-07T00:00:00Z",
        "device_id": "dev_123",
        "signature": {
            "alg": "EdDSA",
            "kid": "lic-2026-q1",
            "value": "",
        },
    }

    canonical = licensing_service._canonicalize_signed_payload(payload)
    payload["signature"]["value"] = _b64url(private_key.sign(canonical))

    payload["profile"] = "relay-device"

    result = licensing_service.verify_activation_lease(
        payload,
        trust_anchors={
            "keys": [
                {
                    "kid": "lic-2026-q1",
                    "alg": "EdDSA",
                    "public_key": _b64url(public_key),
                }
            ]
        },
    )

    assert result.valid is False
    assert result.message == "Signature verification failed."


def test_preflight_license_returns_active_for_valid_standard_license():
    payload = _base_license()

    result = licensing_service.preflight_license(
        "standard",
        payload,
        trust_anchors={"keys": []},
    )

    assert result.compatibility.allowed is True
    assert result.verification.valid is False
    assert result.compliance_state == "unlicensed"


def test_oem_embedded_profile_allows_matching_oem_license():
    payload = _base_license()
    payload["product"] = {
        "policy_id": "oem-embedded-core",
        "runtime_roles": ["embedded"],
        "distribution_profiles": ["oem-embedded-core"],
        "product_surface": "embedded-core-app",
    }
    payload["controls"] = {
        "offline_allowed": True,
        "offline_lease_days": 30,
        "require_activation": True,
        "require_reporting": True,
        "enforcement_profile": "oem-embedded",
    }
    payload["entitlements"] = ["oem_distribution"]

    result = licensing_service.evaluate_profile_license_compatibility(
        "oem-embedded-core",
        payload,
    )

    assert result.allowed is True
    assert result.control_class == "oem-embedded"


def test_dev_local_profile_does_not_require_license():
    result = licensing_service.preflight_deployment_mode("dev", "dev-local")

    assert result.allowed is True
    assert result.requires_license is False
    assert result.reason == "Developer mode may run the dev-local profile without a commercial license."


def test_community_self_host_profile_does_not_require_license():
    result = licensing_service.preflight_deployment_mode("self-host", "community-self-host")

    assert result.allowed is True
    assert result.requires_license is False
    assert result.reason == "Profile 'community-self-host' does not require a signed commercial license in mode 'self-host'."


def test_standard_profile_requires_license_in_self_host_mode():
    result = licensing_service.preflight_deployment_mode("self-host", "standard")

    assert result.allowed is False
    assert result.requires_license is True
    assert result.reason == "Profile 'standard' requires a signed license artifact in mode 'self-host'."


def test_managed_host_profile_allows_matching_license_in_cloud_host_mode():
    payload = _base_license()
    payload["product"] = {
        "policy_id": "managed-host-core",
        "runtime_roles": ["standard"],
        "distribution_profiles": ["managed-host"],
        "product_surface": "core-app",
    }
    payload["signature"] = {
        "alg": "EdDSA",
        "kid": "missing-kid",
        "value": "abc",
    }

    result = licensing_service.preflight_deployment_mode("cloud-host", "managed-host", payload)

    assert result.requires_license is True
    assert result.allowed is False
    assert result.preflight is not None
    assert result.preflight.compatibility.allowed is True