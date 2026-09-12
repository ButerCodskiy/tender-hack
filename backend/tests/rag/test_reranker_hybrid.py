"""Юнит-тесты гибридного реранкера (ADR-0001, ADR-0006: Weighted Dense + Lexical Keyword Match)."""

from src.rag.reranker import HybridReranker, LexicalDenseReranker
from src.rag.schemas import ContextChunk


def test_hybrid_reranker_weights_formula() -> None:
    """Проверяет расчет по формуле S = 0.65 * S_dense + 0.35 * S_lexical."""
    reranker = LexicalDenseReranker()  # По умолчанию: 0.65 / 0.35

    # Чанк 1: dense = 0.80, запрос из 2 слов, совпадает 1 слово -> lex = 0.50
    # Ожидаемый скор = 0.65 * 0.80 + 0.35 * 0.50 = 0.52 + 0.175 = 0.695
    chunk1 = ContextChunk(
        chunk_id="chunk_1",
        doc_id="DOC_1",
        title="Оферты и СТЕ",
        section_path="Раздел 1",
        quote_text="Правила создания и публикации оферты на Портале.",
        relevance_score=0.80,
    )

    query = "публикации спецификации"
    reranked = reranker.rerank(query, [chunk1])

    assert len(reranked) == 1
    assert reranked[0].relevance_score == 0.695


def test_exact_hex_error_code_boost() -> None:
    """Проверяет приоритетный подъем чанка с точным совпадением hex-кода системной ошибки (0x...)."""
    reranker = HybridReranker()

    # Чанк A: высокий dense скор (0.88), но общая статья про ЭЦП без кода ошибки
    chunk_generic = ContextChunk(
        chunk_id="chunk_generic",
        doc_id="DOC_ECP",
        title="Работа с электронной подписью",
        section_path="Регламент ЭЦП",
        quote_text="Общие сведения о сертификатах и настройке плагина КриптоПро.",
        relevance_score=0.88,
    )

    # Чанк B: умеренный dense скор (0.62), но содержит точный код ошибки 0x80090016
    chunk_error_fix = ContextChunk(
        chunk_id="chunk_error_fix",
        doc_id="DOC_ERRORS",
        title="Устранение ошибок КриптоПро",
        section_path="База знаний техподдержки",
        quote_text="При возникновении системной ошибки 0x80090016 проверьте пин-код токена Рутокен.",
        relevance_score=0.62,
    )

    query = "Не удается подписать оферту, ошибка 0x80090016 в плагине"
    reranked = reranker.rerank(query, [chunk_generic, chunk_error_fix])

    # Чанк с ошибкой 0x80090016 обязан быть на первом месте
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "chunk_error_fix"
    assert reranked[1].chunk_id == "chunk_generic"


def test_exact_law_article_boost() -> None:
    """Проверяет точное совпадение по номеру статьи закона (ст. 93 44-ФЗ)."""
    reranker = LexicalDenseReranker()

    # Чанк A: общий регламент закупок по 44-ФЗ без статьи 93
    chunk_law_general = ContextChunk(
        chunk_id="chunk_law_general",
        doc_id="DOC_44FZ",
        title="Осуществление закупок по 44-ФЗ",
        section_path="Общие положения",
        quote_text="Порядок проведения электронных процедур и аукционов.",
        relevance_score=0.82,
    )

    # Чанк B: статья 93 (закупка у единственного поставщика)
    chunk_article_93 = ContextChunk(
        chunk_id="chunk_article_93",
        doc_id="DOC_44FZ_ART93",
        title="Статья 93. Закупка у единственного поставщика",
        section_path="44-ФЗ > Глава 3",
        quote_text="Осуществление закупки у единственного поставщика (подрядчика, исполнителя).",
        relevance_score=0.68,
    )

    query = "Как оформляется контракт по ст. 93 44-ФЗ на Портале?"
    reranked = reranker.rerank(query, [chunk_law_general, chunk_article_93])

    # Чанк со статьей 93 обязан обойти общий регламент благодаря boost за ст. 93
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "chunk_article_93"
    assert reranked[1].chunk_id == "chunk_law_general"


def test_empty_chunks_and_boundary_scores() -> None:
    """Проверяет граничные случаи: пустой список чанков и нормализацию скора."""
    reranker = LexicalDenseReranker()
    assert reranker.rerank("запрос", []) == []

    # Проверка, что скор не превышает 1.0 даже при максимальном бусте
    chunk_max = ContextChunk(
        chunk_id="chunk_max",
        doc_id="DOC_MAX",
        title="Статья 34 44-ФЗ Ошибка 0x80070005",
        section_path="Раздел",
        quote_text="Полное совпадение ст. 34 44-ФЗ и ошибка 0x80070005",
        relevance_score=0.99,
    )
    result = reranker.rerank("ст. 34 44-ФЗ 0x80070005", [chunk_max])
    assert result[0].relevance_score <= 1.0
