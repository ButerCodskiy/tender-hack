"""
Модуль сквозного профилирования производительности и мониторинга памяти (profiler.py).

Реализует:
1. Замер времени исполнения (wall time) ключевых стадий конвейера.
2. Мониторинг RAM процесса (RSS) через psutil с безопасным fallback.
3. Мониторинг VRAM GPU через torch.cuda с детекцией CPU-only.
4. Расчет скоростных характеристик (pages/sec, tokens/sec, доли стадий в %).
5. Красивое табличное форматирование отчетов (ASCII table).
6. Атомарное сохранение агрегированного отчета в profiling_report.json.
"""

import json
import logging
import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.kb.schemas import (
    BatchProfilingReportSchema,
    DocumentProfilingMetricsSchema,
    StageTimingSchema,
)

logger = logging.getLogger(__name__)

# Безопасный импорт psutil
try:
    import psutil  # type: ignore
except ImportError:
    psutil = None
    logger.info(
        "Пакет psutil не установлен. Мониторинг RAM будет использовать fallback-значения."
    )

# Безопасный импорт torch
try:
    import torch  # type: ignore
except ImportError:
    torch = None


def get_current_ram_rss_mb() -> float:
    """Получение текущего объема оперативной памяти процесса (RSS) в МБ."""
    if psutil is not None:
        try:
            process = psutil.Process()
            return round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass
    return 0.0


def get_vram_allocated_mb() -> str | float:
    """Получение объема выделенной памяти GPU (VRAM) в МБ или отметка 'CPU-only'."""
    if torch is not None:
        try:
            if torch.cuda.is_available():
                return round(
                    torch.cuda.max_memory_allocated() / (1024 * 1024), 2
                )
        except Exception:
            pass
    return "CPU-only"


def get_active_device() -> str:
    """Определение основного вычислительного устройства."""
    if torch is not None:
        try:
            if torch.cuda.is_available():
                return f"cuda:0 ({torch.cuda.get_device_name(0)})"
        except Exception:
            pass
    return "cpu"


class DocumentProfiler:
    """
    Профилировщик обработки одного документа.
    Собирает замеры по стадиям и метрики памяти.
    """

    def __init__(self, doc_id: str, page_count: int = 1) -> None:
        self.doc_id = doc_id
        self.page_count = max(page_count, 1)
        self.token_count = 0
        self.stages: dict[str, float] = {}
        self._start_time = time.perf_counter()
        self._end_time: float | None = None
        self.ram_start_mb = get_current_ram_rss_mb()
        self.ram_peak_mb = self.ram_start_mb

    @contextmanager
    def stage(self, stage_name: str) -> Generator[None, None, None]:
        """Контекстный менеджер замера длительности конкретного этапа."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - t0
            self.stages[stage_name] = (
                self.stages.get(stage_name, 0.0) + duration
            )
            curr_ram = get_current_ram_rss_mb()
            self.ram_peak_mb = max(self.ram_peak_mb, curr_ram)

    def finish(self, token_count: int = 0) -> DocumentProfilingMetricsSchema:
        """Завершение профилирования документа и расчет итоговых метрик."""
        self._end_time = time.perf_counter()
        self.token_count = token_count
        total_duration = max(self._end_time - self._start_time, 0.0001)

        ram_end_mb = get_current_ram_rss_mb()
        self.ram_peak_mb = max(self.ram_peak_mb, ram_end_mb)
        ram_delta = round(self.ram_peak_mb - self.ram_start_mb, 2)

        vram = get_vram_allocated_mb()
        device = get_active_device()

        stage_schemas: dict[str, StageTimingSchema] = {}
        for s_name, s_dur in self.stages.items():
            pct = round((s_dur / total_duration) * 100, 1)
            stage_schemas[s_name] = StageTimingSchema(
                stage_name=s_name,
                duration_sec=round(s_dur, 4),
                percentage=pct,
            )

        pages_sec = round(self.page_count / total_duration, 2)
        tokens_sec = round(self.token_count / total_duration, 1)

        return DocumentProfilingMetricsSchema(
            doc_id=self.doc_id,
            page_count=self.page_count,
            token_count=self.token_count,
            total_duration_sec=round(total_duration, 4),
            pages_per_sec=pages_sec,
            tokens_per_sec=tokens_sec,
            ram_start_mb=self.ram_start_mb,
            ram_peak_mb=self.ram_peak_mb,
            ram_delta_mb=ram_delta,
            vram_allocated_mb=vram,
            device=device,
            stages=stage_schemas,
        )


class PipelineProfiler:
    """
    Глобальный профилировщик конвейера.
    Агрегирует метрики по нескольким документам и выводит сводную статистику.
    """

    def __init__(self) -> None:
        self.document_metrics: list[DocumentProfilingMetricsSchema] = []
        self._batch_start_time = time.perf_counter()

    def start_document(
        self, doc_id: str, page_count: int = 1
    ) -> DocumentProfiler:
        """Создание профилировщика для документа."""
        return DocumentProfiler(doc_id=doc_id, page_count=page_count)

    def record_document(self, metrics: DocumentProfilingMetricsSchema) -> None:
        """Регистрация завершенного профиля документа."""
        self.document_metrics.append(metrics)

    def build_batch_report(self) -> BatchProfilingReportSchema:
        """Построение агрегированного отчета по всем документам батча."""
        batch_duration = max(
            time.perf_counter() - self._batch_start_time, 0.0001
        )
        total_docs = len(self.document_metrics)
        total_pages = sum(d.page_count for d in self.document_metrics)
        total_tokens = sum(d.token_count for d in self.document_metrics)
        max_ram = max(
            (d.ram_peak_mb for d in self.document_metrics),
            default=get_current_ram_rss_mb(),
        )

        device = get_active_device()
        vram = get_vram_allocated_mb()
        vram_info = (
            f"{vram} MB" if isinstance(vram, (int, float)) else str(vram)
        )

        avg_pages_sec = round(total_pages / batch_duration, 2)
        avg_tokens_sec = round(total_tokens / batch_duration, 1)

        return BatchProfilingReportSchema(
            total_documents=total_docs,
            total_pages=total_pages,
            total_tokens=total_tokens,
            total_duration_sec=round(batch_duration, 4),
            avg_pages_per_sec=avg_pages_sec,
            avg_tokens_per_sec=avg_tokens_sec,
            max_ram_rss_mb=round(max_ram, 2),
            vram_info=vram_info,
            device=device,
            documents=self.document_metrics,
        )

    def format_table(
        self, metrics: DocumentProfilingMetricsSchema | None = None
    ) -> str:
        """
        Форматирование метрик в аккуратную текстовую таблицу ASCII.
        Если metrics передан — выводит отчет по документу, иначе — сводный отчет по батчу.
        """
        lines: list[str] = []
        border = "+" + "-" * 42 + "+" + "-" * 16 + "+" + "-" * 12 + "+"
        header = f"| {'Этап конвейера':<40} | {'Время (с)':<14} | {'Доля (%)':<10} |"

        if metrics is not None:
            title = f"ПРОФИЛИРОВАНИЕ ДОКУМЕНТА: {metrics.doc_id}"
            lines.append("=" * 74)
            lines.append(f" {title}")
            lines.append(
                f" Страниц: {metrics.page_count} | Токенов: {metrics.token_count} | "
                f"Устройство: {metrics.device}"
            )
            lines.append(
                f" Скорость: {metrics.pages_per_sec} стр/с ({metrics.tokens_per_sec} токенов/с) | "
                f"RAM пик: {metrics.ram_peak_mb} МБ | VRAM: {metrics.vram_allocated_mb}"
            )
            lines.append(border)
            lines.append(header)
            lines.append(border)

            for s_name, s_data in metrics.stages.items():
                row = f"| {s_name:<40} | {s_data.duration_sec:>14.4f} | {s_data.percentage:>9.1f}% |"
                lines.append(row)

            lines.append(border)
            lines.append(
                f"| {'ИТОГО (total_duration)':<40} | "
                f"{metrics.total_duration_sec:>14.4f} | "
                f"{'100.0%':>10} |"
            )
            lines.append(border)
            lines.append("=" * 74)

        else:
            rep = self.build_batch_report()
            title = "СВОДНЫЙ ОТЧЕТ ПРОИЗВОДИТЕЛЬНОСТИ ПАКЕТА"
            lines.append("=" * 74)
            lines.append(f" {title}")
            lines.append(
                f" Документов: {rep.total_documents} | Страниц: {rep.total_pages} | "
                f"Токенов: {rep.total_tokens} | Устройство: {rep.device}"
            )
            lines.append(
                f" Общее время: {rep.total_duration_sec:.2f} с | "
                f"Средняя скорость: {rep.avg_pages_per_sec} стр/с "
                f"({rep.avg_tokens_per_sec} токенов/с)"
            )
            lines.append(
                f" Макс. RAM (RSS): {rep.max_ram_rss_mb} МБ | VRAM GPU: {rep.vram_info}"
            )
            lines.append(border)
            lines.append(
                f"| {'Документ':<40} | {'Время (с)':<14} | {'Стр/сек':<10} |"
            )
            lines.append(border)

            for d in rep.documents:
                doc_snippet = d.doc_id[:38]
                row = (
                    f"| {doc_snippet:<40} | "
                    f"{d.total_duration_sec:>14.4f} | "
                    f"{d.pages_per_sec:>10.2f} |"
                )
                lines.append(row)

            lines.append(border)
            lines.append("=" * 74)

        return "\n".join(lines)

    def save_atomic_report(self, out_path: Path) -> None:
        """
        Атомарное сохранение отчета в JSON через временный файл .tmp
        для предотвращения синтаксически битых файлов при прерывании процесса.
        """
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_data = self.build_batch_report().model_dump(mode="json")

        tmp_path = out_path.with_suffix(f"{out_path.suffix}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        # Атомарная замена файла в файловой системе
        os.replace(tmp_path, out_path)
        logger.info("Отчет профилирования атомарно сохранен: %s", out_path)
