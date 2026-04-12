# search/ingest/acl.py
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def extract_tenant_id(owner_id: str) -> str:
    """
    Extract tenant_id from owner_id.
    
    For Agience's single-tenant-per-user model, tenant_id = owner_id.
    This allows future multi-tenant support without schema changes.
    """
    return owner_id


def compute_acl_principals_workspace(
    owner_id: str,
    workspace_id: str,
    collection_ids: List[str],
) -> List[str]:
    """
    Compute ACL principals for a workspace artifact.
    
    Workspace artifacts are scoped to:
    - The workspace owner (always)
    - The workspace itself (for workspace-scoped queries)
    
    Collection IDs are stored but not used for ACL (workspace artifacts
    are ephemeral and not shared via collections).
    """
    principals = set()
    
    # Owner always has access
    if owner_id:
        principals.add(owner_id)
    
    # Workspace ID for workspace-scoped queries
    if workspace_id:
        principals.add(f"workspace:{workspace_id}")
    
    return sorted(principals)


def compute_acl_principals_collection(
    owner_id: str,
    collection_id: str,
    grant_keys: Optional[List[str]] = None,
) -> List[str]:
    """
    Compute ACL principals for a collection artifact.
    
    Collection artifacts are accessible to:
    - The collection owner (always)
    - The collection itself (for collection-scoped queries)
    - Share key holders (if shares exist)
    
    Note: Share key access is resolved at query time by fetching
    active shares. Here we just add the collection ID as a principal.
    """
    principals = set()
    
    # Owner always has access
    if owner_id:
        principals.add(owner_id)
    
    # Collection ID for collection-scoped queries
    if collection_id:
        principals.add(f"collection:{collection_id}")
    
    # Share keys (if provided)
    if grant_keys:
        for key in grant_keys:
            if key:
                principals.add(f"share:{key}")
    
    return sorted(principals)


def build_acl_filter(
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    grant_keys: Optional[List[str]] = None,
) -> dict:
    """
    Build OpenSearch filter for ACL principals with MANDATORY tenant isolation.
    
    SECURITY: All queries MUST include tenant_id filter to prevent cross-tenant leaks.
    
    The filter matches documents where:
    1. tenant_id = user's tenant (MANDATORY)
    2. acl_principals contains ANY of:
       - user_id (for owned content)
       - workspace:<workspace_id> (for workspace-scoped search)
       - collection:<collection_id> (for collection-scoped search)
       - share:<key> (for share-based access)
    """
    principals = set()
    tenant_id = None
    
    if user_id:
        principals.add(user_id)
        tenant_id = extract_tenant_id(user_id)
    
    if workspace_id:
        principals.add(f"workspace:{workspace_id}")
    
    if collection_id:
        principals.add(f"collection:{collection_id}")
    
    if grant_keys:
        for key in grant_keys:
            if key:
                principals.add(f"share:{key}")
    
    if not principals or not tenant_id:
        # No access or no tenant - return filter that matches nothing
        logger.warning("build_acl_filter called without principals or tenant_id")
        return {"match_none": {}}
    
    # MANDATORY: tenant_id filter + acl_principals filter
    # This ensures strict tenant isolation at the search layer
    return {
        "bool": {
            "must": [
                {"term": {"tenant_id": tenant_id}},
                {"terms": {"acl_principals": list(principals)}}
            ]
        }
    }
