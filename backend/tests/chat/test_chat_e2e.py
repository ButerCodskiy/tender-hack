"""Сквозные тесты потоковой отправки сообщений клиентом и SSE-оркестратора POST /api/v1/chat/messages."""

import json
import uuid
from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as aioredis
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies import (
    get_chat_repository,
    get_chat_service,
    get_db,
    get_rag_service,
    get_redis_context,
    get_redis_line_queue,
    get_redis_ticket_events,
    get_ticket_repository,
)
from src.auth.models import RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.core.redis_client import RedisChatContext
from src.core.security import create_access_token
from src.db.database import Base, async_session_maker, engine
from src.main import app


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Гарантирует актуальную схему таблиц и очищает данные перед каждым тестом."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE message_sources, messages, tickets, chats, "
                "support_lines, client_profiles, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE message_sources, messages, tickets, chats, "
                "support_lines, client_profiles, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )


@pytest.fixture
async def redis_context(
    redis_client: aioredis.Redis,
) -> AsyncGenerator[RedisChatContext, None]:
    """Предоставляет клиент управления контекстом Redis."""
    context_mgr = RedisChatContext(redis=redis_client)
    yield context_mgr


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Предоставляет изолированную сессию базы данных PostgreSQL."""
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def client(
    test_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Создает тестовый HTTP-клиент с сессией базы данных."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_user(test_session: AsyncSession) -> UserModel:
    """Создает тестового пользователя с ролью клиента."""
    role = RoleModel(id=1, code="client", name="Клиент")
    test_session.add(role)
    await test_session.flush()

    user = UserModel(
        email="test_client_streaming@zakupki.mos.ru",
        password_hash="fake_hash",
        full_name="Иван Заказчиков",
        role_id=role.id,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client_user: UserModel) -> dict[str, str]:
    """Формирует заголовки авторизации с валидным Bearer-токеном клиента."""
    token = create_access_token(user_id=client_user.id, role_code="client")
    return {"Authorization": f"Bearer {token}"}


def parse_sse_events(raw_sse: str) -> list[dict]:
    """Разбирает сырой текст потока SSE на список событий и спарсенных данных."""
    events = []
    blocks = raw_sse.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_name = None
        data_json = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                payload_str = line[len("data: ") :].strip()
                data_json = json.loads(payload_str)
        if event_name and data_json is not None:
            events.append({"event": event_name, "data": data_json})
    return events


async def test_send_message_unauthorized(client: AsyncClient) -> None:
    """Проверяет отклонение запроса без токена или с недействительным токеном (401)."""
    resp_no_token = await client.post(
        "/api/v1/chat/messages",
        json={"text": "Вопрос без авторизации"},
    )
    assert resp_no_token.status_code == status.HTTP_401_UNAUTHORIZED

    resp_bad_token = await client.post(
        "/api/v1/chat/messages",
        json={"text": "Вопрос с плохим токеном"},
        headers={"Authorization": "Bearer invalid-jwt-token"},
    )
    assert resp_bad_token.status_code == status.HTTP_401_UNAUTHORIZED


async def test_send_message_validation_empty_text(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет ошибку 422 Unprocessable Content при пустом тексте сообщения."""
    resp_empty = await client.post(
        "/api/v1/chat/messages",
        json={"text": ""},
        headers=auth_headers,
    )
    assert resp_empty.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    resp_whitespace = await client.post(
        "/api/v1/chat/messages",
        json={"text": "    "},
        headers=auth_headers,
    )
    assert resp_whitespace.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    resp_missing = await client.post(
        "/api/v1/chat/messages",
        json={},
        headers=auth_headers,
    )
    assert resp_missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_send_message_sse_streaming_success(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
    redis_context: RedisChatContext,
) -> None:
    """Сквозной тест отправки сообщения, потока SSE, сохранения в PostgreSQL и контекст Redis."""
    client_question = (
        "Как подписать протокол разногласий по котировочной сессии?"
    )

    response = await client.post(
        "/api/v1/chat/messages",
        json={"text": client_question},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers.get("content-type", "")

    # 1. Проверка структуры событий Server-Sent Events
    events = parse_sse_events(response.text)
    assert len(events) >= 7

    event_names = [e["event"] for e in events]
    assert event_names == [
        "status",
        "status",
        "status",
        "sources",
        "sentence",
        "sentence",
        "done",
    ]

    # Проверка промежуточных статусов
    status_codes = [
        e["data"]["code"] for e in events if e["event"] == "status"
    ]
    assert status_codes == ["classifying", "searching", "reranking"]

    # Проверка события источников базы знаний
    sources_event = next(e for e in events if e["event"] == "sources")
    sources_list = sources_event["data"]["sources"]
    assert len(sources_list) > 0
    assert (
        sources_list[0]["chunk_id"] == "chunk_portal_zakupki_reglament_sec4_p1"
    )
    assert sources_list[0]["doc_id"] == "DOC_PORTAL_REGULATION_V6"
    assert sources_list[0]["quote_text"] is not None

    # Проверка предложений ответа
    sentence_events = [e for e in events if e["event"] == "sentence"]
    assert len(sentence_events) == 2
    assert sentence_events[0]["data"]["sentence_idx"] == 0
    assert sentence_events[0]["data"]["verified"] is True
    assert sentence_events[1]["data"]["sentence_idx"] == 1
    assert sentence_events[1]["data"]["verified"] is True

    # Проверка финального события done
    done_event = next(e for e in events if e["event"] == "done")
    bot_message_id_str = done_event["data"]["message_id"]
    assert bot_message_id_str is not None
    bot_message_id = uuid.UUID(bot_message_id_str)
    assert done_event["data"]["all_verified"] is True
    assert len(done_event["data"]["text"]) > 0

    # 2. Проверка записей в PostgreSQL
    chat = await test_session.scalar(
        select(ChatModel).where(ChatModel.client_id == client_user.id)
    )
    assert chat is not None

    tickets = (
        await test_session.scalars(
            select(TicketModel).where(TicketModel.chat_id == chat.id)
        )
    ).all()
    assert len(tickets) == 1
    ticket = tickets[0]
    assert ticket.status == TicketStatus.BOT_PROCESSING
    assert ticket.priority == TicketPriority.P2

    messages = (
        await test_session.scalars(
            select(MessageModel)
            .where(MessageModel.ticket_id == ticket.id)
            .options(selectinload(MessageModel.sources))
            .order_by(MessageModel.created_at.asc())
        )
    ).all()
    assert len(messages) == 2

    # Сообщение клиента
    client_msg = messages[0]
    assert client_msg.sender_type == MessageSenderType.CLIENT
    assert client_msg.sender_id == client_user.id
    assert client_msg.text == client_question
    assert client_msg.moderation_status == MessageModerationStatus.PASSED

    # Сообщение бота
    bot_msg = messages[1]
    assert bot_msg.id == bot_message_id
    assert bot_msg.sender_type == MessageSenderType.BOT
    assert bot_msg.sender_id is None
    assert bot_msg.text == done_event["data"]["text"]
    assert bot_msg.moderation_status == MessageModerationStatus.PASSED

    # Нормативные источники регламентов
    assert len(bot_msg.sources) == len(sources_list)
    assert (
        bot_msg.sources[0].chunk_id == "chunk_portal_zakupki_reglament_sec4_p1"
    )
    assert bot_msg.sources[0].doc_id == "DOC_PORTAL_REGULATION_V6"

    # 3. Проверка ключей и данных в Redis
    stored_redis_messages = await redis_context.get_messages(ticket.id)
    assert len(stored_redis_messages) == 2
    assert stored_redis_messages[0]["sender"] == "client"
    assert stored_redis_messages[0]["text"] == client_question
    assert stored_redis_messages[1]["sender"] == "bot"
    assert stored_redis_messages[1]["text"] == done_event["data"]["text"]

    ttl = await redis_context.get_ttl(ticket.id)
    assert 1700 <= ttl <= 1800

    # Очистка контекста Redis
    await redis_context.clear_context(ticket.id)


async def test_send_message_consecutive_messages_reuse_active_ticket(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
    redis_context: RedisChatContext,
) -> None:
    """Проверяет связывание последующих сообщений с уже открытым активным тикетом."""
    # Первое сообщение клиента
    resp1 = await client.post(
        "/api/v1/chat/messages",
        json={"text": "Первый вопрос по регламенту"},
        headers=auth_headers,
    )
    assert resp1.status_code == status.HTTP_200_OK

    # Второе сообщение клиента в той же сессии
    resp2 = await client.post(
        "/api/v1/chat/messages",
        json={"text": "Уточняющий вопрос к предыдущему ответу"},
        headers=auth_headers,
    )
    assert resp2.status_code == status.HTTP_200_OK

    # Проверяем, что в БД ровно один тикет
    chat = await test_session.scalar(
        select(ChatModel).where(ChatModel.client_id == client_user.id)
    )
    assert chat is not None

    tickets = (
        await test_session.scalars(
            select(TicketModel).where(TicketModel.chat_id == chat.id)
        )
    ).all()
    assert len(tickets) == 1
    ticket = tickets[0]

    # В обращении должно быть 4 сообщения (клиент 1, бот 1, клиент 2, бот 2)
    messages = (
        await test_session.scalars(
            select(MessageModel)
            .where(MessageModel.ticket_id == ticket.id)
            .order_by(MessageModel.created_at.asc())
        )
    ).all()
    assert len(messages) == 4
    assert [m.sender_type for m in messages] == [
        "client",
        "bot",
        "client",
        "bot",
    ]

    # В Redis также накоплены 4 реплики
    stored_redis = await redis_context.get_messages(ticket.id)
    assert len(stored_redis) == 4
    assert [m["sender"] for m in stored_redis] == [
        "client",
        "bot",
        "client",
        "bot",
    ]

    await redis_context.clear_context(ticket.id)


async def test_chat_service_dependency_injection(
    redis_client: aioredis.Redis,
) -> None:
    """Проверяет корректное внедрение зависимостей сессии БД, репозиториев и Redis в ChatService."""
    async with async_session_maker() as session:
        rag_service = await get_rag_service()
        repo = await get_chat_repository(session=session)
        ticket_repo = await get_ticket_repository(session=session)
        redis_context = get_redis_context(redis=redis_client)
        ticket_events = get_redis_ticket_events(redis=redis_client)
        line_queue = get_redis_line_queue(redis=redis_client)

        service = await get_chat_service(
            repo=repo,
            session=session,
            rag_service=rag_service,
            ticket_repo=ticket_repo,
            redis_context=redis_context,
            ticket_events=ticket_events,
            line_queue=line_queue,
        )

        assert service.repo is repo
        assert service.session is session
        assert service.rag_service is rag_service
        assert service.ticket_repo is ticket_repo
        assert service.redis_context is redis_context
        assert service.ticket_events is ticket_events
        assert service.line_queue is line_queue
