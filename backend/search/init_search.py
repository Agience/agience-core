# search/init_search.py
import json
import logging
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from db.opensearch import (
    get_opensearch_client,
    close_opensearch_client,
    clear_readonly_blocks,
)
from opensearchpy.exceptions import AuthorizationException

logger = logging.getLogger(__name__)

# Mapping files directory
MAPPINGS_DIR = Path(__file__).parent / "mappings"

def _is_canonical_artifacts_mapping(client, index_name: str) -> bool:
    """Return True when the existing index has the canonical artifacts mapping shape."""
    try:
        mapping = client.indices.get_mapping(index=index_name)
        props = (
            mapping.get(index_name, {})
            .get("mappings", {})
            .get("properties", {})
        )
        if props.get("root_id", {}).get("type") != "keyword":
            return False
        if props.get("version_id", {}).get("type") != "keyword":
            return False
        if props.get("collection_id", {}).get("type") != "keyword":
            return False
        if props.get("content_vector", {}).get("type") != "knn_vector":
            return False
        return True
    except Exception:
        return False


def ensure_search_indices_exist() -> bool:
    """Ensure all search indices exist with correct mappings.

    Creates indices from mapping files if they don't already exist.
    Safe to call multiple times — no-op when indices are present.

    Returns True if any index was newly created.
    """
    client = get_opensearch_client()

    indices = [
        ("artifacts", MAPPINGS_DIR / "artifacts.json"),
    ]

    any_created = False
    for index_name, mapping_path in indices:
        if not mapping_path.exists():
            logger.warning(f"Mapping file not found: {mapping_path}")
            continue
        if client.indices.exists(index=index_name):
            if _is_canonical_artifacts_mapping(client, index_name):
                logger.info(f"Index already exists: {index_name}")
                continue
            raise RuntimeError(
                f"Index '{index_name}' exists but does not match canonical artifacts mapping. "
                "Refusing auto-migration; clean the index explicitly and re-run initialization."
            )

        logger.info(f"Creating index {index_name}...")
        with open(mapping_path) as f:
            mapping_config = json.load(f)
        client.indices.create(
            index=index_name,
            body={
                "settings": mapping_config.get("settings", {}),
                "mappings": mapping_config.get("mappings", {}),
            },
        )
        logger.info(f"Created index: {index_name}")
        any_created = True

    return any_created


def init_search_indices():
    """
    Initialize search indices on startup.
    
    Creates indices if they don't exist. If ANY index is newly created,
    triggers a full reindex of all collection artifacts IN A BACKGROUND THREAD
    so startup doesn't block.
    
    Safe to call on every startup.
    """
    logger.info("Initializing search indices...")
    
    try:
        # Clear any read-only-allow-delete blocks left from a previous disk-full event.
        # These blocks persist after disk space is recovered; we remove them on every
        # startup so the cluster self-heals automatically.
        clear_readonly_blocks()
        
        # Cluster health is informational only; least-privilege OpenSearch users may not
        # have `cluster:monitor/health`. Avoid failing startup for that.
        try:
            client = get_opensearch_client()
            health = client.cluster.health()
            logger.info(f"OpenSearch cluster status: {health.get('status', 'unknown')}")
        except AuthorizationException as e:
            logger.info(f"OpenSearch cluster health not permitted for configured user (continuing): {e}")
        
        any_index_created = ensure_search_indices_exist()
        
        logger.info("Search indices initialization complete")
        
        # If any index was newly created, kick off background reindex from DB -> unified indices.
        # This is a ONE-TIME initial population when indices don't exist.
        # After this, indexing happens on create/update/commit events (not batch reindex).
        if any_index_created:
            logger.info("New indices detected. Starting ONE-TIME initial reindex from DB ...")
            threading.Thread(target=_reindex_all_artifacts, daemon=True).start()
        
    except Exception as e:
        logger.error(f"Failed to initialize search indices: {e}", exc_info=True)
        raise


def _reindex_all_artifacts():
    """Reindex every artifact in every collection (including workspaces) into OpenSearch.

    Collections and workspaces are both collections. Artifacts are artifacts.
    One function, one path.
    """
    try:
        from core.dependencies import get_arango_db
        from db.arango import query_documents, list_collection_artifacts, COLLECTION_ARTIFACTS
        from entities.collection import Collection as CollectionEntity
        from entities.artifact import Artifact as ArtifactEntity, COLLECTION_CONTENT_TYPE, WORKSPACE_CONTENT_TYPE
        from search.ingest.pipeline_unified import index_artifact

        logger.info("Starting full reindex of all artifacts...")

        db_gen = get_arango_db()
        db = next(db_gen)

        try:
            # Containers (workspaces and collections) now live in artifacts table.
            collections = [
                c for c in query_documents(db, CollectionEntity, COLLECTION_ARTIFACTS, {})
                if c.content_type in (COLLECTION_CONTENT_TYPE, WORKSPACE_CONTENT_TYPE)
            ]
            logger.info(f"Found {len(collections)} collections to reindex")

            # Build list of (collection_id, artifact) for every non-archived artifact
            artifacts_to_index: List[Tuple[str, ArtifactEntity]] = []
            for collection in collections:
                artifacts_list = list_collection_artifacts(db, collection.id)
                if not artifacts_list:
                    continue
                for art_dict in artifacts_list:
                    artifact = ArtifactEntity.from_dict(art_dict) if isinstance(art_dict, dict) else art_dict
                    if artifact.state != ArtifactEntity.STATE_ARCHIVED:
                        artifacts_to_index.append((collection.id, artifact))

            logger.info(f"Reindexing {len(artifacts_to_index)} artifacts...")

            max_workers = min(4, len(artifacts_to_index)) or 1
            total_indexed = 0
            total_failed = 0

            def index_safe(collection_id: str, artifact: ArtifactEntity) -> Tuple[bool, str]:
                try:
                    success = index_artifact(artifact, collection_id, is_head=True)
                    return (success, artifact.id)
                except Exception as e:
                    logger.warning(f"Failed to reindex artifact {artifact.id}: {e}")
                    return (False, artifact.id)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(index_safe, coll_id, artifact)
                    for coll_id, artifact in artifacts_to_index
                ]

                for i, future in enumerate(futures, 1):
                    try:
                        success, artifact_id = future.result()
                        if success:
                            total_indexed += 1
                        else:
                            total_failed += 1
                        if i % 10 == 0:
                            logger.info(
                                f"  Progress: {i}/{len(futures)} processed "
                                f"({total_indexed} indexed, {total_failed} failed)"
                            )
                    except Exception as e:
                        total_failed += 1
                        logger.warning(f"Unexpected error during reindex: {e}")

            logger.info(f"Reindex complete: {total_indexed} indexed, {total_failed} failed")

        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

    except Exception as e:
        logger.error(f"Failed reindex: {e}", exc_info=True)


def check_search_health() -> dict:
    """Check search service health."""
    try:
        client = get_opensearch_client()
        try:
            health = client.cluster.health()
            return {
                "opensearch_status": health.get("status", "unknown"),
                "opensearch_nodes": health.get("number_of_nodes", 0),
            }
        except AuthorizationException:
            # Fall back to an index-level probe that doesn't require cluster monitor perms.
            can_reach = client.indices.exists(index="artifacts")
            return {
                "opensearch_status": "reachable" if can_reach or can_reach is False else "unknown",
                "opensearch_nodes": 0,
            }
    except Exception as e:
        logger.error(f"OpenSearch health check failed: {e}")
        return {
            "opensearch_status": "error",
            "opensearch_error": str(e),
        }


def shutdown_search():
    """Close search connections on shutdown."""
    logger.info("Closing OpenSearch connections...")
    close_opensearch_client()
