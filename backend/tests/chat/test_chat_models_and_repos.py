"""Интеграционные тесты моделей, репозиториев и оперативного контекста Redis."""

from datetime import datetime

import pytest
import redis.asyncio as aioredis
import uuid6
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RoleModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageSenderType,
    MessageSourceModel,
    TicketModel,
    TicketPriority,
    TicketStatus,
)
from src.chat.repository import ChatRepository, TicketRepository
from src.core.config import settings
from src.core.redis_client import RedisChatContext
from src.operators.models import SupportLineModel


@pytest.fixture
async def session(async_session: AsyncSession) -> AsyncSession:
    """Предоставляет изолированную асинхронную сессию базы данных с откатом изменений."""
    return async_session


@pytest.fixture
async def base_context(
    session: AsyncSession,
) -> tuple[UserModel, ChatModel, SupportLineModel]:
    """Получает или создает тестовые сущности пользователя, чата и линии поддержки."""
    stmt_role = select(RoleModel).where(RoleModel.code == "client")
    role = (await session.scalars(stmt_role)).first()
    if not role:
        role = RoleModel(code="client", name="Клиент")
        session.add(role)
        await session.flush()

    stmt_user = select(UserModel).where(
        UserModel.email == "supplier@zakupki.mos.ru"
    )
    user = (await session.scalars(stmt_user)).first()
    if not user:
        user = UserModel(
            email="supplier@zakupki.mos.ru",
            password_hash="hashed_secret",
            role_id=role.id,
        )
        session.add(user)
        await session.flush()

    stmt_line = select(SupportLineModel).where(SupportLineModel.code == "L1")
    line = (await session.scalars(stmt_line)).first()
    if not line:
        line = SupportLineModel(code="L1", name="Первая линия")
        session.add(line)
        await session.flush()

    chat = ChatModel(client_id=user.id)
    session.add(chat)
    await session.flush()

    return user, chat, line


async def test_ticket_status_lifecycle_and_filtering(
    session: AsyncSession,
    base_context: tuple[UserModel, ChatModel, SupportLineModel],
) -> None:
    """Проверяет корректность фильтрации активных и закрытых обращений."""
    _, chat, line = base_context
    ticket_repo = TicketRepository(session=session)

    # 1. Создание активного тикета
    active_ticket = TicketModel(
        chat_id=chat.id,
        line_id=line.id,
        priority=TicketPriority.P1,
        status=TicketStatus.BOT_PROCESSING,
    )
    await ticket_repo.create(active_ticket)

    found_active = await ticket_repo.get_active_by_chat_id(chat.id)
    assert found_active is not None
    assert found_active.id == active_ticket.id
    assert found_active.priority == TicketPriority.P1

    # Завершенных тикетов пока нет
    found_closed = await ticket_repo.get_last_closed_by_chat_id(chat.id)
    assert found_closed is None

    # 2. Перевод тикета в терминальный статус
    active_ticket.status = TicketStatus.RESOLVED
    active_ticket.closed_at = datetime.now(settings.TIMEZONE)
    await ticket_repo.update(active_ticket)

    # Активный тикет больше не возвращается
    found_active_after_close = await ticket_repo.get_active_by_chat_id(chat.id)
    assert found_active_after_close is None

    # Завершенный тикет успешно найден
    found_closed_after_close = await ticket_repo.get_last_closed_by_chat_id(
        chat.id
    )
    assert found_closed_after_close is not None
    assert found_closed_after_close.id == active_ticket.id
    assert found_closed_after_close.status == TicketStatus.RESOLVED


async def test_chat_repository_save_and_eager_load_messages(
    session: AsyncSession,
    base_context: tuple[UserModel, ChatModel, SupportLineModel],
) -> None:
    """Проверяет сохранение сообщений с источниками и их хронологическую выборку."""
    user, chat, line = base_context
    chat_repo = ChatRepository(session=session)
    ticket_repo = TicketRepository(session=session)

    ticket = TicketModel(
        chat_id=chat.id,
        line_id=line.id,
        status=TicketStatus.IN_PROGRESS,
    )
    await ticket_repo.create(ticket)

    # Сообщение клиента
    client_msg = MessageModel(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.CLIENT,
        sender_id=user.id,
        text="Как подписать контракт?",
    )
    await chat_repo.save_message(client_msg)

    # Ответ бота с источником
    source = MessageSourceModel(
        chunk_id="chunk_sec1_p5",
        doc_id="DOC_CONTRACT_REGLAMENT",
        quote_text="Подписание осуществляется усиленной ЭП в течение 5 дней.",
    )
    bot_msg = MessageModel(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.BOT,
        text="Подписание контракта регламентировано статьей 5.",
    )
    await chat_repo.save_message(bot_msg, sources=[source])

    # Выборка последних реплик чата
    messages = await chat_repo.get_recent_messages(chat.id, limit=50)
    assert len(messages) == 2
    assert messages[0].id == client_msg.id
    assert messages[1].id == bot_msg.id

    # Проверка подгрузки источников без вторичных запросов к БД
    assert len(messages[1].sources) == 1
    assert messages[1].sources[0].chunk_id == "chunk_sec1_p5"
    assert messages[1].sources[0].doc_id == "DOC_CONTRACT_REGLAMENT"


async def test_cascade_deletion_and_foreign_key_protection(
    session: AsyncSession,
    base_context: tuple[UserModel, ChatModel, SupportLineModel],
) -> None:
    """Проверяет каскадное удаление сообщений тикета и защиту от удаления чата."""
    _, chat, line = base_context
    ticket_repo = TicketRepository(session=session)
    chat_repo = ChatRepository(session=session)

    ticket = TicketModel(
        chat_id=chat.id,
        line_id=line.id,
        status=TicketStatus.BOT_PROCESSING,
    )
    await ticket_repo.create(ticket)

    msg = MessageModel(
        ticket_id=ticket.id,
        sender_type=MessageSenderType.CLIENT,
        text="Тестовый вопрос",
    )
    source = MessageSourceModel(
        chunk_id="chunk_test_1",
        doc_id="DOC_TEST",
    )
    await chat_repo.save_message(msg, sources=[source])
    ticket_id = ticket.id
    await session.commit()

    # Попытка удалить чат при наличии тикета должна завершаться ошибкой RESTRICT
    await session.delete(chat)
    with pytest.raises(IntegrityError):
        await session.flush()

    await session.rollback()

    # Повторное получение тикета и его удаление: проверяем каскадное удаление сообщений
    current_ticket = await ticket_repo.get_by_id(ticket_id)
    assert current_ticket is not None
    await session.delete(current_ticket)
    await session.flush()

    messages = await session.scalars(
        select(MessageModel).where(MessageModel.ticket_id == ticket_id)
    )
    assert list(messages.all()) == []

    sources = await session.scalars(
        select(MessageSourceModel).where(
            MessageSourceModel.chunk_id == "chunk_test_1"
        )
    )
    assert list(sources.all()) == []


async def test_redis_context_sliding_window_and_ttl(
    redis_client: aioredis.Redis,
) -> None:
    """Проверяет скользящее окно 10 реплик, время жизни 1800с и очистку в Redis."""
    context_mgr = RedisChatContext(redis=redis_client)
    test_ticket_id = uuid6.uuid7()

    try:
        # Гарантируем чистоту ключа
        await context_mgr.clear_context(test_ticket_id)

        # Добавляем 12 реплик (превышаем лимит 10)
        for i in range(12):
            await context_mgr.add_message(
                ticket_id=test_ticket_id,
                sender="client" if i % 2 == 0 else "bot",
                text=f"Сообщение {i}",
            )

        # Проверяем, что сохранились только последние 10 сообщений (номера 2–11)
        stored_messages = await context_mgr.get_messages(test_ticket_id)
        assert len(stored_messages) == 10
        assert stored_messages[0]["text"] == "Сообщение 2"
        assert stored_messages[-1]["text"] == "Сообщение 11"

        # Проверяем корректность установки TTL (30 минут = 1800 секунд)
        ttl = await context_mgr.get_ttl(test_ticket_id)
        assert 1700 <= ttl <= 1800

        # Проверяем удаление контекста при закрытии обращения
        await context_mgr.clear_context(test_ticket_id)
        remaining = await context_mgr.get_messages(test_ticket_id)
        assert remaining == []

        ttl_after_clear = await context_mgr.get_ttl(test_ticket_id)
        assert ttl_after_clear == -2  # Ключ не существует
    finally:
        await context_mgr.close()
