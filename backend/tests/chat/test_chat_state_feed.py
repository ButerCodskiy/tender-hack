"""Интеграционные тесты эндпоинта состояния переписки и истории клиента GET /api/v1/chat."""

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import uuid6
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.models import RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageSenderType,
    MessageSourceModel,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.core.config import settings
from src.core.security import create_access_token
from src.main import app
from src.operators.models import SupportLineModel


@pytest.fixture
async def test_session(async_session: AsyncSession) -> AsyncSession:
    """Предоставляет изолированную сессию базы данных PostgreSQL с откатом изменений."""
    return async_session


@pytest.fixture
async def client(
    test_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """Создает тестовый HTTP-клиент с изолированной сессией базы данных."""

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
    stmt_role = select(RoleModel).where(RoleModel.code == "client")
    role = (await test_session.scalars(stmt_role)).first()
    if not role:
        role = RoleModel(code="client", name="Клиент")
        test_session.add(role)
        await test_session.flush()

    user = UserModel(
        email=f"test_client_{uuid6.uuid7().hex[:8]}@zakupki.mos.ru",
        password_hash="fake_hash",
        full_name="Иван Клиентов",
        role_id=role.id,
    )
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(client_user: UserModel) -> dict[str, str]:
    """Формирует заголовки авторизации с валидным Bearer-токеном."""
    token = create_access_token(user_id=client_user.id, role_code="client")
    return {"Authorization": f"Bearer {token}"}


async def test_get_chat_state_new_user(
    client: AsyncClient,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет состояние чата нового пользователя без обращений и сообщений."""
    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "chat_id" in data
    assert data["active_ticket"] is None
    assert data["messages"] == []
    assert data["can_escalate"] is False
    assert data["can_cancel"] is False
    assert data["can_feedback"] is False
    assert data["feedback_ticket_id"] is None


async def test_get_chat_state_active_bot_processing(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет флаги доступных действий при активном тикете на этапе бота."""
    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        priority=TicketPriority.P2,
        status=TicketStatus.BOT_PROCESSING,
    )
    test_session.add(ticket)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["chat_id"] == str(chat.id)
    assert data["active_ticket"] is not None
    assert data["active_ticket"]["id"] == str(ticket.id)
    assert data["active_ticket"]["status"] == TicketStatus.BOT_PROCESSING
    assert data["active_ticket"]["priority"] == TicketPriority.P2
    assert data["active_ticket"]["assigned_operator_name"] is None
    assert data["active_ticket"]["line_code"] is None
    assert data["can_escalate"] is True
    assert data["can_cancel"] is False
    assert data["can_feedback"] is False
    assert data["feedback_ticket_id"] is None


async def test_get_chat_state_active_queued(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет флаг отмены тикета при нахождении обращения в очереди."""
    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        status=TicketStatus.QUEUED,
    )
    test_session.add(ticket)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["can_escalate"] is False
    assert data["can_cancel"] is True
    assert data["can_feedback"] is False


async def test_get_chat_state_assigned_with_operator_and_line(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    stmt_op_role = select(RoleModel).where(RoleModel.code == "operator")
    operator_role = (await test_session.scalars(stmt_op_role)).first()
    if not operator_role:
        operator_role = RoleModel(code="operator", name="Оператор")
        test_session.add(operator_role)
        await test_session.flush()

    operator = UserModel(
        email=f"operator_anna_{uuid6.uuid7().hex[:8]}@zakupki.mos.ru",
        password_hash="fake_hash",
        full_name="Анна Смирнова",
        role_id=operator_role.id,
    )
    test_session.add(operator)

    stmt_line = select(SupportLineModel).where(SupportLineModel.code == "L1")
    line = (await test_session.scalars(stmt_line)).first()
    if not line:
        line = SupportLineModel(code="L1", name="Первая линия")
        test_session.add(line)
        await test_session.flush()

    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=operator.id,
        priority=TicketPriority.P1,
        status=TicketStatus.IN_PROGRESS,
    )
    test_session.add(ticket)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    active_ticket = data["active_ticket"]
    assert active_ticket is not None
    assert active_ticket["id"] == str(ticket.id)
    assert active_ticket["assigned_operator_name"] == "Анна Смирнова"
    assert active_ticket["line_code"] == "L1"
    assert active_ticket["priority"] == "P1"
    assert active_ticket["status"] == "in_progress"
    assert data["can_escalate"] is False
    assert data["can_cancel"] is False
    assert data["can_feedback"] is False


async def test_get_chat_state_resolved_awaits_feedback(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет выставление флагов оценки при завершенном обращении."""
    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        status=TicketStatus.RESOLVED,
        closed_at=datetime.now(settings.TIMEZONE),
    )
    test_session.add(ticket)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["active_ticket"] is None
    assert data["can_escalate"] is False
    assert data["can_cancel"] is False
    assert data["can_feedback"] is True
    assert data["feedback_ticket_id"] == str(ticket.id)


async def test_get_chat_state_messages_feed_and_sources(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет хронологическую ленту сообщений с прикрепленными источниками регламентов."""
    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        status=TicketStatus.BOT_PROCESSING,
    )
    test_session.add(ticket)
    await test_session.flush()

    msg_client = MessageModel(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.CLIENT,
        sender_id=client_user.id,
        text="Как подписать протокол разногласий?",
    )
    test_session.add(msg_client)
    await test_session.flush()

    msg_bot = MessageModel(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.BOT,
        text="Протокол разногласий подписывается в течение 5 рабочих дней.",
    )
    test_session.add(msg_bot)
    await test_session.flush()

    source = MessageSourceModel(
        message_id=msg_bot.id,
        chunk_id="chunk_portal_sec4",
        doc_id="DOC_PORTAL_REGULATION",
        quote_text="Участник закупки вправе сформировать протокол разногласий...",
    )
    test_session.add(source)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["id"] == str(msg_client.id)
    assert messages[0]["sender_type"] == "client"
    assert messages[0]["text"] == "Как подписать протокол разногласий?"
    assert messages[0]["sources"] == []

    assert messages[1]["id"] == str(msg_bot.id)
    assert messages[1]["sender_type"] == "bot"
    assert len(messages[1]["sources"]) == 1
    assert messages[1]["sources"][0]["chunk_id"] == "chunk_portal_sec4"
    assert messages[1]["sources"][0]["doc_id"] == "DOC_PORTAL_REGULATION"
    assert (
        messages[1]["sources"][0]["quote_text"]
        == "Участник закупки вправе сформировать протокол разногласий..."
    )


async def test_get_chat_state_messages_feed_limit_50(
    client: AsyncClient,
    test_session: AsyncSession,
    client_user: UserModel,
    auth_headers: dict[str, str],
) -> None:
    """Проверяет ограничение ленты до 50 сообщений и сохранение хронологии."""
    chat = ChatModel(client_id=client_user.id)
    test_session.add(chat)
    await test_session.flush()

    ticket = TicketModel(
        chat_id=chat.id,
        status=TicketStatus.BOT_PROCESSING,
    )
    test_session.add(ticket)
    await test_session.flush()

    for i in range(60):
        msg = MessageModel(
            ticket_id=ticket.id,
            sender_type=MessageSenderType.CLIENT,
            text=f"Сообщение {i:02d}",
        )
        test_session.add(msg)
    await test_session.commit()

    response = await client.get("/api/v1/chat", headers=auth_headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    messages = data["messages"]
    assert len(messages) == 50
    # Последние 50 сообщений из 60 — это номера 10..59 в хронологическом порядке
    assert messages[0]["text"] == "Сообщение 10"
    assert messages[-1]["text"] == "Сообщение 59"


async def test_get_chat_state_unauthorized(client: AsyncClient) -> None:
    """Проверяет возврат 401 Unauthorized при отсутствии или невалидности токена."""
    # Запрос без заголовка Authorization
    resp_no_token = await client.get("/api/v1/chat")
    assert resp_no_token.status_code == status.HTTP_401_UNAUTHORIZED

    # Запрос с невалидным токеном
    resp_bad_token = await client.get(
        "/api/v1/chat",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp_bad_token.status_code == status.HTTP_401_UNAUTHORIZED
