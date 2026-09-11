"""Модульные тесты сервисного слоя рабочего места оператора (HIGH-10)."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import uuid6
from fastapi import HTTPException

from src.auth.models import ClientProfileModel, UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
    MessageSenderType,
    TicketModel,
    TicketStatus,
)
from src.chat.moderation import ProfanityModerator
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
    SupportLineModel,
)
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.service import OperatorService


@pytest.fixture
def mock_service() -> tuple[
    OperatorService,
    AsyncMock,  # operator_repo
    AsyncMock,  # support_line_repo
    AsyncMock,  # ticket_repo
    AsyncMock,  # line_queue
    AsyncMock,  # ticket_events
    AsyncMock,  # chat_context
    AsyncMock,  # session
]:
    """Создает изолированный инстанс OperatorService со всеми замоканными зависимостями."""
    session = AsyncMock()
    redis = AsyncMock()
    operator_repo = AsyncMock(spec=OperatorRepository)
    support_line_repo = AsyncMock(spec=SupportLineRepository)
    ticket_repo = AsyncMock(spec=TicketRepository)
    line_queue = AsyncMock(spec=RedisLineQueue)
    redis_events = AsyncMock(spec=RedisOperatorEvents)
    ticket_events = AsyncMock(spec=RedisTicketEvents)
    chat_context = AsyncMock(spec=RedisChatContext)
    moderator = ProfanityModerator()

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
        moderator=moderator,
    )

    return (
        service,
        operator_repo,
        support_line_repo,
        ticket_repo,
        line_queue,
        ticket_events,
        chat_context,
        session,
    )


def create_dummy_profile(
    user_id: UUID,
    line_id: int = 1,
    line_code: str = "L1",
    shift_status: str = "offline",
    max_slots: int = 5,
) -> OperatorProfileModel:
    """Вспомогательная фабрика тестового профиля оператора."""
    line = SupportLineModel(
        id=line_id, code=line_code, name=f"Линия {line_code}", is_active=True
    )
    user = UserModel(
        id=user_id,
        email="operator@zakupki.mos.ru",
        full_name="Тестовый Оператор",
    )
    profile = OperatorProfileModel(
        user_id=user_id,
        line_id=line_id,
        shift_status=shift_status,
        max_slots=max_slots,
    )
    profile.line = line
    profile.user = user
    return profile


def create_dummy_ticket(
    ticket_id: UUID,
    operator_id: UUID | None,
    line_code: str = "L1",
    status: str = TicketStatus.ASSIGNED.value,
    priority: str = "P1",
) -> TicketModel:
    """Вспомогательная фабрика тестового обращения с клиентом и сообщениями."""
    chat_id = uuid6.uuid7()
    client_id = uuid6.uuid7()
    client = UserModel(
        id=client_id,
        email="client@zakupki.mos.ru",
        full_name="Петр Клиентов",
    )
    client.client_profile = ClientProfileModel(
        user_id=client_id,
        company_name="ООО «Поставщик»",
        inn="7701987654",
        kpp="770101001",
        phone="+79990001122",
    )
    chat = ChatModel(id=chat_id, client_id=client_id)
    chat.client = client

    line = SupportLineModel(
        id=1, code=line_code, name=f"Линия {line_code}", is_active=True
    )

    ticket = TicketModel(
        id=ticket_id,
        chat_id=chat_id,
        line_id=line.id,
        status=status,
        priority=priority,
        assigned_operator_id=operator_id,
        created_at=datetime.now(settings.TIMEZONE),
    )
    ticket.chat = chat
    ticket.line = line

    msg1 = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        sender_type=MessageSenderType.CLIENT.value,
        sender_id=client_id,
        text="Здравствуйте, не могу отправить ценовое предложение",
        moderation_status=MessageModerationStatus.PASSED.value,
        created_at=datetime.now(settings.TIMEZONE),
    )
    msg1.sources = []
    ticket.messages = [msg1]
    return ticket


# ==============================================================================
# 1. ТЕСТЫ СМЕНЫ ОПЕРАТОРА И ВАЛИДАЦИИ СТАТУСОВ
# ==============================================================================


@pytest.mark.asyncio
async def test_operator_shift_lifecycle_and_validation(
    mock_service: tuple,
) -> None:
    """Проверяет переключение статуса смены, валидацию и триггер ребалансировки."""
    service, operator_repo, support_line_repo, _, _, _, _, session = (
        mock_service
    )
    user_id = uuid6.uuid7()
    profile = create_dummy_profile(user_id, shift_status="offline")

    # 1. Получение профиля со статистикой слотов
    operator_repo.get_operator_profile_with_stats.return_value = (
        profile,
        "L1",
        2,
    )
    res = await service.get_profile(user_id)
    assert res.user_id == user_id
    assert res.shift_status == "offline"
    assert res.active_slots_count == 2
    assert res.line_code == "L1"

    # 2. Переключение в active -> триггер диспетчеризации
    profile.shift_status = "active"
    operator_repo.update_shift_status.return_value = profile
    support_line_repo.get_by_id.return_value = profile.line

    with patch.object(
        service, "_safe_dispatch_task", new_callable=AsyncMock
    ) as mock_dispatch:
        updated = await service.update_shift(user_id, "active")
        assert updated.shift_status == "active"
        operator_repo.update_shift_status.assert_awaited_once_with(
            user_id, "active"
        )
        session.commit.assert_awaited_once()
        mock_dispatch.assert_awaited_once_with("L1", "shift_resumed")

    # 3. Переключение в break -> без триггера
    profile.shift_status = "break"
    operator_repo.update_shift_status.reset_mock()
    session.commit.reset_mock()

    with patch.object(
        service, "_safe_dispatch_task", new_callable=AsyncMock
    ) as mock_dispatch:
        updated = await service.update_shift(user_id, "break")
        assert updated.shift_status == "break"
        mock_dispatch.assert_not_called()

    # 4. Недопустимый статус -> 400 Bad Request
    with pytest.raises(HTTPException) as exc_info:
        await service.update_shift(user_id, "sleeping")
    assert exc_info.value.status_code == 400
    assert "Недопустимый статус смены" in exc_info.value.detail

    # 5. Несуществующий оператор -> 404 Not Found
    operator_repo.get_operator_profile_with_stats.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await service.get_profile(uuid6.uuid7())
    assert exc_info.value.status_code == 404


# ==============================================================================
# 2. ТЕСТЫ ИДЕМПОТЕНТНОСТИ OPEN_TICKET
# ==============================================================================


@pytest.mark.asyncio
async def test_open_ticket_idempotency_and_forbidden(
    mock_service: tuple,
) -> None:
    """Проверяет перевод assigned -> in_progress, событие operator_joined и идемпотентность."""
    service, operator_repo, _, _, _, ticket_events, _, session = mock_service
    operator_id = uuid6.uuid7()
    other_operator_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    ticket = create_dummy_ticket(
        ticket_id, operator_id, status=TicketStatus.ASSIGNED.value
    )
    operator_repo.get_ticket_workspace_data.return_value = ticket
    operator_profile = create_dummy_profile(operator_id, shift_status="active")
    operator_repo.get_by_user_id.return_value = operator_profile

    # 1. Первый вызов open_ticket (статус assigned)
    workspace = await service.open_ticket(operator_id, ticket_id)

    assert workspace.status == TicketStatus.IN_PROGRESS.value
    assert workspace.ticket_id == ticket_id
    assert workspace.client.full_name == "Петр Клиентов"
    assert workspace.client.company_name == "ООО «Поставщик»"
    assert len(workspace.messages) == 1

    operator_repo.assign_ticket_to_operator.assert_awaited_once_with(
        ticket_id, operator_id, status=TicketStatus.IN_PROGRESS.value
    )
    session.commit.assert_awaited_once()
    ticket_events.publish_operator_joined.assert_awaited_once_with(
        ticket_id=ticket_id, operator_name="Тестовый Оператор"
    )

    # 2. Повторный вызов тем же оператором (тикет уже in_progress)
    operator_repo.assign_ticket_to_operator.reset_mock()
    session.commit.reset_mock()
    ticket_events.publish_operator_joined.reset_mock()

    ticket.status = TicketStatus.IN_PROGRESS.value
    workspace_repeat = await service.open_ticket(operator_id, ticket_id)

    assert workspace_repeat.status == TicketStatus.IN_PROGRESS.value
    # Не должно быть повторного закрепления и повторного события
    operator_repo.assign_ticket_to_operator.assert_not_called()
    ticket_events.publish_operator_joined.assert_not_called()

    # 3. Попытка открыть чужой тикет другим оператором -> 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        await service.open_ticket(other_operator_id, ticket_id)
    assert exc_info.value.status_code == 403

    # 4. Попытка открыть закрытый тикет -> 400 Bad Request
    ticket.status = TicketStatus.RESOLVED.value
    with pytest.raises(HTTPException) as exc_info:
        await service.open_ticket(operator_id, ticket_id)
    assert exc_info.value.status_code == 400


# ==============================================================================
# 3. ТЕСТЫ ЗАВЕРШЕНИЯ ТИКЕТА И ОСВОБОЖДЕНИЯ СЛОТА (RESOLVE_TICKET)
# ==============================================================================


@pytest.mark.asyncio
async def test_resolve_ticket_frees_slot_and_triggers_dispatch(
    mock_service: tuple,
) -> None:
    """Проверяет закрытие обращения, очистку контекста Redis и запуск ребалансировки."""
    service, operator_repo, _, _, _, ticket_events, chat_context, session = (
        mock_service
    )
    operator_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    ticket = create_dummy_ticket(
        ticket_id,
        operator_id,
        line_code="L1",
        status=TicketStatus.IN_PROGRESS.value,
    )
    operator_repo.get_ticket_workspace_data.return_value = ticket

    with patch.object(
        service, "_safe_dispatch_task", new_callable=AsyncMock
    ) as mock_dispatch:
        res = await service.resolve_ticket(operator_id, ticket_id)

        assert res.status == "resolved"
        assert res.ticket_id == ticket_id
        assert res.closed_at is not None

        # Проверяем вызовы репозитория и БД
        operator_repo.resolve_ticket.assert_awaited_once_with(ticket_id)
        session.commit.assert_awaited_once()

        # Проверяем очистку контекста диалога в Redis
        chat_context.clear_context.assert_awaited_once_with(ticket_id)

        # Проверяем публикацию события закрытия тикета
        ticket_events.publish_ticket_resolved.assert_awaited_once()

        # Проверяем вызов ребалансировки на освободившийся слот линии L1
        mock_dispatch.assert_awaited_once_with("L1", "slot_freed")


# ==============================================================================
# 4. ТЕСТЫ ПЕРЕВОДА ТИКЕТА НА ДРУГУЮ ЛИНИЮ (TRANSFER_TICKET)
# ==============================================================================


@pytest.mark.asyncio
async def test_transfer_ticket_queue_migration_and_system_message(
    mock_service: tuple,
) -> None:
    """Проверяет перевод тикета на целевую линию, системное сообщение и очереди."""
    (
        service,
        operator_repo,
        support_line_repo,
        _,
        line_queue,
        ticket_events,
        _,
        session,
    ) = mock_service

    operator_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    ticket = create_dummy_ticket(
        ticket_id,
        operator_id,
        line_code="L1",
        status=TicketStatus.IN_PROGRESS.value,
        priority="P1",
    )
    operator_repo.get_ticket_workspace_data.return_value = ticket

    target_line = SupportLineModel(
        id=2, code="L2", name="Линия L2", is_active=True
    )
    support_line_repo.get_by_code.return_value = target_line

    with patch.object(
        service, "_safe_dispatch_task", new_callable=AsyncMock
    ) as mock_dispatch:
        res = await service.transfer_ticket(
            user_id=operator_id,
            ticket_id=ticket_id,
            target_line_code="L2",
            transfer_comment="Требуется проверка криптопровайдера",
        )

        assert res.status == "queued"
        assert res.ticket_id == ticket_id
        assert res.line_code == "L2"

        # Проверяем обновление тикета в БД
        operator_repo.transfer_ticket.assert_awaited_once_with(
            ticket_id=ticket_id,
            target_line_id=2,
            comment="Требуется проверка криптопровайдера",
        )
        # Проверяем системное сообщение
        operator_repo.add_system_message.assert_awaited_once()
        system_text = operator_repo.add_system_message.call_args[0][1]
        assert "L2" in system_text
        assert "криптопровайдера" in system_text

        session.commit.assert_awaited_once()

        # Проверяем постановку в очередь Redis целевой линии
        line_queue.enqueue_ticket.assert_awaited_once_with(
            line_code="L2", ticket_id=ticket_id, priority="P1"
        )

        # Проверяем публикацию события в Pub/Sub
        ticket_events.publish_ticket_transferred.assert_awaited_once_with(
            ticket_id=ticket_id,
            new_line_code="L2",
            reason="Требуется проверка криптопровайдера",
        )

        # Проверяем вызов задач диспетчеризации: для целевой L2 и текущей L1
        assert mock_dispatch.await_count == 2
        mock_dispatch.assert_any_await("L2", "ticket_escalated")
        mock_dispatch.assert_any_await("L1", "slot_freed")

    # Перевод на ту же линию -> 400 Bad Request
    support_line_repo.get_by_code.return_value = ticket.line
    with pytest.raises(HTTPException) as exc_info:
        await service.transfer_ticket(operator_id, ticket_id, "L1")
    assert exc_info.value.status_code == 400


# ==============================================================================
# 5. ТЕСТЫ ОТПРАВКИ СООБЩЕНИЙ ОПЕРАТОРОМ И МОДЕРАЦИИ
# ==============================================================================


@pytest.mark.asyncio
async def test_send_operator_message_and_profanity_block(
    mock_service: tuple,
) -> None:
    """Проверяет отправку сообщения оператором, сохранение в БД и блокировку мата."""
    (
        service,
        operator_repo,
        _,
        ticket_repo,
        _,
        ticket_events,
        chat_context,
        session,
    ) = mock_service
    operator_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    ticket = create_dummy_ticket(
        ticket_id, operator_id, status=TicketStatus.IN_PROGRESS.value
    )
    ticket_repo.get_by_id.return_value = ticket

    msg = MessageModel(
        id=uuid6.uuid7(),
        ticket_id=ticket_id,
        sender_type=MessageSenderType.OPERATOR.value,
        sender_id=operator_id,
        text="Добрый день! Протокол разногласий сформирован.",
        moderation_status=MessageModerationStatus.PASSED.value,
        created_at=datetime.now(settings.TIMEZONE),
    )
    msg.sources = []
    operator_repo.save_operator_message.return_value = msg

    # 1. Корректный ответ оператора
    res = await service.send_message(
        user_id=operator_id,
        ticket_id=ticket_id,
        text="Добрый день! Протокол разногласий сформирован.",
    )
    assert res.text == "Добрый день! Протокол разногласий сформирован."
    assert res.sender_type == "operator"
    assert res.moderation_status == "passed"

    operator_repo.save_operator_message.assert_awaited_once_with(
        ticket_id=ticket_id,
        operator_id=operator_id,
        text="Добрый день! Протокол разногласий сформирован.",
    )
    session.commit.assert_awaited_once()
    chat_context.add_message.assert_awaited_once()
    ticket_events.publish_new_message.assert_awaited_once()

    # 2. Нецензурная лексика оператора должна блокироваться модератором с 400
    with pytest.raises(HTTPException) as exc_info:
        await service.send_message(
            user_id=operator_id,
            ticket_id=ticket_id,
            text="Какого хуя вы не прочитали регламент?",
        )
    assert exc_info.value.status_code == 400
    assert "недопустимую лексику" in exc_info.value.detail


# ==============================================================================
# 6. ТЕСТЫ ВЫБОРКИ САЙДБАРА
# ==============================================================================


@pytest.mark.asyncio
async def test_get_sidebar_tickets_formatting(
    mock_service: tuple,
) -> None:
    """Проверяет форматирование списка закрепленных тикетов для сайдбара."""
    service, operator_repo, _, _, _, _, _, _ = mock_service
    operator_id = uuid6.uuid7()
    ticket_id = uuid6.uuid7()

    ticket = create_dummy_ticket(
        ticket_id, operator_id, status=TicketStatus.IN_PROGRESS.value
    )
    operator_repo.get_sidebar_tickets.return_value = [ticket]

    cards = await service.get_sidebar_tickets(operator_id)
    assert len(cards) == 1
    assert cards[0].ticket_id == ticket_id
    assert cards[0].client_name == "Петр Клиентов"
    assert cards[0].company_name == "ООО «Поставщик»"
    assert cards[0].unread_messages_count == 1
    assert "ценовое предложение" in cards[0].last_message_preview
