"""Переранжирование и валидация релевантности найденных кандидатов (ADR 0001, ADR 0006)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from src.rag.schemas import ContextChunk


class LexicalDenseReranker:
    """Гибридный реранкер на основе dense-векторной близости (0.65) и лексического соответствия (0.35).

    Поддерживает приоритетное точное сопоставление по номерам статей 44-ФЗ / 223-ФЗ
    и шестнадцатеричным кодам системных ошибок (0x...).
    """

    HEX_ERROR_REGEX: ClassVar[re.Pattern] = re.compile(
        r"\b0x[0-9a-fA-F]{4,8}\b", re.IGNORECASE
    )
    LAW_ARTICLE_REGEX: ClassVar[re.Pattern] = re.compile(
        r"\bст(?:ать[яеий]|[\.]?)\s*(\d+(?:\.\d+)?)\b", re.IGNORECASE
    )
    LAW_REGIME_REGEX: ClassVar[re.Pattern] = re.compile(
        r"\b(?:44|223)\s*[-‑–—]?\s*фз\b", re.IGNORECASE
    )

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
    ) -> float:
        """Вычисляет бонус за точное совпадение шестнадцатеричных кодов ошибок и статей законов."""
        target_parts = [
            chunk.title or "",
            chunk.section_path or "",
            chunk.quote_text or "",
        ]
        target_text = " ".join(target_parts).lower()
        boost = 0.0

        # 1. Проверка совпадения шестнадцатеричных кодов ошибок (0x...)
        query_hex = self.extract_hex_errors(query)
        if query_hex:
            chunk_hex = self.extract_hex_errors(target_text)
            if query_hex.intersection(chunk_hex):
                boost += 0.40

        # 2. Проверка точного совпадения номеров статей (например, ст. 93, ст. 34)
        query_articles = self.extract_article_numbers(query)
        if query_articles:
            chunk_articles = self.extract_article_numbers(target_text)
            if query_articles.intersection(chunk_articles):
                boost += 0.30

        # 3. Проверка совпадения правового режима (44-ФЗ / 223-ФЗ)
        query_laws = self.extract_law_regimes(query)
        if query_laws:
            chunk_laws = self.extract_law_regimes(target_text)
            if query_laws.intersection(chunk_laws):
                boost += 0.10

        return boost

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """Переранжирует список чанков по гибридной формуле:

        S = 0.65 * S_dense + 0.35 * S_lexical + ExactMatchBoost.
        Возвращает отсортированный по убыванию релевантности список чанков.
        """
        if not chunks:
            return []

        scored_chunks: list[tuple[float, ContextChunk]] = []
        for chunk in chunks:
            dense_score = (
                chunk.relevance_score
                if chunk.relevance_score is not None
                else 0.0
            )
            lex_score = self.compute_lexical_score(query, chunk)
            exact_boost = self.compute_exact_match_boost(query, chunk)

            final_score = (
                (self.dense_weight * dense_score)
                + (self.lexical_weight * lex_score)
                + exact_boost
            )

            # Нормализация в диапазон [0.0, 1.0]
            normalized_score = min(1.0, round(final_score, 4))

            updated_chunk = chunk.model_copy(
                update={"relevance_score": normalized_score}
            )
            scored_chunks.append((final_score, updated_chunk))

        # Сортировка по невозрастанию итогового скора
        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored_chunks]


# Алиас для спецификаций
HybridReranker = LexicalDenseReranker
