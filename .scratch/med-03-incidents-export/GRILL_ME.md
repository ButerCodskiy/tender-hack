# GRILL_ME — Adversarial Design Probing: MED-03

> Ветка: `feat/med-03-incidents-export`
> Дата: 2026-09-11
> Статус: утвержденные решения по 4 инженерным рискам

---

## Риск 1 — Оптимизация SQL-запроса экспорта (N+1 Prevention)

### Вопрос: ORM joinedload vs selectinload vs Core SELECT

**Контекст:**
- `get_tickets_for_export` должен подтянуть для каждого тикета: `line.code`, `assigned_operator.full_name`, `feedback.score/comment`, `audit.*`
- Все отношения уже объявлены в `TicketModel`: `line`, `assigned_operator`, `feedback`, `audit` (все uselist=False кроме incidents)
- Размер выборки: до 90 дней × N тикетов/день — может быть тысячи строк

**Анализ вариантов:**

| Стратегия | SQL | Риск | Применимость |
|---|---|---|---|
| Lazy loading (default ORM) | 1 + N×4 запросов | Критический N+1 | Запрещено |
| `selectinload` | 1 + 4 IN-запросов | Безопасно, память O(N) | Хорошо для связей uselist=True |
| `joinedload` | 1 запрос с 4 LEFT OUTER JOIN | Безопасно, один round-trip | Оптимально для uselist=False |
| SQLAlchemy Core + flat SELECT | 1 запрос | Максимальный контроль | Избыточно при ORM-схеме |

**Решение: `joinedload` для всех четырёх связей uselist=False.**

Обоснование:
- `feedback` (uselist=False), `audit` (uselist=False), `line` (uselist=False), `assigned_operator` (uselist=False) — все скалярные → `joinedload` безопасен и даёт единственный SQL round-trip.
- `selectinload` добавил бы 4 дополнительных IN-запроса без выигрыша (связи скалярные).
- `joinedload` на `assigned_operator` требует `innerjoin=False` (LEFT OUTER JOIN), т.к. оператор может быть None (бот-решение).

**Итоговый запрос репозитория:**

```python
from sqlalchemy.orm import joinedload

stmt = (
    select(TicketModel)
    .where(
        TicketModel.status.in_([
            "resolved",
            "closed_by_inactivity",
            "closed_by_moderation",
        ]),
        TicketModel.created_at >= dt_from,
        TicketModel.created_at <= dt_to,
    )
    .options(
        joinedload(TicketModel.line),
        joinedload(TicketModel.assigned_operator),
        joinedload(TicketModel.feedback),
        joinedload(TicketModel.audit),
    )
    .order_by(TicketModel.created_at.asc())
)
```

### Вопрос: фильтрация по диапазону дат с учётом Europe/Moscow

**Проблема:** `from_date` и `to_date` — объекты `datetime.date` без тайм-зоны.
БД хранит `created_at` как `TIMESTAMPTZ` (UTC внутри). Все сравнения должны вестись в UTC, но границы дня должны совпадать с концом дня по Москве.

**Формула преобразования (через `settings.TIMEZONE = ZoneInfo("Europe/Moscow")`):**

```python
from datetime import datetime, time
from zoneinfo import ZoneInfo

tz: ZoneInfo = settings.TIMEZONE  # ZoneInfo("Europe/Moscow")

# Начало дня from_date по MSK → UTC
dt_from = datetime.combine(from_date, time.min, tzinfo=tz)
# Конец дня to_date по MSK → UTC (23:59:59.999999 MSK = 20:59:59 UTC)
dt_to = datetime.combine(to_date, time.max, tzinfo=tz)
```

Использование `time.max` даёт `23:59:59.999999` MSK — включает всё за последний день.
PostgreSQL `TIMESTAMPTZ` сравнивает в UTC, psycopg/asyncpg передают timezone-aware datetime → всё корректно.

**Запрещено:** наивные `datetime` без tzinfo, хардкод `+03:00`, промежуточные переменные-обёртки tz — проектный стандарт.

---

## Риск 2 — Пустые выборки и спецсимволы в CSV

### Пустая выборка

**Поведение:** Если за выбранный период нет тикетов с терминальным статусом:
- CSV: HTTP 200 OK, файл со строкой-заголовком и без строк данных.
- JSON: HTTP 200 OK, `{"items": []}`.
- HTTP 404 / 204 — не используется: клиент (руководитель) должен явно видеть, что данных нет, а не получать ошибку.

Реализация в сервисе:

```python
if not tickets:
    # CSV: только заголовок
    # JSON: {"items": []}
    # Обработка одинакова — сервис возвращает пустой список строк
```

### Экранирование спецсимволов в CSV

**Риск:** `feedback_comment` и `audit_summary` могут содержать:
- Переводы строк `\n`, `\r\n` (внутри ответа клиента или резюме модели)
- Кавычки `"` (прямая речь в тексте)
- Запятые `,` (разделитель CSV)
- Точки с запятой `;` (Excel с русской локалью иногда использует их как разделитель)

**Решение: `csv.writer` с `quoting=csv.QUOTE_MINIMAL` (по умолчанию):**

- `csv.writer` автоматически оборачивает поля в двойные кавычки при наличии `,`, `"` или `\n` внутри значения.
- Внутренние `"` экранируются удвоением: `"` → `""`.
- Переводы строк внутри кавычек корректно разбираются большинством CSV-парсеров (RFC 4180).
- Точки с запятой не являются разделителем в нашем CSV (разделитель — запятая), поэтому не требуют экранирования.

**Важно:** `io.StringIO` → `StringIO.getvalue()` → `.encode("utf-8-sig")` → передать в `Response(content=..., media_type="text/csv")`.

Последовательность:

```python
import csv
import io

buf = io.StringIO()
writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
writer.writerow(EXPORT_HEADERS)      # строка заголовков
for row in rows:
    writer.writerow(row.to_csv_list())

csv_bytes = buf.getvalue().encode("utf-8-sig")
```

**Защита от None:** Все nullable-поля (оператор, линия, оценка, резюме) перед записью приводятся к строке через `str(value) if value is not None else ""`.

---

## Риск 3 — Валидация диапазона дат

### from_date > to_date

**Где валидировать:** На уровне FastAPI-хендлера через Pydantic `model_validator` либо через `Query`-зависимость.

Поскольку параметры передаются как отдельные `Query`-параметры (не объект), валидацию реализуем в хендлере через явную проверку:

```python
from fastapi import HTTPException, status

if from_date > to_date:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "invalid_date_range",
            "message": "Дата начала не может быть позже даты окончания",
        },
    )
```

**Почему 422, а не 400:**
- 422 Unprocessable Entity — стандартный ответ FastAPI при ошибках валидации входных данных.
- 400 зарезервирован для ошибок бизнес-логики (например, закрытый тикет).

### Максимальное окно выгрузки — 90 дней

**Риск:** Неограниченный диапазон → запрос за годы → OOM воркера FastAPI.

**Решение: ограничение в хендлере, константа в модуле:**

```python
EXPORT_MAX_DAYS = 90

delta = (to_date - from_date).days
if delta > EXPORT_MAX_DAYS:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "date_range_too_large",
            "message": f"Максимальный диапазон выгрузки — {EXPORT_MAX_DAYS} дней",
        },
    )
```

**Порядок проверок в хендлере:**
1. `from_date > to_date` → 422
2. `delta > EXPORT_MAX_DAYS` → 422
3. Передача в `AnalyticsService.generate_export()`

---

## Риск 4 — Пагинация и индексы реестра инцидентов

### Анализ существующих индексов

Текущий индекс из `models.py` и `DATABASE_SPECIFICATION.md §5.3`:

```sql
CREATE INDEX idx_incidents_status
    ON system_incidents (status)
    WHERE status = 'open';
```

**Проблема:** Это **частичный индекс** — он охватывает ТОЛЬКО строки со `status = 'open'`.

| Запрос | Использует idx_incidents_status? |
|---|---|
| `WHERE status = 'open'` | ДА |
| `WHERE status = 'in_review'` | НЕТ — full table scan |
| `WHERE status = 'resolved'` | НЕТ — full table scan |
| `WHERE status IS NULL (без фильтра)` | НЕТ |
| `ORDER BY created_at DESC` | НЕТ — нужен отдельный индекс |

**Вывод:** Для `GET /incidents?status=resolved&limit=50` частичный индекс не помогает.

### Нужный составной индекс

Для эффективной работы `GET /api/v1/analytics/incidents` с фильтрами по `status`, `incident_type` и сортировкой `ORDER BY created_at DESC`:

```sql
CREATE INDEX idx_incidents_status_created
    ON system_incidents (status, created_at DESC);
```

Этот индекс покрывает:
- Фильтрацию по любому значению `status` (полный, не частичный)
- Сортировку `ORDER BY created_at DESC` без дополнительного filesort
- Комбинацию `WHERE status = 'open' ORDER BY created_at DESC` → index scan

Для дополнительного фильтра по `incident_type`:

```sql
CREATE INDEX idx_incidents_type_created
    ON system_incidents (incident_type, created_at DESC);
```

Или составной:

```sql
CREATE INDEX idx_incidents_list
    ON system_incidents (status, incident_type, created_at DESC);
```

**Ограничение зоны ответственности:**
Создание файла миграции Alembic закреплено за Разработчиком 4 (HACKATHON_ROADMAP §1).
Разработчик 1 (текущая задача MED-03):
- Объявляет новый `Index` декларативно в `SystemIncidentModel.__table_args__` в `models.py`
- Передаёт модель Разработчику 4 для включения в следующую ревизию миграции

**Декларация в модели:**

```python
__table_args__ = (
    CheckConstraint(...),       # существующий
    CheckConstraint(...),       # существующий
    Index(                      # существующий частичный (оставить)
        "idx_incidents_status",
        "status",
        postgresql_where=text("status = 'open'"),
    ),
    Index(                      # НОВЫЙ — для списка реестра
        "idx_incidents_status_created",
        "status",
        "created_at",
        postgresql_ops={"created_at": "DESC"},
    ),
)
```

### Покрытие пагинации `limit/offset`

OFFSET-пагинация с `created_at DESC` + составным индексом:
- При `offset=0, limit=50` — index scan первых 50 строк → быстро
- При `offset=900, limit=50` — PostgreSQL читает 950 строк → деградация при глубоком офсете
- Для реестра инцидентов (исторически небольшой набор, сотни строк) OFFSET-пагинация приемлема

**Keyset-пагинация (`last_seen_id + created_at`) не нужна** для данного кейса — объём реестра инцидентов не предполагает тысяч записей.

---

## Итоговые решения

| # | Риск | Решение |
|---|---|---|
| 1a | N+1 в экспорте | `joinedload` x4 связи, один SQL round-trip |
| 1b | Временная зона | `datetime.combine(date, time.min/max, tzinfo=settings.TIMEZONE)` |
| 2a | Пустая выборка | HTTP 200 + файл только с заголовком (CSV) / `{"items": []}` (JSON) |
| 2b | Спецсимволы CSV | `csv.writer(quoting=QUOTE_MINIMAL)` + `encode("utf-8-sig")` |
| 3a | from_date > to_date | HTTP 422 с кодом `invalid_date_range` |
| 3b | Ограничение окна | Константа `EXPORT_MAX_DAYS = 90`, HTTP 422 `date_range_too_large` |
| 4a | Частичный индекс | Добавить `idx_incidents_status_created (status, created_at DESC)` |
| 4b | Миграция | Декларировать Index в models.py, миграцию создаёт Разработчик 4 |
