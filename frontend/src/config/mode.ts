/**
 * Управление режимом работы фронтенда:
 * - Standalone (автономный визуальный режим без API и БД)
 * - Backend API (работа с реальным сервером FastAPI и базой данных)
 */

const STORAGE_STANDALONE_KEY = 'portal_standalone_mode';
const MODE_CHANGE_EVENT = 'portal_mode_changed';

/**
 * Проверяет, активирован ли автономный (standalone) режим.
 * Приоритет проверки:
 * 1. URL-параметр: ?standalone=true|false или ?mode=standalone|api
 * 2. Сохраненное значение в localStorage (если пользователь переключил в UI)
 * 3. Переменная окружения сборки VITE_STANDALONE (из .env.standalone или CLI)
 */
export function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') {
    return import.meta.env.VITE_STANDALONE === 'true' || import.meta.env.VITE_STANDALONE === '1';
  }

  // 1. Проверка URL-параметров
  const params = new URLSearchParams(window.location.search);
  const standaloneParam = params.get('standalone');
  if (standaloneParam !== null) {
    return standaloneParam === 'true' || standaloneParam === '1';
  }
  const modeParam = params.get('mode');
  if (modeParam !== null) {
    if (modeParam.toLowerCase() === 'standalone' || modeParam.toLowerCase() === 'mock') return true;
    if (modeParam.toLowerCase() === 'api' || modeParam.toLowerCase() === 'backend') return false;
  }

  // 2. Проверка localStorage
  const saved = localStorage.getItem(STORAGE_STANDALONE_KEY);
  if (saved !== null) {
    return saved === 'true';
  }

  // 3. Флаг из Vite env
  const envVal = import.meta.env.VITE_STANDALONE;
  return envVal === 'true' || envVal === '1';
}

/**
 * Устанавливает или переключает режим в рантайме с сохранением в localStorage
 */
export function setStandaloneMode(standalone: boolean): void {
  try {
    localStorage.setItem(STORAGE_STANDALONE_KEY, String(standalone));
    window.dispatchEvent(new CustomEvent(MODE_CHANGE_EVENT, { detail: { standalone } }));
  } catch (err) {
    console.warn('Не удалось сохранить режим в localStorage:', err);
  }
}

/**
 * Сбрасывает переопределение из localStorage и возвращает к значению из переменной окружения
 */
export function resetStandaloneMode(): void {
  try {
    localStorage.removeItem(STORAGE_STANDALONE_KEY);
    window.dispatchEvent(new CustomEvent(MODE_CHANGE_EVENT, {
      detail: { standalone: isStandaloneMode() },
    }));
  } catch {}
}

/**
 * Подписка на изменение режима работы фронтенда
 */
export function onModeChange(callback: (standalone: boolean) => void): () => void {
  const handler = (e: Event) => {
    const custom = e as CustomEvent<{ standalone: boolean }>;
    callback(custom.detail?.standalone ?? isStandaloneMode());
  };

  window.addEventListener(MODE_CHANGE_EVENT, handler);
  return () => {
    window.removeEventListener(MODE_CHANGE_EVENT, handler);
  };
}
