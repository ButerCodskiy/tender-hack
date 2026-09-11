# Пошаговый план реализации: Планировщик таймаутов, контроль неактивности и контроль связи операторов (HIGH-12)

> **Статус:** Подготовлен к реализации на основе результатов Grill Me  
> **Зона ответственности:** `backend/src/operators/`, `backend/src/chat/`, `backend/src/core/`, `backend/tests/operators/`  
> **Часовой пояс:** Московское время (`Europe/Moscow`, UTC+3), строго `datetime.now(settings.TIMEZONE)`

---

## Шаг 1. Схемы результатов проверки таймаутов (`src/operators/schemas.py`)

- **Файл:** `backend/src/operators/schemas.py`
- **Задачи:**
  1. Создать Pydantic-схему результатов проверки таймаутов `CheckTimeoutsResult`:
     ```python
     class CheckTimeoutsResult(BaseModel):
         bot_tickets_closed: int = 0
         operator_warnings_sent: int = 0
         operator_tickets_closed: int = 0
         operators_marked_offline: int = 0
         tickets_requeued: int = 0
         affected_line_codes: list[str] = Field(default_factory=list)
     ```
  2. Добавить причину триггера `"operator_disconnected"` и `"inactivity_timeout"` в `DispatchTriggerReason` (если еще не добавлены).

---

## Шаг 2. Методы слоя доступа к данным в репозиториях (`src/chat/repository.py` и `src/operators/repository.py`)

- **Файлы:**
  - `backend/src/chat/repository.py` (`TicketRepository`)
  - `backend/src/operators/repository.py` (`OperatorRepository`)
- **Задачи:**
  1. В `TicketRepository` (`src/chat/repository.py`):
     - `get_inactive_bot_tickets(cutoff: datetime, limit: int = 100) -> list[TicketModel]`:
       Выборка тикетов со статусом `bot_processing` и `updated_at <= cutoff` (сортировка по `updated_at ASC`).
     - `get_in_progress_tickets_with_messages(limit: int = 100) -> list[TicketModel]`:
       Выборка тикетов `in_progress` с загруженными сообщениями (`selectinload(TicketModel.messages)`) и линией (`selectinload(TicketModel.line)`).
     - `close_ticket_by_inactivity(ticket_id: UUID, cutoff: datetime, now: datetime) -> bool`:
       Оптимистический атомарный запрос:
       ```sql
       UPDATE tickets 
       SET status = 'closed_by_inactivity', 
           closed_at = :now, 
           updated_at = :now 
       WHERE id = :ticket_id 
         AND status IN ('bot_processing', 'in_progress') 
         AND updated_at <= :cutoff 
       RETURNING id;
       ```
       Возвращает `True`, если статус обновлен, и `False`, если обновлений не произошло (гонка с новым сообщением клиента).
  2. В `OperatorRepository` (`src/operators/repository.py`):
     - `get_disconnected_operators(cutoff: datetime, limit: int = 100) -> list[OperatorProfileModel]`:
       Выборка операторов со статусом `active` или `break`, у которых `disconnected_at IS NOT NULL` и `disconnected_at <= cutoff`.
     - `set_operator_offline(user_id: UUID, now: datetime) -> OperatorProfileModel | None`:
       Обновляет статус сотрудника на `offline`, сбрасывает `disconnected_at = NULL`, `updated_at = now`.
     - `requeue_operator_tickets(operator_id: UUID, now: datetime) -> list[TicketModel]`:
       Выбирает все активные тикеты сотрудника (`assigned`, `in_progress`), обновляет:
       `assigned_operator_id = None`, `assigned_at = None`, `opened_at = None`, `status = 'queued'`, `updated_at = now`.
       Возвращает список затронутых тикетов с загруженным `line.code`.

---

## Шаг 3. Фабрика блокировки в Redis (`src/core/redis_client.py`)

- **Файл:** `backend/src/core/redis_client.py`
- **Задачи:**
  1. В `RedisLineQueue` добавить хелпер для получения блокировки планировщика таймаутов:
     ```python
     def get_timeouts_lock(self, ttl_seconds: int = 25) -> RedisDistributedLock:
         return RedisDistributedLock(
             redis=self.redis,
             key="lock:check_system_timeouts",
             ttl_seconds=ttl_seconds,
         )
     ```
  2. Проверить метод `requeue_ticket_front(line_code, ticket_id)` — убедиться в корректной работе `LPUSH queue:line:{line_code}`.

---

## Шаг 4. Бизнес-логика таймаутов в сервисе операторов (`src/operators/service.py`)

- **Файл:** `backend/src/operators/service.py`
- **Задачи:**
  1. Реализовать метод `check_timeouts(now: datetime | None = None) -> CheckTimeoutsResult`:
     - Параметр `now` (по умолчанию `datetime.now(settings.TIMEZONE)`) обеспечивает детерминированное тестирование.
     - **Блок 1: Неактивность у бота (10 минут):**
       - `bot_cutoff = now - timedelta(minutes=10)`
       - Выборка тикетов через `ticket_repo.get_inactive_bot_tickets(bot_cutoff)`.
       - Для каждого: вызов `ticket_repo.close_ticket_by_inactivity(ticket.id, bot_cutoff, now)`.
       - При успешном обновлении:
         * Добавить системное сообщение в БД: `await self.operator_repo.add_system_message(ticket.id, "Диалог завершен в связи с отсутствием активности.")`
         * Очистить контекст Redis: `await self.chat_context.clear_context(ticket.id)`
         * Опубликовать событие в Pub/Sub: `await self.ticket_events.publish_ticket_closed_inactivity(ticket.id)`
         * Инкрементировать счетчик `bot_tickets_closed`.
     - **Блок 2: Неактивность у оператора (10 минут напоминание, 15 минут закрытие):**
       - `warn_cutoff = now - timedelta(minutes=10)`
       - `close_cutoff_5m = now - timedelta(minutes=5)`
       - Выборка тикетов через `ticket_repo.get_in_progress_tickets_with_messages()`.
       - Для каждого определить последнюю реплику `last_message`:
         * **Сценарий 1 (Напоминание 10 минут):** Если последняя реплика — от оператора (`sender_type == 'operator'`) и `last_message.created_at <= warn_cutoff`:
           - Сохранить системное сообщение: `msg = await self.operator_repo.add_system_message(ticket.id, "Вы еще здесь?")`
           - Обновить `ticket.updated_at = now`
           - Опубликовать событие `new_message` в `channel:ticket:{ticket_id}` через `ticket_events.publish_new_message(ticket.id, ...)`
           - Инкрементировать `operator_warnings_sent`.
         * **Сценарий 2 (Закрытие 15 минут):** Если последняя реплика — системная с текстом напоминания («Вы еще здесь?») и `last_message.created_at <= close_cutoff_5m`:
           - Вызвать `ticket_repo.close_ticket_by_inactivity(ticket.id, close_cutoff_5m, now)`.
           - При успехе:
             * Очистить контекст Redis: `await self.chat_context.clear_context(ticket.id)`
             * Опубликовать `ticket_closed_inactivity` в `channel:ticket:{ticket_id}`
             * Если у тикета есть линия, поставить в очередь `dispatch_line_queue` для освободившегося слота (`trigger_reason="slot_freed"`)
             * Инкрементировать `operator_tickets_closed`.
     - **Блок 3: Контроль связи операторов (10 минут разрыва):**
       - `disconnect_cutoff = now - timedelta(minutes=10)`
       - Выборка операторов через `operator_repo.get_disconnected_operators(disconnect_cutoff)`.
       - Для каждого сотрудника:
         * Перевести статус в `offline`: `await self.operator_repo.set_operator_offline(op.user_id, now)`
         * Массово вернуть незавершенные тикеты: `requeued = await self.operator_repo.requeue_operator_tickets(op.user_id, now)`
         * Для каждого тикета: `await self.line_queue.requeue_ticket_front(ticket.line.code, ticket.id)`
         * Добавить код линии в `affected_lines.add(ticket.line.code)`
         * Инкрементировать `operators_marked_offline` и `tickets_requeued += len(requeued)`.
       - Для каждой линии в `affected_lines`:
         * Запустить задачу диспетчеризации: `await self._safe_dispatch_task(line_code, trigger_reason="operator_disconnected")` (ровно 1 вызов на линию!).
     - Закоммитить транзакцию: `await self.session.commit()`.
     - Вернуть `CheckTimeoutsResult(...)`.

---

## Шаг 5. Фоновая периодическая задача Taskiq (`src/operators/tasks.py`)

- **Файл:** `backend/src/operators/tasks.py`
- **Задачи:**
  1. Задекларировать периодическую задачу с интервалом 30 секунд:
     ```python
     @broker.task(
         task_name="check_system_timeouts",
         schedule=[{"interval": 30}],
     )
     async def check_system_timeouts() -> dict[str, Any]:
     ```
  2. Реализовать логику выполнения с распределенным локом:
     - Инициализировать Redis-клиент и `RedisDistributedLock(redis, "lock:check_system_timeouts", ttl_seconds=25)`.
     - `async with lock as acquired:`
       - Если `not acquired`: залогировать пропуск `"check_system_timeouts: лок уже занят другим воркером, пропуск"` и вернуть `{"status": "skipped", "reason": "lock_busy"}`.
       - Обернуть вызов в `asyncio.timeout(20.0)` для гарантированного завершения до истечения TTL лока.
       - Открыть сессию БД `async with async_session_maker() as session:`, инициализировать `OperatorService(session, redis)` и вызвать `await service.check_timeouts()`.
       - Вернуть словарь с результатами `CheckTimeoutsResult.model_dump()`.
     - Корректно закрыть клиент Redis в блоке `finally`.

---

## Шаг 6. Автоматические тесты (`tests/operators/test_timeouts_scheduler.py`)

- **Файл:** `backend/tests/operators/test_timeouts_scheduler.py`
- **Задачи:**
  1. Написать набор юнит- и интеграционных тестов с моками и временными сдвигами:
     - **Тест 1:** Неактивность бота: тикет старше 10 минут закрывается, шлется системное сообщение, контекст чистится, событие публикуется.
     - **Тест 2:** Активность бота: тикет младше 10 минут не закрывается.
     - **Тест 3:** Неактивность оператора: тикет с последним сообщением оператора старше 10 минут получает ровно одно напоминание «Вы еще здесь?».
     - **Тест 4:** Идемпотентность напоминания: тикет, где последнее сообщение уже системное «Вы еще здесь?», не получает спам-сообщений на следующем такте.
     - **Тест 5:** Закрытие тикета у оператора: тикет с системным напоминанием старше 5 минут переводится в `closed_by_inactivity`, освобождается слот, инициируется диспетчеризация.
     - **Тест 6:** Отключение оператора: оператор с `disconnected_at` старше 10 минут переводится в `offline`, тикеты переходят в `queued` и помещаются в начало очереди линии в Redis, запускается `dispatch_line_queue`.
     - **Тест 7:** Оператор с `disconnected_at` младше 10 минут не переводится в `offline`.
     - **Тест 8:** Распределенный лок: если лок в Redis уже взят, задача `check_system_timeouts` возвращает `skipped/lock_busy` без вызова сервиса.
     - **Тест 9:** Гонка с клиентом: если клиент обновил тикет, оптимистический UPDATE вернет `False`, тикет не будет ошибочно закрыт.
  2. Запустить все тесты через `uv run pytest tests/operators/test_timeouts_scheduler.py`.
  3. Проверить форматирование и линтер: `uv run ruff check src/ tests/`.

---

## Шаг 7. Обновление RoadMap

- **Файл:** `docs/HACKATHON_ROADMAP.md`
- **Задачи:**
  - Отметить выполненные чекбоксы задачи `HIGH-12`:
    - [x] Реализована централизованная периодическая задача `check_system_timeouts` с запуском каждые 30 секунд.
    - [x] Закрываются тикеты при неактивности клиента у бота (10 минут) со статусом `closed_by_inactivity`.
    - [x] Отправляется предупреждение и закрывается тикет при неактивности клиента у оператора (10 и 15 минут).
    - [x] В блоке `finally` обработчика SSE фиксируется отметка времени обрыва связи оператора `disconnected_at`.
    - [x] При отсутствии связи оператора более 10 минут статус переводится в `offline`, а тикеты возвращаются в начало очереди линии.
