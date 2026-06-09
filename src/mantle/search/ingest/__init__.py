# search/ingest/__init__.py
from search.ingest.pipeline_unified import (
    index_artifact,
    index_artifacts_batch,
    delete_artifact_from_index,
    enqueue_index_artifact,
    enqueue_index_artifacts_batch,
)

# Import the module (not from itself - import the actual module file)
import search.ingest.index_queue as index_queue

__all__ = [
    "index_artifact",
    "index_artifacts_batch",
    "delete_artifact_from_index",
    "enqueue_index_artifact",
    "enqueue_index_artifacts_batch",
    "index_queue",
]
