"""Слой доступа к данным домена operators."""

from datetime import datetime
from uuid import UUID

import uuid6
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import UserModel
from src.chat.models import (
    ChatModel,
    MessageModel,
    MessageModerationStatus,
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

ACTIVE_OPERATOR_TICKET_STATUSES: tuple[TicketStatus, ...] = (
    TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS,
)


class SupportLineRepository:
    """Репозиторий для работы с линиями поддержки."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий активной сессией базы данных."""
        self.session = session

    async def get_by_id(self, line_id: int) -> SupportLineModel | None:
        """Извлекает линию поддержки по первичному ключу."""
        return await self.session.get(SupportLineModel, line_id)

    async def get_by_code(self, code: str) -> SupportLineModel | None:
        """Извлекает линию поддержки по системному коду."""
        stmt = select(SupportLineModel).where(SupportLineModel.code == code)
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_all_active(self) -> list[SupportLineModel]:
        """Возвращает список всех активных линий поддержки."""
        stmt = (
            select(SupportLineModel)
            .where(SupportLineModel.is_active.is_(True))
            .order_by(SupportLineModel.id.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(self, line: SupportLineModel) -> SupportLineModel:
        """Сохраняет новую линию поддержки в базе данных."""
        self.session.add(line)
        await self.session.flush()
        return line


class OperatorRepository:
    """Репозиторий для управления профилями операторов и параметрами смены."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий активной сессией базы данных."""
        self.session = session

    async def get_by_user_id(
        self, user_id: UUID, load_relations: bool = False
    ) -> OperatorProfileModel | None:
        """Извлекает профиль оператора по идентификатору пользователя."""
        if not load_relations:
            return await self.session.get(OperatorProfileModel, user_id)

        stmt = (
            select(OperatorProfileModel)
            .where(OperatorProfileModel.user_id == user_id)
            .options(
                selectinload(OperatorProfileModel.user),
                selectinload(OperatorProfileModel.line),
            )
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_operator_profile_with_stats(
        self, user_id: UUID
    ) -> tuple[OperatorProfileModel, str, int] | None:
        """Извлекает профиль оператора с загруженными связями, кодом линии и числом занятых слотов."""
        profile = await self.get_by_user_id(user_id, load_relations=True)
        if profile is None:
            return None

        line_code = profile.line.code if profile.line else ""

        stmt_slots = select(func.count(TicketModel.id)).where(
            TicketModel.assigned_operator_id == user_id,
            TicketModel.status.in_(ACTIVE_OPERATOR_TICKET_STATUSES),
        )
        active_slots_count = (await self.session.scalar(stmt_slots)) or 0
        return profile, line_code, active_slots_count

    async def get_sidebar_tickets(
        self, operator_id: UUID
    ) -> list[TicketModel]:
        """Возвращает список закрепленных тикетов оператора с загруженными клиентом, линией и сообщениями."""
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.assigned_operator_id == operator_id,
                TicketModel.status.in_(ACTIVE_OPERATOR_TICKET_STATUSES),
            )
            .options(
                selectinload(TicketModel.chat)
                .selectinload(ChatModel.client)
                .selectinload(UserModel.client_profile),
                selectinload(TicketModel.line),
                selectinload(TicketModel.messages),
            )
            .order_by(
                case(
                    (TicketModel.priority == "P0", 0),
                    (TicketModel.priority == "P1", 1),
                    else_=2,
                ),
                TicketModel.created_at.asc(),
            )
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_ticket_workspace_data(
        self, ticket_id: UUID
    ) -> TicketModel | None:
        """Извлекает обращение со всеми данными клиента, линии и историей сообщений."""
        stmt = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .options(
                selectinload(TicketModel.chat)
                .selectinload(ChatModel.client)
                .selectinload(UserModel.client_profile),
                selectinload(TicketModel.line),
                selectinload(TicketModel.copilot_summary),
                selectinload(TicketModel.messages).selectinload(
                    MessageModel.sources
                ),
            )
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def assign_ticket_to_operator(
        self,
        ticket_id: UUID,
        operator_id: UUID,
        status: str = TicketStatus.IN_PROGRESS.value,
    ) -> TicketModel | None:
        """Закрепляет тикет за оператором и переводит в статус активного диалога."""
        ticket = await self.session.get(TicketModel, ticket_id)
        if ticket is None:
            return None
        ticket.assigned_operator_id = operator_id
        ticket.status = status
        if ticket.opened_at is None:
            ticket.opened_at = datetime.now(settings.TIMEZONE)
        ticket.updated_at = datetime.now(settings.TIMEZONE)
        await self.session.flush()
        return ticket

    async def save_operator_message(
        self, ticket_id: UUID, operator_id: UUID, text: str
    ) -> MessageModel:
        """Сохраняет текстовый ответ оператора в таблице messages."""
        msg = MessageModel(
            id=uuid6.uuid7(),
            ticket_id=ticket_id,
            sender_type=MessageSenderType.OPERATOR.value,
            sender_id=operator_id,
            text=text,
            moderation_status=MessageModerationStatus.PASSED.value,
            created_at=datetime.now(settings.TIMEZONE),
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def add_system_message(
        self, ticket_id: UUID, text: str
    ) -> MessageModel:
        """Добавляет системное сервисное сообщение в историю обращения."""
        msg = MessageModel(
            id=uuid6.uuid7(),
            ticket_id=ticket_id,
            sender_type=MessageSenderType.SYSTEM.value,
            sender_id=None,
            text=text,
            moderation_status=MessageModerationStatus.PASSED.value,
            created_at=datetime.now(settings.TIMEZONE),
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def transfer_ticket(
        self,
        ticket_id: UUID,
        target_line_id: int,
        comment: str | None = None,
    ) -> TicketModel | None:
        """Переводит обращение на другую линию, сбрасывая закрепленного оператора."""
        ticket = await self.session.get(TicketModel, ticket_id)
        if ticket is None:
            return None
        ticket.transferred_from_operator_id = ticket.assigned_operator_id
        ticket.assigned_operator_id = None
        ticket.assigned_at = None
        ticket.opened_at = None
        ticket.line_id = target_line_id
        ticket.status = TicketStatus.QUEUED.value
        ticket.transfer_comment = comment
        ticket.updated_at = datetime.now(settings.TIMEZONE)
        await self.session.flush()
        return ticket

    async def resolve_ticket(self, ticket_id: UUID) -> TicketModel | None:
        """Завершает обращение со статусом resolved и отметкой closed_at."""
        ticket = await self.session.get(TicketModel, ticket_id)
        if ticket is None:
            return None
        ticket.status = TicketStatus.RESOLVED.value
        ticket.closed_at = datetime.now(settings.TIMEZONE)
        ticket.updated_at = datetime.now(settings.TIMEZONE)
        await self.session.flush()
        return ticket

    async def get_active_by_line(
        self, line_id: int
    ) -> list[OperatorProfileModel]:
        """Возвращает всех операторов на указанной линии со статусом смены active."""
        stmt = (
            select(OperatorProfileModel)
            .where(
                OperatorProfileModel.line_id == line_id,
                OperatorProfileModel.shift_status
                == OperatorShiftStatus.ACTIVE,
                OperatorProfileModel.disconnected_at.is_(None),
            )
            .order_by(OperatorProfileModel.last_assigned_at.asc().nullsfirst())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_least_loaded_active_for_update(
        self, line_id: int
    ) -> OperatorProfileModel | None:
        """Атомарно выбирает наименее загруженного оператора на линии с блокировкой строки."""
        active_slots_subquery = (
            select(func.count(TicketModel.id))
            .where(
                TicketModel.assigned_operator_id
                == OperatorProfileModel.user_id,
                TicketModel.status.in_(ACTIVE_OPERATOR_TICKET_STATUSES),
            )
            .scalar_subquery()
        )

        stmt = (
            select(OperatorProfileModel)
            .where(
                OperatorProfileModel.line_id == line_id,
                OperatorProfileModel.shift_status
                == OperatorShiftStatus.ACTIVE,
                OperatorProfileModel.disconnected_at.is_(None),
                active_slots_subquery < OperatorProfileModel.max_slots,
            )
            .order_by(
                active_slots_subquery.asc(),
                OperatorProfileModel.last_assigned_at.asc().nullsfirst(),
            )
            .limit(1)
            .with_for_update(of=OperatorProfileModel, skip_locked=True)
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def create(
        self, profile: OperatorProfileModel
    ) -> OperatorProfileModel:
        """Сохраняет новый профиль оператора в базе данных."""
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def update_shift_status(
        self, user_id: UUID, shift_status: OperatorShiftStatus | str
    ) -> OperatorProfileModel | None:
        """Обновляет статус рабочей смены оператора."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None
        profile.shift_status = str(shift_status)
        return await self.update(profile)

    async def update(
        self, profile: OperatorProfileModel
    ) -> OperatorProfileModel:
        """Фиксирует изменения профиля оператора в базе данных."""
        profile.updated_at = datetime.now(settings.TIMEZONE)
        await self.session.flush()
        return profile

    async def mark_connected(
        self, user_id: UUID
    ) -> OperatorProfileModel | None:
        """Сбрасывает отметку disconnected_at при установлении связи (если смена не offline)."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None
        if profile.shift_status in {
            OperatorShiftStatus.ACTIVE.value,
            OperatorShiftStatus.BREAK.value,
        }:
            profile.disconnected_at = None
            profile.updated_at = datetime.now(settings.TIMEZONE)
            await self.session.flush()
        return profile

    async def mark_disconnected(
        self, user_id: UUID
    ) -> OperatorProfileModel | None:
        """Фиксирует время потери связи оператором disconnected_at."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None
        profile.disconnected_at = datetime.now(settings.TIMEZONE)
        profile.updated_at = datetime.now(settings.TIMEZONE)
        await self.session.flush()
        return profile

    async def get_disconnected_operators(
        self, cutoff: datetime, limit: int = 100
    ) -> list[OperatorProfileModel]:
        """Выбирает операторов с зафиксированным обрывом связи disconnected_at <= cutoff."""
        stmt = (
            select(OperatorProfileModel)
            .where(
                OperatorProfileModel.shift_status.in_(
                    (
                        OperatorShiftStatus.ACTIVE.value,
                        OperatorShiftStatus.BREAK.value,
                    )
                ),
                OperatorProfileModel.disconnected_at.is_not(None),
                OperatorProfileModel.disconnected_at <= cutoff,
            )
            .options(
                selectinload(OperatorProfileModel.line),
                selectinload(OperatorProfileModel.user),
            )
            .order_by(OperatorProfileModel.disconnected_at.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def set_operator_offline(
        self, user_id: UUID, now: datetime
    ) -> OperatorProfileModel | None:
        """Переводит профиль оператора в статус offline со сбросом disconnected_at."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None
        profile.shift_status = OperatorShiftStatus.OFFLINE.value
        profile.disconnected_at = None
        profile.updated_at = now
        await self.session.flush()
        return profile

    async def requeue_operator_tickets(
        self, operator_id: UUID, now: datetime
    ) -> list[TicketModel]:
        """Сбрасывает закрепление незавершенных тикетов оператора и переводит их в queued.

        Подгружает отношение line через selectinload(TicketModel.line) во избежание DetachedInstanceError.
        """
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.assigned_operator_id == operator_id,
                TicketModel.status.in_(ACTIVE_OPERATOR_TICKET_STATUSES),
            )
            .options(selectinload(TicketModel.line))
        )
        result = await self.session.scalars(stmt)
        tickets = list(result.all())
        for ticket in tickets:
            ticket.assigned_operator_id = None
            ticket.assigned_at = None
            ticket.opened_at = None
            ticket.status = TicketStatus.QUEUED.value
            ticket.updated_at = now
        await self.session.flush()
        return tickets

    async def get_queued_tickets_for_line(
        self, line_id: int
    ) -> list[TicketModel]:
        """Выбирает тикеты линии со статусом queued, отсортированные по приоритету и времени.

        Использует частичный индекс idx_tickets_queued_recovery (ORDER BY priority ASC, created_at ASC).
        """
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.line_id == line_id,
                TicketModel.status == TicketStatus.QUEUED.value,
            )
            .order_by(
                TicketModel.priority.asc(),
                TicketModel.created_at.asc(),
            )
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_queued_tickets_by_lines(self) -> dict[int, int]:
        """Подсчитывает количество тикетов со статусом queued для каждой линии поддержки."""
        stmt = (
            select(TicketModel.line_id, func.count(TicketModel.id))
            .where(TicketModel.status == TicketStatus.QUEUED.value)
            .group_by(TicketModel.line_id)
        )
        result = await self.session.execute(stmt)
        return {
            line_id: count
            for line_id, count in result.all()
            if line_id is not None
        }
