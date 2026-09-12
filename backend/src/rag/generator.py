"""Конвейер потоковой генерации ответа со сносками и верификацией фактов."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable
from uuid import UUID

import razdel

from src.core.llm_client import get_llm_stream_client
from src.rag.prompts import format_rag_prompt
from src.rag.schemas import (
    ContextChunk,
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagSentenceEventSchema,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class LlmStreamClientProtocol(Protocol):
    """Протокол взаимодействия генератора с клиентом потоковой генерации LLM."""

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        """Генерирует поток строковых токенов модели."""
        ...


class MockLlmStreamClient:
    """Тестовый клиент для локальной разработки, изоляции модулей и юнит-тестов."""

    def __init__(
        self,
        tokens: list[str] | None = None,
        default_text: str | None = None,
        delay: float = 0.0,
        fail_times: int = 0,
    ) -> None:
        """Инициализирует тестовый генеративный стрим-клиент."""
        self.tokens = tokens
        self.default_text = default_text
        self.delay = delay
        self.fail_times = fail_times
        self.call_count = 0

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        timeout: float = 30.0,
    ) -> AsyncIterator[str]:
        """Эмулирует потоковую отдачу токенов языковой модели."""
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise TimeoutError("LLM generation stream timeout (mock failure)")

        if self.tokens is not None:
            for token in self.tokens:
                if self.delay > 0:
                    await asyncio.sleep(self.delay)
                yield token
            return

        text = self.default_text or (
            "По вашему вопросу: в соответствии с регламентом Портала поставщиков Москвы, "
            "протокол разногласий формируется в личном кабинете поставщика.\n\n"
            "Подписание осуществляется с использованием усиленной квалифицированной "
            "электронной подписи (ЭЦП) в течение 3 рабочих дней [^1]."
        )
        words = text.split(" ")
        for i, word in enumerate(words):
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            yield word + (" " if i < len(words) - 1 else "")


class SentenceBuffer:
    """Буферизатор потока токенов с выделением законченных предложений и списков."""

    def __init__(self) -> None:
        """Инициализирует пустой буфер накопления текста."""
        self.buffer: str = ""

    def feed(self, token: str) -> list[str]:
        """Принимает очередной фрагмент текста от LLM и отдает готовые фразы.

        Сбрасывает буфер по двойному переносу строки (\n\n) для корректной
        буферизации списков и перечислений Markdown без зависания в ожидании точки.
        """
        self.buffer += token
        emitted: list[str] = []

        # 1. Принудительный сброс блоков списков и абзацев по \n\n
        while "\n\n" in self.buffer:
            head, self.buffer = self.buffer.split("\n\n", 1)
            if head.strip():
                for s in razdel.sentenize(head):
                    text = s.text.strip()
                    if text:
                        emitted.append(text)

        # 2. Нарезка оставшегося буфера на предложения через razdel
        sentences = list(razdel.sentenize(self.buffer))
        if len(sentences) > 1:
            for s in sentences[:-1]:
                text = s.text.strip()
                if text:
                    emitted.append(text)
            last_start = sentences[-1].start
            self.buffer = self.buffer[last_start:]

        return emitted

    def flush(self) -> list[str]:
        """Сбрасывает остаток буфера по завершении потока генерации."""
        emitted: list[str] = []
        if self.buffer.strip():
            for s in razdel.sentenize(self.buffer):
                text = s.text.strip()
                if text:
                    emitted.append(text)
        self.buffer = ""
        return emitted


class FactCheckingGuard:
    """Инлайн-валидатор фактологической корректности (числа, сроки, проценты, сноски)."""

    FOOTNOTE_REGEX = re.compile(
        r"(?:\[\^?(\d+)\]|\[источник\s*(\d+)\]|\(источник[и]?\s*(\d+)\))",
        re.IGNORECASE,
    )

    def extract_footnotes(self, text: str) -> list[int]:
        """Извлекает 1-based порядковые номера сносок ([^1], [1], [Источник 1], (источник 1))."""
        res: list[int] = []
        for match in self.FOOTNOTE_REGEX.findall(text):
            for group in match:
                if group:
                    res.append(int(group))
        return res

    def extract_numeric_facts(self, text: str) -> set[str]:
        """Извлекает нормализованные числовые значения, проценты, суммы и даты.

        Предварительно вырезает маркеры сносок, нумерованные списки, а также
        структурные обозначения (Способ 1, Шаг 2, Вариант 3), исключая ложные
        срабатывания на нумерацию шагов.
        """
        # 1. Исключаем сноски
        cleaned = self.FOOTNOTE_REGEX.sub("", text)
        # 2. Исключаем упоминания источников вида "(источники 6 и 7)", "источник 1"
        cleaned = re.sub(r"(?i)\(источник[и]?\s*[\d\s,и]+\)", " ", cleaned)
        cleaned = re.sub(r"(?i)\bисточник[и]?\s+\d+\b", " ", cleaned)
        # 3. Исключаем структурную нумерацию (Способ 1, Шаг 2, Вариант 3, Раздел 4, Пункт 5)
        cleaned = re.sub(
            r"(?i)\b(?:способ|шаг|этап|вариант|пункт|раздел|глава|часть)\s+\d+\b",
            " ",
            cleaned,
        )
        # 4. Исключаем маркеры нумерованных списков и подзаголовков (1., 2., ### 1., 1) )
        cleaned = re.sub(
            r"(?:^|(?<=\n))\s*(?:#{1,6}\s*)?\d+[\.)]\s*", " ", cleaned
        )
        # 5. Склеиваем пробелы между цифрами (например, "500 000" -> "500000")
        normalized = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
        # 6. Нормализуем слеши в датах (например, "15/10/2024" -> "15.10.2024")
        normalized = re.sub(r"(?<=\d)/(?=\d)", ".", normalized)
        # 7. Извлекаем последовательности цифр с точками или запятыми
        tokens = re.findall(r"\b\d+(?:[.,]\d+)*\b", normalized)
        return {t.replace(",", ".").strip(".") for t in tokens if t.strip(".")}

    def verify_sentence(
        self,
        sentence: str,
        chunks: list[ContextChunk],
        allowed_query_numbers: set[str],
    ) -> bool:
        """Выполняет инлайн-проверку предложения на сноски и числа.

        Правила верификации:
        1. Если сноска ссылается на несуществующий чанк (N <= 0 или N > len(chunks)) -> False.
        2. Если в предложении нет чисел/дат/процентов и сноски валидны -> True.
        3. Если в предложении есть числа, но нет ни одной сноски:
           - Числа разрешены только если они полностью содержались в запросе пользователя.
           - Иначе -> False.
        4. Если в предложении есть числа и валидные сноски:
           - Все числа из предложения обязаны присутствовать в процитированных чанках
             или в запросе пользователя. При отсутствии хотя бы одного числа -> False.
        """
        footnotes = self.extract_footnotes(sentence)

        # Проверка валидности индексов сносок
        for fn in footnotes:
            if fn <= 0 or fn > len(chunks):
                return False

        sentence_numbers = self.extract_numeric_facts(sentence)
        if not sentence_numbers:
            return True

        if not footnotes:
            # Есть числа, но нет сноски: допустимо только если числа пришли из вопроса
            return sentence_numbers.issubset(allowed_query_numbers)

        # Собираем допустимые числа из всех процитированных чанков
        cited_numbers: set[str] = set()
        for fn in footnotes:
            chunk = chunks[fn - 1]
            chunk_content = f"{chunk.title or ''} {chunk.section_path or ''} {chunk.quote_text or ''}"
            cited_numbers.update(self.extract_numeric_facts(chunk_content))

        valid_pool = cited_numbers | allowed_query_numbers
        return sentence_numbers.issubset(valid_pool)


UNVERIFIED_FACTS_DISCLAIMER = (
    "[Данные о сроках, суммах или статьях не подтверждены регламентом Портала и скрыты. "
    "Пожалуйста, обратитесь к оператору]"
)


class RagStreamGenerator:
    """Генератор потоковых ответов с нарезкой на предложения и факт-чекингом."""

    def __init__(
        self,
        llm_client: LlmStreamClientProtocol | None = None,
        timeout: float | None = None,
    ) -> None:
        """Инициализирует генератор потока с заданным клиентом LLM."""
        from src.core.config import settings

        self.llm_client = llm_client or get_llm_stream_client()
        self.timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS
        self.guard = FactCheckingGuard()

    async def generate_response_stream(
        self,
        query: str,
        chunks: list[ContextChunk],
        conversation_history: list[dict[str, str]] | None = None,
        message_id: UUID | None = None,
    ) -> AsyncIterator[
        RagSentenceEventSchema
        | RagDoneEventSchema
        | RagDegradedModeEventSchema
    ]:
        """Генерирует поток предложений и финальное событие со сносками и верификацией."""
        system_prompt, user_prompt = format_rag_prompt(
            query=query,
            chunks=chunks,
            conversation_history=conversation_history,
        )

        query_numbers = self.guard.extract_numeric_facts(query)
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") == "user":
                    query_numbers.update(
                        self.guard.extract_numeric_facts(msg.get("text", ""))
                    )

        buffer = SentenceBuffer()
        sentence_idx = 0
        full_text_parts: list[str] = []
        all_verified = True

        try:
            stream = self.llm_client.generate_stream(
                prompt=user_prompt,
                system_prompt=system_prompt,
                timeout=self.timeout,
            )

            async for token in stream:
                completed = buffer.feed(token)
                for sentence in completed:
                    verified = self.guard.verify_sentence(
                        sentence, chunks, query_numbers
                    )
                    text_to_emit = sentence
                    if not verified:
                        all_verified = False
                        logger.warning(
                            "FactCheckingGuard: недостоверные факты в предложении '%s', скрываем текст.",
                            sentence,
                        )
                        text_to_emit = UNVERIFIED_FACTS_DISCLAIMER

                    full_text_parts.append(text_to_emit)
                    yield RagSentenceEventSchema(
                        sentence_idx=sentence_idx,
                        text=text_to_emit,
                        verified=verified,
                    )
                    sentence_idx += 1

            # Сбрасываем завершающий остаток буфера
            tail_sentences = buffer.flush()
            for sentence in tail_sentences:
                verified = self.guard.verify_sentence(
                    sentence, chunks, query_numbers
                )
                text_to_emit = sentence
                if not verified:
                    all_verified = False
                    logger.warning(
                        "FactCheckingGuard: недостоверные факты в предложении '%s', скрываем текст.",
                        sentence,
                    )
                    text_to_emit = UNVERIFIED_FACTS_DISCLAIMER

                full_text_parts.append(text_to_emit)
                yield RagSentenceEventSchema(
                    sentence_idx=sentence_idx,
                    text=text_to_emit,
                    verified=verified,
                )
                sentence_idx += 1

            full_text = " ".join(full_text_parts)
            yield RagDoneEventSchema(
                message_id=message_id,
                text=full_text,
                all_verified=all_verified,
            )

        except Exception as exc:
            logger.warning(
                "RAG generator stream error, switching to degraded mode: %s",
                exc,
            )
            if not full_text_parts:
                yield RagDegradedModeEventSchema(
                    message=(
                        "Генеративная модель временно недоступна. "
                        "Ниже представлены найденные нормативные регламенты."
                    ),
                    sources=chunks,
                )
            else:
                full_text = " ".join(full_text_parts)
                yield RagDoneEventSchema(
                    message_id=message_id,
                    text=full_text,
                    all_verified=False,
                )
