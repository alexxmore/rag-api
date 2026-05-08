import time
import uuid

from app.settings import get_settings
from app.vector_store import FaissVectorStore


def lookup_cache(store: FaissVectorStore, query_vector: list[float]) -> dict | None:
    settings = get_settings()
    results = store.search(query_vector, top_k=1)
    if results and results[0]["score"] >= settings.cache_similarity_threshold:
        return results[0]
    return None


def store_cache(
    store: FaissVectorStore,
    query_vector: list[float],
    query: str,
    response: str,
    model: str,
    sources: list[str],
) -> None:
    settings = get_settings()
    store.add(
        query_vector,
        {
            "id": str(uuid.uuid4()),
            "query": query,
            "response": response,
            "model": model,
            "sources": sources,
            "created_at": int(time.time()),
            "expire_at": int(time.time()) + settings.semantic_cache_ttl_seconds,
        },
    )
