# Контекст и результаты разведки по задаче MED-02
## «Расчет показателей эффективности и сводный аналитический дашборд»

**Дата анализа:** 2026-09-11  
**Статус этапа:** Разведка и анализ кодовой базы завершены (Read-Only).  
**Целевые модули:**
- `backend/src/analytics/` (`models.py`, `schemas.py`, `metrics.py`, `service.py`, `repository.py`, `tasks.py`)
- `backend/src/api/v1/analytics.py`
- `backend/alembic/versions/` (миграции аналитики)
- `docs/API_SPECIFICATION.md` (§6.1, §6.2)
- `docs/DATABASE_SPECIFICATION.md` (§5.4)
- `docs/QUEUES_SPECIFICATION.md` (§2.3, §3, §4)
- `docs/BACKEND_ARCHITECTURE.md` (§3, §4)

---

### 1. Модель суточных метрик `OperatorMetricDailyModel`

#### 1.1. Текущее состояние модели и миграций
- Модель **была объявлена** в рамках задачи `MED-01` в файле [`backend/src/analytics/models.py`](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/models.py#L204-L250).
- Соответствующая таблица создана в миграции Alembic [`backend/alembic/versions/b2c3d4e5f6a7_create_analytics_tables.py`](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/alembic/versions/b2c3d4e5f6a7_create_analytics_tables.py#L133-L180).

#### 1.2. Анализ соответствия схеме базы данных (DATABASE_SPECIFICATION.md §5.4)

| Поле в DATABASE_SPECIFICATION.md (§5.4) | Тип в БД-спецификации | Поле в `OperatorMetricDailyModel` (`models.py`) | Поле в миграции `b2c3d4e5f6a7` | Соответствие / Расхождение |
|---|---|---|---|---|
| `id` | `UUID PRIMARY KEY` | `id: Mapped[uuid.UUID]` (uuid7) | `sa.Column("id", sa.Uuid())` | **Соответствует** |
| `operator_id` | `UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE` | `operator_id: Mapped[uuid.UUID]`, FK `users.id`, `ondelete="RESTRICT"` | `sa.ForeignKeyConstraint(["operator_id"], ["users.id"], ondelete="RESTRICT")` | **Расхождение по ondelete:** в спецификации `CASCADE`, в коде `RESTRICT`. |
| `metric_date` | `DATE NOT NULL` | `metric_date: Mapped[date]` | `sa.Column("metric_date", sa.Date())` | **Соответствует** |
| `total_tickets_handled` | `INTEGER NOT NULL DEFAULT 0` | `total_tickets_handled: Mapped[int]` (default 0) | `sa.Column("total_tickets_handled", sa.Integer(), server_default="0")` | **Соответствует спецификации БД.** В пользовательском запросе названо `tickets_resolved_count` — в кодовой базе и спецификации БД каноническое имя `total_tickets_handled`. |
| `avg_first_response_time_sec` | `NUMERIC(8,2) NULL` | `avg_first_response_time_sec: Mapped[Decimal \| None]` | `sa.Numeric(precision=8, scale=2)` | **Соответствует спецификации БД.** В пользовательском запросе названо `avg_first_response_time_seconds` — каноническое имя `avg_first_response_time_sec`. |
| `avg_handling_time_sec` | `NUMERIC(8,2) NULL` | `avg_handling_time_sec: Mapped[Decimal \| None]` | `sa.Numeric(precision=8, scale=2)` | **Соответствует спецификации БД.** В пользовательском запросе названо `avg_handling_time_seconds` — каноническое имя `avg_handling_time_sec`. |
| `avg_client_csat` | `NUMERIC(3,2) NULL` | `avg_client_csat: Mapped[Decimal \| None]` | `sa.Numeric(precision=3, scale=2)` | **Соответствует спецификации БД.** В запросе названо `avg_csat` — каноническое имя `avg_client_csat`. |
| `avg_adjusted_csat` | `NUMERIC(3,2) NULL` | `avg_adjusted_csat: Mapped[Decimal \| None]` | `sa.Numeric(precision=3, scale=2)` | **Соответствует** |
| `avg_ai_quality_score` | `NUMERIC(3,2) NULL` | `avg_ai_quality_score: Mapped[Decimal \| None]` | `sa.Numeric(precision=3, scale=2)` | **Соответствует** |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()` | **ОТСУТСТВУЕТ** | **ОТСУТСТВУЕТ** | ⚠️ **КРИТИЧЕСКИЙ ДЕФЕКТ:** Колонка `created_at` не была добавлена ни в модель, ни в миграцию! |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()` | **ОТСУТСТВУЕТ** | **ОТСУТСТВУЕТ** | ⚠️ **КРИТИЧЕСКИЙ ДЕФЕКТ:** Колонка `updated_at` не была добавлена ни в модель, ни в миграцию! |

#### 1.3. Композитные ключи и индексы для UPSERT
- **Уникальное ограничение:**
  - В модели объявлено: `UniqueConstraint("operator_id", "metric_date", name="uq_operator_daily_metrics")`.
  - В миграции создано: `sa.UniqueConstraint("operator_id", "metric_date", name="uq_operator_daily_metrics")`.
  - В PostgreSQL ограничение `UNIQUE` гарантирует наличие уникального композитного B-tree индекса, что позволяет выполнять атомарный UPSERT через синтаксис PostgreSQL:
    ```sql
    INSERT INTO operator_metrics_daily (id, operator_id, metric_date, total_tickets_handled, ...)
    VALUES (...)
    ON CONFLICT (operator_id, metric_date) DO UPDATE SET ...
    ```
- **Индексы:**
  - В модели и миграции создан: `Index("idx_operator_metrics_date", "metric_date")`.
  - В `DATABASE_SPECIFICATION.md` (§5.4) дополнительно заложен составной индекс для быстрых выборок периода по оператору: `CREATE INDEX idx_metrics_operator_period ON operator_metrics_daily (operator_id, metric_date DESC);`.

---

### 2. Контракты Pydantic-схем (`backend/src/analytics/schemas.py`)

В текущем файле [`backend/src/analytics/schemas.py`](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/schemas.py) схемы дашборда и суточных метрик операторов **ПОЛНОСТЬЮ ОТСУТСТВУЮТ** (реализованы только схемы аудита MED-01: `AuditTicketPayloadSchema`, `AuditLlmOutputSchema`, `FeedbackCreateRequestSchema`, `FeedbackResponseSchema`, `TicketAuditResponseSchema`, `SystemIncidentResponseSchema`).

#### 2.1. Схема для `GET /api/v1/analytics/dashboard`
Согласно `API_SPECIFICATION.md` (§6.1), контракт ответа определен следующим образом:

```python
class AnalyticsDashboardResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_tickets: int = Field(..., description="Общее число обращений за период")
    bot_resolved_percent: float = Field(..., description="Процент обращений, решенных ботом без человека")
    avg_first_response_time_sec: float = Field(..., description="Среднее время первого ответа оператора")
    avg_handling_time_sec: float = Field(..., description="Среднее время полного решения обращения")
    client_csat: float = Field(..., description="Средняя оценка клиентов от 1 до 5")
    adjusted_csat: float = Field(..., description="Скорректированная оценка клиентов за вычетом системных сбоев")
    avg_ai_politeness_score: float = Field(..., description="Оценка вежливости по аудиту модели")
    avg_ai_completeness_score: float = Field(..., description="Оценка полноты по аудиту модели")
    active_incidents_count: int = Field(..., description="Число нерешенных технических сбоев портала")
```

**Сравнение с полями из запроса пользователя:**
- Query-параметры фильтрации: в `API_SPECIFICATION.md` (§6.1) query-параметры названы `from_date` (date, опционально) и `to_date` (date, опционально). В запросе пользователя фигурируют `period_from`, `period_to`. Для строгого соответствия спецификации роутер должен принимать `from_date: date | None = None` и `to_date: date | None = None`. При необходимости возврата периода в теле ответа можно добавить `from_date`/`to_date` (или алиасы).
- `bot_resolved_percent` vs `deflection_rate` / `bot_resolved_tickets`: в спецификации API поле названо `bot_resolved_percent: float` (значение от 0.0 до 100.0). В запросе пользователя упомянуты также `bot_resolved_tickets` и `deflection_rate`. Добавление точного количества тикетов бота (`bot_resolved_tickets: int`) и `deflection_rate: float` обогащает дашборд и не ломает спецификацию.
- Времена: в спецификации API используются суффиксы `_sec` (`avg_first_response_time_sec`, `avg_handling_time_sec`).

#### 2.2. Схемы для `GET /api/v1/analytics/operators`
Согласно `API_SPECIFICATION.md` (§6.2), контракт определен следующим образом:

```python
class OperatorDailyMetricResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operator_id: UUID = Field(..., description="Идентификатор оператора")
    operator_name: str = Field(..., description="ФИО сотрудника")
    line_code: str = Field(..., description="Линия поддержки")
    metric_date: date = Field(..., description="Дата")
    total_tickets_handled: int = Field(..., description="Количество обработанных тикетов")
    avg_first_response_time_sec: float | None = Field(None, description="Среднее время первого ответа")
    avg_handling_time_sec: float | None = Field(None, description="Среднее время диалога")
    avg_client_csat: float | None = Field(None, description="Средняя оценка клиентов")
    avg_adjusted_csat: float | None = Field(None, description="Скорректированная оценка")
    avg_ai_quality_score: float | None = Field(None, description="Оценка качества от модели")
```

- Эндпоинт `GET /api/v1/analytics/operators` возвращает список таких объектов: `list[OperatorDailyMetricResponseSchema]` (Query-параметры: `date: date | None = None`, `line_code: str | None = None`).
- Для удобства и расширяемости можно также поддержать схему-обертку `OperatorMetricsListResponseSchema(items: list[...], total: int)`.

#### 2.3. Схема для фоновой задачи Taskiq `calculate_daily_metrics`
Согласно `QUEUES_SPECIFICATION.md` (§2.3), необходима схема полезной нагрузки:
```python
class DailyMetricsPayloadSchema(BaseModel):
    metric_date: str = Field(..., description="Дата расчетного периода (YYYY-MM-DD)")
    operator_id: UUID | None = Field(None, description="Идентификатор конкретного оператора для точечного перерасчета")
```

---

### 3. Формулы и специфика расчета метрик в БД

#### 3.1. First Response Time (FRT, Время первого ответа)
- **Бизнес-смысл:** Скорость реакции оператора на обращение клиента.
- **Точки фиксации в данных:**
  1. Первое сообщение тикета (клиентское): `MIN(created_at)` из `messages` с `sender_type = 'client'` (или `tickets.created_at`).
  2. Первое ответное сообщение оператора: `MIN(created_at)` из `messages` с `sender_type = 'operator'` для данного тикета (и данного оператора).
- **Специфика оператора vs очередь:**
  - Если отсчитывать от первого сообщения клиента вообще, то для тикетов, долго ожидавших в очереди (`queued`), в FRT войдет время ожидания в очереди (Queue Wait Time).
  - Если оценивать непосредственно оперативность оператора, время отсчитывается от момента назначения/взятия тикета: `opened_at` (или `assigned_at`).
  - **Каноническая формула для тикета по ТЗ:**
    $$\text{FRT}_{\text{ticket}} = \text{EXTRACT(EPOCH FROM } (\min(m_{\text{operator}}.\text{created\_at}) - \min(m_{\text{client}}.\text{created\_at})))$$
  - **Агрегация по оператору за сутки:**
    $$\text{avg\_first\_response\_time\_sec} = \text{AVG}(\text{FRT}_{\text{ticket}})$$ по всем тикетам, где оператор дал хотя бы один ответ.

#### 3.2. Average Handling Time (AHT, Среднее время ведения / решения)
- **Бизнес-смысл:** Продолжительность работы над обращением.
- **Точки фиксации в данных:**
  - В таблице `tickets` есть поля:
    * `created_at` — создание тикета;
    * `assigned_at` — назначение на оператора;
    * `opened_at` — фактическое открытие/взятие в работу (`OperatorRepository.assign_ticket_to_operator`: `if ticket.opened_at is None: ticket.opened_at = datetime.now(...)`);
    * `closed_at` — фиксация закрытия обращения (`resolved`, `closed_by_inactivity` и др.).
- **Каноническая формула:**
  - Для обращений с оператором:
    $$\text{Handling Time} = \text{EXTRACT(EPOCH FROM } (\text{closed\_at} - \text{COALESCE}(\text{opened\_at}, \text{assigned\_at}, \text{created\_at})))$$
  - Для автоматических обращений бота (где оператор не назначался):
    $$\text{Handling Time}_{\text{bot}} = \text{EXTRACT(EPOCH FROM } (\text{closed\_at} - \text{created\_at}))$$
  - Среднее время AHT:
    $$\text{avg\_handling\_time\_sec} = \text{AVG}(\text{Handling Time})$$

#### 3.3. Deflection Rate (Процент автоматизации ботом)
- **Определение в `BACKEND_ARCHITECTURE.md` (§3, строка 120):**
  $$\text{Deflection Rate} = \frac{\text{COUNT}(\text{status} = 'resolved' \text{ AND } \text{assigned\_operator\_id IS NULL})}{\text{COUNT}(\text{status} = 'resolved')}$$
- **Определение в запросе пользователя:** отношение тикетов, решенных ботом (`status = 'resolved' AND assigned_operator_id IS NULL`), к **общему числу обращений за период** (`COUNT(*)`).
- **Сравнение:**
  - Знаменатель `COUNT(status = 'resolved')` показывает долю бота среди *успешно завершенных консультаций*.
  - Знаменатель `COUNT(*)` показывает долю бота от *всех входящих обращений* (включая незавершенные, закрытые по неактивности и отмененные).
  - В схеме API `API_SPECIFICATION.md` (§6.1) метрика называется `bot_resolved_percent: float` (в процентах, от 0 до 100%).
  - SQL-выражение с защитой от деления на 0:
    ```sql
    ROUND(
      COALESCE(
        (COUNT(*) FILTER (WHERE status = 'resolved' AND assigned_operator_id IS NULL)::float /
         NULLIF(COUNT(*) FILTER (WHERE status = 'resolved'), 0)) * 100.0,
        0.0
      )::numeric,
      2
    )
    ```

#### 3.4. Adjusted CSAT (Скорректированная оценка удовлетворенности)
- **Бизнес-смысл:** Защита оператора от снижения оценки из-за сбоев инфраструктуры платформы (падение портала, ошибки плагина ЭЦП `0x...`, недоступность ЕРУЗ).
- **Связь таблиц:**
  - `ticket_feedbacks` хранит оценку клиента `score` (от 1 до 5).
  - `ticket_audits` хранит результат арбитража LLM `is_system_issue` (`true` при наличии подтвержденного системного сбоя).
- **Каноническая формула:**
  - Базовый CSAT (`client_csat` / `avg_client_csat`):
    $$\text{CSAT}_{\text{raw}} = \text{AVG}(tf.\text{score})$$
  - Скорректированный CSAT (`adjusted_csat` / `avg_adjusted_csat`):
    $$\text{CSAT}_{\text{adj}} = \text{AVG}(tf.\text{score}) \quad \text{для всех тикетов, где } (ta.\text{is\_system\_issue IS NOT TRUE})$$
  - Любой тикет, где аудит подтвердил `is_system_issue = true`, строго исключается из числителя и знаменателя при расчете скорректированной оценки оператора и сводного дашборда.

#### 3.5. AI Quality Scores
- В аудите `ticket_audits` языковая модель выставляет:
  * `politeness_score` (1–5) — вежливость;
  * `completeness_score` (1–5) — полнота решения.
- Для общего дашборда:
  * `avg_ai_politeness_score = AVG(ta.politeness_score)`
  * `avg_ai_completeness_score = AVG(ta.completeness_score)`
- Для суточных показателей оператора:
  * `avg_ai_quality_score = AVG((ta.politeness_score + ta.completeness_score) / 2.0)`

---

### 4. Существующий роутер `backend/src/api/v1/analytics.py`

#### 4.1. Проверка зависимостей безопасности
- В файле [`backend/src/api/v1/analytics.py`](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/analytics.py#L8-L12):
  ```python
  router = APIRouter(
      prefix="/analytics",
      tags=["analytics"],
      dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))],
  )
  ```
  Безопасность проверена: роутер **уже защищен** централизованной проверкой RBAC для ролей `supervisor` и `admin` (реализовано в рамках задачи HIGH-13).

#### 4.2. Наличие эндпоинтов
- В файле объявлен только `APIRouter`.
- **Ни одного эндпоинта нет** (файл фактически пустой за пределами объявления роутера и зависимости).
- Предстоит реализовать:
  1. `GET /api/v1/analytics/dashboard`
  2. `GET /api/v1/analytics/operators`

---

### 5. Периодическая задача `calculate_daily_metrics` (`backend/src/analytics/tasks.py`)

#### 5.1. Регистрация в Taskiq Scheduler
- В [`backend/src/analytics/tasks.py`](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/tasks.py) сейчас зарегистрирована **только одна задача**: `audit_ticket_quality`.
- Задача `calculate_daily_metrics` **ОТСУТСТВУЕТ** и в Taskiq Scheduler **НЕ ЗАРЕГИСТРИРОВАНА**.

#### 5.2. Спецификация расписания и часовой пояс
- В `docs/QUEUES_SPECIFICATION.md` (§2.3, строка 126) зафиксировано:
  > Расписание Taskiq Scheduler: **ежедневно в 00:05**.
- В запросе пользователя упомянуто: «раз в сутки в 01:00 UTC+3 / `crontab`».
- В проекте действует строгое правило времени: **московское время (`Europe/Moscow`, UTC+3)**.
- В Taskiq используется `LabelScheduleSource(broker)` (см. `backend/src/core/broker.py:24-27`), что позволяет задать расписание прямо в декораторе:
  ```python
  @broker.task(
      task_name="calculate_daily_metrics",
      queue_name="analytics_queue",
      schedule=[{"cron": "5 0 * * *"}],  # либо 0 1 * * *
  )
  ```
- **Специфика расчета отчетных суток:** При запуске ночью (в 00:05 или 01:00) расчетная дата `metric_date` — это **вчерашний день** относительно текущего времени в часовом поясе Москвы: `(datetime.now(settings.TIMEZONE) - timedelta(days=1)).date()`.

#### 5.3. Идемпотентность и распределенная блокировка
- Задача должна быть защищена `RedisDistributedLock(redis, key="lock:calculate_daily_metrics", ttl_seconds=300)`.
- Сохранение в `operator_metrics_daily` должно выполняться через `INSERT ... ON CONFLICT (operator_id, metric_date) DO UPDATE` (идемпотентный UPSERT).

---

### 6. Сводка выявленных расхождений и архитектурных развилок для `/grill-me`

1. **Отсутствие `created_at` и `updated_at` в `OperatorMetricDailyModel`:**
   В `DATABASE_SPECIFICATION.md` (§5.4) эти поля обязательны, но отсутствуют в текущей модели и миграции `b2c3d4e5f6a7`. Необходимо решить: создаем ли отдельную миграцию для добавления этих колонок или обновляем модель.
2. **Точка отсчета First Response Time (FRT):**
   От первого сообщения клиента в тикете (`m.created_at`) ИЛИ от момента передачи тикета оператору (`opened_at` / `assigned_at`).
3. **Знаменатель Deflection Rate:**
   Делить на `COUNT(status = 'resolved')` (по `BACKEND_ARCHITECTURE.md`) ИЛИ на `COUNT(*)` (все созданные за период тикеты).
4. **Расписание Taskiq Scheduler:**
   `00:05` (по `QUEUES_SPECIFICATION.md`) ИЛИ `01:00` UTC+3 (по запросу пользователя).
5. **Источник данных дашборда `GET /api/v1/analytics/dashboard`:**
   Расчет на лету прямым SQL-запросом по таблицам `tickets`, `ticket_feedbacks`, `ticket_audits` за произвольный период `[from_date, to_date]` (обеспечивает актуальность до секунды) vs агрегация из суточных таблиц `operator_metrics_daily`.
