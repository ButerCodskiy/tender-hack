"""Тесты консольного интерфейса пакетного разбора и экспорта артефактов БЗ (MED-06)."""

import json
import zipfile
from pathlib import Path

from src.kb.cli import (
    build_summary_statistics,
    create_export_archive,
    format_completeness_table,
    format_summary_table,
    generate_markdown_tree,
    is_faq_table_file,
    main,
    parse_faq_table_document,
    run_ingest,
    transliterate_to_slug,
)


def test_transliterate_to_slug() -> None:
    """Проверяет корректную транслитерацию кириллицы в безопасные слаги."""
    assert (
        transliterate_to_slug("Положение о закупках 44-ФЗ")
        == "polozhenie_o_zakupkakh_44_fz"
    )
    assert (
        transliterate_to_slug("Регламент L2: технические сбои!")
        == "reglament_l2_tekhnicheskie_sboi"
    )
    assert transliterate_to_slug("Document 123 (v.2)") == "document_123_v_2"
    assert transliterate_to_slug("   ") == "document"
    assert len(transliterate_to_slug("А" * 100, max_length=20)) <= 20


def test_is_faq_table_file(tmp_path: Path) -> None:
    """Проверяет детекцию файлов FAQ (XLSX, CSV с ключевыми словами)."""
    xlsx_file = tmp_path / "faq.xlsx"
    xlsx_file.write_bytes(b"PK\x03\x04fake_xlsx")
    assert is_faq_table_file(xlsx_file) is True

    pdf_file = tmp_path / "regulations.pdf"
    pdf_file.write_bytes(b"%PDF-1.5")
    assert is_faq_table_file(pdf_file) is False

    faq_csv = tmp_path / "questions.csv"
    faq_csv.write_text(
        "Тема;Вопрос;Ответ\n1;Как войти?;По паролю", encoding="utf-8"
    )
    assert is_faq_table_file(faq_csv) is True

    other_csv = tmp_path / "data.csv"
    other_csv.write_text("id,val1,val2\n1,a,b", encoding="utf-8")
    assert is_faq_table_file(other_csv) is False


def test_parse_faq_table_document(tmp_path: Path) -> None:
    """Проверяет разбор таблицы FAQ в синтетический документ, узел и чанки."""
    csv_file = tmp_path / "faq_test.csv"
    csv_file.write_text(
        "Вопрос;Ответ\n"
        "Как сбросить пароль?;Нажмите Забыли пароль на форме входа.\n"
        "Ошибка плагина;Переустановите плагин КриптоПро.\n",
        encoding="utf-8",
    )

    result = parse_faq_table_document(csv_file, regime="MOS_PORTAL")

    assert result.document.doc_id.startswith("DOC_FAQ_")
    assert "faq_test" in result.document.title
    assert len(result.nodes) == 1
    assert result.nodes[0].title == "Типовые вопросы и ответы"
    assert len(result.chunks) == 2
    assert "Как сбросить пароль?" in result.chunks[0].text
    assert "Нажмите Забыли пароль" in result.chunks[0].text
    assert result.chunks[0].has_table is False
    assert result.completeness_report is not None
    assert result.completeness_report.discrepancy_ratio == 0.0


def test_generate_markdown_tree(tmp_path: Path) -> None:
    """Проверяет генерацию дерева файлов Markdown и корневого README.md."""
    documents = [
        {
            "doc_id": "doc_44fz",
            "title": "Положение о закупках 44-ФЗ",
            "regime": "MOS_PORTAL",
            "edition_date": "2026-09-01",
        }
    ]
    nodes = [
        {
            "node_id": "node_sec_1",
            "doc_id": "doc_44fz",
            "level": "section",
            "section_path": "Раздел 1. Общие положения",
            "title": "Раздел 1. Общие положения",
            "full_content": "Текст общих положений регламента.",
            "table_md": None,
        },
        {
            "node_id": "node_tbl_1",
            "doc_id": "doc_44fz",
            "level": "item",
            "section_path": "Раздел 1 > Таблица сроков",
            "title": "Таблица сроков",
            "full_content": "| Этап | Срок |\n|---|---|\n| Подача | 5 дней |",
            "table_md": "| Этап | Срок |\n|---|---|\n| Подача | 5 дней |",
        },
    ]
    chunks = [
        {
            "chunk_id": "chunk_101",
            "node_id": "node_sec_1",
            "text": "Текст общих положений",
            "has_table": False,
            "token_count": 45,
        },
        {
            "chunk_id": "chunk_102",
            "node_id": "node_tbl_1",
            "text": "| Этап | Срок |",
            "has_table": True,
            "token_count": 30,
        },
    ]
    reports = [
        {
            "doc_id": "doc_44fz",
            "pymupdf_char_count": 1000,
            "docling_char_count": 1010,
            "discrepancy_ratio": 0.01,
            "is_scanned": False,
            "needs_manual_review": False,
        }
    ]

    markdown_dir = tmp_path / "markdown"
    generated_files = generate_markdown_tree(
        documents=documents,
        nodes=nodes,
        chunks=chunks,
        completeness_reports=reports,
        markdown_dir=markdown_dir,
    )

    readme_file = markdown_dir / "README.md"
    doc_file = markdown_dir / "polozhenie_o_zakupkakh_44_fz.md"

    assert readme_file.exists()
    assert doc_file.exists()
    assert len(generated_files) == 2

    # Проверка содержания README.md
    readme_content = readme_file.read_text(encoding="utf-8")
    assert "Каталог регламентов и базы знаний" in readme_content
    assert "Положение о закупках 44-ФЗ" in readme_content
    assert "polozhenie_o_zakupkakh_44_fz.md" in readme_content
    assert "99.0%" in readme_content

    # Проверка содержания {doc_slug}.md
    doc_content = doc_file.read_text(encoding="utf-8")
    assert "# Положение о закупках 44-ФЗ" in doc_content
    assert "## Содержание документа" in doc_content
    assert "## Раздел 1. Общие положения" in doc_content
    assert "Текст общих положений регламента." in doc_content
    assert "| Этап | Срок |" in doc_content
    assert "🔖 **Поисковые фрагменты (Qdrant):**" in doc_content
    assert "`chunk_101` (45 токенов)" in doc_content
    assert "`chunk_102` (30 токенов 📊 таблица)" in doc_content


def test_build_summary_statistics() -> None:
    """Проверяет расчет сводной статистики объемов базы знаний."""
    documents = [{"doc_id": "d1"}, {"doc_id": "d2"}]
    nodes = [
        {"level": "section"},
        {"level": "article"},
        {"level": "article"},
        {"level": "item", "table_md": "|a|b|"},
    ]
    chunks = [
        {"token_count": 100, "has_table": False},
        {"token_count": 200, "has_table": True},
        {"token_count": 300, "has_table": False},
    ]
    reports = [
        {
            "doc_id": "d1",
            "discrepancy_ratio": 0.02,
            "is_scanned": False,
            "needs_manual_review": False,
        },
        {
            "doc_id": "d2",
            "discrepancy_ratio": 0.08,
            "is_scanned": True,
            "needs_manual_review": True,
        },
    ]
    failed = [{"filename": "corrupted.pdf", "error": "Bad PDF"}]

    stats = build_summary_statistics(
        documents=documents,
        nodes=nodes,
        chunks=chunks,
        completeness_reports=reports,
        failed_files=failed,
        duration_sec=12.5,
    )

    assert stats["documents"]["total_submitted"] == 3
    assert stats["documents"]["successfully_parsed"] == 2
    assert stats["documents"]["failed_count"] == 1
    assert stats["nodes"]["total_count"] == 4
    assert stats["nodes"]["by_level"]["section"] == 1
    assert stats["nodes"]["by_level"]["article"] == 2
    assert stats["nodes"]["by_level"]["item"] == 1
    assert stats["chunks"]["total_count"] == 3
    assert stats["chunks"]["total_tokens"] == 600
    assert stats["chunks"]["avg_tokens_per_chunk"] == 200.0
    assert stats["chunks"]["max_tokens_chunk"] == 300
    assert stats["chunks"]["chunks_with_tables"] == 1
    assert stats["tables"]["total_tables_extracted"] == 1
    assert stats["completeness_validation"]["scanned_documents_count"] == 1
    assert (
        stats["completeness_validation"]["manual_review_required_count"] == 1
    )
    assert len(stats["failed_files"]) == 1


def test_create_export_archive(tmp_path: Path) -> None:
    """Проверяет сборку и целостность единого ZIP-архива."""
    export_dir = tmp_path / "export"
    export_dir.mkdir()

    (export_dir / "parsed_documents.json").write_text("[]", encoding="utf-8")
    (export_dir / "parsed_nodes.json").write_text("[]", encoding="utf-8")
    (export_dir / "parsed_chunks.json").write_text("[]", encoding="utf-8")
    (export_dir / "summary_statistics.json").write_text("{}", encoding="utf-8")

    md_dir = export_dir / "markdown"
    md_dir.mkdir()
    (md_dir / "README.md").write_text("# Index", encoding="utf-8")
    (md_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")

    archive_path = create_export_archive(export_dir, "kb_export.zip")
    assert archive_path.exists()

    with zipfile.ZipFile(archive_path, "r") as zf:
        namelist = zf.namelist()
        assert "parsed_documents.json" in namelist
        assert "parsed_nodes.json" in namelist
        assert "parsed_chunks.json" in namelist
        assert "summary_statistics.json" in namelist
        assert "markdown/README.md" in namelist
        assert "markdown/doc1.md" in namelist


def test_format_tables() -> None:
    """Проверяет форматирование текстовых таблиц для консоли."""
    reports = [
        {
            "doc_id": "doc_test",
            "docling_char_count": 1000,
            "pymupdf_char_count": 1005,
            "discrepancy_ratio": 0.005,
            "is_scanned": False,
            "needs_manual_review": False,
        }
    ]
    comp_str = format_completeness_table(reports)
    assert "ОТЧЕТ КОНТРОЛЯ ПОЛНОТЫ ИЗВЛЕЧЕНИЯ СИМВОЛОВ" in comp_str
    assert "doc_test" in comp_str
    assert "0.50%" in comp_str

    stats = {
        "documents": {
            "total_submitted": 1,
            "successfully_parsed": 1,
            "failed_count": 0,
        },
        "nodes": {
            "total_count": 5,
            "by_level": {"section": 1, "article": 2, "item": 2},
        },
        "chunks": {
            "total_count": 10,
            "chunks_with_tables": 2,
            "total_tokens": 2500,
            "avg_tokens_per_chunk": 250.0,
        },
        "tables": {"total_tables_extracted": 2},
        "completeness_validation": {
            "avg_completeness_percent": 99.5,
            "scanned_documents_count": 0,
            "manual_review_required_count": 0,
        },
        "duration_seconds": 3.14,
    }
    sum_str = format_summary_table(stats)
    assert "СВОДНАЯ СТАТИСТИКА БАЗЫ ЗНАНИЙ (KB EXPORT)" in sum_str
    assert "Поисковых чанков:            10" in sum_str
    assert "3.14 сек" in sum_str


def test_run_ingest_e2e_with_faq_and_docs(tmp_path: Path) -> None:
    """E2E-тест пакетного запуска run_ingest со смешанным контентом (MD регламент + CSV FAQ)."""
    input_dir = tmp_path / "input_docs"
    input_dir.mkdir()
    out_dir = tmp_path / "kb_export"

    # 1. Текстовый регламент
    reg_file = input_dir / "reglament_l1.md"
    reg_file.write_text(
        "# Регламент первой линии поддержки\n\n"
        "## Статья 1. Предмет регламента\n"
        "Первая линия осуществляет первичную классификацию обращений.\n\n"
        "## Статья 2. Сроки реакции\n"
        "Время первого ответа не должно превышать 120 секунд.\n",
        encoding="utf-8",
    )

    # 2. Таблица FAQ
    faq_file = input_dir / "faq_answers.csv"
    faq_file.write_text(
        "Тема;Вопрос;Ответ\n"
        "Портал;Как получить доступ?;Подайте заявку через личный кабинет.\n",
        encoding="utf-8",
    )

    exit_code = run_ingest(
        input_path=input_dir,
        out_dir=out_dir,
        mode="fast",
        enable_profiling=False,
        create_archive=True,
    )

    assert exit_code == 0

    # Проверяем созданные артефакты
    assert (out_dir / "parsed_documents.json").exists()
    assert (out_dir / "parsed_nodes.json").exists()
    assert (out_dir / "parsed_chunks.json").exists()
    assert (out_dir / "completeness_reports.json").exists()
    assert (out_dir / "summary_statistics.json").exists()
    assert (out_dir / "markdown" / "README.md").exists()
    assert (out_dir / "kb_export.zip").exists()

    # Проверяем содержимое JSON
    docs = json.loads(
        (out_dir / "parsed_documents.json").read_text(encoding="utf-8")
    )
    assert len(docs) == 2  # регламент + FAQ

    chunks = json.loads(
        (out_dir / "parsed_chunks.json").read_text(encoding="utf-8")
    )
    assert len(chunks) >= 2

    stats = json.loads(
        (out_dir / "summary_statistics.json").read_text(encoding="utf-8")
    )
    assert stats["documents"]["successfully_parsed"] == 2
    assert stats["documents"]["failed_count"] == 0


def test_main_cli_arguments(tmp_path: Path) -> None:
    """Проверяет аргументы командной строки CLI (--dir, --input, ошибки валидации)."""
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    out_dir = tmp_path / "out"

    (input_dir / "test.txt").write_text(
        "Простой тестовый документ.", encoding="utf-8"
    )

    # 1. Запуск с флагом --dir
    code = main(
        [
            "ingest",
            "--dir",
            str(input_dir),
            "--out-dir",
            str(out_dir),
            "--mode",
            "fast",
            "--no-archive",
        ]
    )
    assert code == 0
    assert (out_dir / "parsed_documents.json").exists()

    # 2. Ошибка: не указан ни --dir, ни --input
    code_err = main(["ingest", "--out-dir", str(out_dir)])
    assert code_err == 1

    # 3. Ошибка: несуществующая директория
    code_not_found = main(
        ["ingest", "--dir", str(tmp_path / "non_existent_folder")]
    )
    assert code_not_found == 1
