"""Тесты реестра инцидентов и экспорта отчетов (MED-03)."""

import csv
import io
import json
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.analytics.models import (
    IncidentStatus,
    IncidentType,
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.repository import AnalyticsRepository
from src.analytics.schemas import (
    EXPORT_HEADERS,
    AnalyticsExportResponseSchema,
    AnalyticsExportRowSchema,
)
from src.analytics.service import AnalyticsService
from src.api.dependencies import get_analytics_service, get_current_user
from src.api.v1.analytics import router as analytics_router
from src.auth.models import RoleModel, UserModel, UserRole
from src.chat.models import TicketModel, TicketPriority, TicketStatus
from src.core.config import settings
from src.operators.models import SupportLineModel


def create_mock_user(role_code: str) -> UserModel:
    """Создает мок пользователя с указанной ролью."""
    return UserModel(
        id=uuid6.uuid7(),
        email=f"{role_code}@test.ru",
        password_hash="fake",
        full_name=f"Тестовый {role_code.capitalize()}",
        role=RoleModel(id=1, code=role_code, name=role_code.capitalize()),
        is_active=True,
    )


# --- 1. Тесты схем данных Pydantic ---


def test_export_row_schema_and_csv_serialization() -> None:
    """Проверяет валидацию строки экспорта и метод сериализации to_csv_list."""
    tid = uuid6.uuid7()
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=settings.TIMEZONE)
    closed = datetime(2026, 9, 10, 12, 5, 30, tzinfo=settings.TIMEZONE)

    row = AnalyticsExportRowSchema(
        ticket_id=tid,
        created_at=now,
        closed_at=closed,
        handling_time_sec=330,
        status="resolved",
        priority="P1",
        line_code="L2",
        assigned_operator_name="Анна Иванова",
        feedback_score=4,
        feedback_comment="Все отлично, спасибо!",
        is_system_issue=False,
        root_cause=None,
        politeness_score=5,
        completeness_score=4,
        audit_summary="Оператор предоставил полное решение",
    )

    csv_list = row.to_csv_list()

    # Число колонок в строке должно строго совпадать с заголовками экспорта (15)
    assert len(csv_list) == len(EXPORT_HEADERS) == 15
    assert csv_list[0] == str(tid)
    assert csv_list[1] == now.isoformat()
    assert csv_list[2] == closed.isoformat()
    assert csv_list[3] == "330"
    assert csv_list[4] == "resolved"
    assert csv_list[5] == "P1"
    assert csv_list[6] == "L2"
    assert csv_list[7] == "Анна Иванова"
    assert csv_list[8] == "4"
    assert csv_list[9] == "Все отлично, спасибо!"
    assert csv_list[10] == "False"
    assert csv_list[11] == ""  # None -> пустая строка
    assert csv_list[12] == "5"
    assert csv_list[13] == "4"
    assert csv_list[14] == "Оператор предоставил полное решение"


def test_export_row_schema_handles_all_nullable_fields() -> None:
    """Проверяет сериализацию в CSV при всех отсутствующих опциональных полях."""
    tid = uuid6.uuid7()
    now = datetime(2026, 9, 10, 10, 0, 0, tzinfo=settings.TIMEZONE)

    row = AnalyticsExportRowSchema(
        ticket_id=tid,
        created_at=now,
        closed_at=None,
        handling_time_sec=None,
        status="closed_by_inactivity",
        priority="P2",
        line_code=None,
        assigned_operator_name=None,
        feedback_score=None,
        feedback_comment=None,
        is_system_issue=None,
        root_cause=None,
        politeness_score=None,
        completeness_score=None,
        audit_summary=None,
    )

    csv_list = row.to_csv_list()
    assert len(csv_list) == 15
    assert csv_list[2] == ""
    assert csv_list[3] == ""
    assert csv_list[6] == ""
    assert csv_list[7] == ""
    assert csv_list[8] == ""
    assert csv_list[9] == ""


def test_export_response_json_schema() -> None:
    """Проверяет сериализацию схемы ответа JSON-экспорта."""
    tid = uuid6.uuid7()
    now = datetime(2026, 9, 10, 10, 0, 0, tzinfo=settings.TIMEZONE)

    item = AnalyticsExportRowSchema(
        ticket_id=tid,
        created_at=now,
        closed_at=None,
        handling_time_sec=None,
        status="resolved",
        priority="P0",
    )

    resp = AnalyticsExportResponseSchema(
        items=[item],
        total=1,
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 10),
    )

    data = json.loads(resp.model_dump_json())
    assert data["total"] == 1
    assert data["from_date"] == "2026-09-01"
    assert data["to_date"] == "2026-09-10"
    assert len(data["items"]) == 1
    assert data["items"][0]["ticket_id"] == str(tid)


# --- 2. Тесты сервисного слоя AnalyticsService ---


@pytest.mark.asyncio
async def test_service_get_incidents_success_and_validation() -> None:
    """Проверяет валидацию фильтров и вызов репозитория в get_incidents."""
    mock_repo = AsyncMock(spec=AnalyticsRepository)
    incident_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()
    now = datetime.now(settings.TIMEZONE)

    mock_incident = SystemIncidentModel(
        id=incident_id,
        ticket_id=ticket_id,
        incident_type=IncidentType.PORTAL_DOWNTIME.value,
        description="Сбой авторизации",
        status=IncidentStatus.OPEN.value,
        created_at=now,
        resolved_at=None,
    )
    mock_repo.get_incidents.return_value = [mock_incident]

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    # 1. Успешный вызов с корректными параметрами
    result = await service.get_incidents(
        status=IncidentStatus.OPEN.value,
        incident_type=IncidentType.PORTAL_DOWNTIME.value,
        limit=20,
        offset=5,
    )
    assert len(result) == 1
    assert result[0].id == incident_id
    mock_repo.get_incidents.assert_awaited_once_with(
        status="open",
        incident_type="portal_downtime",
        limit=20,
        offset=5,
    )

    # 2. Недопустимый incident_type -> HTTP 422
    with pytest.raises(Exception) as exc_info:
        await service.get_incidents(incident_type="invalid_type")
    assert "Неизвестный тип инцидента" in str(exc_info.value)

    # 3. Недопустимый status -> HTTP 422
    with pytest.raises(Exception) as exc_info:
        await service.get_incidents(status="invalid_status")
    assert "Неизвестный статус инцидента" in str(exc_info.value)


@pytest.mark.asyncio
async def test_service_generate_export_csv() -> None:
    """Проверяет генерацию CSV: utf-8-sig с BOM, заголовок, экранирование."""
    mock_repo = AsyncMock(spec=AnalyticsRepository)

    ticket_id = uuid6.uuid7()
    op_id = uuid6.uuid7()
    created_at = datetime(2026, 9, 5, 10, 0, 0, tzinfo=settings.TIMEZONE)
    closed_at = datetime(2026, 9, 5, 10, 15, 0, tzinfo=settings.TIMEZONE)

    ticket = TicketModel(
        id=ticket_id,
        chat_id=uuid6.uuid7(),
        line_id=1,
        assigned_operator_id=op_id,
        priority=TicketPriority.P1,
        status=TicketStatus.RESOLVED,
        created_at=created_at,
        closed_at=closed_at,
    )
    ticket.line = SupportLineModel(id=1, code="L1", name="Первая линия")
    ticket.assigned_operator = UserModel(
        id=op_id,
        email="op@test.ru",
        password_hash="fake",
        full_name="Петров Петр",
    )
    ticket.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        score=5,
        comment='Отличный ответ, с "кавычками" и\nпереносом строки!',
        created_at=closed_at,
    )
    ticket.audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        politeness_score=5,
        completeness_score=5,
        root_cause="none",
        summary="Вопрос решен корректно, замечаний нет",
        is_system_issue=False,
        created_at=closed_at,
    )

    mock_repo.get_tickets_for_export.return_value = [ticket]

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    content_bytes, media_type = await service.generate_export(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 10),
        fmt="csv",
    )

    assert media_type == "text/csv"
    # Проверка UTF-8 BOM для корректного открытия в Microsoft Excel
    assert content_bytes.startswith(b"\xef\xbb\xbf")

    # Декодируем и парсим CSV
    text_content = content_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text_content)))

    # Первая строка — заголовок (15 колонок)
    assert reader[0] == EXPORT_HEADERS
    # Вторая строка — данные тикета
    assert len(reader) == 2
    assert reader[1][0] == str(ticket_id)
    assert reader[1][3] == "900"  # 15 минут = 900 секунд
    assert reader[1][6] == "L1"
    assert reader[1][7] == "Петров Петр"
    assert reader[1][8] == "5"
    assert 'с "кавычками" и\nпереносом' in reader[1][9]
    assert reader[1][10] == "False"


@pytest.mark.asyncio
async def test_service_generate_export_empty_tickets_csv() -> None:
    """Проверяет выгрузку CSV при отсутствии тикетов за период (возвращается заголовок)."""
    mock_repo = AsyncMock(spec=AnalyticsRepository)
    mock_repo.get_tickets_for_export.return_value = []

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    content_bytes, media_type = await service.generate_export(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 2),
        fmt="csv",
    )

    assert media_type == "text/csv"
    text_content = content_bytes.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text_content)))
    assert len(reader) == 1
    assert reader[0] == EXPORT_HEADERS


@pytest.mark.asyncio
async def test_service_generate_export_json() -> None:
    """Проверяет генерацию JSON-экспорта."""
    mock_repo = AsyncMock(spec=AnalyticsRepository)
    mock_repo.get_tickets_for_export.return_value = []

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    content_bytes, media_type = await service.generate_export(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 2),
        fmt="json",
    )

    assert media_type == "application/json"
    data = json.loads(content_bytes.decode("utf-8"))
    assert data["total"] == 0
    assert data["items"] == []
    assert data["from_date"] == "2026-09-01"
    assert data["to_date"] == "2026-09-02"


# --- 3. Интеграционные тесты API маршрутов /incidents и /export ---


@pytest.fixture
def mock_analytics_service_export() -> AsyncMock:
    """Мок сервиса аналитики для тестирования API."""
    mock = AsyncMock(spec=AnalyticsService)

    incident_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()
    mock.get_incidents.return_value = [
        SystemIncidentModel(
            id=incident_id,
            ticket_id=ticket_id,
            incident_type="portal_downtime",
            description="Сбой сервера",
            status="open",
            created_at=datetime.now(settings.TIMEZONE),
            resolved_at=None,
        )
    ]
    mock.generate_export.return_value = (
        b"\xef\xbb\xbfheader1,header2\n",
        "text/csv",
    )
    return mock


@pytest.fixture
def supervisor_api_app(mock_analytics_service_export: AsyncMock) -> FastAPI:
    """Приложение с авторизацией супервизора."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service_export
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.SUPERVISOR.value
    )
    return app


@pytest.fixture
def operator_api_app(mock_analytics_service_export: AsyncMock) -> FastAPI:
    """Приложение с авторизацией оператора (доступ закрыт)."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service_export
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.OPERATOR.value
    )
    return app


@pytest.mark.asyncio
async def test_api_get_incidents_success(supervisor_api_app: FastAPI) -> None:
    """Проверяет успешное получение списка инцидентов супервизором."""
    transport = ASGITransport(app=supervisor_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/incidents?status=open&incident_type=portal_downtime&limit=10&offset=0"
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["incident_type"] == "portal_downtime"
    assert data[0]["status"] == "open"


@pytest.mark.asyncio
async def test_api_get_incidents_invalid_limit(
    supervisor_api_app: FastAPI,
) -> None:
    """Проверяет валидацию пагинации limit > 100."""
    transport = ASGITransport(app=supervisor_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/analytics/incidents?limit=101")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_api_export_date_validation_inverted(
    supervisor_api_app: FastAPI,
) -> None:
    """Проверяет ошибку 422, если from_date > to_date."""
    transport = ASGITransport(app=supervisor_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/export?from_date=2026-09-10&to_date=2026-09-01&format=csv"
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_date_range"


@pytest.mark.asyncio
async def test_api_export_date_validation_exceeds_max_days(
    supervisor_api_app: FastAPI,
) -> None:
    """Проверяет ошибку 422, если диапазон превышает EXPORT_MAX_DAYS (90 дней)."""
    transport = ASGITransport(app=supervisor_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/export?from_date=2026-01-01&to_date=2026-06-01&format=csv"
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    detail = response.json()["detail"]
    assert detail["code"] == "date_range_too_large"


@pytest.mark.asyncio
async def test_api_export_csv_headers_and_disposition(
    supervisor_api_app: FastAPI, mock_analytics_service_export: AsyncMock
) -> None:
    """Проверяет заголовки ответа CSV: Content-Disposition, media_type."""
    transport = ASGITransport(app=supervisor_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/v1/analytics/export?from_date=2026-09-01&to_date=2026-09-10&format=csv"
        )

    assert response.status_code == status.HTTP_200_OK
    assert "text/csv" in response.headers["content-type"]
    assert (
        "attachment; filename=analytics_export_2026-09-01_2026-09-10.csv"
        in response.headers["content-disposition"]
    )
    mock_analytics_service_export.generate_export.assert_awaited_once_with(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 10),
        fmt="csv",
    )


@pytest.mark.asyncio
async def test_api_analytics_endpoints_forbidden_for_operators(
    operator_api_app: FastAPI,
) -> None:
    """Проверяет, что эндпоинты /incidents и /export недоступны операторам (403)."""
    transport = ASGITransport(app=operator_api_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        resp_incidents = await client.get("/api/v1/analytics/incidents")
        resp_export = await client.get(
            "/api/v1/analytics/export?from_date=2026-09-01&to_date=2026-09-10"
        )

    assert resp_incidents.status_code == status.HTTP_403_FORBIDDEN
    assert resp_export.status_code == status.HTTP_403_FORBIDDEN
