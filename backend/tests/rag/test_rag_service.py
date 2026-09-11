"""Тесты сервисной заглушки поискового ядра RagService и контрактов потоковых событий."""

import uuid6
from pydantic import TypeAdapter

from src.rag.schemas import (
    RagDoneEventSchema,
    RagQueryRequestSchema,
    RagResponseSchema,
    RagSentenceEventSchema,
    RagSourcesEventSchema,
    RagStatusEventSchema,
    RagStreamEvent,
)
from src.rag.service import RagService


async def test_generate_answer_stream_flow() -> None:
    """Проверяет корректность потока событий SSE: порядок, структуру и типы."""
    service = RagService()
    message_id = uuid6.uuid7()
    payload = RagQueryRequestSchema(
        query="Как подписать протокол разногласий?",
        message_id=message_id,
    )

    events: list[RagStreamEvent] = []
    async for event in service.generate_answer(payload):
        events.append(event)

    # Проверка общего количества событий (3 status + 1 sources + 2 sentence + 1 done)
    assert len(events) == 7

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

    # 3. Проверка предложений sentence
    assert isinstance(events[4], RagSentenceEventSchema)
    assert events[4].event == "sentence"
    assert events[4].sentence_idx == 0
    assert events[4].verified is True
    assert "протокол разногласий" in events[4].text

    assert isinstance(events[5], RagSentenceEventSchema)
    assert events[5].event == "sentence"
    assert events[5].sentence_idx == 1
    assert events[5].verified is True
    assert "[^1]" in events[5].text

    # 4. Проверка события done
    assert isinstance(events[6], RagDoneEventSchema)
    assert events[6].event == "done"
    assert events[6].message_id == message_id
    assert events[6].all_verified is True
    assert events[4].text in events[6].text
    assert events[5].text in events[6].text


async def test_generate_answer_without_message_id() -> None:
    """Проверяет генерацию ответа без предварительно заданного message_id."""
    service = RagService()
    payload = RagQueryRequestSchema(query="Как пройти регистрацию?")

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
