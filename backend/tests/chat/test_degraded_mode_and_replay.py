from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import get_auth_service, get_chat_service
from src.api.v1.chat import router as chat_router
from src.auth.models import RoleModel, UserModel
from src.auth.service import AuthService
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.repository import ChatRepository, TicketRepository
from src.chat.schemas import ClientSendMessageRequestSchema
from src.chat.service import ChatService
from src.core.config import settings
from src.core.redis_client import RedisChatContext, RedisTicketEvents
from src.rag.schemas import (
    RagDegradedModeEventSchema,
    RagSourceChunkSchema,
    RagSourcesEventSchema,
)
from src.rag.service import RagService


@pytest.fixture
def mock_chat_context() -> tuple[
    ChatService,
    AsyncMock,  # repo
    AsyncMock,  # session
    AsyncMock,  # ticket_repo
    AsyncMock,  # redis_context
    AsyncMock,  # ticket_events
]:
    """Создает изолированный ChatService со всеми моками."""
    repo = AsyncMock(spec=ChatRepository)
    session = AsyncMock()
    ticket_repo = AsyncMock(spec=TicketRepository)
    redis_context = AsyncMock(spec=RedisChatContext)
    ticket_events = AsyncMock(spec=RedisTicketEvents)
    rag_service = AsyncMock(spec=RagService)

    service = ChatService(
        repo=repo,
        session=session,
        rag_service=rag_service,
        ticket_repo=ticket_repo,
        redis_context=redis_context,
        ticket_events=ticket_events,
    )
    return service, repo, session, ticket_repo, redis_context, ticket_events


@pytest.mark.asyncio
async def test_degraded_mode_saves_message_sources_and_redis(
    mock_chat_context: tuple[
        ChatService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет сохранение реплики деградации и первоисточников в PostgreSQL и Redis."""
    service, repo, _session, ticket_repo, redis_context, _ = mock_chat_context

    user_id = uuid6.uuid7()
    user = UserModel(
        id=user_id,
        email="client_deg@zakupki.mos.ru",
        password_hash="hash",
        full_name="Клиент Деградация",
    )
    chat = ChatModel(id=uuid6.uuid7(), client_id=user_id)
    repo.get_by_client_id.return_value = chat

    active_ticket = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        status=TicketStatus.BOT_PROCESSING.value,
        priority=TicketPriority.P2.value,
    )
    ticket_repo.get_active_by_chat_id.return_value = active_ticket

    # Мокаем генератор RAG, отдающий событие degraded_mode
    mock_chunk = RagSourceChunkSchema(
        chunk_id="chk_1",
        doc_id="doc_1",
        title="Статья 1",
        quote_text="Цитата",
        relevance_score=0.95,
    )

    async def _rag_gen(req):
        yield RagSourcesEventSchema(sources=[mock_chunk])
        yield RagDegradedModeEventSchema(
            message="Генеративная модель временно недоступна. Ниже представлены найденные нормативные регламенты.",
            sources=[mock_chunk],
        )

    service.rag_service.generate_answer = _rag_gen

    payload = ClientSendMessageRequestSchema(text="Как подписать протокол?")
    events = []
    async for chunk in service.process_client_message(
        payload=payload, user=user, accept_header="text/event-stream"
    ):
        events.append(chunk)

    output = "".join(events)
    assert "event: sources" in output
    assert "event: degraded_mode" in output
    assert "Генеративная модель временно недоступна" in output

    # Проверяем сохранение реплики бота в repo.save_message
    saved_calls = repo.save_message.call_args_list
    assert len(saved_calls) == 2  # 1: клиент, 2: бот (деградация)
    bot_msg = saved_calls[1][0][0]
    sources = saved_calls[1][1].get("sources")

    assert bot_msg.sender_type == MessageSenderType.BOT.value
    assert "Генеративная модель временно недоступна" in bot_msg.text
    assert bot_msg.moderation_status == MessageModerationStatus.PASSED.value
    assert len(sources) == 1
    assert sources[0].chunk_id == "chk_1"

    # Проверяем сохранение в оперативный контекст Redis
    redis_context.add_message.assert_awaited()
    last_call = redis_context.add_message.await_args_list[-1]
    assert last_call.kwargs["sender"] == "bot"
    assert (
        "Генеративная модель временно недоступна" in last_call.kwargs["text"]
    )


@pytest.mark.asyncio
async def test_high_level_rag_exception_handled_gracefully(
    mock_chat_context: tuple[
        ChatService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет перехват критического исключения до генератора (сбой Qdrant/эмбеддинга)."""
    service, repo, _session, ticket_repo, _redis_context, _ = mock_chat_context

    user_id = uuid6.uuid7()
    user = UserModel(
        id=user_id,
        email="client_err@zakupki.mos.ru",
        password_hash="hash",
        full_name="Клиент Сбой",
    )
    chat = ChatModel(id=uuid6.uuid7(), client_id=user_id)
    repo.get_by_client_id.return_value = chat
    ticket_repo.get_active_by_chat_id.return_value = TicketModel(
        id=uuid6.uuid7(), chat_id=chat.id, status="bot_processing"
    )

    async def _crashing_gen(req):
        raise ConnectionError("Qdrant cluster unavailable")
        yield

    service.rag_service.generate_answer = _crashing_gen

    payload = ClientSendMessageRequestSchema(text="Вопрос при падении")
    events = []
    async for chunk in service.process_client_message(
        payload=payload, user=user, accept_header="text/event-stream"
    ):
        events.append(chunk)

    output = "".join(events)
    assert "event: degraded_mode" in output
    assert "Генеративная модель временно недоступна" in output

    # Убеждаемся, что бот-сообщение сохранено
    saved_calls = repo.save_message.call_args_list
    assert len(saved_calls) == 2
    bot_msg = saved_calls[1][0][0]
    assert bot_msg.sender_type == MessageSenderType.BOT.value


@pytest.mark.asyncio
async def test_sse_replay_protocol_via_last_event_id(
    mock_chat_context: tuple[
        ChatService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет досылку пропущенных сообщений по Last-Event-ID и дедупликацию Pub/Sub."""
    service, repo, _, ticket_repo, _, ticket_events = mock_chat_context

    user = UserModel(
        id=uuid6.uuid7(),
        email="client_sse@zakupki.mos.ru",
        password_hash="hash",
        full_name="Клиент СЕЕ",
    )
    chat = ChatModel(id=uuid6.uuid7(), client_id=user.id)
    repo.get_by_client_id.return_value = chat

    ticket_id = uuid6.uuid7()
    ticket = TicketModel(id=ticket_id, chat_id=chat.id, status="in_progress")
    ticket_repo.get_by_id.return_value = ticket

    last_event_id = uuid6.uuid7()
    msg_replayed = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        sender_type="operator",
        text="Пропущенный ответ оператора",
        moderation_status="passed",
        created_at=datetime.now(settings.TIMEZONE),
    )
    repo.get_messages_since_id.return_value = [msg_replayed]

    # Мокаем Pub/Sub стрим: первое сообщение - дубликат replayed, второе - новое
    async def _mock_pubsub(ticket_id, request):
        yield f'id: {msg_replayed.id}\nevent: new_message\ndata: {{"text": "Дубликат"}}\n\n'
        yield 'id: 018e5f1b-3a21-729d-9e5c-29b1f0c23b99\nevent: new_message\ndata: {"text": "Новое сообщение"}\n\n'

    ticket_events.subscribe_ticket_events = _mock_pubsub

    request_mock = AsyncMock(spec=Request)
    chunks = []
    async for chunk in service.stream_chat_events(
        user=user,
        ticket_id=ticket_id,
        request=request_mock,
        last_event_id=last_event_id,
    ):
        chunks.append(chunk)

    output = "".join(chunks)

    # 1. Проверяем вызов get_messages_since_id
    repo.get_messages_since_id.assert_awaited_once_with(
        ticket_id=ticket_id,
        last_event_id=last_event_id,
    )

    # 2. Проверяем, что пропущенное сообщение отправлено
    assert str(msg_replayed.id) in output
    assert "Пропущенный ответ оператора" in output

    # 3. Проверяем, что дубликат из PubSub был отфильтрован
    assert "Дубликат" not in output

    # 4. Проверяем, что действительно новое сообщение пришло
    assert "Новое сообщение" in output


@pytest.mark.asyncio
async def test_get_chat_events_endpoint_with_last_event_id_header() -> None:
    """Интеграционный тест эндпоинта GET /api/v1/chat/events с заголовком Last-Event-ID."""
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")

    user = UserModel(
        id=uuid6.uuid7(),
        email="client_test_header@zakupki.mos.ru",
        password_hash="fake",
        full_name="Тест Заголовок",
        role=RoleModel(id=1, code="client", name="Клиент"),
        is_active=True,
    )
    mock_auth = AsyncMock(spec=AuthService)
    mock_auth.get_user_by_token.return_value = user

    mock_chat = AsyncMock(spec=ChatService)

    async def _mock_stream(user, ticket_id, request, last_event_id=None):
        yield f'id: 123\nevent: new_message\ndata: {{"replayed_after": "{last_event_id}"}}\n\n'

    mock_chat.stream_chat_events = _mock_stream

    app.dependency_overrides[get_auth_service] = lambda: mock_auth
    app.dependency_overrides[get_chat_service] = lambda: mock_chat

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        last_id = str(uuid6.uuid7())
        response = await client.get(
            "/api/v1/chat/events?token=valid_token",
            headers={"Last-Event-ID": last_id},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert last_id in response.text
