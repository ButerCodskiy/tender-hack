"""Интеграционные тесты сервиса распределения обращений и фоновой задачи Taskiq."""

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import redis.asyncio as aioredis
import uuid6
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import ClientProfileModel, RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.core.config import settings
from src.core.redis_client import (
    RedisDistributedLock,
    RedisLineQueue,
)
from src.db.database import Base, async_session_maker, engine
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)
from src.operators.schemas import DispatchPayloadSchema
from src.operators.service import OperatorService
from src.operators.tasks import dispatch_line_queue


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Очищает таблицы базы данных перед и после каждого теста."""
    tables_to_truncate = (
        "messages, message_sources, tickets, chats, "
        "client_profiles, operator_profiles, support_lines, users, roles"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                f"TRUNCATE TABLE {tables_to_truncate} RESTART IDENTITY CASCADE;"
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"TRUNCATE TABLE {tables_to_truncate} RESTART IDENTITY CASCADE;"
            )
        )


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Предоставляет изолированную сессию базы данных."""
    async with async_session_maker() as s:
        yield s


@pytest.fixture
async def base_setup(
    session: AsyncSession,
) -> tuple[RoleModel, SupportLineModel, UserModel]:
    """Создает базовые роли, линию поддержки и тестового клиента."""
    role = RoleModel(id=2, code="operator", name="Оператор поддержки")
    client_role = RoleModel(id=1, code="client", name="Клиент")
    session.add_all([role, client_role])
    await session.flush()

    line = SupportLineModel(
        code="L1",
        name="Первая линия",
        description="Консультации и общие вопросы",
    )
    session.add(line)

    client_user = UserModel(
        id=uuid6.uuid7(),
        email="client@example.com",
        password_hash="hash",
        full_name="Тестовый Заказчик",
        role_id=client_role.id,
    )
    session.add(client_user)
    await session.flush()

    client_profile = ClientProfileModel(
        user_id=client_user.id,
        company_name="ПАО Поставщик",
        inn="7701234567",
    )
    session.add(client_profile)
    await session.flush()

    await session.commit()
    return role, line, client_user


async def create_operator(
    session: AsyncSession,
    role_id: int,
    line_id: int,
    email: str,
    name: str,
    shift_status: str = OperatorShiftStatus.ACTIVE,
    max_slots: int = 5,
    last_assigned_at: datetime | None = None,
    disconnected_at: datetime | None = None,
) -> OperatorProfileModel:
    """Вспомогательная функция создания пользователя-оператора и его профиля."""
    user = UserModel(
        id=uuid6.uuid7(),
        email=email,
        password_hash="hash",
        full_name=name,
        role_id=role_id,
    )
    session.add(user)
    await session.flush()

    profile = OperatorProfileModel(
        user_id=user.id,
        line_id=line_id,
        shift_status=shift_status,
        max_slots=max_slots,
        last_assigned_at=last_assigned_at,
        disconnected_at=disconnected_at,
    )
    session.add(profile)
    await session.flush()
    await session.commit()
    return profile


async def create_ticket(
    session: AsyncSession,
    client_id: uuid6.UUID,
    line_id: int,
    status: str = TicketStatus.QUEUED,
    priority: str = TicketPriority.P2,
    assigned_operator_id: uuid6.UUID | None = None,
) -> TicketModel:
    """Вспомогательная функция получения чата и создания тикета."""
    stmt = select(ChatModel).where(ChatModel.client_id == client_id)
    chat = (await session.scalars(stmt)).first()
    if chat is None:
        chat = ChatModel(id=uuid6.uuid7(), client_id=client_id)
        session.add(chat)
        await session.flush()

    ticket = TicketModel(
        id=uuid6.uuid7(),
        chat_id=chat.id,
        line_id=line_id,
        status=status,
        priority=priority,
        assigned_operator_id=assigned_operator_id,
        created_at=datetime.now(settings.TIMEZONE),
    )
    session.add(ticket)
    await session.flush()

    msg = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=ticket.id,
        sender_type=MessageSenderType.CLIENT,
        sender_id=client_id,
        text=f"Вопрос с приоритетом {priority}",
        moderation_status=MessageModerationStatus.PASSED,
        created_at=datetime.now(settings.TIMEZONE),
    )
    session.add(msg)
    await session.flush()

    await session.commit()
    return ticket


async def test_redis_distributed_lock_lifecycle_and_contention(
    redis_client: aioredis.Redis,
) -> None:
    """Проверяет захват, исключение конкуренции и безопасное освобождение блокировки."""
    lock_key = "lock:dispatch:line:TEST_LOCK"
    await redis_client.delete(lock_key)

    # 1. Первый процесс захватывает блокировку
    lock1 = RedisDistributedLock(
        redis=redis_client, key=lock_key, ttl_seconds=5
    )
    acquired1 = await lock1.acquire()
    assert acquired1 is True
    assert lock1.acquired is True

    # Ключ присутствует в Redis со значением токена первого процесса
    val = await redis_client.get(lock_key)
    assert val == lock1.token
    ttl = await redis_client.ttl(lock_key)
    assert 0 < ttl <= 5

    # 2. Второй процесс пытается захватить тот же ключ — получает отказ
    lock2 = RedisDistributedLock(
        redis=redis_client, key=lock_key, ttl_seconds=5
    )
    acquired2 = await lock2.acquire()
    assert acquired2 is False
    assert lock2.acquired is False

    # 3. Второй процесс пытается освободить чужую блокировку — ключ сохраняется
    released2 = await lock2.release()
    assert released2 is False
    assert await redis_client.get(lock_key) == lock1.token

    # 4. Первый процесс освобождает блокировку — ключ атомарно удаляется
    released1 = await lock1.release()
    assert released1 is True
    assert await redis_client.get(lock_key) is None


async def test_redis_distributed_lock_context_manager(
    redis_client: aioredis.Redis,
) -> None:
    """Проверяет работу контекстного менеджера `async with lock as acquired`."""
    lock_key = "lock:dispatch:line:TEST_CM"
    await redis_client.delete(lock_key)

    async with RedisDistributedLock(
        redis=redis_client, key=lock_key, ttl_seconds=5
    ) as acquired:
        assert acquired is True
        # Внутри контекста ключ существует
        assert await redis_client.exists(lock_key) == 1

    # По выходу из контекста ключ автоматически освобожден
    assert await redis_client.exists(lock_key) == 0


async def test_dispatch_line_empty_queue(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """При пустой очереди метод возвращает 0 назначений со статусом queue_empty."""
    _, line, _ = base_setup
    queue_mgr = RedisLineQueue(redis=redis_client)
    await queue_mgr.clear_queue(line.code)

    service = OperatorService(session=session, redis=redis_client)
    result = await service.dispatch_line(line.code)

    assert result.line_code == line.code
    assert result.assigned_count == 0
    assert result.assigned_ticket_ids == []
    assert result.stop_reason == "queue_empty"

    # Блокировка снята
    assert await redis_client.exists(f"lock:dispatch:line:{line.code}") == 0


async def test_dispatch_line_line_not_found(
    session: AsyncSession,
    redis_client: aioredis.Redis,
) -> None:
    """При отсутствии линии поддержки метод возвращает статус line_not_found."""
    service = OperatorService(session=session, redis=redis_client)
    result = await service.dispatch_line("NON_EXISTENT_LINE")

    assert result.assigned_count == 0
    assert result.stop_reason == "line_not_found"


async def test_dispatch_line_lock_busy(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """При занятой блокировке метод не начинает сопоставление и возвращает lock_busy."""
    _, line, _ = base_setup
    lock_key = f"lock:dispatch:line:{line.code}"
    await redis_client.set(lock_key, "busy_worker", ex=10)

    try:
        service = OperatorService(session=session, redis=redis_client)
        result = await service.dispatch_line(line.code)

        assert result.assigned_count == 0
        assert result.stop_reason == "lock_busy"
    finally:
        await redis_client.delete(lock_key)


async def test_dispatch_line_priority_assignment_and_least_loaded(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Проверяет сквозное распределение: тикет P0 назначается наименее загруженному оператору."""
    role, line, client = base_setup
    queue_mgr = RedisLineQueue(redis=redis_client)
    await queue_mgr.clear_queue(line.code)

    # 1. Создаем двух операторов:
    # op1 свободен (0 активных слотов)
    op1 = await create_operator(
        session, role.id, line.id, "op1@test.ru", "Оператор 1", max_slots=5
    )
    # op2 имеет 1 активный тикет (1 занятый слот)
    op2 = await create_operator(
        session, role.id, line.id, "op2@test.ru", "Оператор 2", max_slots=5
    )
    await create_ticket(
        session,
        client.id,
        line.id,
        status=TicketStatus.IN_PROGRESS,
        assigned_operator_id=op2.user_id,
    )

    # 2. Создаем три тикета: P2, P1, P0
    t_p2 = await create_ticket(
        session, client.id, line.id, priority=TicketPriority.P2
    )
    t_p1 = await create_ticket(
        session, client.id, line.id, priority=TicketPriority.P1
    )
    t_p0 = await create_ticket(
        session, client.id, line.id, priority=TicketPriority.P0
    )

    # 3. Помещаем в очередь Redis:
    # P2 -> конец, P1 -> конец, P0 -> начало (LPUSH)
    await queue_mgr.enqueue_ticket(line.code, t_p2.id, priority="P2")
    await queue_mgr.enqueue_ticket(line.code, t_p1.id, priority="P1")
    await queue_mgr.enqueue_ticket(line.code, t_p0.id, priority="P0")

    # В голове очереди должен быть тикет P0
    assert await queue_mgr.peek_tickets(line.code, 0, 0) == [str(t_p0.id)]

    # 4. Запускаем распределение
    service = OperatorService(session=session, redis=redis_client)
    result = await service.dispatch_line(line.code)

    assert result.assigned_count == 3
    assert result.stop_reason == "queue_empty"
    assert result.assigned_ticket_ids[0] == t_p0.id

    # 5. Проверяем назначения в базе данных
    async with async_session_maker() as verify_session:
        # P0 должен достаться наименее загруженному op1 (у него было 0 слотов)
        p0_db = await verify_session.get(TicketModel, t_p0.id)
        assert p0_db is not None
        assert p0_db.status == TicketStatus.ASSIGNED
        assert p0_db.assigned_operator_id == op1.user_id

        # Очередь в Redis полностью разобрана
        assert await queue_mgr.get_queue_len(line.code) == 0

    # 6. Блокировка линии снята
    assert await redis_client.exists(f"lock:dispatch:line:{line.code}") == 0


async def test_dispatch_line_operators_exhausted_requeue(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """При исчерпании свободных операторов тикет возвращается в начало очереди через LPUSH."""
    role, line, client = base_setup
    queue_mgr = RedisLineQueue(redis=redis_client)
    await queue_mgr.clear_queue(line.code)

    # 1 оператор с 1 доступным слотом
    op = await create_operator(
        session, role.id, line.id, "busy_op@test.ru", "Занятой", max_slots=1
    )

    # Создаем 2 тикета
    t1 = await create_ticket(session, client.id, line.id, priority="P1")
    t2 = await create_ticket(session, client.id, line.id, priority="P2")

    await queue_mgr.enqueue_ticket(line.code, t1.id, priority="P1")
    await queue_mgr.enqueue_ticket(line.code, t2.id, priority="P2")

    service = OperatorService(session=session, redis=redis_client)
    result = await service.dispatch_line(line.code)

    # Первый тикет назначен, второй вернулся в очередь
    assert result.assigned_count == 1
    assert result.assigned_ticket_ids == [t1.id]
    assert result.stop_reason == "no_operators"

    # Второй тикет сохранен в голове очереди Redis
    assert await queue_mgr.get_queue_len(line.code) == 1
    assert await queue_mgr.peek_tickets(line.code) == [str(t2.id)]

    async with async_session_maker() as verify_session:
        t1_db = await verify_session.get(TicketModel, t1.id)
        assert t1_db is not None
        assert t1_db.status == TicketStatus.ASSIGNED
        assert t1_db.assigned_operator_id == op.user_id

        t2_db = await verify_session.get(TicketModel, t2.id)
        assert t2_db is not None
        assert t2_db.status == TicketStatus.QUEUED
        assert t2_db.assigned_operator_id is None


async def test_dispatch_line_skips_invalid_and_non_queued_tickets(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Невалидные тикеты или тикеты не в статусе queued пропускаются без возврата в очередь."""
    role, line, client = base_setup
    queue_mgr = RedisLineQueue(redis=redis_client)
    await queue_mgr.clear_queue(line.code)

    await create_operator(
        session, role.id, line.id, "op@test.ru", "Оператор", max_slots=5
    )

    # 1. Битый UUID
    await redis_client.rpush(f"queue:line:{line.code}", "not-a-valid-uuid")

    # 2. Несуществующий тикет
    ghost_id = uuid6.uuid7()
    await redis_client.rpush(f"queue:line:{line.code}", str(ghost_id))

    # 3. Тикет уже в статусе resolved
    resolved_ticket = await create_ticket(
        session, client.id, line.id, status=TicketStatus.RESOLVED
    )
    await redis_client.rpush(
        f"queue:line:{line.code}", str(resolved_ticket.id)
    )

    # 4. Валидный тикет в статусе queued
    valid_ticket = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )
    await redis_client.rpush(f"queue:line:{line.code}", str(valid_ticket.id))

    service = OperatorService(session=session, redis=redis_client)
    result = await service.dispatch_line(line.code)

    assert result.assigned_count == 1
    assert result.assigned_ticket_ids == [valid_ticket.id]
    assert result.stop_reason == "queue_empty"
    assert await queue_mgr.get_queue_len(line.code) == 0


async def test_taskiq_dispatch_line_queue_task_e2e(
    session: AsyncSession,
    redis_client: aioredis.Redis,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Проверяет выполнение фоновой задачи Taskiq dispatch_line_queue."""
    role, line, client = base_setup
    queue_mgr = RedisLineQueue(redis=redis_client)
    await queue_mgr.clear_queue(line.code)

    op = await create_operator(
        session,
        role.id,
        line.id,
        "taskiq_op@test.ru",
        "Taskiq Оператор",
        max_slots=5,
    )
    ticket = await create_ticket(session, client.id, line.id, priority="P0")
    await queue_mgr.enqueue_ticket(line.code, ticket.id, priority="P0")

    payload = DispatchPayloadSchema(
        line_code=line.code, trigger_reason="ticket_escalated"
    )

    # Запускаем фоновую задачу напрямую
    task_res = await dispatch_line_queue(payload=payload)

    assert task_res["line_code"] == line.code
    assert task_res["assigned_count"] == 1
    assert task_res["assigned_ticket_ids"] == [str(ticket.id)]
    assert task_res["stop_reason"] == "queue_empty"

    async with async_session_maker() as verify_session:
        db_ticket = await verify_session.get(TicketModel, ticket.id)
        assert db_ticket is not None
        assert db_ticket.status == TicketStatus.ASSIGNED
        assert db_ticket.assigned_operator_id == op.user_id

    # Проверяем, что блокировка освобождена
    assert await redis_client.exists(f"lock:dispatch:line:{line.code}") == 0
