"""Модуль прямого импорта структурированных таблиц типовых вопросов и ответов (FAQ Loader).

Обеспечивает парсинг XLSX и CSV, генерацию синтетических документов и узлов
для соблюдения внешних ключей, пакетную вставку в PostgreSQL (kb_chunks)
и индексацию в Qdrant (коллекция knowledge_base).
"""

import csv
import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import openpyxl
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.qdrant_client import get_qdrant_client
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel
from src.kb.qdrant import (
    EmbeddingStub,
    chunk_id_to_qdrant_uuid,
    init_knowledge_base_collection,
)
from src.kb.repository import KbRepository
from src.kb.schemas import FaqImportResultSchema

logger = logging.getLogger(__name__)


@dataclass
class FaqRow:
    """Структура распарсенной строки вопроса и ответа."""

    row_idx: int
    question: str
    answer: str


class FaqParser:
    """Парсер структурированных файлов таблиц FAQ (XLSX и CSV)."""

    QUESTION_HEADER_PATTERN = re.compile(
        r"вопрос|question|тема|наименование\s+вопроса", re.IGNORECASE
    )
    ANSWER_HEADER_PATTERN = re.compile(
        r"ответ|answer|решение|порядок\s+действий", re.IGNORECASE
    )

    @classmethod
    def _find_header_columns(
        cls, rows: list[list[Any]]
    ) -> tuple[int, int, int]:
        """Определяет индексы колонок вопроса и ответа, а также строку начала данных.

        Возвращает:
            (question_col_idx, answer_col_idx, start_data_row_idx)
        """
        max_search_rows = min(5, len(rows))
        for row_idx in range(max_search_rows):
            row = rows[row_idx]
            q_col: int | None = None
            a_col: int | None = None

            for col_idx, cell in enumerate(row):
                cell_str = str(cell or "").strip()
                if not cell_str:
                    continue
                if q_col is None and cls.QUESTION_HEADER_PATTERN.search(
                    cell_str
                ):
                    q_col = col_idx
                elif a_col is None and cls.ANSWER_HEADER_PATTERN.search(
                    cell_str
                ):
                    a_col = col_idx

            if q_col is not None and a_col is not None and q_col != a_col:
                return q_col, a_col, row_idx + 1

        # Фолбэк: если заголовки не распознаны, берем колонку 0 и 1 с 0-й строки
        return 0, 1, 0

    @classmethod
    def parse_xlsx(cls, content: bytes) -> tuple[list[FaqRow], int]:
        """Парсит книгу Excel (XLSX), считывая активный лист."""
        wb = openpyxl.load_workbook(
            filename=io.BytesIO(content),
            data_only=True,
            read_only=True,
        )
        sheet = wb.active
        if sheet is None:
            wb.close()
            return [], 0

        raw_rows: list[list[Any]] = []
        for row in sheet.iter_rows(values_only=True):
            raw_rows.append(list(row))
        wb.close()

        if not raw_rows:
            return [], 0

        q_col, a_col, start_row = cls._find_header_columns(raw_rows)
        parsed_items: list[FaqRow] = []
        total_rows = len(raw_rows)

        for idx in range(start_row, total_rows):
            row = raw_rows[idx]
            val_q = row[q_col] if q_col < len(row) else None
            val_a = row[a_col] if a_col < len(row) else None

            str_q = str(val_q or "").strip()
            str_a = str(val_a or "").strip()

            if str_q and str_a:
                parsed_items.append(
                    FaqRow(
                        row_idx=idx + 1,
                        question=str_q,
                        answer=str_a,
                    )
                )

        return parsed_items, total_rows

    @classmethod
    def parse_csv(cls, content: bytes) -> tuple[list[FaqRow], int]:
        """Парсит CSV с автоопределением кодировки и разделителя."""
        text = ""
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = content.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not text:
            text = content.decode("utf-8", errors="replace")

        # Определение разделителя
        first_line = text.splitlines()[0] if text.splitlines() else ""
        semicolon_count = first_line.count(";")
        comma_count = first_line.count(",")
        tab_count = first_line.count("\t")

        if semicolon_count >= comma_count and semicolon_count > 0:
            delimiter = ";"
        elif comma_count > 0:
            delimiter = ","
        elif tab_count > 0:
            delimiter = "\t"
        else:
            delimiter = ";"

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [list(row) for row in reader]

        if not raw_rows:
            return [], 0

        q_col, a_col, start_row = cls._find_header_columns(raw_rows)
        parsed_items: list[FaqRow] = []
        total_rows = len(raw_rows)

        for idx in range(start_row, total_rows):
            row = raw_rows[idx]
            val_q = row[q_col] if q_col < len(row) else ""
            val_a = row[a_col] if a_col < len(row) else ""

            str_q = str(val_q or "").strip()
            str_a = str(val_a or "").strip()

            if str_q and str_a:
                parsed_items.append(
                    FaqRow(
                        row_idx=idx + 1,
                        question=str_q,
                        answer=str_a,
                    )
                )

        return parsed_items, total_rows

    @classmethod
    def parse(cls, content: bytes, filename: str) -> tuple[list[FaqRow], int]:
        """Маршрутизирует файл в соответствующий парсер по расширению."""
        lower_name = filename.lower()
        if lower_name.endswith((".xlsx", ".xlsm", ".xltx")):
            return cls.parse_xlsx(content)
        return cls.parse_csv(content)


class FaqLoader:
    """Загрузчик и индексатор структурированных таблиц FAQ."""

    BATCH_SIZE: int = 100

    def __init__(
        self,
        session: AsyncSession,
        repo: KbRepository | None = None,
        qdrant_client: AsyncQdrantClient | None = None,
        embedding_generator: Any | None = None,
    ) -> None:
        """Инициализирует загрузчик сессией БД, репозиторием и клиентом Qdrant."""
        self.session = session
        self.repo = repo or KbRepository(session)
        self.qdrant_client = qdrant_client or get_qdrant_client()
        self.embedding_generator = embedding_generator or EmbeddingStub(
            dim=1024
        )

    @staticmethod
    def generate_doc_id(filename: str) -> str:
        """Генерирует синтетический идентификатор документа по имени файла."""
        md5_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()
        return f"DOC_FAQ_{md5_hash}"

    @staticmethod
    def generate_node_id(filename: str) -> str:
        """Генерирует синтетический идентификатор узла по имени файла."""
        md5_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()
        return f"NODE_FAQ_{md5_hash}"

    @staticmethod
    def generate_chunk_id(filename: str, row_idx: int) -> str:
        """Генерирует синтетический идентификатор чанка по имени файла и номеру строки."""
        raw = f"{filename}_{row_idx}"
        md5_hash = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return f"chunk_faq_{md5_hash}"

    async def _clean_existing_document(
        self, doc_id: str, collection_name: str
    ) -> None:
        """Идемпотентно удаляет старый документ из PostgreSQL и Qdrant."""
        # 1. Удаление из PostgreSQL (каскадно удалит узлы и чанки)
        await self.repo.delete_document(doc_id)

        # 2. Удаление из Qdrant по фильтру doc_id
        try:
            filter_selector = qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="doc_id",
                            match=qmodels.MatchValue(value=doc_id),
                        )
                    ]
                )
            )
            await self.qdrant_client.delete(
                collection_name=collection_name,
                points_selector=filter_selector,
            )
        except Exception as exc:
            logger.warning(
                "Предупреждение при удалении старых точек Qdrant для %s: %s",
                doc_id,
                exc,
            )

    async def load_faq_table(
        self,
        file_content: bytes,
        filename: str,
        regime: str = "MOS_PORTAL",
        collection_name: str | None = None,
    ) -> FaqImportResultSchema:
        """Выполняет полный цикл импорта таблицы FAQ.

        1. Парсит пары «вопрос-ответ» из XLSX или CSV.
        2. Идемпотентно очищает предыдущую версию документа при совпадении doc_id.
        3. Создает синтетический KbDocumentModel и KbNodeModel.
        4. Пакетами по 100 строк векторизует и вставляет данные в Qdrant и PostgreSQL.
        5. Фиксирует транзакцию базы данных.
        """
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME

        # Инициализация коллекции в Qdrant при необходимости
        try:
            await init_knowledge_base_collection(
                self.qdrant_client, target_collection
            )
        except Exception as exc:
            logger.warning(
                "Коллекция Qdrant уже существует или не требует пересоздания: %s",
                exc,
            )

        # 1. Разбор файла
        parsed_rows, total_rows = FaqParser.parse(file_content, filename)

        doc_id = self.generate_doc_id(filename)
        node_id = self.generate_node_id(filename)

        # 2. Идемпотентная очистка дубликатов
        await self._clean_existing_document(doc_id, target_collection)

        if not parsed_rows:
            return FaqImportResultSchema(
                doc_id=doc_id,
                node_id=node_id,
                filename=filename,
                total_rows=total_rows,
                imported_count=0,
                skipped_count=total_rows,
                status="indexed",
            )

        # 3. Создание синтетического родительского документа и узла
        doc_model = KbDocumentModel(
            doc_id=doc_id,
            title=filename,
            regime=regime,
            edition_date=datetime.now(settings.TIMEZONE).date(),
            status="indexed",
            error_message=None,
            source_url=f"faq://{filename}",
        )
        await self.repo.create_document(doc_model)

        node_model = KbNodeModel(
            node_id=node_id,
            doc_id=doc_id,
            parent_node_id=None,
            level="item",
            section_path=f"FAQ Import > {filename}",
            article_no=None,
            part_no=None,
            title="База типовых вопросов",
            full_content="Синтетический контейнер импорта FAQ",
            table_md=None,
            token_count=0,
        )
        self.session.add(node_model)
        await self.session.flush()

        # 4. Пакетная векторизация и сохранение чанков
        imported_count = 0
        for i in range(0, len(parsed_rows), self.BATCH_SIZE):
            batch_rows = parsed_rows[i : i + self.BATCH_SIZE]
            batch_chunks: list[KbChunkModel] = []
            batch_points: list[qmodels.PointStruct] = []

            for row in batch_rows:
                chunk_id = self.generate_chunk_id(filename, row.row_idx)
                chunk_text = f"Вопрос: {row.question}\nОтвет: {row.answer}"

                # Модель SQLAlchemy
                chunk_model = KbChunkModel(
                    chunk_id=chunk_id,
                    node_id=node_id,
                    text=chunk_text,
                    context_prefix=None,
                    hyp_questions=[],
                    embedding_model_version="bge-m3",
                )
                batch_chunks.append(chunk_model)

                # Точка для Qdrant
                payload = {
                    "node_id": node_id,
                    "doc_id": doc_id,
                    "regime": regime,
                    "kb_type": "faq",
                    "kind": "qa_pair",
                    "status": "ACTIVE",
                    "question": row.question,
                    "answer": row.answer,
                    "has_table": False,
                }

                if hasattr(self.embedding_generator, "create_point"):
                    point = self.embedding_generator.create_point(
                        chunk_id=chunk_id,
                        text=chunk_text,
                        payload=payload,
                    )
                else:
                    vectors = self.embedding_generator.generate_vectors(
                        chunk_text
                    )
                    point = qmodels.PointStruct(
                        id=str(chunk_id_to_qdrant_uuid(chunk_id)),
                        vector=vectors,
                        payload={
                            **payload,
                            "chunk_id": chunk_id,
                            "text": chunk_text,
                        },
                    )
                batch_points.append(point)

            # Пакетный upsert в Qdrant
            await self.qdrant_client.upsert(
                collection_name=target_collection,
                points=batch_points,
            )

            # Пакетное добавление в PostgreSQL
            self.session.add_all(batch_chunks)
            await self.session.flush()
            imported_count += len(batch_rows)

        # 5. Фиксация транзакции
        await self.session.commit()

        skipped_count = total_rows - imported_count
        return FaqImportResultSchema(
            doc_id=doc_id,
            node_id=node_id,
            filename=filename,
            total_rows=total_rows,
            imported_count=imported_count,
            skipped_count=skipped_count,
            status="indexed",
        )
