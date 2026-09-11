"""
Сквозной тест для консольного модуля cli.py (test_kb_cli.py).
Создает синтетические документы регламента (PDF и TXT), запускает run_ingest
и валидирует созданные артефакты JSON.
"""

import json
from pathlib import Path

import fitz

from src.kb.cli import run_ingest
from src.kb.schemas import (
    CompletenessReportSchema,
    ParsedChunkSchema,
    ParsedDocumentSchema,
    ParsedNodeSchema,
)


def test_cli_ingest_pipeline_pdf(tmp_path: Path):
    # Тест на PDF с латинскими заголовками для совместимости со стандартными шрифтами Helvetica
    pdf_path = tmp_path / "sample_regulation.pdf"
    doc = fitz.open()
    page = doc.new_page()

    text_content = (
        "Section 1. General Provisions\n"
        "1.1. This Regulation establishes the procurement procedures.\n"
        "1.2. Participation is open to all registered legal entities.\n\n"
        "Article 2. Security Requirements\n"
        "The security deposit amount is determined based on NMTC.\n"
        "For procurements under 600k rubles, deposit is not required.\n"
    )
    page.insert_text((50, 50), text_content, fontsize=11)
    doc.save(str(pdf_path))
    doc.close()

    out_dir = tmp_path / "output_pdf"
    run_ingest(
        input_path=pdf_path,
        out_dir=out_dir,
        doc_id="DOC_SAMPLE_PDF",
        regime="MOS_PORTAL",
    )

    doc_file = out_dir / "parsed_documents.json"
    node_file = out_dir / "parsed_nodes.json"
    chunk_file = out_dir / "parsed_chunks.json"
    rep_file = out_dir / "completeness_reports.json"

    assert doc_file.exists()
    assert node_file.exists()
    assert chunk_file.exists()
    assert rep_file.exists()

    with open(doc_file, encoding="utf-8") as f:
        docs = json.load(f)
        assert len(docs) == 1
        d = ParsedDocumentSchema.model_validate(docs[0])
        assert d.doc_id == "DOC_SAMPLE_PDF"

    with open(node_file, encoding="utf-8") as f:
        nodes = json.load(f)
        assert len(nodes) >= 2
        for n in nodes:
            ParsedNodeSchema.model_validate(n)

    with open(chunk_file, encoding="utf-8") as f:
        chunks = json.load(f)
        assert len(chunks) >= 2
        for c in chunks:
            assert "token_count" not in c
            ParsedChunkSchema.model_validate(c)


def test_cli_ingest_pipeline_txt(tmp_path: Path):
    # Тест на кириллическом тексте регламента в формате TXT
    txt_path = tmp_path / "reglament_44fz.txt"
    text_content = (
        "Раздел 1. Общие положения регламента котировочных сессий\n"
        "1.1. Настоящий Регламент устанавливает правила проведения котировочных сессий "
        "на Портале поставщиков города Москвы.\n\n"
        "Статья 2. Обеспечение заявок участников\n"
        "Размер обеспечения определяется исходя из начальной цены контракта.\n"
        "При НМЦК до 600 тысяч рублей обеспечение не требуется.\n"
    )
    txt_path.write_text(text_content, encoding="utf-8")

    out_dir = tmp_path / "output_txt"
    run_ingest(
        input_path=txt_path,
        out_dir=out_dir,
        doc_id="DOC_44FZ_TXT",
        regime="MOS_PORTAL",
    )

    doc_file = out_dir / "parsed_documents.json"
    node_file = out_dir / "parsed_nodes.json"
    chunk_file = out_dir / "parsed_chunks.json"
    rep_file = out_dir / "completeness_reports.json"

    assert doc_file.exists()
    assert node_file.exists()
    assert chunk_file.exists()
    assert rep_file.exists()

    with open(node_file, encoding="utf-8") as f:
        nodes = json.load(f)
        assert len(nodes) >= 2

    with open(rep_file, encoding="utf-8") as f:
        reps = json.load(f)
        rep = CompletenessReportSchema.model_validate(reps[0])
        assert rep.pymupdf_char_count > 0
        assert not rep.needs_manual_review
