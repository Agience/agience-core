# db/arango_identity.py
# type: ignore[import, attr-defined, assignment, arg-type, union-attr, call-arg, index, misc, return-value, override, var-annotated]
"""
Identity-tier Arango repositories: people, platform settings, passkey
credentials, OTP codes.

Moved out of the old `db/arango_workspace.py` (which was deleted as part of
the unified-artifact-store refactor). Logic unchanged — functions still
return plain dicts; service layer handles entity conversion.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from arango.database import StandardDatabase

logger = logging.getLogger(__name__)

# ---------- Collection names ----------

COLL_PEOPLE = "people"
COLL_PLATFORM_SETTINGS = "platform_settings"
COLL_PASSKEY_CREDENTIALS = "passkey_credentials"
COLL_OTP_CODES = "otp_codes"


# ---------- Internal helpers ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_doc(d: dict) -> dict:
    """Map ``id`` -> ``_key`` and strip None values for ArangoDB insert/replace."""
    doc = {k: v for k, v in d.items() if v is not None}
    if "id" in doc:
        doc["_key"] = doc.pop("id")
    return doc


def _from_doc(raw: dict) -> dict:
    """Map ``_key`` back to ``id`` and drop ArangoDB system fields."""
    if not raw:
        return raw
    out = dict(raw)
    out["id"] = out.pop("_key", out.get("_id", "").split("/")[-1])
    out.pop("_id", None)
    out.pop("_rev", None)
    return out


# ============================================================
#  PERSON functions
# ============================================================

def get_person_by_oidc_identity(db: StandardDatabase, oidc_provider: str, oidc_subject: str) -> Optional[dict]:
    try:
        cursor = db.aql.execute(
            "FOR p IN @@coll FILTER p.oidc_provider == @prov AND p.oidc_subject == @sub LIMIT 1 RETURN p",
            bind_vars={"@coll": COLL_PEOPLE, "prov": oidc_provider, "sub": oidc_subject},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving person by oidc identity %s/%s", oidc_provider, oidc_subject)
        return None


def get_person_by_email(db: StandardDatabase, email: str) -> Optional[dict]:
    try:
        cursor = db.aql.execute(
            "FOR p IN @@coll FILTER p.email == @email LIMIT 1 RETURN p",
            bind_vars={"@coll": COLL_PEOPLE, "email": email},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving person by email %s", email)
        return None


def get_person_by_username(db: StandardDatabase, username: str) -> Optional[dict]:
    try:
        cursor = db.aql.execute(
            "FOR p IN @@coll FILTER LOWER(p.username) == @username LIMIT 1 RETURN p",
            bind_vars={"@coll": COLL_PEOPLE, "username": username.lower()},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving person by username %s", username)
        return None


def get_person_by_google_id(db: StandardDatabase, google_id: str) -> Optional[dict]:
    found = get_person_by_oidc_identity(db, "google", google_id)
    if found:
        return found
    try:
        cursor = db.aql.execute(
            "FOR p IN @@coll FILTER p.google_id == @gid LIMIT 1 RETURN p",
            bind_vars={"@coll": COLL_PEOPLE, "gid": google_id},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving person by google_id %s", google_id)
        return None


def get_person_by_id(db: StandardDatabase, person_id: str) -> Optional[dict]:
    try:
        coll = db.collection(COLL_PEOPLE)
        raw = coll.get(person_id)
        if not raw:
            return None
        return _from_doc(raw)
    except Exception:
        logger.exception("Error retrieving person by id %s", person_id)
        return None


def create_person(db: StandardDatabase, person_dict: dict) -> Optional[str]:
    try:
        now = _now_iso()
        person_dict.setdefault("created_time", now)
        person_dict.setdefault("modified_time", now)
        person_dict.setdefault("preferences", {})
        doc = _to_doc(person_dict)
        coll = db.collection(COLL_PEOPLE)
        result = coll.insert(doc)
        return result.get("_key") or doc.get("_key")
    except Exception:
        logger.exception("Error creating person %s", person_dict.get("email"))
        return None


def update_person(db: StandardDatabase, person_id: str, updates: dict) -> bool:
    try:
        updates["modified_time"] = _now_iso()
        coll = db.collection(COLL_PEOPLE)
        coll.update({"_key": person_id, **updates})
        return True
    except Exception:
        logger.exception("Error updating person %s", person_id)
        return False


def list_all_people(db: StandardDatabase) -> List[dict]:
    try:
        cursor = db.aql.execute(
            "FOR p IN @@coll SORT p.created_time ASC RETURN p",
            bind_vars={"@coll": COLL_PEOPLE},
        )
        return list(cursor)
    except Exception:
        logger.exception("Error listing all people")
        return []


def count_people(db: StandardDatabase) -> int:
    try:
        coll = db.collection(COLL_PEOPLE)
        return coll.count()
    except Exception:
        logger.exception("Error counting people")
        return 0


def update_person_preferences(db: StandardDatabase, person_id: str, preferences: dict) -> bool:
    try:
        coll = db.collection(COLL_PEOPLE)
        coll.update({"_key": person_id, "preferences": preferences or {}})
        return True
    except Exception:
        logger.exception("Error updating preferences for person %s", person_id)
        return False


# ============================================================
#  PLATFORM SETTINGS functions
# ============================================================

def get_platform_setting(db: StandardDatabase, key: str) -> Optional[dict]:
    try:
        coll = db.collection(COLL_PLATFORM_SETTINGS)
        raw = coll.get(key)
        if not raw:
            return None
        return _from_doc(raw)
    except Exception:
        logger.exception("Error retrieving platform setting %s", key)
        return None


def set_platform_setting(
    db: StandardDatabase,
    key: str,
    value: str,
    category: Optional[str] = None,
    is_secret: bool = False,
    updated_by: Optional[str] = None,
) -> bool:
    try:
        now = _now_iso()
        doc: dict = {
            "_key": key,
            "value": value,
            "is_secret": is_secret,
            "updated_time": now,
        }
        if category is not None:
            doc["category"] = category
        if updated_by is not None:
            doc["updated_by"] = updated_by

        coll = db.collection(COLL_PLATFORM_SETTINGS)
        existing = coll.get(key)
        if existing:
            coll.update(doc)
        else:
            doc["created_time"] = now
            coll.insert(doc)
        return True
    except Exception:
        logger.exception("Error setting platform setting %s", key)
        return False


def get_platform_settings_by_category(db: StandardDatabase, category: str) -> List[dict]:
    try:
        cursor = db.aql.execute(
            "FOR s IN @@coll FILTER s.category == @cat RETURN s",
            bind_vars={"@coll": COLL_PLATFORM_SETTINGS, "cat": category},
        )
        return [_from_doc(raw) for raw in cursor]
    except Exception:
        logger.exception("Error fetching platform settings for category %s", category)
        return []


def get_all_platform_settings(db: StandardDatabase) -> List[dict]:
    try:
        cursor = db.aql.execute(
            "FOR s IN @@coll RETURN s",
            bind_vars={"@coll": COLL_PLATFORM_SETTINGS},
        )
        return [_from_doc(raw) for raw in cursor]
    except Exception:
        logger.exception("Error fetching all platform settings")
        return []


# ============================================================
#  PASSKEY CREDENTIAL functions
# ============================================================

def get_passkey_credential(db: StandardDatabase, credential_id: str) -> Optional[dict]:
    try:
        coll = db.collection(COLL_PASSKEY_CREDENTIALS)
        raw = coll.get(credential_id)
        if not raw:
            return None
        return _from_doc(raw)
    except Exception:
        logger.exception("Error retrieving passkey credential %s", credential_id)
        return None


def get_passkey_credentials_for_person(db: StandardDatabase, person_id: str) -> List[dict]:
    try:
        cursor = db.aql.execute(
            "FOR c IN @@coll FILTER c.person_id == @pid RETURN c",
            bind_vars={"@coll": COLL_PASSKEY_CREDENTIALS, "pid": person_id},
        )
        return [_from_doc(raw) for raw in cursor]
    except Exception:
        logger.exception("Error fetching passkey credentials for person %s", person_id)
        return []


def create_passkey_credential(db: StandardDatabase, credential_dict: dict) -> Optional[str]:
    try:
        now = _now_iso()
        credential_dict.setdefault("created_time", now)
        credential_dict.setdefault("sign_count", 0)
        doc = _to_doc(credential_dict)
        coll = db.collection(COLL_PASSKEY_CREDENTIALS)
        result = coll.insert(doc)
        return result.get("_key") or doc.get("_key")
    except Exception:
        logger.exception("Error creating passkey credential")
        return None


def update_passkey_sign_count(db: StandardDatabase, credential_id: str, new_sign_count: int) -> bool:
    try:
        coll = db.collection(COLL_PASSKEY_CREDENTIALS)
        coll.update({"_key": credential_id, "sign_count": new_sign_count})
        return True
    except Exception:
        logger.exception("Error updating passkey sign count %s", credential_id)
        return False


def get_passkey_credential_by_id_and_person(
    db: StandardDatabase, credential_id: str, person_id: str
) -> Optional[dict]:
    try:
        cursor = db.aql.execute(
            "FOR c IN @@coll FILTER c._key == @cid AND c.person_id == @pid LIMIT 1 RETURN c",
            bind_vars={"@coll": COLL_PASSKEY_CREDENTIALS, "cid": credential_id, "pid": person_id},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving passkey credential %s for person %s", credential_id, person_id)
        return None


def update_passkey_credential(db: StandardDatabase, credential_id: str, updates: dict) -> bool:
    try:
        coll = db.collection(COLL_PASSKEY_CREDENTIALS)
        coll.update({"_key": credential_id, **updates})
        return True
    except Exception:
        logger.exception("Error updating passkey credential %s", credential_id)
        return False


def delete_passkey_credential(db: StandardDatabase, credential_id: str) -> bool:
    try:
        coll = db.collection(COLL_PASSKEY_CREDENTIALS)
        coll.delete(credential_id)
        return True
    except Exception:
        logger.exception("Error deleting passkey credential %s", credential_id)
        return False


def delete_passkey_credential_for_person(
    db: StandardDatabase, credential_id: str, person_id: str
) -> bool:
    try:
        cursor = db.aql.execute(
            "FOR c IN @@coll FILTER c._key == @cid AND c.person_id == @pid "
            "REMOVE c IN @@coll RETURN OLD",
            bind_vars={"@coll": COLL_PASSKEY_CREDENTIALS, "cid": credential_id, "pid": person_id},
        )
        return sum(1 for _ in cursor) > 0
    except Exception:
        logger.exception("Error deleting passkey credential %s for person %s", credential_id, person_id)
        return False


# ============================================================
#  OTP CODE functions
# ============================================================

def create_otp_code(db: StandardDatabase, otp_dict: dict) -> Optional[str]:
    try:
        now = _now_iso()
        otp_dict.setdefault("created_time", now)
        otp_dict.setdefault("attempts", 0)
        doc = _to_doc(otp_dict)
        coll = db.collection(COLL_OTP_CODES)
        result = coll.insert(doc)
        return result.get("_key") or doc.get("_key")
    except Exception:
        logger.exception("Error creating OTP code")
        return None


def get_otp_code_by_email(db: StandardDatabase, email: str) -> Optional[dict]:
    try:
        cursor = db.aql.execute(
            "FOR o IN @@coll FILTER o.email == @email SORT o.created_time DESC LIMIT 1 RETURN o",
            bind_vars={"@coll": COLL_OTP_CODES, "email": email},
        )
        for raw in cursor:
            return _from_doc(raw)
        return None
    except Exception:
        logger.exception("Error retrieving OTP code for email %s", email)
        return None


def delete_otp_code(db: StandardDatabase, otp_id: str) -> bool:
    try:
        coll = db.collection(COLL_OTP_CODES)
        coll.delete(otp_id)
        return True
    except Exception:
        logger.exception("Error deleting OTP code %s", otp_id)
        return False


def increment_otp_attempts(db: StandardDatabase, otp_id: str) -> bool:
    try:
        db.aql.execute(
            "UPDATE {_key: @key} WITH {attempts: (DOCUMENT(@@coll, @key).attempts || 0) + 1} IN @@coll",
            bind_vars={"@coll": COLL_OTP_CODES, "key": otp_id},
        )
        return True
    except Exception:
        logger.exception("Error incrementing OTP attempts %s", otp_id)
        return False


def get_recent_failed_otp_count(db: StandardDatabase, email: str, since_iso: str, max_attempts: int) -> int:
    try:
        cursor = db.aql.execute(
            "FOR o IN @@coll "
            "FILTER o.email == @email AND o.created_time >= @since "
            "AND o.used != true AND o.attempts >= @max "
            "COLLECT WITH COUNT INTO cnt "
            "RETURN cnt",
            bind_vars={
                "@coll": COLL_OTP_CODES,
                "email": email,
                "since": since_iso,
                "max": max_attempts,
            },
        )
        for val in cursor:
            return val
        return 0
    except Exception:
        logger.exception("Error counting recent failed OTP codes for %s", email)
        return 0


def get_valid_otp_codes(db: StandardDatabase, email: str, now_iso: str, max_attempts: int) -> List[dict]:
    try:
        cursor = db.aql.execute(
            "FOR o IN @@coll "
            "FILTER o.email == @email AND o.expires_at > @now "
            "AND o.used != true AND o.attempts < @max "
            "SORT o.created_time DESC "
            "RETURN o",
            bind_vars={
                "@coll": COLL_OTP_CODES,
                "email": email,
                "now": now_iso,
                "max": max_attempts,
            },
        )
        return [_from_doc(raw) for raw in cursor]
    except Exception:
        logger.exception("Error fetching valid OTP codes for %s", email)
        return []


def mark_otp_used(db: StandardDatabase, otp_id: str) -> bool:
    try:
        coll = db.collection(COLL_OTP_CODES)
        coll.update({"_key": otp_id, "used": True})
        return True
    except Exception:
        logger.exception("Error marking OTP %s as used", otp_id)
        return False


def delete_expired_otp_codes(db: StandardDatabase, now_iso: str) -> int:
    try:
        cursor = db.aql.execute(
            "FOR o IN @@coll "
            "FILTER o.expires_at <= @now OR o.used == true "
            "REMOVE o IN @@coll "
            "COLLECT WITH COUNT INTO cnt "
            "RETURN cnt",
            bind_vars={"@coll": COLL_OTP_CODES, "now": now_iso},
        )
        for val in cursor:
            return val
        return 0
    except Exception:
        logger.exception("Error deleting expired OTP codes")
        return 0
