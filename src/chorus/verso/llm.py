"""
LLM dispatch — Verso-owned (stub).

This module owns multi-provider LLM completion dispatch (Anthropic, Google,
Ollama; future Beacon). It moved here from mantle/services/llm_service.py
because LLM completion is application semantics, not kernel; Verso's persona
role is "Reasoning & transforms," which is the natural home.

Currently a stub: every public function raises NotImplementedError so callers
fail loud. The previous mantle-side implementation depended on
mantle/services/{workspace_service, secrets_service, dependencies} for
per-workspace LLM config + key resolution. Re-implementing those reads in
Verso (likely as HTTP calls to mantle's artifact API for workspace context,
plus a Verso-side credential lookup) is the unblocked next step.

Public surface (preserved so importers stub gracefully):

    complete(...)                      -> (text, raw_response)
    get_llm_key_for_workspace(...)     -> dict | None
    set_workspace_llm(...)             -> None
    clear_workspace_llm(...)           -> None
    _dispatch_anthropic(...)           -> (text, raw)
    _dispatch_google(...)              -> (text, raw)
    _dispatch_ollama(...)              -> (text, raw)
"""
from __future__ import annotations

from typing import Any, Optional, Tuple


_NOT_IMPLEMENTED = (
    "LLM dispatch moved to chorus/verso/llm.py and is currently a stub. "
    "Re-implement provider dispatch + workspace config resolution at the new "
    "location, then update callers to reach Verso via the universal MCP "
    "gateway instead of in-process imports."
)


def complete(
    db: Any,
    user_id: str,
    messages: list[dict],
    *,
    workspace_id: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
) -> Tuple[str, Any]:
    """LLM completion across multi-provider dispatch. Stub."""
    raise NotImplementedError(_NOT_IMPLEMENTED)


def get_llm_key_for_workspace(
    db: Any,
    user_id: str,
    workspace_id: Optional[str] = None,
) -> Optional[dict]:
    """Resolve the LLM key bound to a workspace. Stub."""
    raise NotImplementedError(_NOT_IMPLEMENTED)


def set_workspace_llm(
    db: Any,
    user_id: str,
    workspace_id: str,
    *,
    provider: str,
    model: Optional[str] = None,
    secret_id: Optional[str] = None,
) -> None:
    """Persist a workspace LLM configuration. Stub."""
    raise NotImplementedError(_NOT_IMPLEMENTED)


def clear_workspace_llm(db: Any, user_id: str, workspace_id: str) -> None:
    """Remove a workspace LLM configuration. Stub."""
    raise NotImplementedError(_NOT_IMPLEMENTED)


def _dispatch_anthropic(*args: Any, **kwargs: Any) -> Tuple[str, Any]:
    raise NotImplementedError(_NOT_IMPLEMENTED)


def _dispatch_google(*args: Any, **kwargs: Any) -> Tuple[str, Any]:
    raise NotImplementedError(_NOT_IMPLEMENTED)


def _dispatch_ollama(*args: Any, **kwargs: Any) -> Tuple[str, Any]:
    raise NotImplementedError(_NOT_IMPLEMENTED)
