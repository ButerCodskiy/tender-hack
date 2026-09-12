"""Тесты критического рефакторинга и защиты RAG-пайплайна (Hardening & Verification).

Проверяемые требования:
1. LexicalDenseReranker: расчет S_final = 0.60 * S_dense + 0.40 * R_lex и корректная сортировка.
2. Retriever: отсечение низкоуверенных запросов по score_threshold (0.40) и сохранение при спектральном разрыве (delta >= 0.08, s1 >= 0.28).
3. Retriever: ограничение длины родительского контекста kb_nodes (до 6000 символов).
4. RagService: режим деградации без вызова LLM при пустых источниках.
5. FactCheckingGuard & Generator: активная маскировка непроверенных предложений дисклеймером.
6. ChatService & QueryRouter: перехват chitchat / out_of_domain без RAG, эскалация ошибок 0x... в P0/L2, передача истории диалога.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import uuid6

from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.schemas import ClientSendMessageRequestSchema
from src.chat.service import ChatService
from src.rag.generator import (
    UNVERIFIED_FACTS_DISCLAIMER,
    MockLlmStreamClient,
    RagStreamGenerator,
)
from src.rag.reranker import LexicalDenseReranker
from src.rag.retriever import Retriever
from src.rag.schemas import (
    ContextChunk,
    QueryRouterOutput,
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagQueryRequestSchema,
    RagSentenceEventSchema,
)
from src.rag.service import RagService

# ==============================================================================
# 1. Тесты лексико-плотного реранкера (LexicalDenseReranker)
# ==============================================================================


def test_lexical_dense_reranker_scoring_and_sorting() -> None:
    """Проверяет формулу S_final = 0.60 * S_dense + 0.40 * R_lex и переранжирование."""
    reranker = LexicalDenseReranker(dense_weight=0.60, lexical_weight=0.40)

    # Чанк A: высокий dense (0.90), но нулевой lexical overlap с запросом
    chunk_a = ContextChunk(
        chunk_id="chunk_a",
        doc_id="DOC_A",
        title="Общие положения",
        section_path="Введение",
        quote_text="Текст без ключевых терминов нашего поиска.",
        relevance_score=0.90,
    )

    # Чанк B: умеренный dense (0.70), но 100% lexical overlap
    chunk_b = ContextChunk(
        chunk_id="chunk_b",
        doc_id="DOC_B",
        title="Протокол разногласий",
        section_path="Раздел 4",
        quote_text="Порядок подачи и подписания протокола разногласий в ЛК.",
        relevance_score=0.70,
    )

    query = "протокол разногласий"
    reranked = reranker.rerank(query, [chunk_a, chunk_b])

    # Для chunk_a: lex = 0/2 = 0.0 -> score = 0.60 * 0.90 + 0 = 0.54
    # Для chunk_b: lex = 2/2 = 1.0 -> score = 0.60 * 0.70 + 0.40 * 1.0 = 0.82
    assert len(reranked) == 2
    assert reranked[0].chunk_id == "chunk_b"
    assert reranked[0].relevance_score == 0.82
    assert reranked[1].chunk_id == "chunk_a"
    assert reranked[1].relevance_score == 0.54


def test_lexical_dense_reranker_empty_chunks() -> None:
    """Проверяет обработку пустого списка чанков."""
    reranker = LexicalDenseReranker()
    assert reranker.rerank("какой-то запрос", []) == []


# ==============================================================================
# 2. Тесты Retriever: порог сходства, спектральный разрыв и ограничение размера
# ==============================================================================


@pytest.mark.asyncio
async def test_retriever_low_confidence_spectral_gap_rejects_noise() -> None:
    """При top-1 < 0.40 и отсутствии спектрального разрыва (delta < 0.08) ретривер возвращает []."""
    mock_qdrant = AsyncMock()

    # Два шумовых чанка с близкими низкими оценками
    point1 = MagicMock(score=0.35, payload={"chunk_id": "c1", "text": "Шум 1"})
    point2 = MagicMock(score=0.32, payload={"chunk_id": "c2", "text": "Шум 2"})
    mock_response = MagicMock(points=[point1, point2])
    mock_qdrant.query_points.return_value = mock_response

    retriever = Retriever(qdrant_client=mock_qdrant)
    # Запрос из 5 слов -> effective_threshold = 0.40
    # s1 = 0.35 < 0.40, delta = 0.03 < 0.08 -> отказ
    results = await retriever.retrieve("как испечь вкусный яблочный пирог")

    assert results == []


@pytest.mark.asyncio
async def test_retriever_spectral_gap_accepts_isolated_peak() -> None:
    """При top-1 < 0.40, но delta >= 0.08 и s1 >= 0.28, изолированный пик принимается."""
    mock_qdrant = AsyncMock()

    # Изолированный чанк с заметным отрывом от фона
    point1 = MagicMock(
        id="c1",
        score=0.36,
        payload={
            "chunk_id": "c1",
            "doc_id": "DOC_1",
            "title": "Редкая норма",
            "text": "Специфический пункт регламента.",
        },
    )
    point2 = MagicMock(
        id="c2",
        score=0.22,
        payload={"chunk_id": "c2", "text": "Шумовой фон"},
    )
    mock_response = MagicMock(points=[point1, point2])
    mock_qdrant.query_points.return_value = mock_response

    retriever = Retriever(qdrant_client=mock_qdrant)
    # Запрос из 4 слов -> effective_threshold = 0.40
    # s1 = 0.36, s2 = 0.22, delta = 0.14 >= 0.08, s1 >= 0.28 -> допускаем point1
    results = await retriever.retrieve(
        "специфическая норма регламента портала"
    )

    assert len(results) == 1
    assert results[0].chunk_id == "c1"
    assert results[0].relevance_score == 0.36


@pytest.mark.asyncio
async def test_retriever_caps_parent_node_length() -> None:
    """Проверяет ограничение длины родительского контекста 6000 символами."""
    mock_qdrant = AsyncMock()
    giant_text = "А" * 10000

    point = MagicMock(
        id="c_giant",
        score=0.85,
        payload={
            "chunk_id": "c_giant",
            "doc_id": "DOC_GIANT",
            "title": "Огромный регламент",
            "text": giant_text,
        },
    )
    mock_response = MagicMock(points=[point])
    mock_qdrant.query_points.return_value = mock_response

    retriever = Retriever(qdrant_client=mock_qdrant)
    results = await retriever.retrieve("вопрос по регламенту")

    assert len(results) == 1
    quote = results[0].quote_text
    assert quote is not None
    assert len(quote) < 7000
    assert "Текст фрагмента сокращен для оптимизации контекста" in quote


# ==============================================================================
# 3. Тесты RagService: режим деградации при пустых источниках
# ==============================================================================


@pytest.mark.asyncio
async def test_rag_service_empty_retrieval_triggers_degraded_mode_without_llm() -> (
    None
):
    """При пустом результате поиска RagService эмитит degraded_mode без вызова генератора."""
    mock_retriever = AsyncMock()
    mock_retriever.retrieve.return_value = []

    mock_generator = AsyncMock()
    rag_service = RagService(
        generator=mock_generator, retriever=mock_retriever
    )

    request = RagQueryRequestSchema(query="Как приготовить борщ?")
    events = [event async for event in rag_service.generate_answer(request)]

    # Проверяем, что генератор не вызывался вовсе
    mock_generator.generate_response_stream.assert_not_called()

    # Проверяем последовательность: статусы -> degraded_mode
    degraded_events = [
        e for e in events if isinstance(e, RagDegradedModeEventSchema)
    ]
    assert len(degraded_events) == 1
    assert (
        "не найдена информация по вашему вопросу" in degraded_events[0].message
    )
    assert degraded_events[0].sources == []


# ==============================================================================
# 4. Тесты FactCheckingGuard & Generator: активная маскировка галлюцинаций
# ==============================================================================


@pytest.mark.asyncio
async def test_generator_masks_hallucinated_numbers_with_safe_disclaimer() -> (
    None
):
    """Генератор заменяет предложение с неподтвержденными числами на безопасный дисклеймер."""
    chunk = ContextChunk(
        chunk_id="chunk_1",
        doc_id="DOC_1",
        title="Сроки подписания",
        quote_text="Срок подписания протокола составляет 3 рабочих дня.",
        relevance_score=0.95,
    )

    # Модель галлюцинирует число 99, которого нет в контексте
    hallucinated_stream = "Срок подписания составляет 99 рабочих дней [^1]."
    mock_llm = MockLlmStreamClient(default_text=hallucinated_stream)
    generator = RagStreamGenerator(llm_client=mock_llm)

    events = [
        event
        async for event in generator.generate_response_stream(
            query="Какой срок?",
            chunks=[chunk],
            message_id=uuid6.uuid7(),
        )
    ]

    sentence_events = [
        e for e in events if isinstance(e, RagSentenceEventSchema)
    ]
    done_events = [e for e in events if isinstance(e, RagDoneEventSchema)]

    assert len(sentence_events) == 1
    assert sentence_events[0].verified is False
    # Текст замаскирован
    assert sentence_events[0].text == UNVERIFIED_FACTS_DISCLAIMER
    assert "99" not in sentence_events[0].text

    assert len(done_events) == 1
    assert done_events[0].all_verified is False
    assert UNVERIFIED_FACTS_DISCLAIMER in done_events[0].text


# ==============================================================================
# 5. Тесты ChatService & QueryRouter интеграции
# ==============================================================================


@pytest.mark.asyncio
async def test_chat_service_intercepts_chitchat_and_out_of_domain() -> None:
    """ChatService перехватывает chitchat и out_of_domain без обращения к RAG."""
    mock_repo = AsyncMock()
    mock_session = AsyncMock()
    mock_ticket_repo = AsyncMock()
    mock_rag = AsyncMock()
    mock_router = AsyncMock()

    chat = ChatModel(id=uuid4(), client_id=uuid4())
    active_ticket = TicketModel(
        id=uuid4(),
        chat_id=chat.id,
        status=TicketStatus.BOT_PROCESSING.value,
        priority=TicketPriority.P2.value,
    )
    mock_repo.get_by_client_id.return_value = chat
    mock_ticket_repo.get_active_by_chat_id.return_value = active_ticket
    mock_repo.get_recent_messages.return_value = []

    # 1. Проверка chitchat
    mock_router.route.return_value = QueryRouterOutput(
        intent="chitchat",
        regime_hint="MOS_PORTAL",
        topic="general_faq",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        error_codes=[],
        escalation_requested=False,
        entities=[],
        standalone_query="Привет",
        sub_queries=[],
    )

    chat_service = ChatService(
        repo=mock_repo,
        session=mock_session,
        rag_service=mock_rag,
        ticket_repo=mock_ticket_repo,
        query_router=mock_router,
    )

    events_chitchat = [
        ev
        async for ev in chat_service.process_client_message(
            client_id=chat.client_id,
            payload=ClientSendMessageRequestSchema(text="Привет!"),
        )
    ]

    # RAG не должен вызываться
    mock_rag.generate_answer.assert_not_called()
    assert any("виртуальный ассистент" in ev for ev in events_chitchat)

    # 2. Проверка out_of_domain
    mock_router.route.return_value = QueryRouterOutput(
        intent="out_of_domain",
        regime_hint="MOS_PORTAL",
        topic="general_faq",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        error_codes=[],
        escalation_requested=False,
        entities=[],
        standalone_query="Как сварить борщ?",
        sub_queries=[],
    )

    events_ood = [
        ev
        async for ev in chat_service.process_client_message(
            client_id=chat.client_id,
            payload=ClientSendMessageRequestSchema(text="Как сварить борщ?"),
        )
    ]

    mock_rag.generate_answer.assert_not_called()
    assert any("специализированный консультант" in ev for ev in events_ood)


@pytest.mark.asyncio
async def test_chat_service_elevates_error_code_to_p0_and_passes_history() -> (
    None
):
    """При наличии кода 0x... тикет повышается до P0, а история реплик передается в RAG."""
    mock_repo = AsyncMock()
    mock_session = AsyncMock()
    mock_session.scalars.return_value = MagicMock(
        first=lambda: 2
    )  # line_id = 2 для L2
    mock_ticket_repo = AsyncMock()
    mock_rag = AsyncMock()
    mock_router = AsyncMock()

    chat = ChatModel(id=uuid4(), client_id=uuid4())
    active_ticket = TicketModel(
        id=uuid4(),
        chat_id=chat.id,
        status=TicketStatus.BOT_PROCESSING.value,
        priority=TicketPriority.P2.value,
        line_id=1,
    )
    mock_repo.get_by_client_id.return_value = chat
    mock_ticket_repo.get_active_by_chat_id.return_value = active_ticket

    # Предыдущие сообщения в БД
    msg1 = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=active_ticket.id,
        sender_type=MessageSenderType.CLIENT,
        text="Не могу подписать контракт",
        created_at=MagicMock(),
    )
    mock_repo.get_recent_messages.return_value = [msg1]

    # Роутер находит код ошибки
    mock_router.route.return_value = QueryRouterOutput(
        intent="qa",
        regime_hint="MOS_PORTAL",
        topic="technical_errors",
        priority="P1",
        support_line="L2",
        sentiment="frustrated",
        follow_up_type="none",
        error_codes=["0x80090016"],
        escalation_requested=False,
        entities=[],
        standalone_query="Ошибка плагина 0x80090016",
        sub_queries=[],
    )

    # Мок стрима RAG для проверки переданной истории
    async def _mock_rag_gen(req: RagQueryRequestSchema):
        assert req.conversation_history is not None
        assert len(req.conversation_history) == 1
        assert (
            req.conversation_history[0]["text"] == "Не могу подписать контракт"
        )
        yield RagDoneEventSchema(
            message_id=req.message_id, text="Решение ошибки", all_verified=True
        )

    mock_rag.generate_answer.side_effect = _mock_rag_gen

    chat_service = ChatService(
        repo=mock_repo,
        session=mock_session,
        rag_service=mock_rag,
        ticket_repo=mock_ticket_repo,
        query_router=mock_router,
    )

    _ = [
        ev
        async for ev in chat_service.process_client_message(
            client_id=chat.client_id,
            payload=ClientSendMessageRequestSchema(
                text="Ошибка плагина 0x80090016"
            ),
        )
    ]

    # Проверяем эскалацию тикета
    assert active_ticket.priority == TicketPriority.P0
    assert active_ticket.line_id == 2
    mock_ticket_repo.update.assert_called_with(active_ticket)
