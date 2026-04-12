from openai import OpenAI
from typing import List
from core import config

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client

class Embeddings:
    """
    OpenAI embeddings generator for semantic search.
    Uses text-embedding-ada-002 model (1536 dimensions).
    """

    def __call__(self, input: List[str]) -> List[List[float]]:
        """Generate embeddings for list of text inputs."""
        if not input:
            print(" Empty input to embedding function")
            return []

        try:
            response = _get_client().embeddings.create(
                input=input,
                model="text-embedding-ada-002"
            )
            return [e.embedding for e in response.data]
        except Exception as e:
            print(f" Embedding failed: {e}")
            return []