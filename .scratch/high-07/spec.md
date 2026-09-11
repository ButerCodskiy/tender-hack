# Спецификация задачи HIGH-07: REST API реестра документов и узлов базы знаний

## 1. Контекст и границы модуля
- **Файлы задачи:**
  - `backend/src/api/v1/kb.py` [MODIFY / CREATE]
  - `backend/src/kb/schemas.py` [MODIFY]
  - `backend/src/kb/repository.py` [MODIFY]
  - `backend/src/kb/service.py` [MODIFY]
  - `backend/tests/api/test_kb_api.py` [NEW]
- **Назначение:** Реализация REST API для фронтенда управления базой знаний (просмотр реестра документов, опрос статуса индексации, каскадное удаление документа и ручное редактирование метаданных узлов).

---

## 2. Контракты эндпоинтов (Строго по ТЗ хакатона)

### 2.1. GET /api/v1/kb/documents
- **Параметры (Query):**
  - `regime: Optional[str]` (фильтр: `MOS_PORTAL`, `LAW_44`, `LAW_223`)
  - `status: Optional[str]` (фильтр: `uploaded`, `parsing`, `indexing`, `indexed`, `failed`)
  - `limit: int = 20` (1..100)
  - `offset: int = 0` (>= 0)
- **Ответ (200 OK):** `KbDocumentListResponse`
  - `items: list[KbDocumentResponse]`
  - `total: int`
  - `limit: int`
  - `offset: int`

### 2.2. GET /api/v1/kb/documents/{doc_id}/status
- **Ответ (200 OK):** `KbDocumentStatusResponse`
  - `doc_id: str`
  - `status: str`
  - `error_message: Optional[str]`
  - `chunks_count: int` (количество связанных чанков в `kb_chunks`)
  - `updated_at: datetime`
- **Ошибки:** 404 Not Found, если документ не существует.

### 2.3. DELETE /api/v1/kb/documents/{doc_id}
- **Поведение (Каскадное удаление):**
  1. Удаление документа из `kb_documents` в PostgreSQL (благодаря DDL `ON DELETE CASCADE` удаляются связанные `kb_nodes` и `kb_chunks`).
  2. Удаление всех векторных точек из коллекции Qdrant `knowledge_base` по фильтру `doc_id == {doc_id}`.
- **Ответ (200 OK):** `KbDocumentDeleteResponse(deleted=True, doc_id=doc_id)`
- **Ошибки:** 404 Not Found, если документ не найден.

### 2.4. PATCH /api/v1/kb/nodes/{node_id}
- **Тело запроса:** `KbNodeUpdateRequest`
  - `title: Optional[str]`
  - `section_path: Optional[str]`
  - `importance_weight: Optional[float]`
- **Поведение:**
  - Обновление метаданных узла в PostgreSQL (`kb_nodes`).
  - Синхронное/асинхронное обновление payload в точках Qdrant для всех чанков, принадлежащих этому `node_id` (если изменился заголовок или путь).
- **Ответ (200 OK):** `KbNodeResponse`
- **Ошибки:** 404 Not Found, если узел не найден.

---

## 3. Архитектурные инварианты (AST & Clean Architecture)
1. **Изоляция слоев:** Роутер в `api/v1/kb.py` не имеет права напрямую выполнять SQL-запросы (`select`, `delete` через ORM). Все операции делегируются методам `KbService`.
2. **Асинхронность:** Все вызовы к БД и Qdrant строго через `await`.