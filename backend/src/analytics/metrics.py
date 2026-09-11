"""Алгоритмы расчета метрик SLA, CSAT и показателей операторов."""

from decimal import Decimal


def round_metric(value: float | Decimal | None, precision: int = 2) -> float:
    """Округляет метрику до указанной точности с безопасной обработкой None."""
    if value is None:
        return 0.0
    return round(float(value), precision)


def calculate_deflection_rate(bot_resolved: int, total_resolved: int) -> float:
    """Рассчитывает процент автоматизации ботом (Deflection Rate)."""
    if total_resolved <= 0:
        return 0.0
    return round((bot_resolved / total_resolved) * 100.0, 2)
