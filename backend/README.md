# RAG Backend — Подсистема парсинга и индексации базы знаний (KB Ingestion)

Автономный production-ready конвейер парсинга регламентов, методичек и нормативных документов закупочных процедур с использованием **Docling** и **PyMuPDF**, построенный строго по [Спецификации RAG (раздел 0 и 1)](../docs/RAG_AND_PARSING_SPECIFICATION.md).

---

## 📁 Структура модуля `src/kb/`

```text
backend/
├── pyproject.toml                     # Зависимости, конфигурация Ruff и Pytest
├── README.md                          # Документация подсистемы
├── notebooks/
│   └── docling_ingestion.ipynb        # Интерактивный ноутбук для Google Colab / Kaggle c GPU
├── src/
│   └── kb/
│       ├── __init__.py                # Публичный интерфейс пакета
│       ├── parser.py                  # DocumentParser (PyMuPDF vs Docling AST, OCR, контроль полноты 5%)
│       ├── chunker.py                 # HierarchicalChunker (Header Propagation, линеаризация таблиц, Parent Expansion)
│       ├── tables.py                  # TableProcessor (TableFormer, Markdown-генерация)
│       ├── schemas.py                 # Pydantic v2 схемы (ParsedDocument, ParsedNode, ParsedChunk, Profiling)
│       ├── profiler.py                # PipelineProfiler (замер этапов, RAM/VRAM, защита от OOM и утечек памяти)
│       └── cli.py                     # CLI-раннер пакетного парсинга с инкрементальной атомарной записью
└── tests/
    └── parser/                        # Выделенный пакет тестов конвейера парсинга
        ├── __init__.py
        ├── test_kb_parser.py          # Тесты контроля полноты и OCR
        ├── test_kb_chunker.py         # Тесты иерархического чанкинга и лимитов токенов
        ├── test_kb_tables.py          # Тесты извлечения и линеаризации таблиц
        ├── test_kb_schemas.py         # Тесты DDL-соответствия Pydantic-схем
        ├── test_kb_profiler.py        # Тесты замеров времени, RAM/VRAM и атомарной записи
        └── test_kb_cli.py             # Сквозные интеграционные тесты CLI
```

---

## 🚀 Ключевые возможности

1. **Контроль полноты извлечения текста (PyMuPDF vs Docling):**
   * Извлечение печатных символов через `fitz` и сравнение с объемом Docling.
   * При расхождении $> 5\%$ выставляется флаг `needs_manual_review = True` с логированием предупреждения.
   * Для сканов (число символов PyMuPDF $< 100$) контроль полноты автоматически отключается во избежание ложных срабатываний.
2. **Иерархический чанкинг и Header Propagation:**
   * Построение AST-дерева разделов (`H1 > H2 > H3 > статья > пункт`).
   * Проброс полного пути заголовков (`section_path`) в каждый чанк.
   * Линеаризация таблиц в Markdown-представление с флагом `is_table = True`.
   * Контекстное окно чанков: целевой размер 400 токенов (окно 300–500 токенов, хвосты $< 100$ склеиваются).
3. **Сквозное профилирование производительности (`profiler.py`):**
   * Детальный замер wall time каждого этапа: `extract_pymupdf_text`, `docling_conversion`, `table_extraction`, `header_propagation`, `hierarchical_chunking`, `json_serialization`.
   * Мониторинг потребления оперативной памяти (RAM RSS) и видеопамяти GPU (`torch.cuda.memory_allocated`).
   * Защита от OOM и утечек памяти: принудительный вызов `gc.collect()` и очистка кэша CUDA при потреблении RAM $> 80\%$ или дельте $> 500$ МБ.
   * Режимы работы: `--mode fast` (легковесный CPU/GPU анализ) и `--mode accurate` (полная модель TableFormer + расширенный OCR).
4. **Отказоустойчивость и атомарный сброс:**
   * Инкрементальная запись результатов каждого документа через временный файл (`atomic_write_json`) для защиты от потери данных при падении процесса.
   * Полная DDL-консистентность с PostgreSQL-схемами (`kb_documents`, `kb_nodes`, `kb_chunks`).

---

## 🛠 Запуск через CLI

```bash
# Базовый запуск конвейера в быстром режиме (fast)
python -m src.kb.cli --input-dir /path/to/docs --output-dir /path/to/output --mode fast

# Точный режим с TableFormer и EasyOCR
python -m src.kb.cli --input-dir /path/to/docs --output-dir /path/to/output --mode accurate

# С сохранением профилировочного отчета
python -m src.kb.cli \
  --input-dir ./documents \
  --output-dir ./parsed_output \
  --mode fast \
  --profile-report ./parsed_output/profiling_summary.json
```

---

## 🧪 Запуск тестового набора

Тесты парсера изолированы в каталоге `tests/parser/`:

```bash
# Запуск всех 19 тестов подсистемы парсинга
pytest tests/parser/ -v

# Быстрый запуск
pytest tests/ -q
```
