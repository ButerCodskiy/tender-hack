"""Модели базы данных домена operators."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import uuid6
from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base

if TYPE_CHECKING:
    from src.auth.models import UserModel
    from src.chat.models import TicketModel


class SupportLineModel(Base):
    """Справочник линий поддержки и очередей маршрутизации специалистов."""

    __tablename__ = "support_lines"

    id: Mapped[int] = mapped_column(
        SmallInteger, primary_key=True, autoincrement=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    def __repr__(self) -> str:
        return f"<SupportLineModel id={self.id} code={self.code!r}>"


class OperatorShiftStatus(StrEnum):
    """Статусы рабочей смены оператора."""

    ACTIVE = "active"
    BREAK = "break"
    OFFLINE = "offline"


class OperatorProfileModel(Base):
    """Профиль оператора для управления сменой и балансировки нагрузки."""

    __tablename__ = "operator_profiles"
    __table_args__ = (
        CheckConstraint(
            "shift_status IN ('active', 'break', 'offline')",
            name="chk_operator_shift_status",
        ),
        CheckConstraint(
            "max_slots > 0 AND max_slots <= 20",
            name="chk_operator_max_slots",
        ),
        Index(
            "idx_operator_profiles_dispatch",
            "line_id",
            "shift_status",
            postgresql_where=(text("shift_status = 'active'")),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    line_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("support_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    shift_status: Mapped[str] = mapped_column(
        String(16),
        default=OperatorShiftStatus.OFFLINE,
        server_default="offline",
        nullable=False,
    )
    max_slots: Mapped[int] = mapped_column(
        SmallInteger,
        default=5,
        server_default="5",
        nullable=False,
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )

    user: Mapped["UserModel"] = relationship(back_populates="operator_profile")
    line: Mapped["SupportLineModel"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<OperatorProfileModel user_id={self.user_id} "
            f"line_id={self.line_id} shift_status={self.shift_status!r}>"
        )


class TicketCopilotSummaryModel(Base):
    """Модель аналитической подсказки и контекста оператора (AI Copilot)."""

    __tablename__ = "ticket_copilot_summaries"
    __table_args__ = (Index("idx_copilot_summaries_ticket", "ticket_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_line_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    suggested_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_chunk_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)),
        default=list,
        server_default="{}",
        nullable=False,
    )
    similar_resolved_tickets: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    ticket: Mapped["TicketModel"] = relationship(
        back_populates="copilot_summary"
    )

    def __repr__(self) -> str:
        return f"<TicketCopilotSummaryModel id={self.id} ticket_id={self.ticket_id}>"
