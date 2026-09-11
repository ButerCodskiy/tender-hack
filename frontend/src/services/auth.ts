import { AuthTokens, UserProfile, UserRole } from '../types/auth';

const TOKEN_KEY = 'portal_auth_tokens';
const USER_KEY = 'portal_auth_user';

export const DEMO_USERS: {
  role: UserRole;
  title: string;
  email: string;
  name: string;
  company: string;
  inn: string;
  defaultPassword?: string;
}[] = [
  {
    role: 'client',
    title: 'Поставщик (Клиент)',
    email: 'supplier@example.com',
    name: 'Иванов Иван Иванович',
    company: 'ООО «ТехноСнаб Поставка»',
    inn: '7701234567',
    defaultPassword: 'password123',
  },
  {
    role: 'operator',
    title: 'Оператор 1-й линии',
    email: 'operator1@example.com',
    name: 'Смирнова Анна Сергеевна',
    company: 'Служба технической поддержки',
    inn: '7709876543',
    defaultPassword: 'password123',
  },
  {
    role: 'supervisor',
    title: 'Руководитель поддержки',
    email: 'admin@example.com',
    name: 'Ковалев Михаил Петрович',
    company: 'Контроль качества сервиса',
    inn: '7705554433',
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
