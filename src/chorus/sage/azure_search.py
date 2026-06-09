"""Azure AI Search (Cognitive Search) adapter.

Treats Azure Search as a *derived index* (projection) of platform cards.
Does not own source-of-truth data — all card data lives in the platform.

Used by agience-server-sage as an optional retrieval backend alongside
the platform's built-in OpenSearch index.

Ported from: mcp-servers/_pending/azure_search.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AzureSearchConfig:
    endpoint: str
    api_key: str
    api_version: str
    docs_index: str
    chunks_index: str
    request_timeout_s: float = 10.0


class AzureSearchError(RuntimeError):
    pass


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.rstrip("/")


def parse_connection(connection: Dict[str, Any]) -> AzureSearchConfig:
    """Parse a connection dict (from a card's context.connection field) into config.

    Per-user/per-tenant config is passed at tool-call time — no server-level
    env vars required. This lets multiple tenants use different Azure indexes
    from a single Sage server instance.
    """
    endpoint = str(connection.get("endpoint") or "").strip()
    api_key = str(connection.get("api_key") or "").strip()
    if not endpoint:
        raise ValueError("connection.endpoint is required")
    if not api_key:
        raise ValueError("connection.api_key is required")

    return AzureSearchConfig(
        endpoint=_normalize_endpoint(endpoint),
        api_key=api_key,
        api_version=str(connection.get("api_version") or "2023-11-01").strip(),
        docs_index=str(connection.get("docs_index") or "artifacts_docs").strip(),
        chunks_index=str(connection.get("chunks_index") or "artifacts_chunks").strip(),
        request_timeout_s=float(connection.get("request_timeout_s") or 10.0),
    )


def _to_json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_to_json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    return str(obj)


def _azure_doc_from_artifact(doc: Dict[str, Any], *, doc_id: str) -> Dict[str, Any]:
    """Map a platform card/OpenSearch doc to an Azure Search document."""
    mapped: Dict[str, Any] = {"id": doc_id}
    for key, value in doc.items():
        if key in {"_id", "content_vector"}:
            continue
        if key == "metadata":
            try:
                mapped["metadata_json"] = json.dumps(_to_json_safe(value), ensure_ascii=False)
            except Exception:
                mapped["metadata_json"] = json.dumps({"_error": "failed_to_serialize"})
            continue
        mapped[key] = _to_json_safe(value)
    return mapped


class AzureSearchClient:
    def __init__(self, cfg: AzureSearchConfig) -> None:
        self._cfg = cfg

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "api-key": self._cfg.api_key}

    def _index_url(self, index_name: str) -> str:
        return (
            f"{self._cfg.endpoint}/indexes/{index_name}/docs/index"
            f"?api-version={self._cfg.api_version}"
        )

    def merge_or_upload(self, index_name: str, docs: List[Dict[str, Any]]) -> None:
        if not docs:
            return
        payload = {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in docs]}
        with httpx.Client(timeout=httpx.Timeout(self._cfg.request_timeout_s)) as client:
            resp = client.post(self._index_url(index_name), headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise AzureSearchError(
                f"Azure Search indexing failed ({resp.status_code}): {resp.text[:500]}"
            )

    async def search(self, index_name: str, query: str, top: int = 10) -> List[Dict[str, Any]]:
        url = (
            f"{self._cfg.endpoint}/indexes/{index_name}/docs/search"
            f"?api-version={self._cfg.api_version}"
        )
        payload = {"search": query, "top": top, "queryType": "simple"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(self._cfg.request_timeout_s)) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
        if resp.status_code >= 400:
            raise AzureSearchError(
                f"Azure Search query failed ({resp.status_code}): {resp.text[:500]}"
            )
        return resp.json().get("value", [])


def _iter_batches(items: List[Any], batch_size: int = 500) -> Iterable[List[Any]]:
    for i in range(0, len(items), batch_size):
        yield items[i: i + batch_size]


def upsert_artifacts(*, connection: Dict[str, Any], docs: List[Dict[str, Any]]) -> None:
    """Upsert artifact documents into the docs index."""
    cfg = parse_connection(connection)
    client = AzureSearchClient(cfg)
    azure_docs = []
    for doc in docs:
        doc_id = str(doc.get("_id") or doc.get("id") or "")
        if doc_id:
            azure_docs.append(_azure_doc_from_artifact(doc, doc_id=doc_id))
    for batch in _iter_batches(azure_docs):
        client.merge_or_upload(cfg.docs_index, batch)


def upsert_chunks(*, connection: Dict[str, Any], chunks: List[Dict[str, Any]]) -> None:
    """Upsert chunk documents into the chunks index."""
    cfg = parse_connection(connection)
    client = AzureSearchClient(cfg)
    azure_chunks = []
    for doc in chunks:
        doc_id = str(doc.get("_id") or doc.get("id") or "")
        if doc_id:
            azure_chunks.append(_azure_doc_from_artifact(doc, doc_id=doc_id))
    for batch in _iter_batches(azure_chunks):
        client.merge_or_upload(cfg.chunks_index, batch)
