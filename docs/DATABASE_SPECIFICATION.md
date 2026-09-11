# Спецификация слоя данных: PostgreSQL и Redis

Документ определяет физическую схему реляционной базы данных PostgreSQL в третьей нормальной форме, контракты целостности, индексы и структуру оперативного хранилища Redis.

---

## 1. Архитектурные принципы и нормализация

Схема разработана с соблюдением правил третьей нормальной формы:
* Все атрибуты атомарны, исключены ненормализованные списки и дублирующиеся структуры.
* Профили клиентов и операторов изолированы в отдельных таблицах со связью один к одному к базовой учетной записи, что исключает пустые поля у нерелевантных ролей.
* Непрерывная лента переписки клиента отделена от дискретных единиц обслуживания: один чат объединяет последовательность обращений.
* Метаданные завершенного обращения (отзывы клиентов, результаты автоматического контроля качества, выжимка контекста для оператора) вынесены в специализированные таблицы с внешним ключом к обращению.

### Стандарты типов и первичных ключей

| Категория сущностей | Тип первичного ключа | Обоснование |
|---|---|---|
| Транзакционные сущности (`users`, `chats`, `tickets`, `messages`, `audits`, `feedbacks`) | `UUID` (версия 7) | Включает миллисекундную временную метку, упорядочивает записи в B-дереве без фрагментации страниц, генерируется на прикладном уровне без блокировок последовательностей. |
| Справочники (`roles`, `support_lines`) | `SMALLSERIAL` / `VARCHAR(32)` | Компактные неизменяемые таблицы с числом записей менее сотни. |
| База знаний (`documents`, `nodes`, `chunks`) | `VARCHAR(64)` | Строгая совместимость со спецификацией поискового ядра и внешними идентификаторами нормативных актов. |

Временные метки во всех таблицах хранятся в типе `TIMESTAMPTZ` (время с часовым поясом) со значением по умолчанию `clock_timestamp()`.

### Стандарты именования моделей SQLAlchemy и репозиториев

Согласно правилам [code-rules.md](../.agents/rules/code-rules.md) классы ORM имеют обязательный суффикс `Model`, а методы выборки и сохранения инкапсулируются в доменных репозиториях с суффиксом `Repository`:

| Таблица PostgreSQL | Модель SQLAlchemy | Доменный репозиторий | Размещение в проекте |
|---|---|---|---|
| `roles` | `RoleModel` | `UserRepository` | `src/auth/` |
| `users` | `UserModel` | `UserRepository` | `src/auth/` |
| `client_profiles` | `ClientProfileModel` | `UserRepository` | `src/auth/` |
| `operator_profiles` | `OperatorProfileModel` | `OperatorRepository` | `src/operators/` |
| `support_lines` | `SupportLineModel` | `OperatorRepository` | `src/operators/` |
| `tickets` | `TicketModel` | `OperatorRepository` | `src/operators/` |
| `ticket_copilot_summaries` | `TicketCopilotSummaryModel` | `OperatorRepository` | `src/operators/` |
| `chats` | `ChatModel` | `ChatRepository` | `src/chat/` |
| `messages` | `MessageModel` | `ChatRepository` | `src/chat/` |
| `ticket_feedbacks` | `TicketFeedbackModel` | `AnalyticsRepository` | `src/analytics/` |
| `ticket_audits` | `TicketAuditModel` | `AnalyticsRepository` | `src/analytics/` |
| `operator_metrics_daily` | `OperatorMetricDailyModel` | `AnalyticsRepository` | `src/analytics/` |
| `system_incidents` | `SystemIncidentModel` | `AnalyticsRepository` | `src/analytics/` |
| `kb_documents` | `KbDocumentModel` | `KbRepository` | `src/kb/` |
| `kb_nodes` | `KbNodeModel` | `KbRepository` | `src/kb/` |
| `kb_chunks` | `KbChunkModel` | `KbRepository` | `src/kb/` |
| `kb_article_references` | `KbArticleReferenceModel` | `KbRepository` | `src/kb/` |
| `faq_moderation_queue` | `FaqModerationQueueModel` | `KbRepository` | `src/kb/` |
| `regression_candidates` | `RegressionCandidateModel` | `KbRepository` | `src/kb/` |

---

## 2. Схема PostgreSQL: Учетные записи, роли и профили

Раздел описывает субъектов системы: клиентов (поставщиков), операторов линий поддержки, руководителей и администраторов.

### 2.1. Таблица ролей (`roles`)

Справочник системных прав доступа.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `SMALLSERIAL` | `PRIMARY KEY` | Идентификатор роли |
| `code` | `VARCHAR(32)` | `NOT NULL, UNIQUE` | Уникальный код: `client`, `operator`, `supervisor`, `admin` |
| `name` | `VARCHAR(64)` | `NOT NULL` | Название роли на русском языке |
| `description` | `TEXT` | `NULL` | Описание зоны ответственности |

```sql
CREATE TABLE roles (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    description TEXT
);

INSERT INTO roles (code, name, description) VALUES
('client', 'Клиент (Поставщик)', 'Пользователь портала поставщиков, обращающийся в поддержку'),
('operator', 'Оператор поддержки', 'Специалист линии поддержки, обрабатывающий обращения'),
('supervisor', 'Руководитель поддержки', 'Контроль качества, просмотр аналитики и подтверждение базы знаний'),
('admin', 'Системный администратор', 'Полный доступ к системным настройкам');
```

### 2.2. Таблица пользователей (`users`)

Единый реестр учетных записей для аутентификации.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор пользователя |
| `role_id` | `SMALLINT` | `NOT NULL, REFERENCES roles(id)` | Ссылка на роль |
| `email` | `VARCHAR(255)` | `NOT NULL, UNIQUE` | Адрес электронной почты для входа |
| `password_hash` | `VARCHAR(255)` | `NOT NULL` | Хэш пароля |
| `full_name` | `VARCHAR(255)` | `NULL` | Фамилия, имя и отчество (при наличии) |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT true` | Признак активной учетной записи |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Дата и время регистрации |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Дата и время обновления |

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    role_id SMALLINT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_role ON users (role_id);
```

### 2.3. Таблица линий поддержки (`support_lines`)

Справочник очередей и уровней компетенции специалистов.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `SMALLSERIAL` | `PRIMARY KEY` | Идентификатор линии |
| `code` | `VARCHAR(32)` | `NOT NULL, UNIQUE` | Системный код линии: `L1`, `L2`, `L3` |
| `name` | `VARCHAR(128)` | `NOT NULL` | Название линии поддержки |
| `description` | `TEXT` | `NULL` | Зона ответственности и специфика вопросов |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT true` | Признак доступности линии для маршрутизации |

```sql
CREATE TABLE support_lines (
    id SMALLSERIAL PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true
);

INSERT INTO support_lines (code, name, description) VALUES
('L1', 'Первая линия', 'Консультации по типовым вопросам и навигации по порталу'),
('L2', 'Вторая линия', 'Технические инциденты, электронная подпись, интеграции'),
('L3', 'Третья линия', 'Сложные юридические вопросы, регламенты 44-ФЗ и 223-ФЗ');
```

### 2.4. Профиль оператора (`operator_profiles`)

Служебные параметры специалиста для балансировки нагрузки и контроля смены.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `user_id` | `UUID` | `PRIMARY KEY, REFERENCES users(id)` | Идентификатор оператора |
| `line_id` | `SMALLINT` | `NOT NULL, REFERENCES support_lines(id)` | Закрепленная линия поддержки |
| `shift_status` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'offline'` | Статус смены: `active`, `break`, `offline` |
| `max_slots` | `SMALLINT` | `NOT NULL, DEFAULT 5, CHECK (max_slots > 0)` | Предельное число одновременных диалогов |
| `disconnected_at` | `TIMESTAMPTZ` | `NULL` | Метка времени фиксации разрыва постоянного соединения |
| `last_assigned_at` | `TIMESTAMPTZ` | `NULL` | Время последнего назначения тикета |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время изменения состояния |

```sql
CREATE TABLE operator_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    line_id SMALLINT NOT NULL REFERENCES support_lines(id) ON DELETE RESTRICT,
    shift_status VARCHAR(16) NOT NULL DEFAULT 'offline',
    max_slots SMALLINT NOT NULL DEFAULT 5,
    disconnected_at TIMESTAMPTZ NULL,
    last_assigned_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_operator_shift_status CHECK (shift_status IN ('active', 'break', 'offline')),
    CONSTRAINT chk_operator_max_slots CHECK (max_slots > 0 AND max_slots <= 20)
);

CREATE INDEX idx_operator_profiles_dispatch ON operator_profiles (line_id, shift_status) 
WHERE shift_status = 'active';
```

### 2.5. Профиль клиента (`client_profiles`)

Реквизиты организации поставщика для идентификации контекста обращения (все поля опциональны).

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `user_id` | `UUID` | `PRIMARY KEY, REFERENCES users(id)` | Идентификатор клиента |
| `company_name` | `VARCHAR(255)` | `NULL` | Наименование организации или индивидуального предпринимателя |
| `inn` | `VARCHAR(12)` | `NULL` | ИНН организации (10 знаков) или ИП (12 знаков) |
| `kpp` | `VARCHAR(9)` | `NULL` | КПП для юридических лиц |
| `phone` | `VARCHAR(32)` | `NULL` | Контактный номер телефона |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время обновления профиля |

```sql
CREATE TABLE client_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    company_name VARCHAR(255) NULL,
    inn VARCHAR(12) NULL,
    kpp VARCHAR(9) NULL,
    phone VARCHAR(32) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_inn_length CHECK (inn IS NULL OR length(inn) IN (10, 12))
);

CREATE INDEX idx_client_profiles_inn ON client_profiles (inn) WHERE inn IS NOT NULL;
```

---

## 3. Схема PostgreSQL: Переписка и жизненный цикл обращений

Раздел описывает контейнеры переписки, обращения, сообщения и привязанные подсказки для специалистов.

### 3.1. Таблица чатов клиентов (`chats`)

Долгоживущий контейнер всей истории взаимодействия конкретного поставщика со службой поддержки.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор чата |
| `client_id` | `UUID` | `NOT NULL, UNIQUE, REFERENCES users(id)` | Идентификатор клиента |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время создания чата |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время последней активности |

```sql
CREATE TABLE chats (
    id UUID PRIMARY KEY,
    client_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_chats_client ON chats (client_id);
```

### 3.2. Таблица обращений (`tickets`)

Дискретная сессия решения проблемы с контролем состояний и ответственности.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор обращения |
| `chat_id` | `UUID` | `NOT NULL, REFERENCES chats(id)` | Ссылка на родительский чат |
| `line_id` | `SMALLINT` | `NULL, REFERENCES support_lines(id)` | Текущая линия поддержки |
| `assigned_operator_id` | `UUID` | `NULL, REFERENCES users(id)` | Назначенный оператор |
| `priority` | `VARCHAR(4)` | `NOT NULL, DEFAULT 'P2'` | Приоритет обращения (`P0`, `P1`, `P2`) |
| `status` | `VARCHAR(32)` | `NOT NULL` | Статус жизненного цикла обращения |
| `escalation_reason` | `VARCHAR(64)` | `NULL` | Причина передачи на оператора |
| `transferred_from_operator_id` | `UUID` | `NULL, REFERENCES users(id)` | Предыдущий оператор при переводе |
| `transfer_comment` | `TEXT` | `NULL` | Комментарий оператора при переводе на другую линию |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Момент открытия обращения |
| `assigned_at` | `TIMESTAMPTZ` | `NULL` | Момент назначения в сайдбар оператора |
| `opened_at` | `TIMESTAMPTZ` | `NULL` | Момент открытия диалога оператором |
| `closed_at` | `TIMESTAMPTZ` | `NULL` | Момент перевода в терминальный статус |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время последнего обновления |

Допустимые статусы обращения (`status`):
* `bot_processing`: первичная обработка вопросно-ответной системой (создается сразу при первом сообщении клиента).
* `queued`: ожидание свободного оператора в очереди линии.
* `assigned`: закреплено за оператором, слот занят, карточка в сайдбаре.
* `in_progress`: оператор открыл тикет, идет активная переписка.
* `resolved`: обращение успешно решено и закрыто (признак решения ботом: `assigned_operator_id IS NULL`, признак решения оператором: `assigned_operator_id IS NOT NULL`).
* `closed_by_inactivity`: закрыто автоматически по таймауту неактивности клиента.
* `closed_by_moderation`: закрыто принудительно за нарушение этики общения.
* `canceled`: отменено клиентом до подключения специалиста.

```sql
CREATE TABLE tickets (
    id UUID PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE RESTRICT,
    line_id SMALLINT NULL REFERENCES support_lines(id) ON DELETE RESTRICT,
    assigned_operator_id UUID NULL REFERENCES users(id) ON DELETE RESTRICT,
    priority VARCHAR(4) NOT NULL DEFAULT 'P2' CONSTRAINT chk_ticket_priority CHECK (priority IN ('P0', 'P1', 'P2')),
    status VARCHAR(32) NOT NULL,
    escalation_reason VARCHAR(64) NULL,
    transferred_from_operator_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    transfer_comment TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    assigned_at TIMESTAMPTZ NULL,
    opened_at TIMESTAMPTZ NULL,
    closed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_ticket_status CHECK (status IN (
        'bot_processing', 'queued', 'assigned', 'in_progress',
        'resolved', 'closed_by_inactivity', 'closed_by_moderation', 'canceled'
    ))
);

-- Индекс для балансировщика: подсчет активных слотов оператора
CREATE INDEX idx_tickets_operator_active_slots ON tickets (assigned_operator_id)
WHERE status IN ('assigned', 'in_progress');

-- Индекс для извлечения очереди ожидания при восстановлении Redis (с учетом приоритета и времени создания)
CREATE INDEX idx_tickets_queued_recovery ON tickets (line_id, priority, created_at)
WHERE status = 'queued';

-- Индекс для выборки истории тикетов чата
CREATE INDEX idx_tickets_chat_history ON tickets (chat_id, created_at DESC);
```

### 3.3. Таблица сообщений (`messages`)

Реплики диалога со статусом модерации и метаданными отправителя.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор сообщения |
| `ticket_id` | `UUID` | `NOT NULL, REFERENCES tickets(id)` | Ссылка на обращение |
| `sender_type` | `VARCHAR(16)` | `NOT NULL` | Тип отправителя: `client`, `bot`, `operator`, `system` |
| `sender_id` | `UUID` | `NULL, REFERENCES users(id)` | Идентификатор автора реплики |
| `text` | `TEXT` | `NOT NULL` | Текст сообщения |
| `moderation_status` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'passed'` | Статус проверки: `passed`, `flagged`, `blocked` |
| `moderation_reason` | `VARCHAR(64)` | `NULL` | Причина срабатывания фильтра модерации |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время фиксации сообщения |

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    sender_type VARCHAR(16) NOT NULL,
    sender_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    moderation_status VARCHAR(16) NOT NULL DEFAULT 'passed',
    moderation_reason VARCHAR(64) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_message_sender_type CHECK (sender_type IN ('client', 'bot', 'operator', 'system')),
    CONSTRAINT chk_message_moderation_status CHECK (moderation_status IN ('passed', 'flagged', 'blocked'))
);

CREATE INDEX idx_messages_ticket_feed ON messages (ticket_id, created_at ASC);
```

### 3.4. Таблица источников ответа бота (`message_sources`)

Нормализованная связь между сообщениями бота и фрагментами базы знаний, подтверждающими ответ.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор ссылки |
| `message_id` | `UUID` | `NOT NULL, REFERENCES messages(id)` | Ссылка на сообщение бота |
| `chunk_id` | `VARCHAR(64)` | `NOT NULL` | Идентификатор фрагмента базы знаний |
| `doc_id` | `VARCHAR(64)` | `NOT NULL` | Идентификатор первоисточника регламента |
| `quote_text` | `TEXT` | `NULL` | Цитируемый фрагмент статьи |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время фиксации ссылки |

```sql
CREATE TABLE message_sources (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id VARCHAR(64) NOT NULL,
    doc_id VARCHAR(64) NOT NULL,
    quote_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_message_sources_message ON message_sources (message_id);
CREATE INDEX idx_message_sources_chunk ON message_sources (chunk_id);
```

### 3.5. Подсказки оператору (`ticket_copilot_summaries`)

Автоматически сформированная языковой моделью выжимка диалога и рекомендации нормативных актов при эскалации на человека.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор подсказки |
| `ticket_id` | `UUID` | `NOT NULL, UNIQUE, REFERENCES tickets(id)` | Обращение |
| `summary` | `TEXT` | `NOT NULL` | Краткая формулировка проблемы клиента |
| `suggested_line_code` | `VARCHAR(32)` | `NULL` | Рекомендованная линия поддержки |
| `suggested_response` | `TEXT` | `NULL` | Черновик ответа для оператора |
| `recommended_chunk_ids` | `VARCHAR(64)[]` | `NOT NULL, DEFAULT '{}'` | Массив идентификаторов релевантных статей |
| `similar_resolved_tickets` | `JSONB` | `NOT NULL, DEFAULT '[]'::jsonb` | 3 похожих закрытых обращения из базы прецедентов Qdrant |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время генерации |

```sql
CREATE TABLE ticket_copilot_summaries (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    suggested_line_code VARCHAR(32) NULL,
    suggested_response TEXT NULL,
    recommended_chunk_ids VARCHAR(64)[] NOT NULL DEFAULT '{}',
    similar_resolved_tickets JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_copilot_summaries_ticket ON ticket_copilot_summaries (ticket_id);
```

---

## 4. Схема PostgreSQL: База знаний и контур самообучения

Структура таблиц хранения нормативных документов согласована с архитектурой модуля поиска и обеспечивает полный цикл управления знаниями.

### 4.1. Первичное хранилище документов (`kb_documents`)

Методички, регламенты и законы.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `doc_id` | `VARCHAR(64)` | `PRIMARY KEY` | Идентификатор документа |
| `title` | `TEXT` | `NOT NULL` | Наименование документа |
| `regime` | `VARCHAR(32)` | `NULL, DEFAULT 'MOS_PORTAL'` | Режим регулирования или категория |
| `edition_date` | `DATE` | `NULL, DEFAULT CURRENT_DATE` | Дата редакции документа |
| `status` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'uploaded'` | Статус обработки: `uploaded`, `indexing`, `indexed`, `failed`, `deprecated` |
| `error_message` | `TEXT` | `NULL` | Текст ошибки при сбое парсинга или индексации |
| `source_url` | `TEXT` | `NULL` | Ссылка на первоисточник (при наличии) |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время создания записи |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время обновления записи |

```sql
CREATE TABLE kb_documents (
    doc_id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    regime VARCHAR(32) NULL DEFAULT 'MOS_PORTAL',
    edition_date DATE NULL DEFAULT CURRENT_DATE,
    status VARCHAR(16) NOT NULL DEFAULT 'uploaded',
    error_message TEXT NULL,
    source_url TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_document_status CHECK (status IN ('uploaded', 'indexing', 'indexed', 'failed', 'deprecated'))
);

CREATE INDEX idx_kb_documents_status ON kb_documents (status);
```

### 4.2. Иерархические узлы структуры (`kb_nodes`)

Разделы, статьи и пункты нормативных актов.

```sql
CREATE TABLE kb_nodes (
    node_id VARCHAR(64) PRIMARY KEY,
    doc_id VARCHAR(64) NOT NULL REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    parent_node_id VARCHAR(64) REFERENCES kb_nodes(node_id) ON DELETE CASCADE,
    level VARCHAR(16) NOT NULL,
    section_path TEXT NOT NULL,
    article_no VARCHAR(32) NULL,
    part_no VARCHAR(32) NULL,
    title TEXT NOT NULL,
    full_content TEXT NOT NULL,
    table_md TEXT NULL,
    token_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_kb_nodes_lookup ON kb_nodes (doc_id, article_no, part_no);
CREATE INDEX idx_kb_nodes_path ON kb_nodes (doc_id, section_path);
CREATE INDEX idx_kb_nodes_parent ON kb_nodes (parent_node_id);
```

### 4.3. Поисковые фрагменты (`kb_chunks`)

Атомарные блоки текста, векторизуемые в векторной базе данных.

```sql
CREATE TABLE kb_chunks (
    chunk_id VARCHAR(64) PRIMARY KEY,
    node_id VARCHAR(64) NOT NULL REFERENCES kb_nodes(node_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    context_prefix TEXT NULL,
    hyp_questions JSONB DEFAULT '[]'::jsonb,
    embedding_model_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_kb_chunks_node ON kb_chunks (node_id);
```

### 4.4. Нормативный граф ссылок (`kb_article_references`)

Перекрестные ссылки между статьями нормативных актов.

```sql
CREATE TABLE kb_article_references (
    id SERIAL PRIMARY KEY,
    from_node_id VARCHAR(64) NOT NULL REFERENCES kb_nodes(node_id) ON DELETE CASCADE,
    to_node_id VARCHAR(64) REFERENCES kb_nodes(node_id) ON DELETE SET NULL,
    raw_label TEXT NOT NULL
);

CREATE INDEX idx_kb_refs_from ON kb_article_references (from_node_id);
CREATE INDEX idx_kb_refs_to ON kb_article_references (to_node_id);
```

### 4.5. Очередь черновиков базы знаний (`faq_moderation_queue`)

Контур самообучения: генерация черновиков статей из успешных диалогов операторов для утверждения руководителем.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор черновика |
| `ticket_id` | `UUID` | `NOT NULL, REFERENCES tickets(id)` | Исходное обращение |
| `question` | `TEXT` | `NOT NULL` | Обобщенный типовой вопрос клиента |
| `answer` | `TEXT` | `NOT NULL` | Сформированный ответ оператора |
| `kind` | `VARCHAR(16)` | `NOT NULL` | Категория материала: `normative`, `procedural` |
| `valid_until` | `DATE` | `NULL` | Срок действия регламента |
| `linked_regulation_chunk_id` | `VARCHAR(64)` | `NULL, REFERENCES kb_chunks(chunk_id)` | Базовая нормативная статья |
| `status` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'PENDING'` | Статус проверки: `PENDING`, `APPROVED`, `REJECTED` |
| `reviewer_id` | `UUID` | `NULL, REFERENCES users(id)` | Руководитель, принявший решение |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время генерации черновика |
| `reviewed_at` | `TIMESTAMPTZ` | `NULL` | Время утверждения или отклонения |

```sql
CREATE TABLE faq_moderation_queue (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    kind VARCHAR(16) NOT NULL,
    valid_until DATE NULL,
    linked_regulation_chunk_id VARCHAR(64) NULL REFERENCES kb_chunks(chunk_id) ON DELETE SET NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    reviewer_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    reviewed_at TIMESTAMPTZ NULL,
    CONSTRAINT chk_faq_kind CHECK (kind IN ('normative', 'procedural')),
    CONSTRAINT chk_faq_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED'))
);

CREATE INDEX idx_faq_moderation_status ON faq_moderation_queue (status) WHERE status = 'PENDING';
```

### 4.6. Контрольные пары регрессионного тестирования поиска (`regression_candidates`)

Золотой набор тестовых запросов и кандидатов в Golden Set для автоматической оценки качества поиска (HitRate@3, MRR) и регрессионного тестирования (соответствует Спецификации RAG, раздел 2.3).

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `SERIAL` | `PRIMARY KEY` | Идентификатор контрольной пары |
| `query` | `TEXT` | `NOT NULL` | Текст контрольного запроса |
| `expected_node_id` | `VARCHAR(64)` | `NOT NULL, REFERENCES kb_nodes(node_id)` | Ожидаемый эталонный узел структуры базы знаний |
| `generated_answer` | `TEXT` | `NOT NULL` | Сгенерированный системой ответ |
| `corrected_answer` | `TEXT` | `NOT NULL` | Эталонный скорректированный ответ эксперта |
| `error_tag` | `VARCHAR(32)` | `NOT NULL, CHECK (error_tag IN ('hallucination', 'retrieval_miss', 'out_of_kb', 'outdated_norm', 'tone'))` | Категория ошибки |
| `status` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'PENDING', CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED'))` | Статус проверки кандидатуры |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время фиксации |

```sql
CREATE TABLE regression_candidates (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    expected_node_id VARCHAR(64) NOT NULL REFERENCES kb_nodes(node_id) ON DELETE CASCADE,
    generated_answer TEXT NOT NULL,
    corrected_answer TEXT NOT NULL,
    error_tag VARCHAR(32) NOT NULL CONSTRAINT chk_regression_error_tag CHECK (
        error_tag IN ('hallucination', 'retrieval_miss', 'out_of_kb', 'outdated_norm', 'tone')
    ),
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING' CONSTRAINT chk_regression_status CHECK (
        status IN ('PENDING', 'APPROVED', 'REJECTED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX idx_regression_candidates_node ON regression_candidates (expected_node_id);
```

---

## 5. Схема PostgreSQL: Контроль качества, отзывы и аналитика

Раздел описывает фиксацию оценок пользователей, аудит диалогов искусственным интеллектом, реестр инцидентов и суточные показатели сотрудников.

### 5.1. Отзывы клиентов (`ticket_feedbacks`)

Оценка решения проблемы пользователем.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор отзыва |
| `ticket_id` | `UUID` | `NOT NULL, UNIQUE, REFERENCES tickets(id)` | Обращение |
| `score` | `SMALLINT` | `NOT NULL` | Оценка от 1 до 5 звезд |
| `comment` | `TEXT` | `NULL` | Развернутый комментарий клиента |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время сохранения отзыва |

```sql
CREATE TABLE ticket_feedbacks (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE,
    score SMALLINT NOT NULL,
    comment TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_feedback_score CHECK (score >= 1 AND score <= 5)
);

CREATE INDEX idx_feedbacks_score ON ticket_feedbacks (score);
```

### 5.2. Автоматический аудит диалога (`ticket_audits`)

Независимая оценка качества обслуживания языковой моделью.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор аудита |
| `ticket_id` | `UUID` | `NOT NULL, UNIQUE, REFERENCES tickets(id)` | Проверенное обращение |
| `politeness_score` | `SMALLINT` | `NOT NULL` | Вежливость и тон (от 1 до 5) |
| `completeness_score` | `SMALLINT` | `NOT NULL` | Полнота и точность ответа (от 1 до 5) |
| `root_cause` | `VARCHAR(64)` | `NULL` | Причина негатива: `operator_error`, `system_issue`, `regulation_dissatisfaction`, `none` |
| `summary` | `TEXT` | `NOT NULL` | Аналитическое заключение модели |
| `is_system_issue` | `BOOLEAN` | `NOT NULL, DEFAULT false` | Признак сбоя платформы для снятия штрафа с оператора |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время проведения аудита |

```sql
CREATE TABLE ticket_audits (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE,
    politeness_score SMALLINT NOT NULL,
    completeness_score SMALLINT NOT NULL,
    root_cause VARCHAR(64) NULL,
    summary TEXT NOT NULL,
    is_system_issue BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_audit_politeness CHECK (politeness_score BETWEEN 1 AND 5),
    CONSTRAINT chk_audit_completeness CHECK (completeness_score BETWEEN 1 AND 5),
    CONSTRAINT chk_audit_root_cause CHECK (root_cause IN (
        'operator_error', 'system_issue', 'regulation_dissatisfaction', 'none'
    ))
);

CREATE INDEX idx_audits_system_issue ON ticket_audits (is_system_issue) WHERE is_system_issue = true;
```

### 5.3. Реестр системных инцидентов (`system_incidents`)

Каталог технических сбоев портала, выявленных по итогам анализа обращений.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор инцидента |
| `ticket_id` | `UUID` | `NOT NULL, REFERENCES tickets(id)` | Обращение, выявившее сбой |
| `incident_type` | `VARCHAR(64)` | `NOT NULL` | Тип проблемы: `portal_downtime`, `crypto_plugin`, `api_error` |
| `description` | `TEXT` | `NOT NULL` | Описание симптомов сбоя |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'open'` | Статус инцидента: `open`, `in_review`, `resolved` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время фиксации |
| `resolved_at` | `TIMESTAMPTZ` | `NULL` | Время устранения сбоя разработчиками |

```sql
CREATE TABLE system_incidents (
    id UUID PRIMARY KEY,
    ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    incident_type VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    resolved_at TIMESTAMPTZ NULL,
    CONSTRAINT chk_incident_status CHECK (status IN ('open', 'in_review', 'resolved'))
);

CREATE INDEX idx_incidents_status ON system_incidents (status) WHERE status = 'open';
```

### 5.4. Суточные показатели операторов (`operator_metrics_daily`)

Агрегированная таблица показателей для расчета рейтингов и премирования.

| Колонка | Тип данных | Ограничения | Описание |
|---|---|---|---|
| `id` | `UUID` | `PRIMARY KEY` | Идентификатор записи |
| `operator_id` | `UUID` | `NOT NULL, REFERENCES users(id)` | Оператор |
| `metric_date` | `DATE` | `NOT NULL` | Отчетные сутки |
| `total_tickets_handled` | `INTEGER` | `NOT NULL, DEFAULT 0` | Число обработанных тикетов |
| `avg_first_response_time_sec` | `NUMERIC(8,2)` | `NULL` | Среднее время первого ответа |
| `avg_handling_time_sec` | `NUMERIC(8,2)` | `NULL` | Среднее время ведения тикета |
| `avg_client_csat` | `NUMERIC(3,2)` | `NULL` | Средняя оценка клиентов |
| `avg_adjusted_csat` | `NUMERIC(3,2)` | `NULL` | Оценка клиентов без учета системных сбоев портала |
| `avg_ai_quality_score` | `NUMERIC(3,2)` | `NULL` | Средний балл качества от языковой модели |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время расчета |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT clock_timestamp()` | Время обновления |

```sql
CREATE TABLE operator_metrics_daily (
    id UUID PRIMARY KEY,
    operator_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    total_tickets_handled INTEGER NOT NULL DEFAULT 0,
    avg_first_response_time_sec NUMERIC(8,2) NULL,
    avg_handling_time_sec NUMERIC(8,2) NULL,
    avg_client_csat NUMERIC(3,2) NULL,
    avg_adjusted_csat NUMERIC(3,2) NULL,
    avg_ai_quality_score NUMERIC(3,2) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_operator_date UNIQUE (operator_id, metric_date)
);

CREATE INDEX idx_metrics_operator_period ON operator_metrics_daily (operator_id, metric_date DESC);
```

---

## 6. Спецификация оперативного хранилища Redis

Redis используется исключительно для хранения кратковременных состояний высокой частоты обновления, координации воркеров и мгновенной доставки сообщений.

### 6.1. Реестр структур данных Redis

| Паттерн ключа | Тип структуры | Время жизни (TTL) | Назначение |
|---|---|---|---|
| `chat:context:{ticket_id}` | `List` | 1800 секунд (30 минут) | Скользящее окно последних реплик активного тикета для передачи контекста в языковую модель. |
| `queue:line:{line_code}` | `List` | Без ограничения (постоянный) | Очередь идентификаторов тикетов, ожидающих назначения на оператора конкретной линии. |
| `lock:dispatch:line:{line_code}` | `String` | 5 секунд | Распределенная блокировка процесса распределения очереди линии для защиты от состояния гонки. |
| `channel:ticket:{ticket_id}` | Pub/Sub | Не хранится | Шина передачи сообщений между клиентом и оператором в режиме реального времени. |
| `channel:operator:{operator_id}` | Pub/Sub | Не хранится | Шина уведомлений оператора о назначении нового тикета в его сайдбар. |

### 6.2. Регламент работы с контекстом диалога (`chat:context:{ticket_id}`)

1. **Добавление реплики:** при сохранении каждого сообщения в PostgreSQL в конец списка добавляется сериализованная строка JSON:
   `RPUSH chat:context:{ticket_id} "{\"sender\":\"client\",\"text\":\"...\",\"timestamp\":\"...\"}"`
2. **Ограничение глубины:** список обрезается до последних 10 сообщений:
   `LTRIM chat:context:{ticket_id} -10 -1`
3. **Продление доступности:** при каждом новом сообщении вызывается команда:
   `EXPIRE chat:context:{ticket_id} 1800`
4. **Очистка ресурса:** при переходе тикета в любой терминальный статус (`resolved`, `closed_by_inactivity`, `closed_by_moderation`, `canceled`) ключ немедленно удаляется:
   `DEL chat:context:{ticket_id}`

### 6.3. Регламент работы с очередями ожидания (`queue:line:{line_code}`)

1. **Постановка в очередь:** при эскалации тикета от бота к специалисту идентификатор тикета добавляется в конец очереди:
   `RPUSH queue:line:L1 "6a1c5b8e-..."`
2. **Извлечение для назначения:** воркер балансировщика под блокировкой извлекает первый элемент из начала очереди:
   `LPOP queue:line:L1`
3. **Экстренный возврат:** при нештатном разрыве связи оператора (таймаут более 10 минут) незавершенный тикет возвращается в приоритетное начало очереди:
   `LPUSH queue:line:L1 "6a1c5b8e-..."`

### 6.4. Регламент распределенной блокировки балансировщика

Для исключения гонки между процессами при распределении обращений используется атомарная блокировка:
`SET lock:dispatch:line:{line_code} "{worker_instance_id}" NX EX 5`
Если ключ уже существует, другой процесс пропускает запуск. По завершении транзакции в PostgreSQL блокировка снимается скриптом Lua с проверкой идентификатора владельца.

---

## 7. Транзакционные сценарии и целостность данных

### 7.1. Сценарий реактивного распределения обращений

1. Захватывается блокировка `lock:dispatch:line:{line_code}` в Redis.
2. Проверяется наличие тикетов: `LINDEX queue:line:{line_code} 0`. Если очередь пуста — блокировка снимается.
3. В транзакции PostgreSQL выбирается наименее загруженный активный оператор нужной линии:
   ```sql
   SELECT op.user_id, count(t.id) AS active_slots
   FROM operator_profiles op
   LEFT JOIN tickets t ON t.assigned_operator_id = op.user_id 
       AND t.status IN ('assigned', 'in_progress')
   WHERE op.line_id = :target_line_id 
     AND op.shift_status = 'active'
     AND op.disconnected_at IS NULL
   GROUP BY op.user_id, op.max_slots, op.last_assigned_at
   HAVING count(t.id) < op.max_slots
   ORDER BY active_slots ASC, op.last_assigned_at ASC NULLS FIRST
   LIMIT 1
   FOR UPDATE OF op;
   ```
4. Если свободный оператор найден:
   * Выполняется `LPOP queue:line:{line_code}` в Redis.
   * В PostgreSQL обновляется тикет:
     ```sql
     UPDATE tickets 
     SET status = 'assigned', 
         assigned_operator_id = :operator_id, 
         assigned_at = clock_timestamp(),
         updated_at = clock_timestamp()
     WHERE id = :ticket_id AND status = 'queued';
     ```
   * В профиле оператора обновляется метка:
     ```sql
     UPDATE operator_profiles 
     SET last_assigned_at = clock_timestamp() 
     WHERE user_id = :operator_id;
     ```
   * Фиксируется транзакция.
   * Публикуется событие в `channel:operator:{operator_id}` для мгновенного отображения тикета в сайдбаре сотрудника.
5. Блокировка `lock:dispatch:line:{line_code}` снимается.

### 7.2. Сценарий освобождения рабочего слота

1. При закрытии обращения (`resolved`, `closed_by_inactivity`, `closed_by_moderation`):
   ```sql
   UPDATE tickets 
   SET status = :terminal_status, 
       closed_at = clock_timestamp(),
       updated_at = clock_timestamp()
   WHERE id = :ticket_id;
   ```
2. Удаляется ключ оперативного контекста в Redis: `DEL chat:context:{ticket_id}`.
3. Публикуется событие закрытия в `channel:ticket:{ticket_id}`.
4. Вызывается процедура распределения очереди для соответствующей линии (пункт 7.1).

### 7.3. Сценарий перевода на другую линию поддержки

1. Текущий тикет освобождает слот текущего оператора, сохраняя причину перевода:
   ```sql
   UPDATE tickets 
   SET status = 'queued',
       line_id = :new_line_id,
       transferred_from_operator_id = assigned_operator_id,
       transfer_comment = :transfer_comment,
       assigned_operator_id = NULL,
       assigned_at = NULL,
       opened_at = NULL,
       updated_at = clock_timestamp()
   WHERE id = :ticket_id;
   ```
2. В таблицу `messages` сохраняется служебное системное сообщение (`sender_type = 'system'`) с текстом комментария перевода, чтобы новый специалист сразу увидел его в истории диалога.
3. Идентификатор тикета добавляется в очередь новой линии:
   `RPUSH queue:line:{new_line_code} "{ticket_id}"`
4. Инициируется распределение для старой линии (слот освободился) и для новой линии (появился новый тикет).

---

## 8. Краевые случаи и аварийное восстановление

* **Холодный перезапуск Redis:** при падении или перезапуске экземпляра Redis очереди восстанавливаются стартовым фоновым процессом запросом в PostgreSQL:
  ```sql
  SELECT t.id, sl.code AS line_code
  FROM tickets t
  JOIN support_lines sl ON sl.id = t.line_id
  WHERE t.status = 'queued'
  ORDER BY t.created_at ASC;
  ```
  Идентификаторы пакетом помещаются в соответствующие ключи `queue:line:{line_code}` через `RPUSH`.
* **Защита от утечки зависших блокировок:** все ключи распределенной блокировки имеют жесткий TTL (5 секунд). При падении воркера во время распределения блокировка снимется автоматически.
* **Каскадное удаление данных:** удаление учетных записей (`users`) защищено ограничением `ON DELETE RESTRICT` для предотвращения потери исторических диалогов и тикетов. Удаление тикета каскадно удаляет связанные сообщения, подсказки, отзывы и аудиты.
