"""Тесты расчета показателей эффективности и сводного дашборда (MED-02)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import uuid6
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.metrics import calculate_deflection_rate, round_metric
from src.analytics.models import (
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.repository import AnalyticsRepository
from src.analytics.schemas import (
    AnalyticsDashboardResponseSchema,
    DailyMetricsPayloadSchema,
    OperatorDailyMetricResponseSchema,
    OperatorMetricsListResponseSchema,
)
from src.analytics.service import AnalyticsService
from src.analytics.tasks import calculate_daily_metrics
from src.auth.models import RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageSenderType,
    TicketModel,
    TicketStatus,
)
from src.core.config import settings
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)


class MockRedis:
    """Асинхронный мок Redis для тестирования."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(
        self, key: str, value: str, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: Any
    ) -> Any:
        key = keys_and_args[0] if keys_and_args else None
        if key and key in self._store:
            del self._store[key]
            return 1
        return 0

    async def aclose(self) -> None:
        pass


class InMemoryAnalyticsRepository:
    """In-memory реализация репозитория аналитики для детерминированного тестирования сервиса."""

    def __init__(self) -> None:
        self.metrics_db: list[dict[str, Any]] = []
        self.upsert_called_with: list[dict[str, Any]] = []

    async def get_dashboard_metrics(
        self, from_dt: datetime, to_dt: datetime
    ) -> dict[str, Any]:
        return {
            "total_tickets": 10,
            "bot_resolved_tickets": 4,
            "bot_resolved_percent": 40.0,
            "avg_first_response_time_sec": 45.0,
            "avg_handling_time_sec": 240.0,
            "client_csat": 4.5,
            "adjusted_csat": 4.8,
            "avg_ai_politeness_score": 4.6,
            "avg_ai_completeness_score": 4.7,
            "active_incidents_count": 1,
        }

    async def calculate_operator_metrics_for_date(
        self, target_date: date, operator_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        op_id = operator_id or uuid6.uuid7()
        return [
            {
                "id": uuid6.uuid7(),
                "operator_id": op_id,
                "metric_date": target_date,
                "total_tickets_handled": 8,
                "avg_first_response_time_sec": 30.0,
                "avg_handling_time_sec": 180.0,
                "avg_client_csat": 4.7,
                "avg_adjusted_csat": 4.9,
                "avg_ai_quality_score": 4.8,
            }
        ]

    async def upsert_operator_daily_metrics(
        self, metrics: list[dict[str, Any]]
    ) -> None:
        self.upsert_called_with = metrics
        self.metrics_db.extend(metrics)

    async def get_operator_metrics(
        self, target_date: date | None = None, line_code: str | None = None
    ) -> list[OperatorDailyMetricResponseSchema]:
        op_id = uuid6.uuid7()
        return [
            OperatorDailyMetricResponseSchema(
                operator_id=op_id,
                operator_name="Тестовый Оператор",
                line_code=line_code or "L1",
                metric_date=target_date
                or datetime.now(settings.TIMEZONE).date(),
                total_tickets_handled=5,
                avg_first_response_time_sec=25.0,
                avg_handling_time_sec=150.0,
                avg_client_csat=4.6,
                avg_adjusted_csat=4.8,
                avg_ai_quality_score=4.7,
            )
        ]


# =========================================================================
# 1. Модульные тесты Pydantic-схем и хелперов metrics.py
# =========================================================================


def test_round_metric_and_deflection_rate() -> None:
    """Проверяет хелперы округления и расчета процента автоматизации."""
    assert round_metric(None) == 0.0
    assert round_metric(Decimal("12.3456")) == 12.35
    assert round_metric(12.3456, precision=1) == 12.3

    assert calculate_deflection_rate(0, 0) == 0.0
    assert calculate_deflection_rate(5, 10) == 50.0
    assert calculate_deflection_rate(1, 3) == 33.33


def test_analytics_dashboard_response_schema() -> None:
    """Проверяет валидацию схемы ответа сводного дашборда."""
    schema = AnalyticsDashboardResponseSchema(
        total_tickets=100,
        bot_resolved_percent=42.5,
        bot_resolved_tickets=42,
        avg_first_response_time_sec=45.2,
        avg_handling_time_sec=320.0,
        client_csat=4.65,
        adjusted_csat=4.9,
        avg_ai_politeness_score=4.8,
        avg_ai_completeness_score=4.7,
        active_incidents_count=1,
    )
    assert schema.total_tickets == 100
    assert schema.bot_resolved_percent == 42.5
    assert schema.bot_resolved_tickets == 42
    assert schema.adjusted_csat == 4.9

    with pytest.raises(ValidationError):
        AnalyticsDashboardResponseSchema(total_tickets="not_a_number")  # type: ignore[arg-type]


def test_operator_daily_metric_schema() -> None:
    """Проверяет валидацию схемы суточных метрик оператора."""
    op_id = uuid6.uuid7()
    today = datetime.now(settings.TIMEZONE).date()
    schema = OperatorDailyMetricResponseSchema(
        operator_id=op_id,
        operator_name="Иванов Иван",
        line_code="L1",
        metric_date=today,
        total_tickets_handled=15,
        avg_first_response_time_sec=25.5,
        avg_handling_time_sec=180.0,
        avg_client_csat=4.8,
        avg_adjusted_csat=4.9,
        avg_ai_quality_score=4.75,
    )
    assert schema.operator_id == op_id
    assert schema.operator_name == "Иванов Иван"
    assert schema.line_code == "L1"

    list_schema = OperatorMetricsListResponseSchema(items=[schema], total=1)
    assert len(list_schema.items) == 1
    assert list_schema.total == 1


def test_daily_metrics_payload_schema() -> None:
    """Проверяет валидацию полезной нагрузки задачи calculate_daily_metrics."""
    payload = DailyMetricsPayloadSchema(
        metric_date=date(2026, 9, 10),
        operator_id=uuid6.uuid7(),
    )
    assert payload.metric_date == date(2026, 9, 10)
    assert payload.operator_id is not None

    payload_empty = DailyMetricsPayloadSchema()
    assert payload_empty.metric_date is None
    assert payload_empty.operator_id is None


# =========================================================================
# 2. Модульные тесты AnalyticsService (не зависящие от Docker)
# =========================================================================


@pytest.mark.asyncio
async def test_service_get_dashboard_flow() -> None:
    """Проверяет работу AnalyticsService.get_dashboard и валидацию дат."""
    mock_session = AsyncMock(spec=AsyncSession)
    redis = MockRedis()
    in_memory_repo = InMemoryAnalyticsRepository()

    service = AnalyticsService(
        session=mock_session,
        redis=redis,  # type: ignore[arg-type]
        analytics_repo=in_memory_repo,  # type: ignore[arg-type]
    )

    # 1. Корректный запрос с датами
    res = await service.get_dashboard(
        from_date=date(2026, 9, 1), to_date=date(2026, 9, 10)
    )
    assert res.total_tickets == 10
    assert res.bot_resolved_percent == 40.0
    assert res.adjusted_csat == 4.8

    # 2. Невалидный диапазон (from_date > to_date)
    with pytest.raises(HTTPException) as exc_info:
        await service.get_dashboard(
            from_date=date(2026, 9, 15), to_date=date(2026, 9, 10)
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_service_calculate_daily_metrics_flow() -> None:
    """Проверяет работу AnalyticsService.calculate_daily_metrics."""
    mock_session = AsyncMock(spec=AsyncSession)
    redis = MockRedis()
    in_memory_repo = InMemoryAnalyticsRepository()

    service = AnalyticsService(
        session=mock_session,
        redis=redis,  # type: ignore[arg-type]
        analytics_repo=in_memory_repo,  # type: ignore[arg-type]
    )

    # Запуск с указанием конкретной даты
    result = await service.calculate_daily_metrics(
        target_date=date(2026, 9, 10)
    )
    assert result["status"] == "success"
    assert result["metric_date"] == "2026-09-10"
    assert result["operators_calculated"] == 1
    assert len(in_memory_repo.upsert_called_with) == 1

    # Запуск по умолчанию (target_date=None -> вчера в Москве)
    result_default = await service.calculate_daily_metrics()
    assert result_default["status"] == "success"
    yesterday = (datetime.now(settings.TIMEZONE) - timedelta(days=1)).date()
    assert result_default["metric_date"] == str(yesterday)


@pytest.mark.asyncio
async def test_task_calculate_daily_metrics() -> None:
    """Проверяет фоновую задачу Taskiq calculate_daily_metrics с распределенным локом."""
    mock_session = AsyncMock(spec=AsyncSession)
    redis = MockRedis()

    with (
        patch("src.analytics.tasks.aioredis.from_url", return_value=redis),
        patch("src.analytics.tasks.async_session_maker") as mock_session_maker,
        patch.object(
            AnalyticsService,
            "calculate_daily_metrics",
            return_value={"status": "success", "metric_date": "2026-09-10"},
        ),
    ):
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        mock_session_maker.return_value.__aexit__.return_value = None

        # Первый успешный запуск
        result = await calculate_daily_metrics(
            payload={"metric_date": "2026-09-10"}
        )
        assert result["status"] == "success"
        assert result["metric_date"] == "2026-09-10"

        # Симуляция занятого лока
        await redis.set("lock:calculate_daily_metrics", "busy", ex=300)
        result_busy = await calculate_daily_metrics(
            payload={"metric_date": "2026-09-10"}
        )
        assert result_busy["status"] == "skipped"
        assert result_busy["reason"] == "lock_busy"


# =========================================================================
# 3. Интеграционные тесты SQL-агрегации и репозитория (требуют PostgreSQL)
# =========================================================================


@pytest.mark.asyncio
async def test_dashboard_metrics_calculation(
    async_session: AsyncSession,
) -> None:
    """Проверяет расчет сводного дашборда на лету с арбитражем CSAT и FRT в PostgreSQL."""
    now = datetime.now(settings.TIMEZONE)

    role_op = RoleModel(id=201, code="operator_med02", name="Оператор")
    role_client = RoleModel(id=202, code="client_med02", name="Клиент")
    async_session.add_all([role_op, role_client])
    await async_session.flush()

    operator_user = UserModel(
        id=uuid6.uuid7(),
        role_id=role_op.id,
        email="operator_test@roseltorg.ru",
        password_hash="hash",
        full_name="Смирнов Алексей",
    )
    client_user = UserModel(
        id=uuid6.uuid7(),
        role_id=role_client.id,
        email="client_test@company.ru",
        password_hash="hash",
        full_name="Петров Петр",
    )
    async_session.add_all([operator_user, client_user])
    await async_session.flush()

    line = SupportLineModel(id=201, code="L1_MED02", name="Первая линия")
    async_session.add(line)
    await async_session.flush()

    chat = ChatModel(
        id=uuid6.uuid7(),
        client_id=client_user.id,
        created_at=now - timedelta(days=1),
    )
    async_session.add(chat)
    await async_session.flush()

    t1 = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=None,
        status=TicketStatus.RESOLVED.value,
        created_at=now - timedelta(hours=5),
        closed_at=now - timedelta(hours=4),
    )

    t2 = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=operator_user.id,
        status=TicketStatus.RESOLVED.value,
        created_at=now - timedelta(hours=4),
        opened_at=now - timedelta(hours=3, minutes=50),
        closed_at=now - timedelta(hours=3),
    )

    t3 = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=operator_user.id,
        status=TicketStatus.RESOLVED.value,
        created_at=now - timedelta(hours=3),
        opened_at=now - timedelta(hours=2, minutes=50),
        closed_at=now - timedelta(hours=2),
    )

    t4 = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=operator_user.id,
        status=TicketStatus.IN_PROGRESS.value,
        created_at=now - timedelta(hours=1),
        opened_at=now - timedelta(minutes=50),
    )

    async_session.add_all([t1, t2, t3, t4])
    await async_session.flush()

    msg2_client = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=t2.id,
        sender_type=MessageSenderType.CLIENT.value,
        sender_id=client_user.id,
        text="Вопрос по ЭЦП",
        created_at=now - timedelta(hours=4),
    )
    msg2_op = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=t2.id,
        sender_type=MessageSenderType.OPERATOR.value,
        sender_id=operator_user.id,
        text="Здравствуйте, помогу",
        created_at=now
        - timedelta(hours=3, minutes=45),  # FRT = 15 мин = 900 сек
    )

    msg3_client = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=t3.id,
        sender_type=MessageSenderType.CLIENT.value,
        sender_id=client_user.id,
        text="Ошибка портала",
        created_at=now - timedelta(hours=3),
    )
    msg3_op = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=t3.id,
        sender_type=MessageSenderType.OPERATOR.value,
        sender_id=operator_user.id,
        text="Зафиксировал ошибку",
        created_at=now
        - timedelta(hours=2, minutes=45),  # FRT = 15 мин = 900 сек
    )

    async_session.add_all([msg2_client, msg2_op, msg3_client, msg3_op])

    fb2 = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t2.id,
        score=5,
        created_at=now - timedelta(hours=3),
    )
    fb3 = TicketFeedbackModel(
        id=uuid6.uuid7(),
        ticket_id=t3.id,
        score=1,
        created_at=now - timedelta(hours=2),
    )
    async_session.add_all([fb2, fb3])

    audit2 = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t2.id,
        politeness_score=5,
        completeness_score=5,
        root_cause="none",
        summary="Отличная консультация",
        is_system_issue=False,
        created_at=now - timedelta(hours=3),
    )
    audit3 = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t3.id,
        politeness_score=4,
        completeness_score=4,
        root_cause="system_issue",
        summary="Сбой портала",
        is_system_issue=True,
        created_at=now - timedelta(hours=2),
    )
    async_session.add_all([audit2, audit3])

    repo = AnalyticsRepository(async_session)
    before_metrics = await repo.get_dashboard_metrics(
        from_dt=now - timedelta(hours=10),
        to_dt=now + timedelta(hours=1),
    )

    incident = SystemIncidentModel(
        id=uuid6.uuid7(),
        ticket_id=t3.id,
        incident_type="portal_downtime",
        description="Недоступность сервиса",
        status="open",
        created_at=now - timedelta(hours=2),
    )
    async_session.add(incident)
    await async_session.commit()

    metrics = await repo.get_dashboard_metrics(
        from_dt=now - timedelta(hours=10),
        to_dt=now + timedelta(hours=1),
    )

    assert metrics["total_tickets"] == 4
    assert metrics["bot_resolved_tickets"] == 1
    assert metrics["bot_resolved_percent"] == 33.33
    assert metrics["client_csat"] == 3.0
    assert metrics["adjusted_csat"] == 5.0
    assert metrics["avg_ai_politeness_score"] == 4.5
    assert metrics["avg_ai_completeness_score"] == 4.5
    assert (
        metrics["active_incidents_count"]
        == before_metrics["active_incidents_count"] + 1
    )
    assert metrics["avg_first_response_time_sec"] == 900.0


@pytest.mark.asyncio
async def test_dashboard_metrics_empty_db(
    async_session: AsyncSession,
) -> None:
    """Проверяет безопасность расчета метрик за период без обращений в PostgreSQL."""
    now = datetime.now(settings.TIMEZONE)
    repo = AnalyticsRepository(async_session)
    metrics = await repo.get_dashboard_metrics(
        from_dt=now + timedelta(days=365),
        to_dt=now + timedelta(days=395),
    )
    assert metrics["total_tickets"] == 0
    assert metrics["bot_resolved_tickets"] == 0
    assert metrics["bot_resolved_percent"] == 0.0
    assert metrics["client_csat"] == 0.0
    assert metrics["adjusted_csat"] == 0.0
    assert metrics["avg_first_response_time_sec"] == 0.0
    assert metrics["avg_handling_time_sec"] == 0.0
    assert metrics["active_incidents_count"] >= 0


@pytest.mark.asyncio
async def test_calculate_daily_metrics_and_upsert(
    async_session: AsyncSession,
) -> None:
    """Проверяет расчет суточных показателей операторов и идемпотентный UPSERT в PostgreSQL."""
    target_date = date(2026, 9, 10)
    day_dt = datetime(2026, 9, 10, 12, 0, 0, tzinfo=settings.TIMEZONE)

    role_op = RoleModel(id=203, code="operator_203_med02", name="Оператор")
    role_client = RoleModel(id=204, code="client_204_med02", name="Клиент")
    async_session.add_all([role_op, role_client])
    await async_session.flush()

    op = UserModel(
        id=uuid6.uuid7(),
        role_id=role_op.id,
        email="op_daily_med02@test.ru",
        password_hash="pwd",
        full_name="Ковалев Сергей",
    )
    client = UserModel(
        id=uuid6.uuid7(),
        role_id=role_client.id,
        email="client_daily_med02@test.ru",
        password_hash="pwd",
    )
    async_session.add_all([op, client])
    await async_session.flush()

    line = SupportLineModel(id=202, code="L2_MED02", name="Вторая линия")
    async_session.add(line)
    await async_session.flush()

    profile = OperatorProfileModel(
        user_id=op.id,
        line_id=line.id,
        shift_status=OperatorShiftStatus.ACTIVE.value,
    )
    async_session.add(profile)

    chat = ChatModel(
        id=uuid6.uuid7(),
        client_id=client.id,
        created_at=day_dt - timedelta(days=1),
    )
    async_session.add(chat)
    await async_session.flush()

    t = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        assigned_operator_id=op.id,
        status=TicketStatus.RESOLVED.value,
        created_at=day_dt - timedelta(hours=1),
        opened_at=day_dt - timedelta(minutes=50),
        closed_at=day_dt,
    )
    async_session.add(t)
    await async_session.flush()

    msg_op = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=t.id,
        sender_type=MessageSenderType.OPERATOR.value,
        sender_id=op.id,
        text="Здравствуйте!",
        created_at=day_dt - timedelta(minutes=40),
    )
    fb = TicketFeedbackModel(
        id=uuid6.uuid7(), ticket_id=t.id, score=4, created_at=day_dt
    )
    audit = TicketAuditModel(
        id=uuid6.uuid7(),
        ticket_id=t.id,
        politeness_score=5,
        completeness_score=5,
        root_cause="none",
        summary="Хорошо",
        is_system_issue=False,
        created_at=day_dt,
    )
    async_session.add_all([msg_op, fb, audit])
    await async_session.commit()

    repo = AnalyticsRepository(async_session)

    # 1. Первый расчет
    metrics = await repo.calculate_operator_metrics_for_date(
        target_date=target_date, operator_id=op.id
    )
    assert len(metrics) == 1
    m = metrics[0]
    assert m["operator_id"] == op.id
    assert m["total_tickets_handled"] == 1
    assert m["avg_first_response_time_sec"] == 600.0
    assert m["avg_client_csat"] == 4.0
    assert m["avg_adjusted_csat"] == 4.0
    assert m["avg_ai_quality_score"] == 5.0

    # 2. Атомарный UPSERT
    await repo.upsert_operator_daily_metrics(metrics)
    await async_session.commit()

    # 3. Выборка через get_operator_metrics
    op_metrics = await repo.get_operator_metrics(
        target_date=target_date, line_code="L2_MED02"
    )
    assert len(op_metrics) == 1
    assert op_metrics[0].operator_name == "Ковалев Сергей"
    assert op_metrics[0].line_code == "L2_MED02"
    assert op_metrics[0].total_tickets_handled == 1

    # 4. Повторный расчет и UPSERT (проверка идемпотентности)
    await repo.upsert_operator_daily_metrics(metrics)
    await async_session.commit()

    op_metrics_after = await repo.get_operator_metrics(target_date=target_date)
    assert len(op_metrics_after) == 1
