from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core import config
from core.key_manager import (
    get_licensing_key_id,
    get_licensing_private_key_path,
    get_licensing_trust_anchors_path,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _packaging_root() -> Path:
    return _repo_root() / "packaging"


def _profiles_root() -> Path:
    return _packaging_root() / "profiles"


def _licensing_root() -> Path:
    return _packaging_root() / "licensing"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class _FlexibleModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class LicenseProduct(_FlexibleModel):
    policy_id: str
    runtime_roles: List[str] = Field(default_factory=list)
    distribution_profiles: List[str] = Field(default_factory=list)
    product_surface: Optional[str] = None


class LicenseBranding(_FlexibleModel):
    mode: Optional[str] = None
    scope: List[str] = Field(default_factory=list)


class LicenseControls(_FlexibleModel):
    offline_allowed: bool
    require_activation: bool
    require_reporting: bool
    offline_lease_days: Optional[int] = None
    enforcement_profile: Optional[str] = None


class LicenseSignature(_FlexibleModel):
    alg: str
    kid: str
    value: str


class LicenseArtifact(_FlexibleModel):
    schema_version: str
    license_id: str
    entitlement_id: str
    account_id: str
    issued_at: str
    not_before: str
    expires_at: str
    state: Optional[str] = None
    product: LicenseProduct
    branding: Optional[LicenseBranding] = None
    controls: LicenseControls
    limits: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    reporting: Dict[str, Any] = Field(default_factory=dict)
    entitlements: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    extensions: Dict[str, Any] = Field(default_factory=dict)
    signature: LicenseSignature


class ActivationLeaseSignature(_FlexibleModel):
    alg: str
    kid: str
    value: str


class ActivationLease(_FlexibleModel):
    schema_version: str
    lease_id: str
    license_id: str
    install_id: str
    runtime_role: str
    issued_at: str
    not_before: str
    lease_expires_at: str
    instance_id: Optional[str] = None
    device_id: Optional[str] = None
    profile: Optional[str] = None
    heartbeat_interval_hours: Optional[int] = None
    reporting: Dict[str, Any] = Field(default_factory=dict)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    extensions: Dict[str, Any] = Field(default_factory=dict)
    signature: ActivationLeaseSignature


class CompatibilityIssue(BaseModel):
    code: str
    message: str


class CompatibilityResult(BaseModel):
    allowed: bool
    profile: str
    policy_id: Optional[str] = None
    control_class: Optional[str] = None
    issues: List[CompatibilityIssue] = Field(default_factory=list)


class SignatureVerificationResult(BaseModel):
    valid: bool
    key_id: Optional[str] = None
    algorithm: Optional[str] = None
    message: Optional[str] = None


class LicensePreflightResult(BaseModel):
    verification: SignatureVerificationResult
    compatibility: CompatibilityResult
    compliance_state: str
    warnings: List[str] = Field(default_factory=list)


class DeploymentModeResult(BaseModel):
    mode: str
    profile: str
    requires_license: bool
    allowed: bool
    reason: str
    warnings: List[str] = Field(default_factory=list)
    preflight: Optional[LicensePreflightResult] = None


def load_profile(profile_name: str) -> Dict[str, Any]:
    return _load_json(_profiles_root() / f"{profile_name}.json")


def load_policy_map() -> Dict[str, Any]:
    return _load_json(_licensing_root() / "policy-map.json")


def load_control_classes() -> Dict[str, Any]:
    return _load_json(_licensing_root() / "control-classes.json")


def load_trust_anchors() -> Dict[str, Any]:
    path = Path(config.LICENSING_PUBLIC_KEYS_PATH) if config.LICENSING_PUBLIC_KEYS_PATH else get_licensing_trust_anchors_path()
    if not path.exists() or not path.is_file():
        return {"keys": []}
    return _load_json(path)


def profile_requires_license(profile_name: str) -> bool:
    profile = load_profile(profile_name)
    control_class_name = profile.get("license_class")
    control_class = get_control_class(control_class_name) if control_class_name else None
    if not control_class:
        return True
    return bool(control_class.get("requires_signed_license", True))


def get_policy(policy_id: str) -> Optional[Dict[str, Any]]:
    policies = load_policy_map().get("policies", {})
    policy = policies.get(policy_id)
    if isinstance(policy, dict):
        return policy
    return None


def get_control_class(control_class: str) -> Optional[Dict[str, Any]]:
    classes = load_control_classes().get("control_classes", {})
    item = classes.get(control_class)
    if isinstance(item, dict):
        return item
    return None


def parse_license_artifact(payload: Dict[str, Any]) -> LicenseArtifact:
    return LicenseArtifact.model_validate(payload)


def parse_activation_lease(payload: Dict[str, Any]) -> ActivationLease:
    return ActivationLease.model_validate(payload)


def _canonicalize_signed_payload(payload: Dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _get_trust_anchor_by_kid(kid: str, trust_anchors: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    anchors = trust_anchors or load_trust_anchors()
    for item in anchors.get("keys", []):
        if isinstance(item, dict) and item.get("kid") == kid:
            return item
    return None


def _decode_base64url_unpadded(value: str) -> bytes:
    padding = "=" * ((4 - (len(value) % 4)) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _encode_base64url_unpadded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


@lru_cache(maxsize=1)
def _load_signing_private_key() -> Ed25519PrivateKey:
    path = Path(config.LICENSING_PRIVATE_KEY_PATH) if config.LICENSING_PRIVATE_KEY_PATH else get_licensing_private_key_path()
    if not path.exists() or not path.is_file():
        raise RuntimeError(
            f"Licensing signing key file '{path}' does not exist."
        )

    private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise RuntimeError("Licensing signing key must be an Ed25519 private key.")
    return private_key


def _resolve_signing_key_id(signing_key_id: Optional[str] = None) -> str:
    kid = signing_key_id or config.LICENSING_SIGNING_KEY_ID or get_licensing_key_id()
    if not kid:
        raise RuntimeError(
            "LICENSING_SIGNING_KEY_ID is not configured; signed license issuance is unavailable."
        )
    return kid


def _sign_payload(
    payload: Dict[str, Any],
    *,
    private_key: Optional[Ed25519PrivateKey] = None,
    signing_key_id: Optional[str] = None,
) -> Dict[str, Any]:
    key = private_key or _load_signing_private_key()
    kid = _resolve_signing_key_id(signing_key_id)
    signed = dict(payload)
    signed["signature"] = {
        "alg": "EdDSA",
        "kid": kid,
        "value": _encode_base64url_unpadded(key.sign(_canonicalize_signed_payload(payload))),
    }
    return signed


def digest_signed_payload(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def verify_signature(payload: Dict[str, Any], trust_anchors: Optional[Dict[str, Any]] = None) -> SignatureVerificationResult:
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        return SignatureVerificationResult(valid=False, message="Missing signature block.")

    kid = signature.get("kid")
    alg = signature.get("alg")
    value = signature.get("value")
    if not kid or not alg or not value:
        return SignatureVerificationResult(valid=False, message="Incomplete signature block.")

    anchor = _get_trust_anchor_by_kid(kid, trust_anchors=trust_anchors)
    if anchor is None:
        return SignatureVerificationResult(valid=False, key_id=kid, algorithm=alg, message=f"Unknown signing key '{kid}'.")

    if alg != anchor.get("alg"):
        return SignatureVerificationResult(
            valid=False,
            key_id=kid,
            algorithm=alg,
            message=f"Signature algorithm '{alg}' does not match trust anchor algorithm '{anchor.get('alg')}'.",
        )

    if alg != "EdDSA":
        return SignatureVerificationResult(valid=False, key_id=kid, algorithm=alg, message=f"Unsupported licensing signature algorithm '{alg}'.")

    public_key_b64 = anchor.get("public_key")
    if not isinstance(public_key_b64, str) or not public_key_b64:
        return SignatureVerificationResult(valid=False, key_id=kid, algorithm=alg, message="Trust anchor is missing public key material.")

    try:
        public_key = Ed25519PublicKey.from_public_bytes(_decode_base64url_unpadded(public_key_b64))
        public_key.verify(_decode_base64url_unpadded(value), _canonicalize_signed_payload(payload))
        return SignatureVerificationResult(valid=True, key_id=kid, algorithm=alg, message="Signature verified.")
    except (ValueError, InvalidSignature):
        return SignatureVerificationResult(valid=False, key_id=kid, algorithm=alg, message="Signature verification failed.")


def verify_license_artifact(payload: Dict[str, Any], trust_anchors: Optional[Dict[str, Any]] = None) -> SignatureVerificationResult:
    parse_license_artifact(payload)
    return verify_signature(payload, trust_anchors=trust_anchors)


def verify_activation_lease(payload: Dict[str, Any], trust_anchors: Optional[Dict[str, Any]] = None) -> SignatureVerificationResult:
    parse_activation_lease(payload)
    return verify_signature(payload, trust_anchors=trust_anchors)


def issue_license_artifact(
    *,
    license_id: str,
    entitlement_id: str,
    account_id: str,
    issued_at: str,
    not_before: str,
    expires_at: str,
    policy_id: str,
    runtime_roles: List[str],
    distribution_profiles: List[str],
    product_surface: Optional[str] = None,
    branding_mode: Optional[str] = None,
    branding_scope: Optional[List[str]] = None,
    state: Optional[str] = "active",
    offline_allowed: bool = True,
    require_activation: bool = True,
    require_reporting: bool = True,
    offline_lease_days: Optional[int] = None,
    enforcement_profile: Optional[str] = None,
    limits: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    reporting: Optional[Dict[str, Any]] = None,
    entitlements: Optional[List[str]] = None,
    attributes: Optional[Dict[str, Any]] = None,
    extensions: Optional[Dict[str, Any]] = None,
    private_key: Optional[Ed25519PrivateKey] = None,
    signing_key_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schema_version": "1",
        "license_id": license_id,
        "entitlement_id": entitlement_id,
        "account_id": account_id,
        "issued_at": issued_at,
        "not_before": not_before,
        "expires_at": expires_at,
        "product": {
            "policy_id": policy_id,
            "runtime_roles": runtime_roles,
            "distribution_profiles": distribution_profiles,
            "product_surface": product_surface,
        },
        "controls": {
            "offline_allowed": offline_allowed,
            "offline_lease_days": offline_lease_days,
            "require_activation": require_activation,
            "require_reporting": require_reporting,
            "enforcement_profile": enforcement_profile,
        },
        "limits": limits or {},
        "features": features or {},
        "reporting": reporting or {},
        "entitlements": entitlements or [],
        "attributes": attributes or {},
        "extensions": extensions or {},
    }
    if state is not None:
        payload["state"] = state
    if branding_mode or branding_scope:
        payload["branding"] = {
            "mode": branding_mode,
            "scope": branding_scope or [],
        }

    signed = _sign_payload(payload, private_key=private_key, signing_key_id=signing_key_id)
    parse_license_artifact(signed)
    return signed


def issue_activation_lease(
    *,
    lease_id: str,
    license_id: str,
    install_id: str,
    runtime_role: str,
    issued_at: str,
    not_before: str,
    lease_expires_at: str,
    instance_id: Optional[str] = None,
    device_id: Optional[str] = None,
    profile: Optional[str] = None,
    heartbeat_interval_hours: Optional[int] = None,
    reporting: Optional[Dict[str, Any]] = None,
    attributes: Optional[Dict[str, Any]] = None,
    extensions: Optional[Dict[str, Any]] = None,
    private_key: Optional[Ed25519PrivateKey] = None,
    signing_key_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "schema_version": "1",
        "lease_id": lease_id,
        "license_id": license_id,
        "install_id": install_id,
        "runtime_role": runtime_role,
        "issued_at": issued_at,
        "not_before": not_before,
        "lease_expires_at": lease_expires_at,
        "instance_id": instance_id,
        "device_id": device_id,
        "profile": profile,
        "heartbeat_interval_hours": heartbeat_interval_hours,
        "reporting": reporting or {},
        "attributes": attributes or {},
        "extensions": extensions or {},
    }
    signed = _sign_payload(payload, private_key=private_key, signing_key_id=signing_key_id)
    parse_activation_lease(signed)
    return signed


def evaluate_compliance_state(
    verification: SignatureVerificationResult,
    compatibility: CompatibilityResult,
    license_artifact: LicenseArtifact,
) -> str:
    if not verification.valid:
        return "unlicensed"
    if license_artifact.state == "revoked":
        return "revoked"
    if not compatibility.allowed:
        return "unlicensed"
    return "active"


def preflight_license(
    profile_name: str,
    payload: Dict[str, Any],
    trust_anchors: Optional[Dict[str, Any]] = None,
) -> LicensePreflightResult:
    license_artifact = parse_license_artifact(payload)
    verification = verify_license_artifact(payload, trust_anchors=trust_anchors)
    compatibility = evaluate_profile_license_compatibility(profile_name, payload)
    warnings: List[str] = []

    profile = load_profile(profile_name)
    if profile.get("offline_supported") and not license_artifact.controls.offline_allowed:
        warnings.append(
            f"Profile '{profile_name}' supports offline operation, but this license disallows offline leases."
        )

    compliance_state = evaluate_compliance_state(verification, compatibility, license_artifact)
    return LicensePreflightResult(
        verification=verification,
        compatibility=compatibility,
        compliance_state=compliance_state,
        warnings=warnings,
    )


def preflight_deployment_mode(
    mode: str,
    profile_name: str,
    payload: Optional[Dict[str, Any]] = None,
    trust_anchors: Optional[Dict[str, Any]] = None,
) -> DeploymentModeResult:
    normalized_mode = (mode or "").strip().lower()
    warnings: List[str] = []

    if normalized_mode not in {"dev", "self-host", "cloud-host"}:
        return DeploymentModeResult(
            mode=normalized_mode,
            profile=profile_name,
            requires_license=True,
            allowed=False,
            reason=f"Unknown deployment mode '{mode}'.",
        )

    requires_license = profile_requires_license(profile_name)

    if normalized_mode == "dev":
        if profile_name == "dev-local" and payload is None:
            return DeploymentModeResult(
                mode=normalized_mode,
                profile=profile_name,
                requires_license=False,
                allowed=True,
                reason="Developer mode may run the dev-local profile without a commercial license.",
            )

        warnings.append(
            "Developer mode is intended for the dev-local profile; commercial profiles should usually be exercised with explicit test licenses."
        )

    if not requires_license and payload is None:
        return DeploymentModeResult(
            mode=normalized_mode,
            profile=profile_name,
            requires_license=False,
            allowed=True,
            reason=f"Profile '{profile_name}' does not require a signed commercial license in mode '{normalized_mode}'.",
            warnings=warnings,
        )

    if payload is None:
        return DeploymentModeResult(
            mode=normalized_mode,
            profile=profile_name,
            requires_license=requires_license,
            allowed=False,
            reason=f"Profile '{profile_name}' requires a signed license artifact in mode '{normalized_mode}'.",
            warnings=warnings,
        )

    preflight = preflight_license(profile_name, payload, trust_anchors=trust_anchors)
    return DeploymentModeResult(
        mode=normalized_mode,
        profile=profile_name,
        requires_license=requires_license,
        allowed=preflight.verification.valid and preflight.compatibility.allowed,
        reason="Deployment mode preflight completed.",
        warnings=warnings + preflight.warnings,
        preflight=preflight,
    )


def evaluate_profile_license_compatibility(profile_name: str, payload: Dict[str, Any]) -> CompatibilityResult:
    profile = load_profile(profile_name)
    license_artifact = parse_license_artifact(payload)

    issues: List[CompatibilityIssue] = []

    policy = get_policy(license_artifact.product.policy_id)
    control_class_name: Optional[str] = None
    if policy is None:
        issues.append(
            CompatibilityIssue(
                code="unknown_policy",
                message=f"License policy '{license_artifact.product.policy_id}' is not defined.",
            )
        )
    else:
        control_class_name = policy.get("control_class")

    profile_runtime_role = profile.get("runtime_role")
    if profile_runtime_role not in license_artifact.product.runtime_roles:
        issues.append(
            CompatibilityIssue(
                code="runtime_role_mismatch",
                message=(
                    f"Profile '{profile_name}' requires runtime role '{profile_runtime_role}', "
                    f"but the license allows {license_artifact.product.runtime_roles}."
                ),
            )
        )

    allowed_profiles = set(license_artifact.product.distribution_profiles)
    if allowed_profiles and profile_name not in allowed_profiles:
        issues.append(
            CompatibilityIssue(
                code="profile_not_allowed",
                message=f"Profile '{profile_name}' is not listed in the license distribution profiles.",
            )
        )

    required_entitlements = set(profile.get("required_entitlements", []))
    present_entitlements = set(license_artifact.entitlements)
    missing_entitlements = sorted(required_entitlements - present_entitlements)
    if missing_entitlements:
        issues.append(
            CompatibilityIssue(
                code="missing_entitlements",
                message=(
                    "License is missing required entitlements for this profile: "
                    + ", ".join(missing_entitlements)
                ),
            )
        )

    profile_control_class = profile.get("license_class")
    if control_class_name and profile_control_class != control_class_name:
        issues.append(
            CompatibilityIssue(
                code="control_class_mismatch",
                message=(
                    f"Profile '{profile_name}' expects control class '{profile_control_class}', "
                    f"but policy '{license_artifact.product.policy_id}' resolves to '{control_class_name}'."
                ),
            )
        )

    allowed_branding_scope = set((policy or {}).get("allowed_branding_scope", []))
    requested_branding_scope = set(profile.get("branding_scope", []))
    if not requested_branding_scope.issubset(allowed_branding_scope):
        missing_scope = sorted(requested_branding_scope - allowed_branding_scope)
        if missing_scope:
            issues.append(
                CompatibilityIssue(
                    code="branding_scope_not_allowed",
                    message=(
                        "Profile requests branding scope not allowed by the resolved policy: "
                        + ", ".join(missing_scope)
                    ),
                )
            )

    license_surface = license_artifact.product.product_surface
    profile_surface = profile.get("product_surface")
    if license_surface and profile_surface and license_surface != profile_surface:
        issues.append(
            CompatibilityIssue(
                code="product_surface_mismatch",
                message=(
                    f"Profile '{profile_name}' targets product surface '{profile_surface}', "
                    f"but the license targets '{license_surface}'."
                ),
            )
        )

    return CompatibilityResult(
        allowed=not issues,
        profile=profile_name,
        policy_id=license_artifact.product.policy_id,
        control_class=control_class_name,
        issues=issues,
    )