"""Изолированная математическая модель нового реранкера (Sandbox / Repro Case).

ADR: docs/adr/ADR_RERANKER.md
Компоненты:
1. Weighted Reciprocal Rank Fusion (Weighted RRF, k=60)
2. Динамический расчет порога Cross-Encoder с защитой от коротких запросов (Floor + Regex Bypass)
3. Агрегация и дедупликация дочерних чанков в родительские статьи:
   S_parent = S_max + 0.10 * ln(1 + sum(S_other))
4. Переупорядочивание для нейтрализации эффекта "Lost in the Middle" ([1, 3, 5, 4, 2])
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


# ==============================================================================
# 1. Структуры данных
# ==============================================================================


@dataclass
class ChildChunk:
    """Дочерний поисковый фрагмент."""

    chunk_id: str
    node_id: str
    doc_id: str
    title: str
    text: str
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rrf_score: float = 0.0
    cross_encoder_score: float = 0.0


@dataclass
class ParentArticle:
    """Целостная родительская статья регламента."""

    node_id: str
    doc_id: str
    title: str
    content_markdown: str
    score: float = 0.0
    matched_child_chunks: list[ChildChunk] = field(default_factory=list)


# ==============================================================================
# 2. Математические функции
# ==============================================================================

HEX_ERROR_REGEX = re.compile(r"\b0x[0-9a-fA-F]{4,8}\b", re.IGNORECASE)
LAW_ARTICLE_REGEX = re.compile(
    r"\bст(?:ать[яеий]|[\.]?)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE
)
LAW_REGIME_REGEX = re.compile(r"\b(?:44|223)\s*[-‑–—]?\s*фз\b", re.IGNORECASE)


def compute_weighted_rrf(
    dense_ranks: dict[str, int],
    lexical_ranks: dict[str, int],
    k: int = 60,
    w_dense: float = 0.65,
    w_lex: float = 0.35,
) -> dict[str, float]:
    """Вычисляет взвешенный Reciprocal Rank Fusion (Weighted RRF).

    Formula:
        Score_RRF(d) = w_dense / (k + r_dense(d)) + w_lex / (k + r_lex(d))
    """
    all_doc_ids = set(dense_ranks.keys()).union(lexical_ranks.keys())
    scores: dict[str, float] = {}

    for doc_id in all_doc_ids:
        score = 0.0
        if doc_id in dense_ranks:
            score += w_dense / (k + dense_ranks[doc_id])
        if doc_id in lexical_ranks:
            score += w_lex / (k + lexical_ranks[doc_id])
        scores[doc_id] = round(score, 6)

    return scores


def calculate_dynamic_threshold(
    query: str,
    floor: float = 0.28,
    ceil: float = 0.55,
    beta: float = 0.015,
    min_len: int = 3,
) -> tuple[float, bool]:
    """Вычисляет динамический порог Cross-Encoder на основе длины запроса.

    Для коротких запросов возвращается floor-порог.
    При наличии hex-кода системной ошибки (0x...) или статьи закона (ст. 93 44-ФЗ)
    активируется bypass-флаг, гарантирующий пропуск совпадения без ложного отсечения.
    """
    clean_query = query.strip()
    words = re.findall(r"\b[a-zA-Zа-яА-Я0-9_-]+\b", clean_query)
    word_count = len(words)

    # Проверка спец-паттернов (Bypass / Boost)
    has_hex = bool(HEX_ERROR_REGEX.search(clean_query))
    has_law = bool(LAW_ARTICLE_REGEX.search(clean_query)) and bool(
        LAW_REGIME_REGEX.search(clean_query)
    )
    is_special_bypass = has_hex or has_law

    if is_special_bypass:
        # Для кодов ошибок и статей закона порог фиксируется на минимальном базовом значении
        return floor, True

    # Динамический порог с насыщением: floor + beta * max(0, len - min_len)
    calculated = floor + beta * max(0, word_count - min_len)
    clamped_threshold = min(ceil, max(floor, calculated))
    return round(clamped_threshold, 4), False


def aggregate_parent_articles(
    scored_child_chunks: list[ChildChunk],
    parent_storage_mock: dict[str, dict[str, Any]],
    max_parents: int = 5,
) -> list[ParentArticle]:
    """Агрегирует дочерние чанки в уникальные родительские статьи.

    Формула скора родительской статьи:
        S_parent = S_max + 0.10 * ln(1 + sum(S_other))
    """
    if not scored_child_chunks:
        return []

    # Группировка дочерних чанков по node_id родительской статьи
    grouped: dict[str, list[ChildChunk]] = {}
    for chunk in scored_child_chunks:
        grouped.setdefault(chunk.node_id, []).append(chunk)

    parent_articles: list[ParentArticle] = []

    for node_id, chunks in grouped.items():
        # Сортируем дочерние чанки по убыванию скора кросс-энкодера
        chunks.sort(key=lambda c: c.cross_encoder_score, reverse=True)

        s_max = chunks[0].cross_encoder_score
        s_other_sum = sum(c.cross_encoder_score for c in chunks[1:])

        # Расчет итогового скора родительской статьи
        parent_score = s_max + 0.10 * math.log(1.0 + s_other_sum)
        normalized_score = round(min(1.0, parent_score), 4)

        metadata = parent_storage_mock.get(
            node_id,
            {
                "doc_id": chunks[0].doc_id,
                "title": chunks[0].title,
                "content_markdown": chunks[0].text,
            },
        )

        parent_articles.append(
            ParentArticle(
                node_id=node_id,
                doc_id=metadata.get("doc_id", chunks[0].doc_id),
                title=metadata.get("title", chunks[0].title),
                content_markdown=metadata.get("content_markdown", chunks[0].text),
                score=normalized_score,
                matched_child_chunks=chunks,
            )
        )

    # Сортировка родительских статей по убыванию итогового скора
    parent_articles.sort(key=lambda p: p.score, reverse=True)

    # Ограничение n-m уникальными статьями (до 4-5)
    return parent_articles[:max_parents]


def reorder_lost_in_middle(items: list[T]) -> list[T]:
    """Переупорядочивает список элементов для нейтрализации эффекта 'Lost in the Middle'.

    Порядок размещения элементов [0, 1, 2, 3, 4] по убыванию релевантности:
    Результат: [0, 2, 4, 3, 1]
    - Элемент 0 (самый релевантный) идет в самое начало.
    - Элемент 1 (второй по релевантности) идет в самый конец.
    - Менее релевантные элементы помещаются в середину.
    """
    if len(items) <= 2:
        return list(items)

    head: list[T] = []
    tail: list[T] = []

    for i, item in enumerate(items):
        if i % 2 == 0:
            head.append(item)
        else:
            tail.append(item)

    # tail разворачиваем, чтобы второй лучший элемент встал в самый конец
    tail.reverse()
    return head + tail


# ==============================================================================
# 3. Верификационные сценарии (Self-Test / Repro Case)
# ==============================================================================


def run_verification_suite() -> None:
    print("=" * 80)
    print("ВЕРИФИКАЦИЯ МАТЕМАТИЧЕСКОЙ МОДЕЛИ РЕРАНКЕРА (scratch/reranker_math.py)")
    print("=" * 80)

    # Тест 1: Weighted RRF
    print("\n[Тест 1] Weighted RRF vs Линейная сумма")
    dense_ranks = {"chunk_A": 1, "chunk_B": 2, "chunk_C": 15, "chunk_D": 30}
    lexical_ranks = {"chunk_C": 1, "chunk_A": 20, "chunk_B": 5, "chunk_D": 2}

    rrf_scores = compute_weighted_rrf(dense_ranks, lexical_ranks, k=60)
    sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    print("  Dense ranks:  ", dense_ranks)
    print("  Lexical ranks:", lexical_ranks)
    print("  RRF результат:", sorted_rrf)
    assert sorted_rrf[0][0] in ("chunk_A", "chunk_B"), (
        "Top-1 должен балансировать оба канала"
    )
    print("  --> УСПЕШНО: RRF корректно нормализует ранги независимых распределений.")

    # Тест 2: Динамический порог Cross-Encoder
    print("\n[Тест 2] Динамический порог и Bypass")
    short_q = "штрафы"
    error_q = "Ошибка 0x80070005 при подписании контракта"
    law_q = "каков порядок по ст. 93 44-фз для единственного поставщика"
    long_q = "подробный регламент обжалования протокола разногласий заказчика поставщиком при закупках малого объема в электронном магазине"

    t_short, b_short = calculate_dynamic_threshold(short_q)
    t_error, b_error = calculate_dynamic_threshold(error_q)
    t_law, b_law = calculate_dynamic_threshold(law_q)
    t_long, b_long = calculate_dynamic_threshold(long_q)

    print(f"  Короткий запрос ('{short_q}'): порог = {t_short}, bypass = {b_short}")
    print(f"  Код ошибки ('{error_q[:30]}...'): порог = {t_error}, bypass = {b_error}")
    print(f"  Статья закона ('{law_q[:30]}...'): порог = {t_law}, bypass = {b_law}")
    print(f"  Длинный запрос ('{long_q[:30]}...'): порог = {t_long}, bypass = {b_long}")

    assert t_short == 0.28, "Короткий запрос должен использовать floor 0.28"
    assert b_error is True, "Hex-ошибка обязана активировать bypass"
    assert b_law is True, "Статья 44-ФЗ обязана активировать bypass"
    assert t_long > 0.40, "Длинный запрос должен повышать порог фильтрации шума"
    print("  --> УСПЕШНО: Динамический расчет порога ведет себя строго по ТЗ.")

    # Тест 3: Агрегация n мелких чанков в n-m родительских статей
    print("\n[Тест 3] Агрегация чанков в родительские статьи и дедупликация")
    sample_chunks = [
        ChildChunk(
            chunk_id="c1",
            node_id="ART_93",
            doc_id="44FZ",
            title="Статья 93. Единственный поставщик",
            text="ч. 1 п. 4",
            cross_encoder_score=0.92,
        ),
        ChildChunk(
            chunk_id="c2",
            node_id="ART_93",
            doc_id="44FZ",
            title="Статья 93. Единственный поставщик",
            text="ч. 1 п. 5",
            cross_encoder_score=0.85,
        ),
        ChildChunk(
            chunk_id="c3",
            node_id="ART_93",
            doc_id="44FZ",
            title="Статья 93. Единственный поставщик",
            text="ч. 2 извещение",
            cross_encoder_score=0.60,
        ),
        ChildChunk(
            chunk_id="c4",
            node_id="ART_34",
            doc_id="44FZ",
            title="Статья 34. Контракт",
            text="ответственность",
            cross_encoder_score=0.78,
        ),
        ChildChunk(
            chunk_id="c5",
            node_id="ART_34",
            doc_id="44FZ",
            title="Статья 34. Контракт",
            text="штрафы и пени",
            cross_encoder_score=0.74,
        ),
        ChildChunk(
            chunk_id="c6",
            node_id="SEC_4",
            doc_id="PORTAL_REG",
            title="Раздел 4. Протоколы разногласий",
            text="срок 3 дня",
            cross_encoder_score=0.65,
        ),
    ]

    mock_db = {
        "ART_93": {
            "doc_id": "44FZ",
            "title": "Статья 93. Закупка у единственного поставщика (подрядчика, исполнителя)",
            "content_markdown": "# Полный текст статьи 93...",
        },
        "ART_34": {
            "doc_id": "44FZ",
            "title": "Статья 34. Контракт",
            "content_markdown": "# Полный текст статьи 34...",
        },
        "SEC_4": {
            "doc_id": "PORTAL_REG",
            "title": "Регламент Портала: Раздел 4",
            "content_markdown": "# Полный текст раздела 4...",
        },
    }

    parents = aggregate_parent_articles(sample_chunks, mock_db, max_parents=5)
    print(f"  Входных дочерних чанков: {len(sample_chunks)}")
    print(f"  Итоговых уникальных родительских статей: {len(parents)}")
    for p in parents:
        print(
            f"    - {p.node_id} (score={p.score}): совпало {len(p.matched_child_chunks)} чанков"
        )

    assert len(parents) == 3, (
        "6 дочерних чанков должны схлопнуться строго в 3 родительские статьи"
    )
    assert parents[0].node_id == "ART_93", (
        "Статья 93 с несколькими сильными чанками должна быть топ-1"
    )
    assert parents[0].score > 0.92, (
        "Бонус за сумму вторичных чанков должен увеличить скор родителя"
    )
    print(
        "  --> УСПЕШНО: Дедупликация и кумулятивный скор родителя работают корректно."
    )

    # Тест 4: Lost in the Middle
    print("\n[Тест 4] Переупорядочивание Lost in the Middle")
    ranked_parents = [f"Article_{i}" for i in range(1, 6)]  # [1, 2, 3, 4, 5]
    reordered = reorder_lost_in_middle(ranked_parents)
    print(f"  Исходный ранжированный список: {ranked_parents}")
    print(f"  Размещение для промпта LLM:   {reordered}")

    assert reordered == [
        "Article_1",
        "Article_3",
        "Article_5",
        "Article_4",
        "Article_2",
    ], "Порядок должен быть строго [1, 3, 5, 4, 2]"
    print(
        "  --> УСПЕШНО: Лучшие статьи гарантированно размещены в начале и в конце окна внимания."
    )

    print("\n" + "=" * 80)
    print("ВСЕ 4 ВЕРИФИКАЦИОННЫХ ТЕСТА ПРОЙДЕНЫ УСПЕШНО.")
    print("=" * 80)


if __name__ == "__main__":
    run_verification_suite()
