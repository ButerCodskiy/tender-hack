"""Тесты сервисной заглушки поискового ядра RagService и контрактов потоковых событий."""

from unittest.mock import AsyncMock

import uuid6
from pydantic import TypeAdapter

from src.rag.generator import MockLlmStreamClient, RagStreamGenerator
from src.rag.retriever import Retriever
from src.rag.schemas import (
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagQueryRequestSchema,
    RagResponseSchema,
    RagSentenceEventSchema,
    RagSourceChunkSchema,
    RagSourcesEventSchema,
    RagStatusEventSchema,
    RagStreamEvent,
)
from src.rag.service import RagService


def _get_mock_service(
    chunks: list[RagSourceChunkSchema] | None = None,
) -> RagService:
    """Создает изолированный RagService с мок-генератором и мок-ретривером."""
    if chunks is None:
        chunks = [
            RagSourceChunkSchema(
                chunk_id="chunk_portal_zakupki_reglament_sec4_p1",
                doc_id="DOC_PORTAL_REGULATION_V6",
                title="Регламент ведения котировочных сессий. Раздел 4. Подписание протоколов",
                quote_text=(
                    "Участник закупки вправе сформировать и подписать протокол разногласий "
                    "в личном кабинете поставщика в течение 3 рабочих дней с момента "
                    "публикации проекта контракта заказчиком."
                ),
                section_path="Раздел 4. Подписание протоколов",
                source_url="https://zakupki.mos.ru/regulations/p4",
                relevance_score=0.96,
            )
        ]
    mock_retriever = AsyncMock(spec=Retriever)
    mock_retriever.retrieve.return_value = chunks
    mock_generator = RagStreamGenerator(llm_client=MockLlmStreamClient())
    return RagService(generator=mock_generator, retriever=mock_retriever)


async def test_generate_answer_stream_flow() -> None:
    """Проверяет корректность потока событий SSE: порядок, структуру и типы."""
    service = _get_mock_service()
    message_id = uuid6.uuid7()
    payload = RagQueryRequestSchema(
        query="Как подписать протокол разногласий?",
        message_id=message_id,
    )

    events: list[RagStreamEvent] = []
    async for event in service.generate_answer(payload):
        events.append(event)

    # Проверка общего количества событий (4 status + 1 sources + 2 sentence + 1 done)
    assert len(events) == 8

    # 1. Проверка событий status
    assert isinstance(events[0], RagStatusEventSchema)
    assert events[0].event == "status"
    assert events[0].code == "classifying"

    assert isinstance(events[1], RagStatusEventSchema)
    assert events[1].event == "status"
    assert events[1].code == "searching"

    assert isinstance(events[2], RagStatusEventSchema)
    assert events[2].event == "status"
    assert events[2].code == "reranking"

    # 2. Проверка события sources
    assert isinstance(events[3], RagSourcesEventSchema)
    assert events[3].event == "sources"
    assert len(events[3].sources) == 1
    chunk = events[3].sources[0]
    assert chunk.chunk_id == "chunk_portal_zakupki_reglament_sec4_p1"
    assert chunk.doc_id == "DOC_PORTAL_REGULATION_V6"
    assert chunk.quote_text is not None
    assert chunk.relevance_score is not None

    # 3. Проверка статуса generating
    assert isinstance(events[4], RagStatusEventSchema)
    assert events[4].event == "status"
    assert events[4].code == "generating"

    # 4. Проверка предложений sentence
    assert isinstance(events[5], RagSentenceEventSchema)
    assert events[5].event == "sentence"
    assert events[5].sentence_idx == 0
    assert events[5].verified is True
    assert "протокол разногласий" in events[5].text

    assert isinstance(events[6], RagSentenceEventSchema)
    assert events[6].event == "sentence"
    assert events[6].sentence_idx == 1
    assert events[6].verified is True
    assert "[^1]" in events[6].text

    # 5. Проверка события done
    assert isinstance(events[7], RagDoneEventSchema)
    assert events[7].event == "done"
    assert events[7].message_id == message_id
    assert events[7].all_verified is True
    assert events[5].text in events[7].text
    assert events[6].text in events[7].text


async def test_generate_answer_degraded_mode_when_no_chunks() -> None:
    """Проверяет переход в режим деградации без вызова LLM при отсутствии найденных чанков (ADR 0005)."""
    service = _get_mock_service(chunks=[])
    payload = RagQueryRequestSchema(query="Какой рецепт борща?")

    events: list[RagStreamEvent] = []
    async for event in service.generate_answer(payload):
        events.append(event)

    # 3 status + 1 degraded_mode (без обращения к генератору)
    assert len(events) == 4
    degraded_event = events[-1]
    assert isinstance(degraded_event, RagDegradedModeEventSchema)
    assert degraded_event.event == "degraded_mode"
    assert "не найдена" in degraded_event.message


async def test_generate_answer_without_message_id() -> None:
    """Проверяет генерацию ответа без предварительно заданного message_id."""
    service = _get_mock_service()
    payload = RagQueryRequestSchema(
        query="Как подписать протокол разногласий?"
    )

    events: list[RagStreamEvent] = []
    async for event in service.generate_answer(payload):
        events.append(event)

    done_event = events[-1]
    assert isinstance(done_event, RagDoneEventSchema)
    assert done_event.message_id is None
    assert done_event.all_verified is True


def test_rag_stream_event_discriminated_union() -> None:
    """Проверяет валидацию потоковых событий через дискриминированное объединение Pydantic."""
    adapter = TypeAdapter(RagStreamEvent)

    status_raw = {
        "event": "status",
        "code": "searching",
        "message": "Поиск по базе знаний...",
    }
    parsed_status = adapter.validate_python(status_raw)
    assert isinstance(parsed_status, RagStatusEventSchema)
    assert parsed_status.code == "searching"

    sentence_raw = {
        "event": "sentence",
        "sentence_idx": 0,
        "text": "Тестовое предложение [^1].",
        "verified": True,
    }
    parsed_sentence = adapter.validate_python(sentence_raw)
    assert isinstance(parsed_sentence, RagSentenceEventSchema)
    assert parsed_sentence.sentence_idx == 0


async def test_search_and_answer_backward_compatibility() -> None:
    """Проверяет обратную совместимость метода search_and_answer для существующих тестов."""
    service = RagService()
    payload = RagQueryRequestSchema(
        query="Как подписать протокол разногласий на Портале поставщиков?"
    )
    response = await service.search_and_answer(payload)

    assert isinstance(response, RagResponseSchema)
    assert response.confidence_score == 0.96
    assert response.verified is True
    assert len(response.sources) == 1
    assert "протокол разногласий" in response.answer
