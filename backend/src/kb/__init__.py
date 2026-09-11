"""
Пакет базы знаний (Knowledge Base) и конвейера обработки документов (Ingestion).
"""

from src.kb.chunker import HierarchicalChunker, TokenCounter
from src.kb.exceptions import (
    DocumentNotFoundError,
    KbDomainError,
    NodeNotFoundError,
)
from src.kb.parser import DocumentParser
from src.kb.profiler import DocumentProfiler, PipelineProfiler
from src.kb.schemas import (
    BatchProfilingReportSchema,
    CompletenessReportSchema,
    DocumentProfilingMetricsSchema,
    ParsedChunkSchema,
    ParsedDocumentSchema,
    ParsedExtractionResultSchema,
    ParsedNodeSchema,
    StageTimingSchema,
)
from src.kb.tables import TableProcessor

__all__ = [
    "BatchProfilingReportSchema",
    "CompletenessReportSchema",
    "DocumentNotFoundError",
    "DocumentParser",
    "DocumentProfiler",
    "DocumentProfilingMetricsSchema",
    "HierarchicalChunker",
    "KbDomainError",
    "NodeNotFoundError",
    "ParsedChunkSchema",
    "ParsedDocumentSchema",
    "ParsedExtractionResultSchema",
    "ParsedNodeSchema",
    "PipelineProfiler",
    "StageTimingSchema",
    "TableProcessor",
    "TokenCounter",
]
