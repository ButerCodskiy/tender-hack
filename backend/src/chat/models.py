"""Модели базы данных домена chat."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import uuid6
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.analytics.models import (
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.auth.models import UserModel
from src.db.database import Base

if TYPE_CHECKING:
    from src.operators.models import (
        SupportLineModel,
        TicketCopilotSummaryModel,
    )


class TicketPriority(StrEnum):
    """Приоритеты обращений."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class TicketStatus(StrEnum):
    """Статусы жизненного цикла обращений."""

    BOT_PROCESSING = "bot_processing"  # Первичная обработка ботом
    QUEUED = "queued"  # В очереди к оператору
    ASSIGNED = "assigned"  # Закреплено за оператором
    IN_PROGRESS = "in_progress"  # Активный диалог с оператором
    RESOLVED = "resolved"  # Успешно решено
    CLOSED_BY_INACTIVITY = "closed_by_inactivity"  # Таймаут неактивности
    CLOSED_BY_MODERATION = "closed_by_moderation"  # Нарушение этики общения
    CANCELED = "canceled"  # Отменено клиентом


TERMINAL_TICKET_STATUSES: tuple[TicketStatus, ...] = (
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED_BY_INACTIVITY,
    TicketStatus.CLOSED_BY_MODERATION,
    TicketStatus.CANCELED,
)


class MessageSenderType(StrEnum):
    """Типы авторов сообщений в переписке."""

    CLIENT = "client"
    BOT = "bot"
    OPERATOR = "operator"
    SYSTEM = "system"


class MessageModerationStatus(StrEnum):
    """Статусы проверки сообщений фильтрами модерации."""

    PASSED = "passed"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class ChatModel(Base):
    """Модель долгоживущего чата клиента со службой поддержки."""

    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    client: Mapped[UserModel] = relationship()
    tickets: Mapped[list["TicketModel"]] = relationship(
        back_populates="chat",
        order_by="TicketModel.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<ChatModel id={self.id} client_id={self.client_id}>"


class TicketModel(Base):
    """Модель дискретной сессии обслуживания обращения клиента."""

    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('P0', 'P1', 'P2')",
            name="chk_ticket_priority",
        ),
        CheckConstraint(
            "status IN ('bot_processing', 'queued', 'assigned', 'in_progress', "
            "'resolved', 'closed_by_inactivity', 'closed_by_moderation', 'canceled')",
            name="chk_ticket_status",
        ),
        Index("idx_tickets_chat_history", "chat_id", "created_at"),
        Index(
            "idx_tickets_queued_recovery",
            "line_id",
            "priority",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    line_id: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("support_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    priority: Mapped[str] = mapped_column(
        String(4),
        default=TicketPriority.P2,
        server_default="P2",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=TicketStatus.BOT_PROCESSING,
        nullable=False,
    )
    escalation_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    transferred_from_operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    transfer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    chat: Mapped["ChatModel"] = relationship(
        back_populates="tickets", lazy="selectin"
    )
    line: Mapped["SupportLineModel | None"] = relationship()
    assigned_operator: Mapped["UserModel | None"] = relationship(
        foreign_keys=[assigned_operator_id]
    )
    transferred_from_operator: Mapped["UserModel | None"] = relationship(
        foreign_keys=[transferred_from_operator_id]
    )
    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at.asc()",
    )
    copilot_summary: Mapped["TicketCopilotSummaryModel | None"] = relationship(
        back_populates="ticket",
        uselist=False,
        cascade="all, delete-orphan",
    )
    audit: Mapped["TicketAuditModel | None"] = relationship(
        back_populates="ticket",
        uselist=False,
        cascade="all, delete-orphan",
    )
    feedback: Mapped["TicketFeedbackModel | None"] = relationship(
        back_populates="ticket",
        uselist=False,
        cascade="all, delete-orphan",
    )
    incidents: Mapped[list["SystemIncidentModel"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<TicketModel id={self.id} chat_id={self.chat_id} "
            f"status={self.status!r}>"
        )


class MessageModel(Base):
    """Модель реплики переписки со статусом модерации и метаданными."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('client', 'bot', 'operator', 'system')",
            name="chk_message_sender_type",
        ),
        CheckConstraint(
            "moderation_status IN ('passed', 'flagged', 'blocked')",
            name="chk_message_moderation_status",
        ),
        Index("idx_messages_ticket_feed", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    moderation_status: Mapped[str] = mapped_column(
        String(16),
        default=MessageModerationStatus.PASSED,
        server_default="passed",
        nullable=False,
    )
    moderation_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    ticket: Mapped["TicketModel"] = relationship(back_populates="messages")
    sender: Mapped["UserModel | None"] = relationship(foreign_keys=[sender_id])
    sources: Mapped[list["MessageSourceModel"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageSourceModel.created_at.asc()",
    )

    @property
    def sender_name(self) -> str | None:
        """Отображаемое имя автора реплики."""
        sender_user = self.__dict__.get("sender")
        if sender_user is not None:
            return sender_user.full_name or sender_user.email
        if self.sender_type == MessageSenderType.BOT.value:
            return "ИИ-Ассистент"
        if self.sender_type == MessageSenderType.SYSTEM.value:
            return "Система"
        return None

    @property
    def sender_role(self) -> str | None:
        """Системная роль автора реплики."""
        sender_user = self.__dict__.get("sender")
        if sender_user is not None:
            user_role = sender_user.__dict__.get("role")
            if user_role is not None:
                return user_role.code
        return self.sender_type

    @property
    def ticket_status(self) -> str | None:
        """Статус обращения, к которому относится реплика."""
        ticket_obj = self.__dict__.get("ticket")
        if ticket_obj is not None:
            return ticket_obj.status
        return None

    def __repr__(self) -> str:
        return (
            f"<MessageModel id={self.id} ticket_id={self.ticket_id} "
            f"sender_type={self.sender_type!r}>"
        )


class MessageSourceModel(Base):
    """Модель нормативного источника регламента, подтверждающего ответ бота."""

    __tablename__ = "message_sources"
    __table_args__ = (Index("idx_message_sources_chunk", "chunk_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    message: Mapped["MessageModel"] = relationship(back_populates="sources")

    def __repr__(self) -> str:
        return (
            f"<MessageSourceModel id={self.id} message_id={self.message_id} "
            f"chunk_id={self.chunk_id!r}>"
        )
