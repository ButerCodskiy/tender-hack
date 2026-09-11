"""
Тесты конвейера глубокого разбора документов и таблиц (HIGH-05).
Проверяют:
1. Детерминированную генерацию node_id: 'NODE_' || md5(doc_id || '_' || section_path || '_' || title)
2. Иерархический section_path со стеком заголовков (Раздел > Статья > Пункт)
3. Двойное представление таблиц и привязку context_prefix к чанкам
4. Жизненный цикл фоновой задачи Taskiq index_kb_document (indexing -> indexed / failed)
"""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.kb.chunker import HierarchicalChunker
from src.kb.models import KbDocumentModel
from src.kb.parser import DocumentParser
from src.kb.schemas import ParsedNodeSchema
from src.kb.tasks import index_kb_document


def test_deterministic_node_id_formula():
    """Проверка генерации node_id по строгому правилу ТЗ."""
    doc_id = "DOC_REG_01"
    section_path = "Раздел 1 > Статья 4 > Пункт 2"
    title = "Пункт 2. Сроки подачи заявок"

    raw_key = f"{doc_id}_{section_path}_{title}".encode()
    expected_md5 = hashlib.md5(raw_key).hexdigest()
    expected_id = f"NODE_{expected_md5}"

    generated_id = DocumentParser.generate_node_id(
        doc_id=doc_id, section_path=section_path, title=title
    )
    assert generated_id == expected_id
    assert generated_id.startswith("NODE_")
    assert len(generated_id) == 37  # "NODE_" (5) + 32 md5 hex


def test_deterministic_node_id_uniqueness_on_collision():
    """Проверка детерминированного суффикса при совпадении ключей внутри одного документа."""
    doc_id = "DOC_01"
    section_path = "Раздел 1"
    title = "Текстовый фрагмент"
    seen: dict[str, int] = {}

    id1 = DocumentParser.generate_node_id(doc_id, section_path, title, seen)
    id2 = DocumentParser.generate_node_id(doc_id, section_path, title, seen)
    id3 = DocumentParser.generate_node_id(doc_id, section_path, title, seen)

    assert id1.startswith("NODE_")
    assert id2 == f"{id1}_2"
    assert id3 == f"{id1}_3"


def test_hierarchical_heading_stack_and_section_path(tmp_path: Path):
    """Проверка построения дерева узлов и материализованного пути section_path."""
    sample_txt = tmp_path / "hierarchy_doc.txt"
    sample_txt.write_text(
        "Раздел 1. Общие положения\n"
        "Текст вводного раздела.\n\n"
        "Статья 4. Порядок обеспечения\n"
        "Текст статьи 4.\n\n"
        "4.1. Размер обеспечения\n"
        "Для котировочных сессий размер составляет 0.5%.\n",
        encoding="utf-8",
    )

    parser = DocumentParser()
    result = parser.parse_document(file_path=sample_txt, doc_id="DOC_HIER_01")

    # Ищем узлы по заголовкам
    headings = [
        n
        for n in result.nodes
        if n.level in ("section", "article", "item")
        and not n.title.endswith("...")
    ]
    assert len(headings) >= 3

    node_sec = next(n for n in result.nodes if "Раздел 1" in n.title)
    node_art = next(n for n in result.nodes if "Статья 4" in n.title)
    node_item = next(n for n in result.nodes if "4.1" in n.title)

    # Проверяем накопительный section_path
    assert node_sec.section_path == "Раздел 1. Общие положения"
    assert node_sec.parent_node_id is None

    assert (
        node_art.section_path
        == "Раздел 1. Общие положения > Статья 4. Порядок обеспечения"
    )
    assert node_art.parent_node_id == node_sec.node_id

    assert (
        node_item.section_path
        == "Раздел 1. Общие положения > Статья 4. Порядок обеспечения > 4.1. Размер обеспечения"
    )
    assert node_item.parent_node_id == node_art.node_id

    # Проверяем детерминированность их ID
    for n in (node_sec, node_art, node_item):
        assert n.node_id.startswith("NODE_")
        expected = DocumentParser.generate_node_id(
            "DOC_HIER_01", n.section_path, n.title
        )
        assert n.node_id == expected


def test_chunker_context_prefix_enrichment():
    """Проверка обогащения чанка контекстным префиксом section_path."""
    chunker = HierarchicalChunker(max_tokens=350, min_tail_tokens=80)
    node = ParsedNodeSchema(
        node_id="NODE_TEST123",
        doc_id="DOC_01",
        level="article",
        section_path="Регламент > Раздел 2 > Статья 5",
        title="Статья 5. Сроки",
        full_content="Срок рассмотрения заявок составляет 3 рабочих дня.",
        token_count=10,
    )

    chunks = chunker.chunk_node(node)
    assert len(chunks) == 1
    assert chunks[0].context_prefix == "Регламент > Раздел 2 > Статья 5"
    assert "Срок рассмотрения" in chunks[0].text


def test_dual_view_table_and_chunk_flags(tmp_path: Path):
    """Проверка разделения представлений таблицы (table_md + facts в чанках с context_prefix)."""
    parser = DocumentParser()
    node = ParsedNodeSchema(
        node_id="NODE_TABLE_1",
        doc_id="DOC_01",
        level="item",
        section_path="Регламент > Тарифы",
        title="Таблица тарифов",
        full_content="| Услуга | Стоимость |\n|---|---|\n| Базовая | 500 руб. |",
        table_md="| Услуга | Стоимость |\n|---|---|\n| Базовая | 500 руб. |",
        token_count=15,
    )
    facts = ["Услуга: Базовая; Стоимость: 500 руб."]

    chunks = parser.chunker.chunk_node(node, linearized_table_facts=facts)
    table_chunk = next(c for c in chunks if c.has_table)

    assert table_chunk.has_table is True
    assert "Услуга: Базовая" in table_chunk.text
    assert table_chunk.context_prefix == "Регламент > Тарифы"


@pytest.mark.asyncio
async def test_taskiq_index_kb_document_success_lifecycle(tmp_path: Path):
    """Проверка полного жизненного цикла Taskiq задачи при успехе (indexing -> indexed)."""
    sample_file = tmp_path / "doc.txt"
    sample_file.write_text(
        "Раздел 1. Старт\nТекст регламента.", encoding="utf-8"
    )

    mock_doc = KbDocumentModel(
        doc_id="DOC_TASKIQ_OK",
        title="Test Document",
        status="uploaded",
    )

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_document_by_id.return_value = mock_doc

    mock_qdrant = AsyncMock()

    with (
        patch("src.kb.tasks.async_session_maker") as mock_session_maker,
        patch("src.kb.tasks.KbRepository", return_value=mock_repo),
        patch("src.kb.tasks.get_qdrant_client", return_value=mock_qdrant),
        patch(
            "src.kb.tasks.init_knowledge_base_collection",
            new_callable=AsyncMock,
        ),
    ):
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        await index_kb_document(
            doc_id="DOC_TASKIQ_OK",
            file_path=str(sample_file),
            regime="MOS_PORTAL",
        )

        # Проверяем вызовы обновления статусов
        status_calls = [
            call.kwargs.get("status") or call.args[1]
            for call in mock_repo.update_document_status.call_args_list
        ]
        # Первый вызов - 'indexing', второй - 'indexed'
        assert status_calls[0] == "indexing"
        assert status_calls[-1] == "indexed"

        # Проверяем сохранение дерева
        assert mock_repo.save_full_document_tree.called

        # Проверяем upsert в Qdrant
        assert mock_qdrant.upsert.called


@pytest.mark.asyncio
async def test_taskiq_index_kb_document_failure_lifecycle(tmp_path: Path):
    """Проверка обработки сбоя в задаче Taskiq (indexing -> failed)."""
    non_existent_file = tmp_path / "missing_file.pdf"

    mock_session = AsyncMock()
    mock_repo = AsyncMock()

    with (
        patch("src.kb.tasks.async_session_maker") as mock_session_maker,
        patch("src.kb.tasks.KbRepository", return_value=mock_repo),
        patch("src.kb.tasks.get_qdrant_client", return_value=AsyncMock()),
    ):
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        with pytest.raises(FileNotFoundError):
            await index_kb_document(
                doc_id="DOC_TASKIQ_FAIL",
                file_path=str(non_existent_file),
                regime="MOS_PORTAL",
            )

        # Проверяем, что зафиксирован статус 'failed' с сообщением об ошибке
        failure_calls = [
            call
            for call in mock_repo.update_document_status.call_args_list
            if (
                call.kwargs.get("status") == "failed"
                or (len(call.args) > 1 and call.args[1] == "failed")
            )
        ]
        assert len(failure_calls) == 1
        error_msg = (
            failure_calls[0].kwargs.get("error_message")
            or failure_calls[0].args[2]
        )
        assert error_msg is not None
        assert (
            "не найден" in error_msg.lower()
            or "not found" in error_msg.lower()
        )
