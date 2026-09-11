"""CLI-интерфейс для конвейера парсинга документов и экспорта базы знаний (src.kb.cli).

Примеры запуска:
    uv run python -m src.kb.cli ingest --dir storage/kb_documents
    uv run python -m src.kb.cli ingest --dir ./data/regulations --out-dir storage/kb_export --mode fast
    uv run python -m src.kb.cli ingest --input ./data/sample.pdf --out-dir storage/kb_export --doc-id DOC_44FZ

Генерирует согласованные артефакты базы знаний:
1. parsed_documents.json    -> метаданные документов (kb_documents)
2. parsed_nodes.json        -> иерархическое дерево AST (kb_nodes)
3. parsed_chunks.json       -> поисковые фрагменты (kb_chunks)
4. completeness_reports.json -> журнал контроля полноты (Docling vs PyMuPDF)
5. summary_statistics.json  -> сводная статистика объемов БЗ
6. profiling_report.json    -> метрики скорости, времени стадий и памяти (RAM/VRAM)
7. markdown/                -> структурированное дерево Markdown для демонстрации жюри
8. kb_export.zip            -> единый самодостаточный архив всех артефактов
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import traceback
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from tqdm import tqdm

from src.core.config import settings
from src.kb.faq_loader import FaqLoader, FaqParser
from src.kb.parser import DocumentParser
from src.kb.profiler import PipelineProfiler
from src.kb.schemas import (
    CompletenessReportSchema,
    ParsedChunkSchema,
    ParsedDocumentSchema,
    ParsedExtractionResultSchema,
    ParsedNodeSchema,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kb.cli")


# ────────────────────────────────────────────────────────────────
# Транслитерация и нормализация имен файлов (Slugifier)
# ────────────────────────────────────────────────────────────────

CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate_to_slug(text: str, max_length: int = 80) -> str:
    """Нормализует строку с кириллицей в безопасный ASCII-slug для файловой системы.

    - Транслитерирует кириллические символы в латиницу.
    - Оставляет только буквы и цифры, заменяя прочие символы на подчеркивание.
    - Схлопывает повторяющиеся подчеркивания и обрезает длину.
    """
    text = text.lower().strip()
    result_chars: list[str] = []
    for char in text:
        if char in CYRILLIC_TO_LATIN:
            result_chars.append(CYRILLIC_TO_LATIN[char])
        elif char.isalnum():
            result_chars.append(char)
        else:
            result_chars.append("_")

    slug = "".join(result_chars)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "document"
    return slug[:max_length].rstrip("_")


# ────────────────────────────────────────────────────────────────
# Атомарная запись JSON
# ────────────────────────────────────────────────────────────────


def atomic_write_json(target_path: Path, data: Any) -> None:
    """Атомарная запись данных в JSON-файл через временный файл .tmp

    для предотвращения повреждения файлов при прерывании процесса.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, target_path)


# ────────────────────────────────────────────────────────────────
# Маршрутизация и разбор FAQ-таблиц (XLSX, CSV)
# ────────────────────────────────────────────────────────────────


def is_faq_table_file(file_path: Path) -> bool:
    """Определяет, является ли файл таблицей FAQ по расширению и сигнатуре."""
    ext = file_path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xltx"):
        return True
    if ext == ".csv":
        try:
            sample = file_path.read_bytes()[:4096]
            text = sample.decode("utf-8", errors="ignore").lower()
            return any(
                keyword in text
                for keyword in (
                    "вопрос",
                    "question",
                    "тема",
                    "ответ",
                    "answer",
                    "решение",
                )
            )
        except Exception:
            return False
    return False


def parse_faq_table_document(
    file_path: Path,
    regime: str = "MOS_PORTAL",
) -> ParsedExtractionResultSchema:
    """Разбирает файл таблицы FAQ (XLSX/CSV) в структурированный результат ParsedExtractionResultSchema."""
    content = file_path.read_bytes()
    filename = file_path.name
    parsed_rows, total_rows = FaqParser.parse(content, filename)

    doc_id = FaqLoader.generate_doc_id(filename)
    node_id = FaqLoader.generate_node_id(filename)

    doc = ParsedDocumentSchema(
        doc_id=doc_id,
        title=f"База типовых вопросов: {file_path.stem}",
        regime=regime,
        edition_date=datetime.now(settings.TIMEZONE).date(),
        status="uploaded",
        source_url=f"faq://{filename}",
        is_scanned=False,
    )

    full_content_parts = [
        f"# База типовых вопросов и ответов: {file_path.stem}\n"
    ]
    for row in parsed_rows:
        full_content_parts.append(
            f"### Вопрос {row.row_idx}: {row.question}\n{row.answer}\n"
        )
    full_content = "\n".join(full_content_parts)

    root_node = ParsedNodeSchema(
        node_id=node_id,
        doc_id=doc_id,
        parent_node_id=None,
        level="section",
        section_path=f"FAQ Import > {file_path.stem}",
        article_no=None,
        part_no=None,
        title="Типовые вопросы и ответы",
        full_content=full_content,
        table_md=None,
        token_count=len(full_content.split()),
    )

    chunks: list[ParsedChunkSchema] = []
    for row in parsed_rows:
        chunk_id = FaqLoader.generate_chunk_id(filename, row.row_idx)
        chunk_text = f"Вопрос: {row.question}\nОтвет: {row.answer}"
        chunks.append(
            ParsedChunkSchema(
                chunk_id=chunk_id,
                node_id=node_id,
                text=chunk_text,
                has_table=False,
                token_count=len(chunk_text.split()),
            )
        )

    char_cnt = len(full_content)
    report = CompletenessReportSchema(
        doc_id=doc_id,
        pymupdf_char_count=char_cnt,
        docling_char_count=char_cnt,
        discrepancy_ratio=0.0,
        is_scanned=False,
        needs_manual_review=False,
        details=f"Импортировано {len(parsed_rows)} пар вопрос-ответ из таблицы FAQ (всего строк: {total_rows})",
    )

    return ParsedExtractionResultSchema(
        document=doc,
        nodes=[root_node],
        chunks=chunks,
        completeness_report=report,
        profiling=None,
    )


# ────────────────────────────────────────────────────────────────
# Генерация дерева файлов Markdown для жюри
# ────────────────────────────────────────────────────────────────


def generate_markdown_tree(
    documents: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    completeness_reports: list[dict[str, Any]],
    markdown_dir: Path,
) -> list[Path]:
    """Генерирует структурированное дерево файлов Markdown для демонстрации жюри:

    - markdown/README.md: сводный реестр базы знаний со ссылками и процентами полноты.
    - markdown/{doc_slug}.md: структурированный файл по каждому документу с TOC,
      заголовками, таблицами и якорными маркерами чанков.
    """
    markdown_dir.mkdir(parents=True, exist_ok=True)
    generated_files: list[Path] = []

    # Индексируем узлы и чанки по doc_id и node_id
    nodes_by_doc: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        d_id = n.get("doc_id", "")
        nodes_by_doc.setdefault(d_id, []).append(n)

    chunks_by_node: dict[str, list[dict[str, Any]]] = {}
    for c in chunks:
        n_id = c.get("node_id", "")
        chunks_by_node.setdefault(n_id, []).append(c)

    reports_by_doc: dict[str, dict[str, Any]] = {
        r.get("doc_id", ""): r for r in completeness_reports
    }

    doc_registry_rows: list[dict[str, Any]] = []
    used_slugs: dict[str, int] = {}

    for doc in documents:
        doc_id = doc.get("doc_id", "")
        title = doc.get("title", doc_id)
        regime = doc.get("regime", "MOS_PORTAL")
        edition_date = doc.get("edition_date", "")

        # Генерация уникального slug
        base_slug = transliterate_to_slug(title or doc_id)
        if base_slug in used_slugs:
            used_slugs[base_slug] += 1
            doc_slug = f"{base_slug}_{used_slugs[base_slug]}"
        else:
            used_slugs[base_slug] = 1
            doc_slug = base_slug

        doc_nodes = nodes_by_doc.get(doc_id, [])
        doc_chunks_count = sum(
            len(chunks_by_node.get(n.get("node_id", ""), []))
            for n in doc_nodes
        )
        report = reports_by_doc.get(doc_id, {})
        discrepancy = report.get("discrepancy_ratio", 0.0)
        completeness_pct = max(0.0, 100.0 - (discrepancy * 100.0))
        is_scanned = report.get("is_scanned", False)
        needs_review = report.get("needs_manual_review", False)

        doc_file_path = markdown_dir / f"{doc_slug}.md"

        # Формирование контента документа
        lines: list[str] = [
            f"# {title}",
            "",
            "> **Метаданные документа базы знаний:**",
            f"> - **ID:** `{doc_id}`",
            f"> - **Режим:** `{regime}`",
            f"> - **Дата редакции:** `{edition_date}`",
            f"> - **Полнота извлечения:** `{completeness_pct:.1f}%` (Docling: {report.get('docling_char_count', 0):,} симв. / PyMuPDF: {report.get('pymupdf_char_count', 0):,} симв.)",
            f"> - **Статус контроля:** {'⚠️ Требует ручной проверки' if needs_review else ('📷 Графический скан' if is_scanned else '✅ Верифицирован')}",
            "",
            "---",
            "",
            "## Содержание документа",
            "",
        ]

        # Оглавление (TOC)
        for idx, node in enumerate(doc_nodes, 1):
            n_title = node.get("title", f"Раздел {idx}")
            anchor = transliterate_to_slug(n_title)
            lines.append(f"{idx}. [{n_title}](#{anchor})")

        lines.extend(["", "---", ""])

        # Основной текст по узлам
        for node in doc_nodes:
            n_id = node.get("node_id", "")
            n_title = node.get("title", "")
            n_level = node.get("level", "section")
            n_content = node.get("full_content", "").strip()
            table_md = node.get("table_md")
            sec_path = node.get("section_path", "")

            # Заголовок узла
            h_prefix = (
                "##"
                if n_level == "section"
                else ("###" if n_level == "article" else "####")
            )
            lines.append(f"{h_prefix} {n_title}")
            if sec_path and sec_path != n_title:
                lines.append(f"*Иерархия: `{sec_path}`*")
            lines.append("")

            if n_content:
                lines.append(n_content)
                lines.append("")

            if table_md:
                lines.append(table_md.strip())
                lines.append("")

            # Маркеры чанков
            node_chunks = chunks_by_node.get(n_id, [])
            if node_chunks:
                chunk_labels = [
                    f"`{c.get('chunk_id')}` ({c.get('token_count') or len(c.get('text', '').split())} токенов{' 📊 таблица' if c.get('has_table') else ''})"
                    for c in node_chunks
                ]
                lines.append(
                    f"> 🔖 **Поисковые фрагменты (Qdrant):** {', '.join(chunk_labels)}"
                )
                lines.append("")

            lines.append("---")
            lines.append("")

        with open(doc_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        generated_files.append(doc_file_path)

        doc_registry_rows.append(
            {
                "title": title,
                "slug_filename": f"{doc_slug}.md",
                "doc_id": doc_id,
                "nodes_count": len(doc_nodes),
                "chunks_count": doc_chunks_count,
                "completeness_str": f"{completeness_pct:.1f}%",
                "status": "⚠️ Ревью"
                if needs_review
                else ("📷 Скан" if is_scanned else "✅ OK"),
            }
        )

    # Генерация корневого README.md
    readme_path = markdown_dir / "README.md"
    now_str = datetime.now(settings.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S MSK")
    readme_lines: list[str] = [
        "# Каталог регламентов и базы знаний (Knowledge Base Export)",
        "",
        f"**Дата экспорта:** `{now_str}`  ",
        f"**Всего документов:** `{len(documents)}` | **Всего узлов AST:** `{len(nodes)}` | **Всего чанков:** `{len(chunks)}`",
        "",
        "> Экспорт структурирован для демонстрации жюри и ручного аудита. Каждый документ содержит нативную Markdown-разметку, оглавление, оригинальные сетки таблиц и сквозные маркеры поисковых чанков Qdrant.",
        "",
        "---",
        "",
        "## Реестр документов базы знаний",
        "",
        "| № | Документ | Узлов AST | Чанков | Полнота PyMuPDF | Статус |",
        "|---|---|---|---|---|---|",
    ]

    for idx, r in enumerate(doc_registry_rows, 1):
        readme_lines.append(
            f"| {idx} | [{r['title']}]({r['slug_filename']}) | {r['nodes_count']} | {r['chunks_count']} | {r['completeness_str']} | {r['status']} |"
        )

    readme_lines.extend(
        [
            "",
            "---",
            "*Сгенерировано автоматически подсистемой пакетной обработки базы знаний MED-06.*",
        ]
    )

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines))
    generated_files.append(readme_path)

    return generated_files


# ────────────────────────────────────────────────────────────────
# Сводная статистика объемов базы знаний
# ────────────────────────────────────────────────────────────────


def build_summary_statistics(
    documents: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    completeness_reports: list[dict[str, Any]],
    failed_files: list[dict[str, Any]],
    duration_sec: float,
) -> dict[str, Any]:
    """Формирует агрегированную структуру сводной статистики по базе знаний."""
    total_docs = len(documents) + len(failed_files)
    success_docs = len(documents)

    # Статистика узлов по уровням
    nodes_by_level: dict[str, int] = {}
    tables_count = 0
    for n in nodes:
        lvl = n.get("level", "item")
        nodes_by_level[lvl] = nodes_by_level.get(lvl, 0) + 1
        title_lower = n.get("title", "").lower()
        if (
            n.get("table_md")
            or "таблиц" in title_lower
            or "table" in title_lower
        ):
            tables_count += 1

    # Статистика чанков и токенов
    total_tokens = 0
    chunks_with_tables = 0
    max_chunk_tokens = 0
    for c in chunks:
        tok = c.get("token_count") or len(c.get("text", "").split())
        total_tokens += tok
        max_chunk_tokens = max(max_chunk_tokens, tok)
        if c.get("has_table"):
            chunks_with_tables += 1

    avg_tokens = (
        round(total_tokens / max(len(chunks), 1), 1) if chunks else 0.0
    )

    # Статистика полноты PyMuPDF
    scanned_count = sum(
        1 for r in completeness_reports if r.get("is_scanned", False)
    )
    manual_review_count = sum(
        1 for r in completeness_reports if r.get("needs_manual_review", False)
    )
    avg_discrepancy = (
        sum(r.get("discrepancy_ratio", 0.0) for r in completeness_reports)
        / max(len(completeness_reports), 1)
        if completeness_reports
        else 0.0
    )

    return {
        "generated_at": datetime.now(settings.TIMEZONE).isoformat(),
        "duration_seconds": round(duration_sec, 2),
        "documents": {
            "total_submitted": total_docs,
            "successfully_parsed": success_docs,
            "failed_count": len(failed_files),
        },
        "nodes": {
            "total_count": len(nodes),
            "by_level": nodes_by_level,
        },
        "chunks": {
            "total_count": len(chunks),
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": avg_tokens,
            "max_tokens_chunk": max_chunk_tokens,
            "chunks_with_tables": chunks_with_tables,
        },
        "tables": {
            "total_tables_extracted": tables_count,
        },
        "completeness_validation": {
            "avg_discrepancy_ratio": round(avg_discrepancy, 4),
            "avg_completeness_percent": round(
                max(0.0, 100.0 - (avg_discrepancy * 100.0)), 2
            ),
            "scanned_documents_count": scanned_count,
            "manual_review_required_count": manual_review_count,
        },
        "failed_files": failed_files,
    }


# ────────────────────────────────────────────────────────────────
# Упаковка в единый ZIP-архив
# ────────────────────────────────────────────────────────────────


def create_export_archive(
    export_dir: Path, archive_name: str = "kb_export.zip"
) -> Path:
    """Упаковывает все JSON-дампы, отчеты и сгенерированное дерево Markdown

    в единый самодостаточный ZIP-архив с атомарной фиксацией через временный файл.
    """
    archive_path = export_dir / archive_name
    tmp_path = archive_path.with_suffix(".zip.tmp")

    with zipfile.ZipFile(
        tmp_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        # 1. Запись всех JSON файлов верхнего уровня
        for json_file in sorted(export_dir.glob("*.json")):
            zf.write(json_file, arcname=json_file.name)

        # 2. Запись дерева файлов Markdown
        markdown_dir = export_dir / "markdown"
        if markdown_dir.exists():
            for md_file in sorted(markdown_dir.rglob("*.md")):
                if md_file.is_file():
                    rel_path = md_file.relative_to(export_dir)
                    zf.write(md_file, arcname=str(rel_path).replace("\\", "/"))

    os.replace(tmp_path, archive_path)
    return archive_path


# ────────────────────────────────────────────────────────────────
# Консольное форматирование таблиц (Stdout)
# ────────────────────────────────────────────────────────────────


def format_completeness_table(
    completeness_reports: list[dict[str, Any]],
) -> str:
    """Форматирует отчет контроля полноты извлечения символов в виде ASCII-таблицы."""
    if not completeness_reports:
        return ""

    header = f"{'Документ (doc_id)':<36} | {'Docling':>10} | {'PyMuPDF':>10} | {'Дельта %':>9} | {'Скан':^6} | {'Статус':^8}"
    separator = "-" * len(header)
    rows: list[str] = [
        "",
        "=" * len(header),
        "       ОТЧЕТ КОНТРОЛЯ ПОЛНОТЫ ИЗВЛЕЧЕНИЯ СИМВОЛОВ (PyMuPDF vs Docling)",
        "=" * len(header),
        header,
        separator,
    ]

    for r in completeness_reports:
        doc_id = r.get("doc_id", "")[:35]
        docling_c = f"{r.get('docling_char_count', 0):,}"
        pymupdf_c = f"{r.get('pymupdf_char_count', 0):,}"
        ratio = r.get("discrepancy_ratio", 0.0)
        delta_str = f"{ratio * 100.0:.2f}%"
        is_scanned = "Да" if r.get("is_scanned") else "Нет"
        status = "РЕВЬЮ" if r.get("needs_manual_review") else "OK"
        rows.append(
            f"{doc_id:<36} | {docling_c:>10} | {pymupdf_c:>10} | {delta_str:>9} | {is_scanned:^6} | {status:^8}"
        )

    rows.append("=" * len(header))
    return "\n".join(rows)


def format_summary_table(stats: dict[str, Any]) -> str:
    """Форматирует сводную статистику объемов базы знаний в виде ASCII-блока."""
    docs = stats.get("documents", {})
    nodes = stats.get("nodes", {})
    chunks = stats.get("chunks", {})
    tables = stats.get("tables", {})
    comp = stats.get("completeness_validation", {})
    duration = stats.get("duration_seconds", 0.0)

    lines = [
        "",
        "================================================================================",
        "                    СВОДНАЯ СТАТИСТИКА БАЗЫ ЗНАНИЙ (KB EXPORT)",
        "================================================================================",
        f"Документов обработано:       {docs.get('total_submitted', 0)} (успешно: {docs.get('successfully_parsed', 0)}, с ошибками: {docs.get('failed_count', 0)})",
        f"Узлов AST (структура):       {nodes.get('total_count', 0)} (секций: {nodes.get('by_level', {}).get('section', 0)}, статей: {nodes.get('by_level', {}).get('article', 0)}, пунктов: {nodes.get('by_level', {}).get('item', 0)})",
        f"Поисковых чанков:            {chunks.get('total_count', 0)}",
        f"Чанков с таблицами:          {chunks.get('chunks_with_tables', 0)}",
        f"Суммарно токенов в чанках:   {chunks.get('total_tokens', 0):,} (в среднем: {chunks.get('avg_tokens_per_chunk', 0.0)} токенов/чанк)",
        f"Извлечено таблиц:            {tables.get('total_tables_extracted', 0)}",
        f"Средняя полнота PyMuPDF:     {comp.get('avg_completeness_percent', 0.0)}% (сканов: {comp.get('scanned_documents_count', 0)}, ревью: {comp.get('manual_review_required_count', 0)})",
        f"Время обработки конвейера:   {duration:.2f} сек",
        "================================================================================",
    ]
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# Главная логика пакетного Ingest
# ────────────────────────────────────────────────────────────────


def run_ingest(
    input_path: Path,
    out_dir: Path,
    doc_id: str | None = None,
    regime: str = "MOS_PORTAL",
    mode: Literal["accurate", "fast"] = "accurate",
    enable_profiling: bool = True,
    create_archive: bool = True,
) -> int:
    """Пакетная обработка файлов с инкрементальным сохранением, профилированием,

    генерацией дерева Markdown и единого ZIP-архива.

    Возвращает:
        0 - все файлы обработаны успешно;
        2 - частичный успех (были ошибки в отдельных файлах);
        1 - критическая инфраструктурная ошибка (каталог не существует и т.п.).
    """
    start_time = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)

    target_files: list[Path] = []
    if input_path.is_file():
        target_files = [input_path]
    elif input_path.is_dir():
        for ext in (
            "*.pdf",
            "*.PDF",
            "*.docx",
            "*.DOCX",
            "*.txt",
            "*.md",
            "*.xlsx",
            "*.XLSX",
            "*.xlsm",
            "*.csv",
            "*.CSV",
        ):
            target_files.extend(list(input_path.glob(ext)))
        target_files = sorted(set(target_files))
    else:
        logger.error("Входной путь не существует: %s", input_path)
        return 1

    if not target_files:
        logger.warning(
            "В директории %s не найдено поддерживаемых файлов для разбора.",
            input_path,
        )
        return 0

    logger.info(
        "Найдено файлов для разбора: %d (режим: %s, каталог назначения: %s)",
        len(target_files),
        mode,
        out_dir,
    )

    parser = DocumentParser(mode=mode)
    pipeline_profiler = PipelineProfiler() if enable_profiling else None

    doc_file = out_dir / "parsed_documents.json"
    node_file = out_dir / "parsed_nodes.json"
    chunk_file = out_dir / "parsed_chunks.json"
    report_file = out_dir / "completeness_reports.json"
    profiling_file = out_dir / "profiling_report.json"
    summary_file = out_dir / "summary_statistics.json"

    # Загружаем уже существующие файлы для дозаписи при повторном запуске
    all_documents: list[dict[str, Any]] = []
    all_nodes: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []
    all_reports: list[dict[str, Any]] = []
    failed_files: list[dict[str, Any]] = []

    if doc_file.exists():
        try:
            with open(doc_file, encoding="utf-8") as f:
                all_documents = json.load(f)
        except Exception:
            all_documents = []

    if node_file.exists():
        try:
            with open(node_file, encoding="utf-8") as f:
                all_nodes = json.load(f)
        except Exception:
            all_nodes = []

    if chunk_file.exists():
        try:
            with open(chunk_file, encoding="utf-8") as f:
                all_chunks = json.load(f)
        except Exception:
            all_chunks = []

    if report_file.exists():
        try:
            with open(report_file, encoding="utf-8") as f:
                all_reports = json.load(f)
        except Exception:
            all_reports = []

    # Обработка файлов с прогресс-баром tqdm
    with tqdm(
        total=len(target_files), desc="Обработка документов", unit="файл"
    ) as pbar:
        for file_p in target_files:
            try:
                assigned_doc_id = doc_id if len(target_files) == 1 else None

                # Автоматический роутинг FAQ таблиц
                if is_faq_table_file(file_p):
                    res = parse_faq_table_document(file_p, regime=regime)
                else:
                    page_count = parser.get_document_page_count(file_p)
                    doc_profiler = None
                    if pipeline_profiler:
                        doc_profiler = pipeline_profiler.start_document(
                            doc_id=assigned_doc_id or file_p.stem,
                            page_count=page_count,
                        )

                    res = parser.parse_document(
                        file_path=file_p,
                        doc_id=assigned_doc_id,
                        regime=regime,
                        profiler=doc_profiler,
                    )

                    if res.profiling and pipeline_profiler:
                        pipeline_profiler.record_document(res.profiling)

                # Добавляем результаты
                all_documents.append(res.document.model_dump(mode="json"))
                for n in res.nodes:
                    all_nodes.append(n.model_dump(mode="json"))
                for c in res.chunks:
                    all_chunks.append(c.model_dump(mode="json"))
                if res.completeness_report:
                    all_reports.append(
                        res.completeness_report.model_dump(mode="json")
                    )

                # Инкрементальное атомарное сохранение на диск
                atomic_write_json(doc_file, all_documents)
                atomic_write_json(node_file, all_nodes)
                atomic_write_json(chunk_file, all_chunks)
                atomic_write_json(report_file, all_reports)

                if pipeline_profiler:
                    pipeline_profiler.save_atomic_report(profiling_file)

                pbar.set_postfix(
                    {"doc": file_p.name[:20], "chunks": len(res.chunks)}
                )

            except Exception as exc:
                logger.exception("Ошибка при разборе файла %s", file_p.name)
                failed_files.append(
                    {
                        "filename": file_p.name,
                        "path": str(file_p),
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
            finally:
                pbar.update(1)

    duration_sec = time.perf_counter() - start_time

    # 1. Генерация структурированного дерева файлов Markdown для жюри
    markdown_dir = out_dir / "markdown"
    generated_md_files = generate_markdown_tree(
        documents=all_documents,
        nodes=all_nodes,
        chunks=all_chunks,
        completeness_reports=all_reports,
        markdown_dir=markdown_dir,
    )
    logger.info(
        "Сгенерировано дерево Markdown: %d файлов -> %s",
        len(generated_md_files),
        markdown_dir,
    )

    # 2. Формирование сводной статистики объемов
    summary_stats = build_summary_statistics(
        documents=all_documents,
        nodes=all_nodes,
        chunks=all_chunks,
        completeness_reports=all_reports,
        failed_files=failed_files,
        duration_sec=duration_sec,
    )
    atomic_write_json(summary_file, summary_stats)

    # 3. Упаковка в единый ZIP-архив
    archive_path = None
    if create_archive:
        archive_path = create_export_archive(
            out_dir, archive_name="kb_export.zip"
        )
        logger.info("Создан единый архив базы знаний: %s", archive_path)

    # 4. Вывод консольных отчетов
    completeness_table_str = format_completeness_table(all_reports)
    if completeness_table_str:
        print(completeness_table_str)

    summary_table_str = format_summary_table(summary_stats)
    print(summary_table_str)

    # Итоговый вывод логов
    logger.info(
        "Пакетная обработка базы знаний завершена за %.2f сек", duration_sec
    )
    logger.info("Сохранено документов: %d -> %s", len(all_documents), doc_file)
    logger.info("Сохранено узлов AST:   %d -> %s", len(all_nodes), node_file)
    logger.info("Сохранено чанков:     %d -> %s", len(all_chunks), chunk_file)
    if archive_path:
        logger.info("Архив для жюри:       %s", archive_path)

    if failed_files:
        logger.warning(
            "Внимание: %d файлов завершились с ошибками (см. %s)",
            len(failed_files),
            summary_file,
        )
        return 2

    return 0


# ────────────────────────────────────────────────────────────────
# Точка входа CLI
# ────────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа консольного интерфейса базы знаний."""
    parser = argparse.ArgumentParser(
        prog="python -m src.kb.cli",
        description="Консольные команды конвейера обработки базы знаний (Ingestion и экспорт).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Пакетный разбор документов, валидация PyMuPDF и экспорт артефактов",
    )
    ingest_parser.add_argument(
        "--dir",
        "-d",
        dest="dir_path",
        type=Path,
        default=None,
        help="Директория с документами (PDF, DOCX, XLSX, CSV, TXT, MD)",
    )
    ingest_parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        type=Path,
        default=None,
        help="Алиас для --dir или путь к одиночному файлу",
    )
    ingest_parser.add_argument(
        "--out-dir",
        "-o",
        type=Path,
        default=Path("storage/kb_export"),
        help="Директория для сохранения артефактов (по умолчанию storage/kb_export)",
    )
    ingest_parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Явный идентификатор документа (для одиночного файла)",
    )
    ingest_parser.add_argument(
        "--regime",
        type=str,
        default="MOS_PORTAL",
        help="Правовой/функциональный режим (по умолчанию MOS_PORTAL)",
    )
    ingest_parser.add_argument(
        "--mode",
        choices=["accurate", "fast"],
        default="accurate",
        help="Режим обработки: accurate (с распознаванием таблиц) или fast",
    )
    ingest_parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Отключить профилирование производительности",
    )
    ingest_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Отключить создание итогового ZIP-архива",
    )

    args = parser.parse_args(argv)

    if args.command == "ingest":
        target_path = args.dir_path or args.input_path
        if not target_path:
            logger.error(
                "Необходимо указать параметр --dir <путь> или --input <путь>"
            )
            return 1

        return run_ingest(
            input_path=target_path,
            out_dir=args.out_dir,
            doc_id=args.doc_id,
            regime=args.regime,
            mode=args.mode,
            enable_profiling=not args.no_profile,
            create_archive=not args.no_archive,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
