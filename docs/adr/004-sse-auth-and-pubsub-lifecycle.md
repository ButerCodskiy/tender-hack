# ADR 004: Аутентификация SSE-соединений и управление жизненным циклом Redis Pub/Sub

* **Статус:** Принято
* **Дата:** 2026-09-10
* **Домен:** `backend/src/api/`, `backend/src/chat/`, `backend/src/operators/`, `backend/src/core/`
* **Спецификации:** [docs/API_SPECIFICATION.md](../API_SPECIFICATION.md) (§3.3, §4.7), [docs/BACKEND_ARCHITECTURE.md](../BACKEND_ARCHITECTURE.md), [docs/QUEUES_SPECIFICATION.md](../QUEUES_SPECIFICATION.md), [docs/DATABASE_SPECIFICATION.md](../DATABASE_SPECIFICATION.md)

---

## 1. Контекст

В рамках задачи HIGH-11 реализуются два постоянных канала асинхронных событий по протоколу Server-Sent Events (SSE, `text/event-stream`):
1. **Клиентский канал:** `GET /api/v1/chat/events` — доставка событий изменения состояния обращения (`operator_joined`, `new_message`, `ticket_resolved`, `ticket_closed_inactivity`).
2. **Операторский канал:** `GET /api/v1/operators/events` — доставка уведомлений АРМ специалиста (`ticket_assigned`, `client_message`, `copilot_ready`).

Шиной доставки событий реального времени выступает Redis Pub/Sub с каналами `channel:ticket:{ticket_id}` и `channel:operator:{operator_id}`.

В ходе архитектурной разведки выявлены три критические проблемы:
1. **Ограничение Web API EventSource:** Стандартный браузерный интерфейс `EventSource` (W3C) не поддерживает передачу кастомных HTTP-заголовков (включая `Authorization: Bearer <token>`). Существующая зависимость `get_current_user` принимает токен исключительно из заголовка, что делает прямое подключение из браузера невозможным.
2. **Таймауты промежуточных прокси:** Обратные прокси-серверы (Nginx, Traefik, балансировщики облака) принудительно разрывают неактивные HTTP/SSE-соединения по idle-таймаутам (обычно 60–120 секунд), если в сокет не поступают байты данных.
3. **Утечки соединений Redis Pub/Sub:** Механизм подписки Redis переводит сокет в постоянный блокирующий режим слушателя. При неконтролируемом закрытии соединения клиентом (закрытие вкладки браузера, сбой сети) без явного вызова `pubsub.unsubscribe()` и `pubsub.close()` происходит быстрая утечка пула соединений Redis и деградация всей системы.

---

## 2. Решение

### 2.1. Аутентификация SSE-соединений (Query Parameter Fallback)
1. Для эндпоинтов SSE вводится специализированная зависимость аутентификации `get_current_user_sse`:
   - Первично проверяется стандартный заголовок `Authorization: Bearer <token>`.
   - Если заголовок отсутствует, токен извлекается из query-параметра запроса: `?token=<access_token>`.
   - Токен валидируется тем же криптографическим механизмом `AuthService.get_user_by_token(..., expected_type=TokenType.ACCESS)`.
2. **Меры информационной безопасности:**
   - Query-параметр `token` запрещено выводить в серверные логи доступа (access logs). Middleware логирования обязана маскировать значение токена в строке запроса (`token=***`) либо логировать только относительный путь маршрута (`request.url.path`).
   - Срок жизни JWT access-токена ограничен конфигурацией (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). При истечении срока токена соединение разрывается со статусом `401 Unauthorized`.

### 2.2. Формат потока SSE и Heartbeat (Keep-Alive Ping)
1. Стриминг реализуется нативным `fastapi.responses.StreamingResponse` со стандартными заголовками:
   ```http
   Content-Type: text/event-stream
   Cache-Control: no-cache
   Connection: keep-alive
   X-Accel-Buffering: no
   ```
2. Для предотвращения сброса соединения прокси-серверами генератор событий каждые 15 секунд (интервал `settings.SSE_HEARTBEAT_INTERVAL_SECONDS = 15`) при отсутствии доменных событий отправляет SSE-комментарий:
   ```text
   : ping

   ```
   *Примечание:* По спецификации W3C SSE строки, начинающиеся с символа двоеточия `:`, являются комментариями, игнорируются клиентскими обработчиками `onmessage` и не вызывают ложных срабатываний бизнес-логики фронтенда.

### 2.3. Жизненный цикл соединений Redis Pub/Sub и обработка отключений
1. Каждый SSE-генератор изолирует контекст подписки:
   ```python
   pubsub = redis.pubsub()
   try:
       await pubsub.subscribe(channel_name)
       while True:
           if await request.is_disconnected():
               break
           message = await pubsub.get_message(
               ignore_subscribe_messages=True,
               timeout=1.0,
           )
           if message:
               yield format_sse_event(message)
           else:
               # проверка отправки heartbeat
               ...
   finally:
       await pubsub.unsubscribe(channel_name)
       await pubsub.close()
   ```
2. Опрос сообщений выполняется с неблокирующим таймаутом `timeout=1.0` с непрерывной проверкой `await request.is_disconnected()`.
3. Блок `finally` выполняется гарантированно как при штатном закрытии соединения, так и при исключении `asyncio.CancelledError`, порождаемом ASGI-сервером (Uvicorn) при закрытии сокета клиентом.

### 2.4. Фиксация разрыва связи оператора (`disconnected_at`)
1. При подключении оператора к `GET /api/v1/operators/events`:
   - Профиль оператора в PostgreSQL обновляется: `disconnected_at = None` (только если статус смены `active` или `break`).
   - Оператор немедленно становится доступным для назначения тикетов балансировщиком.
2. В блоке `finally` обработчика операторского стрима:
   - В отдельной транзакции базы данных фиксируется отметка времени обрыва: `disconnected_at = datetime.now(settings.TIMEZONE)`.
   - Балансировщик прекращает назначать новые тикеты оператору с `disconnected_at IS NOT NULL`.
   - Если оператор не переподключился в течение 10 минут, периодическая задача `check_system_timeouts` (HIGH-12) переведет статус в `offline` и вернет тикеты в очередь линии.

---

## 3. Последствия

### Положительные:
1. Полная совместимость со стандартным браузерным `new EventSource('/api/v1/chat/events?token=...')` без необходимости сторонних полифилов.
2. Гарантия защиты от утечек соединений Redis Pub/Sub за счет обязательной очистки в `finally`.
3. Прозрачная работа через любые балансировщики и обратные прокси за счет периодических `: ping\n\n`.
4. Надежный контроль доступности операторов на смене в режиме реального времени.

### Отрицательные / Риски:
1. Передача токена в URL может отражаться в сетевых прокси или логах браузера. Нивелируется использованием HTTPS и маскированием в логах бэкенда.
2. Каждое активное SSE-соединение занимает один Pub/Sub сокет Redis. Пул соединений Redis (`max_connections`) должен быть сконфигурирован с запасом под максимальную пиковую одновременную нагрузку (операторы + клиенты).
