    ...

async def test_redis_line_queue_priority_buffering_and_fifo(redis_client: aioredis.Redis) -> None:
    """Проверяет приоритетную буферизацию в очереди Redis: P0 в голову, P1/P2 в хвост."""
    ...

================================================================================
FILE: backend\tests\operators\test_queue_recovery.py
================================================================================

"""Тесты аварийного восстановления очередей тикетов из PostgreSQL в Redis (MED-09)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
import uuid6
from src.chat.models import TicketModel, TicketPriority, TicketStatus
from src.core.config import settings
from src.core.redis_client import RedisLineQueue
from src.operators.models import SupportLineModel
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.service import OperatorService

class MockDistributedLock:
    """Мок распределенного замка для тестирования асинхронного контекстного менеджера."""

    def __init__(self, acquired: bool=True) -> None:
        ...

    async def __aenter__(self) -> bool:
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        ...

@pytest.fixture
def mock_operator_service() -> tuple[OperatorService, AsyncMock, AsyncMock, AsyncMock]:
    """Создает изолированный инстанс OperatorService с замоканными репозиториями и очередями."""
    ...

@pytest.mark.asyncio
async def test_recover_queued_tickets_order_and_dispatch(mock_operator_service: tuple[OperatorService, AsyncMock, AsyncMock, AsyncMock]) -> None:
    """Проверяет восстановление очереди в правильном порядке приоритетов (P0 -> P1 -> P2, FIFO) и триггер диспетчеризации."""       
    ...

@pytest.mark.asyncio
async def test_recovery_lock_skips_concurrent_run(mock_operator_service: tuple[OperatorService, AsyncMock, AsyncMock, AsyncMock]) -> None:
    """Проверяет пропуск восстановления, если лок lock:queue_recovery уже занят другим процессом."""
    ...

@pytest.mark.asyncio
async def test_check_timeouts_reconciles_queue_on_desync(mock_operator_service: tuple[OperatorService, AsyncMock, AsyncMock, AsyncMock]) -> None:
    """Проверяет автоматическую сверку и восстановление очереди в задаче check_timeouts при расхождении длин."""
    ...

@pytest.mark.asyncio
async def test_redis_line_queue_rebuild_pipeline() -> None:
    """Проверяет, что rebuild_line_queue выполняет DEL и RPUSH атомарно через pipeline."""
    ...

def test_redis_line_queue_recovery_lock() -> None:
    """Проверяет создание правильного ключа распределенной блокировки recovery."""
    ...

================================================================================
FILE: backend\tests\operators\test_timeouts_scheduler.py
================================================================================

"""Тесты планировщика таймаутов, контроля неактивности и связи операторов (HIGH-12)."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
import pytest
import uuid6
from src.chat.models import MessageModel, MessageModerationStatus, MessageSenderType, TicketModel, TicketPriority, TicketStatus     
from src.chat.repository import TicketRepository
from src.core.config import settings
from src.core.redis_client import RedisChatContext, RedisLineQueue, RedisOperatorEvents, RedisTicketEvents
from src.operators.models import OperatorProfileModel, OperatorShiftStatus, SupportLineModel
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.schemas import CheckTimeoutsResult
from src.operators.service import OperatorService
from src.operators.tasks import check_system_timeouts

def make_mock_line(code: str='L1') -> SupportLineModel:
    """Создает мок линии поддержки."""
    ...

def make_mock_ticket(ticket_id: UUID | None=None, status: str=TicketStatus.BOT_PROCESSING.value, updated_at: datetime | None=None, line_code: str='L1') -> TicketModel:
    """Создает мок тикета для тестов."""
    ...

def make_mock_message(ticket_id: UUID, sender_type: str, text: str, created_at: datetime) -> MessageModel:
    """Создает мок сообщения для тикета."""
    ...

@pytest.fixture
def mock_service_deps():
    """Предоставляет моки всех зависимостей OperatorService."""
    ...

async def test_bot_inactivity_ticket_closed_and_context_cleared(mock_service_deps):
    """Тикет в bot_processing старше 10 минут закрывается, контекст удаляется, шлется событие."""
    ...

async def test_bot_inactivity_skipped_if_race_condition(mock_service_deps):
    """Если оптимистический UPDATE вернул False (гонка с клиентом), контекст не удаляется."""
    ...

async def test_operator_inactivity_warning_sent_once(mock_service_deps):
    """Если последнее сообщение от оператора старше 10 минут, шлется напоминание «Вы еще здесь?»."""
    ...

async def test_operator_inactivity_no_spam_when_last_message_is_system(mock_service_deps):
    """Если последнее сообщение уже системное «Вы еще здесь?», спам не шлется на следующем такте."""
    ...

async def test_operator_inactivity_closed_after_5_minutes_post_warning(mock_service_deps):
    """Если после напоминания клиент молчит >= 5 минут, тикет закрывается и слот освобождается."""
    ...

async def test_operator_inactivity_reset_when_client_replied(mock_service_deps):
    """Если клиент ответил после реплики оператора или системы, таймаут сбрасывается."""
    ...

async def test_operator_disconnected_marked_offline_and_tickets_requeued(mock_service_deps):
    """Оператор с обрывом связи > 10 минут переводится в offline, тикеты возвращаются в очередь lines."""
    ...

async def test_operator_disconnected_multiple_tickets_same_line_single_dispatch(mock_service_deps):
    """При возврате нескольких тикетов одной линии диспетчер триггерится ровно 1 раз (Thundering Herd)."""
    ...

async def test_check_system_timeouts_task_skipped_when_lock_busy():
    """Если распределенная блокировка занята другим процессом, задача пропускается со статусом lock_busy."""
    ...

async def test_check_system_timeouts_task_success():
    """При свободном локе задача успешно выполняет проверку таймаутов и возвращает результат."""
    ...

async def test_check_system_timeouts_task_timeout_handling():
    """При превышении локального таймаута 20 секунд задача возвращает execution_timeout_exceeded."""
    ...

async def test_ticket_repo_close_ticket_by_inactivity_success():
    """Проверяет успешный атомарный conditional UPDATE закрытия тикета."""
    ...

async def test_ticket_repo_close_ticket_by_inactivity_not_found():
    """Проверяет возврат False при несовпадении предиката (гонка)."""
    ...

async def test_operator_repo_set_operator_offline():
    """Проверяет перевод профиля оператора в offline со сбросом disconnected_at."""
    ...

async def test_operator_repo_requeue_operator_tickets():
    """Проверяет перевод незавершенных тикетов оператора в queued со сбросом закрепления."""
    ...

================================================================================
FILE: backend\tests\parser\__init__.py
================================================================================



================================================================================
FILE: backend\tests\parser\test_kb_chunker.py
================================================================================

"""
Тесты иерархического чанкинга и токенизации (test_kb_chunker.py).
"""
from src.kb.chunker import HierarchicalChunker, TokenCounter
from src.kb.schemas import ParsedNodeSchema

def test_token_counter():
    ...

def test_hierarchical_chunker_splitting_and_tail_merging():
    ...

def test_table_chunk_has_table_flag():
    ...

================================================================================
FILE: backend\tests\parser\test_kb_cli.py
================================================================================

"""
Сквозной тест для консольного модуля cli.py (test_kb_cli.py).
Создает синтетические документы регламента (PDF и TXT), запускает run_ingest
и валидирует созданные артефакты JSON.
"""
import json
from pathlib import Path
import fitz
from src.kb.cli import run_ingest
from src.kb.schemas import CompletenessReportSchema, ParsedChunkSchema, ParsedDocumentSchema, ParsedNodeSchema

def test_cli_ingest_pipeline_pdf(tmp_path: Path):
    ...

def test_cli_ingest_pipeline_txt(tmp_path: Path):
    ...

================================================================================
FILE: backend\tests\parser\test_kb_high05.py
================================================================================

"""
Тесты конвейера глубокого разбора документов и таблиц (HIGH-05).
Проверяют:
1. Детерминированную генерацию node_id: 'NODE_' || md5(doc_id || '_' || section_path || '_' || title)
2. Иерархический section_path со стеком заголовков (Раздел > Статья > Пункт)
3. Двойное представление таблиц и привязку context_prefix к чанкам
4. Жизненный цикл фоновой задачи Taskiq index_kb_document (indexing -> indexed / failed)
"""
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from src.kb.chunker import HierarchicalChunker
from src.kb.models import KbDocumentModel
from src.kb.parser import DocumentParser
from src.kb.schemas import ParsedNodeSchema
from src.kb.tasks import index_kb_document

def test_deterministic_node_id_formula():
    """Проверка генерации node_id по строгому правилу ТЗ."""
    ...

def test_deterministic_node_id_uniqueness_on_collision():
    """Проверка детерминированного суффикса при совпадении ключей внутри одного документа."""
    ...

def test_hierarchical_heading_stack_and_section_path(tmp_path: Path):
    """Проверка построения дерева узлов и материализованного пути section_path."""
    ...

def test_chunker_context_prefix_enrichment():
    """Проверка обогащения чанка контекстным префиксом section_path."""
    ...

def test_dual_view_table_and_chunk_flags(tmp_path: Path):
    """Проверка разделения представлений таблицы (table_md + facts в чанках с context_prefix)."""
    ...

@pytest.mark.asyncio
async def test_taskiq_index_kb_document_success_lifecycle(tmp_path: Path):
    """Проверка полного жизненного цикла Taskiq задачи при успехе (indexing -> indexed)."""
    ...

@pytest.mark.asyncio
async def test_taskiq_index_kb_document_failure_lifecycle(tmp_path: Path):
    """Проверка обработки сбоя в задаче Taskiq (indexing -> failed)."""
    ...

================================================================================
FILE: backend\tests\parser\test_kb_parser.py
================================================================================

"""
Тесты контроля полноты и детекции сканов (test_kb_parser.py).
"""
from src.kb.parser import DocumentParser

def test_completeness_ok():
    ...

def test_completeness_exceeded():
    ...

def test_scanned_document_no_false_warning():
    """
    При графическом скане PyMuPDF возвращает 0 символов.
    Проверка 5% должна пропускаться, а документ классифицироваться как скан.
    """
    ...

================================================================================
FILE: backend\tests\parser\test_kb_profiler.py
================================================================================

"""
Тесты модуля профилирования производительности и мониторинга памяти (test_kb_profiler.py).
"""
import json
import time
from pathlib import Path
from src.kb.cli import atomic_write_json
from src.kb.profiler import DocumentProfiler, PipelineProfiler, get_current_ram_rss_mb, get_vram_allocated_mb
from src.kb.schemas import BatchProfilingReportSchema, DocumentProfilingMetricsSchema

def test_document_profiler_timings_and_fractions():
    ...

def test_memory_fallbacks():
    ...

def test_pipeline_profiler_aggregation_and_table_format():
    ...

def test_atomic_json_export(tmp_path: Path):
    ...

================================================================================
FILE: backend\tests\parser\test_kb_schemas.py
================================================================================

"""
Тесты Pydantic v2 схем модуля kb (test_kb_schemas.py).
"""
from datetime import date
from src.kb.schemas import CompletenessReportSchema, ParsedChunkSchema, ParsedDocumentSchema, ParsedNodeSchema

def test_parsed_document_schema():
    ...

def test_parsed_node_schema():
    ...

def test_parsed_chunk_schema_ddl_consistency():
    """
    Проверяем, что token_count исключен из персистентного model_dump,
    чтобы не конфликтовать со схемой DDL таблицы kb_chunks.
    """
    ...

def test_completeness_report_schema():
    ...

================================================================================
FILE: backend\tests\parser\test_kb_tables.py
================================================================================

"""
Тесты обработки таблиц, Header Propagation и линеаризации (test_kb_tables.py).
"""
from src.kb.tables import TableProcessor

def test_header_propagation():
    ...

def test_table_markdown_generation():
    ...

def test_table_linearization():
    ...

================================================================================
FILE: backend\tests\rag\test_copilot.py
================================================================================

"""Тесты аналитической подсказки оператора AI Copilot (HIGH-04)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import uuid6
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.auth.models import RoleModel, UserModel
from src.chat.models import ChatModel, TicketModel, TicketStatus
from src.operators.models import TicketCopilotSummaryModel
from src.operators.repository import OperatorRepository
from src.operators.schemas import CopilotSummaryResponseSchema
from src.operators.service import OperatorService
from src.rag.copilot import CopilotService, MockCopilotLlmClient
from src.rag.qdrant_tickets import RESOLVED_TICKETS_COLLECTION, SEED_RESOLVED_TICKETS, ensure_resolved_tickets_collection, search_similar_resolved_tickets
from src.rag.schemas import CopilotLlmOutputSchema, CopilotPayloadSchema
from src.rag.tasks import generate_copilot_summary

def test_copilot_payload_schema_validation() -> None:
    """Проверяет валидацию полезной нагрузки очереди copilot_queue."""
    ...

def test_copilot_llm_output_schema() -> None:
    """Проверяет сериализацию и значения по умолчанию CopilotLlmOutputSchema."""
    ...

@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l2_crypto_marker() -> None:
    """Проверяет авто-назначение линии L2 при обнаружении ошибки КриптоПро / ЭЦП."""
    ...

@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l1_regulation_marker() -> None:
    """Проверяет авто-назначение линии L1 при вопросе о регламенте и котировочных сессиях."""
    ...

@pytest.mark.asyncio
async def test_mock_copilot_llm_client_l3_dispute_marker() -> None:
    """Проверяет авто-назначение линии L3 при маркерах спора / угрозе жалобы в ФАС."""
    ...

@pytest.mark.asyncio
async def test_mock_copilot_llm_client_timeout_simulation() -> None:
    """Проверяет генерацию исключения при симуляции сбоя fail_times."""
    ...

@pytest.mark.asyncio
async def test_qdrant_tickets_ensure_and_seed() -> None:
    """Проверяет создание коллекции и загрузку сид-корпуса прецедентов."""
    ...

@pytest.mark.asyncio
async def test_qdrant_tickets_search_mocked() -> None:
    """Проверяет маппинг результатов векторного поиска в SimilarTicketItemSchema."""
    ...

@pytest.mark.asyncio
async def test_qdrant_tickets_graceful_degradation() -> None:
    """Проверяет возврат пустого списка при сбое или недоступности Qdrant."""
    ...

@pytest.mark.asyncio
async def test_copilot_service_assembly() -> None:
    """Проверяет сборку полного объекта CopilotSummaryResponseSchema."""
    ...

@pytest.mark.asyncio
async def test_open_ticket_returns_existing_summary_unit() -> None:
    """Сценарий Б: open_ticket возвращает сохраненную подсказку из объекта тикета."""
    ...

@pytest.mark.asyncio
async def test_open_ticket_when_summary_not_ready_unit() -> None:
    """Сценарий А: open_ticket отдает copilot_summary=None, если Taskiq еще не завершил генерацию."""
    ...

@pytest.mark.asyncio
async def test_generate_copilot_summary_task_flow_mocked() -> None:
    """Проверяет сценарий работы задачи generate_copilot_summary с mock-хранилищами."""
    ...

@pytest.mark.asyncio
async def test_copilot_failure_isolation_task_mocked() -> None:
    """Проверяет изоляцию сбоя: при падении LLM задача сохраняет деградированную подсказку."""
    ...

@pytest.mark.asyncio
async def test_ticket_copilot_summary_persistence(async_session: AsyncSession) -> None:
    """Проверяет сохранение, извлечение и каскадное удаление модели TicketCopilotSummaryModel."""
    ...

================================================================================
FILE: backend\tests\rag\test_copilot_ollama_fallback.py
================================================================================

"""Юнит-тесты связки Copilot с локальной LLM и бесшовного отката при таймауте (Подплан 3)."""
from unittest.mock import AsyncMock
import pytest
import uuid6
from src.rag.copilot import CopilotService, OllamaCopilotLlmClient
from src.rag.schemas import CopilotLlmOutputSchema

@pytest.mark.asyncio
async def test_ollama_copilot_client_success() -> None:
    """Проверяет успешное получение и парсинг ответа от Ollama."""
    ...

@pytest.mark.asyncio
async def test_ollama_copilot_client_timeout_fallback() -> None:
    """Проверяет бесшовный откат на быстрый шаблон при таймауте локальной модели."""
    ...

@pytest.mark.asyncio
async def test_copilot_service_default_fallback_without_crash() -> None:
    """Проверяет отказоустойчивость сервиса при сбое инференса."""
    ...

================================================================================
FILE: backend\tests\rag\test_generator.py
================================================================================

"""Тесты потокового генератора ответов, буферизации предложений и факт-чекинга."""
import uuid6
from src.rag.generator import FactCheckingGuard, MockLlmStreamClient, RagStreamGenerator, SentenceBuffer
from src.rag.prompts import format_rag_prompt
from src.rag.schemas import ContextChunk, RagDegradedModeEventSchema, RagDoneEventSchema, RagSentenceEventSchema

def _build_mock_chunk(idx: int=1, quote: str='Участник закупки вправе сформировать и подписать протокол разногласий в личном кабинете поставщика в течение 3 рабочих дней с момента публикации проекта контракта. Размер обеспечения составляет 1% (500 000 рублей).', title: str='Раздел 4. Подписание протоколов', section_path: str='Регламент котировочных сессий > Раздел 4') -> ContextChunk:
    """Создает тестовый фрагмент нормативного документа."""
    ...

def test_sentence_buffer_syllable_streaming() -> None:
    """Проверяет склейку разрозненных токенов в законченные фразы через razdel."""
    ...

def test_sentence_buffer_markdown_lists_flush() -> None:
    """Проверяет сброс буфера по двойному переносу строки для Markdown-списков."""
    ...

def test_sentence_buffer_flush_tail_without_period() -> None:
    """Проверяет выгрузку остатка буфера без завершающей точки при окончании потока."""
    ...

def test_fact_checking_guard_no_numbers() -> None:
    """Фраза без чисел и дат признается валидной."""
    ...

def test_fact_checking_guard_footnote_self_trigger_protection() -> None:
    """Проверяет защиту от самострела: индекс сноски [^1] или [1] не трактуется как число."""
    ...

def test_fact_checking_guard_valid_numbers_and_dates() -> None:
    """Проверяет успешную верификацию чисел, сумм с пробелами, процентов и дат."""
    ...

def test_fact_checking_guard_number_without_footnote_fails() -> None:
    """Число во фразе без сноски бракуется (verified: False), если его не было в вопросе."""
    ...

def test_fact_checking_guard_number_from_query_allowed_without_footnote() -> None:
    """Число из вопроса пользователя разрешено повторять без нормативной сноски."""
    ...

def test_fact_checking_guard_invalid_footnote_index() -> None:
    """Сноска с несуществующим индексом (N > len(chunks) или N <= 0) бракуется."""
    ...

def test_fact_checking_guard_hallucinated_number_fails() -> None:
    """Галлюцинированное число, отсутствующее в процитированном чанке, бракуется."""
    ...

async def test_rag_stream_generator_full_success_flow() -> None:
    """Проверяет полный успешный поток: предложения, сноски, итоговое событие done."""
    ...

async def test_rag_stream_generator_unverified_sentence_sets_all_verified_false() -> None:
    """Предложение с непроверенным числом получает verified: False и сбрасывает all_verified."""
    ...

async def test_rag_stream_generator_degraded_mode_on_llm_failure() -> None:
    """При падении LLM-клиента генератор эмитит degraded_mode вместо 500 ошибки."""
    ...

def test_format_rag_prompt_deflection_and_formatting() -> None:
    """Проверяет включение правил deflection и разметки источников в промпт."""
    ...

================================================================================
FILE: backend\tests\rag\test_query_router_pipeline.py
================================================================================

"""Юнит-тесты интеграции QueryRouter с поисковым пайплайном и детерминированного шлюза нормативных статей (Подплан 2)."""
from src.rag.reranker import HybridReranker
from src.rag.schemas import ContextChunk, RagQueryRequestSchema, RagSourceChunkSchema

def test_rag_source_chunk_schema_pin_to_top_default() -> None:
    """Проверяет наличие и дефолтное значение флага pin_to_top в схемах источников."""
    ...

def test_deterministic_pin_to_top_for_article_93_44fz() -> None:
    """Проверяет, что узел со статьей 93 44-ФЗ в заголовке поднимается в топ-1 с pin_to_top=True."""
    ...

def test_deterministic_pin_to_top_for_article_112() -> None:
    """Проверяет детерминированный подъем узла с заголовком 'Статья 112' по запросу 'статья 112'."""
    ...

def test_standalone_query_construction_logic() -> None:
    """Проверяет, что очищенный/нормализованный standalone_query используется в RagQueryRequestSchema."""
    ...

================================================================================
FILE: backend\tests\rag\test_rag_pipeline_hardening.py
================================================================================

"""Тесты критического рефакторинга и защиты RAG-пайплайна (Hardening & Verification).

Проверяемые требования:
1. LexicalDenseReranker: расчет S_final = 0.60 * S_dense + 0.40 * R_lex и корректная сортировка.
2. Retriever: отсечение низкоуверенных запросов по score_threshold (0.40) и сохранение при спектральном разрыве (delta >= 0.08, s1 >= 0.28).
3. Retriever: ограничение длины родительского контекста kb_nodes (до 6000 символов).
4. RagService: режим деградации без вызова LLM при пустых источниках.
5. FactCheckingGuard & Generator: активная маскировка непроверенных предложений дисклеймером.
6. ChatService & QueryRouter: перехват chitchat / out_of_domain без RAG, эскалация ошибок 0x... в P0/L2, передача истории диалога.  
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
import uuid6
from src.chat.models import ChatModel, MessageModel, MessageSenderType, TicketModel, TicketPriority, TicketStatus
from src.chat.schemas import ClientSendMessageRequestSchema
from src.chat.service import ChatService
from src.rag.generator import UNVERIFIED_FACTS_DISCLAIMER, MockLlmStreamClient, RagStreamGenerator
from src.rag.reranker import LexicalDenseReranker
from src.rag.retriever import Retriever
from src.rag.schemas import ContextChunk, QueryRouterOutput, RagDegradedModeEventSchema, RagDoneEventSchema, RagQueryRequestSchema, RagSentenceEventSchema
from src.rag.service import RagService

def test_lexical_dense_reranker_scoring_and_sorting() -> None:
    """Проверяет формулу S_final = 0.60 * S_dense + 0.40 * R_lex и переранжирование."""
    ...

def test_lexical_dense_reranker_empty_chunks() -> None:
    """Проверяет обработку пустого списка чанков."""
    ...

@pytest.mark.asyncio
async def test_retriever_low_confidence_spectral_gap_rejects_noise() -> None:
    """При top-1 < 0.40 и отсутствии спектрального разрыва (delta < 0.08) ретривер возвращает []."""
    ...

@pytest.mark.asyncio
async def test_retriever_spectral_gap_accepts_isolated_peak() -> None:
    """При top-1 < 0.40, но delta >= 0.08 и s1 >= 0.28, изолированный пик принимается."""
    ...

@pytest.mark.asyncio
async def test_retriever_caps_parent_node_length() -> None:
    """Проверяет ограничение длины родительского контекста 6000 символами."""
    ...

@pytest.mark.asyncio
async def test_rag_service_empty_retrieval_triggers_degraded_mode_without_llm() -> None:
    """При пустом результате поиска RagService эмитит degraded_mode без вызова генератора."""
    ...

@pytest.mark.asyncio
async def test_generator_masks_hallucinated_numbers_with_safe_disclaimer() -> None:
    """Генератор заменяет предложение с неподтвержденными числами на безопасный дисклеймер."""
    ...

@pytest.mark.asyncio
async def test_chat_service_intercepts_chitchat_and_out_of_domain() -> None:
    """ChatService перехватывает chitchat и out_of_domain без обращения к RAG."""
    ...

@pytest.mark.asyncio
async def test_chat_service_elevates_error_code_to_p0_and_passes_history() -> None:
    """При наличии кода 0x... тикет повышается до P0, а история реплик передается в RAG."""
    ...

================================================================================
FILE: backend\tests\rag\test_rag_retriever.py
================================================================================

from unittest.mock import AsyncMock
import pytest
from qdrant_client import AsyncQdrantClient
from src.core.config import settings
from src.kb.qdrant import EmbeddingStub, init_knowledge_base_collection
from src.rag.retriever import Retriever
from src.rag.schemas import RagSourceChunkSchema

@pytest.fixture
async def client() -> AsyncQdrantClient:
    ...

@pytest.fixture
def query() -> str:
    ...

async def test_retriever_retrieve(client: AsyncQdrantClient, query: str) -> None:
    ...

async def test_retriever_respects_top_k(client: AsyncQdrantClient) -> None:
    ...

async def test_retriever_handles_qdrant_error() -> None:
    ...

================================================================================
FILE: backend\tests\rag\test_rag_service.py
================================================================================

"""Тесты сервисной заглушки поискового ядра RagService и контрактов потоковых событий."""
from unittest.mock import AsyncMock
import uuid6
from pydantic import TypeAdapter
from src.rag.generator import MockLlmStreamClient, RagStreamGenerator
from src.rag.retriever import Retriever
from src.rag.schemas import RagDegradedModeEventSchema, RagDoneEventSchema, RagQueryRequestSchema, RagResponseSchema, RagSentenceEventSchema, RagSourceChunkSchema, RagSourcesEventSchema, RagStatusEventSchema, RagStreamEvent
from src.rag.service import RagService

def _get_mock_service(chunks: list[RagSourceChunkSchema] | None=None) -> RagService:
    """Создает изолированный RagService с мок-генератором и мок-ретривером."""
    ...

async def test_generate_answer_stream_flow() -> None:
    """Проверяет корректность потока событий SSE: порядок, структуру и типы."""
    ...

async def test_generate_answer_degraded_mode_when_no_chunks() -> None:
    """Проверяет переход в режим деградации без вызова LLM при отсутствии найденных чанков (ADR 0005)."""
    ...

async def test_generate_answer_without_message_id() -> None:
    """Проверяет генерацию ответа без предварительно заданного message_id."""
    ...

def test_rag_stream_event_discriminated_union() -> None:
    """Проверяет валидацию потоковых событий через дискриминированное объединение Pydantic."""
    ...

async def test_search_and_answer_backward_compatibility() -> None:
    """Проверяет обратную совместимость метода search_and_answer для существующих тестов."""
    ...

================================================================================
FILE: backend\tests\rag\test_reranker_hybrid.py
================================================================================

"""Юнит-тесты гибридного реранкера (ADR-0001, ADR-0006: Weighted Dense + Lexical Keyword Match)."""
from src.rag.reranker import HybridReranker, LexicalDenseReranker
from src.rag.schemas import ContextChunk

def test_hybrid_reranker_weights_formula() -> None:
    """Проверяет расчет по формуле S = 0.65 * S_dense + 0.35 * S_lexical."""
    ...

def test_exact_hex_error_code_boost() -> None:
    """Проверяет приоритетный подъем чанка с точным совпадением hex-кода системной ошибки (0x...)."""
    ...

def test_exact_law_article_boost() -> None:
    """Проверяет точное совпадение по номеру статьи закона (ст. 93 44-ФЗ)."""
    ...

def test_empty_chunks_and_boundary_scores() -> None:
    """Проверяет граничные случаи: пустой список чанков и нормализацию скора."""
    ...

================================================================================
FILE: backend\tests\rag\test_router.py
================================================================================

"""Комплексные тесты классификатора и маршрутизатора QueryRouter."""
import pytest
from src.rag.router import DeterministicPrePass, MockLlmClient, QueryRouter
from src.rag.schemas import QueryRouterOutput

def test_pre_pass_error_code_extraction() -> None:
    """Проверяет извлечение шестнадцатеричных кодов ошибок (0x...)."""
    ...

def test_pre_pass_law_and_article_extraction() -> None:
    """Проверяет извлечение правового режима, законов и статей."""
    ...

def test_caps_lock_detection_consecutive_client_messages() -> None:
    """Проверяет детекцию >= 3 сообщений подряд в верхнем регистре (КАПС) от клиента."""
    ...

def test_p0_threats_and_legal_disputes() -> None:
    """Проверяет триггеры приоритета P0: суд, ФАС, прокуратура, жалобы."""
    ...

def test_p0_financial_disputes() -> None:
    """Проверяет триггеры P0: спор по блокировке обеспечения или списанию средств."""
    ...

def test_p1_deadlines_and_error_codes() -> None:
    """Проверяет триггеры приоритета P1: дедлайн < 24ч и коды ошибок."""
    ...

def test_escalation_request_detection() -> None:
    """Проверяет выявление намерения перевода на человека-оператора."""
    ...

@pytest.mark.asyncio
async def test_post_arbiter_enforces_l2_and_p1_on_error_code() -> None:
    """Проверяет инвариант: наличие кода ошибки поднимает линию минимум до L2 и приоритет до P1."""
    ...

@pytest.mark.asyncio
async def test_post_arbiter_topic_to_line_mapping() -> None:
    """Проверяет маппинг тем на линии поддержки: темы L2 -> L2, темы L3 -> L3."""
    ...

@pytest.mark.asyncio
async def test_post_arbiter_p0_on_caps_lock_history() -> None:
    """Проверяет принудительное выставление P0 при 3 сообщениях КАПСом подряд."""
    ...

@pytest.mark.asyncio
async def test_timeout_triggers_enriched_fallback() -> None:
    """Проверяет, что при таймауте LLM (> 1.5 с) фолбэк сохраняет коды ошибок, линию L2 и приоритет P1."""
    ...

@pytest.mark.asyncio
async def test_timeout_fallback_preserves_p0_and_l3_for_threats() -> None:
    """Проверяет, что при таймауте LLM фолбэк сохраняет P0 и L3 для угроз судом/ФАС."""
    ...

@pytest.mark.asyncio
async def test_json_validation_retry_success() -> None:
    """Проверяет повторный запрос при однократном сбое генерации/валидации JSON."""
    ...

@pytest.mark.asyncio
async def test_sub_queries_truncation_and_chitchat_cleaning() -> None:
    """Проверяет обрезание sub_queries до 3 и сброс в [] для приветствий/chitchat."""
    ...

@pytest.mark.asyncio
async def test_anaphora_and_context_history() -> None:
    """Проверяет передачу контекста диалога и разрешение анафоры."""
    ...

================================================================================
FILE: backend\tests\unit\test_operators_api.py
================================================================================

"""Модульные тесты REST API рабочего места оператора (HIGH-10)."""
from datetime import datetime
from unittest.mock import AsyncMock
import pytest
import uuid6
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from src.api.dependencies import get_current_user, get_operator_service, require_operator_user
from src.api.v1.operators import router as operators_router
from src.auth.models import RoleModel, UserModel
from src.chat.schemas import MessageResponseSchema
from src.core.config import settings
from src.operators.schemas import ClientInfoSchema, OperatorProfileResponseSchema, OperatorSidebarTicketSchema, OperatorTicketWorkspaceSchema, ResolveTicketResponseSchema, TransferTicketResponseSchema
from src.operators.service import OperatorService

@pytest.fixture
def mock_operator_service() -> AsyncMock:
    """Создает мок сервиса операторов."""
    ...

@pytest.fixture
def current_operator() -> UserModel:
    """Создает тестового пользователя с ролью оператора."""
    ...

@pytest.fixture
def test_app(mock_operator_service: AsyncMock, current_operator: UserModel) -> FastAPI:
    """Создает тестовое приложение с переопределенными зависимостями."""
    ...

@pytest.fixture
async def api_client(test_app: FastAPI) -> AsyncClient:
    """Предоставляет асинхронный HTTP-клиент."""
    ...

@pytest.mark.asyncio
async def test_get_my_shift_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет GET /api/v1/operators/me/shift."""
    ...

@pytest.mark.asyncio
async def test_patch_my_shift_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет PATCH /api/v1/operators/me/shift."""
    ...

@pytest.mark.asyncio
async def test_get_my_tickets_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет GET /api/v1/operators/tickets."""
    ...

@pytest.mark.asyncio
async def test_open_ticket_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/open."""
    ...

@pytest.mark.asyncio
async def test_send_message_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/messages."""
    ...

@pytest.mark.asyncio
async def test_transfer_ticket_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/transfer."""
    ...

@pytest.mark.asyncio
async def test_resolve_ticket_endpoint(api_client: AsyncClient, mock_operator_service: AsyncMock, current_operator: UserModel) -> None:
    """Проверяет POST /api/v1/operators/tickets/{ticket_id}/resolve."""
    ...

================================================================================
FILE: backend\tests\unit\test_operators_workspace.py
================================================================================

"""Модульные тесты сервисного слоя рабочего места оператора (HIGH-10)."""
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID
import pytest
import uuid6
from fastapi import HTTPException
from src.auth.models import ClientProfileModel, UserModel
from src.chat.models import ChatModel, MessageModel, MessageModerationStatus, MessageSenderType, TicketModel, TicketStatus
from src.chat.moderation import ProfanityModerator
from src.chat.repository import TicketRepository
from src.core.config import settings
from src.core.redis_client import RedisChatContext, RedisLineQueue, RedisOperatorEvents, RedisTicketEvents
from src.operators.models import OperatorProfileModel, SupportLineModel
from src.operators.repository import OperatorRepository, SupportLineRepository
from src.operators.service import OperatorService

@pytest.fixture
def mock_service() -> tuple[OperatorService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    """Создает изолированный инстанс OperatorService со всеми замоканными зависимостями."""
    ...

def create_dummy_profile(user_id: UUID, line_id: int=1, line_code: str='L1', shift_status: str='offline', max_slots: int=5) -> OperatorProfileModel:
    """Вспомогательная фабрика тестового профиля оператора."""
    ...

def create_dummy_ticket(ticket_id: UUID, operator_id: UUID | None, line_code: str='L1', status: str=TicketStatus.ASSIGNED.value, priority: str='P1') -> TicketModel:
    """Вспомогательная фабрика тестового обращения с клиентом и сообщениями."""
    ...

@pytest.mark.asyncio
async def test_operator_shift_lifecycle_and_validation(mock_service: tuple) -> None:
    """Проверяет переключение статуса смены, валидацию и триггер ребалансировки."""
    ...

@pytest.mark.asyncio
async def test_open_ticket_idempotency_and_forbidden(mock_service: tuple) -> None:
    """Проверяет перевод assigned -> in_progress, событие operator_joined и идемпотентность."""
    ...

@pytest.mark.asyncio
async def test_resolve_ticket_frees_slot_and_triggers_dispatch(mock_service: tuple) -> None:
    """Проверяет закрытие обращения, очистку контекста Redis и запуск ребалансировки."""
    ...

@pytest.mark.asyncio
async def test_transfer_ticket_queue_migration_and_system_message(mock_service: tuple) -> None:
    """Проверяет перевод тикета на целевую линию, системное сообщение и очереди."""
    ...

@pytest.mark.asyncio
async def test_send_operator_message_and_profanity_block(mock_service: tuple) -> None:
    """Проверяет отправку сообщения оператором, сохранение в БД и блокировку мата."""
    ...

@pytest.mark.asyncio
async def test_get_sidebar_tickets_formatting(mock_service: tuple) -> None:
    """Проверяет форматирование списка закрепленных тикетов для сайдбара."""
    ...

================================================================================
FILE: scripts\ast_skeleton.py
================================================================================

import ast
import contextlib
import io
import sys
from pathlib import Path

def is_docstring(stmt: ast.AST) -> bool:
    """Проверяет, является ли узел синтаксического дерева строковой константой (докстрингом)."""
    ...

class SkeletonTransformer(ast.NodeTransformer):
    """Трансформер AST, сохраняющий только импорты, объявления классов,

    сигнатуры функций/методов с type hints и докстринги.
    Тела всех функций и методов заменяются на ast.Ellipsis (...).
    """

    def visit_Module(self, node: ast.Module) -> ast.Module:
        ...

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        ...

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        ...

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        ...

    def _transform_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.FunctionDef | ast.AsyncFunctionDef:
        ...

def extract_skeleton(source_code: str, filename: str='<string>') -> str:
    """Парсит синтаксическое дерево и возвращает скелет исходного кода."""
    ...

def should_skip(path: Path) -> bool:
    """Проверяет, находится ли путь в исключаемых служебных директориях."""
    ...

def find_files(target: Path) -> list[Path]:
    """Находит Python-файлы: по файлу, директории или поиску по имени файла."""
    ...

def main() -> None:
    ...