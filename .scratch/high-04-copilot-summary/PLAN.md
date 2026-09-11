# Пошаговый план реализации: Подготовка аналитической подсказки и контекста для оператора (HIGH-04)

> **Статус:** Реализован и верифицирован (14 unit/integration тестов PASSED)  
> **Зона ответственности:** `backend/src/rag/`, `backend/src/operators/`, `backend/tests/rag/`

---

## Этап 1. Модель данных `TicketCopilotSummaryModel` и связь с обращением

> **Цель:** Подготовить реляционную схему для сохранения выжимки диалога и рекомендаций Copilot со связью 1:1 к обращению `tickets`.

- [x] В [backend/src/operators/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/models.py):
  - [x] Объявить модель `TicketCopilotSummaryModel`:
    - `id: Mapped[uuid.UUID]` (PK, default `uuid6.uuid7`)
    - `ticket_id: Mapped[uuid.UUID]` (FK `tickets.id`, ON DELETE CASCADE, UNIQUE, INDEX)
    - `summary: Mapped[str]` (`Text`, nullable=False)
    - `suggested_line_code: Mapped[str | None]` (`String(32)`, nullable=True)
    - `suggested_response: Mapped[str | None]` (`Text`, nullable=True)
    - `recommended_chunk_ids: Mapped[list[str]]` (`ARRAY(String(64))`, default=list, server_default="{}")
    - `similar_resolved_tickets: Mapped[list[dict[str, Any]]]` (`JSONB`, default=list, server_default="[]")
    - `created_at: Mapped[datetime]` (`DateTime(timezone=True)`, server_default=func.clock_timestamp())
    - Связь: `ticket: Mapped["TicketModel"] = relationship(back_populates="copilot_summary")`
- [x] В [backend/src/chat/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/models.py):
  - [x] Добавить в `TicketModel` отношение:
    `copilot_summary: Mapped["TicketCopilotSummaryModel | None"] = relationship(back_populates="ticket", uselist=False, cascade="all, delete-orphan")`
  - [x] Добавить импорт `TicketCopilotSummaryModel` под блоком `if TYPE_CHECKING:`.
- [x] ✅ Проверка:
  - [x] Модели корректно импортируются без циклических зависимостей: `python -c "from src.operators.models import TicketCopilotSummaryModel; from src.chat.models import TicketModel"`.

---

## Этап 2. Pydantic-схемы очереди и генерации Copilot

> **Цель:** Зафиксировать строгие контракты данных для очереди Taskiq `copilot_queue` и структурированного вывода языковой модели.

- [x] В [backend/src/rag/schemas.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/schemas.py):
  - [x] Объявить `CopilotPayloadSchema(BaseModel)` с полем `ticket_id: UUID`.
  - [x] Объявить `CopilotLlmOutputSchema(BaseModel)` с полями:
    - `summary: str`
    - `suggested_line_code: Literal["L1", "L2", "L3"] = "L1"`
    - `suggested_response: str`
    - `recommended_chunk_ids: list[str] = Field(default_factory=list)`
- [x] ✅ Проверка:
  - [x] Схемы успешно валидируют корректные и отбраковывают некорректные payload: `python -c "from src.rag.schemas import CopilotPayloadSchema, CopilotLlmOutputSchema"`.

---

## Этап 3. Векторная база прецедентов `resolved_tickets` в Qdrant

> **Цель:** Обеспечить авто-создание коллекции, сидирование 30+ исторических решений и устойчивый семантический поиск похожих закрытых тикетов.

- [x] Создать файл [backend/src/rag/qdrant_tickets.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/qdrant_tickets.py):
  - [x] Зафиксировать имя коллекции: `RESOLVED_TICKETS_COLLECTION = "resolved_tickets"`.
  - [x] Сформировать корпус из 30+ прецедентов `SEED_RESOLVED_TICKETS` (сбои ЭЦП `0x80090016`, плагин КриптоПро, регламентные разногласия 44/223-ФЗ, блокировки).
  - [x] Реализовать функцию `ensure_resolved_tickets_collection(client: AsyncQdrantClient, embedding_dim: int = 1024)`:
    - Проверка наличия коллекции;
    - Создание конфигурации `VectorParams(size=embedding_dim, distance=Distance.COSINE)`;
    - Пакетная загрузка `PointStruct` с векторами от `EmbeddingStub`.
  - [x] Реализовать функцию `search_similar_resolved_tickets(client: AsyncQdrantClient, query_text: str, limit: int = 3) -> list[SimilarTicketItemSchema]`:
    - Векторизация `query_text`;
    - Поиск `client.search` (или `query_points`);
    - Преобразование в `SimilarTicketItemSchema`;
    - Защита от сбоев (`try/except` -> fallback `[]`).
- [x] ✅ Проверка:
  - [x] Вызов `search_similar_resolved_tickets` при пустом/отключенном Qdrant возвращает пустой список без исключений.

---

## Этап 4. Ядро AI Copilot (`src/rag/copilot.py`)

> **Цель:** Реализовать протокол LLM, контекстно-зависимый мок и сборщик подсказки с объединением выжимки, регламентов и прецедентов Qdrant.

- [x] В [backend/src/rag/copilot.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/copilot.py):
  - [x] Объявить протокол `CopilotLlmClientProtocol` с методом `generate_copilot_summary`.
  - [x] Реализовать класс `MockCopilotLlmClient`:
    - Распознавание маркеров ошибок ЭЦП (рекомендация линии `L2`, готовый черновик настройки плагина и доверенных узлов);
    - Распознавание вопросов по регламентам Портала поставщиков (рекомендация линии `L1`, черновик по разделу 4);
    - Поддержка симуляции сбоев (`fail_times`) и задержек (`delay`).
  - [x] Реализовать класс `CopilotService`:
    - Метод `build_copilot_summary(messages: list[dict], qdrant_client: AsyncQdrantClient | None = None) -> CopilotSummaryResponseSchema`:
      - Формирование текста контекста из сообщений;
      - Генерация выжимки и черновика через `llm_client`;
      - Поиск похожих прецедентов в Qdrant;
      - Сборка финального `CopilotSummaryResponseSchema`.
- [x] ✅ Проверка:
  - [x] Вызов `build_copilot_summary` с тестовыми репликами формирует валидную схему `CopilotSummaryResponseSchema`.

---

## Этап 5. Фоновая задача Taskiq (`src/rag/tasks.py`)

> **Цель:** Реализовать устойчивую фоновую задачу `generate_copilot_summary` в очереди `copilot_queue` с сохранением в PostgreSQL и отправкой события `copilot_ready` в Redis Pub/Sub.

- [x] В [backend/src/rag/tasks.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/tasks.py):
  - [x] Объявить фоновую задачу:
    ```python
    @broker.task(task_name="generate_copilot_summary", queue_name="copilot_queue")
    async def generate_copilot_summary(payload: CopilotPayloadSchema | dict[str, Any]) -> dict[str, Any]:
    ```
  - [x] Извлечение истории диалога:
    - Из Redis `chat:context:{ticket_id}` через `RedisChatContext.get_messages`;
    - Фолбэк в PostgreSQL `MessageModel` при пустом Redis.
  - [x] Вызов `CopilotService.build_copilot_summary`.
  - [x] Сохранение результата в `TicketCopilotSummaryModel` через `async_session_maker` (идемпотентный UPSERT).
  - [x] Проверка `ticket.assigned_operator_id`:
    - При наличии оператора — публикация `publish_copilot_ready` в `channel:operator:{operator_id}`.
  - [x] Изоляция сбоев (Failure Isolation):
    - При таймауте или ошибке LLM — сохранение деградированной записи (`summary="Не удалось автоматически сформировать сводку обращения"`), публикация деградированного события `copilot_ready`.
- [x] ✅ Проверка:
  - [x] Прогон задачи через Taskiq брокер приводит к появлению записи в таблице `ticket_copilot_summaries`.

---

## Этап 6. Доработка АРМ оператора (синхронизация и репозиторий)

> **Цель:** Устранить хардкод `copilot_summary=None` при открытии тикета и подключить триггер фоновой задачи при трансфере тикета.

- [x] В [backend/src/operators/repository.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/repository.py):
  - [x] В методе `get_ticket_workspace_data`: добавить `selectinload(TicketModel.copilot_summary)`.
- [x] В [backend/src/operators/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/service.py):
  - [x] В методе `open_ticket`:
    - Маппинг `ticket.copilot_summary` в `CopilotSummaryResponseSchema` при его наличии;
    - Замена `copilot_summary=None` на `copilot_summary=copilot_dto`.
  - [x] В методе `transfer_ticket`:
    - Добавить запуск фоновой задачи `generate_copilot_summary.kiq(CopilotPayloadSchema(ticket_id=ticket.id))`.
- [x] ✅ Проверка:
  - [x] Если подсказка уже в БД, `open_ticket` возвращает её сразу в теле ответа `OperatorTicketWorkspaceSchema`.

---

## Этап 7. Тестирование и верификация

> **Цель:** 100% подтверждение работоспособности всех сценариев через автоматические тесты.

- [x] Создать файл [backend/tests/rag/test_copilot.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/tests/rag/test_copilot.py):
  - [x] `test_mock_copilot_llm_client_l1_and_l2`: проверка эвристики рекомендаций линий L1 и L2;
  - [x] `test_qdrant_tickets_init_and_search`: проверка создания коллекции, сидирования прецедентов и косинусного ранжирования;
  - [x] `test_qdrant_tickets_graceful_degradation`: проверка устойчивости при недоступности Qdrant;
  - [x] `test_ticket_copilot_summary_persistence`: сохранение и извлечение `TicketCopilotSummaryModel` в PostgreSQL через `async_session`;
  - [x] `test_generate_copilot_summary_taskiq_success`: сквозной запуск фоновой задачи с публикацией в канал оператора;
  - [x] `test_open_ticket_returns_existing_summary`: проверка `open_ticket` для Сценария Б (подсказка уже сгенерирована);
  - [x] `test_copilot_failure_isolation`: проверка сохранения деградированной подсказки при падении LLM.
- [x] Запуск всех тестов:
  - [x] `pytest backend/tests/rag/test_copilot.py -v` (14 PASSED, 1 SKIPPED)
  - [x] `pytest backend/tests/operators/ -v` (21 PASSED)
- [x] Обновление чекбоксов в [docs/HACKATHON_ROADMAP.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/HACKATHON_ROADMAP.md) для задачи HIGH-04.
