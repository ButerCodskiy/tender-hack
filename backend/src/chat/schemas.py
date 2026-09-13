"""Схемы валидации данных домена chat."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClientSendMessageRequestSchema(BaseModel):
    """Схема входящего сообщения от клиента."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Текст сообщения клиента",
        examples=[
            "Как подписать протокол разногласий по котировочной сессии?"
        ],
    )
    ticket_id: UUID | None = Field(
        default=None,
        description="Идентификатор обращения, к которому относится реплика",
        examples=["018e5f1b-3a21-729d-9e5c-29b1f0c23b11"],
    )
    new_ticket: bool = Field(
        default=False,
        description="Признак принудительного создания новой сессии обращения",
        examples=[False],
    )

    @field_validator("ticket_id", mode="before")
    @classmethod
    def validate_ticket_id(cls, value: Any) -> UUID | None:
        """Мягко сбрасывает псевдо-идентификаторы сессий фронтенда (session-*)."""
        if not value:
            return None
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            try:
                return UUID(value)
            except (ValueError, AttributeError):
                return None
        return None

    @field_validator("text")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        """Проверяет, что сообщение не состоит исключительно из пробелов."""
        if not value.strip():
            raise ValueError(
                "Сообщение не может быть пустым или состоять только из пробелов"
            )
        return value


class MessageSourceResponseSchema(BaseModel):
    """Схема ссылки на источник регламента базы знаний в сообщении."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str = Field(
        ...,
        description="Идентификатор фрагмента базы знаний",
        examples=["chunk_portal_zakupki_reglament_sec4_p1"],
    )
    doc_id: str = Field(
        ...,
        description="Идентификатор документа регламента",
        examples=["DOC_PORTAL_REGULATION_V6"],
    )
    quote_text: str | None = Field(
        default=None,
        description="Цитируемый фрагмент текста регламента",
        examples=[
            "Участник закупки вправе сформировать и подписать протокол разногласий..."
        ],
    )


class MessageResponseSchema(BaseModel):
    """Схема реплики переписки чата со статусом модерации и источниками."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Уникальный идентификатор сообщения",
    )
    ticket_id: UUID = Field(
        ...,
        description="Идентификатор обращения, к которому привязана реплика",
    )
    sender_type: str = Field(
        default="bot",
        description="Тип отправителя: client, bot, operator, system",
        examples=["bot"],
    )
    sender_id: UUID | None = Field(
        default=None,
        description="Идентификатор пользователя-автора сообщения",
    )
    sender_name: str | None = Field(
        default=None,
        description="Отображаемое имя автора сообщения (оператора, админа или клиента)",
        examples=["Анна Смирнова"],
    )
    sender_role: str | None = Field(
        default=None,
        description="Системная роль автора сообщения: client, operator, supervisor, admin",
        examples=["operator"],
    )
    text: str = Field(
        ...,
        description="Текст сообщения",
        examples=["Согласно регламенту Портала поставщиков Москвы..."],
    )
    moderation_status: str = Field(
        default="passed",
        description="Статус модерации: passed, flagged, blocked",
        examples=["passed"],
    )
    moderation_reason: str | None = Field(
        default=None,
        description="Причина решения модерации (например, profanity)",
        examples=["profanity"],
    )
    ticket_status: str | None = Field(
        default=None,
        description="Статус обращения, к которому привязана реплика",
        examples=["closed_by_moderation"],
    )
    sources: list[MessageSourceResponseSchema] = Field(
        default_factory=list,
        description="Источники ответа из нормативной базы знаний",
    )
    created_at: datetime = Field(
        ...,
        description="Метка времени фиксации сообщения",
    )


class ActiveTicketSummarySchema(BaseModel):
    """Краткая сводка активного обращения клиента."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Идентификатор активного обращения",
    )
    priority: Literal["P0", "P1", "P2"] = Field(
        default="P2",
        description="Приоритет обращения: P0, P1, P2",
        examples=["P2"],
    )
    status: str = Field(
        ...,
        description="Статус обращения",
        examples=["in_progress"],
    )
    line_code: str | None = Field(
        default=None,
        description="Код закрепленной линии: L1, L2, L3",
        examples=["L1"],
    )
    assigned_operator_name: str | None = Field(
        default=None,
        description="Имя подключенного специалиста",
        examples=["Анна Смирнова"],
    )
    created_at: datetime = Field(
        ...,
        description="Время открытия обращения",
    )


class ChatStateResponseSchema(BaseModel):
    """Полное текущее состояние переписки клиента и история сообщений."""

    model_config = ConfigDict(from_attributes=True)

    chat_id: UUID = Field(
        ...,
        description="Идентификатор постоянного чата клиента",
    )
    active_ticket: ActiveTicketSummarySchema | None = Field(
        default=None,
        description="Активное обращение или null",
    )
    messages: list[MessageResponseSchema] = Field(
        default_factory=list,
        description="Сообщения ленты (до 50 последних)",
    )
    can_escalate: bool = Field(
        ...,
        description="Доступна ли кнопка вызова оператора",
    )
    can_cancel: bool = Field(
        ...,
        description="Доступна ли отмена обращения",
    )
    can_feedback: bool = Field(
        ...,
        description="Требуется ли оценка последнего закрытого обращения",
    )
    feedback_ticket_id: UUID | None = Field(
        default=None,
        description="Идентификатор тикета, ожидающего оценки",
    )


class EscalateRequestSchema(BaseModel):
    """Схема запроса эскалации обращения на оператора."""

    reason: str | None = Field(
        default="client_requested",
        description="Причина вызова оператора",
        examples=["Сложный нестандартный случай"],
    )


class ClientResolveTicketResponseSchema(BaseModel):
    """Схема ответа подтверждения решения вопроса клиентом."""

    status: str = Field(default="resolved", description="Статус обращения")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    closed_at: datetime = Field(..., description="Время закрытия обращения")


class CancelTicketResponseSchema(BaseModel):
    """Схема ответа отмены обращения клиентом."""

    status: str = Field(default="canceled", description="Статус обращения")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
