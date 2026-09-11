"""Интеграционные тесты моделей операторов, репозитория и приоритетных очередей Redis."""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as aioredis
import uuid6
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RoleModel, UserModel
from src.core.redis_client import RedisLineQueue
from src.db.database import Base, async_session_maker, engine
from src.operators.models import (
    OperatorProfileModel,
    OperatorShiftStatus,
    SupportLineModel,
)
from src.operators.repository import OperatorRepository


@pytest.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    """Гарантирует актуальную схему таблиц и очищает данные перед каждым тестом."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "TRUNCATE TABLE operator_profiles, support_lines, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE operator_profiles, support_lines, users, roles "
                "RESTART IDENTITY CASCADE;"
            )
        )


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Предоставляет изолированную асинхронную сессию базы данных."""
    async with async_session_maker() as s:
        yield s


@pytest.fixture
async def base_operator_context(
    session: AsyncSession,
) -> tuple[UserModel, SupportLineModel]:
    """Создает тестового пользователя с ролью оператора и линию поддержки."""
    role = RoleModel(id=2, code="operator", name="Оператор поддержки")
    session.add(role)
    await session.flush()

    user = UserModel(
        id=uuid6.uuid7(),
        email="operator1@zakupki.mos.ru",
        password_hash="secure_hash",
        full_name="Иванов Иван Иванович",
        role_id=role.id,
    )
    session.add(user)

    line = SupportLineModel(
        code="L1",
        name="Первая линия поддержки",
        description="Типовые вопросы",
    )
    session.add(line)
    await session.flush()

    return user, line


async def test_operator_profile_crud_and_queries(
    session: AsyncSession,
    base_operator_context: tuple[UserModel, SupportLineModel],
) -> None:
    """Проверяет жизненный цикл профиля оператора, смену статуса и фильтрацию активных."""
    user, line = base_operator_context
    repo = OperatorRepository(session=session)

    # 1. Создание профиля со статусом offline по умолчанию
    profile = OperatorProfileModel(
        user_id=user.id,
        line_id=line.id,
        shift_status=OperatorShiftStatus.OFFLINE,
        max_slots=5,
    )
    await repo.create(profile)

    # 2. Выборка по user_id
    saved = await repo.get_by_user_id(user.id)
    assert saved is not None
    assert saved.user_id == user.id
    assert saved.line_id == line.id
    assert saved.shift_status == OperatorShiftStatus.OFFLINE
    assert saved.max_slots == 5

    # 3. В статусе offline оператор не должен попадать в выборку активных на линии
    active_operators = await repo.get_active_by_line(line.id)
    assert active_operators == []

    # 4. Переключение статуса смены в active
    updated = await repo.update_shift_status(
        user.id, OperatorShiftStatus.ACTIVE
    )
    assert updated is not None
    assert updated.shift_status == OperatorShiftStatus.ACTIVE

    # 5. Оператор должен появиться в выборке активных на линии
    active_operators = await repo.get_active_by_line(line.id)
    assert len(active_operators) == 1
    assert active_operators[0].user_id == user.id

    # 6. Загрузка профиля с внешними связями
    profile_with_relations = await repo.get_by_user_id(
        user.id, load_relations=True
    )
    assert profile_with_relations is not None
    assert profile_with_relations.user.email == "operator1@zakupki.mos.ru"
    assert profile_with_relations.line.code == "L1"


async def test_operator_profile_constraints(
    session: AsyncSession,
    base_operator_context: tuple[UserModel, SupportLineModel],
) -> None:
    """Проверяет соблюдение ограничений целостности статуса смены и лимита слотов."""
    user, line = base_operator_context

    # 1. Ошибка при недопустимом статусе смены
    with pytest.raises(IntegrityError):
        invalid_status_profile = OperatorProfileModel(
            user_id=user.id,
            line_id=line.id,
            shift_status="invalid_status",
            max_slots=5,
        )
        session.add(invalid_status_profile)
        await session.flush()
    await session.rollback()

    # 2. Ошибка при недопустимом числе слотов (max_slots <= 0)
    with pytest.raises(IntegrityError):
        invalid_slots_profile = OperatorProfileModel(
            user_id=user.id,
            line_id=line.id,
            shift_status=OperatorShiftStatus.OFFLINE,
            max_slots=0,
        )
        session.add(invalid_slots_profile)
        await session.flush()
    await session.rollback()

    # 3. Ошибка при превышении максимального лимита (max_slots > 20)
    with pytest.raises(IntegrityError):
        invalid_slots_high = OperatorProfileModel(
            user_id=user.id,
            line_id=line.id,
            shift_status=OperatorShiftStatus.OFFLINE,
            max_slots=25,
        )
        session.add(invalid_slots_high)
        await session.flush()
    await session.rollback()


async def test_redis_line_queue_priority_buffering_and_fifo(
    redis_client: aioredis.Redis,
) -> None:
    """Проверяет приоритетную буферизацию в очереди Redis: P0 в голову, P1/P2 в хвост."""
    queue_mgr = RedisLineQueue(redis=redis_client)
    line_code = "L1_TEST_QUEUE"

    try:
        # Гарантируем чистоту очереди перед проверкой
        await queue_mgr.clear_queue(line_code)

        ticket_p2_first = str(uuid6.uuid7())
        ticket_p1_first = str(uuid6.uuid7())
        ticket_p0_first = str(uuid6.uuid7())
        ticket_p0_second = str(uuid6.uuid7())
        ticket_p2_second = str(uuid6.uuid7())

        # 1. Добавляем стандартные тикеты P2 и P1 в конец очереди (RPUSH)
        len_1 = await queue_mgr.enqueue_ticket(
            line_code, ticket_p2_first, priority="P2"
        )
        assert len_1 == 1

        len_2 = await queue_mgr.enqueue_ticket(
            line_code, ticket_p1_first, priority="P1"
        )
        assert len_2 == 2

        # 2. Добавляем критический тикет P0 в начало очереди (LPUSH)
        len_3 = await queue_mgr.enqueue_ticket(
            line_code, ticket_p0_first, priority="P0"
        )
        assert len_3 == 3

        # 3. Добавляем еще один критический тикет P0 в начало очереди (LPUSH)
        len_4 = await queue_mgr.enqueue_ticket(
            line_code, ticket_p0_second, priority="P0"
        )
        assert len_4 == 4

        # 4. Добавляем тикет P2 в конец очереди
        len_5 = await queue_mgr.enqueue_ticket(
            line_code, ticket_p2_second, priority="P2"
        )
        assert len_5 == 5

        # 5. Проверяем порядок элементов в списке без извлечения
        items = await queue_mgr.peek_tickets(line_code)
        assert items == [
            ticket_p0_second,
            ticket_p0_first,
            ticket_p2_first,
            ticket_p1_first,
            ticket_p2_second,
        ]

        # 6. Извлекаем тикеты по одному (LPOP) и проверяем строгий порядок обслуживания
        assert await queue_mgr.dequeue_ticket(line_code) == ticket_p0_second
        assert await queue_mgr.dequeue_ticket(line_code) == ticket_p0_first
        assert await queue_mgr.dequeue_ticket(line_code) == ticket_p2_first
        assert await queue_mgr.dequeue_ticket(line_code) == ticket_p1_first
        assert await queue_mgr.dequeue_ticket(line_code) == ticket_p2_second

        # Очередь должна быть пуста
        assert await queue_mgr.dequeue_ticket(line_code) is None
        assert await queue_mgr.get_queue_len(line_code) == 0

        # 7. Проверяем валидацию недопустимого приоритета
        with pytest.raises(ValueError, match="Недопустимый приоритет тикета"):
            await queue_mgr.enqueue_ticket(
                line_code, str(uuid6.uuid7()), priority="INVALID_PRIORITY"
            )

    finally:
        await queue_mgr.clear_queue(line_code)
