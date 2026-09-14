"""Переранжирование и валидация релевантности найденных кандидатов (ADR 0001, ADR 0006, ADR_RERANKER)."""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from src.rag.schemas import ContextChunk

logger = logging.getLogger(__name__)

HEX_ERROR_REGEX: ClassVar[re.Pattern] = re.compile(
    r"\b0x[0-9a-fA-F]{4,8}\b", re.IGNORECASE
)
LAW_ARTICLE_REGEX: ClassVar[re.Pattern] = re.compile(
    r"\bст(?:ать[яеий]|[\.]?)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE
)
LAW_REGIME_REGEX: ClassVar[re.Pattern] = re.compile(
    r"\b(?:44|223)\s*[-‑–—]?\s*фз\b", re.IGNORECASE
)


def compute_weighted_rrf(
    dense_ranks: dict[str, int],
    lexical_ranks: dict[str, int],
    k: int = 60,
    w_dense: float = 0.65,
    w_lex: float = 0.35,
) -> dict[str, float]:
    """Вычисляет взвешенный Reciprocal Rank Fusion (Weighted RRF, ADR_RERANKER).

    Formula:
        Score_RRF(d) = w_dense / (k + r_dense(d)) + w_lex / (k + r_lex(d))
    """
    all_chunk_ids = set(dense_ranks.keys()).union(lexical_ranks.keys())
    scores: dict[str, float] = {}
    for cid in all_chunk_ids:
        score = 0.0
        if cid in dense_ranks:
            score += w_dense / (k + dense_ranks[cid])
        if cid in lexical_ranks:
            score += w_lex / (k + lexical_ranks[cid])
        scores[cid] = round(score, 6)
    return scores


def calculate_dynamic_threshold(
    query: str,
    floor: float = 0.28,
    ceil: float = 0.55,
    beta: float = 0.015,
    min_len: int = 3,
) -> tuple[float, bool]:
    """Вычисляет динамический порог Cross-Encoder на основе длины запроса (ADR_RERANKER).

    Formula:
        T(q) = clamp(floor + beta * max(0, len(q) - min_len), floor, ceil)
    При наличии hex-ошибки (0x...) или статьи закона возвращается (floor, True) для bypass.
    """
    clean_query = query.strip()
    words = re.findall(r"\b[a-zA-Zа-яА-Я0-9_-]+\b", clean_query)
    word_count = len(words)

    has_hex = bool(HEX_ERROR_REGEX.search(clean_query))
    has_law = bool(LAW_ARTICLE_REGEX.search(clean_query)) and bool(
        LAW_REGIME_REGEX.search(clean_query)
    )
    is_special_bypass = has_hex or has_law

    if is_special_bypass:
        return floor, True

    calculated = floor + beta * max(0, word_count - min_len)
    clamped_threshold = min(ceil, max(floor, calculated))
    return round(clamped_threshold, 4), False


def aggregate_parent_articles(
    chunks: list[ContextChunk],
    max_parents: int = 5,
) -> list[ContextChunk]:
    """Агрегирует и дедуплицирует дочерние чанки в родительские статьи (ADR_RERANKER).

    Formula:
        S_parent = S_max + 0.10 * ln(1 + sum(S_other))
    """
    if not chunks:
        return []

    grouped: dict[str, list[ContextChunk]] = {}
    for chunk in chunks:
        parent_key = (
            chunk.node_id
            or chunk.section_path
            or (
                f"{chunk.doc_id}_{chunk.title}"
                if chunk.doc_id
                else chunk.chunk_id
            )
        )
        grouped.setdefault(parent_key, []).append(chunk)

    parent_chunks: list[ContextChunk] = []

    for parent_key, group in grouped.items():
        group.sort(
            key=lambda c: (
                1 if c.pin_to_top else 0,
                c.relevance_score if c.relevance_score is not None else 0.0,
            ),
            reverse=True,
        )
        best_chunk = group[0]
        s_max = (
            best_chunk.relevance_score
            if best_chunk.relevance_score is not None
            else 0.0
        )
        s_other_sum = sum(
            (c.relevance_score if c.relevance_score is not None else 0.0)
            for c in group[1:]
        )
        has_pin = any(c.pin_to_top for c in group)

        parent_score = (
            1.0
            if has_pin
            else min(1.0, round(s_max + 0.10 * math.log(1.0 + s_other_sum), 4))
        )

        aggregated = best_chunk.model_copy(
            update={
                "node_id": best_chunk.node_id or parent_key,
                "relevance_score": parent_score,
                "pin_to_top": has_pin,
            }
        )
        parent_chunks.append(aggregated)

    parent_chunks.sort(
        key=lambda c: (
            1 if c.pin_to_top else 0,
            c.relevance_score if c.relevance_score is not None else 0.0,
        ),
        reverse=True,
    )
    return parent_chunks[:max_parents]


def reorder_lost_in_middle[T](items: list[T]) -> list[T]:
    """Переупорядочивает статьи по U-образной схеме [1, 3, 5, 4, 2] (ADR_RERANKER).

    Сильнейшие статьи помещаются на границах контекста, где внимание LLM максимально.
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

    tail.reverse()
    return head + tail


class LexicalDenseReranker:
    """Гибридный реранкер на основе Weighted RRF (0.65 dense / 0.35 lexical) и родительской агрегации.

    Поддерживает приоритетное точное сопоставление по номерам статей 44-ФЗ / 223-ФЗ
    и шестнадцатеричным кодам системных ошибок (0x...).
    """

    HEX_ERROR_REGEX: ClassVar[re.Pattern] = HEX_ERROR_REGEX
    LAW_ARTICLE_REGEX: ClassVar[re.Pattern] = LAW_ARTICLE_REGEX
    LAW_REGIME_REGEX: ClassVar[re.Pattern] = LAW_REGIME_REGEX

    def __init__(
        self,
        dense_weight: float = 0.65,
        lexical_weight: float = 0.35,
    ) -> None:
        """Инициализирует реранкер с весовыми коэффициентами dense (0.65) и lexical (0.35)."""
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Извлекает нормализованные токены запроса или документа (слова длиной от 2 символов)."""
        tokens = re.findall(r"\b[a-zA-Zа-яА-Я0-9_]{2,}\b", text.lower())
        return set(tokens)

    def extract_hex_errors(self, text: str) -> set[str]:
        """Извлекает коды ошибок в формате 0x..."""
        return {match.lower() for match in self.HEX_ERROR_REGEX.findall(text)}

    def extract_article_numbers(self, text: str) -> set[str]:
        """Извлекает номера статей закона (например, ст. 93 -> '93')."""
        return set(self.LAW_ARTICLE_REGEX.findall(text))

    def extract_law_regimes(self, text: str) -> set[str]:
        """Извлекает упоминания законов (44-фз, 223-фз)."""
        return {
            re.sub(r"[\s‑–—]", "-", match.lower())
            for match in self.LAW_REGIME_REGEX.findall(text)
        }

    def compute_lexical_score(self, query: str, chunk: ContextChunk) -> float:
        """Вычисляет долю покрытия терминов запроса в тексте, заголовке и пути секции чанка."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return 0.0

        target_parts = [
            chunk.title or "",
            chunk.section_path or "",
            chunk.quote_text or "",
        ]
        target_text = " ".join(target_parts).lower()
        chunk_tokens = self._tokenize(target_text)

        matched_tokens = query_tokens.intersection(chunk_tokens)
        return len(matched_tokens) / len(query_tokens)

    def compute_exact_match_boost(
        self, query: str, chunk: ContextChunk
    ) -> tuple[float, bool]:
        """Вычисляет бонус и флаг pin_to_top за точное совпадение шестнадцатеричных кодов ошибок и статей законов."""
        target_parts = [
            chunk.title or "",
            chunk.section_path or "",
            chunk.quote_text or "",
        ]
        target_text = " ".join(target_parts).lower()
        title_or_sec = (
            f"{chunk.title or ''} {chunk.section_path or ''}".lower()
        )
        boost = 0.0
        is_pinned = False

        # 1. Проверка совпадения шестнадцатеричных кодов ошибок (0x...)
        query_hex = self.extract_hex_errors(query)
        if query_hex:
            chunk_hex = self.extract_hex_errors(target_text)
            if query_hex.intersection(chunk_hex):
                boost += 0.40

        # 2. Проверка точного совпадения номеров статей (например, ст. 93, ст. 34, статья 112)
        query_articles = self.extract_article_numbers(query)
        if query_articles:
            chunk_articles = self.extract_article_numbers(target_text)
            if query_articles.intersection(chunk_articles):
                boost += 0.30
                title_articles = self.extract_article_numbers(title_or_sec)
                if query_articles.intersection(title_articles):
                    is_pinned = True

        # 3. Проверка совпадения правового режима (44-ФЗ / 223-ФЗ)
        query_laws = self.extract_law_regimes(query)
        if query_laws:
            chunk_laws = self.extract_law_regimes(target_text)
            if query_laws.intersection(chunk_laws):
                boost += 0.10
                if query_articles and is_pinned:
                    boost += 0.10

        return boost, is_pinned

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
        max_parents: int = 5,
    ) -> list[ContextChunk]:
        """Переранжирует список чанков по Weighted RRF с дедупликацией и Lost-in-the-Middle."""
        if not chunks:
            return []

        # 1. Извлечение dense и lexical скоров
        scored_pairs: list[tuple[ContextChunk, float, float]] = []
        for chunk in chunks:
            dense_score = (
                chunk.relevance_score
                if chunk.relevance_score is not None
                else 0.0
            )
            lex_score = self.compute_lexical_score(query, chunk)
            scored_pairs.append((chunk, dense_score, lex_score))

        # 2. Ранжирование по плотному и лексическому каналам
        scored_pairs.sort(key=lambda item: item[1], reverse=True)
        dense_ranks = {
            item[0].chunk_id: idx + 1 for idx, item in enumerate(scored_pairs)
        }

        scored_pairs.sort(key=lambda item: item[2], reverse=True)
        lexical_ranks = {
            item[0].chunk_id: idx + 1 for idx, item in enumerate(scored_pairs)
        }

        # 3. Вычисление Weighted RRF
        rrf_scores = compute_weighted_rrf(
            dense_ranks=dense_ranks,
            lexical_ranks=lexical_ranks,
            k=60,
            w_dense=self.dense_weight,
            w_lex=self.lexical_weight,
        )

        # 4. Применение точных бустов
        candidate_chunks: list[ContextChunk] = []
        for chunk in chunks:
            exact_boost, is_pinned = self.compute_exact_match_boost(
                query, chunk
            )
            raw_score = rrf_scores.get(chunk.chunk_id, 0.0) + exact_boost
            normalized_score = (
                1.0 if is_pinned else min(1.0, round(raw_score, 4))
            )
            updated = chunk.model_copy(
                update={
                    "relevance_score": normalized_score,
                    "pin_to_top": is_pinned,
                }
            )
            candidate_chunks.append(updated)

        candidate_chunks.sort(
            key=lambda item: (
                1 if item.pin_to_top else 0,
                item.relevance_score
                if item.relevance_score is not None
                else 0.0,
            ),
            reverse=True,
        )

        # 5. Агрегация в родительские статьи и Lost-in-the-Middle
        parents = aggregate_parent_articles(
            candidate_chunks, max_parents=max_parents
        )
        return reorder_lost_in_middle(parents)


# Алиас для спецификаций
HybridReranker = LexicalDenseReranker


class TransformerCrossEncoderReranker(LexicalDenseReranker):
    """Нейросетевой Cross-Encoder реранкер на базе библиотеки transformers.

    Использует архитектуру Sequence Classification (например, BAAI/bge-reranker-base или
    bge-reranker-v2-m3) для попарной оценки (запрос, фрагмент) с динамическим порогом.
    При недоступности модели плавно переходит в режим Weighted RRF.
    """

    def __init__(
        self,
        model_name_or_path: str = "BAAI/bge-reranker-base",
        device: str = "cpu",
        dense_weight: float = 0.65,
        lexical_weight: float = 0.35,
    ) -> None:
        """Инициализирует трансформерный реранкер с опцией лексического фолбэка."""
        super().__init__(
            dense_weight=dense_weight, lexical_weight=lexical_weight
        )
        self.model_name_or_path = model_name_or_path
        self.device = device
        self._model = None
        self._tokenizer = None

    def _lazy_init(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name_or_path, local_files_only=True
                )
                self._model = (
                    AutoModelForSequenceClassification.from_pretrained(
                        self.model_name_or_path, local_files_only=True
                    ).to(self.device)
                )
            except Exception:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_name_or_path
                )
                self._model = (
                    AutoModelForSequenceClassification.from_pretrained(
                        self.model_name_or_path
                    ).to(self.device)
                )
            self._model.eval()
            logger.info(
                "TransformerCrossEncoderReranker loaded successfully with %s on %s",
                self.model_name_or_path,
                self.device,
            )
        except Exception as exc:
            logger.debug(
                "TransformerCrossEncoderReranker not active (%s), using LexicalDense RRF fallback",
                exc,
            )
            self._model = None
            self._tokenizer = None

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
        max_parents: int = 5,
    ) -> list[ContextChunk]:
        """Выполняет переранжирование через Cross-Encoder с динамическим порогом (ADR_RERANKER)."""
        self._lazy_init()
        if self._model is None or self._tokenizer is None or not chunks:
            return super().rerank(query, chunks, max_parents=max_parents)

        import torch

        # 1. Отбор Top-15 кандидатов через первичный Weighted RRF
        if len(chunks) > 15:
            pre_ranked = super().rerank(query, chunks, max_parents=len(chunks))
            candidates = pre_ranked[:15]
        else:
            candidates = chunks

        # 2. Расчет динамического порога отсечения
        threshold, is_bypass = calculate_dynamic_threshold(query)

        # 3. Попарная оценка (query, text) в Cross-Encoder
        pairs = []
        for chunk in candidates:
            text = f"{chunk.title or ''} {chunk.quote_text or ''}".strip()
            pairs.append([query, text])

        try:
            with torch.no_grad():
                inputs = self._tokenizer(
                    pairs,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)
                logits = (
                    self._model(**inputs, return_dict=True)
                    .logits.view(-1)
                    .float()
                )
                raw_logits = logits.cpu().tolist()
                if isinstance(raw_logits, float):
                    raw_logits = [raw_logits]
        except Exception as exc:
            logger.warning(
                "Ошибка инференса Cross-Encoder (%s), фолбэк на RRF", exc
            )
            return super().rerank(query, chunks, max_parents=max_parents)

        # 4. Нормализация и фильтрация по динамическому порогу
        # Min-Max калибровка логитов батча для инвариантности к шкале языковых моделей
        min_logit = min(raw_logits)
        max_logit = max(raw_logits)
        range_logit = max_logit - min_logit

        surviving_chunks: list[ContextChunk] = []
        for chunk, logit in zip(candidates, raw_logits, strict=False):
            if range_logit > 1e-5:
                norm_neural = (float(logit) - min_logit) / range_logit
            else:
                norm_neural = float(
                    torch.sigmoid(torch.tensor(float(logit) + 8.0)).item()
                )

            lex_score = self.compute_lexical_score(query, chunk)
            exact_boost, is_pinned = self.compute_exact_match_boost(
                query, chunk
            )
            final_score = (
                (0.65 * norm_neural) + (0.35 * lex_score) + exact_boost
            )
            normalized_score = (
                1.0 if is_pinned else min(1.0, round(final_score, 4))
            )

            # Проверка порога
            if is_bypass or is_pinned or normalized_score >= threshold:
                updated = chunk.model_copy(
                    update={
                        "relevance_score": normalized_score,
                        "pin_to_top": is_pinned,
                    }
                )
                surviving_chunks.append(updated)

        if not surviving_chunks:
            logger.info(
                "Cross-Encoder: все кандидаты ниже динамического порога %.4f для запроса '%s'",
                threshold,
                query,
            )
            return []

        surviving_chunks.sort(
            key=lambda item: (
                1 if item.pin_to_top else 0,
                item.relevance_score
                if item.relevance_score is not None
                else 0.0,
            ),
            reverse=True,
        )

        # 5. Агрегация в родительские статьи и Lost-in-the-Middle
        parents = aggregate_parent_articles(
            surviving_chunks, max_parents=max_parents
        )
        return reorder_lost_in_middle(parents)


# Алиасы для спецификаций
TransformerReranker = TransformerCrossEncoderReranker
NeuralReranker = TransformerCrossEncoderReranker
