# MED-03 — Реестр системных инцидентов и выгрузка отчетов

> Ветка: `feat/med-03-incidents-export`
> Зона ответственности: `backend/src/analytics/`, `backend/src/api/v1/analytics.py`
> Блокирующая зависимость: задача MED-02 (дашборд и метрики операторов)

---

## 1. Модель данных `SystemIncidentModel`

**Файл:** `backend/src/analytics/models.py` (строки 153-201)

### Поля

| Поле | Тип Python | БД | Примечание |
|---|---|---|---|
| `id` | `UUID` | `UUID PRIMARY KEY` | `uuid6.uuid7()` |
| `ticket_id` | `UUID` | `UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE` | Тикет-источник сбоя |
| `incident_type` | `str` | `VARCHAR(64) NOT NULL` | `portal_downtime`, `crypto_plugin`, `api_error` |
| `description` | `str` | `TEXT NOT NULL` | Описание симптомов |
| `status` | `str` | `VARCHAR(32) NOT NULL DEFAULT 'open'` | `open`, `in_review`, `resolved` |
| `created_at` | `datetime` | `TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()` | |
| `resolved_at` | `datetime or None` | `TIMESTAMPTZ NULL` | Время устранения |

### Перечисления (StrEnum)

- `IncidentType`: `PORTAL_DOWNTIME`, `CRYPTO_PLUGIN`, `API_ERROR`
- `IncidentStatus`: `OPEN`, `IN_REVIEW`, `RESOLVED`

### Связь с TicketModel

- `SystemIncidentModel.ticket` -> `TicketModel.incidents` (bidirectional, cascade `all, delete-orphan`)
- В реестре инцидентов код линии не отдается напрямую через `SystemIncidentModel` — его нужно получать через JOIN с `TicketModel.line` (relationship `TicketModel.line -> SupportLineModel`).
- Тип отношения: один тикет может иметь НЕСКОЛЬКО инцидентов (`list["SystemIncidentModel"]` на стороне TicketModel).
- Жадной подгрузки (`selectinload`) на уровне модели нет — задавать в запросах репозитория.

**Вывод:** Модель полностью соответствует DATABASE_SPECIFICATION.md §5.3. Код линии и `ticket_id` требуют отдельного JOIN-запроса.

---

## 2. Эндпоинт реестра инцидентов (GET /api/v1/analytics/incidents)

### Параметры фильтрации

API_SPECIFICATION.md §6.3 задает только схему ответа. Параметры не указаны явно.
По паттерну других аналитических эндпоинтов и описанию задачи предполагаются:

```
status: Literal['open', 'in_review', 'resolved'] | None = None
incident_type: str | None = None
limit: int = 50
offset: int = 0
```

> ОТКРЫТЫЙ ВОПРОС: параметры фильтрации в спецификации не прописаны — нужно зафиксировать в ADR.

### Схема SystemIncidentResponseSchema

СТАТУС: ГОТОВА (`backend/src/analytics/schemas.py`, строки 108-119)

```python
class SystemIncidentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ticket_id: UUID
    incident_type: str
    description: str
    status: str
    created_at: datetime
    resolved_at: datetime | None
```

Схема совпадает с API_SPECIFICATION.md §6.3 один к одному. OK

### Эндпоинт обновления статуса (PATCH)

- В API_SPECIFICATION.md НЕТ упоминания `PATCH /api/v1/analytics/incidents/{id}`.
- В HACKATHON_ROADMAP.md (MED-03) перечислено только GET для двух эндпоинтов.
- **Вывод**: `PATCH` в рамках MED-03 не реализуется. Только `GET`.

---

## 3. Эндпоинт экспорта данных (GET /api/v1/analytics/export)

### Query-параметры (API_SPECIFICATION.md §6.4)

```
from_date: date    # обязательно
to_date: date      # обязательно
format: Literal['csv', 'json'] = 'csv'
```

### Состав выгрузки

API_SPECIFICATION.md §6.4 НЕ содержит схемы `AnalyticsExportResponseSchema` и не описывает состав строк/колонок.

Состав реконструируется из:
- критериев приемки MED-03: «завершенные тикеты с CSAT, is_system_issue, root_cause, временем обработки, оператором»
- BACKEND_ARCHITECTURE.md §4: audit покрывает вежливость, полноту, root_cause, is_system_issue
- полей TicketModel + TicketAuditModel + TicketFeedbackModel

#### Предполагаемые колонки CSV/JSON-отчета (15 штук)

| Колонка | Источник | Тип |
|---|---|---|
| `ticket_id` | `TicketModel.id` | UUID |
| `created_at` | `TicketModel.created_at` | datetime |
| `closed_at` | `TicketModel.closed_at` | datetime or None |
| `handling_time_sec` | `closed_at - created_at` (вычисляемое) | int or None |
| `status` | `TicketModel.status` | str |
| `priority` | `TicketModel.priority` | str (P0/P1/P2) |
| `line_code` | `TicketModel.line.code` | str or None |
| `assigned_operator_name` | `TicketModel.assigned_operator.full_name` | str or None |
| `feedback_score` | `TicketFeedbackModel.score` | int or None |
| `feedback_comment` | `TicketFeedbackModel.comment` | str or None |
| `is_system_issue` | `TicketAuditModel.is_system_issue` | bool or None |
| `root_cause` | `TicketAuditModel.root_cause` | str or None |
| `politeness_score` | `TicketAuditModel.politeness_score` | int or None |
| `completeness_score` | `TicketAuditModel.completeness_score` | int or None |
| `audit_summary` | `TicketAuditModel.summary` | str or None |

> ОТКРЫТЫЙ ВОПРОС: точный состав колонок не зафиксирован в спецификации — требует утверждения.

### Механизм формирования CSV

- Тип ответа FastAPI: `Response` с `media_type="text/csv"` (стандарт для синхронного формирования)
  - Альтернатива: `StreamingResponse` для больших датасетов
- Заголовок: `Content-Disposition: attachment; filename=analytics_export_YYYY-MM-DD.csv`
- Кодировка: `utf-8-sig` (UTF-8 с BOM) для корректного открытия кириллицы в Microsoft Excel
- Библиотека: стандартная `csv.DictWriter` с `io.StringIO`

### Схема JSON-выгрузки

`AnalyticsExportResponseSchema` в `schemas.py` ОТСУТСТВУЕТ — нужно создать.

---

## 4. Текущее состояние service.py и repository.py

### AnalyticsRepository (repository.py)

| Метод | Статус |
|---|---|
| `create_feedback` | ГОТОВ |
| `get_feedback_by_ticket_id` | ГОТОВ |
| `create_audit` | ГОТОВ |
| `get_audit_by_ticket_id` | ГОТОВ |
| `create_incident` | ГОТОВ |
| `get_open_incident_by_type` | ГОТОВ (дедупликация) |
| `get_ticket_full_audit_data` | ГОТОВ (жадная подгрузка для аудита) |
| `get_incidents` (реестр с фильтрами) | ОТСУТСТВУЕТ |
| `get_tickets_for_export` (JOIN для экспорта) | ОТСУТСТВУЕТ |

### AnalyticsService (service.py)

| Метод | Статус |
|---|---|
| `audit_ticket_quality` | ГОТОВ (полный цикл) |
| `save_feedback` | ГОТОВ |
| `_safe_enqueue_audit` | ГОТОВ |
| `get_incidents` (бизнес-логика реестра) | ОТСУТСТВУЕТ |
| `generate_export` (CSV/JSON) | ОТСУТСТВУЕТ |

---

## 5. Защита маршрутов

**Файл:** `backend/src/api/v1/analytics.py`

```python
router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))],
)
```

СТАТУС: Защита уже установлена на уровне роутера.
Новые эндпоинты `GET /incidents` и `GET /export` наследуют ограничение ролей `supervisor` и `admin` автоматически.
Дополнительных зависимостей на уровне хендлеров не требуется.

---

## 6. Итоговый gap-анализ

### Что нужно создать с нуля

| # | Артефакт | Файл |
|---|---|---|
| 1 | `AnalyticsExportRowSchema` + `AnalyticsExportResponseSchema` | `analytics/schemas.py` |
| 2 | `AnalyticsRepository.get_incidents(status, incident_type, limit, offset)` | `analytics/repository.py` |
| 3 | `AnalyticsRepository.get_tickets_for_export(from_date, to_date)` | `analytics/repository.py` |
| 4 | `AnalyticsService.get_incidents(...)` | `analytics/service.py` |
| 5 | `AnalyticsService.generate_export(from_date, to_date, format)` | `analytics/service.py` |
| 6 | `GET /api/v1/analytics/incidents` хендлер | `api/v1/analytics.py` |
| 7 | `GET /api/v1/analytics/export` хендлер | `api/v1/analytics.py` |

### Открытые вопросы (требуют утверждения перед реализацией)

1. Параметры фильтрации `GET /incidents`: в спецификации не указаны явно. Принять: `status`, `incident_type`, `limit`, `offset`?
2. Состав колонок CSV-экспорта: 15 колонок по таблице выше — подтвердить или скорректировать?
3. `StreamingResponse` vs `Response` для CSV: при каком объеме переключаемся на streaming?
4. Фильтр статуса тикета для экспорта: только `resolved`? Или включать `closed_by_inactivity` и `closed_by_moderation`?
5. Имя файла CSV: использовать `to_date` или дату генерации отчета?
