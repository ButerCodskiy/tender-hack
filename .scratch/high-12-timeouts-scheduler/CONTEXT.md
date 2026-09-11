# Контекст и анализ архитектуры: Планировщик таймаутов и контроль связи операторов (HIGH-12)

Документ фиксирует результаты предпроектного анализа инфраструктуры Taskiq Scheduler, моделей тикетов и операторов, а также регламентов таймаутов согласно `QUEUES_SPECIFICATION.md` (§3, §4), `BACKEND_ARCHITECTURE.md` (§8) и `DATABASE_SPECIFICATION.md` (§2.4, §3.2).

---

## 1. Инфраструктура планировщика Taskiq Scheduler (`src/core/broker.py`)

### Текущее состояние:
- **Конфигурация брокера:** В `src/core/broker.py` инициализирован `ListQueueBroker(url=settings.REDIS_URL)` с бэкендом результатов `RedisAsyncResultBackend` и интеграцией зависимостей FastAPI `taskiq_fastapi.init(broker, "src.main:app")`.
- **Конфигурация планировщика:** Создан экземпляр `scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])`.
- **Механизм регистрации расписания:** 
  Используется `LabelScheduleSource(broker)`. Он сканирует зарегистрированные в брокере задачи и извлекает метки `schedule` из декоратора `@broker.task`.
  Поддерживает:
  - Интервалы: `schedule=[{"interval": 30}]` (целое число секунд или `timedelta`).
  - Cron-выражения: `schedule=[{"cron": "*/30 * * * * *"}]` (6-позиционный крон с секундами).
- **Контейнеризация в Docker Compose:**
  В `docker-compose.yml` сконфигурированы изолированные сервисы:
  - `worker`: `command: ["taskiq", "worker", "src.core.broker:broker", "--fs-discover"]`
  - `scheduler`: `command: ["taskiq", "scheduler", "src.core.broker:scheduler", "--fs-discover"]`
  Флаг `--fs-discover` обеспечивает автоматическое обнаружение задач в проекте при запуске.

---

## 2. Статус задачи `check_system_timeouts` (`src/operators/tasks.py`)

- **Текущее состояние:** Задача `check_system_timeouts` в кодовой базе **отсутствует** (в `src/operators/tasks.py` определена только задача `dispatch_line_queue`).
- **Требуемые параметры:**
  - Название задачи: `check_system_timeouts`.
  - Очередь: по умолчанию (или выделенная очередь).
  - Расписание: запуск каждые 30 секунд:
    `@broker.task(task_name="check_system_timeouts", schedule=[{"interval": 30}])`.
  - Поведение: захват распределенного лока в Redis, открытие сессии БД, вызов доменного метода `OperatorService.check_timeouts()`.

---

## 3. Анализ репозиториев (`TicketRepository` и `OperatorRepository`)

В текущей кодовой базе **нет ни одного специализированного метода** для выборки сущностей по условиям неактивности или массового возврата тикетов в очередь.

### 3.1. Неактивность клиента в диалоге с ботом (10 минут)
- **Спецификация:** `status = 'bot_processing' AND updated_at < now() - 10 minutes`.
- **Что требуется реализовать:**
  Метод в `TicketRepository` (или `OperatorRepository`):
  ```python
  async def get_inactive_bot_tickets(self, cutoff: datetime) -> list[TicketModel]
  ```
  Выборка тикетов со статусом `bot_processing`, у которых `updated_at < cutoff` (где `cutoff = datetime.now(settings.TIMEZONE) - timedelta(minutes=10)`).

### 3.2. Неактивность клиента в диалоге с оператором (10 и 15 минут)
- **Спецификация:** 
  - **Шаг 1 (предупреждение через 10 минут):** `status = 'in_progress'`, последнее сообщение было от оператора, его возраст > 10 минут, предупреждение («Вы еще здесь?») еще не отправлялось.
  - **Шаг 2 (закрытие через 15 минут суммарно):** после ответа оператора прошло $\ge 15$ минут (или после предупреждения прошло $\ge 5$ минут) без ответа клиента.
- **Что требуется реализовать:**
  Запрос для поиска тикетов в статусе `in_progress` с получением последнего сообщения (или временных меток сообщений оператора и клиента):
  - Определение последнего сообщения: через correlated subquery или оконную функцию `ROW_NUMBER() OVER (PARTITION BY ticket_id ORDER BY created_at DESC)`.
  - Либо метод выборки активных тикетов с подгрузкой последнего сообщения (`selectinload(TicketModel.messages)` с ограничением/сортировкой).

### 3.3. Контроль разрыва связи оператора (10 минут)
- **Спецификация:** `shift_status = 'active' AND disconnected_at IS NOT NULL AND disconnected_at < now() - 10 minutes`.
- **Что требуется реализовать:**
  Метод в `OperatorRepository`:
  ```python
  async def get_disconnected_operators(self, cutoff: datetime) -> list[OperatorProfileModel]
  ```
  Выборка операторов со статусом `active` (а также `break`), у которых `disconnected_at < cutoff`.

### 3.4. Массовый возврат тикетов оператора в очередь (`queued`)
- **Спецификация:** При фиксации таймаута связи оператора все его незавершенные тикеты (`assigned`, `in_progress`) должны быть отвязаны от сотрудника, переведены в статус `queued` и возвращены в начало очереди соответствующей линии (`LPUSH queue:line:{line_code}`).
- **Что требуется реализовать:**
  Метод в `OperatorRepository` (или `TicketRepository`):
  ```python
  async def requeue_operator_tickets(self, operator_id: UUID) -> list[TicketModel]
  ```
  Атомарно обновляет тикеты сотрудника:
  - `assigned_operator_id = None`
  - `assigned_at = None`
  - `opened_at = None`
  - `status = TicketStatus.QUEUED.value`
  - `updated_at = datetime.now(settings.TIMEZONE)`
  Возвращает список обновленных тикетов (с загруженным `line_id` / `line.code`) для последующего выталкивания в Redis и запуска диспетчеризации.

---

## 4. Состояние сервисного слоя (`src/operators/service.py`)

- **Текущее состояние:** Метод `check_timeouts()` в `OperatorService` **отсутствует**.
- **Что необходимо реализовать в `OperatorService.check_timeouts()`:**
  1. **Обработка неактивности у бота:**
     - Поиск тикетов `bot_processing` старше 10 минут.
     - Для каждого: перевод в `closed_by_inactivity`, установка `closed_at`, добавление системного сообщения, очистка `chat:context:{ticket_id}` в Redis, публикация события `ticket_closed_inactivity` в `channel:ticket:{ticket_id}`.
  2. **Обработка неактивности у оператора:**
     - Шаг 1: если последнее сообщение от оператора старше 10 минут и предупреждение еще не отправлялось — сохранение системного сообщения «Вы еще здесь?» в БД и публикация в Pub/Sub.
     - Шаг 2: если прошло 15 минут — перевод в `closed_by_inactivity`, установка `closed_at`, освобождение слота оператора, очистка `chat:context:{ticket_id}`, публикация события `ticket_closed_inactivity`, инициирование `dispatch_line_queue` для освободившегося слота.
  3. **Обработка отключенных операторов:**
     - Поиск операторов с `disconnected_at < now() - 10 min`.
     - Перевод статуса смены в `offline`, сброс `disconnected_at = None`.
     - Вызов `requeue_operator_tickets(operator_id)`.
     - Для каждого возвращенного тикета: `LPUSH queue:line:{line_code}` в Redis через `line_queue.requeue_ticket_front(...)`.
     - Запуск `dispatch_line_queue` для каждой затронутой линии.

---

## 5. Механизм распределенной блокировки (Distributed Lock)

- **Реализация в кодовой базе:** Класс `RedisDistributedLock` уже существует в `src/core/redis_client.py` (строка 159).
- **Принцип работы:**
  - Захват: `SET lock:check_system_timeouts {token} NX EX {ttl_seconds}`.
  - Освобождение: Lua-скрипт с проверкой совпадения токена владельца (`UNLOCK_LUA_SCRIPT`).
  - Поддерживает асинхронный контекстный менеджер `async with lock as acquired:`.
- **Параметры для `check_system_timeouts`:**
  - Ключ: `lock:check_system_timeouts`.
  - Время жизни (TTL): 25 секунд (гарантирует автоматическое снятие до следующего такта в 30 секунд, исключая наложение циклов при задержках или падении воркера).
  - Если `not acquired` — немедленный возврат без ошибок и повторных попыток.
