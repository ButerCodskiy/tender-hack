"""Комплексные тесты парсера и загрузчика таблиц типовых вопросов и ответов (FAQ Loader)."""

import hashlib
import io
from unittest.mock import AsyncMock, MagicMock

import openpyxl
import pytest

from src.kb.faq_loader import FaqLoader, FaqParser
from src.kb.models import KbChunkModel, KbDocumentModel, KbNodeModel
from src.kb.service import KbService


def _create_xlsx_bytes(
    rows: list[list[str]], sheet_title: str = "Лист 1"
) -> bytes:
    """Вспомогательная функция формирования in-memory XLSX файла."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def test_faq_parser_xlsx_with_explicit_headers() -> None:
    """Проверяет парсинг XLSX с явными заголовками 'Вопрос' и 'Ответ'."""
    data = [
        ["Вопрос", "Ответ", "Доп. колонка"],
        [
            "Как зарегистрироваться на портале?",
            "Для регистрации перейдите в ЕРУЗ.",
            "123",
        ],
        [
            "Как настроить плагин ЭЦП?",
            "Установите КриптоПро ЭЦП Browser plug-in.",
            "456",
        ],
    ]
    content = _create_xlsx_bytes(data)
    items, total_rows = FaqParser.parse_xlsx(content)

    assert total_rows == 3
    assert len(items) == 2
    assert items[0].question == "Как зарегистрироваться на портале?"
    assert items[0].answer == "Для регистрации перейдите в ЕРУЗ."
    assert items[0].row_idx == 2
    assert items[1].question == "Как настроить плагин ЭЦП?"
    assert items[1].answer == "Установите КриптоПро ЭЦП Browser plug-in."
    assert items[1].row_idx == 3


def test_faq_parser_xlsx_with_offset_headers() -> None:
    """Проверяет парсинг XLSX со смещением шапки (заголовок на 3-й строке)."""
    data = [
        ["Регламент Портала поставщиков Москвы 2026", None],
        ["Таблица типовых ответов", None],
        ["Текст вопроса пользователя", "Решение оператора"],
        [
            "Где найти котировочные сессии?",
            "В главном меню перейдите в раздел Котировочные сессии.",
        ],
    ]
    content = _create_xlsx_bytes(data)
    items, total_rows = FaqParser.parse_xlsx(content)

    assert total_rows == 4
    assert len(items) == 1
    assert items[0].question == "Где найти котировочные сессии?"
    assert (
        items[0].answer
        == "В главном меню перейдите в раздел Котировочные сессии."
    )
    assert items[0].row_idx == 4


def test_faq_parser_xlsx_without_headers_fallback() -> None:
    """Проверяет фолбэк парсинга XLSX без явных заголовков (колонка 0 и 1 с 1-й строки)."""
    data = [
        ["Что такое СТЕ?", "Стандартная товарная единица."],
        ["Как подать оферту?", "Нажмите кнопку Подать оферту в сессии."],
    ]
    content = _create_xlsx_bytes(data)
    items, total_rows = FaqParser.parse_xlsx(content)

    assert total_rows == 2
    assert len(items) == 2
    assert items[0].question == "Что такое СТЕ?"
    assert items[0].answer == "Стандартная товарная единица."
    assert items[1].question == "Как подать оферту?"


def test_faq_parser_csv_utf8_semicolon_and_comma() -> None:
    """Проверяет парсинг CSV с разделителями точка с запятой и запятая."""
    # 1. Точка с запятой
    csv_semicolon = (
        "Вопрос;Ответ\n"
        "Как войти в личный кабинет?;Используйте логин и пароль или ЭЦП.\n"
    ).encode()

    items_semi, _ = FaqParser.parse_csv(csv_semicolon)
    assert len(items_semi) == 1
    assert items_semi[0].question == "Как войти в личный кабинет?"
    assert items_semi[0].answer == "Используйте логин и пароль или ЭЦП."

    # 2. Запятая
    csv_comma = (
        "question,answer\n"
        '"Сколько длится сессия?","Котировочная сессия длится от 3 до 24 часов."\n'
    ).encode()

    items_comma, _ = FaqParser.parse_csv(csv_comma)
    assert len(items_comma) == 1
    assert items_comma[0].question == "Сколько длится сессия?"
    assert (
        items_comma[0].answer == "Котировочная сессия длится от 3 до 24 часов."
    )


def test_faq_parser_csv_encodings_bom_and_cp1251() -> None:
    """Проверяет поддержку кодировок UTF-8 с BOM (utf-8-sig) и Windows-1251 (cp1251)."""
    text = "Вопрос;Ответ\nГде скачать акт?;В разделе документов контракта."

    # UTF-8 с BOM (типично для экспорта из Excel)
    content_bom = text.encode("utf-8-sig")
    items_bom, _ = FaqParser.parse_csv(content_bom)
    assert len(items_bom) == 1
    assert items_bom[0].question == "Где скачать акт?"

    # CP1251
    content_cp1251 = text.encode("cp1251")
    items_cp1251, _ = FaqParser.parse_csv(content_cp1251)
    assert len(items_cp1251) == 1
    assert items_cp1251[0].question == "Где скачать акт?"


def test_faq_parser_skips_empty_and_incomplete_rows() -> None:
    """Проверяет пропуск пустых строк и строк без вопроса или ответа."""
    data = [
        ["Вопрос", "Ответ"],
        ["", ""],
        ["Только вопрос", ""],
        ["", "Только ответ"],
        ["   ", "   "],
        ["Корректный вопрос", "Корректный ответ"],
    ]
    content = _create_xlsx_bytes(data)
    items, total_rows = FaqParser.parse_xlsx(content)

    assert total_rows == 6
    assert len(items) == 1
    assert items[0].question == "Корректный вопрос"
    assert items[0].answer == "Корректный ответ"


def test_faq_loader_id_and_hash_generation() -> None:
    """Проверяет детерминированное формирование MD5 идентификаторов по ТЗ."""
    filename = "faq_portal_2026.xlsx"
    expected_doc_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()
    assert (
        FaqLoader.generate_doc_id(filename) == f"DOC_FAQ_{expected_doc_hash}"
    )
    assert (
        FaqLoader.generate_node_id(filename) == f"NODE_FAQ_{expected_doc_hash}"
    )

    row_raw = f"{filename}_5"
    expected_chunk_hash = hashlib.md5(row_raw.encode("utf-8")).hexdigest()
    assert (
        FaqLoader.generate_chunk_id(filename, 5)
        == f"chunk_faq_{expected_chunk_hash}"
    )


def _create_mock_session() -> AsyncMock:
    """Создает мок асинхронной сессии с синхронными методами add и add_all."""
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.add_all = MagicMock()
    return mock


@pytest.mark.asyncio
async def test_faq_loader_full_lifecycle_and_qdrant_payload() -> None:
    """Проверяет полный цикл загрузки, создание синтетических моделей и контракт Qdrant payload."""
    filename = "test_qa.csv"
    csv_content = (
        "Вопрос;Ответ\n"
        "Как сменить пароль?;В настройках профиля пользователя.\n"
        "Как подать заявку?;В карточке котировочной сессии.\n"
    ).encode()

    mock_session = _create_mock_session()
    mock_repo = AsyncMock()
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])

    loader = FaqLoader(
        session=mock_session,
        repo=mock_repo,
        qdrant_client=mock_qdrant,
    )

    result = await loader.load_faq_table(
        file_content=csv_content,
        filename=filename,
        regime="MOS_PORTAL",
    )

    assert result.filename == filename
    assert result.total_rows == 3
    assert result.imported_count == 2
    assert result.skipped_count == 1
    assert result.doc_id.startswith("DOC_FAQ_")
    assert result.node_id.startswith("NODE_FAQ_")
    assert result.status == "indexed"

    # Проверка вызова очистки дубликатов
    mock_repo.delete_document.assert_awaited_once_with(result.doc_id)
    mock_qdrant.delete.assert_awaited_once()

    # Проверка создания родительского документа
    mock_repo.create_document.assert_awaited_once()
    saved_doc = mock_repo.create_document.call_args[0][0]
    assert isinstance(saved_doc, KbDocumentModel)
    assert saved_doc.doc_id == result.doc_id
    assert saved_doc.status == "indexed"
    assert saved_doc.regime == "MOS_PORTAL"

    # Проверка добавления синтетического узла и чанков в сессию
    assert mock_session.add.call_count >= 1
    added_node = mock_session.add.call_args[0][0]
    assert isinstance(added_node, KbNodeModel)
    assert added_node.node_id == result.node_id
    assert added_node.level == "item"
    assert added_node.section_path == f"FAQ Import > {filename}"

    assert mock_session.add_all.call_count == 1
    added_chunks = mock_session.add_all.call_args[0][0]
    assert len(added_chunks) == 2
    assert all(isinstance(c, KbChunkModel) for c in added_chunks)

    # Проверка вызова upsert в Qdrant и контракта payload
    mock_qdrant.upsert.assert_awaited_once()
    upsert_kwargs = mock_qdrant.upsert.call_args[1]
    points = upsert_kwargs["points"]
    assert len(points) == 2

    first_payload = points[0].payload
    assert first_payload["doc_id"] == result.doc_id
    assert first_payload["node_id"] == result.node_id
    assert first_payload["kb_type"] == "faq"
    assert first_payload["kind"] == "qa_pair"
    assert first_payload["status"] == "ACTIVE"
    assert first_payload["has_table"] is False
    assert first_payload["question"] == "Как сменить пароль?"
    assert first_payload["answer"] == "В настройках профиля пользователя."
    assert (
        first_payload["text"]
        == "Вопрос: Как сменить пароль?\nОтвет: В настройках профиля пользователя."
    )

    # Проверка фиксации транзакции
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_faq_loader_batching_over_100_rows() -> None:
    """Проверяет разбивку на пакеты по BATCH_SIZE = 100 при загрузке 125 строк."""
    rows = [["Вопрос", "Ответ"]]
    for i in range(125):
        rows.append([f"Вопрос номер {i}?", f"Ответ номер {i}."])

    content = _create_xlsx_bytes(rows)

    mock_session = _create_mock_session()
    mock_repo = AsyncMock()
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])

    loader = FaqLoader(
        session=mock_session,
        repo=mock_repo,
        qdrant_client=mock_qdrant,
    )

    result = await loader.load_faq_table(
        file_content=content,
        filename="large_faq.xlsx",
    )

    assert result.total_rows == 126
    assert result.imported_count == 125
    # 125 строк делятся на батчи 100 и 25 -> ровно 2 вызова upsert и add_all
    assert mock_qdrant.upsert.await_count == 2
    assert mock_session.add_all.call_count == 2


@pytest.mark.asyncio
async def test_kb_service_import_faq_table_integration() -> None:
    """Проверяет вызов импорта через фасадный сервис KbService."""
    mock_session = _create_mock_session()
    mock_repo = AsyncMock()
    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections.return_value = MagicMock(collections=[])

    service = KbService(
        repo=mock_repo,
        session=mock_session,
        qdrant_client=mock_qdrant,
    )

    csv_data = "Вопрос;Ответ\nТест вопроса;Тест ответа\n".encode()
    result = await service.import_faq_table(
        file_content=csv_data,
        filename="service_test.csv",
    )

    assert result.imported_count == 1
    assert result.filename == "service_test.csv"
