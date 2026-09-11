"""Модели базы данных домена analytics."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import uuid6
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base

if TYPE_CHECKING:
    from src.auth.models import UserModel
    from src.chat.models import TicketModel


class RootCauseType(StrEnum):
    """Категории первопричин негатива и проблем в обслуживании диалогов."""

    OPERATOR_ERROR = "operator_error"
    SYSTEM_ISSUE = "system_issue"
    REGULATION_DISSATISFACTION = "regulation_dissatisfaction"
    NONE = "none"


class IncidentType(StrEnum):
    """Типы системных инцидентов и сбоев платформы."""

    PORTAL_DOWNTIME = "portal_downtime"
    CRYPTO_PLUGIN = "crypto_plugin"
    API_ERROR = "api_error"


class IncidentStatus(StrEnum):
    """Статусы жизненного цикла системного инцидента."""

    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


class TicketFeedbackModel(Base):
    """Модель отзыва и оценки клиента после завершения обращения."""

    __tablename__ = "ticket_feedbacks"
    __table_args__ = (
        CheckConstraint(
            "score >= 1 AND score <= 5",
            name="chk_feedback_score",
        ),
        Index("idx_feedbacks_score", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    ticket: Mapped["TicketModel"] = relationship(back_populates="feedback")

    def __repr__(self) -> str:
        return f"<TicketFeedbackModel id={self.id} ticket_id={self.ticket_id} score={self.score}>"


class TicketAuditModel(Base):
    """Модель автоматического аудита диалога языковой моделью (AI-QA)."""

    __tablename__ = "ticket_audits"
    __table_args__ = (
        CheckConstraint(
            "politeness_score BETWEEN 1 AND 5",
            name="chk_audit_politeness",
        ),
        CheckConstraint(
            "completeness_score BETWEEN 1 AND 5",
            name="chk_audit_completeness",
        ),
        CheckConstraint(
            "root_cause IN ('operator_error', 'system_issue', 'regulation_dissatisfaction', 'none')",
            name="chk_audit_root_cause",
        ),
        Index(
            "idx_audits_system_issue",
            "is_system_issue",
            postgresql_where=text("is_system_issue = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    politeness_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    completeness_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )
    root_cause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    is_system_issue: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )

    ticket: Mapped["TicketModel"] = relationship(back_populates="audit")

    def __repr__(self) -> str:
        return (
            f"<TicketAuditModel id={self.id} ticket_id={self.ticket_id} "
            f"root_cause={self.root_cause!r} is_system_issue={self.is_system_issue}>"
        )


class SystemIncidentModel(Base):
    """Модель каталога системных технических сбоев портала."""

    __tablename__ = "system_incidents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_review', 'resolved')",
            name="chk_incident_status",
        ),
        CheckConstraint(
            "incident_type IN ('portal_downtime', 'crypto_plugin', 'api_error')",
            name="chk_incident_type",
        ),
        # Частичный индекс для быстрой дедупликации открытых инцидентов
        Index(
            "idx_incidents_status",
            "status",
            postgresql_where=text("status = 'open'"),
        ),
        # Составной индекс для реестра: фильтр по любому статусу + сортировка по дате
        Index(
            "idx_incidents_status_created",
            "status",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="open", server_default="open", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ticket: Mapped["TicketModel"] = relationship(back_populates="incidents")

    def __repr__(self) -> str:
        return (
            f"<SystemIncidentModel id={self.id} ticket_id={self.ticket_id} "
            f"type={self.incident_type!r} status={self.status!r}>"
        )


class OperatorMetricDailyModel(Base):
    """Агрегированная таблица суточных показателей оператора."""

    __tablename__ = "operator_metrics_daily"
    __table_args__ = (
        UniqueConstraint(
            "operator_id", "metric_date", name="uq_operator_daily_metrics"
        ),
        Index("idx_operator_metrics_date", "metric_date"),
        Index(
            "idx_metrics_operator_period",
            "operator_id",
            text("metric_date DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid6.uuid7
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_tickets_handled: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    avg_first_response_time_sec: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    avg_handling_time_sec: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    avg_client_csat: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    avg_adjusted_csat: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    avg_ai_quality_score: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
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

    operator: Mapped["UserModel"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<OperatorMetricDailyModel id={self.id} operator_id={self.operator_id} "
            f"metric_date={self.metric_date}>"
        )
