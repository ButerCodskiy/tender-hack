"""Интеграционные и модульные тесты постоянного потока событий клиента GET /api/v1/chat/events (HIGH-11)."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
import uuid6
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_auth_service,
    get_chat_service,
)
from src.api.v1.chat import router as chat_router
from src.auth.models import RoleModel, UserModel
from src.auth.service import AuthService
from src.chat.models import (
    ChatModel,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.repository import ChatRepository, TicketRepository
from src.chat.service import ChatService
from src.core.redis_client import RedisTicketEvents


@pytest.fixture
def mock_auth_service() -> AsyncMock:
    """Создает мок AuthService для валидации токенов."""
    service = AsyncMock(spec=AuthService)
    user = UserModel(
        id=uuid6.uuid7(),
        email="client_sse@zakupki.mos.ru",
        password_hash="fake",
        full_name="Тест Клиент",
        role=RoleModel(id=1, code="client", name="Клиент"),
        is_active=True,
    )
    service.get_user_by_token.return_value = user
    return service


@pytest.fixture
def mock_chat_service() -> AsyncMock:
    """Создает мок ChatService для эндпоинта /chat/events."""
    service = AsyncMock(spec=ChatService)
    return service


@pytest.fixture
def test_app(
    mock_auth_service: AsyncMock, mock_chat_service: AsyncMock
) -> FastAPI:
    """Создает изолированное приложение FastAPI с переопределенными зависимостями."""
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Предоставляет HTTP-клиент с изолированным транспортом."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


# =====================================================================
# 1. Тесты аутентификации SSE (заголовок vs query param ?token=)
# =====================================================================


async def test_chat_events_missing_token_returns_401(
    api_client: AsyncClient,
) -> None:
    """Проверяет отклонение запроса без токена с кодом 401 not_authenticated."""
    response = await api_client.get("/api/v1/chat/events")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert data["detail"]["code"] == "not_authenticated"


async def test_chat_events_auth_via_query_token(
    api_client: AsyncClient,
    mock_auth_service: AsyncMock,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет успешную аутентификацию через query-параметр ?token=."""

    async def _dummy_stream(
        user: UserModel, ticket_id: UUID | None, request, *args, **kwargs
    ) -> AsyncGenerator[str, None]:
        yield 'event: operator_joined\ndata: {"operator_name": "Анна"}\n\n'

    mock_chat_service.stream_chat_events = _dummy_stream

    response = await api_client.get(
        "/api/v1/chat/events?token=valid_access_token"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: operator_joined" in response.text
    mock_auth_service.get_user_by_token.assert_awaited_once_with(
        "valid_access_token"
    )


async def test_chat_events_auth_via_bearer_header(
    api_client: AsyncClient,
    mock_auth_service: AsyncMock,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет успешную аутентификацию через заголовок Authorization: Bearer <token>."""

    async def _dummy_stream(
        user: UserModel, ticket_id: UUID | None, request, *args, **kwargs
    ) -> AsyncGenerator[str, None]:
        yield 'event: ticket_resolved\ndata: {"status": "resolved"}\n\n'

    mock_chat_service.stream_chat_events = _dummy_stream

    headers = {"Authorization": "Bearer header_token_123"}
    response = await api_client.get("/api/v1/chat/events", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: ticket_resolved" in response.text
    mock_auth_service.get_user_by_token.assert_awaited_once_with(
        "header_token_123"
    )


# =====================================================================
# 2. Тесты логики эндпоинта /chat/events (404 no active ticket, 403)
# =====================================================================


async def test_chat_events_no_active_ticket_404(
    api_client: AsyncClient,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет возврат 404, если у клиента нет активного обращения."""
    mock_chat_service.stream_chat_events.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "no_active_ticket",
            "message": "Активное обращение не найдено",
        },
    )

    response = await api_client.get(
        "/api/v1/chat/events?token=valid_client_token"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"]["code"] == "no_active_ticket"


async def test_chat_events_alien_ticket_forbidden_403(
    api_client: AsyncClient,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет возврат 403 при попытке прослушивания чужого обращения."""
    alien_id = uuid6.uuid7()
    mock_chat_service.stream_chat_events.side_effect = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Доступ к данному обращению запрещен",
    )

    response = await api_client.get(
        f"/api/v1/chat/events?token=valid_token&ticket_id={alien_id}"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "запрещен" in response.json()["detail"]


# =====================================================================
# 3. Юнит-тесты ChatService.stream_chat_events
# =====================================================================


async def test_chat_service_stream_chat_events_validation() -> None:
    """Проверяет валидацию чата и тикетов внутри ChatService.stream_chat_events."""
    user = UserModel(
        id=uuid6.uuid7(),
        email="client@mos.ru",
        password_hash="fake",
        full_name="Клиент",
    )
    chat = ChatModel(id=uuid6.uuid7(), client_id=user.id)
    ticket = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.P2,
    )

    repo = AsyncMock(spec=ChatRepository)
    repo.get_by_client_id.return_value = chat

    ticket_repo = AsyncMock(spec=TicketRepository)
    ticket_repo.get_active_by_chat_id.return_value = ticket

    ticket_events = MagicMock(spec=RedisTicketEvents)

    async def _mock_sub(ticket_id, request):
        yield f'event: operator_joined\ndata: {{"ticket_id": "{ticket_id}"}}\n\n'

    ticket_events.subscribe_ticket_events = _mock_sub

    service = ChatService(
        repo=repo,
        session=AsyncMock(),
        rag_service=AsyncMock(),
        ticket_repo=ticket_repo,
        ticket_events=ticket_events,
    )

    request = MagicMock()
    chunks = []
    async for chunk in service.stream_chat_events(
        user=user, ticket_id=None, request=request
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "event: operator_joined" in chunks[0]
    assert str(ticket.id) in chunks[0]


# =====================================================================
# 4. Юнит-тесты RedisTicketEvents.subscribe_ticket_events
# =====================================================================


async def test_redis_ticket_events_generator_and_ping() -> None:
    """Проверяет парсинг JSON-сообщений, отправку ping и очистку в finally."""
    fake_redis = AsyncMock()
    fake_pubsub = AsyncMock()
    fake_redis.pubsub = MagicMock(return_value=fake_pubsub)

    # Эмулируем 1 сообщение и затем завершение цикла
    ticket_id = uuid6.uuid7()
    test_msg = {
        "type": "message",
        "data": '{"event": "new_message", "data": {"text": "Привет!"}}',
    }
    fake_pubsub.get_message.side_effect = [
        test_msg,
        None,
    ]

    events_mgr = RedisTicketEvents(redis=fake_redis)

    # Имитируем запрос, который отключается на 2-й итерации
    request_mock = AsyncMock()
    request_mock.is_disconnected.side_effect = [False, True]

    received = []
    async for chunk in events_mgr.subscribe_ticket_events(
        ticket_id=ticket_id,
        request=request_mock,
        heartbeat_interval=0.01,
    ):
        received.append(chunk)

    assert len(received) >= 1
    assert "event: new_message" in received[0]
    assert "Привет!" in received[0]

    # Проверяем, что в finally вызван unsubscribe и close
    fake_pubsub.unsubscribe.assert_awaited_once_with(
        f"channel:ticket:{ticket_id}"
    )
    fake_pubsub.close.assert_awaited_once()
