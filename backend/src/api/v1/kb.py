"""Эндпоинты транспортного слоя базы знаний (API v1)."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status

from src.api.dependencies import (
    CurrentOperatorDep,
    CurrentSupervisorDep,
    KbServiceDep,
)
from src.kb.exceptions import (
    DocumentNotFoundError,
    FaqDraftAlreadyReviewedError,
    FaqDraftNotFoundError,
    NodeNotFoundError,
)
from src.kb.schemas import (
    DocumentUploadItemResponseSchema,
    FaqDraftListResponse,
    FaqReviewRequest,
    FaqReviewResponse,
    KbDocumentDeleteResponse,
    KbDocumentListResponse,
    KbDocumentStatusResponse,
    KbNodeResponse,
    KbNodeUpdateRequest,
)

router = APIRouter(prefix="/kb", tags=["kb"])


@router.post(
    "/documents/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Загрузка пакета регламентов для разбора и индексации",
)
async def upload_documents(
    files: list[UploadFile],
    service: KbServiceDep,
    user: CurrentSupervisorDep,
    regime: Annotated[str, Form()] = "MOS_PORTAL",
) -> list[DocumentUploadItemResponseSchema]:
    """Принимает пакет файлов нормативных актов и методичек для асинхронного разбора."""
    return await service.register_uploaded_files(files=files, regime=regime)


@router.get(
    "/documents",
    status_code=status.HTTP_200_OK,
    summary="Получение реестра документов базы знаний с пагинацией и фильтрацией",
)
async def list_documents(
    service: KbServiceDep,
    user: CurrentOperatorDep,
    regime: Annotated[
        str | None,
        Query(
            description="Фильтр по правовому режиму (MOS_PORTAL, LAW_44, LAW_223)"
        ),
    ] = None,
    doc_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Фильтр по статусу документа (uploaded, parsing, indexing, indexed, failed)",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Количество элементов на странице (1..100)",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Смещение выборки (>= 0)",
        ),
    ] = 0,
) -> KbDocumentListResponse:
    """Возвращает страницу реестра документов базы знаний."""
    return await service.list_documents(
        regime=regime,
        status=doc_status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/documents/{doc_id}/status",
    status_code=status.HTTP_200_OK,
    summary="Получение статуса индексации документа",
)
async def get_document_status(
    doc_id: str,
    service: KbServiceDep,
    user: CurrentOperatorDep,
) -> KbDocumentStatusResponse:
    """Возвращает текущий статус обработки документа и число связанных чанков."""
    try:
        return await service.get_document_status(doc_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_not_found",
                "message": f"Документ с id '{doc_id}' не найден",
            },
        ) from exc


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Каскадное удаление документа из БД и векторного индекса Qdrant",
)
async def delete_document(
    doc_id: str,
    service: KbServiceDep,
    user: CurrentSupervisorDep,
) -> KbDocumentDeleteResponse:
    """Удаляет документ из PostgreSQL и гарантированно зачищает связанные точки в Qdrant."""
    try:
        return await service.delete_document(doc_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_not_found",
                "message": f"Документ с id '{doc_id}' не найден",
            },
        ) from exc


@router.patch(
    "/nodes/{node_id}",
    status_code=status.HTTP_200_OK,
    summary="Точечное обновление метаданных узла документа",
)
async def update_node(
    node_id: str,
    data: KbNodeUpdateRequest,
    service: KbServiceDep,
    user: CurrentSupervisorDep,
) -> KbNodeResponse:
    """Обновляет заголовок и путь узла в БД и синхронизирует payload точек в Qdrant."""
    try:
        return await service.update_node(node_id=node_id, data=data)
    except NodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "node_not_found",
                "message": f"Узел с id '{node_id}' не найден",
            },
        ) from exc


# ── MED-05: Эндпоинты модерации FAQ-черновиков ──────────────────


@router.get(
    "/faq-drafts",
    status_code=status.HTTP_200_OK,
    summary="Получение очереди черновиков FAQ для модерации",
)
async def list_faq_drafts(
    service: KbServiceDep,
    user: CurrentSupervisorDep,
    draft_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Фильтр по статусу черновика (PENDING, APPROVED, REJECTED)",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Количество элементов на странице (1..100)",
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Смещение выборки (>= 0)",
        ),
    ] = 0,
) -> FaqDraftListResponse:
    """Возвращает пагинированный список черновиков FAQ из очереди модерации."""
    return await service.list_faq_drafts(
        status=draft_status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/faq-drafts/{draft_id}/review",
    status_code=status.HTTP_200_OK,
    summary="Ревью черновика FAQ супервизором (approve / reject)",
)
async def review_faq_draft(
    draft_id: str,
    data: FaqReviewRequest,
    service: KbServiceDep,
    user: CurrentSupervisorDep,
) -> FaqReviewResponse:
    """Проводит ревью черновика FAQ: approve создаёт чанк в БЗ, reject отклоняет."""
    try:
        return await service.review_faq_draft(
            draft_id=draft_id,
            action=data.action,
            reviewer_id=user.id,
        )
    except FaqDraftNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "faq_draft_not_found",
                "message": f"Черновик FAQ с id '{draft_id}' не найден",
            },
        ) from exc
    except FaqDraftAlreadyReviewedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "faq_draft_already_reviewed",
                "message": f"Черновик FAQ '{draft_id}' уже был обработан",
            },
        ) from exc


# Экспорт роутера для централизованного подключения Разработчиком 4
kb_router = router
