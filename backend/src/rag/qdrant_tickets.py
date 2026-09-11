"""Интеграция коллекции прецедентов resolved_tickets в Qdrant."""

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.models import Distance, VectorParams

from src.kb.qdrant import EmbeddingStub
from src.operators.schemas import SimilarTicketItemSchema

logger = logging.getLogger(__name__)

RESOLVED_TICKETS_COLLECTION = "resolved_tickets"
QDRANT_TICKETS_NAMESPACE = uuid.UUID("d3e4f5a6-b7c8-4d9e-0f1a-2b3c4d5e6f7a")


def ticket_id_to_qdrant_uuid(ticket_key: str) -> uuid.UUID:
    """Генерирует детерминированный UUIDv5 для точки прецедента в Qdrant."""
    return uuid.uuid5(QDRANT_TICKETS_NAMESPACE, ticket_key)


# Корпус из 32 эталонных исторических решений (включая сбои ЭЦП, КриптоПро и регламенты)
SEED_RESOLVED_TICKETS: list[dict[str, Any]] = [
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000001",
        "support_line": "L2",
        "user_query": "Ошибка 0x80090016 при подписании протокола разногласий на Портале поставщиков",
        "solution_text": (
            "Ошибка 0x80090016 указывает на невозможность доступа к закрытому ключу контейнера. "
            "Решение: 1) Переустановите КриптоПро ЭЦП Browser plug-in до актуальной сборки; "
            "2) Добавьте адрес https://zakupki.mos.ru в список доверенных узлов плагина; "
            "3) Проверьте видимость сертификата на носителе Рутокен через панель КриптоПро CSP."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000002",
        "support_line": "L2",
        "user_query": "Плагин КриптоПро cadesplugin не обнаружен в Яндекс.Браузере",
        "solution_text": (
            "Для работы в Яндекс.Браузере необходимо включить расширение 'КриптоПро ЭЦП' в браузере "
            "и разрешить доступ к локальным файлам и URL. После включения перезапустите браузер."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000003",
        "support_line": "L2",
        "user_query": "Ошибка 0x80090008 Указан неправильный алгоритм при формировании подписи",
        "solution_text": (
            "Данная ошибка возникает при попытке подписания алгоритмом ГОСТ Р 34.10-2001. "
            "Решение: обновите КриптоПро CSP до версии 5.0 R2/R3 с поддержкой ГОСТ Р 34.10-2012 "
            "и перевыпустите сертификат в аккредитованном УЦ."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000004",
        "support_line": "L2",
        "user_query": "Не подписывается оферта: ошибка 'Цепочка сертификатов не проверена'",
        "solution_text": (
            "Установите актуальные корневые сертификаты Минцифры России и головного УЦ "
            "в хранилище 'Доверенные корневые центры сертификации' локального компьютера."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000005",
        "support_line": "L2",
        "user_query": "Ошибка 0x80070005 Отказано в доступе при инициализации модуля КриптоПро",
        "solution_text": (
            "Запустите браузер от имени администратора либо проверьте права доступа учетной "
            "записи Windows к ветке реестра HKEY_LOCAL_MACHINE\\SOFTWARE\\Crypto Pro."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000006",
        "support_line": "L1",
        "user_query": "В какой срок поставщик обязан подписать протокол разногласий?",
        "solution_text": (
            "Согласно разделу 4 Регламента ведения котировочных сессий Портала поставщиков, "
            "поставщик вправе сформировать и направить протокол разногласий в течение 3 рабочих дней "
            "с момента размещения проекта контракта заказчиком."
        ),
        "category": "protocol_disagreements",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000007",
        "support_line": "L1",
        "user_query": "Сколько раз можно направлять протокол разногласий по 44-ФЗ?",
        "solution_text": (
            "По части 3 статьи 51 Федерального закона № 44-ФЗ поставщик может направить протокол "
            "разногласий не более одного раза в отношении одного проекта контракта."
        ),
        "category": "protocol_disagreements",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000008",
        "support_line": "L1",
        "user_query": "Где в личном кабинете прикрепить протокол разногласий?",
        "solution_text": (
            "Перейдите в раздел 'Мои контракты', выберите требуемую котировочную сессию в статусе "
            "'На подписании у поставщика', нажмите кнопку 'Создать протокол разногласий', "
            "заполните обоснование и подпишите ЭЦП."
        ),
        "category": "protocol_disagreements",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000009",
        "support_line": "L1",
        "user_query": "Что делать, если заказчик отклонил протокол разногласий?",
        "solution_text": (
            "Если заказчик отклонил протокол разногласий и повторно разместил проект контракта без правок, "
            "поставщик обязан подписать контракт в течение 1 рабочего дня во избежание признания уклонившимся."
        ),
        "category": "protocol_disagreements",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000010",
        "support_line": "L1",
        "user_query": "Как отозвать ценовое предложение в котировочной сессии?",
        "solution_text": (
            "Отзыв ценового предложения допускается до момента окончания приема предложений. "
            "В карточке сессии нажмите 'Отозвать предложение' и подтвердите действие ЭЦП."
        ),
        "category": "quotation_session",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000011",
        "support_line": "L1",
        "user_query": "Какой шаг снижения цены установлен для котировочных сессий?",
        "solution_text": (
            "Шаг снижения цены на Портале поставщиков Москвы составляет от 0.5% до 5% от начальной "
            "(максимальной) цены контракта."
        ),
        "category": "quotation_session",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000012",
        "support_line": "L1",
        "user_query": "Продлевается ли котировочная сессия при подаче ставки в последние минуты?",
        "solution_text": (
            "Да, при подаче ставки менее чем за 5 минут до окончания сессии, время автоматически "
            "продлевается на 5 минут (правило антиснайпинга), но не более чем на 30 минут суммарно."
        ),
        "category": "quotation_session",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000013",
        "support_line": "L3",
        "user_query": "Заблокирован личный кабинет поставщика после смены генерального директора",
        "solution_text": (
            "При смене генерального директора требуется обновление данных в ЕРУЗ (ЕИС). "
            "После автоматической синхронизации ЕРУЗ с Порталом поставщиков (до 24 часов) блокировка "
            "снимается. Для ускоренной ручной верификации направьте выписку из ЕГРЮЛ старшему администратору."
        ),
        "category": "account_blocking",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000014",
        "support_line": "L3",
        "user_query": "Угроза жалобы в ФАС от заказчика за задержку подписания контракта",
        "solution_text": (
            "Срочно зафиксируйте технический инцидент: сделайте скриншоты экрана с системным временем "
            "и текстом ошибки, сформируйте выгрузку логов браузера. Направьте официальное обращение "
            "в службу техподдержки для составления акта о техническом сбое на Портале."
        ),
        "category": "complaints_fas",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000015",
        "support_line": "L3",
        "user_query": "Заказчик в одностороннем порядке расторгает контракт, что делать?",
        "solution_text": (
            "По ч. 12 ст. 95 44-ФЗ решение заказчика вступает в силу через 10 дней с даты надлежащего "
            "уведомления. Если в течение 10 дней устранить нарушение условий контракта, заказчик обязан "
            "отменить решение об одностороннем отказе."
        ),
        "category": "contract_disputes",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000016",
        "support_line": "L1",
        "user_query": "Как опубликовать оферту в Каталоге СТЕ (стандартных товарных единиц)?",
        "solution_text": (
            "В личном кабинете перейдите в раздел 'Оферты' -> 'Добавить оферту', выберите позицию "
            "из справочника СТЕ, укажите цену, условия поставки, прикрепите сертификаты и подпишите ЭЦП."
        ),
        "category": "catalog_ste",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000017",
        "support_line": "L1",
        "user_query": "Сколько длится модерация новой позиции СТЕ?",
        "solution_text": (
            "Срок рассмотрения заявки на создание новой позиции СТЕ службой ведения каталога "
            "составляет до 3 рабочих дней."
        ),
        "category": "catalog_ste",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000018",
        "support_line": "L2",
        "user_query": "Ошибка при загрузке спецификации Excel: Неверный формат шаблона",
        "solution_text": (
            "Скачайте актуальный эталонный шаблон спецификации из карточки сессии. Не изменяйте "
            "названия колонок и порядок листов. Сохраняйте файл в формате .xlsx без макросов."
        ),
        "category": "technical_errors",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000019",
        "support_line": "L2",
        "user_query": "Кнопка 'Подписать и отправить' неактивна в карточке контракта",
        "solution_text": (
            "Кнопка блокируется, если: 1) Не заполнены обязательные поля реквизитов счета; "
            "2) Не прикреплен файл обеспечения исполнения контракта; 3) Истек срок регламента."
        ),
        "category": "technical_errors",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000020",
        "support_line": "L1",
        "user_query": "В какой срок возвращается обеспечение заявки по 44-ФЗ?",
        "solution_text": (
            "Денежные средства, заблокированные на специальном счете в качестве обеспечения заявки, "
            "разблокируются банком в течение 1 рабочего дня с момента публикации итогового протокола."
        ),
        "category": "payment_guarantee",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000021",
        "support_line": "L2",
        "user_query": "Не отображается сертификат ЭЦП в списке доступных для выбора",
        "solution_text": (
            "Проверьте, что личный сертификат привязан к закрытому ключу в КриптоПро CSP: "
            "Сервис -> Просмотреть сертификаты в контейнере -> Установить."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000022",
        "support_line": "L1",
        "user_query": "Как поставщику изменить банковские реквизиты в действующем контракте?",
        "solution_text": (
            "Изменение банковских реквизитов оформляется дополнительным соглашением к контракту. "
            "Направьте заказчику уведомление с новыми реквизитами через функционал сообщений по контракту."
        ),
        "category": "contract_disputes",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000023",
        "support_line": "L2",
        "user_query": "Сбой 0x800B0109 Сертификат корневого центра не входит в число доверенных",
        "solution_text": (
            "Установите корневой сертификат Головного удостоверяющего центра Минцифры "
            "в локальное хранилище доверенных корневых центров."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000024",
        "support_line": "L1",
        "user_query": "Правила проведения закупки малого объема до 600 тысяч рублей",
        "solution_text": (
            "Закупки малого объема по п. 4 и 5 ч. 1 ст. 93 44-ФЗ проводятся через котировочные сессии "
            "длительностью 2, 4 или 24 часа. Победителем признается участник с наименьшей ценой."
        ),
        "category": "quotation_session",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000025",
        "support_line": "L3",
        "user_query": "Необоснованное списание денежных средств со специального счета",
        "solution_text": (
            "Списание платы за победу осуществляется оператором площадки в размере 1% от НМЦК, "
            "но не более 2000 рублей для субъектов МСП. При расхождениях запросите детализацию у финансового отдела."
        ),
        "category": "payment_delays",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000026",
        "support_line": "L2",
        "user_query": "Сообщение: Ошибка проверки подписи: подпись неверна (0x80090006)",
        "solution_text": (
            "Файл документа был изменен после подписания либо поврежден при передаче. "
            "Сформируйте документ заново и выполните повторное подписание."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000027",
        "support_line": "L1",
        "user_query": "Как зарегистрировать филиал организации на Портале поставщиков?",
        "solution_text": (
            "Регистрация филиала осуществляется из головного аккаунта: раздел 'Профиль компании' -> "
            "'Обособленные подразделения' -> 'Добавить филиал' с указанием КПП."
        ),
        "category": "catalog_ste",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000028",
        "support_line": "L2",
        "user_query": "Ошибка таймаута соединения 504 Gateway Timeout при выгрузке отчета",
        "solution_text": (
            "Сформируйте отчет за меньший диапазон дат (не более 1 месяца) или повторите выгрузку "
            "в период минимальной нагрузки на портал (до 09:00 или после 18:00)."
        ),
        "category": "technical_errors",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000029",
        "support_line": "L1",
        "user_query": "Можно ли изменить существенные условия контракта при подписании?",
        "solution_text": (
            "Нет, изменение существенных условий контракта при подписании запрещено ст. 95 44-ФЗ. "
            "Разногласия допускаются только по техническим ошибкам и несоответствиям заявке."
        ),
        "category": "protocol_disagreements",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000030",
        "support_line": "L2",
        "user_query": "Плагин КриптоПро выдает ошибку 'Не удается построить цепочку сертификатов для доверенного корневого центра'",
        "solution_text": (
            "Скачайте и установите корневой сертификат УЦ, выдавшего вашу подпись, "
            "через утилиту 'Сертификаты' в доверенные корневые центры сертификации."
        ),
        "category": "digital_signature_plugin",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000031",
        "support_line": "L3",
        "user_query": "Включение в РНП: заказчик направил сведения в УФАС",
        "solution_text": (
            "Подготовьте письменные возражения в УФАС с подтверждением добросовестности: "
            "выписки логов Портала поставщиков, скриншоты технических сбоев, переписку с техподдержкой."
        ),
        "category": "complaints_fas",
    },
    {
        "ticket_id": "018e0000-0000-7000-8000-000000000032",
        "support_line": "L1",
        "user_query": "Как подписать проект контракта усиленной подписью руководителя?",
        "solution_text": (
            "Откройте карточку проекта контракта, нажмите 'Подписать контракт', выберите действующий "
            "сертификат руководителя и подтвердите операцию вводом пин-кода токена."
        ),
        "category": "protocol_disagreements",
    },
]


async def ensure_resolved_tickets_collection(
    client: AsyncQdrantClient,
    embedding_dim: int = 1024,
) -> None:
    """Инициализирует векторную коллекцию resolved_tickets с косинусной метрикой и сидированием."""
    try:
        collections = await client.get_collections()
        existing_names = {c.name for c in collections.collections}

        if RESOLVED_TICKETS_COLLECTION not in existing_names:
            logger.info(
                "Создание коллекции %s в Qdrant...",
                RESOLVED_TICKETS_COLLECTION,
            )
            await client.create_collection(
                collection_name=RESOLVED_TICKETS_COLLECTION,
                vectors_config=VectorParams(
                    size=embedding_dim, distance=Distance.COSINE
                ),
            )
            await seed_resolved_tickets(client, embedding_dim=embedding_dim)
    except Exception as exc:
        logger.warning(
            "Предупреждение при проверке/инициализации коллекции %s: %s",
            RESOLVED_TICKETS_COLLECTION,
            exc,
        )


async def seed_resolved_tickets(
    client: AsyncQdrantClient,
    embedding_dim: int = 1024,
) -> int:
    """Загружает пакет эталонных прецедентов закрытых обращений в Qdrant."""
    stub = EmbeddingStub(dim=embedding_dim)
    points: list[qdrant_models.PointStruct] = []

    for item in SEED_RESOLVED_TICKETS:
        ticket_id = item["ticket_id"]
        point_id = str(ticket_id_to_qdrant_uuid(ticket_id))
        search_text = f"{item['user_query']} {item['solution_text']}"
        vector = stub.generate_vectors(search_text)["dense"]

        point = qdrant_models.PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "ticket_id": ticket_id,
                "support_line": item["support_line"],
                "user_query": item["user_query"],
                "solution_text": item["solution_text"],
                "category": item.get("category", "general"),
            },
        )
        points.append(point)

    if points:
        await client.upsert(
            collection_name=RESOLVED_TICKETS_COLLECTION,
            points=points,
        )
        logger.info(
            "Успешно засеяно %d прецедентов в коллекцию %s",
            len(points),
            RESOLVED_TICKETS_COLLECTION,
        )

    return len(points)


async def search_similar_resolved_tickets(
    client: AsyncQdrantClient | None,
    query_text: str,
    limit: int = 3,
    embedding_dim: int = 1024,
) -> list[SimilarTicketItemSchema]:
    """Выполняет векторный семантический поиск топ-N похожих закрытых обращений в Qdrant.

    При недоступности базы или ошибке поиска возвращает пустой список (Graceful Degradation).
    """
    if client is None or not query_text.strip():
        return []

    try:
        # 1. Гарантируем наличие коллекции перед поиском
        await ensure_resolved_tickets_collection(
            client, embedding_dim=embedding_dim
        )

        # 2. Векторизация поискового запроса через EmbeddingStub
        stub = EmbeddingStub(dim=embedding_dim)
        query_vector = stub.generate_vectors(query_text)["dense"]

        # 3. Семантический поиск по косинусному расстоянию (совместимость с qdrant-client >= 1.10 и legacy)
        if hasattr(client, "query_points"):
            response = await client.query_points(
                collection_name=RESOLVED_TICKETS_COLLECTION,
                query=query_vector,
                limit=limit,
            )
            search_results = getattr(response, "points", response)
        elif hasattr(client, "search"):
            search_results = await client.search(
                collection_name=RESOLVED_TICKETS_COLLECTION,
                query_vector=query_vector,
                limit=limit,
            )
        else:
            search_results = []

        similar_items: list[SimilarTicketItemSchema] = []
        for scored_point in search_results:
            payload = scored_point.payload or {}
            score = round(float(scored_point.score), 4)

            item = SimilarTicketItemSchema(
                ticket_id=str(payload.get("ticket_id", scored_point.id)),
                support_line=str(payload.get("support_line", "L1")),
                user_query=str(payload.get("user_query", "")),
                solution_text=str(payload.get("solution_text", "")),
                similarity_score=score,
            )
            similar_items.append(item)

        return similar_items
    except Exception as exc:
        logger.warning(
            "Ошибка при поиске похожих прецедентов в Qdrant (активирован fallback): %s",
            exc,
        )
        return []
