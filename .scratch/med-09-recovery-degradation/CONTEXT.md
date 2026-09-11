# Контекст анализа для задачи MED-09: Аварийное восстановление очередей и режим деградации сервиса

## Обзор задачи
- **Код задачи:** MED-09
- **Название:** Аварийное восстановление очередей и режим деградации сервиса
- **Зона ответственности:** [backend/src/operators/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/service.py), [backend/src/chat/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/service.py)
- **Нормативные документы:**
  - [BACKEND_ARCHITECTURE.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/BACKEND_ARCHITECTURE.md) (§2, §3, §8)
  - [QUEUES_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/QUEUES_SPECIFICATION.md) (§3, §4)
  - [API_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/API_SPECIFICATION.md) (§3.2, §3.3)
  - [DATABASE_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/DATABASE_SPECIFICATION.md) (§3.2)
  - [HACKATHON_ROADMAP.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/HACKATHON_ROADMAP.md) (строки 370–379)

---

## 1. Аварийное восстановление очередей из PostgreSQL при старте / сбое Redis

### 1.1. Индекс `idx_tickets_queued_recovery`
- **Текущее состояние в кодовой базе:**
  - В [backend/src/chat/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/models.py#L124-L135) индекс **ОТСУТСТВУЕТ**. В `TicketModel.__table_args__` объявлен только индекс `idx_tickets_chat_history` (`chat_id`, `created_at`).
  - В миграциях Alembic ([backend/alembic/versions/8c3a971c267b_create_support_lines_tickets_messages.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/alembic/versions/8c3a971c267b_create_support_lines_tickets_messages.py#L90)) индекс также не создавался.
- **Спецификация индекса:**
  - Согласно [DATABASE_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/DATABASE_SPECIFICATION.md#L284-L286) и [QUEUES_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/QUEUES_SPECIFICATION.md#L207-L216):
    ```sql
    CREATE INDEX idx_tickets_queued_recovery ON tickets (line_id, priority, created_at)
    WHERE status = 'queued';
    ```
  - **Тип:** Частичный B-tree индекс (partial index) по условию `WHERE status = 'queued'`.
  - **Колонки:** `line_id`, `priority`, `created_at`.
  - **Обоснование сортировки:** Поскольку значения приоритета строковые (`'P0' < 'P1' < 'P2'`), сортировка `ORDER BY priority ASC, created_at ASC` гарантирует, что критические инциденты P0 обрабатываются первыми, а внутри одной приоритетной группы строго соблюдается FIFO (хронологический порядок).

### 1.2. Жизненный цикл приложения (Lifespan)
- **Точка входа:** [backend/src/main.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/main.py#L16-L37):
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
      app.state.redis = redis
      if not broker.is_worker_process:
          await broker.startup()
      yield
      if not broker.is_worker_process:
          await broker.shutdown()
      await redis.aclose()
      await engine.dispose()
  ```
- **Текущее состояние:**
  - При старте сервиса вызов восстановления очередей из PostgreSQL в Redis **НЕ реализован**.
  - Периодическая задача [check_system_timeouts](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/tasks.py#L64-L121) выполняется раз в 30 секунд, но сверяет только таймауты неактивности клиентов/операторов и не проводит reconciliation состояния очереди тикетов в Redis.

### 1.3. Устройство очереди в Redis и методы восстановления
- **Структура ключей в Redis:**
  - В [backend/src/core/redis_client.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/core/redis_client.py#L87-L170) класс `RedisLineQueue` работает с ключами:
    `queue:line:{line_code}` (например, `queue:line:L1`, `queue:line:L2`, `queue:line:L3`).
  - Приоритет P0 пушится в начало: `LPUSH queue:line:{line_code} {ticket_id}`.
  - Приоритеты P1 и P2 пушатся в хвост: `RPUSH queue:line:{line_code} {ticket_id}`.
  - Балансировщик забирает тикеты с головы через `LPOP queue:line:{line_code}` под блокировкой `lock:dispatch:line:{line_code}`.
- **Наличие методов восстановления:**
  - Метод `recover_queued_tickets_from_db()` (или аналогичный) в [OperatorService](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/service.py), [OperatorRepository](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/repository.py), [TicketRepository](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/repository.py) **ОТСУТСТВУЕТ**.
  - В репозиториях нет специализированного запроса для выборки тикетов со статусом `queued`, упорядоченных по индексу восстановления.

---

## 2. Режим деградации при отказе или таймауте LLM (Graceful Degradation)

### 2.1. Точка вызова генерации ответа
- Запрос клиента поступает в `POST /api/v1/chat/messages` ([backend/src/api/v1/chat.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/chat.py#L76-L103)).
- Оркестрация выполняется в [ChatService.process_client_message](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/service.py#L141-L300):
  - Сохраняется сообщение клиента в PostgreSQL и Redis-контекст.
  - Запускается RAG-генератор: `async for event in self.rag_service.generate_answer(rag_request):`
- [RagService.generate_answer](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/service.py#L57-L100):
  - Эмитит статусы: `classifying` $\to$ `searching` $\to$ `reranking`.
  - Получает контекстные чанки (`_retrieve_context_chunks`) и эмитит `event: sources`.
  - Запускает стрим: `async for event in self.generator.generate_response_stream(...)`.
- [RagStreamGenerator.generate_response_stream](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/generator.py#L216-L313):
  - Вызывает `self.llm_client.generate_stream(prompt, system_prompt, timeout=self.timeout)`.

### 2.2. Перехват исключений таймаута / сетевых сбоев LLM
- **В `RagStreamGenerator`:**
  - Обернут в `try ... except Exception as exc:`:
    - Если генератор упал до выдачи первого предложения (`not full_text_parts`), он отдает:
      ```python
      yield RagDegradedModeEventSchema(
          message="Генеративная модель временно недоступна. Ниже представлены найденные нормативные регламенты.",
          sources=chunks,
      )
      ```
    - Если часть предложений уже была отдана, формируется урезанный `RagDoneEventSchema` с `all_verified=False`.
- **Проблемы и слабости текущей реализации в `ChatService`:**
  1. **Отсутствие внешнего `try...except` в `process_client_message`:** Если исключение возникнет в `rag_service.generate_answer` до запуска генератора (например, таймаут/сбой векторного хранилища Qdrant, ошибка классификатора или исключение вне генератора), стрим SSE аварийно завершится с 500 ошибкой.
  2. **Потеря состояния в БД при деградации:** При получении `event: degraded_mode` событие передается клиенту по SSE, но `RagDoneEventSchema` не приходит. В итоге:
     - Запись сообщения бота в таблицу `messages` **не создается**;
     - Найденные источники в `message_sources` **не сохраняются**;
     - В оперативный контекст Redis `chat:context:{ticket_id}` запись **не добавляется**.
     - В результате при перезагрузке страницы (`GET /api/v1/chat`) клиент видит, что его вопрос остался без ответа.

### 2.3. Формат контракта `event: degraded_mode`
- **Pydantic-схема:** [backend/src/rag/schemas.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/rag/schemas.py#L206-L223):
  ```python
  class RagDegradedModeEventSchema(BaseModel):
      event: Literal["degraded_mode"] = "degraded_mode"
      message: str = Field(..., description="Пользовательское пояснение о переходе в режим деградации")
      sources: list[RagSourceChunkSchema] = Field(default_factory=list, description="Список первоисточников")
  ```
- **SSE-формат передачи клиенту:**
  ```text
  event: degraded_mode
  data: {"message": "Генеративная модель временно недоступна. Ниже представлены найденные нормативные регламенты.", "sources": [{"chunk_id": "...", "doc_id": "...", "title": "...", "quote_text": "..."}]}
  ```
- **Требования спецификаций:**
  - Согласно [RAG_AND_PARSING_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/RAG_AND_PARSING_SPECIFICATION.md#L436) и [API_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/API_SPECIFICATION.md#L399):
    В режиме деградации клиенту выводятся найденные статьи базы знаний (Top-3 источников) без генерации текста нейросетью, исключается передача ошибки 500, и обеспечивается возможность дальнейшей эскалации на оператора.

---

## 3. Переподключение клиента к SSE при обрыве сети (Connection Recovery & Replay)

### 3.1. Работа эндпоинта `GET /api/v1/chat/events` с `Last-Event-ID`
- **Текущее состояние в [backend/src/api/v1/chat.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/chat.py#L38-L74):**
  - Эндпоинт принимает `request: Request`, `current_user: CurrentClientSseDep`, `ticket_id: UUID | None`.
  - Заголовок `Last-Event-ID` (и query-параметр `last_event_id`) **НЕ извлекаются и НЕ обрабатываются**.
- **Формирование событий SSE в [backend/src/core/redis_client.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/core/redis_client.py#L18-L33):**
  - Функция `_format_pubsub_to_sse` генерирует только строки `event: ...` и `data: ...`.
  - Поле `id: <event_id>` **НЕ формируется**.
  - Браузерный стандартный клиент `EventSource` без поля `id` не может зафиксировать последний идентификатор события и при обрыве соединения отправляет пустой заголовок `Last-Event-ID`.

### 3.2. Считывание истории пропущенных сообщений
- **Redis vs PostgreSQL:**
  - Ключ `chat:history:{ticket_id}` в Redis **не существует и не поддерживается**.
  - Ключ `chat:context:{ticket_id}` содержит список JSON-объектов `{"sender", "text", "timestamp"}` (без уникальных message ID).
  - В PostgreSQL в таблице `messages` все сообщения имеют первичный ключ `id: UUID` (генерируемый по стандарту UUIDv7, где заложена метка времени и сохраняется естественная монотонная сортировка) и `created_at`.
- **Архитектурный контракт:**
  - В [BACKEND_ARCHITECTURE.md §8 (строка 200)](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/BACKEND_ARCHITECTURE.md#L200) зафиксировано:
    > «При потере связи клиент переподключается к эндпоинту GET SSE. Пропущенные сообщения считываются из истории тикета в PostgreSQL по стандартному REST-запросу.»
  - При этом в [HACKATHON_ROADMAP.md (строка 377)](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/HACKATHON_ROADMAP.md#L377) указан критерий приемки:
    > «Протестировано переподключение клиента к постоянному каналу событий при обрыве сети с досылкой истории переписки.»
  - В настоящее время механизм досылки пропущенных сообщений через `Last-Event-ID` в SSE-канале **отсутствует**. Если клиент переподключается к `GET /api/v1/chat/events`, он слушает только новые события из Redis Pub/Sub, а события, произошедшие в момент разрыва связи, теряются в SSE-потоке.

---

## 4. Сводная таблица готовности компонентов к задаче MED-09

| Компонент / Механизм | Статус в коде | Что требуется реализовать |
|---|---|---|
| Индекс `idx_tickets_queued_recovery` | ❌ Отсутствует в `TicketModel` и миграциях | Добавить индекс в `TicketModel.__table_args__` с предикатом `WHERE status = 'queued'` и подготовить миграцию |
| Вычитка тикетов `queued` по приоритету | ❌ Отсутствует метод в репозиториях | Добавить метод `get_queued_tickets_for_recovery()` с сортировкой `priority ASC, created_at ASC` |
| Восстановление очередей при старте сервиса | ❌ Отсутствует в `lifespan` | Реализовать метод `recover_queued_tickets_from_db()` в `OperatorService` и вызвать его в `lifespan` в `main.py` |
| Фоновая сверка очередей Taskiq | ❌ Нет в `check_system_timeouts` | Добавить сверку рассинхронизации между PostgreSQL (`queued`) и Redis списком в периодическую задачу |
| Обработка сбоя LLM в `RagStreamGenerator` | ✅ Схема и генерация `degraded_mode` есть | Готово на уровне модуля генерации RAG |
| Обработка сбоя RAG в `ChatService` | ⚠️ Частично (нет внешнего try/except) | Обернуть вызов `generate_answer` в try-except для гарантированного перехода в `degraded_mode` без 500 ошибки |
| Сохранение ответа в БД при деградации | ❌ Не сохраняется сообщение и источники | Обеспечить фиксацию деградированного ответа и источников в `messages` / `message_sources`, чтобы не терять контекст |
| Поддержка `id: <event_id>` в SSE-событиях | ❌ Отсутствует в `_format_pubsub_to_sse` | Добавить `id: ...` в SSE-сообщения на основе ID сообщения или timestamp |
| Replay пропущенных сообщений по `Last-Event-ID` | ❌ Не считывается заголовок | Добавить извлечение `Last-Event-ID` в `GET /api/v1/chat/events` и досылку непрочитанных сообщений из PostgreSQL |
