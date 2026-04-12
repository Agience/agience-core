# db/opensearch.py
# type: ignore[import, attr-defined, call-arg, arg-type]
# OpenSearch Python client has incomplete type stubs; parameter names vary by version.
# This file works correctly at runtime.
import os
import time
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import NotFoundError, RequestError, AuthenticationException, AuthorizationException, ConnectionError, TransportError

from core import config

logger = logging.getLogger(__name__)


def _redact_vectors(obj: Any, _depth: int = 0) -> Any:
    """Recursively replace any vector-like value with a short placeholder.

    Matches dict keys ending in '_vector' or any bare list-of-floats value
    (len > 8), so embeddings never appear in log output regardless of nesting.
    """
    if _depth > 10:
        return obj
    if isinstance(obj, dict):
        return {
            k: f"<vector[{len(v)}]>" if k.endswith("_vector") and isinstance(v, list)
            else _redact_vectors(v, _depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        if len(obj) > 8 and all(isinstance(x, float) for x in obj[:8]):
            return f"<vector[{len(obj)}]>"
        return [_redact_vectors(x, _depth + 1) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_vectors(x, _depth + 1) for x in obj)
    return obj


# Global client instance
_opensearch_client: Optional[OpenSearch] = None

# Rate-limit noisy OpenSearch "index blocked" warnings (common in local dev when disk is low)
_LAST_OS_BLOCK_WARNING_AT: float = 0.0
_OS_BLOCK_WARNING_INTERVAL_S: float = 60.0


def _is_floodstage_readonly_allow_delete(exc: Exception) -> bool:
    if not isinstance(exc, TransportError):
        return False
    status = getattr(exc, "status_code", None)
    if status not in (403, 429):
        return False
    msg = str(exc).lower()
    # Message text varies by version; key signals are cluster block + read-only allow delete.
    return "cluster_block_exception" in msg and "read-only-allow-delete" in msg


def _warn_block_rate_limited(message: str) -> None:
    global _LAST_OS_BLOCK_WARNING_AT
    now = time.time()
    if now - _LAST_OS_BLOCK_WARNING_AT >= _OS_BLOCK_WARNING_INTERVAL_S:
        logger.warning(message)
        _LAST_OS_BLOCK_WARNING_AT = now
    else:
        logger.debug(message)

def _build_client(user: Optional[str], pwd: Optional[str]) -> OpenSearch:
    """Create a client honoring your SSL flags. Works with new/old opensearch-py."""
    kwargs = {
        "hosts": [{"host": config.OPENSEARCH_HOST, "port": config.OPENSEARCH_PORT}],
        "scheme": "https" if config.OPENSEARCH_USE_SSL else "http",
        "use_ssl": config.OPENSEARCH_USE_SSL,
        "verify_certs": config.OPENSEARCH_VERIFY_CERTS if config.OPENSEARCH_USE_SSL else False,
        "ssl_assert_hostname": False,
        "ssl_show_warn": False,
        # pool tuning
        "maxsize": 10,                 # default can be 1 in some builds
        "retry_on_timeout": True,
    }
    if user:
        kwargs["basic_auth"] = (user, pwd or "")
        # keep http_auth for older client versions if you need to support both:
        kwargs["http_auth"] = (user, pwd or "")
    return OpenSearch(**kwargs)

def _probe(client: OpenSearch, timeout_s: Optional[float] = None) -> None:
    """Force a request that triggers auth; wait briefly for cold starts.

    Important: do NOT rely on cluster-level health endpoints here.
    In OpenSearch Security, application users are often intentionally denied
    cluster monitor permissions (e.g. `cluster:monitor/health`). Using
    `client.cluster.health()` here can cause noisy 403 retry loops.

    We instead probe via an index-scoped request against an index pattern the
    app is allowed to access (artifacts). This still exercises:
    - connectivity + TLS
    - authentication
    - authorization (index-level)
    """
    if timeout_s is None:
        timeout_s = config.OPENSEARCH_REQUEST_TIMEOUT_S
    deadline = time.time() + config.OPENSEARCH_STARTUP_DEADLINE_S  # Allow for cold starts and security init
    retry_delay = 1.0  # Start with 1-second delay
    start_time = time.time()
    attempt = 0

    while True:
        try:
            # HEAD /artifacts (exists or 404 both prove the service is reachable and auth works)
            # NOTE: this call is permitted by our app role's index_permissions.
            client.indices.exists(index="artifacts", request_timeout=timeout_s)
            return
        except AuthorizationException as e:
            # This is a permanent configuration error (valid creds, insufficient permissions).
            # Don't spin for 120s.
            logger.error(
                "OpenSearch authorization error during startup probe: %s. "
                "The configured user '%s' must have index permissions for 'artifacts*'.",
                e,
                config.OPENSEARCH_USERNAME or "<anonymous>",
            )
            raise
        except AuthenticationException as e:
            logger.error(
                "OpenSearch authentication failed during startup probe for user '%s': %s",
                config.OPENSEARCH_USERNAME or "<anonymous>",
                e,
            )
            raise
        except TransportError as e:
            # Check if it's a transient 503 (security not initialized) vs permanent SSL/auth error
            error_status = getattr(e, "status_code", None)
            error_msg = str(e).lower()
            
            # Fail fast on persistent SSL/TLS config errors (bad cert, wrong protocol).
            # Do NOT fail fast on UNEXPECTED_EOF_WHILE_READING -- that is a transient startup
            # race where OpenSearch's TLS listener isn't ready yet; it should be retried.
            is_transient_ssl = "unexpected_eof" in error_msg or "eof occurred" in error_msg
            is_ssl_error = "ssl" in error_msg or "certificate" in error_msg or "tls" in error_msg
            if is_ssl_error and not is_transient_ssl:
                logger.error(f"SSL/TLS error - failing immediately: {e}")
                raise
            
            # Fail fast on permanent auth errors
            if "authentication" in error_msg or "unauthorized" in error_msg or "forbidden" in error_msg:
                logger.error(f"Authentication error - failing immediately: {e}")
                raise
            
            # Retry on 503 (transient - security initializing)
            if error_status == 503:
                elapsed = time.time() - start_time
                attempt += 1
                logger.warning("Waiting for OpenSearch (503 -- security initializing, attempt %d, %.1fs elapsed)", attempt, elapsed)
                if time.time() > deadline:
                    logger.error("Timeout waiting for OpenSearch security to initialize after %.1fs", elapsed)
                    raise
                time.sleep(min(retry_delay, 3.0))  # Cap at 3 seconds for slow poll
                retry_delay = min(retry_delay * 1.5, 3.0)  # Exponential backoff up to 3s
                continue

            # Fail fast on 401/403 from our probe endpoint.
            if error_status in (401, 403):
                logger.error(
                    "OpenSearch returned %s during startup probe (permanent). "
                    "Check OPENSEARCH_USERNAME/OPENSEARCH_PASSWORD and role permissions.",
                    error_status,
                )
                raise

            # For other transport errors, use exponential backoff
            elapsed = time.time() - start_time
            attempt += 1
            logger.warning("Waiting for OpenSearch (transport error status=%s, attempt %d, %.1fs elapsed)", error_status, attempt, elapsed)
            if time.time() > deadline:
                raise
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 10.0)
            continue
        except (ConnectionError, TimeoutError):
            elapsed = time.time() - start_time
            if time.time() > deadline:
                logger.error("Timeout waiting for OpenSearch connection after %.1fs", elapsed)
                raise
            attempt += 1
            logger.warning("Waiting for OpenSearch (not ready yet, attempt %d, %.1fs elapsed)", attempt, elapsed)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 10.0)

def get_opensearch_client() -> OpenSearch:
    """Get or create OpenSearch client. Fallback to admin if the app user isn't ready yet."""
    global _opensearch_client
    if _opensearch_client is not None:
        return _opensearch_client

    # 1) try configured credentials (or anonymous if none provided)
    primary_user = config.OPENSEARCH_USERNAME or None
    primary_pwd = config.OPENSEARCH_PASSWORD or None
    client = _build_client(primary_user, primary_pwd)
    try:
        _probe(client)
        _opensearch_client = client
        logger.info(f"OpenSearch client initialized as {primary_user or 'anonymous'}")
        return _opensearch_client
    except AuthenticationException as e:
        logger.warning(f"Auth failed for configured user {primary_user!r}: {e}")

    # 2) fallback to admin if available (e.g. first boot before provisioning runs, or admin-mode config)
    admin_pwd = os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD")
    if admin_pwd and primary_user != "admin":
        admin_client = _build_client("admin", admin_pwd)
        try:
            _probe(admin_client)
            _opensearch_client = admin_client
            logger.warning("OpenSearch fallback: connected as 'admin'. Create app user and switch creds ASAP.")
            return _opensearch_client
        except AuthenticationException as e:
            logger.error(f"Admin fallback authentication failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Admin fallback connection failed: {e}")
            raise
    else:
        logger.error("Auth failed and OPENSEARCH_INITIAL_ADMIN_PASSWORD is not set for fallback.")
        raise

def close_opensearch_client():
    """Close OpenSearch client connection."""
    global _opensearch_client
    if _opensearch_client:
        _opensearch_client.close()
        _opensearch_client = None
        logger.info("OpenSearch client closed")


def create_index_from_mapping(index_name: str, mapping_path: Path) -> bool:
    """
    Create an index from a JSON mapping file.
    Returns True if created, False if already exists.
    """
    client = get_opensearch_client()
    
    if client.indices.exists(index=index_name):
        logger.info(f"Index {index_name} already exists")
        return False
    
    with open(mapping_path, "r") as f:
        mapping = json.load(f)
    
    try:
        client.indices.create(index=index_name, body=mapping)
        logger.info(f"Created index {index_name}")
        return True
    except RequestError as e:
        logger.error(f"Failed to create index {index_name}: {e}")
        raise


def clear_readonly_blocks(index_pattern: str = "artifacts*") -> bool:
    """Clear read-only-allow-delete blocks from indices.

    OpenSearch sets index.blocks.read_only_allow_delete=true when the disk hits the
    flood-stage watermark (default 95%). The block persists even after disk space is
    freed -- this function removes it so writes resume automatically.

    Should be called at startup so that a temporarily-full disk doesn't leave the
    cluster permanently broken after disk space is recovered.

    Returns True if the clear succeeded (or no block existed), False on error.
    """
    client = get_opensearch_client()
    try:
        client.indices.put_settings(
            index=index_pattern,
            body={"index": {"blocks": {"read_only_allow_delete": None}}},
        )
        logger.info(f"Cleared read-only-allow-delete blocks on '{index_pattern}'")
        return True
    except NotFoundError:
        return True  # No matching index -- nothing to clear
    except AuthorizationException as e:
        # 403 in a fresh/local cluster means the security plugin is restricting wildcard
        # settings writes; no flood-stage block exists, so this is harmless.
        logger.debug(f"clear_readonly_blocks: permission denied on '{index_pattern}' (no block to clear): {e}")
        return False
    except Exception as e:
        logger.warning(f"Could not clear read-only blocks on '{index_pattern}': {e}")
        return False


def delete_index(index_name: str) -> bool:
    """Delete an index. Returns True if deleted, False if didn't exist."""
    client = get_opensearch_client()
    
    try:
        client.indices.delete(index=index_name)
        logger.info(f"Deleted index {index_name}")
        return True
    except NotFoundError:
        logger.info(f"Index {index_name} does not exist")
        return False


def index_document(index_name: str, doc_id: str, document: Dict[str, Any]) -> bool:
    """Index a single document asynchronously."""
    client = get_opensearch_client()
    
    try:
        client.index(index=index_name, id=doc_id, body=document, refresh=False)
        logger.debug(f"Indexed document {doc_id} in {index_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to index document {doc_id}: {_redact_vectors(e.args) if hasattr(e, 'args') else e}")
        return False


def bulk_index_documents(
    index_name: str, documents: List[Dict[str, Any]], id_field: str = "_id"
) -> int:
    """
    Bulk index documents asynchronously.
    Returns count of successfully indexed documents.
    """
    client = get_opensearch_client()
    
    if not documents:
        return 0
    
    actions = [
        {
            "_index": index_name,
            "_id": doc.pop(id_field) if id_field in doc else doc.get("_id"),
            "_source": doc,
        }
        for doc in documents
    ]
    
    try:
        success, errors = helpers.bulk(client, actions, refresh=False)
        if errors:
            logger.warning(f"Bulk index had {len(errors)} errors")
        logger.info(f"Bulk indexed {success} documents to {index_name}")
        return success
    except Exception as e:
        logger.error(f"Bulk index failed: {_redact_vectors(e.args) if hasattr(e, 'args') else e}")
        return 0


def get_document(index_name: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """Get a document by ID."""
    client = get_opensearch_client()
    
    try:
        result = client.get(index=index_name, id=doc_id)
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        logger.error(f"Failed to get document {doc_id}: {e}")
        return None


def delete_document(index_name: str, doc_id: str) -> bool:
    """Delete a document by ID."""
    client = get_opensearch_client()
    
    try:
        # Avoid refresh="wait_for" here: under flood-stage disk watermark OpenSearch sets
        # read-only-allow-delete blocks, and refresh can be rejected even when deletes are allowed.
        client.delete(
            index=index_name,
            id=doc_id,
            refresh=False,
            request_timeout=config.OPENSEARCH_REQUEST_TIMEOUT_S,
        )
        logger.debug(f"Deleted document {doc_id} from {index_name}")
        return True
    except NotFoundError:
        logger.debug(f"Document {doc_id} not found in {index_name}")
        return False
    except TransportError as e:
        # In local dev, OpenSearch can hit flood-stage disk watermark and temporarily block indices.
        # This should not crash the app or spam ERROR logs.
        if _is_floodstage_readonly_allow_delete(e):
            _warn_block_rate_limited(
                f"OpenSearch index blocked (flood-stage watermark). "
                f"Delete skipped for {index_name}:{doc_id} (non-fatal): {e}"
            )
            return False
        logger.error(f"Failed to delete document {doc_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        return False


def delete_by_query(index_name: str, query: Dict[str, Any]) -> int:
    """
    Delete documents matching a query.
    Returns count of deleted documents.
    """
    client = get_opensearch_client()
    
    try:
        # NOTE: delete_by_query can be very slow on large indices (especially with forced refresh).
        # For MVP/local we run this in a non-blocking mode to avoid request timeouts.
        result = client.delete_by_query(
            index=index_name,
            body={"query": query},
            refresh=False,
            wait_for_completion=False,
            conflicts="proceed",
            request_timeout=config.OPENSEARCH_REQUEST_TIMEOUT_S,
        )

        # When wait_for_completion=False, OpenSearch returns a task id instead of "deleted".
        deleted = int(result.get("deleted", 0) or 0)
        task = result.get("task")
        if task:
            logger.info(f"Started delete-by-query task on {index_name}: {task}")
        else:
            logger.info(f"Deleted {deleted} documents from {index_name}")
        return deleted
    except Exception as e:
        # Avoid crashing indexing on local when OpenSearch is slow/unavailable.
        logger.warning(f"Delete by query failed (non-fatal): {e}")
        return 0


def search(
    index_name: str,
    query: Dict[str, Any],
    size: int = 20,
    from_: int = 0,
    sort: Optional[List[Dict[str, Any]]] = None,
    aggs: Optional[Dict[str, Any]] = None,
    source_fields: Optional[List[str]] = None,
    highlight: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a search query with optional aggregations, source filtering, and highlighting."""
    client = get_opensearch_client()
    
    body = {"query": query, "size": size, "from": from_}
    if sort:
        body["sort"] = sort
    if aggs:
        body["aggs"] = aggs
    if source_fields is not None:
        body["_source"] = source_fields
    if highlight is not None:
        body["highlight"] = highlight
    
    try:
        result = client.search(index=index_name, body=body)
        return result
    except Exception as e:
        logger.error(f"Search failed on {index_name}: {e}")
        return {"hits": {"hits": [], "total": {"value": 0}}, "aggregations": {}}


def knn_search(
    index_name: str,
    field: str,
    query_vector: List[float],
    k: int = 10,
    num_candidates: int = 100,
    filter_query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a kNN vector search."""
    client = get_opensearch_client()
    
    body = {
        "size": k,
        "query": {
            "knn": {
                field: {
                    "vector": query_vector,
                    "k": k,
                }
            }
        },
    }
    
    # Add filter if provided
    if filter_query:
        body["query"] = {
            "bool": {
                "must": [body["query"]],
                "filter": filter_query,
            }
        }
    
    try:
        result = client.search(index=index_name, body=body)
        return result
    except Exception as e:
        logger.error(f"kNN search failed on {index_name}: {e}")
        return {"hits": {"hits": [], "total": {"value": 0}}}


def multi_search(queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute multiple searches in a single request."""
    client = get_opensearch_client()
    
    try:
        result = client.msearch(body=queries)
        return result.get("responses", [])
    except Exception as e:
        logger.error(f"Multi-search failed: {e}")
        return []
