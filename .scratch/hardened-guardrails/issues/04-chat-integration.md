# Задача 04: Сквозная интеграция барьеров в сервис чата

Status: resolved
Blocked by: 01, 02, 03

## Описание
1. Интеграция L1 SensitiveTopicsGuardrail и L2 InjectionAttackDetector в `ChatService.process_client_message`.
2. Мгновенный институциональный отказ без вызова LLM и RAG при срабатывании защиты.
3. Интеграция L4 OutputSafetyGuardrail при обработке финального события генерации (`RagDoneEventSchema`).

## Результат
Интеграция выполнена в `backend/src/chat/service.py`. При срабатывании L1 или L2 генератор RAG не вызывается, клиенту через SSE стримятся институциональные сообщения об отказе.
