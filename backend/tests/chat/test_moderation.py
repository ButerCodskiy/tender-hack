"""Тесты модерации ненормативной лексики и интеграции с сервисом диалогов."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.auth.models import UserModel
from src.chat.models import (
    ChatModel,
    MessageModerationStatus,
    TicketModel,
    TicketStatus,
)
from src.chat.moderation import (
    ProfanityModerator,
    ProfanityValidationError,
    get_moderator,
)
from src.chat.schemas import ClientSendMessageRequestSchema
from src.chat.service import ChatService
from src.operators.models import SupportLineModel

_ = SupportLineModel

# ==============================================================================
# 1. ТЕСТЫ НОРМАЛИЗАТОРА И ДЕОБФУСКАЦИИ
# ==============================================================================


@pytest.fixture
def moderator() -> ProfanityModerator:
    """Фикстура для получения экземпляра модератора."""
    return get_moderator()


def test_normalize_homoglyphs(moderator: ProfanityModerator) -> None:
    """Проверяет корректность замены латинских омоглифов на кириллицу."""
    # латинские 'x', 'y', 'p', 'e', 'a', 'c', 'o'
    raw = "xyp eac o"
    normalized = moderator.normalize(raw)
    assert normalized == "хур еас о"


def test_normalize_leet_speak(moderator: ProfanityModerator) -> None:
    """Проверяет декодирование числовых и символьных leet-замен."""
    assert "о" in moderator.normalize("0")
    assert "з" in moderator.normalize("3")
    assert "а" in moderator.normalize("@")
    assert "б" in moderator.normalize("6")
    assert "с" in moderator.normalize("$")
    assert "ч" in moderator.normalize("4")


def test_normalize_inner_delimiters(moderator: ProfanityModerator) -> None:
    """Проверяет удаление внутрисловных разделителей (точки, дефисы, звездочки)."""
    assert moderator.normalize("п.и.з.д.е.ц") == "пиздец"
    assert moderator.normalize("х_у_й") == "хуй"
    assert moderator.normalize("е-б-а-т-ь") == "ебать"
    assert moderator.normalize("б*л*я*д*ь") == "блядь"


def test_normalize_sparse_letters(moderator: ProfanityModerator) -> None:
    """Проверяет склеивание разреженных одиночных букв через пробелы."""
    assert moderator.normalize("п и з д е ц") == "пиздец"
    assert moderator.normalize("х у й") == "хуй"


def test_normalize_repeated_letters(moderator: ProfanityModerator) -> None:
    """Проверяет схлопывание повторяющихся подряд символов (растягивание букв)."""
    assert moderator.normalize("блллляяяять") == "блять"
    assert moderator.normalize("сууука") == "сука"
    assert moderator.normalize("хххуууййй") == "хуй"


# ==============================================================================
# 2. GOLDEN SET: ЧИСТЫЕ ФРАЗЫ И ЗАЩИТА ОТ SCUNTHORPE PROBLEM (15+ ТЕСТОВ)
# ==============================================================================

CLEAN_PHRASES: list[str] = [
    "Сколько рублей стоит страхование оборудования?",
    "Наблюдаются колебания цен в котировочных сессиях.",
    "Как употреблять данный регламент при поставке?",
    "Мудрое решение комиссии по закупке.",
    "Застрахуйте ответственность генерального поставщика.",
    "Гребной тренажер для детской спортивной школы.",
    "Закупка скипидара и антисептических средств.",
    "Парикмахерские услуги по государственному контракту.",
    "Педагогический состав и учебные пособия.",
    "Стебель растения и семена для посадки в теплицах.",
    "Бляха металлическая для форменного ремня охраны.",
    "Блин, опять забыл прикрепить файл ЭЦП!",
    "Черт побери эту техническую ошибку плагина браузера.",
    "Посудомоечная машина промышленного типа для столовой.",
    "Дубликат акта приема-передачи оборудования.",
    "Барсук и ястреб внесены в перечень охраняемых видов.",
    "Хлеб и хлебобулочные изделия для медицинских учреждений.",
    "Академическая гребля на байдарках и каноэ.",
    "Возобновление работы личного кабинета поставщика.",
    "Штатное требование регламента котировочной сессии.",
    "Предоставьте скребок для уборки снега на территории.",
    # Пограничные кейсы от пользователя
    "Требуется оскорбление чести и достоинства подтвердить решением суда.",
    "Прошу предоставить дубликат акта списания скипидара.",
    "Необходимо застраховать имущество предприятия до завершения сессии.",
    "В контракте зафиксирован сруб леса и выкорчевывание пней.",
    "Поставщик допустил грубое ребячество при исполнении обязательств.",
    "Где находится ближайший пункт гребли на байдарках для закупки инвентаря?",
    "Контракт предусматривает употребление сертифицированных удобрений.",
    "В тексте оферты выявлены существенные колебания параметров влажности.",
    "Успех у йеменских поставщиков подтвержден регламентом.",
]


@pytest.mark.parametrize("phrase", CLEAN_PHRASES)
def test_clean_phrases_not_flagged(
    moderator: ProfanityModerator, phrase: str
) -> None:
    """Гарантирует отсутствие ложных срабатываний (Precision=1.0) на легитимных словах."""
    result = moderator.check_profanity(phrase)
    assert not result.is_profane, (
        f"Ложное срабатывание на чистой фразе: '{phrase}'. "
        f"Сработало слово: '{result.matched_word}'"
    )


# ==============================================================================
# 3. GOLDEN SET: ОБСЦЕННАЯ ЛЕКСИКА И ОБФУСКАЦИЯ (15+ ТЕСТОВ)
# ==============================================================================

PROFANITY_PHRASES: list[str] = [
    # Прямой мат
    "Ну это полный пиздец, товарищи",
    "Какого хуя заявка отклонена?",
    "Не надо меня ебать вашими правилами",
    "Да вы охуели там совсем в поддержке",
    "Заебись сервис работает, ничего не скажешь",
    "Какая-то блядь удалила контракт из системы",
    "Этот поставщик — конченый мудак",
    "Оператор — тупой пидор и не отвечает",
    "Гондон штопаный, верни обеспечение контракта",
    # Leet-speak и спецсимволы
    "Ну ты и бл@дь конечно",
    "Какой-то п1здец творится на портале",
    "х0й вам а не обеспечение заявки",
    "е6ать вы долго отвечаете",
    # Межбуквенные разделители
    "п.и.з.д.е.ц полный с этой ЭЦП",
    "х_у_й вам в рыло",
    "е-б-а-т-ь как долго грузится каталог",
    "б*л*я*д*ь где мой контракт",
    "Гааавно, залууу-па Пе-нис, хе-р (Ррр) Давал-ка, ху-й Бляди-на, голо-вка(*Звук всасывания*)",
    "Шлю-ха, жо-па, член, е-блан Петух, му-дила, ру-ко-блуд, ссанина Очкобля-дун, ваги-на, су-ка, ебла-нище Вла-галище, пердун, дрочила",
    "Пидор, пизда, а, туз, малафья Го-мик, мудила, пи-лотка, манда, а?Анус, вагина, путана, дрочила Педрила, шалава, хуила, мошонка, елда Ра-унд",
    # Разреженные буквы
    "п и з д е ц приехали",
    "х у й вам",
    # Растягивание букв
    "блллляяяять как меня все достало",
    "сууука тупая закрой тикет",
    "пппиииздец зависло все",
    # Комбинированное: чистое провокационное слово + мат
    "Сколько рублей стоит эта хуйня?",
    # Пограничные обфусцированные кейсы от пользователя
    "Служба поддержки, вы просто п и з д е ц какие медленные.",
    "Пошли вы на х уй со своим порталом!",
    "Какого хy17я у меня заблокирован личный кабинет?!",
    "Вы охýели списывать обеспечение заявки!",
    "Что за п.и.$*#ец творится с плагином ЭЦП?",
    "Вы мне мозг до-е-ба-ли своими проверками!",
]


@pytest.mark.parametrize("phrase", PROFANITY_PHRASES)
def test_profane_phrases_flagged(
    moderator: ProfanityModerator, phrase: str
) -> None:
    """Гарантирует безошибочное обнаружение обсценной лексики и обфускации."""
    result = moderator.check_profanity(phrase)
    assert result.is_profane, f"Мат пропущен во фразе: '{phrase}'"
    assert result.reason == "profanity"


# ==============================================================================
# 4. ВАЛИДАЦИЯ СООБЩЕНИЙ ОПЕРАТОРА
# ==============================================================================


def test_validate_operator_message_clean(
    moderator: ProfanityModerator,
) -> None:
    """Чистое сообщение оператора проходит валидацию без исключений."""
    moderator.validate_operator_message(
        "Здравствуйте! Ваш вопрос передан в технический отдел."
    )


def test_validate_operator_message_profane(
    moderator: ProfanityModerator,
) -> None:
    """Матерное сообщение оператора выбрасывает ProfanityValidationError."""
    with pytest.raises(ProfanityValidationError) as exc_info:
        moderator.validate_operator_message("Пошел на хуй отсюда")
    assert "обнаружена недопустимая лексика" in str(exc_info.value)


# ==============================================================================
# 5. ИНТЕГРАЦИОННЫЕ ТЕСТЫ CHAT_SERVICE
# ==============================================================================


@pytest.fixture
def mock_service() -> tuple[ChatService, AsyncMock, AsyncMock, AsyncMock]:
    """Создает ChatService с мокированными зависимостями БД и Redis."""
    repo = AsyncMock()
    ticket_repo = AsyncMock()
    session = AsyncMock()
    redis_context = AsyncMock()
    rag_service = AsyncMock()
    moderator = get_moderator()

    service = ChatService(
        repo=repo,
        session=session,
        rag_service=rag_service,
        ticket_repo=ticket_repo,
        redis_context=redis_context,
        moderator=moderator,
    )
    return service, repo, ticket_repo, redis_context


@pytest.mark.asyncio
async def test_process_client_message_profane_with_sse(
    mock_service: tuple[ChatService, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """При наличии Accept: text/event-stream и мате клиента генерируется событие session_terminated."""
    service, repo, ticket_repo, redis_context = mock_service
    user_id = uuid4()
    chat_id = uuid4()
    ticket_id = uuid4()

    mock_chat = ChatModel(id=chat_id, client_id=user_id)
    mock_ticket = TicketModel(
        id=ticket_id, chat_id=chat_id, status=TicketStatus.BOT_PROCESSING
    )

    repo.get_by_client_id.return_value = mock_chat
    ticket_repo.get_active_by_chat_id.return_value = mock_ticket

    payload = ClientSendMessageRequestSchema(
        text="Какого хуя портал не работает?"
    )
    user = UserModel(
        id=user_id, email="client@zakupki.mos.ru", full_name="Тест"
    )

    events = []
    async for chunk in service.process_client_message(
        payload=payload,
        user=user,
        accept_header="text/event-stream",
    ):
        events.append(chunk)

    # 1. Проверяем формат SSE события
    assert len(events) == 1
    assert "event: session_terminated\n" in events[0]
    data_line = next(
        line for line in events[0].split("\n") if line.startswith("data: ")
    )
    data_json = json.loads(data_line[6:])
    assert data_json["reason"] == "profanity"
    assert "Ваше обращение завершено" in data_json["message"]

    # 2. Проверяем смену статуса тикета
    assert mock_ticket.status == TicketStatus.CLOSED_BY_MODERATION
    assert mock_ticket.closed_at is not None
    ticket_repo.update.assert_awaited_once_with(mock_ticket)

    # 3. Проверяем сохранение заблокированного сообщения
    repo.save_message.assert_awaited_once()
    saved_msg = repo.save_message.call_args[0][0]
    assert saved_msg.moderation_status == MessageModerationStatus.BLOCKED
    assert saved_msg.moderation_reason == "profanity"

    # 4. Проверяем инвалидацию оперативного контекста в Redis
    redis_context.clear_context.assert_awaited_once_with(ticket_id)
    # Матерное сообщение НЕ должно добавляться в Redis
    redis_context.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_process_client_message_profane_without_sse(
    mock_service: tuple[ChatService, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Без Accept text/event-stream при мате клиента выбрасывается HTTPException 400."""
    service, repo, ticket_repo, redis_context = mock_service
    user_id = uuid4()
    chat_id = uuid4()
    ticket_id = uuid4()

    mock_chat = ChatModel(id=chat_id, client_id=user_id)
    mock_ticket = TicketModel(
        id=ticket_id, chat_id=chat_id, status=TicketStatus.BOT_PROCESSING
    )

    repo.get_by_client_id.return_value = mock_chat
    ticket_repo.get_active_by_chat_id.return_value = mock_ticket

    payload = ClientSendMessageRequestSchema(text="Пошли вы на хуй")
    user = UserModel(
        id=user_id, email="client@zakupki.mos.ru", full_name="Тест"
    )

    generator = service.process_client_message(
        payload=payload,
        user=user,
        accept_header=None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await anext(generator)

    assert exc_info.value.status_code == 400
    assert "Ваше обращение завершено" in exc_info.value.detail

    # Проверяем статус тикета и сообщение
    assert mock_ticket.status == TicketStatus.CLOSED_BY_MODERATION
    redis_context.clear_context.assert_awaited_once_with(ticket_id)


@pytest.mark.asyncio
async def test_send_operator_message_profane_raises(
    mock_service: tuple[ChatService, AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Попытка оператора отправить нецензурную реплику вызывает ProfanityValidationError."""
    service, repo, _ticket_repo, _ = mock_service
    operator = UserModel(
        id=uuid4(), email="op@zakupki.mos.ru", full_name="Оператор"
    )
    ticket_id = uuid4()

    with pytest.raises(ProfanityValidationError):
        await service.send_operator_message(
            ticket_id=ticket_id,
            operator=operator,
            text="Сам ты мудак, регламент читай",
        )

    # Сообщение не должно быть сохранено
    repo.save_message.assert_not_called()
