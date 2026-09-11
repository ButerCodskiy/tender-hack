"""Тесты аварийного восстановления очередей тикетов из PostgreSQL в Redis (MED-09)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import uuid6

from src.chat.models import TicketModel, TicketPriority, TicketStatus
from src.core.config import settings
from src.core.redis_client import RedisLineQueue
from src.operators.models import SupportLineModel
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.service import OperatorService


class MockDistributedLock:
    """Мок распределенного замка для тестирования асинхронного контекстного менеджера."""

    def __init__(self, acquired: bool = True) -> None:
        self.acquired = acquired

    async def __aenter__(self) -> bool:
        return self.acquired

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


@pytest.fixture
def mock_operator_service() -> tuple[
    OperatorService,
    AsyncMock,  # operator_repo
    AsyncMock,  # support_line_repo
    AsyncMock,  # line_queue
]:
    """Создает изолированный инстанс OperatorService с замоканными репозиториями и очередями."""
    session = AsyncMock()
    redis = AsyncMock()
    operator_repo = AsyncMock(spec=OperatorRepository)
    support_line_repo = AsyncMock(spec=SupportLineRepository)
    line_queue = AsyncMock(spec=RedisLineQueue)

    service = OperatorService(
        session=session,
        redis=redis,
        operator_repo=operator_repo,
        support_line_repo=support_line_repo,
        line_queue=line_queue,
    )
    return service, operator_repo, support_line_repo, line_queue


@pytest.mark.asyncio
async def test_recover_queued_tickets_order_and_dispatch(
    mock_operator_service: tuple[
        OperatorService, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет восстановление очереди в правильном порядке приоритетов (P0 -> P1 -> P2, FIFO) и триггер диспетчеризации."""
    service, operator_repo, support_line_repo, line_queue = (
        mock_operator_service
    )

    # 1. Настраиваем активные линии
    line_l1 = SupportLineModel(id=1, code="L1", name="Линия 1", is_active=True)
    line_l2 = SupportLineModel(id=2, code="L2", name="Линия 2", is_active=True)
    support_line_repo.get_all_active.return_value = [line_l1, line_l2]

    # Настраиваем распределенные замки
    line_queue.get_recovery_lock.return_value = MockDistributedLock(
        acquired=True
    )
    line_queue.get_dispatch_lock.side_effect = lambda line_code, **kwargs: (
        MockDistributedLock(acquired=True)
    )

    # 2. Настраиваем тикеты для L1 (отсортированные БД по priority ASC, created_at ASC)
    now = datetime.now(settings.TIMEZONE)
    t_p0_first = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority=TicketPriority.P0.value,
        created_at=now - timedelta(minutes=5),
    )
    t_p0_second = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority=TicketPriority.P0.value,
        created_at=now - timedelta(minutes=2),
    )
    t_p1 = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority=TicketPriority.P1.value,
        created_at=now - timedelta(minutes=10),
    )
    t_p2 = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority=TicketPriority.P2.value,
        created_at=now - timedelta(minutes=15),
    )

    operator_repo.get_queued_tickets_for_line.side_effect = lambda line_id: (
        [t_p0_first, t_p0_second, t_p1, t_p2] if line_id == 1 else []
    )

    # Мокаем фоновую задачу Taskiq
    service._safe_dispatch_task = AsyncMock()

    # 3. Выполняем восстановление
    result = await service.recover_queued_tickets_from_db()

    assert result["status"] == "success"
    assert result["recovered_lines"] == {"L1": 4, "L2": 0}

    # 4. Проверяем, что rebuild_line_queue вызван со строгим порядком тикетов
    expected_ids_l1 = [
        t_p0_first.id,
        t_p0_second.id,
        t_p1.id,
        t_p2.id,
    ]
    line_queue.rebuild_line_queue.assert_any_await("L1", expected_ids_l1)
    line_queue.rebuild_line_queue.assert_any_await("L2", [])

    # 5. Проверяем запуск диспетчеризации только для непустой линии
    service._safe_dispatch_task.assert_awaited_once_with(
        "L1", "queue_recovered"
    )


@pytest.mark.asyncio
async def test_recovery_lock_skips_concurrent_run(
    mock_operator_service: tuple[
        OperatorService, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет пропуск восстановления, если лок lock:queue_recovery уже занят другим процессом."""
    service, _, support_line_repo, line_queue = mock_operator_service

    # Замок занят
    line_queue.get_recovery_lock.return_value = MockDistributedLock(
        acquired=False
    )

    result = await service.recover_queued_tickets_from_db()

    assert result["status"] == "skipped"
    assert result["reason"] == "already_recovering"
    support_line_repo.get_all_active.assert_not_called()
    line_queue.rebuild_line_queue.assert_not_called()


@pytest.mark.asyncio
async def test_check_timeouts_reconciles_queue_on_desync(
    mock_operator_service: tuple[
        OperatorService, AsyncMock, AsyncMock, AsyncMock
    ],
) -> None:
    """Проверяет автоматическую сверку и восстановление очереди в задаче check_timeouts при расхождении длин."""
    service, operator_repo, support_line_repo, line_queue = (
        mock_operator_service
    )

    # Настраиваем репозитории для check_timeouts
    service.ticket_repo = AsyncMock()
    service.ticket_repo.get_inactive_bot_tickets.return_value = []
    service.ticket_repo.get_in_progress_tickets_with_messages.return_value = []
    service.ticket_repo.get_tickets_for_audit_timeout.return_value = []
    operator_repo.get_disconnected_operators.return_value = []

    # Линия 1: в БД 2 тикета, в Redis 0 тикетов (рассинхронизация!)
    line = SupportLineModel(id=1, code="L1", name="Линия 1", is_active=True)
    support_line_repo.get_all_active.return_value = [line]
    operator_repo.count_queued_tickets_by_lines.return_value = {1: 2}
    line_queue.get_queue_len.return_value = 0

    t1 = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority="P0",
    )
    t2 = TicketModel(
        id=uuid6.uuid7(),
        line_id=1,
        status=TicketStatus.QUEUED.value,
        priority="P1",
    )
    operator_repo.get_queued_tickets_for_line.return_value = [t1, t2]

    line_queue.get_dispatch_lock.return_value = MockDistributedLock(
        acquired=True
    )
    service._safe_dispatch_task = AsyncMock()

    check_res = await service.check_timeouts()

    # Проверяем, что очередь была восстановлена
    line_queue.rebuild_line_queue.assert_awaited_once_with(
        "L1", [t1.id, t2.id]
    )
    assert "L1" in check_res.affected_line_codes


@pytest.mark.asyncio
async def test_redis_line_queue_rebuild_pipeline() -> None:
    """Проверяет, что rebuild_line_queue выполняет DEL и RPUSH атомарно через pipeline."""
    fake_redis = MagicMock()
    pipe_mock = MagicMock()
    pipe_mock.execute = AsyncMock()
    pipe_ctx = MagicMock()
    pipe_ctx.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_ctx.__aexit__ = AsyncMock(return_value=None)
    fake_redis.pipeline.return_value = pipe_ctx

    line_queue = RedisLineQueue(redis=fake_redis)
    tid1 = uuid6.uuid7()
    tid2 = uuid6.uuid7()

    await line_queue.rebuild_line_queue("L1", [tid1, tid2])

    pipe_mock.delete.assert_called_once_with("queue:line:L1")
    pipe_mock.rpush.assert_called_once_with(
        "queue:line:L1", str(tid1), str(tid2)
    )
    pipe_mock.execute.assert_awaited_once()


def test_redis_line_queue_recovery_lock() -> None:
    """Проверяет создание правильного ключа распределенной блокировки recovery."""
    fake_redis = MagicMock()
    line_queue = RedisLineQueue(redis=fake_redis)
    lock = line_queue.get_recovery_lock(ttl_seconds=30)
    assert lock.key == "lock:queue_recovery"
    assert lock.ttl_seconds == 30
