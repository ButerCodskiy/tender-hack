"""Интеграционные тесты атомарного балансировщика обращений и шины событий Redis."""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

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
from src.core.redis_client import RedisOperatorEvents
from src.db.database import Base, async_session_maker, engine
from src.operators.balancer import TicketBalancer
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)


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
    """Создает базовую роль, линию поддержки и тестового клиента с чатом."""
    role = RoleModel(id=2, code="operator", name="Оператор поддержки")
    client_role = RoleModel(id=1, code="client", name="Клиент")
    session.add_all([role, client_role])
    await session.flush()

    line = SupportLineModel(
        code="L1",
        name="Первая линия",
        description="Консультации",
    )
    session.add(line)

    client_user = UserModel(
        id=uuid6.uuid7(),
        email="client@example.com",
        password_hash="hash",
        full_name="Тестовый Клиент",
        role_id=client_role.id,
    )
    session.add(client_user)
    await session.flush()

    client_profile = ClientProfileModel(
        user_id=client_user.id,
        company_name="ООО Ромашка",
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
    with_message: bool = True,
) -> TicketModel:
    """Вспомогательная функция получения чата и создания тикета и сообщения."""
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

    if with_message:
        msg = MessageModel(
            id=uuid6.uuid7(),
            ticket_id=ticket.id,
            sender_type=MessageSenderType.CLIENT,
            sender_id=client_id,
            text="Тестовый вопрос по регламенту закупки",
            moderation_status=MessageModerationStatus.PASSED,
            created_at=datetime.now(settings.TIMEZONE),
        )
        session.add(msg)
        await session.flush()

    await session.commit()
    return ticket


async def test_balancer_selects_least_loaded_operator(
    session: AsyncSession,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Балансировщик выбирает оператора с наименьшим числом активных слотов."""
    role, line, client = base_setup

    # Создаем двух операторов
    op1 = await create_operator(
        session, role.id, line.id, "op1@mos.ru", "Оператор 1"
    )
    op2 = await create_operator(
        session, role.id, line.id, "op2@mos.ru", "Оператор 2"
    )

    # У второго оператора уже есть 1 активный тикет в in_progress
    await create_ticket(
        session,
        client.id,
        line.id,
        status=TicketStatus.IN_PROGRESS,
        assigned_operator_id=op2.user_id,
    )

    # Создаем тикет в очереди для распределения
    ticket_to_assign = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )

    balancer = TicketBalancer(session=session)
    result = await balancer.assign_ticket(ticket_to_assign.id)

    assert result.success is True
    assert result.operator is not None
    # Должен быть выбран первый оператор (0 слотов против 1 слота)
    assert result.operator.user_id == op1.user_id
    assert result.ticket is not None
    assert result.ticket.status == TicketStatus.ASSIGNED
    assert result.ticket.assigned_operator_id == op1.user_id
    assert result.ticket.assigned_at is not None


async def test_balancer_equal_load_sorts_by_oldest_assigned_or_null(
    session: AsyncSession,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """При равной загрузке приоритет у специалиста с NULL или более давней меткой назначения."""
    role, line, client = base_setup
    now = datetime.now(settings.TIMEZONE)

    # 1. Сравнение: NULL против существующей метки
    await create_operator(
        session,
        role.id,
        line.id,
        "recent@mos.ru",
        "Недавно назначенный",
        last_assigned_at=now - timedelta(minutes=5),
    )
    op_never_assigned = await create_operator(
        session,
        role.id,
        line.id,
        "never@mos.ru",
        "Ни разу не назначался",
        last_assigned_at=None,
    )

    t1 = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )
    balancer = TicketBalancer(session=session)
    res1 = await balancer.assign_ticket(t1.id)

    assert res1.success is True
    # NULL имеет наивысший приоритет (NULLS FIRST)
    assert res1.operator.user_id == op_never_assigned.user_id

    # 2. Сравнение: более давняя метка против свежей метки
    op_older = await create_operator(
        session,
        role.id,
        line.id,
        "older@mos.ru",
        "Давно назначенный",
        last_assigned_at=now - timedelta(hours=2),
    )
    # op_assigned_recently имеет метку 5 минут назад
    t2 = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )
    res2 = await balancer.assign_ticket(t2.id)

    assert res2.success is True
    assert res2.operator.user_id == op_older.user_id


async def test_balancer_filters_inactive_and_busy_operators(
    session: AsyncSession,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Балансировщик игнорирует операторов на перерыве, оффлайн, с разрывом связи и без слотов."""
    role, line, client = base_setup
    now = datetime.now(settings.TIMEZONE)

    # 1. Оператор на перерыве
    await create_operator(
        session,
        role.id,
        line.id,
        "break@mos.ru",
        "На перерыве",
        shift_status=OperatorShiftStatus.BREAK,
    )

    # 2. Оператор оффлайн
    await create_operator(
        session,
        role.id,
        line.id,
        "offline@mos.ru",
        "Оффлайн",
        shift_status=OperatorShiftStatus.OFFLINE,
    )

    # 3. Оператор с разрывом соединения (disconnected_at)
    await create_operator(
        session,
        role.id,
        line.id,
        "disconnected@mos.ru",
        "Связь разорвана",
        shift_status=OperatorShiftStatus.ACTIVE,
        disconnected_at=now - timedelta(minutes=2),
    )

    # 4. Оператор с заполненными слотами (max_slots = 1 и 1 активный тикет)
    op_full = await create_operator(
        session,
        role.id,
        line.id,
        "full@mos.ru",
        "Все слоты заняты",
        shift_status=OperatorShiftStatus.ACTIVE,
        max_slots=1,
    )
    await create_ticket(
        session,
        client.id,
        line.id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=op_full.user_id,
    )

    # 5. Единственный доступный оператор
    op_available = await create_operator(
        session,
        role.id,
        line.id,
        "available@mos.ru",
        "Доступный оператор",
        shift_status=OperatorShiftStatus.ACTIVE,
        max_slots=3,
    )

    t = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )
    balancer = TicketBalancer(session=session)
    res = await balancer.assign_ticket(t.id)

    assert res.success is True
    assert res.operator.user_id == op_available.user_id


async def test_balancer_returns_failure_when_no_operators_available(
    session: AsyncSession,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """При отсутствии доступных операторов тикет остается в очереди."""
    role, line, client = base_setup

    # Все операторы оффлайн
    await create_operator(
        session,
        role.id,
        line.id,
        "off@mos.ru",
        "Оффлайн оператор",
        shift_status=OperatorShiftStatus.OFFLINE,
    )

    t = await create_ticket(
        session, client.id, line.id, status=TicketStatus.QUEUED
    )

    balancer = TicketBalancer(session=session)
    res = await balancer.assign_ticket(t.id)

    assert res.success is False
    assert res.reason == "no_operators_available"
    assert res.operator is None

    # Проверяем, что статус тикета в базе не изменился
    reloaded_ticket = await session.get(TicketModel, t.id)
    assert reloaded_ticket is not None
    assert reloaded_ticket.status == TicketStatus.QUEUED
    assert reloaded_ticket.assigned_operator_id is None


async def test_balancer_publishes_event_to_redis_pubsub(
    session: AsyncSession,
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
    redis_client: aioredis.Redis,
) -> None:
    """После фиксации в базе событие ticket_assigned доставляется в канал оператора."""
    role, line, client = base_setup

    op = await create_operator(
        session, role.id, line.id, "pubsub_op@mos.ru", "Оператор Пубсаб"
    )
    ticket = await create_ticket(
        session,
        client.id,
        line.id,
        status=TicketStatus.QUEUED,
        priority=TicketPriority.P0,
    )

    channel_name = f"channel:operator:{op.user_id}"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)

    # Даем подписке активироваться в брокере
    await asyncio.sleep(0.05)

    redis_events = RedisOperatorEvents(redis=redis_client)
    balancer = TicketBalancer(session=session, redis_events=redis_events)

    res = await balancer.assign_ticket(ticket.id)
    assert res.success is True
    assert res.operator.user_id == op.user_id

    # Читаем сообщение из канала Redis
    received_message = None
    # Игнорируем техническое сообщение о подтверждении подписки
    for _ in range(5):
        msg = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=2.0
        )
        if msg is not None:
            received_message = msg
            break
        await asyncio.sleep(0.1)

    await pubsub.unsubscribe(channel_name)
    await pubsub.close()

    assert received_message is not None
    assert received_message["type"] == "message"
    data_dict = json.loads(received_message["data"])
    assert data_dict["event"] == "ticket_assigned"
    payload = data_dict["data"]
    assert payload["ticket_id"] == str(ticket.id)
    assert payload["priority"] == "P0"
    assert payload["status"] == "assigned"
    assert payload["line_code"] == "L1"
    assert payload["client_name"] == "Тестовый Клиент"
    assert payload["company_name"] == "ООО Ромашка"
    assert "Тестовый вопрос" in payload["last_message_preview"]


async def test_balancer_concurrent_assignment_respects_max_slots(
    base_setup: tuple[RoleModel, SupportLineModel, UserModel],
) -> None:
    """Конкурентные вызовы assign_ticket соблюдают лимиты слотов без гонок и дедлоков."""
    role, line, _ = base_setup

    # Создаем двух операторов с жестким лимитом слотов: по 2 слота каждый (итого 4 слота)
    async with async_session_maker() as init_session:
        op1 = await create_operator(
            init_session,
            role.id,
            line.id,
            "c_op1@mos.ru",
            "Конкурентный 1",
            max_slots=2,
        )
        op2 = await create_operator(
            init_session,
            role.id,
            line.id,
            "c_op2@mos.ru",
            "Конкурентный 2",
            max_slots=2,
        )

        client_role = (
            await init_session.scalars(
                select(RoleModel).where(RoleModel.code == "client")
            )
        ).first()

        # Создаем 5 тикетов в очереди от разных клиентов (доступно только 4 слота)
        tickets = []
        for i in range(5):
            c_user = UserModel(
                id=uuid6.uuid7(),
                email=f"client_{i}@example.com",
                password_hash="hash",
                full_name=f"Клиент {i}",
                role_id=client_role.id,
            )
            init_session.add(c_user)
            await init_session.flush()
            t = await create_ticket(
                init_session, c_user.id, line.id, status=TicketStatus.QUEUED
            )
            tickets.append(t)

    # Функция параллельного распределения тикета в отдельной сессии
    async def assign_single(t_id: uuid6.UUID) -> bool:
        async with async_session_maker() as s:
            b = TicketBalancer(session=s)
            res = await b.assign_ticket(t_id)
            return res.success

    # Запускаем одновременное распределение всех 5 тикетов
    results = await asyncio.gather(*(assign_single(t.id) for t in tickets))

    # Из 5 тикетов ровно 4 должны успешно распределиться, а 1 получить отказ
    assert results.count(True) == 4
    assert results.count(False) == 1

    # Проверяем итоговую загрузку операторов в базе данных
    async with async_session_maker() as check_session:
        op1_tickets = (
            await check_session.scalars(
                text(
                    f"SELECT id FROM tickets WHERE assigned_operator_id = '{op1.user_id}' "
                    "AND status = 'assigned';"
                )
            )
        ).all()
        op2_tickets = (
            await check_session.scalars(
                text(
                    f"SELECT id FROM tickets WHERE assigned_operator_id = '{op2.user_id}' "
                    "AND status = 'assigned';"
                )
            )
        ).all()

        assert len(op1_tickets) == 2
        assert len(op2_tickets) == 2
