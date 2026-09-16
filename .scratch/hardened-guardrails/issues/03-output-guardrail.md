# Задача 03: Выходной барьер безопасности генерации

Status: resolved
Blocked by: none

## Описание
Разработать класс `OutputSafetyGuardrail` в `backend/src/chat/moderation.py`:
1. Экспресс-проверка текста, сгенерированного моделью, до отправки в стрим клиенту.
2. Подмена на институциональный безопасный дисклеймер при обнаружении запрещенных инструкций или принятия роли DAN.

## Результат
Реализован в `backend/src/chat/moderation.py` и интегрирован в `ChatService.process_client_message` (на этапе `RagDoneEventSchema`).
