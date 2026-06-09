"""Handler registry for operation dispatch.

Each registered handler implements the `OperationHandler` protocol and is
identified by a `kind` string matching the `dispatch.kind` in `type.json`.
The operation dispatcher uses `get(kind)` to look up a handler at call time.

Built-in handlers (`mcp_tool`, `native`, `artifact_crud`) are registered at
app startup in `main.py` via `register_builtin_handlers()`.
"""

from __future__ import annotations

import asyncio
import functools
import importlib
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSONPath-lite resolution
# ---------------------------------------------------------------------------

def resolve_ref(
    ref: Any,
    artifact: Dict[str, Any],
    *,
    body: Optional[Dict[str, Any]] = None,
    ctx: Any = None,
) -> Any:
    """Resolve a reference against an artifact document, the dispatch
    request body, the dispatch context, or a graph relationship edge.

    Supported roots:
    - `$._key`, `$.context.foo.bar` → walks the artifact document. The
      `context` field is opportunistically JSON-decoded if stored as a string.
    - `$.body.name`, `$.body.arguments.query` → walks the dispatch request body.
    - `$.ctx.user_id`, `$.ctx.actor_id` → reads named attributes off the
      `DispatchContext` object.
    - `@relationship.<name>` → follows a relationship edge of the given
      name from the artifact and returns the target's `root_id`. Requires
      `ctx.arango_db` to be set (available during dispatch).

    Literal strings (no leading `$.` or `@`) are returned as-is. Non-string
    refs (numbers, dicts) are returned as-is. Missing paths return `None`.
    """
    if not isinstance(ref, str):
        return ref
    if ref.startswith("@relationship."):
        return _resolve_relationship_edge(ref, artifact, ctx)
    if not ref.startswith("$."):
        return ref

    parts = ref[2:].split(".")
    if not parts:
        return None

    first = parts[0]
    remainder = parts[1:]

    if first == "body":
        return _walk_dict(body, remainder)
    if first == "ctx":
        if ctx is None or not remainder:
            return None
        attr = remainder[0]
        cur: Any = getattr(ctx, attr, None)
        return _walk_dict(cur, remainder[1:]) if len(remainder) > 1 else cur

    # Default root: the artifact document itself. Reinclude `first` in the walk.
    return _walk_dict(artifact, parts)


def _resolve_relationship_edge(ref: str, artifact: Dict[str, Any], ctx: Any) -> Optional[str]:
    """Follow a ``@relationship.<name>`` ref to find the target root_id.

    Looks up the artifact's `root_id` (stable identity) and queries
    `collection_artifacts` edges with the matching `relationship` label.
    Returns the target `root_id` or ``None``.
    """
    relationship_name = ref[len("@relationship."):]
    if not relationship_name:
        return None

    db = getattr(ctx, "arango_db", None) if ctx is not None else None
    if db is None:
        logger.warning("@relationship ref '%s' requires DB context but ctx.arango_db is None", ref)
        return None

    from_root_id = artifact.get("root_id") or artifact.get("_key")
    if not from_root_id:
        return None

    from db.arango import get_relationship_target
    return get_relationship_target(db, from_root_id, relationship_name)


def _resolve_input_mapping(mapping: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve ``$.field`` and ``$.field[N]`` refs in *mapping* against *params*.

    Simpler than :func:`resolve_ref` — used for the ``context.run.input_mapping``
    block on a transform artifact, where refs point into a flat params dict
    rather than the artifact structure. Non-string values and strings not
    starting with ``$.`` are passed through unchanged. Keys that resolve to
    ``None`` are omitted.
    """
    result: Dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, str) and value.startswith("$."):
            path = value[2:]
            if "[" in path:
                field, rest = path.split("[", 1)
                try:
                    idx = int(rest.rstrip("]"))
                except ValueError:
                    idx = 0
                raw = params.get(field)
                resolved = raw[idx] if isinstance(raw, list) and len(raw) > idx else None
            else:
                resolved = params.get(path)
            if resolved is not None:
                result[key] = resolved
        else:
            result[key] = value
    return result


def _walk_dict(root: Any, parts: list[str]) -> Any:
    """Walk a dict (or JSON-string-containing-dict) along a dotted path."""
    cur: Any = root
    for part in parts:
        if cur is None:
            return None
        if isinstance(cur, str):
            import json
            try:
                cur = json.loads(cur)
            except Exception:
                return None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class OperationHandler(Protocol):
    kind: str

    async def run(
        self,
        artifact: Dict[str, Any],
        op_spec: "OperationSpec",
        body: Dict[str, Any],
        ctx: "DispatchContext",
    ) -> Any:
        ...


# Forward reference types — defined in operation_dispatcher to avoid circular import.
# We import lazily inside run() or use Any-typed duck typing here.
OperationSpec = Any  # dispatcher's OperationSpec dataclass
DispatchContext = Any  # dispatcher's DispatchContext


# ---------------------------------------------------------------------------
# Registry state
# ---------------------------------------------------------------------------

_handlers: Dict[str, OperationHandler] = {}
_native_targets: Dict[str, Callable[..., Awaitable[Any]]] = {}


def register(kind: str, handler: OperationHandler) -> None:
    """Register a handler for a dispatch kind. Overwrites any existing entry."""
    _handlers[kind] = handler
    logger.info("Registered operation handler: %s", kind)


def get(kind: str) -> Optional[OperationHandler]:
    """Look up a handler by kind. Returns None if not registered."""
    return _handlers.get(kind)


def clear() -> None:
    """Clear all handlers (for tests)."""
    _handlers.clear()
    _native_targets.clear()


def register_native_target(name: str, func: Callable[..., Awaitable[Any]]) -> None:
    """Register a callable that the `native` handler can invoke by name."""
    _native_targets[name] = func


def get_native_target(name: str) -> Optional[Callable[..., Awaitable[Any]]]:
    """Look up a registered native callable. Falls back to importlib if
    `name` is a dotted module path and nothing is registered."""
    if name in _native_targets:
        return _native_targets[name]
    # Fallback: dotted import path (e.g. "services.auth_service.generate_api_key"
    # or short form "auth_service.generate_api_key" resolved under services/).
    if "." in name:
        mod_name, _, attr = name.rpartition(".")
        candidates = [mod_name]
        if not mod_name.startswith("services.") and not mod_name.startswith("core."):
            candidates.insert(0, f"services.{mod_name}")
        for candidate in candidates:
            try:
                mod = importlib.import_module(candidate)
                target = getattr(mod, attr, None)
                if callable(target):
                    return target
            except Exception as exc:
                logger.debug("Native target import failed for %s (%s): %s", name, candidate, exc)
    return None


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------

@dataclass
class McpToolHandler:
    """Dispatch kind ``mcp_tool`` — call an MCP server tool.

    ``op_spec.dispatch`` must provide literal or resolved ``server_ref``
    and ``tool_ref`` strings. Both are resolved through ``resolve_ref``:

    - Literal string (e.g. ``"verso"``) — passed through unchanged.
    - ``$.path`` ref — walked from the artifact document.
    - ``@relationship.edge`` ref — resolved via graph edge traversal.

    If either ref fails to resolve, the handler raises ``ValueError``.
    No fallback path is supported — dispatch must be explicit.
    """

    kind: str = "mcp_tool"

    async def run(
        self,
        artifact: Dict[str, Any],
        op_spec: Any,
        body: Dict[str, Any],
        ctx: Any,
    ) -> Any:
        dispatch = op_spec.dispatch or {}

        # Primary: per-artifact routing resolved from the dispatch block.
        server_id = resolve_ref(dispatch.get("server_ref"), artifact, body=body, ctx=ctx)
        tool_name = resolve_ref(dispatch.get("tool_ref"), artifact, body=body, ctx=ctx)

        if not server_id or not tool_name:
            raise ValueError(
                f"mcp_tool dispatch could not resolve server "
                f"({dispatch.get('server_ref')!r}) or tool "
                f"({dispatch.get('tool_ref')!r}) from artifact/body/ctx"
            )

        from services import chorus_client, server_registry

        # Highest precedence: explicit argument refs declared in the dispatch
        # block, resolved against the artifact / body / ctx via resolve_ref.
        # This lets a type pass its own artifact fields (e.g. content + id) to
        # the tool without a transform-style context.run block — used by the
        # authorizer's invoke → seraph:provide_access_token dispatch.
        dispatch_args = dispatch.get("arguments")
        if isinstance(dispatch_args, dict) and dispatch_args:
            resolved_args = {
                key: resolve_ref(val, artifact, body=body, ctx=ctx)
                for key, val in dispatch_args.items()
            }
            arguments = {k: v for k, v in resolved_args.items() if v is not None}
        else:
            # Resolve input_mapping from the artifact's context.run block.
            # This maps invoke body fields (workspace_id, artifacts[0], etc.)
            # to the tool's expected parameter names (e.g. artifact_id).
            input_mapping = resolve_ref("$.context.run.input_mapping", artifact)
            if isinstance(input_mapping, dict) and input_mapping:
                # Build a flat params dict from the invoke body for mapping resolution
                mapping_source: Dict[str, Any] = {}
                if isinstance(body, dict):
                    mapping_source.update(body.get("params") or {})
                    for k in ("workspace_id", "artifacts", "input"):
                        if k in body and k not in mapping_source:
                            mapping_source[k] = body[k]
                arguments = _resolve_input_mapping(input_mapping, mapping_source)
            else:
                arguments = body.get("arguments", {}) if isinstance(body, dict) else {}

        # Resolve short persona name to UUID for chorus's universal-gateway
        # route. Type schemas may declare server_ref as either a short name
        # ("verso") or a UUID — handle both.
        target_server_id = str(server_id)
        if not chorus_client.is_uuid_like(target_server_id):
            resolved = server_registry.resolve_name_to_id(target_server_id)
            if not resolved:
                raise ValueError(
                    f"mcp_tool dispatch: server '{target_server_id}' is not a known persona "
                    f"and not a UUID. Set server_ref to either a registered short name "
                    f"or the seeded server artifact UUID."
                )
            target_server_id = resolved

        logger.info(
            "mcp_tool dispatch: server=%s tool=%s arguments=%s",
            target_server_id, tool_name, arguments,
        )

        # chorus_client.call_tool is synchronous (httpx.Client); run it in a
        # thread-pool executor to keep the asyncio event loop unblocked.
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            functools.partial(
                chorus_client.call_tool,
                target_server_id,
                str(tool_name),
                arguments or {},
                user_id=ctx.user_id,
            ),
        )

        logger.info("mcp_tool result: server=%s tool=%s result=%s", target_server_id, tool_name, result)
        return result


@dataclass
class NativeHandler:
    """Dispatch kind `native` — call a registered Python callable by name."""

    kind: str = "native"

    async def run(
        self,
        artifact: Dict[str, Any],
        op_spec: Any,
        body: Dict[str, Any],
        ctx: Any,
    ) -> Any:
        dispatch = op_spec.dispatch or {}
        target_name = dispatch.get("target")
        if not target_name:
            raise ValueError("native dispatch missing 'target'")

        target = get_native_target(str(target_name))
        if target is None:
            raise ValueError(f"native dispatch target '{target_name}' not registered")

        if asyncio.iscoroutinefunction(target):
            return await target(artifact, body, ctx)

        # Sync callable — run in a thread-pool executor so the asyncio event
        # loop is not blocked during network calls (e.g. chorus_client).
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(target, artifact, body, ctx),
        )


@dataclass
class ArtifactCrudHandler:
    """Dispatch kind `artifact_crud` — default create/read/update/delete.

    This is a thin pass-through that lets the dispatcher wrap existing
    router→service CRUD paths in the emit envelope without re-implementing
    them. The router calls its existing service function and hands the result
    back to the dispatcher; the handler is a no-op placeholder so the
    dispatcher can still look up a handler and emit events around the call.
    """

    kind: str = "artifact_crud"

    async def run(
        self,
        artifact: Dict[str, Any],
        op_spec: Any,
        body: Dict[str, Any],
        ctx: Any,
    ) -> Any:
        # When the dispatcher is invoked with kind=artifact_crud, the caller
        # supplies a `ctx.inner_result` (already-computed service result) or
        # a `ctx.inner_callable` to run so the dispatcher wraps the call in
        # its emit envelope without re-implementing the service call.
        inner = getattr(ctx, "inner_callable", None)
        if inner is not None:
            result = inner()
            if hasattr(result, "__await__"):
                return await result
            return result
        return getattr(ctx, "inner_result", None)


def register_builtin_handlers() -> None:
    """Register the default set of dispatch handlers. Called from main.py lifespan."""
    register("mcp_tool", McpToolHandler())
    register("native", NativeHandler())
    register("artifact_crud", ArtifactCrudHandler())
