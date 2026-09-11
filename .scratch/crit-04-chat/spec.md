# Спецификация: [CRIT-04] Модели диалогов, обращений и главный оркестратор сообщений

## 1. Цель
Реализовать доменный контур клиентского чата и обращений в соответствии со спецификацией API (`docs/API_SPECIFICATION.md`), схемой базы данных (`docs/DATABASE_SPECIFICATION.md`) и архитектурой бэкенда (`docs/BACKEND_ARCHITECTURE.md`). Обеспечить хранение истории сообщений, управление жизненным циклом обращений, буферизацию контекста диалога в Redis и потоковую отдачу ответов поискового ядра через Server-Sent Events (SSE).

## 2. Основные требования

### 2.1. Модели данных и связи (PostgreSQL)
1. **Справочник линий поддержки (`support_lines` / `SupportLineModel`):**
   * Размещается в `src/operators/models.py`.
   * Первичный ключ `id` (`SmallInteger` / `SMALLSERIAL`).
   * Уникальный системный код `code` (`L1`, `L2`, `L3`), наименование, описание и флаг активности `is_active`.
2. **Реестр обращений (`tickets` / `TicketModel`):**
   * Размещается в `src/chat/models.py` в соответствии с ADR 0002.
   * Первичный ключ `id` (`UUID` версии 7).
   * Внешние ключи к `chats.id`, `support_lines.id` (опционально) и `users.id` (назначенный оператор, опционально).
   * Статусы жизненного цикла: `bot_processing`, `queued`, `assigned`, `in_progress`, `resolved`, `closed_by_inactivity`, `closed_by_moderation`, `canceled`.
   * Приоритет: `P0`, `P1`, `P2` (по умолчанию `P2`).
   * Временные метки: `created_at`, `assigned_at`, `opened_at`, `closed_at`, `updated_at`.
3. **Реестр сообщений (`messages` / `MessageModel`):**
   * Размещается в `src/chat/models.py`.
   * Первичный ключ `id` (`UUID` версии 7).
   * Внешний ключ к `tickets.id` с каскадным удалением.
   * Тип автора `sender_type`: `client`, `bot`, `operator`, `system`.
   * Идентификатор автора `sender_id` (опционально, внешний ключ к `users.id`).
   * Текст сообщения `text` и статус проверки `moderation_status`: `passed`, `flagged`, `blocked`.
   * Метка времени фиксации `created_at`.
4. **Таблица нормативных источников (`message_sources` / `MessageSourceModel`):**
   * Размещается в `src/chat/models.py`.
   * Первичный ключ `id` (`UUID` версии 7).
   * Внешний ключ к `messages.id` с каскадным удалением.
   * Идентификаторы фрагмента (`chunk_id`), документа (`doc_id`) и цитируемый фрагмент (`quote_text`).

### 2.2. Оперативный контекст диалога (Redis)
1. Буферизация скользящего окна реплик активного обращения по ключу `chat:context:{ticket_id}`.
2. Добавление каждой реплики в конец списка (`RPUSH`), обрезка до 10 последних сообщений (`LTRIM -10 -1`) и установка времени жизни 1800 секунд (`EXPIRE 1800`).

### 2.3. Потоковый оркестратор и маршруты API v1
1. **Маршрут `GET /api/v1/chat`:**
   * Получение текущего состояния ленты: идентификатор чата, краткая сводка активного обращения (`ActiveTicketSummarySchema`), до 50 последних сообщений с источниками и флаги доступных действий (`can_escalate`, `can_cancel`, `can_feedback`, `feedback_ticket_id`).
   * Защита маршрута через `CurrentUserDep`.
2. **Маршрут `POST /api/v1/chat/messages`:**
   * Прием входящего сообщения клиента (`ClientSendMessageRequestSchema`).
   * Оркестрация через `ChatService.process_client_message`: поиск или создание активного тикета со статусом `bot_processing`, сохранение реплики клиента в PostgreSQL и Redis.
   * Потоковая отдача ответа клиенту по протоколу Server-Sent Events (`text/event-stream`) с событиями `status`, `sources`, `sentence`, `done`.
   * Фиксация сформированного ответа бота и источников в PostgreSQL и Redis по завершении генерации.

## 3. Декомпозиция задач (Issues)
- [01: Модели диалогов, обращений, линий поддержки и базовые репозитории](issues/01-chat-and-ticket-models-repository.md)
- [02: Эндпоинт текущего состояния переписки и истории клиента](issues/02-chat-state-feed.md)
- [03: Главный оркестратор сообщений и потоковый эндпоинт отправки с SSE](issues/03-message-streaming-orchestrator.md)
