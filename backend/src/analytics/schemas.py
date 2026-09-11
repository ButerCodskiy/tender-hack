"""Схемы валидации данных домена analytics."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.analytics.models import IncidentType, RootCauseType


class AuditTicketPayloadSchema(BaseModel):
    """Схема полезной нагрузки задачи Taskiq audit_ticket_quality."""

    ticket_id: UUID = Field(
        ..., description="Уникальный идентификатор закрытого тикета"
    )
    trigger_reason: str = Field(
        "feedback_received",
        description="Источник запуска: feedback_received или feedback_timeout",
    )


class AuditLlmOutputSchema(BaseModel):
    """Схема структурированного ответа языковой модели (LLM-Judge)."""

    politeness_score: int = Field(
        ..., ge=1, le=5, description="Оценка вежливости и этики от 1 до 5"
    )
    completeness_score: int = Field(
        ..., ge=1, le=5, description="Оценка полноты и точности от 1 до 5"
    )
    root_cause: Literal[
        RootCauseType.OPERATOR_ERROR,
        RootCauseType.SYSTEM_ISSUE,
        RootCauseType.REGULATION_DISSATISFACTION,
        RootCauseType.NONE,
    ] = Field(
        RootCauseType.NONE,
        description="Первопричина негатива или сложностей в диалоге",
    )
    summary: str = Field(
        ..., description="Краткое аналитическое резюме вердикта модели"
    )
    is_system_issue: bool = Field(
        default=False,
        description="Флаг технического сбоя платформы для снятия вины с оператора",
    )
    incident_type: (
        Literal[
            IncidentType.PORTAL_DOWNTIME,
            IncidentType.CRYPTO_PLUGIN,
            IncidentType.API_ERROR,
        ]
        | None
    ) = Field(
        None,
        description="Категория сбоя платформы при наличии системного инцидента",
    )
    incident_description: str | None = Field(
        None,
        description="Краткое описание симптомов сбоя для добавления в реестр инцидентов",
    )


class FeedbackCreateRequestSchema(BaseModel):
    """Схема запроса на оставление отзыва клиентом."""

    score: int = Field(
        ..., ge=1, le=5, description="Оценка качества от 1 до 5 звезд"
    )
    comment: str | None = Field(
        None, max_length=1000, description="Комментарий клиента к оценке"
    )


class FeedbackResponseSchema(BaseModel):
    """Схема ответа с данными сохраненного отзыва клиента."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор отзыва")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    score: int = Field(..., description="Оценка от 1 до 5")
    comment: str | None = Field(None, description="Текст комментария")
    created_at: datetime = Field(..., description="Время фиксации отзыва")


class TicketAuditResponseSchema(BaseModel):
    """Схема ответа с результатами аудита качества диалога."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор записи аудита")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    politeness_score: int = Field(..., description="Балл вежливости от 1 до 5")
    completeness_score: int = Field(..., description="Балл полноты от 1 до 5")
    root_cause: str | None = Field(
        None, description="Классификация первопричины"
    )
    summary: str = Field(..., description="Аналитическое заключение")
    is_system_issue: bool = Field(
        ..., description="Признак технического сбоя платформы"
    )
    created_at: datetime = Field(..., description="Время проведения аудита")


class SystemIncidentResponseSchema(BaseModel):
    """Схема системного инцидента из реестра технических ошибок."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор инцидента")
    ticket_id: UUID = Field(..., description="Обращение, выявившее сбой")
    incident_type: str = Field(..., description="Тип проблемы")
    description: str = Field(..., description="Описание симптомов")
    status: str = Field(..., description="Статус: open, in_review, resolved")
    created_at: datetime = Field(..., description="Время фиксации")
    resolved_at: datetime | None = Field(None, description="Время устранения")


EXPORT_HEADERS: list[str] = [
    "ticket_id",
    "created_at",
    "closed_at",
    "handling_time_sec",
    "status",
    "priority",
    "line_code",
    "assigned_operator_name",
    "feedback_score",
    "feedback_comment",
    "is_system_issue",
    "root_cause",
    "politeness_score",
    "completeness_score",
    "audit_summary",
]


class AnalyticsExportRowSchema(BaseModel):
    """Строка экспортного отчёта по завершённому обращению."""

    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    created_at: datetime = Field(..., description="Время создания обращения")
    closed_at: datetime | None = Field(None, description="Время закрытия")
    handling_time_sec: int | None = Field(
        None, description="Длительность обработки в секундах"
    )
    status: str = Field(..., description="Итоговый статус обращения")
    priority: str = Field(..., description="Приоритет: P0, P1, P2")
    line_code: str | None = Field(None, description="Код линии поддержки")
    assigned_operator_name: str | None = Field(
        None, description="ФИО назначенного оператора"
    )
    feedback_score: int | None = Field(
        None, description="Оценка клиента от 1 до 5"
    )
    feedback_comment: str | None = Field(
        None, description="Комментарий клиента"
    )
    is_system_issue: bool | None = Field(
        None, description="Признак технического сбоя платформы"
    )
    root_cause: str | None = Field(None, description="Первопричина негатива")
    politeness_score: int | None = Field(
        None, description="Балл вежливости от 1 до 5"
    )
    completeness_score: int | None = Field(
        None, description="Балл полноты от 1 до 5"
    )
    audit_summary: str | None = Field(
        None, description="Аналитическое резюме аудита"
    )

    def to_csv_list(self) -> list[str]:
        """Сериализует строку отчёта в плоский список значений для csv.writer.

        None-значения преобразуются в пустую строку. Форматирование datetime
        через isoformat() обеспечивает однозначную читаемость в Excel.
        """
        return [
            str(self.ticket_id),
            self.created_at.isoformat(),
            self.closed_at.isoformat() if self.closed_at is not None else "",
            str(self.handling_time_sec)
            if self.handling_time_sec is not None
            else "",
            self.status,
            self.priority,
            self.line_code or "",
            self.assigned_operator_name or "",
            str(self.feedback_score)
            if self.feedback_score is not None
            else "",
            self.feedback_comment or "",
            str(self.is_system_issue)
            if self.is_system_issue is not None
            else "",
            self.root_cause or "",
            str(self.politeness_score)
            if self.politeness_score is not None
            else "",
            str(self.completeness_score)
            if self.completeness_score is not None
            else "",
            self.audit_summary or "",
        ]


class AnalyticsExportResponseSchema(BaseModel):
    """Схема JSON-ответа экспортного отчёта за выбранный интервал дат."""

    items: list[AnalyticsExportRowSchema] = Field(
        ..., description="Список строк отчёта"
    )
    total: int = Field(..., description="Число строк в выборке")
    from_date: date = Field(..., description="Дата начала периода")
    to_date: date = Field(..., description="Дата окончания периода")


class AnalyticsDashboardResponseSchema(BaseModel):
    """Схема ответа сводной аналитической витрины показателей эффективности."""

    model_config = ConfigDict(from_attributes=True)

    total_tickets: int = Field(
        ..., description="Общее число обращений за период"
    )
    bot_resolved_percent: float = Field(
        ..., description="Процент обращений, решенных ботом без человека"
    )
    bot_resolved_tickets: int = Field(
        default=0, description="Абсолютное число обращений, решенных ботом"
    )
    avg_first_response_time_sec: float = Field(
        ..., description="Среднее время первого ответа оператора (сек)"
    )
    avg_handling_time_sec: float = Field(
        ..., description="Среднее время полного решения обращения (сек)"
    )
    client_csat: float = Field(
        ..., description="Средняя базовая оценка клиентов от 1 до 5"
    )
    adjusted_csat: float = Field(
        ...,
        description="Скорректированная оценка клиентов за вычетом системных сбоев",
    )
    avg_ai_politeness_score: float = Field(
        ..., description="Оценка вежливости по аудиту языковой модели"
    )
    avg_ai_completeness_score: float = Field(
        ..., description="Оценка полноты по аудиту языковой модели"
    )
    active_incidents_count: int = Field(
        ..., description="Число нерешенных технических сбоев портала"
    )


class OperatorDailyMetricResponseSchema(BaseModel):
    """Схема суточных показателей эффективности конкретного оператора."""

    model_config = ConfigDict(from_attributes=True)

    operator_id: UUID = Field(..., description="Идентификатор оператора")
    operator_name: str = Field(..., description="ФИО сотрудника")
    line_code: str = Field(..., description="Линия поддержки")
    metric_date: date = Field(..., description="Отчетная дата")
    total_tickets_handled: int = Field(
        ..., description="Количество обработанных тикетов"
    )
    avg_first_response_time_sec: float | None = Field(
        None, description="Среднее время первого ответа (сек)"
    )
    avg_handling_time_sec: float | None = Field(
        None, description="Среднее время диалога (сек)"
    )
    avg_client_csat: float | None = Field(
        None, description="Средняя оценка клиентов"
    )
    avg_adjusted_csat: float | None = Field(
        None, description="Скорректированная оценка"
    )
    avg_ai_quality_score: float | None = Field(
        None, description="Оценка качества от модели"
    )


class OperatorMetricsListResponseSchema(BaseModel):
    """Схема списка суточных показателей операторов с общим количеством."""

    model_config = ConfigDict(from_attributes=True)

    items: list[OperatorDailyMetricResponseSchema] = Field(
        default_factory=list, description="Список метрик операторов"
    )
    total: int = Field(0, description="Общее число записей")


class DailyMetricsPayloadSchema(BaseModel):
    """Схема полезной нагрузки фоновой задачи Taskiq calculate_daily_metrics."""

    metric_date: date | str | None = Field(
        None, description="Дата расчетного периода (YYYY-MM-DD)"
    )
    operator_id: UUID | None = Field(
        None,
        description="Идентификатор конкретного сотрудника для точечного перерасчета",
    )


class SystemicIssueItemSchema(BaseModel):
    """Схема выявленной системной проблемы платформы или регламентов."""

    title: str = Field(..., description="Название системной проблемы")
    evidence_count: int = Field(
        ..., description="Число зафиксированных жалоб/тикетов"
    )
    affected_line: Literal["L1", "L2", "L3"] = Field(
        ..., description="Затронутая линия поддержки: L1, L2 или L3"
    )
    suspected_cause: str = Field(
        ..., description="Предполагаемая первопричина сбоя или трудности"
    )
    examples: list[str] = Field(
        default_factory=list,
        description="Цитаты и выдержки из обращений пользователей",
    )
    recommendation: str = Field(
        ...,
        description="Конкретная рекомендация для методистов или разработчиков Портала",
    )


class SystemicMetricsSummarySchema(BaseModel):
    """Сводные нормализованные показатели эффективности работы поддержки."""

    total_tickets: int = Field(
        ..., description="Общее число тикетов за период"
    )
    csat_score: float = Field(
        ...,
        description="Нормализованный CSAT (доля_лайков + средний_балл_звезд / 5.0) / 2.0",
    )
    deflection_rate: float = Field(
        ...,
        description="Доля обращений, закрытых ботом без эскалации на оператора",
    )
    oqs_score: float = Field(
        ...,
        description="Интегральная оценка качества работы поддержки OQS (Operator Quality Score)",
    )


class SystemicIssuesReportResponseSchema(BaseModel):
    """Итоговое структурированное аналитическое заключение по системным проблемам."""

    period: str = Field(
        ...,
        description="Анализируемый период (например, 2026-09-01 - 2026-09-12)",
    )
    summary: str = Field(
        ...,
        description="Краткий аналитический обзор ключевых проблем пользователей",
    )
    systemic_issues: list[SystemicIssueItemSchema] = Field(
        default_factory=list,
        description="Кластеризованные системные проблемы",
    )
    metrics_summary: SystemicMetricsSummarySchema = Field(
        ..., description="Сводные метрики эффективности"
    )
    positive_patterns: list[str] = Field(
        default_factory=list,
        description="Положительные паттерны и зоны успешного обслуживания",
    )
