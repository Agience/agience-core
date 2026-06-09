"""Origin /setup router — first-boot wizard.

Slimmed from Mantle's version:
- Operator + platform settings only (Postgres-backed).
- Inbox workspace creation moved out (Mantle creates lazily on first access).
- Passkey registration during setup removed (operator can register post-login).
- Phase 4 callback removed (Mantle's lifespan handles seed content).
- Connection validation kept for Anthropic/email; Arango/OpenSearch validation
  moves to a Mantle endpoint (follow-up — operators can validate via the
  setup wizard restart instead).

Cross-service seed_collections / Mantle-side bootstrap happens via the
`manifest.yml` mechanism — Origin and Mantle each apply their section at
startup independently.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from kernel import config
from kernel.key_manager import delete_setup_token, get_setup_token
from origin.db import persons as db_persons
from origin.db.session import get_db
from origin.services.auth_service import create_jwt_token, hash_password
from origin.services.platform_settings_service import settings as platform_settings

logger = logging.getLogger(__name__)
setup_router = APIRouter(prefix="/setup", tags=["Setup"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class SetupStatusResponse(BaseModel):
    needs_setup: bool
    ready: bool
    version: str
    env_defaults: dict[str, bool | str] = {}


class ValidateTokenRequest(BaseModel):
    token: str


class ValidateTokenResponse(BaseModel):
    valid: bool


class OperatorAccount(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    name: Optional[str] = None


class SettingInput(BaseModel):
    key: str
    value: str
    category: str
    is_secret: bool = False


class SetupCompleteRequest(BaseModel):
    operator: Optional[OperatorAccount] = None
    settings: list[SettingInput] = []


class SetupCompleteResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ValidateConnectionRequest(BaseModel):
    service: str
    config: dict


class ValidateConnectionResponse(BaseModel):
    success: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _verify_setup_token(token: str) -> None:
    expected = get_setup_token()
    if not expected:
        raise HTTPException(status_code=410, detail="Setup already completed")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid setup token")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@setup_router.get("/status", response_model=SetupStatusResponse)
async def get_setup_status():
    email_provider_env = os.getenv("EMAIL_PROVIDER", "")
    if not email_provider_env:
        if os.getenv("SMTP_HOST"):
            email_provider_env = "smtp"
        elif os.getenv("RESEND_API_KEY"):
            email_provider_env = "resend"
        elif os.getenv("SENDGRID_API_KEY"):
            email_provider_env = "sendgrid"
    return SetupStatusResponse(
        needs_setup=platform_settings.needs_setup(),
        ready=not platform_settings.needs_setup(),
        version="origin",
        env_defaults={
            "llm_api_key": bool(os.getenv("LLM_API_KEY")),
            "llm_provider": os.getenv("LLM_PROVIDER", ""),
            "email_provider": email_provider_env,
            "smtp_host": os.getenv("SMTP_HOST", ""),
            "smtp_port": os.getenv("SMTP_PORT", ""),
            "smtp_username": os.getenv("SMTP_USERNAME", ""),
            "smtp_from": os.getenv("SMTP_FROM", os.getenv("PLATFORM_EMAIL_ADDRESS", "")),
            "smtp_has_password": bool(os.getenv("SMTP_PASSWORD")),
            "resend_has_api_key": bool(os.getenv("RESEND_API_KEY")),
            "sendgrid_has_api_key": bool(os.getenv("SENDGRID_API_KEY")),
        },
    )


@setup_router.post("/validate-token", response_model=ValidateTokenResponse)
async def validate_setup_token(body: ValidateTokenRequest):
    expected = get_setup_token()
    if not expected:
        raise HTTPException(status_code=410, detail="Setup already completed")
    return ValidateTokenResponse(valid=(body.token == expected))


@setup_router.post("/validate-connection", response_model=ValidateConnectionResponse)
async def validate_connection(
    body: ValidateConnectionRequest,
    x_setup_token: str = Header(..., alias="X-Setup-Token"),
):
    """Validate Anthropic / embeddings / email provider configs.

    Arango / OpenSearch validation is intentionally not handled here in
    Origin (no Arango client available). Operators verify those by
    completing setup and observing Mantle's startup logs.
    """
    _verify_setup_token(x_setup_token)
    service = body.service.lower()
    cfg = body.config
    try:
        if service == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=cfg.get("api_key", ""))
            # Cheapest possible call: 1-token completion against the quick model.
            client.messages.create(
                model=cfg.get("model") or "claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return ValidateConnectionResponse(success=True)
        if service == "openai":
            import httpx as _httpx

            resp = _httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {cfg.get('api_key', '')}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return ValidateConnectionResponse(success=True)
        if service == "openrouter":
            import httpx as _httpx

            resp = _httpx.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {cfg.get('api_key', '')}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return ValidateConnectionResponse(success=True)
        if service == "embeddings":
            import httpx

            uri = (cfg.get("uri") or "").rstrip("/")
            if not uri:
                return ValidateConnectionResponse(success=False, error="Missing 'uri'")
            headers = {"Content-Type": "application/json"}
            if cfg.get("api_key"):
                headers["Authorization"] = f"Bearer {cfg['api_key']}"
            resp = httpx.post(
                f"{uri}/embed",
                json={"input": ["test"]},
                headers=headers,
                timeout=10.0,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            ok = isinstance(payload.get("vectors"), list) and bool(payload["vectors"])
            return ValidateConnectionResponse(
                success=ok,
                error=None if ok else "Embeddings server returned no vectors",
            )
        if service in ("smtp", "ses", "sendgrid", "resend", "gmail"):
            from origin.services.email_service import test_connection

            success, error = await test_connection({"provider": service, **cfg})
            return ValidateConnectionResponse(success=success, error=error)
        return ValidateConnectionResponse(
            success=False,
            error=(
                f"Service '{service}' not validated by Origin "
                "(use anthropic / embeddings / smtp / ses / sendgrid / resend / gmail)."
            ),
        )
    except Exception as exc:
        return ValidateConnectionResponse(success=False, error=str(exc))


@setup_router.post("/complete", response_model=SetupCompleteResponse)
async def complete_setup(
    body: SetupCompleteRequest,
    x_setup_token: str = Header(..., alias="X-Setup-Token"),
    db: Session = Depends(get_db),
):
    _verify_setup_token(x_setup_token)
    if not platform_settings.needs_setup():
        raise HTTPException(status_code=410, detail="Setup already completed")

    operator_id: Optional[str] = None
    access_token = ""
    refresh_token_str = ""
    op_email = ""
    person_name = ""

    if body.operator:
        if body.operator.password and len(body.operator.password) < 12:
            raise HTTPException(status_code=422, detail="Password must be at least 12 characters")
        password_hash = (
            hash_password(body.operator.password) if body.operator.password else None
        )
        op_email = (body.operator.email or "").lower() if body.operator.email else ""
        person_name = body.operator.name or (op_email.split("@")[0] if op_email else "operator")

        person = db_persons.create(
            db,
            {
                "email": op_email or None,
                "name": person_name,
                "username": person_name,
                "password_hash": password_hash,
            },
        )
        operator_id = str(person.id)

    # Write all settings
    settings_dicts: list[dict] = []
    for s in body.settings:
        if s.is_secret and not s.value:
            continue
        settings_dicts.append(
            {"key": s.key, "value": s.value, "category": s.category, "is_secret": s.is_secret}
        )
    # Inject env-sourced email secrets when not provided in the wizard payload.
    _email_provider_val = next((s.value for s in body.settings if s.key == "email.provider"), "")
    if _email_provider_val == "smtp" and not any(s.key == "email.smtp.password" for s in body.settings):
        _smtp_password = os.getenv("SMTP_PASSWORD", "")
        if _smtp_password:
            settings_dicts.append({"key": "email.smtp.password", "value": _smtp_password, "category": "email", "is_secret": True})
    elif _email_provider_val == "resend" and not any(s.key == "email.resend.api_key" for s in body.settings):
        _resend_key = os.getenv("RESEND_API_KEY", "")
        if _resend_key:
            settings_dicts.append({"key": "email.resend.api_key", "value": _resend_key, "category": "email", "is_secret": True})
    elif _email_provider_val == "sendgrid" and not any(s.key == "email.sendgrid.api_key" for s in body.settings):
        _sendgrid_key = os.getenv("SENDGRID_API_KEY", "")
        if _sendgrid_key:
            settings_dicts.append({"key": "email.sendgrid.api_key", "value": _sendgrid_key, "category": "email", "is_secret": True})
    settings_dicts.append(
        {"key": "platform.setup_complete", "value": "true", "category": "platform", "is_secret": False}
    )
    if operator_id:
        settings_dicts.append(
            {"key": "platform.operator_id", "value": operator_id, "category": "platform", "is_secret": False}
        )
    platform_settings.set_many(db, settings_dicts, updated_by=operator_id)

    if not operator_id:
        # Carry the setup token forward for first-Google-sign-in promotion.
        raw_setup_token = get_setup_token()
        if raw_setup_token:
            platform_settings.set_value(
                db,
                "platform.setup_operator_token",
                raw_setup_token,
                is_secret=True,
                category="platform",
            )
    delete_setup_token()
    db.commit()

    if operator_id and body.operator:
        user_data = {
            "sub": operator_id,
            "email": op_email,
            "name": person_name,
            "picture": "",
            "roles": ["platform:admin"],
            "client_id": getattr(config, "PLATFORM_CLIENT_ID", "platform"),
            "aud": config.AUTHORITY_ISSUER,
        }
        access_token = create_jwt_token(user_data)
        refresh_token_str = create_jwt_token(
            {**user_data, "token_type": "refresh"}, expires_hours=24 * 30
        )
        logger.info("Setup completed. Operator: %s (%s)", person_name, operator_id)
    else:
        logger.info("Setup completed. Operator captured on first OAuth sign-in.")

    return SetupCompleteResponse(access_token=access_token, refresh_token=refresh_token_str)
