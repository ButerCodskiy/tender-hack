# Пошаговый план реализации: Постоянные каналы асинхронных событий для клиента и оператора (HIGH-11)

> **Статус:** Утвержден к реализации с учетом вердикта Grill Me  
> **Зона ответственности:** `backend/src/`, `backend/tests/`

---

## Шаг 1. Зависимость аутентификации для SSE (`src/api/dependencies.py`)

- **Файл:** `backend/src/api/dependencies.py`
- **Задачи:**
  1. Реализовать провайдер `get_current_user_sse`:
     - Принимает опциональные учетные данные из заголовка `credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer)`
     - Принимает опциональный query-параметр `token: str | None = Query(None, alias="token")`
     - Если передан заголовок `Bearer <token>` — извлекает токен из него.
     - Иначе если передан query-параметр `token` — берет его значение.
     - Если токен не найден ни в заголовке, ни в query-параметрах — возбуждает `HTTPException(status_code=401, detail={"code": "not_authenticated", ...})`.
     - Валидирует токен через `await auth_service.get_user_by_token(raw_token, expected_type=TokenType.ACCESS)`.
  2. Реализовать функцию проверки роли оператора `require_operator_user_sse`:
     - Вызывает `get_current_user_sse`.
     - Проверяет роль `operator`, `supervisor`, `admin`.
  3. Объявить аннотированные типы:
     - `CurrentUserSseDep = Annotated[UserModel, Depends(get_current_user_sse)]`
     - `CurrentOperatorSseDep = Annotated[UserModel, Depends(require_operator_user_sse)]`

---

## Шаг 2. Асинхронные генераторы подписки на Redis Pub/Sub и счетчик соединений (`src/core/redis_client.py`)

- **Файл:** `backend/src/core/redis_client.py`
- **Задачи:**
  1. В `RedisOperatorEvents`:
     - Добавить методы счетчика соединений:
       - `incr_operator_connections(operator_id: UUID | str) -> int`: `INCR operator:connections:{operator_id}`
       - `decr_operator_connections(operator_id: UUID | str) -> int`: `DECR operator:connections:{operator_id}`
     - Добавить методы публикации:
       - `publish_client_message(operator_id: UUID | str, data: dict | BaseModel) -> int`: событие `client_message`
       - `publish_copilot_ready(operator_id: UUID | str, data: dict | BaseModel) -> int`: событие `copilot_ready`
     - Реализовать асинхронный генератор `subscribe_operator_events(operator_id: UUID | str, request: Request | None = None)`:
       - Подписывается на `channel:operator:{operator_id}`.
       - В цикле с неблокирующим `pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)`:
         - Проверяет `if request and await request.is_disconnected(): break`.
         - При получении сообщения форматирует SSE `event: ...\ndata: ...\n\n`.
         - Каждые 15 секунд простоя отправляет `: ping\n\n`.
       - В `finally` под `await asyncio.shield(...)`:
         - `await pubsub.unsubscribe(channel)`.
         - `await pubsub.close()`.
  2. В `RedisTicketEvents`:
     - Добавить метод `publish_ticket_closed_inactivity(ticket_id: UUID | str, data: dict | BaseModel | None = None) -> int`: событие `ticket_closed_inactivity`
     - Реализовать асинхронный генератор `subscribe_ticket_events(ticket_id: UUID | str, request: Request | None = None)`:
       - Подписывается строго на `channel:ticket:{ticket_id}`.
       - Цикл вычитки с таймаутом 1 с, проверкой `request.is_disconnected()`, heartbeat `: ping\n\n` раз в 15 с.
       - В `finally` под `await asyncio.shield(...)`:
         - `await pubsub.unsubscribe(channel)`.
         - `await pubsub.close()`.

---

## Шаг 3. Методы фиксации связи в репозитории операторов (`src/operators/repository.py` и `service.py`)

- **Файлы:**
  - `backend/src/operators/repository.py`
  - `backend/src/operators/service.py`
- **Задачи:**
  1. В `OperatorRepository`:
     - Добавить метод `mark_connected(user_id: UUID) -> OperatorProfileModel | None`:
       - Находит профиль `profile = await self.get_by_user_id(user_id)`.
       - Если `profile` существует и его статус в `('active', 'break')`:
         `profile.disconnected_at = None`, `profile.updated_at = datetime.now(settings.TIMEZONE)`.
         `await self.session.flush()`.
     - Добавить метод `mark_disconnected(user_id: UUID) -> OperatorProfileModel | None`:
       - Находит профиль `profile = await self.get_by_user_id(user_id)`.
       - Если `profile` существует:
         `profile.disconnected_at = datetime.now(settings.TIMEZONE)`, `profile.updated_at = datetime.now(settings.TIMEZONE)`.
         `await self.session.flush()`.
  2. В `OperatorService`:
     - Метод `handle_operator_connect(operator_id: UUID) -> None`:
       - `await self.redis_events.incr_operator_connections(operator_id)`.
       - `await self.operator_repo.mark_connected(operator_id)`.
       - `await self.session.commit()`.
     - Метод `handle_operator_disconnect(operator_id: UUID) -> None`:
       - `remaining = await self.redis_events.decr_operator_connections(operator_id)`.
       - Если `remaining <= 0`:
         - В изолированной сессии БД `async with async_session_maker() as cleanup_session`:
           `repo = OperatorRepository(cleanup_session)`.
           `await repo.mark_disconnected(operator_id)`.
           `await cleanup_session.commit()`.
     - Асинхронный генератор `stream_operator_events(operator_id: UUID, request: Request)`:
       - Вызывает `handle_operator_connect`.
       - Делегирует чтение сообщений генератору `subscribe_operator_events`.
       - В блоке `finally` под `await asyncio.shield(self.handle_operator_disconnect(operator_id))`.

---

## Шаг 4. Реализация эндпоинта `GET /api/v1/chat/events` (`src/api/v1/chat.py` и `src/chat/service.py`)

- **Файлы:**
  - `backend/src/api/v1/chat.py`
  - `backend/src/chat/service.py`
- **Задачи:**
  1. В `ChatService` реализовать метод `stream_chat_events(user: UserModel, ticket_id: UUID | None, request: Request)`:
     - Находит чат клиента: `chat = await self.repo.get_by_client_id(user.id)`.
     - Если передан явный `ticket_id`:
       - Проверяет тикет: `ticket = await self.ticket_repo.get_by_id(ticket_id)`.
       - Если тикет не найден $\rightarrow$ `HTTPException(404, detail="Обращение не найдено")`.
       - Если `ticket.chat_id != chat.id` $\rightarrow$ `HTTPException(403, detail="Доступ к данному обращению запрещен")`.
       - Целевой тикет: `target_ticket_id = ticket.id`.
     - Иначе (если `ticket_id is None`):
       - Ищет активный тикет: `active_ticket = await self.ticket_repo.get_active_by_chat_id(chat.id)`.
       - Если активного тикета нет $\rightarrow$ `HTTPException(404, detail={"code": "no_active_ticket", "message": "Активное обращение не найдено"})`.
       - Целевой тикет: `target_ticket_id = active_ticket.id`.
     - Возвращает генератор `self.ticket_events.subscribe_ticket_events(target_ticket_id, request)`.
  2. В `backend/src/api/v1/chat.py` зарегистрировать эндпоинт `GET /api/v1/chat/events`:
     - Использует `CurrentUserSseDep`.
     - Принимает опциональный `ticket_id: UUID | None = Query(None)`.
     - Возвращает `StreamingResponse(service.stream_chat_events(...), media_type="text/event-stream")` с заголовками `Cache-Control`, `Connection`, `X-Accel-Buffering: no`.

---

## Шаг 5. Реализация эндпоинта `GET /api/v1/operators/events` (`src/api/v1/operators.py`)

- **Файлы:**
  - `backend/src/api/v1/operators.py`
- **Задачи:**
  1. В `backend/src/api/v1/operators.py` зарегистрировать эндпоинт `GET /api/v1/operators/events`:
     - Использует `CurrentOperatorSseDep`.
     - Вызывает `service.stream_operator_events(operator.id, request)`.
     - Возвращает `StreamingResponse(..., media_type="text/event-stream")` с антибуферизационными заголовками.

---

## Шаг 6. Тестирование и валидация

- **Файлы:**
  - `backend/tests/chat/test_chat_events_sse.py`
  - `backend/tests/operators/test_operator_events_sse.py`
- **Тест-кейсы:**
  1. Аутентификация SSE через заголовок `Authorization: Bearer` и через `?token=`.
  2. Отказ в доступе (401) при невалидном/отсутствующем токене.
  3. Клиентский стрим: получение 404 при отсутствии активного тикета; получение событий `operator_joined`, `new_message`, `ticket_resolved` при наличии тикета.
  4. Операторский стрим: сброс `disconnected_at` в `None` при подключении, инкремент счетчика.
  5. Мульти-вкладки оператора: открытие 2 соединений, закрытие 1 соединения — `disconnected_at` остается `None`. Закрытие последнего соединения — фиксация `disconnected_at`.
  6. Прогон `uv run pytest` для проверки регрессий.
