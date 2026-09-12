---
version: 1.0.0
name: Zakupki-Mos-ru-Design-System
description: Официальная дизайн-система платформы службы поддержки и АРМ операторов для ЕАИСТ «Портал поставщиков» (zakupki.mos.ru). Строгий утилитарный стиль B2G/B2B порталов Правительства Москвы — контрастная цветовая гамма с фирменным рубиново-красным акцентом (#db2b21), глубоким синим портальным цветом (#264b82), нейтральным светло-серым холстом (#f7f8f9), белыми карточками и прямоугольной геометрией элементов без декоративных скруглений (border-radius: 0px для кнопок, инпутов и табов). Типографика на базе Open Sans и Nunito Sans с базовым кеглем 14px.

colors:
  # Основной фирменный цвет портала (красный гербовый Москвы)
  primary: "#db2b21"
  primary-hover: "#cd1f15"
  primary-focus: "#c7160c"
  primary-active: "#af221a"
  primary-light: "#fef0ef"
  primary-border: "#db2b21"
  on-primary: "#ffffff"

  # Вторичный портальный цвет (навигация, ссылки, инфо-блоки, бренд)
  secondary-blue: "#264b82"
  secondary-blue-hover: "#1c3f72"
  secondary-blue-focus: "#163769"
  secondary-blue-active: "#1a345b"
  secondary-blue-light: "#eaf6ff"
  on-secondary-blue: "#ffffff"

  # Нейтральные темные (текст, темные кнопки)
  ink-primary: "#1a1a1a"
  ink-secondary: "#272727"
  ink-muted: "#7f8792"
  ink-disabled: "#9ba1a9"
  ink-soft: "#555555"

  # Поверхности и фоны
  canvas: "#f7f8f9"
  surface: "#ffffff"
  surface-hover: "#f2f7fc"
  surface-active: "#eaf6ff"
  surface-card: "#ffffff"
  surface-muted: "#eeeeee"
  surface-header: "#ffffff"
  surface-sidebar: "#ffffff"

  # Границы и разделители
  border: "#22242626"       # rgba(34, 36, 38, 0.15)
  border-hairline: "#e5e5e5"
  border-table: "#dddddd"
  border-divider: "#d4d4d5"
  border-input: "#d4d4d5"
  border-input-focus: "#264b82"

  # Статусные и функциональные цвета
  success: "#0d9b68"
  success-hover: "#05895a"
  success-focus: "#007f52"
  success-active: "#096c48"
  success-light: "#e7f8f2"
  on-success: "#ffffff"

  warning: "#fbbd08"
  warning-hover: "#eaae00"
  warning-active: "#cd9903"
  warning-light: "#fffbe6"
  on-warning: "#1a1a1a"

  alert-orange: "#f67319"
  alert-orange-hover: "#f66400"
  alert-orange-active: "#d45b08"
  alert-orange-light: "#fff3ec"
  on-alert-orange: "#ffffff"

  info-teal: "#167c85"
  info-teal-hover: "#0e6b74"
  info-teal-active: "#0f5359"
  info-teal-light: "#eef8f9"
  on-info-teal: "#ffffff"

  error: "#db2b21"
  error-hover: "#cd1f15"
  error-light: "#fef0ef"
  on-error: "#ffffff"

  # Выделение текста и строк
  selection-bg: "#cce2ff"
  selection-text: "#1a1a1a"
  input-selection-bg: "rgba(100, 100, 100, 0.4)"

  # Скроллбары
  scrollbar-track: "rgba(0, 0, 0, 0.1)"
  scrollbar-thumb: "rgba(0, 0, 0, 0.25)"
  scrollbar-thumb-hover: "rgba(128, 135, 139, 0.8)"

typography:
  font-family-sans: "Open Sans, system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif"
  font-family-secondary: "Nunito Sans, system-ui, -apple-system, sans-serif"
  font-family-mono: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"

  base-size: "14px"
  base-line-height: 1.42857

  h1:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "2rem"               # 28px
    fontWeight: 700
    lineHeight: 1.2857
    margin: "calc(2rem - 0.14286em) 0 1rem"
  h2:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "1.71428571rem"       # 24px
    fontWeight: 700
    lineHeight: 1.2857
    margin: "calc(1.714rem - 0.14286em) 0 0.857rem"
  h3:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "1.28571429rem"       # 18px
    fontWeight: 700
    lineHeight: 1.2857
    margin: "calc(1.285rem - 0.14286em) 0 0.642rem"
  h4:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "1.07142857rem"       # 15px
    fontWeight: 700
    lineHeight: 1.2857
  h5:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "1rem"               # 14px
    fontWeight: 700
    lineHeight: 1.2857
  body-regular:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.42857
  body-semibold:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.42857
  body-bold:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.42857
  caption:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.3333
  caption-bold:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.3333
  table-header:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.25
    textTransform: "none"
  table-cell:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.3846
  button:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.0
    textTransform: "none"
  badge:
    fontFamily: "{typography.font-family-sans}"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.0
    letterSpacing: "0.04em"

rounded:
  none: "0px"                      # Базовый радиус для кнопок, инпутов, селектов, карточек
  subtle: "1px"                    # Тосты, разделители
  sm: "2px"
  md: "4px"
  calendar-event: "5px"
  pill: "9999px"                   # Исключительно для компактных статусов, бейджей и аватаров
  scrollbar: "5px"

spacing:
  xxs: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  base: "14px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
  panel: "32px"
  section: "48px"

layout:
  container-max-widths:
    mobile: "100%"
    tablet: "723px"
    desktop-sm: "933px"
    desktop-lg: "1327px"
    desktop-wide: "1592px"
    text-reading: "700px"

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    border: "none"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    padding: "0.7857em 1.5em"       # ~11px 21px
    hover:
      backgroundColor: "{colors.primary-hover}"
      textColor: "{colors.on-primary}"
    active:
      backgroundColor: "{colors.primary-active}"
    disabled:
      opacity: 0.7
      cursor: "default"

  button-secondary-blue:
    backgroundColor: "{colors.secondary-blue}"
    textColor: "{colors.on-secondary-blue}"
    border: "none"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    padding: "0.7857em 1.5em"
    hover:
      backgroundColor: "{colors.secondary-blue-hover}"
    active:
      backgroundColor: "{colors.secondary-blue-active}"

  button-dark:
    backgroundColor: "{colors.ink-primary}"
    textColor: "#ffffff"
    border: "none"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    padding: "0.7857em 1.5em"
    hover:
      backgroundColor: "{colors.ink-secondary}"

  button-basic:
    backgroundColor: "transparent"
    textColor: "{colors.ink-primary}"
    border: "1px solid {colors.border}"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    padding: "0.7857em 1.5em"
    hover:
      backgroundColor: "#ffffff"
      borderColor: "rgba(34, 36, 38, 0.35)"
    active:
      backgroundColor: "#f8f8f8"

  button-basic-primary:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    border: "1px solid {colors.primary}"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    hover:
      backgroundColor: "{colors.primary-light}"
      borderColor: "{colors.primary-hover}"

  button-success:
    backgroundColor: "{colors.success}"
    textColor: "{colors.on-success}"
    border: "none"
    rounded: "{rounded.none}"
    typography: "{typography.button}"
    hover:
      backgroundColor: "{colors.success-hover}"
    active:
      backgroundColor: "{colors.success-active}"

  input-text:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink-primary}"
    borderColor: "{colors.border-input}"
    borderWidth: "1px"
    rounded: "{rounded.none}"
    typography: "{typography.body-regular}"
    padding: "0.6785em 1em"
    focus:
      borderColor: "{colors.border-input-focus}"
      boxShadow: "none"
    placeholderColor: "{colors.ink-muted}"

  data-table:
    backgroundColor: "#ffffff"
    borderColor: "{colors.border-table}"
    headerBackground: "#f7f8f9"
    headerTextColor: "{colors.ink-primary}"
    headerTypography: "{typography.table-header}"
    headerPadding: "10px 14px"
    rowBorderBottom: "1px solid {colors.border-table}"
    cellPadding: "10px 14px"
    cellTextColor: "{colors.ink-primary}"
    cellTypography: "{typography.table-cell}"
    rowHoverBackground: "{colors.surface-hover}"
    rowSelectedBackground: "{colors.surface-active}"

  card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border-hairline}"
    borderWidth: "1px"
    rounded: "{rounded.none}"
    padding: "16px 20px"
    boxShadow: "none"

  chat-widget:
    buttonSize: "54px x 48px"
    buttonRounded: "{rounded.none}"
    accentColor: "{colors.primary}"
    windowBorder: "1px solid {colors.border-hairline}"
    windowShadow: "0 4px 16px rgba(0, 0, 0, 0.12)"
    headerBackground: "{colors.secondary-blue}"
    headerTextColor: "#ffffff"
    clientBubbleBg: "#eaf6ff"
    clientBubbleText: "{colors.ink-primary}"
    operatorBubbleBg: "#ffffff"
    operatorBubbleText: "{colors.ink-primary}"
    operatorBubbleBorder: "1px solid {colors.border-hairline}"

  toast-notification:
    rounded: "{rounded.subtle}"
    boxShadow: "0 1px 10px rgba(0,0,0,0.1), 0 2px 15px rgba(0,0,0,0.05)"
    minHeight: "64px"
    padding: "8px 12px"
    typography: "{typography.body-regular}"
---

# Дизайн-система «Портал поставщиков» (zakupki.mos.ru)

> **Статус:** Обязательный стандарт визуального интерфейса проекта.  
> **Основа:** Исследование стилей портала `zakupki.mos.ru` (`main.css`, `semantic-pp-main-theme.min.css`).  
> **Сфера применения:** Публичный виджет чата поддержки клиентов, АРМ оператора первой/второй линий, аналитический дашборд руководителя, каталог базы знаний и регламентов.

---

## 1. Архитектурные принципы и философия дизайна

1. **Государственная строгость и деловой B2B/B2G стиль:**
   Никаких «мультяшных» скруглений (`rounded-3xl`), неоновых свечений, фиолетовых градиентов или кислотных цветов. Интерфейс должен выглядеть как монолитный, надежный рабочий инструмент закупщика и поставщика города Москвы.

2. **Прямоугольная геометрия контролов (`rounded: 0px`):**
   Кнопки, поля ввода, выпадающие списки, вкладки (табы), панели и карточки имеют **прямые углы** (`border-radius: 0`). Скругления допускаются только для:
   - Статусных таблеток-бейджей (pill `rounded-full`);
   - Аватаров пользователей (`rounded-full`);
   - Скроллбаров (`border-radius: 5px`);
   - Всплывающих Toast-уведомлений (`border-radius: 1px`).

3. **Базовый масштаб (14px):**
   Корневой размер шрифта браузера зафиксирован на `14px` (`html { font-size: 14px }`), что обеспечивает повышенную информационную плотность (data density), критически важную для АРМ оператора и таблиц закупки. `1rem = 14px`.

4. **Высокий контраст и чистый холст:**
   Фон страниц — нейтральный светло-серый `#f7f8f9`. Рабочие области, карточки и списки — чистый белый `#ffffff`. Основной текст — графитовый черный `#1a1a1a` с высокой контрастностью по WCAG AAA.

5. **Цветовые якоря Правительства Москвы:**
   - **Красный `#db2b21` (Mos Red):** главный призыв к действию (CTA), ключевые операции («Отправить заявку», «Принять в работу»), индикаторы критических ошибок и деструктивные действия.
   - **Синий `#264b82` (Mos Navy/Blue):** вторичные действия, информационные панели, кликабельные ссылки, шапка системы, фильтры и активные элементы выбора.
   - **Зеленый `#0d9b68` (Success):** статус «На линии», успешно завершенные тикеты, положительные отметки качества, согласования.

---

## 2. Цветовая палитра и дизайн-токены

### 2.1. Основные и бренд-цвета
| Токен | Значение | Описание / Применение |
|---|---|---|
| `--color-primary` | `#db2b21` | Основной красный цвет портала Москвы. Главные кнопки, акценты. |
| `--color-primary-hover` | `#cd1f15` | Hover-состояние главной кнопки. |
| `--color-primary-focus` | `#c7160c` | Focus-состояние главной кнопки. |
| `--color-primary-active`| `#af221a` | Нажатая главная кнопка. |
| `--color-primary-light` | `#fef0ef` | Мягкая подсветка ошибок и предупреждений. |
| `--color-blue` | `#264b82` | Портальный синий цвет. Ссылки, навигация, фильтры, карточки. |
| `--color-blue-hover` | `#1c3f72` | Наведение на синие кнопки и ссылки. |
| `--color-blue-active` | `#1a345b` | Активное нажатие на синие кнопки. |
| `--color-blue-light` | `#eaf6ff` | Фоновая подсветка выбранных строк таблиц и сообщений клиента. |

### 2.2. Нейтральные цвета и поверхности
| Токен | Значение | Описание / Применение |
|---|---|---|
| `--color-canvas` | `#f7f8f9` | Фоновый цвет страниц, рабочей области бэк-офиса. |
| `--color-surface` | `#ffffff` | Карточки, модальные окна, списки, поля ввода. |
| `--color-surface-hover` | `#f2f7fc` | Наведение на строки таблиц и карточки тикетов. |
| `--color-ink` | `#1a1a1a` | Основной текст, заголовки, активные иконки. |
| `--color-ink-muted` | `#7f8792` | Вторичный текст, метаданные, плейсхолдеры, время. |
| `--color-ink-subtle` | `#9ba1a9` | Неактивные иконки, подсказки. |
| `--color-border` | `rgba(34, 36, 38, 0.15)` | Стандартная граница карточек, кнопок и панелей. |
| `--color-border-hairline`| `#e5e5e5` | Разделительные тонкие линии и границы карточек. |
| `--color-border-table`| `#dddddd` | Границы строк и колонок таблиц данных. |

### 2.3. Семантические статусы
| Статус | Основной цвет | Светлый фон | Применение в техподдержке |
|---|---|---|---|
| **Успех / На линии** | `#0d9b68` (hover: `#05895a`) | `#e7f8f2` | Оператор свободен, тикет решен, бот дал ответ. |
| **Ожидание / Внимание** | `#fbbd08` (hover: `#eaae00`) | `#fffbe6` | Тикет в очереди, тайм-аут ожидания клиента. |
| **Оповещение / Линия 2**| `#f67319` (hover: `#f66400`) | `#fff3ec` | Эскалация, критический баг портала, приоритет. |
| **Ошибка / Блокировка**| `#db2b21` (hover: `#cd1f15`) | `#fef0ef` | Нецензурная лексика, сбой авторизации, штраф QA. |
| **Информация / Бот** | `#167c85` (hover: `#0e6b74`) | `#eef8f9` | Подсказка RAG-копилота, цитата из регламента. |

---

## 3. Типографика

### 3.1. Шрифтовой стек
- **Основной шрифт интерфейса:** `Open Sans, system-ui, -apple-system, Segoe UI, Roboto, sans-serif`.
- **Вспомогательный шрифт таблиц и форм:** `Nunito Sans, system-ui, -apple-system, sans-serif`.
- **Моноширинный шрифт (ID тикетов, коды ошибок, JSON, логи):** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`.

### 3.2. Масштабная сетка заголовков и текстов
Базовая единица `1rem = 14px`.

| Уровень | Размер (rem / px) | Начертание | Высота строки | Межбуквенный интервал |
|---|---|---|---|---|
| **h1** | `2.000rem` (28px) | Bold (700) | `1.2857` (36px) | Normal (0) |
| **h2** | `1.714rem` (24px) | Bold (700) | `1.2857` (31px) | Normal (0) |
| **h3** | `1.285rem` (18px) | Bold (700) | `1.2857` (23px) | Normal (0) |
| **h4** | `1.071rem` (15px) | Bold (700) | `1.2857` (19px) | Normal (0) |
| **h5** | `1.000rem` (14px) | Bold (700) | `1.2857` (18px) | Normal (0) |
| **Body Default** | `1.000rem` (14px) | Regular (400) | `1.4285` (20px) | Normal (0) |
| **Body Semibold**| `1.000rem` (14px) | SemiBold (600)| `1.4285` (20px) | Normal (0) |
| **Caption** | `0.857rem` (12px) | Regular (400) | `1.3333` (16px) | Normal (0) |
| **Caption Bold** | `0.857rem` (12px) | Bold (700) | `1.3333` (16px) | `0.02em` |
| **Micro Badge** | `0.785rem` (11px) | Bold (700) | `1.0000` (11px) | `0.05em` UPPERCASE |

---

## 4. Спецификация UI-компонентов

### 4.1. Кнопки (`.ui.button`)
Все кнопки прямоугольные (`rounded-none` / `border-radius: 0`), шрифт `Open Sans 700`, текст в одну строку (`whitespace-nowrap`).

- **Primary Button (Красная):**
  - Классы: `bg-[#db2b21] hover:bg-[#cd1f15] active:bg-[#af221a] text-white font-bold text-[14px] px-6 py-2.5 rounded-none transition-colors`
  - Применение: «Отправить», «Взять тикет», «Завершить сессию», «Вопрос решен».
- **Secondary Blue Button (Синяя):**
  - Классы: `bg-[#264b82] hover:bg-[#1c3f72] active:bg-[#1a345b] text-white font-bold text-[14px] px-6 py-2.5 rounded-none transition-colors`
  - Применение: «Найти в базе знаний», «Позвать специалиста», «Экспорт отчета».
- **Basic / Outline Button (Контурная):**
  - Классы: `bg-transparent hover:bg-white text-[#1a1a1a] border border-[#22242626] hover:border-[#22242659] active:bg-[#f8f8f8] font-bold text-[14px] px-5 py-2.5 rounded-none transition-all`
  - Применение: «Отмена», «Фильтры», «Вторичные действия».
- **Toggle Active Button (Зеленая «На линии»):**
  - Классы: `bg-[#0d9b68] hover:bg-[#05895a] text-white font-bold text-[14px] px-5 py-2 rounded-none`
  - Применение: статус оператора «На смене / Принимаю обращения».
- **Button Group (Слитная группа кнопок):**
  - Соседние кнопки примыкают встык с отрицательным марджином `margin-left: -1px`, образуя строгую единую панель переключения режимов (например: `[Все] [Мои тикеты] [Очередь] [Архив]`).

### 4.2. Поля ввода и селекты (`.ui.input`, `.ui.form`)
- **Текстовое поле (Input / Textarea):**
  - Высота: `38px` (для однострочных полей).
  - Стили: `bg-white text-[#1a1a1a] border border-[#d4d4d5] rounded-none px-3 py-2 text-[14px] outline-none focus:border-[#264b82] transition-colors placeholder:text-[#7f8792]`
  - Поле с ошибкой: `border-[#db2b21] focus:border-[#cd1f15] bg-[#fef0ef]/30`
- **Выпадающий список (Select / Dropdown):**
  - Прямоугольная рамка, четкий контрастный шеврон, меню выпадает строго под полем без радиусов скругления с легкой тенью `shadow-md border border-[#ddd]`.

### 4.3. Таблицы данных (Реестры тикетов, история, аудит)
- **Шапка таблицы (`thead`):**
  - Фон: `#f7f8f9`
  - Текст: `text-[#1a1a1a] font-bold text-[13px] border-b border-[#dddddd] px-3.5 py-2.5 text-left select-none`
  - Сортируемые колонки имеют иконку стрелки с `cursor-pointer hover:bg-[#eef1f4]`.
- **Строки таблицы (`tbody tr`):**
  - Границы: `border-b border-[#dddddd]`
  - Высота строки: `44px`
  - Ячейки: `px-3.5 py-2.5 text-[13px] text-[#1a1a1a] align-middle`
  - При наведении (Hover): `hover:bg-[#f2f7fc] transition-colors`
  - Выбранная строка (Selected / Active): `bg-[#eaf6ff] border-l-4 border-l-[#264b82]`

### 4.4. Карточки и рабочие панели
- Фон: `#ffffff`
- Границы: `border border-[#e5e5e5]` (или `border border-[#22242626]`)
- Скругление: `rounded-none`
- Тени: плоский дизайн (flat). Допускается только минимальная дискретная тень `shadow-[0_1px_3px_rgba(0,0,0,0.06)]`.

### 4.5. Статусные индикаторы и бейджи (Pill)
Единственный элемент со скруглением `rounded-full` для мгновенного считывания состояния:
- **«Новое / В очереди»:** `bg-[#fffbe6] text-[#b7791f] border border-[#fbbd08]/40 text-[11px] font-bold px-2.5 py-0.5 rounded-full`
- **«В работе у оператора»:** `bg-[#eaf6ff] text-[#264b82] border border-[#264b82]/30 text-[11px] font-bold px-2.5 py-0.5 rounded-full`
- **«Решено ИИ-ботом»:** `bg-[#e7f8f2] text-[#0d9b68] border border-[#0d9b68]/30 text-[11px] font-bold px-2.5 py-0.5 rounded-full`
- **«Закрыто / Нарушение»:** `bg-[#fef0ef] text-[#db2b21] border border-[#db2b21]/30 text-[11px] font-bold px-2.5 py-0.5 rounded-full`

---

## 5. Спецификация зон системы поддержки

### 5.1. Клиентский веб-чат поддержки (Портальный стиль)
- **Плавающая кнопка открытия чата:**
  - Размеры: `54px` (высота) × `48px` (ширина), прижата к нижнему углу экрана (стиль `#chat-widget__button--expand`).
  - Фон: `#db2b21` с официальной белой иконкой диалога.
  - Без скруглений (`rounded-none`).
- **Окно диалога (Chat Window):**
  - Шапка: глубокий синий цвет `#264b82`, логотип Портала поставщиков, заголовок «Служба поддержки ЕАИСТ», статус бота («Онлайн») и кнопка сворачивания.
  - Тело чата: фон `#f7f8f9`.
  - **Сообщения клиента:** прижаты вправо, фон `#eaf6ff`, граница `border border-[#b9dbf7]`, текст `#1a1a1a`, скругление `rounded-none` (или строгий `rounded-[2px]`).
  - **Сообщения бота / оператора:** прижаты влево, фон `#ffffff`, граница `border border-[#e5e5e5]`, текст `#1a1a1a`.
  - **Интерактивные кнопки под ответом бота:** прямоугольные контурные кнопки `[Вопрос решен]` (зеленая обводка) и `[Позвать специалиста]` (синяя обводка).
  - **Системные плашки:** по центру, капс, `text-[11px] text-[#7f8792] py-1 px-3 bg-[#e5e7eb] rounded-none`.

### 5.2. АРМ Оператора (Рабочее место специалиста)
- **Сетка экрана:** Трехколоночный интерфейс максимальной информационной плотности:
  1. **Левая колонка (280–320px) — Список очереди и активных тикетов:**
     - Верхняя панель: статус оператора («На линии» / «Перерыв» / «Не в сети») и счетчик свободных слотов `3/5`.
     - Карточки тикетов в списке: компактные, разделенные `border-b border-[#e5e5e5]`, активный тикет подсвечен синей плашкой `#eaf6ff` и левым бордером `border-l-4 border-l-[#264b82]`.
  2. **Центральная колонка (flex-1) — Активный диалог:**
     - Шапка: ФИО клиента, организация, ИНН, номер закупки (если привязана), таймер неактивности (AFK).
     - Лента переписки с бесконечной прокруткой и системными разделителями прошлых сессий.
     - Поле ввода с кнопкой отправки, прикрепления файлов и шаблонов быстрых ответов.
  3. **Правая колонка (340–380px) — AI Copilot и База Знаний:**
     - Шапка: «ИИ-Ассистент оператора (RAG)».
     - Карточка автоматической суммаризации проблемы клиента.
     - Рекомендованные статьи регламентов с кнопками `[Вставить в ответ]` и `[Открыть регламент]`.
     - Кнопка эскалации: `[Перевести на 2-ю линию]`.

### 5.3. Аналитический дашборд руководителя (Back-office)
- **KPI-карточки (Метрики):**
  - Белые прямоугольные карточки с тонкой рамкой `border border-[#e5e5e5]`.
  - Крупные цифры `text-[32px] font-bold text-[#1a1a1a]`.
  - Лейблы параметров: `text-[12px] font-semibold text-[#7f8792] uppercase`.
  - Процентные тренды: зеленый `+4.2%` (`#0d9b68`) или красный `-1.8%` (`#db2b21`).
- **Графики и диаграммы:**
  - Цветовая шкала линий и столбцов: `#264b82` (синий), `#db2b21` (красный), `#0d9b68` (зеленый), `#f67319` (оранжевый), `#167c85` (тиловый).
  - Сетка графика: пунктир `#e5e5e5`.

---

## 6. Адаптивность и брейкпоинты

Интерфейс строго оптимизирован под экраны операторов (1920×1080, 1440×900, 1366×768) и мобильные устройства пользователей портала:

| Брейкпоинт | Мин. ширина | Особенности отображения |
|---|---|---|
| **Mobile (`< 768px`)** | 320px | Чат разворачивается на полный экран (`w-full h-dvh`). АРМ оператора сворачивает боковые колонки в выдвижные меню (Drawer). |
| **Tablet (`768px - 991px`)** | 723px контейнер | Двухколоночный режим. Правая колонка подсказок прячется в аккордеон. |
| **Desktop Small (`992px - 1399px`)** | 933px контейнер | Полноценный трехколоночный АРМ с компактными отступами. |
| **Desktop Large (`>= 1400px`)** | 1327px контейнер | Стандартное рабочее место оператора с развернутыми деталями базы знаний. |

---

## 7. Конфигурация Tailwind CSS (Интеграция в проект)

Для применения стилей в проекте файл `frontend/tailwind.config.js` конфигурируется следующими токенами:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        mos: {
          red: {
            DEFAULT: '#db2b21',
            hover: '#cd1f15',
            focus: '#c7160c',
            active: '#af221a',
            light: '#fef0ef',
          },
          blue: {
            DEFAULT: '#264b82',
            hover: '#1c3f72',
            focus: '#163769',
            active: '#1a345b',
            light: '#eaf6ff',
          },
          ink: {
            DEFAULT: '#1a1a1a',
            secondary: '#272727',
            muted: '#7f8792',
            disabled: '#9ba1a9',
          },
          canvas: '#f7f8f9',
          surface: '#ffffff',
          border: 'rgba(34, 36, 38, 0.15)',
          hairline: '#e5e5e5',
          table: '#dddddd',
          success: {
            DEFAULT: '#0d9b68',
            hover: '#05895a',
            active: '#096c48',
            light: '#e7f8f2',
          },
          warning: {
            DEFAULT: '#fbbd08',
            hover: '#eaae00',
            light: '#fffbe6',
          },
          alert: {
            DEFAULT: '#f67319',
            hover: '#f66400',
            light: '#fff3ec',
          }
        }
      },
      fontFamily: {
        sans: ['Open Sans', 'system-ui', '-apple-system', 'sans-serif'],
        secondary: ['Nunito Sans', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        'none': '0px',
        'subtle': '1px',
        'sm': '2px',
        'md': '4px',
      },
      maxWidth: {
        'portal-lg': '1327px',
        'portal-md': '933px',
        'portal-sm': '723px',
      }
    },
  },
  plugins: [],
}
```

---

## 8. Чек-лист проверки соответствия дизайну (Do's and Don'ts)

### ✅ ОБЯЗАТЕЛЬНО (Do's)
- Использовать `rounded-none` для всех стандартных кнопок, инпутов, селектов, карточек и вкладок.
- Красный цвет (`#db2b21`) использовать **строго** для одного главного целевого действия на экране (One Primary Action).
- Синий цвет (`#264b82`) применять для ссылок, вторичных действий и ключевых фильтров.
- Держать базовый размер шрифта `14px` для поддержания профессиональной плотности информации.
- Обеспечивать визуальный отклик при наведении на интерактивные строки таблиц (`hover:bg-[#f2f7fc]`).
- Всегда явно указывать состояние курсора (`cursor-pointer` для кликабельного, `cursor-not-allowed` для заблокированного).

### ❌ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО (Don'ts)
- ❌ Никаких скруглений `rounded-xl`, `rounded-2xl`, `rounded-3xl` у кнопок и карточек — это ломает стиль портала Москвы.
- ❌ Никаких градиентов фиолетового, розового или неонового цветов ("AI slop").
- ❌ Никаких размытых цветных теней (`shadow-primary/50` или разноцветный glow).
- ❌ Не использовать дефолтные синие цвета Tailwind (`bg-blue-600` / `#2563eb`), вместо них использовать портальный Mos Navy `#264b82`.
- ❌ Не ставить `div` с `onClick` вместо семантического `<button>`.
- ❌ Не использовать случайные отступы вне шага 4px/8px/12px/16px/24px.
