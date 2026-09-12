from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import UserModel
from src.chat.models import (
    TERMINAL_TICKET_STATUSES,
    ChatModel,
    MessageModel,
    MessageSourceModel,
    TicketModel,
    TicketStatus,
)


class TicketRepository:
    """Репозиторий для управления сущностями обращений в базе данных."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий обращений активной сессией базы данных."""
        self.session = session

    async def get_by_id(self, ticket_id: UUID) -> TicketModel | None:
        """Извлекает обращение по первичному ключу."""
        stmt = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .options(
                selectinload(TicketModel.line),
                selectinload(TicketModel.assigned_operator),
            )
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_by_id_for_update(
        self, ticket_id: UUID, load_details: bool = True
    ) -> TicketModel | None:
        """Извлекает обращение по первичному ключу с блокировкой строки FOR UPDATE."""
        stmt = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .with_for_update()
        )
        if load_details:
            stmt = stmt.options(
                selectinload(TicketModel.chat)
                .selectinload(ChatModel.client)
                .selectinload(UserModel.client_profile),
                selectinload(TicketModel.line),
                selectinload(TicketModel.messages),
            )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_active_by_chat_id(self, chat_id: UUID) -> TicketModel | None:
        """Извлекает активное незавершенное обращение для указанного чата."""
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.chat_id == chat_id,
                TicketModel.status.not_in(TERMINAL_TICKET_STATUSES),
            )
            .options(
                selectinload(TicketModel.assigned_operator),
                selectinload(TicketModel.line),
            )
            .order_by(TicketModel.created_at.desc())
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def get_last_closed_by_chat_id(
        self, chat_id: UUID
    ) -> TicketModel | None:
        """Извлекает последнее завершенное обращение для указанного чата."""
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.chat_id == chat_id,
                TicketModel.status.in_(TERMINAL_TICKET_STATUSES),
            )
            .order_by(
                TicketModel.closed_at.desc().nullslast(),
                TicketModel.created_at.desc(),
            )
        )
        result = await self.session.scalars(stmt)
        return result.first()

    async def create(self, ticket: TicketModel) -> TicketModel:
        """Сохраняет новую запись обращения в базе данных."""
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def update(self, ticket: TicketModel) -> TicketModel:
        """Фиксирует изменения сущности обращения в базе данных."""
        await self.session.flush()
        return ticket

    async def get_inactive_bot_tickets(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        """Выбирает тикеты в обработке ботом, не обновлявшиеся до момента cutoff."""
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.status == TicketStatus.BOT_PROCESSING.value,
                TicketModel.updated_at <= cutoff,
            )
            .order_by(TicketModel.updated_at.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_in_progress_tickets_with_messages(
        self, limit: int = 100
    ) -> list[TicketModel]:
        """Выбирает активные тикеты операторов с загруженными сообщениями и линией поддержки."""
        stmt = (
            select(TicketModel)
            .where(TicketModel.status == TicketStatus.IN_PROGRESS.value)
            .options(
                selectinload(TicketModel.messages),
                selectinload(TicketModel.line),
            )
            .order_by(TicketModel.updated_at.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def close_ticket_by_inactivity(
        self, ticket_id: UUID, cutoff: datetime, now: datetime
    ) -> bool:
        """Атомарно переводит обращение в closed_by_inactivity, если оно не обновлялось после cutoff."""
        stmt = (
            update(TicketModel)
            .where(
                TicketModel.id == ticket_id,
                TicketModel.status.in_(
                    (
                        TicketStatus.BOT_PROCESSING.value,
                        TicketStatus.IN_PROGRESS.value,
                    )
                ),
                TicketModel.updated_at <= cutoff,
            )
            .values(
                status=TicketStatus.CLOSED_BY_INACTIVITY.value,
                closed_at=now,
                updated_at=now,
            )
            .returning(TicketModel.id)
        )
        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()
        await self.session.flush()
        return updated_id is not None

    async def get_tickets_for_audit_timeout(
        self, cutoff: datetime, limit: int = 100
    ) -> list[TicketModel]:
        """Выбирает завершенные тикеты, требующие аудита по таймауту 10 минут."""
        from src.analytics.models import (
            IncidentStatus,
            IncidentType,
            SystemIncidentModel,
            TicketAuditModel,
            TicketFeedbackModel,
        )

        subq_audit = select(TicketAuditModel.ticket_id).where(
            TicketAuditModel.ticket_id == TicketModel.id
        )
        subq_feedback = select(TicketFeedbackModel.ticket_id).where(
            TicketFeedbackModel.ticket_id == TicketModel.id
        )
        subq_incident = select(SystemIncidentModel.ticket_id).where(
            SystemIncidentModel.ticket_id == TicketModel.id,
            SystemIncidentModel.incident_type == IncidentType.API_ERROR.value,
            SystemIncidentModel.status == IncidentStatus.OPEN.value,
        )

        stmt = (
            select(TicketModel)
            .where(
                TicketModel.status == TicketStatus.RESOLVED.value,
                TicketModel.closed_at <= cutoff,
                ~subq_audit.exists(),
                ~subq_feedback.exists(),
                ~subq_incident.exists(),
            )
            .order_by(TicketModel.closed_at.asc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all())


class ChatRepository:
    """Репозиторий для работы с чатами и репликами переписки."""

    def __init__(self, session: AsyncSession) -> None:
        """Инициализирует репозиторий чатов активной асинхронной сессией базы данных."""
        self.session = session

    async def get_by_id(self, chat_id: UUID) -> ChatModel | None:
        """Извлекает чат по первичному ключу."""
        return await self.session.get(ChatModel, chat_id)

    async def get_by_client_id(self, client_id: UUID) -> ChatModel | None:
        """Извлекает постоянный чат конкретного клиента."""
        stmt = select(ChatModel).where(ChatModel.client_id == client_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def create(self, chat: ChatModel) -> ChatModel:
        """Сохраняет новую запись чата в базу данных."""
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def save_message(
        self,
        message: MessageModel,
        sources: list[MessageSourceModel] | None = None,
    ) -> MessageModel:
        """Сохраняет реплику диалога и связанные с ней нормативные источники."""
        self.session.add(message)
        if sources:
            for source in sources:
                source.message = message
                self.session.add(source)
        await self.session.flush()
        return message

    async def get_recent_messages(
        self, chat_id: UUID, limit: int = 50
    ) -> list[MessageModel]:
        """Выбирает до limit последних реплик чата с источниками в хронологическом порядке."""
        stmt = (
            select(MessageModel)
            .join(TicketModel, MessageModel.ticket_id == TicketModel.id)
            .where(TicketModel.chat_id == chat_id)
            .options(
                selectinload(MessageModel.sources),
                selectinload(MessageModel.sender).selectinload(UserModel.role),
            )
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(reversed(result.all()))

    async def get_messages_by_ticket_id(
        self, ticket_id: UUID
    ) -> list[MessageModel]:
        """Возвращает все сообщения обращения с привязанными источниками."""
        stmt = (
            select(MessageModel)
            .where(MessageModel.ticket_id == ticket_id)
            .options(
                selectinload(MessageModel.sources),
                selectinload(MessageModel.sender).selectinload(UserModel.role),
            )
            .order_by(MessageModel.created_at.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_messages_since_id(
        self, ticket_id: UUID, last_event_id: UUID
    ) -> list[MessageModel]:
        """Возвращает сообщения тикета, созданные строго позже указанного last_event_id."""
        ref_msg = await self.session.get(MessageModel, last_event_id)
        if ref_msg is not None:
            stmt = (
                select(MessageModel)
                .where(
                    MessageModel.ticket_id == ticket_id,
                    MessageModel.created_at > ref_msg.created_at,
                )
                .options(
                    selectinload(MessageModel.sources),
                    selectinload(MessageModel.sender).selectinload(
                        UserModel.role
                    ),
                )
                .order_by(MessageModel.created_at.asc())
            )
        else:
            stmt = (
                select(MessageModel)
                .where(
                    MessageModel.ticket_id == ticket_id,
                    MessageModel.id > last_event_id,
                )
                .options(
                    selectinload(MessageModel.sources),
                    selectinload(MessageModel.sender).selectinload(
                        UserModel.role
                    ),
                )
                .order_by(MessageModel.created_at.asc())
            )
        result = await self.session.scalars(stmt)
        return list(result.all())
