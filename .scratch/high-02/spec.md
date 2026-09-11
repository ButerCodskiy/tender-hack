# Спецификация задачи HIGH-02: Классификатор обращений и маршрутизатор (QueryRouter)

## 1. Контекст и границы модуля
- **Файл реализации:** `backend/src/rag/router.py`
- **Файл схем данных:** `backend/src/rag/schemas.py`
- **Назначение:** Единовременный анализ запроса клиента с учетом истории диалога (до 6 последних реплик), определение интента, темы, линии поддержки (L1/L2/L3), приоритета (P0/P1/P2) и нормализация поискового запроса (`standalone_query`).

---

## 2. Pydantic-контракт выхода роутера (Строго по ТЗ)

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class EntityItem(BaseModel):
    type: Literal['article', 'law', 'service', 'error_code']
    doc: Optional[Literal['44-FZ', '223-FZ', 'MOS_PORTAL']] = None
    number: Optional[str] = None
    part: Optional[str] = None

class QueryRouterOutput(BaseModel):
    intent: Literal['qa', 'article_lookup', 'procedural', 'chitchat', 'out_of_domain']
    regime_hint: Optional[Literal['44-FZ', '223-FZ', 'MOS_PORTAL']] = None
    topic: Literal[
        'digital_signature_plugin', 'technical_errors', 'api_integration', 'browser_compatibility',
        'payment_delays', 'account_blocking', 'complaints_fas', 'contract_disputes',
        'registration_portal', 'catalog_navigation', 'quote_sessions_rules', 'general_faq',
        'contract_conclusion', 'closing_documents', 'tender_cancellation', 'bid_security',
        'contract_security', 'delivery_acceptance', 'electronic_store', 'other'
    ]
    priority: Literal['P0', 'P1', 'P2']
    support_line: Literal['L1', 'L2', 'L3']
    sentiment: Literal['neutral', 'frustrated', 'aggressive']
    follow_up_type: Literal['none', 'clarification', 'repeat', 'new_topic']
    error_codes: List[str] = Field(default_factory=list)
    escalation_requested: bool = False
    entities: List[EntityItem] = Field(default_factory=list)
    standalone_query: str
    sub_queries: List[str] = Field(default_factory=list, max_length=3)