"""Тесты потокового генератора ответов, буферизации предложений и факт-чекинга."""

import uuid6

from src.rag.generator import (
    FactCheckingGuard,
    MockLlmStreamClient,
    RagStreamGenerator,
    SentenceBuffer,
)
from src.rag.prompts import format_rag_prompt
from src.rag.schemas import (
    ContextChunk,
    RagDegradedModeEventSchema,
    RagDoneEventSchema,
    RagSentenceEventSchema,
)


def _build_mock_chunk(
    idx: int = 1,
    quote: str = (
        "Участник закупки вправе сформировать и подписать протокол разногласий "
        "в личном кабинете поставщика в течение 3 рабочих дней с момента "
        "публикации проекта контракта. Размер обеспечения составляет 1% (500 000 рублей)."
    ),
    title: str = "Раздел 4. Подписание протоколов",
    section_path: str = "Регламент котировочных сессий > Раздел 4",
) -> ContextChunk:
    """Создает тестовый фрагмент нормативного документа."""
    return ContextChunk(
        chunk_id=f"chunk_test_{idx}",
        doc_id=f"DOC_TEST_{idx}",
        title=title,
        section_path=section_path,
        quote_text=quote,
        relevance_score=0.95,
    )


# ==============================================================================
# 1. Тесты буферизатора предложений (SentenceBuffer)
# ==============================================================================


def test_sentence_buffer_syllable_streaming() -> None:
    """Проверяет склейку разрозненных токенов в законченные фразы через razdel."""
    buffer = SentenceBuffer()
    tokens = [
        "По ",
        "вашему ",
        "вопросу: ",
        "протокол ",
        "формируется ",
        "в ЛК. ",
        "Под",
        "писание ",
        "в течение ",
        "3 дней [^1].",
    ]

    emitted: list[str] = []
    for t in tokens:
        emitted.extend(buffer.feed(t))
    emitted.extend(buffer.flush())

    assert len(emitted) == 2
    assert emitted[0] == "По вашему вопросу: протокол формируется в ЛК."
    assert emitted[1] == "Подписание в течение 3 дней [^1]."


def test_sentence_buffer_markdown_lists_flush() -> None:
    """Проверяет сброс буфера по двойному переносу строки для Markdown-списков."""
    buffer = SentenceBuffer()
    list_tokens = [
        "- Первый пункт регламента\n\n",
        "- Второй пункт регламента\n\n",
    ]

    emitted: list[str] = []
    for t in list_tokens:
        emitted.extend(buffer.feed(t))

    assert len(emitted) == 2
    assert emitted[0] == "- Первый пункт регламента"
    assert emitted[1] == "- Второй пункт регламента"
    assert buffer.buffer == ""


def test_sentence_buffer_flush_tail_without_period() -> None:
    """Проверяет выгрузку остатка буфера без завершающей точки при окончании потока."""
    buffer = SentenceBuffer()
    buffer.feed("Незавершенная фраза без финальной точки")
    flushed = buffer.flush()

    assert len(flushed) == 1
    assert flushed[0] == "Незавершенная фраза без финальной точки"
    assert buffer.buffer == ""


# ==============================================================================
# 2. Тесты инлайн-валидатора фактов (FactCheckingGuard)
# ==============================================================================


def test_fact_checking_guard_no_numbers() -> None:
    """Фраза без чисел и дат признается валидной."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk()
    sentence = "Протокол разногласий формируется в личном кабинете поставщика."

    assert guard.verify_sentence(
        sentence, [chunk], allowed_query_numbers=set()
    )


def test_fact_checking_guard_footnote_self_trigger_protection() -> None:
    """Проверяет защиту от самострела: индекс сноски [^1] или [1] не трактуется как число."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk(quote="Текст без каких-либо чисел вообще.")

    # Предложение не имеет чисел, кроме самой сноски [^1]
    sentence_with_caret = "Протокол формируется в личном кабинете [^1]."
    assert guard.verify_sentence(
        sentence_with_caret, [chunk], allowed_query_numbers=set()
    )

    # Предложение с толерантным синтаксисом [1]
    sentence_without_caret = "Протокол формируется в личном кабинете [1]."
    assert guard.verify_sentence(
        sentence_without_caret, [chunk], allowed_query_numbers=set()
    )


def test_fact_checking_guard_valid_numbers_and_dates() -> None:
    """Проверяет успешную верификацию чисел, сумм с пробелами, процентов и дат."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk(
        quote="Срок подачи до 15.10.2024, обеспечение 1%, сумма 500 000 руб."
    )

    sentence = (
        "Срок подачи заявок установлен до 15/10/2024, "
        "обеспечение составляет 1% на сумму 500000 руб [^1]."
    )
    assert guard.verify_sentence(
        sentence, [chunk], allowed_query_numbers=set()
    )


def test_fact_checking_guard_number_without_footnote_fails() -> None:
    """Число во фразе без сноски бракуется (verified: False), если его не было в вопросе."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk()

    sentence = "Срок подписания составляет 3 рабочих дня."
    # Нет сноски [^N], и числа 3 не было в запросе
    assert not guard.verify_sentence(
        sentence, [chunk], allowed_query_numbers=set()
    )


def test_fact_checking_guard_number_from_query_allowed_without_footnote() -> (
    None
):
    """Число из вопроса пользователя разрешено повторять без нормативной сноски."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk()

    sentence = "По вашему обращению № 12345 сообщаем следующее."
    assert guard.verify_sentence(
        sentence, [chunk], allowed_query_numbers={"12345"}
    )


def test_fact_checking_guard_invalid_footnote_index() -> None:
    """Сноска с несуществующим индексом (N > len(chunks) или N <= 0) бракуется."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk()

    sentence_out_of_bounds = "Срок составляет 3 дня [^99]."
    assert not guard.verify_sentence(
        sentence_out_of_bounds, [chunk], allowed_query_numbers=set()
    )

    sentence_zero = "Срок составляет 3 дня [^0]."
    assert not guard.verify_sentence(
        sentence_zero, [chunk], allowed_query_numbers=set()
    )


def test_fact_checking_guard_hallucinated_number_fails() -> None:
    """Галлюцинированное число, отсутствующее в процитированном чанке, бракуется."""
    guard = FactCheckingGuard()
    chunk = _build_mock_chunk(quote="Срок составляет 3 рабочих дня.")

    # Модель придумала 10 дней и 50%
    sentence = "Срок составляет 10 рабочих дней, а неустойка 50% [^1]."
    assert not guard.verify_sentence(
        sentence, [chunk], allowed_query_numbers=set()
    )


# ==============================================================================
# 3. Тесты генератора потока ответа (RagStreamGenerator)
# ==============================================================================


async def test_rag_stream_generator_full_success_flow() -> None:
    """Проверяет полный успешный поток: предложения, сноски, итоговое событие done."""
    chunk = _build_mock_chunk()
    generator = RagStreamGenerator(llm_client=MockLlmStreamClient())

    message_id = uuid6.uuid7()
    events = [
        event
        async for event in generator.generate_response_stream(
            query="Как подписать протокол разногласий?",
            chunks=[chunk],
            message_id=message_id,
        )
    ]

    assert len(events) == 3
    # Событие 1: sentence 0 (без сноски и чисел)
    assert isinstance(events[0], RagSentenceEventSchema)
    assert events[0].sentence_idx == 0
    assert events[0].verified is True
    assert "протокол разногласий" in events[0].text

    # Событие 2: sentence 1 (число 3 и сноска [^1])
    assert isinstance(events[1], RagSentenceEventSchema)
    assert events[1].sentence_idx == 1
    assert events[1].verified is True
    assert "[^1]" in events[1].text

    # Событие 3: done
    assert isinstance(events[2], RagDoneEventSchema)
    assert events[2].message_id == message_id
    assert events[2].all_verified is True
    assert events[0].text in events[2].text
    assert events[1].text in events[2].text


async def test_rag_stream_generator_unverified_sentence_sets_all_verified_false() -> (
    None
):
    """Предложение с непроверенным числом получает verified: False и сбрасывает all_verified."""
    chunk = _build_mock_chunk()
    hallucinated_text = (
        "Срок подписания протокола составляет 45 рабочих дней [^1]."
    )
    mock_client = MockLlmStreamClient(default_text=hallucinated_text)
    generator = RagStreamGenerator(llm_client=mock_client)

    events = [
        event
        async for event in generator.generate_response_stream(
            query="Какой срок?",
            chunks=[chunk],
        )
    ]

    assert len(events) == 2
    assert isinstance(events[0], RagSentenceEventSchema)
    assert events[0].verified is False  # 45 отсутствует в контексте

    assert isinstance(events[1], RagDoneEventSchema)
    assert events[1].all_verified is False


async def test_rag_stream_generator_degraded_mode_on_llm_failure() -> None:
    """При падении LLM-клиента генератор эмитит degraded_mode вместо 500 ошибки."""
    chunk = _build_mock_chunk()
    failing_client = MockLlmStreamClient(fail_times=1)
    generator = RagStreamGenerator(llm_client=failing_client)

    events = [
        event
        async for event in generator.generate_response_stream(
            query="Сложный вопрос к недоступной модели",
            chunks=[chunk],
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], RagDegradedModeEventSchema)
    assert events[0].event == "degraded_mode"
    assert len(events[0].sources) == 1
    assert events[0].sources[0].chunk_id == chunk.chunk_id


def test_format_rag_prompt_deflection_and_formatting() -> None:
    """Проверяет включение правил deflection и разметки источников в промпт."""
    chunk = _build_mock_chunk(
        idx=1,
        title="Порядок рассмотрения заявок",
        section_path="Статья 48 44-ФЗ",
        quote="Заявка рассматривается комиссией в течение 2 дней.",
    )

    sys_prompt, user_prompt = format_rag_prompt(
        query="Какой срок рассмотрения?",
        chunks=[chunk],
        conversation_history=[
            {"role": "user", "text": "Здравствуйте"},
            {"role": "assistant", "text": "Добрый день!"},
        ],
    )

    # Проверка системного промпта
    assert "DEFLECTION RULE" in sys_prompt
    assert "[^N]" in sys_prompt

    # Проверка пользовательского промпта
    assert (
        "[Источник 1 | Статья 48 44-ФЗ | Порядок рассмотрения заявок]"
        in user_prompt
    )
    assert "Заявка рассматривается комиссией в течение 2 дней." in user_prompt
    assert "Здравствуйте" in user_prompt
    assert "Какой срок рассмотрения?" in user_prompt
