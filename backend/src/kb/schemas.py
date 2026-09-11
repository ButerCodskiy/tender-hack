"""
Pydantic v2 схемы данных для конвейера парсинга нормативных документов (Docling + PyMuPDF).
Согласованы со спецификацией базы данных (kb_documents, kb_nodes, kb_chunks)
и правилами проекта (.agents/rules/code-rules.md).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NodeLevel = Literal["document", "section", "article", "part", "item"]
DocumentStatus = Literal[
    "uploaded", "indexing", "indexed", "failed", "deprecated"
]


class ParsedDocumentSchema(BaseModel):
    """Схема метаданных документа базы знаний (таблица kb_documents)."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(
        ..., description="Уникальный идентификатор документа (UUID или хэш)"
    )
    title: str = Field(..., description="Название регламента или методички")
    regime: str = Field(
        default="MOS_PORTAL", description="Правовой или функциональный режим"
    )
    edition_date: date | None = Field(
        default=None, description="Дата редакции документа"
    )
    status: DocumentStatus = Field(
        default="uploaded", description="Статус обработки документа"
    )
    error_message: str | None = Field(
        default=None, description="Текст ошибки при сбое"
    )
    source_url: str | None = Field(
        default=None, description="URL источника документа"
    )
    is_scanned: bool = Field(
        default=False,
        description="Признак сканированного документа без текстового слоя",
    )
    page_count: int = Field(
        default=1,
        exclude=True,
        description="Количество страниц в документе (исключено из DDL kb_documents)",
    )


class ParsedNodeSchema(BaseModel):
    """Схема иерархического узла структуры документа (таблица kb_nodes)."""

    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Уникальный идентификатор узла AST")
    doc_id: str = Field(
        ..., description="Идентификатор родительского документа kb_documents"
    )
    parent_node_id: str | None = Field(
        default=None, description="Идентификатор родительского узла kb_nodes"
    )
    level: NodeLevel = Field(
        ..., description="Уровень вложенности в иерархии документа"
    )
    section_path: str = Field(
        ..., description="Хлебные крошки иерархии разделов"
    )
    article_no: str | None = Field(
        default=None, description="Номер статьи нормативного акта"
    )
    part_no: str | None = Field(
        default=None, description="Номер части или пункта статьи"
    )
    title: str = Field(..., description="Заголовок узла")
    full_content: str = Field(..., description="Полный текст узла")
    table_md: str | None = Field(
        default=None,
        description="Оригинальная сетка таблицы в формате Markdown",
    )
    token_count: int = Field(
        default=0, description="Количество токенов в полном тексте узла"
    )


class ParsedChunkSchema(BaseModel):
    """
    Схема поискового чанка документа (таблица kb_chunks).
    Поле token_count помечено exclude=True, так как в DDL таблицы kb_chunks его нет.
    Поле has_table предназначено для фильтрации в Qdrant payload.
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str = Field(..., description="Уникальный идентификатор чанка")
    node_id: str = Field(..., description="Идентификатор узла kb_nodes")
    text: str = Field(
        ..., description="Текст фрагмента для векторного поиска и контекста"
    )
    context_prefix: str | None = Field(
        default=None, description="Контекстуализирующий префикс от LLM"
    )
    hyp_questions: list[str] = Field(
        default_factory=list, description="Гипотетические вопросы (HyPE)"
    )
    embedding_model_version: str = Field(
        default="bge-m3", description="Версия модели эмбеддингов"
    )
    has_table: bool = Field(
        default=False,
        description="Признак наличия табличных данных для payload Qdrant",
    )
    token_count: int = Field(
        default=0,
        exclude=True,
        description="Служебное число токенов (исключено из DDL kb_chunks)",
    )


class CompletenessReportSchema(BaseModel):
    """Отчет о результатах контроля полноты извлечения текста (PyMuPDF vs Docling)."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Идентификатор документа")
    pymupdf_char_count: int = Field(
        ..., description="Число символов печатного слоя (PyMuPDF)"
    )
    docling_char_count: int = Field(
        ..., description="Число символов, извлеченных Docling"
    )
    discrepancy_ratio: float = Field(
        ..., description="Относительное расхождение объемов символов"
    )
    is_scanned: bool = Field(
        default=False, description="Признак графического скана"
    )
    needs_manual_review: bool = Field(
        default=False,
        description="Флаг необходимости ручной проверки (дельта > 5%)",
    )
    details: str = Field(default="", description="Пояснения к отчету")


class StageTimingSchema(BaseModel):
    """Метрики замера времени для отдельного этапа конвейера."""

    model_config = ConfigDict(from_attributes=True)

    stage_name: str = Field(..., description="Название этапа конвейера")
    duration_sec: float = Field(
        ..., description="Длительность этапа в секундах"
    )
    percentage: float = Field(
        ..., description="Доля времени от общего цикла (в %)"
    )


class DocumentProfilingMetricsSchema(BaseModel):
    """Сводные метрики профилирования обработки отдельного документа."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Идентификатор документа")
    page_count: int = Field(..., description="Количество обработанных страниц")
    token_count: int = Field(
        ..., description="Суммарное количество токенов в чанках"
    )
    total_duration_sec: float = Field(
        ..., description="Общее время обработки документа в секундах"
    )
    pages_per_sec: float = Field(
        ..., description="Скорость обработки страниц (pages/sec)"
    )
    tokens_per_sec: float = Field(
        ..., description="Скорость обработки токенов (tokens/sec)"
    )
    ram_start_mb: float = Field(
        ..., description="Потребление RAM (RSS) на старте (МБ)"
    )
    ram_peak_mb: float = Field(
        ..., description="Пиковое потребление RAM (RSS) в процессе (МБ)"
    )
    ram_delta_mb: float = Field(
        ..., description="Дельта потребления RAM за время обработки (МБ)"
    )
    vram_allocated_mb: str | float = Field(
        ..., description="Выделенная видеопамять VRAM (МБ) или 'CPU-only'"
    )
    device: str = Field(
        default="cpu", description="Используемое устройство (cpu или cuda)"
    )
    stages: dict[str, StageTimingSchema] = Field(
        default_factory=dict, description="Замеры длительностей по этапам"
    )


class BatchProfilingReportSchema(BaseModel):
    """Агрегированный отчет профилирования по пакету документов."""

    model_config = ConfigDict(from_attributes=True)

    total_documents: int = Field(
        ..., description="Всего обработано документов"
    )
    total_pages: int = Field(..., description="Всего страниц")
    total_tokens: int = Field(..., description="Всего токенов")
    total_duration_sec: float = Field(
        ..., description="Общее время работы батча (с)"
    )
    avg_pages_per_sec: float = Field(
        ..., description="Средняя скорость по страницам"
    )
    avg_tokens_per_sec: float = Field(
        ..., description="Средняя скорость по токенам"
    )
    max_ram_rss_mb: float = Field(
        ..., description="Максимальное пиковое потребление RAM (МБ)"
    )
    vram_info: str = Field(
        ..., description="Информация о VRAM GPU или CPU-only"
    )
    device: str = Field(..., description="Основное вычислительное устройство")
    documents: list[DocumentProfilingMetricsSchema] = Field(
        default_factory=list, description="Метрики по каждому документу"
    )


class ParsedExtractionResultSchema(BaseModel):
    """Полный результат разбора документа для сохранения или фоновой индексации."""

    model_config = ConfigDict(from_attributes=True)

    document: ParsedDocumentSchema = Field(
        ..., description="Метаданные родительского документа"
    )
    nodes: list[ParsedNodeSchema] = Field(
        default_factory=list, description="Список иерархических узлов AST"
    )
    chunks: list[ParsedChunkSchema] = Field(
        default_factory=list, description="Список поисковых чанков"
    )
    completeness_report: CompletenessReportSchema = Field(
        ..., description="Отчет контроля полноты"
    )
    profiling: DocumentProfilingMetricsSchema | None = Field(
        default=None, description="Метрики профилирования документа"
    )


class DocumentUploadItemResponseSchema(BaseModel):
    """Схема ответа при загрузке документа в базу знаний."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(
        ..., description="Уникальный идентификатор принятого документа"
    )
    title: str = Field(..., description="Исходное имя файла документа")
    status: DocumentStatus = Field(
        default="uploaded", description="Текущий статус обработки"
    )
    message: str = Field(
        default="Документ принят в очередь на разбор и индексацию",
        description="Информационное сообщение",
    )


class FaqImportItemSchema(BaseModel):
    """Схема отдельной валидированной вопросно-ответной пары FAQ."""

    model_config = ConfigDict(from_attributes=True)

    row_idx: int = Field(
        ..., description="Порядковый номер строки в исходной таблице"
    )
    question: str = Field(..., description="Очищенный текст вопроса")
    answer: str = Field(..., description="Эталонный текст ответа")
    chunk_id: str = Field(
        ..., description="Идентификатор сформированного чанка"
    )


class FaqImportResultSchema(BaseModel):
    """Схема итогового отчета о пакетном импорте таблицы FAQ."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(
        ..., description="Идентификатор синтетического документа"
    )
    node_id: str = Field(
        ..., description="Идентификатор синтетического родительского узла"
    )
    filename: str = Field(
        ..., description="Исходное имя импортированного файла"
    )
    total_rows: int = Field(
        ..., description="Общее число прочитанных строк таблицы"
    )
    imported_count: int = Field(
        ...,
        description="Число успешно импортированных и проиндексированных пар",
    )
    skipped_count: int = Field(
        ..., description="Число пропущенных пустых или некорректных строк"
    )
    status: DocumentStatus = Field(
        default="indexed", description="Статус синтетического документа"
    )


class KbDocumentResponse(BaseModel):
    """Схема документа в реестре базы знаний."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Уникальный идентификатор документа")
    title: str = Field(..., description="Название документа")
    regime: str | None = Field(
        default="MOS_PORTAL", description="Правовой или функциональный режим"
    )
    edition_date: date | None = Field(
        default=None, description="Дата редакции документа"
    )
    status: DocumentStatus = Field(..., description="Текущий статус обработки")
    error_message: str | None = Field(
        default=None, description="Текст ошибки при сбое"
    )
    source_url: str | None = Field(
        default=None, description="URL или путь к источнику документа"
    )
    created_at: datetime = Field(..., description="Дата и время создания")
    updated_at: datetime = Field(
        ..., description="Дата и время последнего обновления"
    )


class KbDocumentListResponse(BaseModel):
    """Схема ответа со списком документов и метаданными пагинации."""

    model_config = ConfigDict(from_attributes=True)

    items: list[KbDocumentResponse] = Field(
        ..., description="Список документов"
    )
    total: int = Field(
        ...,
        description="Общее количество документов, удовлетворяющих фильтру",
    )
    limit: int = Field(..., description="Количество элементов на странице")
    offset: int = Field(..., description="Смещение выборки")


class KbDocumentStatusResponse(BaseModel):
    """Схема статуса индексации документа."""

    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Уникальный идентификатор документа")
    status: DocumentStatus = Field(..., description="Текущий статус обработки")
    error_message: str | None = Field(
        default=None, description="Текст ошибки при сбое"
    )
    chunks_count: int = Field(
        ..., description="Количество связанных поисковых чанков"
    )
    updated_at: datetime = Field(
        ..., description="Дата и время последнего обновления"
    )


class KbDocumentDeleteResponse(BaseModel):
    """Схема ответа при удалении документа из базы знаний."""

    model_config = ConfigDict(from_attributes=True)

    deleted: bool = Field(
        default=True, description="Признак успешного удаления"
    )
    doc_id: str = Field(..., description="Идентификатор удаленного документа")


class KbNodeUpdateRequest(BaseModel):
    """Схема запроса на точечное обновление метаданных узла документа."""

    model_config = ConfigDict(from_attributes=True)

    title: str | None = Field(
        default=None, min_length=1, description="Новый заголовок узла"
    )
    section_path: str | None = Field(
        default=None,
        min_length=1,
        description="Новые хлебные крошки иерархии разделов",
    )


class KbNodeResponse(BaseModel):
    """Схема структурного узла документа после обновления."""

    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Уникальный идентификатор узла AST")
    doc_id: str = Field(
        ..., description="Идентификатор родительского документа"
    )
    parent_node_id: str | None = Field(
        default=None, description="Идентификатор родительского узла"
    )
    level: NodeLevel = Field(
        ..., description="Уровень вложенности в иерархии документа"
    )
    section_path: str = Field(
        ..., description="Хлебные крошки иерархии разделов"
    )
    article_no: str | None = Field(
        default=None, description="Номер статьи нормативного акта"
    )
    part_no: str | None = Field(
        default=None, description="Номер части или пункта статьи"
    )
    title: str = Field(..., description="Заголовок узла")
    full_content: str = Field(..., description="Полный текст узла")
    table_md: str | None = Field(
        default=None, description="Сетка таблицы в формате Markdown"
    )
    token_count: int = Field(
        default=0, description="Количество токенов в полном тексте узла"
    )
    created_at: datetime = Field(..., description="Дата и время создания узла")


# ────────────────────────────────────────────────────────────────
# MED-05 — Контур самообучения (FAQ-черновики, модерация)
# ────────────────────────────────────────────────────────────────

FaqDraftStatus = Literal["PENDING", "APPROVED", "REJECTED"]
FaqKind = Literal["normative", "procedural"]


class FaqDraftResponse(BaseModel):
    """Схема черновика FAQ из очереди модерации."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Уникальный идентификатор черновика")
    ticket_id: str = Field(..., description="Идентификатор тикета-источника")
    question: str = Field(..., description="Текст извлечённого вопроса")
    answer: str = Field(..., description="Текст эталонного ответа")
    kind: FaqKind = Field(default="procedural", description="Тип FAQ-записи")
    valid_until: date | None = Field(
        default=None, description="Срок актуальности записи"
    )
    linked_regulation_chunk_id: str | None = Field(
        default=None,
        description="ID связанного регламентного чанка kb_chunks",
    )
    status: FaqDraftStatus = Field(
        default="PENDING", description="Статус модерации"
    )
    reviewer_id: str | None = Field(default=None, description="ID рецензента")
    created_at: datetime = Field(..., description="Дата создания черновика")
    reviewed_at: datetime | None = Field(
        default=None, description="Дата проведения ревью"
    )


class FaqDraftListResponse(BaseModel):
    """Пагинированный список черновиков FAQ."""

    model_config = ConfigDict(from_attributes=True)

    items: list[FaqDraftResponse] = Field(..., description="Черновики FAQ")
    total: int = Field(..., description="Всего черновиков по фильтру")
    limit: int = Field(..., description="Размер страницы")
    offset: int = Field(..., description="Смещение")


class FaqReviewRequest(BaseModel):
    """Запрос на ревью черновика FAQ супервизором."""

    action: Literal["approve", "reject"] = Field(
        ..., description="Решение: approve — принять в БЗ, reject — отклонить"
    )


class FaqReviewResponse(BaseModel):
    """Ответ после ревью черновика FAQ."""

    model_config = ConfigDict(from_attributes=True)

    draft_id: str = Field(
        ..., description="Идентификатор обработанного черновика"
    )
    status: FaqDraftStatus = Field(
        ..., description="Итоговый статус после ревью"
    )
    chunk_id: str | None = Field(
        default=None,
        description="ID созданного чанка (только при approve)",
    )
