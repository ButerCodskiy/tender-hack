# 01: Модели диалогов, обращений, линий поддержки и базовые репозитории

**What to build:** Реализовать декларативные модели SQLAlchemy для обращений (`TicketModel`), сообщений (`MessageModel`) и источников (`MessageSourceModel`) в домене `chat` (согласно ADR 0002), а также линий поддержки (`SupportLineModel`) в домене `operators`. Настроить внешние ключи к пользователям, чатам и линиям поддержки. Создать репозитории `TicketRepository` и `ChatRepository` в `src/chat/repository.py`, а также `SupportLineRepository` в `src/operators/repository.py`. Реализовать базовый клиент Redis в `src/core/redis_client.py` для работы со скользящим окном контекста диалога (`chat:context:{ticket_id}`).

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] В `src/operators/models.py` реализована модель `SupportLineModel` (таблица `support_lines` со столбцами `id`, `code`, `name`, `description`, `is_active`).
- [x] В `src/chat/models.py` реализована модель `TicketModel` (таблица `tickets` со столбцами `id` UUID7, `chat_id`, `line_id`, `assigned_operator_id`, `priority`, `status`, `escalation_reason`, `transferred_from_operator_id`, `transfer_comment`, временными метками `created_at`, `assigned_at`, `opened_at`, `closed_at`, `updated_at`).
- [x] В `src/chat/models.py` реализована модель `MessageModel` (таблица `messages` со столбцами `id` UUID7, `ticket_id`, `sender_type`, `sender_id`, `text`, `moderation_status`, `moderation_reason`, `created_at`).
- [x] В `src/chat/models.py` реализована модель `MessageSourceModel` (таблица `message_sources` со столбцами `id` UUID7, `message_id`, `chunk_id`, `doc_id`, `quote_text`, `created_at`).
- [x] В `src/chat/repository.py` реализован `TicketRepository` с методами создания тикета, поиска активного тикета по `chat_id` (`status NOT IN ('resolved', 'closed_by_inactivity', 'closed_by_moderation', 'canceled')`) и поиска последнего завершенного тикета.
- [x] В `src/chat/repository.py` реализован `ChatRepository` с методами сохранения сообщений с источниками и выборки до 50 последних реплик чата с подгрузкой связанных источников.
- [x] В `src/operators/repository.py` реализован `SupportLineRepository` для получения информации о линиях поддержки.
- [x] В `src/core/redis_client.py` реализованы асинхронные методы добавления сообщения в скользящее окно `chat:context:{ticket_id}`, обрезки до 10 реплик (`LTRIM -10 -1`), продления времени жизни (`EXPIRE 1800`) и удаления ключа при закрытии обращения.
- [x] Реализованы автоматические тесты: создание сущностей, проверка внешних ключей, выборка истории диалога и работа методов оперативного контекста Redis.
