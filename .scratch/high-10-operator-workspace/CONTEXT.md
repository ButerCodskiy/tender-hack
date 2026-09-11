# Контекст и аудит контрактов: HIGH-10 («Сервисный слой рабочего места оператора и управление обращениями»)

> **Статус**: Анализ и разведка контрактов (Read-Only)  
> **Дата**: 2026-09-10  
> **Спецификации**: [docs/API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) (§4), [docs/BACKEND_ARCHITECTURE.md](../../docs/BACKEND_ARCHITECTURE.md) (§2, §8), [docs/DATABASE_SPECIFICATION.md](../../docs/DATABASE_SPECIFICATION.md) (§3), [docs/QUEUES_SPECIFICATION.md](../../docs/QUEUES_SPECIFICATION.md)

---

## 1. Модели данных (SQLAlchemy)

### 1.1 Существующие модели в кодовой базе

1. **`SupportLineModel`** (`backend/src/operators/models.py`):
   - Таблица `support_lines`:
     - `id: int` (SmallInteger, PK)
     - `code: str` (VARCHAR(32), unique, например `"L1"`, `"L2"`, `"L3"`)
     - `name: str` (VARCHAR(128))
     - `description: str | None` (Text)
     - `is_active: bool` (default `True`)

2. **`OperatorProfileModel` и `OperatorShiftStatus`** (`backend/src/operators/models.py`):
   - Enum `OperatorShiftStatus`: `"active"`, `"break"`, `"offline"`.
   - Таблица `operator_profiles`:
     - `user_id: UUID` (PK, FK -> `users.id` ondelete CASCADE)
     - `line_id: int` (FK -> `support_lines.id` ondelete RESTRICT)
     - `shift_status: str` (CheckConstraint: `shift_status IN ('active', 'break', 'offline')`, default `"offline"`)
     - `max_slots: int` (CheckConstraint: `max_slots > 0 AND max_slots <= 20`, default `5`)
     - `disconnected_at: datetime | None` (TIMESTAMPTZ)
     - `last_assigned_at: datetime | None` (TIMESTAMPTZ)
     - `updated_at: datetime` (TIMESTAMPTZ)
     - Relationships: `user: Mapped["UserModel"]`, `line: Mapped["SupportLineModel"]`

3. **`TicketModel`, `TicketStatus`, `TicketPriority`** (`backend/src/chat/models.py`):
   - Таблица `tickets`:
     - `id: UUID` (PK, uuid7)
     - `chat_id: UUID` (FK -> `chats.id`)
     - `line_id: int | None` (FK -> `support_lines.id`)
     - `assigned_operator_id: UUID | None` (FK -> `users.id`)
     - `priority: str` (`"P0"`, `"P1"`, `"P2"`, default `"P2"`)
     - `status: str` (`"bot_processing"`, `"queued"`, `"assigned"`, `"in_progress"`, `"resolved"`, `"closed_by_inactivity"`, `"closed_by_moderation"`, `"canceled"`)
     - `escalation_reason: str | None`
     - `transferred_from_operator_id: UUID | None` (FK -> `users.id`)
     - `transfer_comment: str | None` (Text)
     - `created_at: datetime`, `assigned_at: datetime | None`, `opened_at: datetime | None`, `closed_at: datetime | None`, `updated_at: datetime`
     - Relationships: `chat`, `line`, `assigned_operator`, `transferred_from_operator`, `messages`

4. **`MessageModel`, `MessageSourceModel`** (`backend/src/chat/models.py`):
   - Таблица `messages`:
     - `id: UUID`, `ticket_id: UUID`, `sender_type: str` (`"client"`, `"bot"`, `"operator"`, `"system"`), `sender_id: UUID | None`, `text: str`, `moderation_status: str`, `moderation_reason: str | None`, `created_at: datetime`

5. **`UserModel`, `ClientProfileModel`** (`backend/src/auth/models.py`):
   - `UserModel`: `id`, `role_id`, `email`, `full_name`, `is_active`, `operator_profile`, `client_profile`, `role`.
   - `ClientProfileModel`: `company_name`, `inn`, `kpp`, `phone`.

### 1.2 Отсутствующие модели
- **`TicketCopilotSummaryModel`**: В `DATABASE_SPECIFICATION.md` (§3.5) специфицирована таблица `ticket_copilot_summaries` (`id`, `ticket_id`, `summary`, `suggested_line_code`, `suggested_response`, `recommended_chunk_ids`, `similar_resolved_tickets`, `created_at`), но в коде SQLAlchemy она пока не задекларирована. Для HIGH-10 при открытии карточки тикета `copilot_summary` может возвращаться как `None`, если запись отсутствует, либо модель должна быть задекларирована в `operators/models.py`.

---

## 2. Pydantic-схемы (`operators/schemas.py`)

### 2.1 Что уже объявлено (для HIGH-09)
- `TicketAssignedDataSchema` (поля: `ticket_id`, `chat_id`, `priority`, `status`, `line_code`, `client_name`, `company_name`, `last_message_preview`, `unread_messages_count`, `created_at`, `assigned_at`).
- `TicketAssignedEventSchema` (событие `ticket_assigned`).
- `AssignmentResult` (dataclass).
- `DispatchPayloadSchema` и `DispatchResult` (Taskiq payload / результат).
- Псевдоним `OperatorSidebarTicketSchema = TicketAssignedDataSchema`.

### 2.2 Что предстоит объявить для HIGH-10
1. **`OperatorShiftStatusUpdateSchema`**:
   ```python
   class OperatorShiftStatusUpdateSchema(BaseModel):
       shift_status: Literal["active", "break", "offline"] = Field(
           ...,
           description="Новый статус смены: active, break, offline",
           examples=["active"],
       )
   ```
2. **`OperatorProfileResponseSchema`**:
   ```python
   class OperatorProfileResponseSchema(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       user_id: UUID
       full_name: str
       line_id: int
       line_code: str
       shift_status: str
       max_slots: int
       active_slots_count: int
   ```
3. **`ClientInfoSchema`**:
   ```python
   class ClientInfoSchema(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       company_name: str | None = None
       inn: str | None = None
       kpp: str | None = None
       phone: str | None = None
       full_name: str | None = None
       email: str
   ```
4. **`SimilarTicketItemSchema`**:
   ```python
   class SimilarTicketItemSchema(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       ticket_id: str
       support_line: str
       user_query: str
       solution_text: str
       similarity_score: float
   ```
5. **`CopilotSummaryResponseSchema`**:
   ```python
   class CopilotSummaryResponseSchema(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       summary: str
       suggested_line_code: str | None = None
       suggested_response: str | None = None
       recommended_chunk_ids: list[str] = Field(default_factory=list)
       similar_resolved_tickets: list[SimilarTicketItemSchema] = Field(default_factory=list)
   ```
6. **`OperatorTicketWorkspaceSchema`**:
   ```python
   class OperatorTicketWorkspaceSchema(BaseModel):
       model_config = ConfigDict(from_attributes=True)
       ticket_id: UUID
       chat_id: UUID
       priority: Literal["P0", "P1", "P2"] = "P2"
       status: str
       line_code: str
       transfer_comment: str | None = None
       client: ClientInfoSchema
       copilot_summary: CopilotSummaryResponseSchema | None = None
       messages: list[MessageResponseSchema]
   ```
7. **`OperatorSendMessageRequestSchema`**:
   ```python
   class OperatorSendMessageRequestSchema(BaseModel):
       text: str = Field(..., min_length=1, max_length=4000)
   ```
8. **`TransferTicketRequestSchema`**:
   ```python
   class TransferTicketRequestSchema(BaseModel):
       target_line_code: str = Field(..., description="Код целевой линии: L1, L2, L3", examples=["L2"])
       transfer_comment: str | None = Field(None, description="Пояснение причины перевода", examples=["Требуется проверка..."])
   ```
9. **`TransferTicketResponseSchema`** и **`ResolveTicketResponseSchema`**:
   - `TransferTicketResponseSchema`: `status: str = "queued"`, `ticket_id: UUID`, `line_code: str`
   - `ResolveTicketResponseSchema`: `status: str = "resolved"`, `ticket_id: UUID`, `closed_at: datetime`

### 2.3 Расхождения между спецификацией и кодом
1. **Поле `line_code` в сайдбаре**:
   В `API_SPECIFICATION.md` (§4.2) схема `OperatorSidebarTicketSchema` не содержит поля `line_code`. Но в `operators/schemas.py` псевдоним указывает на `TicketAssignedDataSchema`, где `line_code: str | None` присутствует. Наличие `line_code` в сайдбаре полезно для фронтенда и не нарушает валидацию.
2. **Использование `MessageResponseSchema`**:
   `MessageResponseSchema` уже объявлена в `src/chat/schemas.py` и готова к импорту и переиспользованию в `OperatorTicketWorkspaceSchema`.

---

## 3. Слой репозиториев (`repository.py`)

### 3.1 Что уже есть в `OperatorRepository` (`src/operators/repository.py`)
- `get_by_user_id(user_id, load_relations=False)`: получение профиля (при `load_relations=True` загружает `user` и `line`).
- `get_active_by_line(line_id)`: список активных операторов на линии.
- `get_least_loaded_active_for_update(line_id)`: выбор оператора с блокировкой FOR UPDATE (содержит скалярный подзапрос подсчета занятых слотов).
- `create(profile)`
- `update_shift_status(user_id, shift_status)`
- `update(profile)`

### 3.2 Что нужно добавить в репозитории для HIGH-10
1. **Подсчет активных слотов оператора**:
   - Метод `OperatorRepository.count_active_slots(operator_id: UUID) -> int`:
     Подсчет тикетов с `assigned_operator_id == operator_id` в статусах `assigned` или `in_progress`.
2. **Выборка закрепленных за оператором тикетов (для сайдбара)**:
   - Метод `OperatorRepository.get_operator_tickets(operator_id: UUID) -> list[TicketModel]` (или `TicketRepository.get_assigned_tickets(...)`):
     Выборка тикетов в статусах `assigned` и `in_progress`, отсортированных по приоритету (`P0` -> `P1` -> `P2`) и `assigned_at ASC`, с жадной загрузкой `chat`, `chat.client`, `chat.client.client_profile`, `line`, `messages`.
3. **Выборка детального контекста тикета (для Workspace)**:
   - Метод `TicketRepository.get_ticket_with_workspace_details(ticket_id: UUID) -> TicketModel | None`:
     Жадная загрузка клиента, профиля клиента, линии и всех сообщений.

---

## 4. Сервисный слой (`OperatorService`)

### 4.1 Что уже реализовано (для HIGH-09)
- `dispatch_line(line_code: str, trigger_reason: str) -> DispatchResult`:
  Цикл распределения очереди линии Redis с распределенной блокировкой `lock:dispatch:line:{line_code}`, LPOP тикетов и вызовом `TicketBalancer.assign_ticket`.

### 4.2 Что предстоит реализовать с нуля для HIGH-10
1. **`get_operator_profile(user_id: UUID) -> OperatorProfileResponseSchema`**:
   - Получает профиль с `load_relations=True`.
   - Если профиль не найден -> `HTTPException(404)`.
   - Вычисляет `active_slots_count = await self.count_active_slots(user_id)`.
   - Формирует DTO.
2. **`update_shift_status(user_id: UUID, new_status: str) -> OperatorProfileResponseSchema`**:
   - Валидирует статус (`active`, `break`, `offline`).
   - Обновляет статус в БД.
   - **Триггер диспетчеризации**: Если статус изменился на `active`, инициирует фоновую задачу распределения `dispatch_line_queue.kiq(...)` (или прямой вызов `dispatch_line`) с `trigger_reason="shift_resumed"`.
   - Возвращает актуальный `OperatorProfileResponseSchema`.
3. **`get_operator_tickets(user_id: UUID) -> list[OperatorSidebarTicketSchema]`**:
   - Извлекает активные тикеты оператора.
   - Для каждого тикета формирует `OperatorSidebarTicketSchema` (вычисляет `last_message_preview` и количество непрочитанных сообщений от клиента).
4. **`open_ticket(user_id: UUID, ticket_id: UUID) -> OperatorTicketWorkspaceSchema`**:
   - Проверяет принадлежность тикета текущему оператору (`assigned_operator_id == user_id`).
   - Если тикет в статусе `assigned`:
     - Переводит статус в `in_progress`.
     - Заполняет `opened_at = datetime.now(settings.TIMEZONE)`.
     - Фиксирует изменения в БД (`session.commit()`).
     - Публикует событие `operator_joined` в Redis Pub/Sub `channel:ticket:{ticket_id}`:
       ```json
       {
         "event": "operator_joined",
         "data": {
           "ticket_id": str(ticket.id),
           "operator_id": str(user_id),
           "operator_name": operator.full_name or operator.email
         }
       }
       ```
   - Если тикет уже `in_progress` — операция идемпотентна, повторные события не шлются.
   - Формирует `OperatorTicketWorkspaceSchema` со всеми сообщениями и реквизитами клиента.
5. **`send_message(user: UserModel, ticket_id: UUID, text: str) -> MessageResponseSchema`**:
   - Проверяет валидность тикета и принадлежность оператору.
   - Проверяет текст модератором `ProfanityModerator.validate_operator_message(text)`.
   - Сохраняет `MessageModel` (`sender_type="operator"`, `sender_id=user.id`, `moderation_status="passed"`).
   - Добавляет реплику в оперативный контекст Redis `RedisChatContext.add_message(...)`.
   - Публикует событие `new_message` (или `operator_message`) в канал `channel:ticket:{ticket_id}`.
   - Возвращает `MessageResponseSchema`.
6. **`transfer_ticket(user_id: UUID, ticket_id: UUID, target_line_code: str, transfer_comment: str | None) -> dict`**:
   - Проверяет, что тикет закреплен за оператором (`assigned_operator_id == user_id`).
   - Находит целевую линию по коду `target_line_code`. Если не найдена -> `HTTPException(400)`.
   - Если линия та же самая -> ошибка перевода на ту же линию.
   - Запоминает старую линию оператора `source_line_code = ticket.line.code`.
   - Обновляет тикет:
     - `line_id = target_line.id`
     - `assigned_operator_id = None` (освобождает слот оператора!)
     - `transferred_from_operator_id = user_id`
     - `transfer_comment = transfer_comment`
     - `status = TicketStatus.QUEUED`
   - Создает системное сообщение в ленте чата (`sender_type="system"`, текст: `"Обращение переведено на линию {target_line_code}. Причина: {transfer_comment}"`).
   - Сохраняет в БД (`session.commit()`).
   - Помещает тикет в Redis-очередь целевой линии: `await line_queue.enqueue_ticket(target_line_code, ticket.id, priority=ticket.priority)`.
   - Публикует событие `ticket_transferred` в `channel:ticket:{ticket_id}`.
   - **Триггер диспетчеризации**:
     - Запускает `dispatch_line_queue` для целевой линии (`trigger_reason="ticket_escalated"`).
     - Запускает `dispatch_line_queue` для освободившейся исходной линии оператора (`trigger_reason="slot_freed"`).
7. **`resolve_ticket(user_id: UUID, ticket_id: UUID) -> dict`**:
   - Проверяет принадлежность тикета оператору (`assigned_operator_id == user_id`).
   - Переводит статус в `TicketStatus.RESOLVED`, выставляет `closed_at = datetime.now(settings.TIMEZONE)`.
   - Слот оператора освобожден.
   - Сохраняет в БД (`session.commit()`).
   - Очищает оперативный контекст Redis `RedisChatContext.clear_context(ticket_id)`.
   - Публикует событие `ticket_resolved` в `channel:ticket:{ticket_id}`.
   - Запускает фоновую диспетчеризацию на линии освободившегося оператора (`trigger_reason="slot_freed"`).

---

## 5. Транспортный слой (`src/api/v1/operators.py`)

### 5.1 Текущее состояние
В файле `backend/src/api/v1/operators.py` на данный момент всего 6 строк:
```python
from fastapi import APIRouter

router = APIRouter(prefix="/operators", tags=["operators"])
```
Эндпоинты отсутствуют (даже нет стабов).

### 5.2 Что предстоит реализовать с нуля
Все 6 эндпоинтов согласно `API_SPECIFICATION.md`:
1. `GET /api/v1/operators/me/shift` -> `OperatorProfileResponseSchema`
2. `PATCH /api/v1/operators/me/shift` (Body: `OperatorShiftStatusUpdateSchema`) -> `OperatorProfileResponseSchema`
3. `GET /api/v1/operators/tickets` -> `list[OperatorSidebarTicketSchema]`
4. `POST /api/v1/operators/tickets/{ticket_id}/open` -> `OperatorTicketWorkspaceSchema`
5. `POST /api/v1/operators/tickets/{ticket_id}/messages` (Body: `OperatorSendMessageRequestSchema`) -> `MessageResponseSchema` (`status_code=201`)
6. `POST /api/v1/operators/tickets/{ticket_id}/transfer` (Body: `TransferTicketRequestSchema`) -> `{ status: "queued", ticket_id: ..., line_code: ... }`
7. `POST /api/v1/operators/tickets/{ticket_id}/resolve` -> `{ status: "resolved", ticket_id: ..., closed_at: ... }`

*Примечание:* `GET /api/v1/operators/events` (SSE-поток) относится к задаче `HIGH-11` дорожной карты.

### 5.3 Авторизация оператора
- Используется зависимость `CurrentUserDep`.
- Требуется проверка роли оператора: пользователь должен иметь роль `operator` (или `supervisor`/`admin`). При несоответствии -> `HTTPException(403)`.
- Для удобства создается зависимость `CurrentOperatorDep = Annotated[UserModel, Depends(require_operator_role)]`.

---

## 6. Вспомогательные зависимости и внешние каналы

### 6.1 Redis Pub/Sub каналы
1. **`channel:operator:{operator_id}`**:
   - Реализовано в `RedisOperatorEvents.publish_ticket_assigned`.
   - Используется балансировщиком для уведомления о новом назначенном тикете.
2. **`channel:ticket:{ticket_id}`**:
   - Требуется в `RedisTicketEvents` (или методах `RedisOperatorEvents` / `RedisChatContext`):
     - `operator_joined`: отправка клиенту уведомления о подключении оператора.
     - `new_message`: трансляция ответа оператора в поток клиента.
     - `ticket_transferred`: уведомление клиента о переводе диалога на другую линию.
     - `ticket_resolved`: уведомление клиента о закрытии тикета и приглашение к оценке.

### 6.2 Фоновые задачи Taskiq (`dispatch_line_queue`)
- Определена в `src/operators/tasks.py`: `@broker.task(task_name="dispatch_line_queue", queue_name="dispatch_queue")`.
- Способ вызова:
  ```python
  await dispatch_line_queue.kiq(
      DispatchPayloadSchema(
          line_code=line_code,
          trigger_reason=trigger_reason,
      )
  )
  ```
- Места вызова в `OperatorService`:
  - `update_shift_status` -> при смене на `active` (`trigger_reason="shift_resumed"`).
  - `transfer_ticket` -> для целевой линии (`trigger_reason="ticket_escalated"`) и для линии освободившегося оператора (`trigger_reason="slot_freed"`).
  - `resolve_ticket` -> для линии освободившегося оператора (`trigger_reason="slot_freed"`).

### 6.3 Сохранение сообщений оператора в таблицу `messages`
- В `ChatService.send_operator_message` уже реализована валидация мата через `ProfanityModerator.validate_operator_message(text)`, создание `MessageModel` с `sender_type="operator"`, сохранение через `ChatRepository.save_message(...)` и кэширование в `RedisChatContext`.
- В сервисе оператора `OperatorService.send_message` целесообразно либо делегировать вызов в `ChatService.send_operator_message`, либо напрямую использовать `ChatRepository` и `ProfanityModerator`, дополняя публикацией события в Redis Pub/Sub `channel:ticket:{ticket_id}`.
