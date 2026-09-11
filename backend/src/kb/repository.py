"""Слой доступа к данным нормативной базы знаний (KbRepository)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.kb.models import (
    FaqModerationQueueModel,
    KbChunkModel,
    KbDocumentModel,
    KbNodeModel,
)


def topological_sort_nodes(nodes: list[KbNodeModel]) -> list[KbNodeModel]:
    """Сортирует узлы AST от корня к листьям для исключения ForeignKeyViolation."""
    node_map = {n.node_id: n for n in nodes}
    visited: set[str] = set()
    sorted_nodes: list[KbNodeModel] = []

    def visit(node: KbNodeModel) -> None:
        if node.node_id in visited:
            return
        if node.parent_node_id and node.parent_node_id in node_map:
            visit(node_map[node.parent_node_id])
        visited.add(node.node_id)
        sorted_nodes.append(node)

    for n in nodes:
        visit(n)

    return sorted_nodes


class KbRepository:
    """Репозиторий нормативных документов, разделов и чанков базы знаний."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_document(self, doc: KbDocumentModel) -> KbDocumentModel:
        """Сохраняет метаданные нового документа со статусом uploaded."""
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_document_by_id(self, doc_id: str) -> KbDocumentModel | None:
        """Возвращает документ по его doc_id."""
        return await self.session.get(KbDocumentModel, doc_id)

    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Обновляет статус обработки документа и текст ошибки при сбое."""
        doc = await self.get_document_by_id(doc_id)
        if doc is not None:
            doc.status = status
            doc.error_message = error_message
            await self.session.flush()

    async def save_full_document_tree(
        self,
        document: KbDocumentModel,
        nodes: list[KbNodeModel],
        chunks: list[KbChunkModel],
    ) -> None:
        """Атомарно сохраняет полное дерево документа с топологической сортировкой узлов.

        Порядок сохранения:
        1. Документ (kb_documents);
        2. Узлы (kb_nodes) в порядке от корня к листьям (parent_node_id сохраняются первыми);
        3. Чанки (kb_chunks);
        4. Фиксация транзакции commit.
        """
        # 1. Проверяем или добавляем родительский документ
        existing_doc = await self.get_document_by_id(document.doc_id)
        if existing_doc is None:
            self.session.add(document)
        else:
            existing_doc.status = document.status
            existing_doc.error_message = document.error_message
        await self.session.flush()

        # 2. Топологическая вставка узлов AST
        sorted_nodes = topological_sort_nodes(nodes)
        for node in sorted_nodes:
            self.session.add(node)
        await self.session.flush()

        # 3. Вставка чанков
        for chunk in chunks:
            self.session.add(chunk)

        # 4. Фиксация транзакции
        await self.session.commit()

    async def list_documents(
        self,
        skip: int = 0,
        limit: int = 50,
        regime: str | None = None,
        status: str | None = None,
    ) -> tuple[list[KbDocumentModel], int]:
        """Возвращает список документов с пагинацией, фильтрацией и общим количеством."""
        base_stmt = select(KbDocumentModel)
        count_stmt = select(func.count(KbDocumentModel.doc_id))

        if regime:
            base_stmt = base_stmt.where(KbDocumentModel.regime == regime)
            count_stmt = count_stmt.where(KbDocumentModel.regime == regime)
        if status:
            base_stmt = base_stmt.where(KbDocumentModel.status == status)
            count_stmt = count_stmt.where(KbDocumentModel.status == status)

        total = await self.session.scalar(count_stmt) or 0

        query_stmt = (
            base_stmt.order_by(KbDocumentModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.scalars(query_stmt)
        items = list(result.all())
        return items, total

    async def get_document_status_info(
        self, doc_id: str
    ) -> tuple[KbDocumentModel, int] | None:
        """Возвращает документ и количество связанных чанков."""
        doc = await self.get_document_by_id(doc_id)
        if doc is None:
            return None

        count_stmt = (
            select(func.count(KbChunkModel.chunk_id))
            .select_from(KbChunkModel)
            .join(KbNodeModel, KbChunkModel.node_id == KbNodeModel.node_id)
            .where(KbNodeModel.doc_id == doc_id)
        )
        chunks_count = await self.session.scalar(count_stmt) or 0
        return doc, chunks_count

    async def get_node_by_id(self, node_id: str) -> KbNodeModel | None:
        """Возвращает узел документа по его идентификатору."""
        return await self.session.get(KbNodeModel, node_id)

    async def update_node(
        self,
        node_id: str,
        title: str | None = None,
        section_path: str | None = None,
    ) -> KbNodeModel | None:
        """Обновляет заголовок и хлебные крошки пути узла."""
        node = await self.get_node_by_id(node_id)
        if node is None:
            return None

        if title is not None:
            node.title = title
        if section_path is not None:
            node.section_path = section_path

        await self.session.flush()
        return node

    async def delete_document(self, doc_id: str) -> bool:
        """Каскадно удаляет документ и связанные узлы и чанки."""
        doc = await self.get_document_by_id(doc_id)
        if doc is not None:
            await self.session.delete(doc)
            await self.session.flush()
            return True
        return False

    # ── MED-04: Фоновое обогащение чанков ──────────────────────────

    async def list_unenriched_chunks(
        self,
        batch_size: int = 50,
    ) -> list[KbChunkModel]:
        """Возвращает чанки, у которых ещё нет context_prefix (не обогащены)."""
        stmt = (
            select(KbChunkModel)
            .where(KbChunkModel.context_prefix.is_(None))
            .limit(batch_size)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_chunk_by_id(self, chunk_id: str) -> KbChunkModel | None:
        """Возвращает чанк по его chunk_id."""
        return await self.session.get(KbChunkModel, chunk_id)

    async def update_chunk_enrichment(
        self,
        chunk_id: str,
        context_prefix: str,
        hyp_questions: list[str],
    ) -> KbChunkModel | None:
        """Обновляет context_prefix и hyp_questions чанка после обогащения LLM."""
        chunk = await self.get_chunk_by_id(chunk_id)
        if chunk is None:
            return None
        chunk.context_prefix = context_prefix
        chunk.hyp_questions = hyp_questions
        await self.session.flush()
        return chunk

    # ── MED-05: FAQ-черновики и очередь модерации ──────────────────

    async def create_faq_draft(
        self,
        draft: FaqModerationQueueModel,
    ) -> FaqModerationQueueModel:
        """Сохраняет новый черновик FAQ в очередь модерации."""
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def list_faq_drafts(
        self,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[FaqModerationQueueModel], int]:
        """Возвращает пагинированный список черновиков FAQ с фильтрацией по статусу."""
        base_stmt = select(FaqModerationQueueModel)
        count_stmt = select(func.count(FaqModerationQueueModel.id))

        if status:
            base_stmt = base_stmt.where(
                FaqModerationQueueModel.status == status
            )
            count_stmt = count_stmt.where(
                FaqModerationQueueModel.status == status
            )

        total = await self.session.scalar(count_stmt) or 0

        query_stmt = (
            base_stmt.order_by(FaqModerationQueueModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(query_stmt)
        return list(result.all()), total

    async def get_faq_draft_by_id(
        self,
        draft_id: str,
    ) -> FaqModerationQueueModel | None:
        """Возвращает черновик FAQ по его идентификатору."""
        return await self.session.get(FaqModerationQueueModel, draft_id)

    async def update_faq_draft_status(
        self,
        draft_id: str,
        status: str,
        reviewer_id: str,
        reviewed_at: datetime,
    ) -> FaqModerationQueueModel | None:
        """Обновляет статус черновика FAQ после ревью супервизором."""
        draft = await self.get_faq_draft_by_id(draft_id)
        if draft is None:
            return None
        draft.status = status
        draft.reviewer_id = reviewer_id
        draft.reviewed_at = reviewed_at
        await self.session.flush()
        return draft
