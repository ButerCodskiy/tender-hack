"""Интеграционные и модульные тесты REST API аналитики и дашборда (MED-02)."""

from datetime import date
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from src.analytics.schemas import (
    AnalyticsDashboardResponseSchema,
    OperatorDailyMetricResponseSchema,
)
from src.analytics.service import AnalyticsService
from src.api.dependencies import get_analytics_service, get_current_user
from src.api.v1.analytics import router as analytics_router
from src.auth.models import RoleModel, UserModel, UserRole


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


@pytest.fixture
def mock_analytics_service() -> AsyncMock:
    """Создает мок сервиса аналитики."""
    mock = AsyncMock(spec=AnalyticsService)
    mock.get_dashboard.return_value = AnalyticsDashboardResponseSchema(
        total_tickets=45,
        bot_resolved_percent=60.0,
        bot_resolved_tickets=27,
        avg_first_response_time_sec=35.5,
        avg_handling_time_sec=210.0,
        client_csat=4.7,
        adjusted_csat=4.95,
        avg_ai_politeness_score=4.8,
        avg_ai_completeness_score=4.75,
        active_incidents_count=2,
    )
    mock.get_operator_metrics.return_value = [
        OperatorDailyMetricResponseSchema(
            operator_id=uuid6.uuid7(),
            operator_name="Иванов Иван",
            line_code="L1",
            metric_date=date(2026, 9, 10),
            total_tickets_handled=12,
            avg_first_response_time_sec=40.0,
            avg_handling_time_sec=250.0,
            avg_client_csat=4.8,
            avg_adjusted_csat=5.0,
            avg_ai_quality_score=4.9,
        )
    ]
    return mock


@pytest.fixture
def supervisor_app(mock_analytics_service: AsyncMock) -> FastAPI:
    """Приложение с авторизацией под ролью SUPERVISOR."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.SUPERVISOR.value
    )
    return app


@pytest.fixture
def admin_app(mock_analytics_service: AsyncMock) -> FastAPI:
    """Приложение с авторизацией под ролью ADMIN."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.ADMIN.value
    )
    return app


@pytest.fixture
def operator_app(mock_analytics_service: AsyncMock) -> FastAPI:
    """Приложение с авторизацией под ролью OPERATOR (доступ запрещен)."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.OPERATOR.value
    )
    return app


@pytest.fixture
def client_app(mock_analytics_service: AsyncMock) -> FastAPI:
    """Приложение с авторизацией под ролью CLIENT (доступ запрещен)."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.CLIENT.value
    )
    return app


@pytest.mark.asyncio
async def test_get_dashboard_as_supervisor(
    supervisor_app: FastAPI, mock_analytics_service: AsyncMock
) -> None:
    """Супервизор успешно получает данные сводного дашборда."""
    transport = ASGITransport(app=supervisor_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/analytics/dashboard?from_date=2026-09-01&to_date=2026-09-10"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_tickets"] == 45
        assert data["bot_resolved_percent"] == 60.0
        assert data["bot_resolved_tickets"] == 27
        assert data["adjusted_csat"] == 4.95

        mock_analytics_service.get_dashboard.assert_awaited_once_with(
            from_date=date(2026, 9, 1),
            to_date=date(2026, 9, 10),
        )


@pytest.mark.asyncio
async def test_get_dashboard_as_admin(
    admin_app: FastAPI, mock_analytics_service: AsyncMock
) -> None:
    """Администратор успешно получает данные сводного дашборда."""
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/analytics/dashboard")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_tickets"] == 45


@pytest.mark.asyncio
async def test_get_operator_metrics_as_supervisor(
    supervisor_app: FastAPI, mock_analytics_service: AsyncMock
) -> None:
    """Супервизор успешно получает суточные показатели операторов с фильтрами."""
    transport = ASGITransport(app=supervisor_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/analytics/operators?date=2026-09-10&line_code=L1"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["operator_name"] == "Иванов Иван"
        assert data[0]["line_code"] == "L1"

        mock_analytics_service.get_operator_metrics.assert_awaited_once_with(
            target_date=date(2026, 9, 10),
            line_code="L1",
        )


@pytest.mark.asyncio
async def test_rbac_forbidden_for_operator_and_client(
    operator_app: FastAPI, client_app: FastAPI
) -> None:
    """Операторам и клиентам доступ к аналитике запрещен (403 Forbidden)."""
    # 1. Оператор
    transport_op = ASGITransport(app=operator_app)
    async with AsyncClient(
        transport=transport_op, base_url="http://test"
    ) as ac:
        resp_dash = await ac.get("/api/v1/analytics/dashboard")
        assert resp_dash.status_code == status.HTTP_403_FORBIDDEN

        resp_ops = await ac.get("/api/v1/analytics/operators")
        assert resp_ops.status_code == status.HTTP_403_FORBIDDEN

    # 2. Клиент
    transport_cl = ASGITransport(app=client_app)
    async with AsyncClient(
        transport=transport_cl, base_url="http://test"
    ) as ac:
        resp_dash = await ac.get("/api/v1/analytics/dashboard")
        assert resp_dash.status_code == status.HTTP_403_FORBIDDEN

        resp_ops = await ac.get("/api/v1/analytics/operators")
        assert resp_ops.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_unauthorized_without_auth() -> None:
    """Без авторизации возвращается 401 Unauthorized."""
    unauth_app = FastAPI()
    unauth_app.include_router(analytics_router, prefix="/api/v1")

    transport = ASGITransport(app=unauth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/analytics/dashboard")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
