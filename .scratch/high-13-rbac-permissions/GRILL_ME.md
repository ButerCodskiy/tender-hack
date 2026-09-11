# Архитектурная прожарка (Grill Me): Разграничение прав доступа по ролевой модели (HIGH-13)

> **Статус:** Завершено (Утверждено)  
> **Исполнитель:** Разработчик 2  
> **Цель:** Фиксация решений по 5 ключевым инженерным вопросам перед реализацией RBAC.

---

## 1. Архитектура универсальной фабрики зависимостей (`require_roles`) и поддержка SSE

### Принятое решение:
- Реализовать вызываемый класс `RoleChecker` в [backend/src/api/dependencies.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/dependencies.py).
- Конструктор `RoleChecker(allowed_roles: Iterable[UserRole | str], sse: bool = False)`:
  - Нормализует список допустимых ролей в `frozenset[str]` строковых кодов.
  - В зависимости от флага `sse`:
    - при `sse=False` объявляет `__call__(self, current_user: CurrentUserDep) -> UserModel`;
    - при `sse=True` объявляет `__call__(self, current_user: CurrentUserSseDep) -> UserModel`.
- Экспортировать удобные хелпер-фабрики:
  - `require_roles(*roles: UserRole | str) -> RoleChecker` (для обычных HTTP REST-эндпоинтов, извлекает токен строго из заголовка `Authorization: Bearer <token>`);
  - `require_roles_sse(*roles: UserRole | str) -> RoleChecker` (для EventSource / SSE, поддерживает `Authorization: Bearer <token>` и `?token=<token>`).
- Экспортировать готовые типизированные алиасы `Annotated` для частых ролей:
  - `CurrentClientDep = Annotated[UserModel, Depends(require_roles(UserRole.CLIENT))]`
  - `CurrentClientSseDep = Annotated[UserModel, Depends(require_roles_sse(UserRole.CLIENT))]`
  - `CurrentOperatorDep = Annotated[UserModel, Depends(require_roles(UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN))]`
  - `CurrentOperatorSseDep = Annotated[UserModel, Depends(require_roles_sse(UserRole.OPERATOR, UserRole.SUPERVISOR, UserRole.ADMIN))]`
  - `CurrentSupervisorDep = Annotated[UserModel, Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))]`
  - `CurrentAdminDep = Annotated[UserModel, Depends(require_roles(UserRole.ADMIN))]`
- **Защита от `MissingGreenlet` в asyncpg:**
  - Проверка выполняется через безопасное извлечение `role = getattr(current_user, "role", None)` и чтение `role_code = getattr(role, "code", None)`.
  - Если по какой-то причине связь `role` не была загружена в сессии (или передан мок без `role`), зависимость не пытается делать ленивый SQL-запрос `await user.role` (что роняет event loop), а трактует роль как пустую и немедленно бросает 403 Forbidden с кодом `access_denied`.


---

## 2. Матрица доступа и иерархия ролей (Role Matrix)

### Принятое решение:
Утверждена строгая ролевая матрица с принципом суперпользователя `admin` в служебных контурах (без подмены клиентской сущности):

| Домен / Файл | Метод и путь | Назначение | Разрешенные роли | Используемая зависимость |
|---|---|---|---|---|
| **Клиентский чат**<br>`src/api/v1/chat.py` | `GET /api/v1/chat`<br>`POST /api/v1/chat/messages` | Лента сообщений, отправка вопроса | `client` | `CurrentClientDep` |
| **Клиентский чат**<br>`src/api/v1/chat.py` | `GET /api/v1/chat/events` | SSE-поток клиента | `client` | `CurrentClientSseDep` |
| **База знаний**<br>`src/api/v1/kb.py` | `GET /api/v1/kb/documents`<br>`GET /api/v1/kb/documents/{id}/status` | Просмотр реестра и статуса индексации | `operator`, `supervisor`, `admin` | `CurrentOperatorDep` (или `require_roles(OPERATOR, SUPERVISOR, ADMIN)`) |
| **База знаний**<br>`src/api/v1/kb.py` | `POST /api/v1/kb/documents/upload`<br>`DELETE /api/v1/kb/documents/{id}`<br>`PATCH /api/v1/kb/nodes/{id}` | Загрузка документов, удаление, ручная правка узлов | `supervisor`, `admin` | `CurrentSupervisorDep` |
| **Рабочее место оператора**<br>`src/api/v1/operators.py` | Все REST-эндпоинты (`/me/shift`, `/tickets`, `/open`, `/messages`, `/transfer`, `/resolve`) | Управление сменой, диалог с клиентом, передача тикетов | `operator`, `supervisor`, `admin` | `CurrentOperatorDep` |
| **Рабочее место оператора**<br>`src/api/v1/operators.py` | `GET /api/v1/operators/events` | SSE-поток оператора | `operator`, `supervisor`, `admin` | `CurrentOperatorSseDep` |
| **Аналитика**<br>`src/api/v1/analytics.py` | Все эндпоинты (`/dashboard`, `/operators`, `/incidents`, `/export`) | Сводные метрики, аудит качества, выгрузка отчетов | `supervisor`, `admin` | `CurrentSupervisorDep` (на уровне роутера `dependencies=[Depends(...)]`) |
| **Профиль пользователя**<br>`src/api/v1/auth.py` | `GET /api/v1/auth/me` | Данные текущего профиля | Любой аутентифицированный (`client`, `operator`, `supervisor`, `admin`) | `CurrentUserDep` |
| **Публичные эндпоинты**<br>`src/api/v1/auth.py`, `main.py` | `/auth/register`, `/auth/login`, `/auth/refresh`, `/health` | Регистрация, аутентификация, healthcheck | Анонимный доступ | — |

**Обоснование ограничений роли `client` в `chat.py`:**
Бизнес-логика клиентского диалога (`ChatService`) жестко опирается на наличие у пользователя постоянного чата клиента (`ChatModel`) и профиля контрагента (`ClientProfileModel`). Вход оператора или администратора в клиентский чат ломает доменную инвариантность (попытка создать тикет на оператора как на клиента). Администраторы и операторы тестируют клиентский чат через отдельные тестовые учетные записи с ролью `client`.


---

## 3. Строгий контракт ошибки 403 Forbidden

### Принятое решение:
- Создать типизированный класс `AccessDeniedException` в [backend/src/api/dependencies.py](file:///c:/Users/Дмитрий/Desktop/git/test-RAG/backend/src/api/dependencies.py):
  ```python
  class AccessDeniedException(HTTPException):
      """Исключение при отказе в доступе по ролевой модели (403 Forbidden)."""

      def __init__(
          self,
          message: str = "Недостаточно прав для выполнения данной операции",
      ) -> None:
          super().__init__(
              status_code=status.HTTP_403_FORBIDDEN,
              detail={
                  "code": "access_denied",
                  "message": message,
              },
          )
  ```
- **Преимущества подхода:**
  - Наследование от `fastapi.HTTPException` гарантирует автоматическую сериализацию в JSON механизмом FastAPI без необходимости регистрации кастомных `exception_handler` в `main.py` (что сохраняет изоляцию зон ответственности разработчиков).
  - Строгое соответствие схеме `ErrorResponseSchema` из [API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §1.3 (`detail.code = "access_denied"`).
  - Возможность точечной детализации причины (например, `AccessDeniedException("Доступ разрешен только операторам поддержки")` или `AccessDeniedException("Доступ разрешен только клиентам платформы")`), сохраняя единый машиночитаемый `code: "access_denied"`.


---

## 4. План предотвращения регрессий в существующих тестах

### Принятое решение:
1. **Синхронизация `tests/api/test_kb_api.py`:**
   - В фикстуру `test_app` добавить переопределение зависимости:
     ```python
     @pytest.fixture
     def mock_supervisor_user() -> UserModel:
         return UserModel(
             id=uuid6.uuid7(),
             email="supervisor@mos.ru",
             password_hash="fake",
             full_name="Тестовый Супервизор",
             role=RoleModel(id=3, code="supervisor", name="Руководитель"),
             is_active=True,
         )

     @pytest.fixture
     def test_app(mock_kb_service: AsyncMock, mock_supervisor_user: UserModel) -> FastAPI:
         app = FastAPI()
         app.include_router(kb_router, prefix="/api/v1")
         app.dependency_overrides[get_kb_service] = lambda: mock_kb_service
         app.dependency_overrides[get_current_user] = lambda: mock_supervisor_user
         return app
     ```
   - Это предотвращает падение 16 существующих тестов бизнес-логики (пагинация, Qdrant cascade delete, patch node) с кодом 401/403 и не требует изменения тел тестовых функций.

2. **Синхронизация `tests/operators/test_operator_events_sse.py`:**
   - В тесте `test_operator_events_client_role_forbidden_403` обновить проверку структуры 403-ответа:
     ```python
     assert response.status_code == status.HTTP_403_FORBIDDEN
     detail = response.json()["detail"]
     assert detail["code"] == "access_denied"
     assert "Доступ разрешен только операторам" in detail["message"]
     ```

3. **Новый тестовый набор `tests/auth/test_rbac_permissions.py`:**
   - Реализовать исчерпывающее тестирование матрицы доступа RBAC:
     - 401 Unauthorized при отсутствии токена на закрытых роутах.
     - 403 Forbidden с кодом `access_denied` при попытке клиента обратиться к эндпоинтам оператора, KB (upload/patch/delete) и аналитики.
     - 403 Forbidden с кодом `access_denied` при попытке оператора обратиться к клиентскому чату (`chat.py`) или к мутирующим операциям KB (`upload/patch/delete`).
     - 200/201/202 Success при наличии требуемых ролей согласно Role Matrix.


---

## 5. Защита на уровне роутера vs эндпоинтов (OpenAPI & Type Safety)

### Принятое решение:
Выбран **гибридный подход** с разделением зон ответственности:

1. **Маршруты с доступом к контексту пользователя и дифференцированными правами (`chat.py`, `operators.py`, `kb.py`):**
   - Защита внедряется **в сигнатурах функций-обработчиков** через типизированные аннотации:
     - `chat.py`: `current_user: CurrentClientDep` (для REST) и `current_user: CurrentClientSseDep` (для `/events`);
     - `operators.py`: `operator: CurrentOperatorDep` (для REST) и `operator: CurrentOperatorSseDep` (для `/events`);
     - `kb.py` (чтение `GET /documents`, `GET /documents/{id}/status`): `user: CurrentOperatorDep` (или `require_roles(OPERATOR, SUPERVISOR, ADMIN)`);
     - `kb.py` (мутации `POST /upload`, `DELETE /documents/{id}`, `PATCH /nodes/{id}`): `user: CurrentSupervisorDep` (или `require_roles(SUPERVISOR, ADMIN)`).
   - **Преимущества:**
     - Прямой доступ к полям `operator.id`, `current_user.id` без приведения типов и проверок на `None`;
     - Точное разграничение разнородных прав внутри одного роутера (чтение доступно операторам, запись — только супервизорам/админам);
     - Автогенерация схем OpenAPI/Swagger с точным указанием `BearerAuth` для каждого эндпоинта.

2. **Маршруты с монолитными повышенными правами (`analytics.py`):**
   - Защита на уровне роутера:
     ```python
     router = APIRouter(
         prefix="/analytics",
         tags=["analytics"],
         dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))],
     )
     ```
   - **Преимущества:**
     - Принцип **Fail-Safe Defaults**: любой вновь создаваемый эндпоинт аналитики автоматически защищен от случайного публичного открытия.
     - Если обработчику понадобится инстанс пользователя (например, для журнала аудита), он сможет объявить `supervisor: CurrentSupervisorDep` в аргументах без дублирования проверок.

---

## 6. Итоговый статус архитектурной прожарки
- [x] Вопрос 1: Архитектура универсальной фабрики зависимостей (`RoleChecker`, `require_roles`, `require_roles_sse`) утверждена.
- [x] Вопрос 2: Строгая ролевая матрица и статус суперпользователя утверждены.
- [x] Вопрос 3: Контракт ошибки `AccessDeniedException` с кодом `access_denied` утвержден.
- [x] Вопрос 4: План предотвращения регрессий в существующих тестах (`test_kb_api.py`, `test_operator_events_sse.py`) утвержден.
- [x] Вопрос 5: Гибридный подход защиты роутеров и эндпоинтов утвержден.
- **Готовность к переходу к реализации:** Полная.

