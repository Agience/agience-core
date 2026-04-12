"""
services/passkey_service.py

WebAuthn (FIDO2) passkey credential management.

Handles registration and authentication ceremonies using py_webauthn.
Passkey credentials are stored per-user in the ArangoDB passkey_credentials collection.
"""

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from arango.database import StandardDatabase
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    RegistrationCredential,
    AuthenticationCredential,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

from core import config
from db import arango_identity as arango_ws

logger = logging.getLogger(__name__)


def _get_rp_id() -> str:
    """Derive the Relying Party ID from the backend URI hostname."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(config.BACKEND_URI)
        return parsed.hostname or "localhost"
    except Exception:
        return "localhost"


def _get_rp_name() -> str:
    """Platform display name for WebAuthn prompts."""
    from services.platform_settings_service import settings
    return settings.get("branding.title", "Agience") or "Agience"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------

def get_registration_options(
    db: StandardDatabase,
    user_id: str,
    email: str,
) -> dict:
    """
    Generate WebAuthn registration options for a user.

    Returns a dict that the frontend passes to navigator.credentials.create().
    """
    # Exclude already-registered credentials
    existing = arango_ws.get_passkey_credentials_for_person(db, user_id)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=_b64url_decode(cred["id"]),
            transports=cred.get("transports") or [],
        )
        for cred in existing
    ]

    options = generate_registration_options(
        rp_id=_get_rp_id(),
        rp_name=_get_rp_name(),
        user_id=user_id.encode("utf-8"),
        user_name=email,
        user_display_name=email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
        exclude_credentials=exclude_credentials,
        timeout=60000,  # 60 seconds
    )

    # Convert to JSON-serializable dict
    return {
        "rp": {"id": options.rp.id, "name": options.rp.name},
        "user": {
            "id": _b64url_encode(options.user.id),
            "name": options.user.name,
            "displayName": options.user.display_name,
        },
        "challenge": _b64url_encode(options.challenge),
        "pubKeyCredParams": [
            {"type": "public-key", "alg": p.alg}
            for p in options.pub_key_cred_params
        ],
        "timeout": options.timeout,
        "excludeCredentials": [
            {
                "id": _b64url_encode(c.id),
                "type": "public-key",
                "transports": c.transports or [],
            }
            for c in (options.exclude_credentials or [])
        ],
        "authenticatorSelection": {
            "residentKey": options.authenticator_selection.resident_key.value
                if options.authenticator_selection else "preferred",
            "userVerification": options.authenticator_selection.user_verification.value
                if options.authenticator_selection else "preferred",
        },
        "_challenge": _b64url_encode(options.challenge),  # for server-side verification
    }


def verify_registration(
    db: StandardDatabase,
    user_id: str,
    credential: dict,
    expected_challenge: bytes,
    device_name: Optional[str] = None,
) -> dict:
    """
    Verify a WebAuthn registration response and store the credential.

    Returns the stored credential info.
    """
    registration = RegistrationCredential.model_validate(credential)

    verification = verify_registration_response(
        credential=registration,
        expected_challenge=expected_challenge,
        expected_rp_id=_get_rp_id(),
        expected_origin=config.FRONTEND_URI,
    )

    credential_id = _b64url_encode(verification.credential_id)
    public_key = verification.credential_public_key

    # Store in ArangoDB
    arango_ws.create_passkey_credential(db, {
        "id": credential_id,
        "person_id": user_id,
        "public_key": _b64url_encode(public_key),
        "sign_count": verification.sign_count,
        "device_name": device_name,
        "transports": credential.get("response", {}).get("transports", []),
        "created_time": datetime.now(timezone.utc).isoformat(),
    })

    logger.info("Passkey registered for user %s (device: %s)", user_id, device_name)
    return {
        "credential_id": credential_id,
        "device_name": device_name,
    }


# ---------------------------------------------------------------------------
#  Authentication
# ---------------------------------------------------------------------------

def get_authentication_options(
    db: StandardDatabase,
    email: str,
) -> Optional[dict]:
    """
    Generate WebAuthn authentication options for a user identified by email.

    Returns None if the user has no passkeys registered.
    Returns a dict that the frontend passes to navigator.credentials.get().
    """
    person = arango_ws.get_person_by_email(db, email)
    if not person:
        return None

    person_id = person["id"]
    credentials = arango_ws.get_passkey_credentials_for_person(db, person_id)

    if not credentials:
        return None

    allow_credentials = [
        PublicKeyCredentialDescriptor(
            id=_b64url_decode(cred["id"]),
            transports=cred.get("transports") or [],
        )
        for cred in credentials
    ]

    options = generate_authentication_options(
        rp_id=_get_rp_id(),
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
        timeout=60000,
    )

    return {
        "challenge": _b64url_encode(options.challenge),
        "rpId": options.rp_id,
        "timeout": options.timeout,
        "allowCredentials": [
            {
                "id": _b64url_encode(c.id),
                "type": "public-key",
                "transports": c.transports or [],
            }
            for c in (options.allow_credentials or [])
        ],
        "userVerification": options.user_verification.value if options.user_verification else "preferred",
        "_challenge": _b64url_encode(options.challenge),
        "_user_id": person_id,
    }


def verify_authentication(
    db: StandardDatabase,
    credential: dict,
    expected_challenge: bytes,
    expected_user_id: str,
) -> Optional[str]:
    """
    Verify a WebAuthn authentication response.

    Returns the person_id on success, None on failure.
    """
    authentication = AuthenticationCredential.model_validate(credential)
    credential_id = _b64url_encode(authentication.raw_id)

    # Look up the stored credential
    stored = arango_ws.get_passkey_credential_by_id_and_person(db, credential_id, expected_user_id)

    if not stored:
        logger.warning("Passkey credential not found: %s", credential_id)
        return None

    try:
        verification = verify_authentication_response(
            credential=authentication,
            expected_challenge=expected_challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=config.FRONTEND_URI,
            credential_public_key=_b64url_decode(stored["public_key"]),
            credential_current_sign_count=stored.get("sign_count", 0),
        )
    except Exception as e:
        logger.warning("Passkey verification failed: %s", e)
        return None

    # Update sign count and last used
    arango_ws.update_passkey_credential(db, credential_id, {
        "sign_count": verification.new_sign_count,
        "last_used_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info("Passkey authentication successful for user %s", stored["person_id"])
    return stored["person_id"]


# ---------------------------------------------------------------------------
#  Management
# ---------------------------------------------------------------------------

def list_credentials(db: StandardDatabase, user_id: str) -> list[dict]:
    """List all passkey credentials for a user."""
    credentials = arango_ws.get_passkey_credentials_for_person(db, user_id)

    return [
        {
            "credential_id": c["id"],
            "device_name": c.get("device_name"),
            "created_at": c.get("created_time"),
            "last_used_at": c.get("last_used_at"),
        }
        for c in credentials
    ]


def delete_credential(db: StandardDatabase, user_id: str, credential_id: str) -> bool:
    """Delete a passkey credential. Returns True if deleted."""
    return arango_ws.delete_passkey_credential_for_person(db, credential_id, user_id)


def has_passkeys(db: StandardDatabase, email: str) -> bool:
    """Check if a user has any registered passkeys."""
    person = arango_ws.get_person_by_email(db, email)
    if not person:
        return False
    credentials = arango_ws.get_passkey_credentials_for_person(db, person["id"])
    return len(credentials) > 0
