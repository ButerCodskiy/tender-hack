# Архитектурная прожарка (Grill Me): Автоматический аудит завершенных диалогов языковой моделью (MED-01)

> **Статус:** Завершено (Утверждено)  
> **Исполнитель:** Разработчик 1  
> **Зона ответственности:** `backend/src/analytics/` (`models.py`, `schemas.py`, `service.py`, `repository.py`, `tasks.py`), связь с `TicketModel`  
> **Цель:** Фиксация строгих инженерных решений по 5 ключевым вопросам перед реализацией конвейера AI-QA.

---

## 1. Тайминг триггера: гонка между отзывом клиента и таймаутом (Feedback vs Timeout)

### Проблема:
По регламенту (`QUEUES_SPECIFICATION.md` §2.3, §4) аудит должен обязательно учитывать отзыв клиента (`ticket_feedbacks`), если он оставлен:
- **Сценарий А:** Клиент ставит оценку в первые минуты после закрытия (`POST /chat/tickets/{id}/feedback`) $\to$ немедленный запуск аудита с `trigger_reason='feedback_received'`.
- **Сценарий Б:** Клиент не оставил отзыв $\to$ через 10 минут после закрытия периодический планировщик `check_system_timeouts` (раз в 30 сек) находит тикет и ставит задачу с `trigger_reason='feedback_timeout'`.
- **Риск гонки:** Если клиент отправляет отзыв на 9-й минуте 59-й секунде ровно в момент, когда планировщик ставит задачу по таймауту, оба воркера могут параллельно вызвать дорогостоящий LLM-инференс, а также нарушить консистентность аналитических записей.

### Принятое решение:
1. **Уровень реляционной целостности:**
   - Таблица `ticket_audits` имеет ограничение `ticket_id UUID NOT NULL UNIQUE REFERENCES tickets(id) ON DELETE CASCADE`. Повторная вставка физически невозможна на уровне СУБД (PostgreSQL выбросит `IntegrityError` / `UniqueViolation`).
2. **Идемпотентность и быстрый возврат воркера (Fast-Path Check):**
   - Первым действием воркер `audit_ticket_quality` выполняет проверку:
     ```python
     existing_audit = await analytics_repo.get_audit_by_ticket_id(ticket_id)
     if existing_audit is not None:
         logger.info("Тикет %s уже прошел аудит качества, пропуск задачи", ticket_id)
         return {"ticket_id": str(ticket_id), "status": "already_audited"}
     ```
3. **Распределенная блокировка в Redis (защита от параллельного вызова LLM):**
   - Перед вызовом LLM воркер захватывает распределенный лок:
     `SET lock:audit:ticket:{ticket_id} "{worker_id}" NX EX 60`
   - Если лок не получен — параллельный воркер уже выполняет анализ данного тикета, задача немедленно завершается со статусом `locked`.
4. **Фильтрация в периодическом планировщике `check_system_timeouts`:**
   - По регламенту `QUEUES_SPECIFICATION.md` §4, запрос планировщика строго исключает тикеты, по которым отзыв уже есть или аудит уже начат/завершен:
     ```sql
     SELECT t.id
     FROM tickets t
     LEFT JOIN ticket_audits a ON a.ticket_id = t.id
     LEFT JOIN ticket_feedbacks f ON f.ticket_id = t.id
     WHERE t.status = 'resolved'
       AND t.closed_at <= :cutoff_10m
       AND a.id IS NULL
       AND f.id IS NULL
     LIMIT 100;
     ```
   - Если клиент оставил отзыв позже (после того, как тикет уже был проверен по таймауту), отзыв успешно сохраняется в `ticket_feedbacks`, а повторный аудит **не запускается**, исключая повторный расход токенов.

---

## 2. Детекция системных сбоев и дедупликация инцидентов (`system_incidents`)

### Проблема:
При массовом сбое инфраструктуры (например, отказ плагина КриптоПро 0x80090008, недоступность СМЭВ/ЕРУЗ или падение страниц авторизации) десятки или сотни клиентов получают негативный опыт.
Если воркер на каждое такое обращение будет без разбора создавать новую запись в `system_incidents`, реестр инцидентов супервизора (`GET /api/v1/analytics/incidents`) будет мгновенно заспамлен сотнями дубликатов, что парализует работу руководства.

### Принятое решение:
Разделение ответственности между защитой оператора и реестром сбоев платформы:
1. **Защита оператора (100% покрытие каждого тикета):**
   - Для **каждого** тикета со сбоем платформы в `ticket_audits` выставляется `is_system_issue = True` и `root_cause = 'system_issue'`.
   - В формуле скорректированного CSAT (`adjusted_csat` в `GET /api/v1/analytics/dashboard` и `/operators`) такие тикеты безусловно исключаются из расчета рейтинга специалиста:
     $$\text{Adjusted CSAT} = \text{AVG}(\text{score}) \quad \forall \text{ tickets WHERE } \text{is\_system\_issue} = \text{False}$$
2. **Дедупликация инцидентов со скользящим окном (2 часа):**
   - Перед созданием новой строки в `system_incidents` выполняется проверка наличия открытого инцидента того же типа:
     ```python
     existing_incident = await analytics_repo.get_open_incident_by_type(
         incident_type=llm_verdict.incident_type,
         window_hours=2,
     )
     if existing_incident is None:
         # Создаем корневой инцидент
         new_incident = SystemIncidentModel(
             id=uuid6.uuid7(),
             ticket_id=ticket_id,
             incident_type=llm_verdict.incident_type,
             description=llm_verdict.incident_description or llm_verdict.summary,
             status="open",
             created_at=now,
         )
         await analytics_repo.create_incident(new_incident)
     else:
         logger.info(
             "Инцидент типа %s уже открыт (id=%s). Тикет %s привязан к сбою без дублирования инцидента",
             llm_verdict.incident_type, existing_incident.id, ticket_id
         )
     ```
   - Это гарантирует, что в дашборде супервизора отображается один актуальный инцидент с типом `crypto_plugin` или `portal_downtime`, а операторы всех пострадавших тикетов защищены от несправедливых штрафов.

---

## 3. Формирование контекста диалога для LLM-Judge

### Проблема:
Если передавать модели-оценщику «сырой» текст реплик без разметки ролей и метаданных, LLM не сможет:
- отличить шаблонные автоответы RAG-бота от реальных сообщений человека-оператора;
- понять, почему клиент недоволен (например, если клиент ставит 1 звезду из-за отказа в закупке по 44-ФЗ, хотя оператор ответил строго по закону);
- оценить соблюдение корпоративного регламента и приветствия.

### Принятое решение:
1. **Структура входного пакета контекста (`AuditEvaluationInput`):**
   Входной контекст формируется специальным билдером `build_audit_prompt_context` и включает:
   - **Метаданные тикета:** Линия поддержки (`L1`/`L2`/`L3`), факт участия человека (`assigned_operator_id IS NOT NULL`), длительность обслуживания от открытия до закрытия.
   - **Отзыв клиента (при наличии):** Оценка (1–5 звезд) и точный текст комментария клиента (`ticket_feedbacks.comment`).
   - **Хронологическая стенограмма переписки:** Все не заблокированные реплики (`moderation_status != 'blocked'`) с четкими псевдонимами ролей.
2. **Формат стенограммы с явным разделением этапов диалога:**
   ```text
   [МЕТАДАННЫЕ ТИКЕТА]:
   Линия: L2 (Технические сбои и ЭЦП)
   Исполнитель: Оператор поддержки
   Отзыв клиента: Оценка 1/5, Комментарий: "Плагин не видит ключ Рутокен ЭЦП 3.0!"

   [СТЕНОГРАММА ДИАЛОГА]:
   [КЛИЕНТ] (14:02:10): Не могу подписать котировочную заявку, вылезает ошибка 0x80090008!
   [БОТ] (14:02:11): Здравствуйте! Попробуйте перезапустить браузер и обновить КриптоПро ЭЦП Browser plug-in...
   [КЛИЕНТ] (14:03:00): Не помогает, позовите человека срочно, у меня 20 минут до окончания подачи!
   --- [СИСТЕМА]: Эскалация на оператора линии L2 ---
   [ОПЕРАТОР] (14:04:15): Здравствуйте! Меня зовут Алексей. Уточните, установлен ли корневой сертификат Минцифры в хранилище «Доверенные корневые центры»?
   [КЛИЕНТ] (14:05:00): Да, установлен. Ошибка плагина именно на шаге подписи на Портале!
   [ОПЕРАТОР] (14:06:20): В данный момент наблюдается сбой плагина после обновления браузера Chromium-Gost. Техническая служба уже устраняет проблему.
   --- [СИСТЕМА]: Тикет закрыт со статусом resolved ---
   ```
3. **Критерии судейства в системном промпто:**
   - **Вежливость (`politeness_score` 1..5):** Наличие приветствия, корректность тона, отсутствие агрессии или бюрократического хамства.
   - **Полнота (`completeness_score` 1..5):** Дан ли исчерпывающий ответ по регламенту или перенаправлен на корректную линию.
   - **Классификация первопричины (`root_cause`):**
     * `operator_error`: оператор был груб, дал неверную инструкцию, проигнорировал прямой вопрос;
     * `system_issue`: ошибка портала, сбой ЭЦП/КриптоПро, недоступность страниц, технический сбой API;
     * `regulation_dissatisfaction`: клиент недоволен требованиями законодательства (сроки подачи по 44-ФЗ, требования к обеспечению, отклонение заявки комиссией заказчика), при этом оператор корректно разъяснил нормы;
     * `none`: диалог прошел успешно, претензий нет.

---

## 4. Отказоустойчивость и обработка фатальных ошибок (Taskiq Retry & Dead-Letter)

### Проблема:
Вызов внешней LLM подвержен сетевым задержкам, превышению rate-limit (HTTP 429) и временной недоступности (502/503/504).
По спецификации `QUEUES_SPECIFICATION.md` §5.1, очередь `analytics_queue` имеет до 3 попыток с экспоненциальной задержкой (5с, 15с, 45с) и таймаутом 120 секунд. Что делать при окончательном исчерпании попыток?

### Принятое решение:
1. **Политика повторов:**
   - Задача аннотируется параметрами Taskiq:
     ```python
     @broker.task(
         task_name="audit_ticket_quality",
         queue_name="analytics_queue",
         max_retries=3,
         retry_delay=5,
     )
     ```
2. **Обработка фатального исчерпания попыток (Dead-Letter Contract):**
   - Вместо сброса в скрытый Redis dead-letter список, фатальный сбой фиксируется прозрачно в реляционной БД:
     - Создается запись в таблице `system_incidents` с типом `incident_type = 'api_error'` и описанием сбоя сервиса аналитики (`description = f"Сбой AI-аудита диалога тикета {ticket_id}: {error_details}"`).
     - Тикет **НЕ получает фиктивных деградированных оценок** (3/3) в `ticket_audits`. Любые искусственные оценки исказили бы объективные KPI оператора.
3. **Предотвращение бесконечного цикла в планировщике `check_system_timeouts`:**
   - Планировщик при поиске тикетов для таймаут-аудита исключает тикеты, по которым уже зафиксирован инцидент сбоя `api_error`:
     ```sql
     AND NOT EXISTS (
         SELECT 1 FROM system_incidents si
         WHERE si.ticket_id = t.id AND si.incident_type = 'api_error'
     )
     ```
   - Это гарантирует, что проблемный тикет не будет спамить очередь `analytics_queue` каждые 30 секунд.

---

## 5. Модели БД и изоляция миграций

### Проблема:
- Модели `TicketAuditModel`, `TicketFeedbackModel`, `SystemIncidentModel` располагаются в `backend/src/analytics/models.py`.
- Они ссылаются внешними ключами на `tickets.id` (`TicketModel` в `backend/src/chat/models.py`).
- Опасность: циклические импорты между доменами `chat` и `analytics`, а также невидимость новых таблиц для `Base.metadata.create_all` в тестах `test_db` и миграциях Alembic.

### Принятое решение:
1. **Изоляция циклических зависимостей:**
   - Использование `typing.TYPE_CHECKING` для аннотаций типов связей.
   - В строковых декларациях SQLAlchemy указывать имена классов строками (`"TicketModel"`, `"TicketAuditModel"`).
   - В [backend/src/chat/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/chat/models.py) добавить отношения:
     ```python
     if TYPE_CHECKING:
         from src.analytics.models import (
             SystemIncidentModel,
             TicketAuditModel,
             TicketFeedbackModel,
         )

     class TicketModel(Base):
         ...
         audit: Mapped["TicketAuditModel | None"] = relationship(
             back_populates="ticket",
             uselist=False,
             cascade="all, delete-orphan",
         )
         feedback: Mapped["TicketFeedbackModel | None"] = relationship(
             back_populates="ticket",
             uselist=False,
             cascade="all, delete-orphan",
         )
         incidents: Mapped[list["SystemIncidentModel"]] = relationship(
             back_populates="ticket",
             cascade="all, delete-orphan",
         )
     ```
   - В [backend/src/analytics/models.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/analytics/models.py):
     ```python
     if TYPE_CHECKING:
         from src.chat.models import TicketModel

     class TicketAuditModel(Base):
         __tablename__ = "ticket_audits"
         ...
         ticket: Mapped["TicketModel"] = relationship(back_populates="audit")

     class TicketFeedbackModel(Base):
         __tablename__ = "ticket_feedbacks"
         ...
         ticket: Mapped["TicketModel"] = relationship(back_populates="feedback")

     class SystemIncidentModel(Base):
         __tablename__ = "system_incidents"
         ...
         ticket: Mapped["TicketModel"] = relationship(back_populates="incidents")
     ```
2. **Регистрация в Alembic и тестовом окружении:**
   - Экспортировать все модели через `src/analytics/models.py` и `src/analytics/__init__.py`.
   - Добавить импорт моделей аналитики в `backend/alembic/env.py`:
     ```python
     from src.analytics.models import (  # noqa: F401
         OperatorMetricDailyModel,
         SystemIncidentModel,
         TicketAuditModel,
         TicketFeedbackModel,
     )
     ```
   - Добавить миграцию Alembic, создающую таблицы `ticket_feedbacks`, `ticket_audits`, `system_incidents` (и `operator_metrics_daily`).
   - Благодаря этому `Base.metadata.create_all` в фикстуре `async_engine` (`tests/conftest.py`) автоматически подтягивает схемы таблиц в тестовом PostgreSQL контейнере.
