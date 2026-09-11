# Контекст и результаты разведки по задаче MED-01
## «Автоматический аудит завершенных диалогов языковой моделью»

### 1. Модель данных и сущности базы данных
- **Текущее состояние кодовой базы:**
  - Файл `backend/src/analytics/models.py` содержит только docstring. Никаких ORM-моделей в домене `analytics` пока нет.
  - Таблицы `ticket_audits`, `ticket_feedbacks`, `system_incidents`, `operator_metrics_daily` отсутствуют как в моделях SQLAlchemy, так и в версиях миграций Alembic (`backend/alembic/versions/`).
  - В `TicketModel` (`backend/src/chat/models.py`) отсутствуют связи с аудитом, отзывами и инцидентами.

- **Спецификация структуры таблиц (DATABASE_SPECIFICATION.md §5.1, §5.2, §5.3):**
  1. **Таблица `ticket_audits` (AI-QA):**
     - `id`: UUID (PK, default uuid7);
     - `ticket_id`: UUID (NOT NULL, UNIQUE, FK `tickets(id)` ON DELETE CASCADE);
     - `politeness_score`: SMALLINT (NOT NULL, CHECK `politeness_score BETWEEN 1 AND 5`);
     - `completeness_score`: SMALLINT (NOT NULL, CHECK `completeness_score BETWEEN 1 AND 5`);
     - `root_cause`: VARCHAR(64) (NULL, CHECK `root_cause IN ('operator_error', 'system_issue', 'regulation_dissatisfaction', 'none')`);
     - `summary`: TEXT (NOT NULL) — текстовое резюме вердикта языковой модели;
     - `is_system_issue`: BOOLEAN (NOT NULL, DEFAULT false) — признак технического сбоя портала;
     - `created_at`: TIMESTAMPTZ (NOT NULL, DEFAULT `clock_timestamp()`);
     - Индекс: `CREATE INDEX idx_audits_system_issue ON ticket_audits (is_system_issue) WHERE is_system_issue = true;`.

  2. **Таблица `ticket_feedbacks` (отзывы клиентов):**
     - `id`: UUID (PK, default uuid7);
     - `ticket_id`: UUID (NOT NULL, UNIQUE, FK `tickets(id)` ON DELETE CASCADE);
     - `score`: SMALLINT (NOT NULL, CHECK `score >= 1 AND score <= 5`);
     - `comment`: TEXT (NULL);
     - `created_at`: TIMESTAMPTZ (NOT NULL, DEFAULT `clock_timestamp()`);
     - Индекс: `CREATE INDEX idx_feedbacks_score ON ticket_feedbacks (score);`.

  3. **Таблица `system_incidents` (реестр технических сбоев):**
     - `id`: UUID (PK, default uuid7);
     - `ticket_id`: UUID (NOT NULL, FK `tickets(id)` ON DELETE CASCADE);
     - `incident_type`: VARCHAR(64) (NOT NULL, CHECK `incident_type IN ('portal_downtime', 'crypto_plugin', 'api_error')`);
     - `description`: TEXT (NOT NULL);
     - `status`: VARCHAR(32) (NOT NULL, DEFAULT `'open'`, CHECK `status IN ('open', 'in_review', 'resolved')`);
     - `created_at`: TIMESTAMPTZ (NOT NULL, DEFAULT `clock_timestamp()`);
     - `resolved_at`: TIMESTAMPTZ (NULL);
     - Индекс: `CREATE INDEX idx_incidents_status ON system_incidents (status) WHERE status = 'open';`.

---

### 2. Точки триггера аудита (завершение тикетов)
- **Где тикеты переходят в терминальные статусы:**
  1. `POST /api/v1/operators/tickets/{ticket_id}/resolve` (`OperatorService.resolve_ticket` в `backend/src/operators/service.py:550`):
     - Статус меняется на `resolved`, фиксируется `closed_at`, очищается контекст в Redis (`chat_context.clear_context`), публикуется событие `ticket_resolved`, освобождается слот оператора.
     - **Постановка задачи аудита сейчас отсутствует.**
  2. Автозакрытие по неактивности клиента (`OperatorService.check_timeouts` в `backend/src/operators/service.py:622`):
     - При неактивности у бота (10 минут) тикет переводится в `closed_by_inactivity`.
     - При неактивности у оператора (10 мин напоминание, 15 мин закрытие) переводится в `closed_by_inactivity`.
     - **Блок 4 регламента** (QUEUES_SPECIFICATION.md §4: поиск тикетов `status = 'resolved' AND closed_at < now - 10 min` без отзыва в `ticket_feedbacks` и без записи в `ticket_audits` с постановкой в `analytics_queue`) **пока не реализован в `check_timeouts`**.
  3. Клиентские действия (закрытие/отзыв):
     - `POST /api/v1/chat/tickets/{id}/resolve` и `POST /api/v1/chat/tickets/{id}/feedback` из `API_SPECIFICATION.md` (§3.6, §3.7) еще не созданы в `src/api/v1/chat.py` (задача HIGH-15).
- **Итог по триггеру:**
  - В настоящее время постановка задачи аудита в брокер Taskiq не вызывается ни в одном модуле кодовой базы.

---

### 3. Очередь Taskiq (QUEUES_SPECIFICATION.md §2.3, §5.1)
- **Имя очереди:** `analytics_queue`
- **Имя задачи:** `audit_ticket_quality`
- **Исполняющий сервис:** `AnalyticsService.audit_ticket()` в `src/analytics/service.py`
- **Схема полезной нагрузки (`AuditTicketPayloadSchema` в `src/analytics/schemas.py`):**
  - `ticket_id: UUID` — идентификатор тикета;
  - `trigger_reason: str` — `'feedback_received'` или `'feedback_timeout'`.
- **Параметры надежности:**
  - Предельный таймаут задачи: **120 секунд**;
  - Повторы (retries): **до 3 попыток** с экспоненциальной задержкой (5с, 15с, 45с);
  - Обработка фатального сбоя: при 3 неудачных попытках создается запись в таблице `system_incidents` с типом `api_error` (или `analytics_failure`), без замалчивания в скрытых DLQ;
  - **Идемпотентность:** воркер перед анализом проверяет наличие записи в `ticket_audits`. Если аудит по `ticket_id` уже существует, задача завершается без повторного обращения к LLM.

---

### 4. LLM-оценщик (Judge / Evaluator) и Pydantic-схемы
- **Текущее состояние `backend/src/analytics/`:**
  - Все файлы (`models.py`, `schemas.py`, `service.py`, `repository.py`, `tasks.py`, `metrics.py`) являются пустыми заглушками (только docstrings).
- **Схема структурированного ответа модели (`AuditLlmOutputSchema`):**
  ```python
  class AuditLlmOutputSchema(BaseModel):
      politeness_score: int = Field(..., ge=1, le=5, description="Оценка вежливости от 1 до 5")
      completeness_score: int = Field(..., ge=1, le=5, description="Оценка полноты и корректности от 1 до 5")
      root_cause: Literal['operator_error', 'system_issue', 'regulation_dissatisfaction', 'none'] = Field(
          ..., description="Первопричина негатива или проблем диалога"
      )
      summary: str = Field(..., description="Аналитическое заключение языковой модели")
      is_system_issue: bool = Field(default=False, description="Признак технического сбоя платформы")
      incident_type: Literal['portal_downtime', 'crypto_plugin', 'api_error'] | None = Field(
          None, description="Тип сбоя для реестра system_incidents при наличии"
      )
      incident_description: str | None = Field(
          None, description="Краткое описание симптомов технического сбоя для инцидента"
      )
  ```
- **Протокол и мок-клиент (`MockAuditLlmClient`):**
  - Паттерн аналогичен `MockCopilotLlmClient` из `src/rag/copilot.py`:
    - `AuditLlmClientProtocol(Protocol)` с методом `async def evaluate_dialog(...) -> AuditLlmOutputSchema`;
    - `MockAuditLlmClient` с поддержкой:
      * детерминированной контекстной эвристики по ключевым словам (технические сбои, недовольство регламентами, некомпетентность/грубость);
      * настраиваемого дефолтного вывода (`default_output`);
      * счетчика вызовов и симуляции сбоев (`fail_times`) для проверки повторов Taskiq;
      * искусственной задержки (`delay`) для тестирования таймаутов.

---

### 5. Влияние на аналитику
- **Спецификация эндпоинтов (API_SPECIFICATION.md §6):**
  - `GET /api/v1/analytics/dashboard`: рассчитывает `avg_ai_politeness_score`, `avg_ai_completeness_score`, `client_csat`, `adjusted_csat` (исключая тикеты с `ticket_audits.is_system_issue = true`), `active_incidents_count` (из `system_incidents`).
  - `GET /api/v1/analytics/operators`: рассчитывает `avg_adjusted_csat` и `avg_ai_quality_score` на базе оценок модели из `ticket_audits`.
  - `GET /api/v1/analytics/incidents`: отдает реестр технических сбоев, сформированный аудитором из `system_incidents`.
- **Текущее состояние маршрутов:**
  - В `backend/src/api/v1/analytics.py` на данный момент объявлен только роутер с проверкой прав `supervisor`/`admin` (HIGH-13), сами эндпоинты будут реализованы в рамках задач MED-02 и MED-03.
