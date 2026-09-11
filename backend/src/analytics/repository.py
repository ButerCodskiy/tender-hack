"""Слой доступа к данным домена analytics."""

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import uuid6
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.analytics.models import (
    IncidentStatus,
    OperatorMetricDailyModel,
    SystemIncidentModel,
    TicketAuditModel,
    TicketFeedbackModel,
)
from src.analytics.schemas import OperatorDailyMetricResponseSchema
from src.auth.models import UserModel
from src.chat.models import TicketModel
from src.core.config import settings
from src.operators.models import OperatorProfileModel, SupportLineModel


class AnalyticsRepository:
    """Репозиторий для сохранения и выборки сущностей контроля качества и инцидентов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_feedback(
        self, feedback: TicketFeedbackModel
    ) -> TicketFeedbackModel:
        """Сохраняет отзыв клиента."""
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get_feedback_by_ticket_id(
        self, ticket_id: UUID
    ) -> TicketFeedbackModel | None:
        """Находит отзыв по идентификатору обращения."""
        stmt = select(TicketFeedbackModel).where(
            TicketFeedbackModel.ticket_id == ticket_id
        )
        return (await self.session.scalars(stmt)).first()

    async def create_audit(self, audit: TicketAuditModel) -> TicketAuditModel:
        """Сохраняет результаты автоматического аудита диалога."""
        self.session.add(audit)
        await self.session.flush()
        return audit

    async def get_audit_by_ticket_id(
        self, ticket_id: UUID
    ) -> TicketAuditModel | None:
        """Находит результаты аудита по идентификатору обращения."""
        stmt = select(TicketAuditModel).where(
            TicketAuditModel.ticket_id == ticket_id
        )
        return (await self.session.scalars(stmt)).first()

    async def create_incident(
        self, incident: SystemIncidentModel
    ) -> SystemIncidentModel:
        """Регистрирует системный технический сбой."""
        self.session.add(incident)
        await self.session.flush()
        return incident

    async def get_open_incident_by_type(
        self,
        incident_type: str,
        window_hours: int = 2,
        now: datetime | None = None,
    ) -> SystemIncidentModel | None:
        """Находит недавний открытый инцидент того же типа для дедупликации."""
        current_time = now or datetime.now(settings.TIMEZONE)
        cutoff = current_time - timedelta(hours=window_hours)

        stmt = (
            select(SystemIncidentModel)
            .where(
                SystemIncidentModel.incident_type == incident_type,
                SystemIncidentModel.status == IncidentStatus.OPEN,
                SystemIncidentModel.created_at >= cutoff,
            )
            .order_by(SystemIncidentModel.created_at.desc())
        )
        return (await self.session.scalars(stmt)).first()

    async def get_ticket_full_audit_data(
        self, ticket_id: UUID
    ) -> TicketModel | None:
        """Загружает обращение с жадной подгрузкой реплик, отзыва, линии и оператора."""
        stmt = (
            select(TicketModel)
            .where(TicketModel.id == ticket_id)
            .options(
                selectinload(TicketModel.messages),
                selectinload(TicketModel.feedback),
                selectinload(TicketModel.line),
                selectinload(TicketModel.assigned_operator),
            )
        )
        return (await self.session.scalars(stmt)).first()

    async def get_dashboard_metrics(
        self,
        from_dt: datetime,
        to_dt: datetime,
    ) -> dict[str, Any]:
        """Вычисляет сводные показатели дашборда на лету за указанный период."""
        query = text(
            """
            WITH period_tickets AS (
                SELECT
                    t.id,
                    t.status,
                    t.assigned_operator_id,
                    t.created_at,
                    t.opened_at,
                    t.assigned_at,
                    t.closed_at,
                    tf.score AS client_score,
                    ta.is_system_issue,
                    ta.politeness_score,
                    ta.completeness_score
                FROM tickets t
                LEFT JOIN ticket_feedbacks tf ON tf.ticket_id = t.id
                LEFT JOIN ticket_audits ta ON ta.ticket_id = t.id
                WHERE t.created_at >= :from_dt
                  AND t.created_at <= :to_dt
            ),
            first_responses AS (
                SELECT
                    m.ticket_id,
                    MIN(m.created_at) AS first_operator_response_at
                FROM messages m
                JOIN period_tickets pt ON pt.id = m.ticket_id
                WHERE m.sender_type = 'operator'
                GROUP BY m.ticket_id
            )
            SELECT
                COUNT(pt.id) AS total_tickets,
                COUNT(pt.id) FILTER (WHERE pt.status = 'resolved' AND pt.assigned_operator_id IS NULL) AS bot_resolved_tickets,
                ROUND(
                    COALESCE(
                        (COUNT(pt.id) FILTER (WHERE pt.status = 'resolved' AND pt.assigned_operator_id IS NULL)::float /
                         NULLIF(COUNT(pt.id) FILTER (WHERE pt.status = 'resolved'), 0)) * 100.0,
                        0.0
                    )::numeric,
                    2
                ) AS bot_resolved_percent,
                ROUND(
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (fr.first_operator_response_at - pt.created_at))),
                        0.0
                    )::numeric,
                    2
                ) AS avg_first_response_time_sec,
                ROUND(
                    COALESCE(
                        AVG(EXTRACT(EPOCH FROM (pt.closed_at - COALESCE(pt.opened_at, pt.assigned_at, pt.created_at))))
                        FILTER (WHERE pt.closed_at IS NOT NULL),
                        0.0
                    )::numeric,
                    2
                ) AS avg_handling_time_sec,
                ROUND(COALESCE(AVG(pt.client_score), 0.0)::numeric, 2) AS client_csat,
                ROUND(
                    COALESCE(
                        AVG(pt.client_score) FILTER (WHERE pt.is_system_issue IS NOT TRUE),
                        0.0
                    )::numeric,
                    2
                ) AS adjusted_csat,
                ROUND(COALESCE(AVG(pt.politeness_score), 0.0)::numeric, 2) AS avg_ai_politeness_score,
                ROUND(COALESCE(AVG(pt.completeness_score), 0.0)::numeric, 2) AS avg_ai_completeness_score,
                (SELECT COUNT(*) FROM system_incidents WHERE status = 'open') AS active_incidents_count
            FROM period_tickets pt
            LEFT JOIN first_responses fr ON fr.ticket_id = pt.id;
            """
        )
        result = await self.session.execute(
            query, {"from_dt": from_dt, "to_dt": to_dt}
        )
        row = result.mappings().one()
        return {
            "total_tickets": int(row["total_tickets"] or 0),
            "bot_resolved_tickets": int(row["bot_resolved_tickets"] or 0),
            "bot_resolved_percent": float(row["bot_resolved_percent"] or 0.0),
            "avg_first_response_time_sec": float(
                row["avg_first_response_time_sec"] or 0.0
            ),
            "avg_handling_time_sec": float(
                row["avg_handling_time_sec"] or 0.0
            ),
            "client_csat": float(row["client_csat"] or 0.0),
            "adjusted_csat": float(row["adjusted_csat"] or 0.0),
            "avg_ai_politeness_score": float(
                row["avg_ai_politeness_score"] or 0.0
            ),
            "avg_ai_completeness_score": float(
                row["avg_ai_completeness_score"] or 0.0
            ),
            "active_incidents_count": int(row["active_incidents_count"] or 0),
        }

    async def calculate_operator_metrics_for_date(
        self,
        target_date: date,
        operator_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Агрегирует суточные показатели эффективности операторов за указанную дату."""
        day_start = datetime.combine(target_date, time.min).replace(
            tzinfo=settings.TIMEZONE
        )
        day_end = datetime.combine(target_date, time.max).replace(
            tzinfo=settings.TIMEZONE
        )

        query = text(
            """
            WITH op_tickets AS (
                SELECT
                    t.id,
                    t.assigned_operator_id AS op_id,
                    t.opened_at,
                    t.assigned_at,
                    t.created_at,
                    t.closed_at,
                    tf.score AS client_score,
                    ta.is_system_issue,
                    ta.politeness_score,
                    ta.completeness_score
                FROM tickets t
                LEFT JOIN ticket_feedbacks tf ON tf.ticket_id = t.id
                LEFT JOIN ticket_audits ta ON ta.ticket_id = t.id
                WHERE t.assigned_operator_id IS NOT NULL
                  AND t.closed_at >= :day_start
                  AND t.closed_at <= :day_end
                  AND (:operator_id IS NULL OR t.assigned_operator_id = :operator_id)
            ),
            first_responses AS (
                SELECT
                    m.ticket_id,
                    MIN(m.created_at) AS first_response_at
                FROM messages m
                JOIN op_tickets ot ON ot.id = m.ticket_id
                WHERE m.sender_type = 'operator'
                GROUP BY m.ticket_id
            )
            SELECT
                ot.op_id AS operator_id,
                COUNT(ot.id) AS total_tickets_handled,
                ROUND(
                    AVG(EXTRACT(EPOCH FROM (fr.first_response_at - COALESCE(ot.opened_at, ot.assigned_at))))::numeric,
                    2
                ) AS avg_first_response_time_sec,
                ROUND(
                    AVG(EXTRACT(EPOCH FROM (ot.closed_at - COALESCE(ot.opened_at, ot.assigned_at, ot.created_at))))::numeric,
                    2
                ) AS avg_handling_time_sec,
                ROUND(AVG(ot.client_score)::numeric, 2) AS avg_client_csat,
                ROUND(
                    AVG(ot.client_score) FILTER (WHERE ot.is_system_issue IS NOT TRUE)::numeric,
                    2
                ) AS avg_adjusted_csat,
                ROUND(
                    AVG((ot.politeness_score + ot.completeness_score) / 2.0)::numeric,
                    2
                ) AS avg_ai_quality_score
            FROM op_tickets ot
            LEFT JOIN first_responses fr ON fr.ticket_id = ot.id
            GROUP BY ot.op_id;
            """
        )
        result = await self.session.execute(
            query,
            {
                "day_start": day_start,
                "day_end": day_end,
                "operator_id": operator_id,
            },
        )
        rows = result.mappings().all()
        metrics: list[dict[str, Any]] = []
        for r in rows:
            metrics.append(
                {
                    "id": uuid6.uuid7(),
                    "operator_id": r["operator_id"],
                    "metric_date": target_date,
                    "total_tickets_handled": int(
                        r["total_tickets_handled"] or 0
                    ),
                    "avg_first_response_time_sec": r[
                        "avg_first_response_time_sec"
                    ],
                    "avg_handling_time_sec": r["avg_handling_time_sec"],
                    "avg_client_csat": r["avg_client_csat"],
                    "avg_adjusted_csat": r["avg_adjusted_csat"],
                    "avg_ai_quality_score": r["avg_ai_quality_score"],
                }
            )
        return metrics

    async def upsert_operator_daily_metrics(
        self,
        metrics: list[dict[str, Any]],
    ) -> None:
        """Атомарно сохраняет суточные метрики с разрешением конфликтов по (operator_id, metric_date)."""
        if not metrics:
            return

        stmt = pg_insert(OperatorMetricDailyModel).values(metrics)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_operator_daily_metrics",
            set_={
                "total_tickets_handled": stmt.excluded.total_tickets_handled,
                "avg_first_response_time_sec": stmt.excluded.avg_first_response_time_sec,
                "avg_handling_time_sec": stmt.excluded.avg_handling_time_sec,
                "avg_client_csat": stmt.excluded.avg_client_csat,
                "avg_adjusted_csat": stmt.excluded.avg_adjusted_csat,
                "avg_ai_quality_score": stmt.excluded.avg_ai_quality_score,
                "updated_at": func.clock_timestamp(),
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_operator_metrics(
        self,
        target_date: date | None = None,
        line_code: str | None = None,
    ) -> list[OperatorDailyMetricResponseSchema]:
        """Возвращает суточные метрики операторов с фильтрацией по дате и линии поддержки."""
        stmt = (
            select(
                OperatorMetricDailyModel.operator_id,
                UserModel.full_name,
                UserModel.email,
                SupportLineModel.code.label("line_code"),
                OperatorMetricDailyModel.metric_date,
                OperatorMetricDailyModel.total_tickets_handled,
                OperatorMetricDailyModel.avg_first_response_time_sec,
                OperatorMetricDailyModel.avg_handling_time_sec,
                OperatorMetricDailyModel.avg_client_csat,
                OperatorMetricDailyModel.avg_adjusted_csat,
                OperatorMetricDailyModel.avg_ai_quality_score,
            )
            .join(
                UserModel, UserModel.id == OperatorMetricDailyModel.operator_id
            )
            .outerjoin(
                OperatorProfileModel,
                OperatorProfileModel.user_id
                == OperatorMetricDailyModel.operator_id,
            )
            .outerjoin(
                SupportLineModel,
                SupportLineModel.id == OperatorProfileModel.line_id,
            )
        )

        if target_date is not None:
            stmt = stmt.where(
                OperatorMetricDailyModel.metric_date == target_date
            )
        if line_code is not None:
            stmt = stmt.where(SupportLineModel.code == line_code)

        stmt = stmt.order_by(
            OperatorMetricDailyModel.metric_date.desc(),
            OperatorMetricDailyModel.total_tickets_handled.desc(),
        )

        rows = (await self.session.execute(stmt)).all()
        results: list[OperatorDailyMetricResponseSchema] = []
        for r in rows:
            results.append(
                OperatorDailyMetricResponseSchema(
                    operator_id=r.operator_id,
                    operator_name=r.full_name or r.email,
                    line_code=r.line_code or "L1",
                    metric_date=r.metric_date,
                    total_tickets_handled=r.total_tickets_handled,
                    avg_first_response_time_sec=(
                        float(r.avg_first_response_time_sec)
                        if r.avg_first_response_time_sec is not None
                        else None
                    ),
                    avg_handling_time_sec=(
                        float(r.avg_handling_time_sec)
                        if r.avg_handling_time_sec is not None
                        else None
                    ),
                    avg_client_csat=(
                        float(r.avg_client_csat)
                        if r.avg_client_csat is not None
                        else None
                    ),
                    avg_adjusted_csat=(
                        float(r.avg_adjusted_csat)
                        if r.avg_adjusted_csat is not None
                        else None
                    ),
                    avg_ai_quality_score=(
                        float(r.avg_ai_quality_score)
                        if r.avg_ai_quality_score is not None
                        else None
                    ),
                )
            )
        return results

    async def get_incidents(
        self,
        status: str | None = None,
        incident_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SystemIncidentModel]:
        """Возвращает реестр инцидентов с фильтрацией по статусу и типу.

        Фильтры применяются только при наличии значений (None = без фильтра).
        Сортировка: created_at DESC. Покрывается индексом idx_incidents_status_created.
        """
        stmt = (
            select(SystemIncidentModel)
            .order_by(SystemIncidentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(SystemIncidentModel.status == status)
        if incident_type is not None:
            stmt = stmt.where(
                SystemIncidentModel.incident_type == incident_type
            )
        return list((await self.session.scalars(stmt)).all())

    async def get_tickets_for_export(
        self,
        dt_from: datetime,
        dt_to: datetime,
    ) -> list[TicketModel]:
        """Загружает терминальные тикеты за диапазон дат с жадной подгрузкой связей.

        Использует joinedload (4 LEFT OUTER JOIN) вместо lazy-loading во избежание
        N+1 запросов. .unique() обязателен при joinedload для дедупликации строк.
        Временные границы dt_from/dt_to должны быть timezone-aware (Europe/Moscow).
        """
        stmt = (
            select(TicketModel)
            .where(
                TicketModel.status.in_(
                    [
                        "resolved",
                        "closed_by_inactivity",
                        "closed_by_moderation",
                    ]
                ),
                TicketModel.created_at >= dt_from,
                TicketModel.created_at <= dt_to,
            )
            .options(
                joinedload(TicketModel.line),
                joinedload(TicketModel.assigned_operator),
                joinedload(TicketModel.feedback),
                joinedload(TicketModel.audit),
            )
            .order_by(TicketModel.created_at.asc())
        )
        return list((await self.session.scalars(stmt)).unique().all())
