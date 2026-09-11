"""
Тесты Pydantic v2 схем модуля kb (test_kb_schemas.py).
"""

from datetime import date

from src.kb.schemas import (
    CompletenessReportSchema,
    ParsedChunkSchema,
    ParsedDocumentSchema,
    ParsedNodeSchema,
)


def test_parsed_document_schema():
    doc = ParsedDocumentSchema(
        doc_id="DOC_TEST_01",
        title="Тестовый регламент",
        regime="MOS_PORTAL",
        edition_date=date(2026, 1, 15),
        status="uploaded",
        is_scanned=False,
    )
    assert doc.doc_id == "DOC_TEST_01"
    assert doc.status == "uploaded"
    assert not doc.is_scanned

    dump = doc.model_dump(mode="json")
    assert dump["regime"] == "MOS_PORTAL"
    assert dump["edition_date"] == "2026-01-15"


def test_parsed_node_schema():
    node = ParsedNodeSchema(
        node_id="DOC_01_n001",
        doc_id="DOC_01",
        level="article",
        section_path="Регламент > Статья 1",
        article_no="1",
        part_no="2",
        title="Статья 1. Общие положения",
        full_content="Текст статьи 1...",
        token_count=45,
    )
    assert node.node_id == "DOC_01_n001"
    assert node.level == "article"
    assert node.token_count == 45


def test_parsed_chunk_schema_ddl_consistency():
    """
    Проверяем, что token_count исключен из персистентного model_dump,
    чтобы не конфликтовать со схемой DDL таблицы kb_chunks.
    """
    chunk = ParsedChunkSchema(
        chunk_id="DOC_01_n001_c01",
        node_id="DOC_01_n001",
        text="Текст фрагмента статьи",
        context_prefix="Префикс контекста",
        hyp_questions=["Вопрос 1?", "Вопрос 2?"],
        has_table=True,
        embedding_model_version="bge-m3",
        token_count=120,
    )
    dump = chunk.model_dump(mode="json")
    # Проверяем отсутствие token_count в словаре для вставки в БД
    assert "token_count" not in dump, (
        "token_count должен быть исключен из DDL kb_chunks!"
    )
    assert dump["chunk_id"] == "DOC_01_n001_c01"
    assert dump["has_table"] is True
    assert dump["embedding_model_version"] == "bge-m3"


def test_completeness_report_schema():
    rep = CompletenessReportSchema(
        doc_id="DOC_01",
        pymupdf_char_count=5000,
        docling_char_count=4900,
        discrepancy_ratio=0.02,
        is_scanned=False,
        needs_manual_review=False,
    )
    assert rep.discrepancy_ratio == 0.02
    assert not rep.needs_manual_review
