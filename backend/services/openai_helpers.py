"""
OpenAI helper utilities for consistent API usage across the codebase.

Responsibilities:
- Automatically route to Chat Completions API or Responses API based on model
- Build correct parameters for different model families (GPT-5 vs earlier)
- Provide convenience functions to construct clients (sync/async) with optional API key
- Centralized response text extraction

Usage patterns:
- text, raw = create_chat_completion(model="gpt-5-nano", messages=[...], temperature=0.7)
- text, raw = await acreate_chat_completion(model="gpt-4o-mini", messages=[...])

GPT-5 models automatically use Responses API with proper parameters.
Earlier models use Chat Completions API.

Do NOT import application DB services here to avoid circular dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging

import openai

logger = logging.getLogger(__name__)


def is_gpt5_model(model: str) -> bool:
    """Return True if the model belongs to the GPT-5 family (requires Responses API)."""
    return str(model).strip().lower().startswith("gpt-5")


def build_chat_params(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build parameters for chat.completions.create with normalized token field.
    
    For GPT-5 models, this will return params for Responses API instead.

    Args:
        model: Model name
        messages: OpenAI messages array
        temperature: Optional temperature (ignored for GPT-5, use reasoning effort instead)
        max_output_tokens: Soft cap on output tokens; mapped to correct field
        extra: Additional fields to merge in
    """
    if is_gpt5_model(model):
        # GPT-5 uses Responses API with different parameters
        # Convert messages to input string (take last user message as input)
        input_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                input_text = msg.get("content", "")
                break
        
        params: Dict[str, Any] = {
            "model": model,
            "input": input_text,
            "max_output_tokens": max_output_tokens or 1024,
            "reasoning": {"effort": "minimal"},  # Fast mode for demo data
        }
        
        # Add any system messages as context if present
        system_msgs = [m.get("content", "") for m in messages if m.get("role") == "system"]
        if system_msgs:
            # Prepend system context to input
            params["input"] = "\n\n".join(system_msgs) + "\n\n" + input_text
        
        if extra:
            params.update(extra)
        
        return params
    
    # Non-GPT-5: Standard Chat Completions API
    params: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        params["temperature"] = temperature

    # Default if not provided
    limit = max_output_tokens if max_output_tokens is not None else 1024
    params["max_tokens"] = limit

    if extra:
        params.update(extra)

    return params


def get_openai_client(*, api_key: Optional[str] = None, async_mode: bool = False):
    """Return an OpenAI client instance (sync or async)."""
    if async_mode:
        return openai.AsyncOpenAI(api_key=api_key) if api_key else openai.AsyncOpenAI()
    return openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()


def extract_text_from_chat_response(resp: Any) -> str:
    """Best-effort extraction of text from Chat Completions or Responses API response."""
    try:
        # Responses API (GPT-5): has output_text field
        if hasattr(resp, "output_text"):
            return (resp.output_text or "").strip()
        
        # Chat Completions API: has choices array
        choice0 = resp.choices[0] if getattr(resp, "choices", None) else None
        if not choice0:
            return ""
        msg = getattr(choice0, "message", None)
        if not msg:
            return ""
        content = getattr(msg, "content", None)
        return (content or "").strip()
    except Exception as e:
        logger.error("Failed to extract text from OpenAI response", exc_info=e)
        return ""


async def acreate_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    client=None,
    api_key: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Any]:
    """Async convenience wrapper that creates a chat completion and returns (text, raw_response).
    
    Automatically routes to Responses API for GPT-5 models, Chat Completions API for others.
    """
    cli = client or get_openai_client(api_key=api_key, async_mode=True)
    params = build_chat_params(
        model,
        messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        extra=extra,
    )
    
    # Route to correct API based on model
    if is_gpt5_model(model):
        resp = await cli.responses.create(**params)
    else:
        resp = await cli.chat.completions.create(**params)
    
    return extract_text_from_chat_response(resp), resp


def create_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    client=None,
    api_key: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Any]:
    """Sync convenience wrapper that creates a chat completion and returns (text, raw_response).
    
    Automatically routes to Responses API for GPT-5 models, Chat Completions API for others.
    """
    cli = client or get_openai_client(api_key=api_key, async_mode=False)
    params = build_chat_params(
        model,
        messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        extra=extra,
    )
    
    # Route to correct API based on model
    if is_gpt5_model(model):
        resp = cli.responses.create(**params)
    else:
        resp = cli.chat.completions.create(**params)
    
    return extract_text_from_chat_response(resp), resp
