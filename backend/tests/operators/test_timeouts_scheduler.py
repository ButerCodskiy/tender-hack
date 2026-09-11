"""Тесты планировщика таймаутов, контроля неактивности и связи операторов (HIGH-12)."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
import uuid6

from src.chat.models import (
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.repository import TicketRepository
from src.core.config import settings
from src.core.redis_client import (
    RedisChatContext,
    RedisLineQueue,
    RedisOperatorEvents,
    RedisTicketEvents,
)
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.schemas import CheckTimeoutsResult
from src.operators.service import OperatorService
from src.operators.tasks import check_system_timeouts


def make_mock_line(code: str = "L1") -> SupportLineModel:
    """Создает мок линии поддержки."""
    line = SupportLineModel(
        id=1, code=code, name=f"Линия {code}", is_active=True
    )
    return line


def make_mock_ticket(
    ticket_id: UUID | None = None,
    status: str = TicketStatus.BOT_PROCESSING.value,
    updated_at: datetime | None = None,
    line_code: str = "L1",
) -> TicketModel:
    """Создает мок тикета для тестов."""
    tid = ticket_id or uuid6.uuid7()
    line = make_mock_line(code=line_code)
    t = TicketModel(
        id=tid,
        chat_id=uuid6.uuid7(),
        line_id=1,
        priority=TicketPriority.P2.value,
        status=status,
        created_at=updated_at or datetime.now(settings.TIMEZONE),
        updated_at=updated_at or datetime.now(settings.TIMEZONE),
    )
    t.line = line
    t.messages = []
    return t


def make_mock_message(
    ticket_id: UUID,
    sender_type: str,
    text: str,
    created_at: datetime,
) -> MessageModel:
    """Создает мок сообщения для тикета."""
    return MessageModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        sender_type=sender_type,
        text=text,
        moderation_status=MessageModerationStatus.PASSED.value,
        created_at=created_at,
    )


@pytest.fixture
def mock_service_deps():
    """Предоставляет моки всех зависимостей OperatorService."""
    session = AsyncMock()
    redis = AsyncMock()
    operator_repo = AsyncMock(spec=OperatorRepository)
    support_line_repo = AsyncMock(spec=SupportLineRepository)
    ticket_repo = AsyncMock()
    line_queue = AsyncMock(spec=RedisLineQueue)
    redis_events = AsyncMock(spec=RedisOperatorEvents)
    ticket_events = AsyncMock(spec=RedisTicketEvents)
    chat_context = AsyncMock(spec=RedisChatContext)

    service = OperatorService(
        session=session,
        redis=redis,
        operator_repo=operator_repo,
        support_line_repo=support_line_repo,
        ticket_repo=ticket_repo,
        line_queue=line_queue,
        redis_events=redis_events,
        ticket_events=ticket_events,
        chat_context=chat_context,
    )
    # Мокаем вызов задачи Celery/Taskiq _safe_dispatch_task
    service._safe_dispatch_task = AsyncMock()
    return (
        service,
        ticket_repo,
        operator_repo,
        line_queue,
        chat_context,
        ticket_events,
    )


# =========================================================================
# 1. Тесты таймаута неактивности у бота (10 минут)
# =========================================================================


async def test_bot_inactivity_ticket_closed_and_context_cleared(
    mock_service_deps,
):
    """Тикет в bot_processing старше 10 минут закрывается, контекст удаляется, шлется событие."""
    service, ticket_repo, operator_repo, _, chat_context, ticket_events = (
        mock_service_deps
    )
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(
        status=TicketStatus.BOT_PROCESSING.value,
        updated_at=now - timedelta(minutes=11),
    )
    ticket_repo.get_inactive_bot_tickets.return_value = [ticket]
    ticket_repo.close_ticket_by_inactivity.return_value = True
    ticket_repo.get_in_progress_tickets_with_messages.return_value = []
    operator_repo.get_disconnected_operators.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.bot_tickets_closed == 1
    ticket_repo.close_ticket_by_inactivity.assert_called_once_with(
        ticket_id=ticket.id,
        cutoff=now - timedelta(minutes=10),
        now=now,
    )
    operator_repo.add_system_message.assert_called_once_with(
        ticket_id=ticket.id,
        text="Диалог завершен в связи с отсутствием активности.",
    )
    chat_context.clear_context.assert_called_once_with(ticket.id)
    ticket_events.publish_ticket_closed_inactivity.assert_called_once_with(
        ticket.id
    )


async def test_bot_inactivity_skipped_if_race_condition(mock_service_deps):
    """Если оптимистический UPDATE вернул False (гонка с клиентом), контекст не удаляется."""
    service, ticket_repo, operator_repo, _, chat_context, ticket_events = (
        mock_service_deps
    )
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(
        status=TicketStatus.BOT_PROCESSING.value,
        updated_at=now - timedelta(minutes=11),
    )
    ticket_repo.get_inactive_bot_tickets.return_value = [ticket]
    ticket_repo.close_ticket_by_inactivity.return_value = (
        False  # Клиент только что написал!
    )
    ticket_repo.get_in_progress_tickets_with_messages.return_value = []
    operator_repo.get_disconnected_operators.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.bot_tickets_closed == 0
    operator_repo.add_system_message.assert_not_called()
    chat_context.clear_context.assert_not_called()
    ticket_events.publish_ticket_closed_inactivity.assert_not_called()


# =========================================================================
# 2. Тесты таймаута неактивности у оператора (10 минут напоминание, 15 минут закрытие)
# =========================================================================


async def test_operator_inactivity_warning_sent_once(mock_service_deps):
    """Если последнее сообщение от оператора старше 10 минут, шлется напоминание «Вы еще здесь?»."""
    service, ticket_repo, operator_repo, _, _, ticket_events = (
        mock_service_deps
    )
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(status=TicketStatus.IN_PROGRESS.value)
    op_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.OPERATOR.value,
        text="Чем могу помочь?",
        created_at=now - timedelta(minutes=11),
    )
    ticket.messages = [op_msg]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = [ticket]
    operator_repo.get_disconnected_operators.return_value = []

    sys_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.SYSTEM.value,
        text="Вы еще здесь?",
        created_at=now,
    )
    operator_repo.add_system_message.return_value = sys_msg

    result = await service.check_timeouts(now=now)

    assert result.operator_warnings_sent == 1
    assert result.operator_tickets_closed == 0
    operator_repo.add_system_message.assert_called_once_with(
        ticket_id=ticket.id,
        text="Вы еще здесь?",
    )
    ticket_events.publish_new_message.assert_called_once()
    assert ticket.updated_at == now


async def test_operator_inactivity_no_spam_when_last_message_is_system(
    mock_service_deps,
):
    """Если последнее сообщение уже системное «Вы еще здесь?», спам не шлется на следующем такте."""
    service, ticket_repo, operator_repo, _, _, ticket_events = (
        mock_service_deps
    )
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(status=TicketStatus.IN_PROGRESS.value)
    op_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.OPERATOR.value,
        text="Чем могу помочь?",
        created_at=now - timedelta(minutes=12),
    )
    sys_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.SYSTEM.value,
        text="Вы еще здесь?",
        created_at=now
        - timedelta(minutes=2),  # Напоминание отправлено 2 минуты назад
    )
    ticket.messages = [op_msg, sys_msg]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = [ticket]
    operator_repo.get_disconnected_operators.return_value = []

    result = await service.check_timeouts(now=now)

    # Предупреждение повторно НЕ шлется, и тикет еще не закрывается (прошло 2 мин < 5 мин)
    assert result.operator_warnings_sent == 0
    assert result.operator_tickets_closed == 0
    operator_repo.add_system_message.assert_not_called()
    ticket_events.publish_new_message.assert_not_called()


async def test_operator_inactivity_closed_after_5_minutes_post_warning(
    mock_service_deps,
):
    """Если после напоминания клиент молчит >= 5 минут, тикет закрывается и слот освобождается."""
    service, ticket_repo, operator_repo, _, chat_context, ticket_events = (
        mock_service_deps
    )
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(
        status=TicketStatus.IN_PROGRESS.value, line_code="L1"
    )
    op_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.OPERATOR.value,
        text="Чем могу помочь?",
        created_at=now - timedelta(minutes=16),
    )
    sys_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.SYSTEM.value,
        text="Вы еще здесь?",
        created_at=now - timedelta(minutes=6),  # Прошло 6 минут с напоминания
    )
    ticket.messages = [op_msg, sys_msg]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = [ticket]
    ticket_repo.close_ticket_by_inactivity.return_value = True
    operator_repo.get_disconnected_operators.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.operator_tickets_closed == 1
    ticket_repo.close_ticket_by_inactivity.assert_called_once_with(
        ticket_id=ticket.id,
        cutoff=now - timedelta(minutes=5),
        now=now,
    )
    chat_context.clear_context.assert_called_once_with(ticket.id)
    ticket_events.publish_ticket_closed_inactivity.assert_called_once_with(
        ticket.id
    )
    assert "L1" in result.affected_line_codes
    service._safe_dispatch_task.assert_called_once_with(
        line_code="L1", trigger_reason="operator_disconnected"
    )


async def test_operator_inactivity_reset_when_client_replied(
    mock_service_deps,
):
    """Если клиент ответил после реплики оператора или системы, таймаут сбрасывается."""
    service, ticket_repo, operator_repo, _, _, _ = mock_service_deps
    now = datetime.now(settings.TIMEZONE)

    ticket = make_mock_ticket(status=TicketStatus.IN_PROGRESS.value)
    op_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.OPERATOR.value,
        text="Чем могу помочь?",
        created_at=now - timedelta(minutes=12),
    )
    client_msg = make_mock_message(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.CLIENT.value,
        text="Да, я тут!",
        created_at=now - timedelta(minutes=1),
    )
    ticket.messages = [op_msg, client_msg]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = [ticket]
    operator_repo.get_disconnected_operators.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.operator_warnings_sent == 0
    assert result.operator_tickets_closed == 0


# =========================================================================
# 3. Тесты контроля связи операторов (disconnected_at > 10 минут)
# =========================================================================


async def test_operator_disconnected_marked_offline_and_tickets_requeued(
    mock_service_deps,
):
    """Оператор с обрывом связи > 10 минут переводится в offline, тикеты возвращаются в очередь lines."""
    service, ticket_repo, operator_repo, line_queue, _, _ = mock_service_deps
    now = datetime.now(settings.TIMEZONE)

    op_user_id = uuid6.uuid7()
    op_profile = OperatorProfileModel(
        user_id=op_user_id,
        line_id=1,
        shift_status=OperatorShiftStatus.ACTIVE.value,
        disconnected_at=now - timedelta(minutes=11),
    )
    operator_repo.get_disconnected_operators.return_value = [op_profile]

    t1 = make_mock_ticket(line_code="L1")
    t2 = make_mock_ticket(line_code="L2")
    operator_repo.requeue_operator_tickets.return_value = [t1, t2]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.operators_marked_offline == 1
    assert result.tickets_requeued == 2
    assert sorted(result.affected_line_codes) == ["L1", "L2"]

    operator_repo.set_operator_offline.assert_called_once_with(op_user_id, now)
    operator_repo.requeue_operator_tickets.assert_called_once_with(
        operator_id=op_user_id, now=now
    )
    assert line_queue.requeue_to_head.call_count == 2
    # Проверяем, что для L1 и L2 запущена диспетчеризация
    assert service._safe_dispatch_task.call_count == 2


async def test_operator_disconnected_multiple_tickets_same_line_single_dispatch(
    mock_service_deps,
):
    """При возврате нескольких тикетов одной линии диспетчер триггерится ровно 1 раз (Thundering Herd)."""
    service, ticket_repo, operator_repo, line_queue, _, _ = mock_service_deps
    now = datetime.now(settings.TIMEZONE)

    op_user_id = uuid6.uuid7()
    op_profile = OperatorProfileModel(
        user_id=op_user_id,
        line_id=1,
        shift_status=OperatorShiftStatus.ACTIVE.value,
        disconnected_at=now - timedelta(minutes=11),
    )
    operator_repo.get_disconnected_operators.return_value = [op_profile]

    t1 = make_mock_ticket(line_code="L1")
    t2 = make_mock_ticket(line_code="L1")
    t3 = make_mock_ticket(line_code="L1")
    operator_repo.requeue_operator_tickets.return_value = [t1, t2, t3]

    ticket_repo.get_inactive_bot_tickets.return_value = []
    ticket_repo.get_in_progress_tickets_with_messages.return_value = []

    result = await service.check_timeouts(now=now)

    assert result.operators_marked_offline == 1
    assert result.tickets_requeued == 3
    assert result.affected_line_codes == ["L1"]
    assert line_queue.requeue_to_head.call_count == 3
    # Ровно один запуск задачи диспетчеризации для линии L1!
    service._safe_dispatch_task.assert_called_once_with(
        line_code="L1", trigger_reason="operator_disconnected"
    )


# =========================================================================
# 4. Тесты фоновой задачи check_system_timeouts и блокировки Redis
# =========================================================================


async def test_check_system_timeouts_task_skipped_when_lock_busy():
    """Если распределенная блокировка занята другим процессом, задача пропускается со статусом lock_busy."""
    fake_redis = AsyncMock()
    # Имитируем, что acquire() вернул False
    fake_lock = AsyncMock()
    fake_lock.__aenter__.return_value = False

    with (
        patch(
            "src.operators.tasks.aioredis.from_url", return_value=fake_redis
        ),
        patch(
            "src.operators.tasks.RedisDistributedLock", return_value=fake_lock
        ),
        patch("src.operators.tasks.OperatorService") as mock_service_cls,
    ):
        res = await check_system_timeouts()

    assert res == {"status": "skipped", "reason": "lock_busy"}
    mock_service_cls.assert_not_called()
    fake_redis.aclose.assert_called_once()


async def test_check_system_timeouts_task_success():
    """При свободном локе задача успешно выполняет проверку таймаутов и возвращает результат."""
    fake_redis = AsyncMock()
    fake_lock = AsyncMock()
    fake_lock.__aenter__.return_value = True

    expected_result = CheckTimeoutsResult(
        bot_tickets_closed=2,
        operator_warnings_sent=1,
        operator_tickets_closed=0,
        operators_marked_offline=1,
        tickets_requeued=3,
        affected_line_codes=["L1"],
    )

    mock_service_instance = AsyncMock()
    mock_service_instance.check_timeouts.return_value = expected_result

    with (
        patch(
            "src.operators.tasks.aioredis.from_url", return_value=fake_redis
        ),
        patch(
            "src.operators.tasks.RedisDistributedLock", return_value=fake_lock
        ),
        patch("src.operators.tasks.async_session_maker") as mock_session_maker,
        patch(
            "src.operators.tasks.OperatorService",
            return_value=mock_service_instance,
        ),
    ):
        mock_session_maker.return_value.__aenter__.return_value = AsyncMock()
        res = await check_system_timeouts()

    assert res["status"] == "success"
    assert res["result"]["bot_tickets_closed"] == 2
    assert res["result"]["affected_line_codes"] == ["L1"]
    fake_redis.aclose.assert_called_once()


async def test_check_system_timeouts_task_timeout_handling():
    """При превышении локального таймаута 20 секунд задача возвращает execution_timeout_exceeded."""
    fake_redis = AsyncMock()
    fake_lock = AsyncMock()
    fake_lock.__aenter__.return_value = True

    async def slow_check():
        await asyncio.sleep(0.05)
        raise TimeoutError()

    mock_service_instance = AsyncMock()
    mock_service_instance.check_timeouts.side_effect = TimeoutError()

    with (
        patch(
            "src.operators.tasks.aioredis.from_url", return_value=fake_redis
        ),
        patch(
            "src.operators.tasks.RedisDistributedLock", return_value=fake_lock
        ),
        patch("src.operators.tasks.async_session_maker") as mock_session_maker,
        patch(
            "src.operators.tasks.OperatorService",
            return_value=mock_service_instance,
        ),
    ):
        mock_session_maker.return_value.__aenter__.return_value = AsyncMock()
        res = await check_system_timeouts()

    assert res == {
        "status": "timeout",
        "reason": "execution_timeout_exceeded",
    }
    fake_redis.aclose.assert_called_once()


# =========================================================================
# 5. Тесты методов репозиториев (TicketRepository, OperatorRepository)
# =========================================================================


async def test_ticket_repo_close_ticket_by_inactivity_success():
    """Проверяет успешный атомарный conditional UPDATE закрытия тикета."""
    session = AsyncMock()
    repo = TicketRepository(session)
    mock_result = MagicMock()
    tid = uuid6.uuid7()
    mock_result.scalar_one_or_none.return_value = tid
    session.execute.return_value = mock_result

    now = datetime.now(settings.TIMEZONE)
    cutoff = now - timedelta(minutes=10)
    res = await repo.close_ticket_by_inactivity(tid, cutoff=cutoff, now=now)
    assert res is True
    session.execute.assert_called_once()
    session.flush.assert_called_once()


async def test_ticket_repo_close_ticket_by_inactivity_not_found():
    """Проверяет возврат False при несовпадении предиката (гонка)."""
    session = AsyncMock()
    repo = TicketRepository(session)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    now = datetime.now(settings.TIMEZONE)
    cutoff = now - timedelta(minutes=10)
    res = await repo.close_ticket_by_inactivity(
        uuid6.uuid7(), cutoff=cutoff, now=now
    )
    assert res is False


async def test_operator_repo_set_operator_offline():
    """Проверяет перевод профиля оператора в offline со сбросом disconnected_at."""
    session = AsyncMock()
    repo = OperatorRepository(session)
    user_id = uuid6.uuid7()
    profile = OperatorProfileModel(
        user_id=user_id,
        line_id=1,
        shift_status=OperatorShiftStatus.ACTIVE.value,
        disconnected_at=datetime.now(settings.TIMEZONE),
    )
    repo.get_by_user_id = AsyncMock(return_value=profile)

    now = datetime.now(settings.TIMEZONE)
    updated = await repo.set_operator_offline(user_id, now)
    assert updated.shift_status == OperatorShiftStatus.OFFLINE.value
    assert updated.disconnected_at is None
    assert updated.updated_at == now
    session.flush.assert_called_once()


async def test_operator_repo_requeue_operator_tickets():
    """Проверяет перевод незавершенных тикетов оператора в queued со сбросом закрепления."""
    session = AsyncMock()
    repo = OperatorRepository(session)
    user_id = uuid6.uuid7()
    t1 = make_mock_ticket(line_code="L1")
    t1.assigned_operator_id = user_id
    t1.status = TicketStatus.IN_PROGRESS.value

    mock_result = MagicMock()
    mock_result.all.return_value = [t1]
    session.scalars.return_value = mock_result

    now = datetime.now(settings.TIMEZONE)
    requeued = await repo.requeue_operator_tickets(user_id, now)
    assert len(requeued) == 1
    assert requeued[0].assigned_operator_id is None
    assert requeued[0].status == TicketStatus.QUEUED.value
    assert requeued[0].updated_at == now
    session.flush.assert_called_once()
