"""Agent plugin registry utilities.

This module provides a very small and safe surface for locating agent
entrypoints inside the ``agents`` package. Agent identifiers are resolved to
callables located beneath this package only; attempting to traverse outside of
``agents`` (e.g. via ``..`` or absolute imports) is rejected. Identifiers can
optionally specify a function using ``module:attr`` syntax, and fall back to the
``AGENT`` attribute or a callable sharing the module name when omitted.

The goal is to keep agent discovery self-contained so callers never need to
import concrete agent modules directly.
"""

from __future__ import annotations

import importlib
import inspect
import re
from functools import lru_cache
from typing import Callable

_SAFE_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class AgentNotFoundError(LookupError):
	"""Raised when an agent identifier cannot be resolved."""


def _normalise_segment(segment: str) -> str:
	candidate = segment.strip().replace("-", "_").replace("/", ".")
	if not candidate:
		raise AgentNotFoundError("Agent identifier contains empty segment")
	if ".." in candidate:
		raise AgentNotFoundError("Agent identifier cannot traverse directories")
	if not _SAFE_SEGMENT.fullmatch(candidate):
		raise AgentNotFoundError(f"Invalid agent segment '{segment}'")
	return candidate


def _normalise_attr(attr: str) -> str:
	attr_candidate = attr.strip().replace("-", "_")
	if not attr_candidate:
		raise AgentNotFoundError("Agent attribute cannot be empty")
	if not _SAFE_SEGMENT.fullmatch(attr_candidate):
		raise AgentNotFoundError(f"Invalid agent attribute '{attr}'")
	return attr_candidate


def _compose_module_name(identifier: str) -> tuple[str, str | None]:
	module_part, sep, attr_part = identifier.partition(":")
	if not module_part.strip():
		raise AgentNotFoundError("Agent identifier must include a module name")

	dotted = module_part.replace("/", ".")
	segments = [_normalise_segment(seg) for seg in dotted.split(".") if seg]
	if not segments:
		raise AgentNotFoundError("Agent identifier resolved to no module segments")

	module_name = ".".join([__name__] + segments)
	attr_name = _normalise_attr(attr_part) if sep else None
	return module_name, attr_name


@lru_cache(maxsize=64)
def get_agent_callable(identifier: str) -> Callable[..., object]:
	"""Resolve an agent identifier to a callable.

	Agent identifiers are limited to files/packages inside ``agents``. The
	optional ``":attr"`` suffix allows selecting a specific callable; without it
	we look for an ``AGENT`` attribute, then a callable named after the module's
	final segment, and finally fall back to the first callable exported via
	``__all__``.
	"""

	if not identifier or not identifier.strip():
		raise AgentNotFoundError("Agent identifier cannot be blank")

	module_name, attr_name = _compose_module_name(identifier.strip())

	try:
		module = importlib.import_module(module_name)
	except ModuleNotFoundError as exc:
		raise AgentNotFoundError(f"Agent module '{module_name}' not found") from exc

	candidates: list[str] = []
	if attr_name:
		candidates.append(attr_name)
	else:
		if hasattr(module, "AGENT"):
			agent_obj = getattr(module, "AGENT")
			if callable(agent_obj):
				return agent_obj
		tail = module_name.rsplit(".", 1)[-1]
		candidates.extend([tail, f"{tail}_agent"])
		exports = getattr(module, "__all__", [])
		if isinstance(exports, (list, tuple)):
			for name in exports:
				if isinstance(name, str):
					candidates.append(name)

	for candidate in candidates:
		if not isinstance(candidate, str):
			continue
		if not hasattr(module, candidate):
			continue
		attr = getattr(module, candidate)
		if callable(attr):
			return attr

	# As a last resort iterate members, but avoid exposing non-agent details.
	for name, attr in inspect.getmembers(module, callable):
		if name.startswith("_"):
			continue
		return attr

	raise AgentNotFoundError(f"No callable entrypoint found in '{module_name}'")


__all__ = ["get_agent_callable", "AgentNotFoundError"]

