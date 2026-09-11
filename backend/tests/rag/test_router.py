"""Комплексные тесты классификатора и маршрутизатора QueryRouter."""

import pytest

from src.rag.router import (
    DeterministicPrePass,
    MockLlmClient,
    QueryRouter,
)
from src.rag.schemas import QueryRouterOutput


def test_pre_pass_error_code_extraction() -> None:
    """Проверяет извлечение шестнадцатеричных кодов ошибок (0x...)."""
    query = (
        "При подписании оферты плагин выдает код 0x80090006, "
        "а ранее была ошибка 0x00000057. Повторно 0x80090006."
    )
    result = DeterministicPrePass.analyze(query)
    assert len(result.error_codes) == 2
    assert "0x80090006" in result.error_codes
    assert "0x00000057" in result.error_codes

    # Проверка сущностей
    code_entities = [e for e in result.entities if e.type == "error_code"]
    assert len(code_entities) == 2
    assert {e.number for e in code_entities} == {"0x80090006", "0x00000057"}


def test_pre_pass_law_and_article_extraction() -> None:
    """Проверяет извлечение правового режима, законов и статей."""
    # 44-ФЗ
    query_44 = "Как применить ч. 1 ст. 93 Федерального закона № 44-ФЗ?"
    res_44 = DeterministicPrePass.analyze(query_44)
    assert res_44.regime_hint == "44-FZ"
    law_ent = next((e for e in res_44.entities if e.type == "law"), None)
    assert law_ent is not None
    assert law_ent.doc == "44-FZ"

    art_ent = next((e for e in res_44.entities if e.type == "article"), None)
    assert art_ent is not None
    assert art_ent.number == "93"
    assert art_ent.part == "1"
    assert art_ent.doc == "44-FZ"

    # 223-ФЗ
    query_223 = "Разъясните правила по статье 3 223-ФЗ"
    res_223 = DeterministicPrePass.analyze(query_223)
    assert res_223.regime_hint == "223-FZ"

    # Портал поставщиков
    query_portal = "Как подать ценовое предложение в котировочной сессии на Портале поставщиков?"
    res_portal = DeterministicPrePass.analyze(query_portal)
    assert res_portal.regime_hint == "MOS_PORTAL"


def test_caps_lock_detection_consecutive_client_messages() -> None:
    """Проверяет детекцию >= 3 сообщений подряд в верхнем регистре (КАПС) от клиента."""
    # Реплики клиента чередуются с ответами бота
    history = [
        {"sender": "client", "text": "ПОЧЕМУ НЕ РАБОТАЕТ ВАШ ПЛАГИН?"},
        {"sender": "bot", "text": "Здравствуйте! Проверьте сертификат."},
        {
            "sender": "client",
            "text": "Я УЖЕ ВСЕ ПЕРЕУСТАНОВИЛ НИЧЕГО НЕ РАБОТАЕТ!",
        },
        {"sender": "bot", "text": "Уточните версию КриптоПро."},
    ]
    current_caps = "СКОЛЬКО МОЖНО ЖДАТЬ ОТВЕТА ОПЕРАТОРА?"

    assert (
        DeterministicPrePass.check_consecutive_caps(current_caps, history)
        is True
    )

    # Проверка PrePass analyze
    res = DeterministicPrePass.analyze(current_caps, history)
    assert res.caps_p0_triggered is True

    # Отрицательный тест 1: только 2 капс-сообщения от клиента
    history_short = [
        {"sender": "client", "text": "ПОЧЕМУ НЕ РАБОТАЕТ ВАШ ПЛАГИН?"},
        {"sender": "bot", "text": "Здравствуйте!"},
    ]
    assert (
        DeterministicPrePass.check_consecutive_caps(
            current_caps, history_short
        )
        is False
    )

    # Отрицательный тест 2: короткие сообщения ("ДА", "ОК") не должны считаться капсом
    assert DeterministicPrePass.is_caps_message("ДА") is False
    assert DeterministicPrePass.is_caps_message("ОК") is False
    assert (
        DeterministicPrePass.is_caps_message("ЭЦП И ФАС") is False
    )  # < 10 букв


def test_p0_threats_and_legal_disputes() -> None:
    """Проверяет триггеры приоритета P0: суд, ФАС, прокуратура, жалобы."""
    queries = [
        "Мы готовим официальную жалобу в ФАС на действия заказчика!",
        "Если не решите проблему, подаем иск в арбитражный суд",
        "Будем обращаться в прокуратуру с исковым заявлением",
    ]
    for q in queries:
        res = DeterministicPrePass.analyze(q)
        assert res.threat_p0_triggered is True, f"Failed on query: {q}"


def test_p0_financial_disputes() -> None:
    """Проверяет триггеры P0: спор по блокировке обеспечения или списанию средств."""
    queries = [
        "Вы незаконно списали деньги со спецсчета, не согласен с удержанием!",
        "Ошибочно заблокировали обеспечение заявки, верните средства немедленно!",
        "Неправомерное списание денег по котировочной сессии",
    ]
    for q in queries:
        res = DeterministicPrePass.analyze(q)
        assert res.financial_dispute_p0_triggered is True, (
            f"Failed on query: {q}"
        )


def test_p1_deadlines_and_error_codes() -> None:
    """Проверяет триггеры приоритета P1: дедлайн < 24ч и коды ошибок."""
    # Дедлайн
    deadline_query = (
        "Котировочная сессия заканчивается через 2 часа, как подписать оферту?"
    )
    res_deadline = DeterministicPrePass.analyze(deadline_query)
    assert res_deadline.deadline_p1_triggered is True

    # Код ошибки
    error_query = "Сбой плагина ЭЦП с кодом 0x80090006"
    res_error = DeterministicPrePass.analyze(error_query)
    assert "0x80090006" in res_error.error_codes


def test_escalation_request_detection() -> None:
    """Проверяет выявление намерения перевода на человека-оператора."""
    queries = [
        "Позовите человека, бот не помогает",
        "Переведите на оператора пожалуйста",
        "Соедините со специалистом",
    ]
    for q in queries:
        res = DeterministicPrePass.analyze(q)
        assert res.escalation_requested is True, f"Failed on query: {q}"


@pytest.mark.asyncio
async def test_post_arbiter_enforces_l2_and_p1_on_error_code() -> None:
    """Проверяет инвариант: наличие кода ошибки поднимает линию минимум до L2 и приоритет до P1."""
    # LLM ошибочно классифицировала как L1 / P2 / quote_sessions_rules
    llm_output = QueryRouterOutput(
        intent="qa",
        regime_hint="MOS_PORTAL",
        topic="quote_sessions_rules",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        error_codes=[],
        escalation_requested=False,
        entities=[],
        standalone_query="Ошибка при подаче заявки 0x80090006",
        sub_queries=[],
    )
    mock_client = MockLlmClient(default_response=llm_output)
    router = QueryRouter(llm_client=mock_client)

    result = await router.route("Ошибка при подаче заявки 0x80090006")

    assert "0x80090006" in result.error_codes
    # Линия повышена до L2
    assert result.support_line == "L2"
    # Приоритет повышен до P1
    assert result.priority == "P1"


@pytest.mark.asyncio
async def test_post_arbiter_topic_to_line_mapping() -> None:
    """Проверяет маппинг тем на линии поддержки: темы L2 -> L2, темы L3 -> L3."""
    # L2 тема: browser_compatibility со статусом L1 от модели
    llm_output_l2 = QueryRouterOutput(
        intent="qa",
        topic="browser_compatibility",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        error_codes=[],
        standalone_query="Не работает в браузере",
        sub_queries=[],
    )
    router_l2 = QueryRouter(
        llm_client=MockLlmClient(default_response=llm_output_l2)
    )
    res_l2 = await router_l2.route("Не открывается страница в Chromium")
    assert res_l2.support_line == "L2"

    # L3 тема: complaints_fas
    llm_output_l3 = QueryRouterOutput(
        intent="qa",
        topic="complaints_fas",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        error_codes=[],
        standalone_query="Жалоба в ФАС",
        sub_queries=[],
    )
    router_l3 = QueryRouter(
        llm_client=MockLlmClient(default_response=llm_output_l3)
    )
    res_l3 = await router_l3.route("Подаем жалобу в ФАС на протокол")
    assert res_l3.support_line == "L3"
    assert res_l3.priority == "P0"  # Триггер ФАС поднимает приоритет до P0


@pytest.mark.asyncio
async def test_post_arbiter_p0_on_caps_lock_history() -> None:
    """Проверяет принудительное выставление P0 при 3 сообщениях КАПСом подряд."""
    history = [
        {"sender": "client", "text": "ПОЧЕМУ ВСЕ СЛОМАЛОСЬ НА ПОРТАЛЕ?"},
        {"sender": "bot", "text": "Добрый день! Что у вас случилось?"},
        {"sender": "client", "text": "НЕ МОГУ ПОДПИСАТЬ КОНТРАКТ СРОЧНО!"},
        {"sender": "bot", "text": "Проверьте ЭЦП."},
    ]
    query = "ВЕРНИТЕ МНЕ ВОЗМОЖНОСТЬ ПОДПИСАНИЯ!"

    # Даже если модель вернула P2
    llm_output = QueryRouterOutput(
        intent="qa",
        topic="contract_conclusion",
        priority="P2",
        support_line="L1",
        sentiment="frustrated",
        follow_up_type="none",
        standalone_query="Проблема с подписанием контракта",
        sub_queries=[],
    )
    router = QueryRouter(llm_client=MockLlmClient(default_response=llm_output))
    res = await router.route(query, conversation_history=history)

    assert res.priority == "P0"


@pytest.mark.asyncio
async def test_timeout_triggers_enriched_fallback() -> None:
    """Проверяет, что при таймауте LLM (> 1.5 с) фолбэк сохраняет коды ошибок, линию L2 и приоритет P1."""
    # Задержка 2.0 секунды при таймауте 1.5 с
    mock_client = MockLlmClient(delay=2.0)
    router = QueryRouter(llm_client=mock_client, timeout=1.5)

    query = "Критическая ошибка 0x80090006 при отправке оферты"
    result = await router.route(query)

    assert "0x80090006" in result.error_codes
    assert result.support_line == "L2"
    assert result.priority == "P1"
    assert result.topic == "technical_errors"
    assert result.standalone_query == query.strip()
    assert result.sub_queries == []


@pytest.mark.asyncio
async def test_timeout_fallback_preserves_p0_and_l3_for_threats() -> None:
    """Проверяет, что при таймауте LLM фолбэк сохраняет P0 и L3 для угроз судом/ФАС."""
    mock_client = MockLlmClient(delay=2.0)
    router = QueryRouter(llm_client=mock_client, timeout=1.5)

    query = "Мы подаем иск в арбитражный суд и жалобу в ФАС!"
    result = await router.route(query)

    assert result.priority == "P0"
    assert result.support_line == "L3"
    assert result.topic == "complaints_fas"
    assert result.sentiment == "aggressive"


@pytest.mark.asyncio
async def test_json_validation_retry_success() -> None:
    """Проверяет повторный запрос при однократном сбое генерации/валидации JSON."""
    llm_output = QueryRouterOutput(
        intent="qa",
        topic="registration_portal",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        standalone_query="Регистрация на Портале поставщиков",
        sub_queries=[],
    )
    # 1 сбой, затем успешная отдача
    mock_client = MockLlmClient(default_response=llm_output, fail_times=1)
    router = QueryRouter(llm_client=mock_client, timeout=1.5)

    result = await router.route("Как зарегистрироваться на портале?")
    assert result.topic == "registration_portal"
    assert mock_client.call_count == 2


@pytest.mark.asyncio
async def test_sub_queries_truncation_and_chitchat_cleaning() -> None:
    """Проверяет обрезание sub_queries до 3 и сброс в [] для приветствий/chitchat."""
    # 1. chitchat с непустыми sub_queries от модели
    chitchat_output = QueryRouterOutput(
        intent="chitchat",
        topic="general_faq",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        standalone_query="Привет",
        sub_queries=["поисковый запрос 1", "поисковый запрос 2"],
    )
    router = QueryRouter(
        llm_client=MockLlmClient(default_response=chitchat_output)
    )
    res = await router.route("Здравствуйте, хорошего дня!")
    assert res.sub_queries == []

    # 2. Обрезка > 3 подзапросов
    multi_output = QueryRouterOutput(
        intent="qa",
        topic="contract_conclusion",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="none",
        standalone_query="Сложный вопрос",
        sub_queries=[
            "запрос 1",
            "запрос 2",
            "запрос 3",
            "запрос 4",
            "запрос 5",
        ],
    )
    router_multi = QueryRouter(
        llm_client=MockLlmClient(default_response=multi_output)
    )
    res_multi = await router_multi.route(
        "Как заключить контракт и оформить протокол?"
    )
    assert len(res_multi.sub_queries) == 3


@pytest.mark.asyncio
async def test_anaphora_and_context_history() -> None:
    """Проверяет передачу контекста диалога и разрешение анафоры."""
    history = [
        {"role": "user", "text": "Как подписать протокол разногласий?"},
        {
            "role": "bot",
            "text": "В личном кабинете поставщика через раздел договоров.",
        },
    ]
    llm_output = QueryRouterOutput(
        intent="qa",
        regime_hint="MOS_PORTAL",
        topic="contract_conclusion",
        priority="P2",
        support_line="L1",
        sentiment="neutral",
        follow_up_type="clarification",
        standalone_query="Сроки подписания протокола разногласий на Портале поставщиков",
        sub_queries=[],
    )
    router = QueryRouter(llm_client=MockLlmClient(default_response=llm_output))
    res = await router.route(
        "А в какие сроки это нужно сделать?", conversation_history=history
    )

    assert res.follow_up_type == "clarification"
    assert (
        res.standalone_query
        == "Сроки подписания протокола разногласий на Портале поставщиков"
    )
    assert res.topic == "contract_conclusion"
