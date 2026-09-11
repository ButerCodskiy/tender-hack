# Контекст и архитектурный анализ задачи HIGH-13

> **Задача:** Разграничение прав доступа по ролевой модели (RBAC).  
> **Исполнитель:** Разработчик 2 (Пользователи, профили, безопасность).  
> **Зона ответственности:** `backend/src/auth/service.py`, `backend/src/api/dependencies.py`, закрытые маршруты (`src/api/v1/`).  
> **Режим:** Анализ и разведка (READ-ONLY).

---

## 1. Анализ моделей учетных записей и ролей (`backend/src/auth/models.py`)

### 1.1. Устройство `RoleModel` и `UserModel`
Согласно [DATABASE_SPECIFICATION.md](../../docs/DATABASE_SPECIFICATION.md) §2.1 и [backend/src/auth/models.py](../../backend/src/auth/models.py):

- **Перечисление ролей `UserRole(StrEnum)`:**
  ```python
  class UserRole(StrEnum):
      CLIENT = "client"
      OPERATOR = "operator"
      SUPERVISOR = "supervisor"
      ADMIN = "admin"
  ```
- **Модель роли `RoleModel` (`roles`):**
  - `id: Mapped[int]` (SmallInteger, primary_key, autoincrement=True)
  - `code: Mapped[str]` (String(32), unique=True, nullable=False) — символьный код роли (`client`, `operator`, `supervisor`, `admin`)
  - `name: Mapped[str]` (String(64), nullable=False) — человекочитаемое наименование («Клиент (Поставщик)», «Оператор поддержки» и т.д.)
  - `description: Mapped[str | None]` (Text, nullable=True)
  - `users: Mapped[list["UserModel"]] = relationship(back_populates="role")`
- **Модель пользователя `UserModel` (`users`):**
  - `id: Mapped[uuid.UUID]` (Uuid, primary_key, default=uuid6.uuid7)
  - `role_id: Mapped[int]` (SmallInteger, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True)
  - `email: Mapped[str]` (String(255), unique=True, nullable=False, index=True)
  - `password_hash: Mapped[str]` (String(255), nullable=False)
  - `full_name: Mapped[str | None]` (String(255), nullable=True)
  - `is_active: Mapped[bool]` (Boolean, default=True, server_default="true", nullable=False)
  - `created_at`, `updated_at`: `DateTime(timezone=True)`
  - Отношения:
    - `role: Mapped["RoleModel"] = relationship(back_populates="users")`
    - `client_profile: Mapped["ClientProfileModel | None"] = relationship(...)`
    - `operator_profile: Mapped["OperatorProfileModel | None"] = relationship(...)`

### 1.2. Отношение пользователя к роли и стратегия загрузки (lazy/eager)
- **Именование отношения:** `user.role`, строковый код роли доступен как `user.role.code` (или `UserRole(user.role.code)`).
- **Стратегия загрузки в декларативной модели:** По умолчанию `lazy="select"`. В модели явный параметр `lazy` не указан.
- **Особенность Async SQLAlchemy:** При ленивой загрузке попытка синхронного чтения `user.role` в асинхронном контексте (если связь не была загружена в том же запросе) вызывает критическую ошибку `sqlalchemy.exc.MissingGreenlet: await_only() ... GreenletSpawn`.
- Поэтому все точки извлечения `UserModel` для аутентификации **обязаны** использовать eager loading (`joinedload(UserModel.role)` или `selectinload(UserModel.role)`).

---

## 2. Анализ сервисного слоя и репозитория (`backend/src/auth/`)

### 2.1. Методы `AuthService` (`backend/src/auth/service.py`)
- **Методы проверки и валидации ролей:** ❌ **Полностью отсутствуют.**
  В классе `AuthService` нет методов вроде `check_role`, `verify_role_access`, `assert_role` или `has_permission`.
- **Существующие методы `AuthService`:**
  - `register_client`: создает учетную запись с ролью `UserRole.CLIENT`.
  - `login`: аутентифицирует пользователя по email и паролю, проверяет `user.is_active` (при `False` бросает `HTTPException(403, detail={"code": "account_disabled", ...})`), формирует пару токенов с claim `role`.
  - `get_user_by_token(token, expected_type)`: декодирует JWT, извлекает `user_id`, запрашивает пользователя через `self.user_repo.get_by_id(user_id)`, проверяет `user.is_active` (403 `account_disabled`). Саму роль пользователя метод не валидирует.
  - `refresh_tokens`: перевыпускает токены по refresh-токену.
  - `_build_user_profile`: считывает `user.role.code` для построения Pydantic-схемы профиля.
  - `_create_token_response`: зашивает `role=role_code` в JWT токен доступа и токен обновления.

### 2.2. Загрузка связей в `UserRepository` (`backend/src/auth/repository.py`)
- В методе `UserRepository.get_by_id`:
  ```python
  stmt = (
      select(UserModel)
      .options(
          joinedload(UserModel.role),
          joinedload(UserModel.client_profile),
      )
      .where(UserModel.id == user_id)
  )
  ```
- **Вывод:** Связанная роль пользователя `UserModel.role` **подгружается eager-способом (`joinedload`)** при штатной валидации токена в `get_user_by_token`. Обращение к `user.role.code` безопасно в рамках текущей сессии БД.

---

## 3. Анализ зависимостей безопасности (`backend/src/api/dependencies.py`)

### 3.1. Реализация `get_current_user` и `get_current_user_sse`
- `get_current_user`: извлекает `Bearer <token>` через `HTTPBearer(auto_error=False)` и вызывает `await auth_service.get_user_by_token(credentials.credentials)`.
- `get_current_user_sse`: извлекает токен либо из заголовка `Authorization: Bearer <token>`, либо из query-параметра `?token=<token>` (для нативного браузерного `EventSource`) и также вызывает `await auth_service.get_user_by_token(raw_token)`.
- Обе зависимости возвращают инстанс `UserModel` с подгруженной связью `user.role`.
- Для них объявлены псевдонимы типов:
  - `CurrentUserDep = Annotated[UserModel, Depends(get_current_user)]`
  - `CurrentUserSseDep = Annotated[UserModel, Depends(get_current_user_sse)]`

### 3.2. Текущие зависимости проверки ролей
- В файле присутствуют только две специфичные для оператора функции:
  - `require_operator_user(current_user: CurrentUserDep) -> UserModel`
  - `require_operator_user_sse(current_user: CurrentUserSseDep) -> UserModel`
- Для них определены:
  - `CurrentOperatorDep = Annotated[UserModel, Depends(require_operator_user)]`
  - `CurrentOperatorSseDep = Annotated[UserModel, Depends(require_operator_user_sse)]`
- Проверка в них захардкожена:
  ```python
  role_code = current_user.role.code if current_user.role else ""
  if role_code not in {
      UserRole.OPERATOR.value,
      UserRole.SUPERVISOR.value,
      UserRole.ADMIN.value,
  }:
      raise HTTPException(
          status_code=status.HTTP_403_FORBIDDEN,
          detail="Доступ разрешен только операторам поддержки",
      )
  return current_user
  ```

### 3.3. Отсутствующие зависимости и фабрики
- ❌ **Нет универсальной фабрики зависимостей** `require_role(role)` или `require_roles(*roles)`.
- ❌ **Нет зависимости для роли клиента:** `require_client_user` / `CurrentClientDep`.
- ❌ **Нет зависимости для роли руководителя/супервизора:** `require_supervisor_user` / `CurrentSupervisorDep` (для `kb` и `analytics`).
- ❌ **Нет зависимости для роли администратора:** `require_admin_user` / `CurrentAdminDep`.

### 3.4. Ошибки авторизации и формат HTTP 403 Forbidden
- **Проблема с контрактом:** Сейчас в `require_operator_user` выбрасывается:
  ```python
  HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Доступ разрешен только операторам поддержки",
  )
  ```
  Здесь `detail` — простая строка!
- **Контракт по спецификации ([API_SPECIFICATION.md](../../docs/API_SPECIFICATION.md) §1.3):**
  Все ошибки должны возвращаться в виде словаря:
  ```json
  {
    "detail": {
      "code": "access_denied",
      "message": "Недостаточно прав для выполнения данной операции"
    }
  }
  ```
- В [HACKATHON_ROADMAP.md](../../docs/HACKATHON_ROADMAP.md) (задача HIGH-13) прямо зафиксировано:
  > «При нехватке полномочий возвращается ответ `403 Forbidden` с кодом `access_denied`».

---

## 4. Аудит защищаемых маршрутов (API v1)

| Файл роутера | Эндпоинт | Метод | Текущая зависимость | Требуемые роли по спецификации | Статус аудита |
|---|---|---|---|---|---|
| `api/v1/operators.py` | `/me/shift` | GET | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/me/shift` | PATCH | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/events` | GET | `CurrentOperatorSseDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/tickets` | GET | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/tickets/{id}/open` | POST | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/tickets/{id}/messages` | POST | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/tickets/{id}/transfer` | POST | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/operators.py` | `/tickets/{id}/resolve` | POST | `CurrentOperatorDep` | `operator`, `supervisor`, `admin` | ⚠️ Защищен, но 403 отдает строку вместо словаря |
| `api/v1/kb.py` | `/documents/upload` | POST | ❌ **НЕТ** (только `KbServiceDep`) | `supervisor`, `admin` | 🔴 **Дыра безопасности!** Публичный эндпоинт загрузки файлов |
| `api/v1/kb.py` | `/documents` | GET | ❌ **НЕТ** (только `KbServiceDep`) | `supervisor`, `admin`, `operator` | 🔴 **Публичный эндпоинт!** Нет аутентификации |
| `api/v1/kb.py` | `/documents/{id}/status` | GET | ❌ **НЕТ** (только `KbServiceDep`) | `supervisor`, `admin`, `operator` | 🔴 **Публичный эндпоинт!** Нет аутентификации |
| `api/v1/kb.py` | `/documents/{id}` | DELETE | ❌ **НЕТ** (только `KbServiceDep`) | `supervisor`, `admin` | 🔴 **Дыра безопасности!** Публичное удаление документов из БД и Qdrant |
| `api/v1/kb.py` | `/nodes/{id}` | PATCH | ❌ **НЕТ** (только `KbServiceDep`) | `supervisor`, `admin` | 🔴 **Дыра безопасности!** Публичное изменение структуры узлов |
| `api/v1/analytics.py` | (все эндпоинты) | — | ❌ **Роутер пуст** | `supervisor`, `admin` | 🟡 Эндпоинты еще не созданы; роутер не защищен зависимостями |
| `api/v1/chat.py` | `/` (`get_chat_state`) | GET | `CurrentUserDep` | `client` | 🟡 Открыт для всех аутентифицированных пользователей (включая операторов/админов) |
| `api/v1/chat.py` | `/events` | GET | `CurrentUserSseDep` | `client` | 🟡 Открыт для всех аутентифицированных пользователей |
| `api/v1/chat.py` | `/messages` | POST | `CurrentUserDep` | `client` | 🟡 Открыт для всех аутентифицированных пользователей (по API_SPEC §3.2 строка 437 требуется строго `client` $\rightarrow$ иначе 403) |
| `api/v1/auth.py` | `/me` | GET | `CurrentUserDep` | Любая аутентифицированная роль | ✅ Корректно (профиль текущего пользователя) |
| `api/v1/auth.py` | `/register`, `/login`, `/refresh` | POST | Публичные | Анонимный доступ | ✅ Корректно |

---

## 5. Влияние на существующие тесты

1. **`backend/tests/operators/test_operator_events_sse.py`:**
   В тесте `test_operator_events_client_role_forbidden_403` проверяется:
   ```python
   assert "Доступ разрешен только операторам" in response.json()["detail"]
   ```
   Если `detail` станет словарём `{"code": "access_denied", "message": "..."}`, то выражение `"строка" in response.json()["detail"]` в Python вернет `False` (проверяются ключи словаря). Тест потребуется обновить для проверки `response.json()["detail"]["code"] == "access_denied"`.
2. **`backend/tests/api/test_kb_api.py`:**
   В текущих тестах фикстура `test_app` переопределяет только `get_kb_service`. Никаких заголовков авторизации тесты не передают.
   Если на эндпоинты `kb_router` навесить зависимости авторизации (`require_roles(...)`), тесты `test_kb_api.py` упадут с кодом 401 Unauthorized. При внедрении RBAC в `kb.py` потребуется добавить мок `get_current_user` в `test_app` в фикстуре `test_kb_api.py` (или передавать Bearer токен супервизора/админа).
3. **`backend/tests/chat/test_chat_events_sse.py`:**
   Тесты чата используют пользователя с ролью `client`, поэтому ограничение чата ролью `client` не сломает корректные тесты, но потребует добавления негативных тестов (оператор стучится в `/chat`).

---

## 6. Ключевые архитектурные вопросы для сессии «Grill Me»

1. **Дизайн фабрики зависимостей:**
   Реализовать универсальный класс или функцию `require_roles(*allowed_roles: UserRole | str)` с возвратом типизированной зависимости FastAPI, которая извлекает `current_user: CurrentUserDep`, сверяет `user.role.code` и выбрасывает 403 с единым телом `{"code": "access_denied", "message": "..."}`.
2. **Иерархия ролей vs Точное совпадение:**
   - Обладает ли `admin` правами на все действия (суперпользователь)? Например: разрешен ли админу доступ к операторским тикетам и к загрузке документов в KB? (В текущей спецификации: `admin` входит в операторы и супервизоры).
   - Разрешено ли оператору просматривать реестр документов `GET /api/v1/kb/documents` (для поиска нормативки) или KB полностью закрыта только для `supervisor` и `admin`?
3. **Политика доступа к клиентскому чату (`chat.py`):**
   - Строго только `UserRole.CLIENT`, либо доступен также администраторам для отладки?
4. **Защита уровня роутера vs уровня отдельных эндпоинтов:**
   - Для `kb.py`: защищать ли весь роутер `dependencies=[Depends(require_roles(...))]` или точечно вешать на каждый метод (учитывая, что на загрузку/удаление нужен `supervisor`/`admin`, а на просмотр, возможно, допускается `operator`)?
   - Для `analytics.py`: сразу повесить `dependencies=[Depends(require_roles(UserRole.SUPERVISOR, UserRole.ADMIN))]` на весь роутер.
