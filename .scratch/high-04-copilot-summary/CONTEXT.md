# Контекст и анализ готовности: HIGH-04 («Подготовка аналитической подсказки и контекста для оператора»)

## 1. Модель данных `ticket_copilot_summaries`

- **Статус в кодовой базе:** Модель **НЕ ОБЪЯВЛЕНА**.
  - В `backend/src/operators/models.py` объявлены только `SupportLineModel`, `OperatorProfileModel`, `OperatorShiftStatus`.
  - Модуля `backend/src/rag/models.py` не существует.
  - Таблица `ticket_copilot_summaries` отсутствует в миграциях Alembic (`backend/alembic/versions/`).
- **Архитектурная принадлежность:** Согласно [DATABASE_SPECIFICATION.md](../../docs/DATABASE_SPECIFICATION.md) (§1.1, строка 37), таблица `ticket_copilot_summaries` относится к домену `src/operators/`, модели `TicketCopilotSummaryModel` и репозиторию `OperatorRepository`.
- **Спецификация структуры таблицы (DATABASE_SPECIFICATION.md §3.5):**

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор подсказки |
| `ticket_id` | `UUID` | `NOT NULL, UNIQUE, REFERENCES tickets(id) ON DELETE CASCADE` | Внешний ключ обращения |
| `summary` | `TEXT` | `NOT NULL` | Краткая формулировка проблемы клиента |
| `suggested_line_code` | `VARCHAR(32)` | `NULL` | Рекомендованная линия поддержки (`L1`, `L2`, `L3`) |
| `suggested_response` | `TEXT` | `NULL` | Черновик ответа для оператора |
| `recommended_chunk_ids` | `VARCHAR(64)[]` / `ARRAY(String)` | `NOT NULL, DEFAULT '{}'` | Массив идентификаторов релевантных статей базы знаний |
| `similar_resolved_tickets` | `JSONB` | `NOT NULL, DEFAULT '[]'::jsonb` | 3 похожих закрытых обращения из базы прецедентов Qdrant |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время генерации подсказки (UTC+3 / `settings.TIMEZONE`) |

- **Индексы:**
  ```sql
  CREATE INDEX idx_copilot_summaries_ticket ON ticket_copilot_summaries (ticket_id);
  ```

---

## 2. Схемы данных Pydantic

- **`CopilotSummaryResponseSchema`:** **ПРИСУТСТВУЕТ** в `backend/src/operators/schemas.py` (L229–249).
  ```python
  class CopilotSummaryResponseSchema(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      summary: str
      suggested_line_code: str | None = None
      suggested_response: str | None = None
      recommended_chunk_ids: list[str] = Field(default_factory=list)
      similar_resolved_tickets: list[SimilarTicketItemSchema] = Field(default_factory=list)
  ```
- **`SimilarTicketItemSchema`:** **ПРИСУТСТВУЕТ** в `backend/src/operators/schemas.py` (L211–227).
  ```python
  class SimilarTicketItemSchema(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      ticket_id: str
      support_line: str
      user_query: str
      solution_text: str
      similarity_score: float
  ```
- **`CopilotPayloadSchema`:** **ОТСУТСТВУЕТ** в кодовой базе (ни в `src/rag/schemas.py`, ни в `src/operators/schemas.py`).
  - Описана в [QUEUES_SPECIFICATION.md](../../docs/QUEUES_SPECIFICATION.md) (§2.2):
    ```python
    class CopilotPayloadSchema(BaseModel):
        ticket_id: UUID = Field(..., description="Идентификатор обращения")
    ```
- **Связанная схема рабочего пространства оператора:** `OperatorTicketWorkspaceSchema` в `src/operators/schemas.py` (L254) уже содержит опциональное поле `copilot_summary: CopilotSummaryResponseSchema | None = None`, однако в `OperatorService.open_ticket()` оно сейчас захардкожено как `copilot_summary=None`.

---

## 3. Модуль `backend/src/rag/copilot.py`

- **Текущее состояние:** **ПУСТАЯ ЗАГЛУШКА** (2 строки, 105 байт).
  Содержит исключительно заголовочный docstring:
  ```python
  """Генерация сводки диалога и подсказок оператору (Copilot)."""
  ```
- Бизнес-логика, функции вызова языковой модели, поиск прецедентов и сборка подсказки отсутствуют.

---

## 4. Клиент языковой модели (`backend/src/core/llm_client.py`)

- **Текущее состояние файла:** **ПУСТАЯ ЗАГЛУШКА** (2 строки, 97 байт: `"""Клиент языковых моделей и генерации эмбеддингов."""`).
- **Существующая архитектура вызова LLM в проекте:**
  - Прямой интеграции с SDK GigaChat / YandexGPT / OpenAI на данный момент в проекте нет.
  - В смежных модулях (`router.py`, `generator.py`) используется протокольно-моковый паттерн:
    - `LlmRouterClientProtocol` (`generate_structured(schema, prompt, system_prompt, timeout)`).
    - `LlmStreamClientProtocol` (`generate_stream(prompt, system_prompt, timeout)`).
  - Для суммаризации и формирования черновика ответа Copilot требуется либо Pydantic-схема structured output (аналогично `QueryRouter`), либо специализированный генератор выжимки с fallback-стабом (`MockCopilotLlmClient`) для работы и тестирования без внешних API-ключей.

---

## 5. Поиск похожих тикетов в Qdrant (`backend/src/core/qdrant_client.py`)

- **Клиент Qdrant:** В `backend/src/core/qdrant_client.py` реализован синглтон фабрики `get_qdrant_client() -> AsyncQdrantClient`.
- **Коллекция `resolved_tickets`:** **НЕ СУЩЕСТВУЕТ** в коде.
  - В `src/kb/qdrant.py` инициализируется исключительно коллекция `knowledge_base` (dense 1024D + sparse BM25).
  - Методы создания/проверки коллекции `resolved_tickets` отсутствуют.
- **Векторный поиск прецедентов:**
  - Методов поиска похожих обращений по тексту или эмбеддингу в коде нет.
  - По спецификации ([RAG_AND_PARSING_SPECIFICATION.md](../../docs/RAG_AND_PARSING_SPECIFICATION.md) §8.3):
    - Коллекция `resolved_tickets` должна содержать векторизованные тексты закрытых тикетов (30–50 сидовых прецедентов со сбоями ЭЦП, КриптоПро и регламентными вопросами).
    - Payload точки Qdrant: `ticket_id`, `support_line`, `user_query`, `solution_text`.
    - Метод поиска должен возвращать до 3 наиболее релевантных совпадений с `similarity_score`.

---

## 6. Очереди брокера Taskiq (`backend/src/core/broker.py` и `backend/src/rag/tasks.py`)

- **Очередь `copilot_queue`:** В Taskiq на базе `ListQueueBroker` очереди не требуют предварительного объявления в `broker.py`. Имя очереди задается параметром `queue_name="copilot_queue"` в декораторе `@broker.task`.
- **Фоновая задача в `backend/src/rag/tasks.py`:** **ОТСУТСТВУЕТ**. Файл содержит только docstring.
- **Требуемая сигнатура фоновой задачи ([QUEUES_SPECIFICATION.md](../../docs/QUEUES_SPECIFICATION.md) §2.2):**
  ```python
  @broker.task(task_name="generate_copilot_summary", queue_name="copilot_queue")
  async def generate_copilot_summary(
      payload: CopilotPayloadSchema | dict[str, Any],
  ) -> dict[str, Any]:
      ...
  ```
- **Сценарий выполнения задачи:**
  1. Чтение последних сообщений тикета из Redis (`chat:context:{ticket_id}`) или fallback в PostgreSQL (`MessageModel`).
  2. Вызов модуля `src/rag/copilot.py` (LLM-суммаризация, поиск нормативных чанков, поиск похожих тикетов в Qdrant).
  3. Сохранение результата в `TicketCopilotSummaryModel` в PostgreSQL (UPSERT / ON CONFLICT).
  4. Если у тикета назначен оператор (`ticket.assigned_operator_id IS NOT NULL`), отправка события `copilot_ready` в канал оператора `channel:operator:{operator_id}` через `RedisOperatorEvents.publish_copilot_ready`.

---

## 7. Оповещение оператора (`RedisOperatorEvents`)

- **Статус:** **ПОЛНОСТЬЮ РЕАЛИЗОВАН** в `backend/src/core/redis_client.py` (L298–322).
  ```python
  async def publish_copilot_ready(
      self,
      operator_id: UUID | str,
      data: dict | BaseModel,
  ) -> int:
      """Публикует событие готовности подсказки Copilot в канал оператора.
      Канал: channel:operator:{operator_id}
      Событие: copilot_ready
      """
  ```
- При вызове отправляет корректное SSE-совместимое JSON-сообщение `{"event": "copilot_ready", "data": ...}` в персональный канал оператора `channel:operator:{operator_id}`.
- SSE-эндпоинт оператора `GET /api/v1/operators/events` уже подписан на этот канал.
