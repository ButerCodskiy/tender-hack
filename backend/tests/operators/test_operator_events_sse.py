"""Интеграционные и модульные тесты потока событий оператора GET /api/v1/operators/events (HIGH-11)."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_auth_service,
    get_operator_service,
)
from src.api.v1.operators import router as operators_router
from src.auth.models import RoleModel, UserModel
from src.auth.service import AuthService
from src.core.redis_client import RedisOperatorEvents
from src.operators.repository import OperatorRepository
from src.operators.service import OperatorService


@pytest.fixture
def mock_auth_service() -> AsyncMock:
    """Создает мок AuthService для валидации токенов оператора."""
    service = AsyncMock(spec=AuthService)
    operator = UserModel(
        id=uuid6.uuid7(),
        email="op_sse@zakupki.mos.ru",
        password_hash="fake",
        full_name="Тест Оператор",
        role=RoleModel(id=2, code="operator", name="Оператор"),
        is_active=True,
    )
    service.get_user_by_token.return_value = operator
    return service


@pytest.fixture
def mock_operator_service() -> AsyncMock:
    """Создает мок OperatorService для эндпоинта /operators/events."""
    service = AsyncMock(spec=OperatorService)
    return service


@pytest.fixture
def test_app(
    mock_auth_service: AsyncMock, mock_operator_service: AsyncMock
) -> FastAPI:
    """Создает изолированное приложение FastAPI с переопределенными зависимостями."""
    app = FastAPI()
    app.include_router(operators_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_operator_service] = lambda: (
        mock_operator_service
    )
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
# 1. Тесты аутентификации SSE для операторов (401, 403, 200)
# =====================================================================


async def test_operator_events_missing_token_returns_401(
    api_client: AsyncClient,
) -> None:
    """Проверяет отклонение запроса без токена с кодом 401."""
    response = await api_client.get("/api/v1/operators/events")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_operator_events_client_role_forbidden_403(
    api_client: AsyncClient,
    mock_auth_service: AsyncMock,
) -> None:
    """Проверяет запрет доступа для пользователя с ролью client (403 Forbidden)."""
    client_user = UserModel(
        id=uuid6.uuid7(),
        email="regular_client@mos.ru",
        password_hash="fake",
        full_name="Клиент",
        role=RoleModel(id=1, code="client", name="Клиент"),
        is_active=True,
    )
    mock_auth_service.get_user_by_token.return_value = client_user

    response = await api_client.get(
        "/api/v1/operators/events?token=client_access_token"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    detail = response.json()["detail"]
    assert detail["code"] == "access_denied"
    assert "Доступ разрешен только операторам" in detail["message"]


async def test_operator_events_auth_via_query_token_success(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
) -> None:
    """Проверяет успешное подключение оператора через ?token=."""

    async def _dummy_stream(
        operator_id: UUID, request
    ) -> AsyncGenerator[str, None]:
        yield 'event: ticket_assigned\ndata: {"ticket_id": "123"}\n\n'

    mock_operator_service.stream_operator_events = _dummy_stream

    response = await api_client.get(
        "/api/v1/operators/events?token=op_valid_token"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: ticket_assigned" in response.text


async def test_operator_events_auth_via_bearer_header_success(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
) -> None:
    """Проверяет успешное подключение оператора через заголовок Authorization: Bearer."""

    async def _dummy_stream(
        operator_id: UUID, request
    ) -> AsyncGenerator[str, None]:
        yield 'event: copilot_ready\ndata: {"hint": "Регламент 44-ФЗ"}\n\n'

    mock_operator_service.stream_operator_events = _dummy_stream

    headers = {"Authorization": "Bearer op_header_token"}
    response = await api_client.get(
        "/api/v1/operators/events", headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: copilot_ready" in response.text


# =====================================================================
# 2. Юнит-тесты логики счетчика соединений и disconnected_at в OperatorService
# =====================================================================


async def test_operator_service_multi_tab_disconnect_counter() -> None:
    """Проверяет, что disconnected_at выставляется ТОЛЬКО когда закрыты все вкладки (счетчик <= 0)."""
    fake_session = AsyncMock()
    fake_redis = AsyncMock()
    fake_events = AsyncMock(spec=RedisOperatorEvents)
    fake_repo = AsyncMock(spec=OperatorRepository)

    service = OperatorService(
        session=fake_session,
        redis=fake_redis,
        operator_repo=fake_repo,
        redis_events=fake_events,
    )
    operator_id = uuid6.uuid7()

    # 1. Первая вкладка открылась: счетчик = 1 -> mark_connected вызван
    fake_events.incr_operator_connections.return_value = 1
    await service.handle_operator_connect(operator_id)
    fake_events.incr_operator_connections.assert_awaited_once_with(operator_id)
    fake_repo.mark_connected.assert_awaited_once_with(operator_id)

    # 2. Вторая вкладка открылась: счетчик = 2 -> mark_connected вызван повторно
    fake_events.incr_operator_connections.return_value = 2
    await service.handle_operator_connect(operator_id)

    # 3. Закрытие 1-й вкладки: счетчик = 1 (> 0) -> mark_disconnected НЕ должен вызываться
    fake_events.decr_operator_connections.return_value = 1
    await service.handle_operator_disconnect(operator_id)
    fake_repo.mark_disconnected.assert_not_called()

    # 4. Закрытие 2-й вкладки (последней): счетчик = 0 -> mark_disconnected вызывается
    fake_events.decr_operator_connections.return_value = 0
    # Подменяем async_session_maker для изолированной сессии
    mock_cleanup_session = AsyncMock()
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = (
        mock_cleanup_session
    )
    mock_session_maker.return_value.__aexit__.return_value = None

    import src.operators.service as op_service_module

    original_maker = op_service_module.async_session_maker
    op_service_module.async_session_maker = mock_session_maker
    try:
        await service.handle_operator_disconnect(operator_id)
        mock_cleanup_session.commit.assert_awaited_once()
    finally:
        op_service_module.async_session_maker = original_maker


# =====================================================================
# 3. Юнит-тесты RedisOperatorEvents.subscribe_operator_events
# =====================================================================


async def test_redis_operator_events_generator_and_ping() -> None:
    """Проверяет чтение событий оператора, отправку ping и очистку в finally."""
    fake_redis = AsyncMock()
    fake_pubsub = AsyncMock()
    fake_redis.pubsub = MagicMock(return_value=fake_pubsub)

    operator_id = uuid6.uuid7()
    test_msg = {
        "type": "message",
        "data": '{"event": "ticket_assigned", "data": {"ticket_id": "xyz"}}',
    }
    fake_pubsub.get_message.side_effect = [
        test_msg,
        None,
    ]

    events_mgr = RedisOperatorEvents(redis=fake_redis)

    request_mock = AsyncMock()
    request_mock.is_disconnected.side_effect = [False, True]

    received = []
    async for chunk in events_mgr.subscribe_operator_events(
        operator_id=operator_id,
        request=request_mock,
        heartbeat_interval=0.01,
    ):
        received.append(chunk)

    assert len(received) >= 1
    assert "event: ticket_assigned" in received[0]
    assert "xyz" in received[0]

    # Проверяем обязательный unsubscribe и close в finally
    fake_pubsub.unsubscribe.assert_awaited_once_with(
        f"channel:operator:{operator_id}"
    )
    fake_pubsub.close.assert_awaited_once()
