# Инженерное проектирование (Grill Me): MED-09 — Аварийное восстановление очередей и режим деградации сервиса

## 1. Контекст и цели сессии

Задача **MED-09** закрывает критические требования отказоустойчивости платформы:
1. **Холодный старт и сбой Redis:** Восстановление очередей ожидания операторов (`queue:line:{line_code}`) из PostgreSQL с гарантией соблюдения SLA (P0 < 60 с, P1 < 180 с, P2 < 600 с).
2. **Отказ или таймаут LLM:** Переход в режим деградации (`event: degraded_mode`) с выдачей Top-3 статей регламентов, сохранением ответа в PostgreSQL/Redis и предотвращением 500 ошибок.
3. **Обрыв сети клиента в SSE:** Поддержка стандарта `Last-Event-ID` для гарантированной досылки непрочитанных реплик диалога без дублирования и потери сообщений.

---

## 2. Вопрос 1: Алгоритм идемпотентного восстановления очередей (`recover_queued_tickets_from_db`)

### 2.1. Анализ рисков и граничных случаев (Adversarial Probing)
- **Риск 1: Состояние гонки при старте нескольких реплик приложения.**
  Если запущено несколько инстансов FastAPI (или воркеров Taskiq), одновременный запуск восстановления приведет к конкурентной перезаписи очередей Redis и дублированию тикетов.
- **Риск 2: Разрушение порядка приоритетов (P0 vs P1/P2).**
  В штатном режиме P0 пушится в голову (`LPUSH`), а P1/P2 — в хвост (`RPUSH`). Если при восстановлении просто брать тикеты пачкой без строгого упорядочивания, критические инциденты могут оказаться в конце очереди.
- **Риск 3: Вмешательство активного балансировщика во время восстановления.**
  Если балансировщик начнет делать `LPOP` прямо в момент, когда процедура восстановления очистила очередь и успела записать только половину тикетов, тикеты распределятся некорректно.

### 2.2. Архитектурное решение

#### А. Защита от параллельного запуска нескольких реплик
При старте приложения в `lifespan` захватывается глобальная распределенная блокировка в Redis:
```
SET lock:queue_recovery "{instance_uuid}" NX EX 30
```
- Если лок не получен — другая реплика уже выполняет восстановление, текущий инстанс пропускает процедуру.
- Если лок получен — выполняется процедура восстановления, по завершении лок атомарно освобождается Lua-скриптом.

#### Б. Построчная изоляция очередей через `lock:dispatch:line:{line_code}`
Для каждой активной линии поддержки (`SupportLineModel`):
1. Захватывается существующая распределенная блокировка балансировщика:
   `lock = line_queue.get_dispatch_lock(line_code, ttl_seconds=10)`
   Это гарантирует, что ни один фоновый воркер `dispatch_line_queue` не сможет извлекать (`LPOP`) или менять очередь во время восстановления.
2. Извлекаются все тикеты данной линии в статусе `queued` из PostgreSQL:
   ```sql
   SELECT id, priority, created_at
   FROM tickets
   WHERE line_id = :line_id AND status = 'queued'
   ORDER BY priority ASC, created_at ASC;
   ```
3. **Порядок загрузки в Redis:**
   Поскольку `'P0' < 'P1' < 'P2'`, результат сортировки возвращает:
   - Сначала все P0 от старых к новым;
   - Затем все P1 от старых к новым;
   - Затем все P2 от старых к новым.
   
   Чтобы при последующих вызовах `LPOP` первым всегда извлекался самый старый P0, список в Redis наполняется последовательным `RPUSH`:
   ```python
   # Атомарная замена через Redis Pipeline
   async with redis.pipeline(transaction=True) as pipe:
       pipe.delete(f"queue:line:{line_code}")
       if ticket_ids:
           pipe.rpush(f"queue:line:{line_code}", *ticket_ids)
       await pipe.execute()
   ```
   В результате в Redis список имеет вид:
   `[P0_oldest, ..., P0_newest, P1_oldest, ..., P1_newest, P2_oldest, ..., P2_newest]`.
   Первый `LPOP` вернет `P0_oldest`, что строго соответствует SLA!

#### В. Фоновая сверка (Reconciliation) в `check_system_timeouts`
В задачу `check_system_timeouts` (запуск раз в 30 секунд) добавляется легкая сверка:
- Для каждой линии сверяется `LLEN queue:line:{line_code}` и `SELECT COUNT(*) FROM tickets WHERE line_id = :line_id AND status = 'queued'`.
- Если обнаружено расхождение (например, Redis перезагружался без сохранения на диск или упал воркер):
  Инициируется точечный вызов `recover_line_queue(line_code)` под распределенным локом линии, синхронизируя списки с PostgreSQL.
- После успешного восстановления очередей для каждой линии с ненулевым числом тикетов вызывается триггер диспетчеризации:
  `await service._safe_dispatch_task(line_code, "queue_recovered")`.

---

## 3. Вопрос 2: Частичный индекс базы данных и миграция Alembic

### 3.1. Спецификация индекса
Индекс создается строго по спецификациям [DATABASE_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/DATABASE_SPECIFICATION.md#L285) и [QUEUES_SPECIFICATION.md](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/docs/QUEUES_SPECIFICATION.md#L215):
```sql
CREATE INDEX idx_tickets_queued_recovery 
ON tickets (line_id, priority, created_at) 
WHERE status = 'queued';
```

### 3.2. Объявление в SQLAlchemy 2.0 (`backend/src/chat/models.py`)
В класс `TicketModel` в кортеж `__table_args__` добавляется декларация с фильтрацией `postgresql_where`:
```python
Index(
    "idx_tickets_queued_recovery",
    "line_id",
    "priority",
    "created_at",
    postgresql_where=text("status = 'queued'"),
),
```

### 3.3. Миграция Alembic
- Идентификатор новой ревизии: `d4e5f6a7b8c9`.
- Предшествующая ревизия (`down_revision`): `c3d4e5f6a7b8` (`c3d4e5f6a7b8_add_timestamps_to_operator_metrics_daily.py`).
- Код миграции:
```python
"""add_idx_tickets_queued_recovery

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-11 12:30:00.000000

"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_tickets_queued_recovery",
        "tickets",
        ["line_id", "priority", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tickets_queued_recovery",
        table_name="tickets",
        postgresql_where=sa.text("status = 'queued'"),
    )
```

---

## 4. Вопрос 3: Гарантия целостности данных при деградации LLM (`event: degraded_mode`)

### 4.1. Анализ рисков и текущих уязвимостей
1. **Сбой до генератора:** Если падает Qdrant, сервис эмбеддингов или база знаний при вызове `_retrieve_context_chunks`, в `ChatService` нет перехвата — вылетает HTTP 500.
2. **Потеря истории диалога:** При получении `event: degraded_mode` генератор не шлет `RagDoneEventSchema`. В текущем коде `ChatService` сохранение сообщения и источников в БД происходит **только** внутри блока `elif isinstance(event, RagDoneEventSchema):`. Из-за этого деградированный ответ не сохраняется ни в `messages`, ни в `message_sources`, ни в Redis-контекст.
3. **Поведение UI:** При обновлении страницы (`F5`) клиент видит, что сообщение пропало, а контекст диалога рассинхронизируется.

### 4.2. Архитектурное решение: Двухуровневая деградация и обязательная фиксация в БД

#### А. Верхнеуровневый перехват в `ChatService.process_client_message`
Оборачиваем цикл обработки RAG в `try...except Exception`:
```python
try:
    async for event in self.rag_service.generate_answer(rag_request):
        # Обработка событий sources, sentence, done, degraded_mode
        ...
except Exception as exc:
    logger.exception("Критический сбой конвейера RAG: %s", exc)
    # Формируем аварийное событие деградации верхнего уровня
    degraded_event = RagDegradedModeEventSchema(
        message=(
            "Сервис временно испытывает высокую нагрузку. "
            "Пожалуйста, повторите запрос или обратитесь к оператору."
        ),
        sources=collected_sources,
    )
    # Сохраняем аварийное сообщение в БД и отдаем клиенту
    await self._save_degraded_bot_response(active_ticket.id, bot_message_id, degraded_event, collected_sources)
    yield f"event: degraded_mode\ndata: {degraded_event.model_dump_json(exclude={'event'})}\n\n"
```

#### Б. Обязательное сохранение сообщения деградации в PostgreSQL и Redis
При наступлении события `RagDegradedModeEventSchema` (как от `RagStreamGenerator`, так и из внешнего `except`):
1. В таблицу `messages` сохраняется реплика бота:
   - `id`: `bot_message_id` (UUIDv7);
   - `sender_type`: `MessageSenderType.BOT`;
   - `text`: текст сообщения деградации (`event.message`);
   - `moderation_status`: `MessageModerationStatus.PASSED`.
2. В таблицу `message_sources` сохраняются все найденные первоисточники (`collected_sources`), чтобы в веб-интерфейсе продолжали работать сноски и плашки документов.
3. В Redis оперативный контекст диалога добавляется реплика:
   `await self.redis_context.add_message(active_ticket.id, "bot", event.message, created_at)`.
4. В сессии выполняется `await self.session.commit()`.

Благодаря этому:
- История диалога остается полной и консистентной;
- При перезагрузке страницы клиент видит выданный ботом ответ со ссылками на регламенты;
- Оператор при последующей эскалации видит, какие статьи регламента система успела показать клиенту.

---

## 5. Вопрос 4: Протокол Replay пропущенных сообщений по `Last-Event-ID` в SSE

### 5.1. Анализ рисков и проблемы Replay-Race-Condition
- **Риск:** Если сервер сначала прочитает непрочитанные сообщения из базы данных, а потом подпишется на Redis Pub/Sub, сообщение, пришедшее в промежутке между этими шагами, будет безвозвратно потеряно.
- **Риск:** Если сервер сначала подпишется на Redis Pub/Sub, а потом прочитает базу данных, сообщение может прийти и в Pub/Sub, и попасть в выборку из БД, вызвав дублирование на клиенте.

### 5.2. Архитектурное решение

#### А. Добавление поля `id:` в SSE-поток
В `_format_pubsub_to_sse` ([backend/src/core/redis_client.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/core/redis_client.py#L18)) добавляется генерация поля `id:`:
```python
def _format_pubsub_to_sse(raw_data: str | bytes) -> str:
    ...
    event_name = parsed.get("event", "message")
    payload = parsed.get("data", {})
    # Извлекаем message_id из payload или генерируем детерминированный/текущий UUIDv7
    event_id = str(payload.get("id") or payload.get("message_id") or uuid6.uuid7())
    payload_str = json.dumps(payload, ensure_ascii=False, default=str)
    return f"id: {event_id}\nevent: {event_name}\ndata: {payload_str}\n\n"
```
Теперь браузерный `EventSource` автоматически сохраняет `id` последнего события и передает его в заголовке `Last-Event-ID` при реконнекте.

#### Б. Алгоритм бесконфликтного Replay (Sub-Then-Query-With-Deduplication)
В `ChatService.stream_chat_events`:
1. Принимаем `last_event_id: UUID | None` из заголовка `Last-Event-ID` (или query-параметра `last_event_id`).
2. **Шаг 1. Подписка:** Сначала открываем подписку на Redis Pub/Sub канал `channel:ticket:{ticket_id}`.
3. **Шаг 2. Вычитка пропущенных реплик из PostgreSQL:**
   Если `last_event_id` передан:
   - Находим сообщение-отсечку по `last_event_id` и выбираем все сообщения тикета, созданные строго позже:
     ```sql
     SELECT * FROM messages 
     WHERE ticket_id = :ticket_id 
       AND created_at > (SELECT created_at FROM messages WHERE id = :last_event_id)
     ORDER BY created_at ASC;
     ```
     *(Если само сообщение с `last_event_id` не найдено, fallback: выборка по `id > :last_event_id`).*
   - Создаем множество отправленных ID: `replayed_ids = {msg.id for msg in missed_messages} | {last_event_id}`.
   - Стримим пропущенные сообщения клиенту как SSE `event: new_message` с `id: {msg.id}`.
4. **Шаг 3. Чтение из Redis Pub/Sub с дедупликацией:**
   - При получении сообщения из Pub/Sub проверяем: если `msg_id in replayed_ids`, пропускаем его (дедупликация).
   - Если нет — отправляем клиенту и добавляем в `replayed_ids`.

Это на 100% исключает как потерю сообщений при обрыве сети, так и их дублирование.

---

## 6. План внедрения по компонентам

1. **База данных и модели:**
   - Добавить индекс `idx_tickets_queued_recovery` в `TicketModel.__table_args__` в [backend/src/chat/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/models.py).
   - Создать миграцию `d4e5f6a7b8c9_add_idx_tickets_queued_recovery.py` в [backend/alembic/versions/](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/alembic/versions/).
   - Добавить в [OperatorRepository](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/repository.py) / [TicketRepository](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/repository.py) метод `get_queued_tickets_for_line(line_id: int) -> list[TicketModel]`.

2. **Очереди и восстановление:**
   - В [OperatorService](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/service.py) реализовать метод `recover_queued_tickets_from_db()` с глобальным локом `lock:queue_recovery` и построчными локами `lock:dispatch:line:{line_code}`.
   - Вызвать `recover_queued_tickets_from_db()` в `lifespan` в [backend/src/main.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/main.py).
   - В [backend/src/operators/tasks.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/operators/tasks.py) (`check_system_timeouts`) добавить reconciliation очередей при расхождении длины очереди в Redis и PostgreSQL.

3. **Деградация RAG:**
   - В [ChatService.process_client_message](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/service.py) добавить сохранение `event: degraded_mode` в `messages`, `message_sources` и `chat:context:{ticket_id}`.
   - Обернуть генератор в внешний `try...except` для перехвата сбоев до старта стрима (Qdrant/эмбеддинги).

4. **SSE Replay:**
   - Обновить `_format_pubsub_to_sse` в [backend/src/core/redis_client.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/core/redis_client.py), включив строку `id: <uuid>`.
   - В [backend/src/api/v1/chat.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/v1/chat.py) в эндпоинте `/events` принимать заголовок `Last-Event-ID` и query-параметр `last_event_id`.
   - В [ChatService.stream_chat_events](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/service.py) реализовать Replay пропущенных сообщений из PostgreSQL перед переходом на Pub/Sub.

5. **Тестирование:**
   - Написать тесты аварийного восстановления очередей при холодном старте и сбое Redis.
   - Написать тесты деградации с проверкой сохранения в БД и выдачи регламентов.
   - Написать тесты переподключения клиента по `Last-Event-ID` с проверкой досылки пропущенных сообщений без дублей.
