import json
import os
import time
from pathlib import Path
from typing import Any

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.settings import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = SentenceTransformer(settings.embedding_model)

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode([text], normalize_embeddings=True)[0]
        return vector.astype("float32").tolist()

    def embed_many(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return vectors.astype("float32")


class FaissVectorStore:
    def __init__(self, root: Path, name: str, dimensions: int = 384) -> None:
        self.root = root
        self.name = name
        self.dimensions = dimensions
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / f"{name}.faiss"
        self.payload_path = self.root / f"{name}.json"
        self.index = faiss.IndexFlatIP(dimensions)
        self.payloads: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.index_path.exists() and self.payload_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            self.payloads = json.loads(self.payload_path.read_text(encoding="utf-8"))

    def save(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self.payload_path.write_text(json.dumps(self.payloads, ensure_ascii=False, indent=2), encoding="utf-8")

    def rebuild(self, vectors: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)
        self.payloads = payloads
        self.save()

    def add(self, vector: list[float], payload: dict[str, Any]) -> None:
        arr = np.array([vector], dtype="float32")
        self.index.add(arr)
        self.payloads.append(payload)
        self.save()

    def search(self, vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if self.index.ntotal == 0:
            return []
        arr = np.array([vector], dtype="float32")
        scores, indices = self.index.search(arr, min(top_k, self.index.ntotal))
        results = []
        now = int(time.time())
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx < 0:
                continue
            payload = self.payloads[int(idx)]
            expire_at = payload.get("expire_at")
            if expire_at and expire_at < now:
                continue
            results.append({"score": float(score), **payload})
        return results


class QdrantVectorStore:
    def __init__(self, collection_name: str, dimensions: int = 384) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        settings = get_settings()
        if not settings.qdrant_url:
            raise RuntimeError("QDRANT_URL is required when VECTOR_BACKEND=qdrant")
        self.collection_name = collection_name
        self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        existing = [item.name for item in self.client.get_collections().collections]
        if collection_name not in existing:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )

    def rebuild(self, vectors: np.ndarray, payloads: list[dict[str, Any]]) -> None:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE),
        )
        points = [
            PointStruct(id=idx, vector=vector.tolist(), payload=payload)
            for idx, (vector, payload) in enumerate(zip(vectors, payloads, strict=False))
        ]
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def add(self, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct

        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=payload["id"], vector=vector, payload=payload)],
        )

    def search(self, vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        results = self.client.search(collection_name=self.collection_name, query_vector=vector, limit=top_k * 3)
        now = int(time.time())
        cleaned = []
        for item in results:
            payload = item.payload or {}
            expire_at = payload.get("expire_at")
            if expire_at and expire_at < now:
                continue
            cleaned.append({"score": float(item.score), **payload})
            if len(cleaned) >= top_k:
                break
        return cleaned


VectorStore = FaissVectorStore | QdrantVectorStore


def get_chunk_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_backend == "qdrant":
        return QdrantVectorStore(settings.qdrant_chunks_collection)
    return FaissVectorStore(settings.vector_index_path, "chunks")


def get_cache_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_backend == "qdrant":
        return QdrantVectorStore(settings.qdrant_cache_collection)
    return FaissVectorStore(settings.vector_index_path, "semantic_cache")
