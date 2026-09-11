# Архитектурная прожарка (Grill Me): Расчет показателей эффективности и сводный аналитический дашборд (MED-02)

> **Статус:** Проектирование и согласование архитектурных решений  
> **Исполнитель:** Разработчик 1  
> **Зона ответственности:** `backend/src/analytics/` (`models.py`, `schemas.py`, `metrics.py`, `service.py`, `repository.py`, `tasks.py`), `backend/src/api/v1/analytics.py`, миграции Alembic  
> **Цель:** Фиксация строгих инженерных решений по 5 ключевым развилкам перед реализацией фонового расчета метрик и аналитических API-эндпоинтов.

---

## 1. Источник данных для сводного дашборда `GET /api/v1/analytics/dashboard`

### Проблема:
- Если формировать витрину дашборда исключительно из суточных агрегатов `operator_metrics_daily`:
  1. В `operator_metrics_daily` сохраняются показатели **только назначенных операторов**. Тикеты, решенные ботом (`assigned_operator_id IS NULL`), туда не попадают по определению таблицы. Рассчитать `bot_resolved_percent` и общее число обращений из суточной таблицы операторов невозможно.
  2. Данные за текущие сутки («сегодня») будут полностью отсутствовать до ночного запуска планировщика Taskiq.
  3. Невозможно получить корректную статистику за произвольные временные срезы (например, с 09:00 понедельника по 18:00 пятницы).
- Если производить полный расчет на лету по таблицам `tickets`, `ticket_feedbacks`, `ticket_audits`, `system_incidents`:
  - Возникает риск медленных запросов при отсутствии индексов и неоптимальных `JOIN`.

### Принятое инженерное решение:
**Прямой расчет на лету (On-Demand Live Aggregation) единым SQL-запросом в `AnalyticsRepository.get_dashboard_metrics(from_date, to_date)`.**

1. **Единый оптимизированный SQL-запрос:**
   Вместо N независимых запросов все скалярные показатели рассчитываются за один проход по фильтрованному срезу тикетов:
   ```sql
   WITH period_tickets AS (
       SELECT 
           t.id,
           t.status,
           t.assigned_operator_id,
           t.created_at,
           t.opened_at,
           t.assigned_at,
           t.closed_at,
           tf.score AS client_score,
           ta.is_system_issue,
           ta.politeness_score,
           ta.completeness_score
       FROM tickets t
       LEFT JOIN ticket_feedbacks tf ON tf.ticket_id = t.id
       LEFT JOIN ticket_audits ta ON ta.ticket_id = t.id
       WHERE t.created_at >= :from_datetime
         AND t.created_at <= :to_datetime
   ),
   first_responses AS (
       -- Время первого ответа оператора по тикетам периода
       SELECT 
           m.ticket_id,
           MIN(m.created_at) AS first_operator_response_at
       FROM messages m
       JOIN period_tickets pt ON pt.id = m.ticket_id
       WHERE m.sender_type = 'operator'
       GROUP BY m.ticket_id
   )
   SELECT
       COUNT(pt.id) AS total_tickets,
       
       -- Процент автоматизации ботом среди закрытых тикетов
       ROUND(
           COALESCE(
               (COUNT(pt.id) FILTER (WHERE pt.status = 'resolved' AND pt.assigned_operator_id IS NULL)::float /
                NULLIF(COUNT(pt.id) FILTER (WHERE pt.status = 'resolved'), 0)) * 100.0,
               0.0
           )::numeric,
           2
       ) AS bot_resolved_percent,
       
       -- Среднее время первого ответа (разница между созданием тикета и ответом оператора)
       ROUND(
           COALESCE(
               AVG(EXTRACT(EPOCH FROM (fr.first_operator_response_at - pt.created_at))),
               0.0
           )::numeric,
           2
       ) AS avg_first_response_time_sec,
       
       -- Среднее время полного решения тикета (AHT)
       ROUND(
           COALESCE(
               AVG(EXTRACT(EPOCH FROM (pt.closed_at - COALESCE(pt.opened_at, pt.assigned_at, pt.created_at))))
               FILTER (WHERE pt.closed_at IS NOT NULL),
               0.0
           )::numeric,
           2
       ) AS avg_handling_time_sec,
       
       -- Базовый CSAT клиентов (1-5)
       ROUND(COALESCE(AVG(pt.client_score), 0.0)::numeric, 2) AS client_csat,
       
       -- Скорректированный CSAT (исключая системные сбои портала)
       ROUND(
           COALESCE(
               AVG(pt.client_score) FILTER (WHERE pt.is_system_issue IS NOT TRUE),
               0.0
           )::numeric,
           2
       ) AS adjusted_csat,
       
       -- AI-метрики качества
       ROUND(COALESCE(AVG(pt.politeness_score), 0.0)::numeric, 2) AS avg_ai_politeness_score,
       ROUND(COALESCE(AVG(pt.completeness_score), 0.0)::numeric, 2) AS avg_ai_completeness_score,
       
       -- Число активных сбоев
       (SELECT COUNT(*) FROM system_incidents WHERE status = 'open') AS active_incidents_count
   FROM period_tickets pt
   LEFT JOIN first_responses fr ON fr.ticket_id = pt.id;
   ```

2. **Гарантия миллисекундного отклика:**
   - Таблица `tickets` фильтруется по индексу `created_at`.
   - Таблица `messages` обращается только по `ticket_id` из периода через существующий индекс `idx_messages_ticket_feed (ticket_id, created_at)`.
   - Подзапрос к `system_incidents` использует частичный индекс `idx_incidents_status WHERE status = 'open'`.

---

## 2. Математика и границы расчета First Response Time (FRT) и Average Handling Time (AHT)

### Проблема:
- **FRT:** Если для сотрудника считать FRT от первого сообщения клиента в чате, сотрудник будет несправедливо оштрафован за время, пока обращение висело в очереди ожидания `queued` до момента его назначения.
- **AHT:** Тикеты бота закрываются без участия оператора (поля `assigned_at` и `opened_at` равны `NULL`).

### Принятое инженерное решение:
1. **Разделение FRT для дашборда и оператора:**
   - **Для сводного дашборда `GET /api/v1/analytics/dashboard` (клиентский SLA):**
     $$\text{FRT}_{\text{dashboard}} = \text{EXTRACT(EPOCH FROM } (m_{\text{op\_first}}.\text{created\_at} - t.\text{created\_at}))$$
     Клиент оценивает общее время ожидания с момента отправки вопроса до первого ответа человека.
   - **Для суточной эффективности оператора `operator_metrics_daily` (персональный KPI):**
     $$\text{FRT}_{\text{operator}} = \text{EXTRACT(EPOCH FROM } (m_{\text{op\_first}}.\text{created\_at} - \text{COALESCE}(t.\text{opened\_at}, t.\text{assigned\_at})))$$
     Оценивается персональная оперативность сотрудника после того, как тикет поступил в его активную рабочую смену.
   - **Краевой случай (тикет закрыт без ответа оператора):**
     Если оператор не отправил ни одного сообщения (тикет был закрыт клиентом по таймауту или переведен), данный тикет **не включается в расчет FRT** (`NULL`), чтобы не искажать среднее арифметическое.

2. **Расчет AHT (Average Handling Time):**
   - **Для тикетов с участием оператора:**
     $$\text{Handling Time} = \text{EXTRACT(EPOCH FROM } (t.\text{closed\_at} - \text{COALESCE}(t.\text{opened\_at}, t.\text{assigned\_at}, t.\text{created\_at})))$$
     Фактическое время диалога с момента взятия в работу до нажатия кнопки «Завершить».
   - **Для автоматических тикетов бота:**
     $$\text{Handling Time}_{\text{bot}} = \text{EXTRACT(EPOCH FROM } (t.\text{closed\_at} - t.\text{created\_at}))$$
     Время от первого запроса клиента до выдачи итогового ответа базы знаний / FAQ Fast-Path.

---

## 3. Формула Deflection Rate и защита от деления на ноль

### Проблема:
- В `BACKEND_ARCHITECTURE.md` (§3, строка 120) зафиксировано:
  $$\text{Deflection Rate} = \frac{\text{COUNT}(\text{status} = 'resolved' \text{ AND } \text{assigned\_operator\_id IS NULL})}{\text{COUNT}(\text{status} = 'resolved')}$$
- В пользовательских требованиях встречается вариант деления на общее число всех тикетов (`total_tickets`).
- Если за период не было тикетов (например, пустая база или начало смены), деление на ноль вызовет ошибку `ZeroDivisionError` в Python или `division by zero` в PostgreSQL.

### Принятое инженерное решение:
1. **Утвержденная формула:**
   Утверждается формула из архитектурной спецификации (`BACKEND_ARCHITECTURE.md` §3): **доля автоматических решений среди успешно завершенных консультаций**.
   - Дополнительно в схему ответа `AnalyticsDashboardResponseSchema` включается поле `total_tickets`, что позволяет фронтенду при необходимости вывести и конверсию относительно общего входящего потока.
2. **Защита от деления на ноль:**
   В SQL применяется `NULLIF(COUNT(resolved), 0)` в связке с `COALESCE(..., 0.0)`:
   ```sql
   COALESCE(
       (COUNT(*) FILTER (WHERE status = 'resolved' AND assigned_operator_id IS NULL)::float /
        NULLIF(COUNT(*) FILTER (WHERE status = 'resolved'), 0)) * 100.0,
       0.0
   )
   ```
   Если тикетов нет, возвращается безопасное значение `0.0`.

---

## 4. Исправление дефекта `OperatorMetricDailyModel` и миграция Alembic

### Проблема:
В существующей таблице `operator_metrics_daily` (миграция `b2c3d4e5f6a7`) и ORM-модели отсутствуют поля `created_at` и `updated_at`, предусмотренные `DATABASE_SPECIFICATION.md` (§5.4).

### Принятое инженерное решение:
1. **Создание новой миграции Alembic:**
   Создается ревизия `c3d4e5f6a7b8_add_timestamps_to_operator_metrics_daily.py`:
   ```python
   def upgrade() -> None:
       op.add_column(
           "operator_metrics_daily",
           sa.Column(
               "created_at",
               sa.DateTime(timezone=True),
               server_default=sa.func.clock_timestamp(),
               nullable=False,
           ),
       )
       op.add_column(
           "operator_metrics_daily",
           sa.Column(
               "updated_at",
               sa.DateTime(timezone=True),
               server_default=sa.func.clock_timestamp(),
               nullable=False,
           ),
       )
       op.create_index(
           "idx_metrics_operator_period",
           "operator_metrics_daily",
           ["operator_id", sa.text("metric_date DESC")],
       )
   ```
2. **Обновление модели в `backend/src/analytics/models.py`:**
   Добавляются атрибуты `created_at` и `updated_at` с `DateTime(timezone=True)` и `server_default=func.clock_timestamp()`.
3. **Реализация атомарного UPSERT через `pg_insert`:**
   В `AnalyticsRepository` метод `upsert_operator_daily_metrics` реализуется через PostgreSQL-диалект:
   ```python
   stmt = pg_insert(OperatorMetricDailyModel).values(...)
   stmt = stmt.on_conflict_do_update(
       constraint="uq_operator_daily_metrics",
       set_={
           "total_tickets_handled": stmt.excluded.total_tickets_handled,
           "avg_first_response_time_sec": stmt.excluded.avg_first_response_time_sec,
           "avg_handling_time_sec": stmt.excluded.avg_handling_time_sec,
           "avg_client_csat": stmt.excluded.avg_client_csat,
           "avg_adjusted_csat": stmt.excluded.avg_adjusted_csat,
           "avg_ai_quality_score": stmt.excluded.avg_ai_quality_score,
           "updated_at": func.clock_timestamp(),
       },
   )
   await self.session.execute(stmt)
   ```

---

## 5. Расписание и контекст запуска фоновой задачи `calculate_daily_metrics`

### Проблема:
- В `QUEUES_SPECIFICATION.md` (§2.3) указано время запуска `00:05`.
- В запросе упоминалось `01:00`.
- Серверы воркеров могут работать в UTC, тогда как проект обязан функционировать по московскому времени (`Europe/Moscow`, UTC+3).

### Принятое инженерное решение:
1. **Каноническое время расписания:**
   Утверждается запуск в **`00:05` по московскому времени** (`crontab: 5 0 * * *`).
   - К 00:00:00 сутки полностью завершены;
   - 5-минутная дельта гарантирует закрытие зависших сетевых соединений и завершение отложенных задач аудита;
   - Руководство и супервизоры получают актуальные агрегированные данные с самого начала нового рабочего дня.
2. **Использование часового пояса проекта:**
   При вычислении даты по умолчанию строго используется `settings.TIMEZONE`:
   ```python
   now_msk = datetime.now(settings.TIMEZONE)
   calculation_date = (now_msk - timedelta(days=1)).date()
   ```
3. **Ручной запуск и точечный перерасчет:**
   Задача Taskiq `calculate_daily_metrics` принимает полезную нагрузку:
   ```python
   class DailyMetricsPayloadSchema(BaseModel):
       metric_date: date | None = None
       operator_id: UUID | None = None
   ```
   - Если `metric_date` не передан — рассчитывается вчерашний день (`yesterday`).
   - Если `operator_id` передан — пересчитывается статистика только по указанному сотруднику.
   - Если `operator_id is None` — выбираются все операторы с активными/завершенными тикетами за указанные сутки.
4. **Распределенный лок и защита от перегрузки:**
   Запуск задачи защищается блокировкой в Redis:
   `RedisDistributedLock(redis, key="lock:calculate_daily_metrics", ttl_seconds=300)`.

---

## Итоговый вердикт готовности к разработке
Все 5 развилок детерминированы.
Следующий шаг — формирование детального плана реализации (`implementation_plan.md`) и запуск кодирования.
