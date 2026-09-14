"""Фасад поискового и генеративного ядра RagService."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.rag.generator import RagStreamGenerator
from src.rag.reranker import (
    LexicalDenseReranker,
    TransformerCrossEncoderReranker,
)
from src.rag.retriever import Retriever
from src.rag.schemas import (
    ContextChunk,
    RagDegradedModeEventSchema,
    RagQueryRequestSchema,
    RagResponseSchema,
    RagSourceChunkSchema,
    RagSourcesEventSchema,
    RagStatusEventSchema,
    RagStreamEvent,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.operators.schemas import CopilotSummaryResponseSchema


class RagService:
    """Сервис поиска по нормативной базе знаний и генерации ответов."""

    def __init__(
        self,
        generator: RagStreamGenerator | None = None,
        retriever: Retriever | None = None,
        reranker: LexicalDenseReranker | None = None,
    ) -> None:
        """Инициализирует RagService с генератором ответа, ретривером и реранкером."""
        self.generator = generator or RagStreamGenerator()
        self.retriever = retriever or Retriever()
        self.reranker = reranker or TransformerCrossEncoderReranker()

    async def _retrieve_context_chunks(
        self, payload: RagQueryRequestSchema
    ) -> list[ContextChunk]:
        """Извлекает нормативные чанки базы знаний через двухканальный Retriever."""
        chunks = await self.retriever.retrieve(payload.query)
        return list(chunks)

    async def generate_answer(
        self, payload: RagQueryRequestSchema
    ) -> AsyncGenerator[RagStreamEvent, None]:
        """Генерирует потоковый ответ в виде последовательности событий SSE-контракта.

        1. Промежуточные статусы (classifying, searching, reranking);
        2. Найденные источники первоисточников (sources);
        3. Законченные предложения со сносками и инлайн-валидацией (sentence);
        4. Завершающее событие с полным текстом и агрегированной верификацией (done)
           либо событие деградации при сбое генератора или отсутствии статей (degraded_mode).
        """
        # 1. Промежуточные статусные события пайплайна
        yield RagStatusEventSchema(
            code="classifying",
            message="Классификация тематики обращения...",
        )
        await asyncio.sleep(0.01)

        yield RagStatusEventSchema(
            code="searching",
            message="Поиск по нормативным регламентам...",
        )
        await asyncio.sleep(0.01)

        yield RagStatusEventSchema(
            code="reranking",
            message="Анализ точности найденных статей...",
        )
        await asyncio.sleep(0.01)

        # 2. Поиск источников базы знаний через Retriever
        chunks = await self._retrieve_context_chunks(payload)

        # Режим деградации (ADR 0005): если в базе знаний ничего не найдено или низкая уверенность,
        # не вызываем генератор во избежание галлюцинаций
        if not chunks:
            yield RagDegradedModeEventSchema(
                message=(
                    "В нормативной базе Портала поставщиков Москвы не найдена информация по вашему вопросу. "
                    "Рекомендуем уточнить формулировку или обратиться к специалисту поддержки."
                ),
                sources=[],
            )
            return

        # 3. Переранжирование найденных фрагментов с динамическим порогом и дедупликацией
        chunks = self.reranker.rerank(payload.query, chunks, max_parents=5)

        if not chunks:
            yield RagDegradedModeEventSchema(
                message=(
                    "В нормативной базе Портала поставщиков Москвы не найдена информация по вашему вопросу. "
                    "Рекомендуем уточнить формулировку или обратиться к специалисту поддержки."
                ),
                sources=[],
            )
            return

        yield RagSourcesEventSchema(sources=chunks)
        await asyncio.sleep(0.01)

        # 4. Потоковая генерация предложений с инлайн-валидацией через RagStreamGenerator
        yield RagStatusEventSchema(
            code="generating",
            message="Формирование ответа нейросетью...",
        )
        await asyncio.sleep(0.01)

        async for event in self.generator.generate_response_stream(
            query=payload.query,
            chunks=chunks,
            conversation_history=payload.conversation_history,
            message_id=payload.message_id,
        ):
            yield event

    async def search_and_answer(
        self, payload: RagQueryRequestSchema
    ) -> RagResponseSchema:
        """Выполняет поиск релевантных статей и формирует подтвержденный ответ.

        В рамках нулевого сквозного каркаса метод возвращает эталонный
        структурированный ответ с цитатами регламента Портала поставщиков Москвы.
        При подключении векторной базы Qdrant и моделей генерации сигнатура
        метода остается неизменной.
        """
        mock_source = RagSourceChunkSchema(
            chunk_id="chunk_portal_zakupki_reglament_sec4_p1",
            doc_id="DOC_PORTAL_REGULATION_V6",
            title="Регламент ведения котировочных сессий. Раздел 4. Подписание протоколов",
            quote_text=(
                "Участник закупки вправе сформировать и подписать протокол разногласий "
                "в личном кабинете поставщика в течение 3 рабочих дней с момента "
                "публикации проекта контракта заказчиком."
            ),
            relevance_score=0.96,
        )

        answer_text = (
            f"По вашему вопросу «{payload.query}»: в соответствии с регламентом "
            "Портала поставщиков Москвы, протокол разногласий подписывается в "
            "личном кабинете поставщика с использованием усиленной квалифицированной "
            "электронной подписи (ЭЦП) в течение трех рабочих дней [^1]."
        )

        return RagResponseSchema(
            answer=answer_text,
            sources=[mock_source],
            confidence_score=0.96,
            verified=True,
        )

    async def generate_copilot_summary(
        self,
        ticket_id: UUID | str,
        messages: list[dict[str, Any]],
        qdrant_client: AsyncQdrantClient | None = None,
    ) -> CopilotSummaryResponseSchema:
        """Формирует смысловую выжимку проблемы клиента и прецеденты для оператора."""
        from src.rag.copilot import CopilotService

        copilot = CopilotService(qdrant_client=qdrant_client)
        return await copilot.build_copilot_summary(
            ticket_id=ticket_id,
            messages=messages,
            qdrant_client=qdrant_client,
        )
