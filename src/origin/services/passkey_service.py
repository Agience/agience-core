"""Origin passkey service — Postgres-backed.

Ported from Mantle's `services/passkey_service.py`. WebAuthn ceremony logic is
unchanged; only the storage layer swaps from Arango to Postgres.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from kernel import config
from origin.db import passkey_credentials as db_passkeys
from origin.db import persons as db_persons
from origin.services.platform_settings_service import settings

logger = logging.getLogger(__name__)


def _get_rp_id() -> str:
    """Derive the Relying Party ID from the frontend hostname.

    Origin runs at a different host than the frontend; WebAuthn binds to the
    frontend origin (`config.FACET_URI`), so the rpId must match its host.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(config.FACET_URI)
        return parsed.hostname or "localhost"
    except Exception:
        return "localhost"


def _get_rp_name() -> str:
    return settings.get("branding.title", "Agience") or "Agience"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def get_registration_options(db: Session, user_id: str, email: str) -> dict:
    existing = db_passkeys.list_for_person(db, user_id)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(
            id=_b64url_decode(c.id),
            transports=list(c.transports or []),
        )
        for c in existing
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
        timeout=60000,
    )
    return {
        "rp": {"id": options.rp.id, "name": options.rp.name},
        "user": {
            "id": _b64url_encode(options.user.id),
            "name": options.user.name,
            "displayName": options.user.display_name,
        },
        "challenge": _b64url_encode(options.challenge),
        "pubKeyCredParams": [
            {"type": "public-key", "alg": p.alg} for p in options.pub_key_cred_params
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
            if options.authenticator_selection
            else "preferred",
            "userVerification": options.authenticator_selection.user_verification.value
            if options.authenticator_selection
            else "preferred",
        },
        "_challenge": _b64url_encode(options.challenge),
    }


def verify_registration(
    db: Session,
    user_id: str,
    credential: dict,
    expected_challenge: bytes,
    device_name: Optional[str] = None,
) -> dict:
    registration = RegistrationCredential.model_validate(credential)
    verification = verify_registration_response(
        credential=registration,
        expected_challenge=expected_challenge,
        expected_rp_id=_get_rp_id(),
        expected_origin=config.FACET_URI,
    )
    credential_id = _b64url_encode(verification.credential_id)
    db_passkeys.create(
        db,
        {
            "id": credential_id,
            "person_id": user_id,
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
            "device_name": device_name,
            "transports": credential.get("response", {}).get("transports", []),
            "created_time": datetime.now(timezone.utc),
        },
    )
    logger.info("Passkey registered for user %s (device: %s)", user_id, device_name)
    return {"credential_id": credential_id, "device_name": device_name}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def get_authentication_options(db: Session, email: str) -> Optional[dict]:
    person = db_persons.get_by_email(db, email)
    if not person:
        return None
    creds = db_passkeys.list_for_person(db, str(person.id))
    if not creds:
        return None
    allow_credentials = [
        PublicKeyCredentialDescriptor(
            id=_b64url_decode(c.id),
            transports=list(c.transports or []),
        )
        for c in creds
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
        "userVerification": options.user_verification.value
        if options.user_verification
        else "preferred",
        "_challenge": _b64url_encode(options.challenge),
        "_user_id": str(person.id),
    }


def verify_authentication(
    db: Session,
    credential: dict,
    expected_challenge: bytes,
    expected_user_id: str,
) -> Optional[str]:
    authentication = AuthenticationCredential.model_validate(credential)
    credential_id = _b64url_encode(authentication.raw_id)
    stored = db_passkeys.get_by_id_and_person(db, credential_id, expected_user_id)
    if stored is None:
        logger.warning("Passkey credential not found: %s", credential_id)
        return None
    try:
        verification = verify_authentication_response(
            credential=authentication,
            expected_challenge=expected_challenge,
            expected_rp_id=_get_rp_id(),
            expected_origin=config.FACET_URI,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count or 0,
        )
    except Exception as exc:
        logger.warning("Passkey verification failed: %s", exc)
        return None
    db_passkeys.update_sign_count(db, credential_id, verification.new_sign_count)
    logger.info("Passkey authentication successful for user %s", stored.person_id)
    return str(stored.person_id)


# ---------------------------------------------------------------------------
# Management
# ---------------------------------------------------------------------------
def list_credentials(db: Session, user_id: str) -> list[dict]:
    creds = db_passkeys.list_for_person(db, user_id)
    return [
        {
            "credential_id": c.id,
            "device_name": c.device_name,
            "created_at": c.created_time.isoformat() if c.created_time else None,
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        }
        for c in creds
    ]


def delete_credential(db: Session, user_id: str, credential_id: str) -> bool:
    return db_passkeys.delete_for_person(db, credential_id, user_id)


def has_passkeys(db: Session, email: str) -> bool:
    person = db_persons.get_by_email(db, email)
    if person is None:
        return False
    return len(db_passkeys.list_for_person(db, str(person.id))) > 0
