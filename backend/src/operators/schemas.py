"""Схемы валидации данных домена operators."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from src.chat.models import TicketModel
    from src.operators.models import OperatorProfileModel


class TicketAssignedDataSchema(BaseModel):
    """Данные карточки тикета для отображения в сайдбаре оператора."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    chat_id: UUID = Field(..., description="Идентификатор чата")
    priority: Literal["P0", "P1", "P2"] = Field(
        default="P2",
        description="Приоритет обращения: P0, P1, P2",
        examples=["P1"],
    )
    status: str = Field(..., description="Статус: assigned или in_progress")
    line_code: str | None = Field(None, description="Код линии поддержки")
    client_name: str | None = Field(None, description="ФИО клиента или email")
    company_name: str | None = Field(
        None, description="Наименование организации поставщика (при наличии)"
    )
    last_message_preview: str | None = Field(
        None, description="Краткий фрагмент последней реплики"
    )
    unread_messages_count: int = Field(
        0, description="Количество непрочитанных реплик от клиента"
    )
    created_at: datetime = Field(..., description="Время создания обращения")
    assigned_at: datetime | None = Field(
        None, description="Время закрепления за специалистом"
    )

    @classmethod
    def from_ticket(cls, ticket: "TicketModel") -> "TicketAssignedDataSchema":
        """Создает схему карточки обращения на основе модели тикета."""
        client = ticket.chat.client if ticket.chat else None
        profile = client.client_profile if client else None
        last_msg = (
            max(ticket.messages, key=lambda m: m.created_at).text
            if ticket.messages
            else None
        )

        return cls(
            ticket_id=ticket.id,
            chat_id=ticket.chat_id,
            priority=ticket.priority,
            status=str(ticket.status),
            line_code=ticket.line.code if ticket.line else None,
            client_name=(client.full_name or client.email) if client else None,
            company_name=profile.company_name if profile else None,
            last_message_preview=last_msg[:100] if last_msg else None,
            created_at=ticket.created_at,
            assigned_at=ticket.assigned_at,
        )


class TicketAssignedEventSchema(BaseModel):
    """Событие назначения обращения оператору через шину событий."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["ticket_assigned"] = "ticket_assigned"
    data: TicketAssignedDataSchema = Field(
        ..., description="Данные карточки назначенного обращения"
    )


@dataclass
class AssignmentResult:
    """Результат выполнения операции распределения тикета."""

    success: bool
    operator: "OperatorProfileModel | None" = None
    ticket: "TicketModel | None" = None
    reason: str | None = None


DispatchTriggerReason = Literal[
    "ticket_escalated",
    "slot_freed",
    "shift_resumed",
    "scheduled_sync",
    "operator_disconnected",
    "inactivity_timeout",
    "queue_recovered",
]


class CheckTimeoutsResult(BaseModel):
    """Результаты выполнения периодической проверки таймаутов системы."""

    bot_tickets_closed: int = Field(
        0, description="Закрыто тикетов бота по неактивности (10 мин)"
    )
    operator_warnings_sent: int = Field(
        0,
        description="Отправлено предупреждений клиентам у оператора (10 мин)",
    )
    operator_tickets_closed: int = Field(
        0, description="Закрыто тикетов операторов по неактивности (15 мин)"
    )
    operators_marked_offline: int = Field(
        0,
        description="Переведено операторов в offline из-за обрыва связи (>10 мин)",
    )
    tickets_requeued: int = Field(
        0, description="Возвращено тикетов в очередь линии"
    )
    tickets_sent_to_audit: int = Field(
        0,
        description="Отправлено тикетов на аудит качества без отзыва (10 мин)",
    )
    affected_line_codes: list[str] = Field(
        default_factory=list, description="Список затронутых линий поддержки"
    )


class DispatchPayloadSchema(BaseModel):
    """Полезная нагрузка фоновой задачи распределения обращений линии."""

    model_config = ConfigDict(from_attributes=True)

    line_code: str = Field(
        ...,
        description="Системный код линии поддержки (L1, L2, L3)",
        examples=["L1"],
    )
    trigger_reason: DispatchTriggerReason = Field(
        default="ticket_escalated",
        description="Причина запуска: ticket_escalated, slot_freed, shift_resumed, scheduled_sync, operator_disconnected, inactivity_timeout",
        examples=["ticket_escalated"],
    )


@dataclass
class DispatchResult:
    """Результат выполнения цикла распределения очереди линии."""

    line_code: str
    assigned_count: int
    assigned_ticket_ids: list[UUID]
    stop_reason: Literal[
        "queue_empty",
        "no_operators",
        "lock_busy",
        "line_not_found",
    ]


# Псевдонимы схем сайдбара
OperatorSidebarTicketSchema = TicketAssignedDataSchema


# ==============================================================================
# Схемы рабочего места оператора и управления сменой (API v1 §4)
# ==============================================================================


class OperatorShiftStatusUpdateSchema(BaseModel):
    """Схема запроса обновления статуса смены оператора."""

    shift_status: Literal["active", "break", "offline"] = Field(
        ...,
        description="Новый статус смены: active, break, offline",
        examples=["active"],
    )


class OperatorProfileResponseSchema(BaseModel):
    """Схема профиля оператора со статистикой занятых слотов."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(..., description="Идентификатор оператора")
    full_name: str = Field(..., description="ФИО специалиста")
    line_id: int = Field(..., description="Идентификатор закрепленной линии")
    line_code: str = Field(..., description="Код линии: L1, L2, L3")
    shift_status: str = Field(
        ..., description="Статус смены: active, break, offline"
    )
    max_slots: int = Field(
        ..., description="Максимальное количество одновременных диалогов"
    )
    active_slots_count: int = Field(
        ..., description="Число занятых слотов в данный момент"
    )


class ClientInfoSchema(BaseModel):
    """Схема контактных данных и реквизитов организации клиента."""

    model_config = ConfigDict(from_attributes=True)

    company_name: str | None = Field(
        None, description="Наименование организации"
    )
    inn: str | None = Field(None, description="ИНН")
    kpp: str | None = Field(None, description="КПП")
    phone: str | None = Field(None, description="Телефон")
    full_name: str | None = Field(None, description="ФИО контактного лица")
    email: str = Field(..., description="Электронная почта")


class SimilarTicketItemSchema(BaseModel):
    """Схема похожего закрытого обращения из базы прецедентов."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: str = Field(
        ..., description="Идентификатор закрытого обращения"
    )
    support_line: str = Field(..., description="Линия поддержки")
    user_query: str = Field(..., description="Вопрос клиента")
    solution_text: str = Field(
        ..., description="Текст предоставленного решения"
    )
    similarity_score: float = Field(
        ..., description="Степень семантической близости"
    )


class CopilotSummaryResponseSchema(BaseModel):
    """Схема подсказки языковой модели при открытии тикета."""

    model_config = ConfigDict(from_attributes=True)

    summary: str = Field(..., description="Краткая суть проблемы клиента")
    suggested_line_code: str | None = Field(
        None, description="Рекомендованная линия поддержки"
    )
    suggested_response: str | None = Field(
        None, description="Черновик ответа для оператора"
    )
    recommended_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Идентификаторы нормативных статей",
    )
    similar_resolved_tickets: list[SimilarTicketItemSchema] = Field(
        default_factory=list,
        description="Похожие закрытые обращения из базы прецедентов Qdrant",
    )


from src.chat.schemas import MessageResponseSchema  # noqa: E402


class OperatorTicketWorkspaceSchema(BaseModel):
    """Схема полного рабочего контекста тикета для рабочего места оператора."""

    model_config = ConfigDict(from_attributes=True)

    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    chat_id: UUID = Field(..., description="Идентификатор чата")
    priority: Literal["P0", "P1", "P2"] = Field(
        default="P2",
        description="Приоритет обращения: P0, P1, P2",
        examples=["P1"],
    )
    status: str = Field(..., description="Текущий статус обращения")
    line_code: str = Field(..., description="Код линии")
    transfer_comment: str | None = Field(
        None,
        description="Комментарий предыдущего специалиста при переводе",
    )
    client: ClientInfoSchema = Field(
        ..., description="Реквизиты и контакты организации"
    )
    copilot_summary: CopilotSummaryResponseSchema | None = Field(
        None,
        description="Подсказка языковой модели (при готовности)",
    )
    messages: list[MessageResponseSchema] = Field(
        ..., description="Полная история переписки чата"
    )


class OperatorSendMessageRequestSchema(BaseModel):
    """Схема запроса отправки текстового ответа клиенту оператором."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Текст ответа клиенту",
        examples=[
            "Протокол разногласий формируется в личном кабинете в разделе «Мои закупки»."
        ],
    )


class TransferTicketRequestSchema(BaseModel):
    """Схема запроса перевода обращения на другую линию поддержки."""

    target_line_code: str = Field(
        ...,
        description="Код целевой линии: L1, L2, L3",
        examples=["L2"],
    )
    transfer_comment: str | None = Field(
        None,
        description="Пояснение причины перевода",
        examples=["Требуется проверка криптографического плагина"],
    )


class TransferTicketResponseSchema(BaseModel):
    """Схема ответа при переводе обращения на другую линию."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        default="queued", description="Новый статус обращения в очереди"
    )
    ticket_id: UUID = Field(
        ..., description="Идентификатор переведенного обращения"
    )
    line_code: str = Field(
        ..., description="Код линии, на которую переведен тикет"
    )


class ResolveTicketResponseSchema(BaseModel):
    """Схема ответа при успешном завершении обращения оператором."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        default="resolved", description="Статус завершенного обращения"
    )
    ticket_id: UUID = Field(
        ..., description="Идентификатор завершенного обращения"
    )
    closed_at: datetime = Field(
        ..., description="Метка времени завершения диалога"
    )
