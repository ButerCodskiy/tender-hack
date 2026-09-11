# План: Автоматический аудит завершенных диалогов языковой моделью (MED-01)

> **Цель проекта:** Реализовать конвейер автоматического контроля качества закрытых обращений (AI-QA) с арбитражем ответственности оператора, детекцией системных сбоев платформы (`system_incidents`), фиксацией клиентских отзывов (`ticket_feedbacks`) и асинхронной обработкой в очереди `analytics_queue` Taskiq.

---

### Этап 1: Модели базы данных и миграция Alembic
> **Цель:** Создать реляционную схему данных для домена `analytics` (`ticket_feedbacks`, `ticket_audits`, `system_incidents`, `operator_metrics_daily`) и связать с `TicketModel` без циклических импортов.

- [x] Создать модели в [backend/src/analytics/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/models.py):
  - `TicketFeedbackModel` (`ticket_feedbacks`): `id` (UUID, uuid7), `ticket_id` (UUID, UNIQUE, FK `tickets.id`), `score` (SMALLINT 1..5), `comment` (TEXT NULL), `created_at` (TIMESTAMPTZ);
  - `TicketAuditModel` (`ticket_audits`): `id` (UUID, uuid7), `ticket_id` (UUID, UNIQUE, FK `tickets.id`), `politeness_score` (SMALLINT 1..5), `completeness_score` (SMALLINT 1..5), `root_cause` (VARCHAR(64)), `summary` (TEXT), `is_system_issue` (BOOLEAN), `created_at` (TIMESTAMPTZ);
  - `SystemIncidentModel` (`system_incidents`): `id` (UUID, uuid7), `ticket_id` (UUID, FK `tickets.id`), `incident_type` (VARCHAR(64)), `description` (TEXT), `status` (VARCHAR(32), default `'open'`), `created_at` (TIMESTAMPTZ), `resolved_at` (TIMESTAMPTZ NULL);
  - `OperatorMetricDailyModel` (`operator_metrics_daily`): базовая модель суточных метрик per DATABASE_SPECIFICATION §5.4.
- [x] Добавить обратные связи в [backend/src/chat/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/models.py) к `TicketModel`:
  - `audit: Mapped["TicketAuditModel | None"] = relationship(back_populates="ticket", uselist=False, cascade="all, delete-orphan")`
  - `feedback: Mapped["TicketFeedbackModel | None"] = relationship(back_populates="ticket", uselist=False, cascade="all, delete-orphan")`
  - `incidents: Mapped[list["SystemIncidentModel"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")`
- [x] Экспортировать модели в `backend/src/analytics/__init__.py` и зарегистрировать в `backend/alembic/env.py`.
- [x] Создать миграцию Alembic `backend/alembic/versions/*_create_analytics_tables.py`.
- [x] ✅ Проверка:
  - Команда: `ruff check src tests` и запуск создания таблиц в тестовом окружении `pytest tests/auth/test_rbac_permissions.py`.
  - Ожидаемый результат: миграция валидна, `Base.metadata` включает новые таблицы, отсутствие циклических импортов.

---

### Этап 2: Схемы Pydantic, протокол и мок-клиент LLM-оценщика
> **Цель:** Сформировать контракты валидации данных и детерминированный LLM-клиент (`MockAuditLlmClient`) для оценки стенограмм диалогов.

- [x] Создать схемы данных в [backend/src/analytics/schemas.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/schemas.py):
  - `AuditTicketPayloadSchema` (`ticket_id: UUID`, `trigger_reason: str = "feedback_received"`);
  - `AuditLlmOutputSchema` (`politeness_score`, `completeness_score`, `root_cause`, `summary`, `is_system_issue`, `incident_type`, `incident_description`);
  - `FeedbackCreateRequestSchema` (`score: int`, `comment: str | None`);
  - `FeedbackResponseSchema` (`id`, `ticket_id`, `score`, `comment`, `created_at`);
  - `TicketAuditResponseSchema` (`id`, `ticket_id`, `politeness_score`, `completeness_score`, `root_cause`, `summary`, `is_system_issue`, `created_at`);
  - `SystemIncidentResponseSchema` (`id`, `ticket_id`, `incident_type`, `description`, `status`, `created_at`, `resolved_at`).
- [x] Создать [backend/src/analytics/evaluator.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/evaluator.py):
  - Системный промпт `AUDIT_SYSTEM_PROMPT` с четкими критериями вежливости, полноты и классификации причин;
  - `AuditLlmClientProtocol(Protocol)` с асинхронным методом `evaluate_dialog`;
  - Билдер контекста стенограммы `build_audit_dialog_context(ticket, messages, feedback)`;
  - `MockAuditLlmClient` с эвристической классификацией технических сбоев (КриптоПро, ЭЦП, 0x), недовольства законом (44-ФЗ, 223-ФЗ) и ошибок оператора, а также поддержкой симуляции сбоев (`fail_times`) и задержек (`delay`).
- [x] ✅ Проверка:
  - Модульные тесты эвристики `MockAuditLlmClient` на распознавание различных сценариев.

---

### Этап 3: Репозиторий и сервис аналитики
> **Цель:** Реализовать методы сохранения аудита, отзывов, инцидентов с дедупликацией открытых инцидентов и защитой от гонки через Redis lock.

- [x] Создать слой данных в [backend/src/analytics/repository.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/repository.py):
  - `create_feedback`, `get_feedback_by_ticket_id`;
  - `create_audit`, `get_audit_by_ticket_id`;
  - `create_incident`, `get_open_incident_by_type(incident_type, window_hours=2)`.
- [x] Реализовать бизнес-логику в [backend/src/analytics/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/service.py):
  - `audit_ticket_quality(ticket_id, trigger_reason)`:
    * Проверка fast-path (если аудит уже есть $\to$ return);
    * Распределенный лок в Redis `lock:audit:ticket:{ticket_id}` (60 сек);
    * Сборка контекста стенограммы и метаданных;
    * Вызов `evaluator.evaluate_dialog(...)`;
    * Атомарное сохранение `TicketAuditModel`;
    * Если `is_system_issue = True`: дедупликация и создание `SystemIncidentModel` при отсутствии аналогичного сбоя за 2 часа;
    * Обработка ошибок: при исчерпании попыток фиксация инцидента `api_error` в `system_incidents` без создания фиктивных записей в `ticket_audits`.
  - `save_feedback(user_id, ticket_id, score, comment)`:
    * Валидация принадлежности тикета клиенту, статуса `resolved`, отсутствия повторного отзыва;
    * Сохранение `TicketFeedbackModel`;
    * Безопасная постановка задачи `audit_ticket_quality` в `analytics_queue` Taskiq.
- [x] ✅ Проверка:
  - Интеграционный тест сервиса на сохранение аудита, исключение дубликатов инцидентов и корректную установку флага `is_system_issue`.

---

### Этап 4: Интеграция фоновой задачи Taskiq и триггеров закрытия
> **Цель:** Настроить фоновую задачу `audit_ticket_quality` в `analytics_queue`, подключить ее к `check_system_timeouts` и добавить эндпоинт отзыва `POST /chat/tickets/{id}/feedback`.

- [x] Зарегистрировать задачу в [backend/src/analytics/tasks.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/tasks.py):
  - `@broker.task(task_name="audit_ticket_quality", queue_name="analytics_queue", max_retries=3, retry_delay=5)`
- [x] В [backend/src/chat/repository.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/repository.py):
  - Добавить метод `get_tickets_for_audit_timeout(cutoff: datetime, limit: int = 100)` с фильтрацией по `closed_at <= cutoff`, отсутствию аудита, отсутствию отзыва и отсутствию открытого `api_error`.
- [x] В [backend/src/operators/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/service.py) в метод `check_timeouts`:
  - Реализовать Блок 4 регламента `QUEUES_SPECIFICATION.md` §4: для тикетов, закрытых более 10 минут назад без отзыва, ставить задачу `audit_ticket_quality(ticket_id, trigger_reason="feedback_timeout")`.
- [x] В [backend/src/api/v1/chat.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/chat.py):
  - Добавить эндпоинт `POST /chat/tickets/{ticket_id}/feedback` (`CurrentClientDep`) согласно `API_SPECIFICATION.md` §3.7.
- [x] ✅ Проверка:
  - Прогон `check_timeouts` на закрытом 11 минут назад тикете $\to$ задача отправляется в `analytics_queue`.

---

### Этап 5: Комплексный набор тестов и финализация
> **Цель:** Написать полный набор автоматических тестов для конвейера аудита качества диалогов, проверить соответствие всем критериям приемки дорожной карты.

- [x] Создать тестовый набор [backend/tests/analytics/test_dialog_audit.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/tests/analytics/test_dialog_audit.py):
  - Тест 1: Аудит тикета с отзывом клиента (вина оператора) $\to$ оценка вежливости/полноты сохранена, `root_cause='operator_error'`, `is_system_issue=False`;
  - Тест 2: Выявление технического сбоя портала/ЭЦП $\to$ `is_system_issue=True`, создается инцидент в `system_incidents`;
  - Тест 3: Дедупликация инцидентов $\to$ при наличии аналогичного открытого инцидента за 2 часа новая запись в `system_incidents` не создается, а в аудите тикета `is_system_issue=True` сохраняется;
  - Тест 4: Недовольство нормами закона (44-ФЗ) $\to$ `root_cause='regulation_dissatisfaction'`, `is_system_issue=False`;
  - Тест 5: Идемпотентность и Redis lock $\to$ повторный запуск задачи аудита не выполняет повторный вызов LLM и возвращает сохраненный аудит;
  - Тест 6: Срабатывание таймаут-аудита в `check_timeouts` для тикета без отзыва старше 10 минут;
  - Тест 7: Обработка 3 сбоев вызова LLM $\to$ фиксация инцидента `api_error` в `system_incidents` без искажения оценок в `ticket_audits`;
  - Тест 8: Клиентский эндпоинт `POST /chat/tickets/{id}/feedback` $\to$ сохранение отзыва, 409 при повторной отправке, 400 при попытке оценить незавершенный тикет.
- [x] Запустить полный прогон тестов через pytest и проверку линтеров `ruff check` и `ruff format`.
- [x] Отметить выполненные чекбоксы задачи `[MED-01]` в [docs/HACKATHON_ROADMAP.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/HACKATHON_ROADMAP.md).
