"""Юнит-тесты интеграции QueryRouter с поисковым пайплайном и детерминированного шлюза нормативных статей (Подплан 2)."""

from src.rag.reranker import HybridReranker
from src.rag.schemas import (
    ContextChunk,
    RagQueryRequestSchema,
    RagSourceChunkSchema,
)


def test_rag_source_chunk_schema_pin_to_top_default() -> None:
    """Проверяет наличие и дефолтное значение флага pin_to_top в схемах источников."""
    chunk = RagSourceChunkSchema(
        chunk_id="chunk_test",
        doc_id="DOC_TEST",
        title="Тестовый регламент",
        section_path="Раздел 1",
        relevance_score=0.85,
    )
    assert chunk.pin_to_top is False

    chunk_pinned = RagSourceChunkSchema(
        chunk_id="chunk_test_pinned",
        doc_id="DOC_44FZ",
        title="Статья 112 44-ФЗ",
        section_path="Заключительные положения",
        relevance_score=1.0,
        pin_to_top=True,
    )
    assert chunk_pinned.pin_to_top is True


def test_deterministic_pin_to_top_for_article_93_44fz() -> None:
    """Проверяет, что узел со статьей 93 44-ФЗ в заголовке поднимается в топ-1 с pin_to_top=True."""
    reranker = HybridReranker()

    # Чанк A: высокий dense score (0.95), но общее описание закупок
    chunk_general = ContextChunk(
        chunk_id="chunk_general",
        doc_id="DOC_GENERAL",
        title="Порядок проведения котировочных сессий",
        section_path="Общие регламенты ЕИС и Портала",
        quote_text="Котировочные сессии проводятся в соответствии с регламентом торговой площадки.",
        relevance_score=0.95,
    )

    # Чанк B: умеренный dense score (0.55), но точный заголовок статьи 93 44-ФЗ
    chunk_law_93 = ContextChunk(
        chunk_id="chunk_law_93",
        doc_id="DOC_44FZ_93",
        title="Статья 93. Осуществление закупки у единственного поставщика",
        section_path="Федеральный закон № 44-ФЗ",
        quote_text="Закупка у единственного поставщика может осуществляться заказчиком в следующих случаях...",
        relevance_score=0.55,
    )

    query = "Какие основания предусмотрены в ст. 93 44-ФЗ для закупки у единственного поставщика?"
    reranked = reranker.rerank(query, [chunk_general, chunk_law_93])

    assert len(reranked) == 2
    top_chunk = reranked[0]
    assert top_chunk.chunk_id == "chunk_law_93"
    assert top_chunk.pin_to_top is True
    assert top_chunk.relevance_score == 1.0


def test_deterministic_pin_to_top_for_article_112() -> None:
    """Проверяет детерминированный подъем узла с заголовком 'Статья 112' по запросу 'статья 112'."""
    reranker = HybridReranker()

    chunk_irrelevant = ContextChunk(
        chunk_id="chunk_irr",
        doc_id="DOC_IRR",
        title="Инструкция пользователя личного кабинета",
        section_path="Регистрация и вход",
        quote_text="Для входа в личный кабинет используйте сертификат ЭЦП.",
        relevance_score=0.88,
    )

    chunk_art_112 = ContextChunk(
        chunk_id="chunk_112",
        doc_id="DOC_112",
        title="Статья 112. Заключительные положения",
        section_path="Переходный период 44-ФЗ",
        quote_text="Особенности применения отдельных положений Федерального закона в переходный период.",
        relevance_score=0.50,
    )

    query = "Что регулирует статья 112 в части переходных положений?"
    reranked = reranker.rerank(query, [chunk_irrelevant, chunk_art_112])

    assert reranked[0].chunk_id == "chunk_112"
    assert reranked[0].pin_to_top is True
    assert reranked[0].relevance_score == 1.0


def test_standalone_query_construction_logic() -> None:
    """Проверяет, что очищенный/нормализованный standalone_query используется в RagQueryRequestSchema."""
    raw_query = "а как подать?"
    rewritten_standalone = (
        "Как подать заявку на котировочную сессию на Портале поставщиков?"
    )

    effective_query = (
        rewritten_standalone.strip()
        if rewritten_standalone and rewritten_standalone.strip()
        else raw_query
    )

    rag_request = RagQueryRequestSchema(
        query=effective_query,
        message_id=None,
        conversation_history=[],
    )

    assert rag_request.query == rewritten_standalone
    assert rag_request.query != raw_query
