"""Комплексные тесты автоматического аудита качества диалогов языковой моделью (MED-01)."""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import uuid6
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.evaluator import (
    MockAuditLlmClient,
    build_audit_dialog_context,
)
from src.analytics.models import (
    IncidentStatus,
    IncidentType,
    RootCauseType,
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.schemas import (
    AuditLlmOutputSchema,
    AuditTicketPayloadSchema,
    FeedbackCreateRequestSchema,
)
from src.analytics.service import AnalyticsService
from src.api.dependencies import (
    get_analytics_service,
    get_current_user,
)
from src.auth.models import RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    TicketModel,
    TicketStatus,
)
from src.core.config import settings
from src.main import app
from src.operators.models import SupportLineModel
from src.operators.service import OperatorService

# =========================================================================
# 1. Модульные тесты Pydantic-схем
# =========================================================================


def test_audit_ticket_payload_schema() -> None:
    """Проверяет валидацию полезной нагрузки очереди Taskiq analytics_queue."""
    tid = uuid6.uuid7()
    payload = AuditTicketPayloadSchema(ticket_id=tid)
    assert payload.ticket_id == tid
    assert payload.trigger_reason == "feedback_received"

    with pytest.raises(ValidationError):
        AuditTicketPayloadSchema(ticket_id="not-a-uuid")


def test_audit_llm_output_schema() -> None:
    """Проверяет валидацию структурированного ответа модели-оценщика."""
    out = AuditLlmOutputSchema(
        politeness_score=4,
        completeness_score=5,
        root_cause=RootCauseType.NONE,
        summary="Все хорошо",
        is_system_issue=False,
    )
    assert out.politeness_score == 4
    assert out.completeness_score == 5
    assert out.root_cause == "none"

    # Недопустимый балл (>5 или <1)
    with pytest.raises(ValidationError):
        AuditLlmOutputSchema(
            politeness_score=6,
            completeness_score=5,
            root_cause=RootCauseType.NONE,
            summary="Неверный балл",
        )

    with pytest.raises(ValidationError):
        AuditLlmOutputSchema(
            politeness_score=0,
            completeness_score=5,
            root_cause=RootCauseType.NONE,
            summary="Неверный балл",
        )


def test_feedback_schemas_validation() -> None:
    """Проверяет валидацию запроса на оставление отзыва клиентом."""
    valid = FeedbackCreateRequestSchema(score=5, comment="Отличная помощь")
    assert valid.score == 5
    assert valid.comment == "Отличная помощь"

    # Оценка меньше 1
    with pytest.raises(ValidationError):
        FeedbackCreateRequestSchema(score=0)

    # Оценка больше 5
    with pytest.raises(ValidationError):
        FeedbackCreateRequestSchema(score=6)


# =========================================================================
# 2. Модульные тесты эвристики и билдера контекста (MockAuditLlmClient)
# =========================================================================


def test_build_audit_dialog_context() -> None:
    """Проверяет корректность разметки ролей и метаданных для LLM-Judge."""
    tid = uuid6.uuid7()
    msgs = [
        {"sender": "client", "text": "Не могу подать ценовое предложение"},
        {"sender": "bot", "text": "Ознакомьтесь со статьей регламента"},
        {"sender": "operator", "text": "Здравствуйте! Чем могу помочь?"},
        {"sender": "system", "text": "Эскалация на линию L1"},
    ]
    prompt = build_audit_dialog_context(
        ticket_id=tid,
        line_code="L1",
        assigned_operator_name="Петров П.П.",
        feedback_score=1,
        feedback_comment="Ужасный сервис",
        messages=msgs,
    )

    assert str(tid) in prompt
    assert "L1" in prompt
    assert "Петров П.П." in prompt
    assert "Оценка 1/5" in prompt
    assert "Ужасный сервис" in prompt
    assert "[КЛИЕНТ]: Не могу подать ценовое предложение" in prompt
    assert "[БОТ]: Ознакомьтесь со статьей регламента" in prompt
    assert "[ОПЕРАТОР]: Здравствуйте! Чем могу помочь?" in prompt
    assert "[СИСТЕМА]: Эскалация на линию L1" in prompt


@pytest.mark.asyncio
async def test_mock_evaluator_heuristics() -> None:
    """Проверяет классификацию маркеров в MockAuditLlmClient."""
    evaluator = MockAuditLlmClient()

    # 1. Сбой плагина ЭЦП / 0x
    res_tech = await evaluator.evaluate_dialog(
        prompt="Ошибка плагина КриптоПро 0x80090008 при подписи контракта! Оценка 1/5."
    )
    assert res_tech.is_system_issue is True
    assert res_tech.root_cause == RootCauseType.SYSTEM_ISSUE
    assert res_tech.incident_type == IncidentType.CRYPTO_PLUGIN

    # 2. Недовольство регламентом 44-ФЗ
    res_reg = await evaluator.evaluate_dialog(
        prompt="Заявку отклонили по 44-ФЗ, не согласен с комиссией и законом! Оператор все пояснил, но я зол. Оценка 2/5."
    )
    assert res_reg.is_system_issue is False
    assert res_reg.root_cause == RootCauseType.REGULATION_DISSATISFACTION

    # 3. Вина оператора (грубость)
    res_op = await evaluator.evaluate_dialog(
        prompt="Оператор нахамил, бросил диалог и не помог решить проблему! Оценка 1/5."
    )
    assert res_op.is_system_issue is False
    assert res_op.root_cause == RootCauseType.OPERATOR_ERROR
    assert res_op.politeness_score == 2

    # 4. Положительный отзыв
    res_pos = await evaluator.evaluate_dialog(
        prompt="Все отлично решили! Оценка 5/5."
    )
    assert res_pos.is_system_issue is False
    assert res_pos.root_cause == RootCauseType.NONE
    assert res_pos.politeness_score == 5
    assert res_pos.completeness_score == 5


@pytest.mark.asyncio
async def test_mock_evaluator_fail_times() -> None:
    """Проверяет симуляцию сбоев в MockAuditLlmClient."""
    evaluator = MockAuditLlmClient(fail_times=2)
    with pytest.raises(TimeoutError):
        await evaluator.evaluate_dialog("тест")
    with pytest.raises(TimeoutError):
        await evaluator.evaluate_dialog("тест")

    # На 3 раз успешен
    res = await evaluator.evaluate_dialog("тест")
    assert res is not None


# =========================================================================
# 3. Интеграционные тесты сервиса и репозитория аналитики
# =========================================================================


class MockRedis:
    """Асинхронный мок Redis для тестирования распределенных блокировок."""

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


class InMemoryAnalyticsRepository:
    """In-memory реализация AnalyticsRepository для детерминированного тестирования."""

    def __init__(self, ticket_repo: Any = None) -> None:
        self.audits: dict[UUID, TicketAuditModel] = {}
        self.feedbacks: dict[UUID, TicketFeedbackModel] = {}
        self.incidents: list[SystemIncidentModel] = []
        self.ticket_repo = ticket_repo

    async def get_audit_by_ticket_id(
        self, ticket_id: UUID
    ) -> TicketAuditModel | None:
        return self.audits.get(ticket_id)

    async def get_ticket_full_audit_data(
        self, ticket_id: UUID
    ) -> TicketModel | None:
        if self.ticket_repo:
            return (
                await self.ticket_repo.get_ticket_with_messages_and_feedback(
                    ticket_id
                )
            )
        return None

    async def create_audit(self, audit: TicketAuditModel) -> TicketAuditModel:
        self.audits[audit.ticket_id] = audit
        if self.ticket_repo and audit.ticket_id in self.ticket_repo.tickets:
            self.ticket_repo.tickets[audit.ticket_id].audit = audit
        return audit

    async def get_feedback_by_ticket_id(
        self, ticket_id: UUID
    ) -> TicketFeedbackModel | None:
        return self.feedbacks.get(ticket_id)

    async def create_feedback(
        self, feedback: TicketFeedbackModel
    ) -> TicketFeedbackModel:
        self.feedbacks[feedback.ticket_id] = feedback
        if self.ticket_repo and feedback.ticket_id in self.ticket_repo.tickets:
            self.ticket_repo.tickets[feedback.ticket_id].feedback = feedback
        return feedback

    async def get_open_incident_by_type(
        self,
        incident_type: str,
        window_hours: int = 2,
        now: datetime | None = None,
    ) -> SystemIncidentModel | None:
        current_time = now or datetime.now(settings.TIMEZONE)
        cutoff = current_time - timedelta(hours=window_hours)
        for inc in reversed(self.incidents):
            if (
                inc.incident_type == incident_type
                and (
                    inc.status == IncidentStatus.OPEN
                    or inc.status == IncidentStatus.OPEN.value
                )
                and inc.created_at >= cutoff
            ):
                return inc
        return None

    async def create_incident(
        self, incident: SystemIncidentModel
    ) -> SystemIncidentModel:
        self.incidents.append(incident)
        return incident


class InMemoryTicketRepository:
    """In-memory реализация TicketRepository для изолированного тестирования."""

    def __init__(self) -> None:
        self.tickets: dict[UUID, TicketModel] = {}

    def add_ticket(self, ticket: TicketModel) -> None:
        self.tickets[ticket.id] = ticket

    async def get_by_id(self, ticket_id: UUID) -> TicketModel | None:
        return self.tickets.get(ticket_id)

    async def get_ticket_with_messages_and_feedback(
        self, ticket_id: UUID
    ) -> TicketModel | None:
        return self.tickets.get(ticket_id)

    async def get_inactive_bot_tickets(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        return []

    async def get_inactive_client_tickets(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        return []

    async def get_inactive_operator_tickets(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        return []

    async def get_in_progress_tickets_with_messages(
        self, limit: int = 100
    ) -> list[TicketModel]:
        return []

    async def get_tickets_for_audit_timeout(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        matched = []
        for t in self.tickets.values():
            if (
                t.status == TicketStatus.RESOLVED.value
                and t.closed_at
                and t.closed_at <= cutoff
                and not getattr(t, "audit", None)
                and not getattr(t, "feedback", None)
            ):
                matched.append(t)
        return matched[:limit]


def _build_test_ticket(
    status: str = TicketStatus.RESOLVED.value,
    closed_at: datetime | None = None,
    messages_content: list[tuple[str, str]] | None = None,
    feedback_score: int | None = None,
    feedback_comment: str | None = None,
) -> tuple[UserModel, ChatModel, TicketModel]:
    """Строит тестовый граф моделей тикета в оперативной памяти."""
    client = UserModel(
        id=uuid6.uuid7(),
        email=f"client_{uuid6.uuid7().hex[:6]}@test.ru",
        password_hash="fake",
        full_name="Тестовый Клиент",
        is_active=True,
    )
    chat = ChatModel(
        id=uuid6.uuid7(),
        client_id=client.id,
    )
    line = SupportLineModel(
        id=1,
        code="L1",
        name="Линия 1",
        description="Тестовая линия",
        is_active=True,
    )
    ticket = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line.id,
        status=status,
        closed_at=closed_at or datetime.now(settings.TIMEZONE),
    )
    ticket.chat = chat
    ticket.line = line
    ticket.messages = []
    if messages_content:
        for idx, (sender, text) in enumerate(messages_content):
            msg = MessageModel(
                id=uuid6.uuid7(),
                ticket_id=ticket.id,
                sender_type=sender,
                text=text,
                moderation_status=MessageModerationStatus.PASSED.value,
                created_at=datetime.now(settings.TIMEZONE)
                + timedelta(seconds=idx),
            )
            ticket.messages.append(msg)
    if feedback_score is not None:
        fb = TicketFeedbackModel(
            id=uuid6.uuid7(),
            ticket_id=ticket.id,
            score=feedback_score,
            comment=feedback_comment,
            created_at=datetime.now(settings.TIMEZONE),
        )
        ticket.feedback = fb
    return client, chat, ticket


@pytest.mark.asyncio
async def test_audit_operator_error_flow() -> None:
    """Проверяет аудит диалога с виной оператора и сохранение в ticket_audits."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)

    _, _, ticket = _build_test_ticket(
        messages_content=[
            ("client", "Как прикрепить платежное поручение?"),
            ("operator", "Читайте инструкцию на сайте, мне некогда"),
        ],
        feedback_score=1,
        feedback_comment="Оператор нахамил и не помог",
    )
    ticket_repo.add_ticket(ticket)
    analytics_repo.feedbacks[ticket.id] = ticket.feedback

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )
    res = await service.audit_ticket_quality(ticket.id)

    assert res["status"] == "success"
    assert res["root_cause"] == RootCauseType.OPERATOR_ERROR.value
    assert res["is_system_issue"] is False
    assert res["politeness_score"] == 2
    assert res["incident_created"] is False

    # Проверяем запись в репозитории
    audit_record = await analytics_repo.get_audit_by_ticket_id(ticket.id)
    assert audit_record is not None
    assert audit_record.politeness_score == 2
    assert audit_record.is_system_issue is False


@pytest.mark.asyncio
async def test_audit_system_issue_flow_and_incident() -> None:
    """Проверяет выявление системного сбоя, арбитраж оператора и создание инцидента."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)

    _, _, ticket = _build_test_ticket(
        messages_content=[
            (
                "client",
                "Не могу подписать документ, ошибка плагина КриптоПро 0x80090008!",
            ),
            (
                "operator",
                "Здравствуйте! Техническая служба уже устраняет сбой плагина.",
            ),
        ],
        feedback_score=1,
        feedback_comment="Сбой плагина ЭЦП",
    )
    ticket_repo.add_ticket(ticket)
    analytics_repo.feedbacks[ticket.id] = ticket.feedback

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )
    res = await service.audit_ticket_quality(ticket.id)

    assert res["status"] == "success"
    assert res["is_system_issue"] is True
    assert res["root_cause"] == RootCauseType.SYSTEM_ISSUE.value
    assert res["incident_created"] is True

    # Проверяем запись в system_incidents
    incident = await analytics_repo.get_open_incident_by_type(
        IncidentType.CRYPTO_PLUGIN.value
    )
    assert incident is not None
    assert incident.ticket_id == ticket.id
    assert incident.status == IncidentStatus.OPEN.value


@pytest.mark.asyncio
async def test_audit_incident_deduplication() -> None:
    """Проверяет дедупликацию системных инцидентов со скользящим окном 2 часа."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )

    # Тикет 1: первый сбой плагина
    _, _, ticket1 = _build_test_ticket(
        messages_content=[
            ("client", "Сбой КриптоПро 0x80090008"),
            ("operator", "Знаем о проблеме"),
        ],
        feedback_score=1,
    )
    ticket_repo.add_ticket(ticket1)
    res1 = await service.audit_ticket_quality(ticket1.id)
    assert res1["incident_created"] is True

    # Тикет 2: второй сбой плагина через пару минут
    _, _, ticket2 = _build_test_ticket(
        messages_content=[
            ("client", "Опять ошибка плагина 0x80090008!"),
            ("operator", "Чинят"),
        ],
        feedback_score=1,
    )
    ticket_repo.add_ticket(ticket2)
    res2 = await service.audit_ticket_quality(ticket2.id)

    # Защита оператора активна
    assert res2["is_system_issue"] is True
    # Но новый дубликат инцидента в реестре не создан
    assert res2["incident_created"] is False
    assert len(analytics_repo.incidents) == 1


@pytest.mark.asyncio
async def test_audit_idempotency() -> None:
    """Проверяет идемпотентность задачи: повторный аудит не перезаписывает данные."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)
    mock_llm = MockAuditLlmClient()

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        evaluator=mock_llm,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )

    _, _, ticket = _build_test_ticket(
        messages_content=[
            ("client", "Спасибо за помощь"),
            ("operator", "Пожалуйста!"),
        ],
    )
    ticket_repo.add_ticket(ticket)

    res1 = await service.audit_ticket_quality(ticket.id)
    assert res1["status"] == "success"
    assert mock_llm.call_count == 1

    # Повторный запуск аудита
    res2 = await service.audit_ticket_quality(ticket.id)
    assert res2["status"] == "already_audited"
    # Модель повторно НЕ вызывалась
    assert mock_llm.call_count == 1


@pytest.mark.asyncio
async def test_audit_dead_letter_fallback_on_llm_failure() -> None:
    """Проверяет Dead-Letter сценарий: при сбое LLM фиксируется api_error в инцидентах."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)
    failing_llm = MockAuditLlmClient(fail_times=10)

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        evaluator=failing_llm,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )

    _, _, ticket = _build_test_ticket()
    ticket_repo.add_ticket(ticket)

    res = await service.audit_ticket_quality(ticket.id)
    assert res["status"] == "llm_evaluation_failed"

    # Проверяем, что в ticket_audits не записано битых данных
    audit = await analytics_repo.get_audit_by_ticket_id(ticket.id)
    assert audit is None

    # Но в system_incidents зарегистрирован сбой сервиса аналитики
    incident = await analytics_repo.get_open_incident_by_type(
        IncidentType.API_ERROR.value
    )
    assert incident is not None
    assert incident.ticket_id == ticket.id


@pytest.mark.asyncio
async def test_save_feedback_and_validation() -> None:
    """Проверяет сохранение отзыва и бизнес-правила (повторный отзыв, чужой тикет, незавершенный)."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)

    service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )

    client, _, ticket = _build_test_ticket(status=TicketStatus.RESOLVED.value)
    ticket_repo.add_ticket(ticket)

    # 1. Успешное сохранение отзыва
    with patch.object(
        service, "_safe_enqueue_audit", new_callable=AsyncMock
    ) as mock_enqueue:
        fb = await service.save_feedback(
            user_id=client.id,
            ticket_id=ticket.id,
            score=5,
            comment="Все отлично",
        )
        assert fb.score == 5
        assert fb.ticket_id == ticket.id
        mock_enqueue.assert_awaited_once_with(
            ticket_id=ticket.id, trigger_reason="feedback_received"
        )

    # 2. Попытка повторной отправки отзыва -> 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        await service.save_feedback(
            user_id=client.id, ticket_id=ticket.id, score=4
        )
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    # 3. Попытка оценить незавершенный тикет -> 400 Bad Request
    _, _, in_progress_ticket = _build_test_ticket(
        status=TicketStatus.IN_PROGRESS.value
    )
    ticket_repo.add_ticket(in_progress_ticket)
    with pytest.raises(HTTPException) as exc_info:
        await service.save_feedback(
            user_id=in_progress_ticket.chat.client_id,
            ticket_id=in_progress_ticket.id,
            score=5,
        )
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Попытка оценить чужой тикет -> 404 Not Found
    other_user_id = uuid6.uuid7()
    with pytest.raises(HTTPException) as exc_info:
        await service.save_feedback(
            user_id=other_user_id, ticket_id=ticket.id, score=5
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# =========================================================================
# 4. Тесты интеграции с check_system_timeouts
# =========================================================================


@pytest.mark.asyncio
async def test_check_timeouts_enqueues_unreviewed_tickets() -> None:
    """Проверяет регламент QUEUES_SPECIFICATION §4: тикеты закрытые >10 мин без отзыва уходят на аудит."""
    now = datetime.now(settings.TIMEZONE)
    closed_12m_ago = now - timedelta(minutes=12)

    ticket_repo = InMemoryTicketRepository()
    _, _, ticket = _build_test_ticket(
        status=TicketStatus.RESOLVED.value,
        closed_at=closed_12m_ago,
    )
    ticket_repo.add_ticket(ticket)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_redis = MockRedis()
    mock_op_repo = AsyncMock()
    mock_op_repo.get_offline_operators_with_active_assignments.return_value = []
    mock_line_repo = AsyncMock()
    mock_line_queue = AsyncMock()
    mock_redis_events = AsyncMock()
    mock_ticket_events = AsyncMock()
    mock_chat_context = AsyncMock()

    op_service = OperatorService(
        session=mock_session,
        redis=mock_redis,
        operator_repo=mock_op_repo,
        support_line_repo=mock_line_repo,
        ticket_repo=ticket_repo,
        line_queue=mock_line_queue,
        redis_events=mock_redis_events,
        ticket_events=mock_ticket_events,
        chat_context=mock_chat_context,
    )

    with patch.object(
        op_service, "_safe_enqueue_audit", new_callable=AsyncMock
    ) as mock_enqueue:
        res = await op_service.check_timeouts(now=now)
        assert res.tickets_sent_to_audit >= 1
        mock_enqueue.assert_awaited()


# =========================================================================
# 5. Тест REST API: POST /api/v1/chat/tickets/{id}/feedback
# =========================================================================


@pytest.mark.asyncio
async def test_client_feedback_rest_endpoint() -> None:
    """Проверяет вызов HTTP POST /api/v1/chat/tickets/{id}/feedback клиентом."""
    ticket_repo = InMemoryTicketRepository()
    analytics_repo = InMemoryAnalyticsRepository(ticket_repo=ticket_repo)
    redis_mock = MockRedis()
    mock_session = AsyncMock(spec=AsyncSession)

    client_user, _, ticket = _build_test_ticket(
        status=TicketStatus.RESOLVED.value
    )
    client_user.role = RoleModel(id=1, code="client", name="Клиент")
    ticket_repo.add_ticket(ticket)

    analytics_service = AnalyticsService(
        session=mock_session,
        redis=redis_mock,
        analytics_repo=analytics_repo,
        ticket_repo=ticket_repo,
    )

    async def override_get_current_user() -> UserModel:
        return client_user

    async def override_get_analytics_service() -> AnalyticsService:
        return analytics_service

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_analytics_service] = (
        override_get_analytics_service
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        with patch.object(
            analytics_service, "_safe_enqueue_audit", new_callable=AsyncMock
        ):
            # Успешный отзыв
            resp = await ac.post(
                f"/api/v1/chat/tickets/{ticket.id}/feedback",
                json={"score": 5, "comment": "Очень помогли!"},
                headers={"Authorization": "Bearer fake_token"},
            )
            assert resp.status_code == status.HTTP_201_CREATED
            data = resp.json()
            assert data["ticket_id"] == str(ticket.id)
            assert data["score"] == 5
            assert data["comment"] == "Очень помогли!"

            # Повторный отзыв -> 409 Conflict
            resp_dup = await ac.post(
                f"/api/v1/chat/tickets/{ticket.id}/feedback",
                json={"score": 4, "comment": "Повтор"},
                headers={"Authorization": "Bearer fake_token"},
            )
            assert resp_dup.status_code == status.HTTP_409_CONFLICT

    app.dependency_overrides.clear()
