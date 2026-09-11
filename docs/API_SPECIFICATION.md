# Спецификация веб-слоя API v1 и сервисной логики

Документ определяет спецификацию публичного программного интерфейса версии 1 (`src/api/v1/`), схемы валидации данных Pydantic, контракты потоковой передачи событий и алгоритмы сервисной логики.

---

## 1. Архитектурные стандарты и общие соглашения

### 1.1. Базовые соглашения REST
* Все маршруты первой версии располагаются с префиксом `/api/v1`.
* Имена ресурсов в путях указываются во множественном числе в нижнем регистре: `/messages`, `/tickets`, `/documents`.
* Взаимодействие осуществляется в формате JSON (`Content-Type: application/json; charset=utf-8`), за исключением потоковых событий (`text/event-stream`) и загрузки файлов (`multipart/form-data`).
* При успешных операциях возвращаются стандартные коды состояния:
  * `200 OK` — успешное получение, обновление или выполнение действия;
  * `201 Created` — успешное создание ресурса (в заголовке ответа может передаваться ссылка на созданный ресурс);
  * `202 Accepted` — запрос принят в очередь на долгую фоновую обработку;
  * `204 No Content` — успешное удаление ресурса (тело ответа отсутствует).

### 1.2. Стандарты безопасности и аутентификации
* Аутентификация выполняется по схеме Bearer с использованием токенов доступа JWT в заголовке `Authorization: Bearer <access_token>`.
* Время жизни токена доступа составляет 15 минут, токена обновления — 7 дней.
* Привилегии разграничиваются на уровне внедрения зависимостей по коду роли пользователя (`client`, `operator`, `supervisor`, `admin`).

### 1.3. Единый формат ошибок
Все ошибочные ответы возвращаются в унифицированном формате:

```python
from pydantic import BaseModel, ConfigDict, Field

class ErrorDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str = Field(..., description="Машиночитаемый код ошибки", example="ticket_not_found")
    message: str = Field(..., description="Понятное описание причины ошибки на русском языке", example="Обращение не найдено")

class ErrorResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detail: ErrorDetailSchema = Field(..., description="Сведения об ошибке")
```

Стандартные коды ошибок:
* `400 Bad Request` — логическое нарушение бизнес-правил;
* `401 Unauthorized` — отсутствует или просрочен токен доступа;
* `403 Forbidden` — недостаточный уровень роли для выполнения операции;
* `404 Not Found` — запрашиваемый ресурс не существует или принадлежит другому владельцу;
* `409 Conflict` — конфликт состояний (повторная попытка перевода тикета, занятый слот);
* `422 Unprocessable Entity` — ошибка валидации формата входных данных FastAPI/Pydantic;
* `500 Internal Server Error` — необработанный сбой сервера.

### 1.4. Общие заголовки запросов
* `Authorization: Bearer <access_token>` — обязателен для всех закрытых маршрутов;
* `Content-Type: application/json` — обязателен для запросов с телом;
* `X-Request-Id: <UUID>` — опциональный идентификатор сквозной трассировки запроса.

---

## 2. Аутентификация и учетные записи (`src/api/v1/auth.py`)

### 2.1 `POST /api/v1/auth/register`

**Описание:** Регистрация нового клиента (поставщика). Создает учетную запись пользователя с ролью `client`, сохраняет реквизиты профиля организации (если они переданы) и формирует постоянный чат клиента. Все поля, кроме почты и пароля, являются опциональными.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Content-Type` | string | Да | `application/json` |

**Схемы Pydantic:**

```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Literal

class ClientRegisterRequestSchema(BaseModel):
    email: EmailStr = Field(..., description="Электронная почта для входа", example="supplier@example.com")
    password: str = Field(..., min_length=8, max_length=128, description="Пароль пользователя", example="SecretPass123")
    full_name: str | None = Field(None, max_length=255, description="ФИО контактного лица (опционально)", example="Иванов Иван Иванович")
    company_name: str | None = Field(None, max_length=255, description="Наименование организации или ИП (опционально)", example="ООО «Поставка-Плюс»")
    inn: str | None = Field(None, min_length=10, max_length=12, description="ИНН организации (10) или ИП (12) (опционально)", example="7701234567")
    kpp: str | None = Field(None, min_length=9, max_length=9, description="КПП для юридических лиц (опционально)", example="770101001")
    phone: str | None = Field(None, max_length=32, description="Контактный номер телефона (опционально)", example="+79991234567")

class UserProfileResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор пользователя")
    role_code: str = Field(..., description="Код роли пользователя", example="client")
    email: EmailStr = Field(..., description="Электронная почта")
    full_name: str | None = Field(None, description="ФИО пользователя (при наличии)")
    company_name: str | None = Field(None, description="Наименование организации (при наличии)")
    inn: str | None = Field(None, description="ИНН организации (при наличии)")
    created_at: datetime = Field(..., description="Время регистрации")

class AuthTokenResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="Токен доступа JWT")
    refresh_token: str = Field(..., description="Токен обновления")
    token_type: str = Field("bearer", description="Тип токена")
    expires_in: int = Field(900, description="Время действия токена доступа в секундах")
    user: UserProfileResponseSchema = Field(..., description="Профиль зарегистрированного пользователя")
```

**Параметры ответа (`201 Created`):** Возвращает объект `AuthTokenResponseSchema`.

**Примеры:**

Запрос с заполнением всех реквизитов:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "supplier@example.com",
    "password": "SecretPassword123",
    "full_name": "Иванов Иван Иванович",
    "company_name": "ООО «Поставка-Плюс»",
    "inn": "7701234567",
    "kpp": "770101001",
    "phone": "+79991234567"
  }'
```

Запрос с минимальным набором данных (только почта и пароль):
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "supplier@example.com",
    "password": "SecretPassword123"
  }'
```

✅ Ответ `201 Created` (минимальная регистрация):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "018e5f1b-3a21-729d-9e5c-29b1f0c23a01",
    "role_code": "client",
    "email": "supplier@example.com",
    "full_name": null,
    "company_name": null,
    "inn": null,
    "created_at": "2026-09-06T21:00:00Z"
  }
}
```

❌ Ответ `409 Conflict` (почта уже занята):
```json
{
  "detail": {
    "code": "email_already_exists",
    "message": "Пользователь с таким адресом электронной почты уже зарегистрирован"
  }
}
```

**Пограничные случаи:**
* Все реквизиты профиля (`full_name`, `company_name`, `inn`, `kpp`, `phone`) являются опциональными. Регистрация разрешена только по `email` и `password`.
* Если ИНН передан, он валидируется на длину (строго 10 или 12 цифр). Некорректный ИНН → `422 Unprocessable Entity`.
* Повторная регистрация с тем же адресом почты → `409 Conflict`.
* Пароль короче 8 символов → `422 Unprocessable Entity`.

---

### 2.2 `POST /api/v1/auth/login`

**Описание:** Аутентификация пользователя по адресу электронной почты и паролю. Доступно для всех ролей.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Content-Type` | string | Да | `application/json` |

**Схемы Pydantic:**

```python
class LoginRequestSchema(BaseModel):
    email: EmailStr = Field(..., description="Электронная почта", example="operator1@example.com")
    password: str = Field(..., description="Пароль", example="OperatorPass123")
```

**Параметры ответа (`200 OK`):** Возвращает объект `AuthTokenResponseSchema`.

**Примеры:**

Запрос:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "operator1@example.com", "password": "OperatorPass123"}'
```

✅ Ответ `200 OK`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "018e5f1b-3a21-729d-9e5c-29b1f0c23a02",
    "role_code": "operator",
    "email": "operator1@example.com",
    "full_name": "Петров Петр Сергеевич",
    "company_name": null,
    "inn": null,
    "created_at": "2026-09-06T20:00:00Z"
  }
}
```

❌ Ответ `401 Unauthorized` (неверные учетные данные):
```json
{
  "detail": {
    "code": "invalid_credentials",
    "message": "Неверный адрес электронной почты или пароль"
  }
}
```

**Пограничные случаи:**
* Учетная запись деактивирована (`is_active = false`) → `403 Forbidden` с кодом `account_disabled`.
* Неверный пароль или несуществующая почта → `401 Unauthorized` (без уточнения, что именно неверно).

---

### 2.3 `POST /api/v1/auth/refresh`

**Описание:** Выпуск новой пары токенов по действующему токену обновления.

**Схемы Pydantic:**

```python
class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str = Field(..., description="Действующий токен обновления")
```

**Параметры ответа (`200 OK`):** Возвращает объект `AuthTokenResponseSchema`.

**Пограничные случаи:**
* Токен обновления поврежден или истек → `401 Unauthorized` с кодом `token_expired`.
* Пользователь был деактивирован после выдачи токена → `403 Forbidden`.

---

### 2.4 `GET /api/v1/auth/me`

**Описание:** Получение данных текущего аутентифицированного пользователя.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Authorization` | string | Да | `Bearer <access_token>` |

**Параметры ответа (`200 OK`):** Возвращает объект `UserProfileResponseSchema`.

---

## 3. Клиентский чат и обращения (`src/api/v1/chat.py`)

### 3.1 `GET /api/v1/chat`

**Описание:** Получение полного текущего состояния переписки клиента. Возвращает информацию об активном обращении (если есть), последние сообщения единой ленты и перечень разрешенных действий.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Authorization` | string | Да | `Bearer <access_token>` клиента |

**Схемы Pydantic:**

```python
class MessageSourceResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str = Field(..., description="Идентификатор фрагмента базы знаний")
    doc_id: str = Field(..., description="Идентификатор документа регламента")
    quote_text: str | None = Field(None, description="Цитируемый фрагмент")

class MessageResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор сообщения")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    sender_type: str = Field(..., description="Тип отправителя: client, bot, operator, system", example="bot")
    sender_id: UUID | None = Field(None, description="Идентификатор автора (при наличии)")
    text: str = Field(..., description="Текст сообщения")
    moderation_status: str = Field("passed", description="Статус модерации: passed, flagged, blocked")
    sources: list[MessageSourceResponseSchema] = Field(default_factory=list, description="Источники ответа базы знаний")
    created_at: datetime = Field(..., description="Время фиксации")

class ActiveTicketSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор активного обращения")
    priority: Literal['P0', 'P1', 'P2'] = Field('P2', description="Приоритет обращения: P0, P1, P2", example="P2")
    status: str = Field(..., description="Статус обращения", example="in_progress")
    line_code: str | None = Field(None, description="Код закрепленной линии: L1, L2, L3", example="L1")
    assigned_operator_name: str | None = Field(None, description="Имя подключенного специалиста", example="Анна Смирнова")
    created_at: datetime = Field(..., description="Время открытия обращения")

class ChatStateResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chat_id: UUID = Field(..., description="Идентификатор постоянного чата клиента")
    active_ticket: ActiveTicketSummarySchema | None = Field(None, description="Активное обращение или null")
    messages: list[MessageResponseSchema] = Field(..., description="Сообщения ленты (до 50 последних)")
    can_escalate: bool = Field(..., description="Доступна ли кнопка вызова оператора")
    can_cancel: bool = Field(..., description="Доступна ли отмена обращения")
    can_feedback: bool = Field(..., description="Требуется ли оценка последнего закрытого обращения")
    feedback_ticket_id: UUID | None = Field(None, description="Идентификатор тикета, ожидающего оценки")
```

**Параметры ответа (`200 OK`):** Возвращает объект `ChatStateResponseSchema`.

**Примеры:**

Запрос:
```bash
curl http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer <access_token>"
```

✅ Ответ `200 OK`:
```json
{
  "chat_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b10",
  "active_ticket": {
    "id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11",
    "priority": "P2",
    "status": "in_progress",
    "line_code": "L1",
    "assigned_operator_name": "Анна Смирнова",
    "created_at": "2026-09-06T20:50:00Z"
  },
  "messages": [
    {
      "id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b12",
      "ticket_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11",
      "sender_type": "client",
      "sender_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23a01",
      "text": "Как подписать протокол разногласий?",
      "moderation_status": "passed",
      "sources": [],
      "created_at": "2026-09-06T20:50:05Z"
    }
  ],
  "can_escalate": false,
  "can_cancel": false,
  "can_feedback": false,
  "feedback_ticket_id": null
}
```

---

### 3.2 `POST /api/v1/chat/messages`

**Описание:** Единая точка отправки сообщений клиентом.
* Если обращение находится в ведении вопросно-ответной системы (`bot_processing`) или активный тикет отсутствует — создает тикет (при необходимости) и возвращает потоковый ответ `text/event-stream` с генерацией ответа модели.
* Если обращение находится в очереди (`queued`), назначено (`assigned`) или ведется оператором (`in_progress`) — сохраняет сообщение, выталкивает его оператору через оперативную шину и немедленно возвращает код `201 Created` с объектом сообщения.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Authorization` | string | Да | `Bearer <access_token>` клиента |
| `Content-Type` | string | Да | `application/json` |

**Схемы Pydantic:**

```python
class ClientSendMessageRequestSchema(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="Текст сообщения клиента", example="Как продлить срок подачи заявки по 44-ФЗ?")
```

**Формат потокового ответа (SSE при обработке базой знаний):**
Потоковая передача ответа ведется через Server-Sent Events с буферизацией предложений (Sentence-Buffered Streaming с использованием `razdel`): сервер накапливает токены генератора до границы фразы, валидирует слоты за $\le 1$ мс и отдает клиенту законченные предложения с инлайн-флагом верификации:
* `event: status` — передача промежуточного статуса размышления модели (`classifying`, `searching`, `reranking`).
* `event: sources` — список найденных статей нормативных документов и методичек (отправляется сразу после поиска и реранка до старта генерации текста).
* `event: sentence` — сгенерированное предложение с инлайн-флагом достоверности (`verified: true/false`). Если фраза содержит число или норму закона без сноски `[^N]` или число не подтверждено контекстом, передается `verified: false` для предупреждающей подсветки в клиентском интерфейсе без подмены текста.
* `event: token` — опциональная передача дельт токенов для клиентов с посимвольной анимацией.
* `event: done` — финальный блок метаданных с полным текстом ответа, идентификатором сообщения и агрегированным признаком `all_verified`.
* `event: verification` — асинхронный NLI-аудит логического следования утверждений второго уровня (отправляется через 1–2 секунды после `done`).
* `event: escalate` — уведомление о невозможности найти ответ или низкой уверенности и передаче обращения в очередь к оператору.
* `event: degraded_mode` — ответ в режиме деградации при недоступности или таймауте генеративной языковой модели (вывод найденных источников базы знаний без синтеза текста).

Пример потока ответа:
```text
event: status
data: {"code": "searching", "message": "Идет поиск по нормативным регламентам..."}

event: status
data: {"code": "reranking", "message": "Анализ точности найденных статей..."}

event: sources
data: {"sources": [{"chunk_id": "chunk_44fz_art44_p1", "doc_id": "fz-44", "title": "Статья 44. Обеспечение заявок", "quote_text": "Срок подачи ценовых предложений..."}]}

event: sentence
data: {"sentence_idx": 0, "text": "Согласно статье 44 Федерального закона № 44-ФЗ размер обеспечения заявки составляет 1% [^1].", "verified": true}

event: done
data: {"message_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b20", "text": "Согласно статье 44 Федерального закона № 44-ФЗ размер обеспечения заявки составляет 1% [^1].", "all_verified": true}

event: verification
data: {"sentence_idx": 0, "entailment": true, "confidence": 0.96}
```

**Формат JSON ответа (`201 Created` при ведении диалога оператором):**
Возвращает сохраненный объект `MessageResponseSchema`.

❌ Ответ `400 Bad Request` (сообщение заблокировано модерацией):
```json
{
  "detail": {
    "code": "message_blocked_by_moderation",
    "message": "Сообщение содержит недопустимую лексику. Обращение закрыто по правилам регламента."
  }
}
```

**Пограничные случаи:**
* Нарушение правил этики общения → сохранение реплики со статусом `moderation_status = 'blocked'`, перевод тикета в статус `closed_by_moderation`, завершение сессии с ошибкой `400 Bad Request`.
* Попытка отправить сообщение при отсутствии прав роли `client` → `403 Forbidden`.
* Пустое сообщение из одних пробелов → `422 Unprocessable Entity`.

---

### 3.3 `GET /api/v1/chat/events`

**Описание:** Постоянное входящее соединение для клиента по протоколу Server-Sent Events (`text/event-stream`). Используется для приема асинхронных реплик подключенного оператора и уведомлений об изменении состояния диалога.

**Заголовки:**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `Authorization` | string | Да | `Bearer <access_token>` клиента |
| `Accept` | string | Да | `text/event-stream` |

**События шины:**
* `operator_joined` — оператор взял тикет в работу (передает ФИО специалиста).
* `new_message` — входящее текстовое сообщение от оператора.
* `ticket_resolved` — обращение успешно закрыто оператором (status = 'resolved', `assigned_operator_id IS NOT NULL`) либо клиентом подтверждено решение ботом (status = 'resolved', `assigned_operator_id IS NULL`); клиенту отображается форма оценки.
* `ticket_closed_inactivity` — тикет закрыт по истечении времени неактивности.

---

### 3.4 `POST /api/v1/chat/escalate`

**Описание:** Ручной вызов оператора клиентом (эскалация). Переводит текущий тикет из статуса `bot_processing` в статус ожидания `queued`, ставит задачу распределения по свободным специалистам и запускает фоновую подготовку подсказки ассистента.

**Схемы Pydantic:**

```python
class EscalateRequestSchema(BaseModel):
    reason: str | None = Field("client_requested", description="Причина вызова оператора", example="Сложный нестандартный случай")
```

**Параметры ответа (`200 OK`):** Возвращает обновленный объект `ActiveTicketSummarySchema`.

❌ Ответ `409 Conflict` (обращение уже передано специалисту):
```json
{
  "detail": {
    "code": "ticket_already_escalated",
    "message": "Обращение уже находится в очереди или назначено оператору"
  }
}
```

---

### 3.5 `POST /api/v1/chat/tickets/{ticket_id}/cancel`

**Описание:** Отмена обращения клиентом до момента открытия диалога оператором (допустимо в статусах `bot_processing`, `queued` и `assigned`). Если обращение было зарезервировано в статусе `assigned`, слот оператора немедленно освобождается, а балансировщик отбрасывает тикет. При попытке отменить тикет в статусе `in_progress` возвращается ошибка `409 Conflict`.

**Параметры ответа (`200 OK`):**
```json
{
  "status": "canceled",
  "ticket_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11"
}
```

---

### 3.6 `POST /api/v1/chat/tickets/{ticket_id}/resolve`

**Описание:** Подтверждение клиентом успешного решения вопроса вопросно-ответной системой бота (кнопка «Вопрос решен»). Переводит тикет из статуса `bot_processing` в статус `resolved` (при этом `assigned_operator_id IS NULL`), фиксирует `closed_at` и отображает форму оценки качества консультации бота.

**Параметры ответа (`200 OK`):**
```json
{
  "status": "resolved",
  "ticket_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11",
  "closed_at": "2026-09-06T21:05:00Z"
}
```

---

### 3.7 `POST /api/v1/chat/tickets/{ticket_id}/feedback`

**Описание:** Фиксация оценки качества обслуживания (от 1 до 5 звезд) и отзыва после завершения обращения.

**Схемы Pydantic:**

```python
class FeedbackCreateRequestSchema(BaseModel):
    score: int = Field(..., ge=1, le=5, description="Оценка от 1 до 5 звезд", example=5)
    comment: str | None = Field(None, max_length=1000, description="Комментарий клиента", example="Оператор помог быстро решить проблему")

class FeedbackResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор отзыва")
    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    score: int = Field(..., description="Оценка")
    comment: str | None = Field(None, description="Текст комментария")
    created_at: datetime = Field(..., description="Время сохранения")
```

**Параметры ответа (`201 Created`):** Возвращает объект `FeedbackResponseSchema`.

**Пограничные случаи:**
* Повторная отправка отзыва по одному тикету → `409 Conflict`.
* Попытка оценить чужой тикет → `404 Not Found`.
* Попытка оценить незавершенный тикет → `400 Bad Request`.

---

## 4. Рабочее место оператора (`src/api/v1/operators.py`)

### 4.1 `GET /api/v1/operators/me/shift` и `PATCH /api/v1/operators/me/shift`

**Описание:** Управление текущей рабочей сменой оператора. При переходе в статус `active` оператор становится доступен для распределения новых тикетов, при статусах `break` или `offline` новые тикеты не назначаются.

**Схемы Pydantic:**

```python
class OperatorShiftStatusUpdateSchema(BaseModel):
    shift_status: str = Field(..., description="Новый статус смены: active, break, offline", example="active")

class OperatorProfileResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(..., description="Идентификатор оператора")
    full_name: str = Field(..., description="ФИО специалиста")
    line_id: int = Field(..., description="Идентификатор закрепленной линии")
    line_code: str = Field(..., description="Код линии: L1, L2, L3")
    shift_status: str = Field(..., description="Статус смены: active, break, offline")
    max_slots: int = Field(..., description="Максимальное количество одновременных диалогов")
    active_slots_count: int = Field(..., description="Число занятых слотов в данный момент")
```

**Параметры ответа (`200 OK`):** Возвращает объект `OperatorProfileResponseSchema`.

---

### 4.2 `GET /api/v1/operators/tickets`

**Описание:** Получение списка обращений, закрепленных за текущим оператором в его сайдбаре (в статусах `assigned` и `in_progress`).

**Схемы Pydantic:**

```python
class OperatorSidebarTicketSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    chat_id: UUID = Field(..., description="Идентификатор чата")
    priority: Literal['P0', 'P1', 'P2'] = Field('P2', description="Приоритет обращения: P0, P1, P2", example="P1")
    status: str = Field(..., description="Статус: assigned или in_progress")
    client_name: str | None = Field(None, description="ФИО клиента или email")
    company_name: str | None = Field(None, description="Наименование организации поставщика (при наличии)")
    last_message_preview: str | None = Field(None, description="Краткий фрагмент последней реплики")
    unread_messages_count: int = Field(0, description="Количество непрочитанных реплик от клиента")
    created_at: datetime = Field(..., description="Время создания обращения")
    assigned_at: datetime | None = Field(None, description="Время закрепления за специалистом")
```

**Параметры ответа (`200 OK`):** Список объектов `list[OperatorSidebarTicketSchema]`.

---

### 4.3 `POST /api/v1/operators/tickets/{ticket_id}/open`

**Описание:** Открытие карточки обращения оператором из сайдбара. Переводит тикет из статуса `assigned` в статус активного диалога `in_progress`, отправляет клиенту уведомление о подключении оператора и возвращает полный рабочий контекст. Маршрут идемпотентен: если тикет уже открыт, возвращает актуальные данные без повторных уведомлений.

**Параметры ответа (`200 OK`):**

```python
class ClientInfoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str | None = Field(None, description="Наименование организации")
    inn: str | None = Field(None, description="ИНН")
    kpp: str | None = Field(None, description="КПП")
    phone: str | None = Field(None, description="Телефон")
    full_name: str | None = Field(None, description="ФИО контактного лица")
    email: str = Field(..., description="Электронная почта")

class SimilarTicketItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: str = Field(..., description="Идентификатор закрытого обращения")
    support_line: str = Field(..., description="Линия поддержки")
    user_query: str = Field(..., description="Вопрос клиента")
    solution_text: str = Field(..., description="Текст предоставленного решения")
    similarity_score: float = Field(..., description="Степень семантической близости")

class CopilotSummaryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str = Field(..., description="Краткая суть проблемы клиента")
    suggested_line_code: str | None = Field(None, description="Рекомендованная линия поддержки")
    suggested_response: str | None = Field(None, description="Черновик ответа для оператора")
    recommended_chunk_ids: list[str] = Field(default_factory=list, description="Идентификаторы нормативных статей")
    similar_resolved_tickets: list[SimilarTicketItemSchema] = Field(default_factory=list, description="Похожие закрытые обращения из базы прецедентов Qdrant")

class OperatorTicketWorkspaceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: UUID = Field(..., description="Идентификатор обращения")
    chat_id: UUID = Field(..., description="Идентификатор чата")
    priority: Literal['P0', 'P1', 'P2'] = Field('P2', description="Приоритет обращения: P0, P1, P2", example="P1")
    status: str = Field(..., description="Текущий статус обращения")
    line_code: str = Field(..., description="Код линии")
    transfer_comment: str | None = Field(None, description="Комментарий предыдущего специалиста при переводе")
    client: ClientInfoSchema = Field(..., description="Реквизиты и контакты организации")
    copilot_summary: CopilotSummaryResponseSchema | None = Field(None, description="Подсказка языковой модели (при готовности)")
    messages: list[MessageResponseSchema] = Field(..., description="Полная история переписки чата")
```

---

### 4.4 `POST /api/v1/operators/tickets/{ticket_id}/messages`

**Описание:** Отправка текстового ответа клиенту оператором. Фиксирует реплику в базе данных с типом `sender_type = 'operator'`, публикует сообщение в шину Redis Pub/Sub и доставляет клиенту через его постоянный поток событий.

**Схемы Pydantic:**

```python
class OperatorSendMessageRequestSchema(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000, description="Текст ответа клиенту", example="Протокол разногласий формируется в личном кабинете в разделе «Мои закупки».")
```

**Параметры ответа (`201 Created`):** Возвращает объект `MessageResponseSchema`.

---

### 4.5 `POST /api/v1/operators/tickets/{ticket_id}/transfer`

**Описание:** Перевод обращения на другую линию поддержки (например, с L1 на L2). Освобождает слот текущего оператора, переводит статус тикета в `queued` для целевой линии, сохраняет ссылку на предыдущего оператора и `transfer_comment` в таблицу `tickets`, дублирует комментарий системным сообщением (`sender_type = 'system'`) в историю диалога и немедленно инициирует балансировку очереди целевой линии.

**Схемы Pydantic:**

```python
class TransferTicketRequestSchema(BaseModel):
    target_line_code: str = Field(..., description="Код целевой линии: L1, L2, L3", example="L2")
    transfer_comment: str | None = Field(None, description="Пояснение причины перевода", example="Требуется проверка криптографического плагина")
```

**Параметры ответа (`200 OK`):**
```json
{
  "status": "queued",
  "ticket_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11",
  "line_code": "L2"
}
```

---

### 4.6 `POST /api/v1/operators/tickets/{ticket_id}/resolve`

**Описание:** Успешное завершение обращения специалистом. Переводит тикет в статус `resolved` (при этом `assigned_operator_id IS NOT NULL`), фиксирует время закрытия, немедленно освобождает рабочий слот оператора, инициирует назначение следующего ожидающего тикета из очереди линии и ставит фоновую задачу автоматического аудита качества обслуживания в очередь аналитики.

**Параметры ответа (`200 OK`):**
```json
{
  "status": "resolved",
  "ticket_id": "018e5f1b-3a21-729d-9e5c-29b1f0c23b11",
  "closed_at": "2026-09-06T21:15:00Z"
}
```

---

### 4.7 `GET /api/v1/operators/events`

**Описание:** Постоянный поток событий для оператора по протоколу Server-Sent Events (`text/event-stream`). Доставляет события:
* `ticket_assigned` — в сайдбар специалиста назначен новый тикет.
* `client_message` — входящее сообщение от клиента по одному из активных тикетов.
* `copilot_ready` — фоновая задача сформировала подсказку и черновик ответа.

---

## 5. База знаний и контур самообучения (`src/api/v1/kb.py`)

### 5.1 `POST /api/v1/kb/documents/upload`

**Описание:** Загрузка пакета файлов нормативных документов или методических регламентов. Запрос принимает список файлов через `multipart/form-data`, сохраняет их на дисковый том и создает записи в таблице `kb_documents` со статусом `uploaded`. Для каждого файла порождается отдельная независимая фоновая задача Taskiq `index_kb_document` в очереди `ingestion_queue`. Маршрут возвращает код `202 Accepted` со списком зарегистрированных документов. Доступен только для ролей `supervisor` и `admin`.

**Параметры запроса (Form Data):**

| Название | Тип | Обязательный | Описание |
|---|---|---|---|
| `files` | list[UploadFile] | Да | Пакет бинарных файлов регламентов (PDF, DOCX, TXT) |
| `regime` | string | Нет | Режим или категория (опционально, по умолчанию `MOS_PORTAL`) |

**Схемы Pydantic:**

```python
class DocumentUploadItemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Идентификатор созданного документа")
    title: str = Field(..., description="Наименование документа")
    status: str = Field("uploaded", description="Начальный статус обработки")
    message: str = Field(..., description="Поясняющее сообщение")
```

**Параметры ответа (`202 Accepted`):** Возвращает список объектов `list[DocumentUploadItemResponseSchema]`.

```json
[
  {
    "doc_id": "kb_doc_44_fz_v1",
    "title": "44_fz.pdf",
    "status": "uploaded",
    "message": "Документ принят в очередь на разбор и индексацию"
  }
]
```

---

### 5.2 `GET /api/v1/kb/documents` и `GET /api/v1/kb/documents/{doc_id}/status`

**Описание:** Получение реестра документов базы знаний и проверка статуса обработки конкретного файла.

**Схемы Pydantic:**

```python
from datetime import date

class DocumentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    doc_id: str = Field(..., description="Идентификатор нормативного акта")
    title: str = Field(..., description="Наименование")
    regime: str | None = Field(None, description="Режим регулирования или категория (при наличии)")
    edition_date: date | None = Field(None, description="Дата редакции документа")
    status: str = Field(..., description="Статус: uploaded, indexing, indexed, failed, deprecated")
    error_message: str | None = Field(None, description="Текст ошибки при сбое парсинга или индексации")
    created_at: datetime = Field(..., description="Время добавления")
```

---

### 5.3 `DELETE /api/v1/kb/documents/{doc_id}`

**Описание:** Архивация нормативного акта (перевод в статус `deprecated`). Документ перестает участвовать в поиске для новых обращений.

**Параметры ответа (`204 No Content`):** Пустое тело ответа.

---

### 5.4 `PATCH /api/v1/kb/nodes/{node_id}`

**Описание:** Ручная корректировка текста конкретной статьи или пункта регламента в базе знаний. Позволяет оперативно устранить неточность без полной повторной загрузки файла.

**Схемы Pydantic:**

```python
class UpdateKbNodeRequestSchema(BaseModel):
    title: str | None = Field(None, description="Уточненный заголовок статьи")
    full_content: str = Field(..., min_length=1, description="Актуализированный текст статьи")
```

**Параметры ответа (`200 OK`):** Возвращает обновленные данные узла.

---

### 5.5 `GET /api/v1/kb/faq-drafts` и `POST /api/v1/kb/faq-drafts/{draft_id}/review`

**Описание:** Контур самообучения. Просмотр и модерация руководителем черновиков статей, автоматически сгенерированных из успешных ответов операторов.

**Схемы Pydantic:**

```python
class FaqDraftResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор черновика")
    ticket_id: UUID = Field(..., description="Исходное обращение")
    question: str = Field(..., description="Обобщенный вопрос клиента")
    answer: str = Field(..., description="Эталонный ответ")
    kind: str = Field(..., description="Категория: normative или procedural")
    status: str = Field(..., description="Статус: PENDING, APPROVED, REJECTED")
    created_at: datetime = Field(..., description="Время формирования")

class ReviewFaqDraftRequestSchema(BaseModel):
    action: str = Field(..., description="Решение: APPROVED или REJECTED", example="APPROVED")
    question: str | None = Field(None, description="Скорректированный текст вопроса")
    answer: str | None = Field(None, description="Скорректированный текст ответа")
```

**Параметры ответа (`200 OK`):** При утверждении черновик преобразуется в постоянную статью базы знаний и попадает в поисковый индекс.

---

## 6. Аналитика и аудит качества (`src/api/v1/analytics.py`)

### 6.1 `GET /api/v1/analytics/dashboard`

**Описание:** Сводная витрина показателей эффективности поддержки за выбранный временной интервал. Доступна ролям `supervisor` и `admin`.

**Query-параметры:**
* `from_date` (date, опционально): начало периода;
* `to_date` (date, опционально): конец периода.

**Схемы Pydantic:**

```python
class AnalyticsDashboardResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_tickets: int = Field(..., description="Общее число обращений за период")
    bot_resolved_percent: float = Field(..., description="Процент обращений, решенных ботом без человека")
    avg_first_response_time_sec: float = Field(..., description="Среднее время первого ответа оператора")
    avg_handling_time_sec: float = Field(..., description="Среднее время полного решения обращения")
    client_csat: float = Field(..., description="Средняя оценка клиентов от 1 до 5")
    adjusted_csat: float = Field(..., description="Скорректированная оценка клиентов за вычетом системных сбоев")
    avg_ai_politeness_score: float = Field(..., description="Оценка вежливости по аудиту модели")
    avg_ai_completeness_score: float = Field(..., description="Оценка полноты по аудиту модели")
    active_incidents_count: int = Field(..., description="Число нерешенных технических сбоев портала")
```

**Параметры ответа (`200 OK`):** Возвращает объект `AnalyticsDashboardResponseSchema`.

---

### 6.2 `GET /api/v1/analytics/operators`

**Описание:** Суточные показатели работы специалистов службы поддержки для расчета рейтингов и контроля нагрузки.

**Query-параметры:**
* `date` (date, опционально): конкретная дата отчета;
* `line_code` (string, опционально): фильтрация по линии (L1, L2, L3).

**Схемы Pydantic:**

```python
class OperatorDailyMetricResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operator_id: UUID = Field(..., description="Идентификатор оператора")
    operator_name: str = Field(..., description="ФИО сотрудника")
    line_code: str = Field(..., description="Линия поддержки")
    metric_date: date = Field(..., description="Дата")
    total_tickets_handled: int = Field(..., description="Количество обработанных тикетов")
    avg_first_response_time_sec: float | None = Field(None, description="Среднее время первого ответа")
    avg_handling_time_sec: float | None = Field(None, description="Среднее время диалога")
    avg_client_csat: float | None = Field(None, description="Средняя оценка клиентов")
    avg_adjusted_csat: float | None = Field(None, description="Скорректированная оценка")
    avg_ai_quality_score: float | None = Field(None, description="Оценка качества от модели")
```

---

### 6.3 `GET /api/v1/analytics/incidents`

**Описание:** Реестр системных технических сбоев портала (недоступность личного кабинета, ошибки плагина ЭЦП), выявленных автоматическим аудитом переписки.

**Схемы Pydantic:**

```python
class SystemIncidentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор сбоя")
    ticket_id: UUID = Field(..., description="Обращение, зафиксировавшее сбой")
    incident_type: str = Field(..., description="Тип проблемы: portal_downtime, crypto_plugin, api_error")
    description: str = Field(..., description="Описание симптомов проблемы")
    status: str = Field(..., description="Статус: open, in_review, resolved")
    created_at: datetime = Field(..., description="Время обнаружения")
    resolved_at: datetime | None = Field(None, description="Время устранения")
```

---

### 6.4 `GET /api/v1/analytics/export`

**Описание:** Выгрузка сводного отчета в формате файла CSV или JSON.

**Query-параметры:**
* `format` (string, по умолчанию `csv`): формат выгрузки (`csv` или `json`);
* `from_date` (date, обязательно): дата начала;
* `to_date` (date, обязательно): дата окончания.

---

## 7. Сервисная логика и оркестрация диалогов

### 7.1. Главный оркестратор диалогов (`ChatService.process_client_message`)

Метод вызывается эндпоинтом `POST /api/v1/chat/messages` при отправке реплики клиентом.

```text
[Клиент отправил сообщение]
          │
          ▼
1. Проверка учетной записи и контекста чата
   - По user_id извлекается постоянный chat_id из таблицы chats.
   - Выполняется поиск активного обращения со статусом NOT IN ('resolved', 'closed_by_inactivity', 'closed_by_moderation', 'canceled').
   - Если активного тикета нет: атомарно создается новый тикет со статусом bot_processing.
          │
          ▼
2. Модерация входящего текста (chat/moderation.py)
   - Текст проверяется по словарю ненормативной лексики и правилам этики.
   - ЕСЛИ ОБНАРУЖЕНО НАРУШЕНИЕ:
     * Сообщение сохраняется в messages со статусом moderation_status = 'blocked'.
     * Статус тикета переводится в closed_by_moderation.
     * Завершается сессия, клиенту возвращается HTTP 400 Bad Request с предупреждением.
     * Обработка прерывается, вызовы RAG и операторов блокируются.
          │
          ▼
3. Сохранение сообщения клиента
   - Сообщение сохраняется в таблицу messages (sender_type = 'client', moderation_status = 'passed').
   - Реплика сериализуется и добавляется в Redis: RPUSH chat:context:{ticket_id}.
   - Список обрезается до 10 реплик: LTRIM chat:context:{ticket_id} -10 -1.
   - Продлевается время жизни ключа: EXPIRE chat:context:{ticket_id} 1800.
          │
          ▼
4. Развилка по текущему исполнителю обращения:
   ├───────────────────────────────────────────────────────────┐
   │ Ветка А: Тикет ведет человек                              │ Ветка Б: Тикет обрабатывает база знаний
   │ (статус assigned или in_progress)                         │ (статус bot_processing)
   ▼                                                           ▼
   - Публикация в channel:ticket:{ticket_id}                   5. Вызов поискового ядра (rag/service.py)
   - Реплика моментально отображается у оператора              - Передача текста и скользящего окна Redis
   - Возврат клиенту HTTP 201 Created                          - rag/router.py: классификация темы и линии (L1/L2/L3)
                                                               - rag/retriever.py: гибридный поиск по базе знаний
                                                               - rag/reranker.py: ранжирование фрагментов через TEI
                                                               - Трансляция клиенту SSE-событий status
                                                                        │
                                                                        ▼
                                                               6. Оценка уверенности модели:
                                                                ├───────────────────────────────┐
                                                                ▼                               ▼
                                                                Высокая уверенность             Низкая уверенность или отказ
                                                                (ответ найден в статьях)        (или клиент просил человека)
                                                                │                               │
                                                                ▼                               ▼
                                                                - Потоковая генерация ответа    - Перевод статуса в queued
                                                                  через rag/generator.py        - Задача dispatch_line_queue
                                                                - Передача токенов клиенту        в dispatch_queue (Taskiq)
                                                                  в потоке SSE (event: token)   - Задача generate_copilot_summary
                                                                - Сохранение реплики бота         в copilot_queue (Taskiq)
                                                                  в messages и источников       - Отправка клиенту события
                                                                  в message_sources               event: escalate
                                                                - Завершение потока             - Закрытие соединения
                                                                  событием event: done
```

---

### 7.2. Алгоритм подключения и ведения тикета оператором

1. **Поступление обращения:** При назначении балансировщиком тикет переходит в статус `assigned`. Оператор получает уведомление через постоянный поток `GET /api/v1/operators/events` (`ticket_assigned`), карточка появляется в сайдбаре.
2. **Открытие карточки:** Оператор кликает на тикет, отправляя `POST /api/v1/operators/tickets/{ticket_id}/open`. Сервер:
   * Переводит статус тикета в `in_progress`.
   * Публикует событие `operator_joined` с именем специалиста в канал `channel:ticket:{ticket_id}`. Клиент мгновенно видит имя подключившегося специалиста.
   * Возвращает оператору полную ленту сообщений клиента и подсказку ассистента.
3. **Обмен сообщениями:** Ответы оператора отправляются через `POST /api/v1/operators/tickets/{ticket_id}/messages`. Сообщения сохраняются в реляционной базе данных и выталкиваются клиенту в его постоянный поток событий `GET /api/v1/chat/events`.
4. **Завершение:** Оператор нажимает кнопку решения проблемы (`POST /api/v1/operators/tickets/{ticket_id}/resolve`). Сервер:
   * Переводит статус тикета в `resolved` (при этом `assigned_operator_id IS NOT NULL`) и фиксирует метку времени `closed_at`.
   * Публикует событие `ticket_resolved` в канал клиента (в интерфейсе открывается окно оценки от 1 до 5 звезд).
   * Немедленно освобождает рабочий слот специалиста и ставит задачу `dispatch_line_queue` для назначения следующего ожидающего тикета.
   * Отправляет задачу `audit_ticket_quality` в очередь аналитики `analytics_queue` для проверки качества диалога языковой моделью.

---

### 7.3. Алгоритм конвейера загрузки и индексации базы знаний

1. **Прием пакета файлов:** Маршрут `POST /api/v1/kb/documents/upload` сохраняет файлы в каталог `uploads/kb/`, фиксирует записи в таблице `kb_documents` со статусом `uploaded` и ставит независимые задачи `index_kb_document` в очередь `ingestion_queue` Taskiq. Клиент сразу получает код `202 Accepted` со списком зарегистрированных идентификаторов.
2. **Фоновый разбор:** Воркер переводит статус документа в `indexing`, считывает файл, извлекает текст, распознает структуру нормативного документа (разделы, статьи, пункты) и сохраняет узлы в таблицу `kb_nodes`.
3. **Нарезка и векторизация:** Текст разбивается на атомарные фрагменты, формируются гипотетические вопросы, рассчитываются плотные и разреженные векторы, сохраняемые в хранилище Qdrant и таблицу `kb_chunks`.
4. **Финализация:** При успешной индексации статус документа в таблице `kb_documents` обновляется на `indexed`, делая его доступным для поиска ботом. При ошибке статус переводится в `failed` с фиксацией причины в поле `error_message`.
