"""Юнит-тесты гибридного реранкера (ADR-0001, ADR-0006, ADR_RERANKER: Weighted RRF + Dynamic Threshold + Parent Aggregation)."""

from src.rag.reranker import (
    HybridReranker,
    LexicalDenseReranker,
    aggregate_parent_articles,
    calculate_dynamic_threshold,
    compute_weighted_rrf,
    reorder_lost_in_middle,
)
from src.rag.schemas import ContextChunk


def test_hybrid_reranker_weights_formula() -> None:
    """Проверяет расчет по формуле Weighted RRF (k=60, w_dense=0.65, w_lex=0.35)."""
    reranker = LexicalDenseReranker()  # По умолчанию: 0.65 / 0.35

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
    # Для единственного чанка: ранг dense=1, ранг lex=1
    # Score = 0.65 / (60 + 1) + 0.35 / (60 + 1) = 1.0 / 61 = 0.01639 -> 0.0164
    assert reranked[0].relevance_score == 0.0164


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


def test_dynamic_threshold_calculation() -> None:
    """Проверяет динамический порог отсечения Cross-Encoder и bypass-правила (ADR_RERANKER)."""
    # 1. Короткий запрос -> минимальный floor порог
    t_short, bypass_short = calculate_dynamic_threshold("штрафы")
    assert t_short == 0.28
    assert bypass_short is False

    # 2. Системный hex-код ошибки -> bypass True, floor 0.28
    t_hex, bypass_hex = calculate_dynamic_threshold(
        "Ошибка 0x80070005 в плагине"
    )
    assert t_hex == 0.28
    assert bypass_hex is True

    # 3. Статья закона 44-ФЗ -> bypass True, floor 0.28
    t_law, bypass_law = calculate_dynamic_threshold("порядок по ст. 93 44-фз")
    assert t_law == 0.28
    assert bypass_law is True

    # 4. Длинный сложный запрос -> порог возрастает для отсечения шума
    t_long, bypass_long = calculate_dynamic_threshold(
        "подробный регламент обжалования протокола разногласий заказчика поставщиком при закупках малого объема"
    )
    assert t_long >= 0.40
    assert bypass_long is False


def test_parent_aggregation_and_deduplication() -> None:
    """Проверяет дедупликацию дочерних чанков в родительские статьи и расчет S_parent."""
    # 3 дочерних чанка одной статьи (node_id = 'NODE_ART93')
    c1 = ContextChunk(
        chunk_id="c1",
        node_id="NODE_ART93",
        doc_id="44FZ",
        title="Статья 93",
        section_path="44-ФЗ > Ст 93",
        quote_text="Текст 1",
        relevance_score=0.85,
    )
    c2 = ContextChunk(
        chunk_id="c2",
        node_id="NODE_ART93",
        doc_id="44FZ",
        title="Статья 93",
        section_path="44-ФЗ > Ст 93",
        quote_text="Текст 2",
        relevance_score=0.70,
    )
    c3 = ContextChunk(
        chunk_id="c3",
        node_id="NODE_ART93",
        doc_id="44FZ",
        title="Статья 93",
        section_path="44-ФЗ > Ст 93",
        quote_text="Текст 3",
        relevance_score=0.50,
    )
    # 1 дочерний чанк другой статьи (node_id = 'NODE_ART34')
    c4 = ContextChunk(
        chunk_id="c4",
        node_id="NODE_ART34",
        doc_id="44FZ",
        title="Статья 34",
        section_path="44-ФЗ > Ст 34",
        quote_text="Текст 4",
        relevance_score=0.80,
    )

    parents = aggregate_parent_articles([c1, c2, c3, c4], max_parents=5)

    assert len(parents) == 2
    # Статья 93 должна быть топ-1 благодаря сумме скоров вторичных чанков
    assert parents[0].node_id == "NODE_ART93"
    assert parents[0].relevance_score > 0.85
    assert parents[1].node_id == "NODE_ART34"


def test_reorder_lost_in_middle() -> None:
    """Проверяет U-образную раскладку статей [1, 3, 5, 4, 2] для защиты от Lost-in-the-Middle."""
    articles = [f"Art_{i}" for i in range(1, 6)]
    reordered = reorder_lost_in_middle(articles)
    assert reordered == ["Art_1", "Art_3", "Art_5", "Art_4", "Art_2"]


def test_compute_weighted_rrf_formula() -> None:
    """Проверяет расчет по формуле compute_weighted_rrf с весами 0.65 и 0.35."""
    dense_ranks = {"doc_a": 1, "doc_b": 2}
    lexical_ranks = {"doc_a": 2, "doc_b": 1}

    rrf = compute_weighted_rrf(
        dense_ranks=dense_ranks,
        lexical_ranks=lexical_ranks,
        k=60,
        w_dense=0.65,
        w_lex=0.35,
    )
    # doc_a: 0.65/(60+1) + 0.35/(60+2) = 0.65/61 + 0.35/62 = 0.0106557 + 0.00564516 = 0.01630086
    # doc_b: 0.65/(60+2) + 0.35/(60+1) = 0.65/62 + 0.35/61 = 0.0104838 + 0.00573770 = 0.01622150
    assert rrf["doc_a"] > rrf["doc_b"]
    assert round(rrf["doc_a"], 5) == round(0.65 / 61 + 0.35 / 62, 5)
