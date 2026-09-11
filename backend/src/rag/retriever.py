"""Двухканальный гибридный поиск по базе знаний (векторный и лексический)."""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.kb.qdrant import EmbeddingStub
from src.rag.schemas import RagSourceChunkSchema

logger = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        embedding_model: EmbeddingStub,
        top_k: int = 10,
        qdrant_client: AsyncQdrantClient | None = None,
    ):
        self.embedding_model = embedding_model
        self.top_k = top_k
        self.qdrant_client = qdrant_client or get_qdrant_client()

    async def retrieve(
        self,
        query: str,
    ) -> list[RagSourceChunkSchema]:
        vectors = self.embedding_model.generate_vectors(query)
        dense = vectors["dense"]
        sparse = vectors["sparse"]
        try:
            response = await self.qdrant_client.query_points(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                prefetch=[
                    models.Prefetch(
                        query=dense, limit=self.top_k, using="dense"
                    ),
                    models.Prefetch(
                        query=sparse, limit=self.top_k, using="sparse"
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                with_payload=True,
            )
        except Exception as e:
            logger.error(f"При пооиске Qdrant произошла ошибка: {e}")
            return []

        return [
            RagSourceChunkSchema(
                chunk_id=str(point.payload.get("chunk_id", point.id)),
                doc_id=point.payload.get("doc_id", ""),
                title=point.payload.get("title"),
                quote_text=point.payload.get("text"),
                relevance_score=point.score,
            )
            for point in response.points
            if point.payload
        ]
