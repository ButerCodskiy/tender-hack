"""
Тесты контроля полноты и детекции сканов (test_kb_parser.py).
"""

from src.kb.parser import DocumentParser


def test_completeness_ok():
    parser = DocumentParser(completeness_threshold=0.05)
    rep = parser.validate_completeness(
        doc_id="DOC_OK",
        pymupdf_char_count=10000,
        docling_char_count=10100,
    )
    assert not rep.is_scanned
    assert not rep.needs_manual_review
    assert rep.discrepancy_ratio == 0.01


def test_completeness_exceeded():
    parser = DocumentParser(completeness_threshold=0.05)
    rep = parser.validate_completeness(
        doc_id="DOC_WARN",
        pymupdf_char_count=10000,
        docling_char_count=9300,
    )
    assert not rep.is_scanned
    assert rep.needs_manual_review
    assert rep.discrepancy_ratio == 0.07


def test_scanned_document_no_false_warning():
    """
    При графическом скане PyMuPDF возвращает 0 символов.
    Проверка 5% должна пропускаться, а документ классифицироваться как скан.
    """
    parser = DocumentParser(completeness_threshold=0.05)
    rep = parser.validate_completeness(
        doc_id="DOC_SCAN",
        pymupdf_char_count=0,
        docling_char_count=5000,
    )
    assert rep.is_scanned is True
    assert rep.needs_manual_review is False
    assert rep.discrepancy_ratio == 0.0
