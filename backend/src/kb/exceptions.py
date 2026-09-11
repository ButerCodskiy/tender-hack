"""Доменные исключения подсистемы базы знаний (kb)."""


class KbDomainError(Exception):
    """Базовое исключение домена базы знаний."""


class DocumentNotFoundError(KbDomainError):
    """Исключение: запрашиваемый документ не найден в реестре."""

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        super().__init__(f"Документ с id '{doc_id}' не найден")


class NodeNotFoundError(KbDomainError):
    """Исключение: запрашиваемый узел не найден в структуре документа."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f"Узел с id '{node_id}' не найден")


class FaqDraftNotFoundError(KbDomainError):
    """Исключение: запрашиваемый черновик FAQ не найден в очереди модерации."""

    def __init__(self, draft_id: str) -> None:
        self.draft_id = draft_id
        super().__init__(f"Черновик FAQ с id '{draft_id}' не найден")


class FaqDraftAlreadyReviewedError(KbDomainError):
    """Исключение: черновик FAQ уже был рассмотрен (APPROVED или REJECTED)."""

    def __init__(self, draft_id: str, current_status: str) -> None:
        self.draft_id = draft_id
        self.current_status = current_status
        super().__init__(
            f"Черновик FAQ '{draft_id}' уже имеет статус '{current_status}' и не может быть рассмотрен повторно"
        )
