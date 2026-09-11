**Core**

* **React + TypeScript** — макс. объем обучающих данных у моделей, типизация дает агенту самопроверку компилятором.
* **Vite** — сборщик. SPA поверх отдельного FastAPI-бэкенда без SEO/SSR (для публичных лендингов заменяется на Next.js App Router).
* **Biome** — линт + форматирование одним инструментом вместо ESLint+Prettier. Один конфиг, быстрее, агенту проще не путаться.

**API & Data**

* **TanStack Query** — кэш и состояние запросов к бэкенду.
* **Orval** — автоматическая генерация типизированного клиента и хуков TanStack Query из OpenAPI-схемы FastAPI (`/openapi.json`). Без ручного написания.

**UI & 2D Animations**

* **Tailwind CSS v4** — стили внутри компонента. В v4 конфиг не в `tailwind.config.js`, а в CSS через `@theme` (указать агенту, чтобы не сгенерил v3-конфиг).
* **shadcn/ui** — готовые компоненты копируются в код, актуальная версия под Tailwind v4 (важен явный выбор Base UI vs Radix через флаг `-b radix` или `-b base` в CLI).
* **lucide-react** — иконки.
* **motion** (импорт `from "motion/react"`) — анимации. Бывший `framer-motion` (переименован в 2025-м), агенту нужно явно указать актуальный импорт.

**Interactive 3D (WebGL)**

* **React Three Fiber** — обертка на Three.js. Декларативное описание 3D-сцены через React-компоненты.
* **Drei** — набор готовых абстракций (камеры, контролы, загрузчики моделей, окружение) для React Three Fiber.
* **React Postprocessing** — визуальные эффекты постобработки (размытие, хроматическая аберрация, bloom, глитч).
* **PBR-материалы** — физически корректный рендеринг. Для реализма использовать текстурные карты (а не процедурные материалы).
* **Perlin Noise (Шум Перлина)** — генерация псевдослучайных текстур для органических эффектов (туман, деформация сетки).



**Ready-Made Animated Components & Interactive 3D (Готовые анимированные и 3D экосистемы)**

* **Aceternity UI** — ведущая коллекция готовых "wow"-компонентов на React + Tailwind + Motion + Three.js (Background Beams, Globe, Canvas Reveal Effect, Sparkles, Lamp, Tracing Beam, Card Hover Effects). Код копируется в проект без тяжелых библиотек.
* **Magic UI** — готовая библиотека анимированных компонентов для стартап и корпоративных лендингов (Globe, Orbiting Circles, Particles, Retro Grid, Animated Beam, Marquee).
* **react-bits (`reactbits.dev`)** — библиотека премиальных текстовых эффектов (BlurText, SplitText, ShinyText), занимающая 2-е место в JS Rising Stars 2025. Интегрируется напрямую через `npx shadcn add`.
* **Motion Primitives** — расширение для `shadcn/ui` с готовыми анимированными микро-взаимодействиями на базе `motion` (Morphing Dialog, Text Effect, Animated Group).
* **Spline (`@splinetool/react-spline`)** — готовые интерактивные 3D-сцены с физикой и анимациями, экспортируемые напрямую из браузерного 3D-редактора в React-компоненты.
* **Rive (`@rive-app/react-canvas`)** — интерактивные векторные анимации на стейт-машинах реального времени (замена Lottie с высокой производительностью и низким потреблением CPU).

**Ready-Made Shaders & WebGL Effects (Готовые шейдеры и эффекты)**

* **Drei Shader Materials** (`MeshTransmissionMaterial`, `MeshWobbleMaterial`, `MeshDistortMaterial`, `MeshReflectorMaterial`, `Sparkles`, `Float`) — готовые шейдерные материалы из библиотеки Drei для React Three Fiber (стекло, преломление света, размытые отражения, деформации).
* **Fluid Simulation & Shader Gradients** — готовые Canvas/WebGL-компоненты для интерактивных жидкостных фонов и размытых градиентов с реакцией на движение курсора мыши.

**Orchestration & Page Transitions (Оркестровка анимаций и прокрутка)**

* **Lenis** — плавная прокрутка (программно управляемая интерполяция скролла). Нормализует прокрутку между устройствами и синхронизируется с GSAP без блокировки главного потока браузера.
* **View Transitions API (Native)** — встроенный браузерный интерфейс для бесшовных переходов между страницами и состояниями элементов (Shared Element Transitions), выполняемый на композитинговом потоке браузера.
* **GSAP + ScrollTrigger + Flip** — инструмент для сложных временных шкал (timelines), оркестровки анимаций при скролле и сложной реорганизации DOM-элементов по методологии FLIP (First, Last, Invert, Play).

**Model Context Protocol (MCP) Servers**

* **`shadcn MCP`** — официальный первопартийный MCP-сервер (`ui.shadcn.com/docs/mcp`) для поиска, инспекции и автоматической установки компонентов через CLI.
* **`21st MCP`** — официальный MCP-сервер от `21st.dev` для прямого поиска и генерации UI-компонентов по промпту (например, `/ui create navbar`) внутри Cursor, Claude Code или Windsurf.
* **`figma-mcp`** — MCP-сервер для считывания макетов Figma, слоев, токенов дизайна (цветов, отступов) и автоматической трансляции их в Tailwind CSS и motion-компоненты.
* **`context7` / Docs MCP** — предоставление ИИ-агенту актуальной контекстной документации и сигнатур типов для Three.js, WebGPU, GSAP, Motion, Rive и Spline.
* **`chrome-devtools-mcp`** — официальный MCP от Google для глубокой отладки производительности, снятия Performance Trace и проверки Core Web Vitals (LCP/INP/CLS) в активной сессии Chrome без сброса авторизации.
* **`playwright`** — визуальный аудит интерфейса агентом (снятие скриншотов и детерминированные E2E-тесты).

**Agent Skills (Навыки ИИ-агента)**

* **`impeccable`** — мета-скилл и фреймворк дизайн-наставничества (23 специализированные команды `/impeccable init`, `audit`, `polish`, `critique`, `harden` и др.), предотвращающий шаблонный AI-дизайн, задающий жесткий пол качества (Craft Floor), цветовую стратегию, типографику, адаптивность и генерирующий спецификации `PRODUCT.md` / `DESIGN.md`.
* **`frontend-design`** — официальный навык для генерации оригинального, стильного корпоративного дизайна (выбор цветовых палитр, эффекты стекла, типографика, микро-взаимодействия без банальных шаблонов).
* **`ui-ux-pro-max`** — навык проектирования качественных дизайн-систем, предотвращающий генерирование шаблонного "AI-дизайна" (50+ стилей, 97 палитр, 57 шрифтовых пар).
* **`shadcn`** — официальный навык композиции Tailwind v4 и компонентов shadcn/ui.
* **`emilkowalski-animation-skill`** (`emilkowalski/skills`) — набор навыков дизайн-инжиниринга и микро-анимаций от Эмиля Ковальски (Vercel, Linear) для точной настройки кривых Безье, длительностей (`duration`), жестов и физики движения в `motion` / React Native.
* **`shader-expert-skill`** — правила генерации GPU-шейдеров, работы с юниформами и обязательной очистки видеопамяти через Dispose pattern (шаблон явного освобождения VRAM при размонтировании 3D-компонента).
* **`scroll-orchestration-skill`** — паттерны бесшовного связывания Lenis + GSAP ScrollTrigger + R3F Canvas без дёрганий (jank) и рассинхронизации кадровой частоты.

**Top 10 AI-Native Design & Animation Reference Platforms (Топ-10 площадок для ИИ-разработки и референсов)**

* **21st.dev (`21st.dev`)** — "Dribbble для инженеров" и главная открытая маркетплейс-галерея React/Tailwind компонентов. Каждая модель/блок имеет кнопку быстрого копирования промпта для интеграции напрямую в ИИ-агенты (Claude Code, Cursor).
* **v0.dev (`v0.dev`)** — ИИ-сервис от Vercel для генерации полноценных React + Tailwind + shadcn/ui интерфейсов и UI-блоков по текстовому описанию или скриншоту-референсу.
* **Shadcnblocks (`shadcnblocks.com`)** — крупнейший бесплатный каталог готовых блоков веб-страниц (Hero, Features, Pricing, Testimonials, Footers), полносверстанных под экосистему `shadcn/ui`.
* **Uiverse (`uiverse.io`)** — бесплатное открытое сообщество стилизованных элементов интерфейса (кнопки, карточки, формы, переключатели) с уникальными CSS/Tailwind микро-анимациями.
* **Hover.dev (`hover.dev`)** — специализированный каталог анимированных UI-компонентов и блоков с акцентом на кинетическую типографику, реакцию на курсор и сложную динамику на базе `motion`.
* **Aceternity UI (`ui.aceternity.com`)** — главная коллекция "wow"-компонентов с 3D-фонами, шейдерами и физическими эффектами свечения для премиальных лендингов.
* **Magic UI (`magicui.design`)** — библиотека анимированных компонентов для маркетинг-страниц (Globe, Orbiting Circles, Particles, Animated Beams), полностью совместимая с `shadcn/ui`.
* **UI Ball (`ldrs.uiball.com`)** — библиотека легких открытых SVG/CSS индикаторов загрузки (spinners/loaders) для микро-интенсивных интерактивов.
* **Relume (`relume.io`)** — ИИ-платформа для генерации карт сайтов, сеток и компоновочных блоков интерфейсов, используемая для сборки каркаса перед скармливанием агенту.
* **Fontshare (`fontshare.com`)** — бесплатный сервис шрифтов от Indian Type Foundry для быстрого выбора дизайнерских вариативных шрифтов и настройки типографики в Tailwind.


https://getdesign.md/

---

### **Инструкция: Извлечение AI-промптов и кода с 21st.dev без регистрации**

Платформа `21st.dev` блокирует кнопку копирования готового промпта авторизацией и платным API-ключом, однако сам код компонентов распространяется под открытыми лицензиями (MIT) и доступен бесплатно. Ниже описаны способы получения полных промптов без сторонних сервисов и расширений.

#### **1. Браузерная закладка в 1 клик (Букмарклет / Bookmarklet)**
Создайте на панели закладок браузера (`Ctrl + Shift + B`) новую закладку и укажите в поле URL следующий код:

```javascript
javascript:(async function(){try{const p=window.location.pathname;const t=document.querySelector('title')?.innerText.split('|')[0].trim()||'Component';const d=document.querySelector('meta[name="description"]')?.content||'';let deps='clsx tailwind-merge';try{const r=await fetch(window.location.origin+p+'.md');if(r.ok){const txt=await r.text();const m=txt.match(/npm dependencies:\s*(.*)/i);if(m)deps=m[1].trim()+' clsx tailwind-merge';}}catch(e){}let code='';const cdn=document.documentElement.innerHTML.match(/https:\/\/cdn\.21st\.dev\/[^\s"',\\]+\.tsx/);if(cdn){try{const cr=await fetch(cdn[0]);if(cr.ok)code=await cr.text();}catch(e){}}if(!code){const pres=Array.from(document.querySelectorAll('pre, code')).map(el=>el.innerText.trim()).filter(x=>x.length>80);if(pres.length)code=pres[0];}const res=`# Component: ${t}\n> ${d}\n\n### 1. Dependencies\n\`\`\`bash\nnpm install ${deps}\n\`\`\`\n\n### 2. Utility (lib/utils.ts)\n\`\`\`typescript\nimport { ClassValue, clsx } from "clsx";\nimport { twMerge } from "tailwind-merge";\nexport function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }\n\`\`\`\n\n### 3. Component Code\n\`\`\`tsx\n${code||'// Source code'}\n\`\`\``;await navigator.clipboard.writeText(res);alert('✅ Готовый AI-промпт скопирован в буфер обмена!');}catch(err){alert('Ошибка: '+err.message);}})();
```

* **Использование:** Откройте любую страницу с компонентом на `21st.dev` и нажмите на закладку. Скрипт сам заберет зависимости, подтянет открытый TSX-код с CDN и скопирует структурированный промпт в буфер обмена.

#### **2. Прямой Markdown-эндпоинт (.md)**
Добавьте `.md` в конец любого URL компонента:
* `https://21st.dev/@manuarora700/components/floating-dock.md`
* Отдаёт метаданные, теги и точный список необходимых npm-пакетов без авторизации.

#### **3. Первоисточники библиотек (Upstream)**
Все авторы на `21st.dev` ведут свои открытые каталоги, где полный код доступен для копирования напрямую:
* `@manuarora700` → [Aceternity UI](https://ui.aceternity.com)
* `@dillionverma` → [Magic UI](https://magicui.design)
* `@originui` → [Origin UI](https://originui.com)
* `@cult-ui` → [Cult UI](https://cult-ui.com)