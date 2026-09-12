"""Схемы валидации данных домена rag."""

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RagQueryRequestSchema(BaseModel):
    """Схема входящего запроса к поисковому и генеративному конвейеру."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Текст вопроса пользователя",
        examples=[
            "Как подписать протокол разногласий на Портале поставщиков?"
        ],
    )
    message_id: UUID | None = Field(
        default=None,
        description="Идентификатор сообщения диалога для сквозной трассировки и события done",
        examples=["018e5f1b-3a21-729d-9e5c-29b1f0c23b20"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Максимальное количество извлекаемых фрагментов базы знаний",
        examples=[5],
    )
    conversation_history: list[dict[str, str]] | None = Field(
        default=None,
        description="Контекст предыдущих реплик диалога",
        examples=[
            [
                {"role": "user", "text": "Здравствуйте"},
                {"role": "bot", "text": "Добрый день!"},
            ]
        ],
    )


class RagSourceChunkSchema(BaseModel):
    """Схема найденного фрагмента базы знаний, подтверждающего ответ."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str = Field(
        ...,
        description="Уникальный идентификатор фрагмента в базе знаний",
        examples=["chunk_mos_portal_reglament_p4_1"],
    )
    doc_id: str = Field(
        ...,
        description="Идентификатор исходного документа регламента",
        examples=["DOC_REGLAMENT_ZAKUPKI_MOS"],
    )
    title: str | None = Field(
        default=None,
        description="Заголовок раздела или статьи",
        examples=["Раздел 4. Порядок подписания протоколов"],
    )
    quote_text: str | None = Field(
        default=None,
        description="Цитата нормативного текста или методички",
        examples=[
            "Подписание протокола разногласий осуществляется в личном кабинете с помощью ЭЦП."
        ],
    )
    section_path: str | None = Field(
        default=None,
        description="Структурный путь внутри документа (Раздел > Статья)",
        examples=["Раздел 4. Порядок подписания протоколов"],
    )
    source_url: str | None = Field(
        default=None,
        description="Ссылка на нормативный правовой акт или регламент",
        examples=["https://zakupki.mos.ru/regulations/p4"],
    )
    relevance_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Оценка релевантности фрагмента поисковым реранкером",
        examples=[0.94],
    )
    pin_to_top: bool = Field(
        default=False,
        description="Флаг приоритетного закрепления нормативной статьи в топ-1 выдачи",
    )

    @property
    def score(self) -> float:
        """Псевдоним для relevance_score."""
        return (
            self.relevance_score if self.relevance_score is not None else 0.0
        )

    @property
    def text(self) -> str:
        """Псевдоним для quote_text."""
        return self.quote_text or ""


# Изолированный интерфейс фрагмента контекста для генератора (HIGH-01 <-> HIGH-03)
ContextChunk = RagSourceChunkSchema


class RagResponseSchema(BaseModel):
    """Схема ответа генеративного конвейера RAG."""

    model_config = ConfigDict(from_attributes=True)

    answer: str = Field(
        ...,
        description="Сгенерированный текст ответа пользователю со сносками",
        examples=[
            "Для подписания протокола разногласий перейдите в раздел котировочных сессий [^1]."
        ],
    )
    sources: list[RagSourceChunkSchema] = Field(
        default_factory=list,
        description="Список фрагментов нормативной базы, использованных для ответа",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Уверенность модели в ответе",
        examples=[0.95],
    )
    verified: bool = Field(
        default=True,
        description="Признак успешной верификации числовых и фактологических утверждений",
        examples=[True],
    )


class RagStatusEventSchema(BaseModel):
    """Событие промежуточного статуса обработки поискового конвейера."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["status"] = "status"
    code: Literal["classifying", "searching", "reranking"] = Field(
        ...,
        description="Код этапа размышления конвейера",
        examples=["searching"],
    )
    message: str = Field(
        ...,
        description="Пользовательское описание текущего действия",
        examples=["Идет поиск по нормативным регламентам..."],
    )


class RagSourcesEventSchema(BaseModel):
    """Событие передачи найденных источников базы знаний."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["sources"] = "sources"
    sources: list[RagSourceChunkSchema] = Field(
        default_factory=list,
        description="Список найденных фрагментов базы знаний",
    )


class RagSentenceEventSchema(BaseModel):
    """Событие генерации очередного предложения с инлайн-валидацией."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["sentence"] = "sentence"
    sentence_idx: int = Field(
        ...,
        ge=0,
        description="Порядковый индекс предложения в ответе (начиная с 0)",
        examples=[0],
    )
    text: str = Field(
        ...,
        description="Текст законченного предложения со сносками",
        examples=[
            "Согласно статье 44 Федерального закона № 44-ФЗ размер обеспечения заявки составляет 1% [^1]."
        ],
    )
    verified: bool = Field(
        default=True,
        description="Инлайн-флаг фактологической верификации числовых и фактологических слотов",
        examples=[True],
    )


class RagDoneEventSchema(BaseModel):
    """Финальное событие завершения потока генерации ответа."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["done"] = "done"
    message_id: UUID | None = Field(
        default=None,
        description="Идентификатор сохраненного сообщения",
        examples=["018e5f1b-3a21-729d-9e5c-29b1f0c23b20"],
    )
    ticket_id: UUID | None = Field(
        default=None,
        description="Идентификатор обращения",
        examples=["018e5f1b-3a21-729d-9e5c-29b1f0c23b21"],
    )
    text: str = Field(
        ...,
        description="Полный итоговый текст ответа",
        examples=[
            "По вашему вопросу: в соответствии с регламентом Портала поставщиков Москвы..."
        ],
    )
    all_verified: bool = Field(
        default=True,
        description="Агрегированный признак верификации всех утверждений ответа",
        examples=[True],
    )


class RagDegradedModeEventSchema(BaseModel):
    """Событие деградации при сбое генератора или таймауте модели."""

    model_config = ConfigDict(from_attributes=True)

    event: Literal["degraded_mode"] = "degraded_mode"
    message: str = Field(
        ...,
        description="Пользовательское пояснение о переходе в режим деградации",
        examples=[
            "Генеративная модель временно недоступна. Ниже представлены найденные нормативные источники."
        ],
    )
    sources: list[RagSourceChunkSchema] = Field(
        default_factory=list,
        description="Список найденных первоисточников для ручного изучения",
    )
    ticket_id: UUID | None = Field(
        default=None,
        description="Идентификатор связанного обращения",
    )
    message_id: UUID | None = Field(
        default=None,
        description="Идентификатор сообщения бота",
    )


RagStreamEvent = Annotated[
    RagStatusEventSchema
    | RagSourcesEventSchema
    | RagSentenceEventSchema
    | RagDoneEventSchema
    | RagDegradedModeEventSchema,
    Field(discriminator="event"),
]


class EntityItem(BaseModel):
    """Сущность, извлеченная из запроса пользователя."""

    model_config = ConfigDict(from_attributes=True)

    type: Literal["article", "law", "service", "error_code"] = Field(
        ...,
        description="Тип нормативной или технической сущности",
    )
    doc: Literal["44-FZ", "223-FZ", "MOS_PORTAL"] | None = Field(
        default=None,
        description="Правовой режим или документ регламента",
    )
    number: str | None = Field(
        default=None,
        description="Номер статьи, пункта или код ошибки",
    )
    part: str | None = Field(
        default=None,
        description="Номер части или подраздела",
    )


class QueryRouterOutput(BaseModel):
    """Схема структурированного результата классификации и маршрутизации запроса."""

    model_config = ConfigDict(from_attributes=True)

    intent: Literal[
        "qa",
        "article_lookup",
        "procedural",
        "chitchat",
        "out_of_domain",
    ] = Field(
        ...,
        description="Коммуникативное намерение пользователя",
    )
    regime_hint: Literal["44-FZ", "223-FZ", "MOS_PORTAL"] | None = Field(
        default=None,
        description="Рекомендуемый правовой режим или источник регламента",
    )
    topic: Literal[
        "digital_signature_plugin",
        "technical_errors",
        "api_integration",
        "browser_compatibility",
        "payment_delays",
        "account_blocking",
        "complaints_fas",
        "contract_disputes",
        "registration_portal",
        "catalog_navigation",
        "quote_sessions_rules",
        "general_faq",
        "contract_conclusion",
        "closing_documents",
        "tender_cancellation",
        "bid_security",
        "contract_security",
        "delivery_acceptance",
        "electronic_store",
        "other",
    ] = Field(
        ...,
        description="Тематическая категория обращения по таксономии портала",
    )
    priority: Literal["P0", "P1", "P2"] = Field(
        ...,
        description="Приоритет обращения по регламенту времени первого ответа",
    )
    support_line: Literal["L1", "L2", "L3"] = Field(
        ...,
        description="Линия технической или экспертной поддержки",
    )
    sentiment: Literal["neutral", "frustrated", "aggressive"] = Field(
        ...,
        description="Эмоциональная тональность сообщения пользователя",
    )
    follow_up_type: Literal["none", "clarification", "repeat", "new_topic"] = (
        Field(
            ...,
            description="Связь реплики с предшествующим контекстом диалога",
        )
    )
    error_codes: list[str] = Field(
        default_factory=list,
        description="Извлеченные шестнадцатеричные коды системных ошибок",
    )
    escalation_requested: bool = Field(
        default=False,
        description="Флаг явного запроса перевода на оператора-человека",
    )
    entities: list[EntityItem] = Field(
        default_factory=list,
        description="Список выявленных нормативных, сервисных или технических сущностей",
    )
    standalone_query: str = Field(
        ...,
        description="Автономный нормализованный поисковый запрос с разрешением анафоры",
    )
    sub_queries: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Декомпозированные поисковые подзапросы для составных обращений",
    )

    @field_validator("sub_queries", mode="before")
    @classmethod
    def truncate_sub_queries(cls, v: Any) -> Any:
        """Обрезает список подзапросов до 3 элементов для исключения ошибок валидации."""
        if isinstance(v, list):
            return v[:3]
        return v


class CopilotPayloadSchema(BaseModel):
    """Схема полезной нагрузки для фоновой задачи очереди copilot_queue."""

    ticket_id: UUID = Field(
        ...,
        description="Уникальный идентификатор обращения",
        examples=["6a1c5b8e-3d2f-4a1b-9c8e-7f6e5d4c3b2a"],
    )


class CopilotLlmOutputSchema(BaseModel):
    """Структурированный результат генерации языковой модели для Copilot."""

    summary: str = Field(
        ...,
        description="Краткая суть проблемы клиента (1-2 предложения)",
        examples=[
            "Клиент не может подписать протокол разногласий из-за ошибки плагина ЭЦП."
        ],
    )
    suggested_line_code: Literal["L1", "L2", "L3"] = Field(
        default="L1",
        description="Рекомендованная линия поддержки",
        examples=["L2"],
    )
    suggested_response: str = Field(
        ...,
        description="Готовый черновик ответа для оператора со ссылкой на инструкцию",
        examples=[
            "Здравствуйте! Для устранения ошибки обновите плагин КриптоПро ЭЦП Browser plug-in."
        ],
    )
    recommended_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Идентификаторы релевантных статей нормативной базы знаний",
        examples=[["chunk_portal_zakupki_reglament_sec4_p1"]],
    )
