"""Provider-agnostic embeddings.

Default = Agience embeddings server (HTTP). Any provider that exposes
``POST /embed`` returning ``{"vectors": [[float], ...]}`` plugs in via
``EMBEDDINGS_PROVIDER`` + ``EMBEDDINGS_URI`` env / settings.

The historical OpenAI provider is intentionally absent from the platform
default. A future Beacon LLM / embeddings drop-in can register here under
its own provider name without touching call sites.

Call site convention is unchanged from the previous OpenAI-bound
implementation: ``Embeddings()(["text 1", "text 2"]) -> [[float], [float]]``.
That signature is preserved so existing code (search ingest, accessor)
keeps working.
"""

from __future__ import annotations

import logging
import os
from typing import List, Protocol

import httpx

from kernel import config

logger = logging.getLogger(__name__)


def model_id() -> str:
    """Commons-format embedding model id (``<ns>:<path>@<ver>``).

    Provenance for every vector / native code (FACET embedding-registry). The
    AnchorSet is the authoritative source once bootstrapped; this is the
    fallback derived from ``EMBEDDINGS_MODEL`` (default the bge-m3 deployment).
    """
    raw = (os.getenv("EMBEDDINGS_MODEL", "BAAI/bge-m3") or "BAAI/bge-m3").strip()
    ver = (os.getenv("EMBEDDINGS_MODEL_VERSION", "1.0") or "1.0").strip()
    if any(raw.startswith(p) for p in ("hf:", "openai:", "custom:", "facet:")):
        return raw if "@" in raw else f"{raw}@{ver}"
    return f"hf:{raw}@{ver}"


class EmbeddingsProvider(Protocol):
    """Contract every embeddings backend conforms to.

    Implementations should be deterministic for the same input + model
    version, return vectors in declared `EMBEDDINGS_DIM` dimensions, and
    surface failures by returning an empty list (callers fall back to
    BM25-only search rather than crashing the request).
    """

    def __call__(self, input: List[str]) -> List[List[float]]: ...


# ---------------------------------------------------------------------------
# Agience HTTP provider (default)
# ---------------------------------------------------------------------------

class AgienceHTTPEmbeddings:
    """Calls the Agience embeddings server over HTTP.

    Wire format (request)::

        POST {EMBEDDINGS_URI}/embed
        Authorization: Bearer {EMBEDDINGS_API_KEY?}
        Content-Type: application/json

        { "input": ["text 1", "text 2"] }

    Wire format (response)::

        { "vectors": [[float, ...], [float, ...]] }

    Errors return an empty list — the caller decides how to degrade.
    """

    def __init__(
        self,
        uri: str,
        api_key: str | None = None,
        *,
        timeout_s: float = 5.0,
    ) -> None:
        self._uri = uri.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout_s)

    def __call__(self, input: List[str]) -> List[List[float]]:
        if not input:
            return []
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            resp = self._client.post(
                f"{self._uri}/embed",
                json={"input": input},
                headers=headers,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            vectors = payload.get("vectors") or []
            if not isinstance(vectors, list):
                logger.warning(
                    "embeddings: malformed response (vectors not a list)"
                )
                return []
            return vectors
        except httpx.HTTPError as exc:
            logger.warning("embeddings: HTTP error from %s: %s", self._uri, exc)
            return []
        except (ValueError, KeyError) as exc:
            logger.warning("embeddings: malformed JSON from %s: %s", self._uri, exc)
            return []


# ---------------------------------------------------------------------------
# Stub provider (used when no embeddings server is configured)
# ---------------------------------------------------------------------------

class _UnconfiguredEmbeddings:
    """Returns empty lists — search degrades to BM25-only.

    Active when ``EMBEDDINGS_URI`` isn't set. Logs once on first call so
    the operator knows semantic search is offline; subsequent calls stay
    silent to avoid log spam.
    """

    def __init__(self) -> None:
        self._warned = False

    def __call__(self, input: List[str]) -> List[List[float]]:
        if input and not self._warned:
            logger.warning(
                "embeddings: no provider configured "
                "(set EMBEDDINGS_URI or EMBEDDINGS_PROVIDER); "
                "semantic search returns empty vectors"
            )
            self._warned = True
        return []


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------

class OpenAIEmbeddings:
    """Calls OpenAI's embeddings endpoint.

    Activated when ``EMBEDDINGS_PROVIDER=openai``.  Uses
    ``EMBEDDINGS_API_KEY`` and falls back to ``LLM_API_KEY`` so local dev
    with a single OpenAI key needs no extra config.

    Model ``text-embedding-3-small`` supports the ``dimensions`` param;
    we pass ``EMBEDDINGS_DIM`` (default 1024) to keep vector sizes
    consistent with the rest of the search stack.
    """

    _MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str, dimensions: int = 1024) -> None:
        self._api_key = api_key
        self._dimensions = dimensions
        self._client = httpx.Client(timeout=10.0)

    def __call__(self, input: List[str]) -> List[List[float]]:
        if not input:
            return []
        try:
            resp = self._client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._MODEL,
                    "input": input,
                    "dimensions": self._dimensions,
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data") or []
            return [item["embedding"] for item in data]
        except httpx.HTTPError as exc:
            logger.warning("embeddings: OpenAI HTTP error: %s", exc)
            return []
        except (KeyError, ValueError) as exc:
            logger.warning("embeddings: OpenAI malformed response: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider: EmbeddingsProvider | None = None

# Long-term embeddings cache (lazy singleton). See embeddings_cache.py.
_cache = None
_cache_loaded = False


def _build_provider() -> EmbeddingsProvider:
    """Construct the provider implied by current `config` values.

    Resolution order:
    1. ``EMBEDDINGS_URI`` set → :class:`AgienceHTTPEmbeddings`
    2. ``EMBEDDINGS_PROVIDER=openai`` → :class:`OpenAIEmbeddings`
    3. otherwise → :class:`_UnconfiguredEmbeddings` (BM25-only fallback)
    """
    uri = (config.EMBEDDINGS_URI or "").strip()
    if uri:
        return AgienceHTTPEmbeddings(uri, config.EMBEDDINGS_API_KEY)
    if (config.EMBEDDINGS_PROVIDER or "").lower() == "openai":
        api_key = config.EMBEDDINGS_API_KEY or config.LLM_API_KEY
        if api_key:
            return OpenAIEmbeddings(api_key, config.EMBEDDINGS_DIM)
    return _UnconfiguredEmbeddings()


def reset_provider() -> None:
    """Drop the cached provider so the next call rebuilds from config.

    Called by the platform-settings reload path when an operator changes
    embeddings config from the admin UI.
    """
    global _provider, _cache, _cache_loaded
    _provider = None
    _cache = None
    _cache_loaded = False


def _get_cache():
    """Lazy singleton embeddings cache. ``None`` when disabled/unavailable."""
    global _cache, _cache_loaded
    if _cache_loaded:
        return _cache
    if os.getenv("EMBEDDINGS_CACHE", "1").strip().lower() in {"0", "false", "no", "off"}:
        _cache, _cache_loaded = None, True
        return None
    try:
        from kernel.embeddings_cache import EmbeddingsCache
        path = os.getenv("EMBEDDINGS_CACHE_PATH") or str(
            config.BASE_DIR / ".data" / "mantle" / "embeddings_cache.sqlite"
        )
        _cache = EmbeddingsCache(path)
        logger.info("Embeddings cache enabled: %s (%d entries)", path, _cache.count())
    except Exception:
        logger.warning("Embeddings cache unavailable; continuing without it", exc_info=True)
        _cache = None
    _cache_loaded = True
    return _cache


class Embeddings:
    """Provider facade with a transparent long-term cache.

    Existing call sites keep working as ``Embeddings()([texts])``. Cached
    vectors (keyed by model_id + text) short-circuit the provider, so repeated
    embeds of the same text — seeds, reindex, recurring queries — never re-hit
    the (paid, GPU) embedder. Empty/degraded results are never cached, so an
    unconfigured-provider run won't poison the cache.
    """

    def __call__(self, input: List[str]) -> List[List[float]]:
        global _provider
        if _provider is None:
            _provider = _build_provider()
        if not input:
            return []

        cache = _get_cache()
        if cache is None:
            return _provider(input)

        mid = model_id()
        cached = cache.get_many(mid, input)
        misses = [i for i, v in enumerate(cached) if v is None]
        if misses:
            fresh = _provider([input[i] for i in misses]) or []
            store_texts: List[str] = []
            store_vecs: List[List[float]] = []
            for j, i in enumerate(misses):
                v = fresh[j] if j < len(fresh) else None
                cached[i] = v
                if v:
                    store_texts.append(input[i])
                    store_vecs.append(v)
            if store_vecs:
                try:
                    cache.put_many(mid, store_texts, store_vecs)
                except Exception:
                    logger.debug("embeddings cache write failed", exc_info=True)
        return [v if v else [] for v in cached]


__all__ = [
    "AgienceHTTPEmbeddings",
    "Embeddings",
    "EmbeddingsProvider",
    "OpenAIEmbeddings",
    "reset_provider",
]
