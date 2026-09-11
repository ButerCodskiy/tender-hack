"""Интеграционные и модульные тесты для отчета о системных проблемах (Критерий №4 хакатона)."""

from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
import uuid6
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.analytics.models import (
    IncidentType,
    RootCauseType,
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.repository import AnalyticsRepository
from src.analytics.schemas import (
    SystemicIssueItemSchema,
    SystemicIssuesReportResponseSchema,
    SystemicMetricsSummarySchema,
)
from src.analytics.service import AnalyticsService
from src.api.dependencies import get_analytics_service, get_current_user
from src.api.v1.analytics import router as analytics_router
from src.auth.models import RoleModel, UserModel, UserRole
from src.chat.models import (
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.core.config import settings
from src.operators.models import SupportLineModel


def create_mock_user(role_code: str) -> UserModel:
    """Создает мок пользователя с указанной ролью."""
    return UserModel(
        id=uuid6.uuid7(),
        email=f"{role_code}@test.ru",
        password_hash="fake_hash",
        full_name=f"Тестовый {role_code.capitalize()}",
        role=RoleModel(id=1, code=role_code, name=role_code.capitalize()),
        is_active=True,
    )


# --- 1. Тесты Pydantic-схем ---


def test_systemic_issues_schemas_valid() -> None:
    """Проверяет валидацию корректной схемы SystemicIssuesReportResponseSchema."""
    item = SystemicIssueItemSchema(
        title="Сбои плагина ЭЦП КриптоПро при подписании",
        evidence_count=14,
        affected_line="L2",
        suspected_cause="ui_defect / ошибка 0x80090016",
        examples=["Ошибка 0x80090016 при подписании оферты"],
        recommendation="Опубликовать инструкцию по переустановке плагина в FAQ",
    )
    metrics = SystemicMetricsSummarySchema(
        total_tickets=50,
        csat_score=0.82,
        deflection_rate=0.45,
        oqs_score=0.86,
    )
    report = SystemicIssuesReportResponseSchema(
        period="2026-09-01 - 2026-09-12",
        summary="Аналитический отчет выявил ключевые сложности с плагином ЭЦП.",
        systemic_issues=[item],
        metrics_summary=metrics,
        positive_patterns=["Высокая скорость бота"],
    )

    assert report.period == "2026-09-01 - 2026-09-12"
    assert len(report.systemic_issues) == 1
    assert report.systemic_issues[0].affected_line == "L2"
    assert report.metrics_summary.csat_score == 0.82
    assert report.metrics_summary.deflection_rate == 0.45
    assert report.metrics_summary.oqs_score == 0.86


def test_systemic_issue_item_schema_invalid_affected_line() -> None:
    """Проверяет отклонение недопустимого значения линии (только L1, L2, L3)."""
    with pytest.raises(ValidationError):
        SystemicIssueItemSchema(
            title="Ошибка",
            evidence_count=1,
            affected_line="L4",  # Недопустимо
            suspected_cause="Причина",
            examples=[],
            recommendation="Рекомендация",
        )


# --- 2. Модульные тесты бизнес-логики сервиса ---


@pytest.mark.asyncio
async def test_service_generate_report_date_validation() -> None:
    """Проверяет генерацию ошибки 422 при некорректном диапазоне дат (from > to)."""
    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=AsyncMock(spec=AnalyticsRepository),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_systemic_issues_report(
            from_date=date(2026, 9, 20),
            to_date=date(2026, 9, 10),
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail["code"] == "invalid_date_range"


@pytest.mark.asyncio
async def test_service_generate_report_empty_data() -> None:
    """Проверяет корректное формирование отчета при пустой выборке данных."""
    mock_repo = AsyncMock(spec=AnalyticsRepository)
    mock_repo.get_systemic_issues_raw_data.return_value = {
        "total_tickets": 0,
        "bot_resolved_tickets": 0,
        "feedback_scores": [],
        "problem_tickets": [],
        "positive_tickets": [],
    }

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    report = await service.generate_systemic_issues_report(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 12),
    )

    assert report.metrics_summary.total_tickets == 0
    assert report.metrics_summary.csat_score == 0.0
    assert report.metrics_summary.deflection_rate == 0.0
    assert report.systemic_issues == []
    assert "0 обращений" in report.summary


@pytest.mark.asyncio
async def test_service_generate_report_metrics_and_clustering() -> None:
    """Проверяет расчет метрик CSAT/deflection/OQS и кластеризацию обращений по 4 темам."""
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=settings.TIMEZONE)
    line_l1 = SupportLineModel(id=1, code="L1", name="Линия 1")
    line_l2 = SupportLineModel(id=2, code="L2", name="Линия 2")

    # Тикет 1: Сбой YML
    t_yml = TicketModel(
        id=uuid6.uuid7(),
        chat_id=uuid6.uuid7(),
        line=line_l1,
        priority=TicketPriority.P1.value,
        status=TicketStatus.RESOLVED.value,
        created_at=now,
    )
    t_yml.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t_yml.id,
        score=2,
        comment="Ошибка загрузки YML-прайс-листа: тег <param> не валидируется!",
        created_at=now,
    )
    t_yml.audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t_yml.id,
        politeness_score=3,
        completeness_score=3,
        root_cause=RootCauseType.SYSTEM_ISSUE.value,
        summary="Сбой импорта каталога товаров YML",
        is_system_issue=True,
        created_at=now,
    )
    t_yml.incidents = []
    t_yml.messages = [
        MessageModel(
            id=uuid6.uuid7(),
            ticket_id=t_yml.id,
            sender_type=MessageSenderType.CLIENT.value,
            text="Ошибка импорта YML: тег param на строке 40",
            created_at=now,
        )
    ]

    # Тикет 2: Сбой КриптоПро
    t_crypto = TicketModel(
        id=uuid6.uuid7(),
        chat_id=uuid6.uuid7(),
        line=line_l2,
        priority=TicketPriority.P0.value,
        status=TicketStatus.RESOLVED.value,
        created_at=now,
    )
    t_crypto.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t_crypto.id,
        score=1,
        comment="Плагин КриптоПро выдает ошибку 0x80090016 при подписании!",
        created_at=now,
    )
    t_crypto.audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t_crypto.id,
        politeness_score=4,
        completeness_score=3,
        root_cause=RootCauseType.SYSTEM_ISSUE.value,
        summary="Ошибка 0x80090016 плагина ЭЦП",
        is_system_issue=True,
        created_at=now,
    )
    t_crypto.incidents = [
        SystemIncidentModel(
            id=uuid6.uuid7(),
            ticket_id=t_crypto.id,
            incident_type=IncidentType.CRYPTO_PLUGIN.value,
            description="Сбой плагина ЭЦП КриптоПро",
            status="open",
            created_at=now,
        )
    ]
    t_crypto.messages = [
        MessageModel(
            id=uuid6.uuid7(),
            ticket_id=t_crypto.id,
            sender_type=MessageSenderType.CLIENT.value,
            text="Не могу подписать оферту, ошибка плагина КриптоПро 0x80090016",
            created_at=now,
        )
    ]

    # Тикет 3: Навигация
    t_nav = TicketModel(
        id=uuid6.uuid7(),
        chat_id=uuid6.uuid7(),
        line=line_l1,
        priority=TicketPriority.P2.value,
        status=TicketStatus.RESOLVED.value,
        created_at=now,
    )
    t_nav.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t_nav.id,
        score=2,
        comment="Не могу найти кнопку подачи оферты в личном кабинете!",
        created_at=now,
    )
    t_nav.audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t_nav.id,
        politeness_score=4,
        completeness_score=4,
        root_cause=RootCauseType.OPERATOR_ERROR.value,
        summary="Сложности навигации в интерфейсе",
        is_system_issue=False,
        created_at=now,
    )
    t_nav.incidents = []
    t_nav.messages = []

    # Тикет 4: Подписание УПД
    t_signing = TicketModel(
        id=uuid6.uuid7(),
        chat_id=uuid6.uuid7(),
        line=line_l2,
        priority=TicketPriority.P1.value,
        status=TicketStatus.RESOLVED.value,
        created_at=now,
    )
    t_signing.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t_signing.id,
        score=2,
        comment="Ошибка прикрепления УПД к закрывающей оферте!",
        created_at=now,
    )
    t_signing.audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t_signing.id,
        politeness_score=4,
        completeness_score=4,
        root_cause=RootCauseType.SYSTEM_ISSUE.value,
        summary="Сбой сопоставления УПД и оферты",
        is_system_issue=True,
        created_at=now,
    )
    t_signing.incidents = []
    t_signing.messages = []

    # Тикет 5: Положительный
    t_pos = TicketModel(
        id=uuid6.uuid7(),
        chat_id=uuid6.uuid7(),
        line=line_l1,
        priority=TicketPriority.P2.value,
        status=TicketStatus.RESOLVED.value,
        assigned_operator_id=None,  # решено ботом!
        created_at=now,
    )
    t_pos.feedback = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t_pos.id,
        score=5,
        comment="Бот моментально подсказал регламент аккредитации!",
        created_at=now,
    )

    mock_repo = AsyncMock(spec=AnalyticsRepository)
    # 5 тикетов, 2 закрыто ботом, оценки: 2, 1, 2, 2, 5
    mock_repo.get_systemic_issues_raw_data.return_value = {
        "total_tickets": 5,
        "bot_resolved_tickets": 2,
        "feedback_scores": [2, 1, 2, 2, 5],
        "problem_tickets": [t_yml, t_crypto, t_nav, t_signing],
        "positive_tickets": [t_pos],
    }

    service = AnalyticsService(
        session=AsyncMock(),
        redis=AsyncMock(),
        analytics_repo=mock_repo,
    )

    report = await service.generate_systemic_issues_report(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 12),
    )

    # Проверка метрик:
    # 1. deflection_rate = 2 / 5 = 0.40
    assert report.metrics_summary.deflection_rate == 0.40
    # 2. csat_score:
    # Оценки: [2, 1, 2, 2, 5]. Лайки (>= 4): 1 из 5 (0.2).
    # Средний балл: (2+1+2+2+5)/5 = 2.4. 2.4 / 5.0 = 0.48.
    # CSAT_norm = (0.2 + 0.48) / 2 = 0.34.
    assert report.metrics_summary.csat_score == 0.34
    # 3. oqs_score рассчитывается по формуле и находится в отрезке [0.0, 1.0]
    assert 0.0 <= report.metrics_summary.oqs_score <= 1.0

    # Проверка кластеров: должны быть распознаны все 4 темы
    cluster_titles = [item.title for item in report.systemic_issues]
    assert any("КриптоПро" in title for title in cluster_titles)
    assert any("YML" in title for title in cluster_titles)
    assert any("навигаци" in title.lower() for title in cluster_titles)
    assert any(
        "подписани" in title.lower() or "упд" in title.lower()
        for title in cluster_titles
    )

    # Проверка цитат и рекомендаций
    crypto_item = next(
        i for i in report.systemic_issues if "КриптоПро" in i.title
    )
    assert crypto_item.affected_line == "L2"
    assert len(crypto_item.examples) > 0
    assert "0x80090016" in crypto_item.examples[0]
    assert "FAQ" in crypto_item.recommendation


# --- 3. Интеграционные тесты REST API /systemic-issues ---


@pytest.fixture
def mock_analytics_service_for_api() -> AsyncMock:
    """Мок сервиса аналитики для тестирования эндпоинта."""
    mock = AsyncMock(spec=AnalyticsService)
    mock.generate_systemic_issues_report.return_value = (
        SystemicIssuesReportResponseSchema(
            period="2026-09-01 - 2026-09-12",
            summary="Тестовое заключение руководству.",
            systemic_issues=[
                SystemicIssueItemSchema(
                    title="Сбои плагина ЭЦП КриптоПро при подписании",
                    evidence_count=8,
                    affected_line="L2",
                    suspected_cause="Ошибка 0x80090016",
                    examples=["Плагин КриптоПро выдает ошибку 0x80090016"],
                    recommendation="Опубликовать инструкцию по настройке",
                )
            ],
            metrics_summary=SystemicMetricsSummarySchema(
                total_tickets=30,
                csat_score=0.75,
                deflection_rate=0.40,
                oqs_score=0.82,
            ),
            positive_patterns=["Бот успешно решает 40% обращений"],
        )
    )
    return mock


@pytest.fixture
def supervisor_api_app(
    mock_analytics_service_for_api: AsyncMock,
) -> FastAPI:
    """Приложение с авторизацией супервизора."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service_for_api
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.SUPERVISOR
    )
    return app


@pytest.fixture
def client_role_api_app(
    mock_analytics_service_for_api: AsyncMock,
) -> FastAPI:
    """Приложение с авторизацией клиента (поставщика)."""
    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_analytics_service] = lambda: (
        mock_analytics_service_for_api
    )
    app.dependency_overrides[get_current_user] = lambda: create_mock_user(
        UserRole.CLIENT
    )
    return app


@pytest.mark.asyncio
async def test_api_systemic_issues_endpoint_success_supervisor(
    supervisor_api_app: FastAPI,
    mock_analytics_service_for_api: AsyncMock,
) -> None:
    """Проверяет успешное получение аналитического заключения супервизором (200 OK)."""
    async with AsyncClient(
        transport=ASGITransport(app=supervisor_api_app),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/api/v1/analytics/systemic-issues?from_date=2026-09-01&to_date=2026-09-12"
        )

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Проверка схемы и полей ответа
    assert data["period"] == "2026-09-01 - 2026-09-12"
    assert "summary" in data
    assert len(data["systemic_issues"]) == 1
    issue = data["systemic_issues"][0]
    assert issue["title"] == "Сбои плагина ЭЦП КриптоПро при подписании"
    assert issue["affected_line"] == "L2"
    assert issue["evidence_count"] == 8
    assert len(issue["examples"]) == 1

    # Проверка метрик
    metrics = data["metrics_summary"]
    assert metrics["total_tickets"] == 30
    assert metrics["csat_score"] == 0.75
    assert metrics["deflection_rate"] == 0.40
    assert metrics["oqs_score"] == 0.82

    mock_analytics_service_for_api.generate_systemic_issues_report.assert_awaited_once_with(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 12),
    )


@pytest.mark.asyncio
async def test_api_systemic_issues_endpoint_forbidden_for_client(
    client_role_api_app: FastAPI,
) -> None:
    """Проверяет запрет доступа (403 Forbidden) к аналитике для роли клиента/поставщика."""
    async with AsyncClient(
        transport=ASGITransport(app=client_role_api_app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/analytics/systemic-issues")

    assert resp.status_code == status.HTTP_403_FORBIDDEN
