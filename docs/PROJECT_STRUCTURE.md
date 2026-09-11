# Архитектурная структура проекта и схема сквозного взаимодействия

Документ описывает структуру каталогов бэкенда и правила взаимодействия между компонентами при сквозном прохождении пользовательских запросов.

---

## 1. Главная проблема и принцип её решения

### В чём риск
Если доменные модули будут напрямую вызывать друг друга по кругу (`chat` вызывает `operators`, `operators` вызывает `chat`, а внутри них дергается `rag`), в коде возникнут циклические импорты и жесткая связность. При первой же правке логики проект превратится в запутанный клубок.

### Архитектурный принцип: Оркестровка без циклических связей
Каждый входящий сценарий управляется одним конкретным координатором (оркестратором). 
* Нижние слои ничего не знают о тех, кто находится выше.
* Модуль поиска не знает о существовании веб-чатов и пользователей: он лишь принимает текст и возвращает найденные данные.
* Модуль очередей операторов не знает о деталях работы нейросетей: он лишь принимает готовый тикет и распределяет его по свободным слотам.
* Сквозной сценарий собирается в сервисе обработки сообщений (внутри домена диалогов) по строгому линейному конвейеру.

---

## 2. Структура проекта

```text
ai-hack/
├── .dockerignore
├── .gitignore
├── README.md
├── AGENTS.md                  # Правила работы с кодовой базой
├── CONTEXT-MAP.md             # Карта модулей проекта
├── docker-compose.yml         # Сервисы: бэкенд, PostgreSQL, Redis, Qdrant
├── .scratch/                  # Задачи и спецификации веток
│   └── <feature>/issues/
├── docs/                      # Документация и спецификации
│   └── adr/                   # Архитектурные решения
├── frontend/                  # Клиентский чат, АРМ оператора, дашборд
└── backend/
    ├── Dockerfile
    ├── pyproject.toml
    ├── uv.lock
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py             # Регистрация моделей для автогенерации
    │   └── versions/          # Миграции структуры БД
    ├── tests/
    │   ├── unit/
    │   └── integration/
    └── src/
        ├── api/               # Транспортный HTTP-слой
        │   ├── dependencies.py # Зависимости FastAPI: SessionDep, CurrentUserDep, фабрики сервисов
        │   └── v1/
        │       ├── auth.py    # Аутентификация и пользователи
        │       ├── chat.py    # Клиентский чат и стриминг SSE
        │       ├── operators.py # АРМ оператора и смена
        │       ├── kb.py      # Управление базой знаний
        │       ├── analytics.py # Дашборды и отчеты
        │       └── router.py  # Корневой роутер API v1
        ├── db/
        │   └── database.py    # DeclarativeBase, сессии, движок
        ├── core/              # Базовая инфраструктура
        │   ├── config.py      # Настройки pydantic-settings
        │   ├── broker.py      # Брокер и планировщик Taskiq
        │   ├── redis_client.py # Клиент Redis (RedisClient)
        │   ├── qdrant_client.py # Клиент хранилища векторов QdrantClient
        │   ├── llm_client.py   # Клиент языковых моделей и эмбеддингов LlmClient
        │   ├── security.py    # Хеширование и JWT-токены
        │   └── exceptions.py  # Доменные исключения
        ├── auth/              # Пользователи и профили
        │   ├── models.py      # UserModel, OrganizationModel
        │   ├── schemas.py     # Схемы валидации Auth
        │   ├── repository.py  # Слой доступа к БД
        │   └── service.py     # Бизнес-логика AuthService
        ├── chat/              # Диалоги клиентов
        │   ├── models.py      # ChatModel, MessageModel
        │   ├── schemas.py     # Схемы сообщений
        │   ├── repository.py  # ChatRepository
        │   ├── moderation.py  # Фильтр обсценной лексики
        │   └── service.py     # Оркестратор диалога ChatService
        ├── operators/         # Обращения и операторы
        │   ├── models.py      # TicketModel, SupportLineModel, TicketCopilotSummaryModel
        │   ├── schemas.py     # Схемы карточек и очередей
        │   ├── repository.py  # OperatorRepository
        │   ├── balancer.py    # Балансировщик слотов FIFO
        │   ├── service.py     # OperatorService
        │   └── tasks.py       # Задачи: dispatch_line_queue
        ├── rag/               # Поисковое и генеративное ядро
        │   ├── schemas.py     # Схемы поиска и ответов
        │   ├── retriever.py   # Гибридный двухканальный поиск
        │   ├── reranker.py    # Ранжирование кандидатов
        │   ├── router.py      # Классификатор тем и линий
        │   ├── generator.py   # Потоковая генерация ответа
        │   ├── copilot.py     # Сборка подсказки оператору
        │   ├── service.py     # Фасад RagService
        │   └── tasks.py       # Фоновая задача copilot summary
        ├── kb/                # База знаний, регламенты и утверждение черновиков FAQ
        │   ├── models.py      # KbDocumentModel, KbNodeModel, KbChunk, FaqModerationQueueModel
        │   ├── schemas.py     # Схемы загрузки, узлов и черновиков
        │   ├── repository.py  # KbRepository
        │   ├── service.py     # Оркестратор базы знаний KbService
        │   ├── tasks.py       # Фоновые задачи: index_kb_document, enrich_kb_chunks
        │   ├── parser.py      # Разбор PDF/DOCX регламентов
        │   ├── tables.py      # Обработка таблиц
        │   ├── faq_loader.py  # Загрузчик пар вопрос-ответ
        │   ├── chunker.py     # Нарезка текста на фрагменты
        │   └── cli.py         # Консольные команды импорта
        ├── analytics/         # Аналитика качества и KPI
        │   ├── models.py      # TicketAuditModel, TicketFeedbackModel, OperatorMetricDailyModel, SystemIncidentModel
        │   ├── schemas.py     # Схемы отчетов и аудита
        │   ├── repository.py  # AnalyticsRepository
        │   ├── metrics.py     # Расчет SLA и CSAT
        │   ├── service.py     # AnalyticsService
        │   └── tasks.py       # Задачи: audit_ticket_quality
        └── main.py            # Точка входа FastAPI, middleware
```

---

## 3. Сквозной сценарий: путь входящего сообщения пользователя

Когда пользователь отправляет реплику в веб-чат, запрос проходит через систему по строгому линейному маршруту с фиксацией конкретных доменов и файлов:

```text
[Клиентский запрос к /api/v1/chat/messages]
         │
         ▼
1. Транспортный уровень: эндпоинт входящих сообщений (api/v1/chat.py)
   Проверяет права пользователя через зависимость api/dependencies.py (CurrentUserDep).
         │
         ▼
2. Домен chat: сервис диалогов (chat/service.py) — Главный оркестратор сценария
   ├─► Шаг 1: Проверка на ненормативную лексику (домен chat: chat/moderation.py).
   │          При нарушении: немедленно закрывает тикет (closed_by_moderation), фиксирует статус в chat/models.py
   │          и возвращает клиенту системное уведомление. В RAG запрос не передается.
   │
   ├─► Шаг 2: Создание тикета (bot_processing) или привязка к открытому, сохранение реплики в БД
   │          (домен db: db/database.py, домен chat: chat/models.py) и контекста в Redis (домен core: core/redis_client.py).
   │
   ├─► Шаг 3: Передача чистого текста и контекста в фасад поиска (домен rag: rag/service.py).
   │          Внутри домена rag последовательно отрабатывают:
   │          - rag/router.py: классификация темы и линии поддержки (L1/L2/L3)
   │          - rag/retriever.py (через core/qdrant_client.py): гибридный поиск по базе знаний
   │          - rag/reranker.py: перепроверка и ранжирование найденных фрагментов
   │
   ├─► РАЗВИЛКА ПО УВЕРЕННОСТИ И ДЕЙСТВИЮ:
   │   │
   │   ├── Вариант А: Ответ найден в базе знаний
   │   │   - rag/generator.py (домен rag): потоковая генерация ответа со ссылками
   │   │   - chat/service.py (домен chat): сохранение ответа бота в chat/models.py
   │   │   - api/v1/chat.py: передача ответа клиенту потоком SSE
   │   │
   │   └── Вариант Б: Ответ не найден либо пользователь нажал «Позвать оператора»
   │       - operators/service.py (домен operators): перевод тикета в статус queued в очереди Redis
   │       - rag/copilot.py (домен rag): фоновая задача generate_copilot_summary в Taskiq
   │       - operators/balancer.py (домен operators): назначение тикета (status = 'assigned') на оператора
   │       - chat/service.py (домен chat): перевод диалога в режим ожидания сотрудника
   │
   └─► Шаг 4: Асинхронная отправка события закрытия обращения в аналитику
              (домен analytics: analytics/service.py, analytics/models.py).
```

---

## 4. Матрица допустимых зависимостей между модулями

Чтобы код не запутался, действуют строгие правила импорта:

| Модуль | Что может импортировать | Что ему категорически запрещено импортировать |
|---|---|---|
| `db` | Ничего из других модулей | `api`, `auth`, `chat`, `rag`, `operators`, `analytics`, `kb` |
| `core` | `db` | `api`, `auth`, `chat`, `rag`, `operators` и т.д. |
| `kb` | `core`, `db` | `api`, `chat`, `operators` |
| `rag` | `core`, `db` | `api`, `chat`, `operators` |
| `auth` | `core`, `db` | `api`, `chat`, `operators`, `rag` |
| `operators` | `core`, `db`, `auth` (типы пользователей) | `api`, `chat` |
| `chat` | `core`, `db`, `auth`, `rag/service.py`, `operators/service.py` | `api`, внутренние детали других модулей |
| `analytics` | `core`, `db`, модели данных для чтения аналитики | `api`, логику выполнения пользовательских запросов |
| `api/v1` | `core`, сервисы и схемы доменов (`auth`, `chat`, `operators`, `kb`, `analytics`) | Внутренние детали реализации и прямой доступ к БД в обход сервисов |

Благодаря такой схеме транспортный слой изолирован в `api/v1/`, а доменные модули содержат чистую бизнес-логику и вообще не зависят от веб-фреймворка.
