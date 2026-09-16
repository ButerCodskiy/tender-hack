# Задача 06: Жизненный цикл инцидентов безопасности при повторных атаках

Status: resolved
Blocked by: 05

## Описание
Реализовать обработку повторных атак согласно разделу 4 ADR:
1. При первой атаке:
   - Сообщение пользователя сохраняется со статусом `MessageModerationStatus.FLAGGED` и указанием причины нарушения (`moderation_reason`).
   - Инкрементируется счетчик нарушений в рамках сессии/тикета (`chat:violations:{ticket_id}` в Redis или подсчет в БД).
   - Возвращается предупреждающий институциональный отказ, сессия продолжается.
2. При повторной атаке (>= 2 нарушений в одном обращении подряд):
   - Сообщение пользователя сохраняется со статусом `MessageModerationStatus.BLOCKED`.
   - Обращение переводится в терминальный статус `TicketStatus.CLOSED_BY_MODERATION` с `escalation_reason="security_incident"`.
   - Очищается контекст Redis (`redis_context.clear_context`).
   - Публикуются события завершения сессии в Pub/Sub (`publish_session_terminated`).
   - Отправляется задача на аудит инцидента безопасности `_safe_enqueue_audit(ticket_id, "security_incident")`.
   - В поток отдается институциональный отказ `INSTITUTIONAL_REPEAT_VIOLATION_REFUSAL` и SSE-событие `session_terminated`.

## Результат
Реализовано в `backend/src/chat/service.py`, `backend/src/chat/moderation.py`, `backend/src/core/redis_client.py`.
Покрыто сквозными тестами в `test_repeat_attacks_security_incident_lifecycle` и `test_redis_chat_context_violations` в `backend/tests/chat/test_safety_guardrails.py`.
Все 88 тестов успешно пройдены (100%).
