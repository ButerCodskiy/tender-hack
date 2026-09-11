# Контекст и архитектурный анализ задачи HIGH-11

> **Задача:** Постоянные каналы асинхронных событий для клиента и оператора (SSE + Redis Pub/Sub).  
> **Зона ответственности:** `backend/src/api/v1/chat.py`, `backend/src/api/v1/operators.py`, `backend/src/core/redis_client.py`, `backend/src/api/dependencies.py`, `backend/src/operators/repository.py`.  
> **Статус:** Анализ и разведка (READ-ONLY).

---

## 1. Анализ `backend/src/core/redis_client.py` (Redis Pub/Sub)

### 1.1. Наличие асинхронного генератора/хелпера для подписки (`subscribe`)
- **Статус:** ❌ **Отсутствует.**
- В текущем файле реализованы классы:
  - `RedisChatContext` (скользящее окно контекста через списки `chat:context:{ticket_id}`),
  - `RedisLineQueue` (очереди линий `queue:line:{line_code}`),
  - `RedisDistributedLock` (распределенные блокировки через SET NX EX и Lua-скрипт),
  - `RedisOperatorEvents` (публикация в `channel:operator:{operator_id}`),
  - `RedisTicketEvents` (публикация в `channel:ticket:{ticket_id}`).
- **Проблема:** Нет ни одного метода подписки (`subscribe`), асинхронного генератора сообщений или менеджера подписки с автоматической отпиской (`unsubscribe`) и закрытием соединения (`pubsub.close()`) при завершении стрима.
- Для реализации SSE потребуется разработать генератор/контекстный менеджер подписки (например, `listen_channel(channel_name)` или метод в `RedisTicketEvents` / `RedisOperatorEvents`), который берет `redis.pubsub()`, подписывается, в цикле вычитывает сообщения (`pubsub.listen()` или `pubsub.get_message()`) с таймаутом/heartbeat и в блоке `finally` гарантированно отписывается и закрывает PubSub-клиент.

### 1.2. Структура каналов и контракты сообщений
1. **Канал тикета:** `channel:ticket:{ticket_id}`
   - Управляется адаптером `RedisTicketEvents`.
   - Текущие методы публикации:
     - `publish_operator_joined(ticket_id, operator_name)` $\rightarrow$ `event: "operator_joined"`, data: `{"ticket_id": str, "operator_name": str}`
     - `publish_new_message(ticket_id, message_data)` $\rightarrow$ `event: "new_message"`, data: payload `MessageResponseSchema`
     - `publish_ticket_transferred(ticket_id, new_line_code, reason)` $\rightarrow$ `event: "ticket_transferred"`, data: `{"ticket_id": str, "new_line_code": str, "reason": str}`
     - `publish_ticket_resolved(ticket_id, operator_id, closed_at)` $\rightarrow$ `event: "ticket_resolved"`, data: `{"ticket_id": str, "operator_id": str | None, "closed_at": str}`
   - Согласно [API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §3.3 и [HACKATHON_ROADMAP.md](../../docs/HACKATHON_ROADMAP.md) также необходимо событие `ticket_closed_inactivity`.

2. **Канал оператора:** `channel:operator:{operator_id}`
   - Управляется адаптером `RedisOperatorEvents`.
   - Текущие методы публикации:
     - `publish_ticket_assigned(operator_id, data)` $\rightarrow$ `event: "ticket_assigned"`, data: payload схемы тикета
   - Согласно [API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §4.7 и [QUEUES_SPECIFICATION.md](../../docs/QUEUES_SPECIFICATION.md) в канал оператора также должны публиковаться:
     - `client_message` (сообщение клиента по активному тикету оператора),
     - `copilot_ready` (готовность подсказки Copilot от фонового воркера).
   - В текущем коде методов `publish_client_message` и `publish_copilot_ready` нет.

---

## 2. Анализ `backend/src/api/v1/chat.py` (Клиентский SSE-стрим)

### 2.1. Механизм стриминга SSE
- В проекте используется **нативный `fastapi.responses.StreamingResponse`**.
- Библиотека `sse_starlette` в зависимостях ([backend/pyproject.toml](../../backend/pyproject.toml)) **отсутствует** и не используется.
- В эндпоинте `POST /api/v1/chat/messages` стриминг ответов RAG организован через `StreamingResponse`:
  ```python
  return StreamingResponse(
      service.process_client_message(...),
      media_type="text/event-stream",
      headers={
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no",
      },
  )
  ```
- Форматирование SSE-сообщений реализовано напрямую в виде строк формата SSE:
  `f"event: {event_type}\ndata: {json_payload}\n\n"`

### 2.2. Заготовка эндпоинта `GET /api/v1/chat/events`
- **Статус:** ❌ **Отсутствует.**
- В [backend/src/api/v1/chat.py](../../backend/src/api/v1/chat.py) объявлены только два маршрута:
  - `GET /api/v1/chat` (`get_chat_state`),
  - `POST /api/v1/chat/messages` (`send_message`).
- Маршрут `GET /api/v1/chat/events` потребуется создать с нуля.
- Потребуется определить, к какому тикету/каналу подключается клиент:
  - У клиента один постоянный чат (`ChatModel`), и в каждый момент времени может быть активный тикет (`active_ticket`), либо обращение создается при старте.
  - Если активного тикета нет или он закрыт, клиент должен либо ждать подключения/событий, либо слушать канал своего активного тикета с периодической отправкой SSE-комментариев (`: keep-alive\n\n`) для предотвращения закрытия соединения промежуточными прокси/nginx.

---

## 3. Анализ `backend/src/api/v1/operators.py` (Операторский SSE-стрим)

### 3.1. Заготовка эндпоинта `GET /api/v1/operators/events`
- **Статус:** ❌ **Отсутствует.**
- В [backend/src/api/v1/operators.py](../../backend/src/api/v1/operators.py) присутствуют:
  - `GET /me/shift`, `PATCH /me/shift`,
  - `GET /tickets`,
  - `POST /tickets/{ticket_id}/open`,
  - `POST /tickets/{ticket_id}/messages`,
  - `POST /tickets/{ticket_id}/transfer`,
  - `POST /tickets/{ticket_id}/resolve`.
- Маршрут `GET /api/v1/operators/events` отсутствует.
- Согласно [API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §4.7 и [HACKATHON_ROADMAP.md](../../docs/HACKATHON_ROADMAP.md), оператор подключается к персональному каналу `channel:operator:{operator_id}` и ожидает событий: `ticket_assigned`, `client_message`, `copilot_ready`.

---

## 4. Анализ `backend/src/api/dependencies.py` (Аутентификация для SSE)

### 4.1. Извлечение пользователя и поддержка EventSource
- **Текущая реализация:**
  ```python
  http_bearer = HTTPBearer(auto_error=False)

  async def get_current_user(
      credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
      auth_service: AuthServiceDep,
  ) -> UserModel:
      if credentials is None or credentials.scheme.lower() != "bearer":
          raise HTTPException(status_code=401, detail={"code": "not_authenticated", ...})
      return await auth_service.get_user_by_token(credentials.credentials)
  ```
- **Проблема для браузера:**
  - Браузерный стандартный API `EventSource` **не умеет передавать кастомные HTTP-заголовки** (в том числе `Authorization: Bearer <token>`).
  - `EventSource` в веб-приложениях передает токен либо через **Query Parameter** (например, `/api/v1/chat/events?token=<access_token>`), либо через **Cookie**.
  - На текущий момент `get_current_user` и `require_operator_user` принимают токен **строго из заголовка `Authorization`**. Query parameter `?token=` и cookie **не поддерживаются**.
- **Требуемое решение:**
  - Доработать зависимость аутентификации (или сделать специализированную зависимость `get_current_user_from_query_or_header` / расширить `get_current_user`), чтобы при отсутствии `credentials` из `HTTPBearer` выполнялась попытка извлечь токен из `Query(None, alias="token")`.

---

## 5. Анализ `backend/src/operators/models.py` и `repository.py` (Фиксация разрыва связи)

### 5.1. Поле `disconnected_at` в `OperatorProfileModel`
- **Статус:** ✅ **Присутствует.**
- В [backend/src/operators/models.py](../../backend/src/operators/models.py#L99-L102):
  ```python
  disconnected_at: Mapped[datetime | None] = mapped_column(
      DateTime(timezone=True),
      nullable=True,
  )
  ```
- Поле уже используется в фильтрах балансировщика:
  - `get_active_by_line`: `OperatorProfileModel.disconnected_at.is_(None)`
  - `get_least_loaded_active_for_update`: `OperatorProfileModel.disconnected_at.is_(None)`

### 5.2. Поддержка в `OperatorRepository`
- **Статус:** ⚠️ **Косвенная (специальных методов нет).**
- В [backend/src/operators/repository.py](../../backend/src/operators/repository.py) нет выделенных методов вроде `mark_disconnected(operator_id)` и `mark_connected(operator_id)`.
- Есть универсальный метод `update(profile)`.
- Для фиксации подключения и отключения оператора в SSE (в блоках `try` / `finally` генератора ответа) целесообразно добавить методы:
  - `mark_connected(user_id: UUID)`: `disconnected_at = None`,
  - `mark_disconnected(user_id: UUID)`: `disconnected_at = datetime.now(settings.TIMEZONE)`.

---

## 6. Итоговое резюме перед реализацией HIGH-11

| Компонент | Текущее состояние | Что необходимо реализовать |
|---|---|---|
| **SSE-механизм** | Нативный `StreamingResponse` (`text/event-stream`) | Использовать `StreamingResponse` и строковый формат SSE |
| **Redis Pub/Sub** | Только методы `publish_*` в `redis_client.py` | Реализовать хелпер/генератор безопасной подписки и чтения сообщений (`listen`/`subscribe`) с гарантированной отпиской в `finally` |
| **Клиентский SSE (`GET /chat/events`)** | Отсутствует | Создать эндпоинт, получение активного тикета клиента, стриминг из `channel:ticket:{ticket_id}`, keep-alive пинги |
| **Операторский SSE (`GET /operators/events`)** | Отсутствует | Создать эндпоинт, стриминг из `channel:operator:{operator_id}`, отметка `disconnected_at = None` при подключении и фиксация времени обрыва в `finally` |
| **Аутентификация для EventSource** | Только `Authorization: Bearer` | Добавить поддержку извлечения токена из `?token=` query param для совместимости со стандартным браузерным `EventSource` |
| **Модель и репозиторий оператора** | Поле `disconnected_at` есть; явных методов в репозитории нет | Добавить методы установки/сброса `disconnected_at` в `OperatorRepository` / `OperatorService` |
