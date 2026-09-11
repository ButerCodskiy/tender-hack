# Пошаговый план реализации: Разграничение прав доступа по ролевой модели (HIGH-13)

> **Статус:** Утвержден к реализации (на основе решений Grill Me)  
> **Исполнитель:** Разработчик 2  
> **Зона ответственности:** `backend/src/api/dependencies.py`, `backend/src/api/v1/`, `backend/tests/`

---

## Этап 1. Ядро RBAC и исключения безопасности (`src/api/dependencies.py`)

> **Цель:** Создать переиспользуемую фабрику зависимостей `RoleChecker` и класс ошибки `AccessDeniedException`, гарантирующие соблюдение контракта `ErrorResponseSchema` (§1.3) и защиту от `MissingGreenlet`.

- [x] **1.1. Класс исключения `AccessDeniedException`:**
  - Наследуется от `fastapi.HTTPException`.
  - Устанавливает `status_code = status.HTTP_403_FORBIDDEN`.
  - Формирует тело `detail = {"code": "access_denied", "message": message}` (дефолтное сообщение: `"Недостаточно прав для выполнения данной операции"`).
- [x] **1.2. Фабрика и вызываемый класс `RoleChecker`:**
  - Принимает `allowed_roles: Iterable[UserRole | str]` и `sse: bool = False`.
  - Приводит роли к `frozenset[str]` строковых значений.
  - Метод `__call__(self, current_user: UserModel = Depends(...)) -> UserModel`:
    - При `sse=False` зависит от `CurrentUserDep`.
    - При `sse=True` зависит от `CurrentUserSseDep`.
    - Безопасно извлекает роль:
      ```python
      role = getattr(current_user, "role", None)
      role_code = getattr(role, "code", None)
      ```
    - При `role_code not in self.allowed_roles` выбрасывает `AccessDeniedException`.
    - Возвращает `current_user`.
- [x] **1.3. Фабричные функции и типизированные алиасы:**
  - `require_roles(*roles: UserRole | str) -> RoleChecker` (для REST)
  - `require_roles_sse(*roles: UserRole | str) -> RoleChecker` (для SSE)
  - Экспорт типизированных зависимостей `Annotated`:
    - `CurrentClientDep = Annotated[UserModel, Depends(require_roles(UserRole.CLIENT))]`
    - `CurrentClientSseDep = Annotated[UserModel, Depends(require_roles_sse(UserRole.CLIENT))]`
    - `CurrentOperatorDep = Annotated[UserModel, Depends(require_roles(UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN))]`
    - `CurrentOperatorSseDep = Annotated[UserModel, Depends(require_roles_sse(UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN))]`
    - `CurrentSupervisorDep = Annotated[UserModel, Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))]`
    - `CurrentAdminDep = Annotated[UserModel, Depends(require_roles(UserRole.ADMIN))]`
- [x] **1.4. Обратная совместимость:**
  - Переписать `require_operator_user` и `require_operator_user_sse` на использование `RoleChecker` во избежание регрессий, если они импортируются напрямую.
- [x] ✅ **Проверка Этапа 1:**
  - Модульный тест фабрики `RoleChecker`: передача `UserModel` с разрешенной и запрещенной ролью, проверка исключения `AccessDeniedException` с кодом `access_denied`.

---

## Этап 2. Защита клиентского диалога (`src/api/v1/chat.py`)

> **Цель:** Изолировать клиентский чат строго для роли `client` согласно [API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §3.2 (строка 437).

- [x] **2.1. Обновление эндпоинтов в `backend/src/api/v1/chat.py`:**
  - `GET /api/v1/chat` (`get_chat_state`): заменить `current_user: CurrentUserDep` на `current_user: CurrentClientDep`.
  - `GET /api/v1/chat/events` (`get_chat_events`): заменить `current_user: CurrentUserSseDep` на `current_user: CurrentClientSseDep`.
  - `POST /api/v1/chat/messages` (`send_message`): заменить `current_user: CurrentUserDep` на `current_user: CurrentClientDep`.
- [x] ✅ **Проверка Этапа 2:**
  - Запрос к `POST /api/v1/chat/messages` с токеном оператора или администратора возвращает `403 Forbidden` с телом `{"detail": {"code": "access_denied", ...}}`.
  - Запрос с токеном клиента успешно принимается.

---

## Этап 3. Защита базы знаний (`src/api/v1/kb.py`)

> **Цель:** Устранить критическую уязвимость публичного доступа к базе знаний и разграничить права на чтение (`operator`, `supervisor`, `admin`) и мутации (`supervisor`, `admin`).

- [x] **3.1. Защита эндпоинтов чтения:**
  - `GET /api/v1/kb/documents` (`list_documents`): добавить параметр `user: CurrentOperatorDep`.
  - `GET /api/v1/kb/documents/{doc_id}/status` (`get_document_status`): добавить параметр `user: CurrentOperatorDep`.
- [x] **3.2. Защита эндпоинтов изменения и удаления:**
  - `POST /api/v1/kb/documents/upload` (`upload_documents`): добавить параметр `user: CurrentSupervisorDep`.
  - `DELETE /api/v1/kb/documents/{doc_id}` (`delete_document`): добавить параметр `user: CurrentSupervisorDep`.
  - `PATCH /api/v1/kb/nodes/{node_id}` (`update_node`): добавить параметр `user: CurrentSupervisorDep`.
- [x] ✅ **Проверка Этапа 3:**
  - Анонимный запрос к любому эндпоинту `kb.py` возвращает `401 Unauthorized`.
  - Запрос оператора к `POST /upload` или `DELETE /documents/{id}` возвращает `403 Forbidden` (`access_denied`).
  - Запрос оператора к `GET /documents` возвращает `200 OK`.
  - Запрос супервизора или администратора к `POST /upload` возвращает `202 Accepted`.

---

## Этап 4. Защита контура аналитики (`src/api/v1/analytics.py`)

> **Цель:** Закрыть доступ ко всем будущим эндпоинтам аналитики по принципу Fail-Safe Defaults для ролей `supervisor`, `admin`.

- [x] **4.1. Обновление `backend/src/api/v1/analytics.py`:**
  - Установить зависимость на уровне роутера:
    ```python
    router = APIRouter(
        prefix="/analytics",
        tags=["analytics"],
        dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))],
    )
    ```
- [x] ✅ **Проверка Этапа 4:**
  - Любой запрос к эндпоинтам аналитики без токена возвращает `401 Unauthorized`.
  - Запрос клиента или оператора возвращает `403 Forbidden` (`access_denied`).

---

## Этап 5. Синхронизация существующих тестов и новый RBAC тест-сьют

> **Цель:** Предотвратить регрессии в существующих тестах и покрыть новую функциональность комплексными тестами безопасности.

- [x] **5.1. Синхронизация `backend/tests/api/test_kb_api.py`:**
  - В фикстуру `test_app` добавить фикстуру мока супервизора `mock_supervisor_user` (`code="supervisor"`).
  - Зарегистрировать `app.dependency_overrides[get_current_user] = lambda: mock_supervisor_user`.
  - Убедиться, что все 16 тестов в `test_kb_api.py` выполняются без ошибок.
- [x] **5.2. Синхронизация `backend/tests/operators/test_operator_events_sse.py`:**
  - В тесте `test_operator_events_client_role_forbidden_403` адаптировать проверку `response.json()["detail"]["code"] == "access_denied"`.
- [x] **5.3. Создание `backend/tests/auth/test_rbac_permissions.py`:**
  - Тестирование сквозной матрицы ролей:
    - 401 Unauthorized при обращении без токена ко всем закрытым маршрутам (`/chat`, `/chat/events`, `/operators/tickets`, `/kb/documents`, `/kb/documents/upload`, `/analytics`).
    - 403 Forbidden `access_denied` при попытке клиента открыть `/operators/tickets`, `/kb/documents/upload`, `/analytics`.
    - 403 Forbidden `access_denied` при попытке оператора отправить сообщение в `/chat/messages` или удалить документ через `DELETE /kb/documents/{id}`.
    - 200/202 Success для супервизора и администратора в `/kb/documents/upload` и `/operators/tickets`.
- [x] ✅ **Проверка Этапа 5:**
  - Запуск `uv run pytest tests/auth/ tests/api/test_kb_api.py tests/operators/test_operator_events_sse.py`. Все тесты зеленые.

---

## Этап 6. Обновление дорожной карты (`docs/HACKATHON_ROADMAP.md`)

- [x] **6.1. Отметка задачи [HIGH-13] в дорожной карте:**
  - Проставить чекбоксы приемки задачи `HIGH-13`.
