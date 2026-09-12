import { AuthTokens, UserProfile, UserRole } from '../types/auth';
import { isStandaloneMode } from '../config/mode';
import { generateMockAuthTokens } from './mockData';

const TOKEN_KEY = 'portal_auth_tokens';
const USER_KEY = 'portal_auth_user';

export interface DemoUserConfig {
  role: UserRole;
  title: string;
  badge: string;
  lineCode?: 'L1' | 'L2' | 'L3';
  email: string;
  name: string;
  company: string;
  inn: string;
  description: string;
  defaultPassword?: string;
}

export const DEMO_USERS: DemoUserConfig[] = [
  {
    role: 'client',
    title: 'Поставщик',
    badge: 'Клиент',
    email: 'supplier@example.com',
    name: 'Иванов Иван Иванович',
    company: 'ООО «ТехноСнаб Поставка»',
    inn: '7701234567',
    description: 'Подача оферт, котировочные сессии и чат с ИИ/поддержкой',
    defaultPassword: 'password123',
  },
  {
    role: 'operator',
    title: 'Оператор L1',
    badge: '1-я линия',
    lineCode: 'L1',
    email: 'operator1@example.com',
    name: 'Смирнова Анна Сергеевна',
    company: 'Первая линия поддержки',
    inn: '7709876541',
    description: 'Регламенты закупок, классификатор СПГЗ, выгрузка YML-прайсов',
    defaultPassword: 'password123',
  },
  {
    role: 'operator',
    title: 'Оператор L2',
    badge: '2-я линия',
    lineCode: 'L2',
    email: 'operator2@example.com',
    name: 'Кузнецов Петр Васильевич',
    company: 'Вторая линия поддержки',
    inn: '7709876542',
    description: 'КриптоПро CSP, ошибки ЭЦП, валидация УПД и шлюзы ЭДО',
    defaultPassword: 'password123',
  },
  {
    role: 'operator',
    title: 'Оператор L3',
    badge: '3-я линия',
    lineCode: 'L3',
    email: 'operator3@example.com',
    name: 'Соколова Елена Дмитриевна',
    company: 'Третья линия (DevOps)',
    inn: '7709876543',
    description: 'Инфраструктурные инциденты, сбои очередей и исправление багов',
    defaultPassword: 'password123',
  },
  {
    role: 'supervisor',
    title: 'Администратор',
    badge: 'Супервизор',
    email: 'admin@example.com',
    name: 'Ковалев Михаил Петрович',
    company: 'Служба контроля качества',
    inn: '7705554433',
    description: 'Аналитический дашборд, мониторинг SLA, аудит и инциденты',
    defaultPassword: 'password123',
  },
];

export function getStoredTokens(): AuthTokens | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function getStoredUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredAuth(auth: AuthTokens): void {
  try {
    localStorage.setItem(TOKEN_KEY, JSON.stringify(auth));
    localStorage.setItem(USER_KEY, JSON.stringify(auth.user));
  } catch {
    // localStorage unavailable
  }
}

export function clearStoredAuth(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    // localStorage unavailable
  }
}

function parseErrorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') {
    return fallback;
  }
  const obj = data as Record<string, unknown>;
  if (obj.detail) {
    if (typeof obj.detail === 'string') {
      return obj.detail;
    }
    if (typeof obj.detail === 'object' && obj.detail !== null) {
      const detailObj = obj.detail as Record<string, unknown>;
      if (typeof detailObj.message === 'string') {
        return detailObj.message;
      }
    }
    if (Array.isArray(obj.detail)) {
      const messages = obj.detail
        .map((item: unknown) => {
          if (typeof item === 'object' && item !== null && 'msg' in item) {
            return String((item as Record<string, unknown>).msg);
          }
          return '';
        })
        .filter(Boolean);
      if (messages.length > 0) {
        return messages.join('. ');
      }
    }
  }
  if (typeof obj.message === 'string') {
    return obj.message;
  }
  return fallback;
}

export async function loginUser(
  email: string,
  password: string
): Promise<AuthTokens> {
  if (isStandaloneMode()) {
    const cleanEmail = email.trim().toLowerCase();
    const demo = DEMO_USERS.find((d) => d.email.toLowerCase() === cleanEmail);
    const tokens = generateMockAuthTokens({
      email: demo ? demo.email : email.trim(),
      role_code: demo ? demo.role : 'client',
      full_name: demo ? demo.name : email.split('@')[0],
      company_name: demo ? demo.company : 'ООО «Поставка»',
      inn: demo ? demo.inn : '7701234567',
      line_code: demo?.lineCode,
    });
    setStoredAuth(tokens);
    return tokens;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  try {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password }),
      signal: controller.signal,
    });

    if (!res.ok) {
      let errData = null;
      try {
        errData = await res.json();
      } catch {
        // non-json response
      }
      const message = parseErrorMessage(
        errData,
        res.status === 401
          ? 'Неверный адрес электронной почты или пароль.'
          : `Ошибка сервера (${res.status}). Попробуйте позже.`
      );
      throw new Error(message);
    }

    const data: AuthTokens = await res.json();
    setStoredAuth(data);
    return data;
  } catch (err: unknown) {
    if (err instanceof Error) {
      if (err.name === 'AbortError') {
        throw new Error('Превышено время ожидания ответа от сервера.');
      }
      throw err;
    }
    throw new Error('Не удалось выполнить вход. Проверьте соединение.');
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function registerUser(data: {
  email: string;
  password: string;
  full_name?: string;
  company_name?: string;
  inn?: string;
}): Promise<AuthTokens> {
  if (isStandaloneMode()) {
    const tokens = generateMockAuthTokens({
      email: data.email.trim(),
      role_code: 'client',
      full_name: data.full_name?.trim() || 'Новый Поставщик',
      company_name: data.company_name?.trim() || 'ООО «Поставка»',
      inn: data.inn?.trim() || '7701234567',
    });
    setStoredAuth(tokens);
    return tokens;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  // Санитизация полей перед отправкой на бэкенд
  const payload: Record<string, unknown> = {
    email: data.email.trim(),
    password: data.password,
  };

  if (data.full_name?.trim()) {
    payload.full_name = data.full_name.trim();
  }
  if (data.company_name?.trim()) {
    payload.company_name = data.company_name.trim();
  }
  if (data.inn?.trim()) {
    payload.inn = data.inn.trim();
  }

  try {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!res.ok) {
      let errData = null;
      try {
        errData = await res.json();
      } catch {
        // non-json response
      }
      const message = parseErrorMessage(
        errData,
        res.status === 409
          ? 'Пользователь с таким адресом электронной почты уже зарегистрирован.'
          : res.status === 422
          ? 'Неверный формат данных. Проверьте правильность email и ИНН (10 или 12 цифр).'
          : `Ошибка регистрации (${res.status}). Попробуйте позже.`
      );
      throw new Error(message);
    }

    const responseData: AuthTokens = await res.json();
    setStoredAuth(responseData);
    return responseData;
  } catch (err: unknown) {
    if (err instanceof Error) {
      if (err.name === 'AbortError') {
        throw new Error('Превышено время ожидания ответа от сервера.');
      }
      throw err;
    }
    throw new Error('Не удалось зарегистрировать пользователя. Проверьте соединение.');
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchCurrentUser(): Promise<UserProfile | null> {
  if (isStandaloneMode()) {
    return getStoredUser();
  }

  const tokens = getStoredTokens();
  if (!tokens?.access_token) {
    clearStoredAuth();
    return null;
  }

  try {
    const res = await fetch('/api/v1/auth/me', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
      },
    });

    if (!res.ok) {
      clearStoredAuth();
      return null;
    }

    const user: UserProfile = await res.json();
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } catch {
      // ignore
    }
    return user;
  } catch {
    // При сбое сети не сбрасываем локально сохраненного пользователя сразу
    return getStoredUser();
  }
}
