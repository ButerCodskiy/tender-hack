"""Скрипт первичного наполнения эталонного регламента Портала поставщиков (seed.py)."""

import asyncio
import logging

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.db.database import async_session_maker
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel
from src.kb.qdrant import EmbeddingStub, init_knowledge_base_collection
from src.kb.repository import KbRepository

logger = logging.getLogger("kb.seed")


async def seed_test_regulation(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient | None = None,
) -> None:
    """Создает эталонный регламент Портала поставщиков Москвы в PostgreSQL и Qdrant."""
    repo = KbRepository(session=session)
    embedding_stub = EmbeddingStub(dim=1024)

    doc_id = "DOC_PORTAL_REGULATION_V6"

    # 1. Родительский документ
    document = KbDocumentModel(
        doc_id=doc_id,
        title="Регламент ведения котировочных сессий на Портале поставщиков города Москвы",
        regime="MOS_PORTAL",
        status="indexed",
        source_url="https://zakupki.mos.ru/regulation",
    )

    # 2. Иерархические узлы AST (топологический порядок)
    node_root = KbNodeModel(
        node_id=f"{doc_id}_root",
        doc_id=doc_id,
        parent_node_id=None,
        level="document",
        section_path="Регламент котировочных сессий",
        title="Регламент ведения котировочных сессий",
        full_content="Общие положения и правила проведения котировочных сессий.",
        token_count=15,
    )

    node_sec4 = KbNodeModel(
        node_id=f"{doc_id}_sec4",
        doc_id=doc_id,
        parent_node_id=node_root.node_id,
        level="section",
        section_path="Регламент котировочных сессий / Раздел 4. Порядок подписания протоколов",
        title="Раздел 4. Порядок подписания протоколов",
        full_content="Правила и сроки подписания протоколов разногласий и итоговых контрактов.",
        token_count=35,
    )

    node_item41 = KbNodeModel(
        node_id="node_portal_zakupki_reglament_sec4_p1",
        doc_id=doc_id,
        parent_node_id=node_sec4.node_id,
        level="item",
        section_path="Регламент котировочных сессий / Раздел 4 / Пункт 4.1",
        article_no="4",
        part_no="1",
        title="Пункт 4.1. Формирование протокола разногласий",
        full_content=(
            "Участник закупки вправе сформировать и подписать протокол разногласий "
            "в личном кабинете поставщика в течение 3 рабочих дней с момента "
            "публикации проекта контракта заказчиком."
        ),
        token_count=32,
    )

    nodes = [node_root, node_sec4, node_item41]

    # 3. Поисковый чанк
    chunk = KbChunkModel(
        chunk_id="chunk_portal_zakupki_reglament_sec4_p1",
        node_id=node_item41.node_id,
        text=(
            "Участник закупки вправе сформировать и подписать протокол разногласий "
            "в личном кабинете поставщика в течение 3 рабочих дней с момента "
            "публикации проекта контракта заказчиком."
        ),
        context_prefix="Портал поставщиков Москвы. Регламент котировочных сессий.",
        hyp_questions=[
            "В какой срок можно подать протокол разногласий?",
            "Как подписать протокол разногласий на Портале поставщиков?",
        ],
        embedding_model_version="bge-m3",
    )

    # 4. Сохранение в PostgreSQL через топологический репозиторий (идемпотентно)
    existing_doc = await repo.get_document_by_id(doc_id)
    if not existing_doc:
        await repo.save_full_document_tree(
            document=document,
            nodes=nodes,
            chunks=[chunk],
        )
        logger.info(
            "Документ %s и узлы AST успешно сохранены в PostgreSQL", doc_id
        )
    else:
        logger.info(
            "Документ %s уже существует в PostgreSQL, вставка пропущена",
            doc_id,
        )

    # 5. Синхронизация с векторным индексом Qdrant (при наличии клиента)
    client = qdrant_client or get_qdrant_client()
    try:
        await init_knowledge_base_collection(client)
        point = embedding_stub.create_point(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            payload={
                "doc_id": doc_id,
                "node_id": chunk.node_id,
                "title": node_item41.title,
                "section_path": node_item41.section_path,
                "source_url": document.source_url,
                "regime": "MOS_PORTAL",
                "has_table": False,
                "status": "ACTIVE",
                "kb_type": "guide",
                "kind": "chunk",
            },
        )
        target_collections = {
            settings.QDRANT_COLLECTION_NAME,
            "knowledge_base",
            "tender_chunks",
        }
        for target_col in target_collections:
            try:
                await client.upsert(
                    collection_name=target_col,
                    points=[point],
                )
                logger.info(
                    "Точка чанка %s сохранена в Qdrant %s (UUIDv5: %s)",
                    chunk.chunk_id,
                    target_col,
                    point.id,
                )
            except Exception as e:
                logger.warning(
                    "Не удалось сохранить точку в %s: %s", target_col, e
                )
    except Exception as exc:
        logger.warning(
            "Синхронизация с Qdrant пропущена или завершилась ошибкой: %s", exc
        )


async def main() -> None:
    """Точка входа запуска сидинга через python -m src.kb.seed."""
    async with async_session_maker() as session:
        await seed_test_regulation(session=session)


if __name__ == "__main__":
    asyncio.run(main())
