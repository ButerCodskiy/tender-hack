"""Переранжирование и валидация релевантности найденных кандидатов (ADR 0001 / ADR 0005)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rag.schemas import ContextChunk


class LexicalDenseReranker:
    """Гибридный реранкер на основе dense-векторной близости и лексического покрытия ключевых терминов."""

    def __init__(
        self,
        dense_weight: float = 0.60,
        lexical_weight: float = 0.40,
    ) -> None:
        """Инициализирует реранкер с весовыми коэффициентами dense и lexical составляющих."""
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Извлекает нормализованные токены запроса или документа (слова длиной от 2 символов)."""
        tokens = re.findall(r"\b[a-zA-Zа-яА-Я0-9_]{2,}\b", text.lower())
        return set(tokens)

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

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """Переранжирует список чанков по комбинированной оценке S_final = w_d * S_dense + w_l * R_lex.

        Возвращает отсортированный по убыванию релевантности список чанков
        с обновленным полем relevance_score.
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
            final_score = (self.dense_weight * dense_score) + (
                self.lexical_weight * lex_score
            )

            updated_chunk = chunk.model_copy(
                update={"relevance_score": round(final_score, 4)}
            )
            scored_chunks.append((final_score, updated_chunk))

        # Сортировка по невозрастанию итогового скора
        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored_chunks]
