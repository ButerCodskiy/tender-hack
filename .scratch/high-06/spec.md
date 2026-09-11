# Спецификация задачи HIGH-06: Импорт структурированных таблиц типовых вопросов и ответов (FAQ Loader)

## 1. Контекст и границы модуля
- **Зона ответственности (Разработчик 3):**
  - `backend/src/kb/faq_loader.py`
  - `backend/src/kb/schemas.py`
  - `backend/src/kb/service.py` (интеграция метода загрузки)
  - `backend/tests/kb/test_faq_loader.py`
- **Назначение:** Прямой импорт готовых пар «вопрос-ответ» из форматов XLSX и CSV в обход модуля разбора Docling с генерацией синтетических сущностей для соблюдения ссылочной целостности базы данных и индексацией в векторное хранилище Qdrant.

---

## 2. Архитектурные инварианты (Строго по ТЗ хакатона)

### 2.1. Синтетические документы и узлы (Foreign Key Integrity)
В реляционной схеме чанки жестко связаны внешним ключом: `kb_chunks.node_id REFERENCES kb_nodes(node_id)`[cite: 2, 7]. Чтобы не нарушать целостность:
1. Для каждого загружаемого файла создается синтетический документ в `kb_documents`:
   - `doc_id = 'DOC_FAQ_' || md5(filename)`[cite: 2]
   - `title = filename`[cite: 2]
   - `regime = 'MOS_PORTAL'`[cite: 2]
   - `status = 'indexed'`[cite: 2, 7]
   - `edition_date = CURRENT_DATE`[cite: 2]
2. Создается синтетический родительский узел в `kb_nodes`:
   - `node_id = 'NODE_FAQ_' || md5(filename)`[cite: 2]
   - `doc_id = 'DOC_FAQ_' || md5(filename)`[cite: 2]
   - `level = 'item'`[cite: 2, 7]
   - `section_path = 'FAQ Import > ' || filename`[cite: 2]
   - `title = 'База типовых вопросов'`[cite: 2]
   - `full_content = 'Синтетический контейнер импорта FAQ'`[cite: 2, 7]
   - `token_count = 0`[cite: 2, 7]
3. Каждая строка (пара «вопрос-ответ») сохраняется в `kb_chunks`:
   - `chunk_id = 'chunk_faq_' || md5(filename || '_' || row_idx)`
   - `node_id = 'NODE_FAQ_' || md5(filename)`[cite: 2]
   - `text = 'Вопрос: ' || question || '\nОтвет: ' || answer`[cite: 2]
   - `context_prefix = NULL`[cite: 2]
   - `embedding_model_version = 'bge-m3'`[cite: 2, 7]

### 2.2. Контракт индексации в Qdrant (Коллекция knowledge_base)
Точки в Qdrant сохраняются со строгой типизацией payload для обеспечения фильтрации FAQ Fast-Path:
- `chunk_id`: str
- `node_id`: str[cite: 2]
- `doc_id`: str[cite: 2]
- `regime`: 'MOS_PORTAL'[cite: 2]
- `kb_type`: 'faq'[cite: 2]
- `kind`: 'qa_pair'[cite: 2]
- `status`: 'ACTIVE'[cite: 2]
- `text`: исходный текст чанка[cite: 2]
- `question`: очищенный текст вопроса (для быстрого сопоставления)
- `answer`: эталонный текст ответа
- `has_table`: false[cite: 2]

---

## 3. Требования к парсингу файлов
1. **Поддержка XLSX:** Использование `openpyxl`. Автоматическое определение колонок (поиск заголовков `вопрос`/`question` и `ответ`/`answer`, либо чтение первых двух колонок при отсутствии заголовков).
2. **Поддержка CSV:** Автоопределение разделителя (`,` или `;`) и кодировки (UTF-8, UTF-8-SIG, CP1251).
3. **Очистка данных:** Пропуск пустых строк, стрип пробелов, экранирование спецсимволов.

---

## 4. Изоляция и заглушки
- Для работы с эмбеддингами объявляется протокол `EmbeddingClientProtocol` с методом `embed_texts(texts: list[str]) -> list[list[float]]`.
- Для локальных тестов предоставляется `MockEmbeddingClient` (возвращает фиксированные векторы 1024D для BAAI/bge-m3)[cite: 2].
- База данных: использование асинхронных сессий SQLAlchemy 2.0 (`AsyncSession`) через репозиторий `KbRepository`[cite: 4, 7].