# План реализации: Расчет показателей эффективности и сводный аналитический дашборд (MED-02)

> **Цель проекта:** Реализовать систему операционной и суточной аналитики эффективности службы поддержки согласно спецификациям API (§6.1, §6.2), БД (§5.4) и очередей (§2.3, §3), включая расчет метрик SLA (FRT, AHT), процента автоматизации (Deflection Rate), скорректированного индекса удовлетворенности (Adjusted CSAT), фоновую регламентную задачу Taskiq Scheduler `calculate_daily_metrics` и защищенные эндпоинты сводного дашборда и рейтингов операторов.

---

### Этап 1: Миграция Alembic и обновление модели `OperatorMetricDailyModel`
> **Цель:** Устранить дефект отсутствия временных меток в таблице `operator_metrics_daily` и привести модель к полному соответствию `DATABASE_SPECIFICATION.md` (§5.4).

- [x] Создать новую миграцию Alembic [backend/alembic/versions/c3d4e5f6a7b8_add_timestamps_to_operator_metrics_daily.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/alembic/versions/c3d4e5f6a7b8_add_timestamps_to_operator_metrics_daily.py):
  - Добавить колонку `created_at` (TIMESTAMPTZ, NOT NULL, server_default=clock_timestamp());
  - Добавить колонку `updated_at` (TIMESTAMPTZ, NOT NULL, server_default=clock_timestamp());
  - Создать составной индекс `idx_metrics_operator_period` на `(operator_id, metric_date DESC)`.
- [x] Обновить класс `OperatorMetricDailyModel` в [backend/src/analytics/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/models.py):
  - Добавить маппинг `created_at: Mapped[datetime]` и `updated_at: Mapped[datetime]`;
  - Зарегистрировать составной индекс в `__table_args__`.
- [x] ✅ Проверка:
  - Запуск миграций и проверка отсутствия синтаксических ошибок через `uv run ruff check src alembic`.

---

### Этап 2: Схемы Pydantic для API и задач Taskiq
> **Цель:** Сформировать контракты валидации данных дашборда и метрик операторов согласно `API_SPECIFICATION.md` (§6.1, §6.2) и `QUEUES_SPECIFICATION.md` (§2.3).

- [x] В [backend/src/analytics/schemas.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/schemas.py) добавить схемы:
  - `AnalyticsDashboardResponseSchema`:
    * `total_tickets: int` — общее число обращений за выбранный период;
    * `bot_resolved_percent: float` — процент обращений, успешно решенных ботом;
    * `bot_resolved_tickets: int` — абсолютное число обращений, решенных ботом;
    * `avg_first_response_time_sec: float` — среднее время первого ответа оператора (FRT);
    * `avg_handling_time_sec: float` — среднее время полного решения обращения (AHT);
    * `client_csat: float` — средняя базовая оценка клиентов (1..5);
    * `adjusted_csat: float` — скорректированная оценка без учета системных сбоев;
    * `avg_ai_politeness_score: float` — средняя оценка вежливости от LLM;
    * `avg_ai_completeness_score: float` — средняя оценка полноты от LLM;
    * `active_incidents_count: int` — количество открытых технических инцидентов платформы.
  - `OperatorDailyMetricResponseSchema`:
    * `operator_id: UUID` — идентификатор специалиста;
    * `operator_name: str` — ФИО / имя сотрудника;
    * `line_code: str` — код линии поддержки (L1, L2, L3);
    * `metric_date: date` — отчетная дата;
    * `total_tickets_handled: int` — число обработанных тикетов;
    * `avg_first_response_time_sec: float | None` — средняя скорость реакции оператора;
    * `avg_handling_time_sec: float | None` — среднее время ведения диалога;
    * `avg_client_csat: float | None` — базовая оценка клиентов;
    * `avg_adjusted_csat: float | None` — скорректированная оценка;
    * `avg_ai_quality_score: float | None` — интегральный балл качества модели.
  - `DailyMetricsPayloadSchema`:
    * `metric_date: date | None = None` — дата перерасчета (опционально, по умолчанию вчера);
    * `operator_id: UUID | None = None` — точечный перерасчет конкретного оператора (опционально).
- [x] ✅ Проверка:
  - Проверка валидации Pydantic-схем, корректности типов и дефолтных значений.

---

### Этап 3: Репозиторий и SQL-агрегация (`repository.py` и `metrics.py`)
> **Цель:** Реализовать производительные SQL-запросы для прямого расчета дашборда на лету, суточного расчета операторов и атомарного UPSERT в PostgreSQL.

- [x] В [backend/src/analytics/metrics.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/metrics.py):
  - Определить доменные константы и вспомогательные функции расчета SLA и нормализации показателей.
- [x] В [backend/src/analytics/repository.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/repository.py):
  - Метод `get_dashboard_metrics(from_dt: datetime, to_dt: datetime) -> dict[str, Any]`:
    * Единый оптимизированный SQL-запрос с выборкой по интервалу `[from_dt, to_dt]`;
    * Расчет `bot_resolved_percent` с защитой от деления на ноль `NULLIF(..., 0)`;
    * Расчет клиентского FRT (`m.created_at - t.created_at`);
    * Расчет AHT (`closed_at - COALESCE(opened_at, assigned_at, created_at)`);
    * Расчет базового и скорректированного CSAT (с фильтром `ta.is_system_issue IS NOT TRUE`);
    * Агрегация AI-оценок вежливости и полноты;
    * Подсчет открытых системных инцидентов `status = 'open'`.
  - Метод `calculate_operator_metrics_for_date(target_date: date, operator_id: UUID | None = None) -> list[dict[str, Any]]`:
    * Агрегация по тикетам, закрытым или обработанным оператором за указанные сутки;
    * Расчет операторского FRT от момента взятия тикета (`m_op.created_at - COALESCE(opened_at, assigned_at)`);
    * Расчет операторского AHT (`closed_at - COALESCE(opened_at, assigned_at)`);
    * Расчет `avg_client_csat`, `avg_adjusted_csat` и `avg_ai_quality_score` (среднее от `(politeness + completeness) / 2.0`).
  - Метод `upsert_operator_daily_metrics(metrics: list[dict[str, Any]]) -> None`:
    * Атомарный пакетный `INSERT ... ON CONFLICT (operator_id, metric_date) DO UPDATE SET ...` через SQLAlchemy PostgreSQL `pg_insert`.
  - Метод `get_operator_metrics(target_date: date | None = None, line_code: str | None = None) -> list[OperatorDailyMetricResponseSchema]`:
    * Запрос к `operator_metrics_daily` с `JOIN users` (ФИО) и `JOIN support_lines` через профиль оператора с фильтрацией по дате и линии.
- [x] ✅ Проверка:
  - Тестирование генерации корректного SQL-диалекта PostgreSQL и проверка работы с mock session.

---

### Этап 4: Доменный сервис и фоновая задача Taskiq
> **Цель:** Реализовать бизнес-логику аналитики, часовые пояса Москвы и задачу Taskiq Scheduler `calculate_daily_metrics`.

- [x] В [backend/src/analytics/service.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/service.py):
  - Метод `get_dashboard(from_date: date | None = None, to_date: date | None = None) -> AnalyticsDashboardResponseSchema`:
    * Нормализация границ периода с часовым поясом `settings.TIMEZONE` (по умолчанию текущие сутки);
    * Вызов `repository.get_dashboard_metrics` и формирование схемы ответа.
  - Метод `get_operator_metrics(target_date: date | None = None, line_code: str | None = None) -> list[OperatorDailyMetricResponseSchema]`:
    * Вызов `repository.get_operator_metrics` с фильтрацией по дате и линии.
  - Метод `calculate_daily_metrics(target_date: date | None = None, operator_id: UUID | None = None) -> dict[str, Any]`:
    * Определение даты: если не задана, берется строго вчерашний день в часовом поясе Москвы `(datetime.now(settings.TIMEZONE) - timedelta(days=1)).date()`;
    * Вызов агрегации и сохранение через `upsert_operator_daily_metrics`;
    * Логирование и возврат сводной статистики.
- [x] В [backend/src/analytics/tasks.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/tasks.py):
  - Зарегистрировать периодическую задачу Taskiq:
    ```python
    @broker.task(
        task_name="calculate_daily_metrics",
        queue_name="analytics_queue",
        schedule=[{"cron": "5 0 * * *"}],
    )
    async def calculate_daily_metrics(
        payload: DailyMetricsPayloadSchema | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...
    ```
  - Защита задачи через `RedisDistributedLock` с ключом `lock:calculate_daily_metrics` (TTL 300 сек) для предотвращения параллельного запуска воркерами.
- [x] ✅ Проверка:
  - Запуск задачи с передачей тестового payload и проверка корректности захвата лока и обработки дат.

---

### Этап 5: REST API эндпоинты в `src/api/v1/analytics.py`
> **Цель:** Предоставить супервизорам и администраторам защищенный доступ к сводной витрине и карточкам эффективности специалистов.

- [x] В [backend/src/api/v1/analytics.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/analytics.py):
  - Роутер сохраняет проверку ролей `require_roles(UserRole.SUPERVISOR, UserRole.ADMIN)`;
  - Эндпоинт `GET /api/v1/analytics/dashboard`:
    * Query: `from_date: date | None = None`, `to_date: date | None = None`;
    * Response: `AnalyticsDashboardResponseSchema` (200 OK);
  - Эндпоинт `GET /api/v1/analytics/operators`:
    * Query: `date: date | None = None`, `line_code: str | None = None`;
    * Response: `list[OperatorDailyMetricResponseSchema]` (200 OK).
- [x] ✅ Проверка:
  - Проверка валидации параметров FastAPI, автодокументации OpenAPI/Swagger.

---

### Этап 6: Комплексное автоматическое тестирование и финализация
> **Цель:** Обеспечить 100% покрытие сценариев автоматическими тестами, проверить краевые случаи и обновить дорожную карту.

- [x] Создать [backend/tests/analytics/test_metrics_dashboard.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/tests/analytics/test_metrics_dashboard.py):
  - Тест 1: Расчет показателей дашборда на лету (проверка формул FRT, AHT, Deflection Rate, клиентского CSAT, Adjusted CSAT с исключением инцидентов);
  - Тест 2: Защита от деления на ноль при отсутствии тикетов за период (возврат 0.0 для Deflection Rate и CSAT);
  - Тест 3: Расчет суточных показателей операторов `calculate_daily_metrics` и проверка атомарного UPSERT при повторном запуске;
  - Тест 4: Ручной запуск перерасчета по конкретному оператору и за произвольную дату;
  - Тест 5: Выборка метрик операторов с фильтрацией по дате и линии поддержки `line_code`.
- [x] Создать [backend/tests/api/test_analytics_api.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/tests/api/test_analytics_api.py):
  - Тест 6: `GET /api/v1/analytics/dashboard` под ролью `SUPERVISOR` и `ADMIN` $\to$ 200 OK;
  - Тест 7: `GET /api/v1/analytics/dashboard` под ролью `OPERATOR` и `CLIENT` $\to$ 403 Forbidden (RBAC);
  - Тест 8: `GET /api/v1/analytics/operators` с query-фильтрами `date` и `line_code` $\to$ 200 OK;
  - Тест 9: Неавторизованный запрос $\to$ 401 Unauthorized.
- [x] Запустить полный прогон тестов через `pytest tests/analytics tests/api/test_analytics_api.py`.
- [x] Проверить линтеры и форматирование через `uv run ruff check src tests alembic` и `uv run ruff format --check src tests alembic`.
- [x] Обновить чекбоксы задачи MED-02 в [docs/HACKATHON_ROADMAP.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/HACKATHON_ROADMAP.md).
