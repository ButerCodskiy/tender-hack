"""Двухканальный и иерархический поиск по базе знаний (ADR-0001: Small-to-Big Retrieval)."""

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from sqlalchemy import text

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.db.database import async_session_maker
from src.kb.qdrant import EmbeddingStub
from src.rag.schemas import RagSourceChunkSchema

logger = logging.getLogger(__name__)


class Retriever:
    """Поисковый ретривер с поддержкой Small-to-Big гидратации из PostgreSQL."""

    def __init__(
        self,
        embedding_model: EmbeddingStub | None = None,
        top_k: int = 10,
        qdrant_client: AsyncQdrantClient | None = None,
    ):
        self.embedding_model = embedding_model or EmbeddingStub(dim=1024)
        self.top_k = top_k
        self.qdrant_client = qdrant_client or get_qdrant_client()

    def _encode_query(self, query: str) -> list[float]:
        """Генерирует плотный вектор через BAAI/bge-m3 на CUDA (или CPU) с фолбэком на стаб."""
        try:
            import torch
            import torch.nn.functional as F
            from transformers import AutoModel, AutoTokenizer

            if getattr(self, "_bge_model", None) is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._bge_tokenizer = AutoTokenizer.from_pretrained(
                    "BAAI/bge-m3"
                )
                self._bge_model = AutoModel.from_pretrained("BAAI/bge-m3").to(
                    device
                )
                self._bge_model.eval()
                self._bge_device = device

            inputs = self._bge_tokenizer(
                [query],
                padding=True,
                truncation=True,
                max_length=8192,
                return_tensors="pt",
            ).to(self._bge_device)
            with torch.no_grad():
                outputs = self._bge_model(**inputs)
                norm_emb = F.normalize(
                    outputs.last_hidden_state[:, 0], p=2, dim=-1
                )
                return norm_emb[0].cpu().tolist()
        except Exception as exc:
            logger.debug(
                f"BAAI/bge-m3 недоступен, фолбэк на embedding_model: {exc}"
            )
            return self.embedding_model.generate_vectors(query)["dense"]

    async def retrieve(
        self,
        query: str,
    ) -> list[RagSourceChunkSchema]:
        """Поиск наиболее релевантных дочерних чанков в Qdrant и гидратация полных родительских узлов из PostgreSQL."""
        dense = self._encode_query(query)
        sparse = self.embedding_model.generate_vectors(query).get("sparse")

        collection = settings.QDRANT_COLLECTION_NAME
        response = None

        # 1. Поиск в Qdrant
        try:
            # Сначала пробуем прямой dense-поиск (коллекция tender_chunks по ADR-0001)
            response = await self.qdrant_client.query_points(
                collection_name=collection,
                query=dense,
                limit=self.top_k,
                with_payload=True,
            )
        except Exception as exc1:
            # Фолбэк на двухвекторный RRF-поиск (старая коллекция knowledge_base)
            if sparse is not None:
                try:
                    response = await self.qdrant_client.query_points(
                        collection_name=collection,
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
                except Exception as exc2:
                    logger.error(
                        f"Ошибка поиска Qdrant ({collection}): dense={exc1}, rrf={exc2}"
                    )
                    return []
            else:
                logger.error(f"Ошибка поиска Qdrant ({collection}): {exc1}")
                return []

        if not response or not response.points:
            return []

        # 2. Извлечение node_id для Small-to-Big гидратации (ADR-0001)
        node_ids: list[str] = []
        for point in response.points:
            if point.payload and point.payload.get("node_id"):
                nid = str(point.payload["node_id"])
                if nid not in node_ids:
                    node_ids.append(nid)

        # 3. Гидратация полных родительских узлов AST из PostgreSQL (kb_nodes)
        nodes_map: dict[str, Any] = {}
        if node_ids:
            try:
                async with async_session_maker() as session:
                    res = await session.execute(
                        text(
                            "SELECT id, content_markdown, section_path, title, doc_id "
                            "FROM kb_nodes WHERE id = ANY(:node_ids)"
                        ),
                        {"node_ids": node_ids},
                    )
                    for row in res:
                        nodes_map[str(row.id)] = row
            except Exception as exc_db:
                logger.warning(
                    f"Не удалось выполнить гидратацию из kb_nodes: {exc_db}"
                )

        # 4. Формирование обогащенных источников с полным родительским контекстом
        sources: list[RagSourceChunkSchema] = []
        seen_nodes: set[str] = set()

        for point in response.points:
            if not point.payload:
                continue

            node_id = str(point.payload.get("node_id", ""))
            if node_id and node_id in seen_nodes:
                # Дедупликация родительских секций
                continue
            if node_id:
                seen_nodes.add(node_id)

            parent_node = nodes_map.get(node_id)
            if parent_node:
                quote_text = parent_node.content_markdown
                section_path = parent_node.section_path
                title = parent_node.title or section_path
                doc_id = str(parent_node.doc_id)
            else:
                quote_text = point.payload.get("text")
                section_path = point.payload.get("section_path")
                title = (
                    point.payload.get("title")
                    or section_path
                    or "Нормативный регламент"
                )
                doc_id = str(
                    point.payload.get("document_id")
                    or point.payload.get("doc_id", "")
                )

            sources.append(
                RagSourceChunkSchema(
                    chunk_id=str(point.payload.get("chunk_id", point.id)),
                    doc_id=doc_id,
                    title=title,
                    quote_text=quote_text,
                    section_path=section_path,
                    source_url=point.payload.get("source_url"),
                    relevance_score=point.score,
                )
            )

        return sources
