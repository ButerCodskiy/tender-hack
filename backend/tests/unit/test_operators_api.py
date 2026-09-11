"""Модульные тесты REST API рабочего места оператора (HIGH-10)."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_current_user,
    get_operator_service,
    require_operator_user,
)
from src.api.v1.operators import router as operators_router
from src.auth.models import RoleModel, UserModel
from src.chat.schemas import MessageResponseSchema
from src.core.config import settings
from src.operators.schemas import (
    ClientInfoSchema,
    OperatorProfileResponseSchema,
    OperatorSidebarTicketSchema,
    OperatorTicketWorkspaceSchema,
    ResolveTicketResponseSchema,
    TransferTicketResponseSchema,
)
from src.operators.service import OperatorService


@pytest.fixture
def mock_operator_service() -> AsyncMock:
    """Создает мок сервиса операторов."""
    return AsyncMock(spec=OperatorService)


@pytest.fixture
def current_operator() -> UserModel:
    """Создает тестового пользователя с ролью оператора."""
    role = RoleModel(id=2, code="operator", name="Оператор")
    user = UserModel(
        id=uuid6.uuid7(),
        email="operator@zakupki.mos.ru",
        full_name="Иван Операторов",
        role_id=role.id,
    )
    user.role = role
    return user


@pytest.fixture
def test_app(
    mock_operator_service: AsyncMock, current_operator: UserModel
) -> FastAPI:
    """Создает тестовое приложение с переопределенными зависимостями."""
    app = FastAPI()
    app.include_router(operators_router, prefix="/api/v1")
    app.dependency_overrides[get_operator_service] = lambda: (
        mock_operator_service
    )
    app.dependency_overrides[require_operator_user] = lambda: current_operator
    app.dependency_overrides[get_current_user] = lambda: current_operator
    return app


@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncClient:
    """Предоставляет асинхронный HTTP-клиент."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_my_shift_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет GET /api/v1/operators/me/shift."""
    mock_operator_service.get_profile.return_value = (
        OperatorProfileResponseSchema(
            user_id=current_operator.id,
            full_name="Иван Операторов",
            line_id=1,
            line_code="L1",
            shift_status="active",
            max_slots=5,
            active_slots_count=1,
        )
    )

    response = await api_client.get("/api/v1/operators/me/shift")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["shift_status"] == "active"
    assert data["line_code"] == "L1"
    assert data["active_slots_count"] == 1
    mock_operator_service.get_profile.assert_awaited_once_with(
        current_operator.id
    )


@pytest.mark.asyncio
async def test_patch_my_shift_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет PATCH /api/v1/operators/me/shift."""
    mock_operator_service.update_shift.return_value = (
        OperatorProfileResponseSchema(
            user_id=current_operator.id,
            full_name="Иван Операторов",
            line_id=1,
            line_code="L1",
            shift_status="break",
            max_slots=5,
            active_slots_count=1,
        )
    )

    response = await api_client.patch(
        "/api/v1/operators/me/shift",
        json={"shift_status": "break"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["shift_status"] == "break"
    mock_operator_service.update_shift.assert_awaited_once_with(
        current_operator.id, "break"
    )


@pytest.mark.asyncio
async def test_get_my_tickets_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет GET /api/v1/operators/tickets."""
    ticket_id = uuid6.uuid7()
    chat_id = uuid6.uuid7()
    mock_operator_service.get_sidebar_tickets.return_value = [
        OperatorSidebarTicketSchema(
            ticket_id=ticket_id,
            chat_id=chat_id,
            priority="P1",
            status="in_progress",
            line_code="L1",
            client_name="Петр Клиентов",
            company_name="ООО «Поставщик»",
            last_message_preview="Помогите с ЭП",
            unread_messages_count=2,
            created_at=datetime.now(settings.TIMEZONE),
            assigned_at=datetime.now(settings.TIMEZONE),
        )
    ]

    response = await api_client.get("/api/v1/operators/tickets")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["ticket_id"] == str(ticket_id)
    assert data[0]["unread_messages_count"] == 2
    mock_operator_service.get_sidebar_tickets.assert_awaited_once_with(
        current_operator.id
    )


@pytest.mark.asyncio
async def test_open_ticket_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/open."""
    ticket_id = uuid6.uuid7()
    chat_id = uuid6.uuid7()
    mock_operator_service.open_ticket.return_value = (
        OperatorTicketWorkspaceSchema(
            ticket_id=ticket_id,
            chat_id=chat_id,
            priority="P1",
            status="in_progress",
            line_code="L1",
            transfer_comment=None,
            client=ClientInfoSchema(
                company_name="ООО «Поставщик»",
                inn="7701234567",
                kpp="770101001",
                phone="+79991234567",
                full_name="Петр Клиентов",
                email="client@zakupki.mos.ru",
            ),
            copilot_summary=None,
            messages=[],
        )
    )

    response = await api_client.post(
        f"/api/v1/operators/tickets/{ticket_id}/open"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["ticket_id"] == str(ticket_id)
    assert data["status"] == "in_progress"
    assert data["client"]["inn"] == "7701234567"
    mock_operator_service.open_ticket.assert_awaited_once_with(
        current_operator.id, ticket_id
    )


@pytest.mark.asyncio
async def test_send_message_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/messages."""
    ticket_id = uuid6.uuid7()
    msg_id = uuid6.uuid7()
    mock_operator_service.send_message.return_value = MessageResponseSchema(
        id=msg_id,
        ticket_id=ticket_id,
        sender_type="operator",
        sender_id=current_operator.id,
        text="Протокол разногласий принят.",
        moderation_status="passed",
        sources=[],
        created_at=datetime.now(settings.TIMEZONE),
    )

    response = await api_client.post(
        f"/api/v1/operators/tickets/{ticket_id}/messages",
        json={"text": "Протокол разногласий принят."},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] == str(msg_id)
    assert data["sender_type"] == "operator"
    mock_operator_service.send_message.assert_awaited_once_with(
        current_operator.id, ticket_id, "Протокол разногласий принят."
    )


@pytest.mark.asyncio
async def test_transfer_ticket_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/transfer."""
    ticket_id = uuid6.uuid7()
    mock_operator_service.transfer_ticket.return_value = (
        TransferTicketResponseSchema(
            status="queued",
            ticket_id=ticket_id,
            line_code="L2",
        )
    )

    response = await api_client.post(
        f"/api/v1/operators/tickets/{ticket_id}/transfer",
        json={
            "target_line_code": "L2",
            "transfer_comment": "Требуется проверка криптографии",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "queued"
    assert data["line_code"] == "L2"
    mock_operator_service.transfer_ticket.assert_awaited_once_with(
        current_operator.id,
        ticket_id,
        "L2",
        "Требуется проверка криптографии",
    )


@pytest.mark.asyncio
async def test_resolve_ticket_endpoint(
    api_client: AsyncClient,
    mock_operator_service: AsyncMock,
    current_operator: UserModel,
) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/resolve."""
    ticket_id = uuid6.uuid7()
    closed_at = datetime.now(settings.TIMEZONE)
    mock_operator_service.resolve_ticket.return_value = (
        ResolveTicketResponseSchema(
            status="resolved",
            ticket_id=ticket_id,
            closed_at=closed_at,
        )
    )

    response = await api_client.post(
        f"/api/v1/operators/tickets/{ticket_id}/resolve"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "resolved"
    assert data["ticket_id"] == str(ticket_id)
    mock_operator_service.resolve_ticket.assert_awaited_once_with(
        current_operator.id, ticket_id
    )
