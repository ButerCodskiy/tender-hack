"""Переранжирование и валидация релевантности найденных кандидатов (ADR 0001, ADR 0006)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from src.rag.schemas import ContextChunk

logger = logging.getLogger(__name__)


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
                # Если номер статьи явно совпал в заголовке или секции, закрепляем статью в топ-1
                title_articles = self.extract_article_numbers(title_or_sec)
                if query_articles.intersection(title_articles):
                    is_pinned = True

        # 3. Проверка совпадения правового режима (44-ФЗ / 223-ФЗ)
        query_laws = self.extract_law_regimes(query)
        if query_laws:
            chunk_laws = self.extract_law_regimes(target_text)
            if query_laws.intersection(chunk_laws):
                boost += 0.10
                # Если в запросе режим 44-ФЗ/223-ФЗ и в заголовке прямо указана эта статья
                if query_articles and is_pinned:
                    boost += 0.10

        return boost, is_pinned

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """Переранжирует список чанков по гибридной формуле:

        S = 0.65 * S_dense + 0.35 * S_lexical + ExactMatchBoost.
        Закрепленные нормативные статьи (pin_to_top) всегда поднимаются в топ-1.
        Возвращает отсортированный по убыванию релевантности список чанков.
        """
        if not chunks:
            return []

        scored_chunks: list[tuple[float, bool, ContextChunk]] = []
        for chunk in chunks:
            dense_score = (
                chunk.relevance_score
                if chunk.relevance_score is not None
                else 0.0
            )
            lex_score = self.compute_lexical_score(query, chunk)
            exact_boost, is_pinned = self.compute_exact_match_boost(
                query, chunk
            )

            final_score = (
                (self.dense_weight * dense_score)
                + (self.lexical_weight * lex_score)
                + exact_boost
            )

            # Нормализация в диапазон [0.0, 1.0]
            normalized_score = (
                1.0 if is_pinned else min(1.0, round(final_score, 4))
            )

            updated_chunk = chunk.model_copy(
                update={
                    "relevance_score": normalized_score,
                    "pin_to_top": is_pinned,
                }
            )
            scored_chunks.append((final_score, is_pinned, updated_chunk))

        # Сортировка: сначала закрепленные статьи (pin_to_top=True), затем по убыванию итогового скора
        scored_chunks.sort(
            key=lambda item: (1 if item[1] else 0, item[0]), reverse=True
        )
        return [chunk for _, _, chunk in scored_chunks]


# Алиас для спецификаций
HybridReranker = LexicalDenseReranker


class TransformerCrossEncoderReranker(LexicalDenseReranker):
    """Нейросетевой Cross-Encoder реранкер на базе библиотеки transformers.

    Использует архитектуру Sequence Classification (например, BAAI/bge-reranker-base или
    bge-reranker-v2-m3) для попарной оценки (запрос, фрагмент).
    В случае недоступности весов модели или сетевых ограничений выполняет плавный
    фолбэк на гибридный LexicalDenseReranker с сохранением всех гарантий ADR-0001 / ADR-0006.
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
            # Если локальные веса отсутствуют или идет загрузка, плавно работаем в режиме гибридного лексико-плотного фолбэка
            logger.debug(
                "TransformerCrossEncoderReranker not active (%s), using LexicalDense fallback",
                exc,
            )
            self._model = None
            self._tokenizer = None

    def rerank(
        self,
        query: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """Выполняет переранжирование через transformer cross-encoder или гибридный фолбэк."""
        self._lazy_init()
        if self._model is None or self._tokenizer is None or not chunks:
            return super().rerank(query, chunks)

        import torch

        scored_chunks: list[tuple[float, bool, ContextChunk]] = []
        pairs = []
        for chunk in chunks:
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
                scores = (
                    self._model(**inputs, return_dict=True)
                    .logits.view(-1)
                    .float()
                )
                scores = torch.sigmoid(scores).cpu().tolist()
                if isinstance(scores, float):
                    scores = [scores]
        except Exception:
            return super().rerank(query, chunks)

        for chunk, neural_score in zip(chunks, scores, strict=False):
            exact_boost, is_pinned = self.compute_exact_match_boost(
                query, chunk
            )
            final_score = float(neural_score) + exact_boost
            normalized_score = (
                1.0 if is_pinned else min(1.0, round(final_score, 4))
            )
            updated = chunk.model_copy(
                update={
                    "relevance_score": normalized_score,
                    "pin_to_top": is_pinned,
                }
            )
            scored_chunks.append((final_score, is_pinned, updated))

        scored_chunks.sort(
            key=lambda item: (1 if item[1] else 0, item[0]), reverse=True
        )
        return [c for _, _, c in scored_chunks]


# Алиасы для спецификаций
TransformerReranker = TransformerCrossEncoderReranker
NeuralReranker = TransformerCrossEncoderReranker
