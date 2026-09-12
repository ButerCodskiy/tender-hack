# Артефакты экспорта базы знаний (ADR-0001: Small-to-Big Retrieval)

Файлы подготовлены для быстрого переноса и развертывания на демонстрационном ноутбуке без необходимости повторного тяжелого парсинга и GPU-векторизации.

## Состав файлов:

1. **`kb_data.sql`** (4.4 MB) — дамп PostgreSQL, содержащий все спаршенные нормативные документы (`kb_documents`) и родительские узлы AST со всеми неразрывными Markdown-таблицами (`kb_nodes`).
2. **`tender_chunks.snapshot`** (16.1 MB) — бинарный снапшот Qdrant коллекции `tender_chunks` (1587 точек, 1024D вектор `BAAI/bge-m3`, Cosine distance, минималистичный payload `{chunk_id, node_id, document_id, section_path}`).
3. **`restore_kb.py`** — скрипт восстановления в 1 клик для ноутбука.

## Инструкция по восстановлению на демонстрационном ноутбуке:

### Вариант 1. Автоматический (через скрипт):
```bash
python artifacts_export/restore_kb.py
```

### Вариант 2. Вручную через терминал:

1. **Импорт таблиц базы знаний в PostgreSQL:**
   ```bash
   docker exec -i rag_postgres psql -U rag_user -d rag_db < artifacts_export/kb_data.sql
   ```

2. **Восстановление векторной коллекции в Qdrant:**
   ```bash
   curl -X POST "http://localhost:6333/collections/tender_chunks/snapshots/upload?priority=snapshot" \
        -H "Content-Type: application/octet-stream" \
        --data-binary "@artifacts_export/tender_chunks.snapshot"
   ```

3. **Проверка готовности:**
   ```bash
   curl http://localhost:6333/collections/tender_chunks
   ```
