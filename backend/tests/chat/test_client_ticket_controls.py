"""Тесты клиентских эндпоинтов управления обращением: escalate, resolve, cancel и feedback (HIGH-15)."""

from collections.abc import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_analytics_service,
    get_auth_service,
    get_chat_service,
)
from src.api.v1.chat import router as chat_router
from src.auth.models import RoleModel, UserModel
from src.auth.service import AuthService
from src.chat.schemas import (
    ActiveTicketSummarySchema,
    CancelTicketResponseSchema,
    ClientResolveTicketResponseSchema,
)
from src.chat.service import ChatService
from src.core.config import settings


@pytest.fixture
def test_client_user() -> UserModel:
    """Создает объект тестового пользователя с ролью клиента."""
    return UserModel(
        id=uuid6.uuid7(),
        email="test_client_controls@zakupki.mos.ru",
        password_hash="fake",
        full_name="Тестовый Заказчик",
        role=RoleModel(id=1, code="client", name="Клиент"),
        is_active=True,
    )


@pytest.fixture
def mock_auth_service(test_client_user: UserModel) -> AsyncMock:
    """Создает мок AuthService для валидации токенов клиента."""
    service = AsyncMock(spec=AuthService)
    service.get_user_by_token.return_value = test_client_user
    return service


@pytest.fixture
def mock_chat_service() -> AsyncMock:
    """Создает мок ChatService для эндпоинтов чата."""
    return AsyncMock(spec=ChatService)


@pytest.fixture
def mock_analytics_service() -> AsyncMock:
    """Создает мок AnalyticsService для эндпоинта обратной связи."""
    return AsyncMock()


@pytest.fixture
def test_app(
    mock_auth_service: AsyncMock,
    mock_chat_service: AsyncMock,
    mock_analytics_service: AsyncMock,
) -> FastAPI:
    """Создает изолированное приложение FastAPI с переопределенными зависимостями."""
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service
    )
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Предоставляет HTTP-клиент с изолированным транспортом."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer mock_token"},
    ) as client:
        yield client


async def test_escalate_endpoint(
    api_client: AsyncClient,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет эндпоинт ручного вызова оператора POST /api/v1/chat/escalate."""
    ticket_id = uuid6.uuid7()
    now = datetime.now(settings.TIMEZONE)
    mock_chat_service.escalate_ticket.return_value = ActiveTicketSummarySchema(
        id=ticket_id,
        priority="P2",
        status="queued",
        line_code="L1",
        assigned_operator_name=None,
        created_at=now,
    )

    response = await api_client.post(
        "/api/v1/chat/escalate",
        json={"reason": "Нужна консультация человека"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(ticket_id)
    assert data["status"] == "queued"
    assert data["line_code"] == "L1"


async def test_resolve_ticket_endpoint(
    api_client: AsyncClient,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет эндпоинт подтверждения решения POST /api/v1/chat/tickets/{id}/resolve."""
    ticket_id = uuid6.uuid7()
    now = datetime.now(settings.TIMEZONE)
    mock_chat_service.resolve_ticket_by_client.return_value = (
        ClientResolveTicketResponseSchema(
            status="resolved",
            ticket_id=ticket_id,
            closed_at=now,
        )
    )

    response = await api_client.post(
        f"/api/v1/chat/tickets/{ticket_id}/resolve"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "resolved"
    assert data["ticket_id"] == str(ticket_id)


async def test_cancel_ticket_endpoint(
    api_client: AsyncClient,
    mock_chat_service: AsyncMock,
) -> None:
    """Проверяет эндпоинт отмены обращения клиентом POST /api/v1/chat/tickets/{id}/cancel."""
    ticket_id = uuid6.uuid7()
    mock_chat_service.cancel_ticket_by_client.return_value = (
        CancelTicketResponseSchema(
            status="canceled",
            ticket_id=ticket_id,
        )
    )

    response = await api_client.post(
        f"/api/v1/chat/tickets/{ticket_id}/cancel"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "canceled"
    assert data["ticket_id"] == str(ticket_id)


async def test_create_feedback_endpoint(
    api_client: AsyncClient,
    mock_analytics_service: AsyncMock,
) -> None:
    """Проверяет эндпоинт отправки оценки и отзыва POST /api/v1/chat/tickets/{id}/feedback."""
    ticket_id = uuid6.uuid7()
    now = datetime.now(settings.TIMEZONE)
    mock_analytics_service.save_feedback.return_value = {
        "id": str(uuid6.uuid7()),
        "ticket_id": str(ticket_id),
        "score": 5,
        "comment": "Отличный ответ!",
        "created_at": now.isoformat(),
    }

    response = await api_client.post(
        f"/api/v1/chat/tickets/{ticket_id}/feedback",
        json={"score": 5, "comment": "Отличный ответ!"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["score"] == 5
    assert data["comment"] == "Отличный ответ!"
