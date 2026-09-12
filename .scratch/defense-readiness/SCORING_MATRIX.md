# Матрица обратного инжиниринга критериев оценки жюри (Scoring Breakdown Matrix)

> **Цель документа:** Декомпозиция 100 баллов хакатона на атомарные подкритерии с привязкой к кодовой базе, инженерным артефактам, продуктовым требованиям фронтенда (стиль tender.mos.ru, гостевой доступ, чипсы, цитаты, Fast Role Switcher) и рискам потери баллов.  
> **Роль:** Lead Architect & Pitch Producer команды.

---

## Сводная таблица распределения баллов

| № | Категория критериев | Баллы | Профиль жюри | Ключевой фокус проверки |
|---|---|:---:|---|---|
| 1 | Соответствие бизнес-требованиям и полнота решения | **25** | Бизнес-заказчик / Руководитель службы поддержки | Покрытие ТЗ, структурирование базы знаний, маршрутизация, модерация |
| 2 | Архитектура, надежность и чистота инженерных решений | **25** | Главный архитектор / Tech Lead / DevOps | Отказоустойчивость, чистые границы доменов, очереди, concurrency |
| 3 | Качество RAG/AI, точность поиска и отсутствие галлюцинаций | **25** | AI/ML Lead / Исследователь данных | Гибридный поиск, фактчекинг, Small-to-Big чанкинг, AI Copilot |
| 4 | Демонстрация, интерфейс оператора и бизнес-эффект / ROI | **25** | Product Owner / Финансовый директор / CPO | "Золотой путь" Live Demo, АРМ оператора, дашборд руководителя, Unit-экономика |
| **ИТОГО** | **Максимальный балл** | **100** | | |

---

## 1. Соответствие бизнес-требованиям и полнота решения (25 баллов)

### 1.1. Структурирование неформализованной базы знаний регламентов (6 баллов)
* **Что хочет увидеть жюри:**
  - *Технический профиль:* Глубокий синтаксический разбор предоставленных методичек PDF/DOCX с выделением дерева AST (`kb_documents` $\to$ `kb_nodes` $\to$ `kb_chunks`), сохранение целостности таблиц и привязки к статьям/пунктам регламента. Наличие консольной утилиты верификации и выгрузки.
  - *Бизнес-профиль:* Поставщик получает исчерпывающую информацию со ссылкой на конкретную норму (например, регламент Портала поставщиков Москвы или приказ ФНС № 820@), а не разрозненные цитаты.
* **Доказывающие артефакты в коде:**
  - Парсер и нарезчик таблиц: [`backend/src/kb/parser.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/kb/parser.py), [`backend/src/kb/tables.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/kb/tables.py), [`backend/src/kb/chunker.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/kb/chunker.py).
  - Спецификация хранения и ADR: [`docs/adr/0001-kb-storage-and-chunking.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/adr/0001-kb-storage-and-chunking.md), [`docs/RAG_AND_PARSING_SPECIFICATION.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/RAG_AND_PARSING_SPECIFICATION.md).
  - CLI-утилита валидации и экспорта артефактов для жюри: [`backend/src/kb/cli.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/kb/cli.py) (`uv run python -m src.kb.cli ingest`).
  - База данных: таблицы `kb_documents`, `kb_nodes`, `kb_chunks`, `kb_article_references`.
* **Что приведет к потере баллов:**
  - "Наивный" импорт через text splitters langchain без сохранения табличной верстки и структуры заголовков.
  - Утеря регламентных таблиц (например, сроков блокировки обеспечения или форматов УПД).
  - Отсутствие инструмента верификации полноты извлеченного текста.

### 1.2. Автоматическое консультирование и маршрутизация при отсутствии данных (6 баллов)
* **Что хочет увидеть жюри:**
  - *Технический профиль:* Уверенный ответ на типовые запросы; при отсутствии уверенности (score < 0.65) или при специфических сбоях система явно признает отсутствие данных и бесшовно переводит диалог на оператора с сохранением контекста переписки в Redis (`chat:context:{ticket_id}`).
  - *Бизнес-профиль:* Исключение эффекта "глухого телефона": клиент не начинает диалог заново при подключении оператора.
* **Доказывающие артефакты в коде:**
  - Классификатор и оркестратор: [`backend/src/rag/router.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/router.py), [`backend/src/chat/service.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/chat/service.py) (метод `process_client_message`).
  - Эндпоинт эскалации: `POST /api/v1/chat/escalate` ([`backend/src/api/v1/chat.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/api/v1/chat.py)).
  - Сохранение контекста сессии: `chat:context:{ticket_id}` в Redis.
* **Что приведет к потере баллов:**
  - Галлюцинация бота при отсутствии ответа в базе знаний вместо предложения вызвать оператора.
  - Потеря сообщений клиента при переходе к оператору (оператор видит пустой экран).

### 1.3. Распознавание нецензурной лексики и этический фильтр в реальном времени (5 баллов)
* **Что хочет увидеть жюри:**
  - *Технический профиль:* Двусторонний перехватчик: проверка входящих реплик клиента и исходящих ответов оператора. Мгновенное завершение сессии при деструктивном поведении клиента со статусом `closed_by_moderation`.
  - *Бизнес-профиль:* Защита операторов от эмоционального выгорания и травли; предотвращение репутационных рисков портала zakupki.mos.ru.
* **Доказывающие артефакты в коде:**
  - Сервис модерации: [`backend/src/chat/moderation.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/chat/moderation.py) (`ChatModerationService`).
  - Обработка в чате: [`backend/src/chat/service.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/chat/service.py) (`check_message_moderation`).
  - Статусы сообщений: `MessageModerationStatus.BLOCKED`, `TicketStatus.CLOSED_BY_MODERATION`.
  - Тесты: [`backend/tests/chat/test_moderation.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/tests/chat/test_moderation.py).
* **Что приведет к потере баллов:**
  - Пропуск очевидного мата или обсценных конструкций с заменой букв.
  - Неинформативный ответ при блокировке (например, внутренний 500 Internal Server Error вместо 400 Bad Request с разъяснением правил).

### 1.4. Оценивание результатов работы специалистов и аудит диалогов (LLM-Judge) (8 баллов)
* **Что хочет увидеть жюри:**
  - *Технический профиль:* Асинхронная задача Taskiq, запускаемая после отзыва клиента или таймаута; модель-судья оценивает стенограмму по вежливости и полноте (1–5), определяет `root_cause` (`system_issue`, `operator_error`, `regulation_dissatisfaction`).
  - *Бизнес-профиль:* Автоматическое выявление системных проблем портала. Защита оператора от несправедливой оценки, если причиной негатива стал сбой портала (Adjusted CSAT).
* **Доказывающие артефакты в коде:**
  - Модели и энумы: [`backend/src/analytics/models.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/analytics/models.py) (`TicketAuditModel`, `SystemIncidentModel`, `RootCauseType`).
  - Сервис и LLM-Judge: [`backend/src/analytics/service.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/analytics/service.py), [`backend/src/analytics/evaluator.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/analytics/evaluator.py).
  - Фоновые задачи: [`backend/src/analytics/tasks.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/analytics/tasks.py) (`audit_ticket_quality`).
  - Тесты: [`backend/tests/analytics/test_systemic_issues_report.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/tests/analytics/test_systemic_issues_report.py).
* **Что приведет к потере баллов:**
  - Отсутствие классификации первопричин негатива (простое сохранение клиентской звездочки без анализа).
  - Снижение рейтинга оператора из-за падения КриптоПро или недоступности серверов ЕАИСТ.

---

## 2. Архитектура, надежность и чистота инженерных решений (25 баллов)

### 2.1. Изоляция доменов, чистота кода и асинхронный стек (6 баллов)
* **Что хочет увидеть жюри:**
  - Четкое разделение ответственности: `auth`, `chat`, `operators`, `kb`, `rag`, `analytics`.
  - Использование современных паттернов: SQLAlchemy 2.0 (`select()`, `Mapped[]`), Pydantic v2 schemas, Dependency Injection в FastAPI, миграции Alembic.
  - Наличие и соблюдение реестра архитектурных решений (`docs/adr/`).
* **Доказывающие артефакты в коде:**
  - Карта контекстов: [`CONTEXT-MAP.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/CONTEXT-MAP.md), архитектурное описание [`docs/BACKEND_ARCHITECTURE.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/BACKEND_ARCHITECTURE.md).
  - Архитектурные решения: [`docs/adr/0001-kb-storage-and-chunking.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/adr/0001-kb-storage-and-chunking.md), [`docs/adr/0002-ticket-model-in-chat-domain.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/adr/0002-ticket-model-in-chat-domain.md), [`docs/adr/004-sse-auth-and-pubsub-lifecycle.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/adr/004-sse-auth-and-pubsub-lifecycle.md).
  - Отсутствие циклических зависимостей между модулями.
* **Что приведет к потере баллов:**
  - Синхронные блокирующие вызовы (`time.sleep()`, синхронные драйверы `psycopg2` вместо `asyncpg`).
  - Прямой доступ контроллеров API в базу в обход сервисного слоя и репозиториев.

### 2.2. Очереди, балансировка и защита от состояний гонки (7 баллов)
* **Что хочет увидеть жюри:**
  - Балансировщик входящих обращений по линиям (L1, L2, L3) с учетом емкости слотов (`active_slots < max_slots`).
  - Приоритетная маршрутизация (P0 вытесняет P1/P2 через `LPUSH` в Redis-очереди).
  - Распределенные блокировки Redis (`lock:dispatch:{line_code}`) и выбор оператора с `SELECT ... FOR UPDATE` в транзакции PostgreSQL.
* **Доказывающие артефакты в коде:**
  - Балансировщик: [`backend/src/operators/balancer.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/operators/balancer.py) (`TicketBalancer`).
  - Очереди и задачи Taskiq: [`backend/src/operators/tasks.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/operators/tasks.py) (`dispatch_line_queue`).
  - Спецификация очередей: [`docs/QUEUES_SPECIFICATION.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/QUEUES_SPECIFICATION.md).
* **Что приведет к потере баллов:**
  - Назначение двух тикетов на один слот оператора (race condition).
  - Потеря тикета при одновременном закрытии клиентом и оператором.

### 2.3. Аварийное восстановление, таймауты и Graceful Degradation (6 баллов)
* **Что хочет увидеть жюри:**
  - Восстановление очередей при холодном старте или падении Redis из PostgreSQL по индексу `idx_tickets_queued_recovery`.
  - Автоматическое закрытие неактивных тикетов планировщиком Taskiq Scheduler (`check_system_timeouts` каждые 30 секунд).
  - Отслеживание дисконнектов операторов по отметке `disconnected_at` с возвратом тикетов в начало очереди при отсутствии связи > 10 мин.
  - Режим деградации RAG при таймауте LLM: событие `event: degraded_mode` с выдачей проверенных фрагментов регламента напрямую клиенту.
* **Доказывающие артефакты в коде:**
  - Режим деградации: [`backend/src/rag/generator.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/generator.py) (`RagDegradedModeEventSchema`).
  - Восстановление и таймауты: [`backend/src/operators/service.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/operators/service.py), [`backend/src/operators/tasks.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/operators/tasks.py).
  - Индексы БД: `idx_tickets_queued_recovery` в [`backend/src/chat/models.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/chat/models.py).
* **Что приведет к потере баллов:**
  - Вечно "висящие" сессии при закрытии вкладки браузера.
  - Белый экран или ошибка 500 для пользователя при сбое стороннего API нейросети.

### 2.4. Безопасность, RBAC и постоянный транспорт SSE (6 баллов)
* **Что хочет увидеть жюри:**
  - Централизованный RBAC с гранулярными правами: `client`, `operator`, `supervisor`, `admin`.
  - Поддержка изолированных анонимных гостевых сессий (Guest Session ID).
  - Реализация SSE без утечек памяти: Heartbeat ping каждые 15 секунд (`: ping\n\n`), закрытие Pub/Sub в блоке `finally`.
  - Решение ограничения браузерного `EventSource` (передача JWT в параметре `?token=` с маскированием в логах доступа по ADR 004).
* **Доказывающие артефакты в коде:**
  - Зависимости безопасности: [`backend/src/api/dependencies.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/api/dependencies.py) (`require_roles`, `get_current_user_sse`).
  - ADR 004: [`docs/adr/004-sse-auth-and-pubsub-lifecycle.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/adr/004-sse-auth-and-pubsub-lifecycle.md).
  - Эндпоинты стриминга: `GET /api/v1/chat/events`, `GET /api/v1/operators/events`.
* **Что приведет к потере баллов:**
  - Доступ клиента к операторским или аналитическим эндпоинтам.
  - Разрыв соединения через 60 секунд из-за отсутствия пингов в Nginx/прокси.
  - Утечка соединений Redis Pub/Sub при перезагрузках страницы.

---

## 3. Качество RAG/AI, точность поиска и отсутствие галлюцинаций (25 баллов)

### 3.1. Двухканальный гибридный поиск и иерархический контекст (7 баллов)
* **Что хочет увидеть жюри:**
  - Сочетание плотного векторного поиска (`dense` эмбеддинги `bge-m3`, 1024D) и разреженного лексического поиска (`sparse` BM25 с русским стеммингом).
  - Переранжирование кандидатов кросс-энкодером `bge-reranker-v2-m3`.
  - Стратегия Small-to-Big чанкинга: точный векторный матчинг по небольшому чанку (до 350 токенов) с подтягиванием родительского раздела AST (`section_path`, `full_content`) для генератора.
* **Доказывающие артефакты в коде:**
  - Поисковое ядро: [`backend/src/rag/retriever.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/retriever.py), [`backend/src/rag/reranker.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/reranker.py).
  - Спецификация: [`docs/RAG_AND_PARSING_SPECIFICATION.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/RAG_AND_PARSING_SPECIFICATION.md).
  - Конфигурация Qdrant: коллекция с мультивекторами `dense` и `sparse`.
* **Что приведет к потере баллов:**
  - Наивный RAG по косинусному расстоянию без BM25, теряющий артикулы, номера законов и коды ошибок (например, код `0x80090016` или `приказ 820`).

### 3.2. Инлайн-фактчекинг и кликабельные источники цитат (7 баллов)
* **Что хочет увидеть жюри:**
  - Строгая валидация фактов на лету: любое числовое значение, дата, сумма или срок в ответе сверяются с исходным чанком базы знаний (`FactCheckingGuard`).
  - Кликабельные сноски `[^1]`, `[^2]`, открывающие модальное окно/шторку с точной цитатой из спаршенного Markdown и пути статьи (`section_path`).
  - Признак `verified: true/false` в потоке предложений.
* **Доказывающие артефакты в коде:**
  - Валидатор фактов: [`backend/src/rag/generator.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/generator.py) (`FactCheckingGuard`).
  - Методы: `extract_numeric_facts`, `extract_footnotes`, `verify_sentence`.
  - Промпты с запретом домысливания: [`backend/src/rag/prompts.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/prompts.py).
* **Что приведет к потере баллов:**
  - Выдуманные моделью сроки (например, "ответ заказчика 10 дней" вместо регламентных 3 дней).
  - "Мертвые" некликабельные сноски без возможности проверить первоисточник.

### 3.3. Потоковая отдача с разбивкой предложений (SentenceBuffer) (5 баллов)
* **Что хочет увидеть жюри:**
  - Мгновенная реакция интерфейса (Time to First Token < 400 мс).
  - Нарезка на законченные фразы с помощью библиотеки `razdel` и умный сброс буфера по абзацам `\n\n` для корректного отображения списков Markdown.
  - Понятные статусы для пользователя: `searching` $\to$ `reranking` $\to$ `generating` $\to$ `verified`.
* **Доказывающие артефакты в коде:**
  - Буферизатор: [`backend/src/rag/generator.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/generator.py) (`SentenceBuffer`).
  - Схемы событий: `RagSentenceEventSchema`, `RagSourcesEventSchema`, `RagDoneEventSchema` ([`backend/src/rag/schemas.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/schemas.py)).
* **Что приведет к потере баллов:**
  - Зависание на 8–10 секунд и резкое появление «простыни» текста целиком.
  - Обрезка предложений на полуслове или залипание списков в ожидании точки.

### 3.4. AI Copilot для оператора поддержки (6 баллов)
* **Что хочет увидеть жюри:**
  - Автоматическая подготовка аналитической подсказки в момент эскалации:
    1. Краткая суть проблемы в 1–2 предложениях (summary).
    2. Рекомендованная линия (L1, L2, L3) и обоснование.
    3. Готовый профессиональный черновик ответа для оператора с кнопкой быстрой вставки.
    4. Релевантные статьи регламента и похожие решенные прецеденты из Qdrant.
* **Доказывающие артефакты в коде:**
  - Сервис Copilot: [`backend/src/rag/copilot.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/copilot.py) (`generate_copilot_summary`).
  - Прецедентный поиск по решенным тикетам: [`backend/src/rag/qdrant_tickets.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/qdrant_tickets.py).
  - Модели и таблица: `ticket_copilot_summaries`.
* **Что приведет к потере баллов:**
  - Оператор подключается к тикету «вслепую» и тратит несколько минут на чтение длинной переписки.
  - Черновик ответа содержит общие фразы без учета контекста конкретной проблемы поставщика.

---

## 4. Демонстрация, интерфейс оператора и бизнес-эффект / ROI (25 баллов)

### 4.1. Продуктовая зрелость интерфейса и стиль Портала поставщиков (7 баллов)
* **Что хочет увидеть жюри:**
  - Фирменная стилизация tender.mos.ru: основные цвета `#004B87`, `#E31E24`, `#F5F6F8`, контрастная типографика, плашки и логотип.
  - **Гостевой режим (Anonymous Client):** старт чата в 1 клик без обязательного логина, хранение UUID в localStorage.
  - **Чипсы быстрых вопросов (Quick Actions):** готовые кликабельные сценарии для мгновенного старта Live Demo.
  - **Fast Role Switcher:** мгновенное переключение между ролями «Клиент» $\leftrightarrow$ «Оператор L2» $\leftrightarrow$ «Супервизор» за 200 мс прямо из шапки.
* **Доказывающие артефакты в коде:**
  - Компоненты фронтенда: [`frontend/src/components/chat/WelcomeScreen.tsx`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/frontend/src/components/chat/WelcomeScreen.tsx), [`frontend/src/components/operator/OperatorWorkspace.tsx`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/frontend/src/components/operator/OperatorWorkspace.tsx).
  - Цветовая палитра: [`frontend/tailwind.config.js`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/frontend/tailwind.config.js).
* **Что приведет к потере баллов:**
  - Необходимость тратить драгоценное время питча на ввод email и пароля в форме авторизации.
  - Дженерик-дизайн "из коробки" без узнаваемых цветов и элементов портала закупок Москвы.

### 4.2. Аналитический дашборд руководителя, Adjusted CSAT и системные инциденты (7 баллов)
* **Что хочет увидеть жюри:**
  - Мониторинг ключевых показателей поддержки: Deflection Rate (% автоматизации ботом), время первого ответа (FRT), время решения (AHT).
  - Наглядное сравнение базового клиентского CSAT и скорректированного CSAT (Adjusted CSAT), исключающего влияние сбоев платформы на KPI операторов.
  - Реестр технических инцидентов (`system_incidents`) с группировкой по типам (`crypto_plugin`, `portal_downtime`, `api_error`).
  - Экспорт отчета в CSV с кодировкой UTF-8-SIG (BOM) для корректного открытия в Microsoft Excel на Windows.
* **Доказывающие артефакты в коде:**
  - API аналитики: [`backend/src/api/v1/analytics.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/api/v1/analytics.py) (`GET /dashboard`, `GET /systemic-issues`, `GET /incidents`, `GET /export`).
  - Логика расчета метрик и SQL-запросы: [`backend/src/analytics/repository.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/analytics/repository.py) (`ROUND(AVG(ot.client_score) FILTER (WHERE ot.is_system_issue IS NOT TRUE)::numeric, 2) AS avg_adjusted_csat`).
* **Что приведет к потере баллов:**
  - Отсутствие инструмента для руководства и супервизоров.
  - Выгрузка CSV, открывающаяся "крякозябрами" в Excel из-за отсутствия BOM-метки.

### 4.3. Экономическая модель и обоснование ROI для Портала поставщиков (6 баллов)
* **Что хочет увидеть жюри:**
  - Прозрачный финансовый расчет: затраты на инференс моделей vs экономия фонда оплаты труда (ФОТ).
  - Метрики окупаемости:
    * Стоимость 1 сессии в LLM-контуре: **0.08–0.15 руб.** (компактный промптинг, кеширование контекста).
    * Себестоимость обработки 1 тикета оператором: **~120–150 руб.**
    * При Deflection Rate = **68.4%** и сокращении AHT оператора с **12 мин до 2.5 мин** экономия составляет более **70% операционных расходов поддержки**.
* **Доказывающие артефакты в коде:**
  - Расчет стоимости токенов и таймингов в архитектурной документации: [`docs/concept.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/docs/concept.md), презентация проекта.
* **Что приведет к потере баллов:**
  - Абстрактные тезисы ("наш AI оптимизирует процессы") без конкретных цифр рублей, секунд и процентов.

### 4.4. Безупречность Live Demo и скоростной тайминг (< 100 секунд) (5 баллов)
* **Что хочет увидеть жюри:**
  - Уверенная демонстрация без единой заминки: полный сквозной цикл за **90–95 секунд**.
  - Наличие тумблера `Demo: Mock / Live` для мгновенного парирования сетевых сбоев.
  - Наличие мобильного QR-кода на слайдах для вовлечения жюри.
* **Доказывающие артефакты в коде:**
  - Демо-сидирование базы: [`backend/src/db/seed_demo.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/db/seed_demo.py) (30 сценариев реальных обращений).
  - Детерминированные моки: `MockLlmStreamClient` в [`backend/src/rag/generator.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/generator.py), `MockCopilotLlmClient` в [`backend/src/rag/copilot.py`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/backend/src/rag/copilot.py).
  - Сценарий Live Demo: [`.scratch/defense-readiness/LIVE_DEMO_SCRIPT.md`](file:///c:/Users/Дмитрий/Desktop/git/tender-hack/.scratch/defense-readiness/LIVE_DEMO_SCRIPT.md).
* **Что приведет к потере баллов:**
  - Зависание демо из-за ожидания ручного набора текста на клавиатуре.
  - Падение демонстрации при отсутствии интернет-соединения в аудитории.
