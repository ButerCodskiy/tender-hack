"""
Тесты модуля профилирования производительности и мониторинга памяти (test_kb_profiler.py).
"""

import json
import time
from pathlib import Path

from src.kb.cli import atomic_write_json
from src.kb.profiler import (
    DocumentProfiler,
    PipelineProfiler,
    get_current_ram_rss_mb,
    get_vram_allocated_mb,
)
from src.kb.schemas import (
    BatchProfilingReportSchema,
    DocumentProfilingMetricsSchema,
)


def test_document_profiler_timings_and_fractions():
    profiler = DocumentProfiler(doc_id="TEST_DOC_01", page_count=5)

    with profiler.stage("extract_pymupdf_text"):
        time.sleep(0.02)

    with profiler.stage("hierarchical_chunking_and_tokenization"):
        time.sleep(0.03)

    metrics = profiler.finish(token_count=350)
    assert isinstance(metrics, DocumentProfilingMetricsSchema)
    assert metrics.doc_id == "TEST_DOC_01"
    assert metrics.page_count == 5
    assert metrics.token_count == 350
    assert metrics.total_duration_sec >= 0.05
    assert metrics.pages_per_sec > 0
    assert metrics.tokens_per_sec > 0

    assert "extract_pymupdf_text" in metrics.stages
    assert "hierarchical_chunking_and_tokenization" in metrics.stages
    assert metrics.stages["extract_pymupdf_text"].percentage > 0
    assert (
        metrics.stages["hierarchical_chunking_and_tokenization"].percentage > 0
    )


def test_memory_fallbacks():
    ram = get_current_ram_rss_mb()
    assert isinstance(ram, float)
    assert ram >= 0.0

    vram = get_vram_allocated_mb()
    assert isinstance(vram, (float, int, str))


def test_pipeline_profiler_aggregation_and_table_format():
    pipeline = PipelineProfiler()

    p1 = pipeline.start_document("DOC_A", page_count=10)
    with p1.stage("stage_1"):
        time.sleep(0.01)
    m1 = p1.finish(token_count=500)
    pipeline.record_document(m1)

    p2 = pipeline.start_document("DOC_B", page_count=20)
    with p2.stage("stage_1"):
        time.sleep(0.01)
    m2 = p2.finish(token_count=1000)
    pipeline.record_document(m2)

    rep = pipeline.build_batch_report()
    assert isinstance(rep, BatchProfilingReportSchema)
    assert rep.total_documents == 2
    assert rep.total_pages == 30
    assert rep.total_tokens == 1500

    doc_table = pipeline.format_table(m1)
    assert "ПРОФИЛИРОВАНИЕ ДОКУМЕНТА: DOC_A" in doc_table
    assert "stage_1" in doc_table

    batch_table = pipeline.format_table()
    assert "СВОДНЫЙ ОТЧЕТ ПРОИЗВОДИТЕЛЬНОСТИ ПАКЕТА" in batch_table
    assert "DOC_A" in batch_table
    assert "DOC_B" in batch_table


def test_atomic_json_export(tmp_path: Path):
    target = tmp_path / "profiling_report.json"
    pipeline = PipelineProfiler()
    p = pipeline.start_document("DOC_ATOMIC", page_count=1)
    pipeline.record_document(p.finish(token_count=100))

    pipeline.save_atomic_report(target)
    assert target.exists()

    with open(target, encoding="utf-8") as f:
        data = json.load(f)
    assert data["total_documents"] == 1
    assert data["documents"][0]["doc_id"] == "DOC_ATOMIC"

    # Проверяем вспомогательную функцию atomic_write_json
    custom_target = tmp_path / "custom.json"
    atomic_write_json(custom_target, {"status": "ok", "count": 42})
    assert custom_target.exists()
    with open(custom_target, encoding="utf-8") as f:
        c_data = json.load(f)
    assert c_data["status"] == "ok"
