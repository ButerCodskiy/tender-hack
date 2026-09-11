# Сессия «Grill Me»: Краевые случаи и анализ отказов архитектуры SSE (HIGH-11)

> **Статус:** Обновлено с учетом ревью архитектуры  
> **Контекст:** Реализация постоянных асинхронных каналов SSE для клиентов и операторов с шиной Redis Pub/Sub.

---

## Вопрос 1. Client Disconnect Detection (Детекция закрытия вкладки клиентом)

### Проблема:
Если клиент внезапно закрывает вкладку браузера, рвет Wi-Fi или убивает процесс браузера, TCP-соединение разрывается (отправляется TCP FIN/RST либо сокет молча «умирает»). Если асинхронный генератор бэкенда заблокирован на ожидании сообщений из Redis, поток рискует зависнуть навсегда, превратившись в процесс-зомби с утечкой памяти и соединения с Redis.

### Как именно генератор FastAPI/Starlette узнает о разрыве?
1. **Уровень ASGI-сервера (Uvicorn):**
   - Uvicorn слушает ASGI `receive`-канал. При закрытии сокета клиентом Uvicorn отправляет ASGI-событие `{"type": "http.disconnect"}`.
   - Во время выполнения `StreamingResponse` Uvicorn отслеживает это событие. Если стриминг активен, Uvicorn генерирует отмену фоновой корутины (`asyncio.CancelledError`).
2. **Уровень Starlette `request.is_disconnected()`:**
   - Внутри FastAPI объект `Request` имеет метод `await request.is_disconnected()`. Он проверяет статус ASGI-канала.
   - Однако если генератор находится в блокирующем вызове `await pubsub.get_message(...)` с бесконечным таймаутом, корутина не получит управление для проверки этого флага до прихода сообщения.
3. **Уровень сокета при `yield`:**
   - Если генератор пытается выполнить `yield chunk` в закрытый сокет, Starlette перехватывает ошибку записи (`ClientDisconnect`, `BrokenPipeError`, `ConnectionResetError`) и принудительно завершает генератор.

### Инженерное решение в коде:
- Использовать **цикл опроса с коротким таймаутом** (`timeout=1.0` в `pubsub.get_message`):
  ```python
  try:
      while True:
          # 1. Явная проверка отключения на каждой итерации
          if await request.is_disconnected():
              logger.info("Клиент разорвал соединение (is_disconnected)")
              break

          # 2. Неблокирующее чтение из Pub/Sub с таймаутом 1 секунда
          raw_message = await pubsub.get_message(
              ignore_subscribe_messages=True,
              timeout=1.0,
          )
          if raw_message is not None:
              data = format_sse_event(raw_message)
              yield data
              last_activity = asyncio.get_event_loop().time()
          else:
              # 3. Отправка heartbeat раз в 15 секунд при простое
              now = asyncio.get_event_loop().time()
              if now - last_activity >= 15.0:
                  yield ": ping\n\n"
                  last_activity = now
  except asyncio.CancelledError:
      logger.info("SSE-поток отменен сервером (CancelledError)")
      raise
  finally:
      # 4. Защита от отмены в finally через asyncio.shield
      await asyncio.shield(cleanup_pubsub(pubsub, channel_name))
  ```

---

## Вопрос 2. Жизненный цикл смены оператора (`disconnected_at`) и мульти-вкладки

### Проблема наивного решения:
Если оператор открывает АРМ в двух вкладках или перезагружает страницу (F5), наивное выставление `disconnected_at` в блоке `finally` сделает оператора «отключенным» в PostgreSQL при закрытии любой первой вкладки, хотя вторая вкладка остается активной.

### Архитектурное решение: Счетчик соединений в Redis:
1. **Ключ счетчика:** `operator:connections:{operator_id}` в Redis.
2. **При подключении к `GET /api/v1/operators/events`:**
   - Инкрементируем счетчик: `count = await redis.incr(f"operator:connections:{operator_id}")`.
   - Если статус смены оператора равен `active` или `break`:
     - Сбрасываем `disconnected_at = None` в PostgreSQL.
   - Если статус смены `offline`, `disconnected_at` не трогаем и статус смены не меняем (оператор сам должен нажать «Начать смену»).
3. **При разрыве соединения в блоке `finally`:**
   - Декрементируем счетчик: `count = await redis.decr(f"operator:connections:{operator_id}")`.
   - Если `count <= 0`:
     - Страхуемся от отрицательных чисел: сбрасываем ключ в 0 или удаляем.
     - **Только в этом случае** фиксируем разрыв связи в PostgreSQL:
       `disconnected_at = datetime.now(settings.TIMEZONE)`.
   - Обязательно оборачиваем операции в `finally` в `await asyncio.shield(...)` и изолированную сессию `async with async_session_maker() as session:`, так как при `asyncio.CancelledError` стандартный вызов упадет.

---

## Вопрос 3. Маршрутизация каналов клиента (Строго `channel:ticket:{ticket_id}`)

### Правило спецификации:
В системе **НЕ существует** канала `channel:chat:{chat_id}`. Все сервисы (`chat/service.py`, `operators/service.py`) публикуют события строго в каналы тикетов: `channel:ticket:{ticket_id}`.

### Логика эндпоинта `GET /api/v1/chat/events`:
1. **Клиент передал `ticket_id` явно:**
   - Проверяем существование тикета и его принадлежность текущему клиенту (`ticket.chat.client_id == current_user.id`).
   - Если тикет не принадлежит клиенту $\rightarrow$ `403 Forbidden`.
   - Если тикет не найден $\rightarrow$ `404 Not Found`.
   - Подписываемся на `channel:ticket:{ticket_id}`.
2. **Клиент не передал `ticket_id`:**
   - Находим постоянный чат клиента: `chat = await chat_repo.get_by_client_id(current_user.id)`.
   - Ищем активный тикет: `active_ticket = await ticket_repo.get_active_by_chat_id(chat.id)`.
   - **Если активного тикета нет:**
     - Возвращаем `404 Not Found` с телом:
       `{"detail": {"code": "no_active_ticket", "message": "Активное обращение не найдено. Начните диалог через отправку сообщения."}}`.
     - Никаких пустых подписок на фиктивные каналы не создается.
3. **Перевод тикета на другую линию (`ticket_transferred`):**
   - Идентификатор обращения `ticket_id` **НЕ МЕНЯЕТСЯ**.
   - Событие `ticket_transferred` публикуется в тот же канал `channel:ticket:{ticket_id}`.
   - Клиент получает событие штатно без переподключения.

---

## Вопрос 4. Защита пула соединений Redis

### Решение:
- Не создаем параллельных пулов в `app.state.redis_pubsub` и не меняем базовую инициализацию `main.py`.
- Используем существующий клиент Redis из `request.app.state.redis`.
- Защита пула строится на:
  1. Обязательном вызове `await asyncio.shield(pubsub.unsubscribe(channel))` и `await asyncio.shield(pubsub.close())` в блоке `finally`.
  2. Циклической проверке `await request.is_disconnected()` каждую секунду, исключающей зависание сокетов.

---

## Вопрос 5. Backpressure и защита от `asyncio.CancelledError` в `finally`

1. **Защита `finally` через `asyncio.shield`:**
   - Когда Starlette/Uvicorn обнаруживает разрыв соединения, в корутину генератора прилетает `asyncio.CancelledError`.
   - Любая асинхронная операция ввода-вывода внутри `finally` (коммит в БД, декремент в Redis, закрытие pubsub) без `asyncio.shield` будет мгновенно отменена, что приведет к повреждению состояния и `CancelledError`.
   - **Все финализирующие I/O-операции оборачиваются в `asyncio.shield`**:
     ```python
     finally:
         await asyncio.shield(self._safe_cleanup(...))
     ```
2. **Backpressure:**
   - Регулируется сетевым буфером сокета и стандартным лимитом Redis `client-output-buffer-limit pubsub`.
   - При разрыве сокета генератор ловит `ClientDisconnect` и немедленно переходит в `finally`.
