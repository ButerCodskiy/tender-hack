"""Сервисный слой управления базой знаний (KbService)."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import uuid6
from fastapi import UploadFile
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.kb.exceptions import (
    DocumentNotFoundError,
    FaqDraftAlreadyReviewedError,
    FaqDraftNotFoundError,
    NodeNotFoundError,
)
from src.kb.faq_loader import FaqLoader
from src.kb.models import (
    FaqModerationQueueModel,
    KbChunkModel,
    KbDocumentModel,
    KbNodeModel,
)
from src.kb.parser import DocumentParser
from src.kb.qdrant import (
    EmbeddingStub,
    chunk_id_to_qdrant_uuid,
    init_knowledge_base_collection,
)
from src.kb.repository import KbRepository
from src.kb.schemas import (
    DocumentUploadItemResponseSchema,
    FaqDraftListResponse,
    FaqDraftResponse,
    FaqImportResultSchema,
    FaqReviewResponse,
    KbDocumentDeleteResponse,
    KbDocumentListResponse,
    KbDocumentResponse,
    KbDocumentStatusResponse,
    KbNodeResponse,
    KbNodeUpdateRequest,
    ParsedExtractionResultSchema,
)

logger = logging.getLogger(__name__)


class KbService:
    """Сервис приема, парсинга и индексации документов базы знаний."""

    def __init__(
        self,
        repo: KbRepository,
        session: AsyncSession,
        qdrant_client: AsyncQdrantClient | None = None,
    ) -> None:
        self.repo = repo
        self.session = session
        if qdrant_client is not None:
            self.qdrant_client = qdrant_client
        else:
            try:
                self.qdrant_client = get_qdrant_client()
            except Exception as exc:
                logger.warning(
                    "Не удалось инициализировать Qdrant клиент: %s", exc
                )
                self.qdrant_client = None
        self.embedding_stub = EmbeddingStub(dim=1024)

    async def register_uploaded_files(
        self,
        files: list[UploadFile],
        regime: str = "MOS_PORTAL",
    ) -> list[DocumentUploadItemResponseSchema]:
        """Принимает пакет файлов, сохраняет их на диск и регистрирует в очереди.

        Сохраняет файлы в каталог settings.KB_STORAGE_DIR, создает записи в
        таблице kb_documents со статусом 'uploaded' и отправляет задачу
        в очередь Taskiq. При отсутствии подключения к брокеру продолжает работу.
        """
        storage_dir = settings.KB_STORAGE_DIR
        storage_dir.mkdir(parents=True, exist_ok=True)

        responses: list[DocumentUploadItemResponseSchema] = []

        for file in files:
            filename = Path(file.filename or "document.pdf").name
            doc_id = f"kb_doc_{uuid6.uuid7()}"
            saved_filename = f"{doc_id}_{filename}"
            target_path = storage_dir / saved_filename

            # Сохранение бинарного файла на диск
            content = await file.read()
            await asyncio.to_thread(target_path.write_bytes, content)

            # Регистрация документа в PostgreSQL
            doc_model = KbDocumentModel(
                doc_id=doc_id,
                title=filename,
                regime=regime,
                status="uploaded",
                source_url=str(target_path),
            )
            await self.repo.create_document(doc_model)

            # Постановка задачи в фоновую очередь Taskiq (с безопасным fallback)
            try:
                from src.kb.tasks import index_kb_document

                await index_kb_document.kiq(
                    doc_id=doc_id, file_path=str(target_path), regime=regime
                )
            except Exception as exc:
                logger.warning(
                    "Брокер Taskiq недоступен, задача index_kb_document для %s отложена: %s",
                    doc_id,
                    exc,
                )

            responses.append(
                DocumentUploadItemResponseSchema(
                    doc_id=doc_id,
                    title=filename,
                    status="uploaded",
                    message="Документ принят в очередь на разбор и индексацию",
                )
            )

        await self.session.commit()
        return responses

    async def ingest_document(
        self,
        doc_id: str,
        file_path: Path,
        regime: str = "MOS_PORTAL",
    ) -> ParsedExtractionResultSchema:
        """Синхронный конвейер разбора и сохранения документа для тестов и сидинга."""
        parser = DocumentParser(mode="fast")

        # 1. Парсинг через Docling / PyMuPDF
        parse_result = parser.parse_document(
            file_path=file_path, doc_id=doc_id, regime=regime
        )

        # 2. Формирование ORM моделей
        doc_model = KbDocumentModel(
            doc_id=parse_result.document.doc_id,
            title=parse_result.document.title,
            regime=parse_result.document.regime,
            edition_date=parse_result.document.edition_date,
            status="indexed",
            error_message=None,
            source_url=str(file_path),
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

        # 3. Чанки уже нарезаны парсером с сохранением табличных фактов
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

        # 4. Топологическое сохранение в PostgreSQL
        await self.repo.save_full_document_tree(
            document=doc_model,
            nodes=node_models,
            chunks=chunk_models,
        )

        # 5. Инициализация и upsert точек в Qdrant
        if self.qdrant_client is not None:
            try:
                await init_knowledge_base_collection(self.qdrant_client)
                points = [
                    self.embedding_stub.create_point(
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
                if points:
                    await self.qdrant_client.upsert(
                        collection_name=settings.QDRANT_COLLECTION_NAME,
                        points=points,
                    )
            except Exception as exc:
                logger.warning(
                    "Ошибка при сохранении векторов в Qdrant: %s", exc
                )

        return parse_result

    async def import_faq_table(
        self,
        file_content: bytes,
        filename: str,
        regime: str = "MOS_PORTAL",
        collection_name: str | None = None,
    ) -> FaqImportResultSchema:
        """Выполняет прямой импорт структурированной таблицы FAQ (XLSX, CSV)."""
        loader = FaqLoader(
            session=self.session,
            repo=self.repo,
            qdrant_client=self.qdrant_client,
            embedding_generator=self.embedding_stub,
        )
        return await loader.load_faq_table(
            file_content=file_content,
            filename=filename,
            regime=regime,
            collection_name=collection_name,
        )

    async def list_documents(
        self,
        regime: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> KbDocumentListResponse:
        """Возвращает реестр документов с фильтрацией и метаданными пагинации."""
        models_list, total = await self.repo.list_documents(
            skip=offset, limit=limit, regime=regime, status=status
        )
        items = [KbDocumentResponse.model_validate(m) for m in models_list]
        return KbDocumentListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_document_status(
        self, doc_id: str
    ) -> KbDocumentStatusResponse:
        """Возвращает статус индексации документа и количество связанных чанков."""
        info = await self.repo.get_document_status_info(doc_id)
        if info is None:
            raise DocumentNotFoundError(doc_id)

        doc, chunks_count = info
        return KbDocumentStatusResponse(
            doc_id=doc.doc_id,
            status=doc.status,
            error_message=doc.error_message,
            chunks_count=chunks_count,
            updated_at=doc.updated_at,
        )

    async def delete_document(self, doc_id: str) -> KbDocumentDeleteResponse:
        """Атомарно удаляет документ из PostgreSQL и гарантированно зачищает векторы в Qdrant.

        Порядок выполнения (двухфазная очистка):
        1. Проверка существования документа в БД (DocumentNotFoundError при отсутствии).
        2. Удаление точек из коллекции Qdrant по фильтру doc_id. При сбое Qdrant
           транзакция PostgreSQL откатывается, и документ не удаляется.
        3. Каскадное удаление записи из kb_documents и коммит транзакции.
        """
        doc = await self.repo.get_document_by_id(doc_id)
        if doc is None:
            raise DocumentNotFoundError(doc_id)

        try:
            if self.qdrant_client is not None:
                await self.qdrant_client.delete(
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    points_selector=qdrant_models.FilterSelector(
                        filter=qdrant_models.Filter(
                            must=[
                                qdrant_models.FieldCondition(
                                    key="doc_id",
                                    match=qdrant_models.MatchValue(
                                        value=doc_id
                                    ),
                                )
                            ]
                        )
                    ),
                )

            await self.repo.delete_document(doc_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return KbDocumentDeleteResponse(deleted=True, doc_id=doc_id)

    async def update_node(
        self, node_id: str, data: KbNodeUpdateRequest
    ) -> KbNodeResponse:
        """Точечно обновляет заголовок и путь узла в БД и синхронизирует payload в Qdrant."""
        node = await self.repo.get_node_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(node_id)

        try:
            updated_node = await self.repo.update_node(
                node_id=node_id,
                title=data.title,
                section_path=data.section_path,
            )

            # Синхронное обновление метаданных в payload точек Qdrant
            if self.qdrant_client is not None and (
                data.title is not None or data.section_path is not None
            ):
                payload_to_update: dict[str, Any] = {}
                if data.title is not None:
                    payload_to_update["title"] = data.title
                if data.section_path is not None:
                    payload_to_update["section_path"] = data.section_path

                if payload_to_update:
                    await self.qdrant_client.set_payload(
                        collection_name=settings.QDRANT_COLLECTION_NAME,
                        payload=payload_to_update,
                        points=qdrant_models.Filter(
                            must=[
                                qdrant_models.FieldCondition(
                                    key="node_id",
                                    match=qdrant_models.MatchValue(
                                        value=node_id
                                    ),
                                )
                            ]
                        ),
                    )

            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return KbNodeResponse.model_validate(updated_node)

    # ── MED-04: Асинхронное фоновое обогащение чанков ────────────

    async def enrich_chunk(
        self,
        chunk_id: str,
        context_prefix: str,
        hyp_questions: list[str],
    ) -> KbChunkModel | None:
        """Обогащает конкретный чанк: сохраняет context_prefix и hyp_questions в БД и Qdrant."""
        chunk = await self.repo.update_chunk_enrichment(
            chunk_id=chunk_id,
            context_prefix=context_prefix,
            hyp_questions=hyp_questions,
        )
        if chunk is None:
            logger.warning("Чанк %s не найден для обогащения", chunk_id)
            return None

        # Обновляем payload и пересчитываем вектор в Qdrant
        if self.qdrant_client is not None:
            try:
                enriched_text = f"{context_prefix}\n{chunk.text}"
                qdrant_point_id = str(chunk_id_to_qdrant_uuid(chunk_id))

                # Обновляем payload (context_prefix, hyp_questions)
                await self.qdrant_client.set_payload(
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    payload={
                        "context_prefix": context_prefix,
                        "hyp_questions": hyp_questions,
                    },
                    points=[qdrant_point_id],
                )

                # Пересчитываем вектор с учётом контекстного префикса
                vectors = self.embedding_stub.generate_vectors(enriched_text)
                await self.qdrant_client.update_vectors(
                    collection_name=settings.QDRANT_COLLECTION_NAME,
                    points=[
                        qdrant_models.PointVectors(
                            id=qdrant_point_id,
                            vector=vectors,
                        )
                    ],
                )
            except Exception as exc:
                logger.warning(
                    "Ошибка при обновлении Qdrant для чанка %s: %s",
                    chunk_id,
                    exc,
                )

        return chunk

    async def enrich_chunks_batch(self, batch_size: int = 50) -> int:
        """Пакетное обогащение чанков без context_prefix.

        Возвращает количество обогащённых чанков.
        На этапе заглушки генерирует детерминированные context_prefix и hyp_questions.
        При подключении реального LLM-клиента — заменить тело цикла.
        """
        chunks = await self.repo.list_unenriched_chunks(batch_size=batch_size)
        if not chunks:
            logger.info("Нет чанков для обогащения")
            return 0

        enriched_count = 0
        for chunk in chunks:
            # Заглушка LLM: генерация контекстного префикса и гипотетических вопросов
            context_prefix = (
                f"Этот фрагмент описывает нормативное положение из базы знаний. "
                f"Контекст: {chunk.text[:100]}..."
            )
            hyp_questions = [
                f"Что говорится в регламенте о: {chunk.text[:50]}?",
                "Какой порядок действий описан в данном фрагменте?",
            ]

            result = await self.enrich_chunk(
                chunk_id=chunk.chunk_id,
                context_prefix=context_prefix,
                hyp_questions=hyp_questions,
            )
            if result is not None:
                enriched_count += 1

        await self.session.commit()
        logger.info("Обогащено %d чанков из %d", enriched_count, len(chunks))
        return enriched_count

    # ── MED-05: Контур самообучения (FAQ-черновики) ───────────────

    async def create_faq_draft(
        self,
        ticket_id: str,
        question: str,
        answer: str,
        kind: str = "procedural",
    ) -> FaqDraftResponse:
        """Создаёт черновик FAQ из решённого тикета и помещает в очередь модерации."""
        draft_id = f"faq_{uuid6.uuid7()}"
        draft = FaqModerationQueueModel(
            id=draft_id,
            ticket_id=ticket_id,
            question=question,
            answer=answer,
            kind=kind,
            status="PENDING",
        )
        await self.repo.create_faq_draft(draft)
        await self.session.commit()
        return FaqDraftResponse.model_validate(draft)

    async def list_faq_drafts(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> FaqDraftListResponse:
        """Возвращает пагинированный список черновиков FAQ."""
        drafts, total = await self.repo.list_faq_drafts(
            status=status, limit=limit, offset=offset
        )
        items = [FaqDraftResponse.model_validate(d) for d in drafts]
        return FaqDraftListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    async def review_faq_draft(
        self,
        draft_id: str,
        action: str,
        reviewer_id: str,
    ) -> FaqReviewResponse:
        """Проводит ревью черновика FAQ: при approve — создаёт чанк в БЗ."""
        draft = await self.repo.get_faq_draft_by_id(draft_id)
        if draft is None:
            raise FaqDraftNotFoundError(draft_id)

        if draft.status != "PENDING":
            raise FaqDraftAlreadyReviewedError(
                draft_id=draft_id, current_status=draft.status
            )

        now = datetime.now(settings.TIMEZONE)
        new_status = "APPROVED" if action == "approve" else "REJECTED"

        await self.repo.update_faq_draft_status(
            draft_id=draft_id,
            status=new_status,
            reviewer_id=reviewer_id,
            reviewed_at=now,
        )

        chunk_id: str | None = None

        if action == "approve":
            # Создаём FAQ-чанк в kb_chunks и индексируем в Qdrant
            chunk_id = f"faq_chunk_{uuid6.uuid7()}"
            faq_text = f"Вопрос: {draft.question}\nОтвет: {draft.answer}"

            # Создаём чанк, привязываясь к dummy node (FAQ не имеет иерархии)
            # В production здесь будет создание или привязка к FAQ-узлу
            chunk_model = KbChunkModel(
                chunk_id=chunk_id,
                node_id=draft.ticket_id,  # временная привязка к ticket_id
                text=faq_text,
                context_prefix=f"FAQ из решённого обращения {draft.ticket_id}",
                hyp_questions=[draft.question],
                embedding_model_version="bge-m3",
            )
            self.session.add(chunk_model)

            # Индексируем в Qdrant
            if self.qdrant_client is not None:
                try:
                    point = self.embedding_stub.create_point(
                        chunk_id=chunk_id,
                        text=faq_text,
                        payload={
                            "doc_id": "faq_self_learning",
                            "node_id": draft.ticket_id,
                            "regime": "FAQ",
                            "has_table": False,
                            "status": "ACTIVE",
                            "kb_type": "faq",
                            "kind": "faq",
                            "context_prefix": chunk_model.context_prefix,
                            "hyp_questions": [draft.question],
                        },
                    )
                    await self.qdrant_client.upsert(
                        collection_name=settings.QDRANT_COLLECTION_NAME,
                        points=[point],
                    )
                except Exception as exc:
                    logger.warning(
                        "Ошибка при индексации FAQ-чанка %s в Qdrant: %s",
                        chunk_id,
                        exc,
                    )

        await self.session.commit()
        return FaqReviewResponse(
            draft_id=draft_id,
            status=new_status,
            chunk_id=chunk_id,
        )
