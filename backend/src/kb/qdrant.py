"""Интеграция с векторным хранилищем Qdrant и двухвекторный стаб (dense + sparse)."""

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.models import Distance, SparseVectorParams, VectorParams

from src.core.config import settings

# Детерминированный namespace для генерации UUIDv5 точек Qdrant
QDRANT_CHUNK_NAMESPACE = uuid.UUID("a2b3c4d5-e6f7-4a5b-8c9d-0e1f2a3b4c5d")


def chunk_id_to_qdrant_uuid(chunk_id: str) -> uuid.UUID:
    """Генерирует детерминированный UUIDv5 по строковому chunk_id для точки Qdrant."""
    return uuid.uuid5(QDRANT_CHUNK_NAMESPACE, chunk_id)


async def init_knowledge_base_collection(
    client: AsyncQdrantClient,
    collection_name: str | None = None,
) -> None:
    """Инициализирует двухвекторную коллекцию в Qdrant (dense 1024D + sparse BM25)."""
    target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
    collections = await client.get_collections()
    existing_names = [c.name for c in collections.collections]

    if target_collection not in existing_names:
        await client.create_collection(
            collection_name=target_collection,
            vectors_config={
                "dense": VectorParams(size=1024, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(),
            },
        )


class EmbeddingStub:
    """Тестовый генератор двухвекторных представлений (dense + sparse) для окружения без GPU."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def generate_vectors(self, text: str) -> dict[str, Any]:
        """Генерирует согласованную двухвекторную структуру под схему коллекции knowledge_base."""
        # Детерминированный вектор 1024D на основе длины текста и хэша
        seed = sum(ord(c) for c in text) if text else 1
        dense_vector = [
            ((seed * (i + 1)) % 1000) / 1000.0 for i in range(self.dim)
        ]
        # Нормализация
        norm = sum(v * v for v in dense_vector) ** 0.5 or 1.0
        normalized_dense = [v / norm for v in dense_vector]

        # Валидный sparse вектор с индексами и значениями весов BM25
        sparse_vector = models.SparseVector(
            indices=[(seed % 50) + 1, ((seed * 7) % 50) + 51],
            values=[0.65, 0.95],
        )

        return {
            "dense": normalized_dense,
            "sparse": sparse_vector,
        }

    def create_point(
        self,
        chunk_id: str,
        text: str,
        payload: dict[str, Any],
    ) -> models.PointStruct:
        """Формирует объект PointStruct с детерминированным UUIDv5 и двумя векторами."""
        vectors = self.generate_vectors(text)
        point_id = str(chunk_id_to_qdrant_uuid(chunk_id))
        enriched_payload = {**payload, "chunk_id": chunk_id, "text": text}

        return models.PointStruct(
            id=point_id,
            vector=vectors,
            payload=enriched_payload,
        )
