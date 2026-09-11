"""Фоновые задачи конвейера базы знаний Taskiq."""

import logging
from pathlib import Path

from src.core.broker import broker
from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.db.database import async_session_maker
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel
from src.kb.parser import DocumentParser
from src.kb.qdrant import EmbeddingStub, init_knowledge_base_collection
from src.kb.repository import KbRepository

logger = logging.getLogger(__name__)


@broker.task(task_name="index_kb_document", queue_name="ingestion_queue")
async def index_kb_document(
    doc_id: str,
    file_path: str,
    regime: str = "MOS_PORTAL",
) -> None:
    """Фоновая задача разбора, сохранения и векторной индексации документа регламента."""
    logger.info(
        "Запуск фоновой индексации документа %s из %s (regime=%s)",
        doc_id,
        file_path,
        regime,
    )

    path = Path(file_path)
    async with async_session_maker() as session:
        repo = KbRepository(session)

        # 1. Перевод статуса в 'indexing'
        await repo.update_document_status(doc_id=doc_id, status="indexing")
        await session.commit()

        try:
            # 2. Глубокий разбор документа и иерархический чанкинг
            parser = DocumentParser(mode="fast")
            parse_result = parser.parse_document(
                file_path=path,
                doc_id=doc_id,
                regime=regime,
            )

            doc_model = KbDocumentModel(
                doc_id=parse_result.document.doc_id,
                title=parse_result.document.title,
                regime=parse_result.document.regime,
                edition_date=parse_result.document.edition_date,
                status="indexing",
                error_message=parse_result.document.error_message,
                source_url=str(path),
            )

            node_models = [
                KbNodeModel(
                    node_id=n.node_id,
                    doc_id=doc_model.doc_id,
                    parent_node_id=n.parent_node_id,
                    level=n.level,
                    section_path=n.section_path,
                    article_no=n.article_no,
                    part_no=n.part_no,
                    title=n.title,
                    full_content=n.full_content,
                    table_md=n.table_md,
                    token_count=n.token_count,
                )
                for n in parse_result.nodes
            ]

            chunk_models = [
                KbChunkModel(
                    chunk_id=c.chunk_id,
                    node_id=c.node_id,
                    text=c.text,
                    context_prefix=c.context_prefix,
                    hyp_questions=c.hyp_questions,
                    embedding_model_version=c.embedding_model_version,
                )
                for c in parse_result.chunks
            ]

            # Сохранение полного дерева узлов и чанков в PostgreSQL
            await repo.save_full_document_tree(
                document=doc_model,
                nodes=node_models,
                chunks=chunk_models,
            )

            # 3. Пакетная векторизация и upsert в Qdrant (knowledge_base)
            try:
                qdrant_client = get_qdrant_client()
                if qdrant_client is not None:
                    await init_knowledge_base_collection(qdrant_client)
                    embedding_stub = EmbeddingStub(dim=1024)

                    points = [
                        embedding_stub.create_point(
                            chunk_id=c.chunk_id,
                            text=c.text,
                            payload={
                                "doc_id": doc_model.doc_id,
                                "node_id": c.node_id,
                                "regime": doc_model.regime,
                                "has_table": c.has_table,
                                "status": "ACTIVE",
                                "kb_type": "guide",
                                "kind": "chunk",
                            },
                        )
                        for c in parse_result.chunks
                    ]

                    # Пакетная загрузка порциями по 100 точек
                    batch_size = 100
                    for i in range(0, len(points), batch_size):
                        batch = points[i : i + batch_size]
                        await qdrant_client.upsert(
                            collection_name=settings.QDRANT_COLLECTION_NAME,
                            points=batch,
                        )
            except Exception as q_exc:
                logger.warning(
                    "Предупреждение при векторизации в Qdrant для %s: %s",
                    doc_id,
                    q_exc,
                )

            # 4. Успех: переводим в статус 'indexed'
            await repo.update_document_status(doc_id=doc_id, status="indexed")
            await session.commit()
            logger.info("Документ %s успешно проиндексирован.", doc_id)

        except Exception as exc:
            logger.exception(
                "Ошибка при индексации документа %s",
                doc_id,
            )
            await session.rollback()
            await repo.update_document_status(
                doc_id=doc_id,
                status="failed",
                error_message=str(exc),
            )
            await session.commit()
            raise


@broker.task(
    task_name="enrich_kb_chunks",
    queue_name="ingestion_queue",
)
async def enrich_kb_chunks(batch_size: int = 50) -> dict[str, int]:
    """MED-04: Фоновое обогащение чанков context_prefix и hyp_questions.

    Извлекает пакет необогащённых чанков, генерирует для каждого
    контекстный префикс и гипотетические вопросы (заглушка LLM),
    обновляет PostgreSQL и пересчитывает вектора в Qdrant.
    """
    logger.info(
        "Запуск фонового обогащения чанков (batch_size=%d)", batch_size
    )

    async with async_session_maker() as session:
        repo = KbRepository(session)

        try:
            qdrant_client = get_qdrant_client()
        except Exception:
            qdrant_client = None

        from src.kb.service import KbService

        service = KbService(
            repo=repo, session=session, qdrant_client=qdrant_client
        )
        enriched_count = await service.enrich_chunks_batch(
            batch_size=batch_size
        )
        logger.info("Фоновое обогащение завершено: %d чанков", enriched_count)
        return {"enriched": enriched_count}


@broker.task(
    task_name="generate_faq_draft",
    queue_name="ingestion_queue",
)
async def generate_faq_draft(
    ticket_id: str,
    question: str,
    answer: str,
    kind: str = "procedural",
) -> dict[str, str]:
    """MED-05: Генерация черновика FAQ из решённого тикета.

    Вызывается после закрытия тикета оператором (HIGH-10 хук).
    Создаёт запись в faq_moderation_queue со статусом PENDING.
    """
    logger.info("Создание черновика FAQ из тикета %s", ticket_id)

    async with async_session_maker() as session:
        repo = KbRepository(session)

        try:
            qdrant_client = get_qdrant_client()
        except Exception:
            qdrant_client = None

        from src.kb.service import KbService

        service = KbService(
            repo=repo, session=session, qdrant_client=qdrant_client
        )
        draft = await service.create_faq_draft(
            ticket_id=ticket_id,
            question=question,
            answer=answer,
            kind=kind,
        )
        logger.info(
            "Черновик FAQ %s создан для тикета %s", draft.id, ticket_id
        )
        return {"draft_id": draft.id, "status": draft.status}
