# ADR 0001: Архитектура хранения базы знаний, синхронизация Qdrant и иерархический чанкинг

* **Статус:** Принято (Accepted, с учетом архитектурного аудита)
* **Дата:** 2026-09-08
* **Домен:** `backend/src/kb/`, `backend/src/rag/`
* **Спецификации:** [docs/RAG_AND_PARSING_SPECIFICATION.md](../RAG_AND_PARSING_SPECIFICATION.md), [docs/DATABASE_SPECIFICATION.md](../DATABASE_SPECIFICATION.md), [docs/API_SPECIFICATION.md](../API_SPECIFICATION.md)

---

## 1. Контекст (Context)

Для работы гибридного поиска и генеративного конвейера RAG требуется надежное первичное хранилище нормативных документов, регламентов и пользовательских инструкций Портала поставщиков Москвы.

В ходе проектирования подсистемы базы знаний (`src/kb/`) были согласованы следующие ключевые требования и архитектурные границы:
1. **Реляционное первичное хранилище (PostgreSQL):**
   Необходимо хранить иерархию AST документов (`kb_documents` $\to$ `kb_nodes` $\to$ `kb_chunks`), таблицы в формате Markdown, метаданные и граф нормативных ссылок (`kb_article_references`). Первичные ключи согласно спецификации базы данных заданы как `VARCHAR(64)` (например, `chunk_portal_zakupki_reglament_sec4_p1`, `DOC_REGLAMENT_ZAKUPKI_MOS`).
2. **Векторное хранилище (Qdrant):**
   Векторная база требует, чтобы идентификатор точки (`PointStruct.id`) был строго `UUID` или 64-битным беззнаковым целым числом (`unsigned int`). Строковые идентификаторы произвольного формата напрямую в качестве ID точки не поддерживаются.
3. **Размерность и профили векторов:**
   Поисковое ядро использует двухканальный поиск: плотные эмбеддинги `bge-m3` (1024D) и разреженные лексические векторы `BM25`. Коллекция обязана поддерживать оба именованных вектора.
4. **Алгоритм нарезки текста (чанкинг) и токенизация:**
   Ограничение максимального размера чанка зафиксировано в 350 токенов. Токенизация для чанкинга в unit-тестах и локальном контуре фиксируется на базе библиотеки `tiktoken` (`cl100k_base`), что исключает сетевые вызовы и тяжелые зависимости `transformers`.
5. **Топологический порядок вставки дерева AST:**
   Таблица `kb_nodes` содержит самоссылку `parent_node_id REFERENCES kb_nodes(node_id)`. При пакетном сохранении документа вставка узлов обязана выполняться строго топологически (от корня к листьям), предотвращая ошибку `ForeignKeyViolation`.
6. **Транспортная асинхронность загрузки (`POST /api/v1/kb/documents/upload`):**
   HTTP-эндпоинт обязан быть неблокирующим (`202 Accepted`), сохраняя файлы в единый каталог `settings.KB_STORAGE_DIR` (`storage/kb_documents/`) и делегируя разбор задаче Taskiq. Эндпоинты реестра и статусов (`GET /documents`) исключены из скоупа текущей задачи (относятся к HIGH-07).
7. **Координация команды и регламент ветвления:**
   Чтобы исключить блокировку Разработчика 4 (ответственного за общую инфраструктуру, роутинг и релиз миграций), в рамках задачи [CRIT-03] запрещено создавать миграции в `alembic/versions/`, модифицировать `alembic/env.py` и править корневой `src/api/v1/router.py`. Модуль `kb` предоставляет только готовые декларативные модели `models.py` и экспортирует `kb_router` из `src/api/v1/kb.py`.

---

## 2. Архитектурное решение (Decision)

### 2.1. Модели базы данных PostgreSQL (`src/kb/models.py`)

Создаются декларативные модели SQLAlchemy 2.0 с наследованием от `src.db.database.Base`:
- **`KbDocumentModel` (`kb_documents`):**
  - `doc_id: Mapped[str]` — `VARCHAR(64)`, Primary Key;
  - `title: Mapped[str]` — `Text`, название документа;
  - `regime: Mapped[str]` — `VARCHAR(32)`, по умолчанию `'MOS_PORTAL'`;
  - `edition_date: Mapped[date | None]` — дата редакции;
  - `status: Mapped[str]` — `VARCHAR(16)`, `uploaded`, `indexing`, `indexed`, `failed`, `deprecated`;
  - `error_message: Mapped[str | None]` — текст ошибки;
  - `source_url: Mapped[str | None]` — ссылка на источник;
  - `created_at`, `updated_at: Mapped[datetime]` — таймстемпы с таймзоной (`settings.TIMEZONE`).
  - Связь: `nodes: Mapped[list["KbNodeModel"]] = relationship(back_populates="document", cascade="all, delete-orphan")`.

- **`KbNodeModel` (`kb_nodes`):**
  - `node_id: Mapped[str]` — `VARCHAR(64)`, Primary Key;
  - `doc_id: Mapped[str]` — `ForeignKey("kb_documents.doc_id", ondelete="CASCADE")`;
  - `parent_node_id: Mapped[str | None]` — `ForeignKey("kb_nodes.node_id", ondelete="CASCADE")`;
  - `level: Mapped[str]` — `VARCHAR(16)` (`document`, `section`, `article`, `part`, `item`);
  - `section_path: Mapped[str]` — путь по дереву AST;
  - `article_no: Mapped[str | None]`, `part_no: Mapped[str | None]`;
  - `title: Mapped[str]`, `full_content: Mapped[str]`;
  - `table_md: Mapped[str | None]` — сырая сетка Markdown;
  - `token_count: Mapped[int]`;
  - Связи: `document`, `parent_node`, `children_nodes`, `chunks: Mapped[list["KbChunkModel"]] = relationship(cascade="all, delete-orphan")`.

- **`KbChunkModel` (`kb_chunks`):**
  - `chunk_id: Mapped[str]` — `VARCHAR(64)`, Primary Key;
  - `node_id: Mapped[str]` — `ForeignKey("kb_nodes.node_id", ondelete="CASCADE")`;
  - `text: Mapped[str]` — текст фрагмента;
  - `context_prefix: Mapped[str | None]` — префикс от LLM;
  - `hyp_questions: Mapped[list[str]]` — `JSONB`, список гипотетических вопросов;
  - `embedding_model_version: Mapped[str]` — версия модели эмбеддингов (`bge-m3`);
  - `created_at: Mapped[datetime]`.

- **`KbArticleReferenceModel` (`kb_article_references`):**
  - `id: Mapped[int]` — PK (Serial);
  - `from_node_id: Mapped[str]` — `ForeignKey("kb_nodes.node_id", ondelete="CASCADE")`;
  - `to_node_id: Mapped[str | None]` — `ForeignKey("kb_nodes.node_id", ondelete="SET NULL")`;
  - `raw_label: Mapped[str]`.

### 2.2. Синхронизация идентификаторов между PostgreSQL и Qdrant

Для исключения рассинхронизации и необходимости хранения отдельной таблицы маппинга принимается детерминированная схема:
1. В PostgreSQL и в `payload` Qdrant хранится строковый `chunk_id` вида `{node_id}_c{idx}` (например, `chunk_portal_zakupki_reglament_sec4_p1`).
2. В качестве нативного ID точки `PointStruct.id` в Qdrant используется **детерминированный UUIDv5**:
   ```python
   import uuid

   QDRANT_CHUNK_NAMESPACE = uuid.UUID("a2b3c4d5-e6f7-4a5b-8c9d-0e1f2a3b4c5d")

   def chunk_id_to_qdrant_uuid(chunk_id: str) -> uuid.UUID:
       return uuid.uuid5(QDRANT_CHUNK_NAMESPACE, chunk_id)
   ```
3. Это гарантирует:
   - Идемпотентность повторных вставок (`upsert`) без риска дублирования точек;
   - Мгновенное прямое вычисление UUID точки по `chunk_id` без обращений к базе данных;
   - Поиск в Qdrant возвращает в payload оригинальный `chunk_id`, по которому RAG за $\le 1$ мс находит узел в PostgreSQL.

### 2.3. Конфигурация коллекции Qdrant (`knowledge_base`) и EmbeddingStub

1. **Единый клиент:** Модуль `kb` использует централизованный асинхронный клиент из `src.core.qdrant_client.get_qdrant_client()`. Создание дублирующих инстансов клиента внутри `kb` запрещено.
2. **Именованные векторы:** Коллекция `knowledge_base` настраивается с двумя векторами:
   - `dense`: размерность `1024`, метрика расстояния `Distance.COSINE` (под BAAI/bge-m3);
   - `sparse`: разреженные векторы под BM25 (структура `SparseVectorParams`).
3. **Двухвекторный тестовый стаб (`EmbeddingStub`):**
   Для автономных тестов без GPU/TEI стаб обязан генерировать точку со строго двумя векторами:
   - `dense`: `list[float]` длины 1024;
   - `sparse`: объект `qdrant_client.models.SparseVector(indices=[1, 2], values=[0.5, 0.8])`.
   Это исключает ошибки валидации схемы Qdrant API при вставке точек.

### 2.4. Топологическая вставка дерева AST в репозитории (`save_full_document_tree`)

Для гарантии ссылочной целостности сохранение дерева документа в `KbRepository` выполняется в строгой топологической последовательности:
1. `session.add(document)` (сохранение родительской записи `kb_documents`);
2. Топологическая сортировка узлов `kb_nodes`:
   - Сначала сохраняются узлы без родителя (`parent_node_id IS NULL`, уровень `document` / корневые разделы);
   - Затем дочерние узлы в порядке возрастания глубины AST (`section` $\to$ `article` $\to$ `part` / `item`);
3. Вставка всех чанков `kb_chunks` (каждый чанк ссылается на гарантированно существующий `node_id`);
4. Единый `await session.commit()` транзакции.

### 2.5. Алгоритм чанкинга и токенизация (`tiktoken`)

1. **Токенизация:**
   - Подсчет токенов выполняется строго через `tiktoken` с энкодингом `cl100k_base`.
   - Это обеспечивает детерминированный, быстрый и локальный расчет токенов без сетевых запросов и тяжелых зависимостей.
2. **Размер чанка и границы:**
   - Максимальный размер: `max_tokens = 350`.
   - Семантические границы: параграфы $\to$ предложения.
3. **Политика перекрытия (Overlap):**
   - Межчанковое перекрытие внутри узла принимается равным **0** (`overlap = 0`).
   - Семантическая связность восстанавливается на этапе генерации RAG с помощью алгоритма `Parent Expansion` (подтягивание родительского узла AST объемом до 2500 токенов).
4. **Подклейка коротких хвостов:**
   - Хвостовые фрагменты `< 80` токенов объединяются с предыдущим чанком (если суммарный объем $\le 450$ токенов).
5. **Формат идентификаторов:**
   - `node_id`: `{doc_id}_{section_slug}`
   - `chunk_id`: `{node_id}_c{idx}`

### 2.6. Эндпоинт `POST /api/v1/kb/documents/upload` и скоуп API

1. **Единый путь хранения:**
   Файлы сохраняются в директорию `settings.KB_STORAGE_DIR` (`storage/kb_documents/`). Разнобой `data/` и `uploads/` исключен.
2. **Скоуп эндпоинтов:**
   В рамках [CRIT-03] создается **строго один эндпоинт**: `POST /api/v1/kb/documents/upload`. Эндпоинты `GET /documents` и `GET /documents/{id}/status` исключены (вынесены в HIGH-07).
3. **Асинхронная очередь Taskiq:**
   Эндпоинт принимает пакет файлов, сохраняет их на диск, создает записи со статусом `uploaded`, ставит задачу `index_kb_document` в брокер Taskiq и возвращает `202 Accepted`.
4. **Синхронный конвейер для тестов и сидинга:**
   В `KbService` реализуется прямой метод `ingest_document(doc_id, file_path)`, вызываемый скриптом сидинга и модульными тестами в обход брокера.

---

## 3. Последствия (Consequences)

### Положительные:
1. **Отсутствие блокеров параллельной разработки:** Разработчик 4 может независимо управлять корневым `router.py` и генерировать централизованную миграцию.
2. **Надежность внешних ключей:** Топологическая вставка в `KbRepository` полностью исключает `ForeignKeyViolation`.
3. **Стабильность тестов Qdrant:** Двухвекторный стаб `EmbeddingStub` (dense + sparse) удовлетворяет схеме коллекции `knowledge_base` без падений API.
4. **Быстрые и изолированные тесты:** `tiktoken` позволяет мгновенно тестировать чанкинг без тяжелых библиотек и GPU.

### Риски и компенсация:
- *Риск:* Небольшое отличие в количестве токенов между `tiktoken (cl100k_base)` и токенизатором `bge-m3` (SentencePiece).
  *Компенсация:* Запас лимита в 350 токенов (контекстное окно `bge-m3` составляет 8192 токена) гарантирует, что чанк гарантированно помещается в модель эмбеддингов с огромным запасом.

---

## 4. Инварианты связей и ограничения целостности (Data Invariants)

1. **Каскадность удаления (`ON DELETE CASCADE`):**
   Удаление записи в `kb_documents` каскадно удаляет все связанные узлы в `kb_nodes`, чанки в `kb_chunks` и нормативные ссылки в `kb_article_references`.
2. **Топологическая целостность:**
   В таблице `kb_nodes` родительский узел `parent_node_id` обязан существовать до создания дочернего узла.
3. **Отсутствие сирот (`No Orphan Chunks`):**
   Каждый чанк в `kb_chunks` строго ссылается на существующий `node_id`.
4. **Двухвекторное соответствие в Qdrant:**
   Каждая точка в коллекции `knowledge_base` имеет `PointStruct.id = uuid5(QDRANT_CHUNK_NAMESPACE, chunk_id)` и содержит оба вектора: `dense` (1024D) и `sparse`.
5. **Временные зоны:**
   Все поля времени (`created_at`, `updated_at`) сохраняются строго с часовым поясом `settings.TIMEZONE` (МСК, UTC+3).
