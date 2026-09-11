# Context Map

Карта модулей, архитектурных областей и спецификаций проекта.

## Доменные модули системы (`backend/src/`)

### Бэкенд-обвязка
- **auth**: пользователи, роли, организации, JWT-токены.
  - Контекст: `backend/src/auth/CONTEXT.md`
  - Спецификации: [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md), [docs/DATABASE_SPECIFICATION.md](docs/DATABASE_SPECIFICATION.md)
- **chat**: входящие сообщения клиентов, фильтрация ненормативной лексики, стриминг SSE, оркестрация диалога.
  - Контекст: `backend/src/chat/CONTEXT.md`
  - Спецификации: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md), [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md)
- **operators**: АРМ оператора, балансировка очереди, распределение тикетов, смена.
  - Контекст: `backend/src/operators/CONTEXT.md`
  - Спецификации: [docs/QUEUES_SPECIFICATION.md](docs/QUEUES_SPECIFICATION.md), [docs/DATABASE_SPECIFICATION.md](docs/DATABASE_SPECIFICATION.md)
- **kb (бэк-офис)**: реестр регламентов, модерация пар вопрос-ответ (FAQ), API базы знаний.
  - Контекст: `backend/src/kb/CONTEXT.md`
  - Спецификации: [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md), [docs/DATABASE_SPECIFICATION.md](docs/DATABASE_SPECIFICATION.md)
- **analytics**: аудит качества, метрики SLA/CSAT, отчеты и дашборды.
  - Контекст: `backend/src/analytics/CONTEXT.md`
  - Спецификации: [docs/DATABASE_SPECIFICATION.md](docs/DATABASE_SPECIFICATION.md), [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md)

### RAG и парсинг
- **rag**: гибридный поиск, классификатор тем, реранкер, потоковая генерация ответа, сборка контекста оператора.
  - Контекст: `backend/src/rag/CONTEXT.md`
  - Спецификация: [docs/RAG_AND_PARSING_SPECIFICATION.md](docs/RAG_AND_PARSING_SPECIFICATION.md)
- **kb (парсер и чанкер)**: парсер PDF/DOCX регламентов, извлечение таблиц, нарезка текста на фрагменты.
  - Контекст: `backend/src/kb/CONTEXT.md`
  - Спецификация: [docs/RAG_AND_PARSING_SPECIFICATION.md](docs/RAG_AND_PARSING_SPECIFICATION.md)

## Общая архитектура и контракты
- **Требования и концепция**: [docs/task.md](docs/task.md), [docs/concept.md](docs/concept.md)
- **Архитектура бэкенда**: [docs/BACKEND_ARCHITECTURE.md](docs/BACKEND_ARCHITECTURE.md)
- **Схема потоков и структура**: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)
- **Очереди и задачи Taskiq**: [docs/QUEUES_SPECIFICATION.md](docs/QUEUES_SPECIFICATION.md)
- **База данных PostgreSQL**: [docs/DATABASE_SPECIFICATION.md](docs/DATABASE_SPECIFICATION.md)
- **Контракты API v1**: [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md)
- **Дорожная карта хакатона**: [docs/HACKATHON_ROADMAP.md](docs/HACKATHON_ROADMAP.md)
- **Архитектурные решения и изменения контрактов**: каталог `docs/adr/`
