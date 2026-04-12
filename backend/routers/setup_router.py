"""
routers/setup_router.py

Setup wizard endpoints. Only functional during setup mode (first boot).

The setup wizard creates the platform operator account, writes all platform
settings to the DB, validates infrastructure connections, and triggers Phase 4
initialization in the background (no process restart required).
"""

import logging
import uuid
import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from arango.database import StandardDatabase

from core.dependencies import get_arango_db
from db import arango_identity as arango_ws
from services.platform_settings_service import settings as platform_settings
from services.auth_service import hash_password, create_jwt_token

logger = logging.getLogger(__name__)

setup_router = APIRouter(prefix="/setup", tags=["Setup"])


# ---------------------------------------------------------------------------
#  Request / Response models
# ---------------------------------------------------------------------------

class SetupStatusResponse(BaseModel):
    needs_setup: bool
    ready: bool
    version: str
    env_defaults: dict[str, bool] = {}


class ValidateTokenRequest(BaseModel):
    token: str


class ValidateTokenResponse(BaseModel):
    valid: bool


class OperatorAccount(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    name: Optional[str] = None
    passkey_credential: Optional[dict] = None
    passkey_challenge: Optional[str] = None
    passkey_device_name: Optional[str] = None


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
    service: str  # "arango", "opensearch", "s3", "openai", "smtp", "ses", "sendgrid", "resend"
    config: dict


class ValidateConnectionResponse(BaseModel):
    success: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
#  Endpoints
# ---------------------------------------------------------------------------

@setup_router.get("/status", response_model=SetupStatusResponse)
async def get_setup_status():
    """Check if platform setup is needed."""
    try:
        import main as _main
        version = _main.BUILD_INFO.get("version") or "unknown"
        setup_mode = _main._setup_mode
    except Exception:
        version = "unknown"
        setup_mode = True

    import os
    env_defaults = {
        "openai_api_key": bool(os.getenv("OPENAI_API_KEY")),
    }

    return SetupStatusResponse(
        needs_setup=platform_settings.needs_setup(),
        ready=not setup_mode,
        version=version,
        env_defaults=env_defaults,
    )


@setup_router.post("/validate-token", response_model=ValidateTokenResponse)
async def validate_setup_token(body: ValidateTokenRequest):
    """Validate a setup token without consuming it."""
    from core.key_manager import get_setup_token

    expected = get_setup_token()
    if not expected:
        raise HTTPException(status_code=410, detail="Setup already completed")

    return ValidateTokenResponse(valid=(body.token == expected))


@setup_router.post("/validate-connection", response_model=ValidateConnectionResponse)
async def validate_connection(
    body: ValidateConnectionRequest,
    x_setup_token: str = Header(..., alias="X-Setup-Token"),
):
    """
    Test a service connection without saving it.
    Requires the setup token in the X-Setup-Token header.
    """
    _verify_setup_token(x_setup_token)

    service = body.service.lower()
    cfg = body.config

    try:
        if service == "arango":
            from schemas.arango.initialize import get_arangodb_connection
            db = get_arangodb_connection(
                host=cfg.get("host", "arangodb"),
                port=int(cfg.get("port", 8529)),
                username=cfg.get("username", "root"),
                password=cfg.get("password", "root"),
                db_name=cfg.get("database", "agience"),
            )
            # Quick connectivity check
            db.version()
            return ValidateConnectionResponse(success=True)

        elif service == "opensearch":
            from opensearchpy import OpenSearch
            client = OpenSearch(
                hosts=[{"host": cfg.get("host", "search"), "port": int(cfg.get("port", 9200))}],
                http_auth=(cfg.get("username", ""), cfg.get("password", "")) if cfg.get("username") else None,
                use_ssl=cfg.get("use_ssl", False),
                verify_certs=cfg.get("verify_certs", False),
                timeout=5,
            )
            client.cluster.health()
            return ValidateConnectionResponse(success=True)

        elif service == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=cfg.get("api_key", ""))
            # Test with a tiny embedding
            client.embeddings.create(input="test", model="text-embedding-ada-002")
            return ValidateConnectionResponse(success=True)

        elif service in ("smtp", "ses", "sendgrid", "resend"):
            from services.email_service import test_connection
            success, error = await test_connection({"provider": service, **cfg})
            return ValidateConnectionResponse(success=success, error=error)

        elif service == "s3":
            import boto3
            from botocore.config import Config as BotoCfg

            endpoint_url = cfg.get("endpoint_url") or None
            region = cfg.get("region") or "us-east-1"
            boto_cfg = BotoCfg(s3={"addressing_style": "path"}) if endpoint_url else None
            client = boto3.client(
                "s3",
                aws_access_key_id=cfg.get("access_key_id"),
                aws_secret_access_key=cfg.get("secret_access_key"),
                region_name=region,
                endpoint_url=endpoint_url,
                **({"config": boto_cfg} if boto_cfg else {}),
            )
            bucket = cfg.get("bucket", "agience-content")
            try:
                client.head_bucket(Bucket=bucket)
            except Exception:
                # Bucket doesn't exist yet — try to create it (MinIO / permissive S3)
                create_kwargs: dict = {"Bucket": bucket}
                if region and region != "us-east-1":
                    create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
                client.create_bucket(**create_kwargs)
            return ValidateConnectionResponse(success=True)

        else:
            return ValidateConnectionResponse(success=False, error=f"Unknown service: {service}")

    except Exception as e:
        return ValidateConnectionResponse(success=False, error=str(e))



@setup_router.post("/complete", response_model=SetupCompleteResponse)
async def complete_setup(
    body: SetupCompleteRequest,
    background_tasks: BackgroundTasks,
    x_setup_token: str = Header(..., alias="X-Setup-Token"),
    db: StandardDatabase = Depends(get_arango_db),
):
    """
    Complete the platform setup wizard.

    1. Validates the setup token
    2. Creates the operator person record (email + password)
    3. Optionally registers a passkey
    4. Writes all settings to platform_settings
    5. Marks setup as complete
    6. Deletes the setup token file
    7. Returns JWT tokens for the new operator
    """
    _verify_setup_token(x_setup_token)

    if not platform_settings.needs_setup():
        raise HTTPException(status_code=410, detail="Setup already completed")

    from core import config

    operator_id = None
    access_token = ""
    refresh_token_str = ""
    person_name = ""

    if body.operator:
        # ------------------------------------------------------------------
        # 1. Create operator person record (email/password auth)
        # ------------------------------------------------------------------
        password_hash = None
        if body.operator.password:
            if len(body.operator.password) < 12:
                raise HTTPException(status_code=422, detail="Password must be at least 12 characters")
            password_hash = hash_password(body.operator.password)

        operator_id = str(uuid.uuid4())
        op_email = (body.operator.email or "").lower() if body.operator.email else ""
        person_name = body.operator.name or (op_email.split("@")[0] if op_email else "operator")
        arango_ws.create_person(db, {
            "id": operator_id,
            "email": op_email,
            "name": person_name,
            "username": person_name,
            "password_hash": password_hash,
            "preferences": {},
        })

        # ------------------------------------------------------------------
        # 2. Create operator's inbox workspace
        #    Ensure search indices exist with correct mappings BEFORE the first
        #    artifact is created and indexed. Without this, create_workspace()
        #    triggers synchronous indexing (the index worker isn't running yet),
        #    which causes OpenSearch to auto-create artifacts with dynamic
        #    mapping — mapping UUID fields as "text" instead of "keyword" and
        #    breaking all ACL term/terms filters for the lifetime of the install.
        # ------------------------------------------------------------------
        try:
            from search.init_search import ensure_search_indices_exist
            await asyncio.to_thread(ensure_search_indices_exist)
        except Exception:
            logger.warning(
                "Could not pre-create search indices before workspace setup "
                "(OpenSearch may not be ready). Phase 4 will retry.",
                exc_info=True,
            )

        from services.workspace_service import create_workspace
        create_workspace(
            db=db,
            user_id=operator_id,
            name="Inbox",
            is_inbox=True,
        )

        # ------------------------------------------------------------------
        # 3. Optionally register a passkey
        # ------------------------------------------------------------------
        if body.operator.passkey_credential and body.operator.passkey_challenge:
            try:
                from services import passkey_service
                challenge_bytes = passkey_service._b64url_decode(body.operator.passkey_challenge)
                passkey_service.verify_registration(
                    db=db,
                    user_id=operator_id,
                    credential=body.operator.passkey_credential,
                    expected_challenge=challenge_bytes,
                    device_name=body.operator.passkey_device_name,
                )
            except Exception as e:
                logger.warning("Passkey registration during setup failed: %s", e)

    # ------------------------------------------------------------------
    # 4. Write platform settings to DB
    # ------------------------------------------------------------------
    settings_dicts = [
        {"key": s.key, "value": s.value, "category": s.category, "is_secret": s.is_secret}
        for s in body.settings
    ]
    settings_dicts.append({
        "key": "platform.setup_complete",
        "value": "true",
        "category": "platform",
        "is_secret": False,
    })
    if operator_id:
        # Stored so get_operator_user() can identify the operator without
        # requiring an Arango grant (Arango isn't connected in setup mode).
        settings_dicts.append({
            "key": "platform.operator_id",
            "value": operator_id,
            "category": "platform",
            "is_secret": False,
        })

    platform_settings.set_many(db, settings_dicts, updated_by=operator_id)

    # Clear any stale infrastructure settings from previous incomplete setup runs
    # that are not being provided in this run.  Without this, leftover values (e.g.
    # db.arango.host=graph from an old Docker-targeted run) would survive and
    # override config defaults, breaking the new installation.
    infra_keys_provided = {s["key"] for s in settings_dicts}
    infra_keys_all = [
        "db.arango.host", "db.arango.port", "db.arango.username", "db.arango.database",
        "search.opensearch.host", "search.opensearch.port", "search.opensearch.use_ssl",
        "search.opensearch.verify_certs",
    ]
    stale_keys = [k for k in infra_keys_all if k not in infra_keys_provided]
    if stale_keys:
        platform_settings.delete_keys(db, stale_keys)
        # load_settings_from_db() only updates vars that ARE in the DB — it never
        # resets vars that were just deleted.  Explicitly revert deleted infra vars
        # to their env/compiled defaults so Phase 4 uses the right values.
        import os
        _infra_defaults = {
            "db.arango.host":     lambda: os.getenv("ARANGO_HOST", "127.0.0.1"),
            "db.arango.port":     lambda: int(os.getenv("ARANGO_PORT", "8529")),
            "db.arango.username": lambda: os.getenv("ARANGO_USERNAME", "root"),
            "db.arango.database": lambda: os.getenv("ARANGO_DATABASE", "agience"),
            "search.opensearch.host": lambda: os.getenv("OPENSEARCH_HOST", "127.0.0.1"),
            "search.opensearch.port": lambda: int(os.getenv("OPENSEARCH_PORT", "9200")),
            "search.opensearch.use_ssl":     lambda: os.getenv("OPENSEARCH_USE_SSL", "true").lower() in ("true", "1"),
            "search.opensearch.verify_certs": lambda: os.getenv("OPENSEARCH_VERIFY_CERTS", "false").lower() in ("true", "1"),
        }
        _var_names = {
            "db.arango.host": "ARANGO_HOST",
            "db.arango.port": "ARANGO_PORT",
            "db.arango.username": "ARANGO_USERNAME",
            "db.arango.database": "ARANGO_DATABASE",
            "search.opensearch.host": "OPENSEARCH_HOST",
            "search.opensearch.port": "OPENSEARCH_PORT",
            "search.opensearch.use_ssl": "OPENSEARCH_USE_SSL",
            "search.opensearch.verify_certs": "OPENSEARCH_VERIFY_CERTS",
        }
        for key in stale_keys:
            if key in _infra_defaults and key in _var_names:
                try:
                    from core import config as _config
                    setattr(_config, _var_names[key], _infra_defaults[key]())
                except Exception:
                    pass

    config.load_settings_from_db()

    # ------------------------------------------------------------------
    # 5. Persist the setup token for first-login operator promotion (Google-only),
    #    then delete from disk.  When operator is None the first Google sign-in
    #    that presents a matching setup_operator_token will be promoted instead.
    # ------------------------------------------------------------------
    from core.key_manager import delete_setup_token, get_setup_token
    if not operator_id:
        _raw_setup_token = get_setup_token()
        if _raw_setup_token:
            platform_settings.set_many(
                db,
                [{
                    "key": "platform.setup_operator_token",
                    "value": _raw_setup_token,
                    "category": "platform",
                    "is_secret": True,
                }],
                updated_by=None,
            )
    delete_setup_token()

    # ------------------------------------------------------------------
    # 6. Return JWT tokens (only when an operator account was created now)
    # ------------------------------------------------------------------
    if operator_id and body.operator:
        user_data = {
            "sub": operator_id,
            "email": op_email,
            "name": person_name,
            "picture": "",
            "roles": ["platform:admin"],
            "client_id": config.PLATFORM_CLIENT_ID,
        }
        access_token = create_jwt_token(user_data)
        refresh_payload = {**user_data, "token_type": "refresh"}
        refresh_token_str = create_jwt_token(refresh_payload, expires_hours=24 * 30)
        logger.info("Setup completed. Operator: %s (%s)", person_name, operator_id)
    else:
        logger.info("Setup completed. Operator identity will be captured on first Google sign-in.")

    from main import run_phase4_after_setup
    background_tasks.add_task(run_phase4_after_setup)

    return SetupCompleteResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
    )


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _verify_setup_token(token: str) -> None:
    """Validate the setup token from the X-Setup-Token header."""
    from core.key_manager import get_setup_token

    expected = get_setup_token()
    if not expected:
        raise HTTPException(status_code=410, detail="Setup already completed")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid setup token")
