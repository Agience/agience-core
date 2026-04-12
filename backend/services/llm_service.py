"""
LLM Service -- per-workspace LLM configuration and key resolution.

Handles:
- Per-workspace LLM configuration (provider, model, key binding)
- Fallback chain: workspace config -> user default -> Agience env
- Multi-provider support (OpenAI, Anthropic, Azure, etc.)

Key storage: delegated to secrets_service (person.preferences.secrets, type="llm_key").
Key CRUD endpoints: served by secrets_router (generic /secrets API).
"""

from __future__ import annotations

import logging
from typing import Optional
from arango.database import StandardDatabase

from services import workspace_service as ws_svc
from services import secrets_service
from core import config
from core.dependencies import get_arango_db

logger = logging.getLogger(__name__)


def get_llm_key_for_workspace(
    db: StandardDatabase,
    user_id: str,
    workspace_id: str,
    provider: str = "openai",
) -> Optional[str]:
    """
    Get decrypted API key for workspace LLM invocation.

    Fallback chain:
    1. Workspace-specific key (workspace card context `llm.key_id`)
    2. User's default key for provider (type="llm_key")
    3. Agience default from environment
    """
    arango_db: StandardDatabase = next(get_arango_db())

    # 1. Check workspace-specific LLM config
    try:
        context = ws_svc.get_workspace_context(db, user_id, workspace_id)
        llm_config = context.get("llm", {}) if isinstance(context, dict) else {}

        if llm_config.get("key_id"):
            val = secrets_service.get_secret_value(
                arango_db, user_id,
                secret_type="llm_key",
                provider=provider,
                secret_id=llm_config["key_id"],
            )
            if val:
                return val
    except Exception as e:
        logger.warning("Failed to get workspace LLM config: %s", e)

    # 2. User's default key for provider
    try:
        val = secrets_service.get_secret_value(
            arango_db, user_id, secret_type="llm_key", provider=provider
        )
        if val:
            return val
    except Exception as e:
        logger.warning("Failed to get user default LLM key: %s", e)

    # 3. Agience default from environment
    if provider == "openai":
        return config.OPENAI_API_KEY

    logger.warning("No API key found for provider %s", provider)
    return None


def set_workspace_llm(
    db: StandardDatabase,
    user_id: str,
    workspace_id: str,
    provider: str,
    model: str,
    key_id: Optional[str] = None,
):
    """
    Configure LLM for workspace.

    Args:
        db: Database session
        user_id: User ID
        workspace_id: Workspace ID
        provider: LLM provider (openai, anthropic, etc.)
        model: Model name (gpt-4, claude-3-opus, etc.)
        key_id: Optional secret ID (uses default if None)
    """
    context = ws_svc.get_workspace_context(db, user_id, workspace_id)
    if not isinstance(context, dict):
        context = {}

    context["llm"] = {
        "provider": provider,
        "model": model,
        "key_id": key_id,
    }

    ws_svc.update_workspace_context(db, user_id, workspace_id, context)


def clear_workspace_llm(db: StandardDatabase, user_id: str, workspace_id: str):
    """Remove workspace-specific LLM config (falls back to user/Agience defaults)."""
    context = ws_svc.get_workspace_context(db, user_id, workspace_id)
    if not isinstance(context, dict):
        return

    if "llm" in context:
        del context["llm"]
        ws_svc.update_workspace_context(db, user_id, workspace_id, context)
