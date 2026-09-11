"""Маршруты аналитики, метрик качества и отчетов."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.analytics.schemas import (
    AnalyticsDashboardResponseSchema,
    OperatorDailyMetricResponseSchema,
    SystemIncidentResponseSchema,
)
from src.analytics.service import EXPORT_MAX_DAYS
from src.api.dependencies import AnalyticsServiceDep, require_roles
from src.auth.models import UserRole

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))],
)


@router.get(
    "/dashboard",
    summary="Сводная аналитическая витрина показателей эффективности",
    description="Возвращает операционные показатели эффективности за выбранный временной интервал.",
)
async def get_dashboard(
    analytics_service: AnalyticsServiceDep,
    from_date: Annotated[
        date | None, Query(description="Начало периода")
    ] = None,
    to_date: Annotated[date | None, Query(description="Конец периода")] = None,
) -> AnalyticsDashboardResponseSchema:
    """Возвращает сводные метрики дашборда за указанный период дат."""
    return await analytics_service.get_dashboard(
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/operators",
    summary="Суточные показатели эффективности операторов",
    description="Возвращает показатели работы специалистов поддержки с фильтрацией по дате и линии.",
)
async def get_operator_metrics(
    analytics_service: AnalyticsServiceDep,
    date: Annotated[
        date | None, Query(description="Конкретная дата отчета")
    ] = None,
    line_code: Annotated[
        str | None,
        Query(description="Фильтрация по коду линии поддержки (L1, L2, L3)"),
    ] = None,
) -> list[OperatorDailyMetricResponseSchema]:
    """Возвращает список суточных показателей операторов."""
    return await analytics_service.get_operator_metrics(
        target_date=date,
        line_code=line_code,
    )


@router.get(
    "/incidents",
    summary="Реестр системных технических сбоев портала",
    description="Возвращает журнал системных инцидентов с фильтрацией по статусу и типу сбоя.",
)
async def get_incidents(
    analytics_service: AnalyticsServiceDep,
    status: Annotated[
        Literal["open", "in_review", "resolved"] | None,
        Query(description="Фильтрация по статусу инцидента"),
    ] = None,
    incident_type: Annotated[
        str | None,
        Query(
            description="Фильтрация по типу инцидента (portal_downtime, crypto_plugin, api_error)"
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1, le=100, description="Количество записей на страницу (1-100)"
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Смещение для пагинации"),
    ] = 0,
) -> list[SystemIncidentResponseSchema]:
    """Возвращает отсортированный по дате реестр системных сбоев."""
    incidents = await analytics_service.get_incidents(
        status=status,
        incident_type=incident_type,
        limit=limit,
        offset=offset,
    )
    return [
        SystemIncidentResponseSchema.model_validate(inc) for inc in incidents
    ]


@router.get(
    "/export",
    summary="Выгрузка сводного аналитического отчета",
    description="Формирует экспортный отчет по завершенным обращениям в формате CSV или JSON за выбранный период дат.",
)
async def export_analytics(
    analytics_service: AnalyticsServiceDep,
    from_date: Annotated[date, Query(description="Дата начала периода")],
    to_date: Annotated[date, Query(description="Дата окончания периода")],
    format: Annotated[
        Literal["csv", "json"],
        Query(description="Формат выгрузки (csv или json)"),
    ] = "csv",
) -> Response:
    """Выгружает сводный отчет по завершенным обращениям в формате CSV (utf-8-sig) или JSON."""
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_date_range",
                "message": "Дата начала не может быть позже даты окончания",
            },
        )

    delta = (to_date - from_date).days
    if delta > EXPORT_MAX_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "date_range_too_large",
                "message": f"Максимальный диапазон выгрузки — {EXPORT_MAX_DAYS} дней",
            },
        )

    content, media_type = await analytics_service.generate_export(
        from_date=from_date,
        to_date=to_date,
        fmt=format,
    )

    filename = (
        f"analytics_export_{from_date}_{to_date}.csv"
        if format == "csv"
        else f"analytics_export_{from_date}_{to_date}.json"
    )

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
