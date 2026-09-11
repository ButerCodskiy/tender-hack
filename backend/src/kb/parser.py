"""
Модуль парсинга нормативных документов (Docling + PyMuPDF).

Реализует:
1. Извлечение печатного слоя текста через PyMuPDF (fitz) и подсчет символов.
2. Поддержку режимов обработки:
   - accurate (по умолчанию): полный TableFormer, OCR при необходимости.
   - fast: отключение OCR при плотном текстовом слое (> 100 симв/стр), быстрый разбор таблиц.
3. Автоматическую классификацию графических сканов: при pymupdf_char_count == 0
   документ помечается как is_scanned = True, а проверка дельты 5% отключается.
4. Контроль полноты: при расхождении объема символов PyMuPDF и Docling > 5%
   выставляется флаг needs_manual_review = True с логированием warning.
5. Интеграцию с DocumentProfiler для посекундного профилирования каждой стадии.
6. Защиту от утечек памяти: gc.collect() и torch.cuda.empty_cache() после каждого документа.
"""

import gc
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import fitz  # PyMuPDF

from src.core.config import settings
from src.kb.chunker import HierarchicalChunker, TokenCounter
from src.kb.profiler import DocumentProfiler
from src.kb.schemas import (
    CompletenessReportSchema,
    NodeLevel,
    ParsedChunkSchema,
    ParsedDocumentSchema,
    ParsedExtractionResultSchema,
    ParsedNodeSchema,
)
from src.kb.tables import TableProcessor

logger = logging.getLogger(__name__)

# Безопасный импорт torch для очистки CUDA кэша
try:
    import torch  # type: ignore
except ImportError:
    torch = None


class DocumentParser:
    """Оркестратор разбора нормативных документов (Docling + PyMuPDF)."""

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        chunker: HierarchicalChunker | None = None,
        completeness_threshold: float = 0.05,
        mode: Literal["accurate", "fast"] = "fast",
    ) -> None:
        self.token_counter = token_counter or TokenCounter()
        self.chunker = chunker or HierarchicalChunker(
            token_counter=self.token_counter
        )
        self.completeness_threshold = completeness_threshold
        self.mode = mode
        self.table_processor = TableProcessor()

    @staticmethod
    def get_document_page_count(file_path: Path) -> int:
        """Определение количества страниц в документе."""
        if file_path.suffix.lower() in (".txt", ".md", ".docx", ".doc"):
            return 1
        try:
            with fitz.open(file_path) as doc:
                return max(len(doc), 1)
        except Exception:
            return 1

    @staticmethod
    def extract_pymupdf_text(file_path: Path) -> tuple[str, int]:
        """
        Извлечение текстового слоя через PyMuPDF (fitz), чтение docx (zip/xml) или прямое чтение txt.
        Возвращает кортеж (полный текст, число печатных символов).
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        # Прямое чтение текстовых файлов
        if file_path.suffix.lower() in (".txt", ".md"):
            try:
                full_text = file_path.read_text(encoding="utf-8")
                char_count = len(re.findall(r"\S", full_text))
                return full_text, char_count
            except Exception as exc:
                logger.warning(
                    "Ошибка чтения файла %s: %s", file_path.name, exc
                )
                return "", 0

        # Чтение документов DOCX через извлечение xml из zip
        if file_path.suffix.lower() == ".docx":
            try:
                import xml.etree.ElementTree as ET
                import zipfile

                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    texts = [
                        node.text
                        for node in tree.iter()
                        if node.tag.endswith("t") and node.text
                    ]
                    full_text = " ".join(texts)
                    char_count = len(re.findall(r"\S", full_text))
                    return full_text, char_count
            except Exception as exc:
                logger.warning(
                    "Ошибка чтения DOCX файла %s: %s", file_path.name, exc
                )
                return "", 0

        full_text_parts: list[str] = []
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    text = page.get_text()
                    if text:
                        full_text_parts.append(text)
        except Exception as exc:
            logger.warning(
                "Ошибка чтения PyMuPDF для %s: %s", file_path.name, exc
            )
            return "", 0

        full_text = "\n".join(full_text_parts)
        char_count = len(re.findall(r"\S", full_text))
        return full_text, char_count

    def validate_completeness(
        self,
        doc_id: str,
        pymupdf_char_count: int,
        docling_char_count: int,
    ) -> CompletenessReportSchema:
        """
        Сверка объемов символов PyMuPDF vs Docling.
        Обработка сканов: при pymupdf_char_count == 0 документ помечается как скан,
        проверка 5% отключается (нет ложного срабатывания).
        """
        if pymupdf_char_count == 0:
            logger.info(
                "Документ %s: текстовый слой PyMuPDF отсутствует. "
                "Классифицирован как скан (is_scanned=True).",
                doc_id,
            )
            return CompletenessReportSchema(
                doc_id=doc_id,
                pymupdf_char_count=0,
                docling_char_count=docling_char_count,
                discrepancy_ratio=0.0,
                is_scanned=True,
                needs_manual_review=False,
                details="Графический скан: текстовый слой отсутствует, задействован OCR.",
            )

        discrepancy = abs(docling_char_count - pymupdf_char_count) / max(
            pymupdf_char_count, 1
        )
        needs_review = discrepancy > self.completeness_threshold

        if needs_review:
            logger.warning(
                "Контроль полноты НЕ пройден для %s: дельта %.2f%% > %.2f%% "
                "(PyMuPDF: %d симв., Docling: %d симв.)",
                doc_id,
                discrepancy * 100,
                self.completeness_threshold * 100,
                pymupdf_char_count,
                docling_char_count,
            )
            details = (
                f"Превышен порог расхождения символов ({discrepancy:.1%} > "
                f"{self.completeness_threshold:.1%}). Требуется ручная проверка."
            )
        else:
            details = (
                f"Контроль полноты пройден "
                f"(дельта {discrepancy:.1%} <= {self.completeness_threshold:.1%})."
            )

        return CompletenessReportSchema(
            doc_id=doc_id,
            pymupdf_char_count=pymupdf_char_count,
            docling_char_count=docling_char_count,
            discrepancy_ratio=round(discrepancy, 4),
            is_scanned=False,
            needs_manual_review=needs_review,
            details=details,
        )

    def _extract_article_and_part(
        self, title: str, content: str
    ) -> tuple[str | None, str | None]:
        """Извлечение номера статьи и части с помощью регулярных выражений."""
        article_no = None
        part_no = None

        combined = f"{title}\n{content[:200]}"
        art_match = re.search(
            r"(Статья|Article)\s+(\d+([\.\-]\d+)?)", combined, re.IGNORECASE
        )
        if art_match:
            article_no = art_match.group(2)

        part_match = re.search(
            r"(Часть|Пункт|Раздел|Section)\s+(\d+([\.\-]\d+)?)",
            combined,
            re.IGNORECASE,
        )
        if part_match:
            part_no = part_match.group(2)

        return article_no, part_no

    def _parse_with_docling(
        self,
        file_path: Path,
        chars_per_page: float,
        profiler: DocumentProfiler | None = None,
    ) -> tuple[list[dict[str, Any]], str, int]:
        """
        Попытка разбора через Docling с учетом режима fast/accurate.
        """
        # Текстовые файлы без разметки (txt, md) обрабатываются напрямую структурным AST-парсером
        if file_path.suffix.lower() in (".txt", ".md"):
            return self._parse_with_pymupdf_ast(file_path, profiler=profiler)

        try:
            import os

            _ssl_cert = os.environ.get("SSL_CERT_FILE")
            if _ssl_cert and not Path(_ssl_cert).is_file():
                os.environ.pop("SSL_CERT_FILE", None)

            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

            from docling.backend.pypdfium2_backend import (
                PyPdfiumDocumentBackend,
            )
            from docling.datamodel.base_models import (
                InputFormat,  # type: ignore
            )
            from docling.datamodel.pipeline_options import (  # type: ignore
                PdfPipelineOptions,
                TableFormerMode,
            )
            from docling.document_converter import (  # type: ignore
                DocumentConverter,
                PdfFormatOption,
                WordFormatOption,
            )

            pipeline_options = PdfPipelineOptions()

            # В режиме fast при наличии достаточного текста отключаем OCR и тяжелую модель TableFormer
            if self.mode == "fast" and chars_per_page > 100:
                pipeline_options.do_ocr = False
                pipeline_options.do_table_structure = False
                logger.info(
                    "Docling: режим fast (%.1f симв/стр). OCR отключен, do_table_structure=False.",
                    chars_per_page,
                )
            else:
                pipeline_options.do_ocr = True
                pipeline_options.table_structure_options.mode = (
                    TableFormerMode.ACCURATE
                )

            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        backend=PyPdfiumDocumentBackend,
                        pipeline_options=pipeline_options,
                    ),
                    InputFormat.DOCX: WordFormatOption(),
                }
            )

            # Замер конверсии документа
            if profiler:
                with profiler.stage("docling_conversion"):
                    conv_res = converter.convert(file_path)
            else:
                conv_res = converter.convert(file_path)

            docling_doc = conv_res.document
            raw_elements: list[dict[str, Any]] = []
            docling_text_parts: list[str] = []

            heading_pattern = re.compile(
                r"^(Раздел\s+\d+|Статья\s+\d+|Глава\s+\d+|Section\s+\d+|Article\s+\d+|Chapter\s+\d+|\d+(\.\d+)*\.?\s+[А-ЯЁA-Z])",
                re.IGNORECASE,
            )

            for item, _level in docling_doc.iterate_items():
                item_type = getattr(item, "label", type(item).__name__)
                text_val = getattr(item, "text", "")
                docling_text_parts.append(text_val)

                if "Table" in item_type or hasattr(
                    item, "export_to_dataframe"
                ):
                    if profiler:
                        with profiler.stage("docling_table_extraction"):
                            table_md, facts = (
                                self.table_processor.process_docling_table(
                                    item, doc=docling_doc
                                )
                            )
                    else:
                        table_md, facts = (
                            self.table_processor.process_docling_table(
                                item, doc=docling_doc
                            )
                        )

                    raw_elements.append(
                        {
                            "type": "table",
                            "text": text_val,
                            "table_md": table_md,
                            "linearized_facts": facts,
                        }
                    )
                elif (
                    "Heading" in item_type
                    or "Section" in item_type
                    or (
                        len(text_val.strip()) < 160
                        and heading_pattern.match(text_val.strip())
                    )
                ):
                    level_val = getattr(item, "level", 1)
                    if not isinstance(level_val, int) or level_val < 1:
                        lower_t = text_val.lower().strip()
                        if lower_t.startswith(
                            ("раздел", "глава", "section", "chapter")
                        ):
                            level_val = 1
                        elif lower_t.startswith(("статья", "article")):
                            level_val = 2
                        elif re.match(r"^\d+\.\d+\.\d+", text_val.strip()):
                            level_val = 4
                        elif re.match(r"^\d+(\.\d+)+", text_val.strip()):
                            level_val = 3
                        else:
                            level_val = 2
                    raw_elements.append(
                        {
                            "type": "heading",
                            "text": text_val,
                            "level": level_val,
                        }
                    )
                else:
                    raw_elements.append(
                        {
                            "type": "text",
                            "text": text_val,
                        }
                    )

            full_text = "\n".join(docling_text_parts)
            char_count = len(re.findall(r"\S", full_text))
            return raw_elements, full_text, char_count

        except ImportError:
            logger.info(
                "Docling не установлен. Применяется встроенный структурный AST-парсер."
            )
            return self._parse_with_pymupdf_ast(file_path, profiler=profiler)
        except Exception as exc:
            logger.warning(
                "Docling недоступен для %s (%s). Применяется структурный парсер.",
                file_path.name,
                exc,
            )
            return self._parse_with_pymupdf_ast(file_path, profiler=profiler)

    def _parse_with_pymupdf_ast(
        self,
        file_path: Path,
        profiler: DocumentProfiler | None = None,
    ) -> tuple[list[dict[str, Any]], str, int]:
        """
        Встроенный структурный парсер на базе PyMuPDF / текстовых паттернов.
        """
        if profiler:
            with profiler.stage("docling_conversion"):
                full_text, char_count = self.extract_pymupdf_text(file_path)
        else:
            full_text, char_count = self.extract_pymupdf_text(file_path)

        raw_elements: list[dict[str, Any]] = []
        lines = full_text.split("\n")
        current_block: list[str] = []

        heading_pattern = re.compile(
            r"^(Раздел\s+\d+|Статья\s+\d+|Глава\s+\d+|Section\s+\d+|Article\s+\d+|Chapter\s+\d+|\d+(\.\d+)*\.?\s+[А-ЯЁA-Z])",
            re.IGNORECASE,
        )

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if current_block:
                    raw_elements.append(
                        {"type": "text", "text": "\n".join(current_block)}
                    )
                    current_block = []
                continue

            if heading_pattern.match(line_str) and len(line_str) < 160:
                if current_block:
                    raw_elements.append(
                        {"type": "text", "text": "\n".join(current_block)}
                    )
                    current_block = []

                lower_line = line_str.lower()
                if lower_line.startswith(
                    ("раздел", "глава", "section", "chapter")
                ):
                    level_val = 1
                elif lower_line.startswith(("статья", "article")):
                    level_val = 2
                elif re.match(r"^\d+\.\d+\.\d+", line_str):
                    level_val = 4
                elif re.match(r"^\d+(\.\d+)+", line_str):
                    level_val = 3
                else:
                    level_val = 2

                raw_elements.append(
                    {"type": "heading", "text": line_str, "level": level_val}
                )
            else:
                current_block.append(line_str)

        if current_block:
            raw_elements.append(
                {"type": "text", "text": "\n".join(current_block)}
            )

        return raw_elements, full_text, char_count

    @staticmethod
    def generate_node_id(
        doc_id: str,
        section_path: str,
        title: str,
        seen_ids: dict[str, int] | None = None,
    ) -> str:
        """
        Генерация стабильного детерминированного ID:
        node_id = 'NODE_' || md5(doc_id || '_' || section_path || '_' || title)
        С детерминированным суффиксом при повторах в документе.
        """
        raw_key = f"{doc_id}_{section_path}_{title}".encode()
        base_id = f"NODE_{hashlib.md5(raw_key).hexdigest()}"
        if seen_ids is not None:
            if base_id in seen_ids:
                seen_ids[base_id] += 1
                return f"{base_id}_{seen_ids[base_id]}"
            seen_ids[base_id] = 1
        return base_id

    def parse_document(
        self,
        file_path: Path | str,
        doc_id: str | None = None,
        title: str | None = None,
        regime: str = "MOS_PORTAL",
        source_url: str | None = None,
        profiler: DocumentProfiler | None = None,
    ) -> ParsedExtractionResultSchema:
        """
        Главная точка входа для парсинга документа с профилированием и защитой памяти.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {path}")

        try:
            # Определение числа страниц для метрик производительности
            page_count = self.get_document_page_count(path)

            if not doc_id:
                file_bytes = path.read_bytes()
                hash_suffix = hashlib.sha256(file_bytes[:4096]).hexdigest()[
                    :12
                ]
                doc_id = f"doc_{path.stem}_{hash_suffix}"

            doc_title = title or path.stem.replace("_", " ").title()

            # 1. Извлечение текста через PyMuPDF для контроля полноты
            if profiler:
                with profiler.stage("extract_pymupdf_text"):
                    pymupdf_text, pymupdf_chars = self.extract_pymupdf_text(
                        path
                    )
            else:
                pymupdf_text, pymupdf_chars = self.extract_pymupdf_text(path)

            chars_per_page = pymupdf_chars / max(page_count, 1)

            # 2. Извлечение элементов через Docling (или AST-фолбэк)
            raw_elements, docling_text, docling_chars = (
                self._parse_with_docling(
                    path,
                    chars_per_page=chars_per_page,
                    profiler=profiler,
                )
            )

            # 3. Контроль полноты и детекция сканов
            report = self.validate_completeness(
                doc_id=doc_id,
                pymupdf_char_count=pymupdf_chars,
                docling_char_count=docling_chars,
            )

            # Создаем документ (page_count исключен из DDL kb_documents)
            document = ParsedDocumentSchema(
                doc_id=doc_id,
                title=doc_title,
                regime=regime,
                edition_date=datetime.now(settings.TIMEZONE).date(),
                status="uploaded",
                error_message=report.details
                if report.needs_manual_review
                else None,
                source_url=source_url,
                is_scanned=report.is_scanned,
                page_count=page_count,
            )

            # 4. Построение иерархических узлов (kb_nodes) и чанков
            nodes: list[ParsedNodeSchema] = []
            all_chunks: list[ParsedChunkSchema] = []
            seen_node_ids: dict[str, int] = {}
            heading_stack: list[dict[str, Any]] = []

            for elem in raw_elements:
                elem_type = elem.get("type", "text")
                elem_text = elem.get("text", "").strip()

                if not elem_text and elem_type != "table":
                    continue

                if elem_type == "heading":
                    h_level = elem.get("level", 1) or 1
                    while (
                        heading_stack and heading_stack[-1]["level"] >= h_level
                    ):
                        heading_stack.pop()

                    parent_node_id = (
                        heading_stack[-1]["node_id"] if heading_stack else None
                    )

                    if heading_stack:
                        current_section_path = " > ".join(
                            [h["title"] for h in heading_stack] + [elem_text]
                        )
                    else:
                        current_section_path = elem_text

                    node_id = self.generate_node_id(
                        doc_id=doc_id,
                        section_path=current_section_path,
                        title=elem_text,
                        seen_ids=seen_node_ids,
                    )

                    heading_stack.append(
                        {
                            "level": h_level,
                            "node_id": node_id,
                            "title": elem_text,
                        }
                    )

                    level: NodeLevel = "section"
                    if "Статья" in elem_text or "Article" in elem_text:
                        level = "article"
                    elif re.match(r"^\d+\.\d+", elem_text):
                        level = "item"
                    elif h_level == 1:
                        level = "section"
                    elif h_level == 2:
                        level = "article"
                    else:
                        level = "item"

                    art_no, part_no = self._extract_article_and_part(
                        elem_text, ""
                    )
                    tok_cnt = self.token_counter.count_tokens(elem_text)

                    node = ParsedNodeSchema(
                        node_id=node_id,
                        doc_id=doc_id,
                        parent_node_id=parent_node_id,
                        level=level,
                        section_path=current_section_path,
                        article_no=art_no,
                        part_no=part_no,
                        title=elem_text,
                        full_content=elem_text,
                        table_md=None,
                        token_count=tok_cnt,
                    )
                    nodes.append(node)

                    if profiler:
                        with profiler.stage(
                            "hierarchical_chunking_and_tokenization"
                        ):
                            node_chunks = self.chunker.chunk_node(node)
                    else:
                        node_chunks = self.chunker.chunk_node(node)
                    all_chunks.extend(node_chunks)

                elif elem_type == "table":
                    parent_node_id = (
                        heading_stack[-1]["node_id"] if heading_stack else None
                    )
                    parent_path = (
                        " > ".join([h["title"] for h in heading_stack])
                        if heading_stack
                        else doc_title
                    )
                    section_path = f"{parent_path} > Таблица"
                    title = f"Таблица ({parent_path})"

                    node_id = self.generate_node_id(
                        doc_id=doc_id,
                        section_path=section_path,
                        title=title,
                        seen_ids=seen_node_ids,
                    )
                    table_md = elem.get("table_md", "")
                    linearized = elem.get("linearized_facts", [])

                    if profiler:
                        with profiler.stage(
                            "header_propagation_and_linearization"
                        ):
                            # Если facts еще не сформированы
                            if not linearized and table_md:
                                linearized = (
                                    self.table_processor.to_linearized_facts(
                                        [table_md.split("\n")]
                                    )
                                )

                    full_content = table_md or "\n".join(linearized)
                    tok_cnt = self.token_counter.count_tokens(full_content)

                    node = ParsedNodeSchema(
                        node_id=node_id,
                        doc_id=doc_id,
                        parent_node_id=parent_node_id,
                        level="item",
                        section_path=section_path,
                        article_no=None,
                        part_no=None,
                        title=title,
                        full_content=full_content,
                        table_md=table_md,
                        token_count=tok_cnt,
                    )
                    nodes.append(node)

                    if profiler:
                        with profiler.stage(
                            "hierarchical_chunking_and_tokenization"
                        ):
                            node_chunks = self.chunker.chunk_node(
                                node, linearized_table_facts=linearized
                            )
                    else:
                        node_chunks = self.chunker.chunk_node(
                            node, linearized_table_facts=linearized
                        )
                    all_chunks.extend(node_chunks)

                else:  # Текстовый блок
                    parent_node_id = (
                        heading_stack[-1]["node_id"] if heading_stack else None
                    )
                    section_path = (
                        " > ".join([h["title"] for h in heading_stack])
                        if heading_stack
                        else doc_title
                    )

                    art_no, part_no = self._extract_article_and_part(
                        "", elem_text
                    )
                    tok_cnt = self.token_counter.count_tokens(elem_text)

                    title_snippet = elem_text[:60].replace("\n", " ") + (
                        "..." if len(elem_text) > 60 else ""
                    )
                    node_id = self.generate_node_id(
                        doc_id=doc_id,
                        section_path=section_path,
                        title=title_snippet,
                        seen_ids=seen_node_ids,
                    )

                    node = ParsedNodeSchema(
                        node_id=node_id,
                        doc_id=doc_id,
                        parent_node_id=parent_node_id,
                        level="item",
                        section_path=section_path,
                        article_no=art_no,
                        part_no=part_no,
                        title=title_snippet,
                        full_content=elem_text,
                        table_md=None,
                        token_count=tok_cnt,
                    )
                    nodes.append(node)

                    if profiler:
                        with profiler.stage(
                            "hierarchical_chunking_and_tokenization"
                        ):
                            node_chunks = self.chunker.chunk_node(node)
                    else:
                        node_chunks = self.chunker.chunk_node(node)
                    all_chunks.extend(node_chunks)

            # Если узлов не сформировано — создаем корневой узел
            if not nodes:
                root_section_path = doc_title
                root_node_id = self.generate_node_id(
                    doc_id=doc_id,
                    section_path=root_section_path,
                    title=doc_title,
                    seen_ids=seen_node_ids,
                )
                tok_cnt = self.token_counter.count_tokens(
                    docling_text or pymupdf_text
                )
                root_node = ParsedNodeSchema(
                    node_id=root_node_id,
                    doc_id=doc_id,
                    parent_node_id=None,
                    level="document",
                    section_path=root_section_path,
                    article_no=None,
                    part_no=None,
                    title=doc_title,
                    full_content=docling_text or pymupdf_text,
                    table_md=None,
                    token_count=tok_cnt,
                )
                nodes.append(root_node)
                all_chunks.extend(self.chunker.chunk_node(root_node))

            # Завершаем профилирование документа
            profiling_metrics = None
            if profiler:
                total_chunk_tokens = sum(
                    getattr(
                        c,
                        "token_count",
                        self.token_counter.count_tokens(c.text),
                    )
                    for c in all_chunks
                )
                profiling_metrics = profiler.finish(
                    token_count=total_chunk_tokens
                )

            return ParsedExtractionResultSchema(
                document=document,
                nodes=nodes,
                chunks=all_chunks,
                completeness_report=report,
                profiling=profiling_metrics,
            )

        finally:
            # Защита от OOM: принудительная очистка памяти процесса и VRAM GPU
            gc.collect()
            if torch is not None:
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
