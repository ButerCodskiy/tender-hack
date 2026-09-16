# Задача 02: Детектор структурных атак и Prompt Injections

Status: resolved
Blocked by: none

## Описание
Разработать класс `InjectionAttackDetector` в `backend/src/chat/moderation.py`:
1. Поиск структурных разделителей и управляющих тегов (`</system>`, `[INST]`, `[SYSTEM]`, `### Instruction:`).
2. Поиск команд отмены/сброса системного контекста (`ignore previous instructions`, `забудь все правила`, `act as DAN`, `unrestricted mode`).
3. Метод `check_injection(text: str) -> SafetyCheckResult`.

## Результат
Реализован в `backend/src/chat/moderation.py`. Покрыт 20 сценариями тестов (прямые и обфусцированные атаки). Время реакции < 0.2 мс.
