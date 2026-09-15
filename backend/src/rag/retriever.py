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
        top_k: int = 30,
        qdrant_client: AsyncQdrantClient | None = None,
    ):
        self.embedding_model = embedding_model or EmbeddingStub(dim=1024)
        self.top_k = top_k
        self.qdrant_client = qdrant_client or get_qdrant_client()

    def _encode_query(self, query: str) -> list[float]:
        """Генерирует плотный вектор через BAAI/bge-m3 на AMD GPU (Ollama) с фолбэком на embedding_model."""
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/embeddings",
                data=json.dumps({"model": "bge-m3", "prompt": query}).encode(
                    "utf-8"
                ),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "embedding" in data and len(data["embedding"]) == 1024:
                    return data["embedding"]
        except Exception as ollama_exc:
            logger.debug("Ollama bge-m3 embeddings fallback: %s", ollama_exc)

        return self.embedding_model.generate_dense_vector(query)

    async def retrieve(
        self,
        query: str,
    ) -> list[RagSourceChunkSchema]:
        """Поиск наиболее релевантных дочерних чанков в Qdrant и гидратация полных родительских узлов из PostgreSQL."""
        dense = self._encode_query(query)
        sparse = self.embedding_model.generate_sparse_vector(query)

        collection = settings.QDRANT_COLLECTION_NAME
        response = None

        # 1. Поиск в Qdrant
        try:
            # Сначала пробуем прямой dense-поиск с указанием имени вектора "dense"
            response = await self.qdrant_client.query_points(
                collection_name=collection,
                query=dense,
                using="dense",
                limit=self.top_k,
                with_payload=True,
            )
        except Exception:
            try:
                # Попытка прямого поиска для безымянных векторов
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
                                    query=dense,
                                    limit=self.top_k,
                                    using="dense",
                                ),
                                models.Prefetch(
                                    query=sparse,
                                    limit=self.top_k,
                                    using="sparse",
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
                    logger.error(
                        f"Ошибка поиска Qdrant ({collection}): {exc1}"
                    )
                    return []

        if not response or not response.points:
            return []

        # 2. Оценка уверенности (score threshold) и эвристика спектрального разрыва
        query_words_count = len(query.strip().split())
        effective_threshold = max(
            0.32, 0.40 - max(0, 4 - query_words_count) * 0.02
        )

        raw_points = list(response.points)
        s1 = float(getattr(raw_points[0], "score", 0.0) or 0.0)
        s2 = (
            float(getattr(raw_points[1], "score", 0.0) or 0.0)
            if len(raw_points) > 1
            else 0.0
        )
        delta = s1 - s2

        filtered_points: list[Any] = []
        if s1 < effective_threshold:
            # Если top-1 ниже порога, проверяем спектральный разрыв (изолированный пик)
            if delta >= 0.08 and s1 >= 0.28:
                logger.info(
                    "Retriever: спектральный разрыв top-1 (score=%.4f, s2=%.4f, delta=%.4f, "
                    "threshold=%.4f) для запроса '%s'",
                    s1,
                    s2,
                    delta,
                    effective_threshold,
                    query,
                )
                filtered_points = [raw_points[0]]
            else:
                logger.info(
                    "Retriever: низкая уверенность (score=%.4f < %.4f, delta=%.4f < 0.08) "
                    "для запроса '%s'. Отказ от генерации.",
                    s1,
                    effective_threshold,
                    delta,
                    query,
                )
                return []
        else:
            filtered_points = [
                p
                for p in raw_points
                if float(getattr(p, "score", 0.0) or 0.0)
                >= effective_threshold
            ]

        if not filtered_points:
            return []

        # 3. Извлечение node_id для Small-to-Big гидратации (ADR-0001)
        node_ids: list[str] = []
        for point in filtered_points:
            if point.payload and point.payload.get("node_id"):
                nid = str(point.payload["node_id"])
                if nid not in node_ids:
                    node_ids.append(nid)

        # 4. Проверка метаданных родительских узлов AST из PostgreSQL (kb_nodes)
        nodes_map: dict[str, Any] = {}
        if node_ids:
            try:
                async with async_session_maker() as session:
                    res = await session.execute(
                        text(
                            "SELECT node_id, full_content, section_path, title, doc_id, table_md "
                            "FROM kb_nodes WHERE node_id = ANY(:node_ids)"
                        ),
                        {"node_ids": node_ids},
                    )
                    for row in res:
                        nodes_map[str(row.node_id)] = row
            except Exception as exc_db:
                logger.debug(
                    "Retriever: выборка из kb_nodes пропущена (фолбэк на payload Qdrant): %s",
                    exc_db,
                )

        # 5. Формирование обогащенных источников
        sources: list[RagSourceChunkSchema] = []

        for point in filtered_points:
            if not point.payload:
                continue

            node_id = str(point.payload.get("node_id", ""))
            parent_node = nodes_map.get(node_id) if node_id else None
            quote_text = point.payload.get("text") or ""
            if len(quote_text) > 6000:
                quote_text = (
                    quote_text[:6000]
                    + "\n\n[... Текст фрагмента сокращен для оптимизации контекста ...]"
                )
            section_path = point.payload.get("section_path") or (
                parent_node.section_path if parent_node else None
            )
            title = (
                point.payload.get("title")
                or (parent_node.title if parent_node else None)
                or section_path
                or "Нормативный регламент"
            )
            doc_id = str(
                point.payload.get("document_id")
                or point.payload.get("doc_id", "")
                or (parent_node.doc_id if parent_node else "")
            )

            parent_full_content = (
                parent_node.full_content if parent_node else None
            )
            parent_title = parent_node.title if parent_node else None

            sources.append(
                RagSourceChunkSchema(
                    chunk_id=str(point.payload.get("chunk_id", point.id)),
                    node_id=node_id or None,
                    doc_id=doc_id,
                    title=title,
                    quote_text=quote_text,
                    section_path=section_path,
                    source_url=point.payload.get("source_url"),
                    relevance_score=point.score,
                    parent_title=parent_title,
                    parent_full_content=parent_full_content,
                    highlight_quote=quote_text,
                )
            )

        return sources


async def hydrate_parent_articles(
    sources: list[RagSourceChunkSchema],
    session: Any = None,
    max_parent_chars: int = 5000,
) -> list[RagSourceChunkSchema]:
    """Выполняет гидратацию родительских статей (Small-to-Big) из PostgreSQL (kb_nodes).

    Для источников с is_parent=True и заполненным node_id:
    - Извлекает full_content, title, section_path, table_md из kb_nodes.
    - Сохраняет parent_full_content и parent_title для интерактивного просмотра на Frontend.
    - Рассчитывает символьные смещения highlight_offset (start, end) для подсветки цитаты в шторке.
    - Устанавливает quote_text равным родительскому контенту (с адаптивным окном при превышении лимита)
      для передачи в генератор ответов LLM.
    """
    if not sources:
        return []

    parent_node_ids = [
        s.node_id
        for s in sources
        if getattr(s, "is_parent", False) and s.node_id
    ]
    if not parent_node_ids:
        return sources

    nodes_map: dict[str, Any] = {}
    try:
        if session is not None:
            res = await session.execute(
                text(
                    "SELECT node_id, full_content, section_path, title, doc_id, table_md "
                    "FROM kb_nodes WHERE node_id = ANY(:node_ids)"
                ),
                {"node_ids": parent_node_ids},
            )
            for row in res:
                nodes_map[str(row.node_id)] = row
        else:
            async with async_session_maker() as sess:
                res = await sess.execute(
                    text(
                        "SELECT node_id, full_content, section_path, title, doc_id, table_md "
                        "FROM kb_nodes WHERE node_id = ANY(:node_ids)"
                    ),
                    {"node_ids": parent_node_ids},
                )
                for row in res:
                    nodes_map[str(row.node_id)] = row
    except Exception as exc:
        logger.debug("hydrate_parent_articles fallback: %s", exc)

    hydrated_sources: list[RagSourceChunkSchema] = []
    for source in sources:
        if (
            getattr(source, "is_parent", False)
            and source.node_id
            and source.node_id in nodes_map
        ):
            row = nodes_map[source.node_id]
            full_content = row.full_content or ""
            quote = source.highlight_quote or source.quote_text or ""

            # Вычисляем смещение цитаты в родительском документе
            highlight_offset = None
            if quote and quote in full_content:
                start_idx = full_content.find(quote)
                highlight_offset = {
                    "start": start_idx,
                    "end": start_idx + len(quote),
                }
            elif quote:
                # Поиск первого ключевого предложения
                first_sentence = quote.split(".")[0].strip()
                if len(first_sentence) > 15 and first_sentence in full_content:
                    start_idx = full_content.find(first_sentence)
                    highlight_offset = {
                        "start": start_idx,
                        "end": start_idx + len(first_sentence),
                    }

            # Адаптивное окно контекста для промпта LLM
            context_text = full_content
            if len(context_text) > max_parent_chars:
                if highlight_offset:
                    mid = highlight_offset["start"]
                    half = max_parent_chars // 2
                    w_start = max(0, mid - half)
                    w_end = min(len(full_content), mid + half)
                    prefix = (
                        "[... Текст статьи сокращен ...]\n\n"
                        if w_start > 0
                        else ""
                    )
                    suffix = (
                        "\n\n[... Текст статьи сокращен ...]"
                        if w_end < len(full_content)
                        else ""
                    )
                    context_text = (
                        prefix + full_content[w_start:w_end] + suffix
                    )
                else:
                    context_text = (
                        full_content[:max_parent_chars]
                        + "\n\n[... Текст родительской статьи сокращен для оптимизации контекста ...]"
                    )

            hydrated_chunk = source.model_copy(
                update={
                    "parent_title": row.title or source.title,
                    "parent_full_content": full_content,
                    "quote_text": context_text,
                    "section_path": row.section_path or source.section_path,
                    "title": row.title or source.title,
                    "highlight_quote": quote,
                    "highlight_offset": highlight_offset,
                }
            )
            hydrated_sources.append(hydrated_chunk)
        else:
            hydrated_sources.append(
                source.model_copy(
                    update={
                        "highlight_quote": source.highlight_quote
                        or source.quote_text,
                    }
                )
            )

    return hydrated_sources
